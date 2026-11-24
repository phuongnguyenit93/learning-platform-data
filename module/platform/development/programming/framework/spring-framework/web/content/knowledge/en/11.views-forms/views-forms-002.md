# ViewResolver, Resolution Order, and Template Engine Integration in Spring MVC

## 1. Problem and Objectives

In Spring MVC, a controller may return the string `"books/detail"`, yet the browser ultimately receives HTML generated from the file `templates/books/detail.html`. What locates the corresponding file? Why does a view name sometimes go through Thymeleaf and other times get routed to JSP? Understanding **ViewResolver**, **View**, and resolution order answers these questions.

This lesson helps you:

- Distinguish request URLs, logical view names, `Model`, `ViewResolver`, `View`, and template engines.
- Trace the path from a `@Controller` return value to the rendered HTML.
- Understand how multiple `ViewResolver` instances are consulted by `order` and why `InternalResourceViewResolver` for JSP must be placed last.
- Distinguish `BeanNameViewResolver`, `InternalResourceViewResolver`, `ThymeleafViewResolver`, `FreeMarkerViewResolver`, and `ContentNegotiatingViewResolver`.
- Configure Thymeleaf in Spring Boot, use prefix/suffix and view names, and distinguish MVC ViewResolver order from the engine's own template resolver order.
- Understand `redirect:`, `forward:`, `ModelAndView`, form binding, and cases where `@RestController` bypasses view resolution.
- Run a Spring Boot 3 + Java 17 application with HTML templates, form validation, redirects, and tests using `MockMvc`.

**Scope:** Spring MVC on the Servlet stack, suitable for Spring Framework 6.x, Spring Boot 3.x, and Java 17+. WebFlux classes use a different reactive mechanism and are not the focus of this lesson.

## 2. Logical View Names Differ from HTML, URLs, and API Responses

An illustrative controller:

```java
@Controller
class BookPageController {

    @GetMapping("/books/7")
    String detail(Model model) {
        model.addAttribute("title", "Learning Spring MVC");
        return "books/detail";
    }
}
```

*This illustrative snippet belongs inside a controller class with appropriate imports; a complete project example is in Section 7.*

The roles:

| Component | Example | Responsibility |
| --- | --- | --- |
| HTTP URL | `GET /books/7` | Identifies the request the client wants to send |
| Handler mapping | `@GetMapping("/books/7")` | Selects the controller method |
| Model | `{"title":"Learning Spring MVC"}` | Rendering data for the current request |
| Logical view name | `"books/detail"` | Abstract name returned by the controller |
| ViewResolver | `ThymeleafViewResolver` | Finds the View object matching the name and locale |
| View | Thymeleaf View | Renders the model using the appropriate template |
| Template | `classpath:/templates/books/detail.html` | Source markup/expressions processed by the engine |
| HTTP response | `text/html` | HTML content returned to the browser |

Data typically flows along this chain:

```text
HTTP GET /books/7
  → DispatcherServlet
  → HandlerMapping selects BookPageController.detail
  → HandlerAdapter invokes controller
       ├── Model has attribute title
       └── view name: "books/detail"
  → ViewResolver(s): resolveViewName("books/detail", locale)
       ├── resolver 1 declines → null → tries resolver 2
       └── resolver 2 accepts → returns Thymeleaf View
  → View.render(model, request, response)
       ├── reads/parses template books/detail.html
       ├── applies model + template expressions
       └── writes HTML to HttpServletResponse
```

**ViewResolver resolves a name to a View; the View actually renders.** A controller does not need to know the absolute location of the template if logical names and conventions are configured properly. `ViewResolver` does not replace `HandlerMapping`: the former runs after the controller has been chosen, whereas the latter determines the HTTP endpoint.

### 2.1. Return Types That Can Skip View Name Resolution

In `@Controller`, a `String` return value is normally a view name. In `@RestController` or a method with `@ResponseBody`, `String` is instead the direct body. For example:

```java
@Controller
class PageController {
    @GetMapping("/home")
    String home() {
        return "home"; // logical view name
    }

    @ResponseBody
    @GetMapping("/plain")
    String plain() {
        return "Hello"; // response body is the string Hello
    }
}

@RestController
class ApiController {
    @GetMapping("/api/hello")
    Map<String, String> hello() {
        return Map.of("message", "Hello"); // Jackson serializes JSON
    }
}
```

*This is a standalone illustration; you need to import `Map` and the annotations when using it in a project.* `@RestController` combines `@Controller` with `@ResponseBody` semantics. `ResponseEntity<?>` also typically writes directly to the HTTP response via a message converter. Do not expect Thymeleaf to render `home.html` if a `@RestController` returns `"home"`: the client normally receives the literal text `home`.

### 2.2. ModelAndView and View Objects

```java
@GetMapping("/dashboard")
ModelAndView dashboard() {
    return new ModelAndView(
        "dashboard",
        "heading",
        "Overview Page"
    );
}
```

`ModelAndView` holds both the view name and the model; the result is equivalent to taking `Model` and returning `"dashboard"`. You can also supply a `View` instance directly, in which case a resolver does not necessarily need to look it up by name. When a method returns no view name, MVC can sometimes infer one from the request via `RequestToViewNameTranslator`, though returning an explicit name makes APIs and controllers easier to maintain.

## 3. Common ViewResolvers

| Resolver | Mechanism | Practical Use Case |
| --- | --- | --- |
| `BeanNameViewResolver` | Looks up a Spring bean matching the view name and having type `View` | CSV, Excel, PDF, or custom View beans |
| `InternalResourceViewResolver` | Prepends/appends prefix/suffix and creates `InternalResourceView` to forward/include via Servlet | JSP/JSTL; **always place last in the chain** |
| `UrlBasedViewResolver` | Base class mapping view names to URLs by convention | Foundation for URL-based resolvers |
| `FreeMarkerViewResolver` | Creates `FreeMarkerView` for the corresponding template | Server-side FreeMarker |
| `ThymeleafViewResolver` | Creates Thymeleaf View; engine processes template file | Thymeleaf in Spring MVC/Boot |
| `ContentNegotiatingViewResolver` | Picks an appropriate View supplied by other resolvers based on media type/Accept | One resource with multiple representations |
| `ViewResolverComposite` | Aggregates configured resolvers | Result of configuration via MVC registry |

A `ViewResolver` follows the contract of returning `null` if it cannot find or does not handle a view name. With multiple resolvers, this allows the next one to try. However, not every resolver **knows** whether a template exists before returning a View. An overly broad resolver can "claim" the name and then fail during rendering instead of giving another resolver a chance.

`AbstractCachingViewResolver` provides caching for resolved Views. **Caching a View differs from caching HTML**: the model can still vary per request. Template engines also have their own caches for parsed templates, and HTTP/CDN caches are yet another layer.

### 3.1. JSP: InternalResourceViewResolver

Example:

```java
@Bean
InternalResourceViewResolver jspViewResolver() {
    InternalResourceViewResolver resolver = new InternalResourceViewResolver();
    resolver.setPrefix("/WEB-INF/jsp/");
    resolver.setSuffix(".jsp");
    resolver.setOrder(Ordered.LOWEST_PRECEDENCE);
    return resolver;
}
```

*Illustrative configuration snippet in a separate JSP application; requires importing `@Bean`, `Ordered`, and `InternalResourceViewResolver`. Do not add this simultaneously to the Thymeleaf demo in Section 7.*

The name `"orders/detail"` is mapped to:

```text
/WEB-INF/jsp/orders/detail.jsp
```

JSPs are typically placed under `WEB-INF` so browsers cannot open template files directly. When using JSTL, you need to configure `JstlView` and the appropriate JSTL library. A standard Spring Boot executable JAR is usually not a convenient way to deploy JSPs; if you need JSP, check WAR/container packaging and Boot's JSP limitations.

### 3.2. BeanNameViewResolver and Custom Views

If a controller returns `"monthlyCsv"` and the container has a bean named `monthlyCsv` of type `View`, then `BeanNameViewResolver` can return that bean. This maps directly to a specialized View rather than a template file. An ordinary service bean with the same name **does not** become a View.

