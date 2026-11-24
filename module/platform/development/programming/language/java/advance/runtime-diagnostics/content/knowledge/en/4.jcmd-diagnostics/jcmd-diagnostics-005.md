# 4.5 Choosing Output Paths in the Target JVM Context and Checking Remaining Disk Space

When diagnosing Java with **jcmd**, a command may be typed on a Linux host, inside a container, or via a Pod control tool; however, **the heap dump or JFR file is created by the target JVM**. Therefore, the output path must be interpreted in the **target JVM's filesystem/mount namespace and working directory**, not assumed to match the directory where the operator runs the command. If chosen wrongly, the command may report **No such file or directory**, **Permission denied**, **Read-only file system**, or **No space left on device**; worse, the dump may succeed yet land in a hard-to-retrieve location, be deleted when the container restarts, or fill up a volume holding application data.

Within **The jcmd Tool** section, this lesson focuses on **how to decide where files are saved**, **checking sufficient space before collection**, and **verifying the file after writing**. The jcmd examples are based on **JDK 21/HotSpot**; command syntax and attachability must be re-confirmed on the real JVM. Never run heap-dump commands against production merely to practice this lesson.

## 1. Learning objectives

After this lesson, you will be able to:

- Distinguish **paths handled by the target JVM** from **stdout redirection paths handled by the shell invoking jcmd**.
- Predict differences between absolute paths, relative paths, the JVM's working directory, and paths existing only on the host or inside a container.
- Select a writable volume or directory with suitable **permissions**, **capacity**, **inodes**, **quotas**, **retention**, and **file retrieval mechanism**.
- Run preflight checks with **pwd, id, ls/stat, df -h, df -i** in the right environment and understand the limits of each check.
- Estimate required space for **JFR** and **heap dumps**, distinguishing final output file size from temporary buffers/repositories and concurrent writes.
- Understand why **Docker overlay**, **bind mounts**, **Docker volumes**, **Kubernetes emptyDir/PVC**, and **tmpfs** lead to different choices.
- Verify output after jcmd succeeds, copy files safely, and avoid mistaking incomplete/truncated files for valid diagnostic data.

## 2. Foundational question: who actually opens the output file?

**jcmd** is a utility that asks a **running JVM** to execute a diagnostic command. When the JVM writes a file, writing typically happens **inside the JVM process** with the access permissions and filesystem visible to the JVM. The jcmd caller may be somewhere else.

Compare these three operations on JDK 21 HotSpot; **12345** is an illustrative PID and must not be used literally on a real machine:

~~~bash
jcmd 12345 VM.version
jcmd 12345 Thread.print -l > ./thread-dump.txt
jcmd 12345 GC.heap_dump /diagnostics/heap/incident-001.hprof
~~~

The three operations have **three output semantics**:

| Operation | Where does output data go? | Who determines the path? |
| --- | --- | --- |
| **VM.version** | Text content in stdout of the jcmd utility | No dump data file is created in this example. |
| **Thread.print -l > ./thread-dump.txt** | **./thread-dump.txt** relative to the working directory of **the shell running jcmd** | The **>** operator is handled by the shell; if the shell is on the host the file is on the host, if inside a container it is in the container. |
| **GC.heap_dump /diagnostics/heap/incident-001.hprof** | HPROF file at a path accessible by **the target JVM** | The filename is a **diagnostic command argument**, executed by the JVM. |

Similarly, with the command:

~~~bash
jcmd 12345 JFR.dump name=incident filename=/diagnostics/jfr/incident-001.jfr
~~~

**/diagnostics/jfr/incident-001.jfr** must make sense to **the target JVM**. The file does not automatically appear at the same path on your laptop/host just because you invoked jcmd from there.

**Additional distinction:** **jcmd -f commands.txt** reads an **input file containing commands** on the jcmd tool side. By contrast, **JFR.dump**'s **filename=...** option or **GC.heap_dump**'s file argument tells the JVM to create an **output file**. Do not treat every path appearing on the same command line as belonging to the same filesystem side.

### 2.1. Two operational perspectives for a containerized JVM

Suppose there is a container **orders-java**, where the JVM sees:

~~~text
/app                      application and working directory
/diagnostics              mount point for diagnostic files
/diagnostics/jfr          JFR output directory
/diagnostics/heap         heap dump output directory
~~~

On the Linux host, directory **/srv/diag/orders/** is bind-mounted to **/diagnostics**. Then:

- The JVM receives **/diagnostics/heap/a.hprof**, opens the file via the container path, and writes into the mount.
- Users on the host can see the same data at **/srv/diag/orders/heap/a.hprof**, provided this bind mount is actually configured.
- Passing **/srv/diag/orders/heap/a.hprof** to jcmd as the dump path **is wrong** if the JVM does not have that host path in its mount namespace.
- Another container may mount the **same volume** at a different path name; verify the mount layout of **the exact JVM container**.

The host path and container path are **two names for storage according to mount configuration**, not two strings you can arbitrarily translate from the container name.

## 3. Absolute paths, relative paths, and working directory

### 3.1. Absolute paths are the safer default

For files created by the JVM, prefer **absolute paths in the JVM's filesystem**:

~~~bash
jcmd 12345 GC.heap_dump /diagnostics/heap/orders-incident-001.hprof
jcmd 12345 JFR.dump name=incident filename=/diagnostics/jfr/orders-incident-001.jfr
~~~

Mandatory prerequisites are that **/diagnostics/heap** and **/diagnostics/jfr** actually exist, allow JVM write access, and have sufficient space. The commands above are **naming examples**, not confirmation of paths or capacity in any real environment.

