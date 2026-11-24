# Configuring by Environment Without Unintentionally Opening Permissions

The same Spring Boot application can run on a developer's machine (local/dev), in testing environments (test/staging), and in production. Environments typically differ in ports, databases, integration endpoints, machine identities, certificates, and operational parameters. However, **the core authorization policy must never be accidentally relaxed** merely because a profile, environment variable, or configuration flag changes.

This lesson focuses on **modern Spring Security configuration with SecurityFilterChain**, Spring Profiles, externalized configuration, and feature flags. The goal is allowing **operational parameters and experimental features** to vary while keeping access governed by **deny by default, least privilege, and verify every environment**.

The hands-on example uses Java 17+, Spring Boot 3.3.6, and Spring Security 6.x. This is a localhost lab: in-memory accounts are activated only in the local profile; outside local, the example intentionally **provides no login accounts** so APIs requiring authentication deny by default. For production, replace this with a real identity mechanism (such as OAuth2 Resource Server or a secure user store), infrastructure controls, and a supported dependency version. Never treat these demo accounts as a production login solution.

## 1. The Problem: Environments Differ, Yet Permissions Must Be Intentional

Imagine an application with three paths:

- GET /api/ping: basic liveness check, intentionally public by design.
- GET /api/me: returns the current principal, only for authenticated users.
- GET /internal/diagnostics: supports checks on a local machine, only for callers with ROLE_OPS; **does not exist as a Controller when running in production**.

Locally, the development team wants diagnostics and test accounts enabled. In production, an operator accidentally sets APP_DIAGNOSTICS_ENABLED=true. If code simply checks "if flag=true then permitAll," or a local configuration overrides the production SecurityFilterChain, the application can expose sensitive APIs.

**Sound design** asks these questions before writing code:

1. Which endpoints are genuinely public in **every** environment?
2. Which identities and permissions are trusted, even if a flag is turned on by mistake?
3. What conditions permit a diagnostic route or bean to exist?
4. If a profile is missing, misspelled, or both local and prod are active simultaneously, how will the application behave?
5. If a property is overridden by command-line, environment variable, or config outside the JAR, which guardrails still hold?
6. How do you verify **actual responses and side effects**, not just read config files?

A profile is not an automatic security boundary. It is a configuration selection condition. **Safety comes from explicit policies, independent guardrails, trustworthy identity data, and testing against the configuration actually deployed.**

## 2. Distinguishing Profiles, Properties, Secrets, and Security Policies

| Concept | What is it used for? | Risk when misused |
| --- | --- | --- |
| **Spring Profile** | Activates a group of beans or config documents by name such as local, test, prod. | A local profile can be activated accidentally in a real environment; multiple profiles can be active at once. |
| **Externalized property** | Configures partner URLs, timeouts, ports, logging, feature flags via YAML, env, or CLI. | Higher-precedence sources can override safe values in application.yml. |
| **Feature flag** | Enables/disables a feature or operational mode. | Using a flag to bypass authentication/authorization can open permissions too broadly. |
| **Secret** | Passwords, private keys, client secrets, signing tokens, or database credentials. | Committing secrets to repos, printing them to logs, or sharing them between local and production. |
| **SecurityFilterChain** | Enforces HTTP rules, authentication, and authorization for matching requests. | A chain with an overly narrow securityMatcher can leave requests outside all chains. |
| **Authorization rule** | Decides who may call a path/method or act on a resource. | Overly broad permitAll(), misordered matchers, or missing owner/tenant checks. |
| **Deployment policy** | Restricts allowed runtime configs, runtime identities, networks, secrets, and pre-deploy checks. | Relying only on YAML inside the JAR while ignoring final values in Kubernetes/CI/CD. |

**Profiles are suited for selecting features or deployment adapters.** Properties suit operational parameters or feature flags. **Authorization** must decide allowed actions using trusted identities; there should never be logic saying "if dev, bypass all security."

What to avoid:

~~~java
// Anti-pattern: configuration fragment that MUST NOT go into a real app.
if (environment.acceptsProfiles(Profiles.of("dev"))) {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().permitAll());
} else {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated());
}
~~~

If dev is enabled on staging/production or runtime values differ from expectations, the entire API can become public. Even admin-only endpoints become over-exposed. This is a **policy-altering bug**, not merely a profile naming mistake.

## 3. How Does Spring Boot Resolve Effective Configuration?

Spring Boot supports **application.yml**, **application-{profile}.yml**, environment variables, system properties, command-line arguments, and external config sources outside the JAR. Sources merge by precedence: **higher-precedence sources can override lower-precedence sources**.

Example:

~~~yaml
# src/main/resources/application.yml
app:
  diagnostics:
    enabled: false
~~~

~~~yaml
# src/main/resources/application-local.yml
app:
  diagnostics:
    enabled: true
~~~