### 3.3. Thymeleaf and FreeMarker

With Spring Boot, adding `spring-boot-starter-thymeleaf` activates the necessary Thymeleaf configuration when auto-configuration conditions match. FreeMarker has its own starter `spring-boot-starter-freemarker`. When using a single engine, it is usually best to let Boot apply defaults and then adjust prefix/suffix/cache via properties.

If multiple template engines are installed together, check **which resolver actually owns each view name**. You can restrict view name patterns and adjust `order` to prevent one engine from trying to render another engine's templates.

## 4. ViewResolver Order: Lower Numbers Run First

Spring MVC consults multiple resolvers according to `Ordered` and actual configuration:

- `order = -10` takes precedence over `0`.
- `order = 0` takes precedence over `10`.
- Resolvers with lower priority (higher order values) are checked later.
- `Ordered.LOWEST_PRECEDENCE` is a very low priority, suitable for a fallback resolver that accepts many names.
- When a resolver returns `null`, the chain can continue; when it returns a View, that result is used in the chosen pipeline.

Suppose we have an **explicit configuration**:

| Resolver | Order | Accepted View Names |
| --- | ---: | --- |
| `BeanNameViewResolver` | 0 | Only names with a matching View bean |
| `ThymeleafViewResolver` | 10 | `pages/*` |
| `InternalResourceViewResolver` | 1000 | JSP fallback |

When the controller returns `"pages/home"`:

```text
BeanNameViewResolver: no View bean → null
ThymeleafViewResolver: accepts "pages/home" → Thymeleaf View
InternalResourceViewResolver: does not need to run
```

When returning `"legacy/report"`:

```text
BeanNameViewResolver: no bean → null
ThymeleafViewResolver: not in pages/* → null
InternalResourceViewResolver: /WEB-INF/jsp/legacy/report.jsp
```

The **order numbers in the table are examples only**; they are not fixed defaults across all Spring Boot versions. When debugging, inspect the actual beans in `ApplicationContext` and your environment configuration.

### 4.1. Why Must the JSP Resolver Be Last in the Chain?

`InternalResourceViewResolver` cannot reliably confirm a JSP file exists from the view name alone; it typically has to perform `RequestDispatcher.forward()` and let the Servlet/JSP container handle it. Consequently, this resolver can create an `InternalResourceView` for almost any name. If it is placed **before Thymeleaf**, a name like `"pages/home"` can be sent to `/WEB-INF/jsp/pages/home.jsp` even when you expected Thymeleaf, causing the page to fail to render properly.

**Rule:** place `InternalResourceViewResolver` last in the entire resolver order whenever multiple ViewResolvers coexist. This rule is emphasized in the official Spring MVC documentation, not merely a configuration habit.

### 4.2. Configuration with WebMvcConfigurer

A Spring MVC application **intentionally using JSP** can configure resolvers as follows:

```java
@Configuration
class LegacyViewConfig implements WebMvcConfigurer {
    @Override
    public void configureViewResolvers(ViewResolverRegistry registry) {
        registry.beanName();
        registry.jsp("/WEB-INF/jsp/", ".jsp");
    }
}
```

*This is a standalone illustration; requires importing `Configuration`, `WebMvcConfigurer`, `ViewResolverRegistry`, and an appropriate JSP environment. Do not insert into the sample Boot/Thymeleaf project.*

`ViewResolverRegistry` also supports registering custom resolvers and enabling content negotiation when needed. In Spring Boot, **do not enable `@EnableWebMvc` just to tweak a template property**: that annotation hands many parts of MVC configuration back to you and can disable existing auto-configuration. Use properties and `WebMvcConfigurer` appropriately before choosing to replace all MVC defaults.

### 4.3. MVC Resolver Order vs. Template Resolver Order Are Two Different Things

`ThymeleafViewResolver#setOrder(...)` affects the **Spring MVC ViewResolver** order. However, Thymeleaf also has internal **ITemplateResolver** instances to locate template sources, prefix/suffix, and caching. A property like `spring.thymeleaf.template-resolver-order` belongs to **Thymeleaf's template resolver chain**, not the ordering of Spring MVC resolvers.

