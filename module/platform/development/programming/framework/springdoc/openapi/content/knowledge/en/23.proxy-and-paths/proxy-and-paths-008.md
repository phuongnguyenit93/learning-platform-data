# External HTTPS with HTTP between proxy and application

In many Spring Boot systems, browsers connect over HTTPS to a reverse proxy or load balancer, while the proxy forwards requests to the application over HTTP within a private network. This is the TLS termination pattern (terminating TLS at the proxy). It centralizes certificate management and avoids per-service TLS setup, yet the application must know that the original request arrived over HTTPS and may have traversed a public path prefix.

This is especially important for springdoc-openapi and Swagger UI. If the application only sees the internal HTTP connection, OpenAPI may generate server URLs starting with http://, Swagger UI may load documentation from the wrong host, or redirects may point to an internal URL. If the proxy strips a public prefix without informing the application, links such as /v3/api-docs or /swagger-ui/** can be generated missing the prefix.

## 1. External HTTPS, internal HTTP model

Common flow:

~~~mermaid
flowchart LR
    C[Browser / API client] -->|HTTPS :443| P[Reverse proxy / Load balancer]
    P -->|HTTP :8080 in private network| A[Spring Boot application]
    A --> S[Spring Security + springdoc]
    S --> D[OpenAPI JSON / Swagger UI]
    D -->|Public HTTPS URL| C
~~~

The client connects to https://api.example.com, and the proxy decrypts TLS and forwards the request to http://spring-app:8080. On the application side, the socket and servlet request may show only:

- Scheme is http.
- Internal port is 8080.
- Host is the service name or container address.
- Path may have had a public prefix stripped by the proxy.

Meanwhile, the client expects to see the public URL:

https://api.example.com/gateway

The application must receive the original metadata via forwarded headers and handle them properly.

### 1.1. Three common TLS arrangements

| Model | Where is TLS terminated? | Downstream connection | When appropriate |
|---|---|---|---|
| TLS termination | Reverse proxy | HTTP to application | Proxy and application reside within a controlled private network. |
| TLS re-encryption | Proxy decrypts and re-encrypts | HTTPS to application | Internal network segment also needs encryption or traverses partially untrusted networks. |
| TLS passthrough | Application or final ingress | L4 proxy forwards TLS intact | Application manages certificates itself and requires end-to-end TLS to the service. |

This guide focuses on TLS termination: HTTPS from client to proxy and HTTP from proxy to Spring Boot. With re-encryption, forwarded headers remain useful so the application knows the external URL; additionally, certificates and trust stores must be configured for the internal HTTPS connection.

With TCP-level TLS passthrough, the proxy does not decrypt HTTP and therefore cannot inject X-Forwarded-Proto or X-Forwarded-Prefix. The application terminates TLS itself and sees HTTPS directly.

## 2. Forwarded headers convey the original URL

The proxy can send the RFC 7239 standard Forwarded header or the common X-Forwarded-* headers.

| Header | Example | Meaning |
|---|---|---|
| Forwarded | proto=https;host=api.example.com;for=203.0.113.10 | Standard header describing proxied request metadata. |
| X-Forwarded-For | 203.0.113.10 | Original client address or proxy chain traversed. |
| X-Forwarded-Host | api.example.com | Host used by the client externally. |
| X-Forwarded-Port | 443 | Public port. |
| X-Forwarded-Proto | https | Original client scheme. |
| X-Forwarded-Prefix | /gateway | Public prefix stripped from the path by the proxy before forwarding. Widely supported header, though not part of RFC 7239. |

Example proxy-forwarded request:

~~~http
GET /v3/api-docs HTTP/1.1
Host: spring-app:8080
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-For: 203.0.113.10
X-Forwarded-Prefix: /gateway
~~~

The application can use these headers to construct redirects, links, and server URLs matching the external request. Without handling them, the application may generate links using the internal scheme, host, port, or path.

### 2.1. X-Forwarded-Prefix does not rewrite the request path itself

Suppose the client calls URL https://api.example.com/gateway/v3/api-docs.

The proxy may strip /gateway before sending the request to the application. The application then receives /v3/api-docs, while X-Forwarded-Prefix: /gateway tells it the external prefix to use when building URLs.

These are two separate actions:

- proxy_pass or the proxy rewrite rule determines which path is sent to the application.
- X-Forwarded-Prefix announces the public prefix so the framework builds external URLs.

