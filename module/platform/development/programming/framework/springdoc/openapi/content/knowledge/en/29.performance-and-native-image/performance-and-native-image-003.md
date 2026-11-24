# Shared Cache and Request-Dependent Customizers

## 1. Why Does Caching Affect the OpenAPI Document?

Springdoc OpenAPI generates documentation from handler mappings, annotations, DTOs, Jackson metadata, validation constraints, security configuration, and customizers. In an application with many controllers, nested schemas, and numerous operations, this process can consume significant CPU and time.

If Springdoc had to re-analyze the entire API structure every time a client fetched /v3/api-docs, the documentation endpoint could become a source of repeated load. Therefore, Springdoc computes the OpenAPI description once by default and stores it in a cache for subsequent requests to reuse.

Caching reduces document construction costs, but it introduces an important boundary: computed content may be shared across multiple requests. If a customizer pulls information from the current request—such as host, scheme, tenant, or headers—the result of the first request may be retained and returned to subsequent requests.

This lesson focuses on how caching works, how to measure initial and subsequent read costs, how to configure preloading, and how to handle request-dependent customizers without leaking metadata between clients.

## 2. What Work Is Involved in Document Generation?

When Springdoc needs to create an OpenAPI description, the framework must combine multiple metadata sources:

1. Discover handler methods and request mappings of Spring MVC or WebFlux.
2. Read annotations on controllers, methods, parameters, and DTOs.
3. Analyze request body, response, and generic types.
4. Convert Jackson properties, enums, and serialization metadata into schemas.
5. Incorporate Bean Validation constraints.
6. Build components, schema references, security schemes, and responses.
7. Apply OpenApiCustomizer and document group configurations.
8. Finalize the OpenAPI model to return from the documentation endpoint.

The cost depends on the size and complexity of the API. An application with a few endpoints and simple DTOs is generally much lighter than one with hundreds of operations, generic wrappers, polymorphic schemas, HATEOAS, Data REST, multiple groups, and complex customizers.

Do not treat the time to fetch /v3/api-docs as merely JSON serialization time. The first document generation may have to perform the entire analysis and OpenAPI model construction process.

## 3. Distinguishing Initial Generation from Subsequent Reads

In the default configuration, Springdoc computes the OpenAPI description once and caches it. Therefore, the first request that needs to generate the description may be slower than subsequent requests.

| Phase | Main Work | Typical Cost |
|---|---|---|
| Application startup | Initialize Spring context, beans, handler mappings | Application-wide startup cost |
| First documentation fetch | Analyze API, build schemas, run customizers, and store in cache | Potentially highest for the docs endpoint |
| Subsequent fetches | Retrieve cached description, serialize, and return HTTP | Typically lower |
| Cache miss or entry eviction | Regenerate description for the corresponding locale | Re-incurs document generation cost |
| Restart or new instance creation | In-process cache does not exist yet | Initial generation cost may repeat |

Distinguish Springdoc's cache from an HTTP response cache. Springdoc caches the computed OpenAPI description. Requests still pass through the web stack, content negotiation, and response writing. JSON/YAML still must be converted to the appropriate representation and transmitted over HTTP; do not assume the raw response bytes are cached.

Swagger UI also loads HTML, JavaScript, CSS, and swagger-config. Caching the OpenAPI description does not mean all UI resources use the same cache.

## 4. Springdoc Default Cache

Key property:

~~~yaml
springdoc:
  cache:
    disabled: false
~~~

The default value of springdoc.cache.disabled is false, meaning OpenAPI description caching is enabled.

When caching is enabled:

- Springdoc reuses the computed description.
- Subsequent requests do not need to rebuild the entire document while the cache entry remains present.
- One description is cached per locale requested via Accept-Language.
- The cache is in-memory state within the application instance.
- When the instance restarts, the in-process cache is recreated.

The cache is not a shared store across pods or servers. If a deployment has multiple replicas, each instance has its own cache. The first request hitting each instance may need to generate its own description unless the instance preloaded it.

