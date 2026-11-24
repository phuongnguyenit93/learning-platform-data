# Controlling FORWARD, ERROR, and ASYNC with dispatcherTypeMatchers in Spring Security Servlet

**Lesson:** HTTP Authorization. **Illustrative environment:** Java 17+, Spring Boot 3.3.5, Spring Security 6.x, and Jakarta Servlet. This lesson explains how to use <code>dispatcherTypeMatchers</code> to avoid accidentally blocking FORWARD/ERROR/ASYNC dispatches while not inadvertently exempting sensitive controllers or services from authorization.

**Key point:** A single HTTP request sent by a browser can trigger multiple internal Servlet dispatches. These passes can have different DispatcherTypes. URL-based security rules are not always automatically applied identically to REQUEST, FORWARD, ERROR, and ASYNC. Proper control requires examining **Servlet filter registration**, the selected **SecurityFilterChain**, **authorization matcher order**, and the **target path of the dispatch**.

## 1. Understand DispatcherType Before Configuring

<code>jakarta.servlet.DispatcherType</code> is an enum describing the Servlet container's dispatch type, not an HTTP method.

| DispatcherType | Meaning | Example |
| --- | --- | --- |
| <code>REQUEST</code> | Client sends an HTTP request directly | GET /reports |
| <code>FORWARD</code> | Server transfers processing internally to another resource | Spring MVC <code>forward:/internal/render</code> |
| <code>ERROR</code> | Container handles an error and invokes the error page/servlet | Sending 500 then invoking /error |
| <code>ASYNC</code> | Servlet resumes a request processed asynchronously | MVC <code>Callable</code> returns a result, then redispatches |
| <code>INCLUDE</code> | A resource's content is included into another resource's response | <code>RequestDispatcher.include(...)</code> |

GET/POST refer to HTTP methods, whereas REQUEST/FORWARD/ERROR/ASYNC refer to **Servlet dispatch passes**. A single GET can go through REQUEST then FORWARD, or REQUEST then ASYNC. Arbitrary headers such as <code>X-Dispatcher-Type: FORWARD</code> cannot directly change the dispatcher type; the container decides it. However, the internal dispatch target can be influenced indirectly if a controller accepts a client-supplied path and uses it to forward.

### FORWARD

~~~text
Browser GET /view
  |
  v
DispatcherType.REQUEST /view
  |
  | MVC Controller returns "forward:/internal/render"
  v
DispatcherType.FORWARD /internal/render
  |
  v
HTTP response
~~~

### ERROR

~~~text
Browser GET /error-trigger
  |
  v
DispatcherType.REQUEST /error-trigger
  |
  | response.sendError(500)
  v
DispatcherType.ERROR /error
  |
  v
Error page with status 500
~~~

### ASYNC

~~~text
Browser GET /async/report
  |
  v
DispatcherType.REQUEST /async/report
  |
  | Spring MVC Callable starts async processing
  v
Task runs on worker thread
  |
  v
DispatcherType.ASYNC /async/report
  |
  v
MVC completes response
~~~

This is an internal server mechanism. Do not equate ASYNC dispatch with any arbitrary work running in a <code>CompletableFuture</code>: a task running on another thread does not automatically create a Servlet ASYNC dispatch without the Servlet async lifecycle.

## 2. Two Layers Must Be Configured Correctly: Filter Mapping and Authorization

**The first layer is Filter registration.** The Servlet container only invokes security filters for registered dispatcher types. If <code>springSecurityFilterChain</code> is not mapped to FORWARD, then a <code>dispatcherTypeMatchers(FORWARD)</code> rule will not be evaluated on that FORWARD pass.

**The second layer is Spring Security authorization.** When the security filter chain handles a dispatch, <code>authorizeHttpRequests</code> evaluates matchers to decide access.

Example configuration snippet:

~~~java
http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
    .anyRequest().authenticated());
~~~

The snippet above allows ERROR **if the security filter actually runs on ERROR dispatches**. It does not itself alter Servlet filter registration.

In Spring Boot 3.x, you can specify the security filter's dispatcher types with a property:

~~~yaml
spring:
  security:
    filter:
      dispatcher-types: request, async, error, forward
~~~

