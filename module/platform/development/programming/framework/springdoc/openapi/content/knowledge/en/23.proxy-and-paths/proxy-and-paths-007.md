# Trust boundaries for proxy-forwarded headers

## 1. Why do proxy-forwarded headers need a trust boundary?

A Spring Boot application often runs behind a reverse proxy, ingress controller, load balancer, or API gateway. Clients connect to the proxy; the proxy forwards requests to the application over an internal network. Therefore, the address, scheme, and host seen by the application can differ from what the client actually used externally.

For example, a client calls:

~~~http
https://api.example.com/gateway/v3/api-docs
~~~

The proxy terminates TLS and forwards to Spring Boot over internal HTTP:

~~~text
http://spring-app:8080/v3/api-docs
~~~

If the application only sees the internal request, it may assume the request uses HTTP and the host is spring-app:8080. Generated URLs for redirects, links, or the OpenAPI document can thus be wrong. Proxies typically send additional headers such as `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, and `X-Forwarded-Prefix` so the application knows the external metadata.

These headers are trustworthy only when they come from a controlled proxy. Clients can send headers with the same names and spoof the IP, host, scheme, or prefix if the proxy does not strip and overwrite them. If the application trusts every value it receives, an attacker can corrupt generated URLs, mislead audit logs, influence redirects, or cause confusion about the request origin.

With Springdoc OpenAPI, proxy metadata also affects server URLs and the paths Swagger UI uses to load documentation or call the API. Therefore, a clear trust boundary must be established between clients, proxies, and the application before configuring forwarded headers.

## 2. What are Forwarded and X-Forwarded-*?

There are two common header groups:

- **Forwarded**: the standardized header per RFC 7239, capable of carrying client/proxy, host, and protocol information.
- **X-Forwarded-***: a widely adopted convention group supported by many reverse proxies and frameworks.

A request may contain:

~~~http
Forwarded: for=203.0.113.10;proto=https;host=api.example.com
X-Forwarded-For: 203.0.113.10
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
X-Forwarded-Port: 443
X-Forwarded-Prefix: /gateway
~~~

Each header has a different meaning:

| Header | Forwarded information | Potential impact |
|---|---|---|
| Forwarded | for, by, host, proto | Client/proxy address, host, and scheme |
| X-Forwarded-For | Client IP address and proxies in the chain | Audit logs, rate limiting, IP-based policies |
| X-Forwarded-Proto | External scheme such as http or https | Secure request flag, redirects, and generated URLs |
| X-Forwarded-Host | Host used by the client externally | Absolute URLs, redirects, and OpenAPI server |
| X-Forwarded-Port | External port | Absolute URLs and redirects |
| X-Forwarded-Prefix | Prefix added or preserved externally by the proxy | Context path and links to API/Swagger UI |

Not every proxy sends all of these headers. Some systems send only Forwarded; some use X-Forwarded-*; some include both. Identify what your actual proxy sends and configure Spring Boot consistently with that source.

## 3. The proxy is the trust boundary, not the header name

A header name does not prove the origin of its value. A client can send a direct request such as:

~~~http
GET /v3/api-docs HTTP/1.1
Host: api.example.com
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
X-Forwarded-For: 127.0.0.1
~~~

If the proxy passes these headers verbatim to the application and Spring trusts them, the application may record a wrong client IP or generate URLs with a client-controlled host.

The trust boundary must be enforced at the infrastructure layer:

1. Only permitted proxies/load balancers may connect to the application port.
2. The outer boundary proxy must remove forwarded headers sent by clients.
3. The proxy must write values determined by itself.
4. Downstream internal proxies may be trusted only when inside the controlled infrastructure chain.
5. The application interprets forwarded headers only over trusted connection paths.

Do not enable forwarded-header processing on an application directly reachable from the Internet without a header-filtering proxy layer. Spring Framework can read headers, but it cannot verify on its own whether the proxy sending them is trustworthy.

## 4. Crucial rule: strip client-sent values, then rewrite them

At the first proxy receiving connections from clients, strip forwarded headers that clients might set themselves, then set values based on the actual request observed by the proxy.

With Nginx acting as an edge proxy directly receiving client connections, an illustrative configuration:

~~~nginx
location / {
    proxy_pass http://spring-app:8080;

    proxy_set_header Host $host;
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
}
~~~

In this example, Nginx discards the Forwarded header received from the client and generates X-Forwarded-* headers based on the request the proxy handles. This configuration assumes Nginx is the direct edge proxy; if there is a load balancer in front, $remote_addr may be the load balancer's address rather than the end client's.

Also validate the Host accepted by the proxy. Do not forward an arbitrary client-sent Host as a trusted X-Forwarded-Host. Use an allowlist of valid hostnames, virtual hosts, and an appropriate default server configuration.

If using the configuration:

~~~nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
~~~

Nginx appends the current peer address to the incoming X-Forwarded-For chain. This is safe only when existing entries in the chain were produced by an upstream trusted proxy. At the edge proxy, never preserve a client-supplied chain by default.

## 5. Multi-proxy chains and determining the client IP

In a multi-tier architecture, requests may traverse:

~~~text
Browser
  -> CDN
  -> Load Balancer
  -> Ingress Controller
  -> Spring Boot
~~~

Each proxy may append its address to X-Forwarded-For. The result can be a comma-separated list of IPs. Do not always pick the first element and treat it as the real client IP, as the leading entry may have been injected by the client if the edge proxy failed to strip the initial header.

A safe operational rule:

- Identify exactly which proxies are permitted to connect to the next tier.
- Identify which proxy strips incoming headers and which only appends.
- Trust only hops belonging to controlled network ranges or proxy lists.
- Compute the client IP from the chain after peeling off trusted hops in the right order.
- Never use X-Forwarded-For as an authorization basis without an origin verification process.

For example, if ingress accepts requests only from a load balancer with a fixed IP, ingress can trust the metadata normalized by the load balancer. If ingress also accepts requests from Pods or other networks, restrict network policies and configure trusted proxies accordingly.

Do not handle multi-proxy chains by trusting every address or every header. The trusted hop count and proxy list must reflect the real topology.

## 6. Risks of trusting arbitrary forwarded headers

| Spoofed value | Possible consequence |
|---|---|
| X-Forwarded-For | Corrupted audit logs, bypassed IP rate limits or allowlist policies |
| X-Forwarded-Proto | Application thinks the request is HTTPS even though client connected over HTTP; redirects/cookie URLs may break |
| X-Forwarded-Host | Generates absolute URLs or redirects to an attacker-controlled host |
| X-Forwarded-Port | Generated URLs contain an incorrect port |
| X-Forwarded-Prefix | Links, redirects, or OpenAPI URLs contain a forged path prefix |
| Forwarded | Can simultaneously affect host, proto, and client address |

In particular, X-Forwarded-Host can lead to host-header poisoning. If the application generates confirmation links, redirects, password-reset URLs, or OpenAPI servers based on a forged host, clients can be directed to an unintended domain.

A forged X-Forwarded-Proto can also mislead the application about HTTPS status. This affects redirects, Secure cookies, and URL construction. Enable forwarded-header handling only when the proxy is responsible for setting those values.

## 7. Configuring Spring Boot with server.forward-headers-strategy

Spring Boot provides the property:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Main options:

| Value | Behavior |
|---|---|
| NONE | Does not use forwarded headers to alter request metadata |
| NATIVE | Uses the web server/container's support |
| FRAMEWORK | Uses Spring Framework's forwarded-header handling mechanism |

**FRAMEWORK** uses Spring Framework's mechanism. For the Servlet stack, this is typically ForwardedHeaderFilter; for WebFlux, Spring uses ForwardedHeaderTransformer to adjust reactive requests.

**NATIVE** delegates handling to the container or embedded server. For instance, Tomcat has proxy metadata handling via RemoteIpValve. Exact configuration details depend on the container.

Do not enable multiple forwarded-header handling mechanisms simultaneously without understanding their ordering and scope. Pick one strategy suited to your stack and inspect request values after passing through the proxy.

Exact property names and behaviors must be verified against the Spring Boot version in use. Do not copy configurations from another project without verifying the container and network topology.

## 8. ForwardedHeaderFilter in Servlet

For Spring MVC/Servlet applications, Spring Framework provides ForwardedHeaderFilter to interpret forwarded headers. The filter can adjust request attributes seen by the application, such as scheme, host, port, and prefix.

In Spring Boot, when choosing:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Boot can configure the corresponding filter mechanism. If the application manually registers a ForwardedHeaderFilter via a bean or FilterRegistrationBean, check whether Boot already registers a similar filter to avoid duplicate processing.

Crucially, the filter does not authenticate the header source. Spring Framework warns that an application cannot tell whether a forwarded header was sent by a trusted proxy or a malicious client. The edge proxy must remove untrusted headers before the request reaches the application.

If you cannot guarantee the proxy has sanitized headers, do not let the application interpret them as trusted data. You can use a remove-only forwarded-header mode in the appropriate filter configuration, or choose the NONE strategy, depending on architecture and version.

## 9. Forwarded headers in WebFlux

WebFlux applications do not use the Servlet Filter chain. Spring Framework provides ForwardedHeaderTransformer to adjust ServerHttpRequest based on forwarded headers.

In Spring Boot, the FRAMEWORK strategy can configure the transformer for the reactive stack. Do not manually add Servlet's ForwardedHeaderFilter to a WebFlux application.

The security principles remain the same as for Servlet:

- Trust forwarded headers only from controlled proxies.
- The edge proxy must strip client-sent headers.
- Do not leave the application with a direct access path bypassing the proxy.
- Verify the host, scheme, port, and prefix seen by WebFlux.
- Do not use forged headers as an authorization basis.

If the same system includes both Servlet and Reactive services, each service must be configured appropriately for its web stack. Do not copy filter beans between the two application types.

## 10. Handling X-Forwarded-Proto when TLS terminates at the proxy

A common architecture terminates TLS at the ingress or load balancer. The connection from client to proxy uses HTTPS, while the internal connection to Spring Boot uses HTTP.

Example:

~~~text
Client --HTTPS--> Reverse Proxy --HTTP--> Spring Boot
~~~

The application sees an internal HTTP request. The proxy needs to send:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Port: 443
~~~

Once Spring processes forwarded headers from a trusted proxy, the request can be recognized externally as HTTPS. This ensures redirects and absolute URLs are generated with the right scheme.

Do not statically set X-Forwarded-Proto to https if the proxy also serves HTTP or has multiple virtual hosts with different policies. The value must reflect the scheme the client actually used, after the proxy completes TLS termination and validates the host.

The application should still use HTTPS at the public boundary. Forwarded headers do not encrypt connections and do not replace TLS.

## 11. X-Forwarded-Host and preventing host-header poisoning

When the proxy forwards the external host, Spring can use that value to build absolute URLs. If X-Forwarded-Host is uncontrolled, an attacker can send a forged host and make the application generate URLs pointing to another domain.

For example, an OpenAPI document could be generated with:

~~~yaml
servers:
  - url: https://attacker.example/api
~~~

If clients trust this server URL and send credentials when trying the API, the risk extends beyond displaying inaccurate documentation.

Required safeguards:

1. The proxy accepts only hostnames on an allowlist.
2. The proxy writes X-Forwarded-Host according to the validated virtual host.
3. The application trusts forwarded headers only from the proxy.
4. Never use arbitrary host values to build sensitive links.
5. For APIs with fixed hostnames, consider configuring static or environment-specific OpenAPI servers.
6. Test requests with spoofed Host/X-Forwarded-Host headers.

Do not treat Host or X-Forwarded-Host headers as user identity. They only describe the target/host of a request and must be controlled at the proxy.

## 12. X-Forwarded-Prefix and context path

A proxy may expose the application under an external prefix, for example:

~~~text
https://example.com/platform/shop/
~~~

while forwarding the request to Spring Boot at an internal path:

~~~text
http://spring-app:8080/
~~~

The proxy may send:

~~~http
X-Forwarded-Prefix: /platform/shop
~~~

Spring's forwarded-prefix handling can use this information when generating external URLs. However, distinguish clearly:

- **Context path**: the path prefix that the Spring Boot application itself is configured to serve.
- **Forwarded prefix**: the external prefix added or maintained by the proxy when forwarding.
- **Path rewriting**: the proxy may preserve the prefix or strip it before forwarding.

If the proxy keeps the prefix in the request path while also sending an identical X-Forwarded-Prefix, the application may produce URLs with a duplicated prefix. If the proxy strips the prefix without sending a forwarded prefix, generated URLs may miss the external path segment.

Choose one clear model and verify the internal request path, forwarded prefix, and public URL in a single test run.

## 13. Impact on OpenAPI server URLs

An OpenAPI document can contain a `servers` array specifying the API base URL. When Springdoc infers URLs from requests or Spring MVC provides server metadata, forwarded headers can influence the recognized host, scheme, port, and prefix.

Example of a proper document when the API is published through a proxy:

~~~yaml
servers:
  - url: https://api.example.com/gateway
    description: Public API
~~~

If requests reach Spring Boot over internal HTTP yet the OpenAPI document has server URL http://spring-app:8080, Swagger UI may call the wrong address or browsers may block requests due to mixed content.

There are two configuration approaches:

- Use forwarded headers sanitized by a trusted proxy so the application recognizes the external URL.
- Declare explicit Server Objects per environment if public hostnames/paths are fixed.

Example with the Swagger Core model:

~~~java
@Bean
public OpenAPI shopOpenAPI() {
    return new OpenAPI()
        .servers(List.of(
            new Server()
                .url("https://api.example.com/gateway")
                .description("Public API")
        ));
}
~~~

Do not declare static servers while simultaneously expecting Springdoc to infer a different server without clearly understanding the merge behavior. Inspect the servers array in the final OpenAPI JSON.

## 14. Swagger UI and OpenAPI documents behind a reverse proxy

Swagger UI loads multiple resources: the HTML page, JavaScript/CSS, swagger-config, and the OpenAPI document. Afterward, Try it out sends requests to the server URL described in OpenAPI.

When running behind a proxy, verify:

- The Swagger UI entry point redirects to the public URL with the right scheme/host/prefix.
- JS/CSS assets load under the public prefix.
- swagger-config returns the appropriate document URL.
- OpenAPI JSON/YAML has the right server URL.
- Group documents have accurate URLs.
- Try it out calls the right public API base URL.
- No mixed content occurs when the page uses HTTPS while the server URL uses HTTP.

If the application is published under the /gateway prefix, all links generated by Swagger UI and Springdoc must remain consistent with that prefix. Do not fix only the Swagger UI URL while overlooking the OpenAPI document URL or the server URL inside the document.

If customizing springdoc.api-docs.path or springdoc.swagger-ui.path, keep them aligned with reverse proxy routes and security matchers. Internal paths forwarded by the proxy to the application may differ from public paths seen by browsers.

## 15. Nginx configuration example with public prefix

Suppose a client accesses:

~~~text
https://api.example.com/gateway/swagger-ui.html
~~~

Nginx strips the prefix before forwarding to the application while passing the prefix metadata:

~~~nginx
location /gateway/ {
    proxy_pass http://spring-app:8080/;

    proxy_set_header Host $host;
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-Prefix /gateway;
}
~~~

This example assumes Nginx is the direct edge proxy and the host has been validated via virtual host configuration. Trailing slashes on location and proxy_pass affect how Nginx rewrites URIs; verify the URL the application actually receives.

If there is a load balancer in front of Nginx, do not use this configuration verbatim to determine the client IP. Configure trusted real IPs from the load balancer's network ranges first, and only then use the verified address. Never append an unsanitized X-Forwarded-For chain from clients.

## 16. Never use forwarded headers as an authorization mechanism

Forwarded headers are metadata about the request's path. They are not credentials.

Do not write rules like:

~~~java
if ("127.0.0.1".equals(request.getRemoteAddr())) {
    allowAdminAccess();
}
~~~

if the remote address value can be altered from a header that clients can spoof. Likewise, never grant admin access simply because X-Forwarded-For contains an internal IP.

If network-based access restriction is needed, enforce it at the firewall, ingress, or trusted network layer; if checking inside the application, rely on verified remote peers/proxies and an explicit trust-chain configuration. For user permissions, use real authentication and authorization such as OAuth2/JWT, sessions, or API keys.

Forwarded headers also do not prove a request came from a specific browser, user, or service. They merely provide routing metadata forwarded by proxies.

## 17. Testing the trust boundary

Test both legitimate flows and spoofing flows.

| Scenario | Expectation |
|---|---|
| Valid proxied request over HTTPS | Application receives https scheme |
| Proxied request with allowlisted host | Generated URLs use the right public host |
| Proxied request with prefix | Links and OpenAPI server contain the prefix exactly once |
| Client sends forged X-Forwarded-Host | Proxy strips/overwrites it; forged value does not affect the app |
| Client sends forged X-Forwarded-Proto | Proxy rewrites according to the actual connection |
| Client sends forged X-Forwarded-For | Forged IP is not treated as a trusted client IP |
| Direct access to application port | Blocked at network level or forwarded headers are untrusted |
| Multi-proxy chain | Only configured hops are trusted |
| OpenAPI document fetched via proxy | servers and paths match public URL |
| Swagger UI Try it out | Requests reach the right host, scheme, and prefix |

Use integration tests through the ingress/reverse proxy to verify real behavior. MockMvc alone generally cannot prove that the proxy sanitizes headers or that a firewall blocks direct access.

When checking OpenAPI, fetch /v3/api-docs through the public URL and inspect the servers field. Also check redirects and swagger-config/UI asset requests in the Browser Network tab.

## 18. Common errors

| Symptom | Causes to check |
|---|---|
| OpenAPI servers contains container hostname | Application has not processed forwarded host or proxy does not send the header |
| Swagger UI creates HTTP URLs despite external HTTPS | X-Forwarded-Proto missing, wrong, or not properly trusted |
| Redirect points to unfamiliar domain | Host/X-Forwarded-Host not allowlisted and sanitized |
| /gateway prefix is duplicated | Proxy keeps prefix and also sends a duplicate X-Forwarded-Prefix |
| Swagger UI links miss prefix | Proxy rewrites path without forwarding prefix or framework ignores it |
| Client IP is always the proxy IP | X-Forwarded-For or native remote IP support not configured |
| Client can spoof IP via header | Edge proxy preserves client-sent X-Forwarded-For |
| Same request gives different URLs | Multiple forwarded-header handling mechanisms active simultaneously |
| Servlet works but WebFlux fails | Wrong filter/transformer or mismatched web stack configuration |
| Only YAML or group docs have wrong URLs | Unaligned matchers, path rewrites, or endpoint configuration |
| App trusts headers when called directly | Backend port is not access-restricted or strategy trusts every request |
| Try it out calls internal host | OpenAPI server URL does not reflect the public URL |

When investigating, compare the external request, headers sent by the proxy, the request seen by Spring, and the generated OpenAPI JSON. Do not rely solely on application logs because logs may already reflect interpreted forwarded values.

## 19. Secure configuration checklist

Before enabling forwarded-header processing in Spring Boot:

1. Identify every proxy/load balancer/ingress in the path.
2. Identify which edge proxy strips client-sent forwarded headers.
3. Ensure proxies rewrite host, proto, port, and client IP from verified sources.
4. Restrict networks so the application accepts traffic only from permitted proxies.
5. Choose the appropriate server.forward-headers-strategy: NONE, NATIVE, or FRAMEWORK.
6. Do not register duplicate filters/transformers alongside Boot's configured mechanism.
7. Verify X-Forwarded-Prefix and path rewriting.
8. Allowlist public hostnames and prevent host-header poisoning.
9. Never use forwarded headers as credentials or authorization rules.
10. Verify OpenAPI servers, swagger-config, UI resources, and Try it out via the public URL.
11. Test requests with spoofed forwarded headers and confirm the proxy strips/overwrites them.
12. Test both Servlet and Reactive according to the exact web stack.

The trust boundary lies at the controlled proxy and the network path from the proxy to the application. Spring Boot should interpret forwarded headers only after infrastructure guarantees their origin. When host, scheme, client IP, and prefix are forwarded properly, Springdoc can generate OpenAPI documents and Swagger UI with public-appropriate URLs without trusting arbitrary client-supplied data.

