# The static, public, resources, and META-INF/resources directories on the classpath

## 1. Objectives and scope

**Static resources** are pre-existing files that are usually returned as-is rather than dynamically generated for each request: HTML, CSS, JavaScript, images, SVG, fonts, text documents, and so on. In a **Spring Boot Web MVC** application using the default configuration, you can place these files in four locations on the **classpath**:

1. `classpath:/static/`
2. `classpath:/public/`
3. `classpath:/resources/`
4. `classpath:/META-INF/resources/`

The four locations are **file lookup sources**, not four mandatory URL prefixes. By default, Spring MVC maps static resources to the URL pattern `/**`; the names `static`, `public`, `resources`, or `META-INF/resources` usually **do not appear** in the URL returned to the browser.

After this lesson, you will be able to:

- Explain what the `classpath` is in a Java/Spring Boot application and the actual locations of the four directories in the source structure.
- Map file paths accurately to HTTP request URLs.
- Run a Spring Boot application with resources in all four places and verify it when running via Maven or as an executable JAR.
- Distinguish static resources from `templates`, `application.properties`, API controllers, and the `src/main/webapp` directory.
- Understand the impact of `spring.mvc.static-path-pattern`, `spring.web.resources.static-locations`, security, and duplicate resource names.
- Diagnose cases resulting in 404, 401/403, stale files due to caching, or missing assets after packaging.

The main examples use **Spring Boot 3.3.x, Java 17+, Spring MVC, embedded Tomcat, and Maven**. With WebFlux, the four classpath sources are similar, though the handler and URL mapping property differ (section 10).

## 2. What is the classpath, and why are there two "resources" names?

The **classpath** is the set of directories and JARs where the Java class loader can look up classes and resources at runtime. In a typical Maven project layout:

~~~text
assets-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/                          <- Java source code
        │   └── com/example/assetsdemo/
        │       └── AssetsDemoApplication.java
        └── resources/                     <- source resources root
            ├── application.properties
            ├── static/                    <- classpath:/static/
            ├── public/                    <- classpath:/public/
            ├── resources/                 <- classpath:/resources/
            └── META-INF/
                └── resources/             <- classpath:/META-INF/resources/
~~~

**The two segments named `resources` have different meanings:**

- `src/main/resources/` (the **outer** directory): the standard source directory whose contents Maven/Gradle copies onto the classpath. It is not a public URL by itself.
- `src/main/resources/resources/` (the **inner** directory): one of the four default sources searched by Spring Boot when a static resource request arrives. The repeated name is valid and required for the file to sit at `classpath:/resources/`.

Example:

~~~text
File in source code:
  src/main/resources/resources/docs/guide.txt
After being placed on the classpath:
  resources/docs/guide.txt
Default Spring MVC search location:
  classpath:/resources/
Default URL:
  GET /docs/guide.txt
~~~

The file `src/main/resources/application.properties` sits directly at the **classpath root**, yet **is not exposed by Spring MVC as a static asset** merely because it is on the classpath. This is an important boundary between “readable by the application” and “allowed to be served over HTTP”.

In a normal Maven build, the contents of `src/main/resources` are copied into `target/classes`; in Gradle, the corresponding contents usually reside in `build/resources/main`. When packaged as a Spring Boot executable JAR, application resources typically live in `BOOT-INF/classes/`. Physical paths vary by build tool, while the path **relative to the classpath** remains the primary concept.

## 3. How do the four default directories differ?

| Location on the classpath | Maven placement path | Common usage | Example URL |
| --- | --- | --- | --- |
| `classpath:/static/` | `src/main/resources/static/` | Application CSS, JS, images, static HTML pages | `/css/site.css` |
| `classpath:/public/` | `src/main/resources/public/` | Other public files, grouped according to project organization | `/about.html` |
| `classpath:/resources/` | `src/main/resources/resources/` | An additional static resource location; easily confused with the outer source directory | `/docs/guide.txt` |
| `classpath:/META-INF/resources/` | `src/main/resources/META-INF/resources/` | Servlet-convention assets and resources packaged inside dependency JARs | `/icons/logo.svg` |

