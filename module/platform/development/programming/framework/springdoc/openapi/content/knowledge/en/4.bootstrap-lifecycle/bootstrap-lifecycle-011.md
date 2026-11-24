# Distinguishing Application API Paths from Documentation Paths

In a Spring Boot application with springdoc-openapi, business API URLs, OpenAPI document URLs, and Swagger UI URLs usually share the same host while serving different purposes. Confusing these path types can cause the application to return 404 when clients fetch documentation, Swagger UI to miss the JSON/YAML, or the OpenAPI document to emit wrong server URLs after deployment behind a reverse proxy.

Distinguish three layers:

1. **Application API paths** are controller mappings, such as `/api/orders/{id}`. Clients call these paths to execute business operations.
2. **OpenAPI documentation paths** are endpoints exposed by springdoc, defaulting to `/v3/api-docs` and `/v3/api-docs.yaml`. Clients, API catalogs, or SDK generators call these endpoints to retrieve the contract.
3. **Swagger UI paths** are URLs opening the browser interface, usually starting at `/swagger-ui.html` by default and routing to Swagger UI assets. The interface then fetches the OpenAPI document from the documentation endpoint.

All three layers can be affected by context paths, servlet mappings, or reverse proxy prefixes, yet their configurations do not substitute for one another. Changing the documentation fetch URL does not change controller mappings; changing the Swagger UI path does not change API paths; and changing API paths does not change OpenAPI endpoints.

## 1. Identifying Default URLs

For a Spring MVC application without a context path, without customized springdoc paths, and with the UI starter, common URLs are:

| Purpose | Default URL | Who Uses It? |
| --- | --- | --- |
| Business API | Defined by controllers, e.g., `/api/orders` | Frontend applications, services, or API clients. |
| Default OpenAPI JSON | `/v3/api-docs` | API catalogs, SDK generators, contract tests, and Swagger UI. |
| Default OpenAPI YAML | `/v3/api-docs.yaml` | Export pipelines, registries, or consumers needing YAML files. |
| Grouped OpenAPI JSON | `/v3/api-docs/{group}` | Consumers of a separately grouped document. |
| Grouped OpenAPI YAML | `/v3/api-docs/{group}.yaml` | Consumers needing a group's YAML. |
| Swagger UI entry point | `/swagger-ui.html` | Developers opening the interactive documentation UI. |
| Swagger UI static resources | Usually `/swagger-ui/index.html` | Browsers loading HTML, JavaScript, CSS, and UI assets. |
| Swagger config | Defaults usually to `/v3/api-docs/swagger-config` | Swagger UI reading settings and document lists. |

The URLs above are common springdoc 2.x defaults under standard configuration. An application may change base paths, groups, context paths, servlet mappings, or proxy prefixes. When diagnosing, verify actual URLs in the running environment instead of assuming every application uses these exact paths.

## 2. Business API Paths Come from Controller Mappings

Controllers determine operation methods and paths. Example:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    OrderResponse getOrder(@PathVariable String id) {
        return orderService.findById(id);
    }
}
~~~

`OrderService` and `OrderResponse` are application-defined types; the constructor illustrates injecting the service into the controller.

The operation published in OpenAPI has path `/api/orders/{id}` and method `GET`. springdoc reads the mapping from the controller and puts the operation into the document; `/v3/api-docs` is where the document containing that operation is returned.

If the mapping changes to `/api/v2/orders/{id}`, the business API changes path. The default OpenAPI endpoint can still be `/v3/api-docs`. If only `springdoc.api-docs.path` changes, the business API keeps its existing mapping.

Do not add documentation paths to a controller's `@RequestMapping` just to make Swagger UI work. For instance, `/v3/api-docs` is not a business controller endpoint and should not be re-declared in a custom controller when springdoc already manages it.

## 3. Changing the OpenAPI Endpoint with springdoc.api-docs.path

The `springdoc.api-docs.path` property changes the endpoint for downloading the OpenAPI document. Example:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~

With this configuration, the default documentation endpoint shifts from `/v3/api-docs` to `/openapi`; the corresponding YAML endpoint is usually `/openapi.yaml`. Business operations like `/api/orders/{id}` remain unchanged.

If groups exist, group documents are served under the new base path, for example:

