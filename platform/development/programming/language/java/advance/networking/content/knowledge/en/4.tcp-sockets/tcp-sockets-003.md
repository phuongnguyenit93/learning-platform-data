# Connecting to a Multi-Address Hostname and Distinguishing DNS Errors from Connection Errors

## 1. The problem: a hostname does not mean a single IP address

In Java, developers often start with a name and port like `api.example.org:443`. To establish a TCP connection, the operating system needs the **destination IP address** and **TCP port**. However, a single hostname can resolve to **multiple** IPv4 and/or IPv6 addresses. Some addresses may be reachable, while others may be blocked, have no listener, or traverse an inactive network path.

There are two distinct logical phases:

1. **Name resolution:** translating a hostname into candidate IP addresses; usually via the machine's name service mechanism, which may use DNS, the hosts file, or a cache.
2. **TCP connection:** for each IP and port, attempting to establish a TCP connection to a specific endpoint.

Key distinction: **successful name resolution does not prove the TCP port is open**, and **one IP failing to connect does not prove all IPs for that name fail**. An error in step 1 is not the same kind of error as in step 2.

Lesson objectives:

- Explain why a hostname can yield multiple IPv4/IPv6 addresses and why the address order can change.
- Know when to use `InetAddress.getAllByName` instead of only using `getByName`.
- Distinguish `UnknownHostException` during resolution from `ConnectException`, `SocketTimeoutException`, and other errors during `Socket.connect`.
- Write and run a Java 17 example that tries multiple addresses, closes failed sockets, preserves causes, and stops at the first address that connects successfully.
- Recognize the limitations of sequential attempts, timeouts, TLS security, and retrying after data has already been sent.

## 2. Hostnames with multiple addresses: A, AAAA, and resolvers

DNS has **A records** for IPv4 addresses and **AAAA records** for IPv6 addresses. A hostname can receive multiple records of the same type or both types. Illustrative example:

| Hostname | Candidate address | Family |
|---|---|---|
| `api.example.org` | `192.0.2.10` | IPv4 |
| `api.example.org` | `192.0.2.11` | IPv4 |
| `api.example.org` | `2001:db8::10` | IPv6 |

The IPs above belong to ranges reserved for documentation (TEST-NET and the IPv6 documentation prefix); they must not be used as addresses of a running service.

Reasons for having multiple addresses include: multiple backend hosts, multi-region deployments, DNS-based load balancing, redundancy, and simultaneous IPv4/IPv6 support. However, the returned results depend on the resolver and network environment; a program **should not assume** that DNS always returns the three IPs above, that all IPs from the zone file appear, or that IPv4/IPv6 always follow a fixed order.

In practice, "name resolution" is broader than "sending a DNS query": Java may receive results from the hosts file, JVM cache, OS cache, or a configured name service. Consecutive calls sometimes do not reflect DNS changes immediately due to caching/TTL. On the other hand, an IP literal such as `127.0.0.1` or `::1` does not require DNS to be represented as an `InetAddress`.

**A hostname contains no information about whether port 443 has a listener.** DNS A/AAAA resolves addresses; port status and reachability are only checked at the TCP step (or via another specialized check).

### General flowchart

```text
hostname + port
      |
      v
Name resolution: hosts/cache/DNS
      |
      +-- failed --> name resolution error (TCP not attempted yet)
      |
      +-- succeeded --> [IPv6 A, IPv4 B, IPv4 C, ...]
                              |
                              v
                       try IP A : port
                              |
                   failed?    +-- no --> TCP connected
                      |
                      v
                       try IP B : port
                              |
                   failed?    +-- no --> TCP connected
                      |
                      v
                       try IP C : port
                              |
                all failed --> combined connection error
```

The diagram describes **sequential fallback** for learning purposes; production clients may sort and perform overlapping attempts to reduce latency.

## 3. Java APIs to distinguish

### 3.1. `InetAddress.getAllByName`: retrieving candidates

