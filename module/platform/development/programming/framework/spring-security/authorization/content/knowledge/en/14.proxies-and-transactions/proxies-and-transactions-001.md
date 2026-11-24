# Spring AOP and Conditions for Method Security to Execute

## 1. Why Does a Method with `@PreAuthorize` Still Run?

Consider two calls to the same method:

```java
// (1) reportService is injected by Spring from the ApplicationContext
reportService.deleteReport("R-7");

// (2) inside ReportService
this.deleteReport("R-7");
```

Suppose `deleteReport` is annotated with `@PreAuthorize("hasRole('ADMIN')")`. In the default Spring Method Security configuration using a **Spring AOP proxy**, call (1) goes through the proxy to check authorization, whereas call (2) is **self-invocation** that can go directly to the target object and bypass the check. This is the cause of many authorization bugs in the service layer even though the annotation looks completely right.

This lesson explains the conditions required for Spring Security to **actually intercept a method call**: enabling Method Security, identifying a Spring-managed bean, ensuring the call path goes through the proxy, proxy type, method interceptability, enabled annotations, authentication data, and transaction-related factors.

After this lesson, you will be able to:

1. Distinguish a **Spring AOP proxy** from the Spring Security HTTP filter chain.
2. Understand how Spring Security applies `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter`.
3. Determine when a call **goes through the proxy** and when it is bypassed.
4. Distinguish JDK interface proxies from CGLIB subclass proxies, especially limitations around `private`, `final`, `static`, and self-invocation.
5. Write a Spring Boot Java 17+ example verifying that **the same method** can be denied through the proxy yet executed via `this`.
6. Design services and tests to catch bugs early, including when combining `@Transactional` and `@Async`.

**Technical context:** Spring Security 6.x / Spring Boot 3.x with proxy-based Method Security, which is the common case in Spring MVC, REST, and service applications. Spring Security offers advanced modes such as AspectJ weaving, but they are not the default behavior here.

## 2. From a Java Call to the Security Interceptor

Spring AOP does not automatically rewrite the bytecode of every Java call in an application. In the standard proxy mechanism, Spring places **a proxy object** in front of the target bean. Callers obtaining the bean from the container normally receive the proxy, and the proxy runs a chain of advisors/interceptors before or after forwarding the call to the target.

```text
Controller / other service / test
                  |
                  | call reportService.deleteReport(...)
                  v
         Spring-injected bean
              (AOP proxy)
                  |
                  v
          Method Security advisors
           |  @PreFilter: filter parameters
           |  @PreAuthorize: pre-invocation authorization check
           |  Authentication + SpEL + AuthorizationManager
           |
        granted? ------- no ------> AccessDeniedException
           |
          yes
           v
          Target bean
          deleteReport(...)
           |
           v
           |  @PostAuthorize: check return value
           |  @PostFilter: filter return value
           v
        Caller receives result
```

This is a conceptual diagram: the exact advisor order depends on the annotation type and configuration. `@PreFilter`, `@PreAuthorize`, `@PostAuthorize`, and `@PostFilter` have their own interceptors. For example, in modern Spring Security, `@PreAuthorize` is handled by `AuthorizationManagerBeforeMethodInterceptor`, using `PreAuthorizeAuthorizationManager` to evaluate the expression.

**Key takeaway:** an annotation is not code that automatically executes whenever the JVM runs a method. An annotation is metadata; appropriate AOP infrastructure and **a call crossing the proxy boundary** are required for the interceptor to trigger.

### How Does Spring Method Security Differ from HTTP Security?

| Mechanism | Primary interception point | Best suited to protect | Requires HTTP? |
| --- | --- | --- | --- |
| `SecurityFilterChain` | Incoming HTTP requests to the web application | URLs, routes, endpoints, requests | Yes |
| Method Security | Spring bean calls via advisors | Service operations, parameters, return values | No |
| Database-level access control | Data queries/writes | Ownership, tenant isolation, race conditions | No |

`requestMatchers("/admin/**").hasRole("ADMIN")` cannot replace constraints on a service invoked from a scheduler, message listener, or another service. Conversely, `@PreAuthorize` does not configure HTTP authentication or the 401/403 response flow on its own.

## 3. Conditions for Method Security to Run

