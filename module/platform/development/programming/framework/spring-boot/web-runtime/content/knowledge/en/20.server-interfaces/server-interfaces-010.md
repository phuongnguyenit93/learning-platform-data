# Diagnosing Template Not Found Errors and Classpath Order Differences in Spring Boot

## 1. Understanding the Failure to Diagnose

In a Spring Boot application with a server-rendered UI, a controller may return the view name `"catalog/detail"`, yet the browser reports an error or displays the wrong version of a page. With the exact same source code, `bootRun` may succeed while the IDE fails; conversely, the IDE may show the updated template while the executable JAR still renders an older copy.

This is not always a simple "wrong HTML path" mistake. There are at least four independent questions:

1. **Did the request reach the right controller/handler?** If not, the template engine never had a chance to run.
2. **Did the controller return a view name or a response body?** Only the view-returning path triggers view resolution.
3. **What resource path did the view resolver / template resolver build?** Prefix, view name, suffix, locale, engine, and customizations determine the target.
4. **What resources exist on the runtime classpath, and in what lookup order?** When the same resource path appears across multiple source sets, modules, or JARs, ordering differences across IDE, Gradle, and executable JARs can alter the outcome.

In Spring Boot **3.3.x** (Spring Framework 6.1.x, Java 17+), the official documentation warns that IDEs may order the classpath differently from Maven, Gradle, or a packaged JAR, causing expected templates not to be found. Therefore, fixing the root cause requires inspecting the **classpath of the failing process itself**, not just looking at files inside the IDE.

This lesson aims to separate failures across views, template resources, fragments, engines, and dependencies; verify packaged template locations; identify duplicate resources and ordering differences; and choose fixes that remain reliable across environments.

## 2. From HTTP Request to Template File: Four Distinct Layers

```text
HTTP GET /catalog/42
    |
    v
Spring MVC HandlerMapping
    |  locates @GetMapping("/catalog/{id}") or matching route
    v
@Controller returns view name "catalog/detail"
    |  Model contains product, id...
    v
Spring MVC ViewResolver
    |  selects ThymeleafView / FreeMarkerView / ...
    v
Template engine / TemplateResolver
    |  e.g., Thymeleaf: classpath:/templates/ + catalog/detail + .html
    v
Resource / ClassLoader / Template loader
    |  finds actual bytes in classes directory or JAR on classpath
    v
Parse + evaluate template, model, fragments, and return HTTP response
```

This path applies when **Spring MVC returns a view name to render HTML**. With `@RestController` or `@ResponseBody`, a `String` return value is the response body and is not resolved by Thymeleaf. With `redirect:` and `forward:`, Spring MVC handles special prefixes before regular view rendering.

| Layer | Example Error | Inspect the Right Layer |
| --- | --- | --- |
| HTTP/handler mapping | 404 because no `GET /catalog/42` exists | Controller mapping, context path, `@RequestMapping`, HTTP method, security |
| Controller/view name | Returning `"catalog/detail.html"` when suffix is already `.html` | Actual return value, `@Controller` vs. `@RestController` |
| View/template resolver | Engine not installed, `prefix` or `suffix` altered | Resolver beans, `spring.thymeleaf.*`, `view-names`, custom resolver order |
| Resource/classpath | File missing from artifact, duplicate `templates/catalog/detail.html` in another JAR | ClassLoader URL(s), `BOOT-INF/classes`, nested dependency JARs, classpath index |
| Parse/render | File exists, but expression/fragment/encoding fails | Root cause `TemplateInputException`, `TemplateProcessingException`, fragment expression |

**Do not equate HTTP 404 with "Thymeleaf could not find the template."** An unmapped request usually returns 404; when the route matches and a view fails to resolve or render, the failure occurs during rendering and often yields HTTP 500. Security rules, custom error handlers, and view resolver fallbacks can produce different status codes.

## 3. Default Conventions of Template Engines in Spring Boot

Spring Boot auto-configures Thymeleaf, FreeMarker, Groovy Templates, and Mustache. By default, several engines look for templates under `src/main/resources/templates`, though **file extensions depend on the engine**.

| Engine | Common Starter | Default File Location/Name | Controller Typically Returns |
| --- | --- | --- | --- |
| Thymeleaf | `spring-boot-starter-thymeleaf` | `classpath:/templates/catalog/detail.html` | `"catalog/detail"` |
| FreeMarker | `spring-boot-starter-freemarker` | `classpath:/templates/catalog/detail.ftlh` in Boot 3.3 | `"catalog/detail"` |
| Mustache | `spring-boot-starter-mustache` | `classpath:/templates/catalog/detail.mustache` | `"catalog/detail"` |
| Groovy Templates | `spring-boot-starter-groovy-templates` | Extension per Groovy template configuration | Matching logical view name |
| JSP | Servlet view resolver/container | Typically configured JSP path for WARs | View name, subject to embedded executable JAR limits |

