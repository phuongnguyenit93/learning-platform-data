# Boundaries with AOP, Transactions, and Web Modules in Spring Framework

## 1. Why Separate Layers of Responsibility?

When learning Spring Core Container, it is easy to jump from `@Component`, `@Bean`, and `@Autowired` to assuming the container automatically handles logging, transactions, HTTP endpoints, and every annotation-driven behavior. That conclusion is **incorrect**.

**Spring Core Container** is primarily responsible for **managing and assembling beans**: reading configuration metadata, instantiating objects, resolving dependencies, applying scopes, coordinating lifecycles, and providing `BeanFactory`/`ApplicationContext`. Other mechanisms can *build on* the container to attach additional behavior:

- **Spring AOP:** applies advice such as logging, timing, or cross-cutting policies around eligible **method invocations**, typically via proxies.
- **Spring Transaction Management:** provides infrastructure to declare/coordinate transactions (such as `@Transactional`) and an appropriate transaction manager; in the common mode, this uses an AOP proxy.
- **Spring Web MVC / WebFlux:** organizes receiving HTTP requests, handler mapping, binding, response/result handling, and errors; controller/service beans are still supplied by the Spring container.
- **Spring Boot:** assists with bootstrap, dependency starters, and auto-configuration; it is **not synonymous with Spring Core Container** and is not required to run plain Spring Framework.

A console application can use `ApplicationContext` **without a web server, database transactions, or aspects**. A web/transactional application still needs the IoC container, plus the corresponding infrastructure components.

~~~text
          Spring Boot (if chosen)
        bootstrap / auto-configuration
                      |
      +---------------v----------------+
      | Spring Core Container          |
      | BeanFactory / ApplicationContext|
      | bean definitions + DI + lifecycle|
      +----------------+---------------+
                       |
       +---------------+----------------+
       |               |                |
    Spring AOP      Spring Tx       Spring Web
   method proxy   tx interceptor   MVC / WebFlux
       |           + tx manager         |
       +----> service / repository <----+
                    beans
~~~

The diagram illustrates **functional collaboration relationships**, not a complete Maven dependency graph. AOP, transactions, and web are distinct features/responsibility layers, though all can share beans managed by the container.

## 2. What Belongs to the Core Container

An `ApplicationContext` such as `AnnotationConfigApplicationContext` can perform:

1. Reading bean configuration (`@Configuration`, `@Bean`, component scanning if enabled).
2. Instantiating beans, selecting constructors/factory methods, and injecting dependencies.
3. Managing scopes, commonly `singleton` per context; managing bean init/destroy callbacks per the applicable rules.
4. Providing `Environment`, resource loading, internationalization via `MessageSource`, event publication, and other context utilities.
5. Executing the `refresh()` startup process, where bean definitions and post-processors can be registered, discovered, and activated.

Configuration example:

~~~java
@Configuration
class CoreConfig {
    @Bean
    Notifier notifier() {
        return new ConsoleNotifier();
    }

    @Bean
    OrderService orderService(Notifier notifier) {
        return new OrderService(notifier);
    }
}
~~~

This is an **illustrative snippet**, not standalone runnable without defining `Notifier`, `ConsoleNotifier`, and `OrderService`. Wiring `notifier` into `OrderService`'s constructor is **pure DI**; it **does not automatically** add AOP logging, open a database transaction, or expose REST endpoints.

Inside the container there are extension mechanisms such as `BeanPostProcessor`. AOP and transaction modules can register additional post-processors and proxies. Thus the boundary is not "Core has nothing to do with AOP," but rather **Core provides the foundation, while specialized features require their own infrastructure and configuration**.

### Layer Identification Table

| Question / behavior | Primary responsibility |
| --- | --- |
| "Who creates `OrderService` and passes `Repository` into its constructor?" | Core Container (DI / bean factory) |
| "Who adds logging before calling a service?" | AOP advice and auto-proxy infrastructure, or plain logging code |
| "Who decides to open/commit/roll back a transaction when calling a service?" | Transaction interceptor + transaction manager + transactional resource |
| "Who turns `GET /orders/7` into a controller call?" | Web MVC dispatcher/handler mapping or WebFlux dispatcher |
| "Who bundles default dependencies and auto-configures the server?" | Spring Boot when used |
| "Who executes SQL statements?" | JDBC/JPA/the corresponding database client, not the IoC container |
| "Who executes `new` inside a `@Bean` factory?" | Factory code called by the container, not magic eliminating `new` |

