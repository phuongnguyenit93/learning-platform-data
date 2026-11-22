# InetSocketAddress: Resolved, Unresolved, and Ephemeral Ports

## 1. What Does InetSocketAddress Describe?

In Java networking programming, an endpoint typically needs an **IP address or hostname** and a **port number**. The `java.net.InetSocketAddress` class represents that pair of information to pass into operations such as `Socket.connect(...)`, `ServerSocket.bind(...)`, or `DatagramSocket.bind(...)`.

Three different questions must be separated:

1. **Which machine is it pointing to?** An `InetAddress` with a known IP, or only an unresolved hostname?
2. **Which port is being used?** What is the port number declared in the `InetSocketAddress`?
3. **Has the real socket been bound by the operating system to an address/port yet?** Only a `bind` operation (or a connect that causes the socket to be auto-bound to a port) allocates actual network resources.

`InetSocketAddress` is an **immutable** object: once created, its hostname, IP, or port cannot be modified. Creating this object **does not open a TCP connection, listen, or reserve a port**. Specifically, the constructor taking a hostname may perform a domain name lookup when creating the object.

For example, a test server might request `127.0.0.1:0`. The `0` is a request for the operating system to choose a port upon `bind`, not yet the actual port. After binding succeeds, the socket may be listening on `127.0.0.1:53124` (the number is illustrative only); to know the actual number, you must query the **bound socket**.

## 2. Four Ways to Create an Address and Their Meanings

| Creation method | Address resolution | State/use case |
| --- | --- | --- |
| `new InetSocketAddress(port)` | Creates an IP address representing **all local interfaces** (wildcard); no DNS lookup | `isUnresolved() == false`; commonly used for server `bind` |
| `new InetSocketAddress(inetAddress, port)` | Takes an existing `InetAddress`; no hostname lookup needed at this step | `isUnresolved() == false`; selects a specific IP, e.g., loopback |
| `new InetSocketAddress(hostname, port)` | **Attempts to resolve** the hostname upon creation; if unsuccessful, still creates the object | Can be resolved or unresolved, depending on the resolution result |
| `InetSocketAddress.createUnresolved(hostname, port)` | **Does not resolve** the hostname upon creation | Always unresolved; used when you want to defer resolution or let a proxy handle it |

Accepted ports range from **0 to 65535**; values outside this range throw `IllegalArgumentException`. Port `0` is designed for the system to choose a port for a **local bind** operation. For a remote service destination, the application usually must know the actual port, such as `443`; port `0` must not be understood as "automatically finding the port of the remote server".

In the form taking `InetAddress`, passing `null` for the address parameter also means wildcard. The wildcard address can be represented as IPv4 or IPv6 depending on the system. It means **any appropriate local address when binding**, not a remote server address that can be connected to.

### Methods to Remember

| Method | Meaning |
| --- | --- |
| `isUnresolved()` | `true` when the object holds a hostname without an `InetAddress` |
| `getAddress()` | Returns `InetAddress`, or `null` if unresolved |
| `getHostString()` | Gets the stored hostname or IP string representation **without triggering a reverse DNS lookup** |
| `getHostName()` | Gets the hostname; in some cases may trigger a reverse DNS lookup |
| `getPort()` | Returns the port number recorded in the object, **does not reflect the port later assigned to the socket** |

Do not parse the string from `toString()` to extract hostname/port: its representation may contain IPv6 square brackets, `/`, or an `<unresolved>` part. Use the corresponding getters instead.

## 3. Resolved vs. Unresolved: Is There an IP Yet?

**Resolved** means `InetSocketAddress` has an `InetAddress`. The IP may have been passed directly, for example `InetAddress.getLoopbackAddress()`, or determined through hostname resolution. In that case:

- `isUnresolved()` is `false`.
- `getAddress()` is not `null`.
- This **does not prove** that the target machine is running, the port is open, or the connection will succeed.

**Unresolved** means it still holds the hostname and port but has no IP yet:

- `isUnresolved()` is `true`.
- `getAddress()` is `null`; calling a method on this result without checking will cause a `NullPointerException`.
- `getHostString()` still returns the hostname for logging, passing to another layer, or a proxy.

There are **two paths to unresolved**: name resolution failing when using the constructor taking a `String`, or deliberately not resolving by using `createUnresolved`. Therefore, "unresolved" does not mean "the hostname is definitely wrong". A SOCKS proxy, for instance, can be given the hostname to resolve on the proxy side; the ability to handle unresolved addresses depends on the API and how the connection is set up. When using a direct connection, check the API's requirements instead of assuming every socket type accepts unresolved addresses.

