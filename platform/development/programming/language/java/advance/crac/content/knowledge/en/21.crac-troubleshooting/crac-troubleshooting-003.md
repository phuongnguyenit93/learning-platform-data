# Finding Open Files or Sockets From Error Messages

When creating a CRaC checkpoint, an application can encounter errors related to file descriptors, open files, sockets, pipes, or native resources managed by libraries. An error message sometimes mentions only a descriptor number, inode, path, or OS error code. To locate the exact resource, correlate that message with the list of handles held by the process, then trace back to the Java component or library that opened it.

On Linux, the most useful tools are typically /proc/PID/fd, lsof, ss, and fuser. For sockets, combine inode information from /proc or lsof with connection state from ss. On Windows, you can use Sysinternals Handle, Process Explorer, and PowerShell commands for TCP/UDP endpoints.

The goal is not merely finding which file or socket is open. You must determine who owns it, why it is still open at checkpoint time, whether that resource is supported by the engine or needs closing, and how to recover it after restore.

## 1. Read the Error Message Before Running Tools

First, preserve the full log of the failed checkpoint attempt. Do not grab only the last line: the error line may identify the file descriptor, while preceding lines show which Resource or native step was handling the resource.

Information to extract:

- Timestamp and PID of the process being checkpointed.
- Stage where failure occurred: beforeCheckpoint callback, engine dump step, or restore step.
- File descriptor number if stated in the log, e.g., FD 17.
- Path, inode, handle type, or socket address if present.
- Operating system error code such as EBADF, EMFILE, ENFILE, EADDRINUSE, or EOPNOTSUPP.
- Resource name, Java class, library, or native component appearing in the stack trace.
- Checkpoint engine name and version if provided in the log.

An illustrative log may look like:

~~~text
Checkpoint failed while saving process 2481
Unsupported file descriptor: fd=17
Target: socket:[73192]
Native checkpoint operation returned EOPNOTSUPP
~~~

This is only a formatting example, not a standard message across every CRaC runtime. If the log includes FD number 17 and socket inode 73192, those two values can be used to locate the corresponding socket in the process. If the log states a file path, search for that path in the FD list and verify which process holds it.

### Distinguishing Java Callback Errors From Checkpoint Engine Errors

Errors can arise at two layers:

| Origin | Common symptoms | Investigation direction |
|---|---|---|
| Resource.beforeCheckpoint | Java stack trace, Resource class name, flush/close error, or timeout | Locate the component owning the resource and callback logic |
| JDK/CRaC runtime | Runtime logs, warnings about JVM state or native handles | Cross-check JDK/CRaC version and runtime configuration |
| Checkpoint engine | Native dump error, FD, socket, namespace, or kernel error code | Correlate FDs with /proc, lsof, ss, and engine logs |
| Restore | Error reopening files, connections, credentials, or afterRestore callback | Check resources changed during checkpoint interval and recovery logic |

Do not conclude that every file descriptor reported by the engine is an application bug. Some descriptors belong to the JVM, agents, or runtime. Conversely, a completed Java callback does not prove all native handles are checkpointable.

## 2. Finding the PID of the Java Process

On Linux, find processes with ps:

~~~shell
ps -eo pid,ppid,user,comm,args | grep '[j]ava'
~~~

If you know part of the application name:

~~~shell
pgrep -af 'order-service'
~~~

Select the exact PID of the process creating the checkpoint. Avoid mistaking the PID of Gradle, a shell launcher, a sidecar, or another Java process.

In containers, the PID visible inside the container may differ from the host PID. If running commands inside the container, use the PID in that PID namespace when accessing /proc inside the container. If investigating from the host, identify the corresponding host PID and the namespace the process uses.

You can inspect process details:

~~~shell
ps -p 2481 -o pid,ppid,user,lstart,stat,cmd
cat /proc/2481/status
~~~

Replace 2481 with the actual PID. Do not reuse a PID from an older run because PIDs can be recycled after a process exits.

## 3. Listing File Descriptors via /proc

On Linux, each process has a /proc/PID/fd directory. Each entry is a symbolic link to the object that the file descriptor references.

