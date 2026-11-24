# What is a web runtime and Spring Boot's role in serving HTTP requests

## Objectives and scope

This article explains the runtime environment of a Java web application, how Spring Boot initializes that environment, and the path of an HTTP request in a Spring Boot application using Spring MVC (Servlet stack). Examples use Java 17 or later and Spring Boot 3.x.

After completing this lesson, you will be able to distinguish between the JVM, web server, Servlet container, Spring MVC, and Spring Boot; describe the lifecycle of a request; create a minimal HTTP endpoint; and recognize common configurations and operational errors.

## 1. What is a web runtime?

A **web runtime** is the environment and active components that enable a web application to receive, process, and respond to requests over a network. For a Java application on the Servlet stack, the runtime typically includes:

- **JVM:** the process that executes Java bytecode and manages memory, garbage collection, and threads.
- **Web server / Servlet container:** opens network ports, accepts HTTP connections, parses requests, manages the lifecycle of Servlets and Filters, and dispatches requests to the application. Tomcat is a common Servlet container.
- **Spring Framework / Spring MVC:** provides dependency injection, URL-to-controller mapping, data binding, validation, exception handling, and request/response conversion.
- **Application code:** controllers, services, repositories, configuration, and business logic components.
- **Operational resources:** configuration, logging, database connections, HTTP clients, thread pools, connection limits, and system observability tools.

These components collaborate within a single process to serve requests. With the default Spring Boot Web configuration, Tomcat is embedded and runs inside the same JVM as the application; typically, there is no need to install a separate Tomcat server and deploy a WAR file onto it.

It is important to distinguish these concepts:

| Component | Role |
|---|---|
| JDK | Java development kit, including compiler and runtime |
| JVM | Executes bytecode and manages the Java process |
| Tomcat | Web server and Servlet container, accepts HTTP and executes Servlets |
| Spring MVC | Framework for handling requests using the controller and Servlet model |
| Spring Boot | Automates configuration, packaging, and launching Spring applications more conveniently |
| Application | Business logic written by the development team |

Spring Boot does not replace the HTTP server or handle the entire HTTP protocol itself. It wires and configures the appropriate components so the application can run with less manual configuration.

### Overall architecture

For a Spring MVC application using embedded Tomcat, a typical processing flow looks like this:

~~~mermaid
flowchart TD
    A[HTTP Client] --> B[Reverse Proxy / Load Balancer - if any]
    B --> C[Embedded Tomcat]
    C --> D[Servlet Filter Chain]
    D --> E[DispatcherServlet]
    E --> F[HandlerMapping]
    F --> G[HandlerAdapter]
    G --> H[Controller]
    H --> I[Service]
    I --> J[Repository / External Services]
    J --> I
    I --> H
    H --> K[HttpMessageConverter]
    K --> L[HTTP Response]
~~~

The diagram illustrates the common path. A specific request might not go through a repository or external service; requests serving static files also have their own handler.

## 2. What role does Spring Boot play in the web runtime?

When using Spring Boot with **spring-boot-starter-web**, Boot provides the startup mechanism and auto-configuration for a Spring MVC application.

### 2.1. Providing dependencies via starters

The **spring-boot-starter-web** dependency aggregates the libraries required for a Servlet web application, typically including Spring MVC, embedded Tomcat, and libraries supporting JSON data conversion such as Jackson.

Thanks to starters, a project does not need to declare each foundational library individually. Dependency versions are managed consistently according to the Spring Boot version.

### 2.2. Auto-configuration based on the classpath

Spring Boot inspects existing dependencies and configurations to create the necessary beans. In a typical Servlet MVC application, Boot configures the web application context, embedded server, **DispatcherServlet**, Spring MVC components, and HTTP message converters.

Auto-configuration is conditional: when an application adds libraries or declares corresponding beans itself, some default configurations may change or no longer be applied. Therefore, it is necessary to understand which dependencies are on the classpath and which configurations are overridden by the application.

### 2.3. Starting the server alongside the application

When running **SpringApplication.run(...)**, Spring Boot creates the ApplicationContext, registers beans, applies auto-configuration, and initializes the web server. When the context is refreshed, the embedded server is started and begins accepting requests.

Because the server is embedded, the application can be run with **java -jar** in development environments, servers, or containers. The build and deployment workflow is also simpler because the server and application are packaged together.

### 2.4. Managing configuration and lifecycle

Boot supports configuration via **application.properties**, **application.yml**, environment variables, and command-line arguments. This allows changing ports, context paths, TLS, or thread limits per environment without modifying source code.

