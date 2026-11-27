# Stub Artifact Does Not Exist, Wrong Classifier, or Wrong Version

## Learning Objectives

**Spring Cloud Contract** lets producers and consumers define HTTP or messaging behavior using **Groovy/YAML DSL**. The producer generates tests to verify its implementation and then packages a **stub artifact**. The consumer uses **Stub Runner** to run client tests and integrates with **CI** to detect incompatible API changes.

In practice, the error message **“Stub not found”** can refer to four different failures:

1. **Artifact does not exist yet** in the repository where the consumer is looking.
2. **Artifact exists under different coordinates**: `groupId`, `artifactId`, `version`, `classifier`, or file type.
3. **JAR downloaded yet lacks stubs**: missing HTTP mappings or message definitions.
4. **Stub runs yet request does not match**: consumer calls the wrong port, method, path, header, or body, so WireMock returns 404.

This lesson belongs to the **Troubleshooting** chapter and focuses on missing stub artifacts, wrong classifiers, or wrong versions. After this lesson, you will be able to:

- Read Stub Runner's `group:artifact:version:classifier:port` ID accurately.
- Distinguish contract definitions JARs, producer application JARs, and producer `:stubs` JARs.
- Verify whether the producer generated tests, ran tests, built stubs, and published them.
- Cross-check consumer coordinates against actual artifacts in the Maven repository.
- Diagnose `LOCAL`, `REMOTE`, and `CLASSPATH` modes, repository URLs, permissions, and caches.
- Inspect JAR contents, `mappings`, and `__files` instead of relying on filenames.
- Separate artifact resolution errors from WireMock unmatched 404s.
- Build CI quality gates and reproducible evidence-backed error reports.

> **First rule:** verify in order: **artifact exists → coordinates match → JAR contains stubs → Stub Runner starts → request matches mapping**. Never tweak JSON assertions when the bug is in the classifier or repository.

## 1. Running Scenario: Inventory and Checkout

**Inventory Service** exposes:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

Agreed response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-101","available":true,"quantity":8}
~~~

**Checkout Service** needs to test its HTTP client without starting all of Inventory. It loads stubs using Stub Runner.

Suppose the relevant artifacts are:

| Artifact | Sample Coordinates | Role |
|---|---|---|
| **Contract definitions** | `com.example.contracts:inventory-contracts:1.6.0` | Holds Groovy/YAML DSL, possibly published from a separate contracts repo |
| **Producer application** | `com.example:inventory-producer:2.3.0` | Executable JAR of the real Inventory app |
| **Producer stub** | `com.example:inventory-producer:2.3.0:stubs` | JAR of mappings and fixtures for consumer tests |

Corresponding files might be:

~~~text
inventory-contracts-1.6.0.jar
inventory-producer-2.3.0.jar
inventory-producer-2.3.0-stubs.jar
~~~

**Only the last file is the producer stub JAR** in this example. An application JAR with the same group/artifact/version and **no classifier** cannot substitute for the stub JAR.

### Stub Runner in the Consumer

JUnit 5 + Spring Boot example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.3.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/verified-stubs"
)
class CheckoutInventoryClientTest {

    @StubRunnerPort("inventory-producer")
    int inventoryStubPort;

    @Test
    void usesInventoryStub() {
        // Configure Checkout's real HTTP client:
        // http://localhost:<inventoryStubPort>
        // Send GET /api/inventory/SKU-101 and assert response.
    }
}
~~~

This is a **configuration skeleton**, not a full test; a real project needs dependencies, the HTTP client, and assertions. `example.invalid` is a nonexistent placeholder URL.

If the consumer fails immediately when the Spring test context boots because it cannot resolve `inventory-producer:2.3.0:stubs`, editing JSONPath inside the test method will not fix the root cause.

## 2. Decoding the Stub Runner ID

A standard ID takes the form:

~~~text
groupId:artifactId:version:classifier:port
~~~

Example:

~~~text
com.example:inventory-producer:2.3.0:stubs:0
    |            |          |    |   |
    |            |          |    |   +-- Port=0: run stub on dynamic port
    |            |          |    +------ Classifier: stubs
    |            |          +----------- Producer stub version
    |            +---------------------- Maven artifactId
    +----------------------------------- Maven groupId
~~~

| Component | Example | Common Mistake |
|---|---|---|
| `groupId` | `com.example` | Confused with contract definitions group |
| `artifactId` | `inventory-producer` | Confused display service name with Maven artifactId |
| `version` | `2.3.0` | Uses an unpublished new version or a stale version |
| `classifier` | `stubs` | Omitting classifier makes resolver look for main JAR or another artifact |
| `port` | `0` | Consumer mistakes dynamic port for literal `localhost:0` |

**Watch out for differing coordinate formats:**

- Stub Runner ID: `group:artifact:version:classifier:port`.
- Maven dependency plugin CLI: `group:artifact:version:packaging:classifier`, e.g., `com.example:inventory-producer:2.3.0:jar:stubs`.

Do not pass `...:stubs:0` straight into a Maven dependency command expecting Maven to understand `0` as a port.

### Using Dynamic Ports Properly

`:0` tells Stub Runner to pick an available port. The client must retrieve the runtime port via `@StubRunnerPort` or `StubFinder`, rather than hard-coding `http://localhost:0` or `localhost:8080`.

If the consumer reports `Connection refused` because it hit the wrong port, that is a **client routing error**, not evidence that the artifact does not exist.

### Should Dynamic Versions Be Used?

Resolvers/version mechanisms may support dynamic versions (such as `+`). However, CI requires reproducibility, so prefer **explicit versions** and, when needed, record JAR digests. Never switch to “latest” just to dodge a resolution error.

## 3. Decision Tree for Classifying Failures

~~~mermaid
flowchart TD
    A["Consumer reports stub not found"] --> B{"Did artifact resolve?"}
    B -->|No| C["Verify group/artifact/version/classifier"]
    C --> D["Check repository root, mode, auth, publish"]
    B -->|Yes| E{"Does JAR contain needed mappings?"}
    E -->|No| F["Check packaging, META-INF, __files, filters"]
    E -->|Yes| G{"Did Stub Runner bind a port?"}
    G -->|No| H["Check bootstrap/config/port conflicts"]
    G -->|Yes| I{"Does request match WireMock mapping?"}
    I -->|No| J["Check URL, method, query, headers, body"]
    I -->|Yes| K{"Do consumer assertions PASS?"}
    K -->|No| L["Check contract expectations and version"]
    K -->|Yes| M["Record version/digest + reports"]
~~~

| Symptom | First Layer to Suspect | What Not to Do Yet |
|---|---|---|
| `Could not resolve artifact` | Repository/coordinates/publish | Edit response JSONPath |
| HTTP 401/403 from repository | Credentials/read permissions | Randomly change classifier |
| HTTP 404 downloading `-stubs.jar` | Missing file/coordinates | Increase HTTP client timeout |
| JAR downloaded yet `no mappings` | Generation/packaging | Assume Stub Runner is serving |
| Stub Runner fails to bind port | Startup/configuration | Edit contract body |
| WireMock HTTP 404 after stub starts | Unmatched request | Assume artifact does not exist |
| Consumer connects to wrong port | Client base URL | Republish JAR |
| Stub mapping matches yet response assertion fails | DSL, implementation, or stale artifact | Use `latest` to hunt for a green build |

**Two different 404s:** an HTTP 404 when the resolver tries to download a file from a Maven repository, and an HTTP 404 returned by WireMock when a request matches no mapping. Always note **which URL returned 404**.

