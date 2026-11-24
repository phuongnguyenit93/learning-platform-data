# ViewResolver and View Resolution Order in the Spring Boot Web Runtime

> **Context:** parent menu **Server Interfaces**; the focus is server-side rendered HTML with **Spring MVC** on the Servlet stack. The content also highlights important differences with Spring WebFlux. The hands-on example uses Spring Boot **4.1.2**, Java **17+**, Maven, and Thymeleaf. In Spring Boot 3.x, the MVC starter is typically named `spring-boot-starter-web`; in Boot 4.x, the starter is `spring-boot-starter-webmvc`. Actual order values, beans, and auto-configuration must be verified against the version and configuration of your application.

## Objectives

After this lesson, you can:

1. Explain the roles of `ViewResolver`, `View`, *logical view name*, `Model`, and the HTML rendering step.
2. Distinguish **mapping a route to a controller** from **mapping a view name to a UI view**; know when Spring MVC performs view resolution and when it does not.
3. Describe the **order in which multiple ViewResolvers are tried**, the meaning of `Ordered`/`order`, returning `null` when unable to resolve, and why the JSP resolver needs to be placed last.
4. Understand how Spring Boot auto-configures Thymeleaf, FreeMarker, JSP, and `ContentNegotiatingViewResolver`; distinguish **MVC's ViewResolver** from **Thymeleaf's internal TemplateResolver**.
5. Run an MVC application that returns HTML from templates, redirects using `redirect:`, and includes a custom ViewResolver with higher priority to observe the actual path taken.
6. Diagnose errors such as missing templates, one resolver intercepting another resolver's view names, 404/500 responses, `@RestController` returning a template name as text, and misconfigured prefix/suffix properties.

## 1. Where ViewResolver Fits in the MVC Pipeline

Suppose the browser sends:

~~~http
GET /pages/welcome?name=Lan HTTP/1.1
Host: localhost:8080
Accept: text/html
~~~

A controller can return the **logical view name** string `"pages/welcome"` along with a model containing `name="Lan"`. This string is **not directly a file** and is not HTML content. `ViewResolver` helps the framework locate a `View` to render the template with the model.

~~~text
Browser sends GET /pages/welcome?name=Lan
             |
             v
Servlet container / DispatcherServlet
             |
             v
HandlerMapping finds @GetMapping("/pages/welcome") method
             |
             v
HandlerAdapter invokes @Controller
             |
             +--> model.put("name", "Lan")
             +--> returns logical view name "pages/welcome"
             |
             v
ViewResolver chain (by priority)
   resolver 1 -> null if not applicable
   resolver 2 -> View if found/recognized
   resolver 3 -> only tried if needed
             |
             v
View.render(model, request, response)
   -> Thymeleaf uses template pages/welcome.html
   -> th:text safely inserts name Lan into HTML
             |
             v
HTTP 200 + Content-Type: text/html + HTML body
~~~

Separate responsibilities:

| Component | What Does It Receive? | What Does It Return or Do? |
| --- | --- | --- |
| `HandlerMapping` | HTTP request method/path/headers | Selects handler/controller; does **not** select template yet |
| `HandlerAdapter` | The located handler | Invokes handler, collects return value/model |
| `@Controller` + `Model` | Request/business data | Returns logical view name and presentation data |
| `ViewResolver` | Logical view name, `Locale`, and relevant context | Returns a `View` object or `null` if it cannot resolve |
| `View` | Model + request/response | Performs rendering/forward/redirect per view technology |
| Template engine | Template path + model | Produces complete HTML, evaluates expressions/fragments |
| Servlet response | Status, headers, content | Sends bytes back to the client |

**Boundary point:** `DispatcherServlet` coordinates multiple steps, but seeing the URL `/pages/welcome` does not mean a file `/pages/welcome.html` exists. **The controller decides the view name**; the resolver/engine and prefix/suffix determine the actual resource.

### Three Different Return Paths

~~~java
// Excerpt for comparison; imports and surrounding classes are omitted here.
@Controller
class PageController {
    @GetMapping("/page")
    String page(Model model) {
        model.addAttribute("message", "Hello");
        return "pages/home"; // logical view name -> ViewResolver
    }

    @GetMapping("/go")
    String go() {
        return "redirect:/page"; // requests redirect, does not render file "redirect:"
    }
}

@RestController
class ApiController {
    @GetMapping("/api/message")
    String message() {
        return "pages/home"; // BODY is literally the string "pages/home"
    }
}
~~~

With `@RestController` (equivalent to `@Controller` + `@ResponseBody`), a method's `String` return value is typically written straight to the response body via an HTTP message converter, **without** going through a resolver to look up HTML. With `@Controller` and a `String` return value without `@ResponseBody`, the string is interpreted as a logical view name. This is a very common source of bugs when learning SSR.

