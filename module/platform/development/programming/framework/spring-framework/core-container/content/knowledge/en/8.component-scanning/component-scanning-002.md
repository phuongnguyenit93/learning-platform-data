# Meaning of @Service, @Repository, and @Controller in Spring Core Container

## 1. Objectives and Context

When writing a Spring Framework application, we typically divide code into classes for HTTP handling, business logic, and data access. The three annotations `@Controller`, `@Service`, and `@Repository` help describe those roles in source code and allow Spring to discover classes during **component scanning**.

After this lesson, you will be able to:

- Explain why all three annotations create **bean candidates** through the `@Component` mechanism.
- Distinguish between the **architectural role** and **runtime behavior** of each stereotype, avoiding the assumption that the annotation automatically creates endpoints, transactions, or database connections.
- Describe the process by which `@ComponentScan` discovers classes, registers bean definitions, instantiates beans, and performs dependency injection.
- Write a plain Java Spring Framework example where `@Repository`, `@Service`, and `@Controller` are discovered and properly injected into one another.
- Analyze the conditions for **persistence exception translation** of `@Repository` and the conditions for **HTTP routing** of `@Controller`.
- Use bean names, qualifiers, scopes, and scan scopes appropriately; and troubleshoot real-world configuration errors.

This lesson focuses on the **Spring Core Container and component scan**. Examples involving Spring MVC, data access, and transactions are used to explain stereotype roles, not to replace in-depth courses on web or data access.

## 2. What Is a Stereotype?

A **stereotype** is an annotation that classifies the role of a class in an application. Spring provides the general-purpose stereotype `@Component` and specialized stereotypes:

- `@Controller`: a class responsible at the request-receiving/presentation boundary, typically a web controller.
- `@Service`: a class representing a business service or use case orchestration.
- `@Repository`: a class responsible for storing, retrieving, and querying data (repository/DAO).

What they share regarding Spring management is that **all three are meta-annotated with `@Component`**.

```java
// Conceptual diagram of annotation relationships; not the complete Spring definitions.
@Component
public @interface Service {}

@Component
public @interface Repository {}

@Component
public @interface Controller {}
```

The syntax above only illustrates the idea of meta-annotations; the real definitions also include `@Target`, `@Retention`, `@Documented`, and other attributes. **Do not copy this sketch to replace the real annotations.**

When component scanning is enabled for an appropriate package, Spring recognizes classes marked with `@Component` or stereotypes meta-annotated with `@Component`, and then registers bean definitions for them.

```text
Classpath containing compiled classes
             |
             v
       @ComponentScan
             |
             +--> @Controller --> bean definition --> controller bean
             |
             +--> @Service ----> bean definition --> service bean
             |
             +--> @Repository -> bean definition --> repository bean
             |
             v
     IoC Container manages lifecycle, dependencies, scope
```

An annotation marks a class as a candidate; whether the bean actually appears depends on the **scan scope**, filters, conditional configuration, naming conflicts, and the success of bean creation. Not every class on the classpath automatically becomes a bean.

## 3. Quick Comparison of the Three Annotations

| Aspect | `@Controller` | `@Service` | `@Repository` |
| --- | --- | --- | --- |
| Primary meaning | Presentation / web entry point | Business logic, use cases, orchestration | Data access and persistence |
| Specialization of | `@Component` | `@Component` | `@Component` |
| Discovered via component scan | Yes | Yes | Yes |
| Supports constructor injection | Yes | Yes | Yes |
| Default scope | Singleton | Singleton | Singleton |
| Automatically opens HTTP endpoint just from the annotation? | **No** | No | No |
| Automatically starts a transaction? | No | **No** | No |
| Marker supported for persistence exception translation | Not primary purpose | Not primary purpose | **Yes, when corresponding exception translation infrastructure is configured** |
| Typically called by which classes? | Dispatcher/handler or other caller | Controller, other service, listener | Service or other business component |
| Benefits beyond bean creation | Web component recognition, web infrastructure integration | Expressing architectural intent, AOP pointcuts | Expressing persistence layer, AOP pointcuts, exception translation support |

