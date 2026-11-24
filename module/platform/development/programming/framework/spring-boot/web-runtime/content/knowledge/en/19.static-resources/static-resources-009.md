# Static resources in executable JARs, WARs, and when running from an IDE

## 1. Objective and core problem

Static resources (*static resources*) are files served verbatim to HTTP clients, such as `index.html`, CSS, JavaScript, images, fonts, favicons, or public PDF documents. In a Spring Boot Web application, they are normally served by a framework-configured **resource handler**; there is no need to create a dedicated `@GetMapping` for every file.

A frequent issue: `/css/site.css` loads successfully when running the main class in an IDE yet returns **404** after building a `.jar` or deploying a `.war`. The primary cause is **differences in classpath, archive layout, and application context path**, combined with developers confusing source locations, packaging locations, and public URLs.

Three concepts must be kept distinct:

- **Source path:** where the file sits in the project, e.g., `src/main/resources/static/css/site.css`.
- **Runtime resource location:** where Spring looks up the resource after building/running, e.g., `classpath:/static/css/site.css`, stored inside an archive as `BOOT-INF/classes/static/css/site.css`.
- **HTTP URL:** which path clients request, e.g., `GET /css/site.css` under default context path and static path pattern.

The path `src/main/resources/static` is **not a URL prefix**. Requesting `/static/css/site.css` is usually wrong; the default URL is `/css/site.css`.

This lesson focuses on Spring Boot 3.x, Java 17+, Spring MVC/Servlet with executable JARs and WARs. WebFlux has a dedicated note because it does not use WAR/Servlet web roots in the same way.

## 2. Default static resource locations in Spring Boot

Spring Boot MVC looks up static content from classpath locations and from the `ServletContext` root:

| Runtime location | Common source location | URL when app runs at root context |
| --- | --- | --- |
| `classpath:/static/` | `src/main/resources/static/` | `/path/to/file` |
| `classpath:/public/` | `src/main/resources/public/` | `/path/to/file` |
| `classpath:/resources/` | `src/main/resources/resources/` | `/path/to/file` |
| `classpath:/META-INF/resources/` | `src/main/resources/META-INF/resources/` | `/path/to/file` |
| Servlet web root (MVC) | `src/main/webapp/` when packaged as WAR | `/path/to/file` |

Example project:

~~~text
src/main/resources/
├── static/
│   ├── index.html
│   ├── css/site.css
│   └── js/app.js
├── public/
│   └── images/logo.svg
└── META-INF/
    └── resources/robots.txt
~~~

Without custom mappings, the corresponding URLs are:

~~~text
GET /                    -> static/index.html (welcome page if detected)
GET /index.html          -> static/index.html
GET /css/site.css        -> static/css/site.css
GET /js/app.js           -> static/js/app.js
GET /images/logo.svg     -> public/images/logo.svg
GET /robots.txt          -> META-INF/resources/robots.txt
~~~

Spring MVC uses `ResourceHttpRequestHandler`; Spring WebFlux uses `ResourceWebHandler`. The default resource mapping is typically `/**`, though controller/route handlers and welcome pages have separate precedence rules. Placing two files with the same relative name into different locations yields hard-to-predict behavior based on configuration/classpath order; choose one consistent source location.

### `index.html` and `templates/index.html` are two different things

`src/main/resources/static/index.html` can become the **welcome page** at `GET /`. Conversely, `src/main/resources/templates/index.html` is a template for view engines like Thymeleaf and is not automatically served as a static file. Templates require an engine and an appropriate controller/view mapping.

Static files are **public under the resource mapping** unless protected separately. Never store tokens, secret keys, private configs, backups, or customer data inside static locations.

## 3. IDEs, Gradle/Maven output, and the classpath

In an IDE, clicking Run may place source resources or compiled output directories onto the runtime classpath. With standard Gradle/Maven:

~~~text
Source:          src/main/resources/static/css/site.css
                  |
                  v