```java
// Illustrative snippet inside a method that can throw UnknownHostException.
InetAddress[] addresses = InetAddress.getAllByName("api.example.org");
for (InetAddress address : addresses) {
    System.out.println(address.getHostAddress());
}
```

`getAllByName` returns an array of candidate `InetAddress` objects for the hostname according to the active name service; if it cannot resolve to a usable address, it throws `UnknownHostException`. It does not check the port, perform a TCP handshake, or send HTTP data. `InetAddress.getByName(host)` only returns **one** address and is therefore unsuitable if the goal is to control the process of trying **all candidates** yourself.

Each element may be an `Inet4Address` or `Inet6Address`. `getHostAddress()` gives the numeric address. The list and order depend on the operating system and the environment's address policy, not a contract that "IPv6 is preferred first" or "the first IP is always fastest".

### 3.2. `Socket.connect`: trying a known IP:port

```java
// address is a resolved InetAddress; port and timeoutMillis are valid.
try (Socket socket = new Socket()) {
    socket.connect(
            new InetSocketAddress(address, port), timeoutMillis);
    // The TCP connection is only considered established if connect returns successfully.
}
```

Details that are easy to confuse:

- `new Socket()` creates an unconnected socket. Each attempt should use a new socket; after a failed connect, close the old socket.
- `new InetSocketAddress(address, port)` takes a **resolved InetAddress**, so you can determine that any exception occurred specifically during the TCP connect phase.
- `connect(endpoint, timeoutMillis)` sets the **timeout for that connection attempt**. It does not set a DNS timeout, nor does it guarantee that the total time to try 5 IPs is less than that same timeout.
- `socket.setSoTimeout(ms)` controls the **blocking read** timeout on the socket; it does not set a timeout for DNS or connect.
- A basic `Socket` is TCP. Communicating over HTTPS requires adding TLS with certificate and hostname verification; do not treat "TCP connect OK" as "HTTPS OK".

When using a constructor that accepts a hostname directly, resolution can be hidden inside the creation/connection process. If you need to distinguish DNS errors from TCP errors in logs and diagnostics, proactively separate the two steps.

## 4. Classifying errors by the exact phase

| When it occurs | Common Java symptom | Correct interpretation |
|---|---|---|
| Resolving hostname via `getAllByName` | `UnknownHostException` | No usable address was received from the name resolution mechanism, or resolution encountered an issue |
| `connect` to IP and port | `ConnectException`, often with "Connection refused" | The destination rejected the connection; there may be no listener or a device actively refused it |
| `connect(endpoint, timeout)` | `SocketTimeoutException` | Failed to establish TCP within the configured deadline |
| Routing to the IP | `NoRouteToHostException`, `SocketException` such as "Network is unreachable" | There is an issue with the network path/reachability |
| Reading from a connected socket | `SocketTimeoutException` when using `setSoTimeout` | Waited too long for application data; this is a read timeout, not a DNS timeout |
| HTTPS/TLS handshake | `SSLHandshakeException` or certificate error | TCP may have succeeded, but the TLS handshake/verification failed |
| After the application protocol | HTTP status `401`, `404`, `503` | An HTTP response was received; that is an application-layer status |

**Do not over-infer from an exception.** `UnknownHostException` does not by itself tell you whether DNS returned NXDOMAIN, the resolver temporarily lost connectivity, the hosts file is wrong, or a name is unconfigured. `ConnectException` does not prove the server is completely down; the port may not be listening or a firewall may have returned a rejection. `SocketTimeoutException` from connect does not prove the server is dead; packets may be dropped or the network path may be slow.

**A hostname can both resolve successfully and fail to connect.** For example, `api.example.org` returns three IPs; `192.0.2.10:443` refuses, `2001:db8::10:443` times out, but `192.0.2.11:443` succeeds. Here DNS has already provided the list; the issue lies in individual TCP paths, and the client can continue with the working address.

### Three quick diagnostic examples

