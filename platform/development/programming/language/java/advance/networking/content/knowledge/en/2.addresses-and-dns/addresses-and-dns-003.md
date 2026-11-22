# getByName, getAllByName, and a Hostname with Multiple Addresses

## Objectives

After this lesson, you can:
- Distinguish between retrieving **one** address and retrieving a **list** of addresses from the same hostname using `InetAddress`.
- Explain why a hostname can resolve to multiple IPv4/IPv6 addresses and why resolution results can change.
- Write a Java 17+ program to inspect resolution results, handle errors, and avoid wrong assumptions about ordering or reachability.

## 1. From Hostname to IP Address

A hostname such as `api.example.com` is an application-layer name. Before establishing a normal TCP/UDP connection to a name, the system needs to map that name to one or more IP addresses. In DNS, an **A** record represents an IPv4 address; an **AAAA** record represents an IPv6 address. Beyond DNS, the system name resolver can also be affected by the hosts file, operating system configuration, caches, and network policies. Therefore, the result observed from Java does not necessarily match a raw DNS query.

A hostname can be associated with multiple IPs because:
- **Multiple machines serving the same name:** distributing traffic, increasing availability, or placing servers in multiple regions.
- **A single machine/platform with multiple interfaces or addresses:** multiple IPs do not necessarily mean multiple physical machines.
- **Dual stack:** the same name has both A and AAAA records to support both IPv4 and IPv6.
- **Location-, policy-, or time-based DNS:** different clients, or the same machine at different times, may receive different sets of addresses.

A **hypothetical** example (the documentation IPs `192.0.2.0/24` and `2001:db8::/32` do not represent real services):

~~~text
service.example
  ├─ A     → 192.0.2.10
  ├─ A     → 192.0.2.11
  └─ AAAA  → 2001:db8::10
~~~

From that hypothetical data, a single resolution may return one IPv4 address, or a set of IPv4/IPv6 addresses, depending on the resolver and environment. **A hostname does not have a mandatory one-to-one relationship with an IP.**

## 2. Two Methods of `java.net.InetAddress`

| API | Return Type | Meaning |
|---|---|---|
| `InetAddress.getByName(String host)` | `InetAddress` | Retrieves **one address** for a hostname or IP literal. |
| `InetAddress.getAllByName(String host)` | `InetAddress[]` | Retrieves the **array of addresses** returned by the system's configured resolver for that name. |
| `address.getHostAddress()` | `String` | Retrieves the textual IP representation from an existing `InetAddress`. |
| `address.getAddress()` | `byte[]` | Retrieves the raw IP bytes (4 bytes for IPv4, 16 bytes for IPv6). |

Both `getByName` and `getAllByName` are synchronous resolution APIs: a call may block waiting for the resolver, and may throw `UnknownHostException` when no address can be found. They **do not create a socket, do not open a connection, do not probe ports, and do not check whether the server is alive**.

**`getByName(host)`:** suitable when the software only needs a single address object. For a multi-IP hostname, the API selects one address according to the resolver's result/policy; there is no contract that it is the fastest, healthiest, closest, or always IPv4. Nor should you take that IP and infer that the hostname has only one address.

**`getAllByName(host)`:** suitable when you need to inspect or process the candidate set. The result is an array containing one or more `InetAddress` instances if resolution succeeds; the array does not necessarily contain every record published in global DNS because the data may be affected by the resolver, address family selection, configuration, and caching. Element order must not be treated as a fixed priority or a load-balancing algorithm.

**Relationship between the two calls:** when served from the same consistent result set, the address chosen by `getByName` is usually included in the set of addresses returned by `getAllByName`. However, they are **two separate calls**: data, configuration, or caches may change. Do not write tests assuming two independent calls must produce the exact same set and order forever.

The argument can be a name like `example.com` or an IP literal like `127.0.0.1` / `2001:db8::1`. For a valid IP literal, Java parses the address directly without needing a DNS query to translate a name to an IP. The `null` or empty-string cases have loopback semantics according to the API; in applications, you should validate input and reject empty hostnames when that is not intended.

## 3. Runnable Program: Comparing Two Results

Save as **`AddressLookup.java`** (Java 17 or later):

~~~java
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.UnknownHostException;

