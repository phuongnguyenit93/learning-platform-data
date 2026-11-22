# Permissions for Creating Dumps with jmap

`jmap` can attach to a running JVM and write the heap to an HPROF file. A dump command only succeeds when two independent conditions are met: the operator has permission to attach to the Java process, and the account running the JVM can create files in the target directory. Having permission to run `jmap` on the host is not enough if the process belongs to another account or the dump directory is not writable.

In modern JDKs, Oracle recommends using `jcmd` for diagnosing running processes. `jmap` is still useful for understanding legacy syntax and working with existing systems, but Oracle classifies `jmap` as an experimental/unsupported tool and recommends migrating to `jcmd`. The sections below explain both so you can choose the right tool and grant permissions with the proper scope.

## 1. What Is a Dump and Which Type Are You Creating?

The term "dump" is often used for several different kinds of files. You should identify the type of data to collect before granting permissions or choosing a command.

| Dump Type | Contents | Common Tools | Purpose |
| --- | --- | --- | --- |
| Heap dump (`.hprof`) | Objects currently on the Java heap, reference fields, and object retention relationships | `jmap -dump`, `jcmd GC.heap_dump`, `-XX:+HeapDumpOnOutOfMemoryError` | Investigating memory leaks, unexpected object growth, and `OutOfMemoryError` |
| Heap histogram | Object counts and total size by class | `jmap -histo`, `jcmd GC.class_histogram` | Identifying classes consuming the most heap before taking a large heap dump |
| Thread dump | Stack traces, thread states, and optionally lock information | `jstack`, `jcmd Thread.print`, `jcmd Thread.dump_to_file` | Investigating deadlocks, blocked threads, or unresponsive applications |
| Flight Recording (`.jfr`) | Time-series JVM events such as GC, threads, locks, allocations, and CPU | `jcmd JFR.start`, `JFR.dump`, `jfr` | Inspecting behavior before/after an incident and analyzing performance |
| OS core/crash dump | OS-level process memory image, including native memory and OS state | Linux core dump, Windows crash dump, `gcore`, debugger | Investigating native crashes, JVM faults, or JNI errors |

`jmap -dump` creates an **HPROF heap dump**, not an OS core dump. A heap dump focuses on JVM-managed objects; a core dump captures broader process state, including native memory and OS state at crash time. The two file types differ in size, access permissions, and analysis methods.

## 2. Two Required Permission Layers

### Permission to Attach to the JVM

To take a dump from a running JVM, the tool must be able to connect to the target process:

- Run on the same host as the target JVM.
- With `jcmd`, use the same effective user ID and group ID that started the JVM. On Linux, this typically means running as the same service account.
- Use a JDK compatible with the target JVM. Oracle does not support using `jcmd`, `jmap`, `jstack`, or `jinfo` from one JDK version to diagnose a JVM running on a different JDK version.
- The JVM must allow the Attach mechanism. If the JVM was started with `-XX:+DisableAttachMechanism`, attach tools such as `jcmd`, `jstack`, `jmap`, and `jinfo` cannot connect through the normal mechanism.
- The PID must belong to the right host/container and PID namespace. `jcmd -l` does not list a JVM running inside a separate Docker process; in that case, look up the PID with `ps` inside the container or run the tool from within the target container.

Root or Administrator privileges should not be the default approach. Identify the application's service account and perform diagnostic operations under that exact identity. On Windows, a terminal opened as Administrator does not necessarily share the same identity as a Windows Service running under a virtual service account or domain account.

### Permission to Write the Dump File

The JVM process must be able to write the file to the requested path. Verify the following:

- The target directory already exists; dump commands do not always create parent directories automatically.
- The account running the JVM has permission to create and write files in that directory.
- On POSIX systems, the directory requires write and execute permissions for that account; all parent directories must also allow traversal.
- On Windows, the NTFS ACL must grant file creation/write permissions to the exact service identity.
- The filesystem has enough free space, and disk quotas or inode limits have not been reached.
- The path is not on a read-only mount or a failing network filesystem.
- SELinux, AppArmor, container security profiles, antivirus software, or Windows Controlled Folder Access are not blocking the write operation.

