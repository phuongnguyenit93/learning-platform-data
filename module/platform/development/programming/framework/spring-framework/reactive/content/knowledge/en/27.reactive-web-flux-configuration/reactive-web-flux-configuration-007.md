# `ForwardedHeaderTransformer` and Proxy Trust Boundaries in Spring WebFlux

## 1. The Problem: The Application Needs to Know Where the Original Request Came From

A WebFlux application typically runs behind a reverse proxy, ingress controller, or load balancer. Clients access the public address:

```text
https://api.example.com/orders
```

The proxy terminates TLS and forwards the request onto the internal network:

```text
http://orders-service:8080/orders
```

When the request arrives at the application, the direct TCP connection is from the proxy to `orders-service`. Therefore, looking only at the request received by the server, the application might see:

- Scheme as `http`, even though the client used HTTPS.
- Host as `orders-service`, not `api.example.com`.
- Port as `8080`, not `443`.
- Remote address as the proxy's IP, not the original client IP.
- Internal path possibly containing a context prefix that external clients do not see.

The proxy can forward metadata about the original request via HTTP headers. Spring WebFlux provides `ForwardedHeaderTransformer` to read these headers, adjust request information, and strip the processed headers.

However, forwarded headers are data that any HTTP client can send itself. If the application trusts them without controlling the proxy, clients can spoof host, scheme, or IP address. This is the single most important trust boundary of this topic.

After this lesson, you will be able to:

1. Distinguish RFC 7239 `Forwarded` from the `X-Forwarded-*` group.
2. Understand how `ForwardedHeaderTransformer` modifies request URIs and addresses.
3. Register the transformer in Spring WebFlux and configure Spring Boot.
4. Distinguish `FRAMEWORK`, `NATIVE`, and `NONE`.
5. Design a proxy at the trust boundary to strip spoofed forwarded headers.
6. Handle multiple proxies, client IPs, external HTTPS, and URL prefixes.
7. Use `removeOnly` when you only need to strip forwarded headers without using them.
8. Test behavior with `WebTestClient` and `MockServerHttpRequest`.

## 2. Why Do Proxies Alter Request Information?

Consider the model:

```text
Browser
  |
  | HTTPS https://api.example.com/orders
  v
Reverse proxy / ingress
  | - TLS termination
  | - public host: api.example.com
  | - public port: 443
  | - client address: 203.0.113.25
  |
  | HTTP http://orders-service:8080/orders
  v
Spring WebFlux
```

An application behind a proxy receives connections from the proxy. Without forwarded metadata, the request may appear as follows:

| Information | Client Sees | Backend Sees |
|---|---|---|
| Scheme | `https` | `http` |
| Host | `api.example.com` | `orders-service` |
| Port | `443` | `8080` |
| Remote address | `203.0.113.25` | Proxy IP |
| Public path | `/orders` | Possibly `/internal/orders` |

This mismatch affects more than just displaying information:

- Redirects may return URLs like `http://orders-service:8080/...`.
- Absolute links in JSON/HTML may contain internal hostnames.
- `Secure` cookies or HTTPS checks may behave incorrectly.
- OAuth2 redirect URIs may be generated with the wrong scheme/host.
- Audit logs, rate limiting, or IP-based policies may mistakenly use the proxy address.
- Applications placed behind a path prefix may generate incorrect links.

Forwarded headers allow the proxy to communicate certain attributes of the original request when forwarding. WebFlux needs to turn that metadata into a request matching the external client's perspective.

## 3. Two Families of Forwarded Headers

There are two common header styles.

### 3.1. Standard `Forwarded` Header per RFC 7239

RFC 7239 defines a standard header that can contain multiple attributes:

```http
Forwarded: for=203.0.113.25;proto=https;host=api.example.com
```

Key attributes:

| Attribute | Meaning |
|---|---|
| `for` | Client address or hop preceding the proxy |
| `by` | Address of the proxy creating the entry |
| `host` | Original host accessed by the client |
| `proto` | Original protocol, usually `http` or `https` |

A chain of multiple proxies can have multiple comma-separated elements:

```http
Forwarded: for=203.0.113.25;proto=https;host=api.example.com,
           for=10.10.0.12;by=10.10.0.20
```

IPv6 values, obfuscated identifiers, and strings with special characters have specific quoting rules. Do not manually split headers with `split(",")` or `split(";")` to build security logic.

### 3.2. `X-Forwarded-*` Header Group

This is the header group widely used prior to RFC 7239:

```http
X-Forwarded-For: 203.0.113.25
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
```

Common headers:

| Header | Meaning |
|---|---|
| `X-Forwarded-For` | Client / preceding hop IP |
| `X-Forwarded-Host` | Public host |
| `X-Forwarded-Proto` | Public scheme |
| `X-Forwarded-Port` | Public port |
| `X-Forwarded-Ssl` | SSL status, typically `on` or `off` |
| `X-Forwarded-Prefix` | Public path prefix stripped or modified by the proxy when forwarding |

`X-Forwarded-*` is a de facto convention, not a unified standard header group in RFC 7239. Different proxies may support different subsets of headers. Applications must know which ones their proxy sends.

