# 3.6 Distinguishing Container PIDs from Host PIDs

When investigating a Java process inside a container, the same JVM may be recorded as **PID 1** inside the container yet **PID 48210** on the Linux host. These are not two processes: they can be **two identifiers for the exact same process** under two **PID namespaces**. Entering a PID in the wrong scope can cause **ps**, **jcmd**, **kill**, **/proc** operations, and log/trace correlation to target the wrong process or report that no JVM was found.

This lesson explains the **Linux** PID namespace mechanism, how to map container PIDs to host PIDs, cases where Java cannot be assumed to be PID 1, and how to pick the right PID when diagnosing Java 21 JVMs with Docker/Kubernetes. Commands and example outputs use illustrative numbers; real PIDs must be verified at operation time.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why a single process can have **multiple valid PIDs** when viewed from different PID namespaces.
- Distinguish **JVM PID**, **container PID 1**, **PID returned by the Docker daemon**, **Linux host PID**, and **container ID**.
- Read **NStgid** alongside **NSpid** in **/proc/<pid>/status** and understand the display order from outer to inner namespaces.
- Correlate a Java process inside a container with the corresponding process on the Linux host without guessing by adding/subtracting a PID offset.
- Choose the right PID for **jcmd, ps, JFR, thread dumps** according to where the diagnostic tool runs.
- Recognize exceptions such as **--pid=host**, shared-namespace containers, Kubernetes **shareProcessNamespace**, **hostPID**, minimal images, and Docker Desktop.
- Reduce the risk of targeting the wrong process after container restarts or PID reuse.

## 2. PIDs Are Scoped Numbers: PID Namespace Defines “Viewed From Where”

On Linux, **process IDs (PIDs)** are managed by the kernel and have meaning within a **PID namespace**. When a container uses its own PID namespace, processes inside usually only see processes in that namespace and visible child namespaces; they do not by default see all processes on the Linux host. Conversely, an ancestor namespace can see processes in child namespaces, yet each views the process using a PID belonging to its own namespace.

Example in a typical Linux Docker setup:

~~~text
A Java process X in the Linux kernel
    |
    +-- Linux host PID namespace : PID 48210
    |
    +-- Container PID namespace  : PID 1

Both 48210 and 1 can refer to process X.
~~~

**Decisive point:** a PID is a value tied to a **perspective (namespace)**, not a globally unique, permanent identifier for a process. Different processes in different PID namespaces can all be **PID 1** without conflict.

Several key rules:

1. A process belongs to a PID namespace when created. Namespaces can be nested into a hierarchy.
2. A process in a child namespace has a corresponding PID in that namespace and in every ancestor namespace that can see it. These PIDs **have no simple arithmetic conversion rule**.
3. **getpid()**, corresponding to **ProcessHandle.current().pid()** in Java, returns the process number from the perspective of the runtime where the JVM executes. Never treat that number as a global PID usable everywhere.
4. A child PID namespace normally cannot inspect/control processes existing only in an ancestor namespace using host PIDs. Visibility also depends on which namespace **/proc** was mounted from.
5. PID namespaces and **cgroups** solve two different problems: namespaces govern **PIDs and process visibility**; cgroups handle process grouping and resource limits/accounting. Sharing the same cgroup or container ID does not make two PIDs equal.

**“Host” must be defined clearly:** in Docker Engine running directly on Linux, the host is usually the Linux kernel where the Docker daemon runs. In **Docker Desktop on Windows/macOS**, Linux containers run inside a **Linux VM**: PIDs seen by the Docker Engine belong to the VM environment, **not Windows/macOS process IDs**. In Kubernetes, “host PID” usually means the PID in the namespace of the **Linux node** running the Pod, not the workstation running kubectl.

## 3. Do Not Equate PID 1, Java PID, and Host PID

A container can run one or many processes. **PID 1** is the init process inside a dedicated PID namespace when the container actually has one; PID 1 does not mean “this is definitely Java”.

### 3.1. Three Common Startup Structures

**Case A: Java is executed directly**

~~~text
Linux host                          Inside container
PID 48210  java -jar app.jar   <=>   PID 1  java -jar app.jar
~~~

If the entrypoint starts **java** directly or a shell uses **exec java ...**, Java can indeed be PID 1. In that case, the Docker container's **State.Pid** can point to the actual Java process from the Linux host perspective.

