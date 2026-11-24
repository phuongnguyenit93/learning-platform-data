# DispatcherServlet Registration and Request Mapping in Spring Boot

## 1. Where Does DispatcherServlet Sit in the Spring MVC Flow?

In Spring MVC, **DispatcherServlet** is the front controller: a central Servlet that receives HTTP requests routed to it by the Servlet container, locates a matching handler, executes the MVC processing pipeline, and generates the HTTP response. In a Spring Boot application running on the Servlet model with default embedded Tomcat, developers typically only need to declare `@Controller` or `@RestController` classes; Spring Boot automatically creates and registers `DispatcherServlet`.

Distinguish three sequential decisions:

1. The **web server / Servlet container** accepts the connection on an IP and port and decides which web application (context path) the request belongs to.
2. **Servlet mapping** inside the container decides which Servlet receives the remaining HTTP path. Spring Boot's default `DispatcherServlet` is typically mapped to the `"/"` URL pattern within the application's context.
3. **Handler mapping** inside `DispatcherServlet` selects a controller method, functional handler, static resource handler, or other handler based on HTTP method, path, and mapping conditions.

A `@GetMapping("/books")` does not create a new Servlet in Tomcat. It registers a handler method with Spring MVC so that `DispatcherServlet` invokes it when a matching request arrives. Conversely, `ServletRegistrationBean` or `ServletContext.addServlet(...)` registers at the **Servlet container layer**, before `@RequestMapping` logic is ever considered.

Typical flow:

~~~text
Client  GET /app/books/42
   |
   v
TCP/TLS -> embedded Tomcat HTTP Connector
   |
   v
Web application context path: /app
   |
   v
Servlet Filter chain (e.g., Spring Security, logging)
   |
   v
Tomcat Servlet URL mapping: "/" -> DispatcherServlet
   |
   v
DispatcherServlet
   +-- HandlerMapping (e.g., RequestMappingHandlerMapping)
   |       -> BookController.find(42)
   +-- HandlerAdapter (e.g., RequestMappingHandlerAdapter)
   |       -> argument resolution + controller invocation
   +-- Return value handling / HttpMessageConverter
   |       -> JSON response
   +-- HandlerExceptionResolver when processing throws an exception
   |
   v
Filter chain finishes -> Tomcat -> HTTP response -> Client
~~~

From an operations standpoint, "Tomcat has opened the port" does not guarantee a valid `DispatcherServlet`, the expected controller mappings, or that the application is ready to serve traffic. Diagnostics must check the exact layer at fault: network, Servlet registration, Spring MVC handler mapping, or downstream business logic.

## 2. Spring Boot Automatically Creates and Registers DispatcherServlet

In an application using `spring-boot-starter-web`, Spring Boot 3.3 typically places key components on the classpath:

- Spring Web and Spring MVC, including `org.springframework.web.servlet.DispatcherServlet`.
- Jakarta Servlet API and an embedded Servlet container (Tomcat by default unless dependencies are changed).
- Auto-configurations for Servlet web applications, MVC, message conversion, error handling, and static resources.

When classpath, application type, and bean conditions match, `DispatcherServletAutoConfiguration` creates a `DispatcherServlet` bean commonly named **dispatcherServlet**. A `DispatcherServletRegistrationBean` bean (commonly named **dispatcherServletRegistration**) registers that Servlet with the `ServletContext` at the path determined by Spring MVC properties, defaulting to `"/"`.

In essence, there are two distinct objects/responsibilities:

| Concept | Responsibility |
|---|---|
| `DispatcherServlet` bean | Holds Spring MVC's front controller logic; managed by Spring as a bean |
| `DispatcherServletRegistrationBean` | Registers the Servlet bean with Tomcat/Jetty/Undertow's `ServletContext`; specifies URL pattern, Servlet name, load-on-startup |
| `ServletWebServerFactory` | Creates and configures the embedded Servlet server, including port and container |
| `RequestMappingHandlerMapping` | Locates controller methods registered via `@RequestMapping`, `@GetMapping`, `@PostMapping`... |
| `RequestMappingHandlerAdapter` | Invokes controller methods, binds arguments, and processes return values |
| `HandlerExceptionResolver` | Converts exceptions during MVC into an appropriate result/response |
| `HttpMessageConverter` | Reads/writes HTTP bodies by media type, such as JSON |
| `ViewResolver` | Resolves view names for controllers returning UI pages under the MVC model |

In standard Spring Boot, there is no need to write `web.xml`, create a `WebApplicationInitializer`, call `ServletContext.addServlet`, or manually register every controller. When `@SpringBootApplication` is placed in an appropriate parent package, component scan finds the controllers, and the MVC infrastructure automatically discovers handler methods.

### 2.1. Conditions for Auto-Configuration to Take Effect

Do not infer solely from a dependency named `spring-web`: the application must run as a **Servlet web application** with Spring MVC present. A reactive WebFlux application typically uses `DispatcherHandler` instead of `DispatcherServlet`. An application configured with `spring.main.web-application-type=none` will not start an embedded web server.

If multiple web libraries are present, verify Spring Boot's actual web stack. When both Spring MVC and WebFlux are on the classpath in a standard setup, Spring Boot prefers Servlet/MVC; using `WebClient` does not automatically switch the server to reactive.

Declaring a custom `DispatcherServlet` or registration bean can cause the default auto-configuration to back off due to bean conditions. Therefore, before "fixing" an issue by adding a second bean, check what auto-configuration actually creates and how it affects servlet mapping.

