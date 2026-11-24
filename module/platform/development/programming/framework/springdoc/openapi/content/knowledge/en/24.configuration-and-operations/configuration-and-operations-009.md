# Preloading, Caching, and Document Update Timing

springdoc-openapi builds the OpenAPI specification from the application's controllers, models, annotations, and configuration. This analysis can take noticeable time when a system has many endpoints, nested schemas, customizers, or multiple document groups. If the document is generated only upon the first request, users may experience slow latency the first time Swagger UI is opened after application startup.

springdoc provides two related mechanisms: **preloading** to load the document during application startup and **caching** to retain the computed OpenAPI result for subsequent requests. Understanding both is important because they affect when generation cost occurs, memory usage, per-locale content, and whether request-dependent details are reflected.

This article explains how to enable preloading, choose locales, manage caching, handle documents that vary per request or proxy, and verify behavior via OpenAPI endpoints and integration tests.

## 1. Why Are Preloading and Caching Needed?

OpenAPI generation typically involves:

1. Scanning Spring controllers and mappings.
2. Parsing annotations such as @Operation, @Parameter, @Schema, and @ApiResponse.
3. Resolving request/response types and generic types.
4. Building components, schemas, security schemes, and references.
5. Applying OpenApiCustomizer, OperationCustomizer, or per-group configuration.
6. Producing the final document to return as JSON or YAML.

If the application computes the document only when `/v3/api-docs` is first requested, that request bears the entire initialization cost. Caching retains the computed result so subsequent requests do not rebuild the document under identical conditions.

Preloading shifts part of document-generation work to application startup. When a user opens the documentation after the application becomes ready, the document may already be preloaded.

The two mechanisms address two different points in time:

| Mechanism | Primary Effect | Trade-off |
|---|---|---|
| Preloading | Generates OpenAPI during startup | Startup may take longer |
| Caching | Reuses the computed document | Uses memory and may hold stale content if inputs change at runtime |
| Disabling cache | Recomputes the document per request | Increases CPU and latency on every fetch |
| Preloading multiple locales | Prepares documents for multiple languages | Increases startup time and amount of retained data |

Do not enable every option simply because it exists. Base your choice on endpoint count, locale count, group count, and whether server URLs or metadata depend on the request.

## 2. Enabling Preloading at Application Startup

The springdoc.pre-loading-enabled property controls preloading of the OpenAPI document. The default value is false.

application.yml:

~~~yaml
springdoc:
  pre-loading-enabled: true
~~~

Or application.properties:

~~~properties
springdoc.pre-loading-enabled=true
~~~

When enabled, springdoc loads OpenAPI during application startup rather than waiting for the first documentation request. This is helpful when:

- The API has many controllers or complex schemas.
- Swagger UI is opened immediately after deployment completes.
- You want to detect OpenAPI generation errors early during startup.
- You want to move computation cost away from the first user request.
- The application has readiness checks requiring documentation to be ready before receiving traffic.

Preloading does not make document generation free. The cost is shifted to startup, so measure startup duration and CPU/memory usage after enabling it.

## 3. Selecting Locales to Preload

If documentation is translated based on Accept-Language or i18n configuration, you can specify which locales to load via springdoc.pre-loading-locales.

Example:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales:
    - vi-VN
    - en-US
    - ja-JP
~~~

application.properties:

~~~properties
springdoc.pre-loading-enabled=true
springdoc.pre-loading-locales=vi-VN,en-US,ja-JP
~~~

If pre-loading-locales is not specified, springdoc preloads using the application's default Locale. When providing a list, choose only locales that are actually published and translated.

The document's locale is typically chosen from the Accept-Language header when a client fetches OpenAPI. Example:

~~~bash
curl -H "Accept-Language: vi-VN" \
  http://localhost:8080/v3/api-docs
~~~

And:

~~~bash
curl -H "Accept-Language: en-US" \
  http://localhost:8080/v3/api-docs