You can check them in the following order:

| Condition | If missing | Practical check |
| --- | --- | --- |
| Compatible Spring Security and AOP libraries are on the classpath | No suitable method authorization infrastructure | Check dependencies and `ApplicationContext` |
| `@EnableMethodSecurity` or equivalent configuration is present | `@PreAuthorize` is not activated just by adding the starter | Inspect configuration and test a call |
| Method/class has an **enabled** and clearly defined annotation | No advisor applies to the method to be protected | Check annotations and enable options |
| Target is a Spring bean, proxy is created, and caller uses the proxy bean | Manually `new`-ed objects are not intercepted | `AopUtils.isAopProxy(bean)` |
| Call is interceptable and **goes through the proxy** | `this.method()`, `private`/`final` (with CGLIB) can bypass | Test calling from another bean |
| `Authentication` and valid policy/expression are present | Denied or mis-evaluated against context | `@WithMockUser`, test allow/deny cases |
| Not disrupted by thread switching or unexpected advisor ordering | Evaluated with a different security context, or check order differs from expectations | Test the real path with async/transactions |

The AOP and annotation conditions determine **whether the mechanism intercepts the method at all**. Having the right `Authentication` and policy determines **whether an intercepted call is allowed or denied**. Separating these two layers avoids misdiagnosis: a call returning successfully does not necessarily mean access was granted; it may mean the call bypassed the interceptor.

## 4. Enabling Method Security Properly

### 4.1. Registering the Configuration

With Java config:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

You can place `@EnableMethodSecurity` directly on the `@SpringBootApplication` class, as in the full example in section 7. In Spring Boot, adding the `spring-boot-starter-security` dependency **does not enable** Method Security by default. `@EnableMethodSecurity` replaces the older `@EnableGlobalMethodSecurity` configuration in modern Spring Security.

`@EnableMethodSecurity` enables the pre/post annotation group by default:

- `@PreAuthorize`: condition must be true **before** the method body executes.
- `@PostAuthorize`: evaluated **after** the method body returns; can reference `returnObject`.
- `@PreFilter`: removes input parameter elements that do not satisfy the condition.
- `@PostFilter`: filters elements of the return value.

To use `@Secured` or JSR-250 (`@RolesAllowed`, `@PermitAll`, `@DenyAll`) via their respective mechanisms, you must enable the options:

```java
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
```

That configuration is an **alternative example** and does not need to be added alongside the default `@EnableMethodSecurity` for the demo. The corresponding annotation dependency is required when using JSR-250. If `prePostEnabled = false` is configured, the pre/post annotations are no longer automatically enabled by `@EnableMethodSecurity`.

### 4.2. Beans, Proxies, and Scan Scope

Typically, a service must be a Spring-managed bean:

```java
@Service
public class PaymentService {
    @PreAuthorize("hasAuthority('payment:approve')")
    public void approve(long paymentId) {
        // ...
    }
}
```

Callers must have `PaymentService` injected by Spring and must invoke it **through the container-provided reference**. This differs from:

```java
PaymentService service = new PaymentService();
service.approve(42L); // Manual Java object; no Spring AOP advice
```

The snippet above only illustrates the bug and is not code to use in a real application. `@Service` is the common way to create a bean via component scanning; beans can also be provided via `@Bean`. Security annotations can be placed on methods, classes, or interfaces according to Spring Security rules, though conflicting annotations across multiple interfaces/supertypes should be resolved explicitly rather than relying on ambiguous outcomes.

**Being a bean alone is not enough:** if a method calls another protected method within the same target via `this`, the internal call does not pass back through the proxy.

### 4.3. Limitations of Annotations and Expressions

Example:

```java
@PreAuthorize("hasAuthority('report:read')")
public Report readReport(String id) {
    // ...
}
```

`hasAuthority('report:read')` looks for an authority with the exact string `report:read` in `Authentication`. Under the default configuration, `hasRole('ADMIN')` checks for the `ROLE_ADMIN` authority, not just the string `ADMIN`. Specify consistently how the application assigns roles/authorities.

Spring Security does not automatically infer object-level permissions from method names. If you need owner/ACL checks, you must provide appropriate expressions and trusted data sources. Even when the interceptor works flawlessly, a poorly written authorization policy still causes security flaws.