## 3. Boundary with Spring AOP

### 3.1. What Does AOP Do?

**Aspect-Oriented Programming (AOP)** separates logic used across multiple layers (*cross-cutting concerns*) from core business flow, for example:

- Auditing/logging selected method calls.
- Timing, tracking metrics, tracing.
- Applying a shared validation/policy check around method calls.
- Implementing the interceptor mechanism used for `@Transactional` in common transaction setups.

Core concepts:

| Term | Meaning |
| --- | --- |
| **Aspect** | Modularization of a cross-cutting concern, e.g., tracing |
| **Join point** | Point where behavior can be applied; in proxy-based Spring AOP, primarily method execution on a Spring bean |
| **Pointcut** | Expression matching methods/join points |
| **Advice** | Behavior applied before/after/around an invocation |
| **Target** | Object containing the real business logic |
| **Proxy** | Intermediary object intercepting calls, applying interceptors, then delegating to the target |

Spring AOP does not automatically "weave" all Java code in an application. It primarily intercepts **method executions on eligible Spring beans** via proxies. Join points like field access or constructor execution are outside the normal scope of Spring AOP proxies; deeper bytecode-level AOP requires tools like AspectJ weaving, which is a different mechanism.

### 3.2. Why Adding `@Aspect` Alone Is Not Enough

The following block is only a syntax example and **does not work from the annotation alone**:

~~~java
@Aspect
class TraceAspect {
    @Before("execution(* process(..))")
    void beforeProcess() {
        System.out.println("TRACE before");
    }
}
~~~

You need `org.aspectj.lang.annotation.Aspect`/`Before` and infrastructure that detects aspects and applies proxies; typically:

- `spring-aop` and the AspectJ library for pointcut parsing.
- `@EnableAspectJAutoProxy` or equivalent auto-configuration.
- The aspect bean registered in the same `ApplicationContext`.
- The target must be a container-managed bean and the call must **go through the proxy**.

`@Aspect` describes advice; it does not automatically turn an object created with `new` outside the container into a proxied bean.

### 3.3. Critical Limitation: Self-Invocation and Proxies

Consider:

~~~java
class PaymentService {
    public void checkout() {
        this.verify();
    }

    public void verify() {
        // verification logic
    }
}
~~~

If Spring AOP attaches proxy-based advice to `verify()`, then `checkout()` calling `this.verify()` invokes the method **directly on the target**, bypassing the proxy; advice applied to external proxy calls to `verify` will **not** run on that internal call.

Common consequences:

- JDK dynamic proxies implement interfaces; code should invoke through the appropriate interface type. Class-based proxies (CGLIB) generate a subclass when conditions allow.
- With class-based proxies, `final` classes cannot be subclassed and `final` methods cannot be overridden to be advised; private methods also cannot be intercepted by proxies this way.
- Retrieving a bean with `getBean(Interface.class)` may return a **proxy**, not a direct reference to the target.
- A call **through the proxy** and an internal call via `this` can behave differently regarding advice even though the same business method code executes.

The usual design fix is moving the intercepted behavior into a separate bean and calling it through an injected dependency. Avoid overusing `AopContext.currentProxy()`, as that couples domain/service code to AOP infrastructure.

## 4. Boundary with Transaction Management

### 4.1. `@Transactional` Is Not an Automatic Transaction from Core Container

The annotation:

~~~java
@Transactional
public void transferMoney() {
    debitSource();
    creditDestination();
}
~~~

is an **illustrative snippet**, lacking `debitSource`/`creditDestination` definitions. More importantly: **`@Transactional` alone does not guarantee opening, committing, or rolling back a transaction**.

For declarative transactions to work in a typical proxy setup, you generally need:

1. Dependencies for transaction abstraction, such as `spring-tx`; for JDBC, also `spring-jdbc` and a database driver.
2. Transaction interception enabled, typically via `@EnableTransactionManagement` (or appropriate auto-configuration).
3. A `TransactionManager` bean matching the resource: e.g., `JdbcTransactionManager`/`DataSourceTransactionManager` for a JDBC `DataSource`, `JpaTransactionManager` for JPA, or an equivalent for your environment.
4. The service must be a Spring bean; calls needing the annotation must pass **through the proxy** in proxy mode.
5. Reading/writing resources must **actually participate in the same transaction**; using an unmanaged separate connection can break intended rollbacks.

**Illustrative configuration example, not standalone runnable** because `DataSource`, JDBC driver, repositories, and database connection beans must be provided:

~~~java
@Configuration
@EnableTransactionManagement
class TransactionConfig {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
~~~

Imports required in this snippet:

- `@Configuration`: `org.springframework.context.annotation.Configuration`
- `@EnableTransactionManagement`: `org.springframework.transaction.annotation.EnableTransactionManagement`
- `PlatformTransactionManager`: `org.springframework.transaction.PlatformTransactionManager`
- `DataSource`: `javax.sql.DataSource` (JDK JDBC API)
- `JdbcTransactionManager`: `org.springframework.jdbc.support.JdbcTransactionManager`

With `@Transactional`, defaults in Spring 6.x are propagation `REQUIRED`, isolation `DEFAULT`, and rollback on `RuntimeException`/`Error`; checked exceptions **do not trigger rollback by default** unless configured otherwise. Spring 6.2 provides options to customize default rollback behavior, so verify the active policy when applying it.

### 4.2. Transaction Proxy and Database Are Two Different Layers

~~~text
Caller
  |
  v
Transactional proxy  [spring-tx + AOP infrastructure]
  |-- opens/joins transaction via TransactionManager
  |-- invokes business method
  |-- commits / rolls back per policy
  v
OrderService (business logic)
  |
  v
Repository / JDBC / JPA
  |
  v
Database resource
~~~

`spring-tx` defines the API and interceptor; it does not replace a database, connection pool, JDBC driver, or mapper. Nor does `@Transactional` **turn multiple independent systems into a distributed transaction** without appropriate protocols/management.

A classic mistake:

~~~java
class OrderService {
    public void place() {
        this.save();        // self-invocation within the same target
    }

    @Transactional
    public void save() {
        // DB operations
    }
}
~~~

Under the default proxy mechanism, `this.save()` does not go through the transactional proxy; **you cannot expect a new transaction to be started solely from `save`'s annotation**. If `place()` is already running inside another transaction, it may continue using the existing transaction; the accurate takeaway is that **advice for `save` is not triggered on internal self-invocation**.

To avoid mistakes: invoke transactional methods through a Spring-managed dependency/proxy, or restructure service boundaries cleanly; test commit/rollback scenarios against a real database test rather than only reading logs.

### 4.3. Transactions Do Not Mean Every AOP Aspect Is a Transaction

Spring AOP can be used for tracing **without a database or transaction manager**. Conversely, transaction management can be used in a batch/CLI application **without an HTTP server**. These modules relate to each other, yet remain separate concepts and infrastructure.

For reactive processing, choose `ReactiveTransactionManager` and an appropriate reactive context; do not assume thread-local-based transactions for blocking JDBC apply unchanged to reactive pipelines.

## 5. Boundary with Web Modules

### 5.1. An IoC Container Is Not an HTTP Server

An `AnnotationConfigApplicationContext` can create beans for Java console, CLI, batch, or test applications. It **does not automatically create HTTP endpoints** just because service beans exist.

Example:

~~~java
@Bean
OrderService orderService(OrderRepository repository) {
    return new OrderService(repository);
}
~~~

This is an illustration requiring the relevant types to be declared. The `OrderService` bean exists in the context, yet no `GET /orders` endpoint or port 8080 appears automatically.

### 5.2. Spring Web MVC: Servlet Stack

The main module `spring-webmvc` builds on the Servlet API. Its central component is **`DispatcherServlet`**, a front controller: it receives HTTP requests, finds the right handler, binds parameters, calls the controller, processes the return value, and produces the response/error.

An illustrative controller:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final OrderLookup lookup;

    OrderController(OrderLookup lookup) {
        this.lookup = lookup;
    }

    @GetMapping("/{id}")
    String find(@PathVariable String id) {
        return lookup.find(id);
    }
}
~~~

This block is **not standalone runnable**: it lacks the `OrderLookup` definition, web imports, component registration, dispatcher configuration, and web runtime.

For a client to actually call `GET /orders/7`, you need Spring MVC configuration, a compatible servlet/web server environment, handler mappings/adapters, HTTP serialization or view resolution, and a web app lifecycle. With Spring Boot, these are typically auto-configured by a web starter; with plain Spring Framework, you must bootstrap the corresponding web infrastructure.

### 5.3. Spring WebFlux: Reactive Stack

`spring-webflux` is the reactive web framework, featuring the **`DispatcherHandler`** front controller and Reactor/Reactive Streams pipelines when configured appropriately. It can run on runtimes such as Netty or supporting Servlet adapters.

`WebFlux` is not simply "MVC where every method is async." Keep in mind:

- Result representations such as `Mono`/`Flux` and non-blocking/backpressure execution flows when the stack and dependencies support them.
- WebFlux has its own handler mappings, adapters, and result handlers; it does not use Spring MVC's `DispatcherServlet` as its default coordinator.
- Using WebFlux **does not automatically make blocking JDBC non-blocking**. When designing reactive systems, evaluate drivers, transactions, and execution threads.
- Core DI can still inject services/repositories into web handlers just like in MVC applications.

### 5.4. Using Core, AOP, and Tx Without Web

Flow diagram of two application styles:

~~~text
CLI / Scheduler -----------> Service bean
                                |
Web Client -> Dispatcher -> Controller bean -> Service bean
                                |
                   [AOP / transaction proxy if enabled]
                                |
                           Repository bean -> DB
~~~

**The HTTP dispatcher is a boundary layer**; it does not dictate how beans are constructed. **Transactions typically sit at the service/use-case boundary**, regardless of whether the call originated from a CLI, HTTP, or a job scheduler.

If you only want to learn how beans are created/injected, run a non-web `AnnotationConfigApplicationContext` example. If you need to test HTTP mappings, spin up MVC/WebFlux infrastructure. If you need to test transactions, set up a transaction manager/resource to prove commit/rollback.

## 6. Module and Dependency Reference Table

| Module / project | Typical responsibility | Do not assume |
| --- | --- | --- |
| `spring-core`, `spring-beans` | Foundational utilities, bean factory, dependency wiring | Not an HTTP router or transaction manager |
| `spring-context` | `ApplicationContext`, config, events, message source | Does not automatically start a web server |
| `spring-aop` | Proxies and interceptors for AOP | Does not automatically enable aspects without registration/config |
| `spring-tx` | Transaction abstraction, advice, and annotations | Does not automatically provide JDBC connections/database |
| `spring-jdbc` | JDBC helpers and JDBC transaction manager | Does not replace a database/driver |
| `spring-orm` | ORM/JPA integration | Not Core DI; still requires a JPA provider/config |
| `spring-webmvc` | HTTP on Servlet stack | Not a console `ApplicationContext` |
| `spring-webflux` | HTTP reactive stack | Does not automatically convert blocking code to reactive |
| **Spring Boot** (separate project) | Starters, auto-configuration, application bootstrap | Not another name for Spring Core Container |
| **Spring Security** (separate project) | Authentication/authorization, security filters/method security | Does not appear automatically because of `@Service` |

**Note on Maven:** the list above describes responsibilities; transitive dependencies accompany each other depending on version. `spring-aop` may appear on the classpath pulled in by another module, yet **having a JAR on the classpath does not mean advice is enabled or running**. Conversely, an application does not need every module to use plain DI.

## 7. Runnable Java 17 Example: Plain IoC and AOP Are Two Separate Steps

This example runs **without Spring Boot, a web server, a database, or a transaction manager**. It opens two `ApplicationContext`s:

1. The first context only provides `ProcessingService` via `@Bean`, so calling the method runs **without advice**.
2. The second context also creates the service, but enables `@EnableAspectJAutoProxy` and registers an aspect. Here the object retrieved via the interface is an AOP proxy and prints an extra log line **before** the business method.

We intentionally reuse the exact same business service to observe **changes in infrastructure**, not changes to the method body.

### 7.1. Maven Project

Requires JDK 17+, Maven, and dependency download access on the first run. Uses Spring Framework **6.2.0** (a Spring 6 release compatible with Java 17). Structure:

~~~text
spring-boundaries/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BoundaryDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>spring-boundaries</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.BoundaryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Why declare `spring-aop` and `aspectjweaver` explicitly?** So the demo's AOP setup does not rely on accidental transitive dependency assumptions. This is a `@AspectJ`-style example using **proxy-based** Spring AOP, requiring no bytecode weaving agent.

### 7.2. Complete Java File

