# Unix domain sockets via StandardProtocolFamily.UNIX and UnixDomainSocketAddress

## 1. The problem: communication between processes on the same machine

A Java application may need to exchange data with another process on the **same machine**: an internal service, a management process, a daemon, a worker, or two programs running separately while sharing the same operating system. TCP loopback via `127.0.0.1`/`::1` is one option. A **Unix domain socket** is another option for **local inter-process communication (IPC)**, identified primarily by a **filesystem path**, rather than an IP and port.

Since **Java 16** (JEP 380), Java NIO supports Unix domain sockets via `ServerSocketChannel` and `SocketChannel`. Because this topic belongs to the **Buffers and channels** group, the focus here is on **`StandardProtocolFamily.UNIX`, `UnixDomainSocketAddress`, channel lifecycle, and `ByteBuffer`**.

The two communicating ends follow this model:

~~~text
Server process                          Client process
ServerSocketChannel                     SocketChannel
open(StandardProtocolFamily.UNIX)       open(StandardProtocolFamily.UNIX)
           |                                       |
bind(UnixDomainSocketAddress)           connect(UnixDomainSocketAddress)
           |_______________________________________|
                           |
                    local pathname
             e.g. /run/myapp/service.sock
                           |
                 server.accept() -> SocketChannel
                           |
                 bidirectional ByteBuffer read/write
~~~

The path `/run/myapp/service.sock` is only a Unix/Linux-style illustration, not a mandatory path or one that exists automatically on every operating system.

**Key characteristics:**

- Used for **same-host** communication, not direct connections from one machine to another over the Internet.
- There is no **IP/port** pair like `InetSocketAddress`; a `UnixDomainSocketAddress` object wraps a `Path`.
- Connections use a **stream-oriented channel**: data is still a byte stream, with **no automatic message boundaries**.
- No network TCP port needs to be opened for this service, but you still need to manage **file/path access permissions**, connections, and resource limits.
- Support depends on the **JDK, operating system, and provider**. Java 17+ has the API, but a specific environment may still not support `UNIX`.

## 2. APIs to distinguish

| API | Role |
| --- | --- |
| `StandardProtocolFamily.UNIX` | Selects the Unix domain address family, instead of `INET`/`INET6` |
| `UnixDomainSocketAddress.of(Path)` | Creates an endpoint address from a path on the default filesystem of the OS |
| `UnixDomainSocketAddress.of(String)` | Creates an address from a path string |
| `ServerSocketChannel.open(UNIX)` | Creates a server channel for Unix domain, initially unbound |
| `server.bind(address)` | Binds the socket name to the filesystem and starts listening |
| `server.accept()` | Accepts a connection, returning a `SocketChannel` for exchanging data |
| `SocketChannel.open(UNIX)` | Creates an unconnected Unix domain client channel |
| `client.connect(address)` | Connects to the socket path that the server is listening on |
| `SocketChannel.open(address)` | Shorthand: automatically infers the `UNIX` family when address is a `UnixDomainSocketAddress` |
| `ByteBuffer` | Buffer with `position`/`limit`/`capacity` for `read` and `write` |
| `Files.deleteIfExists(path)` | Cleans up the socket filesystem node **after the server closes** |

Typical imports:

~~~java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;
~~~

*This is an illustrative list of imports; the standalone runnable examples below include all necessary imports.*

Common pitfall: the **no-argument** `SocketChannel.open()` and `ServerSocketChannel.open()` normally create Internet channels and do **not** automatically create Unix domain sockets. To control the protocol explicitly, call the `open(StandardProtocolFamily.UNIX)` version. For clients, `SocketChannel.open(unixAddress)` is also valid because there is an overload that automatically infers the family from the address type.

Some legacy adapter methods such as `SocketChannel.socket()` or `ServerSocketChannel.socket()` **do not support Unix domain sockets** and may throw `UnsupportedOperationException`. Use the **channel API directly**, for example `read(ByteBuffer)`, `write(ByteBuffer)`, `getLocalAddress()`, and `getRemoteAddress()`. Do not convert a Unix domain channel into a `java.net.Socket`/`ServerSocket` via `socket()` as you would with an Internet channel.

## 3. UnixDomainSocketAddress: the endpoint is a path, not a port

An address can be created with:

~~~java
Path socketPath = Path.of("/run/myapp/service.sock");
UnixDomainSocketAddress address = UnixDomainSocketAddress.of(socketPath);
~~~

*Snippet illustrating a Unix path; choose a path whose parent directory actually exists and has appropriate permissions for the operating system in use.*

Or with a string:

~~~java
UnixDomainSocketAddress address =
        UnixDomainSocketAddress.of("service.sock");
~~~

*The snippet above illustrates a relative address. The server and client must resolve the path according to their respective working directories/deployment setups.*

`UnixDomainSocketAddress` is an **address descriptor**; it does not create a file, open a channel, or connect by itself. Only when `server.bind(address)` succeeds does the OS/JDK create the filesystem node for the Unix domain socket at that address. The client needs a path that refers to the **same actual endpoint**.

Notes about paths:

- **Parent directory:** must exist and have appropriate access permissions. For a real service, place the socket in a dedicated directory with managed ownership/permissions.
- **Name already exists:** bind generally cannot reuse an existing path. Simply closing the server **does not automatically delete** the old socket file; the node must be cleaned up properly after closing.
- **Length limit:** operating systems impose a limit on Unix domain socket paths in **bytes** (typically around 100 bytes, depending on the platform). Deeply nested temp or project paths can cause bind to fail.
- **Path from the default filesystem:** `UnixDomainSocketAddress.of(Path)` requires a `Path` belonging to the default filesystem; do not arbitrarily use a `Path` from a virtual/ZIP provider.
- **Relative addresses:** depend on the working directory and how the two processes resolve the path. Production programs should configure and verify paths consistently.
- **Not synonymous with a regular data file:** the socket node created by the OS is a named endpoint for IPC; do not read/write it with `Files.readString(...)` like a text file.

On the client side, when calling `connect` without explicitly calling `bind` on a local address, the socket is usually **unnamed**: the local address has an empty path and there is **no separate client file to delete**. The server, on the other hand, needs a discoverable name for clients to connect to.

## 4. Server and client lifecycle

**Server side:**

~~~text
ServerSocketChannel.open(UNIX)
    -> bind(UnixDomainSocketAddress.of(path))
    -> accept()
    -> SocketChannel of the newly accepted session
    -> read/write ByteBuffer on the accepted channel
    -> close the accepted channel and the server channel
    -> delete the server's filesystem socket node
~~~

**Client side:**

~~~text
SocketChannel.open(UNIX)
    -> connect(UnixDomainSocketAddress.of(same path))
    -> read/write ByteBuffer
    -> close()
~~~

`ServerSocketChannel` is the **listening channel**, not the channel for exchanging payloads with a specific client. Only after `accept()` is the returned value a connected `SocketChannel` for transferring data. A server can call `accept()` multiple times for multiple clients, each with its own channel.

`accept()`, `read()`, and `write()` use **blocking mode by default**: if the required event or data is not yet available, the call may wait. You can call `configureBlocking(false)` and use a `Selector`, but then you must handle `accept() == null`, reads/writes returning 0, registering `SelectionKey`s, and completing unfinished connections with `finishConnect()`. The two examples in this lesson use blocking mode to stay focused on Unix domain sockets and `ByteBuffer`.

A Unix domain stream channel **does not turn into a UDP datagram**. One `write` call does not necessarily correspond to one `read` call. For variable-length messages, you must have framing (such as a length prefix), just like other byte streams.

## 5. Java 17+ example: creating a Unix domain socket and exchanging data bidirectionally

This example runs **both the server and client in a single program** to verify the API without needing two terminals. It creates a dedicated temporary directory, binds to `service.sock` inside that directory, the client connects, the server receives `"HELLO"` and replies `"OK"`. The path is uniquely generated for each run, so it does not overwrite an existing socket pathname.