## 4. Where Are Artifacts Stored in a Maven Repository?

Maven-compatible repositories lay out artifacts as:

~~~text
<repository-root>/
  <group-id-as-folders>/
    <artifact-id>/
      <version>/
        <artifact-id>-<version>-<classifier>.<extension>
~~~

Example:

~~~text
https://repo.example.invalid/repository/verified-stubs/
└── com/
    └── example/
        └── inventory-producer/
            └── 2.3.0/
                ├── inventory-producer-2.3.0.pom
                ├── inventory-producer-2.3.0.jar
                └── inventory-producer-2.3.0-stubs.jar
~~~

Relative path to the stub JAR:

~~~text
com/example/inventory-producer/2.3.0/inventory-producer-2.3.0-stubs.jar
~~~

Stub Runner's `repositoryRoot` must point to the **repository root** `.../repository/verified-stubs`, not `.../2.3.0` or directly to the JAR file.

### Cross-Check Sequence

1. Does the ID requested by the consumer match group/artifact/version/classifier?
2. Does the target repository contain `*-stubs.jar`?
3. Does the repository have the POM/metadata required by the resolver?
4. Using CI credentials, is the download response 200, 401, 403, 404, or 5xx?
5. Is the downloaded file actually a JAR, or an HTML login page?
6. Does `jar tf` list this producer's mappings?
7. Which artifact/port do Stub Runner logs report as loaded and running?

### With SNAPSHOTs

Maven snapshots can be stored as **timestamped snapshots** with `maven-metadata.xml`—for instance, directory `2.3.1-SNAPSHOT` containing filenames with timestamps/build numbers.

Do not hand-construct a URL to `inventory-producer-2.3.1-SNAPSHOT-stubs.jar` and conclude it does not exist when the repository uses timestamped filenames. Use Maven/Stub Runner resolvers and inspect metadata/download logs.

## 5. Do Not Confuse Contract Definitions with Producer Stubs

Classic mistake:

~~~text
Producer fetches contract definitions:
  com.example.contracts:inventory-contracts:1.6.0

Consumer Stub Runner configures:
  com.example.contracts:inventory-contracts:1.6.0:stubs:0
~~~

**Wrong target:** the contract definitions JAR contains Groovy/YAML DSL for the **producer to generate tests**. The consumer needs the stub JAR from the **verified producer**, such as:

~~~text
Producer code:
  com.example:inventory-producer:2.3.0

Producer generated contract tests:
  PASS

Stub artifact:
  com.example:inventory-producer:2.3.0:stubs

Checkout Stub Runner ID:
  com.example:inventory-producer:2.3.0:stubs:0
~~~

No Spring Cloud Contract rule requires the contract JAR version `1.6.0` to equal the producer version `2.3.0`. CI should link contract revision, producer revision, and the verified stub artifact.

**Seeing a contract JAR in Nexus does not prove the producer published a stub JAR.**

## 6. The Producer Must Truly Generate and Publish Stubs

Chain to verify:

~~~text
Groovy/YAML DSL
    |
    v
Generate producer tests
    |
    v
Run against real producer implementation
    |
    v
PASS
    |
    v
Generate HTTP mappings / message definitions
    |
    v
Package stubs JAR (classifier stubs)
    |
    v
Install/publish to repository
~~~

Creating a file and uploading it to a repository are **two separate actions**.

### Maven Producer

For a Maven producer configured with the Spring Cloud Contract Maven plugin:

~~~bash
# Run verification per existing lifecycle and config.
./mvnw -B -ntp clean verify

# Install artifacts into local Maven repository per plugin attachment.
./mvnw -B -ntp install
~~~

Never use `-DskipTests` or `-Dmaven.test.skip=true` to force a stub build: if producer tests did not run, the artifact cannot be treated as verified.

If expected outputs are:

~~~text
target/inventory-producer-2.3.0.jar
target/inventory-producer-2.3.0-stubs.jar
~~~

yet only the main application JAR appears, check contract discovery, plugin configuration, stub generation, and **artifact attachment**. Exact filenames can vary by Maven `finalName`/plugin version.

### Gradle Producer

For a Gradle module with a modern Spring Cloud Contract plugin:

~~~bash
./gradlew :inventory-producer:tasks --all
./gradlew :inventory-producer:contractTest
./gradlew :inventory-producer:verifierStubsJar
~~~

Artifacts typically appear under:

~~~text
inventory-producer/build/libs/
~~~

`verifierStubsJar` mainly **creates/packages** the stub; it does not mean the artifact was published to the Maven repository the consumer uses. Configure publication/upload and inspect publish logs separately.

### Key Questions

- Did the producer discover the DSL properly and generate **non-zero tests**?
- Did generated producer tests execute and PASS, or were they skipped?
- Does the artifact carry classifier `stubs` in actual metadata/publication?
- Do logs confirm install/publish succeeded?
- Is the consumer requesting the exact published version or a different one?
- Was the artifact built from the **same revision** verified by producer tests?

**Do not start by editing the consumer if the producer has not published stubs yet.**


## 7. Open the Stub JAR to Verify Contents

Filename `inventory-producer-2.3.0-stubs.jar` **does not guarantee** it contains the right mappings. The archive may be empty, packaged with the wrong layout, or mistakenly hold application classes.

Use the JDK tool:

~~~bash
jar tf inventory-producer-2.3.0-stubs.jar
~~~

For an HTTP stub JAR following Spring Cloud Contract conventions, output may include:

~~~text
META-INF/
META-INF/MANIFEST.MF
META-INF/com.example/inventory-producer/2.3.0/
META-INF/com.example/inventory-producer/2.3.0/contracts/
META-INF/com.example/inventory-producer/2.3.0/mappings/
META-INF/com.example/inventory-producer/2.3.0/mappings/stockAvailable.json
~~~

This is an **illustrative layout**: plugin versions, paths, and consumer-specific settings can differ. Inspect the real JAR and Stub Runner logs in use.

### Signs of a JAR with Wrong Contents

~~~text
Downloaded:
  inventory-producer-2.3.0-stubs.jar

Archive:
  META-INF/MANIFEST.MF
  BOOT-INF/classes/application.properties
  BOOT-INF/lib/...
~~~

If the JAR looks like a Spring Boot fat JAR with no mappings/contract definitions, the pipeline may have **published the application JAR under classifier `stubs`**. Stub Runner cannot turn controller classes into WireMock stubs automatically.

Another JAR may contain `mappings` yet lack `GET /api/inventory/SKU-101` because:

- The contract DSL was not discovered by the generator.
- The producer did not configure the right Groovy/YAML DSL source.
- `contractsPath` or `includedFiles`/`ignoredFiles` excluded the file.
- The artifact belongs to another consumer when `stubs-per-consumer` is enabled.
- The artifact was packaged from an old revision.
- Mapping files were excluded from the JAR by copy/package settings.

**How to fix:** fix generation/packaging on the producer, verify generated contract tests, and publish a new artifact at the proper version; never manually inject an unverified JSON mapping into a published artifact.

### When Mappings Reference External Files

A WireMock mapping may use:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-101"
  },
  "response": {
    "status": 200,
    "bodyFileName": "stock-available.json",
    "headers": {
      "Content-Type": "application/json"
    }
  }
}
~~~

In that case, the stub artifact must include the matching body file under `__files` per WireMock and Spring Cloud Contract packaging conventions. If missing, the artifact resolves and the server starts, yet response requests fail at runtime.