Use filenames that distinguish **service/instance/timestamp/incident** instead of repeating **heap.hprof**. By default, **GC.heap_dump** on JDK 21 has an **-overwrite** option defaulting to **false**; do not rely on overwriting old files and do not enable overwrite without a clear reason.

### 3.2. Relative paths can place files in unexpected locations

Example:

~~~bash
jcmd 12345 GC.heap_dump heap.hprof
jcmd 12345 JFR.dump name=incident filename=incident.jfr
~~~

Do not assume these two files end up in the jcmd terminal's current directory. They are created from the **target JVM's** perspective. For relative paths in these commands, check the **JVM's working directory** or where the JVM was launched per its specific mechanism; **never use the jcmd utility's cwd to draw conclusions**.

For instance, you might stand in **/home/operator/** on the host, while the Java process was launched from **/app** inside a container. The file will not necessarily be in **/home/operator/**.

On Linux, if you have permission to inspect procfs of **the right JVM** from the corresponding scope:

~~~bash
readlink /proc/12345/cwd
~~~

The command returns the **current working directory of the process** as seen by that procfs. If the JVM inside a container has PID **1** while its host PID is **48210**, **/proc/1/cwd** inside the container and **/proc/48210/cwd** on the host can represent the same process across two namespaces. What path is shown and whether it is readable also depend on mount namespaces and symlink read permissions. This is a **verification step**, not an automatic PID translation.

**System.getProperty("user.dir")** in Java normally reflects the working directory Java received at startup, though that property can be modified and is not an OS-level check for all cwd changes. When you need certainty about where files are opened, prefer **explicitly configured absolute paths** and verify from the JVM's side.

### 3.3. Do not rely on an implicit /tmp path

Some JFR modes use a **temporary repository**, often defaulting to the OS temporary directory. Meanwhile, the final output file of **JFR.dump**/**JFR.start** may be configured at another path. Thus, a situation can occur where **the destination volume still has free space** while **/tmp or the JFR repository runs out of space**. Check both locations when using JFR with **disk=true**.

**/tmp** is not always the same storage type: it may sit on the container's writable layer, on another volume, or on **tmpfs**. Only **df/findmnt/mount** and actual container configuration tell you for sure. Picking **/tmp** because "everyone has it" does not replace checking space, quotas, write permissions, or data lifecycle.

## 4. Choosing a location by data lifecycle and deployment architecture

| Location | Advantages | Limitations to check |
| --- | --- | --- |
| **App directory in container writable layer** | Path may be easy to reference | Can be lost when container is replaced, shares space with image/log layers, and is subject to ephemeral storage limits. May be blocked if root filesystem is read-only. |
| **Docker bind mount** | Maps explicitly to a Linux host path; easy file retrieval when set up properly | Ownership, SELinux/ACL where applicable, host path, and host/container differences must be verified. "Host" here means the machine running the Docker daemon, not necessarily the machine running Docker CLI. |
| **Docker named volume** | Docker manages storage lifecycle; can be shared with another container if configured | Do not guess host path from volume name; use Docker metadata to inspect. Remaining space depends on underlying filesystem/driver/quota. |
| **Kubernetes emptyDir on disk** | Temporary directory for a Pod; can be mounted into both Java container and sidecar | Usually lost when Pod is removed from the node; bounded by ephemeral-storage/sizeLimit and node disk pressure. |
| **Kubernetes emptyDir with medium: Memory** | Fast I/O access in tmpfs | Consumes **RAM** and counts against memory limits; a large heap dump can cause memory pressure/OOM instead of merely "disk full". |
| **Kubernetes PVC** | Can suit retaining files across Pod lifecycle, depending on StorageClass and policy | Check real quota, mount permissions, throughput, filesystem, concurrent access, and sensitive data. A PVC does not automatically guarantee free space. |
| **NFS/remote volume/object pipeline** | Can simplify retrieval and policy management | Network I/O and state increase dump duration; path must be a real mount/file API to the JVM. Object store URIs cannot inherently be used like HPROF/JFR file paths. |

It is good practice to have a **dedicated diagnostic directory**, isolated from critical operational data, with controlled retention/cleanup procedures. Choose the target according to **diagnostic goal**: short JFR captures usually require less space than large heap dumps, though there is no fixed size rule. Dump files can contain sensitive data, so choosing where to store them is both an operational and security decision.

### 4.1. Docker bind mount example

Illustrative configuration design example:

~~~bash
docker run --name orders-java \
  --mount type=bind,source=/srv/diag/orders,target=/diagnostics \
  my-orders-image
~~~

Inside the JVM container, use **/diagnostics/...**; on the Docker daemon's Linux host, inspect **/srv/diag/orders/...**. This is an illustrative container launch command; do not re-run it if the service is already live.

To inspect mounts of a running container, this is a read-only metadata query:

~~~bash
docker inspect --format '{{json .Mounts}}' orders-java
~~~

Fields in the metadata identify **Source** and **Destination**. Never guess them from the image name or container name.

**Docker Desktop:** Linux containers run inside a Linux VM; host/bind-mount paths go through a mapping layer to the desktop machine. Rely on Docker-supported metadata/paths instead of assuming VM **/proc** or directories match Windows/macOS paths directly.

### 4.2. Kubernetes structure example

The YAML snippet only illustrates **mount structure**, not a complete manifest:

~~~yaml
spec:
  containers:
    - name: app
      image: example/orders:1.0
      volumeMounts:
        - name: diagnostic-files
          mountPath: /diagnostics
  volumes:
    - name: diagnostic-files
      emptyDir:
        sizeLimit: 4Gi
~~~

Even if the example declares **sizeLimit: 4Gi**, do not run **df -h** and conclude a full 4 GiB is usable: **sizeLimit**, container/Pod **ephemeral-storage** limits, and node pressure can restrict actual usable capacity under Kubernetes accounting/eviction rules. Kubelet and filesystem configuration govern how this is enforced. When data must survive Pod deletion, a properly provisioned and mounted **PVC** is generally more suitable than emptyDir.

