# `swagger-config` and resource URLs must all be reachable

Swagger UI operates through several separate HTTP requests. The browser loads the UI page, loads JavaScript/CSS, calls the `swagger-config` endpoint, and then uses the URL inside that configuration to fetch OpenAPI JSON/YAML. If the application runs behind a reverse proxy, API gateway, or under a context path, all of these URLs must point to the right public address and be properly forwarded by the proxy.

Therefore, being able to open `/swagger-ui.html` does not prove Swagger UI is fully working. The page may load yet display no APIs because `swagger-config` returns 404, the OpenAPI URL in config points to an internal host, or JavaScript resources are blocked by the proxy. You must inspect the entire request chain from the browser.

## 1. URLs involved in loading Swagger UI

With default Springdoc configuration, primary requests typically look like:

| Component | Default URL | Role |
|---|---|---|
| Swagger UI page | `/swagger-ui.html` | UI entry point; usually redirects to the actual UI page |
| UI resources | `/swagger-ui/**` | JavaScript, CSS, images, and Swagger UI assets |
| Swagger UI config | `/v3/api-docs/swagger-config` | Returns configuration used by Swagger UI to locate OpenAPI documents |
| Default OpenAPI | `/v3/api-docs` | Returns OpenAPI JSON |
| OpenAPI YAML | `/v3/api-docs.yaml` | Returns OpenAPI YAML |
| Group OpenAPI | `/v3/api-docs/{group}` | Returns the document of a `GroupedOpenApi` |
| OAuth redirect | `/swagger-ui/oauth2-redirect.html` | Callback page when Swagger UI performs an OAuth2 authorization flow |

These URLs can change when configuring `springdoc.api-docs.path`, `springdoc.swagger-ui.path`, `springdoc.swagger-ui.configUrl`, a context path, or a reverse proxy prefix. The table above shows paths relative to the application's context path, not necessarily the final public paths.

For example, if the application is published under prefix `/docs`, the browser may need to access:

```text
https://api.example.com/docs/swagger-ui.html
https://api.example.com/docs/swagger-ui/swagger-ui.css
https://api.example.com/docs/v3/api-docs/swagger-config
https://api.example.com/docs/v3/api-docs
https://api.example.com/docs/swagger-ui/oauth2-redirect.html
```

Not every Swagger UI version produces the exact same asset request list or redirect URL. Inspect the Network tab to see the actual URLs your application version loads.

## 2. `swagger-config` differs from the OpenAPI document

These are two endpoints with different responsibilities:

- `configUrl` points to Swagger UI's configuration document, usually `/v3/api-docs/swagger-config`.
- `url` or `urls` inside the Swagger UI config points to the OpenAPI document that the UI renders.

Example:

```text
GET /v3/api-docs/swagger-config
```

This endpoint returns a configuration JSON that may include fields such as `url`, `urls`, `oauth2RedirectUrl`, and UI options. Swagger UI then calls the OpenAPI URL specified in that configuration, for example:

```text
GET /v3/api-docs
```

Do not configure `springdoc.swagger-ui.configUrl` to point straight to `/v3/api-docs`. The two endpoints have different formats and purposes. If the UI receives an OpenAPI document where it expects a config object, it may report a config parse error or fail to render APIs.

Explicit configuration example when API Docs uses a custom path:

```yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /reference
    config-url: /openapi/swagger-config
```

In this case, check `/reference`, `/openapi/swagger-config`, and `/openapi`. Changing `api-docs.path` changes the base path of both the OpenAPI endpoint and swagger-config; changing `swagger-ui.path` changes only the UI entry point.

## 3. Key properties and their scope

Springdoc provides separate properties for UI URLs and document URLs:

| Property | Common default | Scope |
|---|---|---|
| `springdoc.swagger-ui.path` | `/swagger-ui.html` | UI entry point path |
| `springdoc.swagger-ui.configUrl` | `/v3/api-docs/swagger-config` | URL to fetch Swagger UI config |
| `springdoc.swagger-ui.url` | Unset | URL of a custom single OpenAPI file |
| `springdoc.swagger-ui.urls` | Unset | List of multiple OpenAPI documents, often for groups or external services |
| `springdoc.swagger-ui.urlsPrimaryName` | Unset | Name of the default selected document when `urls` is present |
| `springdoc.swagger-ui.oauth2RedirectUrl` | `/swagger-ui/oauth2-redirect.html` | OAuth2 callback URL |
| `springdoc.swagger-ui.use-root-path` | `false` | Allows accessing Swagger UI from the application root path |
| `springdoc.api-docs.path` | `/v3/api-docs` | Base path for OpenAPI and swagger-config endpoints |

