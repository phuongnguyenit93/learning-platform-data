# @EnableMethodSecurity and Conditions for Annotations to Take Effect

> **Module:** Spring Security - fundamentals  
> **Group:** Method protection  
> **Core Question:** Why can putting `@PreAuthorize` on a method still fail to block an unauthorized caller? What conditions must hold for Spring Security to actually check the method call?

## 1. What Should You Understand After This Lesson?

You will understand:

- The role of `@EnableMethodSecurity` in **activating method-level authorization** in Spring Security.
- The difference between declaring a `@PreAuthorize` annotation and having that annotation actually **enforced by the Spring Method Security interceptor**.
- Key conditions: configuration is loaded into the ApplicationContext, the object is a Spring-managed bean, the call passes through a proxy/advice, the method can be intercepted, and `Authentication`/`GrantedAuthority` satisfy the condition.
- Why calling a method within the same class (`self-invocation`), using `new`, placing annotations on private/final methods, or misconfiguring Servlet/WebFlux layers can cause expected enforcement to fail.
- How to write and run a Spring Boot example with `@EnableMethodSecurity`, `@PreAuthorize`, and `@WithMockUser` to verify both allowed and denied calls.
- When to use `@PreAuthorize`, `@PostAuthorize`, `@Secured`, JSR-250, and `@EnableReactiveMethodSecurity`.

## 2. What Does Method Security Protect?

**Method security** controls access when invoking **application methods**. Example:

~~~java
@PreAuthorize("hasAuthority('report:publish')")
public String publishReport() {
    return "published";
}
~~~

This rule means: *before executing the method body*, Spring Security must decide whether the current principal holds the `report:publish` authority. If not, an authorization interceptor denies the call, typically with an exception in the `AccessDeniedException` family.

The scope of method security differs from HTTP endpoint authorization configuration:

| Layer | Example | When checked |
| --- | --- | --- |
| HTTP request security | `requestMatchers("/reports/**").authenticated()` | When the request passes through the security filter chain |
| Method security | `@PreAuthorize("hasAuthority('report:publish')")` | When the method is called through the interceptor infrastructure |
| Object-level authorization | `@PreAuthorize("@reportPolicy.canRead(authentication, #id)")` | When the method's policy evaluates the subject and resource |

An endpoint may allow everyone at the HTTP layer via `permitAll()`, yet the underlying service still carries `@PreAuthorize` and can deny the call. Conversely, a method is not protected merely because another controller's URL is marked `authenticated()`.

**Key point:** Authorization annotations are not Java instructions checked automatically by the JVM. They are **metadata** used by Spring Security to configure call interception. If that mechanism is inactive or the call bypasses it, the method body can run normally.

## 3. Which Components Does `@EnableMethodSecurity` Activate?

In Spring Security 6, the standard approach is to place `@EnableMethodSecurity` on a configuration class loaded by Spring:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

You can also place `@EnableMethodSecurity` on the `@SpringBootApplication` class, since it is itself a Spring configuration class.

Here is an easily overlooked point:

> **Simply adding `spring-boot-starter-security` does not automatically enable method security.** You must explicitly activate it with `@EnableMethodSecurity` (or equivalent configuration).

When enabled, Spring Security registers advisor/interceptor infrastructure for the relevant annotations. For `@PreAuthorize`, an `AuthorizationManager`-based interceptor makes decisions before the invocation. For `@PostAuthorize`, the check runs after the method returns. In the common proxy mode, Spring AOP creates/applies proxies to eligible Spring beans so calls route through these interceptors.

Overview:

~~~text
ApplicationContext loads @EnableMethodSecurity
    |
    v
Registers Method Security advisors/interceptors
    |
    v
Spring creates protected beans and appropriate proxies
    |
    v
Caller -> Spring bean proxy -> checks @PreAuthorize
                                   |
                         +---------+---------+
                         |                   |
                     GRANTED               DENIED
                         |                   |
                         v                   v
                  Execute method     AccessDeniedException
~~~

Not every Java call to an annotated method goes through this check. **The proxy/advice is the decisive boundary.**

### Annotation Family Defaults

Important flags on `@EnableMethodSecurity`:

| Attribute | Default | Affected annotations |
| --- | --- | --- |
| `prePostEnabled` | `true` | `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` |
| `securedEnabled` | `false` | `@Secured` |
| `jsr250Enabled` | `false` | `@RolesAllowed`, `@PermitAll`, `@DenyAll` from Jakarta annotations |

