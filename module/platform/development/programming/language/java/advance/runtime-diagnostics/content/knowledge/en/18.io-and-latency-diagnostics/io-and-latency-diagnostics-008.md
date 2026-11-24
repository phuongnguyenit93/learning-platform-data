# 18.8 What the JVM Can Observe vs. Evidence Needed from the OS or External Services

## Learning objectives

An 800 ms Java request does not mean the JVM performed 800 ms of work. A 400 ms `jdk.SocketRead` event does not mean the network spent 400 ms transmitting data. A `FileWrite` returning successfully does not prove data was durably persisted to disk. Conversely, seeing no I/O events in JFR **does not** prove the application is not waiting on I/O.

This lesson establishes **the observability boundary** between the JVM, the operating system, networks/storage, and external services. The goal is to know what can be concluded directly from JVM data, what remains a hypothesis, and where to gather additional evidence—especially during **I/O and latency** investigations.

After this lesson, you will be able to:

1. Distinguish Java/JVM I/O events, application spans, OS/kernel counters, network measurements, and server-side telemetry.
2. Explain why socket read/write duration, file I/O duration, thread states, and CPU metrics do not equal network RTT, disk latency, or database execution time.
3. Recognize blind spots caused by NIO/asynchronous I/O, connection pools, DNS, TLS, proxies, retries, kernel buffers, storage caches, cgroups, and JFR thresholds.
4. Collect timestamped evidence from Linux/containers and dependent services in a targeted, safe manner.
5. Align timelines by trace/request ID and evaluate competing hypotheses before concluding root cause.
6. Write an investigation record with explicit observation boundaries instead of vaguely saying "I/O is slow."

Example scope: Java 17+ on HotSpot/OpenJDK, Java Flight Recorder (JFR) and Java Mission Control (JMC), Linux/cgroup v2, along with systems involving HTTP/gRPC, databases, or storage. Exact visibility depends on JVM vendor/version, OS, container runtime, network stack, application libraries, and event settings. Linux commands are **conditional investigative tools**—not every environment has them installed or grants permission to run them.

## 1. A request crosses multiple responsibility domains

Suppose a Java service receives a request, fetches data from a database, and returns an HTTP response:

~~~text
Client
  |
  | Internet / DNS / TLS
  v
Ingress / Load Balancer / Reverse Proxy
  |
  | Route, queue, retries, connection
  v
Java service
  |-- HTTP server accept / parse / dispatch
  |-- Executor queue / connection pool wait
  |-- Java business code
  |-- JDBC / HTTP client / TLS / socket I/O
  |        |
  |        v
  |    OS kernel / TCP / network / proxy
  |        |
  |        v
  |    Database / remote service / storage
  |        |
  |        v
  |    Remote CPU, locks, disk, cache, queue
  |-- Response encoding / socket write
  v
Proxy / network / end user
~~~

There are at least **four vantage points**:

- **Application/JVM:** method calls, Java thread stacks, Java-visible I/O operations, GC/JIT, heap, instrumented client/server spans.
- **OS/kernel/container:** CPU scheduling, run queues, TCP state/retransmissions/RTT estimates, socket buffers, file descriptors, process I/O counters, block-device queues, cgroup limits, and pressure stalls.
- **Intermediate infrastructure:** DNS resolvers, service meshes, load balancers, TLS termination, sidecar proxies, NAT, packet loss, rate limiting, and network policies.
- **Remote dependency:** connection queues, server thread pools, query execution/locks, storage IOPS, downstream retries, throttling, and competing tenants.

One symptom is often **observed across multiple domains**, yet only certain sources sit close enough to the mechanism to explain why it happened. JFR can detect a Java thread waiting on a socket; knowing whether it is **waiting for the database to run a query**, **packet loss**, or **an upstream queue** requires data from external domains.

**Core principle:** "Where I observed the wait" is not automatically "what caused the delay."

## 2. What the JVM can observe directly

### 2.1. JFR socket and file I/O events

Common JFR event names on HotSpot:

| Event | What it shows when enabled/recorded | What it does NOT prove by itself |
| --- | --- | --- |
| jdk.SocketRead | Duration of an instrumented socket read, endpoint/address/port, bytes, and thread/stack if present | Network RTT, server processing time, every packet, every async read |
| jdk.SocketWrite | Duration of an instrumented socket write and bytes written per event semantics | That data arrived/was ACKed at destination, or remote service processed it |
| jdk.FileRead | Duration of a Java-visible file read, path/bytes when present | That every byte hit physical disk, or exact device service time |
| jdk.FileWrite | Duration of a Java-visible file write | That data was `fsync`ed or durably stored, or actual device flush latency |
| jdk.JavaMonitorEnter / jdk.ThreadPark | Certain monitor contention / park situations in the JVM if captured | Every kind of queue, OS/scheduler wait time, or network wait |
| jdk.CPULoad / jdk.ThreadCPULoad | JVM/thread CPU usage signals across capture intervals | CPU throttling, every I/O wait cause, packet loss |
| jdk.GarbageCollection and GC phases | GC activity in the JVM to correlate pauses/pressure with requests | That every latency window is caused by GC or every I/O event is a network fault |

**Events must be enabled and satisfy capture conditions**: thresholds, periods, `stackTrace`, durations, recording windows, and retained data. Short I/O events may not appear if thresholds are non-zero. "Default" thresholds can differ across `.jfc` configs, JDKs, and views; **inspect the active configuration** rather than hard-coding one threshold for all environments.

With `SocketRead`, a long event may represent the time a thread spent **waiting for data to arrive** on the receiving side. That span can combine server query execution, transit time, kernel waits, and scheduling—insufficient to split each component apart.

