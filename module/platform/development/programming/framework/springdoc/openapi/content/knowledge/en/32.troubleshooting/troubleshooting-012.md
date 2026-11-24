# Incorrect Server URL Behind a Proxy or When Using the Management Port

When opening Swagger UI, the HTML page may load successfully while **Try it out** calls the wrong host, scheme, port, or path. A common case is the OpenAPI document containing an internal URL such as `http://orders-service:8080`, while external clients must call `https://api.example.com/orders`. Another case occurs when Swagger UI and the OpenAPI endpoint are moved to the Actuator management port, causing `servers` in the document to unintentionally point to the management port instead of the business API port.

To diagnose this, separate three URLs:

1. **Swagger UI URL:** where the browser opens the UI page.
2. **OpenAPI document URL:** where Swagger UI loads JSON/YAML.
3. **URL in `servers`:** used by Swagger UI or client generators to invoke operations.

These three URLs can live on different hosts, ports, and paths. Fixing only the Swagger UI page URL does not guarantee API requests are sent correctly.

This lesson explains how to inspect generated URLs, handle forwarded headers behind a reverse proxy, configure server URLs, diagnose management port setups, enable CORS in the right places, and test the path from browser to API.

## 1. Distinguishing Three URLs in the Swagger UI Flow

Suppose a service has:

~~~text
Swagger UI:
https://docs.example.com/orders/swagger-ui.html

OpenAPI document:
https://docs.example.com/orders/v3/api-docs

API server:
https://api.example.com/orders
~~~

Swagger UI loads the document from the second URL. Then it reads `servers` inside the document to construct operation request URLs.

If the document contains:

~~~yaml
servers:
  - url: http://orders-service:8080
paths:
  /api/orders:
    get:
      responses:
        "200":
          description: Success
~~~

Try it out will call:

~~~text
http://orders-service:8080/api/orders
~~~

This is an internal hostname that external browsers cannot reach. The document URL may be right while `servers` is still wrong.

When investigating, check separately:

- Does the HTML page load?
- Does Swagger UI load `swagger-config` and OpenAPI JSON?
- What is the `servers` value in JSON?
- How is the final Try it out URL assembled?

## 2. Understanding How springdoc Generates `servers`

When the document does not explicitly declare `servers`, springdoc can infer the base URL from the request used to fetch the OpenAPI document. Host, port, scheme, and context path of that request can affect the generated URL.

This works well when the application is accessed directly. Behind a reverse proxy, the request Spring Boot sees may differ from the public request the browser sent.

For example:

~~~text
Public request:
https://api.example.com/orders/v3/api-docs

Upstream request:
http://orders-service:8080/v3/api-docs
~~~

If the application only sees the upstream request, the inferred server URL may use `http`, hostname `orders-service`, and port `8080`.

According to the springdoc FAQ, if server annotations are declared, those servers are used instead of the automatically inferred URL. This is a useful option when the public URL is stable and known.

## 3. Reading `servers` in OpenAPI JSON Before Editing Configuration

Start by downloading the document:

~~~bash
curl -fsS https://api.example.com/orders/v3/api-docs -o openapi.json
~~~

Inspect `servers`:

~~~bash
jq '.servers' openapi.json
~~~

Inspect paths:

~~~bash
jq '.paths | keys' openapi.json
~~~

Inspect version and metadata:

~~~bash
jq '{openapi, info, servers}' openapi.json
~~~

If `servers` contains an internal hostname, wrong scheme, or wrong port, focus on how server URLs are generated. If `servers` is right yet Try it out still calls the wrong URL, check operation paths, server overrides on Path Item/Operation, and Swagger UI configuration.

Do not infer the API URL from Swagger UI's browser address bar. The API invocation URL is determined by `servers` combined with operation paths.

## 4. Distinguishing Application Port and Management Port

Spring Boot can listen on two ports:

- `server.port`: port receiving business API requests.
- `management.server.port`: port dedicated to Actuator management endpoints.

For example:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /actuator
~~~

Business APIs remain on port `8080`. Actuator endpoints sit under port `9090` and base path `/actuator`.

Exposing Swagger UI on the management port does not mean business APIs also moved to port `9090`. `servers` in OpenAPI must point to the port or public route of the business API.

This is the most critical point when troubleshooting Try it out errors after enabling `use-management-port`.

## 5. Enabling springdoc on the Actuator Management Port

To expose OpenAPI and Swagger UI on the management port, configure:

~~~yaml
springdoc:
  use-management-port: true

management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include:
          - openapi
          - swagger-ui
~~~

With the default `/actuator` base path, endpoints are exposed under the management port:

~~~text
http://localhost:9090/actuator/openapi
http://localhost:9090/actuator/swagger-ui
~~~

The management port must differ from the application port to use this feature.

If `management.endpoints.web.base-path` is changed, the docs endpoints move under the new base path. For example, base path `/manage` makes the endpoints `/manage/openapi` and `/manage/swagger-ui`.

These are Actuator endpoints, not the default `/v3/api-docs` and `/swagger-ui.html` paths on the application port.

## 6. Which springdoc Path Properties No Longer Apply

When `springdoc.use-management-port=true`, regular springdoc path properties do not apply to endpoints exposed under the management base path.

For example, do not expect `springdoc.api-docs.path` or `springdoc.swagger-ui.path` to rename the Actuator `openapi` and `swagger-ui` endpoints.

Endpoint names under the Actuator base path are managed by springdoc. Use `management.endpoints.web.base-path` to change the Actuator base path, and verify the actual URLs after deployment.

If you want to keep using `/v3/api-docs` and `/swagger-ui.html` on the application port, do not enable `use-management-port`. Pick one exposure location based on operational goals.

## 7. Distinguishing `use-management-port` from `show-actuator`

These two properties solve different requirements:

| Property | Effect |
|---|---|
| `springdoc.use-management-port` | Exposes OpenAPI and UI under the Actuator management port |
| `springdoc.show-actuator` | Adds Actuator endpoints into OpenAPI documentation |

Enabling `show-actuator` does not automatically move Swagger UI to the management port. If only `show-actuator` is enabled, the UI may remain on the application port.

If the management port differs from the application port and you want the UI to invoke Actuator endpoints on the admin port, CORS for Actuator endpoints may also need configuration.

Do not enable both just to view Actuator. Decide clearly whether you need to move UI/document endpoints to the management port or merely document Actuator operations.

## 8. Why Does Try It Out Call the Wrong Management Port?

Suppose:

~~~text
Application API:
http://localhost:8080/api/orders

Management docs:
http://localhost:9090/actuator/openapi

Management Swagger UI:
http://localhost:9090/actuator/swagger-ui
~~~

The browser loads Swagger UI and the OpenAPI document from port `9090`. If `servers` is inferred from the document-fetching request, the generated URL may be `http://localhost:9090`.

Then Try it out calls:

~~~text
http://localhost:9090/api/orders
~~~

Yet the actual API runs on port `8080`. The request will return 404, 401, or find no route.

The fix is declaring `servers` pointing to the application API URL:

~~~yaml
servers:
  - url: http://localhost:8080
    description: Application API
~~~

In production, use the public URL or corresponding gateway route. Never use the management port as the server for business APIs unless APIs are actually served on that port.

## 9. Explicitly Declaring `servers` with `@OpenAPIDefinition`

If the API has a stable public base URL, declare:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com/orders",
            description = "Public Orders API"
        )
    }
)
class OpenApiConfiguration {
}
~~~

This prevents server URLs from being inferred from management-port document requests or upstream addresses.

If multiple environments exist, read the server URL from deployment configuration or use an `OpenAPI` bean/customizer. Do not hard-code a production URL into source code if the same artifact must run across multiple environments.

## 10. Declaring `servers` with an `OpenAPI` Bean

You can read the URL from `Environment`:

~~~yaml
api:
  public-base-url: https://api.example.com/orders
~~~

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

import java.util.List;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI openAPI(Environment environment) {
        String publicBaseUrl =
            environment.getRequiredProperty("api.public-base-url");

        return new OpenAPI()
            .servers(List.of(
                new Server()
                    .url(publicBaseUrl)
                    .description("Public API")
            ));
    }
}
~~~

An `OpenAPI` bean fits well when `servers` metadata is shared across the application's document. If multiple groups have different public prefixes, use a group-specific customizer or structure beans per document.

After configuring, download the JSON and verify `servers` actually holds the expected value. Do not only check that the bean was created.

## 11. Using `ServerBaseUrlCustomizer` to Adjust Auto-Inferred URLs

springdoc provides `ServerBaseUrlCustomizer` to adjust the base URL inferred from requests.

For example:

~~~java
import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class PublicBaseUrlConfiguration {

    @Bean
    ServerBaseUrlCustomizer serverBaseUrlCustomizer(
        Environment environment
    ) {
        String publicBaseUrl =
            environment.getRequiredProperty("api.public-base-url");

        return ignoredServerBaseUrl -> publicBaseUrl;
    }
}
~~~

This works well when one application has one stable public base URL. If URLs must vary by group or request, design custom logic and test each case.

`ServerBaseUrlCustomizer` adjusts the automatically inferred URL. If the document already declares explicit `servers` via annotations or the model, check how that configuration takes precedence before adding a customizer.

## 12. Checking `Forwarded` and `X-Forwarded` Headers

A reverse proxy can forward requests to Spring Boot with an internal host, port, and scheme. To let the framework recognize the public request, the proxy can send:

- `Forwarded` per RFC 7239.
- `X-Forwarded-Host`.
- `X-Forwarded-Port`.
- `X-Forwarded-Proto`.
- `X-Forwarded-Prefix`.
- `X-Forwarded-For`.

Example public request:

~~~text
https://api.example.com/orders/v3/api-docs
~~~

Proxy forwards to:

~~~text
http://orders-service:8080/v3/api-docs
~~~

Forwarded headers inform the application that the original request used HTTPS, host `api.example.com`, and prefix `/orders`.

If the application does not process these headers, automatic server URLs may reflect internal addresses.

## 13. Configuring `server.forward-headers-strategy`

Spring Boot provides the property:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Main options:

| Value | How it works |
|---|---|
| NONE | Applies no forwarded-header processing |
| NATIVE | Lets the web server handle them natively |
| FRAMEWORK | Uses Spring Framework's `ForwardedHeaderFilter` |

If the proxy sends common headers like `X-Forwarded-For` and `X-Forwarded-Proto`, `NATIVE` may suffice depending on the web server. If extra headers such as `X-Forwarded-Prefix` must be handled or native behavior falls short, `FRAMEWORK` is the option to consider.

Consult documentation for your embedded server and Spring Boot version. Do not assume every server handles all headers identically.

## 14. Handling `X-Forwarded-Prefix`

`X-Forwarded-Prefix` matters when a gateway exposes a public prefix yet strips that prefix before forwarding requests upstream.

For example:

~~~text
Public:
https://api.example.com/orders/v3/api-docs

Upstream:
http://orders-service:8080/v3/api-docs
~~~

The gateway can send:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
X-Forwarded-Prefix: /orders
~~~

When Spring processes this header, the framework can construct URLs including the public prefix.

If `X-Forwarded-Prefix` is missing, the document may contain a server URL without `/orders`. Try it out then calls a route that does not exist on the gateway.

If the gateway does not strip the prefix and forwards `/orders/...` intact, do not add the prefix a second time. Determine exact route rewriting to avoid duplicated URLs.

## 15. Reverse Proxies Must Overwrite Forwarded Headers

Never trust forwarded headers sent directly by a browser or client.

If a proxy preserves client-supplied `X-Forwarded-Host`, a user can make the application generate URLs with an arbitrary host. This can break links or leak unintended information.

At the proxy boundary:

1. Strip client-supplied forwarded headers.
2. Recreate `Forwarded` or `X-Forwarded-*` from the actual connection/request.
3. Allow upstream to accept traffic only from trusted proxies.
4. Ensure the public scheme is determined accurately.
5. Disallow direct client access to upstream when unnecessary.

Forwarded headers are trustworthy only when created and protected by a trusted proxy.

## 16. Distinguishing Context Path from Proxy Prefix

Two prefixes are commonly confused:

- `server.servlet.context-path`: the Spring Boot application's actual context path.
- `X-Forwarded-Prefix`: a public prefix added or represented by a proxy.

For instance, an app has context path `/app`, while the gateway publishes prefix `/orders`. The public URL may contain both depending on how the gateway rewrites:

~~~text
https://api.example.com/orders/app/v3/api-docs
~~~

If the gateway strips `/orders` while upstream still serves under `/app`, Spring must understand both the context path and the forwarded prefix properly.

Do not declare the same prefix in context path, proxy route, and OpenAPI `servers` without accounting for how they combine. If a prefix appears twice in the final URL, inspect each layer instead of randomly editing `servers`.

## 17. Disabling Cache When URLs Must Be Computed Per Request

springdoc computes the OpenAPI description and caches the result by default. This can cause issues if the same application is accessed through multiple proxies or hosts and the server URL must vary per request.

You can disable caching:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Or:

~~~properties
springdoc.cache.disabled=true
~~~

Disabling the cache forces the document to be recomputed per request, which fits cases where the URL genuinely depends on each request's host or forwarded headers.

If `servers` is explicitly declared and stable, you usually do not need to disable caching just to fix URLs. Disabling caching does not replace proper proxy configuration and can increase document generation overhead.

With caching enabled, remember that the computed document may be reused. Do not expect each request on a different host to auto-generate a different `servers` entry while caching holds the previous result.

## 18. CORS When Swagger UI and API Are on Different Ports

A browser origin consists of scheme, host, and port. Therefore:

~~~text
http://localhost:9090
http://localhost:8080
~~~

are two distinct origins.

When Swagger UI runs on management port `9090` while Try it out calls the application API on port `8080`, the browser needs CORS permitting the UI's origin to access the API.

Configure CORS on the application API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ApiCorsConfiguration {

    @Bean
    WebMvcConfigurer corsConfigurer() {
        return new WebMvcConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/api/**")
                    .allowedOrigins("https://docs.example.com")
                    .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
                    .allowedHeaders("Authorization", "Content-Type", "Accept")
                    .allowCredentials(true);
            }
        };
    }
}
~~~

If using Spring Security, enable and configure CORS in the security filter chain. Permit only necessary origins; never use wildcards when sending credentials.

Management endpoint CORS and application API CORS are two separate scopes. Swagger UI may load the document successfully yet still be blocked by the browser when calling the API.

If a portal on another origin needs to load the OpenAPI document from the Actuator management endpoint, you can configure CORS for Actuator:

~~~yaml
management:
  endpoints:
    web:
      cors:
        allowed-origins: https://docs.example.com
        allowed-methods: GET,OPTIONS
        allowed-headers: Authorization,Content-Type,Accept
~~~

When Swagger UI and the OpenAPI endpoint are both served from the management port on the same origin, the browser does not need CORS for those internal requests. CORS may still be needed when Try it out calls the application API on a different port.

## 19. Securing the Management Port

The management port often hosts health, metrics, environment, and operational endpoints. If `springdoc.use-management-port` is enabled, the OpenAPI document and Swagger UI also appear on this port.

Do not expose the entire management port to the Internet just to serve API documentation.

Check:

- Does `management.server.address` bind to an appropriate interface?
- Do firewalls or network policies permit only admin networks?
- Does Spring Security protect Actuator endpoints?
- Does `management.endpoints.web.exposure.include` list only needed endpoints?
- Should Swagger UI be public or restricted to internal developers?
- Does the OpenAPI document expose internal operations or sensitive details?

Actuator exposure merely makes an endpoint exposable; it does not replace authorization and network controls.

## 20. Complete Management Port Configuration

Example where the application API runs on `8080` and admin docs run on `9090`:

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework

management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include:
          - health
          - info
          - openapi
          - swagger-ui

springdoc:
  use-management-port: true

api:
  public-base-url: https://api.example.com/orders
~~~

OpenAPI and UI are exposed under the management base path:

~~~text
http://localhost:9090/actuator/openapi
http://localhost:9090/actuator/swagger-ui
~~~

`servers` in OpenAPI must use the application API public URL:

~~~yaml
servers:
  - url: https://api.example.com/orders
~~~

Do not leave `servers` using `http://localhost:9090` or `/actuator`. That is where docs are served, not where business operations live.

## 21. CORS When Management Port Differs from Application Port

If Swagger UI is served on the management port and the API on the application port, the browser calls the API across origins. Enable CORS for application endpoints.

If an external portal and the management port also have different origins, enable CORS for both document loading and API calls.

You can reduce complexity by putting a single public reverse proxy sharing the same origin for UI, docs, and API. The gateway can route `/docs` and `/actuator/openapi` to the management service, and `/orders/**` to the application service.

Either way, `servers` must point to the public API route, not the management route.

## 22. When to Use `show-actuator`

If the goal is including Actuator operations in API documentation, use:

~~~yaml
springdoc:
  show-actuator: true
~~~

This property adds a group for Actuator endpoints to OpenAPI. It does not mean Swagger UI moves to the management port.

If the management port differs from the application port and you want to call Actuator operations from the UI, check CORS for Actuator endpoints. If you want both UI and OpenAPI endpoints exposed under the management base path, use `use-management-port` alongside Actuator configuration.

## 23. Verifying URLs After Enabling the Management Port

Use `curl` to check the documentation endpoint:

~~~bash
curl -i http://localhost:9090/actuator/openapi
~~~

Check `servers`:

~~~bash
curl -fsS http://localhost:9090/actuator/openapi \
  | jq '.servers'
~~~

Check operation paths:

~~~bash
curl -fsS http://localhost:9090/actuator/openapi \
  | jq '.paths | keys'
~~~

If `servers` contains port `9090` or `/actuator`, configure the server URL for the application API.

Check Swagger UI:

~~~bash
curl -I http://localhost:9090/actuator/swagger-ui
~~~

If the documentation endpoint works yet the UI fails to load the API spec, inspect browser network requests and the URL configured in Swagger UI.

## 24. Verifying URLs Through a Reverse Proxy

Always test from the public URL users actually visit:

~~~bash
curl -fsS https://api.example.com/orders/v3/api-docs -o openapi.json
~~~

Then:

~~~bash
jq '.servers' openapi.json
~~~

If the document is exposed via a management route:

~~~bash
curl -fsS https://ops.example.com/orders/actuator/openapi -o openapi.json
~~~

Even when the document is loaded from `ops.example.com`, `servers` can still point to `https://api.example.com/orders`.

Do not use upstream hostnames in public tests. Direct container checks isolate only one layer; they do not prove the proxy produced the right URLs.

## 25. Using `OpenApiCustomizer` for Group-Specific Servers

If the application has multiple groups with distinct public prefixes:

~~~java
import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class GroupServerConfiguration {

    @Bean
    GroupedOpenApi ordersApi() {
        OpenApiCustomizer serverCustomizer = openApi ->
            openApi.setServers(List.of(
                new Server()
                    .url("https://api.example.com/orders")
                    .description("Orders public API")
            ));

        return GroupedOpenApi.builder()
            .group("orders")
            .pathsToMatch("/api/orders/**")
            .addOpenApiCustomizer(serverCustomizer)
            .build();
    }
}
~~~

A customizer attached to a group applies the server URL only to that document. If every group shares the same server, use an `OpenAPI` bean or `GlobalOpenApiCustomizer`.

Inspect each group endpoint after configuring. Do not assume a customizer for the default document automatically applies to every group.

## 26. Diagnosing by Symptom

| Symptom | Possible cause | Check first |
|---|---|---|
| `servers` uses container hostname | Proxy headers not processed | `X-Forwarded-Host` and `Forwarded` |
| `servers` uses HTTP instead of HTTPS | Public scheme not forwarded | `X-Forwarded-Proto` |
| `servers` misses gateway prefix | Proxy strips prefix without sending prefix header | `X-Forwarded-Prefix` |
| `servers` duplicates prefix twice | Context path and forwarded prefix both applied | Compare public path vs upstream path |
| Try it out calls management port | Document inferred `servers` from management request | Check `servers` and set app API URL |
| OpenAPI endpoint 404 on management port | Actuator endpoint not exposed | `management.endpoints.web.exposure.include` |
| Swagger UI 404 with `use-management-port` | Calling `/swagger-ui.html` by mistake | Use `/actuator/swagger-ui` |
| Changing `springdoc.swagger-ui.path` has no effect | Running in management port mode | Check `use-management-port` rules |
| UI loads spec yet API call hits CORS | UI and API on different origins | CORS on application API |
| URL varies by proxy yet document keeps old URL | Cache retains previous result | Check `springdoc.cache.disabled` |
| UI loads yet API returns 401 | API security policy | Authentication and token |
| URL is right yet path is wrong | Server URL and operation path combine wrongly | Inspect `servers` alongside `paths` |

## 27. Step-by-Step Investigation Procedure

When encountering an incorrect server URL, follow this order:

1. Record the URL the browser uses to open Swagger UI.
2. Identify the actual OpenAPI document URL.
3. Download the document and inspect `servers`.
4. Combine `servers` with operation paths to compute the final URL.
5. Identify which proxy the request traverses and whether the proxy strips prefixes.
6. Inspect `Forwarded` and `X-Forwarded-*` headers arriving upstream.
7. Check `server.forward-headers-strategy`.
8. Determine whether UI/document run on the management port.
9. If using the management port, verify `servers` points to the application API.
10. Check CORS and security.
11. Disable cache temporarily only if URLs must be computed per request.
12. Re-test through the public gateway URL.

Proceeding step by step isolates which layer produces the wrong URL. Do not simultaneously change proxy rules, server annotations, context path, and caching without evidence.

## 28. Verifying in Integration Tests

You can verify `servers` in the OpenAPI document with `WebTestClient`:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OpenApiServerUrlTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publishesPublicApiServerUrl() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.servers[0].url")
            .isEqualTo("https://api.example.com/orders");
    }
}
~~~

If using `use-management-port`, test the endpoint on the management context/port and assert `servers` still points to the application API. Test setup depends on the project's Actuator and management port settings.

Also test combined paths and operations to ensure prefixes are not duplicated. Customizer unit tests do not replace testing behind a real reverse proxy.

## 29. Post-Deployment Checks

After any change to ingress, gateway, context path, or management port:

- Load Swagger UI via the public route.
- Load `swagger-config` if the UI uses the config endpoint.
- Load OpenAPI JSON.
- Inspect `servers`.
- Verify scheme, host, port, and prefix.
- Try out a safe read-only operation.
- Confirm the browser reports no CORS errors.
- Confirm management endpoints are not unintentionally exposed publicly.

Automate these checks in deployment smoke tests. Proxy configuration can change independently of Spring Boot code and break documentation URLs even when the application itself did not change.

## 30. Common Mistakes

| Configuration mistake | Consequence |
|---|---|
| Not processing forwarded headers | URL contains internal host/port |
| Proxy omits `X-Forwarded-Prefix` | Public path prefix disappears |
| Proxy fails to overwrite forwarded headers | App may trust spoofed host/scheme from clients |
| Using management port as `servers` | Try it out calls the wrong port |
| Enabling `use-management-port` yet calling `/v3/api-docs` | Documentation endpoint returns 404 |
| Forgetting to expose `openapi` and `swagger-ui` in Actuator | Endpoints do not appear |
| Using springdoc path properties in management mode | Paths do not change as expected |
| Missing CORS between two ports | Browser blocks requests |
| Disabling cache without controlling URLs | Different requests may generate varying servers |
| Conflicting explicit server annotations and customizers | Final server becomes unpredictable |
| Exposing management port publicly | Operational endpoints leaked |
| Adding prefix in both proxy and `servers` | URL duplicates path segment |

## 31. Pre-Release Checklist

- [ ] Distinguished Swagger UI URL, OpenAPI document URL, and `servers`.
- [ ] Identified application port and management port.
- [ ] If using the management port, verified it differs from the application port.
- [ ] Exposed `openapi` and `swagger-ui` in Actuator.
- [ ] Used `/actuator/openapi` and `/actuator/swagger-ui` in management mode.
- [ ] Did not rely on springdoc path properties when `use-management-port=true`.
- [ ] `servers` points to the application API public URL.
- [ ] Forwarded headers are safely generated and overwritten by the proxy.
- [ ] `X-Forwarded-Proto` reflects the public scheme.
- [ ] `X-Forwarded-Host` reflects the public host.
- [ ] `X-Forwarded-Prefix` reflects the prefix after rewriting.
- [ ] `server.forward-headers-strategy` matches the embedded server.
- [ ] Context path and proxy prefix are not applied twice.
- [ ] CORS is configured for both docs and API when cross-origin.
- [ ] Management port is protected by network policy and security.
- [ ] `ServerBaseUrlCustomizer` alters URLs only when necessary.
- [ ] Caching is considered if URLs depend on requests.
- [ ] Verified `servers` with `curl` and `jq`.
- [ ] Tested Try it out via the public route.
- [ ] Ran smoke tests after deployment.

## 32. References

- [springdoc-openapi v2 – Actuator support](https://springdoc.org/v2/)
- [springdoc-openapi FAQ – Reverse proxy and forwarded headers](https://springdoc.org/faq.html)
- [springdoc-openapi FAQ – Server URL generation](https://springdoc.org/faq.html)
- [springdoc-openapi FAQ – Disable OpenAPI cache](https://springdoc.org/faq.html)
- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html)
- [Spring Boot – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Framework – ForwardedHeaderFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html)
- [Spring Boot Actuator – Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)

Incorrect server URLs usually stem from confusing the document-fetching URL with the API invocation URL. Behind a reverse proxy, handle `Forwarded` and `X-Forwarded-*` headers at the proper trust boundary—especially scheme, host, and prefix. When using a management port, OpenAPI/UI live under the Actuator base path while `servers` must still point to the application API. Verify JSON `servers`, CORS, security, and Try it out over the public route before concluding the incident is resolved.
