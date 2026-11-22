# Backlog and Operating System-Dependent TCP Connection Queue Limits

When writing a **TCP server** in Java, we often see the **backlog** parameter on **ServerSocket** or **ServerSocketChannel**. The name suggests this is the number of connections queued waiting, but the value passed from Java **is not a guarantee** that the operating system will hold that exact number of connections. Backlog is a **configuration request for the listening socket's queue**; the operating system, kernel version, system limits, TCP handshake state, and the rate at which the application calls **accept()** determine the actual behavior.

Problems often appear during a burst of concurrent access: clients may complete or nearly complete the TCP handshake while the server has not yet popped connections from the queue; some **connect()** calls may be slow, time out, or fail. Increasing the backlog sometimes helps absorb a short burst, but **cannot increase long-term processing throughput** if the accept loop, workers, or system resources are overloaded.

This lesson helps you distinguish the handshake queue from the accept-pending queue, properly understand the Java API, the common model on Linux and differences across operating systems, run Java 17 examples yourself, observe real metrics, and choose a safe operational approach.

## 1. Which stage of the connection lifecycle does backlog belong to?

A TCP server typically goes through the following steps:

1. **bind** the listener's IP address/port.
2. **listen** so the kernel receives incoming connections and maintains the necessary state/queues.
3. **accept** so the application retrieves a ready connected socket from the kernel.
4. **read/write** to process the byte stream on the accepted socket.
5. **close** when the transaction/connection ends.

~~~text
   TCP client                     TCP kernel server                  Java server
      |                                  |                                |
      | ------ SYN ---------------------> |                                |
      | <----- SYN-ACK ------------------ |                                |
      | ------ ACK ---------------------> |                                |
      |                          connection eligible                  |
      |                          enters accept queue                  |
      |                                  | --- accept() ---------------> |
      |                                  | <-- Accepted Socket --------- |
      | <-------------------- application data over socket -------------->|
~~~

The diagram is a basic explanatory model; the exact path also depends on the kernel, retransmissions, TCP Fast Open, SYN cookies, and error cases. **Java ServerSocket.accept() does not perform every TCP handshake itself**: the kernel handles the networking part, then returns a ready socket to the application when accept succeeds.

The key point is that **a successful client connect does not mean Java has accepted that connection or processed the request**. The operating system can complete the handshake and hold the connection in a queue waiting for the application to call accept. Even the point at which both sides consider the connection complete can differ in situations where the server queue is under pressure.

### What backlog is NOT

- **Not the maximum number of live TCP connections allowed**: after accept, connections can continue to live for many seconds/minutes; limits also depend on file descriptors, memory, application configuration, and load.
- **Not a thread limit**: ServerSocket and the worker pool are two different layers; backlog does not create new threads and does not determine the size of an ExecutorService.
- **Not the business request queue length**: a single accepted socket can carry multiple requests; queues in an ExecutorService, message broker, or database are a separate matter.
- **Not the receive/send buffer size**: SO_RCVBUF and SO_SNDBUF hold socket data, which is different from the number of pending connections.
- **Not the number of clients guaranteed to connect before being rejected**: the kernel can enforce limits, change how queuing works, retry, or have state not reflected in a Java queue.

## 2. Two common queue types in Linux TCP

When talking about backlog in practice, we need to separate **incomplete handshake state** from **connections that are established but not yet accepted**.

<escape>
</escape>

~~~text
Client sends SYN
      |
      v
 [Request / incomplete handshake state]
 [SYN queue or equivalent mechanism]
      |
      | Handshake completes per kernel rules
      v
 [Accept queue: completed connections waiting for app]
      |
      | ServerSocket.accept()
      v
 [Accepted socket: application processes via thread/event loop]
~~~

**SYN queue / incomplete handshake queue.** In the traditional Linux model, the kernel tracks requests currently in the TCP handshake phase. The count and limiting policy are related to **net.ipv4.tcp_max_syn_backlog**. When SYN cookies are enabled and the corresponding path is triggered, the kernel can avoid storing per-SYN state in the usual way; one must not infer from this that the entire server has unlimited processing capacity.

