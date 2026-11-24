# Aggregating Multi-Service Documentation and Handling Server URLs

In a multi-service architecture, each Spring Boot application can generate its own OpenAPI document. Teams often want to host those documents inside a shared Swagger UI while ensuring URLs inside each document point to public endpoints exposed through an API gateway or reverse proxy.

With `springdoc-openapi`, three layers must be distinguished:

1. **Multiple document groups inside one application:** use `GroupedOpenApi` to generate multiple OpenAPI documents from one Spring Boot service.
2. **Multiple documents from multiple services:** use `springdoc.swagger-ui.urls` so Swagger UI renders a document selector.
3. **One merged OpenAPI document:** requires a real aggregation step to combine paths, schemas, security schemes, and metadata from multiple documents.

Swagger UI can display multiple documents within one interface, yet the document selector does not merge documents into a single OpenAPI specification. At the same time, the server URL in each document must reflect the address consumers can actually reach, not an internal container hostname.

This lesson guides you through designing documentation endpoints, configuring multi-service Swagger UI, handling URLs behind gateways/proxies, declaring `servers`, securing documentation, testing, and distributing specs.

## 1. Models for organizing documentation

There are three common models:

| Model | Documentation Source | Result |
|---|---|---|
| Grouped documents | Multiple controller groups within one Spring Boot app | Multiple OpenAPI URLs within the same service |
| Multi-service Swagger UI | OpenAPI endpoints from multiple services | One Swagger UI with a selector to choose each document |
| Merged OpenAPI | Multiple documents parsed and merged | One OpenAPI document containing paths/components of multiple services |

`GroupedOpenApi` fits when one application has multiple API groups such as `public`, `admin`, and `partner`. Multi-URL Swagger UI fits when a documentation portal displays APIs from orders, catalog, identity, or payment services.

Merged OpenAPI fits when consumers or downstream tools require strictly one spec file containing the full contract. This requires resolving collisions across schema names, `operationId` values, security schemes, servers, and paths.

Before configuring, determine whether consumers need an interface to pick from multiple documents or a single unified document. These two requirements have different architectures and testing workflows.

## 2. `GroupedOpenApi` inside a single service

`GroupedOpenApi` creates independent documents from controllers within the same Spring Boot application.

Example splitting `public` and `admin` APIs:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiDocumentationGroups {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .build();
    }
}
~~~

With default configuration, the documents can be fetched at:

~~~text
/v3/api-docs/public
/v3/api-docs/admin
~~~

The group name becomes the final segment of the documentation endpoint. Each group can configure `pathsToMatch`, `pathsToExclude`, `packagesToScan`, `packagesToExclude`, and dedicated customizers.

Do not use groups to represent services running on separate hosts. `GroupedOpenApi` only scans endpoints within the current `ApplicationContext`.

## 3. Selecting groups by package or path

If controllers are split by package:

~~~java
@Bean
GroupedOpenApi catalogApi() {
    return GroupedOpenApi.builder()
        .group("catalog")
        .packagesToScan("com.example.catalog.api")
        .build();
}
~~~

If filtering by URL:

~~~java
@Bean
GroupedOpenApi orderApi() {
    return GroupedOpenApi.builder()
        .group("orders")
        .pathsToMatch("/api/orders/**")
        .pathsToExclude("/api/orders/internal/**")
        .build();
}
~~~

Pick a stable criterion matching your source structure. Package filters work well when boundaries follow modules; path filters work well when boundaries follow routes.

After creating groups, fetch each group's endpoint and verify no operations are missing. Two groups can include the same operation if filters overlap; decide intentionally whether that behavior is desired.

## 4. Swagger UI displaying multiple documents from multiple services

`springdoc` supports configuring a list of URLs for Swagger UI using `springdoc.swagger-ui.urls`.

Example of a documentation portal accessing three services through an API gateway:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
    disable-swagger-default-url: true
    urls:
      - name: Orders
        url: /orders/v3/api-docs
      - name: Catalog
        url: /catalog/v3/api-docs
      - name: Identity
        url: /identity/v3/api-docs
    urls-primary-name: Orders
