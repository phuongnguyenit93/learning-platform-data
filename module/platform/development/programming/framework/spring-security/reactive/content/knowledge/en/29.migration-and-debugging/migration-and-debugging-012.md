# Reading Upgrade Guides and Verifying Version-Specific Defaults in Spring Security Reactive

## 1. Why Read Migration Guides and Re-Verify Defaults?

A WebFlux application can **compile cleanly yet change its security behavior** after upgrading Spring Boot, Spring Framework, or Spring Security. Unchanged configuration code does not guarantee every request gets the same outcome: CSRF defaults, authority mappings, JWT decoders, filter ordering, error handling, sessions, or auto-configuration may differ. Conversely, many changes described in migration guides apply only to **Servlet** and must not be copied into **Reactive**.

For example, an application previously handled CSRF tokens the legacy way, yet a newer version uses BREACH protection; browsers start receiving HTTP 403 even though roles remain right. Or an internal JWT-issuing API uses a custom `typ` value; upon upgrading, you must compare type verification and validator sets before deciding to remove temporary compatibility config. Fixing tests to turn "green" via `csrf.disable()` or accepting any JWT type can introduce vulnerabilities.

After this lesson, you will be able to:

1. Read the right documentation for your **running version, target version, WebFlux stack**, and every intermediate release.
2. Distinguish **API/DSL changes**, **default changes**, **behavioral changes**, **dependency changes**, and **changes in your own application config**.
3. Build a before/after decision table covering login, authorization, CSRF, CORS, OAuth2/JWT, sessions, HTTP statuses, and security headers.
4. Use `WebTestClient` with `spring-security-test` to turn expected security behavior into tests runnable on both old and new versions.
5. Upgrade in stages, gather evidence, isolate causes, and roll back safely whenever tests reveal discrepancies.

**Scope:** **Spring Security Reactive** applications on Spring WebFlux, using `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveSecurityContextHolder`, `ReactiveAuthenticationManager`, and client types such as HTTP Basic, cookie/session, OAuth2 Login, or bearer-token resource servers. Examples use Java 17. This lesson does not assume every listed change affects every app: compare only against features actually in use.

## 2. First Step: Pin Exact Resolved Versions Rather Than Guessing from Doc Titles

A project typically involves multiple version numbers:

| Component | Role | Why record it |
| --- | --- | --- |
| JDK | Runtime and toolchain | Upgrades may require a higher minimum JDK or change TLS/crypto providers |
| Spring Boot | BOM/dependency management and auto-configuration | Changing parent/BOM can bump many libraries simultaneously |
| Spring Framework / WebFlux | HTTP stack, codecs, reactive context | WebFlux changes affect requests, responses, and exceptions |
| Spring Security | Authentication, authorization, CSRF, OAuth2, headers | Primary migration guide for auditing security controls |
| Reactor / Reactor Netty | Publishers, schedulers, HTTP server/client | Context propagation, pipelines, timeouts, and event loops |
| Jackson | JSON/serialization, especially custom session/token serialization | Major versions can change APIs, formats, and modules |
| Spring Session, OAuth2 client, gateway, test libraries | Optional components | Artifact compatibility cannot be inferred from a single version number |

**Record two sets of numbers:** `baseline` is the *currently running* set, and `candidate` is the *target release* set. Never read an unversioned `/reference/` documentation URL as if it described your running version; unversioned pages typically point to the latest branch.

Example input table for an upgrade cycle:

| Attribute | Baseline | Candidate | Verification source |
| --- | --- | --- | --- |
| Java | 17 | Per candidate compatibility requirements | `java -version`, build pipeline |
| Spring Boot | 3.x.y | Approved target version | Parent/BOM, `dependency:tree` |
| Spring Security | Resolved by BOM | Resolved by candidate BOM | Effective dependencies |
| WebFlux | Running on Reactive stack | Still Reactive | Dependency graph, application context |
| Authentication flow | Basic / form / OIDC / JWT / opaque | Any changes? | `SecurityWebFilterChain` config, beans, and tests |
| Session/CSRF | Cookie/`WebSession` vs. bearer-only | Policy preserved or changed | Browser, config, tests |
| Gateway/TLS/routes | Active rules/headers | Candidate rules/headers | Tests at public ingress |

Do not write "Security 6" when you actually only checked Boot 3: inspect the exact resolved artifacts. Likewise, avoid overriding `spring-security-*` versions past Boot's BOM without compatibility evidence. When forced to override a Security patch, record the exact reason, exact version, related BOM, and compatibility test suite.

### 2.1. Collecting Versions with Maven

In a real Maven project:

```bash
java -version
./mvnw -version
./mvnw help:effective-pom -Doutput=effective-pom.xml
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=org.springframework
./mvnw dependency:tree -Dincludes=io.projectreactor
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core
```

If using system Maven instead of the wrapper, replace `./mvnw` with `mvn`; on Windows you can use `mvnw.cmd`. Archive `dependency:tree` outputs as CI artifacts per build ID. Inspect `effective-pom.xml` only in internal environments; it may contain repository settings and properties that should not be made public.

### 2.2. Collecting Versions with Gradle

Example using Gradle with Java/Spring Boot plugins:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-webflux
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-config
./gradlew dependencyInsight --configuration runtimeClasspath --dependency reactor-core
```

Use your project's real configuration; if `runtimeClasspath` does not exist, inspect the Gradle model and substitute the valid configuration. Never conclude which package is running from direct dependency declarations alone: dependency constraints, resolution strategies, platforms/BOMs, dependency locks, or runtime classpath jars can yield unexpected versions.

## 3. Reading Upgrade Docs in the Right Order and for the Right Stack

Every step must answer four questions: **where are we, where are we going, which changes take effect, and what evidence confirms it?**

### 3.1. Documentation Sources to Check in Order

1. **Release notes / security advisories** for the target release and every intermediate version: bug fixes, CVEs, intentional behavior changes, and deprecated/removed features.
2. **Spring Boot migration guide**: properties and auto-configuration, starter/module names, dependency management, Actuator, Jackson, Spring Framework, and minimum Java version.
3. **Spring Security preparation guide** for the target major: bring code into a compatible state on the older release before enabling new behavior—such as preparing on 6.5 before moving to 7.
4. **Spring Security migration guide** for the target version, choosing the **Reactive** branch. The **Servlet** section is only a reference if another module uses Servlet; never copy Servlet APIs into WebFlux.
5. **Version-pinned Reference and Javadoc** for every symbol in use: `SecurityWebFilterChain`, `ServerHttpSecurity`, `ServerWebExchangeMatcher`, `ReactiveJwtDecoder`, `ServerCsrfTokenRepository`, etc.
6. **Spring Security test reference** for that same version line, plus issues/release notes for specific bugs. When source code and docs appear inconsistent, verify with a small version-locked test and record the finding.

Key starting pages:

- Spring Security migrations: https://docs.spring.io/spring-security/reference/migration/
- Spring Security reactive migration: https://docs.spring.io/spring-security/reference/migration/reactive.html
- Preparation for Security 7 on the Security 6.5 branch: https://docs.spring.io/spring-security/reference/6.5/migration-7/index.html
- Configuration migration 6.5 → 7: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
- Spring Security Reactive: https://docs.spring.io/spring-security/reference/reactive/index.html
- Spring Boot reference: https://docs.spring.io/spring-boot/reference/

**Versioning rule:** pin `/6.5/`, `/7.0/`, or the matching doc branch when cross-checking, and record the access date and tested commit/build. Never use SNAPSHOT/RC pages as a production baseline unless intentionally targeting that pre-release. Whenever current unversioned docs shift, recapture links pinned to the exact version under test.

### 3.2. Turning Changelog Items into a Technical Checklist

Every relevant migration-guide entry must become a verifiable decision:

| Question while reading | What to record |
| --- | --- |
| Which version introduces the change? | Exact major/minor/patch and doc link |
| Does it apply to Reactive or Servlet? | Stack; API classes; module |
| What condition triggers impact? | E.g., custom JWT decoder or custom CSRF token handling |
| What was the prior default behavior? | Baseline tests, old-version Javadoc |
| What replaces it after upgrading? | Candidate tests, new configuration |
| Does current config override the default? | Link to config/bean, property, or custom filter |
| Does security meaning change? | Risk, negative/positive tests, owner |
| How to handle failures? | Proper fix, rollback trigger, never weaken security indiscriminately |

Prioritize **Removed**, **Deprecated**, **Changed default**, **Behavioral change**, and **Security hardening** items. Compile errors are easy to spot; silent runtime differences without tests are far more dangerous.

### 3.3. Do Not Confuse Source Compatibility with Behavior Compatibility

- **Source compatibility:** imports and methods still exist; code compiles.
- **Binary compatibility:** pre-compiled libraries/plugins still link at runtime.
- **Configuration compatibility:** beans/properties are still consumed by Boot auto-config or Spring Security as before.
- **Behavior compatibility:** identical requests and credentials produce identical allow/deny decisions, headers, sessions, and exceptions.
- **Data compatibility:** serialized sessions, OAuth2 authorized-client records, encrypted tokens, or stored legacy password hashes remain readable after deployment.
- **Operational compatibility:** TLS/ciphers, logging, metrics, latency, tracing, gateways, browsers, and IdPs interact properly.

Running controller unit tests alone usually covers only a slice. Changes in `WebFilter`s or default configuration take effect before controllers are ever invoked.

## 4. Default Groups That Must Be Verified Specifically in Reactive Apps

Not every group changes in every version. Still, for each group your app relies on, confirm it via tests and release notes spanning the upgrade window.

| Group | What to compare before/after | Signs of change |
| --- | --- | --- |
| Boot auto-configuration | Presence/absence of `SecurityWebFilterChain` bean, default user, login mechanism, config order | Entire API suddenly returns 401/302 or routes become public |
| Authentication | Basic/form/OAuth2/JWT/opaque, issuer, audience, timestamps, authorities, password encoder, entry point | Logins fail, valid tokens get 401, wrong error messages |
| HTTP authorization | `securityMatcher` chain selection, `pathMatchers` and ordering, trailing `denyAll`/`authenticated` | `USER` reaches admin, new routes left unprotected |
| Reactive method security | `@EnableReactiveMethodSecurity`, `@PreAuthorize`, principal/roles, `Mono`/`Flux` return types | HTTP opens properly, yet another tenant's data is read |
| CSRF | Enabled state, repository, how tokens reach clients, token handler, unsafe-method checks | Valid POST returns 403, or tokenless POST still succeeds |
| CORS | Preflight, origins/methods/headers/credentials, filter ordering | `OPTIONS` gets 401/302, unknown origins can read responses |
| Headers and cookies | HSTS, CSP, frame options, nosniff, cache control, `SameSite`, `Secure`, `HttpOnly` | Missing headers on 200/401/403, session cookies altered |
| Session and reactive context | `WebSession`, `ServerSecurityContextRepository`, Reactor Context, auth save/load | Empty principal after redirect, user context drops in pipeline |
| OAuth2 login/client | Redirect URI, callback, `state`, authorized client, role mapping | Redirect loops, 403 right after login, refresh fails |
| JWT Resource Server | `ReactiveJwtDecoder`, `typ`, issuer, audience, signature, JWKS, clock skew | Valid JWT gets 401, or wrong-purpose token is accepted |
| Opaque token Resource Server | `ReactiveOpaqueTokenIntrospector`, client auth encoding, timeouts | Introspection gets 401 or stalls unexpectedly |
| Error mapping | 401/403/5xx, failure handlers, exception propagation | System failures reported as bad credentials or leak exceptions |
| Test/security integration | `WebTestClient`, `spring-security-test`, mock principal/CSRF, real vs. mock client | Tests green via mocks while production fails |
| Logging/observability | Request/trace correlation, reactive context, masking, audit events | Lost traces, duplicate logs, leaked tokens |

**Verify both explicit config and implicit defaults.** When an application declares its own `SecurityWebFilterChain`, Boot auto-config behaves differently than when none is declared. A blog post stating "by default all requests require authentication" is not enough to assume that holds for your app.

## 5. Documented Changes: How to Read Without Mixing Up Stacks

### 5.1. Reactive CSRF: From Security 5.8 to Security 6.0

Reactive CSRF documentation states: in **5.8**, `ServerCsrfTokenRequestAttributeHandler` was the default handler; starting in **6.0**, the default changed to `XorServerCsrfTokenRequestAttributeHandler` to provide BREACH protection. CSRF remains enabled by default for unsafe HTTP methods.

Implications:

- Users with session cookies issuing `POST` requests must send CSRF tokens via the expected mechanism.
- If an SPA reads tokens and sends headers, check how tokens are rendered and decoded by the handler. Never "fix" it by skipping token validation.
- Choosing `CookieServerCsrfTokenRepository` vs. `WebSessionServerCsrfTokenRepository` is a **token storage decision**, while the request token handler is a **separate decision**.
- If customizing the handler, verify BREACH mitigations remain adequate; reverting to the older handler can remove protection and requires a threat review.

Snippet to **preserve the running version's default mechanism**:

```java
// Snippet inside a WebFlux @Bean SecurityWebFilterChain:
http.csrf(org.springframework.security.config.Customizer.withDefaults());
```

To compare an older baseline against a new candidate, run four checks: GET form/token, POST without token, POST with bad token, and POST with a token fetched via the official mechanism and sent in the right header. Reuse the same cookie/session throughout the flow. Testing with `WebTestClient.mutateWith(csrf())` verifies rule enforcement yet **does not replace real browser tests of how the SPA fetches and sends tokens**.

Source: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html

### 5.2. Lambda DSL and Removal of Legacy Configuration APIs

The Spring Security 7 preparation guide states that **Lambda DSL** is the required configuration style in 7; legacy `.and()` chaining is no longer valid syntax for those configurations. Apply this to configuration templates, and **never copy Servlet examples using `HttpSecurity`, `SecurityFilterChain`, and `authorizeHttpRequests` into WebFlux**.

Illustrative Reactive Lambda DSL:

```java
// Body of a @Bean; requires ServerHttpSecurity, SecurityWebFilterChain,
// and Customizer imports in a real project.
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public").permitAll()
                    .pathMatchers("/admin/**").hasRole("ADMIN")
                    .anyExchange().authenticated())
            .httpBasic(org.springframework.security.config.Customizer.withDefaults())
            .build();
}
```

After rewriting to the new DSL, compare *matcher ordering, chain ordering, and enabled default behaviors* against the baseline. Even a "syntax refactor" can accidentally alter `permitAll`, CSRF, HTTP Basic, or form login scopes.

Source: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html

### 5.3. Security 6.5 → 7: JWT `typ` Validation in Reactive

According to the Spring Security 7 migration guide, for `NimbusReactiveJwtDecoder`, `typ` header validation moves toward `JwtTypeValidator`. The 6.5 preparation guide shows how to adopt the validator ahead of the major upgrade; once on 7, transitional configuration can be removed if keeping the default policy.

**What must be verified:** which JWT types the application accepts, whether `at+jwt` or custom `typ` tokens exist, and what the token-purpose policy requires. A validly signed JWT **is not automatically** the right token type or for the right issuer/audience/resource. Avoid disabling validation merely to keep invalid tokens working.

Illustrative snippet **applicable only during transition on Security 6.5 when using a custom decoder** (not a complete program):

```java
// Spring Security 6.5: prepare 7.x-aligned typ validation behavior
NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
                .validateTypes(false)
                .build();