**Case B: shell/wrapper without exec**

~~~text
Linux host                          Inside container
PID 48210  /bin/sh start.sh    <=>   PID 1  /bin/sh start.sh
PID 48253  java -jar app.jar   <=>   PID 7  java -jar app.jar
~~~

Docker usually knows the PID of the **container's initial process**, e.g. **48210**. Yet the JVM to diagnose is process **48253** (PID 7 inside). Passing Docker inspect's initial-process PID to **jcmd** would target the shell, not the JVM.

**Case C: minimal init or process supervisor**

~~~text
Linux host                          Inside container
PID 48210  tini                 <=>   PID 1  tini
PID 48253  java -jar app.jar    <=>   PID 7  java -jar app.jar
~~~

Using **docker run --init**, a supervisor, or an init wrapper helps forward signals and reap zombie children. Then Java is usually a **child process**, so **PID 1** is still not the PID to pass to JVM diagnostics.

**Practical consequence:** before running **jcmd 1**, verify that PID 1 in the current namespace **is actually the JVM**. Do not infer it from container name, Java image, or service name alone.

### 3.2. PID, PPID, TID, Container ID, and Pod UID Differ

| Term | What it is | What it is used for |
| --- | --- | --- |
| **PID** | ID of a process within a specific PID namespace | Specifying a process for ps, jcmd, signals, /proc from the caller's view. |
| **PPID** | PID of the parent process as seen from the relevant namespace | Understanding the process tree; a parent in an outer namespace may not appear as expected. |
| **TID / LWP ID** | Kernel-level thread ID | Investigating individual native threads; do not mix with process PID or Java thread ID. |
| **Container ID** | ID managed by the container runtime | Selecting a container for docker exec/inspect; **not a PID**. |
| **Pod UID / container runtime ID** | Orchestration/runtime identity | Pinpointing the exact workload/instance, useful when multiple containers share a logical name. |
| **PID namespace inode** | Identity of a PID namespace object in the same kernel | Comparing whether two processes share the same PID namespace. |

In Java, **Thread.currentThread().threadId()** is the **Java thread ID**, not the Linux PID of the JVM and not guaranteed to be the native TID; never pass it as a **jcmd** argument. On Linux, **Tgid** is the **thread-group ID**, i.e., the process ID of the thread group; **Pid** in a task's status file is the **thread ID**. For the thread-group leader, both values usually match.

## 4. Kernel Data for Cross-Checking: /proc/<pid>/status

On a Linux host, if you have permission to read **/proc/<host-pid>/status**, you may see lines like:

~~~text
Name:   java
Tgid:   48210
Pid:    48210
PPid:   47990
NStgid: 48210   1
NSpid:  48210   1
~~~

*This is illustrative data for the case where the JVM itself is PID 1 in the container, read from procfs mounted in the host namespace.*

**How to read NStgid:**

- **NStgid** lists the **thread-group ID / process PID** across the PID namespaces the process belongs to.
- **The leftmost value** is the PID in the namespace of the process **that mounted the procfs** being read (typically the host namespace when using standard **/proc** on a Linux host).
- Values further right are PIDs in progressively deeper child namespaces.
- In the example above, **48210** is the PID per host procfs, and **1** is the PID in the container's namespace.
- With deeply nested namespaces, you may see three or more numbers, e.g. **NStgid: 48253 301 7**. Do not assume there are always exactly two columns.

**NSpid** follows the same order but describes the **thread ID** in each PID namespace. When reading **/proc/<pid>/status** of the **thread-group leader**, NSpid usually equals NStgid. When reading **/proc/<pid>/task/<tid>/status** of another thread, NSpid shows the **TID** and can differ from NStgid. When looking for **the JVM's PID as a process**, prefer **NStgid**; never use a Java worker thread's TID as the process PID.

**Exact note on /proc:** the kernel exposes namespace fields on supported Linux kernels (introduced in Linux 4.1). Leftmost values depend on **which namespace mounted procfs**. Inside a container whose procfs is mounted in its own namespace, the same process might show only:

~~~text
Name:   java
NStgid: 1
NSpid:  1
~~~

