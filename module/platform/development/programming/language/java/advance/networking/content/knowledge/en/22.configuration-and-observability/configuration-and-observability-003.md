# DNS Cache Properties Differ from Regular System Properties

## 1. Learning Objectives

In Java Networking, changing a hostname → IP mapping often leads to the question: **“Why did I change DNS, yet my Java application still calls the old IP?”** Part of the answer may lie in the **DNS/address cache inside the JVM**. However, there is a detail that is very easy to misconfigure: the standard properties controlling `InetAddress` TTL are **Java security properties**, not regular system properties that you set with `-Dnetworkaddress.cache.ttl=...` or `System.setProperty(...)`.

This topic belongs to the **Configuration and Observability** group. This lesson helps you:
1. Identify the two security properties `networkaddress.cache.ttl` and `networkaddress.cache.negative.ttl`.
2. Explain **positive cache** (successful lookups) and **negative cache** (failed lookups) along with `-1`/`0`/TTL-in-seconds values.
3. Distinguish `Security.getProperty` from `System.getProperty`; `Security.setProperty` from `System.setProperty`.
4. Configure DNS TTL **properly before starting the application** via `conf/security/java.security` or a supplementary file using `-Djava.security.properties=...`.
5. Understand why `-Dnetworkaddress.cache.ttl=0` is **not** the standard way to disable the `InetAddress` DNS cache.
6. Observe caching in a local environment independent of Internet DNS using `jdk.net.hosts.file` and three runnable Java 17+ examples.
7. Avoid confusing the JVM cache with the OS resolver, authoritative DNS TTL, proxy caches, HTTP client connection pooling, or already-open TCP connections.
8. Know how to inspect configuration when an application receives stale IPs or retains `UnknownHostException` results for a period of time.

**Key takeaway:** `networkaddress.cache.ttl` is the name of a **security property**. `System.getProperty("networkaddress.cache.ttl")` may return the string set via `-D` without **reflecting** the security policy value that `InetAddress` uses. To view a security property, read `java.security.Security.getProperty(...)`.

## 2. Which Layers Does DNS Resolution in Java Span?

When Java needs to connect to `api.example.com:443`, the logical chain may include:

```text
Application: Socket/HttpClient/URLConnection
             │
             ▼
Hostname + service port
             │
             ▼
InetAddress / JDK name-resolution mechanism
             │
             ├─ JVM positive/negative address cache
             │     ├─ hit  -> return cached result
             │     └─ miss -> query name service
             ▼
Operating system / local hosts / DNS / name service provider
             │
             ▼
IP address(es): IPv4 and/or IPv6
             │
             ▼
TCP connect / TLS / HTTP request
```

This is a **conceptual** diagram, not a claim that every request calls `InetAddress.getByName` once. For example:
- An HTTP client can keep and reuse an already-open connection, so it **does not need to look up DNS again** for each HTTP request.
- The name service may use `hosts`, DNS, NIS, OS configuration, or another provider mechanism.
- The name resolution result may contain multiple IPs. IPv4/IPv6 selection policies and retry/failover can affect the actual IP used.
- The JVM address cache and the DNS cache in the OS/recursive resolver are **not the same cache**.

The control point in this lesson is the **Java name-resolution cache**, not modifying authoritative DNS TTLs or flushing caches on a router.

## 3. Two Standard Properties: Positive and Negative TTL

Java SE 17 defines two **Java security properties** for caching hostname resolution:

| Property | Cached Result | Java 17 API Default | Values |
| --- | --- | --- | --- |
| `networkaddress.cache.ttl` | Successful lookup: hostname → address | **Implementation-specific** when no SecurityManager is installed; **forever** if a SecurityManager is installed | Number of seconds, `0`, `-1` |
| `networkaddress.cache.negative.ttl` | Failed lookup: e.g. `UnknownHostException` | **10 seconds** per Java 17 documentation | Number of seconds, `0`, `-1` |

Key meanings:
- `0`: **do not store the result** in the corresponding Java cache.
- Positive integer `n`: cache the result for **n seconds**.
- `-1`: **cache forever** per policy. The Java 17 networking documentation also notes that other negative values similarly mean never expire; for readable configuration, use `-1`.
- Property not declared: uses the implementation/runtime default; **do not** assume every JVM 17 has a fixed 30-second positive TTL.
- Negative TTL and positive TTL are **independent**: setting positive=60 does not automatically make negative=60.

### Example Scenario

```text
t=0:   app lookup good.example -> 192.0.2.10 (success)
t=1:   upstream DNS changes to 192.0.2.11
t=10:  app looks up again
       ├─ positive TTL=60: may still receive 192.0.2.10 from JVM cache
       └─ positive TTL=0: JVM does not retain the positive result,
                          but external caches/resolvers may still hold the old IP

t=0:   app lookup typo.invalid -> UnknownHostException
t=2:   name service begins having a record for typo.invalid
t=3:   app looks up again
       ├─ negative TTL=10: may still fail from JVM negative cache
       └─ negative TTL=0: JVM must query the name service again,
                          the result still depends on underlying resolver layers
```

The `192.0.2.x` addresses are an illustrative documentation range; this is not executed output. Two local programs below will **measure changes in a test name service**, without using public DNS.

## 4. A Security Property Is Not a System Property

Java has **two different configuration namespaces**:

| Characteristic | Java system property | Java security property |
| --- | --- | --- |
| Read | `System.getProperty(key)` | `Security.getProperty(key)` |
| Write in code | `System.setProperty(key, value)` | `Security.setProperty(key, value)` |
| Loaded from file | `-D...`, JVM/runtime config | `$JAVA_HOME/conf/security/java.security`, supplementary security file |
| Used for | Countless runtime/network/app settings | Security policy and certain special network parameters |
| Standard Java 17 DNS cache TTL? | **No** | **Yes** |

