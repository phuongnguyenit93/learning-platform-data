# Documenting Disabled Mechanisms with Rationale and Compensating Tests

> **Scope:** Spring Security fundamentals, **Application Design** group. A guide to recording every decision to disable or relax a security mechanism, explicitly stating **baseline, deviation, rationale, boundary, risks, compensating controls, test evidence, owner, review deadline, and rollback procedure**. Practical examples use Java 17, Spring Boot 3.3.5, Spring Security 6.x, JUnit 5, and MockMvc for Servlet/Spring MVC.

## 1. A disabled mechanism is a design decision, not a "fix" for 401/403

Real applications have multiple client types and trust boundaries. Browsers using cookies/sessions carry CSRF risk; service-to-service callers may use Bearer tokens, mTLS, or signatures; public APIs need `permitAll`, whereas administrative functions still require roles. An API-only application can disable HTML form login if it provides an alternative authentication mechanism. A page needing an iframe can adjust framing without dropping all security response headers.

Testing only "the endpoint returns 200" is not enough to prove safety. You need **negative tests**: requests without credentials, wrong credentials, wrong roles, missing CSRF tokens, out-of-scope endpoints, and overly broad header policies must be blocked. At the same time, you must prove the replacement mechanism works and does not break independent controls.

**Practical rule:** whenever a security setting is disabled, relaxed, or bypassed, create an exception record before merging; keep code changes strictly scoped; write tests defending the outer baseline; and give owners and reviewers a clear trigger for restoration.

### Commonly confused changes

| Change | Meaning | Risk |
| --- | --- | --- |
| `formLogin(AbstractHttpConfigurer::disable)` | Disables the Spring Security–generated form login endpoint/flow | Must have a real alternative authentication mechanism |
| `httpBasic(AbstractHttpConfigurer::disable)` | Disables HTTP Basic | Clients relying on Basic can no longer authenticate |
| `csrf(AbstractHttpConfigurer::disable)` | Removes CSRF protection in the chain | Dangerous if browsers still carry ambient credentials |
| `csrf(...ignoringRequestMatchers(...))` | Exempts only matching requests | Overly broad matchers can create vulnerabilities |
| `authorizeHttpRequests(...permitAll())` | Skips authorization checks for a route | Does not automatically disable CSRF, headers, or remaining filters |
| `web.ignoring()` | Excludes requests from the Spring Security filter chain | Can drop security layers and security headers |
| `headers(...disable)` | Removes security response headers | Browsers lose anti-framing, MIME-sniffing, and similar protections |
| Overly broad CORS | Allows JS from other origins to read responses | Does not replace authentication or CSRF |
| `SessionCreationPolicy.STATELESS` | Policy not to create/use sessions for `SecurityContext` | Does not automatically ensure tokens are valid or CSRF-free |
| Removing `@EnableMethodSecurity` | Method security annotations may stop taking effect | Service logic invoked outside HTTP routes can be bypassed |

**Important distinction:** a public URL should use `permitAll` if it is genuinely public, rather than arbitrarily using `web.ignoring` just so anonymous callers can reach it. For machine-to-machine endpoints, you can design a separate security chain, while checking both where filtering begins and where decisions are made.

## 2. How to decide exceptions using a threat model

Before making changes, answer in writing:

1. Who is the caller: browser, service account, mobile app, partner, or scheduler?
2. How are credentials sent: cookie/session, HTTP Basic, Authorization Bearer, client certificate, or HMAC?
3. Does the browser automatically attach credentials to requests? This question is especially critical for CSRF.
4. Does the resource mutate data, grant permissions, download sensitive info, or only serve public GETs?
5. Where are permissions decided: filter, method security, gateway, or internal application?
6. Is TLS enforced from client to gateway and gateway to backend? Which proxies are trusted?
7. Do compensating controls run server-side or merely trust that clients "will send the right thing"?
8. When the identity service, secret manager, or policy service fails to respond, do requests **fail closed**?
9. Can you audit, track metrics, rate-limit, and roll back when underlying assumptions change?
10. Do you have direct test evidence of the real flow rather than only mocking `Authentication`?