That **does not mean** the host PID is also 1; the container's procfs simply shows a narrower view. **Do not rely on /proc/self/status inside a container expecting to obtain the host PID**. If fields are absent or permission-restricted, use the container runtime/node mechanism rather than guessing the PID.

### 4.1. Checking the Namespace Inode

Linux also provides a symlink representing the namespace, for example:

~~~bash
readlink /proc/48210/ns/pid
~~~

*Illustrative* output:

~~~text
pid:[4026532465]
~~~

If two processes are on **the same Linux kernel** and their **/proc/<pid>/ns/pid** paths resolve to the same namespace inode, they share the same PID namespace. However, an inode does not replace **PID mapping**: two processes in the same namespace still have different PIDs. Comparing inodes across **different machines/VMs** is meaningless. Never deduce an internal PID from the inode number.

**PID namespace inode** is also useful to see that **host PID 1** and **container PID 1** belong to two distinct namespaces even though both equal 1. You need both namespace and context to identify the process accurately.

## 5. Docker Engine Practice on Linux: Cross-Checking a Running Container

This section assumes you have **Docker CLI access to the daemon managing the container on a Linux host** and required permissions. Assume the container is named **my-java-app**; replace with the real ID/name. These commands only inspect information and do not stop processes.

### Step 1 — Look at Processes Inside the Container

When the image has **sh**, **ps**, and **cat**:

~~~bash
docker exec my-java-app sh -c 'ps -eo pid,ppid,comm'
docker exec my-java-app sh -c 'cat /proc/1/status | grep -E "^(Name|Tgid|Pid|PPid|NStgid|NSpid):"'
~~~

Check **Java's PID** and **PID of process 1** to see whether they match. **docker exec** spawns temporary processes while running the command, so the process list may include the new shell/ps. If the container is **distroless** without shell/ps, do not conclude no PID exists; switch to Docker daemon/runtime info or organization-approved debugging tools.

**If Java is PID 7:** use **7** when operating inside that same PID namespace/container, regardless of what PID Docker inspect reports for process 1. Verify process name and command line rather than relying on the number alone.

### Step 2 — Get the Container Initial Process PID from the Docker Daemon

Run where Docker CLI and the appropriate daemon are accessible:

~~~bash
docker inspect --format '{{.State.Pid}}' my-java-app
docker inspect --format '{{.HostConfig.PidMode}}' my-java-app
~~~

Suppose the first command outputs **48210**. In **Docker Engine directly on Linux**, **State.Pid** is typically the PID of **the container's initial process** from the Linux host/daemon perspective. It is **not** the container ID and **not necessarily** Java's PID when Java was spawned by a shell, tini, or supervisor. A value of **0** or no available PID can appear when the container is no longer running; check container status.

**HostConfig.PidMode** helps detect whether the container uses a special PID sharing mode such as **host** or **container:<id>**. This field does not replace identifying the live JVM process itself.

### Step 3 — Read the PID Map on the Right Linux Host

On **the same Linux host/kernel as the Docker daemon**:

~~~bash
HOST_PID=$(docker inspect --format '{{.State.Pid}}' my-java-app)
printf 'Docker init host PID: %s\n' "$HOST_PID"
grep -E '^(Name|Tgid|Pid|PPid|NStgid|NSpid):' /proc/"$HOST_PID"/status
readlink /proc/"$HOST_PID"/ns/pid
~~~

**Prerequisites:** running in a Linux shell on the right host, with procfs and sufficient permissions. Never copy **/proc/$HOST_PID** commands to Windows PowerShell/macOS expecting to read the same kernel: with Docker Desktop, the daemon/Linux containers live inside a VM. When Docker CLI connects to a remote daemon, that PID also belongs to **the daemon host**, not the machine where you type commands.

**Hypothetical example** if the initial process is Java:

~~~text
Docker init host PID: 48210
Name:   java
Tgid:   48210
Pid:    48210
NStgid: 48210   1
NSpid:  48210   1
pid:[4026532465]
~~~

The line **NStgid: 48210 1** is strong evidence for the PID pair if procfs is mounted in the host namespace. Numbers are illustrative, not fixed output.

### Step 4 — If Java Is Not PID 1, Locate the JVM Itself on the Host

Suppose:

~~~text
Docker init: host PID 48210 / container PID 1 / program tini
Java:        host PID 48253 / container PID 7 / program java
~~~

