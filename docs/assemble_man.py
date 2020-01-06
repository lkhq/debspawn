#!/usr/bin/env python3

import os
import sys
from xml.sax.saxutils import escape as xml_escape
from functools import reduce

sys.path.append("..")


class DocbookEditor:

    def __init__(self):
        self._replacements = {}

    def add_substvar(self, name, replacement):
        self._replacements['@{}@'.format(name)] = replacement

    def register_command_flag_synopsis(self, actions, command_name):

        flags_text = ''
        flags_entries = ''
        for item in actions:
            options_text = xml_escape('|'.join(item.option_strings))
            flags_text += '<arg>{}</arg>\n'.format(options_text)

            oid = item.option_strings[0]
            desc_text = None
            if oid == '-h':
                desc_text = 'Print brief help information about available commands.'
            if command_name != 'create':
                if oid == '--variant':
                    desc_text = 'Set the variant of the selected image, that was used for bootstrapping.'
                elif oid == '-a':
                    desc_text = 'The architecture of the base image that should be selected.'

            if not desc_text:
                desc_text = item.help
            desc_text = xml_escape(desc_text)

            if desc_text.startswith('CF|'):
                desc_text = desc_text[3:]
                desc_text = desc_text.replace('binary:', '<option>binary</option>:', 1)
                desc_text = desc_text.replace('arch:', '<option>arch</option>:', 1)
                desc_text = desc_text.replace('indep:', '<option>indep</option>:', 1)
                desc_text = desc_text.replace('source:', '<option>source</option>:', 1)

            flags_entries += '''<varlistentry>
                                  <term>{}</term>
                                  <listitem>
                                      <para>
                                      {}
                                      </para>
                                 </listitem>
                              </varlistentry>'''.format(options_text, desc_text)

        self.add_substvar('{}_FLAGS_SYNOPSIS'.format(command_name.upper()), flags_text)
        self.add_substvar('{}_FLAGS_ENTRIES'.format(command_name.upper()), flags_entries)

    def process_file(self, input_fname, output_fname):

        with open(input_fname, 'r') as f:
            template_content = f.read()

        result = reduce(lambda x, y: x.replace(y, self._replacements[y]), self._replacements, template_content)

        with open(output_fname, 'w') as f:
            f.write(result)

        return output_fname


def generate_docbook_pages(build_dir):
    from debspawn.cli import create_parser

    build_dir = os.path.abspath(build_dir)

    parser = create_parser()
    editor = DocbookEditor()
    editor.register_command_flag_synopsis(parser._get_optional_actions(), 'BASE')

    xml_manpages = []
    xml_manpages.append(editor.process_file('docs/debspawn.1.xml', os.path.join(build_dir, 'debspawn.1.xml')))

    for command, sp in parser._get_positional_actions()[0]._name_parser_map.items():

        editor.register_command_flag_synopsis(sp._get_optional_actions(), command)
        template_fname = 'docs/debspawn-{}.1.xml'.format(command)
        if not os.path.isfile(template_fname):
            if command in ['ls', 'b']:
                continue  # the ls and b shorthands need to manual page
            print('Manual page template {} is missing! Skipping it.'.format(template_fname))
            continue

        xml_manpages.append(editor.process_file(template_fname, os.path.join(build_dir, os.path.basename(template_fname))))

    return xml_manpages


if __name__ == '__main__':
    generate_docbook_pages('/tmp')
