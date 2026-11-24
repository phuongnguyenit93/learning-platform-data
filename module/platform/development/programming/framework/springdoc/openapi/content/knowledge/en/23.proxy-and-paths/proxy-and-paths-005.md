# Forwarded, X-Forwarded-* and scheme, host, prefix information

When a Spring Boot application runs behind a load balancer, ingress, or reverse proxy, the backend often cannot see the URL the user accessed. A client may call HTTPS at api.example.com/gateway, while the proxy connects to the backend over HTTP at 10.0.0.12:8080 and strips the /gateway prefix before forwarding. If the backend relies solely on the internal request, redirects and URLs in OpenAPI documentation can end up using the wrong scheme, host, port, or path prefix.

The Forwarded and X-Forwarded-* headers pass original request metadata through the proxy. Spring Boot can process these headers so the application sees more accurate public information. You need to understand each header, rules when multiple proxies are present, and trust boundaries to configure this properly without opening the door to forged headers.

## 1. Why does the backend need to know the public URL?

Suppose a user opens:

~~~text
https://api.example.com/gateway/docs
~~~

The reverse proxy forwards the request to the backend:

~~~text
http://10.0.0.12:8080/docs
~~~

The backend sees HTTP, an internal hostname, and a path without the prefix. If the application builds redirects or absolute URLs from the internal request, the result may be:

~~~text
http://10.0.0.12:8080/swagger-ui/index.html
~~~

That address cannot be used from an external browser. The application needs the metadata of the public request:

| Property | Expected public value |
| --- | --- |
| Scheme | https |
| Host | api.example.com |
| Port | 443 |
| Prefix | /gateway |
| Swagger UI URL | https://api.example.com/gateway/docs |

Forwarded headers tell the backend which properties should be preserved as requests traverse network layers.

## 2. The Forwarded header per RFC 7239

RFC 7239 defines the standard header named Forwarded. A proxy can include attributes such as:

~~~http
Forwarded: for=203.0.113.25;proto=https;host=api.example.com
~~~

Common parameters:

| Parameter | Meaning |
| --- | --- |
| for | Address of the client or the node preceding the proxy |
| by | Address of the proxy node adding the Forwarded element |
| proto | Client-side request scheme, e.g. http or https |
| host | Host header used by the client when sending the request to the proxy |

Forwarded can contain multiple elements separated by commas. Each element describes a hop in the proxy chain. Example:

~~~http
Forwarded: for=203.0.113.25;proto=https;host=api.example.com, for=10.0.1.8;proto=http;host=service.internal
~~~

Values may require double quotes when containing special characters. IPv6, ports, and quoted-strings must also be parsed according to RFC syntax rather than splitting strings manually on commas or semicolons in application code.

Forwarded has no standard parameter to represent a path prefix. Prefix information is usually passed via the extension header X-Forwarded-Prefix.

## 3. Common X-Forwarded-* headers

The X-Forwarded-* group is a widely adopted convention between reverse proxies and applications:

| Header | Information | Example |
| --- | --- | --- |
| X-Forwarded-For | List of client and proxy IPs traversed | 203.0.113.25, 10.0.1.8 |
| X-Forwarded-Host | Public host accessed by the client | api.example.com |
| X-Forwarded-Proto | Public scheme | https |
| X-Forwarded-Port | Public port | 443 |
| X-Forwarded-Prefix | Prefix added or stripped by the proxy when forwarding | /gateway |

Example of a proxy-forwarded request:

~~~http
GET /docs HTTP/1.1
Host: app.internal
X-Forwarded-For: 203.0.113.25
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /gateway
~~~

The backend receives request path /docs but can reconstruct the public URL https://api.example.com/gateway/docs if the proxy and framework are configured consistently.

X-Forwarded-Prefix is not a standard header in RFC 7239; it is a convention supported by many proxies and frameworks. Verify which headers your actual proxy sends and whether the running framework understands them.

## 4. Comparing Forwarded and X-Forwarded-*

Forwarded is the standardized header in RFC 7239. X-Forwarded-* is a group of deployment convention headers that existed widely beforehand.

| Criterion | Forwarded | X-Forwarded-* |
| --- | --- | --- |
| Standard | RFC 7239 | Common convention, no single unified RFC for the whole group |
| Host | host=... | X-Forwarded-Host |
| Scheme | proto=... | X-Forwarded-Proto |
| Client IP | for=... | X-Forwarded-For |
| Port | Can appear inside host per URI authority syntax | X-Forwarded-Port |
| Prefix | No dedicated standard attribute | X-Forwarded-Prefix |

Some proxies send both Forwarded and X-Forwarded-*. Avoid letting the two header sets carry conflicting values. Choose one normalization policy at the edge proxy and inspect how the container/framework behaves when both are present.

