# Limitations of `getLocalHost()` and `isReachable()` When Assessing Connectivity

## Learning Objectives

In Java, the two methods `java.net.InetAddress.getLocalHost()` and `InetAddress.isReachable(...)` are often used as quick answers to very different questions: "What IP is the machine using?", "Does the machine have network access?", "Is the server alive?", or "Can my application call the API?". **Neither method by itself confirms that a service at a specific host and port is usable.**

After this lesson, you will understand the exact information each API returns; why the results can be misleading on multi-NIC machines, containers, VPNs, or firewall-blocked systems; how to check DNS, TCP, TLS, and HTTP at the right layer; and how to write Java 17+ probes with timeouts and interpretable results.

## 1. Distinguishing the Questions Before Choosing an API

| Question to answer | Appropriate tool | What has **not** been proven |
|---|---|---|
| What is the system's current hostname and what IP does that name resolve to? | `InetAddress.getLocalHost()` | That the IP is a public IP, an outbound IP, or an IP reachable by other machines |
| Which IP addresses are bound to the network interfaces? | `NetworkInterface.getNetworkInterfaces()` | Which address will be selected as the source when connecting to a specific destination |
| Which IPs does the name `api.example.com` resolve to? | `InetAddress.getAllByName("api.example.com")` | That any of those IPs actually accept connections |
| Does an IP address respond to the JDK's reachability probe? | `address.isReachable(timeout)` | That service port `443`/`8080` is open, TLS is valid, or HTTP works |
| Can the client complete a TCP connection to host:port? | `Socket.connect(endpoint, timeout)` | That the server understands HTTP, TLS handshake succeeds, or business logic is healthy |
| Does the HTTP(S) endpoint return the expected response? | `HttpClient.send(...)` + status/body check | That all dependencies or the entire system are always healthy |

Important principle: **do not use a measurement at a lower layer to automatically conclude that a higher layer works**. Successful DNS does not prove TCP; successful TCP does not prove TLS/HTTP; an HTTP response does not prove the data or business logic is correct.

```text
Hostname / machine configuration
         │
         ▼
Name service (DNS, hosts file, cache...) ─► IP address
         │
         ▼
Route, interface, firewall, NAT ──────────► path to IP
         │
         ▼
TCP host:port ────────────────────────────► service connection
         │
         ▼
TLS (if using HTTPS) ─────────────────────► secure session
         │
         ▼
HTTP request + status + payload ──────────► API behavior
```

`getLocalHost()` relates to the **current machine's name/address**, whereas `isReachable()` is a probe **to an IP address**. They sit at two different positions in the diagram and do not substitute for checking the service.

## 2. What Does `InetAddress.getLocalHost()` Actually Do?

According to the Java 17 API contract, the static method:

```java
InetAddress local = InetAddress.getLocalHost();
String ipText = local.getHostAddress();
```

retrieves the **hostname provided by the system for the current machine**, and then uses the environment's name resolution mechanism to look up an `InetAddress`. This mechanism can be influenced by the `hosts` file, DNS, name service configuration, or caching; the API may cache the result for a short period.

This is a **name resolution operation**, not an "Internet connectivity check" command, not a "what is my public IP" query, and not the selection of an interface suited for a remote server.

### 2.1. Conclusions You Can and Cannot Draw

Suppose `getLocalHost().getHostAddress()` returns `192.168.1.12`. We only know that the current machine's hostname resolved to that address in the running environment. From this single result, you cannot conclude that:

- `192.168.1.12` is the address used when Java opens a socket to `203.0.113.10`. The operating system selects the route/source address based on routing, binding, and network policy.
- Other machines on the Internet can directly reach `192.168.1.12`. This is a private address format; firewall, NAT, port mapping, and routing must also be in place.
- That address is bound to an active interface or to the port the application is listening on.
- `getLocalHost()` always returns an IPv4 address. The result can be IPv4 or IPv6, depending on the environment.
- The result stays stable forever. DHCP, VPNs, containers, DNS/hosts, and caches can change over time.