Gradle output:   build/resources/main/static/css/site.css
Maven output:    target/classes/static/css/site.css
                  |
                  v
Classpath URI:   classpath:/static/css/site.css
                  |
                  v
HTTP URL:        /css/site.css
~~~

IDEs may use their own output directories depending on settings. What must be verified is **whether the resource is present on the runtime classpath**, not merely whether the file exists on disk. When modifying files in `src/main/resources`, the IDE may need to build/sync/copy resources again; IDE file watching alone does not guarantee the packaged artifact is up to date.

Useful steps when debugging:

1. Run via the IDE main class and access `http://localhost:8080/css/site.css`.
2. Run `./gradlew bootRun` or `./gradlew processResources` to verify the file in `build/resources/main/static/css/site.css`.
3. Package and **list the archive contents**; verify `BOOT-INF/classes/...` or `WEB-INF/classes/...`.
4. Launch the built archive itself, re-request the HTTP URLs, and compare.

A resource appearing in the IDE does not guarantee `bootJar`/`bootWar` includes it; builds may use custom source sets, exclusions, or files generated after packaging.

## 4. Executable JARs and the actual location of static resources

Spring Boot `bootJar` produces an archive containing a launcher, application classes, and dependencies. Illustrative layout:

~~~text
assets-demo.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── demo/assets/StaticAssetsApplication.class
    │   ├── application.properties
    │   └── static/
    │       ├── index.html
    │       ├── css/site.css
    │       └── js/app.js
    └── lib/
        ├── spring-webmvc-....jar
        └── ... other dependencies
~~~

**`src/main/resources/static/css/site.css` → `BOOT-INF/classes/static/css/site.css`**. The Spring Boot launcher sets up the classloader so `BOOT-INF/classes` forms the application classpath, allowing the resource handler to locate `classpath:/static/css/site.css`. You do not need to extract the JAR onto disk to serve files.

### The `src/main/webapp` trap

`src/main/webapp` is a **Servlet WAR** convention, not a static classpath location for executable JARs. Spring Boot officially warns that for JARs, most build tools **ignore** this directory.

~~~text
src/main/webapp/css/site.css            (do not use as static source for bootJar)
src/main/resources/static/css/site.css  (use this for bootJar)
~~~

Even if `src/main/webapp` happens to be served by an IDE or local servlet runtime, a production JAR can still omit those files. The durable fix is moving files into an appropriate location under `src/main/resources` and checking the archive; do not write a controller to paper over packaging mistakes.

### `jar` and `bootJar` are different

`jar` normally produces a standard Java archive. `bootJar` uses the Spring Boot plugin to package dependencies and the launcher for `java -jar`. If you accidentally build a plain JAR thinking it is an executable JAR, the layout and runtime classpath will differ. Always verify which build task creates the deployed file.

## 5. Minimal runnable example with Java 17 + Spring Boot MVC

Create a Gradle Java project. This example picks Spring Boot `3.3.13` and the Gradle dependency management plugin `1.1.6` for illustration; real projects should use versions governed and supported by your build system.

Structure:

~~~text
assets-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/demo/assets/StaticAssetsApplication.java
        └── resources/
            ├── application.properties
            └── static/
                ├── index.html
                ├── css/site.css
                └── js/app.js
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'assets-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('bootJar') {
    archiveFileName = 'assets-demo.jar'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/java/demo/assets/StaticAssetsApplication.java`:

~~~java
package demo.assets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StaticAssetsApplication {
    public static void main(String[] args) {
        SpringApplication.run(StaticAssetsApplication.class, args);
    }
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

`src/main/resources/static/index.html`:

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Static Assets Demo</title>
  <link rel="stylesheet" href="css/site.css">
  <script defer src="js/app.js"></script>
</head>
<body>
  <h1>Static assets from Spring Boot</h1>
  <p id="status">Waiting for JavaScript</p>
</body>
</html>
~~~

`src/main/resources/static/css/site.css`:

~~~css
body {
    color: #234;
    font-family: sans-serif;
    margin: 2rem;
}
~~~

`src/main/resources/static/js/app.js`:

~~~javascript
document.getElementById("status").textContent = "JavaScript loaded";
~~~

No controller is needed: while Web MVC auto-configuration remains intact, Spring Boot serves the files automatically.

### Running during development

In an IDE, import the Gradle project and run the main class `demo.assets.StaticAssetsApplication`. When using the included Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Once the server listens on port 8080:

~~~bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/js/app.js
~~~

Verification: `GET /` returns HTTP **200** containing `Static assets from Spring Boot`; CSS returns **200** with `color: #234;`; JavaScript returns **200** with `textContent = "JavaScript loaded"`. The browser displays “JavaScript loaded”. Header ordering and system headers may vary by server/runtime.

