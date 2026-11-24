# Mixed content errors, wrong base URLs, and redirect loops

When deploying Spring Boot and springdoc-openapi behind a reverse proxy, Swagger UI may load yet fail to fetch the OpenAPI document, or the documentation page may show endpoints with wrong URLs. Three common error categories are mixed content, incorrect base URLs/path prefixes, and redirect loops.

These errors typically arise when the proxy terminates TLS externally, changes the host, or adds/strips a path prefix before forwarding requests to the application. Spring Boot sees an internal request different from the public URL used by the browser. If forwarded headers or OpenAPI configuration are inconsistent, springdoc and Swagger UI can produce wrong links.

## 1. Distinguishing URLs in the Swagger UI flow

An application typically involves at least three distinct URLs:

| URL | Role | Related configuration |
|---|---|---|
| Public Swagger UI URL | Address users open in the browser | `springdoc.swagger-ui.path`, context path, and reverse proxy |
| OpenAPI document URL | Address where Swagger UI fetches JSON/YAML | `springdoc.api-docs.path`, `springdoc.swagger-ui.url` |
| API server URL | Base URL used to build requests when clicking Try it out | `servers` in OpenAPI |

Deployment example:

- Swagger UI: `https://docs.example.com/catalog/swagger-ui/index.html`
- OpenAPI JSON: `https://docs.example.com/catalog/v3/api-docs`
- API: `https://api.example.com/catalog/api/orders`

These three URLs may share a host or use different hosts. Do not use `springdoc.swagger-ui.url` to fix the base URL of operations; that property specifies the document the UI should load. The API's base URL is described in the `servers` field of OpenAPI.

If Swagger UI opens properly yet Try it out sends requests to the wrong host, inspect `servers`. If the UI fails to load the specification, check the document URL. If the browser redirects repeatedly before the page renders, inspect forwarded headers and redirects at the proxy/app.

## 2. What is mixed content?

Mixed content occurs when a page loaded over HTTPS requires the browser to fetch resources or call endpoints over unencrypted HTTP. Active requests such as `fetch`, XHR, and API calls are typically blocked by browsers when an HTTPS page calls an HTTP URL.

Example:

- Swagger UI: `https://docs.example.com/swagger-ui/index.html`
- OpenAPI document: `http://api.example.com/v3/api-docs`
- API server in OpenAPI: `http://api.example.com`

The Swagger UI page is protected by HTTPS, while the document or API uses HTTP. Consequences may include:
- Swagger UI fails to load the OpenAPI document.
- Try it out reports a mixed content error and does not send the request.
- An OAuth2 authorize/token endpoint using HTTP is blocked by the browser.
- An HTTPS request is redirected to an HTTP URL and then blocked on the next step.

Inspect every URL the browser uses, not just the Swagger UI page URL. This includes OpenAPI JSON/YAML, API servers, OAuth2 authorization/token endpoints, and any callback URLs.

## 3. How to spot mixed content

Open your browser's Developer Tools:

1. Select the **Console** tab and look for `Mixed Content` messages.
2. Select the **Network** tab and filter by Fetch/XHR.
3. Check which requests use `http://` while the main page uses `https://`.
4. Check whether the blocked request is the OpenAPI document, an API operation, or an OAuth2 endpoint.
5. Inspect the response or redirect chain of the relevant URL if the browser permits.

A mixed content error often triggers before the request ever reaches the backend. Therefore, Spring Boot logs may not record the request the browser blocked.

Do not rely solely on `curl` to conclude mixed content is fixed. `curl` does not enforce browser mixed content policies. Re-verify using the browser Console and Network tabs after fixing URLs.

## 4. Fixing mixed content with public HTTPS URLs

If Swagger UI and the API share the same host, prefer relative URLs or consistent public HTTPS URLs. If the API is on a separate host, declare an HTTPS server explicitly.

OpenAPI server example:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com/catalog",
            description = "Public API"
        )
    }
)
class OpenApiConfiguration {
}
~~~