### 3.3. Example Request Passing Through a Proxy

The backend request might look like:

```http
GET /orders HTTP/1.1
Host: orders-service:8080
X-Forwarded-For: 203.0.113.25
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
```

The backend still receives an internal HTTP connection, but the forwarded headers describe the public request sent by the client.

`ForwardedHeaderTransformer` can use this information to adjust the request URI and corresponding address before creating `ServerWebExchange`.

## 4. What Does `ForwardedHeaderTransformer` Do?

`ForwardedHeaderTransformer` belongs to the package:

```java
org.springframework.web.server.adapter.ForwardedHeaderTransformer
```

This is Spring WebFlux's mechanism, corresponding to `ForwardedHeaderFilter` in the Servlet stack.

When registered, the transformer:

1. Checks whether the request contains forwarded headers.
2. Reads host, port, and scheme information from `Forwarded` or `X-Forwarded-*`.
3. May update remote/local addresses from `for`/`by` information.
4. Processes `X-Forwarded-Prefix` according to configuration.
5. Removes processed forwarded headers from the request.
6. Returns the adjusted request so WebFlux creates the exchange and continues processing.

Model:

```text
Incoming ServerHttpRequest
        |
        v
ForwardedHeaderTransformer
        |
        +---- No forwarded headers
        |          |
        |          v
        |     Keep original request
        |
        +---- Has forwarded headers
                   |
                   v
             Read metadata
                   |
                   v
          Update URI/address
                   |
                   v
          Remove forwarded headers
                   |
                   v
          ServerWebExchange
                   |
                   v
          WebFilter / Controller
```

The transformer runs early, before `ServerWebExchange` is created. As a result, controllers, WebFilters, and downstream components see the adjusted request.

### 4.1. Request URI Is Adjusted

Example original request arriving at the backend:

```text
http://orders-service:8080/orders/42
```

Header sent by the proxy:

```http
Forwarded: for=203.0.113.25;proto=https;host=api.example.com:443
```

After processing, the URI seen by the application may be:

```text
https://api.example.com:443/orders/42
```

APIs commonly affected:

```java
ServerHttpRequest request = exchange.getRequest();

URI uri = request.getURI();

String scheme = uri.getScheme();
String host = uri.getHost();
int port = uri.getPort();
String path = uri.getRawPath();

InetSocketAddress remoteAddress = request.getRemoteAddress();
```

There is no need to read headers manually and rewrite URIs in every controller. The transformer provides centralized handling at the WebFlux layer.

### 4.2. Remote Address Can Be Updated

If present:

```http
X-Forwarded-For: 203.0.113.25
```

the transformer can update `ServerHttpRequest.getRemoteAddress()` to the forwarded address.

This is convenient for logging or constructing request metadata. However, after the transformer runs, the remote address may represent the client from the forwarded header rather than the direct TCP peer (the proxy).

Therefore, do not use the adjusted remote address to identify which proxy is directly connected. Peer/trust boundary checks must happen at the network layer or a layer with access to the real connection address.

### 4.3. Forwarded Headers Are Stripped After Processing

After the transformer consumes the metadata, headers such as `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and related headers are removed from the adjusted request.

This prevents downstream code from accidentally re-processing the same data. If controllers need the information, read the adjusted URI or remote address.

Do not write code assuming controllers will always still see `X-Forwarded-For` after the transformer has run.

## 5. Registering the Transformer in Spring WebFlux

`WebHttpHandlerBuilder` can automatically detect a bean named exactly `forwardedHeaderTransformer`.

In plain Spring Framework, it can be registered as:

```java
@Configuration
public class ForwardedHeaderConfiguration {

    @Bean
    public ForwardedHeaderTransformer forwardedHeaderTransformer() {
        return new ForwardedHeaderTransformer();
    }
}
```

Keep the bean name `forwardedHeaderTransformer` so WebFlux detects and uses it.

There is no need to create a custom `WebFilter` to read forwarded headers manually. The transformer runs earlier, before the exchange is created.

### 5.1. Do Not Confuse `ForwardedHeaderFilter` with the Transformer

| Component | Stack | Role |
|---|---|---|
| `ForwardedHeaderFilter` | Spring MVC / Servlet | Wraps Servlet request/response to apply forwarded headers |
| `ForwardedHeaderTransformer` | Spring WebFlux / Reactive | Adjusts `ServerHttpRequest` before creating exchange |

If the application uses `spring-boot-starter-webflux`, use `ForwardedHeaderTransformer`.

`ForwardedHeaderFilter` belongs to the Servlet stack. Do not register it as a reactive `WebFilter`.

## 6. Spring Boot Configuration: FRAMEWORK, NATIVE, and NONE

Spring Boot has the property:

```properties
server.forward-headers-strategy=FRAMEWORK
```

Three main options:

| Value | Meaning |
|---|---|
| `FRAMEWORK` | Uses Spring Framework's forwarded header handling; WebFlux uses `ForwardedHeaderTransformer` |
| `NATIVE` | Uses the embedded server/container's native forwarded header support |
| `NONE` | Does not enable forwarded header handling |

For WebFlux, configure Spring Framework mode:

```properties
server.forward-headers-strategy=FRAMEWORK
```

Or YAML:

```yaml
server:
  forward-headers-strategy: FRAMEWORK
