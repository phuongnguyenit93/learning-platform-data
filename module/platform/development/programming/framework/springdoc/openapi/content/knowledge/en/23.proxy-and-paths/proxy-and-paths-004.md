# Reverse proxy, gateway, and external paths differing from internal paths

In deployment environments, clients usually do not call a Spring Boot service directly. Requests pass through a reverse proxy, ingress, or API gateway before reaching the application. This intermediary layer may terminate TLS, change the host, add a public prefix, or rewrite the path before forwarding the request. Consequently, the URL the client sees can differ from the URL Spring MVC receives.

This difference directly affects OpenAPI documentation and Swagger UI. If the application is only aware of its internal address, OpenAPI may generate `servers` with the wrong host or scheme; links in responses may point to an internal service; Swagger UI may call endpoints missing the prefix or hit the wrong `swagger-config` endpoint. Both the proxy and the application must be configured to agree on how the public URL is recognized.

## 1. Distinguishing public URL and internal URL

Suppose a client accesses an API through a gateway:

```text
Client
  https://api.example.com/catalog/api/orders/42
             |
             v
Reverse proxy / API gateway
  public host: api.example.com
  public prefix: /catalog
  TLS: HTTPS
             |
             v
Spring Boot service
  http://catalog-service:8080/api/orders/42
```

The client sees the URL `https://api.example.com/catalog/api/orders/42`. The gateway forwards to the application over the internal network using HTTP and may strip the `/catalog` prefix. Spring Boot only sees `http://catalog-service:8080/api/orders/42` unless the proxy forwards the original request metadata.

| Component | Public value | Internal value |
| --- | --- | --- |
| Scheme | `https` | `http` after TLS termination |
| Host | `api.example.com` | `catalog-service` |
| Port | `443` | `8080` |
| Prefix | `/catalog` | May have been stripped by the gateway |
| Controller path | `/api/orders/42` | `/api/orders/42` |

These are two valid perspectives of the same request. The application needs the public metadata when generating redirects, absolute URLs, hypermedia links, or OpenAPI `servers`, while still routing to controllers according to the internal path it actually receives.

## 2. Two common prefix-rewrite patterns

A gateway can either preserve the prefix when forwarding or strip the prefix before sending the request to the application. These two approaches require different configurations.

**Preserving the prefix:**

```text
Public:  https://api.example.com/catalog/api/orders
Internal: http://catalog-service:8080/catalog/api/orders
```

The application must have a context path or routes matching `/catalog`. For example, `server.servlet.context-path=/catalog` makes controller mapping `/api/orders` accessible under `/catalog/api/orders`.

**Stripping the prefix at the gateway:**

```text
Public:  https://api.example.com/catalog/api/orders
Internal: http://catalog-service:8080/api/orders
```

The gateway removes `/catalog` before forwarding. In this case, the application still handles path `/api/orders`; the proxy needs to pass metadata indicating the public prefix is `/catalog`, typically via `X-Forwarded-Prefix`.

Do not configure `server.servlet.context-path=/catalog` when the proxy already preserves `/catalog` in the path without testing the actual flow. If both layers add the prefix, requests can become `/catalog/catalog/api/orders` or OpenAPI can generate URLs with duplicated prefixes.

## 3. Forwarded headers convey original request information

Reverse proxies typically send headers describing the public request:

| Header | Meaning | Example |
| --- | --- | --- |
| `Forwarded` | Standard RFC 7239 header describing proxy metadata such as host and proto | `for=192.0.2.10;host=api.example.com;proto=https` |
| `X-Forwarded-Host` | Host used by the client externally | `api.example.com` |
| `X-Forwarded-Proto` | Public scheme | `https` |
| `X-Forwarded-Port` | Public port | `443` |
| `X-Forwarded-For` | Client IP address and proxies in the chain | `198.51.100.20` |
| `X-Forwarded-Prefix` | Public prefix stripped by the proxy before forwarding | `/catalog` |

`Forwarded` is the standard header; `X-Forwarded-*` headers are widely adopted conventions supported by many proxies and frameworks. Not every proxy sends every header. Configuration must match the product in use and the number of proxy hops along the path.

The application should only trust forwarded headers produced by trusted reverse proxies. If a client can send `X-Forwarded-Host: attacker.example` directly to Spring Boot and the application trusts it, generated URLs can be spoofed. The edge proxy must strip or overwrite client-supplied forwarded headers and emit fresh values based on the real request.

## 4. Enabling forwarded-header handling in Spring Boot

