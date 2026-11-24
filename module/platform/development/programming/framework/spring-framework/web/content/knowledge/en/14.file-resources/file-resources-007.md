# Resource Chain, Resource Versioning, and Content-Fingerprinted Paths in Spring MVC

## 1. The Problem: Static Assets Changed, Yet Clients Still See Old Content

In a web-rendering Spring MVC application, CSS, JavaScript, images, and fonts are typically cached by browsers or CDNs for speed. If the path stays unchanged across a deployment, caches may keep serving the old asset:

```text
Release A:
  HTML -> /css/site.css
  Browser caches CSS A, Cache-Control: max-age=2592000

Release B:
  HTML -> /css/site.css
  Server has CSS B bytes, browser may still use CSS A

Release B with content fingerprint:
  HTML -> /css/site-<hash-B>.css
  New URL -> new cache key -> browser downloads CSS B
```

A **content fingerprint** is an identifier computed from the **file's content bytes** and embedded into the public URL, typically right before the file extension. For example, `/css/site-e36d2e05253c6c7085a91522ce43a0b4.css`. When the file changes, the fingerprint changes; browsers never mistakenly reuse a cached response from the old URL.

The **resource chain** is Spring MVC's pipeline of `ResourceResolver` and `ResourceTransformer` components to locate, version, transform, or serve static resources. Combining the chain with `ResourceUrlProvider` and `ResourceUrlEncodingFilter`, the application can **write logical URLs** in templates while **emitting versioned URLs** to clients without renaming files in the source tree.

After this lesson, you should understand:

- `ResourceHttpRequestHandler` and static resource locations.
- Resolver chain vs transformer chain; inbound resource URL vs outbound generated URL.
- `VersionResourceResolver`, `ContentVersionStrategy`, and `FixedVersionStrategy`.
- Enabling content versioning with Spring Boot properties or Java `WebMvcConfigurer`.
- Generating fingerprinted paths via Thymeleaf, `ResourceUrlProvider`, and `ResourceUrlEncodingFilter`.
- Combining HTTP caching, multi-version deployments, and CDNs to prevent 404s.
- Testing HTML → fingerprinted URL → asset GET against an embedded Servlet container.

The runnable example baseline is **Java 17+, Spring Framework 6.2.x / Spring Boot 3.5.x, and Spring MVC Servlet**. Spring WebFlux uses separate reactive resource APIs; do not import `org.springframework.web.servlet.resource` in a WebFlux app.

## 2. Where Does Spring Boot Serve Static Files From?

In a Boot Servlet app, static resources are normally looked up in:

```text
classpath:/META-INF/resources/
classpath:/resources/
classpath:/static/
classpath:/public/
```

Examples:

| Source file | Typical logical URL |
| --- | --- |
| `src/main/resources/static/css/site.css` | `/css/site.css` |
| `src/main/resources/static/js/app.js` | `/js/app.js` |
| `src/main/resources/public/images/logo.svg` | `/images/logo.svg` |
| `src/main/resources/META-INF/resources/favicon.ico` | `/favicon.ico` |

Boot normally maps static content to `/**`. You can change the pattern with `spring.mvc.static-path-pattern` or static locations with `spring.web.resources.static-locations`. The `templates/` folder is for the template engine and is **not public by default** as static files. In executable JARs, `src/main/webapp` is not a standard choice as in WARs.

Spring MVC registers `ResourceHttpRequestHandler` for resource handlers; this handler knows how to read resources, process HTTP preconditions such as `Last-Modified`, supply media types, and run the configured resource chain.

**Never add `@EnableWebMvc` just to enable static resources in Spring Boot**: this annotation can stop Spring Boot MVC auto-configuration from applying in its default way. If you need custom MVC handlers, implement `WebMvcConfigurer` without `@EnableWebMvc`, unless you intentionally want to manage the entire MVC infrastructure yourself.

## 3. How It Works When HTML References a Fingerprinted CSS File

```text
File inside JAR:
  classpath:/static/css/site.css
                    |
Resource handler /css/** (or Boot static handler /**)
                    |
         VersionResourceResolver
                    |
         ContentVersionStrategy
                    |
    computes MD5 hex from content bytes
                    |
        ResourceUrlProvider generates URL
                    |
   /css/site-<fingerprint>.css
                    |
Browser GET /css/site-<fingerprint>.css
                    |
DispatcherServlet / ResourceHttpRequestHandler
                    |
VersionResourceResolver:
   strips hash from name, finds site.css,
   verifies hash matches current resource
                    |
PathResourceResolver reads actual file bytes
                    |
HTTP 200 + CSS + cache headers
```

