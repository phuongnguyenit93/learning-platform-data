# Spring AOP Proxies and the Risk of Bypassing Checks via Self-Invocation

## 1. The Problem: Annotations Exist, Yet Authorization Never Runs

Spring Security lets you protect method calls with annotations such as **@PreAuthorize**, **@PostAuthorize**, **@Secured**, or **@RolesAllowed**. When using **@EnableMethodSecurity** in the default setup, these checks run through the **Spring AOP proxy** mechanism. This carries an important architectural limitation:

**Calls to a protected method passing through the Spring proxy can trigger authorization checks. Calls from one method to another inside the exact same object using this or implicit local calls do not pass through the proxy, and therefore do not trigger the called method's advice.**

Consider this scenario:

~~~java
@Service
class ReportService {

    public String readFromController() {
        return this.readSensitiveReport();
    }

    @PreAuthorize("hasAuthority('report:read')")
    public String readSensitiveReport() {
        return "confidential-report";
    }
}
~~~

This is an illustrative fragment, assuming @EnableMethodSecurity is enabled and the class is Spring-managed. If a controller calls **reportService.readSensitiveReport()** on the proxied bean, Spring Security can deny an unauthorized caller. Yet if the controller calls **reportService.readFromController()**, which then calls **this.readSensitiveReport()**, the **@PreAuthorize check on readSensitiveReport** is bypassed in standard proxy configurations.

This easily creates an **authorization vulnerability** if a method relies solely on an inner method's annotation to protect data. This is a general characteristic of Spring AOP proxies—also affecting @Transactional and @Cacheable—though this lesson focuses on its security impact for method security.

After this lesson, you will:
- Distinguish **proxy object**, **target object**, **advice**, and **method interceptor**.
- Understand why **self-invocation** bypasses protection on the called method.
- Recognize the symptom through HTTP **200/401/403** outcomes.
- Reorganize Spring beans so authorization runs reliably on every call path.
- Write tests verifying both direct proxy calls and indirect call paths.
- Distinguish self-invocation limits from **private/final method** issues, manually instantiated beans, and forgetting to enable method security.

## 2. How Method Security Works with Spring AOP

### 2.1. Enabling Method Security Is Not Default in Spring Boot Starter Security

Adding the **spring-boot-starter-security** dependency turns on Spring Boot's default HTTP security, yet **does not automatically enable annotation-level method security**. With Spring Security 6.x, the standard way to enable it is:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Or place **@EnableMethodSecurity** on another configuration class, including the main application class. In the default setup, this annotation activates interceptors for **@PreAuthorize**, **@PostAuthorize**, **@PreFilter**, and **@PostFilter**. Families like @Secured or JSR-250 require their corresponding opt-in flags when used.

**@EnableMethodSecurity** applies to Spring-managed objects in the ApplicationContext. If an object is created via **new ReportService()** outside the container, Spring has no opportunity to wrap it with a method-security proxy.

### 2.2. A Proxy Is the Object Other Beans Call

A bean containing protected methods can be wrapped by Spring with a proxy. Calls through the proxy are intercepted by Spring AOP and routed through interceptors. For @PreAuthorize, Spring Security uses a before-invocation interceptor to evaluate the authorization expression against the current Authentication.

~~~text
Controller / Other Service
         |
         | calls reportService.readSensitiveReport()
         v
Spring AOP proxy of ReportService
         |
         +--> Advisor / Method Security interceptor
         |         |
         |         +--> Reads @PreAuthorize
         |         +--> Gets Authentication from SecurityContext
         |         +--> Matches authority
         |         |
         |         +--> Lacks permission: denies (method does not run)
         |         +--> Authorized: forwards call to target method
         |
         v
ReportService target.readSensitiveReport()
         |
         v
Return value
~~~

**Advice** is extra behavior applied at a method invocation point. With @PreAuthorize, advice runs **before** the target method executes; with @PostAuthorize, it can check **after** the method returns. Spring Security 6.x implements this via AuthorizationManagers and method interceptors.

