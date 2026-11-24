# Prerequisites: Java, IoC/DI, HTTP, and Concurrency

Before learning **Spring Framework Web**, it helps to connect four areas of knowledge: Java expresses objects and behavior; IoC/DI lets Spring instantiate, wire, and manage objects; HTTP defines how clients and servers exchange messages; and concurrency determines what happens when multiple requests arrive at the same time. Understanding these foundations lets you read controllers, services, and application errors by how they actually work, rather than just memorizing annotations.

## 1. Big picture of a web request

A request flows through typical layers of responsibility:

```text
Client (browser, curl, another app)
    │  HTTP request: method + URL + headers + body (if any)
    ▼
Web server / Servlet container
    ▼
Spring MVC DispatcherServlet
    ▼
Handler mapping → Controller → Service → (Repository / external system)
    ▲                     │          │
    │                     └── Spring DI provides dependencies
    └── HTTP response: status + headers + body
```

This is a conceptual diagram for **traditional Spring MVC**. The dispatcher finds the matching handler; the controller layer handles HTTP communication; the service contains business behavior; the framework converts data between JSON and Java objects via HTTP message converters. Components may be used by multiple requests concurrently.

You should be able to answer four questions: how Java objects represent requests and responses; who creates and connects controllers with services; what makes up a valid HTTP request; and whether a service is safe when multiple threads call it simultaneously.

## 2. Java fundamentals you need to know

### 2.1. Classes, objects, interfaces, constructors, and access scope

- A **Class** describes data and methods; an **object** is an instance of a class. Two requests may invoke the same service object.
- An **Interface** describes a behavioral contract. Code depending on an interface allows swapping implementations and writing tests without forcing callers to know details.
- A **Constructor** establishes valid initial state. Spring commonly uses constructors to pass managed dependencies.
- `private` hides implementation state; `final` on a field prevents reassigning the reference after initialization. `final` does not by itself make the referenced object immutable.
- **Method parameters and local variables** belong to each individual invocation. Fields on a singleton bean are state that can be shared across invocations.

The plain-Java DI example below runs standalone, without Spring. File `ConstructorDiDemo.java`:

```java
interface Formatter {
    String format(String name);
}

final class VietnameseFormatter implements Formatter {
    @Override
    public String format(String name) {
        return "Xin chào, " + name + "!";
    }
}

final class WelcomeService {
    private final Formatter formatter;

    WelcomeService(Formatter formatter) {
        this.formatter = formatter;
    }

    String welcome(String name) {
        return formatter.format(name);
    }
}

public class ConstructorDiDemo {
    public static void main(String[] args) {
        Formatter formatter = new VietnameseFormatter();
        WelcomeService service = new WelcomeService(formatter);
        System.out.println(service.welcome("Lan"));
    }
}
```

Run with JDK 17+:

```bash
javac ConstructorDiDemo.java
java ConstructorDiDemo
```

Result:

```text
Xin chào, Lan!
```

`WelcomeService` uses a `Formatter` supplied from elsewhere via its constructor; it does not instantiate `VietnameseFormatter` itself. That is **dependency injection**, even without a container.

### 2.2. Data, generics, records, exceptions, and annotations

- `String`, primitives, `List<T>`, `Map<K,V>`, and `Optional<T>` are types frequently seen in request handlers and services. Generics let the compiler check types; `List<String>` represents a collection of elements, distinct from `String`.
- `record` (Java 16+, available in Java 17) suits simple DTOs: the compiler generates a canonical constructor, accessors, `equals`, `hashCode`, and `toString`. A record prevents reassigning its components, though it does not guarantee deep immutability if it holds mutable collections.
- Checked exceptions require declaring or handling per language rules; runtime exceptions have no such requirement. In a web app, an unhandled exception can lead to HTTP 500; turning it into a business error code requires appropriate handling mechanisms.
- Annotations such as `@Override` are metadata attached to declarations. Spring reads annotations like `@Controller`, `@Service`, and `@GetMapping` through framework mechanisms; simply writing an annotation does not turn a class into an HTTP endpoint unless Spring registers it.
- Distinguish **references**, **values**, and **mutability**. Java passes arguments by value, even when that value is a reference to an object; passing a reference does not create an independent copy of the object.

