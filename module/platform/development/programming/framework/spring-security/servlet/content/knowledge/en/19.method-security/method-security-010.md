# Spring AOP Proxies, Self-Invocation, and Method Protection Limits in Spring Security Servlet

**Scope:** Java 17+, Spring Boot 3.x, Spring Security 6.x, and Servlet applications. This lesson belongs to **Method Security**. The focus is on how Spring AOP proxies activate <code>@PreAuthorize</code>, why internal <code>this.method()</code> calls can bypass the interceptor, limitations of JDK proxies/CGLIB, and how to fix, test, and review architecture so permissions are enforced consistently.

**Core message:** a method having a security annotation **does not mean** every Java call to that method is protected. With proxy-based method security, the interceptor only observes calls going through the Spring proxy. If code calls the target directly, especially an internal call via <code>this</code>, the permission check may not run.

## 1. Method Security and HTTP Security Do Not Replace Each Other

Spring Security has multiple authorization layers:

| Layer | Mechanism | Role |
| --- | --- | --- |
| HTTP | <code>SecurityFilterChain</code>, <code>authorizeHttpRequests</code> | Blocks requests by URL, HTTP method, authentication state, or coarse role |
| Method | <code>@PreAuthorize</code>, <code>@PostAuthorize</code>, method interceptors | Protects invoking operations/services by authority or policy |
| Policy | Bean deciding permissions on action/resource | Evaluates owner, tenant, data, state |
| Persistence | Query scope, transaction, version, constraint | Prevents operations from touching out-of-scope data, avoids TOCTOU |

Example service method:

~~~java
@PreAuthorize("hasAuthority('report:export')")
public String exportRestrictedData() {
    return "confidential-report";
}
~~~

When a call **passes through a Spring proxy configured for method security**, a user lacking <code>report:export</code> is denied before the method runs. Yet merely seeing the annotation in source code is insufficient to know whether every call path goes through the proxy.

A URL protected with <code>authenticated()</code> only requires an authenticated identity. Someone with <code>report:read</code> does not automatically hold <code>report:export</code>. Conversely, method security does not replace CSRF, login/logout, sessions, entry points, CORS, and Servlet-layer checks.

## 2. Spring AOP Proxies Sit in Front of the Target Bean

Spring can wrap a business object in a proxy to run additional advice/interceptors. Another bean injecting the dependency typically receives the container-managed proxy instead of instantiating the target object itself.

~~~text
Controller or OtherService
           |
           v
      Spring proxy
           |
       Method interceptor
       @PreAuthorize
          / \
       deny  allow
        |      |
        v      v
       403   Target service method
                 |
                 v
             Business logic
~~~

The <code>Proxy</code> receives calls to public service methods, lets the method-security interceptor evaluate <code>Authentication</code> and authorities, and forwards to the target when allowed. When denied, an <code>AccessDeniedException</code> (or subclass) is typically thrown and translated into an appropriate response by the web security layer.

This is **interception**, not the JVM understanding <code>@PreAuthorize</code> as an <code>if</code> statement running on every method call. A proxy is not a sandbox stopping internal code from accessing repositories or real objects directly.

### Enabling Method Security

In Spring Security 6, the common configuration is:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

When applied, <code>@EnableMethodSecurity</code> registers method-authorization infrastructure for enabled annotations; <code>@PreAuthorize</code>/<code>@PostAuthorize</code> are supported in standard configurations. Without appropriate method-security configuration, annotations can exist in source without any interceptor.

Do not treat successfully importing an annotation as proof the method is protected; run tests on a Spring-managed bean in a real application context.

## 3. Self-Invocation: Internal Calls Do Not Go Through the Proxy

Example of an intentionally flawed service:

~~~java
@Service
public class UnsafeReportService {

    public String runInsecureWorkflow() {
        return this.exportRestrictedData();
    }

    @PreAuthorize("hasAuthority('report:export')")
    public String exportRestrictedData() {
        return "confidential:2026";
    }
}
~~~

Suppose a user only has <code>report:read</code>. If a caller invokes <code>unsafeReportService.exportRestrictedData()</code> through the Spring proxy, the method-security interceptor sees <code>@PreAuthorize</code> and denies it.

