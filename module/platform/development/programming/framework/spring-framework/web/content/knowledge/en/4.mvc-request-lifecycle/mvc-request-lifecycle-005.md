# ModelAndView, ViewResolver, and the View Rendering Phase in Spring MVC

## 1. Problem: Once the Controller Finishes, How Does HTML Reach the Browser?

An HTTP request to a Spring MVC application does not end the moment the controller method returns. With **server-side rendered HTML**, after the controller fetches data and decides which page to display, the framework still has to:

1. Gather the data to display (**model**).
2. Identify the logical view name or view object (**view**).
3. Find a tool/target capable of handling the view (**view resolution**).
4. Render the view using the model into HTTP response content (**rendering**).

The three central concepts are **`ModelAndView`**, **`ViewResolver`**, and **`View`**. They work with `DispatcherServlet` to complete the final stretch of the MVC flow.

For example, the browser calls:

```http
GET /books HTTP/1.1
Host: localhost:8080
Accept: text/html
```

The controller may return the page name `"books"` along with a model containing a title and a list of books. A `ViewResolver` maps `"books"` to a template such as `classpath:/templates/books.html`; the template engine substitutes data expressions and produces HTML to send back to the browser.

**Distinction:** A controller returning `"books"` does not mean the response body contains only the word `books`. With `@Controller` and no `@ResponseBody`, this is typically a **logical view name**. With `@RestController` or `@ResponseBody`, the result goes through the response-body writing mechanism and usually **does not invoke ViewResolver**.

## 2. Position in the MVC Processing Flow

```text
Client / Browser
      |
      | HTTP GET /books
      v
Servlet container (Tomcat, Jetty, ...)
      |
      v
DispatcherServlet
      |
      +--> HandlerMapping: find handler matching URL + method
      |
      +--> HandlerAdapter: prepare arguments, invoke controller
      |         |
      |         v
      |   @Controller: run business logic, provide model/view
      |         |
      |         v
      |   ModelAndView or equivalent info
      |
      +--> ViewResolver(s): logical name "books" -> View
      |                                           |
      |                                           v
      +-------------------------------------- View.render(...)
                                                  |
                                                  v
                                        HTML / HTTP response
                                                  |
                                                  v
                                               Browser
```

This is a **typical synchronous HTML-producing request flow**, omitting filters, interceptors, exception resolvers, locale resolution, multipart processing, and other capabilities. Spring MVC has many return value types and async mechanisms; not every request walks through every view lookup step.

In Spring MVC, `DispatcherServlet` is the **front controller**. It coordinates strategy components such as `HandlerMapping`, `HandlerAdapter`, `HandlerExceptionResolver`, and `ViewResolver`. From controller to response, the framework is responsible for interpreting the return value type and deciding how to complete the request.

### Relationships Among Classes

| Component | Job | Example |
|---|---|---|
| `Model` | Holds data for the view to read | `pageTitle`, `books`, `user` |
| Logical view name | Business/UI-level view name | `"books"`, `"account/profile"` |
| `ModelAndView` | Bundles view and model data, optionally carrying an HTTP status | `new ModelAndView("books")` |
| `ViewResolver` | Turns a logical view name into a `View` object | Thymeleaf, JSP, FreeMarker resolver |
| `View` | Renders data into the HTTP response | Thymeleaf view, JSP view, RedirectView |
| `DispatcherServlet` | Coordinates the request and rendering step | Spring MVC's front controller |

`ModelAndView` is not already-rendered HTML. `ViewResolver` is not the template engine either: the resolver **selects/resolves the view**, whereas `View` and the underlying technology perform the rendering. Some systems bundle these roles within a single library, but conceptually they should be kept distinct.

## 3. What Is Model?

**Model** represents the attributes that a controller supplies to the view for a single request. In an annotated Spring MVC controller, `org.springframework.ui.Model` is the interface for placing name–value pairs into the model:

```java
@GetMapping("/greeting")
public String greeting(Model model) {
    model.addAttribute("name", "Lan");
    model.addAttribute("message", "Welcome!");
    return "greeting";
}
```

