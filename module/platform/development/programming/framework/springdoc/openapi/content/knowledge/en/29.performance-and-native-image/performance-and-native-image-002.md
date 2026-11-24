# Initial Document Generation Cost and Subsequent Reads

Springdoc does not merely serve a static OpenAPI file. From controllers, DTOs, annotations, Spring configuration, and Jackson, the library must build an OpenAPI model before returning JSON/YAML to the client. This construction work can take time when an application has many endpoints, nested schemas, multiple groups, or complex customizers.

In the default configuration, Springdoc computes the OpenAPI description and caches the result. As a result, the initial generation typically incurs a higher cost than subsequent reads. Subsequent requests still require HTTP processing and response serialization, but they can reuse the computed OpenAPI model instead of re-analyzing all controllers and schemas.

## 1. Two Phases: Cold Generation and Warm Read

The document lifecycle can be visualized as follows:

~~~text
Application starts
       |
       v
Spring Boot registers controllers, beans, and mappings
       |
       v
Client requests OpenAPI for the first time
       |
       v
Springdoc analyzes endpoints, annotations, DTOs, and schemas
       |
       v
OpenApiCustomizer / OperationCustomizer finalizes the model
       |
       v
OpenAPI model is cached
       |
       v
Subsequent requests retrieve the model from cache
       |
       v
Serialize JSON/YAML and send response
~~~

The two phases have different characteristics:

| Phase | Main Work | Typical Cost |
| --- | --- | --- |
| Cold generation | Analyzing mappings, annotations, generic types, DTOs, validation, Jackson, and customizers | CPU, reflection, object allocation, and higher latency |
| Warm read | Retrieving the cached OpenAPI model, serializing the response, and transmitting over HTTP | Lower, though serialization, security, and network costs remain |

Do not treat warm reads as free operations. A document with thousands of operations or large schemas still produces a substantial response that must be serialized and transmitted over the network on every fetch.

## 2. How Does Springdoc Build the Document Initially?

When the document is requested and no suitable cached copy exists, Springdoc must gather information from the application:

1. Read handler mappings and identify matching controllers/operations.
2. Analyze annotations such as @Operation, @Parameter, @ApiResponse, @Schema, and @SecurityRequirement.
3. Resolve data types, generics, nested DTOs, collections, enums, and schema relationships.
4. Read metadata from Jackson, Bean Validation, and enabled model converters.
5. Apply OperationCustomizer, OpenApiCustomizer, and group configurations.
6. Finalize the OpenAPI model before serializing it to JSON/YAML.

The more endpoints and complex schemas an application has, the greater the amount of metadata that must be analyzed. Customizers that perform additional business logic or call external services also increase construction time.

With the standard lazy configuration, the first request to the OpenAPI endpoint may be where users notice this cost. If preloading is enabled, this work is shifted to the application startup phase.

## 3. How Do Subsequent Requests Use the Cache?

Under the default configuration, Springdoc computes the OpenAPI description once and caches the result. When a client requests the same document with the same computed locale, Springdoc can reuse the cached model.

Example:

~~~text
GET /v3/api-docs
    -> Compute OpenAPI model and store in cache

GET /v3/api-docs
    -> Use cached model

GET /v3/api-docs
    -> Use cached model
~~~

Caching avoids repeating the work of analyzing controllers, annotations, and schemas on every request. Even so, each response still passes through the HTTP stack and may need to serialize the OpenAPI model to JSON/YAML.

Swagger UI typically loads multiple resources such as the UI page, swagger-config, and the OpenAPI document. When a user reopens the interface, document requests can still occur; Springdoc's backend cache reduces model creation costs but does not replace HTTP, browser, or CDN caching.

## 4. Default Cache Configuration

Commonly used cache properties:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 100
~~~

Meaning:

| Property | Default Value | Role |
| --- | --- | --- |
| springdoc.cache.disabled | false | OpenAPI description caching is enabled |
| springdoc.cache.max-entries | 100 since Springdoc 2.9.1 | Limits the number of cached descriptions by locale |

When caching is enabled, Springdoc can serve the already-computed document. Starting from Springdoc 2.9.1, the number of cached descriptions is bounded; when the limit is exceeded, the least recently used entry can be evicted under an LRU policy.

The max-entries property should be checked against the Springdoc version in use. If the project runs a 2.x version older than 2.9.1, do not assume this property exists or has the same behavior.