**Do not infer from “mapping JSON exists” that external response files also exist.** Verify both mappings and referenced fixtures.

## 8. Wrong Classifier: Main JAR Exists, Stubs JAR Does Not

Typical scenario:

~~~text
Maven repository contains:
  inventory-producer-2.3.0.pom
  inventory-producer-2.3.0.jar

Maven repository DOES NOT contain:
  inventory-producer-2.3.0-stubs.jar
~~~

Consumer requests:

~~~text
com.example:inventory-producer:2.3.0:stubs:0
~~~

The artifact resolver cannot locate **classifier `stubs`** merely because the main JAR exists.

### Comparison Table

| File | Classifier | Is This the Artifact Consumer Needs? |
|---|---|---|
| `inventory-producer-2.3.0.jar` | None | No, it is the application artifact |
| `inventory-producer-2.3.0-stubs.jar` | `stubs` | **Yes**, for this Stub Runner convention |
| `inventory-producer-2.3.0-tests.jar` | `tests` | No, a test-classes JAR does not inherently hold stub mappings |
| `inventory-producer-2.3.0-sources.jar` | `sources` | No, source artifact |
| `inventory-contracts-1.6.0.jar` | None; different artifact | No, contract definition artifact |

**Classifier is part of artifact coordinates**, not an arbitrary filename suffix. Putting `-stubs` in a filename before manual upload will not create valid Maven metadata if the publisher attaches the artifact under different coordinates.

### Gradle: Wiring `verifierStubsJar` to a Publication

Illustrative `maven-publish` pattern for a Gradle producer with the Spring Cloud Contract plugin applied:

~~~groovy
plugins {
    id 'java'
    id 'maven-publish'
    // Spring Cloud Contract plugin and version must be configured
    // per your project's actual BOM/toolchain.
}

group = 'com.example'
version = '2.3.0'

publishing {
    publications {
        verifiedStubs(MavenPublication) {
            groupId = 'com.example'
            artifactId = 'inventory-producer'
            version = project.version.toString()

            artifact(tasks.named('verifierStubsJar'))
        }
    }
}
~~~

**This snippet is a publication example, not a complete `build.gradle`.** The `verifierStubsJar` task must exist and configure the right output classifier in your Spring Cloud Contract plugin version. `maven-publish` takes the artifact from the task, yet **still requires repository upload** and a release gate ensuring producer contract tests PASSED.

Do not assume a `publishVerifiedStubsPublicationToMavenLocal` task exists if no publication was created. Run `./gradlew tasks --all` and check actual task names.

### Maven: Does the Attached Artifact Have Classifier `stubs`?

In a Maven producer using the Spring Cloud Contract Maven plugin, check:

- Did the plugin run stub-generation goals in the lifecycle?
- Is the stub JAR **attached** with classifier `stubs`?
- Do `install`/`deploy` carry the attached artifact?
- Does any profile or parent POM disable the contract plugin?
- Did you verify the actual `target` directory and local/remote Maven repos?

If the main JAR publishes while the `stubs` JAR does not, the cause usually lies in **plugin goals, attached artifacts, or deploy/publish config**, not consumer read permissions.

### Do Not Fix by Emptying the Consumer Classifier

Dropping `stubs` so the resolver downloads the main JAR simply shifts the error to **no mappings found**. Fix **what gets published**, rather than lowering expectations on artifact type.

## 9. `LOCAL`: The JAR Must Actually Exist in the Maven Local Repository

Stub Runner `LOCAL` resolves artifacts from the Maven local repository of the environment executing the tests.

Example:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.3.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

With default Maven settings, the path may be:

~~~text
~/.m2/repository/com/example/inventory-producer/2.3.0/
  inventory-producer-2.3.0.pom
  inventory-producer-2.3.0.jar
  inventory-producer-2.3.0-stubs.jar
~~~

On Windows, the default local Maven repository typically sits under the user's home directory at `.m2/repository`. If Maven `settings.xml` overrides `localRepository`, the actual path will differ.

### Two Critical Questions

**Is having the JAR in `target/` or `build/libs/` enough?**

**No.** Producer build outputs do not automatically appear in the Maven local repository at the coordinates resolved by Stub Runner `LOCAL`.

**Is the consumer running on the same machine/container as the producer build?**

If the producer runs in job A and the consumer runs in job B with separate filesystems, job B's `LOCAL` **cannot see job A's Maven local**. Install/publish into the consumer's environment or use `REMOTE` with a shared accessible repository.

### Maven: Installing Stubs Locally

~~~bash
# In a producer configured so the plugin attaches stubs:
./mvnw -B -ntp clean install
~~~

After the command, **physically check for `-stubs.jar`** under the Maven local repository. If missing, inspect plugin attachment instead of assuming `install` always publishes stubs under every config.

### Gradle: Publish the Right Publication to Maven Local

Once `maven-publish` is configured with a stub publication:

~~~bash
./gradlew :inventory-producer:tasks --all

# Exact task name depends on the publication name in build.gradle:
./gradlew :inventory-producer:publishVerifiedStubsPublicationToMavenLocal
~~~

Then inspect files in Maven local and run the `LOCAL` consumer test.

**Distinction:** `mavenLocal()` inside a Gradle `repositories` block only tells Gradle it **can read** Maven local. It **never writes artifacts** to Maven local.

### Maven Local Cache Is Not an Absolute Source of Truth

A file in `~/.m2` can be:

- Stubs from an older commit with the same `SNAPSHOT` version.
- An artifact installed manually with the wrong classifier.
- An artifact published by another project to the same coordinates.
- A misnamed main JAR.
- Out-of-sync metadata.

Check filenames, JAR entries, version, and digest when needed before concluding the local copy is right.

## 10. `REMOTE`: `repositoryRoot` Must Point to the Right Source

`REMOTE` configuration:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.3.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/verified-stubs"
)
~~~

Starting from `repositoryRoot`, the resolver resolves Maven coordinates. This URL is **not**:

- The producer's production base URL like `https://inventory.example.invalid`.
- The HTTP endpoint the consumer client calls.
- A path to Groovy DSL files in Git.
- A direct link to `-stubs.jar`.
- The contract definitions repository URL, unless the organization intentionally hosts both artifact types there.

### Distinguish Registry HTTP Statuses

| Result | Common Meaning | How to Handle |
|---|---|---|
| **200** returns right JAR | File downloadable | Inspect contents, checksum, version |
| **200** returns HTML login page | Broken redirect/proxy auth | Check `Content-Type`, redirects, and auth |
| **401** | Unauthenticated or bad token | Check CI credentials |
| **403** | Authenticated yet lacks read access | Check repository ACL/tenant |
| **404** | Artifact/path absent or hidden by auth policy | Verify metadata, coordinates, and permissions |
| **429** | Registry rate-limited | Controlled retry; do not edit contracts |
| **5xx** | Repository/proxy/network error | Check server health and cache layer |
| **TLS/certificate error** | Wrong CA/proxy/truststore | Configure proper trust; never disable TLS validation |

Never commit tokens/passwords into `@AutoConfigureStubRunner`, YAML configs, or repository URLs. Use secret management and resolver/credential mechanisms supported by your Stub Runner version.

### One Maven Server Can Host Multiple Logical Repositories

For example, Artifactory/Nexus may have:

~~~text
repository/maven-releases/
repository/maven-snapshots/
repository/verified-stubs/
repository/contract-definitions/
~~~

The producer might publish stubs to `verified-stubs` while Checkout points at `maven-releases`. Two repos on the same host **do not share artifacts**.

