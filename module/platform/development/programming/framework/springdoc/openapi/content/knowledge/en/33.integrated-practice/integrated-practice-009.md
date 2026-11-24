# Deploying Behind a Reverse Proxy and Testing Try It Out Paths

When a Spring Boot application runs behind Nginx, an ingress controller, an API gateway, or a load balancer, users access the API through a public address such as `https://api.example.com/shop`, while the application itself may receive requests at `http://127.0.0.1:8080`. If the proxy alters the scheme, host, port, or strips a path prefix before forwarding requests to Spring, springdoc may generate internal URLs or Swagger UI may send Try it out requests to the wrong address.

To deploy properly, synchronize three pieces: the proxy must forward original request information, Spring Boot must trust and process forwarded headers from authorized proxies, and the OpenAPI document must contain a server base URL that consumers can actually reach. Then verify Swagger UI, swagger-config, OpenAPI JSON, and the final URL called when clicking Try it out.

## 1. Request flow through a reverse proxy

A public request typically goes through these steps:

1. The browser sends a request to the public HTTPS domain.
2. The reverse proxy terminates TLS, receives the public host/path, and applies route rewrites.
3. The proxy forwards the request to Spring Boot over internal HTTP or internal HTTPS.
4. Spring handles the controller, springdoc, or Swagger UI.
5. The response returns through the proxy and is rendered by the browser.

Example:

~~~text
Browser
  https://api.example.com/shop/catalog/swagger-ui.html
             |
             v
Reverse proxy
  TLS termination
  strips /shop before forwarding
  adds X-Forwarded-* headers
             |
             v
Spring Boot
  http://127.0.0.1:8080/catalog/swagger-ui.html
  server.servlet.context-path=/catalog
             |
             v
springdoc
  /catalog/openapi
  /catalog/openapi/swagger-config
  Swagger UI and OpenAPI document
~~~

If the application does not know that the original request used HTTPS and a specific public domain, it may generate redirects or server URLs based on `http://127.0.0.1:8080`. If the application does not know the proxy stripped `/shop`, generated links may omit the prefix. As a result, the Swagger UI page loads, but the documentation or Try it out fails.

## 2. Distinguishing URL components

A public URL can comprise multiple parts managed by different layers:

| Component | Example | Where configured |
| --- | --- | --- |
| Public scheme | `https` | TLS proxy and `X-Forwarded-Proto` or `Forwarded` |
| Public host | `api.example.com` | DNS, proxy, and `X-Forwarded-Host` |
| Public port | `443` | Proxy listener and `X-Forwarded-Port` if needed |
| Proxy prefix | `/shop` | Proxy route/rewrite and `X-Forwarded-Prefix` |
| Servlet context path | `/catalog` | `server.servlet.context-path` |
| Controller mapping | `/api/orders` | `@RequestMapping`, `@GetMapping`, `@PostMapping` |
| OpenAPI JSON path | `/openapi` | `springdoc.api-docs.path` |
| Swagger UI path | `/docs` | `springdoc.swagger-ui.path` |

These components are not interchangeable. `server.servlet.context-path` is the application's context path; `X-Forwarded-Prefix` describes the public prefix added or stripped by the proxy; `springdoc.api-docs.path` is the OpenAPI document route; controller mappings are the business API paths.

Do not add the same prefix in multiple places. If the proxy preserves `/shop` when forwarding, the application receives a path that already has the prefix and should not be treated as a stripped-prefix case. If the proxy strips `/shop`, the application needs that public prefix to reconstruct links.

## 3. Choosing the right forwarded headers

Two common header groups:

| Header | Meaning |
| --- | --- |
| `Forwarded` | RFC 7239 standard header, capable of carrying `proto`, `host`, and client info |
| `X-Forwarded-For` | De facto standard original client IP address |
| `X-Forwarded-Host` | Host requested by the client |
| `X-Forwarded-Port` | Public port |
| `X-Forwarded-Proto` | Original scheme, typically `https` or `http` |
| `X-Forwarded-Ssl` | Used by some proxies to indicate TLS status |
| `X-Forwarded-Prefix` | Public path prefix added, replaced, or stripped by the proxy when forwarding |

