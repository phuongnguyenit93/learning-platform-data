# Calls Through a Spring Bean vs. Manually Created Objects with `new`

## 1. The Core Issue: The Annotation Is Present, but Does the Advice Run?

In Spring Security, a method annotated with `@PreAuthorize` does not protect itself merely because the annotation sits in the source code. In the common **Spring AOP proxy** configuration, Spring must manage the object and create a **proxy** at the call boundary. Only calls made **through the proxy** pass through the method security interceptors/advice. Similarly, `@Transactional` normally requires a transaction interceptor to open, join, commit, or roll back a transaction.

Direct comparison:

```java
// May receive a Spring-managed proxy:
OrderService managed = applicationContext.getBean(OrderService.class);
managed.changeOrder(42L);       // Method security/transaction advice has a chance to run.

// Standalone manually created object:
OrderService manual = new OrderService();
manual.changeOrder(42L);        // Invokes the method directly, bypassing Spring AOP advice.
```

This is an **object-reference illustration**, not a standalone Java program: `OrderService` and the application configuration are assumed to exist. The first case is protected only when **method security is actually enabled**, an advisor matches the method, and the bean has been proxied. Not every Spring bean automatically gets a proxy.

The consequences of instantiating a service manually with `new` can be severe:

- A method annotated with `@PreAuthorize("hasAuthority('ORDER_WRITE')")` still executes even if the caller lacks that authority.
- `@Transactional` on the method itself does not automatically activate a transaction interceptor.
- Dependency injection, `@PostConstruct`, bean scope settings, and container-managed lifecycle hooks do not apply to objects created manually outside the container.
- Unit tests calling `new Service()` may pass green yet **fail to test enforcement** of Spring method security or transaction proxies.

**Key point to remember:** "The object has the annotation" and "the call is actually intercepted by Spring" are two different things. This lesson focuses on that distinction in **Spring Security authorization** and **transactions**.

## 2. What Are a Spring Bean, Target, and Proxy?

A **Spring-managed bean** is an object registered in the `ApplicationContext`; Spring is responsible for creating or obtaining the object, injecting dependencies, applying `BeanPostProcessor`s, and managing its lifecycle according to scope.

The **target** is the object implementing the business logic. The **proxy** is the representative object sitting between caller and target, capable of executing cross-cutting logic before/after the call such as authorization or transactions. In proxy mode, **the exact reference held by the caller** determines whether the call passes through interceptors.

Two paths:

```text
A. Caller receives a proxied Spring bean
   Controller / other service
             |
             v
      Spring AOP proxy
             |
      +------+-----------------------------+
      | @PreAuthorize: authorization check |
      | @Transactional: transaction advice |
      | Other relevant advisors            |
      +------+-----------------------------+
             |
             v
         Target method
             |
             v
         Return/exception

B. Caller manually creates an object outside the container
   Caller
      |
      v
   new Service(...)
      |
      v
   Target method
   (bypasses Spring AOP interceptors)
```

Diagram A should not be read as a **fixed ordering** of security and transaction advice: ordering depends on advisors and configuration. The important invariant of proxy mode is that only external calls passing through the proxy are inspected by the respective advice. An interceptor can reject a call before the method body runs.

### Distinguishing Three Conditions

| Question | Meaning | If missing |
| --- | --- | --- |
| Is the object in the Spring container? | `@Service`, `@Component`, `@Bean`, or another registration mechanism | No bean management or automatic proxying |
| Is method security / transaction infrastructure enabled? | `@EnableMethodSecurity`, transaction management, and a suitable transaction manager | Bean may exist, but annotations are not enforced |
| Does the caller hold a reference going through the proxy to the right method? | Controller, another service, or `ApplicationContext.getBean` receives the proxied bean | `new`, self-invocation, or unproxyable methods bypass advice |

Therefore, saying "getting a Spring bean guarantees authorization" is **too broad**. You must examine configuration, advisors, annotations, method characteristics, and the call path.

## 3. Why Doesn't `new` Trigger `@PreAuthorize`?

With `@EnableMethodSecurity`, Spring Security registers advisors/interceptors for `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` according to configuration. A `@PreAuthorize` call through a proxy is handled by `AuthorizationManagerBeforeMethodInterceptor`; the manager evaluates the SpEL expression based on `Authentication`, method parameters, and relevant policies.

Example:

```java
@Service
public class DocumentService {

    @PreAuthorize("hasAuthority('DOCUMENT_DELETE')")
    public String deleteDocument(long id) {
        return "deleted-" + id;
    }
}
```

If a controller receives `DocumentService` via constructor injection, the controller normally holds the Spring bean (proxied in that configuration). An account with only `DOCUMENT_READ` will be denied when calling `deleteDocument` through the proxy.

Conversely:

```java
DocumentService direct = new DocumentService();
System.out.println(direct.deleteDocument(42L));
```

The stdout of this **plain Java snippet with no other dependencies** is:

```text
deleted-42
```

With the `direct` instance, Spring never sees the call and therefore **does not run the `@PreAuthorize` interceptor**. Even if the code reads `SecurityContextHolder` manually, that does not make a direct call pass through an interceptor automatically.

### `@EnableMethodSecurity` Is a Required Step

Spring Boot Starter Security **does not automatically enable method-level authorization** just from adding the dependency. In a typical Servlet/method-controller application, you need:

```java
@Configuration
@EnableMethodSecurity
class SecurityMethodConfig {
}
```

Two imports:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

`@SpringBootApplication` also carries the characteristics of a configuration class; `@EnableMethodSecurity` can be placed directly on the application class. Enabling method security does not replace configuring HTTP endpoint protection, authentication providers, CSRF, or web-layer policies.

## 4. `@Transactional` Is Affected the Same Way

In default transaction proxy mode, `@Transactional` is interpreted by the transaction advisor. When a call goes through the proxy, it can open a transaction, bind it to the thread, and ensure commit/rollback according to rules. Calling a method directly on an instance created with `new` **does not trigger Spring's transaction advisor simply because the annotation is on the method**.

```java
@Service
public class TransferService {

    @Transactional
    public void transfer(long fromId, long toId, long amount) {
        debit(fromId, amount);
        credit(toId, amount);
    }
}
```

The snippet above is a **business-logic illustration**; `debit`/`credit` are implemented by the system. If a call bypasses the transaction advice and each DB update commits independently, a failure in `credit` could leave `debit` committed. That is the risk of losing atomicity; actual behavior also depends on the transaction manager, data access layer, auto-commit, and any active transaction.

There is one exception to understand precisely: if `new TransferService()` is called **inside a transaction already opened by another component on the same thread**, its DB operations **may still participate in the existing transaction**. The bug is that the annotation on the `new` instance **does not itself create or adjust a new transaction boundary**. Hence, you must not state unconditionally that "every `new` call is always outside a transaction."

With `@Transactional(propagation = REQUIRES_NEW)`, the difference is even clearer: bypassing advice means the requirement to open a new transaction and suspend the current one **is not honored** by that annotation.

## 5. Runnable Java 17 Spring Boot Program: Same Method, Three Call Paths

This demo demonstrates both method security and transaction advice together without needing a web server. It uses:

- Java 17, Maven, and Spring Boot **3.5.15** (Spring Framework 6.2 / Spring Security 6.x).
- `spring-boot-starter-security` to enable method security.
- `spring-boot-starter-jdbc` + H2 to provide a real `PlatformTransactionManager`.
- Explicit `@EnableMethodSecurity` and `@EnableTransactionManagement`.
- One `GuardedService` class, with a method carrying both `@PreAuthorize` and `@Transactional`.
- Checking transaction state with `TransactionSynchronizationManager.isActualTransactionActive()`.

This is a **runnable demo in a complete Maven project**, whereas other snippets are clearly marked as architectural illustrations. The demo does not replace a production authentication system.

### 5.1. Project Structure

```text
proxy-vs-new/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                ├── ProxyVsNewApplication.java
                └── GuardedService.java
```

### 5.2. The `pom.xml` File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.15</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>proxy-vs-new</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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
```

Having H2 on the classpath lets Spring Boot auto-configure a data source and transaction manager. No records are modified in the demo; the transaction is opened purely to observe the advice.

### 5.3. The `src/main/java/demo/GuardedService.java` File

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class GuardedService {

    @PreAuthorize("hasAuthority('DOC_WRITE')")
    @Transactional
    public String update() {
        boolean active =
                TransactionSynchronizationManager.isActualTransactionActive();
        return "executed, transaction=" + active;
    }

    public String callUpdateInternally() {
        return this.update();
    }
}
```