### 2.2. Why Can the Result Easily Mislead?

**Multi-NIC machines.** Laptops have Wi-Fi, Ethernet, VPN, loopback, or virtual interfaces. A hostname usually resolves to only one address, while different destinations may use different routes and source addresses.

**Containers, VMs, Kubernetes.** Code running inside a container's network namespace may see the container/pod's internal IP, not the physical host's IP or the service's public address. When a pod is recreated, its IP can change; external clients typically access it through a Service, ingress, or proxy rather than the address observed by `getLocalHost()`.

**Inconsistent hosts file or DNS.** A hostname can be mapped to loopback, a stale IP, or an IP no longer assigned to the machine. When the hostname cannot be resolved, `getLocalHost()` can throw `UnknownHostException` **even when TCP to another IP still works**. Conversely, `getLocalHost()` can succeed even when the network adapter is disconnected, because the name information is preconfigured or cached.

**Legacy Java 17 security mechanism.** If a `SecurityManager` is present and the permission check does not allow local name resolution, the Java 17 specification permits returning the loopback address. That is a historical API behavior, not proof that the machine only has loopback.

### 2.3. Other APIs for Other Purposes

- `InetAddress.getLoopbackAddress()`: retrieves the loopback address (`127.0.0.1` or `::1`), suitable for testing servers/clients **on the same machine**. It does not substitute for an externally reachable address.
- `NetworkInterface.getNetworkInterfaces()`: lists the interfaces and addresses visible to the Java environment. You need to distinguish virtual interfaces, loopback, up/down state, IPv4, and IPv6; an interface being up **does not guarantee** working Internet access.
- `socket.getLocalAddress()` after `Socket.connect(...)`: reports the local IP that the socket **selected for a specific TCP connection**. This is usually better evidence than `getLocalHost()` if you want to know the **outbound path to a specific remote endpoint**, though it is still an observation inside the machine/container and does not by itself reveal a public IP behind NAT.
- `socket.getLocalSocketAddress()`: provides both the local address **and the local port** for that connection.
- A "what is my IP" web service can return the IP that the service **sees** (which may be a proxy/NAT), but does not prove inbound connectivity; it also depends on that external service itself.

**Avoid a common design mistake:** binding a server using `getLocalHost()` just because you think it is the "primary" address. If you only want to allow local connections, bind loopback explicitly. If you need to listen on the machine's appropriate addresses, use a wildcard bind (`0.0.0.0` or `::` depending on family/configuration) and manage the firewall. **A wildcard bind address is not an address external clients should use as a destination.**

## 3. What Does `InetAddress.isReachable()` Actually Check?

Two main overloads:

```java
boolean reachable = address.isReachable(1500);
boolean reachableViaInterface =
        address.isReachable(networkInterface, 0, 1500);
```

The `timeout` parameter is in **milliseconds**; `ttl` is the hop limit or `0` to use the default, and `networkInterface` specifies the test interface or `null` to allow the default choice. Negative values for `timeout` (or `ttl`) cause `IllegalArgumentException`. The probe may throw `IOException` on network errors, rather than necessarily just returning `false`.

**The most important point:** the JDK describes this as a *best-effort* probe. A typical implementation uses **ICMP Echo Request** if sufficient privileges are available; otherwise, it may try **TCP Echo on port 7**, depending on the OS and JDK. Therefore `isReachable()` has no API parameter to test an application's **port 443, 5432, or 8080**.

### 3.1. `false` Does Not Mean "Service Unreachable"

`isReachable()` can return `false` because:

- A device or firewall blocks ICMP, or the TCP Echo port 7 service is not enabled.
- Raw ICMP/socket permissions, OS policies, namespaces/containers, or network configurations disallow the probe.
- The ICMP path is filtered/rate-limited differently from TCP traffic to the application port.
- The timeout is too short for the latency or a slow-responding device.
- Reply packets take a different path, are blocked, or are not received under test conditions.

In these cases, TCP to `host:443` or `host:8080` **can still succeed**. Therefore, never write:

```java
// Flawed reasoning: ICMP/Echo failure does not rule out TCP :443.
if (!remoteIp.isReachable(1000)) {
    throw new IllegalStateException("HTTPS service is offline");
}
```

### 3.2. `true` Does Not Mean "API Is Healthy"

Even when `isReachable()` returns `true`:

- The target TCP port may be **closed** or the application may not have started yet.
- The TCP server may accept the connection but fail to read requests or respond.
- TLS may fail due to certificate, hostname, protocol version, or authentication requirements.
- HTTP may return `401`, `403`, `404`, `429`, `500`, or a response with an invalid schema.
- A DB, message broker, or business upstream may be failing even though the host responds to the network probe.

`isReachable()` cannot verify HTTP method/path, TLS, auth, or business data. `true` is only **a signal for the type of probe the JDK performed** at that moment.

### 3.3. Remaining Limitations

- `isReachable()` is not identical to the `ping` command on every OS. Implementation, privileges, parameters, and results can differ.
- Switching to the `isReachable(netif, ttl, timeout)` overload helps direct the test interface/hops; it **does not add a port parameter** and does not turn it into an application health check.
- `getByName("host")` or `getAllByName("host")` only resolves the name; it does not guarantee ICMP responses or a TCP service.
- An `IOException` from the probe should be reported separately if diagnostics are needed; do not lump all errors into "server is dead".
- The result is a **point-in-time snapshot**. Running a test before sending a request still carries the risk of the network/service changing in between (time-of-check vs. time-of-use).

## 4. Analyzing Real-World Scenarios

| Observation | Reliable conclusion | What must not be inferred |
|---|---|---|
| `getLocalHost()` throws `UnknownHostException` | The local hostname could not be resolved by the current mechanism | The machine lost Internet access or cannot connect to services by IP |
| `getLocalHost()` returns `127.0.0.1` | The local hostname currently maps to loopback | All endpoints are only locally reachable |
| `getLocalHost()` returns a private IP | The name service currently returns a private IP | The machine has no outbound Internet route or that IP is public |
| `isReachable(ip, 1000) == false` | The JDK probe did not confirm reachability under those conditions | TCP port 443/8080 is definitely closed |
| `isReachable(ip, 1000) == true` | The destination responded to the probe per implementation logic | HTTP/TLS or business transactions will succeed |
| `Socket.connect(host:port)` succeeds | The TCP handshake to that endpoint completed | The server returns valid data or TLS/HTTP succeeds |
| HTTPS returns `200` from `/health` | The request to that endpoint was processed and returned `200` | All dependencies are healthy, unless the endpoint has a contract to check them |

Two systems can both yield `isReachable() == false` yet be completely different: one blocks ICMP and still serves HTTPS fine; the other has lost its route completely. You must **check the actual application port and protocol** to tell them apart.

## 5. Java 17+: Inspecting Local Addresses Without Inferring Connectivity

Create `HostIdentityInspect.java`:

```java
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.net.UnknownHostException;
import java.util.Enumeration;

public class HostIdentityInspect {
    public static void main(String[] args) throws SocketException {
        try {
            InetAddress local = InetAddress.getLocalHost();
            System.out.println("getLocalHost IP: " + local.getHostAddress());
        } catch (UnknownHostException e) {
            System.out.println("getLocalHost: hostname not resolved");
        }

        System.out.println("loopback IP: "
                + InetAddress.getLoopbackAddress().getHostAddress());

        Enumeration<NetworkInterface> interfaces =
                NetworkInterface.getNetworkInterfaces();
        if (interfaces == null) {
            return;
        }

        while (interfaces.hasMoreElements()) {
            NetworkInterface networkInterface = interfaces.nextElement();
            if (!networkInterface.isUp()) {
                continue;
            }

            Enumeration<InetAddress> addresses =
                    networkInterface.getInetAddresses();
            while (addresses.hasMoreElements()) {
                InetAddress ip = addresses.nextElement();
                System.out.println(networkInterface.getName() + " -> "
                        + ip.getHostAddress());
            }
        }
    }
}
```

