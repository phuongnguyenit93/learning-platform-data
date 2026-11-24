# Environment-Specific Configuration Management and Full Endpoint Surface Testing in Spring Security Servlet

**Context:** Java 17+, Spring Boot 3.x, Spring Security 6.x, and Jakarta Servlet. This lesson belongs to **Security Configuration**. Two capabilities go hand in hand: managing dev/staging/prod configuration without skewing security policies, and testing the full endpoint surface actually reachable, including controllers, filters, Actuator, custom Servlets, and gateway routes.

An application can block familiar APIs correctly while still leaving an admin URL exposed because of an accidentally enabled profile, a `SecurityFilterChain` not covering a new URL, or an unintentionally exposed Actuator endpoint. Therefore **effective configuration, `SecurityFilterChain` scope, and actual endpoint inventory** must be verified with repeatable tests.

## 1. Distinguishing environment values from security policies

**Environment values** are settings that vary by deployment target: CORS domains, management ports, downstream URLs, log levels, TLS/forwarded headers, secret sources, cookie settings, active profiles.

**Security policy** is the decision of who can access what: public endpoints, authentication, roles/scopes, resource ownership, CSRF, sessions, security headers, permissions across GET/POST/PUT/DELETE methods.

Some reasonable differences:
- Dev can enable DEBUG logging to understand filter chain mechanics, while production logs only what is necessary.
- Allowed frontend origins may differ between dev and prod, yet must be an exact controlled allowlist.
- Production requires TLS and proper cookie protection; dev may run HTTP on localhost.
- Debug endpoints appear only in explicitly permitted environments and must have dedicated authentication/network protection.

Invariants that should hold **across all environments**: admin operations require ADMIN permission, user/tenant data is usable only by authorized users, state-changing requests have appropriate CSRF defense, new endpoints are not public by default, and all listeners/management ports are controlled.

| Item | Can vary by environment? | Must be verified |
| --- | --- | --- |
| Logging level | Yes | Never leak tokens, cookies, or secrets into logs |
| CORS domains | Yes | Trusted origins only; never treat CORS as authorization |
| TLS, `Secure` cookies | Technical settings may differ | Production must match real deployment security |
| Admin API roles | Usually kept consistent | Users without ADMIN are always denied |
| Actuator exposure | Change only intentionally | Minimal health; sensitive endpoints never public |
| Client secrets/passwords | Different values | Never commit; retrieve from a protected secret source |
| Unclassified URLs | Should not open automatically | Deny by default with review alerts |

Never use the dev profile as an excuse to enable <code>permitAll("/**")</code> application-wide: dev tests would no longer reflect the staging/prod security policy.

## 2. Spring Profiles and effective configuration sources

Spring Boot supports <code>application.yml</code> alongside <code>application-dev.yml</code>, <code>application-staging.yml</code>, and <code>application-prod.yml</code>. Profiles can be activated via <code>SPRING_PROFILES_ACTIVE</code> or launch arguments, even multiple profiles at once. Configurations are also overridden by environment variables, system properties, command-line arguments, config imports, and external sources per Spring Boot's precedence rules.

Reference layout:

~~~text
src/main/resources/
  application.yml          # Shared settings, safe limits
  application-dev.yml      # Local observation and test configuration
  application-staging.yml  # Staging infrastructure
  application-prod.yml     # Production
~~~

Do not guess the effective value simply by opening a YAML file. Check which profiles are actually active, which source overrode a key, and the policy's effect via integration tests. If using tools to inspect <code>Environment</code> or Actuator, never print or expose secrets to logs or the web.

Three layers must be managed clearly:
1. **Tested security rules:** `SecurityFilterChain`, authorization, and CSRF/session strategy, preferably shared across environments.
2. **Non-secret values:** CORS allowlist, ports, URLs, log levels, health details.
3. **Secrets:** signing keys, passwords, client secrets, certificates/private keys; supplied from a secret manager or managed config source. Avoid committing real passwords into YAML or code.

A profile named <code>prod</code> is not automatically secure: what matters are the created beans, effective properties, registered/exposed endpoints, and which security matchers handle requests.