Spring Boot has the `server.forward-headers-strategy` property to choose how the application processes proxy metadata:

```yaml
server:
  forward-headers-strategy: framework
```

Common values:

| Value | Behavior |
| --- | --- |
| `none` | Do not apply forwarded headers. The application uses the request information received by the container. |
| `native` | Use the web server/container's forwarded-header handling if supported by the container. |
| `framework` | Use Spring Framework's mechanism; in MVC this is `ForwardedHeaderFilter`, and WebFlux uses `ForwardedHeaderTransformer`. |

Choose `framework` when you want Spring Framework to handle forwarded metadata consistently across supported containers. Choose `native` when the infrastructure and container are already configured to handle forwarded headers. Do not enable multiple handling mechanisms at once if they could apply the prefix or host twice.

When the proxy strips the public prefix, verify that the framework receives `X-Forwarded-Prefix` and reconstructs the public context path as intended. When the proxy preserves the prefix in internal requests, you normally do not want to add the same prefix again via a forwarded header.

`server.forward-headers-strategy=framework` does not make forwarded headers from arbitrary sources safe. Enable it only when the application sits behind a trusted proxy and direct access to the application is controlled.

## 5. Configuring a reverse proxy with Nginx

Example where Nginx publishes a service under the `/catalog` prefix while stripping that prefix before forwarding to Spring Boot:

```nginx
location /catalog/ {
    proxy_pass http://catalog-service:8080/;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Prefix /catalog;
}
```

With `location /catalog/` and a `proxy_pass` URI ending in `/`, Nginx replaces the URI portion matching the location with the URI in `proxy_pass`; for example, `/catalog/api/orders` is rewritten to `/api/orders`. `X-Forwarded-Prefix` informs the application that the `/catalog` prefix was stripped.

In the application:

```yaml
server:
  port: 8080
  forward-headers-strategy: framework

springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
```

This is an illustrative configuration for a stripped-prefix topology. If Nginx preserves the URI or the application already has a context path, adjust `proxy_pass`, `X-Forwarded-Prefix`, and server settings so the prefix is not duplicated.

Do not copy this exact configuration for every gateway. Nginx, Kubernetes Ingress, Traefik, Envoy, and Spring Cloud Gateway have different rewrite syntaxes and forwarded-header behaviors. What must remain consistent is that public host, scheme, port, and prefix metadata accurately reflect the request the client actually sent.

## 6. Impact on OpenAPI `servers`

OpenAPI uses `servers` to describe the base URL clients use when calling paths in the document. Example:

```yaml
servers:
  - url: https://api.example.com/catalog
    description: Public gateway
paths:
  /api/orders:
    get:
      responses:
        '200':
          description: List of orders
```

Swagger UI combines the server URL with the operation path to form requests. In the example above, requests go to `https://api.example.com/catalog/api/orders`.

If springdoc infers the server URL from the request while the application only sees `http://catalog-service:8080`, Swagger UI may call the internal host or use HTTP instead of HTTPS. Handling forwarded headers helps Spring recognize the original request details; afterward, inspect `servers` in the generated document.

When the public URL is fixed and cannot be reliably inferred from the request, you can declare the server explicitly:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = @Server(
        url = "https://api.example.com/catalog",
        description = "Public gateway"
    )
)
class OpenApiServerConfiguration {}
```

Or configure it using the `OpenAPI` model:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Bean
OpenAPI storeOpenAPI() {
    return new OpenAPI()
        .addServersItem(new Server()
            .url("https://api.example.com/catalog")
            .description("Public gateway"));
}
```

Use a static URL only when it suits the deployment environment. If local, staging, and production have different hosts, manage server URLs per profile or deployment configuration. Avoid hard-coding a production host in documentation used in local environments.

## 7. Avoiding adding the prefix twice

A common mistake is having the prefix appear in both `servers.url` and `paths`:

```yaml
servers:
  - url: https://api.example.com/catalog
paths:
  /catalog/api/orders:
    get:
      responses:
        '200':
          description: OK
```

Swagger UI will combine them into `/catalog/catalog/api/orders`. If the `/catalog` prefix is already in `servers.url`, the operation path should be `/api/orders` in the example topology.

Apply a clear rule:

- `servers.url` holds the scheme, host, port, and public base prefix.
- `paths` holds operation paths relative to the server base URL.
- Do not repeat the same prefix in both places.

If the gateway rewrites both prefixes and sub-paths, verify the final public URL by inspecting the request Swagger UI generates rather than guessing from internal mappings alone.