The example explicitly adds FORWARD for testing. Do not apply this property directly to a plain Servlet application without Spring Boot; in that case you must register the filter through the appropriate Servlet container mechanism. When deploying a WAR, adding a reverse proxy, or changing bootstrap, verify the actual mapping rather than inferring from code.

Additionally, some filters inside the chain have their own logic regarding running on ERROR/ASYNC dispatches, such as filters extending <code>OncePerRequestFilter</code>. Having the container invoke the chain does not mean every inner filter runs identically to REQUEST. Therefore testing on a real Servlet container matters.

## 3. dispatcherTypeMatchers: Syntax, Order, and Permissions

The Spring Security DSL can use:

~~~java
import jakarta.servlet.DispatcherType;

// Snippet inside a SecurityFilterChain bean:
http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        DispatcherType.FORWARD, DispatcherType.ERROR).permitAll()
    .dispatcherTypeMatchers(DispatcherType.ASYNC).authenticated()
    .anyRequest().denyAll());
~~~

<code>dispatcherTypeMatchers</code> creates a matcher by dispatch type, then combines it with <code>permitAll</code>, <code>authenticated</code>, <code>hasRole</code>, <code>hasAuthority</code>, <code>denyAll</code>...

**This is only an API illustration, not a recommended production policy.** Allowing **all** FORWARDs can let a forward to a sensitive endpoint bypass URL authorization. Allowing ASYNC based solely on authenticated state can likewise weaken the target URL's `hasRole` rule. The sample policy below restricts by both dispatcher type and path.

### First Matching Matcher Wins

~~~java
http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll());
~~~

If an ERROR dispatch has a path under `/admin/**`, the earlier ERROR rule matches and is used. Reversing the two rules could cause the URL rule to demand ADMIN even when the container is merely rendering a generic error. Order is part of the security policy.

Do not confuse authorization matcher order with <code>SecurityFilterChain</code> order. When there are multiple chains, <code>FilterChainProxy</code> selects the **first chain** matching the request; authorization rules in other chains are not evaluated. A policy for ERROR in an unselected chain has no effect.

## 4. FORWARD: Allow by Path, Do Not Broaden Arbitrarily

A Spring MVC <code>@Controller</code> can return the view name <code>forward:/internal/render</code>. For a page requiring `ROLE_USER`, we expect:
- Browser sends REQUEST <code>/view</code>: requires `ROLE_USER`.
- MVC performs FORWARD to <code>/internal/render</code>: only allow this target and still check `ROLE_USER`.
- Browser directly calls REQUEST <code>/internal/render</code>: denied.

A matcher combining dispatcher type + path:

~~~java
RequestMatcher forwardView = req ->
    req.getDispatcherType() == DispatcherType.FORWARD
    && "/internal/render".equals(req.getServletPath());

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(forwardView).hasRole("USER")
    .dispatcherTypeMatchers(DispatcherType.FORWARD).denyAll()
    .anyRequest().denyAll());
~~~

<code>RequestMatcher</code> belongs to <code>org.springframework.security.web.util.matcher</code>. <code>requestMatchers(forwardView)</code> sits **before** the FORWARD `denyAll` fallback. With the demo's default servlet mapping, <code>getServletPath()</code> is the internal forwarded path. If the application uses complex servlet mappings, inspect the actual request path in the runtime environment.

**Why can <code>permitAll(FORWARD)</code> be dangerous?** If a public endpoint lets users specify a forward target, and FORWARD is `permitAll`, a request can internally forward to <code>/admin/export</code>. Then the ADMIN rule on the URL can be skipped during the FORWARD pass because the earlier dispatcher matcher already decided. Prevent this flaw by never forwarding to sensitive targets from untrusted input, maintaining a target allowlist, and testing forbidden forwards.

In a safe internal template-rendering system, a broad rule for FORWARD may be considered, but only after inventorying all possible targets and verifying that the initial REQUEST enforces proper authorization.

## 5. ERROR: Render Errors Without Exposing Secrets

ERROR dispatch lets the Servlet container run an error page when processing fails. If authorization blocks the ERROR pass, a 500 error can be masked by 401/403, causing users to see the wrong error page and making logs harder to trace.

Common configuration:

~~~java
http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
    .anyRequest().authenticated());
~~~