**This snippet only illustrates a handler**; it is not standalone runnable because it lacks the controller class, imports, dependencies, and template. Inside the `greeting` view, attributes `name` and `message` can be used to generate UI content.

Distinguish clearly:

- `Model` is the API for adding attributes used during rendering.
- `ModelMap` is a map-style implementation for model data.
- `Map<String, Object>` can also be used by Spring MVC in certain controller signatures.
- `@ModelAttribute` declares/initializes model attributes and supports data binding; it is not synonymous with `@RequestBody`.
- A model used for rendering **does not automatically survive across multiple HTTP requests**; a redirect creates a new request, passing one-time notices can use flash attributes, and persisting session state requires a dedicated mechanism.

Conceptual illustration of a model:

```text
pageTitle -> "Book Catalog"
books     -> ["Java Core", "Spring MVC"]
notice    -> "Saved successfully"
```

When the template reads these values, it can display the heading, iterate over the list, and show the notice. Model data may be strings, numbers, collections, or business objects/view DTOs. Avoid dumping complex entities containing sensitive fields straight into the model if the view only needs a few specific properties.

## 4. What Is ModelAndView?

`org.springframework.web.servlet.ModelAndView` is an **object combining view and model information**, optionally including an HTTP status, for Spring MVC to perform the rendering step.

Common ways to construct it:

```java
ModelAndView mav = new ModelAndView("books");
mav.addObject("pageTitle", "Book Catalog");
mav.addObject("books", List.of("Java Core", "Spring MVC"));
return mav;
```

Or pass data up front:

```java
return new ModelAndView("books", "pageTitle", "Book Catalog");
```

You can supply an actual `View` object instead of a view name, or set an appropriate status using the `ModelAndView` API. However, in most server-side HTML controllers, **logical view name + model** is clear and flexible enough.

### Internal Parts

```text
ModelAndView
  ├── View name: "books"             (or a View object)
  ├── Model:
  │     "pageTitle" = "Book Catalog"
  │     "books"     = List<String>
  └── HTTP status (optional)
```

Commonly used methods:

| API | Effect |
|---|---|
| `new ModelAndView("books")` | Creates result with a logical view name |
| `addObject("key", value)` | Adds an attribute to the model |
| `addAllObjects(map)` | Adds multiple attributes |
| `getViewName()` | Gets the view name if the result uses a view name |
| `getView()` | Gets the `View` object if set directly |
| `getModel()` | Gets the attributes in the model |
| `setViewName("...")` | Changes the view name |
| `setStatus(HttpStatus.OK)` | Attaches an appropriate HTTP status when needed |

When a controller returns `ModelAndView`, Spring MVC interprets it into view and model to coordinate rendering. If a controller returns `String` alongside a `Model` parameter, Spring can assemble equivalent information without requiring you to instantiate `ModelAndView` yourself.

### Comparing Two Ways to Express It

**Approach A: controller returns `ModelAndView`**

```java
@GetMapping("/books")
public ModelAndView books() {
    ModelAndView mav = new ModelAndView("books");
    mav.addObject("pageTitle", "Book Catalog");
    mav.addObject("books", List.of("Java Core", "Spring MVC"));
    return mav;
}
```

**Approach B: controller returns view name, model via parameter**

```java
@GetMapping("/books")
public String books(Model model) {
    model.addAttribute("pageTitle", "Book Catalog");
    model.addAttribute("books", List.of("Java Core", "Spring MVC"));
    return "books";
}
```

These are two **mutually exclusive alternatives** for declaring the endpoint and must not both map `GET /books` in the same application. Both snippets are standalone method examples requiring placement in a `@Controller` with appropriate imports and templates.

When logic just adds a few attributes and picks one page, `String + Model` is usually more concise. `ModelAndView` is convenient when bundling view and model as a single value, dynamically picking views, or integrating with APIs returning `ModelAndView`.

## 5. ViewResolver: Turning a Logical Name into a View