```

Boot configures forwarded header support at the Framework layer according to this strategy.

### 6.1. When to Choose FRAMEWORK?

Choose `FRAMEWORK` when:

- You want Spring WebFlux to handle forwarded headers.
- You need consistent behavior across different connectors.
- You want to use `ForwardedHeaderTransformer`.
- You need `removeOnly` or want control over the transformer bean.

### 6.2. When to Choose NATIVE?

`NATIVE` asks the embedded server to process forwarded headers. Exact behavior depends on the connector/server and version.

If using native support, read the documentation for the specific embedded server you run. Do not assume all containers handle every header identically.

### 6.3. Avoid Double Processing

Do not enable forwarded header processing in both the native server and Spring Framework simultaneously without an explicit design.

If both layers modify the URI or remote address, requests can be transformed twice or yield unpredictable results.

Pick one clear strategy:

- `FRAMEWORK`: Spring handles it.
- `NATIVE`: the container handles it.
- `NONE`: neither handles it.

## 7. Trust Boundaries: Why Are Forwarded Headers Dangerous?

Any HTTP client can send headers itself:

```http
X-Forwarded-For: 127.0.0.1
X-Forwarded-Host: admin.internal
X-Forwarded-Proto: https
```

If a request reaches the application directly and the transformer trusts these values, the application may think the request came from localhost, an internal admin host, or an HTTPS connection.

This is request metadata spoofing.

`ForwardedHeaderTransformer` does not verify that headers were added by a trusted proxy. It is not a proxy allowlist, does not validate signatures, and does not check that the direct connection address belongs to a valid proxy.

### 7.1. The Proxy at the Trust Boundary Must Strip Client-Supplied Data

Crucial rule:

> The first proxy at the trust boundary must remove forwarded headers sent by external clients, then regenerate forwarded values from metadata that the proxy itself has verified.

Both families must be handled:

- `Forwarded`
- All `X-Forwarded-*` headers used by the application or infrastructure

If a proxy merely appends a value to an existing client header, an attacker can inject spoofed values into the chain.

Dangerous example:

```http
X-Forwarded-For: 127.0.0.1
```

Proxy appends the real client IP without stripping the old header:

```http
X-Forwarded-For: 127.0.0.1, 203.0.113.25
```

If a downstream component trusts the first element without a clear trust policy, it may accept the spoofed IP.

### 7.2. The Proxy Should Generate Headers from Connections It Verifies

An edge proxy can produce:

```http
X-Forwarded-For: 203.0.113.25
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
```

These values must come from the connection and host verified by the proxy.

If a proxy receives requests through another upstream proxy, configure the trust chain at the proxy layer. Do not blindly trust every address present in client-sent headers.

### 7.3. Block Direct Access to the Backend

Even when the proxy is properly configured, the application can still be attacked if clients connect directly to the backend and send spoofed forwarded headers.

Apply defense in depth:

- Backend accepts traffic only from the proxy's subnet/security group.
- Kubernetes NetworkPolicy allows only ingress/gateway to connect to the service.
- Do not expose backend ports directly to the Internet.
- Edge proxy strips forwarded headers from external requests.
- Regenerate only headers defined in the system contract.
- Public hostnames should be restricted to permitted domains.

`ForwardedHeaderTransformer` processes metadata; controlling who may supply metadata is the responsibility of network and proxy architecture.

## 8. Secure Reverse Proxy Configuration

Example Nginx forwarding HTTPS to an internal HTTP WebFlux application:

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location / {
        proxy_pass http://orders-service:8080;

        proxy_set_header Host $host;

        # Strip standard header sent by the client.
        proxy_set_header Forwarded "";

        # Record metadata from the connection directly received by the proxy.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;

        # Do not send prefix if the proxy does not rewrite paths.
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";
    }
}
```

This is an illustrative configuration for an edge proxy. In a multi-proxy environment, configure real IP/trusted upstream settings appropriately and only append information from verified proxies.

If the application uses other `X-Forwarded-*` headers, the proxy must also strip or overwrite them according to the contract. Never let client-supplied values cross the trust boundary.

### 8.1. Why Use `$remote_addr` at the Edge Proxy?

`$remote_addr` is the peer from which Nginx directly receives the TCP connection. When Nginx is the edge proxy, it can use that value to record the observed client address.

If Nginx sits behind another load balancer, `$remote_addr` may be the load balancer's address. In that case, configure a trusted real-IP source and explicit proxy chain. Do not enable trusting all IP sources.

### 8.2. Do Not Blindly Use `$proxy_add_x_forwarded_for`

`$proxy_add_x_forwarded_for` normally appends `$remote_addr` to an existing `X-Forwarded-For` value.

If the existing value came directly from the client without sanitization, the resulting chain still contains spoofed data.