**Accept queue / completed connections waiting for accept.** On Linux since 2.2, the **backlog** parameter of TCP listen mainly determines the queue length of **completely established connections waiting for the application to accept**. Linux caps this request by **net.core.somaxconn**. If the application requests a backlog of 10,000 while somaxconn is 4,096, the kernel may silently cap the request down to that level according to the listen(2) documentation. The exact value **must be read on the running machine**, not guessed by distribution.

**Note on metrics:** “SYN queue” and “accept queue” are useful models for understanding Linux TCP, not a Java API standard guaranteeing two tangible queues with the same structure on every OS. Kernels, versions, and network optimizations can change how requests, ACKs, retransmissions, and actual limits are managed.

| Aspect | Incomplete handshake connections | Completed connections waiting for accept |
|---|---|---|
| TCP step | Processing SYN/SYN-ACK/ACK handshake | Already eligible to become an application socket |
| Concern | Resources before a complete connection, SYN flood, retransmissions | Is the application pulling connections out of the kernel fast enough? |
| Commonly related on Linux | **tcp_max_syn_backlog**, **tcp_syncookies**, and kernel policies | **listen(backlog)** value after **somaxconn** limit |
| Directly visible in Java via ServerSocket? | No portable API to read the number of pending SYNs | No portable API to get actual queue length or pending count |
| Overload | May retry/drop or use anti-SYN-flood mechanisms | May cause handshakes to stall, drop/retry, time out, or fail to connect; no uniform result across all systems |

### What happens when the accept queue is full?

There is no single answer such as “connection B+1 always gets Connection refused”. On Linux and other OSes, handling also depends on the handshake stage, TCP options, retransmissions, kernel policy, and configuration. Some clients may see **slow connect()**, **SocketTimeoutException**, **ConnectException**, or even appear connected while the server application cannot yet process them. Such observations do not accurately measure backlog length in isolation.

**Backlog is a buffer for accept calls**, not a guarantee of latency or request-processing capacity after accept.

## 3. How do Java APIs declare backlog?

### 3.1. java.net.ServerSocket

Java 17 provides these common ways:

~~~java
// A bound server socket with requested backlog:
ServerSocket server = new ServerSocket(port, backlog, bindAddress);

// Or create unbound then bind with backlog:
ServerSocket server2 = new ServerSocket();
server2.bind(new InetSocketAddress(bindAddress, port), backlog);
~~~

**This is an illustrative API snippet**, assuming imports and port/backlog/bindAddress variables already exist; in real usage, the listener must be closed with try-with-resources and IOException must be handled.

- **port = 0**: asks the operating system to allocate an ephemeral port; read the actual port using **getLocalPort()**.
- **backlog > 0**: suggested value. Exactly how many pending connections, and whether it is capped or ignored, is **implementation-specific**.
- **backlog <= 0**: Java uses an **implementation-dependent default value**; “0” should not be interpreted as “no queue”.
- **new ServerSocket(port)** per the Java 17 API requests a default of 50 for the queue, but **there is no guarantee the operating system enforces exactly 50**. What effective backlog the system uses still depends on the implementation and OS.
- **bind(...)** configures the listener once. For an already-bound ServerSocket, you cannot simply call bind again to change the backlog; you need appropriate listener lifecycle management/deployment configuration.

The JDK documentation clearly states that backlog is the **requested maximum number of pending connections** and the operating system may impose a limit or ignore the parameter. Do not extrapolate a formula that Java backlog = number of concurrent clients.

### 3.2. java.nio.channels.ServerSocketChannel

With Java NIO, you pass backlog right at bind time:

~~~java
try (ServerSocketChannel channel = ServerSocketChannel.open()) {
    channel.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0), 128);
    // accept() or register OP_ACCEPT with a Selector depending on the I/O model.
}
~~~

This illustrative snippet has its type names imported in the corresponding Java examples; it only shows the **bind(SocketAddress, int)** overload. **ServerSocketChannel.bind(endpoint)** without a backlog parameter is equivalent to calling the overload with the same endpoint and backlog = 0 per Java 17, meaning the implementation chooses the default. ServerSocketChannel can be used in blocking or non-blocking mode; changing modes does not turn backlog into a limit for all open connections.