Your diagnosis must record the **exact root URL the consumer actually used**, not just “the company Nexus.”

### Works for Developer Account, Fails in CI

Possible reasons:

- Developer has credentials in Maven settings; CI does not.
- Developer has VPN/internal DNS; CI runner sits on another network.
- Developer hits local Maven cache while assuming it is remote.
- CI encounters different proxy/certificate policies.
- Consumer pipeline injects the wrong `repositoryRoot` environment variable.
- CI requests a version not yet promoted to the published repository.

**How to verify:** test resolving the exact coordinates **in the same environment/identity** used by consumer CI, rather than extrapolating from a developer laptop.

## 11. `CLASSPATH`: Artifact Exists on the Test Runtime Classpath

Some Stub Runner setups support `CLASSPATH` mode, reading stubs from the test classpath instead of downloading via remote Maven every run.

Conceptual example:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.3.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.CLASSPATH
)
~~~

For this mode to work, stub artifacts/resources must **genuinely be on the test runtime classpath** in a structure recognized by your Stub Runner version.

Illustrative Maven test dependency:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>inventory-producer</artifactId>
    <version>2.3.0</version>
    <classifier>stubs</classifier>
    <type>jar</type>
    <scope>test</scope>
</dependency>
~~~

**Do not equate `CLASSPATH` with `LOCAL`.** A JAR sitting in `~/.m2` available to Maven does not prove it is on the runtime classpath. Inspect effective test dependencies and JAR entries.

Specific versions of `CLASSPATH` mode also follow conventions for scanning resources; consult docs for your plugin version. If an IDE run has a different test classpath from CI, outcomes can differ too.

### Choosing a Mode by Goal

| Mode | Primary Source | When to Use | Common Pitfall |
|---|---|---|---|
| `LOCAL` | Maven local repository | Multi-module dev integration, testing stubs before remote publish | Not installed or wrong `~/.m2` |
| `REMOTE` | Maven-compatible repository | Consumer CI/releases needing shared stub artifacts | Wrong URL, credentials, version, classifier |
| `CLASSPATH` | Test runtime classpath | Stubs declared in test dependencies/resources | JAR missing from classpath or wrong layout |

**These modes choose the source**, without changing the requirement that stubs must contain valid mappings/definitions.

## 12. Wrong Version: Producer and Consumer Are Not Using the Same Artifact

Example:

~~~text
Producer release:
  inventory-producer 2.3.1
  inventory-producer 2.3.1:stubs

Checkout consumer:
  ids = com.example:inventory-producer:2.3.0:stubs:0
~~~

Checkout may still PASS, yet it only proves compatibility with stub `2.3.0`. It **does not verify the `2.3.1` API**.

Another scenario:

~~~text
Checkout requests:
  inventory-producer:2.3.2:stubs

Repository contains:
  2.3.0:stubs
  2.3.1:stubs

Producer has not released:
  2.3.2:stubs
~~~

The “artifact not found” error is accurate: the consumer requests a **version that does not exist yet**.

### Causes of Version Drift

- Consumer bumped the constant before the producer published.
- Producer published only the new application version, omitting the `stubs` classifier.
- CI built a `-SNAPSHOT` candidate while the consumer requested a release version.
- Gradle `project.version` in a subproject differs from the root version.
- Maven parent POM sets a different `revision`/property than the published artifact.
- Git tag does not match the installed/deployed version.
- Maven/Gradle cache holds a stale artifact under a mutable version.
- Producer built from branch A and published from branch B.

### Diagnostic Rule

Do not compare only the string `2.3.0` inside `build.gradle`/`pom.xml`. Inspect the **actually published artifact**: coordinates, version, classifier, digest, publish timestamp, source revision, and test reports.

### SNAPSHOT vs. Release

- `2.3.1-SNAPSHOT` fits development, yet its bytes can change under the same logical version.
- `2.3.1` release must be immutable; never overwrite it “to fix an artifact” without bumping the version or following an approved rollback policy.
- Consumer CI compatibility gates should pin exact candidate versions/digests.
- With Maven snapshots, resolver metadata/caching can cause two runners to receive different bytes.

**Do not recommend “wipe caches on every machine” as a long-term fix.** Use proper versioning, immutability, and clear inputs/provenance.

## 13. `groupId`, `artifactId`, and `version` in Multi-Module Builds

In multi-module projects, a module name is not necessarily the Maven `artifactId`.

Gradle example:

~~~text
project root:
  :services:inventory
  :services:checkout

Maven publication configured:
  groupId = com.example.platform
  artifactId = inventory-api
  version = 3.0.0
~~~

If Checkout Stub Runner uses:

~~~text
com.example:inventory:3.0.0:stubs:0
~~~

the resolver searches for the **wrong group/artifact** even though `:services:inventory:verifierStubsJar` succeeded.

Correct coordinates per the illustrated publication:

~~~text
com.example.platform:inventory-api:3.0.0:stubs:0
~~~

### Where to Check?

**Maven:**

- `<groupId>` and `<artifactId>` in the effective POM.
- Parent POM and version properties, `revision`, profiles.
- Maven deploy/install logs showing attached stub artifacts.
- POM and artifact files actually published to the repository.

**Gradle:**

- `project.group` and `project.version` on the **subproject**.
- Whether `publishing.publications` overrides `groupId`/`artifactId`/`version`.
- What classifier/output `verifierStubsJar` produces.
- The exact publish task (which may differ from generic `publish`).
- The repository the publication actually uploads to.

### Service Name Does Not Determine Coordinates

An app may set `spring.application.name=inventory-service` while its `artifactId` is `inventory-api`. Stub Runner's resolver uses **artifact coordinates**, not Spring's application name.

`@StubRunnerPort` must also name the exact running stub ID/artifact. How the consumer reads the port and how Maven fetches the artifact are related steps, not substitutes for each other.

## 14. Right Artifact, Yet Mappings Are Filtered or Ambiguous

Sometimes the consumer downloads the exact `inventory-producer-2.3.0-stubs.jar`, yet startup reports no matching stubs. The cause can be **contents or filtering**, not the classifier itself.

### Contracts Placed Under the Wrong Source Path

Suppose the DSL actually sits in:

~~~text
shared-contracts.jar:
  com/example/inventory-producer/checkout/stockAvailable.groovy
~~~

yet the producer configures `contractsPath` as:

~~~text
com/example/contracts/shared-contracts
~~~

The producer downloads the contract definitions artifact cleanly yet discovers zero DSL files. As a result, the stub artifact is empty, missing mappings, or the pipeline generates no tests.

**How to fix:** align `contractsPath` with the path inside the contract JAR; enable fail-on-no-contracts per your plugin version and check test counts.

### Stubs Per Consumer

When using **stubs-per-consumer**, the artifact/Stub Runner organizes or filters mappings by consumer identity. A consumer with a mismatched name or folder will miss its mappings even though the JAR is non-empty.

Check:

1. Is `stubs-per-consumer` enabled on the producer?
2. What is the contract directory layout?
3. What `consumerName` does Stub Runner pass?
4. In which folder do generated mappings reside?
5. Is the mapping file for Checkout actually selected when Stub Runner starts?

Seeing `mappings/` exist is not enough; locate the **exact mapping for the interaction under test**.

### Multiple Mappings Matching the Same Conditions

If two mappings both match:

~~~text
GET /api/inventory/SKU-101
~~~

yet return different responses, ordering/priority affects which stub is served. This is **mapping ambiguity**, distinct from “artifact does not exist.”