## 5. Caching by Locale and Accept-Language

Springdoc supports localized documentation content. Requests can include an Accept-Language header to choose the description language:

~~~http
GET /v3/api-docs
Accept-Language: vi
~~~

Another request might ask for English:

~~~http
GET /v3/api-docs
Accept-Language: en
~~~

Springdoc caches descriptions by requested locale. Consequently, an application supporting multiple languages can generate multiple distinct OpenAPI model copies. When bounding the cache, consider the number of locales clients actually use.

If serving only one language, there is no need to configure preloading for multiple locales. If supporting multiple locales, inspect cache entry counts and memory after those languages are accessed.

## 6. Limiting the Number of Cache Entries

Example configuration:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 20
~~~

Lowering max-entries limits the number of OpenAPI descriptions retained in the cache, but can cause rarely used locales to be evicted and recomputed on the next request. Raising the limit can reduce recomputations at the expense of additional memory.

Do not increase max-entries solely because you observe cache misses. First determine how many locales the application has, whether there are multiple document groups, and how actual requests are distributed.

## 7. Preloading: Shifting the Cost to Startup

If you do not want the first user to wait for Springdoc to build the documentation, you can enable preloading:

~~~yaml
springdoc:
  pre-loading-enabled: true
~~~

Preloading instructs Springdoc to load the OpenAPI documentation when the application starts. As a result, the documentation can be ready before clients send the first request.

Preloading changes when the cost occurs:

| Without Preload | With Preload |
| --- | --- |
| Lighter startup regarding documentation generation | Startup consumes extra time and CPU to generate documentation |
| First OpenAPI request may be slow | First OpenAPI request typically avoids cold generation |
| Document is generated on demand | Document is generated eagerly at application startup |

Preloading does not eliminate OpenAPI construction cost. It only shifts the cost from the first request to startup. If the document is large, measure startup and readiness times before enabling it on every instance.

## 8. Preloading Multiple Locales

You can specify a list of locales to load at startup:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales:
    - vi
    - en
~~~

If pre-loading-locales is not specified, Springdoc preloads using the default locale. The locale list should be limited to languages the application actually publishes.

Preloading many locales can lengthen startup and consume additional initial CPU/memory because multiple content versions must be prepared. Measure with the system's real locale count, and do not add fallback languages if no clients use them.

## 9. Multiple GroupedOpenApi Beans Increase the Documents to Prepare

An application can define multiple groups such as public, partner, and internal:

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

Each group has its own set of operations and schemas to describe. As the number of groups grows, document construction cost and cache size can increase accordingly. If each group also supports multiple locales, the total number of document variants must be accounted for when measuring performance.

Only create groups when they serve a clear purpose such as separating audiences, security boundaries, or API lifecycles. Do not split documentation into too many small groups if they only differ by a few tags without a practical consumption need.

## 10. When Should Caching Be Disabled?

Caching can be disabled via:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

When caching is disabled, Springdoc recomputes the OpenAPI description instead of using a precomputed cached copy. This can be useful when the server URL or content must be computed per HTTP request, for example when the same Swagger UI is served through multiple internal and external proxies with different hosts/schemes.

Disabling caching increases CPU usage and latency for every documentation request, especially when the OpenAPI spec has many operations/schemas or heavy customizers. Do not turn it off merely to fix proxy URLs if forwarded headers or an explicit server URL can be configured more cleanly.

Consider the following:

- Use an explicit server URL via @OpenAPIDefinition if the contract has a fixed address.
- Configure the reverse proxy and forwarded headers properly if the URL depends on the public host/scheme.
- Use the default cache if the documentation is stable throughout the application lifecycle.
- Only disable caching when results genuinely need to differ per request.

## 11. Customizers Can Increase Cold Generation Cost

OperationCustomizer and OpenApiCustomizer are very useful for adding metadata, but the logic inside them also lies on the document generation path.

For example, a customizer should not query a database or external service for every operation:

~~~java
@Bean
OpenApiCustomizer apiCustomizer() {
    return openApi -> {
        // Only modify metadata in the OpenAPI model.
        openApi.getInfo().setDescription("Public API documentation");
    };
}
~~~

Keep customizers:

- Deterministic for a given configuration.
- Free of unnecessary HTTP or database calls.
- Free of repeated classpath scanning or reading large files.
- Free of creating excessively large intermediate objects per operation.
- Modifying only the metadata parts actually needed.

