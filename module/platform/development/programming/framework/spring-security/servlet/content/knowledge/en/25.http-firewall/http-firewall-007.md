# Impact Assessment Before Relaxing HttpFirewall Policy (Spring Security Servlet)

## 1. Why Must You Assess Impact?

In Spring Security **Servlet**, `HttpFirewall` is the layer that inspects requests before Spring Security selects a `SecurityFilterChain` and enforces security rules. The default **StrictHttpFirewall** implementation rejects many HTTP methods or URLs exhibiting dangerous or ambiguous parsing characteristics: semicolons in paths, encoded slashes, backslashes, certain abnormal encoded sequences, and other cases depending on version.

When a legitimate client encounters an error tied to a firewall-rejected request, a knee-jerk "enable allow to make it work" fix can restore functionality while reopening request forms the design previously sought to prevent. The core task is therefore **evaluating what will change before relaxing policy**:

1. Which legitimate request is being blocked? Is there concrete evidence proving it is a real business requirement?
2. Which layer rejected the request: CDN, reverse proxy, Servlet container, `HttpFirewall`, authorization, or controller?
3. Precisely which **request shapes** does an allow option permit additionally, including attacker-crafted payloads?
4. Do the proxy, container, Spring MVC, and security matchers understand **the exact same path and HTTP method**?
5. Can the issue be solved through URL/client design or proper upstream configuration **without** modifying `HttpFirewall`?
6. If relaxation is unavoidable, which tests prove access control cannot be bypassed, and what is the rollback plan?

A **4xx** response—even 400 or 403—is insufficient to conclude `HttpFirewall` caused it. Identify the error source before choosing a fix.

## 2. Where Does HttpFirewall Sit in the Request Flow?

Typical flow:

~~~text
Browser / API client
    |
    v
CDN / WAF / Load balancer / Reverse proxy (if any)
    |  May decode, rewrite, or normalize path
    v
Servlet container (Tomcat / Jetty / Undertow)
    |  Parses HTTP request; may reject some URLs itself
    v
Spring Security FilterChainProxy
    |
    +-- HttpFirewall inspects and wraps HttpServletRequest
    |     |
    |     +-- Reject: RequestRejectedException
    |     |       -> error handling mechanism, status depends on configuration
    |     |
    |     +-- Accept: continue
    |
    +-- Select SecurityFilterChain by request matcher
    +-- Authentication / Authorization / CSRF / other filters
    |
    v
DispatcherServlet -> Spring MVC handler -> service -> database
~~~

**`HttpFirewall` performs its checks before Spring Security matchers decide which chain applies**. It reduces the risk of layers interpreting request paths differently and creating security-matcher bypasses. `StrictHttpFirewall` is a strong filtering layer, yet it does not replace normalization/validation at the proxy, container, framework, and business layers.

If the container or proxy already rejected the request, the request **may never have reached** `HttpFirewall`. Conversely, if an upstream layer transformed the URL before passing it to the application, the firewall sees only **the post-transformation representation**. That is why testing solely with a `MockHttpServletRequest` cannot prove the entire system is safe.

**Two implementations to distinguish:**

- **StrictHttpFirewall**: strict by default; the right choice to evaluate from a conservative baseline.
- **DefaultHttpFirewall**: different behavior that may handle or normalize certain paths less strictly. Never swap the entire implementation just to resolve one blocked case; the blast radius exceeds changing one specific rule.

Beyond path checks, `StrictHttpFirewall` also enforces rules on methods, hosts, headers/parameters, and invalid characters depending on version. When reviewing a real error, determine **which check** triggered it rather than attributing every `RequestRejectedException` to "encoded URLs."

## 3. Categorizing Commonly Proposed Changes

The names below are **StrictHttpFirewall** API examples; verify against your running Spring Security version and analyze real requests before using them.