Yet when a caller invokes <code>unsafeReportService.runInsecureWorkflow()</code>:
1. The proxy receives the <code>runInsecureWorkflow()</code> call.
2. The outer method has no authorization rule of its own, so the proxy delegates to the target.
3. The target calls <code>this.exportRestrictedData()</code> **on the target object itself**.
4. The inner call does not go back through the proxy, so the interceptor attached to the inner method is not triggered.
5. The <code>exportRestrictedData()</code> logic executes even though the user lacks the export authority.

~~~text
Caller               Spring proxy                 Target UnsafeReportService
  |                        |                                 |
  | runInsecureWorkflow()  |                                 |
  |----------------------->|                                 |
  |                        | runInsecureWorkflow()           |
  |                        |-------------------------------->|
  |                        |                                 |
  |                        |       this.exportRestrictedData()
  |                        |       (bypasses proxy)          |
  |                        |                                 |
  |<-----------------------|<--------------------------------|
  |       confidential:2026                                 |
~~~

**This is a real security vulnerability if the outer method is an accessible entry point.** Learners need to understand this mechanism rather than slapping annotations on inner methods and assuming every call is protected.

In the hands-on project below, <code>UnsafeReportService</code> exists solely to test and demonstrate the bypass; it is **never wired into the HTTP Controller**.

## 4. Difference Between Proxy Calls and `this` Calls

Two paths:

~~~text
SAFE PATH (cross-bean)
Controller
   |
   v
ReportWorkflowService.runExport()
   |
   v
ReportExportService proxy.exportRestrictedData()
   |
   +--> @PreAuthorize("hasAuthority('report:export')")
           |
           +-- Deny -> stop
           +-- Allow -> target exportRestrictedData()


UNSAFE PATH (self-invocation)
UnsafeReportService proxy.runInsecureWorkflow()
   |
   v
Target.runInsecureWorkflow()
   |
   v
this.exportRestrictedData() on target
   |
   v
Skips exportRestrictedData() interceptor
~~~

An easy-to-audit fix is **extracting high-privilege operations into a separate Spring bean** and having the workflow inject that bean. Every time the workflow calls the injected bean, the call goes through the proxy and the interceptor can deny it.

You can also place <code>@PreAuthorize</code> on the **public entrypoint** <code>runInsecureWorkflow()</code> if the entire workflow requires the same permission. However, ensure every other entrypoint to the operation remains protected; patching only one URL or outer method can leave new callers unprotected.

When policies require conditions on documents, owners, or tenants, they can be evaluated explicitly in a domain service/use case. What matters is not "must use AOP", but that **every execution path to a sensitive action has a mandatory check point**.

## 5. JDK Dynamic Proxies and CGLIB Proxies

Spring AOP has two common proxy types:

| Characteristic | JDK dynamic proxy | CGLIB/class-based proxy |
| --- | --- | --- |
| Mechanism | Proxy implements interfaces | Proxy subclasses the target class |
| API callers normally use | Interface | Class or interface |
| Limitation | Concrete-only methods are absent from interface proxy | Final classes cannot be subclassed, final methods cannot be overridden |
| <code>this.inner()</code> calls | Still bypasses proxy | Still bypasses proxy |
| How selected | Depends on interfaces and proxy strategy | Can configure <code>proxyTargetClass=true</code> |

Do not claim every Spring Boot app always uses one proxy type. Proxy creation depends on Spring AOP settings, method-security infrastructure, and bean structure.

When class-based proxies are needed:

~~~java
@Configuration
@EnableMethodSecurity(proxyTargetClass = true)
public class MethodSecurityConfiguration {
}
~~~

This **does not fix self-invocation**, does not make private or static methods intercepted, and cannot let CGLIB override final methods. If a project uses JDK proxies, callers should typically inject via the matching interface; injecting only the concrete implementation can cause type/proxy errors.

You can inspect beans in tests:

~~~java
assertThat(AopUtils.isAopProxy(reportExportService)).isTrue();
// When needed: AopUtils.isJdkDynamicProxy(bean)
// or AopUtils.isCglibProxy(bean).
~~~

<code>AopUtils</code> comes from Spring AOP; checking proxy types helps diagnose configuration, **yet a bean being a proxy does not guarantee every call path is protected**.