For reliable tests, each scenario needs a distinguishing request matcher or explicit scenario/priority design, plus verification of runtime mappings.


## 15. Artifact Downloads, Yet Stub Runner Fails to Open a Port

This step happens after confirming the artifact and JAR contents are right. Stub Runner must still unpack/stage stub files and start the WireMock HTTP server or configure messaging stubs.

Common causes:

- Fixed port already in use by another process.
- Stub Runner configuration is not loaded into the Spring test context.
- `@AutoConfigureStubRunner` is missing from the active test/config class.
- Error loading JSON mappings or body files.
- WireMock/Stub Runner dependency incompatible with your Spring Boot/Cloud version.
- Test uses `@StubRunnerPort` with the wrong artifact ID or before the server starts.
- Maven artifact resolves, yet stub contents lack the layout expected by the resolver.
- Mode/plugin version differences in how mappings are discovered.
- Resource conflict across multiple Stub Runner instances binding the same port.

### Distinguish Startup Failure from Request Failure

**Startup failure:**

~~~text
Spring test context fails before the test method
Reason: stub download / mapping load / server port bind
~~~

**Runtime request failure:**

~~~text
Stub Runner reports a listening HTTP port
Consumer test makes a request
WireMock responds 404 unmatched request
~~~

These are two separate phases. If the stub never started, comparing response schemas makes no sense yet.

### How to Verify

1. Inspect Stub Runner logs for which artifact was downloaded and whether mappings extracted.
2. Check test context configuration and dependency versions.
3. Identify the port assigned by Stub Runner.
4. For fixed ports, check whether another service bound the port.
5. Inspect loaded mappings/unmatched request journal if the test server exposes them.
6. If mapping loading fails, check JSON syntax and body file paths.
7. If dependency errors occur, inspect Spring Boot/Cloud/Contract BOMs and the dependency graph.

Do not brute-force random port numbers; prefer `:0` to allocate dynamic ports for parallel tests and read the port at runtime.

## 16. WireMock 404: Never Confuse with Artifact 404

This is one of the most confusing errors.

**Maven artifact 404** occurs when the resolver tries to fetch:

~~~text
.../com/example/inventory-producer/2.3.0/
inventory-producer-2.3.0-stubs.jar
~~~

**WireMock 404** occurs when the HTTP client calls:

~~~http
GET /api/inventory/SKU-102 HTTP/1.1
Host: localhost:<stub-runner-port>
~~~

while Stub Runner only has a mapping for:

~~~http
GET /api/inventory/SKU-101
~~~

WireMock returns a default 404 because **no mapping matched the request**.

### Illustrative Mapping

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-101",
    "headers": {
      "Accept": { "contains": "application/json" }
    }
  },
  "response": {
    "status": 200,
    "headers": { "Content-Type": "application/json" },
    "jsonBody": {
      "sku": "SKU-101",
      "available": true,
      "quantity": 8
    }
  }
}
~~~

This is an **illustrative WireMock mapping**, without claiming the Spring Cloud Contract generator emits these exact keys/ordering.

Requests fail to match when:

- Using `POST` instead of `GET`.
- URL omits `/api` or uses a different SKU.
- Mapping defines a query parameter matcher the client omits.
- `Accept`/`Content-Type` header is missing or has another value.
- JSON body misses a field, has wrong number/string type, order, or encoding.
- Consumer calls the right hostname yet hits **another service's port**.
- Consumer loads an older stub artifact lacking the new mapping.

### Do Not Turn Unmatched 404 into a Green Test

If a consumer error-path test asserts only:

~~~java
assertThat(status).isEqualTo(404);
~~~

a URL typo can pass even though it **never matched the business 404 stub**.

A business error contract needs both status **and** meaningful error body/code:

~~~json
{
  "code": "SKU_NOT_FOUND",
  "message": "SKU does not exist"
}
~~~

Consumer tests should assert `code=SKU_NOT_FOUND` and verify the actual request matched the right WireMock mapping.

### Request Mismatch Debugging Workflow

1. Confirm Stub Runner has a real listening port.
2. Record method, path, query, headers, and body sent by **Checkout's real client**.
3. Inspect matched/unmatched requests on the WireMock test server.
4. Open the mapping JSON inside the downloaded artifact.
5. Check each request matcher condition one by one.
6. If the contract is right and client is wrong, fix the consumer.
7. If the consumer request is valid and mapping is too strict/wrong, fix Groovy/YAML DSL and let the producer re-verify.
8. Never hand-edit generated mapping JSON inside a published artifact; fix the source and rebuild.

## 17. Missing Message Stub Differs from WireMock HTTP Errors

Spring Cloud Contract is not limited to HTTP. A producer may emit messages and a consumer uses Stub Runner/`StubTrigger` to receive events by **label**.

A Groovy messaging contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_changed'

    input {
        triggeredBy('publishStockChanged()')
    }

    outputMessage {
        sentTo('inventory-events')
        body(
            eventType: 'StockChanged',
            sku: 'SKU-101',
            quantity: 8
        )
        headers {
            messagingContentType(applicationJson())
        }
    }
}
~~~

The consumer can call `StubTrigger.trigger("stock_changed")` **when messaging Stub Runner is configured with the matching binder/adapter**. The consumer's handler test must wait for event handling and assert the outcome.

### Failures to Separate

| Symptom | Where to Suspect |
|---|---|
| Cannot download `:stubs` JAR | Artifact coordinates/repository, same as HTTP |
| JAR downloads yet lacks `stock_changed` label | Contract/message stub contents, consumer filtering |
| Label exists yet cannot trigger | `StubTrigger` configuration/label mapping |
| Trigger succeeds yet consumer never receives | Destination, binder, listener, test context |
| Consumer receives wrong payload | Schema, serialization, matcher, artifact version |
| Producer tests emit no message | Producer publisher/base test/test binder |
| Consumer test PASSES while producer test FAILS | Candidate stub does not prove real publisher |

**Do not expect all message stubs to appear as WireMock HTTP mappings.** Check contract/message definitions and matching labels/destinations instead.

If the consumer times out after `StubTrigger`, do not conclude the artifact does not exist: the message may have triggered while the handler listened on the wrong destination.

## 18. Git SCM and Maven Artifact Repositories Do Not Resolve the Same Way

Some Spring Cloud Contract projects store contracts/stubs in **Git SCM** instead of a Maven-compatible repository. In the SCM downloader mechanism, the URL may begin with the prefix:

~~~text
git://https://git.example.invalid/team/service-contracts.git
~~~

When using Git as the stub source per SCM conventions, the layout typically involves:

~~~text
META-INF/
  com.example/
    inventory-producer/
      2.3.0/
        contracts/
        mappings/
~~~

This is an **SCM file tree**, not a requirement for a Maven repository URL serving `inventory-producer-2.3.0-stubs.jar`.

### Distinguish Each Case

- If the consumer uses standard **Maven/`REMOTE` HTTPS `repositoryRoot`**, inspect the POM, Maven coordinates, and `-stubs.jar`.
- If the consumer uses the **Git SCM resolver `git://...`**, inspect the Git URL, credentials, commit/branch, `META-INF/group/artifact/version` layout, and `mappings` contents.
- If using **`LOCAL`**, inspect the consumer environment's Maven local repository.
- If using **`CLASSPATH`**, inspect the test runtime classpath.

Do not pass a bare Git URL without the SCM prefix into a Maven repository field assuming Stub Runner will clone it. Equally, do not expect `-stubs.jar` at a Git HTTP root when the pipeline is designed for SCM layout.