## 5. Caching Differentiated by Locale

Springdoc supports generating OpenAPI descriptions according to the requested locale. For example, a client sends:

~~~http
GET /v3/api-docs
Accept-Language: vi
~~~

or:

~~~http
GET /v3/api-docs
Accept-Language: en
~~~

The document may contain localized summaries, descriptions, or metadata. Because the content differs, Springdoc stores descriptions keyed by the requested locale.

This means an application with multiple locales may require multiple cache entries. When a locale does not yet have an entry, Springdoc must compute the description for that locale.

If users send many unnecessary Accept-Language values, the number of requested locales can grow and cause cache churn. Define the list of supported documentation languages, configure preloading for only the required locales, and bound the entry count according to the Springdoc version in use.

Do not assume the default cache key includes arbitrary request headers. Springdoc documentation describes caching by locale; host, tenant, user ID, role, or arbitrary headers must not be treated as automatic cache-partitioning dimensions.

## 6. Limiting the Number of Cache Entries

In Springdoc versions that support cache bounding, you can configure:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 100
~~~

springdoc.cache.max-entries sets the maximum number of OpenAPI descriptions retained in the cache. Springdoc v2 configuration documentation notes this property starting in version 2.9.1; other version lines should check their corresponding property reference.

When the limit is reached, the oldest entry under the version's eviction policy is evicted to make room. Current Springdoc documentation describes evicting the least recently used entry.

Too low a limit can cause frequently used locales to be evicted and rebuilt. Too high a limit can hold many OpenAPI models on the heap, especially when documents are large or contain many schemas.

Choose max-entries based on the actual locale count, document size, and instance heap. Do not raise the limit solely to avoid cache misses if the application does not need many locales.

## 7. Cache Is Per-Instance Memory

Suppose a deployment has three replicas:

~~~text
                  Load Balancer
                  /     |     \
                 v      v      v
              Pod A   Pod B   Pod C
              Cache   Cache   Cache
~~~

Each pod has its own process and cache:

- The first request to Pod A may build the description on Pod A.
- Subsequent requests to Pod A can reuse the entry.
- The first request to Pod B may still need to build the description on Pod B.
- When Pod C restarts, Pod C's cache starts empty.

Because the load balancer distributes requests, users may notice some initial requests after a deployment are slower than later ones. This does not necessarily mean caching is broken; requests may be landing on instances that are not yet warm.

Do not assume the Springdoc cache is shared across replicas. If identical documents are required across all replicas, ensure source, profile, locale, and customizers produce identical output; caching only optimizes within each process.

## 8. When Should OpenAPI Documents Be Preloaded?

If you want to shift document generation cost from the first request to startup, Springdoc provides preloading:

~~~yaml
springdoc:
  pre-loading-enabled: true
~~~

The springdoc.pre-loading-enabled property enables preloading the OpenAPI description when the application starts. By default, this property is false.

You can specify which locales to preload:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales:
    - vi
    - en
~~~

If no locale list is specified, Springdoc uses the default locale according to the version's configuration documentation.

Preloading is suitable when:

- Documentation endpoints are called frequently right after deployment.
- You do not want the first user to pay the schema construction cost.
- The documentation has a small, well-defined set of locales.
- The application can tolerate slightly longer startup times to prepare the document.

Preloading does not reduce the total amount of work required; it changes when that work runs. CPU and memory are consumed during startup instead of the first time a client fetches the documentation.

## 9. Trade-Off Between Preloading and Readiness

When preloading is enabled, the application must complete document generation before serving fully according to the corresponding startup flow. This can lengthen startup or time to readiness.

Measure:

- Time from process start to application ready.
- Time to generate the OpenAPI description for each preloaded locale.
- CPU and heap during startup.
- Latency of /v3/api-docs after readiness.
- Behavior when multiple replicas start simultaneously.