For example, these two lines are **not equivalent**:

```java
System.setProperty("networkaddress.cache.ttl", "0");
Security.setProperty("networkaddress.cache.ttl", "0");
```

The first line creates/updates a **system property** with that exact string name. However, the Java SE 17 documentation states that the two DNS cache TTL keys are **security properties, not configured via `-Dnetworkaddress.cache.ttl=...` or `System.setProperty`**.

The second line changes the value in the **security property namespace**, but there is a very important caveat: **runtime mutation is not guaranteed to change the effective enforcement policy if the subsystem has already read/cached the TTL policy earlier**. For accurate and reproducible configuration, prefer setting it **before the application JVM starts**.

## 5. Why Is `-Dnetworkaddress.cache.ttl=0` Misleading?

A launcher may run:

```bash
java -Dnetworkaddress.cache.ttl=0 Main
```

A valid JVM can accept this option and:

```java
System.getProperty("networkaddress.cache.ttl")
```

returns `"0"`. An operator sees `"0"` and assumes the cache is disabled. **However**, an arbitrary system property can exist without being used by `InetAddress` as a security policy.

Per the Java 17 documentation:
- `-Dnetworkaddress.cache.ttl=0` only sets a **system property** of that name.
- `-Dnetworkaddress.cache.negative.ttl=0` also only sets a **system property** of the same name.
- Standard DNS TTLs must be configured in **security properties**.
- Verify using `Security.getProperty("networkaddress.cache.ttl")`, not just by looking at `System.getProperties()`, JVM flags, or environment variable files.

**One easily confused exception:** older JDK versions/implementations had `sun.net.inetaddr.ttl` and `sun.net.inetaddr.negative.ttl`, which are **private implementation-specific system properties**. They are **not** standard API/security properties; their behavior and precedence may vary by JDK. Do not treat that private mechanism as portable deployment documentation, especially when writing Java 17+ modules.

## 6. Setting It Properly in the Runtime `java.security` File

Modern JDKs typically read security properties from:

```text
$JAVA_HOME/conf/security/java.security
```

On Windows, the corresponding path is typically:

```text
%JAVA_HOME%\conf\security\java.security
```

The configuration lines can be:

```properties
# Cache successful lookups for up to 30 seconds (application-chosen value)
networkaddress.cache.ttl=30

# Cache failed lookups for up to 5 seconds (application-chosen value)
networkaddress.cache.negative.ttl=5
```

`30` and `5` here are **example configuration values**, not a claim about the default of every Java 17 runtime. If a property is **commented out** with `#`, `Security.getProperty(key)` may return `null`; the cache implementation can still use its own default.

You should not edit the shared system JDK file directly without proper permissions and change-management processes:
- A modification can affect **every application** running on the same JDK installation.
- JDK updates can replace/overwrite the file.
- The production container image/JRE may not use the `JAVA_HOME` that your shell sees.
- Multiple `java` runtimes may exist on the same machine, so you need to check the exact `java.home` path in the process.
- It is better to use an **application-specific security overlay file**, configured in the startup script/deployment manifest and tested.

## 7. Security Overlay File via `-Djava.security.properties`

A seemingly paradoxical point: to set a DNS security property, you can use **a separate system property** as the **path to a security configuration file**:

```bash
java -Djava.security.properties=custom.security Main
```

This is the **correct** approach: `java.security.properties` is the name of a **launcher system property** that tells the JVM to load an additional file containing security properties; it is completely different from `-Dnetworkaddress.cache.ttl=30`.

Create `custom.security`:

```properties
networkaddress.cache.ttl=30
networkaddress.cache.negative.ttl=5
```

The Java SE 17 security guide distinguishes:
- `-Djava.security.properties=<URL>` with **a single equals sign after the property name**: loads an additional security file alongside the master configuration; keys specified in the overlay can override the corresponding values.
- `-Djava.security.properties==<URL>` with **two equals signs after the property name**: **replaces the entire master security properties** with the specified file. **Do not use this carelessly** because it can drop other security defaults/providers/policies.

In this example, we only need **single equals**. There is no need (and it is inadvisable) to replace the entire JDK security file just to adjust two TTL values.

When using this in Docker/CI, mount/copy the security overlay file properly into the container image, provide a path that exists when the JVM starts, and check file permissions. A nonexistent filename can prevent the configuration from loading as intended; always inspect the actual security property value.

## 8. `Security.setProperty`: Callable, but Not a Guaranteed “Cache Reload”

Java provides:

```java
import java.security.Security;

Security.setProperty("networkaddress.cache.ttl", "30");
String configured = Security.getProperty("networkaddress.cache.ttl");
```

This is a **code snippet**, not a file with `main`. The code mutates the security property in the **current JVM process**, but:
- This is a **global** value, not per-thread/per-HttpClient/per-tenant.
- Many security settings are read once or cached by subsystems during initialization. The API does not guarantee that changing the value **after** name resolution has already occurred will invalidate the existing cache.
- Changing the policy does **not** clear existing positive/negative cache entries or open TCP connections under any standard contract you can rely on.
- For production code, prefer setting it **at launch time**, restarting the process when changing it, and verifying on the exact JDK being run.

Distinguish between:
- `Security.getProperty(key) == "30"`: the security namespace currently records the string `"30"`.
- **Effective runtime address-cache behavior**: must be verified empirically under controlled conditions (it may already have been fixed by the JVM before the program changed the property).

**Do not** build an HTTP endpoint that allows users to arbitrarily call `Security.setProperty`; that mutates global security config and can cause unpredictable behavior across requests.

## 9. Java 17+ Demo #1: Proving the Two Namespaces Are Independent