`Forwarded` is the RFC 7239 standard. The `X-Forwarded-*` group is a convention used by many proxies and cloud platforms. Check the exact headers your system's proxy actually sends; do not enable header processing for a different header format than the one in use.

For springdoc behind a reverse proxy, `X-Forwarded-Prefix` is often the easiest piece to overlook. For example, the browser calls `/shop/catalog/docs`, while the proxy forwards `/catalog/docs` to the app. The app needs the `/shop` prefix to build accurate public URLs.

## 4. Configuring a reverse proxy with Nginx

Example where Nginx accepts requests under `/shop/`, strips that prefix when forwarding to the app on port 8080, and forwards public request information:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location /shop/ {
        proxy_pass http://127.0.0.1:8080/;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Prefix /shop;
    }
}
~~~

In this configuration, the trailing slashes on `location /shop/` and `proxy_pass .../` replace the matched prefix with a slash when forwarding. Public request:

~~~text
https://api.example.com/shop/catalog/docs
~~~

is forwarded to the application as:

~~~text
http://127.0.0.1:8080/catalog/docs
~~~

The `X-Forwarded-Prefix: /shop` header lets Spring reconstruct the public path segment. The example uses `$remote_addr` so the edge proxy records the observed client IP. If your topology includes multiple trusted proxies, design the client IP chain according to your topology and trust only values set by trusted hops.

This is an illustrative example. If an upstream load balancer sits in front of Nginx and has already terminated TLS, `$scheme` or `$server_port` on Nginx may reflect the internal connection rather than the public one. In that case, Nginx must obtain the public scheme/port from the trusted upstream per your deployment configuration. Never forward client-supplied headers blindly without validation.

If the proxy keeps the `/shop` prefix when forwarding, do not apply this prefix-stripping rule. Identify the exact path Spring actually receives and configure headers so the prefix is not doubled.

## 5. Configuring Spring Boot 3 and Spring Framework 6

In Spring Boot 3.x, the property controlling forwarded header handling is `server.forward-headers-strategy`. Main values:

| Value | Behavior |
| --- | --- |
| `none` | Do not interpret forwarded headers |
| `native` | Use the embedded web server's built-in handling |
| `framework` | Use `ForwardedHeaderFilter` for Servlet or `ForwardedHeaderTransformer` for WebFlux |

If the proxy only sends `X-Forwarded-For` and `X-Forwarded-Proto`, `native` may suffice depending on the embedded server. If you need `X-Forwarded-Prefix` support to restore a stripped prefix, check your server's capabilities and consider `framework`.

Example for Spring Boot 3 with Spring MVC:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

With Tomcat and TLS terminated at the proxy, Spring Boot 3 has an additional note regarding context root redirects:

~~~yaml
server:
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
~~~

Add this Tomcat setting only in deployments with TLS termination at the proxy. If using Jetty or Reactor Netty, check the corresponding embedded server property instead of copying Tomcat settings.

When choosing `framework`, Spring Boot automatically registers the appropriate forwarded-header component. Do not register a second `ForwardedHeaderFilter` if Boot already provides one. If not using Spring Boot auto-configuration, register the filter once and ensure it runs before components that need the reconstructed request URL.

## 6. Configuring Spring Boot 4 and Spring Framework 7

Spring Boot 4 uses a new property group for forwarded headers:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: web-server
        use-prefix: true
~~~

`strategy: web-server` delegates header interpretation to the embedded server if supported. `use-prefix: true` enables `X-Forwarded-Prefix` support in the web-server mechanism. Spring Boot recommends using the web server's native support when it handles all headers sent by your proxy.

If the embedded server does not support the required header set, you can use Spring Framework's mechanism:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: framework
~~~

On the Servlet stack, Spring Framework uses `ForwardedHeaderFilter`. On the reactive stack, Spring Framework uses `ForwardedHeaderTransformer`. Spring Framework has a dedicated option to enable `X-Forwarded-Prefix` handling on the forwarded-header component. If registering the filter/transformer manually outside auto-configuration, enable the prefix option before placing the component in the chain. When using Spring Boot, verify how your minor version maps prefix properties to the `framework` strategy; do not assume changing `strategy` alone enables prefix handling everywhere.

