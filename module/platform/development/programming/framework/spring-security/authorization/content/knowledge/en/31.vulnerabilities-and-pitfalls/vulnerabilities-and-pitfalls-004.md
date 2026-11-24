# Missing @EnableMethodSecurity or Calling Methods Without Going Through the Proxy

## 1. Security Issue to Identify

In Spring Security, placing **@PreAuthorize**, **@PostAuthorize**, or another protection annotation on a method **is not enough to guarantee every call is authorized**. Two major mistakes in the *method security* mechanism are:

1. **Method security is not enabled:** the project has Spring Security and annotations on services, yet lacks **@EnableMethodSecurity** in the application context. In that case, **@PreAuthorize** may be mere metadata with no interceptor applied.
2. **Calls bypass the Spring AOP proxy:** method security is enabled, yet code calls an annotated method on the same object (**self-invocation**) or invokes an object not managed by Spring; the interceptor is absent from the call path.

As a result, an authenticated user without sufficient permissions can still read reports, approve orders, update balances, or perform an operation meant only for administrators. This defect belongs to **broken authorization**, and does not necessarily manifest as a compile error, exception, or log message.

Goal of this lesson: understand when **@PreAuthorize** actually runs, reproduce both root causes, route calls through a proxied bean, and write regression tests that turn the build **red** if method security is disabled again.

> Examples focus on Spring Boot 3.3.x, Spring Security 6.x, Java 17+, and the standard Spring MVC model. Only reproduce vulnerabilities using accounts and data you control in a learning/test environment.

## 2. Why Request-Layer Security Cannot Replace Service-Layer Security

An application may have the configuration:

~~~java
http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated());
~~~

This rule requires callers to be logged in, but **does not automatically enforce** that only role ADMIN can call **ReportReader.readSecret(...)**. If a controller open to all logged-in users invokes the service method, rules must be added at the request layer, the service layer, or both depending on design. Once service-level policy is chosen, it must be enabled and routed through the interceptor.

Distinguishing the layers:

| Component | Effect | What It Does Not Automatically Guarantee |
| --- | --- | --- |
| SecurityFilterChain and authorizeHttpRequests | Controls HTTP requests by matcher/rule | Every internal service call checks `@PreAuthorize` |
| @EnableMethodSecurity | Registers method-level authorization infrastructure | Every call goes through the proxy if code self-invokes via `this` |
| @PreAuthorize on a method | Describes conditions before execution | Runs on its own if no corresponding interceptor exists |
| Spring AOP proxy | Intercepts calls entering the bean to run authorization advice | Intercepts self-invocation on the target object |
| Business policy / data-access check | Determines permissions by owner, tenant, action | Called properly if the actual execution path skips the policy layer |

**Roles and object-level permissions are two different levels.** Even when method security works, **hasRole('ADMIN')** only checks the role; for multi-tenant data or documents belonging to other users, the application also needs resource-level policies.

## 3. Mechanism: Spring Calls Into the Proxy Before Reaching the Real Method

When method security is enabled in the default **PROXY** mode, Spring creates a proxy around eligible beans. When another bean calls a protected method, the call passes through the proxy, through **AuthorizationManagerBeforeMethodInterceptor** (for `@PreAuthorize`), and only then enters the target if the policy permits.

~~~text
Controller / another bean
          |
          v
   Spring AOP proxy of ReportReader
          |
          +--> check @PreAuthorize("hasRole('ADMIN')")
                   |                    |
                   | allowed            | denied
                   v                    v
            ReportReader.readSecret   AccessDeniedException
                   |
                   v
              Result / side effect
~~~

Conversely, once inside the target object, calling **this.readSecret(...)** is an internal Java call to the same object. It **does not go back through the proxy**, so the advice on **readSecret** is not executed for that call.

~~~text
Another bean --> proxy of ReportService --> target.run()
                                               |
                                               v
                                       this.readSecret()
                                       (bypasses proxy)
                                               |
                                               v
                                       guard is skipped
~~~

That is the difference between **an annotation present in source code** and **authorization enforced at runtime**.

### 3.1. Mistake 1: Missing @EnableMethodSecurity

Example service:

~~~java
@Service
class PaymentApprovalService {
    @PreAuthorize("hasRole('ADMIN')")
    public void approve(long paymentId) {
        // Perform payment approval
    }
}
~~~

