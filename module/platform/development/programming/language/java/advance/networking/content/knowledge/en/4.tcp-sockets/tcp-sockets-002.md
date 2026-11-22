# Creating a Socket, Binding a Local Address, and Connecting to a Remote Endpoint

## 1. Where does a Socket stand in a TCP connection?

A TCP connection connects two endpoints: **local IP address + local port number** and **remote IP address + remote port number**. In Java, `java.net.Socket` represents one end of a TCP connection for reading/writing a byte stream. The server side typically uses `ServerSocket` to listen, and then `accept()` returns a new `Socket` for each accepted connection.

~~~text
Client machine                                  Server machine
local IP:local port  ------ TCP connect ----->  remote IP:remote port
192.0.2.10:51000                                192.0.2.20:8080

Seen from client: local = 192.0.2.10:51000; remote = 192.0.2.20:8080
Seen from server: local = 192.0.2.20:8080; remote = 192.0.2.10:51000
~~~

The IPs and ports in the diagram are for illustration only. "Local" and "remote" are always **relative roles with respect to the socket being observed**: the client's local port is the remote port of the socket created by the server's `accept()`.

In this lesson, three actions must be clearly distinguished:

1. **`new Socket()`:** creates a TCP object not yet attached to a source address and without a remote peer.
2. **`socket.bind(localEndpoint)`:** attaches the socket to an address/port on the **local machine**. This operation does not connect to the server yet.
3. **`socket.connect(remoteEndpoint, timeout)`:** requests establishing a TCP connection to the **destination IP/hostname and port**; only after it succeeds can bytes be exchanged. If the socket is not yet bound, the system automatically chooses an appropriate local address and port during connect.

Key question: `bind` chooses the **source**, `connect` chooses the **destination**. For most TCP clients, we **do not need to bind manually**: `connect` alone is enough for the system to automatically assign the source.

## 2. Related classes and address types

| Class or API | Role |
| --- | --- |
| `Socket` | TCP socket used to connect, send, and receive data |
| `ServerSocket` | Server-side socket used to bind a listening port and `accept` |
| `SocketAddress` | Abstract type of a socket address |
| `InetSocketAddress` | Pair of `(InetAddress/hostname, port)`; used as a bind/connect parameter |
| `InetAddress` | IP address; `getLoopbackAddress()` is used for local testing |

`InetSocketAddress` only **describes an address**; it does not create a connection or reserve a port upon instantiation. `new InetSocketAddress(loopback, 0)` is a **request** to choose a port when binding; it does not hold the actual port until you query the bound socket.

Ways to instantiate `Socket` to know:

| Creation method | When is the connection performed? |
| --- | --- |
| `new Socket()` | Not yet; call `connect(...)` afterward |
| `new Socket(host, port)` | Immediately in the constructor |
| `new Socket(ipAddress, port)` | Immediately in the constructor |
| `new Socket(host, port, localAddress, localPort)` | Constructor chooses the source address/port and then connects |

Use `new Socket()` when you need to **control the sequence**, specify the source IP, configure options before connecting, or set an explicit connect timeout. Use immediate-connect constructors for simple cases. Immediate-connect constructors may throw an I/O exception right at instantiation time.

## 3. Lifecycle: unbound, bound, connected, and closed

~~~text
new Socket()
   |  state: unbound, unconnected
   |
   | [optional] bind(local IP, local port)
   v
Socket bound, still unconnected
   |
   | connect(remote IP/hostname, remote port, timeout)
   v
Socket bound + connected
   |
   | getInputStream()/getOutputStream()
   | transfer bytes over TCP
   v
close()
~~~

If you **skip the explicit bind step**, `connect` will automatically do what is needed for the socket to have a local endpoint. Once connected, a socket cannot change its local endpoint by binding again.