## 6. Cases Where Method-Security Interception Has Limits

**Private methods:** not part of the public service API callable via JDK proxies; internal calls to private methods must not be relied upon for mandatory policy enforcement.

**Final methods:** CGLIB cannot override final methods. With interface proxies, what matters is whether calls go through the interface/proxy; do not generalize one rule across all proxy strategies. When security interception is required, prefer tested public, non-final service operations.

**Final classes:** subclass-based class proxying cannot work on final classes; configurations requiring subclassing may fail at startup.

**Static methods:** not instance calls passing through a Spring bean proxy.

**Constructors / @PostConstruct:** while an object is still initializing, never assume a proxy is ready to intercept internal calls. Startup also usually lacks a user SecurityContext.

**Objects created with new:** manual constructors bypass the Spring container and bean post-processors; <code>@PreAuthorize</code> does not automatically become an interceptor on that object.

**Annotations on interfaces/implementations:** Spring Security has rules for finding annotation metadata, yet inheritance/multiple interfaces can create conflicts. Test the real proxy configuration rather than only reading annotations in source code.

**Multiple proxies/advices:** <code>@Transactional</code>, <code>@Async</code>, and custom AOP advices may apply at different layers, and advice ordering affects behavior. Never guess solely from annotation order in a Java file.

## 7. Hands-On Project Design

Using **Java 17+, Maven, Spring Boot 3.3.5, Spring Security 6.x**. The example defines two demo users: <code>reader</code> with <code>report:read</code>; <code>exporter</code> with both <code>report:read</code> and <code>report:export</code>.

HTTP Basic is chosen so 401/403/200 are easy to observe; hardcoded passwords are for localhost only. The public endpoint and export endpoint are exposed via the Controller. The unsafe class is registered as a Spring bean yet **not exposed over HTTP**; only tests use it to demonstrate the bypass.

~~~text
method-proxy-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/methodproxy/
    │   ├── MethodProxyApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── UnsafeReportService.java
    │   ├── ReportExportService.java
    │   ├── ReportWorkflowService.java
    │   └── ReportController.java
    └── test/java/com/example/methodproxy/
        └── MethodProxySecurityTest.java
~~~

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>method-proxy-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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

### 7.2. Application Class

Create <code>src/main/java/com/example/methodproxy/MethodProxyApplication.java</code>:

~~~java
package com.example.methodproxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodProxyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodProxyApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfiguration.java

Create <code>src/main/java/com/example/methodproxy/SecurityConfiguration.java</code>:

~~~java
package com.example.methodproxy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-local-123"))
                .authorities("report:read")
                .build(),
            User.withUsername("exporter")
                .password(encoder.encode("exporter-local-123"))
                .authorities("report:read", "report:export")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/reports/public").permitAll()
                .requestMatchers("/reports/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

<code>@EnableMethodSecurity</code> enables method-security advice. HTTP only requires authenticated for report URLs; detailed export permissions are enforced on the service method. <code>authorities("report:export")</code> uses the exact string, so the expression is <code>hasAuthority</code> rather than <code>hasRole</code> which automatically prepends <code>ROLE_</code>.

Demo passwords are hashed by the encoder; never hardcode credentials in production. CSRF is not disabled. If there are state-changing POST endpoints, evaluate CSRF for the browser/token model and never use GET for side effects merely for testing convenience.

### 7.4. UnsafeReportService.java — Intentionally Illustrating the Bug

Create <code>src/main/java/com/example/methodproxy/UnsafeReportService.java</code>:

~~~java
package com.example.methodproxy;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class UnsafeReportService {

    public String runInsecureWorkflow() {
        // INTENTIONALLY WRONG: calls this on target, bypassing the proxy.
        return this.exportRestrictedData();
    }

    @PreAuthorize("hasAuthority('report:export')")
    public String exportRestrictedData() {
        return "confidential:2026";
    }
}
~~~

If a caller bean invokes the proxy <code>unsafe.exportRestrictedData()</code>, the export rule is checked. Yet <code>unsafe.runInsecureWorkflow()</code> enters the target and <code>this.exportRestrictedData()</code> goes straight to the inner method, causing the rule on the inner method to be skipped. **Never expose this service on an HTTP endpoint** in a real application.

### 7.5. ReportExportService.java — Separate Protected Operation

Create <code>src/main/java/com/example/methodproxy/ReportExportService.java</code>:

~~~java
package com.example.methodproxy;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportExportService {

    @PreAuthorize("hasAuthority('report:export')")
    public String exportRestrictedData() {
        return "confidential:2026";
    }
}
~~~

This operation only runs through the proxy when callers use the Spring-managed bean. Without the matching authority, the interceptor denies before returning data. A real service still needs tenant, report ownership, and query-scope policies, not just a single authority check.

### 7.6. ReportWorkflowService.java — Calling Another Bean

Create <code>src/main/java/com/example/methodproxy/ReportWorkflowService.java</code>:

~~~java
package com.example.methodproxy;

import org.springframework.stereotype.Service;

@Service
public class ReportWorkflowService {

    private final ReportExportService exportService;

    public ReportWorkflowService(ReportExportService exportService) {
        this.exportService = exportService;
    }

    public String runExport() {
        // Calls the injected Spring bean, not this.exportRestrictedData().
        return exportService.exportRestrictedData();
    }
}
~~~

When the workflow is called, it delegates to **another Spring proxy**. This directly fixes the bypass cause in the demo. If a new caller invokes the export service, the operation itself still carries the policy. Yet if a developer injects the repository directly and bypasses the export service, architecture reviews and tests are still needed.

### 7.7. ReportController.java — Not Exposing the Unsafe Bean

Create <code>src/main/java/com/example/methodproxy/ReportController.java</code>:

~~~java
package com.example.methodproxy;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportWorkflowService workflow;

    public ReportController(ReportWorkflowService workflow) {
        this.workflow = workflow;
    }

    @GetMapping("/reports/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/reports/export")
    public String export() {
        return workflow.runExport();
    }
}
~~~

The controller contains no policy and does not inject <code>UnsafeReportService</code>. The GET endpoint returns simulated content; in a real product, exporting might create a job or modify resources, in which case you must choose the appropriate HTTP method/CSRF/rate limit/auditing and never turn a mutation into GET.

## 8. Testing with Spring Security Test and MockMvc

Create <code>src/test/java/com/example/methodproxy/MethodProxySecurityTest.java</code>:

~~~java
package com.example.methodproxy;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodProxySecurityTest {

    @Autowired
    UnsafeReportService unsafe;

    @Autowired
    ReportExportService exportService;

    @Autowired
    ReportWorkflowService workflow;

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "reader", authorities = {"report:read"})
    void selfInvocationBypassesInnerMethodInterceptor() {
        // Bean has a proxy yet internal call via this still bypasses it.
        assertThat(AopUtils.isAopProxy(unsafe)).isTrue();

        assertThatThrownBy(() -> unsafe.exportRestrictedData())
            .isInstanceOf(AccessDeniedException.class);

        // This proves the vulnerability, not recommended behavior.
        assertThat(unsafe.runInsecureWorkflow())
            .isEqualTo("confidential:2026");
    }

    @Test
    @WithMockUser(username = "reader", authorities = {"report:read"})
    void crossBeanInvocationEnforcesPolicy() {
        assertThat(AopUtils.isAopProxy(exportService)).isTrue();

        assertThatThrownBy(() -> workflow.runExport())
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "exporter",
        authorities = {"report:read", "report:export"})
    void exporterMayCallProtectedOperation() {
        assertThat(workflow.runExport()).isEqualTo("confidential:2026");
    }

    @Test
    void httpBoundaryAndMethodSecurityWorkTogether() throws Exception {
        mvc.perform(get("/reports/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/reports/export"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/reports/export")
                .with(httpBasic("reader", "reader-local-123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/reports/export")
                .with(httpBasic("exporter", "exporter-local-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("confidential:2026"));
    }
}
~~~

The test suite proves two very different behaviors:
- The unsafe bean has a proxy. Calling the annotated method directly from outside denies `reader`; yet the same `reader` calling the outer method and hitting <code>this.exportRestrictedData()</code> bypasses it.
- The safe export bean has a proxy; cross-bean calls from the workflow enforce the policy and `reader` is denied.
- `exporter` with the permission is allowed.
- MockMvc sends requests through both HTTP security and method security, producing the expected 200/401/403 statuses.

The test intentionally letting the unsafe method return the secret is a **vulnerability-detection test**. In production code, eliminate the bypass path, never expose the HTTP route, and never treat this test as "business success".

Use <code>@SpringBootTest</code> to actually load Spring-managed beans and method-security interceptors. A <code>@WebMvcTest</code> or a mocked service may not represent production's real proxy infrastructure; at least one integration test must exercise the real call path.

## 9. Running with Maven and Checking 401/403/200

In the directory containing `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

In another terminal:

~~~bash
# Anonymous can view public content.
curl -i http://localhost:8080/reports/public

# Anonymous lacks access to export.
curl -i http://localhost:8080/reports/export

# Reader is logged in yet lacks report:export.
curl -i -u reader:reader-local-123 http://localhost:8080/reports/export

# Exporter has report:export authority.
curl -i -u exporter:exporter-local-123 http://localhost:8080/reports/export
~~~

| Caller | HTTP authenticated() | Method @PreAuthorize | Expected Result |
| --- | --- | --- | --- |
| Anonymous GET /reports/public | permitAll | No export rule | 200, public |
| Anonymous GET /reports/export | Fails | Never reaches service | 401 (Basic) |
| Reader GET /reports/export | Passes | Lacks report:export | 403 |
| Exporter GET /reports/export | Passes | Has report:export | 200, confidential:2026 |

If `reader` receives 200 instead of 403, check <code>@EnableMethodSecurity</code>, whether the bean is proxied, whether the Controller -> Workflow -> ExportService path is wired properly, and whether the method is truly called through the proxy. Never apply a band-aid `if` check only in the Controller because the service can still be called by batch/message handlers.

The statuses above are expected outcomes for the illustrative config, **not results of a pre-run Maven execution**. The code is designed and statically checked; run it with JDK 17+/Maven to verify fully.

## 10. @PreAuthorize vs @PostAuthorize and Other Annotations

| Mechanism | When Checked | Notes |
| --- | --- | --- |
| <code>@PreAuthorize</code> | Before method call | Suitable for blocking sensitive actions before side effects |
| <code>@PostAuthorize</code> | After method runs | Can inspect returnObject, yet side effects may have occurred |
| <code>@PreFilter</code> | Before call, filters input collection | Fits specific cases; must understand mutability |
| <code>@PostFilter</code> | After call, filters returned collection | Does not replace query scoping for large datasets |
| <code>@Secured</code> | Based on role/authority list | Requires enabling support, e.g. <code>securedEnabled=true</code> |
| <code>@RolesAllowed</code> | JSR-250 role-based | Requires <code>jsr250Enabled=true</code> and needed dependency |

<code>@EnableMethodSecurity</code> enables pre/post annotations in standard configs; <code>@Secured</code> and JSR-250 must be explicitly enabled when used. Do not assume switching to a different annotation type fixes self-invocation: as long as enforcement relies on proxies, internal calls can still bypass it.

**Never use @PostAuthorize as the sole barrier for actions modifying system state.** A method may already have executed database UPDATEs, sent emails, or called external services before post-authorization denies. HTTP 403 at that point does not automatically roll back external side effects.

Example referencing a policy bean:

~~~java
@PreAuthorize("@documentPolicy.canEdit(authentication, #documentId)")
public void editDocument(@P("documentId") Long documentId, String content) {
    // Reached only after the policy allows.
}
~~~

This is an illustrative snippet, not a standalone runnable class. <code>documentPolicy</code> must be a bean with a matching `canEdit` method, and <code>@P</code> belongs to <code>org.springframework.security.access.method.P</code>. Use trusted server identity/tenant sources, never trusting an owner from the request body.

## 11. Self-Invocation Can Also Affect @Transactional and @Async

Spring's <code>@Transactional</code> typically relies on proxy-based advice. If method A calls <code>this.methodB()</code> where the transaction annotation is only on B, the internal call can skip transaction advice meant for B.

Similarly, <code>@Async</code> is typically applied via proxies; <code>this.asyncMethod()</code> may not dispatch work to an executor as expected.

Notably, a method carrying both <code>@PreAuthorize</code> and <code>@Transactional</code> or <code>@Async</code> can involve multiple interceptors/advices. Never guess when a transaction starts solely from annotation order. Test that permissions are denied **before** side effects, and that transactions/queries preserve data integrity under races.

### Async and SecurityContext

<code>SecurityContextHolder</code> is thread-bound by default. When code runs on another executor thread, it does not automatically inherit the HTTP request's Authentication. You can use <code>DelegatingSecurityContextRunnable</code>, <code>DelegatingSecurityContextCallable</code>, an appropriate executor wrapper, or pass a trusted identity and re-verify permissions at execution time.

Do not use <code>MODE_INHERITABLETHREADLOCAL</code> globally for thread pools due to risks of retaining stale/wrong identities. Never pass raw tokens/cookies in task payloads/logs. When a user's permissions are revoked while a job is still running, implement re-checking and cancellation/compensation policies.

### Transactions and TOCTOU

If owner/tenant permissions are checked at t1 yet data changes before an UPDATE at t2, an UPDATE lacking owner/tenant predicates can modify the wrong record (time-of-check to time-of-use). Use transaction isolation/locks, optimistic versioning, or conditional SQL:

~~~sql
UPDATE reports
SET content = :content
WHERE id = :reportId
  AND tenant_id = :trustedTenant
  AND owner_username = :authenticatedUsername
  AND status = 'EDITABLE';
~~~

Sensitive bind values must be server-verified; check the updated row count. This code is illustrative SQL, not a file in the demo project. Method security complements, yet **never replaces**, data-layer consistency.

## 12. Other Bypass Paths and How to Prevent Them

### Using new Instead of a Spring Bean

~~~java
ReportExportService direct = new ReportExportService();
direct.exportRestrictedData(); // No Spring proxy, no advice.
~~~

This snippet illustrates the hazard. There is no Spring AOP boundary when an object is instantiated manually outside the container.

### Calling Private/Final/Static Methods

An annotated private method is not a protected service entrypoint. With CGLIB, final methods cannot be subclass-overridden. With static methods, there is no instance-proxy call. Place policies on public API methods that callers genuinely invoke through Spring-managed proxies.

### Self-Injecting Your Own Bean or AopContext.currentProxy()

You may encounter workarounds like self-injecting the proxy or calling <code>AopContext.currentProxy()</code> with `exposeProxy` enabled. They couple code to Spring AOP, introduce circular dependencies, and complicate maintenance; in new systems, **prefer extracting protected operations into separate beans** or enforcing policies explicitly at public use cases.

### Interfaces and Annotation Inheritance

When using JDK dynamic proxies, callers may only see interface methods. With multiple interfaces, generic inheritance, and annotations split across interfaces and implementations, inspect which metadata Spring Security applies as intended. Avoid conflicting annotations and test the bean proxy directly.

### With Multiple SecurityFilterChains or Multiple Entry Points

Method security can protect a service even when invoked by a message consumer, GraphQL resolver, or scheduled job — **if the call goes through the proxy** with a proper authentication/policy context. Yet a new HTTP route calling a repository directly or a background job lacking context remains an unsafe path. Architecture reviews must audit every call path to sensitive actions.

## 13. How Should Owner/Tenant Method Security Be Designed?

An authority such as <code>report:export</code> only indicates a general capability. To decide whether a report belonging to a tenant may be exported, policies need tenant memberships and server-side resource metadata.

Example policy structure (not a standalone Java file in the demo project):

~~~java
@Component("reportPolicy")
public class ReportPolicy {
    private final ReportRepository reports;
    private final TenantDirectory tenants;

    public ReportPolicy(
            ReportRepository reports, TenantDirectory tenants) {
        this.reports = reports;
        this.tenants = tenants;
    }

    public boolean canExport(Authentication auth, Long reportId) {
        if (auth == null || !auth.isAuthenticated()) {
            return false;
        }

        boolean allowedAuthority = auth.getAuthorities().stream()
            .anyMatch(a -> "report:export".equals(a.getAuthority()));
        if (!allowedAuthority) {
            return false;
        }

        String trustedTenant = tenants.findTrustedTenant(auth.getName());
        return trustedTenant != null && reports.findById(reportId)
            .map(r -> trustedTenant.equals(r.tenantId()))
            .orElse(false);
    }
}
~~~

<code>ReportRepository</code>, <code>TenantDirectory</code>, and domain entities must be built to fit your real system; this is only an explanatory policy snippet. Never read a self-declared `tenantId` from HTTP headers as authority. If a user belongs to multiple tenants, verify membership for the selected tenant and specific action.

A service operation:

~~~java
@PreAuthorize("@reportPolicy.canExport(authentication, #reportId)")
public byte[] exportOne(@P("reportId") Long reportId) {
    // Once the policy allows, query the exact data scope.
    return new byte[0];
}
~~~

It still must be invoked through the proxy. If the service has a public workflow calling <code>this.exportOne()</code>, the method policy expression may not run. Extract the operation into another bean or protect the outer use case. Queries must also scope by tenant/owner before pagination/export; never fetch all documents and filter permissions afterward in Java.

## 14. Distinguish Proxies from the Business Authorization Model

A proxy only guarantees code interception via Spring AOP. It **does not inherently know** which document belongs to which account, which tenant is allowed, or whether access was revoked.

Clear separation:
- Authentication verifies the user, with authorities from a trusted origin.
- Policy centralizes owner/tenant/resource/action rules, defaulting to deny when data is missing.
- Method-security interceptors enforce calling the policy before the operation via the proxy.
- Services execute business logic.
- Repositories/transactions enforce data scoping and concurrency invariants.
- Controllers only handle HTTP and return DTOs, without duplicating rules into dozens of if/else blocks.

If a data-access class exposes public methods returning every record, method security on the service will not stop another developer from injecting the repository directly. Combine architecture tests, dependency boundaries, and code reviews to eliminate bypass paths.

## 15. What Testing Constitutes Sufficient Proof?

| Test Type | What It Proves | Limitation |
| --- | --- | --- |
| <code>AopUtils.isAopProxy(bean)</code> | The bean is currently an AOP proxy | Does not prove inner calls are intercepted |
| Direct secured method test | The proxy method rejects unauthorized users | Does not check outer workflows |
| Self-invocation demonstration | Outer calls can skip inner annotations | Production code must be fixed once identified |
| Cross-bean workflow test | Calls pass through the protected proxy | Does not replace tenant policies |
| MockMvc HTTP test | SecurityFilterChain + method security apply on requests | Does not simulate all background callers |
| Policy unit test | Owner/tenant/role matrix is accurate | Does not prove proxy wiring |
| Database/transaction test | Policy and updates/queries stay consistent | Needs production-like data/transactions |
| Async/security-context test | Identity propagates properly across executors | Does not prove permissions were not revoked |
| Architecture tests | No controller/adapter injects repositories indiscriminately | Does not replace runtime integration tests |

**Negative tests are vital.** Testing only that admin/exporter succeeds fails to catch low-privilege users calling workflows and bypassing protection. Test a user holding only <code>report:read</code> across *all public use cases* and across every call path.

<code>@WebMvcTest</code> may not initialize all real security interceptors/beans; have at least one <code>@SpringBootTest</code> or equivalent test context for real method security. Never mock the protected service in tests and conclude annotations work.

## 16. Common Pitfalls

| Pitfall / Symptom | Cause | Resolution |
| --- | --- | --- |
| @PreAuthorize present yet users can still call it | Self-invocation, method security disabled, or not using proxy | Check EnableMethodSecurity, bean, call path |
| AopUtils says bean is proxy yet inner call doesn't block | Proxy only sees outer method | Extract protected operation into separate bean |
| @Transactional on inner method has no effect | this.inner() skips transaction advice | Call through bean proxy, verify transactions |
| @Async runs synchronously | Self-invocation bypasses async advice | Cross-bean call or proper async infrastructure |
| Final class cannot be class-proxied | CGLIB cannot subclass final class | Design proxy-compatible services |
| Private @PreAuthorize method | Not an intercepted public bean API | Protect public operations |
| new Service() has annotation yet doesn't block | Not a Spring-managed bean | Inject container-managed bean |
| JDK proxy cannot be injected by concrete type | JDK proxy exposes interfaces | Inject interface or adjust proxy strategy |
| @PostAuthorize used for mutations | Side effects occur before denial | Pre-authorize and enforce transaction invariants |
| @WithMockUser admin tests always pass | No negative tests | Test reader/cross-tenant/anonymous |
| Web test mocks service, losing method interceptor | Slice/mock differs from production | Integration test real beans |
| HTTP authenticated() yet export leaks | Missing/bypassed method policy | Enforce on operation service |
| Async thread lacks Authentication | Context not propagated | Context wrappers or re-check permissions |
| A manager views another tenant | Checked role only | Tenant membership and query scoping |
| Policy checks then UPDATE writes wrong row | TOCTOU | Conditional updates, transactions/locks |
| Catching AccessDeniedException and returning default data | Swallows denial | Fail closed with appropriate status |

## 17. Pre-Production Checklist

1. <code>@EnableMethodSecurity</code> is enabled and tests prove <code>@PreAuthorize</code> is actually enforced by interceptors.
2. Protected operations are public methods on Spring-managed services invoked through proxies.
3. Never rely on <code>this.securedMethod()</code> for enforcement. Any sensitive self-invocation must be fixed or have explicit policy checks.
4. Choose proxy strategies fitting interfaces/classes; avoid final/private/static methods as mandatory policy points.
5. Controllers/batches/messages/GraphQL do not access sensitive repositories directly around enforced services.
6. Run both positive and negative tests, especially low-privilege users calling outer workflows.
7. HTTP authentication, CSRF, CORS, session policies, URL authorization, and method policies are all reviewed.
8. Resource policies use identities/tenants from verified sources; deny if resource/membership is invalid.
9. Verify transactions, races, optimistic versions, and query scoping when mutations or exports handle real data.
10. When using @Async, control context propagation, lifecycle, cancellation, and permission re-check timing.
11. Never use @PostAuthorize as a barrier before side effects.
12. When adding public service methods, HTTP routes, or schedulers, re-audit enforcement and call paths.
13. Audit denials/allows safely; never log credentials, session IDs, or unauthorized data.
14. After upgrading Spring Boot/Security or changing proxy settings, re-run method-security integration tests.

## 18. Self-Check Questions

**Question 1.** Why can <code>this.exportRestrictedData()</code> skip <code>@PreAuthorize</code>?  
**Answer:** It invokes the method directly on the target object, not back through the Spring AOP proxy. The inner method's interceptor is not triggered.

**Question 2.** Does enabling <code>@EnableMethodSecurity(proxyTargetClass=true)</code> automatically fix self-invocation?  
**Answer:** No. CGLIB changes the proxy strategy, yet inner method calls still happen on the target and can bypass the interceptor.

**Question 3.** Why is a bean being an AOP proxy insufficient to prove every method is safe?  
**Answer:** The proxy only intercepts calls passing through it. Internal calls, `new` objects, or direct data access can go around it.

**Question 4.** How does cross-bean invocation help?  
**Answer:** The workflow calls the protected operation through an injected Spring bean, so the proxy/interceptor checks authorities before the target runs.

**Question 5.** Why is @PostAuthorize unsuitable as the sole permission check before DELETE/UPDATE?  
**Answer:** Because it evaluates after the method runs, potentially after side effects that 403 cannot automatically undo.

**Question 6.** HTTP permits <code>authenticated()</code> while the method requires <code>report:export</code>. What does `reader` with <code>report:read</code> receive?  
**Answer:** `reader` passes coarse authentication yet is denied by method security, typically HTTP 403.

**Question 7.** Should you trust <code>@WithMockUser</code> in a slice test to conclude proxy interception is enabled in production?  
**Answer:** No. Test with real Spring beans and an application context containing the method-security infrastructure.

**Question 8.** Does an @Async job automatically use Authentication from the request thread?  
**Answer:** No. Explicit context propagation or re-verifying identity/permissions is required.

**Question 9.** Does holding the export authority mean a user can export every tenant?  
**Answer:** No. Membership/ownership and authorized data scope must be verified.

**Remember:** Spring Security method security in proxy mode is an **interceptor on calls through a Spring proxy**. Design protected operations in Spring beans genuinely called through proxies; never assume self-invocation is protected; use policy/service/data layers and integration tests to ensure no call path to a sensitive action lacks permission checks.