With `SocketWrite`, returning from write usually means only that the buffer was **accepted at the corresponding I/O layer**; the kernel can buffer it, TLS/client libraries may process further, and the network may not have delivered it to the remote application yet. A fast write does not prove a fast end-to-end response.

### 2.2. Thread dumps, stacks, and JVM runtime metrics

JVM data also provides:
- Java thread states (`RUNNABLE`/`BLOCKED`/`WAITING`/`TIMED_WAITING`), stack traces, and lock ownership as visible to the JVM.
- GC logs, safepoints, heap/JFR, CPU sampling, and classloading/JIT evidence.
- Application-level timers, OpenTelemetry spans, JMX pool metrics, HTTP client metrics, logs with trace/request IDs.
- Executor/connection-pool counts and timings if the library exports telemetry.

Yet `java.lang.Thread.State.RUNNABLE` **does not equal** an OS thread continuously burning CPU: a thread may sit in a native call or wait on kernel I/O. `WAITING` does not pinpoint an external resource cause without stacks and pool context. A thread dump is a **snapshot**, whereas tail latency problems usually require time series.

### 2.3. JFR coverage is not uniform across all I/O APIs

Seeing an event name in documentation does not guarantee every I/O path emits that event. Non-blocking frameworks, NIO selectors, native transports, asynchronous file channels, JNI, TLS libraries, and RPC stacks use different mechanisms. At lower layers, one logical HTTP request can map to many socket reads/writes; conversely, many requests can share one HTTP/2 connection.

For example, a non-blocking client shows a 900 ms request span yet no `jdk.SocketRead` appears on the request thread. This **does not prove there was no network I/O**: the request may have waited in a connection pool/queue or run on a different event-loop thread, and JFR may not instrument that exact operation.

**When comparing JFR and application traces, align levels:** request → logical RPC → connection acquisition → write → server wait → read → deserialize. Never pin a single socket event onto a whole request without correlating traces and connection reuse.

## 3. Five types of time you must keep distinct

### 3.1. End-to-end latency

From when the client initiates a request until it receives the full response. It can include DNS, TCP/TLS, proxy queues, the Java service, remote dependencies, data transfer, and client rendering. A single JFR file from the Java service **cannot** observe both ends.

### 3.2. Application server span

Measured inside the Java service from request receipt until writing/completing the response per instrumentation rules. Does not necessarily include load-balancer queuing or data sitting in the kernel accept queue before a handler starts. For async responses, verify when the span ends.

### 3.3. Client call span

Measures an `HttpClient`/JDBC/gRPC client operation at the application layer. It can include: connection pool wait, DNS, proxy resolution, TCP connect, TLS handshake, write, server processing, read, retries/backoff, and decoding. Seeing 400 ms on a client span **is not enough** to call it 400 ms of network transit.

### 3.4. Java I/O event duration

Measures a specific `FileRead`/`SocketRead` operation per JVM/JFR semantics. It does not cover every stage of a logical request and can be filtered by thresholds. If one request triggers 10 socket read events, you still cannot blindly sum their durations to get request latency: events may run on different threads, overlap, omit pre/post phases, or represent only part of the protocol.

### 3.5. Kernel/device/remote-service metrics

- **TCP RTT estimate:** kernel estimate of TCP segment round-trip time; not equal to DB query duration or an entire HTTP call.
- **Block-device await:** average latency of I/O requests on a device over an interval; differs from cached/FS Java `FileRead` time and from per-request p99.
- **Remote service duration:** measured by the peer service at its own boundaries; typically excludes client pool waits and upstream infrastructure.
- **Trace spans:** instrumented work intervals, often nested; adding parent + child spans causes **double counting**, while parallel spans can overlap.

Never mechanically subtract numbers from different clocks, sampling scopes, or layers and label the remainder "network time." Decompose only after establishing compatible intervals, reliable clocks, and zero double-counting.

## 4. "What does the JVM know?" vs. "What is still unknown?"

| Question | What JVM/JFR can provide | Additional evidence needed to conclude root cause |
| --- | --- | --- |
| How long did a Java thread wait on socket read? | `SocketRead` event duration, thread, stack, endpoint if captured | To know why it waited: tracing, TCP, proxy, remote logs |
| Are TCP retransmissions rising? | JFR lacks full TCP stack counters | `ss`/`nstat`/SNMP counters, network telemetry, authorized packet traces |
| Did network RTT to the dependency rise? | Slow app calls/`SocketRead` are only hints | Per-socket/path TCP RTT, network devices, remote vantage point |
| How long did the database query run? | Client-side JDBC spans (if instrumented), possibly SQL tags | DB server query duration, execution plan, locks/waits, pool queues |
| Is the connection pool saturated? | Only if the library emits dedicated metrics/spans | Pool active/idle/pending, acquisition wait, connection lifecycle |
| Is DNS resolution slow? | App timers/JFR stacks may hint at it | Resolver metrics/logs, DNS query timing/cache misses, DNS server |
| Did file reads hit physical disk? | `FileRead` timing/path and bytes per API | Page cache stats, OS per-process I/O, block I/O traces/device counters |
| Is the storage volume being throttled? | Slow JVM file ops are a symptom | `iostat`, cgroup `io.stat`/`io.pressure`, cloud volume limits, storage metrics |
| Was the container CPU-throttled during I/O? | CPU/safepoint/thread metrics may hint at it | cgroup `cpu.stat`, host scheduler metrics, run queues |
| Was the remote API rate-limited/retried? | Client status/retry spans if instrumented | API gateway/service response logs, rate-limit headers, retry counters |
| Did a JVM GC pause overlap the latency? | JFR/GC logs, safepoints | APM request timeline and OS pressure to determine impact |
| Where did the user experience slow responses? | Server spans show only one slice | Client RUM/tracing, edge/ingress timings, network path |
| Did TLS handshake/connection setup cost time? | Client instrumentation, stacks, and some JVM events if present | Proxy TLS metrics, connect timings, socket states, cert/DNS logs |
| Is the remote object store slow reading files? | Client spans and Java network I/O | Object-store server-side latency, status/throttling, retries, network path |

