# Port 0, Bind Addresses, and Advertising the Assigned Address

**Topic:** Java Advance - networking  
**Knowledge Group:** TCP Servers

When a TCP server runs in tests, launches multiple instances in parallel, or is started by another process, hardcoding a port such as 8080 easily causes conflicts. In Java, **binding to port 0** lets the operating system choose an available TCP port. After **binding succeeds**, the server retrieves the **actual port** from **ServerSocket.getLocalPort()** or **getLocalSocketAddress()**, and then advertises the correct endpoint to clients.

However, the **assigned port** is only one part of the endpoint. The **bind address** specifies the local network addresses on which the listener accepts connections; the **advertised address** is the host/IP and port **that clients can actually use to reach it**. These two addresses can differ when the server binds a wildcard address, runs in a container, sits behind NAT/a load balancer, or serves clients on a different network.

This lesson follows the exact sequence: **choose a bind address → request port 0 → OS assigns a port → read the real endpoint → choose a client-reachable address → advertise after the server is ready → client connects → revoke the information on shutdown**.

## 1. What Does Port 0 Mean?

A TCP listener address has two key components:

~~~text
Local IP address + local TCP port

Specific bind example: 127.0.0.1:53217
Wildcard bind example: 0.0.0.0:53217
IPv6 loopback example: [::1]:53217
~~~

**Port 0 in a bind call** is a special request: **let the operating system choose an available port**. The chosen port usually comes from the ephemeral port range configured by the operating system. The exact number is not fixed and can change on every run. **Port 0 is not a service port that clients are told to connect to**; after binding, the listener has a **non-zero** port.

In Java:

~~~java
// Snippet: requires importing java.net.* and closing the socket after use.
ServerSocket listener = new ServerSocket(); // Not yet bound.
int before = listener.getLocalPort();       // -1.

listener.bind(new InetSocketAddress(
        InetAddress.getLoopbackAddress(), 0)); // OS selects the actual port.

int assignedPort = listener.getLocalPort();   // Typically 1..65535.
SocketAddress bound = listener.getLocalSocketAddress();
~~~

**getLocalPort() == -1** means the ServerSocket has **never been successfully bound**. After binding, this value is the actual port; closing the socket later **does not mean** the getter reverts to -1. **ServerSocket.isBound()** indicates whether the socket has been bound, but it can still return true after **close()**; use **isClosed()**, service state, and health checks as well when you need to determine whether the listener is still active.

There are two common approaches:

- **new ServerSocket(0)**: the constructor immediately binds to a suitable wildcard address and asks the OS to assign a port. Convenient for quick demos/tests when selecting a specific interface is unnecessary.
- **new ServerSocket()**, followed by **bind(new InetSocketAddress(address, 0), backlog)**: separates creation from binding, allowing you to choose the address and configure options needed before bind. This is the clearer approach when teaching about bind addresses and dynamic ports.

A **client Socket** can also be assigned an ephemeral source port by the OS when connecting; that source port is **not** the listening port of the ServerSocket. **ServerSocket.accept()** returns a **new Socket** for each connection without changing the listener port.

## 2. Bind Is an OS-Level Action, Not a Java Variable

**ServerSocket.bind(...)** asks the OS TCP/IP stack to register a local endpoint for listening for connections. The OS checks whether the address belongs to a valid network interface/namespace context, whether the port is available, and whether permissions and policies allow it, then creates the listener. After binding succeeds:

1. The listener has a **local address** and a **local port**.
2. The kernel can handle the initial TCP connection handshake and place connections waiting for **accept()** into the appropriate queue.
3. **accept()** returns the socket for each accepted connection.
4. The Java application continues reading/writing bytes and executing the protocol on that socket.

**A successful bind does not prove that every client on the Internet can connect**. Firewalls, routes, interfaces, container port mappings, ACLs, NAT, proxies, and application readiness can still block connections.

The **backlog** parameter in **ServerSocket.bind(endpoint, backlog)** is a request for the queue of pending connections waiting to be accepted; the OS may adjust or cap it. It is not the maximum number of clients the entire application can serve concurrently, nor is it a request timeout.

