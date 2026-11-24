# Spring Boot forwarded-header processing strategies

A Spring Boot application commonly runs behind a reverse proxy, ingress controller, or load balancer. Browsers access the application over HTTPS on a public domain, while the proxy forwards requests to Spring Boot over HTTP on an internal network. If the application only sees the internal connection, it may assume the request uses HTTP, the host is the container name, and the port is 8080. As a result, redirects, absolute links, OAuth2 callbacks, or request-derived URLs can be wrong.

Reverse proxies can send **forwarded headers** to tell the application what details the client used externally. Spring Boot provides the **server.forward-headers-strategy** property to select how those headers are handled: **NONE**, **NATIVE**, or **FRAMEWORK**.

Choosing the right strategy helps Spring understand the request's scheme, host, port, and external prefix. However, forwarded headers are trustworthy only when they arrive from a controlled proxy. If the application directly accepts headers set by clients, callers can spoof the host or scheme and influence URLs, redirects, and certain security decisions.

## 1. Why are forwarded headers needed?

Suppose the deployment flow is as follows:

~~~text
Browser
  https://api.example.com/gateway/api/orders
          |
          v
Reverse proxy / ingress
  TLS termination
  rewrite /gateway
          |
          v
Spring Boot
  http://orders-service:8080/api/orders
~~~

Spring Boot sees a connection from the proxy to orders-service:8080. Without receiving forwarded metadata, the request may be seen as:

| Property seen by Spring | Internal value |
|---|---|
| Scheme | http |
| Host | orders-service |
| Port | 8080 |
| External context/prefix | No /gateway |
| Secure request | false |

Yet the user actually accessed:

~~~text
https://api.example.com/gateway/api/orders
~~~

This discrepancy can break:

- Redirects to login pages or OAuth2 callbacks.
- Absolute URLs built with ServletUriComponentsBuilder.
- The Location header in responses.
- Links in emails or HATEOAS content built from the current request.
- Cookies with the Secure attribute or logic depending on request.isSecure().
- Server URLs dynamically generated for OpenAPI documentation when the application relies on the current request.
- Logs and audits needing to distinguish the client address from the proxy address.

Forwarded headers relay the public request's details so the framework or web server can adjust the request seen by the application.

## 2. Types of forwarded headers

There are two common header groups.

### Standard Forwarded header

RFC 7239 defines the Forwarded header. Example:

~~~http
Forwarded: for=198.51.100.24;proto=https;host=api.example.com
~~~

Common parameters:

| Parameter | Meaning |
|---|---|
| for | Address of the client or the node ahead of the proxy |
| by | Proxy node receiving the request |
| proto | External scheme, e.g. https |
| host | Host used by the client, optionally with port |

If a request passes through multiple proxies, the header may contain multiple comma-separated elements. Do not split the string with a simple rule and treat the first or last element as a trusted client.

### X-Forwarded-* group

The X-Forwarded-* headers are widely used in reverse proxies:

| Header | Meaning |
|---|---|
| X-Forwarded-For | Client address and/or proxy chain |
| X-Forwarded-Proto | External scheme such as https |
| X-Forwarded-Host | External host |
| X-Forwarded-Port | External port |
| X-Forwarded-Prefix | Public prefix added or stripped from the internal path by the proxy |

Example:

~~~http
X-Forwarded-For: 198.51.100.24
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /gateway
~~~

X-Forwarded-Prefix is particularly useful when a proxy receives a URL with the /gateway prefix and strips that prefix before forwarding the request to the application. The framework needs to know the public prefix to reconstruct URLs clients can reach.

Avoid sending two conflicting sets of headers. Standardize on whether the proxy emits Forwarded, the X-Forwarded-* group, or a canonical header set that the container/framework is configured to read.

## 3. Spring Boot's three strategies

Configuration property:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Spring Boot offers three options:

| Value | How it handles | When appropriate |
|---|---|---|
| NONE | Does not ask Spring Boot to process forwarded headers | Directly accessed app or proxy does not send trusted headers |
| NATIVE | Uses the web server/container's forwarded-header handling | Container has suitable support and is configured properly |
| FRAMEWORK | Uses Spring Framework's mechanism to adjust requests | Want consistent forwarded-header handling at the framework layer |