Therefore:

~~~java
@EnableMethodSecurity
~~~

is sufficient for using `@PreAuthorize`/`@PostAuthorize` in standard setups, whereas if you want `@Secured` or `@RolesAllowed`, enable them explicitly:

~~~java
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

There is no need to enable all annotation families if a project standardizes on a single family. Enabling extra annotation families only makes sense when actually using them, since overlapping policies can become hard to reason about.

## 4. Necessary Conditions for Annotations to **Actually** Take Effect

Treat this as a chain of conditions that must all be satisfied.

### Condition 1: Configuration Is Loaded into the Right ApplicationContext

`@EnableMethodSecurity` must reside on a configuration class scanned or imported into the context containing the service to protect. Creating a config file outside `@ComponentScan` without `@Import`/registration has no effect simply because the class exists in source.

With Spring Boot, place the configuration in the root package or a scanned subpackage, or import it explicitly. Never assume a configuration in another module automatically takes effect inside a test slice or a new ApplicationContext.

### Condition 2: The Object Is Spring-Managed

Correct example:

~~~java
@Service
public class ReportService {
    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "ok";
    }
}
~~~

When the application obtains `ReportService` from the Spring container (dependency injection, `ApplicationContext.getBean(...)`), the container has the opportunity to create a proxy/interceptor to protect it.

Example bypassing the container:

~~~java
// Wrong example if you expect Spring AOP to protect this call:
ReportService service = new ReportService();
service.readReport();
~~~

An object instantiated directly with `new` is not a Spring-managed proxy. The annotation still exists in bytecode, but **there is no method-security interceptor** standing in front of that call.

### Condition 3: The Call Passes Through the Proxy/Advice

In default proxy mode, calls must travel from the caller through a reference that is **a bean supplied by Spring**, without bypassing the proxy.

~~~text
Controller / Other Service
       |
       v
ReportService bean proxy
       |
       v
@PreAuthorize interceptor
       |
       v
ReportService target method
~~~

If the bean uses a JDK dynamic proxy, protected methods must match the proxied interface. If using a class-based proxy, Java inheritance/overriding constraints apply: `final` classes cannot be subclassed; `final` methods cannot be overridden. `private` methods cannot be overridden to weave advice in the usual class-proxy way. Do not rely on annotations on such methods and conclude they are "already protected."

Spring Framework 6 supports intercepting certain non-public methods with class-based proxies in applicable situations, but **the most verifiable design** for this lesson is protecting public methods on Spring-managed services called through proxies. Do not generalize that all non-public methods are always intercepted or always skipped across all proxy modes.

### Condition 4: An Appropriate Authentication Context Exists at Check Time

`@PreAuthorize("hasAuthority('report:read')")` needs access to the active `Authentication` and `GrantedAuthority` values. The system may hold a valid identity that lacks the authority; in that case, the annotation **worked correctly** by denying access.

When unauthenticated, the context may be empty or hold anonymous authentication depending on configuration. Depending on the call path and exception translation, the outcome is a method-level denial/error or an appropriate HTTP response. Do not view every `403` as proof that "the annotation isn't working."

**Never fabricate an authenticated token from client data to bypass security in production code.** In tests, `@WithMockUser` creates a simulated security context legitimately because it is a controlled test fixture.

### Condition 5: Expressions and Policy Data Sources Are Meaningful

Example:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void closePeriod() {
    // ...
}
~~~

By default, `hasRole("ADMIN")` checks for the `ROLE_ADMIN` authority. If the system only grants `ADMIN` without the matching prefix, the annotation may deny even though the user is logged in. Similarly, `hasAuthority("report:read")` requires an exact authority string match.

Expressions can access method parameters:

~~~java
@PreAuthorize("@reportPolicy.canRead(authentication, #reportId)")
public Report find(long reportId) {
    // ...
}
~~~

This is an illustrative snippet requiring the `reportPolicy` bean, `Report` type, and corresponding implementation. The name `#reportId` must be resolvable via parameter name metadata or a compatible parameter naming mechanism. In Java, compiling with `-parameters` preserves parameter names for Spring; or specify the name explicitly with `@P("reportId")` when needed. If an expression references the wrong name, SpEL errors or unexpected decisions can occur.

### Condition 6: No Call Path Bypasses the Checking Infrastructure