~~~

For outputs to differ, the application must have corresponding metadata or i18n configuration. Sending Accept-Language alone does not automatically translate hardcoded descriptions in annotations.

Do not preload dozens of unused locales. Each document variant takes time to build and can occupy a cache slot.

## 4. Distinguishing Preloading from Caching

Preloading and caching are often used together, yet they are not the same concept:

- Preloading decides when the document is generated.
- Caching decides whether the generated result is retained for reuse.

springdoc's default cache setting is enabled. You can leave the default intact:

~~~yaml
springdoc:
  cache:
    disabled: false
~~~

Or omit springdoc.cache.disabled if no special behavior is needed.

When caching is active, springdoc keeps the computed OpenAPI result to serve subsequent requests. According to the official FAQ, the OpenAPI description is computed once and cached by default; caching can be disabled when server URLs must be recomputed per request, such as when the same Swagger UI is served behind both internal and external proxies.

If preloading is enabled while caching is disabled, the document may still be built at startup, yet subsequent requests will not benefit from cache reuse as they do when caching is enabled. Verify the actual cost of combined settings on your version.

## 5. Disabling Cache When Documentation Depends on the Request

In some systems, OpenAPI document content depends on the current request. For example:

- Server URL is inferred from the request's host and scheme.
- The application is accessed across multiple domains.
- Reverse proxies add different path prefixes.
- A customizer builds metadata per tenant or context.
- Document content varies with the request's locale.

If the cache retains a document created from the first request, later requests could receive a server URL or metadata inappropriate for the current request.

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

When caching is disabled, springdoc recomputes the OpenAPI document per request instead of serving a stored cached result. This allows request-dependent values to stay current, but also increases CPU usage and latency on every documentation fetch.

Disable caching only for a concrete reason. If the document is identical across all requests, keeping the cache enabled is usually much more efficient.

## 6. Caching by Locale and Accept-Language

For multilingual documentation, the cache must distinguish the requested locale. springdoc stores one description per locale requested via Accept-Language.

Example:

| Request Header | Document Variant |
|---|---|
| Accept-Language: vi-VN | Vietnamese document |
| Accept-Language: en-US | English document |
| Accept-Language: ja-JP | Japanese document |

If caching does not distinguish locales, users can receive the wrong language content. Therefore, check both the request headers and the returned descriptions.

Configuring pre-loading-locales prepares the chosen locales ahead of time. Caching continues managing requested variants. Preloading locales does not replace configuring translations and does not guarantee every locale has complete translations.

If the application does not use i18n, do not declare multiple locales just to enlarge the cache.

## 7. Limiting the Number of Cached Documents

Newer springdoc versions provide springdoc.cache.max-entries to cap how many OpenAPI descriptions are kept in the cache.

Example:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 100
~~~

Or:

~~~properties
springdoc.cache.disabled=false
springdoc.cache.max-entries=100
~~~

According to current configuration documentation, max-entries defaults to 100. Each entry corresponds to a requested locale; when the limit is exceeded, the least recently used entry is evicted under an LRU policy.

The max-entries property was added in newer release lines: springdoc 2.x docs record it from 2.9.1 and 3.x docs record it from 3.1.1. If your project uses an older version, consult the matching reference before configuring it; do not assume every version supports this property.

The value 100 is the default documented by current releases, not an optimal figure for every application. Choose the limit based on actual locale count, cached document count, and memory allocated to the application.

## 8. Preloading Multiple Locales Can Slow Startup

Suppose an application supports three locales: vi-VN, en-US, and ja-JP. When preloading is enabled for all three, springdoc must prepare the corresponding documents as configured.

If the application has many groups, large schemas, and heavy customizers, total preparation time can grow. Consider:

- The number of locales actually supported.
- The number of published OpenAPI groups.
- Schema sizes and operation counts.
- Customizer workload.
- Memory allocated for computed documents.
- Deployment readiness timeouts.
- Number of instances starting concurrently during rollouts.

