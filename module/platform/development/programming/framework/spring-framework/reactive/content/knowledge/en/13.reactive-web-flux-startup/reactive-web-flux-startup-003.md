# Initializing WebFlux Configuration and a Minimal Endpoint

## 1. Goal and context

**Spring WebFlux** is Spring's reactive web framework, built around an asynchronous and non-blocking model. WebFlux applications typically use **Project Reactor** with two familiar data types:

- **Mono<T>** represents a result that has at most one element.
- **Flux<T>** represents a sequence that can have from zero to many elements.

A minimal WebFlux application needs the right dependencies, a Spring Boot entry point, a suitable HTTP configuration, and at least one endpoint that returns a Mono or Flux. When the application starts, Spring creates the ApplicationContext, detects controllers/handlers, configures codecs to convert requests/responses, and initializes the reactive web server.

This lesson shows how to create a WebFlux application from scratch using Maven and Java 17+, configure a few necessary properties, write an annotated endpoint and a functional endpoint, run the application, test it with WebTestClient, and recognize common configuration mistakes.

After this lesson, you will be able to:

- Distinguish WebFlux from Spring MVC and know when to choose each stack.
- Add the correct starter to launch a WebFlux application.
- Create a main class with @SpringBootApplication.
- Write REST endpoints that return Mono and Flux.
- Understand the role of HTTP message codecs and WebFluxConfigurer.
- Write a functional endpoint using RouterFunction and HandlerFunction.
- Run, check, and test endpoints with curl and WebTestClient.
- Avoid blocking, manual subscribing, and duplicated configuration that wipe out the benefits of reactive.

## 2. How does WebFlux differ from Spring MVC?

| Characteristic | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Main model | Servlet, usually processed per request thread | Reactive, supports non-blocking I/O |
| Common return types | Object, ResponseEntity, Callable, DeferredResult | Mono<T>, Flux<T>, Publisher |
| Common runtime | Servlet container such as Tomcat | Reactor Netty by default in the common Boot configuration |
| I/O | Can use blocking APIs following the servlet model | Suited to reactive/non-blocking clients and servers |
| Data flow | Usually returns the response after processing | Can stream many elements through Flux/SSE |
| Ecosystem | Spring MVC, Servlet filters, MVC interceptors | WebFilter, WebClient, Reactor Context, reactive security |

WebFlux fits when the system has asynchronous I/O, needs streaming, or wants to connect reactive services without holding threads in blocking waits. It does not by itself make a CPU-bound algorithm faster, nor does it turn JDBC or a blocking library into non-blocking just by changing the return type.

**Not every application needs WebFlux.** If the whole system uses JDBC/blocking and the load does not demand a reactive model, Spring MVC can be simpler. The value of WebFlux is clearer when most of the processing chain can be non-blocking from end to end.

### 2.1. Avoid putting two web starters in the same application unless intended

To create a pure WebFlux application, use **spring-boot-starter-webflux**. Do not add **spring-boot-starter-web** arbitrarily.

If both the MVC and WebFlux starters appear on the classpath, Spring Boot usually prefers the Spring MVC configuration. This is a common reason why an application thought to be using WebFlux actually starts with the servlet stack. If the real goal is WebFlux, check the dependency tree and remove the unnecessary MVC starter instead of trying to fix it with lots of configuration.

WebFlux can run on Reactor Netty by default, and also supports some other runtimes through configuration. In this hands-on lesson we keep the default configuration to reduce the number of components to set up.

## 3. Create a Maven project and add dependencies

Sample directory structure:

~~~text
reactive-webflux-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/webflux/
    │   │       ├── ReactiveWebFluxApplication.java
    │   │       ├── GreetingController.java
    │   │       ├── FunctionalRoutes.java
    │   │       └── WebFluxConfiguration.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/webflux/
                └── GreetingControllerTest.java
~~~

