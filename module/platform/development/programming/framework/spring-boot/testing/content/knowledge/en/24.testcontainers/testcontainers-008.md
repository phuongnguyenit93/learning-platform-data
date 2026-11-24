# Testcontainers: Choosing Images, Pinning Versions, and Controlling Repeatability

## 1. An integration test can change outcomes even when Java code stays untouched

You write a Spring Boot test connecting to PostgreSQL via Testcontainers:

```java
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:latest");
```

Today the test passes. A week later, a fresh CI machine pulls a different image under the same `latest` tag, the database server or OS inside the image changes, and the migration fails. The developer's machine still passes because its local Docker cache holds the old image. Nothing changed in the Java source, yet **the execution conditions changed**.

That is why images must be managed like a **test dependency**. There are three distinct questions:

1. **Which image to choose?** Right service, engine, architecture, version, extensions, and trusted publisher?
2. **How to pin the image?** Mutable tag, version tag, or `sha256` digest? How tightly to pin for stable results?
3. **How to control repeatability?** Once the image is pinned, what other sources of variance (JDK, Gradle, dependencies, schema, timezone, locale, test data, container startup, and CI runtime) can still produce different outcomes?

A **patch-specific tag** like `postgres:16.6-alpine` reduces unintended drift compared to `postgres:latest`, yet **a tag can still be republished by the registry**. A Docker image **digest** identifies a content-immutable manifest or multi-platform image index. When using a verified digest, the runtime does not automatically pick a new manifest just because the registry maintainer updated a tag. However, digest pinning **does not by itself protect against security vulnerabilities, missing images on the registry, or CPU architecture differences**.

This lesson explains the mechanics, decision criteria, safe image-upgrade workflow, and a runnable **Java 17 + Spring Boot 3.3 + Testcontainers + PostgreSQL** project where the image selection is explicit configuration verified against the actual database version.

## 2. Learning outcomes

After this lesson, you will be able to:

1. Understand how Docker image, repository name, tag, digest, manifest, image index, and local image ID differ.
2. Select images by vendor/major/minor/patch, distribution variant, architecture, extensions, and operating environment.
3. Explain why `latest`, `16`, `16-alpine`, and even `16.6-alpine` remain **mutable tags**.
4. Use `docker pull`, `docker image inspect`, and `docker buildx imagetools inspect` to obtain real digests without inventing hashes.
5. Distinguish a **multi-platform index digest** from a **single-architecture manifest digest**.
6. Use `DockerImageName.parse(...)` and dedicated Testcontainers modules to reference pinned images.
7. Manage images from private registries/mirrors and cases needing `asCompatibleSubstituteFor(...)`.
8. Understand image pull policies and the Docker local cache, avoiding the assumption that "tests ran on tag X" means the latest X was pulled.
9. Write a JUnit `@DataJpaTest` with `PostgreSQLContainer`, `@ServiceConnection`, Flyway, Hibernate validation, and real PostgreSQL SQL tests.
10. Capture `DatabaseMetaData`, `server_version_num`, schema migration version, and requested image reference for diagnostics.
11. Understand why JDK/Gradle/Boot BOM/JDBC driver, migrations, locale/timezone, container state, and platform still affect repeatability.
12. Design a digest-upgrade workflow incorporating security review, testing, and rollback to the previous version.
13. Distinguish reproducibility of a **binary image** from repeatability of **test results** and production equivalence.
14. Choose pinning strategies for PR gates, compatibility matrices, nightly security refreshes, and release tests.

## 3. Image, container, tag, and digest: terminology map

| Term | Core meaning | Example |
| --- | --- | --- |
| Registry | System storing/distributing images | `docker.io`, internal registry |
| Repository | Image repository name in a registry | `library/postgres` |
| Tag | Label pointing to an image manifest/index | `16.6-alpine`, `16-alpine`, `latest` |
| Image reference | String specifying an image to pull/run | `postgres:16.6-alpine` |
| Digest | Content hash of a manifest or image index | `sha256:...` |
| Image ID | Local Docker image/config identifier | `sha256:...` string from `docker image inspect` |
| Image manifest | Describes config/layers for one specific image | `linux/amd64` manifest |
| Image index / manifest list | Collection of manifests across platforms | Index containing `linux/amd64`, `linux/arm64` |
| Container | Running instance created from an image | PostgreSQL process of a test run |
| Volume/data directory | Runtime storage of the container | `PGDATA`, data initialized during tests |
| Testcontainers module | Java API starting a specific service type | `PostgreSQLContainer` |

Two commonly confused facts:

**A tag is a name, not an immutability guarantee.** A registry can change the mapping tag → manifest/index. A seemingly specific tag like `16.6-alpine` can still be rebuilt to pick up base-image security patches or per publisher release policy.

**A digest identifies manifest/index content, not publisher trustworthiness.** Knowing a hash does not mean you verified provenance, signatures, licenses, or vulnerability status. An image can also be removed from a registry even though its digest remains a valid identifier.

### 3.1. What forms can an image reference take?

```text
postgres:latest
postgres:16
postgres:16-alpine
postgres:16.6-alpine
docker.io/library/postgres:16.6-alpine
postgres@sha256:<verified-real-digest>
docker.io/library/postgres@sha256:<verified-real-digest>
```

The two lines containing `<verified-real-digest>` **illustrate syntax only**, not runnable commands; substitute an **actual SHA-256 digest fetched from the registry**. Never invent a fake 64-character hex string just to make an example look real.

### 3.2. Tag and digest can appear together

Docker supports referencing an image with both tag and digest in certain forms (`name:tag@sha256:...`). When a digest is specified, **the digest is what locks the selected content**. The tag helps human readers recognize the "version line," but must never be treated as proof of content if the digest does not match expectations.

When managing test configuration, record all of:

- **Human-readable version intent:** PostgreSQL 16, Alpine variant.
- **Resolved immutable reference:** image repository + verified digest.
- **Source and verification timestamp:** registry/publisher, date, and update workflow.
- **Platform:** `linux/amd64` or `linux/arm64` when relevant.

## 4. Why is `latest` unsuitable for critical regression tests?

Consider the test:

```java
new PostgreSQLContainer<>("postgres:latest");
```

The risks:

- `latest` can jump to a **new major version**, changing SQL behavior, extension compatibility, or server defaults.
- Developer A and CI B have different local image caches.
- Image publishers can rebuild the same tag, updating OS packages without changing the name.
- Cold-cache CI pulls the current release; warm-cache developer stays on the old one.
- A migration failure may reproduce on only one machine, hard to explain from Git commits.
- On release day, logs showing only `postgres:latest` do not reveal which version tests actually ran.

**Never use `latest` for test gates that need identical conditions on rerun.** Using `latest` can be helpful in a separate job aimed at early compatibility detection against upcoming releases; however, that job must be labeled a **moving target**, not a deterministic verification gate.

### 4.1. Pinning major, minor, patch, and digest

| Strategy | Example | Stability | When appropriate |
| --- | --- | --- | --- |
| Unpinned | `postgres:latest` | Very low | Upstream canary tracking |
| Pin major | `postgres:16` | Fixes major line, patches may shift | Compatibility within a major version |
| Pin major + distro | `postgres:16-alpine` | Fixes major/variant, still updates | CI wanting regular patch updates |
| Pin patch tag | `postgres:16.6-alpine` | More specific, yet **tag remains mutable** | Controlled local labs / compatibility matrices |
| Pin digest | `postgres@sha256:...` | Locks manifest/index | PR/release gates needing traceability |
| Pin verified internal digest | `registry.example...@sha256:...` | Locks artifact from internal registry | Enterprises using mirroring/allowlists |

There is no single "best" for every job. A system can combine:

- PR gates running a reviewed digest (stable).
- Nightly jobs running the latest patch tag of the same major (catching upstream changes).
- Compatibility jobs running across supported PostgreSQL major versions.
- Security update workflows opening PRs to bump digests and run the full regression suite.

### 4.2. Version pinning is not quality pinning

