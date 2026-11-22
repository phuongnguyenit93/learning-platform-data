# SO_KEEPALIVE, TCP_NODELAY, SO_LINGER, and Send/Receive Buffers in Java TCP Sockets

**Topic:** Java Advance - networking  
**Group:** TCP with Sockets

When programming TCP with **java.net.Socket**, we often ask: Why does a silent connection not detect that the peer has disappeared? Why do many writes of very few bytes have latency? Why does **close()** sometimes wait, and sometimes cause the receiving side to see **Connection reset**? Why does increasing the buffer still not make the application faster? The four option groups **SO_KEEPALIVE**, **TCP_NODELAY**, **SO_LINGER**, and **SO_SNDBUF/SO_RCVBUF** adjust different behaviors of the **TCP stack in the operating system**.

These are **transport/socket** options; they do not define requests, responses, or business logic processing. A successful **write()** does not prove that the process on the other side has read or committed the transaction. Default values, capacity limits, and effectiveness depend on the operating system, JDK, connection state, and network conditions.

## 1. Layer Diagram and Quick Reference Table

~~~text
Java Application                        Java Application
      │  write bytes / read response          ▲
      ▼                                       │
BufferedOutputStream (if used)        BufferedInputStream (if used)
      │                                       ▲
Socket.getOutputStream()               Socket.getInputStream()
      │                                       ▲
TCP send buffer (OS)                    TCP receive buffer (OS)
      │  TCP segments / ACK / window          ▲
      └──────── IP, network or loopback ──────┘

TCP_NODELAY: choice to use Nagle when sending small data segments
SO_KEEPALIVE: TCP probe when a connection is inactive for a long time
SO_LINGER: close() behavior when there is still unsent data
SO_SNDBUF: kernel-level send buffer size hint
SO_RCVBUF: kernel-level receive buffer size hint
~~~

| Option | Classic Socket API | Primary Effect | What is **not** guaranteed |
| --- | --- | --- | --- |
| **SO_KEEPALIVE** | **setKeepAlive(boolean)** / **getKeepAlive()** | Checks an idle TCP connection using the OS mechanism | Not an application-level heartbeat; no fixed detection time |
| **TCP_NODELAY** | **setTcpNoDelay(boolean)** / **getTcpNoDelay()** | Enables/disables Nagle's algorithm to balance latency and small packets | Does not mean each write creates one packet; does not force the peer to read immediately |
| **SO_LINGER** | **setSoLinger(boolean, int)** / **getSoLinger()** | How **close()** handles unsent TCP bytes | Does not confirm the server has processed the data |
| **SO_SNDBUF** | **setSendBufferSize(int)** / **getSendBufferSize()** | Suggests the socket's send buffer size | Not the number of bytes guaranteed to be writable without blocking |
| **SO_RCVBUF** | **setReceiveBufferSize(int)** / **getReceiveBufferSize()** | Suggests the receive buffer size, related to the TCP receive window | Not the maximum size of a message |

All of the above options can be configured on a socket according to the API and depending on the appropriate state. With **SocketChannel**, the standard equivalents are in **java.net.StandardSocketOptions**. **ServerSocket** has **setReceiveBufferSize(...)** for connections that will be accepted via **accept()**, but it does not have the semantics of “enabling TCP_NODELAY for all clients” through a similar setter on the listener.

## 2. SO_KEEPALIVE: Detecting Broken Idle TCP Connections

### Problem to Solve

Suppose a client maintains a long-lived TCP connection with a server. An intermediate device loses power or the peer is disconnected from the network without sending FIN/RST. The Java program may still have **Socket.isConnected() == true**; this method reflects that the socket was connected, **not a ping** confirming the peer is still alive at the time of the call. During periods with no I/O, TCP may not have received any error indication yet.

**SO_KEEPALIVE** allows the operating system's TCP stack to send **keepalive probes** when the connection has been idle long enough. If the probes receive no response according to the operating system's policy, TCP can mark the connection as broken; subsequent I/O operations may receive an error. The network path and NAT/firewall devices also affect how long an idle connection can survive.

### API and Lifecycle