A controller can also return `ModelAndView` containing view name + model; a concrete `View`; or HTTP body types such as `ResponseEntity<T>`. Not every return type triggers the same view-resolution mechanism. For instance, returning `ResponseEntity<String>` writes the body and skips looking up a Thymeleaf template.

## 2. What Contract Is ViewResolver?

In **Spring MVC (Servlet)**, the primary interface is:

~~~java
// API shape to understand the contract, not an application class you rewrite.
public interface ViewResolver {
    View resolveViewName(String viewName, Locale locale) throws Exception;
}
~~~

The contract allows returning `null` if the resolver does not apply to the view name. The framework can then ask the next resolver in the chain. Not every resolver can verify whether a resource exists before creating a `View`; that directly affects ordering.

Example of logical view name `"pages/welcome"` with Thymeleaf:

~~~text
viewName                    = pages/welcome
spring.thymeleaf.prefix     = classpath:/templates/
spring.thymeleaf.suffix     = .html

Resource looked up          = classpath:/templates/pages/welcome.html
~~~

This is the typical rule with Thymeleaf auto-configuration. If you change `spring.thymeleaf.prefix=classpath:/views/`, the resource needs to be placed at `src/main/resources/views/pages/welcome.html` (in a standard Maven project), even though the controller URL does not have to change.

A resolver can know on its own that it does **not** handle a certain group of view names via `viewNames`/`excludedViewNames` configuration or custom rules. This is important when an application mixes multiple engines or layouts: a specialized resolver only claims the group of views it handles.

## 3. Lookup Order: Lower `order` Numbers Have Higher Priority

When multiple `ViewResolver` instances are present, MVC sorts them by priority, typically via `Ordered` or the corresponding annotation. **The smaller the order number, the higher the priority**:

~~~text
Ordered.HIGHEST_PRECEDENCE  = -2147483648  (very high priority)
order -100                  = higher priority than 0
order 0
order 10
order 100
Ordered.LOWEST_PRECEDENCE   = 2147483647   (very low priority)
~~~

A simple mental model for a **regular resolver chain**:

~~~java
// Pseudocode to understand the rule, not DispatcherServlet's actual code.
for (ViewResolver resolver : sortedResolvers) {
    View view = resolver.resolveViewName(viewName, locale);
    if (view != null) {
        return view;
    }
}
throw new IllegalStateException("No matching View");
~~~

This pseudocode conveys the priority and fallback rule; it **does not fully describe** composite resolvers such as `ContentNegotiatingViewResolver`. A composite resolver may query **multiple member resolvers** and then select a `View` based on media type, rather than simply stopping at the first resolver that returns non-null.

### When Does "Fallback" Actually Happen?

- Resolver A **does not apply or cannot resolve the view** and returns `null` → MVC tries the next resolver.
- Resolver A returns a `View`, but that `View` **fails to render** once selected → this usually causes a render/response error; there is no guarantee Spring will go back and try resolver B.
- Two resolvers can both resolve the same view name → ordering and, if present, content negotiation affect the choice; avoid overlapping patterns or set explicit order values.
- Two resolvers have the **same order** → do not design around an arbitrary/unguaranteed ordering among beans; proactively assign distinct values.

**Do not equate a resolver returning `null` directly with HTTP 404 or 500**. The final HTTP status depends on whether a handler exists, exception handlers, and the stage where the failure occurred. An unmatched route is usually 404; a matched route where template rendering fails usually leads to a server error. However, routing or view resolution can be customized, so inspect the actual exceptions and logs.

### Why Should `InternalResourceViewResolver` Come Last?

`InternalResourceViewResolver` typically builds a Servlet/JSP view from a logical name + prefix/suffix. With JSP, it cannot be sure whether the target resource exists merely by creating the `View`: the actual check happens during `RequestDispatcher.forward(...)`. Therefore, it may **return a View even when the physical JSP does not exist**, preventing subsequent resolvers from being tried. Spring Framework documentation emphasizes **placing InternalResourceViewResolver last in the chain**.

Incorrect example:

~~~text
order 0   : InternalResourceViewResolver (looks up JSP by name)
order 10  : ThymeleafViewResolver

controller returns "pages/welcome":
InternalResourceViewResolver may return InternalResourceView
-> never reaches Thymeleaf as expected
-> dispatches to wrong JSP/resource or errors.
~~~

A sensible configuration when mixing is unavoidable:

~~~text
Specialized resolver: only accepts "admin/*" or a clearly defined group
Thymeleaf/FreeMarker: handles corresponding logical names
InternalResourceViewResolver: final fallback if JSP/Servlet views are still used
~~~

