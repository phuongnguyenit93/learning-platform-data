# ViewResolver and Rendering Views from View Names in Spring MVC

## 1. Lesson Objectives

In a server-side HTML Spring MVC application, a controller typically **does not manually assemble an entire HTML string**. Instead, the controller executes business logic, puts data into a `Model`, and returns a **logical view name** such as `"welcome"`, `"products/list"`, or `"orders/detail"`.

Spring MVC uses `ViewResolver` to translate that logical name into a `View` object capable of rendering the page. The `View` combines data in the model with the corresponding template, producing the HTTP response sent to the browser.

Example:

```java
@GetMapping("/welcome")
public String welcome(Model model) {
    model.addAttribute("name", "Lan");
    return "welcome";
}
```

Here `"welcome"` is a **view name**, not the response content itself and not the `/welcome` URL. With Thymeleaf auto-configured by Spring Boot, this name normally maps to `src/main/resources/templates/welcome.html`.

This lesson focuses on the **Spring MVC/Servlet stack**: execution flow, resolver types, Spring Boot configuration, a runnable example, redirects, and common pitfalls. Spring WebFlux also has a `ViewResolver` concept, but it uses a different API.

## 2. Roles of DispatcherServlet, ModelAndView, ViewResolver, and View

| Component | Primary role | When does it participate? |
|---|---|---|
| `DispatcherServlet` | Front Controller coordinating HTTP requests, handlers, results, and view rendering | Throughout the MVC flow |
| `HandlerMapping` | Finds the handler/controller matching the URL and HTTP method | Before invoking the controller |
| `HandlerAdapter` | Calls the controller method, handles parameters and return values | During request processing |
| `Model` | Collection of attributes used by the view during rendering | Populated by controller or model binders |
| `ModelAndView` | Represents the model together with a `View` name or concrete `View` | Once the controller/handler has executed |
| `ViewResolver` | Resolves a logical view name into a `View` object | When the result needs to be rendered as a view |
| `View` | Renders the model into a response using a specific UI technology | After the view is resolved |

Core Spring MVC interface:

```java
package org.springframework.web.servlet;

public interface ViewResolver {
    View resolveViewName(String viewName, java.util.Locale locale)
            throws Exception;
}
```

This is an **abbreviated illustrative signature** of the API method, not a Java file to recreate an existing interface. `resolveViewName` may return `null` to indicate that the current resolver cannot resolve that view name.

`View` is responsible for rendering the response from model data. When a controller returns a `View` object directly, Spring MVC can use that object without resolving a view name through the resolver chain.

## 3. Complete View Rendering Flow

Diagram for an HTTP request serving HTML:

```text
GET /welcome?name=Lan
        |
        v
DispatcherServlet
        |
        v
HandlerMapping -> HandlerAdapter
        |
        v
@Controller#method(...)
  model.addAttribute("name", "Lan")
  return "welcome"
        |
        v
ModelAndView (viewName = "welcome", model = { name: "Lan" })
        |
        v
DispatcherServlet handles view
        |
        v
ViewResolver.resolveViewName("welcome", locale)
        |
        v
View (e.g., ThymeleafView)
        |
        v
View.render(model, request, response)
        |
        v
Template + model -> HTML response
        |
        v
Browser displays page
```

Step-by-step explanation:

1. The browser sends a request to the application; `DispatcherServlet` accepts it based on servlet mapping configuration.
2. `HandlerMapping` locates `@GetMapping("/welcome")`; `HandlerAdapter` invokes the method and resolves parameters like `Model` and `@RequestParam`.
3. The controller adds `name = "Lan"` to the model and returns `"welcome"`.
4. Spring MVC treats a `String` return value in a standard `@Controller` as a **view name**, bundling the view name and model for rendering. A controller can also return `ModelAndView` directly.
5. `DispatcherServlet` consults appropriate `ViewResolver`s to obtain a `View` for the name `welcome`.
6. A template resolver such as Thymeleaf locates/evaluates the matching template using the model and locale according to that engine's rules.
7. `View.render(...)` writes the response body, typically HTML with `Content-Type: text/html`.

Thus, **`ViewResolver` finds or constructs the `View` object; `View` does the rendering**. Do not confuse a resolver with a controller, template engine, HTTP client, or a specific directory.