Common Thymeleaf defaults in Boot 3.3:

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.enabled=true
spring.thymeleaf.cache=true
spring.thymeleaf.check-template=true
spring.thymeleaf.check-template-location=true
```

These defaults are **shown explicitly for learning**; omit them if you only want default behavior. `check-template-location` checks whether the **template folder location** exists; it does not replace checking each individual view file. `check-template` controls checking template existence during resolution. Turning checks off merely to silence warnings can hide misconfigurations.

In FreeMarker, the Boot 3.3 default suffix is **`.ftlh`**—do not assume Thymeleaf's `.html` applies to every engine. Relevant properties include `spring.freemarker.template-loader-path` and `spring.freemarker.suffix`. Mustache uses `spring.mustache.prefix` and `spring.mustache.suffix`. Check the effective configuration of whichever engine is actually on the classpath.

## 4. Why Can a Controller Return a String and Still Fail to Find the Template?

Correct Thymeleaf example:

**`src/main/java/com/example/view/CatalogController.java`**

```java
package com.example.view;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class CatalogController {

    @GetMapping("/catalog")
    public String catalog(Model model) {
        model.addAttribute("product", "Java");
        return "catalog/detail";
    }
}
```

**`src/main/resources/templates/catalog/detail.html`**

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Catalog</title></head>
<body>
  <h1>CATALOG_FROM_APP</h1>
  <p th:text="${product}">fallback</p>
</body>
</html>
```

With default Thymeleaf settings, the resolved path is:

```text
classpath:/templates/catalog/detail.html
```

Why is `"catalog/detail"` right? The resolver builds **prefix + view name + suffix**. Returning `"templates/catalog/detail"` would look for `classpath:/templates/templates/catalog/detail.html`; returning `"catalog/detail.html"` while `.html` suffix is active could look for `detail.html.html` or trigger engine-specific handling. Use consistent logical view names instead of guessing.

**Common mistake:**

```java
// @RestController => "catalog/detail" is the response BODY, does not render template.
@RestController
public class WrongCatalogController {
    @GetMapping("/wrong")
    public String wrong() {
        return "catalog/detail";
    }
}
```

The snippet above illustrates a **misleading declaration**, not code to add to a real application. For view-rendering controllers, use `@Controller` or an appropriate view handler; never annotate a view-name-returning method with `@ResponseBody`.

`return "redirect:/catalog"` issues a redirect and `return "forward:/catalog"` issues a forward per Spring MVC mechanics; neither looks for `redirect.html` or `forward.html` inside `templates`.

## 5. Distinguishing "Missing Resource" from "Resource Exists, Rendering Failed"

Common log messages often point to the failing layer, yet **never draw conclusions solely from the last line of a stack trace**.

| Symptom / Log (Illustrative) | Suspect Layer | How to Trace the Cause |
| --- | --- | --- |
| `TemplateInputException: Error resolving template ...` | Engine cannot open the requested template | Check view name, prefix, suffix, classpath, resolver |
| `template might not exist or might not be accessible` | Thymeleaf resource lookup or resolver selection | Inspect full view name, actual candidate path, and exception cause |
| `TemplateProcessingException` | File was likely loaded, error in expression/fragment/processor | Read nested cause, line/column position, model data |
| `Error resolving fragment` or `th:replace` error | Missing fragment/subtemplate or wrong fragment name | Check fragment file, `th:fragment` name, relative resolution |
| Warning `Cannot find template location` | Prefix directory not found at startup | Check packaging and `spring.thymeleaf.prefix`; do not treat as conclusive for every view |
| 404 before controller is called | Handler/path/security/routing | Check URL, HTTP method, `@RequestMapping`, context path |
| Controller runs yet returns literal body `"index"` | `@RestController`/`@ResponseBody` | Fix controller annotation when rendering views |
| Redirect to login / 401 / 403 | Security filter chain | Check security rules; not necessarily a template error |
| App runs yet displays old HTML version | Caching, duplicate template name, stale JAR, reverse proxy | Identify actual bytes and which URL wins classpath lookup |

How to read stack traces:

1. Find the **first request-related exception** and the deepest **root cause**.
2. Note the view name, template name, fragment name, path, and engine mentioned in the log.
3. Confirm the controller actually executed using logs or a breakpoint.
4. Verify the target file exists in the **runtime artifact**, not only in the source tree.
5. If the file truly exists yet the error persists, inspect classpath order and resolver configuration.

An exception from evaluating `${product.name}` on a `null` model cannot be fixed by moving `index.html`; fix the model or template expression.

## 6. Layers of Ordering That Must Not Be Conflated

"Order" in this context spans multiple layers, each solving a different decision:

| Ordering Layer | What It Decides | Relevant API / Component | When to Inspect |
| --- | --- | --- | --- |
| Handler mapping order | Which controller handles the request? | Spring MVC `HandlerMapping` | Endpoint not invoked or route collision |
| View resolver order | Which resolver handles the view name? | `ViewResolver`, `Ordered` | Multiple engines, fallback, or custom resolver |
| Template resolver order | Which template source is tried first? | Thymeleaf `ITemplateResolver`, `order`, `resolvablePatterns` | Multiple template resolvers/prefixes or filesystem sources |
| Resource loader/classpath order | Which classpath entry wins when resource paths collide? | `ClassLoader.getResource(s)`, Spring `ResourceLoader` | IDE differs from JAR, modules/libraries have duplicate templates |
| Build/packaging order | Where resources are packaged, which dependencies are included? | Gradle/Maven, `bootJar`, Boot Loader | Running JAR differs from `bootRun` |
| Cache order/lifecycle | Which parsed template version does the renderer hold? | Template cache, restart/DevTools | Source edited yet response unchanged |

For instance, given **two Thymeleaf TemplateResolvers** with different prefixes, resolver priority decides which source is queried first. Within **a single resolver** using `classpath:/templates/`, however, if two JARs share the same resource name, **classpath/resource lookup order** decides which file is found. Changing Spring MVC's `HandlerMapping.order` does nothing when two JARs both contain `templates/catalog/detail.html`.

Likewise, the **static resource locations** list (`classpath:/static/`, `classpath:/public/`) governs static files; it is **not Thymeleaf's template lookup order** inside `classpath:/templates/`.

## 7. Classpath: Source Paths, Runtime Paths, and Duplicate Resources

In a typical Gradle/Maven project layout:

```text
src/main/resources/templates/catalog/detail.html
        |
        v
build/resources/main/templates/catalog/detail.html    (typical Gradle output)
        |
        +--> bootRun / IDE: resources sit in classpath entries
        |
        +--> bootJar: BOOT-INF/classes/templates/catalog/detail.html
```

When a dependency JAR also contains:

```text
library-a.jar!/templates/catalog/detail.html
```

both share the same **relative classpath resource name** `templates/catalog/detail.html`. If code or an engine uses a **first-match** lookup (`ClassLoader.getResource`), only one copy is used even though multiple copies exist. `ClassLoader.getResources` can list all matching URLs for diagnostics.

**The classpath is not identical to the source filesystem.** A file in `src/test/resources/templates` can appear on the test classpath yet normally stays out of the production JAR; conversely, a template from a dependency JAR can appear at runtime despite not living in the main module's source tree.

Common resource locations:

| Source | Runtime Resource Path | Notes |
| --- | --- | --- |
| Main module under `bootRun` | `build/resources/main/templates/...` or equivalent output dir | Build tool layout may differ from IDE |
| Main module under `java -jar` | `BOOT-INF/classes/templates/...` | Located inside the executable JAR |
| Dependency JAR | Nested JAR inside `BOOT-INF/lib/` containing `templates/...` | Inspect nested JARs or enumerate URLs |
| Test resources | Test output/classpath | Cannot assume presence in production JAR |
| Filesystem prefix | e.g., `file:/.../templates/` resolver | Depends on working directory, mounts, and read permissions |

On Linux, `Detail.html` and `detail.html` are distinct filenames. Windows usually uses a case-insensitive filesystem, so code that works on Windows can report missing files when deployed to Linux or containers. Slashes, spaces, and Unicode characters must also match the **exact resource name**.

## 8. Spring Boot Executable JARs and `classpath.idx`

A Spring Boot executable JAR typically has this layout:

```text
myapp.jar
├── META-INF/
├── org/springframework/boot/loader/
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/view/...
    │   ├── application.properties
    │   └── templates/catalog/detail.html
    ├── lib/
    │   ├── library-a.jar
    │   └── library-b.jar
    └── classpath.idx     (if generated)
```

Spring Boot Loader supports nested JARs without unpacking all dependencies. `BOOT-INF/classes` holds the application's own classes and resources; `BOOT-INF/lib` holds dependency JARs.

Notably, `BOOT-INF/classpath.idx`, when present, records **the order in which nested library JARs are added to the classpath** when launching `java -jar` via Boot Loader. Spring Boot documentation notes this index is typically generated by the Maven/Gradle plugin; its ordering reflects how the build tool orders the dependency classpath. **The index is used only by Boot Loader for `java -jar`**, not when running from an IDE or via Gradle `bootRun` / Maven `spring-boot:run`.

Illustrative example:

```text
- "BOOT-INF/lib/library-b.jar"
- "BOOT-INF/lib/library-a.jar"
```