- Default JSON: `/openapi`
- Default YAML: `/openapi.yaml`
- Group `partner-v1` JSON: `/openapi/partner-v1`
- Group `partner-v1` YAML: `/openapi/partner-v1.yaml`

After changing the base path, update everywhere the document is fetched: Swagger UI if a static URL is configured, API catalogs, CI exports, contract tests, gateway routes, monitoring, and Spring Security matchers. Some integrations pick up the default URL provided by springdoc automatically; still verify actual requests rather than guessing all configs updated.

Do not confuse `springdoc.api-docs.path` with `springdoc.swagger-ui.path`. The first changes the JSON/YAML endpoint; the second changes the UI entry point.

## 4. Changing the Swagger UI URL with springdoc.swagger-ui.path

If developers should open the interface at `/docs`, configure:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
~~~

`/docs` is the UI entry point URL. It does not change API paths in the document and does not automatically change the JSON endpoint. Depending on static resource configuration and version, the entry point may redirect to the actual Swagger UI resources.

Example configuring both endpoint types:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
~~~

Expected result on an application without a context path:

| Function | URL |
| --- | --- |
| Business API | `/api/orders/{id}` |
| OpenAPI JSON | `/openapi` |
| OpenAPI YAML | `/openapi.yaml` |
| Swagger UI entry point | `/docs` |

Opening `/docs` only proves the UI entry point is reachable. Swagger UI must still load swagger config and the OpenAPI document. If HTML loads successfully while the API area shows an error, check subsequent requests in the browser's Network tab.

## 5. Configuring Swagger UI to Use the Right Document

Normally springdoc supplies the OpenAPI URL to Swagger UI automatically. When using a specific document or multiple groups, you can configure a URL list:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
    urls:
      - name: public-v1
        url: /openapi/public-v1
      - name: partner-v1
        url: /openapi/partner-v1
~~~

In the example, Swagger UI displays a document selector for the two groups. The URLs in the list are OpenAPI document fetch URLs; they are not business operation URLs.

If using a single external document or a separately published file, `springdoc.swagger-ui.url` can point to that specification URL. If using `springdoc.swagger-ui.config-url`, Swagger UI fetches settings from the designated endpoint. These properties control the UI's document/config source; they do not change controller mappings.

When configuring an absolute URL, confirm the browser can reach that host and CORS policies permit fetching the document if cross-origin. If the URL is relative, it resolves against the origin/base path of the open page; check actual request URLs after deploying behind a proxy.

## 6. Group IDs Create Additional Documentation Paths

Groups are created using `GroupedOpenApi`:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroups {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-v1")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner-v1")
            .pathsToMatch("/api/partner/**")
            .build();
    }
}
~~~

The group ID appears in the document URL. With the default base path:

| Group | JSON | YAML |
| --- | --- | --- |
| Default | `/v3/api-docs` | `/v3/api-docs.yaml` |
| `public-v1` | `/v3/api-docs/public-v1` | `/v3/api-docs/public-v1.yaml` |
| `partner-v1` | `/v3/api-docs/partner-v1` | `/v3/api-docs/partner-v1.yaml` |

If `springdoc.api-docs.path` is changed to `/openapi`, group URLs also shift base to `/openapi/{group}`. Group IDs do not alter API operation paths. For instance, `partner-v1` can contain operation `GET /api/partner/orders` while the document is fetched at `/openapi/partner-v1`.

A group ID is part of a discovery URL that registries or clients may store. Changing a group ID can break consumers fetching the document, even while controllers keep running normally.

## 7. Application Context Path Prefixes Every Endpoint

In a Servlet application, `server.servlet.context-path` sets the context path for the entire application:

~~~yaml
server:
  servlet:
    context-path: /store
~~~

With this configuration, externally accessed URLs normally carry the `/store` prefix:

| Application Endpoint | Access URL |
| --- | --- |
| API `GET /api/orders/{id}` | `/store/api/orders/{id}` |
| OpenAPI JSON `/v3/api-docs` | `/store/v3/api-docs` |
| Swagger UI `/swagger-ui.html` | `/store/swagger-ui.html` |

The context path is not part of controller mappings. Controllers still declare `/api/orders/{id}`; the container mounts the whole application under `/store`.