Only append when the proxy has verified and sanitized the chain from a trusted upstream. At the edge proxy, overwriting is usually easier to control.

## 9. Multiple Proxies and Client Address Chains

A request may traverse multiple hops:

```text
Client
  |
  v
Edge proxy
  |
  v
Internal load balancer
  |
  v
Ingress
  |
  v
WebFlux application
```

Proxies can build a chain:

```http
X-Forwarded-For: client-ip, proxy-1, proxy-2
```

Or:

```http
Forwarded: for=client-ip;proto=https,
           for=proxy-1,
           for=proxy-2
```

Values in the chain are trustworthy only when every hop is governed by a clear trust policy.

### 9.1. Do Not Treat the First Element as Trusted IP by Default

Many systems take the first element in `X-Forwarded-For` as the client IP. That is only valid if the proxy at the trust boundary stripped any initial spoofed header and subsequent proxies follow the contract.

Otherwise, a client can inject a fake first element and proxies simply append other addresses after it.

### 9.2. Define Which Proxies Are Allowed to Add Metadata

In a multi-proxy system:

1. Identify which proxy is the trust boundary.
2. Strip forwarded headers from untrusted traffic.
3. Define which proxies are permitted to append to the chain.
4. Set limits and rules for selecting the client address.
5. Block direct access paths to the backend.
6. Test both legitimate chain requests and attempts to spoof headers.

`ForwardedHeaderTransformer` does not replace a trusted-proxy allowlist. It processes values supplied according to the header contract; deciding which sources may produce those values must be solved in infrastructure.

## 10. `X-Forwarded-Prefix`: Application Published Under a Different Path

A common case is when a proxy exposes a public path prefix different from the backend path.

Example:

```text
Public:
https://example.com/api/orders

Backend:
http://orders-service:8080/orders
```

The proxy can send:

```http
X-Forwarded-Prefix: /api
```

The transformer uses the prefix to adjust the context path and request URL from the external perspective.

Some deployment patterns:

| Mapping | Prefix Sent by Proxy | Purpose |
|---|---|---|
| `/api/{path}` → backend `/{path}` | `/api` | Add public prefix |
| `/app1/{path}` → backend `/{path}` | `/app1` | Preserve application prefix |
| `/api/app1/{path}` → backend `/app1/{path}` | `/api/app1` | Change public prefix |
| `/app1/{path}` → public `/{path}` | Empty prefix | Remove internal prefix |

`X-Forwarded-Prefix` is not part of RFC 7239. It is a custom convention header and must be generated accurately by the proxy.

### 10.1. Prefixes and Route Mapping

Do not manually prepend `X-Forwarded-Prefix` to every controller path. The transformer adjusts request/context paths at the framework layer. Test actual routes against your application mappings, especially when you have:

- `@RequestMapping`
- WebFlux functional routes
- Context path
- Static resource paths
- Redirects
- URL generation

If the proxy does not rewrite paths, do not send a synthetic prefix.

## 11. `removeOnly`: Stripping Forwarded Headers Without Using Them

In some cases, an application does not want to use forwarded metadata but still needs to strip these headers so downstream code does not accidentally read them.

`ForwardedHeaderTransformer` has the property:

```java
setRemoveOnly(true)
```

Spring Framework configuration example:

```java
@Configuration
public class ForwardedHeaderConfiguration {

    @Bean
    public ForwardedHeaderTransformer forwardedHeaderTransformer() {
        ForwardedHeaderTransformer transformer =
                new ForwardedHeaderTransformer();

        transformer.setRemoveOnly(true);

        return transformer;
    }
}
```

In this mode:

- `Forwarded` and `X-Forwarded-*` are stripped.
- The URI is not adjusted based on those headers.
- Remote/local addresses are not updated from forwarded metadata.
- The request proceeds with information from the actual backend connection.

Use `removeOnly` when:

- The backend does not need to know public scheme/host/client IP.
- You want to ensure downstream code cannot read forwarded headers arbitrarily.
- Proxies are not yet configured reliably enough to trust forwarded metadata.
- The application has its own request metadata handling policy.

`removeOnly` does not authenticate proxies and does not prevent direct client connections. It simply ignores forwarded values and strips them.

### 11.1. Do Not Enable Two Processing Mechanisms Simultaneously

When using Spring Boot `server.forward-headers-strategy=FRAMEWORK`, Boot configures the Framework mechanism. When customizing `removeOnly`, declare the transformer bean properly and verify your Boot version's auto-configuration so only one handler is active.

When using `NATIVE`, do not simultaneously have both server-native support and a Spring transformer adjusting the request without an explicit design.

## 12. Impact on Redirects, HTTPS, and Spring Security

### 12.1. Redirects Need Public Scheme and Host

If the backend receives internal HTTP while clients access HTTPS, the application can generate redirects based on the adjusted URI:

```text
Client -> https://api.example.com/login
Proxy  -> http://app:8080/login
```

If the application does not know the original scheme is HTTPS, a redirect can become:

```http
Location: http://app:8080/login
```

Once forwarded headers are handled properly, the framework can build more accurate public URLs.