Note that this is a **way to organize priorities**, not fixed default order numbers across every Boot version. For JSP in a Spring Boot executable **JAR**, support is limited; normally choose a suitable template engine or WAR packaging rather than adding JSP solely to demonstrate ordering.

## 4. Typical Resolvers and Their Roles

| Type | Role | When to Use / Caveats |
| --- | --- | --- |
| `ThymeleafViewResolver` | Maps logical view name to `ThymeleafView` to process HTML/templates | SSR web pages; requires Thymeleaf starter and matching template resources |
| `FreeMarkerViewResolver` | Renders FreeMarker templates | When the app uses FreeMarker; prefix/suffix and loader path differ from Thymeleaf |
| `InternalResourceViewResolver` | Builds internal view/forward to JSP or Servlet resources | Must be placed last; not a general mechanism for serving arbitrary static files |
| `BeanNameViewResolver` | Matches view name against a bean of type `View` | Special view cases, e.g., custom view or report |
| `ContentNegotiatingViewResolver` | Selects a View based on the client's desired media type, usually via `Accept` | Composite resolver; **not a template engine** |
| Custom `ViewResolver` | Resolves views using custom logic, can return `null` | Use only for clear needs; must control order, caching, names, and content type |
| `UrlBasedViewResolver` | Base class mapping view names to URLs via prefix/suffix | Suitable only when URL mapping is simple; subclasses differ in resource-existence checks |

You do not need to declare all resolvers manually. With the MVC starter and an appropriate template engine, Spring Boot auto-configures most of the pipeline. Intervene only when the defaults cannot express your application's view routing logic.

### `ContentNegotiatingViewResolver` Does Not Mean "Try in Order Until the First Match"

Suppose an endpoint can return HTML or another report format. The client sends:

~~~http
Accept: text/html
~~~

When configured, `ContentNegotiatingViewResolver` can ask other resolvers for candidate `View` instances and then pick the View matching the requested media type. It is typically given **very high priority** to coordinate the other resolvers.

Do not assume that declaring `@Bean ViewResolver order=-999` always runs ahead of all content negotiation behavior. Boot may provide a composite resolver with `Ordered.HIGHEST_PRECEDENCE` that in turn delegates to member resolvers. Thus "ordering" has **two levels**:

1. The order among resolvers that MVC processes at the outer level.
2. The order and selection criteria **inside the composite resolver** by candidate view and `Accept` header.

If a system only needs HTML from Thymeleaf and JSON from REST, the simpler architecture is to **separate HTML routes using `@Controller`** and **JSON routes using `@RestController`/`@ResponseBody`**, rather than adding content negotiation solely to route APIs.

### Do Not Confuse Three Different Mechanisms

| Mechanism | Input | Output |
| --- | --- | --- |
| `HandlerMapping` | HTTP request URL/method/headers | Handler/controller method |
| Spring MVC `ViewResolver` | Logical view name, `Locale` | Spring MVC `View` |
| Thymeleaf **TemplateResolver** | Template name, locale, template mode, engine policy | Template/resource for Thymeleaf to process |

The property `spring.thymeleaf.template-resolver-order` governs the **order of template resolvers inside Thymeleaf** when multiple template resolvers exist. It is **not equivalent** to the `order` of a Spring MVC `ViewResolver`; changing this property does not change Thymeleaf's priority relative to a JSP ViewResolver.

## 5. How Does Spring Boot Auto-Configure View Resolution?

Typically you add:

- `spring-boot-starter-webmvc`: configures the Servlet web runtime and Spring MVC for Boot 4.x.
- `spring-boot-starter-thymeleaf`: adds Thymeleaf integration and its auto-configuration.

With templates under `src/main/resources/templates/`, Boot typically uses the prefix `classpath:/templates/` and suffix `.html`. When you return `"pages/welcome"`, the app looks up `templates/pages/welcome.html`.

Key Thymeleaf properties:

~~~properties
# Typically these are the defaults; written explicitly for visibility.
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.encoding=UTF-8
spring.thymeleaf.enabled=true

# For development to see template changes on restart/with devtools.
# Keep caching enabled in production unless hot updates are required.
spring.thymeleaf.cache=false
~~~

Do not confuse `spring.mvc.view.prefix` / `spring.mvc.view.suffix` with `spring.thymeleaf.prefix` / `spring.thymeleaf.suffix`. The `spring.mvc.view.*` group applies to the internal/JSP view resolver; Thymeleaf uses its own property group.

Boot may register `ContentNegotiatingViewResolver`, `BeanNameViewResolver`, and a default internal-resource resolver alongside resolvers provided by template starters. Bean counts, orders, auto-configuration conditions, and exact names can vary by version, dependencies, and application-defined beans; **do not build business logic around a default order table from an older Boot release**.