Do not write a simplistic custom parser for Forwarded if the application only needs framework handling. The syntax includes quoted-strings, multiple hops, and IPv6; an incomplete parser can misinterpret hosts or client addresses.

## 5. What do scheme, host, port, and prefix affect?

Forwarded attributes are not just for logging. They can affect URLs generated by the framework:

- Scheme determines whether URLs start with http or https, secure request status, and certain redirects.
- Host determines the hostname in absolute URLs, callback links, or server URLs.
- Port determines the public port when the URL does not use the default port.
- Prefix helps reconstruct the public path when the proxy strips a prefix before forwarding to the backend.
- Client IP can be used for logging, auditing, rate limiting, or network policies, but is only safe when you know which hop is trusted.

In Springdoc integration, this metadata matters when Swagger UI redirects to static pages, loads swagger-config, loads OpenAPI JSON/YAML, or when the OpenAPI document has a request-inferred server URL. Inspect the generated specification rather than assuming all URLs are automatically correct.

## 6. Configuring Spring Boot to process forwarded headers

Spring Boot provides the server.forward-headers-strategy property:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Common values:

| Value | Behavior |
| --- | --- |
| none | Do not enable automatic forwarded-header processing |
| native | Use the web server/container's forwarded-header support |
| framework | Use Spring Framework's forwarded-header processing mechanism |

For the servlet stack, the framework strategy uses ForwardedHeaderFilter. For WebFlux, Spring uses the corresponding request transformer, typically ForwardedHeaderTransformer. Exact support details also depend on the Spring Boot version, web server, and application configuration.

Choose a strategy that fits the proxy architecture. Do not enable multiple overlapping mechanisms if they both modify scheme, host, port, or prefix. Double processing can produce malformed URLs or duplicated prefixes.

Example using the framework strategy when the backend runs behind a proxy:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

If the application needs manual forwarded-header processing or the container already has native configured, inspect the respective configurations and make sure only one layer is responsible for transforming metadata.

## 7. Servlet MVC: ForwardedHeaderFilter

In Spring MVC, ForwardedHeaderFilter wraps the request so servlet APIs see the metadata forwarded by the proxy. APIs such as getScheme(), isSecure(), getServerName(), getServerPort(), and URI/context path can reflect public values once the filter processes the request.

Spring Boot can auto-configure the filter via server.forward-headers-strategy=framework. When using this automatic mechanism, do not register a second ForwardedHeaderFilter without a specific reason.

If registering the filter manually, set the filter order appropriately so components building redirects or URLs execute after the request has been transformed. Registration and filter ordering must align with Spring Security and other filters in the application.

## 8. WebFlux: ForwardedHeaderTransformer

In WebFlux, requests are reactive server requests rather than servlet requests, so servlet filters are not used. Spring Framework provides ForwardedHeaderTransformer to adjust request information based on forwarded headers.

In Spring Boot, server.forward-headers-strategy=framework instructs the framework to process forwarded metadata for the appropriate web stack. Do not use ForwardedHeaderFilter in a pure WebFlux application.

If configuring the transformer manually, avoid registering a second transformer or combining a transformer with a native mechanism processing the same headers. Verify URLs generated by WebFlux handlers, redirects, and Springdoc after enabling configuration.

## 9. TLS-terminating proxy: preserving the https scheme

A common pattern:

~~~text
Browser --HTTPS--> Reverse proxy --HTTP--> Spring Boot
~~~

The browser connects via HTTPS to the proxy, while the proxy forwards over HTTP to the backend. If the backend does not receive metadata, the request may be seen as HTTP. The application could then issue redirects to http, break absolute URLs, or cause issues with Secure cookies.

The proxy should pass the original scheme, for example:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Port: 443
~~~

With RFC 7239:

~~~http
Forwarded: proto=https;host=api.example.com
~~~

The proto value must describe the scheme the client used to connect to the proxy, not the scheme the proxy uses to connect to the backend. If there are multiple load balancer layers, the first layer terminating TLS must pass trusted metadata so downstream layers do not erroneously overwrite it with http.

## 10. Host and port must be allowed public hosts

When a proxy forwards a request, the backend's Host header may be an internal hostname. X-Forwarded-Host tells the application which public hostname the client used.

Example:

~~~http
Host: spring-app.service.local:8080
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
~~~

The application can use this information to construct public URLs if forwarded headers are trusted and processed properly.

The Host header is an input that must be controlled. The proxy should accept only hostnames configured in its virtual host/server_name or corresponding allowlist. Never use an arbitrary client-supplied X-Forwarded-Host value to generate critical URLs, email links, redirects, or documentation contents.

If the public host uses a non-default port, ensure the proxy passes the accurate port. If the host already contains a port, avoid generating URLs with a duplicated port. Inspect the final absolute URLs in responses and the OpenAPI document.

## 11. Prefix when the proxy strips a path

Suppose a client accesses:

~~~text
https://api.example.com/gateway/openapi
~~~

The proxy removes /gateway before forwarding the request:

~~~text
Backend receives: /openapi
X-Forwarded-Prefix: /gateway
~~~

The backend needs to recognize the public prefix to build corresponding redirects or URLs. Nginx example:

~~~nginx
location /gateway/ {
    proxy_pass http://127.0.0.1:8080/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-Prefix /gateway;
}
~~~

With location /gateway/ and a proxy_pass URI ending in a slash, Nginx replaces the URI part matching location with the specified URI. Thus /gateway/openapi becomes /openapi at the backend. X-Forwarded-Prefix passes back the stripped public prefix.

If the proxy does not strip the prefix, the backend must be configured to accept the prefixed path or matching route rewrite. Do not send X-Forwarded-Prefix to add a prefix that the backend already handles via context path if that causes the prefix to be doubled.

## 12. Handling a chain of multiple proxies

A request can traverse multiple layers:

~~~text
Browser -> CDN -> Load balancer -> Ingress -> Nginx -> Spring Boot
~~~

Each proxy may add or overwrite forwarded metadata. Therefore you must establish:

1. Which proxy is the first trusted point that knows the public scheme and host.
2. Which proxies are permitted to append addresses to X-Forwarded-For.
3. Which proxy is responsible for normalizing X-Forwarded-Host, Proto, Port, and Prefix.
4. Whether the backend accepts traffic only from authorized proxies or can be called directly.
5. Whether the framework is configured to process the forwarded chain according to the exact trust boundary.

X-Forwarded-For is typically a comma-separated list of IPs. With multiple hops, you cannot arbitrarily take the first or last element and assume it is the real client. You must know which proxy added each entry and configure trusted proxies accordingly.

Forwarded can also contain multiple elements in proxy order. Parsing the chain must follow the standard and trust policy, not simply whichever string position the application prefers.

## 13. Trust boundaries and spoofing risks

If the backend is directly reachable, an attacker can send:

~~~http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
X-Forwarded-Prefix: /trusted
~~~

If the application trusts these headers, it can produce redirects or documentation URLs pointing to the attacker's domain. A forged X-Forwarded-For can also corrupt logs, audits, or access limits if the application mistakenly treats it as the client IP.

Protective measures:

- Allow the backend to accept traffic only from permitted reverse proxies or networks.
- The edge proxy must strip or overwrite forwarded headers supplied by clients.
- Use a public host allowlist at the proxy and application where available.
- Never use a forwarded IP as the basis for user authentication.
- Configure a clear trusted proxy chain across infrastructure and application layers.
- Test behavior when requests hit the backend directly, if such an access path exists.

ForwardedHeaderFilter and ForwardedHeaderTransformer turn headers into request information used by the application. They do not verify on their own whether the proxy sending the header is trustworthy. The trust boundary must be enforced at the network/proxy layer.

## 14. Impact on Springdoc and OpenAPI servers

Springdoc builds documentation from request mappings, configuration, and request context. Behind a proxy, forwarded metadata can affect redirects and URLs generated from the request. If the OpenAPI document contains a request-inferred servers URL, check whether host, scheme, port, and prefix match the public address.

Example of expected server URL:

~~~yaml
servers:
  - url: https://api.example.com/gateway
~~~

If the document instead generates:

~~~yaml
servers:
  - url: http://spring-app.service.local:8080
~~~

then client generators or Swagger UI may mistakenly call the internal backend. Inspect /v3/api-docs or your custom api-docs path to check the servers value. If the project declares servers explicitly via @OpenAPIDefinition or OpenApiCustomizer, explicit configuration may determine the URL instead of request metadata.

With Swagger UI, check in order:

1. Entry URL and redirect Location.
2. swagger-config URL.
3. OpenAPI JSON/YAML URL inside swagger-config.
4. Server URL inside the OpenAPI document.
5. The URL that Try it out actually calls.

If the UI renders properly yet Try it out calls an internal hostname, the fault may lie in the servers URL or document config rather than static resource paths.

## 15. Spring Security, redirects, and cookies

An accurate public scheme affects redirects during authentication flows. For example, an application running behind a TLS-terminating proxy without receiving X-Forwarded-Proto may generate an http redirect instead of https.

This is especially important for:

- OAuth2/OIDC login redirect URIs.
- Redirects from the login page back to the original URL.
- Cookies with the Secure attribute.
- Absolute links generated by the application.
- Swagger UI redirects to static resources.

Forwarded headers do not replace OAuth client configuration. Redirect URIs still must be registered accurately with the identity provider and match the actual public URL. Likewise, CORS cannot fix a wrong scheme or host; CORS is a cross-origin access policy, not a URL reconstruction mechanism.

## 16. A more complete Nginx configuration example