Do not treat "REST API," "stateless," "internal only," "behind a WAF," "CORS enabled," or "HTTPS enabled" as sufficient reason on its own to drop an independent control. For instance, HTTPS encrypts transport yet does not prove who sent a webhook; CORS is a browser policy governing cross-origin reads, not a guard against all state-changing requests.

## 3. Security Exception Register

Records should live in version-controlled repositories or a change management system with history and approval controls. They do not need to be long essays, yet they must answer **why the decision exists and whether it remains safe today**.

| Field | What to record |
| --- | --- |
| `exception_id` | ID code, links to code/comment/PR/tests |
| `system/component` | Service, security chain, environment, and dependency versions |
| `control_baseline` | Default protection mechanism or internal standard requirement |
| `deviation` | Exact configuration/code disabling or relaxing the control |
| `scope` | HTTP method, path, audience/client/tenant, environment |
| `business_reason` | Requirement and alternatives considered |
| `threats` | Feasible attacks once the mechanism is removed |
| `assumptions` | Conditions about clients, credentials, and proxies that must always hold |
| `compensating_controls` | Other controls genuinely **verified by the server** |
| `positive_tests` | Valid cases that still work |
| `negative_tests` | Invalid or out-of-scope cases that are blocked |
| `evidence` | CI run, git commit, config version, and tested environment |
| `owner/approver` | Accountable owner and risk acceptor |
| `effective/review/expiry` | Effective date, review deadline, and revocation triggers |
| `monitoring` | Appropriate logs, audit events, counters, and alerts |
| `rollback` | Conditions and steps to restore the baseline |
| `residual_risk` | Remaining risk and the level accepted |

### Sample record for an API-only application

Here we choose a narrowly scoped, easily verifiable change: **disabling HTML form login**, while keeping HTTP Basic for the demo API and keeping CSRF and security headers intact. HTTP Basic in real environments must use **TLS**, password controls, throttling, and proper authentication. In production systems, OAuth2/OIDC Bearer or mTLS may be better choices depending on clients.

```markdown
# SEC-EXC-API-001 — No generated HTML form login

- Status: PROPOSED (illustrative template, not production approval)
- Baseline: Spring Security form login may be available when configured
- Deviation: explicitly disable formLogin; API accepts HTTP Basic in demo
- Client: non-browser API client controlled by application owner
- Reason: no interactive HTML login page is provided
- In-scope: generated form-login mechanism only
- Not disabled: authentication, authorization, CSRF, security headers
- Threat introduced: losing authentication if replacement is misconfigured
- Compensating controls: authenticated HTTP Basic with BCrypt user store;
  HTTPS requirement in deployment; explicit route policy and deny-all fallback
- Positive evidence:
  - valid API user GET /api/me -> 200
  - authorized report reader GET /api/reports -> 200
- Negative evidence:
  - anonymous protected GET -> 401
  - wrong Basic password -> 401
  - insufficient authority -> 403
  - unsafe POST missing/invalid CSRF -> 403
  - generated /login is not usable as an authentication entry
  - default security headers remain present
- Owner role: API platform owner
- Reviewer role: application security reviewer
- Review trigger: browser clients, credential model, gateway or route changes
- Deployment precondition: HTTPS, secret storage, audit and rate controls
- Rollback: restore form login only after reviewing intended login UX
```

This is a **template**, not a real approval. In real projects, assign named individuals for owner/approver, and link PRs and test evidence to the exact commit/deployment. If the system later introduces cookie-bearing browser clients to the API, re-evaluate CSRF, authentication methods, and the threat model instead of clinging to an outdated "API-only" rationale.

## 4. From exception record to tests: both "allow" and "deny"

The test matrix must demonstrate the exact boundaries of the decision.

