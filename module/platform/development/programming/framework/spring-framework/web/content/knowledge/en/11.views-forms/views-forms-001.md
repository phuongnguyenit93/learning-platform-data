# Model, ModelMap, ModelAndView, and Logical View Names in Spring MVC

## 1. Lesson Objectives

When building HTML interfaces with **Spring MVC**, a controller usually does not return HTML directly. It prepares data for the interface (**model**) and indicates which interface should be displayed (**view**). Spring then uses a **ViewResolver** to select the actual view (for example, a Thymeleaf template) and render the response.

This lesson helps you:

1. Distinguish **`Model`**, **`ModelMap`**, and **`ModelAndView`** in terms of Java type, data-holding capability, and how the view is specified.
2. Understand how a **logical view name** such as `"products/detail"` is resolved to an actual template like `classpath:/templates/products/detail.html`.
3. Choose an appropriate controller style: passing `Model`/`ModelMap` as a parameter and returning a `String`, or returning `ModelAndView`.
4. Understand default view names, `redirect:`, `forward:`, `@ModelAttribute`, and form data placed into the model.
5. Recognize when a `String` is interpreted as a **view name** and when it is sent as the **response body** under `@ResponseBody`/`@RestController`.
6. Write a Java 17+ / Spring Boot 3.x application with Thymeleaf templates, forms, and MockMvc tests.

**Scope:** Spring Framework 6.x, Spring Boot 3.x, Spring MVC using the Servlet stack and server-rendered HTML. Spring WebFlux and SPA frontends have their own rendering and data-passing mechanisms. View names and data binding remain useful knowledge when an application combines HTML pages with REST APIs.

## 2. Model and View Have Two Distinct Roles

An HTML page displaying a product may need data such as:

~~~json
{"id":101,"name":"Spring MVC Book","price":120000}
~~~

With server-rendered Spring MVC, the controller puts that data into the **model**, specifies the **view** name, and Spring coordinates both to render HTML:

~~~mermaid
flowchart TD
    A[HTTP GET /products/101] --> B[DispatcherServlet]
    B --> C[Controller]
    C --> D[Model: product]
    C --> E[Logical view: products/detail]
    D --> F[ViewResolver]
    E --> F
    F --> G[Template: products/detail.html]
    G --> H[HTML response]
~~~

- **Model** is a collection of **named attributes** for the view to use. The model is not an entity/database model in the ORM sense, nor is it automatically stored in a session or database.
- **View** is the way to render the response, such as a Thymeleaf template, JSP, or another `View` implementation.
- **Logical view name** is an identifier such as `"products/detail"`, not necessarily a physical file path.
- **ViewResolver** locates an appropriate `View` based on the logical name. When using default Thymeleaf in Spring Boot 3.x, the name `"products/detail"` typically maps to `src/main/resources/templates/products/detail.html`.
- The view combines with the model to produce HTML returned to the browser. Data in the model normally has the scope of that request's handling; do not treat it as persistent storage.

Common misconception: In Spring MVC, `model.addAttribute("product", product)` **does not send JSON** to the client. The controller needs to return a view name or a view object; the template rendering step then produces the HTML response body. With `@RestController`, the return value is typically converted directly into the body via `HttpMessageConverter`, without any template lookup step.

## 3. Comparing `Model`, `ModelMap`, and `ModelAndView`

| Criterion | `Model` | `ModelMap` | `ModelAndView` |
| --- | --- | --- | --- |
| Package | `org.springframework.ui.Model` | `org.springframework.ui.ModelMap` | `org.springframework.web.servlet.ModelAndView` |
| Java type | **Interface** | **Class** extending `LinkedHashMap<String, Object>` | **Class** combining model and view |
| Primary role | Add/read model attributes | Map-style model | Specify the view and attach the model in the same result |
| Data-adding API | `addAttribute(...)`, `addAllAttributes(...)`, `asMap()` | `addAttribute(...)`, `put(...)`, `get(...)` | `addObject(...)`, `addAllObjects(...)` |
| Handler parameter | Yes | Yes | Uncommon as a parameter, usually a **return value** |
| Typically returned from handler | `String` view name or `Model` itself | `String` view name or `ModelMap` itself | `ModelAndView` |
| View name carried inside object? | No | No | Yes (`setViewName`, constructor) |
| When to choose | Most regular HTML handlers | When you need Map-style API operations | When you want to return model + view + status in one object |