~~~java
Socket socket = new Socket();
socket.setKeepAlive(true);
boolean enabled = socket.getKeepAlive(); // true if setting the option succeeded
~~~

This is an illustrative **snippet**; it does not create a connection because **connect(...)** has not been called. According to Java StandardSocketOptions, the default state of **SO_KEEPALIVE** is **false**; you should check the actual state of the socket rather than relying on assumptions about the entire environment.

**SO_KEEPALIVE=true does not mean a failure will be detected a few seconds later.** The OS decides the idle time before probing, the interval between probes, the number of retries, and how to conclude the connection is dead. Some systems default to an idle time of about **two hours**, but that number is not a guarantee by Java. TCP keepalive is a transport-layer signal; it cannot prove that the application on the other side is processing requests properly or still has sufficient resources.

### Need a Short Timeout or Application-Level Heartbeat?

- **TCP keepalive** is suitable for detecting certain broken TCP connections after an idle period with low protocol overhead, but detection time is usually long or OS-dependent.
- **Socket.setSoTimeout(ms)** sets a timeout for a waiting **read()** operation on the Socket; it does **not** automatically send keepalives, does not set a timeout for **write()**, and is not a deadline for the entire request.
- **Socket.connect(address, ms)** sets a timeout for the connect step; it does not determine the timeout for reading the response.
- **Application-layer heartbeats** (e.g., **PING/PONG** carrying a message ID) verify that the peer has **read and responded according to the protocol**, which is useful when shorter health checks/deadlines are needed. You still have to consider the sending schedule, jitter, retries, and the possibility of application overload.
- A connection through a load balancer/NAT can be dropped when idle even if SO_KEEPALIVE is enabled; if you need to keep a connection alive in a specific system, you must understand the timeout policies of every hop.

### Advanced Keepalive Timing Tuning

Since Java 11, the **jdk.net** module provides platform-dependent options:

- **ExtendedSocketOptions.TCP_KEEPIDLE**: number of seconds of inactivity before starting probes.
- **ExtendedSocketOptions.TCP_KEEPINTERVAL**: interval in seconds between unanswered probes.
- **ExtendedSocketOptions.TCP_KEEPCOUNT**: maximum number of unanswered probes before considering the connection broken.

API example (only applies when the option is supported by the platform):

~~~java
import jdk.net.ExtendedSocketOptions;
import java.net.Socket;

try (Socket socket = new Socket()) {
    if (socket.supportedOptions().contains(ExtendedSocketOptions.TCP_KEEPIDLE)) {
        socket.setOption(ExtendedSocketOptions.TCP_KEEPIDLE, 60);
    }
    socket.setKeepAlive(true);
}
~~~

This is a **standalone illustrative snippet** and does not connect to a server. When using modules in a modular program, you need to declare the dependency **requires jdk.net;** and check OS support. Do not automatically set the same three parameters on every OS: some platforms do not support the options or have different value limits. Do not use SO_KEEPALIVE in place of timeouts/heartbeats in protocols with strict SLAs.

## 3. TCP_NODELAY: Nagle, Small Packets, and Latency

### What Does Nagle Do?

TCP is a **byte stream** and may have to send many small chunks of bytes. **Nagle's algorithm** is one of the mechanisms that helps limit sending too many small segments while there is still unacknowledged data. When Nagle is enabled, some small writes may be coalesced/delayed instead of immediately creating additional small segments.

~~~text
Application: write("A") → write("B") → write("C")
                        │
        Nagle may delay/coalesce small bytes
                        │
TCP/IP: number of segments and send timing depend on ACK, OS,
        send buffer, congestion/flow control, and link state
~~~

**TCP_NODELAY=true** requests **disabling Nagle**. The option name is easily misunderstood: **true** means *no delay from Nagle*, while **false** means allowing Nagle to operate.

~~~java
socket.setTcpNoDelay(true);   // disable Nagle
boolean noDelay = socket.getTcpNoDelay();

socket.setTcpNoDelay(false);  // allow Nagle
~~~

### When to Consider true?