In the example, the operation path might be `/api/orders`, so the final URL called is:

~~~text
https://api.example.com/catalog/api/orders
~~~

If the document and API share the same origin, you can use a relative server URL:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;

@OpenAPIDefinition(
    servers = @Server(
        url = "/catalog",
        description = "API through public gateway"
    )
)
class OpenApiConfiguration {
}
~~~

This is an alternative to the absolute server URL example above; pick one suitable configuration rather than declaring two classes with the same name. A relative URL is resolved by the browser against the document's current origin. Use this approach only when the API's public path actually sits under the `/catalog` prefix. If the API has a separate host, declare the full HTTPS URL.

If configuring the OpenAPI document URL via `springdoc.swagger-ui.url`, ensure that URL also uses HTTPS or is a valid relative URL:

~~~yaml
springdoc:
  swagger-ui:
    url: https://api.example.com/catalog/v3/api-docs
~~~

Do not configure an HTTP URL and rely on the browser to upgrade it automatically. Some browser or proxy policies may alter handling, but configuring it accurately from the start remains the reliable approach.

## 5. Why does Spring Boot generate the wrong scheme or host after TLS termination?

In a common architecture, TLS terminates at a reverse proxy or load balancer:

~~~text
Browser -- HTTPS --> Reverse proxy -- HTTP --> Spring Boot
~~~

The browser sends HTTPS to the proxy. The proxy decrypts TLS and forwards the request internally over HTTP. If the proxy does not pass public scheme/host details, Spring Boot sees only the internal HTTP connection and may produce URLs such as:

`http://internal-app:8080/v3/api-docs`

or generate redirects to HTTP.

For the application to know the original URL, the proxy must send forwarded headers. Common headers:

| Header | Meaning |
|---|---|
| `Forwarded` | Standard RFC 7239 header describing proxy metadata such as `proto` and `host` |
| `X-Forwarded-Proto` | External scheme, e.g. `https` |
| `X-Forwarded-Host` | Public host accessed by the client |
| `X-Forwarded-Port` | Public port |
| `X-Forwarded-For` | Client IP address through the proxy chain |
| `X-Forwarded-Prefix` | Public prefix added by or used by the proxy when rewriting paths |

The proxy must set these values based on the received request. At the edge proxy, strip or overwrite forwarded headers sent by external clients and set trusted values anew. Also restrict direct connections to the backend so clients cannot bypass the proxy and supply spoofed headers themselves.

## 6. Configuring forwarded headers in Spring Boot

Spring Boot provides the `server.forward-headers-strategy` property to decide how the application handles forwarded headers.

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Common options:

| Value | How it handles | When to use |
|---|---|---|
| `none` | Does not process forwarded headers | Application is not behind a proxy or should not use proxy metadata |
| `native` | Uses the web server/container's mechanism | When the container supports it and native configuration fits |
| `framework` | Uses Spring Framework forwarded-header support | When processing `Forwarded`/`X-Forwarded-*` is needed, especially with prefixes |

With `framework`, Spring uses `ForwardedHeaderFilter` in the Servlet stack or `ForwardedHeaderTransformer` in WebFlux to adjust scheme, host, port, and request info based on forwarded headers. This lets URL- or redirect-generating components see public metadata rather than internal connection details.

With Tomcat, `native` can use `RemoteIpValve` for forwarded headers supported by the container. Prefix handling capabilities and details depend on the container/version. If your architecture requires `X-Forwarded-Prefix`, verify that the chosen strategy actually handles prefixes; `framework` is typically appropriate when forwarded-header support is needed at the Spring layer.

Do not enable forwarded-header processing if the backend is directly reachable from untrusted networks and the proxy fails to strip forged headers. Forwarded headers affect request metadata the application trusts as public.

## 7. Configuring the reverse proxy to pass accurate public details