Boot also integrates application lifecycle management, logging, default error handling, and graceful shutdown for the web server. Deeper observability features such as health checks and metrics can be added with Spring Boot Actuator.

## 3. How does the application start up?

A Spring Boot MVC application typically goes through the following steps:

1. The JVM launches the class containing the **main** method.
2. **SpringApplication.run(...)** creates an Environment and ApplicationContext suitable for a Servlet web application.
3. Component scan finds classes annotated with **@Component**, **@Service**, **@Repository**, and **@Controller**.
4. Auto-configuration creates foundational beans based on the classpath and configuration.
5. The web server factory creates an embedded server (typically Tomcat by default when using **spring-boot-starter-web**).
6. The ApplicationContext refreshes; the server starts and begins listening on the configured port.
7. The application emits a readiness event (**ApplicationReadyEvent**) once startup completes.

**@SpringBootApplication** is a composite annotation comprising three main parts:

- **@SpringBootConfiguration:** marks the primary configuration class.
- **@EnableAutoConfiguration:** enables the auto-configuration mechanism.
- **@ComponentScan:** scans for components in the current package and its subpackages.

Placing the main class in the root package of the application helps component scan easily discover controllers and services. If the main class is in the wrong package, controllers may not be detected even though the source code exists.

## 4. How does an HTTP request flow through the runtime?

For a request **GET /api/greetings?name=Lan**, a typical flow consists of the following stages.

### Step 1: Network connection and HTTP acceptance

The client resolves the domain name, establishes a TCP connection, and may perform a TLS handshake. In real-world deployments, a reverse proxy or load balancer may sit in front of the application and terminate TLS there.

Tomcat's Connector accepts the connection, parses the HTTP data, and creates Servlet API request/response objects. Port, TLS, header limit, and connection configurations affect this stage.

### Step 2: Servlet Filter Chain

The container invokes the Servlet Filter chain before the request reaches the target Servlet. Filters can read or modify the request/response, check access permissions, log, handle CORS, or set character encoding.

If the project uses Spring Security, the security filter chain is typically integrated at this stage. Simply adding **spring-boot-starter-web** does not automatically enable all Spring Security authentication and authorization mechanisms; the application must add and configure the appropriate security dependency.

### Step 3: DispatcherServlet receives the request

**DispatcherServlet** is the Front Controller of Spring MVC. It receives the request that passed through the filter chain and dispatches it to the appropriate handler.

Spring MVC uses key components:

- **HandlerMapping:** finds the controller method or handler matching the HTTP method, URL, and mapping conditions.
- **HandlerAdapter:** invokes the selected handler.
- **Argument resolvers:** extract data from paths, query parameters, headers, body, or other sources to construct method parameters.
- **HttpMessageConverter:** reads the body—for example, JSON into a Java object—and converts the returned object into response data.

### Step 4: Interceptor and Controller

Spring MVC has **HandlerInterceptor**, allowing logic to run before the controller (**preHandle**), after the controller processes (**postHandle**), and when the request finishes (**afterCompletion**). Interceptors operate inside the Spring MVC flow, after the handler lookup step.

Filters and interceptors have different scopes: Filters belong to the Servlet container and can wrap many types of Servlets; interceptors are tied to Spring MVC handlers. Security requirements at the HTTP layer are usually placed in the Spring Security filter chain.

The controller receives the bound data, validates input conditions, and calls a service to perform business logic. Controllers should focus on HTTP communication; business rules should reside in services for easier testing and reuse.

### Step 5: Business logic processing

The service may call a repository to access the database, invoke an HTTP client to another system, or coordinate multiple components. These operations often directly affect request processing time.

In traditional Servlet MVC, synchronous calls typically hold a worker thread for the entire processing duration. If a database query or external service call is slow, the thread serving the request can be held for a long time.

### Step 6: Creating the HTTP response

The return value from the controller is processed by Spring MVC. With **@RestController**, the object is typically converted to JSON by a suitable **HttpMessageConverter**, such as Jackson.

The response is written back to the Servlet response, travels back through the filter chain so filters can add headers or perform final processing, and is sent to the client. HTTP status, response headers, and body are three crucial parts to inspect when debugging.

### Step 7: Exception handling

If a controller or service throws an exception, Spring MVC looks for a matching handler mechanism, such as **@ExceptionHandler** or **@ControllerAdvice**. If no suitable handler exists, the exception may become an HTTP 500 error and be handled by Spring Boot's default error mechanism.

Do not return stack traces or internal details to clients in production environments. Log with context on the server side and return a consistent error message that does not expose sensitive data.

## 5. Creating a minimal Spring Boot HTTP application