- **Small, latency-sensitive request/response** protocols: for example, interactive commands, certain RPCs, or sessions requiring fast responses.
- Many very small writes can suffer from the interaction between Nagle and **delayed ACK** on the peer side; real measurements may show delays. Disabling Nagle sometimes improves latency.
- If the program transfers bulk data, small-packet overhead and the number of system calls may matter more. Proper **batching/framing** or application-level buffering is often helpful before toggling the flag.

### Easily Overlooked Limitations

1. **TCP_NODELAY does not disable BufferedOutputStream/BufferedWriter**. If the writer still holds bytes, you must call **flush()** at the right time according to the protocol.
2. **flush()** and **TCP_NODELAY** do not guarantee that the peer has received or that the peer application has processed the data.
3. **TCP_NODELAY=true** does not force **one write() = one segment**, does not disable TCP congestion control, does not disable the peer's delayed ACK, and does not eliminate buffering at TLS, frameworks, or the NIC.
4. Disabling Nagle can increase the number of small packets, CPU/network overhead, and reduce throughput on other workloads. Benchmark with real payloads, RTT, concurrent connections, and real metrics.

**Rule of thumb:** choose according to specific latency/throughput needs. If the application sends one character at a time across many consecutive writes, you should reconsider how requests are batched before deciding solely to enable TCP_NODELAY.

## 4. SO_LINGER: What Happens on close()?

When an application calls **Socket.close()**, there may still be TCP bytes in the send buffer that have not been sent or acknowledged. **SO_LINGER** adjusts **the socket closing behavior in this case**. It does **not** change the timeout for **connect()** or **read()**, and it is not a mechanism to “keep the connection alive for N more seconds” for business logic.

| Configuration | Typical Behavior |
| --- | --- |
| **setSoLinger(false, 0)** | Linger disabled; **getSoLinger() == -1**. **close()** does not wait until all unsent bytes are transmitted; the OS may continue sending the remaining data if possible |
| **setSoLinger(true, 0)** | Linger enabled with timeout **0**: **abortive close**; on TCP this usually forces a close with RST, which can cause the peer to receive **Connection reset** and lose unread bytes |
| **setSoLinger(true, n)** with **n > 0** | When unsent bytes remain, **close()** may block for up to about **n seconds** for the OS to try sending the data; once the limit is reached it may still force-close |

According to Java's **Socket.setSoLinger(boolean, int)**, the timeout unit is **seconds**; the maximum limit is platform-dependent. **getSoLinger()** returns **-1** when disabled. **SO_LINGER** only affects **close**; it does not turn calling **close()** into an application-level acknowledgment.

A few technical points:

- **setSoLinger(true, 0)** is an intentional case, usually to quickly discard a connection; it should **not** be used as the default for protocols that need to deliver a full response.
- **setSoLinger(true, 5)** does not guarantee that the receiver has called read, parsed, or committed the request. TCP ACK (if any) acknowledges at the TCP layer, not business processing.
- When linger is enabled, **close()** can block and impact latency/thread resources, especially when the network is slow or the peer is not reading.
- With **SocketChannel** in **non-blocking mode**, the contract of **SO_LINGER on close** is not defined the same way as for blocking sockets; extra caution is required.
- Do not use SO_LINGER to solve framing. To confirm that all data has been received, read the protocol **response** before closing.

**Closing a connection properly in normal programs** usually means: sending a properly framed request, calling **shutdownOutput()** if needed to signal the end of the sending direction, reading the full response according to the protocol, and then closing the socket using **try-with-resources**. Calling **shutdownOutput()** sends the end-of-stream marker for the write side (TCP FIN in half-close semantics) when appropriate, but it also does not prove that business processing succeeded. Do not use EOF as a delimiter unless the protocol defines it that way.

## 5. SO_SNDBUF and SO_RCVBUF: Kernel TCP Buffers

These two options adjust **hints** for the size of TCP buffers managed by the **operating system**, not the size of a **byte[]**, **ByteBuffer**, or **BufferedWriter** in Java.

~~~text
SENDER                                       RECEIVER
App → Java stream → kernel send buffer       kernel receive buffer → Java stream → App
                              │     network     ▲
                              └──── TCP/IP ─────┘