| Point in time | `isBound()` | `isConnected()` | `getLocalPort()` | `getPort()` |
| --- | --- | --- | --- | --- |
| Right after `new Socket()` | `false` | `false` | `-1` | `0` |
| After `bind(localIp, 0)` succeeds | `true` | `false` | Actual local port (> 0) | `0` |
| After `connect(remote, timeout)` succeeds | `true` | `true` | Actual local port | Actual remote port |
| After `close()` of a previously connected socket | `true` | `true` | May retain old port | May retain old port |

The `getPort()` column in `Socket` is the **remote port**; `getLocalPort()` is the **local port**. When not bound, `getLocalSocketAddress()` returns `null`; when not connected, `getRemoteSocketAddress()` returns `null`.

**Note:** `isBound()` and `isConnected()` describe what **has previously succeeded**, so they can remain `true` after `close()`. You must check `isClosed()` to know whether the socket is closed; even an unclosed state does not guarantee the peer is still available if the network just failed.

## 4. Client-side bind: choosing the source address/port

A client that wants to use the loopback IP and let the operating system assign a port automatically can call:

~~~java
Socket client = new Socket();
InetSocketAddress requestedLocal =
        new InetSocketAddress(InetAddress.getLoopbackAddress(), 0);
client.bind(requestedLocal);
~~~

*The snippet above illustrates the operation inside a program with exception handling and socket closing; two complete examples appear later.*

Read the two components carefully:

- `InetAddress.getLoopbackAddress()` selects the address of the **current machine** (usually `127.0.0.1` or `::1`). The source address must be bindable on the machine running the code. Do not pass the remote server's IP into `client.bind`.
- Port `0` asks the operating system to assign an **available local port** at bind time. `requestedLocal.getPort()` remains `0` because `InetSocketAddress` is immutable; **`client.getLocalPort()`** returns the actual assigned port.

Other forms:

| Call | Meaning |
| --- | --- |
| `client.bind(new InetSocketAddress(localIp, 0))` | Choose local IP; system chooses local port |
| `client.bind(new InetSocketAddress(localIp, 55000))` | Request specific local IP and port |
| `client.bind(new InetSocketAddress(0))` | Wildcard local + auto-assigned port |
| `client.bind(null)` | System chooses a valid local address and auto-assigned port |
| Do not bind before connect | System binds automatically during connection |

**Wildcard** (`0.0.0.0` or `::`) only has special meaning when binding on the **local side**; it is not a destination IP address to which a connection can be sent. If the machine has multiple network interfaces, manual binding can help select the source IP, but you must choose an address that actually exists on the machine and matches the route to the peer.

Most clients do not need a fixed source port. Hardcoding a port can cause `BindException` when the port is occupied and makes it difficult to run multiple sessions in parallel. Unless there is a specific requirement, let the system choose port `0` or bind automatically during `connect`.

Binding on `ServerSocket` differs in role: `listener.bind(...)` opens a **listening endpoint** on the server; `client.bind(...)` chooses the **source** for an outgoing connection. Both only accept addresses belonging to their respective local sides.

## 5. Client-side connect: choosing the destination address/port

With an unconnected `Socket`:

~~~java
InetSocketAddress remote = new InetSocketAddress("example.com", 443);
try (Socket client = new Socket()) {
    client.connect(remote, 2_000);
    client.setSoTimeout(2_000);
    // Read/write via client.getInputStream() and client.getOutputStream().
}
~~~

*This snippet is for explaining the API and is not a standalone program; the example hostname does not guarantee that a specific service is running.*

- `remote` specifies the **server machine/port**. The destination port must be a real service port, such as `443`, rather than using port `0` as when requesting a local port.
- `connect(remote, 2_000)` attempts the TCP handshake, with a connection timeout of **2,000 milliseconds**; if it succeeds, the socket becomes connected and bound.
- `setSoTimeout(2_000)` applies to blocking `read()` calls on `InputStream`; it **does not replace the connect timeout**.
- `new InetSocketAddress(hostname, port)` may perform DNS resolution upon creation. DNS resolution time is not guaranteed to fall within the `connect` timeout budget. An unresolved address may not be accepted for a direct connection; when a proxy is needed, check the corresponding API/configuration.