The **pom.xml** file uses Spring Boot 3.3.5 and Java 17:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>reactive-webflux-demo</artifactId>
    <version>1.0.0</version>
    <name>reactive-webflux-demo</name>

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
            <artifactId>spring-boot-starter-webflux</artifactId>
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
~~~

Meaning of the dependencies:

- **spring-boot-starter-webflux** brings in Spring WebFlux, Reactor, and the default reactive server that fits the Boot configuration.
- **spring-boot-starter-test** provides JUnit Jupiter, Spring Test, and commonly used testing libraries, including WebTestClient in a WebFlux environment.
- The Spring Boot parent manages compatible dependency/plugin versions; you do not need to set a version for each library that Boot manages.

You do not need to add **spring-boot-starter-web** for this example. If the project already has that starter, check whether MVC is really needed before deploying.

## 4. The Spring Boot entry point

Create the file **ReactiveWebFluxApplication.java**:

~~~java
package com.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveWebFluxApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ReactiveWebFluxApplication.class,
            args
        );
    }
}
~~~

**@SpringBootApplication** combines three main capabilities:

1. **@SpringBootConfiguration**: marks the main configuration class of the application.
2. **@EnableAutoConfiguration**: lets Spring Boot configure beans based on the existing dependencies and configuration.
3. **@ComponentScan**: scans for components from the main class's package downward.

Because the main class is in **com.example.webflux**, controllers, services, and configurations placed in this package or its subpackages will be detected automatically. If you place components outside the scan scope, you need to organize packages sensibly or configure the scan explicitly.

With WebFlux, Spring Boot recognizes the reactive starter and configures the web application with the reactive stack. In the default case, the server will start with Reactor Netty if the corresponding dependency/runtime is present.

**You do not need to add @EnableWebFlux in a typical Spring Boot application.** Boot already provides auto-configuration. Use @EnableWebFlux only when you want to control the WebFlux configuration at a low level and accept responsibility for the auto-configuration parts that the application replaces.

## 5. Write a minimal annotated endpoint using Mono

Create the file **GreetingController.java**:

~~~java
package com.example.webflux;

import java.time.Duration;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class GreetingController {

    @GetMapping("/hello")
    public Mono<Map<String, String>> hello(
        @RequestParam(defaultValue = "World") String name
    ) {
        return Mono.just(
            Map.of("message", "Hello, " + name)
        );
    }

    @GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofSeconds(1))
            .map(sequence ->
                ServerSentEvent.builder("tick-" + sequence)
                    .id(Long.toString(sequence))
                    .event("tick")
                    .build()
            );
    }
}
~~~

### 5.1. Analyzing the /api/hello endpoint

- **@RestController** marks a component that handles HTTP and serializes the return value into the response body.
- **@RequestMapping("/api")** sets a prefix for the endpoints in the class.
- **@GetMapping("/hello")** maps HTTP GET to the hello method.
- **@RequestParam(defaultValue = "World")** reads the query parameter name; if the client does not pass it, the value is World.
- **Mono<Map<String,String>>** indicates the result is emitted using the reactive model and there is only one map.
- **Map.of(...)** creates immutable data suitable as a simple response; the Spring codec will serialize it to JSON.

Request:

~~~http
GET /api/hello?name=Lan HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

Response body:

~~~json
{
  "message": "Hello, Lan"
}
~~~

When there is no query parameter:

~~~http
GET /api/hello
~~~

Response:

~~~json
{
  "message": "Hello, World"
}
~~~

### 5.2. Analyzing the /api/events endpoint

The second endpoint returns **Flux<ServerSentEvent<String>>**. This is an example of streaming data over time:

- **Flux.interval(Duration.ofSeconds(1))** emits an increasing number every second.
- **map(...)** turns the sequence number into a ServerSentEvent.
- **id(...)** sets the event id so the client can identify the event.
- **event("tick")** sets the event name.
- **data(...)** sets the payload.
- **produces = TEXT_EVENT_STREAM_VALUE** requires the response to use the media type text/event-stream.