Writing faster than transmission capacity → send queue may fill up
Reading slower than arrival rate → receive queue fills up, advertised window may shrink
~~~

### SO_SNDBUF: Send Buffer

~~~java
socket.setSendBufferSize(16 * 1024);
int actualSendBytes = socket.getSendBufferSize();
~~~

When an application writes bytes to a TCP socket, the kernel normally accepts the bytes into the send queue and transmits them according to TCP conditions. If the peer reads slowly, the receive window is small, the congestion window shrinks, or the network path is congested, the send buffer can fill up; a **blocking write()** may wait and thus exhibit **backpressure**. With a non-blocking SocketChannel, **write()** may return fewer bytes than requested or **0**, and the caller must wait for readiness before continuing to write.

**setSendBufferSize(n)** is only a **hint**; the OS may apply a different value, auto-tune it, or cap it by policy. Always use **getSendBufferSize()** to observe the reported size. A large size does not prevent packet loss on the network or turn a write into “already delivered to the peer.”

### SO_RCVBUF: Receive Buffer

~~~java
socket.setReceiveBufferSize(32 * 1024);
int actualReceiveBytes = socket.getReceiveBufferSize();
~~~

The receive buffer stores TCP bytes that the kernel has received but the application has not yet read. Receive capacity is related to the **TCP advertised receive window**: if the application reads slowly and the receive buffer fills up, TCP may advertise a small or zero window to ask the sender to slow down. Increasing the receive buffer **can** help high-latency, high-bandwidth links operate more efficiently, but it does not replace the speed of reading, decoding, and processing.

Do not confuse:

- **SO_RCVBUF** with the size of one TCP segment: a single read() may return fewer or more bytes than one segment.
- **SO_RCVBUF** with a fixed number of bytes per read: the caller decides the size of byte[]/ByteBuffer, and read can still return fewer bytes.
- **SO_RCVBUF** with a message limit: the protocol still needs payload limits to avoid unbounded reading and memory allocation.
- OS buffers with application buffers: **BufferedInputStream**, **BufferedOutputStream**, Netty buffers, TLS records, etc. are separate buffering layers.

### Why Does Configuration Timing Matter?

According to the **Socket Javadoc**, if an application needs a TCP receive window larger than **64 KiB**, it should request **SO_RCVBUF** **before connecting**. Specifically:

1. **Client Socket**: call **setReceiveBufferSize(...)** on an unconnected socket, then call **connect(...)**.
2. **Server side**: create an unbound **new ServerSocket()**, call **ServerSocket.setReceiveBufferSize(...)**, and then call **bind(...)**. This is the suggested value for **Socket** instances returned from **accept()**.
3. After **accept()**, call **accepted.getReceiveBufferSize()** to verify the actual value. Changing the value afterward cannot retroactively satisfy all window scaling negotiation requirements during the TCP handshake.

~~~java
ServerSocket listener = new ServerSocket();
listener.setReceiveBufferSize(256 * 1024); // before bind()
listener.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
// Socket accepted = listener.accept();
// int actual = accepted.getReceiveBufferSize();
~~~

The above is a **snippet**; in real use you need to import **java.net.\***, handle exceptions, and close the listener. **setReceiveBufferSize** does not guarantee the kernel allocates exactly 256 KiB; the OS has its own limits and autotuning mechanisms.

### How Much Buffer Is Appropriate?

There is no single right size for every application. For a link with **100 Mbit/s** and **100 ms RTT**, the estimated bandwidth-delay product is approximately:

~~~text
100,000,000 bit/s × 0.1 s ÷ 8 = 1,250,000 bytes ≈ 1.25 MB
~~~

This is only an estimate of the amount of bytes that can be “in flight” at one time when trying to fully utilize throughput. Window scaling, congestion window, kernel autotuning, number of connections, memory pressure, number of copies, read/write patterns, and OS policies together determine effectiveness. Do not conclude that every socket must be configured to **1.25 MB**, or that raising both buffers indefinitely is optimal.

**Tuning is meaningful when you measure** blocked senders, receive queue backlog, RTT/throughput, dropped/retransmitted packets, memory per connection, and tail latency (p95/p99). With many thousands of connections, setting buffers too high can significantly increase memory cost.

