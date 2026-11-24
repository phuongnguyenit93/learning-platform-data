# Reviewing Default Behavior Changes, Renamed Properties, and Server Support When Upgrading Spring Boot

## 1. Why Isn't "Bump Version and Build Green" Enough?

A Spring Boot application can **compile, start, and return HTTP 200** after a version upgrade yet still behave differently on real requests: URLs with a trailing `/` stop matching, `server.*` was renamed so HTTP header limits no longer apply as expected, `management.*` exposes admin endpoints differently, Servlet/Jakarta APIs break on an older Tomcat, or tests using a mock context miss an HTTP listener failure.

Upgrading Spring Boot is a **web runtime contract verification** problem, not just bumping version numbers in `pom.xml`/`build.gradle`.

Three risk areas you must audit:

1. **Default behavior changes:** identical code/config yields different routing, security, encoding, shutdown, metrics, sessions, HTTP errors, server auto-configuration, or dependency behavior.
2. **Configuration migration (renamed/removed/repurposed properties):** old keys are ignored, temporary aliases expire, new defaults apply silently, or higher-precedence config sources override them.
3. **Server and platform support:** Java, Spring Framework, Jakarta Servlet, Tomcat/Jetty/Undertow, Netty, external WAR containers, build plugins, Spring Cloud, and dependencies must fit the **compatibility matrix**.

This article belongs to **Debugging and Upgrades** in the **Spring Boot - web-runtime** module. Hands-on examples use **Spring Boot 3.5.16, Java 17+, Maven, and Spring MVC/Tomcat** as the baseline and specifically explain migrating from Spring Boot 2.x → 3.x and 3.5.x → 4.x. Version numbers are **illustrative milestones anchored to each line's docs**, not a mandate that every app must upgrade immediately to that exact patch.

### After This Article You Will Be Able To

- Inventory code, dependencies, configurations, and runtime environments prior to upgrading.
- Distinguish **changed defaults**, **renamed keys**, **removed APIs**, and **unsupported containers**.
- Use release notes, migration guides, metadata, diagnostics, and `spring-boot-properties-migrator` properly.
- Verify effective config after multiple sources (profiles, environment, CLI, Kubernetes) combine.
- Write regression tests covering HTTP path matching, status/body, headers, health, security, and startup.
- Audit embedded Tomcat/Jetty/Undertow and external WAR containers per major release line.
- Roll out incrementally with canaries, metrics, rollbacks, and documented evidence.

## 2. Four Change Types Commonly Conflated

| Change type | Meaning | Verified example | Response |
| --- | --- | --- | --- |
| Default changed | Property omitted; behavior changed automatically | Spring Framework 6 defaults to **no** trailing-slash matching | Write contract tests and state explicit policy |
| Property renamed | New key replaces old key | Boot 3: `server.max-http-header-size` → `server.max-http-request-header-size` | Update source configs, verify binding |
| API/dependency migration | Package/class/starter changed | Boot 3: Servlet imports `javax.servlet` → `jakarta.servlet` | Recompile, update deps, test runtime |
| Support matrix changed | Older runtime/server no longer supported | Boot 4: Servlet 6.1, Tomcat 11 baseline; Undertow dropped | Pick supported server, update image/OS/deploy |

A renamed property **does not guarantee the default value stayed the same**. Nor should you assume "migrator reported zero old keys" means every config is valid: keys in Kubernetes ConfigMaps, environment variables, Helm templates, external secrets, or `@PropertySource` may not be evaluated by the migrator at the right moment.

### Easily Misunderstood Example

Suppose an API defines:

```java
@GetMapping("/api/items/{sku}")
public Item get(@PathVariable String sku) { ... }
```

In an older system, `/api/items/pen/` might return 200. Spring Framework 6 flipped default trailing-slash matching to **`false`**, so the same URL can now return 404. Counting controllers or checking compilation will not catch this. You must test both URLs explicitly and decide the API contract: accept both, redirect to canonical URL, or return 404.

The snippet above is **illustrative**, not a standalone Java file. Runnable code is in section 11.

## 3. Record a Baseline Before Changing Versions

Do not start by editing the POM. First capture a **reproducible baseline**.

### 3.1. Mandatory Inventory

| Area | What to record |
| --- | --- |
| Build | Spring Boot parent/plugin, Maven/Gradle wrapper, Java toolchain, Gradle/Maven versions |
| Spring stack | Spring Framework, Spring Security, Spring Data, Spring Cloud train, Micrometer, Actuator |
| Web runtime | MVC vs. WebFlux, Tomcat/Jetty/Undertow/Netty, embedded vs. external WAR |
| Container | Tomcat image/version, Jakarta Servlet level, OS/JDK, connectors, HTTP/2/TLS |
| Dependencies | BOM, dependency tree, pinned/overridden versions, `javax.*` libraries, native libs |
| Runtime config | `application*.yml/properties`, environment, CLI args, ConfigMap/Secret, JVM/system props |
| HTTP contract | Method/path/status, media types, validation, error schema, trailing slash, CORS |
| Edge behavior | Headers, forwarded proxies, sessions/cookies, compression, upload limits, shutdown |
| Observability | Actuator exposure, metric names/tags, traces, health/readiness, log format |
| Operations | Resource limits, pool/thread counts, database schema, deploy strategy, rollback |

Also capture **Git revision, container image digest, commit/build ID**, active profile lists, and sanitized **secret-free** configurations. Never dump tokens/cookies/passwords from `Environment` into logs just to diff them.

### 3.2. Capturing Build Information

Maven:

```bash
java -version
mvn -version
mvn help:effective-pom
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.boot:*,org.springframework:*
```

The `-Dincludes` syntax above illustrates filtering the dependency tree via Maven Dependency Plugin; if your shell expands `*`, quote the argument or use simpler includes. `effective-pom` in real projects can contain sensitive config; never publish it openly.