Here:

- `update()` is a `public`, non-`final` method, compatible with class-based proxies.
- `@PreAuthorize` requires the `DOC_WRITE` authority.
- `@Transactional` requests transaction advice for valid calls through the proxy.
- `callUpdateInternally()` intentionally uses `this.update()` to illustrate **self-invocation**: a call inside the target does not re-enter the proxy.

Do not write production security logic like `callUpdateInternally()`; it serves solely as an educational failure case.

### 5.4. The `src/main/java/demo/ProxyVsNewApplication.java` File

```java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableMethodSecurity
@EnableTransactionManagement
public class ProxyVsNewApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ProxyVsNewApplication.class);
        app.setDefaultProperties(Map.of(
                "spring.main.web-application-type", "none",
                "spring.main.banner-mode", "off",
                "logging.level.root", "OFF"
        ));
        try (ConfigurableApplicationContext ignored = app.run(args)) {
            // CommandLineRunner executes the calls before run() returns.
        }
    }

    @Bean
    CommandLineRunner compareCalls(GuardedService managed) {
        return args -> {
            GuardedService manuallyCreated = new GuardedService();

            System.out.println("Spring bean proxy: "
                    + AopUtils.isAopProxy(managed));
            System.out.println("new instance proxy: "
                    + AopUtils.isAopProxy(manuallyCreated));

            try {
                authenticate("reader", "DOC_READ");

                try {
                    System.out.println("bean + reader: " + managed.update());
                } catch (AccessDeniedException denied) {
                    System.out.println("bean + reader: DENIED");
                }

                System.out.println("new + reader: "
                        + manuallyCreated.update());

                System.out.println("self-call + reader: "
                        + managed.callUpdateInternally());

                authenticate("writer", "DOC_WRITE");
                System.out.println("bean + writer: " + managed.update());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void authenticate(String username, String authority) {
        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                        username,
                        "ignored",
                        List.of(new SimpleGrantedAuthority(authority))
                )
        );
        SecurityContextHolder.setContext(context);
    }
}
```

**Note:** `authenticate(...)` only constructs a test `Authentication` in Java code; it is not a login endpoint or a production authentication approach. In a real HTTP application, `SecurityFilterChain` and authentication infrastructure are configured to authenticate callers.

### 5.5. Compiling and Running

From the `proxy-vs-new` directory (requires JDK 17+, Maven, and access to download Maven Central dependencies):

```bash
mvn -q clean package
java -jar target/proxy-vs-new-1.0.0.jar
```

Lines printed by the program when run with the configuration above:

```text
Spring bean proxy: true
new instance proxy: false
bean + reader: DENIED
new + reader: executed, transaction=false
self-call + reader: executed, transaction=false
bean + writer: executed, transaction=true
```

### 5.6. Line-by-Line Explanation

| Call | Authorization | Transaction | Why |
| --- | --- | --- | --- |
| `AopUtils.isAopProxy(managed)` | — | — | Spring returns a proxied bean because advisors match the class/method |
| `AopUtils.isAopProxy(manuallyCreated)` | — | — | Standalone `new` instance is not proxied by the container |
| `managed.update()` with `DOC_READ` | Denied | Method does not run | `@PreAuthorize` is enforced through the proxy |
| `manuallyCreated.update()` with `DOC_READ` | Not checked by advice | `false` in demo | Caller invokes target directly; annotations are inert on this call path |
| `managed.callUpdateInternally()` with `DOC_READ` | Skips check on `update()` | `false` in demo | `this.update()` bypasses proxy; outer method opens no transaction |
| `managed.update()` with `DOC_WRITE` | Allowed | `true` | Proxy runs both security and transaction advice of `update()` |

The `self-call + reader` line is especially important: **even when the object originally came from Spring**, an internal call within the same instance via `this.update()` also skips the target method's advice. The call path is the deciding factor.

`TransactionSynchronizationManager.isActualTransactionActive()` answers **whether a transaction is currently bound to the thread**, not whether a business operation committed successfully. Because the demo has no outer transaction surrounding `new`/self-call, those cases print `false`.

## 6. A Mistake More Common Than `new`: Self-invocation in the Same Bean

A service may be properly obtained from Spring yet still call an annotated method through the wrong path:

```java
@Service
public class OrderWorkflow {

    public void execute(long id) {
        approve(id); // Implicit call via this.approve(id).
    }

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    @Transactional
    public void approve(long id) {
        // Execute order approval business logic.
    }
}
```

This is an **illustrative architectural snippet**, not a standalone program. If a caller invokes `workflow.execute(id)` through the proxy, once inside the body of `execute`, calling `approve(id)` is a direct call on `this`; `@PreAuthorize` and `@Transactional` on **approve** are not triggered for that internal invocation.

Distinction:

```text
Controller -> proxy -> approve(id)
             ^ approve's authorization + transaction are applied

Controller -> proxy -> execute(id) -> this.approve(id)
                            ^
                  does not pass through proxy at approve call
```

Even if `execute` itself carries `@Transactional`, that **does not make `approve`'s advice run again**. However, if `execute`'s transaction is already open, `approve` can execute **inside the existing transaction**. The main difference is that `approve`'s own rules (such as `REQUIRES_NEW`, `readOnly`, timeout, or `@PreAuthorize`) are not applied by advice for the internal call.

### Recommended Design: Split into Two Spring Beans

```java
@Service
public class OrderWorkflow {
    private final OrderApprovalService approval;

    public OrderWorkflow(OrderApprovalService approval) {
        this.approval = approval;
    }

    public void execute(long id) {
        approval.approve(id); // Call through Spring-injected bean.
    }
}
```

```java
@Service
public class OrderApprovalService {
    private final OrderRepository repository;

    public OrderApprovalService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    @Transactional
    public void approve(long id) {
        repository.markApproved(id);
    }
}
```

These two classes are **integration snippets for an application with `OrderRepository`**, not a standalone runnable project; `markApproved` is an application repository operation. Splitting beans ensures `OrderWorkflow` holds a **proxy reference** to `OrderApprovalService`. Every `approval.approve` call passes through the target service's interception point.

For a large service, you can organize an orchestration layer and a protected business execution layer; avoid creating new beans just to put annotations on every tiny method. Place security/transactions at **the business boundary that needs protection**.

## 7. Not Every `new` Syntax Bypasses Spring

What must be avoided is **creating an object manually and using it directly outside the container**. Instantiating an object with the `new` keyword inside a **`@Bean` factory method** does not by itself strip it of Spring's mechanisms:

```java
@Configuration
class OrderConfiguration {
    @Bean
    OrderService orderService() {
        return new OrderService();
    }
}
```

When `@Configuration` is managed by Spring, the object returned from `@Bean` becomes a bean and is processed by bean post-processors; if matching advisors exist, Spring **can return a proxy** of that bean. Do not register both `@Service` and `@Bean` creating two beans for the same responsibility unless intentional.

Comparison:

| Creation and usage pattern | Becomes a Spring bean? | Can AOP advice participate? |
| --- | --- | --- |
| `new OrderService()` called directly in business code | No | Not via automatic Spring proxy mechanism |
| `@Service` + constructor injection into Controller | Yes | Yes, if infrastructure/advisors/methods are valid |
| `@Bean OrderService service() { return new OrderService(); }` then inject bean | Yes | Yes, when Spring processes and proxies the bean |
| `ApplicationContext.getBean(OrderService.class)` | Yes | Retrieves the configured bean, which may be a proxy |
| `this.securedMethod()` inside target | Target is managed, but internal call skips proxy | Advice on **securedMethod** is bypassed in proxy mode |
| `new` then explicitly wrapped with framework's proxy factory | Can be proxied via explicit mechanism | Only advisors added to the proxy; does not by default include full Spring bean lifecycle |

**Further distinction:** a class without `@Service` can still be a Spring bean via `@Bean` or another registration mechanism. Conversely, merely putting `@Service` on a class while keeping it outside component-scan, or manually `new`-ing an instance of that class, **does not turn that instance into a proxied bean**.

## 8. Dependency Injection and Lifecycle: Consequences Beyond AOP

Consider:

```java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('INVOICE_WRITE')")
    @Transactional
    public void change(long id) {
        repository.change(id);
    }
}
```

With constructor injection, `new InvoiceService()` **does not compile** because the argument is missing. If a caller manually supplies `InvoiceRepository` and calls `new InvoiceService(repo)`, the business method may run, but this object still **is not intercepted by Spring AOP**. Constructor injection makes dependencies explicit; it does not replace container management.

With field injection:

```java
@Autowired
private InvoiceRepository repository;
```

An instance created manually with `new` outside Spring normally has `repository == null` if not assigned manually, which can throw a `NullPointerException`. Even so, separate the two bugs clearly: **missing injection** and **missing AOP advice**. Fixing one does not automatically fix the other.

Other Spring mechanisms also depend on lifecycle/bean management: configuration properties binding, `@PostConstruct`, `@PreDestroy`, bean scopes, and proxy participation for `@Async`, `@Cacheable`, and transactions. Each annotation has its own activation conditions; do not deduce that all of them always work just because a class has `@Component`.

Do not rely on security/transaction proxies inside a bean's own constructor or `@PostConstruct`. During initialization, the proxy may not yet be fully established for internal calls.

## 9. JDK Proxies, CGLIB, and Method Limitations

Spring AOP has two common mechanisms:

- **JDK dynamic proxy**: primarily proxies interfaces; callers hold the interface type. Methods needing interception must belong to the method surface actually exposed by the proxy.
- **CGLIB/class-based proxy**: the proxy is a subclass of the target; it can support calling concrete methods on the class, but cannot override `final` or `private` methods.

Whether the framework chooses JDK or class-based proxies depends on configuration; Spring Boot may default to class-based proxies in certain situations, whereas Spring Framework proxy settings have different defaults. Do not guess the proxy type solely from whether the class has an interface.

| Situation | Risk | How to check |
| --- | --- | --- |
| Bean has an interface, yet application expects to inject concrete class | JDK proxy is not an instance of the implementation class | Inject the interface or configure appropriate proxy mode |
| `final class` with class-based proxy | Cannot create subclass proxy | Use suitable interface/proxy or non-final class |
| `final public method` with class-based proxy | Cannot override to insert advice | Place checks on a proxyable public method |
| `private method` with `@PreAuthorize`/`@Transactional` | Cannot be intercepted via normal proxy calls | Move enforcement to public service boundary |
| `this.method()` or implicit `method()` call | Bypasses proxy even though bean is managed | Split beans or change call path |
| Calling method before Spring finishes initializing proxy | Advice cannot be guaranteed yet | Do not trigger secured business operations in constructor/`@PostConstruct` |

**Especially with Kotlin**, classes and methods are final by default; configuring the plugin to open classes for Spring when needed must align with the proxy strategy.

### Useful Debug Checks

```java
Object bean = context.getBean("guardedService");

boolean proxied = AopUtils.isAopProxy(bean);
boolean jdk = AopUtils.isJdkDynamicProxy(bean);
boolean cglib = AopUtils.isCglibProxy(bean);
```

These three checks require importing `org.springframework.aop.support.AopUtils`. This is an integration snippet where `context` is the Spring `ApplicationContext`. `isAopProxy == true` only confirms the object is proxied; **it does not prove a specific method has matching security/transaction advice**. You must test behavior with both allowed and denied callers and observe real transactions.

## 10. Safe Fixes in Real Applications

### Approach 1: Inject Spring Beans via Constructor (Recommended Default)

```java
@RestController
@RequestMapping("/documents")
public class DocumentController {
    private final DocumentCommandService service;

    public DocumentController(DocumentCommandService service) {
        this.service = service;
    }

    @PostMapping("/{id}/archive")
    public void archive(@PathVariable long id) {
        service.archive(id);
    }
}
```

This is an integration snippet: `DocumentCommandService` is an application business bean with appropriate Spring MVC imports. The controller **does not `new` the service manually**. Method security for `archive` still needs to be enabled, and the policy must sit at the right boundary.

### Approach 2: Extract the Protected Method to Another Bean

If you currently have `this.archive(id)`, move `archive` to an injected service like the `OrderApprovalService` example. This is usually the simplest way to avoid self-invocation without forcing business code to be AOP-aware.

### Approach 3: Use Self-Proxy or `AopContext.currentProxy()` Judiciously

You can inject a bean's own proxy or use `AopContext.currentProxy()` when expose-proxy is configured. However:

- Self-injection can cause circular dependencies, hurt readability, and complicate testing.
- `AopContext.currentProxy()` couples business classes directly to Spring AOP and requires proper expose-proxy configuration.
- Do not change proxy types just to patch a design that could cleanly split beans.

Therefore, treat this as a conditional option, not the default in every service.