If orchestration uses startup probes and readiness probes, set thresholds aligned with real startup times. Do not set excessively large timeouts just to mask a customizer that makes slow database or HTTP service calls.

For applications with many locales, preloading every locale can prolong startup and increase heap usage. Only preload locales that users actually need.

If a customizer depends on a request, preloading poses a particular problem: at startup there is typically no client request to supply a host or tenant. Do not combine request-dependent customizers with preloading unless a clear fallback exists and behavior has been verified.

## 10. When Should Caching Be Disabled?

Springdoc provides the property:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

When caching is disabled, Springdoc recomputes the OpenAPI description per request instead of reusing a cached description. Springdoc documentation cites a valid scenario: Swagger UI served through internal and external proxies where the server URL must be calculated per HTTP request.

For example, the same application may be accessed via two different public hostnames. If the OpenAPI server URL is derived from the current request, a document cached from the first hostname may not suit the second hostname.

Disabling caching can solve request-dependent data issues, but it increases CPU usage and latency for each documentation fetch. If Swagger UI or monitoring continuously pulls the OpenAPI document, rebuilding can become a significant repeated load.

Do not disable caching simply to refresh documentation after code changes. Code changes normally accompany a restart/deploy, at which point the new instance's cache is rebuilt. In development, you can disable caching to observe runtime changes, but production should have a concrete justification.

## 11. The Cache Does Not Automatically Distinguish Host, Tenant, or User

Suppose a customizer adds a server URL from the request:

~~~text
Request A:
Host = api-a.example.com

Request B:
Host = api-b.example.com
~~~

If Request A triggers the initial document generation while caching is enabled, the document may contain the server URL for api-a.example.com. Request B may receive that cached description even though its current host is api-b.example.com.

Similarly, if a customizer adds tenant metadata:

~~~text
Tenant A -> x-tenant: tenant-a
Tenant B -> x-tenant: tenant-b
~~~

locale-based caching does not automatically create two separate documents for two tenants. A document generated in Tenant A's context can be reused in Tenant B's context.

This is not merely a display issue with the wrong URL. If a document contains paths, schemas, security requirements, or metadata specific to a tenant/user, cache reuse can leak information or advertise the wrong API surface.

Do not place user data, access rights, or tenant-specific details into a shared document without proper cache partitioning and authorization mechanisms.

## 12. OpenApiCustomizer Does Not Receive the Request as a Parameter

OpenApiCustomizer is a callback used to modify the OpenAPI model after Springdoc builds the document. The customizer interface receives an OpenAPI object; it does not directly receive HttpServletRequest or ServerWebExchange as a parameter.

Some Servlet applications obtain the current request via RequestContextHolder. This approach relies on thread-bound request context and applies only to the corresponding Servlet model. Do not assume it can be used identically in WebFlux.

For example, a customizer might read a request attribute set by a trusted filter:

~~~java
@Bean
OpenApiCustomizer requestAwareServerCustomizer() {
    return openApi -> {
        RequestAttributes attributes =
            RequestContextHolder.getRequestAttributes();

        if (!(attributes instanceof ServletRequestAttributes servletAttributes)) {
            return;
        }

        HttpServletRequest request = servletAttributes.getRequest();

        String publicBaseUrl =
            (String) request.getAttribute("validatedPublicBaseUrl");

        if (StringUtils.hasText(publicBaseUrl)) {
            openApi.setServers(List.of(
                new Server().url(publicBaseUrl)
            ));
        }
    };
}
~~~

This example assumes an upstream filter has already validated the host and forwarded headers and set the validatedPublicBaseUrl attribute. Do not read unvalidated Host or X-Forwarded-Host headers directly inside the customizer.

This snippet only illustrates Servlet usage. Import the appropriate Spring and OpenAPI model classes for your project version.

## 13. Why Are Request-Dependent Customizers Dangerous When Caching Is Enabled?

Suppose the customizer above runs during the first documentation fetch:

1. Request A arrives for api-a.example.com.
2. The filter validates the host and sets validatedPublicBaseUrl.
3. Springdoc invokes the customizer and writes server URL api-a.example.com into the OpenAPI model.
4. Springdoc stores the computed description in the cache.
5. Request B arrives for api-b.example.com.
6. If the cache entry is reused, the customizer may not run again; Request B receives a document containing Request A's server URL.

This happens because the cache retains the computed result, whereas the default cache key is not designed to differentiate arbitrary hosts.

If the document generated from the first request includes specific permissions or tenant details, that metadata can also appear in responses to later requests. Therefore, customizers using request context must be designed alongside the caching policy, rather than looking solely at the OpenAPI model modification code.

A safe rule is that customizers should by default be deterministic: the same configuration and same locale produce the exact same document, independent of any user or arbitrary request.

## 14. Handling Cases Where the Server URL Truly Depends on the Request

If you need to compute the server URL per request in a Servlet application, consider:

~~~yaml
springdoc:
  cache:
    disabled: true
  pre-loading-enabled: false
~~~

When caching is disabled, the customizer can run again during document generation for the current request. Preloading is disabled because startup has no concrete request from which to determine a public URL.

Before applying this, verify:

- The request context exists at the moment Springdoc builds the document.
- Forwarded headers originate only from trusted proxies.
- The host is on an allowlist.
- The scheme and prefix reflect the actual public URL.
- The customizer does not read authentication details to alter the document per user.
- Rebuilding the document on every request meets expected load capacity.

If you only need a fixed server URL per environment, use an OpenAPI bean or static profile configuration and keep caching enabled. This is usually simpler and more efficient.

Disabling caching does not replace validating forwarded headers. It only causes the document to be recomputed; untrusted request data must still never be used as metadata.

## 15. Distinguishing Servlet and WebFlux Request Contexts

In Servlet applications, RequestContextHolder can provide RequestAttributes bound to the current thread when the request context is established.

In WebFlux, request processing relies on a reactive pipeline and Reactor Context. Requests are not guaranteed to execute on the same thread. Therefore, reading ThreadLocal/RequestContextHolder is not a general model for obtaining ServerWebExchange.

OpenApiCustomizer is a synchronous callback receiving the OpenAPI model. Do not attempt to retrieve reactive requests via ThreadLocal or assume the customizer will have access to ServerWebExchange.

If WebFlux requires request-dependent documentation, prefer:

- Using static server URLs or relative URLs.
- Separating documents by explicit configuration/deployment.
- Using a dedicated, controlled integration endpoint if request-specific output is truly required.
- Designing explicit cache keys and authorization instead of using the default locale cache for tenant data.

Do not copy Servlet examples using RequestContextHolder into WebFlux applications without an appropriate reactive design.

## 16. Customizers Should Be Deterministic and Side-Effect-Free

A customizer may be invoked when the document is generated for the first time, when a cache entry is evicted, when caching is disabled, or when an instance starts preloading. Therefore, customizers should have these properties:

- Do not query a database merely to enrich descriptions.
- Do not call external HTTP services if configuration can be obtained at startup.
- Do not produce business side effects.
- Do not store request data in fields of a singleton bean.
- Do not mutate a shared OpenAPI model after the document has been published.
- Remain idempotent when run repeatedly without creating duplicate tags, schemas, or extensions.
- Rely on stable, validated configuration data.

Example to avoid:

~~~java
@Bean
OpenApiCustomizer slowCustomizer(ProductRepository repository) {
    return openApi -> {
        long count = repository.count();
        openApi.addExtension("x-product-count", count);
    };
}
~~~

This code forces document generation to depend on the database. If caching is disabled, the query runs on every document load. If preloading is enabled, the query runs during startup and slows readiness.

If the metric to display is continuously changing runtime data, the OpenAPI document is usually not the right place. Use a metrics/status endpoint or separate operational documentation.