| Endpoint | User and credential | CSRF | Decision to prove |
| --- | --- | --- | --- |
| GET /public | Anonymous | Not needed | 200; only resources explicitly marked public |
| GET /api/me | Anonymous | Not needed | 401; API is not opened by disabling form login |
| GET /api/me | Wrong Basic password | Not needed | 401; real provider authentication runs |
| GET /api/me | Valid Basic user | Not needed | 200; returns the right identity |
| GET /api/reports | Missing `SCOPE_reports.read` | Not needed | 403 |
| GET /api/reports | Has `SCOPE_reports.read` | Not needed | 200 |
| POST /api/notes | Has ROLE_EDITOR | Missing | 403; CSRF is not disabled |
| POST /api/notes | Has ROLE_EDITOR | Invalid | 403 |
| POST /api/notes | Has ROLE_EDITOR | Valid | 200 |
| POST /api/notes | Only has reports scope | Valid | 403; valid CSRF alone is insufficient |
| GET /login | Valid Basic user | Not needed | Generated login page is not exposed |
| GET /unknown | Valid Basic user | Not needed | Does not automatically become public |
| GET /public | Anonymous | Not needed | `nosniff`, `X-Frame-Options` remain present |

**Distinguish authentication from authorization:** `@WithMockUser` tests can be useful when testing roles alone, yet **do not verify passwords, JWT decoders, or HTTP Basic providers**. When the goal is to prove the replacement authentication mechanism truly works, send credentials through the filter in an HTTP test. This demo uses `httpBasic(...)` for that purpose.

## 5. Runnable Maven demo on Java 17

This example disables only Spring Security's **form login**. It does not disable CSRF, CORS, headers, or authorization. Browser-style POSTs still require a CSRF token. HTTP Basic uses BCrypt-hashed passwords in a mock user store.

```text
documented-security-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/documentedsecurity/
    │   └── DocumentedSecurityApplication.java
    └── test/java/com/example/documentedsecurity/
        └── DocumentedSecurityApplicationTest.java
```

### 5.1 pom.xml

```xml
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
    <artifactId>documented-security-demo</artifactId>
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
    <build><plugins><plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin></plugins></build>
</project>
```

### 5.2 Java configuration and API

Create `src/main/java/com/example/documentedsecurity/DocumentedSecurityApplication.java`:

```java
package com.example.documentedsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DocumentedSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(DocumentedSecurityApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails editor = User.withUsername("editor")
            .password(encoder.encode("editor-demo-password"))
            .authorities("ROLE_EDITOR")
            .build();
        UserDetails analyst = User.withUsername("analyst")
            .password(encoder.encode("analyst-demo-password"))
            .authorities("SCOPE_reports.read")
            .build();
        return new InMemoryUserDetailsManager(editor, analyst);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/notes")
                    .hasRole("EDITOR")
                .anyRequest().denyAll())
            // SEC-EXC-API-001: no generated HTML form login.
            .formLogin(AbstractHttpConfigurer::disable)
            // Compensating authentication path for this learning demo.
            .httpBasic(Customizer.withDefaults())
            // Keep CSRF, security response headers and other defaults.
            .csrf(Customizer.withDefaults())
            .build();
    }

    @RestController
    static class Api {
        @GetMapping("/public")
        String publicPage() {
            return "public ok";
        }

        @GetMapping("/api/me")
        String me(Authentication authentication) {
            return "hello " + authentication.getName();
        }

        @GetMapping("/api/reports")
        String reports() {
            return "report allowed";
        }

        @PostMapping("/api/notes")
        String addNote() {
            return "note saved";
        }
    }
}
```

**Key points:**