### Approach 4: AspectJ Weaving or Manual Proxying

Spring supports AspectJ mode for cases where advice must apply to self-invocation because bytecode is woven, though build/runtime cost, weaving setup, and annotation scope must be verified separately. This is a different mechanism from AOP proxies and is not enabled by default with `@EnableMethodSecurity`.

Spring Security also provides `AuthorizationProxyFactory` for **manually proxying** objects when method security is needed on an object not directly created by Spring. This does not mean the object automatically receives `@Autowired`, all `BeanPostProcessor`s, or transaction advice; check which advisors the proxy factory applies. For standard application services, registering beans and constructor injection remain clearer.

## 11. Transactions and Authorization: Easy-to-Misunderstand Scenarios

### 11.1. `@Transactional` Does Not Replace Authorization

If a method passes through the transaction proxy yet bypasses method security, it **can still write unauthorized data** inside a valid transaction. Conversely, a method with authorization but no proper transaction can perform partial writes and fail halfway. Both are needed when business requirements demand them.

### 11.2. Controller-Level Permissions Do Not Replace Service-Level Permissions

A service call can originate from HTTP, a scheduler, a message consumer, an integration test, or another service. Placing policies at the service boundary matters when data must be consistently protected across multiple entry points. Enabling HTTP authorization does not make `new Service()` run `@PreAuthorize`.

### 11.3. Where Exceptions Occur Determines Rollback

In proxy mode, exceptions passing through transaction advice follow rollback rules. By default Spring rolls back on `RuntimeException` or `Error`, while checked exceptions require `rollbackFor` or matching rules if rollback is desired. Do not catch exceptions and return success when the business operation requires a full rollback.

Do not conclude unconditionally that "`new` causes every SQL statement to auto-commit": if the caller already opened a transaction and operations share the same resource/thread, they may still roll back with that transaction. The real bug is that **the bypassed method's annotation is not respected as its own transaction boundary**.

### 11.4. `SecurityContext` Is Not Proof of an Interceptor

A method invoked on a manually created object can still read `SecurityContextHolder.getContext().getAuthentication()` if the caller already populated the thread's context. That still **does not trigger `@PreAuthorize`**. Likewise, a method may see an active transaction opened by another caller, which does not prove `@Transactional` on the current method executed.

## 12. Practical Testing to Catch Bypasses

### Plain Java Unit Tests Using `new`

Appropriate for testing algorithms, input validation, data processing, and mocked dependencies. They are **not integration tests** proving annotation-based method security or transaction interception.

### Integration Tests Using Spring Proxies

Assuming the project includes `spring-boot-starter-test` and `spring-security-test`:

```java
@SpringBootTest
class GuardedServiceSecurityTest {

    @Autowired
    GuardedService service;

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void readerCannotCallSecuredMethodThroughBean() {
        assertThrows(AccessDeniedException.class, service::update);
    }

    @Test
    @WithMockUser(authorities = "DOC_WRITE")
    void writerRunsWithTransaction() {
        assertEquals("executed, transaction=true", service.update());
    }
}
```

This is an **integration test snippet** (requiring JUnit 5, Spring test, and Spring Security test imports). The test must obtain the bean from the application context, not manually create `new GuardedService()`, in order to test real advice.

When testing database transactions, add tests that mutate data and intentionally throw an error, verifying state after rollback. Checking `isActualTransactionActive()` is a useful sign that advice created a transaction, **not sufficient** to prove full business consistency.

Suggested test matrix:

| Scenario | Expected outcome |
| --- | --- |
| Bean + caller lacking authority | `AccessDeniedException`; method body does not run |
| Bean + caller with sufficient authority | Method runs; transaction active when infrastructure is configured |
| Instance manually created with `new` | Annotation-based advice does not run automatically; do not use as security proof |
| Proxy -> method A -> `this.methodB()` | B's own advice is bypassed in proxy mode |
| Proxy -> bean A -> injected bean B | Method B's advice applies if matched |
| `@Bean` returning object created with `new` | Bean is still post-processed/proxied when properly configured |
| Interface present with JDK proxy | Caller uses interface type and method is on proxy surface |
| `final` class/method with CGLIB | Proxy limitations identified; real allow/deny tests |
| Caller already has active transaction | Do not confuse inherited transaction with new method transaction advice |
| Add `@Transactional(propagation = REQUIRES_NEW)` | Test actually opens a new transaction via bean, not direct internal call |