1. `getAllByName("unknown.invalid")` throws `UnknownHostException`: this is a **resolution error** in this call; no TCP attempt to a resolved IP has occurred. `.invalid` is a suffix reserved for invalid names in public DNS, though tests can be affected by environment resolver policies.
2. The hostname resolves to `127.0.0.1`, with no service listening on the port: DNS/resolution succeeded, and `connect` typically throws `ConnectException`.
3. `connect` to port 443 succeeds, then HTTPS reports a certificate mismatch: the error is in **TLS and hostname verification**, not DNS/TCP connect.

## 5. Multi-address retry policy

A simple TCP implementation can follow these steps:

1. Accept the hostname and port; determine the per-attempt timeout along with an appropriate overall time limit.
2. Call `InetAddress.getAllByName(host)` to retrieve the addresses. If it fails here, report a name resolution error separately.
3. For each `InetAddress`, create **a new `Socket`** and call `connect(new InetSocketAddress(address, port), timeoutMillis)`.
4. If connect fails, **close that socket**, record the IP and exception, and try the next candidate.
5. If connect succeeds, **stop the loop**, and hand the open socket and responsibility for closing it to the application code.
6. If all connects fail, construct a combined connection error and retain the component errors for diagnostics. Do not call this "DNS failed".

A critical design condition: **only fall back across IPs before a connection has succeeded**. Once an application message has been sent, a timeout while reading the response **does not guarantee the server has not processed the request**. Resending an order creation or money transfer command can execute duplicates if idempotency is missing.

This example uses sequential fallback, which is easy to understand and verify; on a dual-stack network where one family is broken, sequential fallback can be slow because it must wait for a timeout before trying the other family. Optimizations will be discussed after the example.

## 6. Java 17+ example: one IP fails, the other works

The following program is completely **offline**, using loopback addresses and an ephemeral port chosen by the operating system. For consistent results on machines with different hosts files/DNS, the example prepares two `InetAddress` instances in order: IPv6 `::1` then IPv4 `127.0.0.1`. The server intentionally **binds only to `127.0.0.1`**. Therefore, a TCP connect to `::1` cannot reach that listener, while the IPv4 connect will succeed.

This is a **simulated candidate list** to test the fallback algorithm; it does not claim that real DNS for `localhost` always returns both IPs or returns IPv6 first. The same program includes `connectHost`, illustrating how to replace the simulated list with the result of **`getAllByName(host)` for a real hostname**.

Save the file **`MultiAddressConnectDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class MultiAddressConnectDemo {

    // Pattern using a real hostname: resolve first, then try the IPs.
    static Socket connectHost(String host, int port, int timeoutMillis)
            throws IOException {
        InetAddress[] candidates = InetAddress.getAllByName(host);
        return connectCandidates(candidates, port, timeoutMillis);
    }

    // Retry only when TCP connect has not succeeded yet.
    static Socket connectCandidates(
            InetAddress[] addresses, int port, int timeoutMillis)
            throws IOException {

        IOException summary =
                new IOException("All TCP connection attempts failed");

        for (InetAddress address : addresses) {
            Socket candidate = new Socket();
            try {
                candidate.connect(
                        new InetSocketAddress(address, port), timeoutMillis);
                return candidate; // caller is responsible for closing the socket
            } catch (IOException failure) {
                summary.addSuppressed(failure);
                try {
                    candidate.close();
                } catch (IOException closeFailure) {
                    summary.addSuppressed(closeFailure);
                }

                String family = address instanceof Inet6Address
                        ? "IPv6" : "IPv4";
                System.out.println(family + " connect failed");
            }
        }

        throw summary;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newSingleThreadExecutor();

        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {

            Future<String> received = workers.submit(() -> {
                try (Socket peer = server.accept()) {
                    peer.setSoTimeout(2_000);

                    BufferedReader in = new BufferedReader(
                            new InputStreamReader(
                                    peer.getInputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedWriter out = new BufferedWriter(
                            new OutputStreamWriter(
                                    peer.getOutputStream(),
                                    StandardCharsets.UTF_8));

                    String request = in.readLine();
                    out.write("PONG\n");
                    out.flush();
                    return request;
                }
            });

            InetAddress[] demoAddresses = {
                    InetAddress.getByName("::1"),
                    InetAddress.getByName("127.0.0.1")
            };

            try (Socket client = connectCandidates(
                    demoAddresses, server.getLocalPort(), 1_000)) {
                client.setSoTimeout(2_000);

                BufferedReader in = new BufferedReader(
                        new InputStreamReader(
                                client.getInputStream(),
                                StandardCharsets.UTF_8));
                BufferedWriter out = new BufferedWriter(
                        new OutputStreamWriter(
                                client.getOutputStream(),
                                StandardCharsets.UTF_8));

                String family = client.getInetAddress()
                        instanceof Inet6Address ? "IPv6" : "IPv4";
                System.out.println("Connected via " + family);

                out.write("PING\n");
                out.flush();
                System.out.println("Client received: " + in.readLine());
            }

            System.out.println("Server received: "
                    + received.get(3, TimeUnit.SECONDS));
        } finally {
            workers.shutdownNow();
        }
    }
}
```