### 12.2. Host Headers Affect Absolute URLs

Some features build absolute links or redirects based on the request host. If an application blindly trusts `X-Forwarded-Host`, an attacker can cause emails, redirects, or password-reset links to point to an attacker-controlled domain.

Restrict permitted hosts at the proxy/ingress and do not use an unverified forwarded host to generate sensitive links.

### 12.3. Spring Security and Secure Channels

Policies based on scheme/secure requests need to see the properly adjusted information. If TLS terminates at the proxy, the backend may receive HTTP; the forwarded transformer lets WebFlux know the original request was HTTPS.

However, forwarded headers are not proof of client identity. Never use `X-Forwarded-For` to replace authentication, authorization, or CSRF checks.

When Spring Security is present, also test:

- HTTPS redirects.
- OAuth2 redirect URIs.
- Secure channel policies.
- Secure cookies.
- Host allowlists.
- Direct requests to the backend with spoofed forwarded headers.

## 13. `FRAMEWORK` vs `NATIVE` and Avoiding Duplicate Processing

| Configuration | Processing Component | Key Point |
|---|---|---|
| `FRAMEWORK` | Spring WebFlux `ForwardedHeaderTransformer` | Behavior managed by Spring Framework |
| `NATIVE` | Embedded server/connector | Behavior varies by server and version |
| `NONE` | No forwarded header processing | Request keeps backend connection metadata |

If using Reactor Netty native forwarded support, the server can also read `Forwarded` or `X-Forwarded-*`. Pick the right header family sent by your proxy and read the documentation for your exact Reactor Netty version.

Do not enable native forwarding and also register a transformer with the same responsibility without understanding execution order and transformation results. A request's URI or remote address could be updated multiple times.

For the Spring Boot WebFlux project in this hands-on lesson, use `FRAMEWORK` to clearly demonstrate `ForwardedHeaderTransformer` behavior.

## 14. Observing Requests After Transformation

A controller can read the adjusted request information:

```java
@GetMapping("/request-info")
public Mono<Map<String, Object>> requestInfo(
        ServerWebExchange exchange) {

    ServerHttpRequest request = exchange.getRequest();
    URI uri = request.getURI();

    Map<String, Object> result = new LinkedHashMap<>();
    result.put("scheme", uri.getScheme());
    result.put("host", uri.getHost());
    result.put("port", uri.getPort());
    result.put("path", uri.getRawPath());
    result.put("remoteAddress", request.getRemoteAddress());

    return Mono.just(result);
}
```

This is how metadata is observed at the application layer. Do not return all forwarded headers to clients or log raw header values indiscriminately.

### Do Headers Still Exist After Transformation?

You can check:

```java
boolean hasForwarded =
        request.getHeaders().containsKey("Forwarded");

boolean hasXForwardedFor =
        request.getHeaders().containsKey("X-Forwarded-For");
```

If the transformer processed them, the corresponding headers have normally been removed. This is intentional behavior.

If you need to audit raw forwarded headers, record the proxy-verified metadata in proxy/access logs or a secure observability channel before the transformer strips them. Do not keep raw values in controllers just for debugging.

## 15. Diagnosing Common Issues

### 15.1. Redirect Returns HTTP Instead of HTTPS

Check:

- Does the proxy send `X-Forwarded-Proto: https` or `Forwarded: proto=https`?
- Is `server.forward-headers-strategy` set to `FRAMEWORK` or an appropriate native strategy?
- Does the backend actually receive the header?
- Is another proxy overwriting the scheme?
- Are two layers processing forwarded headers simultaneously?

### 15.2. Host in Links Is an Internal Hostname

Check:

- Does the proxy send `X-Forwarded-Host` or `Forwarded: host=...`?
- Is Host overwritten from `$host`/verified public host?
- Is the backend using a forwarded transformer?
- Is there a host allowlist at the proxy or application?

### 15.3. Client IP Is Always the Proxy IP

Check:

- Does the proxy send `X-Forwarded-For` or `Forwarded: for=...`?
- Does the proxy strip client-supplied values before creating new headers?
- Is Framework/native forwarding enabled?
- Is `removeOnly` enabled?
- Is the controller reading remote address before or after transformation?

### 15.4. Client IP Can Be Spoofed

If clients can connect directly to the backend or the edge proxy merely appends headers, the forwarded IP is untrustworthy.

Fix at the trust boundary:

1. Block direct access paths to the backend.
2. Strip client-sent forwarded headers.
3. Regenerate metadata from verified connections.
4. Configure explicit proxy chain and real-IP policies.
5. Test spoofed requests from outside.

### 15.5. Routes Break When a Prefix Is Present

Check:

- Does the proxy rewrite paths or not?
- Does `X-Forwarded-Prefix` match the public path?
- Is the prefix sent twice?
- Is the application's context path configured independently?
- Are both a transformer and native support processing the prefix twice?

### 15.6. Forwarded Headers Are Not Stripped

Check:

- Is the transformer detected with bean name `forwardedHeaderTransformer`?
- Is Boot's strategy set to `FRAMEWORK`?
- Is a native strategy active instead of Framework?
- Does the request pass through a properly configured WebFlux `WebHttpHandlerBuilder`?

## 16. Runnable Java 17+ Project: ForwardedHeaderTransformer with WebTestClient

Sample project uses:

- Java 17.
- Spring Boot 3.3.5.
- Spring WebFlux.
- JUnit 5 and Spring Test.
- `WebTestClient` to send requests with forwarded headers.

Spring Boot 3.3.5 manages Spring Framework 6.1.14. Thus the example uses the no-arg constructor of `ForwardedHeaderTransformer` and `setRemoveOnly(boolean)`, compatible with this version.

The project verifies three behaviors:

1. Standard `Forwarded` changes scheme, host, and port of the request.
2. `X-Forwarded-*` can also alter metadata when `Forwarded` is absent.
3. `removeOnly` strips forwarded headers while keeping the internal URI intact.

### 16.1. Project Structure

```text
forwarded-headers-webflux/
├── pom.xml
└── src/
    ├── main/java/edu/demo/forwarded/
    │   ├── ForwardedApplication.java
    │   ├── RequestInfo.java
    │   └── RequestInfoController.java
    └── test/java/edu/demo/forwarded/
        ├── ForwardedHeadersIntegrationTests.java
        └── ForwardedHeaderTransformerTests.java
```

### 16.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>forwarded-headers-webflux</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 16.3. `application.properties`

```properties
server.forward-headers-strategy=FRAMEWORK
```

This setting tells Spring Boot to use Spring Framework's forwarded header mechanism for WebFlux.

### 16.4. `ForwardedApplication.java`

```java
package edu.demo.forwarded;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ForwardedApplication {

    public static void main(String[] args) {
        SpringApplication.run(ForwardedApplication.class, args);
    }
}
```

### 16.5. `RequestInfo.java`

```java
package edu.demo.forwarded;

public record RequestInfo(
        String scheme,
        String host,
        int port,
        String path,
        String remoteAddress,
        boolean forwardedHeadersPresent) {
}
```

Record representing request details after WebFlux processes forwarded headers.

### 16.6. `RequestInfoController.java`

```java
package edu.demo.forwarded;

import java.net.InetSocketAddress;
import java.net.URI;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.http.server.reactive.ServerHttpRequest;

import reactor.core.publisher.Mono;

@RestController
public class RequestInfoController {

    @GetMapping("/inspect")
    public Mono<RequestInfo> inspect(ServerWebExchange exchange) {
        ServerHttpRequest request = exchange.getRequest();
        URI uri = request.getURI();

        InetSocketAddress remote = request.getRemoteAddress();

        String remoteAddress =
                remote == null ? null : remote.getHostString();

        boolean forwardedHeadersPresent =
                request.getHeaders().containsKey("Forwarded")
                || request.getHeaders().containsKey("X-Forwarded-For")
                || request.getHeaders().containsKey("X-Forwarded-Host")
                || request.getHeaders().containsKey("X-Forwarded-Proto")
                || request.getHeaders().containsKey("X-Forwarded-Port")
                || request.getHeaders().containsKey("X-Forwarded-Prefix");

        RequestInfo info = new RequestInfo(
                uri.getScheme(),
                uri.getHost(),
                uri.getPort(),
                uri.getRawPath(),
                remoteAddress,
                forwardedHeadersPresent);

        return Mono.just(info);
    }
}
```

The controller reads the URI and remote address adjusted by WebFlux. `forwardedHeadersPresent` lets tests confirm the transformer removed the processed headers.

### 16.7. `ForwardedHeadersIntegrationTests.java`

```java
package edu.demo.forwarded;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "server.forward-headers-strategy=FRAMEWORK")
@AutoConfigureWebTestClient
class ForwardedHeadersIntegrationTests {

    @Autowired
    WebTestClient client;

    @Test
    void standardForwardedHeaderReconstructsPublicRequest() {
        client.get()
                .uri("/inspect")
                .header(
                        "Forwarded",
                        "for=192.0.2.60;proto=https;host=api.example.test:443")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.scheme").isEqualTo("https")
                .jsonPath("$.host").isEqualTo("api.example.test")
                .jsonPath("$.port").isEqualTo(443)
                .jsonPath("$.path").isEqualTo("/inspect")
                .jsonPath("$.forwardedHeadersPresent").isEqualTo(false);
    }

    @Test
    void xForwardedHeadersReconstructPublicRequest() {
        client.get()
                .uri("/inspect")
                .header("X-Forwarded-For", "192.0.2.61")
                .header("X-Forwarded-Host", "portal.example.test")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Port", "443")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.scheme").isEqualTo("https")
                .jsonPath("$.host").isEqualTo("portal.example.test")
                .jsonPath("$.port").isEqualTo(443)
                .jsonPath("$.forwardedHeadersPresent").isEqualTo(false);
    }
}
```

These two tests send forwarded headers directly to verify transformer behavior. In production, only enable using headers when requests arrive from trusted proxies and the proxy has sanitized client-supplied data.