### `pushStubsToScm` Does Not Happen Automatically

In an SCM workflow, pushing mappings/stubs to Git typically requires configuring and intentionally running the `pushStubsToScm` goal/task. Having Groovy/YAML DSL inside `contracts/` **does not guarantee** mappings were generated, producer-verified, and pushed.

If a consumer using Git SCM does not see new mappings, check:

1. Did producer generated contract tests PASS?
2. Did the push-stubs job actually run?
3. Is the consumer reading the right Git ref/branch/commit?
4. Were mapping files pushed to the right `META-INF/.../version` path?
5. Are push/read permissions, branch protection, and revision tracking aligned?

Never “fix” this by pushing unverified proposals directly to a branch consumers treat as released.

## 19. Most Valuable Diagnostic Commands

Run these commands **inside a project already configured with the Maven/Gradle plugin, wrapper, and repositories**. They are examples for practice, not commands executed for this lesson.

### Maven Producer

~~~bash
# Verify producer tests and artifact packaging.
./mvnw -B -ntp clean verify

# Install artifacts/attached stubs into local Maven repository.
./mvnw -B -ntp install
~~~

To test resolving the classifier separately using the Maven dependency plugin:

~~~bash
./mvnw -B -ntp dependency:get \
  -Dartifact=com.example:inventory-producer:2.3.0:jar:stubs \
  -Dtransitive=false
~~~

Here `-Dartifact` uses `group:artifact:version:packaging:classifier`, not a Stub Runner ID. The command resolves via active Maven repositories/settings; if a dedicated repository is needed, configure repositories or resolver parameters per plugin version docs.

### Gradle Producer

~~~bash
./gradlew :inventory-producer:tasks --all
./gradlew :inventory-producer:contractTest
./gradlew :inventory-producer:verifierStubsJar
~~~

If Maven publication `verifiedStubs` is configured:

~~~bash
./gradlew :inventory-producer:publishVerifiedStubsPublicationToMavenLocal
~~~

This **task name comes from the illustrative publication name in section 8**. Your actual task name may differ by config. Do not assume the task exists without checking `tasks --all`.

### Inspect Archive

~~~bash
jar tf inventory-producer-2.3.0-stubs.jar
~~~

Check entries under:

~~~text
META-INF/.../mappings/
META-INF/.../contracts/
META-INF/.../__files/  (if body files are used)
~~~

### Inspect Maven Local Path

On systems using the default Maven local path:

~~~text
~/.m2/repository/com/example/inventory-producer/2.3.0/
~~~

If Maven settings override `localRepository`, use the actual path. In multi-job CI, each job may have its own isolated local repository.

### Observe Stub Runner

- Enable controlled diagnostic logging in the test environment to see resolved coordinates.
- Record requested ID, repository root, mode, and actual artifact version.
- Inspect resolution errors: 401/403/404/TLS/timeout.
- If bootstrap succeeds, record the HTTP port or message stub labels.
- Inspect WireMock's unmatched request journal when HTTP clients get 404.
- Never print secrets in logs or enable verbose HTTP auth tracing carelessly.

A useful diagnostic command set yields **precise evidence** of which stage succeeded, rather than blindly retrying.

## 20. CI Must Verify the Entire Chain, Not Just Packaging

A producer–consumer pipeline can be structured as:

~~~mermaid
flowchart TD
    A["Producer commit + contract revision"] --> B["Generate contract tests"]
    B --> C{"Nonzero tests executed and PASS?"}
    C -->|No| X["Block stub publish"]
    C -->|Yes| D["Package :stubs JAR"]
    D --> E{"Classifier, mappings, fixtures correct?"}
    E -->|No| X
    E -->|Yes| F["Publish candidate with exact version/digest"]
    F --> G["Consumer resolves that artifact"]
    G --> H{"Artifact download and startup PASS?"}
    H -->|No| X
    H -->|Yes| I["Stub Runner consumer tests"]
    I --> J{"HTTP/message assertions PASS?"}
    J -->|No| X
    J -->|Yes| K["Approval and release"]
~~~

**Never use “Gradle BUILD SUCCESS” or “Maven BUILD SUCCESS” as sole proof.** A build can run `0 contract tests` or package the application artifact instead of the `stubs` classifier.

### Minimum Quality Gates

| Step | Mandatory Evidence |
|---|---|
| Contract discovery | Right DSL version/paths, no unexpected 0 contracts |
| Producer verification | Generated producer tests actually executed and PASSED |
| Stub packaging | `-stubs.jar` file with right classifier and needed mappings/fixtures |
| Publication | Right repository, `group:artifact:version:stubs`, and digest |
| Consumer resolution | Stub Runner downloaded exact artifact, mode, and URL |
| Stub runtime | Port/labels ready, needed mappings loaded |
| Consumer verification | Real HTTP client/message handler properly handles success/error cases |
| Release | Artifact promoted from the exact verified candidate |

### Same-Job CI with Maven Local

For a monorepo or local experiment, the producer can publish-to-local and the consumer can test immediately in the **same environment**:

~~~bash
# Conceptual sequence for a configured Gradle multi-project.
./gradlew :inventory-producer:contractTest
./gradlew :inventory-producer:publishVerifiedStubsPublicationToMavenLocal
./gradlew :checkout-consumer:test
~~~

CI must run these commands **fail-fast**: if producer tests fail, do not run subsequent steps. The consumer needs `stubsMode=LOCAL` and proper dependency/repository settings.

If producer and consumer run in **two separate CI jobs on separate runners**, never use `LOCAL` expecting artifacts to appear automatically on another runner. Use a staging/remote repository or pass provenance-tracked artifacts between jobs.

### When Publish Succeeds Yet Consumer Still Cannot Download

Record:

~~~text
Publish log:
  uploaded: com.example:inventory-producer:2.3.0:stubs
  repository: <actual-publish-repository>

Consumer config:
  ids: com.example:inventory-producer:2.3.0:stubs:0
  repositoryRoot: <actual-read-repository>
  stubsMode: REMOTE
~~~

Then compare **repository URL, group/artifact/version/classifier, and read permissions**. Two logs both mentioning `inventory-producer` can still point to two different logical repositories.


## 21. From Logs to Root Cause: Complete Troubleshooting Table

