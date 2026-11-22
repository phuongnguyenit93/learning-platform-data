# System-Wide Proxy Properties and Per-HttpClient Configuration

*Java Advance – networking | Parent topic: Proxies and HTTP Sessions | Java 17+ API*

## 1. Why distinguish between JVM-wide and per-HttpClient proxy configuration?

An HTTP request in Java can be sent **directly to the origin** or **through a proxy**:

~~~text
DIRECT:
  Java HttpClient -----------------------> HTTP origin server

HTTP via proxy:
  Java HttpClient ----> HTTP proxy ------> HTTP origin server

HTTPS via HTTP proxy:
  Java HttpClient ----> HTTP proxy
                          |
                       CONNECT host:443
                          |
                       TLS tunnel ------> HTTPS origin server
~~~

A proxy can serve outbound access control, egress firewalling, caching, auditing, or routing. However, a single service might call an Internet API **via a corporate proxy** while also calling an **internal network API directly**. Using a single global configuration for all requests makes it easy to hit network errors, route data to the wrong path, or create races between threads.

Java 17 supports two main ways of configuring proxies:

- **JVM-level default:** `System Properties` such as `http.proxyHost`, `https.proxyHost`, `http.nonProxyHosts`, `java.net.useSystemProxies`; the default `ProxySelector.getDefault()` decides the proxy for each URI.
- **Per-`HttpClient` instance:** `HttpClient.newBuilder().proxy(ProxySelector)` can attach a fixed proxy, custom routing, or `HttpClient.Builder.NO_PROXY` to bypass the proxy.

**The most important point:** setting `-Dhttp.proxyHost=...` **does not force every HttpClient** to go through that proxy. When a client has its own `ProxySelector`, it can choose a different route. Conversely, a client that does not configure `proxy(...)` typically uses the **JVM's default proxy selector**.

~~~text
JVM-wide default:
  -Dhttp.proxyHost=proxy-global.example
  -Dhttp.nonProxyHosts=localhost|127.*
                  |
                  v
        ProxySelector.getDefault()
                  |
            HttpClient A
           (no proxy set)

HttpClient B: builder.proxy(ProxySelector.of(proxy-special))
    -> proxy-special, dedicated selector for B

HttpClient C: builder.proxy(HttpClient.Builder.NO_PROXY)
    -> direct connection, regardless of default proxy
~~~

Do not change `System.setProperty(...)` before each request to toggle a proxy on or off. This is **global state of the Java process**, not an option on a single `HttpRequest`, so other clients or libraries can be affected.

## 2. Table of Java 17 proxy-related System Properties

According to Oracle's Java 17 *Networking Properties* documentation:

| Property | Default value | What is it used for? |
|---|---|---|
| `http.proxyHost` | None | Selects the HTTP proxy host for `http://` requests |
| `http.proxyPort` | `80` | HTTP proxy port |
| `https.proxyHost` | None | Selects the HTTP proxy for `https://` requests |
| `https.proxyPort` | `443` | Proxy port for HTTPS requests; should specify the actual port |
| `http.nonProxyHosts` | `localhost\|127.*\|[::1]` | Hostname pattern accessed **directly** |
| `java.net.useSystemProxies` | `false` | Allows using OS proxy settings on supported platforms |
| `socksProxyHost` | None | SOCKS proxy for networking APIs that support it |
| `socksProxyPort` | `1080` | Default SOCKS port |
| `socksProxyVersion` | `5` | SOCKS 4/5 depending on implementation capabilities |

Three points to remember:

1. **`http.nonProxyHosts` is used for both HTTP and HTTPS** in Java 17's default proxy selection. There is no standard Java 17 rule requiring `https.nonProxyHosts` to be set.
2. **`https.proxyPort` defaults to 443** in the documentation, but the actual port of a corporate HTTP proxy may be 3128 or 8080. This **does not** mean the HTTPS origin port must match the proxy port.
3. `socksProxyHost` belongs to broader Java networking; do not assume every `java.net.http.HttpClient` implementation handles SOCKS like an HTTP forward proxy. Check the specific JDK version, proxy type, and API.

