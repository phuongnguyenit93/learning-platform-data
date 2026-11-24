# Keeping Development Services Out of Production Packaging

## 1. Problem: Live Environments Accidentally Initializing Test Infrastructure

In a **Spring Boot Integration** application, development environments typically need PostgreSQL, Redis, Kafka, RabbitMQ, or a mock HTTP server. Spring Boot supports **development-time services** such as Docker Compose and Testcontainers so developers get full local infrastructure without manually configuring every endpoint. While highly productive during development and testing, this introduces a boundary that must be controlled: **production apps must use separately provisioned and managed production infrastructure, never spinning up test infrastructure due to mispackaged dependencies**.

Suppose a team runs PostgreSQL and Kafka via Compose, using `spring-boot-docker-compose` so Spring Boot resolves connections automatically. If dev-time libraries, Compose files, or `dev` configs remain active in production packaging and deployment, the app may:

- Attempt to invoke the Docker CLI/socket to spin up databases or brokers outside production infrastructure.
- Pick up connection info from a development service and accidentally **write to a different database** than configured for production.
- Fail at startup because production hosts lack Docker/Compose, deny Docker daemon permissions, or block image pulls.
- Start Testcontainers or test resources at app launch, causing misrouting, data loss on container removal, and operational violations.
- Activate local seed data, simplified auth, schedulers, or test-only consumers in a live environment.

This risk is especially severe in integration applications: an HTTP → database → outbox → Kafka flow may **report success** while writing to a test DB/broker, or a consumer may process messages and commit offsets against the wrong cluster. Checking only "the app passed healthchecks" is not enough.

~~~mermaid
flowchart TD
    Source["Source code"] --> Build["Build / dependency resolution"]
    Build --> Artifact["Executable JAR / OCI image"]
    Artifact --> Runtime["Production runtime"]
    DevDeps["Docker Compose / Testcontainers / Devtools"] -. "If leaked into runtime" .-> Artifact
    Runtime --> Prod["Production DB / broker / cache"]
    Runtime -. "Misconfig / service connection" .-> Local["Development-time services"]
    Gate["CI packaging + runtime configuration checks"] --> Artifact
~~~

**Objective:** separate development services from production infrastructure, configure dependency scopes properly, inspect final JARs/images, block accidental activation paths, and test thoroughly to catch releases pulling in unintended service connections.

## 2. Understanding "Development-Time Services" in Spring Boot

### 2.1. Spring Boot Docker Compose Support

In Spring Boot versions supporting Docker Compose (3.1+), `org.springframework.boot:spring-boot-docker-compose` lets dev apps discover Compose files and interact with their containers. For supported images/services, Spring Boot generates **connection details** to wire PostgreSQL, Redis, brokers, and related services.

Example `compose.yaml` strictly **for local use**:

~~~yaml
services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: integration_dev
      POSTGRES_USER: dev_user
      POSTGRES_PASSWORD: local_only_password
    ports:
      - "127.0.0.1:15432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "127.0.0.1:16379:6379"
~~~

When running Spring Boot on a developer machine with Docker, Compose support starts/detects services and supplies connection info. Loopback ports `127.0.0.1:...` illustrate local access; hosts/ports differ if the app runs inside a container on the same network.

**Easy-to-miss detail:** Compose integration can supply `ConnectionDetails` consumed by auto-configurations. Therefore never inspect only `spring.datasource.url` and assume the app **definitely** connects there: if dev-service connection details exist, verify the **actual runtime target**.

Compose files are not automatically embedded **inside the JAR** just because the Compose module is present. Risk emerges when **support libraries, Compose files, Docker access, and activation conditions** coincide—or when runtime loads the wrong config. Clearly separate **packaging dependencies**, **copying Compose files into images**, and **starting external containers**.

### 2.2. Testcontainers and `@ServiceConnection`

Testcontainers is normally used in integration tests to launch ephemeral databases or brokers in containers. With `spring-boot-testcontainers`, `@ServiceConnection` extracts connection info from supported containers so tests avoid hardcoding ports.

If container startup code sits in `src/main/java`, or test-only dependencies land on the runtime classpath, configuration like "PostgreSQL Testcontainer auto-starts on app launch" can execute in production. Merely having Testcontainers JARs on the classpath **does not automatically** launch containers without activating code/config. Still, keeping them completely out of production artifacts is an essential safeguard.

### 2.3. Components Easily Misclassified as "Dev-Only"