This should only allow **rendering a generic error message**. It does not mean the ERROR handler may access sensitive data or perform unauthenticated business operations. Error pages must avoid returning stack traces, tokens, cookies, password hashes, SQL, or PII. If detailed diagnostics are needed, use a separate administrative endpoint with authentication/authorization.

Distinguish Servlet ERROR dispatches from errors handled by Spring Security's <code>AuthenticationEntryPoint</code>/<code>AccessDeniedHandler</code>: a 401/403 response does not necessarily trigger an ERROR dispatch. <code>MockMvc</code> also does not always simulate container handling of <code>sendError</code> and dispatching to `/error` completely like embedded Tomcat. Therefore test ERROR via HTTP against a real server.

A direct REQUEST to <code>/error</code> differs from an ERROR dispatch to the same path. The rule <code>requestMatchers("/error").permitAll()</code> opens the URL by path matcher, whereas <code>dispatcherTypeMatchers(ERROR).permitAll()</code> only opens the dispatch type. Choose according to your error handler's policy.

## 6. ASYNC: Do Not Bypass Role Checks on Redispatch

Spring MVC supports <code>Callable</code>, <code>DeferredResult</code>, and other async processing styles. An initial REQUEST may be authorized with the URL's role, after which the container uses an ASYNC dispatch to complete the result. Placing <code>dispatcherTypeMatchers(ASYNC).permitAll()</code> before all URL rules can cause an ASYNC dispatch to a sensitive path to stop enforcing `hasRole`/`hasAuthority` as expected.

Scoped ASYNC example:

~~~java
RequestMatcher asyncReport = req ->
    req.getDispatcherType() == DispatcherType.ASYNC
    && "/async/report".equals(req.getServletPath());

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(asyncReport).hasRole("USER")
    .dispatcherTypeMatchers(DispatcherType.ASYNC).denyAll()
    .anyRequest().authenticated());
~~~

Intended flow:
1. REQUEST <code>/async/report</code> can only start when the user has `ROLE_USER`.
2. When ASYNC dispatches back to the same path, it must still satisfy `ROLE_USER`.
3. ASYNC dispatches to other paths hit `denyAll`, instead of bypassing permissions by default.

Not every app must pick this exact policy; some apps allow ASYNC after the initial REQUEST has checked all conditions. However, you must prove the redispatch destination is strictly a safe path and async logic cannot switch to a higher-privilege resource.

### SecurityContext on Worker Threads

<code>WebAsyncManagerIntegrationFilter</code> helps integrate `SecurityContext` for certain Spring MVC flows like <code>Callable</code>, yet not every executor/custom task automatically inherits the context. <code>SecurityContextHolder</code> by default binds context to a thread. If a job runs on another thread, you may need <code>DelegatingSecurityContextCallable</code>, <code>DelegatingSecurityContextRunnable</code>, an executor wrapper, or a policy that re-checks permissions in the service.

Do not blindly enable <code>MODE_INHERITABLETHREADLOCAL</code> for thread pools because of the risk of leaking the wrong identity. <code>dispatcherTypeMatchers</code> controls Servlet dispatches; it **does not** replace proper context propagation across all Java async tasks.

## 7. Policy Matrix Before Writing Code

| Dispatch type | Path | Permission | Reason |
| --- | --- | --- | --- |
| REQUEST | GET /public | permitAll | Public endpoint |
| REQUEST | GET /view | ROLE_USER | User may view the page |
| FORWARD | /internal/render | ROLE_USER | Internal forward to a single target |
| FORWARD | Other paths | denyAll | Do not bypass permissions on sensitive URLs |
| ERROR | Error dispatch | permitAll | Allow container to render errors safely |
| REQUEST | GET /async/report | ROLE_USER | Start async task |
| ASYNC | /async/report | ROLE_USER | Continue only on matching path and role |
| ASYNC | Other paths | denyAll | Do not open all async targets |
| REQUEST | GET /admin | ROLE_ADMIN | Administrative feature |
| REQUEST | /internal/render | denyAll | Disallow calling internal view directly |
| REQUEST | Other paths | denyAll | Fail closed |

Specific data-access actions require service-layer authorization (owner/tenant, record status), not just HTTP roles. For a product with multiple Servlets or Spring `SecurityFilterChain`s, the matrix also needs a servlet mapping/chain ownership column.

