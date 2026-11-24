# Reviewing Dependencies, Patches, and Configuration Before Release — Spring Security Servlet

## 1. Why Is a Successful Build Not Enough for Security?

A Spring Boot application uses Spring Security to protect APIs, login forms, or OAuth2 Login. Business tests are green and the JAR builds cleanly. Yet before release, many risks can still remain:

- **Direct or transitive dependencies** carry disclosed vulnerabilities; a library is declared at "the right version" in the POM while runtime resolves a different version via dependency mediation or overrides.
- **Spring Security and Spring Framework fall out of sync** because one dependency was bumped individually while the Spring Boot BOM still manages the remaining modules.
- **JDK, embedded Tomcat/Jetty, base images, proxies**, or native libraries remain unpatched even though the application's Java code has not changed.
- **Production config differs from test config**: sensitive URLs are marked `permitAll()`, CSRF is disabled globally, CORS is overly broad, session cookies lack required flags, or reverse proxies lack proper trust boundaries.
- **Secrets leak into configs/builds/logs**, demo accounts remain active, or actuator endpoints are accidentally exposed to the Internet.
- **Patches exist yet compatibility was never tested**; rushing a version bump alters login/session/CSRF behavior or silently breaks policy.
- **No rollback plan or release evidence**, so during an incident nobody knows which dependency versions or configs are actually running.

Therefore, "pre-release review" is an evidence-backed **security release gate**, not merely running `mvn package`.

Goal of this guide: establish a practical workflow to **inventory dependencies → triage vulnerabilities → select and test patches → verify Spring Security Servlet configuration → freeze artifacts/configs → roll out under control**, complete with a Java 17, Maven, Spring Boot 3, and MockMvc example.

**Version scope caveat:** The sample POM below pins **Spring Boot 3.3.5** to illustrate a reproducible configuration at a point in time. It **does not** imply 3.3.5 or any dependency in this article is the latest or still supported when you release. Before every release, check **current** vendor/upstream security advisories and support status, and pick patches approved by your organization. Never infer "active" CVEs from historical examples.

## 2. Inventory Scope: More Layers Than `pom.xml`

A Servlet application spans many layers:

~~~text
                         Source repository
                                  |
                                  v
                  pom.xml / dependencyManagement
                                  |
                 +----------------+----------------+
                 |                                 |
          Direct dependencies                Transitive dependencies
                 |                                 |
                 +----------------+----------------+
                                  |
                                  v
                    Spring Boot application JAR
                     Spring Security / Framework
                     Jackson / logging / embedded
                     Servlet container libraries
                                  |
                                  v
                       JDK + OS/base image
                                  |
                                  v
                Ingress / reverse proxy / TLS / WAF
                                  |
                                  v
                  Identity provider / DB / secrets
                                  |
                                  v
                      Production runtime config
~~~

Reviews must distinguish:

| Layer | What to verify | Evidence to keep |
| --- | --- | --- |
| Source/commit | Branch, commit, security config changes, and dependency sources | Commit SHA, review approval, changelog |
| Maven dependencies | Direct + transitive + runtime/test scopes, final resolved versions | Dependency tree, effective POM |
| Maven build plugins | Plugin versions, plugin dependencies, download sources, build behavior | POM, plugin reports, CI configuration |
| Spring Boot/Security | Boot BOM, Spring Framework, Spring Security, Spring MVC, embedded servlet container | BOM/resolved coordinates, compatibility tests |
| Java runtime | JDK vendor, version, security updates, JVM flags | `java -version`, image/host metadata |
| Image/OS | Base image digest, OS packages, native libraries | Image SBOM, scanner report, digest |
| Infrastructure | TLS/proxy/CDN, network policies, cookies, trusted headers | Deployment manifests, config diffs |
| Secrets/IdP | Secret sources, rotation, OAuth/LDAP/JWT trust configs | Secret inventory *without secret values*, approvals |
| Live application | `SecurityFilterChain`, endpoints, headers, logging, environment profiles | Test reports, smoke tests, deployment records |

**Do not ignore transitive dependencies:** an app may declare only `spring-boot-starter-web`, yet the starter pulls in many libraries including the embedded servlet container. SCA scanning only direct dependency lines misses a large portion of the attack surface.

**Do not scan only the JAR:** container images/OS packages, binary tools, and frontend JS libraries each have their own vulnerability lifecycle. A Java SCA tool does not replace an image scanner or secret scanner.

## 3. Spring Boot BOM: Upgrade Intentionally, Never Mix Arbitrarily

With Maven, the `spring-boot-starter-parent` parent manages compatible versions across many dependencies, including Spring modules. Using starters normally means **no need** to pin individual versions for libraries managed by the BOM.

Sound example in principle:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
</dependencies>
~~~

This is a **POM snippet**. A complete testable POM appears in section 8.

Four upgrade cases must be kept clear:

1. **Upgrading Spring Boot to a supported, compatibility-tested release**: usually aligns all managed libraries and pulls in related fixes. Read release notes and migration guides first.
2. **Overriding a BOM-managed dependency** for an emergency patch: only after evaluating blast radius, ABI/API compatibility, and approval. Record reason, related issue/CVE, override expiration date, and cleanup plan once the BOM catches up.
3. **Upgrading libraries outside the BOM**: still pin versions, run tests, and inspect licenses and transitive dependencies.
4. **Upgrading build plugins, JDK, or servlet containers separately**: can alter outputs, build behavior, or runtime behavior; verify at that exact layer instead of assuming bumping Spring Security alone covers it.

Anti-pattern example:

~~~xml
<!-- Example NOT to apply blindly -->
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-web</artifactId>
    <version>6.3.0</version>
</dependency>
~~~