| Symptom | Hypothesis to Test First | Evidence to Gather | Fix at the Right Layer |
|---|---|---|---|
| `Failed to download stub` | Artifact not yet published | Repository lacks `*-stubs.jar` | Producer packages and publishes |
| `Artifact not found` yet main JAR exists | Missing `stubs` classifier | Only `artifact-version.jar` exists | Attach/publish `stubs` classifier |
| Maven reports `Missing artifact ...:jar:stubs` | Wrong coordinates or repo | Group/artifact/version/type/classifier in logs | Align producer publication and Stub Runner ID |
| Release 2.3.1 does not exist yet | Consumer bumped version early | Registry only holds 2.3.0 | Publish verified 2.3.1 or temporarily pin available version |
| Consumer uses `2.3.0-SNAPSHOT`, producer published `2.3.0` | Version mismatch | POM/version/deploy log | Use exact released version |
| `REMOTE` fails, `LOCAL` PASSES on laptop | Dev local cache hides remote bug | Compare remote files and `~/.m2` | Publish remotely/grant read access |
| `LOCAL` fails in new CI job | Missing file in CI Maven local | Job's local repo path | Install in same job or use `REMOTE` |
| Remote returns HTTP 401 | Missing auth | HTTP status and CI identity | Configure read credentials |
| Remote returns HTTP 403 | Missing permission | Repository ACL | Grant minimum read scope |
| Remote returns HTTP 404 | Wrong URL or artifact truly absent | Root/path/file/metadata | Fix coordinates, `repositoryRoot`, or publish |
| Remote returns HTML login | Redirect/proxy | `Content-Type`, redirect target | Fix authentication/SSO resolver |
| Remote returns timeout/5xx | Network/proxy/repository | Registry logs/health | Fix network or controlled retry |
| JAR downloads yet lacks mappings | Broken contract discovery/packaging | `jar tf` and generated stubs dir | Fix producer build |
| JAR has mappings yet lacks body file | `__files` omitted from package | Mapping `bodyFileName` + archive listing | Package fixtures properly |
| Stub Runner fails to start | Broken JSON mapping or port/dependency | Startup exception | Fix mapping/config/dependency |
| Consumer calls URL and receives 404 | Unmatched WireMock request | Unmatched request journal | Compare method/path/headers/body |
| Consumer calls `localhost:0` | Dynamic port misunderstanding | Stub Runner runtime port | Inject `@StubRunnerPort`/`StubFinder` |
| Consumer PASSES yet producer lacks endpoint | Unverified candidate stub | Producer generated test FAILS | Block verified publication |
| Checkout test green on 2.3.0, production runs 2.3.1 | Stale stub | Consumer resolved ID + deploy version | Run compatibility against right candidate |
| Mapping for another consumer selected | Consumer filtering or duplicate | JAR layout, loaded mappings list | Configure/filter properly |
| Message trigger cannot find label | Message stub not packaged | Contract label + archive contents | Rebuild messaging stub |
| Message triggers yet handler times out | Wrong binder/destination | Consumer logs and destination | Fix messaging test setup |
| Different bytes for same version | Mutable artifact/cache | SHA-256 or metadata | Immutable releases + provenance |

### Prioritizing When Multiple Errors Appear Together

If you see both “artifact 404” and “response assertion failed” across different runs, start from the **current failing run's output**:

1. Capture the artifact request and source for the **exact failing run**.
2. Check whether it downloaded the artifact.
3. If not, do not analyze WireMock requests from another run to draw conclusions.
4. If yes, compare bytes/digest against the producer-verified artifact.
5. Only once the stub runtime is healthy should you inspect mappings and consumer assertions.

Never mix logs from multiple builds/versions and treat them as describing one single failure.

## 22. Practice Exercise 1 — Artifact Completely Absent

### Problem Statement

Checkout consumer configures:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.4.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/verified-stubs"
)
~~~

The repository holds:

~~~text
com/example/inventory-producer/
  2.3.0/inventory-producer-2.3.0-stubs.jar
  2.3.1/inventory-producer-2.3.1-stubs.jar
~~~

No `2.4.0` folder exists. Producer `main` is on a commit preparing for 2.4.0, yet has not published the artifact.

**Q1. Is this a WireMock mapping error?**

**No.** Stub Runner has not resolved stub artifact 2.4.0 yet, so no corresponding WireMock has mappings to test.

**Q2. Should you change the consumer ID to `+` or `latest`?**

No, if the goal is to verify compatibility with release 2.4.0. Downloading an older release may give green tests yet **proves nothing** about consumer compatibility with the new producer candidate.

**Q3. What must the producer do?**

The producer must generate/run contract tests and PASS, package the stub JAR with classifier `stubs`, publish candidate 2.4.0 to the staging/approved repository per policy, and pass the exact coordinates/digest to Checkout.

**Q4. What if Checkout needs to develop ahead?**

It can use stub 2.3.1 to test already-supported interactions or an unverified candidate stub **on an isolated test branch**, clearly labeled. Never treat an unverified stub as proof that 2.4.0 is implemented.

### Sample Evidence Response

~~~text
Requested:
  com.example:inventory-producer:2.4.0:stubs

Available:
  2.3.0:stubs
  2.3.1:stubs

Root cause:
  producer 2.4.0 stubs not published

Action:
  run producer verification, package and publish candidate,
  update Checkout CI to use exact candidate coordinates

Status:
  BLOCKED_ON_PRODUCER_ARTIFACT
~~~

The status name is a team workflow example, not an official Spring Cloud Contract status.

## 23. Practice Exercise 2 — Wrong Classifier in Publication

### Problem Statement

Producer build output:

~~~text
build/libs/inventory-producer-2.4.0-stubs.jar
~~~

Yet after publish, the Maven repository holds only:

~~~text
inventory-producer-2.4.0.jar
inventory-producer-2.4.0.pom
~~~

Checkout requests:

~~~text
com.example:inventory-producer:2.4.0:stubs:0
~~~

**Q1. Did the producer create the stub?**

Signs indicate the task created the file in build output. Still run `jar tf` to verify its contents. **Creating a file does not mean it was published.**

**Q2. Is the consumer misconfigured?**

Not necessarily. `:stubs` is the right classifier for this convention. The bug appears to be in **publication/attachment**: the JAR exists in the build, yet was not uploaded to the repository under that classifier.

**Q3. Which configurations need checking?**

- Maven: plugin stub generation/attachment, `install`/`deploy`, and attached artifacts.
- Gradle: `publishing.publications`, `verifierStubsJar` artifact, `archiveClassifier`/classifier metadata, and publish task.
- Registry: actual coordinates of the uploaded file, checking if `artifactId`/`groupId` changed.

**Q4. Should you drop `:stubs` from the consumer ID?**

No. The resolver would download the main application JAR and the error would turn into “no mappings found,” leaving consumer stub needs unsolved.

### Verified Fix Direction

~~~text
Before:
  repository has inventory-producer-2.4.0.jar

After:
  repository has inventory-producer-2.4.0.jar
  repository has inventory-producer-2.4.0-stubs.jar

Verify:
  expected mapping exists inside -stubs.jar
  consumer REMOTE resolves exact classifier
  Stub Runner starts and client test passes
~~~

For immutable release versions, **never overwrite** the same coordinates if policy forbids it; bump version/republish per controlled release rules.

## 24. Practice Exercise 3 — Wrong Version in Multi-Module

### Problem Statement

Gradle project contains:

~~~text
:platform:inventory-service
:platform:checkout-service
~~~

Actual producer publication:

~~~text
groupId    = com.example.platform
artifactId = inventory-api
version    = 3.1.0
classifier = stubs
~~~

Checkout instead uses:

~~~text
com.example:inventory-service:3.1.0:stubs:0
~~~

**Q1. Which components diverge?**

Both `groupId` and `artifactId`. The consumer used the project/service name instead of Maven publication coordinates.

**Q2. What is the right Stub Runner ID in this example?**

~~~text
com.example.platform:inventory-api:3.1.0:stubs:0
~~~

**Q3. Is fixing the ID alone enough?**

Verify the publication actually has `inventory-api-3.1.0-stubs.jar` and the JAR holds mappings. Then verify Stub Runner starts and consumer tests use the right port.

**Q4. What if Inventory source moved to 3.1.1 while the artifact is still 3.1.0?**

Consumer test results only prove behavior from stub 3.1.0. To verify 3.1.1, the producer must verify/publish the matching stub and the consumer must pin the new candidate.

## 25. Practice Exercise 4 — 404 at Stub Runtime, Not Registry

### Problem Statement

Logs show:

~~~text
Resolved stub artifact:
  com.example:inventory-producer:2.3.0:stubs

Stub Runner HTTP port:
  13142