Property names in YAML use kebab-case, e.g., `config-url`, `oauth2-redirect-url`, `use-root-path`, `api-docs.path`. Spring Boot relaxed binding maps them to the corresponding properties.

`springdoc.swagger-ui.url` is used when you want the UI to load a custom OpenAPI file. If `urls` is declared, the `urls` list takes precedence and the single `url` is ignored. Each item in `urls` needs a unique name and URL so Swagger UI's top bar can distinguish documents.

Example configuring two groups:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Public API
```

Group paths must match the registered group names exactly. If documents are served behind a proxy prefix, URLs in the list must also be reachable through the public prefix or be generated accurately via forwarded headers.

## 4. Distinguishing entry path, API Docs path, and context path

These three path layers are often confused:

1. **Context path or base path** is the shared prefix the Spring Boot application uses for requests.
2. **Swagger UI path** is the path for opening the UI.
3. **API Docs path** is the path for retrieving OpenAPI JSON/YAML and swagger-config.

Example with Spring MVC:

```yaml
server:
  servlet:
    context-path: /orders

springdoc:
  swagger-ui:
    path: /reference
  api-docs:
    path: /openapi
```

Internal application paths now include:

```text
/orders/reference
/orders/openapi/swagger-config
/orders/openapi
/orders/openapi.yaml
```

Context path `/orders` applies across the whole app. `swagger-ui.path` and `api-docs.path` are separate paths nested inside that context path.

With Spring WebFlux, the application can use `spring.webflux.base-path` instead of `server.servlet.context-path`. Distinguish the running stack's base path setting from prefixes added or stripped by a reverse proxy.

Changing `springdoc.swagger-ui.path` does not change `springdoc.api-docs.path`. Changing `springdoc.api-docs.path` also does not change the public path exposed by the proxy. Each layer must be configured and verified independently.

## 5. Two common reverse proxy patterns

When exposing an application under a prefix, two deployment patterns are common. Pick one model and keep the proxy and application consistent.

### Pattern A: Proxy preserves the prefix when forwarding

For example, the client calls:

```text
https://api.example.com/orders/swagger-ui.html
```

The proxy forwards path `/orders/swagger-ui.html` to the backend. The application must be configured to accept that path, such as via context path `/orders` or a matching base path. Do not add the same prefix again via `X-Forwarded-Prefix` if the application already sees and handles the prefix in the request path.

### Pattern B: Proxy strips the prefix before forwarding

The client still calls:

```text
https://api.example.com/orders/swagger-ui.html
```

However, the proxy strips `/orders` before sending to the application, so the backend receives `/swagger-ui.html`. In this case, the proxy must pass the public prefix via `X-Forwarded-Prefix: /orders`, alongside the external host and scheme.

The application must process forwarded headers so Springdoc generates correct public links. If the proxy strips the prefix without sending `X-Forwarded-Prefix`, the application may generate `/v3/api-docs/swagger-config` missing `/orders`; the browser will call the wrong path.

Do not let the proxy keep the prefix in the request path while also sending a forwarded prefix of the same value if the backend applies both. The result can be duplicated prefixes like `/orders/orders/...`.

## 6. Nginx configuration when the proxy strips the prefix

Example where Nginx exposes Spring Boot under `/docs/` and strips this prefix before forwarding requests to the backend:

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location /docs/ {
        # Trailing / makes Nginx replace /docs/ with / in proxy_pass.
        proxy_pass http://spring-app:8080/;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Prefix /docs;
    }
}
```

Public request `/docs/swagger-ui.html` is forwarded to the backend at path `/swagger-ui.html`; request `/docs/v3/api-docs/swagger-config` is forwarded to `/v3/api-docs/swagger-config`. `X-Forwarded-Prefix` informs the backend of the public prefix stripped by the proxy.

