# Preparing the Linux Environment for the Lab

CRaC labs require a Linux environment capable of checkpointing and restoring Java processes. In addition to a CRaC-enabled JDK, the machine needs a suitable kernel, the CRIU tool, and the necessary system permissions to save and restore process state.

The preparation should be done on a dedicated Linux machine or a virtual machine used for learning. A virtual machine helps control the operating system version, kernel, JDK, and access permissions; at the same time, the environment can be recreated if an experimental configuration goes wrong.

## 1. Understanding the Environment Components

A CRaC environment on Linux has the following main components:

| Component | Role |
|---|---|
| Linux kernel | Provides low-level mechanisms to freeze, record, and restore process state |
| CRIU | User-space process checkpoint/restore tool; the CRaC runtime uses it to work with operating system state |
| CRaC-enabled JDK | A JVM with CRaC integration, providing options and APIs for applications to participate in the checkpoint/restore lifecycle |
| Java application | Prepares resources before checkpoint and recovers resources after restore when needed |
| Checkpoint directory | Stores the images and metadata created during the checkpoint process |

CRaC and CRIU have different responsibilities. CRaC provides JVM-level integration and application APIs; CRIU performs most of the process checkpoint/restore work on Linux. Installing CRIU alone does not give a regular JDK CRaC capabilities. Conversely, having a CRaC-enabled JDK without CRIU or without the required kernel permissions can still cause the checkpoint operation to fail.

## 2. Choosing a Suitable Linux Machine

### Recommended Environment

To get started, use a popular Linux distribution that has a CRIU package and can install a corresponding CRaC JDK. 64-bit Ubuntu LTS is a convenient choice for the lab because it has the APT package manager and extensive community documentation.

A physical machine or a virtual machine can be used. With a virtual machine, ensure that the kernel inside the virtual machine provides the features required by CRIU; the host operating system's configuration does not substitute for the guest kernel running the JVM.

Other environments need to be evaluated separately:

- Debian and Fedora can be used if the operating system version, kernel, CRIU, and JDK are in a supported combination.
- Rocky Linux, AlmaLinux, and RHEL-compatible distributions depend on the repository version and available CRIU packages.
- WSL1 does not provide an independent Linux kernel, so it is not suitable for CRIU labs. WSL2 has a Linux kernel, but usability still depends on the kernel, permissions, and CRIU features; it must be checked directly using the criu check command.
- Containers share the kernel with the host and may be restricted by capabilities, namespaces, seccomp, or security policies. It is best to complete the lab on a Linux host or VM before moving to containers.

Do not choose an operating system based solely on the distribution name. Also check the CPU architecture, the running kernel, and the support matrix of the CRaC JDK vendor. Some JDK distributions only provide CRaC builds for certain architectures; do not assume every x86-64 build has an equivalent ARM64 build.

### Gathering System Information

Open a terminal on the Linux machine and run:

~~~bash
cat /etc/os-release
uname -r
uname -m
id
~~~

These commands show:

- /etc/os-release: distribution name and version.
- uname -r: the currently running kernel version, not a kernel version that is installed but not yet booted.
- uname -m: machine architecture, commonly x86_64 or aarch64.
- id: current user and groups.

Record this information for reference when installing the JDK and troubleshooting errors. If you have just upgraded the kernel, reboot the machine before checking to make sure the JVM runs on the new kernel.

## 3. Installing and Checking CRIU

CRIU (Checkpoint/Restore In Userspace) is the component that records and restores process state. The CRaC runtime typically needs to invoke CRIU during the checkpoint/restore process.

### Installing on Ubuntu or Debian

On APT-based systems, update the package index and install CRIU:

~~~bash
sudo apt update
sudo apt install -y criu
~~~

Check the binary and version:

~~~bash
command -v criu
criu --version
~~~

If command -v criu does not return a path, the shell has not found CRIU. Check the package installation output, the distribution's package name, and the PATH variable.

### Installing on Fedora

On Fedora, it can be installed using DNF:

~~~bash
sudo dnf install -y criu
~~~

After installation, verify with command -v criu and criu --version as above. For RHEL-family distributions, use a repository supported by your administrator or operating system vendor; package locations and versions may vary.

### Checking Kernel Capabilities

Run the CRIU checks:

~~~bash
sudo criu check
sudo criu check --all
~~~

criu check verifies the basic conditions for CRIU to work. criu check --all additionally checks optional features that CRIU can use. Read the full output instead of just looking at the command exit code.

If the check fails, the cause may fall into one of the following categories:

- The kernel lacks a required feature or an unsuitable kernel is running.
- CRIU is too old for the kernel or lacks support for a feature.
- The current user lacks the required permissions.
- A container, namespace, or security policy is restricting the operation.
- An optional feature is unsupported even though basic checkpoint functionality can still be used.

Not every warning from criu check --all means that no labs can be run. Distinguish mandatory features from optional features, then cross-check with the JDK requirements and the lab content.

## 4. Checking Checkpoint/Restore Permissions

