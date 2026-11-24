# `@PreAuthorize` Not Running Due to Proxy Configuration or Internal Calls — Spring Security Servlet Diagnostics

> **Scope:** Spring Security 6.x, Spring Framework 6.x, Spring Boot 3.x, Java 17+; focused on **method security on Spring-managed beans** in Spring MVC/Servlet applications. This guide distinguishes missing method-security activation, non-proxy objects, `this.method()` calls within the same bean, JDK dynamic proxy vs. CGLIB proxy limits, and testing mistakes that make `@PreAuthorize` appear ineffective. Includes a complete Maven project, application, and MockMvc tests to **observe both the self-invocation bug and the separate-bean fix**.

## 1. Symptoms and the First Question

You write:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void deleteEverything() {
    // Sensitive operation.
}
~~~

Yet a user holding only `ROLE_USER` still triggers the method, or a unit test calls the method without receiving `AccessDeniedException`. Do not jump to concluding Spring Security ignored authorization for one single reason. There are at least four cause groups:

1. **Method security is not enabled**: missing `@EnableMethodSecurity`, or the annotation lives on a configuration class not loaded as a bean.
2. **Calls bypass the Spring AOP proxy**: `this.deleteEverything()`, direct internal calls, instantiating with `new`, or holding a reference to the target instead of the proxy.
3. **The proxy cannot intercept that specific method**: `private` or `final` methods, a `final` target class under class-based proxies, or visibility/resolution/annotation placement incompatible with the proxy and framework version.
4. **The expression or test is not what you think**: `hasRole` vs. `hasAuthority`, a mocked `Authentication` with overly broad roles, a different request matcher, tests not loading security configuration, invoking a different bean/overload, or a custom method-security advisor.

**Core principle:** `@PreAuthorize` is not an `if` statement automatically injected at the top of your method body. Under default method security using **Spring AOP proxies**, the framework evaluates the expression **on the way through the proxy before the target method executes**. Calling the target directly without going through the proxy skips the advice.

### 1.1. What Is the Normal Outcome?

Suppose a service has:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public String sensitiveAction() {
    return "allowed";
}
~~~

When **the call goes through the proxy**:
- Valid `Authentication` with `ROLE_ADMIN` → the method executes and returns `allowed`.
- Valid `Authentication` with only `ROLE_USER` → the interceptor denies before the method runs, typically throwing `AccessDeniedException`.
- Missing or insufficiently trusted `Authentication` → security infrastructure handles it according to context and the corresponding exception type.

Inside an HTTP request traversing `SecurityFilterChain`, the exception may translate to:
- **403 Forbidden** when authenticated yet lacking permissions;
- **401 Unauthorized** or **302 redirect to the login page** when unauthenticated, depending on the authentication entry point.

When calling the service directly from a Java test without Servlet filters, you normally see **a Java exception** rather than an HTTP status. Do not equate `@PreAuthorize` with “always produces 403 in every environment”.

## 2. How Does Spring Security Method Security Work Through Proxies?

In Spring Security 6.x with `@EnableMethodSecurity`, interceptors/authorization managers integrate with Spring AOP to enforce annotations such as `@PreAuthorize` on supported methods.

~~~text
HTTP request after passing Spring Security FilterChain
         |
         v
Controller (Spring-managed)
         |
         | injected reference to service BEAN
         v
+---------------------------------+
| Spring AOP proxy of service     |  <--- protected boundary
| - @PreAuthorize interceptor     |
| - reads current Authentication  |
| - evaluates SpEL                |
| - DENY -> exception             |
| - ALLOW -> invokes target       |
+---------------------------------+
         |
         v
     Target service method
         |
         v
     Business operation
~~~

**The keyword is proxy reference.** Spring manages beans and typically injects a proxy-wrapped reference at dependency injection sites. The framework does not rewrite your class body to insert an inline authorization check.

### 2.1. Minimal Configuration in Spring Security 6

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

This is **a complete configuration class when placed inside a Spring application**. Starting with Spring Security 6, prefer `@EnableMethodSecurity` over the older `@EnableGlobalMethodSecurity`. `@EnableMethodSecurity` enables `@PreAuthorize`/`@PostAuthorize` by default without requiring `prePostEnabled=true` for standard usage.

**Separate two independent axes:**
- `http.authorizeHttpRequests(...)` controls **HTTP requests** traversing the Servlet filter chain.
- `@PreAuthorize(...)` controls **Java method invocations** through the method-security infrastructure.

An app can require login on URLs while **method security is still disabled**. In that state, `authenticated()` only blocks anonymous requests; it **never replaces** a `hasRole('ADMIN')` rule on a service method.

### 2.2. Key Components

| Component | Role |
| --- | --- |
| `@EnableMethodSecurity` | Activates method-security infrastructure in the application context. |
| `@PreAuthorize` | Declares an expression evaluated before method execution. |
| `AuthorizationManagerBeforeMethodInterceptor` | An interceptor in the modern method-security model enforcing authorization decisions. |
| `SecurityContextHolder` | Source of `Authentication` typically read when method security evaluates decisions. |
| `Authentication` and `GrantedAuthority` | Authenticated identity and actual authorities. |
| Spring AOP proxy | Interception point before invocations reach the target. |
| `AopUtils.isAopProxy(bean)` | Checks whether a bean reference is an AOP proxy in tests/diagnostics. |

Internal classes and advisor sets can vary across versions or customizations. **Never hard-code internal filter/advisor order or class names** as an API contract unless guaranteed by the framework.

## 3. Classic Bug: Self-Invocation Bypasses `@PreAuthorize`

Example:

~~~java
@Service
public class OrderService {

    public void submitOrder() {
        // Call WITHIN THE SAME target object:
        this.approveHighValueOrder();
    }

    @PreAuthorize("hasRole('MANAGER')")
    public void approveHighValueOrder() {
        // Approval logic.
    }
}
~~~

This is a **bug-illustration fragment**, omitting imports and other application components.