The `org.springframework.web.servlet.ViewResolver` interface has this core conceptual method:

```java
View resolveViewName(String viewName, Locale locale) throws Exception;
```

The resolver takes `viewName` and `locale` and tries to locate a matching `View` object. When it cannot resolve one, by contract it may return `null`, allowing other resolvers to try next.

Example:

```text
Controller returns: "books"
        |
        v
ThymeleafViewResolver
        |
        v
Thymeleaf view "books"
        |
        v
Template: classpath:/templates/books.html
```

**The actual path depends on the engine and configuration.** Not every `ViewResolver` prepends a prefix and appends a suffix, and not every view is an HTML file. Some views represent JSPs, redirects, other content representations, or a pre-provided bean.

### 5.1. Common ViewResolvers

| Resolver | Usage scenario | Notes |
|---|---|---|
| `ThymeleafViewResolver` | Renders Thymeleaf templates | Integrates Thymeleaf's template engine |
| `InternalResourceViewResolver` | JSP and Servlet forwarding | Should be placed last in resolver chain |
| `FreeMarkerViewResolver` | Renders FreeMarker | Depends on FreeMarker configuration |
| `BeanNameViewResolver` | Looks up `View` beans by name | Useful for custom views |
| `ContentNegotiatingViewResolver` | Picks a view compatible with client-accepted media types | Combines/delegates to other resolvers |
| `UrlBasedViewResolver` | Maps view names by URL convention | Base class for several resolvers |

**Note on priority:** Multiple resolvers can be declared and ordered via the `order` property (smaller order values are evaluated earlier). The first resolver that finds a matching view can end the resolution process, so wrong ordering may prevent the desired engine from being selected.

`InternalResourceViewResolver` has difficulty verifying whether the target JSP exists before forwarding the request, so in multi-resolver configurations it usually needs to be placed **last**. If placed earlier, it may claim almost any view name and block subsequent resolvers.

### 5.2. ViewResolver Does Not Always Need Manual Configuration

In Spring Boot MVC, adding `spring-boot-starter-thymeleaf` causes Boot to auto-configure the Thymeleaf view resolver and look for templates under `classpath:/templates/`. View name `"books"` defaults to `templates/books.html`.

Depending on configuration, properties like these can be used:

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.cache=false
```

The prefix/suffix values above are common Thymeleaf defaults in Boot. Setting `cache=false` is helpful when editing templates during development, but generally should not be disabled arbitrarily in production. **View resolver caching and template engine caching are not necessarily the same mechanism**.

Plain Spring Framework lacks Boot auto-configuration; you must provide the required MVC/template configuration yourself. Do not take Boot properties and assume they work automatically in a plain Spring MVC WAR.

### 5.3. Locale and Content Negotiation

`ViewResolver` receives `Locale`, so some resolvers/templates can select content matching the language or region. Locale can also affect date/number formatting and message bundles inside templates; do not confuse locale with view path.

When multiple representations exist, `ContentNegotiatingViewResolver` can combine resolvers and use requested media types (e.g., `Accept` header) to choose a compatible view. However, returning JSON from `@ResponseBody` normally goes through `HttpMessageConverter` and **does not need to force JSON into a template view**.

## 6. How Does the Rendering Step Actually Happen?

After selecting a `View`, `DispatcherServlet` invokes the view's render capability, whose contract has the form:

```java
void render(
        Map<String, ?> model,
        HttpServletRequest request,
        HttpServletResponse response
) throws Exception;
```

This is an **API signature for explanation**, not a standalone Java program. `HttpServletRequest`/`HttpServletResponse` imports correspond to Jakarta Servlet in Spring Framework 6+.

Typical step-by-step when rendering Thymeleaf:

1. `View` receives the model and request/response.
2. The engine finds/reads the template named `books` per prefix/suffix.
3. Expressions inside the template access the model (`pageTitle`, `books`).
4. The engine generates HTML markup, evaluating conditions, loops, fragments, links, and escaped output per engine syntax.
5. Spring and the Servlet response write content, status, and appropriate headers, such as `Content-Type: text/html;charset=UTF-8` when configured.
6. The Servlet container sends response bytes to the client; the browser parses HTML and performs client-side UI rendering on screen.

**Two types of "render" to distinguish:** Spring renders **HTML content on the server**; the browser renders the **visual UI** from HTML/CSS/JS on the client. `View.render` does not directly draw pixels on the user's screen.

Example Thymeleaf template:

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="${pageTitle}">Placeholder title</title>
</head>
<body>
    <h1 th:text="${pageTitle}">Placeholder title</h1>
    <ul>
        <li th:each="book : ${books}" th:text="${book}">Book</li>
    </ul>
</body>
</html>
```