## 4. How Logical View Names Differ from Template Files and URLs

Suppose the controller returns:

```java
return "pages/welcome";
```

With Spring Boot's default Thymeleaf setup:

```text
View name:       pages/welcome
Template prefix: classpath:/templates/
Template suffix: .html
Template:        classpath:/templates/pages/welcome.html
Source file:     src/main/resources/templates/pages/welcome.html
```

Not every resolver simply concatenates a prefix and suffix. For example, `BeanNameViewResolver` maps a name to a `View` bean, while `ContentNegotiatingViewResolver` coordinates multiple resolvers to select a representation based on media type.

These three addresses mean different things:

- URL `/welcome`: HTTP routing, used by `HandlerMapping` to locate the controller.
- View name `pages/welcome`: logical name returned by the controller for Spring MVC to resolve.
- Template resource `classpath:/templates/pages/welcome.html`: file or resource used by the template engine to render HTML.

Changing `@GetMapping("/welcome")` to `@GetMapping("/hello")` does not require changing the view name. Multiple URLs can also return the same view, differing only in model data.

## 5. Spring Boot 3.x + Java 17 + Thymeleaf Example

This example is a Spring Boot 3.x application using **Spring MVC (Servlet)** and **Thymeleaf**. You need a Java 17 Maven project with these dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-thymeleaf</artifactId>
    </dependency>
</dependencies>
```

This is the `<dependencies>` section for a `pom.xml` **that already has a Spring Boot parent or dependency management**, not a complete standalone POM. Create a project with Spring Initializr using Java 17 and selecting `Spring Web` and `Thymeleaf`; the file structure should look like:

```text
src/main/
  java/com/example/mvcdemo/
    MvcDemoApplication.java
    WelcomeController.java
  resources/
    application.properties
    templates/
      pages/
        welcome.html
```

### 5.1. Main Class

File `src/main/java/com/example/mvcdemo/MvcDemoApplication.java`:

```java
package com.example.mvcdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcDemoApplication.class, args);
    }
}
```

### 5.2. Controller Returning a View Name and Model Data

File `src/main/java/com/example/mvcdemo/WelcomeController.java`:

```java
package com.example.mvcdemo;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class WelcomeController {

    @GetMapping("/welcome")
    public String welcome(
            @RequestParam(defaultValue = "Guest") String name,
            Model model) {
        model.addAttribute("name", name);
        return "pages/welcome";
    }
}
```

Breakdown:

- `@Controller` participates in Spring MVC view rendering.
- `@GetMapping("/welcome")` binds the HTTP path to the handler method.
- `@RequestParam(defaultValue = "Guest")` reads the `name` parameter; when omitted, uses the default value.
- `model.addAttribute("name", name)` exposes the value to the template via `${name}`.
- `return "pages/welcome"` is the logical view name; Spring MVC passes this name to the resolver chain.

### 5.3. Thymeleaf Template

File `src/main/resources/templates/pages/welcome.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Welcome Page</title>
</head>
<body>
    <h1>Hello, <span th:text="${name}">Guest</span>!</h1>
    <a th:href="@{/welcome(name='Minh')}">Greet Minh</a>
</body>
</html>
```

Thymeleaf evaluates `th:text="${name}"` using model data. Text content is HTML-escaped by default, helping prevent arbitrary HTML injection from user parameters. `th:href` constructs a context-aware URL.

Note that `welcome.html` lives under **`templates/pages`**, not `static/pages`. The `static` folder is meant for CSS, JavaScript, images, and static assets served directly.

### 5.4. Configuration (Optional with Defaults)

File `src/main/resources/application.properties`:

```properties
server.port=8080
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.mode=HTML