`Model` and `ModelMap` are **two ways to access Spring MVC's model**, not two separate data stores. In ordinary MVC handlers, Spring provides the model object used for the request, whereas `ModelAndView` is a **return value carrying both view and model information**. They do not create three different ways of sending data to the browser.

**Quick rule of thumb:** if a handler only needs to add a few attributes and display a template, use `Model` as a parameter and return a `String` view name. If you need a `Map` API, you can accept `ModelMap`. If you want to build an object representing the view, model, and possibly the status at the same time, return `ModelAndView`.

## 4. `Model`: Direct Interface for Working with Attributes

The most common pattern in a controller using Thymeleaf:

~~~java
@Controller
@RequestMapping("/products")
public class ProductController {

    @GetMapping("/{id}")
    public String detail(@PathVariable long id, Model model) {
        ProductDto product = productService.findById(id);
        model.addAttribute("product", product);
        model.addAttribute("pageTitle", "Product Information");
        return "products/detail";
    }
}
~~~

**This is an illustrative snippet inside a controller**, not a standalone program; `ProductDto` and `productService` need to be defined and injected. Notable points:

- `Model` **is an interface**; Spring supplies an instance to the method. You do not need to create `new Model()` yourself.
- `model.addAttribute("product", product)` creates an attribute with key `product`; the Thymeleaf view references it with `${product}`.
- `return "products/detail"` is a **logical view name**, not JSON and not a Java class name.
- Spring Boot + Thymeleaf by default looks for the corresponding template at `classpath:/templates/products/detail.html` if the template engine is configured.
- The controller must handle the case where `findById` does not find a product, for example by throwing an exception mapped to 404 or returning an appropriate error page. This example focuses on the model/view flow.

Commonly used methods of `Model`:

~~~java
model.addAttribute("title", "Product List");
model.addAttribute("count", 3);
model.addAttribute("items", items);
model.addAllAttributes(Map.of("category", "books", "sort", "name"));
Map<String, Object> snapshot = model.asMap();
~~~

These are illustrative statements placed inside a handler that has `model` and `items` variables. References are used in the view by attribute name. Use `addAttribute(String, Object)` to avoid convention-based naming surprises when adding an object without specifying an explicit key.

`Model` **does not hold a view name**. The return value or default view name mechanism determines which view to render.

## 5. `ModelMap`: Using the Model in `Map` Style

`ModelMap` is a class extending `LinkedHashMap<String, Object>`, providing both the Map API and model helper methods:

~~~java
@GetMapping("/summary")
public String summary(ModelMap model) {
    model.put("pageTitle", "Overview");
    model.addAttribute("total", 3);
    return "products/summary";
}
~~~

This is an illustrative handler in a `@Controller`; `ModelMap` must be imported. In the `products/summary.html` template, both attributes named `pageTitle` and `total` can be used.

Retrieval examples:

~~~java
Object total = model.get("total");
boolean contains = model.containsKey("pageTitle");
Map<String, Object> copied = new LinkedHashMap<>(model);
~~~

These are illustrative statements inside the same method with `ModelMap model`; `Map` and `LinkedHashMap` must be imported. When you do not need `put`, `get`, or `containsKey`, the `Model` interface usually expresses intent more clearly. Avoid putting sensitive entities, access tokens, or objects with very large object graphs into the model just because a Map allows storing any object.

**Do not confuse `ModelMap` with a `Map` returning JSON.** If an HTML handler returns a `Map` or `ModelMap` as its return value, Spring MVC may treat it as model attributes and **implicitly infer the view name**. If a REST handler uses `@ResponseBody`, the same `Map` type can instead be serialized to JSON. The controller annotation and return-value handling mechanism determine the behavior.

## 6. `ModelAndView`: Encapsulating View and Model

When you want to specify both the view and the data in the same place:

~~~java
@GetMapping("/detail")
public ModelAndView detail() {
    return new ModelAndView("products/detail")
            .addObject("product", new ProductDto(101L, "Spring MVC Book"))
            .addObject("pageTitle", "Product Details");
}
~~~

This is an illustrative method in a `@Controller` and requires defining `ProductDto`. `ModelAndView` allows:

- Passing the view name via the constructor `new ModelAndView("products/detail")` or `setViewName(...)`.
- Adding attributes with `addObject("key", value)` or `addAllObjects(map)`.
- Setting a `View` implementation directly via constructor/`setView(View)` instead of a logical name when needed.
- Setting an appropriate HTTP status using `setStatus(HttpStatus...)` in Spring Framework 6.x (this does not turn it into a `ResponseEntity`; the status still applies to the rendered view response).