If both JARs contain a resource at the same path, changing dependencies or their order can change which copy is found. **Never assume classes or resources are always picked alphabetically or by JAR name**: inspect the index, classloader, and resource loader of the failing run. With reproducible builds, index entry ordering can reflect plugin rules; never rely on accidental ordering instead of maintaining a single source of truth for templates.

A very useful debugging nuance: `ClassLoader.getSystemClassLoader()` may **fail to see nested JAR resources as expected** when running under Spring Boot Loader. In diagnostic code, prefer `Thread.currentThread().getContextClassLoader()` or the `ResourceLoader` used by the framework.

## 9. Standalone Java 17 Lab: Same Path, Different Order, Different Result

This example uses **JDK 17+** with no Spring Boot required. It creates two temporary directories containing the **same relative path** and opens `URLClassLoader` with opposite orders. This provides direct evidence of how ordered classpath entries resolve lookups.

**File `ClasspathOrderDemo.java`:**

```java
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.List;

public class ClasspathOrderDemo {
    private static final String RESOURCE = "templates/catalog/detail.html";

    public static void main(String[] args) throws Exception {
        Path first = Files.createTempDirectory("templates-first-");
        Path second = Files.createTempDirectory("templates-second-");

        createTemplate(first, "FROM_FIRST");
        createTemplate(second, "FROM_SECOND");

        check(first, second);
        check(second, first);
    }

    private static void createTemplate(Path root, String text)
            throws IOException {
        Path file = root.resolve(RESOURCE);
        Files.createDirectories(file.getParent());
        Files.writeString(file, text, StandardCharsets.UTF_8);
    }

    private static void check(Path left, Path right) throws Exception {
        URL[] urls = {left.toUri().toURL(), right.toUri().toURL()};

        try (URLClassLoader loader = new URLClassLoader(urls, null)) {
            URL winner = loader.getResource(RESOURCE);
            List<URL> all = Collections.list(loader.getResources(RESOURCE));

            System.out.println("winner=" + read(winner));
            System.out.println("candidates=" + all.size());
        }
    }

    private static String read(URL resource) throws IOException {
        if (resource == null) {
            return "<missing>";
        }
        try (InputStream input = resource.openStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
```

Compile and run:

```bash
javac ClasspathOrderDemo.java
java ClasspathOrderDemo
```

**Exact stdout** with `URLClassLoader` and both directories created successfully:

```text
winner=FROM_FIRST
candidates=2
winner=FROM_SECOND
candidates=2
```

On the first pass, `first` takes precedence; reversing the order lets `second` win. `getResources` proves **both** resources exist. The key lesson is that "finding one resource" does not prove "only one resource exists."

This demonstrates `ClassLoader` mechanics and **does not represent every detail inside Thymeleaf or Spring Boot**. Template engines may combine multiple resolvers or caching, yet whenever a resolution step relies on first-match classloader lookup, classpath order determines which copy wins.

## 10. Spring Boot Practice: Views Work When the Path Is Right

MVC + Thymeleaf example on Java 21. The files below form a complete application in a Gradle project with wrapper.

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/view/TemplateApplication.java`**

```java
package com.example.view;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TemplateApplication {

    public static void main(String[] args) {
        SpringApplication.run(TemplateApplication.class, args);
    }
}
```

Place `CatalogController.java` in the same package as in Section 4. Create the Thymeleaf file as in Section 4. If adding configuration, you can place:

**`src/main/resources/application.properties`**

```properties
server.port=8080
```

Start the app:

```bash
./gradlew bootRun
```

Then:

```bash
curl -i -H 'Accept: text/html' http://localhost:8080/catalog
```

With this simple app and port 8080 free, the response is HTTP 200 containing:

```text
CATALOG_FROM_APP
```

and the text `Java` provided by the model. Exact HTTP headers and HTML whitespace depend on the renderer, so the full response is not pinned verbatim.

From this working baseline, you can introduce controlled failures:

- **Wrong view name:** Change controller to `return "catalog/unknown";` → the route still matches, but `templates/catalog/unknown.html` does not exist.
- **Wrong directory:** Move `detail.html` to `src/main/resources/static/catalog/detail.html` while keeping the controller and default Thymeleaf prefix → the template engine does not look inside `static/`.
- **Wrong suffix:** Set `spring.thymeleaf.suffix=.htm` while keeping the file `.html` → the resolver expects a different extension.
- **Missing engine:** Remove the Thymeleaf dependency and try returning a view name → MVC cannot render HTML templates in `templates` via Thymeleaf.
- **`@RestController`:** Change the controller annotation → returns a literal string instead of rendering HTML.

Change **only one variable at a time** and restart to isolate the cause. Never introduce multiple faults simultaneously, as that makes stack traces and outcomes hard to interpret.

## 11. Diagnosing the Classpath Live Inside a Running Application

A helpful technique is having the live process list all URLs matching the target resource name. With default Thymeleaf and controller `return "catalog/detail"`, the classpath resource name is:

```text
templates/catalog/detail.html
```

**`src/main/java/com/example/view/TemplateResourceProbe.java`** — drop-in sample for the Spring Boot app above:

```java
package com.example.view;

