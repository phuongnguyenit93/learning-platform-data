# Setting Documentation Paths and Cache Headers

## 1. Objective

In the **SPRING_REST_DOCS** module, HTTP tests using MockMvc, WebTestClient, or REST Assured generate snippets for requests, responses, payloads, headers, parameters, and multipart parts. Asciidoctor/Markdown combines snippets into REST API documentation. When documentation is packaged and served as static resources, you need stable URLs and appropriate cache policies so users access the right version without retaining stale content too long.

This lesson addresses three questions: which URL exposes the documentation; how HTML, CSS, JavaScript, images, and fonts should have different `Cache-Control` policies; and how to verify cache headers, conditional requests, and content after a release.

## 2. Separating Public URLs from Classpath Locations

Suppose the JAR contains:

```text
BOOT-INF/classes/static/docs/
├── index.html
├── css/site.css
├── js/navigation.js
└── images/upload-flow.png
```

The classpath path is `static/docs/index.html`. With the default static resource mapping, the URL is typically `/docs/index.html`; the `static` prefix does not appear in the URL.

| Component | Value |
| --- | --- |
| Classpath location | `classpath:/static/docs/` |
| Entry point file | `index.html` |
| Default URL | `/docs/index.html` |
| CSS URL | `/docs/css/site.css` |
| Image URL | `/docs/images/upload-flow.png` |

Do not guess the public URL from the directory name alone. If the application changes `spring.mvc.static-path-pattern`, the context path, or registers a custom resource handler, the actual URL will differ.

## 3. Setting a URL Prefix with ResourceHandlerRegistry

When an explicit prefix such as `/api-reference/**` is needed, map the prefix to the classpath docs:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ApiDocsWebConfiguration implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/api-reference/**")
                .addResourceLocations("classpath:/static/docs/");
    }
}
```

Corresponding mapping:

| Resource | URL |
| --- | --- |
| `static/docs/index.html` | `/api-reference/index.html` |
| `static/docs/css/site.css` | `/api-reference/css/site.css` |
| `static/docs/images/upload-flow.png` | `/api-reference/images/upload-flow.png` |

The resource location should end with a trailing slash. The URL prefix may differ from the classpath directory name. Review the MVC configuration so a custom handler does not interfere with other static resources.

### 3.1. Friendly Entry Point URL

Using the explicit URL `/api-reference/index.html` is easy to verify. Do not assume `/api-reference/` automatically opens the index inside a subdirectory; welcome-page handling depends on configuration and version.

If you want a shorter URL, create an intentional redirect:

```java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class ApiDocsLandingController {

    @GetMapping("/api-reference")
    String redirectToDocs() {
        return "redirect:/api-reference/index.html";
    }
}
```

Verify the redirect location when the application runs behind a context path or reverse proxy.

## 4. Choosing a Versioned URL Strategy

API documentation changes across releases. Common strategies:

| Strategy | Example | Best For |
| --- | --- | --- |
| Stable URL pointing to latest | `/api-reference/index.html` | Users wanting current docs |
| Versioned URL | `/api-reference/v1/index.html` | Retaining docs for older API versions |
| Release-based URL | `/api-reference/2026.11/index.html` | Exact traceability of released docs |

You can provide both a stable URL for the current release and versioned URLs for supported releases. Versioned URLs should remain immutable after publication.

Example:

```text
static/
└── api-reference/
    ├── current/index.html
    ├── v1/index.html
    └── v2/index.html
```

If shipping docs only inside a single JAR, package the current version. If multiple versions must be retained, consider publishing docs as a separate artifact/site so you do not carry the entire history inside every JAR.

The version in the URL should match the API/release version published by the team. Do not remove older versions while clients still rely on them.

## 5. Cache-Control and Basic Directives

The `Cache-Control` header instructs browsers and shared caches on how to store and reuse responses.

| Directive | Meaning |
| --- | --- |
| `max-age=300` | Response may be used for 300 seconds without revalidation |
| `public` | Shared caches may store the response if other conditions allow |
| `private` | Only private caches such as the user's browser may store it |
| `no-cache` | May be stored, but must revalidate before reuse |
| `no-store` | Do not store the response in any cache |
| `must-revalidate` | Once stale, must revalidate before using |
| `immutable` | While fresh, the client does not need to revalidate the resource |

`no-cache` does not mean "do not store"; to forbid storage use `no-store`. `private` does not replace authorization. `public` does not make a private endpoint safe to share.

### 5.1. HTML and Assets Have Different Lifecycles

The HTML landing page typically changes per release. CSS/JS/images can be cached longer if filenames include a hash/version and content never changes at the same URL.

| Resource Type | Suggested Policy | Reason |
| --- | --- | --- |
| `index.html` at current URL | `no-cache` or short `max-age` | Must revalidate to receive new releases |
| Immutable versioned HTML | Long `max-age`, optionally `immutable` | URL represents a fixed release |
| Fixed-name CSS/JS | Short/moderate `max-age` | Content can change at the same URL |
| Hashed/versioned CSS/JS | Long `max-age` + `immutable` | URL changes whenever content changes |
| Versioned images/fonts | Long `max-age` + `immutable` | Asset does not change at the same URL |
| Private documentation | `private` or `no-store` | Prevent shared caches from retaining sensitive content |

These are sample policies; exact durations depend on release frequency and CDN behavior. Do not mark `/docs/index.html` as `immutable` if the URL always points to the latest release.

## 6. Configuring Caching with ResourceHandlerRegistry

Spring MVC lets you set `CacheControl` on a resource handler:

```java
import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ApiDocsResourceConfiguration implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/api-reference/**")
                .addResourceLocations("classpath:/static/docs/")
                .setCacheControl(CacheControl.maxAge(Duration.ofMinutes(5))
                        .cachePublic());
    }
}
```

This example allows public caching for 5 minutes. Use `cachePublic()` only if the content is genuinely public. For docs requiring login or containing internal details, use a `private`/`no-store` policy and proper authorization.

### 6.1. Different Policies for HTML and Assets

You can register handlers with specific patterns:

```java
registry.addResourceHandler("/api-reference/**/*.html")
        .addResourceLocations("classpath:/static/docs/")
        .setCacheControl(CacheControl.noCache());