~~~yaml
# src/main/resources/application-prod.yml
app:
  diagnostics:
    enabled: false
~~~

When running with the local profile, values from application-local.yml normally override the base file, making app.diagnostics.enabled true. When running with prod, false is used **unless overridden by a higher-precedence source**.

Command-line example:

~~~bash
java -jar target/security-env-demo-1.0.0.jar --spring.profiles.active=prod --app.diagnostics.enabled=true
~~~

In Spring Boot, command-line arguments can override values inside files by default. Therefore **setting false in application-prod.yml is not an absolute guarantee**. That is why we need multiple independent conditions, and a SecurityFilterChain must never open permissions based on a flag.

### 3.1. Notable Override Sources

- application.yml inside the application.
- application-local.yml and application-prod.yml when the corresponding profile is active.
- Config files placed outside the artifact, such as mounted by a container/orchestrator.
- Environment variables, e.g. APP_DIAGNOSTICS_ENABLED.
- Java system properties, e.g. -Dapp.diagnostics.enabled=true.
- Command-line properties, e.g. --app.diagnostics.enabled=true.
- Test properties or test-framework overrides in test environments.

**Do not memorize a simplified precedence list and assume it holds in all cases.** Spring Boot has specific PropertySource ordering, location groups, and config import rules; versions can also add config sources. When in doubt, consult the exact version's docs and verify effective values in the running environment.

Never print the entire Environment or expose /env to clients just to check a flag: it can contain passwords, tokens, internal URLs, or sensitive metadata. When observability is needed, log only **profile names, publishable boolean flags, and build identifiers** under a safe logging policy.

### 3.2. Multiple Active Profiles

~~~bash
java -jar target/security-env-demo-1.0.0.jar --spring.profiles.active=local,prod
~~~

Spring Boot can activate multiple profiles simultaneously. With multiple profile-specific documents, load order and precedence decide the final property. **Never assume "if prod is present, all local configuration disappears."**

Annotation:

~~~java
@Profile("local")
~~~

only checks that local is active; it **still evaluates true** when both local and prod are active. Conversely, the expression:

~~~java
@Profile("local & !prod")
~~~

requires local and **not prod**. The profile expression uses AND/NOT operators supported by Spring Framework. It fits a local-only feature well, though it still does not replace authorization or network policies.

Profile names should be standardized in the project: local, test, staging, and prod are not privileged security keywords. Use consistent names, validate them in pipelines, and never rely on spelling variants like prod/production to guarantee safety.

## 4. Safety Principles When Designing SecurityFilterChain

### 4.1. One Core Protection Policy, Minimal Variation Across Environments

When an API shares the same permission model everywhere, keep **one SecurityFilterChain** with the same rules:

~~~java
// Illustrative configuration snippet inside a @Configuration class.
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
        .requestMatchers(HttpMethod.GET, "/internal/diagnostics")
            .hasRole("OPS")
        .anyRequest().denyAll()
    ).httpBasic(Customizer.withDefaults()).build();
}
~~~

Regardless of profile:

- GET /api/ping is intentionally public, because that is a deliberate business decision.
- GET /api/me requires a valid Authentication.
- GET /internal/diagnostics requires ROLE_OPS **even locally**.
- Every unlisted method and URL is denied by denyAll().

The snippet uses HTTP Basic for the lab; **production authentication mechanisms** must be replaced with an appropriately designed configuration. Changing how credentials are verified does not mean changing public/member/admin permissions.

### 4.2. Do Not Use permitAll to "Debug Faster"

Dangerous pattern:

~~~java
// Anti-pattern: flawed illustrative snippet.
if (diagnosticsEnabled) {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/internal/**").permitAll());
}
~~~

An environment variable becomes an access-opening switch. If diagnostics are needed, use a **dedicated path, dedicated role, and create the bean only in the right environment**, alongside network access controls. A feature flag decides only whether a feature exists, never automatically grants permission to use it.

### 4.3. SecurityMatcher Differs from requestMatchers

When using multiple SecurityFilterChains:

- **securityMatcher("/api/**")** restricts **the entire chain** to requests matching that scope.
- **requestMatchers("/api/admin/**").hasRole("ADMIN")** is an authorization rule **inside an already-selected chain**.
- **anyRequest().denyAll()** applies only to requests belonging to the selected chain; it does not protect URLs outside the chain's securityMatcher.
- If **no chain matches a request**, Spring Security may **leave that request unprotected**.

This bug happens frequently when creating a separate chain for local/admin and forgetting a fallback.

~~~java
// Anti-pattern: only an /api/** chain exists; URLs outside /api may be unprotected.
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated())
        .build();
}
~~~

If you genuinely need multiple chains, keep a **fallback SecurityFilterChain with no narrow securityMatcher** and add rules blocking all unpermitted paths. Manage @Order, each chain's authentication filters, and test out-of-scope paths. If splitting chains is unnecessary, **one chain covering the whole application is easier to verify**.

### 4.4. HTTP Methods, Patterns, and Precedence

~~~java
.requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
~~~

permits **GET**, which does not automatically permit POST/DELETE on the same path. Matchers are evaluated in declaration order; put specific rules before general rules. hasRole("OPS") checks authority ROLE_OPS; hasAuthority("OPS") is a different condition.

Even so, SecurityFilterChain does not understand every business rule: GET /api/orders/42 passing authenticated() still requires the Service to check owner/tenant. An environment flag must never bypass that check.

## 5. Enabling a Local Feature with Two Independent Conditions

To ensure an experimental endpoint exists only when truly intended, the example uses **two conditions**:

1. Profile **local** is active and **prod is not**.
2. Flag **app.diagnostics.enabled=true** is explicitly set.

In addition, **SecurityFilterChain always requires ROLE_OPS** if the route is present. That creates three guardrails: environment selection, intentional feature activation, and role authorization on invocation.

Example:

~~~java
@RestController
@Profile("local & !prod")
@ConditionalOnProperty(
    prefix = "app.diagnostics",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
class LocalDiagnosticsController {
    // GET /internal/diagnostics is declared here.
}
~~~

**@ConditionalOnProperty** with havingValue="true" matches only when the property resolves to true under Boot's rules; **matchIfMissing=false** ensures an absent property does not enable the feature. In application.yml, the default value is also set to false so operators see the safe intent upfront.

| Active profiles | Effective flag | Diagnostics controller? | Access condition when present |
| --- | --- | --- | --- |
| No local | false or true | **No** | No diagnostics handler exists. |
| local | false | **No** | No diagnostics handler exists. |
| local | true | **Yes** | Only principals with ROLE_OPS. |
| prod | true via accidental override | **No** | Profile guard prevents bean registration. |
| local and prod | true | **No** | Expression local & !prod is false. |
| test/staging | true | **No** | local profile is absent. |

What to avoid:

- @Profile("!prod") on a debug bean: when no profile is active, !prod is still true, enabling debug in unnamed environments.
- @ConditionalOnProperty(name="debug", matchIfMissing=true): a forgotten property enables the feature.
- Using conditions to **turn off authorization filters** instead of merely gating bean existence.
- Re-exposing the same debug endpoint in another unguarded Controller.
- Relying solely on a profile guard without controlling identity, roles, network, and rate limits.

**Note:** If an actual deployment sets profile local without enabling prod, this guard treats it as local. Hence CI/CD must validate expected profiles and reject mismatched deployments; an application cannot tell by itself that a profile name is misused on a production cluster.

## 6. Hands-On Java 17 / Spring Boot 3.3.6 Lab

We build an application whose single JAR runs under either the local or prod profile. Authorization configuration code **is never relaxed by profile**. Demo accounts exist only when local and not prod; other environments have an empty user store so **demo accounts cannot log in**.

**Prerequisites:** JDK 17+, Maven 3.9+, port 8080 free. All testing uses localhost and dummy data.

### 6.1. Project Structure

~~~text
security-env-demo/
  pom.xml
  src/main/resources/
    application.yml
    application-local.yml
    application-prod.yml
  src/main/java/com/example/envdemo/
    SecurityEnvApplication.java
    ApiController.java
    LocalDiagnosticsController.java
    SecurityConfig.java
  src/test/java/com/example/envdemo/
    LocalProfileTests.java
    LocalDisabledTests.java
    ProductionProfileTests.java
    MixedProfilesTests.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-env-demo</artifactId>
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

No Spring WebFlux dependency is needed: the example is Spring MVC/Servlet with SecurityFilterChain and HttpSecurity. If a real project uses WebFlux, it needs ServerHttpSecurity and SecurityWebFilterChain accordingly.

### 6.3. application.yml

~~~yaml
spring:
  application:
    name: security-env-demo

app:
  diagnostics:
    enabled: false
~~~

The base file **does not set spring.profiles.active=local**. Profiles are chosen explicitly at runtime/deployment. Without the local profile, demo accounts and diagnostics are not created.

### 6.4. application-local.yml

~~~yaml
app:
  diagnostics:
    enabled: true
~~~

The local profile enables only **the conditional feature**; it contains no anyRequest().permitAll() and defines no weaker SecurityFilterChain. When running locally, the experimental endpoint remains restricted to ROLE_OPS.

### 6.5. application-prod.yml

~~~yaml
app:
  diagnostics:
    enabled: false
~~~

The production file sets false as an intended value, yet **does not rely on it alone**. An external property could override this value; @Profile("local & !prod") still prevents the diagnostics bean from existing when prod is active.

### 6.6. SecurityEnvApplication.java

~~~java
package com.example.envdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityEnvApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityEnvApplication.class, args);
    }
}
~~~

The main class sits in root package com.example.envdemo so Spring Boot scans beans in the same package. Never activate the local profile in main, because that would affect every environment sharing the artifact.

### 6.7. ApiController.java

~~~java
package com.example.envdemo;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }
}
~~~

**GET /api/ping** is an intentionally public endpoint returning JSON status=ok. Do not place debug data, dependency versions, or environment details here.

**GET /api/me** requires authentication. The identity comes from the Authentication verified by Spring Security, never trusting a client-sent userId in query params or headers. In real apps returning sensitive profiles, still enforce object permissions and set suitable cache policies.

### 6.8. LocalDiagnosticsController.java

~~~java
package com.example.envdemo;

import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("local & !prod")
@ConditionalOnProperty(
    prefix = "app.diagnostics",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class LocalDiagnosticsController {

    @GetMapping("/internal/diagnostics")
    public Map<String, String> diagnostics() {
        return Map.of("mode", "local", "details", "demo-only");
    }
}
~~~

The Controller returns a fixed string and **never prints Environment, secrets, connection strings, principal details, or stack traces**. Even locally, diagnostic data should remain minimal.

**The two conditions above decide only whether the bean exists.** Route access must still be checked independently by SecurityFilterChain.

### 6.9. SecurityConfig.java

~~~java
package com.example.envdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET,
                    "/internal/diagnostics").hasRole("OPS")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            Environment env,
            PasswordEncoder encoder) {

        boolean localOnly =
            env.acceptsProfiles(Profiles.of("local & !prod"));

        if (!localOnly) {
            // Intentionally provides no demo credentials in prod,
            // test, or when the local profile is absent.
            return new InMemoryUserDetailsManager();
        }

        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-learner"))
            .roles("USER")
            .build();

        UserDetails operator = User.withUsername("operator")
            .password(encoder.encode("demo-ops"))
            .roles("USER", "OPS")
            .build();

        return new InMemoryUserDetailsManager(learner, operator);
    }
}
~~~

Analyzing the decisions:

1. **No @Profile on SecurityFilterChain.** The filter chain bean always exists, even if profiles are absent. It uses no narrow securityMatcher, so by default it covers all application requests per chain mechanics.
2. **GET /api/ping is intentionally public**, with no env-based logic opening extra URLs.
3. **GET /api/me uses authenticated()**; every profile requires a valid identity.
4. **GET /internal/diagnostics requires ROLE_OPS** regardless of flags, so a USER locally still gets 403.
5. **anyRequest().denyAll()** ensures unlisted methods/paths never open automatically.
6. **PasswordEncoder uses BCrypt**, never storing plain passwords in UserDetails.
7. **UserDetailsService is always a bean**, yet outside local & !prod returns an empty user store. No demo user can authenticate there.
8. **HTTP Basic config still operates at the protocol level**, yet outside local no demo principal exists; login-protected APIs return 401 for demo credentials. This is **fail-closed for practice**, not a production identity solution.
9. **Default CSRF is not disabled.** This lesson uses only GET. For apps with cookies or browser-attached credentials and POST/PUT/PATCH/DELETE operations, evaluate CSRF and client patterns per threat model.
10. HTTP Basic only Base64-encodes credentials; **HTTPS is mandatory** when exchanging credentials over real networks. The lab uses dummy data on localhost only.

Never replace the non-local branch with a default user having a hardcoded password. When a real product runs in prod, integrate OAuth2/OIDC, JWT Resource Server, opaque-token introspection, or an approved identity source. **Swapping identity providers may require separate authn configuration**, yet permission policies in authorizeHttpRequests must still be verified and never broadened implicitly.

## 7. Running the Same Artifact Across Environments

### 7.1. Building and Running Locally

In the security-env-demo directory:

~~~bash
mvn test
mvn package
java -jar target/security-env-demo-1.0.0.jar --spring.profiles.active=local
~~~

Use a second terminal to test. On Windows PowerShell use **curl.exe**; Linux/macOS normally use **curl**.

~~~powershell
curl.exe -i http://localhost:8080/api/ping
curl.exe -i http://localhost:8080/api/me
curl.exe -i -u learner:demo-learner http://localhost:8080/api/me
curl.exe -i -u learner:demo-learner http://localhost:8080/internal/diagnostics
curl.exe -i -u operator:demo-ops http://localhost:8080/internal/diagnostics
~~~

**Expected** HTTP results:

| Request | Status | Reason |
| --- | --- | --- |
| Anonymous GET /api/ping | 200 | Intentionally public route; JSON body has status=ok. |
| Anonymous GET /api/me | 401 | Missing HTTP Basic credentials. |
| GET /api/me with learner/demo-learner | 200 | Authenticated; body user=learner. |
| GET /internal/diagnostics with learner | 403 | Valid credentials but missing ROLE_OPS. |
| GET /internal/diagnostics with operator/demo-ops | 200 | Has ROLE_OPS and bean exists locally. |
| POST /api/ping with operator | 403 if CSRF passes | POST method is unpermitted; missing CSRF can block even earlier. |

Extra headers vary by Servlet container. HTTP Basic normally includes a WWW-Authenticate header on 401 responses. For public GETs, **do not send invalid Authorization headers**, because the authentication filter can process faulty credentials before reaching permitAll() authorization.

### 7.2. Running prod with Flag Intentionally Mis-Enabled

Stop the local instance and run:

~~~bash
java -jar target/security-env-demo-1.0.0.jar --spring.profiles.active=prod --app.diagnostics.enabled=true
~~~

Expected outcomes:

- GET /api/ping without credentials: **200**.
- GET /api/me with learner/demo-learner: **401** because demo users were not created.
- GET /internal/diagnostics with operator/demo-ops: **401**, because no demo account exists; the diagnostics Controller is also **not registered**.
- No diagnostics route operates in prod, even with flag true forced on the command line.

The main safeguard is **@Profile("local & !prod")** on the Controller. @ConditionalOnProperty is an additional layer, while the role policy applies whenever the bean exists.

With a real production IdP, a request bearing a principal with ROLE_OPS might pass authorization for the diagnostics URL, yet because **no handler exists**, the application still cannot return diagnostic content. A 404/403 status for a missing URL can depend on error dispatch/handler config; **never use status alone to prove a bean is absent**. Test the ApplicationContext directly and verify no sensitive data is returned.

### 7.3. Running with Both Profiles Simultaneously

~~~bash
java -jar target/security-env-demo-1.0.0.jar --spring.profiles.active=local,prod --app.diagnostics.enabled=true
~~~

In the demo, **local & !prod** is false, so the diagnostics bean and demo users are not created. That is **fail-closed** behavior for those two parts, even though the property was overridden.

In real systems, pipelines should **reject conflicting profile configurations before deployment**: never allow a release with both local and prod to appear on a production cluster. Inspect manifests/Helm values or actual running system parameters, not only application-prod.yml in source.

### 7.4. When No Profile Is Specified

With no active profile, Spring uses the framework's default profile mechanism. In this lesson, because local is absent, demo accounts and the diagnostics Controller **are not created**. That is safe behavior for an unspecified environment.

Never set **spring.profiles.default=local** just for convenience on a laptop if the artifact is shared across environments: forgetting to set the active profile in production would accidentally activate local.

## 8. Automated Testing Across Multiple Profiles

Reading YAML is not enough: we must **boot ApplicationContext under each profile set** and verify real beans, statuses, and permissions. The tests below use Spring Boot Test, JUnit 5, MockMvc, and Spring Security Test.

### 8.1. LocalProfileTests.java

~~~java
package com.example.envdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.context.ActiveProfiles;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("local")
class LocalProfileTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPingIsAccessibleAnonymously() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void privateApiRejectsAnonymous() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void privateApiAcceptsLocalUser() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "demo-learner")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("learner"));
    }

    @Test
    void diagnosticsRejectsOrdinaryUser() throws Exception {
        mvc.perform(get("/internal/diagnostics")
                .with(httpBasic("learner", "demo-learner")))
            .andExpect(status().isForbidden());
    }

    @Test
    void diagnosticsAllowsLocalOperator() throws Exception {
        mvc.perform(get("/internal/diagnostics")
                .with(httpBasic("operator", "demo-ops")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("local"));
    }

    @Test
    void arbitraryPathIsDeniedEvenForOperator() throws Exception {
        mvc.perform(get("/api/not-listed")
                .with(httpBasic("operator", "demo-ops")))
            .andExpect(status().isForbidden());
    }

    @Test
    void spoofedRoleHeaderDoesNotAuthenticate() throws Exception {
        mvc.perform(get("/internal/diagnostics")
                .header("X-Role", "OPS"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

These tests prove **local does not mean everything is public**: anonymous gets 401 on private APIs, USER lacking the role gets 403 on diagnostics, and a spoofed role header does not establish identity.

### 8.2. LocalDisabledTests.java

~~~java
package com.example.envdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = "app.diagnostics.enabled=false")
@ActiveProfiles("local")
class LocalDisabledTests {

    @Autowired
    ApplicationContext context;

    @Test
    void diagnosticsBeanIsAbsentWhenFlagIsFalse() {
        assertThat(
            context.getBeanNamesForType(LocalDiagnosticsController.class)
        ).isEmpty();
    }
}
~~~

The test uses a property with higher precedence than application-local.yml to force false. **@Profile local is still true**, yet @ConditionalOnProperty refuses to register the Controller. That is why both conditions must be tested separately instead of inferring from profile names alone.

### 8.3. ProductionProfileTests.java

~~~java
package com.example.envdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "app.diagnostics.enabled=true")
@AutoConfigureMockMvc
@ActiveProfiles("prod")
class ProductionProfileTests {

    @Autowired
    ApplicationContext context;

    @Autowired
    MockMvc mvc;

    @Test
    void diagnosticsControllerAbsentDespiteFlagOverride() {
        assertThat(
            context.getBeanNamesForType(LocalDiagnosticsController.class)
        ).isEmpty();
    }

    @Test
    void localDemoCredentialsCannotAuthenticate() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "demo-learner")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void publicPingRemainsExplicitlyPublic() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk());
    }
}
~~~

**Meaning:** a true property can override the prod file, yet cannot make @Profile local & !prod true. Demo accounts are also not loaded in production, leaving no path using local passwords to access private data.

### 8.4. MixedProfilesTests.java

~~~java
package com.example.envdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = "app.diagnostics.enabled=true")
@ActiveProfiles({"local", "prod"})
class MixedProfilesTests {

    @Autowired
    ApplicationContext context;

    @Test
    void localOnlyControllerIsAbsentWhenProdAlsoActive() {
        assertThat(
            context.getBeanNamesForType(LocalDiagnosticsController.class)
        ).isEmpty();
    }
}
~~~

This test **does not replace** a deployment policy rejecting invalid combined profiles. It only proves the local feature remains absent when prod is also active.

### 8.5. Running Tests

~~~bash
mvn test
~~~

**Expected:** all tests pass with the declared project and dependencies. Do not hardcode Maven runtime or output line counts; they depend on the machine, cache, and plugin versions. If a test fails, inspect active profiles, property overrides, and root cause before altering configuration.

MockMvc tests verify Spring Security/MVC inside ApplicationContext. They **do not replace** real HTTP tests through ingress/gateway, TLS, reverse proxies, Actuator on a separate port, or production identity providers.

## 9. Environment Configuration Risk Matrix to Check

| Failure scenario | Possible consequence | Required control | Test evidence |
| --- | --- | --- | --- |
| SPRING_PROFILES_ACTIVE not set | App runs with unintended default profile. | Safe defaults; no demo identities or debug beans in default; deployment check. | Startup test without local; verify no sensitive beans exist. |
| local accidentally enabled in production | Dev endpoints/users are created. | Combine profile guard with deploy policy; grant only valid roles; network restrictions. | Test local+prod, review manifests, check actual active profiles. |
| Diagnostics flag enabled in prod | Experimental feature appears. | @Profile local & !prod AND flag; independent OPS role. | ProductionProfileTests with flag=true. |
| Putting anyRequest().permitAll() in a local SecurityFilterChain | All endpoints become public if local is enabled wrongly. | One unified policy, explicit permitAll for public URLs, denyAll fallback. | Negative tests for /api/me, /internal, and unknown paths. |
| SecurityFilterChain restricted only to /api/** | /admin or /actuator URLs can fall outside all chains. | Fallback chain or a single chain without a narrow securityMatcher. | Test routes outside /api, inspect filter chains at runtime. |
| Adding a new endpoint without adding policy | New endpoint is reachable unintentionally. | anyRequest().denyAll(), matcher review, and tests. | Test /api/not-listed with a privileged principal. |
| Changing default role or authority mapping | Over-broad grants or false denials. | Standardize role prefix, scope mapping, test multiple identities. | Test USER 403, OPS 200; verify issuer/audience with JWT. |
| Enabling management endpoints via config | Exposes env/heapdump/loggers or sensitive metrics. | Exposure allowlist, chain/network security, and management port policy. | Probe from unauthorized network; inspect actuator policy. |
| CORS wildcard + credentials | Unwanted origins read data in browsers. | Explicit origin allowlist; avoid wildcard for credentialed requests. | Browser preflight/credential tests per environment. |
| Disabling CSRF when changing environments | Browsers send cookie-bearing requests causing unintended side effects. | Maintain CSRF per credential model; change only via threat model/review. | Test POST missing token is blocked when CSRF applies. |
| Secrets from env printed to logs | Leaks client secrets/passwords/tokens. | Secret store, redaction, and logging policy. | Inspect logs/tracing before release. |
| Proxy path rewrites or forwarded headers | App matchers see different paths; IP/host may be spoofed. | Verify trusted proxies, base paths, network policies. | End-to-end tests through real ingress. |

**When configuration behaves unexpectedly, never rush to fix it with permitAll() or disabling CSRF.** Identify the exact filter chain, matcher, principal, rule, profile, property source, and infrastructure layer causing the discrepancy.

## 10. Actuator and Management Ports: Attack Surface Beyond Controllers

When adding Spring Boot Actuator, access to endpoints such as health, info, metrics, loggers, env, and heapdump carries very different implications. **Never use management.endpoints.web.exposure.include=* just for convenience in production.**

Points to check:

- Which endpoints are **actually created and exposed** over the web? Some endpoints may be disabled or unexposed even when beans exist.
- Is there a separate **management.server.port**? If different from the application port, verify which security policy applies to the management context.
- Is there a custom SecurityFilterChain? Once a custom chain is declared, Boot's default Actuator security config may **yield control** to the application; never assume Boot keeps protecting every actuator endpoint for you.
- An /api/** securityMatcher does not automatically protect /actuator/**.
- Public health may make sense for load balancers, yet detail levels must be restricted. Never return full exceptions, database URLs, or cluster internals in public responses.
- Beyond Spring Security, use network policies, ingress allowlists, operational permissions, and auditing.

If Actuator needs role protection, check **EndpointRequest** or matchers suited to your exact Boot version, design a fallback chain, and test statuses over the **real network path**. Never paste a hypothetical Actuator config into a demo lacking the actuator dependency and claim it is protected.

## 11. Secrets, External Config, and Operational Consistency

### 11.1. Secrets Differ from Feature Flags

The property app.diagnostics.enabled is a non-sensitive boolean. By contrast, values such as DB_PASSWORD, OAuth client secrets, private keys, and signing tokens must be managed via a **secret store** or a deployment mechanism with controlled access.

Never commit real secrets into application-local.yml or application-prod.yml in git. Never dump the entire Environment just to check a final flag, never log Authorization request headers, and never pass credentials in query parameters.

In production, you typically need:

- Workload/service account identities authorized to read only the appropriate secret group.
- TLS to dependent services; verify certificates/mTLS when required by design.
- Secret rotation policies and expiration/revocation handling.
- No shared admin accounts between local and production.
- Privilege boundaries among operators, applications, and CI/CD; never give test pipelines excessive production permissions.

### 11.2. Overrides via Environment Variables

Spring Boot supports relaxed binding for many properties. For example, a runtime can set **APP_DIAGNOSTICS_ENABLED=true** for app.diagnostics.enabled, or **SPRING_PROFILES_ACTIVE=prod** to pick profiles.

Syntax varies by OS:

~~~powershell
# PowerShell example for a local lab process.
$env:SPRING_PROFILES_ACTIVE = "local"
$env:APP_DIAGNOSTICS_ENABLED = "true"
java -jar target/security-env-demo-1.0.0.jar
~~~

~~~bash
# Unix shell example for a single local run.
SPRING_PROFILES_ACTIVE=local APP_DIAGNOSTICS_ENABLED=true \
  java -jar target/security-env-demo-1.0.0.jar
~~~

These commands illustrate non-sensitive flags. When running in production, verify actual values coming from Helm/Kubernetes manifests, Docker, systemd, runtime environments, and command lines—not just source files.

### 11.3. Do Not Lock Security Policy to Profile Names

A safer organization:

- **Permission rules** live in SecurityFilterChain or method security, reviewed like business code.
- **Profiles** choose adapters or permitted components; sensitive beans have clear conditions and default off.
- **Flags** toggle functional branches within permitted environments, without granting permissions themselves.
- **Identity providers** vary by environment in issuer, client ID, key material, and endpoints; the server still verifies issuer/audience/expiry, scopes, and object permissions.
- **Deployment gates** check profiles, missing/broken config, exposure, roles, and negative tests before admitting traffic.

Using the same artifact does not guarantee identical behavior: external config outside the JAR, proxies, and secrets can alter runtime decisions. Everything must be verified per release.

## 12. When Should the Application Refuse to Start?

Certain errors should **fail fast** rather than running in an insecure state:

- Production lacks a trusted issuer/JWK or valid identity-source credentials.
- Configuration sets a mode that bypasses authentication on sensitive paths.
- Token signing secrets are missing or still set to demo values.
- Production profile is combined with local when prohibited by organizational policy.
- An expected SecurityFilterChain is missing or an admin gateway route is unprotected.
- Configuration requires a trusted proxy or TLS that the deployment fails to provide.

These checks should execute **before admitting traffic** via application validation, deployment admission checks, config validation, or proper startup readiness gates. Never merely log a warning and continue serving requests when baseline security configuration is missing.

In the lab, we use an **empty user store outside local** so protected endpoints return 401, letting learners observe fail-closed behavior. That is **not** a complete working prod setup; when moving to production, replace it with a real identity source and make startup fail if required identity-source configuration is invalid.

**Never force startup failures in a way that leaves a public port open briefly before shutting down.** When startup validation is needed, run the check early enough in the lifecycle alongside readiness/network gating.

## 13. Safe Pre-Release Verification Workflow

A practical workflow:

1. **Inventory routes and methods** from Controllers, OpenAPI, gateways, message listeners, and management endpoints; label public/authenticated/admin/object-level.
2. **Define the unified policy** in code; expose only URLs with business justification; use a denyAll fallback where appropriate.
3. **List valid profiles and properties** for local, test, staging, prod. Specify forbidden profile combinations.
4. **Isolate local-only features** into @Profile + @ConditionalOnProperty beans, still preserving roles/authorities and network limits.
5. **Configure per-environment authentication** via managed providers/issuers/secrets; never carry demo passwords into prod.
6. **Write negative tests across the matrix:** anonymous, lower role, wrong credentials, flag on/off, local/prod/mixed, undeclared methods, and object/tenant permissions.
7. **Build and test the exact artifact meant for deployment**, then verify actual config and proxy/ingress per environment.
8. **Check logs, caching, CORS/CSRF, and Actuator**; restrict secrets/debug output and trace real request paths.
9. **Enforce CD gates**: if profiles or security configs are invalid, block deployment or block the build from receiving traffic.
10. **Monitor and re-audit** whenever adding routes, changing auth mechanisms, rotating secrets/issuers, updating proxies, or opening management ports.

You can store a permission table in the repo for reviews:

| Resource | Local | Staging | Prod | Unified policy |
| --- | --- | --- | --- | --- |
| GET /api/ping | 200 anonymous | 200 anonymous | 200 anonymous | Intentionally public. |
| GET /api/me | Auth required | Auth required | Auth required | Never broadened by flags. |
| GET /internal/diagnostics | May exist if flag=true, needs OPS | Bean absent | Bean absent | Profile guard, property guard, and role guard. |
| Undeclared GET/POST routes | Deny | Deny | Deny | Fail closed by rule. |
| Sensitive Actuator if present | Protected per task | Restricted and authorized | Restricted and authorized | Explicit exposure, network, and audit. |

Never record "prod 404" as sole proof for diagnostics: code might still carry the route while filters return 403/404 depending on policy. **Testing the bean directly and checking responses/side effects** proves the feature is unavailable.

## 14. Self-Check Questions

1. Why is setting app.diagnostics.enabled=false in application-prod.yml **not enough** if command-line arguments can override it?
2. Can @Profile("!prod") activate when no profile is set? Why is local & !prod stricter for local-only endpoints?
3. What risk does a SecurityFilterChain with only securityMatcher("/api/**") and no fallback pose for /admin or /actuator?
4. Why is flag-dependent requestMatchers("/internal/**").permitAll() a dangerous design?
5. In the demo, why does the same user learner get 200 at /api/me yet 403 at /internal/diagnostics?
6. Why should demo accounts be created only under profile local & !prod, and why must prod use a real identity provider?
7. When you see 403 on a POST, how do you distinguish a CSRF error from denyAll authorization?
8. If both local and prod are active, the final property may be true. Which guardrail still prevents the diagnostics bean? What else must deployment policy do?
9. Why is a 404 response for an endpoint insufficient to prove its Controller was excluded from ApplicationContext?
10. When using a JWT Resource Server, which parameters must vary by environment and what must stay strict regarding scope, audience, and object permissions?

### Key Checklist

- **Never turn a profile name or feature flag into an app-wide permitAll switch.**
- **SecurityFilterChain covers all** requests or has an explicit fallback chain when using multiple chains.
- **Intentional permitAll, explicit authenticated/hasRole, denyAll fallback** are verifiable starting points.
- **Local-only beans** should require both profile and property conditions, default off, and expose no secrets.
- **Demo accounts stay local only**; production uses an approved identity source.
- **Test every profile and flag combination** with context + HTTP status + actual permissions, including misconfigurations.
- **Externalized config can override YAML**; verify runtime values and never log secrets.
- **Proxies, Actuator, CORS, CSRF, and data-level permissions** still require dedicated policies.
- **CI/CD and readiness** prevent a misconfigured security build from receiving traffic.

## References

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): permitAll, hasRole, denyAll, matcher ordering.
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): securityMatcher, multiple SecurityFilterChains, and fallback.
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html): activating profiles and profile-specific configuration.
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): property source precedence and profile-specific files.
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html): profile expressions with &, !, and |.
- [Spring Boot — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): havingValue and matchIfMissing.

**Version note:** Hands-on code targets Spring Boot 3.3.6/Spring Security 6.x to keep examples consistent. For projects using newer versions, consult the matching documentation for APIs and configuration behavior, apply patches, and re-run the test matrix against the selected dependencies.

## Conclusion

Configuring securely across environments is more than creating application-local.yml and application-prod.yml. You must keep **core authorization policies stable**, protect all requests with SecurityFilterChain, enable local features only under proper profile/flag guards while still enforcing roles on invocation, use trustworthy identity sources per environment, and fail closed when configuration is missing. Most importantly, **test likely misconfiguration combinations**, verify runtime/deployment against source code, and block non-compliant releases from receiving traffic.