## 17. Choosing an Architecture for Each Requirement

| Requirement | Appropriate Approach | Cache |
|---|---|---|
| One fixed public base URL per environment | OpenAPI bean or profile configuration | Enabled |
| Multilingual documentation | Configure locales, preload needed locales | Enabled, bounded entries |
| Multiple proxies sharing one public URL | Configure forwarded headers and stable server URL | Enabled |
| One UI accessed via multiple public hosts, server URL must follow request | Controlled request-aware customizer | May disable |
| Tenant-specific documentation | Separate document/deployment or explicit partitioning mechanism | Do not use default cache if key excludes tenant |
| Metadata varying by user/role | Split documentation by audience or design explicit authorization | Avoid shared locale-only cache |
| Large API, documentation changes rarely | Default cache and preload if needed | Enabled |
| Local development needing to observe customizer every time | Temporarily disable cache | Disabled in dev environment |

Do not choose disabled cache simply because a single first request is slow. Determine whether the document genuinely depends on the request or merely needs preloading to improve the experience.

## 18. Measuring Initial Cost and Subsequent Reads

To measure accurately, distinguish cold generation from warm retrieval.

Testing procedure:

1. Start a new instance with caching enabled and preloading disabled.
2. Wait for the application to become ready.
3. Send the first request to /v3/api-docs.
4. Send several subsequent requests with the same locale.
5. Record latency, CPU, and allocations for each group.
6. Start a new instance and repeat with preloading enabled.
7. Repeat with cache disabled if comparison is needed.
8. Test a second locale to observe separate cache entries.
9. Test multiple replicas to observe per-instance cold caches.

Do not rely on a single measurement. Run multiple iterations, exclude JVM/JIT warmup effects if the goal is steady-state comparison, and report p50/p95/p99 instead of only averages.

Do not hardcode strict latency thresholds in ordinary unit tests because timing depends on CI runners. Use dedicated benchmarks or performance tests in a stable environment.

## 19. Monitoring Performance with Appropriate Tools

Standard Spring Boot/JVM tools can be used for observation:

- HTTP server request metrics to measure docs endpoint latency.
- Access logs or reverse proxy logs to separate initial requests from subsequent ones.
- Java Flight Recorder to inspect CPU, allocations, and hotspots.
- Java Mission Control or an equivalent profiler to analyze call stacks.
- Container metrics to view CPU, heap, and startup time.
- Startup/readiness logs to measure preloading impact.

Do not assume Springdoc exposes built-in metrics for cache hit/miss counts if the version in use does not publish such metrics. If cache hit ratios are needed, add appropriate instrumentation or inspect via profiling; do not infer solely from latency.

When benchmarking, keep artifact, profile, locale, request headers, proxy route, and response size constant. If multiple variables change at once, it is hard to tell whether improvements came from caching or other settings.

## 20. Testing Caching and Request-Dependent Customizers

Tests should verify both scenarios.

**When caching is enabled:**

- Request A builds the document with locale vi.
- Request B with the same locale must receive the same stable contract metadata.
- If hosts differ, the document must not accidentally carry Host A's server URL when the design requires a fixed URL.
- Requests with locale en generate a separate English document.
- Locales do not exceed the configured cache limit.

**When caching is disabled:**

- Two requests with different valid public hosts must receive corresponding server URLs if the architecture requires it.
- Spoofed host headers must be rejected or overwritten by the proxy/filter.
- Requests lacking a trusted public URL must use a safe fallback or omit dynamic servers.
- Customizers do not access tenant/user data beyond allowed scope.

You can use MockMvc for Servlet and WebTestClient for WebFlux to test endpoints. However, mocked request tests do not prove that a real proxy sanitizes headers. For forwarded headers, integration tests through ingress/reverse proxy or corresponding infrastructure tests are required.

## 21. Environment-Specific Configuration Examples

A production configuration with a fixed server URL and caching enabled:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 20
  pre-loading-enabled: true
  pre-loading-locales:
    - vi
    - en