Spring does **not** require physically creating a fingerprinted file on disk. The packaged file remains `site.css`; the versioned URL is resolved via the resolver mapping. The logical URL `/css/site.css` is usually still directly requestable, so set appropriate caching policies for unversioned paths too.

### Inbound vs Outbound

- **Outbound**: when rendering HTML, `ResourceUrlProvider` looks up the public versioned path for `/css/site.css`, e.g., `/css/site-abc....css`.
- **Inbound**: the client sends a GET to the public versioned path; `VersionResourceResolver` strips the version segment and checks whether it matches the actual file's content.
- **Version mismatch**: a URL with a bogus hash is normally not served by the resolver; most configurations return 404.
- **Missing file**: a version strategy does not turn a missing resource into a valid one.

If you hardcode `href="/css/site.css"` inside a **static HTML file** served raw as bytes, resource URL rewriting does not run automatically over that arbitrary text. You must use a template, helper, manifest, or build-time rewriting.

## 4. Components of the Resource Chain

### 4.1. ResourceResolver Chain

| Component | Responsibility |
| --- | --- |
| `PathResourceResolver` | Finds the underlying resource within allowed locations; usually the final resolver |
| `VersionResourceResolver` | Applies version strategies, generates and validates public URLs |
| `EncodedResourceResolver` | Selects pre-compressed resources like gzip/brotli when appropriate |
| `WebJarsResourceResolver` | Resolves versionless WebJars URLs when the matching locator dependency is present |

**Resolver order affects correctness.** When using both `EncodedResourceResolver` and `VersionResourceResolver`, Spring requires **Encoded before Version** so the content hash is computed from the **uncompressed** file, avoiding hash differences caused by gzip/brotli encoding.

Resolvers can cache lookup results as configured. `resourceChain(true)` in Java config enables resource chain caching; `spring.web.resources.chain.cache` is Boot's property for internal chain caching, not the HTTP `Cache-Control` header.

### 4.2. ResourceTransformer Chain

Transformers can alter the **representation** served. For example, `CssLinkResourceTransformer` inspects `@import` and `url(...)` inside CSS, queries the chain, and rewrites links to their public versioned URLs:

```css
@import "theme.css";

.banner {
  background-image: url("../images/banner.svg");
}
```

With the right transformer, CSS can emit references to versioned URLs. However, Spring **does not automatically parse arbitrary JavaScript strings** containing URLs, ES-module imports, dynamic `fetch()` calls, source maps, or JSON manifests. When those assets have URL-dependent logic, you may need a bundler, a fixed strategy, or an explicit transformer.

When both resolvers and transformers are needed, verify processing order and inspect the **actual returned response body**, not just source files.

## 5. ContentVersionStrategy: Byte Hashing and Fingerprinted Paths

In Spring Framework 6.x, `org.springframework.web.servlet.resource.ContentVersionStrategy` uses **MD5 hex** of the content to create a filename version. Example:

```text
Resource: /css/site.css
MD5(bytes): <32 hex chars of the real file>
Public URL: /css/site-<32 hex chars>.css
```

The MD5 of an empty file is `d41d8cd98f00b204e9800998ecf8427e`. That hash is **valid only for empty content**, not for the sample CSS snippets in this lesson. Never hardcode fake hashes into production HTML.

Characteristics:

1. Same resource bytes and strategy → same fingerprint; redeploying does not unnecessarily mint a new URL.
2. Changed bytes → usually different fingerprint; the new URL avoids old cache keys.
3. Computed from bytes, so encoding, line-ending, or comment changes also change the URL.
4. Not a security signing algorithm, tamper-proof checksum, or **Subresource Integrity (SRI)**. MD5 is unsuitable as a cryptographic source-integrity guarantee.
5. Does not minify, transpile, generate `.gz`/`.br` files, or emit a CDN deployment manifest.
6. Versioning in the URL enables invalidation; it **does not set HTTP cache lifetimes** unless cache headers are configured.

### Filename Path Versioning vs Query-String Versioning