Calling through the proxy is the starting point of the check. Therefore, merely seeing an annotation in source code is **not enough** to conclude every call path is protected.

### 2.3. Why Is Self-Invocation Different?

~~~text
EXTERNAL: Controller -> proxy -> readSensitiveReport()
                                   |
                                   +--> @PreAuthorize executes

INTERNAL: Controller -> proxy -> readFromController()
                                     |
                                     v
                                  target.readFromController()
                                     |
                                     v
                                  this.readSensitiveReport()
                                     |
                                     +--> DOES NOT re-enter the proxy
                                     +--> DOES NOT run @PreAuthorize on target method
~~~

Once execution enters the **target object**, the **this** reference points to the executing target instance itself. Calling **this.readSensitiveReport()** or **readSensitiveReport()** inside the same class does not loop back out through the outer proxy. Thus Spring AOP has no hook to run the target method's interceptor.

Key distinctions:
- **It is not that @PreAuthorize stops working across the entire app.** External calls directly to the protected method are still blocked.
- **It is not that the user was implicitly granted permission.** The internal call path simply walks around where the check was placed.
- **Setting @EnableMethodSecurity(proxyTargetClass=true) does not fix this.** Subclass-based proxies share the same self-invocation limitation under Spring AOP's proxy model.
- **Not every self-invocation is a vulnerability.** Risk arises when a flow reaches sensitive data or operations without an equivalent check on reachable entry gates.

## 3. JDK Dynamic Proxies vs. Class-Based Proxies (CGLIB)

Spring AOP has two common proxy models:

| Feature | JDK dynamic proxy | Class-based proxy (CGLIB) |
| --- | --- | --- |
| Mechanism | Proxy implements interfaces | Proxy generates a subclass of the class |
| Typically used when | Bean has suitable interfaces and class proxy isn't forced | Bean lacks suitable interfaces, or config forces class proxies |
| Caller perspective | Usually injected by interface | Can be injected by concrete class type |
| Self-invocation impact | **Still skips advice** when target calls itself | **Still skips advice** when target calls itself |
| Notable limits | Only methods exposed on proxied interfaces pass through JDK proxy | Final classes and final/private methods cannot be subclass-overridden for advice |

You may encounter:
- **@EnableMethodSecurity(proxyTargetClass = true)** to request class-based proxies for method security in PROXY mode.
- Other global Spring Boot/Spring Framework proxy settings can affect which proxy type is created.
- **@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)** is a different mode, requiring corresponding AspectJ weaving setup; flipping the flag alone does not automatically protect internal calls.

**Key conclusion:** picking JDK proxies vs. CGLIB is not the fix for self-invocation. The standard fix is **structuring calls so sensitive methods are invoked from another bean through its proxy**, or placing checks on reachable entry points.

## 4. Complete Control Example in Spring Boot 3.x

Let's create three endpoints purely to observe the mechanism:

1. **/lab/direct**: calls the @PreAuthorize method directly through its proxy.
2. **/lab/self**: calls a public *unannotated* method, which internally invokes the annotated method.
3. **/lab/fixed**: calls a façade service, which invokes the @PreAuthorize method on **another bean**.

