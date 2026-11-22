# Checking `supportedOptions` and Differences Between JDKs and Operating Systems When Working with TCP Sockets

A Java program may compile cleanly on JDK 17 yet fail to enable a socket option when running on Windows, Linux, or a different JDK build. Even when `setOption(...)` succeeds, the measured buffer size or TCP behavior may differ from the requested value. To build reliable TCP applications, you need to distinguish between **the option name existing in the API**, **the socket type supporting it**, **the configuration being accepted**, and **the actual effect determined by the kernel**.

This lesson focuses on `java.net.Socket`, `java.net.ServerSocket`, and NIO `SocketChannel`, `ServerSocketChannel` on Java 17+, using `supportedOptions()` as the starting point and comparing the impact of JDK version, JDK vendor, operating system, protocol family, and socket state.

## 1. Four Different Layers of Verification

~~~text
1. Does the Java API declare SocketOption<T>?
               |
               v
2. socketInstance.supportedOptions().contains(option)?
               |
               v
3. Does setOption(option, value) succeed?
               |
               v
4. What does getOption(option) return, and how does TCP/OS behave?
~~~

| Layer | The Right Question | Example |
| --- | --- | --- |
| **Present in the API** | From which JDK is the constant `StandardSocketOptions.SO_REUSEPORT` available? | Available since Java 9, but presence in the API does not mean every OS supports it |
| **Supported by the instance** | Is `channel.supportedOptions().contains(SO_REUSEPORT)` true on this channel? | May be `true` on one JDK/OS combination and `false` on another |
| **Configuration accepted** | Does `setOption(SO_REUSEPORT, true)` throw an exception? Was it set at the right time? | Some options must be set **before bind** to take effect |
| **Actual value/effect** | What does `getOption` return? How does the OS handle bind, ACK, TCP buffers, and keep-alive? | `SO_RCVBUF` may be adjusted by the kernel; `SO_REUSEADDR` does not guarantee always being able to rebind the port |

Therefore, the right verification pattern is typically:

~~~java
// Illustrative snippet inside a method that has a channel of type SocketChannel.
if (channel.supportedOptions()
        .contains(StandardSocketOptions.TCP_NODELAY)) {
    channel.setOption(StandardSocketOptions.TCP_NODELAY, true);
    Boolean effective =
            channel.getOption(StandardSocketOptions.TCP_NODELAY);
}
~~~

Here you must `import java.net.StandardSocketOptions;`; `setOption/getOption` may throw `IOException`. This snippet only illustrates the order of operations; standalone programs and full error handling appear in later sections. **Being present in `supportedOptions` does not mean a `setOption` call can never fail.**

## 2. Which Socket Types Use `supportedOptions()`?

### 2.1. Classic Socket API: `java.net`

Since Java 9, the three main types have the following instance API:

~~~java
Set<SocketOption<?>> clientOptions = socket.supportedOptions();
Set<SocketOption<?>> serverOptions = serverSocket.supportedOptions();
~~~

- `Socket` is the client-side TCP connection endpoint or an `accept`ed socket.
- `ServerSocket` is a listening socket, **not** a connected TCP data stream. It typically supports options related to bind/listen/receive buffer, and does not necessarily support `TCP_NODELAY`.
- `SocketOption<T>` describes the option name and value type (`name()`, `type()`). For example, the value type `T` is `Boolean` for `TCP_NODELAY` and `Integer` for `SO_RCVBUF`.
- `Socket.supportedOptions()` and `ServerSocket.supportedOptions()` return a `Set<SocketOption<?>>`; this set may include implementation-extended options and may be empty if `SocketImpl` cannot be created. The API still allows retrieving the supported set **after the socket has been closed**, but that does not make `getOption/setOption` on a closed socket work again.

Do not create your own `new SocketOption<...>()` just to match a name and compare strings. When checking standard options, use the `StandardSocketOptions.TCP_NODELAY` / `SO_RCVBUF` constants directly; for extended options, use the constants from their corresponding module.