**Key takeaway:** the three annotations help Spring **identify, register, and classify beans**, but they do not form three different types of IoC Containers. The same container still manages them using bean definitions, dependency injection, and scope.

## 4. Component Scanning Mechanism Under the Hood

All three stereotypes go through **the exact same** Spring class-scanning path:

```java
@Configuration
@ComponentScan(basePackages = "com.example.catalog")
class CatalogConfig { }
```

After `CatalogConfig` is registered in the context, Spring inspects classes in `com.example.catalog` and its subpackages. The default filter accepts `@Controller`, `@Service`, and `@Repository` because they carry the `@Component` meta-annotation. For valid candidates, the scanner creates bean definitions; the container then instantiates them and resolves dependencies according to scope/lifecycle. A class bearing a stereotype that lies outside the root, is excluded by a condition/filter, or lacks a dependency can still be absent or fail.

`basePackageClasses = CatalogPackage.class` also configures the scan area, via the **package containing the marker class** rather than scanning only the marker itself. What is noteworthy across the three stereotypes is not different scanning algorithms, but **each layer's responsibility and the specialized infrastructure that can interpret that metadata**.

## 5. @Service: Marking the Business Layer

### 5.1. Meaning

`@Service` is a specialization of `@Component`, suited for representing the **service layer**: business actions, use cases, domain rules, or coordinating multiple collaborators.

A service can:

- Validate and enforce business rules.
- Coordinate multiple repositories, domain services, or integration gateways.
- Produce use case results for controllers, listeners, or scheduled jobs.
- Serve as a placement point for cross-cutting policies through other annotations/aspects if configured.

Structural example:

```java
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final StockRepository stock;
    private final PaymentGateway payments;

    public CheckoutService(StockRepository stock, PaymentGateway payments) {
        this.stock = stock;
        this.payments = payments;
    }

    public Receipt checkout(Cart cart) {
        stock.reserve(cart);
        return payments.charge(cart);
    }
}
```

`StockRepository`, `PaymentGateway`, `Receipt`, and `Cart` are illustrative business types; this snippet is not a standalone program. `@Service` makes the class a bean candidate when scanned; the dependencies still require corresponding beans for injection.

### 5.2. @Service Does Not Automatically Create Transactions, Retries, or Caching

The following expectations are **not true solely from `@Service`**:

- Every method call automatically runs in a transaction.
- Spring automatically retries when a service throws an error.
- Return values are automatically cached.
- Methods automatically run asynchronously.
- Every method call is intercepted by AOP for logging.

Those capabilities require separate infrastructure/annotations/configurations, such as `@Transactional` paired with transaction management, `@Cacheable` with caching infrastructure, or `@Async` with async execution. Placing these annotations on a service must satisfy the requirements of the proxy mechanism, method invocation, and corresponding infrastructure.

Illustrative example (**not a standalone program**):

```java
@Service
public class TransferService {
    @org.springframework.transaction.annotation.Transactional
    public void transfer(long fromId, long toId, long amount) {
        // Requires DAO, transaction manager, and actual business logic.
    }
}
```

`@Transactional` declares a transaction if Spring transaction infrastructure is properly enabled—it is not an inherent privilege of `@Service`. Even without `@Service`, a `@Component` or `@Bean` bean can participate in transactions when configured accordingly.

### 5.3. Why Not Use @Component for Everything?

Scanning and dependency injection can still work, but `@Service` makes class responsibility easier to understand and facilitates architectural analysis, tooling, and AOP pointcuts targeting the service layer. Spring may also add stereotype-specific semantics in future versions.

Use `@Service` when a class actually holds business responsibility; do not place it on a data adapter or request controller just because you want Spring to inject it.

## 6. @Repository: Marking the Persistence / Data Access Layer

### 6.1. Meaning

`@Repository` is intended for a component responsible for **storing, querying, searching, and retrieving data**. Many teams use it for DAOs; in Domain-Driven Design, a repository often represents a collection of domain objects and hides persistence details from the business layer.

