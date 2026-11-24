# Auto-Configuration of Template Engines Supported by Spring Boot

> **Scope:** Spring Boot web-runtime, focusing on **server-side HTML rendering** with Spring MVC and comparing support in Spring WebFlux. Property names, file extensions, and examples follow **Spring Boot 3.3.x with Java 17+**; when using a different Spring Boot version, consult the official documentation for that release.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish a **server-side template engine**, view name, `ViewResolver`, model, and the actual HTML returned to the browser.
2. Explain why adding the right dependency and placing files in the right directory activates Spring Boot **auto-configuration** without manually defining a `ViewResolver`.
3. Correctly list the four template engines that Boot 3.3 auto-configures for **Spring MVC**: **Thymeleaf**, **FreeMarker**, **Mustache**, and **Groovy Templates**; distinguish the cases of WebFlux and JSP.
4. Run a Spring MVC + Thymeleaf example with a complete file structure, controller, model, template, `application.properties`, and test commands.
5. Switch engines to FreeMarker or Mustache, understanding what changes in dependencies, template extensions, syntax, and configuration.
6. Customize prefix/suffix/template path/cache/view patterns via properties, know when a custom bean is required, and avoid unintentionally disabling auto-configuration.
7. Diagnose missing views, accidentally returning bodies instead of views, parse errors, template caching issues, XSS, multi-engine conflicts, and packaging issues.

## 2. What Is a Template Engine? Flow of Rendering an HTML Page

A template engine combines an **HTML template** and **request data** to generate the final HTML on the server. The browser receives the resulting HTML; normally it does **not** receive the Thymeleaf `.html` source with `th:...`, FreeMarker `.ftlh` with `<#...>`, Mustache `.mustache` with `{{...}}`, or Groovy template code.

Classic example: a handler receives `GET /hello?name=Lan`, puts `name = "Lan"` into the `Model`, and returns the view name `"hello"`. The engine locates the `hello` template at the proper path and renders it. The response typically has `Content-Type: text/html` (with charset depending on configuration).

```text
Browser
   |
   | GET /hello?name=Lan
   v
Spring DispatcherServlet / WebFlux DispatcherHandler
   |
   v
@Controller (sets Model: name="Lan")
   |
   | return "hello"  <-- logical view name, not HTML
   v
ViewResolver / ViewResolutionResultHandler
   |
   | classpath:/templates/hello.html  (Thymeleaf)
   v
Template Engine + Model
   |
   v
HTML rendered --> HTTP response --> Browser
```

Separating roles:

| Component | Responsibility |
|---|---|
| `@Controller` | Selects business flow, supplies the model, returns a view name or `ModelAndView`. |
| `Model` | Set of attributes for the template in the request, e.g., `name`, `items`. |
| View name `"hello"` | Logical name used by the resolver to identify a view, **not necessarily the full file path**. |
| `ViewResolver` (MVC) | Converts a view name into the appropriate `View` and handles prefix/suffix and view type. |
| Template engine | Reads the template, evaluates expressions/conditions/loops, and produces output. |
| Auto-configuration | Spring Boot registers/configures default beans when dependencies, classpath, web environment, existing beans, and properties satisfy conditions. |

**Important example:**

```java
@Controller
class PageController {
    @GetMapping("/page")
    String page(Model model) {
        model.addAttribute("title", "Lan's Page");
        return "home"; // view name: "home"
    }
}
```

The snippet above illustrates **a method inside an already configured MVC application**, requiring imports and an application class; `return "home"` does not send the literal string `"home"` to the client. If `@Controller` is replaced with `@RestController` or `@ResponseBody` is added, the returned string becomes the **response body**, so the template is not rendered. This is a common reason learners see the text `home` instead of an HTML page.

## 3. Engines Auto-Configured by Spring Boot 3.3

According to the Spring Boot 3.3 documentation for Servlet Web Applications, Spring Boot provides auto-configuration for **FreeMarker, Groovy Templates, Thymeleaf, and Mustache** in Spring MVC applications. Other engines can still be integrated with appropriate configuration or frameworks, but you should not assume Boot provides official auto-configuration merely because an engine works with Spring MVC.

| Engine | Starter in Spring Boot 3.3 | Default Template File | Best Fit |
|---|---|---|---|
| **Thymeleaf** | `spring-boot-starter-thymeleaf` | `src/main/resources/templates/hello.html` | HTML close to natural HTML syntax; expressions, forms, fragments, convenient Spring MVC integration. |
| **FreeMarker** | `spring-boot-starter-freemarker` | `src/main/resources/templates/hello.ftlh` | Powerful template language, macros/loops/conditionals, reusable for HTML or text rendering. |
| **Mustache** | `spring-boot-starter-mustache` | `src/main/resources/templates/hello.mustache` | Concise syntax, minimal logic, section and partial model. |
| **Groovy Templates** | `spring-boot-starter-groovy-templates` | `src/main/resources/templates/hello.tpl` | Templates written with the Groovy Markup Template Engine; fits systems already using Groovy. |