Here **docker inspect State.Pid = 48210** identifies only **tini**. You must locate **the JVM's host PID 48253**, for instance via process listings visible to Docker/runtime or the Linux host, then confirm:

~~~bash
grep -E '^(Name|Tgid|Pid|PPid|NStgid|NSpid):' /proc/48253/status
readlink /proc/48253/ns/pid
~~~

Illustrative output:

~~~text
Name:   java
Tgid:   48253
Pid:    48253
PPid:   48210
NStgid: 48253   7
NSpid:  48253   7
pid:[4026532465]
~~~

Thus **48253** is the JVM's host PID, and **7** is its container PID. Do not calculate **48253 - 48210 = 43** and treat 43 as an “offset” for other processes: each namespace assigns PIDs independently and can reuse numbers.

When multiple JVMs share a container or processes restart, also verify command line, start time, container ID, and namespace. **Yesterday's PID pair may have been reclaimed and reused today.**

### Step 5 — Choose Commands Based on Where the Tool Runs

| Execution location | PID used to target the JVM | Typical operations |
| --- | --- | --- |
| **Inside the container / JVM PID namespace** | Java's **container PID**, e.g. **7** | **jcmd 7 VM.version**, **ps -p 7**, **/proc/7/status** if tools and permissions allow. |
| **On the Linux host running the Docker daemon** | The JVM's **host PID**, e.g. **48253** | **ps -p 48253**, **/proc/48253/status**, try **jcmd 48253 ...** when attach is supported. |
| **Docker CLI from a laptop connected to a remote Linux daemon** | PID on the daemon/remote host, **not laptop PID** | **docker inspect/exec** targets the daemon; /proc checks must run on the exact Linux host. |
| **Docker Desktop Windows/macOS (Linux containers)** | PID inside container or inside Linux VM from daemon view | Use **docker exec**/supported diagnostics; **tasklist/Activity Monitor** will not directly show Linux PIDs. |
| **Kubernetes container with isolated PID namespace** | PID in the container namespace when exec'd in | **kubectl exec** into the right container, verify JVM PID before running jcmd; host PID belongs to the Linux node. |

Do not convert PIDs by adding/subtracting a number, and do not pick **PID 1** just because it is a Java container.

## 6. Runnable Java 21 Example: Viewing the PID Seen by the JVM Itself

Java provides **ProcessHandle.current().pid()**. It is very useful for logging **the PID in the JVM's execution environment**, yet no Java SE API turns that number into a “Linux host PID” across all platforms.

The program below also reads **/proc/self/status** on Linux. It still compiles on Java 21 on other platforms; when **/proc** is absent, that part is skipped with a clear message.

**File PidNamespaceView.java**

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class PidNamespaceView {
    private static String field(List<String> lines, String name) {
        String prefix = name + ":";
        return lines.stream()
                .filter(line -> line.startsWith(prefix))
                .findFirst()
                .map(line -> line.substring(prefix.length()).trim())
                .orElse("(not available)");
    }

    public static void main(String[] args) throws IOException {
        ProcessHandle self = ProcessHandle.current();

        System.out.println("Java PID: " + self.pid());
        System.out.println("Java parent PID: "
                + self.parent()
                        .map(parent -> Long.toString(parent.pid()))
                        .orElse("(not visible)"));

        Path status = Path.of("/proc/self/status");
        if (!Files.isReadable(status)) {
            System.out.println("/proc/self/status: unavailable");
            return;
        }

        List<String> lines = Files.readAllLines(status);
        for (String name : List.of(
                "Name", "Tgid", "Pid", "PPid", "NStgid", "NSpid")) {
            System.out.println(name + ": " + field(lines, name));
        }
    }
}
~~~

Compile and run with JDK 21:

~~~bash
javac --release 21 PidNamespaceView.java
java PidNamespaceView
~~~

**Interpreting stdout:** lines **Java PID**, **Java parent PID**, **Name**, **Tgid**, **Pid**, **PPid**, **NStgid**, **NSpid** print in order when **/proc** is readable, while exact numbers **vary per run**. Do not assume a single “standard” set of PIDs. If **/proc** is unreadable, the program prints the two Java PID lines and **/proc/self/status: unavailable**.

