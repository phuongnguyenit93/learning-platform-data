# Specification-Only Starters vs. UI-Bundled Starters

springdoc-openapi has two main starter groups for each Spring application type: a starter that only serves the OpenAPI document and a starter that also integrates Swagger UI. Choosing the right artifact helps control dependencies, application size, deployment surface, and how users view documentation.

Both groups can generate OpenAPI JSON/YAML from controllers, models, and annotations. The key difference is that the UI starter also packages Swagger UI and the web resources required to render and interact with the document.

This guide compares the Spring MVC and WebFlux artifacts, how to choose by environment, Maven/Gradle dependencies, exposed endpoints, configuration, security, deployment, and testing after swapping starters.

## 1. Distinguishing the Two Roles

A springdoc application can provide two independent capabilities:

- **Specification generation:** analyzing Spring controllers, mappings, DTOs, validation, and OpenAPI annotations to build the document.
- **Specification display:** providing a web interface for users to browse operations, inspect schemas, enter credentials, and test requests.

The API starter provides only specification generation. The UI starter provides both specification generation and the Swagger UI interface.

~~~text
                  Spring Boot application
                           |
                    springdoc integration
                           |
                 Generate OpenAPI document
                           |
                 /v3/api-docs (JSON/YAML)
                           |
             +-------------+-------------+
             |                           |
        API starter                 UI starter
             |                           |
       OpenAPI document          OpenAPI document
             |                           |
    External portal/client       Swagger UI assets
    generator/CI consumer         /swagger-ui/**
                                         |
                                   Try it out
                                         |
                                    API endpoints
~~~

Swagger UI should not be treated as mandatory for generating OpenAPI. A pipeline can export the document for an API portal or code generator without embedding an interface in the application.

## 2. The Four Main Artifacts

springdoc provides starters corresponding to Spring MVC and Spring WebFlux:

| Platform | Generate OpenAPI only | Generate OpenAPI and include Swagger UI |
|---|---|---|
| Spring MVC | `springdoc-openapi-starter-webmvc-api` | `springdoc-openapi-starter-webmvc-ui` |
| Spring WebFlux | `springdoc-openapi-starter-webflux-api` | `springdoc-openapi-starter-webflux-ui` |

These artifacts belong to the `org.springdoc` group.

Maven coordinate example:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

For the UI version, replace the artifact with:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

For WebFlux, replace `webmvc` with `webflux`.

Do not add both the API and UI starters for the same platform just to get full features. The UI starter already includes the required API document integration; adding the API starter alongside it is usually redundant.

## 3. Choosing the Starter by Spring MVC vs. WebFlux

Before deciding whether to include Swagger UI, identify the application's web stack.

**Spring MVC** typically uses:

- `spring-boot-starter-web`.
- `@RestController` with the Servlet stack.
- `springdoc-openapi-starter-webmvc-api` or `webmvc-ui`.

**Spring WebFlux** typically uses:

- `spring-boot-starter-webflux`.
- Reactive controllers or functional routes.
- `springdoc-openapi-starter-webflux-api` or `webflux-ui`.

Do not choose the WebFlux starter just because a service method returns `Mono` or `Flux`. Determine the actual web application type and underlying starter that Spring Boot boots.

An application should use the starter matching its chosen web stack. Avoid putting both MVC and WebFlux starters on the same classpath without an explicitly designed and tested hybrid architecture.

## 4. What Does the API Starter Provide?

The API starter integrates springdoc with Spring to generate the OpenAPI document. Commonly used default endpoints:

~~~text
GET /v3/api-docs
GET /v3/api-docs.yaml
~~~

The JSON document describes:

- OpenAPI version.
- API information in `info`.
- Server URLs.
- Paths and operations.
- Parameters.
- Request bodies.
- Responses and status codes.
- Components and schemas.
- Security schemes and requirements.
- Tags, examples, and extensions.

The API starter does not package the Swagger UI interface. Thus, the application can still provide machine-readable documentation for portals, generators, or testing tools without UI assets.

The API starter does not mean OpenAPI is a static file. The document is still dynamically generated from controllers and configuration at runtime, unless a pipeline explicitly exports it as a static artifact.

## 5. What Additional Capabilities Does the UI Starter Provide?

The UI starter includes OpenAPI document integration and Swagger UI assets. Common default paths:

~~~text
/swagger-ui.html
/swagger-ui/index.html
/v3/api-docs
/v3/api-docs.yaml
~~~

The `/swagger-ui.html` path usually redirects to the actual UI page. Exact URLs can vary based on configuration, context path, or reverse proxy.

Swagger UI allows users to:

- Browse tags and operations.
- View parameters, request bodies, and response schemas.
- View request/response examples.
- Use the Authorize button to enter credentials.
- Test API calls with Try it out.
- Choose a server declared in the OpenAPI document.
- Browse multiple documents if configured.

The UI starter does not replace Spring Security, an authentication server, or API authorization. It only provides an interactive interface for the contract and sends requests to endpoints as configured.

## 6. Differences in Dependency Footprint

The UI starter brings additional dependencies and web resources to serve the interface. Typically the dependency tree includes the `swagger-ui` WebJar along with UI integration components.

The API starter has a smaller footprint because it does not package Swagger UI assets.

| Aspect | API starter | UI starter |
|---|---|---|
| OpenAPI JSON/YAML | Yes | Yes |
| Generate document from Spring | Yes | Yes |
| Swagger UI assets | No | Yes |
| Built-in API browsing page | No | Yes |
| Built-in Try it out | No | Yes |
| Swagger UI WebJar dependency | Not needed | Yes |
| Use with external API portal | Suitable | Still works |
| Suitable for apps only exporting contracts | Suitable | Usually extra dependencies |

Actual size increase depends on versions, dependency management, and packaging. Inspect the dependency tree or executable archive instead of estimating by artifact name.

## 7. When to Choose the API Starter?

Choose the API starter when the application only needs to publish the OpenAPI document for other consumers or pipelines.

Common scenarios:

- CI starts the app, downloads `/v3/api-docs`, and validates the contract.
- OpenAPI Generator uses the document to generate SDKs.
- An organization's centralized API portal reads JSON/YAML from multiple services.
- Documentation is stored in an artifact repository or Git.
- Swagger UI is hosted in a separate web application.
- Production only exposes the contract to controlled internal systems.
- You want to minimize dependencies and do not need an in-service UI.

For example, a microservice can expose OpenAPI JSON via an internal endpoint; a separate API portal handles rendering documentation for developers.

In this model, the service still needs to ensure the document is accurate, versioned, and protected by policy. Having no Swagger UI does not mean the OpenAPI endpoint should be left open publicly by default.

## 8. When to Choose the UI Starter?

Choose the UI starter when users need access to interactive documentation directly inside the Spring Boot application.

Common cases:

- Developers need to test endpoints in a local environment.
- QA needs to view schemas and send manual requests.
- An internal app has a small set of APIs without a centralized portal.
- A demo or sandbox needs an accompanying documentation UI.
- Operations teams need to verify operations and authentication in a test environment.

Built-in UI reduces the effort of deploying a separate documentation site. However, production requires considering who can access the UI, the document, and the described operations.

If the interface is only needed in local/dev, you can enable UI in that profile and disable or exclude UI from the production artifact.

## 9. Maven: API-Only Configuration for Spring MVC

API-only dependency example:

~~~xml
<properties>
    <springdoc.version>2.x.y</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
~~~

Use a version compatible with the Spring Boot version in use. The `2.x.y` placeholder in the example illustrates the springdoc line for Spring Boot 3; for Spring Boot 4, choose the springdoc 3.x line. In either case, replace the placeholder with a specific release managed in the project.

With this configuration, the application can generate OpenAPI JSON/YAML. There is no built-in Swagger UI unless another UI dependency is added.

## 10. Maven: UI Configuration for Spring MVC

If Swagger UI is needed, use the UI artifact:

~~~xml
<properties>
    <springdoc.version>2.x.y</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
~~~

There is no need to also declare `springdoc-openapi-starter-webmvc-api` to get `/v3/api-docs`. The UI starter already provides API document integration.

Do not manually add `org.webjars:swagger-ui` with an arbitrary version if the starter already manages that dependency. Overriding the WebJar can create a mismatch between springdoc and the packaged Swagger UI version.

## 11. Maven: Configuration for Spring WebFlux

API-only:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-api</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

With UI:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Keep `spring-boot-starter-webflux` as the application's web stack. Do not add `spring-boot-starter-web` just to make Swagger UI work; the WebFlux UI starter is built for the corresponding reactive stack.

## 12. Gradle: API-Only and UI Starters

With Gradle Groovy DSL, API-only:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation "org.springdoc:springdoc-openapi-starter-webmvc-api:$springdocVersion"
}
~~~

UI:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation "org.springdoc:springdoc-openapi-starter-webmvc-ui:$springdocVersion"
}
~~~

With Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation(
        "org.springdoc:springdoc-openapi-starter-webmvc-api:$springdocVersion"
    )
}
~~~

To switch to UI, replace the `webmvc-api` artifact with `webmvc-ui`.

Declare the version in a shared place, such as a version catalog or Gradle property. Do not let modules within the same application pull in different springdoc versions.

## 13. Configuring OpenAPI Endpoints

You can change the document path:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~

The default JSON endpoint then becomes:

~~~text
/openapi
~~~

The corresponding YAML endpoint is served according to the path and extension configuration supported by the springdoc version, typically `/openapi.yaml`.

The `springdoc.api-docs.enabled` property controls serving API docs:

~~~yaml
springdoc:
  api-docs:
    enabled: true
~~~

If set to `false`, the OpenAPI endpoint is disabled. Default Swagger UI will then be unable to fetch the document from this endpoint unless configured to read a different OpenAPI URL.

Do not change the path and forget to update CI scripts, the API portal, security matchers, and Swagger UI config.

## 14. Configuring Swagger UI

Interface properties reside under `springdoc.swagger-ui`:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    path: /docs
    operations-sorter: alpha
    tags-sorter: alpha
    display-operation-id: true
~~~

`enabled` turns Swagger UI on or off when the UI starter is present. `path` customizes the UI access path; the sorters control display order.

If using the API-only starter, setting `springdoc.swagger-ui.enabled=true` does not automatically add Swagger UI dependencies or static assets. The configuration only takes effect when the UI components are on the runtime classpath.

You can disable the UI while keeping the OpenAPI endpoint:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: true
~~~

This configuration is useful when using the UI starter in a profile that needs the document without serving the interface. If you want to exclude UI dependencies from the production artifact, using the API starter for the production artifact is clearer.

## 15. Where Does Swagger UI Read the Document From?

By default, built-in Swagger UI reads the OpenAPI document served by the same springdoc application, typically `/v3/api-docs`.

If the UI is hosted separately, it can load the spec from another URL:

~~~yaml
springdoc:
  swagger-ui:
    url: https://docs.example.com/contracts/orders/openapi.json
~~~

When using an external URL, check:

- Whether the browser can reach that host.
- Whether CORS allows downloading the document.
- Whether the URL requires authentication.
- Whether the TLS certificate is valid.
- Whether the spec has server URLs matching the environment to test.

A standalone UI can also read multiple documents via a URL list configuration. An API service does not need to package the UI simply because its documentation is viewed in Swagger UI elsewhere.

## 16. Distinguishing API Docs Endpoints and Swagger UI Endpoints

The two endpoints have different roles:

| Endpoint | Role | Typical Consumer |
|---|---|---|
| `/v3/api-docs` | OpenAPI JSON | Parsers, portals, generators, developers |
| `/v3/api-docs.yaml` | OpenAPI YAML | Reviewers, YAML-supporting tools |
| `/swagger-ui/index.html` | UI resources | Developers, QA |
| `/swagger-ui.html` | Convenience path/redirect | Browser users |

The API starter provides the document endpoints. The UI starter adds the interface paths.

Checking only `/swagger-ui.html` does not prove the OpenAPI JSON is valid. Checking only `/v3/api-docs` does not prove static assets and the UI work.

## 17. Disabling UI in Production

Profiles can be used to control the UI:

~~~yaml
# application-dev.yml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
~~~

~~~yaml
# application-prod.yml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

This configuration keeps the OpenAPI endpoint in production while disabling the UI.

If production does not need runtime OpenAPI endpoints at all, both can be disabled:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

If the pipeline needs a contract artifact, export it during the build/test stage before building the production artifact, or use a dedicated documentation profile/application.

Note: disabling the UI via property does not remove Swagger UI dependencies from the executable JAR if you still package the UI starter. To genuinely reduce the footprint, choose the API starter in the production build.

## 18. Protecting API Docs and Swagger UI

An OpenAPI document can expose:

- Internal paths.
- Operation and schema names.
- Headers and security schemes.
- Server URLs.
- Error models.
- Internal features not intended for public consumers.

Swagger UI also allows users to interact with the API via Try it out. Therefore, access policies must be defined for both the document and the interface.

Ways to protect them:

- Allow access only from the internal network.
- Require authentication for `/v3/api-docs/**`.
- Protect `/swagger-ui/**` and UI paths.
- Use profiles to keep UI disabled in public production.
- Export filtered specs separately for external consumers.
- Exclude administrative endpoints or sensitive information from public documents.

Hiding an operation with `@Hidden` only affects documentation; it does not replace endpoint authorization. Security schemes in OpenAPI also only describe security mechanisms; they do not configure Spring Security automatically.

## 19. Spring Security Matchers Must Cover the Right Endpoints

If the application protects documentation, matchers must match the actual paths. Illustrative configuration example:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers(
            "/v3/api-docs/**",
            "/swagger-ui/**",
            "/swagger-ui.html"
        ).hasRole("API_DOCS")
        .anyRequest().authenticated()
    );

    return http.build();
}
~~~

This is only a policy example. The application must configure authentication, CSRF, and filters appropriate for the actual deployment.

If custom paths like `/openapi` or `/docs` are used, update the matchers accordingly. If the UI is public while JSON docs are protected, Swagger UI may load the page successfully while the request fetching the document gets 401/403.

Do not open all of `/v3/**` or `/swagger-ui/**` to anonymous access just to make the UI work if policy requires authentication.

## 20. Try It Out and CORS

Swagger UI sends requests directly from the user's browser to the API server selected in the document. If the UI and API have different origins, the browser enforces CORS.

Common errors:

- Swagger UI loads, but Try it out fails due to CORS.
- Preflight OPTIONS requests are blocked.
- The Authorization header is not allowed.
- Server URLs in OpenAPI point to internal hostnames.
- The browser does not send cookies due to SameSite or credential policy.

To fix this, configure CORS on the API server or gateway according to actual origins, methods, and headers. Do not use wildcard credentials in production.

The API-only starter has no built-in Try it out, so it does not introduce CORS for an in-service UI. However, external portals/UIs must still comply with CORS when calling the API or loading the document directly from a browser.

## 21. Using the API Starter with a Centralized API Portal

A common architecture is for each service to expose OpenAPI JSON while a separate portal aggregates documentation:

~~~text
orders-service  ---- /v3/api-docs ----+
                                      |
billing-service ---- /v3/api-docs ----+--> API portal
                                      |
catalog-service ---- /v3/api-docs ----+
                                             |
                                      Developer browser
~~~

Services use the API starter. The portal can:

- Periodically fetch specs.
- Receive artifacts from CI.
- Store documents by version.
- Display multiple services in one interface.
- Enforce permissions by team or product.
- Generate SDKs from approved contracts.

This model separates responsibilities: services own the contract; the portal owns the documentation browsing experience.

Avoid letting the portal pull an unstable runtime document and treat it as a release. Tie artifacts to commits, API versions, and validation status.

## 22. Using the API Starter for CI and Code Generation

A pipeline can start the application with a CI profile, download OpenAPI JSON, and run validators/generators:

~~~bash
curl -fsS \
  http://localhost:8080/v3/api-docs \
  -o target/openapi.json
~~~

Then:

~~~bash
openapi-generator-cli validate -i target/openapi.json
~~~

Generate a trial client:

~~~bash
openapi-generator-cli generate \
  -i target/openapi.json \
  -g java \
  -o target/generated-client
~~~

CI does not need to open Swagger UI to perform these steps. The API starter keeps the runtime limited to the document generation parts needed.

If exporting multiple groups, fetch each group endpoint and inspect them independently. If API docs are protected, the pipeline needs credentials from a secret store and must avoid logging tokens.

## 23. Inspecting the Maven Dependency Tree

Use Maven to inspect springdoc and Swagger UI:

~~~bash
mvn dependency:tree \
  -Dincludes=org.springdoc,org.webjars
~~~

With API-only, you should not see the Swagger UI WebJar pulled in solely by the springdoc API starter.

With the UI starter, the dependency tree typically shows the `org.webjars:swagger-ui` artifact or corresponding UI dependency.

If Swagger UI still appears when using the API starter, check whether another dependency pulls it in. Do not judge solely by direct dependency names; inspect the full runtime dependency tree.

## 24. Inspecting Gradle Dependency Insight

With Gradle:

~~~bash
./gradlew dependencyInsight \
  --dependency swagger-ui \
  --configuration runtimeClasspath
~~~

You can inspect the springdoc group:

~~~bash
./gradlew dependencies \
  --configuration runtimeClasspath
~~~

Use the output to identify which dependency pulls Swagger UI onto the runtime classpath. If multiple versions exist, resolve conflicts through proper dependency management rather than arbitrary exclusions.

After swapping starters, run tests and inspect the executable archive to confirm UI assets are no longer in the API-only artifact.

## 25. Inspecting Executable JAR Contents

With a Spring Boot executable JAR, you can check packaged dependencies:

~~~bash
jar tf target/application.jar | findstr /i "swagger-ui"
~~~

If using API-only and no other dependency brings Swagger UI, you typically will not see nested Swagger UI libraries or resources.

With the UI starter, inspect `BOOT-INF/lib` to confirm the WebJar is packaged.

Archive structure depends on build plugins and packaging. Treat the output as a dependency verification check rather than relying on a fixed file name across all versions.

## 26. Smoke Testing the API Starter

With API-only, check the OpenAPI document:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Check YAML:

~~~bash
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

Check JSON contents:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs |
  jq '{openapi, info, pathCount: (.paths | length)}'
~~~

API-only does not need a Swagger UI page test because it provides no interface. Instead, test document endpoints, key schemas, security schemes, and groups.

If the endpoint returns 404, verify the starter matches the web stack, `springdoc.api-docs.enabled`, custom paths, and component scanning before concluding the dependency is broken.

## 27. Smoke Testing the UI Starter

With the UI starter, check both the document and interface:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

~~~bash
curl -I http://localhost:8080/swagger-ui/index.html
~~~

Open the UI URL in a browser and verify:

- The HTML page loads successfully.
- JavaScript/CSS assets do not 404.
- The document URL loads successfully.
- Tags and operations appear.
- Schemas and security schemes display accurately.
- Try it out sends requests to the right server.

If HTML returns 200 but the UI is blank, inspect the browser console and network tab. The cause is usually document URL, security, CORS, or static assets rather than OpenAPI generation.

## 28. Integration Testing for API-Only

WebTestClient example:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OpenApiEndpointTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publishesOpenApiDocument() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.openapi").exists()
            .jsonPath("$.info.title").isNotEmpty()
            .jsonPath("$.paths").exists();
    }
}
~~~

This test verifies the API document endpoint works. If the application uses MVC, MockMvc can be used instead of WebTestClient.

Do not write a test that only checks HTTP 200. Verify critical operations, request schemas, response schemas, and security requirements to catch empty documents or missing metadata.

## 29. Integration Testing for the UI Starter

Server-side tests can verify the UI route:

~~~java
@Test
void servesSwaggerUiEntryPoint() {
    webTestClient.get()
        .uri("/swagger-ui/index.html")
        .exchange()
        .expectStatus().isOk();
}
~~~

Depending on static resource and redirect configuration, you may need to check `/swagger-ui.html` or a custom UI path. An HTTP test does not verify that JavaScript rendered properly in a browser; run a browser smoke test when UI is an important feature.

Keep document tests and UI tests separate so you know whether a failure lies in generation or static assets.

## 30. Switching from UI Starter to API Starter

If currently using the UI starter and you want to serve only the document:

1. Replace `springdoc-openapi-starter-webmvc-ui` with `springdoc-openapi-starter-webmvc-api` or the WebFlux equivalent.
2. Remove unused Swagger UI configuration.
3. Keep necessary `springdoc.api-docs` configuration.
4. Update security matchers if UI paths no longer exist.
5. Verify the portal or CI still downloads `/v3/api-docs`.
6. Inspect the dependency tree to confirm the Swagger UI WebJar is gone.
7. Inspect the executable JAR.
8. Run integration tests for JSON/YAML.
9. Update developer guides to use the portal or external documentation.

Do not delete OpenAPI annotations just because the UI was removed. Annotations and controllers are still required to generate the document.

## 31. Switching from API Starter to UI Starter

If an integrated interface is needed:

1. Replace the API artifact with the UI artifact for the same web stack.
2. Do not keep both API and UI starters simultaneously.
3. Verify dependency versions and the WebJar.
4. Enable `springdoc.swagger-ui.enabled`.
5. Confirm UI and OpenAPI document URLs.
6. Configure authentication/CORS if needed.
7. Ensure server URLs in the spec point to the right environment.
8. Smoke test HTML, assets, and the document.
9. Test Try it out with an authorized endpoint.
10. Update security policy for UI and docs.

There is no need to change controllers, DTOs, or OpenAPI annotations just because the starter changed from API to UI.

## 32. Managing springdoc and Spring Boot Versions

API and UI starters must use the same springdoc version line compatible with Spring Boot.

Common major version selection rules:

| Spring Boot | Typical corresponding springdoc line |
|---|---|
| Spring Boot 4.x | springdoc 3.x |
| Spring Boot 3.x | springdoc 2.x |
| Spring Boot 2.x | springdoc 1.x branch; check support status and upgrade requirements |

This is a major-line guideline. Check the compatibility table and release notes to pick a specific patch/minor, especially when Spring Boot introduces a new minor release.

Do not pair `webmvc-api` from one version with `webmvc-ui` from another version. Do not upgrade swagger-core or the swagger-ui WebJar individually without verifying compatibility with springdoc.

## 33. Avoiding Duplicate Dependencies and Conflicts

Common dependency mistakes:

- Adding both `webmvc-api` and `webmvc-ui`.
- Using both MVC and WebFlux starters unintentionally.
- Keeping Springfox alongside springdoc after migration.
- Manually adding a swagger-ui WebJar with a different version.
- Overriding swagger-core/swagger-annotations outside dependency management.
- Declaring different springdoc versions across modules.

How to check:

~~~bash
mvn dependency:tree -Dverbose
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Resolve conflicts in dependency management or the version catalog. Do not apply blanket exclusions before understanding which dependency requires the excluded class or resource.

## 34. Multi-Module Applications

In a multi-module application, the starter should usually be declared in the module that runs Spring Boot, which owns the ApplicationContext and web server.

Example:

~~~text
orders-parent
  orders-domain
  orders-application
  orders-web
  orders-service
~~~

The `orders-service` or `orders-web` module can own the web and springdoc starters. A domain module containing only business models should not pull in Swagger UI dependencies unnecessarily.

If a shared module holds DTOs with OpenAPI annotations, the annotation dependency can be managed separately, while ensuring uniform versions and avoiding pulling web starters into domain modules.

Do not let each submodule declare a different springdoc starter and create an unpredictable classpath.

## 35. Using an External UI

If an organization has a centralized Swagger UI or API portal, services can use the API-only starter. The external UI fetches the document from the service URL or from an exported artifact.

When an external UI loads directly from the service, consider:

- CORS for the browser origin.
- Authentication of the document endpoint.
- Network route from browser to service.
- Public server URL in OpenAPI.
- TLS and certificates.
- Version of the displayed document.
- Portal and CDN caching.

If the portal fetches the spec via its backend instead of the browser, CORS may not apply to fetching the document, though the portal still must control access permissions and artifact freshness.

## 36. Choosing Artifacts per Environment

A project can choose different starters by build variant or module, while avoiding an inconsistent runtime classpath.

Common patterns:

- **Local development:** UI starter so developers can test APIs.
- **CI export job:** API starter to download and validate the document.
- **Production service:** API starter if runtime docs are needed; disable docs if required by policy.
- **Central documentation portal:** API starter in services and UI in the portal.
- **Public sandbox:** UI starter if a clear protection policy is in place.

If Maven profiles or Gradle configurations swap dependencies by environment, inspect the dependency graph and artifact of each profile. Merely toggling `springdoc.swagger-ui.enabled` does not replace picking the right dependency if the goal is reducing package size.

## 37. Common Issues

| Symptom | Causes to Check |
|---|---|
| `/v3/api-docs` works but Swagger UI 404s | Using API starter or UI is disabled |
| `swagger-ui.enabled=true` but no UI | Property does not automatically add UI dependency |
| UI loads but shows no operations | Wrong document URL, docs blocked, or JSON error |
| UI HTML 200 but JavaScript/CSS 404 | Static assets or wrong reverse proxy path |
| API starter still contains Swagger UI WebJar | Another dependency pulls the WebJar in |
| Both API and UI starters added | Redundant dependency or version conflict |
| UI API calls hit CORS | Browser origin differs from API origin |
| UI returns 401 when fetching document | Security matcher protects docs without UI credentials |
| `/v3/api-docs` 404s | Wrong web stack starter, custom path, or api-docs disabled |
| YAML endpoint 404s | Endpoint config or version needs checking |
| API portal displays stale spec | Portal cache or artifact not yet updated |
| Production UI still packaged despite disable | UI starter still present in runtime dependencies |
| MVC/WebFlux beans behave unexpectedly | Chosen starter mismatches application type |
| Boot upgrade breaks springdoc | Wrong major line or incompatible patch |

## 38. Decision Workflow

Before adding dependencies, answer in order:

1. Does the application use Spring MVC or WebFlux?
2. Are OpenAPI JSON/YAML endpoints needed?
3. Do users need Swagger UI directly inside the service?
4. If UI is included, is it only for local/dev or also production?
5. Is there a centralized API portal or external UI?
6. How are docs endpoints and the UI protected?
7. Is reducing runtime dependency footprint necessary?
8. Which springdoc major line corresponds to the Spring Boot version?
9. At which step will CI export and validate the document?
10. Which tests verify the document and UI separately?

If only a machine-readable contract is needed, choose the API starter. If an embedded interface is needed, choose the UI starter. If a separate portal already exists, there is usually no need to package Swagger UI inside every microservice.

## 39. Pre-Release Checklist

- [ ] Spring MVC or WebFlux web stack identified.
- [ ] Correct API or UI artifact selected.
- [ ] API and UI starters for the same stack not added simultaneously.
- [ ] springdoc version compatible with Spring Boot.
- [ ] No leftover Springfox or redundant Swagger UI WebJar.
- [ ] API-only still serves OpenAPI JSON/YAML as required.
- [ ] UI starter serves the right page and static assets.
- [ ] `springdoc.api-docs.enabled` matches policy.
- [ ] `springdoc.swagger-ui.enabled` set properly per environment.
- [ ] Security matchers protect docs and UI per policy.
- [ ] Server URL and reverse proxy paths are accurate.
- [ ] CORS configured if UI calls an API on a different origin.
- [ ] CI downloads and validates the OpenAPI document.
- [ ] Group documents verified if configured.
- [ ] Dependency tree and executable archive inspected.
- [ ] Separate tests exist for API docs and Swagger UI.
- [ ] Hiding UI is not treated as an API security measure.

## 40. References

- [springdoc-openapi – Documentation](https://springdoc.org/)
- [springdoc-openapi – Getting Started](https://springdoc.org/#getting-started)
- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html)
- [springdoc-openapi – FAQ](https://springdoc.org/faq.html)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Swagger UI – Usage](https://swagger.io/docs/open-source-tools/swagger-ui/usage/installation/)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Spring Boot – Managing Dependencies](https://docs.spring.io/spring-boot/reference/using/build-systems.html)

Both API starters and UI starters generate OpenAPI documents; UI starters add Swagger UI assets and interface routes. Choose API-only when contracts are consumed by CI, SDK generators, or a centralized portal. Choose UI when browsing and testing APIs directly inside the service is needed. Always match the starter to MVC/WebFlux, manage versions according to Spring Boot, inspect the dependency tree, and separately protect both document endpoints and the interface.