An already created `InetSocketAddress` **does not automatically transition from unresolved to resolved**. If resolution is needed later, you can call `InetAddress.getByName(hostname)` (handling `UnknownHostException`), and then **create a new `InetSocketAddress` object** from the IP and the old port. `getHostString()` only retrieves the string; it does not perform that resolution step.

Conversely, a wildcard address used for `bind` has a special `InetAddress` and is **not** considered unresolved. This is the difference between "an IP representing all local interfaces" and "knowing only a hostname without an IP yet".

### Example 1: Distinguishing the Three States with Java 17+

Create the file `AddressStatesDemo.java`:

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;

public class AddressStatesDemo {
    public static void main(String[] args) {
        InetSocketAddress resolved =
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 8080);
        InetSocketAddress unresolved =
                InetSocketAddress.createUnresolved("example.com", 443);
        InetSocketAddress wildcard = new InetSocketAddress(0);

        System.out.println("resolved: " + !resolved.isUnresolved());
        System.out.println("unresolved: " + unresolved.isUnresolved());
        System.out.println("unresolved IP null: " + (unresolved.getAddress() == null));
        System.out.println("unresolved host: " + unresolved.getHostString());
        System.out.println("wildcard: " + wildcard.getAddress().isAnyLocalAddress());
        System.out.println("requested port: " + wildcard.getPort());
    }
}
~~~

Run:

~~~bash
javac AddressStatesDemo.java
java AddressStatesDemo
~~~

Deterministic output, independent of DNS or an external server:

~~~text
resolved: true
unresolved: true
unresolved IP null: true
unresolved host: example.com
wildcard: true
requested port: 0
~~~

Explanation: `getLoopbackAddress()` provides a known loopback IP; `createUnresolved` intentionally holds only the hostname; `new InetSocketAddress(0)` has a wildcard IP and requested port `0`. There is no `bind` call yet, so there is no actual ephemeral port yet. `new InetSocketAddress("example.com", 443)` is not used in this fixed-state test because the result depends on whether DNS can resolve it at runtime.

## 4. When Does Ephemeral Port Assignment Happen?

When binding to **local port 0**, the operating system selects an available port according to its own mechanism (typically from the ephemeral/temporary port range). The flow:

1. Create the requested address, for example `new InetSocketAddress(InetAddress.getLoopbackAddress(), 0)`. At this point `getPort() == 0`.
2. Create an unbound socket, for example `new ServerSocket()`.
3. Call `server.bind(requested)`. If successful, the operating system has selected and bound a real port to the socket.
4. Read `server.getLocalPort()` or `((InetSocketAddress) server.getLocalSocketAddress()).getPort()` to get the assigned port.
5. Pass the real port to the client/other test while the server is still running. Closing the socket releases the resource; do not assume the next run will reuse it or get a different port number.

**Key point:** the `requested` object still has `getPort() == 0` after step 3, because it is immutable. The real port belongs to **the state of the bound `ServerSocket`**, and is not backfilled into the requested object.

`new ServerSocket(0)` is a shorthand to create a server socket and immediately bind it to an ephemeral port on the wildcard address. However, when you only want to accept connections from the current machine, you should explicitly bind to `InetAddress.getLoopbackAddress()` instead of the wildcard. Binding to the wildcard may cause the service to listen on multiple network interfaces, depending on the system and firewall policy.

### Example 2: Getting the Real Port and Connecting Locally

Create the file `DynamicPortDemo.java`:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;

public class DynamicPortDemo {
    public static void main(String[] args) throws IOException {
        InetSocketAddress requested =
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0);
        System.out.println("before bind: " + requested.getPort());

        try (ServerSocket server = new ServerSocket()) {
            server.bind(requested);
            InetSocketAddress actual =
                    (InetSocketAddress) server.getLocalSocketAddress();

            System.out.println("selected port valid: " + (server.getLocalPort() > 0));
            System.out.println("same port: " + (server.getLocalPort() == actual.getPort()));

            try (Socket client = new Socket()) {
                client.connect(actual, 3_000);
                try (Socket accepted = server.accept()) {
                    System.out.println("connected: " + client.isConnected());
                }
            }
        }
    }
}
~~~

Run:

~~~bash
javac DynamicPortDemo.java
java DynamicPortDemo
~~~

Output when the machine allows creating local TCP sockets:

~~~text
before bind: 0
selected port valid: true
same port: true
connected: true
~~~