With Spring Boot 3.x, forwarded-header handling can be enabled at the Spring Framework layer:

```yaml
server:
  forward-headers-strategy: framework
```

In the Servlet stack, this uses `ForwardedHeaderFilter`; in the reactive stack, Spring Framework uses `ForwardedHeaderTransformer`. Exact configuration depends on the Spring Boot version and web server type.

If the proxy only passes headers like `X-Forwarded-For` and `X-Forwarded-Proto`, the web server's native strategy may suffice. When prefix handling or forwarded headers unsupported by the web server are needed, check the `framework` option in documentation matching your Spring Boot version.

### Trusting forwarded headers

Accept forwarded headers only from trusted reverse proxies. The edge proxy should strip or overwrite client-sent `Forwarded` and `X-Forwarded-*` headers, then regenerate values from the actual request. If the backend directly receives forged forwarded headers, the application can emit links with untrusted hosts, schemes, or prefixes.

## 7. Springdoc configuration example when the application sits under `/docs`

When the proxy strips `/docs` and sends `X-Forwarded-Prefix`, the application can keep default internal paths:

```yaml
server:
  forward-headers-strategy: framework

springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
    config-url: /v3/api-docs/swagger-config
```

You do not need to hardcode `/docs` into every property if forwarded headers are handled properly. Inspect the swagger-config response to confirm generated URLs carry the public prefix.

If forwarded headers cannot be configured at the backend, configure appropriate public URLs and ensure the proxy forwards those exact routes. However, that approach risks drift across environments and easily misses group URLs or OAuth callbacks. Proper forwarded-header handling is generally easier to maintain.

## 8. `ServerBaseUrlCustomizer` does not replace Swagger UI URL configuration

Springdoc provides `ServerBaseUrlCustomizer` to adjust the server base URL placed inside the OpenAPI document. This is useful when generated `servers` have a host, port, or scheme that does not match the public API address.

Conceptual example:

```java
import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiServerConfiguration {

    @Bean
    ServerBaseUrlCustomizer publicServerBaseUrlCustomizer() {
        return serverBaseUrl -> serverBaseUrl
            .replace("http://spring-app:8080", "https://api.example.com");
    }
}
```

This is an illustrative example only; avoid fixed string replacements if the application serves multiple hosts or environments. Prefer forwarded headers passed by a trusted proxy.

`ServerBaseUrlCustomizer` affects `servers` in the OpenAPI document—the URL Try it out uses to invoke business APIs. It does not fix paths for Swagger UI to load HTML, assets, `swagger-config`, or the OpenAPI document. If Swagger UI cannot load config, this customizer will not resolve the root cause.

## 9. Configuring multiple OpenAPI documents or static files

### Multiple internal groups

If the application has multiple `GroupedOpenApi` beans, Swagger UI can display a list of documents:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public
        url: /v3/api-docs/public
      - name: Admin
        url: /v3/api-docs/admin
    urls-primary-name: Public
```

The proxy must allow access to every listed URL. Exposing `/v3/api-docs` while blocking `/v3/api-docs/admin` still prevents the Admin group from loading.

### Static OpenAPI files

If you want Swagger UI to load a file placed in `src/main/resources/static`, e.g., `openapi.yaml`, configure:

```yaml
springdoc:
  swagger-ui:
    url: /openapi.yaml
    disable-swagger-default-url: true
```

In this case, browsers must be able to reach `/openapi.yaml` via the same origin or an origin with proper CORS. If `urls` is used, the single `url` setting is ignored.

### Documents from other services

Swagger UI can load OpenAPI documents from other services using `urls`. The browser makes those requests, so the source service must allow CORS from Swagger UI's origin. A URL reachable from the Spring Boot server is not necessarily reachable from a user's browser.

## 10. OAuth2 redirect must also pass through the proxy

When Swagger UI uses the OAuth2 Authorization Code Flow, the browser returns to the callback URL configured by `springdoc.swagger-ui.oauth2RedirectUrl`. The default URL is usually `/swagger-ui/oauth2-redirect.html` relative to the application's context path.

If the UI opens at `https://api.example.com/docs/swagger-ui.html`, the callback must also be exposed under the `/docs` prefix and the proxy must forward to the corresponding callback resource. If the authorization server has a redirect URI registered without the prefix while the browser returns to a URL with the prefix, login will fail with a redirect URI mismatch.