| Proposed Change | Possible Valid Scenario | Risks to Review First |
| --- | --- | --- |
| **setAllowSemicolon(true)** | Legacy apps using matrix parameters like `/items;color=red` | Path parameters and route/security matchers interpret differently; masks protected paths |
| **setAllowUrlEncodedSlash(true)** | Legacy IDs embedding `/` as `%2F` in a path variable | Proxy/container decodes `%2F` to `/`, shifting path segment boundaries; matchers and controllers see different paths |
| **setAllowBackSlash(true)** | Legacy client sends `\` in URLs | Some layers treat backslash as slash; enables path traversal or matcher bypass |
| **setAllowUrlEncodedPercent(true)** | Input contains literal `%` encoded as `%25` | Double decoding: `%252F` may decode multiple times into `/`; path-resolution mismatch |
| Relaxing character or other path-encoding limits | Legacy client emits non-standard URLs | Inconsistent normalization, Unicode, separators, control characters, or traversal |
| **setAllowedHttpMethods(...)** with a new list | A client requires an extra HTTP method | Expands attack surface; unusual methods handled differently by proxy/container or routing layer |
| Using a less strict `HttpFirewall` or blanket customizations | Wanting to "let every URL run" | Hard to know exactly which guardrails were disabled |

**Important note:** a URL containing **%2F**, **;**, **\\**, or **%25** may be processed differently by proxies/Servlet containers before reaching the application. The table above describes **risk categories to verify**, not a claim that every stack returns the same response for each string.

One change may fix a legitimate request while exposing a bypass on another. Testing must cover both **valid cases** and **closely related adversarial cases**.

## 4. Understanding the Root Risk: Divergent URL Interpretations

### 4.1. Proxy, Servlet, and Security Matcher Paths Must Align

Suppose endpoints to protect are:

~~~text
/admin/reports/**  -> ADMIN
/public/**         -> permitAll
~~~

For a normal request **/admin/reports/2026**, the path is unambiguous. Yet variants like:

~~~text
/admin;tracking=x/reports/2026
/admin%2Freports/2026
/admin//reports/2026
/admin/%2e%2e/public/x
/admin%5Creports/2026
~~~

may be understood differently across layers, or rejected outright at the proxy/container. **Do not assume** each payload above automatically bypasses a given application; the purpose is verifying consistency: after every decode/normalization step, **authorization must govern the exact resource actually served**.

If a matcher decides "not `/admin/**`" yet the final router serves the administrative resource, the policy has a critical flaw. A vital test case ensures unauthenticated requests **never** retrieve administrative data even when the URL uses an accepted variant.

### 4.2. Semicolons and Matrix Variables

Spring MVC can support matrix variables with syntax like:

~~~text
/products;color=red;size=m
~~~

If a legacy client truly requires **;**, **setAllowSemicolon(true)** may be considered. Still, verify:

- Which request path do security matchers evaluate; is path-parameter handling compatible with the Spring MVC router?
- Does the proxy/container preserve or strip everything after the semicolon?
- Can URLs carrying semicolons appear on admin paths or paths where access control relies on path prefixes?
- Does caching/CDN distinguish **/a** and **/a;x=1** the same way as the backend?
- Are matrix variables truly needed, or can the client switch to query parameters such as **/products?color=red**?

**Allowing `;` does not mean skipping authorization tests on any route.** A global change affects the entire application, including endpoints that do not use matrix variables.

### 4.3. Encoded Slash, Backslash, and Double Encoding

A logical ID like **region/east** placed in a path segment may be encoded by clients as **region%2Feast**. If a proxy decodes it to **region/east**, the segment count changes. This impacts route matching, access control, and cache keys alike.

Double-encoding example:

~~~text
%2F   -> /
%252F -> %2F -> /   (if two layers decode sequentially)
~~~

This is an **illustrative double-decoding sequence**, not guaranteed Servlet container behavior. Observe clearly **how many times each layer decodes**. With Windows-oriented components, **\\** is sometimes treated as a separator, though web stacks do not necessarily behave identically.

Before permitting encoded slashes, consider redesigning the API: use **query parameters**, **request bodies**, or **opaque IDs** composed strictly of URL-safe characters like base64url. Avoid relying on encoded path separators surviving intact through every proxy.