An old pinned digest can become **vulnerable**. When a critical CVE arises, the right response is not blindly deleting the pin and reverting to `latest`; select a patched image, verify provenance/digest, update the pin in code/lock manifest, and run compatibility tests.

Pin to **control when changes occur**, not to freeze a version forever.

## 5. Docker local cache and image pull policy

Docker caches pulled/built images on the local host. Testcontainers generally leverages the image cache and pulls only as required by the active policy. A build with cached `postgres:16-alpine` can execute a different binary than a cold-cache build despite identical source and tag.

### 5.1. The "works on my machine" phenomenon

```text
Developer A (warm cache)
  postgres:16-alpine -> digest D1
  tests -> PASS

CI B (fresh pull)
  postgres:16-alpine -> digest D2
  tests -> FAIL

Git commit + test source: identical.
Actual image digest: different.
```

Pinning by digest directs both environments to the **same manifest/index** instead of letting each host resolve a moving tag independently.

### 5.2. Should you always pull?

Testcontainers provides image pull policies:

```java
PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16-alpine")
                .withImagePullPolicy(
                        PullPolicy.alwaysPull());
```

This is a **reference snippet**; does it import `org.testcontainers.images.builder.Transferable`? **No**; the required class for `PullPolicy` is `org.testcontainers.images.PullPolicy`. Never add unrelated imports into code. `alwaysPull` attempts to pull the referenced image, which can be slower and depends on registry/network availability.

- With a **mutable tag**: always pull surfaces new tag builds quickly, yet **destabilizes regression gates** whenever upstream moves the tag.
- With an **immutable digest**: always pull does not change the selected content, yet can add unnecessary network/registry load.
- In **offline CI**: always pulling can fail even when the right image is already cached.
- For **security updates**: use an image update workflow rather than enabling always pull and hoping test locks update themselves.

**Choose pull policy per job objective**, rather than using it as a substitute for version pinning.

### 5.3. Pull policy does not control every image

A Testcontainers suite can also use auxiliary images, such as the resource reaper or module-specific sidecars/helpers. Pinning the PostgreSQL image **does not lock every image** Testcontainers pulls. For a complete audit, record the Testcontainers library version, every created image, registry/substitutions, and container runtime.

Do not disable resource cleanup just to reduce image pull errors; configure registry mirrors and permissions properly in restricted environments.

## 6. Digest: content-immutable, yet still platform-dependent

A Docker/OCI `sha256` digest can identify either:

1. **An image manifest for one platform**, e.g. `linux/amd64`.
2. **An image index / manifest list** containing multiple manifests, e.g. `linux/amd64` and `linux/arm64`.

When you pin an **index digest**, the registry index never changes, yet Docker on `amd64` and Docker on `arm64` select **two different platform manifests** within that index. Tests may pass logically on both, while OS binaries and architecture behavior still differ.

### 6.1. Inspecting the manifest index

Command:

```bash
docker buildx imagetools inspect postgres:16.6-alpine
```

This displays the repository, media type, top-level digest, and lists architecture/platform manifests. Never copy an `linux/arm64` digest onto a `linux/amd64` CI node expecting native execution.

### 6.2. Choosing index digest vs architecture digest

- **Index digest**: preserves the manifest set, convenient for teams mixing Apple Silicon/`arm64` laptops and Linux/`amd64` CI; different machines still execute different platform binaries. This provides **multi-platform release set** reproducibility, not byte-for-byte identical binaries across machines.
- **Platform manifest digest**: locks the exact image for a specific architecture; fits a uniform `linux/amd64` CI fleet. On other platforms it may require emulation or fail to run.
- **Tag digests recorded in SBOMs/lockfiles**: know which digest kind was recorded so you never misclaim "100% identical image."

### 6.3. Why `--platform` matters

Docker supports selecting a platform when pulling/building/running. However, the Testcontainers module, runtime support, image support, and host architecture must still align. Do not force all tests to run emulated `amd64` on `arm64` purely for uniformity; emulation can be slow, introduce system bugs, and fail to represent production.

To claim repeatability, record at least **image digest + OS/CPU platform + database server version**.

## 7. Obtaining a real digest from an image without fabricating hashes

### 7.1. Pull a chosen patch tag

```bash
docker pull postgres:16.6-alpine
```

This is an **illustrative tag for the lab**, not advice to deploy an unpatched PostgreSQL 16.6 in production. In real systems, choose an approved, supported patch/digest.

Docker prints `Digest: sha256:...` corresponding to the pulled registry object. Record only **actual digests** from that output.

### 7.2. Inspect local RepoDigests

```bash
docker image inspect \
  --format '{{json .RepoDigests}}' \
  postgres:16.6-alpine
```

`RepoDigests` holds repository-digest references attached to the local image when available. It may be absent on locally built images not pulled from a registry. Never mistake `Id` from `docker image inspect` for a registry manifest digest.

To extract one reference from the pulled image:

```bash
docker image inspect \
  --format '{{index .RepoDigests 0}}' \
  postgres:16.6-alpine
```

This works only when `RepoDigests` is non-empty; if element 0 does not exist, investigate rather than fabricating a digest.

### 7.3. Inspect the registry index directly

```bash
docker buildx imagetools inspect postgres:16.6-alpine
```

For a top-level index, output usually lists `Digest` and platform manifests. When choosing the index digest, store the **fully qualified name + digest** exactly as reported by the tool.

### 7.4. Why not compare `docker image inspect .Id` with a registry digest?

`image .Id` is typically the hash of the image config (a local image identifier). A registry digest is typically the hash of a manifest or index. Both may start with `sha256:`, yet **they hash different objects**. A test or script comparing the two strings and claiming a supply-chain mismatch is flawed in principle.

A sound report records clearly:

- `requestedImageReference`: which image did the test author request?
- `repoDigest`: which registry manifest/index ref resolved?
- `imageId`: local image config ID?
- `platform`: which architecture did the container run on?
- `serverVersion`: what version did the real program report?

Do not lump all of these under a vague label like "image hash."

## 8. Criteria for choosing an image

When picking a PostgreSQL image or other service images, apply this table:

| Criterion | Question to answer |
| --- | --- |
| Real service or emulator? | Real PostgreSQL engine, or a simulated service? |
| Publisher | Docker Official Image / vendor image / internal image? |
| Major compatibility | Which PostgreSQL major version does production run? |
| Patch and support | Has the patch received security updates, and is it still supported? |
| Distro variant | Alpine vs Debian; does it affect libc/locale/extensions? |
| CPU architecture | Do CI `linux/amd64` and dev `arm64` both have matching manifests? |
| Extensions/features | Are `pg_trgm`, PostGIS, SSL, locale/ICU, or logical replication needed? |
| Runtime startup | Are entrypoint, readiness, init scripts, and health checks module-compatible? |
| License and compliance | Permitted to distribute and pull the image in CI? |
| Registry availability | Can CI pull via network/mirror/credentials? |
| Provenance/signature | Is there a way to verify publisher and build provenance? |
| Data initialization | Empty volume, which schema/migrations/scripts run? |
| Upgrade plan | Is there a process to pick and test newer digests? |

### 8.1. Alpine or Debian?

`postgres:16.6-alpine` and a Debian-based PostgreSQL image of the same major version do not behave identically in base OS, glibc vs musl, locale/ICU, installed packages, extension availability, and startup scripts.

If production uses PostgreSQL with specific ICU/collation settings, an Alpine test image may **not reflect** the same collation behavior. When integration tests guard sorting or case normalization, pick a variant and locale matching production or test specifically in a matching environment.

**Note:** the patch tag pinned in this lab may age over time. Picking the right baseline patch as of today is a maintenance decision, not a permanent constant.

### 8.2. A smaller image is not automatically better for every test

Alpine images are typically smaller and faster to pull, yet when extensions, build tools, or locales are needed they may require customization. Debian-based images may be larger while offering better extension compatibility. Choose based on **the behavior being verified**, not megabytes alone.

### 8.3. Choosing the right image for Kafka/Redis/MongoDB