## 5. Choose output type before budgeting space

### 5.1. JFR: final file and repository need not be in the same place

**JFR.start** can start a recording and, when the recording stops, write a file at the configured **filename**. In **JDK 21 jcmd** docs, **duration=60s** sets the recording duration; **filename** specifies the output file when the recording finishes. By default **disk=true** can use a disk repository while recording. **JFR.dump** creates a dump file from a running recording, and **the recording continues running** after the dump.

Illustrative example, run only after preflight:

~~~bash
jcmd 12345 JFR.start name=orders-triage settings=default duration=60s filename=/diagnostics/jfr/orders-triage-001.jfr
jcmd 12345 JFR.check
~~~

The file **orders-triage-001.jfr** may only appear once the recording stops, rather than immediately after JFR.start returns success. Check **JFR.check**, diagnostic output, and expected duration before concluding the file is missing.

Another option, if recording **orders-triage** is already active:

~~~bash
jcmd 12345 JFR.dump name=orders-triage filename=/diagnostics/jfr/orders-triage-snapshot-001.jfr
~~~

**JFR.dump** does not stop a running recording. If **name** is omitted, JDK 21 syntax allows dumping data from multiple active recordings; specify an explicit name to avoid mixing contents. With **JFR.dump**, the filename argument can be a directory so the JVM generates a filename; when you need predictable paths and verification, specify a **full filename**.

Placeholders **%p** and **%t** are supported by JDK 21 in JFR **filename** to insert JVM PID/timestamp, which helps prevent name collisions. Do not generalize that every diagnostic command supports the same placeholders.

A **JFR storage budget** should include: intermediate repository (if used), final exported file, repeated dumps, related diagnostic logs, and safety headroom. **JFR.start maxsize** can cap recording data retained on disk per JFR mechanics, yet it does not guarantee the entire filesystem will not fill up from other files or a series of separate dump files.

### 5.2. Heap dump: large size, pause-time risk

**GC.heap_dump** creates an HPROF heap dump and is documented in JDK 21 as **Impact: High**, depending on heap size and contents. Per documentation, the command normally requests a full GC before dumping unless **-all** is used to dump unreachable objects too. Consequently, a heap dump can induce noticeable pauses as well as CPU, I/O, and disk impact.

Absolute filename example:

~~~bash
jcmd 12345 GC.heap_dump /diagnostics/heap/orders-incident-001.hprof
~~~

JDK 21 also supports compression:

~~~bash
jcmd 12345 GC.heap_dump -gz=1 /diagnostics/heap/orders-incident-001.hprof.gz
~~~

**Do not run both commands on the same incident just to "be sure we get a file"**: those are two separate dump operations and can generate heavy load. **-gz=1** requests the corresponding GZIP compression level, which may reduce on-disk size while adding CPU work; compression ratios are **not fixed** and do not guarantee a file stays below a given threshold. Compressed files require an analysis tool supporting that format.

**-Xmx** indicates the JVM's maximum heap limit when active, **not the exact size of an HPROF file**. Live set, object graph, HPROF structure, compressibility, and runtime dump overhead all cause sizes to vary. A heap dump can be very large; in production, use a **conservative estimate based on heap, observed metrics, and headroom**, rather than assuming "the file will surely be only 10% of -Xmx".

**Warning:** heap dumps can contain tokens, sessions, personal information, and configuration strings still sitting on the heap. Avoid public mounts, avoid copying into uncontrolled shared folders, and enforce proper retention/deletion policies after analysis.

### 5.3. Crash/OOM dumps and JFR dumps are separate mechanisms

When a JVM is launched with:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/diagnostics/heap
~~~

an automatic heap dump on **OutOfMemoryError** uses the configured path per **java** command docs and the filesystem visible to the JVM. This is a **startup** configuration, distinct from manually invoking **jcmd PID GC.heap_dump**. If the path is unwritable or out of space at OOM time, the file may not be created; do not treat the flags as an absolute guarantee of collection.

Likewise, JFR files are written when a **recording finishes**, when running **JFR.dump**, or when **dumponexit** is configured, depending on the mode. Never assume merely seeing JFR options means a file already sits at a fixed location.

## 6. Inspecting the exact destination directory: existence, permissions, and filesystem

Suppose the intended destination is **/diagnostics/heap** inside a container. Before asking the JVM to create a file, verify **on the very filesystem the JVM sees**:

~~~bash
id
pwd
ls -ld /diagnostics /diagnostics/heap
df -h /diagnostics/heap
df -i /diagnostics/heap
~~~

Illustrative commands for a Linux shell having those tools. If a minimal image lacks **sh, df, stat, ps**, that is an image limitation; use ops-approved debug/runtime tools instead of assuming the mount does not exist.

**Meaning of each check:**

1. **id**: displays UID/GID of **the current shell**. Crucial because a shell via **docker exec/kubectl exec** may run as a different user from the JVM. **The caller's permissions are not automatically the JVM's permissions**.
2. **pwd**: displays cwd of **the shell**, just for orientation; does not prove the JVM's cwd if the shell is a separate process.
3. **ls -ld**: confirms the directory actually exists and shows owner/group/mode; if ACLs, SELinux, or mount policies apply, mode bits alone are inconclusive.
4. **df -h directory**: inspects the filesystem hosting the directory and free blocks from the running command's perspective.
5. **df -i directory**: inspects free inodes if supported by the filesystem. Exhausting inodes can block file creation even when blocks remain.
6. If **findmnt -T /diagnostics/heap** or **stat -f** is available: inspect mount/filesystem type to distinguish overlay, volume, and tmpfs.