| Component | Role in development/testing | Risk if shipped to production |
|---|---|---|
| `spring-boot-docker-compose` | Integrates services from Docker Compose | Attempts to discover/start dev services when config & Docker access exist |
| `spring-boot-testcontainers` + Testcontainers | Connects DB/broker containers in tests or dev launchers | Leaks test infra into runtime; may launch containers if scanned |
| `spring-boot-devtools` | Hot reload and dev conveniences | Unsuitable release behavior and extra configuration surface |
| Embedded Kafka, fake brokers, SMTP capture, HTTP stubs | Isolates integration tests | Test listeners/ports/fixtures or fake transports intercept live business flows |
| H2 database and data-seeding configs | Prototype or repository testing | App uses ephemeral in-memory storage instead of real PostgreSQL |
| `application-dev.yml`, `compose.yaml` | Routes local services | Accidentally activated/copied; leaks sample passwords and dev hosts |

Not every library in this table is **always forbidden** in every product. The task is identifying dev-specific resources, evaluating real production needs, and ensuring release configs enable only approved components.

## 3. Crucial Boundaries: Compile Classpath, Runtime Classpath, and Artifacts

An application can **run fine in an IDE** while the release artifact behaves completely differently due to dependency scopes:

1. **Compile classpath**: libraries needed for compilation.
2. **Test classpath**: libraries included during test runs.
3. **Development/`bootRun` classpath**: libraries helpful locally, including `developmentOnly` dependencies.
4. **Production runtime classpath**: libraries the release needs at runtime.
5. **Repackaged executable JAR / Docker image**: final deployable output shaped by the Spring Boot plugin, `bootJar`/`repackage` rules, and Dockerfiles.

You cannot infer packaged contents just by reading `build.gradle` or `pom.xml`: Spring Boot plugins apply packaging exclusions, while custom setups, shadow JARs, manual copies, or images running `bootRun` alter the actual outcome.

~~~mermaid
flowchart LR
    Dev["Local: bootRun / IDE"] --> DevDeps["developmentOnly + runtime"]
    Tests["JUnit / Testcontainers"] --> TestDeps["testImplementation / test scope"]
    Build["Release: bootJar / repackage"] --> Runtime["Production runtime dependencies"]
    Runtime --> JAR["Executable JAR"]
    JAR --> Image["OCI image"]
    DevDeps -. "Block from release" .-> JAR
    TestDeps -. "Block from release" .-> JAR
~~~

## 4. Declaring Dependencies Properly with Gradle

For Gradle projects using the Spring Boot plugin (Groovy DSL example):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<compatible-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'

    // For local runs; excluded from standard executable bootJar.
    developmentOnly 'org.springframework.boot:spring-boot-docker-compose'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    // Scoped to test source set, excluded from production runtime.
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
~~~

`<spring-boot-version>` and `<compatible-version>` are **placeholders**, not literal build values; real projects use versions aligned with the Spring Boot BOM. Testcontainers module coordinates may vary across major releases; match the modules supported by your project's Spring Boot BOM/Testcontainers version.

Here:

- `developmentOnly` fits tools used when running the app **in development** and is excluded by Spring Boot's Gradle plugin from default executable JARs.
- `testImplementation` fits Testcontainers launched from tests, especially code under `src/test/java`.
- Putting dev dependencies into `implementation` or `runtimeOnly` is a common misclassification that pulls them onto the production runtime classpath.

**Check custom builds carefully:** if a project overrides JAR assembly, uses `shadowJar`, writes custom `Jar` tasks, alters `BOOT-INF/lib`, or copies all of `build/libs` into an image, default exclusions may break. Above all, never use `bootRun` or any command carrying a development classpath as a **production entrypoint**.

### 4.1. Example Test Keeping Testcontainers Strictly in the Test Source Set

~~~java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:17-alpine");

    @Test
    void repositoryCanPersistOrder() {
        // Call repository/service and assert against the database container.
    }
}
~~~

This file belongs strictly under `src/test/java`. `@ServiceConnection` provides test connection details when supporting dependencies sit on the test classpath; never move container configs into `src/main/java` merely for IDE convenience. To use Testcontainers while running the app locally, use a **test-only launcher** per Spring Boot docs, keeping dev code out of runtime artifacts.

The snippet shows structural layout, not a complete test: add data setup, real repository invocations, and assertions, using Spring Boot/Testcontainers versions supporting these annotations.

## 5. Declaring Dependencies Properly with Maven