decoder.setJwtValidator(JwtValidators.createDefaultWithValidators(
        new JwtIssuerValidator(issuer), JwtTypeValidator.jwt()));
return decoder;
```

Per the finalization guide for Security 7, once token purpose and required validators are verified, the default shape can be:

```java
// Spring Security 7: illustrates default JWT typ validation only
NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
                .build();
decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer(issuer));
return decoder;
```

The two snippets above use APIs from two different release lines—never place them in the same file, and never copy them verbatim if the app already defines audience or other custom validators. **Always preserve all business validators** during migration; these snippets only show migration-related validator wiring. Test with valid tokens, bad signatures, expired tokens, wrong issuers, wrong audiences, missing `typ`, unexpected `typ`, and wrong-purpose tokens. Never log full bearer tokens in CI.

Source: https://docs.spring.io/spring-security/reference/migration/reactive.html

### 5.4. Spring Boot 4 / Security 7: Reading Dependency and JSON Changes

The Spring Security 7 migration guide requires aligning with the matching Spring Boot 4 release and notes the move from Jackson 2 to Jackson 3 for related integrations; applications that serialize/deserialize security objects with custom modules especially need review. This is an **ecosystem + serialization** change, not just editing one line in `SecurityWebFilterChain`.

Additional checklist:

- Compare the effective dependency graph and remove conflicting overrides. Verify Spring Framework, WebFlux, Jackson, Reactor, and test dependencies align.
- If the app stores serialized authentications, sessions, or authorized clients, write a test reading baseline-written data with the candidate, and have an approved migration/session-expiration plan.
- Compare how Jackson modules used by Spring Security are configured. The 7 guide moves from `SecurityJackson2Modules` on Jackson 2 to `SecurityJacksonModules` on Jackson 3; update only if the project **actually uses this feature**.
- Check Spring Session, Redis, message-broker, and cache integrations. Starting up cleanly does not prove old session data remains deserializable.
- If Spring Cloud Gateway or modules outside WebFlux exist, read each artifact's migration guide and run end-to-end tests through the gateway.

Source: https://docs.spring.io/spring-security/reference/migration/

### 5.5. Separating Servlet Changes from Reactive Changes

Entries for `PortResolver` or `AntPathRequestMatcher` / `MvcRequestMatcher` in the **Servlet** guide do not mean you should add a `PortResolver` bean or use Servlet `PathPatternRequestMatcher` in WebFlux. In WebFlux, inspect `ServerWebExchangeMatcher`, `PathPatternParserServerWebExchangeMatcher`, and version-appropriate `ServerHttpSecurity` APIs.

Likewise, thread-local `SecurityContextHolder`, `HttpSession`, Servlet `FilterChainProxy`, and `MockMvc` are not the default tools for reading principals, managing sessions, or testing Reactive; use `ReactiveSecurityContextHolder`, `WebSession`, and `WebTestClient`.

When a migration-guide item mentions only Servlet, record "**not applicable** after verifying stack/API" instead of guessing WebFlux changed identically. Marking an item not applicable is a valid review outcome when backed by evidence.

## 6. Risk-Reducing Upgrade Workflow

### Phase A — Capture Baseline **Before Changing Dependencies**

1. Record build ID/commit, Java version, parent/BOM, dependency graph, and active profile configs.
2. Inventory all `SecurityWebFilterChain` beans and `@Order` values when multiple chains exist; note which matcher selects which chain.
3. List critical requests: login, logout, OAuth2 callback, token refresh, API reads/writes, admin, actuator, tenant/ownership checks, CSRF preflight, and error routes.
4. For each request, specify **actor, credential, CSRF token, route, method, expected HTTP/status, headers, and side effects**.
5. Run and archive baseline tests in CI with both positive and negative cases. Never record a known broken state as an acceptable baseline; flag existing security debt for fixing.
6. Document explicit configs and every place relying on defaults: `httpBasic(withDefaults())`, `oauth2ResourceServer`, `csrf`, custom managers/converters/decoders, and default user auto-config.
7. Store test fixtures (mock JWTs, test cookies, serialized auth samples if any) without exposing real credentials.

### Phase B — Read Changes and Plan

1. Choose an officially supported upgrade path, such as 6.x → 6.5 with preparation → 7.x per official docs; **do not skip required preparation steps**.
2. Read every relevant migration guide/release note and map each applicable item to code/config edits, an owner, and one or more tests.
3. Categorize items: compile failure, deprecated API, changed default, security behavior, dependency/runtime, and operational compatibility.
4. Separate dependency-upgrade PRs from business-policy-change PRs where possible. Clear separation shows whether a failure came from the framework bump or a rule change.
5. Check security advisories and the latest supported patch on the target branch. Old sample versions in learning docs are **fixtures**, not long-term pinning recommendations.

### Phase C — Run Candidate and Compare

1. Update parent/BOM/lockfiles; build cleanly and verify the new dependency graph.
2. Fix removed APIs and migration-required configs; never weaken policies with `permitAll` or `csrf.disable()` just to get a green build.
3. Run unit, integration, API contract, and security tests against the exact baseline scenario set. Compare by security semantics rather than version-dependent raw log lines or stack traces.
4. Run `WebTestClient` bound to `ApplicationContext` to exercise Spring Security filters, plus real HTTP tests through servers/gateways to catch redirects, cookies, CORS, and TLS issues.
5. Verify real JWTs against test IdP metadata, JWKS rotation, signatures, issuer/audience/`typ`, and expiry; never use production tokens.
6. Compare auth/authorization latency, errors, and logs without leaking payloads or tokens when diagnostics are enabled.

### Phase D — Canary/Rollout and Rollback

1. Test staging environments matching production gateways, TLS, cookies, and identity providers.
2. Roll out via canary slices where supported; monitor 401/403/5xx rates, OAuth2 callbacks, login rates, p95/p99 latency, session restoration, refresh tokens, and CSRF/CORS failures.
3. Prepare rollback triggers if changes cause false denies, false allows, or data leaks. Where data/session migrations occur, rollback plans must account for schema compatibility, not just container image rollbacks.
4. After release, lock versions and archive the migration record; continue reviewing release notes for subsequent patch upgrades since patches can adjust security-related behavior.

## 7. Runnable Example: "Security Contract Tests" for a Baseline

This sample intentionally **omits a custom `SecurityWebFilterChain`** so you can observe the default WebFlux security configuration generated by Spring Boot + Spring Security. It illustrates why baseline tests must be re-run whenever you later introduce custom chain beans. It pins Spring Boot **3.3.13** as a **fixed learning fixture** for reproducible execution; that branch has reached end of OSS support and is **not a production version recommendation**.

For a real candidate upgrade, you **update parent/BOM per the migration guide**, adjust APIs if needed, and re-run **the exact same security contract tests**. None of the commands below automatically proves compatibility for every newer release.

### 7.1. Create `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>dev.example</groupId>
    <artifactId>reactive-upgrade-contract</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