If the application context **lacks @EnableMethodSecurity** (or equivalent configuration), Spring Boot Starter Security **does not enable method-level authorization automatically**. In an application that only checks **authenticated()** at HTTP, a regular user can reach **approve** even without ADMIN. This is an illustrative snippet, omitting underlying repositories/services.

Enable it on a configuration class belonging to the running application context:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Or place **@EnableMethodSecurity** on the **@SpringBootApplication** class. With Spring Security 6, this annotation replaces the older **@EnableGlobalMethodSecurity** API in new configurations.

Commonly confused cases:
- The annotation sits on a **@Configuration** that is not component-scanned/imported into the context needing protection. Code compiles, yet the interceptor is not active where the bean runs.
- Configuring **@EnableMethodSecurity(prePostEnabled = false)** while code relies on **@PreAuthorize/@PostAuthorize**. You have disabled the default pre/post interceptor group unless you re-register it manually.
- The application uses **@Secured** or **@RolesAllowed** without enabling the corresponding group. With typical configuration, only **@PreAuthorize/@PostAuthorize** are enabled by default; **@Secured** requires **securedEnabled = true**, and JSR-250 **@RolesAllowed** requires **jsr250Enabled = true**.
- Tests only call the controller with a highly privileged user; without a **USER must be denied** case, missing configuration still leaves tests green.

### 3.2. Mistake 2: Self-Invocation Bypasses the Proxy

The following snippet **has @EnableMethodSecurity** yet remains dangerous if **run()** can be called by a regular user and no other policy protects that path:

~~~java
@Service
public class ReportService {
    public String run(long id) {
        return readSecret(id); // equivalent to this.readSecret(id)
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String readSecret(long id) {
        return "report:" + id;
    }
}
~~~

Step-by-step call explanation:

1. External code fetches the **ReportService** bean from Spring and calls **run(7)**. The call into **run** may go through the proxy, but **run** has no `@PreAuthorize` condition.
2. Inside the target, **run** calls **this.readSecret(7)**. This is an internal call; the method interceptor for **readSecret** does not execute.
3. The result **report:7** may be returned to USER. Yet the same USER calling **reportService.readSecret(7)** directly through the proxy is blocked.

This discrepancy makes the vulnerability hard to detect when testing only the annotated method directly without testing **every entry point** that can lead to it. Both an explicit **this.readSecret(...)** call and an implicit call omitting **this** suffer from the exact same issue.

Other cases that bypass the proxy include: manually instantiating the service with **new ReportService()**; calling **private** or **final** methods expecting Spring AOP to intercept; calling on the raw target object instead of the Spring bean; calling via an internal path that never touches the interceptor. With class proxies (CGLIB), **private/final** methods cannot be overridden for advice; JDK dynamic proxies only expose methods defined on the proxied interface. A safe rule for demos is to use **public** methods, Spring-managed beans, and a separate bean calling via dependency injection.

**Changing to @EnableMethodSecurity(proxyTargetClass = true) does not cure self-invocation.** Choosing CGLIB over JDK proxy only changes the proxy form; it does not route `this` calls back through the proxy. Spring has an AspectJ weaving option, but it requires separate setup/dependencies and is not the default fix for a service design flaw.

## 4. Reproduction Matrix and Identifying the True Root Cause

Suppose route **GET /api/reports/7** requires the user to be logged in. Business policy: only users with **ROLE_ADMIN** may view the report; users with **ROLE_USER** must be denied.

| Method Security | Call Path to Protected Logic | Caller | Expected | Symptom of Defect |
| --- | --- | --- | --- | --- |
| Enabled and proxy active | Controller → ReportReader proxy → readSecret | ADMIN | 200, correct report content | None |
| Enabled and proxy active | Controller → ReportReader proxy → readSecret | USER | 403, no report data | If 200, investigate |
| **Missing @EnableMethodSecurity** | Controller → bean with inactive @PreAuthorize | USER | 403 | 200 shows annotation is not blocking |
| Enabled but **self-invocation** | Controller → run → this.readSecret | USER | 403 | 200 due to bypassed interceptor |
| Enabled and proxy active | Direct call via Spring-managed proxy | USER | AccessDeniedException | If content returned, call is unguarded |
| Enabled and proxy active | Unauthenticated HTTP request | anonymous | 401 with HTTP Basic | If 200, request rule also needs checking |

**403** in Spring MVC is usually the result of **AccessDeniedException** thrown during the request flow and handled by filters; testing the service directly receives the exception rather than an HTTP status. Distinguish the two contexts when reading tests. With form login, clients may encounter a 302 redirect to login instead of 401.

When suspecting missing configuration, check:
- Which context actually contains **@EnableMethodSecurity**?
- Is **@PreAuthorize** turned off via **prePostEnabled = false**?
- Is the tested bean an **@Autowired** bean from Spring or an instance created with **new**?
- Does the entry point call the annotated method directly, or go through another method on the **same instance**?
- Does a proxy exist, and does the proxy type cover the method to protect?
- Are HTTP/endpoint security rules masking the vulnerability? For example, a route blocks USER before the service, yet the service remains unsafe when invoked from another queue/job.

## 5. Complete Java 17+ Example: Enabling Method Security and Calling Through a Bean Proxy

This example builds a small Spring Boot 3.3.5 application. Endpoint **GET /api/reports/{id}** only requires authentication at the request layer, while the ADMIN role is enforced on the method of **ReportReader**. **ReportFacade** and **ReportReader** are two separate Spring beans; consequently, when the facade calls **reader.readSecret(...)**, the call passes through the reader's proxy. This demo returns a mock string and contains no real reports.

### 5.1. Directory Structure

~~~text
method-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/security/
    │   ├── MethodSecurityDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── ReportReader.java
    │   ├── ReportFacade.java
    │   └── ReportController.java
    └── test/java/example/security/
        └── MethodSecurityRegressionTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'method-security-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/example/security/MethodSecurityDemoApplication.java**

~~~java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class MethodSecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityDemoApplication.class, args);
    }
}
~~~