- `.formLogin(AbstractHttpConfigurer::disable)` does not remove all authentication. `httpBasic` still accepts credentials, and `UserDetailsService` and `PasswordEncoder` still verify username/password.
- `httpBasic` here is a mechanism for learning and testing. Production uses **HTTPS**, secret management, and brute-force protection; OIDC/OAuth2 JWT or mTLS may be better choices. Disabling form login does not automatically make Basic optimal for every system.
- `requestMatchers` scopes specific methods/paths alongside `anyRequest().denyAll()`. Undeclared endpoints do not open automatically.
- `hasRole("EDITOR")` checks `ROLE_EDITOR` per the default role prefix. `hasAuthority("SCOPE_reports.read")` matches the exact string.
- CSRF stays enabled; a user with a valid password whose POST lacks CSRF still gets 403. Never disable CSRF just to run `curl -X POST` quickly.
- Spring Security's response header configuration remains intact because `headers().disable()` is not used.

## 6. Complete tests: compensating controls and baseline

Create `src/test/java/com/example/documentedsecurity/DocumentedSecurityApplicationTest.java`:

```java
package com.example.documentedsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentedSecurityApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicGetWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public ok"));
    }

    @Test
    void anonymousCannotReadProtectedApi() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsRejectedByRealBasicAuth() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("editor", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialAuthenticates() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("editor", "editor-demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello editor"));
    }

    @Test
    void editorLacksReportScope() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("editor", "editor-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystHasReportScope() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("analyst", "analyst-demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("report allowed"));
    }

    @Test
    void browserStylePostWithoutCsrfIsStillBlocked() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("editor", "editor-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongCsrfTokenIsBlocked() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("editor", "editor-demo-password"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfAndRoleAllowPost() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("editor", "editor-demo-password"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("note saved"));
    }

    @Test
    void correctCsrfCannotReplaceMissingRole() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("analyst", "analyst-demo-password"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginPageIsNotExposedAsApi() throws Exception {
        mvc.perform(get("/login")
                .with(httpBasic("editor", "editor-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownRouteIsDenied() throws Exception {
        mvc.perform(get("/unknown")
                .with(httpBasic("editor", "editor-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void securityHeadersRemainEnabled() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"));
    }
}
```

These **13 cases** cover both positive and negative paths: public 200, anonymous 401, wrong password 401, valid credentials 200, missing scope 403, sufficient scope 200, missing/invalid CSRF 403, valid CSRF and role 200, CSRF does not replace missing role 403, login route not exposed, unknown route denied, and default headers still present.

### Running and expected results

```bash
mvn test
mvn spring-boot:run
```