**Pass an existing path to df**. If the target file does not exist yet, **df -h /diagnostics/heap/incident.hprof** can fail because the path does not exist; check **the parent directory**:

~~~bash
df -h /diagnostics/heap
df -i /diagnostics/heap
~~~

If **/diagnostics/heap** does not exist yet, inspect an existing ancestor directory to identify the mount, then **confirm how to create the directory with proper permissions/process** before dumping. Creating a directory under the wrong mount point can land data in the container's writable layer instead of the intended volume.

### 6.1. Verify permissions using the JVM's exact identity

Suppose the container shell runs as root while the JVM runs as UID **10001**; the command:

~~~bash
test -w /diagnostics/heap
~~~

returning success for root **does not prove UID 10001 can write**. Verify using the JVM's effective user/group or configured ACL/mount permissions. Files created by the JVM must reside where **the JVM has permission to open/write**, not just the jcmd utility.

With Docker, **docker exec --user 10001 ...** can help test a matching user, though effective GID, supplementary groups, and mount security still matter. Avoid assuming from a matching UID name alone. On Kubernetes, check **securityContext**, UID/GID/fsGroup, and actual volume permissions; root seeing a file does not guarantee the JVM user can write.

Check for a **read-only root filesystem** (e.g., Kubernetes **readOnlyRootFilesystem**), **:ro** mounts, read-only bind mounts, or volume policies. When a destination directory is read-only, **df** may still show plenty of free blocks, yet writing will fail.

### 6.2. Check physical path, symlinks, and inodes

If **/diagnostics/heap** is a symlink pointing elsewhere, checking a nearby parent directory may measure **the wrong filesystem**. Verify with available tools:

~~~bash
ls -ld /diagnostics/heap
readlink -f /diagnostics/heap
df -h /diagnostics/heap
df -i /diagnostics/heap
~~~

Depending on the image, **readlink -f** may be absent or handle symlinks differently. For stricter security, avoid symlinks pointing outside the diagnostic volume and use a specific pre-provisioned directory.

**Inodes** are rarely the primary bottleneck for **one large heap dump**, but can become an issue when creating thousands of small JFR chunks/files or on a nearly inode-exhausted filesystem. Use **df -i** to catch this limit, while still checking quotas and concurrent consumption.

## 7. "df shows plenty of space" is still not enough

Free space reported by **df -h** is a **filesystem snapshot**, not a guarantee that allocation will succeed. There are at least six obstacles to consider:

- **User/group/project/volume quotas** can be smaller than filesystem free space. `df` does not automatically display every applicable quota limit.
- **Kubernetes ephemeral-storage limits / emptyDir sizeLimit** and node pressure can cause a Pod to be **evicted**, even while `df` inside the container looks spacious.
- **tmpfs** consumes RAM; a heap dump into **emptyDir medium: Memory** can trigger RAM pressure or a memory OOM.
- The container's **writable layer** can share storage with images, logs, and other containers; a large file affects the node/service.
- **Concurrent writers** can consume remaining space between preflight and final write; never treat initial measurements as immutable.
- **I/O errors, permissions, inode exhaustion, read-only remounts, or disconnected network volumes** can all leave an incomplete file.

**Quota** and **filesystem capacity** are two distinct concepts. For example, `df` might report 20 GiB free while the Pod only has 1 GiB of ephemeral-storage budget left—a 4 GiB dump can still get the workload evicted. Therefore, accurate planning requires checking **both the filesystem and limits defined by the container orchestrator/volume**.

### 7.1. Budgeting with safety reserve

Let:

- **F**: usable free space measured on the exact filesystem at preflight time.
- **D**: estimated dump file size; if unknown, use a conservative assumption and state it explicitly.
- **R**: reserved space for logs, application writes, background activity, and data growth during the dump.
- **T**: additional temporary space **on the same filesystem** (e.g., JFR repository, concurrent writes), if any.
- **Q**: remaining space allowed under actual quota/ephemeral/PVC limits, if constrained.

Initial check condition:

\[
F \ge D+R+T,\qquad Q \ge D+R+T
\]

If **Q** cannot be measured, you cannot conclude space is guaranteed from **df** alone. If T sits on a **different filesystem**, check that filesystem separately; never add files from one volume into another volume's free space.

Illustrative example in **MiB**:

| Parameter | Hypothetical value |
| --- | ---: |
| Free/usable at file destination | 3,072 MiB |
| Estimated heap dump file | 2,200 MiB |
| Reserve for system/logs | 768 MiB |
| Temporary files on same filesystem | 0 MiB |
| Total needed (estimate + reserve) | 2,968 MiB |
| Estimated headroom | 104 MiB |

By **filesystem indicators alone**, the math barely passes, yet **104 MiB** of headroom is thin; if the dump grows larger than estimated or quota is below 2,968 MiB, the operation risks failing. **There is no universal reserve threshold** suitable for every workload: base it on baseline write rates, active limits, and the service's risk tolerance.

Do not use **post-GC heap used** as a guaranteed predictor of HPROF size. Do not treat **last time's file size** as an upper bound for the next dump. Compression also provides no space guarantee.

### 7.2. Why "df -h /" easily misleads

On Linux containers, **/** may live on a writable overlay while **/diagnostics** is a separate PVC or bind mount. Then:

~~~bash
df -h /
df -h /diagnostics
~~~

can report **two different filesystems and two different available amounts**. If the JVM actually writes to **/diagnostics**, the figure that matters is the filesystem **hosting /diagnostics**, not the root filesystem. Likewise, if **/tmp** holds the JFR repository while the final file lands in **/diagnostics**, check **both**.

### 7.3. When files are deleted yet df does not rise