Gradle:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot
./gradlew dependencyInsight --dependency tomcat
```

For full dependency auditing, save SBOM/SCA reports supported by your CI pipeline. The goal is spotting transitive versions that diverge from the Spring Boot BOM before and after version bumps.

### 3.3. Capture an HTTP Baseline

At minimum, run representative requests before upgrading:

```bash
curl -i http://127.0.0.1:8080/api/items/pen
curl -i http://127.0.0.1:8080/api/items/pen/
curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":2}'
curl -i http://127.0.0.1:8080/actuator/health
```

These are **command templates**. For real apps, substitute your actual contract URLs, ensuring the test environment is authorized and test data is synthetic. Record status, `Content-Type`, JSON schema, headers, and body—not just "the endpoint answered."

## 4. Reading Upgrade Documentation in the Right Order

**Reliable reading order:**

1. **Spring Boot system requirements** for the target line/version.
2. **Migration guide** from source major/feature line to target line, focusing on web, properties, tests, and servers.
3. **Release notes for every intermediate feature release** crossed—do not skip versions in between.
4. Release notes for Spring Framework, Security, Data, Cloud, Micrometer, and libraries you actually use.
5. API Javadoc, configuration metadata, and runtime diagnostics to verify target keys/APIs.
6. Empirical regression tests against the target artifact/container.

When going from **2.7.x → 3.5.x**, reading only 3.5 release notes is insufficient. Understand Boot 3.0 migration (Jakarta, Spring Framework 6, property renames, URL matching) plus 3.1/3.2/3.3/3.4/3.5 changes. When going from **3.5.x → 4.x**, study the Boot 4 guide carefully because it is a major migration: Spring Framework 7, Servlet 6.1, module/starter reorganizations, and removed deprecated APIs.

**Never rely on a blog written for Boot 2 or snapshot docs to infer behavior of a new target line.** Always verify the documentation URL/version.

## 5. Version and Server Matrix Overview

The milestones below follow official system requirements and migration guides; read by **target line** rather than mixing a Boot 4 server assumption into Boot 3.

| Milestone | Minimum Java | Spring Framework | Notable embedded Servlet containers | External WAR |
| --- | --- | --- | --- | --- |
| Boot 2.7.x | Java 8 (verify exact patch) | Spring Framework 5.3 | Tomcat 9 / `javax.servlet` generation | Servlet 3.1+ / Java EE generation, varies by release |
| Boot 3.5.16 | Java 17 | Spring Framework 6.2.19+ | Tomcat **10.1** (Servlet 6), Jetty **12.0** (Servlet 6), Undertow **2.3** (Servlet 6) | **Servlet 5.0+ compatible** |
| Boot 4.0.x | Java 17 | Spring Framework **7.x** | Tomcat **11**, Jetty **12.1** (Servlet 6.1) | Servlet **6.1+**; Undertow support removed |
| Boot 4.1.x | Java 17 (per current docs) | Spring Framework 7.x | Tomcat 11 / Jetty 12.1 Servlet 6.1 | Check system requirements page for the **exact patch** |

**Note:** the 2.7.x row is a **generational summary**, not blanket approval of Java 8 across future dependencies/JDKs. Certain Boot 2.7 patches or libraries have specific platform requirements; verify the exact release. For Boot 4.1, consult `https://docs.spring.io/spring-boot/4.1/system-requirements.html` rather than treating table rows as static across all patches.

### 5.1. Three Server Compatibility Checks

- Read target **Boot system requirements** and the Embedded Container matrix.
- Check the **Java/Jakarta Servlet** level of external Tomcat/application servers. Tomcat 9 (`javax.servlet.*`) cannot run Boot 3 Jakarta Servlet apps directly; Tomcat 10.1 targets Servlet 6.0; Tomcat 11 targets Servlet 6.1.
- Verify real runtime on deployment: `NoSuchMethodError`, `NoClassDefFoundError`, missing classes, Servlet startup, HTTP routing, SSL connectors, and proxy paths. Compile success does not prove external WAR compatibility.

### 5.2. Undertow Changes Between 3 and 4