Checkpoint and restore require permissions to operate on processes and certain kernel resources. Specific permissions depend on the kernel version, CRIU, how the JVM is run, and security configuration.

In a virtual machine dedicated to the lab, the simplest approach is to start with the permission configuration according to the documentation of the CRaC JDK and CRIU versions being used. Some setups require administrative privileges; some newer environments can configure appropriate capabilities to run as a regular user.

Note the following points:

- Running sudo criu check only confirms that CRIU can perform the check within the privilege context of that command. It does not by itself prove that a JVM run by a regular user also has sufficient permissions.
- The Java process and the jcmd command controlling the process usually need to run under the same user. Avoid starting the application with one user and controlling it with another user.
- If using a regular user, follow the least-privilege guidelines of CRIU, the kernel, and the JDK vendor. A capability such as CAP_CHECKPOINT_RESTORE may be relevant on kernels that support it; older kernels or other operations may require additional permissions.
- In a container, container permissions are restricted independently of root privileges inside the container. Having UID 0 inside a container does not mean having full privileges on the host.
- Do not arbitrarily set setuid or grant all capabilities to the CRIU binary. Those changes elevate the privileges of a system program and must be well understood before applying.

If criu check reports an error related to ptrace or Yama, check the current policy:

~~~bash
sysctl kernel.yama.ptrace_scope
~~~

Only adjust the policy when the error message and environment documentation indicate it is the cause. Do not disable ptrace protection on a shared machine just to make the lab work. If a change is needed, prefer a temporary configuration in a dedicated VM and restore it after the lab.

SELinux and AppArmor can also restrict access. When encountering permission errors, check audit logs or kernel logs to identify the exact blocked action. Do not disable the entire protection mechanism as a default troubleshooting step.

## 5. Installing a CRaC-enabled JDK

Not every OpenJDK distribution includes CRaC. You need to download a JDK published by a vendor with CRaC support that matches:

- The Java version required by the module and lab.
- The Linux distribution in use.
- The CPU architecture of the machine.
- The CRaC and CRIU versions supported by the vendor.

Follow the JDK vendor's installation instructions. It can be installed from a package repository or extracted from an archive into a separate directory. Do not overwrite the system JDK if the machine also serves other applications.

After installation, set JAVA_HOME to point to the CRaC JDK directory. For example, if the JDK is extracted to /opt/jdks/crac-jdk:

~~~bash
export JAVA_HOME=/opt/jdks/crac-jdk
export PATH="$JAVA_HOME/bin:$PATH"
~~~

This is an example path; replace it with the actual directory on your machine. You can add these two lines to the user's shell configuration file to keep the setting when opening a new terminal.

Check the JDK currently in use:

~~~bash
echo "$JAVA_HOME"
command -v java
java -version
command -v jcmd
~~~

Ensure java and jcmd come from the same JDK. If java -version displays a different JDK, check the PATH order, shell configuration files, and Java symbolic links.

### Checking JVM CRaC Options

A quick way to check is to ask the JVM to recognize the checkpoint option:

~~~bash
java -XX:CRaCCheckpointTo=/tmp/crac-option-check -version
~~~

This command only checks whether the JVM recognizes the CRaCCheckpointTo option; because the program only prints the version and exits, it **does not perform an actual checkpoint**. If the JVM reports Unrecognized VM option, you are most likely using a JDK without CRaC or have selected the wrong Java on PATH.

Do not infer restore capability solely from the JVM accepting an option. A complete checkpoint/restore smoke test must be performed using the actual JDK, CRIU, and permissions of the environment.

## 6. Preparing the Checkpoint Directory

Checkpointing can generate many image and metadata files. Choose a local directory where the user running the JVM has read, write, and file creation permissions. For example:

~~~bash
mkdir -p "$HOME/crac/checkpoints"
chmod 700 "$HOME/crac/checkpoints"
df -h "$HOME"
~~~

A directory in home helps restrict access to the current user. Check available disk space before running the lab; checkpoint size depends on the heap, process state, and saved resources.

When choosing a checkpoint storage location, note:

- Prefer a local filesystem on the VM or Linux machine.
- Do not use a temporary directory that may be automatically cleaned on reboot if you want to keep checkpoints across restarts.
- Avoid network filesystems or cloud-synced directories during your first lab; only use them once compatibility has been verified.
- Ensure the restoring user has read permissions for the checkpoint and required files.
- Keep mount paths and directory structures consistent between checkpoint and restore.
- Do not manually edit or delete files inside the checkpoint.

Checkpoints may contain sensitive data from the application's memory, such as tokens, user information, or business data. Protect the checkpoint directory like sensitive data: restrict access permissions, do not commit it to Git, and do not share it publicly.

## 7. Checking Environment Limits

Before running the application, check resources and the shell environment:

~~~bash
free -h
df -h
ulimit -n
id
~~~

These commands help detect common issues early:

- Too little RAM compared to the heap and data the application needs to hold.
- Insufficient filesystem space for the checkpoint.
- File descriptor limit lower than the application's needs.
- The running user is not the expected user or lacks required groups/permissions.