The first example intentionally sets **two different values** for the same key name in the two namespaces. To stay safe, it uses only a standalone test JVM and calls `InetAddress` with a **numeric loopback**; the program does **not** perform Internet DNS queries.

Save the file **`DnsNamespaceDemo.java`**:

```java
import java.net.InetAddress;
import java.security.Security;

public class DnsNamespaceDemo {
    public static void main(String[] args) throws Exception {
        String positive = "networkaddress.cache.ttl";
        String negative = "networkaddress.cache.negative.ttl";
        System.setProperty(positive, "900");
        System.setProperty(negative, "900");
        Security.setProperty(positive, "2");
        Security.setProperty(negative, "0");

        System.out.println("security-positive=" + Security.getProperty(positive));
        System.out.println("system-positive=" + System.getProperty(positive));
        System.out.println("security-negative=" + Security.getProperty(negative));
        System.out.println("system-negative=" + System.getProperty(negative));
        System.out.println("namespaces-independent=" +
                !Security.getProperty(positive).equals(System.getProperty(positive)));
        System.out.println("loopback=" +
                InetAddress.getByName("127.0.0.1").isLoopbackAddress());
    }
}
```

Commands on JDK 17 or later:

```bash
javac DnsNamespaceDemo.java
java DnsNamespaceDemo
```

Verified output compiled/run with `javac --release 17`:

```text
security-positive=2
system-positive=900
security-negative=0
system-negative=900
namespaces-independent=true
loopback=true
```

Meaning:
1. `Security.getProperty(positive)` and `System.getProperty(positive)` both take the same string name but **return two different values**.
2. Both positive and negative TTL keys are shown to belong to a separate namespace from system properties.
3. `loopback=true` is a check on the IP literal `127.0.0.1`, **not a DNS cache timing measurement**. A numeric IP literal requires no public DNS query.
4. The `2`/`0` values in the security namespace **do not prove** that the `InetAddress` subsystem picked up the policy dynamically, because this test only verifies the property-management APIs.

To see the **actual** effect of TTL on name resolution, we need a test environment with a mutable name source, such as `jdk.net.hosts.file` in the next example.

## 10. `jdk.net.hosts.file`: A Normal System Property, Used in Its Proper Role

Java 17 provides the `jdk.net.hosts.file` system property for specifying a **custom hosts file** during name resolution, which is useful for **tests**. For comparison:

```bash
java -Djdk.net.hosts.file=demo.hosts App
```

This is a **real system property**, passed via `-D` at launch. The file content has a hosts-file format:

```text
127.0.0.2 sample.invalid
127.0.0.3 another.invalid
```

It is **not** a DNS TTL security property. It replaces the **hostname → address mapping source** for Java name resolution in a test environment. Applications that need real name service in production should not configure an arbitrary test hosts file.

Benefits of a dedicated file:
- No need to edit `/etc/hosts` or the Windows hosts file.
- No need to set up an authoritative DNS server.
- No public DNS usage, avoiding nondeterministic results or query spam risk.
- Local mappings can be changed directly inside the program to observe positive/negative cache TTL.
- Each run is in a **fresh JVM process**, free of cache from previous experiments.

**Note:** `jdk.net.hosts.file` is a name-service input mechanism, whereas `networkaddress.cache.ttl` is the **cache** TTL. The two must be configured in **two different namespaces**.

## 11. Two Security Config Files for a Controlled Comparison

Create **`ttl-zero.security`**:

```properties
networkaddress.cache.ttl=0
networkaddress.cache.negative.ttl=0
```

Create **`ttl-long.security`**:

```properties
networkaddress.cache.ttl=60
networkaddress.cache.negative.ttl=0
```

With `ttl-zero.security`, the positive cache does not retain results; with `ttl-long.security`, successful results can be retained for 60 seconds. Negative TTL is set to `0` in both files so that **positive cache testing is not affected by negative caching**.

These are **configs for a test JVM**, not a recommendation to use `TTL=0` in production. Disabling the cache can increase resolver traffic, latency, and the risk of DNS hiccups turning into widespread failures.

Both files will be loaded using:

```text
-Djava.security.properties=ttl-zero.security
-Djava.security.properties=ttl-long.security
```

Use **one file per JVM launch**, do not pass both files simultaneously for the same experiment.

## 12. Java 17+ Demo #2: Positive TTL with a Changing Hosts File

This program makes a controlled change in the `demo.hosts` file you specify:
1. Writes `127.0.0.2 sample.invalid`.
2. Resolves `sample.invalid` with `InetAddress.getByName`; receives `127.0.0.2`.
3. Overwrites the hosts file with `127.0.0.3 sample.invalid`.
4. Resolves the same hostname once more.
5. Prints the security TTL, both IPs, and the `changed` flag.

If positive TTL = `0`, **the JDK does not retain the positive result** and the second lookup can see the new file. If TTL = `60` and this happens immediately in the same JVM, the second lookup is served from the positive cache and continues to return the old IP.

Save the exact file **`DnsHostsFileCacheDemo.java`**:

```java
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Security;

public class DnsHostsFileCacheDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Provide hosts file path");
        }
        Path hosts = Path.of(args[0]);
        String hostname = "sample.invalid";
        Files.writeString(hosts,
                "127.0.0.2 " + hostname + "\n", StandardCharsets.UTF_8);
        String first = InetAddress.getByName(hostname).getHostAddress();

        Files.writeString(hosts,
                "127.0.0.3 " + hostname + "\n", StandardCharsets.UTF_8);
        String second = InetAddress.getByName(hostname).getHostAddress();

        System.out.println("security-ttl=" +
                Security.getProperty("networkaddress.cache.ttl"));
        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("changed=" + !first.equals(second));
    }
}
```