In another terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u editor:editor-demo-password http://localhost:8080/api/me
curl -i -u editor:editor-demo-password http://localhost:8080/api/reports
curl -i -u analyst:analyst-demo-password http://localhost:8080/api/reports
```

| Request | Expected status | Primary body |
| --- | --- | --- |
| GET /public | 200 | `public ok` |
| GET /api/me anonymous | 401 | Basic challenge |
| GET /api/me editor | 200 | `hello editor` |
| GET /api/reports editor | 403 | Denied |
| GET /api/reports analyst | 200 | `report allowed` |

These statuses are **expected from the code**, not a claim that tests were executed here. `MockMvc` checks Servlet requests inside the JVM and does not itself verify TLS/ingress, security gateways, proxy headers, or browser behavior.

## 7. For CSRF exceptions: conditions for meaningful compensating tests

If an API genuinely serves only signed webhooks without cookies/sessions, a **narrow** CSRF exemption may be needed. The record must state exact HTTP methods/paths, client types and credentials, the replacement authentication filter, anti-tampering, replay defense, load limits, and error handling.

**Mandatory additional tests:**

- Browser POSTs outside the exemption with missing/wrong CSRF still return 403, and only return 2xx with valid CSRF and user.
- Webhooks missing credentials/signatures are rejected even if the caller sends an allowed `Origin`.
- A signature valid for body A fails when the body is altered to B.
- Invalid or stale timestamps are rejected; duplicate IDs must be checked against replay.
- Methods outside the exemption and lookalike paths must not open access automatically.
- When the secret manager or replay store is unavailable, fail closed or queue per contract.
- Compensating controls must work across gateways, multiple replicas, and restarts—not merely inside a single unit test.

**Warning:** HMAC provides authenticity/integrity only if secrets are managed securely and producer/consumer agree on canonical bytes. Timestamps alone do not prevent replay within the validity window; event IDs plus atomic distributed idempotency are needed when required. Never open a public route first and rely only on checking a spoofable "header X exists" condition.

## 8. When disabling or relaxing response headers, CORS, and HSTS

### Framing and CSP

If a page must be embedded in an iframe, disabling all security headers also drops `X-Content-Type-Options`, cache directives, and other protections. Adjust only the framing policy or configure CSP `frame-ancestors` for allowed origins, while testing that other sensitive resources remain protected against framing. MockMvc proves the server emits the right headers; **browser E2E** tests are what verify browsers enforce CSP without breaking UI.

### CORS

CORS is a browser mechanism governing cross-origin response reads. CORS is neither authentication nor authorization, and does not replace CSRF. A CORS relaxation record needs the origin scheme/host/port, `allowCredentials`, `allowedMethods`/`Headers`, proxy configuration, and rationale. Test valid preflight, wrong origin, wrong method, wrong header, and confirm actual requests still obey auth/CSRF. Never use wildcards with credentialed browser responses and call it clean.

### HSTS and HTTPS

HSTS must be evaluated at the real HTTPS boundary. If TLS terminates at a reverse proxy, Spring Boot may see internal HTTP; the proper fix is configuring proxy/trusted forwarded headers appropriately rather than disabling HSTS for convenience. Test TLS certificates, HTTPS redirects, HSTS headers, subdomain coverage, and ensure clients spoofing `X-Forwarded-Proto` are not trusted.

### Sessions and tokens

For stateless APIs using only Bearer tokens, the record must state why forms/sessions were removed, that every request must carry a token, and how signature/issuer/audience/expiry/roles are verified. `@WithMockUser` **does not** prove the JWT decoder or `PasswordEncoder` works; pass real request tokens through filters/providers in integration tests.

## 9. A repeatable review/CI workflow

```text
Security config change
    |
    v
Exception ID + threat model + scope + owner
    |
    v
Reviewer approves residual risk
    |
    v
Code narrow change + compensating controls
    |
    v
JUnit/MockMvc positive and negative tests
    |
    v
CI gate + integration/browser/proxy tests where relevant
    |
    v
Deploy, audit, monitor
    |
    v