Example where Nginx terminates HTTPS, receives public path `/catalog/`, and strips the `/catalog/` prefix before forwarding requests to Spring Boot at root:

~~~nginx
server {
    listen 443 ssl;
    server_name docs.example.com;

    location /catalog/ {
        proxy_pass http://127.0.0.1:8080/;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Prefix /catalog;
    }
}
~~~

In this configuration, the trailing `/` on `proxy_pass` causes Nginx to replace the URI part matching the location with `/` when forwarding. Thus request:

~~~text
/catalog/v3/api-docs
~~~

is forwarded to the backend as:

~~~text
/v3/api-docs
~~~

`X-Forwarded-Prefix: /catalog` informs Spring that the public URL has the `/catalog` prefix. Combined with `server.forward-headers-strategy: framework`, the application can generate links reflecting the public URL.

If the proxy keeps the prefix intact and sends `/catalog/...` to the backend, the backend configuration must be designed to handle that prefix. Do not both keep the prefix in the backend path and add `X-Forwarded-Prefix` in a way that duplicates the path.

Choose one clear rewrite strategy:
- Proxy strips prefix: backend handles the internal path, forwarded prefix describes the public prefix.
- Proxy preserves prefix: backend must recognize the prefix per application config; avoid re-adding the same prefix a second time.

## 8. Distinguishing context path, proxy prefix, and springdoc path

The following properties solve different problems:

| Property | Role | Example |
|---|---|---|
| `server.servlet.context-path` | Context path of a Spring MVC/Servlet application | `/app` |
| `spring.webflux.base-path` | Base path of a WebFlux application | `/app` |
| `springdoc.api-docs.path` | Endpoint path serving the OpenAPI document | `/v3/api-docs` |
| `springdoc.swagger-ui.path` | Path for opening Swagger UI | `/swagger-ui.html` |
| `springdoc.swagger-ui.url` | Document URL loaded by Swagger UI | `/app/v3/api-docs` or HTTPS URL |
| OpenAPI `servers` | Base URL used to invoke API operations | `/catalog` or `https://api.example.com/catalog` |

Do not use `springdoc.api-docs.path` to change the base path of business APIs. For example, changing the docs endpoint to `/openapi` does not mean `/api/orders` also moves to `/openapi/orders`.

Likewise, `springdoc.swagger-ui.path` changes only the entry path to the UI. It does not change the API's public base URL.

Example configuration:

~~~yaml
server:
  servlet:
    context-path: /app
  forward-headers-strategy: framework

springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
~~~

With context path `/app`, the internal endpoint can be `/app/v3/api-docs`. If the proxy also adds public prefix `/catalog`, the external URL may be `/catalog/app/v3/api-docs`, depending on how the proxy rewrites paths. Define every path layer clearly before configuring document URLs.

## 9. Wrong base URL in OpenAPI servers

When clicking Try it out, Swagger UI combines the URL in `servers` with the operation's path.

Example:

~~~yaml
servers:
  - url: https://api.example.com/catalog
paths:
  /api/orders:
    get:
      responses:
        "200":
          description: OK
~~~

Resulting Request URL:

~~~text
https://api.example.com/catalog/api/orders
~~~

If `servers.url` already contains `/catalog/api` while the operation path also starts with `/api`, the final URL can become:

~~~text
https://api.example.com/catalog/api/api/orders
~~~

This is a duplicate prefix error. Decide whether the prefix belongs in `servers` or in the operation path and declare it only once.

If `servers` is generated as `http://localhost:8080`, check:
1. Does the proxy send `X-Forwarded-Proto` and `X-Forwarded-Host`?
2. Does Spring Boot process forwarded headers?
3. Does the proxy send `X-Forwarded-Prefix` when rewriting paths?
4. Is an `@OpenAPIDefinition(servers = ...)` or OpenAPI bean overriding the server URL?
5. Is a profile configuration or customizer producing an internal URL?