Do not copy Boot 3's `server.forward-headers-strategy` straight into Boot 4 without checking your version. The two configuration generations use different property names.

## 7. Distinguishing Servlet and WebFlux

Forwarded header support depends on the web stack:

| Web stack | Spring Framework mechanism |
| --- | --- |
| Spring MVC / Servlet | `ForwardedHeaderFilter` |
| Spring WebFlux / Reactive | `ForwardedHeaderTransformer` |

With Spring MVC, the filter wraps the request so downstream components observe the restored scheme, host, port, and path. With WebFlux, the transformer performs the equivalent role on reactive requests.

Do not register `ForwardedHeaderFilter` in a WebFlux application. Likewise, do not add `ForwardedHeaderTransformer` to a Servlet stack. When using Spring Boot, pick the appropriate strategy and let Boot configure the right component type.

## 8. Protecting forwarded headers at the trust boundary

Forwarded headers can alter how the application perceives host, scheme, port, client IP, and prefix. Only trusted proxies should be allowed to set these headers.

At the edge proxy:

- Strip or overwrite `Forwarded` and all `X-Forwarded-*` headers sent by external clients.
- Reconstruct the headers from request properties actually observed by the proxy.
- Trust only internal hops defined in your topology.
- Block direct Internet access to application ports if the design requires all traffic to traverse the proxy.
- Never configure Tomcat's trusted-proxy pattern to allow all addresses in production.

If an application trusts a user-supplied `X-Forwarded-Host`, attackers can cause the server to generate URLs pointing to a spoofed host. This can produce malicious links, bad redirects, or OpenAPI documents containing untrusted server URLs.

Spring Framework recommends that edge proxies reset both `Forwarded` and `X-Forwarded-*`, even when only one family is used. Spring configuration should also specify only the header types the proxy is authorized to send.

## 9. Distinguishing context path, proxy prefix, and API path

Suppose a system has this configuration:

~~~yaml
server:
  servlet:
    context-path: /catalog

springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
~~~

The public proxy receives prefix `/shop` and strips it before forwarding. Resulting URLs:

| Target | Path inside application | Public path |
| --- | --- | --- |
| Swagger UI | `/catalog/docs` | `/shop/catalog/docs` |
| OpenAPI JSON | `/catalog/openapi` | `/shop/catalog/openapi` |
| Swagger config | `/catalog/openapi/swagger-config` | `/shop/catalog/openapi/swagger-config` |
| API controller | `/catalog/api/orders` | `/shop/catalog/api/orders` |

In this example, `/shop` is the proxy prefix, `/catalog` is the context path, and `/api/orders` is the controller mapping. If any part changes, update the proxy route, forwarded headers, and published URLs accordingly.

If the application uses context path `/catalog` while controller mappings already start with `/catalog`, you may be duplicating the prefix. Check actual backend URLs before adding paths to OpenAPI servers.

With Spring WebFlux, the application's base path is configured with `spring.webflux.base-path` instead of `server.servlet.context-path`. Do not use Servlet properties for reactive applications.

## 10. Setting paths for OpenAPI and Swagger UI

By default, springdoc serves OpenAPI JSON at `/v3/api-docs` and Swagger UI at `/swagger-ui.html` (typically redirecting to UI resources). You can customize these paths:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
~~~

If the application has context path `/catalog` and proxy prefix `/shop`, the corresponding public URLs are:

~~~text
https://api.example.com/shop/catalog/docs
https://api.example.com/shop/catalog/openapi
https://api.example.com/shop/catalog/openapi/swagger-config
~~~

`springdoc.swagger-ui.path` changes the Swagger UI HTML route. `springdoc.api-docs.path` changes the OpenAPI endpoint. Neither alters business controller mappings.

If Swagger UI is configured to load a static OpenAPI file, `springdoc.swagger-ui.url` must point to a file reachable by the browser. If using `springdoc.swagger-ui.config-url`, the config endpoint must also traverse the public route and prefix. Never configure an internal URL such as `http://127.0.0.1:8080/openapi` for end-user browsers.

## 11. How springdoc generates the server URL