Boot 3.5 supports Undertow 2.3 as an embedded Servlet option. The Spring Boot 4 migration guide **removed Undertow support** due to the Servlet 6.1 baseline, which Undertow did not meet at release time. If an app uses:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-undertow</artifactId>
</dependency>
```

that is a **Boot 3.x dependency snippet** and cannot simply remain assuming Boot 4 supports it. When upgrading to Boot 4, pick supported Tomcat or Jetty, and verify connection settings, compression, websocket/session behavior, and latency instead of merely swapping starters and assuming identical behavior.

### 5.3. Spring Boot 4 Modular Starters

Boot 4 adopts more modular starters. Per the 4.0 migration guide, `spring-boot-starter-web` is deprecated in favor of **`spring-boot-starter-webmvc`** when upgrading. Similarly, technologies like Flyway/Liquibase require their dedicated Boot starters. Never assume Boot 3.5 code compiles unchanged on 4.0 just by bumping the version: package names, test auto-configuration, and dependencies can change.

In Boot 4, **classic starters** may exist as a transitional bridge where permitted by the migration guide, though they should not be the long-term destination. Check the exact starter and package-move tables in the guide.

## 6. Default Changes Requiring Special Audit in Web Runtime

A changed default can **pass the build cleanly** yet break production. The areas below need explicit regression tests or explicit policy decisions.

### 6.1. Trailing Slash and Path Matching

Spring Framework 6.0 changed default trailing-slash matching to **`false`**: `/api/items/pen` and `/api/items/pen/` are no longer equivalent by default.

For example, Boot 2.x / older Spring MVC may return 200 for both, whereas Boot 3.x may return 404 on the trailing-slash URL. Do not globally re-enable the old behavior just to turn tests green without auditing security matchers and proxies; instead:

- Return 404 for non-canonical URLs.
- Redirect `/api/items/pen/` to `/api/items/pen` at the gateway/filter with proper semantics (308 preserves method/body better than 301 in many cases).
- Explicitly declare both routes if the API contract genuinely supports both.
- Review Security matchers so one path isn't protected while its sibling is exposed.

**Test the actual URLs** in the target environment. `MockMvc` validates MVC mappings; live HTTP/proxy tests are needed when path rewrites or container contexts matter.

### 6.2. HTTP Request Header Size and Container Differences

In the Boot 3 migration, the old property:

```properties
server.max-http-header-size=16KB
```

was replaced by:

```properties
server.max-http-request-header-size=16KB
```

The new key emphasizes **request** header size. Boot 3.0 docs explain the old key had inconsistent behavior: Tomcat sometimes applied it to response headers too, unlike Jetty/Netty/Undertow. Bounding **response headers** on some servers requires server-specific customization rather than the new request key.

Never assume keeping the old key maintains the same limit after upgrading. Test oversized request headers safely within test limits, confirm the status emitted by the **actual target server**, and do not assume status codes are identical across containers.

### 6.3. Actuator Web and JMX Exposure

The Spring Boot 3.0 migration guide notes default JMX exposure narrowed to **health** only, aligning with web exposure defaults. Also, the `httptrace` endpoint was renamed to **`httpexchanges`**, with updated APIs and repository classes.

What to test:

- Which endpoints are actually exposed over HTTP/JMX?
- Are admin/metrics endpoints protected by security/network policy?
- Did health/readiness paths shift due to `context-path` or management `base-path`?
- Do monitoring dashboards and alert rules still match metric names/tags?
- Do legacy clients calling `/actuator/httptrace` need migrating to `/actuator/httpexchanges`?

This is an **endpoint rename**; do not assume every `management.endpoint.httptrace.*` property maps 1-to-1 automatically to the new prefix.

### 6.4. Spring Security Defaults and Matcher Behavior

Spring Security versions also advance alongside Boot. Do not rely on pre-5.7 `WebSecurityConfigurerAdapter` patterns, ant matchers, or legacy default security auto-configuration. In Boot 3 / Spring Security 6, define a `SecurityFilterChain` bean using compatible `requestMatchers`.

Regression tests must ensure:
- Anonymous users reach public endpoints while private ones return 401/403 properly.
- POST/PUT/DELETE with session cookies enforce CSRF rules.
- CORS preflights follow policy.
- Trailing-slash/context-path matcher patterns leave no unprotected gaps.
- Password encoders, session/cookie flags, and auth redirects stay accurate.

**Never disable the entire `SecurityFilterChain` just to make an upgrade test pass.**

### 6.5. Request/Response Content, JSON, and Error Handling

Check:
- Jackson version and module registration (Java Time, Records, Kotlin).
- Unknown JSON fields, enum coercion, naming strategies, dates/time zones.
- Bean Validation annotations/Jakarta packages and error body shapes.
- `Accept`/`Content-Type` negotiation and 406/415.
- `ProblemDetail`/error responses if enabled or customized.
- Multipart limits, temp upload directories, and proxy buffering.
- Compression, forwarded headers, redirects, and host/scheme construction.

Many regressions surface only on invalid inputs. Negative tests for 400/404/405/415/401/403 are just as vital as 200 tests.

### 6.6. Graceful Shutdown, Async, and Resource Lifecycles

The Boot 3 migration guide notes changes in graceful shutdown lifecycle phases. Apps with custom `SmartLifecycle`, schedulers, message listeners, or connection-draining logic must test shutdown ordering, termination duration, and readiness behavior. Also verify:
- Do in-flight requests finish cleanly or get cut off?
- Is the Kubernetes `terminationGracePeriodSeconds` long enough?
- Do JDBC pools, HTTP clients, and thread executors shut down cleanly?
- Do sticky sessions or WebSocket connections recover as designed?
- Do health/readiness probes flip before stopping traffic acceptance?

Never apply a single arbitrary timeout without measuring your workload.

## 7. Property Renames: Read the Exact Key and Version Scope

Examples sourced from official migration guides:

| Context | Old key/name | New key/name or action |
| --- | --- | --- |
| Boot 2.7 → 3.0 | `server.max-http-header-size` | `server.max-http-request-header-size` |
| Boot 2.7 → 3.0 Redis | `spring.redis.*` | `spring.data.redis.*` |
| Boot 2.7 → 3.0 Cassandra | `spring.data.cassandra.*` | `spring.cassandra.*` |
| Boot 2.7 → 3.0 Actuator endpoint | `httptrace` | `httpexchanges` endpoint/API; review clients |
| Boot 3.x → 4.0 Spring Session Redis | `spring.session.redis.*` | `spring.session.data.redis.*` |
| Boot 3.x → 4.0 Spring Session MongoDB | `spring.session.mongodb.*` | `spring.session.data.mongodb.*` |
| Boot 4 starters | `spring-boot-starter-web` | `spring-boot-starter-webmvc` recommended |
| Boot 4 test HTTP clients | Boot 3 `TestRestTemplate` auto-configuration assumptions | Boot 4 requires explicit test auto-configuration/dependencies; check migration guide |

**Do not treat this table as a blind search-and-replace across every repo**. Know your source/target versions and which components the app uses. An app without Cassandra needs no Cassandra key edits; an app using a non-Spring-Data Redis client may have its own config namespace.

### 7.1. Rename vs. Removal vs. Semantic Change

- **Rename:** same-meaning property moved to a new name; old key may work temporarily as an alias.
- **Remove:** property deleted completely; must be removed or redesigned, with no alias.
- **Split/merge:** one old key splits into multiple new keys, or a new key changes scope.
- **Behavior changed:** key name stayed identical, yet default, precedence, or implementation changed.
- **Conditional auto-configuration changed:** bean is created only when matching classpath/feature dependencies exist.
- **Starter moved:** dependency coordinate changed even if properties stayed the same.

If an auto-config no longer loads, a property can sit in config without ever binding. Inspect effective `@ConfigurationProperties` beans and condition evaluations rather than just grepping keys in source code.

## 8. Spring Boot Properties Migrator: A Transition Aid, Not a "Fix"

Spring Boot provides `spring-boot-properties-migrator` to inspect `Environment` at startup, log diagnostics about renamed/removed properties, and—for supported cases—**temporarily migrate values at runtime**.

Add **temporarily** in Maven for the target Spring Boot line:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
```

Gradle:

```groovy
runtimeOnly("org.springframework.boot:spring-boot-properties-migrator")
```

Workflow:

1. Bump dependencies and run the app in local/staging with production-like profiles.
2. Read warning diagnostics: legacy keys, suggested replacements, or removed keys.
3. Update the **actual configuration sources**: application YAML, environment variables, Helm/Kustomize/ConfigMaps, deploy scripts, secret references, CI variables.
4. Restart to verify warnings are gone and behavior matches.
5. **Remove the migrator dependency** from production builds once finished.

**Never leave the migrator installed permanently.** Boot docs warn that properties added late to `Environment` (e.g., via `@PropertySource`) may not be processed. The migrator cannot inspect custom app-invented keys, unrendered Helm templates, or env vars absent at runtime, and never replaces integration tests.

### 8.1. Configuration Edit Example

Legacy config when migrating from 2.7 to 3.x:

```properties
server.max-http-header-size=16KB
spring.redis.host=redis.internal.example
spring.redis.port=6379
```

Spring Boot 3.x config:

```properties
server.max-http-request-header-size=16KB
spring.data.redis.host=redis.internal.example
spring.data.redis.port=6379
```

The hostname above is an **illustrative placeholder, not a real target**. Never commit real credentials or private production addresses into guides. Test network connectivity and Redis version compatibility separately when the app actually uses Redis.

### 8.2. Mandatory Steps After Using the Migrator

- Confirm every key actually binds via config binder, not just that warnings vanished.
- Measure effective behavior: header limits, Redis connections, session TTL, Actuator exposure, HTTP statuses.
- Check across local/staging/prod profiles.
- Inspect the dependency tree to confirm required auto-configurations are on the classpath.
- Re-run smoke and integration tests **after removing the migrator**; if the app only works while the migrator is present, migration is incomplete.

## 9. Property Precedence and "Silently Overridden Values"

Even after updating the right key, runtime can still pick a different value due to configuration source precedence.

Common sources:

- `application.properties`/`application.yml` inside the artifact.
- `application-prod.yml`/`application-staging.yml` for active profiles.
- External config locations / config trees.
- Host/container/pod environment variables.
- JVM system properties and CLI arguments.
- Test-specific `@TestPropertySource`/`@SpringBootTest(properties=...)`.
- Spring Cloud Config or external config providers (if used).

Example:

```properties
# Inside the JAR
server.port=8080
```

Launched as:

```bash
java -jar app.jar --server.port=9090
```

The CLI argument overrides the properties file. Looking only at the file and concluding the app opens 8080 is wrong for that process.

### 9.1. Inspecting Effective Configuration Safely