If other parts of the same application still use a different Spring Security line managed by the BOM, conflicts or unpredictable behavior can arise. Do not judge `6.3.0` alone as vulnerable or safe; the issue illustrated is an **isolated override lacking compatibility evidence**.

When an override is unavoidable, inspect the **effective POM** and **resolved dependency graph** to confirm module consistency, and run regression tests covering filter chains, login, sessions, authorization, method security, and error handling. In multi-module Maven builds, check parent POMs, `dependencyManagement`, exclusions, test/runtime scopes, and per-module plugins.

## 4. Gathering Real Dependency Evidence with Maven

In a directory containing `pom.xml` with Maven/JDK installed:

~~~bash
# Record the exact JDK runtime/build used in the test environment.
java -version
mvn -version

# Clean + run unit/integration tests and configured verify goals.
mvn -B -ntp clean verify

# Inspect the dependency tree resolved by Maven.
mvn -B -ntp dependency:tree

# Save tree evidence to the build artifact directory.
mvn -B -ntp dependency:tree -DoutputFile=target/dependency-tree.txt

# Inspect the effective POM after inheritance, profiles, and dependencyManagement.
mvn -B -ntp help:effective-pom -Doutput=target/effective-pom.xml

# Suggest redundant or missing declared dependencies via usage analysis.
mvn -B -ntp dependency:analyze
~~~

**Read each command accurately:**

- `dependency:tree` shows the Maven-resolved graph, including direct and transitive artifacts. This is essential for checking final versions rather than trusting declared POM lines.
- `help:effective-pom` shows configuration after inheritance/profiles, exposing unexpected dependency overrides or repository/plugin settings.
- `dependency:analyze` focuses on declarations vs. bytecode references, which can yield false positives with reflection, annotation processing, or framework injection; **it is not a vulnerability scanner**.
- `clean verify` runs lifecycle phases and attached tests; if a project accidentally sets `skipTests` or a wrong profile, this command will not invent missing tests. Inspect test reports and actual CI steps.
- In multi-module builds, run from the reactor root and inspect each module's artifacts. For production profiles, compare the resolved graph under that profile; `mvn dependency:tree` under another profile does not guarantee an identical production classpath.

Save **dependency coordinates** (`groupId:artifactId:version:scope`) and the build/release JDK version. Never treat a red tool warning as absolute truth without checking where the dependency is used, whether it can be excluded from runtime, and whether an upstream patch exists.

**Reproducibility:** pin plugin/build tool versions, lock repository sources per policy, and avoid `LATEST`, `RELEASE`, snapshots, and unbounded version ranges. For images, prefer pinning **digests** over mutable tags. Built and scanned artifacts should be **promoted unchanged** from staging → production rather than rebuilt in production with different dependency versions.

## 5. SBOM: Component Inventory for Future Investigations

A **Software Bill of Materials (SBOM)** is a machine-readable document describing an artifact's components, typically in CycloneDX or SPDX format. It answers "Did last night's deploy include library X version Y?" without guessing from today's branch.

A sound workflow:

~~~text
Build clean from approved commit
        |
        +--> resolved dependency tree
        +--> Maven SBOM (direct/transitive components)
        +--> image/OS SBOM if packaged as a container
        +--> test + vulnerability/license scan
        +--> artifact SHA-256 + provenance
        |
        v
Archive with release ID and deploy that exact artifact
~~~

If your team uses the **CycloneDX Maven plugin**, pin the plugin version in `pom.xml` or central plugin management, generate the SBOM in CI, and archive the output. Example command **after the plugin is declared and pinned in the build**:

~~~bash
mvn -B -ntp cyclonedx:makeBom
~~~

Plugin configuration must be provided by your build team aligned with currently supported versions and internal policy; the learning example below **does not force unvetted security plugins**. In multi-module Maven builds, select the appropriate goal (such as an aggregate BOM) so other modules' components are not omitted.

An SBOM does not by itself determine whether a vulnerable dependency is **exploitable in your application**. It is input for SCA, inventory, incident response, and license governance. SBOM files can reveal internal architecture details; store and share them with appropriate access controls.

Verify SBOM quality: includes direct and transitive components, actual resolved versions, Java runtime/image layers where applicable, parser-valid format, and ties to the exact artifact checksum. If the SBOM was generated from `main` while production deployed a different JAR, evidence is broken.

## 6. SCA, CVEs, Advisories, and Patching Decisions

**Software Composition Analysis (SCA)** compares inventories against vulnerability feeds, outputting package versions alongside CVE/GHSA/advisory IDs. Assessment sources include:

- **Official** security advisories and release notes from Spring, related libraries, JDK, servlet containers, and OS/base images.
- Reputable advisory databases: CVE/NVD, GitHub Security Advisories, OSV, and authoritative known-exploited catalogs where applicable.
- Your organization's updated SCA/container scanner, recording scan timestamp and scanner version.
- Real verification against running code paths, whether vulnerable features are enabled, and available mitigations.

**No single CVSS score alone determines priority.** Also evaluate exploitability, active exploitation evidence, Internet exposure, pre-auth vs. post-auth requirements, data impact, actually affected versions, and patch availability.

A useful **triage record**:

| Attribute | Content |
| --- | --- |
| Component | `group:artifact:resolvedVersion` or OS package |
| Advisory | ID and official source URL |
| Exposure | Runtime? build/test-only? affected endpoint/capability in use? |
| Impact | RCE, SSRF, auth bypass, info leak, DoS, etc. per advisory |
| Exploitability | Public exploit or in-the-wild evidence? entry point exposed? |
| Fix | Vendor-confirmed fixed version, BOM compatible? |
| Workaround | Feature flag, endpoint/network block, risk-reducing config |
| Owner/deadline | Assignee and SLA by risk tier |
| Exception | Evidence-backed rationale, approver, expiration date |
| Evidence | Dependency tree, scan date, regression tests, deployment ID |

