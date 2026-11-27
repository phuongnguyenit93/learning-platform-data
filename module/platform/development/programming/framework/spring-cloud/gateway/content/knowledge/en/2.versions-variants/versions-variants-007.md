# Distinguishing Stable, Preview, and Snapshot Documentation in Spring Cloud Gateway

A Spring Cloud Gateway documentation page may describe a **stable (GA)** release, a **preview** release, or a **snapshot** build. These three labels indicate maturity and how likely the content is to change. Picking the wrong documentation branch can leave an application with non-working route configuration, wrong predicate/filter names, misconfigured Spring Security integration, or an unreleased behavior shipped to production.

This lesson belongs to the **Versions and Variants** topic, focusing on reading the right documentation when building an API Gateway for microservices. Examples directly relate to route predicates, filter chains, path/header rewriting, service discovery, authentication, rate limiting, circuit breakers, retries, TLS, and request observability.

## 1. Why Identify the Documentation Type?

Suppose a team operates a stable Gateway with a route to an order service, a token-relay filter, and rate limiting. When searching how to configure a new filter, the team opens the "latest" page and copies an example. The project compiles, yet the route returns 404 or a configuration property is ignored. The cause may be that the page describes a different development branch from the library actually running.

There are **three things to distinguish**:

1. **Running library version**: the actual Spring Cloud Gateway artifact resolved by Maven/Gradle and packaged into the application.
2. **Documentation branch being read**: stable, preview, or snapshot; this can differ significantly from the actual library.
3. **Gateway variant**: such as Gateway Server WebFlux vs. Gateway Server MVC. Both variants have different configuration keys, request processing mechanics, and integration capabilities; a "stable" badge does not make an example for one variant automatically usable on the other.

Therefore, a page labeled "stable" can still be **unsuitable** if it belongs to a newer Gateway line or a different variant than your project uses.

## 2. What Do Stable, Preview, and Snapshot Mean?

| Criterion | Stable / GA | Preview (milestone, RC, preview docs) | Snapshot |
|---|---|---|---|
| Meaning | Officially released version (General Availability) | Pre-GA release for evaluation and verification | Development build, typically from an unreleased code branch |
| Typical notation | X.Y.Z, e.g., 4.2.2 | X.Y.Z-M1, X.Y.Z-RC1, or preview label | X.Y.Z-SNAPSHOT |
| API/config stability | Backed by release commitments; changes are documented per release | May still be adjusted before GA | Can change per commit, build, or timestamp |
| Reproducibility | Dependencies can be pinned to an exact released version | Can be pinned to an exact published M/RC milestone | The same SNAPSHOT coordinate can pull different builds over time |
| Typical artifact source | Release repositories such as Maven Central | Milestone/release-candidate repositories, depending on project publishing | Development snapshot repositories |
| Documentation purpose | Developing, upgrading, and operating the matching version | Evaluating upcoming changes, testing upgrades | Tracking work-in-progress features, experimenting, or contributing |
| Production suitability | Suitable after checking compatibility and support lifecycle | Usually not chosen without an explicit risk-acceptance policy | Should not be used as a standard production baseline |

**Stable does not mean "every stable release is still supported."** An older GA version may have reached end of maintenance or security support. Always check the support policy and release notes for that exact version line.

**Preview is not a single version suffix.** A documentation page may use the word "preview" for a pre-release documentation branch; the underlying artifact might be a milestone (M), a release candidate (RC), or an experimental feature inside a GA release. Read **the exact version and status stated on the page**. An RC is a fixed release milestone, not a SNAPSHOT merely because it is not GA yet.

**SNAPSHOT is a mutable development coordinate.** In the Maven ecosystem, snapshot builds may be stored with timestamped filenames, yet when requesting `X.Y.Z-SNAPSHOT`, the build tool can fetch a newer build based on metadata/cache rules. Snapshot docs and snapshot artifacts are also not guaranteed to come from the exact same commit.

> Version numbers in this lesson are solely for illustrating how to recognize labels; they do not assert those are the current stable/preview versions at the time of reading.

## 3. Reading "Version" Accurately in the Spring Ecosystem

A Spring Cloud Gateway application is shaped by multiple release layers:

| Layer | What to identify? | Why does it matter? |
|---|---|---|
| Java and Spring Boot | JDK and Spring Boot versions | Runtime requirements, baseline dependencies, and framework changes |
| Spring Cloud release train | `spring-cloud-dependencies` BOM version | Manages the compatible version set across Spring Cloud projects |
| Spring Cloud Gateway | Actual Gateway artifact version | Determines available APIs, filters, predicates, and configuration |
| Gateway variant | Server WebFlux vs. Server MVC | Determines execution model and matching configuration location |
| Documentation branch | Stable/preview/snapshot and displayed version number | Determines whether the guide was written for the runtime above |

Spring Cloud uses a **release train** to coordinate many related libraries. Consequently, the Spring Cloud BOM version **does not have to match** the Spring Cloud Gateway artifact version. Never deduce "Gateway version X" solely by looking at the release train name; inspect the dependency tree or actual dependency resolution.

Similarly, two pages both marked "stable"—one for **Gateway Server WebFlux** and the other for **Gateway Server MVC**—can still differ in starters, packages, request-processing characteristics, and route declarations. Confirm the variant before copying configuration.

## 4. Workflow for Choosing the Right Documentation

~~~mermaid
flowchart TD
    A["Check actual Gateway version and variant"] --> B["Cross-check Spring Boot and Spring Cloud BOM"]
    B --> C{"What kind of artifact is in use?"}
    C -->|"GA / release"| D["Open stable docs for the exact version line"]
    C -->|"Milestone / RC"| E["Open preview docs for the same release milestone"]
    C -->|"SNAPSHOT"| F["Open snapshot docs and verify commit/build"]
    D --> G["Check release notes, support, and configuration"]
    E --> G
    F --> G
    G --> H["Test routes, filters, and integrations in a test environment"]
~~~

### Step 1 — Determine Versions from the Project, Not the Browser

Inspect the build file to see which Spring Boot, Spring Cloud BOM, and Gateway starter the project declares. Then inspect **resolved dependencies**, because dependency management or transitive dependencies can make the running version differ from initial assumptions.

Example inspection commands (use the build tool your project uses):

~~~bash
# Maven Wrapper: list resolved Spring Cloud dependencies
./mvnw dependency:tree -Dincludes=org.springframework.cloud:*

# Gradle Wrapper: inspect why a Gateway dependency was selected
./gradlew dependencyInsight --dependency spring-cloud-gateway --configuration runtimeClasspath
~~~

If the project has multiple profiles or modules, run the command in the module that actually packages the Gateway. With Gradle, adjust the dependency name and configuration to match the active starter/variant; with Maven, also inspect the effective POM if BOM inheritance is complex.

**Record at minimum**: Spring Boot, Spring Cloud BOM, resolved Gateway artifact and version, WebFlux/MVC, and JDK. This is the technical identity needed to locate the right documentation page.

### Step 2 — Inspect the Version Selector and Page URL

On official documentation sites, look at the version selector, branch banner, and URL. A link saying "latest", "current", "preview", or "snapshot" **is not enough to conclude** it matches your application's version. Aliases like "current" can change targets after a release.

Check all of these together:

- **Which version number** is the page displaying, and is it GA, M/RC, or snapshot?
- Is this documentation for **Gateway Server WebFlux** or **Server MVC**?
- Does the page state "applies to", "since", "deprecated", "removed", or version-specific support conditions?
- Are the **starter name, configuration namespace, and predicates/filters** used in examples present in the version your project resolves?
- For snapshot pages: is there enough branch, commit, doc build date, or trace info to match your test artifact?

Save a version-pinned URL or revision whenever possible. A bookmark pointing to the "latest" alias is not reproducible evidence for a past deployment.

### Step 3 — Cross-Check Release Notes and Compatibility Tables

Cross-check release notes for **Gateway**, the **Spring Cloud** release train, and the **Spring Boot ↔ Spring Cloud** compatibility matrix at deployment time. Pay attention to Java version requirements, configuration property changes, deprecations, security upgrades, and filter behavior changes. Do not assume bumping a standalone Gateway artifact is sufficient.

Documentation is a guide; **artifacts, release notes, and support status** determine whether that guide applies to your running system.

### Step 4 — Run Smoke Tests Close to Production Behavior