**Safety policy:** Template files sit within the application's **code/trust boundary**, with potential access to the model and beans depending on integration. Do not allow users to upload or directly edit server-executable templates. Do not pass arbitrary query parameters directly as view names: for example, `return request.getParameter("view")` can lead to unintended resource access or view injection. Map user input through an allowlist of permitted view names.

## 6. Runnable Example: Thymeleaf and a High-Priority ViewResolver

Goals of the demo application:

- `GET /pages/welcome?name=Lan` → controller returns `"pages/welcome"` → custom resolver **returns null** → Thymeleaf renders the HTML template.
- `GET /pages/about` → Thymeleaf renders another template.
- `GET /pages/plain` with `Accept: text/plain` → controller returns `"special/plain"` → application resolver returns a **custom View** → plain-text content.
- `GET /pages/start` → HTTP redirect to the welcome page.
- `GET /api/ping` → REST JSON body; does not use ViewResolver to look up a template.

This is **a standalone project** using Spring Boot 4.1.2, Java 17, and Maven 3.6.3+.

### Directory Structure

~~~text
view-resolver-demo/
  pom.xml
  src/main/java/com/example/viewdemo/
    ViewDemoApplication.java
    PageController.java
    ApiController.java
    PriorityViewConfig.java
  src/main/resources/
    application.properties
    templates/pages/welcome.html
    templates/pages/about.html
~~~

### `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>view-resolver-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

The Boot parent selects compatible dependencies. The MVC starter uses embedded Tomcat by default. The Thymeleaf starter provides the view engine to locate and render templates.

### `ViewDemoApplication.java`

~~~java
package com.example.viewdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ViewDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ViewDemoApplication.class, args);
    }
}
~~~

The main class sits in the parent package of the controllers/config so component scanning registers them.

### `PageController.java`

~~~java
package com.example.viewdemo;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class PageController {

    @GetMapping("/pages/welcome")
    public String welcome(
            @RequestParam(defaultValue = "Guest") String name,
            Model model) {
        model.addAttribute("name", name);
        return "pages/welcome";
    }

    @GetMapping("/pages/about")
    public String about(Model model) {
        model.addAttribute("product", "Spring Boot");
        return "pages/about";
    }

    @GetMapping("/pages/plain")
    public String plain(Model model) {
        model.addAttribute("message", "View rendered by the application itself");
        return "special/plain";
    }

    @GetMapping("/pages/start")
    public String start() {
        return "redirect:/pages/welcome?name=Lan";
    }
}
~~~

Do not use `@ResponseBody` on methods returning template names. Values in the model **do not decide the view**; the view is chosen by `return "pages/welcome"`. The `"pages/*"` strings are all resolved by Thymeleaf using template files in the corresponding directory.

### `ApiController.java`

~~~java
package com.example.viewdemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}
~~~

The HTTP response body is JSON, for example `{"status":"ok"}`. This is reference code to contrast writing an HTTP body via a message converter with resolving an HTML template.

### `PriorityViewConfig.java` — a Resolver with Explicit Ordering

~~~java
package com.example.viewdemo;

import java.util.Locale;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.web.servlet.View;
import org.springframework.web.servlet.ViewResolver;
import org.springframework.web.servlet.view.AbstractView;

@Configuration(proxyBeanMethods = false)
public class PriorityViewConfig {

    @Bean
    ViewResolver priorityViewResolver() {
        return new PriorityResolver();
    }

    // This resolver only accepts "special/plain"; other names return null.
    static final class PriorityResolver implements ViewResolver, Ordered {
        private final View plainView = new PlainTextView();

        @Override
        public int getOrder() {
            return -100; // smaller number -> higher priority
        }

        @Override
        public View resolveViewName(String viewName, Locale locale) {
            return "special/plain".equals(viewName) ? plainView : null;
        }
    }

    // Custom view writing the response: acts as a very simple renderer.
    static final class PlainTextView extends AbstractView {
        PlainTextView() {
            setContentType("text/plain;charset=UTF-8");
        }

        @Override
        protected void renderMergedOutputModel(
                Map<String, Object> model,
                HttpServletRequest request,
                HttpServletResponse response) throws Exception {
            response.setContentType(getContentType());
            response.getWriter().write(
                    String.valueOf(model.getOrDefault("message", "")));
        }
    }
}
~~~

Notable points:

- `PriorityResolver` implements both `ViewResolver` and `Ordered` to declare its order. The value `-100` means **higher priority than resolvers with larger order numbers**, though Boot may have a composite `ContentNegotiatingViewResolver` with higher precedence; that composite resolver may query `PriorityResolver` as a delegate. Do not interpret `-100` as "guaranteed to be the first method invoked in every version."
- For `"special/plain"`, the resolver returns `PlainTextView`; for `"pages/welcome"`, it returns `null` so another resolver can proceed.
- `PlainTextView` reads the `message` value from the model and writes a `text/plain` body. This is a didactic example, **not a template engine to use in production**.
- `@Configuration(proxyBeanMethods = false)` is appropriate because the code does not call one `@Bean` method directly from another `@Bean` method.
- The custom resolver claims only one view name; this pattern avoids "hijacking" ordinary Thymeleaf templates.

### `application.properties`

~~~properties
server.port=8080
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.encoding=UTF-8
spring.thymeleaf.cache=false
~~~

The exercise sets `cache` to `false` so template edits are easy to test; production should review this based on operational needs. If environment variables or command-line arguments override a property, the effective value may differ from this file.

### Template `src/main/resources/templates/pages/welcome.html`

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Welcome Page</title>
</head>
<body>
    <h1>Hello, <span th:text="${name}">Guest</span>!</h1>
    <p>This page is rendered on the server using Thymeleaf.</p>
    <a href="/pages/about">About</a>
</body>
</html>
~~~

`th:text="${name}"` reads the model attribute; Thymeleaf escapes content by default for HTML text context. If a client sends `name=<script>...`, it is not injected directly as markup when using `th:text`. Do not switch to `th:utext` for untrusted input.

### Template `src/main/resources/templates/pages/about.html`

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>About</title>
</head>
<body>
    <h1 th:text="${product}">Product</h1>
    <p>HTML view resolved from logical name <code>pages/about</code>.</p>
    <a href="/pages/welcome?name=Lan">Back to welcome page</a>
</body>
</html>
~~~

### Run and Observe

In the `view-resolver-demo` directory:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i -H "Accept: text/html" \
  "http://localhost:8080/pages/welcome?name=Lan"
~~~

Expect **HTTP 200**, HTML Content-Type, and a body containing:

~~~html
<h1>Hello, <span>Lan</span>!</h1>
~~~

Other HTML parts are still in the body; headers such as Date/Transfer-Encoding may vary.

~~~bash
curl -i -H "Accept: text/html" http://localhost:8080/pages/about
~~~

Expect the About page with `Spring Boot` inside the `h1` tag. Both pages are rendered by Thymeleaf via logical view names.

~~~bash
curl -i -H "Accept: text/plain" http://localhost:8080/pages/plain
~~~

Expect HTTP 200, Content-Type `text/plain;charset=UTF-8`, and the exact body:

~~~text
View rendered by the application itself
~~~

This is the **View** created by `PriorityResolver`, with no `templates/special/plain.html` file needed. Requesting `Accept: text/plain` avoids ambiguity when a content-negotiating resolver evaluates multiple view formats.

~~~bash
curl -i http://localhost:8080/pages/start
~~~

Expect a redirect response (usually HTTP 302) and `Location` pointing to `/pages/welcome?name=Lan`. Use `curl -i -L ...` to follow the redirect and receive HTML; there is no template file `redirect:/pages/welcome?name=Lan.html`.

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/ping
~~~

Expect HTTP 200 and a JSON body with field `status` equal to `ok`. This route does not go through the Thymeleaf ViewResolver.

On Windows PowerShell 5.1, use `curl.exe` to ensure the real cURL binary runs, for example `curl.exe -i "http://localhost:8080/pages/welcome?name=Lan"`. You can build the JAR using:

~~~bash
mvn package
java -jar target/view-resolver-demo-0.0.1-SNAPSHOT.jar
~~~

Java code must be built with Maven because Spring/Thymeleaf dependencies are not on the classpath of bare `javac`. When running the JAR, templates reside on the classpath at `BOOT-INF/classes/templates/...` inside the Spring Boot-packaged archive.

### What the Example Verifies

| URL | Logical Name or Return | Expected Observation |
| --- | --- | --- |
| `/pages/welcome?name=Lan` | `pages/welcome` | Thymeleaf selects template `pages/welcome.html` and renders the model |
| `/pages/about` | `pages/about` | Thymeleaf renders the About page |
| `/pages/plain` | `special/plain` | Custom resolver returns a `text/plain` View |
| `/pages/start` | `redirect:/pages/welcome?name=Lan` | HTTP redirect; does not look up a `redirect:*` file |
| `/api/ping` | `Map<String,String>` from `@RestController` | JSON body via message conversion, no view lookup |