- Read startup logs: active profiles and actual bound port.
- If Actuator is present, inspect `configprops`/`env` **only in protected environments**, with sanitization and access control, when verifying bindings.
- Log **allowlisted non-sensitive values** in a test-only diagnostic endpoint if helpful.
- For secret values, verify **source and bound state**, never printing plaintext.
- Test against production-like artifacts/containers, not just `mvn test` with default profiles.
- Search for legacy keys across CI/CD, ConfigMaps, Deployment env vars, Helm charts, and external configs; repo search alone is insufficient.

### 9.2. Relaxed Binding Does Not Fix Renames

Spring Boot supports relaxed binding (e.g., `server.max-http-request-header-size` and `SERVER_MAX_HTTP_REQUEST_HEADER_SIZE` in environment variables). However, relaxed binding **does not translate a removed property name into its new name**. If a deployment passes `SERVER_MAX_HTTP_HEADER_SIZE`, it does not bind as `SERVER_MAX_HTTP_REQUEST_HEADER_SIZE` in Boot 3.

Determine the exact full name of the new key rather than expecting Boot to "guess" the old name.

## 10. Choosing BOMs, Starters, Jakarta, and Servers

### 10.1. Let Boot Manage Dependency Versions Whenever Possible

In Maven, use `spring-boot-starter-parent` or import the `spring-boot-dependencies` BOM. In Gradle, use the Boot plugin and dependency management / native platforms. Avoid pinning individual versions of Spring Framework, Tomcat, Jackson, SnakeYAML, Netty, Hibernate, or Micrometer without a supported reason and regression tests.

If using Spring Cloud, pick the release train compatible with the **target Boot line**. Never upgrade Boot 3.x → 4.x while leaving an incompatible Cloud train just because it compiles. Verify official compatibility matrices, enterprise support policies, and third-party starter versions.

### 10.2. Servlet Containers When Migrating Boot 2 to 3

- Boot 2 / Framework 5 used the `javax.servlet` generation; Tomcat 9 was standard.
- Boot 3 / Framework 6 moved to `jakarta.servlet`, Jakarta EE 10 baseline.
- Update import statements, compiled libraries, test dependencies, and external Tomcat accordingly.
- An external WAR built for Boot 3 will not run incompatibly on Tomcat 9 due to Servlet API namespace differences.
- On Tomcat 10.1, verify HTTP connectors, TLS, sessions, JSPs, and classpath/Servlet filters.

Boot 3 example import:

```java
import jakarta.servlet.http.HttpServletRequest;
```

If you still see `javax.servlet.http.HttpServletRequest`, migration is incomplete. Still, **do not blindly replace every `javax.*` package with `jakarta.*`**: only Jakarta EE APIs migrated; `javax.crypto`, `javax.net`, and `javax.xml` belong to the JDK and remain `javax.*`.

### 10.3. Servlet Containers When Migrating Boot 3.5 to 4

Spring Boot 4 builds on Jakarta EE 11 / Servlet 6.1 and Spring Framework 7. Tomcat 11 and Jetty 12.1 are the embedded servlet options cited in docs; Undertow support was dropped in the 4.0 migration guide.

If deploying a WAR to an external server, verify **Servlet 6.1+**, not merely "Tomcat is running." Tomcat 10.1 (Servlet 6.0) **does not meet** Boot 4's Servlet 6.1 baseline. Never lower target API versions to bypass the support matrix unless explicitly supported by your vendor.

### 10.4. Reactor Netty and Spring WebFlux

Reactive WebFlux apps normally run Reactor Netty, sitting outside the Servlet container table in the MVC sense. Audit Reactor Netty/Netty releases, TLS, HTTP/2, event-loop threads, `WebClient` behavior, and reactive security separately. Do not assume Tomcat 11 compatibility implies WebFlux apps are verified.

### 10.5. `spring-boot-starter-web` and Boot 4

Per the Boot 4 migration guide, `spring-boot-starter-web` is deprecated in favor of `spring-boot-starter-webmvc` under the modular starter convention. Boot 4 also changes auto-configuration package layouts and test APIs. Builds need import/dependency reviews, not just bumping `<version>`.

**The lab in section 11 is intentionally anchored to Boot 3.5.16.** If targeting Boot 4, migrate starters, API packages, and test configs per the migration guide before expecting that code to compile.

## 11. Complete Lab: Locking Down HTTP Behavior Before Upgrading Boot 3.5

Build a small service with:

- `GET /api/items/{sku}` returning JSON and a contract-identifying header.
- `POST /api/quotes` validating JSON and computing totals.
- `GET /api/contract` returning **non-sensitive** metadata distinguishing sample version/config.
- `@RestControllerAdvice` returning explicit error codes.
- `application.properties` containing clearly documented illustrative settings.
- JUnit service tests, `MockMvc` slice tests, and `@SpringBootTest(RANDOM_PORT)` live HTTP tests.

The goal is **locking down behavior** before attempting an upgrade—not optimizing a Spring Boot 3.5 production template.

### 11.1. Directory Layout

```text
boot-upgrade-audit/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/upgrade/
    │   │   ├── UpgradeAuditApplication.java
    │   │   ├── CatalogService.java
    │   │   ├── CatalogController.java
    │   │   └── ApiErrors.java
    │   └── resources/application.properties
    └── test/java/com/example/upgrade/
        ├── CatalogServiceTest.java
        ├── CatalogMvcTest.java
        └── UpgradeBehaviorHttpTest.java
```

No database required. Public classes match filenames under the same root package.

### 11.2. `pom.xml` Running Spring Boot 3.5.16

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>boot-upgrade-audit</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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

**Do not add `spring-boot-properties-migrator` permanently to the baseline POM**. Use it **strictly temporarily during migration**, removing it once all keys are updated. Spring Boot 4 changes starter and test packages, so do not bump the version directly assuming Boot 4 compatibility.

### 11.3. `UpgradeAuditApplication.java`

```java
package com.example.upgrade;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UpgradeAuditApplication {

    public static void main(String[] args) {
        SpringApplication.run(UpgradeAuditApplication.class, args);
    }
}
```

### 11.4. `CatalogService.java`

```java
package com.example.upgrade;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    public record Item(String sku, long unitPriceVnd) {
    }

    public record Quote(
            String sku,
            int quantity,
            long unitPriceVnd,
            long totalVnd) {
    }

    public Item item(String sku) {
        return switch (sku) {
            case "pen" -> new Item("pen", 12_000);
            case "book" -> new Item("book", 35_000);
            default -> throw new UnknownItemException(sku);
        };
    }

    public Quote quote(String sku, int quantity) {
        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException(
                    "quantity must be 1..100");
        }
        Item found = item(sku);
        return new Quote(
                found.sku(),
                quantity,
                found.unitPriceVnd(),
                Math.multiplyExact(
                        found.unitPriceVnd(), (long) quantity));
    }
}

class UnknownItemException extends RuntimeException {
    UnknownItemException(String sku) {
        super("Unknown SKU: " + sku);
    }
}
```

