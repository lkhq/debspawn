# DebSpawn

[![Build Status](https://travis-ci.org/lkorigin/debspawn.svg?branch=master)](https://travis-ci.org/lkorigin/debspawn)

Debspawn is a tool to build Debian packages in an isolated environment. Unlike similar tools like `sbuild`
or `pbuilder`, `debspawn` uses `systemd-nspawn` instead of plain chroots to manage the isolated environment.
This allows Debspawn to isolate builds from the host system much further via container technology. It also allows
for more advanced features to manage builds, for example setting resource limits for individual builds.

Please keep in mind that Debspawn is *not* a security feature! While it provides a lot of isolation from the
host system, you should not run arbitrary untrusted code with it. The usual warnings for all container technology
apply here.

Debspawn also allows one to run arbitrary custom commands in its environment. This is used by the Laniakea[1] Spark workers
to execute a variety of non-package builds and QA actions in the same environment in which we usually build packages.

Debspawn was built with simplicity in mind. It should both be usable in an automated environment on large build farms,
as well as on a personal workstation by a human user.
Due to that, the most common operations are as easily accessible as possible. Additionally, `debspawn` will always try
to do the right thing automatically before resorting to a flag that the user has to set.
Options which change the build environment are - with one exception - not made available intentionally, so
achieving reproducible builds is easier.
See the FAQ below for more details.

[1]: https://github.com/lkorigin/laniakea

## Usage

### Installing Debspawn

Clone the Git repository, install the (build and runtime) dependencies of `debspawn`:
```ShellSession
sudo apt install xsltproc docbook-xsl python3-setuptools zstd systemd-container debootstrap
```

You can the run `debspawn.py` directly from the Git repository, or choose to install it:
```ShellSession
sudo pip3 install .
```

Debspawn requires at least Python 3.5. We try to keep the dependency footprint of this tool as
small as possible, so it is not planned to raise that requirement or add any more dependencies
anytime soon.

### On superuser permission

If `sudo` is available on the system, `debspawn` will automatically request root permission
when it needs it, there is no need to run it as root explicitly.
If it can not obtain privileges, `debspawn` will exit with the appropriate error message.

### Creating a new image

You can easily create images for any suite that has a script in `debootstrap`. For Debian Unstable for example:
```ShellSession
$ debspawn create sid
```
This will create a Debian Sid (unstable) image for the current system architecture.

To create an image for testing Ubuntu builds:
```ShellSession
$ debspawn create --arch=i386 cosmic
```
This creates an `i386` image for Ubuntu 18.10. If you want to use a different mirror than set by default, pass it with the `--mirror` option.

### Refreshing an image

Just run `debspawn update` and give the details of the base image that should be updated:
```ShellSession
$ debspawn update sid
$ debspawn update --arch=i386 cosmic
```

This will update the base image contents and perform other maintenance actions.

### Building a package

You can build a package from its source directory, or just by passing a plain `.dsc` file to `debspawn`. If the result should
be automatically signed, the `--sign` flag needs to be passed too:
```ShellSession
$ cd ~/packages/hello
$ debspawn build sid --sign

$ debspawn build --arch=i386 cosmic ./hello_2.10-1.dsc
```

Build results are by default returned in `/var/lib/debspawn/results/`

### Building a package - with git-buildpackage

You can use a command like this to build your project with gbp and Debspawn:
```ShellSession
$ gbp buildpackage --git-builder='debspawn build sid --sign'
```

### Manual interactive-shell action

If you want to, you can log into the container environment and either play around in
ephemeral mode with no persistent changes, or pass `--persistent` to `debspawn` so all changes are permanently saved:
```ShellSession
$ debspawn login sid

# Attention! This may alter the build environment!
$ debspawn login --persistent sid
```

### Deleting a container image

At some point, you may want to permanently remove a container image again, for example because the
release it was built for went end of life.
This is easily done as well:
```ShellSession
$ debspawn delete sid
$ debspawn delete --arch=i386 cosmic
```

### Running arbitrary commands

This is achieved with the `debspawn run` command and is a bit more involved. Refer to the manual page
and help output for more information.


## FAQ

#### Why use systemd-nspawn? Why not $other_container?

Systemd-nspawn is a very lightweight container solution readily available without much (or any) setup on all Linux systems
that are running systemd. It does not need any background daemon and while it is light on features, it
fits the relatively simple usecase of building in an isolated environment perfectly.


#### Do I need to set up apt-cacher-ng to use this efficiently?

No - while `apt-cacher-ng` is generally a useful tool, it is not required for efficient use of `debspawn`. `debspawn` will cache
downloaded packages between runs fully automatically, so packages only get downloaded when they have not been retrieved before.


#### Is the build environment the same as sbuild?

No, unfortunately. Due to the different technology used, there are subtle differences between sbuild chroots and `debspawn` containers.
The differences should not have any impact on package builds, and any such occurrence is highly likely a bug in the package's
build process. If you think it is not, please file a bug against Debspawn. We try to be as close to sbuild's default environment
as possible.

One way the build environment differs from Debian's default sbuild setup intentionally is in its consistent use of unicode.
By default, `debspawn` will ensure that unicode is always available and default. If you do not want this behavior, you can pass
the `--no-unicode` flag to `debspawn` to disable unicode in the tool itself and in the build environment.


#### Will this replace sbuild?

Not in the foreseeable future. Sbuild is a proven tool that works well for Debian and supports other OSes than Linux, while `debspawn` is Linux-only,
a thing that will not change.


#### What is the relation of this project with Laniakea?

The Laniakea job runner uses `debspawn` for a bunch of tasks and the integration with the Laniakea system is generally quite tight.
Of course you can use `debspawn` without Laniakea and integrate it with any tool you want. Debspawn will always be usable
without Laniakea automation.


#### This tool is really fast! What is the secret?

Surprisingly, building packages with `debspawn` is often a bit faster than using `pbuilder` and `sbuild` with their default settings.
There is nothing special going on here (unless you are on a filesystem that supports copy-on-write), the speed gain comes almost
exclusively from the internal use of the Zstandard compression algorithm for base images. Zstd allows for fast decompression of the bases,
which is exactly why it was chosen (LZ4 would be even faster, but Zstd actually is a good compromise here). This shaves off a few seconds of time
for each build that is used on base image decompression.