### Packaging the JAR, inspecting contents, running the JAR

~~~bash
./gradlew clean bootJar
jar tf build/libs/assets-demo.jar | grep "BOOT-INF/classes/static/"
java -jar build/libs/assets-demo.jar
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
jar tf .\build\libs\assets-demo.jar |
    Select-String 'BOOT-INF/classes/static/'
java -jar .\build\libs\assets-demo.jar
~~~

Entries that must appear (order unimportant):

~~~text
BOOT-INF/classes/static/index.html
BOOT-INF/classes/static/css/site.css
BOOT-INF/classes/static/js/app.js
~~~

Repeat the three HTTP requests. Before starting the JAR on the same host, stop the previous `bootRun` process if both bind port 8080. If the archive lacks those entries, fix source paths or build tasks; if the archive has them yet HTTP returns 404, investigate mappings, config, or context path first.

**Practical smoke test:** copy the JAR to a different directory without the project source tree and run it. If `GET /css/site.css` still succeeds, the resources are genuinely inside the archive with no reliance on external source files.

## 6. WAR: two location types and two launch modes

A WAR is an archive following the Servlet Web Application model. Spring Boot **MVC/Servlet** can build an executable WAR runnable via `java -jar`, while also deploying to an external Servlet container when configured properly.

Illustrative layout:

~~~text
assets-demo.war
├── META-INF/
├── WEB-INF/
│   ├── classes/
│   │   ├── demo/assets/StaticAssetsApplication.class
│   │   └── static/
│   │       ├── index.html
│   │       └── css/site.css
│   ├── lib/...
│   └── lib-provided/...
├── css/
│   └── war-only.css
└── favicon.ico
~~~

There are **two sources** here:

- **Classpath static:** `src/main/resources/static/css/site.css` lives at `WEB-INF/classes/static/css/site.css`. Spring's resource handler serves it at `/css/site.css` within the application context.
- **Servlet web root:** `src/main/webapp/css/war-only.css` lives at `css/war-only.css` in the WAR root. When the WAR is deployed as a Servlet web app, the web root acts as a dedicated WAR resource location.

Never request `/WEB-INF/classes/static/css/site.css` from a browser. `WEB-INF` is internal, and containers block direct access to it; the valid URL is determined by **resource mappings**.

**Recommendation:** if you want a set of assets to work identically across IDE, JAR, and WAR, use `src/main/resources/static`. Use `src/main/webapp` only when your target is genuinely a WAR and you test that deployment mode.

### Gradle setup for an executable and deployable WAR

To create the WAR variant of the MVC example above, use this `build.gradle` in place of the JAR configuration:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('bootWar') {
    archiveFileName = 'assets-demo.war'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`providedRuntime` packages the embedded container libraries in the proper area (typically `WEB-INF/lib-provided`) when you need both an executable WAR and external container deployment. Do not swap `providedRuntime` for `compileOnly` arbitrarily: integration tests might lack required runtime libraries.

To allow an external servlet container to initialize the Spring Boot app, update the main class to:

~~~java
package demo.assets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class StaticAssetsApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(StaticAssetsApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(StaticAssetsApplication.class, args);
    }
}
~~~