If the model has `pageTitle="Book Catalog"` and `books=["Java Core", "Spring MVC"]`, the browser receives an HTML document containing that heading and two list items. In the rendered HTML, `th:text` and `th:each` attributes have already been processed by the engine; it is no longer the raw template.

### Why Care About HTML Escaping?

Thymeleaf `th:text` escapes characters that carry special meaning in HTML. For example, if a book title contains `<script>`, using `th:text` displays it as literal text rather than injecting an executable script tag. Conversely, `th:utext` outputs unescaped HTML and poses an **XSS risk** if rendering untrusted data that has not been properly validated/sanitized.

Do not rely on "automatic template escaping" as a substitute for authentication, authorization, input validation, and application security policies. Model data should only contain information permitted for display; server-side rendering can still leak data if a controller dumps sensitive details into a template.

## 7. Controller Return Value Types: When Is ViewResolver Involved?

In Spring MVC, how a return value is interpreted depends on **annotations and return-value handlers**.

| Controller returns | Typical Spring handling | Uses ViewResolver? |
|---|---|---|
| `@Controller` returning `String "books"` | Logical view name, combined with current model | Yes |
| `@Controller` returning `ModelAndView("books")` | View + model (+ optional status) | Yes if a view name is given |
| `@Controller` returning a `View` object | Uses the view object directly with the model | No need to resolve a view name |
| `@Controller` returning `Model`/`Map` | Adds attributes; may infer default view name | Yes if rendering a view |
| `@Controller` + `@ResponseBody` | Writes data using `HttpMessageConverter` | No |
| `@RestController` | Writes result as response body by default | No in normal cases |
| `ResponseEntity<T>` | Specifies status, headers, and body | Not via normal view path |
| `"redirect:/books"` | Selects redirect view / HTTP redirect | May use a strategy handling redirect prefix |
| `"forward:/books"` | Server-side forward to target resource | Depends on resolver supporting forward prefix |

**Confusing example:**

```java
@Controller
class ExampleController {
    @GetMapping("/a")
    public String a() {
        return "home";            // logical view name: home
    }

    @ResponseBody
    @GetMapping("/b")
    public String b() {
        return "home";            // plain text response body: home
    }
}
```

These two methods are placed in an illustrative class, assuming MVC configuration and a `home` view exist. The exact same Java `String` value can lead to two different HTTP paths depending on annotations.

**`@RestController` combines the semantics of `@Controller` and `@ResponseBody` at the class level.** When you want to render server-side HTML templates, the natural choice is `@Controller` returning a view name/`ModelAndView`, rather than `@RestController` returning `"books"`.

## 8. Complete Example: Spring Boot MVC + Thymeleaf

The example runs on **Java 17+**, Maven, and Spring Boot 3.3.5 (a fixed version chosen to illustrate the API, not claimed as the latest release). When building a new product, select a currently supported Spring Boot version appropriate for your environment. The application uses `spring-boot-starter-web` for HTTP MVC handling and `spring-boot-starter-thymeleaf` for HTML rendering.

### 8.1. Project Structure

```text
mvc-view-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/views/
    │   │   ├── MvcViewApplication.java
    │   │   ├── CatalogService.java
    │   │   └── CatalogController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/books.html
    └── test/
        └── java/com/example/views/
            └── CatalogControllerTest.java
```