app:
  api:
    public-url: https://api.example.com
~~~

OpenAPI bean using the configuration value:

~~~java
@Bean
OpenAPI apiOpenAPI(ApiProperties properties) {
    return new OpenAPI()
        .servers(List.of(
            new Server()
                .url(properties.publicUrl())
                .description("Public API")
        ));
}
~~~

With this approach, the document does not depend on the first request. Preloading prepares the required locales at startup; caching serves subsequent requests.

If the public URL genuinely varies per request and a trusted filter already sets a request attribute, the configuration can switch to:

~~~yaml
springdoc:
  cache:
    disabled: true
  pre-loading-enabled: false
~~~

Only use the second configuration when document rebuild costs are acceptable and request data sources are protected. Do not enable both preloading and customizers requiring a request context without a clear fallback.

## 22. Common Pitfalls

| Symptom | Cause to Investigate |
|---|---|
| First docs request is slow, subsequent ones are fast | Initial OpenAPI description generation cost |
| Each pod shows different docs latency after deploy | Per-instance caches warmed at different times |
| Host A's server URL appears when accessing Host B | Request-dependent customizer generated a cached document |
| Tenant A sees Tenant B's metadata | Default cache does not partition by tenant |
| Disabling cache spikes CPU | Every request must rebuild the description |
| Startup slows after enabling preload | Document generation cost shifted to startup |
| Second locale is slower than the first | Cache entry for that locale had not been created yet |
| Cache entries are continuously evicted | Locale count exceeds max-entries or limit is too low |
| Customizer runs without a request | Preload or document generation is not tied to an HTTP request |
| RequestContextHolder is null | No Servlet request context when the customizer runs |
| WebFlux cannot read request from ThreadLocal | Reactive context is not guaranteed to be thread-bound |
| Swagger UI displays internal URLs | Server URL or forwarded headers misconfigured |
| Cache disabled yet spoofed host still used | Source of Host/X-Forwarded-* not verified |
| Customizer makes docs unusually slow | Database queries, HTTP calls, or heavy computation inside customizer |

When investigating, compare the JSON documents of the first and subsequent requests, and check locale, host, profile, and cache state. Do not look solely at response time while ignoring reused document content.

## 23. Cache and Customizer Design Principles

When using Springdoc caching with customizers:

1. Understand that the cache stores the computed OpenAPI description, not raw HTTP response bytes by default.
2. Treat the cache as per-instance state; every pod has its own cache.
3. Keep caching enabled by default for stable documents.
4. Use springdoc.cache.max-entries to bound locale entries in supported versions.
5. Use preloading to shift document generation cost to startup when appropriate.
6. Do not assume the default cache key distinguishes host, tenant, user, or arbitrary headers.
7. Prefer deterministic, request-independent customizers.
8. Never store request data in fields of a singleton customizer.
9. Only disable caching when the document genuinely must be computed per request.
10. When disabling caching, re-evaluate CPU, latency, and load from Swagger UI/monitoring.
11. Do not rely on RequestContextHolder in WebFlux.
12. Do not preload documents that require a request context without a fallback.
13. Verify forwarded headers from trusted proxies before using them to construct server URLs.
14. Test document contents across different hosts, locales, tenants, and instances.
15. Measure cold generation, warm requests, and startup separately.

Caching avoids rebuilding a stable contract. Request-dependent customizers demand output varying with the current context. When these two mechanisms are combined without clear partitioning rules, documents can be incorrect or leak metadata across requests. Keep documents stable and caching enabled whenever possible; recompute per request only when truly required, using verified request sources and measured costs.

## 24. Official References

- [Springdoc FAQ – Cache and server URL](https://springdoc.org/faq.html)
- [Springdoc Configuration Properties](https://springdoc.org/properties.html)
- [Springdoc OpenAPI v2 Documentation](https://springdoc.org/v2/)