DTO example:

```java
record GreetingRequest(String name) {}
record GreetingResponse(String message) {}
```

In the JSON request `{"name":"Lan"}`, the key name must match the JSON converter's mapping rules. Do not assume all invalid input data will be blocked automatically: checking constraints like empty strings, null, length, and format is a separate validation step.

## 3. IoC and DI in Spring

### 3.1. IoC is lifecycle control; DI is how dependencies are passed

**Inversion of Control (IoC)** means application code delegates creating, configuring, and wiring components to an external mechanism. In Spring, `ApplicationContext` is the container managing **beans**. **Dependency Injection (DI)** is how the container supplies the objects a bean needs, commonly through its constructor.

Without DI, a service might call `new` on concrete dependencies itself, making implementations harder to swap. With constructor injection, dependencies are explicit requirements of the class, and a fake can be supplied in unit tests.

A typical object creation flow:

```text
Spring starts → scans config/components → registers beans
             → resolves dependencies → invokes constructor → bean ready to serve
```

Common stereotype annotations:

| Annotation | Typical role |
| --- | --- |
| `@Component` | General-purpose Spring bean |
| `@Service` | Business-layer bean; a specialized form of `@Component` |
| `@Repository` | Data-access layer bean; supports translating certain data-access exceptions |
| `@Controller` | MVC controller, commonly used with views |
| `@RestController` | Combines `@Controller` and `@ResponseBody`; return values are written to the HTTP response body |

Appropriate bean registration configuration (component scanning or `@Bean` declarations) is required. Spring Boot typically provides starter defaults, though package scanning location still affects whether classes are discovered.

### 3.2. Preferring constructor injection

```java
@Service
class GreetingService {
    String greet(String name) {
        return "Hello, " + name + "!";
    }
}

@RestController
class GreetingController {
    private final GreetingService greetingService;

    GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/hello")
    String hello(@RequestParam(defaultValue = "friend") String name) {
        return greetingService.greet(name);
    }
}
```

This snippet **illustrates code inside a Spring MVC application**; it is not a standalone Java program because it depends on Spring libraries, bean registration, and application startup. When a class has only one constructor, Spring does not require `@Autowired` on that constructor.

`GreetingController` only knows it needs a `GreetingService`. In unit tests you can pass a service directly, or extract an interface and pass a stub/fake. An unregistered bean causes a dependency-resolution error at startup; multiple matching beans of the same type may require `@Qualifier` or `@Primary`.

### 3.3. Scope and lifecycle directly affect concurrency

**Singleton** is the default bean scope: within one Spring container, a bean definition normally produces a single reused object. It is **not synonymous** with a JVM-wide singleton and **not synonymous** with thread-safe. A singleton controller serves many concurrent requests; storing a username or an unsynchronized counter in its fields can cause bugs.

The `prototype` scope creates a new object each time the container is asked for a bean of that scope; request/session scopes depend on a web context. Changing scope is not an automatic fix for every concurrency bug. Per-request state should be passed via parameters, local variables, or an appropriately scoped abstraction.

## 4. HTTP: the communication language between client and server

### 4.1. Request and response structure

An HTTP request consists of a method, target path/resource, headers, and an optional body. A response consists of a status, headers, and an optional body. Readable example (the first line reflects HTTP/1.1 syntax; HTTP/2 and HTTP/3 use different wire representations):

```http
POST /api/greetings HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"name":"Lan"}
```

```http
HTTP/1.1 201 Created
Content-Type: application/json

{"message":"Hello, Lan!"}
```

A **URL path** such as `/api/greetings/42` typically identifies a resource; **query parameters** such as `?lang=vi&page=2` typically express filtering, sorting, or pagination; **headers** carry metadata such as `Content-Type` or `Authorization`; the **body** carries the payload. Distinguish `Content-Type` (the media type being sent) from `Accept` (the media type the client wishes to receive).