If using a VM, allocate enough RAM and disk for the sample application and checkpoint. You do not need to allocate overly large resources for the first lab; start with a small application and increase as needed.

Check network connectivity if the lab uses a database, HTTP service, or message broker. Hostnames, DNS, routes, and firewalls must allow the application to reconnect after restore. A TCP connection opened before checkpoint may no longer be valid after restore; the environment must allow the application to create new connections.

## 8. Notes on Running in Containers

Containers do not have their own kernel. CRIU runs based on the host's kernel, while the container only sees a subset of resources and permissions granted by the host.

A container can have criu installed and run as the root user and still fail to checkpoint due to:

- Missing required capabilities.
- Seccomp blocking necessary syscalls.
- Namespaces not allowing operations on related processes or resources.
- Improper /proc mount or required filesystems.
- SELinux/AppArmor or container runtime policies restricting permissions.

Therefore, do not copy the exact CRIU installation commands from a VM and expect a container to behave identically. If the lesson is run in a container, specific instructions are needed for the image, runtime, host kernel, capabilities, and security policies. Use the minimal configuration according to the environment's official documentation; do not enable privileged mode or disable seccomp arbitrarily.

## 9. Smoke Test Before Starting the Lab

After completing the above steps, re-run the check commands:

~~~bash
cat /etc/os-release
uname -r
uname -m
criu --version
sudo criu check
java -version
command -v java
command -v jcmd
echo "$JAVA_HOME"
~~~

Compare the results with the requirements of the chosen CRaC JDK. If the basic checks succeed, the next step is to run a small Java application using this JDK, create a checkpoint, and restore it in the same environment.

For a sample application, the general workflow looks like:

1. Start the application with the CRaC-enabled JDK and specify the checkpoint directory via the -XX:CRaCCheckpointTo option.
2. Wait for the application to finish initializing and be ready for checkpoint.
3. Use jcmd from the same JDK and the same user to request the JVM to checkpoint, following the command provided by the CRaC JDK.
4. Confirm that the checkpoint has been created and the process has entered the state expected by the runtime.
5. Restart the JVM using the restore option -XX:CRaCRestoreFrom pointing to the checkpoint, according to the documentation of the JDK distribution in use.
6. Confirm that the application continues operating and external resources are recreated or validated.

Option names and control commands must match the CRaC JDK distribution. If the lab provides specific commands, use those exact commands instead of guessing from another JDK distribution.

A successful smoke test should confirm all three things: the JVM actually creates a checkpoint, the JVM can restore from that checkpoint, and the application continues processing after restore. Simply seeing the checkpoint directory appear or seeing java -version run successfully is not enough to conclude that the entire environment is ready.

## 10. Troubleshooting Common Setup Errors

| Symptom | Check Direction |
|---|---|
| criu: command not found | Check whether the package is installed and whether PATH includes the binary directory |
| criu check reports missing permissions | Run the check in the exact user/capability context that the JVM will use; see CRIU and JDK permission guides |
| CRIU reports unsupported kernel | Check uname -r, the booted kernel, and the kernel requirements of the CRIU version |
| criu check --all reports an optional feature unavailable | Determine whether that feature is required for the lab or the type of resource being checkpointed |
| JVM reports Unrecognized VM option for CRaCCheckpointTo | Verify JAVA_HOME, PATH, and java -version; install the correct CRaC-enabled JDK |
| java and jcmd come from two different directories | Put $JAVA_HOME/bin at the front of PATH and reopen the terminal |
| Checkpoint fails with Permission denied | Check user permissions, checkpoint directory, capabilities, ptrace, and SELinux/AppArmor policies |
| Restore cannot connect to database or broker | Check resource recovery callbacks, DNS, firewall, credentials, and remote service status |
| Insufficient disk space | Check df -h, clean up old lab data properly, and choose a local filesystem with enough space |

When encountering an error, keep the full messages from the JVM, CRIU, and kernel. A single Permission denied line is not enough to determine which permission needs to be changed; you need to know which process was denied, on which file or syscall, and in which user/capability context.

## 11. Environment Completion Checklist

Before moving on to the lab, confirm the following items:

- [ ] Running on a suitable Linux kernel; OS version, kernel, and CPU architecture have been recorded.
- [ ] CRIU is installed and the criu --version command works.
- [ ] criu check has been run in the appropriate permission context; any remaining errors are understood.
- [ ] The correct CRaC-enabled JDK for the current OS and architecture has been installed.
- [ ] JAVA_HOME, java, and jcmd all point to the intended JDK.
- [ ] The JVM recognizes the JDK's CRaC options.
- [ ] The user running the application has the necessary permissions for CRIU and the checkpoint directory.
- [ ] The checkpoint directory is on a suitable filesystem, has sufficient space, and has protected access permissions.
- [ ] Limits of the VM, container, or security policies (if any) have been identified.
- [ ] A complete checkpoint/restore smoke test has succeeded before doing the main lab.

Once the above conditions are met, the Linux environment is ready to practice the checkpoint and restore steps. During learning, keep the JDK, kernel, and permission configuration stable so that application errors can be distinguished from environment errors.