Placing **@EnableMethodSecurity** on the startup class ensures it belongs to the demo's main application context. By default **prePostEnabled = true**, so the interceptor for **@PreAuthorize** is enabled.

**src/main/java/example/security/SecurityConfig.java**

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

The HTTP configuration intentionally requires only `authenticated` so tests can prove **service method security** is what blocks USER access. In a real system, corresponding HTTP rules should still be added for defense in depth; do not expect the route itself to check ADMIN in this example.

**src/main/java/example/security/ReportReader.java**

~~~java
package example.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportReader {
    @PreAuthorize("hasRole('ADMIN')")
    public String readSecret(long reportId) {
        return "report:" + reportId;
    }
}
~~~

**hasRole('ADMIN')** requires the **ROLE_ADMIN** authority under Spring Security's default convention; **@WithMockUser(roles = "ADMIN")** creates the matching authority in tests. **@PreAuthorize** blocks before the method body starts, making it suitable for operations that must prevent side effects.

**src/main/java/example/security/ReportFacade.java**

~~~java
package example.security;

import org.springframework.stereotype.Service;

@Service
public class ReportFacade {
    private final ReportReader reader;

    public ReportFacade(ReportReader reader) {
        this.reader = reader;
    }

    public String open(long reportId) {
        return reader.readSecret(reportId);
    }
}
~~~

**ReportFacade** is injected with the Spring-managed **ReportReader bean**, rather than instantiating it with **new**. Because **readSecret** has a policy applied, calls from this other bean go through the proxy. This is the core fix for self-invocation.

**src/main/java/example/security/ReportController.java**

~~~java
package example.security;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reports")
public class ReportController {
    private final ReportFacade facade;

    public ReportController(ReportFacade facade) {
        this.facade = facade;
    }

    @GetMapping("/{id}")
    public String get(@PathVariable long id) {
        return facade.open(id);
    }
}
~~~

Note: the response is demo text, not an ID-based data-access problem. For a real API, role checks do not replace owner/tenant checks on the report; object-specific permissions must also be verified in the service/data-access layer.

## 6. Regression Test: Testing Both Proxy and HTTP Path