**JSP is a different case:** Spring MVC supports JSP via Servlet/JSP infrastructure, but JSP **is not included in the four engines above**. In Spring Boot 3.3, when using embedded Tomcat/Jetty, JSP has packaging limitations: JSP is not supported in an **executable JAR** and requires considering a **WAR**; Undertow does not support JSP. Therefore, do not treat `spring-boot-starter-web` + JSP as equivalent to a standard template engine starter. This is why the Boot documentation advises avoiding JSP when suitable alternatives exist.

### Differences with Spring WebFlux

Spring Boot supports template engine auto-configuration for **FreeMarker, Thymeleaf, and Mustache** in WebFlux; **Groovy Templates is not in the WebFlux auto-configuration list** in the Boot 3.3 documentation. With WebFlux, some FreeMarker features have limitations; check the corresponding properties and view integration sections. Adding `spring-boot-starter-webflux` does not turn every template engine into a fully non-blocking renderer; template/expression evaluation still consumes CPU.

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot typically chooses a **Servlet/MVC web application** by default inference; do not see `Mono` on the classpath and assume a Reactor Netty server is running.

## 4. Under What Conditions Does Auto-Configuration Activate?

Rather than forcing you to manually create `TemplateEngine`, `TemplateResolver`, `ViewResolver`, and numerous beans, Boot provides dedicated auto-configurations. They evaluate relevant conditions such as:

1. **Template engine classes** present on the classpath (usually pulled in by a starter).
2. **Spring MVC or WebFlux classes**, the web application type, and the current environment.
3. Existing beans; many auto-configurations register defaults via `@ConditionalOnMissingBean` or equivalent conditions.
4. Configuration properties such as `spring.thymeleaf.enabled`, `spring.freemarker.enabled`, `spring.mustache.enabled`.
5. View resolver settings, template paths, and template file extensions.

Thus, "having added the starter" **does not guarantee** every resolver will always work regardless of configuration: the app might be using the wrong web stack, your own bean might replace the default, the engine might be disabled, or templates might sit outside the loader path.

Common beans in Spring MVC:

| Engine | Typical View Resolver | Function |
|---|---|---|
| Thymeleaf | `ThymeleafViewResolver` | Uses Thymeleaf configuration to locate `hello.html`. |
| FreeMarker | `FreeMarkerViewResolver` | Combines loader path/prefix/suffix, typically locating `hello.ftlh`. |
| Mustache | `MustacheViewResolver` | Locates Mustache templates by prefix/suffix. |
| Groovy | `GroovyMarkupViewResolver` | Locates Groovy Markup templates by path/suffix. |

Spring MVC also includes foundational resolvers like `InternalResourceViewResolver` and `BeanNameViewResolver`; depending on the application, `ContentNegotiatingViewResolver` may also be present. If you register extra resolvers or mix engines, **ordering and view-name matching rules** can affect which engine is chosen. Do not rely on "whichever resolver was added last" to resolve conflicts: inspect resolver configuration and view patterns directly.

**Do not add `@EnableWebMvc` just to use Thymeleaf.** This annotation switches much of the default Spring MVC setup to manual management; if your goal is simply adding a template engine or extending MVC, keep Boot MVC auto-configuration and add only beans or a `WebMvcConfigurer` when genuinely needed. `@EnableWebFlux` warrants the same caution on the reactive side.

## 5. Minimal Integration Workflow with Spring MVC

With an auto-configured template engine, four steps are usually enough:

1. The project includes Spring Boot + the web MVC starter.
2. Add **one** template engine starter, e.g., `spring-boot-starter-thymeleaf`.
3. Create template files under `src/main/resources/templates/` (or customize the path via properties).
4. Write a `@Controller` returning a **view name** and populating `Model` attributes.

Gradle example (Groovy DSL) in a project already using the Spring Boot plugin/dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
```

This is the **dependencies section** in an already configured build, not a complete `build.gradle`. In Spring Boot 3.3, Boot manages dependency versions through dependency management/BOM; do not manually pin mismatched versions on starters without a clear reason.

With Maven, the equivalent inside `<dependencies>` is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-thymeleaf</artifactId>
</dependency>
```

This Maven snippet assumes the Spring Boot parent/BOM is configured. Both configurations describe **an MVC web runtime**; there is no need to add `spring-boot-starter-webflux` just to render HTML on the server.

### Project Structure

```text
src/main/
  java/
    example/views/
      ViewsApplication.java
  resources/
    application.properties
    templates/
      greeting.html
```

`templates/` inside `src/main/resources` is packaged as a classpath resource, so when running an executable JAR, templates are still resolved via `classpath:/templates/`. Do not create `src/main/webapp` for Thymeleaf expecting Boot to scan there as the default template location.

## 6. Complete Spring MVC + Thymeleaf Example

Create `src/main/java/example/views/ViewsApplication.java`:

```java
package example.views;

import java.util.List;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@SpringBootApplication
public class ViewsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ViewsApplication.class, args);
    }

    @Controller
    static class GreetingController {
        @GetMapping("/greeting")
        String greeting(
                @RequestParam(defaultValue = "friend") String name,
                Model model) {
            model.addAttribute("name", name);
            model.addAttribute("topics",
                    List.of("Spring MVC", "Thymeleaf", "Template engine"));
            return "greeting";
        }
    }
}
```

Notes:

- `@Controller` is essential for a `String` return value to be interpreted as a **view name**.
- `model.addAttribute` passes data to the template for that request.
- `return "greeting"` excludes `.html` and `/templates/`; the Thymeleaf resolver combines prefix + view name + suffix to locate the file.
- In package `example.views`, the application class scans components in the same package/subpackages; a nested `static` controller annotated with `@Controller` is detected by component scanning.
- `@RequestParam(defaultValue = "friend")` allows calling the URL without supplying `name`.

Create `src/main/resources/templates/greeting.html`:

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Greeting Page</title>
</head>
<body>
  <h1>Hello <span th:text="${name}">friend</span>!</h1>
  <h2>Topics covered:</h2>
  <ul>
    <li th:each="topic : ${topics}"
        th:text="${topic}">A topic</li>
  </ul>
</body>
</html>
```

In Thymeleaf, `th:text="${name}"` reads the `name` attribute from the model and **HTML-escapes** the content for text context. The `th:each` loop creates an `li` for each item in `topics`. The placeholder text inside the elements serves as sample markup and is replaced during rendering. This keeps the file structurally valid HTML when opened directly as a template.

Example `src/main/resources/application.properties` (the values below match most Boot 3.3 defaults):

```properties
spring.thymeleaf.enabled=true
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.mode=HTML
spring.thymeleaf.encoding=UTF-8
spring.thymeleaf.cache=true
```

When learning auto-configuration, you can omit all of these lines since Boot provides defaults. Keep them when you want to **make explicit** the template path, mode, or caching behavior.

Run from the project root using:

```bash
./gradlew bootRun
```

On Windows use `gradlew.bat bootRun`; for Maven projects use `./mvnw spring-boot:run` or `mvnw.cmd spring-boot:run`. Visit:

```bash
curl -i "http://localhost:8080/greeting?name=Lan"
```

Expected result: status `200 OK`, HTML content type, body containing `Hello Lan!` and three `li` elements with `Spring MVC`, `Thymeleaf`, and `Template engine`. **Do not assert byte-for-byte identical HTTP output**, since HTML whitespace, headers, and serialization details can vary across versions and containers.

### Verifying Escaping Behavior

Call:

```bash
curl -i "http://localhost:8080/greeting?name=%3Cb%3ELan%3C%2Fb%3E"
```

`name` is decoded into a string containing markup `<b>Lan</b>`. With `th:text`, the output HTML encodes `<` and `>` in text position into entities such as `&lt;b&gt;Lan&lt;/b&gt;`. The browser displays the text `<b>Lan</b>` rather than rendering a bold tag. Switching to `th:utext` or concatenating HTML strings manually bypasses escaping and can introduce **XSS** vulnerabilities when data comes from users.

## 7. Converting the Example to Other Engines

You **do not need to keep all four starters** in the project at once. In the experiments below, keep `ViewsApplication.java` unchanged, remove `spring-boot-starter-thymeleaf`, add **one** starter for your chosen engine, and place the corresponding template file. The view name remains `greeting`.

### 7.1. FreeMarker

Replace the template dependency with:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-freemarker'
```

Create `src/main/resources/templates/greeting.ftlh`:

```ftl
<#ftl output_format="HTML" auto_esc=true>
<!doctype html>
<html lang="en">
<head><meta charset="UTF-8"><title>Greeting Page</title></head>
<body>
  <h1>Hello ${name}!</h1>
  <ul>
  <#list topics as topic>
    <li>${topic}</li>
  </#list>
  </ul>
</body>
</html>
```

`<#list ...>` iterates over the list in the model, and `${...}` reads values. With `.ftlh` files and the HTML output format directive with `auto_esc=true`, values inserted into HTML text are escaped according to the output format context. Do not casually use `?no_esc` on untrusted data.

Typical Boot 3.3 properties:

```properties
spring.freemarker.enabled=true
spring.freemarker.template-loader-path=classpath:/templates/
spring.freemarker.prefix=
spring.freemarker.suffix=.ftlh
spring.freemarker.charset=UTF-8
spring.freemarker.cache=false
```

**Difference from Thymeleaf:** `template-loader-path` sets the template source location; `prefix` is typically empty by default in FreeMarker. If you set `spring.freemarker.prefix=pages/`, view name `greeting` resolves to `pages/greeting.ftlh` inside the loader path. Do not confuse these two settings and accidentally look under `templates/templates/...`.

### 7.2. Mustache

