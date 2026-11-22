# InetAddressResolverProvider and Resolver Replacement Mechanisms by Supported Java Version

`InetAddressResolverProvider` is the **standard SPI (Service Provider Interface) since Java 18, per JEP 418**, allowing applications to provide a hostname and IP address resolver for `java.net.InetAddress` to use at **JVM-wide scope**. Prior to Java 18, there was no equivalent public SPI to replace the global `InetAddress` resolver. On Java 9–17, you can configure a custom `hosts` file via `jdk.net.hosts.file` when static name mapping is needed; on Java 8, you typically rely on OS configuration or handle mapping within the application itself.

**Key takeaway:** this is a way to replace *name/address resolution* for `InetAddress`, not an API to set a DNS server per HTTP request; nor does it mean every networking library or DNS client will automatically use this provider.

## 1. Which step is being replaced?

An application calls `InetAddress.getByName("service.example.test")` or `getAllByName(...)` to translate **hostname → one or more IPv4/IPv6 addresses** (forward lookup). The **IP → hostname** direction is reverse lookup, for example when calling `getCanonicalHostName()`.

~~~text
Application → InetAddress → lookup cache → selected resolver
                                         ├─ built-in resolver → OS configuration, hosts, DNS, ...
                                         └─ custom InetAddressResolver → application rules / custom service
~~~

`InetAddress` is not merely a pure DNS client: the default resolver may combine `hosts`, OS name-service configuration, and DNS or other naming mechanisms. Even when DNS returns an address, TCP connection, HTTPS, TLS certificate verification, and proxy policies remain separate steps.

Two calls to distinguish:

- `InetAddress.getByName(host)`: requests name resolution; may go through the resolver and the cache.
- `InetAddress.getByAddress(host, bytes)`: **constructs an InetAddress object from known IP bytes**, without querying DNS to find the IP. This is the safe way to construct results inside a custom resolver, avoiding calling back into `getByName`.

## 2. Support matrix by version

| Java Version | Replace `InetAddress` resolver via standard SPI? | Supported mechanisms to consider |
|---|---|---|
| **Java 8 and older** | **No** public `InetAddressResolverProvider` | Configure `hosts`/DNS at the OS level; map names in application logic or libraries if needed |
| **Java 9–17**, including Java 11/17 LTS | **No** such SPI | Uses system resolver by default; can set `-Djdk.net.hosts.file=...` to use a custom hosts file for `InetAddress` |
| **Java 18 and later**, including Java 21/25 LTS | **Yes**: `java.net.spi.InetAddressResolverProvider` and `InetAddressResolver` | Register a provider via `ServiceLoader` to replace the JVM-wide resolver; or use built-in/`jdk.net.hosts.file` for simple cases |

**Easy milestone to remember: Java 9 added `jdk.net.hosts.file`; Java 18 added the SPI (JEP 418).** Java 9 also removed the legacy internal name-service provider mechanism that had been documented in earlier JDK releases. Do not use examples with `sun.net.spi.nameservice.*` or `sun.net.spi.nameservice.provider.*` on an older JDK as a stable API solution for Java 17 or 21; those are not public Java SE APIs guaranteed to be supported.

If a project compiles with `--release 17` or runs on JDK 17, code importing `java.net.spi.InetAddressResolverProvider` will **fail to compile/run**. The SPI examples below require **JDK 18+ at both compile time and runtime**.

## 3. Mechanics of the SPI since Java 18

The SPI resides in the `java.base` module, package `java.net.spi`, with four main types:

| Type | Responsibility |
|---|---|
| `InetAddressResolverProvider` | **Factory** for the custom resolver; an abstract class requiring a concrete provider implementation with a no-arg constructor |
| `InetAddressResolver` | Interface defining `lookupByName` and `lookupByAddress` |
| `InetAddressResolver.LookupPolicy` | Describes the requested address family (IPv4/IPv6) and preference order |
| `InetAddressResolverProvider.Configuration` | Provides `builtinResolver()` to delegate normal resolution, and `lookupLocalHostName()` when the local host name is needed |

### Provider initialization and selection