Sending the header without configuring rewrite can cause the application to receive a path that does not match controllers. Conversely, rewriting properly without passing the prefix can cause Swagger UI to generate URLs missing /gateway.

## 3. Configuring Spring Boot to process forwarded headers

Spring Boot has two main processing approaches:

- **Native/web server**: containers such as Tomcat or Jetty process forwarded headers using their own mechanisms.
- **Framework**: Spring Framework handles them via ForwardedHeaderFilter on the Servlet stack or ForwardedHeaderTransformer on the reactive stack.

Choose the approach matching your proxy, container, and Spring Boot version. Do not enable multiple mechanisms simultaneously if both modify scheme/host/path, as that can produce wrong output or apply the prefix twice.

### 3.1. Spring Boot 3.x

In Spring Boot 3.x, the commonly used property is server.forward-headers-strategy.

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Common values:

| Value | Behavior |
|---|---|
| NONE | Does not process forwarded headers. |
| NATIVE | Uses the web server/container's support. |
| FRAMEWORK | Uses Spring Framework forwarded-header support. |

When X-Forwarded-Prefix needs to be handled to generate URLs with a public prefix, FRAMEWORK is typically easier to control if native container support does not fully handle prefixes. The Springdoc FAQ also recommends server.forward-headers-strategy=framework when prefix handling is needed.

Do not manually register an additional ForwardedHeaderFilter if Spring Boot already auto-configures the filter from this property. If managing a filter manually, ensure it runs before URL-building components and is mapped for the appropriate dispatcher types.

### 3.2. Spring Boot 4.x

Spring Boot 4 moves forwarded-header configuration under the server.request.header.forwarded.* property group. Example using Spring Framework to process forwarded headers and enable prefix handling:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: framework
        use-prefix: true
~~~

use-prefix defaults to false; if the proxy sends X-Forwarded-Prefix, enable it explicitly so the application uses the prefix. When the web server/container fully supports all headers in use, web-server can be chosen; if prefix support is needed and native support cannot handle it, use framework.

Do not copy Boot 3 configuration verbatim to Boot 4 without checking properties for the major version. server.forward-headers-strategy has been replaced in Boot 4 configuration documentation.

### 3.3. Tomcat when a proxy terminates SSL

If using Tomcat and encountering redirects at context root before X-Forwarded-Proto is applied, Spring Boot provides dedicated properties:

- Spring Boot 3.x: server.tomcat.redirect-context-root: false.
- Spring Boot 4.x: server.tomcat.servlet.redirect-context-root: false.

Configure this only when Tomcat's redirect/context-root behavior requires it. Do not add the property blindly to every application; verify actual redirects and documentation for the running version.

## 4. Configuring Nginx to terminate TLS and forward HTTP to the application

The example below assumes Nginx is the edge TLS termination point, public host is api.example.com, public prefix is /gateway, and Spring Boot listens on HTTP at spring-app:8080.

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate     /etc/nginx/tls/api.example.com.crt;
    ssl_certificate_key /etc/nginx/tls/api.example.com.key;

    location /gateway/ {
        # Trailing URI "/" in proxy_pass replaces the /gateway/ prefix with "/".
        proxy_pass http://spring-app:8080/;

        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port  $server_port;

        # Example where Nginx is the first proxy receiving requests from the Internet.
        proxy_set_header X-Forwarded-For  $remote_addr;

        # Announce the prefix stripped before forwarding.
        proxy_set_header X-Forwarded-Prefix /gateway;
    }
}
~~~

In this configuration:

- Client calls /gateway/v3/api-docs.
- Nginx strips /gateway/ and forwards /v3/api-docs to the application.
- $scheme on the TLS server is https.
- $server_port is 443.
- X-Forwarded-Prefix informs the backend that the external prefix is /gateway.

Nginx specifies that if proxy_pass contains a URI, the URI part matching the location is replaced by the URI in proxy_pass. Thus the trailing / in http://spring-app:8080/; is significant in this prefix-stripping example.

### 4.1. If you want to preserve the prefix when forwarding

If the application serves paths under /gateway/... itself, use a configuration without a trailing URI in proxy_pass:

~~~nginx
location /gateway/ {
    proxy_pass http://spring-app:8080;
}
~~~

Nginx then forwards the full path /gateway/... to the application. The application needs a matching context path or mapping. Do not simultaneously strip the prefix at the proxy and configure the application to expect the prefix internally; pick one consistent rule.

### 4.2. Proxy sitting behind another load balancer

