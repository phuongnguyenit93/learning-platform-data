# ProxySelector: Per-URI Proxy Selection and Handling `connectFailed` in Java 17

## 1. Scenario: One `HttpClient`, Different Connection Routes per URI

A Java application calls multiple HTTP APIs: an internal endpoint inside the corporate network, an external partner that must go through a proxy, and a public HTTP endpoint that needs to go through a different proxy. If you only configure **a single fixed proxy** or send every request directly, the application may take the wrong route, violate egress policy, or fail to connect.

`java.net.ProxySelector` is the **extension point for route-selection policy**. It answers the question:

> For this **target URI**, what is the recommended list of connection methods: an HTTP proxy, a SOCKS proxy (if supported by the client/protocol), or a direct connection?

With a custom `ProxySelector`, you can specify:

- URIs belonging to an internal domain allowed for direct access → `Proxy.NO_PROXY`.
- HTTPS URIs to a partner service → prefer proxy A, with proxy B as a backup in the list.
- Public HTTP URIs → use only proxy B.
- When a proxy is known to be unable to **establish a connection**, the `connectFailed(URI, SocketAddress, IOException)` method receives the notification so the policy can be updated for subsequent selections.

**Core distinction:** `select` returns **connection route recommendations**; it does not open sockets itself, send HTTP requests, perform authentication, or verify that a proxy is alive. `connectFailed` is a **notification of a failure to establish a connection to the proxy**, not a callback for every error HTTP response such as `404` or `502`.

This lesson is part of the **Proxies and HTTP Sessions** section, focusing on the `ProxySelector` contract in Java 17, URI-based selection, the meaning of the proxy list, failure notifications, and the difference between selection policy and an HTTP client's actual failover behavior.

## 2. Distinguishing `Proxy`, `ProxySelector`, and `HttpClient`

| Component | Java API | Responsibility |
|---|---|---|
| **Proxy endpoint** | `java.net.Proxy` | Describes **one** connection method: HTTP proxy, SOCKS proxy, or DIRECT |
| **Proxy address** | `java.net.SocketAddress`, usually `InetSocketAddress` | Host/IP and port **of the proxy**, distinct from the target URI's host/port |
| **Policy / selector** | `java.net.ProxySelector` | Selects a `Proxy` list by URI; receives `connectFailed` to learn when a proxy cannot be reached |
| **HTTP client** | `java.net.http.HttpClient` | Creates/connects HTTP/TLS, sends requests, receives responses; can be configured with a `ProxySelector` via its builder |
| **HTTP request** | `java.net.http.HttpRequest` | Method, URI, headers, body publisher, and request timeout |
| **Proxy authentication** | `java.net.Authenticator` and HTTP client policy | Supplies credentials for challenges when a proxy requires authentication; **separate** from proxy selection |
| **HTTP response** | `HttpResponse` | Status, headers, and body from an HTTP exchange; an error status does not mean `connectFailed` is called |

A `Proxy` value typically carries:

```java
// Illustrative snippet; java.net.* imports are assumed in context.
Proxy corpProxy = new Proxy(
        Proxy.Type.HTTP,
        InetSocketAddress.createUnresolved(
                "proxy.corp.example", 8080));

Proxy direct = Proxy.NO_PROXY;
```

`Proxy.NO_PROXY` represents a **direct connection**. For direct, `type()` returns `Proxy.Type.DIRECT` and `address()` is `null`. Do not cast `proxy.address()` to `InetSocketAddress` before checking `type()`.

A proxy of type `HTTP` is not the target URI; it is an **intermediary hop** that the HTTP client connects to first, then executes the appropriate HTTP proxy mechanism. `Proxy.Type.SOCKS` is another type, with socket-layer semantics and varying levels of support across HTTP clients/handlers. You should not assume every `ProxySelector` consumer supports every `Proxy.Type`.

### Connection Route Diagram

```text
Java App
  |
  | HttpRequest.uri() = https://api.partner.example/v1
  v
ProxySelector.select(target URI)
  |
  +--> Proxy A (HTTP proxy at proxy-a.example:8080)
  +--> Proxy B (HTTP proxy at proxy-b.example:8081)
             |
             v
   HTTP client selects and attempts to connect according to its capabilities/contract
             |
       Proxy connected
             |
             v
     Origin api.partner.example
             |
             v
     HTTP response / I/O error
```

**Important:** the list A, B expresses the **selector's preference order**; it **does not promise** that every `HttpClient` implementation will automatically try all proxies in sequence, forward every request, or invoke `connectFailed` in every situation. Actual retry/failover behavior must be verified against the specific client and JDK in use.

## 3. The `ProxySelector.select(URI)` Contract

Two abstract methods must be implemented when creating a subclass:

```java
// API signatures; this is not a standalone class.
public abstract List<Proxy> select(URI uri);

public abstract void connectFailed(
        URI uri, SocketAddress sa, IOException ioe);
```

### What does `select` receive?

`URI` describes the **destination** the application wants to access. Java 17 documents typical forms:

- `http://host[:port]/...` for HTTP connections.
- `https://host[:port]/...` for HTTPS connections.
- `socket://host:port` in TCP socket contexts using an appropriate selector.

Examples:

```text
http://public.example/status
https://api.partner.example/v1/orders
https://reports.corp.example/dashboard
```

Here `uri.getScheme()` gives `http` or `https`, `uri.getHost()` gives the hostname; `uri.getPort()` can be `-1` when no port is declared. For path-based policies, you can inspect `uri.getPath()`, but you must account for URL normalization and redirects, and choosing a proxy based on **destination host/scheme** is usually clearer.