### Investigating Production Issues

If investigating an annotation being "ignored":

1. Find where the service is instantiated: is there `new SomeService(...)` or a factory holding raw instances?
2. Verify the class is registered as a bean and the exact Spring-managed reference is injected via DI.
3. Check `@EnableMethodSecurity` and the transaction manager / transaction proxy configuration.
4. Inspect the call stack: caller -> proxy -> target, or target -> `this.method`?
5. Check proxy type, method visibility/`final`, and advisors matching the annotation.
6. Write a test through the Spring bean: missing permissions must be blocked and a transaction test must take effect.
7. Only then check SpEL expressions, authority mappings, rollback rules, and other configs.

Do not log access tokens, passwords, or full principals when debugging. Logging the method, relevant roles/authorities, controlled resource ID, and authorization outcome per security policy is sufficient.

## 13. Frequently Asked Questions

**If `@Service` is on the class, is `new Service()` protected by Spring?** No. `@Service` lets component scanning recognize the class to register **a bean**; it does not make instances created elsewhere automatically pass through a proxy.

**Can I `@Autowired` a class and also manually `new` another instance?** Yes in Java, but they are two distinct objects. Method security/transaction advice applies to the proxied bean; manually created objects do not automatically get those interceptors.

**Is `@Bean` using `return new Foo()` wrong?** No. The returned object is registered in the container and can be post-processed/proxied. Distinguish **how the object is constructed** from **how callers obtain the object**.

**I see `AopUtils.isAopProxy(bean) == true`, so is every method protected?** No. A proxy may exist for transactions or another advisor; only methods matched by an advisor receive the corresponding advice. Test the specific method's behavior.

**Why isn't `this.securedMethod()` checked while `otherBean.securedMethod()` is?** An internal `this` call jumps straight into the target; `otherBean` is normally a proxy returned by Spring via DI.

**What if a method without `@PreAuthorize` calls a method with `@PreAuthorize` in the same class?** In proxy mode, the internal call can bypass the second method's `@PreAuthorize`. Never rely on the second method's annotation to guard an internal call path.

**If I only use JDK proxies, are concrete methods intercepted?** Only calls that can go through the proxied interface surface are handled appropriately by the interceptor; consider proxy configuration and annotation placement. Spring Boot can configure class-based proxies in some setups.

**What if a `new` service is called inside a transactional method?** The new instance is not automatically proxied by Spring AOP. However, its DB operations may use the caller's existing transaction on the same thread; do not mistake that for `@Transactional` on the new instance taking effect.

**What if I need to programmatically proxy an object?** Dedicated proxy factory / AspectJ mechanisms exist, but you must explicitly configure advisors and understand their scope. Most application services are clearer when registered as beans and injected.

## 14. Pre-Production Service Checklist

- [ ] Business services with sensitive access are registered and obtained from the Spring container.
- [ ] Controllers, listeners, schedulers, and other services use constructor injection and never manually instantiate services needing method advice.
- [ ] `@EnableMethodSecurity` is enabled when relying on `@PreAuthorize`/`@PostAuthorize`.
- [ ] Transaction manager and transaction management are configured when using `@Transactional`.
- [ ] Protected methods are proxyable; advice does not rely on `private`, `final`, or self-invocation.
- [ ] Protected methods are called through a **proxy reference**, including during internal orchestration.
- [ ] `@Bean { return new ...; }` is not confused with `new` objects created outside the container.
- [ ] Tests exist for **deny** (missing permission), **allow** (valid permission), and transaction rollback where required by business logic.
- [ ] AOP proxy type behavior (JDK/CGLIB), `REQUIRES_NEW`, nested calls, and caller transactions are well understood.
- [ ] Unit tests instantiating `new` are never used as proof that method security is enforced.

**Technical conclusion:** In Spring proxy mode, what decides behavior is not whether a class contains `@Service`, `@PreAuthorize`, or `@Transactional` in source code. What decides is **whether the call passes through a Spring AOP proxy with the matching advisors**. Obtaining beans from the container, enabling the proper infrastructure, and designing calls across bean boundaries ensure consistent authorization and transaction enforcement.

## Official References

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Framework 6.2 — Proxying Mechanisms and self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework — Transactional annotation and proxy mode limitations](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Transaction propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Security — Method security testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