Example `pom.xml` for Docker Compose development support:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Development-time support; Spring Boot packaging applies exclusion rules. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-docker-compose</artifactId>
        <scope>runtime</scope>
        <optional>true</optional>
    </dependency>

    <!-- Test classpath only. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-testcontainers</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**Two easy traps:**

1. In Maven, `optional=true` primarily controls **transitivity to downstream projects depending on this module**; it does not mean "guaranteed absent from this module's runtime classpath." The Spring Boot Maven plugin excludes `spring-boot-docker-compose` during repackaging in supported versions, yet you must still verify final output whenever customizing plugins, builds, or exclusions.
2. `scope=test` confines Testcontainers to tests, unlike `runtime` or `compile`, which ship them inside artifacts. When upgrading Testcontainers major versions, verify exact coordinates against your BOM.

Never enable packaging flags that **include Docker Compose** inside production executable artifacts. In Maven, inspect `spring-boot-maven-plugin` config (including `excludeDockerCompose` where supported), `repackage` settings, and build-profile overrides. Never treat `<optional>true</optional>` as a substitute for inspecting the actual JAR contents.

### Why Not Rely Only on Maven/Gradle Profiles?

Build profiles separate dependency groups, yet CI can select the wrong profile, and if an image contains multiple artifacts, building the right profile still does not ensure the release artifact was launched. Better practice is **proper scopes + clean builds + inspecting the final artifact + validating runtime config**.

## 6. Guarding via Runtime Configuration

### 6.1. Disabling Docker Compose in the Production Profile

`src/main/resources/application-prod.yml`:

~~~yaml
spring:
  docker:
    compose:
      enabled: false
  datasource:
    url: ${PROD_JDBC_URL}
    username: ${PROD_DB_USER}
    password: ${PROD_DB_PASSWORD}

app:
  integration:
    environment: production
~~~

In deployment environments, also set:

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_DOCKER_COMPOSE_ENABLED=false
PROD_JDBC_URL=jdbc:postgresql://<production-db-host>:5432/integration
~~~

Placeholders must come from real secret/config management—never commit production credentials to repositories. **`spring.docker.compose.enabled=false` is a defense-in-depth fallback if the Compose module unexpectedly exists; the primary defense remains excluding that module from production artifacts.**

Configuration sources like env vars or CLI flags override `application-prod.yml`. If a deploy script accidentally injects `SPRING_DOCKER_COMPOSE_ENABLED=true`, the file setting is overridden. Always inspect applied deployment manifests and verify effective endpoints/connections.

Never assume "production always runs with profile `prod`" without enforcing it. Validate environment configuration before accepting traffic, such as checking mandatory properties or startup validation aligned with your architecture.

### 6.2. Configuration Rules Matching Spring Boot Integration

| Setting/connection | Development environment | Production |
|---|---|---|
| PostgreSQL | Local Compose/Testcontainers; sample data | Provisioned database, controlled migrations, least-privilege roles |
| Kafka/RabbitMQ | Test broker, dedicated topics | Provisioned broker/namespace/ACLs, environment-scoped consumer groups |
| Redis/cache | Local cache instance, wipeable | Production cache with proper TTLs, auth, and real topology |
| HTTP clients | WireMock/mock API/test endpoints | Verified partner endpoints, TLS, timeouts, credentials, rate limits |
| Email | Mailpit/GreenMail, fake recipients | Approved email provider, recipient guards, send controls |
| Schedulers | Can trigger immediately for testing | Cluster coordination, idempotency, durable job state |
| Service connections | Built from dev containers | Production coordinates via trusted configs/secrets |

Stopping PostgreSQL auto-creation is insufficient if `spring.kafka.bootstrap-servers` still defaults to `localhost:9092` or `spring.data.redis.host` uses a local value. Inspect **every integration adapter**, not just the database.

### 6.3. Never Rely Solely on `@Profile`

A local-only config class might look like:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("dev")
class LocalIntegrationConfiguration {
    // Contains only adapters and stubs meant strictly for development.
}
~~~

Yet if this class starts containers and lives in `src/main/java`, it still **gets packaged into the JAR**. If someone flips on `dev` in production, those beans activate. For Testcontainers or non-production mocks, **keeping code in the test source set or a separate dev launcher module** eliminates the risk at the root.

## 7. Inspecting Executable JARs Before Release

**Inspect the deployed binary**, because dependency trees do not tell the full story after repackaging. For instance, a standard Spring Boot executable JAR stores libraries under `BOOT-INF/lib/`.