On Linux, an unlinked file **still held open by a process's file descriptor** continues consuming blocks until the descriptor closes. In this scenario, directory listings or **du** may miss those used blocks while **df** still counts them. When investigating, check deleted-yet-open files using appropriate tools and permissions; **never delete files or kill processes arbitrarily** just to reclaim space.

## 8. Java 21 example: checking space from the filesystem seen by the JVM

**java.nio.file.FileStore** provides **getUsableSpace()**, the usable bytes from the JVM's perspective for a filestore. The API explicitly states that the value **is only a hint near read time and does not guarantee a write will succeed**. This is a **preflight check**, not a substitute for orchestrator/quota checks or post-write verification.

**File DiagnosticSpacePreflight.java:**

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

public final class DiagnosticSpacePreflight {
    private static final long MIB = 1024L * 1024L;

    private static long mibToBytes(String value) {
        return Math.multiplyExact(Long.parseLong(value), MIB);
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 3) {
            System.out.println(
                    "Usage: java DiagnosticSpacePreflight <dir> <estimateMiB> <reserveMiB>");
            return;
        }

        Path dir = Path.of(args[0]).toAbsolutePath().normalize();
        long estimate = mibToBytes(args[1]);
        long reserve = mibToBytes(args[2]);
        if (estimate < 0 || reserve < 0) {
            throw new IllegalArgumentException(
                    "Estimate and reserve must be nonnegative");
        }

        if (!Files.isDirectory(dir)) {
            System.out.println("Directory exists: false");
            return;
        }

        FileStore store = Files.getFileStore(dir);
        long usable = store.getUsableSpace();
        long required = Math.addExact(estimate, reserve);

        System.out.println("Directory: " + dir);
        System.out.println("Directory exists: true");
        System.out.println("Directory writable (hint): "
                + Files.isWritable(dir));
        System.out.println("File store read-only: "
                + store.isReadOnly());
        System.out.println("Usable MiB (snapshot): " + usable / MIB);
        System.out.println("Required MiB: " + required / MIB);
        System.out.println("Filesystem budget check: "
                + (usable >= required));
    }
}
~~~

Compile with JDK 21:

~~~bash
javac --release 21 DiagnosticSpacePreflight.java
java DiagnosticSpacePreflight /diagnostics/heap 2200 768
~~~

**The output has a fixed part and an environment-dependent part.** If the directory does not exist, the program prints exactly:

~~~text
Directory exists: false
~~~

If the directory exists, the program prints seven lines with **Directory**, **Directory exists: true**, **Directory writable (hint)**, **File store read-only**, **Usable MiB (snapshot)**, **Required MiB: 2968**, and **Filesystem budget check** in that exact order. Path, writable, read-only, usable values, and the boolean result depend on the environment; **there is no fixed free-space stdout number**.

**Understand the limitations:**
- **Files.isWritable** can catch obvious permission errors, yet remains only a point-in-time check; permissions or mounts can change before writing.
- FileStore may be unaware of **ephemeral-storage limits** or other orchestrator-level quotas.
- Running the program in a different JVM/process may observe a different filesystem or UID; for strong evidence, run it inside **the same container/namespace and user as the application**, or integrate a controlled check inside the real app.
- The program **creates no files**, does not prove every expected file can be created, and does not attempt a heap dump.
- For large volumes, also factor in quotas, I/O latency, inodes, log growth, and safety reserve.

### 8.1. Java 21 example with deterministic stdout to understand the budget calculation

**File DumpBudgetExample.java:**

~~~java
public final class DumpBudgetExample {
    public static void main(String[] args) {
        long usableMiB = 3072;
        long estimatedDumpMiB = 2200;
        long reserveMiB = 768;

        long requiredMiB = estimatedDumpMiB + reserveMiB;
        long headroomMiB = usableMiB - requiredMiB;

        System.out.println("Required: " + requiredMiB + " MiB");
        System.out.println("Headroom: " + headroomMiB + " MiB");
        System.out.println("Pass filesystem budget: "
                + (headroomMiB >= 0));
    }
}
~~~

~~~bash
javac --release 21 DumpBudgetExample.java
java DumpBudgetExample
~~~

**Exact stdout:**

~~~text
Required: 2968 MiB
Headroom: 104 MiB
Pass filesystem budget: true
~~~

**true** here only means **true under the hypothetical inputs**, without accounting for quotas, extra writes, or changing free space. Never let this example autonomously approve taking a real dump on a live system.

## 9. Controlled preflight workflow for a JVM in Docker

Suppose the JVM for service **orders-java** runs in Linux Docker, with **/diagnostics** mounted and **jcmd** available. The example below outlines the workflow, not commands executed on a real system.

### Step 1 — Confirm the right container/JVM and identity

~~~bash
docker inspect --format '{{.State.Running}}' orders-java
docker inspect --format '{{json .Mounts}}' orders-java
docker exec orders-java id
docker exec orders-java ps -eo pid,ppid,comm
~~~

These commands may be unavailable in minimal images. **Do not assume Java is PID 1**; init wrappers, shells, and shared PID namespaces can change the JVM's PID. The subsequent commands assume **the JVM's PID inside the container was verified to be 1**. For another JVM PID, substitute the real number in that namespace.

When the right tools are present:

~~~bash
docker exec orders-java jcmd 1 VM.version
docker exec orders-java jcmd 1 help GC.heap_dump
docker exec orders-java jcmd 1 help JFR.dump
~~~

**jcmd** requires attach capability and proper permissions, typically matching effective user/group per JDK docs. Failures can stem from missing JDK tools in the image, restricted attach, or targeting the wrong process; picking the right PID is only a necessary condition.

### Step 2 — Inspect directories inside the container