### NONE

~~~yaml
server:
  forward-headers-strategy: none
~~~

With NONE, the application does not apply forwarded headers via Spring Boot's automatic strategy. Spring sees the information of the connection made directly to it, typically the connection from the reverse proxy.

This is appropriate when there is no trusted proxy in front or when the system must not interpret client-supplied headers. If deployed behind a proxy with NONE still active, URLs built from the request may use the internal host, port, and scheme.

### NATIVE

~~~yaml
server:
  forward-headers-strategy: native
~~~

With NATIVE, Spring Boot tells the web server/container to use its own forwarded-header processing capability. For example, Tomcat can use RemoteIpValve to interpret forwarded headers and update request information.

The advantage is handling at the container layer. However, supported headers, how trusted proxies are identified, and prefix handling depend on the container and its configuration. Do not assume every container interprets every header the same way.

If choosing NATIVE, consult the documentation for the running container, configure the trusted proxy list, and inspect the requests received by the application. With Tomcat, you may need to tune server.tomcat.remoteip.* properties depending on topology and headers sent by the proxy.

### FRAMEWORK

~~~yaml
server:
  forward-headers-strategy: framework
~~~

With FRAMEWORK, Spring Boot uses Spring Framework's forwarded-header support. In Servlet applications, this uses ForwardedHeaderFilter; in reactive applications, Spring uses ForwardedHeaderTransformer.

The framework mechanism adjusts request properties such as scheme, host, port, secure state, and prefix metadata according to supported forwarded headers. Spring APIs building URLs from the adjusted request can generate public URLs rather than internal URLs.

This is a common choice when you want Spring Framework to handle forwarded headers independently of container-specific capabilities. You still must ensure the proxy overwrites incoming headers and the application receives traffic only from trusted proxies.

## 4. Which strategy to choose?

You can choose based on these questions:

1. Does the application run behind a reverse proxy or ingress?
2. Does the proxy send the public scheme, host, port, and prefix?
3. Does the proxy strip or overwrite client-sent forwarded headers?
4. Does the container in use have suitable native forwarding support?
5. Does the application use Servlet MVC or WebFlux?

Selection guide:

| Environment | Recommended direction |
|---|---|
| Running directly, no proxy | NONE |
| Behind proxy, want Spring Framework to process headers | FRAMEWORK |
| Behind proxy, container has configured and tested native support | NATIVE |
| Behind multiple proxy layers | Pick one mechanism, normalize headers at the trust boundary, and verify the proxy chain |

Do not enable multiple mechanisms simultaneously just to be sure headers are picked up. If the container already modifies the request and the framework then interprets the same headers again, host, scheme, or prefix values may be applied twice. Choose one strategy as the primary handler.

If the property is omitted, the default behavior typically corresponds to not processing forwarded headers; deployment environments or container settings may add their own behavior. Check the actual effective configuration rather than assuming from a single YAML file.

## 5. Basic configuration in application.yml

For a Spring MVC application behind a reverse proxy:

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework
~~~

Equivalent in application.properties:

~~~properties
server.port=8080
server.forward-headers-strategy=framework
~~~

With WebFlux, server.forward-headers-strategy remains the Spring Boot configuration point; the framework-side processing uses the corresponding reactive mechanism instead of a Servlet filter.

There is no need to manually register an extra ForwardedHeaderFilter if Spring Boot already auto-configures it via FRAMEWORK. Adding a duplicate filter can cause requests to be adjusted multiple times or make filter ordering hard to reason about.

## 6. Nginx reverse proxy example