For a gateway, verify at minimum the flows the project actually uses: do route predicates match properly, do filters run in the expected order, are paths/headers transformed accurately across the gateway, and do authentication and authorization reject invalid requests? If used, add checks for service discovery, rate limiting (429), circuit breaker/fallback, retries, TLS, and tracing/metrics/logging.

A documentation example compiling cleanly still **does not prove** the filter chain behaves properly at runtime.

## 5. Practical Example: Three Similar-Looking Pages for Three Different Goals

Assume a team operates an API Gateway using **Gateway 4.2.2 GA** on a verified compatible release train and Spring Boot version. While searching for routing instructions, the team finds three pages:

| Page found | Example label | Decision |
|---|---|---|
| Docs matching the Gateway 4.2.x line (stable) | 4.2.x | Prefer this for the running system; check patch differences if any |
| Docs for Gateway 5.0.0-M1 (preview) | 5.0.0-M1 | Use only for upgrade evaluation/labs; do not copy directly into a 4.2.2 system |
| Docs for Gateway 5.0.0-SNAPSHOT | 5.0.0-SNAPSHOT | Reference only for in-development behavior; verify commit and artifact before testing |

The YAML route example below illustrates syntax commonly found in **some Gateway Server WebFlux 4.x lines**. This is a version-scoped example, **not a configuration snippet guaranteed to work unchanged across all WebFlux/MVC branches or newer releases**:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: order-service
          uri: http://order-service:8080
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
~~~

In this illustrative configuration, the `Path` predicate matches paths starting with `/api/orders/`, then `StripPrefix=1` removes the first path segment before forwarding. When calling `GET /api/orders/42`, the target service is expected to receive `GET /orders/42` assuming no other filter or proxy alters the path.

**If you mistakenly read preview/snapshot docs**, you might copy a property name or structure meant for a newer branch and then observe that routes are not created or requests go to the wrong target. The right diagnosis is to check the configuration namespace for the **exact version and exact variant** in the docs, configuration metadata packaged with the library, route registration logs, and smoke test results. Do not guess syntax simply because two pages both have "Gateway" in the title.

## 6. Most Common Pitfalls When Cross-Referencing Gateway Docs

### 6.1 Route Predicates and Filter Chains

Factory names, parameter syntax, filter ordering, and default filters can differ across branches. When needing `RewritePath`, `StripPrefix`, `AddRequestHeader`, or `RemoveRequestHeader`, open the page for the exact version and confirm input/output paths with test requests.

In particular, filter execution order can alter authentication, retries, and header modifications. A preview example does not guarantee binary or semantic compatibility with an older stable line.

### 6.2 Authentication, Authorization, and TLS

Documentation for Spring Security, OAuth2 Resource Server, Token Relay, or TLS often carries specific prerequisites by Spring Boot, Spring Security, and Gateway variant. Cross-check these prerequisites against the release train rather than looking only at the Gateway version number. In previews, APIs/filters may still be revised; in snapshots, docs may describe APIs not yet present in the binary you downloaded.

### 6.3 Rate Limiter, Circuit Breaker, Retry, and Discovery

A `RateLimiter`, `CircuitBreaker`, `Retry`, or load-balanced URI example depends additionally on integration libraries, data stores, or service discovery. Documentation on another branch may use different dependency versions. After selecting the right documentation, verify extra dependencies, trigger conditions, retry bounds to prevent request amplification, and fallback behavior when a service is unavailable.

### 6.4 Request Observability and Operations

Metric/tag names, actuator endpoint mechanisms, distributed tracing, access logs, and observability properties can change across Spring Boot/Spring Cloud lines. Before putting instructions into a runbook, inspect actual metrics/logs emitted by the running artifact. Snapshot pages should never be the sole source for configuring production alerts or incident playbooks.

## 7. When Should Each Type Be Used?

**Choose stable** when developing production features, troubleshooting, writing runbooks, testing compatibility, or upgrading within released versions. Pick the exact line of your running artifact; if an older line is end-of-life, plan an upgrade instead of blindly reading the newest stable docs.

**Choose preview** when evaluating breaking changes, inspecting features slated for the next release, or testing an upgrade plan. Use a dedicated experimental branch, document the milestone/RC, matching BOM, differences from stable, and test results. Once GA is published, re-check release notes and GA docs because preview content may have changed.