HTTP is designed as **stateless at the request level**: each request must carry sufficient information to be processed under the protocol. Applications can still maintain session state using cookies, sessions, or tokens; that is an added mechanism layer, not built-in per-request statefulness.

### 4.2. Methods and semantic properties

| Method | Typical meaning | Safe? | Idempotent? |
| --- | --- | --- | --- |
| `GET` | Retrieve a representation of a resource | Yes | Yes |
| `HEAD` | Retrieve response metadata like GET, without a response body | Yes | Yes |
| `POST` | Request processing/resource creation per endpoint semantics | No | Not guaranteed |
| `PUT` | Create or replace resource state at the specified URI | No | Yes |
| `PATCH` | Partially modify a resource | No | Not guaranteed |
| `DELETE` | Remove a link/resource per endpoint semantics | No | Yes |

**Safe** means the client is not requesting a meaningful state change; technical logs or metrics may still be recorded. **Idempotent** means repeating the same request has the same intended effect on server state; repeated calls do not necessarily return the same status or response body. For example, the first DELETE may return 204 and the next 404, while the effect "the resource is gone" remains unchanged.

These properties govern API design, retries, and caching. Do not put money transfers or data deletion behind GET. If you need to prevent duplicate creation when a client retries a POST, the API can design an idempotency key and persist processing state, rather than assuming POST is idempotent by default.

### 4.3. Important status codes

| Status | Common meaning |
| --- | --- |
| `200 OK` | Request succeeded, usually with a response body |
| `201 Created` | Resource created; may include a `Location` header |
| `204 No Content` | Succeeded, with no response body |
| `400 Bad Request` | Request invalid in syntax or input per handler validation |
| `401 Unauthorized` | Missing or invalid authentication credentials for a protected resource |
| `403 Forbidden` | Server understood the request but denies authorization |
| `404 Not Found` | Matching resource/endpoint not found |
| `405 Method Not Allowed` | URI exists but the HTTP method is unsupported |
| `409 Conflict` | Request conflicts with current resource state |
| `415 Unsupported Media Type` | Submitted content type is not supported |
| `500 Internal Server Error` | Unmapped server-side error |

4xx codes mainly reflect request/client errors; 5xx codes reflect server-side issues, though specific circumstances must be examined. JSON body structure does not determine status codes on its own. Also avoid confusing **401 (authentication)** with **403 (authorization)**.

### 4.4. What Spring MVC does for you

- `@GetMapping`, `@PostMapping`, `@PutMapping` map methods/paths to handlers.
- `@PathVariable` extracts values from the path; `@RequestParam` extracts query or form parameters depending on the case; `@RequestBody` asks to convert the body into an object.
- `@ResponseBody`/`@RestController` serializes return values via message converters; `ResponseEntity<T>` lets you control status, headers, and body.
- JSON converters (such as Jackson when appropriate dependencies are present) do not replace validation or define business rules.
- DispatcherServlet performs dispatching at the web layer; services should not be forced to depend on `HttpServletRequest` just to perform business calculations.

HTTPS is HTTP over a TLS-protected connection; using HTTPS does not replace authentication, authorization, input validation, or CORS configuration. CORS is enforced by browsers for cross-origin access, not a general API authorization mechanism.

## 5. Concurrency in web applications

### 5.1. Multiple requests, same bean

In a typical Spring MVC setup using synchronous Servlet processing, the server uses execution threads to handle multiple requests concurrently. Exact details depend on the container, configuration, async mechanisms, or virtual threads; you should not assume each HTTP connection stays permanently bound to a single Java thread.

Suppose two requests invoke a singleton controller:

```java
@RestController
class UnsafeCounterController {
    private int counter = 0;

    @GetMapping("/unsafe-count")
    int next() {
        return ++counter;
    }
}
```