## 5. JDK Proxies and CGLIB Proxies

Spring AOP has two main proxy mechanisms:

| Characteristic | JDK dynamic proxy | CGLIB class proxy |
| --- | --- | --- |
| Proxy object | Implements the target's interface(s) | Subclass generated from the target |
| Suitable when | Service declares an interface; caller uses the interface | Bean has no interface or configuration uses class proxies |
| Methods callable through proxy | Methods exposed on the proxied interface(s) | Instance methods that can be overridden/intercepted |
| Main limitation | Methods not in the interface are not exposed on the JDK proxy | `final` classes cannot be subclassed; `final`/`private` methods cannot be overridden |
| Self-invocation `this.method()` | Bypasses AOP advice | Bypasses AOP advice |

The Spring Framework documentation describes the default for plain Spring AOP: if an interface is present it can use a JDK proxy, otherwise CGLIB. **Spring Boot can configure class-based proxies by default**; do not infer the proxy type solely from the presence of an interface. The reliable way is to inspect the actual object:

```java
import org.springframework.aop.support.AopUtils;

System.out.println(AopUtils.isAopProxy(service));
System.out.println(AopUtils.isJdkDynamicProxy(service));
System.out.println(AopUtils.isCglibProxy(service));
```

These three lines are an **illustrative code snippet**, assuming `service` has been injected by Spring; the output depends on the active configuration.

### `private`, `final`, `static`, and Constructors

- `private` methods cannot be interception points for a subclass proxy; placing `@PreAuthorize` on a private helper does not protect calls to that helper.
- `final` methods on a CGLIB-proxied class cannot be overridden and therefore cannot be advised; `final` classes cannot have a subclass proxy created. With JDK interface proxies, you must look at actual calls through the interface, and you should not turn that into a way to work around class design.
- `static` methods are not invoked through an instance proxy in the manner of normal Spring AOP method advice.
- Constructors and code executing before the bean/proxy is handed to callers are not safe places to rely on `@PreAuthorize` on other methods. Avoid calling logic requiring method security from a constructor or early initialization assuming the proxy already protects it.
- Spring AOP can support some non-public methods in certain proxy setups, but **public service methods called from another bean** are the clearest and easiest-to-test choice.
- If using Kotlin, classes and methods are `final` by default, so pay special attention to the `all-open` plugin mechanism or interface/proxy design.

**Switching from a JDK proxy to CGLIB does not fix self-invocation.** Both only apply advice when the call enters the proxy.

## 6. Self-invocation: Causes, Consequences, and Fixes

Consider this buggy example:

```java
@Service
public class InvoiceService {

    public void submitInvoice(long id) {
        this.publishInvoice(id); // direct call on target
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void publishInvoice(long id) {
        // Assume side effects that write real data
    }
}
```

Another service calls `invoiceService.submitInvoice(10)` through the proxy. Once the proxy delegates the call into the body of `submitInvoice`, the expression `this.publishInvoice(10)` is just an internal Java call. Because it **does not create a new invocation entering the proxy**, the advisor for `publishInvoice` does not run.

This behavior also commonly affects `@Transactional`, `@Cacheable`, and other Spring AOP mechanisms. It is not a bug in SpEL or `hasRole`.

### Proper Design: Separate Bean Boundaries

```java
@Service
public class InvoicePublishingService {

    @PreAuthorize("hasRole('ADMIN')")
    public void publishInvoice(long id) {
        // operation only admin is allowed to perform
    }
}
```

```java
@Service
public class InvoiceWorkflowService {

    private final InvoicePublishingService publishingService;

    public InvoiceWorkflowService(InvoicePublishingService publishingService) {
        this.publishingService = publishingService;
    }

    public void submitInvoice(long id) {
        publishingService.publishInvoice(id); // through bean/proxy
    }
}
```

These two snippets illustrate splitting beans; when placed in separate Java files with the necessary imports, the protected method is invoked through the Spring-injected reference. Workflow callers do not need to know AOP details. Even then, test the actual bean in the context and the data update logic.

Less preferred options include injecting the bean's own proxy reference or using `AopContext.currentProxy()`. They increase coupling to Spring AOP, can introduce circular dependencies, or require extra configuration. Whenever design changes are allowed, **extracting a service responsible for the protected method** is usually easier to understand, maintain, and test.