When no static server is declared, springdoc can auto-generate the server URL from the incoming request. Consequently, request metadata seen by Spring behind a reverse proxy affects the `servers` field in the OpenAPI document.

For example, OpenAPI JSON might contain:

~~~json
{
  "servers": [
    {
      "url": "http://127.0.0.1:8080/catalog"
    }
  ],
  "paths": {
    "/api/orders": {
      "get": {
        "summary": "List orders"
      }
    }
  }
}
~~~

If this is a public document, the server URL above is wrong. Browsers would try to call the user's own loopback interface instead of the public API.

Once forwarded headers are handled properly, the server URL reflects the public address, for example:

~~~json
{
  "servers": [
    {
      "url": "https://api.example.com/shop/catalog"
    }
  ],
  "paths": {
    "/api/orders": {
      "get": {
        "summary": "List orders"
      }
    }
  }
}
~~~

In this example, combining the server base URL with path `/api/orders` produces `https://api.example.com/shop/catalog/api/orders`.

## 12. Declaring a static server URL when the public domain is fixed

If the API is always published at a fixed domain and base path, you can declare the server in OpenAPI:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;

@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com/shop/catalog",
            description = "Public API"
        )
    }
)
class OpenApiDefinitionConfiguration {
}
~~~

When the server annotation is present, springdoc uses the declared server instead of auto-generating a URL from the request. This works well when there is a single stable public base URL, such as a single production domain.

Do not hardcode a production URL if the same artifact must run across multiple environments with different domains. Use profile-based configuration or an OpenAPI bean to supply environment-specific server URLs. Ensure the server URL includes the right proxy prefix/context path and does not repeat paths already present in paths.

## 13. Using ServerBaseUrlCustomizer when auto-generated URLs need adjustment

springdoc provides `ServerBaseUrlCustomizer` to adjust auto-generated server base URLs. For example, springdoc documentation uses it to strip unwanted ports or normalize URLs shown in Swagger UI.

Before writing a customizer, check:

1. Are forwarded headers being processed properly?
2. Is the proxy sending `X-Forwarded-Prefix`?
3. Is the current server URL wrong in scheme, host, port, or path?
4. Is the wrong URL caused by `@OpenAPIDefinition(servers = ...)` overriding auto-generation?
5. Which `ServerBaseUrlCustomizer` signature does your springdoc version use?

A customizer should fix only the specific discrepancy identified. Do not use a generic string replacement across all hosts/paths if the application serves multiple environments. If the same application has multiple public hosts, check caching and concurrency before creating request-dependent server URLs.

## 14. Handling cache with multiple proxies or multiple public hosts

By default, springdoc computes the OpenAPI document and caches the result. This improves performance.

However, one application may be reached through multiple hosts or proxies, for example:

- Internal portal: `https://internal.example.net/catalog`
- Public portal: `https://api.example.com/shop/catalog`

If the server URL is generated from the first request and the cached document is shared, users accessing via another host may see the first host's server URL.

The springdoc FAQ provides the property:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Disabling cache forces OpenAPI documents to be recomputed per request. Enable this only when URLs must vary by host/proxy and after evaluating computation overhead. If the public domain is fixed or static server annotations are used, disabling cache is usually unnecessary.

With multiple groups, check each group's document. Each group has its own endpoint and may have different server/path configurations.

## 15. Understanding server base URL and paths in Try it out

Swagger UI does not infer the API address from the HTML page URL. When a user clicks Try it out, Swagger UI reads the OpenAPI document:

1. Selects an entry from `servers`.
2. Takes the operation's path and method.
3. Substitutes path parameters with user-entered values.
4. Appends query parameters, headers, body, and authorization per declarations.
5. Sends the request to the combined URL.

Example:

~~~yaml
servers:
  - url: https://api.example.com/shop/catalog
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrder
~~~

When a user enters `orderId=ORD-100`, the URL called is:

~~~text
https://api.example.com/shop/catalog/api/orders/ORD-100
~~~

If `servers[0].url` omits `/shop`, the request bypasses the proxy route. If the server URL already contains `/shop/catalog` while the operation path also contains `/shop/catalog`, the prefix is duplicated. Read both `servers` and `paths` to determine the final URL.

## 16. Checking OpenAPI JSON through the public domain