Business rules have no HTTP stack dependencies, so unit tests remain valid across server/Boot changes. `Math.multiplyExact` guards against silent overflow.

### 11.5. `CatalogController.java`

```java
package com.example.upgrade;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record QuoteRequest(
        @NotBlank String sku,
        @Min(1) @Max(100) int quantity) {
}

@RestController
@RequestMapping("/api")
public class CatalogController {

    private final CatalogService catalog;

    public CatalogController(CatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
            value = "/items/{sku}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CatalogService.Item> item(
            @PathVariable String sku) {
        return ResponseEntity.ok()
                .header("X-Api-Contract", "catalog-v1")
                .body(catalog.item(sku));
    }

    @PostMapping(
            value = "/quotes",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public CatalogService.Quote quote(
            @Valid @RequestBody QuoteRequest request) {
        return catalog.quote(
                request.sku(), request.quantity());
    }

    @GetMapping(
            value = "/contract",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> contract() {
        return Map.of(
                "api", "catalog-v1",
                "routing", "explicit");
    }
}
```

`@Valid` requires the Jakarta validation starter; the request DTO uses a Java 17 record. `X-Api-Contract` is a **demo** header, not generated by Spring Boot. Asserting it catches fallback routes returning unexpected HTML or default pages.

### 11.6. `ApiErrors.java`

```java
package com.example.upgrade;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrors {

    @ExceptionHandler(UnknownItemException.class)
    public ResponseEntity<Map<String, String>> missing(
            UnknownItemException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(
                Map.of("code", "ITEM_NOT_FOUND"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalid(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.badRequest().body(
                Map.of("code", "INVALID_REQUEST"));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> unreadable(
            HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest().body(
                Map.of("code", "INVALID_JSON"));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badArgument(
            IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body(
                Map.of("code", "INVALID_REQUEST"));
    }
}
```

Testing the error contract guards against changes when the framework updates default error responses or exception mappings. This handler deliberately omits raw exception messages and stack traces from client responses.

### 11.7. `application.properties`

```properties
spring.application.name=boot-upgrade-audit

server.port=8080
server.max-http-request-header-size=16KB
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=15s

management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
```

`server.max-http-request-header-size` is the Boot 3 key, **not** legacy `server.max-http-header-size`. `server.shutdown=graceful` and the shutdown phase timeout make intent explicit, though real connection draining still needs testing. The numbers `16KB`/`15s` are **lab choices**, not universal production defaults.

Actuator exposes only `health` and `info`. When adding Redis, JPA, or Security in real projects, audit health contributors and endpoint security separately.

## 12. Unit and MVC Tests: Locking Down the Business/API Contract

### 12.1. `CatalogServiceTest.java`

```java
package com.example.upgrade;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CatalogServiceTest {

    private final CatalogService catalog =
            new CatalogService();

    @Test
    void computesPriceExactly() {
        assertEquals(
                new CatalogService.Quote(
                        "pen", 2, 12000, 24000),
                catalog.quote("pen", 2));
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> catalog.quote("pen", 0));
    }

    @Test
    void rejectsUnknownSku() {
        assertThrows(UnknownItemException.class,
                () -> catalog.item("unknown"));
    }
}
```

Unit tests involve no network or Spring context. They cannot detect path matching or Servlet container incompatibilities, yet establish a business-logic baseline.

### 12.2. `CatalogMvcTest.java`

```java
package com.example.upgrade;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CatalogController.class)
class CatalogMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    CatalogService catalog;

    @Test
    void itemContractIncludesHeaderAndBody()
            throws Exception {
        given(catalog.item("pen"))
                .willReturn(new CatalogService.Item("pen", 12000));

        mvc.perform(get("/api/items/pen")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Api-Contract", "catalog-v1"))
                .andExpect(jsonPath("$.sku")
                        .value("pen"))
                .andExpect(jsonPath("$.unitPriceVnd")
                        .value(12000));
    }

    @Test
    void trailingSlashDoesNotMatchByDefault()
            throws Exception {
        mvc.perform(get("/api/items/pen/"))
                .andExpect(status().isNotFound());
    }

    @Test
    void quantityZeroIsRejectedByMvcValidation()
            throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"pen","quantity":0}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));
    }

    @Test
    void wrongMethodReturns405() throws Exception {
        mvc.perform(post("/api/items/pen"))
                .andExpect(status().isMethodNotAllowed());
    }
}
```

In Boot 3.5 / Spring Framework 6.2, `@MockitoBean` lives in `org.springframework.test.context.bean.override.mockito`. Slice tests verify MVC routes, validation, and converters without starting an embedded server, which is why live HTTP tests are also needed. `CatalogService` is mocked so the slice stays focused on the web contract.

Note: `status().isNotFound()` asserts the **Boot 3.5 MVC default trailing-slash behavior in this lab**. If your app defines custom URL matching, proxy rewrites, or explicit routes, assert your agreed contract rather than blindly expecting 404.

## 13. Live HTTP Tests: Catching Real Embedded Server Bugs

File `UpgradeBehaviorHttpTest.java`:

```java
package com.example.upgrade;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.RANDOM_PORT)
class UpgradeBehaviorHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    private String url(String path) {
        return "http://127.0.0.1:" + port + path;
    }

    @Test
    void actualServerStartsAndReturnsContract() {
        assertTrue(port > 0);

        ResponseEntity<Map> response = http.getForEntity(
                url("/api/items/pen"), Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("pen", response.getBody().get("sku"));
        assertEquals(12000,
                ((Number) response.getBody()
                        .get("unitPriceVnd")).intValue());
        assertEquals("catalog-v1",
                response.getHeaders()
                        .getFirst("X-Api-Contract"));
    }

    @Test
    void actualServerRejectsTrailingSlash() {
        ResponseEntity<String> response =
                http.getForEntity(
                        url("/api/items/pen/"), String.class);

        assertEquals(
                HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void actualServerValidatesJson() {
        ResponseEntity<Map> response =
                http.postForEntity(
                        url("/api/quotes"),
                        new QuoteRequest("pen", 0),
                        Map.class);

        assertEquals(
                HttpStatus.BAD_REQUEST,
                response.getStatusCode());
        assertEquals("INVALID_REQUEST",
                response.getBody().get("code"));
    }

    @Test
    void healthEndpointIsReachable() {
        ResponseEntity<Map> response = http.getForEntity(
                url("/actuator/health"), Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("UP",
                response.getBody().get("status"));
    }
}
```

These tests use **real Tomcat on a random loopback port**, avoiding `server.port=8080` and CI port collisions. They verify server initialization, real HTTP statuses/headers, and container routing beyond `MockMvc`. Still, they **do not** exercise external reverse proxies, Kubernetes ingress, TLS, or standalone Tomcat WAR deployments.

### Important When Targeting Boot 4