### 16.8. `ForwardedHeaderTransformerTests.java`

```java
package edu.demo.forwarded;

import org.junit.jupiter.api.Test;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.web.server.adapter.ForwardedHeaderTransformer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class ForwardedHeaderTransformerTests {

    @Test
    void removeOnlyDiscardsHeadersWithoutChangingRequestUri() {
        ServerHttpRequest original =
                MockServerHttpRequest
                        .get("http://internal.example:8080/inspect")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-Host", "public.example.test")
                        .build();

        ForwardedHeaderTransformer transformer =
                new ForwardedHeaderTransformer();

        transformer.setRemoveOnly(true);

        ServerHttpRequest transformed =
                transformer.apply(original);

        assertEquals(
                "http",
                transformed.getURI().getScheme());

        assertEquals(
                "internal.example",
                transformed.getURI().getHost());

        assertEquals(
                8080,
                transformed.getURI().getPort());

        assertFalse(
                transformed.getHeaders()
                        .containsKey("X-Forwarded-Proto"));

        assertFalse(
                transformed.getHeaders()
                        .containsKey("X-Forwarded-Host"));
    }
}
```

This test confirms `removeOnly` keeps the internal URI intact and removes the incoming headers.

### 16.9. Running Tests

From the directory containing `pom.xml`:

```bash
mvn test
```

When Maven resolves dependencies and assertions pass, the test suite has three cases:

1. RFC 7239 `Forwarded` alters scheme/host/port and headers are removed.
2. `X-Forwarded-*` alters scheme/host/port and headers are removed.
3. `removeOnly` strips headers while preserving the original scheme/host/port.

Expected output:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

This is the expected result to check after running Maven; this document does not claim the tests were executed in the authoring environment.

## 17. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Trusting every `X-Forwarded-For` from clients | Clients spoof IP addresses | Edge proxy strips external values and regenerates them |
| Stripping only `X-Forwarded-*` while leaving `Forwarded` | Standard header can still be spoofed | Handle both header families |
| Proxy only appends to existing XFF | Spoofed client value remains in the chain | Sanitize at the trust boundary before appending |
| Exposing backend directly | Clients bypass proxy and send fake forwarded headers | Firewall, security group, or NetworkPolicy |
| Using `ForwardedHeaderFilter` in WebFlux | Wrong stack abstraction | Use `ForwardedHeaderTransformer` |
| Registering bean with wrong name | WebFlux does not auto-detect transformer | Use bean name `forwardedHeaderTransformer` |
| Wrapping transformer as a `WebFilter` | Runs too late relative to exchange creation | Use transformer on WebHttpHandlerBuilder |
| Not configuring forward strategy in Boot | URI remains internal host/scheme | Use `FRAMEWORK` or an appropriate native strategy |
| Enabling native and Framework simultaneously | Request may be adjusted twice | Choose one mechanism |
| Using `removeOnly` while expecting scheme to become HTTPS | Headers are stripped and ignored | Only use removeOnly when discarding metadata |
| Reading XFF in controller after transform | Header may already be stripped | Read the adjusted `getRemoteAddress()` |
| Using transformed remote address to verify proxy | Address may be the forwarded client IP | Check peer at the network/proxy layer |
| Trusting `X-Forwarded-Host` to build arbitrary links | Host header poisoning, spoofed links | Host allowlist and proxy overwrite |
| Not handling path prefix | Broken links and context paths | Configure `X-Forwarded-Prefix` per contract |
| Letting multiple proxies append unchecked | Client IP chain can be spoofed | Define a trusted proxy chain |
| Manually parsing Forwarded with split | Mis-handles quoting, IPv6, and multi-hop | Use Spring transformer/parser |
| Assuming transformer authenticates proxies | Flawed security model | Proxy/network layer must establish trust |

## 18. Production Checklist

### Proxy and Network Boundary

- Backend accepts traffic only from permitted proxies/ingress.
- No direct access path from the Internet to the backend.
- First proxy strips client-sent `Forwarded` and all `X-Forwarded-*`.
- Proxy regenerates host, proto, port, and client address from verified metadata.
- Multi-proxy chains have clear append/overwrite rules.
- Public hosts are on an allowlist.
- Prefix is sent only when the proxy actually rewrites paths.

### Spring WebFlux

- Use `ForwardedHeaderTransformer` for the reactive stack.
- Transformer bean is registered with the exact name if configured manually.
- `server.forward-headers-strategy` matches the environment.
- Only one layer processes forwarded headers.
- `removeOnly` is chosen intentionally for the right goal.
- Controllers read the adjusted URI/remote address.
- Do not rely on raw forwarded headers after the transformer has stripped them.

### Security and Application

- Do not use forwarded IP as authentication.
- Do not use transformed IP to identify the TCP proxy peer.
- Redirects and absolute URLs use controlled hosts.
- OAuth2 redirect URIs are not derived from arbitrary hosts.
- HTTPS policies are tested behind TLS termination.
- Logs do not record raw headers containing sensitive data.
- IP-based rate limiting has a trust policy for the proxy chain.