- **Kafka:** broker image/version, KRaft vs ZooKeeper, advertised listener addresses, message format compatibility; never use a "Kafka-like emulator" to claim real broker fidelity.
- **Redis:** major version, standalone vs cluster, ACLs, Redis Streams/TTL; one node does not prove failover.
- **MongoDB:** server major/FCV, indexes, BSON conversions, replica set/transaction topology.
- **RabbitMQ:** version, management plugins, queue type (classic/quorum), acknowledgment/redelivery.
- **Elasticsearch/OpenSearch:** engine version, analyzer/index settings, plugins; API similarity does not guarantee vendor equivalence.
- **LocalStack:** an emulator of a subset of AWS APIs; image pinning keeps the emulator stable, **it does not turn it into production AWS**.

Never equate "runs in a container" with production equivalence: you need the right **service type** and **tested behavior**.

## 9. Testcontainers image modules and image name compatibility

With the PostgreSQL module, standard usage:

```java
import org.testcontainers.containers.PostgreSQLContainer;

PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.6-alpine");
```

When passing the image ref through configuration or digest, use:

```java
import org.testcontainers.utility.DockerImageName;

DockerImageName image =
        DockerImageName.parse(imageReference);

PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>(image);
```

In this snippet, `imageReference` must be supplied by the app/test (the lab has complete code in Section 12/13). `DockerImageName.parse` lets Testcontainers parse registry/path/tag/digest cleanly instead of manual string manipulation.

### 9.1. Private registry/mirror

A CI setup restricting Docker Hub may mirror the official PostgreSQL image into an internal registry, for example:

```text
registry.example.invalid/mirror/postgres:16.6-alpine
```

This is an **illustrative name with no real server**. Dedicated modules verify that the image belongs to a compatible family. For a vetted mirror with **the same PostgreSQL behavior**, declare:

```java
DockerImageName mirrored =
        DockerImageName.parse(
                "registry.example.invalid/mirror/postgres:16.6-alpine")
            .asCompatibleSubstituteFor("postgres");

PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>(mirrored);
```

This is a **non-runnable snippet** because the registry URL is illustrative. `asCompatibleSubstituteFor("postgres")` is an **assertion of responsibility that the substitute image is compatible with official postgres**; it **does not** verify the binary or pull from upstream.

Before allowing a mirror in CI:

1. Verify upstream and mirror digests, keeping in mind manifest/index digests can change when copied.
2. Confirm the image actually runs the target PostgreSQL version.
3. Verify extensions, entrypoint/env vars, and architecture.
4. Manage registry auth via the CI secret store.
5. Never hardcode registry passwords in Java source or Gradle files.
6. If a mirror image is rebuilt/customized, treat it as a **new artifact** and update attestation/reviews.

### 9.2. Automatic image name substitution

Testcontainers supports image name substitution through config or custom substitutors. This lets test code reference official image names while CI resolves them to a registry mirror.

This flexibility carries a consequence: **the image reference written in a test is not necessarily the image actually run**. When auditability/reproducibility is required, record both the requested ref and actual resolved ref, and govern substitutions by policy.

Do not interpret a test requesting `postgres:16.6-alpine` as proof it pulled the official Docker Hub image if a substitutor/registry mirror is active.

## 10. Pinning images does not synchronize Java library versions

An integration test spans multiple version layers:

```text
Git revision
  |
  +-- JDK 17 toolchain / Gradle wrapper
  +-- Spring Boot version + Spring Dependency BOM
  +-- Testcontainers Java artifacts
  +-- PostgreSQL JDBC driver / Hibernate
  +-- Flyway/Liquibase version
  +-- Testcontainers image reference/digest
  +-- PostgreSQL server binary version
  +-- SQL migrations + seed data
  +-- OS/CPU architecture + container runtime
  +-- Locale/UTC + test execution order/concurrency
  |
  v
Test behavior
```

Pinning `postgres@sha256:...` while leaving dynamic versions `+` or `latest.release` in Gradle can still change the dependency tree on rerun. Conversely, locking Maven/Gradle dependencies while keeping `postgres:latest` lets the service engine drift.

### 10.1. Use the Spring Boot BOM instead of hardcoding scattered versions

In Spring Boot 3.3, Testcontainers integration and Spring/JUnit libraries are coordinated by Boot's dependency management. Pick one Spring Boot line and let the BOM align compatible versions. When overriding a Testcontainers version is necessary, require clear justification, compatibility checks, and Gradle lockfiles.

**Do not** drop APIs/code from the latest Testcontainers 2.x into a Boot 3.3 project using 1.x artifacts without checking breaking changes. `@ServiceConnection` mechanics and module dependency layouts can change across major lines.

### 10.2. Gradle Wrapper and dependency locking

- Commit `gradle/wrapper/gradle-wrapper.properties` / wrapper files approved by your organization.
- Use Java toolchains to target Java 17 instead of picking up whatever runtime sits on a developer's machine.
- Never use dynamic dependencies when reruns must resolve identical versions.
- Consider Gradle dependency locking (`dependencyLocking { lockAllConfigurations() }`) to lock transitive dependencies.
- Review lockfiles whenever upgrading the BOM, JDBC driver, or Testcontainers.
- When using an internal Maven mirror, verify artifact provenance and caching policies.

### 10.3. Database image tag vs server version

`postgres:16.6-alpine` describes the intended tag. Actual SQL:

```sql
SELECT current_setting('server_version_num');
```

verifies the server major/minor/patch number from **the running database process**. It does not replace digest checks, yet confirms tests connected to the right engine/version.

Do not assert byte-for-byte equality on `SELECT version()` in CI: the string contains compiler/OS/build metadata that varies by platform. If the contract requires major 16, assert the major version and log the exact server version as diagnostic metadata.

## 11. Pinning images while still permitting intentional upgrades

An effective pattern separates **baseline configuration** from **override mechanism**:

```text
DEFAULT_TEST_IMAGE = "postgres:16.6-alpine"  // patch tag for the lesson
CI_LOCKED_TEST_IMAGE = verified repo@sha256:digest
NIGHTLY_TARGET_IMAGE = reviewed newer candidate
```

This is a policy sketch, not Java syntax or runnable config. In the lab:

- Java tests read the system property `test.postgres.image`.
- Gradle forwards `-PtestPostgresImage=...` into that property.
- Without an override, it falls back to illustrative tag `postgres:16.6-alpine` so learners can run it easily.
- Release/PR CI gates should override with a **verified digest**.
- Tests verify the actual PostgreSQL major version and migration version so they never pass on the wrong engine.

This lets **the exact same test code** run against an approved artifact without embedding a fake digest in documentation.

### 11.1. The image reference must be an atomic configuration unit

Never construct an image name via:

```java
String ref = "postgres:" + System.getenv("PG_MAJOR");
```

if digest pinning is the goal. That selects only a major tag and drops patch/digest precision. Pass the **complete image reference** (repository + tag or repository + digest) and validate it against policy.

### 11.2. What if the override is missing in release CI?

Failing closed is the strict choice:

- Require `-PtestPostgresImage` to be `repo@digest` in release pipelines.
- If missing, fail the pipeline with a clear message.
- Local labs allow falling back to a patch tag for learning.
- A separate job can run a moving tag to monitor upstream, without labeling it a reproducible gate.

In the runnable example, fallback is kept for accessibility; fail-closed enforcement is described as a **CI extension**, without pretending the demo code enforces it itself.

## 12. Runnable project: Java 17 + Spring Boot 3.3 + PostgreSQL Testcontainers + Flyway

Goal: build a **JPA test slice** connecting to real PostgreSQL 16 (not H2), with the schema created by **Flyway migrations** instead of Hibernate `create-drop`. We will:

1. Pass the PostgreSQL image reference via a Gradle project property (replaceable with a digest).
2. Use `DockerImageName.parse` and `PostgreSQLContainer`.
3. Use `@ServiceConnection` so Boot extracts JDBC connection details from the container.
4. Use `@AutoConfigureTestDatabase(replace=NONE)` because Spring Boot **3.3** may replace datasources in `@DataJpaTest` by default.
5. Use Flyway to create schema/indexes and Hibernate `ddl-auto=validate` to verify mappings.
6. Assert the real database is PostgreSQL major 16 and migration version is 1.
7. Run native SQL `ILIKE` to prove PostgreSQL engine behavior.
8. Let PostgreSQL reject duplicate unique keys and negative price `CHECK` constraints.

### 12.1. Project structure

```text
test-image-reproducibility/
├── settings.gradle
├── build.gradle
├── src/main/java/example/imagepin/
│   ├── ImagePinApplication.java
│   ├── InventoryItem.java
│   └── InventoryRepository.java
├── src/main/resources/db/migration/
│   └── V1__create_inventory_item.sql
└── src/test/java/example/imagepin/
    └── PinnedPostgresIntegrationTest.java
```

Create each file at the exact path/package. The example uses `Spring Boot 3.3.0` **to keep imports consistent**, not as a claim that it is the latest production release. Real systems should select an actively supported release with security patches. PostgreSQL tag `16.6-alpine` is likewise an **illustrative baseline** that must be updated to a reviewed digest/version before production pipeline use.

### 12.2. `settings.gradle`

```groovy
rootProject.name = 'test-image-reproducibility'
```

### 12.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.flywaydb:flyway-core'

    runtimeOnly 'org.flywaydb:flyway-database-postgresql'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()

    systemProperty 'test.postgres.image',
            providers.gradleProperty('testPostgresImage')
                    .orElse('postgres:16.6-alpine')
                    .get()
}
```

**Why use Gradle `systemProperty`?** A project property `-PtestPostgresImage=...` lives only inside the Gradle process, whereas tests execute in a forked JVM. `tasks.named('test').systemProperty(...)` passes the value into the JUnit JVM so `System.getProperty("test.postgres.image")` can read it. Passing `-Dtest.postgres.image=...` to `./gradlew test` without forwarding it to the test worker will not automatically reach the JUnit JVM.

**Why include `flyway-database-postgresql`?** Modern Flyway splits database-specific modules for PostgreSQL; the Spring Boot 3.3 BOM manages compatible versions. Having `flyway-core` alone may be insufficient for Flyway 10.x + PostgreSQL.

**Why is H2 omitted?** The goal is real PostgreSQL. No H2 test driver is needed; yet `replace=NONE` is still written so intent is explicit and Boot 3.3-compatible.

**Gradle Wrapper:** if a compatible Gradle 8.x is installed locally, run `gradle wrapper --gradle-version 8.7` once and commit the wrapper files. Then run `./gradlew` or `.\gradlew.bat`. The project tree lists only key source files rather than printing binary wrapper files.

### 12.4. `ImagePinApplication.java`

**`src/main/java/example/imagepin/ImagePinApplication.java`:**

```java
package example.imagepin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImagePinApplication {
    public static void main(String[] args) {
        SpringApplication.run(ImagePinApplication.class, args);
    }
}
```

`@DataJpaTest` uses this application class to locate auto-configuration and scan matching entities/repositories without loading unrelated services/controllers like `@SpringBootTest`.

### 12.5. `InventoryItem.java`

**`src/main/java/example/imagepin/InventoryItem.java`:**

```java
package example.imagepin;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "inventory_item")
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, length = 40)
    private String sku;

    @Column(name = "title", nullable = false, length = 120)
    private String title;

    @Column(name = "price_cents", nullable = false)
    private long priceCents;

    protected InventoryItem() {
        // Required by JPA.
    }

    public InventoryItem(
            String sku,
            String title,
            long priceCents) {
        this.sku = sku;
        this.title = title;
        this.priceCents = priceCents;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getTitle() {
        return title;
    }

    public long getPriceCents() {
        return priceCents;
    }
}
```

The entity uses `GenerationType.IDENTITY` so PostgreSQL assigns IDs. Tests **do not** assert that IDs start at 1; sequence/identity counters can advance even across rolled-back transactions.

### 12.6. `InventoryRepository.java`

**`src/main/java/example/imagepin/InventoryRepository.java`:**

```java
package example.imagepin;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    Optional<InventoryItem> findBySku(String sku);

    @Query(
            value = """
                    SELECT *
                      FROM inventory_item
                     WHERE title ILIKE CONCAT('%', :term, '%')
                     ORDER BY sku
                    """,
            nativeQuery = true
    )
    List<InventoryItem> searchTitleIgnoreCase(
            @Param("term") String term);
}
```

`ILIKE` is PostgreSQL-specific syntax. If a test accidentally ran on H2, this query would not prove PostgreSQL equivalence; metadata assertions and an explicit datasource verify the real engine.

`@Param` binds the query parameter instead of concatenating raw SQL strings with input. If input contains `%` or `_`, pattern matching treats them as wildcards; literal substring search requires escaping wildcards per contract rather than assuming parameter binding turns `LIKE` into literal matching.

### 12.7. Flyway migration `V1__create_inventory_item.sql`

**`src/main/resources/db/migration/V1__create_inventory_item.sql`:**

```sql
CREATE TABLE inventory_item (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(40) NOT NULL,
    title VARCHAR(120) NOT NULL,
    price_cents BIGINT NOT NULL,
    CONSTRAINT uk_inventory_item_sku UNIQUE (sku),
    CONSTRAINT ck_inventory_nonnegative
        CHECK (price_cents >= 0)
);

CREATE INDEX idx_inventory_item_title_lower
    ON inventory_item (lower(title));
```

This migration contains valid PostgreSQL DDL for the lab's target version. Hibernate **does not recreate the schema**, because the test sets `ddl-auto=validate`.

Key distinctions:

- `uk_inventory_item_sku` enforces the unique business key.
- `ck_inventory_nonnegative` enforces non-negative prices in the database.
- Expression index `lower(title)` is an example expression index, yet **does not guarantee** accelerating `ILIKE '%term%'`; leading-wildcard searches may require `pg_trgm` and a matching index.
- SQL migrations are part of repeatability: the same image with altered migrations produces a different schema.
- Production may involve Flyway history, baseline/repair/validate, and upgrades from older schemas; the lab uses only V1 on an empty schema.

**Never copy `ddl-auto=create-drop` into a migration integration test**: Hibernate may generate the schema in place of Flyway and mask broken production DDL.

## 13. Complete test `PinnedPostgresIntegrationTest.java`

**`src/test/java/example/imagepin/PinnedPostgresIntegrationTest.java`:**

```java
package example.imagepin;

import java.sql.Connection;
import java.util.List;