Do not preload locales the application does not serve. If only Vietnamese documentation exists, configure the appropriate default Locale or that specific locale instead of creating unnecessary copies.

## 9. Preloading and Application Readiness

In Kubernetes or orchestration platforms, startup and readiness are distinct milestones.

Preloading generates documents during startup. However, readiness probes must be designed around the state the application truly guarantees. Do not assume every preload configuration automatically makes health endpoints wait until every document/group/locale is ready in the exact manner desired.

A practical verification approach:

1. Enable preloading in the deployment profile.
2. Start the application with startup logs captured.
3. Measure time from process start to readiness.
4. Once ready, call /v3/api-docs.
5. Compare first-request latency with preloading enabled vs. disabled.
6. Verify each preloaded locale.
7. Verify grouped documents if the application has multiple groups.

Preloading pays off when document generation time noticeably impacts the first request. If the document is small and the first request has negligible latency, preloading may not justify the added startup time.

## 10. Recommended Configuration for Development

In local or development environments, you can prioritize fast documentation opening and easy testing:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales:
    - vi-VN
    - en-US
  cache:
    disabled: false
~~~

If the application has many locales while you are testing only one language on a given day, trim the preload list for faster startup.

When changing controllers, DTOs, or annotations, restart the application to reload the updated structure unless a dedicated refresh mechanism is in place. Saving a Java or YAML file in the IDE does not automatically update the cached document of a running process.

## 11. Recommended Configuration for Production

For production environments with a stable public hostname where documentation rarely changes within a process lifecycle, you can normally keep caching enabled:

~~~yaml
springdoc:
  pre-loading-enabled: true
  cache:
    disabled: false
~~~

You can preload the default locale or the list of locales actually served.

If server URLs are derived from incoming requests and the same application is accessed through multiple proxies/hostnames, consider disabling caching:

~~~yaml
springdoc:
  pre-loading-enabled: false
  cache:
    disabled: true
~~~

This is an illustrative configuration for request-dependent URLs. Disabling caching means documents may be recomputed on every request, so load-test before rolling out broadly.

If the public URL is fixed, an alternative is declaring `servers` explicitly so the document does not depend on the request host. You can then keep caching enabled.

## 12. When Does Documentation Change?

The OpenAPI document is generated from metadata inside the running application. Common sources include:

- Controller mappings.
- DTOs and generic types.
- OpenAPI annotations.
- OpenApiCustomizer and OperationCustomizer.
- GroupedOpenApi configurations.
- Properties and profiles.
- Locale or request metadata if supported by the application.

When source code or configuration changes, the application process usually needs a restart or redeployment to load the new metadata. Caching is not a file watcher that automatically updates on source edits.

When documents are cached, the computed result can persist for the lifetime of the process. Therefore, after updating controllers, schemas, or annotations, verify that the application restarted with the new artifact and generated the updated document.

Do not treat calling /v3/api-docs again as a cache-refresh operation. With caching enabled, requests can return the previously computed document.

## 13. Updating OpenAPI in a Running Application

If an application has dynamic metadata that changes at runtime, determine the document generation strategy:

- If the document is derived from fixed controller/annotation structures, deploying a new artifact and restarting is the standard update path.
- If a customizer reads dynamic data, determine whether that data changes per request.
- If server URLs or content depend on the request, consider disabling caching.
- If data changes only with environment configuration, a restart/redeploy may be required when configuration changes.
- If documentation must update live inside a running process without restarting, there must be a clearly supported mechanism to update the OpenAPI model/cache; do not assume springdoc detects changes automatically.

Avoid building custom cache-clearing endpoints that reach into internal non-public beans. Such approaches are implementation-dependent and prone to breaking across upgrades.

## 14. springdoc Cache Is Not HTTP Cache or CDN Cache