The example below assumes Nginx is the direct public proxy, terminates TLS, and strips the /gateway prefix:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location /gateway/ {
        proxy_pass http://127.0.0.1:8080/;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-Prefix /gateway;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

Spring Boot:

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework

springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
~~~

Expected public URLs:

~~~text
https://api.example.com/gateway/docs
https://api.example.com/gateway/openapi
https://api.example.com/gateway/openapi.yaml
~~~

This example assumes Nginx is the direct public proxy, so X-Forwarded-For is overwritten with the real peer address. If Nginx sits behind a trusted load balancer, design separately how to preserve the IP chain of verified hops; do not append client-supplied X-Forwarded-For verbatim. If the load balancer already terminated TLS, Nginx's $scheme variable may be http. In that case, do not blindly use $scheme as the public scheme; derive the value from metadata sent by the trusted load balancer and ensure Nginx strips/overwrites client headers before forwarding.

The example above is only suitable when Nginx is a controlled trust point. If multiple proxies are involved, redesign the header chain and network allowlists rather than copying the configuration mechanically.

## 17. Testing forwarded headers locally

You can simulate headers with curl when calling the local backend:

~~~bash
curl -i http://localhost:8080/docs \
  -H "X-Forwarded-Host: api.example.com" \
  -H "X-Forwarded-Proto: https" \
  -H "X-Forwarded-Port: 443" \
  -H "X-Forwarded-Prefix: /gateway"
~~~

This is only a simulated test in a controlled local environment. Do not use this spoofed request to conclude that the production system has established a safe trust boundary.

Verify further:

~~~bash
curl -i https://api.example.com/gateway/docs
curl -i https://api.example.com/gateway/openapi
curl -i https://api.example.com/gateway/openapi.yaml
~~~

Observe the Location response header, Content-Type, and URLs in swagger-config. Open browser Developer Tools to inspect real requests to swagger-config, static assets, and the OpenAPI document.

## 18. Common errors

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Redirect uses http despite client using https | X-Forwarded-Proto missing or wrong | Proxy passes public proto and Spring processes forwarded headers |
| URL uses internal hostname | Host/X-Forwarded-Host does not reflect public hostname | Proxy normalizes host and accepts only allowed domains |
| Port is wrong or duplicated | X-Forwarded-Port and host authority are inconsistent | Normalize host/port at the proxy and check final URL |
| /gateway prefix disappears | Proxy strips prefix without sending X-Forwarded-Prefix | Send prefix and enable appropriate forwarded-header handling |
| Prefix appears twice | Prefix was kept in backend path yet added again | Pick one layer responsible for handling the prefix |
| X-Forwarded-For contains multiple IPs | Request traversed multiple proxies | Identify trusted proxy chain and how to select client IP |
| Client can set X-Forwarded-Host | Proxy does not strip/overwrite client headers | Normalize headers at the edge and block direct backend access |
| MVC works but WebFlux fails to handle properly | Servlet filter used in reactive stack or misconfiguration | Use the forwarded-header mechanism matching WebFlux |
| Swagger UI loads but Try it out calls wrong host | servers URL or swagger-config contains internal URL | Check OpenAPI servers and document URL in config |
| OAuth redirect URI mismatch | Public scheme/host/prefix reconstructed wrongly or stale client registration | Align forwarded metadata and redirect URI at identity provider |

## 19. Deployment checklist

- [ ] Public URL identified including scheme, host, port, and prefix.
- [ ] Every proxy hop and TLS termination point identified.
- [ ] Forwarded or X-Forwarded-* chosen as the consistent metadata source.
- [ ] Edge proxy strips or overwrites client-sent forwarded headers.
- [ ] X-Forwarded-Host contains only allowed public hostnames.
- [ ] X-Forwarded-Proto reflects the client-side scheme, not the internal connection to backend.
- [ ] X-Forwarded-Port matches the public port.
- [ ] X-Forwarded-Prefix used only when the proxy altered the prefix according to convention.
- [ ] Backend accepts requests only from trusted proxies if trusting forwarded headers.
- [ ] server.forward-headers-strategy chosen appropriately for servlet or reactive stack.
- [ ] No duplicate filters/transformers registered.
- [ ] Redirect Location and OpenAPI servers URLs verified.
- [ ] swagger-config, Swagger UI assets, and Try it out verified.
- [ ] OAuth redirect URI and Secure cookies verified if authentication is used.
- [ ] Tested via the public URL and verified the direct-backend access case.

Forwarded and X-Forwarded-* help Spring Boot reconstruct the public scheme, host, port, and prefix when requests pass through a proxy. For Springdoc to generate accurate redirects and documentation URLs, the proxy must pass accurate metadata, Spring must process it according to the appropriate web stack, and the backend must trust headers only from controlled proxies. When multiple proxies exist, manage the trust chain explicitly and verify final URLs using real responses and the OpenAPI document.
