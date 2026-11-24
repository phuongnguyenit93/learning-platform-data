# The Role of Spring Web in Java Applications and Types of Web Applications

## 1. What problem does Spring Web solve?

A typical Java application can run from the command line, execute scheduled tasks, or process data without receiving HTTP requests. When you want to provide a website or networked service, the application needs to accept HTTP requests, determine which functionality to run, process data, and send HTTP responses to browsers, mobile apps, or other systems.

**Spring Web** is the group of Spring Framework components that helps build the web communication layer on the Java platform. Instead of manually reading HTTP requests and dispatching each Servlet for every URL, developers can declare request endpoints, parameters, input data, results, and error-handling rules using Spring components.

Example request:

```http
GET /api/books/42 HTTP/1.1
Host: example.com
Accept: application/json
```

The application can return:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"title":"Basic Java"}
```

This is a protocol illustration: Spring maps `GET /api/books/42` to handler code, converts `42` into a parameter, and then serializes the result object into JSON when an appropriate conversion library is configured.

It is important to distinguish three commonly seen names:

- **Spring Framework** is the foundation with IoC/DI and many modules, including the web modules.
- **Spring Web / Spring MVC / Spring WebFlux** are the web-processing components of Spring Framework. `spring-web` provides common HTTP foundations; `spring-webmvc` implements the MVC model on Servlet; `spring-webflux` implements the reactive web stack.
- **Spring Boot** provides auto-configuration, dependency management, and faster startup for Spring applications. Boot is often used together with Spring Web, but Boot and Spring Web are not synonymous.

## 2. Main roles of Spring Web

### 2.1. Exposing Java logic over an HTTP interface

Spring routes requests by path and HTTP method, for example `GET /products` to read a list or `POST /products` to create a new item. The controller is responsible for receiving requests and delegating business processing to a service, rather than packing all logic into the HTTP-handling method.

Common annotations in Spring MVC include `@Controller`, `@RestController`, `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PathVariable`, `@RequestParam`, and `@RequestBody`. They declare the request-handling contract and data binding, and do not themselves replace business validation, authentication, or transaction management.

### 2.2. Converting data between HTTP and Java objects

An application can receive data from the path, query string, headers, cookies, forms, or request body, and then bind that data to Java parameters or objects. For REST APIs, Spring typically uses HTTP message converters/codecs to read and write JSON. Converting to JSON generally requires an appropriate serialization library, which is configured by the corresponding starters.

For example, `GET /api/books?limit=10` contains the query parameter `limit`, whereas `POST /api/books` may contain JSON in the request body. These two data locations are different and need to be handled appropriately.

### 2.3. Organizing the web layer and integrating with the ecosystem

The web layer can combine with Spring Validation to validate data, Spring Security for authentication/authorization, the service layer for business logic, and repositories to work with databases. Spring also provides mechanisms for exception handling, CORS configuration, response content, file uploads, page navigation, and other web capabilities.

A maintainable separation of responsibilities:

```text
Client (browser / mobile / other service)
                 |
              HTTP(S)
                 v
Web server / servlet container / HTTP runtime
                 |
    Spring Web: routing + binding + response
                 |
              Controller
                 |
               Service
                 |
       Repository / external system
                 |
            Data/results