### 2.1. Bypassing hosts with http.nonProxyHosts

Example value:

~~~text
localhost|127.*|[::1]|*.corp.example
~~~

`|` is the **delimiter between multiple patterns**, and `*` is the wildcard within a pattern. It is not comma-separated, not full regex, and not CIDR syntax such as `10.0.0.0/8`.

When an application sets `http.nonProxyHosts` explicitly, it needs to list the localhost/loopback entries it still wants to bypass; do not assume all default entries are always appended automatically. Specifically, Java 17 excludes many loopback forms from the proxy by default; this is why requests to `127.0.0.1` can go direct even when `http.proxyHost` is configured.

**Do not use this bypass pattern as an SSRF filter.** DNS can resolve a hostname to an internal IP, DNS names can change, and a hostname pattern is not sufficient to block requests controlled by an untrusted party. Security policy requires additional network egress restrictions and appropriate destination validation.

### 2.2. java.net.useSystemProxies is read at startup

`java.net.useSystemProxies=true` lets the default proxy selector try using proxy settings from the OS on platforms described by Oracle, such as Windows/macOS/GNOME. According to the Java 17 documentation, this property **is only checked once when the JVM starts up**.

~~~bash
java -Djava.net.useSystemProxies=true -version
~~~

The command above only checks the Java runtime; for an actual application, pass `-Djava.net.useSystemProxies=true` **when launching the application**, before the main class/`-jar`. Do not expect `System.setProperty("java.net.useSystemProxies", "true")` mid-program to make Java reload OS proxy config.

Specific Java proxy properties such as `http.proxyHost` take **precedence over OS proxy settings** when both are configured. The fact that the operating system uses PAC, browser preferences, or a VPN does not guarantee Java applies the exact same behavior as a browser.

### 2.3. System properties are not environment variables

| Source | Example | Automatically applied to Java HttpClient? |
|---|---|---|
| JVM `-D` | `-Dhttp.proxyHost=proxy.corp.example` | Can be used by the default proxy selector |
| Java runtime | `System.setProperty("http.proxyHost", "...")` | Global in the JVM, easily affects multiple clients |
| OS settings | Proxy settings in Windows/macOS | Platform-dependent, enabled via `java.net.useSystemProxies` from startup |
| Shell environment | `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` | **No guarantee** that default Java 17 HttpClient reads them automatically like curl |
| Dedicated builder | `.proxy(ProxySelector.of(...))` | Applies to **that HttpClient instance** |

A framework or library may read environment variables itself and build its own client. Therefore, read the framework's documentation if applicable; do not infer from `curl` respecting `HTTPS_PROXY` that every Java client does the same.

## 3. How to pass -D when running the JVM

If the corporate proxy is `proxy.corp.example:3128`:

~~~bash
java \
  -Dhttp.proxyHost=proxy.corp.example \
  -Dhttp.proxyPort=3128 \
  -Dhttps.proxyHost=proxy.corp.example \
  -Dhttps.proxyPort=3128 \
  '-Dhttp.nonProxyHosts=localhost|127.*|[::1]|*.corp.example' \
  -version
~~~

The command uses `-version` so it can be tested **without a Java artifact**. When running a real application, replace `-version` with the actual startup arguments. The `-D` options must come **before** `-jar` or the main class name. Quote `http.nonProxyHosts`: the `|` character in a shell can be interpreted as a pipeline.

On Windows PowerShell, you can use a single line to avoid line-continuation syntax mistakes:

~~~powershell
java '-Dhttp.proxyHost=proxy.corp.example' '-Dhttp.proxyPort=3128' '-Dhttps.proxyHost=proxy.corp.example' '-Dhttps.proxyPort=3128' '-Dhttp.nonProxyHosts=localhost|127.*|[::1]|*.corp.example' -version
~~~