Review on expiry/change; rollback if assumptions break
```

Flag code reviews specifically on diffs containing `disable()`, `permitAll()`, `ignoringRequestMatchers`, `web.ignoring()`, CORS wildcards, `{noop}` encoders, removed JWT validators, or deleted method-security annotations. Do not assume every occurrence is automatically wrong; **reconcile against the exception register and evidence**.

CI should verify negative tests are not `@Disabled`/skipped, security filter chains are active, tests run on the right versions, and mock identities are not hiding real authentication bugs. Store test results tied to commit, config profile, and environment. Post-deploy, periodically compare effective configuration against the exception register: code review proves repository config only, not that gateways/proxies didn't override it.

## 10. Exception lifecycle: monitoring and rollback

An exception should be reviewed immediately whenever:

- A new browser/cookie client is added, or a machine endpoint begins accepting sessions.
- Matchers, methods, URLs, tenants, or `SecurityFilterChain` beans change.
- Auth provider/token format/JWT issuer/audience or key rotation changes.
- Proxy/TLS/CORS policies or load balancers change.
- Data becomes more sensitive, roles change, or administrative permissions expand.
- Replica count changes invalidate assumptions about caches/replay stores.
- Protective tests are skipped or fail, or monitoring shows anomalous denials.
- The review deadline arrives and the owner cannot provide evidence.

If conditions no longer hold, roll back: restore the baseline protection, revoke unneeded keys/permissions, migrate clients on schedule, and notify operations. Never keep a "temporary" exception indefinitely just because old tests passed once.

### Auditing and data protection

Events and logs are helpful when investigating exceptions, yet never log passwords, `Authorization` headers, session cookies, CSRF tokens, raw JWTs, API secrets, or full principals/requests. Record request IDs, event types, outcomes, reason codes, and minimal metadata; protect log access, retention, and missing-event detection. `DEBUG`/`TRACE` logging does not replace a durable audit trail.

## 11. Common pitfalls to avoid

1. **"REST APIs should disable CSRF."** Insufficient if browser credentials exist. Inspect cookies, sessions, Basic, Bearer, and real routes.
2. **"Internal-only so skip auth."** Internal networks do not stop compromised services, SSRF, or lateral movement.
3. **Only a comment in code.** Without an owner, review, tests, and rollback, exceptions become ungoverned.
4. **Using broad `permitAll`.** Admin/public routes get mixed; use exact matchers and a deny-all fallback.
5. **Using `web.ignoring` when you just want public access.** It can drop security headers and filters; prefer evaluating `permitAll`.
6. **Disabling all headers for an iframe.** Relax framing only; test that remaining headers stay active.
7. **Treating CORS as CSRF defense.** The two mechanisms address different risks.
8. **Testing only happy paths.** Test bad credentials/roles/tokens, out-of-scope paths, and dependency failures.
9. **Testing with `@WithMockUser` and assuming password/JWT validation works.** The annotation injects a mock security context, bypassing providers.
10. **Ignoring failure modes of compensating controls.** Letting requests through when the IdP/key store is down is fail-open.
11. **Ignoring proxies/gateways.** Actual runtime behavior can differ from Spring Boot source; run deployment tests.
12. **"We have tests" that are skipped.** Evidence must come from real test runs on the matching commit/version.
13. **Skipping expiry/reviews.** Client and credential models evolve; clear review triggers are essential.
14. **Logging tokens/secrets in audit logs.** Record enough to investigate without turning logs into a sensitive-data store.
15. **Unfeasible rollback.** Always keep a path to migrate clients to safe protocols and revoke exceptions when risk rises.

## 12. Pre-merge or pre-deploy checklist

| Question | When is it satisfied? |
| --- | --- |
| Baseline and deviation clear? | Know which setting changed, on which chain/route/method |
| Threat model documented? | Know clients, credentials, data, and trust boundaries |
| Narrowest possible scope? | Nothing relaxed beyond business needs |
| Server-side compensating controls? | Never relying solely on UI or well-behaved browsers |
| Positive tests PASS? | Valid requests achieve business outcomes |
| Negative tests PASS? | Bad tokens/roles/CSRF/routes are denied |
| Rest of baseline still protected? | CSRF/headers/authorization intact outside the exception |
| Real authentication tested properly? | HTTP Basic/JWT/mTLS exercises the real filter/provider |
| Evidence tied to commit/deploy? | Linked to CI run, version, and environment |
| Owner, approver, review deadline set? | Accountable person accepted the risk |
| Auditing/monitoring in place? | Detects out-of-scope abuse and control failures |
| Rollback plan ready? | Baseline can be restored if requirements change |
| No secrets leaked? | Credentials/logs/test artifacts are protected |

## 13. Conclusion

- Disabling or relaxing a Spring Security control is a risk-bearing engineering decision, **not a workaround for 401/403**.
- A strong exception record connects **baseline → deviation → rationale → boundary → compensating controls → tests → owner/approval → review/rollback**.
- Prefer **narrowly scoped changes** while keeping independent defense layers active; disabling form login must never disable auth/CSRF/headers.
- Negative tests prove callers lacking permissions, sending bad credentials, or hitting out-of-scope routes remain blocked.
- In-JVM tests do not replace checking browsers, TLS, proxies, and production dependencies.
- When assumptions change or an exception expires, review and **roll back** instead of leaving weak configuration around forever.

## References

- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Testing CSRF: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — HTTP Security Response Headers: https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html
- Spring Security — CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- OWASP — CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP — ASVS: https://owasp.org/www-project-application-security-verification-standard/