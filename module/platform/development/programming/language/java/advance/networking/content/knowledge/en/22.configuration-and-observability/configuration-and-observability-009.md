# Java Networking: Correlating Application Metrics, Socket States, and OS Limits

## 1. The Problem: The Server Is “Alive” Yet Users Cannot Connect

A Java server may report **30% CPU**, **only 40% heap used**, and a dashboard showing **200 active requests**, yet clients still repeatedly hit `ConnectException`, slow connections, `Too many open files`, or timeouts. Where does the problem lie?

To answer this, do not look only at Java metrics. A request passes through multiple layers:

~~~text
                    Java application metrics
   requests, accepted sessions, active handlers, queue,
   connection pool, response latency, connect errors
                              |
                              v
                    JVM / process resources
     Java threads, heap, direct buffers, process open FDs
                              |
                              v
                     Operating system
       TCP LISTEN / ESTABLISHED / CLOSE_WAIT / TIME_WAIT
     accept queue, SYN queue, ports, socket buffers,
        per-process and system-wide resource limits
                              |
                              v
                  Network / proxy / client
       NAT, firewalls, LB, retries, timeouts, DNS,
        retransmissions and upstream availability
~~~

**The key point:** the three groups of metrics **do not share the same unit, scope, or measurement timing**:

- An `activeRequest` is usually an **application processing unit**, not a TCP socket.
- An HTTP keep-alive connection may be idle while still in **TCP ESTABLISHED**.
- A long-lived WebSocket may have **no request handler currently running**.
- A `TIME_WAIT` entry may exist in the kernel **after the application has already closed the socket**, and does not equate to an open Java `Socket`.
- The **process** `openFileDescriptorCount` metric includes many types of file descriptors besides network sockets (files, pipes, epoll, logging, etc.), not “the number of connections”.
- `ss -s` or kernel TCP statistics usually measure the **network namespace/host**, not a single Java process.
- If the Java service runs inside a container, host metrics may include many other processes/namespaces or may not reflect the same limits that apply to the container.

Goal: know how to **count the right things**, correlate application metrics with TCP socket states and OS limits, analyze discrepancies, build meaningful dashboards/alerts, and run a **Java 17+** demo illustrating how a single JVM can have client-side sockets, server-side sockets, and a listening socket while having **only two active server sessions being processed**.

## 2. Start from Questions and Scope, Not from a Single Number

Ask five questions before opening a terminal:

1. **What target is being measured?** Which process PID, which container/pod, which IP/port, IPv4 or IPv6, inbound or outbound?
2. **What is being counted?** In-flight requests, established sockets, file descriptors, TCP state entries, accept queue, or connection pool entries?
3. **At what point in time?** An instantaneous snapshot or a one-minute rate? Metrics exported every 15 seconds versus `ss` captured at a different moment can diverge due to short bursts.
4. **At what level?** Process, network namespace, entire host, cluster, proxy, or the entire backend pool?
5. **What is the purpose of the investigation?** Connection leak, server overload, client reconnect storm, bind failure, ephemeral port exhaustion, file descriptor exhaustion, or OS backlog?

Some common scenarios:

| Symptom | Metrics to correlate first |
| --- | --- |
| `Too many open files` | Process open FDs, per-process soft limit, socket/file type |
| Slow HTTP 200 despite low CPU | Request/queue latency, active handlers, socket send/receive queue, downstream I/O |
| New connections fail while existing connections work | `LISTEN`, accept queue, errors, backlog, FD limits, firewall/proxy |
| Outbound `Cannot assign requested address` | Ephemeral port use, outbound connection churn, destination, NAT, TIME_WAIT |
| `CLOSE_WAIT` growing over the long term | Socket close ownership in the process, leaked streams/sessions |
| Sudden spike in `TIME_WAIT` | Connection close rate, active closer, connection reuse, client retries |
| App reports 100 active but OS sees 20,000 established | Keep-alive/idle pools, WebSockets, proxy fan-out, scope mismatch |
| Heap is normal but RSS grows | Direct buffers, native memory, kernel socket memory, threads, file descriptors |

**Do not rush to tune `sysctl` or increase `ulimit`** before knowing whether there is a leak or simply normal traffic. Raising limits can temporarily mask a resource leak and cause the incident to spread further.

## 3. Define Application Metrics Precisely

An observable system should have the following metric groups:

| Illustrative metric | Type | When it increases/decreases | Meaning |
| --- | --- | --- | --- |
| `net_accept_total` | Counter | Increments after each inbound socket is accepted | Total accepts since process startup |
| `net_connection_closed_total` | Counter | Increments when the socket has actually closed | Total closes recorded by the application |
| `net_active_server_connections` | Gauge | Increments after accept, decrements in `finally` after close | Number of accepted server sockets currently owned by the application |
| `net_outbound_active_connections` | Gauge | Tracks open/close or pool connection state | Outbound connections managed by the application |
| `http_requests_in_flight` | Gauge | Increments when the request handler starts, decrements when it finishes | HTTP work currently being processed, **not sockets** |
| `http_request_duration_seconds` | Histogram | Observed when the request completes | Latency distribution p50/p95/p99 by method/route |
| `http_request_errors_total` | Counter | By status/error type | HTTP 4xx/5xx and transport errors per contract |
| `net_connect_failures_total` | Counter | Increments when connect fails | Failures opening new connections from the app |
| `net_read_timeouts_total` | Counter | When a read times out | Client/server read stall |
| `net_bytes_received_total` / `sent_total` | Counter | Bytes actually received/sent | App-level traffic; does not always equal wire bytes |
| `executor_active_tasks` | Gauge | Number of running workers | Thread pool saturation |
| `executor_queued_tasks` | Gauge | Tasks waiting in the executor queue | Sign of backlog inside the application |
| `pool_idle_connections` | Gauge | Idle connections in HTTP/DB pool | May still be TCP ESTABLISHED |
| `socket_send_queue_bytes` | OS/diagnostic | Kernel outbound data waiting | Slow-reading client, network congestion, or scheduling |

The names in the table are **design suggestions**, not an automatic metric set available in every JDK library. JDK `HttpClient`, Netty, Spring Boot, Micrometer, or Prometheus exporters have different concrete metrics; you must read the documentation for the exact version and actual instrumentation.

### 3.1. Counters, gauges, and histograms are not interchangeable

- A **Counter** like `accepted_total` grows over the lifetime of the process. To know the **rate**, compute the rate/delta; resetting on process restart does not mean “connections were reset to 0 in the kernel”.
- A **Gauge** like `active_connections` describes the most recent collection point. A value of 200 today and 200 tomorrow does not necessarily mean **the same 200 sessions**.
- A **Histogram** of request duration allows analyzing latency distribution; p99 cannot be inferred from an arithmetic mean alone.
- **Error rate** must use the appropriate denominator: `connect_failures / connect_attempts` differs from `http_5xx / all_requests` and differs from timeout rate.

**Do not attach `remoteIp`, `userId`, `socketId`, or request ID to every time-series label**: cardinality can explode when clients are numerous or change constantly. Use route templates, role, protocol, status class, and a bounded instance ID; detailed values belong in logs/traces with sampling and privacy controls.

### 3.2. Count at the right moment and ensure decrementing in finally

For inbound TCP, increment the gauge after the application takes ownership of the accepted socket, and decrement it when the socket is no longer owned:

~~~java
AtomicInteger active = new AtomicInteger();
LongAdder acceptedTotal = new LongAdder();

void onAccepted(Socket socket) {
    active.incrementAndGet();
    acceptedTotal.increment();
    try (socket) {
        handleRequest(socket);
    } catch (IOException error) {
        recordSocketError(error);
    } finally {
        active.decrementAndGet();
    }
}
~~~

This is an **illustrative fragment**, requiring application methods `handleRequest`/`recordSocketError` and appropriate Java imports. If ownership is transferred to another worker, the gauge should measure the **socket lifecycle**, not just the duration before the accept method returns.

**Submission failure case:** if `ExecutorService.execute(...)` throws `RejectedExecutionException` before the handler runs, the application must **close the socket** and **decrement the gauge if it was incremented**; otherwise metrics may report a phantom leak. If instrumentation counts accept total before rejection, rejected connections are clearly still counted in accept total, while the active gauge must return to 0 after close.

### 3.3. HTTP multiplexing breaks the 1 request = 1 connection relationship

- HTTP/1.1 keep-alive reuses a single socket for multiple **sequential** requests.
- HTTP/2 can multiplex multiple streams/requests over **a single TCP connection** if both client and server support it.
- An HTTP client pool can keep sockets idle even when there are no in-flight requests.
- A reverse proxy can aggregate many client connections into fewer backend connections or open separate outbound connections; each layer has independent metrics.
- WebSocket holds a session that can stay open for a long time even without messages; message callbacks are usually shorter than the socket lifetime.

Therefore, **do not compare the number of active HTTP requests against the number of ESTABLISHED rows** and treat a difference as a bug. You must classify by protocol, direction, and connection pooling.

## 4. TCP States Are Kernel States, Not Java Thread States

On Linux/macOS/Windows, the TCP stack has states; tools display names and details depending on the OS:

| TCP state | Intuitive description | When to investigate |
| --- | --- | --- |
| `LISTEN` | Waiting to accept connections at a local endpoint | Server not listening on the right IP/port, backlog full |
| `SYN-SENT` / `SYN_SENT` | Attempting to open an outbound connection | Connect timeout, routing/firewall, server unreachable |
| `SYN-RECV` / `SYN_RECEIVED` | Received SYN, handshake not yet complete | SYN flood, backlog, network path, asymmetric routing |
| `ESTABLISHED` | TCP connection established | Idle pool, active sessions, WebSocket, both ends of loopback |
| `FIN-WAIT-1` / `FIN_WAIT1` | This side has sent FIN and is waiting for acknowledgment | Close in progress, slow peer/network |
| `FIN-WAIT-2` / `FIN_WAIT2` | Received ACK for FIN, waiting for peer to close | Peer holding half-close too long, timeout policy |
| `CLOSE-WAIT` / `CLOSE_WAIT` | **Peer has sent FIN**, local application has not closed its side of the socket | If persistently increasing: check for leaks/close ownership |
| `LAST-ACK` / `LAST_ACK` | Waiting for ACK for the final FIN | Check close rate and connection loss |
| `TIME-WAIT` / `TIME_WAIT` | Temporarily holding state after termination to handle old/delayed packets | Churn/reconnect, active closer; **not a leak by itself** |
| `CLOSING` | Both sides initiated close simultaneously | Can be normal during simultaneous close |
| `CLOSED` | No active connection remains in the TCP control block | Usually no persistent socket entry to count |

**Distinguish application-side close from TCP state:** `Socket.close()` returning does not mean the kernel must immediately erase every trace of the connection. `TIME_WAIT` can persist after the socket descriptor is closed. Conversely, `CLOSE_WAIT` indicates that **the local side has not completed closing** after the peer closed its sending direction; if the count keeps rising, suspect that the application forgot to `close`, while still investigating by PID, stack, and history.

### 4.1. Analyze `ESTABLISHED` before treating it as “active users”

For example, the same JVM runs a loopback TCP server and connects to itself:

~~~text
Java process
   listener on 127.0.0.1:randomPort   -> 1 listening socket
   outbound client Socket A           -> 1 TCP endpoint
   outbound client Socket B           -> 1 TCP endpoint
   accepted server Socket A           -> 1 TCP endpoint
   accepted server Socket B           -> 1 TCP endpoint

Server application metric: 2 accepted active connections.
OS may list: 4 TCP ESTABLISHED endpoints in the same process
             + 1 LISTEN endpoint.
Process FDs: also include files/pipes/epoll/console and other descriptors.
~~~

This is a case where **you cannot expect the counters to match**. The number of kernel rows also depends on the OS, IPv4/IPv6, socket viewing permissions, and snapshot timing. When the same process owns both client and server ends, you must not add both ends of the loopback and call it “4 users”.

### 4.2. `CLOSE_WAIT` differs from `TIME_WAIT`

**CLOSE_WAIT:** the remote side has sent FIN, and the local application is still responsible for closing the socket after processing any remaining data. If `CLOSE_WAIT` for a PID rises persistently along with `open_fd`, inspect code using `Socket`, `InputStream`, `OutputStream`, `try-with-resources`, cancellation handling, and connection pool release.

**TIME_WAIT:** typically associated with the side that actively initiates the TCP close; the kernel retains state to handle delayed segments. Many `TIME_WAIT` entries can reflect **a high rate of short-lived connections closing continuously**, not unclosed Java streams. Find why clients continuously open/close (no pool reuse), proxy lifecycle, request retries, or deployment churn; do not rush to enable risky kernel tunables.

### 4.3. `LISTEN` does not mean every connection is accepted

A listening socket does not by itself guarantee that the acceptor/workers have enough capacity. `LISTEN` may still be shown while the accept queue is full, the JVM has hit its FD limit, CPU scheduling is insufficient, a rate limiter is rejecting traffic, or proxy routing is misconfigured. You need to combine **accept rate + accepts/errors + queue length + socket backlog** and latency at both ends.

## 5. File Descriptors (FDs) Are a Finite Resource, but Not Every FD Is a Socket

On Unix-like systems, TCP sockets typically use **file descriptors**. Each process has an open FD limit, but the FD list also contains:

- TCP and UDP sockets, Unix-domain sockets.
- Log/config/data files, pipes, eventfd, epoll/kqueue-related handles.
- Temporary files, mmap-related resources, and runtime internals.
- Descriptors serving the Java application and native libraries.

Therefore:

~~~text
process_open_fd != number_of_ESTABLISHED_sockets
process_open_fd != app_active_connections
process_open_fd != total_OS_TCP_states
~~~

### 5.1. Two numbers to read together: open and limit

On Unix-like JVMs there is an appropriate MXBean:

~~~java
var bean = ManagementFactory.getOperatingSystemMXBean();
if (bean instanceof com.sun.management.UnixOperatingSystemMXBean unix) {
    long open = unix.getOpenFileDescriptorCount();
    long max  = unix.getMaxFileDescriptorCount();
    System.out.println("Open FDs: " + open + ", max FDs: " + max);
} else {
    System.out.println("Unix FD metrics not available on this platform");
}
~~~

This is a **Java 17 fragment** requiring `import java.lang.management.ManagementFactory`. `com.sun.management.UnixOperatingSystemMXBean` is an **extension API for Unix-like platforms**, not a built-in API that returns FD counts on every Windows JVM. If a positive `max` is measured, the `open/max` ratio helps alert when approaching the limit; however, some systems may return a sentinel when unknown, so you must validate the values before dividing.