The Boot 4 migration guide notes that test packages/auto-configurations changed and `@SpringBootTest` no longer provides `TestRestTemplate` automatically as in Boot 3.5. You need explicit `@AutoConfigureTestRestTemplate`, required dependencies, updated imports, or migration to `RestTestClient` per Boot 4 guidance. **Never claim the Boot 3.5 Java test code above compiles untouched on Boot 4.** The lab's purpose is establishing a solid baseline for observable migration.

## 14. Running the Lab, Observing Outputs, and Checking Renamed Keys

### 14.1. Prerequisites

Java 17+, Maven, source files in the expected paths.

```bash
java -version
mvn -version
mvn clean test
mvn clean package
java -jar target/boot-upgrade-audit-1.0.0.jar
```

Maven may need network access on first build to download dependencies. Printed test counts depend on Surefire version; do not assume identical stdout across environments.

### 14.2. HTTP Smoke Checks

In another terminal:

```bash
curl -i http://127.0.0.1:8080/api/items/pen
curl -i http://127.0.0.1:8080/api/items/pen/
curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":2}'
curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":0}'
curl -i http://127.0.0.1:8080/actuator/health
```

Expected **with the Boot 3.5.16 demo source and config**:

| Request | Status | What to verify |
| --- | --- | --- |
| `GET /api/items/pen` | 200 | Header `X-Api-Contract: catalog-v1`, JSON `sku=pen`, `unitPriceVnd=12000` |
| `GET /api/items/pen/` | 404 | Trailing slash rejected by default |
| `POST /api/quotes`, quantity 2 | 200 | JSON includes `totalVnd` 24000 |
| `POST /api/quotes`, quantity 0 | 400 | JSON `code=INVALID_REQUEST` |
| `GET /actuator/health` | 200 when healthy | JSON `status=UP` |

JSON body of successful POST:

```json
{"sku":"pen","quantity":2,"unitPriceVnd":12000,"totalVnd":24000}
```

JSON property ordering is not a contract to assert. Example values are **expected from the source code**, not measured benchmark or execution captures.

### 14.3. Negative Checks and Server Limits

The command below demonstrates an **invalid request test** to run only in test environments:

```bash
curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: text/plain" \
  --data 'sku=pen&quantity=2'
```

Because the controller requires JSON, expect HTTP **415 Unsupported Media Type**, unless a filter/proxy/security layer intercepts earlier. Results can shift when security or container layers change, which is precisely why recording a baseline matters.

Request header limits (16KB in the lab) should be tested with bounded, safe automated tests; never send giant overload payloads at production hosts. Exact statuses and limits vary across Servlet containers and proxies.

## 15. Monitoring Configuration and Auto-Configuration After Upgrades

### 15.1. `ConditionEvaluationReport`

When a starter moves or is removed, a bean may stop being auto-configured. Use `--debug` or `ConditionEvaluationReport` in tests or startup diagnostics to see which auto-configurations matched or failed to match instead of guessing from dependency lists.

Local run example:

```bash
java -jar target/boot-upgrade-audit-1.0.0.jar --debug
```

Boot prints the condition evaluation report. Logs can be verbose and list class/dependency names; strip secrets/PII before sharing. Never leave `--debug` enabled indefinitely in production to avoid log volume bloat.

### 15.2. Actuator `configprops` and `env`

`configprops` and `env` reveal bound configuration, yet are sensitive. To inspect:
- Expose only in dedicated admin environments with auth and network restrictions.
- Check sanitized sources/properties.
- Turn off extra exposure once done.
- Never paste raw responses holding identifiers or credentials into public issue trackers.

The demo's `management.endpoints.web.exposure.include=health,info` deliberately omits `env` and `configprops` for safety.

### 15.3. Scanning Configs with Search

You can search for legacy keys in a real repo using `git grep`:

```bash
git grep -n "server.max-http-header-size"
git grep -n "spring.redis."
git grep -n "spring.data.cassandra."
git grep -n "management.endpoint.httptrace"
git grep -n "javax.servlet"
```

`git grep` scans only tracked repo files, missing **external** ConfigMaps, Helm variable values, CI secrets, runtime environments, and binary libraries. If source code contains strings inside docs/comments/tests, review context rather than running blind replace-all.

Never run grep across production filesystems containing secrets and paste full outputs into public chats. Keep only safe match names.

## 16. Comparing Before and After with a Migration Matrix

A migration matrix should record **source expected behavior** and **target observed behavior**:

| Check | Source baseline | Target candidate | Verdict |
| --- | --- | --- | --- |
| Java/version/build | Record JDK, Boot, plugin versions | Record new JDK, Boot BOM | Compatible? |
| Servlet engine | Tomcat/Jetty/Undertow version | Exact embedded/external version | Supported? |
| `GET /api/items/pen` | Status + body/header | Status + body/header | Same contract? |
| Trailing slash | 200 or 404 per source | 200/404 per target | Intentional? |
| Invalid JSON | 400 + error schema | 400 + error schema | Same? |
| HTTP header limits | Old effective threshold | New effective threshold | Policy upheld? |
| Session cookie | `Path`/`Domain`/`SameSite`/`Secure` | Current flags | Safe? |
| Login/CSRF/CORS | 401/403/preflight | Current status/headers | Safe? |
| Actuator exposure | Endpoints/roles | Endpoints/roles | Not wider? |
| Graceful shutdown | Timing/active requests | Timing/active requests | Meets SLO? |
| Metrics/traces | Names/tags | Names/tags | Alerts working? |
| Startup/resources | Heap/threads/pools | Same load profile | No regression? |

"Target version number is higher" is **not sufficient to mark PASS**. A behavior change may be desirable (such as rejecting trailing slashes for canonical URLs), yet must be explicitly approved and reflected in tests, docs, and clients.

### Minimum Evidence for a PASS Row

- Test name/command, environment, version, timestamp.
- Request and expected status/contract.
- Sanitized observed status/body/headers.
- Owner/approver for any breaking change.
- Rollback criteria if the change proves unacceptable.

When multiple profiles, tenants, or regions exist, build matrices for representative configs—not just a dev laptop.

## 17. Mandatory Security Review

Upgrading frameworks can shift security posture through matcher semantics, dependencies, default filter ordering, cookie flags, Actuator exposure, and server connector settings.

### Key Checklist

- **Authentication/authorization:** anonymous vs. authenticated, role-based access, method/path matchers, resource servers.
- **CSRF:** browser sessions/cookies, unsafe methods, token lifecycles.
- **CORS:** `OPTIONS` preflight, `Access-Control-Allow-Origin`, credentials, headers.
- **Cookies:** `Secure`/`HttpOnly`/`SameSite`, `Domain`/`Path`, session persistence/redeploys.
- **HTTPS:** TLS versions/certificates/proxy forwarded headers/redirect locations.
- **Actuator:** `health`, `info`, and any other exposed endpoints have explicit policy; never accidentally expose `env`, `heapdump`, `mappings`, `loggers`, or `shutdown`.
- **Error pages:** never expose stack traces or internal class names due to changed defaults.
- **Uploads/static content:** resource path matching, content-type sniffing, cache controls.
- **Dependencies:** CVEs, transitive libraries, and third-party starters.