1. Once the JVM is fully initialized and an `InetAddress` call needs resolution for the first time, the JDK searches for an `InetAddressResolverProvider` implementation via `ServiceLoader` **using the system class loader**.
2. If multiple providers are found, **the first provider found** is used; **the order is implementation-specific**, so you should not rely on provider names or JAR ordering.
3. The JDK invokes `provider.get(configuration)`; the returned `InetAddressResolver` object becomes the **JVM-wide resolver** for subsequent lookups.
4. If **no provider is found**, the JDK uses the **built-in resolver**.
5. If **a provider is found but initialization throws an error/exception**, the error is propagated to the caller that triggered the lookup; **do not expect automatic fallback to built-in**. If a specific hostname is not handled by the custom resolver, your own code must explicitly delegate via `configuration.builtinResolver()`.
6. Lookups occurring **before the VM is fully booted** may still use the built-in resolver according to JDK implementation notes.

The provider is normally selected **once per JVM lifecycle**, not re-selected on every request. Therefore, changing the classpath, adding a service file, or modifying the provider after a lookup has already occurred will not "hot swap" the current process's resolver; use a fresh JVM to test.

### Two required methods and lookup policy

~~~java
Stream<InetAddress> lookupByName(
    String host,
    InetAddressResolver.LookupPolicy policy
) throws UnknownHostException;

String lookupByAddress(byte[] addr) throws UnknownHostException;
~~~

- `lookupByName` takes a **hostname** (not assumed to be a string-form IP address) and returns a `Stream<InetAddress>`. If no matching address is found, throw `UnknownHostException`.
- `lookupByAddress` takes **4 IPv4 bytes or 16 IPv6 bytes** in network byte order; returns the hostname or throws `UnknownHostException`.
- `LookupPolicy.characteristics()` is a bit mask: `IPV4`, `IPV6` indicate the address families to look up; `IPV4_FIRST` and `IPV6_FIRST` indicate the order when both are present. For example, if the policy only allows IPv6, a resolver that only stores IPv4 records **must not return IPv4**.
- With multiple addresses, a custom resolver must filter and order according to the policy. `IPV4_FIRST`/`IPV6_FIRST` are meaningful when both families are present; without a preference flag, follow system order.

## 4. Runnable example: override one internal name, delegate others to the default resolver

Goal: in a JVM using the provider, `service.example.test` resolves to **192.0.2.44** and reverse lookup returns this name. `192.0.2.0/24` is a documentation address range, **not a real Internet server**. Other names are delegated to the built-in resolver; the example generates no DNS traffic of its own and requires no Internet connection.

Project structure when running on the **classpath**:

~~~text
resolver-demo/
├── src/
│   └── demo/
│       ├── StaticResolverProvider.java
│       └── ResolverDemo.java
└── resources/
    └── META-INF/
        └── services/
            └── java.net.spi.InetAddressResolverProvider
~~~

### 4.1. Implementing the provider

Create `src/demo/StaticResolverProvider.java`:

~~~java
package demo;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.Arrays;
import java.util.stream.Stream;

public final class StaticResolverProvider extends InetAddressResolverProvider {
    private static final String HOST = "service.example.test";
    private static final byte[] IPV4 = {(byte) 192, 0, 2, 44};

    public StaticResolverProvider() {}

    @Override
    public String name() { return "static-demo"; }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        InetAddressResolver builtin = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, InetAddressResolver.LookupPolicy policy)
                    throws UnknownHostException {

                if (!HOST.equalsIgnoreCase(host)) {
                    return builtin.lookupByName(host, policy);
                }
                if ((policy.characteristics()
                        & InetAddressResolver.LookupPolicy.IPV4) == 0) {
                    throw new UnknownHostException("No IPv4 requested: " + host);
                }
                return Stream.of(InetAddress.getByAddress(HOST, IPV4.clone()));
            }

            @Override
            public String lookupByAddress(byte[] address)
                    throws UnknownHostException {
                if (Arrays.equals(address, IPV4)) {
                    return HOST;
                }
                return builtin.lookupByAddress(address);
            }
        };
    }
}
~~~

**Explanation of design decisions in the code:**

