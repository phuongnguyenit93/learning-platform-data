# @Controller, @RestController, and Controller Detection in Spring Web

In Spring Web, a **controller** is a Spring object (bean) that participates in receiving HTTP requests, invoking business logic, and deciding the returned result. The two most common annotations are **@Controller** and **@RestController**. Both identify a class as having a controller role, but **differ in how Spring interprets the return value from a handler method**.

This lesson belongs to the **Request Routing** group, so we need to distinguish two steps that happen before a request reaches a method: **Spring discovers/registers the controller as a bean**, and then **Spring MVC registers the request mappings** of eligible beans. Annotating a class is only a condition for the framework to recognize it; the controller must also reside in the ApplicationContext serving the request and have mapped methods.

Objectives after this lesson:

- Accurately distinguish **@Component, @Controller, @RestController, and @ResponseBody**.
- Explain why a @RestController class can exist yet calling its URL still returns **404**.
- Describe the mechanism **component scan → bean definition → controller detection → handler mapping → request dispatch**.
- Choose **view name** or **response body** appropriately according to application requirements.
- Organize packages, declare mappings, and verify with a runnable Spring Boot MVC example.
- Know the limits of controller detection when using hierarchical contexts, proxies, and different web stacks.

## 1. Where Does a Controller Sit in Spring MVC?

An HTTP request is not routed directly to a method simply because the method name resembles a URL. Spring MVC goes through **DispatcherServlet**, selects a handler via **HandlerMapping**, then invokes the handler using **HandlerAdapter** and handles the return value.

~~~text
Client HTTP request
       |
Servlet container / Servlet filter chain
       |
DispatcherServlet
       |
RequestMappingHandlerMapping
       |      (detected and registered controller mappings)
       v
Select handler by path, HTTP method,
Content-Type, Accept, params, headers...
       |
RequestMappingHandlerAdapter
       |-- resolve arguments: @PathVariable, @RequestParam,
       |   @RequestBody, Model, Servlet request, ...
       v
@Controller / @RestController handler method
       |
       +-- Model + view name -> ViewResolver -> HTML
       |
       +-- @ResponseBody / @RestController
       |      -> HttpMessageConverter -> JSON/text/...
       |
       +-- ResponseEntity -> status + headers + body
       |
HTTP response
~~~

This is the simplified flow of **Spring MVC on the Servlet stack**. With Spring WebFlux, the familiar controller annotations are still supported, but the underlying infrastructure is WebFlux HandlerMapping/HandlerAdapter, **DispatcherHandler**, and reactive codecs. The discovery/controller mapping approach shares similar ideas, while the I/O model differs.

**Two steps that must not be merged into one:**

1. **Bean discovery/registration:** the Java class is brought into the Spring ApplicationContext as a bean.
2. **Request mapping registration:** Spring MVC inspects controller beans, looks for @RequestMapping or @GetMapping/@PostMapping..., and registers the corresponding HTTP conditions.

A class can be a Spring bean but **not an HTTP controller**; a class with @Controller that is **not registered as a bean in the right context** cannot serve requests either.

## 2. What Is @Controller?

**@Controller** belongs to the **org.springframework.stereotype** package. It is a stereotype annotation marking a web component type, meta-annotated with **@Component**, so it falls into the default group that Spring component scan can detect.

~~~java
package example.web;

import org.springframework.stereotype.Controller;

@Controller
public class HomeController {
}
~~~

This only **declares a potential controller bean**, with no endpoints yet: there is no @GetMapping or any other mapping.

When adding a handler:

~~~java
@Controller
public class HomeController {

    @GetMapping("/home")
    public String home() {
        return "home";
    }
}
~~~

This snippet is **illustrative**, not standalone: it still needs @GetMapping imported, an MVC context, a view resolver, and a template/view named **home**. In traditional Spring MVC, the String value **"home"** is interpreted as a **view name** for ViewResolver to resolve. If a matching template exists, the view will be rendered into HTML.

### Not Every Return Value of @Controller Is a View Name

With @Controller, Spring MVC has multiple return-value handlers. The outcome depends on **annotations on the method, the return data type, and the MVC configuration**:

- **String** or **View** in a regular handler: usually represents a view name or View.
- **ModelAndView**: explicitly specifies both view and model.
- **Model** or **@ModelAttribute**: used for model data following MVC rules.
- **@ResponseBody**: writes the return value into the HTTP response body.
- **ResponseEntity<T>**: carries status, headers, and body, and can write the body **even when the class only uses @Controller**.
- **redirect:** or **forward:** in a view name: creates a redirect/forward via the view resolution mechanism.

Therefore, you should not conclude that "@Controller can never return JSON". @Controller **can return JSON**; you just need to use the appropriate return type or annotation for writing the response body.

## 3. What Is @RestController?

**@RestController** belongs to the **org.springframework.web.bind.annotation** package and is a **composed annotation** with two main meanings:

~~~text
@RestController
    ≈ @Controller
    + @ResponseBody at class level
~~~

The ≈ symbol indicates **equivalence in primary semantics**, not a complete definition of every attribute of the annotation.

~~~java
package example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/api/status")
    public Status status() {
        return new Status("ok");
    }

    public record Status(String value) {
    }
}
~~~

This is an **illustrative controller snippet** requiring an MVC/Boot ApplicationContext and an appropriate JSON converter, not a standalone runnable Java program. If registered and Jackson supports records, the endpoint returns a JSON body equivalent to:

~~~json
{"value":"ok"}
~~~

Unlike @Controller returning a view name, handlers in @RestController have **@ResponseBody** semantics by default: objects are converted into an HTTP representation via **HttpMessageConverter**s (MVC) instead of being passed to a ViewResolver.