```

The diagram represents a logical view, not a rule that every project must have all layers or that every call must go through a repository. Security filters, interceptors, exception handlers, and infrastructure components can also participate in the processing flow.

## 3. How does an HTTP request flow through a Spring MVC application?

With the Servlet/Spring MVC stack, the common flow is:

1. The browser or client sends a request to the server. A Servlet container, such as Tomcat, accepts the connection and passes the request to the application.
2. Matching Servlet filters are applied; this can be where part of security or request metadata handling occurs.
3. Spring MVC's `DispatcherServlet` acts as the central dispatcher, finding the matching handler/controller through the handler mapping system.
4. Spring binds parameters, executes necessary steps such as type conversion and validation if declared, and then invokes the controller method.
5. The controller calls the service and handles the result or error; Spring builds the response by writing a body (such as JSON) or resolving a view name to render HTML.
6. The container returns the HTTP status, headers, and body to the client. If an error occurs, an exception resolver or error-handling mechanism can produce a corresponding response.

`DispatcherServlet` is a central concept of Spring MVC. In **Spring WebFlux**, the central dispatcher of the reactive stack is typically `DispatcherHandler`, and how I/O is handled differs from the traditional Servlet model.

HTTP has meaningful status codes: `200 OK` when reading succeeds, `201 Created` when creating a resource, `400 Bad Request` when the request is invalid, `401 Unauthorized` when valid authentication credentials are missing, `403 Forbidden` when permissions are insufficient, `404 Not Found` when the resource does not exist, and `500 Internal Server Error` for server-side errors. The actual status code must reflect the situation; Spring does not automatically choose the right code for every business case unless appropriate handling is designed.

## 4. Common types of web applications

Applications can be categorized by **how the UI is produced**, **how clients communicate**, or **how the system is deployed**. The groups below are different classification dimensions, so a single product can belong to multiple groups at the same time.

### 4.1. Server-side rendered HTML websites (server-side rendering)

The server receives a request, fetches data, and renders HTML before returning it to the browser. In Spring MVC, a `@Controller` can return a view name combined with a template engine such as Thymeleaf.

```text
Browser -- GET /catalog --> Spring MVC Controller
        <-- Rendered HTML -- Template + data