With Spring WebFlux, base path configuration usually uses:

~~~yaml
spring:
  webflux:
    base-path: /store
~~~

This is the base path of a reactive application. Do not use `server.servlet.context-path` to configure the base path for a pure WebFlux application. Choose the property matching your web stack.

When an application has a context path, verify the actual URLs of APIs, documents, Swagger UI, and swagger config. A URL working at local root may require a prefix upon deployment.

## 8. Distinguishing Context Path, Servlet Mapping, and Controller Path

In a Servlet application, a request URL may be assembled from multiple parts:

~~~text
https://api.example.com/store/api/orders/42
                     |      |   |
                     |      |   +-- Controller mapping
                     |      +------ Application context path
                     +------------- Public host and scheme
~~~

A custom servlet mapping or gateway configuration can also affect how requests are routed to DispatcherServlet. Thus, when a URL fails to match, determine which host, context path, servlet mapping, and controller mapping the request reached.

Do not manually add the same prefix to both `server.servlet.context-path` and `@RequestMapping` if the goal is simply mounting the app under a context. If both include `/store`, URLs can become `/store/store/...`.

Similarly, do not place `/store` simultaneously in proxy rewrites, context path, and OpenAPI `servers.url` without clarifying which layer owns the prefix. Duplicated prefixes are a common cause of Swagger UI generating wrong URLs.

## 9. Reverse Proxies Adding Public Prefixes

In production, an application may run at root internally while being published under a prefix. Example:

~~~text
Client:
  https://gateway.example.com/store/api/orders/42

Reverse proxy:
  strips /store prefix when forwarding request

Spring Boot:
  receives /api/orders/42
~~~

If the proxy strips the prefix before forwarding, the backend may only see path `/api/orders/42`. In that situation, the application needs to know the public prefix if springdoc must construct absolute URLs or Swagger UI needs to call endpoints back under `/store`.

One approach is having the proxy send trusted forwarded headers and Spring process them. Spring Boot example:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

The proxy can pass the public scheme, host, and prefix using corresponding forwarded headers. Exact settings depend on the proxy and path rewrite behavior. Only trust forwarded headers controlled by the proxy; do not allow internet clients to dictate hosts or prefixes reflected in the documentation.

Nginx example illustrating stripping a prefix and sending the original prefix:

~~~nginx
location /store/ {
    proxy_pass http://spring-app/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Prefix /store;
}
~~~

This is an illustrative configuration. Verify Nginx location, `proxy_pass` trailing slash, path rewrites, and actual forwarded headers in your system. If the proxy preserves the prefix instead of stripping it, configure the backend to accept that path; do not apply both strategies simultaneously.

## 10. OpenAPI servers URL Is Not the Document Fetch URL

OpenAPI has a `servers` field describing the base URL clients use when calling operations. It is not the endpoint where the OpenAPI document is downloaded.

Example document having:

~~~yaml
servers:
  - url: https://api.example.com/store
paths:
  /api/orders/{id}:
    get:
      operationId: getOrderById
~~~

Clients combine the server URL with the operation path to call:

`https://api.example.com/store/api/orders/42`

Meanwhile, the OpenAPI document can be fetched at:

`https://api.example.com/store/v3/api-docs`

Do not put `/v3/api-docs` into `servers.url`; that is a discovery/document URL. Do not append `/api` to the server URL if operation paths already start with `/api`, as clients could generate URLs with duplicated prefixes.

If a public API has a fixed base URL, you can declare it explicitly with annotations:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com/store",
            description = "Public API"
        )
    }
)
class PublicServerConfiguration {
}
~~~

If local, staging, and production have different hosts, do not hard-code a production host across all environments. Use profile/environment-variable configuration or let server URLs be determined from trusted forwarded headers. Inspect documents in each environment to ensure URLs do not point to internal hostnames.

## 11. Securing the Right Paths with Spring Security

Documentation and Swagger UI paths often have different access policies than business APIs. For example:

- Business APIs require an access token and scopes.
- OpenAPI documents are downloadable only by development teams or internal API registries.
- Swagger UI is open only in dev/staging environments or to signed-in users.