# Only disable template caching during development
spring.thymeleaf.cache=false
```

The `prefix` and `suffix` properties already default to the values shown above. Writing them out makes the path from `"pages/welcome"` to `templates/pages/welcome.html` clear.

In production, keep template caching enabled to avoid repeated template resolution and parsing overhead. Do not let development settings degrade production performance without reason.

### 5.5. Running the Example

From the root directory of a Maven project with `mvnw`:

```bash
./mvnw spring-boot:run
```

In another terminal:

```bash
curl -s "http://localhost:8080/welcome?name=Lan"
```

The HTML response will contain a snippet equivalent to:

```html
<h1>Hello, <span>Lan</span>!</h1>
```

This is **a rendered HTML fragment**, not the full byte-for-byte response: the HTML document also includes `html`, `head`, `body`, and anchor tags. Visiting `/welcome` without query parameters renders the default name `Guest`.

After running, changing the view name to `"pages/other"` without creating `templates/pages/other.html` causes Thymeleaf to fail to locate the template, typically resulting in a view resolution or rendering error. This confirms that the view name serves solely as a key for template resolution.

## 6. Differences Between @Controller, @RestController, and @ResponseBody

The two methods below share the same `String` return type, yet carry **different semantics**:

```java
@Controller
class HtmlController {
    @GetMapping("/page")
    String page() {
        return "pages/welcome";
    }
}
```

In a plain `@Controller`, Spring MVC interprets `"pages/welcome"` as a view name.

```java
@RestController
class ApiController {
    @GetMapping("/api/message")
    String message() {
        return "pages/welcome";
    }
}
```

In a `@RestController`, the `String` is written to the **HTTP response body** as text; Spring MVC does not ask `ViewResolver` to look up `pages/welcome.html`. `@RestController` is equivalent to applying `@Controller` plus `@ResponseBody` at the class level.

Similarly:

```java
@Controller
class PlainTextController {
    @GetMapping("/plain")
    @ResponseBody
    String plain() {
        return "Not using ViewResolver";
    }
}
```

Methods with `@ResponseBody` go through `HttpMessageConverter` to produce the body. APIs returning JSON via `ResponseEntity<...>` or `@ResponseBody` do not normally use `ViewResolver`.

This is one of the most common mistakes when developers new to Spring MVC see a web page showing just the literal text `welcome`: the controller was annotated with `@RestController`.

## 7. Using ModelAndView to Bundle View and Model Together

Instead of adding to `Model` and returning a `String`, a controller can return `ModelAndView`:

```java
package com.example.mvcdemo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.servlet.ModelAndView;

@Controller
public class ProfileController {

    @GetMapping("/profile")
    public ModelAndView profile() {
        ModelAndView mv = new ModelAndView("pages/profile");
        mv.addObject("displayName", "Mai");
        mv.addObject("role", "Member");
        return mv;
    }
}
```

Spring MVC receives a `ModelAndView` containing view name `pages/profile` and two model attributes. To make the endpoint work, add `src/main/resources/templates/pages/profile.html`, where `${displayName}` and `${role}` can be referenced.

`ModelAndView` can also be constructed from a concrete `View` object instead of a logical name. When `ModelAndView` already holds a `View` instance, view-name resolution is skipped.

For small controllers, `Model` + `String` is usually easier to read. `ModelAndView` is handy when you want to return the view and model explicitly in one return object.

## 8. Common ViewResolvers

| Resolver | How it resolves view names | Usage example |
|---|---|---|
| `ThymeleafViewResolver` | Uses Thymeleaf configuration to pick an HTML template and build a `View` | `"pages/welcome"` → `templates/pages/welcome.html` |
| `InternalResourceViewResolver` | Applies prefix/suffix to form an internal resource; supports JSP, Servlet dispatch | `"orders/list"` → `/WEB-INF/jsp/orders/list.jsp` |
| `BeanNameViewResolver` | Looks up a `View` bean in `ApplicationContext` matching the view name | A `View` bean named `reportView` |
| `FreeMarkerViewResolver` | Maps view names to FreeMarker templates | `.ftlh` pages |
| `ContentNegotiatingViewResolver` | Coordinates other resolvers/views to select a representation matching `Accept` and media type | HTML, XML, PDF when matching views are configured |

Spring Boot auto-configures several resolvers based on dependencies and web environment. If you add the Thymeleaf starter to an MVC app, Spring Boot normally registers `ThymeleafViewResolver` and its template engine automatically. That is why the example in section 5 required no manual resolver beans.

### 8.1. InternalResourceViewResolver and JSP

For JSP, the mapping idea is:

```properties
spring.mvc.view.prefix=/WEB-INF/jsp/
spring.mvc.view.suffix=.jsp
```

If a controller returns `"orders/list"`, the expected resource is `/WEB-INF/jsp/orders/list.jsp`. This **only works when the application is deployed with a JSP engine and the right resource layout**; adding prefix/suffix properties does not bring a JSP compiler into the project.

JSP has limitations with embedded servlet containers and executable JAR packaging; Spring Boot recommends considering template engines like Thymeleaf or FreeMarker whenever possible. For traditional JSP apps, verify the Jasper dependency, packaging type, and `src/main/webapp/WEB-INF/jsp/` layout for your server.

`spring.mvc.view.prefix` and `spring.mvc.view.suffix` belong to the internal resource resolver; they are **not** how you change Thymeleaf's template paths. Thymeleaf uses `spring.thymeleaf.prefix` and `spring.thymeleaf.suffix`.

### 8.2. BeanNameViewResolver

`BeanNameViewResolver` treats bean names themselves as logical view names. For instance, a bean named `reportView` implementing `View` can be chosen when a controller returns `"reportView"`. This is useful if `View` is a custom component or generates output in a specialized format.

A `@Component("reportView")` alone is not enough if that component does not implement `View`; the resolver looks for **`View` beans**, not arbitrary beans.

### 8.3. ContentNegotiatingViewResolver

This resolver acts as a coordinator rather than rendering templates itself. It compares the content types the client accepts (usually from the `Accept` header) against compatible `View`s provided by other resolvers. When multiple view technologies coexist, configure media types, resolver ordering, and default views carefully.

Do not confuse `ContentNegotiatingViewResolver` with default JSON serialization via `@ResponseBody`: those are two separate pipelines.

## 9. Chaining Multiple Resolvers and Precedence Order

Spring MVC can register **multiple** `ViewResolver`s. They are ordered by `Ordered`, `@Order`, or corresponding order settings. Resolvers with **smaller order numbers** are tried earlier.

Overview:

```text
View name = "report"
        |
        v