### Why shouldn't you probe for a "free" port and then close it?

A common anti-pattern:

~~~java
// Illustrates a pattern that SHOULD NOT be used to reserve a port.
int port;
try (ServerSocket probe = new ServerSocket(0)) {
    port = probe.getLocalPort();
}
// probe is closed; the port is no longer held by this process.
ServerSocket server = new ServerSocket(port); // May fail due to a race.
~~~

Between **probe.close()** and the second bind, another process can claim that port: this is a **time-of-check to time-of-use (TOCTOU)** bug. The right approach is to **keep the ServerSocket that bound successfully**, read **getLocalPort()** from that open socket, and use that same socket as the listener. There is no need to "check for a free port" before requesting a bind to port 0.

## 3. Bind Address: Loopback, Wildcard, or a Specific IP?

Even with the same port 0 request, the bind address changes the scope of accepted connections.

| Bind address | Meaning and usage example | What to remember when advertising |
| --- | --- | --- |
| **127.0.0.1** | IPv4 loopback; clients on the same host | Do not advertise 127.0.0.1 to clients on other machines |
| **::1** | IPv6 loopback; clients on the same host | When formatting with a port, use **[::1]:port** |
| **0.0.0.0** | IPv4 wildcard; listens on appropriate local IPv4 addresses | **0.0.0.0** is a bind address, not a destination host for external clients |
| **::** | IPv6 wildcard; dual-stack/IPv4-mapped behavior depends on OS and configuration | Do not assume it accepts IPv4; verify on the target system |
| **192.0.2.10** | Illustrates binding a specific IPv4 address assigned to an interface | Bind succeeds only when the IP is valid in the environment; clients must have a route and access permission |
| **Address of a real interface** | Used on hosts with multiple NICs, network namespaces, or multiple services | Do not assume this is a public address; it depends on routing, NAT, and firewalls |

**192.0.2.10** is an example address from the documentation range; it is not an IP you should use on your machine.

### Loopback is suitable for tests

~~~java
InetAddress localOnly = InetAddress.getLoopbackAddress();
ServerSocket listener = new ServerSocket();
listener.bind(new InetSocketAddress(localOnly, 0));
~~~

**InetAddress.getLoopbackAddress()** returns the system's loopback address, which may be IPv4 or IPv6. A test client should use **the exact same address object** to connect, avoiding cases where the server binds **127.0.0.1** while **localhost** on the client resolves to **::1** or vice versa.

### Wildcard is suitable when accepting from multiple interfaces

~~~java
// Snippet: requests an IPv4 wildcard bind; handle IOException in real code.
InetAddress allIPv4 = InetAddress.getByName("0.0.0.0");
ServerSocket listener = new ServerSocket();
listener.bind(new InetSocketAddress(allIPv4, 0));
int assignedPort = listener.getLocalPort();
~~~

This is an example of an **IPv4 wildcard bind**. It does not create a "public IP" to return to clients. You must **separately choose** a hostname/IP appropriate for **the client's location**; in a container or behind NAT, the external host port may also differ from the port bound inside.

**Open-access risk:** wildcard binding can expose the service on more interfaces than intended. Use network ACL/firewall rules, TLS/authentication, and a bind address suited to your actual requirements.

### Binding to a specific IP

If a machine has multiple NICs, binding to a specific IP restricts the local endpoint on which the socket listens. That IP must be usable within the process's network namespace. **InetAddress.getLocalHost()** is not a reliable formula for choosing an advertised address: the hostname may resolve to loopback, an internal IP, one of several NICs, or another address unreachable by clients.

## 4. Reading the Actual OS-Assigned Address and Port

With a bound **ServerSocket**:

~~~java
int port = listener.getLocalPort();
InetAddress bindAddress = listener.getInetAddress();
InetSocketAddress actual = (InetSocketAddress) listener.getLocalSocketAddress();

System.out.println(actual.getPort() == port);   // true if the bind is valid.
~~~

This snippet must be placed in a context with an already-bound **listener** variable; the stdout in the comment holds only when the listener is as described.