**Do not use `URI.toString().contains("corp")` as a bypass policy.** That substring can match inside a path, query, or forged username; for example:

```text
https://attacker.example/download?next=corp.example
```

is not a corporate domain. You should extract `getHost()`, normalize the hostname according to appropriate rules, and check **exact host or dot-prefixed suffix**. If you support Unicode domains, IPv6, trailing dots, IDNs, or special hostnames, you need stricter normalization and testing than a demo.

### What does `select` return?

`select(uri)` returns `List<Proxy>`, where each element is a candidate. If the policy uses no proxy, per the API it returns a **list containing the direct element**:

```java
return List.of(Proxy.NO_PROXY);
```

Do not return `null` or an empty list to express direct. If you want to prefer one proxy and then a backup proxy:

```java
return List.of(primaryProxy, backupProxy);
```

If only proxies are allowed, **do not append `Proxy.NO_PROXY` at the end** as a "harmless fallback": it can create a direct connection path and **bypass egress policy**. A candidate list is not a security rule; the client may try or skip elements depending on its implementation.

### Validating the input URI

Java 17 documentation states that `select` throws `IllegalArgumentException` if the argument is `null` or the protocol/host cannot be determined. In a custom selector, you can write:

```java
if (uri == null || uri.getScheme() == null
        || uri.getHost() == null) {
    throw new IllegalArgumentException(
            "Absolute URI with scheme and host required");
}
```

Do not guess the hostname from an improperly parsed authority component. `URI.create("/relative/path")` has no host; it is not a complete absolute HTTP URI sufficient for proxy selection. For unsupported schemes, have an explicit policy (reject or delegate to an appropriate selector) rather than silently returning DIRECT for every unfamiliar scheme.

## 4. `Proxy.Type`, `Proxy.NO_PROXY`, and Preference Order

`Proxy.Type` has the main types:

| Type | Meaning | `Proxy.address()` |
|---|---|---|
| `HTTP` | HTTP-based proxy | `SocketAddress` pointing to the proxy endpoint |
| `SOCKS` | Socket-layer SOCKS proxy | `SocketAddress` pointing to the proxy endpoint |
| `DIRECT` | Direct connection, without a proxy | `null` for `Proxy.NO_PROXY` |

Choosing `Proxy.NO_PROXY` means the client is advised to **connect directly to the target URI**. It does **not** mean "no network" or "skip the request". If network policy requires going through a proxy, placing DIRECT in the wrong place is a serious bug.

### What does the candidate list mean?

Suppose:

```java
return List.of(proxyA, proxyB);
```

The selector **suggests** proxy A first, then proxy B. According to the `ProxySelector` model, when a proxy fails to connect, the party performing the connection **should** notify `connectFailed` so the selector can update its choices. However, whether to try proxy B immediately, how many times to retry, and how to handle request replay belong to the **consumer's implementation**, not to the fact that you returned a List.

**Do not write in API docs "returning a List of two proxies ⇒ Java HttpClient is guaranteed to failover."** Run integration tests with your exact JDK, request type, proxy type, network errors, and body-replayability scenarios.

### Preference order is not round-robin

`List.of(A, B)` simply returns **A then B**; there is no automatic load balancing by weight, latency, or health. If you want round-robin, sticky routing, circuit breakers, backoff, or region affinity, that is logic you must **implement explicitly** and ensure thread safety for.

### When is direct appropriate?

- Loopback `localhost`/`127.0.0.1` in permitted environments.
- An internal domain **explicitly allowed by policy to bypass**.
- A local test that does not need a proxy.

Do not rely on "host ends with `.internal`" from untrusted input as the sole defense against SSRF or firewall bypass; DNS resolution, private IPs, redirects, and egress policies still need independent protection.

## 5. Selecting by URI: Scheme, Hostname, Port, and Policy

A common policy:

```text
URI host belongs to *.corp.example / localhost
    -> DIRECT (only when company policy allows)

URI scheme https and partner host
    -> HTTP proxy A, backup HTTP proxy B

URI scheme http in public zone
    -> HTTP proxy B

Unsupported URI scheme or unknown host
    -> FAIL validation; do not silently fall back to DIRECT
```

This is a pedagogical example, **not a standard policy for every enterprise**. In real systems, host routing may depend on domain allowlists, datacenters, tenants, geographic regions, service types, and security regulations.

### Why check the scheme first?

`http` and `https` differ in how the client connects and protects content. An HTTPS URI sent through an **HTTP proxy** typically uses the `CONNECT` method to establish a tunnel to the origin, followed by a TLS handshake to the origin over the tunnel. This differs from sending a plain HTTP request through a proxy. Policy may force HTTPS traffic to a more tightly governed proxy.

### What role does the port play?