### 2.2. When Is DispatcherServlet Initialized?

You can configure:

~~~yaml
spring:
  mvc:
    servlet:
      load-on-startup: 1
~~~

In Spring Boot 3.3, the `spring.mvc.servlet.load-on-startup` property defaults to `-1`. A positive value instructs the container to eagerly initialize the Servlet at startup according to the Servlet spec's `load-on-startup` ordering. This relates to when the Servlet initializes, **not** a way to change route/controller mappings, and does not prove all business dependencies are ready. Avoid arbitrarily changing this value to mask 404 or readiness issues.

## 3. Two Mapping Layers: Servlet URL Patterns and @RequestMapping

The Servlet container layer works with URL patterns per the Servlet specification, such as:

- An exact path: `/special`.
- A prefix: `/legacy/*`.
- An extension suffix: `*.do`.
- The default mapping: `/`.
- A `/*` pattern is a broad path mapping, **different** from the default mapping `"/"`.

Tomcat uses the Servlet spec's precedence rules when choosing a Servlet: exact match, longest prefix match, extension match, and default match. You cannot conclude a request always passes through `DispatcherServlet` just because the application has controllers; if another Servlet has a more specific mapping, it can receive the request first.

Only after `DispatcherServlet` is chosen does Spring MVC evaluate handler mappings: path conditions, HTTP method, params, headers, `consumes`, and `produces`. `RequestMappingHandlerMapping` uses controller annotations to build mappings at the **Spring MVC layer**, without creating additional URL patterns in Tomcat.

Example:

~~~java
@RestController
@RequestMapping("/books")
class BookController {

    @GetMapping("/{id}")
    String find(@PathVariable long id) {
        return "book " + id;
    }
}
~~~

In an application where `DispatcherServlet` is mapped to `"/"` with an empty context path, `GET /books/42` is handed by Tomcat to `DispatcherServlet`; Spring MVC selects `BookController.find(...)` and returns the body `"book 42"`. Tomcat does not need to know about the specific controller or the `"/books/{id}"` route in its Servlet registration list.

### 3.1. Default Mapping "/" Is Not "/*"

This is an important distinction when manually adjusting Servlet registration:

- `"/"` is the default Servlet mapping under container rules. Another Servlet registered with a more specific exact or prefix mapping still gets the chance to receive matching requests.
- `"/*"` is a path-prefix pattern with different precedence and can intercept URLs intended for other Servlets or view/resource handling.
- Do not change the default `"/"` to `"/*"` thinking they are equivalent expressions. Changing it can affect additional Servlets, request forwarding, error pages, and view/asset handling.

For typical Spring Boot MVC applications, keeping the default `"/"` mapping is simplest and most compatible.

### 3.2. Route Annotations Also Have Conditions Beyond Path

Example:

~~~java
@PostMapping(
        path = "/books",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
)
ResponseEntity<BookView> create(@RequestBody NewBook body) {
    BookView saved = new BookView(101L, body.title());
    return ResponseEntity.status(HttpStatus.CREATED).body(saved);
}
~~~

This is an illustrative controller method snippet that must be placed inside a Spring MVC class with the `BookView`, `NewBook`, and corresponding imports added. It does not register a separate Servlet. Spring MVC selects the handler based on `POST /books` and matching `Content-Type`/`Accept` conditions.

HTTP status codes often help pinpoint the failing layer: 404 may indicate no matching servlet/handler/resource; 405 usually means the route exists but the HTTP method is unsupported; 415 relates to a `Content-Type` incompatible with `consumes`; 406 relates to an `Accept` header incompatible with `produces`. Do not blame every 4xx response on `DispatcherServlet` registration.

## 4. Combining Paths: Context Path, Servlet Path, Controller Path

Three path types are frequently confused:

1. **server.servlet.context-path**: the web application prefix at the Servlet container level.
2. **spring.mvc.servlet.path**: the registration path of `DispatcherServlet` within the web application.
3. **@RequestMapping/@GetMapping**: the handler path relative to the MVC space managed by `DispatcherServlet`.

Controller example:

~~~java
@RestController
@RequestMapping("/books")
class BookController {
    @GetMapping("/{id}")
    String book(@PathVariable long id) {
        return "book-" + id;
    }
}
~~~

Some configurations and expected URLs:

| Context path | DispatcherServlet path | Controller path | Complete GET URL |
|---|---|---|---|
| Empty (default) | `"/"` (default) | `/books/7` | http://localhost:8080/books/7 |
| `/catalog` | `"/"` | `/books/7` | http://localhost:8080/catalog/books/7 |
| Empty | `/api` | `/books/7` | http://localhost:8080/api/books/7 |
| `/catalog` | `/api` | `/books/7` | http://localhost:8080/catalog/api/books/7 |

The URLs above assume `server.port=8080`, no URL rewriting by a reverse proxy, no conflicting servlet mappings, and that a servlet path prefix is configured with a compatible path matching strategy.

### 4.1. Context Path for the Entire Servlet Application

Configuration:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /catalog
~~~

Controller `GET /books/7` is accessed via `GET /catalog/books/7`. Context path belongs to the web application. It applies to other Servlets registered in the same context as well, including Servlets that do not go through Spring MVC.

Use a context path when the entire web application needs a uniform prefix, such as a product version or shared path on a server. When behind an ingress, gateway, or reverse proxy doing path rewrites, separate the external URL from the path Tomcat actually receives; do not assume the proxy always preserves the prefix.