```java
import org.springframework.stereotype.Repository;

@Repository
public class JdbcCustomerRepository {
    private final org.springframework.jdbc.core.JdbcTemplate jdbc;

    public JdbcCustomerRepository(
            org.springframework.jdbc.core.JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String findName(long id) {
        return jdbc.queryForObject(
            "select name from customer where id = ?",
            String.class,
            id
        );
    }
}
```

This is an illustrative DAO example requiring the `spring-jdbc` dependency, a configured `JdbcTemplate`, a `DataSource`, and a `customer` table in a real DB; it is not a standalone runnable program. `@Repository` allows component scan to discover the class and indicates that it belongs to the data access layer.

### 6.2. Exception Translation: A Noteworthy Distinction

A special role of `@Repository` is **marking a repository as eligible** for Spring's mechanism that translates persistence exceptions into Spring's unified data access exception hierarchy, centered around `org.springframework.dao.DataAccessException` and its subclasses.

For example, vendor persistence APIs may throw technology-specific exceptions. Exception translation allows upper calling layers to handle more neutral error categories such as data not found, integrity violation, lock contention, etc. The exact mapping is determined by the corresponding translator.

However, remember the **conditions** clearly:

1. The repository bean has an appropriate stereotype, such as `@Repository`.
2. Exception translation infrastructure, typically `PersistenceExceptionTranslationPostProcessor`, is registered.
3. A `PersistenceExceptionTranslator` matching the persistence technology exists to convert the exception type being handled.
4. The call actually goes through the proxy/interceptor (when the implementation mechanism uses a proxy) and that exception type is supported by the translator.

```text
Caller
  |
  v
Repository proxy / interceptor
  |
  v
@Repository target -> persistence API -> vendor exception
  |
  v
Matching PersistenceExceptionTranslator
  |
  +--> DataAccessException (if translatable)
  |
  +--> original exception (if no matching translation exists)
```

Example of registering the post-processing mechanism in an appropriate configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.annotation.PersistenceExceptionTranslationPostProcessor;

@Configuration
class DataAccessConfig {
    @Bean
    static PersistenceExceptionTranslationPostProcessor
            persistenceExceptionTranslationPostProcessor() {
        return new PersistenceExceptionTranslationPostProcessor();
    }
}
```

This example requires `spring-tx` on the classpath and a suitable translator from the data-access stack; the configuration class alone **does not guarantee translation of every exception**. Declaring a `static @Bean` for a `BeanPostProcessor` helps register it early in the container lifecycle. If a framework/data starter already configures translation, do not register a duplicate without checking.

**Further distinctions:**

- `JdbcTemplate` already has its own mechanism to translate many `SQLException` cases into `DataAccessException` from its own operations. That result **is not because** the user put `@Repository` on the DAO class.
- `@Repository` does not automatically create a `DataSource`, `EntityManager`, `JdbcTemplate`, schema, or connection pool.
- A `@Repository` class does not become an auto-query-generating Spring Data repository solely via the annotation. Spring Data repository interfaces and Spring Data's proxy factory are a **different mechanism**.
- Do not assume every `RuntimeException` or every SQL error is translated; the infrastructure and translator determine this.

### 6.3. Boundary Between Repository and Service

Typically, a repository defines operations such as `findById`, `save`, or queries tailored to business needs; a service combines those operations to fulfill a use case. A repository should not hold HTTP logic, response headers, or directly decide status codes.

Collaboration example:

```text
OrderService.placeOrder()
    |
    +-- inventoryRepository.checkStock()
    +-- orderRepository.save()
    +-- paymentGateway.authorize()
    |
    +-- return business result
```

The methods here illustrate collaboration relationships, not specific built-in Spring APIs.

## 7. @Controller: Marking the Presentation/Web Layer

### 7.1. Meaning in Core Container

`@Controller` is also a `@Component` stereotype. When scanned, a controller is registered as a Spring bean, participating in injection and lifecycle just like other beans.

```java
import org.springframework.stereotype.Controller;