`https://api.example:8443` differs from `https://api.example` as an endpoint. If policy only permits the proxy to access certain ports, you need to check `getPort()` (applying the scheme's default when `-1`). However, **do not extract ports from the path or an unparsed URI string**.

### Should path/query participate in the policy?

`ProxySelector.select(URI)` receives the URI, so a custom policy **can** inspect path/query. However, routing by query easily leaks sensitive data and causes mismatches between proxies/caches and the origin. Many systems should choose proxies by **scheme + destination host + port**, while access control and URL validity are handled by the security/HTTP API layer.

### Suffix bypasses must avoid spoofing

Check that the host ends with `".corp.example"` for subdomains, plus exact `"corp.example"` if you want to allow the apex domain. Do not write `host.endsWith("corp.example")`, which would accidentally accept `evilcorp.example`. If the allowlist includes IPs/CIDRs or IPv6, use an address parser and appropriate DNS/resolution checks rather than plain string comparison.

## 6. What Information Does `connectFailed` Receive and When Is It Used?

Signature:

```java
@Override
public void connectFailed(
        URI uri, SocketAddress sa, IOException ioe) {
    // Record a proxy that failed to establish a connection.
}
```

Three distinct parameters:

| Parameter | Meaning | Do not confuse with |
|---|---|---|
| `uri` | **URI of the resource the client was trying to access** when using the proxy | URI of the proxy itself |
| `sa` | **Socket address of the proxy/SOCKS server** to which the connection failed | Address of the origin server (except special cases you should not assume) |
| `ioe` | `IOException` that caused the failure to establish the connection to the proxy | An HTTP status code or arbitrary business exception |

Java 17 documents that this method is called when **a connection could not be established to a proxy/SOCKS server**. An implementation may temporarily exclude the broken proxy, reorder proxies, or record a health metric. Do not assume the callback will fire for every `IOException` in an HTTP application.

### Valid examples of errors to consider

- TCP connection to the proxy host:port was refused (`ConnectException`).
- Proxy could not be reached due to network unreachable/timeout during proxy connection setup, depending on client/provider.
- A specific proxy address is unavailable, and the selector wants to deprioritize it for a cooldown period.

### Errors that are **not synonymous** with `connectFailed`

- Server returns `404 Not Found`: a **valid HTTP response**.
- Origin returns `500 Internal Server Error`: no evidence that connecting to the proxy failed.
- Proxy returns `407 Proxy Authentication Required`: an HTTP response was already received from the proxy; that is a **proxy authentication problem**, not by default a TCP connection failure to the proxy.
- Proxy returns `502 Bad Gateway`: the proxy **already returned an HTTP response**. It indicates an upstream/gateway issue, **not the same signal** as being unable to connect to the proxy endpoint.
- JSON parsing or validation failure after the HTTP response completes: an application error, not a proxy connection setup failure.
- TLS certificate verification failure against the origin: requires investigating TLS trust/host and the tunnel; **you cannot automatically attribute every SSL exception to the proxy being down**.

For a specific `HttpClient` or handler, consult its documentation and observe in practice when `connectFailed` is called. A test program calling `selector.connectFailed(...)` **manually** can test the policy, but **does not prove that the HTTP client automatically emits the callback in every scenario**.

## 7. Designing Health Updates in `connectFailed`

For a simple demo, a thread-safe boolean flag can record that proxy A is failing so subsequent `select` calls omit proxy A. In production, you need more care:

1. **Identify the proxy by the socket address** that actually failed; do not mark the entire proxy list down because one endpoint failed.
2. **Do not keep failures permanent** if the system can recover: use expiry/cooldown, backoff, and bounded retries.
3. **Avoid races** between concurrent `select` and `connectFailed` threads: use `AtomicBoolean`, `ConcurrentHashMap`, or immutable snapshots; be careful with consecutive health updates.
4. **Do not block for long** inside the callback: never perform synchronous HTTP health checks, slow DNS lookups, or database calls inside `connectFailed`.
5. **Be observable**: metrics per proxy endpoint, error class, failure count, last failure timestamp, selected route—but **do not log credentials/tokens/sensitive queries**.
6. **Define fail-open vs. fail-closed**: if all mandatory proxies fail, is direct allowed? In environments enforcing egress through a proxy, the answer is usually **no**.
7. **Do not confuse health with authorization**: a live proxy does not mean a request through it is authorized to call the resource.
8. **There is no automatic rollback**: if a request already sent bytes through a proxy and then failed later, retry decisions must be based on HTTP method/idempotency and whether the body is replayable, not just a callback.

### Warning on host failover

When two proxies are different gateways, trying B after A can change the egress path, the source IP seen by the origin, audit policy, latency, and upstream permissions. Therefore, a "backup proxy" should belong to the **same set of proxies approved for that URI**, not just any functioning proxy.

### Unresolved addresses

`InetSocketAddress.createUnresolved("proxy-a.example", 8080)` creates an endpoint by hostname/port without performing DNS at object creation time. It is well-suited for deterministic selection tests. **Do not interpret unresolved as guaranteed to connect**; when the HTTP client actually connects, DNS resolution or connection can still fail depending on the environment and implementation.

## 8. Integrating with `java.net.http.HttpClient`

How to set a custom proxy selector **for a specific `HttpClient`**:

```java
// Illustrative code assuming RoutingSelector selector already exists.
HttpClient client = HttpClient.newBuilder()
        .proxy(selector)
        .build();
```

This keeps the scope clear: the client uses the selector provided to the builder. There is no need to modify the JVM-wide `ProxySelector.setDefault`, which avoids unexpectedly changing routes for other libraries or threads.

### Three convenient configurations

```java
// 1. A fixed proxy for HTTP/HTTPS:
HttpClient fixed = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                InetSocketAddress.createUnresolved(
                        "proxy.example", 8080)))
        .build();

// 2. Intentionally always connect directly:
HttpClient direct = HttpClient.newBuilder()
        .proxy(HttpClient.Builder.NO_PROXY)
        .build();

// 3. Custom per-URI policy:
// HttpClient custom = HttpClient.newBuilder()
//         .proxy(new RoutingSelector())
//         .build();
```

`ProxySelector.of(address)` is a convenience factory that uses a single proxy for **HTTP and HTTPS**. It cannot replace a custom selector with a proxy list and per-URI rules. `HttpClient.Builder.NO_PROXY` is a selector used to specify direct explicitly.

**Default:** in Java 17, if the builder does not call `proxy(...)`, a new client typically uses the **default proxy selector**. The default selector may inspect system configuration and Java networking system properties. Do not rely on `HttpClient.proxy()` returning `Optional.empty()` to conclude the client uses no proxy: the API notes it **may still use an unexposed default selector**.

### A built client has its own configuration

An `HttpClient` created from a builder holds configuration state bound to that client; calling `ProxySelector.setDefault(...)` after creating the client **does not automatically change the default proxy already captured** for the existing client. If you want to change routing at runtime for a new policy, depending on your implementation: update the thread-safe state of the attached custom selector, or create a new client with the appropriate configuration.

**Caution:** a selector with mutable state becomes part of the client integration; an `HttpClient` used from multiple threads can invoke the selector concurrently across simultaneous requests. You must control concurrency and never return a mutable `ArrayList` that another thread is modifying.

### Do not confuse `ProxySelector.of(...)` with `URL.openConnection(Proxy)`

The legacy API `URL.openConnection(Proxy)` uses **a single `Proxy` passed by the caller for one connection**; it does not share the same contract as a `ProxySelector` selecting by URI. Some protocol handlers may not support proxies or may handle them differently. Java's `java.net.http.HttpClient` uses `Builder.proxy(ProxySelector)`, not a single `Proxy` directly in the builder.

## 9. System-Wide Default, Properties, and Overrides

Java provides:

```java
ProxySelector current = ProxySelector.getDefault();
// ProxySelector.setDefault(custom) changes the global default
// for consumers that use the default going forward.
```

**Do not unilaterally change the global default** inside a shared library/SDK in the same JVM: other networking modules may rely on different system proxies, and cross-thread changes cause unpredictable behavior. In an application with full startup control, system-level configuration can be reasonable if clearly managed.

Some common Java networking properties:

| Property | General role |
|---|---|
| `http.proxyHost`, `http.proxyPort` | HTTP proxy in the default configuration |
| `https.proxyHost`, `https.proxyPort` | HTTPS proxy in the default configuration |
| `http.nonProxyHosts` | Hosts that bypass the proxy according to the default selector/handler policy |
| `socksProxyHost`, `socksProxyPort` | SOCKS configuration in APIs that support it |
| `java.net.useSystemProxies` | Enables Java to use system proxy settings on supported platforms, typically evaluated at startup |

Actual behavior depends on the runtime, client, and platform. Do not treat this list as a guarantee that all values are dynamically re-read on every request. **`java.net.useSystemProxies` is documented as being checked at startup.** If you want per-tenant/per-URI routing, use a dedicated selector and explicit configuration instead of relying on mutating `System.setProperty(...)` at arbitrary times.

### Is bypassing with `nonProxyHosts` the same as a custom policy?

`http.nonProxyHosts` uses host pattern syntax for the default selector/HTTP handler, not a list of `URI`s, and is not necessarily equivalent to the rules you implement in `select`. If you choose a custom selector, you are responsible for defining your own bypass policy; do not assume the default `nonProxyHosts` automatically applies inside custom code.

### Proxy credentials

Credentials do not live in the `Proxy` endpoint or the `select` return list. If the proxy requires HTTP authentication, you may need an `Authenticator`/challenge handling and client-specific configuration. **Do not embed user/password in the target URI hoping the selector will use them as proxy credentials**, and do not log `Proxy-Authorization`.

## 10. HTTPS Through an HTTP Proxy, `CONNECT`, and HTTP Sessions

When the target is `https://origin.example` and policy chooses an **HTTP proxy**, a common connection flow is:

```text
Java HttpClient --TCP--> HTTP proxy
                       |
                       | CONNECT origin.example:443 HTTP/1.1
                       v
               Proxy creates TCP tunnel
                       |
         Java HttpClient --TLS--> origin.example
                       |
                       v
                HTTPS request/response
```

This is the **general model** of HTTPS tunneling; details can vary by HTTP version and implementation.

- The proxy can see the `CONNECT` target hostname/port, timing, and traffic volume; tunneling **does not mean the proxy can see plaintext HTTPS** as long as end-to-end TLS is maintained.
- The Java client must still verify the origin's TLS certificate/hostname according to trust policy. Routing through a proxy **does not disable TLS verification**.
- In environments with managed TLS interception, a proxy may intentionally intercept/decrypt TLS if the client trusts the appropriate certificate; that is a separate security/trust concern.
- For plain `http://`, an HTTP proxy can receive the HTTP request in proxy form, without end-to-end TLS to the origin.
- `407 Proxy Authentication Required` is an **HTTP status** from the proxy; handle authentication per client policy rather than automatically marking the proxy TCP-down.
- `502 Bad Gateway` from a proxy is still an HTTP response; it may indicate an origin/upstream problem and does not by itself prove a failure to connect **to the proxy**.

**Do not manually invoke `connectFailed` just because you received 407/502** and cycle through proxies. Separate network/proxy-endpoint failures from HTTP response statuses and business outcomes.

### HTTP sessions and connection reuse

An `HttpClient` may reuse connections according to its policy/runtime. Updating a custom selector's list after an error **does not necessarily switch already-open connections to another proxy immediately**. For an established connection, subsequent requests may use the connection pool rather than re-running every proxy-selection step. To verify when selection or fallback occurs, test against the specific JDK, proxy, and scenario; **do not use the number of `select` calls as a reliable count of HTTP requests**.

## 11. Runnable Java 17 Example: URI-Based Proxy Selection and Updating After `connectFailed`

This demo program **does not open network connections to fake hosts**. It calls `select` directly with three URIs, then **simulates** a connection failure to proxy A via `connectFailed`, calls `select` again, and builds an `HttpClient` configured with the selector. This keeps stdout deterministic and independent of DNS, the Internet, or a corporate proxy.

**Demo policy**:

1. Host `localhost`, `127.0.0.1`, or subdomain `*.corp.example` → DIRECT.
2. Public HTTP URI → proxy B only.
3. Public HTTPS URI → proxy A then B; after proxy A is reported failed, recommend only B.
4. URI missing scheme/host or with a non-HTTP(S) scheme → throw `IllegalArgumentException`.
5. `AtomicBoolean` guards the health flag in the example; production requires cooldowns and richer state.

Create file **`ProxySelectorRoutingDemo.java`**:

```java
import java.io.IOException;
import java.net.ConnectException;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.SocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.util.List;
import java.util.Locale;
import java.util.StringJoiner;
import java.util.concurrent.atomic.AtomicBoolean;

public class ProxySelectorRoutingDemo {
    static final class RoutingSelector extends ProxySelector {
        private final Proxy primary = new Proxy(Proxy.Type.HTTP,
                InetSocketAddress.createUnresolved(
                        "proxy-a.example", 8080));
        private final Proxy backup = new Proxy(Proxy.Type.HTTP,
                InetSocketAddress.createUnresolved(
                        "proxy-b.example", 8081));
        private final AtomicBoolean primaryHealthy =
                new AtomicBoolean(true);

        @Override
        public List<Proxy> select(URI uri) {
            if (uri == null || uri.getScheme() == null
                    || uri.getHost() == null) {
                throw new IllegalArgumentException(
                        "Absolute URI with scheme and host required");
            }

            String scheme = uri.getScheme()
                    .toLowerCase(Locale.ROOT);
            if (!scheme.equals("http") && !scheme.equals("https")) {
                throw new IllegalArgumentException(
                        "Unsupported scheme: " + scheme);
            }

            String host = uri.getHost()
                    .toLowerCase(Locale.ROOT);

            if (host.equals("localhost")
                    || host.equals("127.0.0.1")
                    || host.endsWith(".corp.example")) {
                return List.of(Proxy.NO_PROXY);
            }

            if (scheme.equals("http")) {
                return List.of(backup);
            }

            return primaryHealthy.get()
                    ? List.of(primary, backup)
                    : List.of(backup);
        }

        @Override
        public void connectFailed(
                URI uri, SocketAddress address,
                IOException error) {
            if (uri == null || address == null || error == null) {
                throw new IllegalArgumentException(
                        "uri, address and error are required");
            }

            if (primary.address().equals(address)) {
                primaryHealthy.set(false);
            }

            System.out.println("Failed proxy: "
                    + endpoint(address) + " ("
                    + error.getClass().getSimpleName() + ")");
        }

        SocketAddress primaryAddress() {
            return primary.address();
        }
    }

    static String endpoint(SocketAddress address) {
        InetSocketAddress inet = (InetSocketAddress) address;
        return inet.getHostString() + ":" + inet.getPort();
    }

    static String describe(List<Proxy> proxies) {
        StringJoiner result = new StringJoiner(" -> ");
        for (Proxy proxy : proxies) {
            if (proxy.type() == Proxy.Type.DIRECT) {
                result.add("DIRECT");
            } else {
                result.add(proxy.type() + " "
                        + endpoint(proxy.address()));
            }
        }
        return result.toString();
    }

    public static void main(String[] args) {
        RoutingSelector selector = new RoutingSelector();
        URI internal = URI.create(
                "https://reports.corp.example/dashboard");
        URI partner = URI.create(
                "https://api.partner.example/v1");
        URI publicHttp = URI.create(
                "http://public.example/status");

        System.out.println("Internal: "
                + describe(selector.select(internal)));
        System.out.println("Partner before: "
                + describe(selector.select(partner)));
        System.out.println("Public HTTP: "
                + describe(selector.select(publicHttp)));

        // Simulate a failure notification from the caller; NO network connection is made.
        selector.connectFailed(partner,
                selector.primaryAddress(),
                new ConnectException("connection refused"));

        System.out.println("Partner after: "
                + describe(selector.select(partner)));

        HttpClient client = HttpClient.newBuilder()
                .proxy(selector)
                .build();
        System.out.println("HttpClient selector attached: "
                + (client.proxy().orElseThrow() == selector));
    }
}
```

Compile and run commands for **JDK 17 or later**:

```bash
javac --release 17 -encoding UTF-8 ProxySelectorRoutingDemo.java
java ProxySelectorRoutingDemo
```

**Exact stdout:**

```text
Internal: DIRECT
Partner before: HTTP proxy-a.example:8080 -> HTTP proxy-b.example:8081
Public HTTP: HTTP proxy-b.example:8081
Failed proxy: proxy-a.example:8080 (ConnectException)
Partner after: HTTP proxy-b.example:8081
HttpClient selector attached: true
```

### Line-by-line explanation

1. **Internal DIRECT:** `select` reads `uri.getHost()`, recognizes `reports.corp.example` as a subdomain under the demo policy, and returns `List.of(Proxy.NO_PROXY)`.
2. **Partner before:** for public HTTPS, `select` returns an **ordered list** of HTTP proxies A and B. This is a policy result; **no connection has been made to them yet**.
3. **Public HTTP:** the demo rule for HTTP-scheme URIs uses B and does not include A in the list.
4. **Failed proxy:** the program itself calls `selector.connectFailed` with A's `SocketAddress` and a constructed `ConnectException` to **simulate** a failure. This is **not** a log emitted by `HttpClient` on a real connection failure.
5. **Partner after:** `AtomicBoolean` flips to false, so the next `select` returns only proxy B. This does **not** prove the consumer automatically falls back or retries requests.
6. **HttpClient selector attached:** `HttpClient.newBuilder().proxy(selector)` accepts that exact instance; `client.proxy().orElseThrow()==selector` is `true`. The program does not call `client.send` against the fake hosts.

### Limitations to understand

- `InetSocketAddress.createUnresolved` **does not resolve DNS**, allowing the demo to run without Internet access; when used for real connections, DNS/network failures can still occur.
- `connectFailed` in the demo is called **manually** and does not test the HTTP client runtime's callback invocation.
- Using `AtomicBoolean` is a simplification: after a single failure, proxy A is permanently excluded for the lifetime of the demo selector. Production needs cooldown/retry probes/per-proxy health and metrics.
- Removing proxy A from `select` only affects new selections; it does not guarantee already-sent requests or open connections switch proxies immediately.
- The URIs `*.corp.example`, `*.partner.example` here are illustrative dummy addresses; no real proxy connection or configuration is needed to run the program.

## 12. Production Design Considerations and Trade-Offs

### 12.1. One list for many URIs or a per-tenant policy?

A shared proxy is easy to manage, but sending all traffic through one path can affect latency and security. Per-tenant/per-service routing requires controlled mappings so untrusted user input cannot pick an internal proxy to reach a private network.

Do not store credentials in the returned proxy choices. If multiple tenants have different identities/egress paths, manage separate clients/selectors/auth per policy, avoiding mixing privileges in a shared connection pool when the design does not permit it.

### 12.2. Circuit breaker with cooldown

When A fails:

```text
A HEALTHY --> (connect failure) --> A COOLDOWN
     ^                               |
     |                               v
     +---- (probe succeeded) ---- A PROBING
                         (probe failed) -> A COOLDOWN
```

This is a **recommended design pattern**, not a built-in feature of `ProxySelector`. You can store `nextRetryNanos` per proxy and use `System.nanoTime()` to compute cooldowns; never block `select` waiting for a proxy to recover. Probing must be rate-limited, and probing may require a dedicated protocol/endpoint.

### 12.3. A healthy proxy does not mean requests will succeed

Establishing a TCP connection to the proxy only clears one step. The proxy can still require authentication, reject the destination, hit upstream errors, lose connectivity to the origin, or return HTTP errors. `connectFailed` cannot replace HTTP error handling, status-based retries, origin circuit breakers, or business observability.

### 12.4. Minimize allocations and latency in the selector

If `select` is called frequently, do not reload config from a database or perform DNS lookups for every proxy on each call. Keep immutable proxy lists per configuration, read thread-safe health state, and return `List.of(...)` so consumers cannot accidentally mutate the list. You need a safe policy-reload mechanism, race-free tests, and a clear definition of when changes apply to new connections.

### 12.5. Avoid policy-violating fail-open behavior

Appending DIRECT at the end of a proxy list is a form of "if no proxy works, try going direct." In corporate networks with mandatory inspection/egress policies, that can violate compliance. If all proxies are unavailable, a **fail-closed** policy should usually let the request fail in a controlled manner rather than silently bypassing.

However, merely returning a proxy list is not enough to enforce network security. You still need egress firewalls, DNS/redirect policies, allowlists, TLS, and auditing as appropriate.

## 13. Two-Layer Testing for `ProxySelector`

### 13.1. Network-free unit tests

Assertions on the selector itself can verify:

| Input | Expected under demo policy |
|---|---|
| `https://reports.corp.example/dashboard` | `[DIRECT]` |
| `https://api.partner.example/v1` when healthy | `[proxyA,proxyB]` |
| `http://public.example/status` | `[proxyB]` |
| `https://api.partner.example/v1` after reporting A failed | `[proxyB]` |
| `null` | `IllegalArgumentException` |
| `/relative/path` | `IllegalArgumentException` |
| `file:///tmp/a` | `IllegalArgumentException` in demo policy |
| `https://evilcorp.example` | **Must not** bypass if rule properly checks `.corp.example` |
| `http://localhost/status` | DIRECT |

Test that `connectFailed` with B's `SocketAddress` does not mark A unhealthy if the code should only mark A when A fails. If the selector tracks health per address, test identical hostnames with different ports to avoid misidentifying endpoints.

### 13.2. Integration tests with a mock/test proxy

To verify **which proxy `HttpClient` actually uses**, set up a loopback test proxy server (or proxy test framework) that accepts connections/HTTP requests/tunnels and exercise scenarios such as:

1. Proxy A is available and returns/forwards valid responses.
2. Proxy A refuses the TCP connection; observe whether `connectFailed` is called, and whether B is tried or an error is returned.
3. Proxy returns `407`/`502`: compare behavior against a connect failure.
4. HTTPS `CONNECT` tunnel and TLS handshake success/failure.
5. Redirect from origin A to origin B: does the selector re-select for the new URI?
6. Connection reuse: does a second request trigger selection again?
7. One-shot `BodyPublisher` stream: if the client attempts retry/failover, can the body be replayed?
8. Connection timeout vs. request timeout, concurrency/health races, and shutdown.

**Do not infer a consumer's contract from unit tests of `select` alone.** The program in this lesson tests selector logic and builder wiring; integration tests verify real network behavior.

### 13.3. Security-layer testing

For user-supplied URIs, also test:

- Lookalike internal domains such as `evilcorp.example`.
- Encoded URLs, userinfo, fragments, queries containing internal hostnames, Unicode/IDN.
- Redirects to `127.0.0.1`, private IPs, link-local, or metadata services when policy forbids them.
- DNS returning results outside the allowlist or changing over time.
- Proxy credentials not leaking to the wrong origin or an untrusted proxy.
- Proxy failure: does it fall back to DIRECT against policy?

This is the **SSRF/egress** control layer, which is not automatically solved just because the code uses `ProxySelector`.

## 14. Common Mistakes and How to Fix Them

| Mistake | Consequence | Correct approach |
|---|---|---|
| Thinking `select` performs the connection | Misses real error handling | `select` only returns a list of proxies/direct |
| Returning `null` when there is no proxy | Violates contract and breaks clients | Return `List.of(Proxy.NO_PROXY)` when direct is permitted |
| Returning `List.of()` to mean direct | Not a valid direct entry | Use `Proxy.NO_PROXY` |
| Using `Proxy.NO_PROXY.address()` as proxy host | `null`/cast error | Check `type()==DIRECT` |
| Assuming `List.of(A,B)` guarantees `HttpClient` fails over A→B | Wrong expectations on retries/compatibility | Test the actual consumer/JDK; do not promise fallback |
| Assuming `connectFailed` is called on all HTTP `5xx` | Falsely marks healthy proxies down | Follow the contract: only proxy connection failures |
| Treating `407` as a proxy TCP connect failure | Infinite retries, broken auth handling | Handle proxy authentication |
| Treating `502` as always meaning unreachable proxy | Confuses upstream/gateway failures | Separate HTTP status from network failures |
| Permanently disabling proxy A after one transient error | Skewed traffic, no self-recovery | Use appropriate cooldown/circuit breaker/probing |
| Falling back to DIRECT for all URIs on proxy error | Bypasses egress/security policy | Fail-closed as required |
| Using `URI.toString().contains("corp")` | Forged query/path bypass | Check normalized host/scheme |
| `host.endsWith("corp.example")` without a leading dot | Accepts `evilcorp.example` | Use `.corp.example` suffix + explicit apex domain |
| Poor synchronization when updating proxy lists | Races/corrupted state | Immutable lists and thread-safe health state |
| Blocking on DNS/HTTP health checks inside `select`/`connectFailed` | Increased latency or potential deadlocks | Lightweight callbacks; separate rate-limited probing |
| Calling `setDefault` in a shared library | Unintentionally alters JVM-wide routing | Use `HttpClient.Builder.proxy(...)` per client |
| Thinking `HttpClient.proxy()==Optional.empty` means direct | Client may use a hidden default proxy | Inspect builder/actual default policy |
| Thinking `http.nonProxyHosts` applies automatically in a custom selector | URIs bypass/route against policy | Implement and test your own rules |
| Putting proxy passwords in URIs or logs | Credential leakage | Use authentication APIs and redaction |
| Treating HTTPS over HTTP proxy as completely plaintext | Misunderstands `CONNECT` + TLS | Distinguish the tunnel from end-to-end TLS |
| Treating a live proxy as a successful request | Origin can still fail or time out | Observe HTTP status + business outcome |
| Updating selector health and expecting pooled connections to switch immediately | Requests continue using existing connections | Test connection reuse/lifecycle |
| Auto-retrying a payment/upload POST after network failure | Duplicate side effects or non-replayable body | Idempotency, deadlines, replay-safe policy |
| Treating an unresolved address as proof DNS is OK | Real connections can still fail resolution | Understand `createUnresolved` only defers DNS |

## 15. Self-Check Questions

**Question 1.** Does `ProxySelector.select(URI)` connect to the proxy itself?

**Answer:** No. It returns a list of `Proxy` or `Proxy.NO_PROXY`. The consumer, such as an HTTP client, performs the connection according to its own capabilities and policy.

**Question 2.** If you do not want to use a proxy for an internal URI, what should you return?

**Answer:** `List.of(Proxy.NO_PROXY)`. Do not return `null` or an empty list to represent direct.

**Question 3.** Is the `URI` passed to `select` the URI of the proxy or of the resource being accessed?

**Answer:** Of the **target resource**. The proxy's address is in `Proxy.address()` and in `SocketAddress sa` of `connectFailed` when the proxy cannot be reached.

**Question 4.** What does `connectFailed(uri, sa, ioe)` indicate?

**Answer:** Connecting to the proxy/SOCKS server at `sa` failed while serving `uri`, with `IOException ioe`. It supports updating proxy ordering/health.

**Question 5.** If a server returns `404`, should you manually call `connectFailed`?

**Answer:** No. `404` is an HTTP status from a valid HTTP exchange, with no evidence that the TCP connection to the proxy endpoint failed.

**Question 6.** Does a proxy returning `407 Proxy Authentication Required` mean proxy A is down?

**Answer:** Not by default. The proxy returned an HTTP response; you need to handle proxy authentication/challenges and policy rather than marking a connect failure solely because of status 407.

**Question 7.** Does the list `[A, B]` guarantee that JDK 17 `HttpClient` tries B if A fails?

**Answer:** You cannot promise this generally across all consumers/scenarios; the selector provides a **recommended order**, while actual fallback/retry logic must be verified on the specific client and runtime.

**Question 8.** Why should you not put `Proxy.NO_PROXY` at the end of the list for Internet traffic if the enterprise requires a proxy?

**Answer:** Because DIRECT allows connecting straight to the origin, potentially bypassing mandatory egress/inspection; when proxies are unavailable, you should fail-closed per policy.

**Question 9.** Are `Proxy.Type.HTTP` and `Proxy.Type.SOCKS` synonymous?

**Answer:** No. They are different proxy mechanisms. SOCKS support depends on the client/protocol; do not assume every `HttpClient` supports it.

**Question 10.** What does `Proxy.NO_PROXY.address()` return?

**Answer:** `null`; you must check `type` before reading or casting the address.

**Question 11.** How does `ProxySelector.of(address)` differ from a custom selector?

**Answer:** The `of` factory returns a selector that uses a single proxy address for HTTP/HTTPS, convenient for fixed policies. A custom subclass handles URIs and health/fallback with custom logic.

**Question 12.** If `HttpClient.proxy()` returns `Optional.empty()`, is it guaranteed there is no proxy?

**Answer:** No. The Java 17 API notes that the client may still use a default proxy selector not exposed through this `Optional`.

**Question 13.** Should a URL containing query `?next=corp.example` be selected as DIRECT via `contains("corp.example")`?

**Answer:** No. You must inspect the request's `URI.getHost()`, never confusing query/path with the authority.

**Question 14.** After a single `connectFailed`, should you permanently disable proxy A?

**Answer:** The demo does so for observability, but production should use a health model, cooldown, and probing back according to policy.

**Question 15.** When changing the proxy route, are already-open HTTP connections guaranteed to switch immediately?

**Answer:** No. Connection reuse/pooling and when routes are selected are decided by the client runtime; integration testing is required.

**Question 16.** Why is `HttpClient.newBuilder().proxy(selector)` usually safer than changing `ProxySelector.setDefault` in an SDK?

**Answer:** Because it binds the policy to a specific client without surprising other libraries or HTTP clients in the same JVM.

**Question 17.** For HTTPS through an HTTP proxy, what do the client and origin typically do after `CONNECT`?

**Answer:** Establish a TLS session to the origin through the tunnel and verify certificate/hostname. The proxy still sees the `CONNECT` destination and connection metadata; `CONNECT` does not disable TLS.

**Question 18.** When a response is lost after a payment POST through a proxy, should you immediately retry if proxy B is healthy?

**Answer:** No. The server may have already committed before the response was lost. Decisions must be based on idempotency, business state, deadlines, and replay policy; switching proxies does not guarantee exactly-once delivery.

## 16. Practical Checklist for Java Networking

Before using `ProxySelector` in a real application:

1. **Lock down the routing policy**: which domains/schemes/ports are DIRECT, which must use a proxy, and which backup groups are approved.
2. **Parse URIs properly**: validate `getScheme`, `getHost`, port/IDN/IPv6 as needed; avoid ambiguous substring/suffix checks over the entire URI.
3. **Return valid lists** from `select`: never `null`, never empty, use `Proxy.NO_PROXY` only when permitted.
4. **Distinguish proxy endpoints from origins**: `Proxy.address` and `connectFailed.sa` are proxy addresses.
5. **Attach the custom selector to the right `HttpClient`** via `HttpClient.newBuilder().proxy(selector)` to avoid global surprises.
6. **Do not promise failover** without integration-testing the actual behavior of the client/JDK, proxy type, and request type.
7. **Define callback failures clearly**: `connectFailed` is a failure to establish a connection to the proxy, not an HTTP error status.
8. **Manage concurrency/health**: immutable lists, atomic state, cooldowns, observability, and lightweight callbacks.
9. **Fail-closed when egress is mandatory**: do not add unauthorized DIRECT fallbacks.
10. **Control proxy authentication** separately; do not hardcode credentials or log secrets.
11. **HTTPS still requires TLS verification**: `CONNECT` is a tunnel, not a replacement for trust/hostname checking.
12. **Test redirects and connection reuse** because routing may be applied at different points.
13. **Define timeouts and retry policies** aligned with HTTP methods, idempotency, and `BodyPublisher` replayability.
14. **Protect against SSRF and DNS issues** with independent network controls, not solely selector host matching.
15. **Monitor errors at the right layer**: DNS/network, proxy connect, proxy HTTP 407/502, origin status, TLS, and business outcome.

**Remember:** `ProxySelector.select(uri)` decides **proxy/direct candidates by target URI**. `connectFailed(uri, sa, ioe)` is feedback about a **connection failure to a proxy endpoint**, allowing the policy to update ordering or health. `HttpClient.Builder.proxy(selector)` is how you attach the policy to a client in Java 17. Distinguish **route selection**, **actual connection**, **HTTP response**, and **business outcome**; do not infer failover, retries, or security from a `Proxy` list alone.

### Official Documentation (Java SE 17)

- [java.net.ProxySelector — select, connectFailed, of, default](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html)
- [java.net.Proxy — HTTP/SOCKS/DIRECT and Proxy.NO_PROXY](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Proxy.html)
- [java.net.InetSocketAddress — createUnresolved](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html)
- [java.net.http.HttpClient.Builder — proxy, NO_PROXY](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [java.net.http.HttpClient — default selector and proxy()](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 Networking Properties — proxies](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html)
- [RFC 9110 — HTTP Semantics, CONNECT and status](https://www.rfc-editor.org/rfc/rfc9110)