Create `src/main/java/demo/BoundaryDemo.java`:

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class BoundaryDemo {
    public interface ProcessingService {
        void process(String id);
    }

    public static class DefaultProcessingService implements ProcessingService {
        @Override
        public void process(String id) {
            System.out.println("BUSINESS " + id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class CoreConfig {
        @Bean
        public ProcessingService processingService() {
            return new DefaultProcessingService();
        }
    }

    @Aspect
    public static class TraceAspect {
        @Before("execution(* process(..))")
        public void beforeProcess() {
            System.out.println("TRACE before");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy
    @Import(CoreConfig.class)
    public static class AopConfig {
        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    public static void main(String[] args) {
        // 1. IoC only: beans and constructor/factory method, NO aspect.
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CoreConfig.class)) {
            ProcessingService service =
                    context.getBean(ProcessingService.class);
            System.out.println("CORE proxy=" + AopUtils.isAopProxy(service));
            service.process("A01");
        }

        // 2. IoC + AOP: enable auto-proxy and register aspect in another context.
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AopConfig.class)) {
            ProcessingService service =
                    context.getBean(ProcessingService.class);
            System.out.println("AOP proxy=" + AopUtils.isAopProxy(service));
            service.process("B02");
        }
    }
}
~~~

In the `spring-boundaries` directory:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

**Stdout lines explicitly printed by `BoundaryDemo`, in order:**

~~~text
CORE proxy=false
BUSINESS A01
AOP proxy=true
TRACE before
BUSINESS B02
~~~

`mvn -version` also prints Maven/JDK info; Maven or libraries may emit extra logs depending on configuration and environment. The block above lists **the demo code's output**, without promising that is the entirety of terminal text. No HTTP request or database connection is needed.

### 7.3. Analyzing Why the Output Differs

1. Both contexts read the `processingService()` bean definition and create `DefaultProcessingService` via `@Bean`: that is **IoC capability**.
2. In the first context, there is no proxying infrastructure for aspects, so `AopUtils.isAopProxy` returns `false` and `process("A01")` prints only business output.
3. In the second context, `@EnableAspectJAutoProxy` configures advice application, `TraceAspect` is a Spring bean, and the pointcut matches `process(..)`. Spring returns a proxy for the service: `AopUtils.isAopProxy` returns `true`.
4. The call from `main` goes **through the proxy**, triggering `@Before` to print `TRACE before`, then the target runs and prints `BUSINESS B02`.
5. The example registers no `PlatformTransactionManager`, adds no `@Transactional`, and uses no web module. **AOP working does not mean transactions or HTTP are active**.

**Note:** The pointcut `execution(* process(..))` is intentionally kept simple in the demo so it does not depend on the service's package. In larger applications, restrict pointcuts to appropriate packages/interfaces/annotations to avoid unintentionally advising similarly named methods.

## 8. Adding Transactions or Web: What Changes?

### 8.1. When Adding Transactions

A use case writing data to a DB will need a repository and a real driver/data source. Example flow:

~~~text
Client (CLI/Web/Job)
    -> Spring-managed Service proxy (@Transactional if configured)
    -> Repository (JDBC/JPA)
    -> Database
~~~

You must add a matching transaction manager, enable transaction management, configure the data source/JPA, and test rollback behavior. **You cannot modify `BoundaryDemo` merely by adding `@Transactional` to a method and claim database transactions work** when the underlying resources are missing.

**A test proving real transactions** should:

- Prepare initial data before calling the service.
- Inside the service, write some rows and then intentionally throw an unchecked exception.
- Invoke through the Spring-managed proxy.
- Re-read the database after the error: the written data must have rolled back according to the expected policy.
- Check both caught/swallowed exceptions and checked exceptions, since default rollback policies are not identical.

### 8.2. When Adding HTTP

For a service to be invoked over HTTP, you need controllers and a web framework:

~~~text
HTTP GET /orders/7
  -> DispatcherServlet (Spring MVC)
  -> OrderController bean
  -> OrderService bean
  -> repository/data source (if any)
  -> HTTP response
~~~

With WebFlux, replace the dispatcher with `DispatcherHandler` alongside reactive infrastructure. Services and repositories can still be beans, though request/response handling and reactive semantics require separate verification.

Do not cram SQL logic, HTTP binding, and bean creation code into one class just because Spring manages it. Layers can interact via interfaces and constructor injection with clear responsibilities.

## 9. Identifying Common Mistakes

| Symptom or misconception | Explanation and how to address |
| --- | --- |
| Has `@Component` and assumes HTTP endpoint exists automatically | Requires controller mapping and MVC/WebFlux dispatcher/server |
| Puts `@Aspect` on a class, yet advice never runs | Check bean registration, auto-proxy infrastructure, pointcut, and proxy invocation |
| Creates service with `new` outside container and expects advice | That object is not automatically proxied by Spring |
| Advice runs when called from controller, not when called internally | Self-invocation via `this` bypasses the proxy |
| Uses `final` class/method expecting class-based proxy advice | Subclass proxies have limitations on `final` |
| Adds `@Transactional` and assumes rollback is guaranteed | Requires transaction interceptor, manager, participating resources, and right policy |
| Catches `RuntimeException` inside transactional method and returns normally | Without marking rollback-only or rethrowing to the boundary, it may commit |
| Uses JDBC transactions yet separate connection does not participate | Check how connections are obtained/bound and the manager |
| Assumes every HTTP request is a DB transaction by default | HTTP dispatchers do not define business transactions automatically |
| Assumes `spring-context` means a web server is included | Core `ApplicationContext` runs in CLI without HTTP |
| Uses WebFlux expecting blocking JDBC not to block | Must evaluate blocking dependencies, schedulers, and reactive drivers |
| Uses Spring Boot assuming every Spring module is added automatically | Starters/auto-config select components by dependencies and conditions, not "enable everything" |

## 10. Practice Scenarios with Answers

**Scenario A.** `@Service class InventoryService` is scanned into a bean, has no `@Transactional`, and web is not enabled. Can it be injected into another bean? Does it automatically roll back if a DB write method fails?

**Answer:** If scanning succeeds and dependencies are unambiguous, it can be injected. However, there is no basis to conclude automatic transactions or rollback exist. DB access depends on actual code and infrastructure.

**Scenario B.** `@EnableAspectJAutoProxy` and `@Aspect` are present, but a service calls `this.doWork()`. Will advice targeting `doWork` necessarily run?

**Answer:** No. With proxy-based Spring AOP, direct internal calls do not pass through the proxy. Extract the advised method into an appropriate collaborator or adjust boundary design.

**Scenario C.** A CLI app only needs `@Configuration`, `@Bean`, and constructor injection, with no HTTP or DB. Are Spring Boot, web, or transactions required?

**Answer:** No. Spring Framework's `AnnotationConfigApplicationContext` can initialize and wire beans in a non-web Java application.

**Scenario D.** A controller with `@GetMapping("/ping")` is registered as a Spring bean in a regular `AnnotationConfigApplicationContext`. Can you open a browser and hit it right away?

**Answer:** Not yet. You need a web dispatcher and an appropriate HTTP runtime. Bean management and HTTP routing are two separate capabilities.

**Scenario E.** A team adds `spring-tx` to Maven; are all service methods transactional now?

**Answer:** Not yet. Having the library on the classpath is insufficient; transaction management must be enabled, a manager configured, and calls routed appropriately. Annotations and bean registration are part of configuration, not the full set of conditions.

## 11. Checklist When Designing a Spring Application

1. **Separate responsibilities:** who owns business logic, who creates beans, who applies advice, who manages transactions, who handles HTTP.
2. **Start with IoC:** define key collaborators via beans and constructor injection, avoiding pervasive `ApplicationContext` lookups inside services.
3. **Intentional AOP:** define specific pointcuts/advice, invoke through Spring proxies, and check self-invocation and proxy types.
4. **Clear transactions:** choose a `TransactionManager` matching the resource, place boundaries at the right use case, and test real rollback/commit.
5. **HTTP at the boundary:** controllers handle mapping, validation, and data transfer; business logic belongs in separate services.
6. **Choose MVC/WebFlux by need:** do not pick WebFlux just because "it's newer," nor assume MVC requires a reactive stack.
7. **Understand modules/dependencies:** include the right libraries in the build, without equating classpath presence with enabled features.
8. **Keep tests fast:** unit test logic with plain Java/fakes; Spring context tests verify wiring/aspects/tx; web tests verify mappings and HTTP behavior.
9. **Don't trust annotations in isolation:** always ask "who reads this metadata, when, on which object, and through which infrastructure does the call pass?"
10. **Evaluate errors and lifecycles:** do mutable singletons need synchronization? Do database transactions roll back? Where are the server/context started and closed?

**Conclusion:** **The Core Container solves creating and wiring beans**. **AOP extends method invocations with proxies/advice**, **transaction management coordinates commit/rollback boundaries with real resources**, and **Spring MVC/WebFlux handle the HTTP protocol**. They complement each other rather than replacing one another. Understanding these boundaries avoids "put an annotation and it magically works" bugs, places responsibilities in the right layers, and produces Spring applications that are testable, maintainable, and extensible.

### Official Spring Framework Reference Documentation

- [IoC Container and BeanFactory/ApplicationContext](https://docs.spring.io/spring-framework/reference/6.2/core/beans/introduction.html)
- [Spring AOP proxying and self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Declarative transactions and @Transactional](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html)
- [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)