The program:
- Does not use `new Socket` or send HTTP requests; it only performs local name resolution.
- The `demo.hosts` file is a **writable test resource**, so run it in a dedicated test directory, not pointing at important configuration files.
- The hostname `sample.invalid` is a test name and is resolved only from the specified file.
- Every run **rewrites the hosts file from scratch**, so output does not depend on previous run order.
- All measured results depend on the JDK 17 provider and the test environment's filesystem; do not assume custom name service providers react identically.

## 13. Running Positive TTL 0 and 60

Place the following files in **the same test directory**:
- `DnsHostsFileCacheDemo.java`
- `ttl-zero.security`
- `ttl-long.security`

Compile:

```bash
javac DnsHostsFileCacheDemo.java
```

Run with positive TTL equal to 0:

```bash
java -Djava.security.properties=ttl-zero.security -Djdk.net.hosts.file=demo.hosts DnsHostsFileCacheDemo demo.hosts
```

Verified output:

```text
security-ttl=0
first=127.0.0.2
second=127.0.0.3
changed=true
```

Run again in a **fresh JVM process** with TTL 60:

```bash
java -Djava.security.properties=ttl-long.security -Djdk.net.hosts.file=demo.hosts DnsHostsFileCacheDemo demo.hosts
```

Verified output:

```text
security-ttl=60
first=127.0.0.2
second=127.0.0.2
changed=false
```

Explanation:
- `-Djava.security.properties=ttl-zero.security` or `ttl-long.security` is a **security config overlay file**; the JVM loads the exact declared TTL.
- `-Djdk.net.hosts.file=demo.hosts` is a **system property** telling Java's resolver to read a custom hosts file.
- Within the same process, the program modifies the mapping between two lookups.
- TTL=0 prevents the Java cache from retaining the name resolution result for the second lookup, so `127.0.0.3` is observed.
- TTL=60 retains the positive cache entry for hostname `sample.invalid`, so the next lookup still sees `127.0.0.2`.

**This is a hosts-file experiment, not a test of changing Internet DNS records.** It isolates the effect of the JVM cache and produces reproducible output in the tested JDK 17 environment.

## 14. Crucial Control Experiment: Direct `-D` Does Not Beat Security Config

A program can simultaneously have:
- Positive security TTL = `60` from `ttl-long.security`.
- Ordinary system property `networkaddress.cache.ttl=0` from `-Dnetworkaddress.cache.ttl=0`.

Command:

```bash
java -Djava.security.properties=ttl-long.security -Dnetworkaddress.cache.ttl=0 -Djdk.net.hosts.file=demo.hosts DnsHostsFileCacheDemo demo.hosts
```

Verified output on JDK 17:

```text
security-ttl=60
first=127.0.0.2
second=127.0.0.2
changed=false
```

Notable point: even though the command includes `-Dnetworkaddress.cache.ttl=0`, the second lookup **still uses the security TTL value 60**. This clearly illustrates the nature of **two non-equivalent namespaces**. The system property value does not override the value from security properties.

Do not treat this output as a claim that every environment with an OS hosts file or a custom resolver caches identically; it verifies the **standard mechanism and JDK behavior in a local test setup**. Any runtime upgrade should re-run the relevant regression tests.

## 15. Negative DNS Cache: Why Does a Newly Created Name Still Throw `UnknownHostException`?

The **negative cache** retains **failed** name lookup results for a period of time. The documented Java 17 default is about 10 seconds:

```text
t=0:  lookup new-service.invalid -> UnknownHostException
      JVM may retain the failed result

t=2:  service now has a name record in the name service

t=3:  look up the exact same hostname again
      if negative TTL has not expired -> may still throw UnknownHostException

t>=10: lookup after TTL expires has a chance to query the name service
       but may still fail due to other resolver layers
```

Setting `networkaddress.cache.negative.ttl=0` keeps Java from retaining **negative results** in the JVM cache, but does not guarantee public DNS immediately sees the new record: authoritative zones, recursive resolvers, OS caches, network splits, and firewalls still have an effect.

**Do not** set negative TTL too long or forever just to reduce DNS query counts. For applications using service discovery/auto-scaling, retaining `UnknownHostException` for too long can keep newly deployed services undiscovered.

## 16. Java 17+ Demo #3: Verifying Negative TTL

This example uses **the same local hosts file mechanism** and does the opposite of the positive demo:
1. The hosts file is initially empty (only a comment).
2. Looking up `missing.invalid` fails.
3. The program adds `127.0.0.4 missing.invalid` to the hosts file.
4. Looks up the hostname again and prints the results.

Save the file **`DnsNegativeCacheDemo.java`**:

```java
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Security;

public class DnsNegativeCacheDemo {
    private static String lookup(String hostname) {
        try {
            return InetAddress.getByName(hostname).getHostAddress();
        } catch (UnknownHostException ignored) {
            return "UNKNOWN";
        }
    }

    public static void main(String[] args) throws Exception {
        Path hosts = Path.of(args[0]);
        String name = "missing.invalid";
        Files.writeString(hosts, "# initially empty\n",
                StandardCharsets.UTF_8);
        String first = lookup(name);
        Files.writeString(hosts, "127.0.0.4 " + name + "\n",
                StandardCharsets.UTF_8);
        String second = lookup(name);
        System.out.println("negative-ttl=" +
                Security.getProperty("networkaddress.cache.negative.ttl"));
        System.out.println("first=" + first);
        System.out.println("second=" + second);
    }
}
```

The `lookup` method converts `UnknownHostException` into a readable string **only for demo purposes**; in production you should typically propagate/record the error type and apply a retry policy, rather than treating `"UNKNOWN"` as an actual IP.

Create **`neg-zero.security`**:

```properties
networkaddress.cache.ttl=0
networkaddress.cache.negative.ttl=0
```

Create **`neg-sixty.security`**:

```properties
networkaddress.cache.ttl=0
networkaddress.cache.negative.ttl=60
```

Positive TTL is kept at `0` so the test focuses on **negative results**. Do not use the JDK's global security file; use only an overlay dedicated to the demo JVM.

## 17. Running Negative TTL and Comparing Output

Compile:

```bash
javac DnsNegativeCacheDemo.java
```

Test with negative TTL `0`:

```bash
java -Djava.security.properties=neg-zero.security -Djdk.net.hosts.file=demo.hosts DnsNegativeCacheDemo demo.hosts
```

Verified output:

```text
negative-ttl=0
first=UNKNOWN
second=127.0.0.4
```

Test with negative TTL `60` in a **fresh JVM process**:

```bash
java -Djava.security.properties=neg-sixty.security -Djdk.net.hosts.file=demo.hosts DnsNegativeCacheDemo demo.hosts
```

Verified output:

```text
negative-ttl=60
first=UNKNOWN
second=UNKNOWN
```

Explanation:
- On the first lookup, the hosts file does not yet contain `missing.invalid`, so the lookup throws `UnknownHostException`, printed as `UNKNOWN`.
- The file is then updated immediately inside the program.
- When negative TTL = `0`, the next lookup can re-query the hosts file and receives `127.0.0.4`.
- When negative TTL = `60`, the JVM retains the negative cache entry from the first lookup, so the next lookup still reports unknown host, even though the new file already contains the mapping.

**Conclusion:** The cache does not only retain old IPs; it can also retain the **conclusion “hostname does not exist / cannot be resolved”**. Therefore, deploying a new service can fail for a while even after the DNS/hosts source has been updated.

## 18. What the Examples Proved — and Did Not Prove

| Experiment | What Was Verified | What Must Not Be Concluded |
| --- | --- | --- |
| `DnsNamespaceDemo` | `Security` and `System` hold two independent values for the same key | Dynamic `Security.setProperty` always changes effective `InetAddress` caching |
| Positive TTL 0 vs 60 | JDK 17 uses security TTL for lookups from a custom hosts file in a fresh process | Public DNS/OS resolvers always return fresh results immediately when TTL=0 |
| Security TTL 60 + system `-D` TTL 0 | `-Dnetworkaddress.cache.ttl=0` does not override security TTL | No other implementation-specific properties exist |
| Negative TTL 0 vs 60 | The JVM can cache name resolution failures and reuse them | All HTTP errors are caused by negative DNS caching |
| `jdk.net.hosts.file` | Mapping sources can be controlled in Java 17 tests without modifying the system | This is a general DNS configuration solution for production |

This helps avoid an uncontrolled test like “look up the same hostname 1000 times and compare latency” and concluding TTL equals a specific value. Latency also depends on OS cache, scheduler, network, JVM JIT, GC, and resolver. The demos use **IP/`UnknownHostException` results and a mutable data source**, giving them stronger explanatory power than millisecond numbers.

## 19. Why Changing a Security Property Mid-Run May Not Take Effect

An error-prone approach is:

```java
InetAddress.getByName("my-service.internal");
// The application has already performed name resolution.
Security.setProperty("networkaddress.cache.ttl", "0");
InetAddress.getByName("my-service.internal");
// There is no contract guaranteeing the second lookup bypasses the existing cache.
```

This is an **illustrative code snippet**, without imports/class, and the hostname is just an example.

Reasons:
1. Many security/runtime configurations may be **read and stored at subsystem initialization time**.
2. Lookup results already in the cache may have **precomputed expiry timestamps**; changing the property string does not necessarily invalidate entries.
3. `Security.setProperty` updates the **registry**; there is no standard public `InetAddress.clearDnsCache()` API in Java 17.
4. HTTP clients/sockets may already have open **TCP connections** to the old IP, regardless of what a new name resolution would return.

A more reliable approach: set TTL in a security file before startup, **start a fresh JVM process**, and test/observe behavior. When rolling out config in Kubernetes or a server deployment, restart/recreate pods/instances per operations policy; do not expect editing a file on disk to update a running JVM automatically.

## 20. Defaults and `SecurityManager` in Java 17

The Java 17 `InetAddress` Javadoc states:
- When a **SecurityManager is installed**, positive hostname resolution is cached **forever** by default to reduce DNS spoofing risk.
- When **no SecurityManager is installed**, the default positive TTL is **implementation-dependent**; the JDK does not guarantee the same number of seconds across all runtimes/vendors.
- The negative lookup cache has a documented default of **10 seconds**.

Therefore, a check like:

```java
String value = Security.getProperty("networkaddress.cache.ttl");
System.out.println(value);
```

may print `null` if the property is not declared in the security file, even though the runtime still has **default behavior**. `null` only means the key has no explicit value in the security registry at read time, not that “caching is off”.

Java 17 **deprecated `SecurityManager` for removal**; this is historical context for the API defaults, not a recommendation to install a `SecurityManager` to change DNS caching. Explicitly configuring TTL values in a security file makes operational intent much easier to verify than relying on defaults.

## 21. Three Different Caches: JVM, OS, and Recursive DNS

Do not treat positive TTL = 0 as magic that makes the server always reach the newest DNS IP:

```text
Java process                    OS resolver                   DNS infrastructure
  InetAddress JVM cache    ->  OS/hosts/name service    ->   recursive resolver
       own TTL                      own cache                   own cache
                                                                    │
                                                           authoritative zone
                                                                    │
                                                               DNS record TTL
```

For example:
- JVM TTL=0 makes Java query the name service more often.
- The OS or recursive resolver can still cache records according to its own policy.
- The authoritative server's DNS record TTL is not the value you set in `java.security`.
- A proxy or service mesh may resolve the hostname on behalf of the client; Java sees the proxy connection rather than resolving the origin directly.
- HTTP keep-alive/HTTP/2 can reuse a connection even after the JVM TTL expires.