If running in an IDE, application server, container, or build tool, make sure the **VM options reach the actual application JVM**, not just the build tool's JVM. Setting a proxy for the Maven/Gradle process does not automatically cause every child/forked application process to receive the same settings.

### 3.1. Should you call System.setProperty while serving requests?

Java may read certain proxy properties during operation; however, `System.setProperty` mutates the **entire JVM**, with no per-client isolation. A default selector using the property may observe the new value; another client or library may have cached/captured its configuration at build time.

The solution for multi-tenant/multi-API workloads is **per-HttpClient configuration**, creating a new client when you want to change routes. Do not do this:

~~~java
// Anti-pattern: mutating global state before each request.
System.setProperty("http.proxyHost", "proxy-A");
clientA.send(requestA, HttpResponse.BodyHandlers.discarding());
System.setProperty("http.proxyHost", "proxy-B");
clientB.send(requestB, HttpResponse.BodyHandlers.discarding());
~~~

This code is not safe under concurrency: requests from another thread can be routed through the newly changed proxy. In addition, the default selector already being stored by the client and connection reuse mean the outcome is not simply "the property right before `send` determines everything."

## 4. What does ProxySelector.getDefault() do?

`java.net.ProxySelector` returns connection options for a URI:

~~~java
// Snippet, requires importing ProxySelector, Proxy, List, URI.
ProxySelector selector = ProxySelector.getDefault();
List<Proxy> selected = selector.select(
        URI.create("https://service.example.test/resource"));

for (Proxy candidate : selected) {
    System.out.println(candidate.type());
}
~~~

Main APIs:

| API | Meaning |
|---|---|
| `ProxySelector.getDefault()` | Gets the JVM's default selector |
| `ProxySelector.setDefault(selector)` | Replaces the default selector **JVM-wide** |
| `select(URI)` | Selects a list of proxy/direct candidates for a URI |
| `connectFailed(URI, SocketAddress, IOException)` | Callback when the caller reports it could not connect to the proxy |
| `ProxySelector.of(InetSocketAddress)` | Fixed proxy for HTTP/HTTPS |
| `Proxy.NO_PROXY` | Represents a direct choice |
| `Proxy.Type.HTTP` | HTTP proxy |
| `Proxy.Type.SOCKS` | SOCKS proxy |
| `Proxy.Type.DIRECT` | Connection without a proxy |

`ProxySelector.select` states **which route the selector wants to choose**, not that the connection will succeed: DNS, firewall, TCP, proxy authentication, and TLS can all fail afterward.

**Do not overuse `ProxySelector.setDefault` in a service with multiple clients.** Java 17 `HttpClient` captures system-wide defaults **at instance creation time**; changing the default selector after a client is built does not make the old client automatically switch selectors according to the Javadoc. That does not mean every property value is permanently snapshotted in every implementation, but it is enough to show that changing the global selector between requests is an unreliable design.

## 5. Not specifying builder.proxy: the default selector can still be used

~~~java
HttpClient a = HttpClient.newHttpClient();
HttpClient b = HttpClient.newBuilder().build();
~~~

When the builder does not call `proxy(...)`, new clients use the JVM's **default ProxySelector** per the Java 17 Javadoc. The default selector understands the applicable `http.proxyHost`, `https.proxyHost`, `http.nonProxyHosts`, etc.

A very common pitfall:

~~~java
HttpClient client = HttpClient.newHttpClient();
boolean configuredExplicitly = client.proxy().isPresent();
~~~

`HttpClient.proxy()` returns an `Optional` containing the **ProxySelector explicitly provided to the builder**. If no selector was provided to the builder, the Optional can be **empty**, **yet the client still has an implicit default proxy selector in use**. Therefore:

~~~text
client.proxy().isEmpty() != "client definitely goes DIRECT"
~~~