If you genuinely need to intercept **internal calls as well**, Spring Security provides AspectJ weaving mode (`@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)`), but you must fully configure AspectJ, the aspects library, and compile-time or load-time weaving. **Simply changing one annotation attribute without setting up weaving does not turn self-invocation into a protected call.**

## 7. Runnable Example: Observing Proxies and Self-invocation

This is a Java 17 / Spring Boot `3.5.8` application (a pinned version for the demo). It does not need an HTTP server or database. The `SELF_CALL` line illustrates **an intentional vulnerability** on a method that only returns a string so you can learn AOP; never copy this calling pattern into business logic with side effects.

Structure:

```text
method-security-proxy-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── MethodSecurityProxyDemoApplication.java
    │   ├── ReportService.java
    │   └── ReportWorkflow.java
    └── test/java/demo/
        └── ReportServiceSecurityTest.java
```

### 7.1. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'method-security-proxy-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-security` provides Spring Security and its related dependencies; `@EnableMethodSecurity` in the application registers the method authorization infrastructure. `spring-boot-starter-test` and `spring-security-test` support testing with `@WithMockUser`.

### 7.2. Service with Three Call Paths

**`src/main/java/demo/ReportService.java`:**

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public String readReport(String id) {
        return "report:" + id;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String adminOnly() {
        return "admin-result";
    }

    // ONLY TO ILLUSTRATE THE ISSUE; do not use in production business logic.
    public String selfCallDemo() {
        return this.adminOnly(); // bypasses proxy method-security advice
    }
}
```

`readReport` and `adminOnly` are checked by Spring Security when callers invoke them through the proxy. By contrast, `selfCallDemo` calls `this.adminOnly()` once already inside the target; therefore, the interceptor for `adminOnly` does not run again.

### 7.3. Workflow Going Through an Injected Bean

**`src/main/java/demo/ReportWorkflow.java`:**

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class ReportWorkflow {

    private final ReportService reports;

    public ReportWorkflow(ReportService reports) {
        this.reports = reports;
    }

    public String callAdmin() {
        return reports.adminOnly();
    }
}
```

`ReportWorkflow` receives `ReportService` from Spring, so even though `callAdmin` has no annotation, the call **to `ReportService.adminOnly`** still goes through the `ReportService` proxy.

### 7.4. Configuration and Observation Program

**`src/main/java/demo/MethodSecurityProxyDemoApplication.java`:**

```java
package demo;

import java.util.List;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class MethodSecurityProxyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityProxyDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo(
            ReportService reports,
            ReportWorkflow workflow) {
        return args -> {
            var authentication = new UsernamePasswordAuthenticationToken(
                "alice",
                "demo-only",
                List.of(new SimpleGrantedAuthority("report:read"))
            );
            SecurityContextHolder.getContext()
                .setAuthentication(authentication);

            try {
                System.out.println("PROXY: " + AopUtils.isAopProxy(reports));
                System.out.println("READ: " + reports.readReport("R-7"));

                try {
                    reports.adminOnly();
                    System.out.println("DIRECT_ADMIN: UNEXPECTED");
                } catch (AccessDeniedException denied) {
                    System.out.println("DIRECT_ADMIN: DENIED");
                }

                // Illustration only: this.adminOnly() bypasses security advice.
                System.out.println("SELF_CALL: " + reports.selfCallDemo());

                try {
                    workflow.callAdmin();
                    System.out.println("OTHER_BEAN: UNEXPECTED");
                } catch (AccessDeniedException denied) {
                    System.out.println("OTHER_BEAN: DENIED");
                }
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }
}
```

In the demo program, `alice` has the `report:read` authority but **does not have `ROLE_ADMIN`**. Because `ReportService` is a proxied Spring bean, calling `reports.adminOnly()` is denied. `reports.selfCallDemo()` is called through the proxy, yet inside it calls `this.adminOnly()`, so the interceptor for `adminOnly` does not run.

Generate the corresponding Gradle Wrapper if the project does not have one yet, then run:

```bash
./gradlew bootRun
```

On Windows PowerShell: `.\gradlew.bat bootRun`. If Gradle is installed locally and the project has no Wrapper yet, you can run `gradle bootRun`.