```text
Spring MVC ViewResolver chain
   └── ThymeleafViewResolver
        └── ThymeleafView
             └── Thymeleaf TemplateEngine
                  └── TemplateResolver chain
                       └── classpath:/templates/pages/home.html
```

If `"pages/home"` falls into the JSP resolver, fix **MVC ViewResolver order/viewNames**; if Thymeleaf was chosen but looks up the wrong file, check **template prefix/suffix/resource resolution**.

## 5. ContentNegotiatingViewResolver and HTTP Accept

In some applications, the same resource may be represented as HTML, PDF, or JSON:

```http
GET /reports/42 HTTP/1.1
Accept: text/html
```

or:

```http
GET /reports/42 HTTP/1.1
Accept: application/pdf
```

`ContentNegotiatingViewResolver` does not render HTML/PDF itself. It asks other resolvers for candidate `View`s and picks the View whose media type is compatible with what the client accepts. Additional `defaultViews` such as a JSON or PDF View can be supplied. **Without a PDF View, `Accept: application/pdf` will not magically generate a PDF.**

The common path for REST JSON is different:

```text
@RestController returns Java object
 → @ResponseBody return-value handler
 → MappingJackson2HttpMessageConverter
 → application/json response body
```

In this case, neither `ContentNegotiatingViewResolver` nor `MappingJackson2JsonView` is required. Distinguish **content negotiation when selecting a View** from **content negotiation when selecting an HTTP message converter**, even though both involve `Accept`.

Spring Boot may auto-configure `ContentNegotiatingViewResolver` depending on the `View` beans present and active conditions. Do not assume it is always present in every application; inspect the metadata/bean list of the specific context.

## 6. The `redirect:` and `forward:` Prefixes

When a controller returns a view name with a special prefix:

```java
@PostMapping("/save")
String save() {
    return "redirect:/documents/7";
}

@GetMapping("/legacy-entry")
String legacyEntry() {
    return "forward:/internal/page";
}
```

*Illustrative snippet inside a `@Controller`.*

- `redirect:/documents/7` produces an **HTTP redirect** to the new URL; the browser sends a new request. This is the tool behind Post/Redirect/Get (PRG).
- `forward:/internal/page` requests an **internal Servlet forward** within the same request, without triggering an HTTP redirect to the browser.
- `redirect:` is supported by URL-based resolvers as a special directive. It is not an HTML filename.
- `forward:` is useful when transferring to a URL handled by a Servlet; you do not need it to point to a JSP if logical view names are already configured through a JSP resolver.

If you need to display a notice on the next GET after a valid POST, use `RedirectAttributes.addFlashAttribute(...)`. Flash data is held temporarily across the redirect without necessarily appearing in the URL. If a form **has validation errors**, you typically return the same view in the current request to preserve input and `BindingResult` rather than redirecting unconditionally.

Avoid concatenating untrusted URL values directly into `"redirect:" + userInput` as it can introduce an **open redirect**; allowlist permitted routes/hosts.

## 7. Complete Spring Boot 3 + Thymeleaf + Java 17 Demo

The example application covers all paths:

- `GET /` → controller returns `"home"`, Thymeleaf renders `home.html`.
- `GET /greetings/Ada` → `"greetings/detail"`, HTML using `Model`.
- `GET /model-view` → `ModelAndView` returns the same `home` template.
- `GET /api/greetings/Ada` → `@RestController` returns JSON, **bypassing** view resolution.
- `GET /signup` and `POST /signup` → Thymeleaf form, `@Valid`, and `BindingResult`; a valid form redirects to the completion page.

Uses Java 17+, Maven, and Spring Boot **3.3.13**. No database or Servlet JSP engine is required.

### 7.1. Structure

```text
view-resolution-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/ViewResolutionApplication.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/
    │           ├── home.html
    │           ├── greetings/detail.html
    │           ├── signup.html
    │           └── signup-done.html
    └── test/java/example/ViewResolutionTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>view-resolution-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

The Thymeleaf starter lets Boot configure the template engine and resolver. You do not need to manually create a `ThymeleafViewResolver` bean to use the default template location.

### 7.3. application.properties

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.mode=HTML
spring.thymeleaf.encoding=UTF-8
# Disable cache for learning/development environment.
spring.thymeleaf.cache=false
```