public final class AddressLookup {
    public static void main(String[] args) {
        String host = args.length > 0 ? args[0] : "example.com";

        try {
            InetAddress first = InetAddress.getByName(host);
            InetAddress[] all = InetAddress.getAllByName(host);

            System.out.println("Host: " + host);
            System.out.println("getByName: " + first.getHostAddress());
            System.out.println("getAllByName: " + all.length + " address(es)");

            for (int i = 0; i < all.length; i++) {
                InetAddress ip = all[i];
                String family = ip instanceof Inet4Address ? "IPv4" : "IPv6";
                System.out.printf("%d. %s (%s)%n",
                        i + 1, ip.getHostAddress(), family);
            }
        } catch (UnknownHostException e) {
            System.err.println("Cannot resolve host: " + host);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 AddressLookup.java
java AddressLookup 127.0.0.1
~~~

**Exact stdout** for the IP literal input `127.0.0.1`:

~~~text
Host: 127.0.0.1
getByName: 127.0.0.1
getAllByName: 1 address(es)
1. 127.0.0.1 (IPv4)
~~~

This example uses a literal so the output does not depend on DNS. It demonstrates the return types and how to iterate over the array, **not** that a real hostname has multiple IPs. To observe the real resolver, run:

~~~bash
java AddressLookup example.com
java AddressLookup localhost
~~~

For these commands, there is **no fixed stdout**: the count, order, and address families may vary by environment. `localhost` is usually configured locally and may correspond to IPv4 `127.0.0.1`, IPv6 `::1`, or both. If only one address is returned, that is a valid result; do not fabricate extra IPs just to produce two lines.

**Code explanation:** `first` is a single address from the first call; `all` is the array of addresses from the second call. `getHostAddress()` outputs the IP address for observation; `instanceof Inet4Address` identifies IPv4, and the remaining addresses in this case are IPv6. `UnknownHostException` is caught specifically to display a clear resolution error. Network connection handling, timeouts, and retries remain separate responsibilities.

## 4. When a Hostname Returns Multiple IPs, What Should You Understand?

Suppose an actual resolution for `service.example` (for illustration only) returns:

~~~text
192.0.2.10
192.0.2.11
2001:db8::10
~~~

- `getByName("service.example")` only provides **one** `InetAddress`, for example `192.0.2.10`. This example address is **not a guarantee** that Java always picks the first element or always chooses IPv4.
- `getAllByName("service.example")` can provide an **array** containing the candidates above. The application can log them, classify IPv4/IPv6, or attempt connections according to its own policy.
- Even if an address appears in the array, the target host/port may still refuse the connection, time out, be unroutable, or fail TLS. **Successful name resolution is different from a successful connection.**
- Multiple addresses for the same hostname do not automatically guarantee load balancing. The resolver may change the order, the application may pick one address, and DNS does not monitor the full health of the service.

A typical flow diagram:

~~~text
hostname
  → Java/system resolver (may use cache, hosts, DNS...)
  → InetAddress[] (returned addresses)
  → application/HTTP client selects and tries addresses according to policy
  → socket connect(IP, port) → success or error
~~~

You should separate three questions: **what does the name resolve to?** (`getAllByName`), **which address is selected?** (resolver/client rules), and **is the selected address reachable?** (socket, route, port, TLS, application). Confusing these three layers is the cause of many hard-to-reproduce bugs.

## 5. Application: Iterating Candidates When You Want a Fallback Path

If you build a low-level TCP client yourself, retrieving multiple addresses is only the **first step**. You must set timeouts, handle failures for each candidate, and close resources promptly. The following snippet is **an illustrative method to place in a Java class importing `java.io.IOException` and `java.net.*`**; it is not a standalone `main` program:

~~~java
static Socket connectAny(String host, int port, int timeoutMillis)
        throws IOException {
    IOException lastFailure = null;

    for (InetAddress address : InetAddress.getAllByName(host)) {
        Socket socket = new Socket();
        try {
            socket.connect(new InetSocketAddress(address, port), timeoutMillis);
            return socket; // The caller must close the Socket when done.
        } catch (IOException ex) {
            lastFailure = ex;
            try {
                socket.close();
            } catch (IOException closeFailure) {
                ex.addSuppressed(closeFailure);
            }
        }
    }

    throw new IOException("No reachable address for " + host, lastFailure);
}
~~~

This is a **sequential attempt** example, so if each address times out, the total duration can be large; you need to validate `port` and `timeoutMillis` before use, and the caller must close the returned socket (typically with `try-with-resources`). In real HTTP/TLS applications, prefer a standard client with proper connection policies, IPv4/IPv6 preference, retries, and hostname/TLS verification. **Do not manually replace the hostname with a fixed IP and skip certificate verification**; the address used to connect does not replace the TLS server identity.

If you only need to call a REST API, generally pass the **hostname URL** to the HTTP client and let the library handle connections. Do not build your own address-rotation mechanism with `getAllByName` without a specific requirement.

## 6. Ordering, IPv4/IPv6, and Caching

**Order is not fixed.** The candidate set and order are affected by DNS, caches, the system resolver, IPv6 support, and JVM networking properties. Java does not guarantee that the array is always sorted in ascending address order, IPv4 before IPv6, or that a specific IP stays at index 0. Therefore:
- Do not write business logic tying the "primary server" to `all[0]`.
- Do not write unit tests expecting real DNS results to have exactly N IPs in a hardcoded order.
- If candidate ordering must be guaranteed, specify the application's policy explicitly after resolution; if availability must be checked, check it at the connection step.

**Name caching.** `InetAddress` caches both successful and failed resolutions. Java's cache TTL can be tuned via security properties such as `networkaddress.cache.ttl` (positive) and `networkaddress.cache.negative.ttl` (negative); some JDKs also support `networkaddress.cache.stale.ttl`. The default TTL for positive records depends on the implementation/configuration, so do not claim that every JVM always re-queries DNS on every call or always caches forever. These are **security properties**, so you should not assume setting `-Dnetworkaddress.cache.ttl=...` is the standard way to configure them.

When DNS changes but Java still observes the old address, check the JVM cache, OS/resolver cache, external DNS, and TTL timing; do not blame every discrepancy on a `getAllByName` bug.

**IPv4 and IPv6.** A hostname may have both A and AAAA records, but the JVM/host machine does not necessarily support or select both. Do not split IP strings on `:` to detect IPv6: IPv6 has a different textual format from IPv4 and can also include a scope ID. Use `instanceof Inet4Address` or `instanceof Inet6Address` when you genuinely need to classify; if you are only logging, `getHostAddress()` is enough.

## 7. Common Mistakes and Fixes

| Misconception or Mistake | Correct Understanding / Practice |
|---|---|
| "`getByName` returned one IP, so the hostname has only one IP." | It only returns **one** element; use `getAllByName` if you need the observable set of addresses. |
| "`getAllByName` always returns all A/AAAA records from authoritative DNS." | The API returns the set provided by the **configured resolver**, which can be affected by caches/policies/IPv6. This is not a raw DNS record query API. |
| "The first element is the primary/fastest server." | Order is not a measure of health, latency, weight, or application priority. |
| "If the name resolves, port 443 must be open." | Resolution does not attempt a connection; connection errors must be handled in the socket/HTTP client. |
| "`UnknownHostException` proves the domain is unregistered." | It can be caused by DNS, network, hosts/resolver, or policy; the exception only indicates that the resolution attempt failed. |
| "Every call will see the latest DNS." | There are multiple cache layers and TTLs; results may repeat even if external DNS has changed. |
| "`getHostName()` or `getCanonicalHostName()` is how to get all additional IPs." | These are name/reverse-lookup or canonical-name operations (best effort), **not a replacement** for `getAllByName`. |
| "Returning an IPv6 address means the machine can definitely connect over IPv6." | Having an IPv6 address does not guarantee a working IPv6 network path, route, or service. |

Additional note: `InetAddress` represents an **IP address**, without a port number. `InetSocketAddress` is what combines an address (or hostname) with a port. Also, DNS results should not be used as proof of server identity; for HTTPS/TLS, hostname/certificate verification still needs to take place.

## 8. Self-Check and Mini-Exercises

1. Run `java AddressLookup 127.0.0.1` and explain why the result is deterministic without a DNS query.
2. Run `java AddressLookup localhost` and `java AddressLookup example.com` in two environments. Record the count, order, and address families **exactly as observed**, without assuming they must match.
3. If a hostname returns 2 IPv4 addresses and 1 IPv6 address, what does `getByName` tell you? What additional information does `getAllByName` give? Can you infer that all three TCP ports are open?
4. Consider a scenario where DNS has switched from IP A to IP B, yet the JVM still sees A. List the cache layers to check before concluding the application is buggy.
5. Modify the program yourself to count the number of IPv4 and IPv6 addresses in `all`. When writing automated tests, use IP literals/fixtures for deterministic logic and separate integration tests that perform real DNS resolution.

**Core answers:** (1) literals are parsed directly; (3) `getByName` returns one address, `getAllByName` returns the candidate array seen by the resolver, without checking ports; (4) JVM cache, OS/resolver cache, and DNS infrastructure. Questions (2) and (5) primarily evaluate real-world observation and array handling, with no single fixed standard IP set.

## 9. Key Takeaways

- `getByName(host)` → **one `InetAddress`**; `getAllByName(host)` → **an `InetAddress[]` array**.
- A hostname can map to multiple IPv4/IPv6 addresses; the order and count from the resolver vary by environment.
- **DNS lookup ≠ successful connection**; you need proper client/socket handling, timeouts, error handling, and TLS.
- Caches and system/JVM configuration can make results differ from expectations; avoid depending on "hardcoded" IP sets in tests and business logic.

### References

- [Oracle Java SE 21 — `InetAddress`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html)
- [Oracle Java SE 21 — Networking Properties (Address Cache)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/doc-files/net-properties.html)