Never turn a security 403 into 200 by adding `permitAll("/**")` during migration. Verify security matches policy rather than relaxing rules to pass tests.

## 18. Performance and Operations: Upgrading Code Does Not Guarantee Identical Capacity

Changing Spring Framework, Tomcat, Jetty, or the JDK can alter latency, thread scheduling, buffer allocation, TLS, GC, and metric instrumentation. Hold the traffic profile and dataset constant to compare:

- Achieved RPS, per-operation p95/p99, error rates, and timeout rates.
- Tomcat active/busy threads, servlet request queues, HTTP connections.
- Hikari active/pending/timeouts (if the app uses a DB).
- JVM heap/GC pauses, CPU throttling, RSS, native buffers.
- PostgreSQL query latency, locks, and connections.
- Actuator metrics/tracing names/tags and alerts.
- Startup time, readiness, graceful shutdown, and autoscaler behavior.

Run smoke tests first, followed by baseline load/soak tests in authorized environments. **Never use 10 local requests to claim production throughput is unaffected.**

### Notable Areas to Measure After a Major Upgrade

- Jackson/codec response size and serialization cost.
- Tomcat 10.1 → 11 servlet engine changes.
- Undertow → Tomcat/Jetty when moving Boot 3 to 4.
- JDK upgrades and GC configuration.
- Security filters and observability middleware overhead.
- Thread/connection limits and HTTP/2/TLS settings.
- Scheduler/async completion and graceful shutdown phase order.
- Aggregate DB pool size if replica or thread counts changed.

## 19. Phased Upgrade Workflow and Rollback

### Phase A — Baseline and Plan

1. Lock down source version, target line, JDK, and server/container matrix.
2. Read official migration guides and release notes along the **full path**.
3. Inventory legacy properties, deprecated APIs, removed starters, and library overrides.
4. Freeze artifacts, test data, HTTP contracts, and SLOs.
5. Classify breaking changes by user impact, operations, security, and data.

### Phase B — Build and Code Migration

1. Update Boot parent/BOM and build plugins.
2. Update Java toolchain; migrate `javax` → `jakarta` within the needed scope when moving 2→3.
3. Update property keys across all config sources, adding the migrator **temporarily** if helpful.
4. Replace removed/deprecated APIs and starter/package moves.
5. Choose compatible Tomcat/Jetty/Netty and external WAR containers if applicable.
6. Rebuild, run unit/MVC/integration tests, and resolve transitive conflicts.

### Phase C — Runtime Verification

1. Boot with profiles/configs matching target production.
2. Check effective properties and condition evaluations for missing beans.
3. Run live HTTP smoke/contract tests (positive + negative).
4. Verify Actuator exposure, security, TLS/proxies, cookies, and context paths.
5. Run representative load/soak tests and compare metrics.
6. Remove the properties migrator, rebuild, and run final tests.

### Phase D — Controlled Rollout

- Use canary/blue-green/rolling strategies as appropriate; keep rollback viable where schema/data allow.
- Monitor 4xx/5xx, p95/p99, readiness, restart counts, CPU, heap/GC, pools, logs, and traces.
- Define explicit **rollback triggers**: business error spikes, auth failures, SLO misses, startup failures, queue growth.
- If a database migration is **irreversible**, rolling back only the app binary is insufficient; use expand/contract schema strategies and backup plans.
- Never swap versions across the entire fleet simultaneously without observation.
- Post-deploy, verify through the public entrypoint (Ingress/TLS) as well as internal app health.

### Runbook Template

```text
Baseline:  Boot/source artifact, JDK, server, config snapshot
Candidate: Boot/target artifact, JDK, server, dependency tree
Feature flags/profiles and property migration diff:
Functional pass/fail: routes, status, JSON, invalid cases
Security pass/fail: auth, CORS, CSRF, cookies, Actuator
Runtime pass/fail: live HTTP, readiness, graceful shutdown
Performance pass/fail: p95/p99/errors/throughput
Canary percentage and monitoring window:
Rollback artifact/trigger/owner:
Open risks and approved behavior changes:
```

The template above contains no actual test results. Populate every field with verified evidence from the specific system.

## 20. Common Issues and How to Distinguish Them

| Symptom | Suspected cause | Resolution |
| --- | --- | --- |
| `GET /api/foo/` changed 200 → 404 | Trailing-slash default changed | Test both URLs; decide canonical contract |
| App boots yet header limit is wrong | Legacy `server.max-http-header-size` key | Switch to `server.max-http-request-header-size` |
| Redis config stopped taking effect | Legacy `spring.redis` prefix | Check `spring.data.redis` and real connection |
| Cassandra binding broken | Prefix changed 2→3 | Check `spring.cassandra` |
| Actuator `/httptrace` 404 | Endpoint renamed | Review `/httpexchanges` and repository/API |
| JMX endpoint missing | JMX exposure default changed | Set exposure explicitly and verify security |
| `javax.servlet` `ClassNotFound` | Incomplete Boot 3/Jakarta migration | Update imports/dependencies/container |
| Boot 3 WAR fails on Tomcat 9 | Incompatible Servlet API | Use a Jakarta-compatible container |
| Boot 4 WAR fails on Tomcat 10.1 | Servlet 6.1 baseline | Use Tomcat 11 / Servlet 6.1+ compatible server |
| Boot 4 Undertow dependency fails | Server support removed | Switch to supported Tomcat or Jetty |
| Boot 4 test `TestRestTemplate` fails to inject | Test auto-config/packages changed | Read Boot 4 migration guide and update imports/deps |
| Boot 4 `starter-web` deprecation | Modular starter changes | Switch to `starter-webmvc` per guide |
| App startup fails with missing bean | Auto-configuration/starter moved | Inspect classpath + condition report |
| JSON body changed while unit tests pass | Missing HTTP contract tests | Add `MockMvc`/live HTTP response assertions |
| 401/403 spikes after upgrade | Security matchers/filters/CSRF | Policy regression tests; never `permitAll` |
| Prometheus alerts silent | Metric names/tags changed | Compare scrape outputs and dashboard rules |
| Health 200 on Tomcat root yet WAR 404 | Wrong context / deploy failed | Check per-WAR `/catalog/actuator/health` |
| Connection pool exhausted post-upgrade | Thread/pool/resource profile shifted | Monitor Hikari/Tomcat/DB metrics |
| Properties migrator warnings gone yet behavior wrong | External config or unbound key | Check effective config and runtime tests |
| Jumping 2.7 straight to 4 causes too many errors | Skipped 3.x migrations | Step through latest 2.7/3.5 and major guides |
| App runs locally yet ingress returns 502 | Container readiness, port, or proxy mismatch | Run staging/proxy smoke checks per deployment |
| Rollback fails | Schema/data migration not backward-compatible | Use expand-contract schema strategy |