Illustrative visualization **when Java is actually process 1** in a Linux container whose procfs is mounted in the container namespace:

~~~text
Java PID: 1
Java parent PID: (not visible)
Name: java
Tgid: 1
Pid: 1
PPid: 0
NStgid: 1
NSpid: 1
~~~

These lines are **only one illustrative possibility**, not guaranteed for all containers. **Name**, parent visibility, procfs mount, and JVM launcher can vary. If Java is **PID 7**, the program typically sees **Java PID: 7** in its namespace; when reading **host procfs** outside, an operator may see NStgid like **48253 7**.

**Important limitation:** the Java program reads **whatever procfs is mounted at that path**. If /proc is not mounted for the current namespace, NStgid can reflect a different view than **ProcessHandle.current().pid()**. Do not interpret that mismatch as a `ProcessHandle` bug; inspect procfs/namespace configuration.

### 6.1. Java 21 Example with Fixed Stdout: Parsing a Sample NStgid

This snippet illustrates parsing **a known sample input**, without querying a real process.

**File PidMappingExample.java**

~~~java
public final class PidMappingExample {
    public static void main(String[] args) {
        String status = """
                Name:\tjava
                NStgid:\t48253\t7
                NSpid:\t48253\t7
                """;

        String line = status.lines()
                .filter(s -> s.startsWith("NStgid:"))
                .findFirst()
                .orElseThrow();

        String[] ids = line.substring("NStgid:".length())
                .trim()
                .split("\\s+");

        System.out.println("PID at procfs mount: " + ids[0]);
        System.out.println("PID at innermost namespace: "
                + ids[ids.length - 1]);
    }
}
~~~

~~~bash
javac --release 21 PidMappingExample.java
java PidMappingExample
~~~

**Exact stdout:**

~~~text
PID at procfs mount: 48253
PID at innermost namespace: 7
~~~

If the sample field had three numbers **48253 301 7**, the **ids** array would have three elements; the first still reflects the procfs mount, and the last reflects the innermost namespace. In real systems, verify field name, process status, and procfs perspective before treating them as host/container PIDs.

## 7. When Using Java Diagnostic Tools: Wrong-Scope PID Means Wrong JVM

With JDK 21, **jcmd** takes the Java process PID as an argument. Its documentation notes that **jcmd -l** does not necessarily list JVMs running in separate Docker processes; use appropriate process management tools to find the PID. Attaching requires running on the same machine as the JVM and meeting permission, runtime/VM, filesystem, and namespace requirements; **knowing the right PID does not guarantee attach will succeed**.

### 7.1. Running jcmd Inside a Container

When the container has JDK tools and Java is confirmed as PID 7:

~~~bash
docker exec my-java-app jcmd 7 VM.version
docker exec my-java-app jcmd 7 help
~~~

Or, if already in a shell **inside the right PID namespace**, run:

~~~bash
jcmd 7 VM.version
jcmd 7 Thread.print
~~~

**Thread.print** should only be used when a thread snapshot is needed with awareness of overhead. **VM.version** is a minimally intrusive verification step. If Java is PID 1, replace **7** with **1**, but only **after verifying** via process list or Java PID logs.

Commands can fail because a JRE/jlink/distroless image lacks **jcmd**, lacks permissions for effective UID/GID, attach is restricted, wrong container, or socket paths/files are blocked. **Do not fix errors by automatically elevating container privileges** without knowing the cause.

### 7.2. Running jcmd from the Linux Host

If the JVM's **host PID 48253** is confirmed and host tools/kernel can attach properly:

~~~bash
jcmd 48253 VM.version
~~~

The command **can still fail** even with the right PID. When a JVM runs in a container, HotSpot's attach mechanism involves permissions, PID namespaces, temp paths, and mount namespaces; security policies or mismatched toolsets can interfere. **`jcmd -l` not showing** a Docker JVM also **does not prove** the JVM is absent. Prefer running tools in the JVM's appropriate environment or a verified debug workflow.

**Pick PID for /proc based on procfs view**: read **/proc/48253/status** on the host to inspect that JVM, yet read **/proc/7/status** inside a normal container namespace. **Never pass 48253 into a container's /proc path** just because you saw that number on the host.

### 7.3. Connecting to Other Diagnostic Signals