**Hypothetical example**: a scanner flags a vulnerability in parser X version Y pulled in via library Z. Do not immediately declare the product vulnerable to RCE from one scanner line; verify whether parser X is in the runtime artifact, receives untrusted input, and hits the affected code path. Equally, **never mark it a false positive** merely because the team has not seen an exploit. Base conclusions on advisories and testing.

When a patch cannot ship immediately: apply verified mitigations, raise controlled logging/monitoring, narrow exposure, and record a **time-bounded exception**. "Risk accepted" never means exempt from future review. For severe actively exploited vulnerabilities, you may need to **block the release or disable the feature** instead of shipping on schedule.

**Scanner freshness:** yesterday's clean scan does not prove zero new advisories today. Release gates should log SCA database timestamps and schedule periodic re-scans of running artifacts, especially for apps deployed infrequently.

## 7. Patching Workflow Without Breaking Security Behavior

Once a dependency requires patching, proceed methodically:

~~~text
Advisory / scanner finding
       |
       v
Verify affected coordinate and reachability
       |
       v
Choose vendor-supported fixed version / compatible BOM
       |
       v
Create isolated change; no broad unrelated upgrades
       |
       v
Resolve dependency graph + scan again
       |
       v
Compile + unit + integration + security regression
       |
       v
Build immutable artifact; verify checksum / SBOM
       |
       v
Staging/canary and rollback rehearsal
       |
       v
Production promotion + monitor + re-scan
~~~

**Small, clearly verified changes** are far easier to review and roll back than upgrading all plugins, the JDK, and Spring dependencies at once. Sometimes, however, the vendor requires upgrading an entire Boot/Spring line for a supported fix; in that case, check migration notes and related breaking changes.

Critical regression areas after upgrading Spring Security/Spring Framework:

- **URL matching**: `requestMatchers`, matcher ordering, servlet paths, multiple `SecurityFilterChain`s, encoded URLs/trailing slashes.
- **Authentication**: login, Basic, form login, OAuth2/OIDC, logout, failure handlers, session fixation protection, remember-me.
- **Authorization**: `hasRole`/`hasAuthority`, `@PreAuthorize`, role hierarchies, custom principals, and account status flags.
- **CSRF**: form POSTs, browser-called JSON endpoints, token repositories, cookie-backed SPAs, logout.
- **Headers/CORS**: CSP/HSTS, `X-Content-Type-Options`, CORS preflight/actual requests, `Origin` allowlists.
- **Servlet container/session**: cookies, forward/error dispatches, reverse proxies/forwarded headers, session timeout/persistence.
- **Other dependencies**: serialization/JSON, validation, logging, uploads/downloads, TLS providers, and timeouts.

For vulnerabilities in embedded Tomcat or Jackson, do not blindly edit a `starter-web` line without verification. Inspect the resolved version of the affected component, vendor release notes/fixes, and BOM compatibility.

A patch can fix a CVE while altering auth or session behavior; never approve a release solely because SCA turned from red to green without **negative security tests**.

## 8. Java 17 + Spring Boot 3.3.5 Example for a Security Release Gate

This compact example illustrates a Servlet app with explicit URL policies, preserved CSRF and security headers, and **MockMvc regression tests** before release.

**Important:** this is a **testing-practice application**, not production authentication. It intentionally provisions no real login users; tests build principals with `with(user(...))` to test authorization, while any HTTP Basic request with credentials is rejected. This avoids hardcoding demo accounts or relying on Spring Boot's generated default password as a production login flow. Before deploying a real business app, add a **verified authentication provider**, test it independently, and configure proper secrets management.

### 8.1. Structure

~~~text
release-security-gate-demo/
├── pom.xml
├── src/main/java/example/releasegate/ReleaseGateApplication.java
├── src/main/resources/application.properties
└── src/test/java/example/releasegate/ReleaseGateSecurityTests.java
~~~

### 8.2. Complete POM

**pom.xml**:

~~~xml
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
    <groupId>example</groupId>
    <artifactId>release-security-gate-demo</artifactId>
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

Do not declare separate versions for `spring-security-web`, `spring-security-config`, Spring MVC, or Jackson; let the parent/BOM manage them. If organizational policy requires a different patch, verify and document the upgrade/override per sections 3–7.

### 8.3. Minimal Configuration

**src/main/resources/application.properties**:

~~~properties
# Do not put secrets in files. Limit error details returned to clients.
server.error.include-message=never
server.error.include-stacktrace=never
~~~

This is **not** a complete production config checklist. In particular, HTTPS/trusted proxy/session cookie/actuator settings must match your real deployment architecture rather than copying properties blindly across environments.

### 8.4. Servlet Security Policy and Endpoints

**src/main/java/example/releasegate/ReleaseGateApplication.java**:

~~~java
package example.releasegate;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReleaseGateApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReleaseGateApplication.class, args);
    }

    @Bean
    UserDetailsService denyDefaultAccounts() {
        // Demo has no real users. This bean prevents Boot
        // from auto-creating a default account with a logged password.
        // Production MUST replace this with a real authentication provider.
        return username -> {
            throw new UsernameNotFoundException(
                    "No real users configured in demo");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/me")
                            .authenticated()
                        .requestMatchers(
                                HttpMethod.POST, "/api/notes")
                            .hasRole("USER")
                        .requestMatchers(
                                HttpMethod.GET, "/admin/audit")
                            .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .headers(headers -> headers
                        .contentSecurityPolicy(csp -> csp
                                .policyDirectives(
                                        "default-src 'self'; " +
                                        "object-src 'none'; " +
                                        "base-uri 'self'")))
                .build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/public/ping")
        Map<String, String> ping() {
            return Map.of("status", "ok");
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("user", authentication.getName());
        }

        @PostMapping("/api/notes")
        ResponseEntity<Map<String, String>> createNote() {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(Map.of("id", "note-1"));
        }

        @GetMapping("/admin/audit")
        Map<String, String> audit() {
            return Map.of("result", "restricted");
        }
    }
}
~~~