Another style:

~~~java
ModelAndView mav = new ModelAndView();
mav.setViewName("products/detail");
mav.addObject("product", product);
mav.addObject("pageTitle", "Product Details");
return mav;
~~~

The lines above are also illustrative inside a method returning `ModelAndView`. If you omit the view name and no condition tells Spring the request has already been fully handled, the framework may fall back to a **default view name**, leading to unexpected results. Choose an explicit view name when code needs to be easy to verify.

**Example of setting a status for a view:**

~~~java
ModelAndView mav = new ModelAndView("errors/not-found");
mav.setStatus(HttpStatus.NOT_FOUND);
mav.addObject("message", "Product not found");
return mav;
~~~

A corresponding error template is required to render HTML. Changing the HTTP status to 404 does not automatically create a template; Spring still needs a view resolver and an actual resource. For REST APIs returning JSON, `ResponseEntity` or `ProblemDetail` is usually used instead of an HTML `ModelAndView`.

## 7. How Are Logical View Names Resolved?

Suppose a controller has:

~~~java
@GetMapping("/greeting")
public String greeting(Model model) {
    model.addAttribute("name", "Lan");
    return "hello";
}
~~~

Assuming the application includes `spring-boot-starter-thymeleaf`, Spring Boot usually auto-configures the Thymeleaf view resolver. By default:

~~~properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
~~~

The name `"hello"` is combined into `classpath:/templates/hello.html`. Place the file at:

~~~text
src/main/resources/templates/hello.html
~~~

A minimal template:

~~~html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org" lang="en">
<head><meta charset="UTF-8"><title>Demo</title></head>
<body>
  <h1 th:text="'Hello, ' + ${name}">Greeting</h1>
</body>
</html>
~~~

Thymeleaf processes `th:text` with the model value `name` and escapes the data for HTML context. This is an important security point: client-supplied data should not be embedded into raw HTML using unescaped string concatenation.

**A logical view name is not a file path on disk.** One view resolver may prepend/append a prefix/suffix, while another resolver may choose JSP or another view type. Do not build template paths directly from client parameters (`return userSuppliedViewName;`), as this can lead to displaying the wrong template or navigation risks.

### 7.1. Forms of View Names

| Handler returns | Interpretation in HTML `@Controller` |
| --- | --- |
| `"hello"` | Logical view name; resolver locates the template |
| `"products/detail"` | Logical view name inside a subdirectory |
| `"redirect:/products"` | Requests an HTTP redirect to URL `/products` |
| `"forward:/internal"` | Server-side forward to another path |
| `new ModelAndView("hello")` | View `hello` and attached model |
| `View` instance | Specifies the view directly, bypassing name resolution |
| `Model`/`Map` return value | Model is provided; view name is typically inferred from the request |

`redirect:` and `forward:` are specially recognized by view resolvers that support them (such as `UrlBasedViewResolver` and standard MVC configuration mechanisms). They are **not ordinary template names**.

### 7.2. Default View Name (`RequestToViewNameTranslator`)

If an HTML controller does not return a view name but provides a model and Spring has not considered the response fully handled, the framework can infer a view name from the request URI via `RequestToViewNameTranslator`, which defaults to `DefaultRequestToViewNameTranslator`.

For example, a `GET /pages/implicit` request may be interpreted as the view name `"pages/implicit"` under default rules. Spring then looks for the template `templates/pages/implicit.html`.

Implicit behavior depends on controller placement, routes, the translator, and resolver configuration. If you want to reduce reliance on convention, **return an explicit `String` view name**. Also avoid returning `void` from an HTML controller while expecting an always-empty body: it can trigger the **default view name**.

### 7.3. Why Doesn't `@RestController` Returning `"hello"` Look Up a Template?

~~~java
@Controller
class HtmlController {
    @GetMapping("/html")
    String html() {
        return "hello"; // Logical view name
    }
}

@RestController
class ApiController {
    @GetMapping("/api")
    String api() {
        return "hello"; // HTTP response body is the string hello
    }
}
~~~

This illustrative code contains two controllers (annotation imports required). `@RestController` is equivalent to `@Controller` combined with `@ResponseBody` on handler methods. With `@ResponseBody`, Spring passes the String through `HttpMessageConverter` rather than going through view resolution. To return an HTML template, choose `@Controller` and return a view name; to return JSON or text, choose `@RestController` or `@ResponseBody`.

## 8. Runnable Spring Boot 3.x Example: Model, ModelMap, ModelAndView, and Forms