Do not test only against localhost. Verify via the domain and prefix real users will access:

~~~bash
curl -i \
  -H "Accept: application/json" \
  https://api.example.com/shop/catalog/openapi
~~~

Check swagger-config:

~~~bash
curl -i \
  -H "Accept: application/json" \
  https://api.example.com/shop/catalog/openapi/swagger-config
~~~

If using the default path, replace `/openapi` with `/v3/api-docs`. If groups are configured, append the group name after the API docs path according to the group route generated by the application.

OpenAPI responses must return a success status and valid JSON. Do not accept a 200 response whose body is an HTML login page, proxy error page, or welcome page.

## 17. Using jq to inspect servers and paths

You can download the document to a file and inspect `servers` and `paths`:

~~~bash
curl --fail --silent --show-error \
  https://api.example.com/shop/catalog/openapi \
  -o openapi-public.json

jq '{servers: .servers, paths: (.paths | keys)}' openapi-public.json
~~~

Quickly inspect server URLs:

~~~bash
jq -r '.servers[]?.url' openapi-public.json
~~~

Inspect paths for internal prefixes or duplicated prefixes:

~~~bash
jq -r '.paths | keys[]' openapi-public.json
~~~

Compare `servers[0].url` against the public URL and `paths` against controller mappings. Do not look only at the Swagger UI page, as the UI can load even when the server URL inside the document is wrong.

## 18. Checking swagger-config

Swagger UI usually loads a separate configuration document before fetching OpenAPI JSON. With the default path, the endpoint is:

~~~text
/v3/api-docs/swagger-config
~~~

If using custom path `/openapi`, inspect:

~~~text
/openapi/swagger-config
~~~

In the response, inspect the URL fields or URL list Swagger UI will use. With multiple groups, verify every group URL includes the right public prefix and context path.

If `swagger-config` returns 404 while OpenAPI JSON works, check `springdoc.swagger-ui.config-url`, custom API docs path, and proxy rewrites. If the config URL points to an internal domain, Swagger UI will call the wrong host even after the HTML page loaded from the public domain.

## 19. Checking the actual Try it out URL in the browser

After opening Swagger UI via the public URL:

1. Open the browser's Developer Tools.
2. Select the Network tab and enable Preserve log.
3. Reload Swagger UI.
4. Locate the swagger-config request.
5. Locate the OpenAPI JSON request.
6. Expand an operation and click Try it out.
7. Enter valid path/query parameters and execute the request.
8. Inspect Request URL, Request Method, Request Headers, Status Code, and Response.

The Request URL is definitive proof. It must use the exact HTTPS scheme, public domain, proxy prefix, context path, and controller path.

If the URL is wrong, inspect `servers` in OpenAPI JSON first. If `servers` is right while the browser still calls the wrong URL, check Swagger UI configuration, custom spec URL, group URLs, or request interceptors.

## 20. Checking redirects and HTTPS termination

Many systems terminate TLS at the reverse proxy and forward internal HTTP to Spring Boot:

~~~text
Browser -- HTTPS --> Proxy -- HTTP --> Spring Boot
~~~

If Spring sees only the internal connection, it may issue `http://...` redirects instead of `https://...`. Browsers may block requests due to mixed content or redirect to internal hosts/ports.

Check:

- Is `X-Forwarded-Proto` or `Forwarded: proto=https` sent by the proxy?
- Is Spring Boot processing that header properly?
- Does Tomcat need `server.tomcat.redirect-context-root=false` under TLS termination?
- Do Redirect Locations preserve the public host, HTTPS, and prefix?
- Does the Swagger UI OAuth redirect URL use the public HTTPS path?

Never work around this by allowing HTTP browser calls if production mandates HTTPS. Fix forwarded information and redirects at the proper layer.

## 21. CORS when Swagger UI and the API use different origins

If Swagger UI and the API share the same origin—for instance both under `https://api.example.com` differing only by path—browsers typically do not require CORS solely due to different paths.

If the UI is at `https://docs.example.com` while the API is at `https://api.example.com`, those are two different origins. Browsers may send preflight OPTIONS requests before the real request, especially when Authorization headers or non-simple methods are used.