springdoc.cache.disabled controls the internal cache of the computed document. It does not configure HTTP Cache-Control, browser caches, or CDN caches.

Distinguish them as follows:

| Cache Type | Where Stored | Effect |
|---|---|---|
| springdoc OpenAPI cache | Inside application process | Reuses computed OpenAPI model |
| HTTP cache | Browser or intermediary via HTTP headers | May reuse HTTP responses |
| CDN/reverse proxy cache | Intermediate infrastructure | May serve cached responses at the edge |
| Build artifact | CI/CD or artifact repository | Stores spec files exported at build time |

Disabling springdoc's cache does not clear responses already cached by a CDN. Conversely, setting Cache-Control: no-store on HTTP responses does not necessarily disable springdoc's internal cache.

If the document varies by Accept-Language, HTTP caches and proxies must handle Vary: Accept-Language properly. If the document depends on host or forwarded headers, key caches by host and ensure intermediaries do not serve one domain's document to another domain.

## 15. Combining Preloading with Multiple GroupedOpenApi Beans

An application may expose multiple grouped documents, such as public, partner, and admin:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .build();
}

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .build();
}
~~~

These documents are typically accessed via:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
~~~

Each group can have distinct operations, components, and customizers. When an application defines multiple groups, check each group's endpoint rather than checking only the default /v3/api-docs.

Do not assume preloading a default document proves every group and locale has been prepared as required by your application. Verify the live documentation URLs after startup and measure access times for each group.

If a group uses expensive customizers, measure it separately because generation cost can vary across documents.

## 16. Caching and Reverse-Proxy-Dependent Server URLs

An important case is serving the same Swagger UI through multiple hostnames or proxies. Server URLs may be inferred by springdoc from the request.

Example:

~~~text
Request A:
https://api.example.com/v3/api-docs

Request B:
https://partner.example.com/v3/api-docs
~~~

If the document is built from request A and cached, request B may receive the server URL for api.example.com. This causes Swagger UI on the partner domain to call the wrong host.

springdoc's official FAQ highlights this scenario and recommends disabling caching so the server URL is recomputed on each HTTP request:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Before disabling caching, verify that the proxy sends accurate Forwarded or X-Forwarded-* headers and that Spring Boot processes forwarded headers. Disabling cache does not fix incorrect host/proto/prefix headers; it simply tells springdoc to recompute the document from the current request.

If the application has a single public URL, you can declare `servers` explicitly and keep caching enabled to reduce overhead.

## 17. Sizing Cache Limits to Match Locales

If your version supports springdoc.cache.max-entries, pick a limit based on locale count and actual usage.

For example, an application serving three locales regularly:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 10
~~~

The value 10 here is an illustrative limit, not a fixed recommendation. If requests carry many varied Accept-Language headers or clients send unnormalized locale variants, the cache may accumulate more entries than expected until hitting the cap.

Recommendations:

- Normalize accepted locales.
- Publish only languages with translated content.
- Monitor request counts by Accept-Language.
- Size max-entries adequately for active locales.
- Verify eviction behavior when exceeding the limit.
- Check property support for your springdoc version.

Do not increase max-entries unboundedly to avoid eviction. Each document can hold many schemas and operations, so memory footprint depends substantially on the API size.

## 18. Checking Configuration in application.yml and application.properties

YAML configuration:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales:
    - vi-VN
    - en-US
  cache:
    disabled: false
    max-entries: 20
~~~

Equivalent properties configuration:

~~~properties
springdoc.pre-loading-enabled=true
springdoc.pre-loading-locales=vi-VN,en-US
springdoc.cache.disabled=false
springdoc.cache.max-entries=20
~~~

Spring Boot configuration sources can override one another, including:

- application.yml.
- application-{profile}.yml.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Config servers or secret/config management systems.

If behavior diverges from expectations, check the active profile and final effective configuration values. You can use Actuator env/configprops in a secured environment to inspect bound properties; never expose these management endpoints publicly to unauthorized users.