With Gradle:

~~~bash
./gradlew clean bootJar
jar tf build/libs/integration-service.jar
~~~

With Maven:

~~~bash
./mvnw -DskipTests package
jar tf target/integration-service.jar
~~~

`integration-service.jar` is an **illustrative filename**; use your build's real artifact name. `jar tf` lists JAR entries without executing the app or touching production.

A simple CI gate (Bash), run **after build**:

~~~bash
set -eu
APP_JAR="build/libs/integration-service.jar"

if jar tf "$APP_JAR" | grep -E \
  '(^|/)BOOT-INF/lib/(spring-boot-docker-compose|spring-boot-testcontainers|spring-boot-devtools|testcontainers-[^/]*|junit-jupiter[^/]*)[^/]*\.jar$'
then
  echo "ERROR: Development/test dependency found in release JAR" >&2
  exit 1
fi

echo "Release JAR dependency check passed."
~~~

Swap `APP_JAR` for your build path; use equivalent checks in PowerShell/Windows CI. The regex above is **an example project allow/deny policy**—expand it for Testcontainers modules and stubs actually used in your repo, noting it does not automatically cover unlisted test artifacts or nested repackaging formats.

**Key limitation of this gate:** if your project pulls a library whose filename misses the regex, update the policy. If `bootJar` lacks `BOOT-INF/lib` (e.g., native images, shaded JARs, layered images, or custom packaging), inspect with a tool built for that artifact format. Never treat an empty regex match as complete proof unless the check understands your exact artifact layout.

### 7.1. Dependency Reports for Diagnostics

In Gradle, inspect:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencies --configuration developmentOnly
~~~

In Maven:

~~~bash
./mvnw dependency:tree
~~~

If a dev library shows up on `runtimeClasspath`, trace the dependency edge that pulled it in. Still, **never conclude a JAR does or does not contain a library from dependency trees alone**: plugins can exclude libraries during packaging, or custom copy steps can inject extra JARs. Always cross-check **both reports and the actual artifact**.

### 7.2. Inspecting Docker/OCI Images

A multi-stage Dockerfile should copy **only the verified artifact** into the runtime image:

~~~dockerfile
# Build stage handled by CI or a builder image outside this snippet.
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY integration-service.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This assumes `integration-service.jar` is already built and verified. Real configs must ensure valid COPY paths in build context, matching Java runtimes, and proper directory permissions. **Never** bake the Docker CLI, `/var/run/docker.sock`, compose files, `src/test`, or fixture directories into release images without explicit approval.

A dangerous anti-pattern:

~~~dockerfile
# DO NOT use this to run release builds.
COPY . /workspace
WORKDIR /workspace
ENTRYPOINT ["./gradlew", "bootRun"]
~~~

`bootRun` can activate development classpaths, run Gradle, and look for local infrastructure—it is not a dependency-locked release artifact. Build images from executable artifacts or your project's official packaging mechanism.

When using Spring Boot Buildpacks/`bootBuildImage`, still inspect the resulting image and runtime dependency list. Buildpacks differ from running `bootRun`, yet do not waive checking profiles and connections.

## 8. Ensuring Production Startup Never Launches Dev Services

Before routing live traffic, verify:

- Startup logs show zero attempts to discover compose files, run `docker compose up`, or launch `Testcontainers`.
- The app process makes zero requests to a Docker daemon/socket.
- Effective `ConnectionDetails` point to environment-appropriate databases/brokers/caches; localhost or dynamic ports appear only when explicitly part of an approved design (such as a sidecar).
- Startup never executes dev seeds or test migrations against live databases; only approved production migrations run.
- Readiness turns green only after essential environment-appropriate dependencies respond; a running dev dependency must never stand in for real target checks.

Example startup state check:

~~~text
Expected:
  db.host = postgres.prod.internal
  kafka.bootstrap = kafka-prod.internal:9092
  redis.host = redis-prod.internal
  docker.compose.enabled = false

Unexpected:
  db.host = 127.0.0.1:15432
  kafka.bootstrap = localhost:9092
  container.image = postgres:17-alpine (started by application)
~~~

These hostnames are **illustrative**, not a mandate to hardcode hosts everywhere. In certain deployments, local sidecars/proxies are intentional; verify against approved deployment specs rather than treating "localhost is always wrong" as an absolute rule.

