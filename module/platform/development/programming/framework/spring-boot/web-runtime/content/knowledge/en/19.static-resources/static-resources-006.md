# WebJars and resources packaged inside libraries — Spring Boot web runtime

## 1. Understanding the essence

In a Spring Boot application, images, CSS, JavaScript, fonts, icons, and static files do not have to live inside the source directory of the **main application**. They can also reside in **JAR dependencies** on the runtime classpath. Spring MVC and Spring WebFlux include mechanisms to look up resources from the classpath and serve their contents over HTTP, enabling a UI library to carry shared assets for multiple applications.

**WebJars** are a convention for packaging browser-side web libraries (such as jQuery or Bootstrap) as Maven/Gradle JAR artifacts. The key distinguishing feature of a WebJar is its path layout organized by library name and version under `META-INF/resources/webjars/`. Spring Boot already provides default HTTP mapping for this type of resource.

Distinguish clearly:

- **Java library containing resources:** any JAR dependency containing files in static locations configured for Spring Boot lookup, notably `META-INF/resources/`; not required to be a WebJar.
- **WebJar:** a JAR packaged according to the standard layout for a frontend library, typically exposed at URLs like `/webjars/{library-name}/{version}/{file}`.
- **Static resource handler:** the Spring MVC/WebFlux component that accepts a URL, locates a `Resource` on the classpath or configured locations, and writes bytes and HTTP headers. This handler **is not a REST controller**.
- **Embedded server:** Tomcat/Jetty/Reactor Netty accepts connections and passes requests to the Spring web stack; the server does not understand WebJars conventions on its own unless the framework/configuration provides a matching resource mapping.

Example of a dependency JAR containing:

```text
some-ui-library-1.0.0.jar
└── META-INF/
    └── resources/
        └── shared-ui/
            ├── theme.css
            └── logo.svg
```

With default Spring Boot configuration, the web application can serve two URLs:

```text
GET /shared-ui/theme.css
GET /shared-ui/logo.svg
```

Meanwhile, a jQuery WebJar version 3.7.1 typically has the structure:

```text
jquery-3.7.1.jar
└── META-INF/
    └── resources/
        └── webjars/
            └── jquery/
                └── 3.7.1/
                    └── jquery.min.js
```

And the corresponding URL:

```text
GET /webjars/jquery/3.7.1/jquery.min.js
```

The path starting with `/webjars/` above is the **public URL**, while `META-INF/resources/webjars/` is the **internal JAR path**. Do not insert `META-INF/resources` into browser URLs.

## 2. Why are resources inside dependency JARs found?

There are three essential conditions:

1. **The dependency exists at runtime.** Maven/Gradle declarations must place the JAR on the runtime classpath; a dependency declared only in `test` scope is unavailable in production.
2. **Files reside at the right path inside the JAR.** `META-INF/resources/` is a location served by Boot by default. For WebJars, the inner path is normally `META-INF/resources/webjars/{library}/{version}/...`.
3. **The application has a resource handler for that URL.** Under normal Spring Boot MVC/WebFlux auto-configuration, default handlers are registered; if you disable default mappings or replace all MVC configuration, you must restore the mapping manually.

This is a classpath mechanism. It does not require manually unpacking dependencies into `src/main/resources/static`, writing a controller returning byte arrays, or relying on external source directories at runtime.

### Default static locations

Spring Boot supports the following resource directories on the **classpath**:

| Path inside the classpath | Example URL with default config | Commonly used for |
| --- | --- | --- |
| `/static/site.css` | `/site.css` | Main application assets |
| `/public/help.html` | `/help.html` | Static pages, public documentation |
| `/resources/banner.svg` | `/banner.svg` | An alternative static location |
| `/META-INF/resources/shared-ui/theme.css` | `/shared-ui/theme.css` | Assets packaged inside library JARs |
| `/META-INF/resources/webjars/jquery/3.7.1/jquery.min.js` | `/webjars/jquery/3.7.1/jquery.min.js` | Versioned WebJars |

Examples in the table assume unchanged `server.servlet.context-path`, web base path, static patterns, and resource locations. `/resources` in the table is **a directory on the classpath**, not a mandatory URL prefix.

In Maven/Gradle projects, `src/main/resources/static` and `src/main/resources/META-INF/resources` are packaged onto the classpath during build. In a Spring Boot JAR project:

- Application classes and application resources usually live in `BOOT-INF/classes/`;
- Dependency JARs usually live in `BOOT-INF/lib/`;
- The Spring Boot launcher builds the runtime classpath across both, allowing resource handlers to read from nested JARs inside the executable JAR.

`src/main/webapp` is a familiar layout for traditional WAR/Servlet builds, **not a recommended location when building a Spring Boot executable JAR**. Do not place WebJar files or shared assets there expecting them to be packaged automatically inside a JAR.

## 3. Runtime processing of a WebJar request

Logical diagram:

```text
Browser:
GET /webjars/jquery/3.7.1/jquery.min.js
                  |
           Embedded HTTP server
                  |
        Spring MVC / WebFlux router
                  |
      Resource handler for /webjars/**
                  |
       Classpath resource resolution
                  |
META-INF/resources/webjars/jquery/3.7.1/jquery.min.js
         inside dependency JAR
                  |
    HTTP 200 + Content-Type + cache headers
                  |
                Browser
```

In **Spring MVC**, Spring Boot configures `ResourceHttpRequestHandler` via `ResourceHandlerRegistry`/`HandlerMapping` infrastructure. In **Spring WebFlux**, the corresponding file-serving class is `ResourceWebHandler`. Both can locate static resources on the classpath and support WebJars.

The handler classes serve content by static path, detect content types, support `Last-Modified`/conditional requests, and emit cache headers according to configuration. Having the version in the URL enables longer caching when an appropriate policy is configured; Spring does not automatically mark responses “immutable” without caching configuration.

**Important:** JavaScript is returned by the server as **bytes** for the browser to execute. Spring Boot does not execute JavaScript libraries on the JVM merely because a WebJar is on the classpath.

### Where do MVC and WebFlux differ?

| Aspect | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Resource handler | `ResourceHttpRequestHandler` | `ResourceWebHandler` |
| Typical pattern | `/**` for static resources | `/**` for static resources |
| WebJars default | `/webjars/**` | `/webjars/**` |
| Property to change WebJars pattern | `spring.mvc.webjars-path-pattern` | `spring.webflux.webjars-path-pattern` |
| Property to change static pattern | `spring.mvc.static-path-pattern` | `spring.webflux.static-path-pattern` |
| Default locations | `classpath:/static/`, `/public/`, `/resources/`, `/META-INF/resources/`, and corresponding servlet context root | Similar classpath locations, without relying on a Servlet root |
| Customization | `WebMvcConfigurer#addResourceHandlers` | `WebFluxConfigurer#addResourceHandlers` |

Do not infer that WebFlux only serves JSON APIs and cannot use WebJars: both stacks include static resource handlers. Conversely, do not choose WebFlux merely because an app loads many JavaScript files: that choice is about web processing models, not frontend asset packaging.

## 4. Two WebJars URL styles: versioned and versionless

### 4.1. Versioned URLs — default preference

Suppose the dependency is jQuery 3.7.1:

```html
<script src="/webjars/jquery/3.7.1/jquery.min.js"></script>
```

The path matches the layout inside the WebJar. Spring Boot can serve it via the default mapping **without adding a WebJars locator**.

Pros: explicit about which artifact version is running, minimal lookup overhead, suitable for version-based caching, and easy to troubleshoot 404s. Cons: upgrading a WebJar requires updating the version in URLs as well (or using a suitable URL generation mechanism).

### 4.2. Versionless URLs — require a locator

URL format:

```html
<script src="/webjars/jquery/jquery.min.js"></script>
```

This format **does not automatically work in every project solely because `jquery` was added to Maven**. In modern Spring Framework, `org.webjars:webjars-locator-lite` must be on the classpath for Spring to register `LiteWebJarsResourceResolver` to resolve versions. With Boot 3.5.16, you can add the dependency:

```xml
<dependency>
    <groupId>org.webjars</groupId>
    <artifactId>webjars-locator-lite</artifactId>
    <version>1.1.4</version>
</dependency>
```

This is an **additional dependency snippet inside `<dependencies>`**, not a standalone POM. The locator version shown is an example released artifact; in production, verify compatibility with your Spring version.

When the locator is active, a versionless request can be mapped to the file inside the versioned WebJar. Do not confuse “the browser automatically knows the version” with “a server-side resource resolver looks up the version”. Using **versioned URLs** generally remains simpler.