When a client connects, the response does not need to wait for the whole Flux to complete. Each element is written out when its signal arrives. When the client disconnects, the subscription may be cancelled; the corresponding interval source is asked to stop.

This is a minimal SSE example, not a durable message broker. If a client disconnects and then reconnects, the server does not automatically recover every missed event unless the application builds its own replay/id mechanism.

## 6. Configure WebFlux deliberately with WebFluxConfigurer

Spring Boot configures many parts automatically. When you need to customize one specific point, you can implement **WebFluxConfigurer** without re-enabling the whole configuration through @EnableWebFlux.

Create the file **WebFluxConfiguration.java**:

~~~java
package com.example.webflux;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer
    ) {
        configurer.defaultCodecs()
            .maxInMemorySize(1024 * 1024);
    }
}
~~~

Here the configuration limits the memory used for reading/writing content that the codec needs to buffer to 1 MiB. This is an illustrative value to show how to customize; you must choose it according to payload size, resource limits, and the application's requirements.

**HTTP message codecs** handle the conversion between byte streams and Java types, for example:

- JSON to Java objects and vice versa through Jackson when the appropriate dependency is present.
- String to text.
- ByteBuffer/DataBuffer for binary data.
- Server-Sent Events for event streams.
- Reactive data types such as Mono and Flux at the web adapter layer.

If a client sends a payload exceeding the codec's buffer limit, the request may fail with a data limit error. Do not raise the limit indefinitely just to make the error disappear; check the request size, streaming, and the risk of memory consumption.

### 6.1. application.properties

Create the file **src/main/resources/application.properties**:

~~~properties
spring.application.name=reactive-webflux-demo
server.port=8080
logging.level.com.example.webflux=INFO
~~~

- **spring.application.name** sets the application name for observability/logging.
- **server.port** chooses the HTTP port.
- **logging.level...** configures the log level for the application package.

You can change the port through an environment variable or profile configuration. Do not hard-code secrets, tokens, or production environment information in a committed properties file.

### 6.2. When do you need @EnableWebFlux?

In a typical Boot application, let auto-configuration manage WebFlux. If you add **@EnableWebFlux**, the application deliberately enables the full WebFlux configuration and may cause some of Boot's default customizations to no longer apply as before.

Use it only when you need deep control and understand the beans/codecs/handler mappings you must configure yourself. For common needs such as adding CORS, codecs, formatters, or converters, starting from **WebFluxConfigurer** is usually the less disruptive choice.

## 7. Functional endpoint: RouterFunction and HandlerFunction

Besides annotated controllers, WebFlux supports a functional routing model. Two concepts:

- **RouterFunction<ServerResponse>** describes the route condition and the corresponding handler.
- **HandlerFunction<ServerResponse>** handles a request that has been routed and returns Mono<ServerResponse>.

Create the file **FunctionalRoutes.java**:

~~~java
package com.example.webflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> helloRoute() {
        return RouterFunctions.route()
            .GET(
                "/functional/hello",
                request -> ServerResponse.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .bodyValue("Hello from functional WebFlux")
            )
            .build();
    }
}
~~~

The functional endpoint above does not need @RestController. Spring picks up the RouterFunction bean and registers the corresponding route.

Request:

~~~http
GET /functional/hello HTTP/1.1
Host: localhost:8080
~~~

Response:

~~~text
Hello from functional WebFlux
~~~

### 7.1. Annotation or functional endpoint?

| Criterion | Annotated controller | Functional endpoint |
| --- | --- | --- |
| Route declaration | @GetMapping, @PostMapping | RouterFunctions.route |
| Handler | Method in @RestController | HandlerFunction |
| Suitable for | Common REST APIs, resource-based controllers | Explicit routes, handler composition, per-module endpoints |
| Validation/binding | Integrated annotations and argument resolvers | You organize reading the request, validating, and building the response yourself |
| Code readability | Familiar to most Spring developers | Explicit at the routing/handler layer |