You can also call `connect(remote)` without specifying a timeout, or use an immediate-connect constructor. However, on unreliable networks, passing a specific positive connect timeout helps control the wait time. A connect timeout of `0` means waiting indefinitely until connected or an error occurs.

**A successful TCP connection does not mean the remote application has already processed a request**: after connecting, bytes must be exchanged according to the application protocol. TCP provides an ordered byte stream and does not automatically preserve "one message" boundaries.

## 6. Example 1: no manual bind, connect chooses the local endpoint automatically

This example runs a TCP server and client **on the same machine**, without using the Internet. The server binds loopback at port `0` and retrieves the actual port; the client only calls `connect` and the operating system assigns the local IP/port.

Create the file `SocketAutoBindDemo.java`:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;

public class SocketAutoBindDemo {
    public static void main(String[] args) throws IOException {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            try (Socket client = new Socket()) {
                System.out.println("new: bound=" + client.isBound()
                        + ", connected=" + client.isConnected());
                System.out.println("new local port: " + client.getLocalPort());
                System.out.println("new remote port: " + client.getPort());

                client.connect(listener.getLocalSocketAddress(), 2_000);
                try (Socket incoming = listener.accept()) {
                    System.out.println("connected: bound=" + client.isBound()
                            + ", connected=" + client.isConnected());
                    System.out.println("auto local port allocated: "
                            + (client.getLocalPort() > 0));
                    System.out.println("client remote = listener local: "
                            + (client.getPort() == listener.getLocalPort()));
                    System.out.println("server sees client local port: "
                            + (incoming.getPort() == client.getLocalPort()));
                    client.getOutputStream().write(65);
                    System.out.println("server received: "
                            + incoming.getInputStream().read());
                }
            }
        }
    }
}
~~~

Compile/run on JDK 17+:

~~~bash
javac SocketAutoBindDemo.java
java SocketAutoBindDemo
~~~

Output when the system allows TCP loopback:

~~~text
new: bound=false, connected=false
new local port: -1
new remote port: 0
connected: bound=true, connected=true
auto local port allocated: true
client remote = listener local: true
server sees client local port: true
server received: 65
~~~

Explanation in execution order:

1. `listener.bind(new InetSocketAddress(loopback, 0))` creates an auto-assigned server port. `listener.getLocalSocketAddress()` returns the exact destination address the client needs.
2. The client's `new Socket()` is not yet bound/connected, so `getLocalPort() == -1` and `getPort() == 0`.
3. `client.connect(...)` automatically chooses the local endpoint; afterward, both `isBound()` and `isConnected()` are `true`.
4. `listener.accept()` returns `incoming`, a server-side `Socket`. `incoming.getPort()` is the client's source port, so it matches `client.getLocalPort()`.
5. The client writes a single byte `65` via `OutputStream`, and the server reads `65`. `ServerSocket` remains the listener; `incoming` is the socket handling that connection.

The example checks conditions using booleans instead of printing port numbers that change on every run. Obtaining the loopback address from the same `InetAddress` object allows it to run in environments preferring either IPv4 or IPv6.

## 7. Example 2: bind the source first, then connect to the destination

This case uses the same loopback server, but the client calls `bind` **first**. We will observe the **bound but not yet connected** state, then compare both sides of the connection.

Create the file `SocketExplicitBindDemo.java`:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;