**Choose snapshot** when verifying an unreleased bug fix/feature or reproducing an issue against a specific commit. Record the **commit or build timestamp**, dependency coordinates, repository used, documentation build date, and test results. Use appropriate caching/locking/pinning to reduce the risk of builds changing between test runs. Avoid pulling auto-updating snapshots into production without strict controls.

For Maven/Gradle, GA artifacts are typically available via release repositories; milestone or snapshot artifacts may require dedicated repositories specified in the version's guide. **Never add a snapshot repository to a production project just so an example copied from a snapshot page can resolve dependencies.**

## 8. A Reproducible Documentation-Selection Check

Suppose a team needs to add rate limiting to a stably running gateway. Practical procedure:

1. **Lock down the current state**: record resolved Gateway version, Boot, Cloud BOM, JDK, and WebFlux/MVC; confirm how the gateway currently loads routes (configuration or Java DSL).
2. **Open same-line documentation**: select the rate limiter/filter reference for the exact stable version and variant; reject search results if the opened page points to a snapshot.
3. **Verify dependencies**: read integration library requirements, backing storage if applicable, and configuration conditions stated in the same-line docs.
4. **Test behavior**: build a test route, send requests below/above the limit, verify expected status codes, headers, or metrics, and test backend error cases.
5. **Record evidence**: save the version and URL of the referenced docs, test configuration, results, and items to re-verify on upgrade.

If exploring a feature **only available in preview**, explicitly note "not present in running GA", set up a test environment with a compatible BOM, and keep that example out of current production guides.

You can keep a short record directly inside the project's technical docs:

~~~text
Runtime: Gateway <artifact + resolved version>, WebFlux or MVC
Platform: Spring Boot <version>, Spring Cloud BOM <train>, JDK <version>
Docs: <branch URL and pinned version>
Doc type: stable | preview (M/RC) | snapshot (commit/build)
Reference scope: route, predicate/filter, security, observability
Test results: <test cases and outcomes>
Decision: adopt | continue testing | defer
~~~

Angle brackets are placeholders to fill in, not literal version names or configuration properties.

## 9. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| "Latest" is always what should run in production | "Latest" may alias the newest page or a development branch; check version labels and support policy |
| "Stable" means the docs match every stable release | Stable docs must still match your artifact's **version line** and **variant** |
| Spring Cloud release train and Gateway share the same version | The BOM manages multiple artifacts; inspect actual dependencies for the Gateway version |
| Preview and snapshot are the same thing | M/RC are identifiable pre-release milestones; SNAPSHOTs are mutable development builds |
| The newest snapshot doc page surely matches the local SNAPSHOT | Docs and artifacts may be built at different times or from different commits |
| One passing request proves full compatibility | You must test filter ordering, backend errors, security, rate limits, and observability for the behaviors your project uses |
| Gateway WebFlux and Gateway MVC share all examples | Each variant has its own starter, runtime environment, and configuration |
| Older GA releases are maintained indefinitely | GA status and active support status are two separate questions |

## 10. Checklist Before Copying an Example from Docs

- [ ] I know the **resolved Gateway artifact**, Spring Cloud release train, Spring Boot, and JDK.
- [ ] I know whether the project uses **Server WebFlux** or **Server MVC**.
- [ ] I checked the page's **actual version label**, not just "latest/current".
- [ ] I classified the page as **GA**, **M/RC**, or **SNAPSHOT**.
- [ ] I checked compatibility requirements, release notes, and support status.
- [ ] I verified the starter, configuration namespace, predicate/filter names, and extra dependencies.
- [ ] I tested successful requests plus relevant error/security/observability scenarios.
- [ ] I recorded the exact version and doc URL so others can re-verify later.

## Official Sources to Cross-Check

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — start from official docs, then select the **exact version and variant**.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — project overview and links to docs/releases.
- [Spring Cloud project](https://spring.io/projects/spring-cloud) — release trains, compatibility, and support lifecycle.
- [Spring Boot project](https://spring.io/projects/spring-boot) — cross-check Boot versions and underlying platform requirements.

**Core rule:** before applying any Gateway configuration line, identify **running artifact → variant → Spring Boot/Cloud BOM → same-version doc branch → behavioral tests**. Stable is the starting point for running systems; preview and snapshot are valuable for research but demand stricter cross-checking and verification.