```text
ContentVersionStrategy:
  /css/site-<hash>.css

Different manual query approach:
  /css/site.css?v=<hash>
```

Query versioning can work, yet CDN/proxy policies may ignore or normalize query parameters. Spring MVC's `ContentVersionStrategy` uses URL path filename versioning. Never describe `?v=...` as the standard output of this class.

## 6. Enabling Resource Content Fingerprinting in Spring Boot 3.5

With the default Boot MVC static handler, a minimal setup in **`src/main/resources/application.properties`**:

```properties
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**
```

Equivalent YAML:

```yaml
spring:
  web:
    resources:
      chain:
        strategy:
          content:
            enabled: true
            paths: "/**"
```

Pick **one** of properties or YAML; never configure conflicting values in both and guess precedence.

With this setup, assets in static locations managed by the handler can get versioned URLs. `/**` here is the **static resource** pattern—it does not fingerprint REST endpoint URLs.

To target only specific directories, scope the strategy to explicit URL patterns:

```properties
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/css/**,/js/**
```

To apply versioning to images/fonts referenced by CSS, ensure their locations/patterns also have versioning enabled or use an appropriate build approach.

### Internal Resource Chain Cache

```properties
spring.web.resources.chain.cache=true
```

This property controls **resource resolution caching inside Spring**, not `Cache-Control: max-age=...`. While editing files continuously in dev, disable chain caching or use Boot DevTools/proper rebuilds. In immutable production JARs, internal caching reduces lookup overhead.

### Why Is Java Config Unneeded for the Basic Example?

Boot 3.5 supports content/fixed resource strategies via properties. If you also manually add a resource handler for the same path, verify which chain and mapping actually execute: Boot properties **must not be assumed to automatically apply to every custom `ResourceHandlerRegistration`**.

## 7. FixedVersionStrategy: Version Prefix Instead of Per-File Hashes

For some assets, hashed filenames cause friction—especially JS module loaders using relative module paths. Spring supports a release-based **fixed version prefix**:

```properties
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**

spring.web.resources.chain.strategy.fixed.enabled=true
spring.web.resources.chain.strategy.fixed.paths=/js/lib/**
spring.web.resources.chain.strategy.fixed.version=v12
```

Example output:

```text
/css/site.css
    -> /css/site-<content-hash>.css

/js/lib/module.js
    -> /v12/js/lib/module.js
```

`v12` is chosen by the application/release. When JS content changes, the URL **does not change automatically** if you forget to bump the version. Changing `v12`→`v13` even when bytes did not change forces browsers to re-download unchanged files. Never configure overlapping patterns without testing that assets under `/js/lib/**` actually use the fixed strategy rather than the content strategy.

| Criterion | Content version | Fixed version |
| --- | --- | --- |
| Version value | Hash of content bytes | Predefined release string |
| Single file changes | Usually only that file's URL changes | Release version must be bumped |
| Unchanged file across deploys | URL can be reused | URL typically changes per release |
| Best suited for | CSS, standalone assets, images/fonts | JS module trees or release-based rollouts |
| Risk | Relative imports, build dependency graphs | Forgetting to bump version causes stale caches |

## 8. Complete Spring Boot 3.5 + Thymeleaf Illustrative Program

The example includes a Java 17 app, a Thymeleaf template, a CSS file, properties, and integration tests. Spring Boot manages the static resource handler, with no custom resource-handler bean in this example.

### 8.1. Directory Structure

```text
resource-chain-demo/
├─ build.gradle
└─ src/
   ├─ main/
   │  ├─ java/demo/resource/ResourceChainApplication.java
   │  └─ resources/
   │     ├─ application.properties
   │     ├─ static/css/site.css
   │     └─ templates/home.html
   └─ test/
      └─ java/demo/resource/ResourceChainApplicationTests.java
```

### 8.2. Gradle Dependencies

In a project already configured with the Boot 3.5 plugin, repositories, Java 17 toolchain, and dependency management, add this fragment:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **`build.gradle` fragment**, not the entire build file. If using Maven, add the corresponding starters via the Spring Boot BOM.

### 8.3. Properties

Create `src/main/resources/application.properties`:

```properties
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**
```

Do not also declare `@EnableWebMvc` or a `WebMvcConfigurer` for the same resource pattern. With Thymeleaf, Boot auto-configures the corresponding URL rewriting when conditions apply.

### 8.4. Java Application and Controller