**Upgrade note:** very old documentation may refer to `webjars-locator-core` or `webjars-locator`. Check the Spring Framework/Boot version you use; in modern documentation, the indicated mechanism is `webjars-locator-lite`.

## 5. Runnable example: Spring Boot MVC loading jQuery from a WebJar

Illustrative example with **Java 17+**, **Maven**, and **Spring Boot 3.5.16** so APIs and starters align. jQuery version 3.7.1 is pinned for path comparison; this does not mean it is the latest version suited to every project. For new systems, select a supported Spring Boot version and update dependencies according to security policies.

### 5.1. Project structure

```text
webjars-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/webjarsdemo/
        │       └── WebjarsDemoApplication.java
        └── resources/
            └── static/
                ├── index.html
                └── css/
                    └── site.css
```

### 5.2. Complete `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webjars-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.webjars</groupId>
            <artifactId>jquery</artifactId>
            <version>3.7.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-web` brings in Spring MVC and default embedded Tomcat; `org.webjars:jquery:3.7.1` puts jQuery's JS files into a **dependency JAR** on the runtime classpath. No `@EnableWebMvc` or extra resource handler is needed for versioned URLs.

### 5.3. Runnable Java main

File `src/main/java/com/example/webjarsdemo/WebjarsDemoApplication.java`:

```java
package com.example.webjarsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebjarsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebjarsDemoApplication.class, args);
    }
}
```

No `@RestController` is required to serve `/index.html`, CSS, or WebJars. This is a key takeaway of this lesson: **static resources are mapped by the web infrastructure**, not by custom Java controllers.

### 5.4. HTML and CSS

File `src/main/resources/static/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WebJars demo</title>
  <link rel="stylesheet" href="/css/site.css">
</head>
<body>
  <h1>Static resources from classpath</h1>
  <p id="webjar-status">Checking library...</p>

  <script src="/webjars/jquery/3.7.1/jquery.min.js"></script>
  <script>
    const statusElement = document.getElementById("webjar-status");
    statusElement.textContent = window.jQuery
        ? "jQuery " + window.jQuery.fn.jquery + " loaded"
        : "Failed to load jQuery";
  </script>