public class SocketExplicitBindDemo {
    public static void main(String[] args) throws IOException {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            InetSocketAddress requestedLocal = new InetSocketAddress(loopback, 0);
            try (Socket client = new Socket()) {
                client.bind(requestedLocal);
                System.out.println("request port stays zero: "
                        + (requestedLocal.getPort() == 0));
                System.out.println("after bind: bound=" + client.isBound()
                        + ", connected=" + client.isConnected());
                System.out.println("actual local port > 0: "
                        + (client.getLocalPort() > 0));
                System.out.println("remote before connect is null: "
                        + (client.getRemoteSocketAddress() == null));

                InetSocketAddress destination =
                        new InetSocketAddress(loopback, listener.getLocalPort());
                client.connect(destination, 2_000);
                try (Socket incoming = listener.accept()) {
                    System.out.println("client remote port is listener port: "
                            + (client.getPort() == listener.getLocalPort()));
                    System.out.println("accepted remote port is client local port: "
                            + (incoming.getPort() == client.getLocalPort()));
                }
                client.close();
                System.out.println("after close: bound=" + client.isBound()
                        + ", connected=" + client.isConnected()
                        + ", closed=" + client.isClosed());
            }
        }
    }
}
~~~

Run:

~~~bash
javac SocketExplicitBindDemo.java
java SocketExplicitBindDemo
~~~

Output:

~~~text
request port stays zero: true
after bind: bound=true, connected=false
actual local port > 0: true
remote before connect is null: true
client remote port is listener port: true
accepted remote port is client local port: true
after close: bound=true, connected=true, closed=true
~~~

Three easily misunderstood points are demonstrated directly:

- `requestedLocal.getPort()` remains `0` because `InetSocketAddress` is immutable. The **actual** bound port is in `client.getLocalPort()` and `client.getLocalSocketAddress()`.
- After bind but before connect: `isBound() == true`, `isConnected() == false`, and `getRemoteSocketAddress() == null`. `bind` does not create a TCP connection to the destination machine.
- After `close()`: `isClosed() == true`, but `isBound()` and `isConnected()` remain `true` because they record states that once succeeded. A closed socket can no longer be used to exchange bytes.

To demonstrate the post-close state, the program calls `close()` explicitly. Upon exiting `try-with-resources`, the additional close call is safe.

## 8. Reading the right endpoint on each side

Commonly used getters:

| `Socket` API | Returned address/port |
| --- | --- |
| `getLocalAddress()` | Local IP address of the socket |
| `getLocalPort()` | Local port; `-1` when not bound |
| `getLocalSocketAddress()` | Local endpoint; `null` when not bound |
| `getInetAddress()` | Remote IP address after connect |
| `getPort()` | Remote port; `0` when not connected |
| `getRemoteSocketAddress()` | Remote endpoint; `null` when not connected |

For a connection accepted via `ServerSocket listener`:

- `listener.getLocalPort()` is the port the server is listening on.
- `client.getPort()` is the remote port seen from the **client**, equal to the port the server is listening on.
- `incoming.getLocalPort()` is the local port seen from the **server**, also the port the server is listening on.
- `incoming.getPort()` is the remote port seen from the **server**, equal to the client's local port.

For diagnostics when connected, you can log:

~~~java
System.out.println("local=" + client.getLocalSocketAddress());
System.out.println("remote=" + client.getRemoteSocketAddress());
~~~

*This is an illustrative snippet inside a method that has a `client` variable, not a standalone runnable program.* When not bound/connected, one or both values may be `null`. Do not try to parse IPs/ports by splitting the `toString()` string, because the format can differ between IPv4, IPv6, and hostnames.

## 9. Timeouts, exceptions, and closing resources

| Setting/method | Which operation does it wait for? |
| --- | --- |
| `client.connect(remote, 2_000)` | Timeout for establishing the TCP connection within 2,000 ms |
| `client.setSoTimeout(2_000)` | Timeout for blocking `read()` operations on `InputStream` |
| `listener.setSoTimeout(2_000)` | Timeout for `ServerSocket.accept()` |

These are three **different** timeouts. Do not interpret the connect timeout as the maximum time for DNS + read + write + the entire application request. In the APIs above, `0` usually means no timeout limit; negative values are invalid.

Common errors:

- **`BindException`:** the source port is already in use or the source IP cannot be bound. Choosing port `0` helps avoid unnecessarily fixing a port.
- **`ConnectException`:** the destination host/port refuses the connection, for example when no service is listening.
- **`SocketTimeoutException`:** the connect, read, or accept timeout has expired, respectively. A timeout does not by itself identify the exact network cause.
- **`UnknownHostException` or unresolved address:** there is a problem when hostname resolution is needed. `new InetSocketAddress(String, int)` may attempt DNS right in the constructor and retain an unresolved state if it fails.
- **`SocketException`/`IOException`:** the socket is closed, in an invalid state, or another I/O error occurred. `IllegalArgumentException` is used for many invalid arguments, such as a negative timeout.

Always close `Socket`/`ServerSocket` using `try-with-resources` to avoid leaking socket descriptors and connections. If connect fails, close that socket and create a new `Socket` for an independent retry. Do not assume you can call `bind` multiple times on an already bound socket, or change the source address after already connected. When handling multiple clients, the server can continue calling `accept()` on the listener; each accepted socket must be managed and closed separately.

Do not rely on `SO_REUSEADDR` as a guarantee that every overlapping IP/port bind pair is valid: behavior depends on the operating system and socket state.

## 10. Common mistakes and how to fix them

1. **Using `client.bind(serverIp:serverPort)`:** wrong role. Bind takes the **client machine's** address, while the server address goes in `connect`.
2. **Using port `0` for the remote endpoint:** port `0` is used to request a port when **binding locally**. The client must know the server's actual port.
3. **Hardcoding a single source port for every session:** prone to port conflicts and makes concurrent runs difficult. Use an auto-assigned port or omit `bind` when there is no special requirement.
4. **Thinking `new Socket()` is already connected:** the no-arg constructor creates an unconnected socket. Only constructors taking host/port actively connect immediately.
5. **Thinking a successful bind means the server has responded:** bind does not contact the server at all; you must connect first, and then the application still has to send/receive data according to the protocol.
6. **Calling `bind` after `connect`:** at that point the socket already has a local endpoint; you cannot re-bind to change the source.
7. **Using `isConnected()` instead of `isClosed()`:** `isConnected()` can remain `true` after closing; nor does it guarantee the network will not drop between two operations.
8. **Not bounding wait times:** connect/read/accept can block; set appropriate timeouts and handle `SocketTimeoutException`.
9. **Binding wildcard when only intending to serve locally:** test servers should bind loopback to limit the scope of listening interfaces; firewall and network policies must still be considered.
10. **Reading the port from the request object `InetSocketAddress(..., 0)` after bind:** it remains `0`. Read from `Socket.getLocalPort()` or `ServerSocket.getLocalPort()` after a successful bind.

## 11. Self-check and practice

**Question 1.** You just called `Socket s = new Socket()`. What are `s.isBound()` and `s.isConnected()`, and what is `s.getLocalPort()`?

Answer: `false`, `false`, and `-1`. `s.getPort()` when not connected is `0`.

**Question 2.** `s.bind(new InetSocketAddress(loopback, 0))` succeeded, but `connect` has not been called yet. Is there an actual local port yet? Is there a remote endpoint yet?

Answer: there is an actual local port, read via `s.getLocalPort()`; there is no remote endpoint yet, so `s.getRemoteSocketAddress() == null`.

**Question 3.** A client has local port `51432` and connects to server port `8080`. After `accept`, what is `incoming.getPort()` on the server typically?

Answer: `51432`. This is the remote port **seen from the server**; `incoming.getLocalPort()` is `8080`.

**Question 4.** Remove `client.bind(requestedLocal)` from the second example. What is `client.getLocalPort()` before connect, and how does it change after connect succeeds?

Answer: before connect it is `-1`; after connect, the operating system automatically binds an actual local port (usually > 0).

**Practice:** run both examples several times and observe the actual port numbers by printing `getLocalPort()`. Do not write tests asserting that two runs **must** be assigned two different ports: the operating system may reassign a released port. Add statements to print `getLocalSocketAddress()`/`getRemoteSocketAddress()` after connect to compare with the values on the `incoming` side.

## API Documentation

- [`Socket` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html)
- [`ServerSocket` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html)
- [`InetSocketAddress` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetSocketAddress.html)