First Resolver
  -> View? yes: use View
  -> null? pass to next resolver
        |
        v
Second Resolver
  -> View? yes: use View
  -> null? continue
        |
        v
No matching view -> resolution/rendering error
```

Important:

- A resolver can return `null` when it cannot resolve a name; `DispatcherServlet` moves on to the next resolver.
- A resolver may **construct a `View` object from prefix/suffix rules even if the underlying resource does not exist**; the error may only surface during rendering. Therefore, do not assume every resolver checks file existence before returning a view.
- `InternalResourceViewResolver` for JSP should usually sit **last in the chain**: prior to dispatching via `RequestDispatcher`, it cannot reliably know whether a JSP exists, so it can shadow views meant for other resolvers.
- Avoid registering multiple resolvers that can claim the same view names without explicit ordering. When mixing Thymeleaf and JSP, carefully manage view names, prefixes/suffixes, order, and resource existence checks.

When Spring Boot auto-configures resolvers, avoid creating beans with conflicting names or types without understanding the impact on auto-configuration. For simple setups, starters and properties suffice.

## 10. redirect: and forward: Are Special View Names

### 10.1. Redirect Changes the URL on the Client Side

`redirect:` is a special prefix recognized by supporting resolvers to issue an HTTP redirect:

```java
@Controller
class NavigationController {