Since Java 9, `Socket`, `ServerSocket`, and `DatagramSocket` all have `getOption`, `setOption`, and `supportedOptions`. The legacy utility `jdk.net.Sockets` has been **deprecated since JDK 16**; on Java 17+, call the methods directly on the socket instance. When maintaining Java 8 code, check the JDK 8 API separately and do not mistakenly call instance methods added in Java 9.

### 2.2. NIO Channels: `java.nio.channels`

`NetworkChannel` declares three methods:

~~~java
Set<SocketOption<?>> supportedOptions();
<T> T getOption(SocketOption<T> name) throws IOException;
<T> NetworkChannel setOption(SocketOption<T> name, T value)
        throws IOException;
~~~

These are **illustrative signatures from the interface**; learner Java programs do not rewrite them. Concrete TCP channels `SocketChannel` and `ServerSocketChannel` may specialize the return type for `setOption`, and also have their own open, bind, connect, and accept methods.

- `SocketChannel.open()` creates a connecting TCP/IP channel, initially not connected to a peer; you can query `supportedOptions()` immediately.
- `ServerSocketChannel.open()` creates a listening channel, initially unbound; you can query support and configure certain options before binding.
- `SocketChannel.open(StandardProtocolFamily.UNIX)` (on JDKs that support it) creates a **Unix-domain socket**, not a regular TCP/IP socket; its option set and semantics differ. Do not use the option set of the UNIX family to conclude TCP support over IP.
- Customized `SelectorProvider`/`SocketImpl` implementations may expose a different option set than the JDK default implementation.

The Javadoc specifies that `NetworkChannel.supportedOptions()` continues to return the option set even if the channel is closed. Conversely, `getOption/setOption` on a closed channel may throw `ClosedChannelException`. **Supported** here means *advertised capability* for the running object type/implementation, not connection state, network quality, or remote server agreement.

### 2.3. Do Not Confuse TCP Options with Other Mechanisms

- `StandardSocketOptions` is the set of options of type `SocketOption<T>`; it is not a list of every socket feature in Java.
- `Socket.setSoTimeout(milliseconds)` controls the **blocking read** timeout, whereas `Socket.connect(address, timeout)` controls the connection timeout. They do not appear as `StandardSocketOptions.SO_TIMEOUT`; `supportedOptions` is no substitute for reading the timeout APIs.
- `ServerSocket.setSoTimeout` applies to `accept`, not TCP keep-alive.
- `SO_KEEPALIVE` is an OS-level TCP idle probing mechanism, not equivalent to an application heartbeat or service health check.
- `IP_MULTICAST_IF`, `IP_MULTICAST_TTL`, and `SO_BROADCAST` are for datagrams/multicast, not default choices to apply to TCP sockets.
- `SSLSocket` also has its own API for TLS (protocol/cipher/handshake). Socket `supportedOptions` cannot be used instead of `getSupportedProtocols()` or to inspect negotiated TLS parameters.

## 3. Common TCP Options and System Dependence

| Option | Type `T` | Usually Relevant To | What Can Be Expected / Things to Note |
| --- | --- | --- | --- |
| `TCP_NODELAY` | `Boolean` | TCP client/connected socket | Enable to disable Nagle's algorithm; does not guarantee every `write` reaches the peer immediately |
| `SO_KEEPALIVE` | `Boolean` | TCP client/connected socket | Enables the OS TCP keep-alive mechanism; timing/retries and effectiveness depend on the OS |
| `SO_SNDBUF` | `Integer` | TCP data-sending socket | Send buffer size is a **hint**; the OS may adjust it, read back with `getOption` |
| `SO_RCVBUF` | `Integer` | TCP receiving socket, and some listening sockets | Receive buffer size is a **hint**; actual value/limits depend on the OS |
| `SO_REUSEADDR` | `Boolean` | Bind socket/listening socket | Semantics depend on socket type/OS; set **before bind**; does not guarantee port-reuse bind will succeed |
| `SO_REUSEPORT` | `Boolean` | Some listening TCP sockets | Support and semantics depend on socket type/OS, may allow multiple listeners to bind the same address:port; always probe first |
| `SO_LINGER` | `Integer` (seconds) | Connected TCP socket | Controls `close` handling when unsent data remains; intended for blocking sockets, do not use indiscriminately on non-blocking channels |
| `IP_TOS` | `Integer` | Some IP sockets | ToS/traffic class value is a hint; network infrastructure may ignore or alter it |