~~~

When opening `/docs`, Swagger UI displays a selector allowing users to pick Orders, Catalog, or Identity. `urls-primary-name` specifies the document selected when the UI initializes.

Names in the list must be unique; URLs must also be unique because Swagger UI uses them as identifiers for selections. Use short, clear names consistent with service names or API domains.

Relative URLs like `/orders/v3/api-docs` are often convenient when the portal and services are exposed through the same gateway origin. Browsers fetch documents from the same host, avoiding many CORS issues.

## 5. Configuring the URL list with `application.properties`

You can use `application.properties` instead of YAML:

~~~properties
springdoc.swagger-ui.path=/docs
springdoc.swagger-ui.disable-swagger-default-url=true
springdoc.swagger-ui.urls[0].name=Orders
springdoc.swagger-ui.urls[0].url=/orders/v3/api-docs
springdoc.swagger-ui.urls[1].name=Catalog
springdoc.swagger-ui.urls[1].url=/catalog/v3/api-docs
springdoc.swagger-ui.urls[2].name=Identity
springdoc.swagger-ui.urls[2].url=/identity/v3/api-docs
springdoc.swagger-ui.urls-primary-name=Orders
~~~

The URL list configuration lives inside Swagger UI. It neither creates proxy routes nor automatically exposes documentation endpoints on target services.

You still must ensure each URL returns valid OpenAPI JSON and the portal is authorized to access that URL.

## 6. Distinguishing single `url` from multi-document `urls`

Swagger UI can configure a single spec URL or a list of URLs:

| Property | Purpose |
|---|---|
| `springdoc.swagger-ui.url` | Loads one OpenAPI document |
| `springdoc.swagger-ui.urls` | Displays a list of multiple OpenAPI documents |
| `springdoc.swagger-ui.urls-primary-name` | Selects the initial document name from the list |
| `springdoc.swagger-ui.configUrl` | URL to load Swagger UI configuration |
| `springdoc.swagger-ui.path` | Path to the Swagger UI HTML page |

If the portal needs multiple services, use `urls`. If you only want to replace the default spec with a single static file or different URL, `url` may fit.

Do not arbitrarily configure both `url` and `urls` at once. Determine which document source the UI should use and inspect the generated `swagger-config`.

## 7. The `swagger-config` endpoint and document loading flow

By default, Swagger UI fetches configuration from:

~~~text
/v3/api-docs/swagger-config
~~~

When a URL list is configured, the config endpoint supplies the metadata Swagger UI uses to build the document selector.

The typical loading flow is:

~~~text
Browser
  |
  v
/docs
  |
  v
Swagger UI JavaScript
  |
  v
/v3/api-docs/swagger-config
  |
  v
List of Orders, Catalog, Identity
  |
  +----> /orders/v3/api-docs
  |
  +----> /catalog/v3/api-docs
  |
  +----> /identity/v3/api-docs
~~~

If the UI page opens yet the dropdown is empty, inspect the `swagger-config` response and network requests loading each document. Failures can stem from configuration, reverse proxies, authentication, or CORS.

If overriding `configUrl`, ensure the new configuration endpoint returns the exact format Swagger UI expects. Do not confuse `configUrl` with the OpenAPI JSON URL.

## 8. Gateway routes for multiple services

An API gateway can expose a public prefix for each service:

~~~text
https://api.example.com/orders/**
https://api.example.com/catalog/**
https://api.example.com/identity/**
~~~