import javax.sql.DataSource;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.TestPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataJpaTest(properties = {
        "spring.jpa.hibernate.ddl-auto=validate"
})
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class PinnedPostgresIntegrationTest {
    private static final String IMAGE =
            System.getProperty(
                    "test.postgres.image",
                    "postgres:16.6-alpine");

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>(
                    DockerImageName.parse(IMAGE))
                    .withDatabaseName("inventory_it")
                    .withUsername("inventory")
                    .withPassword("inventory");

    @Autowired
    InventoryRepository repository;

    @Autowired
    DataSource dataSource;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    Flyway flyway;

    @Test
    void usesRealPostgresMajor16NotH2()
            throws Exception {
        assertTrue(POSTGRES.isRunning());
        assertTrue(!IMAGE.isBlank());

        try (Connection connection =
                     dataSource.getConnection()) {
            assertEquals("PostgreSQL",
                    connection.getMetaData()
                            .getDatabaseProductName());
        }

        String value = jdbc.queryForObject(
                "SELECT current_setting('server_version_num')",
                String.class);

        assertNotNull(value);

        int versionNumber = Integer.parseInt(value);
        int major = versionNumber / 10000;

        assertEquals(16, major);
    }

    @Test
    void flywayMigrationIsAppliedBeforeJpaValidation() {
        assertNotNull(flyway.info().current());

        assertEquals(
                "1",
                flyway.info().current()
                        .getVersion().toString());

        Long count = jdbc.queryForObject(
                """
                SELECT count(*)
                  FROM information_schema.tables
                 WHERE table_schema = current_schema()
                   AND table_name = 'inventory_item'
                """,
                Long.class);

        assertEquals(Long.valueOf(1L), count);
    }

    @Test
    void postgresIlikeQueryRunsOnRealEngine() {
        repository.saveAllAndFlush(List.of(
                new InventoryItem(
                        "CAM-01", "Camera Body", 10000L),
                new InventoryItem(
                        "CAM-02", "camera Lens", 5000L),
                new InventoryItem(
                        "ACC-01", "Tripod", 2000L)));

        List<InventoryItem> found =
                repository.searchTitleIgnoreCase("cAmErA");

        assertEquals(
                List.of("CAM-01", "CAM-02"),
                found.stream()
                        .map(InventoryItem::getSku)
                        .toList());
    }

    @Test
    void realUniqueConstraintRejectsDuplicateSku() {
        repository.saveAndFlush(
                new InventoryItem(
                        "DUP-01", "First", 1000L));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new InventoryItem(
                                "DUP-01", "Second", 2000L)));

        // End method after SQL error; test transaction rolls back.
    }

    @Test
    void realCheckConstraintRejectsNegativePrice() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new InventoryItem(
                                "BAD-PRICE", "Invalid", -1L)));

        // Do not keep querying a transaction after violation.
    }
}
```

**This is a single class with 5 JUnit methods** and no HTTP server. It verifies **the JPA slice + PostgreSQL engine + Flyway schema**. That stays focused on image/version/reproducibility without pulling in out-of-scope controllers or services.

### 13.1. Why use `@ServiceConnection`?

In Spring Boot 3.3, `@ServiceConnection` on a typed `PostgreSQLContainer<?>` lets Boot supply `JdbcConnectionDetails` to the `DataSource`. Never hardcode container host/port because host ports are allocated dynamically.

If using `@DynamicPropertySource` instead, you must manually put `spring.datasource.url`/username/password from the container into `Environment`. Do not enable both configuration paths simultaneously without a specific reason, as it makes tracing the final bean/URI harder.

### 13.2. Why `@AutoConfigureTestDatabase(replace=NONE)`?

`@DataJpaTest` in Spring Boot 3.3 uses test database auto-configuration; default `Replace.ANY` can swap the `DataSource` for an embedded DB. `NONE` expresses the intent to "keep the real datasource provided by Testcontainers."

**Version caveat:** Spring Boot 3.4 introduced `Replace.NON_TEST` as the new default, but that enum constant does not exist in Boot 3.3. The example intentionally uses `NONE` to stay compatible with the chosen version.

`NONE` is not a security guard: if a datasource points to production, it will still keep that datasource. In the lab, connection details come from the PostgreSQL container, and CI must isolate production secrets and networks.

### 13.3. Why assert actual DB vendor and server version?

`usesRealPostgresMajor16NotH2` confirms:

- The container runtime started.
- The `DataSource` bean connects to a real engine reporting `PostgreSQL`.
- The SQL server returns `server_version_num` with major 16.

If H2 were used by accident, the metadata assertion fails. If you switch the image to PostgreSQL 17 in a "compatibility run," the major assertion also fails — that is **intentional** on a fixed baseline, whereas compatibility jobs should parameterize the expected major version to cover a multi-major range.

**Do not confuse:** major 16 does not prove the exact image digest; two PostgreSQL 16 patch images with different digests still report major 16. Image digests must be verified at the artifact/registry/container runtime layer separately.

### 13.4. Which repeatability factor does Flyway verify?

`flywayMigrationIsAppliedBeforeJpaValidation` asserts that migration V1 executed and created the table. Combined with `ddl-auto=validate`, if entity mappings and schema diverge, the application context fails immediately on load.

Migrations give a consistent **starting schema** across CI runs. Still, V1 on an empty database does not replace testing "upgrading data from schema N-1" or migrations applied on production-like datasets.

### 13.5. Why test `ILIKE` rather than testing only in Java?

`postgresIlikeQueryRunsOnRealEngine` executes native PostgreSQL SQL `ILIKE`. Mockito could return any arbitrary list; this test makes PostgreSQL itself parse and run the query and JDBC/Hibernate map the rows.

Results are ordered because the SQL specifies `ORDER BY sku`. Avoid asserting ordering not guaranteed by the query contract.

### 13.6. `UNIQUE` and `CHECK` constraints are database behavior

The two negative tests do not use Bean Validation to simulate failures. Flyway DDL creates `UNIQUE` and `CHECK(price_cents >= 0)`; PostgreSQL itself must reject violating INSERTs.

With `GenerationType.IDENTITY`, Hibernate can run INSERT right inside `save` to retrieve the ID, so wrap **the whole `saveAndFlush` call inside the `assertThrows` lambda** instead of assuming errors only trigger on `flush()`.

After an SQL exception, the transaction/persistence context can no longer be used safely. The method ends and Spring TestContext rolls back; do not issue further queries in the same negative test after the exception.

## 14. Local and CI commands with an explicit image reference

### 14.1. Default run with the illustrative patch tag

With a Gradle Wrapper and Docker available:

```bash
./gradlew test
```

The test worker receives `test.postgres.image=postgres:16.6-alpine` from `build.gradle`. **Expected** result: 5 methods pass with PostgreSQL engine 16, Flyway V1, and the test schema. On a first run, pulling the image requires Docker Hub/registry access.

**Docker was not executed while authoring this text**. Do not present fabricated runtime logs, ports, or digests as measured output.

### 14.2. Pinning a different verified image reference

Linux/macOS:

```bash
./gradlew test \
  '-PtestPostgresImage=postgres:16.6-alpine'
```

Windows PowerShell:

```powershell
.\gradlew.bat test '-PtestPostgresImage=postgres:16.6-alpine'
```

This is still a patch tag pin, **not yet an immutable digest**.

### 14.3. Running with a real digest read from a local image

After pulling the image and confirming `RepoDigests` is non-empty:

```bash
IMAGE_REF=$(docker image inspect \
  --format '{{index .RepoDigests 0}}' \
  postgres:16.6-alpine)