### 8.2. Maven Dependencies

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>mvc-view-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
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

The Thymeleaf starter provides template engine integration with Spring MVC. Boot supplies `DispatcherServlet`, sets up the matching resolver, and locates HTML files in the default templates directory; there is no need to declare `InternalResourceViewResolver` manually for this example.

### 8.3. Bootstrapping the Application

Create `MvcViewApplication.java`:

```java
package com.example.views;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcViewApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcViewApplication.class, args);
    }
}
```

### 8.4. Data-Providing Service

Create `CatalogService.java`:

```java
package com.example.views;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    public List<String> listTitles() {
        return List.of("Java Core", "Spring MVC");
    }
}
```

The service uses an immutable list so the example has deterministic output without needing a database. In a real application, the service can fetch data from repositories or external services, while the controller remains focused on preparing data needed for the view.

### 8.5. Controller Illustrating Three Processing Paths

Create `CatalogController.java`:

```java
package com.example.views;

import java.util.List;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.ModelAndView;

@Controller
public class CatalogController {
    private final CatalogService catalog;

    public CatalogController(CatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/books")
    public ModelAndView showBooks() {
        ModelAndView mav = new ModelAndView("books");
        mav.addObject("pageTitle", "Book Catalog");
        mav.addObject("books", catalog.listTitles());
        return mav;
    }

    @GetMapping("/books/alternative")
    public String showBooksAlternative(Model model) {
        model.addAttribute("pageTitle", "Book Catalog");
        model.addAttribute("books", catalog.listTitles());
        return "books";
    }

    @GetMapping("/books/json")
    @ResponseBody
    public List<String> booksAsJson() {
        return catalog.listTitles();
    }

    @GetMapping("/books/go")
    public String navigateToBooks() {
        return "redirect:/books";
    }
}
```

Four endpoints with different meanings:

- `GET /books`: creates a `ModelAndView` with view name `books` and model; Spring finds the Thymeleaf view to render.
- `GET /books/alternative`: equivalent HTML outcome, but the controller returns a `String` view name and uses a `Model` parameter.
- `GET /books/json`: `@ResponseBody` makes Spring use HTTP message conversion to return JSON; **does not render books.html**.
- `GET /books/go`: creates an HTTP redirect to `/books`; the browser sends a new request to the target.

`List<String>` on the JSON endpoint is converted to JSON via Jackson in `spring-boot-starter-web`'s configuration. The application does not return service objects or template engine objects to the client.

### 8.6. Creating the Thymeleaf Template

Create `src/main/resources/templates/books.html`:

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="${pageTitle}">Default title</title>
</head>
<body>
    <h1 th:text="${pageTitle}">Default title</h1>
    <ul>
        <li th:each="book : ${books}" th:text="${book}">Book title</li>
    </ul>
    <a th:href="@{/books/alternative}">Model-based version</a>