The following example creates an endpoint that returns a greeting in JSON format.

### Project structure

~~~text
web-runtime-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/webruntime/
        │       ├── WebRuntimeApplication.java
        │       └── GreetingController.java
        └── resources/
            └── application.yml
~~~

### 5.1. Maven declaration

Create **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>web-runtime-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>web-runtime-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 5.2. Startup class

Create **src/main/java/com/example/webruntime/WebRuntimeApplication.java**:

~~~java
package com.example.webruntime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebRuntimeApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }
}
~~~

### 5.3. REST Controller

Create **src/main/java/com/example/webruntime/GreetingController.java**:

~~~java
package com.example.webruntime;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {

    @GetMapping
    public GreetingResponse greet(
            @RequestParam(defaultValue = "friend") String name) {
        return new GreetingResponse("Hello, " + name);
    }

    public record GreetingResponse(String message) {
    }
}
~~~

Explanation:

- **@RestController** marks the controller as returning data directly in the response body.
- **@RequestMapping("/api/greetings")** sets the base URL for the controller.
- **@GetMapping** maps HTTP GET requests to the **greet** method.
- **@RequestParam** extracts the query parameter **name**; if the client does not send it, the default value is **friend**.
- **GreetingResponse** is a Java record. Jackson can serialize records into JSON.

### 5.4. Running the application and sending a request

JDK 17+ and Maven are required. In the directory containing **pom.xml**, run:

~~~bash
mvn spring-boot:run
~~~

Once the server starts successfully, send a request from another terminal:

~~~bash
curl "http://localhost:8080/api/greetings?name=Lan"
~~~

On Windows PowerShell, you can explicitly invoke **curl.exe**:

~~~powershell
curl.exe "http://localhost:8080/api/greetings?name=Lan"
~~~

Expected response body:

~~~json
{"message":"Hello, Lan"}
~~~

This request illustrates the entire chain: Tomcat receives HTTP, the filter chain is invoked, DispatcherServlet locates **GreetingController**, Spring binds the **name** query parameter, the controller returns the record, and Jackson converts the record to JSON.

You can package and run the JAR:

~~~bash
mvn clean package
java -jar target/web-runtime-demo-0.0.1-SNAPSHOT.jar
~~~

The build command produces an executable JAR file. When running the JAR, the embedded server is still started inside the JVM; there is no need to deploy the application onto a separately installed Tomcat.

## 6. Configuring the web runtime

Spring Boot allows configuring the server in **src/main/resources/application.yml**.

Example changing the port, context path, and some Tomcat thread limits:

~~~yaml
server:
  port: 8081
  servlet:
    context-path: /app
  tomcat:
    threads:
      max: 200
      min-spare: 10
    accept-count: 100
~~~

After this configuration, the example endpoint is accessed at:

~~~text
http://localhost:8081/app/api/greetings?name=Lan
~~~

Meaning of the properties:

- **server.port:** the HTTP port the embedded server listens on.
- **server.servlet.context-path:** the common URL prefix for the application.
- **server.tomcat.threads.max:** the maximum number of worker threads in the request-processing thread pool.
- **server.tomcat.threads.min-spare:** the minimum number of idle worker threads Tomcat tries to maintain.
- **server.tomcat.accept-count:** the queue length for incoming connection requests when all worker threads are busy, subject to connector limits and handling.

Do not increase the thread pool arbitrarily. If the application is bottlenecked by the database connection pool or external services, increasing threads can increase the number of requests waiting at the dependency layer and cause the system to overload faster.

### Environment-specific configuration

Values that change across local, staging, and production should be externalized outside source code. You can set defaults in YAML and override them via environment variables or runtime arguments.

For example, **SERVER_PORT** can be set in the deployment environment to change the port without editing configuration files. For TLS, database passwords, or API keys, use a secret manager or appropriate environment variables; never commit secrets to Git.

If enabling HTTPS directly on the embedded server, configure a valid certificate and private key. In many systems, TLS is terminated at a reverse proxy/load balancer; in that case, configure proxy headers properly so the application recognizes the original request scheme and address.

### Graceful shutdown

During deployment, the application should have time to finish in-flight requests before the process terminates completely. Spring Boot supports graceful shutdown for the embedded web server. You can configure the timeout as needed:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

The timeout should align with the deployment platform's timeout and actual request processing times.

## 7. Servlet MVC vs. Reactive WebFlux

Spring Boot supports two popular web models. Choose a model based on how the application handles I/O and the desired architecture.

