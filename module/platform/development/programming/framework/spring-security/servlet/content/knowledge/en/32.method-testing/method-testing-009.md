# Testing Proxy Invocation vs. Self-Invocation Within the Same Object

## 1. Problem: One Method, Two Different Call Paths

In a **Spring Security Servlet** application using **method security**, you might write a method:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public String readReport() {
    return "REPORT-42";
}
~~~

A call **from another bean through the Spring proxy** normally triggers the security advice created by **`@PreAuthorize`**. A caller lacking the **`report:read`** authority is denied before the method body runs.

However, if **another method on the same object** calls **`this.readReport()`**, that internal call goes directly to the target object instead of re-entering the Spring proxy. Under **proxy-based method security**, the advice on **`readReport()`** may not execute. This is the **self-invocation** trap.

~~~text
Path A — through the Spring proxy:

Controller / Facade
       │
       ▼
Spring AOP proxy of ReportService
       │
       ├── @PreAuthorize("hasAuthority('report:read')")
       │     ├── allowed → readReport()
       │     └── missing permission → AccessDeniedException
       ▼
Target ReportService.readReport()


Path B — internal call:

Controller
       │
       ▼
Spring AOP proxy of ReportService
       │  (outerMethod has no advice)
       ▼
Target ReportService.outerMethod()
       │
       └── this.readReport()
               │
               └── called directly on target, does not re-enter proxy
                   ⇒ @PreAuthorize on readReport() is not evaluated
~~~

The issue is not "Spring Security randomly ignores `@PreAuthorize`". **The call path** determines whether method interception occurs.

### Learning Outcomes

After this article, you will be able to:

1. Distinguish **proxy invocation** from **self-invocation** in Spring AOP/method security.
2. Configure **`@EnableMethodSecurity`**, **`@PreAuthorize`**, and a sound security boundary.
3. Write **unit/integration tests with a Spring context** verifying method security for authorized, under-privileged, and internal-call principals.
4. Use **`MockMvc`** to verify the HTTP consequences of each call path; clearly understand **401** and **403**.
5. Spot **false positives** caused by manually instantiating services with **`new`**, mocks stripping proxies, or testing only one controller path.
6. Refactor into **separate beans** or protect the **public entry method**, never relying on a `this()` call whose advice is bypassed.

Examples use **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC (Servlet)**. Do not copy the `SecurityFilterChain` configuration directly to a WebFlux `SecurityWebFilterChain`.

## 2. Proxy-Based Method Security Mechanism

### 2.1. Spring Method Security Is Not Just an Annotation

When **`@EnableMethodSecurity`** is enabled in a Spring application, the framework creates interceptors/advisors for supported annotations such as **`@PreAuthorize`** and **`@PostAuthorize`**. In standard proxy mode:

- The target bean is accessed through a **Spring AOP proxy**.
- Calls can be wrapped by interceptors checking **`Authentication`** and making authorization decisions.
- **`@PreAuthorize`** is evaluated **before** the method body.
- On denial, the advice throws **`AccessDeniedException`** (or the matching security error), and the method body does not execute.
- **`@PostAuthorize`** checks after the method body runs; it can prevent returning the result to the caller, yet **cannot undo side effects** that already happened. It suffers from the same proxy-boundary limitation.

Without **`@EnableMethodSecurity`**, placing **`@PreAuthorize`** on a method does not ensure interceptors run. In Spring Security 6, **`@EnableMethodSecurity`** is the modern configuration approach; do not confuse it with the legacy **`@EnableGlobalMethodSecurity`**.

A plain Java call **does not magically gain** method-security advice simply because the class sits in a Spring app. To trigger interception, callers must obtain the **Spring-managed bean** and go through the right **proxy**.

### 2.2. JDK Dynamic Proxies and Class-Based Proxies

Spring AOP may use:

- **JDK dynamic proxy**: typically used when proxying via interfaces. Callers should interact through the appropriate interface.
- **Class-based proxy (CGLIB)**: generates a proxy subclass of the target class; commonly needed for beans without interfaces.

Either way, **self-invocation** still bypasses interceptors: once execution is inside the target object, **`this.someMethod()`** does not dispatch a new request through the proxy.

Certain methods/classes cannot be proxied normally. For example, **`final` methods** cannot be overridden/intercepted by subclass-based proxies; **`private` methods** are not public proxy entry points. Never place annotations on private/final methods assuming method security protects them. Behavior on non-public methods depends on proxy type and Spring version; test against your actual configuration.