## 19. Verifying Preloading and Caching with curl

After starting the application, call the OpenAPI endpoint:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Verify locales:

~~~bash
curl -i \
  -H "Accept-Language: vi-VN" \
  http://localhost:8080/v3/api-docs
~~~

And:

~~~bash
curl -i \
  -H "Accept-Language: en-US" \
  http://localhost:8080/v3/api-docs
~~~

Compare:

- Does the response return a success status?
- Is Content-Type application/json?
- Are descriptions/summaries in the expected language?
- Does the Server URL have the right hostname and prefix?
- Do all groups include expected paths and schemas?

You can save documents to compare:

~~~bash
curl -fsS -H "Accept-Language: vi-VN" \
  http://localhost:8080/v3/api-docs -o openapi-vi.json

curl -fsS -H "Accept-Language: en-US" \
  http://localhost:8080/v3/api-docs -o openapi-en.json
~~~

Do not judge whether caching is enabled or disabled solely by request timing. Latency also depends on JVM warm-up, network, proxies, and system load. Combine logs, effective configuration, and repeated measurements.

## 20. Measuring Startup Time and First-Request Latency

To evaluate preloading, compare two runs with identical data and environments:

| Metric | Preloading Disabled | Preloading Enabled |
|---|---|---|
| Startup duration | Usually less OpenAPI generation work | May increase due to upfront document generation |
| First /v3/api-docs request | May pay document computation cost | May be faster if document was preloaded |
| Subsequent requests with cache on | Uses cached result | Uses cached result |
| Memory | Depends on documents created upon access | May rise earlier because documents are built at startup |

These are trends to measure, not millisecond guarantees. Results depend on controller count, schemas, locales, groups, and customizers.

Use the same profile, JVM options, dataset, and iteration count. Discard cold first runs if isolating JIT or class-loading costs. Record both startup duration and p50/p95 latencies of documentation requests.

## 21. Testing the OpenAPI Document with WebTestClient or MockMvc

You can write integration tests verifying documentation endpoints still work after enabling preloading:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OpenApiPreloadingTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void servesOpenApiAfterApplicationStartup() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.openapi").exists()
            .jsonPath("$.paths").exists();
    }
}
~~~

If multiple locales are supported, test each separately:

~~~java
@Test
void servesVietnameseOpenApi() {
    webTestClient.get()
        .uri("/v3/api-docs")
        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi-VN")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.info.title").isNotEmpty();
}
~~~

To prove translated content, assert on a translated description or summary rather than only checking that info.title exists.

This test verifies endpoints and content; it does not directly measure whether preloading occurred during startup. To verify performance gains, benchmark startup and first-request latency in the same environment.

## 22. Testing Grouped Documents and Locales

If the application has public and partner groups, write tests for each endpoint:

~~~java
@Test
void servesPublicGroup() {
    webTestClient.get()
        .uri("/v3/api-docs/public")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.paths").exists();
}

@Test
void servesPartnerGroup() {
    webTestClient.get()
        .uri("/v3/api-docs/partner")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.paths").exists();
}
~~~

If locale affects each group, combine Accept-Language tests with group endpoints. You do not need to test every possible combination if the application does not publish them; prioritize groups and locales with actual consumers.

If groups have distinct security rules or customizers, test their content and access controls as well.

## 23. Updating Documentation After Code Changes

A typical deployment cycle is:

1. Modify controllers, DTOs, annotations, or customizers.
2. Run unit tests and OpenAPI contract tests.
3. Build a new application artifact.
4. Deploy and start the new process.
5. Springdoc generates/preloads documents per configuration.
6. Verify /v3/api-docs and groups.
7. Verify locales and server URLs.
8. Compare OpenAPI diff against the previous release.
9. Publish the spec to clients or the API portal.

With caching enabled, the new process maintains a fresh cache for its lifecycle. Never try to carry over stale caches across deployments when the goal is documentation reflecting updated source code.