### Testing and Operations

- Test standard `Forwarded`.
- Test `X-Forwarded-*`.
- Test that headers are stripped after transformation.
- Test `removeOnly`.
- Test requests with no forwarded headers.
- Test path prefixes if deployment rewrites paths.
- Test spoofed requests reaching the backend directly.
- Maintain proxy logs/metrics to correlate with application request details.

## 19. Self-Check Exercises

**Exercise 1.** Why does the backend see `http://orders-service:8080` even though the client accessed HTTPS?

**Answer:** The proxy terminates TLS and forwards via HTTP to the backend. Without forwarded metadata, the backend only sees the internal connection.

**Exercise 2.** How do `Forwarded` and `X-Forwarded-Proto` differ?

**Answer:** `Forwarded` is the RFC 7239 standard header containing `for`, `by`, `host`, and `proto` attributes; `X-Forwarded-Proto` is a convention header carrying only the scheme.

**Exercise 3.** Does `ForwardedHeaderTransformer` authenticate the proxy sending headers?

**Answer:** No. It processes header values. The proxy and network boundary must ensure only trusted proxies can produce forwarded metadata used by the application.

**Exercise 4.** Why does an edge proxy need to strip both `Forwarded` and `X-Forwarded-*`?

**Answer:** Clients can send one or both families. If only one family is stripped, the application may accept spoofed data from the remaining family.

**Exercise 5.** What does `server.forward-headers-strategy=FRAMEWORK` mean for WebFlux?

**Answer:** Tells Spring Boot to use Spring Framework's forwarded header handling, which in the reactive stack is `ForwardedHeaderTransformer`.

**Exercise 6.** What does `removeOnly=true` do?

**Answer:** Strips forwarded headers without using them to alter the request URI or address.

**Exercise 7.** Why should `getRemoteAddress()` after transformation not be used to verify which proxy connected directly?

**Answer:** The transformer can update remote address from `for`/`X-Forwarded-For` to the client address. The real TCP peer address must be checked at the network/server layer before trusting forwarded data.

**Exercise 8.** When is `X-Forwarded-Prefix` used?

**Answer:** When a proxy exposes a public path prefix different from the backend path and needs to communicate the public prefix so the framework builds URLs and context paths properly.

**Exercise 9.** Why can `$proxy_add_x_forwarded_for` be dangerous at an edge proxy?

**Answer:** It appends the new address to the existing header. If the existing value came from the client unsanitized, the chain still contains spoofed addresses.

**Exercise 10.** Should you choose `FRAMEWORK` or `NATIVE`?

**Answer:** Choose based on your embedded server and control needs. `FRAMEWORK` uses Spring's transformer; `NATIVE` uses the server's built-in support. Avoid enabling both to process the same request.

## 20. Key Takeaways

- Proxies change scheme, host, port, remote address, and sometimes path when forwarding requests.
- `Forwarded` is the RFC 7239 standard header; `X-Forwarded-*` is a widely used convention header group.
- `ForwardedHeaderTransformer` processes forwarded metadata before creating `ServerWebExchange`, adjusts the request, and strips the consumed headers.
- In WebFlux, use `ForwardedHeaderTransformer`; `ForwardedHeaderFilter` belongs to the Servlet stack.
- WebFlux automatically detects a bean named `forwardedHeaderTransformer`.
- Spring Boot offers `FRAMEWORK`, `NATIVE`, and `NONE`; only one layer should process headers.
- `removeOnly=true` strips headers and ignores metadata.
- The transformer does not verify the proxy source and does not replace a trusted-proxy policy.
- Edge proxies must strip client-supplied forwarded headers and regenerate verified metadata.
- Backends should accept connections only from trusted proxies.
- Remote address after transformation may be the client IP; do not use it to identify the TCP peer.
- Forwarded host, scheme, and prefix can affect redirects, absolute URLs, OAuth2, and security policies.
- Multiple proxies require clear chain rules; do not trust XFF just because the first element looks valid.

When configuring forwarded headers, answer three questions: **which proxy is allowed to generate metadata, has the proxy stripped client-supplied data, and is the application processing forwarded headers at exactly one layer?**

## Official Documentation

- Spring Framework 6.2, **WebFlux Reactive Core – Forwarded Headers and Security Considerations**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.1, **`ForwardedHeaderTransformer` API**: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/server/adapter/ForwardedHeaderTransformer.html
- Spring Framework 6.1, **`ForwardedHeaderUtils` API**: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/util/ForwardedHeaderUtils.html
- Spring Boot 3.3, **Running Behind a Front-end Proxy Server**: https://docs.spring.io/spring-boot/3.3/reference/howto.html
- Spring Boot 3.3, **`ServerProperties.ForwardHeadersStrategy` API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html
- IETF, **RFC 7239 – Forwarded HTTP Extension**: https://www.rfc-editor.org/rfc/rfc7239
- Spring Framework 6.1, **`MockServerHttpRequest` API**: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/mock/http/server/reactive/MockServerHttpRequest.html
- Spring Framework 6.2, **WebTestClient**: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html