## 21. Hands-On Exercises

### A. Reproduce Trailing-Slash Difference

Using the demo project, run `GET /api/items/pen` and `GET /api/items/pen/`. Verify 200 and 404 on Boot 3.5. If both must return 200, add an explicit mapping or intentional redirect and update tests.

### B. Legacy Key Test

Change `server.max-http-request-header-size` to `server.max-http-header-size` on Boot 3.5. Add `spring-boot-properties-migrator` temporarily and observe warning diagnostics; restore the new key, remove the migrator, and verify startup. Never treat Tomcat booting cleanly as proof header limits are enforced.

### C. Migrating Redis Prefixes

A Boot 2.x app uses `spring.redis.host`. Prepare a migration diff to `spring.data.redis.host` in Boot 3. Check application YAML, profiles, environment variables (`SPRING_DATA_REDIS_HOST`), and Helm templates. Never paste real Redis credentials into logs.

### D. Server Matrix

Build a table comparing Boot 2.7/Tomcat 9, Boot 3.5/Tomcat 10.1, and Boot 4/Tomcat 11 by Java/Jakarta Servlet level. Identify which allow direct WAR deployment vs. rebuilding and migrating package imports.

### E. Auditing Boot 4 Undertow

If using `spring-boot-starter-undertow` in Boot 3.5, read the 4.0 migration guide and design a switch to Tomcat or Jetty. Compare HTTP/2, compression, websocket/session configs, and p95 before and after.

### F. Actuator Endpoint Migration

If monitoring clients call `/actuator/httptrace` on an older line, design a verification plan for `/actuator/httpexchanges` on the target supported API while ensuring sensitive endpoints stay non-public.

### G. `@SpringBootTest(RANDOM_PORT)` and Proxies

Local tests pass, then staging behind a `/shop` gateway fails; verify the API contract via the public path, TLS, cookies, and forwarded headers. Explain what embedded server tests miss compared to deployed E2E tests.

### H. Security Defaults

Create a test matrix: public GET, authenticated POST, CSRF-invalid POST, private GET Actuator. Verify post-upgrade statuses never relax authorization. If 403s change, inspect matchers/policies instead of disabling filters.

### I. Never Leave the Migrator as a Permanent Dependency

Once all keys are updated, remove `spring-boot-properties-migrator`, rebuild, and re-run the same suite. If tests only pass with the migrator attached, migration is incomplete.

### J. Rollback Plan

Simulate a canary showing rising 5xx after 10 minutes while database schema changes already ran. Draft a rollback plan covering expand-contract migrations/snapshots, binary versions, traffic draining, and decision owners. Never promise `kubectl rollout undo` alone suffices when schemas are incompatible.

## 22. Pre-Merge / Pre-Deploy Upgrade Checklist

### Baseline and Documentation

- [ ] Source/target Boot versions and official migration path documented.
- [ ] Read every migration guide/release note along the path; never mix Boot 3 and 4 docs.
- [ ] Audited Spring Framework, Security, Data, Cloud, Micrometer, and third-party integrations.
- [ ] Recorded Java, Maven/Gradle, Docker/image/JDK, and external WAR requirements.
- [ ] Captured artifact checksums, dependency reports, and sanitized config snapshots.

### Properties and Behavior

- [ ] Scanned renamed/removed properties across repo, CI/CD, deployment manifests, and runtime configs.
- [ ] Used `spring-boot-properties-migrator` **temporarily** where helpful, then removed it.
- [ ] Confirmed effective values, profiles, and precedence—not just repo key grepping.
- [ ] Explicitly tested HTTP routing, trailing slashes, and context paths.
- [ ] Verified HTTP header request/response limits, encoding, compression, and upload handling.
- [ ] Tested JSON serialization, error schemas, and 400/404/405/415 responses.
- [ ] Verified Actuator exposure/health/metrics/traces and dashboards remain accurate.
- [ ] Verified session cookies, CORS, CSRF, redirects, and security matchers never relax permissions.
- [ ] Tested graceful shutdown and background resource cleanup.

### Runtime/Server and Rollout

- [ ] Verified Java/Jakarta Servlet level fits target and checked Tomcat/Jetty/Undertow/Netty support.
- [ ] Deployed external WARs (if applicable) to the **exact target container/version**; embedded tests do not replace external smoke tests.
- [ ] Eliminated incompatible `javax.servlet.*`/libraries on Boot 3/4.
- [ ] Handled Boot 4 modular starters and test API changes when targeting Boot 4.
- [ ] Unit, `MockMvc`, `RANDOM_PORT`, and deployed HTTP tests pass under proper profiles.
- [ ] Compared load/performance/error budgets under identical workloads.
- [ ] Defined canary/blue-green/rollback thresholds and schema migration strategy.
- [ ] Health/readiness checks target the right app/context; full observability active post-deploy.
- [ ] Confirmed neither debug/diagnostic Actuator exposures nor the migrator remain in the final artifact.

## 23. Official Reference Documentation

- [Spring Boot 3.5 — Upgrading](https://docs.spring.io/spring-boot/3.5/upgrading.html): migration guides, `spring-boot-properties-migrator`, and guidance.
- [Spring Boot 3.5.16 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): JDK/Framework/Tomcat/Jetty/Undertow/Servlet versions.
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): Jakarta, `server.max-http-request-header-size`, Redis/Cassandra, trailing slash, Actuator.
- [Spring Boot 3.5 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes): 3.5 feature/default changes such as Tomcat APR defaults.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): Servlet 6.1, Tomcat 11/Jetty 12.1, Undertow removed, modular starters, Spring Session property prefixes, and test API migrations.
- [Spring Boot 4.1 — System Requirements](https://docs.spring.io/spring-boot/4.1/system-requirements.html): reference for 4.1 versions and target Servlet/JDK compatibility.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): config sources and property precedence.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): exposure and security.
- [Spring Boot 3.5 — MVC Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Servlet runtime, request handling, and MVC.
- [Spring Framework — MVC Testing With MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): mock vs. actual HTTP tests.
- [Apache Tomcat 10.1 Documentation](https://tomcat.apache.org/tomcat-10.1-doc/): Servlet 6.0 container.
- [Apache Tomcat 11 Documentation](https://tomcat.apache.org/tomcat-11.0-doc/): Servlet 6.1 container.

**Conclusion:** A trustworthy Spring Boot upgrade verifies **three separate pillars**: default behaviors still honor HTTP/security contracts; renamed/removed properties are updated across every config source and actually bind; and Java/Spring/Jakarta/Servlet containers are supported on the target line. A green build or successful `SpringApplication` startup is never enough: back it with unit, MVC, live HTTP, external container/proxy tests, metrics, and evidence-backed rollout/rollback.