The prefix/suffix values above match Thymeleaf's defaults in Boot 3.x. When returning `"greetings/detail"`, the engine looks for the template `classpath:/templates/greetings/detail.html`. Do not use `spring.mvc.view.prefix` to adjust Thymeleaf; that property serves Servlet resource/JSP resolution in appropriate configurations.

`spring.thymeleaf.view-names` and `spring.thymeleaf.excluded-view-names` help restrict Thymeleaf's set of logical names when using multiple engines. In production, template caching should normally be enabled to improve performance.

### 7.4. ViewResolutionApplication.java

All classes/records are in the same file `src/main/java/example/ViewResolutionApplication.java`; only the main class is declared `public`.

```java
package example;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.ModelAndView;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@SpringBootApplication
public class ViewResolutionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ViewResolutionApplication.class, args);
    }
}

class SignupForm {
    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    public SignupForm() {}

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}

@Controller
class PageController {

    @GetMapping("/")
    String home(Model model) {
        model.addAttribute("heading", "MVC Home");
        return "home";
    }

    @GetMapping("/model-view")
    ModelAndView modelView() {
        return new ModelAndView("home", "heading", "ModelAndView Page");
    }

    @GetMapping("/greetings/{name}")
    String greeting(@PathVariable String name, Model model) {
        model.addAttribute("message", "Hello, " + name + "!");
        return "greetings/detail";
    }

    @GetMapping("/signup")
    String showSignup(Model model) {
        model.addAttribute("signupForm", new SignupForm());
        return "signup";
    }

    @PostMapping("/signup")
    String submit(@Valid @ModelAttribute("signupForm") SignupForm form,
                  BindingResult errors,
                  RedirectAttributes redirectAttributes) {

        if (errors.hasErrors()) {
            return "signup"; // re-render form with BindingResult
        }

        redirectAttributes.addFlashAttribute(
                "notice", "Registered: " + form.getName());

        return "redirect:/signup/done";
    }

    @GetMapping("/signup/done")
    String done() {
        return "signup-done";
    }
}

@RestController
class GreetingApiController {
    @GetMapping("/api/greetings/{name}")
    Map<String, String> greeting(@PathVariable String name) {
        return Map.of("message", "Hello, " + name + "!");
    }
}
```

Notice that `PageController` and `GreetingApiController` have different return paths: a String in `@Controller` is a logical view name, whereas a Map in `@RestController` is written directly as JSON. `BindingResult` sits immediately after the form DTO so the controller can re-render the same page when validation fails.

### 7.5. templates/home.html

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Home</title>
</head>
<body>
  <h1 th:text="${heading}">Default Heading</h1>
  <nav>
    <a th:href="@{/greetings/Ada}">Greeting</a>
    <a th:href="@{/signup}">Sign Up</a>
  </nav>
</body>
</html>
```

Thymeleaf uses `th:text` to insert the `heading` model attribute into HTML. The `${heading}` syntax is a valid Thymeleaf expression after replacing the `$` symbol with a dollar sign `$`; the file created in this lesson uses the proper `$` sign.

### 7.6. templates/greetings/detail.html

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Greeting</title>
</head>
<body>
  <h1 th:text="${message}">Default Greeting</h1>
</body>
</html>
```

`th:text` escapes HTML characters from the model by default, helping prevent user names containing markup from being rendered as HTML. For untrusted data, avoid `th:utext` unless sanitized under a strict safety contract.

### 7.7. templates/signup.html

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Sign Up</title>
</head>
<body>
  <h1>Sign Up</h1>
  <form th:action="@{/signup}" th:object="${signupForm}" method="post">
    <label>Name
      <input type="text" th:field="*{name}">
    </label>
    <span th:if="${#fields.hasErrors('name')}"
          th:errors="*{name}">Name error</span>

    <label>Email
      <input type="email" th:field="*{email}">
    </label>
    <span th:if="${#fields.hasErrors('email')}"
          th:errors="*{email}">Email error</span>

    <button type="submit">Submit</button>
  </form>
