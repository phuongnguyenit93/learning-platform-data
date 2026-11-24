# Comparing paths across local, test, and production environments

A Spring Boot API may run at `http://localhost:8080/api/orders` on a developer machine, `https://test.example.com/order-service/api/orders` in a test environment, and `https://api.example.com/api/orders` in production. Controllers can share the exact same mappings, yet the host, scheme, port, context path, and reverse-proxy-managed prefix differ.

When integrating springdoc-openapi, these differences affect both API call URLs and documentation endpoints like `/v3/api-docs`, `/v3/api-docs.yaml`, and Swagger UI. If proxy or forwarded-header configuration is wrong, Swagger UI may load the page yet fail to fetch the OpenAPI document, or the generated document may emit `servers` pointing to an internal hostname, HTTP instead of HTTPS, or a duplicated prefix.

## 1. Distinguishing the parts that form a URL

A URL called by clients typically has the structure:

```text
scheme://host:port/public-prefix/context-path/servlet-path/controller-mapping
```

Each component has a distinct meaning:

| Component | Example | Where usually configured |
|---|---|---|
| Scheme | `https` | TLS termination at proxy/load balancer or application |
| Host | `api.example.com` | DNS, reverse proxy, forwarded host |
| Port | `443` | Public listener or forwarded port |
| Public prefix | `/order-service` | Gateway/Ingress/reverse proxy |
| Servlet context path | `/app` | `server.servlet.context-path` for Spring MVC |
| WebFlux base path | `/app` | `spring.webflux.base-path` for Spring WebFlux |
| Servlet path | `/api` | Servlet mapping in MVC application if configured |
| Controller mapping | `/orders` | `@RequestMapping`, `@GetMapping`... |

Not every application uses all of these parts. A simple project may have only host, port, and controller mapping. An application behind a gateway may also have a public prefix handled by the proxy.

In Spring MVC, `server.servlet.context-path` sets the context path for the servlet application. In Spring WebFlux, `spring.webflux.base-path` sets the base path for reactive handlers. These two properties belong to two different web stacks; do not configure both merely to handle the same prefix.

## 2. Public paths vs. upstream paths

A reverse proxy typically receives a public URL and forwards the request to Spring Boot's internal address. The path seen by the client can differ from the path received by the application.

Example public URL:

```text
https://test.example.com/order-service/api/orders
```

The proxy can forward in one of two ways:

| Proxy type | Request path received by app | Public prefix |
|---|---|---|
| Preserves prefix | `/order-service/api/orders` | Application must serve paths with this prefix or have a matching context/base path |
| Strips prefix before proxying | `/api/orders` | Proxy must pass stripped prefix info via forwarded header if app needs to reconstruct public URLs |

What matters is agreeing on where the prefix is owned. If the proxy already strips `/order-service`, do not simultaneously configure the application to re-add the same prefix to runtime routes unintentionally. Conversely, if the proxy preserves the prefix, the application must have matching mappings.

## 3. Example of the same controller running in three environments

Suppose a controller has the mapping:

```java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping
    List<OrderResponse> listOrders() {
        return orderService.findAll();
    }
}
```

If the application has no context path or WebFlux base path, the upstream path is `/api/orders`. Three environments can be arranged as follows:

| Environment | Public URL | Upstream URL |
|---|---|---|
| Local | `http://localhost:8080/api/orders` | `http://localhost:8080/api/orders` |
| Test | `https://test.example.com/order-service/api/orders` | `http://order-app:8080/api/orders` |
| Production | `https://api.example.com/api/orders` | `http://order-app:8080/api/orders` |

In test, the gateway strips the `/order-service` prefix before forwarding to the app. Production has no separate prefix, so the public path matches the upstream path. The controller needs no mapping changes across environments.

This is an illustrative model. Actual setup depends on the gateway, ingress, context path, and servlet/base path chosen by the system.

## 4. Two common reverse proxy configurations

### Preserving the prefix when forwarding

If the proxy keeps the entire path intact, a request to `/order-service/api/orders` is forwarded to the application with the same path. The application must then serve the `/order-service` prefix, such as through a context path or matching route prefix.

Nginx example forwarding the URI unchanged:

```nginx
location /order-service/ {
    proxy_pass http://order_app;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

With `proxy_pass` having no URI after the upstream in the configuration above, Nginx forwards the current URI according to proxy_pass without-URI rules. Verify the rewrite behavior of your real Nginx config, especially if `rewrite` directives or nested locations are present.

### Stripping the prefix before forwarding

If the application serves only `/api/**`, the proxy can strip `/order-service` from the public path and send the remainder to the app:

```nginx
location /order-service/ {
    proxy_pass http://order_app/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Prefix /order-service;
}
```

In this configuration, the trailing `/` in `proxy_pass http://order_app/` replaces the URI segment matching location `/order-service/` with `/` when forwarding. For instance, `/order-service/api/orders` is sent upstream as `/api/orders`. `X-Forwarded-Prefix` tells the application which public prefix was stripped by the proxy.

Do not copy this configuration verbatim if your gateway preserves prefixes or involves multiple proxy layers. Inspect paths before and after every rewrite layer.

## 5. Forwarded headers carry external URL metadata

When TLS terminates at a load balancer, the application may receive only HTTP from the proxy. If the application inspects the internal request without knowing public metadata, it may build wrong URLs like `http://order-app:8080/...`.

Headers commonly used to convey public details:

| Header | Meaning |
|---|---|
| `Forwarded` | Standardized header per RFC 7239, can contain `proto`, `host`, and `for` |
| `X-Forwarded-Host` | Host used by the client externally |
| `X-Forwarded-Proto` | External scheme, typically `https` |
| `X-Forwarded-Port` | Public port |
| `X-Forwarded-For` | Client/proxy address chain across hops |
| `X-Forwarded-Prefix` | Public prefix that the proxy may have stripped from the request path |

An internal request might carry:

```http
Host: order-app:8080
X-Forwarded-Host: test.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /order-service
```

The application can use this metadata to construct accurate external URLs, including links, redirects, and OpenAPI server URLs, provided forwarded-header support is enabled and the proxy sends accurate values.

## 6. Configuring `server.forward-headers-strategy`

Spring Boot provides `server.forward-headers-strategy` to choose how the application handles forwarded headers.

| Value | Behavior |
|---|---|
| `none` | Do not apply forwarded headers to requests |
| `native` | Use the web server/container's forwarded-header support if supported |
| `framework` | Use Spring Framework's mechanism to process forwarded headers |

Example configuration when running behind a reverse proxy and needing Spring to handle forwarded headers:

```yaml
server:
  forward-headers-strategy: framework
```

With Spring MVC running on Tomcat, Jetty, or Undertow, the `native` strategy can work well if the container handles the headers required by your topology. When consistent `X-Forwarded-Prefix` handling via Spring Framework is needed, verify the `framework` option and behavior of your running Spring Boot/Spring Framework version.

Do not pick a strategy based solely on environment names. Choose based on the container and how the proxy sends headers, then verify the request URL seen by the application. When running directly locally without a proxy, `none` is usually clearer.

## 7. Specific configuration for Spring MVC and WebFlux

### Spring MVC

Spring MVC can set a context path in configuration:

```yaml
server:
  port: 8080
  servlet:
    context-path: /order-app
```

Controller mapping `/api/orders` is then served under context path `/order-app`.

### Spring WebFlux

Spring WebFlux can set a base path:

```yaml
server:
  port: 8080

spring:
  webflux:
    base-path: /order-app
```

Route/controller mapping `/api/orders` is attached to the application's base path per WebFlux configuration.

Do not use `server.servlet.context-path` to configure a pure WebFlux application, and do not use `spring.webflux.base-path` as a substitute for Spring MVC's context path. Confirm which web stack the project runs, especially if both MVC and WebFlux starters are on the classpath.

## 8. Configuring profiles for local, test, and production

Environment-varying settings can be separated using Spring Profiles.

`application-local.yml`:

```yaml
server:
  port: 8080
  forward-headers-strategy: none

springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
```

`application-test.yml`:

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

`application-prod.yml`:

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

In this example, the application does not add a context path itself; the proxy owns the public prefix. Local calls the application directly, while test and production receive requests through proxies. If production uses a different prefix, configure the gateway and forwarded headers accordingly or set the application base path under one consistent design.

Activate profiles via environment variables:

```bash
SPRING_PROFILES_ACTIVE=local
```

In test or deployment pipelines, the platform can set `SPRING_PROFILES_ACTIVE=test` or `prod`. Do not bundle a fixed production hostname into source code if the same artifact deploys across multiple environments.

## 9. springdoc endpoints are also affected by base path

Common default URLs:

| Component | Default path |
|---|---|
| OpenAPI JSON | `/v3/api-docs` |
| OpenAPI YAML | `/v3/api-docs.yaml` |
| Swagger UI entry | `/swagger-ui.html` |
| Swagger UI assets | `/swagger-ui/**` |
| Swagger config | `/v3/api-docs/swagger-config` |
| OpenAPI group | `/v3/api-docs/{group}` |

If Spring MVC has context path `/order-app`, these URLs are accessed under that context path. If the proxy strips prefix `/order-service` and sends `X-Forwarded-Prefix`, public URLs may be `/order-service/v3/api-docs` or `/order-service/swagger-ui.html`, depending on how the proxy and application are configured.

Documentation paths can be customized:

```yaml
springdoc:
  api-docs:
    path: /openapi/spec
  swagger-ui:
    path: /docs
```

After changing them, update proxy routes, security matchers, health/availability checks, and shared user links. Do not change only the Swagger UI URL while forgetting the JSON/YAML endpoints the UI needs to load.

## 10. Comparing `servers` and `paths` in OpenAPI

OpenAPI separates the base URL in `servers` from individual operation paths. Example:

```yaml
servers:
  - url: https://test.example.com/order-service
paths:
  /api/orders:
    get:
      operationId: listOrders
```

Clients combine the two parts to call:

```text
https://test.example.com/order-service/api/orders
```

If `servers.url` already includes `/order-service`, do not repeat that prefix in path `/api/orders`. If `servers.url` is `https://test.example.com/order-service` and the path is also `/order-service/api/orders`, the final URL duplicates the prefix.

Similarly, avoid including `/api` in `servers.url` if every path already starts with `/api`, unless the API genuinely has two layers of that prefix.

## 11. Helping springdoc recognize the public URL behind a proxy

When the OpenAPI document is generated from the current request, springdoc can use request metadata to construct the server URL. If the application sees only the internal host, HTTP scheme, and upstream port, `servers` may reflect those internal values.

To make documentation reflect the public URL:

1. The reverse proxy must set accurate `Host` or `X-Forwarded-Host`.
2. The proxy must set `X-Forwarded-Proto` to the external scheme.
3. If needed, the proxy must set `X-Forwarded-Port` and `X-Forwarded-Prefix`.
4. Spring Boot must process forwarded headers with the right strategy.
5. No intermediate proxy overwrites or drops required headers.
6. Inspect `servers` in JSON/YAML generated from the actual public URL.

If the system has a fixed public base URL, you can declare the server URL explicitly via `@OpenAPIDefinition(servers = ...)` or an `OpenAPI` bean. However, fixed values must match the environment. If the same artifact runs in local, test, and production, use environment-specific config or forwarded request metadata rather than hard-coding one hostname.

Example configuring the server URL via a property:

```java
import java.util.List;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI openAPI(@Value("${app.public-api-url}") String publicApiUrl) {
        return new OpenAPI()
                .info(new Info()
                        .title("Order API")
                        .version("1.0.0"))
                .servers(List.of(new Server().url(publicApiUrl)));
    }
}
```

`app.public-api-url` can be set in each profile. When using this explicit declaration, ensure it does not conflict with springdoc request-derived server generation or other customizers.

## 12. Example server URL values per environment

`application-local.yml`:

```yaml
app:
  public-api-url: http://localhost:8080
```

`application-test.yml`:

```yaml
app:
  public-api-url: https://test.example.com/order-service
```

`application-prod.yml`:

```yaml
app:
  public-api-url: https://api.example.com
```

With controller mapping `/api/orders`, the OpenAPI document combines the server URL with the path to form the full endpoint. If production has a `/v1` prefix, put that prefix in either the server URL or the path under a single convention.

Never use test URLs in production. Never expose internal hostnames like `order-app:8080` in documentation meant for external clients if clients cannot resolve or reach that hostname.

## 13. Configuring Swagger UI URL and groups

Swagger UI needs to load OpenAPI config and the spec. When configuring static URLs, account for the public base path:

```yaml
springdoc:
  swagger-ui:
    path: /docs
    url: /v3/api-docs
```

A path starting with `/` is relative to the origin root. When the application is exposed under prefix `/order-service`, a root-relative URL `/v3/api-docs` may bypass the prefix and call the wrong endpoint at the root domain. Verify the actual URLs the browser requests after deployment.

With multiple groups, you can declare a list of URLs:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: orders
        url: /v3/api-docs/orders
      - name: billing
        url: /v3/api-docs/billing
    urls-primary-name: orders
```

If a public prefix is added/stripped by the proxy, group URLs must also be reachable from the browser via that prefix. Avoid hard-coding `http://localhost:8080` or internal hostnames in `url`, `configUrl`, or the group list sent to clients.

## 14. Avoiding missing or duplicated prefixes

Two common errors:

**Missing prefix:** the client opens `https://test.example.com/order-service/swagger-ui.html`, yet Swagger UI fetches the spec from `https://test.example.com/v3/api-docs`. The proxy routes only `/order-service/**`, so the spec request gets `404`.

**Duplicated prefix:** the proxy strips `/order-service` while the application also sets context path `/order-service`, or both `servers.url` and `paths` include the prefix. The result can become `/order-service/order-service/api/orders`.

To pinpoint the cause, check three values:

1. The URL the browser calls.
2. The request path the proxy sends upstream.
3. The request URI/context path Spring receives.

Then compare them against `servers` and `paths` in OpenAPI. Do not fix it by randomly adding prefixes in multiple places; designate a single owner for each path segment.

## 15. Testing endpoints across local, test, and production

Build a URL matrix before deploying:

| Component | Local | Test | Production |
|---|---|---|---|
| API | `http://localhost:8080/api/orders` | `https://test.example.com/order-service/api/orders` | `https://api.example.com/api/orders` |
| OpenAPI JSON | `http://localhost:8080/v3/api-docs` | `https://test.example.com/order-service/v3/api-docs` | `https://api.example.com/v3/api-docs` |
| Swagger UI | `http://localhost:8080/swagger-ui.html` | `https://test.example.com/order-service/swagger-ui.html` | `https://api.example.com/swagger-ui.html` |
| Public server URL | `http://localhost:8080` | `https://test.example.com/order-service` | `https://api.example.com` |

The URLs above assume the test proxy strips the prefix and production has no prefix. If your topology differs, adjust the matrix to match real configuration.

Check the API:

```bash
curl -i https://test.example.com/order-service/api/orders
```

Check OpenAPI:

```bash
curl -fS \
  https://test.example.com/order-service/v3/api-docs \
  -o openapi-test.json
```

Inspect `servers` and paths:

```bash
jq '.servers' openapi-test.json
jq '.paths | keys' openapi-test.json
```

Do not stop at confirming HTTP status 200. Verify that combining server URL and path yields a URL reachable from the client network.

## 16. Using browser Network tab to inspect Swagger UI

When Swagger UI opens yet displays no APIs, open browser Developer Tools and inspect the Network tab:

- Do requests to `/swagger-ui/swagger-ui.css` and JavaScript assets succeed?
- Does the request to `/v3/api-docs/swagger-config` have the right public prefix?
- Does the request to `/v3/api-docs` or a group URL miss the prefix?
- Is the response `200`, `301/302`, `401/403`, or `404`?
- Does a redirect `Location` header switch to an internal hostname or HTTP?
- Does the Console report mixed content when an HTTPS page calls an HTTP spec?

If assets return `404`, check proxy rewrites for `/swagger-ui/**`. If config returns `401/403`, check documentation security rules. If spec returns `404`, check paths and prefixes. If redirects emit wrong scheme/host URLs, check forwarded headers and trusted proxies.

## 17. Trusting forwarded headers and preventing spoofing

Forwarded headers can affect redirect URLs, links, and server URLs in OpenAPI. If the application accepts forwarded headers from any source, external clients can send forged headers like `X-Forwarded-Host` or `X-Forwarded-Proto` to manipulate generated URLs.

A secure design requires:

- Trusting forwarded headers only from proxies/load balancers inside a trusted network or allowlist.
- Configuring the proxy to strip client-sent forwarded headers before adding proxy-determined values.
- Not exposing the application directly to the Internet when assuming every request passes through a trusted proxy.
- Bounding the proxy chain and `X-Forwarded-For` interpretation to the real topology.
- Validating `Host` and avoiding generating links from arbitrary client-supplied hostnames.
- Testing both proxied requests and direct upstream requests in a controlled environment.

Do not enable forwarded-header processing solely to fix one Swagger UI URL without establishing a trusted header source. This configuration affects every request, not just springdoc.

## 18. Security matchers and CORS when a prefix is present

If protecting `/v3/api-docs` or `/swagger-ui/**` with Spring Security, determine the path Spring Security sees after proxy rewrite and after applying context path. Matchers must match the in-application path, not necessarily the full public URL.

For instance, the proxy strips `/order-service` and forwards `/v3/api-docs` to the app. The security matcher generally needs to match `/v3/api-docs/**`, not `/order-service/v3/api-docs/**`. If the proxy preserves the prefix and the app has a matching context path, the rule differs.

If browsers call the API from another origin, CORS must allow the corresponding origin, methods, and headers. CORS does not fix path rewrites, does not add prefixes to OpenAPI, and does not replace authorization. A valid CORS config can still return `404` if the spec URL is wrong.

## 19. Common errors

| Symptom | Possible cause | How to fix |
|---|---|---|
| Works locally yet test returns `404` | Proxy strips or keeps prefix differently than expected | Inspect request paths before/after rewrite and upstream mappings |
| Swagger UI loads page yet shows no APIs | Config URL/spec URL lacks public prefix | Inspect Network tab and `/v3/api-docs/swagger-config` URL |
| OpenAPI `servers` points to `http://service:8080` | App misses or ignores forwarded host/proto | Configure proxy headers and `server.forward-headers-strategy` |
| OpenAPI URL duplicates prefix | Prefix appears across proxy, context/base path, and `servers`/`paths` simultaneously | Designate a single owner for each prefix |
| Redirect from HTTPS to HTTP | External scheme not forwarded or unprocessed | Set `X-Forwarded-Proto: https` and configure forwarded headers |
| Works in test yet fails in production | Hostnames, path prefixes, or ingress rules differ | Maintain a URL matrix and test the artifact in every environment |
| `/v3/api-docs.yaml` returns 404 | Proxy routes only JSON endpoint or rewrite misses `.yaml` suffix | Add a YAML route and verify actual URLs |
| Group docs return 404 | `/v3/api-docs/{group}` not routed through proxy | Add group pattern and verify group names |
| Swagger UI assets return 404 | Proxy does not forward `/swagger-ui/**` | Add static assets route and check trailing slashes |
| Redirect produces unfamiliar host | Trusting untrusted forwarded host or proxy fails to overwrite header | Trust only authenticated proxies and overwrite incoming headers |
| Security matcher fails to match | Using public path when app receives upstream path | Write matchers for the path Spring actually receives |
| Browser reports mixed content | HTTPS UI calls HTTP OpenAPI URL | Fix server URL/config URL and forwarded scheme |

## 20. Pre-release comparison workflow

1. Record public base URLs for local, test, and production.
2. Specify clearly whether the proxy preserves or strips prefixes; determine upstream request paths.
3. Determine whether the app uses a Spring MVC context path, WebFlux base path, or no base path.
4. Check controller mappings and springdoc documentation endpoints.
5. Configure proxies to send appropriate `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, port, and prefix.
6. Configure `server.forward-headers-strategy` per container and proxy trust level.
7. Inspect `servers` and `paths` in OpenAPI JSON/YAML.
8. Inspect Swagger UI config, spec URL, group URLs, and static assets.
9. Verify security matchers and CORS against actual paths/origins.
10. Run curl and check browser Network from a client perspective in each environment.
11. Verify redirects, scheme, host, port, prefix, and trailing slashes.
12. Save the URL matrix as verification criteria after any gateway, ingress, or base-path change.

## 21. Design principles

- Separate public URLs, upstream URLs, context/base paths, servlet paths, and controller mappings clearly.
- Choose a single owner for each prefix; avoid adding the same prefix at both the proxy and application unintentionally.
- When a proxy strips a prefix, pass public metadata via forwarded headers if the app needs to build external URLs.
- Configure `server.forward-headers-strategy` according to the real container and proxy type.
- Trust forwarded headers only from controlled proxies; strip client-sent values before the proxy sets trusted ones.
- Keep `servers.url` and `paths` free of duplicated prefixes.
- Test JSON, YAML, Swagger UI, group endpoints, and static assets alike.
- Never hard-code localhost or internal hostnames into documentation intended for external clients.
- Use profiles or externalized config outside the artifact to supply environment-specific URLs.
- Test URLs from the client side, not solely by calling upstream directly.

## Conclusion

API paths across local, test, and production can differ due to host, scheme, port, proxy prefix, context path, WebFlux base path, and controller mappings. For springdoc-openapi to generate accurate documentation, determine whether the proxy preserves or strips prefixes, configure forwarded headers properly, and align `servers` with `paths`. Swagger UI, OpenAPI JSON/YAML, group endpoints, and static assets must all traverse the proxy under accurate paths. Maintain a per-environment URL matrix, verify requests from the client's perspective, and trust forwarded headers only when produced by controlled proxies.