If a Controller calls `orderService.approveHighValueOrder()` through the **Spring bean proxy**, security advice has a chance to block it. However, if the Controller calls `orderService.submitOrder()` through the proxy, and `submitOrder()` on the **target** executes `this.approveHighValueOrder()`, the internal call **does not pass through the proxy a second time**. The annotation on `approveHighValueOrder()` can **go unchecked**.

~~~text
CASE A — external invocation through proxy:

Controller -> OrderService proxy
              | @PreAuthorize(hasRole('MANAGER'))
              | -> deny USER / allow MANAGER
              v
            target.approveHighValueOrder()


CASE B — self invocation BYPASSES advice on inner method:

Controller -> OrderService proxy
              | submitOrder() has no equivalent policy
              v
            target.submitOrder()
              |
              | this.approveHighValueOrder()
              |  ^ direct call inside target
              |    bypasses proxy/interceptor
              v
            target.approveHighValueOrder()
~~~

**This is inherent to self-invocation in proxy-based Spring AOP**, not unique to `@PreAuthorize`. The same mechanism affects `@Transactional`, `@Cacheable`, and `@Async` when called internally within the same class using proxy-based advice.

### 3.1. Why “The Outer Method Already Went Through the Proxy” Is Not Enough

A proxy can only intercept **method entries crossing the proxy boundary**. Having entered an outer method via the proxy does not route inner `this.*` calls back through the proxy.

For example, if `submitOrder()` only has `@PreAuthorize("isAuthenticated()")` while `approveHighValueOrder()` requires `MANAGER`, any authenticated user can still execute the inner logic unless guarded otherwise. **A weaker rule on an outer method never substitutes for the inner method's rule**.

### 3.2. Watch Out for Calls Without Explicit `this`

In Java, simply writing:

~~~java
approveHighValueOrder();
~~~

inside the same class is still a self-call through `this`. Omitting `this.` **does not fix the problem**. Calls from constructors, `private` helpers, or a target reference cached in a field likewise bypass Spring proxies.

## 4. Best Fix: Move the Protected Boundary to Another Spring Bean

The clearest, easiest-to-test fix is extracting the policy-protected operation into **a separate service bean** and injecting it wherever callers invoke it.

~~~text
Controller
   |
   v
WorkflowService bean
   |
   | injected reference
   v
SensitiveOperationService PROXY
   |
   | @PreAuthorize("hasRole('ADMIN')")
   |
   +-- user lacking permission -> AccessDeniedException
   |
   v
SensitiveOperationService target
~~~

Every entry point needing the sensitive operation then invokes it through the policy-enforcing service proxy. This structure:
- reduces the risk of forgetting checks when adding new entry points;
- separates **orchestration** from **security-sensitive operations**;
- lets tests verify denial at the exact boundary;
- avoids hacks grabbing the current proxy from `AopContext`;
- works cleanly across Controllers, message listeners, and services with varied callers.

**Important:** splitting beans does not replace resource-specific permission checks; `@PreAuthorize("hasRole('ADMIN')")` is only a role-based example. Ownership/tenant checks require appropriate expressions or authorization services.

## 5. Runnable Maven/Java 17 Example: Observing the Bug and the Fix

The project includes:
- `GET /api/direct`: Controller calls the protected method through the injected Spring service proxy.
- `GET /api/unsafe`: Controller calls another method on the service, which **self-invokes** the protected method. This endpoint is **intentionally insecure to demonstrate the bug**.
- `GET /api/fixed`: Controller calls a separate orchestration service, which calls the protected method **through its proxy reference**.
- Two accounts: `alice` with `ROLE_USER` and `admin` with `ROLE_ADMIN`.

**Use this project only in learning environments; `/api/unsafe` is an intentional anti-pattern and must never remain in production.** Spring Boot 3.3.5 is used as a concrete Java 17+ example version, not claimed to be the latest release.

### 5.1. Project Structure

~~~text
method-security-proxy-demo/
  pom.xml
  src/
    main/
      java/com/example/methodsecurity/
        MethodSecurityDemoApplication.java
        SecurityConfig.java
        SensitiveService.java
        WorkflowService.java
        ProbeController.java
    test/
      java/com/example/methodsecurity/
        MethodSecurityIntegrationTest.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>method-security-proxy-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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

### 5.3. Main Application and EnableMethodSecurity

**`src/main/java/com/example/methodsecurity/MethodSecurityDemoApplication.java`:**

~~~java
package com.example.methodsecurity;

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

Note that `@EnableMethodSecurity` must belong to a **configuration class actually loaded by the Spring `ApplicationContext`**. Placing it on a class instantiated manually with `new` or outside component scanning without importing it will not activate method-security infrastructure.

### 5.4. SecurityConfig: Real Users for the HTTP Basic Demo

**`src/main/java/com/example/methodsecurity/SecurityConfig.java`:**

~~~java
package com.example.methodsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("user-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            // All example endpoints are GET read-only;
            // CSRF is not disabled and there are no state-changing POSTs.
            .build();
    }
}
~~~

Points to note:

1. `httpBasic` verifies real credentials through the authentication provider; tests do not use client-asserted principals.
2. `.authenticated()` on URLs requires login yet **does not check `ADMIN` role yet**. This is intentional so tests highlight the boundary between HTTP security and method security.
3. `.roles("ADMIN")` produces the `ROLE_ADMIN` authority, matching `hasRole('ADMIN')`.
4. `SessionCreationPolicy.STATELESS` keeps the Basic demo sessionless; it is **not** a prerequisite for enabling method security.
5. The demo hard-codes passwords in source for learning. Production needs an identity store/IdP, password hashing, secret management, TLS/HTTPS, and proper auditing.
6. The GET APIs mutate no business state—even the “unsafe” endpoint simply returns a string; the goal is observing proxy behavior without introducing real risk into a live system.

### 5.5. SensitiveService: Protected Method and Self-Invocation

**`src/main/java/com/example/methodsecurity/SensitiveService.java`:**

~~~java
package com.example.methodsecurity;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class SensitiveService {

    @PreAuthorize("hasRole('ADMIN')")
    public String privilegedAction() {
        return "privileged-action";
    }

    // INTENTIONALLY WRONG: target calls itself.
    // @PreAuthorize on privilegedAction() is not applied
    // to the internal call this.privilegedAction().
    public String unsafeSelfInvocation() {
        return this.privilegedAction();
    }
}
~~~