**The stdout lines printed by the demo code** (Spring Boot also prints startup logs) are:

```text
PROXY: true
READ: report:R-7
DIRECT_ADMIN: DENIED
SELF_CALL: admin-result
OTHER_BEAN: DENIED
```

Explanation in exact order:

1. `PROXY: true` proves the bean is wrapped in a Spring AOP proxy.
2. `READ` succeeds because the authority matches `report:read`.
3. `DIRECT_ADMIN: DENIED` proves calling `@PreAuthorize("hasRole('ADMIN')")` through the proxy works.
4. `SELF_CALL: admin-result` is **evidence of a self-invocation bypass**, **not a successful authorization grant**.
5. `OTHER_BEAN: DENIED` proves calling the same method from another bean via injection still enforces the check.

Manually creating `UsernamePasswordAuthenticationToken` is a **technique to simulate a security context for the demo**. Never accept a username from a client and construct an authenticated token like this in a real system; use the authentication flow configured by Spring Security.

## 8. Testing Security with `@SpringBootTest`

**`src/test/java/demo/ReportServiceSecurityTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class ReportServiceSecurityTest {

    @Autowired ReportService reports;
    @Autowired ReportWorkflow workflow;

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "report:read"
    )
    void proxyEnforcesProtectionOnExternalCalls() {
        assertTrue(AopUtils.isAopProxy(reports));
        assertEquals("report:R-7", reports.readReport("R-7"));

        assertThrows(
            AccessDeniedException.class,
            reports::adminOnly
        );
        assertThrows(
            AccessDeniedException.class,
            workflow::callAdmin
        );
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void selfInvocationDemonstratesBypass() {
        // ONLY verifies the issue; do not accept this pattern in production.
        assertEquals("admin-result", reports.selfCallDemo());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanInvokeProtectedMethod() {
        assertEquals("admin-result", reports.adminOnly());
        assertThrows(
            AccessDeniedException.class,
            () -> reports.readReport("R-7")
        );
    }

    @Test
    @WithAnonymousUser
    void anonymousCallerCannotRead() {
        assertThrows(
            AccessDeniedException.class,
            () -> reports.readReport("R-7")
        );
    }
}
```

Run:

```bash
./gradlew test
```

`@SpringBootTest` loads the real context, while `@WithMockUser`/`@WithAnonymousUser` come from `spring-security-test`. `@Autowired` obtains the service proxy rather than manually creating `new ReportService()`. The four tests simultaneously confirm: **proxy presence**, **allowing with the right authority**, **denying when missing authority**, **self-invocation bypass**, and **denying anonymous callers**.

This is a useful test because a unit test calling a plain Java object directly can pass every business assertion while **never executing the interceptor**. If replacing `@SpringBootTest` with a test slice like `@WebMvcTest`, verify whether that slice imports the necessary method security configuration and service beans.

## 9. Why Do `@PreAuthorize` and `@PostAuthorize` Differ When Side Effects Exist?

The two annotations execute at different points:

```java
@PreAuthorize("hasAuthority('document:write')")
public void updateDocument(long id) {
    // update occurs after the pre-authorize check succeeds
}
```

```java
@PostAuthorize("returnObject.owner() == authentication.name")
public Document findDocument(long id) {
    // this method has already executed before checking the result
    return repository.findById(id).orElseThrow();
}
```

These are **illustrative syntax snippets**, assuming a `Document` record and Spring-injected `repository` exist; they are not standalone Java programs. `@PostAuthorize` allows using `returnObject`, which is useful when you must load a resource first to know whether viewing is permitted. However, if the method body **already wrote data**, post-checking can happen too late to prevent side effects. For write operations, check beforehand or tie authorization conditions directly into the data operation and transaction.

`@PreFilter`/`@PostFilter` also require going through the proxy and can modify collections; do not assume the annotations apply automatically if the call is self-invocation.

## 10. Method Security and `@Transactional`

A service often has both:

```java
@PreAuthorize("hasAuthority('transfer:approve')")
@Transactional
public void approveTransfer(long transferId) {
    // check business constraints and update within transaction
}
```