## 8. Runnable Spring Boot Project

The example uses Java 17+, Spring Boot 3.3.5, Spring Security 6.x, and Maven. HTTP Basic helps test 200/401/403; demo user <code>reader</code> has `ROLE_USER`, and <code>admin</code> has `ROLE_USER` and `ROLE_ADMIN`. Demo credentials are only for localhost use.

Structure:

~~~text
dispatcher-security-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/dispatchdemo/
    │   │   ├── DispatchSecurityApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   ├── ViewController.java
    │   │   └── ApiController.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/dispatchdemo/
            └── DispatcherSecurityTest.java
~~~

### 8.1. Maven pom.xml

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
  <artifactId>dispatcher-security-demo</artifactId>
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

### 8.2. Main Class

Create <code>src/main/java/com/example/dispatchdemo/DispatchSecurityApplication.java</code>:

~~~java
package com.example.dispatchdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DispatchSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(DispatchSecurityApplication.class, args);
    }
}
~~~

### 8.3. application.yml — Registering Filter for FORWARD

~~~yaml
spring:
  security:
    filter:
      dispatcher-types: request, async, error, forward
~~~

This is a Spring Boot property for security filter registration. If using a different Servlet setup, verify the actual filter mapping rather than just copying YAML.

### 8.4. SecurityConfiguration.java

Create <code>src/main/java/com/example/dispatchdemo/SecurityConfiguration.java</code>:

~~~java
package com.example.dispatchdemo;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class SecurityConfiguration {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass-123"))
            .roles("USER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass-123"))
            .roles("USER", "ADMIN")
            .build();
        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        RequestMatcher forwardView = req ->
            req.getDispatcherType() == DispatcherType.FORWARD
            && "/internal/render".equals(req.getServletPath());

        RequestMatcher asyncReport = req ->
            req.getDispatcherType() == DispatcherType.ASYNC
            && "/async/report".equals(req.getServletPath());

        return http
            .authorizeHttpRequests(auth -> auth
                // Scoped matchers before dispatcher-based fallbacks.
                .requestMatchers(forwardView).hasRole("USER")
                .dispatcherTypeMatchers(DispatcherType.FORWARD).denyAll()

                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()

                .requestMatchers(asyncReport).hasRole("USER")
                .dispatcherTypeMatchers(DispatcherType.ASYNC).denyAll()

                .requestMatchers(HttpMethod.GET,
                    "/public", "/error-trigger").permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/view", "/secure", "/async/report").hasRole("USER")
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Configuration explanation:
- FORWARD to `/internal/render` requires `ROLE_USER`; other FORWARDs hit `denyAll`.
- ERROR dispatch is `permitAll` to produce generic error responses; error controllers must not read sensitive data.
- ASYNC redispatch to `/async/report` still requires `ROLE_USER`; other ASYNC paths hit `denyAll`.
- REQUEST `/view` and `/async/report` are checked before triggering internal dispatches.
- Direct REQUEST `/internal/render` is not on the allowlist, so it hits `denyAll`.
- REQUEST `/admin` requires `ROLE_ADMIN`; `reader` with only `ROLE_USER` receives 403.
- <code>anyRequest().denyAll()</code> prevents new endpoints from opening by default.
- Spring Security protects state-changing methods with CSRF by default; the example only lists GET and does not disable CSRF.

If a real app has multiple <code>SecurityFilterChain</code>s, the matchers here only take effect when this chain is selected. The demo has a single chain and uses no narrow <code>securityMatcher</code> to stay focused on dispatcher authorization.

### 8.5. ViewController.java

Create <code>src/main/java/com/example/dispatchdemo/ViewController.java</code>:

~~~java
package com.example.dispatchdemo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class ViewController {
    @GetMapping("/view")
    public String view() {
        return "forward:/internal/render";
    }

    @ResponseBody
    @GetMapping("/internal/render")
    public String internalRender() {
        return "rendered-view";
    }
}
~~~

The class uses <code>@Controller</code>, not <code>@RestController</code>, so Spring MVC interprets <code>forward:/internal/render</code> as a view name performing a FORWARD. With <code>@RestController</code>, that String would merely be sent as a normal response body.

### 8.6. ApiController.java

Create <code>src/main/java/com/example/dispatchdemo/ApiController.java</code>:

~~~java
package com.example.dispatchdemo;

import java.io.IOException;
import java.util.concurrent.Callable;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/secure")
    public String secure(Authentication auth) {
        return "secure:" + auth.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }

    @GetMapping("/async/report")
    public Callable<String> asyncReport(Authentication auth) {
        String user = auth.getName();
        return () -> "async:" + user;
    }

    @GetMapping("/error-trigger")
    public void errorTrigger(HttpServletResponse response)
            throws IOException {
        response.sendError(
            HttpServletResponse.SC_INTERNAL_SERVER_ERROR, "demo failure");
    }
}
~~~