If you want to verify fallback in a real runtime, set a breakpoint or add logging inside `PriorityResolver.resolveViewName(...)` and observe `viewName` for HTML requests. **Note** that `ContentNegotiatingViewResolver` may invoke the resolver again as a delegate or evaluate multiple candidates, so **do not assert an exact invocation count**; verify the actual View used and the HTTP response content.

## 7. What Happens When Multiple Template Engines Exist?

Suppose a project integrates both Thymeleaf and FreeMarker:

~~~text
src/main/resources/templates/pages/welcome.html
src/main/resources/templates/pages/report.ftlh
~~~

When the controller returns `"pages/report"`, both resolvers may be queried. If both resolvers are configured to accept any name, selection can depend on order, resource-existence checks, and content negotiation. Good design is to **partition view names** clearly:

~~~text
pages/*    -> Thymeleaf
report/*   -> FreeMarker
special/*  -> View bean or custom resolver
JSP        -> final fallback (if the project truly requires it)
~~~

This is a design convention; it does not take effect automatically just by creating folder names. You must configure the resolvers/engines so they **accept only matching patterns**, such as `viewNames`/`excludedViewNames` if supported by the resolver, and set appropriate orders. You should not have two resolvers both "unconditionally claiming to handle" every template name.

**Illustrative configuration example** in a project with FreeMarker and Thymeleaf (do not paste directly into the demo above without adding the engine and considering auto-configuration):

~~~java
// Illustration: assuming you have a ThymeleafViewResolver bean already created.
// You do not need to adjust order in a single-engine application.
thymeleafViewResolver.setViewNames(new String[] {"pages/*"});
thymeleafViewResolver.setOrder(10);

// Assuming FreeMarkerViewResolver has the dependency and proper template loader:
freeMarkerViewResolver.setViewNames("reports/*");
freeMarkerViewResolver.setOrder(20);

// If JSP is needed as a fallback:
internalResourceViewResolver.setOrder(Ordered.LOWEST_PRECEDENCE);
~~~

This snippet is **not a runnable standalone class**; it only clarifies the principle of configuring view-name patterns and order when an application uses multiple engines. Do not confuse `spring.thymeleaf.view-names` with `spring.thymeleaf.template-resolver-order`, and avoid modifying auto-configured beans by arbitrary name/order without checking the actual version.

### Distinguishing View Resolution and Static Resource Mapping

- The template `src/main/resources/templates/pages/welcome.html` is normally **not served as a static file**. It is looked up by the engine using a logical view name and rendered with a model.
- The file `src/main/resources/static/css/site.css` is normally served directly by the **static resource handler** when a client requests `/css/site.css`.
- Returning `"css/site"` from a `@Controller` does **not** mean it will automatically find `static/css/site.css` as a template.

When debugging, determine whether the request is handled by the controller's `RequestMappingHandlerMapping` or the static resources' `ResourceHttpRequestHandler`; they are two separate paths.

## 8. Redirect, Forward, and Special View Names

Spring MVC supports view names with special prefixes:

- `redirect:/pages/welcome`: generates an HTTP redirect so the client performs a new request; status is typically 302 unless another redirect status is chosen. Model data/flash attributes must be handled explicitly if they need to survive the redirect.
- `forward:/internal/path`: requests a server-side Servlet forward, **without** sending a 3xx status to change the browser URL. With resolvers based on `UrlBasedViewResolver`, this produces an `InternalResourceView`/`RequestDispatcher.forward`. It is not synonymous with rendering a Thymeleaf view path.
- `"pages/welcome"`: a regular logical view handled by the resolution chain.

To pass data across a redirect, use `RedirectAttributes` to attach allowed query/path variables or flash attributes. Do not put sensitive data in the query string; do not store data indefinitely in the HTTP session just to share a model across multiple pages.

**Regarding security:** avoid redirecting directly to user-supplied URLs without validation, such as `return "redirect:" + request.getParameter("next")`. This can create an open redirect vulnerability. Allow only internal paths or validate the target against an allowlist.

## 9. How Is ViewResolver Different in Spring WebFlux?

WebFlux selects handlers differently at the reactive layer, yet still retains the concept of **view name → view rendering**:

| Aspect | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Front controller | `DispatcherServlet` | `DispatcherHandler` |
| ViewResolver interface | `org.springframework.web.servlet.ViewResolver` | `org.springframework.web.reactive.result.view.ViewResolver` |
| Resolver result | `View` or `null` | `Mono<View>` (can be empty if unresolved) |
| View rendering component | MVC view handling, Servlet stack `View.render(...)` | `ViewResolutionResultHandler` with reactive `View` |
| Template engine | Thymeleaf/FreeMarker and configured view technologies | WebFlux-compatible engines; configuration differs from MVC |
| JSP | Can use Servlet/JSP, subject to packaging limits | JSP resolver does not apply as on the Servlet stack |
| I/O mechanism | Servlet/MVC request execution | Publisher/Subscriber pipeline, non-blocking integration |

In WebFlux, `HandlerResult` holds the return value and model; `ViewResolutionResultHandler` uses resolvers to choose a view by logical name. Handler authors can return a `String` view name in the appropriate context, but must not copy code using `jakarta.servlet.http.HttpServletResponse` and `InternalResourceViewResolver` from MVC to WebFlux. Those are **two interfaces sharing a name but with different packages and semantics**.

WebFlux documentation also warns that template views can access internal context information/beans, so untrusted parties must not edit templates. When using a reactive engine to render large pages or a model containing publishers, buffering, streaming, and event-loop blocking must also be considered; SSR HTML is not automatically exempt from reactive rules.

## 10. Diagnosing View Resolution Failures

An effective checklist sequence:

1. **Did the URL match a controller?** Check `@GetMapping`, HTTP method, context path, and whether the `@Controller` is component-scanned. A route 404 happens **before** view resolution.
2. **Is the return value a view name or a body?** Check `@Controller` versus `@RestController` and `@ResponseBody` on the method; `String` has different semantics.
3. **What is the exact logical view name?** Log or set a breakpoint in the controller: `"pages/welcome"` differs from `"/pages/welcome"` and `"pages/welcome.html"` depending on the resolver.
4. **Where is the actual template file?** With default Thymeleaf: `src/main/resources/templates/pages/welcome.html`. Check case sensitivity, suffix, encoding, and whether the file is packaged in the JAR.
5. **Which starters are on the classpath?** Are `spring-boot-starter-thymeleaf` or an appropriate engine present? Did you mix up MVC/WebFlux starters or add multiple engines?
6. **Which resolver runs first?** Inspect the `ViewResolver` beans list, `getOrder()`, view-name patterns, and whether a resolver returns `null` or a `View`. Pay special attention to `InternalResourceViewResolver`.
7. **Is content negotiation involved?** If the response changes by `Accept`, inspect `ContentNegotiatingViewResolver` and candidate View Content-Types; do not assume simple ordering.
8. **Is there a rendering error?** HTML template parse errors, `th:text` expressions, missing model attributes, broken layouts/fragments, or missing files can throw exceptions **after the route matched**.
9. **Is a cache holding an old template?** Check `spring.thymeleaf.cache`, engine template cache, reload mechanisms, and dev/prod environment differences.
10. **Which HTTP status is sent?** Use `curl -i` to distinguish 3xx redirects, 200 HTML, 404 routes, 406 content negotiation, and 500 render failures; do not guess from a blank browser page.

Common symptoms table:

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| Browser literally shows `pages/welcome` | Controller is `@RestController` or has `@ResponseBody` | Switch HTML route to `@Controller`, return logical name |
| `GET /pages/welcome` returns 404 | No matching URL mapping or controller not scanned | Check `HandlerMapping` and package structure |
| Controller runs but reports template cannot be resolved/rendered | Missing template, wrong prefix/suffix, or missing engine dependency | Check view name, resource path, classpath, stack trace |
| Using two template engines renders the wrong view | Resolvers accept overlapping patterns; unclear order | Separate view-name patterns and define explicit priorities |
| JSP resolver "eats" all view names | `InternalResourceViewResolver` placed ahead of other resolvers | Place it last in the chain or remove if JSP is unused |
| Thymeleaf template edited but page does not update | Cache or running artifact contains old version | Disable dev cache, check deploy/restart/build |
| `redirect:` returns unexpected content | `@ResponseBody` present or invalid redirect URL | Check controller return semantics and `Location` |
| Client `Accept: application/json` does not receive JSON | Route only has HTML view, content negotiation or `produces` mismatch | Separate JSON API or configure explicit representations |
| Template displays literal `${name}` | Thymeleaf engine not running or static file not evaluating expressions | Access via controller route to render, inspect `th:text` |
| JSP works in WAR but not in executable JAR | JSP/Servlet packaging limitation | Use a supported WAR or switch template engine |

### Tips for Observing Active Resolvers

Logging can be enabled in development:

~~~properties
logging.level.org.springframework.web.servlet=DEBUG
logging.level.org.springframework.web.servlet.view=TRACE
logging.level.org.thymeleaf=DEBUG
~~~

Log levels and logger names may vary across versions; do not rely on a single log line as a test assertion. You can register a diagnostic runner **only when needed** to print `ViewResolver` beans and their orders from `ApplicationContext`, or place breakpoints inside your custom resolver and `ThymeleafViewResolver`. Do not enable TRACE for the entire web stack in production under heavy traffic or with sensitive data.

If `spring-boot-starter-actuator` is present, the beans/conditions endpoints can help explain auto-configuration, but proper exposure and authorization controls are required. The condition report explains why a bean was configured; an HTTP request test verifies which view actually renders.

## 11. Short Exercises with Answers

**Scenario 1.** An application declares resolver A with order=5 and resolver B with order=10. Both accept `"home"` and return a View. Which resolver takes precedence in a standard chain?

**Answer:** A has a smaller order number, so it takes precedence. However, if `ContentNegotiatingViewResolver` sits above them, inspect how it gathers candidates and selects by media type; never assert A always wins from a single order pair alone.

**Scenario 2.** Resolver A returns `null` when given `"reports/monthly"`. Does that immediately mean HTTP 404?

**Answer:** No. MVC can ask the next resolver; an error occurs only if the entire pipeline fails to produce a valid result. The HTTP status depends on routing and error handling.

**Scenario 3.** Why shouldn't `InternalResourceViewResolver` be placed at order=0 ahead of Thymeleaf?

**Answer:** It can create a JSP/internal View without verifying that the target file exists, thereby claiming the view name and preventing fallback to Thymeleaf. Place the JSP resolver last if still in use.

**Scenario 4.** `@RestController` returns `"pages/welcome"` and the browser only shows that literal string. What needs to be fixed?

**Answer:** Use `@Controller` (without `@ResponseBody`) for the HTML page route and ensure a matching Thymeleaf template exists. A REST controller writes a `String` directly into the HTTP body.

**Scenario 5.** You need to move templates from `templates/` to `views/`. Is changing `spring.mvc.view.prefix` alone enough?

**Answer:** Not when using Thymeleaf. Set `spring.thymeleaf.prefix=classpath:/views/` and place files accordingly, because `spring.mvc.view.*` properties target internal resource/JSP views.

**Scenario 6.** Using `return "redirect:/pages/welcome"`; does Spring look for `redirect:/pages/welcome.html` in templates?

**Answer:** No. `redirect:` is a special view name that returns an HTTP redirect. The browser can then send a new request to the redirected path.

**Scenario 7.** A resolver returns the right View, but the template fails due to an expression error. Will the framework necessarily try the next resolver?

**Answer:** No. A failure during rendering is usually an exception from the already-selected View/engine, unlike `resolveViewName` returning `null`. Investigate the template parse/render error and model.

**Scenario 8.** Is `spring.thymeleaf.template-resolver-order` the order of the Spring MVC `ViewResolver`?

**Answer:** No. This property orders template resolvers inside Thymeleaf; the Spring MVC ViewResolver is a separate layer.

## 12. Summary of Rules to Remember

1. **Route mapping first, view resolving second:** `HandlerMapping` selects the controller; `ViewResolver` selects the View by logical name.
2. **Lower `order` numbers → higher priority:** if a resolver returns `null`, the framework can proceed to the next one.
3. **An overly eager resolver can block fallback:** especially `InternalResourceViewResolver`/JSP; place it last.
4. **`ContentNegotiatingViewResolver` is a composite case:** it can query multiple resolvers and select a candidate based on `Accept`; do not mechanically reduce all behavior to "first non-null."
5. **ViewResolver differs from TemplateResolver:** Spring MVC picks the View; Thymeleaf locates and processes the template.
6. **`@Controller` returns view names; `@RestController` returns bodies:** distinguish them to avoid literal strings in the response.
7. **A Thymeleaf-only project typically needs no custom resolver:** Boot defaults plus proper template paths are sufficient.
8. **With multiple view technologies, name clearly and order explicitly:** avoid overlapping prefixes/suffixes and patterns; verify actual runtime behavior.
9. **Redirect/forward are not template files:** both control response flow with distinct HTTP semantics.
10. **Never expose dynamic templates or view names to untrusted input:** expose only view and redirect targets permitted by the application.

## Official Documentation

- [Spring Framework — MVC View Resolution, ViewResolver chaining, redirect and forward](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/viewresolver.html)
- [Spring Framework — MVC View Resolvers configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/view-resolvers.html)
- [Spring Framework — MVC Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html)
- [Spring Framework — @ResponseBody and @RestController](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html)
- [Spring Boot — Web MVC and Template Engines](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot — Application properties, spring.thymeleaf.*](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot — Build Systems and Starter names](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Framework — WebFlux View Resolution and View Technologies](https://docs.spring.io/spring-framework/reference/web/webflux-view.html)
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)

**Practical takeaway:** Verify whether the controller genuinely returns a **logical view name**; then examine the resolver list by order, `null`-return rules, content negotiation, and template resources. Only by understanding each layer can you explain accurately why a URL reaches the expected HTML, gets claimed by another resolver, or fails during rendering.