Example:

~~~shell
ls -l /proc/2481/fd
~~~

Illustrative output:

~~~text
0 -> /dev/null
1 -> /var/log/order-service/stdout.log
2 -> /var/log/order-service/stderr.log
3 -> /opt/app/config/application.yml
7 -> socket:[73192]
9 -> pipe:[82014]
12 -> anon_inode:[eventpoll]
17 -> socket:[84501]
~~~

Common meanings:

- The number on the left is the file descriptor in the process.
- Regular paths can be files, devices, or files in the filesystem.
- socket:[inode] is a kernel-represented socket identified by inode.
- pipe:[inode] is one end of a pipe.
- anon_inode:[...] is typically a kernel resource such as eventpoll or eventfd.
- memfd: may be a file-backed memory object in RAM.

Not every entry is a regular file. If the engine reports an unsupported descriptor, the object type such as pipe, eventpoll, socket, or device may matter more than a path name.

### Inspecting a Specific FD

If the error message specifies FD 17:

~~~shell
readlink /proc/2481/fd/17
cat /proc/2481/fdinfo/17
~~~

readlink shows what object the descriptor points to. fdinfo can provide flags, position, mount ID, or details depending on descriptor type and kernel.

Example fdinfo for a file:

~~~text
pos:    4096
flags:  0100002
mnt_id: 32
ino:    912345
~~~

pos is the descriptor's current file offset. For buffered streams, the physical file position may differ from the logical position already processed by the application. Do not treat pos as the business offset if BufferedInputStream or read-ahead classes are involved.

### Listing All FDs With Their Targets

You can use a shell loop to print FD numbers and targets:

~~~shell
for fd in /proc/2481/fd/*; do
    name=$(basename "$fd")
    printf '%s -> ' "$name"
    readlink "$fd"
done
~~~

If the shell or permissions forbid reading an entry, note the error and continue investigating with lsof. The FD list can change while the process runs; output is a point-in-time reading at the moment of execution, not an atomic snapshot of the whole application.

## 4. Using lsof to Find Open Files

lsof (list open files) lists files and handles held by a process. On Linux, sockets, pipes, and many kernel objects also appear as open files.

List all resources of a PID:

~~~shell
lsof -nP -p 2481
~~~

Options:

- -p 2481: inspect only the process with PID 2481.
- -n: do not resolve network addresses to hostnames.
- -P: do not convert port numbers to service names.

Each output line typically contains columns COMMAND, PID, USER, FD, TYPE, DEVICE, SIZE/OFF, NODE, and NAME. The FD column contains the descriptor number and may have suffixes such as r, w, u indicating open mode. The NODE column usually holds the inode; NAME can hold the path or socket details.

### Finding Files by Path

If the log names a specific file:

~~~shell
lsof -nP -- /var/data/orders/current.log
~~~

Or filter within one process:

~~~shell
lsof -nP -p 2481 | grep '/var/data/orders'
~~~

If multiple processes have the file open, determine which descriptor belongs to the process being checkpointed. Do not close files from another process merely because the path matches.

### Finding Deleted Files That Are Still Open

An easy-to-miss situation is a file deleted from a directory while a process still holds a descriptor. Linux lets the process continue accessing that inode until the last descriptor closes.

Find unlinked files still held open:

~~~shell
lsof -nP -p 2481 +L1
~~~

Or search for the deleted marker:

~~~shell
lsof -nP -p 2481 | grep '(deleted)'
~~~

Example:

~~~text
java 2481 app  15w REG  8,1  1048576 912345 /var/log/app.log (deleted)
~~~

This often occurs when logrotate deletes or renames a file while a logger still holds the old handle. The application keeps writing to the old inode even though the path was removed. If checkpointing needs the path or a recoverable file descriptor, this can cause failures or prevent finding the file by name.

The usual fix is instructing the logger to close the old file and reopen via the logging framework's rotation mechanism. Do not delete additional files or close descriptors externally while the application is still writing.

## 5. Finding Open Sockets

Sockets also appear under /proc/PID/fd as socket:[inode]. You can use lsof to filter a process's sockets:

~~~shell
lsof -nP -a -p 2481 -i
~~~

This command shows Internet sockets owned by the process. For Unix domain sockets:

~~~shell
lsof -nP -U -p 2481
~~~

The NAME column typically displays protocol, local/remote addresses, and ports. Example:

~~~text
java 2481 app  17u IPv4 84501 0t0 TCP 10.0.0.12:43120->10.0.0.20:5432 (ESTABLISHED)
java 2481 app  21u IPv6 84502 0t0 TCP *:8080 (LISTEN)
~~~

These are examples only. Host/port names may be resolved if -nP is omitted.

### Using ss to Inspect Connection States

ss displays kernel sockets, TCP states, and process info when permissions allow:

~~~shell
ss -tanp
ss -uanp
ss -xap
~~~

Meaning:

- -t: TCP.
- -u: UDP.
- -a: both listening and non-listening sockets.
- -n: display numeric addresses and ports.
- -p: show process if permitted.
- -x: Unix domain sockets.

Filter by port:

~~~shell
ss -tanp '( sport = :8080 or dport = :8080 )'
~~~

Filtering by PID in output can be done by reading the process column, though formatting depends on iproute2 version. lsof -p PID -i is often more convenient once the PID is known.

### Correlating Socket Inodes With FDs

Suppose:

- /proc/2481/fd/17 points to socket:[84501].
- lsof -nP -p 2481 -i shows FD 17, NODE 84501.
- ss -tanp shows the corresponding TCP connection.

These three sources identify which socket FD 17 is, its local/remote endpoints, and its current state.

If ss -p does not show the process, it may be due to insufficient permissions or the socket belonging to another network namespace. Check from the right namespace and with sufficient permissions to read process info. On Linux, /proc/PID/net reflects the process's network namespace; it is not a list of sockets exclusive to that single process.

In containers, you may need to run the command inside the process's network namespace from the host:

~~~shell
nsenter -t 2481 -n ss -tanp
~~~

This command requires appropriate privileges and should only be used in authorized operational environments. Replace 2481 with the process's actual host PID. If already inside the container, use the current PID and namespace rather than confusing it with a host PID.

### Distinguishing Socket States

Common TCP states:

| State | General meaning | What to check |
|---|---|---|
| LISTEN | Socket awaiting incoming connections | Does the server listener need closing before checkpoint and reopening after restore? |
| ESTABLISHED | Active connection | Will the peer keep the session or time out while the process is paused? |
| CLOSE-WAIT | Peer has closed, application has not yet closed local socket | Application may not have handled EOF or released the connection |
| FIN-WAIT / LAST-ACK | Connection is in the process of closing | Check threads and socket-closing logic |
| TIME-WAIT | Kernel retains TCP state after connection closure | Usually has no corresponding open application file descriptor |

Do not conclude every TIME-WAIT is an open socket of the Java process. TIME-WAIT is normally a kernel TCP state after the socket has already closed; it can affect rebinding an address/port, yet is not necessarily an FD still held by the process.

## 6. Finding the Process Holding a File or Port

When only the file path is known:

~~~shell
fuser -v /var/data/orders/current.log
~~~

When only the TCP port is known:

~~~shell
ss -ltnp 'sport = :8080'
~~~

Or:

~~~shell
lsof -nP -iTCP:8080 -sTCP:LISTEN
~~~

When only the Unix socket path is known:

~~~shell
lsof -nP -U | grep '/run/service.sock'
~~~

These commands help identify the process owning a resource. Before taking action, confirm whether the PID is actually the application being checkpointed. Do not use fuser -k or kill commands automatically without understanding impact; they can terminate processes serving traffic or writing data.

## 7. Common Error Codes and How to Interpret Them

Native error messages may include POSIX error codes. Exact meanings depend on the system call and engine, yet these codes commonly point the investigation:

| Error code | Common meaning | Investigation direction |
|---|---|---|
| EMFILE | Process reached its file descriptor limit | Count FDs, hunt for leaks, check ulimit and handle lifecycles |
| ENFILE | System-wide file table reached its limit | Check host load and other processes |
| EBADF | Invalid or already closed descriptor | Look for close/use races, recycled FDs, or handle management bugs |
| EADDRINUSE | Address/port already in use | Find listener or process holding the port; review socket lifecycle and TIME-WAIT |
| EOPNOTSUPP | Operation or resource type unsupported | Identify FD type and checkpoint engine limitations |
| ENOENT | Path or target does not exist | Check deleted/renamed files, mounts, and working directory |
| EACCES / EPERM | Insufficient permissions | Check user, capabilities, namespaces, and permissions |

Not all logs use errno names; some print only numeric codes or runtime-specific strings. Look up the exact engine and system call in the logs. A single error code is insufficient to determine root cause without knowing which operation failed.

### EMFILE and ENFILE

Count open FDs:

~~~shell
ls -1 /proc/2481/fd | wc -l
ulimit -n
cat /proc/2481/limits
~~~

ulimit -n in the current shell is not necessarily the limit of a process launched by another service manager. /proc/PID/limits reflects the target process's limits.

In Java, you can read the current descriptor count on Unix platforms via the JDK's MXBean:

~~~java
import java.lang.management.ManagementFactory;

import com.sun.management.UnixOperatingSystemMXBean;

public final class FileDescriptorMetrics {
    public static void print() {
        var bean = ManagementFactory.getOperatingSystemMXBean();
        if (bean instanceof UnixOperatingSystemMXBean unix) {
            System.out.println("openFD="
                    + unix.getOpenFileDescriptorCount());
            System.out.println("maxFD="
                    + unix.getMaxFileDescriptorCount());
        }
    }
}
~~~

The MXBean provides only the current FD count and limit on supported platforms. It does not list paths, sockets, or Java objects owning individual descriptors. Use /proc or lsof to locate specific resources.

If FD counts climb steadily over time, audit code paths creating streams, channels, sockets, executors, HTTP clients, JDBC pools, and native libraries. Raising ulimit can ease symptoms but will not fix a leak.

## 8. Tracing From an FD Back to the Owning Java Component

The operating system knows the process and descriptor, yet does not always know which Java object opened it. An FD can be created by:

- FileInputStream, FileOutputStream, or FileChannel.
- Socket, ServerSocket, or DatagramSocket.
- HTTP clients, JDBC drivers, or connection pools.
- Logging frameworks and appenders.
- Native libraries via JNI/JNA.
- JVM, JFR, agents, or frameworks.
- Pipes, process builders, or IPC libraries.

### Using Information From lsof

If FD 17 points to /var/data/orders/current.log, search for code owning writers to that file. If FD 17 is a TCP connection to database port 5432, inspect the corresponding connection pool/driver. If it is a Unix socket to an agent, locate the library or IPC process that created the socket.

File names or endpoints are clues only; multiple components can open the same path or connect to the same endpoint.

### Using Thread Dumps

Thread dumps help locate threads performing I/O or holding relevant locks:

~~~shell
jcmd 2481 Thread.print
~~~

Or:

~~~shell
jstack 2481
~~~

A thread dump does not directly map every FD to a Java object. However, stack traces can reveal threads inside SocketInputStream, FileChannel, JDBC drivers, HTTP clients, or specific libraries. Combine log timestamps, thread dumps, and FD inventories to track down the owner.

Some JVMs require attach permissions or configuration allowing attach. If commands do not work, rely on application logs, JFR, or already enabled observability tools. Do not restart the process solely to take a thread dump if doing so destroys the state under investigation.

### Adding Logs Where Resources Are Created and Closed

For application-owned resources, log:

- Component or Resource name.
- Resource type: file, socket, channel, or client.
- Sanitized path or endpoint with sensitive details stripped.
- Open, close, and reopen timestamps.
- Current lifecycle state.
- Close/reopen errors if any.

Do not log tokens, passwords, queries containing sensitive data, or payloads. For sockets, log only approved host/port information; for files, avoid logging file contents or sensitive details embedded in paths.

## 9. Special Resources in /proc

Not every descriptor corresponds to a file or socket the application can close directly.

| Target in /proc/PID/fd | Possible meaning | Handling direction |
|---|---|---|
| pipe:[inode] | Pipe between threads/processes or subprocesses | Identify producer/consumer and pipe lifecycle |
| anon_inode:[eventpoll] | epoll instance | Find owning selector/event loop |
| anon_inode:[eventfd] | Event notification descriptor | Find library/runtime creating the eventfd |
| anon_inode:[timerfd] | Timer descriptor | Check scheduler/native timer integration |
| memfd:name | In-memory file | Identify library creating memfd and engine support |
| /dev/* | Device handle | Check driver and access permissions |
| socket:[inode] | Kernel socket | Correlate with lsof and ss |

For example, Java NIO Selectors on Linux may use epoll underneath. If the engine reports an anon_inode eventpoll, do not try deleting the descriptor manually. Find the Selector or event loop owning it and check whether the JDK/CRaC runtime provides guidance for handling that resource type.

Similarly, descriptors created by JNI/native libraries must be closed through the library's API. Closing an FD directly from a shell while the JVM still holds the corresponding Java object can allow the kernel to reuse the FD number for another resource; the stale object may then inadvertently operate on the new descriptor.

## 10. Investigating Inside Containers and Kubernetes

Containers usually have separate PID namespaces and network namespaces. Therefore:

- The PID inside the container may differ from the host PID.
- /proc/PID/fd must be read inside a PID namespace that sees the process.
- ss must run inside the corresponding network namespace to see the right sockets.
- Access to /proc may be restricted by user, mount options, ptrace policy, or container security context.

If inside the container:

~~~shell
ps -ef
ls -l /proc/1/fd
ss -tanp
~~~

If investigating from the host, determine the host PID first. You can use docker top for Docker containers or the corresponding runtime tool to locate the PID. In Kubernetes, process info may need to be gathered from inside the container or via node-level diagnostics depending on operator permissions.

If using the host PID and needing to inspect the process's network namespace:

~~~shell
nsenter -t HOST_PID -n ss -tanp
~~~

Replace HOST_PID with the actual PID. Do not run nsenter or host-level tools without appropriate operational authorization. If the container has restricted capabilities, failing to see sockets does not prove no sockets exist.

### Notes on Sidecars and Other Processes

A Pod may contain multiple containers, sharing or separating process and network namespaces depending on configuration. Sockets opened by a sidecar do not necessarily belong to the JVM. If engine logs identify the JVM's PID, investigate only that PID's FDs first; check other processes later only if the error points to shared resources.

Do not stop a sidecar or delete socket paths to resolve a JVM FD error before determining dependencies. Doing so can break health checks, service meshes, or workload IPC connections.

## 11. Equivalent Tools on Windows

CRaC and checkpoint engines are normally used on Linux, yet if you need to investigate a Java application on Windows or a runtime/vendor with custom tools, the following tools can be used.

### Sysinternals Handle

Microsoft Sysinternals Handle lists open handles of a process:

~~~powershell
handle.exe -p 2481
~~~

Replace 2481 with the actual PID. You can filter by file name or handle string using options supported by your Handle version. Read the help text of your exact tool version before running. Do not use forced handle-closing options during diagnostics; doing so can corrupt application state.

Process Explorer also lets you select a process, view its handle list, and search for processes holding a specific file or object. It is a visual option when correlating handles with processes.

### Finding TCP and UDP Endpoints With PowerShell

List TCP connections of a PID:

~~~powershell
Get-NetTCPConnection -OwningProcess 2481 |
    Select-Object LocalAddress, LocalPort, RemoteAddress,
                  RemotePort, State, OwningProcess
~~~

List UDP endpoints:

~~~powershell
Get-NetUDPEndpoint -OwningProcess 2481 |
    Select-Object LocalAddress, LocalPort, OwningProcess
~~~

Or use netstat:

~~~powershell
netstat -ano
netstat -ano | findstr ":8080"
~~~

The PID in the last column of netstat can be correlated to a process:

~~~powershell
Get-Process -Id 2481
~~~

PowerShell cmdlets and outputs may vary across Windows versions. To locate file handles, use Handle or Process Explorer; Get-NetTCPConnection lists only network endpoints, not file handles.

## 12. Example Workflow for Finding a Socket From an FD Error

Suppose the checkpoint log reports:

~~~text
checkpoint error: unsupported fd 17
~~~

You can investigate in sequence:

**Step 1: Confirm the process and FD.**

~~~shell
ps -p 2481 -o pid,user,cmd
readlink /proc/2481/fd/17
cat /proc/2481/fdinfo/17
~~~

If the output is socket:[84501], record inode 84501.

**Step 2: Find the process's socket details.**

~~~shell
lsof -nP -a -p 2481 -i
~~~

Locate the line with FD 17 or NODE 84501. Note TCP/UDP, local endpoint, remote endpoint, and state.

**Step 3: Cross-check state from the kernel.**

~~~shell
ss -tanp
~~~

If the process is in its own network namespace, run ss in that namespace. If lsof and ss disagree, check permissions, reading timing, and whether the socket closed during investigation.

**Step 4: Trace back to the Java owner.**

Inspect thread dumps and connection logs to identify the client or library that created the socket. If the endpoint is a database, check the JDBC pool. If it is an HTTP endpoint, check the HTTP client or connection pool. If it is a Unix socket, identify the agent or IPC library.

**Step 5: Choose a lifecycle policy.**

If the socket cannot be supported by the engine, stop accepting requests, drain operations using the socket, close the client/connection before checkpoint, and create new connections after restore. If the library already has CRaC integration, use that integration per its documentation.

**Step 6: Re-test.**

Create a checkpoint after resources have been handled. After restore, confirm the new client connects, no stale FDs are reused, and readiness opens only once dependencies are ready.

## 13. From Investigation Findings to Lifecycle Fixes

Finding the FD is only the first step. Handle it at the right owner:

| Found resource | Common owner | Handling around checkpoint |
|---|---|---|
| InputStream/FileChannel | File reader or repository | Stop reader, save logical offset, close channel, reopen after restore |
| OutputStream/log file | Writer or logging appender | Drain writer, flush, close and reopen via framework API |
| JDBC socket | Driver/connection pool | Drain transactions, close or refresh connections per pool/driver CRaC integration |
| HTTP socket | HTTP client/connection pool | Stop requests, close client or connections per contract, recreate after restore |
| Server listener | Web server or embedded server | Use framework/server CRaC integration to close and rebind in proper order |
| Unix domain socket | IPC client/server or agent | Verify engine support and recreate socket per protocol |
| Pipe/subprocess FD | ProcessBuilder or native library | Terminate or manage subprocess, close streams, and confirm engine support |
| epoll/eventfd | Selector or event loop | Use JDK/framework lifecycle; do not close descriptors directly from outside |
| Native handle | JNI/JNA or SDK | Use the library's official close/reopen API |

### Example Resource Managing a File Channel

The following example illustrates a Resource owning a FileChannel. It saves the read/write position, closes the channel before checkpoint, and opens a new channel after restore:

~~~java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ManagedFile implements Resource {
    private final Path path;
    private FileChannel channel;
    private long savedPosition;

    public ManagedFile(Path path) throws IOException {
        this.path = path;
        open();
        Core.getGlobalContext().register(this);
    }

    public synchronized FileChannel channel() {
        if (channel == null || !channel.isOpen()) {
            throw new IllegalStateException("File is not ready");
        }
        return channel;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (channel != null && channel.isOpen()) {
            savedPosition = channel.position();
            channel.force(true);
            channel.close();
            channel = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        open();
        channel.position(savedPosition);
    }

    private void open() throws IOException {
        channel = FileChannel.open(
                path,
                StandardOpenOption.CREATE,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE);
    }
}
~~~

This is an example managing an application-owned file. In real applications, drain threads using the channel before the callback. If buffering is present, channel position may differ from the logical processed offset; save an appropriate business offset. force(true) carries I/O cost and should be used only when durability requires it. If checkpoint is aborted after the channel closed, the coordinator needs a path to reopen the resource for the current process before accepting work.

Do not use this pattern to manually manage file descriptors of HTTP clients, JDBC drivers, or logging frameworks. Those libraries can maintain internal pools, threads, and native state; use the lifecycle APIs they provide.

## 14. Do Not Manually Close Descriptors From Outside the Process

Once FD 17 is identified, it may be tempting to close it immediately from a shell or native debugger. That is usually not the right fix for a running Java application.

Risks include:

- The Java object still holds a reference to the closed descriptor.
- The kernel may reuse the same FD number for another resource.
- Subsequent reads/writes from the old object may get EBADF or affect the wrong resource.
- Another thread may be using the descriptor at the moment of closure.
- A connection pool may continue marking the connection as valid.
- The afterRestore callback may open another handle while the old one was never cleanly released.

Close resources through the owning object or API. Use forced handle-closing tools only when system operational documentation explicitly requires it and impact has been assessed.

Similarly, do not delete a socket file path in use by a server to try clearing errors. Removing the pathname does not necessarily close a bound socket; it can prevent new clients from connecting or leave two inconsistent endpoints.

## 15. Concise Investigation Workflow

When receiving an error message about an open file or socket, follow this sequence:

1. Save full checkpoint logs and extract PID, FD, path, inode, or errno.
2. Confirm the right process and namespaces.
3. Use /proc/PID/fd to identify resource type and inode.
4. Use lsof -p PID to locate files, sockets, pipes, and deleted-yet-open resources.
5. For sockets, use lsof -i, lsof -U, and ss to find endpoints/states.
6. Use thread dumps, application logs, and dependency graphs to locate the Java/native owner.
7. Read the documentation of the CRaC runtime, checkpoint engine, and resource-owning library.
8. Close, flush, drain, or reopen resources at the proper lifecycle owner.
9. Test the recovery path if checkpoint is aborted after beforeCheckpoint already closed resources.
10. Create a checkpoint and test restore in a compatible environment; verify FDs, sockets, and readiness after restore.

During investigation, start with read-only inspection commands. Avoid killing processes, closing FDs, deleting sockets, or altering system limits before identifying root cause. If sharing output, strip tokens, sensitive usernames, paths containing secrets, and unnecessary internal metadata.

## 16. Common Misconceptions

**"Every entry in /proc/PID/fd is a regular file."**

Incorrect. Entries can be sockets, pipes, eventfd, epoll, memfd, or devices. Inspect symbolic links and match resource types.

**"A TIME-WAIT socket is an open Java FD."**

Not necessarily. TIME-WAIT is normally a kernel TCP state after the application already closed the socket. Verify process ownership via lsof or ss.

**"If the file path no longer exists, the process cannot have it open."**

Incorrect on Linux. An unlinked file can still be held open via an FD; use lsof +L1 to find it.

**"Java's MXBean tells you exactly which files are open."**

The Unix MXBean provides only FD counts and limits. /proc or lsof is required to list individual resources.

**"You can close a problematic FD by FD number from the shell."**

Do not do this. Closing outside the process can desynchronize Java objects and allow FD numbers to be reused. Close through the owner API.

**"If checkpoint reports a socket error, just raise ulimit."**

Raising the FD limit helps only with EMFILE/ENFILE limit errors. It does not make an unsupported socket or FD type compatible with the engine.

**"lsof showing nothing means no resource is open."**

It may be due to missing permissions, the process residing in another namespace, lsof not being installed, or resources changing during inspection. Cross-check /proc, ss, and access permissions.

## 17. Conclusion

To find open files or sockets from error messages, start from PID, FD, inode, path, and errno in the logs. On Linux, /proc/PID/fd shows what a descriptor points to; lsof lists files/sockets and detects deleted-yet-open files; ss provides connection states and endpoints. Inside containers, investigate in the exact PID and network namespaces. On Windows, use Sysinternals Handle/Process Explorer and PowerShell TCP/UDP commands.

Once the resource is found, trace back to the Java or native component owning it and handle it using that component's lifecycle API. Do not close descriptors manually based solely on FD numbers. With CRaC, coordinate work draining, close or prepare resources before checkpoint, reopen after restore, and accept traffic only once dependencies are ready.