    @GetMapping("/old-page")
    public String oldPage() {
        return "redirect:/welcome";
    }
}
```

When a browser requests `/old-page`, the server returns a redirect HTTP response (typically 3xx, such as 302) with an appropriate `Location` header. The browser makes a **new request** to `/welcome`; the URL in the address bar changes. This does not render a template at `templates/redirect:/welcome.html`.

Use redirect after `POST` to prevent duplicate form submissions when the user reloads the page (the **Post/Redirect/Get** pattern). Example:

```java
@PostMapping("/contacts")
public String saveContact(
        @RequestParam String name,
        RedirectAttributes redirectAttributes) {
    // Saving logic via service is implemented in the application.
    redirectAttributes.addFlashAttribute("notice", "Saved " + name);
    return "redirect:/contacts";
}
```

This is an **illustrative snippet inside a `@Controller`** and requires `PostMapping`, `RequestParam`, and `RedirectAttributes` imports from Spring. `addFlashAttribute` passes data across a redirect using flash attributes for the next request; avoid stuffing sensitive data into query strings.

Never redirect to an arbitrary URL taken directly from client input without validation, as that creates an **open redirect** vulnerability.

### 10.2. Forward Keeps the Request on the Server Side

The `forward:` prefix triggers server-side forwarding via `RequestDispatcher.forward()`, for example:

```java
@GetMapping("/legacy")
public String legacy() {
    return "forward:/welcome";
}
```

Here Spring MVC forwards internally to `/welcome`. The browser does not issue a separate redirect request, and the displayed URL does not necessarily change.

| Aspect | `redirect:/welcome` | `forward:/welcome` |
|---|---|---|
| Nature | Redirect response | Server-side dispatch |
| HTTP request | Client typically issues a new request | Continues within the same request/dispatch cycle |
| Browser URL | Usually updates to target URL | Usually keeps original URL |
| Passed data | Query params, flash attributes, or other mechanisms | Request attributes and request state within forward scope |
| Purpose | Navigation, Post/Redirect/Get | Internal transfer to another handler/resource |

Do not confuse `forward:` with normal template name resolution. Not every view technology needs or should use `forward:`.

## 11. View Controllers: Rendering Templates Without Controller Logic

If a template-backed static page merely maps a URL to a template, configure it directly via `WebMvcConfigurer`:

```java
package com.example.mvcdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ViewRouteConfig implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addViewController("/help")
                .setViewName("pages/help");
    }
}
```

Visiting `/help` causes Spring MVC to select view name `pages/help` and resolve it to the matching template, such as `templates/pages/help.html`.

When using `WebMvcConfigurer` to extend Spring Boot's MVC setup, you normally **do not need `@EnableWebMvc`**. Adding `@EnableWebMvc` alters Boot's auto-configuration, creating extra manual configuration work.

## 12. Model Data, Escaping, Layouts, and Static Resources

In server-side rendering, the model can be populated via:

- `Model.addAttribute(...)` or `ModelMap`.
- `@ModelAttribute` return values or parameters.
- `ModelAndView.addObject(...)`.
- Flash attributes after a redirect.

Templates read the model to render lists, messages, forms, or tables. Thymeleaf example:

```html
<p th:text="${message}">Default content</p>
<ul>
    <li th:each="product : ${products}"
        th:text="${product.name}">Product</li>