- **Java application logs:** log **ProcessHandle.current().pid()** alongside container ID/Pod UID, instance ID, start timestamp, and VM version so operators can identify the log source. PID alone is not a sufficient global key.
- **GC/JFR logs:** files are written to the filesystem as seen by the JVM process; when inspecting from the host or another container, account for mount namespaces and where files actually land.
- **Thread dumps:** native thread IDs in a dump are not process PIDs; Java virtual-thread IDs are not Linux PIDs either. Distinguish threads from processes so you do not pass the wrong ID to signals/attach.
- **Metrics:** a label **pid=7** from inside a container does not automatically match **pid=48253** from a host node exporter. Use correlation keys containing container/runtime identity and verified namespace/mapping pairs.
- **JMX and internal management APIs:** can expose metrics via endpoints without manual PID translation, though endpoint access, networking, cost, and security must still be controlled.

## 8. Exceptions Where “Container Has Its Own PID and Java Is PID 1” Fails

### 8.1. Docker --pid=host

The Docker option:

~~~bash
docker run --pid=host ...
~~~

tells the container to **share the Linux host's PID namespace** instead of using its own isolated PID namespace. Processes inside then see PIDs from the host namespace; **PID 1** is usually the host's init and **not** the container's main process. However, the container still keeps other isolation mechanisms (mount, user, network, cgroup...) depending on configuration; sharing PIDs does not remove all isolation.

Do not enable **--pid=host** just to work around PID visibility issues: sharing the namespace expands visible processes and the security surface. Some user namespace configurations also restrict using this option.

### 8.2. Docker --pid=container:<name-or-id>

Two containers can share a single PID namespace:

~~~bash
docker run --pid=container:my-java-app ...
~~~

The first process of the second container **is not necessarily PID 1**, because the namespace already has an init process. Tools in the second container can see processes of the target container if procfs, permissions, and configuration allow. Use container ID/namespace to pinpoint the right process; never assume every container has its own PID 1.

### 8.3. Kubernetes shareProcessNamespace and hostPID

Normally, containers in a Pod **do not necessarily** see each other's processes. When a Pod is configured with:

~~~yaml
spec:
  shareProcessNamespace: true
~~~

containers in the Pod share one PID namespace. The application's main process may have a **PID other than 1**, while **PID 1** may be the Pod sandbox process. Sidecars/debug containers can see other processes in the Pod subject to permissions. This affects stack collection, signal delivery, and entrypoint design.

With **hostPID: true**, the Pod uses the node's PID namespace; processes inside containers see PIDs in that host namespace. Kubernetes API does not allow setting both **hostPID** and **shareProcessNamespace** on the same Pod. These options require explicit deployment and security decisions.

Example reading Java's PID from a specific container:

~~~bash
kubectl exec pod-name -c app-container -- ps -eo pid,ppid,comm
~~~

If the image lacks **ps**, use an ephemeral debug container or node-level tools per operational policy. **kubectl** running on a laptop does not make the laptop's **/proc** equal to the node's /proc; to get real host PIDs, inspect from **the node/runtime** hosting the Pod.

### 8.4. Docker Desktop, VMs, and Remote Daemons

On Docker Desktop for Linux containers:

~~~text
Windows/macOS desktop
     |
     +-- Linux VM (Docker Engine, Linux host PIDs)
             |
             +-- container PID namespace (container PIDs)
~~~

In this diagram, **Docker inspect State.Pid** reflects the process from the Docker Engine/Linux VM view; it is not a number you can pass to Windows **taskkill** or macOS **kill** to directly target the Linux JVM. When Docker CLI uses a context pointing to a remote daemon, “host” means **the daemon machine**, not the user's terminal.

**The same phrase "host PID" can refer to three different environments**: physical Linux node, Docker VM, or remote daemon host. Diagnostic reports must explicitly state the underlying environment.

### 8.5. Procfs, Nested Namespaces, Rootless, and Permissions

A customized container may not mount procfs as you expect; thus **ps**, **/proc/self**, or **NStgid** may yield unexpected views. Nested namespaces, containers inside containers, rootless runtimes, and security policies can alter tools and readability.