### 4.4. HTTP Methods and Headers

Expanding the HTTP method list can open additional ways to reach endpoints that authorization rules or proxies do not inspect equivalently. For example, `TRACE` is blocked under strict settings. Also audit **method overrides** performed by filters/proxies: the backend may see the rewritten method rather than the original method.

Do not confuse the firewall with CORS: **CORS `allowedMethods`** controls only cross-origin browser behavior, whereas `StrictHttpFirewall`'s **allowed HTTP methods** inspect real requests arriving at the application. CORS does not stop `curl` from sending any method accepted by the application.

## 5. Require Evidence of a False Positive Before Changing Anything

A "blocked request" ticket needs at minimum:

| Data to Collect | Purpose |
| --- | --- |
| Failing feature, client name, and version | Confirm this is a supported business flow |
| Expected endpoint and method | Establish permission and data scope |
| Safe URL/path form with sensitive data masked | Pinpoint the failing character/encoding without leaking secrets |
| Status, exception type, messages from proxy/container/app | Identify the layer actually rejecting |
| Frequency, impact ratio, environment | Quantify the scope of impact |
| Path transformations at CDN/proxy/container | Know what the firewall actually sees |
| Expected `SecurityFilterChain` and authorization matcher | Confirm the path is properly protected |
| Legitimate clients and untrusted clients able to reach it | Assess attack surface |

**Never log full URLs when they contain tokens, emails, secrets, or personal data.** For diagnostics, use fingerprints or sanitized character patterns, request IDs, route/category, and exception type; apply appropriate retention and permissions. Never write cookies, `Authorization` headers, CSRF tokens, session IDs, or request bodies to logs just to track `RequestRejectedException`.

### Distinguishing Errors by Location

1. **No access log at the application:** inspect WAF, proxy, and container first; concluding "`StrictHttpFirewall` blocked it" may be wrong.
2. **`RequestRejectedException` before controller:** check which `HttpFirewall` policy rejected it; trace via request ID, exception class, and sanitized metadata.
3. **401/403 after entering security chain:** inspect authentication, authorization, and CSRF. Relaxing `HttpFirewall` likely will not help.
4. **404 or no matching handler:** the request may have passed the firewall while the MVC router did not recognize the path. Relaxing the firewall will not necessarily help.
5. **Browser displays a CORS error:** inspect CORS/preflight independently; do not change `HttpFirewall` without proof of involvement.

Compare **request path** conditions across both the proxy and application. Even after changing one setter, valid requests still fail if an upstream layer rejects them.

## 6. Risk Assessment Template Before Granting Exceptions

A sound decision documents **before/after**, scope of change, and controls. You can use the following template in a design ticket (this is an assessment template, not configuration parameters):

| Criterion | Required Questions |
| --- | --- |
| Need | Which request is failing and why can't the client be fixed? |
| Exact change | Setter, old/new value, environment, Spring Security version? |
| Scope | All routes or one group? Which systems are affected? |
| Threat model | How might attackers craft URLs/methods/headers? |
| Path interpretation | Do CDN, proxy, container, Spring Security, and Spring MVC agree? |
| Authorization | Do distinct URLs resolving to the same resource share identical authorization? |
| Tests | Which negative, positive, regression, integration, and fuzz inputs must pass? |
| Observability | Error/latency/403/404 metrics, bypass indicators, rollback thresholds? |
| Owner and approval | Who owns security, API, operations, and deployment timing? |
| Rollback | Which config/deploy reverts it, and is any data affected? |

**Example decision:** a legacy client exclusively sends **/products;color=blue**, and the product team proves the client cannot be updated immediately. If choosing to relax **setAllowSemicolon(true)**, you must test both public and admin routes, cache/proxy behavior, and all existing matchers, then deploy with monitoring. If the client can migrate to **/products?color=blue**, that usually reduces attack surface more effectively.

Do not use self-invented numeric risk scores as proof of safety. Decisions must rest on concrete business scenarios, permission mappings, real configuration, and test results.

## 7. Minimal-Change Strategy

Prioritize fixes by root cause:

1. **Client builds malformed URLs:** fix URL encoding and API contracts; prevent clients from concatenating paths from untrusted data.
2. **Ambiguous path design:** move data containing slashes/semicolons into query params, body, or URL-safe IDs.
3. **Inconsistent proxy decode/rewrite:** fix how the proxy forwards paths and also check the container.
4. **Feature genuinely needs rare syntax:** prove the contract cannot change right now, pick **exactly one** `StrictHttpFirewall` exception, test in isolation, and measure impact.
5. **Client sends special methods:** document the exact use case and route, adjust the method allowlist with verification; never open methods merely to silence errors.

With **StrictHttpFirewall**, many setters apply to the firewall handling requests across the application/filter chain; never assume only one controller or path is "relaxed." If a requirement truly applies only to one area, design an explicit boundary and test thoroughly; calling a global setter alone does not scope the exception by endpoint.

**Never choose an "accept all" configuration** just because happy-path tests succeed. Mutated requests, path-confusion exploits, and exotic methods live outside the happy path.

## 8. Java 17 Example: Keeping a Strict Baseline and Evaluating Exceptions in Tests

This is a **Spring Security Servlet** example with **Spring Boot 3.4.5 / Java 17**. The real application uses the default `StrictHttpFirewall`. A separate test demonstrates what happens if **only** semicolons are allowed on an **isolated** firewall instance without altering production policy.

Structure:

~~~text
firewall-review/
├── pom.xml
└── src/
    ├── main/java/example/firewall/FirewallReviewApplication.java
    └── test/java/example/firewall/FirewallPolicyTest.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>firewall-review</artifactId>
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

**src/main/java/example/firewall/FirewallReviewApplication.java**:

~~~java
package example.firewall;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.StrictHttpFirewall;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FirewallReviewApplication {
    public static void main(String[] args) {
        SpringApplication.run(FirewallReviewApplication.class, args);
    }
}