Check:

- Origin of the Swagger UI page.
- Server URL in OpenAPI.
- API's CORS allowlist.
- Allowed methods and headers, including Authorization and Content-Type when needed.
- Credentials if using cookies/sessions.
- Whether the proxy forwards OPTIONS to the app or handles preflight properly.

Never combine wildcard origins with credentialed requests. If the API requires cookies/sessions, configure explicit origins and matching credentials policies.

## 22. Checking authentication and OAuth redirects

A Try it out request returning 401 or 403 may already be hitting the right URL while lacking access permissions. Separate routing errors from authentication errors:

| Symptom | What to check |
| --- | --- |
| 404 | Proxy rewrite, context path, controller mapping |
| 401 | Missing or expired token/session |
| 403 | Authenticated principal lacks permissions, CSRF, or gateway policy |
| CORS error | Preflight or response missing CORS headers |
| 502/504 | Proxy cannot reach backend or backend timed out |

With OAuth2, the redirect URL must match the public address used by the browser. If Swagger UI is served under `/shop/catalog/docs`, the OAuth redirect page needs the corresponding prefix too. Configure `springdoc.swagger-ui.oauth2-redirect-url` when auto-detection fails to generate the right public URL.

Never place production client secrets in public Swagger UI configuration. Tokens should only be entered through an appropriate Authorize mechanism with minimal lifetime and scopes.

## 23. Checking multiple OpenAPI groups

If the application has multiple groups, each group has its own documentation endpoint. For example, groups `public` and `partner`:

~~~yaml
springdoc:
  group-configs:
    - group: public
      paths-to-match:
        - /api/public/**
    - group: partner
      paths-to-match:
        - /api/partner/**
~~~

With the default API docs path, group documents are typically accessed at:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
~~~

If customizing `springdoc.api-docs.path`, check the actual routes generated by the application. The proxy must forward both the default document and group documents, and Swagger UI's Topbar must point to the right public URL for each group.

Do not check only the first group. One group can have a different server URL or path filter, causing Try it out to fail on only part of the documentation.

## 24. Pre-publication verification matrix

| Verification layer | Passing evidence |
| --- | --- |
| Proxy route | Public request reaches the right backend path |
| Forwarded headers | Scheme, host, port, and prefix reflect the public request |
| Spring Boot | Strategy matches version and embedded server |
| Swagger UI HTML | Returns 200 or valid redirect at public URL |
| swagger-config | Valid JSON; URLs do not point to internal hosts |
| OpenAPI JSON | `servers` and `paths` combine into public endpoints |
| Try it out | Request URL uses exact HTTPS, host, and prefix |
| Security | Tokens, roles, CSRF, and CORS are handled properly |
| Groups | All group URLs are reachable through the proxy |
| Trust boundary | Proxy strips/overwrites untrusted client forwarded headers |

## 25. Common mistakes

**Swagger UI loads but Try it out calls localhost.** The server URL in OpenAPI was generated from the internal request. Configure forwarded host/proto and inspect `servers`.

**URL uses http instead of https.** The proxy terminates TLS without sending `X-Forwarded-Proto`, or Spring is not processing that header.

**Missing `/shop` prefix.** The proxy strips the prefix without sending `X-Forwarded-Prefix`, or the application has not enabled prefix support.

**Prefix appears twice.** The proxy preserves the prefix in the path while the app also adds the forwarded prefix, or both server URL and operation path include the same prefix.

**Swagger UI returns 404 after changing context path.** Inspect `server.servlet.context-path`, `springdoc.swagger-ui.path`, `springdoc.api-docs.path`, and proxy rewrites.

**swagger-config returns 404.** `config-url` does not match the custom API docs path, or the proxy does not forward the config endpoint.

**OpenAPI JSON is correct but Try it out hits the wrong host.** Inspect `servers`, server annotations, and `springdoc.swagger-ui.url`/`urls` configuration.

**The first request locks the server URL for other hosts.** Check springdoc caching when one application serves multiple hosts/proxies.

**Browser blocks request even though curl succeeds.** Check CORS, preflight, mixed content, and redirects.

**Application trusts client-sent headers.** Configure the edge proxy to strip and rewrite forwarded headers; never let clients spoof host/proto/prefix.

**Registering ForwardedHeaderFilter multiple times.** If Spring Boot already auto-configures it via strategy, do not add a duplicate filter.

**Using Boot 3 properties in Boot 4.** Check the exact version because forwarded header properties were renamed.

## 26. Investigation workflow when Try it out calls the wrong URL

1. Record the Swagger UI URL opened by the user.
2. Call swagger-config via the public domain and identify the OpenAPI URL the UI will load.
3. Download OpenAPI JSON via the public domain.
4. Read `servers` and `paths` in the document.
5. Combine the server base URL with an operation path to predict the final URL.
6. Click Try it out and compare the prediction with the Request URL in the Network tab.
7. If scheme/host/port is wrong, check `Forwarded` or `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port`.
8. If the prefix is wrong, check `X-Forwarded-Prefix`, proxy rewrite, and `use-prefix`.
9. If the context path is wrong, check `server.servlet.context-path`.
10. If document servers are right but the UI calls the wrong URL, check Swagger UI config URL, custom spec URL, and groups.
11. If the URL is right but returns 401/403, investigate authentication/authorization/CSRF.
12. If the URL is right but the browser blocks it, investigate CORS, TLS, and redirects.
13. Repeat for each group and each published environment.

## 27. Deployment checklist

- [ ] Determine whether the proxy strips or preserves the prefix.
- [ ] Identify the public scheme, host, and port.
- [ ] Document proxy prefix, context path, controller mappings, and springdoc paths.
- [ ] Configure the proxy to send accurate forwarded headers.
- [ ] Edge proxy strips or overwrites client-sent forwarded headers.
- [ ] Choose `server.forward-headers-strategy` for Spring Boot 3.
- [ ] Choose `server.request.header.forwarded.strategy` and `use-prefix` for Spring Boot 4.
- [ ] Use the Servlet filter or Reactive transformer matching the stack.
- [ ] Avoid registering duplicate forwarded filters.
- [ ] Inspect generated server URLs in OpenAPI JSON.
- [ ] If declaring static servers, ensure URLs match each environment.
- [ ] Check caching when one service serves multiple public hosts.
- [ ] Verify Swagger UI, swagger-config, and all groups.
- [ ] Verify Try it out using the Browser Network tab.
- [ ] Verify CORS, authentication, OAuth redirects, and HTTPS.
- [ ] Run smoke tests through the public domain, not only via localhost.

## 28. Conclusion

Deploying springdoc behind a reverse proxy requires accurately restoring public request details and any path prefix modified by the proxy. Configure the proxy to set forwarded headers, enable the strategy matching your Spring Boot version, distinguish proxy prefixes from servlet context paths and controller mappings, and inspect `servers` in the OpenAPI document. Try it out only hits the right address when the server base URL combined with operation paths yields the exact public endpoint. Checking swagger-config, OpenAPI JSON, and the Request URL in the browser is the final confirmation before publishing documentation.

## 29. References

- [springdoc-openapi FAQ — Deploy behind a reverse proxy](https://springdoc.org/faq.html): forwarded headers, `X-Forwarded-Prefix`, `ForwardedHeaderFilter`, `ServerBaseUrlCustomizer`, and caching.
- [Spring Boot 3.5 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): `server.forward-headers-strategy`, native support, and Framework filter.
- [Spring Boot 4.2 — Embedded Web Servers](https://docs.spring.io/spring-boot/4.2/how-to/webserver.html): `server.request.header.forwarded.strategy`, `use-prefix`, and forwarded header strategies.
- [Spring Framework 7 — Forwarded Headers](https://docs.spring.io/spring/reference/web/webmvc/filters.html#filters-forwarded-headers): `Forwarded`, `X-Forwarded-*`, `X-Forwarded-Prefix`, and security considerations.
- [OpenAPI Specification 3.1 — Server Object](https://spec.openapis.org/oas/v3.1.1.html#server-object): server base URL and how to declare API servers.
- [springdoc-openapi — Swagger UI properties](https://springdoc.org/v2/faq.html): path, config URL, OpenAPI URL, group URL, and OAuth redirect properties.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): Forwarded header format.