### Brief Comparison

| Criterion | @Controller | @RestController |
|---|---|---|
| Belongs to Spring stereotypes | Yes; meta-annotated with @Component | Yes; meta-annotated with @Controller and @ResponseBody |
| Detected by component scan | Yes when within scan scope and matching filters | Yes under the same conditions |
| Can contain @GetMapping/@PostMapping | Yes | Yes |
| Default returned String | Usually a **view name** | **Response body** String |
| Default JSON object return | Requires @ResponseBody/ResponseEntity or appropriate mechanism | Via response body converter when JSON is supported |
| Using Model + HTML template | Fits naturally | Not suitable if you want String to be interpreted as a view name |
| Using for REST API | Possible, if @ResponseBody is added | Common and convenient |
| Creates a server/URL by itself? | No | No |
| Any difference in package scanning? | Negligible at the stereotype level | Negligible at the stereotype level |

**Choose by return semantics:** server-side HTML templates typically use @Controller; JSON/text APIs typically use @RestController. Both can coexist in the same Spring MVC application.

## 4. @ResponseBody Is the Key Difference

**@ResponseBody** instructs the framework to treat the return value as the **HTTP response body**. It can be placed on a **method** or a **class**.

For the same goal of returning a JSON API, the two approaches below are nearly equivalent:

~~~java
@Controller
public class ProfileController {

    @ResponseBody
    @GetMapping("/api/profile")
    public Profile profile() {
        return new Profile(7, "An");
    }

    public record Profile(int id, String name) {
    }
}
~~~

~~~java
@RestController
public class ProfileController {

    @GetMapping("/api/profile")
    public Profile profile() {
        return new Profile(7, "An");
    }

    public record Profile(int id, String name) {
    }
}
~~~

**These are two alternative versions**; you must not create two classes with the same name/mapping simultaneously in one project. You need annotation imports, Spring Web dependency, and a suitable JSON converter.

Both return a serialized object, for example:

~~~json
{"id":7,"name":"An"}
~~~

In Spring MVC, **RequestResponseBodyMethodProcessor** is one of the mechanisms handling this return style and coordinates **HttpMessageConverter**s with media types. The JSON converter usually comes from Jackson. If the project has no converter supporting the return type and media type, Spring cannot automatically produce JSON merely because @RestController is present.

### An Easily Confused String Case

~~~java
@Controller
class HtmlController {

    @GetMapping("/welcome")
    public String welcome() {
        return "welcome";
    }
}
~~~

Spring MVC may look for the **welcome** view; a configured template/view is required. Whereas:

~~~java
@RestController
class TextController {

    @GetMapping("/welcome")
    public String welcome() {
        return "welcome";
    }
}
~~~

Spring MVC writes the plain text body **welcome** (if the mapping matches), **without looking for a welcome template**. The two examples are **separate choices**; do not create the same URL in one app unless you intentionally distinguish them by other conditions.

A common mistake is changing a @Controller class to @RestController to "fix a 404" and then seeing the browser display the word **home** instead of an HTML page. In that case, the cause is **changing how the return value is handled**, without necessarily fixing scanning/mapping.

### ResponseEntity Is a Special Case

~~~java
@Controller
class HealthController {

    @GetMapping("/check")
    public ResponseEntity<String> check() {
        return ResponseEntity.ok()
                .header("X-Check", "passed")
                .body("OK");
    }
}
~~~

**You must import** @Controller, @GetMapping, and **org.springframework.http.ResponseEntity** when putting this illustrative method into a project. ResponseEntity is handled by MVC as a special return type, so **@ResponseBody is not needed** on the method to write the body "OK". Result: status 200, X-Check: passed, body OK.

However, using @RestController usually communicates intent more clearly when the entire class contains only API endpoints.

## 5. Controller Detection Mechanism: From Class to Bean

### Step A — Spring Finds Candidate Components

In Java configuration, for example:

~~~java
@Configuration
@ComponentScan("example.web")
class WebConfig {
}
~~~

This is a **configuration snippet**, requiring imports for @Configuration and @ComponentScan. During ApplicationContext startup, Spring scans classes with matching stereotypes under **example.web** and its subpackages according to component scanning rules. Spring uses class metadata to identify candidates and register **BeanDefinition**s.

By default, annotations in the **@Component** family such as **@Service**, **@Repository**, **@Controller**, **@Configuration**, and **@RestController** (via meta-annotations) can be detected.

**That means:** @RestController is detected because it **indirectly carries @Component**, not because Spring Boot continuously searches for any class name ending in "Controller".

For example:

~~~text
example/
  web/
    StatusController.java       <-- @RestController, inside scan scope
  service/
    GreetingService.java        <-- @Service, outside "example.web"
  another/
    OtherController.java        <-- @Controller, outside "example.web"
~~~

If configuration only scans **example.web**, the two classes outside this package are not automatically brought into the context by that scan. They can still be registered manually or through other configuration, but **you must not assume they were scanned**.

### Step B — BeanDefinition Is Created, Bean Is Instantiated

After identifying a component, Spring stores the bean configuration and performs instantiation, dependency resolution, and lifecycle steps according to the bean type and scope. A bean can be:

- Scanned by **@ComponentScan** or **context:component-scan** in XML.
- Registered via **@Bean** in a @Configuration class.
- Imported from another configuration using **@Import**.
- Registered programmatically via the ApplicationContext/registry API.

**@Controller does not force you to use component scan.** A controller object can be registered in other ways, as long as Spring MVC sees it as a valid controller bean in the right context.