</body>
</html>
```

During rendering, Thymeleaf:

1. Receives `pageTitle` and `books` from the model.
2. Replaces `th:text` with HTML-escaped text data.
3. Iterates through `books` using `th:each` to produce two `li` elements.
4. Builds the link with `th:href`.
5. Produces the HTML response for the browser.

The `books.html` file is the source template; at runtime the browser does not need to understand `th:...` syntax. The server-side engine has already processed those attributes.

### 8.7. Configuration and Running

In `src/main/resources/application.properties`, you can set:

```properties
server.port=8080
spring.thymeleaf.cache=false
```

`cache=false` is a development convenience to observe template changes. Do not add `@EnableWebMvc` to a Boot example unless you specifically need to replace parts of MVC auto-configuration.

Run from the project directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Or build the JAR first and run:

```bash
mvn clean package
java -jar target/mvc-view-demo-1.0.0.jar
```

Assuming the server runs normally on `localhost:8080`, test:

```bash
curl -i "http://localhost:8080/books"
```

The expected response has status `200 OK`, a `text/html`-compatible `Content-Type`, and HTML containing the heading **Book Catalog**, along with two lines **Java Core** and **Spring MVC**. Do not assert every exact response byte because formatting and headers depend on versions/configuration.

```bash
curl -s "http://localhost:8080/books/json"
```

Exact expected JSON body when using the example list:

```json
["Java Core","Spring MVC"]
```

```bash
curl -i "http://localhost:8080/books/go"
```

Expected result: HTTP `302 Found` with a `Location` header pointing to `/books`; it may be an absolute URL or a form matching runtime configuration. By default `curl` **does not follow redirects** unless `-L` is added.

```bash
curl -L "http://localhost:8080/books/go"
```

When following the redirect, the client ultimately receives the HTML of `/books`.

### 8.8. Testing View Name, Model, and HTML Together

Create `src/test/java/com/example/views/CatalogControllerTest.java`:

```java
package com.example.views;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CatalogControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void rendersViewFromModelAndView() throws Exception {
        mvc.perform(get("/books"))
           .andExpect(status().isOk())
           .andExpect(view().name("books"))
           .andExpect(model().attribute("pageTitle", "Book Catalog"))
           .andExpect(model().attribute(
                   "books", List.of("Java Core", "Spring MVC")))
           .andExpect(content().string(containsString("Java Core")))
           .andExpect(content().string(containsString("Spring MVC")));
    }

    @Test
    void writesJsonWithoutTemplateRendering() throws Exception {
        mvc.perform(get("/books/json"))
           .andExpect(status().isOk())
           .andExpect(content().json(
                   "[\"Java Core\",\"Spring MVC\"]"));
    }

    @Test
    void redirectsToBooks() throws Exception {
        mvc.perform(get("/books/go"))
           .andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrl("/books"));
    }
}
```

Run:

```bash
mvn test
```

The assertions verify **meaningful outcomes of each stage**: the handler chooses view `books`, the model holds the two required attributes, Thymeleaf actually renders HTML containing the content, the JSON endpoint produces JSON, and the redirect generates the target URL. This is a Spring Boot integration test with `MockMvc` running through the MVC pipeline without opening a real network port. When context paths, security, or templates change, test expectations should be updated accordingly.

## 9. Redirect and Forward: Both Can Return Special View Names

A `@Controller` can return a logical view name prefixed with `redirect:` or `forward:` depending on MVC configuration.

### 9.1. Redirect: Client Is Instructed to Go to Another URL

```java
@GetMapping("/old")
public String oldPage() {
    return "redirect:/books";
}
```

This is an **illustrative method**; to run, it must be placed in a registered controller. Spring typically uses an equivalent `RedirectView` to produce a redirect response. The client receives a 3xx code and `Location`, then sends **a new request** to the target URL. The URL displayed in the browser's address bar usually changes when the browser follows the redirect.

Redirects are especially useful for the **Post/Redirect/Get (PRG)** pattern: after the server processes a POST form successfully, returning a redirect makes the browser load the result page via GET, reducing the risk of a user refreshing and accidentally resubmitting the POST.

Illustrative method showing PRG with a flash message:

```java
@PostMapping("/orders")
public String submitOrder(
        @RequestParam String title,
        RedirectAttributes redirectAttributes) {
    // Process order creation via service and check for errors here.
    redirectAttributes.addFlashAttribute(
            "notice", "Order received: " + title);
    return "redirect:/orders";
}
```

This is an **illustrative snippet**, not a complete production endpoint: it lacks the class, imports, service, input validation, authentication/CSRF, order persistence, and the `GET /orders` target. `RedirectAttributes.addFlashAttribute` passes temporary data to the post-redirect request without putting notices in the query string. Flash attributes are typically stored temporarily via a session/FlashMap mechanism; concurrent requests can create situations that need careful handling.

Do not assume the previous request's model persists into the next request; after a redirect, reload data or use flash/session as designed.

### 9.2. Forward: Server Forwards Internally

```java
@GetMapping("/legacy")
public String legacyPage() {
    return "forward:/books";
}
```

This is also an illustrative method. Forward uses the `RequestDispatcher.forward()` mechanism in the Servlet container to transfer processing **internally on the server**, typically keeping the same request/response, and the browser does not see an HTTP 3xx redirect from this controller. Forward is subject to Servlet API constraints—for instance, once a response is committed it generally cannot be forwarded.

Do not treat redirect and forward as completely interchangeable. Redirect creates a new request, can change the URL, and suits PRG; forward stays within the current request. Verify view resolvers and servlet mappings when using the `forward:` prefix.

## 10. How the ViewResolver Stage Interacts with Errors

Different situations can produce symptoms that look similar in the browser:

| Symptom | Suspected stage | Check suggestions |
|---|---|---|
| `404 Not Found` on `/books` | Handler mapping or URL | Check `@GetMapping`, context path, servlet mapping |
| Controller runs, but template not found | View resolution/rendering | Check view name, `templates/`, suffix, starter |
| `500 Internal Server Error` with template error | Rendering | Check expressions, model attributes, template syntax errors |
| Browser literally shows the word `books` | Return value writes body | Did you accidentally use `@RestController`/`@ResponseBody`? |
| Model has data, but page is blank | Template expression / binding | Check key names and how they are accessed in template |
| Multiple ViewResolvers, wrong page picked | Resolver chain | Check `order` and overly broad resolvers |
| JSP not found despite right view name | JSP path / resolver / packaging | Check `InternalResourceViewResolver` and WAR/JAR |
| Redirect leaks data in URL | Redirect attributes | Use `RedirectAttributes` only for public data; flash for temporary notices |

### 10.1. Wrong Path / View Name Mismatch

For instance, a controller returns `"book-list"`, while the file is `templates/books.html`. Without special mapping configuration, the resolver cannot find template `book-list`. Create the matching template name or fix the view selection logic, rather than randomly changing unrelated properties.

### 10.2. Accidentally Using `@RestController`

```java
@RestController
class WrongPageController {
    @GetMapping("/bad-page")
    public String page() {
        return "books";
    }
}
```

This example returns the literal text `books` as the response body, **without** asking Thymeleaf to look up `books.html`. For server-side HTML, use `@Controller` and return the view name; for data-returning APIs, keep `@RestController`.

### 10.3. Mixing Web Templates with `@ResponseBody`

If `@ResponseBody` is placed on a method returning `ModelAndView`, Spring may attempt to serialize the object itself as a body rather than interpreting it as an MVC view-rendering result. Do not combine them for HTML display; pick one response mechanism.

### 10.4. JSP and Spring Boot JARs

JSP has different packaging, container, and configuration requirements than Thymeleaf. Spring Boot documents limitations when using JSP with embedded Servlet containers and executable JARs. Do not mechanically copy `InternalResourceViewResolver` config from a traditional WAR project into a Boot JAR; if JSP is required, evaluate the specific deployment structure. For introductory Boot MVC examples, Thymeleaf is usually easier to practice with.

### 10.5. Unescaped Data or Exposing Sensitive Data

The model is not an authorization mechanism. Ensure services/controllers restrict what data is placed into the view and apply context-appropriate escaping/encoding. With Thymeleaf HTML, prefer `th:text` for input text rather than rendering unverified HTML.

## 11. Observing and Verifying the Rendering Pipeline

You can debug via a sequence of questions:

1. **Did the request reach the right `DispatcherServlet`?** Check URL, HTTP method, and request mapping logs.
2. **Which controller was selected?** Check handler mapping for matching path/method.
3. **What did the controller return?** `String` view name, `ModelAndView`, `ResponseEntity`, or `@ResponseBody`?
4. **Does the model contain all needed attributes?** Check keys, data types, and values.
5. **Which resolver processed the view?** Check engine/starter, prefix, suffix, resolver order, and template lookup errors.
6. **What did the view render?** Check HTML response, status, `Content-Type`, especially expression errors.
7. **Does the browser display something different from the response?** Check CSS, JavaScript, browser cache, and Developer Tools.

In a learning environment, you can selectively enable Spring MVC logging to observe mapping and view resolution, while avoiding verbose logging of user data or sensitive request bodies. When debugging, compare the **HTML in Network → Response** against the **DOM after JavaScript executes** to distinguish server template bugs from client rendering bugs.

Remember that view resolution can be **completely skipped** if the response was already handled (e.g., `@ResponseBody`, `ResponseEntity`, streaming) or the controller triggered a redirect. Seeing no Thymeleaf logs in a JSON API is normal behavior.

## 12. Design Question: Should ModelAndView Always Be Used?

Not necessarily. In annotated Spring MVC, pick the style suited to the job:

- When the view is fixed and there are only a few attributes: `String` + `Model` is usually concise.
- When you want to package model and view into one object or select views dynamically: `ModelAndView` is explicit.
- When a controller produces JSON/REST responses: `@RestController`/`@ResponseBody`/`ResponseEntity` is usually more suitable.
- When serving a large file/stream: consider an appropriate response or streaming mechanism instead of forcing it into an HTML template.
- When redirecting after POST: return `redirect:` or `RedirectView` combined with `RedirectAttributes`.
- When the UI is a static SPA or served via CDN: Spring MVC may act purely as a backend API; server-side template rendering is not required.

Do not push database queries, external service calls, business updates, or complex authorization checks into templates. Controllers should coordinate, services should execute business logic, models should prepare presentation data, and views should only render. This separation makes code easier to test and reduces security bugs.

## 13. Self-Check Questions

**Question 1.** A `@Controller` returns `"profile"` and adds `user` to `Model`. Does the browser receive the literal string `profile` as the body?  
**Answer:** Usually no. Spring treats that string as a logical view name, runs view resolution, and renders with the model. The final body is produced by the view.

**Question 2.** Does `ModelAndView` compile Thymeleaf templates itself?  
**Answer:** No. It carries view and model information; `ViewResolver` selects a `View`, and then the view together with the template engine performs rendering.

**Question 3.** If a `@RestController` returns `"books"`, is `books.html` rendered?  
**Answer:** Not by default; `@RestController` applies `@ResponseBody`, so the string is written directly to the response body.

**Question 4.** `GET /books` returns 404—does that definitely mean `ViewResolver` is misconfigured?  
**Answer:** No. The request might not match any handler/mapping. Verify routing first before investigating view resolution.

**Question 5.** If Spring Boot has the Thymeleaf starter, do you need to manually create an `InternalResourceViewResolver` for `books.html`?  
**Answer:** No. With default Thymeleaf setup, Boot auto-configures the appropriate resolver and looks up templates in `src/main/resources/templates`.

**Question 6.** What is the core difference between `redirect:/books` and `forward:/books`?  
**Answer:** Redirect responds asking the client to send a new request to the target URL; forward transfers the request internally on the server when Servlet conditions permit.

**Question 7.** Does `Model` data from a POST request automatically remain in `Model` after a redirect?  
**Answer:** Not by default. You can use flash attributes to pass temporary notices or reload data in the target GET request.

**Question 8.** Can `InternalResourceViewResolver` be placed first in a chain of multiple resolvers?  
**Answer:** It is not recommended. The JSP resolver typically cannot tell for sure whether a resource exists before forwarding, so it should be placed last to give specialized resolvers a chance to handle views first.

## 14. Official References

1. [Spring Framework — DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html): front controller and MVC strategies.
2. [Spring Framework — View Resolution](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/viewresolver.html): `ViewResolver`, `View`, resolver chains, redirect, and forward.
3. [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): controller return value types supported by Spring MVC.
4. [Spring Framework — Redirect Attributes / Flash Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html): passing data across redirects.
5. [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): auto-configuration of template engines and template locations in Boot.

**Key takeaway:** In a server-side HTML-rendering request, the controller prepares the **model** and specifies the **view**; `ModelAndView` can bundle both, `ViewResolver` locates the `View` object, and `View.render` produces the HTTP response. With `@ResponseBody`/`@RestController`, Spring writes data directly via message conversion and typically skips view resolvers.