</ul>
```

This is a fragment sample; the controller must put `message` and `products` into the model. Thymeleaf can render shared layouts or fragments (header, footer, navigation); that is a template-engine feature, **not `ViewResolver`'s HTTP routing algorithm**.

Safety when rendering UI:

- `th:text` HTML-escapes data contextually; prefer it for user-supplied input.
- `th:utext` renders unescaped HTML; sanitize/control the content strictly if you must use it.
- Never put sensitive data, session tokens, or secrets into a model rendered to HTML.
- For forms, verify CSRF protection and validation via Spring Security/Bean Validation if your app uses them.
- CSS/JS/images are served separately, e.g., `src/main/resources/static/css/site.css`; view resolution is not the general mechanism for serving static files.

## 13. Testing Controllers and View Names

Besides manual testing, `MockMvc` can verify view names and model attributes. Example test for Spring Boot 3.x, assuming `spring-boot-starter-test`:

File `src/test/java/com/example/mvcdemo/WelcomeControllerTest.java`:

```java
package com.example.mvcdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class WelcomeControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void rendersNamedViewWithModel() throws Exception {
        mockMvc.perform(get("/welcome").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(view().name("pages/welcome"))
                .andExpect(model().attribute("name", "Lan"));
    }
}
```

Run command on a Maven project with Maven Wrapper:

```bash
./mvnw test
```

The test confirms the controller picks the right view name and model; testing actual HTML rendering requires the template and matching config to be present. To ensure the HTML reaching the browser is accurate, supplement with `MockMvc` assertions on the HTML response or HTTP integration tests.

Testing in a browser is also helpful: open Developer Tools, Network tab, and check status, `Content-Type`, response body, and redirect chains. When a template is not found, read the original stacktrace/exception instead of looking only at a generic error page.

## 14. Common Errors and How to Fix Them

| Symptom | Common cause | How to resolve |
|---|---|---|
| Browser renders only the literal text `pages/welcome` | Controller uses `@RestController` or `@ResponseBody` | Use `@Controller` and return the view name to render HTML |
| Template not found | Wrong view name, wrong `templates/` path, wrong prefix/suffix, or missing template engine dependency | Check actual resource in classpath, paths, and Thymeleaf config |
| View renders, but model data is missing | Forgot `addAttribute` or mismatched key name with template | Match `model.addAttribute("name", ...)` with `${name}` |
| Added JSP, but it does not run | Missing JSP engine, incompatible packaging, or wrong `/WEB-INF/` layout | Check JSP limits with embedded containers and Maven/Gradle setup |
| Thymeleaf ignores `spring.mvc.view.prefix` | That property belongs to internal resource resolver | Use `spring.thymeleaf.prefix` and `spring.thymeleaf.suffix` |
| Multiple resolvers pick the wrong view | `ViewResolver` ordering or a resolver matching too broadly | Check order, prioritize specific resolvers, keep `InternalResourceViewResolver` last |
| Returned `"redirect:/..."`, but no redirect happened | `@ResponseBody` present or other return-value handling | Verify MVC view-name flow and 3xx response |
| Browser errors after POST submit | Wrong redirect path or target endpoint lacks handler | Check `Location` header and target mapping |
| Circular view path error | Default view name or forward loops back to the same handler | Return an explicit view name and check prefix/suffix and target path |
| Old template still shown after edits | Template cache enabled or app resources not reloaded | Disable cache in dev; rebuild/redeploy when needed |
| All MVC pages changed after adding `@EnableWebMvc` | Altered auto-configured MVC setup | Remove `@EnableWebMvc` if you only want `WebMvcConfigurer` |

### Debugging Step by Step

1. Identify the request URL and which method/controller was actually selected.
2. Check whether `@Controller` or `@RestController`/`@ResponseBody` is present.
3. Note the return value: `String` view name, `ModelAndView`, `View`, or direct response body.
4. Inspect the model keys passed to the template.
5. Check the list of `ViewResolver`s and their resolution order when using multiple view technologies.
6. Confirm prefix, suffix, and template existence on the runtime classpath.
7. Inspect template engine exceptions, status code, and response body.
8. For redirects/forwards, verify the target path, context path, and target mapping.

## 15. Choosing ViewResolver vs. @ResponseBody in Real Designs

Use **ViewResolver** when the application serves server-rendered dynamic HTML, such as admin consoles, forms, reports, internal dashboards, or pages reusing shared fragments.

Use **`@RestController` / `@ResponseBody`** when endpoints return JSON, text, or data consumed by a separate frontend, such as REST APIs for React, Vue, or mobile apps.

Both approaches can coexist inside one Spring MVC application. Distinguish them by each endpoint's response requirements, not by whether the URL contains `api`.

If choosing Spring WebFlux instead of Spring MVC, use the reactive stack's namespaces and view resolution mechanisms; Servlet APIs like `org.springframework.web.servlet.ViewResolver` cannot be used directly to configure WebFlux.

## 16. Review Checklist

1. A `@Controller` returning `String` normally specifies a logical view name, not an HTML body.
2. `DispatcherServlet` coordinates controllers, models, resolvers, and rendering.
3. `ViewResolver` maps view name → `View`; `View` renders the model into an HTTP response.
4. With Spring Boot Thymeleaf, `"pages/welcome"` normally points to `classpath:/templates/pages/welcome.html`.
5. `spring.thymeleaf.prefix/suffix` differs from `spring.mvc.view.prefix/suffix` for internal-resource/JSP resolvers.
6. Multiple resolvers can coexist; control ordering, especially placing `InternalResourceViewResolver` last.
7. `@RestController` / `@ResponseBody` uses `HttpMessageConverter`, bypassing standard view-name rendering.
8. `ModelAndView` bundles model data with a view name or concrete `View`.
9. `redirect:` produces an HTTP redirect; `forward:` transfers processing internally on the server.
10. Tests should verify view name, model attributes, and actual rendered HTML in responses.

## 17. References

- Spring Framework — View Resolution: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/viewresolver.html
- Spring Framework — Controller Method Return Values: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework — `@ResponseBody`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html
- Spring Framework — MVC Configuration: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config.html
- Spring Boot — Customize ViewResolvers: https://docs.spring.io/spring-boot/how-to/spring-mvc.html
- Spring Boot 3.5 — Servlet Web Applications and Template Engines: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Thymeleaf — Using Thymeleaf: https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html