### Step C — Spring MVC Identifies Which Beans Are Handlers

When the MVC infrastructure initializes, **RequestMappingHandlerMapping** (or the corresponding mapping infrastructure) looks for bean types considered **handlers**, typically types annotated with **@Controller**, including via meta-annotations such as @RestController. The framework inspects methods annotated with @RequestMapping or composed mappings such as @GetMapping, @PostMapping.

For example:

~~~java
@Service
class LibraryService {

    @GetMapping("/books")
    public String list() {
        return "data";
    }
}
~~~

This is an **example illustrating a design mistake**. Even though @Service is scanned as a bean and the method has @GetMapping, Spring MVC **does not treat it as an annotated controller just because of @GetMapping**. Do not put handler annotations on @Service expecting endpoints to be created automatically. Have a @Controller/@RestController call the service and map the URL.

### Step D — Registering Mappings

A handler method typically produces metadata containing:

- URL path/pattern.
- HTTP method: GET, POST, PUT, DELETE, PATCH...
- **params**: query/form parameter conditions, if any.
- **headers**: other header conditions, if any.
- **consumes**: media type of the request body.
- **produces**: response media type accepted by the client.
- Custom conditions or API version requirements depending on configuration/framework version.

Mappings combine conditions at the **class level** and **method level**. If two duplicate mappings cannot be distinguished in the same environment, the application may throw an **Ambiguous mapping** error at startup; overlapping mappings with different specificity may only cause ambiguity at request time, depending on configuration.

### Step E — DispatcherServlet Dispatches the Request

When a request arrives, Spring evaluates registered mappings, selects the appropriate handler method, binds method arguments, invokes the controller, and processes the result. **It does not re-scan the entire classpath to look for controllers on every request**.

This explains why editing source code and saving the file does not make a new endpoint appear in a running Java process if the project lacks a corresponding reload/restart mechanism.

## 6. How Does Spring Boot Detect Controllers?

In Spring Boot, **@SpringBootApplication** bundles necessary mechanisms such as **@SpringBootConfiguration**, **@EnableAutoConfiguration**, and **@ComponentScan**. By default, component scanning starts from **the package containing the main application class** and its subpackages.

Recommended structure:

~~~text
src/main/java/
  com/example/shop/
    ShopApplication.java         <-- @SpringBootApplication
    web/
      ProductRestController.java <-- @RestController
      HomeController.java        <-- @Controller
    service/
      ProductService.java        <-- @Service
    config/
      WebConfiguration.java      <-- @Configuration
~~~

Because ShopApplication is in **com.example.shop**, all matching subpackages fall within the default scan scope.

**Error example:**

~~~text
src/main/java/
  com/example/shop/bootstrap/
    ShopApplication.java       <-- @SpringBootApplication
  com/example/shop/web/
    ProductRestController.java <-- @RestController
~~~

In that case, the default scan package is **com.example.shop.bootstrap** and its subpackages; **com.example.shop.web** is a sibling package and is outside the scan. The application may still start the HTTP server, yet a GET to ProductRestController's mapping returns **404**.

**Sensible fixes:**

- Move ShopApplication up to **com.example.shop** (a clean and maintainable structure).
- Or when there is a genuine reason, explicitly configure scanning with @SpringBootApplication(scanBasePackages = "com.example.shop") or an appropriate @ComponentScan. When changing the scan scope, remember that other parts like entity/repository scanning have their own mechanisms; do not assume adjusting component scan is enough for every type of metadata.

**Avoid placing the main class in the default package (no package declaration)**: Spring Boot warns that this structure can cause overly broad classpath scanning that is hard to control. Use a clearly named Java package.

### Component Scan Does Not Mean @EnableWebMvc

- **@ComponentScan** discovers and registers beans such as controllers/services.
- **@EnableWebMvc** enables Java MVC configuration in **plain Spring MVC**.
- **Spring Boot MVC auto-configuration** conditionally sets up the MVC infrastructure/DispatcherServlet, so Boot normally **does not need @EnableWebMvc**.

A project can scan @Controller beans yet lack a DispatcherServlet/web infrastructure or required dependencies. Conversely, servlet MVC may be running, yet failing to scan controllers means no corresponding mappings exist. When debugging, you must verify **both layers**.

## 7. Complete Spring Boot MVC Example: HTML and JSON Running Together

This example helps distinguish **@Controller → Thymeleaf view** and **@RestController → JSON** within **the same application**. Use **Java 17+**, Maven, Spring Initializr at **https://start.spring.io/** and select dependencies:

1. **Spring Web** to run Spring MVC.
2. **Thymeleaf** to render HTML templates.
3. Optionally add **Spring Boot DevTools** in development, though it is not required.

Use a Spring Boot version supported by Initializr and a compatible JDK. **Do not use Spring Reactive Web** for this Servlet MVC example. Across Boot versions, the MVC starter artifact name may differ (Boot 3.x commonly uses spring-boot-starter-web, Boot 4.x uses spring-boot-starter-webmvc); select via Initializr to get the right configuration.

Create the base package **example.discovery** in the project. Files:

~~~text
src/main/
  java/example/discovery/
    DiscoveryApplication.java
    service/GreetingService.java
    web/PageController.java
    web/GreetingRestController.java
    web/MixedController.java
  resources/
    templates/greeting.html
~~~

### 7.1. Main Application Class

**src/main/java/example/discovery/DiscoveryApplication.java**

~~~java
package example.discovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiscoveryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DiscoveryApplication.class, args);
    }
}
~~~

**Why place it here:** the main class belongs to **example.discovery**, above **example.discovery.web** and **example.discovery.service**, so default Spring component scan can detect controllers and services. No custom @ComponentScan is needed.