**Answer boundary:** "JFR observed a 350 ms `SocketRead`" is an observation. "The database spent 350 ms running SQL" is an inference; you need DB-side evidence or traces for the same request to substantiate it.

## 5. Big trap: no events does not mean no I/O

Before concluding something **did not happen**, verify:

1. Did the recording cover the exact instance/PID and timestamp of the incident?
2. Were `jdk.SocketRead`/`jdk.SocketWrite`/`jdk.FileRead`/`jdk.FileWrite` enabled in `.jfc` with `stackTrace`?
3. What was the threshold? Short I/Os can be dropped even while thousands of short calls sum up big.
4. Does the event duration match the target object? Async/NIO/HTTP/2 may not map 1-to-1 to logical requests.
5. Did enough data survive rolling retention/`maxsize`? Were there restarts or was JFR started only after the incident?
6. Did events run on different threads? Did you filter by the right thread/process?
7. Were there waits **before** I/O, such as connection pools, executor queues, rate limiters, DNS, token refreshes, or circuit breakers?
8. Did you check library/native transports, kernel bypass, proxies/sidecars, and JDK event support?
9. Long events selected by thresholds introduce **selection bias**: the median of recorded events is not the median of all executed I/O.
10. Was JFR data missing/gapped due to crashes, full disks, instrumentation overhead, or partial capture windows?

Avoid setting ultra-low thresholds by default in production to "catch every event": event/stack trace volumes can spike and alter performance. When needed, take a short controlled profile capture, measure overhead, and save the configuration.

## 6. Collecting evidence inside the JVM: minimal workflow

JDK 21 command examples; substitute real PID and paths. `jcmd` requires suitable attach permissions; minimal containers may omit JDK tools. Use a path writable from the Java process's perspective.

~~~bash
java -version
jcmd -l
PID=12345                      # Example; verify the real PID
jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" help JFR.start
jcmd "$PID" JFR.check
~~~

If a recording is already running, dump data per operational policy **without stopping** it. If none is running, consider a short capture around a reproducing workload:

~~~bash
jcmd "$PID" JFR.start name=io_probe \
  settings=profile disk=true duration=2m \
  filename=/var/tmp/io-probe.jfr
~~~

These commands are illustrative: `profile` does not guarantee every event is enabled at your desired threshold. For detailed I/O, inspect `.jfc` or configure each event explicitly via API/settings; never claim missing events mean no I/O. The file path is resolved by the target JVM; wait for completion/verify the file before analyzing. Recordings can contain sensitive data.

Once the file is complete:

~~~bash
jfr summary /var/tmp/io-probe.jfr
jfr metadata /var/tmp/io-probe.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite \
  /var/tmp/io-probe.jfr
jfr print --events jdk.FileRead,jdk.FileWrite \
  /var/tmp/io-probe.jfr
jfr print --events jdk.ThreadPark,jdk.JavaMonitorEnter \
  /var/tmp/io-probe.jfr
~~~

Notes:
- `jfr summary` shows recorded event types and counts, **not actual total I/O operations**.
- `metadata` describes schemas/types and does not prove event instances exist.
- `jfr print` outputs events if present. For large files, print selected events or analyze in JMC; output can be huge.
- To inspect stacks, check the event's `stackTrace` property and `--stack-depth`. Increasing print depth cannot recover frames that were never recorded.
- Align event `startTime`/`duration` with application trace IDs/timestamps. Socket events do not carry logical request trace IDs by default; correlate with additional instrumentation.

**What needs proving?** For each question, build a table listing event, thread/stack, remote address or file path, timestamp, duration/bytes, and coverage level. Only then decide which evidence source to collect next.

## 7. OS/network data: what the JVM cannot measure for the kernel

### 7.1. Linux socket states and TCP

On the exact host **and network namespace** of the process/container, common useful commands include:

~~~bash
ss -s
ss -tin
ss -tinp
ip -s link
nstat -az
~~~

Explanation:
- `ss -s`: summary of socket counts by state, signaling connection buildup.
- `ss -tin`: TCP sockets with internal info such as RTT estimate, retransmission state, cwnd, and send/receive queues depending on kernel.
- `ss -tinp`: adds process association when permitted; inside containers, PID/namespace isolation may restrict visibility.
- `ip -s link`: interface bytes and packet drops/errors; stats are usually **interface-wide**, not isolated to the Java app.
- `nstat -az`: kernel protocol statistics/counters, depending on `iproute2`/config. Counters are typically cumulative; take deltas over a window and check scale rather than reading one cumulative figure and concluding packet loss just occurred.

**TCP RTT** in `ss` is the kernel's estimate for a TCP socket—not DNS/TLS setup, server app time, or client HTTP latency. Cwnd/retransmissions help test network congestion/loss hypotheses, yet still must be correlated with the right connection path, timestamp, and remote/proxy metrics.

Never run `ss -tin` from a different namespace and say "there are no connections." Sidecar meshes can make Java connect only to localhost while upstream TCP connections live inside the sidecar; verify the real network path and namespace.

### 7.2. Packet-level data and eBPF

When suspecting retransmissions, handshake timeouts, resets, abnormal socket queues, or packet loss, packet captures or eBPF tracing on the node/sidecar may be needed.

**Execute only with operational and security approval**, tightly filtered by host/port/duration, avoiding sensitive payload capture and assessing overhead. TLS protects wire payloads, yet metadata remains sensitive; termination points expose more.