## 3. Spring Security mechanics to recall before inventorying URLs

On Servlet, <code>DelegatingFilterProxy</code> typically delegates requests to the <code>springSecurityFilterChain</code> bean, which is a <code>FilterChainProxy</code> managing multiple <code>SecurityFilterChain</code>s if declared by the application. It **selects the first `SecurityFilterChain` whose `RequestMatcher` matches the request**, and runs only that chain's security filters.

Thus two layers must be inspected:
- <code>http.securityMatcher(...)</code> decides **whether the request belongs to the entire chain**; multiple chains may overlap, yet only the first matching chain in order is chosen.
- <code>authorizeHttpRequests(...requestMatchers(...))</code> decides **permissions inside the selected chain**. <code>anyRequest().denyAll()</code> covers only requests belonging to that chain.

For example, a chain with <code>securityMatcher("/api/**")</code> and <code>anyRequest().denyAll()</code> **does not automatically block** <code>/internal/export</code>. If no `SecurityFilterChain` matches <code>/internal/export</code>, Spring Security does not apply those chains' security filters to the request. A chain covering the remainder or proper scope configuration is required.

In this lesson, the runnable example uses **a single chain whose default matcher matches every request**, making full-surface verification straightforward to demonstrate.

## 4. Spring Boot project illustrating a shared policy

The example uses Java 17+, Maven, **Spring Boot 3.3.5**, and Spring Security 6.x. Policy:
- GET <code>/public/info</code> is public.
- GET/POST <code>/api/reports</code> for ANALYST or ADMIN; POST also carries default CSRF protection.
- GET <code>/api/admin/audit</code> only for ADMIN.
- Actuator health is allowed publicly with minimal info.
- Other URLs hit <code>denyAll</code> under the sample policy.

**Learning purpose:** demo accounts are loaded from external configuration and stored in memory; production needs proper identity management, secrets, and MFA/auditing. This demo mainly proves endpoint scope and policy consistency across profiles.

~~~text
security-surface-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/securitysurface/
    │   │   ├── SecuritySurfaceApplication.java
    │   │   └── SecurityConfiguration.java
    │   └── resources/
    │       ├── application.yml
    │       ├── application-dev.yml
    │       └── application-prod.yml
    └── test/java/com/example/securitysurface/
        └── SecuritySurfaceTest.java
~~~

### 4.1. pom.xml

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
  <artifactId>security-surface-demo</artifactId>
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
      <artifactId>spring-boot-starter-actuator</artifactId>
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

### 4.2. Controller

Create <code>src/main/java/com/example/securitysurface/SecuritySurfaceApplication.java</code>:

~~~java
package com.example.securitysurface;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SecuritySurfaceApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecuritySurfaceApplication.class, args);
    }

    @GetMapping("/public/info")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/api/reports")
    public String reports() {
        return "reports";
    }

    @PostMapping("/api/reports")
    public ResponseEntity<String> createReport() {
        return ResponseEntity.status(HttpStatus.CREATED).body("created");
    }

    @GetMapping("/api/admin/audit")
    public String adminAudit() {
        return "audit";
    }
}
~~~

A single URL can have **multiple HTTP methods**. The sample's authorization rules apply by path while CSRF protects unsafe methods, showing that testing only GET is insufficient.

### 4.3. SecurityConfiguration.java

Create <code>src/main/java/com/example/securitysurface/SecurityConfiguration.java</code>:

~~~java
package com.example.securitysurface;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/public/info")
                    .permitAll()
                .requestMatchers("/api/admin", "/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers("/api/reports", "/api/reports/**")
                    .hasAnyRole("ANALYST", "ADMIN")
                .anyRequest()
                    .denyAll())
            .httpBasic(Customizer.withDefaults())
            // Default CSRF remains enabled.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(Environment env, PasswordEncoder encoder) {
        String analystName = env.getRequiredProperty("app.demo-users.analyst-name");
        String analystPass = env.getRequiredProperty("app.demo-users.analyst-password");
        String adminName = env.getRequiredProperty("app.demo-users.admin-name");
        String adminPass = env.getRequiredProperty("app.demo-users.admin-password");

        return new InMemoryUserDetailsManager(
            User.withUsername(analystName)
                .password(encoder.encode(analystPass))
                .roles("ANALYST")
                .build(),
            User.withUsername(adminName)
                .password(encoder.encode(adminPass))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

Key takeaways:
- No <code>securityMatcher</code> is declared, so this chain matches every request and <code>denyAll()</code> at the end actually handles unpermitted URLs.
- The health rule uses Spring Boot Actuator's <code>EndpointRequest</code>, avoiding total reliance on a hardcoded URL string when the management base path can change. The sample assumes Actuator shares the application port; a separate management port must be audited separately.
- The <code>/api/admin/**</code> rule comes before broader rules. For authorization matchers, the first matching rule decides permission.
- <code>hasRole("ADMIN")</code> corresponds to authority <code>ROLE_ADMIN</code>, created by <code>.roles("ADMIN")</code> in the example.
- Default CSRF remains enabled. For APIs used with browser cookies/sessions, do not disable CSRF merely because the URL starts with <code>/api</code>. Pure bearer-token APIs may need a different strategy, yet you must analyze how credentials are sent.
- Uses <code>Environment.getRequiredProperty</code> to require user properties at startup. Passwords are hashed with BCrypt before being placed in the demo store. In real products, do not build an identity store out of two static accounts.

### 4.4. YAML Configuration

Create <code>src/main/resources/application.yml</code>:

~~~yaml
app:
  demo-users:
    analyst-name: ${DEMO_ANALYST_NAME}
    analyst-password: ${DEMO_ANALYST_PASSWORD}
    admin-name: ${DEMO_ADMIN_NAME}
    admin-password: ${DEMO_ADMIN_PASSWORD}

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
~~~

Create <code>src/main/resources/application-dev.yml</code>:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Create <code>src/main/resources/application-prod.yml</code>:

~~~yaml
logging:
  level:
    org.springframework.security: WARN
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Both profiles use **the exact same `SecurityConfiguration`** and the same authorized endpoint list. The YAML only adjusts log levels and cookie attributes. Cookie configuration takes effect if the application issues session cookies; the example uses HTTP Basic to test roles, not a complete session-based login system.

The <code>DEMO_*</code> variables are required. Do not provide weak fallback passwords in config files or put production secrets into the repository. For production deployment, use a secret manager, least privilege, and credential rotation. If required configuration is missing, the application should fail startup rather than run with the wrong policy.


## 5. Starting with a profile and observing policy

On Windows using PowerShell, open the directory containing <code>pom.xml</code>:

~~~powershell
$env:DEMO_ANALYST_NAME = "analyst"
$env:DEMO_ANALYST_PASSWORD = "local-analyst-pass"
$env:DEMO_ADMIN_NAME = "admin"
$env:DEMO_ADMIN_PASSWORD = "local-admin-pass"
$env:SPRING_PROFILES_ACTIVE = "dev"
mvn spring-boot:run
~~~

These are strictly fake credentials for local demo. Never put real secrets into shell history or pipeline logs. In another terminal, use <code>curl.exe</code> on Windows (avoiding the <code>curl</code> alias in Windows PowerShell):

~~~powershell
curl.exe -i http://localhost:8080/public/info
curl.exe -i http://localhost:8080/api/reports
curl.exe -i -u "analyst:local-analyst-pass" http://localhost:8080/api/reports
curl.exe -i -u "analyst:local-analyst-pass" http://localhost:8080/api/admin/audit
curl.exe -i -u "admin:local-admin-pass" http://localhost:8080/api/admin/audit
curl.exe -i http://localhost:8080/actuator/health
curl.exe -i -u "admin:local-admin-pass" http://localhost:8080/api/unknown
~~~

Expected results when the application runs normally:

| Request | Expected | Reason |
| --- | --- | --- |
| GET <code>/public/info</code> anonymous | 200 and body <code>public</code> | Intentionally public |
| GET <code>/api/reports</code> anonymous | 401 | HTTP Basic requires authentication |
| GET <code>/api/reports</code> with ANALYST | 200, <code>reports</code> | Sufficient role |
| GET <code>/api/admin/audit</code> with ANALYST | 403 | Missing `ROLE_ADMIN` |
| GET <code>/api/admin/audit</code> with ADMIN | 200, <code>audit</code> | Sufficient role |
| GET <code>/actuator/health</code> anonymous | 200 if health is UP | Minimal health exposed |
| GET <code>/api/unknown</code> with ADMIN | 403 | `denyAll` rule rejects unlisted URLs |

A URL without a registered controller can still return **403** because Spring Security rejects it before Spring MVC checks routes. Therefore a 403 result does not prove an endpoint exists; an audit needs both mapping inventory and HTTP behavior.

Try switching profiles with <code>$env:SPRING_PROFILES_ACTIVE = "prod"</code>, restarting, and running the same matrix. Testing locally over HTTP does not prove all production TLS/`Secure` cookie settings work; those checks must run against the real domain and deployment infrastructure.

### POST and CSRF

GET/POST requests to the same path can be handled differently. The demo keeps CSRF enabled, so a POST with HTTP Basic and **no CSRF token** returns 403:

~~~powershell
curl.exe -i -u "analyst:local-analyst-pass" -X POST http://localhost:8080/api/reports
~~~

This is the behavior of the current configuration. For browsers using session cookies, a CSRF token must be issued and submitted per the chosen mechanism. For APIs not using cookies or auto-sent credentials, properly evaluate the threat model before deciding the scope needing CSRF; never disable it app-wide just to make a POST test pass.

## 6. Writing integration tests for the security surface

Create <code>src/test/java/com/example/securitysurface/SecuritySurfaceTest.java</code>:

~~~java
package com.example.securitysurface;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "app.demo-users.analyst-name=analyst",
    "app.demo-users.analyst-password=test-analyst-pass",
    "app.demo-users.admin-name=admin",
    "app.demo-users.admin-password=test-admin-pass"
})
@AutoConfigureMockMvc
class SecuritySurfaceTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    RequestMappingHandlerMapping mvcMappings;

    @Test
    void publicEndpointAndHealthAreIntentional() throws Exception {
        mvc.perform(get("/public/info"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/actuator/health"))
            .andExpect(status().isOk());
    }

    @Test
    void reportsRequireAuthentication() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/reports")
                .with(httpBasic("analyst", "test-analyst-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports"));
    }

    @Test
    void roleBoundaryIsEnforced() throws Exception {
        mvc.perform(get("/api/admin/audit")
                .with(httpBasic("analyst", "test-analyst-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin/audit")
                .with(httpBasic("admin", "test-admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("audit"));
    }

    @Test
    void postRequiresCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("analyst", "test-analyst-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/reports")
                .with(httpBasic("analyst", "test-analyst-pass"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created"));
    }

    @Test
    void unknownRouteIsNotAccidentallyPublic() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("admin", "test-admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void importantControllerMappingsExist() {
        Set<String> paths = mvcMappings.getHandlerMethods()
            .keySet()
            .stream()
            .flatMap(info -> info.getPatternValues().stream())
            .collect(Collectors.toSet());

        assertThat(paths).contains(
            "/public/info",
            "/api/reports",
            "/api/admin/audit"
        );
    }
}
~~~

The tests use fake data supplied in <code>@SpringBootTest</code>; they do not need credentials from a real system. They check HTTP Basic, roles, CSRF, and default deny, while checking a set of paths against controller mappings registered in the context.

Run the same suite against each environment:

~~~powershell
mvn test "-Dspring.profiles.active=dev"
mvn test "-Dspring.profiles.active=prod"
~~~

For staging, add <code>application-staging.yml</code> and run the corresponding profile with the suite. Green tests mean the policy of the **Spring context at test time** satisfies the matrix; it does not automatically test TLS listeners, firewalls, proxies, DNS, or separate management ports. After deployment, run smoke/integration tests against actually permitted routes.

The test reading <code>RequestMappingHandlerMapping</code> is one way to inspect MVC inventory, **not a complete way to enumerate every endpoint**. It omits endpoints handled by custom Servlets, Spring Security filters, the Actuator management context, or ingress/gateway. HTTP methods must also be extracted from mapping conditions if the inventory needs exact methods rather than path strings alone.

## 7. Endpoint surface has more layers than controllers

The **endpoint surface** is every route a client or another component can trigger. For a complete audit, gather routes from multiple sources and determine real access paths in each environment.

| Source | Example | What to check |
| --- | --- | --- |
| Spring MVC controllers | GET/POST/PUT/DELETE in <code>@RequestMapping</code> | HTTP method, path, role, tenant/ownership |
| Other `HandlerMapping`s | Functional endpoints, resource handlers, error handlers | Does the route exist and which security policy does it receive |
| Spring Security filters | Login, logout, OAuth callbacks, CSRF, request cache | Filter-handled URLs may not appear in controllers |
| Actuator | Health, info, env, metrics, mappings, heapdump | Exposure, returned details, roles, port |
| Manually registered Servlets/filters | <code>ServletRegistrationBean</code>, library filters | Whether they sit inside the intended security chain |
| Developer tooling | H2 console, Swagger/OpenAPI UI, debug controllers | Expose only intentionally; never expose sensitive info publicly |
| Other protocols/flows | WebSocket handshake, SSE, file upload | Connection authentication, operation authorization |
| Infrastructure | Gateway, ingress, proxy, management listener | Domain, path rewrite, port, TLS, internal/public routing |

When Spring Boot Actuator is enabled, distinguish **instantiated endpoints**, **exposed over HTTP**, and **who is permitted access**. Configuring <code>management.endpoints.web.exposure.include</code> only controls exposure; security and networking remain separate layers.

In the demo, only health is exposed over HTTP. Never publicly expose <code>/actuator/env</code>, <code>/actuator/configprops</code>, <code>/actuator/heapdump</code>, or <code>/actuator/mappings</code> for observation convenience. If operational management endpoints are needed, use an internal network or clear authentication/authorization layers.

If <code>management.server.port</code> differs from the main port, management may run in a separate application context. **You cannot assume** the application port's `SecurityFilterChain` is enough to protect the management port. Audit both listeners and network/ingress rules. Custom Spring Security beans also mean you should not assume all of Boot's default Actuator security config continues to be auto-generated.

## 8. Building a structured inventory

Each endpoint should have at least these fields:

| Field | Purpose |
| --- | --- |
| HTTP method + URL/matcher | Identify exact entry points, avoiding missed POST or OPTIONS |
| Registration source | Controller, filter, Actuator, Servlet, gateway |
| Env and exposed port | Dev/staging/prod, application/management port |
| Authentication | Anonymous, session, Basic, bearer token, OAuth/OIDC |
| Authorization | Roles, scopes, and permissions on specific resources |
| CSRF/CORS | Whether token is needed, which origins/methods/headers are allowed |
| Owner | Team responsible for the endpoint and changes |
| Test/expected status | Tests for anonymous, right role, wrong role, and edge cases |
| Data sensitivity | Public, personal, internal, sensitive |

Capture a verified inventory snapshot of the running version and compare against the previous snapshot whenever adding controllers, libraries, Actuator, or gateway rules. Do not treat OpenAPI listings as the sole source of truth: docs can miss filter endpoints, custom Servlets, non-MVC routes, and undocumented paths. Logs also only prove **previously observed requests**, not that an endpoint does not exist.

You can use Spring MVC's <code>RequestMappingHandlerMapping</code> and <code>RequestMappingInfo</code> method conditions to collect MVC routes. When Actuator mappings are needed, enable them only in controlled environments and restrict permissions/network; never expose system introspection endpoints to the Internet. Cross-check against Servlet registrations, `SecurityFilterChain`s, gateways, and real deployment config.

## 9. Access matrix testing: seeing 403 alone is not enough

Reference matrix for the demo:

| Endpoint | Anonymous | ANALYST | ADMIN |
| --- | --- | --- | --- |
| GET <code>/public/info</code> | 200 | 200 | 200 |
| GET <code>/api/reports</code> | 401 | 200 | 200 |
| GET <code>/api/admin/audit</code> | 401 | 403 | 200 |
| POST <code>/api/reports</code> missing CSRF | 403 | 403 | 403 |
| POST <code>/api/reports</code> with CSRF | 401 | 201 | 201 |
| GET <code>/actuator/health</code> when UP | 200 | 200 | 200 |
| GET <code>/api/unknown</code> | Denied | 403 | 403 |

Distinguish:
- **200** means the request succeeded, yet if a private resource returns 200 anonymously that signals a policy bug.
- **401** usually indicates the authentication entry point requesting credentials; with HTTP Basic there is normally <code>WWW-Authenticate</code>.
- **403** can come from missing role, missing CSRF, or a `denyAll` rule; it does not by itself prove an MVC route exists.
- **404** can mean the route does not exist, yet it does not prove the path lacks an authentication guard.
- **302** may come from web form login, while an API expecting Basic/JWT might expect 401. Check which security chain was actually selected.

A real application matrix must also test ordinary roles accessing another user's or tenant's data. A user permitted to call <code>GET /api/reports/{id}</code> is not necessarily permitted to read every user's report. URL authorization must be paired with per-resource permission checks.

## 10. Error-prone environment scenarios

### Specialized chain shadowing or leaving URLs uncovered

When there are multiple `SecurityFilterChain`s, <code>@Order(1)</code> is evaluated before <code>@Order(2)</code>. A general matcher chain placed first can prevent a narrower chain behind it from ever running. Conversely, creating only a chain for <code>/api/**</code> can leave other URLs matching no chain at all. Test all matchers thoroughly and maintain a chain covering protected URLs.

### Cross-origin CORS

CORS governs whether JavaScript from another origin can read responses; **it does not replace authentication/authorization**. A frontend on another domain may need OPTIONS preflight and allowed origins, methods, and headers. CORS with credentials cannot combine a wildcard origin <code>*</code> for that response type. Profiles may provide different allowlists, which must be tightly managed and tested.

### CSRF and sessions

Browsers automatically attach matching cookies by context, so cookie/session apps face CSRF risk. SameSite helps defend but does not replace necessary CSRF checks. APIs using explicitly attached bearer tokens can use a different strategy, yet must account for whether the app accepts cookies or hosts form/login endpoints in the same deployment.

### TLS, reverse proxies, and URL rewriting

Production requires TLS on public paths; behind a proxy, client and backend host/scheme/path information can differ. Trust forwarded headers only from trusted proxies. Test actual matchers after the gateway adds/strips path prefixes; do not assume the client-visible URL is always the URL Spring Security matches against.

### Static, error, and HTTP dispatches

Static resources, <code>/error</code>, forward/error dispatches, multipart uploads, and WebSocket handshakes are also part of the request surface. Intentional <code>permitAll</code> may be needed for static/error so app behavior is not broken, yet never enable broad <code>web.ignoring()</code> just to fix a broken screen. <code>permitAll</code> inside a chain still traverses security filters, whereas ignored paths or unmatched paths behave differently.

### Dev-only endpoints

A <code>@Profile("dev")</code> bean can cause a controller to exist only in dev; dev inventory must record it, and production tests must verify it is absent and no equivalent URL is exposed by another library. A profile is not an authentication mechanism: dev endpoints also need network/permission controls if they contain sensitive data.


## 11. Endpoint surface review process when changing the system

1. **Discover** every new/modified/deleted route: MVC mappings, Servlet/filter registrations, Actuator endpoints, gateway/ingress, and new profile beans.
2. **Assign owner, data sensitivity, and least-privilege permissions** for each method + route. For resource IDs, define ownership/tenant rules.
3. **Identify the selected `SecurityFilterChain`** via matcher order; find overlaps or missing catch-alls. Only then analyze authorization rules inside the chain.
4. **Build an access matrix:** anonymous, valid user, user missing role, admin, wrong tenant, missing/wrong CSRF, and other methods. Record expected response/body, not just status.
5. **Run tests for every profile** in CI. Any change making a new endpoint public or altering security status must be reviewed before release.
6. **Verify post-deployment** on real domains/ports: TLS, proxies, management listeners, CORS preflight, cookies, and network policy. Reconcile against the running artifact/commit inventory.
7. **Monitor drift** between approved policy and runtime configuration. When an unclassified endpoint is discovered, maintain default deny and route through review.

You do not need an external Internet scanner to take the first steps: most initial checks can run in MockMvc/integration tests and route inventories exported from a controlled runtime. External testing must be performed only against authorized systems, domains, and access scopes.

## 12. Common mistakes table

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Dev has a <code>permitAll("/**")</code> chain | Local tests mask broken permissions | Run a shared baseline policy across all profiles |
| Default passwords/secrets in files | Weak credentials easily leak on deploy | Require external secrets; fail fast if missing |
| Only an <code>/api/**</code> chain thinking <code>denyAll</code> protects the whole app | Some URLs receive no security filters from that chain | Add properly scoped/catch-all chains |
| Placing <code>/**</code> matcher before a narrow chain | Specialized chain is never selected | Order narrow chains first; test overlaps |
| Searching only <code>@RestController</code> | Misses Actuator, login/logout filters, custom Servlets | Aggregate inventory from all sources |
| Enabling extra Actuator endpoints without checking roles/ports | Leaks config, heapdump, or operational data | Audit exposure, security, and network |
| Treating CORS as access control | Other clients still call the API | Enforce independent server-side authorization |
| Disabling CSRF app-wide to make POST succeed | Cookie sessions become vulnerable to CSRF | Design CSRF per threat model and per chain |
| Testing only anonymous calls | Misses regular users reading/editing admin/other-tenant data | Test roles, ownership, and negative cases |
| Treating 403 as proof an endpoint exists | Misinterprets route mapping | Inspect route registry and response |
| Testing only one port or one profile | Misses management context or prod drift | Test all required profiles and listeners |
| Trusting one YAML file instead of runtime config | Overlooks environment overrides | Safely inspect effective values and run tests |

## 13. Self-check

**Scenario 1:** The dev profile gives all endpoints <code>permitAll</code>, while the prod profile requires authentication. Are green dev tests enough to guarantee prod is safe?  
**Answer:** No. Dev tests no longer reflect the security baseline; you must test proper rules for every role on both profiles.

**Scenario 2:** The sole chain has <code>securityMatcher("/api/**")</code> and <code>anyRequest().denyAll()</code>. Is endpoint <code>/internal/export</code> guaranteed to be blocked by Spring Security?  
**Answer:** No. That URL lies outside the chain's matcher scope; another matching chain or design change is needed so every protected endpoint is handled by a chain.

**Scenario 3:** Setting <code>management.endpoints.web.exposure.include=health,env</code> automatically makes <code>/actuator/env</code> public, right?  
**Answer:** Not automatically; exposure and authorization/network are separate layers. Even so, the new surface has expanded and must be audited and protected before deployment.

**Scenario 4:** Why are all paths from <code>RequestMappingHandlerMapping</code> not the entire endpoint surface?  
**Answer:** It focuses on MVC handler mappings; filter endpoints, Actuator on separate contexts/ports, other registered Servlets, and gateways may not appear there.

**Scenario 5:** Can green MockMvc tests under dev/prod replace testing real TLS, ingress, and management ports?  
**Answer:** No. They test Spring context behavior in tests; security on infrastructure listeners and entry points must be verified additionally after deployment.

**Key takeaway:** environments govern operational values, whereas access policy requires a secure baseline and continuous testing. List **every method + endpoint + port + profile**, identify which chain actually processes it, apply least privilege, and test denied cases. New or unclassified endpoints must be discovered before becoming public entry points.