The port number chosen by the operating system varies by environment, so the program **checks conditions** rather than printing a fixed port number. The client uses the exact `actual` retrieved from the bound server, so there is no need to guess the port. The two `try-with-resources` blocks ensure the sockets are closed upon completion; `bind` or `connect` errors may throw `IOException`. The `3_000` argument to `connect` is the connection timeout in milliseconds, not a port.

Similarly, the client-side socket is also usually assigned a **local port** automatically by the operating system when connecting if the application has not bound it. Distinguish the client's local port from the **destination** port the client connects to.

## 5. Choosing the Right Creation Method for the Purpose

| Scenario | Appropriate approach | Reason |
| --- | --- | --- |
| Server listening on all interfaces on port 8080 | `server.bind(new InetSocketAddress(8080))` | Wildcard is used for **local** addresses |
| Test server listening only locally and wanting an ephemeral port | `server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0))` | Restricted to loopback, get port via `getLocalPort()` |
| Client connecting to a hostname and accepting immediate resolution | `new InetSocketAddress("service.example", 443)` | Can resolve the hostname at creation time |
| Wanting to keep the hostname to resolve later/via proxy | `InetSocketAddress.createUnresolved("service.example", 443)` | Does not force DNS to run at creation time |
| Already having an IP beforehand | `new InetSocketAddress(ip, 443)` | No extra hostname lookup needed in the constructor |

The name `service.example` in the table is illustrative only and does not assume it exists in DNS. For real connection code, determine the host, port, resolution mechanism, and timeout according to the target system.

In TCP communication, `ServerSocket.bind` is **binding a local listening endpoint**, whereas `Socket.connect` is **connecting to a remote endpoint**. Both use `InetSocketAddress`, but the direction of the operation differs. For example, `0.0.0.0:8080`/wildcard is appropriate when **binding**; a client should not treat `0.0.0.0` as a remote service IP.

## 6. Common Mistakes and Misconceptions

1. **Thinking `new InetSocketAddress(0)` has already reserved a port.** Wrong: the object is not bound yet; `getPort()` is still 0. You must bind successfully and then query the socket.
2. **Thinking resolved means connectable.** Wrong: knowing the IP does not confirm the server is running, the port is open, the network route is working, or the firewall allows it.
3. **Thinking unresolved is always an error.** You can deliberately defer DNS with `createUnresolved`; some connection paths through a proxy require the original hostname. Conversely, do not pass an unresolved address to an API that only accepts a resolved IP.
4. **Calling `getAddress().getHostAddress()` without checking.** For unresolved, `getAddress()` is `null`; check `isUnresolved()` first.
5. **Using `getHostName()` for logging without considering DNS.** It can perform a reverse lookup in some cases. `getHostString()` does not perform a reverse lookup.
6. **Using port 0 for a destination address hoping Java will automatically find the service.** The automatic port selection mechanism applies to **local bind**, not discovering a remote server's port.
7. **Binding to the wildcard when you only want to run local tests.** Actively use loopback to avoid opening a listening endpoint on unnecessary interfaces.
8. **Relying on `toString()` or simple hostname comparison.** Use getters; `equals()` compares both the port and IP address for resolved addresses, or the hostname (case-insensitive) for an unresolved pair. The two different states are not equivalent by default.
9. **Assuming DNS is always stable and unique.** A hostname may have multiple IPv4/IPv6 records; the resolution result, IP order, and reachability may vary by machine, network, and time.

## 7. Self-Check

**Question 1.** What is `getAddress()` for `InetSocketAddress.createUnresolved("localhost", 9000)`, even though `localhost` can normally be resolved?

Answer: `null`. `createUnresolved` intentionally skips resolution, so `isUnresolved() == true`.

**Question 2.** Create `InetSocketAddress requested = new InetSocketAddress(0)` and then bind successfully. Does `requested.getPort()` change to the assigned port?

Answer: no. It remains `0`. Get the actual port from `ServerSocket.getLocalPort()` or the corresponding socket.

**Question 3.** Why is `new InetSocketAddress(0)` not considered unresolved?

Answer: this constructor already has a wildcard `InetAddress` representing local addresses; unresolved is the state of **not having an IP for a hostname yet**, not the state of "not having bound a port yet".

**Short exercise:** Modify `DynamicPortDemo` to print `server.getLocalPort()`, run it multiple times, and observe the output. Explain why you **must not** write an assertion requiring two runs to pick two different ports. Then replace loopback with wildcard and state the difference in the scope of interfaces on which the server can listen.

## API Documentation

- [`InetSocketAddress` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetSocketAddress.html)
- [`ServerSocket` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html)
- [`Socket` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html)