**Diagnostic takeaway:** `SensitiveService` is Spring-managed, so the reference injected into the controller is a proxy. Yet **inside the target**, `this.privilegedAction()` bypasses the proxy—and the method does not re-check permissions.

Do not “fix” this merely by adding `@PreAuthorize("isAuthenticated()")` onto `unsafeSelfInvocation()`. A regular user is already authenticated and would still enter; the expression must enforce the actual required privilege, or the structure must route the sensitive call through a proxy.

### 5.6. WorkflowService: Fixing by Calling Through an Injected Bean

**`src/main/java/com/example/methodsecurity/WorkflowService.java`:**

~~~java
package com.example.methodsecurity;

import org.springframework.stereotype.Service;

@Service
public class WorkflowService {

    private final SensitiveService sensitiveService;

    public WorkflowService(SensitiveService sensitiveService) {
        this.sensitiveService = sensitiveService;
    }

    public String invokeSafely() {
        // ANOTHER bean calls SensitiveService via its injected proxy.
        return sensitiveService.privilegedAction();
    }
}
~~~

Separating beans creates an explicit interception boundary. When `WorkflowService.invokeSafely()` is invoked from the controller, it calls `SensitiveService.privilegedAction()` through the Spring-injected reference, allowing `@PreAuthorize` to intercept.

### 5.7. Controller: Three Call Paths to Compare

**`src/main/java/com/example/methodsecurity/ProbeController.java`:**

~~~java
package com.example.methodsecurity;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ProbeController {

    private final SensitiveService sensitiveService;
    private final WorkflowService workflowService;

    public ProbeController(
            SensitiveService sensitiveService,
            WorkflowService workflowService) {
        this.sensitiveService = sensitiveService;
        this.workflowService = workflowService;
    }

    @GetMapping("/direct")
    public Map<String, String> direct() {
        return Map.of(
            "result", sensitiveService.privilegedAction());
    }

    @GetMapping("/unsafe")
    public Map<String, String> unsafe() {
        return Map.of(
            "result", sensitiveService.unsafeSelfInvocation());
    }

    @GetMapping("/fixed")
    public Map<String, String> fixed() {
        return Map.of(
            "result", workflowService.invokeSafely());
    }
}
~~~

Endpoint `/api/unsafe` intentionally reproduces **method-security advice bypass** for learning observation. **Never deploy such an endpoint in real systems**, and never use GET endpoints to perform state-changing mutations.

### 5.8. Running with Maven and curl

Requires JDK 17+, Maven, and repository access for dependencies.

~~~bash
mvn test
mvn spring-boot:run
~~~

There is no fixed Maven stdout: dependency caching, logger/test reporters, and machine setup can vary output. Below are the **expected HTTP outcomes based on the demo config**, not captured server transcripts.

Without credentials:

~~~bash
curl -i http://localhost:8080/api/direct
~~~

Expected HTTP `401 Unauthorized` because `/api/**` requires authentication and the app configures a Basic entry point.

User without `ROLE_ADMIN`:

~~~bash
curl -i -u alice:user-pass http://localhost:8080/api/direct
~~~

Expected HTTP `403 Forbidden`. `@PreAuthorize` intercepts via the proxy.

Same user calling the broken self-invocation path:

~~~bash
curl -i -u alice:user-pass http://localhost:8080/api/unsafe
~~~

Expected HTTP 200, representative response:

~~~json
{"result":"privileged-action"}
~~~

**200 here is an intentional design-bug demonstration, not acceptable production behavior.** HTTP authentication ran and succeeded, yet method security **did not apply to the internal call**.

Same user calling the fixed path:

~~~bash
curl -i -u alice:user-pass http://localhost:8080/api/fixed
~~~

Expected HTTP `403 Forbidden` because the call traverses the `SensitiveService` proxy.

Valid admin user:

~~~bash
curl -i -u admin:admin-pass http://localhost:8080/api/direct
curl -i -u admin:admin-pass http://localhost:8080/api/fixed
~~~

Expected HTTP 200 with `{"result":"privileged-action"}` on both endpoints.

**Note:** `curl -u` and HTTP localhost in this example are for study only. On real networks use HTTPS and keep production passwords out of terminal history and logs.

## 6. Integration Tests Proving the Real Cause

Tests must load the real Spring application context and security filters. Use MockMvc with real Basic credentials so authentic `Authentication` and AOP method-security proxies run.

**`src/test/java/com/example/methodsecurity/MethodSecurityIntegrationTest.java`:**

