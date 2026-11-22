# Caching Successful, Failed, and Expired DNS Results in Java

When a Java application connects to `api.example.com`, the hostname needs to be resolved to an IP address. Repeated lookups can be time-consuming; however, keeping results for too long can also cause the application to keep calling an IP that has changed. `java.net.InetAddress` provides caching for both **successful resolution results (positive cache)** and **failed resolution results (negative cache)**. On supported JDKs, a **stale cache** policy also allows temporarily using an old successful address when a refresh fails.

**Version scope:** the positive/negative concepts and the two properties `networkaddress.cache.ttl`, `networkaddress.cache.negative.ttl` apply to Java 17+. The `networkaddress.cache.stale.ttl` property is documented in Java 21, but is **not listed in Java 17 documentation**; only configure stale after verifying that your actual JDK/runtime supports it. This lesson examines name resolution through `InetAddress` and does not apply by default to all third-party DNS libraries.

## 1. What results are stored and where?

`InetAddress.getByName(host)` returns a single address; `InetAddress.getAllByName(host)` returns the addresses provided by the resolver. With the default resolver, data may come from local machine configuration (for example, the hosts file), the operating system's resolver, and naming services such as DNS. Therefore, **calling `InetAddress` once does not mean a DNS query packet has been sent over the network**.

~~~text
Java application calls InetAddress.getAllByName(host)
          |
          v
  InetAddress name/address cache in the JVM
          |
       Cache hit? ---- yes ----> return cached IP or throw cached error
          |
          no
          v
 Configured resolver (hosts/OS/DNS/...)
          |
          +---- resolution succeeds ----> positive cache ----> IP list
          |
          +---- resolution fails -------> negative cache ----> UnknownHostException
~~~

Three layers that are often confused:

| Layer | Contents | Key point to remember |
| --- | --- | --- |
| `InetAddress` cache in the JVM | Successful/failed results when the application resolves names through this API | Governed by Java security properties; typically must be observed per JVM process |
| OS or recursive DNS resolver/cache | Data stored by the system and DNS infrastructure | Has its own TTL policy and refresh mechanism |
| Connection pool / TCP socket | Connections already opened to an IP | Changing the DNS cache **does not automatically switch** an active socket to another IP |

The TTL in a DNS record published by the DNS infrastructure and the TTL of the **`InetAddress` cache** are two separate concerns that must be distinguished. You must not infer that the JVM's TTL is guaranteed to equal the DNS record TTL. Some HTTP clients, Netty resolvers, or service-discovery clients have their own caches; check the actual resolution path before applying this policy.

## 2. Positive cache: storing successful resolutions

Suppose at time `t0`, the resolver returns `service.example -> 192.0.2.10`. If the positive TTL is 30 seconds, resolutions through the same cache within that validity window can use this address without calling the underlying resolver. When the cache entry expires, a new lookup may need to resolve again and receive `192.0.2.20`.

**Significance:** reduces latency and query load, but if the TTL is too long, the application may keep using an old IP after the service changes its address (deployment, failover, load balancing). A TTL of `-1` means cache forever according to policy; `0` means no caching; a positive number is the number of seconds. The default positive TTL is described in Java documentation as **implementation-dependent** when no Security Manager is present; do not take a default number from one environment and assume it applies to every JVM.

Returned addresses may be IPv4, IPv6, or multiple addresses. The results of `getAllByName` and the order of addresses can vary by machine. Do not use a fixed IP or a fixed query duration as the expected output for networking examples.

## 3. Negative cache: storing failed resolutions

If the resolver cannot find a valid address for a hostname, calling `InetAddress.getByName`/`getAllByName` may throw `UnknownHostException`. The JVM can remember this failed result for the **negative TTL**. Subsequent calls within that window may fail immediately from the cache, even if the external cause has been fixed.

Example:

1. `t0`: the application looks up `new-service.example` when the service name has not been created yet or the DNS system is failing; the lookup fails.
2. Negative TTL = 10 seconds: within the validity window, repeated lookups may continue receiving errors from the cache.
3. When the negative entry expires, a new lookup can retry. If the name is now valid, the application can receive the IP and create a positive entry.

**Do not equate every `UnknownHostException` with "DNS returned NXDOMAIN".** The error may be influenced by resolver configuration, the network, or naming services. This API provides no basis for attributing all lookup errors to a specific DNS response. Negative caching is useful for preventing futile repeated queries, but a TTL that is too large can prolong an outage after DNS recovers. According to Java documentation, the default negative TTL is **10 seconds**; the specific deployment configuration should still be checked.