If Nginx directly terminates TLS from clients and proxies requests to Spring Boot, the configuration can forward external information as follows:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location / {
        proxy_pass http://orders-service:8080;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

This example assumes Nginx sees the public HTTPS connection and terminates TLS itself. In that case, $scheme is https and $server_port is the listener's public port.

In the Internet-edge example, X-Forwarded-For is set to the peer address Nginx directly observes. This discards any X-Forwarded-For chain a client might have sent. If there is a trusted load balancer in front, separately configure the trust chain and preserve only addresses added by authenticated proxies; never copy headers verbatim from arbitrary clients.

If TLS was already terminated at a load balancer ahead of Nginx, Nginx may only see internal HTTP. Then $scheme may be http; do not use it to overwrite the public HTTPS metadata. Configure the trusted upstream proxy layer to overwrite forwarded headers, restrict Nginx to accept traffic only from that layer, and forward verified values according to the topology.

Specifically, never blindly use $http_x_forwarded_proto or $http_x_forwarded_host from arbitrary clients. Preserve these values only when a trusted upstream has stripped forged headers and set them itself.

## 7. Proxy stripping prefix and X-Forwarded-Prefix

Some systems expose APIs under the /gateway prefix while Spring Boot routes start at /api. The proxy may strip the prefix before forwarding:

~~~text
Public URL:  https://api.example.com/gateway/api/orders
Backend URL: http://orders-service:8080/api/orders
~~~

If the proxy does not pass the public prefix, Spring may produce redirects or links like:

~~~text
http://orders-service:8080/api/orders
~~~

When the proxy is configured to strip the prefix, it can send:

~~~http
X-Forwarded-Prefix: /gateway
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
X-Forwarded-Port: 443
~~~

Spring Framework can use this prefix when building URLs from the request. Ensure the prefix is applied only once:

- If the proxy preserves /gateway in the forwarded path, do not configure an extra prefix in a way that duplicates it in URLs.
- If the proxy strips /gateway, pass the public prefix so the application reconstructs external URLs.
- If the application already has server.servlet.context-path, distinguish the internal context path from the proxy-added prefix.

The right result must be a URL that clients can call, not an internal path the proxy uses to reach the backend.

## 8. How do forwarded headers affect URLs in Spring?

When the request is adjusted properly, APIs reading request info can reflect the external address:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@GetMapping("/diagnostics/request")
Map<String, Object> requestInfo(HttpServletRequest request) {
    return Map.of(
        "scheme", request.getScheme(),
        "secure", request.isSecure(),
        "serverName", request.getServerName(),
        "serverPort", request.getServerPort(),
        "contextPath", request.getContextPath(),
        "requestURI", request.getRequestURI()
    );
}
~~~

This endpoint should only be used in development or testing environments; do not expose unnecessary infrastructure details in production.

URL-building APIs like ServletUriComponentsBuilder.fromCurrentRequest() can use metadata adjusted by the forwarded-header mechanism. This is helpful when:

- Creating a Location header after a POST creates a resource.
- Building absolute links in responses.
- Generating redirects back to a frontend.
- Building callback URIs for an OAuth2 Client using the request base URL.
- Constructing navigation links in HATEOAS content.

Forwarded headers do not automatically rewrite URLs hard-coded in application.yml, a database, or environment variables. If a server URL is statically configured, update that configuration to match the public domain.

## 9. Impact on OAuth2/OIDC redirect URIs

Spring Security OAuth2 Client commonly uses a redirect URI template containing {baseUrl}:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          my-client:
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

If the application runs behind an HTTPS proxy yet Spring sees only internal HTTP, {baseUrl} may resolve to http://... . An Identity Provider registered with https://... will reject it with a redirect URI mismatch error.

When forwarded headers are processed correctly, the base URL can reflect the public scheme and host. After configuring, still verify the actual authorization request in the browser's Network tab:

- Does redirect_uri use the HTTPS scheme?
- Do host and port match the public domain?
- Is the context path or prefix preserved?
- Does the callback path match registrationId?

Do not work around a redirect URI mismatch by loosening the registered redirect URI list to wildcards. Fix the proxy metadata and register exact URIs.

## 10. Impact on springdoc-openapi and Swagger UI

If the application or a customizer builds documentation URLs based on the current request, forwarded headers help Spring recognize the right public scheme, host, and prefix. This can affect:

- Absolute URLs in responses or documentation links.
- servers dynamically built from the request.
- Swagger UI loading API docs through a reverse proxy prefix.
- OAuth2 redirect URLs for Swagger UI if configured relative to the public address.

However, not every springdoc configuration infers the server URL from forwarded headers. If OpenAPI has statically declared servers, static values remain authoritative. Inspect the final JSON at /v3/api-docs and the requests Swagger UI actually sends.

Example when the public API sits under the /gateway prefix:

~~~yaml
springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
~~~

These properties define documentation endpoints inside the application. The proxy still needs to map the public path to the right backend path and send the proper prefix/scheme/host if rewriting URLs. Do not add /gateway to proxy rewrites, context path, and OpenAPI server URLs alike if it is already combined at another layer.

## 11. Trust boundary: accept forwarded headers only from trusted proxies

Forwarded headers can be spoofed if clients send them directly to the application:

~~~http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
~~~

If the application trusts those values, it can create redirects or absolute links pointing to a caller-specified host. This can lead to host-header poisoning, redirects to wrong domains, unintended callback URIs, or inaccurate log entries.

Mandatory principles:

1. Place the application behind a trusted proxy and restrict direct Internet access to backend ports.
2. The edge proxy must strip or overwrite client-sent forwarded headers.
3. Trust forwarded headers only when generated by proxies within a controlled topology.
4. If multiple proxies exist, explicitly define which proxies are trusted and how address chains are processed.
5. Do not use X-Forwarded-For as an authenticated identity; it is network metadata that can be forged if the trust chain is wrong.
6. Validate valid Host headers at the ingress/proxy and application.

If the header source cannot be controlled, choose NONE or configure a mechanism that only strips headers instead of interpreting them. Spring Framework provides a remove-only forwarded-header handling mode in certain filter configurations; its purpose is to remove untrusted headers before the application uses the request, not to trust client-supplied values.

## 12. Configuring multiple proxy layers

In multi-layer deployments, e.g., CDN → load balancer → ingress → Spring Boot, each layer can add or append forwarded headers. Clearly determine:

- Which layer terminates TLS?
- Which layer sees the real client IP?
- Which layer is permitted to write Forwarded or X-Forwarded-*?
- Are headers overwritten or appended?
- Which proxies in the chain will Spring/container trust?

You cannot assume the first or last entry in X-Forwarded-For is always the trusted client address. If using Tomcat native support, configure trusted/internal proxies per container documentation. If using Spring Framework, ensure the edge proxy normalizes headers and the backend cannot be called directly from untrusted sources.

Avoid having each layer independently add an X-Forwarded-Prefix or alter X-Forwarded-Proto without a convention. Consistent headers across the entire route prevent malformed URLs and hard-to-trace issues.

## 13. Testing forwarded headers through the proxy

Prefer testing with requests passing through the actual reverse proxy/ingress in use, rather than calling the backend port directly.

You can use a temporary diagnostic endpoint in development:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ForwardedHeaderProbeController {

    @GetMapping("/_diagnostics/request-url")
    Map<String, Object> inspect(HttpServletRequest request) {
        return Map.of(
            "scheme", request.getScheme(),
            "secure", request.isSecure(),
            "host", request.getServerName(),
            "port", request.getServerPort(),
            "contextPath", request.getContextPath(),
            "requestURI", request.getRequestURI()
        );
    }
}
~~~

Call the public URL:

~~~bash
curl -i https://api.example.com/gateway/_diagnostics/request-url
~~~

The output should reflect the public address as designed. If the proxy strips the /gateway prefix, inspect the context path/request URI after Spring applies the forwarded prefix.

After testing, remove or secure the diagnostic endpoint. Do not let this endpoint leak internal hosts, ports, proxy topology, or sensitive request data in production.

### Inspecting request headers at the proxy edge

In a test environment, you can observe what requests the backend receives or enable appropriate logging at the proxy. Confirm:

- The proxy sets X-Forwarded-Proto accurately.
- The public host is passed properly.
- The public port is preserved if needed.
- The prefix is passed when the proxy rewrites paths.
- Client-supplied forwarded headers are stripped or overwritten.

Do not log full Authorization, Cookie, or token headers just to debug forwarded headers.

## 14. Testing with MockMvc

For Servlet applications using the FRAMEWORK strategy, integration tests can send forwarded headers and verify the adjusted request URL. Example test endpoint returning scheme/host:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ForwardedHeaderTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void usesPublicSchemeAndHostFromForwardedHeader() throws Exception {
        mockMvc.perform(get("/_test/request-url")
                .header(
                    "Forwarded",
                    "proto=https;host=api.example.test"
                ))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.scheme").value("https"))
            .andExpect(jsonPath("$.host").value("api.example.test"));
    }
}
~~~