**src/test/java/example/security/MethodSecurityRegressionTest.java**

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityRegressionTest {
    @Autowired MockMvc mvc;
    @Autowired ReportReader reader;
    @Autowired ReportFacade facade;

    @Test
    void securedReaderIsAopProxy() {
        assertTrue(AopUtils.isAopProxy(reader));
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotCallReaderDirectly() {
        assertThrows(AccessDeniedException.class,
                () -> reader.readSecret(7));
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotBypassMethodSecurityThroughFacade() throws Exception {
        assertThrows(AccessDeniedException.class,
                () -> facade.open(7));

        mvc.perform(get("/api/reports/7"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadThroughHttpAndFacade() throws Exception {
        assertEquals("report:7", facade.open(7));

        mvc.perform(get("/api/reports/7"))
                .andExpect(status().isOk())
                .andExpect(content().string("report:7"));
    }

    @Test
    void anonymousUserMustAuthenticate() throws Exception {
        mvc.perform(get("/api/reports/7"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Run in the project directory with JDK 17+ and a compatible Gradle (e.g., Gradle 8.5 wrapper):

~~~bash
./gradlew test
~~~

If a new project does not yet have a Gradle wrapper, use installed Gradle:

~~~bash
gradle test
~~~

**Expect 5 PASSing tests** on the valid configuration. Tests need no DB or external HTTP server: **MockMvc** executes requests in the test application context; **@WithMockUser** creates a mock security context. Commands and results below are **expectations for the sample**, not stdout from an executed run.

| Test | Assertion |
| --- | --- |
| securedReaderIsAopProxy | Reader is wrapped in an AOP proxy |
| userCannotCallReaderDirectly | USER is blocked on direct method call |
| userCannotBypassMethodSecurityThroughFacade | USER is blocked at both facade and endpoint |
| adminCanReadThroughHttpAndFacade | ADMIN can still perform the valid operation |
| anonymousUserMustAuthenticate | Unauthenticated request gets 401 |

**Try a counter-proof verification in the test environment:**

1. Temporarily remove **@EnableMethodSecurity**, run tests. **userCannotCallReaderDirectly** and **userCannotBypassMethodSecurityThroughFacade** must FAIL because the method is no longer blocked; the proxy test may also FAIL. Restore the annotation.
2. Temporarily replace the facade with a version calling the protected method **on itself** (snippet in Section 7), run tests. USER can retrieve data; the **userCannotBypassMethodSecurityThroughFacade** test must FAIL. Restore the two-bean design.
3. Rerun tests after restoring. Consider the configuration safe only when tests covering both denied and allowed cases PASS.

Do not infer security just because the ADMIN test returns 200: both buggy and valid implementations can return 200 for ADMIN. **Negative tests with USER** are what prove the permission barrier is working.

## 7. Intentionally Faulty Variant to Understand Self-Invocation

This is a **dangerous alternative version for illustration**, do not combine with **ReportFacade.java** from Section 5. If you replace the facade with this code and keep the controller/config/tests unchanged, the **open** method calls **readSecret** on the target itself:

~~~java
package example.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportFacade {
    public String open(long reportId) {
        return readSecret(reportId); // self-invocation: bypasses advice
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String readSecret(long reportId) {
        return "report:" + reportId;
    }
}
~~~

Observations:

- **GET /api/reports/7** as USER can return **200, report:7**, because the endpoint calls **open**, whereas **@PreAuthorize** sits only on **readSecret** and is not invoked through a proxy.
- As USER, calling **reportFacade.readSecret(7)** directly from another bean is still denied because that call enters the proxy.
- If you only test `readSecret` directly and forget to test the **open** path, you can falsely conclude that method security protects the whole service.
- Fix by moving the protected logic into a separate **ReportReader bean** and injecting it into the facade as in Section 5. Do not try to solve this by repeating **@EnableMethodSecurity** or enabling **proxyTargetClass**.

If a design mandates multiple internal calls within the same class, you can extract the policy into a **separate authorization bean** and invoke it at the entry point, or enforce explicit permission checks consistently inside the service. Solutions like self-injection or calling **AopContext.currentProxy()** create coupling to AOP mechanics and can introduce circular dependencies or fragile configurations; prefer splitting beans.

## 8. Diagnosing with Proxies and Actual Call Paths

A useful check when in doubt is verifying whether the injected object is a proxy:

~~~java
import org.springframework.aop.support.AopUtils;

boolean proxy = AopUtils.isAopProxy(reportReader);
System.out.println("Proxied: " + proxy);
~~~

This snippet depends on the **reportReader** variable injected from Spring; it is not standalone Java. If the **readSecret** method has the interceptor applied in the example, expect **Proxied: true**. However, seeing a proxy alone **is not enough** to conclude every path is safe: a call from proxy to target followed by the target calling another method on itself can still skip advice.

Read stack traces or set breakpoints at:
- The bean injected into the controller/facade.
- The public method annotated with **@PreAuthorize**.
- Code calling that method from another bean vs from **this**.
- Denied results and any side effects that occurred.

Do not merely search for the string **@PreAuthorize** in source code. The goal is to prove **actual callers** are checked before sensitive logic executes. If a method has multiple entry points such as HTTP, message consumer, scheduler, CLI, or tests, build a matrix across every entry point.

Distinguishing situations that are easily conflated:

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| `@PreAuthorize` is present yet USER can call it even directly on the injected bean | Method security not enabled, annotation group disabled, bean not proxied / annotation unrecognized | Check configuration and run negative direct-call test |
| Direct call is blocked, yet another endpoint still returns data | Self-invocation or another call path bypassing the protected method | Trace from endpoint to target; test through facade |
| Tests show a proxy exists yet bypass still occurs | Proxy only intercepts entry into the bean; internal calls skip it | Inspect methods containing `this.method()` |
| USER always gets 403 over HTTP so the service is assumed safe | HTTP rule blocks first; service method security might still be inactive | Test the service via injected bean, not just endpoints |
| Only an annotated method on a certain interface/class is unblocked | Proxy structure, annotation placement, or method overridability | Inspect actual bean, interface, and public/final/private; test actual permissions |
| Test uses `new ReportReader()` to check security | Object is not managed by Spring | Use `@SpringBootTest` and `@Autowired` bean |

**Do not use @PostAuthorize to “block before” write operations.** `@PostAuthorize` can evaluate after the method body has already run, so side effects may happen before denial. For sensitive write/delete/approve commands, use `@PreAuthorize` or a service-level policy invoked before the action and verify transaction consistency.

## 9. Prevention in Code Reviews and Real Project Testing

Checklist focused specifically on the two defects in this lesson:

- Locate the active method security configuration in the **deployed application context**, not just in source/test configs.
- Confirm the right annotation type is enabled: **@PreAuthorize**, **@PostAuthorize**, **@Secured**, **@RolesAllowed** have different activation flags.
- Verify beans are created/injected by Spring; do not bypass with **new** or direct references to the target object.
- Search for **this.sensitiveMethod(...)** calls, implicit internal calls, and **private/final** helpers carrying permission annotations; evaluate every entry point that can reach that logic.
- Place protected methods at an appropriate **service boundary** and call them from another bean; keep sensitive business logic out of controllers.
- Have at least one **allowed** test and one **denied** test for each important role/action. Test both the service via **@Autowired** and real endpoints/consumers.
- For object/tenant authorization, add different-owner/different-tenant cases; **hasRole** does not replace resource permission verification.
- Whenever changing AOP config, package scanning, bean lifecycle, or splitting/merging services, rerun authorization coverage tests; self-invocation easily reappears after refactoring.
- For write APIs, check storage state/side effects after a denied request; checking only 403 can miss changes made before the check.
- Never run test operations against production data without authorization; log test cases with mock data and mask credentials.

### Common Myths

**“Having spring-boot-starter-security means method security turns on automatically.”** False. The starter supports web security, while method-level authorization requires **@EnableMethodSecurity** or equivalent setup.

**“Putting @PreAuthorize on a method is enough.”** Not enough. The method must be visible to the right interceptor and calls must pass through the proxy interception point.

**“Since CGLIB is used, this.securedMethod() is intercepted.”** False. CGLIB is still a proxy; self-invocation on the target does not go through it.

**“A passing test with ADMIN principal proves the policy is running.”** False. That only proves the happy path; you must test that USER is blocked.

**“Putting policy in the controller protects everywhere.”** Not necessarily. A message listener, scheduled job, or another bean may call the service directly. Business authorization should be enforced at the layer owning sensitive logic.

**“Disable HTTP filters in MockMvc to make testing method security easier.”** Do not use HTTP tests with disabled filters as evidence of HTTP policy. When testing services, use direct bean tests; when testing endpoints, keep the real security filter chain.

## 10. Practical Conclusion

For a Spring method to truly be protected by **@PreAuthorize**, two conditions must hold simultaneously: **(1) method security is enabled in the right context; (2) calls to the protected method pass through a Spring-managed proxy** (or an intentionally configured alternative advice mechanism). Missing either one can leave the annotation unenforced even though source code looks valid.

When testing, always verify **both directions**: a valid user must succeed, and an insufficiently privileged user must be blocked both when calling the bean directly and through every relevant entry point. With Spring Security, verifying actual call paths is far more reliable than counting annotations in code.

### Official References for Further Reading

- Spring Security — Method Security (Spring Security 6.x): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Framework — Spring AOP Proxying Mechanisms (self-invocation, JDK/CGLIB): https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