@Controller
public class CatalogController {
    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    public String lookup(int id) {
        return service.findTitle(id);
    }
}
```

`CatalogService` is an illustrative business type. In a **plain `ApplicationContext`**, the `lookup` method is just a Java method. Adding `@Controller` does not automatically create an HTTP endpoint or start a server.

### 7.2. Why Can Spring MVC Recognize a Controller?

In an application with Spring MVC infrastructure enabled, `@Controller` beans can be treated as **handlers**. Spring MVC uses components such as `RequestMappingHandlerMapping` and `RequestMappingHandlerAdapter` to find request mappings and invoke handler methods.

To map HTTP requests, web MVC/`DispatcherServlet` configuration and routing annotations such as `@RequestMapping`, `@GetMapping`, or `@PostMapping` are also required.

```java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/catalog")
public class CatalogPageController {
    private final CatalogService catalogService;

    public CatalogPageController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable int id, Model model) {
        model.addAttribute("title", catalogService.findTitle(id));
        return "catalog/detail";
    }
}
```

This is an illustrative MVC example and **does not run standalone** without `CatalogService`, Spring MVC servlet infrastructure, and a view resolver/template. With an MVC controller returning `String` as above, `"catalog/detail"` is normally interpreted as a **view name**. Not every string returned from a method in `@Controller` is written verbatim into the HTTP response body.

### 7.3. How Does @RestController Relate to @Controller?

`@RestController` in Spring MVC is a composed annotation carrying the semantics of `@Controller` **and `@ResponseBody`**. It is typically suited for APIs that return data into the response body rather than a view name:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
public class CatalogApiController {
    private final CatalogService catalogService;

    public CatalogApiController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/{id}")
    public CatalogDto detail(@PathVariable int id) {
        return new CatalogDto(id, catalogService.findTitle(id));
    }

    public record CatalogDto(int id, String title) {}
}
```

This illustrative snippet requires `CatalogService` and Spring Web MVC infrastructure. When properly configured, the response body is written via appropriate `HttpMessageConverter`s. JSON is typically produced if a converter (such as Jackson) and matching content negotiation exist. `@RestController` itself **does not download a JSON library, open an HTTP port, or configure a server**.

### 7.4. Being Careful About the Web Boundary

A `@Controller` bean can still be created in a context containing only Spring Core, but it will **not handle HTTP** without a DispatcherServlet or appropriate handler infrastructure. Conversely, merely adding `@RequestMapping` on a class that is not registered in the context will not cause the application to receive requests either.

In Spring WebFlux, annotated controllers also exist, but the dispatch/handler flow belongs to the reactive infrastructure and should not be equated with MVC Servlet. Stereotype questions in Core Container only require understanding **how beans are discovered** and **the role that web infrastructure can subsequently use**.

## 8. Runnable Example: Three Stereotypes in One Spring ApplicationContext

To observe the component scan mechanism without setting up an HTTP server or database, this example uses **Spring Framework 6.2.19**, **Java 17+**, and Java configuration `AnnotationConfigApplicationContext`.

We have three classes: a repository providing mock data, a service calling the repository, and a controller calling the service. Bean names are declared explicitly so the result does not depend on Java **nested class** naming rules.

Project structure:

```text
spring-stereotype-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── StereotypeDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'spring-stereotype-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.StereotypeDemo'
}
```

`spring-context` is sufficient for a Core Container demo: the three annotations belong to `org.springframework.stereotype`; no MVC, JDBC, or Spring Boot dependencies are needed just to observe bean scanning.

**`src/main/java/demo/StereotypeDemo.java`**

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Controller;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;

public class StereotypeDemo {

    @Configuration
    @ComponentScan(basePackageClasses = StereotypeDemo.class)
    public static class Config {
    }

    @Repository("catalogRepository")
    public static class CatalogRepository {
        public String findTitle(int id) {
            return "Product-" + id;
        }
    }

    @Service("catalogService")
    public static class CatalogService {
        private final CatalogRepository repository;