This is the **same Java file** from the JAR example, adapted for WAR; do not keep two public classes with the same package/name. `main()` supports running the executable WAR, while `configure(...)` supports external containers. With Spring Boot 3.x, external containers must support **Jakarta Servlet**; older containers supporting only `javax.servlet` will not work.

You can add `src/main/webapp/css/war-only.css`:

~~~css
.war-banner { font-weight: bold; }
~~~

Commands:

~~~bash
./gradlew clean bootWar
jar tf build/libs/assets-demo.war | grep "WEB-INF/classes/static/"
jar tf build/libs/assets-demo.war | grep "css/war-only.css"
java -jar build/libs/assets-demo.war
~~~

You should see `WEB-INF/classes/static/index.html` and `WEB-INF/classes/static/css/site.css`; WAR-root resources appear under `css/war-only.css`. When deployed to an external Servlet container, the context path may derive from the WAR name or container configuration. For example, if the context path is `/assets-demo`, clients call `/assets-demo/css/site.css`, not `/css/site.css`. Do not treat the archive name as a guaranteed fixed context path across all environments.

### WAR does not apply the same way to WebFlux

Spring Boot WebFlux uses `ResourceWebHandler` with similar classpath locations, yet **does not use `src/main/webapp` and does not support Servlet MVC WAR deployment**. With WebFlux, choose executable JARs and resources in `src/main/resources/static`. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot defaults to MVC, so verify the actual active web stack.

## 7. Comparison table: IDE, JAR, and WAR

| Criterion | IDE / `bootRun` | Executable JAR | WAR |
| --- | --- | --- | --- |
| Preferred static source | `src/main/resources/static` | `src/main/resources/static` | `src/main/resources/static`; `webapp` when Servlet web root is needed |
| Runtime file location | IDE output/classpath, usually `build/resources/main` or `target/classes` | `BOOT-INF/classes/static` | `WEB-INF/classes/static` |
| `src/main/webapp` | May be supported in dev; do not rely on it | Unreliable, usually omitted from packaging | Packaged as WAR root |
| Build/launcher | Main class, `bootRun` | `bootJar`, `java -jar .jar` | `bootWar`, `java -jar .war` or external container |
| Default URL | `/css/site.css` | `/css/site.css` | `/css/site.css` within the WAR context |
| Common mistake | IDE has not synced resource outputs | Files missing from archive | Wrong context path, broken WAR layout, or incompatible container |

Never use an HTTP 200 in the IDE as proof that the production artifact will succeed. Inspect the **exact archive produced by CI/CD**.

## 8. Configuring URL patterns and resource locations

### Changing static URLs while keeping file locations

Spring MVC:

~~~properties
spring.mvc.static-path-pattern=/assets/**
~~~

`src/main/resources/static/css/site.css` is now served at `/assets/css/site.css` (relative to the context path). Do not move files into `static/assets`, because this property changes the **URL mapping**, not the source location.

Spring WebFlux uses a different property:

~~~properties
spring.webflux.static-path-pattern=/assets/**
~~~

Do not use `spring.mvc.static-path-pattern` for pure WebFlux or vice versa.

### Changing static resource lookup locations

~~~properties
spring.web.resources.static-locations=classpath:/site/
~~~

The resource handler now searches `src/main/resources/site` (on the built classpath). This value **replaces the default classpath static locations list**; if you need both a custom location and the default `static` location, list them explicitly:

~~~properties
spring.web.resources.static-locations=classpath:/static/,classpath:/site/
~~~

In MVC/Servlet, the `ServletContext` root is still added automatically as a location. WebFlux has no Servlet web root. Configure multiple locations only when avoiding duplicate filenames.

### Changing the Servlet context path

~~~properties
server.servlet.context-path=/catalog
~~~

With the MVC embedded server, the public URL becomes `/catalog/css/site.css`. The file remains in `static/css/site.css`. When running a WAR inside an external container, the context path depends on deployment settings; do not hardcode paths from JAR/WAR folder names.

### Reading static files from outside the archive

~~~properties
spring.web.resources.static-locations=classpath:/static/,file:/opt/demo/public/
~~~

`file:/opt/demo/public/` is a Unix/Linux example. At deploy time, the directory must exist and the process must have read permissions; containers may require a volume mount. External files are not embedded in the JAR, so tests must verify runtime infrastructure. Never map folders holding secrets or private uploads into public HTTP paths.

### Disabling default mappings

~~~properties
spring.web.resources.add-mappings=false
~~~

If you disable automatic static mappings without registering a custom resource handler, requests can return 404 **even though files exist in the archive**. Likewise, `@EnableWebMvc` or `@EnableWebFlux` hands most framework configuration over to you; for limited customization, use `WebMvcConfigurer`/`WebFluxConfigurer` to keep auto-configuration intact when appropriate.

## 9. Why does `getFile()` work in the IDE yet fail in an executable JAR?

Inside an IDE, classpath resources often exist as files on disk. Once packaged, resources are read from JAR entries and **cannot necessarily be mapped to a real `java.io.File`**.

Fragile approach:

~~~java
// Snippet illustrating a common mistake:
Resource resource = new ClassPathResource("static/css/site.css");
File file = resource.getFile(); // Can fail when the resource is inside a JAR
~~~

To read classpath data reliably, use streams. Complete Java example in `src/main/java/demo/assets/ReadAsset.java` (run with Spring Core on the classpath):

~~~java
package demo.assets;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;

public final class ReadAsset {
    private ReadAsset() {
    }

    public static void main(String[] args) throws IOException {
        ClassPathResource css =
                new ClassPathResource("static/css/site.css");

        try (InputStream in = css.getInputStream()) {
            String text = new String(
                    in.readAllBytes(), StandardCharsets.UTF_8);
            System.out.println(text.contains("color: #234;"));
        }
    }
}
~~~

With the CSS file from section 5, **stdout** of this class is:

~~~text
true
~~~

`ReadAsset` is a separate Java main class launched via IDE/JavaExec with Spring dependencies on the classpath. The launcher of `assets-demo.jar` still points to `StaticAssetsApplication` per the build configuration. Inside a Boot app, you can apply `ClassPathResource#getInputStream()` in services or a `CommandLineRunner` using the exact same principle.

**Note:** serving static files over HTTP via Spring MVC/WebFlux **does not require** reading them yourself with `ClassPathResource`. The resource handler already does this; `getInputStream()` is only for Java code that genuinely needs to read resource contents.

## 10. HTTP testing and artifact verification

Add a JUnit 5 test with `spring-boot-starter-test` at `src/test/java/demo/assets/StaticAssetsHttpTest.java`:

~~~java
package demo.assets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StaticAssetsHttpTest {
    @Autowired
    TestRestTemplate http;

    @Test
    void welcomePageIsServed() {
        ResponseEntity<String> response =
                http.getForEntity("/", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .contains("Static assets from Spring Boot");
    }

    @Test
    void cssIsServed() {
        ResponseEntity<String> response =
                http.getForEntity("/css/site.css", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("color: #234;");
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.assets.StaticAssetsHttpTest
~~~

`RANDOM_PORT` starts a real HTTP server on an ephemeral port; `TestRestTemplate` resolves against the test root URL. The test proves classpath and resource mappings work **within the test runtime**. It is insufficient to prove files were packaged into the JAR/WAR: you still need `jar tf` and a smoke test against the archive itself.

Against the built JAR:

~~~bash
jar tf build/libs/assets-demo.jar | grep "BOOT-INF/classes/static/"
curl -i http://localhost:8080/
curl -I http://localhost:8080/css/site.css
~~~

`curl -I` sends a HEAD request, so the response has no body; verify HTTP 200 and the CSS media type. For a WAR, use `jar tf build/libs/assets-demo.war` and include the proper context path in requests.

## 11. Differences in real deployments

### Case sensitivity

Windows is usually case-insensitive for filenames; Linux and archive entry lookups match exact casing. `Logo.svg` and `logo.svg` must never be mixed. A URL that works on a developer workstation can return 404 inside a Linux container.

### Stale caches or CDNs

When HTTP returns 200 yet the browser displays old JavaScript/CSS, inspect HTTP caching, CDNs, reverse proxies, or service workers before assuming the new resource was not packaged. Spring Boot supports `Cache-Control`, for example:

~~~properties
spring.web.resources.cache.cachecontrol.max-age=30d
~~~

For frequently updated resources, use fingerprinted/versioned filenames. The resource chain can configure versioning, yet hardcoded HTML is not rewritten automatically without matching URL generation. Distinguish between **a new asset version being deployed** and **the browser hitting a stale cached URL**.

### WebJars and dependency resources

Dependencies can package resources under `META-INF/resources`, especially WebJars under `META-INF/resources/webjars`. Consequently, assets can be served from nested dependency JARs without appearing in `BOOT-INF/classes/static`. When tracing WebJar resources, inspect dependencies and the `/webjars/**` mapping.

### SPA route fallback

A Single Page Application may load `GET /` properly yet fail with 404 when refreshing `/users/42` directly because that is a client-side route, not a static file. You must configure an appropriate forward/fallback to the HTML entry while avoiding capturing `/api/**` and asset paths. Switching from JAR to WAR will not solve SPA routing on its own.

### Security and headers

Even when files are inside the JAR, requests can receive 401/403 if a security filter blocks them, or be rejected by browsers due to Content Security Policy or MIME types. Clearly separate **404 (resource not found)**, **401/403 (security)**, **200 HTML fallback instead of CSS**, and **proxy/network failures**. Never place sensitive data inside public static locations.

## 12. Symptom-based diagnosis

| Symptom | Common cause | Resolution step |
| --- | --- | --- |
| IDE 200, JAR 404 | Static files in `src/main/webapp` or excluded by build | Run `jar tf`, move to `src/main/resources/static`, and rebuild |
| IDE 404, JAR 200 | IDE has not copied resources or wrong classpath root | Refresh Gradle/Maven, inspect IDE output directory |
| Archive has the file, HTTP 404 | Wrong context/path pattern/static locations, or auto mapping disabled | Check effective properties and handler mappings |
| WAR 404 at `/css/...` yet works at `/app/css/...` | WAR deployed with `/app` context path | Use the proper context root; check container config |
| `getFile()` fails in JAR | Resource is an archive entry, not an OS file | Use `getInputStream()` |
| WebFlux does not serve `src/main/webapp` | Reactive stack does not use Servlet web roots | Use `src/main/resources/static` inside a JAR |
| `index.html` 200 yet `/foo/bar` 404 | SPA client route lacks server fallback | Design a safe SPA fallback |
| CSS 200 yet browser reports wrong MIME type | Response is an HTML error/fallback page | Inspect response body and `Content-Type` |
| Asset stale only in browser | Cache, service worker, CDN, or old artifact | Compare checksums, URL versions, and cache policies |
| Linux 404, Windows works | Filename case mismatch | Verify paths character-for-character |
| Static 404 after `@EnableWebMvc` | MVC auto-config replaced | Restore config or register proper resource handlers |
| Private resource leaked | Placed mistakenly in a public static folder | Move out of static and use an authorized endpoint |

**Practical investigation sequence:**

1. Identify the archive and launch mode: IDE/main, `bootRun`, `java -jar`, or external WAR.
2. Identify the requested URL including context path and resource path; inspect actual HTTP status and body.
3. Confirm the exact artifact deployed and list the archive with `jar tf`.
4. Cross-check archive contents against source files, build output, and source-set configuration.
5. Inspect `spring.web.resources.*`, `spring.mvc.static-path-pattern` or `spring.webflux.static-path-pattern`, security, and custom mappings.
6. If HTTP returns 200 yet the UI is broken, check response `Content-Type`, caching, browser console, frontend base URL, and proxy.

Fix only the layer causing the real error. When an asset is missing from the archive, adding a `@GetMapping` usually masks rather than solves the packaging issue.

## 13. Summary diagram

~~~text
                            FILE IN PROJECT
                                    |
                 +------------------+------------------+
                 |                                     |
      src/main/resources/static/             src/main/webapp/
                 |                                     |
         Build processResources                   Servlet WAR only
                 |                                     |
        +--------+--------+                            |
        |                 |                            |
      IDE              bootJar                        bootWar
  classpath output        |                            |
        |       BOOT-INF/classes/static/       WAR root + WEB-INF/classes/static/
        |                 |                            |
        +-----------------+----------------------------+
                          |
                   Web resource mapping
                          |
              URL /css/site.css (within context)
~~~

Files in `src/main/resources/static` work across IDEs, executable JARs, and WARs; `src/main/webapp` is only for WAR/Servlet web root needs. Whenever failures appear after deployment, verify the **runtime classpath/WAR root before URL mappings**.

## 14. Self-check exercises

**1.** `src/main/resources/static/images/logo.png` is packaged in a JAR. Is the default URL `/static/images/logo.png` or `/images/logo.png`?

**Answer:** `/images/logo.png`; `static` is not a URL prefix.

**2.** Why can `src/main/webapp/css/site.css` work locally yet be missing from an executable JAR?

**Answer:** `webapp` is a source location for WAR/Servlet web roots; `bootJar` normally does not put that directory on the classpath. Move it to `src/main/resources/static/css/site.css` and verify with `jar tf`.

**3.** For the same CSS file in `src/main/resources/static`, what are its paths inside a JAR and a WAR?

**Answer:** JAR: `BOOT-INF/classes/static/css/site.css`; WAR: `WEB-INF/classes/static/css/site.css`.

**4.** A WAR is deployed at context `/demo`. Is the CSS URL `/css/site.css` or `/demo/css/site.css`?

**Answer:** The external URL is normally `/demo/css/site.css`, assuming default mappings and that exact context path.

**5.** With `spring.mvc.static-path-pattern=/assets/**` and the file still in `static/css/site.css`, which URL is right?

**Answer:** `/assets/css/site.css` within the application context.

**6.** Why shouldn't you use `new ClassPathResource(...).getFile()` for files packaged inside a JAR?

**Answer:** The resource may exist inside the archive without a corresponding OS file; use `getInputStream()`.

**7.** `@SpringBootTest` with `RANDOM_PORT` passes. Do you still need to check the production archive?

**Answer:** Yes. Tests verify the test runtime classpath and HTTP mappings; packaging tasks can still omit files when building the JAR/WAR.

**8.** Does WebFlux use `src/main/webapp` for WAR deployments like Spring MVC?

**Answer:** No. For Spring Boot WebFlux, use static classpath locations and executable JARs.

## 15. Official references

- [Spring Boot 3.3 — Servlet Web Applications / Static Content](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): default static locations, `spring.mvc.static-path-pattern`, servlet root, and the `src/main/webapp` warning for JARs.
- [Spring Boot — Reactive Web Applications / Static Content](https://docs.spring.io/spring-boot/reference/web/reactive.html): `ResourceWebHandler`, `spring.webflux.static-path-pattern`, and WebFlux WAR limitations.
- [Spring Boot — Nested JAR / Executable Archive Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html): `BOOT-INF/classes`, `WEB-INF/classes`, and dependency layout.
- [Spring Boot — Gradle Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootJar`, `bootWar`, and `providedRuntime`.
- [Spring Framework — Spring MVC Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): resource handling, caching, and customization.

**Conclusion:** For public assets that must work consistently when run from an IDE, executable JAR, and WAR, place them in `src/main/resources/static`. Treat **classpath, archive, and HTTP URL** as three separate layers, and verify each layer during deployment.