Method security only checks calls that are actually intercepted. Another access path might call the target directly, or a similar operation might live on an unannotated method. Therefore, test the **public entry points of the service** and real invocation paths rather than merely seeing the annotation in the source file.

## 5. Runnable Example: Spring Boot + Spring Security + JUnit

The goal is verification through **actual behavior**, not just checking that code contains `@PreAuthorize`.

The sample uses Java 17, Spring Boot 3.3.5 (Spring Security 6.x), Gradle 8.x, and Spring Security Test. It does not need a web server because tests call the Spring bean directly. This cleanly isolates the question: does method security block the service method?

### 5.1. Project Structure

~~~text
method-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/methodsecurity/
    │   ├── MethodSecurityApplication.java
    │   └── ReportService.java
    └── test/java/demo/methodsecurity/
        └── ReportServiceSecurityTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'method-security-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-security` provides Spring Security infrastructure; `spring-security-test` brings test annotations such as `@WithMockUser`; `spring-boot-starter-test` brings JUnit 5 and Spring Boot Test integration.

### 5.2. Enabling Method Security

File `src/main/java/demo/methodsecurity/MethodSecurityApplication.java`:

~~~java
package demo.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class MethodSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityApplication.class, args);
    }
}
~~~

Here the `@SpringBootApplication` class is loaded when the Spring app/test initializes the context, so `@EnableMethodSecurity` sits in an effective location. No separate `@Configuration` class is needed in this example.

### 5.3. Protected Methods in a Spring Bean

File `src/main/java/demo/methodsecurity/ReportService.java`:

~~~java
package demo.methodsecurity;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "report:ok";
    }

    @PreAuthorize("hasAuthority('report:write')")
    public String publishReport() {
        return "report:published";
    }
}
~~~

Both methods are public and the class is non-final, compatible with basic proxying. The policy distinguishes `report:read` and `report:write`; a user with read permission **does not automatically** gain publish permission.

### 5.4. Testing from Outside the Bean

File `src/test/java/demo/methodsecurity/ReportServiceSecurityTest.java`:

~~~java
package demo.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ReportServiceSecurityTest {

    @Autowired
    ReportService reportService;

    @Test
    void securityAdviceIsAppliedToSpringBean() {
        assertTrue(AopUtils.isAopProxy(reportService));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void aReaderCanRead() {
        assertEquals("report:ok", reportService.readReport());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void aReaderCannotPublish() {
        assertThrows(AccessDeniedException.class,
            () -> reportService.publishReport());
    }

    @Test
    @WithMockUser(username = "bob",
        authorities = {"report:read", "report:write"})
    void aPublisherCanPublish() {
        assertEquals("report:published", reportService.publishReport());
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotRead() {
        assertThrows(AccessDeniedException.class,
            () -> reportService.readReport());
    }
}
~~~

Run from the project root with JDK 17+ and Gradle 8.x:

~~~bash
gradle test
~~~

Or run only this lesson's test:

~~~bash
gradle test --tests demo.methodsecurity.ReportServiceSecurityTest
~~~

**Expected outcome:** the five tests above pass. The first verifies the injected instance is an AOP proxy; the subsequent tests verify method calls are allowed/denied according to authorities. `"report:ok"` and `"report:published"` are deterministic return values from the code, asserted directly without predicting full Gradle or startup logs.

**These tests are code for you to run in the sample project; "passing" is the design expectation, not an execution result performed inside this article.** In an environment lacking JDK, Gradle, or network access to download dependencies, prepare the environment before running.

### 5.5. Why Are These Tests Valuable?

- `@WithMockUser` populates the security context in the test environment; it does not perform real login/password validation. Thus, the tests focus strictly on **authorization**, without conflating it with authentication.
- `@Autowired` receives the bean from Spring, so tests pass through the proxy; calling `new ReportService()` would bypass this condition.
- An **insufficient-permission** case is verified via an exception instead of testing only success paths. If method security is accidentally disabled, `aReaderCannotPublish` will likely fail because the method is no longer blocked.
- `AopUtils.isAopProxy` is a helpful signal about the proxy mechanism, but a proxy could be created for another reason (transactions, caching, etc.). You must **test denial behavior** to prove method security is active, not just check for a proxy.

## 6. Classic Bug: Self-Invocation Bypasses the Proxy

The following example illustrates a risky structure:

~~~java
@Service
public class UnsafeReportWorkflow {

    public String runWorkflow() {
        // Internal call on "this", does NOT go through the Spring AOP proxy.
        return publish();
    }

    @PreAuthorize("hasAuthority('report:write')")
    public String publish() {
        return "published";
    }
}
~~~

If an external caller obtains `UnsafeReportWorkflow` via Spring and calls `runWorkflow()`, the initial call passes through the proxy. However, `runWorkflow()` **has no** `@PreAuthorize`; when it calls `this.publish()`, that is an internal call on the target object and does not pass through the proxy. In standard proxy mode, the annotation on `publish()` **does not protect this internal call path**.

Diagram:

~~~text
Caller
  |
  v
Spring proxy -> runWorkflow()  (no rule)
                      |
                      v
                   this.publish()
                      |
                      +-- bypasses proxy / @PreAuthorize does not run
~~~

### Clean Fix: Extract the Protected Method into a Separate Bean

~~~java
@Service
public class PublishCommandService {

    @PreAuthorize("hasAuthority('report:write')")
    public String publish() {
        return "published";
    }
}
~~~

~~~java
@Service
public class ReportWorkflowService {

    private final PublishCommandService commands;

    public ReportWorkflowService(PublishCommandService commands) {
        this.commands = commands;
    }

    public String runWorkflow() {
        return commands.publish();
    }
}
~~~

The two snippets above are **illustrative integration code**, requiring `@Service` imports and placing public classes in their respective files. Spring injects `PublishCommandService` via bean reference so `commands.publish()` travels through the protected service's proxy.

If the entire workflow must require publish permission, you can also place `@PreAuthorize` directly on the **public entry method** `runWorkflow()` to guard the boundary callers actually invoke. Explicit design is better than relying on an internal call happening to be intercepted.

**Do not treat self-invocation as an annotation syntax error.** The annotation compiles cleanly and the application starts normally, yet the actual execution path bypasses interception.

## 7. Proxy Mode, Visibility, Final, and Call Site

These scenarios must be analyzed by proxy type and call site:

| Case | Risk | How to verify or handle |
| --- | --- | --- |
| Instantiating service with `new` | Does not use Spring bean/proxy | Use dependency injection / `ApplicationContext` |
| Method calling another method in the same object | Self-invocation bypasses advice in proxy mode | Extract bean or guard entry method |
| Annotated `private` method | AOP proxies do not intercept private self-calls in the usual way | Place rules on interceptable public methods |
| `final` method/class with class-based proxy | Cannot override/subclass to apply advice | Design beans/methods non-final or pick an appropriate proxy strategy |
| Interface-based proxy | Only properly exposed interface calls pass through JDK proxy | Use appropriate interface contracts, test injection/dispatch |
| Bean outside component scan | Bean/proxy missing from expected context | Fix `@ComponentScan`/`@Import`/config |
| Annotated method where caller holds target object directly | Bypasses advice | Use the Spring-managed reference |
| Service run in an isolated test context | `@EnableMethodSecurity` might be missing in that context | Use `@SpringBootTest` or import appropriate method security config |

**AspectJ weaving is a different mechanism** from Spring AOP proxies and can address certain self-invocation cases if separately configured. This is not the default for `@EnableMethodSecurity`, and switching to weaving requires deliberate intent, dependencies, and testing; do not switch merely because an annotation is being skipped without analyzing call paths.

### Should You Call Your Own Proxy?

Some code attempts to look up its proxy from `ApplicationContext` or self-inject to avoid self-invocation. That can work under specific conditions, but creates circular dependencies, harms readability, and complicates testing. For new code, prefer extracting responsibilities into another bean or placing policies on public entry points. If a project has a legacy design hard to split, test the real call path rather than trusting proxy workarounds.

## 8. Configuring Enabling and Disabling of an Annotation Family

Example using `@PreAuthorize` without `@Secured`:

~~~java
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

`@PreAuthorize` is enabled by default. In some legacy systems, you may see:

~~~java
@Secured("ROLE_ADMIN")
public void rotateKeys() {
    // ...
}
~~~

For `@Secured` to take effect, you need:

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

Similarly with Jakarta JSR-250:

~~~java
@RolesAllowed("ADMIN")
public void rotateKeys() {
    // ...
}
~~~

requires:

~~~java
@EnableMethodSecurity(jsr250Enabled = true)
~~~

`@Secured` belongs to `org.springframework.security.access.annotation.Secured`; `@RolesAllowed` belongs to `jakarta.annotation.security.RolesAllowed`. This example differentiates configurations and does not form a standalone app. Role and authority names in the system must align with how Spring Security matches them.

You can also use:

~~~java
@EnableMethodSecurity(prePostEnabled = false)
~~~

when intentionally disabling the default pre/post group configuration, but then **do not expect** `@PreAuthorize`/`@PostAuthorize` to work unless an alternative infrastructure is registered. This is a real-world reason annotations are "present in code but never executed."

If the same method is covered by multiple authorization rules/advices, all applicable checks must pass; do not infer that writing `@PermitAll` from one annotation family automatically overrides rules from another family or from HTTP security.

## 9. Reading `@PreAuthorize` Expressions Accurately

### 9.1. Checking Authentication

~~~java
@PreAuthorize("isAuthenticated()")
public String viewMyDashboard() {
    return "dashboard";
}
~~~

Requires a principal recognized by Spring Security as authenticated. Anonymous authentication has its own semantics, so do not check `authentication.isAuthenticated()` manually in code assuming it equals the security expression.

### 9.2. Checking Roles

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void cleanAuditLogs() {
    // ...
}
~~~

By default convention, `hasRole('ADMIN')` checks for authority `ROLE_ADMIN`. `hasAuthority('ADMIN')` checks for the exact string `ADMIN`. If a user has authority `ROLE_EDITOR`, a method requiring `ROLE_ADMIN` must still be denied despite being logged in.

### 9.3. Checking Specific Authorities

~~~java
@PreAuthorize("hasAuthority('report:read')")
public String readReport() {
    return "report:ok";
}
~~~

The `report:read` authority comes from a trusted authentication/authority-mapping mechanism, not an arbitrary field sent in a request body by the client. Having `report:write` **does not necessarily** imply `report:read`, unless the system grants both or a policy defines a different mapping.

### 9.4. Checking Parameters and Object-Level Policy

~~~java
@PreAuthorize("@reportPolicy.canRead(authentication, #documentId)")
public Document loadDocument(long documentId) {
    return documentRepository.findById(documentId).orElseThrow();
}
~~~

This snippet is illustrative only: `Document`, `documentRepository`, and bean `documentPolicy` (`reportPolicy` in the expression) must be defined by the application. Policies must rely on server data to check owner/tenant; never trust client-supplied `ownerId` or `tenantId`. If the policy bean is missing or the parameter name cannot be resolved, the expression may throw an error rather than "silently granting access."

Method security only helps you **make decisions in the right place**; it does not guarantee your business rules or object access checks are complete.

## 10. Differences Between `@PreAuthorize` and `@PostAuthorize`

- `@PreAuthorize` runs before the method body, suitable for blocking unauthorized actions.
- `@PostAuthorize` evaluates after the method returns and can inspect the result via `returnObject`.
- `@PreFilter`/`@PostFilter` can filter collection arguments/return values when used with supported types and semantics.

Illustrative example:

~~~java
@PreAuthorize("hasAuthority('invoice:read')")
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public Invoice getInvoice(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

`Invoice`, field `ownerUsername`, and `repository` belong to the application; this is not a standalone runnable example. The first condition checks authority. The second allows returning the invoice only if the user is the owner.

**Do not use `@PostAuthorize` to "protect" operations that already caused side effects.** If the method has transferred funds, deleted data, or called an external API before being denied after returning, the action may already have happened. For state-mutating operations, check permissions **before** execution, including object/tenant access.

Similarly, reading data and then denying in `@PostAuthorize` can waste resources or trigger side effects (logging, caching). Choose policy placement based on business semantics, not convenience of a single annotation.

## 11. Annotations at Class and Method Level

Spring Security can pick up security metadata at the class or method level depending on placement and annotation type:

~~~java
@Service
@PreAuthorize("hasAuthority('finance:read')")
public class FinanceService {

    public String summary() {
        return "summary";
    }

    @PreAuthorize("hasAuthority('finance:write')")
    public String updateBudget() {
        return "updated";
    }
}
~~~

Class-level annotations create a shared policy for related methods; method-level annotations can specialize/replace rules of the same family according to Spring Security's metadata resolution rules. Do not blindly assume two expressions of the same kind combine with AND or OR without understanding override rules and interceptor ordering.

Avoid conflicting security annotations inherited from multiple interfaces or superclasses. In some cases Spring throws an error due to ambiguous metadata and requires explicit annotations on the implementation. For critical APIs, write tests at the actual call site to verify the final applied rule.

## 12. Servlet vs. WebFlux: Choosing the Right Mechanism

The main body of this lesson uses imperative method security in Servlet/Spring MVC applications or ordinary services:

~~~java
@Configuration
@EnableMethodSecurity
class ServletMethodSecurityConfig {
}
~~~

For **reactive method security** in WebFlux, use the dedicated configuration:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {
}
~~~

The imports in the reactive example are `org.springframework.context.annotation.Configuration` and `org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity`.

Reactive Spring Security uses the Reactor Context for `Authentication` via `ReactiveSecurityContextHolder`. When writing reactive services, return publishers (`Mono`/`Flux`) and let security advice interact with the publisher reactively, for example:

~~~java
// Illustrates a method belonging to a Spring-managed reactive service.
@PreAuthorize("hasAuthority('report:read')")
public Mono<String> readReport() {
    return Mono.just("report:ok");
}
~~~

The snippet above is not a standalone class. It requires Reactor/WebFlux dependencies and matching reactive configuration. Avoid ThreadLocal `SecurityContextHolder` or `block()` as the default way to check security in WebFlux. Do not assume Servlet's `@EnableMethodSecurity` substitutes for `@EnableReactiveMethodSecurity` when security context lives in Reactor Context.

If an application mixes blocking and non-blocking layers, context transfer boundaries must be explicitly designed and tested; never treat scheduler switches as automatically propagating `ThreadLocal` across APIs outside Reactor.

## 13. When an HTTP Test Returns 401/403, Is Method Security Working?

**You cannot conclude that from HTTP status alone.** A request could be blocked before reaching the method (at the filter chain, CSRF, CORS, request authorization) or blocked at the method interceptor.

Servlet example:

~~~text
HTTP request
   |
   v
SecurityFilterChain / request authorization
   |
   +-- denied here -> controller/service may not run
   |
   v
Controller
   |
   v
Spring service proxy
   |
   +-- @PreAuthorize denies -> AccessDeniedException
   |
   v
Service target method
~~~

When unauthenticated, HTTP Basic apps typically return `401` via the entry point; authenticated users lacking permissions typically receive `403` via exception translation. However, CSRF can also return `403`, custom handlers or form login can redirect, and non-HTTP method calls throw exceptions rather than producing HTTP statuses.

**The most reliable test for method security** is invoking the bean from the Spring context in tests with `@WithMockUser` (with and without permissions) and asserting the method body executes only when authorized. HTTP tests remain necessary to verify the entire request flow, but a test checking only a `403` response does not reveal which filter denied it.

### Distinguishing Tests with Annotations When Method Security Is Off

If you delete `@EnableMethodSecurity` from the sample project:

- `ReportService` source still compiles and retains `@PreAuthorize`.
- Calling `reportService.publishReport()` can execute directly because no method-security interceptor is registered.
- Test `aReaderCannotPublish` should fail (no `AccessDeniedException` thrown), exposing the missing infrastructure.

This is a **thought experiment to understand the cause**, not an instruction to remove configuration in your retained app.

## 14. Troubleshooting by Symptom

| Symptom | Likely cause | Specific check |
| --- | --- | --- |
| `@PreAuthorize` blocks nobody | Missing `@EnableMethodSecurity` or config not loaded | Check config classes/contexts in app and tests |
| Direct call via `new` still runs | Not using bean/proxy | Inject `@Service` via constructor or `@Autowired` |
| Controller call is blocked, but call from another method in same class isn't | Self-invocation | Trace `this.method()`, split bean, or guard entry |
| `@Secured` does not block | `securedEnabled` defaults to `false` | Enable `@EnableMethodSecurity(securedEnabled = true)` |
| `@RolesAllowed` does not block | `jsr250Enabled` not enabled | Enable `jsr250Enabled = true` |
| Admin denied despite logging in | Wrong authority, e.g. `ADMIN` vs `ROLE_ADMIN` | Inspect `Authentication.getAuthorities()` and rules |
| Expression `#id` behaves unexpectedly | Missing parameter name metadata or invalid SpEL | Build with `-parameters` or use `@P("id")` |
| Final/private method unprotected | Proxy/visibility limitations | Move policy to interceptable public entry method |
| `@SpringBootTest` behaves differently from web runtime | Test context missing config or different security data | Inspect test annotations/imports, use integration tests |
| Proxy exists but no denial happens | Proxy serves another purpose or security advice not applied | Test missing authority with `assertThrows`, inspect advisors/interceptors |
| WebFlux reads wrong principal or loses identity | ThreadLocal/Servlet assumptions in reactive pipeline | Use reactive method security + Reactor Context |
| HTTP 403 despite correct method authority | Request filter/CSRF/authorization blocked earlier | Trace filter chain and compare security rules |

When debugging, **never log credentials, raw tokens, or the entire `SecurityContext`**. You may record minimal audit logs containing principal ID, action, resource, and decision at appropriate boundaries without exposing sensitive data.

## 15. Checklist Before Considering an Annotation "Protecting"

1. **Right annotation:** Do you need `@PreAuthorize`, `@PostAuthorize`, `@Secured`, or `@RolesAllowed`? Is that family enabled?
2. **Right context:** Is `@EnableMethodSecurity` in a Spring configuration actually loaded?
3. **Right bean:** Is the service created by the Spring container? Do callers get the bean/proxy rather than using `new`?
4. **Right call path:** Does the call go through the proxy without self-invocation or final/private method restrictions blocking advice?
5. **Right principal:** What is the caller's Authentication? Could it be anonymous/remember-me? Do granted authorities match the rule string?
6. **Right policy:** Does the SpEL expression have valid parameters, beans, and resource data?
7. **Right stack:** Are you using imperative/Servlet `@EnableMethodSecurity` or reactive/WebFlux `@EnableReactiveMethodSecurity`?
8. **Negative tests exist:** Are unauthorized callers actually denied **before** business logic runs?

These questions should be answered via tests/instrumentation at the **real call path**. That is far more trustworthy than merely seeing the annotation in your IDE.

## 16. Self-Check Exercises

**Exercise 1 — missing configuration.** A Spring Boot application includes `spring-boot-starter-security` and a service with `@PreAuthorize("hasRole('ADMIN')")`, but lacks `@EnableMethodSecurity`. Can you conclude the method is protected?

**Answer:** No. Spring Boot Starter Security does not automatically enable method-level authorization. You must add the corresponding configuration to the ApplicationContext, then test calls through the bean.

**Exercise 2 — self-invocation.** Class `OrderService` has `placeOrder()` calling `this.approveOrder()`, where `approveOrder()` has `@PreAuthorize("hasAuthority('order:approve')")`. Why can an unauthorized user still enter the method body?

**Answer:** In Spring AOP proxy mode, internal calls via `this` bypass the proxy/advice. Extract `approveOrder` into another Spring bean or place the rule on an appropriate entry method; verify with tests.

**Exercise 3 — role and authority.** A user has authority `ROLE_ADMIN`. What is the difference between `hasRole('ADMIN')` and `hasAuthority('ADMIN')`?

**Answer:** With the default role prefix, `hasRole('ADMIN')` checks `ROLE_ADMIN`, whereas `hasAuthority('ADMIN')` checks the exact string `ADMIN`. They can produce different outcomes.

**Exercise 4 — proxy.** Why is `AopUtils.isAopProxy(service) == true` not enough to prove `@PreAuthorize` is active?

**Answer:** The proxy might have been created for transactions, caching, or another advice; you must test a caller/request lacking authority and verify the method is denied at the right time.

**Exercise 5 — post-execution check.** Why shouldn't `@PostAuthorize` alone be used to protect a money transfer operation?

**Answer:** Because checking after the method completes can come too late; side effects have already occurred. Policies and resource permissions must be checked before execution.

**Exercise 6 — WebFlux.** An application returns `Mono<String>` and uses Reactor Context for the principal. Which annotation enables method security appropriately?

**Answer:** Use `@EnableReactiveMethodSecurity` and reactive method security infrastructure; avoid reading identity via Servlet's default ThreadLocal approach.

## 17. Takeaways and References

**`@EnableMethodSecurity` enables the method authorization infrastructure; annotations only truly protect when Spring loads the configuration, the method belongs to a Spring bean, calls are intercepted, and authorization expressions are evaluated against the proper authentication context.** In proxy mode, carefully check for self-invocation and non-interceptable methods. Always test both authorized and unauthorized cases.

Official Spring Security documentation:

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security — EnableMethodSecurity API](https://docs.spring.io/spring-security/site/docs/6.2.6/api/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html)
- [Spring Framework — Understanding AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