Create a project using Spring Initializr:

- **Java:** 17 or higher.
- **Spring Boot:** 3.x branch.
- **Build:** Maven.
- **Dependencies:** Spring Web, Thymeleaf, Validation, Spring Boot Starter Test.

The corresponding starters are `spring-boot-starter-web`, `spring-boot-starter-thymeleaf`, `spring-boot-starter-validation`, and `spring-boot-starter-test`. The Java package uses `com.example.demo`. If using Spring Boot 4.x/Framework 7.x, verify imports and dependency configuration for your version.

File structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/PageController.java
src/main/resources/templates/demo.html
src/main/resources/templates/pages/implicit.html
src/main/resources/templates/registration.html
src/main/resources/templates/thanks.html
src/test/java/com/example/demo/PageControllerTest.java
~~~

### 8.1. Startup File

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 8.2. Complete Controller

**`src/main/java/com/example/demo/PageController.java`**

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.ui.ModelMap;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.servlet.ModelAndView;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/pages")
public class PageController {

    @GetMapping("/model")
    public String useModel(Model model) {
        model.addAttribute("title", "Model Example");
        model.addAttribute("message", "Data from Model");
        return "demo";
    }

    @GetMapping("/modelmap")
    public String useModelMap(ModelMap model) {
        model.put("title", "ModelMap Example");
        model.addAttribute("message", "Data from ModelMap");
        return "demo";
    }

    @GetMapping("/modelandview")
    public ModelAndView useModelAndView() {
        ModelAndView mav = new ModelAndView("demo");
        mav.addObject("title", "ModelAndView Example");
        mav.addObject("message", "Data from ModelAndView");
        mav.setStatus(HttpStatus.OK);
        return mav;
    }

    // No view name returned: MVC infers pages/implicit when using
    // DefaultRequestToViewNameTranslator and request /pages/implicit.
    @GetMapping("/implicit")
    public Model implicitView(Model model) {
        model.addAttribute("title", "Implicit View");
        model.addAttribute("message", "Data from default view");
        return model;
    }

    @GetMapping("/register")
    public String showRegistration(Model model) {
        model.addAttribute("registration", new RegistrationForm());
        return "registration";
    }

    @PostMapping("/register")
    public String submitRegistration(
            @Valid @ModelAttribute("registration") RegistrationForm form,
            BindingResult errors,
            RedirectAttributes redirectAttributes) {

        if (errors.hasErrors()) {
            return "registration";
        }

        redirectAttributes.addFlashAttribute("name", form.getName());
        return "redirect:/pages/thanks";
    }

    @GetMapping("/thanks")
    public String thanks() {
        return "thanks";
    }

    public static class RegistrationForm {
        @NotBlank
        private String name;