```

This is suitable for content websites, admin panels, forms, and products that want server-side UI rendering. The advantage is a centralized rendering flow where the page already contains HTML content in the response; in return, each navigation/submit step may entail a request and re-render the whole page or part of it, depending on the design.

### 4.2. Backend REST APIs returning data to clients

The server mainly returns JSON (or another data format) and does not necessarily generate HTML. Mobile apps, JavaScript frontends, partner systems, or other services consume the API. Spring MVC typically uses `@RestController` for this style.

```text
Mobile / SPA / Service -- HTTP + JSON --> Spring API
Mobile / SPA / Service <-- status + JSON -- Spring API
```

For example, an order management system has endpoints to read orders, create orders, and change statuses. The important points are clear resource design, HTTP methods, status codes, authentication, validation, and data contracts. **REST** is an API design style; using `@RestController` does not automatically guarantee that the entire API adheres to REST constraints.

### 4.3. Single-page applications (SPAs) with a Spring backend

An SPA (for example, a frontend using React, Vue, or Angular) loads most of its JavaScript UI in the browser, then calls APIs to fetch/update data. Spring Web can serve as the backend API; the frontend can be served from the same origin or deployed separately via a CDN/web server.

When the frontend and backend are on different origins, it is necessary to understand CORS configuration. CORS is a browser mechanism that controls whether scripts can read cross-origin responses; it is **not** an authentication or authorization mechanism. Authentication/authorization must still be enforced on the backend.

### 4.4. Web apps with real-time interaction

When clients need to receive continuous updates such as notifications, chat, price changes, or task progress, an application can use:

- **WebSocket** for a long-lived bidirectional connection when both client and server need to proactively send messages.
- **Server-Sent Events (SSE)** for a primarily unidirectional event stream from server to browser over HTTP.
- **Polling/long polling** when the client periodically checks for updates or holds a request open waiting for data.

Spring supports building these communication styles, but protocol selection should be based on bidirectionality, infrastructure, connection count, reconnection mechanics, and security requirements. Not every "real-time" feature needs WebSocket.

### 4.5. Monolith applications and microservices systems

This is a way of dividing deployment boundaries, not a way of representing the UI:

- **Monolith**: a single deployment unit that can contain server-side UI, APIs, services, and data access. Spring Web handles the HTTP entry point of that application.
- **Microservices**: multiple independently deployed services, each of which may have its own Spring Web API and communicate over HTTP or messaging. The system must account for timeouts, inter-service authentication, observability, network failures, and data consistency.
- **Modular monolith**: still deployed as one application, but divided into clear business modules to reduce coupling between parts.

Using Spring Web **does not require** choosing microservices; a well-structured monolith is often a reasonable starting point when there is no requirement to split deployments.

### 4.6. Static websites

A website consisting only of prebuilt HTML/CSS/JS that requires no Java business processing on the server can be served directly from a CDN or web server. Spring Web is not necessarily needed. When a static website calls a separate backend API, Spring Web may appear only on the backend side.

### Quick comparison table

| Application type | Primary response/communication | What Spring usually handles | Example |
|---|---|---|---|
| Server-side website | Server-rendered HTML | MVC controller + view resolver/template | Admin portal |
| Backend API | HTTP status + JSON | REST controller, binding, serialization | Order API |
| SPA + backend | JavaScript UI calling HTTP API | Backend REST, security, CORS when needed | React dashboard |
| Real-time | WebSocket, SSE, or polling | Endpoints and event infrastructure | Chat, notifications |
| Microservices | APIs across multiple services | HTTP endpoints per service | Payment service |
| Static website | HTML/CSS/JS files | Using Spring is optional | Static landing page |

A system can be both "SPA + REST API" from the UI perspective, a "modular monolith" from the deployment perspective, and also have "SSE" for notifications. Therefore, the rows in the table should not be treated as mutually exclusive choices.

## 5. Spring MVC and Spring WebFlux: the two main web stacks

Spring provides two prominent web-processing models. Both can expose HTTP endpoints and controllers and handle requests/responses; the notable difference lies in their execution model and I/O interaction.

| Criterion | Spring MVC | Spring WebFlux |
|---|---|---|
| Typical foundation | Servlet API, servlet container | Reactive Streams, non-blocking runtime |
| Dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Common style | Controllers return regular objects/values; supports async when needed | Controllers or functional endpoints, often using `Mono`/`Flux` |
| Blocking I/O | Fits well with many traditional blocking libraries | Must avoid blocking on event-loop threads; optimal when the entire I/O path supports non-blocking |
| Common use cases | CRUD, server-side HTML, REST with JPA/JDBC | High concurrent I/O, streaming, interacting with reactive downstreams |
| Trade-offs | Approachable model and mature Servlet ecosystem | Requires understanding reactive programming, backpressure, schedulers, and blocking boundaries |

**There is no rule that "WebFlux is always faster than MVC".** Outcomes depend on load, I/O wait time, system resources, and all dependencies. A WebFlux controller that directly calls JDBC or a blocking library on the event loop can still cause bottlenecks. Conversely, MVC supports asynchronous processing and can serve a large share of typical applications well.

Some applications can also use Spring MVC with virtual threads depending on the JDK, servlet container, and configuration. Virtual threads and WebFlux are two different concurrency approaches; you should not infer that an application using the latest Java automatically becomes reactive.

**Stack selection tip:** If the system is a website or CRUD REST service using JPA/JDBC and blocking libraries, Spring MVC is usually easier to start with and operate. If the processing flow is mostly non-blocking, needs streaming, and has a team familiar with reactive programming, consider Spring WebFlux after evaluating actual needs.

## 6. Small Spring MVC REST endpoint example

This example is for a **Spring Boot project that already has the web MVC dependency** and a JDK compatible with the Spring Boot version in use. It is a complete Java class *within a Spring Boot project*, not a standalone program that can be run with just `javac DemoApplication.java`: it requires Spring dependencies and the build system's run task.

Create the file `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
class GreetingController {
    @GetMapping("/api/hello")
    public Map<String, String> hello(
            @RequestParam(defaultValue = "friend") String name) {
        return Map.of("message", "Hello, " + name);
    }
}
```

Run the application with the corresponding project task, such as `./gradlew bootRun` (on Windows you can use `gradlew.bat bootRun`) if the project has the Spring Boot Gradle plugin and appropriate web configuration. While the application is listening on the default port 8080, send:

```bash
curl -s "http://localhost:8080/api/hello?name=Lan"
```

Expected response body (when a JSON converter is configured, as in common web MVC setups):

```json
{"message":"Hello, Lan"}
```

Explanation of each part:

1. `@SpringBootApplication` marks the entry point and enables Spring Boot's appropriate configuration mechanisms.
2. `@RestController` indicates that the return value of handler methods is written to the HTTP response body rather than interpreted as a view name.
3. `@GetMapping("/api/hello")` registers a handler for HTTP GET at that path.
4. `@RequestParam` reads the `name` parameter from the query string; when absent, the default value is `friend`.
5. `Map.of` creates Java data; the HTTP message conversion mechanism converts the map into JSON to return to the client. HTTP input/output is performed by Spring and the web runtime.

If a client accesses `/api/hello` without `name`, the response will carry the message `Hello, friend`. This small example only demonstrates routing and serialization; in a real application, controllers typically call services, perform validation, handle errors, and secure endpoints as required.

### When you want to return HTML instead of JSON

In a Spring MVC project with a configured template engine and an appropriate template, the controller typically looks like:

```java
@Controller
class HomeController {
    @GetMapping("/home")
    String home(Model model) {
        model.addAttribute("title", "Home");
        return "home";
    }
}
```

This is an **illustrative snippet** and cannot run standalone because `import` statements, template engine configuration, and the `home` template file are omitted. Unlike `@RestController`, the value `"home"` from a regular `@Controller` here is interpreted as a view name for the view resolver to process, rather than a JSON body.

## 7. Choosing application type and technology for each requirement

Start from the **consumer of the result** and the **interaction style**:

1. If users need a server-rendered HTML website, consider Spring MVC with a template engine.
2. If the client is a mobile app, SPA, or another system, design a clear HTTP API; either Spring MVC or WebFlux can serve the API.
3. If updates need to be pushed from the server to the client, evaluate SSE/WebSocket based on communication direction and load characteristics.
4. If business logic mainly uses JDBC/JPA or blocking libraries, prioritize consistency with the blocking execution model; switch to reactive only when there is a specific reason.
5. Choose monolith, modular monolith, or microservices based on deployment needs, team size, and business boundaries; that choice is relatively independent of whether HTML is rendered or JSON is returned.

For example, a ticket-booking website might start as a Spring MVC application rendering HTML and connecting to a database via JPA. When adding a mobile app, the same system can provide a REST API. When seat statuses need continuous updates, SSE or WebSocket can be added. Capabilities are extended as needed without converting the entire application to microservices just because multiple client types appear.

## 8. Common misconceptions and design mistakes

- **"Spring Web is a web server."** Spring Web is an application-layer framework; the web server/Servlet container or HTTP runtime handles accepting network connections. Spring Boot can launch an embedded server based on dependencies and configuration, but they are separate roles.
- **"Simply using `@RestController` makes an API REST-compliant."** The annotation only provides a way to handle requests and write responses; resource design, HTTP semantics, status codes, and API contracts still need to be designed deliberately.
- **"Controllers should contain all logic."** Stuffing business validation, SQL, and external system calls directly into controllers makes applications hard to test and maintain. Keep controllers thin and separate responsibilities into services and appropriate layers.
- **"CORS protects the API."** CORS is primarily a constraint on JavaScript access in browsers; the API still needs authentication, authorization, input validation, and real security measures.
- **"Reactive means every function runs in parallel or is always fast."** Reactive describes a way of composing and processing asynchronous, non-blocking streams; actual performance still depends on blocking points and resources.
- **"An SPA requires Spring to serve the frontend files."** The frontend can be hosted separately; Spring Web can provide only the backend.
- **"Every service must be deployed as a microservice."** Code boundaries and deployment boundaries are not the same. Clear business modules can be organized within a single application.

## 9. Self-check for comprehension

**Scenario 1:** An iOS app needs to fetch a list of products in JSON format. What role does Spring Web play?  
**Answer:** It provides HTTP endpoints, maps requests, invokes business logic, converts objects into JSON, and returns HTTP responses. Spring does not build the iOS UI.

**Scenario 2:** Does a website using Thymeleaf to render pages on the server need a REST API for every screen?  
**Answer:** No. Controllers can return HTML views directly; a REST API is only needed when there is separate data communication or other clients.

**Scenario 3:** A Spring MVC application uses JPA but needs real-time progress notifications. Is it mandatory to rewrite everything in WebFlux?  
**Answer:** No. You can evaluate SSE, WebSocket, or polling on the current architecture; appropriate resource, timeout, reconnect, and concurrency handling must be designed.

**Key takeaway:** Spring Web is the layer connecting web protocols and Java application logic. The application type is determined by how clients consume HTML/data/events, while Spring MVC or WebFlux is the choice of web-processing stack. Monolith/microservices design is a different deployment architecture dimension and is not dictated by using Spring Web.