Keep three places aligned:

1. `springdoc.swagger-ui.oauth2RedirectUrl` in Springdoc.
2. The callback URL Swagger UI actually sends in the authorization request.
3. The redirect URI registered on the authorization server.

If using a custom redirect URL, ensure it is publicly reachable and included in the OAuth2 client's valid redirect URI list. Never use an internal URL like `http://spring-app:8080/...` in browser-side OAuth client configuration.

## 11. Security and CORS across the URL chain

Swagger UI needs to load UI assets, swagger-config, and the OpenAPI document. If Spring Security protects any of these endpoints, the browser may receive 401, 403, or a redirect to the login page instead of the expected JSON.

Common symptoms:

- The UI page loads yet the operation list is empty because `/v3/api-docs/swagger-config` returns 401.
- `swagger-config` returns 200 yet the OpenAPI URL returns 302 to a login page, causing a JSON parse error in the UI.
- The JSON document is reachable via cURL yet blocked by the browser due to CORS when UI and document have different origins.
- UI resources return 403 because security rules permit `/swagger-ui.html` without permitting `/swagger-ui/**`.

If UI and OpenAPI share the same origin, CORS is usually unnecessary for that request. If they are on different origins, the server serving OpenAPI must allow Swagger UI's origin, required methods, and headers. CORS does not replace authentication; documentation endpoints still require their own access policies.

When securing documentation, check all of:

- Entry point `/swagger-ui.html` or custom path.
- Static resources `/swagger-ui/**`.
- Swagger config endpoint `/v3/api-docs/swagger-config` or custom path.
- OpenAPI JSON/YAML and groups `/v3/api-docs/**`.
- OAuth2 redirect resource if OAuth is used.

Matchers must match actual paths after the context path and proxy configuration. Permitting only the entry point while forgetting assets or the config endpoint leaves the UI partially broken.

## 12. Inspecting the swagger-config response

After deployment, call the public swagger-config URL:

```bash
curl -i https://api.example.com/docs/v3/api-docs/swagger-config
```

The response must be Swagger UI configuration JSON. You should not receive login page HTML, reverse proxy error pages, or a welcome page.

If `jq` is available, inspect the URLs published by the config:

```bash
curl -fsS https://api.example.com/docs/v3/api-docs/swagger-config \
  | jq '{url, urls, oauth2RedirectUrl}'
```

Verify:

- Does `url` point to the public OpenAPI document?
- Is each `urls[].url` reachable from the browser?
- Does `oauth2RedirectUrl` contain the right context path/proxy prefix?
- Do any URLs point to `localhost`, container hostnames, private IPs, or internal ports?
- Do any URLs duplicate prefixes like `/docs/docs/...`?

Next, call each OpenAPI document:

```bash
curl -i https://api.example.com/docs/v3/api-docs
curl -i https://api.example.com/docs/v3/api-docs.yaml
curl -i https://api.example.com/docs/v3/api-docs/admin
```

If the API Docs path has been customized, adjust test URLs accordingly. The goal is to verify every document listed in swagger-config, not just the default document.

## 13. Checking UI resources in the browser

Open Developer Tools → Network, reload Swagger UI, and verify in order:

1. Request to the entry point returns a valid redirect or 200 HTML page.
2. JavaScript/CSS under `/swagger-ui/**` return 200 with accurate content types.
3. Request to `swagger-config` returns 200 JSON.
4. Request to OpenAPI JSON/YAML returns a valid document.
5. If using OAuth2, the callback resource is reachable via the public URL.

Filter the Network tab by `swagger`, `api-docs`, `openapi`, or `oauth2-redirect`. A 200 response can still be wrong if the body is a login HTML page instead of JavaScript, CSS, or JSON. Always check status, content type, and response body.

To locate where a bad URL originates, inspect the swagger-config response first. If the config already contains internal URLs or lacks a prefix, check forwarded headers and server request metadata. If config is right yet requests return 404, check proxy routing. If requests return 401/403, check security matchers. If the browser reports CORS, check origins and CORS response headers.