**Key takeaway:** the attach command is issued from the operator's account, but the dump file is created inside the target JVM. Therefore, you must check write permissions for the account running the application, not just the user running the command.

## 3. Granting Permissions to the Dump Directory

Create a dedicated directory per application where only the service account and the operations team have access. Do not use shared directories like `/tmp` for long-term storage of production heap dumps.

### Linux

Example for an application running as user/group `myapp`:

```bash
APP_USER=myapp
APP_GROUP=myapp
DUMP_DIR=/var/lib/myapp/dumps

sudo install -d \
  -o "$APP_USER" \
  -g "$APP_GROUP" \
  -m 0700 \
  "$DUMP_DIR"

sudo -u "$APP_USER" test -w "$DUMP_DIR" \
  && echo "DUMP_DIR_WRITABLE"
```

`0700` allows the owner to read, write, and access the directory; other users and groups have no access by default. If the SRE team needs to read dumps, create a dedicated diagnostic group and use `0750` or controlled ACLs. Never grant `0777` just to make a dump command succeed.

Verify ownership, permissions along the entire path, and available space:

```bash
namei -l /var/lib/myapp/dumps
stat -c '%U:%G %a %n' /var/lib/myapp/dumps
df -h /var/lib/myapp/dumps
df -i /var/lib/myapp/dumps
```

When running under systemd, the directory must exist and the service account must have permissions before the JVM needs to write a dump. You can use `StateDirectory=myapp` in the unit file so systemd creates the state directory according to the service policy; still verify the actual owner and mode.

### Windows

Example for a Windows Service running under the virtual account `NT SERVICE\MyApp`:

```powershell
$dumpDir = 'C:\ProgramData\MyApp\dumps'

New-Item -ItemType Directory -Force -Path $dumpDir | Out-Null

icacls $dumpDir /grant 'NT SERVICE\MyApp:(OI)(CI)M'
icacls $dumpDir
```

Replace `NT SERVICE\MyApp` with the service's actual identity. `(OI)(CI)` enables inheritance to files and subdirectories; `M` stands for Modify. Run ACL changes using an approved administrative account. Afterward, confirm that the JVM actually runs under the granted identity and that the path exists on the host/volume visible to the service.

## 4. Creating a Heap Dump Manually with jmap

`jmap -dump` attaches to a running JVM's PID and writes the heap in HPROF format.

Syntax:

```bash
jmap -dump:live,format=b,file=/var/lib/myapp/dumps/heap.hprof <PID>
```

Options:

- `live`: dumps only live objects after the JVM identifies unreachable objects.
- `format=b`: writes binary HPROF format.
- `file=...`: destination file path.
- `<PID>`: PID of the target JVM to diagnose.

If `live` is omitted, the dump may also include unreachable objects. The `live` option can trigger a Full GC and pause the process. A heap dump can be nearly as large as the currently used heap, so estimate disk space before running it.

On Windows PowerShell, here is an example using a path without spaces to simplify passing arguments to the tool:

```powershell
$pidTarget = 12345
$dumpFile = 'C:\ProgramData\MyApp\dumps\heap.hprof'

jmap.exe "-dump:live,format=b,file=$dumpFile" $pidTarget

if ($LASTEXITCODE -ne 0) {
    throw 'jmap heap dump failed'
}
```

After the command completes, verify that the file exists, is larger than 0 bytes, and is in the expected directory. If a filename already exists, choose a new name or handle the old file according to your retention policy; do not overwrite dumps needed for investigation.

### Using jcmd on Modern JDKs

Oracle recommends `jcmd` instead of the legacy `jmap`, `jstack`, and `jinfo` tools. Equivalent commands:

```bash
jcmd <PID> help GC.heap_dump

jcmd <PID> GC.heap_dump \
  -gz=1 \
  /var/lib/myapp/dumps/heap.hprof.gz
```