### 7.2. Service Containing Only Business Logic

**src/main/java/example/discovery/service/GreetingService.java**

~~~java
package example.discovery.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

The service is a Spring bean but **declares no HTTP endpoints**. Separating logic into a service allows both the HTML controller and JSON controller to share it without duplicating business logic.

### 7.3. HTML Controller: @Controller and Model

**src/main/java/example/discovery/web/PageController.java**

~~~java
package example.discovery.web;

import example.discovery.service.GreetingService;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class PageController {

    private final GreetingService greetingService;

    public PageController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public String greetingPage(
            @RequestParam(defaultValue = "An") String name,
            Model model) {
        model.addAttribute("message", greetingService.greet(name));
        return "greeting";
    }
}
~~~

Key points:

- **@Controller** makes the class a controller bean.
- **@GetMapping("/greeting")** registers HTTP GET /greeting.
- **@RequestParam** reads a query parameter; defaultValue is used when no name is passed.
- **Model** holds the message value for the view.
- **return "greeting"** is a **logical view name**, resolved by the Thymeleaf view resolver to template **templates/greeting.html**, not the literal body text "greeting".

**src/main/resources/templates/greeting.html**

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Spring Controller Example</title>
</head>
<body>
    <h1 th:text="${message}">Message</h1>
</body>
</html>
~~~

Thymeleaf replaces the h1 content with the message present in the Model. **th:text** HTML-escapes the displayed data, which is appropriate for text from requests. Avoid using th:utext for untrusted data because of the risk of HTML/script injection if uncontrolled.

### 7.4. JSON API Controller: @RestController

**src/main/java/example/discovery/web/GreetingRestController.java**

~~~java
package example.discovery.web;

import example.discovery.service.GreetingService;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingRestController {

    private final GreetingService greetingService;

    public GreetingRestController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping(path = "/{name}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public GreetingResponse byName(@PathVariable String name) {
        return new GreetingResponse(greetingService.greet(name));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public GreetingResponse create(@RequestBody GreetingRequest request) {
        return new GreetingResponse(
                greetingService.greet(request.name()));
    }

    public record GreetingRequest(String name) {
    }

    public record GreetingResponse(String message) {
    }
}
~~~

Because @RestController already includes @ResponseBody at the class level, the GreetingResponse object is serialized by the JSON message converter. **@RequestMapping** on the class combines with **@GetMapping** and **@PostMapping** on the methods. The example above has two distinct HTTP mappings:

~~~text
GET  /api/greetings/{name}
POST /api/greetings
~~~

**@ResponseStatus(HttpStatus.CREATED)** makes the POST response status **201** on success. **consumes** restricts the request Content-Type; **produces** specifies the response media type. This simple version does not validate null/blank name fields; a production API should add DTO validation and error handling according to its contract.

### 7.5. @Controller Still Returns a Response Body When Needed

**src/main/java/example/discovery/web/MixedController.java**

~~~java
package example.discovery.web;

import example.discovery.service.GreetingService;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class MixedController {

    private final GreetingService service;

    public MixedController(GreetingService service) {
        this.service = service;
    }

    @ResponseBody
    @GetMapping(path = "/text",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String greetingText(
            @RequestParam(defaultValue = "An") String name) {
        return service.greet(name);
    }

    @GetMapping(path = "/headers",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> greetingWithHeader() {
        return ResponseEntity.ok()
                .header("X-Source", "controller")
                .body("Result from ResponseEntity");
    }
}
~~~

Both methods in the @Controller class **bypass templates**: /text has @ResponseBody, and /headers returns ResponseEntity. This proves @Controller is not limited to HTML.

### 7.6. Run and Verify Each Endpoint

In the Spring Initializr project root directory (where pom.xml is located), run:

~~~bash
# macOS/Linux
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

The MVC server listens on **http://localhost:8080** by default, unless the project changes server.port. Open another terminal:

**A. HTML view**

~~~bash
curl -i "http://localhost:8080/greeting?name=Lan"
~~~

Expect status **200**, HTML Content-Type, and a body containing:

~~~html
<h1>Hello, Lan!</h1>
~~~

The actual HTML includes head/body tags and whitespace from the template; the above is the **key fragment to verify**, not the entire byte-for-byte response.

**B. JSON API**

~~~bash
curl -i -H "Accept: application/json" \
  "http://localhost:8080/api/greetings/Lan"
~~~

Expected JSON body (in terms of content):

~~~json
{"message":"Hello, Lan!"}
~~~

If the JSON serializer escapes Unicode characters, JSON strings with different escape representations can still represent **the same message value**.

**C. POST JSON**

~~~bash
curl -i -X POST "http://localhost:8080/api/greetings" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"name":"Minh"}'
~~~

Expect status **201 Created** and JSON body:

~~~json
{"message":"Hello, Minh!"}
~~~

If you send Content-Type: text/plain when the mapping only consumes JSON, Spring MVC typically returns **415 Unsupported Media Type**. If you send malformed JSON, it may return **400 Bad Request**. Do not confuse receiving a JSON body via @RequestBody with the class being annotated with @RestController.

**D. Plain text from @Controller + @ResponseBody**

~~~bash
curl -i -H "Accept: text/plain" \
  "http://localhost:8080/text?name=Mai"
~~~

Expected body:

~~~text
Hello, Mai!
~~~

This is **not a view name**, thanks to @ResponseBody.

**E. ResponseEntity from @Controller**

~~~bash
curl -i "http://localhost:8080/headers"
~~~

Expect status **200**, response header:

~~~http
X-Source: controller
~~~

And body:

~~~text
Result from ResponseEntity
~~~

If running the example on older Windows PowerShell, you can use **curl.exe** instead of the curl alias to be sure you invoke the real curl tool. When running multiple Spring Boot demos simultaneously, make sure port 8080 is not already occupied.

## 8. When Component Scan Misses a Controller: An Experiment

From the project above, if you move DiscoveryApplication.java to package **example.discovery.bootstrap** while keeping controllers in **example.discovery.web**, the structure becomes:

~~~text
example.discovery.bootstrap.DiscoveryApplication
example.discovery.web.PageController
example.discovery.web.GreetingRestController
example.discovery.web.MixedController
example.discovery.service.GreetingService
~~~

Changing only the package/path of the main class without changing the scan scope causes Boot by default to scan **example.discovery.bootstrap** and its subpackages. The sibling **web** and **service** beans fall outside that scope. The application may start, yet lack the expected endpoints; GET requests to /api/greetings/Lan or /greeting typically return **404**.

**How to fix:** move the main class back to package **example.discovery**. This is the simplest structure and usually preferred.

A situation-dependent alternative is declaring:

~~~java
@SpringBootApplication(scanBasePackages = "example.discovery")
public class DiscoveryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DiscoveryApplication.class, args);
    }
}
~~~