To know the actual route, you must determine the client's exact selector, the URI being used, the bypass policy, and the connection outcome. Do not use this Optional as a flag confirming no proxy is used.

## 6. Attaching a dedicated proxy to each HttpClient

### 6.1. Fixing a single HTTP proxy

~~~java
// Snippet; import HttpClient, ProxySelector, InetSocketAddress.
HttpClient throughProxy = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.corp.example", 3128)))
        .build();
~~~

`ProxySelector.of(address)` per the Java 17 Javadoc returns a selector that uses that address for HTTP and HTTPS requests. **This is not the default selector**: do not assume it will apply `http.nonProxyHosts`. If you need to bypass localhost/internal hosts specifically for this client, write a custom selector.

### 6.2. Forcing direct connections with NO_PROXY

~~~java
HttpClient direct = HttpClient.newBuilder()
        .proxy(HttpClient.Builder.NO_PROXY)
        .build();
~~~

`HttpClient.Builder.NO_PROXY` is a Java 17 constant for selecting `Proxy.NO_PROXY`, meaning a direct connection. It **does not** clear the JVM's `http.proxyHost` and **does not** alter other clients. Per the Javadoc, `ProxySelector.of(null)` can also create a selector that disables proxying, but `NO_PROXY` is clearer in intent on the builder.

### 6.3. Clients have independent configuration lifecycles

After `build()`, `HttpClient` is an immutable configuration object that can be used for many requests and can share network resources/connection pools. There is no standard `HttpRequest.Builder.proxy(...)` in Java 17 to change routes per request.

To send API A through proxy 1 and API B direct, use **two clients**. To route multiple URIs within a single client with complex rules, use a **custom ProxySelector**. When proxy configuration changes at runtime, create a new client and switch traffic in a thread-safe manner rather than mutating global JVM properties.

## 7. Custom ProxySelector for URI-based routing

When you need to bypass internal hosts, you can write a custom selector:

~~~java
// Snippet, not a standalone program.
ProxySelector policy = new ProxySelector() {
    @Override
    public List<Proxy> select(URI uri) {
        String host = uri.getHost();
        if (host == null) {
            throw new IllegalArgumentException("URI must have a host");
        }
        if ("localhost".equalsIgnoreCase(host)
                || "127.0.0.1".equals(host)) {
            return List.of(Proxy.NO_PROXY);
        }
        return List.of(new Proxy(Proxy.Type.HTTP,
                new InetSocketAddress("proxy.corp.example", 3128)));
    }

    @Override
    public void connectFailed(
            URI uri, SocketAddress address, IOException reason) {
        // Redacted logs/metrics; can update proxy state.
    }
};

HttpClient selectiveClient = HttpClient.newBuilder()
        .proxy(policy).build();
~~~

The snippet above requires importing `ProxySelector`, `Proxy`, `URI`, `List`, `InetSocketAddress`, `SocketAddress`, `IOException`, and `HttpClient`. It only bypasses two specific hostnames: **it is not a complete SSRF solution** for private IP ranges, IPv6, hostname aliases, DNS rebinding, or encoded hostnames.

`select` and any custom selector state must be **thread-safe** when `HttpClient` is shared across multiple requests/threads. `connectFailed` can be used to record proxy connection failures, but is not guaranteed to be called for every HTTP 407/502 status, TLS error, or body read error.

## 8. Distinguishing HTTP proxy and HTTPS CONNECT

### 8.1. HTTP via a forward proxy

When an HTTP client calls an `http://origin.example.test/route` URL through an HTTP proxy, the HTTP/1.1 request sent to the proxy typically has an **absolute-form request-target**:

~~~http
GET http://origin.example.test/route HTTP/1.1
Host: origin.example.test
~~~

The proxy can see the plaintext HTTP URL, headers, and body. It can forward, cache, block, or require authentication. **HTTP does not encrypt data in transit**, so you must consider TLS or network trust boundaries before putting secrets into requests.