Loaded mapping:
  GET /api/inventory/SKU-101
~~~

Checkout sends:

~~~http
GET /inventory/SKU-101 HTTP/1.1
Host: localhost:13142
Accept: application/json
~~~

WireMock returns 404.

**Q1. Do we need to republish the stub?**

No. Stub Runner downloaded the artifact and started cleanly. The issue is a **request path mismatch against the mapping**: the client omitted `/api`.

**Q2. Where could a false positive test occur?**

If a consumer test expects 404 and asserts only HTTP status, a WireMock unmatched 404 could be mistaken for a business 404. Assert error code/body and confirm the matched mapping.

**Q3. When should you fix the contract instead of the consumer?**

If the reviewed requirement is `GET /inventory/{sku}` while the producer contract currently specifies `/api/inventory/{sku}`, both teams must agree on the API path, update the source DSL, and run producer/consumer gates. Never hand-edit generated mappings just to make current tests green.

### Clear Failure Record

~~~text
Artifact resolution: PASS
Stub Runner startup: PASS
HTTP request match: FAIL

Expected mapping: GET /api/inventory/SKU-101
Actual request:   GET /inventory/SKU-101

Root cause: client base path mismatch
Owner: Checkout integration
~~~

This is an actionable report, unlike merely saying “stub not found.”

## 26. Reproducible Stub Incident Report Template

When filing an issue for the producer/platform team, fill in:

~~~text
Title:
  Stub resolution failure for Inventory -> Checkout

Consumer:
  repository/commit: <consumer-repo>@<consumer-sha>
  test: CheckoutInventoryClientTest
  Stub Runner ID: <group:artifact:version:classifier:port>
  stubsMode: <LOCAL|REMOTE|CLASSPATH>
  repositoryRoot: <url-or-not-applicable>

Observed failure:
  phase: <resolve|extract|bootstrap|request-match|assertion>
  error category: <404|401|403|timeout|no-mappings|...>
  exact error: <sanitized-message>

Producer:
  source commit: <producer-sha>
  contract revision: <contract-sha>
  contract test count/result: <count/passed/failed/skipped>
  packaged stub file: <filename>
  published coordinate: <group:artifact:version:classifier>
  artifact digest: <sha256>

Evidence:
  archive mapping entries: <paths>
  Maven registry path: <url-without-secret>
  Stub Runner port: <port-or-none>
  unmatched request: <method/path/headers/body-if-safe>

Root cause:
  <what is confirmed, not a guess>

Next action:
  <owner and concrete step>
~~~

Never put tokens/passwords, private user data, or sensitive log lines into issues. Values inside `<...>` are placeholders.

### Distinguish Conclusion Confidence Levels

- **Confirmed:** “Repository lacks classifier `stubs` for version 2.4.0.”
- **Hypothesis:** “CI publish may have omitted the attached artifact.”
- **Needs investigation:** “Inspect Gradle publication and registry metadata.”
- **Resolved:** “Stub JAR published under exact coordinates; consumer tests using that version PASS.”

This shortens back-and-forth across producer, consumer, and platform teams instead of repeatedly asking “Which version are you using?”

## 27. Checklist Before Reporting a Missing Artifact Error

### Producer and Build

- [ ] Identified the exact producer module building the stub.
- [ ] Groovy/YAML contracts discovered in expected count.
- [ ] Generated producer contract tests actually ran and PASSED.
- [ ] Tests were not unintentionally skipped, filtered, or `0 tests`.
- [ ] Stub JAR built by the right task/goal.
- [ ] Stub JAR contains needed HTTP mappings or message definitions.
- [ ] `bodyFileName` and referenced `__files` entries are valid.
- [ ] Artifact attached/published with classifier `stubs`.
- [ ] Publication group/artifact/version match target coordinates.
- [ ] Publish/install logs show success evidence.
- [ ] Artifact comes from the same revision whose producer tests PASSED.
- [ ] No mutable release overwrite was done to hide errors.

### Repository and Resolver

- [ ] Consumer uses exact `groupId`/`artifactId`/`version`/`classifier`.
- [ ] Stub Runner `:stubs:0` is not confused with Maven dependency coordinates.
- [ ] `stubsMode` matches `LOCAL`, `REMOTE`, or `CLASSPATH` source.
- [ ] If `LOCAL`, JAR is installed in the **consumer environment's** Maven local.
- [ ] If `REMOTE`, `repositoryRoot` points to the exact Maven repository root.
- [ ] Registry holds the actual `*-stubs.jar` file, not only the main JAR.
- [ ] Credentials have minimum required read scope; no hardcoded secrets.
- [ ] HTTP 401/403/404/5xx/TLS errors classified accurately.
- [ ] For `SNAPSHOT`, metadata/resolver/caching checked.
- [ ] Version and digest match the producer-verified artifact.
- [ ] For Git SCM, `git://` and SCM layout verified instead of applying Maven file paths.

### Consumer and Runtime

- [ ] JAR contents include mappings for the use case under test.
- [ ] If `stubs-per-consumer`, consumer identity/filter matches.
- [ ] Stub Runner started on the right port or registered message handlers.
- [ ] HTTP client uses the runtime port from `@StubRunnerPort`/`StubFinder`.
- [ ] Method, URL, query, headers, and JSON body match the mapping.
- [ ] WireMock unmatched 404 is not mistaken for a business 404.
- [ ] Error contracts assert both status and body/code.
- [ ] Messaging label/destination/consumer binder are right.
- [ ] Consumer tests exercise the real HTTP client/message handler, not just stub mappings.
- [ ] CI does not switch to `latest` to bypass errors.
- [ ] Logged source SHA, version, classifier, digest, test reports, and remediation owner.

## 28. Takeaways and References

**Stub artifact missing, wrong classifier, or wrong version** is an **artifact distribution chain** failure, not always a contract DSL or HTTP client bug.

Resolve in order:

1. **Producer:** did generated tests run/PASS and was the stub JAR created?
2. **Publication:** was the artifact attached/uploaded under the exact `group:artifact:version:stubs`?
3. **Resolution:** is consumer Stub Runner searching the right mode, repository, version, and credentials?
4. **Packaging:** does the downloaded JAR hold the right mappings/fixtures/labels?
5. **Runtime:** did Stub Runner start and do consumer requests match?
6. **Compatibility:** do consumer tests use the verified producer's exact stub?

A producer application JAR, a contract definitions JAR, and a producer stub JAR are **three distinct artifact types**. Never swap them by arbitrarily changing classifiers.

### References

- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): `@AutoConfigureStubRunner` configuration, IDs, modes, and ports.
- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): resolver, download, and stub server lifecycle.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): generating tests/stubs and Maven artifact attachment.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): `contractTest`, `verifierStubsJar`, and Gradle integration.
- [Spring Cloud Contract — Git as Storage](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-use-git-as-storage.html): using an SCM repository instead of Maven artifacts.
- [Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): local/remote repository layout and coordinates.
- [Maven Dependency Plugin — dependency:get](https://maven.apache.org/plugins/maven-dependency-plugin/get-mojo.html): verifying resolution of an artifact/classifier.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): configuring publications and Maven local/remote.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): request matching, mappings, and response files.

**Practical conclusion:** when Checkout says “stub not found,” ask **“couldn't it find the artifact, couldn't it find the mapping inside the artifact, or did the request fail to match the running stub?”** Only by pinpointing the exact failing layer and reconciling coordinates/version/classifier against the real artifact can you fix the problem accurately without undermining contract test trustworthiness.