Compile and run from a terminal with JDK 17+:

```bash
javac -encoding UTF-8 HostIdentityInspect.java
java HostIdentityInspect
```

**Output varies by environment.** For example, the lines might look like this (illustrative only, not a required result):

```text
getLocalHost IP: 192.168.1.12
loopback IP: 127.0.0.1
eth0 -> 192.168.1.12
lo -> 127.0.0.1
```

On another machine, `getLocalHost` may fail, loopback may be IPv6 `::1`, interfaces may have different names, and there may be more IPs. The list above provides an **inventory of addresses** visible to the environment; it does not confirm outbound connectivity. If you want to know the source IP of a real connection, inspect `Socket.getLocalAddress()` **after connecting to the actual destination**.

## 6. Java 17+: Placing `isReachable()` Next to a Real TCP Connection

The following example uses loopback to avoid depending on DNS and the Internet. It prints the reachability result per the JDK's mechanism, then creates a TCP listener on an **ephemeral port** and connects to that listener. There is no `if (isReachable)` condition deciding whether to attempt TCP.

Create `ReachabilityLayersDemo.java`:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;

public class ReachabilityLayersDemo {
    public static void main(String[] args) throws IOException {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try {
            System.out.println("isReachable(loopback): "
                    + loopback.isReachable(1000));
        } catch (IOException e) {
            System.out.println("isReachable(loopback): error "
                    + e.getClass().getSimpleName());
        }

        try (ServerSocket server = new ServerSocket()) {
            server.bind(new InetSocketAddress(loopback, 0));
            server.setSoTimeout(2000);
            int port = server.getLocalPort();

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(loopback, port), 2000);

                try (Socket accepted = server.accept()) {
                    System.out.println("TCP connect to listener: OK");
                    System.out.println("Client local IP: "
                            + client.getLocalAddress().getHostAddress());
                    System.out.println("Listener port: " + port);
                }
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 ReachabilityLayersDemo.java
java ReachabilityLayersDemo
```

On a machine that allows TCP loopback, the output has a structure like the following; the boolean, IP format, and port are not fixed:

```text
isReachable(loopback): true
TCP connect to listener: OK
Client local IP: 127.0.0.1
Listener port: 53241
```

The first line can also print `false` or report an `IOException`; the `Client local IP` line may show IPv6; port 53241 is only an example chosen by the OS. If the environment forbids opening a loopback socket, the TCP section can throw `IOException`.

**What the experiment demonstrates:** you are measuring two separate things. `isReachable` has no knowledge of the port the server just bound; meanwhile `Socket.connect` tests the exact `(loopback, port)` endpoint the Java server is listening on. **Even a successful TCP connect only confirms the handshake**, because this program does not send any application message.

Do not turn this check into an assertion that every machine will have `isReachable(loopback) == true`; that property is not standardized as a fixed outcome in restricted environments.

## 7. Java 17+: Checking the Actual Host and TCP Port Instead of Relying on `isReachable()`

For real targets, you usually have a **specific hostname and port** such as `db.internal:5432` or `api.example.com:443`. The code below resolves all addresses returned for the hostname, logs the `isReachable` result for comparison, and **still tries TCP** against each address. The `isReachable` result is not used as a condition to skip the TCP test.

Create `TcpPortProbe.java`:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.UnknownHostException;

public class TcpPortProbe {
    public static void main(String[] args) {
        if (args.length != 2) {
            System.out.println("Usage: java TcpPortProbe <host> <port>");
            return;
        }

        String host = args[0];
        int port;
        try {
            port = Integer.parseInt(args[1]);
            if (port < 1 || port > 65535) {
                throw new NumberFormatException("port out of range");
            }
        } catch (NumberFormatException e) {
            System.out.println("Port must be 1..65535");
            return;
        }

        InetAddress[] addresses;
        try {
            addresses = InetAddress.getAllByName(host);
        } catch (UnknownHostException e) {
            System.out.println("Name resolution failed: " + host);
            return;
        }

        for (InetAddress address : addresses) {
            String ip = address.getHostAddress();

            try {
                System.out.println(ip + " isReachable: "
                        + address.isReachable(800));
            } catch (IOException e) {
                System.out.println(ip + " isReachable error: "
                        + e.getClass().getSimpleName());
            }

            try (Socket socket = new Socket()) {
                socket.connect(new InetSocketAddress(address, port), 2000);
                System.out.println(ip + ":" + port + " TCP CONNECT OK");
                System.out.println("Actual local endpoint: "
                        + socket.getLocalSocketAddress());
                return;
            } catch (IOException e) {
                System.out.println(ip + ":" + port + " TCP failed: "
                        + e.getClass().getSimpleName());
            }
        }

        System.out.println("No resolved address accepted TCP connection.");
    }
}
```

```bash
javac -encoding UTF-8 TcpPortProbe.java
java TcpPortProbe localhost 8080
```

**Output depends on the listener, DNS/hosts, IPv4/IPv6 addresses, firewall, and OS**. For example, when a loopback address has a TCP service on port 8080, you might see:

```text
127.0.0.1 isReachable: true
127.0.0.1:8080 TCP CONNECT OK
Actual local endpoint: /127.0.0.1:54213
```

This is illustrative output, not a guarantee that `localhost` only has IPv4 or that port `8080` is open. When no listener is present, the program may report `ConnectException`, `SocketTimeoutException`, or another I/O exception. If the hostname returns both IPv6 and IPv4, the program will try them in the order returned by the environment until one succeeds or all addresses are exhausted.

**Meaning of each step:**

1. `getAllByName(host)` checks resolution of the **target name** and returns the `InetAddress` entries. It does not check a port.
2. `isReachable(800)` adds a diagnostic signal, but does not prejudge TCP connectivity.
3. `new InetSocketAddress(address, port)` specifies both the target IP **and TCP port**.
4. `socket.connect(..., 2000)` attempts the TCP handshake with a timeout for the connect phase; it does **not** bound all subsequent application steps.
5. `socket.getLocalSocketAddress()` observes the local IP and ephemeral port **of the successful connection itself**. It does not confirm a public IP outside NAT.
6. `TCP CONNECT OK` does not mean TLS handshake, authentication, HTTP requests, or DB queries succeeded.

This program is a **TCP connectivity diagnostic**, not a tool for testing UDP or application health. It may not fully reflect the address selection, retry, DNS cache, proxy, or connection pool algorithms of a real application library. When troubleshooting an error that only occurs in the client itself, configure the probe as close to the client as possible.

## 8. Checking at the Right Application Layer: HTTP(S) Example

If the actual question is "Does `https://api.example.com/health` return a valid result?", send a **real HTTP request** using `HttpClient` (included in JDK 17), instead of using `getLocalHost` or `isReachable`.

Create `HttpHealthProbe.java`:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class HttpHealthProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println("Usage: java HttpHealthProbe <http(s)-url>");
            return;
        }

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        HttpRequest request = HttpRequest.newBuilder(URI.create(args[0]))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        System.out.println("HTTP status: " + response.statusCode());
    }
}
```

```bash
javac -encoding UTF-8 HttpHealthProbe.java
java HttpHealthProbe https://api.example.com/health
```

The URL above is an **illustrative address**, not a guarantee that a live endpoint exists to test. With a valid URL where the server returns `200`, the output is:

```text
HTTP status: 200
```

In other cases, the result is the actual status or an exception (DNS, TCP, timeout, TLS, proxy...). `connectTimeout` applies when a new connection needs to be opened; `HttpRequest.timeout` sets the time limit for the request. For HTTPS, the standard HTTP client also validates the TLS connection/certificate according to its default configuration. `200` only proves **the endpoint returned HTTP 200 on that call**; "healthy" status must be based on the endpoint's specific contract, checking the required body and the dependencies that endpoint is designed to verify.

If using automated checks, clearly define the **success criteria**: for example, expected status, JSON schema, business error codes, maximum latency, and appropriate credentials. `401` proves an HTTP service responded but does not prove the request is valid; `500` shows the application received the request at one layer but server-side processing failed.

## 9. Debugging Workflow When "The Server Cannot Be Reached"

Do not start by calling `getLocalHost()` and treating that as a conclusion. Identify the **actual target** (hostname, port, protocol, path) and **where the probe runs** (physical machine, container, pod, VPN, office network, or external Internet host).

| Step | Check | Distinguishing question |
|---|---|---|
| 1. Input/config | URL, scheme, hostname, port, proxy, service discovery | Is the client calling the right environment and the right endpoint? |
| 2. Name resolution | `getAllByName(remoteHost)`; compare DNS records/hosts | Does the target name resolve to the expected IP in the **client** environment? |
| 3. IP/route | Route, VPN, firewall, namespace, NAT; ICMP when appropriate | Are there signs of a routing failure? Is ICMP filtered separately? |
| 4. Transport | TCP `Socket.connect(remoteIP:port, timeout)`, or corresponding UDP client | Does the **exact port/protocol** accept traffic? |
| 5. Security/protocol | TLS handshake, SNI, certificate, ALPN, DB/HTTP protocol | Do both sides speak the right protocol and authenticate properly? |
| 6. Application | HTTP method/path/status/body or the service's official ping command | Does the service handle the request according to contract? |
| 7. Dependencies | DB, queue, upstream API, auth, quota, response time | Is each critical dependency working? |

Distinguishing common symptoms:

- **`UnknownHostException`** from `getLocalHost()`: the **local** hostname could not be resolved; says nothing directly about the server hostname. `UnknownHostException` from `getAllByName(remoteHost)` relates to the **target name** instead.
- **`ConnectException: Connection refused`** during a TCP test: usually indicates no matching listener or the network actively refused the connection; **not** an HTTP status result.
- **TCP connect timeout**: can be caused by dropped/filtered packets, an unresponsive route/target, or other network conditions; not enough to conclude the server does not exist.
- **TCP connect succeeds but reading response times out**: the connection reached the TCP layer, but the application/protocol or subsequent processing/reading has an issue. `Socket.setSoTimeout(...)` governs the timeout for `read` operations on a traditional socket; connect timeout alone does not replace it.
- **`isReachable() == false` while `Socket.connect()` succeeds**: completely possible. The ICMP/TCP Echo probe is blocked while the service port is open.
- **HTTP status 5xx**: the HTTP endpoint responded, but server-side processing failed; check application/downstream logs instead of only using `ping`.

### Remember the Probe's Vantage Point

A `Socket.connect` result from a laptop **differs** from a result inside a production container if they sit behind different routes, firewalls, or proxies. `getLocalHost` inside a container also describes the container environment, not the view from the Internet. For an inbound service, a connection to `localhost` on the server only proves a **local listener**; it does not guarantee external clients can reach the service through a load balancer, firewall, and public DNS.

For application servers, distinguish at least three checks:

- **Liveness**: whether the process is still running/minimally responsive.
- **Readiness**: whether the instance is ready to accept new traffic.
- **End-to-end health**: whether the business flow actually runs through critical dependencies.

These are different operational contracts. Do not use `isReachable()` as a single criterion to replace all three checks.

## 10. Common Design Mistakes and How to Fix Them

### Mistake 1: "The server's address is `getLocalHost()`"

```java
// Error-prone on multi-NIC/container machines: this is only the resolved local hostname.
String advertisedHost = InetAddress.getLocalHost().getHostAddress();
```

**Fix:** the address clients must call should come from service discovery configuration, DNS, ingress/load balancer, or managed endpoint configuration. If you must measure the local IP of a specific outbound connection, read `Socket.getLocalAddress()` after connecting to the target.

### Mistake 2: "`isReachable()` is a TCP port health check"

```java
// Wrong: this boolean does not check TCP port 443.
boolean httpsUp = InetAddress.getByName("api.example.com")
        .isReachable(1000);