### 8.2. HTTPS via an HTTP proxy

When calling an `https://origin.example.test/route` URL through an HTTP proxy, the client typically requests a tunnel:

~~~http
CONNECT origin.example.test:443 HTTP/1.1
Host: origin.example.test:443
~~~

If the proxy allows it, the TLS handshake to the origin takes place through the tunnel. The proxy normally sees the CONNECT hostname/port and connection metadata, but does not read the HTTPS content inside the tunnel **when TLS terminates at the origin and certificates/hostnames are properly verified**.

Do not conclude that a proxy can never read HTTPS: a corporate proxy may perform TLS interception and issue certificates via a CA trusted by the client. In that case, the proxy is an intermediate TLS termination point that can access content according to policy. **Do not disable hostname/certificate verification** just to "fix errors through a proxy."

### 8.3. Proxy port differs from origin port

`https.proxyPort` describes **the port to connect to the proxy** per the Java property. It does not have to equal the origin's 443, nor does it imply the proxy connection itself is TLS-encrypted. With an HTTP forward proxy serving HTTPS via CONNECT, the client uses HTTP to negotiate the tunnel and then TLS to the origin.

## 9. Proxy authentication and origin authentication

| Status/header | Which party uses it? |
|---|---|
| `407 Proxy Authentication Required` | HTTP proxy |
| `Proxy-Authenticate` | Proxy sends challenge |
| `Proxy-Authorization` | Credentials for the proxy |
| `401 Unauthorized` | Origin server |
| `WWW-Authenticate` | Origin sends challenge |
| `Authorization` | Credentials for the origin server |

**Do not copy origin credentials to the proxy or vice versa.** The HTTP proxy and HTTPS origin have different trust scopes. `HttpClient.Builder.authenticator(...)` can provide a `java.net.Authenticator`; the handler should check `RequestorType.PROXY` if the credentials are only meant for the proxy.

~~~java
// Snippet: credentials retrieved from an appropriate secret store, not hardcoded.
Authenticator proxyAuthenticator = new Authenticator() {
    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
        if (getRequestorType() != RequestorType.PROXY) {
            return null;
        }
        return new PasswordAuthentication(proxyUsername, proxyPassword);
    }
};

HttpClient proxyClient = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.corp.example", 3128)))
        .authenticator(proxyAuthenticator)
        .build();
~~~

Here `proxyUsername`/`proxyPassword` are application-provided values from a secret store, and the specific proxy host/port should be checked before supplying them. Imports include `java.net.Authenticator`, `PasswordAuthentication`, `InetSocketAddress`, `ProxySelector`, and `HttpClient`.

Java 17 has the `jdk.http.auth.tunneling.disabledSchemes` policy: according to Oracle, the standard implementation **disables Basic by default** when authenticating an HTTP proxy tunnel over CONNECT. `jdk.http.auth.proxying.disabledSchemes` controls schemes when proxying HTTP. HTTP Basic is only Base64 and **does not encrypt** credentials. When receiving 407, inspect the proxy challenge, JDK policy, auth scope, and connection channel; **do not blindly disable protective policies**.

## 10. Complete runnable Java 17+ example: two HttpClients with two different routes

The program below creates **two `HttpServer` instances on 127.0.0.1**, requiring no Internet:

- **Origin server** returns `ORIGIN`.
- **Fake proxy server** returns `PROXY` and records whether the HTTP request target is an absolute URI. This is **not a full forward proxy**, only used to demonstrate routing.
- `System.setProperty` at the start of main creates a default selector with `http.proxyHost` and `http.nonProxyHosts`. The remote URI is **only passed to `select` for proxy selection, without sending a request to an Internet host**.
- One `HttpClient` uses `ProxySelector.of(...)` pointing to the fake proxy; even though the target URL is loopback, this client goes through its dedicated proxy.
- One `HttpClient` uses `HttpClient.Builder.NO_PROXY` to call the same URL but goes **directly** to the origin.