~~~bash
docker exec orders-java sh -c 'id; ls -ld /diagnostics /diagnostics/heap /diagnostics/jfr'
docker exec orders-java sh -c 'df -h /diagnostics/heap; df -i /diagnostics/heap'
docker exec orders-java sh -c 'df -h /diagnostics/jfr; df -i /diagnostics/jfr'
docker exec orders-java sh -c 'df -h /tmp'
~~~

These commands use **sh, ls, df** inside the container and apply when the image contains them. If the image lacks them, use other ops-approved tooling to inspect mounts/quotas from the node or a debug container. **Never assume /tmp or /diagnostics values match the host**.

Evaluate **permissions against the JVM's UID/GID**, budget expected size alongside logs/JFR repository and eviction limits. **df -i** checks inodes, **df -h** checks blocks. Neither replaces checking other limits.

### Step 3 — Pick a unique path and write only when justified

Bounded JFR example:

~~~bash
docker exec orders-java jcmd 1 JFR.start name=incident-001 settings=default duration=60s filename=/diagnostics/jfr/orders-incident-001.jfr
~~~

For a heap dump, this is a separate **high-impact command**:

~~~bash
docker exec orders-java jcmd 1 GC.heap_dump /diagnostics/heap/orders-incident-001.hprof
~~~

**Execute a heap dump only with operational approval/accepted impact**, a verified space budget, and a heap-investigation rationale; never run it just to "test the path". If you only need to verify the VM, **VM.version** is far less intrusive.

### Step 4 — Verify the final file from the JVM side, then retrieve it

Once the dump command completes, verify from the exact container:

~~~bash
docker exec orders-java ls -lh /diagnostics/heap/orders-incident-001.hprof
docker exec orders-java df -h /diagnostics/heap
~~~

For a JFR capture with **duration=60s**, wait until the recording stops per status and collection schedule, then inspect the JFR file. **A matching filename alone does not prove validity**: check whether the command reported errors, whether the size makes sense, and whether a compatible analysis tool can open it.

If using Docker CLI with permission to retrieve the file and the storage path is verified:

~~~bash
docker cp orders-java:/diagnostics/jfr/orders-incident-001.jfr ./orders-incident-001.jfr
~~~

**docker cp** copies data from the container path to the Docker CLI caller's local path via Docker mechanics; the destination must have enough space and permissions. With named volumes/bind mounts, a dedicated retrieval path may be used; still verify mapping, permissions, and data integrity.

Do not delete the original until copying and data verification succeed and retention policies are met. If the file is a heap dump, restrict read permissions and avoid posting it to public channels.

## 10. Corresponding workflow in Kubernetes

In Kubernetes, **/diagnostics** may be an **emptyDir**, **PVC**, or platform-managed volume. Assume Pod **orders-0**, container **app** in the current kubeconfig's default namespace; add **-n <namespace>** when needed to avoid targeting the wrong object.

### Step 1 — Confirm Pod, container, volumes, and limits

Read the Pod configuration with appropriate tools:

~~~bash
kubectl get pod orders-0 -o wide
kubectl describe pod orders-0
kubectl exec orders-0 -c app -- id
kubectl exec orders-0 -c app -- df -h /diagnostics
kubectl exec orders-0 -c app -- df -i /diagnostics
~~~

**kubectl describe** helps identify volume mounts, states, and Pod events; also check **resources.limits.ephemeral-storage**, emptyDir **sizeLimit**, and node/volume quotas if applicable. **kubectl exec** starts a new process inside the container and does not automatically share Java's UID if custom settings apply.

In particular, **emptyDir medium: Memory** uses **tmpfs** and counts toward **container memory**. A large heap dump on tmpfs can exhaust the memory budget; a file written into a **memory-backed volume** is not safe just because `df` shows free blocks.

### Step 2 — Choose a location with a matching lifecycle

- If you need a short recording and will **retrieve it immediately**, a disk-backed emptyDir with a clear budget can work.
- If data must survive Pod replacement, choose a configured **PVC or supported collection infrastructure**.
- If you need a large heap dump, weigh **disk free**, **ephemeral-storage/PVC capacity**, **quotas**, **I/O throughput**, and **JVM impact limits**.
- If the Pod has multiple containers, verify the **volumeMount of the exact Java container**, even if a sidecar mounts the same volume at another path.

### Step 3 — Verify the file in the target container

~~~bash
kubectl exec orders-0 -c app -- ls -lh /diagnostics/jfr/orders-incident-001.jfr
kubectl exec orders-0 -c app -- df -h /diagnostics
~~~

To copy the file, **kubectl cp** can be used when the container has **tar** and conditions are met:

~~~bash
kubectl cp -c app orders-0:/diagnostics/jfr/orders-incident-001.jfr ./orders-incident-001.jfr
~~~

If the image lacks `tar` or **kubectl cp** fails, use another platform-supported export mechanism; do not treat a copy failure as proof the JVM failed to write the file. Especially for large heap dumps, check transfer timeouts, copy sessions, destination disk space, and integrity.

## 11. Common traps with paths, quotas, and permissions