## 14. Common errors

| Symptom | Possible cause | How to fix |
|---|---|---|
| `/swagger-ui.html` opens yet says failed to load definition | `configUrl` or OpenAPI URL is wrong/unreachable | Check `/v3/api-docs/swagger-config`, then call the document URL in config |
| `swagger-config` returns 404 | Proxy does not forward API Docs path or `api-docs.path` changed | Update proxy routes and `springdoc.swagger-ui.configUrl` |
| `swagger-config` returns OpenAPI JSON | `configUrl` set to `/v3/api-docs` | Switch back to the corresponding swagger-config endpoint |
| Config contains internal hostname | App misses forwarded host/proto or document cached from internal request | Configure forwarded headers, check proxy and caching |
| URL misses public prefix | Proxy strips prefix without sending `X-Forwarded-Prefix` or backend ignores it | Send the header and enable matching forwarded-header strategy |
| URL duplicates prefix | Proxy preserves prefix while forwarded prefix is also applied | Choose either preserve-prefix or strip-prefix model |
| JavaScript/CSS return 404 | Proxy routes only the entry path, not `/swagger-ui/**` | Expose the UI resource route through the proxy |
| OpenAPI JSON returns HTML | Security redirect, custom error page, or bad proxy rewrite | Check status, content type, login redirects, and routes |
| Group in top bar fails to load | Wrong `urls[].url` or proxy blocks group endpoint | Test each group URL from the browser |
| Try it out calls wrong host | `servers` in OpenAPI derived from internal request | Fix forwarded headers or `ServerBaseUrlCustomizer` |
| OAuth2 login returns 404 | Redirect URL misses prefix or proxy does not serve callback | Align `oauth2RedirectUrl`, proxy route, and registered redirect URI |
| cURL works yet browser cannot load external spec | CORS blocks cross-origin requests | Configure CORS on the document-serving server |
| UI works directly yet fails via gateway | Gateway rewrites path, forwarded headers, or security policy differently | Inspect public URLs and Network tab through the gateway |

## 15. Checklist for deploying Swagger UI behind a reverse proxy

- [ ] Public URL of the Swagger UI entry point identified.
- [ ] Proxy forwards `/swagger-ui/**` and required assets completely.
- [ ] `springdoc.swagger-ui.configUrl` points to the swagger-config endpoint, not the OpenAPI document.
- [ ] Proxy forwards the swagger-config endpoint and returns properly formatted JSON.
- [ ] Every `url` or `urls[].url` in swagger-config is reachable from the browser.
- [ ] OpenAPI JSON, YAML, and all group documents have proper routes.
- [ ] Context path, API Docs path, and UI path are clearly distinguished.
- [ ] Chosen either preserve-prefix or strip-prefix proxy model without double application.
- [ ] If proxy strips prefix, `X-Forwarded-Prefix` is sent and processed by the application.
- [ ] Proxy overwrites client forwarded headers and only trusted backends accept them.
- [ ] Public scheme, host, and port match external HTTPS requests.
- [ ] `servers` in OpenAPI points to the right public API so Try it out works.
- [ ] OAuth2 redirect URL matches the public URL and registered redirect URI on the authorization server.
- [ ] Spring Security permits or authenticates entry, assets, config, documents, and callbacks per policy.
- [ ] CORS is configured if UI and OpenAPI document have different origins.
- [ ] Status, content type, and body of every request checked via cURL and browser Network tab.

Swagger UI is a chain of HTTP resources: the UI page loads assets, calls `swagger-config`, and fetches the OpenAPI document from the configured URL. The reverse proxy and Spring Boot must coordinate to produce accurate scheme, host, port, context path, and public prefix. Distinguish `configUrl` from `url`/`urls`, forward static resources and API Docs endpoints completely, handle forwarded headers per your proxy model, and verify every request from the browser. Only when all URLs are reachable and return expected content types can Swagger UI display documentation and execute Try it out reliably.

## References

- [Springdoc OpenAPI – FAQ: Deploy behind a reverse proxy](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – Configuration Properties](https://springdoc.org/properties.html)
- [Spring Boot 3.5 – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server)
- [Spring Framework – Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