Packet traces can help answer: how long SYN/SYN-ACK took, whether retransmissions occurred, which side sent TCP resets, and how window/ACK patterns behaved. They do **not** by themselves show slow DB queries or Java bugs unless tied to requests/traces.

**Avoid uncontrolled active probing:** load-generating/scanning commands, heavy tracers, or cluster-wide captures can worsen an incident; prefer existing telemetry and minimal targeted queries.

### 7.3. DNS, proxies, TLS, and connection pooling

A slow `client.send` can consist of:
- DNS lookup/cache miss;
- connection pool pending due to limited connections;
- TCP connect or TLS handshake;
- proxy/sidecar queuing/routing/retries;
- waiting for the remote service to receive and process;
- response body transfer;
- deserialization/application callbacks.

JFR `SocketRead`/`Write` sees only part of this; DNS/resolver timings, pool lease durations, and TLS handshakes generally require **client instrumentation** or proxy/client-library telemetry. Measure phases separately—at minimum: acquire → connect/TLS → send → first byte → last byte—if the SDK supports it. HTTP/2 multiplexing shares one socket across many requests, so never bind one socket read to one HTTP request solely by IP/port.

## 8. Evidence from filesystems and block storage

### 8.1. `FileRead`/`FileWrite` are Java-visible operations

A fast Java `FileRead` may read from page cache without touching the physical device. A fast Java `FileWrite` may write into page cache/kernel buffers; it does not mean the disk/volume durably committed the data. Specifically, `fsync`/`FileChannel.force`, journals, filesystem metadata, and remote network filesystems follow distinct rules.

If a request slows down in `FileRead`, competing causes include:
- device queues and IOPS/bandwidth limits;
- storage network congestion on NFS/remote volumes;
- filesystem locks or metadata contention;
- page-cache misses, memory pressure, or direct I/O depending on the app;
- thread scheduling/CPU throttling;
- applications reading huge numbers of tiny files, random access, or post-read serialization.

Therefore JFR file paths and durations are **a starting point**. They do not isolate physical wait on NVMe/volumes versus caching.

### 8.2. Linux counters for correlation

The tools below require packages (`sysstat`) and appropriate permissions:

~~~bash
PID=12345
cat "/proc/$PID/io"
pidstat -d -p "$PID" 1 5
iostat -xz 1 5
~~~

Interpretation:
- `/proc/PID/io` holds counters like `rchar`/`wchar`, `read_bytes`/`write_bytes`, `syscr`/`syscw`; they have **distinct meanings**. `rchar`/`wchar` can include syscall bytes not hitting disk, while `read_bytes`/`write_bytes` relate to actual OS-level storage I/O per kernel definitions. These are **counters**, not per-operation latency.
- `pidstat -d` gives per-process I/O throughput/waits depending on tool version; check units. Insufficient by itself for per-operation p99 I/O.
- `iostat -xz` gives block-device stats: `await`, `r_await`/`w_await`, queues/throughput, and utilization depending on version. These are **device-wide aggregates**, not one Java method; filesystems/RAID/cloud volumes can decouple numbers from logical I/O.
- Target the exact device/volume backing the file path; hosts with multiple volumes make it easy to inspect the wrong healthy device.
- Read over **the exact incident interval**, noting that the first report from some utilities is cumulative since boot rather than the recent window.

If files reside on object stores or remote mounts, local block I/O counters on the Java host may miss server-side latency. Inspect mount/client metrics, network telemetry, and storage-provider metrics instead.

### 8.3. Cgroup v2 I/O and pressure stall information

Inside an applicable cgroup v2 hierarchy, you may find:

~~~bash
cat /sys/fs/cgroup/io.stat
cat /sys/fs/cgroup/io.pressure
cat /sys/fs/cgroup/io.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.events
~~~

**Never assume** `/sys/fs/cgroup` on every host/container is the application's actual cgroup. Verify the process's cgroup path, mount, version (v1 vs. v2), and enabled controllers before reading.

- `io.stat`: read/write bytes and I/O counts per device/cgroup; does not directly provide p95/p99 latency.
- `io.pressure`: PSI, expressing time tasks stalled on I/O over kernel-provided windows/counters. Not equivalent to per-request disk response time.
- `io.max`: bandwidth/IOPS throttle limits if the controller is active; read it to know **configured limits**, not to infer they were hit.
- `cpu.stat`: CPU usage and throttling counters if present; helps separate CPU starvation from "slow I/O."
- `memory.events`: cgroup memory pressure/OOM-related events, helping check memory pressure effects on page cache and the process.

For cloud volumes or CSI drivers, add provider-side throttle/IOPS/throughput/latency metrics; the node's kernel view is not the entire storage backend.

## 9. Evidence from external services

### 9.1. HTTP/gRPC dependencies and proxies

Collect from the exact service/route/instance:
- Server-side request duration by route/method/status, request rate, and p95/p99.
- Concurrent requests, in-flight queues, worker threads, saturation, and deadline/retry counts.
- Proxy/ingress: upstream connect time, upstream response time, retries, queue/routing time, status, reset/timeout reasons, and TLS handshake metrics (if supported).
- Trace spans with `trace_id`/`span_id`, parent relationships, and request paths; account for clock skew and sampling.
- Network telemetry between Java app ↔ proxy ↔ remote service, not just client ↔ Java app.

**Watch for differing duration definitions:** Nginx, Envoy, ALB, and meshes have similar-sounding metrics with different start/end boundaries. Read your product's metric docs. `upstream_response_time` does not necessarily equal total client elapsed time or DB execution time.

### 9.2. Databases

A slow JDBC call can happen due to:
- waiting on the connection pool before starting the query;
- TCP connect/TLS/network;
- server queuing, CPU, locks, or deadlocks/serialization conflicts;
- poor query plans/indexes, scanning many rows, disk/cache misses;
- transactions holding locks too long;
- driver fetch/decoding or reading huge result sets;
- retries/timeouts triggered by the app or proxy.