Replace the template dependency with:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-mustache'
```

Create `src/main/resources/templates/greeting.mustache`:

```html
<!doctype html>
<html lang="en">
<head><meta charset="UTF-8"><title>Greeting Page</title></head>
<body>
  <h1>Hello {{name}}!</h1>
  <ul>
    {{#topics}}
    <li>{{.}}</li>
    {{/topics}}
  </ul>
</body>
</html>
```

In Mustache, `{{name}}` interpolates a variable with **HTML escaping** by default; `{{#topics}}` opens a repeating section when the value is a list, and `{{.}}` refers to the current element. `{{{name}}}` or `{{& name}}` is unescaped and should only be used when the value is properly validated for the context and genuinely requires trusted HTML.

Typical properties:

```properties
spring.mustache.enabled=true
spring.mustache.prefix=classpath:/templates/
spring.mustache.suffix=.mustache
spring.mustache.charset=UTF-8
```

Mustache works well when you want minimal logic in templates. Filtering and business computations should happen earlier in the controller/service; the template primarily displays the model. In larger applications, partials can be used to reuse headers, footers, and UI fragments.

### 7.3. Groovy Templates

Replace the template dependency with:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-groovy-templates'
```

Boot 3.3 provides Groovy Markup view configuration for Spring MVC when the corresponding classes/template infrastructure are on the classpath. Key properties:

```properties
spring.groovy.template.enabled=true
spring.groovy.template.resource-loader-path=classpath:/templates/
spring.groovy.template.suffix=.tpl
spring.groovy.template.charset=UTF-8
```

Templates are `.tpl` files written in **Groovy Markup Template Engine** syntax, which differs from Thymeleaf's `th:...`, FreeMarker's `${...}`, or Mustache's `{{...}}`. Illustrative Groovy Markup structure:

```groovy
html {
    head {
        title('Greeting Page')
    }
    body {
        h1("Hello ${name}!")
        ul {
            topics.each { topic ->
                li(topic)
            }
        }
    }
}
```

The snippet above is a **Groovy Markup template**, not a Java class, and has no separate `javac` command. Escaping behavior depends on template/markup configuration; do not assume Groovy automatically escapes every value. Check `spring.groovy.template.configuration.auto-escape`, tag/attribute contexts, and the Groovy Markup documentation for your exact version before rendering untrusted data.

**Regarding scope:** Groovy Templates is auto-configured by Spring Boot for **Spring MVC** in the list above; do not extrapolate from this MVC example that Groovy Markup has the same auto-configuration for WebFlux.

### 7.4. JSP: Why Isn't It Swapped In Like the Four Engines Above?

JSP is compiled and executed by the servlet container using its own mechanism and typically resides in a web application context, so it is **not** simply a matter of removing the Thymeleaf starter, adding `templates/greeting.jsp`, and expecting Boot to render it. Using JSP in Spring MVC requires configuring compatible dependencies/runtime, resolver/prefix/suffix settings such as `spring.mvc.view.prefix` and `spring.mvc.view.suffix`, a WAR structure, and respecting container limitations. In Boot 3.3, JSP **is not supported** in **executable JAR** packaging; using Tomcat/Jetty with WAR is the path documented, while Undertow does not support JSP.

If your goal is a new server-rendered UI running as an executable JAR, consider one of the four auto-configured engines, usually starting with Thymeleaf or Mustache depending on your needs.

## 8. Spring Boot 3.3 Key Property Reference Table

| Engine | Enable/Disable View Resolution | Default Template Path/Prefix | Default Suffix | Cache |
|---|---|---|---|---|
| Thymeleaf | `spring.thymeleaf.enabled` | `spring.thymeleaf.prefix=classpath:/templates/` | `spring.thymeleaf.suffix=.html` | `spring.thymeleaf.cache=true` by default |
| FreeMarker | `spring.freemarker.enabled` | `spring.freemarker.template-loader-path=classpath:/templates/`, empty prefix | `spring.freemarker.suffix=.ftlh` | `spring.freemarker.cache=false` by default in Boot 3.3 |
| Mustache | `spring.mustache.enabled` | `spring.mustache.prefix=classpath:/templates/` | `spring.mustache.suffix=.mustache` | Boot 3.3 provides `spring.mustache.servlet.cache` for MVC |
| Groovy Templates | `spring.groovy.template.enabled` | `spring.groovy.template.resource-loader-path=classpath:/templates/` | `spring.groovy.template.suffix=.tpl` | `spring.groovy.template.cache=false` by default in Boot 3.3 |

These are **representative values for the 3.3 line**, not a guarantee that property keys or defaults remain identical across every major release. Consult *Common Application Properties* for your exact application version to confirm.

Beyond the main keys, Boot can expose options such as:

- **Thymeleaf:** `spring.thymeleaf.mode`, `encoding`, `check-template`, `check-template-location`, `view-names`, `excluded-view-names`, `template-resolver-order`.
- **FreeMarker:** `spring.freemarker.charset`, `view-names`, `settings.*`, `check-template-location`, plus loader/prefix/suffix paths.
- **Mustache:** `spring.mustache.view-names`, `check-template-location`, and `servlet.*` or `reactive.*` settings depending on the web stack.
- **Groovy:** `spring.groovy.template.view-names`, `resource-loader-path`, `configuration.*`, and rendering properties available in that version.

Configure these in `application.properties`, `application.yml`, environment variables, or an appropriate Boot configuration source. Pick **one clear configuration source** per environment to avoid accidentally overriding values via property-source precedence. Do not replace the entire view infrastructure just to disable caching in development.

## 9. Adjusting Configuration by Environment

### 9.1. Development: Faster Feedback on Template Edits

With Thymeleaf, when you want templates re-read on every render during development:

```properties
# application-dev.properties
spring.thymeleaf.cache=false
```

Run with the dev profile in the sample application:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

The command above uses standard Gradle syntax on Unix shells; on Windows you can use `gradlew.bat bootRun --args="--spring.profiles.active=dev"`. When running `java -jar` directly, place `--spring.profiles.active=dev` after the JAR filename.

Disabling template caching **does not guarantee** edits in `src/main/resources/templates` appear immediately if the running process reads templates already **copied to the output classpath** and the build tool/IDE has not updated resources. Distinguish engine caching from whether the template source has actually been reloaded by the runtime. DevTools can support reload workflows when configured.

### 9.2. Production: Prefer Caching and Verify Packaging

```properties
# application-prod.properties
spring.thymeleaf.cache=true
```

Caching reduces template read/parse overhead, though production template updates typically require an appropriate release/restart. Do not enable caching to mask path errors, data errors, or broken templates. If the app uses FreeMarker/Mustache/Groovy, pick the cache properties matching your version and web stack rather than copying `spring.thymeleaf.cache`.

**Ensure resources are packaged:** in a Spring Boot executable JAR, `src/main/resources/templates/greeting.html` must exist on the JAR's classpath. You can inspect the JAR after building with `jar tf build/libs/<jar-name>.jar` and look for an entry near `BOOT-INF/classes/templates/greeting.html`. The exact artifact name depends on your project; do not hardcode it in deployment scripts.

### 9.3. Changing the Template Folder to Organize UI

If you want to store Thymeleaf templates under `src/main/resources/views/`:

```properties
spring.thymeleaf.prefix=classpath:/views/
spring.thymeleaf.suffix=.html
```

Then `return "greeting"` resolves to `classpath:/views/greeting.html`. To group templates:

```text
src/main/resources/views/
  public/
    greeting.html
  admin/
    dashboard.html
```

Controllers can return `"public/greeting"` or `"admin/dashboard"`; the resolver combines prefix and suffix to locate the file. Never pass paths derived from user parameters without strict validation (e.g., `return request.getParameter("view")`), as that could let users select unintended views.

## 10. Avoiding Conflicts When an Application Has Multiple Template Engines

Technically, multiple starters can be on the classpath and multiple `ViewResolver` beans can coexist in Spring MVC. However, if two resolvers can both accept the view name `"greeting"`, the outcome depends on resolution conditions, ordering, and each resolver's behavior. This can cause the wrong template to be chosen, missing-resource errors, or unexpected responses.

**Easiest approach to operate:** an application primarily uses **one** template engine, mixing engines only when there is a clear migration need.

When multiple engines are unavoidable, partition view names, for example:

```text
templates/
  thymeleaf/
    profile.html
  freemarker/
    invoice.ftlh

View names:
  "thymeleaf/profile"
  "freemarker/invoice"
```

And consider filtering with `view-names` (the properties below illustrate separating logical names in Spring Boot 3.3):

```properties
spring.thymeleaf.view-names=thymeleaf/*
spring.freemarker.view-names=freemarker/*
```

Configuring `view-names` helps restrict which resolver handles which names; however, you must still **verify in practice** the resolver order and outcomes in your running version, along with resource paths and view resolution for each engine. Do not assume wildcard patterns work like HTTP URL routes: here they are **view name patterns**, not HTTP mappings.

For a complex migration, you may register or customize `ThymeleafViewResolver`/`FreeMarkerViewResolver` with bean customizers and explicit ordering. In that case, read the **auto-configuration code/config for your exact version** to avoid creating duplicate beans or causing Boot to back off unexpectedly.

## 11. When Is Manual Bean Configuration Needed?

Use properties first; write manual bean configuration only when requirements exceed what properties support, such as:

- Needing to resolve templates from multiple sources (classpath, controlled database/remote repository), custom dialects, or special extensions.
- Needing complex view naming, localization, escaping, or fragment/layout behavior not covered by properties.
- Needing controlled caching and reloading per tenant/theme, or integrating an engine outside Boot's built-in list.
- Needing explicit ordering across `ViewResolver` beans in an application serving multiple view types.

### Example: Adding a Thymeleaf Dialect

Thymeleaf supports `Dialect` extensions for syntax. Spring Boot integrates dialect beans automatically when appropriate; instead of replacing the entire `SpringTemplateEngine` just to add an extension, define a dialect bean compatible with Boot's integration and verify it is picked up. The example below **only illustrates structure** (`CustomDialect` must be defined in the application):

```java
@Configuration
class ThymeleafExtensions {
    @Bean
    IDialect customDialect() {
        return new CustomDialect();
    }
}
```

This snippet is not a standalone Java application and requires the specific imports from the Thymeleaf API. The benefit of keeping auto-configuration is that Boot continues managing most resolver/engine/encoding/cache wiring and related integrations.

### Why Avoid Unnecessarily Replacing `TemplateEngine`?

If you define your own `SpringTemplateEngine`, `SpringResourceTemplateResolver`, or a bean with the same name/type that auto-configuration creates, `@ConditionalOnMissingBean` conditions may prevent default configuration from applying. Consequently, the app can lose expected integrations, message sources, dialects, or property behaviors. Identify exactly which bean needs replacing, how Boot will back off, and write an integration test to confirm.

### Distinguishing WebMvcConfigurer from @EnableWebMvc

To add small MVC customizations while keeping Boot defaults, declare a `@Configuration` class implementing `WebMvcConfigurer`. `@EnableWebMvc` is generally reserved for taking comprehensive manual control over MVC configuration. Do not add it just to serve view templates, because it alters Boot's MVC auto-configuration suite.

## 12. Spring WebFlux and Template Rendering

WebFlux uses `DispatcherHandler` and Spring WebFlux's reactive view resolution instead of MVC's `DispatcherServlet`/`ViewResolver`. At the developer level, however, the model is similar: `@Controller` returns a view name, the model holds data, and the engine renders content.

Boot 3.3 auto-configures **Thymeleaf, FreeMarker, and Mustache** for WebFlux. Standalone controller class example inside a **WebFlux application that already has a template starter and main class**:

```java
package example.reactiveview;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class ReactivePageController {
    @GetMapping("/reactive-greeting")
    public String greeting(Model model) {
        model.addAttribute("name", "WebFlux");
        return "greeting";
    }
}
```

The snippet above is a **class-level controller**, but it requires a Spring Boot WebFlux application in parent package `example.reactiveview` and the corresponding template starter; it is **not a standalone runnable app**. With Thymeleaf, `src/main/resources/templates/greeting.html` can reuse the same template from the MVC example.

**Reactive notes:**

- HTML rendering and template parsing itself consumes CPU; never assume "it will never block the event loop" merely because a controller returns `Mono` or WebFlux is used.
- FreeMarker on WebFlux does not have full feature parity with MVC; Boot documentation notes certain features are unsupported in the reactive environment.
- Thymeleaf provides `spring.thymeleaf.reactive.*` properties to control rendering/chunking modes in some scenarios. Do not assume views stream fragments like SSE by default simply because the handler is reactive.
- When the model needs service data, prefer composing non-blocking publishers; avoid calling `.block()` on the event loop. Consider response lifecycle, render performance, HTML escaping, and response caching.
- Groovy Templates is not among the three auto-configured WebFlux template engines in Boot 3.3; if custom integration is needed, evaluate framework/version support separately.

## 13. Testing Output and View Resolution

An endpoint returning status 200 is **not enough** to prove a template rendered properly. Verify that:

1. The request maps to the right controller.
2. The view name, prefix/suffix, and engine dependency match.
3. The model has all required keys and the template uses valid engine syntax.
4. The HTTP status, `Content-Type`, and body are genuinely HTML.
5. Untrusted input is properly escaped; Unicode/Vietnamese characters display properly.
6. Files are packaged and found when running the real JAR, not only from the IDE.

### Integration Test Running Against an Embedded HTTP Server

If the project includes `spring-boot-starter-test`, you can place `src/test/java/example/views/ViewsApplicationTests.java` for the **MVC + Thymeleaf** example:

```java
package example.views;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ViewsApplicationTests {
    @Autowired
    TestRestTemplate http;

    @Test
    void rendersHtmlForModelData() {
        ResponseEntity<String> result =
                http.getForEntity("/greeting?name=Lan", String.class);

        assertThat(result.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(result.getHeaders().getContentType()).isNotNull();
        assertThat(result.getHeaders().getContentType()
                .isCompatibleWith(org.springframework.http.MediaType.TEXT_HTML))
                .isTrue();

        assertThat(result.getBody())
                .contains("Hello")
                .contains("Lan")
                .contains("Spring MVC")
                .contains("<li");
    }
}
```

In the Boot project's `build.gradle`, ensure:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
```

Run `./gradlew test` (or `gradlew.bat test` on Windows). The test boots the server on a random port, invokes the live HTTP endpoint, and inspects the HTML; with Boot 3.3 and the standard test starter, `TestRestTemplate` is a suitable integration helper. If a project has multiple main classes or custom configurations, specify the Spring Boot application class explicitly in the test.

### Dedicated Escaping Test

You can add an assertion with a URL-encoded name:

```java
ResponseEntity<String> escaped = http.getForEntity(
        "/greeting?name=%3Cb%3ELan%3C%2Fb%3E",
        String.class);
assertThat(escaped.getBody()).contains("&lt;b&gt;Lan&lt;/b&gt;");
```

This snippet is a **code fragment inside a test method** that already has the `http` variable, not a complete compilable file. If untrusted HTML input produces a real `<b>Lan</b>` tag in the output, inspect whether the template uses `th:utext` or another unescaped markup mechanism.

## 14. Diagnosing Auto-Configuration and Common Errors

### 14.1. Returning Literal "greeting", No HTML

**Symptom:** Response body is the text `greeting`.

**Typical cause:** the controller uses `@RestController` or the method has `@ResponseBody`. This causes the returned string to be written as the response body.

**Fix:** use `@Controller`, return the view name and model; ensure the right media type when the client requests HTML.

### 14.2. 404 or Template Not Found Error

**Possible causes:** missing file at the path, case mismatch, wrong suffix, folder not packaged onto the classpath, missing engine starter, misconfigured prefix, or the app is running a different web stack than expected.

**Ordered troubleshooting steps:**

1. Verify whether the request matches `@GetMapping`.
2. Check the view name returned by the controller and the actual file under `src/main/resources/templates`.
3. Check `spring.<engine>.prefix`, suffix, or `template-loader-path`.
4. Verify dependencies/starters and whether the file exists inside the JAR/WAR.
5. Read the root exception and view resolver logs; do not look solely at the HTTP status.
6. If multiple engines are present, check which resolver claims the view name first.

Mapping failures, view-resolution failures, and rendering failures can all prevent a page from appearing, but **the HTTP status and exception are not necessarily identical**. Do not label every template error as 404.

### 14.3. Template Does Not Update After Editing the File

**Causes:** engine cache; resource files not yet copied by the build tool; templates running from inside a JAR; DevTools/IDE not refreshing the classpath.

**Resolution:** confirm which file is actually loaded, disable caching appropriately in development, and refresh resources or restart when needed. Keep caching enabled in production as appropriate and follow a clean deployment workflow.

### 14.4. Parse or Expression Errors

Each engine has its own syntax: Thymeleaf `th:text="${name}"`, FreeMarker `${name}`, Mustache `{{name}}`, Groovy Markup uses Groovy syntax. Changing the starter without updating templates causes parse errors or incorrect literal output. Check the file extension, namespace if applicable, model keys, and property access expressions.

With FreeMarker, accessing a missing variable can raise a template error depending on the expression/defaults; fallback syntax like `${name!"Guest"}` can be used when a default value is genuinely desired. With Thymeleaf, handle null or missing model attributes per page requirements. Never let template rendering trigger uncontrolled database queries or side effects via object method calls inside expressions.

### 14.5. XSS Introduced by Rendering Raw Data

- Thymeleaf: `th:text` escapes normally, `th:utext` does not escape.
- FreeMarker: configure HTML output format/auto-escaping, avoid `?no_esc` on user input.
- Mustache: `{{name}}` escapes, triple-mustache or `&` does not escape.
- Groovy: verify escaping mode and insertion rules per output context; do not assume safety by default.

HTML text escaping does not replace handling **JavaScript, CSS, URL, and HTML attribute contexts** or input validation/sanitization. Do not embed untrusted data directly into `<script>` tags or dangerous URLs assuming an engine handles every context automatically.

### 14.6. Views Disappear When Running an Executable JAR

Check that the files exist under `BOOT-INF/classes/templates/...` in the archive; use `classpath:` paths instead of relying on the working directory. Do not use JSP in an executable JAR due to Boot 3.3 limitations. If loading templates from an external filesystem path, clarify mounts, security, update strategy, and runtime paths.

### 14.7. Seeing Multiple Resolvers or the App Switching Web Stacks

If multiple template starters are present simultaneously, list the active `ViewResolver` beans and `view-names` to spot conflicts. If an app unexpectedly boots MVC instead of WebFlux, check whether both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath; Boot defaults to MVC when both exist. `spring.main.web-application-type` can be configured intentionally and should not be changed blindly.

### 14.8. Using the Condition Evaluation Report

Spring Boot provides an auto-configuration condition report when started with `--debug` or appropriate logging configuration. In a test environment, you can pass:

```bash
./gradlew bootRun --args='--debug'
```

Inspect entries for `ThymeleafAutoConfiguration`, `FreeMarkerAutoConfiguration`, `MustacheAutoConfiguration`, and `GroovyTemplateAutoConfiguration`. Read the **matched/not matched** conditions rather than guessing from dependency names. If using the Actuator `conditions` endpoint, restrict access because it reveals internal configuration details; never leave it publicly exposed just to debug templates.

## 15. Choosing an Engine for Real-World Needs

| Need | Usually Suitable Choice | Considerations |
|---|---|---|
| Server-rendered HTML pages with Spring MVC, forms/fragments/validation | Thymeleaf | HTML-friendly syntax, strong integration; understand escaping and layouts/fragments. |
| HTML templates and documents with complex conditions/macros | FreeMarker | Control output format, escaping, loader path, macros, and null handling. |
| Simple UI/notifications with minimal presentation logic | Mustache | Clarity, sections/partials; keep logic in the service/controller beforehand. |
| Stack already uses Groovy and wants Groovy markup templates | Groovy Templates (MVC) | Manage Groovy runtime, escaping, syntax, and WebFlux limits. |
| Legacy JSP project needing maintenance | JSP (MVC) | WAR packaging, container support, migration risk; not among the four auto-configured engines. |
| JSON-only REST API | No template engine needed | `@RestController`/`@ResponseBody` with message converters; avoid unnecessary starters. |
| WebFlux app needing server-rendered HTML | Thymeleaf, FreeMarker, or Mustache as supported by version | Reactive/streaming traits and template cost; do not assume Groovy is auto-configured. |

Spring Boot supports multiple engines so you can choose the right tool, **not to install all of them**. Each starter adds dependencies and potentially beans/view resolvers; choosing the minimal set needed makes the app easier to understand and test.

## 16. Hands-On Self-Check Exercises

**Exercise A — Change template path:** Move `greeting.html` from `templates/` to `views/`, and set `spring.thymeleaf.prefix=classpath:/views/`. Keep `return "greeting"`. Expect the endpoint to still render successfully once packaged onto the classpath.

**Exercise B — Distinguish view and body:** Temporarily change `@Controller` to `@RestController` in the MVC example and call `/greeting`. Explain why the output becomes the literal text `greeting`. Then change it back to `@Controller`.

**Exercise C — Switch engine:** Remove the Thymeleaf starter, add the Mustache starter, and use `greeting.mustache`. Verify the list items render via `{{#topics}}` and `{{.}}` without changing the controller.

**Exercise D — Test escaping:** Send `name=%3Cscript%3Ealert(1)%3C%2Fscript%3E` via `curl`; verify the HTML output does **not** contain an executable script tag. Compare escaping across engines and avoid raw-rendering configurations.

**Exercise E — Read auto-config conditions:** Run the app with `--debug`, locate the matching engine auto-configuration, and explain which dependencies/beans/properties activated it. Then set `spring.thymeleaf.enabled=false` in a test profile and observe the effect on view resolution.

**Exercise F — Compare MVC and WebFlux:** In a separate project using only the WebFlux starter, add Thymeleaf and a `@Controller` returning a view name. Explain why the server does not use `DispatcherServlet` and why generating HTML still incurs processing cost.

### Review Questions

**1. How many template engines does Spring Boot 3.3 auto-configure for MVC?**  
Four: Thymeleaf, FreeMarker, Mustache, and Groovy Templates.

**2. Does JSP share the same auto-configured starter mechanism and executable JAR execution as Thymeleaf?**  
No. JSP relies on Servlet/JSP integration and has WAR/JAR and container limitations in Boot 3.3.

**3. Does `@RestController` returning `"hello"` render `hello.html`?**  
No. `@RestController` applies `@ResponseBody` semantics, so the string is sent as the response body. `@Controller` is used for view names.

**4. Does FreeMarker use `spring.freemarker.prefix=classpath:/templates/` by default?**  
Not quite. FreeMarker uses **`template-loader-path=classpath:/templates/`** and `prefix` is typically empty. These are two different properties.

**5. Why might an edited template not appear even when template caching is disabled?**  
Because the edited source file may not have been copied to the active runtime classpath, or the app is reading templates inside a JAR; template cache is not the only layer.

**6. Does WebFlux auto-configure Groovy Templates the same way as MVC?**  
Not according to the Boot 3.3 auto-configuration list; WebFlux includes FreeMarker, Thymeleaf, and Mustache.

**7. When using two template engines, is adding both starters sufficient to avoid conflicts?**  
No. You must check view resolver conditions, view name patterns, resolver ordering, and file/resource paths.

**8. If a template renders user-supplied data, what must be checked carefully?**  
**Output-context-appropriate escaping**, avoiding raw HTML or JavaScript injection, and validating/sanitizing input where appropriate.

## 17. Official Reference Documentation

- [Spring Boot 3.3 — Servlet Web Applications: Template Engines](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html#web.servlet.spring-mvc.template-engines): list of auto-configured MVC engines and default template location.
- [Spring Boot 3.3 — Reactive Web Applications: Template Engines](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html#web.reactive.webflux.template-engines): list of engines and limitations on WebFlux.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): prefix, suffix, template path, caching, and per-engine properties.
- [Spring Boot — How-to: Customize ViewResolvers](https://docs.spring.io/spring-boot/3.3/how-to/spring-mvc.html): resolver beans and how to customize view resolution.
- [Spring Framework — MVC View Technologies](https://docs.spring.io/spring-framework/reference/web/webmvc-view.html): how Spring MVC integrates view technologies.
- [Thymeleaf — Using Thymeleaf](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html): expressions, `th:text`, escaping, and template modes.
- [Apache FreeMarker — Manual](https://freemarker.apache.org/docs/index.html): `.ftlh`, output formats, auto escaping, expressions, and macros.
- [Mustache Specification](https://mustache.github.io/mustache.5.html): variables, sections, and HTML escaping.
- [Groovy — Markup Template Engine](https://docs.groovy-lang.org/latest/html/documentation/template-engines.html#_the_markuptemplateengine): Groovy template syntax and rendering configuration.