This is an **alternative version of the main class**; do not create two DiscoveryApplication classes simultaneously. The annotation parameter resolves the component scan scope for the example; in projects with JPA entities or Spring Data repositories, you may also need to separately consider @EntityScan/@EnableJpaRepositories scopes and package structure.

### Other Reasons a Controller Is Not Found

- The class lacks @Controller/@RestController or an appropriate meta-annotated custom annotation.
- The controller has the right stereotype annotation but is not a bean in the **DispatcherServlet ApplicationContext** handling the request.
- @ComponentScan has **excludeFilters**, or **useDefaultFilters=false** causing the class to be excluded.
- Conditional bean registration (**@Profile**, **@Conditional...**) is not satisfied.
- The controller is not included in the runtime classpath/artifact, or stale code was compiled.
- There are multiple DispatcherServlets or multiple ApplicationContexts, and the controller resides in a context not visible from the servlet serving the request.
- The handler method lacks @RequestMapping or a composed HTTP mapping, so the controller bean provides no endpoints.
- The URL you call has the wrong context path, servlet mapping, @RequestMapping prefix, HTTP method, or is blocked by a filter/security/proxy before reaching MVC.

**Diagnose by layer:** first confirm whether the bean exists, then confirm whether the mapping is registered, and finally compare against the actual HTTP request.

## 9. From Discovered Controller to Exact Mapping

**Recognizing a bean and routing an endpoint are two separate tasks.** After Spring finds a controller, `RequestMappingHandlerMapping` registers method metadata. A class-level prefix like `@RequestMapping("/api/books")` combines with `@GetMapping("/{id}")` to form `GET /api/books/{id}`; `@PostMapping` on that same class can share the path `/api/books` while differing in HTTP method.

The sample controllers in section 7 demonstrated GET with a URI variable, POST accepting JSON, response status, and media types. When running the application, you should also check the following scenarios:

| Symptom | Next question |
| --- | --- |
| HTTP 404 | Was the bean/controller scanned, does the method have a mapping, and does the URL match the prefix/context path? A handler may also intentionally return 404 for a missing resource. |
| HTTP 405 | Does the path already have a handler, but the request used the wrong HTTP method? |
| HTTP 406 | Does the `Accept` header match the response `produces` and available converters? |
| HTTP 415 | Does the request `Content-Type` match `consumes` and body-reading converters? |
| Startup reports `Ambiguous mapping` | Did two handlers register identical method/path/params/headers/media type conditions? |

A controller bean may have many handler methods, or none at all. Duplicate mappings must not be fixed merely by renaming Java methods: you must change HTTP conditions according to the API contract. When comparing competing URI patterns, rely on mapping specificity rather than declaration order.

This section only bridges **controller discovery** and routing. Subsequent lessons in this chapter dive specifically into class/method-level mappings, condition combinations, URI patterns, ambiguity, and status codes; there is no need to repeat the same demo application at every conceptual level.

## 10. How Does an MVC Annotated Controller Differ from a Servlet or Functional Endpoint?

Spring MVC still allows writing lower-level HTTP Servlets, registering Servlets directly, or using **RouterFunction** functional endpoints. Therefore, "a Spring Web application has endpoints" does not mean every endpoint lives in a @Controller.

| HTTP handler type | Registration method | Managed by Spring MVC RequestMappingHandlerMapping as an annotated controller? |
|---|---|---|
| @Controller + @GetMapping | Controller bean + mapping annotation | Yes |
| @RestController + @GetMapping | Controller bean + mapping annotation | Yes |
| A @Service with @GetMapping | Service bean without controller stereotype | No, @GetMapping alone is not enough |
| Custom Servlet | Servlet registration/mapping | Not an annotated controller mapping |
| Spring MVC functional RouterFunction | RouterFunction bean | Goes through functional routing infrastructure, not @GetMapping |
| Spring WebFlux annotated controller | Reactive application context + reactive mapping | Uses WebFlux infrastructure, not MVC DispatcherServlet |
| Spring WebFlux functional route | WebFlux RouterFunction<ServerResponse> | Goes through WebFlux functional routing |

**Note specifically:** @RestController does not mean "using Spring WebFlux". It works in both **Spring MVC** and **Spring WebFlux**, depending on the active dependencies, ApplicationContext, and web stack. To know whether the real server uses Servlet or reactive, inspect the actual runtime and configuration.