</body>
</html>
```

`th:object` accesses the `signupForm` model attribute. `th:field` binds inputs to properties, while `#fields.hasErrors(...)` and `th:errors` read validation info from `BindingResult`. Applications with Spring Security need to account for CSRF tokens per their configuration; this sample uses only MVC/Validation.

### 7.8. templates/signup-done.html

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Completed</title>
</head>
<body>
  <h1>Completed</h1>
  <p th:text="${notice}">Notice</p>
  <a th:href="@{/signup}">Back</a>
</body>
</html>
```

The `notice` message is a flash attribute, temporarily preserved across the redirect. If `/signup/done` is accessed directly, this attribute may be absent; real applications should define appropriate display behavior.

### 7.9. Running the Application

Requires Java 17+ and Maven. Inside the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Open in a browser:

```text
http://localhost:8080/
http://localhost:8080/greetings/Ada
http://localhost:8080/signup
http://localhost:8080/api/greetings/Ada
```

Or use cURL:

```bash
curl -i http://localhost:8080/greetings/Ada
curl -i http://localhost:8080/api/greetings/Ada
curl -i -X POST http://localhost:8080/signup \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "name=Ada&email=ada@example.com"
```

Expected results:

- `GET /greetings/Ada` returns 200 with HTML containing `<h1>Hello, Ada!</h1>`, rendered from the template.
- `GET /api/greetings/Ada` returns 200 with JSON body `{"message":"Hello, Ada!"}`; no template is needed.
- A valid `POST /signup` returns a redirect (typically HTTP 302) to `/signup/done`; the subsequent GET request can use the flash attribute to display `Registered: Ada`.
- `POST /signup` with an empty `name=` re-renders the signup template; the controller chooses to return a view and by default may return HTTP 200 even though validation errors are shown on the page. This is not a REST API scenario that automatically returns 400.

Use `curl.exe` on Windows PowerShell if `curl` is aliased to something else; the `\` line continuation syntax above is for POSIX shells.

## 8. Testing MVC View Resolution with MockMvc

File `src/test/java/example/ViewResolutionTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class ViewResolutionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void homeRendersTemplateAndModel() throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(view().name("home"))
            .andExpect(content().string(
                    containsString("<h1>MVC Home</h1>")));
    }

    @Test
    void nestedLogicalViewResolvesCorrectTemplate() throws Exception {
        mvc.perform(get("/greetings/Ada"))
            .andExpect(status().isOk())
            .andExpect(view().name("greetings/detail"))
            .andExpect(content().string(
                    containsString("<h1>Hello, Ada!</h1>")));
    }

    @Test
    void modelAndViewAlsoWorks() throws Exception {
        mvc.perform(get("/model-view"))
            .andExpect(status().isOk())
            .andExpect(view().name("home"))
            .andExpect(content().string(
                    containsString("ModelAndView Page")));
    }

    @Test
    void restControllerWritesJsonWithoutView() throws Exception {
        mvc.perform(get("/api/greetings/Ada"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.message")
                    .value("Hello, Ada!"));
    }

    @Test
    void invalidFormReturnsSameTemplateWithBindingErrors()
            throws Exception {
        mvc.perform(post("/signup")
                    .param("name", "")
                    .param("email", "ada@example.com"))
            .andExpect(status().isOk())
            .andExpect(view().name("signup"))
            .andExpect(model().attributeHasFieldErrors(
                    "signupForm", "name"));
    }

    @Test
    void validFormRedirectsWithFlashAttribute() throws Exception {
        mvc.perform(post("/signup")
                    .param("name", "Ada")
                    .param("email", "ada@example.com"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/signup/done"))
            .andExpect(flash().attribute(
                    "notice", "Registered: Ada"));
    }
}
```

Run `mvn test`. Note the two different kinds of checks: `view().name(...)` verifies the logical name returned by the controller, whereas `content().string(...)` verifies the HTML rendered with model data. If you only assert the view name without checking content or resources, tests can pass "green" even when the actual template does not exist or the engine never runs.

`MockMvc` runs inside the test context without opening an HTTP port. With a `@WebMvcTest` slice, make sure required view engine configuration and resources are loaded; for example, using `@SpringBootTest` + `@AutoConfigureMockMvc` exercises full auto-configuration.

## 9. Multi-Engine Integration: Paths and Migration Strategy

If maintaining Thymeleaf alongside JSP or Thymeleaf alongside FreeMarker:

1. Partition view name groups by technology, such as `pages/*` for Thymeleaf and `legacy/*` for JSP.
2. Restrict view names on the appropriate engine; Thymeleaf supports `spring.thymeleaf.view-names` and `spring.thymeleaf.excluded-view-names`.
3. Inspect the actual ViewResolver `order` from `ApplicationContext`. More specific resolvers or those accepting only explicit names should run earlier; the JSP InternalResource resolver goes last.
4. Ensure names not belonging to an engine **are not claimed by that engine** only to fail with a template error during rendering.
5. Write tests for a Thymeleaf HTML page, a JSP page (if applicable), a custom View, and a JSON endpoint.
6. Check packaging: JSP requires supporting Servlet container/packaging; many Boot JAR setups should prefer classpath-friendly template engines.
7. Keep the model contract clear while migrating from an old engine to a new one so the frontend continues to display data and form errors accurately.

**You cannot simply change the suffix from `.jsp` to `.html` and consider the migration complete:** template syntax, tag libraries, security escaping, layouts, form binding, and caching behavior can all differ.

## 10. Troubleshooting View Resolution

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Browser shows literal text `home` instead of HTML | `@ResponseBody` method or `@RestController` class | Use `@Controller` and a view name instead of response body |
| `home.html` not found | Wrong prefix/suffix or file not on classpath | Check `templates/home.html` and `spring.thymeleaf.*` |
| Thymeleaf is bypassed and request goes to JSP | JSP resolver runs earlier or view names are not scoped | Check resolver order and view name restrictions |
| View name is right, response returns 500 | Template syntax error, missing resource, expression or render error | Check Thymeleaf cause/logs and template path |
| GET request returns 404 | No HTTP handler, or another logic/resource issue | Check HandlerMapping before ViewResolver |
| Redirect unexpectedly appends query parameters | Model attributes leaked into redirect unexpectedly | Use `RedirectAttributes` explicitly |
| Form submission fails and loses error messages | Redirected to a new request without carrying flash state | Return the form view in the same request |
| `th:text` renders empty | Model missing attribute or wrong attribute name | Check `model.addAttribute(...)` and expression |
| Edited template shows no change | Template engine cache or HTTP cache | Identify cache layer and disable cache only in dev |
| API returns JSON instead of HTML | `@RestController`/message converter is working as designed | Separate API controllers from HTML page controllers as intended |
| `Accept: application/pdf` does not produce PDF | No View supports PDF media type | Register an actual View; do not expect content negotiation to generate files |
| Changing `spring.mvc.view.prefix` has no effect on Thymeleaf | Adjusting JSP/Servlet resolver configuration instead | Use `spring.thymeleaf.prefix/suffix` |
| Enabling `@EnableWebMvc` changes many behaviors | Overrides most MVC auto-configuration | Customize via Boot properties/`WebMvcConfigurer` first |

### 10.1. Recommended Debugging Steps

1. Check **which controller was selected**, its return type, method/class annotations, and the actual logical view name.
2. If handling `@ResponseBody`/`ResponseEntity`, inspect **HTTP message converters** instead of adjusting template resolvers.
3. List ViewResolver beans, their `order`, view name patterns, and which beans can return `null`.
4. Verify templates sit at the expected path under prefix/suffix; maintain consistent letter casing.
5. Read the stack trace to distinguish **no handler found**, **resolver failed to pick a View**, and **View rendering error**.
6. Use `MockMvc` to assert both `view().name(...)` and the HTML body; for JSON, assert media type and body separately.
7. When caching causes confusion, inspect the resolver cache, template engine cache, and HTTP/browser cache in turn.

You can enable debug logging in development:

```properties
logging.level.org.springframework.web.servlet.view=DEBUG
logging.level.org.thymeleaf=INFO
```

When tests need more visibility, use `andDo(print())` on `MockMvc` to inspect the model, view name, and response. Do not log or expose sensitive model data in production responses.

## 11. Template Rendering Security

- Use `th:text` for untrusted input because it HTML-escapes content; be cautious with `th:utext` as it can render unsanitized HTML.
- Do not allow clients to supply arbitrary template/view names directly as return values; only use names from an explicit allowlist.
- Do not concatenate client-supplied URLs into `redirect:` without validating host/path, to prevent open redirects.
- Keep secrets and internal fields out of the model, HTML hidden inputs, JavaScript, and server-rendered markup.
- For forms, validation does not replace CSRF protection or authorization; apply the appropriate security mechanisms.
- In production, configure appropriate template caching and versioned assets; do not disable caching system-wide merely for debugging convenience.
- `forward:` is not a way to bypass authorization. Security filter configurations may apply differently depending on dispatcher type and must be verified against the real system.

## 12. Self-Check Questions

1. What does `@Controller` returning `"books/detail"` mean? **A logical view name**, not an HTML body or browser URL.
2. What decides which controller handles `GET /books/7`? **HandlerMapping**, not ViewResolver.
3. How do `ViewResolver` and `View` differ? **The resolver selects the View; the View renders the model into the response**.
4. Between two resolvers with order `0` and `100`, which runs first? **Order 0**.
5. Why does JSP `InternalResourceViewResolver` go last? **It cannot verify JSP existence before Servlet dispatch and easily claims every name**.
6. Does `BeanNameViewResolver` render a service bean with the same name? **No**, it requires a bean of type `View`.
7. Where does default Thymeleaf in Boot look for `"home"`? **`classpath:/templates/home.html`**, if default prefix/suffix are kept.
8. When a method annotated with `@ResponseBody` returns `"home"`, does Thymeleaf render it? **No**, the literal text `home` is written directly to the body.
9. Does `ContentNegotiatingViewResolver` convert Java objects into JSON by itself? **No**; it selects another View by media type. JSON REST endpoints normally use message converters.
10. Is `redirect:/orders/7` equivalent to the template `orders/7.html`? **No**, it redirects to a new URL.
11. Should an invalid form return the template or redirect immediately? **Usually return the template in the same request** to preserve `BindingResult`.
12. Does setting `spring.thymeleaf.template-resolver-order` change the order between Thymeleaf and JSP ViewResolvers? **No**; that is an internal ordering level inside the template engine.
13. If the view name is correct but the HTML fails, is it always a 404? **No**, a template rendering exception can cause HTTP 500.
14. If a test only checks that `view().name("home")` passes, is the template guaranteed to render? **Not necessarily**; add assertions on the rendered HTML.
15. Why avoid `th:utext` for user names? **Because untrusted markup could be injected into HTML, causing XSS**.

## 13. Official Documentation

- [Spring Framework 6.2 — View Resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/viewresolver.html): `ViewResolver`/`View` contracts, chaining, JSP-last, redirect/forward, and content negotiation.
- [Spring Framework 6.2 — MVC View Resolvers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/view-resolvers.html): API for configuring resolvers via `WebMvcConfigurer`.
- [Spring Framework 6.2 — JSP and JSTL](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-view/mvc-jsp.html): JSP resolver and `JstlView`.
- [Spring Boot 3 — Spring MVC How-to](https://docs.spring.io/spring-boot/3.3/how-to/spring-mvc.html): default resolver beans and template engine integration.
- [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html): `spring.thymeleaf.prefix`, suffix, cache, view-names, and related properties.
- [Thymeleaf + Spring Tutorial](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html): Spring MVC/Thymeleaf, expressions, forms, and validation.

**Remember:** `@Controller` returns a logical view name; MVC queries `ViewResolver`s in priority order, locates the matching `View`, and the `View` renders the model via a template engine or Servlet/JSP. `@RestController` and `@ResponseBody` go through message converters. Choose the right pipeline before tweaking resolvers and prefix/suffix settings.