The list above intentionally says **“usually relevant to”**—not every option is guaranteed on every socket type. Read the `Socket`/`ServerSocket` or `SocketChannel`/`ServerSocketChannel` Javadoc and **query the actual instance** to get the usable list.

### 3.1. Buffers: `setOption(SO_RCVBUF, 16384)` Does Not Promise an Exact Size

With `SO_RCVBUF`, the requested configuration value is a *hint* to the networking implementation. The OS may enforce min/max bounds, adjust internally, or allocate a size that reads back differently from the requested number; the same applies to `SO_SNDBUF`. A test like:

~~~java
channel.setOption(StandardSocketOptions.SO_RCVBUF, 16 * 1024);
int effective = channel.getOption(StandardSocketOptions.SO_RCVBUF);
~~~

only makes sense when the channel supports the option, is still open, and the requested value is valid. **Do not assert `effective == 16384` as a portable requirement**. If the application requires a minimum buffer by design, check the reported value and establish a fallback/fail policy with clear messaging, while also measuring performance under real TCP traffic.

### 3.2. `SO_REUSEADDR` Differs from `SO_REUSEPORT`

`SO_REUSEADDR` has semantics related to reusing an address/port in certain TCP states; operating systems may handle `TIME_WAIT` and bind policies differently. `SO_REUSEPORT` (in `StandardSocketOptions` since Java 9) is intended to support port reuse on supporting implementations; for TCP it *usually* allows multiple listening sockets on the same address and port. The two options **are not two interchangeable names for the same behavior**.

Workflow for a listener that needs `SO_REUSEPORT`:

1. Open the listening socket/channel.
2. Query `supportedOptions().contains(StandardSocketOptions.SO_REUSEPORT)`.
3. If supported, set `setOption(SO_REUSEPORT, true)` **before binding**; still catch any errors that may occur.
4. Bind to an allowed address/port, then test connection distribution on the **target OS/JDK**. Do not infer from a single successful `setOption` call that the kernel is distributing incoming connections as desired.

Do not experiment with overlapping binds on production ports. For tests, use a loopback address / controlled port and clean up resources after running.

### 3.3. Keep-Alive and Extended Parameters

`SO_KEEPALIVE=true` asks the OS to use TCP keep-alive when a connection is idle. This is not a timeout for a `read` call, does not monitor application logic, and does not always detect a failed peer within the timeframe developers imagine.

The JDK-specific module `jdk.net` has `ExtendedSocketOptions.TCP_KEEPIDLE`, `TCP_KEEPINTERVAL`, and `TCP_KEEPCOUNT` (introduced in JDK 11) to express probe timing/count parameters in **seconds or counts**. These options may **not be available on a given OS or socket type**, and accepted values depend on the kernel. Only when a capability probe returns true is there reason to try get/set; some extended options are also read-only, such as `SO_INCOMING_NAPI_ID`. Do not treat “the constant exists in the class” as permission to call `setOption`.

`ExtendedSocketOptions.TCP_QUICKACK` (JDK 10+) is also OS-dependent; according to the Javadoc it is **not a permanent switch**, because subsequent TCP processing may change the delayed ACK state again. Therefore, from a value read back immediately after setting, you cannot guarantee that all future ACKs will follow a fixed policy.

### 3.4. `SO_LINGER` and Channel State

`SO_LINGER` takes a negative value to disable linger; a non-negative value is the duration in seconds for `close` handling when pending data remains. The Javadoc notes it is intended for **blocking sockets**; when enabled on a non-blocking socket, `close` behavior is undefined. Do not try to set linger “to be faster” while ignoring blocking conditions, application protocol, and the impact on unsent data.

## 4. Why Do JDKs and OSes Differ?