- `get(Configuration)` receives `builtinResolver()` and retains it for fallback. Do not call `InetAddress.getByName(...)` from `lookupByName`, because that call typically loops back into the newly installed resolver, causing **infinite recursion**.
- `InetAddress.getByAddress(HOST, IPV4.clone())` constructs the address from known bytes, **without performing a forward lookup**. The method may throw `UnknownHostException` if the address bytes are invalid.
- For hostnames other than the demo name, the example explicitly calls `builtin.lookupByName`. Without this fallback, a custom resolver that only knows one name could break all other lookups.
- For the demo host, only IPv4 is supported; if the policy does not request IPv4, report not found instead of returning the wrong family. Since there is only a single IP, the example does not need to handle IPv4/IPv6 list ordering.
- `lookupByAddress` supports reverse mapping of the assigned IP and delegates to built-in for other addresses. Reverse mapping does not automatically prove identity or security.
- The provider has a `public` no-arg constructor; initialization should be very lightweight, avoiding network lookups in the constructor, static initializer, or `get` to prevent class-loading cycles/deadlocks.

### 4.2. Registering with `ServiceLoader`

The contents of **`resources/META-INF/services/java.net.spi.InetAddressResolverProvider`** is a single line:

~~~text
demo.StaticResolverProvider
~~~

The **file** name is the fully qualified SPI name; the **content** is the fully qualified provider class name with package. Do not add `.java`, `.class`, parentheses, or the `InetAddressResolver` name instead of the provider. The file must be present on the **runtime classpath** (typically inside a JAR at `META-INF/services/...`), not just in the source directory.

### 4.3. Program calling `InetAddress`

Create `src/demo/ResolverDemo.java`:

~~~java
package demo;
import java.net.InetAddress;

public class ResolverDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("forward=" + InetAddress.getByName("service.example.test")
                .getHostAddress());
        byte[] ip = {(byte) 192, 0, 2, 44};
        System.out.println("reverse=" + InetAddress.getByAddress(ip)
                .getCanonicalHostName());
    }
}
~~~

From the `resolver-demo` directory, run on macOS/Linux with **JDK 18+**:

~~~bash
javac --release 18 -d out src/demo/StaticResolverProvider.java src/demo/ResolverDemo.java
mkdir -p out/META-INF/services
cp resources/META-INF/services/java.net.spi.InetAddressResolverProvider out/META-INF/services/
java -cp out demo.ResolverDemo
~~~

Verified output:

~~~text
forward=192.0.2.44
reverse=service.example.test
~~~

The code above was compiled with `javac --release 18` and tested on **OpenJDK 24**. The reverse test uses `getCanonicalHostName()`, which may require consistent forward/reverse name/IP verification: because the example provides **both consistent forward and reverse mappings**, it returns the defined name. If you only construct `InetAddress.getByAddress(HOST, IP)` and call `getHostName()`, you may simply get back the stored name without actually exercising the reverse resolver.

**On Windows PowerShell**, replace the two directory-creation/copy commands with:

~~~powershell
New-Item -ItemType Directory -Force out/META-INF/services
Copy-Item resources/META-INF/services/java.net.spi.InetAddressResolverProvider out/META-INF/services/
~~~

The two `javac` and `java` commands remain unchanged; be sure to run from the root directory of the example. If using a JAR, package the service file into the JAR and place that JAR on the system classpath.

### 4.4. Projects using the Java Platform Module System (JPMS)

If deploying the provider as a **named module**, use the `provides` directive in `module-info.java` instead of the classpath setup described above:

~~~java
module demo.resolver {
    provides java.net.spi.InetAddressResolverProvider
        with demo.StaticResolverProvider;
}
~~~

This is a **module declaration snippet**, not a standalone program. At runtime, the module must be resolved into the module graph (for example via `--module-path` and `--add-modules demo.resolver` configuration matching your packaging). Do not assume that merely placing a JAR on the module path is always enough for the provider to be discovered. Do not depend on another provider coming first in an arbitrary order.

## 5. Without the SPI: solutions for Java 9–17

Since **JDK 9**, the system property `jdk.net.hosts.file` specifies a custom hosts file for `InetAddress` host/IP mapping. This mechanism is suitable for **testing or finite static mappings**, does not replace a dynamic DNS resolver, does not provide per-request policies, and requires no Java provider code.