Collect:
- Pool acquisition time, active/idle/pending connections, timeouts/evictions.
- Query fingerprint/ID and execution time **on the DB server**, not only client-side JDBC elapsed.
- Locks/waits, active sessions, CPU, buffer cache, IOPS, and slow-query logs; execution plans when authorized and safe.
- Rows returned/bytes, transaction boundaries, query count per request, statement timeouts.
- DB connection errors, failovers/restarts, replication lag, or quotas/throttling if relevant.

For example, PostgreSQL offers `pg_stat_activity`, `pg_stat_statements`, and `EXPLAIN` subject to policy and cost; they do not automatically link a SQL statement to a JFR event without query ID/trace mapping. **Never run `EXPLAIN ANALYZE` on expensive queries in production** without assessing impact.

### 9.3. Redis/caches, message brokers, object stores

- Cache/Redis: server latency, command duration, CPU/evictions, connections/queues, retries, cache hits/misses.
- Kafka/RabbitMQ: broker request latency, producer batching, consumer lag, partition queues, replication/acks, throttling.
- Object storage: request IDs, server-side latency/TTFB if exposed, retries/throttling/status codes, bandwidth, multipart/sizes.
- DNS: resolver latency, lookup failures/timeouts, cache hits/misses, authoritative/upstream issues.
- Service mesh: xDS/routing, outlier ejection, circuit breaking, pending requests, connect failures, sidecar CPU/throttling.

Depending on the incident, collect only groups **relevant to the actual slow calls**. Never demand "turn on full debug logs in every service"; overhead, sensitive-data exposure, and load can degrade the system further.

## 10. Stitching evidence for a single request

A strong "evidence bundle" aligns these layers:

| Layer | Correlation key | Required timestamps |
| --- | --- | --- |
| Edge/ingress | request ID / trace ID | Receive, queue, upstream connect, first/last response |
| Java service | trace ID / span ID, pod/PID | Handler start/end, route/status, application phases |
| Client library | parent span, connection/request metadata | Acquire, connect/TLS, send, response headers/body, retries |
| JFR | PID, thread ID/name, event/stack, endpoint | `startTime`/duration of `SocketRead`/`FileRead`, GC, `ThreadPark` |
| OS/kernel | PID/TID, socket tuple, netns/cgroup/device | Time-series RTT/retrans/queues, I/O, CPU/PSI, limits |
| Remote service | trace ID/request ID, server instance, query ID | Receive/queue/process/response; locks/CPU/storage |
| User-facing metric | route/customer cohort, request ID if present | End-to-end latency/p99/error/timeout SLO |

**Clocks and scope:** State timezone explicitly (prefer UTC) and track clock sync/skew across hosts. Monotonic clocks measure durations within one process; wall-clock timestamps correlate across hosts and can jump. Socket events must be paired carefully with logical requests—especially with keepalive, HTTP/2 multiplexing, TLS termination, and connection reuse.

### 10.1. Nested spans must not be summed arbitrarily

Example:
- Total server span: 550 ms;
- HTTP client span **nested inside** the server span: 430 ms;
- Database server span **nested inside** that client/server chain: 370 ms.

Never add `550 + 430 + 370 = 1,350 ms` and call it request latency. The intervals **nest**. Nor can you assert `430 - 370 = 60 ms` "is network time" when the client span includes pool wait, retries, proxies, serialization, and unsynchronized clocks.

Quantifying network/wait accurately requires phase-split spans and measurements at both ends, or packet/kernel evidence. Record "unexplained" gaps as **unattributed time** until better telemetry is available.

### 10.2. Sampling and non-matching request data

JFR captures events per config, distributed traces are often head- or tail-sampled, and access logs may be sampled/filtered. Never randomly attach a 400 ms `SocketRead` to a traced request from the same minute without clear connection/thread mapping. For p99 latency, prioritize samples **from the actual tail cohort**, not just average traffic.

## 11. Cheap-to-deep I/O slowdown runbook

### Step 1 — Confirm symptom and scope

Record: UTC window, route/operation, p95/p99, errors/timeouts, throughput, bytes per request, instance/pod/PID, JDK/GC, deploy/change log, and impacted share. Is the whole service affected or one dependency? Does it match a traffic spike?

### Step 2 — Check what the JVM sees

Open JFR for the exact process and incident window. Inspect `SocketRead`/`Write`, `FileRead`/`Write`, `ThreadPark`/monitors, CPU, and GC. Verify event settings/thresholds, stacks, and timestamps. If data is missing, **document the coverage gap** instead of jumping to "no I/O."

### Step 3 — Inspect application-level spans and client pools

Place request handler, client call, connection acquisition, retry, and timeout spans side by side. An HTTP call slowed by pending pool acquisition differs completely from a socket slowed by packet loss. Never read every wait as time spent on the network.

### Step 4 — Check the host/container over the same window

If network is suspected: socket RTT/retrans/queues, interface drops, node/sidecar CPU, netns.
If disk is suspected: block-device await/queues, per-process I/O, `io.pressure`/`io.stat`, volume limits.
If CPU/scheduling is suspected: `cpu.stat` throttling, CPU load, runnable queues, host saturation.
If memory is suspected: page-cache pressure, swap/stall counters where applicable; do not confuse JVM heap used with total process memory.

### Step 5 — Check proxies and remote services

Gather server response time, queues/locks/CPU/storage, status/retries, query IDs, trace IDs; match specific calls to Java client spans. Did the remote service prove slow? If remote processing was fast, what happened before/after the remote span?

### Step 6 — Evaluate competing hypotheses