Create `src/main/java/demo/resource/ResourceChainApplication.java`:

```java
package demo.resource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@SpringBootApplication
public class ResourceChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceChainApplication.class, args);
    }
}

@Controller
class HomeController {
    @GetMapping("/")
    String home() {
        return "home";
    }
}
```

**Valid single Java file:** only `ResourceChainApplication` is public; the package-private controller is discovered by Boot component scanning. `@Controller` returns the view name `home`, rather than raw text/JSON like `@RestController`.

### 8.5. Real CSS

Create `src/main/resources/static/css/site.css`:

```css
:root {
  color-scheme: light;
}

body {
  font-family: system-ui, sans-serif;
  margin: 2rem;
  color: #214e34;
}

h1 {
  font-size: 1.8rem;
}
```

This content is demo data. The MD5 in the URL depends on the **exact bytes and line endings** of the file as packaged.

### 8.6. Thymeleaf Template

Create `src/main/resources/templates/home.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Resource Chain Demo</title>
  <link rel="stylesheet" th:href="@{/css/site.css}">
</head>
<body>
  <h1>Content fingerprint in Spring MVC</h1>
  <p>Open DevTools Network to see the hashed CSS URL.</p>
</body>
</html>
```

`th:href="@{/css/site.css}"` is the logical URL. When Thymeleaf + `ResourceUrlEncodingFilter` + the resource chain work together, the HTML rendered to the browser looks like:

```html
<link rel="stylesheet"
      href="/css/site-0123456789abcdef0123456789abcdef.css">
```

This is a **format illustration**, not the real hash of the CSS above. Obtain the versioned URL from runtime HTML; never hardcode hashes in source HTML.

### 8.7. HTTP Smoke Test

```bash
./gradlew bootRun

curl -i 'http://localhost:8080/'
curl -i 'http://localhost:8080/css/site.css'
```

The first HTTP call typically returns 200 `text/html`, with a versioned `href` in the HTML. The second requests the logical URL, typically returning 200 `text/css`. Next copy the exact public CSS URL from the HTML into curl, for example:

```bash
# Replace the 32 hex chars with the actual value from the HTML response.
curl -i 'http://localhost:8080/css/site-0123456789abcdef0123456789abcdef.css'
```

The line above uses a fake hash, so it is **not guaranteed to return 200**; to succeed, use the real runtime URL. Headers like `Cache-Control`, `ETag`, and `Last-Modified` depend on handler/cache configuration; never assume enabling fingerprinting sets a one-year caching policy.

## 9. Integration Testing Through a Real Servlet Container

A unit test calling `VersionResourceResolver` directly can check hashing, yet **does not prove HTML rendering, the URL filter, and the Servlet resource handler work together**. Use `@SpringBootTest(RANDOM_PORT)` to send HTTP requests through the embedded server.

Create `src/test/java/demo/resource/ResourceChainApplicationTests.java`:

```java
package demo.resource;

import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ResourceChainApplicationTests {

    private static final Pattern VERSIONED_CSS =
            Pattern.compile("href=\"(/css/site-[0-9a-f]{32}\\.css)\"");

    @Autowired
    TestRestTemplate http;

    @Test
    void templateLinksVersionedCssWhichCanBeFetched() {
        ResponseEntity<String> page =
                http.getForEntity("/", String.class);

        assertEquals(HttpStatus.OK, page.getStatusCode());
        String html = page.getBody();
        assertNotNull(html);

        Matcher matcher = VERSIONED_CSS.matcher(html);
        assertTrue(matcher.find(), "Expected versioned CSS link");

        ResponseEntity<String> css =
                http.getForEntity(matcher.group(1), String.class);

        assertEquals(HttpStatus.OK, css.getStatusCode());
        assertNotNull(css.getBody());
        assertTrue(css.getBody().contains("font-family:"));
    }

    @Test
    void unversionedLogicalUrlStillWorksInThisDemo() {
        ResponseEntity<String> css =
                http.getForEntity("/css/site.css", String.class);

        assertEquals(HttpStatus.OK, css.getStatusCode());
        assertNotNull(css.getBody());
        assertTrue(css.getBody().contains("color-scheme:"));
    }

    @Test
    void incorrectHashDoesNotResolve() {
        String badPath =
                "/css/site-00000000000000000000000000000000.css";

        ResponseEntity<String> css =
                http.getForEntity(badPath, String.class);

        assertEquals(HttpStatus.NOT_FOUND, css.getStatusCode());
    }
}
```