## 6. Self-Contained Java 17+ Program on TCP Loopback

The following example sets all four option groups, creates a loopback connection between client and server, sends **ping**, and receives **pong**. Because actual buffer values depend on the OS, the program only checks that the buffers are **positive**, rather than printing a specific number and assuming it is always exact.

Create the file **SocketOptionsDemo.java**:

~~~java
import java.io.DataInputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class SocketOptionsDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket()) {
            // Set receive-buffer hint before bind for accepted sockets.
            listener.setReceiveBufferSize(64 * 1024);
            listener.bind(new InetSocketAddress(loopback, 0));

            try (Socket client = new Socket()) {
                client.setKeepAlive(true);        // Enable TCP keepalive.
                client.setTcpNoDelay(true);       // Disable Nagle.
                client.setSoLinger(false, 0);     // Do not linger on close.
                client.setSendBufferSize(16 * 1024);
                client.setReceiveBufferSize(32 * 1024);
                client.connect(new InetSocketAddress(
                        loopback, listener.getLocalPort()), 3000);
                client.setSoTimeout(3000);

                try (Socket serverSide = listener.accept()) {
                    serverSide.setSoTimeout(3000);

                    System.out.println("keepalive=" + client.getKeepAlive());
                    System.out.println("nodelay=" + client.getTcpNoDelay());
                    System.out.println("linger=" + client.getSoLinger());
                    System.out.println("sendBufferPositive=" +
                            (client.getSendBufferSize() > 0));
                    System.out.println("receiveBufferPositive=" +
                            (client.getReceiveBufferSize() > 0));
                    System.out.println("acceptedBufferPositive=" +
                            (serverSide.getReceiveBufferSize() > 0));

                    client.getOutputStream().write(
                            "ping".getBytes(StandardCharsets.UTF_8));
                    byte[] request = new byte[4];
                    new DataInputStream(serverSide.getInputStream())
                            .readFully(request);
                    System.out.println("request=" +
                            new String(request, StandardCharsets.UTF_8));

                    serverSide.getOutputStream().write(
                            "pong".getBytes(StandardCharsets.UTF_8));
                    byte[] response = new byte[4];
                    new DataInputStream(client.getInputStream())
                            .readFully(response);
                    System.out.println("response=" +
                            new String(response, StandardCharsets.UTF_8));
                }
            }
        }
    }
}
~~~

Compile and run with JDK 17 or later in the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 SocketOptionsDemo.java
java SocketOptionsDemo
~~~

**Expected output in an environment that allows creating TCP loopback sockets:**

~~~text
keepalive=true
nodelay=true
linger=-1
sendBufferPositive=true
receiveBufferPositive=true
acceptedBufferPositive=true
request=ping
response=pong
~~~

An equivalent example was executed in **JShell on JDK 24**, producing these exact output lines; the APIs used are available in Java 17. In restricted network environments or if the OS rejects an option, the program may throw an exception instead of printing the output above.

**Execution flow explanation:**

1. **new ServerSocket()** is unbound; **setReceiveBufferSize** before **bind** sets the receive buffer hint for connections that will be accepted.
2. **bind(loopback, 0)** asks the OS to choose an ephemeral port, without using the external network or DNS.
3. Create an unconnected client **Socket**, then enable SO_KEEPALIVE, TCP_NODELAY, disable linger, and set send/receive buffers. Each setter only adjusts a socket option; it does not change protocol contents.
4. **client.connect(..., 3000)** establishes the connection with a dedicated connect timeout. Then **setSoTimeout(3000)** limits the **read** wait time (on the client); similarly on serverSide.
5. **listener.accept()** returns the socket for an established connection. This is a **different** socket from listener.
6. Send exactly **4 ASCII UTF-8 bytes**, using **DataInputStream.readFully(byte[4])** to receive all 4 bytes or get an EOF error. This avoids assuming a single **read()** always retrieves all the data. In a real protocol, a length-prefix, delimiter, or message framing is needed to determine length.
7. Print the option states and the ping/pong results. Buffers are checked with **> 0** because the OS may adjust sizes.
8. **try-with-resources** closes the sockets. In the example, linger is disabled; an abortive close via **setSoLinger(true, 0)** is not performed.