**Do not infer from open=300, max=1024 that there are 300 TCP connections.** Use OS tools to classify FDs and TCP states before drawing conclusions.

### 5.2. Soft limit, hard limit, and system limit

On Linux, `RLIMIT_NOFILE` has **soft** and **hard** limits for a **process**. The soft limit governs whether additional descriptors can be opened in practice; the hard limit is the administrative ceiling for raising the soft limit according to privileges. There are also system-wide limits and systemd/container runtime settings.

| Level | Example | Keep in mind |
| --- | --- | --- |
| Current shell | `ulimit -n` | Only reflects the shell running the command, not necessarily the JVM service's limit |
| Specific Java process | `/proc/<PID>/limits`, `prlimit` | Exact PID of the instance under investigation |
| Service manager | systemd `LimitNOFILE` | May differ from an interactive shell |
| Global OS | `fs.file-max` and related kernel resource limits | Not a per-JVM FD limit |
| Container/process sandbox | ulimits/cgroups/runtime | Does not always match the host shell |
| Application | max clients, pool cap, worker count | Logical limits **outside** the file descriptor limit |

An app with many log files, pipes, or outbound sockets can hit the FD limit **before** reaching a target of “10,000 inbound clients”. Conversely, if you raise NOFILE while the executor/heap/network cannot handle the load, raising the limit will not solve actual serving capacity.

### 5.3. `EMFILE` / `ENFILE` and errors in Java

The message `Too many open files` is usually related to the process hitting its open file descriptors limit (POSIX `EMFILE`), or the system exhausting its file table entries (POSIX `ENFILE`) depending on OS/context. In Java, accept/open socket/file operations can throw `IOException`, `SocketException`, or a corresponding native message.

Do not catch `IOException` and map every error to “FD exhaustion”; inspect the message/native errno/logs together with the `open_fd` metric, process limit, and the resource type that is growing. If the system-wide limit is exhausted, multiple processes may also be affected.

## 6. Linux Tools: Observing the Right PID, Port, and TCP State

> The commands in this section are **Linux diagnostics**, not Java code. Use the PID/port of a service you are authorized to observe. For containers, run inside the **appropriate network namespace** or clearly understand the difference between host and pod namespaces. Do not scan the whole host when you only need one service.

Example shell variables:

~~~bash
PID=12345
PORT=8080
~~~

Replace `12345` with the **actual PID of the Java process**, and `8080` with the **port the app listens on**. Read within the actual environment/namespace.

### 6.1. Where is it LISTENing?

~~~bash
ss -ltnp "sport = :$PORT"
~~~

- `-l`: listening sockets.
- `-t`: TCP; `-n`: numeric addresses/ports; `-p`: process info if permitted.
- Check `Local Address:Port`. If bound only to `127.0.0.1`, remote hosts cannot directly connect to another interface just because the port is in LISTEN.
- A port can have separate IPv4/IPv6 bindings; `[::]:8080` and `0.0.0.0:8080` should not always be assumed equivalent in every configuration.

On Linux `ss -ltn`, the `Recv-Q`/`Send-Q` columns of listening sockets usually represent **the number of completed-handshake connections waiting to be accepted** and the corresponding queue limit per kernel/stack. Do not mistake them for the total number of active TCP sessions. Kernel releases and TCP SYN backlog mechanisms can cause these counters to behave differently.

### 6.2. Counting connections related to the application port

~~~bash
ss -tanp "( sport = :$PORT or dport = :$PORT )"
ss -tan state established "( sport = :$PORT or dport = :$PORT )"
ss -tan state close-wait "( sport = :$PORT or dport = :$PORT )"
ss -tan state time-wait "( sport = :$PORT or dport = :$PORT )"
~~~

These are point-in-time snapshots; `ss -p` may require appropriate privileges to print PID/process info. The `sport/dport` filter selects **endpoints with that port**, which does not prove every row belongs to **the application's PID**: multiple processes, proxies, or `TIME_WAIT` connections with no remaining userspace owner may also appear.

**Distinguish direction:** if `PORT` is an inbound listener, accepted sockets typically have **source/local port** equal to PORT. Outbound connections from the application to a database on port 5432 have **destination/peer port** 5432; you must filter by peer/local IP, PID, and role rather than treating all port 5432 traffic as belonging to that JVM.

### 6.3. Correlating sockets with a process via lsof

~~~bash
lsof -nP -a -p "$PID" -iTCP
~~~

`-a` applies the intersection of conditions; `-p` restricts to the process, `-iTCP` selects TCP FDs, `-nP` disables DNS/service name lookups so the investigation is not slowed down. With insufficient privileges, results may be incomplete. `lsof` lists **still-open FDs**, whereas `ss` may show `TIME_WAIT` states that are no longer open FDs in the process; the two lists should not be expected to match 100%.

### 6.4. Reading the limits of the right process

~~~bash
grep -E "Max open files" "/proc/$PID/limits"
ls -1 "/proc/$PID/fd" | wc -l
prlimit --pid "$PID" --nofile
~~~

- `/proc/<PID>/limits` gives the soft/hard limits of the **process**.
- `/proc/<PID>/fd` contains symbolic links representing descriptors; the line count can change while listing and may be restricted by permissions. Some observation commands can also have a tiny impact or race with FDs opening/closing.
- `prlimit` can be used to view/adjust resource limits with appropriate privileges. **Here, use it only to inspect**, not to raise limits without a plan.
- `ulimit -n` in a new terminal is **not** proof that a Java service started by systemd/container has the same NOFILE.

Combine `lsof` and `ss` to determine whether open FDs are **sockets or files**, rather than inferring from the total FD count.

### 6.5. Viewing kernel snapshots while keeping the right scope

~~~bash
ss -s
ss -tin state established
sysctl net.core.somaxconn
sysctl net.ipv4.tcp_max_syn_backlog
sysctl net.ipv4.ip_local_port_range
~~~

- `ss -s` is a summary **within the current network namespace**, not process-specific.
- `ss -ti` can provide TCP details such as RTT and retransmission/congestion state depending on the kernel, but samples can change rapidly; avoid logging every socket under high load.
- `somaxconn` relates to the **accept backlog** limit; `tcp_max_syn_backlog` relates to pending SYN handling in Linux TCP. Neither is a parameter for “the maximum number of ESTABLISHED connections Java is allowed to use”.
- `ip_local_port_range` relates to **ephemeral local ports for outbound connections** in the network namespace under actual conditions; do not treat it as the “maximum number of clients” for an inbound server.

Do not blindly apply a `sysctl -w` value from a tutorial. You must identify the root cause, kernel version, actual load, container environment, rollback plan, and security/resource impact.

### 6.6. When suspecting a full backlog

If inbound connect latency is high and the service is still `LISTEN`ing but accept rate drops:

1. Compare the **inbound connect rate** at the proxy/client with Java's `accept_total`.
2. Check `ss -ltn` to see the listening queue and backlog at that moment.
3. Read Linux TCP extended counters related to listen drops/overflows via `nstat`/`netstat -s`, measuring **deltas over time**.
4. Check worker saturation, GC pauses, CPU quotas, scheduler delays, and accept errors due to FD exhaustion.
5. Distinguish the SYN stage from the fully-established accept queue; they are different bottlenecks.
6. If running behind a load balancer, queuing may occur at the proxy before reaching Java's kernel socket; investigate the proxy layer as well.