<code>Callable</code> is a Spring MVC async return type, requiring no <code>@EnableAsync</code> just to use this feature. The demo captures the authenticated username at REQUEST; an async task accessing real data must still check permissions/tenant/ownership at the business layer. <code>sendError(500)</code> lets the embedded Servlet container perform an ERROR dispatch.

## 9. Running and Predicting Behavior

In the project directory:

~~~bash
mvn test
mvn spring-boot:run
~~~

Test with curl:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/secure
curl -i -u reader:reader-pass-123 http://localhost:8080/secure
curl -i -u reader:reader-pass-123 http://localhost:8080/view
curl -i -u reader:reader-pass-123 http://localhost:8080/internal/render
curl -i -u reader:reader-pass-123 http://localhost:8080/admin
curl -i -u admin:admin-pass-123 http://localhost:8080/admin
curl -i -u reader:reader-pass-123 http://localhost:8080/async/report
curl -i http://localhost:8080/error-trigger
~~~

| Scenario | Expected HTTP | Notes |
| --- | --- | --- |
| GET /public anonymous | 200 | <code>public</code> |
| GET /secure anonymous | 401 | HTTP Basic requires authentication |
| GET /secure reader | 200 | <code>secure:reader</code> |
| GET /view reader | 200 | REQUEST and FORWARD, body <code>rendered-view</code> |
| GET /internal/render reader | 403 | Direct REQUEST hits denyAll |
| GET /admin reader | 403 | Reader lacks ROLE_ADMIN |
| GET /admin admin | 200 | <code>admin</code> |
| GET /async/report reader | 200 | REQUEST + ASYNC, body <code>async:reader</code> |
| GET /async/report anonymous | 401 | Unauthorized already at REQUEST |
| GET /error-trigger anonymous | 500 | ERROR dispatch handles generic error |

These are **expected results from the example config**, not an executed run log. If outcomes differ, inspect actual filter registration, `servletPath`, security chain, authorization matcher order, async context, and error controller before modifying policy.

## 10. MockMvc Tests: REQUEST, FORWARD, and ASYNC

Create <code>src/test/java/com/example/dispatchdemo/DispatcherSecurityTest.java</code>:

~~~java
package com.example.dispatchdemo;