The /lab/** endpoints are **permitAll at the HTTP layer** so the effect of **method security** stands out clearly. In real applications, never leave sensitive routes relying on a misconfigured single layer.

### 4.1. Creating the Project

Use Spring Initializr to generate a Gradle project with:
- Java 17 or newer, Spring Boot **3.x**.
- Group **com.example**, artifact **demo**, package **com.example.demo**.
- Dependency **Spring Web** (spring-boot-starter-web).
- Dependency **Spring Security** (spring-boot-starter-security).

The main class name below is **MethodSecurityProxyDemoApplication**. Place all code in a single file:

**src/main/java/com/example/demo/MethodSecurityProxyDemoApplication.java**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class MethodSecurityProxyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityProxyDemoApplication.class, args);
    }
}

@Configuration
class HttpSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        // Demo: permitAll to highlight method security clearly.
                        .requestMatchers("/lab/**").permitAll()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails viewer = User.withUsername("viewer")
                .password("{noop}demo123")
                .roles("USER")
                .build();

        UserDetails reader = User.withUsername("reader")
                .password("{noop}demo123")
                .authorities("report:read")
                .build();

        return new InMemoryUserDetailsManager(viewer, reader);
    }
}

@Service
class VulnerableReportService {

    // When called from another bean through Spring proxy, this method is protected.
    @PreAuthorize("hasAuthority('report:read')")
    public String readProtectedReport() {
        return "sensitive-report";
    }

    // This method has no authorization check rule.
    public String readBySelfInvocation() {
        // Same target object: skips advice on readProtectedReport.
        return this.readProtectedReport();
    }
}

@Service
class ProtectedReportReader {

    // Protection point sits on a separate bean.
    @PreAuthorize("hasAuthority('report:read')")
    public String readProtectedReport() {
        return "sensitive-report";
    }
}

@Service
class SafeReportFacade {

    private final ProtectedReportReader protectedReader;

    SafeReportFacade(ProtectedReportReader protectedReader) {
        this.protectedReader = protectedReader;
    }

    public String readViaOtherBean() {
        // This call invokes the proxy of another bean.
        return protectedReader.readProtectedReport();
    }
}

@RestController
class LabController {

    private final VulnerableReportService vulnerableService;
    private final SafeReportFacade safeFacade;

    LabController(VulnerableReportService vulnerableService,
            SafeReportFacade safeFacade) {
        this.vulnerableService = vulnerableService;
        this.safeFacade = safeFacade;
    }

    @GetMapping("/lab/direct")
    String direct() {
        return vulnerableService.readProtectedReport();
    }

    @GetMapping("/lab/self")
    String self() {
        return vulnerableService.readBySelfInvocation();
    }

    @GetMapping("/lab/fixed")
    String fixed() {
        return safeFacade.readViaOtherBean();
    }
}
~~~

**Why does this code run in a single file?** Only MethodSecurityProxyDemoApplication is a public top-level class, matching the filename; the remaining classes are package-private yet picked up by Spring component scanning in the same package at startup. All protected methods are **public**, classes are non-final, and they are Spring beans eligible for proxying.

**No Service is instantiated manually with new** in this example. Spring injects dependencies via constructors, so the controller holds references to container-provided beans/proxies.

**{noop} passwords** are solely for local illustration; never use them in production. The demo uses GET only, so default CSRF does not block tests. Here, HTTP Basic is enabled so curl can send viewer/reader identities clearly.

### 4.2. Running and Sending Requests

In the root folder of the newly created project:

~~~bash
./gradlew bootRun
~~~

On Windows use **gradlew.bat bootRun**. While the app listens on default port **8080**, open another terminal:

~~~bash
# Unauthorized caller invokes protected method directly
curl -i -u viewer:demo123 http://localhost:8080/lab/direct

# Unauthorized caller goes through self-invoking method
curl -i -u viewer:demo123 http://localhost:8080/lab/self

# Unauthorized caller goes through fixed version calling another bean
curl -i -u viewer:demo123 http://localhost:8080/lab/fixed

# Caller holding report:read authority
curl -i -u reader:demo123 http://localhost:8080/lab/direct
curl -i -u reader:demo123 http://localhost:8080/lab/fixed

# No credentials sent: compare direct and self
curl -i http://localhost:8080/lab/direct
curl -i http://localhost:8080/lab/self
~~~

In PowerShell you may need to use **curl.exe** instead of **curl**.

### 4.3. Expected Results and Key Takeaways

| Request | Expected HTTP status | Success body | Reason |
| --- | --- | --- | --- |
| viewer -> GET /lab/direct | **403** | — | Called via proxy; viewer only has ROLE_USER, missing report:read. |
| viewer -> GET /lab/self | **200** | sensitive-report | Outer method unguarded; internal call bypasses @PreAuthorize. |
| viewer -> GET /lab/fixed | **403** | — | Facade calls ProtectedReportReader proxy; denied for missing permission. |
| reader -> GET /lab/direct | **200** | sensitive-report | Holds report:read; interceptor allows. |
| reader -> GET /lab/fixed | **200** | sensitive-report | Holds report:read and call goes through proxy. |
| anonymous -> GET /lab/direct | **401** with Basic | — | Method security denies; Basic entry point demands authentication. |
| anonymous -> GET /lab/self | **200** | sensitive-report | Self-invocation skips check, even without an identity. |

These are **expected outcomes from the example configuration**, not stdout or HTTP logs from a live execution. Headers and error response bodies depend on version/configuration, yet the contrast between the two call paths for an unauthorized user is the exact proof to observe.

**Why didn't permitAll disable @PreAuthorize?** permitAll at the URL layer lets requests reach the controller. When the controller invokes a protected method through its proxy, method security performs an independent check. **permitAll does not disable @PreAuthorize**; self-invoking inside the target object is what bypasses the interceptor.

**Why is this a security issue?** Unauthorized callers can access data developers thought was guarded behind @PreAuthorize. In the demo, "sensitive-report" is just a sample string containing no real data. In production systems, the exact same code pattern can expose internal records, export confidential reports, or trigger unauthorized state changes.

### 4.4. Does Switching to CGLIB Help?

No. Changing the configuration to:

~~~java
@EnableMethodSecurity(proxyTargetClass = true)
~~~

requests class-based proxies in PROXY mode, yet **readBySelfInvocation()** still calls **this.readProtectedReport()** on the target. Spring AOP does not route internal calls back through the proxy, so the advice on readProtectedReport still does not run.

The fix does not lie in choosing proxy types; it lies in the call path and where authorization checks sit.

## 5. The Clean Fix: Extracting the Protected Method to a Separate Bean

The recommended approach in ordinary code is separating responsibilities so the protected method has a **call path from another bean through the Spring proxy**:

~~~text
Controller
    |
    v
SafeReportFacade (Spring bean)
    |
    | protectedReader.readProtectedReport()
    v
ProtectedReportReader proxy
    |
    +--> @PreAuthorize("hasAuthority('report:read')")
              |
              +--> viewer / anonymous: denied
              +--> reader: allowed
    |
    v
ProtectedReportReader target
    |
    v
Report result
~~~

Key points of the refactoring:
1. **ProtectedReportReader** owns the sensitive method and authorization annotation.
2. **SafeReportFacade** merely orchestrates the flow, receiving **ProtectedReportReader via constructor injection**.
3. Callers never construct protectedReader with new; Spring supplies the proper bean (proxied wherever advisors apply).
4. Every consumer of the sensitive feature calls the protected public method through the injected bean, or enforces equivalent authorization at the entry gate.

That is why the example uses **SafeReportFacade** and **ProtectedReportReader** instead of one class calling across its own methods via this.

### 5.1. Can You Simply Add @PreAuthorize to the Outer Method?

Example:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public String readBySelfInvocation() {
    return this.readProtectedReport();
}
~~~

If an external caller invokes **readBySelfInvocation()** through the proxy, the outer method's interceptor requires report:read before entering. Along **that specific entry path**, the check works.

However, **the internal call to readProtectedReport() still skips readProtectedReport()'s own interceptor**. If a future developer adds another unguarded wrapper method or one requiring weaker rights, the vulnerability returns. Therefore, audit **all entry points**, rather than just slapping on an annotation to make one test pass.

### 5.2. Don't Break Your Design with Ad-Hoc Self-Injection

There are technical workarounds around this limitation:

- **Self-injection:** a bean holds a reference to its own proxy and calls through it, yet this invites circular dependencies, lifecycle coupling, and harder-to-follow code.
- **AopContext.currentProxy():** exposes the current proxy when exposeProxy is configured, yet couples business code directly to Spring AOP; Spring Framework docs discourage relying on it by default.
- **AspectJ compile-time/load-time weaving:** unlike proxy-based AOP, it can intercept internal calls because advice is woven into bytecode; in return it adds build config, tooling, and testing requirements.

In most business services, **splitting out a dedicated protected bean** or **placing checks at explicit entry points** is clearer, easier to test, and less coupled to proxy mechanics.

## 6. Regression Testing: Catching Bypasses, Not Just Checking Annotations

Testing only that **viewer calling /lab/direct gets 403** is insufficient: /lab/self might still be leaking sensitive data. Tests must cover **every real call path to an operation**, especially orchestration methods in the same class.

### 6.1. Integration Testing with MockMvc

Add test dependencies if your project lacks them (Gradle Groovy DSL):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is a fragment inside **build.gradle**, not a complete build.gradle; avoid duplicating dependencies already generated by Spring Initializr. Create file:

**src/test/java/com/example/demo/MethodSecurityProxyDemoTest.java**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityProxyDemoTest {

    @Autowired
    MockMvc mvc;

    @Test
    void directCallRejectsUserWithoutAuthority() throws Exception {
        mvc.perform(get("/lab/direct")
                    .with(httpBasic("viewer", "demo123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void internalSelfCallShowsTheBypass() throws Exception {
        mvc.perform(get("/lab/self")
                    .with(httpBasic("viewer", "demo123")))
                .andExpect(status().isOk())
                .andExpect(content().string("sensitive-report"));
    }

    @Test
    void refactoredCrossBeanCallRejectsUserWithoutAuthority()
            throws Exception {
        mvc.perform(get("/lab/fixed")
                    .with(httpBasic("viewer", "demo123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void refactoredCrossBeanCallAllowsReader() throws Exception {
        mvc.perform(get("/lab/fixed")
                    .with(httpBasic("reader", "demo123")))
                .andExpect(status().isOk())
                .andExpect(content().string("sensitive-report"));
    }
}
~~~

**Run tests** from the project directory:

~~~bash
./gradlew test
~~~

On Windows use **gradlew.bat test**. With Java 17+ and compatible Spring Boot and Security versions, the four tests demonstrate the lesson's expected states.

**The second test deliberately asserts an insecure behavior** to prove the bug. When fixing production code, never keep such a test as a "passing product criterion." Change the expectation to 403/401 per policy once the entry point is secured, or remove the unsafe endpoint and test all valid entry points. Functional tests have value only when expectations reflect security policy.

### 6.2. Test the Injected Bean Directly, Never new the Service in Tests

A common testing mistake is:

~~~java
VulnerableReportService service = new VulnerableReportService();
service.readProtectedReport();
~~~

This object never passed through the Spring container or proxy; that test **does not prove method security works**. To verify the interceptor, write a test with a Spring ApplicationContext and inject the bean:

~~~java
@Autowired
VulnerableReportService vulnerableService;
~~~

Then establish an appropriate Authentication, call through the injected bean, and assert an exception when lacking permissions. With MockMvc and Basic in the example, you also verify the 200/403 responses of HTTP entry points.

In direct service tests, **@WithMockUser(authorities = "report:read")** (when spring-security-test is present) can build a SecurityContext. When testing missing permissions, supply different authorities or a user lacking the required authority. In multithreaded JUnit tests or Reactor pipelines, populate the security context via the right mechanism rather than assuming ThreadLocal works arbitrarily.

## 7. Other Situations Where Annotations Fail to Execute

### 7.1. Objects Not Managed by Spring

~~~java
ReportService service = new ReportService();
service.sensitive();
~~~

This code is only a general illustration. If ReportService is instantiated via new outside Spring, no method-security proxy exists. Putting **@Service** on the class does not convert a manually constructed instance into a bean.

### 7.2. private, final, and Non-Proxyable Classes

With **class-based proxies**, **private** or **final** methods cannot be overridden for Spring AOP to attach advice; **final** classes cannot be subclass-proxied. These constraints must be checked when auditing method security.

Safe practices for beans requiring protection:
- Use clear **public** methods as security entry gates.
- Never assume @PreAuthorize on a **private helper** blocks calls from other methods in the same class.
- In Kotlin, remember classes and methods are final by default; configure opening for proxies appropriately (e.g., the all-open plugin in matching projects).
- When a bean implements interfaces and uses JDK proxying, check which methods are exposed on the interface and where annotations sit; verify with tests rather than just reading class names.

### 7.3. Constructors, @PostConstruct, and Initialization Phases

While an object is being constructed, proxy assembly may not be complete. Do not expect methods called from constructors, initializers, or lifecycle callbacks inside the bean itself to undergo method security like external proxy calls. Separate initialization logic from protected operations; test call paths after the bean has been retrieved from the container.

### 7.4. Any Proxy-Based Annotation Can Be Affected

A self-call can also bypass **@Transactional**, **@Cacheable**, **@Async**, or custom advice depending on how they are configured. For example, if method A in the same bean calls this.methodB() annotated with @Transactional, the transaction advice on B may not run.

However, do not equate the consequences: a method-security bypass can lead to **unauthorized reads/writes of sensitive resources**; bypassing a transaction proxy can corrupt transaction boundaries. Same AOP root cause, different risk profile and testing needs.

### 7.5. Method Security Does Not Fully Replace URL Security

HTTP configuration and method configuration have different scopes:

| Layer | Example | Effect |
| --- | --- | --- |
| HTTP request | requestMatchers("/reports/**").hasAuthority("report:read") | Protects request groups before reaching controllers |
| Method | @PreAuthorize("hasAuthority('report:read')") | Protects method calls intercepted by a Spring proxy |
| Data business logic | Checks whether user belongs to the report's tenant/owner | Prevents accessing out-of-scope records |

If the URL layer strictly blocks unauthorized callers, the self-call demo might not be reachable via that route. Still, a service can be invoked from other controllers, scheduled jobs, message consumers, or internal flows. Therefore, when method-level business protection is needed, never assume HTTP rules cover self-invocation bugs in the service layer.

Method security also does not automatically verify **ownership/tenant/resource state**. Rules grounded in resource data may require parameterized authorization expressions, custom AuthorizationManagers, or service-layer domain checks.

## 8. How to Diagnose When @PreAuthorize Does Not Run

When encountering a @PreAuthorize method that unauthorized users can still reach, check in order:

1. **Is @EnableMethodSecurity enabled?** Spring Boot Starter Security does not enable method annotations automatically.
2. **Is the object a Spring-managed bean?** Instances created with new have no proxy.
3. **Does the caller actually hold a proxy?** With bean injection, inspect the runtime bean type.
4. **Is there self-invocation?** Look for calls like **this.sensitive()**, **sensitive()** within the same class, or unguarded public wrappers.
5. **Can the method be intercepted?** Check private/final modifiers, proxy mode, interfaces, visibility, and bean structure.
6. **Is the annotation in the right place?** Check the concrete method actually called, meta-annotations, and active security configs.
7. **Which authorities does Authentication hold?** Compare exact role/authority strings; hasRole involves ROLE_ by default.
8. **Are there multiple access paths to the feature?** Audit controllers, events, other services, schedulers, and background jobs.
9. **Are other layers skewing test results?** URL authorization, CSRF, or authentication entry points may reject before the method is reached.

### 8.1. Checking Whether a Bean Is a Spring Proxy

In a test running **inside a Spring ApplicationContext**, you can check:

~~~java
import org.springframework.aop.support.AopUtils;

// Fragment example: service is @Autowired from Spring.
boolean isProxy = AopUtils.isAopProxy(service);
System.out.println("Spring AOP proxy: " + isProxy);
~~~

**AopUtils.isAopProxy** only helps confirm the object is AOP-proxied; being a proxy **does not prove every call** to every method is advised. The essential step remains testing call paths and unauthorized cases.

To inspect the runtime class name in dev tests, check **service.getClass().getName()**; with class-based proxies you may see proxy markers in the name. Never write tests asserting exact proxy class name strings, as those are implementation details.

### 8.2. Logging and Controlled Checks

In development, you can temporarily enable:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.aop=DEBUG
~~~

Logs only assist observation and never replace tests. Avoid logging passwords, session cookies, access tokens, or sensitive payloads. The most important test is proving **unauthorized callers are blocked across every entry point**, not merely calling one sample method cleanly.

## 9. With Spring WebFlux and Reactive Method Security

Spring WebFlux has its own HTTP security stack (ServerHttpSecurity, SecurityWebFilterChain). With **reactive method security**, apps typically enable **@EnableReactiveMethodSecurity** and return reactive types like Mono/Flux so authorization integrates into the reactive pipeline with Reactor Context.

**Proxy self-invocation limits still require auditing when configured with AdviceMode.PROXY.** Do not copy servlet @EnableMethodSecurity and assume reactive checks work automatically. Likewise, do not read Authentication from servlet ThreadLocals as the sole mechanism inside a reactor pipeline.

In reactive apps, verification steps remain architecturally similar: Spring bean, caller holding the proxy, calls crossing the proxy, matching authorities, testing self-calls, and testing publishers after subscription / via StepVerifier. Each stack must be tested using its own APIs and security context.

## 10. Practical Review Checklist for Sensitive Services

When reviewing an operation like **exportReport**, **approvePayment**, **deleteUser**, or **readPrivateDocument**, answer:

- **Who can trigger the operation?** List HTTP routes, scheduled jobs, queue consumers, and service callers.
- **Where are the authorization checkpoints?** URL policies, method annotations, or domain checks.
- **Do calls pass through a Spring proxy?** Inspect bean wiring and call graphs; hunt for self-invocation.
- **Are there unnoticed indirect paths?** Unannotated public helper methods calling annotated methods in the same class.
- **Are the checked permissions strict enough?** Authorities, roles, tenants, ownership, and resource states.
- **Does every access path have negative tests?** Especially authenticated users lacking the matching authority.
- **Is there a clear fix for bypasses?** Prefer splitting beans along security boundaries and re-testing all entry points.

### Before and After Refactoring

**Before:** Controller -> ReportService.readForDashboard() -> this.readConfidentialData() (@PreAuthorize). Unauthorized callers can reach the data because the target method bypassed the proxy.

**After:** Controller -> DashboardService.read() -> SecuredReportReader.readConfidentialData() (@PreAuthorize). Cross-bean calls pass through the proxy, verifying permissions before reading data.

Even after fixing the config, test public routes, blocked routes, valid roles, and missing roles. In production, never leave confidential data protected only by assuming "annotations always run" when source code contains internal calls.

## 11. Self-Assessment Questions

1. What is **@EnableMethodSecurity** used for? Why is simply adding spring-boot-starter-security insufficient?
2. What distinct roles do the **proxy** and **target** play when enforcing @PreAuthorize?
3. Why can a Controller calling bean.sensitive() be blocked, whereas bean.doWork() calling this.sensitive() is not?
4. If you switch to **proxyTargetClass=true**, is self-invocation fixed automatically? Explain the call path.
5. In the demo, why does **viewer -> /lab/direct** return 403 while **viewer -> /lab/self** returns 200?
6. Why does extracting the @PreAuthorize method into **ProtectedReportReader** cause calls from **SafeReportFacade** to be checked?
7. When does adding @PreAuthorize to an outer wrapper help, and why must you still audit other entry points?
8. Does testing new ReportService() directly prove Spring method security works?
9. What limitations do **private/final** methods have under class-based proxies?
10. When handling multi-tenant reports, is `@PreAuthorize("hasAuthority('report:read')")` alone enough? What else must be checked?
11. If the same business method is invoked from both a controller and a message consumer, why must both paths be tested?
12. For Spring WebFlux, why must you use the reactive security context mechanism and test actual publishers?

**Takeaway:** Spring Security method security in Spring AOP proxy mode protects **calls passing through the proxy**, not a method by automatically intercepting direct internal calls on the target. **Self-invocation can bypass @PreAuthorize/@PostAuthorize** on the target method. For sensitive logic, ensure explicit authorization checkpoints, prefer separating beans and calling via proxies, and write **negative tests** for every entry point.

## Official Documentation

- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 API — @EnableMethodSecurity: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html
- Spring Framework — Proxying Mechanisms, Self Invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