### 4.1. API Version Is Not Identical to Runtime Support

| Java Milestone | Relevant Detail |
| --- | --- |
| **Java 7** | `NetworkChannel` and `StandardSocketOptions` for NIO channels |
| **Java 9** | `Socket/ServerSocket/DatagramSocket` gain instance methods `supportedOptions()`, `setOption`, `getOption`; `SO_REUSEPORT` is standardized as a constant |
| **JDK 10** | `jdk.net.ExtendedSocketOptions.TCP_QUICKACK` added in JDK-specific API |
| **JDK 11** | Extended TCP keep-alive tuning options `TCP_KEEPIDLE`, `TCP_KEEPINTERVAL`, `TCP_KEEPCOUNT` added |
| **JDK 16** | Legacy utility `jdk.net.Sockets` deprecated in favor of the Java 9 instance API |
| **JDK 17, 21 and later** | The same option name may appear in documentation, yet the actual `supportedOptions` set still depends on OS, build, socket type, and provider |

In particular, compiling/running with `javac --release 17` only checks compilation against the corresponding API/bytecode; it **does not emulate** syscalls, buffer limits, kernel socket options, or the extended options set of the real runtime. A JDK 21 build on Windows and a JDK 21 build on Linux do not have to expose the exact same option set either. Do not treat a `supportedOptions` table printed from a personal machine as the “Java 17 standard” for all machines.

### 4.2. Operating System, Kernel Configuration, and Permissions

- **The kernel TCP stack** determines which options have a backing implementation, what the buffer/keep-alive limits are, and the exact semantics of port reuse.
- **Operating system version** can change exposed options even with the same JDK feature version.
- **JDK vendor/build/patch** can change the implementation, networking provider, or how options map to the OS.
- **Containers, sandbox policies, or process privileges** may restrict socket creation, option changes, or binding; `supportedOptions` does not guarantee the final operation is permitted by the OS.
- **Protocol family** (IPv4/IPv6, TCP/IP vs. Unix-domain) changes the set of meaningful options. The fact that `SocketChannel.open(StandardProtocolFamily.UNIX)` exists in the JDK does not prove the current environment supports Unix-domain sockets.
- **State/lifecycle** matters: some options should be set before `bind`/`connect`, some only make sense after a TCP connection has data, and any `getOption/setOption` on a closed channel may fail.

Record **java.runtime.version**, **java.vendor**, **os.name**, **os.version**, **os.arch**, protocol family, and socket type when comparing two machines. Add container/kernel configuration if there is an actual runtime difference; only relevant factors need to go into production logs.

### 4.3. Reading the Contract in the Right JDK Version

When migrating from JDK 17 to 21, do not only compare constant names: read the `Socket options` section in the Javadoc of the exact `Socket`, `ServerSocket`, `SocketChannel`, and `ServerSocketChannel` classes; then read `StandardSocketOptions` and `jdk.net.ExtendedSocketOptions` for the exact JDK being deployed.

Three different sources need to be cross-checked:

1. **The spec** states standard options and value types (such as `SO_RCVBUF` being `Integer`).
2. **The Javadoc of the exact socket/channel** lists the standard options that socket type supports, along with the possibility of additional implementation-specific options.
3. **The runtime `supportedOptions` output** confirms the capabilities of the open instance in the real environment. You still need to `set/get` to know the accepted and readback values.

For example, the `jdk.net.ExtendedSocketOptions` documentation on JDK 21 has entries that JDK 17 documentation does not. Yet even a new field appearing in a JDK's Javadoc does not mean every OS supports that option. Nor are JDK-specific APIs a compatibility guarantee across all Java SE implementations.

## 5. Java 17+ Program: Exactly Listing Options on the Running Machine

Create the file **`TcpOptionInventory.java`**:

~~~java
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketOption;
import java.net.StandardSocketOptions;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.util.Comparator;
import java.util.Set;