**Note:** A successful ping/pong proves that the two endpoints exchanged 4 bytes according to a minimal protocol over loopback; it does **not** prove that changing TCP_NODELAY or buffer sizes improved performance. To test performance, you need load benchmarks, TCP metrics monitoring, and comparisons across multiple runs.

## 7. With SocketChannel and StandardSocketOptions

If using **java.nio.channels.SocketChannel**, the options are in **StandardSocketOptions**; this is an alternative way to configure the same group of options on an Internet TCP socket:

~~~java
import java.net.StandardSocketOptions;
import java.nio.channels.SocketChannel;

try (SocketChannel channel = SocketChannel.open()) {
    channel.setOption(StandardSocketOptions.SO_KEEPALIVE, true);
    channel.setOption(StandardSocketOptions.TCP_NODELAY, true);
    channel.setOption(StandardSocketOptions.SO_SNDBUF, 16 * 1024);
    channel.setOption(StandardSocketOptions.SO_RCVBUF, 32 * 1024);
    channel.setOption(StandardSocketOptions.SO_LINGER, -1);
    // channel.connect(remoteAddress); // requires a real target address when used
}
~~~

This is a **configuration snippet**, not a connection and data-exchange demo. **SO_LINGER** in NIO is an **Integer**: negative disables it, **0** enables linger with 0 (may force-close), and positive enables a timeout in seconds. Only rely on the defined linger behavior for **blocking mode**; with a **non-blocking SocketChannel**, the close behavior when linger is enabled is not defined the same as in blocking mode.

**SocketChannel.supportedOptions()** and **Socket.supportedOptions()** help discover the options supported by the platform; extended options or other socket types do not necessarily support the entire list. With **ServerSocketChannel**, check the listening channel's API and set the receive-buffer hint before **bind** if a large TCP window is required. NIO **Selector** and partial writes/reads still require framing and backpressure management, regardless of buffer configuration.

## 8. Choosing Configuration by Scenario

| Scenario | Approach | Avoid Jumping to Conclusions |
| --- | --- | --- |
| Long-idle TCP connection where the peer may disappear | Consider **SO_KEEPALIVE**, check OS timeouts, add application heartbeats if there is an SLA | Enabling keepalive does not create a health check every 5 seconds |
| Small RPCs needing low latency | Measure the effect of **TCP_NODELAY=true**, while also fixing batching/flush | true does not guarantee every write is sent immediately |
| Sending bulk bytes and prioritizing throughput | Write in blocks, profile, consider buffers and OS autotuning | Do not assume a larger buffer is always better |
| Slow **close()** or threads stalling for a long time | Check **SO_LINGER**, unsent bytes remaining, network load, and the peer | SO_LINGER is not a read/connect timeout |
| Peer reports **Connection reset** after server closes | Check for forced close, **SO_LINGER=0**, unread data, and middleboxes | Do not blame every RST on a single option |
| Poor throughput on high-RTT networks | Measure bandwidth-delay product, TCP window, BDP, congestion, SO_RCVBUF before connect/bind | Buffers cannot exceed link or CPU limits |
| **write()** blocks when the server reads slowly | Measure send queue, advertised receive window, and receiver application speed | Increasing the send buffer only delays backpressure |
| Thousands of concurrent connections using too much RAM | Measure memory/connection, buffer defaults, and OS limits | Do not force large buffers on every socket |

There is no single “standard” parameter set for every server. You need to know whether the protocol is real-time interactive, upload, streaming, or batch, as well as the number of concurrent connections, payload sizes, RTT, packet loss, idle timeout needs, and memory limits.

## 9. Debugging and Observing the Actual Behavior

A systematic diagnostic approach:

1. **Verify which socket the option is applied to.** The client Socket and the Socket from **ServerSocket.accept()** are **two different endpoints**; settings on the client do not automatically set flags on the peer. The listener only has options appropriate for a server socket.
2. **Print getters, do not just log setters.** **getKeepAlive()**, **getTcpNoDelay()**, **getSoLinger()**, **getSendBufferSize()**, and **getReceiveBufferSize()** show the values reported by Java/OS after applying them.
3. **Distinguish three kinds of waiting:** connect timeout, read timeout, and waiting due to send-buffer/backpressure or linger on close. They have different causes and remedies.
4. **Check the configuration order** of the receive buffer before connect/bind when wanting a large window; monitor the actual value of the accepted Socket.
5. **Measure the protocol end-to-end:** client send latency, server reading the complete message, server processing, client receiving the complete response. TCP keepalive/Nagle/linger do not replace business logs.
6. **Observe OS TCP state when needed:** Linux **ss -tinm** and packet capture tools when permitted; Windows has **netstat -ano** along with appropriate network diagnostic tools. How queues/windows are displayed specifically depends on the OS and permissions.
7. **Benchmark one change at a time:** keep payload, simulated RTT or test environment, concurrency, CPU, p50/p95/p99, and throughput constant; change one option per run to easily isolate its impact.

### Common Misconceptions

- **“SO_KEEPALIVE is an HTTP keepalive or WebSocket ping.”** No. TCP probes are completely different from application messages.
- **“Enabling SO_KEEPALIVE detects lost connections immediately.”** No. Idle time and probe counts depend on the OS.
- **“TCP_NODELAY=true means there are no buffers.”** No. The TCP send buffer, Java BufferedWriter, TLS, and other layers still exist.
- **“TCP_NODELAY automatically makes small packets faster in every case.”** No. Effectiveness depends on workload, congestion, and delayed ACK; overhead may increase.
- **“setSoLinger(true, 0) waits 0 seconds and closes cleanly.”** Easily mistaken: that is usually an **abortive close/RST**, risking data loss.
- **“SO_LINGER=5 guarantees the peer finished processing the request.”** No; at most it adjusts the transport wait window on close, with no application acknowledgment.
- **“setSendBufferSize(1_000_000) guarantees allocating 1 MB.”** No; the setter is a hint, and the OS can alter/limit it.
- **“A large receive buffer means read() gets a whole message.”** No. TCP has no message boundaries; code still needs framing.
- **“setReceiveBufferSize after accept is always equivalent to setting before bind.”** No, especially when requesting a TCP receive window larger than 64 KiB.
- **“Socket.isConnected() returning true means the peer is still alive.”** No. The method state does not verify peer health in real time.

## 10. Self-Check Exercises

1. A client uses a long-lived connection with no requests for 10 minutes, and the peer disappears. Why does **SO_KEEPALIVE=true** not guarantee detection within 10 seconds? What is needed when the detection SLA is 10 seconds?
2. An application writes 100 times, 1 byte each time. Why does **TCP_NODELAY=true** still not prove that 100 TCP segments are created? If using **BufferedOutputStream**, what additional operation must be observed?
3. A server enables **setSoLinger(true, 0)** and closes before finishing sending the response. What might the client see, and why is using **close()** instead of an application response wrong?
4. A client sends 2 MiB and **write()** blocks even after increasing **SO_SNDBUF**. State three causes related to the peer/window/network and the metrics that should be measured.
5. A server needs a receive window larger than 64 KiB. What is the initialization order for **ServerSocket**, **setReceiveBufferSize**, **bind**, and **accept**? Why must the accepted socket be checked?
6. A non-blocking NIO SocketChannel returns **write() = 0**. Should you continuously busy-loop and increase SO_SNDBUF indefinitely? Explain readiness, backpressure, and memory bounds.

**Knowledge summary:** **SO_KEEPALIVE** addresses **idle/liveness at the TCP layer**, **TCP_NODELAY** affects **Nagle and the latency of small writes**, **SO_LINGER** affects **close behavior when unsent bytes remain**, and **SO_SNDBUF/SO_RCVBUF** hint at **kernel buffer sizes and flow control**. No option replaces protocol framing, application acknowledgment, timeouts, or real performance testing.

**API sources for accurate reference:** [Socket (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html), [ServerSocket (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html), [StandardSocketOptions](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/StandardSocketOptions.html), [SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html), and [ExtendedSocketOptions](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.net/jdk/net/ExtendedSocketOptions.html).