./gradlew test "-PtestPostgresImage=$IMAGE_REF"
```

When the command yields a repo-digest reference such as `docker.io/library/postgres@sha256:...`, `PinnedPostgresIntegrationTest` uses `DockerImageName.parse(IMAGE)` to pull/use that exact ref. **Never invent a `sha256`**; fetch it from Docker. In environments enforcing strict registry index/platform control, inspect with `docker buildx imagetools inspect` to confirm which digest type was chosen.

Windows PowerShell:

```powershell
$imageRef = docker image inspect --format '{{index .RepoDigests 0}}' postgres:16.6-alpine
.\gradlew.bat test "-PtestPostgresImage=$imageRef"
```

**Warning:** `RepoDigests` can hold multiple entries or be empty; for locally built images without a pulled registry digest, never treat `.Id` as equivalent. Verify output and policy before use in release gates.

### 14.4. Commands to verify PostgreSQL version after container startup

In the Java test, `current_setting('server_version_num')` is already asserted as major 16. Additional observations (optional, not required in the runnable suite):

```sql
SELECT current_setting('server_version');
SELECT current_setting('server_version_num');
SELECT current_setting('TimeZone');
SHOW server_encoding;
```

Actual outputs depend on image, platform, runtime, and configuration. When a business contract requires a specific timezone or encoding, configure and assert it explicitly rather than seeing "PostgreSQL started" in logs and assuming all environment defaults match.

## 15. Three things that stay "pinned" yet can still change results

### 15.1. Database schema

With the exact same PostgreSQL digest, changing a Flyway migration creates a different schema. Repeatability requires:

- Versioned migration scripts in Git.
- Flyway version aligned with the Boot BOM.
- Consistent Flyway locations, placeholders, and baseline config.
- Hibernate `validate` instead of auto-generating schemas when migrations are the target.
- Never pointing to a shared database holding leftover state from a previous run.

### 15.2. Fixtures and data

Tests using `Instant.now()`, uncontrolled random UUIDs, or fixed waits can flake even if the image never changes. Prefer:

- Fixtures with clear business keys, independent of method order.
- `Clock.fixed(...)` / fixed timestamps when wall-clock time is not under test.
- Avoiding assertions that identity sequences always equal 1.
- Both positive and negative test data.
- Isolated databases / test-managed transaction rollbacks where appropriate.
- Dedicated cleanup for committed writes from server threads or `REQUIRES_NEW` transactions.

In the lab, each `@DataJpaTest` method gets a transaction and default rollback; Flyway runs before tests. Both negative tests end right after the DB exception without querying the broken transaction.

### 15.3. Host/container runtime

With the exact same digest, the following can still differ:

- Docker/Podman/compatible runtime version.
- Linux kernel and filesystem driver.
- CPU architecture and host resources.
- CI container nesting / remote daemon networking.
- DNS/registry mirrors and proxies.
- Locale/timezone.
- CPU/memory pressure affecting timing.
- Parallel test execution and context/container lifecycles.

**Image pinning is necessary for some goals, not sufficient for 100% test repeatability.** When flakes happen, compare environment metadata and test boundaries rather than immediately blaming the image digest.

## 16. Why cache, reuse, and state break repeatability

### 16.1. Image cache vs container data state

Image cache is the pulled layers and manifests. Container data is the files, database rows, and queues created at runtime. Two container runs from **the same image digest** can yield different outcomes if data/volume initialization differs or tests reuse an older container.

### 16.2. Reusable containers

Testcontainers has a container reuse mechanism (opt-in/experimental depending on version). While speeding up local dev, it introduces leftover-state hazards across runs:

- Residual PostgreSQL rows, sequences, and migration history.
- Redis keys and unexpired TTLs.
- Old Kafka topics and offsets.
- Existing MongoDB collections and indexes.
- Cleanup colliding with another test sharing the container.

**Never enable reuse on CI release gates by default** without a verified isolation/reset strategy. A test connecting to a still-running container **does not prove** it booted from the newly pinned image digest.

### 16.3. Spring TestContext cache and `@Container` lifecycle

A static `@Container` under the JUnit extension usually lives per **test class**. Spring TestContext can cache `ApplicationContext` longer, even across classes. If a cached context keeps a datasource pointing to a stopped container, subsequent classes hit connection errors or non-deterministic failures.

With multiple integration classes sharing a DB:

- Use a Spring-managed container bean tied to context lifetime when supported by Boot and fitting the design.
- Or use a JVM-scoped singleton container pattern with consistent cleanup.
- Never combine a singleton container with JUnit `@Container` if the extension will stop it at the end of the class.
- When class-level isolation is needed, spin up separate contexts/containers or separate databases/schemas.
- `@DirtiesContext` is not a rollback or a default fix for every lifecycle issue.

The lab keeps a single PostgreSQL JUnit class to avoid this complexity.

### 16.4. Random mapped ports are a feature, not a lack of repeatability

Testcontainers maps container port 5432 to a **dynamic host port** to prevent collisions. Repeatability does not require a fixed host port; it requires **the app to consume the runtime-supplied URL** and assertions never to depend on a fixed port number.

Keep **contract** elements stable; do not force infrastructure details meant to be dynamically allocated.

## 17. CI policy: pin digests in PR gates, upgrade through review

A controlled workflow:

```text
Developer/Dependency update proposes new image
           |
           v
Check publisher, registry, version, OS, arch support
           |
           v
Resolve actual digest from trusted registry
           |
           v
Scan vulnerabilities, license/provenance/signature
           |
           v
Update approved image reference in CI config/lock
           |
           v
Run unit + slice + Testcontainers integration tests
           |
           v
Check SQL migrations, error behavior, performance risks
           |
           v
Review/merge, record old->new image digest
           |
           v