import java.net.URL;
import java.util.Collections;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TemplateResourceProbe {

    @Bean
    ApplicationRunner reportTemplateClasspath() {
        return args -> {
            String name = "templates/catalog/detail.html";
            ClassLoader loader =
                    Thread.currentThread().getContextClassLoader();

            URL winner = loader.getResource(name);
            List<URL> all = Collections.list(loader.getResources(name));

            System.out.println("template resource count=" + all.size());
            System.out.println("template first=" + winner);
            for (int i = 0; i < all.size(); i++) {
                System.out.println("candidate[" + i + "]=" + all.get(i));
            }
        };
    }
}
```

This configuration class compiles with the lab dependencies; exact URLs have no fixed stdout because runtimes and OS paths vary. A clean sample with the file only in the main module **typically** prints `template resource count=1`. If `count=0`, this classloader cannot see the resource under that name; check the effective prefix/suffix and artifact. If `count>1`, duplicate paths exist and you should identify which JAR or directory provides each URL.

Be careful with conclusions: `getResource` models classloader lookup, **not definitive proof that a custom Thymeleaf `TemplateResolver` uses that same classloader/prefix**. If you configured a `FileTemplateResolver`, `StringTemplateResolver`, a `SpringResourceTemplateResolver` with a custom prefix, or multiple resolvers, cross-check the actual resolver settings as well.

**Do not use** `ClassLoader.getSystemClassLoader()` as your sole evidence when running a Boot executable JAR with nested dependencies. Use the context classloader or Spring's `ResourceLoader`/`ApplicationContext.getResources(...)` matching how the engine loads resources.

## 12. Differences Between IDE, Gradle, and Executable JAR Runs

| Execution Mode | Typical Classpath | Consequence for Template Lookup |
| --- | --- | --- |
| IDE running `main` | IDE arranges module output resources and dependencies | Modules or dependency JARs can appear ahead; order changes with run config tweaks |
| Gradle `bootRun` | Gradle runtime classpath/output classes and resources | Ordered by Gradle; may differ from IDE |
| `./gradlew test` | Test classes/resources + main + dependencies | Test templates can shadow production resources |
| `java -jar build/libs/...jar` | Boot Loader, `BOOT-INF/classes`, and nested `BOOT-INF/lib` | Inspects real artifact and may use `classpath.idx` |
| Docker running packaged JAR | Follows artifact inside image | May still hold stale JAR/build layers or different mounts/configs |
| WAR in Servlet container | `WEB-INF/classes`, `WEB-INF/lib`, and container classloader | Adds parent-first vs. child-first loader differences |

Spring Boot 3.3 documentation explicitly notes: **IDE launches can order the classpath differently from Maven, Gradle, or packaged JARs**. If the IDE reports a missing template while the CLI succeeds, configure the IDE so **the application module's output classes/resources precede dependency entries**, then compare `TemplateResourceProbe` output across both runs.

That does not mean "forcing the IDE to match the JAR" is a good long-term solution when duplicate files exist. If two modules intentionally ship `templates/catalog/detail.html`, fix ownership, namespaces, and packaging so there is one clear source of truth.

## 13. Inspecting the Real Packaged Artifact

Checking files in the IDE project explorer is not enough. Using Section 10's sample app, build:

```bash
./gradlew clean bootJar
```

`clean` here is for the **sample lab project**; in an active working project with unsaved changes or important build caches, run it only once you understand its impact. To inspect the sample app's JAR output, use the actual filename from `build/libs`:

```bash
jar tf build/libs/template-demo-0.0.1-SNAPSHOT.jar
```

The name `template-demo-0.0.1-SNAPSHOT.jar` is **illustrative** if you configured that project name; in real projects use the filename Gradle produces. In the entry list, verify:

```text
BOOT-INF/classes/templates/catalog/detail.html
BOOT-INF/classes/com/example/view/TemplateApplication.class
BOOT-INF/classes/com/example/view/CatalogController.class
```

If the template is missing from `BOOT-INF/classes`, check:

- Is the file really under `src/main/resources/templates` in the source set of the module being built?
- Are any Gradle `processResources`/`sourceSets`/exclude rules filtering the file out?
- Are you running the newly built `bootJar`/artifact or an older JAR?
- In a multi-module build, which module owns the template and which library JAR holds resources?
- On Linux/containers, do filenames and casing match?

Run:

```bash
./gradlew processResources
./gradlew bootJar
```

to inspect the resource pipeline. To find which dependency JAR contains a duplicate resource, inspect the contents of dependency JARs (nested library files) or call `getResources` at runtime. `jar tf` on the **outer executable JAR** normally only lists `BOOT-INF/lib/library-a.jar`, without automatically expanding entries *inside* that nested library JAR.

If the application is packaged as a WAR, look inside `WEB-INF/classes/templates/...` and `WEB-INF/lib` JARs, keeping in mind that deployment modes can alter classloader behavior.

## 14. Configuring Thymeleaf for Debugging

In development, apply intentional settings:

**`application-dev.properties`**

```properties
spring.thymeleaf.cache=false
logging.level.org.thymeleaf=DEBUG
logging.level.org.springframework.web.servlet.view=TRACE
```

Run the sample with the dev profile:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

`cache=false` removes template caching while editing content during development; **it does not fix wrong paths, wrong classpath order, or missing dependencies**. Never disable caching across production just to mask deployment mistakes.

Verify the **effective values** of these properties:

| Property | Purpose | Sign of Misconfiguration |
| --- | --- | --- |
| `spring.thymeleaf.enabled` | Enables view resolution | `false` prevents the engine from handling views as expected |
| `spring.thymeleaf.prefix` | Base template location | Pointing to a different classpath or filesystem location |
| `spring.thymeleaf.suffix` | Default file extension | Looking for `.htm` when files are `.html` |
| `spring.thymeleaf.check-template` | Checks template on resolution | Overrides can alter fallback and error timing |
| `spring.thymeleaf.check-template-location` | Checks template location | Warning that directory does not exist |
| `spring.thymeleaf.view-names` | Restricts view names Thymeleaf processes | View `catalog/detail` falls outside the pattern |
| `spring.thymeleaf.excluded-view-names` | Excludes specific view names | Resolver skips expected view |
| `spring.thymeleaf.template-resolver-order` | Resolver position in the `TemplateResolver` chain | Unexpected order when multiple resolvers exist |

In Spring MVC, when multiple `ViewResolver` beans exist, check the **Spring ViewResolvers' order** separately. When multiple Thymeleaf `ITemplateResolver` instances exist, check each template resolver's **order, resolvable patterns, and `checkExistence`**. Tweaking `spring.thymeleaf.template-resolver-order` to fix a missing classpath resource targets the wrong layer if only one resolver exists.

Spring Boot's `--debug` flag prints the **Condition Evaluation Report** for auto-configuration, useful when suspecting Thymeleaf beans were never created. It does not print every chosen resource URL; pair it with `TemplateResourceProbe`.

## 15. Using Multiple Template Resolvers or Multiple Engines

An application may combine internal templates with theme/library templates or multiple engines. Two kinds of priority apply:

**Logical illustration** (describes the mechanism, not a complete configuration snippet):

```text
Thymeleaf TemplateResolver A: prefix=classpath:/templates-brand/
                            order=1
