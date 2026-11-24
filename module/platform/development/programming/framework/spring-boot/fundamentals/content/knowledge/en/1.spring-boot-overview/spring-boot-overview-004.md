# Relationships Among Spring Boot, Spring MVC, WebFlux, Spring Data, and Spring Security

When building Java applications with the Spring ecosystem, we frequently encounter five names: **Spring Boot**, **Spring MVC**, **Spring WebFlux**, **Spring Data**, and **Spring Security**. They are closely related, yet they solve **different categories of problems**. Understanding these relationships helps you choose the right libraries, trace request processing flows, and avoid confusing web, data access, and security mechanisms.

A Spring Boot application might use only Spring MVC, only WebFlux, or not expose any HTTP API at all. Spring Data and Spring Security are capabilities added as needed, not mandatory layers in every Boot application.

## 1. Big Picture: What Does Each Component Do?

| Component | Main Responsibility | Question It Helps Answer |
|---|---|---|
| **Spring Framework** | Foundation for IoC/Dependency Injection, bean management, configuration, transactions, web integration, and more | How are application objects created, connected, and run? |
| **Spring Boot** | Quickly initialize and configure Spring applications via starters, auto-configuration, dependency version management, and operational utilities | How do we assemble Spring components into a runnable application with minimal manual setup? |
| **Spring MVC** | Build HTTP APIs and web applications on the **Servlet stack** | How do we accept requests, route to controllers, and produce responses under the Servlet model? |
| **Spring WebFlux** | Build HTTP APIs and web pipelines under the **reactive** model, supporting non-blocking I/O | How do we process asynchronous data streams with `Mono`/`Flux`? |
| **Spring Data** | Provide ways to work with data stores via repositories, templates, and technology-specific integrations | How do we query, persist, and map data with minimal boilerplate? |
| **Spring Security** | Authentication, authorization, and application protection; provides integrations for both Servlet and reactive stacks | Who is accessing the app, what actions are they permitted to perform, and how are requests protected? |

**Key point:** Spring Boot is the layer that assists with **assembling and operating** a Spring application; MVC/WebFlux handles **web**; Spring Data handles **data**; Spring Security handles **security**. They are not five competing alternatives that replace one another.

Simple responsibility diagram:

~~~text
                     SPRING BOOT APPLICATION
              (bootstrap, starters, auto-configuration)
                              │
                      Spring Framework
                    (IoC/DI, beans, config)
                              │
             ┌────────────────┼──────────────────┐
             │                │                  │
          WEB LAYER        DATA LAYER        SECURITY
             │                │                  │
       Spring MVC       Spring Data JPA      Spring Security
           or                 or             (Servlet)
       Spring WebFlux   Spring Data R2DBC        or
                          or another type    Spring Security
                                              (Reactive)
~~~

This is a **role** diagram, not a class inheritance diagram. Security typically participates **before** a request reaches a controller, while Spring Data is typically called by a service when saving or retrieving data.

## 2. Where Does Spring Boot Stand Relative to the Spring Framework?

The Spring Framework is the foundation providing `ApplicationContext`, beans, Dependency Injection, transactions, and web modules such as Spring MVC/WebFlux. Spring Boot builds on that foundation to reduce application setup effort:

1. **Starter dependencies** group libraries that commonly go together for a given need, such as `spring-boot-starter-web` or `spring-boot-starter-data-jpa`.
2. **Auto-configuration** inspects libraries present on the classpath, beans declared by the application, and configuration properties to automatically register appropriate beans.
3. **Embedded server and application launch** help package a standalone HTTP service; for example, Spring MVC typically runs on an embedded Servlet container.
4. **Externalized configuration and operations** support environment-specific configuration, logging, and health/metrics when matching components are added.

Familiar entry point:

~~~java
@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@SpringBootApplication` combines key capabilities such as Spring configuration, component scanning, and enabling auto-configuration. However, **Boot does not automatically turn every Spring library into part of your application**: which components are used still depends on actual dependencies and configuration.

For example, adding `spring-boot-starter-web` usually causes Boot to configure a Spring MVC environment with a Servlet container. Replacing it with `spring-boot-starter-webflux` lets Boot configure a reactive web application. Adding `spring-boot-starter-security` activates default security configuration when the application has not declared its own matching configuration.

## 3. Spring MVC and WebFlux: Two Ways to Build the Web Layer

Both Spring MVC and Spring WebFlux can declare controllers using `@RestController`, `@GetMapping`, `@RequestBody`, handle JSON, and return HTTP responses. Similarity in annotations **does not mean the two execution models are the same**.

### 3.1. Spring MVC: Servlets and the Common Processing Flow

Spring MVC is built on the **Servlet API**. `DispatcherServlet` receives requests and dispatches them to the matching controller. The common model handles each request on a Servlet thread, which may wait while calling JDBC, JPA, or external services.

~~~text
HTTP request
  → Servlet container
  → Servlet filters / Spring Security
  → DispatcherServlet
  → Controller → Service → Repository
  → HTTP response
~~~

Example MVC controller with a Spring Data JPA repository:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductMvcController {
    private final ProductJpaRepository repository;

    ProductMvcController(ProductJpaRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    Product findOne(@PathVariable Long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}

interface ProductJpaRepository extends JpaRepository<Product, Long> {
}
~~~

Here `Product` is a JPA entity mapped to a database table. `findById` returns `Optional<Product>`; typical JDBC/JPA queries are **blocking**. This model fits many CRUD applications, transactional business logic, and projects using JDBC/JPA.

Spring MVC also supports asynchronous techniques, but its request-processing foundation remains the **Servlet stack**; therefore, you should not equate MVC with "everything is always synchronous."

### 3.2. Spring WebFlux: Reactive Programming

Spring WebFlux is designed for the **Reactive Streams** model. Rather than always returning an already computed object, a handler can return a publisher describing results that will arrive in the future:

- `Mono<T>`: emits at most **one** value, or completes empty, or emits an error.
- `Flux<T>`: emits **0 to many** values, either finite or long-lived streams.
- **Backpressure**: the subscriber can regulate how much data it requests from the publisher according to the Reactive Streams protocol.

A reactive web processing flow typically looks like this:

~~~text
HTTP request
  → Reactive HTTP runtime
  → Reactive WebFilters / Spring Security
  → DispatcherHandler
  → Controller/Handler → Service → Reactive Repository
  → Mono/Flux → HTTP response
~~~

Equivalent example using Spring Data R2DBC:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductReactiveController {
    private final ProductReactiveRepository repository;

    ProductReactiveController(ProductReactiveRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    Mono<Product> findOne(@PathVariable Long id) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }
}

interface ProductReactiveRepository
        extends ReactiveCrudRepository<Product, Long> {
}
~~~

In this example, `Product` must be mapped appropriately for Spring Data R2DBC; you cannot assume JPA entities and R2DBC mappings are always equivalent. The repository returns `Mono<Product>` and uses an appropriate **R2DBC driver** to access the database reactively.

WebFlux can use Reactor Netty or run on certain Servlet containers that support non-blocking I/O. The defining characteristic is **reactive processing**, not simply the name of the HTTP server.

### 3.3. Should You Choose MVC or WebFlux?

| Criterion | Spring MVC | Spring WebFlux |
|---|---|---|
| Web model | Servlet stack | Reactive stack |
| Common controller return types | POJO, `ResponseEntity<T>`, async types supported | `Mono<T>`, `Flux<T>`, and other supported return types |
| Typical I/O mechanism | Blocking with JDBC/JPA | Non-blocking when **related dependencies** support reactive |
| Common SQL access pairing | Spring Data JPA/JDBC | Spring Data R2DBC |
| Common use cases | CRUD, transactional business apps, systems with blocking libraries | High-concurrency I/O tasks, streams, pipelines with reactive clients/drivers |
| Key considerations | Threads waiting on I/O, resource sizing | Never block event-loop threads; manage backpressure, lifecycle, errors, and reactive transactions |

**WebFlux is not automatically faster than MVC.** Benefits depend on workload, I/O patterns, machine resources, drivers, architecture, and actual measurements. If a WebFlux controller still calls synchronous JPA/JDBC, that operation still blocks the executing thread; merely wrapping a return type in `Mono` does not make the query non-blocking.

In a Boot application, if both the MVC and WebFlux starters are present, **Boot defaults to configuring a Servlet/MVC application**. A valid reason to add WebFlux libraries to an MVC application is using `WebClient` to make outbound HTTP calls; doing so does not switch the server to WebFlux. The application type can be configured explicitly when genuinely needed.

## 4. Spring Data Is the Data Access Layer, Independent of the Web Choice

Spring Data is not a database, nor is it synonymous with JPA. It is a family of projects providing abstractions and storage integrations such as:

- **Spring Data JPA**: repositories for JPA, commonly using Hibernate as the JPA provider and JDBC for SQL access.
- **Spring Data JDBC**: relational database access with a simpler aggregate model than JPA, built on JDBC.
- **Spring Data R2DBC**: relational database access via reactive drivers.
- **Spring Data MongoDB**: supports synchronous or reactive access depending on the chosen driver and API.
- Other modules depending on the data store type.

Example of two repository types sharing the same business intent but having different execution contracts:

~~~java
// JPA: blocking-style query.
interface OrderJpaRepository extends JpaRepository<OrderEntity, Long> {
    Optional<OrderEntity> findByCode(String code);
}

// R2DBC: reactive-style query.
interface OrderR2dbcRepository
        extends ReactiveCrudRepository<OrderRow, Long> {
    Mono<OrderRow> findByCode(String code);
}
~~~

`OrderEntity` and `OrderRow` represent two separate mapping models specific to each technology. Spring Data generates repository implementations based on the enabled module and metadata. Business logic should still live in **services**, rather than making repositories responsible for authentication, authorization, or HTTP routing.

Important relationships:

- **MVC + Spring Data JPA** is a very common combination: controllers call services, services use repositories, and SQL queries run over JPA/JDBC.
- **WebFlux + Spring Data R2DBC** is an end-to-end reactive combination: publishers can flow from the HTTP handler down to the database driver.
- **MVC + a reactive data API** can happen, but you must understand exactly where the bridge between the two models sits.
- **WebFlux + JPA** can also be wired into a system, yet JPA remains blocking. If you are forced to call it, you must offload blocking work away from event-loop threads; this integration carries overhead and limits and does not replace a reactive driver.

Transactions also differ in context: with JPA, transactions are typically bound to the execution thread; with reactive, transactions are managed via the **reactive execution context** and must properly wrap the publisher/operator chain. You cannot take JDBC/JPA transaction management verbatim and apply it to R2DBC.

## 5. Spring Security Protects Both MVC and WebFlux

Spring Security is an independent part of the Spring ecosystem that integrates into the **HTTP processing chain** and can also protect business methods. Two foundational concepts:

- **Authentication:** verifying who the principal accessing the system is, such as via sessions, HTTP Basic, or Bearer tokens.
- **Authorization:** determining which endpoints or operations an authenticated principal is permitted to access.

In Servlet/MVC, Spring Security uses a **Servlet filter chain**, usually configured via `SecurityFilterChain` and `HttpSecurity`. In WebFlux, it uses a reactive **WebFilter chain**, configured via `SecurityWebFilterChain` and `ServerHttpSecurity`.

### 5.1. Configuration Example for Spring MVC

~~~java
@Configuration
class MvcSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

### 5.2. Configuration Example for Spring WebFlux

~~~java
@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/api/public/**").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

The two snippets illustrate **two alternative applications**, each using the security chain matching its web stack. They assume the application has a mechanism providing user details appropriately. HTTP Basic is only an illustrative choice; real applications may use sessions, OAuth2/OIDC, or JWT depending on architecture.

Security can also enforce access control at the service layer using method security, such as `@PreAuthorize` when enabled. This is helpful because a business operation can be invoked from multiple entry points, not just one HTTP endpoint.

Note that **CORS, CSRF, and authorization are distinct concerns**. Configure them based on client type, cookie/session versus token usage, and real threats; do not disable CSRF just to make a test request succeed. Having Spring Security also does not mean every route automatically has the right business policy: developers must still declare and test required access rules.

## 6. How Components Collaborate in a Real Request

Consider an API `GET /api/orders/42` that requires an authenticated user and queries the database.

### Architecture A: Boot + MVC + Spring Data JPA + Security

~~~text
Client
  │ GET /api/orders/42
  ▼
Embedded Servlet container (configured by Boot)
  ▼
Spring Security servlet filters
  │ authenticate and check permissions
  ▼
Spring MVC DispatcherServlet
  ▼
OrderController
  ▼
OrderService (business logic, transactions where appropriate)
  ▼
Spring Data JPA Repository
  ▼
JPA provider → JDBC driver → SQL database
  │
  └─→ result → controller → JSON/HTTP response
~~~

Along this path, Spring Boot is responsible for **startup, wiring configuration, and component lifecycle**. It does not perform routing in place of the controller, write persistence logic in place of JPA, or decide access permissions in place of Security.

### Architecture B: Boot + WebFlux + Spring Data R2DBC + Security

~~~text
Client
  │ GET /api/orders/42
  ▼
Reactive HTTP runtime (configured by Boot)
  ▼
Spring Security reactive WebFilters
  ▼
Spring WebFlux DispatcherHandler
  ▼
OrderHandler / OrderController
  ▼
OrderService returning Mono/Flux
  ▼
Spring Data R2DBC Repository
  ▼
R2DBC driver → SQL database
  │
  └─→ data signals → reactive HTTP response
~~~

In Architecture B, processing steps should preserve reactivity down to key I/O operations. **Do not block event-loop threads** with `Thread.sleep`, JDBC/JPA, synchronous network calls, or blocking file I/O inside reactive handlers. If calling a blocking library is unavoidable, there must be a clear offloading strategy and concurrency limit.

Both architectures can expose the same REST contract while having different **runtimes, error handling, transactions, threading, and performance profiles**.

## 7. How to Choose Starters in Spring Boot?

For a project using Gradle and Spring Boot dependency management, two minimal examples:

**Servlet/MVC and JPA option:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

**Reactive option with WebFlux and R2DBC:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
~~~

These are **two separate reference configurations**; they assume the application has matching database configuration, schema, mappings, and authentication setup. `spring-boot-starter-security` is used in both, yet the type of security infrastructure configured depends on the web stack. With Boot dependency management, library versions are managed according to the Boot version in use; avoid arbitrarily mixing incompatible Spring versions.

Illustrative PostgreSQL connection properties showing the difference:

~~~properties
# MVC + JPA: JDBC
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=app
spring.datasource.password=...

# WebFlux + R2DBC (in a separate application):
# spring.r2dbc.url=r2dbc:postgresql://localhost:5432/catalog
# spring.r2dbc.username=app
# spring.r2dbc.password=...
~~~

In real situations, use environment-specific configuration/secrets rather than putting real passwords into source code. Do not assume `spring.datasource.*` and `spring.r2dbc.*` share the same pool, driver, or transaction manager.

## 8. Misconceptions to Avoid

| Common Misconception | Accurate Understanding |
|---|---|
| "Spring Boot is a framework that replaces Spring MVC." | Boot uses and configures the Spring Framework; MVC is a web framework that can run inside a Boot app. |
| "Every Boot app must have MVC, Data, and Security." | Add only capabilities matching requirements; batch or messaging apps may need no web layer at all. |
| "Spring MVC and WebFlux are just two annotation styles with the same internals." | Annotations can look similar, but Servlet and reactive stacks differ in execution, I/O management, errors, and context. |
| "Returning a Mono gives you full non-blocking execution." | The entire I/O path must be compatible; JDBC/JPA remains blocking even when wrapped in `Mono`. |
| "Spring Data means Hibernate or JPA." | JPA is just one module; Spring Data also supports JDBC, R2DBC, MongoDB, and other stores. |
| "Spring Security only works with MVC." | Security supports both Servlet and reactive integrations; each stack uses its own chain and configuration API. |
| "Having the Security starter means business authorization is complete." | The starter provides infrastructure and defaults; endpoint/method policies must be designed, configured, and tested. |
| "Using WebClient means the server must be WebFlux." | A Spring MVC application can still use WebClient to call external services. |

## 9. Applying This When Designing and Testing

When starting a Spring Boot module, you can make decisions sequentially:

1. **Is an HTTP server needed?** If yes, choose the web stack based on real requirements and downstream libraries.
2. **Is most I/O blocking or reactive-ready?** If using JPA/JDBC and traditional transactions, MVC is usually the simpler choice. If the API handles high-concurrency I/O streams and clients/drivers are reactive, evaluate WebFlux.
3. **Which data store is used?** Pick the right Spring Data module for the storage technology and access model; do not choose based on controller names.
4. **Who can call which endpoints and operations?** Design authentication/authorization, apply Security matching the web stack, and consider service-layer permission checks.
5. **What needs verification?** Test HTTP responses, repository behavior, transactions, error handling, and unauthorized access cases.

Ecosystem testing tools are used accordingly: `MockMvc` and `@WebMvcTest` for MVC web layers; `WebTestClient` and `@WebFluxTest` for WebFlux web layers; `@DataJpaTest` for JPA, `@DataR2dbcTest` for R2DBC; `@SpringBootTest` when multi-layer integration testing is needed. Use Spring Security Test utilities to verify both permitted and denied access. Each test slice loads only part of the context, so do not conclude from a single controller test that security, database, and the whole application work properly.

An easy-to-remember architectural rule: **Controllers/handlers receive and return HTTP; services hold business logic; repositories work with data; security protects entry points and operations; Spring Boot creates the environment for these parts to fit together.** Choosing MVC vs. WebFlux is a decision about **web and I/O processing models**, while choosing Spring Data and Spring Security is driven by **data and security requirements**.