Observe downstream CI and release results
```

When a security advisory hits, never keep an old digest forever just because "tests still pass." Open a patch update PR, verify compatibility, and ship the new digest. If regressions appear, you can revert to the prior digest to investigate **in a test environment**, weighing the security impact of rolling back.

### 17.1. A repository-level image control manifest

Maintain a policy table in README or an organization-managed configuration file:

| Service | Target version | Locked image reference | Platform | Last reviewed |
| --- | --- | --- | --- | --- |
| PostgreSQL | Approved 16.x | Registry repo + verified digest | linux/amd64 | Review date |
| Redis | Approved 7.x | Registry repo + verified digest | linux/amd64 | Review date |
| Kafka | App-supported line | Vendor image + verified digest | linux/amd64 | Review date |

These placeholders are a **governance template**, not a filled manifest. Never invent a fake "sha256" string just to make the table look complete.

### 17.2. Pin vs matrix

If the product supports PostgreSQL 15 and 16:

- **Baseline PR gate:** one approved PostgreSQL 16 digest, run on every PR.
- **Compatibility matrix:** run the same suite against PostgreSQL 15 and 16, adjusting expected major per job or asserting the supported range.
- **Upgrade canary:** run candidate newer image versions, potentially non-blocking while raising alerts.
- **Release gate:** verify image/DB version/migrations matching the deployment target.

Never run a single test asserting major 16 and claim support for majors 15 and 17. Evidence must come from real runs against each engine.

### 17.3. The "digest vanished from registry" problem

An immutable digest **does not guarantee the registry retains the artifact indefinitely**. Registry retention/GC can purge manifests or deny pulls, private mirrors can fall out of sync, or credentials can expire.

To rerun builds months later:

- Establish an artifact retention policy for approved images.
- Mirror/replicate images into a controlled internal registry.
- Save lock manifests and provenance metadata.
- Test pullability/availability in CI.
- For long-term audits, store digest + source + SBOM/attestation + platform.

That is the difference between **content identity** and **artifact availability**.

## 18. Choosing when to pull: PRs, nightlies, and incident debugging

| Job | Reference | Recommended pull policy | Goal |
| --- | --- | --- | --- |
| PR gate | Verified digest | Cache-friendly | Stability, speed |
| Release verification | Approved digest | Controlled cache/registry mirror | Traceable exact artifact |
| Nightly patch compatibility | Reviewed major/patch moving tag | Re-resolve/pull per policy | Catch upstream drift |
| Incident reproduction | Digest from failing run | Pull exact prior digest if still available | Reproduce binary |
| Security patch update | Candidate new digest | Pull candidate | Check fixes + regressions |
| Local exploratory | Intentional patch tag | Usually cached | Fast learning, no byte-identical claim |

Running a nightly "latest image" job is pointless if the pipeline records only the tag without logging the resolved digest; afterward you will not know which image the canary actually saw.

### 18.1. Failure attribution

When a test suddenly fails:

1. Did the Git revision change?
2. Did the requested image ref change?
3. Did the resolved image digest change?
4. Did the platform/architecture change?
5. Did the server version inside the container change?
6. Did the Gradle dependency lock/BOM/JDK change?
7. Did migrations/fixtures/test configuration change?
8. Did container reuse/local cache leave state behind?
9. Was there a registry pull or network failure?
10. Did the test fail at startup, SQL execution, schema validation, or assertion?

This checklist prevents bad "fixes" like bumping timeouts indefinitely or loosening test assertions to fit a new image without knowing why it broke.

## 19. Common troubleshooting table

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| Cold-cache CI fails, local passes | Mutable tag resolved differently | Log actual digest and pin approved digest |
| Tag `latest` changes major | Upstream released a new version | Pin supported major/patch/digest |
| Patch pinned yet digest differs | Publisher rebuilt/republished tag | Switch to a verified digest |
| Pull `manifest unknown` | Wrong tag/digest or purged from registry | Inspect registry and retention policy |
| `no matching manifest for linux/arm64` | Image lacks platform support | Choose a multi-platform image or matching CI arch |
| `pull access denied` | Private registry auth/policy | Check credentials/mirror |
| Container image incompatible with module | Custom mirror differs in family/entrypoint | Pick the right image; mark compatible only when true |
| `Could not find a valid Docker environment` | Container runtime missing | Configure Docker/socket/remote runtime |
| Container startup timeout | Wrong readiness wait, slow image init | Module wait strategy, logs, resources |
| Local runs stale image | Cache + mutable tag | Pull intentionally or pin digest |
| Same image digest, unexpected server version | Different index/arch/entrypoint or wrong server | Assert DB vendor/version, inspect runtime |
| H2 passes, PostgreSQL native SQL fails | Wrong engine in tests or dialect mismatch | `Replace.NONE`/metadata assertion |
| Flyway PostgreSQL unsupported | Missing `flyway-database-postgresql` | Add DB-specific module per BOM |
| Hibernate validation fails | Migration/schema and entity out of sync | Compare migration SQL and column types |
| Unique test does not fail | Index/constraint not created or wrong DB | Assert schema/migration/engine |
| Same digest yields different test results | Test data, timezone, arch, deps, concurrency | Audit reproducibility matrix |
| Passes alone, fails in suite | Shared DB/context/cache/cleanup | Isolate state, fix lifecycle |
| Tests skipped while build stays green | Conditional tags/filters/CI tasks | Report executed vs skipped counts |
| Pinned image has a CVE | Digest frozen too long | Security update workflow, not blind `latest` |
| Docker local image ID differs from digest | Comparing two different hash types | Separate config ID from registry manifest/index digest |
| Container running yet wrong DB hit | Wrong DataSource/service connection | Query JDBC vendor/server/database metadata |

### 19.1. Failing before tests even start

`Could not find a valid Docker environment`, `manifest unknown`, and `pull access denied` occur at the infrastructure layer. They do **not** prove a JPA query is wrong. Inspect container/registry logs, the exact requested image ref, and the platform before touching application code.

### 19.2. PostgreSQL started yet queries fail

Check in order:

- Does the `DataSource` point to the right container?
- Did Flyway migrations run and build the right schema?
- Does Hibernate `validate` pass?
- Are the native `ILIKE` query, column names, and parameter bindings right?
- Were constraints and indexes created?
- Which transaction is active or rolling back?
- Are JDBC driver and server versions compatible?

**Never** work around SQL errors by letting tests run on H2 and claiming the image is fine.

## 20. Security: digest pinning does not equal trust

A valid digest only proves content matches its hash. It **does not prove**:

- The image was built by an approved publisher.
- The image is free of malware.
- All CVEs have been patched.
- Base image and transitive OS packages are safe.
- The registry/mirror has legitimate distribution rights.
- The image contains no embedded secrets.
- Build provenance and SBOM are valid.

Appropriate controls per organization:

- Registry allowlists and signed image verification.
- Software Bill of Materials (SBOM).
- Vulnerability scanning, exception policies, and expiry dates.
- Attestation/provenance verification (e.g., Sigstore/Cosign where approved).
- Pinned digests in a reviewable lock manifest.
- Scheduled patch reviews.
- Never grant production secrets/networks to test runners.
- Restrict Docker socket/daemon permissions.
- Clean up volumes, test data, and logs with appropriate retention.

If a mirrored image is rebuilt, its **digest changes** even when the server version remains identical. That is a new artifact requiring policy review.

## 21. Other parts that must be stabilized for trustworthy repeatability

### 21.1. Timezone and locale

Even with the exact same PostgreSQL binary, differing `SHOW TIME ZONE`, `LC_COLLATE`/collation, ICU, and JVM default timezones can alter date/time behavior, sorting, and case-insensitive search. Best practices:

- Define clear time contracts: `Instant` vs `OffsetDateTime` vs `LocalDate`.
- Use fixed timestamps in fixtures.
- Set and assert timezones where behavior depends on them.
- For collation-sensitive sorting, match the production variant/locale or run a dedicated integration test.
- Never call `System.setDefault(TimeZone...)` recklessly across parallel tests.

### 21.2. Clock and randomness

`Instant.now()`, unseeded UUIDs/randomness, and async retries can cause flakiness independent of the image digest. Use an injectable `Clock`, synthetic business keys, and deterministic seeds where appropriate; if randomness itself is under test, log the random seed for reproduction.

### 21.3. Transactions and isolation

`@DataJpaTest` normally rolls back each method. However, services running on separate server threads, `REQUIRES_NEW`, async writers, or startup migrations can commit outside the test transaction.

The same image does not ensure clean state if tests commit side effects. Use dedicated containers/databases or scoped cleanup, never calling `deleteAll()` on production or shared DBs.

### 21.4. Ready state

A started container process does not mean the service is ready. Testcontainers modules supply readiness logic, yet migrations and application startup may need additional readiness checks when depended upon.

Do not replace wait strategies with a fixed `Thread.sleep(5000)` to paper over flakes. For services like Kafka or Elasticsearch, readiness can involve multiple stages.

### 21.5. Parallel execution

Two test classes wiping tables/queues/keys in the same database container will interfere with one another. Use per-test databases/schemas, isolated prefixes, or serialize tests touching shared mutable state.

### 21.6. Secondary images

Do not overlook images for the resource reaper, sidecars, emulators, or migration jobs. A "DB image lock" is not yet a complete **test infrastructure image lock**.

## 22. Compatibility tests vs reproducibility tests

A **reproducibility test** asks: "Given identical code, approved image artifact, and fixtures/config, is a rerun consistent?"

A **compatibility test** asks: "Does the code work across newer/older versions and variants?"

The two call for different setups:

| Goal | Execution strategy |
| --- | --- |
| Reproducible PR gate | Single verified image digest, locked dependency set |
| PostgreSQL major compatibility | 15/16/17 matrix using approved digests |
| Distro compatibility | Alpine and Debian variants as required |
| ARM/AMD compatibility | Architecture matrix or multi-platform CI fleet |
| Early security patch warning | Nightly candidate image digest |
| Migration upgrade path | Starting N-1 schema/data snapshots, applying N migrations |
| Performance | Representative workload/data/architecture/limits |

Never run a compatibility matrix on mutable tags and call the whole suite fully reproducible. Moving targets can be used to **detect drift**, provided each run logs its exact resolved digest for diagnostics and retesting.

## 23. Example digest-upgrade workflow in a pull request

Suppose a team runs on approved PostgreSQL digest D1 and a patched release D2 becomes available:

1. A registry update bot/developer proposes D2, noting upstream release notes.
2. Verify publisher, signatures/attestations, SBOM, and CVEs.
3. Confirm D2 matches the target PostgreSQL major version and platforms.
4. Run `docker buildx imagetools inspect` to obtain index/platform digests.
5. Update the lock manifest/CI image config — **never weaken test oracles to hide failures**.
6. Run `PinnedPostgresIntegrationTest`: vendor, major version, Flyway, native SQL, unique/`CHECK` constraints.
7. Run additional migration/backward-compatibility tests if DB version or schema changed.
8. Review the D1→D2 diff and record digest, date, and owner.
9. Merge into the default branch so PR/release gates adopt D2.
10. If D2 fails, file a clear issue and either fix the app/migration or hold off on upgrading instead of removing the pin.

**Changing a digest is a dependency update involving compatibility and security review**, not just editing a string.

### 23.1. Checking impact on schemas and extensions

If the app depends on `pg_trgm`, ICU collations, PostGIS, or TimescaleDB:

- Official PostgreSQL images may omit third-party extensions.
- Choose an image bundling the exact extensions and dependency versions required.
- Test migrations on that exact image/extension combination.
- Record provenance/digest for custom images.
- Never say "the PostgreSQL major version matches, so extensions probably match too."

### 23.2. When an internal registry is required

Mirrored or air-gapped CI can host approved images in a private registry. Track the mapping upstream digest → internal digest to know whether an artifact was copied verbatim or rebuilt. A newly mirrored image is not automatically equivalent to upstream merely because it shares a tag.

## 24. Hands-on exercises

### Exercise 1 — Observing a mutable tag

On a study machine with Docker, run `docker pull postgres:16.6-alpine` and inspect `RepoDigests`. Explain why even a specific patch tag still needs a digest for exact binary reproducibility.

### Exercise 2 — Tag vs digest

Run `docker buildx imagetools inspect` on the chosen PostgreSQL tag, recording the top-level digest and platform manifests. Distinguish when to use the index digest vs an architecture manifest digest.

### Exercise 3 — Run the lab with the patch tag

Run `./gradlew test`, noting server major/version and migration V1. Do not claim full binary reproducibility when using only the default patch tag.

### Exercise 4 — Run the lab with a verified digest

Pull the image, extract `RepoDigests`, and pass `-PtestPostgresImage=<verified-image-reference>` to Gradle (syntax placeholder to be filled with your real value). If a digest does not exist or lacks platform support, tests must fail at image pull rather than falling back to `latest`.

### Exercise 5 — Controlled major change

Run the lab against a PostgreSQL 17 candidate image. `usesRealPostgresMajor16NotH2` is expected to fail on the major-version assertion. That shows the **baseline pin** is active. To implement a compatibility matrix, parameterize the expected major version per job and verify migrations/queries on both.

### Exercise 6 — Remove the Flyway PostgreSQL module

On a sandbox branch, temporarily remove `runtimeOnly 'org.flywaydb:flyway-database-postgresql'`, run the lab, and read the root cause regarding Flyway/driver support on Flyway 10.x. Restore the dependency. Takeaway: the image version is not the entire dependency graph.

### Exercise 7 — Break a migration and see context failure

Rename column `price_cents` in the migration without updating the entity. Hibernate `ddl-auto=validate` will fail during context bootstrap. Revert it. Why can `create-drop` hide migration bugs in integration tests?

### Exercise 8 — Database-enforced constraint check

Remove `uk_inventory_item_sku` in a fresh migration on a test branch; the duplicate-key test stops exhibiting duplicate rejection. Revert it. Contrast a mocked repository with a real database enforcing constraints.

### Exercise 9 — Cache vs always pull

Compare a warm local image cache against a clean CI agent using a mutable tag and record resolved digests. Try `PullPolicy.alwaysPull()` in a sandbox test. Explain why always pull cannot replace a digest lock.

### Exercise 10 — ARM vs AMD

Inspect the `linux/arm64` and `linux/amd64` manifests in an image index. If a team mixes Apple Silicon and `amd64` CI, how do you define "same image"? Record top-level digest, platform digest, and actual server version.

### Exercise 11 — Local registry mirror

Design an image name substitution policy for internal CI, using `asCompatibleSubstituteFor("postgres")` only when the mirror image is genuinely compatible. Log the mapping from requested ref to resolved repo-digest.

### Exercise 12 — Security update drill

Prepare a PR upgrading image digest D1 to D2 with changelog, CVE scan, sign-off, compatibility tests, and a rollback plan. Never skip regression tests merely because a scanner shows fewer CVEs on the new image.

### Exercise 13 — Catching leftover test state

Enable container reuse in a controlled sandbox, run a test committing data, rerun, and observe leftover state. Disable reuse, switch to proper ephemeral databases/resets, and explain why test results changed even though the image digest stayed identical.

### Exercise 14 — Reproducibility matrix

Compare two CI runs across: Git SHA, requested image, resolved repo digest, platform, server version, JDK/Gradle, Flyway version, migration checksum, timezone, and executed test count. Highlight which source of variance explains any difference.

## 25. Pre-merge review checklist

- [ ] Service/image chosen is a real engine or emulator **matching the test objective**.
- [ ] Image publisher, registry, distro, and architecture were verified.
- [ ] `latest` is not used on critical regression gates.
- [ ] Understood that patch tags remain mutable.
- [ ] Where artifact reproducibility is needed, a verified `repo@digest` is used.
- [ ] Known whether the digest is a manifest/index or per-platform manifest.
- [ ] Local image config ID is not confused with registry manifest digest.
- [ ] Testcontainers module supports the chosen image type and version.
- [ ] When using a mirror, image compatibility and provenance are verified.
- [ ] Image pull policy/caching matches the CI job type.
- [ ] A workflow exists to update digests when security fixes arrive.
- [ ] Digests are not left frozen indefinitely just because tests pass.
- [ ] Java 17/Gradle/Spring Boot BOM/Testcontainers/JDBC/Flyway dependencies are controlled.
- [ ] Schema migrations and fixture data are versioned/initialized intentionally.
- [ ] Hibernate `create-drop` is not hiding SQL migrations that need testing.
- [ ] Tests assert engine/vendor/server major version rather than only non-null container beans.
- [ ] At least one real database behavior is verified: native SQL, constraint, index, or transaction.
- [ ] Tests do not assume they run against the container if the DataSource could be replaced.
- [ ] No hardcoded host mapped ports or production credentials exist.
- [ ] Test isolation/cleanup never touches production or staging data.
- [ ] Container reuse is not assumed to yield a clean database.
- [ ] Context caching and `@Container` lifecycle are managed properly.
- [ ] Production topology/TLS/networking are not inferred from a local container alone.
- [ ] CI reports executed vs skipped tests transparently.
- [ ] Image/digest/platform/server-version metadata is retained sufficiently for debugging.
- [ ] No fabricated digests or claims of running Docker when not executed.

## 26. Summary and decision flow

```text
Want to test a dependency with Testcontainers?
               |
               v