PID namespaces **do not automatically grant permission** to read every /proc entry or attach to every JVM. User namespace/UID mapping, /proc access permissions, system policies, and JVM tools still govern what is permitted. **Never request --privileged, --pid=host, or disabling protections as a default step** for measurement.

## 9. Why PID 1 Matters Specially for Java Operations

PID 1 inside a PID namespace serves as init: managing lifecycle and reaping orphaned child processes. Linux applies special signal-handling rules to PID 1; a Java application running as PID 1 may not receive/handle signals the way you expect unless proper handlers and signal forwarding are configured.

Example entrypoint design:

~~~dockerfile
# Illustrative snippet, not a complete Dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

In this exec-form (with a separate PID namespace), Java **can** be PID 1. With shell-form or a wrapper script that does not **exec** Java, the shell can be PID 1 with Java as a child. When Docker uses **--init** or a supervisor, init sits at PID 1 to receive signals, forward them, and reap zombies.

Stopping/restarting containers should follow Docker/Kubernetes mechanisms with proper timeouts and graceful shutdown. Avoid running **kill -9** or **kill 1** on a guessed PID: **PID 1** in that namespace might not be the intended JVM, and PIDs can be reused.

## 10. Troubleshooting Recipe: Picking the Right PID Before Debugging

**Scenario:** an alert reports high CPU in the JVM inside container **orders-api**. An operator runs **jcmd 1 Thread.print** inside the container and gets **not a Java process**. On the host, **ps** shows a Java process with PID 56432.

**Analysis:**

1. **Identify the exact instance:** capture container ID/Pod UID, node/daemon, container status, and start time. Avoid confusing it with another replica sharing the same logical name.
2. **Confirm the PID where the tool will run:** inside the container you may see **tini PID 1** and **java PID 7**. On the host sharing the kernel, Java may be **PID 56432**.
3. **Correlate the same process:** inspect host **/proc/56432/status**; illustrative **NStgid** may be **56432 7**. Verify namespace inode and command line if needed. Do not substitute Docker's **State.Pid** for the Java PID when an init/wrapper is present.
4. **Run diagnostics in the right scope:** inside the container run **jcmd 7 VM.version** first; on the host, if attach is supported and permissions match, run **jcmd 56432 VM.version**. Only after verification request thread dumps/JFR.
5. **Keep identity-bound evidence:** record container ID, node, timestamp, host/container PID pair, JVM version, and command outputs. If the container restarts, **re-resolve the mapping** instead of reusing the old PID pair.

**Evidence-based conclusion:** the initial error occurred because **PID 1 was init**, not Java; observation must target the right PID. However, if attach still fails with the right PID, continue checking permissions, filesystem, runtime, and tools. Do not blame mapping for every attach failure.

### 10.1. Checklist Before Running jcmd/ps/kill on a Java Container

| Question | Verification |
| --- | --- |
| Where am I operating from? | Container, Linux node, Docker VM, or laptop connected to remote daemon? |
| Is the PID namespace shared or isolated? | Docker PidMode, Kubernetes hostPID/shareProcessNamespace, namespace inode. |
| Is the Java process PID 1? | Process list, command line, ProcessHandle logs, procfs. |
| Is the PID pair verified on the same process? | NStgid from proper procfs, command/start time/container identity. |
| Which PID must be used where the tool runs? | PID matching the tool's namespace/procfs (or corresponding runtime API). |
| Are tools present and permissions sufficient? | JDK/JRE image, effective UID/GID, attach policy, procfs/socket, security controls. |
| Is the PID still valid at action time? | Verify process is alive and container has not restarted, avoiding PID reuse. |
| Can read-only commands go first? | VM.version, ps, /proc/status; run impactful actions only when necessary. |

## 11. Common Thinking Mistakes