- **getLocalPort()** returns the assigned TCP port, which is the most important value when binding port 0.
- **getInetAddress()** returns the local address used for binding. For a wildcard bind, this is still the **wildcard address**, not the address external clients will connect to.
- **getLocalSocketAddress()** returns a **SocketAddress** (for TCP Internet sockets, an **InetSocketAddress**) containing both address and port. It returns null if the ServerSocket has never been bound.
- **getLocalSocketAddress()** may continue reflecting the previously bound endpoint even after the socket is closed; do not use the getter as a health check.

**Do not read the port before binding and advertise -1 or 0.** Also, **do not advertise the port of a Socket returned by accept()** because that socket represents a single connection, not the service listener. Read the endpoint information from the open **ServerSocket**.

In Java NIO, the same principles apply to **ServerSocketChannel**:

~~~java
// Snippet: requires importing java.net.* and java.nio.channels.ServerSocketChannel.
try (ServerSocketChannel channel = ServerSocketChannel.open()) {
    channel.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));
    InetSocketAddress actual =
            (InetSocketAddress) channel.getLocalAddress();
    System.out.println(actual.getPort() > 0); // true when bind succeeds.
}
~~~

**ServerSocketChannel.getLocalAddress()** reflects the local address after binding; you still need to choose an advertised address appropriate for clients. For HTTP, WebSocket, or TLS running over TCP, port 0 and bind addresses follow the same rules, while the **scheme and access path** must match the actual protocol.

## 5. Endpoint Registration Lifecycle After Bind

A reliable implementation sequence is:

~~~text
PREPARE
  ├─ choose bind host/interface and access permissions
  ├─ choose port = 0 when the OS should assign one automatically
  └─ configure socket options that must be set before bind
          ↓
BIND SUCCEEDS
  ├─ OS registers the listener and assigns the actual port
  └─ read listener.getLocalPort() / getLocalSocketAddress()
          ↓
PREPARE TO SERVE TRAFFIC
  ├─ accept loop / worker / dependencies are ready
  └─ determine reachable host and exposed port for clients
          ↓
ADVERTISE (READY)
  ├─ print structured metadata / IPC / registry / service discovery
  └─ clients obtain the endpoint from the published source, without guessing the port
          ↓
SHUTDOWN
  ├─ stop accepting new connections, revoke registration / mark not-ready
  └─ close listener, handle remaining connections according to policy
~~~

Two concepts must be kept separate:

- **Bound address**: the address accepted by the OS for the listener. For example, **0.0.0.0:52741** inside a container.
- **Advertised endpoint**: the address/port actually used by a specific group of clients. For example, **tcp-service.internal.example:52741**, or **gateway.example.org:443** if external clients connect through a proxy. You must obtain the **assigned port** of the internal listener, then account for port mapping/proxying if present.

**Advertise only after binding succeeds and the application is genuinely ready to serve.** If you register first and bind fails, clients will see a broken endpoint. Conversely, if the listener is bound but the service cannot yet handle requests, advertising too early can cause health checks or initial requests to fail. The system's readiness flow must reflect actual state, not just **isBound()**.

## 6. Complete Java 17+ Example: Port 0 and Advertising via an In-Memory Directory

This example uses a **single process** to focus on the mechanism. The listener binds to **loopback:0**; the OS assigns the actual port; the program stores **Endpoint(address, actualPort)** in a directory under the service name **echo**. The client reads the directory and connects using the exact advertised endpoint. This is an **in-process** way to share information to illustrate discovery. In multi-process or multi-host applications, the directory must be replaced by an appropriate shared publishing channel.

Create the file **PortZeroServerDemo.java**:

~~~java
import java.io.DataInputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class PortZeroServerDemo {
    record Endpoint(InetAddress address, int port) {
        InetSocketAddress socketAddress() {
            return new InetSocketAddress(address, port);
        }
    }

    public static void main(String[] args) throws Exception {
        Map<String, Endpoint> directory = new HashMap<>();
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket()) {
            System.out.println("beforeBindPort=" + listener.getLocalPort());
            listener.bind(new InetSocketAddress(loopback, 0), 16);
            listener.setSoTimeout(3_000);

            Endpoint endpoint = new Endpoint(loopback, listener.getLocalPort());
            directory.put("echo", endpoint);
            System.out.println("bound=" + listener.isBound());
            System.out.println("assignedPortValid=" + (endpoint.port() > 0));
            System.out.println("publishedMatchesBind=" +
                    (endpoint.port() == listener.getLocalPort()
                     && endpoint.address().equals(listener.getInetAddress())));

            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> serverResult = executor.submit(() -> {
                    try (Socket accepted = listener.accept()) {
                        accepted.setSoTimeout(3_000);
                        byte[] request = new byte[4];
                        new DataInputStream(accepted.getInputStream())
                                .readFully(request);
                        accepted.getOutputStream().write(
                                "PONG".getBytes(StandardCharsets.US_ASCII));
                        return new String(request, StandardCharsets.US_ASCII);
                    }
                });

                Endpoint discovered = directory.get("echo");
                try (Socket client = new Socket()) {
                    client.connect(discovered.socketAddress(), 3_000);
                    client.setSoTimeout(3_000);
                    client.getOutputStream().write(
                            "PING".getBytes(StandardCharsets.US_ASCII));
                    byte[] response = new byte[4];
                    new DataInputStream(client.getInputStream())
                            .readFully(response);
                    System.out.println("clientResponse=" +
                            new String(response, StandardCharsets.US_ASCII));
                }
                System.out.println("serverRequest=" +
                        serverResult.get(3, TimeUnit.SECONDS));
            } finally {
                directory.remove("echo", endpoint);
                executor.shutdownNow();
            }
            System.out.println("directoryCleaned=" +
                    !directory.containsKey("echo"));
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 PortZeroServerDemo.java
java PortZeroServerDemo
~~~

**Stdout from a successful run** (compiled with **--release 17** and verified on JDK 24):

~~~text
beforeBindPort=-1
bound=true
assignedPortValid=true
publishedMatchesBind=true
clientResponse=PONG
serverRequest=PING
directoryCleaned=true
~~~

What does each line show?

1. **beforeBindPort=-1**: the **new ServerSocket()** constructor has not registered a listener yet.
2. **listener.bind(loopback:0, 16)**: the OS picks an available port; it is not pre-selected by "probe and close". **16** is the requested backlog, which the OS may adjust.
3. **assignedPortValid=true**: after binding, **getLocalPort() > 0**. The program intentionally does not print a hardcoded port because the assigned number varies between runs.
4. **Endpoint** holds the **InetAddress** and actual port number, and is registered via **directory.put("echo", endpoint)**. The line **publishedMatchesBind=true** confirms the directory entry uses the exact bound endpoint in the demo.
5. The client calls **directory.get("echo")** and then **connect(discovered.socketAddress(), 3000)**. It does not know the port in advance and does not need to scan ports.
6. The server thread calls **accept()**, reads **4 bytes** using **DataInputStream.readFully(...)**, and then replies with **PONG**. The client also reads all 4 bytes; it never assumes a single read returns all bytes.
7. **directory.remove(...)** removes the advertised entry when the demo finishes. This is an important lifecycle step so clients do not use an endpoint that is no longer active.

**Intentional limitations of the demo:** The directory is just a **HashMap within a single process**, not a networked service discovery system. The PING/PONG exchange is a minimal 4-byte protocol; real applications need clear framing, timeouts, and payload limits. Loopback enables self-verification without opening ports to an external network. Output order is deterministic on a successful run because the main thread prints results after receiving the response and waiting on the server's **Future**.

## 7. How Should the Real Address Be Advertised to Clients?

**There is no Java API that automatically advertises an assigned port to all clients.** The server must choose an appropriate **out-of-band communication channel**. What needs to be sent is typically **protocol + advertised host + advertised port + readiness status**, plus service ID/instance ID, TLS identity, and registration TTL/lease when needed.

| Context | Common advertising method | Notes |
| --- | --- | --- |
| Automated tests in the same JVM | Return **server.getLocalPort()** to the test or store **Endpoint** in a shared variable | Reuse the open listener; test clients connect to the exact assigned IP/port |
| Parent process spawns child server | Child writes a structured **READY** record to stdout/pipe/IPC after bind; parent parses and uses it | Synchronize on READY; separate normal logs from machine-readable records |
| Two processes on the same host | Runtime config file, auxiliary UNIX-domain/named pipe, or IPC channel | Requires proper read permissions, atomic writes, stale-file cleanup, and dead-process detection |
| Multiple instances across a network | Service registry/discovery (with heartbeat, lease, or health check) | Advertise reachable hostname/IP and actual port; deregister on shutdown |
| Service behind a gateway/proxy | Advertise the stable gateway/service address | Public address may have a different port from the internal listener |
| Distributed test system | Controller/runner receives post-bind metadata and provides it to test clients | Do not read a static port from config when the server binds port 0 |

Example **discovery record** illustrating the result after the OS assigns port **52741**:

~~~json
{
  "service": "catalog-tcp",
  "protocol": "tcp",
  "host": "service.internal.example",
  "port": 52741,
  "ready": true
}
~~~

This is a **sample record**, not output from the demo; another run may be assigned a different port. The **host** field must be chosen according to the client's network; if the server binds a wildcard address, **do not** use literal **0.0.0.0** or **::** as the registered hostname. If clients require TLS, metadata may need a scheme/server identity matching the certificate. Do not use this JSON as a wire protocol over TCP unless the application explicitly defines JSON read/write framing.

### Advertising within the same process

After binding:

~~~java
// Snippet: server has successfully bound to the required address.
InetSocketAddress actual =
        (InetSocketAddress) listener.getLocalSocketAddress();
int port = actual.getPort();
endpointDirectory.put("catalog-tcp", new Endpoint(advertisedAddress, port));
~~~

This is a **design pseudo-snippet**, not a standalone program: **endpointDirectory**, **Endpoint**, and **advertisedAddress** are types/objects the application must define itself. Within one JVM, you can use dependency injection, a value returned from a start method, a Future/Promise, or a thread-safe map. If multiple threads access the directory, **HashMap** is usually insufficient for synchronization; consider **ConcurrentHashMap** or appropriate synchronization. The demo above registers and reads the map on the main thread, so there is no concurrent map access.

### Advertising across processes or over the network

A parent process can wait for a structured notification line after the child binds. A network registry can store **(service name, reachable host, port, instance ID)** along with health/lease state. Before returning an endpoint to a client, verify that the service is still ready. When the server stops, remove/expire the record; on restart, re-register the new port because port 0 may change.

**Writing to logs without a consumer that can reliably parse them is not service discovery.** If logs are mixed into regular stdout, a parser can easily misread or miss the READY state. The metadata channel should have a clear format, synchronization mechanism, and error handling.

### Host, port, and IPv6

When formatting an endpoint as a **host:port** string, IPv6 addresses contain colons inside the address; the **[::1]:52741** form avoids ambiguity when splitting the port. More simply, keep **host** and **port** as **two separate fields** and use **new InetSocketAddress(host, port)** or the **InetSocketAddress(InetAddress, int)** constructor on the client.

For actual HTTP/HTTPS, you can use **java.net.URI** with the **http/https** scheme and appropriate host/port components; **do not** prepend **http://** to a TCP service using a custom protocol like PING/PONG in the demo. An endpoint represents network reachability; its address syntax must match the protocol the server actually speaks.

## 8. Containers, NAT, Proxies, and Multiple Interfaces: Bind vs. Advertise

### Docker/containers

A process inside a container may bind **0.0.0.0:52741**. Clients outside the container cannot reach the container IP or that port by default. When using Docker port publishing, a host port is mapped to a configured **container port**. For example, if the **actual container listener is port 52741**, mapping host port 18080 to 52741 must be configured to match. If the container binds port 0 and picks a different port on every run, a static mapping to 52741 will break.

**Port 0 inside the application** is different from asking Docker to **auto-assign a host port** when publishing a **fixed container port**. The two port allocations happen in different network namespaces/mapping layers and must be managed separately.

### Kubernetes/service mesh/load balancers

A Kubernetes Service typically uses a stable service address/port pointing to the workload's targetPort. If the application inside the Pod binds port 0 and picks a random port, standard routing/service discovery **will not automatically know** that new port unless a matching update mechanism exists. For typical production services, a **fixed bind port inside the workload** paired with a **stable Service address** is usually simpler. Port 0 is especially useful in **tests, local multi-instance runs, embedded servers**, or when a controller genuinely performs dynamic registration.

Behind a reverse proxy or TLS termination, the client-facing endpoint might be **https://gateway.example.org:443**, while the backend binds TCP on **10.0.2.15:52741**. Clients do not need to know the internal port if the proxy routes traffic properly. Advertise the endpoint from the **consumer's perspective**, rather than blindly copying the ServerSocket's fields.

### Multi-NIC hosts

A server may have an internal IPv4 address, IPv6, a VPN interface, and a management network. Wildcard binding lets the listener accept on the appropriate interfaces, but choosing which IP to advertise depends on the client's network. Relying blindly on **InetAddress.getLocalHost()**, the machine's hostname, or the first IP found can select the wrong path. Configuring an explicit advertised address or obtaining it from a reliable deployment/discovery mechanism prevents this.

### Access control

Port 0 only reduces port collisions; **it is not a security mechanism through hiding the port number**. A wildcard-bound listener can widen the attack surface. Clients must still satisfy authentication, authorization, and encryption requirements as needed; firewalls and network policies must permit the real path. If an internal endpoint is unintentionally advertised externally, that is a configuration bug even if binding succeeded.

## 9. Lifecycle, Concurrent Startup, and Subtle Pitfalls

### Do not advertise before binding

Suppose two servers request port 0 at the same time. The OS can assign two different ports to avoid a listener conflict. However, if a program writes **port = 0** to a registry before binding, both records are useless. The correct flow is **bind → verify actual port → complete readiness → register**.

### Do not keep stale records after closing

After **close()**, **ServerSocket.getLocalPort()** may still report the previous port, and **isBound()** may still return true. These getters do not prove the endpoint is still being served. On shutdown/restart, you must **unregister/expire** the record; clients that cached the old endpoint should retry and refresh discovery according to the protocol.

### Do not treat a bound listener as request-ready

The OS can complete TCP handshakes while connections wait in the backlog; the application thread may not have called **accept()** yet, initialized dependencies, or become ready to process bytes. Readiness should mean the server can serve requests according to its contract, verified by an appropriate health check, not merely **listener.isBound()**.

### Do not use the assigned port as a persistent identity

Port 0 may return **52741** on one run and **54632** on the next. Service identity should be a **service name/instance ID**, while the endpoint is updatable runtime state. Nor should you save a random port into deployment config and assume it will still be available on the next run.

### Do not ignore bind errors

**BindException: Address already in use** can occur when binding a fixed port or under specific configurations/port reservations. **BindException: Cannot assign requested address** usually indicates the IP is unavailable on the host/namespace, though the exact message depends on the OS. If binding fails, **do not advertise an endpoint**. Catch the exception with bind configuration details and cause; do not silently fall back to wildcard or another interface unless explicitly required.

### Exception caveats with port 0

The OS can still fail to assign a port if the ephemeral port range is exhausted, restricted by policy, or out of resources. Port 0 reduces collisions but does not guarantee bind will always succeed. Every listener still consumes OS resources and must be closed properly in its lifecycle.

## 10. Diagnosing Why a Client Cannot Connect

| Symptom | What to check | Resolution |
| --- | --- | --- |
| **getLocalPort() == -1** | ServerSocket is not bound yet | Call bind first; check exceptions and state |
| Registry stores **port 0** | Advertised before bind or saved initial config | Read the port from **getLocalPort()** after bind |
| Client on another machine calls **127.0.0.1** | Loopback means "the client's own machine" | Choose an address reachable from the client; bind the right interface |
| Client calls **0.0.0.0:port** | Wildcard is for binding | Advertise a routable IP/hostname |
| Running in a container, host cannot reach it | Wrong port mapping or container bound only loopback | Check internal listener port, host published port, and network |
| Client can only reach IPv4, server bound only IPv6 | Incompatible address family/dual-stack setup | Verify bind family, DNS A/AAAA records, and routes |
| Client uses old port after restart | Dynamic port changed | Re-register, expire caches, or use a stable route |
| TCP connect succeeds but requests time out | Listener/accept loop/handler not ready | Check readiness, backlog, thread pool, protocol, and timeouts |
| Server has a port but gets **Connection refused** | Listener gone, wrong IP:port, or rejected | Check PID/service, interface, advertised endpoint, and policies |
| Port occasionally "taken" despite probing free | Race between probe and bind | Keep the port-0-bound listener; do not close and re-bind |

Use **netstat -ano** on Windows, or **ss -ltnp** on Linux (with appropriate permissions), to inspect actual local listeners. Compare with the port reported by **ServerSocket.getLocalPort()** after bind, the interface, network namespace, and advertised address. In containers, inspect both the **internal** listener and the **external** port mapping.

When debugging, log fields that distinguish these values clearly:

~~~text
service=catalog-tcp
bindHost=127.0.0.1
bindRequestedPort=0
assignedListenPort=52741
advertisedHost=127.0.0.1
advertisedPort=52741
ready=true
~~~

This is an **illustrative log record**; if the server uses port 0, a real run may be assigned a different number. Keeping **bindRequestedPort**, **assignedListenPort**, and **advertisedPort** as distinct fields helps spot issues with proxies/NAT or when an operator confuses the bind address with the reachable address.

## 11. Design Checklist and Self-Check Exercises

**Before putting a listener into use:**

1. Choose the **bind IP** based on need: loopback for local tests, a specific interface, or a controlled wildcard if remote access is required.
2. If requesting port 0, call **bind(..., 0)** once and keep the open socket; never use port 0 as the client's destination port.
3. Read **getLocalPort()** or **getLocalSocketAddress()** **after bind** and verify the port is valid.
4. Choose **advertised host/port** for the client's network; account for NAT/proxy/container, IPv4/IPv6, and DNS names.
5. Ensure the accept loop and protocol handling are ready before advertising READY status and the endpoint through a client-readable channel.
6. On stop/restart, revoke or expire the registration, close the socket, and update with the new port if applicable.
7. Use an actual connection and protocol response to verify the service works; do not rely on **isBound()** or **getLocalPort()** as the sole health check.

**Exercises:**

1. Why is **new ServerSocket(0)** less prone to conflicts than **new ServerSocket(8080)** when multiple tests run in parallel? Is the OS-chosen port guaranteed to stay the same after a process restart?
2. A server binds **0.0.0.0:0** and is assigned **51423**. Why shouldn't a client on another machine connect to **0.0.0.0:51423**? When does a client need a public address instead of an internal IP?
3. Why does the "bind 0 to find a port → close → re-bind that port" pattern still have a race condition? How do you retain ownership of the port?
4. A service runs inside a container on port **51423**, but is published externally on **443** via a reverse proxy. Which endpoint should be advertised to public clients, and which to internal peers?
5. Does **isBound() == true** after close prove the listener is still active? How should a registry handle shutdown and restart?
6. For a Java test, modify the example to run three listeners concurrently on loopback:0. Each listener must return a different port when all bind successfully; each client must connect to the exact port advertised by its respective listener.
7. When testing with IPv6 loopback, why should you use **InetAddress.getLoopbackAddress()** and construct an **InetSocketAddress** rather than manually concatenating an IPv6 string with **:**?

**Key Takeaways:** **Port 0 is used at bind time**, the OS assigns the port, and only **getLocalPort()/getLocalSocketAddress() after bind** reveals the actual endpoint. The **bind address** determines where the listener accepts connections; the **advertised address** must reflect the path clients use. A sound solution keeps the listener open, advertises the real port after readiness, and cleans up registration when the server stops.

**API References:** [ServerSocket (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html), [InetSocketAddress](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetSocketAddress.html), [Socket](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html), [ServerSocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html).