        public CatalogService(CatalogRepository repository) {
            this.repository = repository;
        }

        public String findTitle(int id) {
            return repository.findTitle(id);
        }
    }

    @Controller("catalogController")
    public static class CatalogController {
        private final CatalogService service;

        public CatalogController(CatalogService service) {
            this.service = service;
        }

        public String show(int id) {
            return service.findTitle(id);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("repository-bean="
                    + context.containsBean("catalogRepository"));
            System.out.println("service-bean="
                    + context.containsBean("catalogService"));
            System.out.println("controller-bean="
                    + context.containsBean("catalogController"));

            CatalogController controller =
                    context.getBean(CatalogController.class);
            System.out.println("result=" + controller.show(7));

            CatalogService first = context.getBean(CatalogService.class);
            CatalogService second = context.getBean(CatalogService.class);
            System.out.println("service-singleton=" + (first == second));
        }
    }
}
```

**Run** from the `spring-stereotype-demo` directory using Gradle with JDK 17+:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper, run `./gradlew run --quiet` (Linux/macOS) or `gradlew.bat run --quiet` (Windows). Do not run `javac StereotypeDemo.java` standalone without putting `spring-context` and transitive dependencies on the classpath; Gradle handles compile and runtime dependencies automatically.

**Lines printed by the program (stdout):**

```text
repository-bean=true
service-bean=true
controller-bean=true
result=Product-7
service-singleton=true
```

**Explanation:**

1. `@ComponentScan(basePackageClasses = StereotypeDemo.class)` scans package `demo`, where the example's stereotype-annotated `static` classes are compiled.
2. The scanner detects `CatalogRepository` via `@Repository`, `CatalogService` via `@Service`, and `CatalogController` via `@Controller`; the corresponding explicit bean names are registered.
3. Spring constructor-injects `CatalogRepository` into the service, and then the service into the controller. A single constructor does not require adding `@Autowired`.
4. `context.containsBean("...")` returns `true` for all three beans, proving they are all present in the container.
5. The direct Java call `controller.show(7)` returns `Product-7`. **This is not an HTTP request** and the program does not start Spring MVC.
6. Two calls to `getBean(CatalogService.class)` return the same instance, matching the default singleton scope.

The example can be extended with `@Scope("prototype")` on the service to observe separate `getBean` calls returning different instances. However, if a prototype has already been injected into a singleton controller, the reference held by the controller remains the object resolved for the controller at initialization time. This is a general scope rule, independent of whether the class is annotated with `@Service` or `@Component`.

## 9. From a Real Request to the Controller -> Service -> Repository Chain

In a properly configured Spring Web MVC application, the processing flow is typically:

```text
HTTP Client
    |
    v
DispatcherServlet / HandlerMapping
    |
    v
@Controller / @RestController
    |  receives request, binds/validates data, and delegates call
    v
@Service
    |  executes use case, orchestrates business rules
    v
@Repository
    |  accesses storage via JDBC/JPA/... or custom adapter
    v