This is **faulty illustrative code**. `++counter` is not an atomic operation; multiple threads can read the same value and overwrite each other's result, losing increments. Beyond atomicity, unsynchronized reads/writes also involve Java Memory Model visibility rules. Do not "fix" this merely by adding `volatile`: `volatile` helps visibility and certain ordering guarantees, but does not make `++` an atomic update.

Solution for an in-memory counter within a single JVM:

```java
private final AtomicInteger counter = new AtomicInteger();

int next() {
    return counter.incrementAndGet();
}
```

You need to import `java.util.concurrent.atomic.AtomicInteger`. This is only a local counter. Multiple application instances or updates across multiple records require consistency mechanisms at the data layer, such as atomic database updates or transactions. AtomicInteger does not automatically handle multi-step transactions.

### 5.2. Standalone Java 17+ example with deterministic output

File `ConcurrentCounterDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentCounterDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger requests = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            List<Future<?>> results = new ArrayList<>();
            for (int i = 0; i < 1_000; i++) {
                results.add(pool.submit(() -> {
                    requests.incrementAndGet();
                }));
            }
            for (Future<?> result : results) {
                result.get();
            }
            System.out.println("Total requests: " + requests.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Run:

```bash
javac ConcurrentCounterDemo.java
java ConcurrentCounterDemo
```

Output:

```text
Total requests: 1000
```

`ExecutorService` schedules 1,000 tasks across a 4-thread pool; `Future.get()` waits for each task to complete or throws an exception if it fails; `AtomicInteger.incrementAndGet()` updates atomically so the result is 1,000. The example uses a fixed pool to simulate concurrent calls, which **does not mean** Spring MVC always uses this exact pool configuration.

If changed to an unsynchronized `int` and `requests++`, the result can be lower than 1,000; however, **never treat a single run that happens to output 1,000 as proof that code is thread-safe**. Race conditions depend on scheduling and can be hard to reproduce consistently.

### 5.3. Safety rules when writing controllers and services

- Prefer **stateless** beans: each request passes input into a method and receives a result; local variables are created per call.
- For state that must be shared, identify its scope: a single request, a single JVM, multiple app instances, or the database. Use thread-safe data structures, locks, or transactions appropriate to that scope.
- Immutability and `final` reduce risk, but do not replace synchronization design for shared mutable objects.
- Some APIs such as `SimpleDateFormat` are mutable and not designed for safe shared use; prefer immutable `java.time` APIs like `DateTimeFormatter` where appropriate.
- Blocking I/O waiting on databases or external HTTP calls holds execution resources in a synchronous model. Timeouts, connection pool limits, load shedding, and latency observability matter more than manually spawning `new Thread()` per request.
- Do not store request or user information in static fields or singleton fields. With `ThreadLocal`, understand that threads can be pooled/reused and require proper lifecycle cleanup; passing data explicitly is usually easier to control.
- **Spring MVC** and **Spring WebFlux** have different execution models; reactive/non-blocking does not automatically make business code with shared mutable state safe.

## 6. Combining all four areas in a Spring MVC example

The following example requires a **Spring Boot 3.x / Spring Framework 6.x project with the `spring-boot-starter-web` dependency**, JDK 17+, and a configured build tool. The files below are application code inside that project, not programs runnable with plain `javac` without Spring libraries. Place the three files in `src/main/java/demo/web/`.

`WebPrerequisitesApplication.java`:

```java
package demo.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebPrerequisitesApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebPrerequisitesApplication.class, args);
    }
}
```

`GreetingService.java`:

```java
package demo.web;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

`GreetingController.java`:

```java
package demo.web;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping
    public GreetingResponse read(
            @RequestParam(defaultValue = "friend") String name) {
        return new GreetingResponse(service.greet(name));
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public GreetingResponse create(@RequestBody GreetingRequest request) {
        return new GreetingResponse(service.greet(request.name()));
    }

    public record GreetingRequest(String name) {}
    public record GreetingResponse(String message) {}
}
```

With the application running on localhost:8080, try:

```bash
curl -i 'http://localhost:8080/api/greetings?name=Lan'
curl -i -X POST 'http://localhost:8080/api/greetings' -H 'Content-Type: application/json' -d '{"name":"Mai"}'
```

The GET response has status **200** and JSON equivalent to `{"message":"Hello, Lan!"}`; the POST response has status **201** and JSON equivalent to `{"message":"Hello, Mai!"}`. Actual headers and JSON character representation may vary by environment.

Step-by-step breakdown:

1. Spring Boot registers `GreetingService` and `GreetingController` via component scanning under the root package `demo.web` (**IoC**).
2. The container passes a `GreetingService` into the controller's constructor (**DI**, Java constructor and `final` field).
3. DispatcherServlet matches the mapping by path and HTTP method; `@RequestParam` reads the query on GET, `@RequestBody` converts JSON to a Java record on POST (**HTTP + Java**).
4. The controller calls the business method and returns a DTO record; Spring serializes it to JSON and assigns the status (**HTTP response**).
5. Each request creates its own local data inside methods; the service does not store name in a field, so this logic has no application-created shared mutable state (**concurrency**).

The example is intentionally simplified: it does not persist real resources, does not demonstrate production POST "create" semantics, has no authentication/authorization, no validation, and no custom error handling. If `{"name":null}` is received, the sample logic may produce a greeting containing the word `null`; input constraints need to be added in the validation lesson. When building real resource-creating APIs, you typically need resource identifiers, persistent state, and consideration of a `Location` header.

## 7. Common thinking mistakes and how to check

| Misconception | Correct understanding |
| --- | --- |
| "Having `@Service` means it is automatically injected everywhere" | The bean must fall under context configuration/scanning; dependencies must be resolvable |
| "Singleton equals thread-safe" | Scope only describes instance count; mutable fields still have race conditions |
| "A `final` field makes the whole object immutable" | `final` only forbids reassigning the field reference; the object inside can still be mutable |
| "GET and POST only differ by method name" | Safe, idempotent, caching, and retry semantics differ |
| "Stateless HTTP means a website cannot have a login session" | Cookies/sessions/tokens add mechanisms to maintain/verify state |
| "Returning a Java record guarantees JSON and HTTP 200 in all cases" | Requires Spring MVC/message converters, mappings, and status selection rules |
| "A request always has a dedicated immutable thread" | Depends on container, configuration, async processing, and execution model |
| "Using `volatile int` makes `++` safe" | `++` is a read-modify-write operation; requires atomics or appropriate locking |
| "Running a concurrency test once with the right output is enough" | Races might not manifest in one run; requires safe design and proper testing |

When debugging an endpoint, trace in order: **HTTP method/URL → handler mapping → binding/deserialization → service dependencies → business behavior → exception handling → serialization/status → state shared across requests**. Tracing step by step isolates bugs much faster than changing annotations at random.

## 8. Self-check before diving deeper into Spring Web

1. If `WelcomeService` creates `new VietnameseFormatter()` itself instead of receiving `Formatter` via its constructor, how does the ability to swap implementations in tests change?
2. Why can a `@RestController` be a singleton and still serve many users properly? What condition makes it dangerous?
3. Identify the method, path, headers, and body in the POST example. Why are `Content-Type` and `Accept` not equivalent?
4. Why can the same DELETE return 204 the first time and 404 the next while remaining idempotent?
5. If two concurrent requests invoke `++counter`, which operation can lose an increment? Why does `AtomicInteger` only solve the counter within a single JVM?
6. In the Spring example, which parts are provided by Java, which by the Spring container, which by HTTP, and which depend on concurrency design?

**You meet the entry bar** when you can explain the flow of a request entering a controller, read constructor injection, distinguish per-request data from shared state, choose appropriate HTTP methods/status codes, and spot dangerous mutable fields in singletons. With that, subsequent topics such as routing, data binding, validation, exception handling, filters/interceptors, and security will rest on a solid foundation.