If Nginx receives requests from a load balancer that already terminated TLS, $scheme in Nginx may be http even though external clients use HTTPS. In that case, do not mechanically overwrite X-Forwarded-Proto with $scheme.

Instead:

1. Trust headers only from the load balancer within the trust boundary.
2. Configure the load balancer to strip client-sent forwarded headers and emit accurate values.
3. Configure Nginx to accept headers only from the trusted upstream.
4. Forward verified values onward to Spring Boot.

The proxy chain must have clear rules on which proxy is allowed to add or modify each header. Never let Internet clients decide the scheme, host, or client IP trusted by the application.

## 5. Trust boundary for forwarded headers

Forwarded headers can affect redirect URLs, OpenAPI server URLs, client addresses, and security logic. If an application directly receives a request with a client-supplied X-Forwarded-Proto: https, it may mistake an HTTP connection for HTTPS.

Spring Framework warns that forwarded headers must be set by a trusted proxy. The proxy at the trust boundary should strip client-sent Forwarded and X-Forwarded-* headers, then write valid values itself. Do not strip only one header format; both standard and non-standard headers may be present.

Deployment principles:

- Do not expose Spring Boot's internal HTTP port directly if the application relies on forwarded headers to determine the original URL.
- Allow only trusted proxies/load balancers to connect to the backend port.
- At the edge proxy, overwrite X-Forwarded-Proto, X-Forwarded-Host, X-Forwarded-Port, and prefix per real configuration.
- Append to the X-Forwarded-For chain only when prior hops are verified and trust is configured accordingly.
- Do not set the trusted proxy configuration to "trust all" in production.
- Check host allow-lists to prevent Host header injection or links pointing to disallowed domains.
- Never use forwarded headers as proof of user identity authentication.

### 5.1. Do not expose backend ports to the Internet

If the backend remains directly reachable from the Internet, clients can bypass Nginx and send forged forwarded headers. Then:

- OpenAPI can generate server URLs with a spoofed host.
- Redirects can point to an unintended scheme or host.
- Logs can record false client addresses.
- Cookies or absolute links can be created with wrong attributes.

Restrict network policies, firewalls, or security groups so only the proxy can access the backend. If direct health checks or administration access are needed, create dedicated paths with explicit permissions and configuration.

## 6. Ensuring OpenAPI and Swagger UI use public HTTPS URLs

Springdoc can infer the server URL from request information. When forwarded headers are handled correctly, URLs in OpenAPI should reflect the public address rather than the container address.

Desired example:

~~~yaml
servers:
  - url: https://api.example.com/gateway
    description: Public API
~~~

If servers is generated as http://spring-app:8080, check in order:

1. Does the proxy send X-Forwarded-Proto: https?
2. Does the proxy send accurate X-Forwarded-Host and X-Forwarded-Port?
3. Does Spring Boot process forwarded headers?
4. Is the prefix stripped and sent in X-Forwarded-Prefix?
5. Does the application receive requests directly from clients bypassing the proxy?
6. Is an @OpenAPIDefinition(servers = ...) or OpenAPI bean setting a fixed server URL that overrides inferred URLs?

### 6.1. Declaring static server URLs per environment

If a deployment always has a fixed public base URL, you can declare the server explicitly:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
        servers = {
            @Server(
                    url = "https://api.example.com/gateway",
                    description = "Public HTTPS API"
            )
        }
)
class OpenApiServerConfiguration {
}
~~~

The explicit server annotation is used instead of an inferred URL. This works well when each environment has a fixed URL and configuration can vary per profile or deployment. Avoid hard-coding a production URL into a shared artifact used across local, test, and staging.

### 6.2. Customizing the server URL when necessary

Springdoc provides ServerBaseUrlCustomizer to adjust the base URL used in Swagger UI/OpenAPI. Use it when you need to normalize URLs according to a specific deployment rule, such as stripping an internal port or adjusting a base path. Prioritize properly configured forwarded headers first; a customizer should not mask a proxy sending the wrong scheme/host.

If a single application serves Swagger UI through multiple proxies or multiple hostnames, the server URL may differ per request. By default, Springdoc caches the OpenAPI document; when recalculation per request is needed, configure:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Disable caching only when the server URL genuinely needs to vary per request. For deployments with a single fixed public base URL, keeping default caching is usually more efficient.

## 7. Swagger UI paths when a context path or prefix is present

There are three path components to distinguish:

| Component | Example | Who manages it |
|---|---|---|
| Public prefix | /gateway | Reverse proxy/load balancer. |
| Application context path | /service | Spring Boot, via server.servlet.context-path. |
| Endpoint path | /v3/api-docs, /swagger-ui/** | Springdoc. |

The external URL can be:

https://api.example.com/gateway/service/v3/api-docs

If the proxy strips /gateway before forwarding, the application receives:

/service/v3/api-docs

In this setup:

- server.servlet.context-path represents /service.
- X-Forwarded-Prefix represents /gateway.
- Do not set server.servlet.context-path=/gateway if the proxy already stripped the prefix and the application only receives the remaining path.

### 7.1. Checking swagger-config

Swagger UI usually loads configuration from /v3/api-docs/swagger-config, then fetches the OpenAPI JSON URL specified there. When using a prefix, verify all of:

- /swagger-ui.html redirects cleanly to a URL with HTTPS and the prefix.
- CSS/JavaScript under /swagger-ui/** loads through the prefix.
- swagger-config loads through the prefix.
- The OpenAPI JSON URL inside config points to /gateway/v3/api-docs or the corresponding group.
- The Try it out button calls the API using the public HTTPS server URL.

If configuring springdoc.swagger-ui.url or configUrl manually, avoid hard-coding internal hostnames like http://spring-app:8080. Use a relative URL matching the public path or configure URLs per environment.

## 8. Configuring proxy and application in one complete example

Suppose:

- Public URL: https://api.example.com/gateway.
- Nginx terminates TLS on port 443.
- Nginx forwards HTTP to spring-app:8080.
- Nginx strips prefix /gateway.
- Spring Boot 3.x uses Spring MVC.

Nginx:

~~~nginx
location /gateway/ {
    proxy_pass http://spring-app:8080/;

    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-Host  $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port  $server_port;
    proxy_set_header X-Forwarded-For   $remote_addr;
    proxy_set_header X-Forwarded-Prefix /gateway;
}
~~~

Spring Boot 3.x:

~~~yaml
server:
  forward-headers-strategy: framework

springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
~~~

For Spring Boot 4.x, the forwarded headers section changes to:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: framework
        use-prefix: true
~~~

There is no need to change springdoc endpoints solely because the proxy strips a prefix. The application keeps serving /v3/api-docs internally; the framework uses the forwarded prefix to build external URLs.

If you want a fixed public URL, you can declare servers per profile. If you want springdoc to infer URLs per request, omit fixed servers and verify forwarded headers along with cache policy.

## 9. Testing scheme, host, port, and prefix

Do not verify merely that Swagger UI returns HTTP 200. Verify the final URLs received by clients.

### 9.1. Checking with curl

Check redirects from the Swagger UI page:

~~~bash
curl -I https://api.example.com/gateway/swagger-ui.html
~~~

The Location header (if present) must use https://api.example.com/gateway/..., not http://spring-app:8080/....

Check OpenAPI servers:

~~~bash
curl -s https://api.example.com/gateway/v3/api-docs
~~~

Read the servers field in the JSON. Expected output has scheme https, the public host, and prefix /gateway.

Check Swagger UI in the browser Network tab:

- swagger-config succeeds.
- OpenAPI JSON loads from the public path.
- No requests go to container hostnames or HTTP URLs.
- CSS/JS do not return 404 due to missing prefix.
- Try it out calls the right HTTPS server.

### 9.2. Testing forwarded headers with MockMvc

MockMvc can test how the Spring application processes forwarded headers when the test uses the same filter configuration. The example below illustrates Spring Boot 3.x:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "server.forward-headers-strategy=framework",
        "springdoc.cache.disabled=true"
})
@AutoConfigureMockMvc
class ForwardedOpenApiUrlTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void generatesPublicHttpsServerUrl() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-Host", "api.example.com")
                        .header("X-Forwarded-Port", "443")
                        .header("X-Forwarded-Prefix", "/gateway"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.servers[0].url")
                        .value("https://api.example.com/gateway"));
    }
}
~~~

This test assumes no static server URL overrides it and that the running springdoc version infers the server URL from the request. If your version or application config produces a different URL, adjust the assertion to match your chosen contract.

MockMvc does not simulate Nginx rewrites, TLS handshakes, or firewalls. Add integration tests through a real proxy or staging environment to verify the complete flow.

### 9.3. Verifying the proxy does not trust spoofed client headers

Send an external request with forged forwarded headers, e.g. X-Forwarded-Proto: http or X-Forwarded-Host: attacker.example, and verify that the edge proxy overwrites them with canonical values. The resulting server URL must still be HTTPS with a valid host.

Also try connecting directly to the backend from an unauthorized network. The connection must be blocked at the network layer; do not rely on the application to sanitize every forged header from the Internet.

## 10. Common errors

- **Swagger UI generates HTTP URLs**: application does not process X-Forwarded-Proto or proxy sends the wrong value.
- **OpenAPI contains container hostname**: Host/X-Forwarded-Host not forwarded or framework does not use forwarded headers.
- **Missing public prefix**: proxy strips path without sending X-Forwarded-Prefix, or application has not enabled prefix handling.
- **Prefix appears twice**: proxy preserves prefix while the application also adds it as a context path or forwarded prefix.
- **Redirect reverts to HTTP**: Tomcat or application did not recognize original HTTPS scheme; check forwarded strategy and redirect context root.
- **Swagger UI loads yet JSON returns 404**: swagger-config points to a URL missing the prefix or proxy rewrite is wrong.
- **Wrong trailing / on proxy_pass**: Nginx replaces or preserves the URI differently from expectations.
- **Trusting forwarded headers from any source**: clients can spoof scheme, host, or client IP.
- **NATIVE enabled yet prefix still missing**: native container may not support prefix; try FRAMEWORK or configure use-prefix per Boot version.
- **Manually creating an extra ForwardedHeaderFilter**: may process headers twice when Boot already auto-configures it.
- **Server URL cached from first proxy**: if the same app serves multiple external URLs, consider springdoc.cache.disabled=true.
- **Hard-coding production URLs in all environments**: local/staging may mistakenly target production.
- **Backend HTTP port exposed directly to the Internet**: clients can bypass the proxy and send forged forwarded headers.

## 11. Deployment workflow

1. **Identify TLS topology**: termination, re-encryption, or passthrough.
2. **Finalize public URL**: scheme, host, port, and prefix seen by clients.
3. **Choose path mapping**: whether the proxy keeps or strips the prefix before forwarding.
4. **Configure proxy**: emit accurate forwarded headers and never trust arbitrary client headers.
5. **Configure Spring Boot per major version**: Boot 3 uses server.forward-headers-strategy; Boot 4 uses server.request.header.forwarded.*.
6. **Enforce trust boundary**: allow only trusted proxies to connect to the backend and generate forwarded headers.
7. **Check springdoc**: confirm servers, swagger-config, redirects, and UI assets.
8. **Choose server URL policy**: infer via forwarded headers or declare statically per environment.
9. **Check cache**: disable caching only if URLs must vary per request/proxy.
10. **Test end-to-end**: external HTTPS, internal HTTP, prefix, redirects, Try it out, and forged header requests.

## 12. Review checklist

- [ ] TLS is terminated at the intended proxy or application per chosen architecture.
- [ ] Public URL has the right HTTPS scheme, host, port, and prefix.
- [ ] Proxy overwrites forwarded headers from trusted sources.
- [ ] Backend accepts connections only from permitted proxies or networks.
- [ ] Spring Boot uses the right forwarded strategy for its major version.
- [ ] X-Forwarded-Prefix is supported if the proxy strips the prefix.
- [ ] No duplicate prefix configured across proxy rewrite, context path, and forwarded prefix.
- [ ] Tomcat redirect context root handled if wrong-scheme redirects occur.
- [ ] OpenAPI servers do not expose internal hosts or ports.
- [ ] Swagger UI and swagger-config load JSON via the public HTTPS path.
- [ ] Static server URLs, if any, are managed per environment.
- [ ] Caching is kept default or intentionally disabled for dynamic URLs.
- [ ] Integration tests verify URLs through a real proxy.
- [ ] Tests confirm forged forwarded headers from clients are not trusted.

## 13. References

- [Spring Boot 3.5 – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 4.0 – Forwarded Headers and Prefix Support](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html)
- [Spring Boot – Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Spring Framework – ForwardedHeaderFilter and Security Considerations](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [springdoc-openapi FAQ – Deploy behind a reverse proxy](https://springdoc.org/faq.html)
- [Nginx – ngx_http_proxy_module and proxy_pass URI behavior](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [RFC 7239 – Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)

When HTTPS terminates at the proxy, the application must rely on trustworthy forwarded headers to recognize the external URL accurately. Align TLS topology, path rewrites, forwarded strategy per Spring Boot version, and springdoc server URLs. Test OpenAPI JSON, Swagger UI, redirects, and Try it out through a real proxy to guarantee clients always use HTTPS along with the exact public path.