Because the demo needs to run standalone in a single file, it sets system properties **before creating clients**. In a real service, pass `-D` at JVM startup or use per-client selectors instead of mutating global state.

**File: `ProxyConfigurationDemo.java`**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

public class ProxyConfigurationDemo {
    private static void reply(HttpExchange exchange, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.US_ASCII);
        exchange.sendResponseHeaders(200, bytes.length);
        try (var out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static String get(HttpClient client, URI uri) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3)).GET().build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200) {
            throw new IOException("status " + response.statusCode());
        }
        return response.body();
    }

    public static void main(String[] args) throws Exception {
        // Demonstration only: set JVM-wide settings before creating clients.
        System.setProperty("http.proxyHost", "proxy.example.invalid");
        System.setProperty("http.proxyPort", "3128");
        System.setProperty("http.nonProxyHosts", "localhost|127.*|[::1]");
        ProxySelector defaultSelector = ProxySelector.getDefault();
        URI remote = URI.create("http://service.example.test/resource");
        URI bypass = URI.create("http://127.0.0.1/health");
        List<Proxy> systemSelection = defaultSelector.select(remote);
        List<Proxy> loopbackSelection = defaultSelector.select(bypass);
        System.out.println("defaultRemoteIsHttpProxy=" +
                (!systemSelection.isEmpty()
                        && systemSelection.get(0).type() == Proxy.Type.HTTP));
        System.out.println("defaultLoopbackIsDirect=" +
                (!loopbackSelection.isEmpty()
                        && loopbackSelection.get(0).type() == Proxy.Type.DIRECT));

        InetAddress host = InetAddress.getByName("127.0.0.1");
        HttpServer origin = HttpServer.create(new InetSocketAddress(host, 0), 0);
        HttpServer proxy = HttpServer.create(new InetSocketAddress(host, 0), 0);
        AtomicBoolean absoluteTarget = new AtomicBoolean(false);
        origin.createContext("/", ex -> reply(ex, "ORIGIN"));
        proxy.createContext("/", ex -> {
            absoluteTarget.set(ex.getRequestURI().isAbsolute());
            reply(ex, "PROXY");
        });
        origin.start();
        proxy.start();
        try {
            URI target = new URI("http", null, "127.0.0.1",
                    origin.getAddress().getPort(), "/data", null, null);
            ProxySelector fixedProxy = ProxySelector.of(
                    new InetSocketAddress(host, proxy.getAddress().getPort()));
            HttpClient viaProxy = HttpClient.newBuilder()
                    .proxy(fixedProxy)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpClient direct = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            System.out.println("viaProxyBody=" + get(viaProxy, target));
            System.out.println("directBody=" + get(direct, target));
            System.out.println("proxySawAbsoluteURI=" + absoluteTarget.get());
            System.out.println("clientsHaveExplicitSelectors=" +
                    (viaProxy.proxy().isPresent()
                            && direct.proxy().isPresent()));
        } finally {
            proxy.stop(0);
            origin.stop(0);
        }
    }
}
~~~

Compile and run with **Java 17+**. `jdk.httpserver` is a JDK module used for local testing:

~~~bash
javac --release 17 --add-modules jdk.httpserver ProxyConfigurationDemo.java
java --add-modules jdk.httpserver ProxyConfigurationDemo
~~~

**Verified stdout with `javac --release 17` on OpenJDK 24:**

~~~text
defaultRemoteIsHttpProxy=true
defaultLoopbackIsDirect=true
viaProxyBody=PROXY
directBody=ORIGIN
proxySawAbsoluteURI=true
clientsHaveExplicitSelectors=true
~~~

Meaning:

| Stdout line | Conclusion |
|---|---|
| `defaultRemoteIsHttpProxy=true` | Default selector picks HTTP proxy for the remote URI per system property |
| `defaultLoopbackIsDirect=true` | Default selector bypasses 127.0.0.1 per nonProxyHosts |
| `viaProxyBody=PROXY` | Per-client fixed proxy sends the request to the fake proxy |
| `directBody=ORIGIN` | Per-client `NO_PROXY` sends the request directly to the origin |
| `proxySawAbsoluteURI=true` | Fake proxy receives an HTTP absolute-form request target |
| `clientsHaveExplicitSelectors=true` | Both test clients have explicitly supplied selectors |

**Demo limitations:** both servers are local; the proxy only returns `PROXY` and does not forward; no HTTPS CONNECT, TLS interception, or proxy authentication is performed. The hosts `proxy.example.invalid` and `service.example.test` **receive no network requests**; they are only used as proxy selection data. Do not deploy this fake proxy to production.

## 11. Redirects and proxies are two separate decisions

A request to `https://api.example.test` may receive a redirect `302 Location: https://files.example.test/report`. With a custom ProxySelector, the initial URL and the post-redirect URL can be routed differently.

~~~text
https://api.example.test/orders
     |
     +-- ProxySelector selects proxy A
     |
     +-- HTTP 302 to https://files.example.test/report
               |
               +-- ProxySelector may select proxy B or DIRECT
               |
               +-- Authorization/Cookie scope needs re-evaluation
~~~

- `followRedirects(HttpClient.Redirect.NEVER/NORMAL/ALWAYS)` controls whether redirects are followed automatically.
- `proxy(ProxySelector)` controls the route for each URI.
- `Authorization`, `Cookie`, `Proxy-Authorization`, or `Authenticator` controls credentials according to the proper trust boundary.

**Do not forward the initial API's token to a different host just because the redirect resolved a valid proxy.** Proxy policy does not automatically grant authorization to the new origin.

## 12. Common pitfalls

| Symptom | Common cause | How to check |
|---|---|---|
| Set `http.proxyHost` but requests still go direct | Client has `NO_PROXY`/custom selector or host is bypassed | Inspect the exact HttpClient instance and selector |
| `client.proxy().isEmpty()` yet traffic goes through proxy | Default selector is used implicitly | Do not use the Optional to infer routing |
| 127.0.0.1 does not go through default proxy | Loopback bypass in `http.nonProxyHosts` | Usually expected behavior |
| Set `https.nonProxyHosts` with no effect | HTTPS uses `http.nonProxyHosts` per Java 17 | Use the right property/custom selector |
| Bypass host list uses commas | Java uses `\|` | Fix the pattern and shell quoting |
| Enabling `useSystemProxies` at runtime has no effect | Property is read at startup | Use `-Djava.net.useSystemProxies=true` |
| OS has `HTTPS_PROXY` but Java does not use proxy | Shell env is not automatically a Java system property | Set `-D` or builder.proxy |
| Proxy connection refused | Wrong proxy host/port or firewall | Check TCP/DNS and proxy logs |
| Proxy returns 407 | Missing auth or scheme disabled | Check Authenticator, 407, and JDK policy |
| HTTPS via proxy fails handshake | CONNECT, intercepting CA, hostname/truststore | Fix certificate/trust, do not trust-all |
| Changed `ProxySelector.setDefault` but old client did not change | Client captured default selector at build time | Build a new client |
| Fixed proxy still receives localhost | `ProxySelector.of` is not the default selector with bypass | Use a custom selector if bypass is needed |
| Built `HttpClient` cannot change proxy | Client config is immutable | Create a new instance |
| HTTP/2 not negotiated via proxy | HTTP version/implementation constraints | Check `HttpResponse.version()` |
| Custom selector misbehaves under high load | Non-thread-safe shared mutable state | Use immutable snapshots/synchronization |
| Request takes wrong route after redirect | New URI has a different policy | Check each redirect hop |

### 12.1. Systematic debugging checklist