**Both Method Security and Transaction Management use advisors** in Spring AOP proxy mode. A single call can pass through multiple interceptors; **advisor order** determines when authorization is checked and when the transaction begins. Do not assume every application has the same order, because custom `order`, `offset`, custom advisors, and different bean layouts exist.

Points to remember:

- `@PreAuthorize` intercepts before the **method body** runs; it does not by default solve database atomicity.
- `@PostAuthorize` performs a post-invocation check; if the method has already committed data, you cannot expect post-checking to automatically "roll back" side effects.
- `@Transactional` also carries self-invocation risk in proxy mode. A `this.update()` call can bypass `update`'s transaction advice as well.
- When ownership/ACL can change concurrently, checking permission before and writing after creates a **TOCTOU (time of check, time of use)** gap. For sensitive writes, enforce the authorization condition directly in the query/update inside the transaction, such as `UPDATE ... WHERE id = :id AND owner_id = :currentUser`, and verify the affected row count.
- If you need clear separation between security and transaction boundaries, organize a secured facade calling a separate transactional bean, test both allow and deny cases, and configure advisor order when genuinely needed.

An easily controllable design diagram:

```text
HTTP Controller / Message Consumer
              |
              v
    Secured Facade Bean
    @PreAuthorize(...)
              |
              v
    Transactional Service Bean
    @Transactional
              |
              v
       Repository / DB
```

Both methods should be called through **the proper bean proxy**. A layered design does not replace record-level authorization constraints in the DB; it simply makes boundaries easier to read and test.

## 11. Threading, Async, and Bean Lifecycle Issues

### 11.1. Thread-Bound `SecurityContext`

In a typical Servlet application, Spring Security uses `SecurityContextHolder` to bind authentication to the execution context, backed by `ThreadLocal` by default. When switching to another thread via `@Async`, `CompletableFuture`, an executor, or a manually spawned `Thread`, the context may **not propagate automatically** to the new thread.

Consequence: a protected method in an async task may be denied even though the original caller is authenticated, or it may receive an inappropriate context if the application mishandles context cleanup. Consider `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextAsyncTaskExecutor`, or framework-provided propagation mechanisms, and **clear the context at the right time**. Never hard-code a shared admin account across an entire thread pool as a "fix."

### 11.2. Bean Initialization and Constructors

Spring must instantiate and prepare beans before callers can receive the full proxy. Do not rely on logic requiring `@PreAuthorize` inside a constructor to protect an initialization operation. Similarly, calling a protected method from `@PostConstruct` may not go through the proxy path you expect.

If work must run after startup, place it in another injected bean and call it through the proxy, establishing the exact security context for the task. The `CommandLineRunner` in the demo runs after the context initializes, but it constructs authentication manually **only for illustration**.

### 11.3. Non-HTTP Entry Points

Method Security can protect calls from jobs, message listeners, or internal components **if** they call a Spring-managed bean through its proxy and have suitable authentication/policies. The absence of an HTTP request does not mean a current user exists automatically; background jobs need an explicit service-account policy or identity.

## 12. Common Pitfalls and How to Diagnose Them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `@PreAuthorize` is ignored everywhere | `@EnableMethodSecurity` not enabled; bean not scanned | Check configuration and test through the context |
| Only calls from some places are bypassed | `this.method()`, object created via `new` | Inspect call graph; split beans or call via bean proxy |
| Annotation placed on `private` method has no effect | Cannot be intercepted via subclass AOP proxy | Move security boundary to a public service method |
| Annotation on `final` method/class fails under CGLIB | Cannot override/subclass | Remove `final` at proxy boundary or design a suitable interface |
| Injecting implementation class fails under JDK proxy | Proxy object only implements the interface | Inject via interface or configure class proxies when appropriate |
| `@Secured`/`@RolesAllowed` used but never enforced | `securedEnabled`/`jsr250Enabled` not enabled | Enable the right option and test that annotation |
| Denied despite having the expected role | Confusing `ROLE_ADMIN` with `ADMIN`, wrong authority or context | Inspect actual `GrantedAuthority` and SpEL |
| Works on direct call, fails in async | Security context not propagated to the new thread | Use delegation mechanisms and test async end-to-end |
| Transaction does not start on internal call | Transaction proxy bypassed via self-invocation | Split beans and verify actual transaction behavior |
| Unit tests pass while production leaks access | Tests call `new Service()` or mocks skip advisors | Add `@SpringBootTest` + `@WithMockUser` integration tests |
| HTTP 403 and 401 behave unexpectedly | Different entry point / exception translation config | Check authentication and web error handling |
| `hasPermission` or bean expression fails | Missing evaluator/bean, wrong parameter name, or bad SpEL | Check expression handler, `@P`, data sources, and deny tests |