registry.addResourceHandler("/api-reference/assets/**")
        .addResourceLocations("classpath:/static/docs/assets/")
        .setCacheControl(CacheControl.maxAge(Duration.ofDays(365))
                .cachePublic()
                .immutable());
```

This example assumes versioned assets live in an `assets` directory. Verify pattern matching and handler ordering for your project's Spring Framework version; avoid letting a broad pattern apply the wrong policy. A clean, manageable option is separating HTML and assets into two URL prefixes/resource roots.

Do not set a one-year `immutable` cache on fixed-name files if content at that URL can change.

## 7. Configuring Caching with Spring Boot Properties

For default static resources, Spring Boot provides the `spring.web.resources.cache` property group.

Example:

```properties
spring.web.resources.cache.cachecontrol.max-age=5m
spring.web.resources.cache.cachecontrol.cache-public=true
```

You can use `spring.web.resources.cache.period` for cache duration. When explicit directives such as `public`/`private`/`no-cache`/`no-store` are needed, the `cachecontrol` group expresses the policy more specifically.

These properties apply to default static resource handling. If you registered a custom handler and called `setCacheControl`, verify that handler's policy; do not assume all properties automatically apply identically to custom handlers.

`spring.web.resources.add-mappings` and `spring.web.resources.static-locations` control enabling mappings and resource locations, not cache policy. Do not confuse them with `Cache-Control` settings.

## 8. Conditional GET, Last-Modified, and ETag

Caching also lets browsers ask the server whether a resource has changed.

- `Last-Modified`: timestamp when the resource was last modified.
- `If-Modified-Since`: client sends the previously received timestamp; the server can return 304 if the resource has not changed.
- `ETag`: validator representing a specific version of a representation.
- `If-None-Match`: client sends the stored ETag; the server can return 304 if the representation still matches.

Spring MVC static resource handling supports `Last-Modified`/conditional requests depending on resource type and framework version. Do not assume every configuration automatically generates an `ETag` for every file. If `ETag` is required, verify actual responses or configure an appropriate validator.

Conditional request example:

```http
GET /api-reference/index.html HTTP/1.1
If-Modified-Since: Tue, 17 Nov 2026 02:00:00 GMT
```

If the resource has not changed since that timestamp and the validator is valid, the server may respond:

```http
HTTP/1.1 304 Not Modified
Cache-Control: no-cache
Last-Modified: Tue, 17 Nov 2026 02:00:00 GMT
```

A 304 response does not resend the HTML body; the browser uses its cached copy. The date in the example illustrates formatting only, not a value to hardcode.

### 8.1. Choosing max-age, no-cache, or no-store

- `max-age` lets the browser use the cached copy while fresh without contacting the server.
- `no-cache` allows storage but requires revalidation before reuse.
- `no-store` instructs caches not to store the response.

For `current` HTML, `no-cache` works well when you want browsers to check for new releases while still leveraging conditional requests. For versioned assets, long `max-age` and `immutable` reduce repeat requests.

## 9. Caching and Authenticated Documentation

If docs are restricted to logged-in users or specific roles:

- Use authorization to restrict access.
- Consider `private` so shared caches do not store responses.
- Use `no-store` when responses contain sensitive data or must not be persisted.
- Never use `public` for user/session-dependent responses.
- Verify whether the CDN/reverse proxy honors `Cache-Control` or overrides headers.

Cache policy example for internal docs:

```java
registry.addResourceHandler("/internal-api-docs/**")
        .addResourceLocations("classpath:/static/internal-docs/")
        .setCacheControl(CacheControl.noStore());