The gateway forwards routes to their respective services. Illustrative example using Spring Cloud Gateway:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://orders-service:8080
          predicates:
            - Path=/orders/**
          filters:
            - StripPrefix=1
        - id: catalog
          uri: http://catalog-service:8080
          predicates:
            - Path=/catalog/**
          filters:
            - StripPrefix=1
~~~

When the browser requests `/orders/v3/api-docs`, the gateway strips the `/orders` prefix and forwards `/v3/api-docs` to `orders-service`.

This is only a routing example. Production configurations also require timeouts, TLS, authentication, rate limits, health checks, and forwarded-header rules.

The Swagger UI portal can then use same-origin URLs:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Orders
        url: /orders/v3/api-docs
      - name: Catalog
        url: /catalog/v3/api-docs
~~~

The gateway must permit access to both documentation endpoints and the API operations users invoke via Try it out.

## 9. What does the URL in the OpenAPI `server` object mean?

In OpenAPI, `servers` defines the base URL consumers use to call operations. Operation paths are appended to the server URL.

For example, a document has:

~~~yaml
servers:
  - url: https://api.example.com/orders
paths:
  /api/orders:
    get:
      responses:
        "200":
          description: Success
~~~

The resulting call URL is:

~~~text
https://api.example.com/orders/api/orders
~~~

If the server URL is `https://orders-service:8080`, external clients may try calling the internal hostname and fail.

The server URL must be an address reachable by target consumers. For documentation published behind a gateway, use the public hostname and public prefix or an appropriate relative URL.

## 10. Using relative server URLs when the portal shares an origin

OpenAPI permits relative server URLs. Example:

~~~yaml
servers:
  - url: /orders
    description: Orders service via API gateway
~~~

If the document is loaded from `https://api.example.com/orders/v3/api-docs`, the server URL `/orders` is resolved by the browser against the same origin:

~~~text
https://api.example.com/orders
~~~

Operation path `/api/orders` becomes:

~~~text
https://api.example.com/orders/api/orders
~~~

This is useful when the same API is deployed across multiple domains while keeping the same path prefix. Consumers reuse the host of the current document without hard-coding environment hostnames.

Check how client generators handle relative server URLs. Some generated clients may require the base URL to be supplied via runtime configuration.

## 11. Declaring fixed servers with `@OpenAPIDefinition`

If a service has a single fixed public base path, you can declare the server in an annotation:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "/orders",
            description = "Orders service via API gateway"
        )
    }
)
class OpenApiServerConfiguration {
}
~~~

When server annotations are present, `springdoc` uses the declared server instead of the URL inferred automatically from requests.

This is a simple option when a service has one stable public path. If different URLs are needed per environment, use configuration properties or an `OpenAPI` bean/customizer to avoid changing source code on deploy.

## 12. Declaring `servers` with an `OpenAPI` bean

You can create an `OpenAPI` bean:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class OpenApiServerBeanConfiguration {

    @Bean
    OpenAPI openAPI() {
        return new OpenAPI()
            .servers(List.of(
                new Server()
                    .url("/orders")
                    .description("Public gateway route"),
                new Server()
                    .url("https://staging.example.com/orders")
                    .description("Staging")
            ));
    }
}
~~~

An `OpenAPI` bean can supply shared metadata across the document. If an application has multiple `GroupedOpenApi` beans and each group needs different servers, check the scope of application and attach group-specific customizers when needed.

Never place internal hostnames such as `orders-service:8080` in public documents. Internal addresses can vary across containers, clusters, or service discovery.

## 13. Multiple servers for production and staging

OpenAPI allows listing multiple servers:

~~~yaml
servers:
  - url: https://api.example.com/orders
    description: Production
  - url: https://staging-api.example.com/orders
    description: Staging
~~~

Swagger UI can show a server selector for operations. Users can pick an environment for Try it out if CORS and authentication allow it.

Publish only servers that document readers are authorized to use. Do not include dev URLs, `localhost`, or internal admin endpoints in public documentation.

If staging uses different credentials than production, clarify this in the guide and ensure Swagger UI does not automatically send production credentials to another host.

## 14. Using server variables for environments

If hostnames or version paths follow a convention, server variables can reduce repetition:

~~~yaml
servers:
  - url: https://{environment}.example.com/{service}
    description: API by environment
    variables:
      environment:
        default: api
        enum:
          - api
          - staging-api
      service:
        default: orders
        enum:
          - orders
          - catalog
~~~

Server variables fit well when values belong to a controlled set. Do not use variables to allow arbitrary URL input if doing so could cause calls to the wrong host or leak credentials to untrusted endpoints.

For services with distinct domains and security policies, separate per-service documents are usually clearer than sharing one server variable.

## 15. Handling reverse proxies and forwarded headers

When an application runs behind a reverse proxy, requests reaching Spring Boot may carry internal host, scheme, port, or prefix values. External clients, meanwhile, connect using the public URL.

Example:

~~~text
Client
  |
  | https://api.example.com/orders
  v
Reverse proxy / API gateway
  |
  | http://orders-service:8080
  v
Spring Boot service
~~~

The proxy can send headers describing the original request:

- `Forwarded` per RFC 7239.
- `X-Forwarded-Host`.
- `X-Forwarded-Port`.
- `X-Forwarded-Proto`.
- `X-Forwarded-Prefix`.
- `X-Forwarded-For`.

Spring Boot must be configured to process forwarded headers if you want the framework to infer the public URL accurately.

## 16. Configuring `server.forward-headers-strategy`

In Spring Boot, the standard property is:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

`FRAMEWORK` uses Spring Framework's `ForwardedHeaderFilter` mechanism to process forwarded headers. `NATIVE` delegates handling to the underlying web server according to its capabilities; consult your web server's documentation and verify which headers the proxy sends.

Choose a strategy matching your infrastructure. Do not simultaneously register a manual filter and configure a strategy in a way that applies the filter twice.

If the proxy uses a public prefix, ensure `X-Forwarded-Prefix` is sent properly. For example, public path `/orders` may be forwarded to the application at root path `/`.

After configuring, inspect the Swagger UI URL, `swagger-config`, the OpenAPI document, and `servers` inside the document. Merely seeing the HTML page open does not prove server URLs are correct.

## 17. Configuring `X-Forwarded-Prefix`

Suppose the gateway receives:

~~~text
https://api.example.com/orders/v3/api-docs
~~~

yet forwards upstream to:

~~~text
http://orders-service:8080/v3/api-docs
~~~

The gateway can send:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
X-Forwarded-Prefix: /orders
~~~

When Spring processes forwarded headers properly, the external URL can be reflected in request-derived links.

If the gateway preserves the prefix in the upstream path instead of stripping it, do not add the prefix again via `X-Forwarded-Prefix`. Determine exactly how the gateway rewrites paths to avoid duplicated URLs like `/orders/orders`.

## 18. Protecting forwarded headers at the proxy boundary

Forwarded headers influence the host and scheme the application trusts. If external clients can forge `X-Forwarded-Host` or `X-Forwarded-Proto` and the proxy forwards them verbatim to the application, an attacker can trick the application into generating URLs with the wrong host or scheme.

At the trust boundary, the proxy should strip client-supplied forwarded headers and overwrite them with values determined from the actual connection.

In addition:

- Restrict the application to accept traffic only from trusted proxies when possible.
- Do not use forwarded hosts to build public links unless the source is verified.
- Verify the scheme is always HTTPS in public environments.
- Never allow internal hostnames to appear in the spec.
- Check redirects, links, and server URLs in the document after deployment.

Forwarded headers are infrastructure inputs, not metadata to blindly trust from browsers.

## 19. Using `ServerBaseUrlCustomizer` when auto-generated URLs need adjustment

`springdoc` provides `ServerBaseUrlCustomizer` to adjust the base URL inferred from requests.

Example for an application with a single fixed public base URL:

~~~java
import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class PublicServerUrlConfiguration {

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

Configuration:

~~~yaml
api:
  public-base-url: https://api.example.com/orders
~~~

This customizer replaces the inferred URL with the configured public URL. Use this approach when the service has one stable public base URL and does not need per-request inference.

If there are multiple groups or each group has its own server, a service-wide customizer may be too broad. Set `servers` per group using an appropriate `OpenApiCustomizer`.

If the document already declares `servers` explicitly via `@OpenAPIDefinition` or an `OpenAPI` bean, verify how that declaration interacts with URL inference. Do not add a customizer just to patch a URL that is already explicitly fixed.

## 20. Setting dedicated servers per group

One application can serve multiple API groups with different public prefixes:

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
    GroupedOpenApi ordersGroup() {
        OpenApiCustomizer serverCustomizer = openApi ->
            openApi.setServers(List.of(
                new Server()
                    .url("/orders")
                    .description("Orders via gateway")
            ));

        return GroupedOpenApi.builder()
            .group("orders")
            .pathsToMatch("/api/orders/**")
            .addOpenApiCustomizer(serverCustomizer)
            .build();
    }

    @Bean
    GroupedOpenApi catalogGroup() {
        OpenApiCustomizer serverCustomizer = openApi ->
            openApi.setServers(List.of(
                new Server()
                    .url("/catalog")
                    .description("Catalog via gateway")
            ));

        return GroupedOpenApi.builder()
            .group("catalog")
            .pathsToMatch("/api/catalog/**")
            .addOpenApiCustomizer(serverCustomizer)
            .build();
    }
}
~~~

Each group has its own server so consumers call the right public prefix. Fetch `/v3/api-docs/orders` and `/v3/api-docs/catalog` to verify each document's server.

If metadata applies to all groups, consider `GlobalOpenApiCustomizer` or an `OpenAPI` bean. If only one group has a different server, attaching the customizer to that group keeps the change scoped.

## 21. CORS when documents reside on another origin

If Swagger UI runs at:

~~~text
https://docs.example.com
~~~

while the service document resides at:

~~~text
https://orders.example.net/v3/api-docs
~~~

browsers treat this as a cross-origin request. CORS must be configured so the docs portal can fetch the OpenAPI JSON. If users click Try it out, API endpoints must also allow the Swagger UI origin.

Verify CORS for both flows:

1. Swagger UI fetching the document.
2. Swagger UI sending test requests to the API server.

Spring MVC CORS example:

~~~java
@Configuration
class CorsConfiguration {

    @Bean
    WebMvcConfigurer corsConfigurer() {
        return new WebMvcConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/**")
                    .allowedOrigins("https://docs.example.com")
                    .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
                    .allowedHeaders("Authorization", "Content-Type", "Accept")
                    .allowCredentials(true);
            }
        };
    }
}
~~~

If using Spring Security, CORS must be enabled and integrated with the security filter chain. With credentials, never use a wildcard origin. Allow only portal origins that genuinely need access.

Configure CORS on the service or gateway receiving the cross-origin request. Configuring CORS on the portal does not automatically grant browsers permission to fetch documents from another service.

## 22. Authentication for documentation and Try it out

Documentation endpoints can be protected with Spring Security. When doing so, decide:

- Who can open Swagger UI?
- Who can fetch `swagger-config`?
- Who can fetch each service's OpenAPI document?
- Who can use Try it out against APIs?
- Which credentials are used for each service?

If a portal loads specs for both orders and catalog, a user may be authorized to read orders docs yet not admin docs. Never make all documents public merely because the portal displays several APIs.

When each service uses different security schemes, keep security configuration inside each OpenAPI document. Swagger UI reads the security scheme of the currently selected document.

Do not place production client secrets directly in `swagger-ui.oauth.clientSecret`. That exposes sensitive credentials in UI configuration; use Authorization Code with PKCE or a mechanism fitting your environment and security policy.

## 23. Multi-document Swagger UI is not a merged spec

Configuring `urls` only builds a selectable list of documents. When selecting Orders, Swagger UI loads the Orders document; when selecting Catalog, it loads the Catalog document.

That does not create a single document containing:

~~~yaml
paths:
  /orders:
  /catalog:
components:
  schemas:
~~~

If a client generator requires one file containing all paths, the `urls` list will not satisfy that requirement. A dedicated merge step is needed.

This is a key distinction when designing an API portal:

| Requirement | Approach |
|---|---|
| One UI selecting per service | Swagger UI `urls` |
| One spec per domain | Separate OpenAPI document per service/group |
| One file for the whole organization | Document-merging aggregator |
| Per-service SDK | Generate SDK from each service's spec |
| Shared cross-domain SDK | Controlled merge or API facade design |

## 24. Challenges when actually merging OpenAPI documents

When merging multiple specs, you cannot simply concatenate `paths` and `components` objects. You must resolve:

- Colliding component schema names, such as `Error` or `PageResponse`.
- Colliding security scheme names with differing definitions.
- Colliding `operationId` values.
- Colliding paths and HTTP methods.
- Differing OpenAPI versions.
- Differing server URLs.
- Colliding tag names with differing descriptions.
- External `$ref` pointers becoming unreachable.
- Differing naming conventions and response envelopes.
- Differing security requirements and OAuth scopes.

For example, two services both define a `Customer` schema with different meanings. Merging without renaming causes one schema to overwrite the other or references to point to the wrong model.

An aggregator must parse each document, namespace components, rewrite all related `$ref` pointers, and re-validate the merged spec. Never use regex text replacement, as it can corrupt descriptions or examples.

## 25. Namespacing components during merging

One convention uses a service prefix:

~~~text
Orders_Order
Orders_ApiError
Catalog_Product
Catalog_ApiError
Identity_User
Identity_ApiError
~~~

When renaming a component, update its references:

~~~yaml
$ref: '#/components/schemas/Orders_ApiError'
~~~

You must also handle references inside `requestBody`, `responses`, `parameters`, `headers`, `callbacks`, `examples`, `securitySchemes`, `links`, and nested schemas.

If the aggregator cannot guarantee complete reference rewriting, keeping documents separate in Swagger UI is safer.

## 26. Handling servers when merging documents

Each service may define its own server:

~~~yaml
servers:
  - url: https://api.example.com/orders
~~~

and:

~~~yaml
servers:
  - url: https://api.example.com/catalog
~~~

When merged, a single root-level `servers` list cannot accurately represent every path if services have different base paths. You can place `servers` at the Path Item or Operation level when distinct servers are needed per path group.

Another option is normalizing paths to include the service prefix and using one shared root server:

~~~yaml
servers:
  - url: https://api.example.com
paths:
  /orders/api/orders:
    get:
      responses:
        "200":
          description: Success
  /catalog/api/products:
    get:
      responses:
        "200":
          description: Success
~~~

Do this only when the aggregator follows explicit path rules and all `$ref` pointers remain valid. Never add the prefix to paths while simultaneously keeping the prefix in the server URL, or final requests will duplicate the prefix.

## 27. Using external OpenAPI files in a portal

If services publish static specs instead of serving dynamic endpoints, Swagger UI can load files via URL.

For example, static files stored in the portal's static resources:

~~~text
src/main/resources/static/openapi/orders.json
src/main/resources/static/openapi/catalog.yaml
~~~

Single-document configuration:

~~~yaml
springdoc:
  swagger-ui:
    url: /openapi/orders.json
~~~

Multi-document configuration:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Orders
        url: /openapi/orders.json
      - name: Catalog
        url: /openapi/catalog.yaml
~~~

Files must be valid OpenAPI documents packaged with the application. If documentation is published by version, use immutable paths such as `/openapi/orders/2.1.0/openapi.json`.

Do not overwrite older release files if consumers need reproducible SDK generation or contract audits.

## 28. Managing versions and documentation URLs

In multi-service systems, each service can release independently. Define a clear documentation URL convention:

~~~text
/orders/v3/api-docs
/catalog/v3/api-docs
/identity/v3/api-docs
~~~

These are the current documentation URLs for each service. If immutable release documentation is needed, distribute artifacts by version:

~~~text
/openapi/orders/2.1.0/openapi.json
/openapi/catalog/4.0.0/openapi.json
/openapi/identity/1.8.2/openapi.json
~~~

Distinguish the API version in `info.version` from the OpenAPI specification version in the `openapi` field. Do not use the `springdoc` library version as the API version.

The portal can display current documentation alongside links to the release archive. When a service changes its contract, CI should generate a new artifact, validate it, and store it under its version.

## 29. Checking `swagger-config` and the URL list

You can fetch Swagger UI configuration:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/swagger-config
~~~

Verify the response contains the `urls` list with accurate URLs and names:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/swagger-config \
  | jq '.urls'
~~~

Inspect each document:

~~~bash
curl -fsS http://localhost:8080/orders/v3/api-docs -o orders.json
curl -fsS http://localhost:8080/catalog/v3/api-docs -o catalog.json
~~~

Check version and servers:

~~~bash
jq '{openapi, info, servers}' orders.json
jq '{openapi, info, servers}' catalog.json
~~~

If the portal runs behind a gateway, run these commands against the public gateway URL to verify the real browser experience. Testing internal `localhost` does not prove public routes work.

## 30. Testing `GroupedOpenApi` inside the application

You can use `WebTestClient` to verify group endpoints:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ApiDocumentationGroupsTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void exposesOrdersDocument() {
        webTestClient.get()
            .uri("/v3/api-docs/orders")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.openapi").exists()
            .jsonPath("$.paths['/api/orders']").exists();
    }
}
~~~

Also test the `catalog` group and verify it does not include `orders` paths. If a group uses a custom server, assert `servers[0].url` matches the public prefix.

For multi-service portals, test `swagger-config` and test fetching each spec. Use `WebTestClient` when routes live in the same test system, or HTTP integration tests through the gateway.

## 31. Testing URLs through a reverse proxy

A deployment verification test should send requests through the actual public gateway path:

~~~bash
curl -fsS https://api.example.com/orders/v3/api-docs -o orders.json
~~~

In real environments, the gateway overwrites `Forwarded` and `X-Forwarded-*` headers itself. Do not forge these headers from a browser or client and treat that as proof of proper proxy configuration.

Inspect the returned document:

- `servers` contains no internal hostnames.
- Scheme is HTTPS if the public endpoint uses HTTPS.
- Service prefixes are neither missing nor duplicated.
- Operation paths do not have prefixes added twice.
- Swagger UI document URLs remain fetchable.
- Try it out invokes the right public endpoint.

If using explicit `servers`, verify they match gateway paths and do not get the forwarded prefix applied a second time.

## 32. Verifying Swagger UI in a browser

After opening the portal:

1. Confirm the Swagger UI page loads cleanly.
2. Open the document selector.
3. Select each service.
4. Verify title, version, and tags match the service.
5. Inspect schemas, request bodies, and responses.
6. Check network requests loading OpenAPI JSON.
7. Try a safe operation in a test environment.
8. Confirm requests go through the public gateway URL.
9. Verify authentication and CORS.
10. Check the browser console for any errors.

The UI page can load successfully while one or more spec URLs fail with 401, 404, or CORS errors. Therefore, test every document in the list.

## 33. Disabling Swagger UI or API docs on services that should not expose them

Some services only need to export specs for internal pipelines without serving a public Swagger UI.

Disable the UI:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
~~~

Disable the API docs endpoint:

~~~yaml
springdoc:
  api-docs:
    enabled: false
~~~

If API docs are disabled on a service, the portal cannot fetch the document from that endpoint. In that case, distribute static specs or build artifacts from CI and supply them to the portal.

A service can enable API docs in an internal profile and disable them in production if policy requires it. Ensure the CI profile can export the contract before the endpoint is disabled.

## 34. Common mistakes

| Symptom | Root cause to check |
|---|---|
| Swagger UI shows only one service | Used `url` instead of `urls`, or `swagger-config` lacks the list |
| Selector shows names yet documents fail to load | Wrong URL, unreachable service, or blocked by authentication |
| Document loads yet Try it out fails | `servers` points to wrong host/prefix or API CORS is unconfigured |
| URL contains container hostname | Forwarded headers unhandled or `servers` not declared publicly |
| URL duplicates `/orders/orders` prefix | Gateway strips or keeps prefix while app/proxy also adds prefix |
| URL drops gateway prefix | Missing `X-Forwarded-Prefix` or server URL omits prefix |
| Scheme is HTTP while public uses HTTPS | `X-Forwarded-Proto` is not being processed |
| Browser reports CORS loading spec | Portal origin not allowed on docs endpoint |
| Browser reports CORS calling API | API endpoint does not allow portal origin |
| One group contains another group's paths | `pathsToMatch`/`pathsToExclude` overlap unintentionally |
| Custom server appears only on default document | Customizer not attached to the intended group |
| Merged spec loses schemas | Component name collision or un-rewritten `$ref` pointers |
| Security scheme overwritten | Duplicate scheme names with differing definitions |
| Client generator calls wrong URL | Server URL and operation path concatenate into wrong route |
| Swagger UI fails to load config | Wrong `configUrl` or security blocks `swagger-config` |

## 35. Workflow for deploying a multi-service portal

An applicable workflow:

1. Identify which services will be published in the portal.
2. Choose public routes for each service's OpenAPI document.
3. Configure gateway routes and path rewriting.
4. Configure server URLs inside each document.
5. Enable the forwarded-header strategy if URLs must be inferred from requests.
6. Configure `springdoc.swagger-ui.urls`.
7. Choose `urls-primary-name`.
8. Ensure docs endpoints have proper authentication/CORS.
9. Fetch `swagger-config` and each OpenAPI document.
10. Verify `servers`, `paths`, `security`, and `schemas`.
11. Test Try it out through the gateway.
12. Store contract artifacts per service/version.
13. Monitor document-loading errors after every deployment.

If a single unified document is required, add a dedicated aggregation step and validate every reference after merging. Never treat multi-URL Swagger UI as a merge step.

## 36. Pre-release checklist

- [ ] Determined whether `GroupedOpenApi`, multi-service UI, or a merged spec is needed.
- [ ] Group names within the same service are unique and meaningful.
- [ ] Every service has a public OpenAPI endpoint or static artifact.
- [ ] `springdoc.swagger-ui.urls` list has unique names and URLs.
- [ ] `urls-primary-name` points to the right default document.
- [ ] `swagger-config` returns the expected URL list.
- [ ] Gateway routes to each service work properly.
- [ ] Server URLs reflect public hostnames and prefixes.
- [ ] No internal hostnames or container ports appear in public specs.
- [ ] Forwarded headers are overwritten by the proxy from trusted sources.
- [ ] `X-Forwarded-Prefix` is neither dropped nor applied twice.
- [ ] `server.forward-headers-strategy` matches the web server.
- [ ] CORS allows the portal to load specs and invoke APIs when cross-origin.
- [ ] Authentication for UI, docs endpoints, and Try it out is tested.
- [ ] Group-specific customizers set servers on the right documents.
- [ ] Merged specs resolve component collisions and all `$ref` pointers.
- [ ] OpenAPI artifacts are versioned and stored immutably.
- [ ] Browser smoke tests selected and loaded every service document.
- [ ] Try it out calls the right public routes.
- [ ] CI checks `swagger-config` and every OpenAPI document.

## 37. References

- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html)
- [springdoc-openapi FAQ – Aggregating external OpenAPI endpoints](https://springdoc.org/faq.html)
- [springdoc-openapi FAQ – Reverse proxy and forwarded headers](https://springdoc.org/faq.html)
- [springdoc-openapi FAQ – GroupedOpenApi and customizers](https://springdoc.org/faq.html)
- [Spring Boot – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Framework – ForwardedHeaderFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html)
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)

Aggregating multi-service documentation requires cleanly separating document groups, Swagger UI's document list, and an actually merged specification. Use `GroupedOpenApi` for multiple groups within one service; use `springdoc.swagger-ui.urls` so a portal can select documents across services; and build an aggregator only when consumers require one unified OpenAPI file. For server URLs, publish public hosts/prefixes, handle forwarded headers properly at the trust boundary, verify CORS, and test Try it out through the gateway before release.