Example `hosts-demo.txt` file:

~~~text
192.0.2.44 service.example.test
~~~

Java 9+ example `ResolveHost.java`:

~~~java
import java.net.InetAddress;

public class ResolveHost {
    public static void main(String[] args) throws Exception {
        System.out.println(
            InetAddress.getByName("service.example.test").getHostAddress()
        );
    }
}
~~~

Compile/run with **JDK 9 or later**, including Java 11/17:

~~~bash
javac ResolveHost.java
java -Djdk.net.hosts.file=hosts-demo.txt ResolveHost
~~~

Output with the file above:

~~~text
192.0.2.44
~~~

**Limitations of a custom hosts file to understand:**

- This property was introduced in **JDK 9**; do not present it as a standard supported solution for Java 8.
- In a built-in-based configuration, when a custom file is specified, normal lookups obtain mappings from **that file**; do not treat it as an "override a few names and automatically query DNS for everything else" table. If the file lacks a required name, you may receive `UnknownHostException`.
- If the path points to a **non-existent** file, the JDK treats it as an empty file and lookups fail, rather than silently ignoring the setting and falling back to default DNS.
- `-D...` must be placed **before the main class name** (or in JVM startup configuration); use an absolute path when running from CI/containers to avoid working directory dependencies.
- It does not replace OS-wide DNS and does not force tools like `nslookup`/`dig` or specialized DNS clients to use the JVM's file.
- When testing independently, do not simultaneously install another SPI provider and attribute the result solely to `jdk.net.hosts.file`: the provider itself decides when to call `builtinResolver()`.

**Java 8:** you can configure the host/container so the default resolver picks up mappings from the system hosts file (path varies by OS), configure system DNS, or supply IPs at the application layer. There is no standard Java SE 8 switch equivalent to `InetAddressResolverProvider` to plug in a JVM-wide provider. Internal `sun.*` APIs and bootclasspath tricks are brittle across JDK upgrades.

## 6. Caching, lifecycle, and scope limits

### `InetAddress` caching

`InetAddress` caches both successful and failed lookups. Java has two relevant **security properties**:

- `networkaddress.cache.ttl`: TTL (in seconds) for successful results; `-1` means cache forever.
- `networkaddress.cache.negative.ttl`: TTL for failed results; `0` means no caching, `-1` means cache forever.

Default values and security conditions may vary by JDK/configuration; you should not assert a fixed positive TTL across all versions. These are **Java security properties**, not automatically equivalent to `-Dnetworkaddress.cache.ttl=...` on the command line. Configure them using the Java security properties mechanism supported by your JDK and verify on your target runtime.

A newly changed mapping might not appear due to **caching**, even when the provider is installed correctly. For simple tests, start a fresh JVM, use a new hostname, and avoid mixing stale/negative cache entries. If the resolver maintains its own cache, you must account for its cache as well.

### JVM-wide effect, but not network-wide

- The provider serves resolution flows invoked through `java.net.InetAddress`; it **does not modify OS DNS configuration**.
- Do not assume all HTTP libraries, database drivers, or DNS clients necessarily go through the SPI: code that uses its own resolver, pre-resolved IP addresses, proxies, or native APIs may take a different path.
- The provider **does not** automatically change DNS CNAME/A/AAAA resolution rules; if you want to query specific DNS records, you must implement it yourself or call an appropriate library inside the resolver.
- Spoofing hostname → IP can cause the application to connect to the wrong endpoint. HTTPS still enforces identity verification and SNI according to its own rules; changing the IP in the resolver does not disable certificate checks.
- Lookups may arrive from multiple threads; implementations must be **thread-safe**, use reasonable timeouts, and avoid unbounded blocking I/O. If the provider is packaged in a shared library, consider its impact on the entire process.
- The provider may not be invoked for IP literals like `192.0.2.44` or `::1`: these are already known address data, not necessarily hostnames requiring resolution.

## 7. Troubleshooting common scenarios