```

This is only the cache policy; the security filter chain must still require authentication/authorization for this prefix. Cache headers do not replace access control.

## 10. Context Path and Reverse Proxy

If the application sets a context path `/service`, the URL may be `/service/api-reference/index.html`. If a gateway exposes the application under `/platform`, the public URL may be `/platform/service/api-reference/index.html`.

| Component | Example |
| --- | --- |
| Classpath resource | `static/docs/index.html` |
| Resource handler pattern | `/api-reference/**` |
| Context path | `/service` |
| Public gateway prefix | `/platform` |
| Public URL | `/platform/service/api-reference/index.html` |

Use relative links in HTML whenever possible. If Asciidoctor generates absolute URLs, configure the base path to match the deployment. Check redirect `Location` headers, asset URLs, and cache headers from a client outside the gateway.

## 11. Testing URLs and Cache Headers

You can use MockMvc to verify responses. Example for HTML with a `no-cache` policy:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ApiDocsCacheHeadersTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void servesDocsWithExpectedCacheControl() throws Exception {
        mockMvc.perform(get("/api-reference/index.html"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL,
                        containsString("no-cache")
                ))
                .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_HTML));
    }
}
```

If a different policy is configured, adjust expectations to match actual values. For `max-age`, assert the required directives rather than comparing the entire string verbatim because directive order can vary.

Testing a separate asset:

```java
mockMvc.perform(get("/api-reference/assets/site.abc123.css"))
        .andExpect(status().isOk())
        .andExpect(header().string(
                HttpHeaders.CACHE_CONTROL,
                allOf(
                    containsString("max-age"),
                    containsString("immutable")
                )
        ))
        .andExpect(content().contentTypeCompatibleWith("text/css"));
```

This example assumes the versioned resource actually exists and the handler applies the `immutable` policy to the matching pattern.

### 11.1. Testing Conditional Requests

If the server returns `Last-Modified`, capture the value from the first response and send `If-Modified-Since` in a subsequent request to verify 304 when the resource is unchanged. Do not hardcode environment-dependent timestamps.

Smoke tests after running the executable JAR should verify:

1. HTML returns 200.
2. CSS/images return 200.
3. `Cache-Control` contains expected directives.
4. Conditional requests return 304 if validators are supported.
5. After a release, the `current` URL serves new content and older versioned URLs retain old content.

## 12. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Docs URL returns 404 | Handler prefix mismatch or file not on classpath | Inspect archive and resource mapping |
| `/docs/` does not open index | No welcome-page mapping for subdirectories | Use `/docs/index.html` or a tested redirect |
| Browser shows stale HTML | `max-age` too long on current URL | Use `no-cache`/short `max-age` for current HTML |
| Stale CSS after release | Fixed asset URL with long cache | Version/hash assets or purge cache |
| `no-cache` misunderstood as "do not store" | Confusing revalidation with `no-store` | Use `no-store` when storage must be prevented |
| Private docs cached by shared cache | Using `public` on authorized content | Use `private`/`no-store` and inspect CDN |
| `ETag` missing | Assuming framework auto-generates `ETag` for every resource | Verify responses and configure validator if needed |
| Versioned asset still cached briefly | Handler pattern mismatch or policy applied by another handler | Inspect resource handler mappings |
| Gateway returns wrong URLs | Context path/proxy prefix unaccounted for | Check forwarded headers and public URLs |
| Flaky cache header tests | Full string comparison or hardcoded timestamps | Assert needed directives and read validators from responses |

## 13. Hands-On Exercise

Set up URLs and cache policies for User API documentation:

1. Package docs under `classpath:/static/docs/`.
2. Register the URL `/api-reference/**` using `ResourceHandlerRegistry`.
3. Place the HTML entry point at `/api-reference/index.html`.
4. Separate assets into a versioned directory such as `assets/v2/` or use hashed filenames.
5. Configure current HTML to use `no-cache` or a short `max-age`.
6. Configure versioned assets to use a long `max-age` and `immutable`.
7. If docs are private, require an appropriate role and avoid `cache-public`.
8. Write MockMvc tests verifying the URL, `Content-Type`, and `Cache-Control`.
9. Send a conditional request using the validator actually returned by the server; check for 304 if supported.
10. Run the executable JAR behind a gateway/context path and verify both the public URL and asset URLs.

**Completion criteria:** choose stable/versioned URLs; accurately explain `max-age`, `public`/`private`, `no-cache`/`no-store`, and `immutable`; configure caching for HTML and assets; verify response headers and conditional requests; prevent shared caches from storing private documentation.

## 14. Self-Check Questions

**1. What is the default URL for classpath `static/docs/index.html`?**

Usually `/docs/index.html`; the `static` segment does not appear in the URL.

**2. Why might HTML and CSS/JS need different cache policies?**

Current HTML typically changes per release, whereas versioned assets can be immutable per URL and cached longer.

**3. How does `no-cache` differ from `no-store`?**

`no-cache` permits storage but requires revalidation before reuse; `no-store` prohibits storing the response.

**4. Is `public` appropriate for docs requiring login?**

No. Responses depending on access control need an appropriate `private`/`no-store` policy and security enforcement.

**5. Should `immutable` be set on `/api-reference/index.html`?**

Not if that URL always points to the current release. `immutable` suits versioned/hashed URLs whose content never changes.

**6. Does `dependsOn` in Gradle set cache headers?**

No. `dependsOn` belongs to the build task graph; cache headers are configured in HTTP resource handling or at the proxy/CDN.

**7. How do you verify `ETag` or `Last-Modified`?**

Call the resource endpoint, inspect response headers, and send the corresponding conditional request. Do not assume `ETag` appears automatically without configuring or verifying it.

## References

- [Spring Boot — Static Content](https://docs.spring.io/spring-boot/reference/web/servlet.html#web.servlet.spring-mvc.static-content): static locations and static resource configuration.
- [Spring Framework — Serving Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): resource handlers, `CacheControl`, and conditional requests.
- [Spring Framework — CacheControl API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/CacheControl.html): `Cache-Control` directives and builder.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): semantics of HTTP cache directives.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): conditional requests, validators, and response semantics.