@Configuration
class FirewallSecurityConfiguration {
    @Bean
    WebSecurityCustomizer firewallCustomizer() {
        return web -> {
            StrictHttpFirewall firewall = new StrictHttpFirewall();
            // Keep default policy intact. Do not relax system-wide.
            web.httpFirewall(firewall);
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .anyRequest().permitAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class FirewallDemoController {
    @GetMapping("/public/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/admin/report")
    Map<String, String> report() {
        return Map.of("report", "private");
    }
}
~~~

**Meaning:** path **/public/ping** allows public access, while **/admin/report** requires the ADMIN role. Even without relaxing the firewall, security matchers must still protect the right routes. If path rules are later modified, retest to verify URL variants cannot expose administrative routes publicly.

### Testing the Before/After Difference of One Setter Directly

**src/test/java/example/firewall/FirewallPolicyTest.java**:

~~~java
package example.firewall;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.web.firewall.FirewalledRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.mock.web.MockHttpServletRequest;

@SpringBootTest
@AutoConfigureMockMvc
class FirewallPolicyTest {
    @Autowired
    MockMvc mvc;

    private static MockHttpServletRequest request(String method, String path) {
        MockHttpServletRequest req = new MockHttpServletRequest(method, path);
        req.setServletPath(path);
        return req;
    }

    @Test
    void defaultFirewallRejectsSemicolon() {
        StrictHttpFirewall strict = new StrictHttpFirewall();
        assertThrows(RequestRejectedException.class,
                () -> strict.getFirewalledRequest(
                        request("GET", "/public/items;color=red")));
    }

    @Test
    void isolatedCandidateCanAllowSemicolon() {
        StrictHttpFirewall candidate = new StrictHttpFirewall();
        candidate.setAllowSemicolon(true);
        assertDoesNotThrow(() -> {
            FirewalledRequest wrapped = candidate.getFirewalledRequest(
                    request("GET", "/public/items;color=red"));
            wrapped.reset();
        });
    }

    @Test
    void semicolonExceptionStillRejectsEncodedSlash() {
        StrictHttpFirewall candidate = new StrictHttpFirewall();
        candidate.setAllowSemicolon(true);
        assertThrows(RequestRejectedException.class,
                () -> candidate.getFirewalledRequest(
                        request("GET", "/admin%2Freport")));
    }

    @Test
    void traceMethodIsRejectedByDefault() {
        StrictHttpFirewall strict = new StrictHttpFirewall();
        assertThrows(RequestRejectedException.class,
                () -> strict.getFirewalledRequest(
                        request("TRACE", "/public/ping")));
    }

    @Test
    void adminRouteRequiresAuthentication() throws Exception {
        mvc.perform(get("/admin/report"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void adminRoleCanAccessProtectedRoute() throws Exception {
        mvc.perform(get("/admin/report")
                        .with(user("reviewer").roles("ADMIN")))
                .andExpect(status().isOk());
    }
}
~~~

Run:

~~~bash
mvn test
mvn spring-boot:run
~~~

Expected test result: **all 6 tests PASS** in an environment with Java 17 and Maven once dependencies are resolved. This is the expected behavior of the example; **runtime outcomes must be verified by running in a real environment**, not inferred from text alone. After startup, **GET /public/ping** returns JSON with **status=ok**. Unauthenticated **GET /admin/report** must be blocked by security rules.

**Why isn't testing the candidate enough?** The unit tests above use `MockHttpServletRequest` with test-controlled paths. Production Servlet containers and proxies can parse or normalize URLs before the request reaches the firewall. Allowing a request through **one `StrictHttpFirewall` instance** does not prove the corresponding endpoint routes correctly or remains properly authorized. Hence real server and proxy integration tests are required.

### If an Exception Must Be Proposed in Configuration

After a reviewed decision and integration testing, the exact change might be only:

~~~java
StrictHttpFirewall firewall = new StrictHttpFirewall();
firewall.setAllowSemicolon(true); // Only after risk assessment and test verification
~~~

This is a **conditional change snippet**, **not a complete production configuration file**, and is not enabled in the sample application. Place the exception right where `WebSecurity` receives the firewall. Never stack multiple `setAllow...` calls together just to "fix" batches of rejected requests without analyzing each case.

## 9. Required Test Suite Before Relaxing Policy

### 9.1. Positive Tests: Proving Real Need

- Previously blocked requests succeed through the required layers once the new configuration is active.
- Routing reaches **the right controller and target object**, not merely returning a fake 2xx status.
- Authentication, authorization, CSRF, and validation remain enforced.
- Ordinary URLs, methods, and request headers do not change behavior.
- Frontend, API gateway, WAF, Servlet container, and Spring Security share the same path policy.

### 9.2. Negative Tests: Proving Permission Boundaries Hold

| Test Group | Mandatory Expectation |
| --- | --- |
| Anonymous user accessing admin URL | Remains rejected, regardless of path variant |
| Ordinary user calling ADMIN-only endpoint | Remains rejected |
| Paths with `;`, `%2F`, `%5C`, or `%25` in sensitive areas | No matcher bypass; if accepted, routing and permissions remain accurate |
| Duplicate/padded path segments or dot-segments | Never shifts from protected route to public route after normalization |
| HTTP methods outside the API contract | Never accidentally executes state-changing operations |
| Double decoding or proxy-rewritten URLs | Authorization decision stays consistent before and after route resolution |
| Abnormal request headers/hosts | No unintended widening beyond proposed scope |
| Login/logout steps and CSRF-protected POSTs | Continue requiring tokens and permissions as designed |
| Cache/CDN with variant URLs | Never mixes private/public responses across differing cache keys |

Each case should have a **pre-change baseline**, **post-change result**, and logs/traces showing where the request was routed. Permission-related payloads must be tested across **anonymous**, **ordinary user**, and **authorized user**. Do not check only HTTP status; verify **data and side effects**.

### 9.3. Real Integration Testing

Test along the real production network path or a production-like staging environment:

~~~text
Client -> WAF/CDN -> Reverse proxy -> Servlet container
       -> HttpFirewall -> SecurityFilterChain -> Controller
~~~

Compare paths layer by layer with sensitive data masked. Record clearly: URL decode/normalization, servlet context path, forwarding headers, container version, Spring Security version, and route-matching strategy. Test independent URL variants; never assume a `MockMvc` test guarantees the behavior of nginx/Tomcat/Envoy or a CDN.

**One notable distinction:** a request rejected by the container before entering Spring may emit no `RequestRejectedException`. Explain those cases via the corresponding layer's access/error logs rather than flagging a `HttpFirewall` false positive.

## 10. Safe Observability and Rollout

An intentional relaxation should separate three milestones:

**Before deployment:** record baseline rejected requests grouped by reason category and route, affected client volume, 4xx/5xx rates, high-privilege routes, and passing test cases. Use **sanitized** logs/metrics without storing sensitive raw payloads.

**During canary/staging:** compare valid-request success rates against baseline; watch for unusual requests accepted after the change, wrong-controller hits, cache mismatches, authz denials, CSRF failures, and 5xx spikes. Set alerts for unusual access to administrative endpoints and shifts in URL/method distributions.

**After rollout:** keep monitoring long enough to cover real traffic patterns; archive the decision ticket, owner, exact configuration, and regression results. If a security-matcher bypass, private data leak via cache/route, or strange requests reaching controllers appear, **roll back immediately** per plan, then investigate.

Rollback is not merely flipping a boolean back to `false`; if the deployment/config spanned multiple components (gateway, container, application), revert in the proper order and confirm requests return to baseline. Use feature rollouts or deployment revisions where appropriate, but never leave default security policy dependent on untracked manual edits.

## 11. Common Mistakes

1. **Concluding from one 400 error that `StrictHttpFirewall` must be turned off.** Status alone does not prove the failing layer.
2. **Enabling multiple `setAllow...` flags at once.** You cannot tell which solved the need, and blast radius plus rollback become unclear.
3. **Testing only valid URLs.** You miss whether variant URLs bypass matchers.
4. **Testing only Spring `MockMvc`.** Misses decoding/rewriting at proxies, gateways, and Servlet containers.
5. **Believing `permitAll()` or `@CrossOrigin` are substitute controls.** CORS and authorization serve different purposes; permissions must be enforced on the right routes.
6. **Switching to `DefaultHttpFirewall` just to "make errors disappear."** Swapping implementations can alter many rules simultaneously.
7. **Logging entire URLs and headers to troubleshoot.** Can expose tokens/session data; log only necessary masked fields.
8. **Relaxing the firewall while ignoring cache path normalization.** CDN/edge and backend may treat two URL variants as identical or distinct inconsistently.
9. **Failing to retest high-privilege routes after changes.** Especially dangerous when matchers rely on request paths.
10. **Having no rollback plan.** When a bypass is discovered, slow reversal amplifies impact.

## 12. Decision Checklist and Conclusion

Before approving a pull request modifying `StrictHttpFirewall`, verify every item below:

- [ ] A valid request reproduces the error in the specific environment and version.
- [ ] The layer actually rejecting the request has been identified without guessing from status alone.
- [ ] Raw/normalized URLs have been safely recorded and compared across layers.
- [ ] The exact setter/behavior to relax has been identified—no blanket changes.
- [ ] Fixing the client, API contract, and proxy was considered first.
- [ ] The threat model was updated for path confusion, encoding, methods, and sensitive routes.
- [ ] Unit tests and integration tests include both happy paths and negative authorization cases.
- [ ] Authorization/CSRF, returned data, and side effects were verified under variant URLs.
- [ ] Proxy/container/CDN and cache keys were checked.
- [ ] Observability, owner, approval, rollback thresholds, and reversal steps are in place.

**Principle to remember:** relaxing `HttpFirewall` is an **attack-surface change**, not just an input bug fix. Accept it only after establishing business necessity, exception scope, identical request interpretation across all layers, and regression proof that authentication/authorization/CSRF still govern the intended resources. Keep `StrictHttpFirewall` strict as your baseline and open narrow exceptions only after verifiable assessment.