`GC.heap_dump` writes HPROF output. `-gz=1` enables fast gzip compression; level `1` favors speed, while level `9` compresses more aggressively at higher CPU cost. By default, the command requests a Full GC before dumping; the `-all` option includes unreachable objects and changes that behavior. According to the JDK documentation, this is a high-impact command, so avoid running it repeatedly unnecessarily on heavily loaded systems.

`jcmd` can also write a thread dump to a file:

```bash
jcmd <PID> Thread.dump_to_file \
  -format=json \
  /var/lib/myapp/dumps/threads.json
```

For Flight Recorder, you can start a recording and dump a snapshot:

```bash
jcmd <PID> JFR.start \
  name=incident \
  settings=default \
  filename=/var/lib/myapp/dumps/incident.jfr \
  maxsize=256m

jcmd <PID> JFR.dump \
  name=incident \
  filename=/var/lib/myapp/dumps/incident-snapshot.jfr
```

`JFR.dump` writes the current data to a file while the recording continues running. Set `maxsize` and `maxage` appropriately to bound disk usage. Use `jfr summary` to inspect the recording file after collection.

## 5. Automatic Heap Dump on OutOfMemoryError

If the application needs to collect a heap dump when the Java heap runs out of space, configure the JVM at startup:

```bash
java \
  -Xmx2g \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/lib/myapp/dumps \
  -XX:ErrorFile=/var/log/myapp/hs_err_pid%p.log \
  -jar myapp.jar
```

- `-XX:+HeapDumpOnOutOfMemoryError` enables heap dump creation when a Java heap-related `OutOfMemoryError` occurs.
- `-XX:HeapDumpPath` specifies the directory or filename for the heap dump. When given an existing directory, HotSpot creates `java_pid<PID>.hprof` inside that directory.
- `-XX:ErrorFile` specifies the fatal error log when the JVM encounters a critical error. The `hs_err` file is a diagnostic log, not a heap dump.

Create the directory and grant permissions before starting the service. If `HeapDumpPath` is not writable, the JVM cannot save the heap dump to the desired location. Do not rely on an arbitrary service working directory, as it can differ when launched from a terminal, systemd, or a Windows Service.

`-XX:+HeapDumpOnOutOfMemoryError` applies only to `OutOfMemoryError`; it does not replace OS core dumps when the JVM process crashes due to a native fault. Heap dumps and fatal error logs also require their own disk space.

## 6. Permissions for Creating OS Core Dumps

When analyzing native/JVM-level crashes, you need an OS core dump rather than just an HPROF file. On Linux, core file creation depends on process limits and kernel configuration.

Check the shell limit:

```bash
ulimit -c
```

If operational policy permits core dumps, configure the limit before starting the JVM:

```bash
ulimit -c unlimited
java -jar myapp.jar
```

For systemd services, process limits are set by the service manager; configure `LimitCORE=infinity` in the unit file if approved by administrators. Check `kernel.core_pattern` to see whether the kernel writes core files directly or pipes them to a collector. If using `systemd-coredump`, query dumps with `coredumpctl` according to your host's procedures.

Common reasons a core dump does not appear:

- The core size limit is `0` or too low.
- The service account cannot write to the working directory or target directory.
- The disk is full, quota is exhausted, or the network filesystem is unavailable.
- An unwritable `core` file already exists, or a directory named `core` conflicts with the filename.
- The program runs with `setuid` or kernel policy restricts core dumps.
- The JVM handles certain internal signals like `SIGSEGV` for its own purposes; not every signal produces a core file.

On Windows, crash dumps are managed by the OS/debugger diagnostic mechanisms. Write permissions and dump locations depend on Windows Error Reporting configuration or the debugger tools deployed by the organization. `jmap -dump` remains a JVM-level Java heap dump operation, distinct from a Windows process crash dump.

Given an existing core file, `jhsdb jmap --core` can analyze the heap postmortem. `jhsdb` is an experimental tool; attaching it to a running JVM can hang the process and potentially crash it when the debugger detaches. Do not use it in place of `jcmd` for routine heap dumping.

## 7. End-to-End Verification Example on Java 17+