Run:

```bash
./gradlew test
```

The three tests are **designed to pass** for the matching project/baseline; this reflects careful review expectations, **not an executed Gradle output**. The test checks the 32-hex hash format rather than hardcoding a single hash. If the deployment sets `server.servlet.context-path=/shop` or custom Security, update the pattern, HTTP paths, and access permissions accordingly.

To test asset changes across two releases, capture URL A from build A, modify CSS bytes, rebuild B, and capture URL B; assert the URLs differ and B serves the updated content. Never edit a static file at runtime on the same JAR expecting the chain cache to refresh itself.

## 10. Java Config When a Custom ResourceHandlerRegistry Is Needed

This section is an **alternative** to section 8's Boot auto-configuration, not code to add on top of that demo.

In a Spring MVC app, `WebMvcConfigurer` can configure a dedicated resource handler for `/assets/**`:

```java
package demo.resource;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.resource.VersionResourceResolver;

@Configuration
class AssetConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .resourceChain(true)
                .addResolver(new VersionResourceResolver()
                        .addContentVersionStrategy("/**"));
    }
}
```

Place this in a project with `src/main/resources/static/assets/`. A file `app.css` inside has logical URL `/assets/app.css` and public versioned URL `/assets/app-<hash>.css`. `resourceChain(true)` enables caching of the resolver chain; `VersionResourceResolver` performs versioning; Spring handles looking up the underlying resource from the configured locations.

**URL configuration note:** if the same app keeps Boot's default `/**` static handler alongside a custom `/assets/**` handler, verify which specific path mapping wins; never configure two conflicting version strategies.

### 10.1. CSS Link Rewriting

If a custom chain needs to rewrite `@import` or `url(...)` in CSS and does not already have the transformer:

```java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/static/assets/")
        .resourceChain(true)
        .addResolver(new VersionResourceResolver()
                .addContentVersionStrategy("/**"))
        .addTransformer(new CssLinkResourceTransformer());
```

This is a **method fragment** requiring `import org.springframework.web.servlet.resource.CssLinkResourceTransformer`. Test actual CSS responses, and avoid adding a duplicate transformer if the chain already registers one automatically.

### 10.2. Combining With EncodedResourceResolver

When precompressed gzip/brotli assets are produced by the build:

```java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/static/assets/")
        .resourceChain(true)
        .addResolver(new EncodedResourceResolver())
        .addResolver(new VersionResourceResolver()
                .addContentVersionStrategy("/**"));
```

This is a **method fragment** requiring `import EncodedResourceResolver`. **Encoded before Version** is stressed in Spring docs so the content fingerprint stays stable based on the uncompressed file. Actual `.gz`/`.br` files must exist, and you must test `Accept-Encoding`, `Content-Encoding`, and `Vary` to verify compressed variant serving. Adding the resolver does not generate compressed files.

## 11. ResourceUrlProvider and ResourceUrlEncodingFilter

### ResourceUrlProvider

Spring MVC provides `ResourceUrlProvider` as an API to construct URLs from handlers and resolver chains:

```java
@Controller
class AssetInfoController {
    private final ResourceUrlProvider resourceUrls;

    AssetInfoController(ResourceUrlProvider resourceUrls) {
        this.resourceUrls = resourceUrls;
    }

    @GetMapping("/asset-info")
    String show(Model model) {
        String publicUrl =
                resourceUrls.getForLookupPath("/css/site.css");
        model.addAttribute("cssUrl", publicUrl);
        return "asset-info";
    }
}
```

This is a **class fragment** requiring imports for `@Controller`, `@GetMapping`, `Model`, and `ResourceUrlProvider`; the `asset-info` template must exist in the project. The return value can be a versioned path or `null` if resource lookup fails. `getForLookupPath` expects an **MVC lookup path**, not an Internet URL with a host, and may need context-path or public CDN-base handling depending on the environment.

### ResourceUrlEncodingFilter

`org.springframework.web.servlet.resource.ResourceUrlEncodingFilter` wraps the response so views/helpers calling `HttpServletResponse#encodeURL` can inject resource versions into URLs at render time.

