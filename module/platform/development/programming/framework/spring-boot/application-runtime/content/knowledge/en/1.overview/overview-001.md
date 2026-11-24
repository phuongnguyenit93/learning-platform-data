# What Is the Application Runtime in Spring Boot and What Does It Manage?

## 1. What is the application runtime?

An **application runtime** is the entire environment and set of active components when an application has been launched: the running process, the Java Virtual Machine, loaded configuration, application objects, resources, processing threads, work-receiving components, and the application shutdown mechanism. In short, it is **what must be present and what takes place for application code to actually run**, from startup until termination.

In Spring Boot, three closely related concepts should be distinguished:

- **JVM runtime:** The JVM executes Java bytecode, manages heap memory, garbage collection, class loading, and Java threads. The JVM does not natively understand Spring concepts such as beans, dependency injection, or HTTP controllers.
- **Spring ApplicationContext:** Spring's bean container, responsible for configuring, instantiating, wiring dependencies, and managing bean lifecycles.
- **Spring Boot application runtime:** The running application with the JVM, ApplicationContext, and components initialized or auto-configured by Boot, such as an embedded web server, data source, executor, scheduler, and observability systems. Not every application has all of these components.

For example, a Spring Boot API receiving HTTP requests has a runtime with an open network port, handles requests, uses service beans, and may access a database. A Spring Boot program that only runs background jobs still has a runtime and an ApplicationContext, but may **have no HTTP server**.

## 2. Layers that make up the runtime

| Layer | Typical components | Who is primarily responsible? |
| --- | --- | --- |
| Operating system / container | Process, CPU, available memory, files, sockets, stop signals | OS, container runtime, deployment platform |
| Java Virtual Machine | Bytecode execution, class loading/JIT, heap, GC, Java threads | JVM |
| Spring Boot bootstrap | Reading configuration, selecting application type, initializing ApplicationContext, applying auto-configuration | Spring Boot and Spring Framework |
| Spring ApplicationContext | Bean definitions, dependency injection, scope, lifecycle, application events | Spring Framework |
| Application infrastructure (if configured) | Embedded HTTP server, connection pool, scheduler/executor, transaction manager, security filter chain | Corresponding libraries, integrated/auto-configured by Boot |
| Business logic | Controller, service, repository, business rules and data | Code written by the development team |

Overview diagram:

~~~text
Operating System / Container
    └── java Process / JVM
          └── SpringApplication.run(...)
                └── Spring ApplicationContext
                      ├── Application beans (Controller, Service, Repository, ...)
                      ├── Infrastructure beans (DataSource, Executor, ...)
                      └── Embedded web server (if it is a web application)
~~~

**Note:** Spring Boot helps create and configure components. It does not replace the JVM in allocating heap/GC, does not replace the OS in managing CPU, and does not replace the database in storing data.

## 3. Lifecycle: how is the runtime formed, how does it serve, and how does it terminate?

### Phase A — Process startup

When running **java -jar app.jar** or running with Maven/Gradle, the operating system creates a Java process, the JVM loads classes, and the application's **main()** method calls **SpringApplication.run(...)**. Spring Boot prepares the **Environment** to look up configuration from the appropriate sources: application.properties/application.yml files, environment variables, command-line arguments, and other supported sources. **Spring profiles** can determine which configurations or beans take effect.

### Phase B — Building the ApplicationContext

Spring Boot selects the appropriate ApplicationContext type and applies auto-configuration based on the classpath, properties, and configuration conditions. Spring scans and registers beans, resolves dependencies, runs extension mechanisms, and initializes required beans.

For example, if Spring Web MVC and appropriate web configuration are present, Boot typically builds an embedded servlet web server (such as Tomcat) and MVC components. With WebFlux, the runtime may use a reactive HTTP runtime such as Reactor Netty. For a non-web application, the runtime does not need to open an HTTP port.

Bean initialization hooks such as **@PostConstruct** only prove that a single bean has been initialized; they **do not mean the entire application is ready to receive traffic**.

### Phase C — Completing startup and receiving work

Once the context has been refreshed, Spring Boot runs **ApplicationRunner** and **CommandLineRunner** beans. After the necessary startup steps finish, **ApplicationReadyEvent** signals that the application has completed the startup process on the Spring Boot side. In systems with an orchestrator, readiness to receive traffic may also depend on readiness probes and dependency checks.

In the active state, the runtime performs one or more kinds of work: receiving HTTP requests, consuming messages, running jobs, or processing scheduled tasks. Spring invokes the appropriate beans; infrastructure libraries provide connection pools, transactions, thread pools, or other mechanisms if included in configuration.