```

Do not pin a separate version for `spring-security-test`, as the Boot parent keeps it aligned with the Spring Security runtime.

### 7.2. Create `src/main/java/dev/example/upgrade/UpgradeBaselineApplication.java`

```java
package dev.example.upgrade;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class UpgradeBaselineApplication {
    public static void main(String[] args) {
        SpringApplication.run(UpgradeBaselineApplication.class, args);
    }
}

@RestController
class RecordController {
    @GetMapping("/api/records")
    Mono<String> read() {
        return Mono.just("records");
    }

    @PostMapping("/api/records")
    Mono<String> create() {
        // Demo: mutates no data. POST endpoint is for testing CSRF.
        return Mono.just("created");
    }
}
```

Here the presence of Spring Security on the classpath activates Boot's version-specific security auto-configuration. Without a custom `SecurityWebFilterChain`, all endpoints require authentication under the fixture's defaults; form login/Basic can produce different responses depending on `Accept`. Tests send `Accept: application/json` when verifying HTTP 401 rather than assuming browser redirects.

### 7.3. Create `src/test/java/dev/example/upgrade/SecurityContractTest.java`

```java
package dev.example.upgrade;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

@SpringBootTest
class SecurityContractTest {
    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void anonymousRequestMustAuthenticate() {
        client.get().uri("/api/records")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserCanRead() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/api/records")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("records");
    }