Do you need real service engine behavior?
       |                       |
      No                      Yes
       |                       |
  Controlled unit/        Choose right vendor, major,
  mock/slice tests        distro, extensions, platform
                               |
                               v
                    What is the test goal?
                       |           |
             PR/release gate    Compatibility watch
                       |           |
             Approved digest   Reviewed moving candidate
             + locked deps     + log resolved digest
                       |           |
                       +-----+-----+
                             |
                             v
               Isolate data, run migrations,
               explicit readiness, fixed fixtures
                             |
                             v
               Assert service version + behavior,
               record image/arch/runtime metadata
                             |
                             v
               Review security/update policy
```

**Core lesson:** Picking the right image ensures tests exercise a service with **the behavior you need to prove**. Pinning a digest locks **artifact content** instead of depending on a mutable tag. Yet repeatability of the whole integration test also hinges on Java/build dependencies, schema migrations, fixtures, timezone/platform, state isolation, startup, and the CI runtime. **Pin deliberately, record execution conditions, and upgrade with verification**, rather than dropping `:latest` or a bare SHA-256 into code and assuming everything is reproducible.

## 27. Official documentation

- Docker — Pull an image by digest, tag mutability, and update caveats: https://docs.docker.com/reference/cli/docker/image/pull/
- Docker — Inspect image and RepoDigests: https://docs.docker.com/reference/cli/docker/image/inspect/
- Docker — Buildx imagetools inspect: https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/
- Docker — Multi-platform images and image index: https://docs.docker.com/build/building/multi-platform/
- Docker — Image content and provenance overview: https://docs.docker.com/learn/content/prove-where-your-image-came-from/
- Testcontainers Java — Image name substitution/mirrors: https://java.testcontainers.org/features/image_name_substitution/
- Testcontainers Java — Image pull policies: https://java.testcontainers.org/features/advanced_options/
- Testcontainers Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- Testcontainers Java — JUnit Jupiter integration: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers Java — Container lifecycle and reuse: https://java.testcontainers.org/features/reuse/
- Spring Boot 3.3 — Testcontainers and `@ServiceConnection`: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Boot 3.3 — `@DataJpaTest`: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — `@AutoConfigureTestDatabase`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html
- Spring Data JPA — Repositories/query methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Flyway — PostgreSQL database-specific module: https://documentation.red-gate.com/flyway/reference/database-driver-reference/postgresql-database
- Gradle — Dependency locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- PostgreSQL — `ILIKE` and pattern matching: https://www.postgresql.org/docs/current/functions-matching.html
- JUnit Jupiter — Test lifecycle and assertions: https://docs.junit.org/current/user-guide/
