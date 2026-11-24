# Resource chain, content-based versioning, and invalidating stale caches

**Module:** Spring Boot - web-runtime  
**Parent topic:** Static resources

## 1. Scenario and objectives

A Spring Boot website serves an HTML page with CSS, JavaScript, images, and fonts:

~~~text
GET /assets/css/site.css
GET /assets/js/app.js
~~~

After deploying a new release, the CSS/JS contents changed, yet some users still see the old UI or old JavaScript code. The usual reason is that the **browser, proxy, CDN, or service worker still holds the cached response for the old URL**. When file bytes change while the URL stays the same, caches can keep serving the old bytes until freshness lifetime expires or a separate invalidation mechanism runs.

**The solution for immutable resources** is embedding a byte-based version into the URL:

~~~text
/assets/css/site.css
      |
      v
/assets/css/site-<content-hash>.css

Bytes change -> hash changes -> URL changes -> new cache key.
Bytes unchanged -> URL unchanged -> existing cache reused.
~~~

In Spring, the **resource chain** can generate and resolve such URLs. However, a complete solution also requires **`Cache-Control`**, updating links in HTML, keeping older-release assets during rollouts, and understanding cache layers outside the application.

This lesson targets the following capabilities:

1. Understand **`ResourceHttpRequestHandler`/`ResourceWebHandler`**, **`ResourceResolver`**, **`ResourceTransformer`**, and the role of the resource chain.
2. Distinguish **`ContentVersionStrategy`** from **`FixedVersionStrategy`** and the rules for generating proper URLs.
3. Configure **`Cache-Control`** appropriately for assets and HTML; understand **`ETag`**, **`Last-Modified`**, **`304`**, **`no-cache`**, **`no-store`**, and **`immutable`**.
4. Set up a Spring Boot 3.x + Java 17+ example for Spring MVC and recognize where WebFlux differs.
5. Design releases to avoid stale-cache bugs, 404 chunks, CDNs retaining old copies, or users receiving HTML and JS from two different releases.

## 2. How does the resource chain process static resources?

Spring Boot 3.x searches static resources by default in common classpath locations:

- **classpath:/META-INF/resources/**
- **classpath:/resources/**
- **classpath:/static/**
- **classpath:/public/**

In **Spring MVC**, Spring uses **`ResourceHttpRequestHandler`**; in **Spring WebFlux**, Spring uses **`ResourceWebHandler`**. The default static mapping is **`/**`**, changeable via **`spring.mvc.static-path-pattern`** (MVC) or **`spring.webflux.static-path-pattern`** (WebFlux).

The resource chain combines two component groups:

| Component | Responsibility | Examples |
| --- | --- | --- |
| **`ResourceResolver`** | Maps URLs to resources; locates and resolves public paths. | **`VersionResourceResolver`**, **`PathResourceResolver`**, **`EncodedResourceResolver`** |
| **`ResourceTransformer`** | Transforms content or links inside resources before serving. | **`CssLinkResourceTransformer`** when properly configured |

A request using a fingerprinted path can flow through:

~~~text
Browser: GET /assets/css/site-<hash>.css
       |
       v
HandlerMapping selects the /assets/** resource handler
       |
       v
VersionResourceResolver validates the version in the URL
       |
       v
Resolver chain locates site.css in resource locations
       |
       v
Transformer (if present) processes content/links
       |
       v
Resource handler sends response + HTTP cache headers
~~~

There are two directions to distinguish:

- **Inbound:** a versioned URL is resolved and validated against the version of the existing resource; requests that fail validation do not arbitrarily resolve to another file.
- **Outbound:** when rendering HTML or generating asset links, **`ResourceUrlProvider`** runs the chain to produce versioned public paths. If templates or JavaScript write raw original URL strings directly, Spring has no reason to rewrite those links automatically.

For instance, merely changing the filename in HTML to **`site-something.css`** without a matching resolver or file easily triggers **404**. For cache busting to work, **link generation** and **URL resolution** must match.

## 3. ContentVersionStrategy: fingerprinting by bytes

**`ContentVersionStrategy`** computes an **MD5 digest from the resource's contents** and inserts the version into the path before the file extension.

~~~text
Original file:
  src/main/resources/static/assets/css/site.css

Logical URL:
  /assets/css/site.css

Fingerprinted URL when actually resolved:
  /assets/css/site-<32-hex-chars>.css
~~~

Illustrative example, not an actual hash of this file:

~~~text
/assets/css/site-0123456789abcdef0123456789abcdef.css
~~~

The exact **bytes** determine the digest: changing even a single space in CSS alters the hash. When contents stay unchanged between builds, the corresponding URL stays unchanged. Thus browsers and CDNs can cache long-term while still distinguishing updated resources.

**MD5 here only serves as a fingerprint/cache key**; it provides no cryptographic signature verification. Do not equate the version string with **HTTP `ETag`**, **Subresource Integrity (SRI)**, code signing, or release signatures. Each mechanism serves a different purpose and trust model.

**`FixedVersionStrategy`** uses a release-managed version string, such as **`v12`**:

~~~text
/assets/js/loader.js
      |
      v
/v12/assets/js/loader.js
~~~

Fixed versioning fits cases where asset loading forbids altering filenames (such as certain JavaScript module loaders), or when your release process strictly bumps versions. Drawback: **if bytes change yet you forget to increment `v12`, the URL stays the same and browsers may keep the old copy**. Spring Boot allows applying content and fixed strategies to different path patterns.

With **dynamic JS imports, module graphs, and source maps**, inserting hashes directly into paths can break internal references. When a frontend already uses Vite/Webpack/Rollup to emit hashed assets and a manifest, consider using that manifest as the URL source; do not assume Spring can rewrite every string inside bundled JS.

## 4. URL versioning, resource chain cache, and HTTP cache are different

| Mechanism | Where does it take effect? | What it does not do |
| --- | --- | --- |
| **`ContentVersionStrategy`** | Maps file contents to fingerprinted URLs. | Does not automatically set `Cache-Control`/TTL. |
| **`FixedVersionStrategy`** | Prepends an application/release-chosen version. | Does not automatically detect byte changes. |
| **`spring.web.resources.chain.cache`** | Caches resource chain resolution/lookups **inside the server**. | Does not clear browser/CDN caches. |
| **`Cache-Control`** | Governs storing and reusing HTTP responses in browsers/proxies/CDNs. | Does not change URLs or bump versions. |
| **`ETag` / `Last-Modified`** | Validators for conditional requests, enabling 304 when applicable. | Does not force fresh cached entries to call the server. |
| **CDN purge** | Requests edge nodes to delete/invalidate objects per provider policy. | Does not guarantee clearing browser caches or service worker Cache Storage. |

**`Cache-Control: public, max-age=31536000`** lets shared caches treat the asset as fresh for up to one year (subject to applicable HTTP caching rules). **`immutable`** indicates the resource content at that URL will not change during its freshness lifetime, helping skip unnecessary revalidation requests. This policy is only safe when the URL is immutable and the data is genuinely public.

**`Cache-Control: no-cache`** is frequently misunderstood: the response **is allowed to be stored**, yet **must be revalidated before reuse**. This is typically suitable for HTML entrypoints/manifests, where you want users to promptly discover links to new release assets.

**`Cache-Control: no-store`** instructs caches **not to store the response**. Appropriate when sensitive data policies require it; not a default solution for public CSS/JS. **`max-age=0`** marks responses immediately stale; **`must-revalidate`** forbids serving stale responses without validation per HTTP caching rules. You can combine **`no-cache, max-age=0, must-revalidate`** for HTML.

**`ETag` / `Last-Modified` / `304`**: servers may return validators. When a cache needs revalidation, clients send **`If-None-Match`** or **`If-Modified-Since`**. If unchanged, the server can return **`304 Not Modified`** with no body. If an endpoint produces no validator or conditions are unmet, it still returns **`200`** with the new body. A URL version hash and an `ETag` are not the same mechanism.

## 5. Cache policies by content type

| Response type | URL strategy | Recommended `Cache-Control` | Why |
| --- | --- | --- | --- |
| Public CSS/JS/fonts/icons, immutable releases | **Content-hashed URLs** | **public, long max-age**, optionally **immutable** | Content changes yield new URLs; unchanged files reuse cache. |
| HTML entrypoints, index, bundle/manifest references | **Stable URLs** | **no-cache** or short TTL + revalidation | Clients must have a chance to discover new links after deployment. |
| Per-user API data, sensitive documents | Depends on domain | **private/no-store** where appropriate | Prevents shared caches from storing wrong or sensitive data. |
| Uploaded images at fixed URLs whose contents are replaced | Versioned URLs, or validators/TTLs/purge | Depends on content update policy | Fixed URLs with long caching risk showing stale images. |
| Service worker scripts, offline frontend app shells | SW update policy | Follow SW lifecycle, do not copy CSS settings | SW-managed Cache Storage is a separate layer. |

**Critical mistake:** setting **a one-year `max-age` on HTML as well**. If HTML V1 referencing hash H1 remains fresh for a year, browsers will not discover asset H2 even after Spring generates H2 from updated CSS.

**Another mistake:** enabling the content strategy while keeping hardcoded **`/assets/css/site.css`** links in HTML. Users keep requesting the unversioned URL, so browsers treat the old and new files as the same cache key.

## 6. Spring Boot 3.x + Java 17+ demo: Spring MVC, Thymeleaf, and content hashes

This is a runnable example in a **Spring Boot 3.x project already initialized with Gradle wrapper/plugins**, using Java 17 or newer. Add two dependencies to the **`dependencies`** block in **`build.gradle`** (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
~~~

Do not add **`@EnableWebMvc`**: keep Spring Boot's Spring MVC auto-configuration and automatic resource handling support.

### 6.1. Configuring asset paths and the resource chain

Create **`src/main/resources/application.properties`**:

~~~properties
server.port=8080

# Move the static resource handler to /assets/**
spring.mvc.static-path-pattern=/assets/**

# Enable the resource chain and content versioning for the handler's resources
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**
spring.web.resources.chain.cache=true

# Long cache for static assets /assets/**; does not apply to controller GET /
spring.web.resources.cache.cachecontrol.max-age=365d
spring.web.resources.cache.cachecontrol.cache-public=true
~~~

Meaning:

- **`spring.mvc.static-path-pattern=/assets/**`**: **`src/main/resources/static/assets/css/site.css`** has logical URL **`/assets/css/site.css`**. Does not extend long caching to the HTML **`/`** route handled by a controller.
- **`spring.web.resources.chain.strategy.content.enabled=true`** enables content versioning; **`paths=/**`** applies across the resource handler's paths. This property does not automatically fingerprint APIs or controllers.
- **`spring.web.resources.chain.cache=true`** caches processing in the resource chain to avoid repeated lookups/hashing; defaults to `true` in Spring Boot 3.3.
- The **`spring.web.resources.cache.cachecontrol.*`** properties set HTTP cache headers for resources handled by the resource handler. **`365d`** equals 31,536,000 seconds.

**Limitation of this short configuration:** the resource handler may still serve the file at the unhashed original URL **`/assets/css/site.css`**, and that original URL may also receive the long cache header. Therefore, ensure all HTML/clients link to the **fingerprinted URLs**. Larger systems can separate policies for versioned paths at the CDN/edge or use custom handlers to avoid long caching on fixed URLs.

### 6.2. Application and HTML controller

Create **`src/main/java/com/example/assetcache/AssetCacheApplication.java`**:

~~~java
package com.example.assetcache;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@SpringBootApplication
public class AssetCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(AssetCacheApplication.class, args);
    }
}

@Controller
class PageController {
    @GetMapping("/")
    public String index(HttpServletResponse response) {
        response.setHeader(
                HttpHeaders.CACHE_CONTROL,
                "no-cache, max-age=0, must-revalidate"
        );
        return "index";
    }
}
~~~

**`AssetCacheApplication`** matches the filename; **`PageController`** is a package-private top-level class in the same package and gets component-scanned. Spring Boot looks for template **`index`** inside **`src/main/resources/templates/`**. The controller explicitly sets the HTML cache policy independently of the static asset resource handler.

### 6.3. Thymeleaf generating fingerprinted URLs

Create **`src/main/resources/templates/index.html`**:

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Resource chain demo</title>
    <link rel="stylesheet"
          th:href="@{/assets/css/site.css}"
          href="/assets/css/site.css">
    <script defer
            th:src="@{/assets/js/app.js}"
            src="/assets/js/app.js"></script>
</head>
<body>
    <h1>Resource chain demo</h1>
    <p id="status">loading</p>
</body>
</html>
~~~

In Spring Boot MVC with Thymeleaf/FreeMarker, **`ResourceUrlEncodingFilter`** is auto-configured so URLs encoded by the template engine pass through **`ResourceUrlProvider`**. With the resource chain enabled, returned HTML typically outputs:

~~~html
<link rel="stylesheet" href="/assets/css/site-<hash>.css">
<script defer src="/assets/js/app-<hash>.js"></script>
~~~

The **`<hash>`** placeholders above are illustrative only, not literal output; actual values are computed from each file's exact bytes. Only **`th:href`/`th:src`** go through supported URL generation; plain HTML **`href`/`src`** attributes, static HTML files, or hardcoded paths in JS are not automatically rewritten the same way.

### 6.4. Creating CSS and JS files

Create **`src/main/resources/static/assets/css/site.css`**:

~~~css
body {
    font-family: sans-serif;
    color: #17324d;
}
~~~

Create **`src/main/resources/static/assets/js/app.js`**:

~~~javascript
document.getElementById("status").textContent = "ready";
~~~

Expected project layout:

~~~text
src/
  main/
    java/com/example/assetcache/
      AssetCacheApplication.java
    resources/
      application.properties
      templates/
        index.html
      static/
        assets/
          css/site.css
          js/app.js
~~~

Run the project configured with the Spring Boot plugin and Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Visit **`http://localhost:8080/`**: displayed text changes from **`loading`** to **`ready`** once JavaScript executes. When CSS/JS are served via the content strategy, links in the HTML response contain hashes while **actual filenames on the classpath remain unchanged**.

### 6.5. Step-by-step verification with curl

In another Bash terminal:

~~~bash
curl -fsS -D html-headers.txt -o page.html http://localhost:8080/

# Extract the CSS URL actually generated by the template + resource chain
grep -oE '/assets/css/site-[0-9a-f]{32}\.css' page.html

# Print the HTML headers
cat html-headers.txt
~~~

Check:

- HTML route **`/`** returns **`Cache-Control: no-cache, max-age=0, must-revalidate`** (header order may vary).
- The HTML contains a CSS filename with **32 hex characters** and a matching hashed JS filename. If you only see the old links, verify the Thymeleaf dependency, **`th:href`/`th:src`** attributes, filter, and static mapping.
- The browser requests the actual fingerprinted links with no 404s.

Extract the CSS path from the response itself and test the asset:

~~~bash
css_path=$(grep -oE '/assets/css/site-[0-9a-f]{32}\.css' page.html | head -n 1)
curl -fsSI "http://localhost:8080$css_path"
~~~

Expected result for a valid URL: HTTP status **`200`**, content type **`text/css`**, and **`Cache-Control`** specifying public caching with a one-year max-age. Do not assert `ETag` is always present; validators depend on resource metadata and configuration.

**Test content-based invalidation:** change one character in **`site.css`**, rebuild/restart the app so the server uses the new bytes, and call **`GET /`** again. The CSS URL must change in the new HTML; the JS URL stays unchanged if **`app.js`** bytes did not change. For production JARs/containers, updates ship via a **new build/deployment**, not by editing resources inside a running JAR.

## 7. Java-based ResourceHandler configuration when fine-grained control is needed

You can configure separate resolvers, locations, transformers, and caching with **`WebMvcConfigurer`**. This is an **alternative** to the strategy + `static-path-pattern` properties in section 6; do not apply both equivalent setups to the same resource path.

A standalone file **`src/main/java/com/example/assetcache/AssetsMvcConfig.java`**:

~~~java
package com.example.assetcache;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.resource.VersionResourceResolver;

@Configuration(proxyBeanMethods = false)
public class AssetsMvcConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofDays(365))
                                .cachePublic()
                                .immutable())
                .resourceChain(true)
                .addResolver(
                        new VersionResourceResolver()
                                .addContentVersionStrategy("/**"));
    }
}
~~~

**`VersionResourceResolver`** adds the content strategy; **`resourceChain(true)`** enables chain lookup caching; **`CacheControl.maxAge(...).cachePublic().immutable()`** configures HTTP cache headers. **`immutable()`** is available in Spring Framework 6.x; use it only when bytes at the same URL never change. This class requires **`spring-boot-starter-web`** and Boot MVC; do not use **`@EnableWebMvc`** unless intentionally replacing all auto-configuration.

In production, separate paths so **HTML is never served by a handler with a one-year cache**; multiple handlers can assign different TTLs. When adding custom handlers, check which mapping actually wins to avoid overlaps between a custom handler and default resource mappings. If you choose this Java config, remove the equivalent strategy/handler properties from section 6 so ownership stays clear.

### Resolver ordering and CSS links

When using precompressed **`.gz`/`.br`** files via **`EncodedResourceResolver`** together with **`VersionResourceResolver`**, Spring Framework instructs registering **`EncodedResourceResolver` before `VersionResourceResolver`** so fingerprints are computed on the **uncompressed** resource. Version strings should not vary solely across content-encoding variants.

**`CssLinkResourceTransformer`** can rewrite resource links like **`url(...)`** inside CSS when properly configured. For JS imports, module graphs, or bundler asset manifests, do not assume Spring rewrites every link automatically; build tools should keep the entire dependency graph consistent.

## 8. Stale cache invalidation must account for the deployment lifecycle

A release example:

~~~text
Release V1: HTML V1 -> /assets/js/app-H1.js
Release V2: HTML V2 -> /assets/js/app-H2.js
~~~

When new HTML references the new URL, users fetch H2 even if H1 remains cached. **You do not necessarily purge H1** on every release if H1 is immutable and incident-free. However, the policy is incomplete if you **delete H1 from the origin immediately after deploying**.

Recommended rollout process:

1. **Build deterministic assets**; each release's HTML/manifest references the exact bundle hashes. If Spring hashes resources at runtime, all instances must hold identical bytes when serving the same URLs.
2. **Upload/distribute H2 assets before publishing HTML V2**. Otherwise users receive the new HTML yet requests for H2 return 404.
3. **Keep H1 available long enough** for open tabs, cached old HTML, and dynamic imports. If a Spring Boot JAR V2 holds only the new original file, **`VersionResourceResolver` in V2 may no longer serve the H1 URL** because that hash no longer matches the current file's contents.
4. **Update HTML V2** and ensure HTML uses revalidation or short TTL so browsers discover H2. Never use a one-year TTL for HTML entrypoints.
5. **Monitor 404 errors, chunk load failures, cache hit ratios, response headers, and release distribution across nodes** before cleaning up H1 after the chosen compatibility window.

**Rolling deployments:** while V1 and V2 run concurrently behind a load balancer, an HTML request may hit a V1 node while the subsequent H1 asset request hits a V2 node. Because V2 has only the new file, H1 returns 404. Common solutions include **shared multi-release asset storage/CDN**, publishing assets before HTML, or verified atomic release/affinity mechanisms. Do not merely assume “the CDN will cache it” because cache misses still reach an origin of the wrong version.

**When an urgent rollback/revocation is required due to security or a critical bug**, waiting out a long `max-age` is unacceptable. You need a CDN invalidation plan, origin removal, updated asset URLs/HTML, and awareness that browser caches and service workers may keep previously fetched copies. Edge purges cannot guarantee clearing every user device.

## 9. Cache layers must be verified independently

~~~text
Browser
  |- HTTP cache (keyed by URL and headers)
  |- Service Worker / Cache Storage (if the app uses one)
  |
  v
CDN / reverse proxy (has its own cache key, TTL, and edge policies)
  |
  v
Spring Boot resource chain cache (in-process)
  |
  v
JAR classpath / static directory / asset origin
~~~

**Browser HTTP cache:** relies on URL, `Cache-Control`, `Vary`, and validators. Inspect Chrome/Firefox DevTools Network for every response; do not draw conclusions from a single hard reload.

**Service worker:** can serve stale copies from Cache Storage even after the HTTP cache refreshes. Manage its lifecycle, rotate cache names per release, and verify cleanup and SW update mechanics. While old tabs still need dynamic H1 imports, cleaning up too early causes failures.

**CDN/ingress:** may override origin TTLs, normalize or strip query strings from cache keys, cache HTML longer than expected, or serve `stale-while-revalidate`. Inspect actual configuration and response headers at the edge, not only local Spring Boot.

**Spring resource chain cache:** stores lookup results inside the application process. This cache has no control over caches already sitting in browsers; when files on disk change inside a running process, cached lookups may not refresh as expected. In production, publishing immutable artifacts and launching new-release instances is easier to control.

## 10. Spring WebFlux: similar chain, different link rewriting

In WebFlux, static resources are served by **`ResourceWebHandler`** instead of MVC's **`ResourceHttpRequestHandler`**. The default path pattern uses **`spring.webflux.static-path-pattern`**. **`WebFluxConfigurer#addResourceHandlers`** supports chains, resolvers, and `CacheControl` with equivalent functionality.

Example configuration class for **an independent WebFlux project** using **`spring-boot-starter-webflux`**:

~~~java
package com.example.reactiveassets;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.resource.VersionResourceResolver;

@Configuration(proxyBeanMethods = false)
public class ReactiveAssetsConfig implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofDays(365)).cachePublic())
                .resourceChain(true)
                .addResolver(
                        new VersionResourceResolver()
                                .addContentVersionStrategy("/**"));
    }
}
~~~

Place **`ReactiveAssetsConfig.java`** in a component-scanned package. This example is a **configuration class**, not a standalone runnable program; the main app must configure Spring Boot WebFlux.

Key difference: **`ResourceUrlEncodingFilter`** is tied to MVC's servlet response. WebFlux has no equivalent transparent URL rewrite filter across all templates. In WebFlux, you must **explicitly** resolve versioned URLs through **`ResourceUrlProvider`**'s reactive API or pass a frontend-build manifest/hash into templates. Do not copy the assumption “Thymeleaf rewrites all links automatically” from the MVC demo to WebFlux.

## 11. Testing and verification after build/deploy

Verify the following against both the origin **and** CDN/ingress, not solely localhost:

1. **HTML entrypoint:** `GET /` returns proper revalidation headers and points to versioned CSS/JS URLs, not old logical URLs.
2. **Versioned assets:** `GET` on paths extracted from HTML returns **`200`**, expected MIME types and bytes, and appropriate `Cache-Control`.
3. **Content changes:** modifying CSS bytes changes the CSS URL; untouched JS keeps its existing URL. Do not hardcode digests without deterministic build fixtures.
4. **Old releases:** while HTML V1 remains valid, H1 paths must stay available per retention policy. Never let a route fallback return 200 HTML for a 404 JS/CSS request.
5. **Fixed URLs:** if unhashed paths remain, verify their TTL/cache semantics won't trap buggy versions for too long.
6. **Transitive assets:** verify CSS `url(font/image)`, JS dynamic imports, chunks, source maps, path prefixes, and context paths.
7. **Rolling releases:** test asset requests while two backend versions run side by side.
8. **Service worker/CDN:** confirm cache keys, stored versions, expiration, purge policies, and updates behave properly.

If the server provides **`Last-Modified`**, you can test conditional requests:

~~~bash
curl -sSI http://localhost:8080/assets/css/site.css

# Replace placeholder with the actual Last-Modified value returned by the server if present:
curl -sSI -H 'If-Modified-Since: <Last-Modified-value>' \
    http://localhost:8080/assets/css/site.css
~~~

**`304` is only a possible outcome** when a suitable validator exists and the file hasn't changed. **`<Last-Modified-value>`** must be replaced with an actual value; do not copy the placeholder literally as a test command. For fresh versioned assets, skipping revalidation is also the desired behavior.

## 12. Diagnosing common errors

| Symptom | What to inspect | Resolution |
| --- | --- | --- |
| Content strategy enabled yet HTML still shows `site.css` | URLs are hardcoded or bypass `ResourceUrlProvider`/`ResourceUrlEncodingFilter`. | Use Thymeleaf/FreeMarker URL expressions (MVC), a custom helper, or a build manifest. |
| Hashed URL returns 404 | Wrong pattern/location, hash doesn't match bytes, or request hit another release origin. | Verify mappings, classpath, and multi-release asset retention. |
| Page remains stale after deploy | HTML/manifest cached too long, service worker, or CDN retains old copy. | Revalidate HTML, inspect Cache Storage and edge TTL/cache keys. |
| JavaScript chunk errors after rolling deploy | Old tab requests H1 while new node only has H2. | Retain H1 in shared asset origin; deploy assets before HTML. |
| One-year `max-age` applied to everything | HTML and unversioned resources stay stale. | Separate path patterns and cache policies by resource type. |
| Hash unchanged despite source file edits | Build didn't copy resources, JVM resource chain cache, or request hit old node. | Verify bytes in the built artifact, restart/redeploy, and check active origin. |
| Hash changes when toggling gzip/br | Wrong resolver order or hash computed on unstable representation. | Put `EncodedResourceResolver` before `VersionResourceResolver` and verify hashed bytes. |
| WebFlux doesn't auto-rewrite `th:href` | No MVC-style `ResourceUrlEncodingFilter`. | Resolve URLs with reactive `ResourceUrlProvider` API or a manifest. |
| JS module imports break | Import strings aren't updated when paths change. | Use a bundler, `FixedVersionStrategy`, or synchronize the dependency graph. |
| CDN purged yet browser still shows old version | CDN does not control browser HTTP cache/service worker. | Change URLs/HTML references and manage browser/SW lifecycles separately. |

## 13. Applied scenarios

**Scenario A:** HTML V1 references **`app-H1.js`**. You deploy V2 and delete all V1 assets from the origin. An open tab performs a dynamic import of `app-H1.js` after deployment. What happens? **404**, even though V2 and H2 links are valid. Keep H1 available long enough or serve from a multi-version asset store.

**Scenario B:** Spring already generates a new hashed URL for CSS, yet the page still requests **`/assets/css/site.css`**. Why? The link in HTML was not processed through **`ResourceUrlProvider`/`ResourceUrlEncodingFilter`**; fix link generation before expecting cache busting to work.

**Scenario C:** A file is served at an immutable fingerprinted URL and contains no private data. Can it be cached for one year? **Yes**, provided you define proper retention policies, ensure contents at that URL never mutate, and have an incident revocation plan.

**Scenario D:** Both browser and CDN hold a fresh copy of asset H1; HTML V2 points to H2. Must the browser purge H1 before downloading H2? **No**: H2 is a different URL and a different cache key. H1 can expire naturally. What matters is that HTML and CDN actually deliver the accurate H2 links and bytes.

**Self-check questions:** (1) Where does `ContentVersionStrategy` derive its version? (2) What is the difference between `no-cache` and `no-store`? (3) Why is a long `max-age` on `index.html` dangerous? (4) Is `ResourceUrlEncodingFilter` used in MVC or WebFlux? (5) Does resource chain caching clear browser caches? (6) Why must H1 assets be kept during rollouts? (7) Is `ETag` synonymous with a URL version hash?

**Answers:** (1) MD5 digest of the resource's bytes; (2) store and revalidate vs. forbid storing; (3) HTML fails to discover H2; (4) MVC/Servlet; (5) no; (6) open tabs/cached HTML and mixed-version instances still request H1; (7) no, they are two distinct mechanisms.

## 14. Official references

- **Spring Boot 3.3 – Servlet Web Applications / Static Content, Cache Busting:** https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- **Spring Boot 3.3 – Common Application Properties:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- **Spring Framework – MVC Static Resources:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- **Spring Framework – MVC HTTP Caching:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html
- **Spring Framework 6.1 – CacheControl Javadoc:** https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/http/CacheControl.html
- **Spring Boot – Reactive Web Applications:** https://docs.spring.io/spring-boot/reference/web/reactive.html
- **Spring Framework – WebFlux Static Resources:** https://docs.spring.io/spring-framework/reference/web/webflux/config.html