        public RegistrationForm() {
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }
}
~~~

Points to observe:

1. The first three handlers share the logical view **`"demo"`**; in the template, `title` and `message` are model attributes. The only difference is the API used to build the result.
2. `useModel` takes `Model`, `useModelMap` takes `ModelMap`; both return a `String` view name.
3. `useModelAndView` returns a `ModelAndView` with `viewName`, model, and status 200. `setStatus(OK)` here is for illustration and can usually be omitted since 200 is the success default.
4. `implicitView` returns `Model`; the framework infers `pages/implicit` under the default view-name translator configuration. This demonstrates the convention, **not the preferred approach in complex APIs**.
5. `showRegistration` puts `RegistrationForm` into the model. The Thymeleaf template uses it to bind the HTML form.
6. The POST handler receives the form via `@ModelAttribute`, applies Bean Validation with `@Valid`, and places `BindingResult` **immediately after** the form parameter to capture binding/validation errors.
7. If there are errors, it returns the `registration` view name, keeping the model and `BindingResult` so the template can display errors. If valid, it redirects following the **Post/Redirect/Get** pattern and uses `RedirectAttributes` to pass the flash attribute `name` to the next redirect request.
8. `@Controller` is required for handlers returning templates this way. Changing it to `@RestController` gives `String` return values HTTP body semantics, causing vastly different behavior.

### 8.3. Shared Template for All Three Approaches

**`src/main/resources/templates/demo.html`**

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title th:text="${title}">Spring MVC Example</title>
</head>
<body>
  <h1 th:text="${title}">Default Title</h1>
  <p id="message" th:text="${message}">Default Content</p>
</body>
</html>
~~~

When the controller returns `"demo"`, Thymeleaf reads `demo.html` and replaces `th:text` contents with the matching model attributes.

For example, calling `GET /pages/model` renders HTML containing:

~~~html
<h1>Model Example</h1>
<p id="message">Data from Model</p>
~~~

This is an illustrative excerpt extracted from the HTML, not the entire verbatim response (the response also contains `doctype`, `head`, and the remaining tags). Thymeleaf escapes text to reduce the risk of unwanted HTML injection from client data.

### 8.4. Template Using an Inferred View Name

**`src/main/resources/templates/pages/implicit.html`**

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title th:text="${title}">Implicit View</title>
</head>
<body>
  <h1 th:text="${title}">Title</h1>
  <p th:text="${message}">Content</p>
</body>
</html>
~~~

The URL path `/pages/implicit` typically maps to the logical view `pages/implicit` under the default translator. If you refactor the route without renaming the template or vice versa, you may encounter a "template not found" error. This is why handlers returning explicit view names are usually easier to maintain.

### 8.5. Form and Validation Template

**`src/main/resources/templates/registration.html`**

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Registration</title>
</head>
<body>
  <h1>Registration</h1>
  <form method="post" th:action="@{/pages/register}" th:object="${registration}">
    <label for="name">Name</label>
    <input id="name" type="text" th:field="*{name}">
    <p th:if="${#fields.hasErrors('name')}"
       th:errors="*{name}">Name error</p>
    <button type="submit">Submit</button>
  </form>
</body>
</html>
~~~

- `th:object="${registration}"` binds the template to the form object in the model.
- `th:field="*{name}"` gets or sets the `name` value on the object, supporting form re-display when validation fails.
- When the controller returns `"registration"` along with `BindingResult`, Thymeleaf can display errors using `#fields.hasErrors` and `th:errors`.
- Form data is user input: server-side validation is still necessary even when HTML has the `required` attribute.
- If using Spring Security with CSRF enabled, the form must carry a CSRF token according to your actual integration/configuration; do not disable CSRF just to make a form work.

### 8.6. Template After Redirect

**`src/main/resources/templates/thanks.html`**

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Registration Successful</title></head>
<body>
  <h1>Registration Successful</h1>
  <p th:if="${name}" th:text="'Hello, ' + ${name}">Greeting</p>
</body>
</html>
~~~

After a valid POST, `redirect:/pages/thanks` returns an HTTP redirect (typically 302 in this example), and then the browser sends a GET to `/pages/thanks`. `addFlashAttribute` holds the name in temporary flash storage for the next request. It **does not mean** every model attribute from POST automatically appears in the following GET.

In a real application, POST should persist data through a service before redirecting, and only put necessary display information into flash attributes. Flash attributes are stored temporarily (usually session-backed) and are not meant for long-term business data storage.

## 9. Calling the Application and Observing View Rendering

Run inside the directory containing `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

On Windows: `mvnw.cmd spring-boot:run`; if there is no wrapper and Maven is installed: `mvn spring-boot:run`.

The URLs:

~~~text
GET http://localhost:8080/pages/model
GET http://localhost:8080/pages/modelmap
GET http://localhost:8080/pages/modelandview
GET http://localhost:8080/pages/implicit
GET http://localhost:8080/pages/register
GET http://localhost:8080/pages/thanks
~~~

The first three URLs should render **the same `demo.html` file** with different displayed text:

| URL | `title` | `message` |
| --- | --- | --- |
| `/pages/model` | `Model Example` | `Data from Model` |
| `/pages/modelmap` | `ModelMap Example` | `Data from ModelMap` |
| `/pages/modelandview` | `ModelAndView Example` | `Data from ModelAndView` |

You can use `curl -i` to inspect the status, response headers, and HTML output:

~~~bash
curl -i http://localhost:8080/pages/model
curl -i http://localhost:8080/pages/modelmap
curl -i http://localhost:8080/pages/modelandview
~~~

The result is HTML (usually `Content-Type: text/html`), **not JSON**. With Thymeleaf, the entire `model` is used when the template evaluates `${...}` expressions.

Test a valid form submission:

~~~bash
curl -i -X POST http://localhost:8080/pages/register   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode "name=Lan"
~~~

The expected response is a **redirect** (typically 302) with header `Location: /pages/thanks` under standard configuration. `curl` does not retain and send session cookies across separate commands unless instructed; to observe the flash attribute after redirect, use a browser or `curl -L -c cookies.txt -b cookies.txt` with a cookie jar and proper redirect conditions. For session-backed flash attributes, do not assume a bare `curl -L` will always see the greeting.

To test validation errors, send an empty `name`:

~~~bash
curl -i -X POST http://localhost:8080/pages/register   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode "name="
~~~

The controller returns the **`registration` view** (typically HTTP 200 in this example) and the template displays the error at the `name` field, without redirecting. If your product requires HTTP 400 status for validation when rendering a form, you must explicitly set the appropriate status; `BindingResult` does not automatically enforce 400 when a handler chooses to re-render an HTML form.

## 10. Testing `Model`, `ModelMap`, and `ModelAndView` with MockMvc

With `spring-boot-starter-test` in the project, create **`src/test/java/com/example/demo/PageControllerTest.java`**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@WebMvcTest(PageController.class)
class PageControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void modelAddsDataAndReturnsViewName() throws Exception {
        mockMvc.perform(get("/pages/model"))
                .andExpect(status().isOk())
                .andExpect(view().name("demo"))
                .andExpect(model().attribute("title", "Model Example"))
                .andExpect(model().attribute(
                        "message", "Data from Model"));
    }

    @Test
    void modelMapAddsDataAndReturnsSameView() throws Exception {
        mockMvc.perform(get("/pages/modelmap"))
                .andExpect(status().isOk())
                .andExpect(view().name("demo"))
                .andExpect(model().attribute("title", "ModelMap Example"))
                .andExpect(model().attribute(
                        "message", "Data from ModelMap"));
    }

    @Test
    void modelAndViewCombinesDataAndView() throws Exception {
        mockMvc.perform(get("/pages/modelandview"))
                .andExpect(status().isOk())
                .andExpect(view().name("demo"))
                .andExpect(model().attribute(
                        "message", "Data from ModelAndView"));
    }

    @Test
    void implicitViewNameUsesDefaultTranslator() throws Exception {
        mockMvc.perform(get("/pages/implicit"))
                .andExpect(status().isOk())
                .andExpect(view().name("pages/implicit"))
                .andExpect(model().attribute(
                        "message", "Data from default view"));
    }

    @Test
    void formPageProvidesModelAttribute() throws Exception {
        mockMvc.perform(get("/pages/register"))
                .andExpect(status().isOk())
                .andExpect(view().name("registration"))
                .andExpect(model().attributeExists("registration"));
    }

    @Test
    void validFormUsesRedirectAndFlash() throws Exception {
        mockMvc.perform(post("/pages/register")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/pages/thanks"))
                .andExpect(flash().attribute("name", "Lan"));
    }

    @Test
    void invalidFormReturnsToViewWithFieldErrors() throws Exception {
        mockMvc.perform(post("/pages/register")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", ""))
                .andExpect(status().isOk())
                .andExpect(view().name("registration"))
                .andExpect(model().attributeHasFieldErrors(
                        "registration", "name"));
    }
}
~~~

Run the tests:

~~~bash
./mvnw test
~~~

The tests verify the exact separation between **view name** and **model attributes**. `view().name("demo")` verifies logical name selection; `model().attribute(...)` checks the data passed to the view. View resolver behavior can still depend on the template engine and test slice configuration, so keep the Thymeleaf dependency and templates present when running.

If you want to verify rendered HTML, you can add assertions with `content().string(containsString("Data from Model"))` and import Hamcrest matchers; this requires the view to actually be rendered. Production HTML applications need both controller tests and template integration tests to catch invalid template paths or syntax.

## 11. `@ModelAttribute` Populating the Model Before Rendering

Besides calling `model.addAttribute(...)` inside a handler, Spring MVC supports methods annotated with `@ModelAttribute` to prepare shared data:

~~~java
@Controller
@RequestMapping("/shop")
public class ShopController {

    @ModelAttribute("siteName")
    public String siteName() {
        return "Spring Store";
    }

    @GetMapping("/home")
    public String home(Model model) {
        model.addAttribute("pageTitle", "Home");
        return "shop/home";
    }
}
~~~

This is an illustrative class; imports are required. The `siteName()` method is not an HTTP endpoint; it populates the `siteName` attribute in the model before matching handlers are invoked. The `shop/home` template can use both `${siteName}` and `${pageTitle}`. You can place `@ModelAttribute` methods in `@ControllerAdvice` if data truly needs to be shared across multiple controllers.

**Avoid placing rapidly changing data or heavy database queries in an advice applied to all routes** unnecessarily; shared methods may be invoked on many requests. Do not use `@ModelAttribute` to inadvertently expose sensitive information in HTML views.

`@ModelAttribute` on a **handler parameter** instead serves to access/instantiate a target object and bind request values; it is not identical to a method-level `@ModelAttribute` that prepares the model.

## 12. View Names, Redirects, Forwards, and Model Data Lifecycle

### `return "redirect:/..."`

Used when the browser needs a **new request**. After a successful POST, redirecting prevents the browser from resubmitting the form on refresh. Regular model attributes should not be assumed to survive automatically into the new request. `RedirectAttributes` has two mechanisms:

- `addAttribute(...)`: typically used for URL template variables or query parameters during a redirect. Avoid putting passwords, tokens, or sensitive information in URLs.
- `addFlashAttribute(...)`: temporarily stores data for the post-redirect request (usually in a session flash map), suitable for confirmation notices or brief display state.

**Illustrative example independent of the controller in Section 8:**

~~~java
@PostMapping("/save")
public String save(RedirectAttributes attributes) {
    long id = 101L; // Assume the service created the resource.
    attributes.addAttribute("id", id);
    attributes.addFlashAttribute("notice", "Saved");
    return "redirect:/products/{id}";
}
~~~

When the browser navigates to `/products/101`, the flash value `notice` can be exposed in the target request's model. Do not store large objects or sensitive data in flash storage.

### `return "forward:/..."`

The server **internally forwards** the current request to another path using the servlet request dispatcher, typically without changing the browser's address bar URL and without requiring the browser to send a redirect request. Request attributes can continue to be used during the forward. Avoid infinite forward loops and only forward to routes or views that actually exist.

### Absolute Paths vs. Logical View Names

`"products/detail"` is a view name, not automatically the HTTP path `/products/detail`. Conversely, `"redirect:/products/detail"` specifies the target of an HTTP redirect. A template under `templates/products/detail.html` does not require an endpoint named `/products/detail`; any controller returning that logical view can render the template.

## 13. Model in Form Validation: When Does Invalid Data Stay?

With `@Valid @ModelAttribute("registration") RegistrationForm form, BindingResult errors`, Spring creates or retrieves the form object, binds input, runs validation, and puts error information into the model alongside the object. When the method returns `"registration"`, the view can read the submitted values and field-level errors. That is why the form can re-display input fields after an error.

- `BindingResult` must be placed **immediately after** the validated parameter so the handler receives errors for that target; otherwise, Spring may throw an exception or fail to associate errors as intended.
- `model.addAttribute("registration", ...)` on GET provides the initial form object. On an invalid POST, Spring normally already has that object from binding; do not recreate and overwrite it before re-rendering if you need to preserve user-entered values and errors.
- When using Thymeleaf, `th:object`, `th:field`, and `th:errors` connect the HTML form to the model and `BindingResult`.
- DTO validation only checks input format/constraints; actual persistence must go through a real service/repository and enforce authorization checks for the application context.

A single model can hold multiple form attributes. Avoid overly generic attribute names such as `"data"` for multiple forms on the same page, as templates and error binding become hard to distinguish.

## 14. When Should You Return `ModelAndView` Instead of `String`?

Both styles usually produce equivalent output:

~~~java
@GetMapping("/simple")
public String simple(Model model) {
    model.addAttribute("message", "Hello");
    return "hello";
}
~~~

~~~java
@GetMapping("/combined")
public ModelAndView combined() {
    return new ModelAndView("hello")
            .addObject("message", "Hello");
}
~~~

These are two illustrative methods in a controller that has a `hello.html` template. They can produce identical HTML; there is no general performance rule saying `ModelAndView` is always faster or slower than `Model`.

**Prefer `Model` + `String`** when the method is concise and reads naturally: "add attributes to the model, return the view name." **Prefer `ModelAndView`** when you need to bundle view/model/status in one return object, when handling HTML-oriented exceptions, or when a framework extension expects `ModelAndView`.

Returning `ModelAndView` does not require declaring a `Model` parameter; however, you may still have an implicit model from other mechanisms. Do not add the same data twice through both a model argument and `ModelAndView` unless intentional.

## 15. Common Pitfalls and Troubleshooting

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Browser displays literal text `demo` instead of HTML | Using `@RestController` or `@ResponseBody` | Switch to `@Controller` for handlers returning views |
| `TemplateInputException` or view not found | Logical view does not match template path/prefix/suffix | Check `templates/demo.html`, view name, and Thymeleaf dependency |
| Template renders but attributes are empty | Key mismatch between `addAttribute` and `${...}` | Compare property names, null values, and controller logic |
| Calling `model.put(...)` on a `Model` variable | `Model` is an interface without `put` | Use `addAttribute` or switch to `ModelMap` |
| Template hits a forward/redirect loop | Invalid routing logic or view name collides with route | Check return values, view resolver, and mappings |
| Notice disappears after POST/redirect | Regular model does not survive across a new HTTP request | Use `RedirectAttributes.addFlashAttribute` |
| Invalid form loses previously entered data | Overwriting the form object or improper binding setup | Keep `@ModelAttribute` + `BindingResult` and Thymeleaf `th:field` |
| `void` in an HTML controller renders an unexpected view | Spring applies the default view name | Return an explicit view name or handle the response clearly |
| Returning `Map` expecting JSON | Missing `@ResponseBody` or REST controller annotation | Use `@RestController` or `ResponseEntity` |
| User input becomes the template name | Building view names from untrusted client data | Whitelist view names and separate input from routing |
| View name test passes but page fails at runtime | MockMvc test did not verify actual template rendering | Add integration tests checking rendered HTML and resources |
| HTML is right but URL after POST stays on POST endpoint | Handler renders directly instead of redirecting | Use Post/Redirect/Get if the workflow requires it |

### Mistake: `Model` Is Not a JSON Response

~~~java
@GetMapping("/wrong")
public Model wrong(Model model) {
    model.addAttribute("message", "Hello");
    return model;
}
~~~

This is an **illustrative example inside an HTML `@Controller`**: Spring may treat the return value as the model and infer the view name from the URL. Do not use this pattern to return REST JSON. For REST endpoints, return a DTO/record from `@RestController` or `ResponseEntity<Dto>`.

### Mistake: Using Client Input Directly as the View Name

~~~java
@GetMapping("/show")
public String show(@RequestParam String template) {
    return template;
}
~~~

This is an **anti-pattern** and should not be used. Clients could manipulate template selection, redirects, or forwards. Map input to a fixed **server-side allowlist of view names**, such as an enum or a `switch` with a safe default.

## 16. Review Questions

**1. How do `Model` and `ModelMap` differ?**

`Model` is the model API interface; `ModelMap` is a Map-based class offering `put`, `get`, and `addAttribute`. Both hold attributes that the view reads during the request.

**2. Does the logical view name `"orders/list"` mean Spring accesses the URL `/orders/list`?**

No. It is a view name used by the resolver to find a rendering resource, such as `templates/orders/list.html`. Only prefixes like `redirect:` instruct the browser to navigate to another URL.

**3. When should you choose `ModelAndView`?**

When you want to return a result bundling the view, model, and sometimes status in one object. If you only need to add attributes and return a view name, `Model` + `String` is usually more concise.

**4. Why doesn't `@RestController` returning `"hello"` render `hello.html`?**

Because `@RestController` includes `@ResponseBody` semantics, so the String is written as the HTTP response body via a converter rather than resolved as a logical view name.

**5. When is the implicit default view name used?**

When an HTML handler does not specify a view name and the response is not yet considered fully handled. Spring can infer a view name from the request path via `RequestToViewNameTranslator`.

**6. Is a POST request's model automatically preserved for the GET after a redirect?**

No. That is a separate HTTP request. When you need to pass short messages across a redirect, use `RedirectAttributes.addFlashAttribute` and understand the flash lifecycle.

## 17. Practice Checklist

1. For HTML pages, use `@Controller`, return an explicit logical view name, and pass attributes via `Model` or `ModelMap`.
2. When logic requires bundling view + model + status, use `ModelAndView` with an explicit view name.
3. Confirm the ViewResolver matches your template type, path, prefix/suffix, and case-sensitive filenames on the target OS.
4. Test view names, model attributes, and rendered HTML. For forms, test GET form rendering, valid POST redirect, and invalid POST returning the view with field errors.
5. Control data sources passed into templates, rely on engine escaping, and avoid building view names from client input.
6. Distinguish `redirect:`, `forward:`, implicit views, `@ResponseBody`, and `@RestController`.
7. Keep the model strictly for presentation data; do not confuse it with repositories, entities, or long-term storage.

## Official Documentation

- [Spring Framework 6.2 — Controller Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/return-types.html)
- [Spring Framework 6.2 — Controller Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework 6.2 — `@ModelAttribute` methods](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-modelattrib-methods.html)
- [Spring Framework 6.2 — Redirect Attributes](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html)
- [Spring Framework — View Resolvers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/viewresolver.html)
- [Spring Boot — Template Engines and MVC Views](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