public final class TcpOptionInventory {
    private static void printOptions(
            String label, Set<SocketOption<?>> options) {
        System.out.println(label + ":");
        options.stream()
                .sorted(Comparator.comparing(SocketOption::name))
                .forEach(option -> System.out.println(
                        "  " + option.name()
                        + " (" + option.type().getSimpleName() + ")"));
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Runtime: "
                + System.getProperty("java.runtime.version"));
        System.out.println("Vendor: "
                + System.getProperty("java.vendor"));
        System.out.println("OS: "
                + System.getProperty("os.name"));
        System.out.println("Architecture: "
                + System.getProperty("os.arch"));

        try (Socket client = new Socket();
             ServerSocket listener = new ServerSocket();
             SocketChannel clientChannel = SocketChannel.open();
             ServerSocketChannel listenerChannel =
                     ServerSocketChannel.open()) {

            printOptions("Socket", client.supportedOptions());
            printOptions("ServerSocket", listener.supportedOptions());
            printOptions("SocketChannel",
                    clientChannel.supportedOptions());
            printOptions("ServerSocketChannel",
                    listenerChannel.supportedOptions());

            System.out.println("Socket TCP_NODELAY: "
                    + client.supportedOptions()
                            .contains(StandardSocketOptions.TCP_NODELAY));
            System.out.println("ServerSocket TCP_NODELAY: "
                    + listener.supportedOptions()
                            .contains(StandardSocketOptions.TCP_NODELAY));
            System.out.println("Listener SO_REUSEPORT: "
                    + listenerChannel.supportedOptions()
                            .contains(StandardSocketOptions.SO_REUSEPORT));
        }
    }
}
~~~

~~~bash
javac --release 17 TcpOptionInventory.java
java TcpOptionInventory
~~~

**There is no single fixed stdout:** the `Runtime`, `Vendor`, `OS`, option name/type lines, and `contains` results must be **printed from the actual machine running it**. The program sorts by `option.name()` only to make comparison across environments easier, since `Set` does not guarantee order. When run on a specific system, `SO_RCVBUF (Integer)`, `TCP_NODELAY (Boolean)`, or extended options may appear in the section matching the running socket/provider.

This example **makes no network connections to external hosts** and binds no ports; it only creates socket/channel objects/descriptors and collects capabilities. Opening sockets/channels can still throw `IOException` due to sandbox restrictions or OS resources; that should be recorded as an environment result. `try-with-resources` closes all objects even if an error occurs.

To compare JDK 17 and JDK 21, run the same source with `--release 17` on **two real runtimes**, save their stdout separately, and treat the observed differences only as evidence for **that environment pair**. General conclusions require additional documentation and testing on supported production platforms.

## 6. Java 17+ Program: Checking, Setting, Reading Back, and Handling Errors

Create the file **`TcpOptionReadback.java`**:

~~~java
import java.io.IOException;
import java.net.SocketOption;
import java.net.StandardSocketOptions;
import java.nio.channels.SocketChannel;