Compile and run with JDK 17 or newer, in the directory containing the file:

```bash
javac -encoding UTF-8 MultiAddressConnectDemo.java
java MultiAddressConnectDemo
```

Output on a system with normal TCP loopback:

```text
IPv6 connect failed
Connected via IPv4
Client received: PONG
Server received: PING
```

**Execution flow explanation:**

1. `ServerSocket(0, 1, 127.0.0.1)` binds to the IPv4 loopback; port argument `0` asks the operating system to choose a port automatically. `getLocalPort()` returns that port.
2. A server task waits on `accept()`, reads one line, and sends `PONG\n` when a connection arrives.
3. `connectCandidates` tries `::1:port` with a new socket; this IP does not match the IPv4 listener address, so connect fails. The program catches `IOException`, adds it to the suppressed list of the summary error, and closes the socket.
4. The loop creates another socket and tries `127.0.0.1:port`; connect succeeds. The method returns the open socket and **does not try any more addresses**.
5. The client sends `PING\n` and receives `PONG`; `Future.get` confirms the server received `PING` as expected. `try-with-resources` closes the socket; the executor is shut down in `finally`.
6. If `connectHost("service.example.org", port, timeout)` is used in business code, the hostname is resolved first. An `UnknownHostException` from `getAllByName` occurs **before the TCP attempt loop**. If resolution succeeds but all IPs fail, the method throws the combined `IOException`, and the causes can be inspected with `getSuppressed()`.

**Limitations of the example:** it serves only one connection, does not use TLS, and has no connection pool, overall deadline, candidate count limit, or concurrent retry flow. Running on loopback ports may be restricted by machine policies. Do not turn this demo into a direct Internet service; when building an HTTP client, you should usually use `java.net.http.HttpClient` or a library with appropriate timeout, DNS, proxy, TLS, and pooling policies.

## 7. Limitations of sequential attempts and Happy Eyeballs

If a hostname has both IPv6 and IPv4 but the IPv6 path is broken, a client trying IPv6 sequentially with a 3-second timeout can delay using IPv4 even though IPv4 is completely healthy. This hurts user experience when encountering an incompletely configured dual-stack network.

**Happy Eyeballs** (RFC 8305) is an approach to IPv6/IPv4 connection establishment with candidate sorting and **controlled overlapping** attempts to avoid waiting too long on a non-working address/family. This is a more complex algorithm than a `for` loop; it requires managing losing sockets, cancellation, concurrency, and destination selection policies.

For production, consider:

- **Per-address timeout** and **overall deadline** are two different limits. If there are 8 IPs and each waits 2 seconds sequentially, the time before reporting failure can exceed 16 seconds, not counting resolution.
- **Name-resolution timeout/caching** has its own policy; `Socket`'s connect timeout parameter does not limit the time spent fetching addresses.
- **Connect success** only confirms TCP; the TLS handshake, request timeout, and reading the response also have their own time limits.
- **Cancellation:** once one candidate wins, do not leave other parallel connections open unnecessarily.
- **Do not assume** a `Socket` loop you write has Happy Eyeballs built in. HTTP client library APIs, proxies, or runtimes may have different policies; verify in practice.
- **Connection reuse:** reusing an existing connection can avoid both DNS lookup and TCP/TLS handshakes for each request; pool state must be properly lifecycle-managed.

In Java, `Socket.setSoTimeout` is for read waiting; it is **not** an overall deadline for DNS, TCP, TLS, and the entire request. Do not use a single timeout type to describe every phase.

## 8. TLS/HTTPS, DNS changes, and security

**Keep the hostname for TLS verification:** if the application needs HTTPS for `api.example.org`, picking an IP from `getAllByName` only determines the TCP address. Certificate and hostname verification must still be tied to **`api.example.org`**—never arbitrarily skip verification or trust only the IP. With custom TLS built on `Socket`, you must properly configure the peer host, SNI, and hostname verification; it is better to use an appropriate HTTP/TLS client.

**Do not equate a resolved IP with a permanent destination:** DNS records can change due to failover or load balancing. The JVM and system layers may cache results, so do not assume two resolutions always return the same result or always send a fresh DNS query.

**When a hostname is user-supplied**, you must prevent access to internal addresses or disallowed endpoints (SSRF). Validate every network destination, watch out for DNS rebinding and redirects, and enforce checks on **the actual destination being connected to**. Only checking a hostname string prefix or validating an initial IP while ignoring other IPs is not enough.

**Retries with side effects:** if TCP connect has not succeeded, the application has not sent a request on that socket. However, if the request has been sent and the client times out waiting for a response, the server may have already processed it. For example, retrying a money transfer command or `POST /orders` requires an idempotency contract to avoid duplicate processing.

## 9. Layered diagnostic procedure

When Java reports "cannot connect to hostname":

1. **Verify the input:** hostname, port, scheme, whitespace, typos; a string like `https://...` is not a hostname to pass directly into `getAllByName`.
2. **Check name resolution:** call `getAllByName`; record the number of IPs, IPv4/IPv6, and any exception. Do not assume `nslookup`/`dig` always uses the same cache or the same mechanism as the JVM.
3. **Check each TCP endpoint:** for each IP and port, attempt `connect` with a timeout and record the exception type; one IP failing does not mean other IPs fail.
4. **Check listener and route:** is the server bound to the right interface/port? Binding to `127.0.0.1` does not make the server listen on a public IP address; binding IPv4 also does not automatically provide an IPv6 `::1` listener.
5. **After TCP succeeds:** check TLS/SNI/certificates, access permissions, application protocol, HTTP status, and read timeout.
6. **Check variation over time:** record timestamps, client network/VPN, DNS cache, IPs used, latency, and IPv4/IPv6; analyze intermittent issues separately.

Suggested application-defined log classification:

```text
getAllByName failed       -> NAME_RESOLUTION_ERROR
connect IPv6 timed out    -> TCP_CONNECT_TIMEOUT
connect IPv4 refused      -> TCP_CONNECT_REFUSED
another IP connected      -> TCP_CONNECTED
TLS certificate rejected  -> TLS_VERIFICATION_ERROR
HTTP 503 received         -> HTTP_RESPONSE_ERROR
```

The labels above are only logging examples, **not** standard JDK enums or error codes.

Do not use `ping` to conclude that a TCP port is active: ping is typically based on ICMP, may be filtered, and does not check the TCP listener. Similarly, a successful DNS answer does not measure reachability to the service port.

## 10. Common mistakes when writing Java sockets