When logging connection info for diagnostics, never print passwords, tokens, connection strings with embedded credentials, or sensitive metadata. Prefer logging `environment`, backend type, and redacted endpoints alongside trace IDs, app version, and image digest.

## 9. Failure Paths Caused by Mispackaging and Misconfiguration

| Error | Symptom | Cause to investigate | Prevention |
|---|---|---|---|
| Added Compose to `implementation`/`runtimeOnly` | Release artifact holds dev module or probes Docker at startup | Wrong dependency scope or custom plugin config | Use `developmentOnly`/proper Maven setup; inspect JAR |
| Testcontainers placed in `main` | Production pulls images or demands Docker socket | Container beans scanned or shared dev launcher | Keep container configs in `src/test` or separate dev module |
| Image executes `bootRun` | Production runs dev classpath and needs source/build tools | Dockerfile uses developer run command | Run verified executable JAR / native image |
| Compose files copied into runtime | App can spin up local services | Overly broad build context and `COPY` | Multi-stage builds copying only artifacts; image policies |
| `SPRING_PROFILES_ACTIVE=dev` in prod | Connects to sandboxes, runs seed data | Wrong deployment env var | Lock down deployment manifests; validate before traffic |
| Dev `ConnectionDetails` overrides expected URL | Actual DB/broker differs from configured property | Dev service auto-config remained active | Disable support; verify effective runtime connections |
| In-memory DB runs in live environment | Data disappears on restart | Test URL/profile fallback | Fail fast if prod URL missing; zero test fallbacks |
| Build skips artifact gate | Release ships containing test JARs | Pipeline runs unit tests only | Add artifact/image inspection step |
| Missing Docker permissions | Startup crashes despite healthy prod DB | Compose/Testcontainers activated unintentionally | Keep dev modules out of prod; never mount Docker socket |
| Shared broker with local dev | Consumers read wrong topics/groups | Misconfigured bootstrap/credentials | Namespace, ACL, config validation, and audits |

### Case: A Release Build Writes to the Wrong Database

Suppose production sets `PROD_JDBC_URL` properly, yet the release JAR bundled a development service connection. If Compose/Testcontainers auto-wiring activates, repositories can hit another PostgreSQL instance. Migrations might even initialize tables cleanly in that unintended DB, letting basic smoke checks pass.

To catch this, verify **database identity** and expected schema markers—comparing server metadata from real connections against deployment manifests. Never mutate production data solely to "test connectivity"; controlled read-only queries and tracing suffice to verify the target.

### Case: Asynchronous Workers Amplify Misconfigurations

A message consumer pointing at the wrong Kafka cluster listens to the wrong topic, while a `@Scheduled` job across replicas can fire HTTP webhooks or emails from test fixtures externally. Protecting against dev services must cover **schedulers, listeners, outbound adapters, webhooks, and email gateways**, not just controllers.

## 10. Testing to Guarantee No Development-Time Services Leak

Design a multi-layered verification strategy:

### 10.1. Dependency and Artifact Checks in CI

1. Build using the **real release configuration**, not IDE dev settings.
2. Inspect runtime dependency reports; confirm identified dev/test modules remain in proper scopes.
3. Unpack/inspect the executable JAR and OCI image, asserting forbidden modules and stray Compose/fixture files are absent.
4. Run smoke tests against **that built artifact**, never `bootRun` from source.
5. Confirm no Docker socket is exposed to the app; if another approved feature needs Docker access, isolate permissions and review separately.

### 10.2. Production-Like Smoke Test

In staging or a production-like test deployment:

~~~text
Given:
  artifact = verified release JAR / OCI image
  profile = prod-like
  no Docker socket
  no local compose file
  explicit database, broker, cache endpoints

When:
  start the application and invoke health/readiness + read-only API

Then:
  app makes zero attempts to reach Docker daemon
  connection details point to supplied endpoints
  no seed data or test containers start
  business adapters activate strictly per environment config
~~~

**Smoke test caveat:** lacking a Docker socket can cause dev services to skip quietly or log warnings; a clean startup does not replace binary inspection and runtime target verification. Explicitly assert **no dev modules in the artifact** and **no dev connections active**.

### 10.3. Regression Tests for Configuration Binding

Configuration tests should cover:

| Test case | Input | Expected behavior |
|---|---|---|
| Local developer | Profile `dev`, Docker available, local Compose | App targets test containers cleanly without touching prod |
| CI integration | Testcontainers on test classpath | Tests manage containers; runtime artifact excludes test JARs |
| Production artifact | Release JAR, `prod` profile | `spring.docker.compose.enabled=false`, zero dev services |
| Missing `PROD_JDBC_URL` | Required env var absent | Startup fails fast, never falling back to H2/local Compose |
| Accidental `dev` config | Deployment attempts to activate dev profile | Validation/deployment gate rejects or fails before traffic |
| Wrong broker cluster | Bootstrap servers outside environment allowlist | Caught by startup validation or deployment gate |
| Version rollback | Deploy older artifact with current manifests | No dev infra created; schemas/adapters stay compatible |

In application context tests, checking for internal beans like `DockerComposeLifecycleManager` can be tied to specific Spring Boot versions; prefer verifying **observable behavior and packaged artifacts** rather than counting internal framework beans that may change across upgrades.

### 10.4. Testing Connection Failures Without Dev-Service Self-Healing

If production-like PostgreSQL is temporarily unreachable, the app must surface proper connection errors, reflect accurate readiness, and enforce bounded retries. It **must never** silently switch over to a local PostgreSQL instance and pretend everything is healthy.

This check is vital in integration systems because dependency outages are inevitable; falling back to fake infrastructure shatters the consistency guarantees other services depend on.

## 11. Prevention via Architecture and Release Process

A workflow that stays ergonomic for developers while staying safe in production:

1. **In source code:** place Testcontainers/fixtures under `src/test` or a separate dev-launcher module; scope Compose support strictly to development.
2. **In configuration:** separate `application-dev.yml`, `application-test.yml`, and `application-prod.yml`; require explicit endpoints/credentials in production with zero local fallbacks. Supply all secrets from secret managers.
3. **In builds:** build one clean release artifact via controlled targets, pin BOMs, and audit plugin include/exclude rules.
4. **In CI:** run unit/integration tests with Docker/Testcontainers to verify adapters, then inspect the actual release artifact and image.
5. **In deployment:** never mount Docker sockets or ship Compose files/local scripts into runtime containers; scope network access, namespaces, and secrets strictly to needed services.
6. **During rollout:** verify effective connections, migrations/schemas, consumer groups, topics, caches, and external HTTP endpoints; confirm logs show zero dev-service bootstrapping.
7. **During Spring Boot upgrades:** re-check dependency graphs, `ConnectionDetails` behavior, packaging plugin rules, and post-upgrade smoke tests.

Assign clear ownership: backend teams enforce dependency scopes and code boundaries; platform teams control images/manifests/networks; CI verifies binaries; operations confirms real runtime endpoints. These are **complementary layers** protecting one goal: never running test infrastructure as part of production.

## 12. Self-Check Questions

1. Why doesn't a passing `./gradlew bootRun` with local Compose prove the executable JAR carries the same dependencies and wiring?
2. If `spring-boot-docker-compose` sits in `runtimeOnly`, how can you prove whether the release artifact actually includes or excludes it?
3. Is `optional=true` in Maven enough to guarantee a dependency stays out of the current module's executable JAR? Why?
4. When `@ServiceConnection` generates connection details from Testcontainers, what can cause the URL declared in `application.yml` not to match the actual connection target?
5. What risks does placing container configuration under `src/test/java` eliminate compared to keeping it in `src/main/java` behind `@Profile("dev")`?
6. If production starts up cleanly even while primary PostgreSQL is down, what clues reveal that a dev database was used by mistake?
7. Why is checking the dependency tree alone insufficient when projects customize packaging and Dockerfiles?
8. In a system with HTTP clients, DB, cache, Kafka, and schedulers, which endpoints/adapters must be verified before shifting live traffic?

**Conclusion:** development-time services accelerate building and testing Spring Boot Integration apps, yet their scope must stop at development and testing. Enforce that boundary through **accurate dependency scopes, separate source sets, fail-fast production configs, artifact/image inspection, and effective-connection tests**. By keeping Docker Compose/Testcontainers out of release packaging and preventing accidental mock adapter activation, your system connects exclusively to production-controlled databases, caches, brokers, and HTTP endpoints.

### References

- [Spring Boot — Development-time Services](https://docs.spring.io/spring-boot/reference/features/dev-services.html): Docker Compose support, lifecycles, and service connections.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` and Testcontainers integration for testing.
- [Spring Boot Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootJar`, dependencies, and packaging behavior.
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html): `repackage` and dependency exclusion settings.
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): `scope`, optional dependencies, and transitivity.
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): dependency configurations and classpaths.