## 4. Expired data differs from stale data

**Expired** means the period for using a positive result under the normal TTL has ended; a subsequent resolution needs to consider refreshing. **Stale** means an old positive result has expired but can still be retained under a separate policy to serve as a fallback **when a refresh lookup fails**.

~~~text
Previously resolved successfully?
   |
   +-- No --> no old IP available to use as stale
   |
   +-- Yes --> positive entry still within TTL? -- Yes --> use current entry
                         |
                         No
                         |
                    attempt refresh
                         |
         +---------------+----------------+
         |                                |
      succeeds                          fails
         |                                |
   update IP/TTL            stale enabled and still valid?
                                          |
                                 +--------+--------+
                                 |                 |
                                Yes                No
                                 |                 |
                           use old IP       report resolution error
~~~

On **Java 21**, `networkaddress.cache.stale.ttl` allows retaining and using an old name when the positive TTL has expired and the refresh fails. If the stale TTL is greater than the positive TTL, the `InetAddress` documentation describes the positive TTL as the **refresh interval**: for example, with positive TTL = 30 seconds and stale TTL = 1 day, the JVM can attempt a refresh every 30 seconds while still having a window to use the old data. A stale value of `0` or unset means **do not use stale**; negative values are ignored.

**Do not misinterpret stale as "always return the old IP whenever the TTL expires"**: there must be a prior successful result, the refresh attempt must fail, and the stale policy must still allow its use. When a refresh succeeds, the new address is used according to policy. When no valid old data is available as a fallback, the application may still receive a resolution error.

Stale is helpful if DNS infrastructure is temporarily disrupted while the old IP is still serving traffic. However, the old IP may have been reclaimed, reassigned, or may no longer point to the right system. **Keeping an IP does not guarantee that a TCP/TLS/HTTP connection will succeed or be safe.** This is a trade-off between availability to continue operating and the freshness/accuracy of the connection target.

## 5. Configuring the JVM cache policy

| Java security property | Role | `0` | Positive number | `-1` |
| --- | --- | --- | --- | --- |
| `networkaddress.cache.ttl` | Positive result | Do not cache | Seconds to cache a successful result | Cache forever |
| `networkaddress.cache.negative.ttl` | Negative result | Do not cache | Seconds to cache a failure | Cache forever |
| `networkaddress.cache.stale.ttl` (supported JDKs, e.g., Java 21) | Retain old successful result as fallback when refresh fails | Do not use stale | Seconds under the stale policy | Negative values are ignored; does not mean cache forever |

These are **security properties**, not corresponding system properties. Therefore, `-Dnetworkaddress.cache.ttl=30` and `System.setProperty("networkaddress.cache.ttl", "30")` are **not the official way to configure them**. You can set them in `$JAVA_HOME/conf/security/java.security`, or better for a standalone test, use an additional file via `-Djava.security.properties=...`. A single `=` appends the file to the main configuration; do not use the double `==` syntax and accidentally replace the entire baseline security configuration.

Example of a **test policy**, not default values or recommendations to use verbatim in production:

~~~properties
# dns-cache.security — Java 17+
networkaddress.cache.ttl=3
networkaddress.cache.negative.ttl=2

# Enable only if the JDK supports stale caching (e.g., Java 21+):
networkaddress.cache.stale.ttl=15
~~~

For Java 17, remove or comment out the stale line; Java 17 does not list this mechanism in the `InetAddress` documentation. On a JDK verified to support it, you can enable it when you want to study failed refresh behavior.

The values are read by the JVM through the security configuration mechanism. You can use `Security.setProperty("networkaddress.cache.ttl", "3")` from Java **very early, before the first DNS resolution**, but setting it late may not affect a policy that has already been initialized/held in the cache. Configuring at startup, launching a new process for each scenario, and verifying the effect is a more reproducible approach.

## 6. A Java 17+ program to observe lookup results

Save the exact file `DnsCacheProbe.java`:

~~~java
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.security.Security;
import java.util.Arrays;
import java.util.stream.Collectors;