## 11. Bean Lifecycle, Dependency Injection, and Controller Architecture

Because a controller is a **Spring bean**, it participates in Dependency Injection, scope, lifecycle, and can be affected by BeanPostProcessors.

In the runnable example, both PageController and GreetingRestController receive GreetingService via **constructor injection**. Spring resolves a GreetingService bean and injects it into the controller. If no compatible bean exists, context creation typically fails with a dependency injection error instead of silently creating an endpoint without business logic.

### Why Is Constructor Injection a Good Choice?

- Dependencies are explicitly declared right in the constructor.
- Easy to instantiate the controller in unit tests with a fake service.
- Fields can be final, avoiding uninitialized state.
- No need to rely on field injection and runtime reflection to populate individual fields.

### Thread-Safety and Scope

Controller beans are usually **singleton** by default. Multiple requests can invoke **the same controller instance** concurrently across multiple threads (in MVC/Servlet).

**Bug you should not write:**

~~~java
@RestController
class UnsafeController {

    private String currentName;

    @GetMapping("/unsafe")
    public String unsafe(@RequestParam String name) {
        currentName = name;
        return currentName;
    }
}
~~~

This illustrates a **concurrent state bug**, which can cause one request to return another request's value. Controllers should not hold mutable request-specific fields. Request data should live in **local variables**, method parameters, or a properly managed scope/context mechanism.

A singleton controller does not prevent a service from having independent state, though services must also be designed thread-safe if they are singletons. @RestController does not make an application thread-safe automatically.

### Validation and Layering

Controllers are responsible for **HTTP translation**: reading path/query/body, applying appropriate validation, calling services, and choosing status/response. Business logic and transactions usually belong in services. Do not cram database queries, sending emails, or long processing strategies into a controller when they can be extracted into dedicated components.

A production API typically adds:

- Input/output DTOs and validation (@Valid with a compatible provider).
- @ControllerAdvice/@RestControllerAdvice to standardize error handling.
- Authentication/authorization in the filter/security chain.
- Logging/tracing, payload limits, and timeouts.
- Tests for mappings, content types, and status codes.

**@ControllerAdvice is not a regular controller endpoint.** It applies exception handlers and binder/model methods to matching controllers. **@RestControllerAdvice** is equivalent to @ControllerAdvice with @ResponseBody semantics for exception response handlers; it does not create a REST route just because RestController is in the annotation name.

## 12. Custom Stereotypes and How Spring Recognizes Meta-Annotations

Because @Controller is a stereotype meta-annotated with @Component, a custom annotation can express project intent by meta-annotating it:

~~~java
package example.discovery.web;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.stereotype.Controller;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Controller
public @interface WebPage {
}
~~~

This is a **complete Java annotation** (file **WebPage.java**), recognized by Spring as a controller stereotype if component scanning and metadata processing follow appropriate configuration.

Usage:

~~~java
@WebPage
public class WelcomePageController {

    @GetMapping("/legacy-home")
    public String home() {
        return "greeting";
    }
}
~~~

This class snippet is an **illustrative example** requiring imports for WebPage/@GetMapping, the greeting view, and an MVC context as above.

**Key difference:** a custom stereotype carrying **@Controller** inherits controller semantics; a custom stereotype carrying only **@Component** without @Controller is normally scanned as a bean but **is not enough to be treated as an annotated MVC controller**.

When creating custom annotations, avoid adding unnecessary abstraction layers for small projects. If you need to alias annotation attributes, check **@AliasFor** and meta-annotation declaration rules in your Spring version; do not arbitrarily add fields and assume they will be forwarded.

## 13. Proxies, Contexts, and Hard-to-Detect Controller Cases

### Controller Bean Wrapped in an AOP Proxy

Spring may use AOP proxies to implement transactions, security, or advice. For a controller implementing an interface with a JDK proxy, handler detection might not see annotations on the concrete class the way you expect. Spring documentation recommends **class-based proxying** for controllers when AOP proxies are needed.

Do not try to work around this by adding @RestController to every method or putting controller mappings on a service. Identify the **actual proxy type**, annotation placement, AOP configuration, and framework version; configure class-based proxying appropriately when needed. With Spring 6+, check the version-specific Javadoc regarding interface annotations/proxies.

### Root Context and DispatcherServlet Context

A traditional Servlet application may create:

~~~text
Root WebApplicationContext:
   Service, Repository, security-related infrastructure...
      |
      | parent referenced by child
      v
DispatcherServlet child WebApplicationContext:
   Controller, HandlerMapping, HandlerAdapter, ViewResolver...
~~~

**The child context can see beans in the parent**; the parent cannot automatically see beans that exist only in the child. In traditional Spring MVC, controllers are usually placed in the corresponding DispatcherServlet's context. If multiple DispatcherServlets are created, each servlet can have its own mappings and controller context.

A design mistake example is scanning controllers into a context not served by the servlet and assuming that simply having an ApplicationContext in the JVM means HTTP requests will find the controller. You must verify **bean visibility and the HandlerMapping infrastructure of the right servlet**.

### Lazy Initialization and Profiles

If a controller is constrained by **@Profile("admin")**, the bean may only exist when the admin profile is active. If the bean is not defined because a profile/condition is unmet, Spring MVC cannot register handlers for it. With lazy initialization, do not infer whether a mapping exists from whether the constructor has run; inspect the appropriate bean definitions/mapping registry.

### Controller Missing from Runtime Dependencies

Maven/Gradle may compile a class yet omit it from the running artifact due to wrong module dependencies or packaging. Check the actual classpath, startup logs, and deployed artifact/version, especially in multi-module systems. Having Java source in the editor does not mean that class exists in the running web server process.