If static configurations or catalogs must be read, load them once into an appropriate bean and reuse them. If a customizer requires dynamic per-request data, evaluate its impact on caching and determine whether that data truly belongs in the OpenAPI contract.

## 12. Schema Size and Scan Scope

Large documents generally incur higher generation and serialization costs. Common factors that increase size include:

- Many controllers and operations included in the document.
- DTOs with many properties, generics, or nested relationships.
- Polymorphic schemas, oneOf/anyOf/allOf, and recursive references.
- Many examples or lengthy descriptions.
- Many response status codes and media types.
- Many customizers adding extensions or schemas.

You can restrict the scan scope via configuration:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.api
  paths-to-match:
    - /api/**
  packages-to-exclude:
    - com.example.internal
  paths-to-exclude:
    - /internal/**
~~~

Restricting the scan can reduce the number of operations to process and make the document more concise. However, only exclude endpoints that do not belong to the published contract; do not use filters to hide sensitive endpoints in place of runtime security.

## 13. Distinguishing OpenAPI Caching from HTTP Caching

Springdoc caches the computed OpenAPI model. This is an application-side cache, not synonymous with HTTP response caching.

| Cache Layer | What Does It Store? | Impact |
| --- | --- | --- |
| Springdoc cache | Computed OpenAPI description | Avoids re-analyzing controllers/schemas |
| HTTP/browser cache | JSON/YAML response or Swagger UI assets | Can reduce requests to the backend |
| Reverse proxy/CDN cache | Responses stored by the proxy per cache policy | Can reduce backend and network load |

Do not automatically enable CDN caching for documents whose content depends on authentication, locale, or request context. If using HTTP caching, define cache keys, Vary headers, and access policies to avoid serving documents for the wrong audience or language.

Even on a Springdoc cache hit, the backend still has to serialize the OpenAPI model and send the response if HTTP caching does not serve the request.

## 14. Measuring Cold and Warm Costs

To evaluate accurately, measure startup, the first request, and repeated requests separately:

1. Start a fresh application instance and record when the application becomes ready.
2. Send the first request to /v3/api-docs.
3. Send the same request multiple times to observe warm reads.
4. Test each supported group and locale.
5. Compare cache enabled/disabled and preload enabled/disabled in equivalent environments.
6. Record CPU, heap, allocations, response size, and latency.

Example of measuring request times with curl:

~~~bash
curl -sS -o /dev/null -w "first: %{time_total}s\n" \
  http://localhost:8080/v3/api-docs

curl -sS -o /dev/null -w "warm: %{time_total}s\n" \
  http://localhost:8080/v3/api-docs

curl -sS -o /dev/null -w "warm: %{time_total}s\n" \
  http://localhost:8080/v3/api-docs
~~~

The first command is the first request in the running process; the next two commands help observe warm reads. curl results include both network and HTTP stack overhead, so run multiple times and use median or percentiles rather than concluding from a single sample.

## 15. Measuring Multiple Groups and Locales

If there are multiple documents, measure each URL separately:

~~~bash
curl -sS -o /dev/null -w "default: %{time_total}s\n" \
  http://localhost:8080/v3/api-docs

curl -sS -o /dev/null -w "partner: %{time_total}s\n" \
  http://localhost:8080/v3/api-docs/partner

curl -sS -H "Accept-Language: vi" -o /dev/null \
  -w "vi: %{time_total}s\n" http://localhost:8080/v3/api-docs

curl -sS -H "Accept-Language: en" -o /dev/null \
  -w "en: %{time_total}s\n" http://localhost:8080/v3/api-docs
~~~

When measuring locales, requests must actually produce distinct locales under the application's i18n configuration. If two locales return the exact same content, do not conclude that translation or separate cache costs have been tested.

## 16. Monitoring CPU, Memory, and Startup Time

Request latency is not the only metric. When enabling preload or having many groups/locales, monitor:

- Time from process start until the readiness probe succeeds.
- CPU usage during the phase when Springdoc builds the documentation.
- Heap before and after the OpenAPI model is created.
- Garbage collection and allocation rate.
- Size of the returned JSON/YAML.
- p50, p95, and p99 of documentation requests.

Java Flight Recorder can help identify time spent on reflection, schema resolution, serialization, and customizers. Spring Boot Actuator/Micrometer can provide appropriate process/JVM/HTTP metrics if monitoring is enabled in the application.

Do not merely compare total startup time between two builds. Separate Spring context initialization time, OpenAPI preload time, and readiness time to know which part actually increased.

## 17. Choosing Configuration by Operational Goal

| Goal | Suggested Configuration | Trade-off |
| --- | --- | --- |
| Stable documentation, read frequently | Default cache | First generation may be slow |
| Want faster first request | pre-loading-enabled = true | Longer startup |
| Support multiple locales as soon as app is ready | Preload used locales | Increases startup cost and memory |
| Document URL depends on each request | Consider cache.disabled = true | Every request may have to recompute |
| No need to publish documentation in environment | api-docs.enabled = false | OpenAPI endpoints are no longer served |

Example production configuration for stable documentation:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 100
  pre-loading-enabled: true
  pre-loading-locales:
    - vi
    - en
~~~

Example development configuration when metadata changes need to be observed frequently:

~~~yaml
springdoc:
  cache:
    disabled: true
  pre-loading-enabled: false
~~~

Do not copy these two configurations for every environment. Choose based on documentation stability, locale count, group count, and startup/request time requirements.

## 18. When Should Documentation Endpoints Be Disabled?

If the production environment does not need to serve OpenAPI, endpoints can be disabled:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Disabling Swagger UI alone does not mean OpenAPI JSON/YAML is also disabled. If the goal is not to serve documentation, configure api-docs.enabled appropriately. If a CI pipeline still needs the specification, generate the documentation during a build/test step or use a dedicated environment rather than disabling the endpoint where the pipeline needs access.

## 19. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| First OpenAPI request is slow | Cold generation without cached entry | Measure the cold path and consider preloading |
| Subsequent requests remain slow | Cache disabled, locale changing, or cache miss | Check cache.disabled, Accept-Language, and max-entries |
| Startup increases after enabling preload | Documentation is generated during startup | Measure preload and readiness times |
| Heap grows when supporting many locales | Many descriptions cached | Limit locales and tune max-entries |
| One group is slower than another | Group has more operations/schemas or customizers | Measure each group and narrow scan scope appropriately |
| Disabling cache increases CPU | Every request must recompute OpenAPI | Only disable when per-request data is required |
| Customizer prolongs cold generation | Calls DB/HTTP or heavy processing during model creation | Remove unnecessary I/O and reuse static data |
| Preload finishes but UI is still slow | Asset loading, response serialization, or network time | Measure swagger-config, document, and static resources separately |
| Server URL needs to vary by proxy but cache keeps old URL | Server URL is computed per request while model is cached | Configure forwarded headers/server URL or consider disabling cache |
| Cache max-entries has no effect | Springdoc version does not support the property yet | Check version; max-entries was introduced in 2.9.1 |

## 20. Measurement and Optimization Checklist

- [ ] Measured startup and readiness before enabling preloading.
- [ ] Measured the first OpenAPI request in a fresh process.
- [ ] Measured warm reads multiple times with the same URL.
- [ ] Measured each group and locale separately.
- [ ] Confirmed cache.disabled uses the desired value.
- [ ] Checked cache.max-entries against the Springdoc version.
- [ ] Selected pre-loading-locales based on actually used languages.
- [ ] Customizers do not make unnecessary database/HTTP calls or do heavy processing.
- [ ] packages-to-scan and paths-to-match only include APIs requiring documentation.
- [ ] Monitored CPU, heap, allocation, response size, and latency percentiles.
- [ ] Distinguished Springdoc model caching from HTTP/browser/CDN caching.
- [ ] Verified Swagger UI, swagger-config, and OpenAPI documents after configuration changes.

OpenAPI construction cost is typically concentrated in the first computation; subsequent requests can reuse the cached model but still need to serialize and transmit the response. The default cache suits stable documentation, while preloading shifts cold generation to startup. Disabling the cache should only be used when documentation must vary per request and the team accepts the increased CPU/latency cost. Measuring startup, cold requests, warm reads, individual groups, and locales separately enables choosing configuration based on real data.

## References

- [Springdoc OpenAPI v2 — Core properties](https://springdoc.org/v2/core-properties.html)
- [Springdoc OpenAPI v2 — FAQ: OpenAPI cache](https://springdoc.org/v2/faq.html)