A static `servers` configuration can be useful when the public API URL is fixed. With multiple environments, consider relative server URLs or profile/environment-based configuration to avoid mixing staging and production hosts.

## 10. Configuring multiple environments without hard-coding the wrong URL

Public URLs can be managed via environment-specific configuration. Example:

~~~yaml
# application-dev.yml
app:
  public-api-url: http://localhost:8080

# application-prod.yml
app:
  public-api-url: https://api.example.com/catalog
~~~

An OpenAPI configuration can use this property:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiServerConfig {

    @Bean
    OpenAPI publicServerOpenApi(
            @Value("${app.public-api-url}") String publicApiUrl) {
        return new OpenAPI()
            .addServersItem(new Server().url(publicApiUrl));
    }
}
~~~

This is an explicit way to declare the server URL. If the application already defines another `OpenAPI` bean, merge the configurations rather than creating competing beans. In environments where the UI and API share the same origin, a relative server URL can be simpler and reduce hostname coupling.

Do not let production configuration point to `localhost`, container hostnames, or internal HTTP. Those addresses may be valid inside the backend network yet remain unreachable from users' browsers.

## 11. How do redirect loops commonly happen?

A redirect loop is a repeating chain of redirects between the proxy and the application, or between two canonical URLs. A classic scenario:

1. Browser calls `https://docs.example.com/swagger-ui.html`.
2. Proxy terminates TLS and forwards the request internally over HTTP.
3. Spring Security or the application sees an HTTP request and redirects to HTTPS.
4. Browser already uses HTTPS, yet the proxy again forwards the request internally over HTTP.
5. The application keeps thinking the request is insecure and redirects again.

The chain repeats until the browser reports `ERR_TOO_MANY_REDIRECTS`.

Another pattern occurs when a prefix is added twice:
- Proxy rewrites `/catalog/swagger-ui.html` to `/swagger-ui.html`.
- Application redirects to `/catalog/swagger-ui/index.html`.
- Proxy or filter adds `/catalog` again, creating `/catalog/catalog/...`.
- The URL bounces between rewrites or redirects back and forth across two forms.

Redirects can also loop when the proxy enforces a canonical host while the application redirects to a different host, or when trailing slashes on paths are handled inconsistently.

## 12. Fixing redirect loops caused by HTTPS termination

If the proxy terminates TLS and the backend connects over HTTP, pass the public scheme:

~~~nginx
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Port $server_port;
~~~

Also configure Spring Boot to process forwarded headers:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Then verify:
- Whether the application sees scheme `https` after forwarded headers are processed.
- Whether Spring Security still enforces HTTPS even when the request is already recognized as HTTPS.
- Whether the proxy redirects HTTP to HTTPS at the intended public boundary.
- Whether the backend is redirecting based on internal scheme details.

There should be one primary place responsible for HTTP → HTTPS redirects, usually the edge proxy/load balancer. If the application also performs redirects, it must receive the right forwarded scheme so it does not re-redirect already-HTTPS requests.

Do not indiscriminately disable HTTPS enforcement to hide the bug. Fix the forwarded metadata and ensure the backend trusts headers only from trusted proxies.

## 13. Fixing redirect loops caused by path prefixes

First, record every URL in the redirect chain:
- The initial URL requested by the browser.
- Status `301`, `302`, `307`, or `308`.
- The `Location` header of each response.
- The path the proxy sends to the backend.
- The path the application generates in redirects.

If the proxy strips a prefix, configure the appropriate forwarded prefix. If the proxy preserves the prefix, do not add the prefix again at another layer. Cross-check `server.servlet.context-path` or `spring.webflux.base-path` against actual path rewrites.

With Swagger UI, also check the redirect from `/swagger-ui.html` to `/swagger-ui/**` resources. If `springdoc.swagger-ui.path` is customized, verify whether the final redirect URL includes the public prefix exactly once.

## 14. Symptom-based diagnostic workflow