The test reflects only the filter configuration actually enabled in the test ApplicationContext. If the test does not run with server.forward-headers-strategy=framework, merely adding the header does not prove the filter is active.

Consider adding tests for:

- X-Forwarded-Proto and X-Forwarded-Host if the real proxy uses this header group.
- X-Forwarded-Prefix if path rewriting is used.
- Requests without forwarded headers.
- Spoofed headers from untrusted sources at the proxy/edge test layer.
- Redirect URIs or Location headers generated from the request.

For WebFlux, use WebTestClient and verify the request URI after ForwardedHeaderTransformer is applied. Exact test setup depends on the application's reactive server configuration.

## 15. Signs of misconfiguration and how to handle them

| Symptom | Possible cause | How to check |
|---|---|---|
| Redirect produces http:// URLs despite client using HTTPS | Missing X-Forwarded-Proto/Forwarded or strategy not enabled | Check headers sent by proxy and request scheme |
| Redirect points to container hostname | External host not forwarded or not trusted | Check Host and X-Forwarded-Host |
| URL contains port 8080 instead of 443 | Public port lost or native container ignores port header | Check X-Forwarded-Port and container config |
| URL misses /gateway prefix | Proxy stripped prefix without sending X-Forwarded-Prefix | Check rewrite and prefix header |
| URL has prefix repeated twice | Prefix added at multiple layers | Check proxy rewrite, context path, and forwarded prefix |
| Redirect loop between HTTP and HTTPS | Proxy sends wrong proto or both app and proxy enforce redirects | Check where TLS terminates and X-Forwarded-Proto |
| Client IP is always proxy address | Client IP header unprocessed or wrong trust chain | Check X-Forwarded-For and proxy trust config |
| Client can change host in links | Proxy fails to overwrite forwarded host or backend is directly reachable | Block direct access and normalize headers at edge proxy |
| Tomcat and Spring give different results | Wrong NATIVE/FRAMEWORK choice or double processing | Choose one strategy and inspect container |
| Swagger UI calls wrong server URL | Static OpenAPI servers or unconfigured public URL | Check /v3/api-docs and proxy mapping |