| Criterion | Spring MVC (Servlet) | Spring WebFlux |
|---|---|---|
| Starter | spring-boot-starter-web | spring-boot-starter-webflux |
| Common default runtime | Tomcat | Reactor Netty |
| Processing model | Typically synchronous, blocking | Reactive, supports non-blocking |
| API | Servlet API, Spring MVC | Reactive Streams, Mono, Flux |
| Best suited for | CRUD applications, synchronous business logic, Servlet ecosystem | Asynchronous I/O flows, streaming, or high concurrency when dependencies are also non-blocking |

WebFlux does not automatically make every task faster. If reactive code calls blocking libraries, non-blocking benefits can be lost and the event loop can become blocked. Likewise, MVC remains the right choice for many standard business applications.

The two stacks can share some similar controller annotations, but their runtimes and execution models differ. If both **spring-boot-starter-web** and **spring-boot-starter-webflux** are added, Spring Boot usually prioritizes configuring MVC when both are present. Only add both when you clearly understand the purpose and auto-configuration behavior.

## 8. Threads, connections, and performance

In Servlet MVC, Tomcat typically uses a thread pool to process requests. Threads are reused across multiple requests over time; a new thread is not necessarily created for each request.

When a request performs a blocking operation such as a JDBC query or a synchronous HTTP call, the worker thread usually has to wait for that operation to complete. If many requests wait on a slow service simultaneously, the thread pool can exhaust its worker threads and new requests must wait in a queue or be rejected.

When analyzing performance, examine simultaneously:

- Processing time in the controller/service and wait time for the database or external services.
- Number of busy worker threads, request queue, and open connections.
- Size of the database connection pool and connection limits of dependent services.
- Timeouts for HTTP clients, JDBC, and the overall request.
- Memory, CPU, garbage collection, and payload size.

Set explicit timeouts for external calls, avoid holding transactions or locks for long periods, and limit load at dependency points. The thread pool is only one part of processing capacity; overall performance depends on the slowest link in the request path.

## 9. Common errors when running the application

| Symptom | Common cause | What to check |
|---|---|---|
| Application fails to start, reports port in use | Another process is already listening on the configured port | Check which process occupies the port or change server.port |
| HTTP 404 | Wrong URL, wrong context path, or controller not scanned | Check mappings, main class package, and context path |
| HTTP 405 | URL exists but HTTP method is not supported | Check GetMapping, PostMapping, and the method sent by the client |
| HTTP 400 | Query/path parameter fails binding or invalid data | Check data types, body format, and validation |
| HTTP 415 | Content-Type does not match the sent payload | Check the Content-Type header and message converters |
| HTTP 500 | Unhandled exception in the application | Inspect stack trace in server logs and check service/repository |
| Slow response or timeout | Long-running DB query, HTTP call, lock, or blocking work | Measure each dependency's latency, inspect thread pool, and set timeouts |

Some useful commands when debugging:

~~~bash
# View response status, headers, and body
curl -i "http://localhost:8080/api/greetings?name=Lan"

# View detailed connection and HTTP exchange process
curl -v "http://localhost:8080/api/greetings?name=Lan"
~~~

You can temporarily increase log levels in development:

~~~yaml
logging:
  level:
    org.springframework.web: DEBUG
~~~

Do not leave overly verbose logging enabled long-term in production without evaluating the impact on performance and sensitive data. When health checks or metrics are needed, you can add **spring-boot-starter-actuator** and expose only endpoints that comply with security policies.

## 10. Deployment checklist

- Use a JDK version compatible with the chosen Spring Boot version.
- Verify that the web starter and web stack match the architecture.
- Set port, context path, TLS, and proxy headers appropriately for the environment.
- Configure timeouts for the database and external services.
- Configure pools, connection limits, and resources according to actual capacity.
- Log with request context without exposing tokens, passwords, or sensitive data.
- Set up health checks, metrics, and alerts for errors, latency, CPU, memory, and thread pools.
- Test graceful shutdown and restart behavior in the deployment platform.
- Return consistent status codes and errors; do not send internal stack traces to clients.

## 11. Summary

The web runtime is the collection of the execution environment and components that receive, process, and respond to HTTP requests. In a Spring Boot Servlet MVC application, the JVM runs the application; embedded Tomcat accepts connections and executes Servlets; the filter chain handles Servlet-layer concerns; **DispatcherServlet** dispatches to controllers; services execute business logic; and **HttpMessageConverter** converts response data.

Spring Boot helps wire these components via starters, auto-configuration, embedded servers, externalized configuration, and lifecycle management. Understanding each layer clearly helps pinpoint exactly where to troubleshoot issues with connectivity, routing, security, data binding, performance, or deployment.