Thymeleaf TemplateResolver B: prefix=classpath:/templates/
                            order=2

controller returns "catalog/detail"
       |
       +--> query A first
       |       +--> if found and selected: use brand template
       |
       +--> if A does not handle/find it and fallback is allowed
               +--> query B
```

The condition "and fallback is allowed" matters. In Thymeleaf, a resolver can claim a template name within its scope with or without checking existence before returning a resource. A resolver that returns a candidate and then fails to open the file **may not automatically fall back to the next resolver**, depending on resolver settings. For true fallback, configure existence checks, patterns, and ordering supported by the framework, then test both present and absent files.

If both Thymeleaf and FreeMarker are present, they are separate view technologies and can compete for the same **logical view name**. At the MVC layer, inspect registered `ViewResolver` beans, their ordering, and `view-names` filters. At the resource lookup layer, check for `.html` vs. `.ftlh` files. **No classpath ordering rule can substitute for properly designed resolver priorities.**

When designing plugins/themes that override templates, establish a clear contract: view namespaces, custom prefixes, fallback tests, and version/dependency alignment. Never rely on lucky JAR positioning on the classpath to pick the primary UI.

## 16. Diagnosing Multi-Module Projects

Example:

```text
shop-app/
  src/main/resources/templates/orders/detail.html

shop-theme/
  src/main/resources/templates/orders/detail.html

shop-common/
  src/main/resources/templates/fragments/header.html