| Symptom | Possibilities worth checking | Appropriate verification action |
| --- | --- | --- |
| **No such file or directory** | Parent directory missing in **JVM's filesystem**, host path used by mistake, wrong mount, broken symlink | Check mounts, **ls -ld** parent directory **inside container/JVM**; compare Docker/K8s volumeMount. |
| **Permission denied** | JVM UID/GID lacks permission, ACL/SELinux, mount policy | Check JVM effective user, owner/group/mode, ACL/securityContext; do not test only as root shell. |
| **Read-only file system** | Read-only rootfs or volume mount | Check readOnlyRootFilesystem, mount options; choose a provisioned writable path. |
| **No space left on device** | Out of blocks, inodes, temp filesystem, quota, or storage limit | **df -h**, **df -i** on **the right mount**; check quotas/ephemeral/PVC and JFR repository. |
| **df has plenty of space yet write fails** | Stricter quota, permissions, inodes, storage pressure, concurrent writers | Do not stop at `df`; check multiple limit layers and failure timestamp. |
| **jcmd succeeds yet no file appears on host** | File is in JVM mount namespace, relative path, JFR has not stopped yet, no bind/volume mapping | Check path from **container**, JFR.check, Docker/K8s mounts, and recording duration. |
| **JFR.start returned success yet no .jfr file** | File is written when recording stops/per config, auto-generated filename | Check **JFR.check**, **duration**, **filename**, events/errors; do not assume failure immediately. |
| **Dump file is tiny or cannot be opened** | Incomplete dump, disk full, I/O error, interrupted copy, incompatible format/compression | Check command status, size, verify with analysis tool, checksum after copy. |
| **Heap dump causes Pod eviction** | File exceeded ephemeral/emptyDir budget or disk pressure; tmpfs caused memory pressure | Check Pod events/limits, use adequately budgeted location and retrieve promptly. |
| **Same filename from multiple JVMs** | Overwrites/collisions, missing namespace/instance identifier | Use unique names by service, instance, timestamp; verify file does not already exist. |
| **Cannot create file after rename/mount** | Path points to different filesystem, mount/symlink changed, JVM permissions no longer match | Re-check mount and **df** at execution time; do not rely on stale preflight. |

### 11.1. Separating write errors from attach errors

If you receive **Could not attach to target VM**, inspect PID, effective user/group, same-host condition, namespace, attach mechanism, and JDK tools. This is usually **separate** from **GC.heap_dump**/**JFR.dump** filesystem errors occurring after the JVM accepts the command.

If attach succeeds yet opening the file reports **Permission denied**, look at **the JVM's filesystem/UID**, not just the shell account running jcmd.

If jcmd reports success yet retrieving the file fails, the issue may lie in the **export/copy step**, not necessarily the JVM write step. Separating stages prevents repeating an expensive heap dump just because a copy failed.

## 12. Post-write file verification and destination space budget

A verification sequence can include:

1. **Confirm the command completed successfully** and record stdout/stderr, start/end timestamps, JVM PID, and recording name if JFR.
2. **Inspect the file on the JVM's own filesystem**: full path, existence, size, owner/group, modified time. Check whether the system requires file writing to finish before retrieval.
3. **Check the filesystem after writing**: actual remaining space, volume errors, Pod/node storage-pressure events. Creating a large dump can affect other processes.
4. **Copy to the destination** via an appropriate mechanism; the destination also needs enough space. For network copies, watch timeouts and avoid filename collisions.
5. **Verify integrity**: compare before/after sizes or checksums, then open with a compatible JFR/HPROF reader. Do not finalize checksums while a file is still growing.
6. **Manage lifecycle**: tag with incident ID, JVM version, timestamp, access permissions; move to controlled storage or delete per policy once no longer needed.

Example (illustrative paths, read-only commands):

~~~bash
ls -lh /diagnostics/jfr/orders-incident-001.jfr
wc -c /diagnostics/jfr/orders-incident-001.jfr
sha256sum /diagnostics/jfr/orders-incident-001.jfr
df -h /diagnostics/jfr
~~~

Run these commands **where the actual file resides**. **sha256sum** may be absent in minimal images; two-sided checksums are only comparable once writing is confirmed finished with identical bytes. For JFR:

~~~bash
jfr summary /diagnostics/jfr/orders-incident-001.jfr
~~~

**jfr summary** requires the JDK tool and reads the file **where the command is invoked**. If you already copied the file to an analysis machine, use the path on **the analysis machine**, not the container path. You do not need analysis tools installed in production images.

### 12.1. Avoid retaining sensitive files uncontrolled

Heap dumps and recordings can expose business data or infrastructure paths/names. Enforce tight permissions, controlled storage, and policy-based deletion. Before sharing files with an analyst, verify access scope, retention period, encryption in transit/at rest, and incident tracking. Never send a heap dump to a public channel just to check whether it was created.

## 13. Quick decision workflow before pressing Enter

| Question | Expected evidence |
| --- | --- |
| Am I collecting **stdout text**, **JFR**, or a **heap dump**? | Clear diagnostic command name and output file type. |
| Is the file opened by **the jcmd shell** or **the target JVM**? | Shell **>** vs. **filename=/...** or command filename parameter. |
| Do I know the exact **JVM/PID**? | PID in tool's namespace, VM.version, container/Pod identity, and right target. |
| Is the path absolute in **the JVM's filesystem**? | Explicit path configuration, mount point from the right container/Pod, existing parent directory. |
| Does the **JVM UID/GID** have write permission? | Accurate owner/mode/ACL/mount; verified under the JVM's identity. |
| Is **df -h** measuring the right filesystem? | `df` on **the target directory**, not just `df /`. |
| Are there enough **inodes and quota/ephemeral limits**? | `df -i`, volume/Pod/namespace/node budgets, read-only and tmpfs accounted for. |
| Have I budgeted **dump + reserve + temporary files**? | F/D/R/T/Q budget and limits of each involved filesystem. |
| How will the file be **retrieved afterward**? | Bind mount/PVC/copy/export with sufficient destination space. |
| Will it disrupt the system? | Command impact, especially GC.heap_dump, evaluated beforehand. |
| After writing, who verifies **file validity**? | Path, size, checksum/reader, completion timestamp. |

## 14. Case exercises with solutions

**Case A — Confusing host path with container path.** Host has **/srv/diag/orders** and Docker bind-mounts it to **/diagnostics**. The operator runs **jcmd 12345 GC.heap_dump /srv/diag/orders/heap.hprof** from the host. Why can this fail?

