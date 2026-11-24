# Pre-Loading by Group or Locale When Supported by Version

Springdoc builds the OpenAPI document from the application's controllers, models, annotations, configuration, and customizers. If the document is large or has many API groups, the first call can take time to scan endpoints, build schemas, and apply metadata. When multiple clients open Swagger UI right after the service starts, the initial request can experience higher latency than subsequent requests.

Springdoc provides document caching and an option to pre-load on application startup. In supported versions, you can specify which locales to pre-load. When an application has multiple GroupedOpenApi beans, each group has its own document endpoint; to reliably warm each group and language, hit the corresponding URLs after the service is ready. Do not invent a property named group-preload if the version in use does not document such a property.

## 1. Why Pre-Load OpenAPI?

Document generation can involve:

1. Discovering controllers and endpoints according to package/path filters.
2. Reading HTTP method, path, parameter, request body, and response mappings.
3. Analyzing DTOs, generic types, enums, validation, and schemas.
4. Applying @Operation, @ApiResponse, security metadata, and customizers.
5. Building the OpenAPI model, resolving $refs, and serializing to JSON or YAML.

For a small API, this cost is usually negligible. For an application with many controllers, nested schemas, multiple groups, or multiple translations, the first computation can introduce noticeable latency.

Springdoc caches the OpenAPI description after computing it by default. Therefore, the first request typically bears most of the cost; subsequent requests can retrieve the cached document. Pre-loading shifts part of that cost to the startup phase or a warm-up phase before receiving user traffic.

Pre-loading does not simplify schemas and does not make ordinary business requests faster. It primarily reduces latency when clients first load /v3/api-docs/{group} or locale-specific documents.

## 2. Enabling Pre-Loading When Supported by Version

Key properties:

| Property | Default | Meaning |
| --- | --- | --- |
| springdoc.pre-loading-enabled | false | Enables loading the OpenAPI document on application startup. |
| springdoc.pre-loading-locales | Default locale | List of locales to pre-load; accepts a comma-separated list. If omitted, springdoc uses the default locale. |
| springdoc.cache.disabled | false | Disables caching of computed documents. |
| springdoc.cache.max-entries | 100 in supported versions | Limits the number of descriptions held in cache per locale. |

Example configuration in application.yml:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales: en,vi,fr-FR
  cache:
    disabled: false
~~~

In the example, springdoc is instructed to load the document at startup for locales en, vi, and fr-FR. If the JVM's default locale is needed, include it in the list; if pre-loading-locales is left blank, springdoc uses the default locale per version documentation. Keep caching enabled so subsequent requests can reuse computed results.

pre-loading-locales is documented in springdoc starting from the v2.2.0 branch. Check the property reference for the v1, v2, or v3 branch your application actually uses; do not assume a property documented in the latest docs exists in all older releases.

If pre-loading-locales is not declared, official documentation states that springdoc loads the default locale. If the application only publishes one language, do not add other locales to the list.

## 3. How Does Locale Affect the Document?

Springdoc can maintain one OpenAPI description per request locale, determined via the Accept-Language header. For example:

~~~http
GET /v3/api-docs HTTP/1.1
Accept-Language: vi
~~~

Another request may ask for English:

~~~http
GET /v3/api-docs HTTP/1.1
Accept-Language: en
~~~

If the application has localized metadata, the two requests can receive summaries, descriptions, or explanatory text in different languages. Pre-loading locales prepares frequently used variants in advance instead of making the first user of each language pay the computation cost.

The Accept-Language header only selects the locale for the processing mechanism; it does not automatically translate arbitrary Java strings or annotations. If @Operation(summary = "Create order") contains a hardcoded string, sending Accept-Language: vi does not automatically turn it into Vietnamese. To produce multilingual documents, the application must provide translated content using a message/property localization mechanism supported by the springdoc version.

Example verifying two locales:

~~~bash
curl -fsS -H 'Accept-Language: vi' http://localhost:8080/v3/api-docs -o openapi-vi.json
curl -fsS -H 'Accept-Language: en' http://localhost:8080/v3/api-docs -o openapi-en.json
~~~

Compare info, tags, summary, and description fields to verify that content actually changes. If the two files are identical because metadata has not been translated, pre-loading multiple locales may increase startup time and memory without any benefit.

## 4. Pre-Loading Documents for Multiple Groups

GroupedOpenApi splits the API into independent documents. Example:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-v1")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
            .group("internal-v1")
            .pathsToMatch("/api/internal/**")
            .build();
    }
}
~~~

With the default base path, documents are accessed at:

| Group | OpenAPI JSON | OpenAPI YAML |
| --- | --- | --- |
| Default | /v3/api-docs | /v3/api-docs.yaml |
| public-v1 | /v3/api-docs/public-v1 | /v3/api-docs/public-v1.yaml |
| internal-v1 | /v3/api-docs/internal-v1 | /v3/api-docs/internal-v1.yaml |

Groups can have different sets of operations and customizers. To warm a specific group's document, call that group's exact URL. Do not call only /v3/api-docs and assume every group has been warmed.

In the current property reference, springdoc documents pre-loading-enabled and pre-loading-locales, but does not publish a separate property such as springdoc.pre-loading-groups to select a list of groups. Groups are still configured via GroupedOpenApi or springdoc.group-configs; warming specific groups can be done by requesting each group's endpoint after the application is ready.

## 5. Warming Up per Group and Locale

A deployment job can invoke each group/locale pair commonly used by the system. Bash example:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

: "$DOCS_BASE_URL"
BASE_URL="$DOCS_BASE_URL"

for group in public-v1 internal-v1; do
  for locale in en vi; do
    echo "Warming $group ($locale)"
    curl --fail --silent --show-error \
      -H "Accept-Language: $locale" \
      "$BASE_URL/v3/api-docs/$group" \
      -o /dev/null
  done
done
~~~

Set DOCS_BASE_URL without a trailing slash. This script sends requests to each group URL with the corresponding Accept-Language. When the endpoint returns success, springdoc gets the chance to generate and cache the document for that request. Run warm-up after the service is ready to accept requests.

If the internal group is protected, the job needs credentials authorized to read that document. Example adding a bearer header:

~~~bash
curl --fail --silent --show-error \
  -H "Authorization: Bearer $DOCS_TOKEN" \
  -H 'Accept-Language: vi' \
  "$DOCS_BASE_URL/v3/api-docs/internal-v1" \
  -o /dev/null
~~~

Tokens must be pulled from the pipeline's secret store; do not commit them to scripts or enable shell tracing while tokens are present. If warm-up runs through a gateway, use the base URL and prefix that the runner actually reaches.

HTTP warm-up tests routing, security, locale, and document content together. It also helps catch wrong group IDs or unready endpoints. If warm-up must apply to all replicas, ensure requests reach every instance; calling a load-balanced URL multiple times does not guarantee every replica receives a request.

## 6. Configuring Groups via YAML

Besides Java beans, groups can be defined in configuration:

~~~yaml
springdoc:
  group-configs:
    - group: public-v1
      paths-to-match:
        - /api/public/**
    - group: internal-v1
      paths-to-match:
        - /api/internal/**
~~~

When using springdoc.group-configs, there is no need to declare additional GroupedOpenApi beans for those same groups. Avoid defining the same group in both YAML and Java without a clear intent, as duplicate configuration can cause confusion when inspecting registered resources.

Combined with pre-loading:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales: en,vi
  group-configs:
    - group: public-v1
      paths-to-match: /api/public/**
    - group: internal-v1
      paths-to-match: /api/internal/**
~~~

This configuration enables pre-loading and registers two groups. If operations require certainty that both groups have been generated for both locales before serving traffic, run the per-URL warm-up step from the previous section and inspect status/content. Do not rely on an undocumented group-preload property.

## 7. Limiting the Number of Cached Locales

Each requested locale can create a separate OpenAPI description in the cache. Applications supporting multiple languages, multiple groups, or diverse Accept-Language headers must account for memory used by those documents.

Starting in springdoc v2.9.1, springdoc.cache.max-entries limits the number of descriptions kept in cache; v2 documentation lists a default of 100. In the v3 branch, cache bounding was added in v3.1.1, also with a default of 100.

Example for supported versions:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 32
~~~

When the limit is exceeded, the oldest/least recently used entry is evicted per the version's cache policy. Subsequent requests for an evicted locale may need to recompute the document.

Choose max-entries based on the locales actually used and document size. Setting too low a limit can cause constant cache eviction; setting too high a limit can retain many large documents on the heap. Do not assume 100 entries suits every application.

In versions lacking cache limits, avoid letting public docs endpoints accept arbitrary Accept-Language values. Upgrade to a version with bounded caching while restricting accepted locales at the application/gateway layer as supported by your stack. The pre-loading-locales list only specifies which locales to pre-load; do not treat it as a security allowlist for incoming requests.

## 8. When Should Caching Be Disabled?

Property:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Disabling the cache can be helpful in special cases, such as when the server URL must be recomputed per request because the application is served across multiple internal and external proxies or public hosts. The springdoc FAQ cites this as a reason to disable caching.

However, if the goal is reducing cold latency via pre-loading, disabling caching usually works against that goal: documents may have to be recomputed on subsequent requests. Only disable caching when there is a concrete dynamic requirement and the trade-off has been measured.

Do not use cache.disabled=true as a way to refresh documents after changing annotations or controllers in production. Most code/configuration changes require redeploying or a supported refresh mechanism; disabling caching does not replace deployment workflows.

## 9. Balancing Startup Time, Latency, and Memory

Pre-loading shifts computation cost from request time to startup or warm-up. It does not make that cost disappear.

| Strategy | Startup Time | First Request | Memory/Cache |
| --- | --- | --- | --- |
| No pre-load, cache enabled | Generally lower | May be slow due to document generation | Grows as each locale/group is requested. |
| Pre-load default locale | Extra cost at startup | Default locale may be ready sooner | Holds default document in cache. |
| Pre-load multiple locales | Increases with number of generated variants | Reduces cold hits for loaded locales | May hold more descriptions. |
| Warm-up per group/locale | Adds time at post-readiness warm-up step | Warmed pairs can avoid cold hits | Grows with actually cached documents. |
| Cache disabled | Little useful warm-up benefit | Every request may recompute | Lower cache usage but higher CPU/latency when loading docs. |

Do not pre-load every locale and group if most have no users. Choose variants with real traffic, such as public-v1 in Vietnamese and English. Rarely accessed admin groups can generate documents on demand.

Measure separately:

- Startup time to readiness state.
- First OpenAPI request time after readiness.
- Second request time for the same group/locale.
- Request time when switching locales.
- Heap after warming expected variants.

Set thresholds based on your application's measurements rather than turning on every option uniformly across all environments.

## 10. Testing Locales and Groups over HTTP

You can measure document loading time with curl:

~~~bash
curl -sS -o /dev/null \
  -H 'Accept-Language: vi' \
  -w 'status=%{http_code} total=%{time_total}s\n' \
  http://localhost:8080/v3/api-docs/public-v1
~~~

Repeat the same URL to compare cold requests and cached requests. Then switch Accept-Language:

~~~bash
curl -sS -o /dev/null \
  -H 'Accept-Language: en' \
  -w 'status=%{http_code} total=%{time_total}s\n' \
  http://localhost:8080/v3/api-docs/public-v1
~~~

And switch groups:

~~~bash
curl -sS -o /dev/null \
  -H 'Accept-Language: vi' \
  -w 'status=%{http_code} total=%{time_total}s\n' \
  http://localhost:8080/v3/api-docs/internal-v1
~~~

To check content rather than just timing, save the JSON for each group/locale pair and compare paths and translated text. Verify that the response is a valid OpenAPI document rather than a login page or gateway error.

If there are multiple replicas, test each instance or use telemetry to verify which instances received warm-up. A single call through a load balancer does not prove all replicas have warm caches.

## 11. Considerations Behind a Reverse Proxy or HTTP Cache

Locale-specific OpenAPI documents can differ even for the same URL. If a reverse proxy, CDN, or HTTP cache stores responses, ensure the external cache distinguishes requests by Accept-Language when content truly depends on that header. Otherwise, Vietnamese clients might receive an English document previously cached by the proxy.

At the same time, if the server URL is derived from forwarded headers and the application serves the same document across multiple hosts, the internal cache might retain the server URL from the first request. The springdoc FAQ cites this scenario as a reason springdoc.cache.disabled=true might be needed. Before disabling caching, consider configuring explicit servers or normalizing forwarded headers at the proxy to avoid creating unnecessary per-host document variants.

Do not let arbitrary client-sent Accept-Language or forwarded host headers spawn unbounded variants. Restrict locales and trust forwarded headers only from trusted proxies.

## 12. Testing Pre-Loading Configuration

You can verify property binding in a Spring Boot test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OpenApiPreloadingConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void enablesPreloadingForConfiguredLocales() {
        assertThat(environment.getProperty(
            "springdoc.pre-loading-enabled", Boolean.class
        )).isTrue();

        assertThat(environment.getProperty("springdoc.pre-loading-locales"))
            .contains("en")
            .contains("vi");
    }
}
~~~

This test confirms configuration properties are bound. It does not yet prove the document was generated before the first request. To verify behavior, run an integration test or smoke test after startup, invoke the exact group/locale, compare content, and measure request time.

If using springdoc.group-configs, you can test each group's URL in tests:

The method below is an addition to a test class that already has MockMvc and its static imports.

~~~java
@Test
void publicGroupDocumentIsAvailable() throws Exception {
    mockMvc.perform(get("/v3/api-docs/public-v1")
            .header("Accept-Language", "vi"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.openapi").exists())
        .andExpect(jsonPath("$.paths['/api/public/catalog']").exists());
}
~~~

This test proves the group endpoint returns the appropriate document in the test context. It does not by itself prove pre-loading occurred at startup; to verify pre-loading, compare first-request timing and startup logs/metrics on the version in use.

## 13. Notes for GraalVM Native Image

Springdoc supports native images in the Spring Boot 3+ ecosystem, but you must test the actual native-compiled application. Pre-loading is a runtime operation during application startup; it does not mean OpenAPI was generated at build time.

If using @OpenAPIDefinition or @SecurityScheme on an annotation-only class, the springdoc FAQ notes that class may be stripped during native compilation. Place annotations on a Spring configuration class, for example:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(title = "Store API", version = "1.0.0")
)
class OpenApiNativeConfiguration {
}
~~~

After building the native image, verify:

- The application starts and completes pre-loading.
- Each group URL returns an OpenAPI document.
- Configured locales still generate proper documents.
- Schemas, annotations, and customizers appear just as in the JVM build.
- Startup and docs request times meet practical targets.

Do not test only on JVM and assume native image behaves identically. Test the native executable in your pipeline or staging environment if the native image is the deployed artifact.

## 14. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Pre-loading property has no effect | Springdoc version does not support it or property name is wrong | Check core properties for the exact branch and version. |
| Second locale still returns default language content | Annotations/descriptions lack translations or locale not recognized | Check Accept-Language, locale tags, and the application's i18n setup. |
| Only default group is warmed up | Job only calls /v3/api-docs | Call /v3/api-docs/{group} for every required group. |
| Group warm-up returns 404 | Wrong group id, group not registered, or custom base path | Check GroupedOpenApi, springdoc.group-configs, and springdoc.api-docs.path. |
| Internal warm-up receives 401/403 | Group endpoint is secured | Provide appropriate credentials for the job; do not expose internal groups publicly just to warm them. |
| Slow startup after enabling many locales | Each locale incurs document generation work | Only pre-load locales with traffic; re-measure readiness time. |
| Heap grows after warm-up | Many groups/locales create many cache entries or large documents | Reduce locale count, tune cache.max-entries if supported by version. |
| Locales are recomputed continuously | Cache entries evicted or caching disabled | Check springdoc.cache.disabled, cache.max-entries, and locale traffic. |
| Pre-loading enabled yet every request is slow | Cache disabled, requests hit different instances, or documents still regenerate | Check cache config, load balancing, and per-replica telemetry. |
| Works on JVM but native image misses metadata | Annotation class stripped or native behavior differs | Place annotations on @Configuration and test native executable. |
| Proxy returns the wrong language | External HTTP cache does not distinguish Accept-Language | Configure cache vary by header or avoid caching multilingual responses at proxy. |
| Disabling cache increases CPU | Document is recomputed on every request | Only disable when dynamic server URLs are needed; otherwise keep caching and warm-up. |

## 15. Application Principles

- Enable springdoc.pre-loading-enabled when you want to shift OpenAPI generation cost to startup.
- Use springdoc.pre-loading-locales for locales actually used and supported by your version.
- Remember that pre-loading does not automatically translate annotations or descriptive content.
- Use Accept-Language to test documents per locale.
- With multiple groups, call each group's URL; the current property reference has no separate group-preload list property.
- Run warm-up after readiness if you need to ensure specific group/locale pairs are generated.
- Keep caching enabled when the goal is reducing first-request latency; only disable when dynamic server URLs or similar behavior is needed.
- Bound cache entries using springdoc.cache.max-entries from v2.9.1 or v3.1.1 onward.
- Choose locale/group counts based on traffic and heap budget.
- Ensure external HTTP caches handle Accept-Language properly when content depends on locale.
- Test both JVM and native image when deploying GraalVM.

Pre-loading helps reduce cold latency when clients fetch OpenAPI, but you must select the right document variants that will actually be used. springdoc.pre-loading-enabled and springdoc.pre-loading-locales support startup pre-loading depending on version capabilities; caching stores descriptions by locale and groups have separate endpoints. When you need certainty that a specific group/language is ready, warm the corresponding URL after readiness, inspect the content, and measure startup time, request latency, and memory.

## References

- [Springdoc OpenAPI FAQ – cache and locale](https://springdoc.org/faq.html)
- [Springdoc OpenAPI v2 – Core Properties](https://springdoc.org/v2/core-properties.html)
- [Springdoc OpenAPI – Core Properties](https://springdoc.org/core-properties.html)
- [Springdoc OpenAPI v2.2.0 release notes – locale pre-loading](https://github.com/springdoc/springdoc-openapi/releases/tag/v2.2.0)
- [Springdoc OpenAPI v2.9.1 release notes – bounded locale cache](https://github.com/springdoc/springdoc-openapi/releases/tag/v2.9.1)
- [Springdoc OpenAPI v3.1.1 release notes – bounded locale cache](https://github.com/springdoc/springdoc-openapi/releases/tag/v3.1.1)