## 16. Pre-deployment checklist

- [ ] Identified which layer terminates TLS and which layer forwards requests to Spring Boot.
- [ ] Explicitly chosen NONE, NATIVE, or FRAMEWORK.
- [ ] Not enabling native and framework mechanisms simultaneously for the same header chain.
- [ ] Reverse proxy strips or overwrites client-sent forwarded headers.
- [ ] Backend cannot be accessed directly from untrusted sources.
- [ ] Forwarded or X-Forwarded-* reflect accurate public scheme, host, and port.
- [ ] X-Forwarded-Prefix is used only when a path prefix is rewritten by the proxy.
- [ ] Verified internal context path and external prefix are not duplicated.
- [ ] OAuth2/OIDC redirect URIs resolve to the right public HTTPS domain.
- [ ] Absolute links and Location headers reflect the public URL.
- [ ] OpenAPI servers verified in the final JSON, not assumed.
- [ ] Trust chain for client IPs and proxies defined.
- [ ] Integration tests cover scheme, host, prefix, and critical redirects.
- [ ] Forwarded-header diagnostic endpoints removed or secured after testing.

## Conclusion

server.forward-headers-strategy selects how Spring Boot interprets metadata from reverse proxies: **NONE** ignores forwarded headers, **NATIVE** uses the web server/container's support, and **FRAMEWORK** uses Spring Framework's mechanism. Choose a strategy suited to Servlet or WebFlux, normalize Forwarded/X-Forwarded-* at a trusted proxy, and verify the scheme, host, port, and prefix seen by the application. Forwarded headers affect redirects, OAuth2 callbacks, absolute links, and request-derived documentation URLs, though they do not rewrite statically configured URLs. Most importantly, never trust client-supplied headers: the proxy must strip or overwrite them, and the backend should accept traffic only from controlled proxy layers.