### 4.2. DispatcherServlet Path Specifically for Spring MVC

Configuration with a prefix:

~~~yaml
spring:
  mvc:
    servlet:
      path: /api
    pathmatch:
      matching-strategy: ant-path-matcher
~~~

**Version note:** In Spring Boot 3.3, `PathPatternParser` is the default path matching strategy; Spring Boot documentation explicitly notes that setting a custom prefix via `spring.mvc.servlet.path` is **incompatible** with `PathPatternParser`. Therefore, if you intentionally use `spring.mvc.servlet.path=/api` in Spring Boot 3.3, you must configure `matching-strategy: ant-path-matcher` as shown above and verify your actual routes.

If there is no strict need for a dedicated Servlet prefix, it is usually easier to leave `spring.mvc.servlet.path` at its default and use `server.servlet.context-path` or controller-level `@RequestMapping` matching the desired scope. Avoid switching matching strategies unnecessarily, since `AntPathMatcher` and `PathPatternParser` differ in how they accept certain patterns.

### 4.3. @RequestMapping Is Not the Servlet Path

If a class has `@RequestMapping("/api/books")`, handler URLs gain the `/api` prefix inside MVC while `DispatcherServlet` remains mapped to `"/"`. This differs from `spring.mvc.servlet.path=/api`:

- Changing `@RequestMapping` only alters handler mappings; other controllers and Servlet registrations do not move under the new prefix.
- Changing `spring.mvc.servlet.path` shifts the URL scope of `DispatcherServlet` itself; virtually all MVC handlers must be accessed via that prefix.
- Changing `server.servlet.context-path` changes the common prefix for the entire web application.
- Setting `servlet.path=/api` and `@RequestMapping("/api/books")` simultaneously can turn the URL into `/api/api/books`; this is a common configuration mistake.

Avoid double-stacking prefixes when designing routes or writing tests.

## 5. Runnable Java 17+ Example: Default Registration and Controller Mapping

Suppose you create a Spring Boot 3.3.x Java 17 project with starter web. In a Gradle project with the Spring Boot plugin applied, minimal dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Create `src/main/java/dev/example/mvc/MvcDemoApplication.java`:

~~~java
package dev.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcDemoApplication.class, args);
    }
}
~~~

Create `src/main/java/dev/example/mvc/BookController.java`:

~~~java
package dev.example.mvc;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(path = "/books", produces = MediaType.APPLICATION_JSON_VALUE)
public class BookController {

    public record BookView(long id, String title) {}

    public record CreateBook(String title) {}