If only external configuration changes without restarting, verify whether Spring Cloud Config or your refresh mechanism updates the beans and documents. Never assume every property change causes springdoc to regenerate documentation automatically.

## 24. Common Issues

| Symptom | Cause to Investigate |
|---|---|
| First Swagger UI request is slow | Document is built only on first request and cache was not populated |
| Startup slows down after enabling preload | OpenAPI generation work moved to startup |
| English locale still receives Vietnamese descriptions | Translations not configured or Accept-Language not handled as expected |
| New locale missing from preload cache | Not added to pre-loading-locales or default Locale is used |
| Spec host is wrong behind reverse proxy | Cache holds server URL from an earlier request or forwarded headers are misconfigured |
| Requests remain slow after disabling cache | OpenAPI generation cost still exists and recurs on every request |
| Stale documentation after editing controller | Process was not redeployed or cache still holds old document |
| Public group is right while partner group is wrong | Checked only default document, overlooking individual groups |
| max-entries has no effect | springdoc version does not support property yet or config was not bound |
| Preloading did not improve first request | Cache is disabled, document was not preloaded as expected, or latency is dominated elsewhere |
| Memory rises when preloading many locales | Each document variant consumes memory |
| CDN still serves old document after disabling springdoc cache | HTTP/CDN cache is a separate layer |

## 25. Configuration Selection Workflow

You can use this workflow to pick settings:

1. Determine whether the document is large or expensive to generate.
2. Measure first OpenAPI request latency after startup.
3. If the first request is slow, test enabling pre-loading-enabled.
4. If using i18n, specify the exact pre-loading-locales.
5. Keep caching enabled when the document is invariant across requests.
6. Disable caching only when server URLs or metadata genuinely depend on the request.
7. Size cache.max-entries according to locale count and supported versions.
8. Re-measure startup, first request, subsequent requests, and memory.
9. Verify every group and locale.
10. Include documentation tests and contract validation in CI.

Do not disable caching merely to make documentation update after every build. Deploying a new process when source changes is the standard update mechanism. Do not enable preloading if document generation time does not affect user experience and startup budgets are tight.

## 26. Checklist

- [ ] Measured OpenAPI generation time and first-request latency.
- [ ] Determined whether springdoc.pre-loading-enabled is needed.
- [ ] If preloading multiple languages, declared appropriate pre-loading-locales.
- [ ] If no locales are declared, understood the document uses the default Locale.
- [ ] Understood caching is enabled by default.
- [ ] Disabled springdoc.cache.disabled only when documentation depends on the request.
- [ ] Distinguished springdoc cache from HTTP/CDN caches.
- [ ] Verified caching across Accept-Language headers.
- [ ] Confirmed version support for springdoc.cache.max-entries.
- [ ] Sized max-entries appropriately for locale count and memory.
- [ ] Measured preloading's impact on startup/readiness.
- [ ] Verified every GroupedOpenApi document.
- [ ] Verified server URLs behind proxies when multiple hostnames exist.
- [ ] Redeployed the process when source metadata changed.
- [ ] Tested OpenAPI JSON via integration tests.
- [ ] Included validators and spec diffs in CI if the API requires contract governance.

## 27. References

- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html)
- [springdoc-openapi FAQ – Cache and server URLs](https://springdoc.org/faq.html)
- [springdoc-openapi v2 Configuration Properties](https://springdoc.org/v2/properties.html)
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot – Application Startup and Lifecycle](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)

Preloading governs when springdoc creates the OpenAPI document; caching governs whether the result is reused. Enabling preloading can reduce first-request documentation latency at the expense of startup time. Keep caching enabled when the document is stable; disable caching when server URLs or metadata depend on the request. For multilingual documentation, manage Accept-Language, preloaded locale lists, and version-appropriate cache limits. Always benchmark startup, first request, subsequent requests, and verify each group before finalizing production configuration.