**All four directories can serve the same kinds of files** unless constrained otherwise. There is no rule that `static` is only for CSS, `public` is only for HTML, or `META-INF/resources` is only for libraries. The grouping purpose in the table reflects project organization conventions rather than Spring limitations.

With the default configuration, for example:

~~~text
src/main/resources/static/css/site.css
                    └── css/site.css  -->  GET /css/site.css

src/main/resources/public/about.html
                    └── about.html    -->  GET /about.html

src/main/resources/resources/docs/guide.txt
                    └── docs/guide.txt --> GET /docs/guide.txt

src/main/resources/META-INF/resources/icons/logo.svg
                    └── icons/logo.svg --> GET /icons/logo.svg
~~~

Specifically, `/static/css/site.css` is **not** the default URL for `static/css/site.css`. The default URL is `/css/site.css` because Spring resolves the path **after the search root directory**.

If multiple files in different roots produce the **same URL**, such as `static/logo.svg` and `public/logo.svg`, you have created a name collision. The outcome depends on search order/configuration/classpath order; do not rely on “which directory takes precedence” when organizing lessons or applications. Keep relative paths distinct and inspect the final JAR.

### 3.1. Why does META-INF/resources exist?

`META-INF/resources` is a convention related to providing web content from JARs on the classpath. Thanks to this, a **dependency library** can distribute its own assets inside a JAR instead of requiring the application to copy them manually.

For example, a WebJar-style dependency can contain files under `META-INF/resources/webjars/...`. Spring Boot provides a mechanism to serve WebJars via the `/webjars/**` path according to packaging conventions and related configuration. Placing a file in `META-INF/resources` inside **your own application** is also completely valid.

Do not confuse `META-INF/resources` with an arbitrary `META-INF` directory inside a JAR. Not every file under `META-INF` becomes a web resource. Only locations configured in the resource handler as search sources are meaningful for HTTP URLs.

## 4. How is a resource request processed?

In Spring MVC (default Spring Boot configuration), `ResourceHttpRequestHandler` serves static resources. Visualizing the flow:

~~~text
GET /css/site.css
        |
        v
DispatcherServlet
        |
        | Controller/route mapping if matched
        | If no higher-priority matching handler exists
        v