For a long Java `SocketRead`, consider:
- A: long DB query/lock;
- B: packet loss/retransmissions;
- C: proxy queues/retries;
- D: Java thread descheduled/CPU-throttled;
- E: event unrelated to the target request or recording lacks context.

For each hypothesis, write down **what data would confirm or falsify it**. Prioritize evidence from the directly responsible domain rather than hunting for one chart supporting an initial guess.

### Step 7 — Small controlled experiment and verification

Change one justified variable (pool limit, query plan/index, batch size, retry policy, concurrency, storage tier, or network path). Run the same workload and compare SLOs, errors, throughput, resource usage, and dependency metrics. Have a rollback plan. Do not blindly raise timeouts: that often turns fast failures into piled-up queues.

## 12. Scenario A — Long SocketRead caused by the DB server

Hypothetical data:
- Java/JFR: 60 `SocketRead` events lasting 300–600 ms on connections to the database during the checkout p99 spike.
- JDBC span: 500 ms; connection acquisition under 5 ms.
- TCP `ss`: low RTT estimate and no noticeable rise in retransmissions on that socket/window.
- DB tracing/query log: statement execution ~440–480 ms with rising lock waits; query IDs match requests.

**Better-supported conclusion:** the application waited for responses while the DB executed queries/waited on locks; fix contention/SQL/transactions rather than micro-optimizing socket read methods.

**Caveat:** low RTT and zero observed retransmissions do not rule out every network fault; however, combining them with DB-side timings for the exact queries makes the server-wait hypothesis far stronger. Numbers are illustrative, not a formula converting Java `SocketRead` into DB execution.

Action: inspect lock holders, transaction durations, indexes/query plans, and connection behavior; verify improvements in both DB execution time and checkout p99.

## 13. Scenario B — Slow requests with no significant SocketRead events

Hypothetical data:
- HTTP client span 1,100 ms; JFR records few `SocketRead` events.
- Connection pool: pending acquisition 900 ms with growing pending queue.
- Remote service: median processing 40 ms; network RTT/packet drops steady.
- App concurrency jumped from 100 to 1,000 while the pool allows only 30 connections.

**Interpretation:** the main bottleneck is likely **pool acquisition/queuing before socket read ever starts**. Missing long `SocketRead` events does not disprove slow RPCs. Raising connect timeout, tuning GC, or chasing packet loss are wrong first moves.

Action: measure peak in-flight, pool checkouts, connection reuse, retry storms, bounded concurrency, and service capacity; evaluate pool sizing only after checking remote capacity. Blindly enlarging the pool may simply shift the queue to the database.

## 14. Scenario C — Fast FileWrite, yet non-durable data and saturated volume

Hypothetical data:
- Java `FileWrite` events mostly under a few milliseconds.
- Certain transactions have long flush/force steps; end-to-end latency climbs with batch size.
- OS/cloud volume metrics: write queues, await, and throttling/IOPS near limits.
- cgroup `io.pressure` and device stats spike during the incident.

**Interpretation:** the write API looks fast thanks to kernel buffering, while the durability step or backing storage device is slow. Looking only at `FileWrite` histograms misses flush and filesystem pressure. Not all latency belongs to the device unless traces and host counters align cleanly.

Action: inspect transaction/flush frequency, write batching policy, cloud volume limits, filesystem, and durability requirements. Never disable `fsync` or drop durability to "boost performance" without validating data-safety requirements.

## 15. Scenario D — Network wrongly blamed due to CPU throttling

Hypothetical data:
- Java client spans jump from 120 ms to 500 ms during peak hours.
- OS TCP RTT/retransmissions barely move.
- cgroup `cpu.stat` shows throttling counts/time spiking.
- Request workers, event-loop threads, or sidecar CPU approach quota; pending queues grow.
- Remote API server-side processing stays steady.

**Interpretation:** CPU/scheduling starvation and queuing inside the container can make I/O operations **appear slow** even when the network path and remote handler are healthy. JVM CPU load and thread states alone may fail to expose cgroup throttling.

Action: inspect CPU requests/limits, node contention, CPU-heavy serialization/TLS, traffic shaping, and queues; adjust workload/CPU quota in a controlled test and re-check p99.

## 16. Scenario E — Fast SocketWrite, yet client timeouts

Hypothetical data:
- Java server `SocketWrite` is fast and handler duration is small.
- Ingress/proxy logs show unusual downstream sends/resets and queuing/delivery delays.
- Network/edge telemetry shows retransmissions or high RTT for one group of client connections.
- Client end-to-end latency/timeouts spike in only one network region.

**Interpretation:** a fast Java write can mean bytes entered a buffer or transport layer, not that the end client received the full HTTP body. Proxy/edge and client-side evidence is needed to separate server completion, network delivery, and client read timeouts.

Action: inspect load-balancer response-body timings, payload sizes, client regions, TCP paths, and retries/cancellations. Never clear the server completely just because write returned fast, yet do not blame server code for every timeout either.

## 17. Java 17+ example — reading the limits of a measurement

The following program is **standalone and runnable on Java 17+**, using **hypothetical collected numbers**. It illustrates why an entire HTTP client span duration cannot be blamed on the network even when the thread's CPU time during the span is small.

Save as **`LatencyBoundaryDemo.java`**:

~~~java
import java.util.Locale;

public class LatencyBoundaryDemo {
    record Sample(
            String operation,
            long requestWallMs,
            long clientSpanWallMs,
            long clientThreadCpuMs) {

        Sample {
            if (requestWallMs <= 0
                    || clientSpanWallMs < 0
                    || clientSpanWallMs > requestWallMs
                    || clientThreadCpuMs < 0
                    || clientThreadCpuMs > clientSpanWallMs) {
                throw new IllegalArgumentException("Invalid sample");
            }
        }
    }