| Wrong practice | Consequence | Fix |
|---|---|---|
| Using `getByName` and assuming a hostname has only one IP | Skips remaining working candidates | Consider `getAllByName` and a candidate-trying strategy |
| Calling every error "DNS failed" | Misdiagnosis and difficulty fixing the right layer | Separate resolve, connect, TLS, request, and read |
| Combining DNS + connect in one API and logging only the final exception | Hard to identify which phase and IP failed | Resolve first, connect to each `InetAddress`, and preserve causes |
| Setting `setSoTimeout` and thinking `connect` has a timeout | Connection attempts may wait too long | Pass a timeout to `Socket.connect(endpoint, ms)` |
| Reusing a socket after a connect failure | The socket is no longer in a valid state | Create a new socket for each address attempt; always close failed sockets |
| Trying IPs sequentially without an overall deadline | Multiple failing IPs can stretch wait time | Limit total time and choose an appropriate algorithm |
| Treating TCP connected as HTTPS succeeded | Misses handshake/certificate/application errors | Keep the original hostname, verify TLS and application responses |
| Retrying a sent request after a timeout without idempotency | Can execute duplicate operations | Distinguish connect fallback from business-level retry |
| Keeping only the last exception without recording tried IPs | Loses signal about IPv4/IPv6 and fallback order | Log by phase and preserve causes |
| Assuming DNS cache is always fresh or an IP never changes | Failures after failover/destination change | Design caching/connection pooling and refresh appropriately |

## 11. Self-check questions

**1.** `getAllByName("service.example.org")` returns three IPs; connecting to the first IP is refused. Has DNS failed?

**Answer:** No. Name resolution succeeded; this is a TCP error to the first IP/port. The policy can continue trying other IPs.

**2.** Why is `UnknownHostException` from `getAllByName` different from `SocketTimeoutException` from `connect`?

**Answer:** The first exception occurs before any usable candidate IP is obtained during the resolution step; the second exception is a TCP attempt to an IP:port that did not complete within the deadline.

**3.** Does `setSoTimeout(2_000)` guarantee that connecting completes within 2 seconds?

**Answer:** No. It applies to blocking reads after connecting. Use `connect(endpoint, timeout)` for each connect and a separate deadline if you need to bound the entire flow.

**4.** The server only listens on `127.0.0.1:port`. Why does the client fail when trying `::1` and then succeed when trying `127.0.0.1`?

**Answer:** The IPv6 loopback `::1` and IPv4 loopback `127.0.0.1` are different addresses. A listener bound only to IPv4 does not automatically accept connections to the IPv6 loopback.

**5.** When TCP is already connected but HTTPS reports a certificate mismatch, which layer should the error be attributed to?

**Answer:** TLS and hostname verification. Check the original hostname, SNI, certificate, proxy, and protocol configuration; do not assume a DNS error.

**6.** Why can you retry TCP connect to another IP, but you must not automatically retry a `POST` after a read timeout?

**Answer:** When connect has not been established, no business data has been sent on that connection; once the request has been sent, the server may have already processed it even if the client has not received a response.

**7.** Why does the demo not depend on the order of `getAllByName("localhost")`?

**Answer:** The resolver/hosts/OS may return different numbers or orders of IPs. The demo proactively builds a list of IPv6 then IPv4 to accurately test the fallback algorithm; `connectHost` shows how to use real DNS/name resolution.

## 12. Takeaways

- **DNS/name resolution** finds IPs from a hostname; **TCP connect** tries an IP and port.
- Java's `InetAddress.getAllByName` can return **multiple IPv4/IPv6 addresses**, with no guarantee of order or reachability.
- Resolution failure usually appears as `UnknownHostException`; if resolution succeeds but one IP fails, inspect `ConnectException`, connect timeout, or route errors, and you can **try the next IP**.
- Each connect attempt should have its own timeout and socket; close failed sockets, preserve causes, and set an overall deadline.
- Once TCP succeeds, TLS, HTTP, and business errors are separate phases. **TCP fallback** is not the same as safely retrying an application request.

References: JDK 17 API `java.net.InetAddress`, `java.net.Socket`, `java.net.InetSocketAddress`; RFC 8305 (*Happy Eyeballs Version 2*).