## 8. Swagger UI and documentation endpoints also go through the proxy

When Swagger UI is published under the `/catalog` prefix, it is not only business APIs that must work. The gateway must also route all documentation endpoints:

| Public URL | Illustrative internal URL |
| --- | --- |
| `/catalog/swagger-ui.html` | `/swagger-ui.html` |
| `/catalog/swagger-ui/**` | `/swagger-ui/**` |
| `/catalog/v3/api-docs/swagger-config` | `/v3/api-docs/swagger-config` |
| `/catalog/v3/api-docs` | `/v3/api-docs` |
| `/catalog/v3/api-docs/{group}` | `/v3/api-docs/{group}` |

If the UI loads HTML but fails to load CSS/JavaScript, check the `/swagger-ui/**` route. If the page displays an error loading configuration, check `swagger-config`. If the configuration loads but the OpenAPI document returns `404`, check the `url`/`urls` value and the `/v3/api-docs` route.

If `springdoc.api-docs.path` or `springdoc.swagger-ui.path` differs from the defaults, both the gateway and Spring Security must use the customized paths. With multiple groups, verify that routing supports both JSON and YAML URLs for each group.

## 9. Context path vs. forwarded prefix

`server.servlet.context-path` sets the context path of a Servlet application. Example:

```yaml
server:
  servlet:
    context-path: /catalog
```

Controller mapping `/api/orders` will be accessed inside the application under `/catalog/api/orders`.

`X-Forwarded-Prefix` describes a public prefix that the proxy stripped or altered before forwarding the request. For example, the public path is `/catalog/api/orders`, while the application receives `/api/orders` and the proxy sends `X-Forwarded-Prefix: /catalog`.

These two mechanisms are not equivalent:

| Mechanism | Who applies the prefix? | Request path reaching controller |
| --- | --- | --- |
| `server.servlet.context-path=/catalog` | Servlet application | Context path is handled by the container before controller mapping. |
| `X-Forwarded-Prefix=/catalog` | Proxy provides metadata; Spring processes forwarded headers | The application can reconstruct the public URL while internal mappings do not include the prefix. |

With WebFlux, the context/base path is configured via the corresponding reactive server property; do not assume all Servlet properties apply to WebFlux. When switching stacks or containers, verify the properties and forwarded-header mechanism matching the runtime in use.

## 10. Redirects, absolute links, and TLS termination

Proxies typically terminate TLS at the edge and forward HTTP requests into the internal network. If the application is unaware that the external scheme is HTTPS, it may:

- Generate a redirect `Location: http://api.example.com/...` instead of HTTPS.
- Generate hypermedia links using `http://`.
- Publish an OpenAPI server URL using HTTP.
- Produce callbacks or absolute URLs with the wrong scheme.

The proxy should send `X-Forwarded-Proto: https` or `Forwarded: proto=https`; the application should process forwarded headers. If the proxy forwards the wrong scheme, fix it at the proxy before adding controller workarounds.

Do not build absolute URLs manually by concatenating `request.getScheme()`, `getServerName()`, and the path when the application is not processing forwarded headers. Prefer Spring's URI building APIs and appropriate link builders; they can use requests adjusted by forwarded metadata.

## 11. Multiple proxies and trust boundaries

A request can pass through a CDN, load balancer, ingress, and gateway before reaching Spring Boot. Forwarded headers may then contain a list of multiple addresses or a proxy may overwrite certain headers.

Define which proxy is responsible for setting each value:

1. The edge proxy strips forwarded headers sent directly by clients.
2. The edge proxy records the public host and proto.
3. Internal proxies append or normalize metadata according to infrastructure policy.
4. The application accepts requests only from trusted proxies or controlled internal networks.

Do not expose internal service ports directly to the Internet if the application trusts forwarded headers without a reliable proxy layer. If an attacker can call the service directly and supply `X-Forwarded-Host`, they can influence absolute URLs generated by the application.

In particular, do not use a forwarded host to construct links containing sensitive data or redirect to arbitrary domains without checking a public host allowlist. Forwarded headers are routing metadata, not trusted user data.

## 12. Testing OpenAPI and Swagger UI behind a proxy

After deploying behind a gateway, verify from the external client's perspective rather than calling only the internal service:

1. Call the public URL of a business endpoint and confirm the gateway routes the request properly to the controller.
2. Open the public URL of `/v3/api-docs` or your custom base path.
3. Verify `servers` has the right HTTPS scheme, host, and public prefix.
4. Verify `paths` does not duplicate prefixes and combining server + path forms the right public URL.
5. Open the public URL of `/swagger-ui.html` and check `/swagger-ui/**` assets.
6. Verify `swagger-config` points to a document URL reachable from the browser.
7. Use Swagger UI **Try it out** and inspect the Request URL in the Network tab.
8. Check that response `Location`, hypermedia links, and redirects use the public scheme/host.
9. Repeat for each group document if the application uses `GroupedOpenApi`.

Example fetching the document through the gateway:

```bash
curl -i https://api.example.com/catalog/v3/api-docs
```

Inspecting Swagger UI configuration separately:

```bash
curl -i https://api.example.com/catalog/v3/api-docs/swagger-config
```

When testing forwarded headers directly in a local environment, do so only on a trusted network:

```bash
curl -i http://localhost:8080/api/orders \
  -H 'Host: catalog-service:8080' \
  -H 'X-Forwarded-Host: api.example.com' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /catalog'
```

This command lets you observe how the application processes forwarded metadata in a test environment. It does not substitute for confirming that the real proxy strips/overwrites client headers and blocks direct access to the service.

## 13. Common errors

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| OpenAPI `servers` points to internal hostname | Application does not receive `X-Forwarded-Host` or forwarded header strategy is not enabled | Configure proxy and `server.forward-headers-strategy`, then inspect the document. |
| `servers` uses HTTP despite client accessing HTTPS | Missing or ignored `X-Forwarded-Proto` | Have proxy send public proto and Spring process forwarded headers. |
| Swagger UI calls without `/catalog` prefix | Proxy strips prefix without sending `X-Forwarded-Prefix`, or `servers` lacks base prefix | Align rewrite, forwarded prefix, and OpenAPI server URL. |
| URL has `/catalog/catalog` | Prefix added across context path, forwarded prefix, and/or `servers` multiple times | Choose one prefix model and inspect the path after joining server and operation. |
| Controller returns `404` after proxy change | Proxy keeps prefix but app lacks matching context path, or rewrite is wrong | Check actual request URI reaching the app and controller mappings. |
| Redirect `Location` points to HTTP | Application does not recognize external HTTPS scheme | Forward `X-Forwarded-Proto` and enable forwarded-header processing. |
| Hypermedia link uses internal host | Link builder uses unadjusted request or link is hard-coded | Check forwarded host, request context, and link construction. |
| Swagger UI loads but document returns `404` | Gateway does not route `/v3/api-docs` or `swagger-config` points to internal URL | Add routes for docs/config and use appropriate public or relative URLs. |
| Group docs work locally but fail via gateway | Missing route for group path or YAML suffix | Check JSON, `.yaml`, and each `/v3/api-docs/{group}`. |
| Host in links can be spoofed | Application trusts forwarded headers from untrusted sources | Allow traffic only through trusted proxies; proxy strips and rewrites headers. |
| Port or scheme mismatch behind multiple proxies | Proxy layers overwrite metadata inconsistently | Designate the authoritative proxy and normalize forwarded headers at the edge. |

## 14. Principles to follow

- Document the public-to-internal topology before configuring the proxy and springdoc.
- Decide whether the gateway keeps or strips the prefix; do not apply both simultaneously.
- Forward public host, scheme, port, and prefix using appropriate forwarded headers.
- Choose `server.forward-headers-strategy` matching the container and proxy architecture.
- Trust forwarded headers only from controlled proxies; strip forged client-sent headers.
- Keep `servers.url` as the public base URL and `paths` as relative operation paths, avoiding duplicated prefixes.
- Declare static server URLs only when appropriate for the environment; manage hosts per profile/deployment if needed.
- Route Swagger UI, static resources, `swagger-config`, and OpenAPI JSON/YAML through the gateway.
- Verify redirects, `Location`, hypermedia links, and Swagger UI Request URLs from the outside.
- Check each group document and both JSON/YAML endpoints after every proxy change.

A reverse proxy and gateway create a boundary between the address clients use and the address Spring Boot receives. When the proxy rewrites paths, the application needs reliable forwarded metadata to recognize the public host, scheme, and prefix; OpenAPI `servers` must describe the exact base URL clients call. Testing public URLs externally alongside internal requests helps catch wrong hosts, wrong schemes, missing prefixes, or duplicated prefixes early in Swagger UI and response links.

## References

- [Spring Boot – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/reference/howto/webserver.html)
- [Spring Framework – Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers)
- [RFC 7239 – Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object)
- [Nginx – ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