| Symptom | Where to check first | Resolution direction |
|---|---|---|
| Swagger UI reports Mixed Content | Browser Console/Network | Replace HTTP URLs with HTTPS or accurate relative URLs |
| UI opens yet fails to load spec | OpenAPI JSON/YAML request | Check `springdoc.swagger-ui.url`, docs path, context path, and CORS if cross-origin |
| Try it out calls `localhost` or internal host | `servers` in OpenAPI | Fix forwarded headers or server URL |
| URL has prefix repeated twice | Request URL and proxy rewrite | Add the prefix at one layer only |
| Generated URL uses HTTP despite public HTTPS | `X-Forwarded-Proto`, `server.forward-headers-strategy` | Pass and process the forwarded scheme |
| Browser reports `ERR_TOO_MANY_REDIRECTS` | Redirect chain and `Location` | Find the two layers redirecting back and forth |
| Swagger UI redirects to wrong path | `springdoc.swagger-ui.path`, context path, and forwarded prefix | Align public path with backend path |
| OpenAPI JSON loads yet operation URLs are wrong | `servers` | Fix the API base URL, do not change docs path |

## 15. Useful verification commands

Check response headers of Swagger UI or the OpenAPI document:

~~~bash
curl -sS -D - -o /dev/null https://docs.example.com/catalog/v3/api-docs
~~~

Follow the redirect chain and limit redirect count:

~~~bash
curl -sS -D - -o /dev/null -L --max-redirs 10 \
  https://docs.example.com/catalog/swagger-ui.html
~~~

If the command terminates with a max-redirects error, inspect the printed `Location` headers to spot the loop.

Fetch the OpenAPI document and inspect `servers`:

~~~bash
curl -sS https://docs.example.com/catalog/v3/api-docs
~~~

Check:
- Whether the URL in the first element of the `servers` array is a public URL reachable by browsers.
- Whether the scheme is HTTPS when the UI runs over HTTPS.
- Whether the prefix appears exactly once.
- Whether operation paths duplicate the base path.

The commands above check server responses; mixed content must still be verified in a browser. If the API requires authentication, use safe test credentials and keep tokens out of logs or shared commands.

## 16. Proxy and Springdoc configuration checklist

- [ ] Swagger UI opens over HTTPS in public environments.
- [ ] OpenAPI document URL uses HTTPS or an accurate relative URL.
- [ ] Every API server URL in `servers` is reachable from the browser.
- [ ] OAuth2 authorization/token URLs do not use HTTP on HTTPS pages.
- [ ] Proxy passes appropriate `X-Forwarded-Proto`, `X-Forwarded-Host`, and port.
- [ ] `server.forward-headers-strategy` is chosen according to container and prefix needs.
- [ ] Proxy strips or overwrites client-sent forwarded headers.
- [ ] `X-Forwarded-Prefix` is used only when matching how the proxy rewrites paths.
- [ ] Context path, WebFlux base path, docs path, and UI path are clearly distinguished.
- [ ] Base path is not added twice between `servers` and operation paths.
- [ ] Only one layer holds primary responsibility for HTTP → HTTPS redirects.
- [ ] Redirect chain does not loop on host, scheme, or prefix.
- [ ] `/v3/api-docs` and `servers` verified after deployment.
- [ ] Console and Network verified in a real browser.

## References

- [Spring Boot – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/reference/howto/webserver.html#howto.webserver.use-behind-a-proxy-server): configuring forwarded headers when running behind a reverse proxy.
- [Spring Framework – ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers): how Spring processes forwarded headers and original request metadata.
- [springdoc-openapi – Properties](https://springdoc.org/properties.html): configuring API docs path, Swagger UI path, and document URLs.
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object): meaning and resolution of server URLs.
- [MDN – Mixed Content](https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content): how browsers handle HTTP resources on HTTPS pages.
- [MDN – HTTP Redirections](https://developer.mozilla.org/en-US/docs/Web/HTTP/Redirections): redirect statuses and Location header.