1. **“Java in a container is always PID 1.”** False whenever a shell, tini, supervisor, or shared PID namespace is used.
2. **“docker inspect State.Pid is the JVM's PID.”** It is the container's initial process PID per the daemon; the JVM may be a child.
3. **“Container PID differs from host PID by a fixed offset.”** PID namespaces assign PIDs independently; there is no universal add/subtract formula.
4. **“NSpid is always the process PID everywhere.”** NSpid describes thread IDs; use NStgid for process/thread-group IDs, and check which task you are reading.
5. **“NStgid inside a container always includes the host PID.”** Depends on procfs mount; a container's own mount usually shows only numbers in its view.
6. **“JVM missing from jcmd -l means the JVM stopped.”** Docker, process scope, permissions, image, and attach restrictions can hide it from listing.
7. **“docker inspect run from Windows gives a Windows PID.”** Docker Desktop Linux containers run inside a Linux VM; the PID belongs to the Linux daemon environment.
8. **“Being root in a container lets you attach to any JVM.”** Namespaces differ in user mapping, procfs/mount restrictions, effective UID/GID, and JVM tooling.
9. **“A Kubernetes Pod always has Java as PID 1.”** With shareProcessNamespace, Pod init and JVM can be two separate processes.
10. **“A PID recorded last week is still valid after deploy.”** PIDs are reused; always pair with timestamp, container identity, and process start time.
11. **“Same PID number 7 means the same process.”** Two namespaces or two hosts can each have a PID 7.
12. **“Use host PID with jcmd inside the container to be safe.”** PIDs must match the tool's perspective and attach mechanism; the host PID may not even exist in the container's /proc.

## 12. Self-Check

**Q1.** Docker inspect reports **State.Pid = 41000**, while inside the container **ps** shows **tini PID 1** and **java PID 8**. Can you run **jcmd 41000** on the host to capture a Java thread dump?

**A:** Not justified. **41000** is likely **tini**'s host PID, not Java's. You must find the JVM's host PID, verify **NStgid**, and check attachability. Inside the container, once verified, the right target is PID **8**.

**Q2.** On a Linux host, **/proc/53000/status** shows **NStgid: 53000 13**. If host procfs is mounted in the host namespace and the process sits in a child namespace, which PID applies when reading /proc inside the container?

**A:** Usually **13**, if the container's /proc is mounted in the namespace containing that process. On the host use **53000**. Do not invert the direction without verifying procfs perspective.

**Q3.** A JVM prints **ProcessHandle.current().pid() = 1**, while **docker inspect** reports **31200**. Is there a contradiction?

**A:** No. They can refer to the same JVM when it is PID 1 inside the container and PID 31200 on the Linux host. Verify via mapping rather than looking at numbers alone.

**Q4.** Docker Desktop on macOS reports **State.Pid = 880**. Can you run **kill 880** in the macOS terminal to stop that Linux JVM?

**A:** Do not draw that conclusion; PID 880 belongs to the Linux VM per the Docker daemon, not a macOS PID of the same process. Use Docker mechanisms, exec, or debug inside the appropriate Linux environment.

**Q5.** A Pod has **shareProcessNamespace: true**. Can you assume **jcmd 1 VM.version** targets the Java application?

**A:** No. PID 1 may be the Pod sandbox/init process while Java sits at another PID. Inspect the process list and container identities.

**Q6.** Both **readlink /proc/A/ns/pid** and **readlink /proc/B/ns/pid** return the same inode. Does that prove A and B are the same process?

**A:** No. They may be two **different processes in the same PID namespace**. Compare PID, namespace, command, start time, and container identity.

## Reference Sources for Cross-Checking

- [Linux pid_namespaces(7): ancestor/child namespace relationships, PID 1, and /proc](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)
- [Linux proc_pid_status(5): Tgid, Pid, NStgid, and NSpid](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html)
- [Linux namespaces(7): namespace inodes and symlinks in /proc](https://man7.org/linux/man-pages/man7/namespaces.7.html)
- [Docker run: PID namespace modes and --pid](https://docs.docker.com/reference/cli/docker/container/run/)
- [Docker inspect: formatting and querying container metadata](https://docs.docker.com/reference/cli/docker/inspect/)
- [Docker Desktop: boundary between Linux VM and desktop machine](https://docs.docker.com/faqs/platform/)
- [Kubernetes: sharing PID namespace in a Pod](https://kubernetes.io/docs/tasks/configure-pod-container/share-process-namespace/)
- [Java SE 21: ProcessHandle API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html)
- [JDK 21: jcmd, PID lookup, and attach prerequisites](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)

**Immediately actionable principle:** whenever you see a PID associated with a Java container, always identify **which process, in which PID namespace, on which kernel/host, at what time, and from which position the tool runs**. Only after confirming all of those factors should you use the PID to diagnose or control the JVM.