- In Spring Boot 3.5, Thymeleaf/FreeMarker usually get this filter auto-configured by Boot when an appropriate resource chain is active.
- For JSP, Spring Boot docs instruct registering the filter manually.
- For static HTML and client-side JS assembling URL strings, the filter **does not automatically find and replace arbitrary text**.
- If URLs are needed in an API/JSON manifest, invoke the provider or use a build asset manifest.

Example manual registration for JSP:

```java
@Configuration
class ResourceUrlFilterConfig {
    @Bean
    ResourceUrlEncodingFilter resourceUrlEncodingFilter() {
        return new ResourceUrlEncodingFilter();
    }
}
```

This fragment requires imports for `Configuration`, `Bean`, and `ResourceUrlEncodingFilter`. **Do not add this bean to the Thymeleaf demo where the filter is already auto-configured** under the mistaken assumption every app must declare it manually.

## 12. HTTP Caching: Resource Fingerprinting Does Not Automatically Set Cache-Control

`ContentVersionStrategy` changes URLs based on content; `Cache-Control` controls how browsers/CDNs cache responses. These are two **complementary yet independent** mechanisms.

| Mechanism | Effect |
| --- | --- |
| Fingerprinted path | Different cache key whenever asset bytes change |
| `Cache-Control: max-age` | Freshness lifetime of the response |
| `ETag` / `If-None-Match` | Conditional request if the HTTP handler provides an ETag |
| `Last-Modified` / `If-Modified-Since` | Conditional request based on resource timestamp |
| `304 Not Modified` | Allows reusing cached representation after revalidation |
| `Cache-Control: immutable` | Tells clients the asset URL will not change representation within its lifetime |
| CDN cache | Caching tier outside the app; pay attention to keys, purging, and version retention |

A Java MVC resource handler can be configured as:

```java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/static/assets/")
        .setCacheControl(
                CacheControl.maxAge(java.time.Duration.ofDays(365)))
        .resourceChain(true)
        .addResolver(new VersionResourceResolver()
                .addContentVersionStrategy("/**"));
```

This fragment requires importing `CacheControl`. **Risk:** this resource handler can also serve the unversioned logical URL `/assets/app.css`, and `max-age=365d` would apply to that response too unless differentiated. An unchanging URL with changing content is a recipe for stale caches. In production, separate policies between versioned and unversioned URLs (or restrict unversioned access/caching) and assert headers on both.

Boot properties available:

```properties
spring.web.resources.cache.cachecontrol.max-age=30d
spring.web.resources.chain.cache=true
```

The first affects **HTTP headers** emitted by the resource handler; the second affects the **in-app resource resolution cache**. Never enable a huge `max-age` globally across all static resources if some entry points or unversioned URLs still require frequent revalidation.

### HTML Documents Must Stay Fresh

Practical strategy:

```text
HTML:
  Cache-Control: no-cache (cacheable, must revalidate)
  or short TTL appropriate for the product

Versioned CSS/JS:
  Cache-Control: public, max-age=31536000, immutable
  only when URLs represent immutable bytes and old assets remain available
```

These are **architectural recommendations**, not headers emitted automatically by the resource version resolver. If HTML remains cached for a month, users may keep requesting asset URLs from an old release even after a new release deploys.

## 13. Rolling Deployments and Asset Retention — Why 404s Happen After Upgrades

Suppose two servers are serving two releases:

```text
Node A: site.css -> hash AAA
Node B: site.css -> hash BBB

HTML from A references /css/site-AAA.css
Asset request lands on B
B only has bytes matching hash BBB
=> VersionResourceResolver cannot verify hash AAA
=> may return 404
```

This is especially dangerous during rolling updates or blue-green deployments while clients still hold older HTML. Each app instance's resource chain is **not a repository of every previously released version**.

Solutions:

- Retain multi-release assets on a **shared CDN / object storage** long enough for rollbacks and transitions.
- Build/package versioned directories or manifests with retention rather than overwriting old static files in place.
- Coordinate HTML rollout with asset availability.
- Use a fixed release prefix when an asset group must deploy as a cohesive dependency tree.
- Monitor 404s on static URLs, especially hashes from prior releases.
- Never purge CDN versioned assets too early after a rollout.

Content-hashed URLs are only safe for long caching if **the same URL always represents the same bytes** and the origin can still serve it while clients need it.

## 14. JavaScript Module Imports and Source Maps

Example JS module:

```javascript
// main.js
import { greet } from "./util.js";
greet();
```

If HTML links `main-<hash>.js`, the relative import `./util.js` inside JavaScript is **not guaranteed** to be rewritten by the resource chain. `CssLinkResourceTransformer` only processes CSS `@import`/`url()`, not ES module syntax.

Options:

1. **Fixed version prefix** for the entire JS lib/module tree if relative paths must stay intact.
2. **A bundler** such as Vite, webpack, or Rollup emitting hashed files, rewritten import references, and a manifest.
3. A dedicated custom JS transformer if strongly justified and backed by thorough parser/build tests.
4. Keep unversioned module import paths with an appropriate caching policy, accepting the cache-busting trade-off.

Source maps (`.map`), web fonts, SVGs/images in CSS, `srcset`, dynamic JS `fetch`, and CDN-hosted assets also require explicit URL verification; never assume `ResourceUrlEncodingFilter` automatically intercepts all of them.

## 15. Static Content Security and Spring Security

Static resources are normally public, yet putting a file in `static/` **does not automatically make it safe to expose**. Never place private keys, credentials, database backups, sensitive config files, or script-executable user uploads in public resource locations.

When using Spring Security, allow static paths with **exact scope**:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/css/**", "/js/**", "/images/**")
            .permitAll()
        .anyRequest().authenticated());
```

This fragment requires Spring Security configuration and imports, **not present in the runnable demo**. For custom mappings like `/assets/**`, update matchers accordingly. Never open `/**` just because CSS returned 403.

An MD5 hash **does not replace HTTPS, SRI, CSP, or supply-chain protections**. When loading third-party resources, enforce proper integrity and CORS policies. For user-uploaded files, enforce path traversal, MIME, content disposition, and authorization protections independent of resource versioning.

## 16. Common Configuration Mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| HTML still shows `/css/site.css` | URL rewriting not used; link is in static HTML; filter missing | Inspect HTML source, Thymeleaf, and `ResourceUrlProvider` |
| Versioned link has hash but GET returns 404 | Wrong hash, different build bytes, wrong URL mapping/scope/CDN | Verify packaged file and actual version |
| New build changed CSS yet hash stayed old | Container still running old JAR, lookup cache/devtools stale, rebuild missed assets | Compare bytes inside the build artifact |
| Hash changed even though CSS "looks identical" | Different whitespace, line endings, encoding, or build transforms | Compare byte-for-byte |
| CSS background/font returns 404 | CSS internal links not rewritten or wrong relative path | Inspect CSS output and transformer |
| JS module imports fail | JS links are not rewritten like CSS | Use a bundler or fixed strategy |
| CSS GET returns 200 yet browser uses old styles | HTML or unversioned paths cached too long | Check `Cache-Control` and actual URLs in Network tab |
| Assets 404 during rolling deployment | New nodes lack old hash version | Shared asset store / version retention |
| All assets return 401/403 | Security matcher does not permit versioned paths | Fix the permit allowlist accurately |
| Edited CSS in dev does not update | Resource chain cache or build output stale | Disable chain cache in dev, rebuild/restart |
| JSP does not rewrite links | Missing `ResourceUrlEncodingFilter` or URL tag skips `encodeURL` | Add filter/helper/provider |
| Hash unstable with gzip/br | Wrong Encoded/Version resolver order | Put Encoded before Version |
| Adding `@EnableWebMvc` breaks Boot features | Boot MVC auto-config replaced | Use `WebMvcConfigurer` |
| Static resources vanish after JAR deploy | Using `src/main/webapp` or wrong path | Put assets in classpath static locations |
| Fingerprinted URL points to wrong host | Misaligned CDN URL, forwarded proxy, or context-path config | Inspect external base URL configuration |

## 17. Checking Spring Framework and Boot Versions

| Common version | Key thing to remember |
| --- | --- |
| Spring Framework 5.x / Boot 2.x | Resource chain exists; very old Boot versions used `spring.resources.*` instead of `spring.web.resources.*` |
| Spring Framework 6.x / Boot 3.x | Java 17+, `spring.web.resources.chain.strategy.content.*` properties and Thymeleaf URL rewriting as shown |
| Spring Framework 7.x / Boot 4.x | Resource chain and content/fixed strategies remain; Boot 4 reference continues documenting `spring.web.resources.chain.strategy.*`; starter/test infrastructure may differ |

Never copy code from WebFlux's `org.springframework.web.reactive.resource` package when using MVC's `org.springframework.web.servlet.resource`. Class names match, yet APIs and return types differ.

When upgrading Boot 3→4, verify Spring MVC starters, handler registration, resource chains, template filters, URL rewriting, cache headers, Security rules, WebJars locators, and integration tests. Do not stop at checking compilation; run real HTTP tests.

## 18. Production Deployment Checklist

- [ ] Clearly identify the static asset owner: Spring MVC, bundler, object storage, or CDN.
- [ ] Pick one primary versioning strategy and avoid accidental double-hashing.
- [ ] Content strategy enabled for appropriate patterns/locations; fixed strategy for matching assets.
- [ ] Logical URLs from templates/providers are rewritten; MD5 hashes are never hardcoded.
- [ ] Version resolver validates inbound URLs, with a test proving invalid hashes return 404.
- [ ] Resource resolver ordering is right, especially Encoded before Version.
- [ ] CSS internal links, JS modules, fonts, source maps, and CDN paths are tested.
- [ ] Cache headers for HTML, versioned, and unversioned assets are separated appropriately.
- [ ] Old assets are retained long enough across rolling deployments, CDNs, caches, and rollbacks.
- [ ] Spring Security permits only the static paths meant to be public.
- [ ] No secrets, configs, or arbitrary uploads reside in static locations.
- [ ] Integration tests cover HTML → fingerprinted `href` → asset GET, plus post-rebuild checks.
- [ ] Monitoring tracks cache hit ratio, static 404s, and wrong-hostname/prefix URLs.

## 19. Practice Exercises

1. Change one character in the example's `site.css` and rebuild. Does the URL in HTML change? Why does the hash depend on line endings?
2. Distinguish outbound `ResourceUrlProvider` from inbound `VersionResourceResolver`.
3. Why can `@{/css/site.css}` in Thymeleaf be rewritten while a hardcoded `href` in `static/index.html` cannot?
4. When adding `spring.web.resources.cache.cachecontrol.max-age=365d`, what risk does the logical URL `/css/site.css` carry?
5. If release A's HTML points to `site-A.css` but the request routes to node B holding only release B's bytes, why can a 404 happen?
6. Write a test verifying the CSS link in the HTML page with a regex instead of a hardcoded MD5.
7. Try `CssLinkResourceTransformer` with CSS `url("../images/logo.svg")` and inspect the response.
8. With Java config containing both `EncodedResourceResolver` and `VersionResourceResolver`: in what order must they be registered?
9. When ES modules use relative imports, why can `FixedVersionStrategy` or a bundler manifest work better than per-file fingerprinting?
10. A project already uses Vite to emit `app-<hash>.js`. Should you also add Spring `VersionResourceResolver`? Analyze the resulting URLs and cost.
11. With Security enabled, why might versioned `/css/site-<hash>.css` return 403 even though the file exists? Fix the matcher without exposing the API.
12. Contrast JVM resource-chain caching with browser HTTP caching, and design tests for each.

## 20. Official References

- [Spring Framework 6.2 — Static Resources](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/static-resources.html): `ResourceHttpRequestHandler`, resource chain, version resolver, and URL provider.
- [Spring Boot 3.5 — Servlet Static Content](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): content/fixed strategies, default locations, Thymeleaf/FreeMarker integration.
- [Spring Boot 4 — Servlet Static Content](https://docs.spring.io/spring-boot/4.0/reference/web/servlet.html): resource chain configuration and next-generation compatibility.
- [Spring Framework 6.2 — ContentVersionStrategy](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/resource/ContentVersionStrategy.html): MD5 fingerprinting.
- [Spring Framework 6.2 — VersionResourceResolver](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/resource/VersionResourceResolver.html): inbound/outbound versioned paths.
- [Spring Framework 6.2 — ResourceUrlProvider](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/resource/ResourceUrlProvider.html): generating public static URLs.
- [Spring Framework 6.2 — CssLinkResourceTransformer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/resource/CssLinkResourceTransformer.html): CSS `@import` and `url()`.
- [Spring Framework 6.2 — ResourceUrlEncodingFilter](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/resource/ResourceUrlEncodingFilter.html): link rewriting during response encoding.
- [Spring MVC — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): `Cache-Control` and conditional requests.