**Proxy configuration does not turn self-invocation into an intercepted invocation.** Switching to class-based proxies instead of JDK proxies does not change the nature of **`this.readReport()`**.

### 2.3. Permissions and Call Paths: Comparison Table

Suppose **`readReport()`** requires authority **`report:read`**, while **`readFromInside()`** has no annotation:

| Caller / Call Path | Principal Has `report:read`? | Result |
| --- | --- | --- |
| Another bean calls **`reportService.readReport()`** via proxy | Yes | Enters method, receives **`REPORT-42`** |
| Another bean calls **`reportService.readReport()`** via proxy | No | **`AccessDeniedException`**; method body does not run |
| Calls **`reportService.readFromInside()`** via proxy which calls **`this.readReport()`** | Yes | Receives **`REPORT-42`** |
| Calls **`reportService.readFromInside()`** via proxy which calls **`this.readReport()`** | No | **May still receive `REPORT-42`**: annotation on inner method is not intercepted |
| Caller uses **`new ReportService()`** instead of Spring bean | No | No Spring proxy; annotation on plain class does not block |
| Caller uses a bean replaced by a plain mock | Any | Mock likely lacks the real interceptor; outcome does not prove method security |

The fourth row is a security flaw requiring a **negative test**. A test proving only that an authorized user can read the report is insufficient.

## 3. Spring Boot Example with Both Proxy and Self-Invocation Paths

The example implements **two GET HTTP endpoints strictly for a demo environment**. Both require an authenticated user at the HTTP layer; only **`/demo/proxy`** passes through the annotation requiring authority **`report:read`**. **`/demo/self`** intentionally models the anti-pattern so tests observe the bypassed protection. Never ship this unguarded endpoint to production.

### 3.1. Dependencies and Structure

Spring Boot 3.x project using Java 17+ and Gradle wrapper. In **`build.gradle`**, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Illustrative Java files:

~~~text
src/
├── main/java/com/example/methodproxy/
│   ├── MethodProxyApplication.java
│   ├── ReportService.java
│   ├── ReportFacade.java
│   └── DemoController.java
└── test/java/com/example/methodproxy/
    └── ProxyBoundaryTest.java
~~~

Create package **`com.example.methodproxy`** matching the sources. **Spring Boot `starter-security`** brings in the necessary Spring Security libraries and Spring AOP support for method-security proxies.

### 3.2. Application and Security Configuration

File **`src/main/java/com/example/methodproxy/MethodProxyApplication.java`**:

~~~java
package com.example.methodproxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
@EnableMethodSecurity
public class MethodProxyApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodProxyApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-demo-password"))
                        .authorities("report:read")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-demo-password"))
                        .authorities("report:edit")
                        .build());
    }
}
~~~

Explanation:

- **`@EnableMethodSecurity`** enables annotation-based method authorization; this example uses **`@PreAuthorize`**.
- **`SecurityFilterChain`** sets a minimum **`authenticated()`** requirement on all HTTP routes. This is **web authorization**, separate from method authorization inside the service.
- **`alice`** holds **`report:read`** and is permitted to read the report when calling through the proxy.
- **`bob`** holds only **`report:edit`**, so he is logged in yet **not permitted to read the report** per the method policy.
- **HTTP Basic** and the two demo accounts are strictly for reproducing the test. Never hardcode demo passwords in production, and never send Basic credentials over plain HTTP without TLS outside local environments.

Key point: **the web chain `.authenticated()`** lets both alice and bob reach the controller; fine-grained report authorization is expected to happen at the method-security proxy.

### 3.3. Service with One Protected Method and One Self-Invocation

File **`src/main/java/com/example/methodproxy/ReportService.java`**:

~~~java
package com.example.methodproxy;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "REPORT-42";
    }

    public String readFromInside() {
        // Intentional anti-pattern: this is the target object, NOT the proxy.
        return this.readReport();
    }
}
~~~

**`readReport()`** is a public method protected by Spring advice when invoked **through the proxy**. **`readFromInside()`** is also public so the controller can call it on the bean proxy, yet it **lacks** an annotation requiring `report:read`. Once execution reaches **`this.readReport()`**, the interceptor on `readReport()` is not invoked.

This is an **intentionally flawed** design for writing a regression test proving the risk. A real application should never leave an unguarded entry point with a path to sensitive data like this.

### 3.4. Facade Calling Another Bean to Go Through the Proxy

File **`src/main/java/com/example/methodproxy/ReportFacade.java`**:

~~~java
package com.example.methodproxy;

import org.springframework.stereotype.Service;

@Service
public class ReportFacade {

    private final ReportService reportService;

    public ReportFacade(ReportService reportService) {
        this.reportService = reportService;
    }

    public String readThroughProxy() {
        // Another bean calls public method on a Spring-injected bean.
        return reportService.readReport();
    }
}
~~~

**`ReportFacade`** receives a **`ReportService`** bean via constructor injection. In standard method-security setups, the injected reference is the **proxy** or advised delegate managed by the framework. When the facade calls **`reportService.readReport()`**, the policy is evaluated.

Refactoring into **two separate beans** is the most common fix for self-invocation because the interception boundary is explicit, avoiding `ThreadLocal` proxy lookups or self-injection.

### 3.5. Controller to Compare Over HTTP

File **`src/main/java/com/example/methodproxy/DemoController.java`**:

~~~java
package com.example.methodproxy;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final ReportService reportService;
    private final ReportFacade reportFacade;

    public DemoController(
            ReportService reportService,
            ReportFacade reportFacade) {
        this.reportService = reportService;
        this.reportFacade = reportFacade;
    }

    @GetMapping("/demo/proxy")
    public String throughProxy() {
        return reportFacade.readThroughProxy();
    }

    @GetMapping("/demo/self")
    public String throughSelfInvocation() {
        // Used to demonstrate the bug, DO NOT keep this endpoint in production.
        return reportService.readFromInside();
    }
}
~~~

**The controller does not attach `report:read` to both endpoints**, because the demo aims to expose the difference between proxy invocation and self-invocation. In production designs, sensitive policies should sit on an unbypassable entry boundary and also be enforced at the service.

## 4. Expected Run Output and Per-Request Explanation

Run the application:

~~~bash
./gradlew bootRun
~~~

With HTTP Basic locally, try **`alice`**:

~~~bash
curl -i -u alice:alice-demo-password \
  'http://localhost:8080/demo/proxy'
~~~

Expected result:

~~~http
HTTP/1.1 200

REPORT-42
~~~

Actual HTTP headers (`Content-Type`, `Content-Length`, caching, security headers) may vary, while **200** and body **`REPORT-42`** are the expected business outcome.

Try **`bob`** through the proxy:

~~~bash
curl -i -u bob:bob-demo-password \
  'http://localhost:8080/demo/proxy'
~~~

Expected result is **HTTP 403 Forbidden** because bob is authenticated yet lacks **`report:read`**. The response body may be a Spring Boot-rendered error message depending on config; do not assume a fixed error body.

Next, try **`bob`** via the self-invocation path:

~~~bash
curl -i -u bob:bob-demo-password \
  'http://localhost:8080/demo/self'
~~~

In the demo, this is expected to return **HTTP 200** and **`REPORT-42`**. This is direct evidence that **putting `@PreAuthorize` only on an inner method is insufficient** when calls can originate from the same target object.

Finally, try with no credentials:

~~~bash
curl -i 'http://localhost:8080/demo/proxy'
~~~

Expect **HTTP 401** because HTTP Basic requires authentication before dispatching to the controller.

### Why Does One Path Return 403 While the Other Returns 200?

Bob did not gain permission to read the document on the second path. Bob **still lacks `report:read`**. The issue is that the second path **never ran the `report:read` check**. Therefore, a test expecting 403 on every access path must be treated as the security standard. The demo test proves the bug exists, not that returning 200 is desired product behavior.

## 5. Integration Test Proving the Proxy Boundary

Write tests using **`@SpringBootTest`** so Spring instantiates real beans and method-security proxies. Use **`@WithMockUser`** from `spring-security-test` to set an `Authentication` with specific authorities for service calls. This tests **authorization/method interception**, not real password verification.

File **`src/test/java/com/example/methodproxy/ProxyBoundaryTest.java`**:

~~~java
package com.example.methodproxy;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ProxyBoundaryTest {

    @Autowired
    ReportService reportService;

    @Autowired
    ReportFacade facade;

    @Autowired
    MockMvc mvc;

    @Test
    void serviceBeanIsProxied() {
        assertThat(AopUtils.isAopProxy(reportService)).isTrue();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void externalCallWithAuthorityPasses() {
        assertThat(reportService.readReport()).isEqualTo("REPORT-42");
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:edit")
    void externalCallWithoutAuthorityIsDenied() {
        assertThatThrownBy(() -> reportService.readReport())
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:edit")
    void callFromAnotherBeanStillUsesProxy() {
        assertThatThrownBy(() -> facade.readThroughProxy())
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:edit")
    void selfInvocationDemonstratesBypass() {
        // Exposes the BUG: entry method has no advice, inner call uses this.
        assertThat(reportService.readFromInside()).isEqualTo("REPORT-42");
    }

    @Test
    void httpProxyRouteRejectsMissingAuthority() throws Exception {
        mvc.perform(get("/demo/proxy")
                        .with(user("bob").authorities(
                                new SimpleGrantedAuthority("report:edit"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void httpProxyRouteAcceptsRequiredAuthority() throws Exception {
        mvc.perform(get("/demo/proxy")
                        .with(user("alice").authorities(
                                new SimpleGrantedAuthority("report:read"))))
                .andExpect(status().isOk())
                .andExpect(content().string("REPORT-42"));
    }

    @Test
    void httpSelfRouteExposesTheBypass() throws Exception {
        // This test exposes the problem, NOT desired production behavior.
        mvc.perform(get("/demo/self")
                        .with(user("bob").authorities(
                                new SimpleGrantedAuthority("report:edit"))))
                .andExpect(status().isOk())
                .andExpect(content().string("REPORT-42"));
    }

    @Test
    void httpRouteWithoutAuthenticationIsUnauthorized() throws Exception {
        mvc.perform(get("/demo/proxy"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Run in the root directory containing the Gradle wrapper:

~~~bash
./gradlew test --tests com.example.methodproxy.ProxyBoundaryTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.methodproxy.ProxyBoundaryTest
~~~

**Expected outcome:** 9 tests pass if the example is placed into a Boot/Security project of matching version with no interfering config. This is a **prediction from the sample code**, not a confirmed runtime output.

### Four Distinct Conclusions from the Test Suite

| Test Group | What It Proves | What It Does Not Prove |
| --- | --- | --- |
| **`AopUtils.isAopProxy(...)`** | Injected service is an AOP proxy | That every specific method has security advice |
| **`@WithMockUser`** calling service | Method-security interceptor can allow/deny based on `Authentication` | That passwords, OAuth2 tokens, sessions, or real HTTP filters work |
| **`MockMvc + user(...)`** | Web security and method security coordinate in simulated HTTP requests | That real Basic credentials are verified by encoders, or external proxies/gateways are right |
| **HTTP via `curl` and real Basic** | Reproduces endpoints and Basic authentication in a running app | Production safety, IAM/IdP, and every other entry point are tested |

**Do not overuse `@WithMockUser`-only tests.** It is particularly helpful for authorization, yet `SecurityContext` is fabricated by the test. For password authentication or OAuth2/JWT, add matching real-authentication tests.

### Purpose of the "Bypass Still Returns 200" Tests

In this lesson, **`selfInvocationDemonstratesBypass`** and **`httpSelfRouteExposesTheBypass`** assert expectations matching the simulated bug. **Never keep bypass-allowing assertions as production acceptance criteria.**

When refactoring, flip them into regression tests requiring under-privileged callers to be **denied** on **every path**; that is the safe acceptance criterion.

## 6. Refactoring to Eliminate Self-Invocation Bypass

### Solution A — Move the Permission-Checked Method to Another Bean (Preferred)

Instead of keeping both inside one bean:

~~~java
@Service
class InsecureReportService {
    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "REPORT-42";
    }

    public String exportReport() {
        return this.readReport(); // advice is bypassed
    }
}
~~~

split the **protected method** and the **orchestrating method** into two beans. Keeping **`ReportService.java`** with its annotation on `readReport()`, **`ReportFacade.java`** already demonstrates the right structure:

~~~java
public String readThroughProxy() {
    return reportService.readReport();
}
~~~

Because **`ReportFacade`** calls the **injected `ReportService` bean**, the call goes through the method-security proxy. When the caller lacks `report:read`, the interceptor denies access before `readReport()`'s body runs.

**Never instantiate `new ReportService()`**, and never pull the bean out of the Spring context to speed up tests: doing so removes the proxy.

### Solution B — Guard Directly at the Public Entry Method

If multiple call paths truly share the same policy, you can place the guard on the entry method:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public String readFromInside() {
    return this.readReport();
}
~~~

When an external bean invokes **`reportService.readFromInside()`** via the proxy, **`@PreAuthorize` on `readFromInside()`** is evaluated. This may suffice if the entire call flow enters through that single method. However:

- Calling **`this.readFromInside()`** from another method on the same target again risks bypassing the entry advice.
- If another entry point calls the unprotected business logic directly, the policy can still be bypassed.
- If policies differ across methods, an annotation on the entry method may not match finer-grained internal policies.
- Putting guards only on controller paths does not stop schedulers, message consumers, or other services from calling sensitive methods; policies must sit at a trusted service boundary.

Hence, structuring a **protected bean invoked via proxy by different callers** is usually easier to audit and test.

### Solution C — AspectJ Weaving: Different Architecture, Not a Simple Flag

AOP **AspectJ weaving** can apply advice at join points proxy-based AOP cannot intercept, depending on weaving/annotation/mode setup. Yet it requires additional dependencies, compile-time or load-time weaving, and matching deployment/testing strategies. **Never claim flipping one flag on `@EnableMethodSecurity` automatically protects self-invocation.**

In most standard Spring Boot services, separating beans or guarding public entry methods is simpler and less risky.

### Avoid Preferring AopContext.currentProxy() or Self-Injection

You may encounter workarounds like **`AopContext.currentProxy()`**, self-injection, or `ApplicationContext.getBean(...)` to call back through the proxy. These depend on **`exposeProxy`**, proxy types, circular dependencies, or test wiring, making code harder to maintain. For security logic, **refactoring into clean service boundaries** is generally superior.

## 7. Writing Regression Tests After Fixing the Design

Once the unguarded self-invocation path is eliminated, a minimal matrix should include:

| Scenario | Production Criterion |
| --- | --- |
| Alice with **`report:read`** calls service proxy directly | Allowed |
| Bob without **`report:read`** calls service proxy directly | Denied |
| Bob goes through facade/orchestrating service | Denied |
| Bob goes through HTTP controller | **403** |
| Anonymous calls HTTP endpoint | **401** under the demo's Basic config |
| Bob goes through any internal method/alternate path | Cannot read report |
| Task scheduler or message handler calls protected service | Does not accidentally inherit stale or default `Authentication` |
| Data belonging to another user with the same role | Still denied by ownership/tenant policy |
| Method body with side effects | Side effects do not run when denied by `@PreAuthorize` |
| Method with `@PostAuthorize` | Result never leaks; check what side effects ran before post-advice |

### Proving the Method Body Truly Did NOT Run When Denied

Checking only for an exception is sometimes insufficient when a method has side effects. One way to test this is placing a **mock repository** beneath the service and verifying **`save/update`** was never called when `@PreAuthorize` fails. Ensure the service **remains a Spring AOP proxy bean**; never mock or replace the entire service and claim the interceptor was tested.

Example testing idea:

~~~text
Given: Authentication with role USER but lacking report:write
When:  call through proxy to @PreAuthorize("hasAuthority('report:write')") method
Then:  AccessDeniedException
And:   repository.save(...) was never called

Control case:
Given: caller has report:write
When:  call through proxy
Then:  method executes; repository is called per business logic
~~~

This article uses a literal string **`REPORT-42`** for illustration, so no repository or database is needed. With real data, also test authorization by **resource ownership**, not just a single coarse authority.

## 8. Mistakes in Testing Method Security

### 8.1. Instantiating Services with new

~~~java
ReportService service = new ReportService();
service.readReport();  // Does not go through Spring AOP proxy.
~~~

This snippet **is not a method-security test**; it only tests plain Java logic on the target object. If the goal is testing the interceptor, obtain the bean from the Spring test context or set up a real proxy.

### 8.2. Calling the Method Directly via this in the Same Class

For instance, one service method directly calls an annotated method on the same object, leaving **`@PreAuthorize`** on the inner method un-intercepted. Do not think `@WithMockUser` restores advice: the test user supplies `Authentication`, **not proxy routing**.

### 8.3. Mocking the Annotated Service Itself

If a Mockito mock or replacement bean swaps out the entire service under test, calls may hit only the mock. Tests returning stubbed strings/exceptions do not prove **`@PreAuthorize`** was enforced. Keep the real bean at the proxy boundary under test and mock only lower-level dependencies such as repositories or gateways.

### 8.4. Testing Only Authorized Users

If you only have:

~~~java
@WithMockUser(authorities = "report:read")
@Test
void happyPath() {
    assertThat(service.readReport()).isEqualTo("REPORT-42");
}
~~~

the test can **pass even when proxies are inactive**, because the method still returns `REPORT-42`. To catch "forgot `@EnableMethodSecurity`", "self-invocation bypass", or "test calling target directly", include **negative tests** with under-privileged principals. Only negative tests expose the difference between an advised proxy and a plain Java method.

### 8.5. Confusing 401/403 Across Service Calls and HTTP

**`AccessDeniedException`** is a Java exception thrown when invoking a method in a service test. **401/403 are HTTP status codes** decided by web security exception handling, not return values of a direct Java call.

- Protected method call by an authenticated user lacking permission → throws **`AccessDeniedException`** in the demo.
- Authenticated HTTP request denied at method → web layer translates to **403**.
- HTTP request missing Basic credentials → filter blocks before controller, **401**.
- With custom `AuthenticationEntryPoint`/`AccessDeniedHandler`, status/responses may differ; assert status codes under the actual deployed config.

### 8.6. Relying Solely on isAopProxy()

**`AopUtils.isAopProxy(reportService)`** indicates the injected bean is an AOP proxy, yet **does not guarantee** specific method advice is properly registered and actually invoked. A bean may be proxied for transactions, caching, or other advice. You must test **denied when called externally** and **allowed when authorized**, rather than stopping at metadata checks.

### 8.7. Placing @PreAuthorize on private/final Methods

Proxy interception requires compatible method signatures. With class-based proxies, **`final`** blocks overriding; **`private`** never becomes a proxy entry point. Never assume annotations execute if interception is impossible. Build tests from real callers and review class design.

### 8.8. Failing to Test Every Entry Point to the Same Business Logic

A service may be called from REST controllers, MVC actions, scheduled jobs, event listeners, or message consumers. Every path capable of touching sensitive data needs a trustworthy control boundary. Testing one controller path and seeing 403 is not enough if another internal method can bypass it.

## 9. Distinguishing Method Security from Other Proxy Annotations

Although sharing the AOP proxy mechanism, these annotations serve different purposes:

| Annotation | Meaning | Self-Invocation Risk |
| --- | --- | --- |
| **`@PreAuthorize`** | Blocks before method runs if lacking permission | Guard on inner method is skipped |
| **`@PostAuthorize`** | Checks condition after method runs | Output check is skipped; side effects may already have occurred |
| **`@Transactional`** | Creates transaction boundary | Inner method may not start a new transaction as expected |
| **`@Async`** | Dispatches execution to executor | Inner method may run synchronously on the caller thread |
| **`@Cacheable`** | Runs cache logic before/after method | Inner method may bypass cache interceptor |

Each annotation has its own features and configuration exceptions, yet **internal calls bypassing the proxy** are a shared failure mode for Spring AOP proxies. Never assume method security is valid just because transaction or async tests pass; test each type of advice.

## 10. Checklist for Code Review and Deployment

- **Is method security enabled?** Is `@EnableMethodSecurity` present in the real Spring context?
- **Is the bean properly proxied?** Do callers receive the bean via dependency injection rather than `new`?
- **How is the method called?** Trace `controller → facade → service`, especially **`this.`** calls inside the same class.
- **Where are annotations placed?** Are policies on a boundary every caller must cross, not just on internal helpers?
- **Can the method be intercepted?** Check `private`/`final`/class proxy type/visibility.
- **Is the policy complete?** Authentication, authorities, object/tenant permissions, account status, and business conditions.
- **Are negative tests present?** Under-privileged users are denied on bean methods, facades, and HTTP; self-invocation cannot bypass.
- **Are tests written properly?** Avoid `new`, mocking the service itself, internal non-proxied calls, and authorized-only happy-path suites.
- **Are HTTP statuses clear?** Distinguish Java `AccessDeniedException` from HTTP 401/403 and custom handlers.
- **Are side effects protected?** `@PreAuthorize` denies before writing data; `@PostAuthorize` cannot stop side effects that already ran.
- **Are all other entry points covered?** Schedulers, consumers, integration hooks, admin APIs, and shared services.
- **Is refactoring maintainable?** Prefer splitting beans or guarding entry methods; avoid overusing self-injection/`AopContext`.
- **Tested under real deployment settings?** Proxy mode, Spring Security version, method-security config, and servlet security chain align.

**Conclusion:** In Spring Security Servlet with proxy-based method security, **annotations execute only when calls pass through the appropriate interceptor**. Calling **`this.method()`** inside the same target object does not re-enter the proxy, and can bypass **`@PreAuthorize`** placed on an inner method. Prove it with **negative permission tests**, verify both service and HTTP calls, and refactor so every access path to sensitive business logic crosses a mandatory authorization boundary.