    @GetMapping("/{id}")
    public BookView find(@PathVariable long id) {
        return new BookView(id, "Spring MVC");
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> create(@RequestBody CreateBook body) {
        BookView saved = new BookView(100L, body.title());
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }
}
~~~

The two nested records use Java 17. This is a demonstration controller with no database connection or real persistence. When the application starts, component scan finds `BookController` because it is in the same package as the main class. Spring MVC registers two handler mappings:

- `GET /books/{id}` -> `BookController.find(...)`.
- `POST /books` (`Content-Type: application/json`) -> `BookController.create(...)`.

No `web.xml` or `ServletRegistrationBean` is needed in this example. Spring Boot creates `DispatcherServlet` and maps it to `"/"` automatically.

You can add `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
~~~

From the project directory with Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell, you can run `.\gradlew.bat bootRun`. Test GET:

~~~bash
curl -i http://localhost:8080/books/7
~~~

The main result to verify is HTTP 200 and JSON body:

~~~json
{"id":7,"title":"Spring MVC"}
~~~

POST example:

~~~bash
curl -i -X POST http://localhost:8080/books \
  -H "Content-Type: application/json" \
  -d '{"title":"DispatcherServlet"}'
~~~

The command uses Unix shell line continuation; on PowerShell you can write it on a single line with `curl.exe`. The main result is HTTP 201 and body:

~~~json
{"id":100,"title":"DispatcherServlet"}
~~~

Headers such as `Date`, `Content-Length`, `Connection`, or content type parameters may vary by server/config. Do not treat the entire header string as immutable output. If you add `server.servlet.context-path=/catalog`, call `/catalog/books/7`. If you add `spring.mvc.servlet.path=/api` with a compatible matching-strategy, call `/api/books/7`.

### 5.1. Why Does @RestController Work Automatically?

`@RestController` is the semantic combination of `@Controller` and `@ResponseBody`. Spring MVC uses `RequestMappingHandlerMapping` to locate annotated mapping methods, `RequestMappingHandlerAdapter` to invoke the method, and argument resolvers to pass `@PathVariable`/`@RequestBody`.

When the handler returns a record, return-value handlers and `HttpMessageConverter` (usually Jackson via starter web) convert the object to JSON. `DispatcherServlet` coordinates this process; each controller method is not a Servlet and does not need its own port.

### 5.2. Component Scan Also Determines Whether Controllers Are Found

`@SpringBootApplication` includes component scanning starting from the package containing the main class downward. If `BookController` lies outside the scanned package, there will be no handler mapping for it even if `DispatcherServlet` is registered properly and `/actuator/health` works.

When hitting a 404, check package placement, `@Controller`/`@RestController` annotations, and bean conditions. Expand component scan only when needed; do not move the main class or scan the entire classpath arbitrarily.

## 6. Registering DispatcherServlet Manually When Truly Needed

Spring Boot already provides `DispatcherServletAutoConfiguration`, so common cases should use properties instead of creating another Servlet registration. However, when advanced registration control is required (custom Servlet name, load-on-startup, or unusual mappings), `DispatcherServletRegistrationBean` can be used.

Spring Boot 3.3 class details:

- `org.springframework.boot.autoconfigure.web.servlet.DispatcherServletRegistrationBean`.
- It extends `ServletRegistrationBean<DispatcherServlet>`.
- It also implements `DispatcherServletPath` so MVC infrastructure knows the Servlet registration path.
- Its constructor accepts a `DispatcherServlet` and a path.
- It provides `setName`, `setLoadOnStartup`, `setUrlMappings`, or `addUrlMappings`.

Example **replacing the default registration**, without creating a second `DispatcherServlet`. File `src/main/java/dev/example/mvc/DispatcherRegistrationConfig.java`:

~~~java
package dev.example.mvc;

import org.springframework.boot.autoconfigure.web.servlet.DispatcherServletAutoConfiguration;
import org.springframework.boot.autoconfigure.web.servlet.DispatcherServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.DispatcherServlet;

@Configuration(proxyBeanMethods = false)
public class DispatcherRegistrationConfig {

    @Bean(name =
            DispatcherServletAutoConfiguration
                    .DEFAULT_DISPATCHER_SERVLET_REGISTRATION_BEAN_NAME)
    public DispatcherServletRegistrationBean customRegistration(
            DispatcherServlet dispatcherServlet) {

        DispatcherServletRegistrationBean registration =
                new DispatcherServletRegistrationBean(dispatcherServlet, "/api");

        registration.setName(
                DispatcherServletAutoConfiguration
                        .DEFAULT_DISPATCHER_SERVLET_BEAN_NAME);
        registration.setLoadOnStartup(1);
        return registration;
    }
}
~~~

This is an intentionally advanced example: it creates a Spring-managed registration bean using Spring Boot's `DispatcherServlet`, registering it at `/api` instead of the default mapping. Ensure there is no other registration bean with the same name or conflicting mapping in the context. With Spring Boot 3.3, select a compatible path matching strategy when setting a prefix:

~~~yaml
spring:
  mvc:
    pathmatch:
      matching-strategy: ant-path-matcher
~~~

Do not simultaneously configure a conflicting `spring.mvc.servlet.path` in two places alongside a custom registration. Prefer **a single source of truth for the servlet path**; if the goal is simply `/api`, the `spring.mvc.servlet.path` property is sufficient and less risky.

A custom `DispatcherServlet` bean alone does not guarantee the container registers it with the desired mapping: an appropriate registration is required. Similarly, a registration bean that fails to inform the MVC infrastructure of the servlet path can break static resource paths, link generation, or handler mappings. This is why `DispatcherServletRegistrationBean` should be used rather than a plain `ServletRegistrationBean` when replacing the primary `DispatcherServlet` registration.

### 6.1. Should You Create a Second DispatcherServlet?

Multiple `DispatcherServlet` instances can be used for separate web contexts, routing mechanisms, or isolated modules, though this is not the default choice for a CRUD/REST application. Each servlet needs a unique name, explicit registration, non-conflicting mappings, and proper configuration for `ApplicationContext`, component scanning, `HandlerMapping`, error handling, filters, and security.

Only create multiple `DispatcherServlet`s when there is a genuine MVC partitioning requirement and you understand how servlets share or separate `WebApplicationContext`s. Adding a second servlet that reuses the exact same controller beans often causes duplicate routes or ambiguity over which servlet handles a request.

If you only want to group `/v1` and `/v2` endpoints, using `@RequestMapping("/v1")` or well-designed API versioning is far easier to maintain than creating two `DispatcherServlet`s.

### 6.2. Using ServletContext.addServlet Directly

The Servlet spec supports registering via `ServletContext.addServlet(name, servlet)`, followed by `ServletRegistration.Dynamic.addMapping(...)` and `load-on-startup`. In a Spring Boot embedded server, `ServletContextInitializer` and `RegistrationBean` classes integrate better with Boot's lifecycle. Do not call `addServlet` arbitrarily from code running after the container has started; Servlet registration has a specific lifecycle window where modifications are allowed.

Registering via `web.xml` or `WebApplicationInitializer` is a pure Servlet/Spring MVC technique and is unnecessary in a typical Spring Boot embedded Tomcat app. When deploying a WAR to an external container, `ServletContext` and container ownership rules also differ.

## 7. Registering Another Servlet Alongside DispatcherServlet

An application may have a plain Java Servlet handling `/legacy/*` outside Spring MVC. Spring Boot supports `ServletRegistrationBean` for this purpose.

Example file `src/main/java/dev/example/mvc/LegacyServletConfiguration.java`:

~~~java
package dev.example.mvc;

import java.io.IOException;

import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LegacyServletConfiguration {

    @Bean
    ServletRegistrationBean<HttpServlet> legacyServlet() {
        HttpServlet servlet = new HttpServlet() {
            @Override
            protected void doGet(
                    HttpServletRequest request,
                    HttpServletResponse response) throws IOException {

                response.setContentType("text/plain;charset=UTF-8");
                response.getWriter().write("legacy servlet");
            }
        };

        ServletRegistrationBean<HttpServlet> bean =
                new ServletRegistrationBean<>(servlet, "/legacy/*");
        bean.setName("legacyServlet");
        return bean;
    }
}
~~~

Spring Boot 3.x uses the **jakarta.servlet** namespace rather than `javax.servlet` as seen in many Spring Boot 2.x examples. With an empty context path and `DispatcherServlet` mapped to `"/"`, `GET /legacy/check` is routed by Tomcat straight to `legacyServlet` because the prefix mapping `/legacy/*` is more specific than `DispatcherServlet`'s default `"/"`.

Example:

~~~bash
curl -i http://localhost:8080/legacy/check
~~~

Expected body:

~~~text
legacy servlet
~~~

In this case **Spring MVC's `BookController`, `HandlerInterceptor`, and `@ControllerAdvice` do not directly process `legacyServlet`**. However, matching Servlet Filters (including the security filter chain if it covers that URL) can still run before `legacyServlet` receives the request. You must verify security policies for non-MVC Servlets too.

`@ServletComponentScan` enables discovery of `@WebServlet`, `@WebFilter`, and `@WebListener` in an embedded container. It is not required for Spring Boot to register the default `DispatcherServlet`, nor is it how `@RestController`s are discovered. Do not use `@ServletComponentScan` as a generic fix for controller 404s.

### 7.1. Avoiding Servlet Mapping Conflicts

If you register a new Servlet at `/books/*`, requests like `/books/7` may be captured by that Servlet before reaching `DispatcherServlet` mapped at `"/"`. Even though `BookController` still has `@GetMapping("/{id}")`, Spring MVC will never see the request.

When an endpoint suddenly returns 404 or the wrong response after adding a third-party Servlet, check Servlet URL mappings first—not just `@RequestMapping`. Servlet mapping conflicts are distinct from `HandlerMapping` conflicts.

Another Servlet mapped to `"/*"` can intercept more requests than intended. Only use broad patterns after reviewing all servlets, static content, forwards, error dispatches, and security filters involved.

## 8. How Does Spring MVC Process a Request After DispatcherServlet?

Once the container selects `DispatcherServlet`, it uses the MVC strategies configured in the `ApplicationContext`.

1. **HandlerMapping** locates a matching handler. `RequestMappingHandlerMapping` normally resolves `@RequestMapping`; resource handlers, functional routes, or view controllers may be handled by other `HandlerMapping`s.
2. **HandlerExecutionChain** may contain `HandlerInterceptor`s. `preHandle` can allow or block processing; `postHandle` and `afterCompletion` have their own lifecycle roles.
3. The appropriate **HandlerAdapter** invokes the handler. For annotated controllers, `RequestMappingHandlerAdapter` executes the method and handles binding, conversion, and validation as configured.
4. **Argument resolvers** resolve `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody`, `HttpServletRequest`, and other supported parameters.
5. **Return value handlers** turn the result into a response. `@ResponseBody`/`@RestController` typically uses `HttpMessageConverter` (e.g., JSON), whereas a controller returning a view name may need a `ViewResolver`.
6. **HandlerExceptionResolver** handles exceptions thrown by the MVC pipeline; `@ExceptionHandler` and `@ControllerAdvice` may participate.
7. `DispatcherServlet` finishes processing and the Servlet container sends the response back through registered filters.

Depending on async handling, exceptions, forwarding, and handler type, the filter/interceptor callback order can be more complex than a straight line. This is the general model for a standard request.

### 8.1. Filter vs. HandlerInterceptor

| Component | Where does it run? | Impact |
|---|---|---|
| Servlet Filter | Servlet container chain | Can run before `DispatcherServlet`, and can also apply to other Servlets |
| Spring Security Filter Chain | Servlet Filter chain if properly registered | Authentication, authorization, CSRF, and security policies |
| `HandlerInterceptor` | Spring MVC after `DispatcherServlet` picks `HandlerExecutionChain` | MVC handler–aware logic, logging, or lightweight checks |
| `ControllerAdvice` / `ExceptionHandler` | Inside MVC's exception-handling mechanism | Converts MVC exceptions into responses |
| `HandlerMethod` | Mapped controller method | Executes HTTP/business logic |

A Filter mapped to `"/*"` can run for both `/books/7` and `/legacy/check`. A `HandlerInterceptor` registered via MVC only runs when a request passes through Spring MVC appropriately. Do not put mandatory security controls inside a `HandlerInterceptor` assuming every Servlet in the application is protected equally.

### 8.2. HTTP Method and Media Type Are Also Part of Handler Mapping

For example, `GET /books/7` matches the path, but calling `POST /books/7` can return 405 instead of 404 because Spring MVC sees a matching path with an unsupported method. `POST /books` with `Content-Type: text/plain` can return 415 due to `consumes=application/json`. An `Accept` header incompatible with `produces` can lead to 406. When debugging, always check **HTTP method + full URL + headers + content type**.

## 9. Extending Spring MVC While Preserving Boot Auto-Configuration

To add formatters, interceptors, CORS mappings, view controllers, or static resources, usually declare a `WebMvcConfigurer` bean instead of recreating `DispatcherServlet` or using `@EnableWebMvc`.

Example adding an MVC redirect:

~~~java
package dev.example.mvc;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcPathConfiguration implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController("/old-books", "/books/7");
    }
}
~~~

This is a complete class that can be added to the demo. On `GET /old-books`, MVC can return a redirect response to `/books/7`. If a servlet path or context path is configured, check the final redirect URL (`Location` header) in the actual environment.

**`@EnableWebMvc`** takes direct control over MVC configuration and usually disables parts of Boot's `WebMvcAutoConfiguration` defaults. Do not add `@EnableWebMvc` just to make `@GetMapping` work, as `starter-web` already enables standard MVC. Use `WebMvcConfigurer` when you only need to extend specific extension points.

When you need to alter how mapping annotations are discovered, building a custom `RequestMappingHandlerMapping` or `HandlerAdapter` is advanced work that risks breaking all routes; verify first that `WebMvcConfigurer` or standard handler configuration is insufficient before taking that path.

## 10. Static Resources, Error Handling, and MVC Mapping

Spring Boot MVC normally configures static resource handlers to serve static content from locations like `classpath:/static`, `classpath:/public`, `classpath:/resources`, or `META-INF/resources`. This also goes through MVC resource handling for URLs routed to `DispatcherServlet`.

Having no `@GetMapping("/favicon.ico")` does not mean the request returns 404 straight from the Servlet container; the MVC resource handler may try to locate a static resource. In Spring Boot 3.3, when a resource is not found, `NoResourceFoundException` may occur instead of `NoHandlerFoundException` in some default configurations.

You can set:

~~~yaml
spring:
  web:
    resources:
      add-mappings: false
~~~

to disable static resource mappings if an API-only application truly does not need them. However, this also disables default static resource serving, so apply it only after understanding the consequences. Another option is narrowing `spring.mvc.static-path-pattern` to `/assets/**`.

Spring Boot provides error handling for the Servlet stack; `DispatcherServlet` can delegate to `HandlerExceptionResolver`, and Boot can supply `BasicErrorController` for error paths forwarded by the container. Do not create a `"/*"` handler or another catch-all Servlet without checking its impact on `/error` and static resource handling.

### 10.1. Reverse Proxies and Ingress Can Modify URLs Before DispatcherServlet

An external URL like `https://example.com/service/books/7` might be rewritten by a proxy to `/books/7` when forwarded to Tomcat, or kept as `/service/books/7` depending on rewrite rules. When a request misses a controller, determine the exact path the server receives rather than only reading the URL shown in the browser.

If handling `X-Forwarded-*` or `Forwarded` headers is needed, configure appropriate proxy trust and Spring Boot's `server.forward-headers-strategy` for your environment. Never trust headers sent directly by untrusted clients to construct redirect URLs. Servlet mapping still evaluates the internal request path inside the container after network/proxy components have processed it.

## 11. Inspecting What Has Actually Been Registered

Instead of guessing, inspect the different layers directly.

### 11.1. Startup and Logs

Check logs for web application type, embedded server (Tomcat), port, context path, and `DispatcherServlet` initialization details. Do not treat a single `"Tomcat started"` line as proof that all controller mappings were created.

You can temporarily raise log levels in development:

~~~yaml
logging:
  level:
    org.springframework.web.servlet.DispatcherServlet: DEBUG
    org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping: TRACE
~~~

`TRACE` level can generate heavy output and should not be enabled broadly in production. Logs reveal handler selection and mapping registration, but should be paired with real HTTP requests.

### 11.2. Actuator Mappings Endpoint

If you add the dependency:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
~~~

you can expose the `mappings` endpoint in a test environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,mappings
~~~

After startup, run:

~~~bash
curl -i http://localhost:8080/actuator/mappings
~~~

This endpoint displays servlet mappings, filter mappings, and Spring MVC handler mappings. The exact JSON structure depends on Boot version and configuration, so avoid hardcoding internal JSON paths in checks. If Actuator runs on a separate `management.server.port` or a different management context path, the endpoint URL changes accordingly.

**Security:** `mappings` exposes internal endpoint structure; only expose it in controlled environments or protect it with proper authentication/network policies. Do not expose it publicly just to debug a 404.

### 11.3. Inspecting ServletContext Registrations in a Controlled Way

`ServletContext` provides access to `ServletRegistration`s and their mappings. For example, to print registrations once the application starts, you can use a runner:

~~~java
package dev.example.mvc;

import jakarta.servlet.ServletContext;
import jakarta.servlet.ServletRegistration;
import java.util.Map;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ServletMappingsDiagnostic {

    @Bean
    ApplicationRunner logServletMappings(ServletContext servletContext) {
        return args -> {
            for (Map.Entry<String, ? extends ServletRegistration> entry
                    : servletContext.getServletRegistrations().entrySet()) {
                System.out.println(
                        entry.getKey() + " -> " + entry.getValue().getMappings());
            }
        };
    }
}
~~~

This is a diagnostic helper class for Servlet environments. Output depends on the active Servlets and container; do not assume there is only one registration. It tells you whether `DispatcherServlet` is mapped by the container to `"/"` or `"/api/*"`, though it does not prove a specific controller method exists.

In production, avoid logging all mappings per request; the runner here executes once at startup for inspection and can be removed after diagnosis.

## 12. Testing at the Right Layer

### 12.1. MockMvc Tests MVC Handlers

In a project with `spring-boot-starter-test`, you can write a test:

~~~java
package dev.example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getBookIsMappedToController() throws Exception {
        mvc.perform(get("/books/7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.title").value("Spring MVC"));
    }
}
~~~

The file can be `src/test/java/dev/example/mvc/BookControllerTest.java`. `MockMvc` tests the Spring MVC flow and controller mappings without opening a real network port. It is great for binding/validation/responses, but **is not sufficient to prove Tomcat actually registers the right URL pattern or port** when configuring multiple Servlets or custom registrations.

If you use a custom servlet path or context path, pay close attention to how `MockMvc` simulates `servletPath`/`contextPath` in request builders. Do not bake the full external URL into request mappings and assume a default `MockMvc` test always matches real container behavior.

### 12.2. Integration Testing with a Real Port

Use `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)`, or run the application and curl `localhost:port`. Verify:

- `GET /books/7` on the default path.
- `GET /catalog/books/7` with `context-path=/catalog`.
- `GET /api/books/7` with `servlet.path=/api` and compatible `matching-strategy`.
- `GET /legacy/check` with `ServletRegistrationBean("/legacy/*")`.
- `POST /books` with `Content-Type: application/json` and valid body.
- Cases with invalid HTTP method, path, or media type.
- Actuator/health endpoint if present, and actual mappings when management port is separate.

`RANDOM_PORT` starts the real embedded server and picks an available port. This catches Servlet mapping conflicts, wrong ports, request prefixes, security filters, or proxy settings that isolated controller unit tests miss.

### 12.3. Checking Duplicate Mappings at Startup

If two controllers declare identical handler mappings under the same MVC conditions and cannot be disambiguated, Spring MVC can report an ambiguous mapping at startup. For instance, two `@GetMapping("/books")` methods in the same context with identical conditions will conflict.

Duplicate controller mappings differ from Servlet registration conflicts: the former happens inside `RequestMappingHandlerMapping`, while the latter involves URL patterns/Servlet names registered with Tomcat.

## 13. Common Errors and How to Fix Them

| Symptom | Possible cause | How to verify |
|---|---|---|
| Tomcat opens the port, but all controllers return 404 | Controller outside component scan, wrong Servlet path, request intercepted by another Servlet | Check packages, Actuator mappings, servlet registrations |
| `/books/7` returns 404, `/catalog/books/7` returns 200 | `server.servlet.context-path=/catalog` is set | Check context path |
| `/api/books/7` returns 404 even though `@GetMapping("/books/{id}")` is valid | Prefix configured at the wrong layer or incompatible path matcher | Check `spring.mvc.servlet.path`, matcher, servlet registration |
| 404 only behind reverse proxy | Wrong proxy rewrite, forwarded path, or ingress rule | Compare external URL with request path reaching the app |
| `GET` works, `POST` on same path returns 405 | Handler only declares `@GetMapping` | Check HTTP method mapping |
| `POST` returns 415 | `Content-Type` does not match `consumes` | Check `Content-Type` and body converters |
| Request returns 406 | `Accept` incompatible with `produces` | Check `Accept` and handler `produces` |
| Startup fails with ambiguous mapping | Two MVC handler mappings have overlapping conditions | Inspect `@RequestMapping`/`@GetMapping` definitions |
| `/books` request goes to legacy Servlet | Another Servlet registered `/books/*` more specifically than `"/"` | Check `ServletRegistrationBean` and mappings |
| After `@EnableWebMvc`, static resources/CORS change | Default MVC auto-configuration no longer applies fully | Check `WebMvcConfigurer` and `@EnableWebMvc` |
| Security filter runs, `HandlerInterceptor` does not | Request does not go through `DispatcherServlet` or matches no MVC handler | Check servlet mapping and MVC interceptor registration |
| `/actuator/mappings` returns 404/403 | Actuator missing/not exposed, different management port, security policy | Check starter, exposure, port, filter chain |
| Manual Servlet registration causes startup failure | Duplicate Servlet name, URL mapping, bean, or servlet path conflict | Identify exact bean and registration ownership |

### 13.1. Do Not Use @EnableWebMvc to Fix Every Routing Error

In a standard `starter-web` app, auto-configuration already registers `DispatcherServlet` and the MVC infrastructure. `@EnableWebMvc` will not magically discover a controller missing from component scan. It can also alter Boot's default MVC configuration, breaking static resources, converters, or CORS if configured incompletely.

### 13.2. Do Not Use @ServletComponentScan to Find @RestController

`@ServletComponentScan` is for Servlet API annotations like `@WebServlet`/`@WebFilter`/`@WebListener`. `@RestController` is a Spring bean discovered by component scanning. If a `@RestController` sits outside the scanned package, fix the component scan scope or package layout.

### 13.3. Do Not Register a Second DispatcherServlet Just for a Prefix

If you want endpoints at `/api/books`, three mechanisms are often conflated: context path `/api`, servlet path `/api`, or `@RequestMapping("/api/books")`. Each has a different scope. Do not add a new `DispatcherServlet` just to get a prefix; that increases the risk of Servlet mapping and MVC infrastructure conflicts.

### 13.4. Do Not Confuse Servlet Mapping with Controller Mapping

A controller can be properly registered in Spring MVC yet never receive requests because the container routed the URL to another Servlet. Conversely, the Servlet mapping may be right while no MVC handler exists because the controller was never scanned. Use two separate checks: `ServletContext` registrations and `RequestMappingHandlerMapping`/Actuator mappings.

### 13.5. Do Not Assume Every 404 Is NoHandlerFoundException

Spring Boot may configure a `/**` resource handler; a request matching no controller can still be selected by the resource handler and fail because no file was found. With Spring Framework 6.x, you may see `NoResourceFoundException`. Inspect the stack trace and actual handler before writing a global exception handler and misattributing the error source.

### 13.6. With Spring Security, Requests Also Pass Through Filters Before MVC

When accessing a protected route, a 401, 403, or login redirect can happen before any controller is called. Not hitting a controller breakpoint does not automatically prove `DispatcherServlet` is mapped incorrectly. Check the security filter chain, matchers, and access rules before altering Servlet registration.

## 14. Decision Process When Changing Mappings

1. Record the external URL clients call and the actual URL Tomcat receives after proxy/ingress.
2. Determine whether the path change applies to the **entire application** or only a group of controllers.
3. If changing the entire Servlet application, consider `server.servlet.context-path`.
4. If only adding a route prefix for an API group, consider class/controller `@RequestMapping` or API routing config.
5. If you truly need to change `DispatcherServlet`'s managed region, consider `spring.mvc.servlet.path` and the Spring Boot version's path matching strategy.
6. If adding another Servlet on the same server, use `ServletRegistrationBean` or `@WebServlet` within proper scope and non-conflicting URL patterns.
7. If replacing the primary `DispatcherServlet` registration, use `DispatcherServletRegistrationBean` carefully; verify bean name, Servlet name, mapping, and `DispatcherServletPath`.
8. Start the project with the active profile and inspect `ServletContext` registrations and MVC handler mappings.
9. Run `MockMvc` to confirm handler/binding, then test HTTP on a real port to confirm container routing.
10. Re-verify security, Actuator exposure, static resources, forwarding, and reverse proxy behavior after changes.

Do not skip regression tests when changing context path or servlet path: a change intended for one route can impact every MVC endpoint, static resource URL, error page, and generated link in the application.

## 15. Self-Check Questions

**Question 1: Do you need to create DispatcherServlet manually when using spring-boot-starter-web?**  
Usually no. `DispatcherServletAutoConfiguration` creates the bean and corresponding registration in a Servlet MVC application.

**Question 2: Does @GetMapping("/books") register a separate Servlet?**  
No. It declares an MVC handler method for `DispatcherServlet` to select after the Servlet container routes the request to `DispatcherServlet`.

**Question 3: How does server.servlet.context-path=/shop differ from spring.mvc.servlet.path=/api?**  
`/shop` is the prefix for the Servlet web application; `/api` is the mapping prefix for `DispatcherServlet`. If both are set, MVC URLs become `/shop/api/...`, and a compatible strategy must be configured for the servlet prefix in Spring Boot 3.3.

**Question 4: Why does /legacy/check not pass through @ControllerAdvice?**  
If a separate Servlet maps `/legacy/*`, Tomcat can route the request straight to that Servlet. It does not go through `DispatcherServlet`, so MVC `@ControllerAdvice` does not handle that Servlet's errors in the standard way.

**Question 5: Can you replace servlet path by adding @RequestMapping("/api")?**  
That adds a prefix to controller routes without changing the Servlet registration in Tomcat. Their scopes differ.

**Question 6: Why does Spring Boot 3.3 require care when using spring.mvc.servlet.path?**  
Because this property is incompatible with the default `PathPatternParser` per Boot 3.3 docs; if setting a prefix, choose a compatible `matching-strategy`, typically `ant-path-matcher`, or apply the prefix at another layer.

**Question 7: Does a passing MockMvc test prove Tomcat mapped the servlet correctly?**  
Not completely. `MockMvc` primarily tests the Spring MVC pipeline. When modifying `ServletRegistrationBean` or mapping prefixes, test HTTP through a real embedded container.

## 16. Key Principles to Remember

- `DispatcherServlet` is Spring MVC's front controller; the Spring Boot Servlet stack normally creates its bean and registration automatically.
- The Servlet container picks the Servlet by URL pattern **first**; `DispatcherServlet` picks the controller/handler by `@RequestMapping` **afterward**.
- `server.servlet.context-path`, `spring.mvc.servlet.path`, and `@RequestMapping` have different scopes; combine URLs properly and avoid double prefixes.
- Spring Boot 3.3 uses `PathPatternParser` by default; custom servlet path prefixes require compatibility checks, usually `ant-path-matcher`.
- `DispatcherServletRegistrationBean` is for controlling `DispatcherServlet`'s registration; `ServletRegistrationBean` is for registering additional Servlets. Do not create multiple `DispatcherServlet`s without a clear requirement.
- Filters/Spring Security can run before the Servlet; `HandlerInterceptor` and `@ControllerAdvice` sit inside the MVC pipeline.
- When debugging 404/405/406/415, inspect routes, methods, `Content-Type`/`Accept`, component scan, Servlet URL mappings, path prefixes, and proxies before altering business logic.
- Check both Actuator mappings/`Servlet` registrations and real HTTP requests; `MockMvc` tests do not completely replace web server tests.

Once you understand the boundary between **Servlet registration** and **Spring MVC handler mapping**, you can trace a request's exact path, explain why an endpoint is or isn't invoked, and modify Spring Boot configuration without accidentally spawning extra Servlets or breaking live routes.

## 17. References

- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Common Application Properties (`spring.mvc.servlet.path`, `spring.mvc.pathmatch.matching-strategy`): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 API — `DispatcherServletRegistrationBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/DispatcherServletRegistrationBean.html
- Spring Boot 3.3 API — `DispatcherServletAutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/DispatcherServletAutoConfiguration.html
- Spring Boot 3.3 API — `ServletRegistrationBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/ServletRegistrationBean.html
- Spring Framework 6.x — `DispatcherServlet`, Front Controller: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html