**Solution:** **GC.heap_dump**'s argument is opened by the JVM; the JVM inside the container may **only know /diagnostics**, without **/srv/diag/orders**. Once mount and permissions are verified, the right path for the JVM is **/diagnostics/heap.hprof**. Afterward on the host, the file can be seen at **/srv/diag/orders/heap.hprof**. Never pass a host path as a JVM argument when it does not exist in the container's mount namespace.

**Case B — Root df shows 50 GiB free, yet dump runs out of space.** The JVM writes to **/diagnostics**, while **df -h /** reports 50 GiB free. What additional data should you inspect?

**Solution:** Check **df -h /diagnostics**, **df -i /diagnostics**, volume quotas, writable layer, Kubernetes **ephemeral-storage/sizeLimit** if applicable, concurrent writers, and JFR repository if used. **/** and **/diagnostics** may be two separate filesystems.

**Case C — JFR.start succeeds, yet no file appears immediately.** The operator used **duration=60s filename=/diagnostics/a.jfr** and checked 2 seconds later.

**Solution:** JFR.start configures the recording; with a duration, the file is typically written when the recording ends. Inspect **JFR.check** and check after the expected duration. If you need a snapshot from an active recording, use **JFR.dump** with the recording name and a distinct filename, remembering that the recording keeps running.

**Case D — Java runs as UID 10001, debug shell is root.** Root running **test -w /diagnostics/heap** returns true; the JVM still fails with **Permission denied**.

**Solution:** A root shell's permissions do not prove the JVM can write. Inspect directory/mount permissions under the **JVM's effective UID/GID and groups**, ACL/SELinux/securityContext; select a volume or permissions compliant with operational procedures.

**Case E — Memory-backed emptyDir shows "space", yet the JVM hits OOM.** The heap dump was written to **emptyDir medium: Memory**.

**Solution:** Memory-backed emptyDir is **tmpfs**, consuming RAM and counting toward memory budgets; `df` free blocks do not prove sufficient RAM. Choose a disk-backed volume with adequate capacity and policy for large files.

**Case F — jcmd Thread.print creates a file on the host, while JFR.dump leaves no file on the host.** The same user ran both from the Linux host.

**Solution:** **Thread.print > file** uses shell redirection processed **on the host side**. **JFR.dump filename=file** instructs the JVM to write **on the target side**, so the file may reside in the container/volume relative to the target's working directory or absolute target path.

**Case G — Copied file cannot be opened.** The JVM command created a file, and copying started before the recording actually finished.

**Solution:** Confirm completion state and stable file size, re-copy from the finished file, verify checksum/size, and open with a format-compatible reader. Do not immediately trigger a new heap dump when only the copy failed.

## 15. Mistakes to avoid

1. **"Whichever directory I run jcmd from is where the heap dump goes."** False for files created by the target JVM.
2. **"An absolute path on the host is also absolute inside the container."** False unless mounted identically.
3. **"JFR.start returning success means the .jfr file is already written."** Depends on duration and stop/write behavior.
4. **"df -h / reports 100 GiB, so /diagnostics has 100 GiB too."** They can be different filesystems.
5. **"If root in a debug container can write, the JVM user can write."** UID/GID and mount permissions differ.
6. **"Checking df before the command is all you need."** Also consider quotas, inodes, read-only mounts, tmpfs, storage pressure, and concurrent growth.
7. **"A heap dump is guaranteed to be smaller than -Xmx."** No universal guarantee exists across contents/formats; verify estimates carefully.
8. **"Enabling -gz=1 guarantees enough space."** Compression ratios vary and compression adds CPU cost.
9. **"Seeing a file means you have a valid dump."** It could be incomplete/truncated or copied mid-write.
10. **"Kubernetes emptyDir persists across all Pod restarts/replacements."** EmptyDir is tied to Pod lifecycle, not durable storage.
11. **"/tmp is always on disk."** It may be tmpfs or a small writable layer; verify first.
12. **"Not finding the file with kubectl cp means the JVM did not write it."** The container may lack `tar`, or you checked the wrong container/mount or hit a copy error.
13. **"Anyone can read sensitive files stored in a diagnostic volume."** Restrict access permissions and manage lifecycle.
14. **"Dump failed, so just re-run it."** If the cause was out-of-space or permission denied, repeating a heap dump only increases risk and load.

## Technical references

- [JDK 21 — jcmd: JFR.start, JFR.dump, GC.heap_dump, impact and filename](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [JDK 21 — java launcher: HeapDumpOnOutOfMemoryError and HeapDumpPath](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Java SE 21 — FileStore.getUsableSpace(): available metrics are only hints](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileStore.html#getUsableSpace())
- [GNU Coreutils — df: filesystem containing a path and inodes](https://www.gnu.org/software/coreutils/manual/html_node/df-invocation.html)
- [Docker — Bind mounts and host/container path relationship](https://docs.docker.com/engine/storage/bind-mounts/)
- [Docker — docker cp](https://docs.docker.com/reference/cli/docker/container/cp/)
- [Kubernetes — Local ephemeral storage, emptyDir, and limits/eviction](https://kubernetes.io/docs/concepts/storage/ephemeral-storage/)
- [Kubernetes — Sharing volumes with emptyDir](https://kubernetes.io/docs/concepts/storage/volumes/#emptydir)
- [Kubernetes — kubectl cp and tar requirement](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_cp/)

**Prerequisites before starting collection:** confirmed **target JVM**, **command type**, **path actually writable by the JVM**, **JVM permissions**, **filesystem + quota + inode + reserve space**, plus **how the file will be verified and retrieved**. After the command, the file must be verified from the JVM side before treating it as usable diagnostic evidence.