    static void report(Sample s) {
        double share = 100.0 * s.clientSpanWallMs() / s.requestWallMs();
        long wallMinusCpu = s.clientSpanWallMs() - s.clientThreadCpuMs();

        System.out.printf(
                Locale.ROOT,
                "%s: request=%dms, client-span=%dms (%.1f%%), "
                        + "client-thread-cpu=%dms, wall-minus-cpu=%dms%n",
                s.operation(),
                s.requestWallMs(),
                s.clientSpanWallMs(),
                share,
                s.clientThreadCpuMs(),
                wallMinusCpu);
    }

    public static void main(String[] args) {
        report(new Sample("checkout", 500, 420, 12));
        report(new Sample("report", 500, 50, 10));
    }
}
~~~

Compile/run:

~~~bash
javac LatencyBoundaryDemo.java
java LatencyBoundaryDemo
~~~

**Exact** stdout for the fixed inputs:

~~~text
checkout: request=500ms, client-span=420ms (84.0%), client-thread-cpu=12ms, wall-minus-cpu=408ms
report: request=500ms, client-span=50ms (10.0%), client-thread-cpu=10ms, wall-minus-cpu=40ms
~~~

**Proper** interpretation:
- In the `checkout` sample, the client span accounts for 84% of request wall time—making it the primary place to investigate first.
- `wall-minus-cpu = 408 ms` is **the difference between span wall time and one thread's CPU time in the hypothetical sample**; it can include waiting, scheduling, pool waits, DNS, network, server execution, or work on other threads. **Never label 408 ms as network latency.**
- If the client span involves async tasks, CPU across multiple threads is not captured in one simple `client-thread-cpu` number, narrowing interpretation even further.
- Durations in the example assume same request, same scope, and non-negativity; the code does not check sampling errors, clock skew, or coverage. It illustrates arithmetic, **not real I/O measurement** or root-cause inference.

### 17.1. What does real application-level measurement need?

In production instrumentation, use **`System.nanoTime()`** for same-process durations rather than using `System.currentTimeMillis()` as a stopwatch. If current-thread CPU time is needed, `ThreadMXBean` can supply it when supported by JVM/OS and enabled; it does not sum CPU across all async threads within a span.

A good span should include:
- service, route, request/trace ID, remote logical dependency;
- operation start/end, success/error, timeout type, status;
- request/response bytes, attempts/retries;
- pool acquisition, connect/TLS, first byte, body read and decode if supported by the SDK;
- connection reuse and timeouts/deadlines;
- an event-level link to JFR if reliable correlation exists.

Never log secrets, tokens, passwords, full SQL parameters, or complete request/response payloads solely to investigate latency. When attaching query/URL attributes, enforce redaction/sampling policies.

## 18. Symptom-to-evidence selection table

| Primary symptom | Check inside JVM first | Priority external sources | What you must NOT conclude yet |
| --- | --- | --- | --- |
| Slow `SocketRead` | Event/stack/endpoint, JDBC/HTTP spans, GC/CPU | Remote processing logs, TCP RTT/retrans, proxy traces | "Network is slow" from read duration alone |
| Slow client RPC, few socket events | Pool metrics, `ThreadPark`, client span phases | Proxy/mesh queues, remote status, async transport | "Not I/O" because events are missing |
| Slow `SocketWrite` | Event size/duration, thread, backpressure | Socket send queue, network drops, downstream read speed | "Server code writes slowly" without checking kernel |
| Client timeouts while server spans look fast | Handler/write spans, cancellation/error logs | Edge/proxy/client RUM, transport errors | "Delivered successfully to client" |
| Slow JDBC call | Connection acquisition, driver spans, stacks | DB waits/locks/query IDs, execution plans | "SQL execution is slow" from JDBC time alone |
| Slow `FileRead`/`FileWrite` | Path, duration, bytes, GC/CPU | `iostat`, process I/O, fs/cache, cloud volume | "Physical disk is slow" from one `FileRead` |
| Few JFR file I/O events yet high p99 | Thresholds, recording coverage, async model | Traces, queues/pools, dependency metrics | "No bottleneck" |
| p99 spikes under peak load | RPS/route mix, GC, CPU, thread queues | cgroup throttling/PSI, proxy/server load | "JVM bug" before checking capacity |
| DNS/TLS/connect spikes | Client phase timers, logs, errors | Resolver, TLS/sidecar/ingress metrics, socket connects | "`SocketRead` measured DNS too" |
| Only one geographic region fails | Server/traces by region/tenant | Edge/client/network path/CDN metrics | "The whole JVM is slow" |

## 19. Data quality, safety, and common mistakes

### 19.1. Correlation does not equal causality

If JVM `SocketRead` duration rises alongside TCP retransmissions, that supports a network-path issue, **yet you must still** verify matching sockets, remote IPs, namespaces, and routes. Node-wide retransmissions could belong to another workload. If DB query p99 also rises, both may share load or be independent faults.

Conclusions should state:
1. **Direct observations:** which source, metric, and timestamp;
2. **Hypothesis:** mechanism increasing latency;
3. **Discriminating evidence:** from OS, proxy, or remote service;
4. **Limitations:** missing telemetry, sampling/clock skew;
5. **Experiment/fix:** what changed and what will re-verify it.

### 19.2. Mistakes to avoid