</body>
</html>
```

File `src/main/resources/static/css/site.css`:

```css
body {
  font-family: system-ui, sans-serif;
  max-width: 42rem;
  margin: 3rem auto;
  padding: 0 1rem;
}
h1 { color: #214d87; }
```

These are three resources from different origins: HTML and CSS sit inside the application, while jQuery JS comes from the `org.webjars:jquery` dependency. Spring Boot serves all of them over HTTP.

### 5.5. Build, run, and output

In the directory containing `pom.xml`, run with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

Open `http://localhost:8080/`. Once the script finishes loading, the `<p>` text will be:

```text
jQuery 3.7.1 loaded
```

Check directly:

```bash
curl -I http://localhost:8080/
curl -I http://localhost:8080/css/site.css
curl -I http://localhost:8080/webjars/jquery/3.7.1/jquery.min.js
```

In the default demo, these URLs should return **HTTP 200**. Specific headers like `Cache-Control`, `ETag`, `Last-Modified`, and `Content-Length` vary by configuration and server, so no fixed header set is prescribed.

Build the executable JAR:

```bash
mvn clean package
java -jar target/webjars-demo-1.0.0.jar
```

There is no need to copy the jQuery library into an external frontend directory when running the JAR. Inside the executable JAR, the dependency is normally kept under `BOOT-INF/lib/jquery-3.7.1.jar`, and the Spring Boot launcher builds the classpath so Spring locates the resources.

On Windows PowerShell, use `curl.exe` if the `curl` alias does not behave as expected. If port 8080 is busy, run with `--server.port=8081` after the JAR name and adjust the port in the test URLs.

### 5.6. What happens when the dependency is absent?

If you remove `org.webjars:jquery` while HTML still points to `/webjars/jquery/3.7.1/jquery.min.js`, the WebJar URL normally returns **404** (in a demo without Spring Security). `index.html` and `site.css` still load because they belong to the main application's resources.

If you restore the dependency yet use the wrong filename or wrong version in the URL, you also get 404. This is a quick way to check the difference between a **declared dependency** and the **actual path inside the dependency**.

## 6. Packaging shared assets in your own library JAR

WebJars suit third-party frontend libraries. However, when multiple internal apps share logos, a CSS design system, icons, small JS files, or branded stylesheets, you can create your own **asset-containing JAR** following the `META-INF/resources` convention. This JAR does not need any Java classes.

### 6.1. Creating the `brand-assets` library project

Beside `webjars-demo`, create the directory:

```text
brand-assets/
├── pom.xml
└── src/
    └── main/
        └── resources/
            └── META-INF/
                └── resources/
                    └── brand-assets/
                        └── theme.css
```

Complete `brand-assets/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>brand-assets</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
```

File `brand-assets/src/main/resources/META-INF/resources/brand-assets/theme.css`:

```css
.brand-highlight {
  background: #f2f6fd;
  border-left: 4px solid #214d87;
  border-radius: 0.25rem;
  padding: 1rem;
}
```

Inside `brand-assets`:

```bash
mvn clean install
```

This packages the JAR and installs `com.example:brand-assets:1.0.0` into your local Maven repository. Because this is a resource-only JAR, no Java classes are required. Verify:

```bash
jar tf target/brand-assets-1.0.0.jar
```

The listing must contain the **exact** path:

```text
META-INF/resources/brand-assets/theme.css
```

### 6.2. Using the library in the Spring Boot application

In `webjars-demo/pom.xml` from section 5, add the following dependency **inside `<dependencies>`**:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>brand-assets</artifactId>
    <version>1.0.0</version>
</dependency>
```

This is an addition to the **existing** POM, not a replacement POM. Next, in the application's `src/main/resources/static/index.html`, add the CSS link inside `<head>`:

```html
<link rel="stylesheet" href="/brand-assets/theme.css">
```

And you can update the existing `<h1>` to:

```html
<h1 class="brand-highlight">Static resources from classpath</h1>
```

The HTML edits above are **additions/replacements for the section 5 file**, not a second complete HTML document.

Restart from `webjars-demo`:

```bash
mvn clean package
java -jar target/webjars-demo-1.0.0.jar
```

Request:

```bash
curl -I http://localhost:8080/brand-assets/theme.css
```

When the dependency is on the runtime classpath and static mappings are uncustomized, the URL is expected to return **200**. The CSS file resides inside `brand-assets-1.0.0.jar`, not inside the main app's `src/main/resources/static`.

Inspect the executable JAR:

```bash
jar tf target/webjars-demo-1.0.0.jar
```

The listing normally shows `BOOT-INF/lib/brand-assets-1.0.0.jar` and `BOOT-INF/lib/jquery-3.7.1.jar`. Running `jar tf` on the outer JAR shows only **nested JAR names**; to inspect inside a nested dependency, inspect the library JAR individually as in the previous step. Do not conclude the library is missing just because `META-INF/resources/brand-assets/theme.css` does not appear at the top level of the executable JAR.

### 6.3. When should you build a WebJar instead of a plain assets JAR?

If you distribute **an independently named and versioned JS/CSS library** and want consumers to reference standard `/webjars/{library}/{version}/...` paths with clean dependency upgrades, package it with the WebJars structure. If you only need shared internal resources under a custom prefix, `META-INF/resources/brand-assets/` suffices.

There is no need to turn every internal CSS file into a WebJar. Pick a layout that gives consumers predictable URLs and avoids package namespace collisions with other libraries.

## 7. Changing HTTP paths or resource locations

### 7.1. Relevant Spring Boot properties

Example when you **need** to customize patterns (do not add these to the example above unless updating URLs):

```properties
# Spring MVC: change URL for regular static resources
spring.mvc.static-path-pattern=/assets/**

# Spring MVC: change URL specifically for WebJars
spring.mvc.webjars-path-pattern=/vendor/**

# Equivalent configuration in WebFlux:
# spring.webflux.static-path-pattern=/assets/**
# spring.webflux.webjars-path-pattern=/vendor/**
```

These are **optional examples**, incompatible with the paths in sections 5–6 unless you also update the HTML URLs:

- `spring.mvc.static-path-pattern=/assets/**` turns `/css/site.css` into `/assets/css/site.css` under the new mapping.
- `spring.mvc.webjars-path-pattern=/vendor/**` changes WebJar paths to `/vendor/jquery/3.7.1/jquery.min.js`.
- `spring.webflux.*` properties are for WebFlux and do not replace MVC properties when the application runs MVC.

The `spring.web.resources.static-locations` property **replaces the default static locations list**. Changing it to only `classpath:/custom/` can inadvertently stop `/brand-assets/theme.css` or `/index.html` from being served from default locations. Explicitly include all locations you want to keep, or add a separate resource handler.

### 7.2. Adding a dedicated resource handler for one library

In a **Spring MVC** application, if you want to serve CSS from the `brand-assets` JAR at `/design/theme.css`, you can add the following Java class (a complete class placed in a subpackage of `com.example.webjarsdemo`):

```java
package com.example.webjarsdemo;

import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class BrandResourceConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/design/**")
                .addResourceLocations("classpath:/META-INF/resources/brand-assets/")
                .setCacheControl(CacheControl.maxAge(Duration.ofDays(7)));
    }
}
```

With the section 6 dependency, `/design/theme.css` maps to `META-INF/resources/brand-assets/theme.css`. The rest of MVC auto-configuration remains intact when using `WebMvcConfigurer` **without `@EnableWebMvc`**.

In WebFlux, implement the same idea with `WebFluxConfigurer` and `org.springframework.web.reactive.config.ResourceHandlerRegistry`; do not copy MVC imports verbatim into WebFlux.

**Note:** Never map `classpath:/` or an overly broad prefix to a public URL. Point handlers strictly to **directories intended to be public**, and review what files consumers can actually request.

## 8. Caching, versioning, and safe deployment URLs

WebJars with versions in the path help browsers distinguish versions:

```text
/webjars/jquery/3.7.1/jquery.min.js
/webjars/jquery/4.0.0/jquery.min.js
```

If you change the jQuery dependency version while HTML retains the old path, browsers may receive **404** or load an older version from a stray classpath dependency. Therefore, dependency updates and URLs must be tested together.

### Appropriate caching mechanisms

- **URLs with versions or content fingerprints:** you can consider long `Cache-Control` lifetimes when contents at that URL are guaranteed immutable.
- **Unversioned URLs such as `/brand-assets/theme.css`:** if contents change while the URL stays fixed, long caches can trap browsers on stale CSS. Use shorter cache durations or content-hash versioning.
- **`index.html`:** generally needs a more flexible cache policy than fingerprinted assets so new HTML can point to new asset versions.

Spring MVC/WebFlux provides a resource chain with `VersionResourceResolver`. Spring Boot also offers properties:

```properties
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/css/**
```

This is an **illustrative configuration** for a content-hash strategy on CSS paths matching the pattern; ensure HTML/template URL generation emits versioned URLs. Simply enabling the strategy **does not rewrite hardcoded URL strings in static HTML**. View engines and `ResourceUrlProvider`/rewriting mechanisms handle this; verify the output in a browser.

Do not apply a very long `max-age` across all of `/**` without distinguishing immutable assets from HTML. With WebJars, versioned URLs straight from the artifact make rollout easier to control.

## 9. Security and scope of exposed resources

Any file placed under `META-INF/resources/` or another path mapped by a resource handler should be **considered public HTTP content**. Do not place private keys, JWT secrets, sensitive configuration files, internal source maps containing restricted details, customer data, or backups in these paths.

Key points to remember:

1. **Spring Security** may require authentication for `/webjars/**`, `/css/**`, or `/brand-assets/**` if security rules restrict them. Status **401/403** indicates an authorization issue, not a missing resource. Only call `permitAll()` on assets intended to be public, keeping patterns properly scoped.
2. **Classpath JARs are content sources:** third-party web dependencies must be vetted for licenses, provenance, security updates, and the dependency tree. Having a WebJar in a JAR does not prove the JavaScript itself is safe.
3. **Content Security Policy (CSP):** if your policy disallows inline JavaScript, the demo's inline `<script>` block will be blocked; in real apps, move your scripts into static files and declare an appropriate CSP. Self-hosting WebJars from the same origin avoids some CDN dependencies, yet CSP still applies.
4. **CORS:** not always needed. When browsers load JS/CSS from the same origin, ordinary static requests need no special CORS setup. When assets are loaded cross-origin (especially fonts or modules), review CORS, CSP, and deployment settings.
5. **Do not use resource handlers as arbitrary file servers:** configure public locations and patterns intentionally; never let clients select arbitrary filesystem paths via request parameters.

Using WebJars also does not replace full frontend tooling: for large projects needing tree-shaking, bundling, source maps, and complex module graphs, Node/npm + a frontend bundler may be a better fit.

## 10. Troubleshooting 404s and common issues

| Symptom | Possible cause | Check and fix |
| --- | --- | --- |
| `/webjars/jquery/3.7.1/jquery.min.js` returns 404 | WebJar missing at runtime, wrong version, or wrong file path | Inspect `pom.xml`/Gradle dependency tree and actual paths inside the JAR |
| Versioned URL works, `/webjars/jquery/jquery.min.js` returns 404 | No locator installed to resolve versionless URLs | Use versioned URLs, or add a compatible `webjars-locator-lite` |
| Works in IDE, executable JAR fails to load CSS | Dependency has wrong scope, was excluded, or packaged improperly | Inspect `BOOT-INF/lib`, library JARs, and test with real `java -jar` |
| CSS in main project works, CSS in library JAR fails | File is outside served location or prefix name is wrong | Run `jar tf brand-assets-1.0.0.jar` and verify `META-INF/resources/...` |
| Returns 401/403 instead of 404 | Security rules apply to assets | Configure security for public URLs and inspect the filter chain |
| Returns 200 yet browser ignores CSS | Wrong `<link>`, content type, stale cache, CSP, or CSS specificity | Check Network tab, Response/`Content-Type`, Console, and Computed styles |
| Default mappings vanished after adding `@EnableWebMvc` | Application took over MVC configuration from Boot | Remove the annotation if only customizing; use `WebMvcConfigurer` |
| Changing `spring.web.resources.static-locations` broke index/assets | Property replaced default locations | List all desired locations or add a separate handler |
| Changed `spring.mvc.webjars-path-pattern`, HTML still uses `/webjars/...` | Requests no longer match the new WebJar pattern | Update URLs to match the configured pattern |
| Deployed under context path `/app`, origin-relative `/webjars/...` fails | Origin-relative URL skips `/app` | Generate context-aware URLs in templates (e.g., Thymeleaf `@{/webjars/...}`) or configure base properly |
| Assets from two dependencies share the same path | Resource name collision on the classpath | Use distinct namespace prefixes; inspect dependency tree and JAR artifacts |
| Works in dev, production cache still shows stale JS/CSS | Unchanged URL with overly long cache | Version/fingerprint assets and align cache policies |

### Short, ordered diagnostic workflow

1. **Grab the actual URL** from the Network tab, including context path, URL encoding, and HTTP status. Do not look only at the source template string.
2. **Verify the runtime dependency**: Maven dependency tree, POM/Gradle, and build output. For WebJars, confirm `artifactId`, version, and file path.
3. **Verify the path inside the JAR** with `jar tf`; trace from `META-INF/resources` to the URL.
4. **Confirm stack and mappings**: MVC vs. WebFlux, `spring.mvc.*` vs. `spring.webflux.*`, custom resource handlers, and `spring.web.resources.*`.
5. **Distinguish error classes:** 404 comes from mapping/path/packaging; 401/403 from Security; 200 with broken UI from cache, CSP, JS execution, or MIME type.
6. **Run the packaged JAR** as deployed and inspect with `curl -I`/browser rather than relying solely on files existing in project sources.

You do not need to write a `@GetMapping("/webjars/...")` controller to fix WebJar 404s in normal circumstances. A manual controller can mask root causes and forfeit resource handler caching and conditional request support.

## 11. When to choose WebJars, a custom assets JAR, or a frontend build?

| Option | Best suited for | Pros | Trade-offs |
| --- | --- | --- | --- |
| **WebJar dependency** | Server-rendered pages, admin UIs, third-party JS/CSS pinned via Maven | JVM build packages frontend assets, offline deployment, versioned URLs | JS/asset ecosystem may lag behind npm; must monitor library versions |
| **Custom assets JAR** | Design systems, shared icons/CSS/logos across multiple Spring Boot services | Single reusable artifact, Maven-versioned, centralized asset governance | Must define your own namespaces, URLs, and caching policies |
| **App's `src/main/resources/static`** | Small number of assets belonging to one app | Simple, no extra dependency | Less convenient to share across multiple apps |
| **npm + Vite/Webpack/Rollup** | Large SPAs, ES modules, bundling, tree-shaking, frontend optimization | Powerful frontend tooling, code splitting, asset optimization | More complex build pipeline, must integrate build outputs with Boot/CDN |
| **CDN** | Public assets needing global distribution | Reduces server load and leverages edge caching | Adds external dependency; must manage CSP/SRI, availability, versions, and caching |

Options can be combined. For example, CI bundles frontend assets and copies final artifacts into the backend's `static` folder; or a library JAR distributes only approved built files. WebJars are not tied specifically to Spring MVC: JAR contents can be served by any runtime with appropriate resource mappings.

## 12. Practice questions

1. **Given a WebJar `jquery-3.7.1.jar`, what is the default URL to load `jquery.min.js`?**  
   `/webjars/jquery/3.7.1/jquery.min.js`, provided the resource has that exact name/path in the JAR and Boot keeps default mappings.

2. **Why does the URL not include `META-INF/resources`?**  
   Because that is an internal classpath resource location; Spring's resource handler maps the remaining path segment to the public URL.

3. **Can a `brand-assets` JAR with no Java classes serve CSS?**  
   Yes, if it contains `META-INF/resources/brand-assets/theme.css`, is on the runtime classpath, and Boot has a matching mapping.

4. **Is adding a WebJar enough for versionless URLs to work automatically?**  
   Not necessarily. In modern Spring, versionless resolution requires `webjars-locator-lite`; versioned URLs need no locator.

5. **Why does removing `@EnableWebMvc` often fix WebJar 404 errors?**  
   Because `@EnableWebMvc` shifts MVC configuration control to the application instead of Boot auto-configuration; Boot's default resource mappings may no longer be registered.

6. **What is the difference between 404 and 403 when loading CSS?**  
   404 usually means the URL/resource was not found; 403 means the request was denied by security or an access policy. Inspect the response and filter chain before tweaking Maven.

7. **How do you confirm a resource is present in an executable JAR?**  
   Inspect the original dependency JAR with `jar tf`; inspect the executable JAR to confirm the nested dependency sits in `BOOT-INF/lib`; then call the runtime URL.

8. **Does `/webjars/jquery/3.7.1/jquery.min.js` automatically force browsers to cache for a year?**  
   No. Having a version makes long caching safer to enable; HTTP cache policies still must be configured and tested.

## 13. Project adoption checklist

- [ ] Choose WebJar, custom assets JAR, or application `static` based on reuse scope.
- [ ] Pin dependency versions and verify artifacts exist and meet license/security policies.
- [ ] Confirm files exist in the JAR under `META-INF/resources/...` with `jar tf`.
- [ ] Use URLs matching actual paths in the JAR, preferring versioned WebJar URLs.
- [ ] Do not enable `@EnableWebMvc` if you only need additional resource handlers.
- [ ] Check `spring.web.resources.*` and MVC/WebFlux pattern properties before altering mappings.
- [ ] Ensure assets are genuinely public; never put secrets inside mapped directories.
- [ ] Choose distinct cache policies for HTML vs. versioned/fingerprinted assets.
- [ ] Test under real context paths and reverse proxies; avoid hardcoding wrong root URLs.
- [ ] Run both Maven dev mode and the executable JAR; inspect HTTP responses and the Network tab.

## 14. Official references

- [Spring Boot 3.5 — Servlet Web Applications / Static Content / WebJars](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot — Reactive Web Applications / Static Content](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Framework — MVC Static Resources and WebJars locator](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html)
- [Spring Framework — WebFlux Static Resources](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [WebJars — Documentation](https://www.webjars.org/documentation)
- [Maven Central — WebJar jQuery 3.7.1](https://central.sonatype.com/artifact/org.webjars/jquery/3.7.1)
- [Spring Boot — Maven executable JAR](https://docs.spring.io/spring-boot/3.5/how-to/build.html)

**Key takeaway:** WebJars bring frontend libraries into **dependency JARs** using the standard `META-INF/resources/webjars/...` path; Spring Boot's resource handler exposes them at `/webjars/**`. Shared resources under `META-INF/resources/{namespace}/...` in **any library JAR** can likewise be served at the matching HTTP path. Always verify **classpath, internal JAR paths, resource mappings, security, and caching** during deployment.