public class DnsCacheProbe {
    private static void lookup(String host) {
        long start = System.nanoTime();
        try {
            InetAddress[] addresses = InetAddress.getAllByName(host);
            String ips = Arrays.stream(addresses)
                    .map(InetAddress::getHostAddress)
                    .collect(Collectors.joining(", "));
            System.out.printf("%s -> OK [%s]%n", host, ips);
        } catch (UnknownHostException ex) {
            System.out.printf("%s -> UNKNOWN_HOST%n", host);
        } finally {
            long millis = (System.nanoTime() - start) / 1_000_000;
            System.out.printf("  elapsed=%d ms%n", millis);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("Java feature version: "
                + Runtime.version().feature());

        for (String key : new String[] {
                "networkaddress.cache.ttl",
                "networkaddress.cache.negative.ttl",
                "networkaddress.cache.stale.ttl"
        }) {
            System.out.printf("%s=%s%n", key, Security.getProperty(key));
        }

        String goodHost = args.length > 0 ? args[0] : "localhost";
        String badHost = args.length > 1
                ? args[1] : "no-such-host.invalid";

        for (int round = 1; round <= 3; round++) {
            System.out.println("round=" + round);
            lookup(goodHost);
            lookup(badHost);
            if (round < 3) {
                Thread.sleep(1_500);
            }
        }
    }
}
~~~

Compile and run from the directory containing both files:

~~~bash
javac DnsCacheProbe.java
java -Djava.security.properties=dns-cache.security DnsCacheProbe
~~~

You can replace the two machine names with hostnames from your test environment:

~~~bash
java -Djava.security.properties=dns-cache.security DnsCacheProbe localhost no-such-host.invalid
~~~

**How to read the output:** the output includes `Java feature version: ...`, the configuration lines, and three rounds `round=1`, `round=2`, `round=3`. With the sample configuration, the explicit property lines will show `3`, `2`, `15` respectively if the file is loaded; on a JDK that does not support stale, **the printed property value does not prove the runtime enforces the stale policy**. `localhost` usually returns `OK [...]` via the hosts file/loopback; `no-such-host.invalid` usually returns `UNKNOWN_HOST`, though local configuration can change both results. The IPs, number of addresses, `elapsed` time, and hostname handling depend on the machine, so there is no single fixed stdout of addresses/timings across all environments.

**Limits of the evidence:** multiple small `elapsed` times do not prove a JVM cache hit by themselves: it could be the hosts file, OS cache, recursive DNS cache, a fast network path, or warm-up effects. The program demonstrates how to call the API, read the configuration, and distinguish success from failure, but **it cannot count the number of DNS queries the JVM actually sends**. You need to verify using an observable resolver/server and a dedicated test environment.

## 7. Controlled experiments to verify all three states

To properly verify the cache, prepare a test hostname you control and a resolver with query logging (avoid changing DNS in production). Start a new JVM for each scenario to eliminate old cache state.

| Scenario | Setup | Observation and explanation |
| --- | --- | --- |
| **Positive hit / refresh** | Resolvable test name; short positive TTL; call repeatedly before and after TTL; change the IP on the controlled resolver | Before the TTL expires, the application may keep receiving the previous address. After the TTL, a new resolve may receive the new IP; cross-check the resolver logs to separate JVM caching from caches below the JVM |
| **Negative hit / recovery** | Start with an unresolvable name; negative TTL of a few seconds; then create a valid record/state | `UnknownHostException` may continue occurring until the negative entry expires; only a retry after that has a chance to succeed |
| **Stale fallback (supported JDKs)** | Initial lookup succeeds; short positive TTL, longer stale TTL; after the positive TTL, make the refresh fail while the old IP remains usable | While stale is still valid, `InetAddress` may return the previous IP; when the resolver recovers, verify that a successful refresh replaces the old IP |
| **Stale without prior history** | A name that has never resolved successfully before the resolver fails | There is no positive entry to use as stale; do not expect "stale to appear on its own" |
| **Stale expiration** | Keep refresh failures lasting beyond the stale retention window | Eventually it can no longer rely on the old address; the outcome must be evaluated against the resolver and expiration policy |

In the test environment, record timestamps, JDK version, the three security properties, hostname, addresses returned by the resolver, the number of requests actually reaching the resolver, when DNS changed, and application errors. When measuring negative cache, compare the recovery time against the negative TTL; when measuring stale, confirm that a **successful positive lookup occurred before causing DNS to fail**.

## 8. Diagnosing real-world incidents

**Case A — DNS has been updated, but Java still calls the old IP.** Check whether the application uses `InetAddress`, the current positive TTL, the stale policy, IP addresses in the connection pool, OS/resolver cache layers, and whether there is a proxy or a custom DNS client. An open socket or connection pool can continue communicating with the old IP even after new resolutions are already correct.

**Case B — DNS has been created, but Java keeps reporting `UnknownHostException`.** Check the negative TTL, the time of the first failed lookup, whether DNS has actually recovered at the resolver the JVM uses, and which other caches are still holding the failure. Avoid a fix that merely "increases continuous retries": while the negative entry is still valid, frequent retries may not help.

**Case C — when DNS is down, Java still returns an IP, but network requests fail.** If stale is enabled, the returned IP is only a fallback to **attempt a connection**; check whether the old IP is still serving, TLS hostname/SNI, routing, health checks, and TCP/HTTP error logs. Do not treat stale as a guarantee of continuous service availability.

**Case D — TTL configuration seems to have no effect.** Check that a security property is used instead of `-Dnetworkaddress.cache.ttl`, that the security file is loaded at JVM startup, the JDK version, whether a resolution already happened before configuration, and whether the name is resolved through another library's cache. There is no universal public Java SE API to "flush" the entire `InetAddress` cache of a running JVM; starting a new test process is a cleaner way to verify.

## 9. Deciding TTL values for operational goals

- **A shorter positive TTL** picks up IP changes/failover faster, at the cost of higher query volume and greater dependence on the resolver. **A longer one** reduces lookups but extends the time spent using old addresses. Do not set `-1` out of habit for services with dynamic IPs.
- **A short negative TTL** is suitable when hostnames appear and disappear frequently (service discovery, deployment environments), though it can subject DNS infrastructure to many failed lookups. A long negative TTL reduces failed queries but prolongs apparent outages after DNS recovers.
- **Stale TTL** should only be enabled when there is a clear availability requirement, evidence that the old IP remains an acceptable target, and an assessment of the risk of calling the wrong server. For security-sensitive or tenant-sensitive endpoints, stale data can cause greater harm than failing fast.
- Combine this with **timeouts, retries with backoff, health checks, and multi-IP handling** at the connection layer. DNS TTL does not replace those mechanisms, nor does it replace recreating broken connections.
- Choose values based on your infrastructure's DNS lifetimes, desired failover speed, query traffic, fault tolerance, and test results with logging. There is no single three-number configuration that works for every service.

## 10. Common misconceptions to avoid

1. **"DNS record TTL = JVM TTL."** The two TTLs belong to different layers; resolver infrastructure may also cache separately.
2. **"`UnknownHostException` definitely means NXDOMAIN."** Java only reports that name lookup failed; do not attribute the cause to a single DNS code.
3. **"TTL = 0 disables caching across the entire network."** It only controls the relevant `InetAddress` cache; the OS, recursive resolver, and other libraries may still cache.
4. **"Once the positive TTL expires, the old IP will definitely no longer be used."** On JDKs supporting stale and with configuration allowing it, the old IP may be used when refresh fails.
5. **"Enabling stale gives every hostname a fallback."** There must be a prior successful lookup; failing on the very first lookup leaves no old IP.
6. **"Just change `System.setProperty` at runtime."** The cache/policy may already be initialized; configure from JVM startup and verify.
7. **"Java returning the old IP means the connection pool has been updated."** Resolution changes do not close open sockets.
8. **"Three fast lookup rounds prove DNS caching."** You must observe each layer, especially resolver logs, to conclude which cache it is.

## 11. Self-check questions

**Question 1:** A service's DNS record was just created, yet the JVM still gets `UnknownHostException`. Which property should you check first?  
**Answer:** `networkaddress.cache.negative.ttl` and the time the failure was cached; then verify the resolver and caches outside the JVM.

**Question 2:** The positive TTL has expired and the refresh fails. When can Java return the old IP again?  
**Answer:** On a JDK with the stale mechanism enabled, when there was a prior positive result and the old data is still within the stale policy window. Otherwise, the lookup may fail.

**Question 3:** Does lowering the positive TTL to 1 second guarantee that new connections always use the latest DNS IP?  
**Answer:** No. There are still OS/resolver caches, clients managing their own DNS, load balancing, address selection behavior, and reused connections.

**Question 4:** Why not use `-Dnetworkaddress.cache.ttl=5` as a regular JVM flag?  
**Answer:** Because this is a Java security property. Use a security configuration file or set it very early with `Security.setProperty` before the cache policy is initialized.

## Authoritative JDK reference documentation

- Java 17, `InetAddress` (positive and negative cache): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html
- Java 21, `InetAddress` (including stale TTL): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html
- Java 21, Networking Properties (Address Cache): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/doc-files/net-properties.html
- Java 21, Security Properties File (how to configure an additional file): https://docs.oracle.com/en/java/javase/21/security/security-properties-file.html