public final class TcpOptionReadback {
    private static <T> void tryOption(
            SocketChannel channel,
            SocketOption<T> option,
            T requested) {

        if (!channel.supportedOptions().contains(option)) {
            System.out.println(option.name() + ": UNSUPPORTED");
            return;
        }

        try {
            channel.setOption(option, requested);
            T readback = channel.getOption(option);
            System.out.println(option.name()
                    + ": requested=" + requested
                    + ", readback=" + readback);
        } catch (UnsupportedOperationException
                | IllegalArgumentException
                | SecurityException
                | IOException ex) {
            System.out.println(option.name()
                    + ": ERROR " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws IOException {
        try (SocketChannel channel = SocketChannel.open()) {
            tryOption(channel, StandardSocketOptions.TCP_NODELAY, true);
            tryOption(channel, StandardSocketOptions.SO_RCVBUF,
                    16 * 1024);

            System.out.println("SO_REUSEPORT advertised: "
                    + channel.supportedOptions()
                            .contains(StandardSocketOptions.SO_REUSEPORT));
        }
    }
}
~~~

~~~bash
javac --release 17 TcpOptionReadback.java
java TcpOptionReadback
~~~

On a runtime that supports and allows configuring `TCP_NODELAY`, the corresponding line is typically:

~~~text
TCP_NODELAY: requested=true, readback=true
~~~

The other lines intentionally **do not prescribe a single stdout**: `SO_RCVBUF` may differ from `16384`; `SO_REUSEPORT` may or may not be advertised; if `setOption` fails, the program prints the exception class. This is the key takeaway from probing: **capability set, set result, and readback value are three distinct signals**.

`tryOption` does not by itself prove an option improves performance. For hint options like `SO_RCVBUF`, readback only shows the reported size; for `SO_REUSEPORT`, the program only queries it and does **not** enable the feature. When testing a real server, decide whether an option is **required** or **optional**, then choose between logging + fallback or failing fast.

If `TCP_NODELAY` is truly a mandatory requirement for your system's goals, do not just print an error and continue. Turn the result into a configuration exception with environment details, and also verify the readback value. Conversely, for optional optimizations, you can disable the optimization when capability is missing while preserving correct networking functionality.

## 7. Reading Exceptions Properly: Why `contains(option)` Is Still Not Enough

| Observation | Reasonable Meaning | How to Handle |
| --- | --- | --- |
| `supportedOptions().contains(option) == false` | This socket/channel does not advertise the option | Do not call `setOption`; choose a fallback or report platform requirement |
| `UnsupportedOperationException` | The API/implementation does not support the requested option operation | Log socket type, provider, option, runtime; verify the API on the exact instance |
| `IllegalArgumentException` | Invalid value for the option | Fix the value type/range; do not retry blindly |
| `ClosedChannelException` or `IOException` | Channel/socket is already closed or I/O/OS error | Check lifecycle, resource configuration, and errno if available; do not lump into “unsupported option” |
| `SecurityException` | Permission barrier if the runtime enforces corresponding controls | Address policy/permissions; do not silently disable security |
| `setOption` succeeds, `getOption` differs from request | The kernel may have adjusted the hint or clamped the value | Read the option contract, evaluate the actual value needed by the application |
| `set/get` return the same value, yet TCP behaves differently than expected | Network/OS/protocol still have many variables | Test with real traffic; measure latency/throughput with controlled workloads |

Not every `SocketOption` in the supported set is **settable**. For example, `jdk.net.ExtendedSocketOptions.SO_INCOMING_NAPI_ID` is read-only per its Javadoc; if it appears in `supportedOptions`, you must still use `getOption` in the appropriate state and **not** automatically call `setOption`.

Additionally, some options can be read/set in an unconnected state, while others only make sense once a connection is established or after packets arrive. Each option's API documentation and the runtime must determine when to probe/test it.

## 8. Safe Implementation Workflow for TCP Clients/Servers

### 8.1. For a TCP Client

1. Identify requirements: e.g., if low latency is needed consider `TCP_NODELAY`, if detecting long-idle connections is needed evaluate `SO_KEEPALIVE` and application heartbeats.
2. Create the `Socket`/`SocketChannel` of the **exact implementation** in use, then query `supportedOptions` on that very instance.
3. Call `setOption` only when supported; use valid values, handle I/O errors, closed state, and optional-vs-required policy.
4. Read back with `getOption` if you need to observe the effective value, especially for buffer sizes.
5. Connect with an appropriate connect timeout; also set a read timeout/deadline on APIs that support it. `SO_KEEPALIVE` does not replace these timeouts.
6. Test real I/O. `TCP_NODELAY` does not mean one Java `write` is guaranteed to correspond to one TCP packet, and `SO_KEEPALIVE` does not confirm the peer application is processing business logic.

### 8.2. For a Listening TCP Server

1. Create a `ServerSocket` or `ServerSocketChannel`, **unbound**.
2. Determine which of `SO_REUSEADDR`, `SO_REUSEPORT`, `SO_RCVBUF` are meaningful in the target environment.
3. Check support, and set binding-related options **before `bind`**. Do not use `SO_REUSEPORT` as an automatic replacement for `SO_REUSEADDR`.
4. Bind to an explicit address; during testing, prefer loopback and ephemeral port `0` to avoid affecting other services.
5. After `accept`, read/set options intended for the **connected socket** if needed. `TCP_NODELAY` is a data-path option, not a property to apply to a listening `ServerSocket`.
6. Test connection counts and queue behavior under controlled load. `backlog` is also an OS-handled parameter; it is not a socket option that can be inferred from `supportedOptions`.

Correct conceptual example with `ServerSocketChannel` (illustrative snippet; must be inside a `throws IOException` method with the corresponding classes imported):

~~~java
try (ServerSocketChannel server = ServerSocketChannel.open()) {
    if (server.supportedOptions()
            .contains(StandardSocketOptions.SO_REUSEPORT)) {
        server.setOption(StandardSocketOptions.SO_REUSEPORT, true);
    }

    server.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));
}
~~~

This code **only shows the ordering** (probe → set before bind → bind). If `setOption` fails, the exception must be handled by the caller according to production policy; if it succeeds, multiple listeners sharing a port still require an OS-specific test. Do not run port-sharing experiments on production machines.

## 9. Comparing Two Environments Using an Evidence-Based Matrix

Suppose an application plans to use `SO_REUSEPORT` locally, but gets `UNSUPPORTED` on CI. Do not start by forcing `true` or switching the code to `SO_REUSEADDR`. Record the following data:

| Data | Machine A | Machine B |
| --- | --- | --- |
| `java -version` and JDK vendor/build | Value from actual command | Value from actual command |
| `os.name`, `os.version`, `os.arch` | Actual values | Actual values |
| TCP socket type | `ServerSocketChannel` or `ServerSocket` | Same type used |
| IP protocol family | IPv4/IPv6 per environment | IPv4/IPv6 per environment |
| Sorted `supportedOptions` | Printed by inventory probe | Printed by inventory probe |
| `setOption` | Success / exception type | Success / exception type |
| `getOption` | Value reported by OS | Value reported by OS |
| Bind and traffic test results | Actual observation | Actual observation |

**Only columns with evidence may be filled in.** This matrix lets you determine whether: the option is genuinely absent, present but cannot be set, or settable yet the OS lacks the expected application semantics. Those are three different failure classes and require different remedies.

When an option is an optional optimization, log the capability, skip it if missing, and ensure core functionality still runs. When an option is architecturally required (for example, a system relying on multiple listeners on the same port), validate at startup, fail fast with a platform requirement message, and test deployment on the exact supported JDK/OS.

## 10. Common False Claims

**“Having the `SO_REUSEPORT` constant in Java means every machine can enable it.”** False. The standard constant exists in the API, but the option may be absent from `supportedOptions` on a given socket.

**“If `supportedOptions` contains an option, `setOption` will always succeed.”** False. There are still type/range, lifecycle, permission, and I/O error constraints. Some options are read-only.

**“`setOption(SO_RCVBUF, 16384)` succeeded, so the TCP buffer is exactly 16 KiB.”** False. This is a hint and the OS may adjust it; verify readback and performance.

**“`SO_REUSEADDR` guarantees two servers can listen on the same port.”** False. Semantics vary by TCP stack; `SO_REUSEPORT` also needs to be supported and verified separately.

**“`SO_KEEPALIVE` replaces connect/read timeouts or health checks.”** False. It is TCP idle probing, not a business deadline or endpoint liveness check.

**“Every option in `StandardSocketOptions` applies to `ServerSocket`.”** False. Listening sockets and connected sockets have different supported sets; do not apply `TCP_NODELAY` to a listening socket if the API does not advertise it.

**“Once a channel is closed, `supportedOptions` must also throw.”** False. The `NetworkChannel` and classic socket contracts specify still returning the option set after close; however, `set/get` may throw exceptions.

**“Using the same JDK 21 means results on every OS must be identical.”** False. Kernel, provider, permissions, and OS version change capabilities and behavior.

## 11. Self-Check Exercises

**Q1.** Why is checking `StandardSocketOptions.SO_REUSEPORT != null` not enough?  
**Answer:** It does not prove the socket instance supports the option. You need `supportedOptions().contains(SO_REUSEPORT)`, attempt a valid configuration, and verify behavior on the target OS.

**Q2.** Does `ServerSocket.supportedOptions()` necessarily contain `TCP_NODELAY` like `Socket`?  
**Answer:** No. `ServerSocket` is for listening; `TCP_NODELAY` is an option handling segment transmission on a data-carrying TCP socket. Query the right object and read the contract for that socket type.

**Q3.** `SO_RCVBUF` requested 32 KiB, but `getOption` reports a different value. Is Java definitely wrong?  
**Answer:** No. Hint option values may be adjusted by the kernel; check the Javadoc and the application's actual requirements.

**Q4.** `supportedOptions()` still returns a list after `close()`; can you still call `getOption`?  
**Answer:** You should not. `supportedOptions` describes capability, whereas `getOption` on a closed socket/channel may throw `IOException`/`ClosedChannelException`.

**Q5.** If you want to enable `SO_REUSEPORT` on a listener, should you call it before or after bind?  
**Answer:** Before `bind`, after confirming support; then check for errors and test on the target OS/JDK.

**Q6.** Does `ExtendedSocketOptions.TCP_QUICKACK` let you enable it once and trust that all ACKs will always be sent immediately?  
**Answer:** No. Per the Javadoc, TCP protocol processing may change this state later.

**Q7.** The same program lists more options when run on a different JDK vendor and different OS. How should you handle this?  
**Answer:** Record runtime/OS/provider, distinguish standard from extended options, compare capabilities, and test across the support matrix. Do not hardcode the count or order of options in unit tests.

## 12. Checklist Before Using Socket Options in Production

- Read the **Javadoc for the exact JDK and socket type**. Confirm whether the option belongs to TCP/IP, a listening socket, or a specific channel.
- Query `supportedOptions()` directly on the **exact object** to be configured.
- Distinguish **optional optimizations** from **mandatory architectural requirements**.
- Set options at a **valid point in the lifecycle**, especially `SO_REUSEADDR` / `SO_REUSEPORT` before bind.
- Catch exceptions specifically for `UnsupportedOperationException`, `IllegalArgumentException`, `IOException`, and permissions where applicable.
- If the contract specifies a hint or OS-specific behavior, read back with `getOption` and run real behavior tests.
- Do not assume defaults, option counts, `Set` order, buffer sizes, keep-alive timers, or port sharing are identical across all OSes.
- Reproduce on a real JDK/OS/provider matrix, record exact builds, and avoid altering production ports during testing.
- Close sockets/channels with `try-with-resources`; do not use `supportedOptions` as proof that a resource is still open.
- When an option is in `jdk.net.ExtendedSocketOptions`, verify the JDK-specific module and support policy; do not assume all properties are writable.

## Official References

- [Java SE 17 — `Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html) and [`ServerSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): `setOption`, `getOption`, `supportedOptions`, standard sets, and post-close behavior.
- [Java SE 17 — `NetworkChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/NetworkChannel.html), [`SocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html), [`ServerSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): capabilities and NIO APIs.
- [Java SE 17 — `StandardSocketOptions`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): value types and conditions/limits for each option, especially buffers, reuse, linger, and keep-alive.
- [JDK 17 — `ExtendedSocketOptions`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.net/jdk/net/ExtendedSocketOptions.html), [JDK 21 — `ExtendedSocketOptions`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.net/jdk/net/ExtendedSocketOptions.html): extended options and platform-specific scope.
- [JDK 17 — `jdk.net.Sockets`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.net/jdk/net/Sockets.html): deprecated legacy utility; migration to the instance API.
- [Java SE 21 — `Socket`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html), [`NetworkChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/NetworkChannel.html): cross-checking the same contract when upgrading the runtime.

**Key principle to remember:** `StandardSocketOptions` only tells you **the standard option name**; `supportedOptions` tells you **what capability the current object advertises**; `setOption` and `getOption` tell you **the configuration operation and readback**; only real testing tells you **how TCP actually behaves on the target OS/JDK**.