## 14. How to Diagnose an Undetected Controller

Proceed from **right application → right bean → right mapping → right HTTP request**:

### Step 1 — Confirm the Right Process and Web Stack

- Are **server.port** and the context path right?
- Is the right instance/environment running? Is a reverse proxy, Docker port mapping, or gateway rewriting paths?
- Is the project **Spring MVC Servlet** or **Spring WebFlux reactive**?
- Do logs show the embedded server starting successfully?

### Step 2 — Confirm the Controller Is a Spring Bean

- Is there @Controller/@RestController or a custom annotation meta-annotated with @Controller?
- Is the class under the @SpringBootApplication package or corresponding @ComponentScan packages?
- Are any filters, @Profile, or @Conditional excluding the bean?
- Is there a bean creation error due to dependency injection? If startup failed, do not just chase the 404.
- If not using Boot, has XML/Java configuration scanned or registered the controller in the appropriate web context?

### Step 3 — Confirm RequestMappingHandlerMapping Registered the Handler

- Does the method have @GetMapping/@PostMapping/@RequestMapping?
- Do class-level @RequestMapping and method-level URLs combine properly?
- Are duplicate mappings, class proxies, or interface annotations hindering detection?
- Which servlet owns this mapping? Are there multiple ApplicationContexts?
- Did another auto-configuration/scan create the bean while the MVC infrastructure was not enabled properly?

In development, if **Spring Boot Actuator** is enabled and the **mappings** endpoint is exposed in a controlled manner, you can inspect registered mappings. Be careful because management endpoints can reveal detailed application info; do not expose them publicly without control. Actuator is not mandatory if you have proper startup logs and application context inspection.

### Step 4 — Inspect the Actual HTTP Request

~~~bash
curl -i -v -H "Accept: application/json" \
  "http://localhost:8080/api/greetings/Lan"
~~~

Check:

- Path, query string, method, and base path.
- Content-Type for requests with a body; Accept for the expected response.
- Authentication, proxies, CORS, redirects, and filters.
- **404** due to a missing route differs from **405** wrong HTTP method, **406** unsatisfiable response media type, and **415** unsupported request media type.

Browser devtools or Postman/curl are more reliable than guessing from URLs in code. With Spring Security, a valid endpoint may return **401/403** before the controller is invoked.

### Step 5 — Read Logs at the Right Places

Some symptoms:

| Symptom | Cause worth checking |
|---|---|
| Boot app started, yet new controller returns 404 | Package scan, profile/condition, URL, unregistered mapping |
| Startup reports **Ambiguous mapping** | Two handlers registered indistinguishable conditions |
| 404 only for prefixed paths | Context path, servlet path, or class-level @RequestMapping |
| 405 on a similar URL | HTTP method differs from handler mapping |
| API returns literal word **greeting** instead of HTML | Possibly switched @Controller to @RestController, making String the body |
| MVC tries to find a template named **ok** | @Controller returned a String view name when the author wanted body "ok" |
| JSON serialization fails | Converter/dependency, DTO serialization, return type |
| Controller needs a service, yet context fails to start | Missing bean, circular dependency, constructor injection/configuration |
| Endpoint disappears only in production profile | Conditional registration, packaging, @Profile, different config |
| Only one DispatcherServlet receives the controller | Misalignment or difference between child contexts and servlet mappings |

## 15. Verifying with Tests and Inspecting Configuration

Testing can be divided into three layers:

1. **Service/controller unit tests:** call Java methods directly to verify business logic. Does not prove URL mapping, scanning, or converters work.
2. **MVC slice tests:** @WebMvcTest with MockMvc in a Boot MVC app; typically restricts context to the web layer, requiring mocking/importing services and relevant custom configurations. You cannot conclude whole-app scanning is right from a slice test alone.
3. **Full-context integration tests:** @SpringBootTest combined with MockMvc or a real HTTP port to verify component scan, handler mappings, converters, and filters under realistic setup.

Examples of behaviors to test for the project in section 7:

- GET /greeting?name=Lan returns **HTML** containing **Hello, Lan!** in the body.
- GET /api/greetings/Lan with Accept: application/json returns JSON containing **message**.
- POST /api/greetings with Content-Type: application/json and a valid body returns **201**.
- GET /text?name=Mai returns **text/plain**; does not look for a view named after the greeting.
- GET /headers has **X-Source: controller** even though the class uses @Controller.
- Requests with wrong method/media type respond according to the contract.
- Moving a controller outside scan scope in a **separate test environment** causes its mapping to no longer appear.

In tests and production, avoid depending on entire HTML/JSON strings with rigid whitespace/ordering unnecessarily. Verify **status, headers, JSON fields, key HTML elements**, and real business side effects.

## 16. Common Misconceptions

**1. "@RestController automatically creates a REST server."** No. It only describes controller and @ResponseBody semantics. The server/DispatcherServlet or WebFlux runtime is configured separately.

**2. "@Controller is only for HTML pages."** No. @Controller can use @ResponseBody or ResponseEntity to return JSON/text bodies.

**3. "@RestController + @GetMapping still renders a template when returning a String."** Not normally: the String is the response body, not a logical view name.

**4. "Any @Component with @GetMapping creates an endpoint."** No. MVC annotated handler detection looks for an appropriate controller stereotype.

**5. "@Controller guarantees it was detected."** No. The annotation does not automatically add a class outside component scan to the ApplicationContext.

**6. "Spring Boot automatically scans all Maven dependencies."** No. By default it scans from the @SpringBootApplication package, except through explicit imports/configurations/dependencies.