Therefore, to verify failover after a DNS change:
1. Verify that the server/process received the right security TTL.
2. Verify hostname resolution inside the exact JVM/instance.
3. Check the OS/name service and DNS records.
4. Check connection reuse and client pool behavior.
5. Check network routing/firewalls/proxies.

**Do not** conclude that a connection to an old IP proves the TTL property is wrong. If the connection was created earlier, observe when the client **opens a new connection**, not just when it sends a new HTTP request.

## 22. JVM DNS Cache and HTTP Connection Pool Are Different

Suppose `HttpClient` holds an HTTP/2 connection to `api.example.com` at IP A. When DNS changes to IP B:
- The JVM cache may have already expired its TTL.
- A new request may **still use the open connection to A**.
- An actual new connection can trigger re-resolution according to JVM/provider behavior.
- A DNS lookup returning B does not force connection A to close immediately.
- Connection pooling, keep-alive, TLS sessions, proxy routing, and retry policies have their own lifecycles.

Similarly with `Socket`: once connected to an `InetSocketAddress` resolved to IP A, changing a security property does not alter the existing socket.

So when debugging “IP not updating,” distinguish between **lookup result**, **actual connected socket address**, **DNS cache entry**, and **HTTP connection reuse**. They are not the same metric.

## 23. Common Network System Properties for Comparison

The Java 17 networking docs also list properties that genuinely are **system properties**, settable with `-D`:

| Property | Type | Meaning |
| --- | --- | --- |
| `java.net.preferIPv4Stack` | System property | Prefer the IPv4 stack, checked at startup |
| `java.net.preferIPv6Addresses` | System property | IPv4/IPv6 preference order when both are available, typically read at startup |
| `jdk.net.hosts.file` | System property | Specify a custom hosts file for Java name resolution during tests |
| `http.proxyHost` / `http.proxyPort` | System properties | HTTP proxy for the corresponding handler |
| `java.security.properties` | System property **pointing to a security file** | Controls how security configuration is loaded |
| `networkaddress.cache.ttl` | **Security property** | Positive DNS TTL |
| `networkaddress.cache.negative.ttl` | **Security property** | Negative DNS TTL |

Do not confuse **the presence of `-D`** with “this setting is guaranteed to take effect at runtime.” Some system properties are **read exactly once at startup**, so calling `System.setProperty` after the network stack initializes may not change behavior. The Java Networking Properties documentation clearly distinguishes these groups.

Example:

```bash
java -Djava.net.preferIPv4Stack=true App
```

This is a standard system property per Java 17, fundamentally different from:

```bash
java -Dnetworkaddress.cache.ttl=0 App
```

The second line **does not configure standard TTL**.

## 24. Why You Should Not Use `sun.net.inetaddr.ttl` as a Portable Solution

Some blog posts recommend:

```bash
java -Dsun.net.inetaddr.ttl=30 App
java -Dsun.net.inetaddr.negative.ttl=0 App
```

These are **implementation-specific/private properties** that existed in Oracle/Sun JDKs and may still be supported by some builds. However:
- They are not standardized like `networkaddress.cache.ttl` in the Java SE 17 API.
- Their precedence relative to security properties can vary by implementation.
- They may change or be removed in a future JDK.
- Another vendor's JVM or a native-image packaged application may handle them differently.
- When moving to Java 17+ or upgrading runtimes, use the standard approach: `java.security` or `-Djava.security.properties=...`.

Do not “fix” a command by replacing `networkaddress.cache.ttl` with `sun.net.inetaddr.ttl` without a test plan and documenting it as a vendor dependency. Use a security file and the local regression tests in this lesson.

## 25. Tuning for Different Service Types

There is no single “best” TTL value for everything:

| Workload | Considerations |
| --- | --- |
| Backend service calling stable hosts | A finite positive TTL avoids excessive lookups while still allowing updates |
| Service discovery with frequent IP changes | Too long a positive TTL can prolong sticking to old IPs |
| Critical services needing failover | Combine DNS TTL, connection pools, retries, idempotency, and health checks |
| Clusters with many short-lived jobs | Each new JVM has a fresh cache; monitor startup resolution |
| Flaky DNS environments | Too short a TTL can increase error rate/latency; long negative TTL can retain failures |
| DNS provider returning multiple addresses | Resolver order, client retries, and address selection affect outcomes |
| Multi-tenant applications | Security TTL is **JVM-global**, not per tenant or per `HttpClient` |

An example policy could be positive TTL `30` seconds and negative TTL `5` seconds, **if measured and approved**. Do not treat those numbers as mandatory standards or defaults; test in staging with real DNS/connection behavior.

What to measure: DNS lookup success/failure rate, p95 latency, request connect errors, retry/reconnect count, connection pool reuse, actual socket addresses, and recovery time after DNS failover.

## 26. Security Risks: Stale IPs and DNS Rebinding

Long TTL:
- Can retain a **changed** mapping and prolong sending traffic to the old destination.
- If the old IP is reassigned to another service, the impact depends on network/TLS/certificate/service-identity design.
- Does not by itself guarantee protection against DNS spoofing; it is only one component of the system.

Too short a TTL:
- Increases resolver call frequency, load, and exposure to DNS failures.
- Continuously puts the application through dynamic resolution paths, requiring trusted DNS sources.
- **Does not prevent SSRF** merely by disabling the cache.

For URLs from untrusted sources, checking with `InetAddress.getAllByName` and then letting an HTTP client resolve again can lead to **DNS rebinding / time-of-check-to-time-of-use**. Adding cache TTL is not sufficient protection. You need host/scheme/port allowlists, protection on the actual connected address, egress firewalls, blocking link-local/metadata endpoints when disallowed, TLS hostname validation, and redirect policies.