~~~java
package com.example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private SensitiveService sensitiveService;

    @Test
    void sensitiveServiceIsAnAopProxy() {
        assertTrue(AopUtils.isAopProxy(sensitiveService));
    }

    @Test
    void anonymousRequestIsRejectedBeforeController() throws Exception {
        mvc.perform(get("/api/direct"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/direct")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void directCallDeniesNonAdmin() throws Exception {
        mvc.perform(get("/api/direct")
                .with(httpBasic("alice", "user-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void directCallAllowsAdmin() throws Exception {
        mvc.perform(get("/api/direct")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value(
                "privileged-action"));
    }

    @Test
    void internalThisCallDemonstratesBypass() throws Exception {
        // Negative demonstration: 200 is proof of the BUG.
        mvc.perform(get("/api/unsafe")
                .with(httpBasic("alice", "user-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value(
                "privileged-action"));
    }

    @Test
    void refactoredCrossBeanCallDeniesNonAdmin() throws Exception {
        mvc.perform(get("/api/fixed")
                .with(httpBasic("alice", "user-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void refactoredCrossBeanCallAllowsAdmin() throws Exception {
        mvc.perform(get("/api/fixed")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value(
                "privileged-action"));
    }
}
~~~

**Why is this test suite valuable?**

1. `@SpringBootTest` loads `@EnableMethodSecurity`, `SecurityFilterChain`, service beans, and Spring AOP infrastructure.
2. `@AutoConfigureMockMvc` keeps the filter chain active so real Basic credentials traverse the authentication provider.
3. `AopUtils.isAopProxy(sensitiveService)` confirms the injected bean reference is proxied, ruling out a misdiagnosis that Spring created no proxy at all.
4. Tests for `/api/direct` and `/api/fixed` expect 403 for `USER`: both routes enter the protected method **through the proxy**.
5. The `/api/unsafe` test expecting 200 for `USER` **exists solely to reproduce the vulnerability**, not as desired product behavior.
6. The `ADMIN` test expecting 200 proves the rule permits the authorized role rather than blocking everyone.
7. The wrong-password test expects 401, separating HTTP filter authentication failures from method-security authorization failures.

After fixing production code by **deleting the unsafe path**, update tests to assert that “every public entry point to this operation denies non-admins”. Never leave a test asserting a vulnerability remains open in a production test suite.

### 6.1. Why Not Unit-Test with `new`?

A test like:

~~~java
SensitiveService service = new SensitiveService();
String result = service.privilegedAction();
~~~

returns `privileged-action` because it is a **plain Java object** with no Spring proxy. That does not prove `@EnableMethodSecurity` broke; it proves **you are not calling a Spring bean**.

Unit tests can verify pure logic, yet **method-security tests** must execute through an `ApplicationContext` with method-security/proxy infrastructure and an appropriate `Authentication`, or use HTTP integration tests as above.

### 6.2. How `@WithMockUser` Can Mislead

`@WithMockUser(roles = "ADMIN")` is great for verifying **authorization policies**, yet does not prove HTTP Basic passwords, JWT decoders, or form login work. Testing only with a mocked `ADMIN` lets the protected method pass and can omit `ROLE_USER`/anonymous cases. When diagnosing proxies, include both a **deny case** with insufficient authority and an **allow case** with sufficient authority.

### 6.3. When 403 Does Not Behave as Expected

Check in order:
- Is `@EnableMethodSecurity` loaded?
- Is the service bean reference an AOP proxy?
- Did the call go through the proxy or via `this.`?
- Does the user genuinely carry `ROLE_ADMIN`?
- Is the method annotation on the implementation, interface, or an override, and is a different overload being invoked?
- Did `@ControllerAdvice` or a custom exception handler alter the response?
- Does the test enable filters, hit the right security chain, and populate the user context?

Never “fix” tests by adding `permitAll()` or disabling method security/CSRF; that hides bugs instead of solving them.

## 7. Inspecting the Actual Proxy Before Changing Config

### 7.1. Fetching the Bean from `ApplicationContext`

A fragment run inside a Spring test/application:

~~~java
@Autowired ApplicationContext context;

@Test
void inspectProxy() {
    Object bean = context.getBean(SensitiveService.class);

    System.out.println("proxy=" + AopUtils.isAopProxy(bean));
    System.out.println("jdk=" + AopUtils.isJdkDynamicProxy(bean));
    System.out.println("cglib=" + AopUtils.isCglibProxy(bean));
    System.out.println("targetType=" + AopUtils.getTargetClass(bean));
}
~~~

This is a **fragment** needing imports for `ApplicationContext`, `Test`, `AopUtils`, and demo classes; it is not a standalone Java program. Exact JDK/CGLIB results depend on class/interface structure and proxy-target-class settings.

Do not rely solely on `bean.getClass().getName()`: proxies carry generated class names that vary by framework; **`AopUtils`** queries the framework directly. `isAopProxy=true` only confirms the bean is a proxy; proving **a specific method carries method-security advice** still requires deny/allow integration tests.

### 7.2. When the Bean Is Not Proxied

If `AopUtils.isAopProxy` returns false despite `@PreAuthorize`, check:
1. Is `@EnableMethodSecurity` present in the **running/test application context**?
2. Is the class registered as a bean via `@Service`, `@Component`, `@Bean`, or equivalent configuration?
3. Did you accidentally invoke an instance created with `new`?
4. Is the method annotation placed where Spring Security's method-security pointcut detects it?
5. Was the bean instantiated too early in the lifecycle, skipping post-processors?
6. Are custom AOP/proxy factories, profiles, or conditional configs altering the bean?

If the bean carries other advice (`@Transactional`, caching), `isAopProxy=true` still **does not guarantee** the `@PreAuthorize` advisor is present. Access-denied tests at the boundary remain the decisive proof.

### 7.3. When a Proxy Exists Yet the Method Still Does Not Block

Check:
- **Self-invocation:** does the target call `this.protectedMethod()`?
- **Method visibility:** is the method `public` and eligible for advice interception?
- **Final methods/classes:** class-based proxies cannot override `final` methods; `final` classes cannot be subclassed.
- **Annotation placement:** is the annotation on the class, interface, or implementation? Is a different overload/override invoked?
- **Proxy type:** is the bean injected by interface while code holds a reference to the concrete class/target?
- **Expression:** are actual roles/authorities and principal accurate?
- **Multiple application contexts:** did tests or a servlet child context create duplicate beans or differing configs?

In particular, **“a proxy exists” and “the call passed through the proxy” are two different statements**. Self-invocation is the classic example: the injected bean is a proxy, yet a method inside the target invokes another via `this`, bypassing the inner method's advice.

## 8. JDK Dynamic Proxies vs. CGLIB Class-Based Proxies

Spring AOP primarily uses two proxy styles:

| Characteristic | JDK Dynamic Proxy | Class-Based Proxy (Typically CGLIB) |
| --- | --- | --- |
| Mechanism | Implements interfaces. | Subclasses the target class. |
| Typical condition | Bean implements interface(s) and `proxy-target-class` is not forced true. | No interfaces, or configuration forces class proxying. |
| Advisable methods | Depends on methods exposed on the interface and mapped to target. | Depends on overridable/interceptable methods; cannot intercept `final`/`private`. |
| Injecting by concrete class | Not always assignable because JDK proxies do not extend the class. | Typically assignable when types match. |
| Self-invocation `this.method()` | **Bypassed.** | **Bypassed.** |
| Fixes self-invocation by switching proxy type? | **No.** | **No.** |

### 8.1. Switching JDK → CGLIB Does Not Fix Self-Invocation

You can configure:

~~~java
@EnableMethodSecurity(proxyTargetClass = true)
~~~

to request class-based proxies where Spring Security method security supports the option. However, **this is not an automatic fix for self-invocation**: neither interface-based nor subclass-based proxies intercept calls made internally within the target under Spring AOP's proxy model.

If “a method in the same bean must be advised” is the goal, the preferred fix is **refactoring into another bean**. AspectJ weaving is a separate architecture requiring its own setup and operations; it is not enabled merely by `proxyTargetClass=true`.

### 8.2. Final Classes, Final Methods, and Private Methods

Never put `@PreAuthorize` on `private void performSensitiveOperation()` expecting a Spring AOP proxy to invoke advice on a private method. Class-based proxies cannot override `final` methods, and `final` classes cannot be subclassed by class-based proxies. With interface-based proxies, advised methods must have a clear path through the interface and implementation; methods existing only on the concrete target may not be reachable through a JDK proxy.

The safest, most testable design is a **public, non-final method on a Spring-managed service bean**, invoked **from another bean through an injected proxy**. In languages like Kotlin where classes/methods are final by default, check the “open” compiler plugin or design compatible interfaces/advice.

### 8.3. `@PreAuthorize` on Interface vs. Implementation?

Annotation discovery involves method declarations, interfaces, superclasses, and resolution rules in your Spring Security version. Avoid guessing “the framework finds every annotation everywhere”.

In large codebases:
- place policies at the **public service boundary** callers actually use;
- maintain one consistent convention (such as public methods on service implementations);
- avoid conflicting annotations across interfaces, implementations, and overrides;
- write tests invoking the bean through the exact type used in production.

If annotations in a class hierarchy cause ambiguity or startup failures, read the explicit error message and adjust placement rather than catching and swallowing exceptions.

## 9. Common `@EnableMethodSecurity` Configuration Mistakes

### 9.1. Missing Annotation or Placing It in an Unloaded Class

You have:

~~~java
@Configuration
@EnableMethodSecurity
public class SecurityMethodConfig {
}
~~~

yet the class sits outside component scanning and is never imported into the context. In that case the annotation **has no effect**, even though it exists in source. Check `@SpringBootApplication` base packages, `@Import`, test slices/profiles, and conditional configurations.

### 9.2. Confusing `@EnableWebSecurity` with `@EnableMethodSecurity`

`@EnableWebSecurity`/`SecurityFilterChain` governs web security. `@EnableMethodSecurity` activates method security. Never assume that because HTTP Basic login works, `@PreAuthorize` must already be enabled.

### 9.3. Partially Migrated Spring Security 5 Config

Older projects used:

~~~java
@EnableGlobalMethodSecurity(prePostEnabled = true)
~~~

When upgrading to Spring Security 6, prefer `@EnableMethodSecurity`. **Never mix legacy examples and new APIs** without checking dependencies and versions; interceptor registration and annotation configuration evolved across major releases.

### 9.4. Multi-Module Apps and Separate Contexts

If controllers live in app A while services live in a library initialized in context B, method-security config may be missing in the context hosting the bean. Likewise, `@WebMvcTest` slices load MVC components without loading services or method-security configs you expect. Inspect **actual bean instances and active contexts** rather than merely grepping source files.

### 9.5. `@Configuration(proxyBeanMethods=false)` Is Not a Method-Security Toggle

`proxyBeanMethods` on `@Configuration` governs proxying of `@Bean` factory methods inside configuration classes—it is **not** a switch for `@PreAuthorize` on service methods. Do not toggle it as a generic method-security workaround.

## 10. Wrong SpEL Can Look Like a Proxy Bug

Even when method security intercepts properly, the expression itself may not match business rules.

### 10.1. `hasRole` vs. `hasAuthority`

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void adminAction() {
    // ...
}
~~~

`hasRole('ADMIN')` checks `ROLE_ADMIN` under the default role prefix. `hasAuthority('ADMIN')` checks the **exact string** `ADMIN`. If a JWT system emits only `SCOPE_reports.read` while you write `hasRole('ADMIN')`, requests will be denied unless an authority converter/policy grants that role.

A wrong expression normally causes **over-denial** (403), not a bypass like self-invocation. Even so, always inspect actual authorities when analyzing tests.

### 10.2. Parameter Names in SpEL

~~~java
@PreAuthorize("#accountId == authentication.name")
public String readMyData(String accountId) {
    return accountId;
}
~~~

This is a fragment. To resolve `#accountId` by parameter name, the compiler/runtime needs matching metadata or annotations. In Java, configure `-parameters` in the build. Without that metadata, the expression can evaluate differently or fail; check parameter-name discovery in your version.

Options include:
- adding `-parameters` in Maven/Gradle compiler configuration;
- using `@P` for parameter names where supported;
- using positional parameters like `#p0` per method-security SpEL contracts;
- writing an explicit authorization service with clear unit/integration tests.

**Never take actor identity from a client-supplied `accountId` without verifying it against `Authentication`.** Ownership checks must validate the real user, tenant, and permissions—having an annotation alone is not enough.

### 10.3. User/Service Calls an Internal Protected Helper Method

Even a properly written `@PreAuthorize("@permissionService.canEdit(authentication,#id)")` **will not run** if the protected method is called through `this`. Always inspect the **call graph/proxy path** before spending time tweaking SpEL.

### 10.4. `@PreAuthorize` Does Not Protect Every Code Path

If the same business action can be reached from:
- a REST Controller;
- a scheduled job;
- a message listener;
- a batch task;
- another service;
- or the service calling itself;

verify which entry points go through the proxy and whether background jobs carry an appropriate `Authentication`. In jobs lacking an end-user security context, `hasRole` policies can deny or throw. Never blindly impersonate a `SYSTEM` admin in every job; design explicit permissions for service principals/system tasks.

## 11. `SecurityFilterChain` and Method Security Are Two Distinct Layers

Example:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

This only requires login at the URL layer; it never guarantees “only `ADMIN` can invoke every service”. With proper method protection, a `USER` passes the HTTP layer and is then denied at the service with 403.

~~~text
GET /api/direct with ROLE_USER
    |
    +-- HTTP Basic authentication -> SUCCESS
    |
    +-- URL authorization authenticated() -> ALLOW
    |
    +-- Method security hasRole('ADMIN') -> DENY
    |
    v
HTTP 403
~~~

With self-invocation:

~~~text
GET /api/unsafe with ROLE_USER
    |
    +-- HTTP Basic authentication -> SUCCESS
    |
    +-- URL authorization authenticated() -> ALLOW
    |
    +-- Public outer service method -> ALLOW (no rule)
    |
    +-- target.this.privilegedAction() -> BYPASSES proxy
    |
    v
HTTP 200 in demo (BUG)
~~~

**Never add `.permitAll()` to “fix” a 403 from method security.** And never treat `.authenticated()` as sufficient for object-level authorization. Place security rules at the boundary matching your data and domain logic.

## 12. Fixes: What to Prefer and What to Avoid

### 12.1. Preferred: Separate Beans with Clear Authorization Boundaries

Extract `SensitiveOperationService` with the protected method, and have workflows call it via a Spring-managed dependency. Write tests for both permitted and denied callers, including users lacking privileges.

### 12.2. When Only One Entry Point Exists: Protect the Outer Method

You can place the policy on the public outer method:

~~~java
@PreAuthorize("hasRole('MANAGER')")
public void approveAndPublish() {
    approveInternal();
    publishInternal();
}
~~~

This is a **fragment**, safe only if **every call path** enters through that proxied public outer method and the policy covers the entire execution. If inner methods are called directly elsewhere or carry stronger policies, reconsider. Do not treat this as a catch-all pattern for large services.

### 12.3. Explicit Authorization Service When Appropriate

For sensitive business operations, you can invoke explicit checks in the application/service layer—such as `AuthorizationService.requirePermission(actor, resource)` immediately before side effects. This reduces reliance on AOP in hard-to-proxy flows, yet your code must cover **every call site** and include tests. **Never** trust a client-supplied actor as authenticated.

### 12.4. Self-Injection / `AopContext` Is a Workaround, Not the Default

Some patterns obtain the bean's own proxy via `ObjectProvider`, self-injection, or `AopContext.currentProxy()`. These may require `exposeProxy=true`, creating AOP coupling, circular-dependency risks, and harder-to-reason-about lifecycles.

Do not recommend these as the primary fix for `@PreAuthorize` in business applications. **Refactoring into two beans with clean boundaries** is simpler, easier to test, and avoids leaking raw target references.

### 12.5. AspectJ Weaving Is an Architectural Alternative

Spring supports weaving models beyond Spring AOP proxies, yet they require **specific modules, plugins, JVM/instrumentation, and configuration**. AspectJ can intercept self-invocations differently from proxy-based AOP depending on weaving mode, yet is not enabled by `@EnableMethodSecurity` alone.

Do not adopt AspectJ solely as a “quick fix” for one class; weigh build/deploy complexity, performance, compatibility, and full test coverage. Unless a clear technical driver exists, separating service beans carries far lower risk.

## 13. `@Transactional`, `@Async`, and Multiple Advice Layers

Self-invocation affects many Spring AOP features alike.

### 13.1. `@Transactional`

If method A in a service calls `this.methodB()` where `methodB` carries `@Transactional`, transaction advice on B may not apply—often mistaken for database or JPA flush bugs. When `@PreAuthorize` and `@Transactional` sit on the same method, **both require proxy traversal** and may execute in different orders depending on configuration. Never assume authorization always runs before a transaction opens unless you have verified advisor ordering explicitly.

### 13.2. `@Async`

An `@Async` method called via `this.asyncMethod()` can execute synchronously because advice is bypassed. When it truly runs on another executor, `ThreadLocal`-backed `SecurityContextHolder` may not propagate automatically; method security may see a different `Authentication` or `null`.

Separate two questions:
1. **Proxy entry:** did the advice trigger?
2. **Authentication propagation:** once running on another thread, is the right security context present?

Spring Security provides wrappers such as `DelegatingSecurityContextExecutor` alongside integration for specific Spring MVC async modes. Never propagate all security contexts to background jobs blindly via `InheritableThreadLocal`.

### 13.3. `@Cacheable`

If cache advice on a protected method is bypassed by self-invocation, results are not cached as expected. Worse, if policy and caching interact poorly, cache keys can leak data across users or tenants. Always design explicit cache keys and authorization checks rather than relying on proxies as your sole isolation boundary.

## 14. HTTP 401, 403, 500, and Exception Handling

`@PreAuthorize` executes before the target method (when intercepted properly) and can throw an access-denial exception. Inside a Servlet request traversing Spring Security filters, `ExceptionTranslationFilter` and related components map exceptions by context into 401/403/redirect responses.

| Outcome | Common Explanation | How to Verify |
| --- | --- | --- |
| **401** | Missing or invalid HTTP authentication (under Basic entry point). | Inspect HTTP auth filter, headers, and provider. |
| **302** | App uses form login and redirects to the login page. | Inspect entry point, `Accept` header, and saved request. |
| **403** | Authenticated yet lacking authority/permission, or CSRF denial. | Distinguish method denial from CSRF/filter denial. |
| **Unexpected 200** | Rule not applied, self-invocation, unproxied method, or user actually holds privilege. | Test a lower-privilege role and inspect the call graph. |
| **500** | Broken expression, bean/proxy conflict, mis-mapped exception handler, or app bug. | Inspect sanitized exception type and stack trace. |

**Note:** 403 does not automatically come from `@PreAuthorize`: CSRF and URL authorization can also return 403. Likewise, HTTP 200 alone does not prove the service method actually ran; assert response content and side effects in tests.

### How `@ControllerAdvice` Can Mask Failures

A global handler catching broad `Exception.class` or `RuntimeException.class` can turn `AccessDeniedException` into an off-contract HTTP 200, 400, or 500. Never “fix” this by swallowing denials; let Spring Security handle them or map exceptions properly without leaking internals.

In service unit tests that do not run Servlet filters, `AccessDeniedException` is thrown directly. Do not expect it to produce an HTTP response without a web request.

## 15. Debug Logging and Method-Security Observability

In development environments, you can temporarily enable logs:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.aop: DEBUG
~~~

Or raise to scoped `TRACE` in an isolated environment to see filter/advisor details. High log levels incur overhead and can expose authentication/configuration details; **never leave them on long-term in production**, and never dump passwords, JWTs, `Authorization` headers, session cookies, or raw principals.

### What to Observe

1. Did `ApplicationContext` load the `@EnableMethodSecurity` configuration?
2. Is the invoked bean a Spring AOP proxy—JDK or CGLIB?
3. Does the external call site invoke the bean reference or `this.method()`?
4. Is the protected method `public`/non-final? Are there overrides or overloads?
5. Which authorities does `Authentication` actually hold? Are role prefixes right?
6. When denied, where was the exception thrown and who converted it to an HTTP status?
7. Do tests load the right context and security filters?
8. Does the bug happen only from a specific entry point, thread, or background job?

For auditing method denials, use supported authorization observability/events per your version and app policy. **Never log tokens or full `Authentication` objects** just to check roles; log only normalized class/principal IDs where permitted and bounded reason codes.

## 16. Checklist Matrix for Fast Fault Isolation

| Question | If “No” or Wrong | Action |
| --- | --- | --- |
| Does the project load `@EnableMethodSecurity`? | No method-security advisors exist. | Move the annotation into a actually loaded Spring configuration. |
| Is the object a Spring bean? | `new Target()` has no proxy. | Inject the bean from `ApplicationContext`. |
| Is the bean reference an AOP proxy? | Missing proxy or non-matching advisor. | Check `AopUtils.isAopProxy`, config, and annotations. |
| Does the caller go through the proxy? | `this.method()` bypasses inner advice. | Extract bean and call via injected dependency. |
| Is the method interceptable? | `private`/`final`/`final` class/wrong visibility. | Use a public non-final entry point and check proxy strategy. |
| Is the actual role right? | `ROLE_ADMIN` vs. `ADMIN`/`SCOPE_*`. | Check authorities, expressions, and converters. |
| Do SpEL parameter names resolve? | Missing `-parameters` or wrong property. | Check build metadata or use `#p0`/`@P` where suitable. |
| Do tests run security infrastructure? | `@WebMvcTest` missing beans or unit test calling `new`. | Use `@SpringBootTest` / configured Spring test context. |
| Is it the right target method/overload? | Annotation sits on another method. | Find actual call site and test behavior. |
| Was the exception altered? | 200/500 despite method denial. | Inspect `@ControllerAdvice` and exception translation. |
| Are there multiple chains/contexts? | Different HTTP code path than expected. | Test chain matchers, bean instances, and config profiles. |
| Is an async thread involved? | `SecurityContext` was not propagated. | Add explicit context propagation and thread tests. |

### Optimal Investigation Order

**Step 1:** Reproduce with two identities—`USER` and `ADMIN`—through the same HTTP endpoint, not just one mock test.

**Step 2:** Confirm `@EnableMethodSecurity` is active and the injected bean is a proxy.

**Step 3:** Inspect entry points and call graphs for internal `this.` calls. When present, this is usually the fastest path to a fix.

**Step 4:** Inspect method visibility, `final` modifiers, and proxy type. Never flip proxy modes before identifying the root issue.

**Step 5:** Inspect SpEL expressions, authorities, parameter names, and policy config.

**Step 6:** Inspect exception and status conversion, especially with custom controllers or global exception handlers.

**Step 7:** After fixing, add negative tests for **every public/business entry point** that can reach the sensitive operation, not only the annotated method directly.

## 17. Dangerous Anti-Patterns to Spot

### 17.1. Annotating Only an Inner “Sensitive” Method

~~~java
public void checkout() {
    this.commitPayment();
}

@PreAuthorize("hasRole('PAYMENT_ADMIN')")
public void commitPayment() {
    // Side effect.
}
~~~

If `checkout()` is called through the proxy without an equivalent policy, `commitPayment()` can execute without authorization advice running. Even though the role policy sits on the inner method, the real flow is unprotected.

**Fix:** extract `PaymentCommitService` with a protected method, or enforce permissions at the public boundary before side effects, paired with idempotency, ownership, and transaction policies.

### 17.2. Relying on `@PreAuthorize` Against IDOR with Client-Supplied IDs

~~~java
@PreAuthorize("isAuthenticated()")
public Order loadOrder(UUID orderId) {
    return repository.getReferenceById(orderId);
}
~~~

This fragment does not protect ownership; any logged-in user can probe another user's `orderId`. For object-level access control, expressions/services must check **actor, tenant, and target object**. Proxies only enforce the policy you write—they cannot fix an overly weak policy.

### 17.3. Testing Only with Over-Privileged Users

A test suite using only `ADMIN` cannot detect if `@PreAuthorize` disappears: both before and after succeed. Always write negative tests with `USER` and anonymous callers, plus a path that previously risked self-invocation bypass.

### 17.4. Catching `AccessDeniedException` and Returning Success

~~~java
try {
    service.privilegedAction();
} catch (AccessDeniedException ex) {
    return successFallback();
}
~~~

This anti-pattern swallows denials and turns authorization failures into logic bypasses. To handle errors properly, return a failure response or propagate the exception; never run alternative side effects that the policy was meant to block.

### 17.5. Invoking Method-Security-Annotated Methods via Reflection

Attaching `@PreAuthorize` and then invoking the target method via reflection can also bypass proxies. Reflection does not automatically trigger Spring advisors. If dynamic invocation is needed, invoke through the bean proxy using supported APIs and test each path explicitly.

## 18. Self-Check Questions and Answers

**Q1. Why does `@PreAuthorize` on `deleteInvoice()` not run when `createInvoice()` calls `this.deleteInvoice()`?**

Because Spring AOP proxies intercept at the proxy boundary. `this.deleteInvoice()` runs directly on the target without crossing the proxy, so method-security advice on the inner method is not invoked.

**Q2. Does changing `@EnableMethodSecurity(proxyTargetClass=true)` fix self-invocation?**

No. Both class-based proxies and JDK dynamic proxies share the self-invocation limitation under Spring AOP's proxy model. You must change the call graph or weaving model, not just the proxy type.

**Q3. Spring Security Basic works, yet `@PreAuthorize` does not run. What could be wrong?**

Web security and method security are two separate layers. `@EnableMethodSecurity` may be missing, the bean/proxy may be misconfigured, or calls may be internal. Basic authentication succeeding does not prove method security is active.

**Q4. Does `AopUtils.isAopProxy(service) == true` guarantee every method annotation runs?**

No. The proxy may exist for another advisor, or the protected method may be called without crossing the proxy. You still need deny/allow tests at the actual entry point and verification of advisor/annotation placement.

**Q5. With `hasRole('ADMIN')`, which authority is expected by default?**

Typically `ROLE_ADMIN`. With `hasAuthority('ADMIN')`, the exact string `ADMIN` is expected. JWT scopes normally map to `SCOPE_*` under the default converter, not automatically `ROLE_ADMIN`.

**Q6. What is the simplest fix if `WorkflowService` calls a sensitive method inside the same class?**

Move the sensitive operation into a separate Spring-managed service bean and inject it into `WorkflowService`, routing the call through the Spring proxy.

**Q7. Does `new SensitiveService().privilegedAction()` in a unit test return 200 or throw an exception?**

It is a plain Java call with no HTTP and no proxy; it runs the method body and returns the result. You cannot infer anything about real application method-security integration from it.

**Q8. Is HTTP 403 enough to prove `@PreAuthorize` is working?**

Not yet. 403 can come from URL authorization, CSRF, a reverse proxy, or another business rule. Test the method boundary and verify the exact exception/code path.

**Q9. If `@PreAuthorize` runs inside an `@Async` worker without an `Authentication`, did the proxy break?**

Not necessarily. Proxy advice may have executed while `SecurityContext` failed to propagate to the worker thread. Separate proxy interception from security context propagation.

**Q10. Should an “unsafe” endpoint like the demo's be kept in production to monitor proxies?**

No. `/api/unsafe` is purely a lesson reproducing a vulnerability. Once fixed, delete unsafe paths, enforce consistent authorization boundaries, and write negative tests for every path to sensitive operations.

## 19. Hands-On Exercises

1. **Disable `@EnableMethodSecurity` in the demo and run tests.** Observe `directCallDeniesNonAdmin` and `refactoredCrossBeanCallDeniesNonAdmin` no longer denying properly. Explain why HTTP `authenticated()` still lets `ROLE_USER` through the URL layer.
2. **Keep the annotation and test self-invocation.** Observe `internalThisCallDemonstratesBypass` returning 200 for `alice`. Draw the call graph pinpointing where the proxy was bypassed.
3. **Separate beans.** Move the privileged method to a dedicated service. Write tests verifying `USER` gets 403 and `ADMIN` gets 200 through both direct and orchestration paths; delete the intentional bypass endpoint completely.
4. **Make the method `final`.** Mark the protected method `final` under class-based proxying. Document the proxy limitation and why the framework cannot override it; never deploy such experiments to production.
5. **Add `hasAuthority`.** Use `@PreAuthorize("hasAuthority('SCOPE_orders.read')")` on a new method. Create principals with and without that scope and verify allow/deny. Never confuse `SCOPE_orders.read` with `ROLE_ADMIN`.
6. **Test missing parameter metadata.** Write an expression using `#accountId`; toggle the `-parameters` build option in a test environment. Observe how Spring Security resolves parameter names vs. using `#p0`.
7. **Create an HTTP access test.** Assert 401 without Basic credentials, 403 when `alice` invokes the protected method via the proxy, and 200 when `admin` calls it; never conflate authentication with method authorization.
8. **Extend to object permissions.** Create `OrderAuthorizationService.canView(Authentication, UUID)` and an enforcement annotation. Verify an actor in tenant A cannot read tenant B's object even when knowing its object ID.
9. **Audit multiple entry points.** If a service is invoked from REST, a scheduler, and a message consumer, tabulate the context/proxy path for each entry point; allow the operation only where policy is enforced consistently.
10. **Write a regression test.** After fixing self-invocation, keep at least one negative integration test proving `USER` **cannot** complete the operation via any public method that can reach it.

## 20. Final Checklist Before Closing the Issue

- [ ] Confirmed `@EnableMethodSecurity` is on a configuration class actually loaded.
- [ ] The service carrying `@PreAuthorize` is a Spring-managed bean, never instantiated with `new`.
- [ ] The method is interceptable under the proxy strategy, avoiding `private`/`final`/un-proxiable self-invocation.
- [ ] Every key caller invokes through the Spring proxy, never `this.method()` on the target.
- [ ] When beans are separated, the dependency is Spring-injected, not a raw target reference.
- [ ] Expressions match role prefixes, authorities, SpEL parameter names, and business permissions.
- [ ] HTTP `SecurityFilterChain` and method security enforce clear layered policies.
- [ ] Test contexts load method-security infrastructure and the right authentication mechanism.
- [ ] Tests verify `USER` is denied and `ADMIN` is permitted at the service boundary.
- [ ] Negative tests cover every major business entry point, not only direct method calls.
- [ ] Avoided abusing `AopContext`/self-injection merely to hide poor service structure.
- [ ] Avoided blindly changing proxy modes or disabling authorization to make tests pass.
- [ ] Never log credentials, full principals, or tokens when debugging method-security issues.
- [ ] Removed any intentional bypass endpoints from real environments.
- [ ] For async/background tasks, security context and system principal policies are explicit.
- [ ] For object authorization, tenant/ownership/target checks run rather than broad roles alone.

**Conclusion:** When `@PreAuthorize` “does not run”, check **three questions in order**: (1) Is `@EnableMethodSecurity` active? (2) Does the target method have **an eligible Spring AOP proxy**? (3) **Did the specific call cross the proxy**, or was it `this.method()` on the target? Most diagnostic errors come from staring at the annotation while ignoring the call graph. The durable fix is **placing policy on a public service boundary and calling it through an injected bean**, then verifying with `USER`, `ADMIN`, and anonymous integration tests.