- **Reading `SocketRead` duration as network RTT.** It can include server think time, waiting, and scheduling.
- **Reading `SocketWrite` success as client receipt.** Kernel buffering/ACKs/application consumption are separate layers.
- **Reading `FileWrite` duration as durable disk write time.** Page cache, flushing, and filesystem semantics sit in between.
- **No JFR event = no I/O.** Event settings/thresholds, async/native paths, and recording windows can omit data.
- **Concluding I/O causes solely from JVM CPU/heap.** Misses cgroup throttling, kernel/block devices, and remote logs.
- **Using host-aggregate numbers to diagnose one pod.** Verify netns/cgroup/device/socket/process mappings.
- **Summing nested spans into request time.** Parent/child spans overlap; async work makes errors even worse.
- **Comparing data from different timestamps/processes.** A new PID after restart or post-spike snapshot cannot replace pre-failure history.
- **Immediately raising timeouts/pools/retries.** Can amplify queues, connection load, retry storms, and crash dependencies.
- **Enabling system-wide debug traces/captures.** Can add overhead, leak sensitive data, and distort measurements.
- **Trusting default thresholds blindly.** Inspect exact `.jfc`/event settings and versions.
- **Using arbitrary `traceroute`/`ping` to rule out network issues.** Probes can take different paths, protocols, or priorities than app traffic.
- **Assuming low TCP RTT means fast remote responses.** The DB may still be locked or running slow queries.
- **Treating high `iostat` `await` as the sole cause.** Device aggregates can reflect another job; match exact volumes and services.
- **Assuming absolute log timestamps across hosts are synchronized.** Account for clock skew/UTC and trace span boundaries.
- **Comparing event counts captured under different thresholds.** The observed sample sets differ.

### 19.3. Protecting data and operational safety

JFR files, logs, traces, packet captures, and database query samples can expose paths, class names, endpoints, IPs, request IDs, SQL, filenames, stack traces, or sensitive fields. Capture only the minimum required scope, restrict permissions, redact before sharing, enforce retention, and avoid tools that overload or stall production.

When OS or remote-service access is unavailable, document the **evidence blocker** explicitly and engage the owning team: SRE, network, storage, DB, or platform. Never interpret "could not see evidence" as "did not happen."

## 20. I/O incident report template with evidence boundaries

~~~text
# I/O latency investigation

Incident / SLO target:
Service / build / JDK / PID / pod / namespace:
Incident UTC start/end:
RPS / request mix / payload / concurrency:
p95/p99 / error rate / timeout type:
Java application spans / trace IDs:
JFR file / configuration / event thresholds:
Relevant JFR I/O events (type, time, duration, stack, endpoint/path):
Thread/GC/CPU context:
Coverage gaps and sampling limits:

OS evidence:
- Host/netns/cgroup/device identifiers:
- Socket RTT/retrans/queues, interface drops, time window:
- Process/block I/O and io.pressure/limits:
- CPU throttling / memory pressure:
- Missing permissions or unavailable commands:

External evidence:
- Proxy/ingress/mesh timings, retries, status:
- Remote service / DB query ID and server duration:
- Locks, pool queue, CPU/storage, throttling:
- Client experience and end-to-end trace:

Hypothesis A / supporting evidence / falsifier:
Hypothesis B / supporting evidence / falsifier:
What is directly observed vs inferred:
Confidence and remaining gaps:
Smallest proposed experiment:
Validation metrics and rollback:
~~~

This template is an **incident framework**, not JFR tool output. A strong report does not need numbers in every blank; it must make clear what was **directly measured**, what **could not be observed**, and how to obtain the missing evidence.

## 21. Final checklist

- [ ] Verified exact service, instance/PID, JVM version, recording, and UTC incident window.
- [ ] Distinguished end-to-end latency, server span, client call span, JFR I/O duration, kernel RTT, and remote processing time.
- [ ] Did not attribute `SocketRead` to the whole network/server phase or `SocketWrite` to confirmed client delivery.
- [ ] Checked JFR event settings, thresholds, stack coverage, recording retention, and async/native transports.
- [ ] Collected application-level metrics for connection pools, executor queues, retries, deadlines, and error codes.
- [ ] Mapped which logical requests correspond to services/connections/traces and accounted for HTTP/2 multiplexing.
- [ ] Gathered OS/network telemetry from the **exact host, network namespace, and time window**.
- [ ] When suspecting disk, collected process/cgroup/device metrics and distinguished page cache/`fsync`/remote volumes from Java `FileWrite`.
- [ ] When suspecting CPU scheduling, inspected cgroup CPU throttling, host pressure, and sidecars.
- [ ] Inspected remote service/DB/proxy metrics and matched query/request IDs wherever possible.
- [ ] Did not blindly sum nested spans or multi-thread aggregates into request latency.
- [ ] Evaluated competing hypotheses and wrote falsification criteria for each.
- [ ] Did not alter pools/timeouts/heap/GC/storage/network before identifying the bottleneck and guardrails.
- [ ] Ensured telemetry/captures stayed safe, redacted, access-controlled, and bounded in duration.
- [ ] Separated conclusions into **direct observations**, **conditional inferences**, **insufficient data**, and **next measurements**.

## 22. Conclusion

**The JVM excels at showing what the Java application did and where it blocked from the runtime's perspective; the JVM is not a complete measurement system for networks, kernels, disks, or external services.**

For I/O latency, the right sequence is:

**Symptoms & SLO → verify JFR/trace coverage → inspect Java I/O and thread evidence → inspect OS/kernel/container in the right namespace → inspect proxies/remote services for the exact requests → align timelines, rule out competing hypotheses → experiment and re-measure.**

A useful conclusion answers all four at once: **"What did I observe from the JVM?", "Which portion of the end-to-end path is that?", "Which external source proves the rest?", and "If the hypothesis is true, which metrics will change?"**

### Official references

- Oracle JDK 21 — jfr command (summary, metadata, print): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle Java 17 — Troubleshoot Performance Issues Using Flight Recorder, I/O Performance section: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle JDK 21 — JFR API event settings and thresholds: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle JDK 21 — jcmd/JFR.start/JFR.check: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Linux ss(8) manual: https://man7.org/linux/man-pages/man8/ss.8.html
- Linux Kernel cgroup v2 (io.stat, io.max, io.pressure, cpu.stat): https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html