```

**Fix:** test `Socket.connect(..., 443)` if you only need to know whether a TCP handshake succeeds. If you need HTTPS to actually work, send an HTTPS request with `HttpClient` and evaluate the status/response.

### Mistake 3: "`false` means the network is down; `true` means the API is good"

Both inferences go beyond the evidence. A firewall can block ICMP; a server can reply to ICMP while the application port is closed. Logs must clearly state **"probe received no response"**, **"TCP connect failed"**, or **"HTTP health check failed"**, avoiding unsubstantiated `NetworkDown` labels.

### Mistake 4: "One successful check guarantees the next request"

Networks, routes, DNS, processes, and policies can change right after a probe. Do not build a mandatory `isReachable()` step before every HTTP request: it can cause false rejections, add latency, and does not guarantee the subsequent request. Client design needs **appropriate timeouts, proper error handling, controlled retries when safe, and error metrics over time**.

### Mistake 5: "No timeout means it will finish quickly"

Never let probes run indefinitely. For TCP, `connect(endpoint, timeoutMillis)` bounds the connect phase per the API, but name resolution, TLS, and reading the response need their own timeout policies. For HTTP, use both `HttpClient.connectTimeout(...)` where appropriate and `HttpRequest.timeout(...)`. For `isReachable`, the timeout applies only to the best-effort probe, not a check of the entire service stack.

## 11. Self-Check

**Question 1.** A Java application in Docker prints `getLocalHost() = 172.18.0.4`. Should external Internet users call this IP?  
**Answer:** Cannot be inferred. This may be a private IP within a network namespace. Public targets are usually exposed via hostname/ingress/load balancer/NAT and network policy.

**Question 2.** `remoteIp.isReachable(1000)` returns `false`, yet `Socket.connect(remoteIp:443)` succeeds. Is this a contradiction?  
**Answer:** No. The JDK reachability probe may use ICMP or TCP Echo port 7, which is different from TCP port 443. When ICMP is blocked, HTTPS can still work.

**Question 3.** `isReachable(1000)` returns `true`. Is HTTP POST `/payments` guaranteed to work?  
**Answer:** No. TCP/TLS, HTTP protocol, authentication, request validation, and business logic are required. Only an actual request or an appropriate health contract checks the relevant layers.

**Question 4.** `getLocalHost()` throws `UnknownHostException`. Should you report "database server down"?  
**Answer:** No. That is a local hostname resolution issue. Check the DB target name and test connectivity to the DB using its own host:port.

**Question 5.** A client wants to know which local IP was selected when calling `198.51.100.10:8443`; which method should it use?  
**Answer:** After a successful TCP connection, inspect `socket.getLocalAddress()` or `socket.getLocalSocketAddress()` on **that exact socket**. That result is not necessarily the public IP behind NAT.

**Question 6.** Why can testing `localhost:8080` succeed while users on another network still cannot reach the application?  
**Answer:** The listener may only be bound to loopback; or an external firewall, NAT, ingress, DNS, VPN, route, or TLS/proxy is blocking access. Local TCP success does not prove inbound reachability from elsewhere.

## 12. Practical Summary

- `getLocalHost()` = **current machine's hostname → resolved to an address**. Do not use it as proof of public IP, egress IP, or service reachability.
- `isReachable()` = **best-effort probe to an address**, which may rely on ICMP or TCP Echo port 7 and is affected by privileges and firewalls. `true`/`false` says nothing certain about an application port.
- `getAllByName(remoteHost)` = resolves the **target name**; `Socket.connect(remoteIP:port, timeout)` = checks TCP on the **exact port**; `HttpClient` = tests HTTP(S) at the application layer.
- Use **a check at the same layer as the requirement**, run from **the exact place the client operates**, with appropriate timeouts and error classification. Every check is a point-in-time observation, not a guarantee for the next call.

### Java 17 Reference Documentation

- [`InetAddress` — `getLocalHost`, `isReachable`, `getLoopbackAddress`, `getAllByName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html)
- [`NetworkInterface` — network interfaces and addresses](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html)
- [`Socket` — `connect` and local/remote socket address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [`HttpClient` — HTTP request/response and timeouts](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