**Do not** tie DNS cache TTL to allowing token forwarding to a new IP/host. Authentication and authorization must still verify service identity/audience.

## 27. Observability and Troubleshooting When Old IPs Are Still Used

Suggested workflow, from least invasive to deepest:

1. **Confirm the actual running JVM:** `java -version`, `java.home`, container image/runtime path, app process, and JDK vendor.
2. **Read the right namespace:** `Security.getProperty("networkaddress.cache.ttl")` and `Security.getProperty("networkaddress.cache.negative.ttl")`.
3. **Check the system namespace separately:** `System.getProperty(...)` only to detect misplaced `-D` settings.
4. **Inspect the active security files:** master `conf/security/java.security` and overlay `java.security.properties`, file permissions, and startup args.
5. **Confirm startup order:** if a file was just edited without restarting the JVM, do not expect the setting to change immediately.
6. **Observe name resolution:** results from `InetAddress.getAllByName` on the real JVM, per hostname, avoiding DNS spam.
7. **Observe the remote socket address** when a connection is actually opened, distinguishing it from the DNS lookup result.
8. **Check OS/recursive DNS caches**, authoritative records, and proxy/service mesh changes.
9. **Check negative cache:** did the hostname fail before the record appeared?
10. **Run a regression test in an isolated environment** with `jdk.net.hosts.file` + security config and a fresh process to prove JVM policy.
11. **Do not clear internal caches via reflection/hacks** into `java.net.InetAddress`; there is no standard public Java 17 `clearDnsCache`.
12. **Monitor side effects** when retrying network operations, especially `POST`, to avoid business-logic errors.

### Namespace Check Snippet (Code Fragment)

```java
String key = "networkaddress.cache.ttl";
String fromSecurity = Security.getProperty(key);
String fromSystem = System.getProperty(key);
System.out.println("Security property = " + fromSecurity);
System.out.println("System property   = " + fromSystem);
```

This is a **code fragment**, requiring `import java.security.Security`; output depends on the current runtime and **must not** be assumed to have a hardcoded default. If `fromSecurity == null`, the application may still be using the JDK's default TTL.

### Debugging Security Property Initialization

The Java 17 security guide describes these tools:
- `-Djava.security.debug=properties` to log loading of security properties, initial values, and includes. Use with care because debug logs can contain sensitive configuration data.
- `-XshowSettings:security` to print an overview of security settings when the JDK supports this option. Check the runtime version before using.
- Java Flight Recorder event `jdk.InitialSecurityProperty` can help inspect startup configuration on supported JDKs.

**Do not** log raw credentials/keystores/secrets in a bug report. DNS TTL should not require leaving full security subsystem debugging enabled long-term in production.

## 28. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Using `-Dnetworkaddress.cache.ttl=0` and assuming the JVM disabled the cache | This is a **system** property, not the TTL security property | Set it in a security file and check `Security.getProperty` |
| Reading only `System.getProperty` | May show a user-defined value that is not the actual TTL | Read both namespaces and distinguish them |
| Assuming default positive TTL is always 30s | Java 17 states it is implementation-dependent without SecurityManager | Explicitly declare TTL if needed |
| Assuming negative TTL always equals positive TTL | They are two separate policies | Set `networkaddress.cache.negative.ttl` separately |
| Assuming `-1` means cache disabled | `-1` means cache forever | Use `0` if you want no caching |
| Assuming `0` forces the OS DNS cache to expire | Only affects the JVM cache | Check other resolver layers |
| Editing `java.security` without restarting the JVM | Settings may already be loaded/cached | Restart/recreate the process with verified config |
| Calling `Security.setProperty` and expecting entries to flush | No public invalidation guarantee | Use startup configuration and test |
| Using `-Djava.security.properties==...` just to change 1 key | Replaces the entire master security config | Use single-equals overlay |
| Treating `sun.net.inetaddr.ttl` as Java SE standard | Private/vendor-specific | Prefer `networkaddress.cache.ttl` in a security file |
| Using `jdk.net.hosts.file` for production DNS service discovery | It is a mapping file intended for tests | Use DNS/name service suited to your architecture |
| Running demos that edit the system hosts file | Can affect multiple processes | Use a JVM-specific test file |
| Benchmarking with single-lookup timing | Depends on OS cache/network/JIT | Test controlled mappings/negative results |
| Thinking TTL expiration closes old HTTP sockets | Connection lifetime differs from DNS cache | Check connection pooling/lifecycle |
| Using TTL=0 to “prevent SSRF” | DNS rebinding and egress remain dangerous | Validate destination + network-level policy |
| Logging full host/URL/token on every resolution | Risks leaking private data | Log necessary metadata, redact secrets |
| Using TTL forever for dynamic services | Can retain stale IPs/failures for a very long time | Choose a finite TTL and failover strategy |
| Setting the property on a different JVM than the target process | Does not affect other JVMs | Configure each runtime/container/pod |
| Forgetting negative cache when deploying a new hostname | `UnknownHostException` may be retained | Check negative TTL and process state |

## 29. Recommended Test Matrix