Save to `UnixSocketBasicDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class UnixSocketBasicDemo {
    static void writeAll(SocketChannel channel, String value) throws IOException {
        ByteBuffer bytes = StandardCharsets.UTF_8.encode(value);
        while (bytes.hasRemaining()) {
            channel.write(bytes);
        }
    }

    static String readExactly(SocketChannel channel, int count) throws IOException {
        ByteBuffer bytes = ByteBuffer.allocate(count);
        while (bytes.hasRemaining()) {
            if (channel.read(bytes) < 0) {
                throw new EOFException("stream ended before " + count + " bytes");
            }
        }
        bytes.flip();
        return StandardCharsets.UTF_8.decode(bytes).toString();
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("java-uds-");
        Path socketPath = dir.resolve("service.sock");
        try {
            UnixDomainSocketAddress endpoint = UnixDomainSocketAddress.of(socketPath);
            try (ServerSocketChannel server =
                         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
                server.bind(endpoint);

                try (SocketChannel client =
                             SocketChannel.open(StandardProtocolFamily.UNIX)) {
                    client.connect(endpoint);
                    try (SocketChannel accepted = server.accept()) {
                        System.out.println("server unix address: "
                                + (server.getLocalAddress()
                                instanceof UnixDomainSocketAddress));
                        System.out.println("client connected: " + client.isConnected());

                        writeAll(client, "HELLO");
                        System.out.println("server received: " + readExactly(accepted, 5));

                        writeAll(accepted, "OK");
                        System.out.println("client received: " + readExactly(client, 2));
                    }
                }
            }
        } finally {
            Files.deleteIfExists(socketPath);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile/run with **JDK 17+ and a platform supporting Unix domain sockets**:

~~~bash
javac UnixSocketBasicDemo.java
java UnixSocketBasicDemo
~~~

Test output when binding/connecting over a Unix domain socket succeeds:

~~~text
server unix address: true
client connected: true
server received: HELLO
client received: OK
~~~

Step-by-step explanation:

1. `Files.createTempDirectory` provides a unique new directory, then `socketPath = dir.resolve("service.sock")` picks a socket name that does not yet exist. This avoids name collisions when running the demo multiple times; if the temp path is too long for the OS limit, choose a shorter directory.
2. `UnixDomainSocketAddress.of(socketPath)` creates the endpoint. `ServerSocketChannel.open(UNIX).bind(endpoint)` creates the Unix domain server and listens.
3. `SocketChannel.open(UNIX)` creates the client; `client.connect(endpoint)` connects. `server.accept()` returns the server-side channel for this session.
4. `getLocalAddress() instanceof UnixDomainSocketAddress` confirms the endpoint type the server bound to; `client.isConnected()` indicates the connection succeeded.
5. `writeAll` loops while `ByteBuffer.hasRemaining()` because even with a blocking channel you must **never assume a single write always processes the entire buffer**.
6. `readExactly` loops until the required number of bytes is read; `read` returns `-1` when the other side closes its output/the stream ends. `flip()` switches the buffer from write-into mode to read-from mode.

**Demo limitation:** the two lengths of 5 and 2 bytes are known in advance. This is **not general framing** for messages of arbitrary length. In the next section we add a length header to know exactly how many bytes to read.

In `finally`, the program deletes the socket file after the channels have closed, then deletes the temporary directory. This is an extra responsibility beyond merely using `try-with-resources`. Because the directory was created specifically for the demo, this cleanup does not touch an existing service path. For a production service, ownership and lifecycle must be verified before deleting a node—never blindly delete a path managed by another user/process.

## 6. ByteBuffer: position, limit, flip, and reading/writing full bytes

In Java NIO, `ByteBuffer` has three concepts:

| Property | Meaning |
| --- | --- |
| `capacity()` | Fixed capacity of the buffer |
| `position()` | Next position to operate on |
| `limit()` | Upper bound (exclusive) of the region that can be operated on |
| `remaining()` | Number of elements from position to limit |
| `hasRemaining()` | Whether there are remaining bytes to read/write |
| `flip()` | Sets limit = position, position = 0, switching a newly written buffer to read mode |
| `clear()` | position = 0, limit = capacity, preparing to **overwrite**, without erasing byte contents |
| `compact()` | Shifts unread bytes to the beginning of the buffer, preparing to receive more when using an incremental parser |

When writing data **from the program out to a channel**, we typically do:

~~~java
ByteBuffer output = StandardCharsets.UTF_8.encode("HELLO");
while (output.hasRemaining()) {
    channel.write(output);
}
~~~

*Illustrative snippet inside a method that already has `SocketChannel channel`; not a standalone program.*

`StandardCharsets.UTF_8.encode` returns a `ByteBuffer` whose limit matches the encoded data, ready to be read from the buffer for `channel.write` to send. If you use `ByteBuffer.allocate(...)` and then `put(...)`, you must call `flip()` before `write()`; otherwise the channel may send bytes that are not the intended payload.

When **reading from a channel into a buffer**, the order is reversed:

~~~java
ByteBuffer input = ByteBuffer.allocate(5);
while (input.hasRemaining()) {
    if (channel.read(input) < 0) {
        throw new EOFException("missing bytes");
    }
}
input.flip();
String value = StandardCharsets.UTF_8.decode(input).toString();
~~~

*Illustrative snippet for a **blocking SocketChannel** and a pre-known 5-byte payload; requires importing `ByteBuffer`, `EOFException`, and `StandardCharsets`.*

When a channel is in non-blocking mode, `read` or `write` can return 0 even while the buffer still has bytes. Do not busy-spin in a continuous `while` loop without using `Selector`/readiness or a proper scheduling strategy. In blocking mode, the read/write loops above are a simple way to handle partial I/O.

**Important:** A Unix domain socket is a stream, so framing must not rely on the number of read calls. For example, the server writes two consecutive messages; the client may receive the bytes merged or split differently across reads. To read complete messages, you need **boundary rules** and valid size limits.

## 7. Java 17+ example: two length-prefixed messages over one connection

This example upgrades to a protocol with:
- A `4-byte int` header in big-endian (per `ByteBuffer.putInt/getInt` default).
- A body with a number of UTF-8 bytes equal to the length header.
- A limit `MAX_FRAME_BYTES = 1024` to avoid allocating unbounded memory controlled by a peer.
- `readFully` to receive the complete header/body or throw `EOFException`.
- Two messages `"A"` and `"Xin chào"` sent consecutively **over the same Unix domain socket connection**, each replied with `"ACK"`.

Save `UnixSocketFrameDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class UnixSocketFrameDemo {
    private static final int MAX_FRAME_BYTES = 1024;

    static void writeFrame(SocketChannel channel, String message)
            throws IOException {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_FRAME_BYTES) {
            throw new IllegalArgumentException("frame too large");
        }
        ByteBuffer frame = ByteBuffer.allocate(Integer.BYTES + bytes.length);
        frame.putInt(bytes.length);
        frame.put(bytes);
        frame.flip();
        while (frame.hasRemaining()) {
            channel.write(frame);
        }
    }

    static void readFully(SocketChannel channel, ByteBuffer buffer)
            throws IOException {
        while (buffer.hasRemaining()) {
            int n = channel.read(buffer);
            if (n < 0) {
                throw new EOFException("incomplete frame");
            }
        }
    }

    static String readFrame(SocketChannel channel) throws IOException {
        ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);
        readFully(channel, header);
        header.flip();
        int length = header.getInt();
        if (length < 0 || length > MAX_FRAME_BYTES) {
            throw new IOException("invalid frame length: " + length);
        }
        ByteBuffer body = ByteBuffer.allocate(length);
        readFully(channel, body);
        body.flip();
        return StandardCharsets.UTF_8.decode(body).toString();
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("java-uds-frame-");
        Path socketPath = dir.resolve("service.sock");
        try {
            UnixDomainSocketAddress address = UnixDomainSocketAddress.of(socketPath);
            try (ServerSocketChannel server =
                         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
                server.bind(address);
                try (SocketChannel client =
                             SocketChannel.open(StandardProtocolFamily.UNIX)) {
                    client.connect(address);
                    try (SocketChannel accepted = server.accept()) {
                        for (String text : new String[] {"A", "Xin chào"}) {
                            writeFrame(client, text);
                            String received = readFrame(accepted);
                            System.out.println("server received: " + received);
                            writeFrame(accepted, "ACK");
                            System.out.println("client received: "
                                    + readFrame(client));
                        }
                    }
                }
            }
        } finally {
            Files.deleteIfExists(socketPath);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Run:

~~~bash
javac UnixSocketFrameDemo.java
java UnixSocketFrameDemo
~~~

Output:

~~~text
server received: A
client received: ACK
server received: Xin chào
client received: ACK
~~~

Explanation of the steps for a frame:

1. `String.getBytes(UTF_8)` converts the message to bytes first, so the length is the **number of bytes**, not `String.length()`. `"Xin chào"` contains multi-byte characters but is still received correctly.
2. `ByteBuffer.allocate(4 + payload.length)` holds both the header and body. `putInt`/`put` advance the position; `flip` sets the right limit so `SocketChannel.write` sends the prepared data.
3. `readFully(header)` ensures all 4 bytes are received, `flip` then `getInt()` reads the length.
4. **Validate `length < 0 || length > MAX_FRAME_BYTES` before `ByteBuffer.allocate(length)`**. Never allocate an array/buffer based on an unvalidated length field.
5. `readFully(body)` receives the full body (possibly across multiple reads). `flip` then `UTF_8.decode(...)` decodes the exact byte range.
6. The `for` loop sends two frames over one connection; `readFrame` separates the boundaries thanks to the **header**, not because the Unix domain socket remembers boundaries on its own.

`readFully` in the example is only for **blocking channels**. If switching to non-blocking, you must maintain parser state and handle `read() == 0` with readiness events/Selector instead of busy-waiting. In addition, production messaging needs permission checks, context-appropriate authentication/authorization, timeouts/deadlines, client count limits, total memory quotas, and protocol rules for EOF/length violations.

## 8. Distinguishing Unix domain sockets from TCP loopback

| Characteristic | TCP loopback | Unix domain socket |
| --- | --- | --- |
| Endpoint | `InetSocketAddress` with IP + port | `UnixDomainSocketAddress` with path |
| Typical connection scope | Same machine via loopback, or configurable TCP on another IP for remote | **Same host only / not directly over an IP network** |
| Java NIO server | `ServerSocketChannel.open()` then bind IP/port | `ServerSocketChannel.open(UNIX)` then bind path |
| Java NIO client | `SocketChannel.open()` then connect IP/port | `SocketChannel.open(UNIX)` then connect path |
| Data nature | Byte stream | Byte stream |
| Message boundaries | Application-defined | Application-defined |
| Endpoint name management | Port is released according to the OS socket lifecycle | Socket path usually **remains after close**, needs cleanup |
| Access control | Network binding, firewall, OS, and application | Directory/socket file permissions, OS, and application |
| Support | Depends on platform Internet protocols | Depends on AF_UNIX/JDK/provider, path length limits |

A Unix domain socket is usually appropriate when **both processes are on the same host** and want to communicate through an internal pathname. TCP loopback remains useful when you need the ability to move to another host, integrate with systems that require IP/port, or run in an environment without AF_UNIX.

**Do not conclude that Unix domain sockets automatically encrypt data or authenticate peers.** Their "local only" nature and filesystem permissions help reduce the attack surface, but the application still must define trust boundaries, socket-opening permissions, and use appropriate peer/message identification mechanisms when needed. A socket file in a shared directory without permission controls can risk endpoint spoofing or unauthorized access.

## 9. Safe socket file management and resource lifecycle

For a Unix domain socket server **with an explicit path**, a careful deployment lifecycle includes:

1. Create a **dedicated directory** with appropriate permissions, avoiding names controlled by untrusted parties; choose a short path and configure it consistently.
2. Before binding, verify that the target socket name **is not owned by another process**. Do not automatically call `deleteIfExists` on a shared path before binding: you might delete the node of a running service.
3. Open `ServerSocketChannel.open(StandardProtocolFamily.UNIX)` and then `bind(address)`. When clients need to know the path, publish it via controlled configuration.
4. `accept` and manage each `SocketChannel` individually, using `try-with-resources` to close it when done.
5. On shutdown, close the server and all accepted channels, clean up the node **owned by the server itself** with `Files.deleteIfExists(socketPath)`, and handle cleanup errors properly.
6. Monitor filesystem limits, handle/file descriptor quotas, connection counts, and bytes queued for processing.

If a server crashes unexpectedly, the socket file may remain even though the process is no longer listening. The existence of a path **does not prove a server is alive**. Yet you must not assume every remaining socket file is "junk": another process may be using that name. Production systems should have ownership/startup checks to avoid deleting a valid endpoint.

Another API option is `server.bind(null)`: the JDK generates **an automatic socket name in a temporary location**, and you can retrieve the actual address with `(UnixDomainSocketAddress) server.getLocalAddress()`. The created socket file still needs to be deleted after closing—"automatic name" does not mean "auto-delete." For clients to know this name, it must be passed to them via a separate configuration/coordination channel. Do not assume the temp path will always be short enough for the AF_UNIX name limit.

The example uses `Files.createTempDirectory` to demonstrate safe cleanup on a directory owned by the demo program. For real multi-process applications, do not use a temporary directory created exclusively for the server if clients do not know the path; a proper name-provisioning or discovery solution is required.

## 10. Platform limits, exceptions, and APIs not to confuse

**Java requirements:** `StandardProtocolFamily.UNIX` and `UnixDomainSocketAddress` were added in Java 16. To run the code in this lesson, use **JDK 17 or newer**; the source and classes cannot compile with JDK 11 because these APIs are missing. Some operating systems or JDK configurations do not support Unix domain sockets, and `open(UNIX)` may throw `UnsupportedOperationException`. The test examples do not require an Internet connection.

Possible errors:

- **Duplicate bind path:** the name already exists or is owned by another service; usually an I/O/bind error. Do not "fix" this by arbitrarily deleting a path you do not own.
- **Missing directory / insufficient permissions:** server bind or client connect can throw `IOException`; check the path, directory permissions, and file permissions.
- **Path too long:** OS-level AF_UNIX constraint (typically around 100 bytes, though there is no universal number across all machines); choose a shorter name.
- **Connect when the server is not listening:** `connect` fails; it does not turn a path into a live server.
- **Wrong address type:** for example, opening an Internet socket channel and passing a Unix domain address to bind/connect is incompatible; you may encounter `UnsupportedAddressTypeException`.
- **Calling `socket()` on a Unix domain channel:** may throw `UnsupportedOperationException`; use `SocketChannel.read/write(ByteBuffer)` and `ServerSocketChannel.accept()`.
- **`ClosedChannelException`, `EOFException`, and other I/O errors:** you need to control channel lifecycles and handle disconnections; `read` returns `-1` when the peer ends its write side.
- **Non-blocking treated as blocking:** `accept` can return `null`; `read`/`write` can return 0; you must use readiness and proper state management.

The set of socket options also differs from TCP: for instance, `TCP_NODELAY` is a TCP option, not an option for Unix domain channels. In Java 21, a Unix `SocketChannel` typically has options such as `SO_SNDBUF`, `SO_RCVBUF`, and `SO_LINGER`; a Unix `ServerSocketChannel` supports `SO_RCVBUF`. When writing portable code, query `supportedOptions()` instead of hardcoding that every Internet option is valid.

## 11. Channels and Selector: scaling to many connections

The first two examples intentionally use blocking mode for ease of execution. When a server needs many concurrent connections, Java NIO still allows using `Selector` with Unix domain socket channels:

- `ServerSocketChannel` supports `SelectionKey.OP_ACCEPT` to accept new clients.
- `SocketChannel` supports connect/read/write interests (depending on state), just like other stream-oriented channels.
- To register with a selector, you must call `configureBlocking(false)`.
- When `accept()` returns `null` or `read()/write()` returns `0`, that can be a valid result in non-blocking mode; wait for readiness or update interests, **do not busy-spin**.
- For unfinished connections, call `finishConnect()` before reading/writing normally.
- When reading multiple messages into one `ByteBuffer`, the parser must manage state and incomplete data using `flip/compact`; do not treat each readiness event as exactly one frame.

**Conceptual example** (not a complete program):

~~~java
server.configureBlocking(false);
server.register(selector, SelectionKey.OP_ACCEPT);
// On OP_ACCEPT event: accept(), register the new channel;
// On OP_READ: read into the buffer and parse the frame when enough bytes arrive;
// On OP_WRITE: write the remaining portion of the ByteBuffer.
~~~

To run in practice, you need to initialize the `Selector`, run the `select()` loop, and manage selection keys, client state, timeouts, and shutdown. The goal of this section is to show that Unix domain sockets are compatible with the NIO and `Selector` model, **not** to replace framing logic or `ByteBuffer` management.

## 12. Common mistakes

1. **Using `ServerSocketChannel.open()` and then trying to bind a Unix address.** The no-argument version opens an Internet family channel; you must use `open(StandardProtocolFamily.UNIX)`.
2. **Using `InetSocketAddress("localhost", port)` instead of `UnixDomainSocketAddress`.** They are two different addressing models; Unix domain has no TCP port.
3. **Calling `SocketChannel.socket().getInputStream()`.** The `socket()` adapter is not meant for Unix domain channels; read/write `ByteBuffer` directly.
4. **Forgetting `flip()` after `put()` or `read()`.** Incorrect buffer position/limit leads to sending garbage bytes or decoding incomplete data.
5. **Assuming one `write` always writes everything and one `read` always reads everything.** You must use `remaining/hasRemaining`, framing, and EOF handling.
6. **Thinking Unix domain sockets have message boundaries.** They provide a byte stream; use a length prefix or delimiter/application protocol.
7. **Using `new ByteBuffer[length]` or `allocate(length)` from an unvalidated header.** A peer could send an absurd length; check bounds before allocating.
8. **Only closing the server without cleaning up the socket file.** The path node may remain and block the next bind.
9. **Deleting any existing socket file on startup to "fix address-in-use errors."** You might delete another process's endpoint; verify ownership and permissions first.
10. **Choosing an extremely long path in nested/temp directories.** AF_UNIX has a byte limit on names; choose a platform-appropriate path.
11. **Assuming local IPC is automatically secure.** You must restrict path/parent directory permissions, verify the peer, and protect data according to your trust model.
12. **Pointing a client to a path not in the same filesystem namespace.** Two containers/processes must see the same endpoint; proper shared paths/mounts are needed to connect.
13. **Switching to non-blocking while keeping a busy `readFully` loop.** The channel can return 0; you must use a `Selector`/state machine and fairness.

## 13. Self-check questions

**Question 1.** Why does a Unix domain socket address not have `host:port` like TCP? When should you use Unix domain instead of TCP loopback?

Answer: it identifies an internal IPC endpoint via a filesystem path, not via IP/port. Use it when both processes are on the same host, you control the path, and there is appropriate OS/JDK support; TCP loopback is better suited when you need to integrate via an IP/port interface or may have remote requirements later.

**Question 2.** Why is `ServerSocketChannel.open()` insufficient when you want to use `UnixDomainSocketAddress`?

Answer: the no-argument constructor opens an Internet channel; you need `ServerSocketChannel.open(StandardProtocolFamily.UNIX)`. For clients, `SocketChannel.open(unixAddress)` is an overload that can automatically infer the family.

**Question 3.** Why does `ByteBuffer.flip()` need to appear after `putInt`/`put(bytes)` or after `read` fills the buffer?

Answer: because when writing data into the buffer, `position` advances. `flip` sets `limit` to the current position and resets position to 0 so the newly received/written byte region becomes a valid readable region. `clear` only resets the cursors; it does not erase bytes.

**Question 4.** A server sends two frames `"A"` and `"Xin chào"` consecutively. Why can't the client call `read` exactly twice and assume it receives the two messages cleanly?

Answer: a stream-oriented Unix domain socket can merge or split bytes across `read` calls; you need a length prefix or other framing and a loop that reads completely.

**Question 5.** After `server.close()`, why might binding to the same socket path still fail? Should you always call `Files.deleteIfExists(path)` on startup?

Answer: the Unix domain socket server's node may still exist on the filesystem; it usually does not disappear automatically after close. Do not blindly delete on startup: you must verify the path belongs to your service/process and have a mechanism to prevent races; clean up owned paths on shutdown.

**Question 6.** Why might `client.getLocalAddress()` for a Unix domain socket have an empty path?

Answer: a client is not required to bind a local name. A default connection can use an **unnamed** address, so there is no client-side socket file.

**Practice exercises:**
- Run `UnixSocketBasicDemo` twice. Observe why the program creates a dedicated temp directory and cleans up `service.sock` in `finally`.
- In `UnixSocketFrameDemo`, add a UTF-8 message longer than 1 byte/character such as `"Việt Nam"`, and verify that `getBytes(UTF_8)` encoding produces a length in **bytes**.
- Try removing `frame.flip()` before `write` to observe the erroneous behavior in a separate test environment, then restore the correct code.
- Change `MAX_FRAME_BYTES` to `4` and send `"HELLO"`, verifying that the sender rejects it for exceeding the limit before frame allocation.
- Try `ServerSocketChannel.open(StandardProtocolFamily.UNIX).bind(null)`, retrieve `server.getLocalAddress()`, and plan the real path cleanup before running; do not overwrite an existing system endpoint.

## Official references

- [JEP 380 — Unix-Domain Socket Channels](https://openjdk.org/jeps/380)
- [UnixDomainSocketAddress — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/UnixDomainSocketAddress.html)
- [StandardProtocolFamily — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/StandardProtocolFamily.html)
- [ServerSocketChannel — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [SocketChannel — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [ByteBuffer — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html)