### Phase D — Stopping and releasing resources

When the application receives a normal stop signal, Spring closes the ApplicationContext and executes lifecycle callbacks such as **@PreDestroy**, **DisposableBean**, or bean destroy methods. Properly managed resources (pools, executors, connections, etc.) need to be closed. When **graceful shutdown** is enabled for the HTTP server, the server can stop accepting new work and give in-flight requests time to finish according to the configured timeout. Forceful commands like **SIGKILL** do not guarantee that cleanup callbacks will run.

Overall lifecycle:

~~~text
START → JVM → SpringApplication → Environment/Auto-configuration
      → ApplicationContext/Beans → Runners → READY
      → Processing work → Shutdown → Close context/resources → STOP
~~~

## 4. What does the runtime manage in practice?

### 4.1. Configuration and profiles

Spring's **Environment** provides a way to retrieve properties and active profiles. Configuration affects ports, timeouts, external service addresses, log levels, and how beans are initialized. **@ConfigurationProperties** helps map a group of configurations into a strongly typed object.

Distinguish between the **Spring Environment** (the configuration lookup mechanism inside the application) and **deployment environments dev/test/staging/prod**. An application can use the same artifact while using different configurations in each environment. Configuration bound at startup usually does not update automatically just because a file is edited; dynamic refresh requires a dedicated supporting mechanism.

### 4.2. Beans and dependency injection

**ApplicationContext** creates, wires, provides, and manages bean lifecycles. With the default singleton scope, one instance is shared within the context; other scopes have their own rules. The context handles the lifecycle of Spring-managed beans; it does not implicitly manage every object created with the **new** operator anywhere in code.

Example: Controller calls Service; Service is injected with Repository; Repository uses DataSource. The runtime connects the components according to configuration, while the business algorithms reside inside those classes themselves.

### 4.3. Receiving requests and executing work

For web applications, the embedded HTTP server listens on a port, accepts connections, and passes requests into the framework's processing chain (filters, dispatcher/handler, controllers, etc.). For jobs, consumers, or scheduled tasks, work is triggered through the corresponding mechanism rather than HTTP. **There is no rule that every Spring Boot runtime must open port 8080**; the port can change or not exist at all.

### 4.4. Threads, executors, and schedulers

The JVM provides execution threads. The web server, asynchronous processing libraries, **TaskExecutor**, and **TaskScheduler** may use thread pools. Spring integrates and manages the lifecycle of these infrastructure beans when they are declared or auto-configured. Features like **@Async** or **@Scheduled** require proper activation/configuration conditions; adding an annotation does not mean Spring will automatically manage every kind of background task safely.

You should set bounds on pools, queues, timeouts, and shutdown behavior; creating too many threads or unbounded tasks can exhaust application resources.

### 4.5. Connections and transactions

When using JDBC/JPA, the runtime may have a **DataSource** and connection pool (often HikariCP in a suitable JDBC configuration), along with a transaction manager. The pool lends and reclaims connections for tasks, while the transaction manager coordinates transaction boundaries if transaction support is enabled. **The database server remains an external system**; Spring does not manage the memory or storage durability of the database server itself.

### 4.6. Security and observability

When Spring Security is integrated, the filter chain and security components participate in request processing. Logging helps observe errors and events; with **Spring Boot Actuator** and related libraries, the application can expose health, metrics, and operational information. Which endpoints and data are exposed depends on dependencies, configuration, and security policies.

The runtime does not automatically guarantee that an application is healthy: a Java process remains alive even if a critical dependency is failing or requests continuously time out. You must distinguish between **liveness** (whether the process needs to be restarted) and **readiness** (whether it should receive traffic yet) when deploying with an orchestration platform.

## 5. Java 17+ example: observing the runtime in action

Create a Spring Boot project using Spring Initializr, choose **Java 17 or later**, **Maven**, and the **Spring Web** dependency. Replace the contents of **src/main/java/com/example/demo/RuntimeDemoApplication.java** with:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class RuntimeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimeDemoApplication.class, args);
    }

    @GetMapping("/runtime")
    public Map<String, String> runtime() {
        return Map.of("status", "RUNNING");
    }

    @Bean
    public ApplicationRunner afterStartup() {
        return args -> System.out.println("ApplicationRunner executed");
    }

    @Bean(destroyMethod = "close")
    public RuntimeResource runtimeResource() {
        return new RuntimeResource();
    }

    public static final class RuntimeResource implements AutoCloseable {
        public RuntimeResource() {
            System.out.println("RuntimeResource created");
        }

        @Override
        public void close() {
            System.out.println("RuntimeResource closed");
        }
    }
}
~~~