**AsynchronousServerSocketChannel.bind(endpoint, backlog)** also has this parameter with implementation-dependent semantics. Do not mistake “async accept” as causing the OS to ignore the listen queue: the kernel still has to process and queue connection requests to the listener according to its own mechanism.

### 3.3. No portable “getBacklog()”

Java ServerSocket does not expose a standard API to ask “how much backlog is the kernel enforcing?” or “how many slots are occupied?”. If you want to know the **effective limit** and **queue fullness**, you must use the operating system's own tools/counters and measure on the exact host/network namespace where the process runs.

## 4. Runnable Java 17 example: request backlog, accept one connection

The first program's job is to clearly separate **the backlog requested at bind time** from **accepting a connection**. It runs completely on loopback, uses port 0 to avoid port conflicts, creates one worker thread for accept and one client in the same JVM. The output is deterministic; the example makes no claim of testing the OS's actual slot count.

File **BacklogBasicsDemo.java**:

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BacklogBasicsDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        int requestedBacklog = 8;

        try (ServerSocket listener =
                     new ServerSocket(0, requestedBacklog, loopback)) {
            listener.setSoTimeout(3_000);

            ExecutorService worker =
                    Executors.newSingleThreadExecutor();
            try {
                Future<Integer> received = worker.submit(() -> {
                    try (Socket accepted = listener.accept()) {
                        return accepted.getInputStream().read();
                    }
                });

                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            loopback, listener.getLocalPort()), 3_000);
                    client.getOutputStream().write(65); // ASCII character A.
                    client.shutdownOutput();
                }

                System.out.println(
                        "Requested backlog: " + requestedBacklog);
                System.out.println(
                        "Accepted byte: "
                                + received.get(3, TimeUnit.SECONDS));
            } finally {
                worker.shutdownNow();
            }
        }
    }
}
~~~

Compile/run (Java 17+):

~~~bash
javac -encoding UTF-8 BacklogBasicsDemo.java
java BacklogBasicsDemo
~~~

Output of a successful run:

~~~text
Requested backlog: 8
Accepted byte: 65
~~~

In the example:

1. **new ServerSocket(0, 8, loopback)** requests backlog 8 and binds on loopback.
2. The worker blocks on **accept()** to receive one connection.
3. The client completes connect and then writes one byte **65**.
4. When accept returns, **accepted** is a **new** Socket for that connection; the listener socket remains in the listening state.
5. Read returns byte 65 and the Future passes the result to main. The client's **shutdownOutput()** call signals the end of the send direction, without closing the listener.

**What the example does NOT prove:** that the kernel allocated exactly eight slots; that eight concurrent clients is the limit; or that because accept() runs in an ExecutorService, backlog means eight threads. Backlog remains a request to the OS at bind time.

## 5. Experimental example: intentionally not accepting to observe overload

To see the effect of a listener not calling accept, we can keep the server socket **listening** but never call **accept()**, try multiple loopback clients sequentially, and hold onto the Sockets that connected successfully. The result depends on the OS, kernel, retransmission count, and timeouts. Therefore, the program **does not print a fixed prediction of the number of successful connections**.

**Note:** this is a local educational experiment; do not use it to benchmark production capacity. With loopback and short timeouts, differences across machines are normal.

File **BacklogProbeDemo.java**:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.util.ArrayList;
import java.util.List;