| Symptom | Check | Resolution |
|---|---|---|
| `javac` reports `InetAddressResolverProvider` not found | Are `java -version` / `javac -version` JDK 18+? Is `--release 17` being used? | Use JDK 18+ for the SPI; on 17 use a version-appropriate approach |
| Demo runs but host does not receive custom IP | Verify exact path `META-INF/services/java.net.spi.InetAddressResolverProvider`, class name, constructor, runtime classpath | Repackage the service file; run in a fresh JVM |
| Multiple providers present at runtime | Selection order is not guaranteed | Deploy only the intended provider; manage dependencies/JARs containing the SPI |
| Lookup suddenly causes `StackOverflowError` | Does the provider call `InetAddress.getByName` from `lookupByName`? | Return `getByAddress` for static IPs; use `builtinResolver()` for fallback |
| Querying IPv6 only but receiving IPv4 | Resolver ignores `LookupPolicy` | Filter by `IPV4`/`IPV6` and preserve ordering |
| Reverse lookup does not return expected hostname | Is `lookupByAddress` implemented? Does forward mapping match? | Return a consistent hostname and verify both directions |
| Hosts other than the custom name fail | Code does not delegate when host is unrecognized | Use `configuration.builtinResolver()` |
| Hosts/resolver updated but app still sees old IP | `InetAddress` cache, custom cache, or JVM already selected a provider earlier | Check TTL, restart the test JVM |
| Set `jdk.net.hosts.file` but other names all fail | File is missing names or path is wrong | Add the mappings or remove the flag to use the system resolver |
| `nslookup`/`dig` differs from `InetAddress` result | Tools use different mechanisms, or different caches/configs | Test directly with a Java program on the target JVM |

### Minimal debugging sequence

1. Print the JDK version used **at runtime**, not just the compiler or IDE environment variable.
2. Verify the service file is **inside the executable artifact** and the system loader can see the provider.
3. Test a custom hostname, such as `service.example.test`, with `InetAddress.getByName` in a **fresh JVM**.
4. If reverse mapping is present, test the IP → hostname direction separately; note the forward verification in `getCanonicalHostName`.
5. Test a non-custom host to confirm `builtinResolver()` falls back as intended.
6. Check caching, IPv4/IPv6 policy, and framework-specific resolvers if results still differ from expectations.

## 8. Choosing the right solution for the problem

| Need | Suitable approach |
|---|---|
| Testing a few static hostnames, Java 9–17 project | `jdk.net.hosts.file`; run a fresh JVM per case |
| Testing a few static hostnames, Java 8 | OS hosts file/configuration or application-layer mapping |
| Replace the entire resolver behind `InetAddress` with internal rules on Java 18+ | `InetAddressResolverProvider` and service registration, while defining a fallback |
| Only one HTTP client needs custom DNS, others unchanged | Check that HTTP client/library's own API and resolver; a JVM-wide SPI may be too broad |
| Application needs to query DNS records directly (MX, TXT, SRV...) | Use a dedicated DNS library or API; `InetAddressResolver` mainly serves hostname/IP and reverse lookups |
| Want to change the resolver while the program is running | The SPI does not provide public hot-swap; design a fixed resolver that reads dynamic internal configuration, minding caching and synchronization |

**Remember:** `InetAddressResolverProvider` is the mechanism to **replace `InetAddress`'s resolver via ServiceLoader since Java 18**, not a feature available in Java 17. In the provider, `lookupByName` and `lookupByAddress` handle both directions; `LookupPolicy` constrains address families; `Configuration.builtinResolver()` enables safe fallback; check caching and start a fresh JVM when testing.

## Official documentation

- [JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 18 – InetAddressResolverProvider](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html).
- [Java SE 18 – InetAddressResolver](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/spi/InetAddressResolver.html).
- [Java SE 18 – InetAddressResolver.LookupPolicy](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/spi/InetAddressResolver.LookupPolicy.html).
- [Java SE 18 – InetAddressResolverProvider.Configuration](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/spi/InetAddressResolverProvider.Configuration.html).
- [Java SE 18 – Networking properties and hosts file](https://docs.oracle.com/en/java/javase/18/core/java-networking.html).
- [JDK 9 Release Notes – introducing jdk.net.hosts.file](https://www.oracle.com/java/technologies/javase/9-relnotes.html).
- [Java SE 17 – InetAddress and caching](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html).