Database / external persistence
```

The return direction is repository -> service -> controller -> HTTP response. This is a **commonly used organizational pattern**, not a mandatory chain enforced by the container for every project. For example, a service may call another service, a controller may call a query service, or a repository may access a cache or separate domain classes.

An application without web can still use `@Service` and `@Repository`; an application without a database can still have `@Controller`, and a service does not necessarily have to call a repository. Spring IoC manages beans by actual dependencies, and does not create dependency edges merely from annotation names.

**Sensible design roles:**

- Controller: forwards requests and presents results to clients; keeps core business logic in the service.
- Service: decides business logic/use cases, and may bind transactions when configured.
- Repository: hides search/retrieval/storage mechanisms from upper layers.

Separating responsibilities makes testing each layer easier and reduces direct coupling from business logic to web frameworks or persistence details.

## 10. Do Bean Naming and Injection Differ Between Stereotypes?

`@Controller`, `@Service`, and `@Repository` use the same bean naming/injection/scope mechanisms as regular components. `@Service class CheckoutService` typically receives the name `checkoutService`, unless `@Service("checkoutWorkflow")` or a custom `BeanNameGenerator` is used. Acronym-like classes such as `URLClient` may keep leading uppercase letters under JavaBeans naming; check the actual name via the context instead of guessing.

When a constructor requires an interface with multiple implementations, `@Qualifier`, `@Primary`, or an appropriate collection is needed. All three stereotypes default to singleton within a container; do not store per-request mutable state in a singleton field without proper concurrency/scope design. Bean naming is identity in the registry, whereas stereotype annotations express architectural roles.

## 11. Distinguishing Stereotypes from @Bean and @Configuration

The component scanner registers definitions from **classes with stereotypes**; `@Bean` registers definitions from **factory methods** of a configuration processed by Spring. A class outside the codebase can become a bean without carrying a stereotype:

```java
@Configuration(proxyBeanMethods = false)
class IntegrationConfig {
    @Bean
    ExternalClient externalClient() {
        return new ExternalClient("endpoint");
    }
}
```

`ExternalClient` is a hypothetical type in this illustrative snippet; the default bean name here is `externalClient` after the method. Scanning a class and also creating it via `@Bean` can cause duplicate registration or multiple beans of the same type, depending on naming/configuration. Whether registered via scanner or factory method, a Spring-managed instance can receive annotation injection and lifecycle callbacks when the appropriate processors are present. `@Service` is not a prerequisite for a bean to be injected.

## 12. Stereotypes, AOP, and Extension Mechanisms

Stereotypes help tools and aspects classify beans by responsibility. For instance, to record metrics for service methods, an aspect can select classes annotated with `@Service` using an appropriate pointcut.

However, keep three conceptual layers separate:

1. **Bean discovery:** component scanning sees the stereotype/meta-annotation.
2. **Bean creation and injection:** the IoC Container manages objects and dependencies.
3. **Additional behavior:** other mechanisms, such as post-processors, Spring MVC, or AOP, interpret stereotypes/method annotations if enabled.

`@Service` does not directly generate a proxy; `@Repository` does not guarantee an exception-translating proxy if a post-processor/translator is missing; `@Controller` does not automatically configure DispatcherServlet.

### Why Is Separating These Three Layers Important?

Suppose an application can run `context.getBean(MyController.class)` but the HTTP path returns 404. That proves the bean exists in the context, yet **does not prove** Spring MVC scanned the mapping, has a handler, or matched the path.

Conversely, a repository injected successfully whose vendor exceptions are not converted to `DataAccessException` may be missing a translator, post-processor, or a call going through a proxy. A bean existing in the context and an integration behavior working are **two distinct checks**.

## 13. Common Errors and How to Diagnose Them

### Error 1 — Adding @Service and Expecting Spring to Find It Outside the Scan Package

**Symptom:** `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException` when injecting the service.

Check the package containing the class, `@ComponentScan(basePackages=...)`, which configuration classes are loaded, and include/exclude filters. Do not fix it by arbitrarily widening scanning to the entire classpath; choose a consistent root package.

### Error 2 — Adding @Controller and Waiting for an HTTP Endpoint to Appear

**Symptom:** The bean exists, but the HTTP route does not.

Check whether this is a Spring MVC/WebFlux application running the proper infrastructure, whether corresponding `@RequestMapping`/`@GetMapping` annotations exist, whether servlet/reactive handler mappings exist, whether the context contains the right bean, and whether the path/method match the request. `@Controller` in a plain `AnnotationConfigApplicationContext` is just a managed bean.

### Error 3 — Marking @Repository and Assuming Every SQLException Will Be Translated

**Symptom:** The caller still sees the original exception or no translation infrastructure is active.

Check whether the data-access library has its own translation mechanism; if using `PersistenceExceptionTranslationPostProcessor`, ensure the post-processor and matching `PersistenceExceptionTranslator` are registered and calls go through the bean/proxy. Do not catch all exceptions and manually convert them to `DataAccessException` while discarding the root cause.

### Error 4 — Confusing @Service with @Transactional

**Symptom:** Service operations do not roll back even though the class has `@Service`.

Spring only applies transactions when properly configured (`@Transactional`, transaction manager, appropriate interceptor/proxy, etc.). Check transaction boundaries, whether the method is invoked through the Spring proxy, and limitations such as self-invocation in default proxy mode. Do not add `@Service` again to fix it.

### Error 5 — Two Beans Implementing the Same Interface, Ambiguous Candidate

**Symptom:** `NoUniqueBeanDefinitionException`.

Place an explicit qualifier on the injection point or use `@Primary` when one implementation is genuinely the default; when business logic needs all implementations, inject a `List<T>` collection. Do not change all `@Repository` annotations to `@Component` because that does not resolve type-based conflicts.

### Error 6 — Two Classes in Different Packages Generating the Same Bean Name

**Symptom:** Bean definition/name conflict error during scanning.

For example, `catalog.CustomerService` and `billing.CustomerService` may both generate the default name `customerService`. Use explicit names, an appropriate bean name generator, or adjust scan boundaries if they are truly two independent beans.

### Error 7 — Thinking @Controller Returns JSON by Default

A `@Controller` returning a `String` in Spring MVC can represent a view name. To return a response body, use `@ResponseBody` on the method/type or `@RestController` when all handler methods should follow that model; an appropriate message converter is needed to serialize objects.

### Error 8 — Putting an Annotation on a Class and Instantiating It with new

```java
CatalogService service = new CatalogService(new CatalogRepository());
```

This is a manually created Java object; it **does not automatically participate** in container injection, lifecycle, proxies, or `BeanPostProcessor`s merely because the class carries `@Service`/`@Repository`. To use a managed bean, receive it via dependency injection or `context.getBean(...)` in infrastructure/test code.

### Error 9 — Putting Per-Request Business State in a Singleton Service/Controller

All stereotypes are singletons by default. Do not store mutable request/caller data in a singleton field if concurrent requests exist. Keep state in local variables, parameters, or appropriately scoped beans, and design synchronization when needed.

### Error 10 — Assuming Annotations Alone Enforce Architecture

Stereotypes help readers and tooling understand roles, but Spring does not enforce by default that a controller does not run SQL directly or that a repository does not build an HTTP response. Maintain architectural boundaries through package design, code reviews, architecture tests, and project conventions.

## 14. Testing and Practical Observation

### 14.1. Testing Bean Presence

For a plain container:

```java
try (AnnotationConfigApplicationContext ctx =
        new AnnotationConfigApplicationContext(Config.class)) {
    assert ctx.containsBean("catalogRepository");
    assert ctx.containsBean("catalogService");
    assert ctx.containsBean("catalogController");
}
```

This snippet is based on `Config` from `StereotypeDemo`; when used in another file, declare/import the right class names and enable `-ea` assertions, or use JUnit assertions. For standalone tests and clear failure messages, JUnit's `assertTrue` is usually preferable to Java `assert`.

### 14.2. Testing the Constructor Injection Flow

The complete example in section 8 lets you observe `CatalogController` calling `CatalogService` and `CatalogRepository` without manually instantiating each collaborator in `main`. In tests, replace the repository with a fake/test bean when you want to isolate business logic from real data.

### 14.3. Testing Web and Persistence Behavior Separately

- To verify HTTP mappings, run an integration test in a **web application context** with MVC/WebFlux infrastructure; with MVC you can use `MockMvc`. Verify path, HTTP method, response body, status, and validation.
- To verify exception translation, write a test with the actual persistence technology and matching translator/post-processor, invoke through the Spring-managed repository bean, and assert the resulting exception.
- To verify service transactions, use a test with a transaction manager and real transactional resources or an appropriate integration fixture; testing bean scanning alone will not prove commit/rollback.

A `containsBean` check proves bean registration; it **does not prove** that an HTTP endpoint runs or that persistence exceptions are translated.

## 15. Design Checklist

Before annotating a class:

1. Is this class primarily responsible for **presentation, business logic, or data access**? Choose `@Controller`, `@Service`, or `@Repository` accordingly; if it does not fit those groups, the general `@Component` may be more appropriate.
2. Is the class's package within the `@ComponentScan` scope? Is there any filter or condition excluding the bean?
3. Are dependencies constructor-injected and is there one valid bean per parameter? If multiple candidates exist, have qualifiers/primary been configured properly?
4. Does the bean hold mutable state? Is the default singleton scope appropriate for concurrency and lifecycle?
5. If using `@Repository` and expecting exception translation, are the required infrastructure and translator present?
6. If using `@Controller` for HTTP handling, has the application enabled the right web stack, handler mapping, and route annotations?
7. If using `@Service` with transactions/caching/async, has each of those features been enabled, configured, and tested separately?

## 16. Review Questions and Answers

**Question 1.** Why can Spring scan `@Service`, `@Repository`, and `@Controller` at the same time?

**Answer:** Because they are specialized stereotypes meta-annotated with `@Component`. The component scanner's default filter looks for matching classes within the configured packages.

**Question 2.** If `@Controller` is discovered in a plain `AnnotationConfigApplicationContext`, does an HTTP endpoint already exist?

**Answer:** No. The bean exists in the IoC Container; web infrastructure and mappings are required for HTTP requests. Methods can still be invoked as regular Java methods.

**Question 3.** Does `@Service` automatically apply a transaction when a method is called?

**Answer:** No. Transactions are a separate mechanism requiring appropriate annotations/infrastructure, such as `@Transactional` and a transaction manager. The service stereotype only expresses role and supports scanning.

**Question 4.** Does `@Repository` translate every exception into `DataAccessException`?

**Answer:** No. It is a marker for persistence exception translation when a post-processor, translator, and calls through the appropriate mechanism are set up. Only exceptions supported by the translator are converted.

**Question 5.** When two classes in two packages share the name `CustomerService` and are scanned, what can happen?

**Answer:** The default bean names may collide. This can be resolved using explicit names, an appropriate bean name generator, or organizing scan boundaries sensibly. Both using `@Service` does not differentiate their names.

**Question 6.** Can a class become a Spring bean without a stereotype?

**Answer:** Yes. For example, a `@Bean` method in `@Configuration` returning the corresponding object. Component scanning is only one of the bean registration mechanisms.

**Question 7.** Why should you not rely solely on `containsBean("catalogController")` to claim that `GET /catalog/7` works?

**Answer:** Because that check only confirms the bean is registered; an active route requires a web context, handler mapping, mapping annotations, matching request method/path, and corresponding MVC components.

**Question 8.** Does Spring force controllers to call services, and services to call repositories?

**Answer:** No. This is a common layered pattern to manage responsibilities and dependencies, not a runtime rule of the IoC Container.

## 17. Official References

- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): `@Component`, stereotypes, meta-annotations, bean naming, and scan scope.
- [Spring Framework 6.2 — DAO Support](https://docs.spring.io/spring-framework/reference/6.2/data-access/dao.html): repositories, Spring `DataAccessException`, and exception translation.
- [Spring Framework 6.2 — Spring MVC Annotated Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann.html): `@Controller` in MVC and web application conditions.
- [Spring Framework 6.2 — Mapping Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html): mapping annotations and request matching conditions.
- [Spring Framework 6.2 — Spring Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans.html): bean definitions, dependency management, and IoC Container scope of responsibility.
- [Spring Framework 6.2 API — Repository](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/stereotype/Repository.html): stereotype contract and conditions related to `PersistenceExceptionTranslationPostProcessor`.

**Key takeaway:** `@Service`, `@Repository`, and `@Controller` primarily define **class roles** so the Spring Core Container can discover and manage beans. `@Repository` provides an integration point for exception translation in suitable persistence infrastructure; `@Controller` is used by web frameworks to identify handlers. Features such as HTTP routing, transactions, and SQL processing still require their own components to be explicitly configured.