In this example:

1. **SpringApplication.run** builds the runtime and context.
2. **@RestController** creates the GET /runtime endpoint, served by the web server configured by Spring Boot.
3. **ApplicationRunner** runs after the context is initialized, before the **ApplicationReadyEvent** milestone.
4. **RuntimeResource** is a singleton bean created and closed by Spring via **destroyMethod = "close"** when the context terminates normally.

Run the application from the generated Maven project directory:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows, use the equivalent command:
# mvnw.cmd spring-boot:run

# Open a second terminal:
curl http://localhost:8080/runtime
~~~

Expected HTTP response body:

~~~json
{"status":"RUNNING"}
~~~

The logs will contain the lines printed by the example itself (interleaved with Spring Boot logs):

~~~text
RuntimeResource created
ApplicationRunner executed
~~~

Use **Ctrl+C** to stop the application normally; you can observe:

~~~text
RuntimeResource closed
~~~

Note: the example requires the Spring Boot project classpath/dependencies; it cannot be compiled solely with **javac RuntimeDemoApplication.java** without declaring Spring libraries. If port 8080 is already in use or server configuration changes the port, adjust the curl address accordingly.

### Experimenting with runtime configuration

Place the following content in **src/main/resources/application.yml**:

~~~yaml
server:
  port: 8081
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

After restarting, call **http://localhost:8081/runtime**. This configuration changes the HTTP port and requests graceful shutdown within the allowed time. The 20-second timeout is a limit on the shutdown phase, **not a guarantee that every task or every resource will finish** before the process is stopped.

If you add the **Spring Boot Actuator** dependency, you can use appropriately configured and secured health endpoints to monitor the runtime. This is an optional component and is not automatically included in an example that only declares Spring Web.

## 6. How far does Spring Boot manage, and what lies outside its scope?

| Situation | Primarily responsible component |
| --- | --- |
| Bean instantiation, dependency injection, lifecycle callbacks | Spring ApplicationContext |
| Selecting auto-configuration and building infrastructure based on dependencies/properties | Spring Boot |
| Garbage collection, bytecode execution, JVM heap management | JVM |
| Container CPU/memory limits, process scheduling, pod restarts | OS, container runtime, orchestrator |
| Receiving HTTP requests | Embedded web server and corresponding web framework |
| Opening/reclaiming connections in the application pool | Connection-pool library / DataSource |
| Durable data storage, replication, database backups | Database management system and administration platform |
| Business rules, business error handling, idempotency | Development team's application code |

This demarcation is very important when troubleshooting incidents. For example, Spring can close the pool when closing the context, but it **cannot change** container memory limit settings; an application may restart automatically after an error if the orchestrator configures restarts, whereas Spring Boot does not automatically restart the entire process in all cases.

## 7. Common misconceptions

- **"The runtime is the JVM."** The JVM is only the Java execution layer. The Spring Boot runtime also includes the Spring context, application configuration, and initialized infrastructure components.
- **"Using Spring Boot always means having a web server."** Command-line, batch, or background worker applications can run without an HTTP server.
- **"@PostConstruct means the application is ready to receive requests."** This hook belongs to a single bean's lifecycle; use an appropriate readiness mechanism to assess the entire application's ability to accept traffic.
- **"Editing application.yml makes the runtime automatically load the new configuration."** Many properties and beans are determined at startup; changes require a restart or a specifically designed refresh mechanism.
- **"Spring manages all threads, databases, and memory."** The JVM, libraries, database, and OS have different responsibilities. Many resources must have limits configured and be closed properly by the development team.
- **"Any way of stopping the process cleans up everything."** Forceful termination can skip lifecycle callbacks; systems must be designed to tolerate interruption, especially for background tasks and transactions.

## 8. Checklist when operating a Spring Boot runtime

1. **Startup:** Can the application create the ApplicationContext, load the right profile/config, and initialize all required dependencies?
2. **Serving:** Are the web port/consumers/schedulers operating as expected? Which synchronous or asynchronous mechanisms process work?
3. **Resources:** Do heap, thread pools, connection pools, timeouts, file handles, and queues have reasonable limits?
4. **Observability:** Do logs have enough information; are health/readiness/metrics enabled and properly protected?
5. **Shutdown:** Does the application stop accepting new work, finish/roll back in-flight tasks, and release beans/resources within the allowed time?

**Conclusion:** When speaking of the "application runtime in Spring Boot," picture a **running system** consisting of JVM + ApplicationContext + configuration + infrastructure components and business logic. Spring Boot simplifies creating and operating that system; understanding the management boundaries of each layer helps you develop, monitor, and troubleshoot accurately.