You do not need to use both styles for the same route. You can combine them in one application but should divide responsibilities clearly to avoid duplicate routes or logic split in two that is hard to follow.

## 8. Run the application

Prerequisites:

- JDK 17 or later.
- Maven 3.6+ or Maven Wrapper.
- Port 8080 is not occupied by another application.

In the directory containing pom.xml:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Or package and then run the JAR:

~~~bash
mvn clean package
java -jar target/reactive-webflux-demo-1.0.0.jar
~~~

When startup succeeds, the log usually shows that Spring Boot has initialized the ApplicationContext and the reactive web server on port 8080. The specific log lines may differ by patch version, environment, and logging configuration; do not depend on the exact wording of the logs to determine whether an endpoint works.

### 8.1. Check the JSON endpoint

Open another terminal:

~~~bash
curl "http://localhost:8080/api/hello?name=Lan"
~~~

Result:

~~~json
{"message":"Hello, Lan"}
~~~

Try the default parameter:

~~~bash
curl "http://localhost:8080/api/hello"
~~~

Result:

~~~json
{"message":"Hello, World"}
~~~

Check the functional route:

~~~bash
curl "http://localhost:8080/functional/hello"
~~~

Result:

~~~text
Hello from functional WebFlux
~~~

### 8.2. Check Server-Sent Events

Use:

~~~bash
curl -N "http://localhost:8080/api/events"
~~~

The **-N** option disables buffering on the curl side so you can observe each event as it is sent. Illustrative output:

~~~text
id:0
event:tick
data:tick-0

id:1
event:tick
data:tick-1

id:2
event:tick
data:tick-2
~~~

Events continue to be emitted every second until the client disconnects. The sequence number starts from 0 in a new Flux.interval subscription.

## 9. Testing with WebTestClient

WebTestClient lets you send requests and check responses without writing manual tests with curl. With Spring Boot WebFlux, you can test the application on a random server port.

File **src/test/java/com/example/webflux/GreetingControllerTest.java**:

~~~java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class GreetingControllerTest {

    @Autowired
    private WebTestClient client;

    @Test
    void helloReturnsJson() {
        client.get()
            .uri("/api/hello?name=Lan")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello, Lan");
    }

    @Test
    void functionalRouteReturnsText() {
        client.get()
            .uri("/functional/hello")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Hello from functional WebFlux");
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The two tests confirm that:

1. The controller is detected and the GET /api/hello route works.
2. JSON is serialized correctly and the query parameter is bound.
3. The functional RouterFunction is registered and returns the correct text content.

The tests do not depend on port 8080 because Spring Boot uses a random port. If you want to test SSE, write a separate test with a limited number of events and a suitable wait time so the test does not hang indefinitely.

## 10. Overview of the request processing flow

~~~text
HTTP Client
    |
    | GET /api/hello?name=Lan
    v
Reactive Web Server
    |
    v
WebFilter chain
    |
    v
Handler Mapping
    |
    +------------------------------+
    |                              |
    v                              v
Annotated Controller          RouterFunction
    |                              |
    v                              v
Mono / Flux                    HandlerFunction
    |                              |
    +---------------+--------------+
                    |
                    v
          Reactive HTTP Adapter
                    |
                    v
             Message Codecs
                    |
                    v
             HTTP Response
~~~

In the annotation flow, the handler mapping finds the controller method by its mapping. In the functional flow, the RouterFunction selects the suitable HandlerFunction. Both return a reactive Publisher so that the framework coordinates the subscription, signals, and response.

The main components:

- **Web server** accepts connections and creates the request/response abstraction.
- **WebFilter** can handle cross-cutting concerns such as correlation ID, CORS, authentication, or logging.
- **HandlerMapping** finds the corresponding handler.
- **Controller/HandlerFunction** builds the reactive pipeline.
- **HTTP message codecs** convert the data.
- **Reactive adapter** connects the Publisher to the HTTP lifecycle.

Not every step creates a separate thread. Reactor Netty and reactive components usually use an event loop; blocking on the event loop can slow down many requests at the same time.

## 11. Important non-blocking rules

### 11.1. Do not call block in a controller

Avoid:

~~~java
@GetMapping("/bad")
public String bad() {
    return remoteService.fetch()
        .block();
}
~~~

The block call waits for the result synchronously and can block the thread that is handling the request. In WebFlux, return a Publisher:

~~~java
@GetMapping("/good")
public Mono<Data> good() {
    return remoteService.fetch();
}
~~~

Spring WebFlux will subscribe and write the response when the signals arrive.

### 11.2. Do not subscribe manually in a controller

Avoid:

~~~java
@GetMapping("/bad-subscribe")
public Mono<Void> badSubscribe() {
    service.doWork().subscribe();
    return Mono.empty();
}
~~~

Manual subscription detaches the work from the HTTP response lifecycle. The framework may complete the response before the work is done; errors and cancellation of the request are also no longer correctly tied to the task.

Compose the pipeline instead:

~~~java
@GetMapping("/good-work")
public Mono<Void> goodWork() {
    return service.doWork();
}
~~~

### 11.3. If you must call a blocking API

If you must integrate a blocking library, isolate that part on a scheduler meant for blocking:

~~~java
Mono<Result> result = Mono.fromCallable(
        () -> legacyClient.fetchBlocking()
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

This is a snippet that needs the imports **reactor.core.publisher.Mono** and **reactor.core.scheduler.Schedulers**. This approach avoids making the blocking call directly on the event loop, but it **does not turn a blocking library into a non-blocking one**. You still have to limit concurrency, timeouts, and thread resources, and consider replacing it with a reactive client when possible.

### 11.4. CPU-bound work

Heavy CPU computation tasks also need to be designed deliberately. You can use a suitable scheduler or move them to a separate worker pool; do not default to putting every task on boundedElastic. Choose the scheduler according to the nature of the work and measure under real load.

## 12. Common configurations and how to check them

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Application starts MVC instead of WebFlux | spring-boot-starter-web is on the classpath | Check the dependency tree and remove the unnecessary starter |
| Controller is not detected | The controller package is outside the component scan | Place it under the main class's package or configure the scan explicitly |
| Endpoint returns 404 | Wrong path, HTTP method, or the route is not registered | Check the mapping and the request |
| JSON is not serialized as expected | Codec/dependency or data type is unsuitable | Check Jackson and the response type |
| Large request body is rejected | Codec buffer limit | Assess the size and configure maxInMemorySize in a controlled way |
| CPU/threads are stalled | There is a block or blocking library on the event loop | Use a reactive API or isolate the blocking work |
| SSE Flux does not end | Flux.interval is an infinite stream | The client must cancel; if you need it finite, limit it with take(n) |
| WebTestClient test has no bean | Missing test configuration or the application is not running WebFlux | Check the starter, @AutoConfigureWebTestClient, and the test context |
| Port is already in use | Another process is using 8080 | Change server.port or stop the old process |
| Adding @EnableWebFlux loses Boot configuration | Switched to manual control of the WebFlux configuration | Remove the annotation if not truly needed |

### 12.1. Check the dependency tree

You can run:

~~~bash
mvn dependency:tree
~~~

Look for the related dependencies:

- spring-boot-starter-webflux
- reactor-core
- reactor-netty-http
- spring-boot-starter-web

If the application is meant to use pure WebFlux but the dependency tree also contains the MVC starter, find the transitive dependency that brings MVC in and decide whether you need it.

### 12.2. Check the endpoint configuration

If an endpoint does not work, follow this sequence:

1. Has the application started successfully?
2. Which port is the server listening on?
3. Is the controller/route in the ApplicationContext?
4. Do the HTTP method and path match the request?
5. Is there a filter/security rule blocking the request?
6. What data type does the handler return?
7. Does the codec support the data type and media type?
8. Is there an exception in the pipeline before the response is written?

Do not add lots of annotations/configuration to fix a 404 before determining whether the mapping is actually registered.

## 13. When should you add your own WebFlux configuration?

The hands-on lesson has a WebFluxConfigurer only to illustrate a codec customization. In a real project, add configuration only when there is a clear requirement:

- **Codec:** limit payload size, register encoders/decoders, or customize formats.
- **CORS:** only allow the necessary origins, methods, and headers; do not open a wildcard arbitrarily when credentials are involved.
- **WebFilter:** correlation ID, logging, security, or cross-cutting request handling.
- **WebClient:** base URL, timeout, connector, TLS, and filters per service.
- **Error handling:** convert exceptions into responses according to the API contract.
- **Resource management:** suitable connection limits, timeouts, and schedulers.

Prefer small configurations with the right responsibility. Do not create one large configuration class that gathers everything just because it all belongs to WebFlux. Also do not add @EnableWebFlux when a WebFluxConfigurer already meets the need.

## 14. Practice exercises

**Exercise 1 — Basic endpoint:** add GET /api/greet that takes the query parameter name and returns Mono<Map<String,String>>. Check the cases with and without name.

**Exercise 2 — Flux:** add GET /api/numbers that returns Flux<Integer> from Flux.range(1,5). Determine how the JSON array response differs from text/event-stream.

**Exercise 3 — SSE:** replace Flux.interval with Flux.interval(...).take(5). Check that the stream ends after five events and that the client receives the last event.

**Exercise 4 — Functional route:** create POST /functional/echo that takes a JSON body as Mono<Map<String,Object>> and returns the body back. Check the Content-Type and an invalid body.

**Exercise 5 — Codec:** send a payload larger than the maxInMemorySize limit. Observe the exception and decide on a reasonable limit based on the use case instead of increasing it indefinitely.

**Exercise 6 — Test:** add WebTestClient tests for the default parameter, status code, JSON path, and the functional route. Run the tests on a random port.

**Exercise 7 — Blocking:** create a simulated blocking function with a wait time; compare calling it directly with wrapping it in Mono.fromCallable and subscribeOn(boundedElastic). Do not use the result of a single run as a benchmark; observe threads and throughput under load.

**Exercise 8 — Dependency:** try adding spring-boot-starter-web to the project and then check which web application type Boot chooses. Then remove the dependency and confirm pure WebFlux.

## 15. Checklist before bringing WebFlux into a project

- Are the dependencies the right WebFlux stack, without accidentally pulling in MVC?
- Does the package scan cover controllers, configurations, and services?
- Do endpoints return a suitable Mono/Flux or Publisher, without blocking?
- No manual subscribing in controllers/services if the task belongs to the request?
- Do the HTTP codecs support the right payloads and have a reasonable memory limit?
- Have timeout, cancellation, and error handling been designed?
- Do SSE/streaming have reconnect/replay rules if the business needs them?
- Are WebClient and the database client truly reactive or still blocking?
- Do the server, port, logging, and profile configuration contain no secrets?
- Are endpoints tested with WebTestClient?
- Are there metrics/tracing to observe latency, errors, and resources?

## 16. Key takeaways

A minimal Spring WebFlux application needs **starter-webflux**, a Spring Boot main class, handlers that return a Publisher, and a suitable HTTP configuration. You can declare endpoints with **@RestController** or **RouterFunction**; both are integrated into the framework's reactive pipeline.

The value of WebFlux comes from keeping the processing chain non-blocking, managing demand/cancellation, and streaming data according to the proper lifecycle. Merely changing the return type to Mono/Flux while still calling blocking code or subscribing in a detached way will not produce a truly reactive application.

## 17. References

- Spring Boot Reference — Developing Reactive Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Framework Reference — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework Reference — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Framework Reference — Functional Endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Framework Reference — HTTP Message Codecs: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework Reference — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Project Reactor Reference Guide: https://projectreactor.io/docs/core/release/reference/