public class BacklogProbeDemo {
    public static void main(String[] args) throws Exception {
        final int attempts = 12;
        final int requestedBacklog = 2;
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket(
                0, requestedBacklog, loopback)) {

            List<Socket> connectedSockets = new ArrayList<>();
            int timedOut = 0;
            int otherErrors = 0;

            try {
                // Do not call listener.accept() so connections
                // are not drained from the accept queue by the application.
                for (int i = 0; i < attempts; i++) {
                    Socket client = new Socket();
                    try {
                        client.connect(new InetSocketAddress(
                                loopback, listener.getLocalPort()), 250);
                        connectedSockets.add(client);
                    } catch (SocketTimeoutException ex) {
                        timedOut++;
                        client.close();
                    } catch (IOException ex) {
                        otherErrors++;
                        client.close();
                    }
                }

                System.out.println("Attempts: " + attempts);
                System.out.println(
                        "Connected: " + connectedSockets.size());
                System.out.println("Timed out: " + timedOut);
                System.out.println("Other errors: " + otherErrors);
                System.out.println(
                        "Total accounted: "
                                + (connectedSockets.size()
                                + timedOut + otherErrors));
            } finally {
                for (Socket socket : connectedSockets) {
                    socket.close();
                }
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 BacklogProbeDemo.java
java BacklogProbeDemo
~~~

**Two deterministic lines if the program finishes normally**:

~~~text
Attempts: 12
Total accounted: 12
~~~

The three middle lines (**Connected**, **Timed out**, **Other errors**) have measurements that **vary by machine and run**; do not copy a hypothetical number as an “expected output”. Some systems may accept more than the requested backlog due to queue mechanisms, kernel constants, or handshake timing; some systems produce timeouts, errors, or a different number of successes. If all 12 connects succeed, that **does not prove backlog was unconditionally ignored**; it is simply data from that specific trial.

The most important takeaway of the experiment: the server is still **listening** but **not accepting**; the absence of accept allows completed connections to accumulate in the kernel until OS policy takes effect. Try modifying it to use a continuous accept loop and run again; the handling/measurement approach needs to change to avoid immediate socket closure skewing the results.

## 6. Important limits on Linux

On modern Linux, **backlog in Java code** alone is not enough to determine queue capacity:

| Configuration/measurement point | Role | What must not be misunderstood |
|---|---|---|
| **listen(backlog)**, passed by Java at bind | Requests accept queue length for established connections waiting for the app to accept | Does not itself set max active connections |
| **net.core.somaxconn** | Upper limit on listener backlog; higher requests are capped per Linux listen(2) | Not the SYN queue length, nor a performance guarantee |
| **net.ipv4.tcp_max_syn_backlog** | Limit related to TCP requests with incomplete handshakes on the non-SYN-cookies path | Not the number of Java Sockets waiting to be accepted |
| **net.ipv4.tcp_syncookies** | Protection mechanism under SYN pressure that can change how the kernel keeps handshake state | Not a switch to boost application performance or remove the accept queue limit |
| **File descriptor count / socket memory** | Resource limits of the process and kernel | High backlog does not grant more FDs/heap/threads |
| **Worker pool, executor queue, database** | Determines how fast the app processes accepted sockets | Not counted toward the kernel backlog |

According to **listen(2)**, since Linux 2.2 TCP backlog describes the queue of **established connections waiting to be accepted**, while the incomplete requests limit belongs to **tcp_max_syn_backlog** (when applicable). The man-pages documentation notes **somaxconn** has a default value of 4,096 since Linux 5.4, previously often 128; this is a **documented default**, **not a guarantee of the running machine's configuration**. Distros, containers, and administrators may use different values.

You can think of it simply as:

~~~text
effective accept queue backlog
  <= backlog requested by application
  <= or capped by somaxconn per kernel policy
~~~

This is **a way to visualize the limit**, not a formula to calculate the exact number of clients guaranteed to connect. Behavior also involves off-by-one cases, retries, queue structures, and timing races; do not use “backlog B = exactly B successes, client B+1 is definitely rejected” as a test invariant.

### Observing configuration and queues on a Linux machine

The commands below are **Linux commands for learners to run in their own environment**, not output printed by Java:

~~~bash
sysctl net.core.somaxconn
sysctl net.ipv4.tcp_max_syn_backlog
sysctl net.ipv4.tcp_syncookies
ss -lnt
nstat -az | grep -E 'ListenOverflows|ListenDrops|Syncookies'
~~~

How to read them:

- **sysctl** shows the current configuration in the network namespace/kernel you are observing; if running in a container, distinguish between the container and host namespaces. Some values may be managed at the node level and not modifiable from inside a container.
- On many Linux versions, **ss -lnt** shows listening TCP sockets; the **Recv-Q** column may indicate the number of completed connections waiting for accept, while **Send-Q** reflects the listener's accepted backlog level. You must cross-check the exact **iproute2** and kernel versions, and not apply this interpretation to every socket state or every operating system.
- The **ListenOverflows**, **ListenDrops**, **Syncookies...** counters in TCP statistics (e.g., via **nstat**) are incident investigation signals, though counter names, update mechanisms, and visibility depend on the kernel.
- You should measure **usage over time** and counter deltas before/after a test, rather than capturing a single number at one point in time. System counters can aggregate across multiple listeners, so do not conclude that all overflows belong to your application.

**Do not blindly run commands to increase sysctl** in production. Kernel tuning requires combining analysis of the limit source, resources, and security specifics. Changing node/container configuration can affect multiple services.

## 7. Backlog and accept rate: why increasing the queue does not solve long-term overload

Suppose there is a wave of clients establishing TCP connections:

- **Arrival rate**: 200 new connections/second.
- **Application accept rate**: 150 connections/second.
- **Difference**: the queue tends to grow by 50 connections/second while those rates hold.

If the initial usable free queue space is about **100 slots**, it can fill up in roughly **2 seconds** in a simple idealized model. In reality you must measure: arrivals are uneven, handshakes are still pending, accept rate changes, the kernel may cap/retry, and connections may close.

~~~text
Incoming connections (lambda) ---> [ ACCEPT QUEUE ] ---> accept() (mu)
                                         |
                                      backlog
           lambda > mu long-term => queue tends to fill up
           lambda <= mu steady   => queue has a chance to drain
~~~

**Increasing backlog helps absorb temporary bursts**, giving the app more time to pull connections from the queue. If the arrival rate continuously exceeds the accept rate, a large queue still fills up eventually and may only turn fast failures into longer wait times. Real capacity must be increased by improving the accept loop, reducing blocking work on the accept thread, scaling instances properly, and managing downstream resources.

### Distinguishing queues in server architecture

~~~text
Kernel SYN state -> Kernel accept queue -> Java accept()
                                        |
                                        v
                                 Thread pool queue
                                        |
                                        v
                             Parse/TLS/DB/Business logic
~~~

- **Accept queue** holds connections not yet accepted by the app.
- **ExecutorService queue** holds tasks already created by the app after accept. It can fill up when there are too few workers or request processing is too slow; this is a **different queue**.
- **Socket receive buffer** holds data for a single connection. It is not backlog.
- **Connection pool** to the database is also a different resource; a large backlog does not increase DB connections or DB throughput.

A slow server pattern is calling **accept()**, then performing **read request + call DB + write response** directly on the same thread before accepting again. Even if each processing takes 500 ms, the listener can only accept about two connections/second in that model, causing the queue to fill quickly when a burst arrives. The typical design is to keep the accept loop lightweight, hand off accepted sockets to workers with a **bounded count**, and apply backpressure/admission control.

## 8. Designing the accept loop and overload control

For servers with significant connection volume:

1. **Treat backlog configuration as a requested value**, determine OS limits, and then benchmark with the expected workload.
2. **Do not perform slow tasks in the accept loop**. Each accept should quickly hand off the Socket to a worker/event loop, or close it cleanly when additional load cannot be accepted.
3. **Bound worker queues and active connections**. Unbounded queues inside the JVM can cause the heap to grow even when the kernel accept queue is not full.
4. **Use appropriate timeouts and deadlines**. **ServerSocket.setSoTimeout(...)** applies to *waiting for accept*; it does not change backlog and does not automatically time out processing of already-accepted clients. **Socket.connect(address, timeout)** limits client-side connect wait time per the API contract; it provides no guarantee that the server has accepted or processed.
5. **Monitor p95/p99 connect latency, accept rate, pending queue, worker saturation, FD, CPU, memory, TCP retransmissions, and errors/timeouts**, while also cross-checking logs at the LB/proxy.
6. **Run load tests with varying long/short-lived connections**. Bursts of new connections can fill the accept queue even when average request throughput is low; keep-alive reduces connection establishment frequency, but requires protocol support and the ability to manage idle connections.
7. **Prioritize measuring and fixing bottlenecks**: workers blocked on DB, heavy TLS handshakes, CPU parsing, GC, or FD limits will not disappear on their own by increasing backlog.

### Why does a backlog of 10,000 not mean 10,000 active clients?

After **accept()** returns a Socket, the connection is no longer waiting in the accept queue. A server can hold many thousands of accepted Sockets if resources and architecture allow, even when the requested backlog is small. Conversely, a listener with a large backlog may still process only a few requests/second if the downstream application is slow.

**Do not use backlog to limit concurrent users.** Manage active connections, sessions, requests, processing queues, and resources with separate policies.

### Do ServerSocketChannel, Selector, and virtual threads change backlog?

**They do not change the nature of the OS listen queue.** Blocking ServerSocket, NIO ServerSocketChannel with Selector, and servers using virtual threads (Java 21+) all require the kernel to accept incoming connections. These models change how the application accepts, dispatches, and processes Sockets after accept, which can improve queue drain rate. However, the listener's backlog parameter is still subject to OS rules; virtual threads are not a way to bypass somaxconn.

## 9. Common observation and interpretation mistakes

| Symptom | Possible related causes | What to check further |
|---|---|---|
| connect latency increases during a burst | Slow listener/accept queue, handshake retries, network/LB | ss, TCP counters, accept time, network trace |
| connect timeout | Network, firewall, load balancer, listener queue, retransmissions | Do not immediately conclude “backlog too small” |
| Connection refused | No matching listener, rejected by OS/firewall, routing/config error, or queue conditions | Port/IP/namespace, whether listener exists, counters |
| accept() takes a long time to return | No ready connection, network conditions, accept's own timeout | Do not assume by default that the queue is too small |
| Slow requests after successful connect | Workers, database, TLS, CPU, app queue | Application metrics; backlog may be completely normal |
| Java OutOfMemoryError with many sockets | Heap/direct buffers limit, task queue, threads, object lifecycle | Cannot be cured by increasing backlog |
| Many SYN_RECV | Pending handshakes, client/network/SYN flood, or heavy load | tcp_max_syn_backlog, syncookies, counters, network |
| ss Recv-Q rising near the limit | Many completed connections waiting for accept (on Linux where the column has this meaning) | Accept rate, CPU/GC, file descriptors, kernel version |

**Observations must be tied to the right socket and the right runtime environment.** Containers, Kubernetes pods, reverse proxies, or load balancers have their own listeners; the queue at an edge proxy is not the same as the queue at the Java backend server. If load testing through a load balancer, a successful connect() on the client may only prove that the LB side accepted the connection.

**Increasing backlog is not a fix for a SYN flood.** SYN cookies and attack mitigation mechanisms are a separate TCP-layer protection issue; backlog for pending fully-established connections does not replace rate limiting, firewall, and application resource protection policies.

## 10. How to verify across Windows, BSD, macOS, and Linux

**The Java API is portable in method signatures, but detailed backlog semantics are not portable.**

- **Linux**: there are two commonly separated aspects, handshake requests and accept queue; listen backlog is capped by somaxconn; there are corresponding sysctls and statistics tools.
- **BSD/macOS**: the kernel may manage queues, limits, and the relationship between backlog and handshakes differently. Do not apply Linux models, counters, or values directly to other systems.
- **Windows**: backlog is passed down to the Winsock/implementation layer; effective limits and overload behavior follow Windows APIs and OS versions. Do not use Linux sysctl or ss to reason about it.
- **Container/VM**: the same Java image can still run on different kernels and namespaces; some limits are set on the host, proxy, or virtual network; you must measure in the specific deployment environment.

When comparing between two machines, you must record the **JDK version**, **OS/kernel version**, **bind address**, **requested backlog**, OS configuration, whether a proxy/LB is present, how load is generated, measurement duration, and worker/server state. Without this data, a conclusion like "backlog=128 is faster than backlog=64" is usually unfounded.

## 11. Practice exercises

### Exercise 1 — Java's Backlog API

Run **BacklogBasicsDemo.java**, changing requestedBacklog from 8 to 1 and then 512. Verify that **one** connection succeeds on loopback and explain why all three identical results do not prove that the kernel used those exact three queue sizes.

### Exercise 2 — Observing while the server does not accept

Run **BacklogProbeDemo.java** with backlog 1, 2, and 16. Record Connected/Timed out/Other errors for each run. Repeat a few times and check the OS configuration. Why can the total results fluctuate, and why cannot a single connect run be used as an exact measurement of queue slots?

### Exercise 3 — Adding an accept loop

Add a worker that continuously accepts and holds Sockets in a bounded collection; compare with the version that does not accept at all. Be sure to close all Sockets and stop the worker properly. Explain how draining connections from the accept queue differs from completing request processing.

### Exercise 4 — Analyzing the two queues

On Linux, record **net.core.somaxconn**, **net.ipv4.tcp_max_syn_backlog**, **net.ipv4.tcp_syncookies**, and observe **ss -lnt**. Classify which metrics relate to incomplete handshakes and which relate to completed connections waiting for accept. Do not modify sysctl when only observing.

### Exercise 5 — Slow app processing experiment

In a server you control, compare two architectures: (A) processing slow requests right after accept on a single thread; (B) accepting quickly and offloading processing to bounded workers. Under increasing load, measure connect latency, accept rate, worker queue depth, memory, and error rates. Why does simply increasing backlog fail to save throughput when downstream is constrained?

## 12. Comprehension check questions

**1. Is backlog the maximum number of active connections?** No. It relates to the queue request for connections waiting for the application to accept, whereas already-accepted active connections are managed and limited by other mechanisms.

**2. Does new ServerSocket(port, 10) guarantee that the 11th connection is rejected?** No. Specific semantics and limits depend on the implementation/OS, plus timing and handshake state.

**3. Does backlog in modern Linux limit the SYN queue or the accept queue?** Per the listen(2) documentation since Linux 2.2, TCP backlog only limits the queue of fully-established connections waiting for accept; incomplete requests are governed by other mechanisms, including tcp_max_syn_backlog and SYN cookies.

**4. What if Java requests a backlog of 10,000 while somaxconn = 4,096?** On Linux per the listen(2) documentation, a request higher than the limit is capped by the kernel down to somaxconn; you cannot conclude from that alone that the number of successful client connects is exactly 4,096.

**5. Does connect() returning successfully mean the server code has already run accept()?** No. The TCP handshake can complete in the kernel before the app pulls the Socket from the queue; application processing is even less guaranteed.

**6. Does ServerSocket.setSoTimeout(1000) make the backlog longer?** No. It limits the wait time of a blocking accept call, and does not change the number of pending connections for the listener.

**7. Does increasing backlog fix a slow worker pool?** No. It can buffer connection bursts for a short time, but it does not increase CPU, DB throughput, or the number of healthy workers.

**8. Can the actual backlog be measured via ServerSocket.getBacklog()?** There is no such portable method on ServerSocket; OS tools and measurement on the specific deployment environment are required.

## Direct references

- **Java SE 17 — ServerSocket**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- **Java SE 17 — ServerSocketChannel**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html
- **Java SE 17 — AsynchronousServerSocketChannel**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html
- **Linux man-pages — listen(2)**: https://man7.org/linux/man-pages/man2/listen.2.html
- **Linux man-pages — tcp(7)**: https://man7.org/linux/man-pages/man7/tcp.7.html

**Key takeaway:** **backlog is a request for the queue limit of connections waiting to be accepted at the listener, not a limit on all active connections or request processing rate.** The operating system determines the interpretation and effective limit; on Linux there are also somaxconn and separate SYN policies. Proper server design requires accepting fast enough, bounded workers, observability at both kernel and application levels, realistic load testing, and intentional overload handling.