| Case | Expected Result |
| --- | --- |
| `System.setProperty` with same key then `Security.getProperty` | Two independent namespaces |
| Positive TTL=0, hosts file changes IP | Re-resolving sees the new IP in local JDK test |
| Positive TTL=60, hosts file changes IP immediately | Re-resolving still sees the old cached IP |
| Positive TTL=60 + `-Dnetworkaddress.cache.ttl=0` | Direct `-D` does **not** override security TTL |
| Negative TTL=0, hostname initially missing then added | Subsequent lookup can resolve |
| Negative TTL=60, hostname initially missing then added immediately | Subsequent lookup can still throw `UnknownHostException` |
| Single-equals security file overlay | Specifies and loads the keys under test |
| `Security.getProperty` key is null | Do not assume “cache off”; check implementation default |
| Config changed after startup | Do not promise cache invalidation unless verified |
| Java HTTP connection still uses old IP after DNS change | Check keep-alive/pool instead of concluding TTL is wrong |
| DNS proxy / service mesh present | Identify who resolves the hostname last |
| DNS rebinding between validate and connect | Egress/connection policy still blocks disallowed addresses |
| Public DNS outage | DNS queries/latency/retries are bounded, monitoring in place |
| JDK upgrade | Re-run positive/negative TTL tests and config reads |

The local tests from sections 9–17 do **not** require the Internet; they are well-suited to keep as smoke/regression tests when upgrading JDK/container images. For production, add canary tests that verify real service failover, without arbitrarily editing global DNS for ad-hoc experiments.

## 30. Self-Check Questions

**Question 1.** Is `networkaddress.cache.ttl` a system property or a security property?  
**Answer:** A **security property** in Java SE 17.

**Question 2.** How do you read the configured value in the security registry?  
**Answer:** `Security.getProperty("networkaddress.cache.ttl")`, not just `System.getProperty`.

**Question 3.** Does `-Dnetworkaddress.cache.ttl=0` disable the positive JVM DNS cache per the standard API?  
**Answer:** No; it creates an ordinary system property and does not set the security TTL.

**Question 4.** What is `-Djava.security.properties=ttl-zero.security`?  
**Answer:** A **system property specifying a file path** for the JVM to load security properties from; not a direct DNS TTL system setting.

**Question 5.** What does positive TTL `-1` mean?  
**Answer:** Cache forever per policy, not disabled.

**Question 6.** What is the documented Java 17 default for negative TTL?  
**Answer:** About **10 seconds**.

**Question 7.** Is the default positive TTL always 30 seconds?  
**Answer:** No. Without a `SecurityManager`, Java 17 describes the default as implementation-dependent.

**Question 8.** Does `Security.setProperty` after a DNS lookup guarantee the old cache disappears?  
**Answer:** No guarantee. Prefer startup configuration and use a fresh process for testing.

**Question 9.** Why might `HttpClient` still use an old IP even with TTL=0?  
**Answer:** It may be reusing an already-open TCP connection, or the OS/recursive resolver still holds the result.

**Question 10.** What kind of property is `jdk.net.hosts.file`?  
**Answer:** A system property used to specify a custom hosts file for Java name resolution in tests.

**Question 11.** How do positive cache and negative cache differ?  
**Answer:** Positive caches resolved IPs; negative caches failed results such as `UnknownHostException`.

**Question 12.** Should you use a double-equals security file just to set two TTL keys?  
**Answer:** No. Double equals replaces the entire master security configuration; a single-equals overlay is the appropriate approach.

**Question 13.** Does a `null` security property value mean no cache?  
**Answer:** No. The JVM may be applying an implementation default if the property is undeclared.

**Question 14.** Does DNS TTL=0 guarantee protection against DNS rebinding/SSRF?  
**Answer:** No. You need destination, scheme, host, and network egress constraints plus time-of-check/time-of-use protection.

**Question 15.** Why was Internet DNS not needed in the three test programs?  
**Answer:** `jdk.net.hosts.file` lets you provide a custom name mapping file; the program controls the mapping before and after lookup and measures the JVM TTL's effect.

## 31. Summary of Proper Configuration and Operations

**To control the JVM DNS cache:** set `networkaddress.cache.ttl` and `networkaddress.cache.negative.ttl` as **Java security properties** before JVM startup, via `$JAVA_HOME/conf/security/java.security` or an **overlay file** loaded with `-Djava.security.properties=path/to/file`. Inspect with `Security.getProperty(...)`, not ordinary `System.getProperty(...)`.

**To verify behavior:** run the program in a fresh JVM process, use a local `jdk.net.hosts.file` to change mappings, and compare TTL=0/60 and negative lookup cases. Do not modify public DNS or the system hosts file for unit tests.

**To resolve production “stale IP” issues:** analyze the JVM address cache, OS/recursive DNS cache, connection pool, proxy/service mesh, and TCP connection lifetime separately. Choose a TTL suited to throughput and failover goals, monitor errors/latency, and restart/redeploy when changing startup security settings.

**One sentence to remember:** **`-Dnetworkaddress.cache.ttl=...` is not the standard way to configure DNS TTL in Java 17; `java.security.Security` and `java.security` are the right namespace.**

## 32. References

- Oracle Java SE 17 — `Networking Properties` (Address Cache: security properties, do not use direct `-D`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html
- Oracle Java SE 17 — `InetAddress` (caching successful/unsuccessful lookups and defaults): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html
- Oracle Java SE 17 — `Java Networking` (security address cache properties, hosts file configuration): https://docs.oracle.com/en/java/javase/17/core/java-networking.html
- Oracle Java SE 17 — `The Security Properties File` (`java.security.properties` overlay, single/double equals, dynamic caveats): https://docs.oracle.com/en/java/javase/17/security/security-properties-file.html
- Oracle Java SE 17 — `java.security.Security` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Security.html
- Oracle Java SE 17 — `java.lang.System` `getProperty`/`setProperty`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
- Oracle Java SE 17 — `HttpClient` (HTTP connection/reuse and networking context): https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 21 — `Networking Properties` (stale TTL section appearing in newer JDK docs; **do not assume `networkaddress.cache.stale.ttl` as a Java 17 API**): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/doc-files/net-properties.html
- RFC 6761 — Special-Use Domain Names, including `.invalid` for examples: https://www.rfc-editor.org/rfc/rfc6761