**7. "Renaming the method changes the URL."** No. The URL is declared in the request mapping; the Java method name is internal (aside from rare alternative configuration mechanisms).

**8. "Each @RestController has only one endpoint."** No. One bean can contain many handler methods.

**9. "@RequestMapping is enough for everything; no need to check HTTP methods."** An unconstrained @RequestMapping has broad semantics; use shortcut annotations like @GetMapping/@PostMapping when the contract is clear.

**10. "@RestController inherently returns application/json even when returning String or missing a JSON converter."** No. Return type, converters, and content negotiation determine the body/media type.

**11. "When two controllers share a URL, the framework always picks the first class."** No. The mapping registry evaluates all conditions; ambiguity can cause startup or request failure.

**12. "A singleton controller can store per-request instance fields."** Dangerous. A singleton bean can handle concurrent requests; avoid mutable request-specific state.

**13. "Using @ControllerAdvice automatically creates a new URL."** No. Advice provides cross-cutting handling; it does not create HTTP mappings on its own.

**14. "@EnableWebMvc is needed in every Spring Boot project to detect @RestController."** No. Boot normally auto-configures MVC; adding @EnableWebMvc can override Boot defaults.

**15. "@RestController definitely means WebFlux."** No. Both MVC and WebFlux support the annotated controller model; the difference lies in the actual web stack.

## 17. Self-Check and Practice Exercises

**Question 1:** A @Controller class returns String **"dashboard"** from @GetMapping("/dashboard"). What happens?

**Answer:** Without @ResponseBody or other special return-value semantics, Spring MVC treats the String as view name **dashboard** and applies view resolution. If the view/template is missing, a rendering error may occur.

**Question 2:** Same method above, but the class is changed to @RestController?

**Answer:** Spring writes the string **dashboard** into the HTTP response body. It does not render a dashboard template.

**Question 3:** A @Service class contains @GetMapping("/x") and is scanned as a bean. Is GET /x mapped?

**Answer:** Not solely from @GetMapping. Annotated MVC handler detection requires a controller stereotype or suitable handler configuration.

**Question 4:** The main class is in example.app.bootstrap, and controllers are in example.app.web. Does Boot scan the controllers by default?

**Answer:** No, if only default scanning from package example.app.bootstrap is used; you need to place the main class in parent package example.app or configure scanning appropriately.

**Question 5:** How can @Controller return JSON without converting the whole class to @RestController?

**Answer:** Add **@ResponseBody** to the handler that needs to return a body, or use **ResponseEntity<T>**.

**Question 6:** Can @RestController return HTML?

**Answer:** It can return a body with Content-Type text/html if the endpoint intentionally generates HTML, but a returned String from @RestController is not interpreted as a view name; for server-side template views, @Controller is more suitable.

**Question 7:** If a controller bean already exists, is the URL definitely registered?

**Answer:** Not necessarily. MVC must have the infrastructure in the right context, recognize the stereotype, find method mappings, and register them successfully.

**Question 8:** Does Spring MVC re-scan the entire classpath on every HTTP request?

**Answer:** No. The mapping registry is built during initialization and used when dispatching requests.

**Question 9:** Why might a controller work in dev but be missing in production?

**Answer:** Check profiles, conditionals, artifact package/classpath, deployment, context, web stack, and URL/proxy before changing annotations.

**Question 10:** A @RestController uses a field String lastName to store a query name. Is that safe?

**Answer:** Usually not; controllers are singleton by default and may handle concurrent requests, so request state must stay in local variables or an appropriately scoped mechanism.

### Practice Exercises

Starting from the runnable project in section 7, do this step by step:

1. Add GET /api/greetings/default returning a GreetingResponse with a fixed message, and check how it interacts with the pattern GET /api/greetings/{name}. Observe mapping specificity instead of guessing Spring always picks one method.
2. Add a @Controller method with @ResponseBody returning **text/plain**, verifying it does not invoke a view resolver.
3. Place a new controller in a package outside scan scope, start the app, and observe the mapping is missing; move it back to a valid subpackage and verify.
4. Try an endpoint with the same URL but GET versus POST; confirm the two HTTP methods are mapped separately.
5. Add a handler with consumes=application/json, send a request with Content-Type: text/plain, and explain the status.
6. Add Spring Security if the curriculum has covered it; verify that the filter chain can block requests before MVC when unauthorized, and do not mistake that for a controller discovery error.

Do not modify production code for destructive configuration experiments; use a learning project or a separate test branch.

## 18. Official Documentation

- [Spring Framework — Annotated Controllers: Declaration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann.html): @Controller, @RestController, component scanning, and AOP proxy notes.
- [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): @RequestMapping, @GetMapping, mapping conditions, and patterns.
- [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): classification of handler return types.
- [Spring Framework — @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html): writing HTTP response body and message converters.
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): controlling status, headers, and body.
- [Spring Framework — Classpath Scanning](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): stereotype annotations, meta-annotations, and filters.
- [Spring Framework — DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html): request flow and context.
- [Spring Boot — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html): root package of @SpringBootApplication and component scan scope.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): Spring MVC auto-configuration.
- [Spring Framework — Annotated Controllers in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann.html): same annotation model on the reactive stack.

**Key takeaway:** **@Controller** marks a class as a Spring MVC controller bean and lets you handle views or responses depending on the return type. **@RestController** adds @ResponseBody semantics to conveniently return HTTP bodies. **Controller discovery** requires both Spring bean registration in the right context and **RequestMappingHandlerMapping** finding/registering handler methods. When seeing 404, verify in order: **right application → bean exists → mapping registered → request matches**.