When changing docs or UI paths, update security matchers accordingly. Example matchers for default configuration:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml"
    ).hasAuthority("docs.read")
    .requestMatchers(
        "/swagger-ui.html",
        "/swagger-ui/**"
    ).hasAuthority("docs.ui")
    .anyRequest().authenticated()
);
~~~

These are illustrative rules to merge into an existing `SecurityFilterChain`. If `springdoc.api-docs.path` is `/openapi` and `springdoc.swagger-ui.path` is `/docs`, replace matchers with the new paths and cover JSON, YAML, groups, swagger-config, and actual static resources.

For example, with a changed docs base path, URLs to consider include `/openapi`, `/openapi.yaml`, `/openapi/{group}`, `/openapi/{group}.yaml`, and actual swagger config. Pattern `/openapi/**` covers groups and swagger config under the base path, but does not substitute for an explicit matcher for sibling `/openapi.yaml`.

Note that a matcher for `/v3/api-docs/**` does not necessarily cover sibling endpoint `/v3/api-docs.yaml`; check the YAML URL explicitly. Protecting only the UI entry point while leaving JSON public still lets users download the document directly. Conversely, protecting the document without letting Swagger UI fetch config/specs causes the UI to display authentication errors.

Do not expose internal documentation to the internet just so Swagger UI works. Protect the document with the same login/token mechanism, or omit publishing the UI in environments that do not need it.

## 12. Checking Endpoints with curl

When diagnosing, call each URL type separately:

~~~bash
# Business API
curl -i http://localhost:8080/api/orders/42

# OpenAPI JSON
curl -i http://localhost:8080/v3/api-docs

# OpenAPI YAML
curl -i http://localhost:8080/v3/api-docs.yaml

# Group OpenAPI document
curl -i http://localhost:8080/v3/api-docs/partner-v1

# Swagger UI entry point
curl -i http://localhost:8080/swagger-ui.html
~~~

If the application has context path `/store`, prepend `/store` to access URLs. If a proxy publishes prefix `/store`, test URLs through the proxy rather than calling only the backend directly.

For protected endpoints, pass valid tokens or cookies. Distinguish:

- `404`: path, prefix, group id, or route does not exist at the requested URL.
- `401`: missing or invalid authentication credentials.
- `403`: authenticated but lacks permission.
- `302`/`3xx`: redirect occurred; inspect `Location` to see where the UI forwards.
- `200` with login HTML body: request was redirected to a login page instead of receiving JSON/YAML.

## 13. Testing Documentation URLs with MockMvc

OpenAPI endpoints and Swagger UI routes can be verified using Spring Boot tests. Example for a Spring MVC application:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentationPathTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void servesOpenApiJsonAtConfiguredPath() throws Exception {
        mockMvc.perform(get("/openapi"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith("application/json"));
    }

    @Test
    void servesOpenApiYamlAtConfiguredPath() throws Exception {
        mockMvc.perform(get("/openapi.yaml"))
            .andExpect(status().isOk())
            .andExpect(content().string(org.hamcrest.Matchers.containsString("openapi:")));
    }
}
~~~

The example assumes the application configures `springdoc.api-docs.path: /openapi`. If using the default base path, update both test URLs accordingly. If security protects docs, add authentication/authority tests rather than disabling security.

UI endpoint tests can check status or redirects depending on version and static resource configuration. Avoid coupling strictly to a single redirect code if the application customizes resource handlers; verify the `Location` header or access actual Swagger UI resources per your chosen setup.

## 14. Verifying Generated Documents Contain the Right Paths