Static resource handler (default /**)
        |
        | Look up "css/site.css" in static locations
        v
classpath:/static/css/site.css
        |
        v
Read resource, determine appropriate content type
        |
        v
HTTP response: 200 OK, appropriate Content-Type, CSS content
~~~

Key points to understand:

- For ordinary static files, **you do not need to write a `@RestController` or `@GetMapping`** to return each file; the resource handler handles it automatically.
- The `/**` path is a broad fallback pattern for static assets. It does not guarantee every URL maps to a file: if no file is found, the request can still receive **404**.
- Actual controller/router routes are generally evaluated before the welcome/static fallback handler. Therefore, if a controller handles `/`, `index.html` is not necessarily chosen for the root URL.
- MIME types such as `text/css`, `text/html`, and `image/svg+xml` are usually determined by file type and framework/container configuration. Do not hardcode expectations for secondary headers like `Content-Length` or `Last-Modified`, as they can vary at runtime.
- The browser may send separate requests for CSS/JS/images after loading HTML. An HTML page opening while CSS fails does not mean “Spring served all files successfully”.

### 4.1. Welcome page

If `index.html` is found in the configured static locations, Spring Boot can use it as the **welcome page** at `GET /`. If there is no static `index.html`, Boot can evaluate an `index` template when a suitable template engine is present. The welcome page is a **fallback** mechanism, so an explicit mapping for `/` can take precedence.

The file `static/index.html` still has the URL `GET /index.html`. Distinguish between “the `index.html` file being served” and “`/` pointing to the welcome page”: when changing pattern settings or adding a controller, test both paths.

Similarly, `favicon.ico` in a static location can be detected by Spring Boot to serve the favicon, though browsers and caches may still display an old icon after replacing the file.

## 5. Complete runnable example with Spring Boot 3.3.x and Java 17

The following example creates **a standalone application** without needing a database, frontend build tools, or custom controllers. The goal is to demonstrate HTTP serving from each directory.

### 5.1. Project structure

~~~text
assets-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/assetsdemo/
    │   └── AssetsDemoApplication.java
    └── resources/
        ├── application.properties
        ├── static/
        │   ├── index.html
        │   └── css/site.css
        ├── public/
        │   └── about.html
        ├── resources/
        │   └── docs/guide.txt
        └── META-INF/
            └── resources/
                └── icons/logo.svg
~~~

Create the exact paths shown in the tree above. The code examples below correspond to the **entire content** of each file.

**`pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>assets-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

`spring-boot-starter-web` brings in Spring MVC and embedded Tomcat by default; no resource handler configuration is needed to test the four directories. The Spring Boot parent manages the corresponding dependency versions.

**`src/main/java/com/example/assetsdemo/AssetsDemoApplication.java`**

~~~java
package com.example.assetsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AssetsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AssetsDemoApplication.class, args);
    }
}
~~~

Just a `main` class to run, with no controller required. The package sits under `com.example.assetsdemo`, matching the directory tree.

**`src/main/resources/application.properties`**

~~~properties
server.port=8080
~~~

Do not set `spring.web.resources.static-locations` or `spring.mvc.static-path-pattern` in the initial lab so that you use the **defaults**.

**`src/main/resources/static/index.html`**

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Spring Boot Static Resources</title>
  <link rel="stylesheet" href="/css/site.css">
</head>
<body>
  <h1>Static index page</h1>
  <p>This page is read from classpath:/static/index.html.</p>
  <img src="/icons/logo.svg" alt="Illustrative circle" width="80" height="80">
  <p><a href="/about.html">Public page</a></p>
  <p><a href="/docs/guide.txt">Resources document</a></p>
</body>
</html>
~~~

Paths like `href="/css/site.css"` and `src="/icons/logo.svg"` are **relative to the application's root URL** in the lab (the default context path is `/`). If you later deploy the application under a different context path, you must adjust link generation to use the proper prefix, or use a context-aware URL helper.

**`src/main/resources/static/css/site.css`**

~~~css
body {
  font-family: system-ui, sans-serif;
  max-width: 720px;
  margin: 2rem auto;
  line-height: 1.6;
}
h1 {
  color: #14532d;
}
img {
  display: block;
  margin-top: 1rem;
}
~~~

The CSS has the URL `/css/site.css`, **not** `/static/css/site.css`.

**`src/main/resources/public/about.html`**

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>About</title>
</head>
<body>
  <h1>Public page</h1>
  <p>Served from classpath:/public/about.html.</p>
</body>
</html>
~~~

This file is read directly from `classpath:/public/about.html` at the URL `/about.html`.

**`src/main/resources/resources/docs/guide.txt`**

~~~text
Static document in classpath:/resources/docs/guide.txt.
The HTTP path is /docs/guide.txt.
~~~

The `resources/resources` portion in the source path is **intentional**, not a typo.

**`src/main/resources/META-INF/resources/icons/logo.svg`**

~~~xml
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 80 80" width="80" height="80">
  <circle cx="40" cy="40" r="32" fill="#15803d"/>
  <circle cx="40" cy="40" r="12" fill="#ffffff"/>
</svg>
~~~

The SVG file sits under `META-INF/resources`, yet its URL is `/icons/logo.svg`.

### 5.2. Running the application and verifying URLs

Inside the `assets-demo` directory, with Java 17+ and Maven 3.9+ installed, run:

~~~bash
mvn spring-boot:run
~~~

Once the application starts on port 8080, open these URLs:

| URL | Source in project | What to observe |
| --- | --- | --- |
| `http://localhost:8080/` | `static/index.html` | Welcome page with heading and links |
| `http://localhost:8080/index.html` | `static/index.html` | Same HTML content from the static file |
| `http://localhost:8080/css/site.css` | `static/css/site.css` | Returns CSS text |
| `http://localhost:8080/about.html` | `public/about.html` | HTML page “Public page” |
| `http://localhost:8080/docs/guide.txt` | `resources/docs/guide.txt` | Two lines of guide text |
| `http://localhost:8080/icons/logo.svg` | `META-INF/resources/icons/logo.svg` | SVG content or illustrative circle |

Use `curl` to inspect status and headers:

~~~bash
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/about.html
curl -i http://localhost:8080/docs/guide.txt
curl -i http://localhost:8080/icons/logo.svg
~~~

When the files exist, no security blocks them, and configuration has not changed, expect each request to return **200 OK**. `Content-Type` will normally match the file type (CSS, HTML, text, SVG). Other headers may vary by container, framework, client invocation, and caching. When testing on legacy PowerShell, invoke `curl.exe` to avoid the `curl` alias conflict.

You can also try an incorrect URL:

~~~bash
curl -i http://localhost:8080/static/css/site.css
~~~

Expect **404 Not Found** because in the example layout there is no relative file `static/css/site.css` **inside** any static source. The physical prefix `static` is not automatically a URL prefix.

### 5.3. Packaging an executable JAR

Stop the `mvn spring-boot:run` command and run:

~~~bash
mvn clean package
jar tf target/assets-demo-0.0.1-SNAPSHOT.jar
java -jar target/assets-demo-0.0.1-SNAPSHOT.jar
~~~

When inspecting the listing with `jar tf`, look for the corresponding entries:

~~~text
BOOT-INF/classes/static/index.html
BOOT-INF/classes/static/css/site.css
BOOT-INF/classes/public/about.html
BOOT-INF/classes/resources/docs/guide.txt
BOOT-INF/classes/META-INF/resources/icons/logo.svg
~~~

`jar tf` lists many other entries as well; those five lines are the **paths to look for**, not the entire stdout. After running the JAR, request the URLs from section 5.2 again; if the files were packaged properly, the URLs still work under the default classpath mechanism. This is an important verification step: do not mistake the IDE seeing a file for the release artifact actually containing that file.

## 6. Configuration options that change URLs and file lookup locations

There are two separate types of configuration; they must be distinguished when troubleshooting 404 errors.

### 6.1. Changing the **URL pattern**: spring.mvc.static-path-pattern

Keep the example directory structure, and add to `application.properties`:

~~~properties
spring.mvc.static-path-pattern=/assets/**
~~~

Then the pattern accepting static assets changes from `/**` to `/assets/**`. Some example URLs:

| Source file | New URL |
| --- | --- |
| `static/css/site.css` | `/assets/css/site.css` |
| `public/about.html` | `/assets/about.html` |
| `resources/docs/guide.txt` | `/assets/docs/guide.txt` |
| `META-INF/resources/icons/logo.svg` | `/assets/icons/logo.svg` |

**Files do not move directories on disk**: only the HTTP paths change. Root-relative links in `index.html`, such as `href="/css/site.css"`, must now be updated to match the new pattern so the browser can load the CSS. Test welcome page handling at `/` separately when changing the pattern; do not assume `/` behaves identically to the default static path setup.

### 6.2. Changing the **source directories**: spring.web.resources.static-locations

Suppose you create:

~~~text
src/main/resources/my-assets/
  notice.txt
~~~

You can configure:

~~~properties
spring.web.resources.static-locations=classpath:/my-assets/
~~~

When running with the default URL pattern `/**`, `GET /notice.txt` is looked up in `classpath:/my-assets/`. **This setting replaces the default static locations list**, rather than automatically appending `static`, `public`, `resources`, and `META-INF/resources`. In Spring MVC/Servlet, the `ServletContext` root also has separate additional rules, but you should not rely on it to preserve the replaced classpath locations.

If you want to keep the four default locations and add a custom one, explicitly list the classpath sources to retain alongside the new source. For example:

~~~properties
spring.web.resources.static-locations=classpath:/static/,classpath:/public/,classpath:/resources/,classpath:/META-INF/resources/,classpath:/my-assets/
~~~

Location order can affect selection when filenames collide. A safer approach is **not to create duplicate public paths** across sources. This setting changes **where files are searched**, not by automatically adding a `/my-assets/` prefix to the URL.

### 6.3. Changing both

The two properties are independent dimensions:

~~~properties
spring.mvc.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/my-assets/
~~~

With the file `src/main/resources/my-assets/notice.txt`, the URL will be `GET /assets/notice.txt`. If you try calling `GET /notice.txt`, it will no longer match the static handler under the pattern above.

### 6.4. Disabling automatic static resource mappings

~~~properties
spring.web.resources.add-mappings=false
~~~

This setting disables the static resource mappings auto-configured by Spring Boot. When using it, simply placing files in `src/main/resources/static` is **no longer enough** to get serving URLs for them; you must provide an appropriate resource-serving mechanism if the application still needs assets.

### 6.5. Customizing via WebMvcConfigurer

If you need a dedicated URL and a dedicated source, you can register an additional resource handler in Spring MVC. The following is an **additional Java configuration class for a Boot project**, not a standalone `main` program:

~~~java
package com.example.assetsdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ExtraResourceConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/manuals/**")
                .addResourceLocations("classpath:/manuals/");
    }
}
~~~

If you create `src/main/resources/manuals/install.txt`, this handler serves `GET /manuals/install.txt`. The class file must be placed at `src/main/java/com/example/assetsdemo/ExtraResourceConfig.java` so its package matches the example. This is an **additional handler**; it is not required to enable the four default static locations.

**Note on `@EnableWebMvc`:** adding `@EnableWebMvc` makes you responsible for most MVC configuration and can disable the auto-configuration set up by Spring Boot. For simply adding a handler, implementing `WebMvcConfigurer` as in the example without adding `@EnableWebMvc` is simpler.

## 7. Distinguishing commonly confused directories

| Location | Purpose | Served directly via URL as static by default? |
| --- | --- | --- |
| `src/main/resources/static` | Frontend assets | Yes, via the resource handler |
| `src/main/resources/public` | Frontend assets | Yes |
| `src/main/resources/resources` | Frontend assets | Yes |
| `src/main/resources/META-INF/resources` | Web assets or assets inside dependency JARs | Yes |
| `src/main/resources/templates` | Server-side templates such as Thymeleaf, FreeMarker | **No** as static files; rendered by a view engine when invoked properly |
| `src/main/resources/application.properties` | Application configuration | **No**, not in the default static locations |
| `src/main/java` | Java source code | Not a static asset directory |
| `src/main/webapp` | Traditional web resources for WAR | **Should not be used** to serve resources when packaging a Spring Boot executable JAR |

For example, `templates/profile.html` may contain Thymeleaf syntax such as `th:text`, but if you move this file into `static`, Spring serves the file's contents as a static asset; **template expressions will not automatically render** with controller data. Conversely, `static/index.html` can work without a template engine.

An internal configuration file like `application.yml` must not be placed in `static` or `public`, because those are areas accessible over HTTP. Especially avoid configuring `spring.web.resources.static-locations=classpath:/`: widening the static source to the entire classpath root can accidentally expose configuration files and private content for serving.

## 8. Security, caching, WebJars, and routing conflicts

### 8.1. “Public” does not automatically bypass Spring Security

The directory name `public` is not an authorization rule. When **Spring Security** is added to an application, the filter chain may require authentication even for `/css/site.css`, `/about.html`, or `/icons/logo.svg`, depending on the policies you configure.

To make assets genuinely public, you must permit the required URL paths in your security configuration, such as the patterns `/css/**`, `/icons/**`, and `/about.html`. Verify using an unauthenticated request. Do not infer that an endpoint automatically bypasses security just because the file sits in `public`. For sensitive or per-user files, build access control mechanisms instead of placing files in a public static location.

### 8.2. Caching and file updates

Browsers and proxies may cache CSS, JS, and images. If the browser still shows old content after deployment, inspect the Network tab, `Cache-Control`, `ETag`/`Last-Modified` if present, `304 Not Modified` status, and the requested filename.

Spring MVC supports cache handling, conditional requests, and versioning strategies for static resources. When serving long-lived assets, you can use URLs containing versions or content hashes to prevent browsers from using stale code. Enabling a version strategy must be paired with proper reference URL generation; merely enabling the property while keeping hardcoded links may not produce the desired result.

### 8.3. WebJars and META-INF/resources

WebJars package frontend libraries as dependency JARs. Spring Boot supports the `/webjars/**` mechanism for dependencies that follow the WebJar structure; the exact URL format also depends on library name and version. This is one example of why `META-INF/resources` exists, though **not** every Java dependency carrying web assets automatically exposes a `/webjars/**` path.

### 8.4. Conflicts with dynamic routes

Suppose you have a file `static/reports.html` and a controller declaring `@GetMapping("/reports.html")`. Two mechanisms target the same URL. Normal controller mappings take precedence over the default resource handler. Therefore, when a file exists yet the returned content differs from expectations, inspect the **routes registered by the application** rather than checking only the file.

Similarly, the broad `/**` static handler can catch remaining paths when no controller matches. Newer versions of Spring MVC may raise `NoResourceFoundException` for missing static resource URLs rather than the “no handler” exception you might expect. The final HTTP status is still typically 404; distinguishing the exception type is useful when writing a `@ControllerAdvice`.

## 9. Layered diagnosis of static resource errors

| Symptom | Cause to check | How to verify/fix |
| --- | --- | --- |
| `GET /static/css/site.css` returns 404 | Wrong URL: mistakenly included the source directory name `static` | Use `/css/site.css` with the default configuration |
| `GET /docs/guide.txt` returns 404 | Placed `guide.txt` at root `src/main/resources/docs`, not inside a static location | Move to `src/main/resources/resources/docs/guide.txt` or an appropriate source |
| File works in IDE, returns 404 when running JAR | File was not packaged or build used a stale artifact | `mvn clean package`, use `jar tf ...` to verify the entry in `BOOT-INF/classes` |
| Old CSS returns 404 after changing `static-locations` | Property **replaces** the four default directories | Re-list the sources to retain or move files to the new source |
| Page loses CSS after changing `static-path-pattern` | HTML URL still uses `/css/...` while the new pattern is `/assets/**` | Synchronize links with the new pattern |
| Redirected to login, 401, or 403 | Spring Security blocks the asset URL | Check `SecurityFilterChain` and `requestMatchers` for URLs that should be public |
| HTML page loads but logo/CSS does not appear | Wrong asset URL, case-sensitivity mismatch, cached, or blocked | Inspect Network tab, request/status for each asset |
| Works locally, 404 on Linux/container | Filename case mismatch; file not copied into the image | Check exact names and image/JAR contents |
| File replaced yet browser still shows old version | Browser/proxy cache or deployment did not update artifact | Inspect response headers, versioned URLs, and actual file inside the JAR |
| `GET /` does not show `index.html` | Another `/` route exists, welcome page changed, or static location changed | Check routes, `static-locations`, welcome page, and pattern |
| Cannot access files in `templates` via direct URL | It is a template source, not a static root | Render via a view engine or place genuine static files in a static location |

Quick root-cause checklist, in order:

1. **Confirm the URL** being requested by the browser, including context path and prefix if any. In the default example, `/css/site.css` is right while `/static/css/site.css` is wrong.
2. **Confirm the file on the classpath** via the project tree and built artifact, not only the IDE. In an executable JAR, look for `BOOT-INF/classes/static/css/site.css`.
3. **Inspect configuration**: `spring.web.resources.static-locations`, `spring.mvc.static-path-pattern`, `spring.web.resources.add-mappings`, and any `WebMvcConfigurer` beans.
4. **Distinguish HTTP statuses**: 404 usually means route/file not found; 401/403 usually means authorization; 304 and stale content point to caching; 500 requires checking server-side exceptions.
5. **Check collisions** between resources sharing a URL, controller mappings, and packaging differences between local and production.

**Do not use an absolute filesystem path as proof that the classpath has the file.** A directory present on a developer's machine may be absent inside a Docker image; packaging is what matters when running a distributed application.

## 10. Spring WebFlux and WAR: what is the same, and what differs?

With Spring Boot **WebFlux**, the default classpath sources `/static`, `/public`, `/resources`, and `/META-INF/resources` still apply, but the resource handler is `ResourceWebHandler` instead of MVC's `ResourceHttpRequestHandler`. When you want to change the static URL pattern in WebFlux, use:

~~~properties
spring.webflux.static-path-pattern=/assets/**
~~~

Do not use `spring.mvc.static-path-pattern` expecting to change routes in a pure WebFlux application. The `spring.web.resources.static-locations` property is used to change the resource lookup locations in applicable setups. WebFlux does not rely on the Servlet WAR `src/main/webapp` structure as a default classpath source.

With a **Servlet WAR** deployed to a container that provides a `ServletContext`, the `ServletContext` root is a relevant web resource source. This differs from the **executable JAR** lab, where you should use the classpath directories described above. Do not move resources into `src/main/webapp` merely because you saw that layout in traditional JSP/WAR projects: Spring Boot warns that directory is unsuitable when packaging a JAR.

## 11. Self-check questions

**Question 1.** Given `src/main/resources/static/images/photo.png` with the default MVC configuration, which URL is correct: `/static/images/photo.png` or `/images/photo.png`? Why?

**Question 2.** Explain why `src/main/resources/docs/manual.txt` differs from `src/main/resources/resources/docs/manual.txt` from a public HTTP perspective.

**Question 3.** You place `src/main/resources/META-INF/resources/icons/app.svg`. What URL must users call? If you package that file inside a dependency JAR with the same structure, how is Spring Boot designed to handle that kind of resource?

**Question 4.** After setting `spring.mvc.static-path-pattern=/assets/**`, why does `<link href="/css/site.css">` fail to load the stylesheet as before?

**Question 5.** After setting `spring.web.resources.static-locations=classpath:/custom/`, are the four default classpath sources still included automatically?

**Question 6.** Why is placing `private-token.txt` inside `public` an insecure design if its contents are not meant to be public?

**Question 7.** If a file exists in source but running the JAR returns 404, what three things should you check immediately?

**Answers and explanations:**

1. `/images/photo.png`. The `static` directory is a search source, not a default URL segment.
2. Only the second path sits inside the default `classpath:/resources/`; the first path is at the classpath root and is not automatically a static location.
3. `/icons/app.svg`. Spring can serve assets from appropriate classpath sources, including content packaged inside dependency JARs, as long as it is not blocked by configuration/security or overridden by a collision.
4. The URL pattern changed to `/assets/**`, so the new link must use `/assets/css/site.css` in the example configuration.
5. No. Setting `static-locations` replaces the default list; if you want to retain defaults, you must list the sources to keep.
6. Static resources are accessible by URL unless blocked by a security layer; sensitive files must not sit inside publicly served areas.
7. Check the URL/pattern, the actual entry inside the executable JAR (`jar tf`), and `static-locations` along with any security/handler changes.

## 12. Key takeaways when designing applications

- Pick **one consistent organization**, such as placing application assets in `static/` and reserving `META-INF/resources/` for cases that genuinely need JAR/Servlet packaging conventions.
- Understand the two-level path accurately: `src/main/resources` is the **source root**, while `static`, `public`, `resources`, and `META-INF/resources` are **subdirectories on the classpath** selected by Spring Boot as static roots.
- Do not include the static root name in the URL unless you created that path inside the asset hierarchy itself or changed the URL mapping.
- When configuring `static-locations`, remember it **replaces** the default source list. When configuring `static-path-pattern`, remember to update referenced URL paths on your pages.
- Verify both the **HTTP response and the executable JAR contents** before concluding static resources work reliably.
- Treat security, caching, and context path as parts of the real request path; “the file is in the right folder” is only one condition.

## 13. Official references

- Spring Boot 3.3 — Servlet Web Applications, Static Content and Welcome Page: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Framework — Static Resources in Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Boot 3.3 — Reactive Web Applications (when using WebFlux): https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot — Maven Plugin and executable archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/reference/htmlsingle/