Kernel counters are often **aggregated** and may include multiple services. Do not conclude “Java port 8080 caused all TcpExtListenOverflows” from a single namespace-wide total.

## 7. Windows and macOS: Same Questions, Different Tools

### 7.1. Windows PowerShell

Windows does not have `/proc/<PID>/fd` or `RLIMIT_NOFILE` in the Linux sense. You can inspect TCP endpoints with PowerShell:

~~~powershell
$targetPid = 12345
Get-NetTCPConnection -OwningProcess $targetPid |
    Group-Object State |
    Select-Object Name, Count

Get-NetTCPConnection -OwningProcess $targetPid |
    Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess

Get-Process -Id $targetPid |
    Select-Object Id, ProcessName, HandleCount

netstat -ano
netsh int ipv4 show dynamicport tcp
~~~

**Do not blindly use PowerShell's `$PID` variable to refer to the Java process**: `$PID` is the PID of the **current PowerShell process**. Use `$targetPid` obtained from process management tools, JMX/JFR, or Task Manager.

A Windows process's `HandleCount` **is not a TCP socket count**. Handles include many types of kernel objects; permissions and the APIs for counting endpoints also differ from the Unix FD model. Do not directly compare the Unix MXBean's `getOpenFileDescriptorCount` metric with Windows `HandleCount` and apply the same thresholds.

`Get-NetTCPConnection` may require appropriate permissions and reflects TCP state at the time of observation. `netstat -ano` is a general fallback when the NetTCPIP module is unavailable; `netsh int ipv4 show dynamicport tcp` shows Windows's dynamic port range, **not how many free ports currently remain for each destination**.

### 7.2. macOS

Common tools:

~~~bash
PID=12345
lsof -nP -a -p "$PID" -iTCP
netstat -anv -p tcp
sysctl kern.maxfiles
sysctl kern.maxfilesperproc
ulimit -n
~~~

`lsof` filters by process and TCP; `netstat` can show all applications; `sysctl` displays macOS kernel limits. Shell `ulimit` still does not prove the limit of a service daemon started by launchd. You must verify the actual process, permissions, and runtime configuration.

### 7.3. Comparing tools does not mean comparing definitions

| Question | Linux | Windows | macOS |
| --- | --- | --- | --- |
| TCP sockets of a process | `lsof -p PID -iTCP` / `ss -p` | `Get-NetTCPConnection -OwningProcess` | `lsof -p PID -iTCP` |
| TCP states | `ss -tan` | `Get-NetTCPConnection`, `netstat -ano` | `netstat -anv -p tcp` |
| Process resources | `/proc/PID/limits`, `/proc/PID/fd` | Process handles and Windows resource counters | `lsof`, process limits, and `sysctl` |
| Dynamic local port range | `ip_local_port_range` | `netsh int ipv4/ipv6 show dynamicport tcp` | OS network sysctls per version |
| Java PID metrics | JMX/`UnixOperatingSystemMXBean` when supported | JMX and Windows-specific tools | JMX/`UnixOperatingSystemMXBean` when supported |

Do not standardize a dashboard into “fd_open” by mapping Windows `HandleCount` to the same definition without clearly documenting source, platform, and semantics.

## 8. JVM Metrics to Complete the Picture

### 8.1. `ManagementFactory` and MXBeans

Java 17 provides several Management Beans for observing the **JVM/process**:

~~~java
int liveThreads = ManagementFactory.getThreadMXBean().getThreadCount();
long heapUsed = ManagementFactory.getMemoryMXBean()
        .getHeapMemoryUsage().getUsed();

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
    System.out.println(pool.getName()
            + ": count=" + pool.getCount()
            + ", used=" + pool.getMemoryUsed());
}
~~~

This is a **Java fragment** requiring imports for `java.lang.management.ManagementFactory` and `BufferPoolMXBean`, not a standalone program. It can display buffer pools such as `direct` and `mapped` depending on the runtime. Do not treat `direct_buffer_used` as all **native memory** or kernel socket buffers; native memory regions, thread stacks, TLS, JIT, mapped files, and OS memory are accounted for differently.

### 8.2. Open FD metric from Unix MXBean

Measure the **JVM process** on supported platforms:

~~~java
var os = ManagementFactory.getOperatingSystemMXBean();

if (os instanceof com.sun.management.UnixOperatingSystemMXBean unix) {
    long open = unix.getOpenFileDescriptorCount();
    long max = unix.getMaxFileDescriptorCount();
    if (max > 0 && open >= 0) {
        double utilization = 100.0 * open / max;
        System.out.printf("FD use: %.1f%%%n", utilization);
    }
}
~~~

`open/max` helps detect approaching the limit, but does not tell you how many of those are TCP sockets or file descriptors. Combine it with `lsof`/OS tooling and observe the **trend after traffic subsides**. If open FDs keep climbing when application active connections return to baseline, suspect a file/socket/resource leak.

### 8.3. JVM threads and scheduler

A TCP server using a **one-blocking-worker-thread-per-connection** model can run out of threads/stack memory/CPU scheduling **before** running out of file descriptors. Conversely, NIO/Netty uses few selector threads for many connections; a small JVM thread count does not by itself mean the service is healthy. Observe thread count, executor queue, active handlers, blocked runnables, GC pauses, and socket buffer pressure.

Use `jcmd <pid> Thread.print` to inspect thread dumps when permitted. `jcmd` is part of the JDK diagnostic tools, requires matching version/permissions, has overhead, and can impact load; do not run it continuously every second in production.

### 8.4. GC and native memory

If an application has 5,000 connections with low heap usage while RSS/process memory keeps growing:

- Check **direct/mapped buffers** via `BufferPoolMXBean`; remember that the metric only reflects the corresponding pools.
- Check thread stacks, JIT/code cache, native libraries, and TLS/native allocations.
- On Linux, inspect OS socket memory/`ss -m` in context along with container accounting; kernel socket buffers cannot be measured by heap usage alone.
- JDK `jcmd <pid> VM.native_memory summary` requires the JVM to be started with **Native Memory Tracking (NMT)** appropriately enabled; do not assume the command always has data when NMT is off.
- Track down leaks using multiple signals rather than blaming “socket buffers” solely because RSS increased.

## 9. Complete Java 17+ Example: Two Inbound Connections, Four TCP Endpoints in the Same JVM

Demo goal: demonstrate by observation that **a single process can own more FDs/sockets than its server-side active connections metric**. The program creates a loopback `ServerSocket` on a random port, opens **two client Sockets within the same JVM**, accepts them as **two accepted server Sockets**, and holds the workers with a `CountDownLatch` so snapshots are reproducible.

- `LongAdder acceptedTotal` counts the total **accepts** in the demo.
- `AtomicInteger active` counts **server-side accepted sockets** not yet closed.
- The two client sockets in the same process are separate **outbound endpoints**; they **do not increment `active`**.
- The listening `ServerSocket` is also a separate resource.
- `osFdSnapshot(...)` prints the **actual FD count to stderr** on Unix-like JVMs supporting `UnixOperatingSystemMXBean`; on Windows it prints an unavailable message.
- The program prints **deterministic results to stdout**, while FD counts vary by JDK/OS/libraries and go to stderr so as not to claim an absolute number.
- Only when main lets the workers finish do the accepted sockets close and the gauge return to 0; the client sockets are closed by `try-with-resources`.

Save as **SocketMetricCorrelationDemo.java**:

~~~java
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.LongAdder;

public class SocketMetricCorrelationDemo {
    static void osFdSnapshot(String point) {
        OperatingSystemMXBean bean =
                ManagementFactory.getOperatingSystemMXBean();

        if (bean instanceof
                com.sun.management.UnixOperatingSystemMXBean unix) {
            System.err.println("OS [" + point + "]: open_fd="
                    + unix.getOpenFileDescriptorCount()
                    + ", max_fd=" + unix.getMaxFileDescriptorCount());
        } else {
            System.err.println("OS [" + point
                    + "]: Unix FD MXBean unavailable");
        }
    }

    static void process(
            Socket peer, CountDownLatch finishWork,
            AtomicInteger active, CountDownLatch finished,
            AtomicReference<Throwable> failure) {

        try (peer) {
            if (!finishWork.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker wait expired");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            failure.compareAndSet(null, e);
        } catch (IOException | RuntimeException e) {
            failure.compareAndSet(null, e);
        } finally {
            active.decrementAndGet();
            finished.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress host =
                InetAddress.getByName("127.0.0.1");
        ExecutorService workers =
                Executors.newFixedThreadPool(2);

        AtomicInteger active = new AtomicInteger();
        LongAdder acceptedTotal = new LongAdder();
        CountDownLatch acceptedReady = new CountDownLatch(2);
        CountDownLatch finishWork = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(2);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        try (ServerSocket listener =
                     new ServerSocket(0, 8, host)) {

            Thread acceptor = new Thread(() -> {
                try {
                    for (int i = 0; i < 2; i++) {
                        Socket peer = listener.accept();
                        try {
                            workers.execute(() -> process(
                                    peer, finishWork,
                                    active, finished, failure));
                            acceptedTotal.increment();
                            active.incrementAndGet();
                            acceptedReady.countDown();
                        } catch (RejectedExecutionException rejected) {
                            peer.close();
                            throw rejected;
                        }
                    }
                } catch (Exception error) {
                    failure.compareAndSet(null, error);
                }
            }, "tcp-acceptor");
            acceptor.start();

            try (Socket clientA =
                         new Socket(host, listener.getLocalPort());
                 Socket clientB =
                         new Socket(host, listener.getLocalPort())) {

                if (!acceptedReady.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Accept timeout");
                }

                System.out.println("app.accepted_total="
                        + acceptedTotal.sum());
                System.out.println("app.active_server_connections="
                        + active.get());
                System.out.println("app.local_client_sockets=2");

                // FD values vary by OS/JVM; print to stderr.
                osFdSnapshot("connections-open");

                // Let handlers close accepted sockets.
                finishWork.countDown();
                if (!finished.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Worker finish timeout");
                }

                System.out.println(
                        "app.active_server_connections_after_close="
                        + active.get());
                osFdSnapshot("accepted-closed");
            }

            acceptor.join(5000);
            if (acceptor.isAlive()) {
                throw new IllegalStateException(
                        "Acceptor did not exit");
            }
            if (failure.get() != null) {
                throw new IllegalStateException(
                        "Server task failed", failure.get());
            }
        } finally {
            finishWork.countDown();
            workers.shutdown();
            if (!workers.awaitTermination(5, TimeUnit.SECONDS)) {
                workers.shutdownNow();
                throw new IllegalStateException(
                        "Worker pool did not stop");
            }
        }

        System.out.println("workers.terminated="
                + workers.isTerminated());
    }
}
~~~

Run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 SocketMetricCorrelationDemo.java
java SocketMetricCorrelationDemo
~~~

**Stdout verified with Java 17 JShell:**

~~~text
app.accepted_total=2
app.active_server_connections=2
app.local_client_sockets=2
app.active_server_connections_after_close=0
workers.terminated=true
~~~

**Stderr is OS-dependent and has no fixed numbers.** On Unix-like JVMs supporting the extension, it looks like:

~~~text
OS [connections-open]: open_fd=<actual value>, max_fd=<limit>
OS [accepted-closed]: open_fd=<actual value>, max_fd=<limit>
~~~

On JVMs/OSes without extension support (for example, possibly on Windows), stderr will print:

~~~text
OS [connections-open]: Unix FD MXBean unavailable
OS [accepted-closed]: Unix FD MXBean unavailable
~~~

### 9.1. Interpreting correctly instead of chasing a “matching” number

- `accepted_total=2`: the app accepted **two** server-side TCP connections.
- `active_server_connections=2`: two accepted sockets are still within the handlers' lifecycle.
- `local_client_sockets=2`: this JVM also owns **two client sockets** — do not add them to the server-side gauge.
- The listening `ServerSocket` is also open. If OS tools are run at the right moment during the demo, both the listener and the endpoints on both sides of the loopback are visible.
- `active_server_connections_after_close=0`: the handlers have closed the accepted sockets and the gauge is back to 0, yet **the two client sockets and the listener are still open** at the time of `osFdSnapshot("accepted-closed")`. Thus, total process FDs **do not have to be 0** or decrease by exactly 2, because the runtime may also be managing other resources.
- `workers.terminated=true`: the executor stopped after the handlers. This does not mean kernel `TIME_WAIT` entries vanish immediately.

**Important:** `ss` on Linux or `Get-NetTCPConnection` on Windows must be run **while the server is holding the sockets open** if you want to capture an `ESTABLISHED` snapshot. The demo uses latches, so the capture window can be quite short; to observe directly from a terminal, you can add a manual wait **only in a lab**. Do not add an indefinite sleep to a production server.

### 9.2. Why does the demo use Java app metrics + OS FD metrics?

The application knows accurately **how many inbound accepted sockets it owns at the business level**, but it does not know every internal FD created by the JDK, TLS provider, file logger, selector, or native libraries. OS/JMX process counters look at a lower layer. **Combining both views** is what lets you spot a broken app gauge, a socket leak, or a limit set too low.

Observing only an `active` metric without looking at `close`/FD/TCP states easily misses leaks. Yet observing only FDs makes it hard to tell which are the application's DB connections or WebSockets.

## 10. Backlog, Listen Queue, and SYN Queue: Do Not Confuse with Active Connections

### 10.1. `ServerSocket(backlog)` is only a hint

~~~java
ServerSocket server = new ServerSocket(
        8080, 128, InetAddress.getByName("0.0.0.0"));
~~~

This is a **Java fragment**; the port may already be occupied, and close/trust controls are needed. The `backlog=128` parameter suggests the queue length for incoming connections, but the actual value may be adjusted/capped by the OS and implementation. It does **not** mean “Java allows at most 128 ESTABLISHED connections”.

In modern Linux, the accept queue for connections that have completed the handshake and the SYN queue for half-open connections are two distinct concepts; tuning can depend on `somaxconn`, `tcp_max_syn_backlog`, and SYN cookies configuration. Do not assume every OS or Linux kernel version implements them identically.

### 10.2. Diagnosing accept queue saturation

If the app's `active_connections` is low while connect latency increases:

- Read `ss -ltn` Recv-Q/Send-Q and the listener port.
- Check whether the acceptor is blocked by running business logic directly on the accept thread.
- Check running thread count, executor queue, GC pauses, and CPU throttling.
- Check for resource exhaustion such as `EMFILE` causing `accept()` to fail.
- Compare TCP listen overflow/drop **deltas** alongside connection attempt frequency.
- Inspect the proxy/ingress queue, not just the kernel listener.
- Do not just increase backlog while ignoring why the accept loop is slow.

### 10.3. Clients failing to reach the server can be purely a network issue

Rising `SYN_SENT` on the client without corresponding SYNs on the server can point to firewall/routing/NAT; a server in `LISTEN` with an empty backlog does not guarantee that DNS, security groups, LB health, or TLS handshakes are all healthy. No single Java metric proves that packets actually reach the right node.

## 11. Ephemeral Ports and TIME_WAIT: The Trap When an Outbound Client Opens Connections Too Fast

### 11.1. What is a local ephemeral port?

When a Java client calls:

~~~java
Socket socket = new Socket("example.test", 443);
~~~

without choosing a specific local port, the OS typically picks an **ephemeral local port** from a configured range. Each TCP connection is identified by the tuple (protocol, local IP, local port, remote IP, remote port). The effective limit on outbound connections depends on **tuples, local addresses, destination distribution, NAT, kernel reuse rules, and other resources**, not simply taking the port range size as “maximum total connections”.

### 11.2. Symptoms and diagnosis

If a JVM opens and closes thousands of outbound TCP connections per second to **a single destination**:

- `connect_failures` rate and latency increase.
- TCP `TIME_WAIT` may rise on the side that actively closes.
- When no local port/tuple is available, the application may receive `BindException`/`ConnectException` with a message like `Cannot assign requested address` depending on OS/JDK.
- FD usage may **not be high** once sockets are closed while the kernel holds `TIME_WAIT`, so do not conclude “low FD => unrelated to socket churn”.
- A NAT gateway or proxy may have its own port limits and cause errors even when the local JVM still has plenty of resources.

**Preferred solution:** reuse HTTP connections via a client pool/keep-alive, pace request concurrency, reduce retry storms, use backoff+jitter, and consider multiple endpoints by design. Do not rush to tune `tcp_tw_reuse` or disable `TIME_WAIT` without understanding TCP guarantees and kernel/version risks.

### 11.3. The inbound server side

A server listening on `0.0.0.0:8080` can serve very many clients simultaneously because TCP connections differ in their remote tuple; the ephemeral local port range **is not directly a ceiling on inbound connections on port 8080**. Real limits lie in FDs, memory, CPU, threads, protocol, accept/backlog, and infrastructure.

## 12. Buffers and Memory: Low Heap Does Not Prove Healthy Sockets

### 12.1. Kernel send/receive queues

When Java calls `OutputStream.write`/`SocketChannel.write`, data may enter kernel buffers; the syscall result or `CompletionStage` does not by itself prove the peer has processed the business message. If the peer reads slowly, the send queue and memory can grow. `ss -tin`/`ss -m` on Linux can provide per-socket information (depending on permissions/kernel).

When the client sends faster than the server reads, the receive queue can grow; if the application does not consume fast enough, kernel window/backpressure can affect throughput. If the application also buffers payloads on the heap or in direct buffers, **pressure can exist across multiple layers simultaneously**.

### 12.2. Java direct buffers differ from TCP buffers

`ByteBuffer.allocateDirect(...)` allocates a direct buffer outside the regular Java heap. `BufferPoolMXBean` can report some JVM pools, whereas kernel TCP socket buffers are not necessarily counted in the same counter. Do not add `direct_buffer_used + socket_rcvbuf_size` and call it exact RSS: configured buffer sizes are not the actual bytes currently in use, and memory accounting depends on the OS/runtime.

### 12.3. Comparing memory/container metrics

If the service runs in a container, inspect container memory limit/working set/OOM events (cgroup or platform metrics), JVM heap usage, native buffers, and kernel socket memory with the appropriate tools. A process can be OOM-killed even with headroom under `-Xmx` because of total RSS/native/mapped/threads and container policies.

## 13. Data Must Share the Same Timestamp and Scope

Suppose a dashboard scrapes `net_active_server_connections` every 60 seconds, while an engineer runs `ss` right during a 10-second peak. Discrepancies can be caused by **sampling**, not a bug.

Correlation procedure:

1. Identify the **PID/JVM process start time** to avoid confusing a new process after a restart; PIDs can be reused.
2. Record the **UTC timestamp** and timezone at each snapshot.
3. Confirm the **network namespace, container/pod/node, IP, port, and protocol**.
4. Capture **app metric gauges/counters + process FDs + TCP states** within the same few seconds if possible.
5. Group by **role**: listening, inbound accepted, outbound client, proxy-to-backend, Unix-domain sockets.
6. For counters, measure **deltas/rates** over a stable interval; do not compare a cumulative counter against an instantaneous gauge.
7. Segment by deployment version, workload, request arrival rate, keep-alive/connection pooling, and proxy routing.
8. Only conclude there is a leak if you observe **systematic cumulative growth** that does not return to baseline after the workload stops, and identify which resource is not being closed.

### 13.1. There is no simple subtraction that is always true

A misleading formula:

~~~text
OS ESTABLISHED - app active requests = leaked connections  (WRONG)
~~~

Reason: idle keep-alive, HTTP/2 multiplexing, WebSockets, inbound/outbound in the same process, proxy connections, and differing scopes all inflate the left-hand side without any leak. Instead:

~~~text
App active sockets (specifically defined)
  -> compare with OS open TCP FDs for SAME PID + role
  -> compare with FD total and limit
  -> cross-check TCP states and historical trends
  -> inspect ownership and close paths when anomalies persist
~~~

You can use an internal invariant check such as `accepted_total - closed_total ≈ active_connections` **only if** the accepted/closed counters share the same definition, every accept/reject/close path is fully instrumented, and you are evaluating the same process uptime. When the app restarts, counters reset; when events are measured asynchronously, discrepancies can appear. A gauge directly measuring active sockets can be more reliable than subtracting counters that may miss events.

## 14. Diagnostic Table from Metrics to Possible Causes

| Concurrent observations | Primary hypothesis | Verification steps |
| --- | --- | --- |
| `open_fd` rising near process NOFILE; `lsof` shows many TCP sockets | Pool/socket leak or load exceeding design | Identify socket types, owners, close paths, conn pool |
| `open_fd` rising while TCP sockets remain stable | Non-TCP file/pipe/resource leak | Inspect `lsof -p` across all FD categories |
| `CLOSE_WAIT` for PID rising, close counter low | Local app not closing after peer FIN | Thread dump, try-with-resources, cancellation cleanup |
| High `TIME_WAIT`, low process FDs | Connection churn, active close, retry storm | Outbound connect rate, pooling, destinations |
| High `SYN_SENT` on client | Connect path/timeout/firewall/slow destination | DNS, route, peer listener, LB/proxy, timeouts |
| Still `LISTEN`ing but accept queue full | Slow acceptor, FD errors, burst | `ss -ltn`, accept rate, listen drops, executor |
| Request queue high while TCP count stable | Application handler/DB bottleneck | Worker saturation, lock/DB latencies |
| High `ESTABLISHED`, low active requests | Idle keep-alive/WebSocket/pooling | Classify sockets by protocol/role, idle timeout |
| High connect failures, ephemeral ports/single destination stressed | Outbound tuple/port exhaustion or NAT limit | Port ranges, TIME_WAIT, NAT/proxy metrics |
| Low heap, high process RSS | Direct buffers/native/thread/kernel accounting | BufferPoolMXBean, NMT, OS memory and queues |
| Socket send queues growing, low CPU | Slow consumers/network bottleneck | `ss -ti/-m`, client read rates, backpressure |
| TCP retransmissions rising on host | Network loss/congestion or slow remote | Per-socket details, NIC, routes; do not blame one PID hastily |

The table above offers **hypotheses**, not definitive diagnoses. Always verify with same-scope data and controlled experiments.

## 15. Designing Meaningful Dashboards and Alerts

A proper dashboard for a Java network service should place **the layers side by side**, rather than collapsing them into a mysterious “health score”:

- **Application:** active/accepted/closed/rejected connections, request arrival rate, concurrent requests, p95/p99 latency, error rates, request/worker queues, connection-pool active/idle/pending, network bytes.
- **JVM process:** process open FD/max (when supported), JVM thread count, heap/direct buffer usage, GC pauses, CPU, process RSS if measurable.
- **OS/network:** TCP states by port/namespace, `LISTEN` accept queue, retransmissions, TCP resets, ephemeral port distribution, soft/hard resource limits, socket buffer pressure.
- **Infrastructure:** pod readiness/restarts/OOM, ingress/LB connection failures, connection draining, NAT/egress limits, upstream health.

### 15.1. Alert on trends and ratios, not a fixed number

For example, a “high FD utilization” alert can evaluate `open_fd / max_fd` rising near the ceiling **together with connect/accept errors**; actual thresholds require baselines, sustained duration, growth rate, and environment context. There is no single 80% threshold that fits every Java process.

`CLOSE_WAIT` rising continuously after traffic drops is a stronger investigation signal than a single snapshot. High `TIME_WAIT` that is short-lived after a burst can be normal. A `SYN_RECV` spike during sudden load needs to be evaluated alongside listen drops, rate limits, and the network.

### 15.2. Metric labels that avoid cardinality explosion

Use `direction=inbound/outbound`, `protocol=tcp/http/websocket`, `route=/users/{id}`, `status_class=2xx/5xx`, `instance_id`. Do not add client IP, socket 4-tuple, tokens, or request IDs as Prometheus labels for every connection; detailed info belongs in redacted logs/traces.

### 15.3. Rate sampling and correlation

If a system handles 500 connects/s, a once-per-minute TCP snapshot can miss short-lived `SYN_SENT` states. Use counters/rates for connects/errors and OS sampling at an interval suited to the load. For brief incidents, JFR, traces, packet captures under security policy, or network observability can help; **packet captures can contain sensitive data** and must be restricted and access-controlled.

## 16. Investigation Playbook from Symptom to Conclusion

### Scenario A — `Too many open files` when opening a new connection

1. Get the exact PID and the process's soft/hard NOFILE limits.
2. Measure the JVM's `open_fd`, trend, and FD types via `lsof` or `/proc/PID/fd`.
3. Count TCP sockets by state and role; do not look only at `ESTABLISHED`.
4. Compare app active/accepted/closed; look for unclosed sockets, log files, selectors/pipes, or unreleased pools.
5. Fix the leak source or concurrency limit; only raise NOFILE when capacity planning confirms headroom in memory/CPU.
6. Retest under steady load and verify FDs return to baseline after connections close.

### Scenario B — `CLOSE_WAIT` rises after mobile users lose connectivity

The peer actively sent FIN, and the application has not finished closing. Suspect handlers holding `InputStream`, connection pools not releasing responses, or callbacks skipping close. Check the sockets' process PID, lifecycle code, and `closed_total` metrics. Use `try-with-resources`, close in `finally`, and ensure cancellation/timeouts also clean up. Do not eliminate `CLOSE_WAIT` by increasing `somaxconn`.

### Scenario C — High `TIME_WAIT` after every deployment scale-out

Clients are continuously opening new TCP connections to the same upstream. Compare connect attempts/s, retries, pool reuse, DNS/proxy routing, and `TIME_WAIT` distribution. If `open_fd` is not high while outbound connects fail, suspect ephemeral port/NAT constraints or retry storms. Fix pooling/backoff and session reuse before changing kernel tuning.

### Scenario D — Only one HTTP route times out, TCP ESTABLISHED is normal

Requests reach the server and sockets are available, but the route is stuck on a DB/lock/upstream service. TCP states help little in finding the cause; focus on `request_duration`, `executor_queued_tasks`, active workers, thread dumps, and dependency latency. Do not add FDs or change port ranges when the bottleneck is in business logic.

### Scenario E — Proxy reports 502/504, Java active=0

Do not jump to the conclusion that the app is not receiving requests. A proxy timeout/connect failure may occur **before** the request reaches the handler, or metrics may be collected from a different instance/PID. Compare proxy access/upstream metrics, target endpoints, readiness, `LISTEN`, accept errors, network namespace, and timestamps. If the app restarted between two measurements, cumulative counters have reset.

### Scenario F — Server sees 1,000 ESTABLISHED but 20 active HTTP requests

There may be 980 idle keep-alive connections, WebSocket sessions, or HTTP/2 multiplexing. Measure pool idle/active counts, connection hold times, OS socket owner, and protocol. Do not call the remaining 980 connections a leak until you confirm they should have been closed.

### Scenario G — Raised `ulimit -n` in terminal but the service still errors

If the service is run by systemd or a container, an interactive shell's `ulimit` does not change the limit of the running process. Check `/proc/<JVM_PID>/limits`/service manager/runtime; update the launch configuration in the right place, perform a controlled restart, and re-measure. Do not change limits in production without a rollback/capacity check.

### Scenario H — Windows app has 12,000 handles but only 800 TCP connections

`HandleCount` includes many object types; it is not the number of TCP endpoints. Use `Get-NetTCPConnection -OwningProcess` to filter by TCP state and owner, combined with appropriate Windows performance/debugging tools. Do not apply a Unix `RLIMIT_NOFILE` assumption to Windows.

### Scenario I — JVM heap is stable, host is under memory pressure

Check direct/mapped buffers, thread stacks, JVM native memory, page cache, kernel socket memory, cgroup accounting, and buffer/queue counts. `BufferPoolMXBean` does not cover all native/kernel memory; correlate process RSS/container working set and OS counters.

### Scenario J — Server is `LISTEN`ing but fails to absorb a connection burst

Check acceptor scheduling, FD limit, executor saturation, listen queue, SYN backlog, proxy/NAT, and listen drops. `backlog=128` is a hint/queue limit for pending connects, not max active sessions; increasing backlog can help after proving an actual burst, but will not fix a deadlocked accept loop.

## 17. Knowledge Exercises and Solutions

### Exercise 1 — App active is 50, OS sees 100 ESTABLISHED

The same JVM opens 50 outbound loopback client sockets and accepts 50 inbound sockets. Is `active_server_connections=50` wrong?

**Answer:** not necessarily. Each TCP connection has **two endpoints**, and because the same JVM owns both sides, the OS can list around 100 established endpoints; the server-side gauge only counts the accepted side. Additionally, the listener and non-TCP FDs can make the process open FD count even larger.

### Exercise 2 — Accept counter keeps rising, active stays flat

`net_accept_total` goes from 1 million to 2 million in one day, while `net_active_server_connections` stays around 200.

**Answer:** this can be completely normal. A counter is the **total number of accepts over time**, whereas a gauge is the **number of currently open connections** at a given moment. Measure rates and close counts rather than comparing the two absolute numbers.

### Exercise 3 — `CLOSE_WAIT` rises, TIME_WAIT is low

In the same JVM, `CLOSE_WAIT` rises from 10 to 1,000 after clients disconnect, and the app active gauge does not drop.

**Answer:** suspect that the close/cleanup path is not running or the gauge is wrong; verify the process owner, stack traces, and resource lifecycle. Do not draw a final conclusion from just two numbers, but this is a strong signal to check `Socket.close()`/`try-with-resources`.

### Exercise 4 — `TIME_WAIT` is 20,000, open_fd is only 300

Can both numbers be true at the same time?

**Answer:** yes. Many `TIME_WAIT` entries can remain in the kernel after the process has closed its FDs, or they may belong to other processes in the namespace. An aggregated `ss -s` is not a per-PID FD count. Look for churn/active closes and scope mismatches.

### Exercise 5 — `ulimit -n` = 65535, Java PID has soft limit 1024

Why does the application still get “Too many open files”?

**Answer:** the shell you checked and the Java process have different launch contexts. The effective limit belongs to the PID; check `/proc/PID/limits` and the systemd/container runtime. Do not trust shell `ulimit` as a JVM metric.

### Exercise 6 — `somaxconn` increased, yet DB queue remains high

Why did increasing the accept backlog not make requests faster?

**Answer:** the backlog only affects the pending connection queue, whereas the bottleneck is in business logic/DB/executor. You must measure request/queue duration, dependency latency, and concurrency before changing kernel tuning.

### Exercise 7 — Outbound port range has 30,000 ports

Does that mean the server supports at most 30,000 inbound clients?

**Answer:** no. The ephemeral local port range affects local port selection for outbound connections and tuple reuse; an inbound server on a listening port can serve many remote tuples. Practical limits also include FDs, CPU, RAM, brokers, queues, and the network.

### Exercise 8 — Windows `HandleCount` and Unix FDs

Can Windows `HandleCount` be normalized into the same `jvm_fd_open` metric as Linux with a 90% NOFILE alert?

**Answer:** no, not without proper definitions. Windows handles and Unix FDs have different types/limits; distinguish metric source/platform and use OS-specific capacity/diagnostics.

### Exercise 9 — Same server hosts WebSocket and REST

Metric `http_requests_in_flight=0` while `ss` shows 5,000 ESTABLISHED. Is there a bug?

**Answer:** not necessarily. WebSockets can keep connections open for a long time even when no HTTP request is being processed, and keep-alive sockets can also be idle. Separate metrics for active WebSocket sessions/idle pools are needed.

### Exercise 10 — FD usage does not rise, yet connect timeouts increase

Which layers should be checked next?

**Answer:** DNS, routing/firewall, peer SYN backlog/accept queue, outbound ephemeral ports/NAT, TLS handshake, proxy, upstream service, and rate limiters. Low process FDs do not rule out network path errors or `TIME_WAIT` churn.

### Exercise 11 — Two different values observed 20 seconds apart

App gauge is 100 at 10:00:00; `ss` reports 400 at 10:00:20, and the server just received a burst of 2,000 connections.

**Answer:** this may be a sampling or scope mismatch. Re-capture at the same timestamp with PID/ports/role, recording both rates and workload bursts; do not claim the gauge is mis-instrumented based solely on two snapshots taken at different times.

### Exercise 12 — JVM RSS grows while direct buffer MXBean is stable

Can it still be a native/kernel memory issue?

**Answer:** yes. Thread stacks, native libraries, memory mapping, allocator overhead, and kernel socket buffers do not necessarily appear in `BufferPoolMXBean`. Check OS/cgroup memory, NMT if enabled, and socket memory metrics.

## 18. Investigation and Observability Standardization Checklist

- [ ] Have I identified the **exact PID/instance/container**, timestamp, IP/port, IPv4/IPv6, and inbound/outbound direction?
- [ ] Do I distinguish counters, gauges, and histograms, and avoid comparing totals with instantaneous values?
- [ ] Is the active server connections metric incremented/decremented along the **socket lifecycle**, rather than confused with active HTTP requests?
- [ ] Do I understand how HTTP keep-alive/HTTP2/WebSocket cause request counts to differ from socket counts?
- [ ] Have I checked `LISTEN`, `ESTABLISHED`, `CLOSE_WAIT`, `TIME_WAIT`, and the counting scope?
- [ ] Do I know that `CLOSE_WAIT` can suggest a leak when growing persistently, whereas `TIME_WAIT` usually reflects churn?
- [ ] Have I checked process open FDs and **process soft/hard limits**, not just shell `ulimit`?
- [ ] If on Windows, am I using Windows handle/TCP tooling rather than assuming Unix FDs?
- [ ] Have I classified FDs into TCP sockets, logs, pipes, files, or other types?
- [ ] Am I avoiding treating namespace-wide `ss -s`/kernel counters as per-PID metrics?
- [ ] Have I checked the accept queue, SYN backlog, connect/accept errors, and thread scheduling when connects are slow?
- [ ] Do I distinguish ephemeral port range (outbound) from inbound connection capacity?
- [ ] Have I checked retries, connection pooling, `TIME_WAIT`, and NAT/proxy limits when outbound connects fail?
- [ ] Have I checked direct buffers, JVM threads, GC, and OS socket memory when heap does not explain RSS?
- [ ] Did I capture snapshots at the same time and check whether the instance restarted or counters reset?
- [ ] Have I avoided high-cardinality metric labels such as user ID, IP, and socket four-tuple?
- [ ] Do I have error rates, queue depth, p95/p99 latency, and active gauges alongside OS resource metrics?
- [ ] Do I only raise kernel/process limits after identifying the root cause and doing capacity planning?
- [ ] Do I know how to reproduce via load tests, evaluate baseline after stopping traffic, and check for leaks?
- [ ] Can I distinguish proxy/LB/host/container/process and avoid blaming the wrong layer?

**Conclusion:** For reliable Java networking observability, read **all three layers together**: (1) **application** with accept/close/active requests, pools, queues, errors, and latency; (2) **JVM process** with threads/heap/direct buffers/open file descriptors; (3) **operating system** with TCP states, backlog, ephemeral ports, socket buffers, and resource limits. There is no simple equality “active requests = ESTABLISHED = FDs”. A discrepancy is only meaningful when you pin down the **PID, connection direction, socket ownership, protocol, container namespace, and timestamp**. Drawing conclusions after combining **trend + scope + state + errors** prevents raising limits in the wrong place and helps pinpoint socket leaks, client churn, or backlog bottlenecks accurately.

## 19. References

- **Oracle Java 17 — ManagementFactory:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html
- **Oracle Java 17 — UnixOperatingSystemMXBean:** https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/UnixOperatingSystemMXBean.html
- **Oracle Java 17 — BufferPoolMXBean:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html
- **Oracle Java 17 — ServerSocket:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- **Oracle Java 17 — Socket:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- **Linux manual — ss(8):** https://man7.org/linux/man-pages/man8/ss.8.html
- **Linux manual — proc_pid_limits(5):** https://man7.org/linux/man-pages/man5/proc_pid_limits.5.html
- **Microsoft Learn — Get-NetTCPConnection:** https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-nettcpconnection
- **Prometheus — Metric and label naming:** https://prometheus.io/docs/practices/naming/

OS limit/counter values depend on distribution/kernel, JVM, and deployment model (VM, container, systemd, Windows service). When applying them, check the documentation for the actual version and do not treat numbers from a lab machine as universal production thresholds.