```

Both `shop-app` and `shop-theme` contain `templates/orders/detail.html` → duplicate resource risk. If the theme library appears ahead of app output in an IDE run, `getResource` may pick the theme copy. When packaged into a JAR, layout and Boot Loader ordering govern lookup, potentially reversing behavior.

Resolution steps:

1. Call `getResources("templates/orders/detail.html")` inside the **failing runtime** to inspect candidate count and URLs.
2. Check filenames inside `BOOT-INF/classes` and nested library JARs.
3. Choose **one owner for view `orders/detail`**. For example, only the app owns the primary view; the theme uses namespace `templates/theme/orders/detail.html` with explicit resolver/routing selection.
4. When legitimate overrides are needed, configure **two resolvers with explicit order and fallback policies**. Test IDE, `bootRun`, and packaged JAR runs.
5. Prevent accidental duplicates via module/package structure, resource naming conventions, and build/test checks.

Namespacing resources per module is far more durable than placing every `index.html` and `detail.html` directly under the `templates/` root. A shared library can place shared fragments under `templates/shared/fragments/...` without colliding with application views.

**Never try to force classpath order by renaming a JAR `aaa-theme.jar`** or expecting alphabetical sorting to dictate priority. That breaks easily whenever build plugins, launchers, or dependency graphs change.

## 17. Analyzing Misleading Scenarios

### 17.1. `templates/index.html` and the Home Page `/`

An `index` template can serve as the **welcome page** when no higher-priority static `index.html` exists and Spring Boot detects a template engine. However, if the application declares `@GetMapping("/")`, that route can choose a different view. Missing a welcome page at `/` does not imply all templates in the system are missing.

Distinguish:

```text
src/main/resources/static/index.html      => static resource/welcome candidate
src/main/resources/templates/index.html   => template source/welcome candidate
```

Static resource handling and template resolution are separate mechanisms. Moving a template into `static/` just to silence `TemplateInputException` stops Thymeleaf expression evaluation and can expose unprocessed template markup.

### 17.2. File Exists, Yet Thymeleaf Reports a Fragment Error

For instance, `catalog/detail.html` contains:

```html
<header th:replace="~{fragments/header :: topbar}"></header>
```

If `templates/fragments/header.html` lacks a fragment named `topbar`, the engine successfully opened `catalog/detail.html` yet fails during rendering. Check the **nested template name** and fragment declaration:

```html
<div th:fragment="topbar">Navigation</div>
```

This snippet is a **fragment example**; to use it, place it in `templates/fragments/header.html` with the Thymeleaf namespace and matching HTML structure. Do not alter classpath ordering when the real bug is a fragment name.

### 17.3. `@Controller` Has the Wrong Path While the Template File Is Right

A request to `/catalog` might miss the method due to servlet context path `/shop` or a route mapped to `/api/catalog`. When the controller never runs, the template path is not the primary suspect. Test the right external URL, HTTP method, and `Accept` header, and check Spring Security filters/redirects if present.

### 17.4. Stale Caches and Old Artifacts

Editing a template source file in an IDE does not automatically update the resource output directory or a running JAR. When `spring.thymeleaf.cache=true`, the engine can keep serving the parsed template already in memory. Check in order: right process/port, right artifact, right resource URL, template cache, and browser/reverse-proxy cache. Restart and rebuild cleanly in test environments without blindly wiping all caches in production.

## 18. Testing to Catch Failures Before Deployment

An integration test should verify that **HTML actually renders**, not merely that the file sits in source control.

**`src/test/java/com/example/view/TemplateHttpTest.java`** for Section 10's sample:

```java
package com.example.view;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TemplateHttpTest {

    @Autowired
    private TestRestTemplate client;

    @Test
    void catalogTemplateIsRendered() {
        ResponseEntity<String> response =
                client.getForEntity("/catalog", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("CATALOG_FROM_APP");
        assertThat(response.getBody()).contains("Java");
    }
}
```

Run:

```bash
./gradlew test
```

The test assumes the sample does not enforce login security on `/catalog` or change the context path. Using `RANDOM_PORT`, it starts a real HTTP server on an available port and verifies the rendered response body. In environments with custom `@SpringBootTest` configurations, apply matching profiles or dependencies so the test remains valid.

**To catch classpath ordering bugs**, also test the **packaged JAR**. IDE tests evaluate only the test runtime classpath; they do not guarantee `java -jar` sees the same order. A smoke test launching the executable JAR and requesting `/catalog` catches packaging discrepancies. Use `TemplateResourceProbe` when responses mismatch, or add explicit checks for duplicate templates on the runtime classpath in targeted test suites.

Do not leave the probe enabled as permanent logging in production: printing resource URLs can expose internal path details. Enable it only in dev/test or behind a secured diagnostic endpoint.

## 19. Concise Diagnostic Workflow You Can Apply Immediately

When encountering a "template not found" error, check in order:

1. **Pinpoint the HTTP failure:** URL, status, redirect, whether the controller ran, and right profile/process/port.
2. **Capture the actual view name:** verify the class is `@Controller`, check the exact return value, and rule out `redirect:`/`forward:`/`@ResponseBody`.
3. **Identify engine and resolvers:** Thymeleaf/FreeMarker/Mustache? Is the starter dependency present? Which view resolvers and template resolvers are active?
4. **Compute the expected resource path:** default Thymeleaf `catalog/detail` → `classpath:/templates/catalog/detail.html`; for FreeMarker, verify `.ftlh` suffix.
5. **Inspect the runtime classpath:** use context classloader `getResources`, Spring `ResourceLoader`, and inspect resource output / JAR contents directly.
6. **Check for duplicates and ordering:** if multiple URLs exist for one path, compare IDE, `bootRun`, tests, and `java -jar`; inspect `BOOT-INF/classpath.idx` if present.
7. **Inspect nested causes:** if the resource exists, check fragments, parse/expression errors, encoding, model attributes, and caching.
8. **Fix the right layer:** fix view name, prefix, source set, packaging, resolver order, or duplicate resource ownership; add an appropriate regression test.

| Evidence | Reasonable Conclusion | Next Step |
| --- | --- | --- |
| Controller did not run | Template is not the issue yet | Debug routing, security, context path |
| Controller returned literal string body | Bypassed view resolution | Fix controller annotation/API response |
| Engine missing/disabled | Resolver unavailable | Fix dependencies/config |
| `getResources(...)=0` | Context classloader cannot see that resource path | Check expected path, output resources, JAR |
| `getResources(...)>1` | Duplicate resource paths | Identify owner, winning URL, and order |
| JAR has app template while IDE loads dependency template | Runtime classpath order/source differs | Prioritize app output in IDE; remove long-term duplicates |
| Resource exists, fragment error thrown | Not a "root file missing" bug | Fix nested template/fragment |
| `bootRun` PASSES, `java -jar` FAILS | Packaging and Boot Loader classpath mismatch | Inspect artifact, dependencies, index, smoke test |
| Failed only after editing a template | Stale cache or uncopied output file | Compare actual bytes, restart test |

## 20. Common Misconceptions and Self-Check Questions

**Misconception 1:** "`src/main/resources/templates/x.html` exists on disk, so the runtime must see it." Files can remain unprocessed, excluded, in another module/test resource root, or absent from the running artifact.

**Misconception 2:** "`ClassLoader.getResource` found a file, so there are no duplicates." False; use `getResources` to enumerate all matching URLs.

**Misconception 3:** "Classpath ordering is identical across IDE, Gradle, and executable JARs." Not guaranteed. Boot docs explicitly warn of these differences.

**Misconception 4:** "`ViewResolver` order controls JAR order on the classpath." Those are two completely separate ordering layers; identify which layer is failing.

**Misconception 5:** "`@RestController` returning `"catalog/detail"` renders HTML." No; it writes a literal string response body.

**Misconception 6:** "Every template engine looks for `.html` files." Boot 3.3 FreeMarker defaults to `.ftlh`, Mustache to `.mustache`; each engine has its own settings.

**Misconception 7:** "Disabling cache, `check-template`, or warnings fixes missing templates." No; it only hides issues or shifts when failures appear.

**Misconception 8:** "Adding `index.html` under `static/` fixes template errors." Static resources and server-side templates operate in separate layers.

**Misconception 9:** "`classpath.idx` always governs the IDE classpath." Spring Boot uses the classpath index only for Boot Loader `java -jar` runs; IDEs and `bootRun` do not use it.

**Review questions:**

1. A controller returns `"catalog/detail"` with default Thymeleaf; what is the expected classpath path? What changes if the file is placed under `static/`?
2. Why is `ClassLoader.getResources("templates/catalog/detail.html")` more informative than `getResource` when suspecting duplicate templates?
3. How do `@RestController` and `@Controller` differ when a method returns `String`?
4. Why can the same repository pass under `bootRun` yet fail from an executable JAR, or vice versa?
5. How do the roles of `BOOT-INF/classes`, `BOOT-INF/lib`, and `BOOT-INF/classpath.idx` differ?
6. When should you inspect `TemplateResolver` order versus runtime classpath order?
7. Does `TemplateInputException` always mean the root template file does not exist? Give an example of a fragment or resource access failure.
8. What test would you write to verify a template **genuinely renders over HTTP**, and what extra check catches differences between the test classpath and the packaged JAR?

**Operational principle:** place templates in the right directory and namespace, make view names reflect clear logical paths, avoid duplicate classpath resources, and always verify against the **execution mode where the error occurs**. When a file exists yet fails to display properly, first separate handler, view resolver, template resolver, and resource loader before choosing a fix.

### Official References

- Spring Boot 3.3 — Servlet Web Applications, Template Engines section and IDE classpath ordering note: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html
- Spring Boot — Nested JARs and Classpath Index: https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html
- Spring Framework — MVC View Resolvers: https://docs.spring.io/spring-framework/reference/web/webmvc-view/mvc-viewresolver.html
- Thymeleaf + Spring integration: https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html
- Java 17 `ClassLoader#getResources`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