import jakarta.servlet.DispatcherType;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.security.web.util.matcher.RequestMatcher;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.forwardedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DispatcherSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void requestRulesEnforceUserAndAdminRoles() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/secure"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/secure")
                .with(httpBasic("reader", "reader-pass-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("secure:reader"));

        mvc.perform(get("/admin")
                .with(httpBasic("reader", "reader-pass-123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-pass-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void directRequestToInternalEndpointIsDenied() throws Exception {
        mvc.perform(get("/internal/render")
                .with(httpBasic("reader", "reader-pass-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void mvcControllerChoosesForwardTarget() throws Exception {
        mvc.perform(get("/view")
                .with(httpBasic("reader", "reader-pass-123")))
            .andExpect(status().isOk())
            .andExpect(forwardedUrl("/internal/render"));
    }

    @Test
    void asyncRequestCompletesWithReaderRole() throws Exception {
        MvcResult started = mvc.perform(get("/async/report")
                .with(httpBasic("reader", "reader-pass-123")))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(started))
            .andExpect(status().isOk())
            .andExpect(content().string("async:reader"));
    }

    @Test
    void scopedForwardMatcherRejectsOtherTargets() {
        RequestMatcher matcher = req ->
            req.getDispatcherType() == DispatcherType.FORWARD
            && "/internal/render".equals(req.getServletPath());

        MockHttpServletRequest req =
            new MockHttpServletRequest("GET", "/internal/render");
        req.setServletPath("/internal/render");
        req.setDispatcherType(DispatcherType.FORWARD);
        assertThat(matcher.matches(req)).isTrue();

        req.setServletPath("/admin");
        assertThat(matcher.matches(req)).isFalse();

        req.setServletPath("/internal/render");
        req.setDispatcherType(DispatcherType.REQUEST);
        assertThat(matcher.matches(req)).isFalse();
    }
}
~~~

**Guarantee scope of the tests:**
- REQUEST tests verify 200/401/403 by credentials and role.
- Direct REQUEST <code>/internal/render</code> is denied even though the scoped internal FORWARD is permitted.
- <code>forwardedUrl</code> verifies MVC returned a forward view, **not** that Tomcat ran the full FORWARD security filtering pass.
- <code>asyncDispatch</code> simulates MVC async completion in MockMvc and helps catch redispatch bugs in the test pipeline.
- The scoped `RequestMatcher` unit test verifies both `DispatcherType` and target `servletPath` must match.

MockMvc is not a real Servlet container. To verify exact FORWARD/ERROR/ASYNC filter registrations and lifecycles, add tests running an actual embedded server. If a test fails due to version or container differences, inspect framework behavior first; never blindly change `dispatcherTypeMatchers` to `permitAll`.

## 11. Verifying ERROR Dispatch on an Embedded Servlet Container

Use <code>mvn spring-boot:run</code> to run embedded Tomcat, then:

~~~bash
curl -i http://localhost:8080/error-trigger
~~~

Expect the original error to produce HTTP 500, instead of being masked by a 401/403 from an ERROR dispatch accidentally blocked by the security filter. Error body content depends on Boot/container configuration; do not assume identical JSON/HTML everywhere.

An integration test using <code>@SpringBootTest(webEnvironment = RANDOM_PORT)</code> with an HTTP client can verify the real ERROR path as well as whether the filter is registered by the container for FORWARD/ASYNC. When debugging, log dispatch type and path in a controlled test environment, avoiding logging cookies/tokens or sensitive data.

<code>MockHttpServletRequest.setDispatcherType(ERROR)</code> only changes a property on a mock request; it does **not** mean the container created an ERROR dispatch, passed through the error controller, and executed Servlet filter mappings.

## 12. FORWARD, ASYNC, and Security Boundaries

### FORWARD: Who Picks the Target?

If a public controller builds a forward target from user input, e.g., a <code>next</code> parameter, a rule opening all FORWARDs can turn it into an authorization bypass path. Never accept arbitrary paths as forward targets. Use a fixed target allowlist, and place real authorization in the data-handling service.

### ASYNC: Where Are Permissions Enforced?

The HTTP role shows the user may start the task. Long-running tasks might access records belonging to another tenant or run after permissions are revoked. Check permissions on `reportId`/`tenantId`, decide whether to re-check permissions at execution time, and handle timeouts/cancellation. Never use <code>Authentication.getName()</code> captured at REQUEST as proof of permission to read every resource.

### ERROR: Avoid Information Disclosure

Even when ERROR dispatches are `permitAll`, error pages must never return stack traces, SQL, credentials, session IDs, or account data. The purpose of allowing ERROR is rendering a safe response, not opening a secret access path.

## 13. Common Mistakes

| Symptom | Cause | How to Investigate |
| --- | --- | --- |
| Forward gets 403 after REQUEST succeeded | FORWARD target has no matching rule | Check `servletPath` and dispatcher type |
| FORWARD rule has no effect | Security filter not mapped to FORWARD | Inspect effective Servlet filter registration |
| Broad FORWARD `permitAll` grants access to admin targets | Bypasses URL role check on dispatch | Scoped matcher + `denyAll` fallback |
| ERROR 500 turns into 403 | ERROR dispatch blocked | Permit safe error rendering; test on container |
| ERROR `permitAll` yet still fails | Error did not originate from ERROR authorization | Check stack/filter/error handler |
| ASYNC request never completes | ASYNC redispatch blocked or context lost | Check matcher/async lifecycle |
| ASYNC `permitAll` for sensitive paths | Overly broad matcher placed before URL rules | Authorize by dispatch+path |
| Direct internal URL still returns 200 | REQUEST URL accidentally opened | Deny direct URL, allow only scoped FORWARD |
| MockMvc green but real server fails | MockMvc does not fully simulate container | Test embedded Tomcat/Jetty |
| Principal in async thread is null | Missing context propagation | Check `WebAsyncManager`/`DelegatingSecurityContext` |
| Multiple `SecurityFilterChain`s | Another chain selected first | Check first-matching `securityMatcher` |
| Wrong HTTP-method-based rules | Confusing `DispatcherType` with `HttpMethod` | Separate GET/POST from REQUEST/FORWARD |
| Filter unexpectedly runs or skips ERROR | Filter-specific `OncePerRequest` behavior | Check `shouldNotFilter...` and registration |
| INCLUDE issues | INCLUDE is a distinct type | Do not treat INCLUDE as equivalent to FORWARD |

## 14. Practical Checklist

1. Inventory REQUEST endpoints, internal FORWARD targets, ERROR pages, and ASYNC redispatch paths.
2. Confirm <code>springSecurityFilterChain</code> is registered by the container for the dispatcher types that genuinely need protection.
3. Identify the first matching `SecurityFilterChain` for each request before reading authorization rules.
4. Use path-scoped `RequestMatcher`s for sensitive FORWARD/ASYNC dispatches; place them before <code>dispatcherTypeMatchers(...).denyAll()</code> fallbacks.
5. Only `permitAll` ERROR for generic error pages that expose no sensitive data.
6. Avoid exempting all FORWARD/ASYNC without inventorying every reachable target.
7. Check URL authorization on the initial REQUEST and service permissions on real resources.
8. Verify `SecurityContext` propagation for `Callable`/custom executors; never share mutable context across users.
9. Write negative tests: anonymous, missing role, direct internal URL, unexpected FORWARD/ASYNC targets.
10. Test FORWARD/ERROR/ASYNC on a real Servlet container, not only MockMvc.
11. Keep <code>anyRequest().denyAll()</code> for unclassified routes when policy requires fail-closed.
12. Re-run integration tests after upgrading Spring Security/Boot or changing filter registration.

## 15. Self-Check Questions

**Question 1:** Can a browser send a header itself to turn a request into `DispatcherType.FORWARD`?  
**Answer:** No. `DispatcherType` is managed by the Servlet container; however, client input can still indirectly influence internal forward targets if the server allows it.

**Question 2:** Why can placing <code>.dispatcherTypeMatchers(FORWARD).permitAll()</code> before <code>hasRole("ADMIN")</code> be dangerous?  
**Answer:** Because a FORWARD to an admin path can be permitted first by the dispatcher rule, skipping the URL's role check on that dispatch pass.

**Question 3:** Why is an ERROR matcher needed?  
**Answer:** So the infrastructure can render error pages safely when the container performs an ERROR dispatch, avoiding masking the original error with another authentication rule.

**Question 4:** Does a <code>Callable</code> running on a worker thread automatically retain `SecurityContext` in every kind of executor?  
**Answer:** No. Spring MVC has integration for some models like `Callable`, but custom async tasks require proper context propagation and authorization.

**Question 5:** Why is configuring `dispatcherTypeMatchers` insufficient if security filter registration does not receive FORWARD?  
**Answer:** Matchers are only evaluated when the request actually passes through the Spring `SecurityFilterChain` during that dispatch pass.

**Question 6:** Does a unit test calling <code>MockHttpServletRequest.setDispatcherType(ERROR)</code> prove Tomcat ERROR dispatch ran?  
**Answer:** No. Integration tests on a real Servlet container are needed to verify the ERROR lifecycle and filter mappings.

**Question 7:** Does a FORWARD rule to `/internal/render` let a browser directly GET `/internal/render`?  
**Answer:** No. A direct GET is `REQUEST`; the demo uses `denyAll` for the internal URL on `REQUEST`.

**Conclusion:** <code>dispatcherTypeMatchers</code> controls permissions on **a Servlet dispatch pass**, without replacing the initial REQUEST's URL/role policy or altering security filter registration in the container. Scope FORWARD/ASYNC to specific targets, render ERROR safely, and test both matchers and real Servlet dispatches.