The program below retains several byte arrays so the heap has observable data, then keeps running so tools can attach to it.

Create `DumpTarget.java`:

```java
package com.example;

import java.util.ArrayList;
import java.util.List;

public final class DumpTarget {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    private DumpTarget() {
    }

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 32; i++) {
            RETAINED.add(new byte[256 * 1024]);
        }

        System.out.println("DUMP_TARGET_READY");

        while (true) {
            Thread.sleep(1_000);
        }
    }
}
```

Compile and run on Linux:

```bash
mkdir -p build/dump-demo
javac --release 17 -d build/dump-demo DumpTarget.java

java -cp build/dump-demo com.example.DumpTarget \
  > build/dump-demo/application.log 2>&1 &
APP_PID=$!

jps -lv
```

Assume the application's PID is `12345`. Create a dedicated directory and grant permissions before running the dump command:

```bash
sudo install -d -o myapp -g myapp -m 0700 \
  /var/lib/myapp/dumps

sudo -u myapp test -w /var/lib/myapp/dumps

sudo -u myapp jcmd 12345 GC.heap_dump -gz=1 \
  /var/lib/myapp/dumps/heap.hprof.gz
```

Verify the file:

```bash
sudo -u myapp test -s /var/lib/myapp/dumps/heap.hprof.gz
ls -lh /var/lib/myapp/dumps
```

If the command reports `Permission denied`, check the JVM identity and directory write permissions using `namei -l`, `stat`, and ACL/SELinux/AppArmor settings. Do not change the directory mode to `0777` to bypass the error.

### Actual Test Results

On Windows 11 with Azul Zulu JDK 24.0.2, the same demo JVM was run under the current user account. The following operations succeeded in a dedicated test directory:

| Operation | Result |
| --- | --- |
| `jmap -dump:format=b,file=... <PID>` | Produced HPROF of about 10.9 MB |
| `jcmd <PID> GC.heap_dump -gz=1 ...` | Produced gzipped HPROF of about 1.3 MB |
| `jcmd <PID> Thread.dump_to_file -format=json ...` | Produced JSON thread dump |
| `jcmd <PID> JFR.start` and `JFR.dump` | Produced JFR recording; readable by `jfr summary` |
| `-XX:+HeapDumpOnOutOfMemoryError` with `-XX:HeapDumpPath=<directory>` | OOM test produced `java_pid<PID>.hprof` of about 19.4 MB |

These numbers are only from a small demo program, not expected sizes for production applications. All test files and processes were cleaned up after verification.

## 8. Protecting Dumps Because the Data Can Be Highly Sensitive

Heap dumps and core dumps can contain nearly the entire contents of process memory. They may include:

- Passwords, access tokens, refresh tokens, session cookies, and API keys.
- Personal data, requests/responses, transaction payloads, and cached data.
- Encryption keys, database credentials, and internal configurations.
- Application object contents, URLs, SQL queries, payloads, or customer information.

Thread dumps can expose thread names, classes, stack traces, file paths, and certain logged values. JFR recordings can contain system properties, environment metadata, thread names, and stack traces depending on event settings.

Apply these principles:

1. Only the service account and approved incident response team should have read access to dumps.
2. Store dumps on a dedicated volume with encryption at rest and strict access control.
3. Never upload heap/core dumps to public artifacts, web server directories, or unrestricted tickets.
4. Transfer files over secure channels; verify checksums after transfer.
5. Enforce short retention, audit who accesses them, and delete files once the investigation is complete.
6. Do not enable `-overwrite` unless you have explicitly confirmed the old file can be replaced.
7. Never pass passwords, tokens, or keystores in command lines or logs for dump operations.

Dumps are sensitive production data; permissions to create and read dumps should be granted separately following the principle of least privilege.