Explanation of each decision:

- `requestMatchers(HttpMethod.GET, "/public/ping").permitAll()`: only GET is public; avoids accidentally opening all HTTP methods on the URL.
- `GET /api/me`: requires authentication. Users without extra roles can still view their own data if profile logic is properly scoped.
- `POST /api/notes`: requires `ROLE_USER`. CSRF stays enabled, so role tests must supply a valid token.
- `GET /admin/audit`: `ROLE_ADMIN` only.
- `anyRequest().denyAll()`: undeclared routes/methods are blocked at Security before MVC runs. Do not assume 404/405 will happen instead.
- `httpBasic`: in the demo, unauthenticated protected requests typically return **401** instead of redirecting to `/login`; apps using form/OIDC login may have different entry points.
- `headers.contentSecurityPolicy`: adds a baseline CSP per demo policy. A CSP suited for this API is not automatically sufficient for SPAs or pages with inline scripts/styles; production must tailor CSP to real assets, potentially using nonces or report-only during rollout.
- Do not disable CSRF. `permitAll` or `authenticated` does not exempt endpoints from `CsrfFilter`.
- `denyDefaultAccounts` prevents the app from unexpectedly exposing a default login; **all external Basic credentials are rejected**. Test principals are constructed only in the test layer and must not be mistaken for real password authentication.

**Areas not covered by this demo:** multi-tenant ACLs, password policies, logout, session persistence, OAuth2/OIDC integration, rate limiting, error routing, HTTP proxies, and deployment secrets. Production deployments must add matching tests and protections rather than exposing the demo app directly as an authentication service.

### 8.5. Testing the Security Matrix with MockMvc

**src/test/java/example/releasegate/ReleaseGateSecurityTests.java**:

~~~java
package example.releasegate;