    @Test
    void postRequiresCsrfEvenWithAuthentication() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .post().uri("/api/records")
                .exchange()
                .expectStatus().isForbidden();

        client.mutateWith(mockUser("alice").roles("USER"))
                .mutateWith(csrf())
                .post().uri("/api/records")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("created");
    }

    @Test
    void secureResponseHeaderIsPresent() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/api/records")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Content-Type-Options", "nosniff");
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
mvn dependency:tree -Dincludes=org.springframework.security
mvn spring-boot:run
```

Once the app is running, try from another terminal:

```bash
curl -i -H 'Accept: application/json' http://localhost:8080/api/records
```

In the baseline fixture, expect 401 for the anonymous request above, while the `mockUser` tests verify authenticated GET and CSRF-protected POST. Maven prints log lines and timings that vary by machine; there is no fixed console stdout so none is fabricated. `mockUser` requests exercise the security pipeline **with a simulated identity**; testing password auth, bearer/JWTs, or an IdP requires dedicated tests with real test-environment credentials.

### 7.4. Upgrade Experiments and Interpreting Failures

- **Experiment 1 — version bump:** switch parent to a chosen official release, update code per its migration guide, and keep tests unchanged. If compilation fails, check JDK/starters/Jackson/imports/APIs; if it compiles yet test outcomes shift, inspect implicit defaults and custom rules.
- **Experiment 2 — custom chain:** add an `@Bean SecurityWebFilterChain` with custom rules. From that point on, conclusions about Boot's default "every route authenticated" no longer suffice; `/api/records` tests must validate your app-defined rules.
- **Experiment 3 — CSRF change:** in a **separate test environment**, configure CSRF under an explicit valid policy and re-run `postRequiresCsrfEvenWithAuthentication`. If 403 vanishes without a token, record that as an intentional or unapproved policy shift—do not casually change expected status to 200.
- **Experiment 4 — real HTTP tests:** boot the server and inspect `Location`, `Set-Cookie`, `WWW-Authenticate`, CORS headers, and HSTS at an HTTPS edge. `ApplicationContext`-bound tests do not cover ingress or browser behavior.
- **Experiment 5 — token migration:** add a resource server and a suite of valid, wrong-issuer, wrong-audience, and wrong-`typ` test JWTs; compare baseline vs. candidate outcomes. Never log or commit real tokens.

**How to interpret correctly:** a test turning from green to red is a signal to analyze, not proof the library has a bug. The old policy may have been insecure; in that case, align expected behavior with approved security requirements and document the intentional change.

## 8. Building a Pre/Post-Upgrade "Default Diff" Table

Commit this table alongside the upgrade PR. Every "expected" cell must cite a source: migration notes, versioned reference docs, or verified test results. Never fill cells from memory.

| ID | Security invariant | Baseline | Candidate | Test | Decision |
| --- | --- | --- | --- | --- | --- |
| AUTH-01 | Anonymous cannot read private data | 401 or redirect per Accept | Match client contract | `WebTestClient` + real HTTP | PASS/FAIL |
| AUTH-02 | USER cannot access admin | 403 | 403 | Role matrix | PASS/FAIL |
| AUTH-03 | ADMIN can still execute valid APIs | 2xx | 2xx | Positive test | PASS/FAIL |
| CSRF-01 | Cookie/session POST without token is blocked | 403 | 403 | Bad/valid token | PASS/FAIL |
| CSRF-02 | SPA sends token matching new handler | Works | Works | Browser E2E | PASS/FAIL |
| CORS-01 | Unknown origins get no CORS read access | No matching allow-origin | Preserved | Preflight + real browser | PASS/FAIL |
| HDR-01 | Anti-MIME-sniffing header present | Present | Present | Response headers | PASS/FAIL |
| MATCH-01 | New routes are not public by default | Deny/authenticated | Preserved | Unknown-route test | PASS/FAIL |
| JWT-01 | Only valid issuer/audience/typ accepted | Per policy | Preserved or stricter if approved | Signed fixture tokens | PASS/FAIL |
| CONTEXT-01 | Principal follows reactive pipeline | Present | Present | `Mono`/`Flux` + method security | PASS/FAIL |
| SESS-01 | Session/authorized client lifecycle works | Per baseline | Per migration plan | Login/logout/restore | PASS/FAIL |
| AUDIT-01 | Denied/sensitive actions logged adequately | Present | Present | Event assertions | PASS/FAIL |

**Add negative cases:** locked users, wrong passwords, expired tokens, missing scopes, validly signed tokens with wrong audience, cross-tenant attempts, encoded path edge cases, upstream IdP outages, and expired sessions. For each case, assert both the **security decision** and **zero side effects**, not just HTTP status.

The diff table must distinguish:

- `expected_same`: behavior required to stay identical.
- `intentional_change`: approved behavior change backed by migration notes.
- `unexpected_change`: unexplained discrepancy—must block release if security-impacting.
- `not_applicable`: unused feature/stack with supporting evidence.
- `not_verified`: missing required test or environment; never write "PASS" to mask missing evidence.

## 9. Debugging When a Version Change Breaks Tests

### 9.1. SPA POST Suddenly Returns 403

1. Confirm `GET` works for the same user and the login session/token is valid.
2. Compare `WebSession`, cookies, generated/issued CSRF tokens, header names, request handlers, and how the client reads tokens.
3. Read Reactive CSRF migration notes between the two versions (especially 5.8 → 6.0 when relevant).
4. Test missing token, wrong token, and valid token variants. If only a valid token succeeds, the issue lies in CSRF/client integration.
5. If 403 persists with a valid token, inspect roles, matchers, method security, and tenancy. Avoid disabling CSRF to hide the failure.

### 9.2. Previously Working JWT Returns 401 After Upgrade

1. Compare effective `spring-security-oauth2-jose`, the `ReactiveJwtDecoder` bean, issuer/JWKS endpoints, and clocks.
2. Verify JWT signature, `alg`, `kid`, `iss`, `aud`, `exp`, `nbf`, and `typ` using safe local tools; never log real tokens.
3. If moving from 6.5 to 7.x, read the Reactive `JwtTypeValidator` section specifically and retain validation for accepted token types.
4. If authentication succeeds yet APIs return 403, inspect `JwtAuthenticationConverter`, mapped authorities, role prefixes, and authorization rules.
5. Check network/JWKS/IdP errors rather than blaming every 401 on Security changes.

### 9.3. After Update, 401 Turns into 302 to the Login Page

1. Inspect client `Accept` headers, enabled login mechanisms, and `ServerAuthenticationEntryPoint`.
2. Check whether `SecurityWebFilterChain` is Boot-generated or overridden by a new bean.
3. Inspect path matchers for API/HTML routes and custom exception handling.
4. Confirm the expected contract: browser HTML may redirect, whereas JSON APIs should return responses clients handle properly.
5. Test behind the gateway, because rewrites or header changes can create differences unseen in `WebTestClient`.

### 9.4. Unit Tests Pass, Yet Production Loses the Principal

1. Search for `ThreadLocal` or Servlet `SecurityContextHolder` incompatible with Reactor.
2. Verify `ReactiveSecurityContextHolder.getContext()` is read **inside the pipeline** with proper subscription.
3. Across `publishOn`, `subscribeOn`, `WebClient`, schedulers, or custom filters, inspect context propagation and remove manual `subscribe()`/`block()` calls breaking the chain.
4. Check Boot/Security/Reactor/Micrometer version alignment and test end-to-end with a real principal.
5. Distinguish missing permissions from lost authentication using structured events without leaking credentials.

### 9.5. Service Starts, Yet Legacy Data/Sessions Fail to Deserialize

1. Inspect serialized object structures, codecs, Jackson modules, Spring Session repositories, and key namespaces.
2. Check Boot/Security/Jackson release notes; specifically for 6 → 7, read the Jackson 2 → 3 guidance for security object serialization.
3. Test reading baseline-created sample records with the new candidate in a test environment.
4. Prepare a session rotation/expiration/migration strategy when needed, evaluating impact on active user logins.
5. Keep a compatible rollback plan; never assume rolling back container images restores an altered data schema.

## 10. Boundaries and Security Principles When Comparing Versions

**Never achieve "compatibility" by blindly relaxing policies.** For instance, `anyExchange().permitAll()` to pass tests, dropping CSRF on cookie APIs, disabling JWT signature checks, skipping issuer/audience validation, allowing all CORS origins, or logging full tokens are never valid migration fixes.

**Never rely on unverified version labels.** A doc page may render the latest release; a module may resolve a different artifact via a BOM; an app bean may override framework defaults. Require all three together: version-accurate migration notes, the resolved dependency graph, and runtime tests.

**Never "fix" failures by changing assertions to match broken new behavior.** Allow/deny rules must originate from security requirements. When a major upgrade intentionally alters policy, record the RFC/ADR, owner, and rollout details.

**Never declare full policy coverage from `mockUser` unit tests alone.** Simulated-principal tests are great for `AuthorizationManager`, CSRF, and filter logic, yet cannot replace real login/IdP/JWKS, browser cookies, network gateways, CORS, TLS, and database ownership tests.

**Never mix Servlet and Reactive.** Pages with similar titles may show `HttpSecurity` for Servlet and `ServerHttpSecurity` for Reactive; similar names do not guarantee identical types, methods, or defaults. Verify both `/reactive/` doc URLs and API package names.

## 11. Reusable Upgrade Review Record Template

```yaml
security_upgrade_review:
  baseline:
    build: "old-build-id"
    boot: "resolved-boot-version"
    security: "resolved-security-version"
    jdk: "resolved-java-version"
    web_stack: "REACTIVE_WEBFLUX"
  candidate:
    build: "candidate-build-id"
    boot: "approved-target-version"
    security: "resolved-target-version"
    jdk: "approved-jdk"
  documentation:
    - "spring-boot-migration-guide-pinned-url"
    - "spring-security-preparation-guide-pinned-url"
    - "spring-security-reactive-migration-guide-pinned-url"
    - "relevant-release-notes-or-security-advisories"
  impacted_features:
    - "authentication"
    - "authorization"
    - "csrf"
    - "oauth2-jwt"
    - "session-and-headers"
  behavioral_tests:
    baseline_run: "ci-test-report-id"
    candidate_run: "ci-test-report-id"
    differences:
      expected_same: []
      approved_changes: []
      unresolved: []
  operations:
    canary_signal: ["login-success", "401-403-ratio", "p95"]
    rollback_strategy: "documented-for-this-release"
  approval:
    security_owner: "reviewer-id"
    result: "pending"