## 9. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `jmap` or `jcmd` cannot find the PID | Wrong PID, different PID namespace, or JVM running in a separate Docker container | Check with `ps` on the right host/container; use the PID from the target namespace |
| `AttachNotSupportedException` | Different effective UID/GID, attach disabled, or JVM does not support attach | Use the matching service identity, check `-XX:+DisableAttachMechanism`, and use a matching JDK |
| `Permission denied` when creating dump | JVM account cannot write to the directory or OS security policy blocks it | Check owner, mode, NTFS ACLs, SELinux/AppArmor, and permissions on parent directories |
| `No such file or directory` | Dump directory does not exist or is not mounted into the container | Create the directory before startup; check mounts/paths in the JVM namespace |
| `Not enough space` or truncated dump | Disk/quota/inode exhausted or core file limit too low | Check `df -h`, `df -i`, quotas, `ulimit -c`, and retention |
| `jmap` hangs or is unresponsive | Legacy tool or process is hung/in a long GC pause | Prefer `jcmd`; account for Full GC impact and heap size |
| Dump file missing on OOM | JVM actually lacks the flag, path is wrong, or directory is unwritable | Verify JVM command line, `HeapDumpOnOutOfMemoryError`, `HeapDumpPath`, and service account permissions |
| `hs_err_pid*.log` exists but no `.hprof` | Fatal error log and heap dump are separate mechanisms | Check `HeapDumpOnOutOfMemoryError` and the type of failure that occurred |
| Core dump does not appear | `ulimit -c`, `core_pattern`, directory permissions, or kernel policy | Check OS and service manager configuration; do not confuse with HPROF |
| File exists but cannot be opened | Incomplete write, insufficient disk space, transfer corruption, or incompatible analysis tool | Check file size, checksum, format, and JDK/analysis tool version |

## 10. Pre-Production Dump Checklist

1. Confirm whether you need a heap dump, thread dump, JFR recording, or OS core dump.
2. Identify the PID, host/container, and exact JDK version of the target JVM.
3. Identify the service account and effective UID/GID of the JVM.
4. Verify that the Attach mechanism is not disabled.
5. Create the target directory in advance and grant write permission to the JVM account.
6. Check disk space, quotas, inodes, and core dump limits.
7. Choose a unique filename containing an incident ID and timestamp.
8. Estimate Full GC impact and heap size before taking an HPROF dump.
9. Run one dump command, then verify its exit code and file size.
10. Verify that the HPROF/JFR file can be opened with the appropriate analysis tool.
11. Restrict read permissions, enable encryption, audit access, and enforce retention.
12. Record the JDK version, PID, command, timestamp, operator, and checksum.

## 11. Key Takeaways

- `jmap -dump` creates an HPROF Java heap dump; it does not create an OS core dump.
- Creating a dump requires both permission to attach to the JVM and write permission for the JVM's account on the target directory.
- `jcmd` requires the same host and the same effective UID/GID; `-XX:+DisableAttachMechanism` disables attach tools.
- Oracle recommends `jcmd` over `jmap` because `jmap` is classified as experimental/unsupported.
- `-XX:+HeapDumpOnOutOfMemoryError` and `-XX:HeapDumpPath` enable automatic heap dumps on Java heap OOM.
- Linux core dumps also depend on `ulimit -c`, `core_pattern`, working directory, and kernel policy.
- JDK 24 and later permanently disable the Security Manager; attach errors cannot be fixed by adding grants to `java.policy`.
- Heap and core dumps can contain secrets and customer data; grant read access only to investigators, store encrypted, and delete per retention policy.

When JVM identity, attach permissions, and directory write permissions are verified up front, taking a dump becomes a controlled diagnostic operation. The team can collect the necessary evidence without granting overly broad privileges across the entire server.

## References

- [Oracle JDK 24: Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [Oracle JDK 24: The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle JDK 24: The java Command and HeapDumpPath](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [Oracle JDK 24: Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/24/troubleshoot/prepare-java-troubleshooting.html)
- [Oracle JDK 24: Submit a Bug Report and Collect Core Dumps](https://docs.oracle.com/en/java/javase/24/troubleshoot/submit-bug-report.html)
- [Oracle JDK 24: The jhsdb Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jhsdb.html)
- [Oracle: The Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/27/security/security-manager-is-permanently-disabled.html)