import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReleaseGateSecurityTests {

    @Autowired
    MockMvc mvc;

    record Scenario(
            String method, String path, String actor,
            boolean includeCsrf, int expectedStatus) {}

    static Stream<Scenario> matrix() {
        return Stream.of(
                new Scenario("GET", "/public/ping", "ANON",
                        false, 200),
                new Scenario("GET", "/public/ping", "USER",
                        false, 200),
                new Scenario("GET", "/api/me", "ANON",
                        false, 401),
                new Scenario("GET", "/api/me", "USER",
                        false, 200),
                new Scenario("GET", "/api/me", "ADMIN",
                        false, 200),
                new Scenario("POST", "/api/notes", "ANON",
                        true, 401),
                new Scenario("POST", "/api/notes", "USER",
                        true, 201),
                new Scenario("POST", "/api/notes", "ADMIN",
                        true, 403),
                new Scenario("GET", "/admin/audit", "ANON",
                        false, 401),
                new Scenario("GET", "/admin/audit", "USER",
                        false, 403),
                new Scenario("GET", "/admin/audit", "ADMIN",
                        false, 200),
                new Scenario("DELETE", "/api/notes", "ANON",
                        true, 401),
                new Scenario("DELETE", "/api/notes", "USER",
                        true, 403),
                new Scenario("DELETE", "/api/notes", "ADMIN",
                        true, 403)
        );
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("matrix")
    void endpointPolicy(Scenario s) throws Exception {
        MockHttpServletRequestBuilder builder = request(
                HttpMethod.valueOf(s.method()), s.path());

        // To test roles on unsafe methods, supply a valid CSRF token.
        if (s.includeCsrf()) {
            builder.with(csrf());
        }

        if ("USER".equals(s.actor())) {
            builder.with(user("alice").roles("USER"));
        } else if ("ADMIN".equals(s.actor())) {
            builder.with(user("admin").roles("ADMIN"));
        }

        mvc.perform(builder)
                .andExpect(status().is(s.expectedStatus()));
    }

    @Test
    void unsafeMethodMissingCsrfIsDenied() throws Exception {
        mvc.perform(post("/api/notes")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfIsDenied() throws Exception {
        mvc.perform(post("/api/notes")
                        .with(user("alice").roles("USER"))
                        .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void basicCredentialsDoNotCreateARealUserInDemo()
            throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("someone", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void responseHasRequiredHeaders() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"))
                .andExpect(header().string(
                        "Content-Security-Policy",
                        "default-src 'self'; object-src 'none'; " +
                                "base-uri 'self'"))
                .andExpect(jsonPath("$.status").value("ok"));
    }
}
~~~

The `@SpringBootTest` + `@AutoConfigureMockMvc` test uses the application's `SecurityFilterChain` in the Spring Test context. `with(user(...))` supplies a **test-constructed authenticated principal** without verifying passwords or IdPs, making it suitable for testing URL policies without production accounts. The separate `httpBasic(...)` test confirms the demo does not accidentally accept nonexistent accounts.

The matrix separates **anonymous, USER, and ADMIN**, HTTP methods, and CSRF. Note `ADMIN` holds only `ROLE_ADMIN`, not `ROLE_USER` automatically; hence `POST /api/notes` returns 403 in the demo. In a real app, configure a role hierarchy if required by business rules.

Interpret security assertions carefully:

- On **POST with the right role**, attach `.with(csrf())` so 201 proves both CSRF and authorization passed.
- On **POST missing CSRF**, 403 must not be treated as proof of role checks; write dedicated CSRF tests.
- On **undeclared methods**, `denyAll` may reject before Spring MVC returns 405.
- Checking CSP and `nosniff` confirms baseline headers are present; it does **not** verify HSTS, because MockMvc does not simulate real browser HTTPS connections.
- Method/URL authorization does not replace object-level ownership/tenant checks or data-access reviews.

Run from the project directory:

~~~bash
mvn -B -ntp clean verify
~~~

Expected behavior **from the declared code and dependencies**: the matrix, CSRF, Basic auth, and security header cases execute; the build passes the release gate only when all relevant tests pass. This is **expected behavior**, not build output observed on the current machine. To verify the real pipeline, run the command in a JDK/Maven/CI environment with dependency access.

If using a different Spring Security patch or entry point configuration, update the status contract intentionally. Never "make tests green" by adding `permitAll` to endpoints that should stay private.

## 9. Spring Security Servlet Configuration: Pre-Release Checklist

### 9.1. Inspect Every `SecurityFilterChain`

In an app that may define multiple chains:

- List **`securityMatcher`**, `@Order`, request scope, and filters attached to each chain.
- Ensure every sensitive URL matches **a protected chain**; avoid accidental catch-all `permitAll` chains or URLs matched by no chain.
- Inside `authorizeHttpRequests`, place specific matchers ahead of broad matchers; verify HTTP methods, servlet paths, context paths, and proxy rewrites.
- Enforce **default-deny** where possible with an explicit public allowlist: `/login`, public CSS/JS, restricted health endpoints, valid OAuth callbacks.
- Review `web.ignoring` or bypassing filter chains for static resources: whenever possible, use `permitAll` to keep security headers and filter behavior. Never expose private uploads as public static resources.
- For `@PreAuthorize` and method security: verify `@EnableMethodSecurity`, Spring-managed proxies, absence of self-invocation, and owner/tenant/permission checks in services.

A practical test ensures a regular user **cannot** open another user's files/orders merely because both hold `ROLE_MEMBER`. URL rules protect the **operation layer**; object-level ACLs protect individual records.

### 9.2. Authentication and Account Lifecycle

- Never ship `{noop}`, hard-coded passwords, generated development users, or auth-bypass endpoints.
- Verify `PasswordEncoder`/credential rotation, disabled/locked accounts, rate limiting, brute-force monitoring, logout, and recovery flows.
- If using OAuth2/OIDC: verify issuer/discovery/JWK, audience/client ID, redirect URIs, allowed scopes, `state`/`nonce`, token storage, callback CSRF/sessions, and external-identity-to-local-role mapping.
- If using a resource server: verify JWT signature/issuer/audience/expiration, opaque token introspection where appropriate, and authority mapping that never auto-escalates; never confuse login principals with Bearer API auth.
- If using LDAP: use LDAPS or StartTLS with certificate validation, least-privileged service accounts, and no plaintext credentials.
- Test logout/session revocation, role changes, and previously issued sessions.

**Distinguish authentication vs. authorization:** a successful login does not grant access to every tenant, project, or document. Specifically audit places reading client-sent `tenantId`, `userId`, or `role` instead of trusted identity from `SecurityContext`.

### 9.3. CSRF, CORS, and Browsers

**CSRF:** apps authenticating via cookies/sessions can have browsers automatically attach credentials on cross-site requests; keep CSRF enabled on unsafe methods. If disabling CSRF for a pure Bearer-token API group, document the threat model and prove credentials cannot be auto-sent by browsers under that mechanism. Never use `csrf.disable()` just to silence a MockMvc 403 without investigation.

**CORS:** never configure `allowedOrigins("*")` combined with credentials. Allow only required origins, methods, and headers; `Vary: Origin` and proxy caching can matter. `OPTIONS` preflight requests usually carry no cookies/credentials; when CORS is enabled, process CORS before authentication. `permitAll(OPTIONS)` **does not** generate valid `Access-Control-Allow-Origin` headers by itself.

**Cookies:** review `Secure`, `HttpOnly`, `SameSite`, domain/path, and session timeouts against your architecture. `SameSite` can affect OAuth login redirects/callbacks or cross-site flows, so test in real browsers. Cookie flags do not replace CSRF policy when cross-site attack surfaces remain.

### 9.4. Security Headers and TLS

- Verify `X-Content-Type-Options: nosniff`; verify `Content-Security-Policy` if rendering HTML, testing against real scripts/styles/assets.
- **HSTS** only applies when browsers receive it over valid HTTPS. Do not claim HSTS works from MockMvc HTTP tests alone; verify over HTTPS behind the real proxy.
- Verify TLS termination at proxies and outbound TLS to IdP/LDAP/databases, with no trust-all stores or disabled hostname verification.
- With proxies: accept `Forwarded`/`X-Forwarded-*` only from **trusted proxies**, enforce ingress controls, and strip client-supplied headers. Configure `server.forward-headers-strategy` per architecture; blindly trusting forwarded headers causes broken redirects, Host poisoning, and spoofed HTTPS.
- Check `Content-Disposition` and `Cache-Control` on private files. Never put secrets/tokens/PII in logs or public caches/CDNs.

### 9.5. Actuator, Debug Settings, and Errors

If using Spring Boot Actuator:

- Expose only `health`/`info` or strictly required endpoints; endpoints like `env`, `configprops`, `heapdump`, `loggers`, and `mappings` need dedicated access controls and should usually never be public.
- Separate the management port/network when feasible, with authn/authz and ingress rules matching risk.
- Configure minimal health details for unauthenticated callers to avoid leaking database/host names.
- Never leave Spring Security debug/trace or stack traces enabled in production without strict time limits and redaction.
- Never return raw exceptions, JWTs, passwords, access tokens, session cookies, or sensitive PII in HTTP error responses/logs.

**Note:** Actuator setups vary across applications; the section 8 demo **does not** include `starter-actuator`, so those endpoints do not exist there. Do not include `/actuator/**` in test matrices if the app actually does not declare it.

## 10. Secrets and Environment-Specific Configuration

A valid config in tests is **not** enough to assume production matches tests. Systems can pull config from YAML, environment variables, JVM system properties, Config Server, Kubernetes Secrets/ConfigMaps, Helm values, and secret managers.

What to verify:

1. **List of configuration inputs**, precedence order, and origins. In Spring Boot, an environment variable or CLI flag can override `application.yml`. Never open only files in Git to guess production settings.
2. **Active profiles** (`spring.profiles.active`), associated YAML/profile files, feature flags, and fallbacks. Clearly separate `local`, `test`, `staging`, and `prod`.
3. **Secrets**: DB passwords, OAuth client secrets, signing keys, TLS private keys, API keys, and webhook secrets come from managed stores with rotation/auditing; never bake into build artifacts.
4. **Block dangerous settings**: dummy secrets, `{noop}`, permissive auth, unapproved `csrf.disable()`, wildcard CORS + credentials, `spring.security.debug=true`, stacktrace exposure, demo datasource credentials.
5. **Never print effective config containing secrets to logs**. When diffing, redact values and compare critical keys/policies instead of dumping the entire environment.
6. **Config permissions**: who can edit Helm values, secret manager policies, ingress headers, and admission settings? Source review alone misses config changes made outside the repository.

Illustrative **production configuration example, not to be applied blindly**:

~~~properties
# HTTPS must actually be deployed at ingress/app.
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax

# Never return internal exception details.
server.error.include-message=never
server.error.include-stacktrace=never
~~~

Cookie properties require browser testing when using form/OIDC login/cookie sessions. For OAuth2 callbacks with special cross-site requirements, verify `SameSite` and cookie/session behavior in the real flow rather than switching to `SameSite=None` arbitrarily. In modern browsers, `SameSite=None` normally requires `Secure`; that still demands HTTPS and CSRF/threat modeling.

**Do not paste the sample config above into a POM or test file and claim production is safe.** Confirm **effective runtime values** post-deploy using redacted inspection tools and security approval.

## 11. CI/CD Release Gate: Checking at Build, Staging, and Runtime

A pipeline can enforce the following gates:

| Gate | Minimum criteria | Evidence to store |
| --- | --- | --- |
| Source review | Auth/security changes reviewed; no secrets in diff | Commit SHA, review, secret-scan report |
| Dependency resolution | No out-of-policy version ranges/snapshots; sound BOM | Tree, effective POM |
| SCA + license | Findings patched or valid exception; scan DB is fresh | SCA report + owner/expiry, license report |
| SBOM | Includes direct/transitive and links to exact artifact | CycloneDX/SPDX artifact |
| Build/test | Approved JDK, `clean verify` passes, no skipped tests | Test reports, redacted CI logs |
| Security tests | URL method/role, CSRF, headers, tenant ACL, auth failure pass | JUnit/MockMvc reports |
| Image/OS scan | No policy-violating findings; image digest pinned | Scanner report, image digest |
| Staging smoke | Login, logout, proxy TLS/cookies, public/private routes accurate | Automated smoke results |
| Approval | Risk exceptions/hotfixes have owner, expiry, and approver | Ticket/change record |
| Deploy | Promote exact scanned artifact; canary/rollback ready | Artifact digest, rollout ID |

Example **CI command sequence** for a Maven project:

~~~bash
set -e

java -version
mvn -version

mvn -B -ntp clean verify
mvn -B -ntp dependency:tree -DoutputFile=target/dependency-tree.txt
mvn -B -ntp help:effective-pom -Doutput=target/effective-pom.xml

# SCA, SBOM, license, and image scan steps are configured
# by your organization's CI with pinned tool versions and approved policies.
# Never delete/suppress scanner failures for a fake green pipeline.
~~~

This is a **Bash snippet for Linux/macOS CI environments**; Windows PowerShell requires matching syntax. `set -e` stops the script on command failure in normal contexts; CI must separately verify error handling across pipes/parallel jobs. These commands **do not replace an SCA scan**—configure an appropriate scanner to produce vulnerability evidence. If the scanner needs network access or fresh databases, manage caches, credentials, and update timestamps transparently.

Name artifacts by release ID/commit SHA, store checksums, and apply retention. Never store secrets/tokens in test attachments, screenshots, or plain-text pipeline artifacts.

### 11.1. Never Release When Tests Are Skipped

Flags like `-DskipTests` or `-Dmaven.test.skip=true` speed up builds yet **do not equal a quality gate**. CI must verify executed test counts and reports, not just the package stage's exit code.

Block automated deploys on critical regressions in authentication/authorization/CSRF or policy-breaching dependency findings without valid exceptions. During a security scanner outage, whether to fail closed or follow an emergency process must be pre-approved—never silently bypass scanners.

### 11.2. Artifact Verification and Provenance

Build artifacts from reviewed commits on trusted runners/toolchains. Store checksums (e.g., JAR SHA-256 or image digest), provenance/attestation where supported, SBOMs, and scanner reports. Promote an **immutable artifact** from staging to production. Never rebuild with altered dependency versions and reuse the old artifact's reports.

For container images, pinning base images by digest does not auto-apply security patches: maintain an active process to rebuild images when upstream fixes arrive. Never choose blindly between "pin" and "update"; combine **reproducibility + patch cadence**.

### 11.3. Post-Deploy Smoke Tests to Run

From an external client passing through the **real ingress/proxy**:

- Public health route exposes only permitted information.
- Protected route returns the right 401/302/403 entry point for anonymous callers.
- Login success/failure, token/session/cookie behavior, logout, and session invalidation.
- Low-role users cannot read admin routes; cross-tenant/non-owner access is denied.
- POST without CSRF token (where CSRF applies) is rejected; valid POST with right CSRF token and credentials succeeds.
- HTTPS redirects/hardening match design; cookies carry `Secure`/`HttpOnly`/`SameSite`; HSTS is verified over HTTPS.
- CSP/nosniff/caching headers are right; allowed vs. disallowed CORS origins behave per policy.
- Actuator/internal debug endpoints are not exposed; logs contain no secrets/tokens.

**Never run destructive operations in production** to "test DELETE". Use isolated tenant/test data, staging environments, dry-run interfaces, or non-destructive checks.

## 12. Canary, Rollback, and Post-Release Monitoring

Security review does not stop at the merge request. When deploying a patch:

1. **Pre-deploy:** snapshot versions, dependency tree, SBOM, image digest, and redacted configs; take backups/snapshots as needed; verify DB migrations are backward-compatible.
2. **Canary:** route a fraction of traffic or staging-equivalent traffic through the new artifact; monitor login success/failure, 401/403s, CSRF rejections, 5xxs, latency, session creation, IdP callbacks, and token issuance.
3. **Compare to baseline:** a post-deploy rise in 403s could mean tightened policy working rightly—or legitimate users being blocked. Do not inspect only aggregate KPIs; break down by endpoint, method, and observable user segments.
4. **Promote/rollback decision:** on authorization bypasses, broken token validation, or severe session/cookie bugs, halt rollout per runbook. Rolling back the application alone may not suffice if DB migrations ran or keys/secrets rotated.
5. **Post-deploy:** verify actual running pod/VM artifact digests, run smoke tests, watch for new advisories/scanner findings, create a change record, and notify owners.
6. **Post-release review:** update lessons learned, dependency waiver expirations, and regression tests for any bugs found.

**Never log excessive credential-bearing detail** just to debug auth failures. Focus on event codes, request IDs, endpoint/method, access decision type, and privacy-compliant version/tenant identifiers; redact Authorization headers, cookies, JWTs, reset links, and password payloads.

A sound rollback plan accounts for key rotation, session schemas, data migrations, and "rolling forward to a fixed version" when rolling back would reintroduce a severe vulnerability. Do not blindly revert to an old version confirmed exploitable; disable the feature or ship an emergency hotfix instead.

## 13. Handling Newly Disclosed CVEs After Release

An artifact that scanned clean at release can still have a new vulnerability disclosed later. Maintain a continuous workflow:

~~~text
New advisory / monitoring alert
           |
           v
Identify affected artifacts via SBOM + deployment inventory
           |
           v
Verify exposure, fixed versions and mitigation
           |
           v
Risk decision / escalation and interim controls
           |
           v
Patch -> regression gate -> staged rollout
           |
           v
Confirm active runtime versions + close incident ticket
~~~

Inventory queries must answer **which service, which environment, which artifact digest, and which dependency version** are currently running. Looking only at the latest POM on `main` does not tell you an older build is still running in staging or another region.

For severe CVEs:

- Check vendor advisories and fixed versions, exploitability in your environment, and exposed endpoints/capabilities.
- Identify deployed environments, potentially affected data, and responsible owners.
- Apply verified interim mitigations if patching cannot happen immediately.
- Re-run tests for authn/authz, CSRF, headers, sessions, proxies, and business invariants after upgrading.
- Record mitigations/exceptions in a change record with owner and expiration, then verify with updated SBOMs/deployed artifacts.
- Execute incident response and notifications per organizational obligations when required.

Never write "just upgrade to version X to be safe" without verifying current advisories and BOM compatibility. For fast-moving libraries and security frameworks, verify exact fixed versions from authoritative sources **at remediation time**.

## 14. Common Mistakes in Release Security Reviews

| Mistake | Risk | Right approach |
| --- | --- | --- |
| Inspecting only direct dependencies | Misses transitive CVEs | Resolved tree + runtime SBOM |
| Treating `pom.xml` version as runtime version | BOM/profile/override may change resolved version | Effective POM + dependency tree |
| Overriding only `spring-security-web` blindly | Module version skew/compatibility bugs | Upgrade BOM cleanly or verify overrides |
| Confusing `dependency:analyze` with SCA | Does not check CVEs | Dedicated SCA/advisory reports |
| Relying solely on CVSS | Ignores reachability/active exploits/business impact | Evidence-based triage and SLAs |
| Scanning SBOM from branch, deploying another artifact | Results do not match production | Promote immutable artifacts; verify checksums |
| Skipping tests/CSRF to force a green build | Misses regressions or opens auth bypasses | Negative tests and approved policy exceptions |
| Testing only with `@WithMockUser` | Skips auth providers/credentials | Add real login/token integration tests |
| Assuming every POST 403 is a role check | Could be `CsrfFilter` blocking first | Role tests with valid CSRF + separate CSRF tests |
| `permitAll("/**")` to silence 401/403s | Exposes unintended URLs | Narrow public allowlist + `denyAll` |
| CORS `*` with credentials | Data exposure via browser policy | Origin allowlist; audit preflights |
| Trusting arbitrary forwarded headers | Wrong redirect host/scheme, broken trust boundary | Trusted proxies; ingress header sanitization |
| Enabling HTTPS only on app, forgetting outbound TLS | Credentials leak to LDAP/IdP/DB | End-to-end TLS/truststores, hostname verification |
| Leaking secrets in artifacts/config dumps | Long-lived key/credential exposure | Secret managers; redact CI/logs |
| Exposing actuator/debug without auth | Leaks env/config/heap/logs | Restrict endpoints + network + auth |
| No rollback or deployment evidence | Hard recovery after hotfixes | Immutable artifacts, checksums, change records |
| Closing CVEs with indefinite exceptions | Forgotten lingering risk | Owner, evidence, deadline/expiry |
| Pinning image digest and never rebuilding | Runs stale OS packages | Pin + regular patch/image rebuild cadence |
| Assuming old releases are "still supported" | Misses upstream security patches | Check current lifecycle/support/advisories |

Prioritize verifying **runtime security behavior**, not just how clean YAML or POM files look. A configuration that looks right on paper can still leave no protection if shadowed by another chain or overridden by environment settings.

## 15. Self-Check Exercises

**Q1.** The POM declares `spring-boot-starter-web`, not Tomcat. Must Tomcat vulnerabilities still be checked?  
**Yes.** The embedded container is a transitive runtime dependency and must appear in inventory/SCA.

**Q2.** Dependency tree has zero warnings and `mvn clean verify` passes. Does that prove zero CVEs?  
**No.** You need up-to-date SCA/advisory scans and separate triage; builds/tests are not vulnerability databases.

**Q3.** To patch a Spring Security flaw, should you arbitrarily pin one Spring Security module higher than the BOM?  
**No.** Check vendor-supported fixed versions, BOM compatibility, and regressions; use controlled overrides only when necessary.

**Q4.** A POST endpoint returns 403 for a user with the right role. Is the role rule definitely wrong?  
**No.** A CSRF token may be missing. Role tests must include a valid CSRF token; test missing tokens separately.

**Q5.** A scanner flags a test-only dependency; can you delete the alert without review?  
**No.** Verify scope and threat model, as build/test environments also carry supply-chain risk; prioritize by impact and policy.

**Q6.** A CORS preflight `OPTIONS` without cookies gets 401. Should users log in for preflights?  
**Not necessarily.** When CORS is enabled, preflights should be handled properly before auth; actual requests still enforce authentication/authorization.

**Q7.** MockMvc sees `X-Content-Type-Options` properly and no HSTS over HTTP. Can you conclude production lacks HSTS?  
**No.** HSTS is observed over HTTPS; verify through the real ingress/proxy.

**Q8.** Runtime config in Kubernetes differs from `application.yml` in Git. Which serves as security evidence?  
**The effective values after merging all configuration sources**, collected/redacted with proper permissions; source files are only one input.

**Q9.** An image was built and scanned in staging, then rebuilt in production for deploy. Do the scan results still hold?  
**No.** Dependencies/images may differ; promote the exact verified artifact/digest.

**Q10.** Firewall exposure was narrowed for an unpatched CVE. Can you mark it fixed and stop tracking?  
**No.** That is a time-bounded mitigation/exception needing an owner, reviews, and a patching plan.

**Q11.** Passing `@WithMockUser` tests proves `PasswordEncoder` or OIDC signature validation works, right?  
**No.** Mock principals bypass authentication providers; write dedicated integration tests.

**Q12.** After a patch, 401/403s jump sharply. Is that automatically good news showing more attacks are blocked?  
**Not by default.** Classify whether blocked requests are legitimate traffic or authorization/CSRF/session bugs, compare baselines, and test valid users.

## 16. Practical Release Gate Checklist

### Before Building the Artifact

- [ ] Commits reviewed; secret scanning finds no exposed credentials/keys.
- [ ] JDK/toolchain and lifecycle support verified against current upstream sources.
- [ ] Dependency tree + effective POM archived; direct/transitive versions are clear.
- [ ] BOM and any Spring/Security/Servlet overrides reviewed together.
- [ ] SCA + license + image/OS scans use fresh data; findings have fixes or valid owner/expiry exceptions.
- [ ] SBOM ties to the exact artifact; plugins/build sources are governed.
- [ ] Clean build/test without skips; test reports archived and executed test counts verified.

### Before Deploying to Staging

- [ ] URL/method/role matrix covers anonymous, wrong roles, CSRF, and owner/tenant negative cases.
- [ ] Spring Security filter chains, matcher order, and default-deny verified in the target environment.
- [ ] CSRF/CORS/headers/cookies/sessions/redirects/proxies tested against the threat model.
- [ ] OAuth/OIDC, LDAP, JWT, and authn providers tested if used by the application.
- [ ] No admin/test accounts, `{noop}`, security debug, or unapproved endpoint bypasses.
- [ ] Secrets come from proper stores; runtime config diffs redacted; production profile accurate.
- [ ] Actuator/internal endpoints and error details not exposed publicly.
- [ ] Staging tested through proxy/TLS/IdP/DB close to production, not MockMvc alone.

### Before Promoting to Production

- [ ] Artifact/image digest, SBOM, test reports, SCA reports, and commit SHA match.
- [ ] Approver, runbook, canary/rollback or roll-forward plan in place.
- [ ] DB migrations and session/key-rotation impacts checked before any rollback.
- [ ] Post-deploy smoke tests cover anonymous/low-role/admin, CSRF, and headers.
- [ ] Monitoring tracks auth failures/401/403/5xx by method/endpoint without logging secrets.
- [ ] Owner and re-scan schedule assigned for post-release advisories.

**Conclusion:** Reviewing dependencies, patches, and configuration before release is not a checklist divorced from security engineering. For Spring Security Servlet, a trustworthy release requires **knowing the exact packaged versions**, **triaging and remediating vulnerabilities with evidence**, **verifying runtime protections**, **running regression tests for authentication/authorization/CSRF**, and **shipping the exact verified artifact** with post-deploy observability, revocation, and remediation readiness.