```

This is a **structural template**, not an audited record for any product. Attach real evidence links, policy versions, test runs, reviewer sign-offs, and exception expirations in practice; never put passwords or JWTs into YAML.

## 12. Final Checklist Before Marking Migration Complete

- [ ] Recorded resolved baseline and candidate versions of Boot, Security, Framework, Reactor, Java, and Jackson.
- [ ] Read release notes, preparation guides, migration guides, and Reactive sections for the **exact upgrade path**.
- [ ] Every applicable change has an owner, applicability condition, required edits, and verifying tests.
- [ ] No Servlet config used in place of WebFlux, and no Boot defaults assumed when custom chains exist.
- [ ] Authentication (Basic/form/OIDC/bearer), authorization (HTTP and method), CSRF, CORS, headers, and sessions all have positive and negative tests.
- [ ] JWTs verify signature, `iss`, `aud`, `exp`, and `typ` per requirements; no custom validators dropped during migration.
- [ ] `ApplicationContext`-bound tests pass, alongside smoke tests through HTTP/TLS/gateways/IdPs in production-like environments.
- [ ] Zero unexplained security discrepancies; zero leaked tokens, PII, or exception details.
- [ ] Legacy serialization/session compatibility (if present) and rollback paths evaluated.
- [ ] Candidate release includes dependency graph, test reports, migration record, and required approvals.

## 13. References

1. Spring Security migration overview: https://docs.spring.io/spring-security/reference/migration/
2. Spring Security Reactive migration: https://docs.spring.io/spring-security/reference/migration/reactive.html
3. Spring Security 6.5 preparation for 7.0: https://docs.spring.io/spring-security/reference/6.5/migration-7/index.html
4. Spring Security 6.5 configuration preparation: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
5. Spring Security Reactive CSRF and version-related handler: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
6. Spring Security WebFlux request authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
7. Spring Security Reactive tests: https://docs.spring.io/spring-security/reference/reactive/test/index.html
8. Spring Boot Maven dependency management: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
9. Spring Boot reference / migration: https://docs.spring.io/spring-boot/reference/
10. Spring Security 6.5 preparation for JWT type validation: https://docs.spring.io/spring-security/reference/6.5/migration-7/oauth2.html

**Operational takeaway:** the primary value of a migration guide is generating **concrete hypotheses about changes**; final proof must come from resolved dependencies, running configurations, and tests verifying security decisions in the Reactive application. Only when all three match the approved security contract is the upgrade ready for release.