1. Confirm the JDK version, JVM `-D` arguments, and configuration source (without logging secrets).
2. Check whether the target URI is `http` or `https`, along with its hostname and port.
3. Determine whether the client uses the **default**, **fixed**, **NO_PROXY**, or **custom** selector.
4. If default, inspect `http.proxyHost`, `https.proxyHost`, `http.nonProxyHosts`, and `java.net.useSystemProxies`.
5. If custom, test `select(uri)` on each hostname; do not assume the selector automatically uses Java properties.
6. Observe TCP errors to the proxy, HTTP 407, and HTTPS CONNECT/TLS separately.
7. Check the redirect policy and credentials at each hop.
8. Avoid mutating JVM global state while analyzing a live request; create an isolated test client/selector to reproduce.

## 13. Self-check questions

**1. Does `-Dhttp.proxyHost=...` force every HttpClient to go through the proxy?** No; a builder can provide its own selector.

**2. If `builder.proxy(...)` is not set, what does Java 17 HttpClient use?** The JVM's default ProxySelector.

**3. Does `HttpClient.proxy().isEmpty()` mean direct?** No; an implicit default selector may be in use.

**4. Which API makes a client always direct?** `builder.proxy(HttpClient.Builder.NO_PROXY)`.

**5. Which API sets a fixed HTTP proxy?** `builder.proxy(ProxySelector.of(new InetSocketAddress(host,port)))`.

**6. Does `ProxySelector.of(...)` automatically obey `http.nonProxyHosts`?** Do not assume so; it is a fixed selector, different from the default selector.

**7. What is the HTTPS bypass property in Java 17?** `http.nonProxyHosts` is also used for HTTPS.

**8. When must `java.net.useSystemProxies` be set?** At JVM startup.

**9. Is shell `HTTPS_PROXY` guaranteed to be used by Java 17 HttpClient?** Not by default.

**10. What delimiter does `http.nonProxyHosts` use?** `|`, with wildcard `*`.

**11. What does HTTPS over an HTTP proxy typically use to establish a tunnel?** `CONNECT host:443`, followed by TLS to the origin.

**12. How does 407 differ from 401?** 407 is proxy authentication, 401 is origin server authentication.

**13. Why might Basic be rejected for HTTPS CONNECT?** JDK 17's `jdk.http.auth.tunneling.disabledSchemes` policy blocks Basic by default.

**14. Does changing the default selector after creating a client guarantee the old client switches routes?** No; system-wide defaults are captured when the client is created.

**15. Why does the demo print both `PROXY` and `ORIGIN` for the same target?** The two HttpClients have different selectors; one goes to the fake proxy, one goes directly.

## 14. Official documentation

- [Java SE 17 – Networking Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html): proxyHost/Port, nonProxyHosts, SOCKS, and useSystemProxies.
- [Java SE 17 – Java Networking](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): Java proxy properties, OS settings, and proxy auth policies.
- [Java SE 17 – HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `proxy(ProxySelector)`, `NO_PROXY`, `authenticator`.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): default selector, `proxy()` Optional, immutable configuration.
- [Java SE 17 – ProxySelector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html): `getDefault`, `setDefault`, `select`, `connectFailed`, `of`.
- [Java SE 17 – Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Proxy.html): `Proxy.NO_PROXY` and proxy types.
- [Java SE 17 – Authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Authenticator.html): distinguishing proxy/origin authentication.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): local demo.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): CONNECT, 401, and 407.
- [RFC 9112 – HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): absolute-form request-target when going through a proxy.

**Key takeaway:** Java proxy properties and `ProxySelector.getDefault()` determine the **JVM-wide default route**. `HttpClient.Builder.proxy(...)` determines the **client's own route**: `ProxySelector.of` for a fixed proxy, `NO_PROXY` for direct, and a custom selector for URI-based routing. For HTTPS, understand CONNECT/TLS; for credentials, distinguish 407/proxy auth from 401/origin auth. Do not mutate global JVM properties before every request; verify the exact policy of the client actually sending HTTP.