### Minimal Investigation Checklist

1. **Bean:** Is `AopUtils.isAopProxy(service)` `true`? If `false`, check whether the bean is in the context and whether the method has an enabled annotation.
2. **Call path:** Does the caller hold a Spring-injected bean or a manually `new`-ed object? Is there `this.protectedMethod()` in the same class?
3. **Proxy type:** Check `AopUtils.isJdkDynamicProxy`/`isCglibProxy`; is the method `private`/`final`/`static` or only declared on the implementation?
4. **Annotation:** Is `@EnableMethodSecurity` on a configuration actually loaded? Was `prePostEnabled` turned off or `securedEnabled`/`jsr250Enabled` forgotten?
5. **Authentication:** Does `Authentication` have the expected principal and authorities? Was there a thread/context switch?
6. **Tests:** An authorized user must pass; an unauthorized user must get `AccessDeniedException`; the method must produce no side effects when blocked.
7. **Transactions and data:** Is ownership/ACL in the DB verified at write time?

`AopUtils.isAopProxy(service) == true` only proves **the bean has an AOP proxy**, not that every protected method or every call path is protected. A bean may be proxied due to `@Transactional`/logging rather than Method Security. Always confirm with tests **allowing and denying the exact method**; advisor/debug logs can assist but do not replace outcome tests.

## 13. Quick Knowledge Check

1. **Does adding `spring-boot-starter-security` automatically enable `@PreAuthorize`?**  
   No. You normally need `@EnableMethodSecurity` or equivalent configuration.

2. **Is a `@Service` instantiated with `new` protected by method security?**  
   No. A manually `new`-ed object is not the proxy bean configured by Spring.

3. **Why is `this.adminOnly()` dangerous?**  
   Because an internal call does not go through the proxy to run `adminOnly`'s interceptor.

4. **Does switching from a JDK proxy to CGLIB fix self-invocation?**  
   No. Both are still proxy mechanisms and do not intercept `this.method()` automatically.

5. **Why can a `final` method break CGLIB protection?**  
   A subclass proxy cannot override a `final` method.

6. **How do `@PreAuthorize` and `@PostAuthorize` differ?**  
   One checks before the method body runs; the other checks after the method and can read `returnObject`.

7. **Can Method Security be used in a job without an HTTP request?**  
   Yes, if the job calls through the proxy and has appropriate authentication/policies.

8. **Does `@Transactional` make `@PreAuthorize` unnecessary?**  
   No. Transactions manage consistency/rollback; authorization decides who may perform the operation. Both have proxy boundaries and should be tested together.

9. **If `isAopProxy(service)` returns `true`, is that method guaranteed to be safe?**  
   No. You must still verify the right annotation, interceptable method, proxied call path, and correct authorization decision.

10. **What is the most maintainable fix for self-invocation?**  
    Move the protected method to a separate service bean and inject that bean into the caller, then add integration tests for missing-permission cases.

## 14. Official References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): enabling `@EnableMethodSecurity`, interceptors, annotations, advisor configuration, and AspectJ mode.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK proxies, CGLIB, `final`/`private`, self-invocation, and workarounds.
- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html): proxy concepts in Spring AOP.
- [Spring Security — Method Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser` and testing method authorization.
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): propagating `SecurityContext` across threads/executors.
- [Spring Boot 3.5.8 release](https://spring.io/blog/2025/11/20/spring-boot-3-5-8-available-now/): version information used in the example.

**Key takeaway:** a Method Security annotation protects a call only when the infrastructure is enabled, the bean and method are suitable, the call goes through a proxy with the matching advisor, and the authorization condition is evaluated with the right authentication. **Self-invocation is a critical limitation of Spring AOP proxies**; design service boundaries carefully, test real call paths, and protect writes at the data layer when needed.