A documentation endpoint returning JSON does not prove the business paths inside the document are correct. Check the `paths` field:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiApplicationPathTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void documentContainsBusinessPathWithoutDocsPrefix() throws Exception {
        String body = mockMvc.perform(get("/openapi"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode document = objectMapper.readTree(body);
        assertThat(document.path("paths")
            .has("/api/orders/{id}")).isTrue();
        assertThat(document.path("paths")
            .has("/openapi")).isFalse();
    }
}
~~~

This test illustrates the principle: `paths` holds business operations; `/openapi` is where the document is downloaded and should not appear as an application operation unless the application genuinely has such a controller mapping.

If using a context path, `MockMvc` can be configured differently depending on test setup. Inspect request URLs in the corresponding integration environment and distinguish internal application paths from public URLs via a proxy.

## 15. Common Errors

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| `/api/orders` works, but `/v3/api-docs` returns 404 | Missing springdoc starter, or API docs disabled/path changed | Check starter and `springdoc.api-docs.path`, `springdoc.api-docs.enabled`. |
| `/docs` returns 404 | `springdoc.swagger-ui.path` not configured or wrong context path called | Check UI starter, property, and full public URL. |
| Swagger UI opens but fails to load document | Stale swagger config/spec URL, 401/403, or bad proxy rewrite | Check Network tab, swagger-config, and JSON/YAML endpoints. |
| JSON works, but YAML returns 404 | Wrong `.yaml` suffix called or matcher/proxy does not route it | Check the YAML URL matching base path and group. |
| Group document returns 404 | Wrong group id or group not registered | Check `GroupedOpenApi.group(...)` and `/base-path/{group}` URL. |
| Public URL repeats `/store/store` | Prefix added multiple times across proxy, context path, or server URL | Assign prefix ownership to one layer and remove duplicates. |
| Swagger UI calls internal host | Forwarded headers unhandled or server URL hard-coded | Configure trusted proxy headers or environment-specific `servers`. |
| OpenAPI paths contain unwanted proxy prefix | Public prefix confused with operation path or proxy rewrite | Check forwarded prefix and actual path received by backend. |
| Security protects UI, yet JSON stays public | Matcher only covers UI, docs endpoint unprotected | Add matchers for JSON, YAML, groups, and swagger-config. |
| Security protects JSON, causing Swagger UI to fail | UI lacks permission to fetch config/spec | Check both static resources and docs endpoints. |
| Works locally, fails in production | Different context path, proxy prefix, scheme, or host | Test through public ingress and inspect `Location`, request URLs, and `servers`. |
| Document has `/openapi` inside `paths` | Controller mapping collides with docs URL or misconfigured customizer | Check controller mappings and customizers; do not confuse docs endpoint with operation. |

## 16. Checklist When Changing Paths

Before changing API, docs, or UI paths, verify:

1. Are business API paths in controllers changing?
2. Is `springdoc.api-docs.path` changing?
3. Is `springdoc.swagger-ui.path` changing?
4. Do group IDs and each group's JSON/YAML URLs stay the same?
5. Is a context path or WebFlux base path applied?
6. Is the reverse proxy stripping or preserving prefixes?
7. Are forwarded headers set by a trusted proxy?
8. Does OpenAPI `servers.url` contain the right public base URL without duplicating prefixes?
9. Does Swagger UI load the right swagger-config and OpenAPI document?
10. Do Spring Security matchers cover UI, JSON, YAML, groups, and config endpoints?
11. Are CI exports, API catalogs, monitoring, or contract tests using old URLs?
12. Were tests run through ingress/public URLs rather than only localhost?

## 17. Guiding Principles

- Keep API operation paths, OpenAPI document paths, and Swagger UI paths separate.
- Use controller mappings for business APIs; use `springdoc.api-docs.path` for JSON/YAML.
- Use `springdoc.swagger-ui.path` to change the UI entry point.
- Remember that group IDs create additional document URLs under the API docs base path.
- Distinguish application context paths from controller mappings and reverse proxy prefixes.
- For WebFlux, use the WebFlux base path; for Servlet, use the Servlet context path.
- Do not repeat the same prefix across proxy rewrites, context path, and `servers.url` if it creates duplicate URLs.
- Keep OpenAPI `servers.url` as the base URL for API operations, not the document fetch URL.
- Update security matchers for Swagger UI, swagger-config, JSON, YAML, and groups alike.
- Test public URLs through proxies, not just backend localhost.

Application API paths determine where clients execute business logic; OpenAPI paths determine where consumers fetch contracts; Swagger UI paths determine where developers open the interface. Context paths and reverse proxies can prefix these URLs, while `servers.url` describes the base URL for calling operations. When these roles are cleanly separated and configurations, security matchers, and public-URL tests are updated together, an application can change how it publishes documentation without accidentally altering its business APIs.

## References

- [Springdoc OpenAPI FAQ – API docs path and Swagger UI path](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – Core Properties](https://springdoc.org/core-properties.html)
- [Spring Boot – Servlet Web Applications: Context Path](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Framework – Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object)
