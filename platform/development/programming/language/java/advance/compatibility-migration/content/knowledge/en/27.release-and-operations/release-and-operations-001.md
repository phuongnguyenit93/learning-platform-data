
# Storing Artifacts, Configurations, and Test Results for Each Migration Step

Upgrading Java is not just changing the `sourceCompatibility` line or changing the Docker base image. In a running system, the process can involve multiple steps: upgrading the compiler JDK, keeping or changing `--release`, updating Gradle/Maven, replacing dependencies, removing internal APIs, migrating frameworks and Jakarta EE, adjusting JVM flags, testing compatibility across multiple versions, and then performing a canary deployment. Each step can produce **a new binary, a new configuration, and new test results**.

If you only record "CI green" or "upgraded to Java 21", a few weeks later the development team will struggle to answer: which artifact was tested, which artifact was released, what the exact JDK update was, which GC the server used, which tests were skipped, which dependency set caused an error, and whether a rollback is feasible.

Therefore, in *Java Advance Compatibility Migration*, under the *Release and Operations* section, **storing artifacts, configurations, and test results for each migration step** is part of the compatibility strategy: creating a chain of evidence that can be reproduced, cross-checked, integrity-verified, and used to support failure investigation/rollback.

The goal is not to collect every file indefinitely, but to store **the right objects, the right versions, with clear traceability relationships and security controls**.

## 1. Why Must Each Migration Step Have Evidence?

Suppose the application goes through these states:

~~~text
S0: Java 11, old framework, old dependencies
S1: JDK 21 compiler, still building with --release 11
S2: replace dependencies using JDK internal APIs
S3: upgrade framework, change javax -> jakarta
S4: switch runtime and bytecode baseline
S5: optimize GC and container resources
S6: canary and production rollout
~~~

If only the final S6 artifact is stored, a regression in production could have been caused by S1, S2, S3, S4, or S5. Without intermediate evidence, the team must recreate past conditions and may no longer be able to build the old version.

Storing per step helps:

- **Isolate fault-inducing changes:** compare last-known-good with the first failing step.
- **Reproduce:** run the exact JAR, runtime, and configuration that were used.
- **Make decisions:** base release gates on reports and metrics rather than intuition.
- **Rollback:** immediately retrieve the matching binary, container image, config, and schema.
- **Perform security checks:** identify which dependencies/runtimes need patching.
- **Audit and collaborate:** know who created it, who approved it, when, and based on what evidence.
- **Preserve failure results:** also store failed test runs to understand the root cause.

### 1.1. What Is a Migration Step?

A *migration step* needs a clear scope and testing criteria. For example:

~~~text
ID: JAVA-MIG-04
Goal: upgrade runtime JDK from 17 to 21
Unchanged: public HTTP API, database schema, business features
Must verify: startup, integration, API contract, p99, CPU, RSS
Result: artifact + manifest + test reports + decision
~~~

A migration step does not necessarily correspond to a production release. It can be a research phase, staging phase, toolchain upgrade, or compatibility fix.

### 1.2. What Does "Build Succeeded" Prove?

It proves that the specific build process met its exit condition. It **does not by itself prove**:

- All tests actually ran.
- The artifact being deployed is identical to the artifact that was tested.
- The runtime JDK is compatible.
- API/event/database contracts are unchanged.
- Native/JNI dependencies are present in the image.
- Performance SLOs are maintained.
- A rollback path exists after schema migration.

Therefore, **a build record is one part of release evidence**, not the whole.

## 2. Distinguishing Artifacts, Configurations, and Test Results

| Category | Examples | Question Answered |
|---|---|---|
| Release artifact | JAR, WAR, container image, desktop installer | Which binary was built? |
| Supporting artifact | SBOM, generated source, migration SQL, runtime image | Which components was the binary built from? |
| Build configuration | JDK toolchain, build plugin, dependency lock | How was it built? |
| Runtime configuration | JVM flags, heap/GC, feature flags, server/container | Under what conditions does the binary run? |
| Test evidence | JUnit XML, contract report, benchmark raw data | What was verified? |
| Deployment evidence | Image digest, rollout records, canary observations | Which version is running where? |
| Decision evidence | Approval, exception, rollback decision | Why was it promoted or blocked? |

An **artifact** can be broadly understood as any valuable output from a pipeline. However, when designing a repository, you should distinguish **runnable binaries** from **evidence used to explain the binary**.

### 2.1. Relationships Between Objects

~~~mermaid
flowchart TD
    A["Migration step ID"] --> B["Source commit"]
    B --> C["Build toolchain + dependencies"]
    C --> D["Build ID"]
    D --> E["Binary artifact + SHA-256"]
    E --> F["Test runs + reports"]
    E --> G["Deployment + configuration"]
    F --> H["Release gate"]
    G --> H
    H --> I["Promote / Hold / Rollback"]
    I --> J["Runtime observations"]
~~~

A test report containing only `PASS` without pointing to the binary, JDK, and environment is not enough to prove a release is safe.

## 3. Identification: Version Does Not Replace Checksum

During a migration, there are multiple version concepts.

| Field | Sample Value | Meaning |
|---|---|---|
| Git commit | `abcdef123...` | Source code/configuration at a commit |
| App version | `2.7.0` | Product version |
| Build ID | `ci-18421` | A build execution |
| Migration ID | `JAVA-MIG-04` | A step in the plan |
| JAR SHA-256 | `sha256:...` | Byte content of the JAR |
| Image digest | `registry.example/app@sha256:...` | Specific manifest/container image |
| Test run ID | `test-18421-jdk21` | A test execution |
| Deployment ID | `prod-492` | A deployment execution |
| DB revision | `V034__expand_order.sql` | Schema migration milestone |

### 3.1. Why Is Storing Only the App Version Dangerous?

Two pipelines can both produce `orders-2.7.0.jar` yet have different contents because:

- Snapshot/dynamic dependency versions changed.
- The JDK vendor/update or compiler plugin changed.
- The build includes a generated timestamp.
- The source tree has uncommitted changes.
- The build configurations differ.
- An artifact was rebuilt after testing.
- Multiple architectures were packaged using different native tools.

Therefore, **do not use a filename or version label as the sole identifier of an artifact**.

### 3.2. Traceability Rules

A release record should answer:

1. Which build produced the artifact?
2. Which source commit and dependency lock were used?
3. What is the checksum/digest of the artifact?
4. Which test run tested that checksum?
5. Which configuration snapshot was used during testing?
6. Which deployment ran this exact artifact?
7. Which deployment do the metrics and promotion decision belong to?

If one link is missing, the record loses part of its reproducibility.

## 4. Reference Evidence Directory Structure

A suitable structure for CI/artifact storage:

~~~text
java-migration/
└── orders-service/
    └── JAVA-MIG-04/
        └── ci-18421/
            ├── manifest.yaml
            ├── artifacts/
            │   ├── orders.jar
            │   ├── orders.jar.sha256
            │   ├── sbom.json
            │   └── schema-migrations/
            ├── build/
            │   ├── toolchain.json
            │   ├── dependency-tree.txt
            │   ├── build-summary.txt
            │   └── source-revision.txt
            ├── config/
            │   ├── runtime-effective.redacted.yaml
            │   ├── jvm-flags.redacted.txt
            │   └── environment-metadata.json
            ├── tests/
            │   ├── unit/
            │   ├── integration/
            │   ├── contract/
            │   ├── runtime-matrix/
            │   └── performance/
            ├── deployment/
            │   ├── staging.yaml
            │   ├── canary.json
            │   └── promotion-decision.yaml
            └── checksums.sha256
~~~

This is an illustrative structure. In a real system, files may be stored across object storage, an artifact repository, a CI test reporting service, and a release management system. A **central manifest** containing references is needed for traceability.

### 4.1. Git, CI, and the Artifact Repository Have Different Responsibilities

**Git** is suitable for source code, build scripts, config templates, lockfiles, migration SQL, manifest templates, and release policies.

The **CI system** runs builds/tests and produces logs and reports. However, CI logs may expire based on retention policies or be deleted.

The **artifact repository/object storage** holds binaries and evidence requiring long-term retrieval, with access permissions and version/retention policies.

Do not stuff heap dumps, JFR recordings, and tens of GBs of binaries into a Git repository just so you "don't lose history".

### 4.2. Do Not Overwrite Using a latest Path

The names:

~~~text
artifacts/latest/app.jar
reports/latest/test.xml
~~~

can be useful as pointers, but are not sufficient as immutable storage. You should use paths based on **migration step + build ID + artifact hash**; aliases like `stable` or `last-known-good` simply point to these objects.

## 5. Manifest: A Single Entry Point for All Evidence

Example record:

~~~yaml
schema_version: 1

application: orders-service

migration:
  id: "JAVA-MIG-04"
  title: "Switch runtime to JDK 21"
  predecessor: "JAVA-MIG-03"
  stage: "STAGING"
  outcome: "PENDING"

source:
  commit: "EXACT_GIT_COMMIT"
  tag: "release/java-migration"

build:
  id: "ci-18421"
  tool: "Gradle Wrapper"
  tool_version: "EXACT_GRADLE_VERSION"
  compiler:
    vendor: "APPROVED_JDK_VENDOR"
    version: "EXACT_JDK_BUILD"
    release_target: 17
  runner_image: "EXACT_CI_IMAGE_DIGEST"

artifacts:
  jar:
    path: "artifacts/orders.jar"
    sha256: "EXACT_SHA256"
  container:
    image: "registry.example/orders@sha256:EXACT_DIGEST"
  sbom: "artifacts/sbom.json"

config:
  snapshot: "config/runtime-effective.redacted.yaml"
  jvm_flags: "config/jvm-flags.redacted.txt"
  secret_policy: "SECRET_VERSION_REFERENCES_ONLY"

tests:
  unit: "tests/unit/summary.yaml"
  integration: "tests/integration/summary.yaml"
  contract: "tests/contract/summary.yaml"
  runtime_matrix: "tests/runtime-matrix/results.yaml"
  performance: "tests/performance/summary.yaml"

deployment:
  record: "deployment/staging.yaml"
  promotion: "deployment/promotion-decision.yaml"
~~~

All `EXACT_*` values are only placeholders; do not publish this manifest as actual evidence until it has been populated and verified by the pipeline.

### 5.1. The Manifest Must Be a Snapshot of Reality

For example, the compiler uses JDK 21 with `--release 17`, staging uses JDK 21, and production uses JDK 17 during the mixed-version phase. These are separate axes and must be recorded individually.

Do not use a single `javaVersion: 21` field if it hides the difference between the **build JDK**, **target bytecode/API**, and **runtime JDK**.

### 5.2. Do Not Confuse Test Statuses

The following statuses are not the same:

- `PASS`: run and passed.
- `FAIL`: run and failed.
- `SKIPPED`: skipped by the test runner.
- `NOT_RUN`: did not run.
- `BLOCKED`: could not run due to dependencies/environment.
- `FLAKY`: exhibited instability or required retries.
- `TIMED_OUT`: exceeded time limit.

A gate must not silently convert `SKIPPED` to `PASS` just because the pipeline exit code is 0.

## 6. Storing Intact Binary Artifacts

Artifacts that typically need to be stored:

- Main JAR/WAR/EAR or plugin package.
- Native desktop installer.
- Custom JDK runtime image if distributed with the application.
- Container image digest.
- SQL migration bundle.
- Generated classes when they are part of the release.
- Dependency manifest/SBOM.
- Corresponding checksum or signature.

### 6.1. Computing Checksums

On a shell with `sha256sum`:

~~~bash
sha256sum build/libs/orders.jar
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "build\libs\orders.jar"
~~~

SHA-256 helps verify whether two byte streams are identical. However, **a hash does not by itself prove that the builder is trustworthy, the source is correct, or the artifact has passed testing**. That evidence must come from CI provenance, test reports, and verification policies.

### 6.2. Build Once, Promote the Same Artifact

Risky approach:

~~~text
Build A → Test A → Rebuild B → Deploy B
~~~

Even though A and B share the same Git commit, they can still produce different binaries.

Sustainable approach:

~~~text
Build Artifact A
       ├── Unit/Integration/Contract tests on A
       ├── Security scan A
       ├── Staging deploy A
       └── Production promote A by checksum/digest
~~~

If a signing, repackaging, or native installer creation step alters the bytes, the new output also needs its own **checksum and record**.

### 6.3. Also Store Failed Build Evidence

If compiling with a new JDK fails due to an `IllegalAccessError`, you still need to store:

- Build ID and Git commit.
- JDK/compiler version.
- Error log with sensitive data redacted.
- Dependency versions.
- Compiler/annotation processor configuration.
- Failure classification and issue link.

You should not store only successful builds.

## 7. Containers: A Tag Is Not a Digest

A container can be referenced as:

~~~text
registry.example/orders:2.7.0
~~~

However, a tag can be mutated if the registry/policy allows it. A reference by digest is more explicit:

~~~text
registry.example/orders@sha256:IMAGE_MANIFEST_DIGEST
~~~

Record all of the following:

- Release tag.
- Running digest.
- Application JAR checksum inside the image.
- Base image digest.
- JDK vendor/update inside the image.
- OS/architecture.
- Build ID and source commit.

### 7.1. A Container Image Contains More Than Just the JAR

Two images with the same JAR can differ in:

- CA certificates.
- JDK runtime.
- OS shared libraries.
- Locale/timezone data.
- Entrypoint/JVM options.
- User permissions.
- Native drivers.

Therefore, when reproducing a bug, **storing only the JAR is not enough** if the system runs in containers.

### 7.2. Multi-Architecture

A multi-arch image reference can point to separate image manifests for Linux amd64/arm64. When an issue appears only on one architecture, you must record the actual platform and the corresponding digest, not just the shared tag.

## 8. Storing Toolchain and Build Inputs

To reproduce a Java build, record:

- Git commit and submodule revisions.
- Maven/Gradle Wrapper version.
- Compiler JDK vendor, update, and architecture.
- `--release`, `source`/`target`.
- Build plugins and annotation processors.
- Dependency graph and lockfiles.
- BOM/version catalogs.
- Native compilation tools if JNI is used.
- Build runner image/OS.
- Redacted relevant environment values.
- Compiler flags and JPMS options.
- Generated source inputs.

### 8.1. Illustrative Collection Commands

~~~bash
java -version
javac -version
git rev-parse HEAD
git status --porcelain
./gradlew --version
~~~

Or with Maven:

~~~bash
mvn -version
mvn dependency:tree
~~~

Run these commands in the appropriate pipeline context, and do not treat them as the sole verification. A Gradle daemon may use a different JDK from the shell's `java`; a Java toolchain may specify a separate compiler JDK.

### 8.2. Dirty Working Tree

If building from uncommitted files, the Git SHA does not fully identify the source. For releases, you should use a clean checkout/immutable commit or explicitly record out-of-Git changes and manage storage permissions appropriately.

### 8.3. Dynamic Dependencies Make Reproduction Difficult

Dynamic ranges/SNAPSHOTs can resolve differently over time. You should store resolved versions, lockfiles, or dependency verification metadata, not just the declared configuration lines.

## 9. Maven: Dependencies and Effective Configuration

A Maven build can vary by profiles, properties, plugins, and dependency mediation.

Example report collection:

~~~bash
mvn -version
mvn dependency:tree
mvn help:effective-pom
~~~

`effective-pom` shows the computed configuration, but it may contain sensitive data from settings/profiles. **Do not upload raw output publicly** without redaction.

### 9.1. Scopes Must Be Stored

A `provided` dependency may exist at compile time without entering the runtime JAR/WAR. A `test` dependency does not prove that production has the corresponding provider.

Store the following information:

- Compile/runtime/test dependency scopes.
- BOM versions.
- Dependency exclusions.
- Plugin versions.
- Profiles.
- Transitive dependency selection.

### 9.2. External Servers Are Not Fully Captured in the Dependency Tree

When deploying a WAR to an application server, some APIs/providers are supplied by the server. A Maven dependency tree cannot describe the full runtime without knowing the server modules. You need to snapshot the platform profile and server version.

## 10. Gradle: Configuration, Toolchain, and Dependency Resolution

Some reports:

~~~bash
./gradlew --version
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency example-library \
  --configuration runtimeClasspath
~~~

Actual configurations depend on plugins/source sets. If the app has test fixtures or custom annotation processors, collect the corresponding reports as well.

### 10.1. Storing Lockfiles and Version Catalogs

Version catalogs describe desired versions; actual dependency resolution also depends on constraints, platforms, and transitive dependencies. Store:

- Resolved graph.
- Lockfiles when dependency locking is enabled.
- Dependency verification metadata if used.
- Gradle Wrapper version.
- JVM running the Gradle daemon.
- Java toolchain compiler version.
- Build cache policy if relevant.

### 10.2. The Build Cache Is Not a Release Repository

A cache entry can be evicted or have a different retention period. It does not necessarily contain the manifest, approvals, or test evidence. Use a dedicated artifact repository to store release-critical outputs.

## 11. Source Configuration Differs from Effective Configuration

Applications typically receive configuration through multiple layers:

~~~text
application.yaml
  + profile-specific properties
  + environment variables
  + JVM -D options
  + command-line arguments
  + Kubernetes ConfigMaps / secrets
  + Helm/Kustomize overlays
  + remote feature flags
  + server/platform defaults
  = effective runtime configuration
~~~

Storing only `application.yaml` from Git is not enough to know which settings production runs with.

### 11.1. Configuration Catalog

| Category | Examples | What to Store |
|---|---|---|
| Source config | Git-tracked templates | Commit and file reference |
| Deployment config | Rendered manifests | Redacted snapshot |
| Runtime config | Effective properties | Values affecting the migration |
| JVM config | GC/heap/module flags | Effective flags and origin |
| Feature flags | New API/serialization enabled | State at test/deploy time |
| Server config | Servlet/JPA/TLS module versions | Platform/version/profile |
| External resources | Database/broker/cache | Engine version, schema revision |

### 11.2. Do Not Dump Secrets

Do not store verbatim:

- Database password.
- API key.
- Access token.
- Signing key.
- Private TLS key.
- JWT signing secret.
- Full connection string with credentials.
- Command line containing tokens.
- Heap dump containing user data without dedicated controls.

Example snapshot:

~~~yaml
database:
  endpoint: "INTERNAL_ENDPOINT_REFERENCE"
  schema_version: "V034"
  username: "REDACTED"
  password:
    secret_ref: "secret-manager/orders-db"
    version_ref: "APPROVED_SECRET_VERSION"

tls:
  truststore_ref: "approved-truststore-version"
  private_key: "NOT_EXPORTED"
~~~

Secret reference/version IDs enable traceability without duplicating secrets in the archive. Even endpoints can be sensitive depending on organizational policy.

### 11.3. Do Not Use Weak Password Hashes Instead of Redaction

A short hashed password can still be guessed. Use proper secret-manager metadata instead of inventing your own secret storage mechanism.

## 12. JVM Flags and Runtime Metadata

Important parameters when upgrading the JDK:

- `-Xms`, `-Xmx`, heap percentage.
- GC collector and tuning.
- `--add-opens`, `--add-exports`.
- `-Dfile.encoding`, timezone, locale.
- Java agents.
- TLS/security providers.
- Thread count, active processor count.
- Unified GC logging.
- `java.home`/runtime image reference.

### 12.1. Collecting from a HotSpot Runtime

Example commands (on supported JVMs):

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

When diagnosing a new JVM:

~~~bash
java -XX:+PrintCommandLineFlags -version
java -XX:+PrintFlagsFinal -version
java --list-modules
~~~

Not every JVM vendor uses the same diagnostic options. Do not apply HotSpot patterns to OpenJ9 without verification.

### 12.2. Actual GC May Differ from Assumed Configuration

The absence of `UseG1GC` on the command line does not prove the JVM is not using G1. The JVM can select a default based on JDK/version/resources. You should record the **actually selected** collector, max heap/active CPU count, and container limits.

### 12.3. Redaction Is Required Before Upload

`VM.command_line` may contain sensitive system properties. Collect it in an authorized environment, filter out secrets, and do not expose the full content in public logs.

## 13. The Test Environment Is Part of the Result

The same JAR runs differently due to:

- JDK vendor/update.
- OS distribution and CPU architecture.
- Container cgroup v1/v2, CPU/memory quotas.
- Filesystem permissions.
- Timezone, locale, and charset.
- Native/JNI libraries.
- Database/driver version.
- Message broker/cache version.
- Application server/framework.
- TLS truststore/certificate.
- Feature flags.
- Background traffic/load.

Therefore, a test report must record at least an **environment ID** that can resolve to those parameters.

### 13.1. No Need to Store the Entire Virtual Machine

The goal is to store information that affects reproducibility, not to dump the entire filesystem or environment variables. If a complete environment must be preserved, an immutable container/VM image digest and IaC/config version may be more suitable.

### 13.2. Performance Tests Must Match Resources

A JDK 21 benchmark on a 16-core workstation cannot be compared directly with Java 17 in a pod with a 1 vCPU quota. The test record needs the CPU limit, memory limit, and workload profile.

## 14. Which Fields Should Test Reports Contain?

A test run can record:

~~~yaml
test_run:
  id: "test-18421-integration"
  build_id: "ci-18421"
  artifact_sha256: "EXACT_JAR_HASH"
  environment_id: "postgres-stage-2026-11"
  started_at: "ISO_8601_TIMESTAMP"
  elapsed_seconds: 172
  status: "PASS"

counts:
  passed: 248
  failed: 0
  skipped: 3
  aborted: 0

reports:
  junit_xml: "tests/integration/junit.xml"
  logs: "tests/integration/logs.redacted.txt"

notes:
  - "Three test cases skipped per policy, see details"
~~~

The numbers are illustrative, not actual results.

### 14.1. Skipped and Flaky Tests

If a test is skipped because a database/HSM is unavailable, it must not be recorded as PASS without an explicit exception. If a test fails on the first attempt and passes on a retry, you must store both the failed attempt and the flaky status, without erasing traces.

### 14.2. Do Not Keep Only a CI URL

CI jobs and logs can expire. For release-critical evidence, store exported reports and summaries in an archive with appropriate retention, linking to the CI job as supplementary information.

### 14.3. Test Inputs and Fixtures

A report is not reproducible if the source data has changed. You should record the dataset/fixture version and checksum where appropriate; for production data, data protection policies must be enforced.

## 15. JUnit XML and Raw Test Logs

JUnit XML is commonly supported by CI systems, although the detailed schema depends on the runner.

~~~xml
<testsuite name="OrderIntegrationTest"
           tests="3"
           failures="0"
           errors="0"
           skipped="1"
           time="1.82">
  <testcase classname="OrderIntegrationTest"
            name="createOrder" time="0.42"/>
  <testcase classname="OrderIntegrationTest"
            name="getOrder" time="0.31"/>
  <testcase classname="OrderIntegrationTest"
            name="requiresHardwareToken">
    <skipped message="Test environment unavailable"/>
  </testcase>
</testsuite>
~~~

You should keep:

1. A small summary for the release gate to read.
2. Raw JUnit XML/JSON to inspect individual cases.
3. Related logs/stack traces on failure.
4. Test runner/JDK version.
5. Links to fixtures and configuration.
6. Attempt/retry records.

### 15.1. HTML Reports and Screenshots

HTML reports, UI screenshots, or HTTP captures can help with debugging, but require access control and retention management. If they contain customer data, redaction or synthetic data is required.

## 16. Testing Layers in Java Migration

| Test class | Goal | Evidence to Store |
|---|---|---|
| Compile/build | Valid JDK and compiler flags | Build log, toolchain report |
| Unit | Business logic | JUnit XML, coverage when needed |
| Integration | DB/broker/framework/provider | Results, service versions |
| Contract | HTTP/event/gRPC compatibility | Contract files and verification |
| Binary/API | Public API compatibility | Bytecode/API diff |
| Runtime matrix | Both baseline and target JDKs run | Per-JDK reports |
| Security | TLS, authentication, dependency scan | Scan summary and exceptions |
| Performance | Throughput/latency/heap/GC | Raw metrics, GC logs, config |
| Deployment | Startup, canary, rolling, rollback | Deployment records |
| Data migration | Schema/backfill consistency | Revision, row counts, checks |
| Soak/resilience | Long-running reliability | Metrics, logs, incident triggers |

You cannot have only unit tests and assume all the remaining categories have been verified.

## 17. Multi-JDK Test Matrix

Suppose a product is built with JDK 21 using `--release 17` and claims to run on JDK 17/21:

| Artifact | Runtime | Test | Evidence |
|---|---|---|---|
| Hash A | JDK 17 update X | Unit | Report J17 |
| Hash A | JDK 21 update Y | Unit | Report J21 |
| Hash A | JDK 17 update X | Integration | DB/HTTP J17 |
| Hash A | JDK 21 update Y | Integration | DB/HTTP J21 |
| Hash A | Production-like image | Startup/performance | Runtime report |

`--release` restricts the API/bytecode of compiled source code, but **does not prove** that every third-party dependency and provider runs on the lowest runtime. Therefore, real runtime testing is required.

### 17.1. Multi-Release JAR

If an artifact contains `META-INF/versions/*`, different runtimes may load different implementations. You must test all supported JDKs instead of only testing the JDK used for compilation.

### 17.2. Each Artifact Must Be Linked to Its Own Tests

If the pipeline builds separate artifacts for x64/ARM64 or different release channels, do not carry over results from Hash A to Hash B without explicitly recording it.

## 18. Storing API and Framework Compatibility Reports

When upgrading dependencies or migrating `javax.*` to `jakarta.*`, public method descriptors can change.

For example:

~~~java
public void register(javax.servlet.Filter filter);
~~~

then:

~~~java
public void register(jakarta.servlet.Filter filter);
~~~

These are two different binary type names, creating risks for already-compiled consumers.

Descriptors can be inspected with:

~~~bash
javap -classpath previous.jar -p -s com.example.PublicApi
javap -classpath candidate.jar -p -s com.example.PublicApi
~~~

In addition to text diffs, you should use an appropriate API compatibility tool if the library guarantees a binary contract.

### 18.1. Storing All Compatibility Layers

~~~yaml
compatibility:
  source: "PASS_OR_REVIEW"
  binary_api: "PASS_OR_REVIEW"
  http_contract: "PASS_OR_REVIEW"
  event_schema: "PASS_OR_REVIEW"
  database_schema: "PASS_OR_REVIEW"
  runtime_behavior: "PASS_OR_REVIEW"
~~~

An HTTP service can preserve its wire contract despite using a different Java/Jakarta generation, whereas within the same JVM classloader, a binary name mismatch is a separate problem.

### 18.2. Consumer/Provider Versions

In a rolling deployment, the new provider must preserve the contract for old consumers; new producers may send data to old consumers. Store the **V1→V2 and V2→V1** test result matrix when the topology permits.

## 19. Storing DB Schema and Data Migration Evidence

A schema migration can follow:

~~~mermaid
flowchart TD
    A["Schema S1, app V1"] --> B["Expand S2: add columns/tables"]
    B --> C["V1 still reads/writes S2"]
    C --> D["V1/V2 running together"]
    D --> E["Backfill and data verification"]
    E --> F["Drain old consumers"]
    F --> G["Contract S3: remove old structure"]
~~~

At each step, you should store:

- Migration scripts and checksums.
- DB engine/version.
- Before/after revisions.
- Migration execution ID.
- Row counts and constraint checks.
- Backfill job version.
- Lock/transaction impact.
- V1/V2 tests on the same schema.
- Backup/snapshot reference.
- Rollback boundaries.

### 19.1. Do Not Put Raw Production Data into the Artifact Store

Instead of uploading database dumps containing PII, store aggregate validation metrics, migration revisions, snapshot references, and redacted reports. If a dump must be retained, a restricted repository with approved encryption, auditing, and retention must be used.

### 19.2. Schema Rollback and App Rollback Are Not the Same

V2 may have already written data in a new format; V1 after a rollback might not understand it. You must test and clearly record the status `ROLLBACK_SAFE` or `ROLL_FORWARD_ONLY`, along with the reason and recovery plan.

## 20. Performance Evidence Must Include Raw Data

Upgrading the JDK can change the default GC, JIT, classloading, threading, and memory footprint. A performance report should record:

- Artifact hash and JDK update/vendor.
- GC collector and heap flags.
- CPU/memory limits and container image.
- Dataset/workload and concurrency.
- Warmup duration.
- Measurement duration/repetitions.
- Throughput.
- p50/p95/p99/max latency.
- Error/timeout rate.
- CPU, throttling, and RSS/native memory.
- GC pause histogram/GC log.
- Dependencies such as DB/network.

### 20.1. Do Not Store Only Chart PNGs

Chart images aid presentation, but do not allow recalculating percentiles or filtering outliers. You must keep **raw measurements** (CSV/JSON/Parquet as appropriate), chart-generation scripts/configs, and summaries.

### 20.2. Sample Summary

~~~yaml
benchmark:
  artifact_sha256: "EXACT_HASH"
  jdk: "EXACT_JDK_BUILD"
  collector: "G1"
  workload: "orders-load-profile"
  warmup_minutes: 10
  measurement_minutes: 20
  metrics:
    throughput_rps: 2500
    p99_ms: 180
    error_rate_pct: 0.1
  raw_data: "tests/performance/requests.csv"
  gc_log: "tests/performance/gc.redacted.log"
~~~

These figures are illustrative only.

### 20.3. Compare Across Matching Environments

If the baseline ran on larger CPUs than the candidate, comparing p99 is unfair. Fully record the test environment and use the same workload, warmup, and resource profile whenever possible.

## 21. Storing JDK Internals/JPMS Compatibility Results

Migration tasks may require removing:

- `sun.*`/`com.sun.*` internal API usage.
- Reflection into non-public JDK packages.
- `--add-opens`/`--add-exports` workarounds.
- Modules that have been removed from the JDK.
- Third-party agents/bytecode tools that do not support the new classfile version.

Useful evidence:

~~~bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
jdeps --print-module-deps --class-path "lib/*" app.jar
java --list-modules
~~~

`jdeps` analyzes static references and does not detect all reflection strings or dynamic loading. Store its output to track changes, but integration tests are still necessary.

### 21.1. Track Module Flags Step by Step

For example:

~~~text
Step A: 5 module-access workarounds
Step B: upgrade library => 3 remaining
Step C: upgrade framework => 1 remaining
Step D: remove last workaround => 0
~~~

You must record the **flag name, reason, owner, and test proving it can be removed**, not just the count.

## 22. Storing Canary and Production Rollout Results

When deploying, you need to record:

- Deployment ID.
- Environment/cluster/namespace.
- Artifact/image digest.
- JDK runtime image.
- Effective non-secret configuration.
- Feature flags.
- Schema migration revision.
- Canary percentage and routing rule.
- Readiness/health status.
- Error rate, latency, CPU/RSS/GC.
- Incident/alert timeline.
- Promotion/hold/rollback decision.

### 22.1. One Build Can Have Multiple Deployments

~~~text
ci-18421 => artifact Hash A
  ├── staging-231 => PASS
  ├── canary-prod-232 => HOLD
  └── canary-prod-233 => PASS after config adjustment
~~~

If configuration changed between deployments, that is an input variable that must be stored. Do not assume a new deployment means a new build.

### 22.2. Even a Small Canary Has System-Wide Impact

A canary receiving only 5% of HTTP traffic can still publish events to a shared broker or update a shared database affecting all consumers. Therefore, observability needs per-version metrics as well as coverage of systems using shared state.

## 23. Tying Release Decisions to Testing Criteria

Sample promotion decision:

~~~yaml
promotion:
  artifact_digest: "sha256:EXACT_HASH"
  build_id: "ci-18421"
  from: "staging"
  to: "production-canary"
  decision: "APPROVED"
  decided_at: "ISO_8601_TIMESTAMP"

gates:
  compile: "PASS"
  unit: "PASS"
  integration: "PASS"
  contract: "PASS"
  performance: "PASS"
  security: "PASS"

exceptions:
  - id: "WAIVER-123"
    status: "APPROVED_WITH_EXPIRY"
    owner: "Responsible team"
    reason: "Documented exception"

approval:
  role: "AUTHORIZED_RELEASE_ROLE"
  evidence_manifest: "manifest.yaml"
~~~

Do not record `APPROVED` without actual approval. The sample only illustrates the schema.

### 23.1. Waivers Must Be Explicit

When a test/gate cannot yet pass:

- Record the specific test.
- Reason.
- Risk.
- Responsible owner.
- Compensating controls.
- Due date.
- Who approved it.
- Whether promotion is permitted.

Do not enable a setting to skip tests and then erase traces from the report.

## 24. Rollback Requires Binary, Config, and State

A proper rollback record contains:

1. Last-known-good artifact checksum/digest.
2. Runtime image/JDK version.
3. Effective configuration snapshot.
4. Feature flag state.
5. Database/schema compatibility.
6. Queue/session/cache format.
7. Rollback runbook.
8. Rehearsal evidence.
9. Rollback triggers/decision owner.

~~~yaml
rollback:
  from_deployment: "prod-492"
  target_artifact: "sha256:LAST_KNOWN_GOOD_HASH"
  runtime_image: "registry.example/runtime@sha256:EXACT_DIGEST"
  config_snapshot: "config/last-known-good.redacted.yaml"
  database_compatibility: "VERIFIED_WITH_CURRENT_SCHEMA"
  rehearsal: "tests/deployment/rollback-report.xml"
  operator_runbook: "APPROVED_RUNBOOK_ID"
  status: "READY_FOR_APPROVAL"
~~~

An older artifact is not guaranteed to run against a newer schema. When rollback is unsafe, you need a roll-forward plan, adapter, backup/restore, or maintenance window.

### 24.1. Rollback Is Also a Test

The test should simulate:

~~~text
Deploy V1
-> Apply compatible schema expand
-> Deploy V2
-> V2 writes data/events
-> Rollback to V1
-> V1 reads/writes without corrupting data
~~~

Store the test run, artifact hashes, and schema revision.

## 25. Protecting Information in the Artifact/Evidence Repository

These records may contain sensitive data:

- Internal endpoints and network topology.
- Dependency vulnerabilities.
- Access tokens/passwords in logs.
- PII in HTTP captures.
- Heap/JFR recordings.
- Signing-related metadata.
- Certificates and customer information.

You should apply:

- Role-based access control.
- Encryption at rest/in transit.
- Audit logs for access/mutations.
- Redaction before upload.
- Appropriate retention.
- Backup/restore.
- Immutable objects/versioning where supported.
- Separation of public binaries from restricted diagnostics.
- No raw dumps placed in public CI artifacts.

### 25.1. Classification by Sensitivity

| Category | Examples | Governance |
|---|---|---|
| Public release | Published installer, public checksum | Published after approval |
| Internal build | Test binary, dependency graph | Internal permissions |
| Restricted diagnostics | Logs with PII, JFR | Restricted permissions, specific retention |
| Highly sensitive | Heap dump, key material | Avoid collecting unless necessary; specially controlled store |

Do not assume that a file named `gc.log` is definitely harmless.

### 25.2. Secret References Instead of Values

When reproducibility is needed, record the **secret version ID** from the secret manager instead of recording the value. Do not use an arbitrary hash of a password as a safe substitute.

## 26. Retention Policy: Do Not Store Indefinitely

Categories that typically need longer retention:

- Production artifacts and checksums.
- Release/provenance manifests.
- Test gate summaries.
- Deployment/approval records.
- Last-known-good binaries/configs.
- Schema migration scripts and references.
- Open incident evidence.

Categories that can have shorter retention:

- Experimental builds.
- Verbose compiler logs.
- Repeated raw performance captures.
- Failed temporary artifacts not serving an investigation.
- High-volume debug logs.

Specific retention periods depend on legal, security, budget, and rollback requirements. You should not pick a single day count for every project.

### 26.1. Recovery Must Be Tested

A good archive policy does not stop at "uploaded", it must verify:

- Files can be read back.
- Checksums still match.
- References in the manifest are not broken.
- On-call operators have access when needed.
- Backups/replicas are still working.
- Retention does not delete last-known-good too early.

## 27. Mutable Pointers and Immutable Evidence

A dashboard can point:

~~~text
stable -> ci-18421 / sha256 A
canary -> ci-18429 / sha256 B
last-known-good -> ci-18410 / sha256 Z
~~~

The pointers can change during promotion, while A/B/Z must be objects with immutable IDs.

If the repository allows overwriting the same coordinates, a locking/control policy is needed to prevent altering history without an audit trail.

### 27.1. Signed Metadata and Attestation

Build provenance/signatures can attest to the builder, source, and artifact digest under a policy. However, you must verify:

- Which identity does the signature belong to?
- What artifact digest was signed?
- Which trust root/verification policy applies?
- Does the provenance accurately describe the inputs/build steps?
- Does the deployment gate verify the signature or merely store the signature file?

Storing a signature without a way to verify it does not guarantee a secure release chain.

## 28. Reproducibility: Same Source Does Not Guarantee Same Bytes

Artifacts can differ due to:

- ZIP/JAR timestamps.
- File ordering.
- Generated source timestamps.
- Build paths.
- Dynamic dependency versions.
- JDK/OS/toolchain.
- Locale/timezone.
- Native build tools.
- Signing timestamps.
- Platform-specific packaging.

### 28.1. Reproducible Builds vs. Different Runtimes

A build reproducing identical bytes does not mean production behavior will be identical if the JDK, DB, config, or traffic differs.

Conversely, when a native installer requires a new timestamp and the checksum changes, record the mapping between the signed/unsigned artifact, provenance, and test evidence; do not attempt to alter hashes to make them look the same.

## 29. Illustrative Evidence Collection Script

A shell skeleton for a Linux pipeline after build/test:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

STEP_ID="JAVA-MIG-04"
BUILD_ID="ci-18421"
ROOT="evidence/$STEP_ID/$BUILD_ID"

mkdir -p "$ROOT/artifacts" "$ROOT/build" "$ROOT/tests"

cp build/libs/orders.jar "$ROOT/artifacts/orders.jar"

git rev-parse HEAD > "$ROOT/build/source-commit.txt"
java -version 2> "$ROOT/build/java-version.txt"
javac -version 2> "$ROOT/build/javac-version.txt"
./gradlew --version > "$ROOT/build/gradle-version.txt"

sha256sum "$ROOT/artifacts/orders.jar" \
  > "$ROOT/artifacts/orders.jar.sha256"

# Copy JUnit output if generated by the test runner.
cp -R build/test-results/test "$ROOT/tests/unit"

# Next steps in a real pipeline:
# generate manifest, redact sensitive data,
# verify required evidence, and upload immutably.
~~~

This is **not a complete production script**. It uses hardcoded IDs and does not yet enforce permissions, source cleanliness, redaction, retention, or upload/readback. Those parts must be automated in real-world usage.

### 29.1. PowerShell Checksum

~~~powershell
$artifact = "build\libs\orders.jar"
$hash = Get-FileHash -LiteralPath $artifact -Algorithm SHA256
$hash.Algorithm
$hash.Hash
~~~

Whether CI runs on Windows or Linux, checksums should be recorded in a unified manifest schema.

### 29.2. Do Not Lose Evidence When Tests Fail

In CI, configure the upload/archiving step appropriately so logs/reports are kept even when tests fail, but never allow the upload logic to turn a failed test step into a release PASS.

## 30. Pipeline with Per-Step Evidence Gates

~~~mermaid
flowchart TD
    A["Step N: scope + acceptance criteria"] --> B["Capture source/build inputs"]
    B --> C["Build immutable binary"]
    C --> D["Hash + manifest"]
    D --> E["Run unit/integration/contract/runtime tests"]
    E --> F["Archive reports and redacted config"]
    F --> G{"Required gates passed?"}
    G -->|No| H["HOLD, store failed evidence"]
    H --> A
    G -->|Yes| I["Deploy staging/canary with same digest"]
    I --> J["Store runtime telemetry"]
    J --> K{"SLOs and invariants met?"}
    K -->|Yes| L["Promote and keep rollback artifacts"]
    K -->|No| M["Rollback/hold and incident record"]
    L --> N["Step N+1"]
~~~

### 30.1. Do Not Rebuild Before Production

The artifact tested in staging should be promoted by checksum/digest. If a rebuild is mandatory, a corresponding release record and verification must be created for the new binary.

### 30.2. Separate the Test Gate from Evidence Upload

When tests fail, archiving can still succeed. The pipeline needs to reflect:

~~~text
TEST_STATUS=FAIL
EVIDENCE_ARCHIVE_STATUS=SUCCESS
RELEASE_GATE=BLOCKED
~~~

This is a valid state; do not report a release PASS merely because the evidence was saved.

## 31. Multi-Stage Java 11 to 21 Migration Example

Suppose the Orders application migrates from Java 11 to 21.

### Step A — Upgrade Build Tool, Keep Java 11 Target

~~~text
Compiler JDK: 21
Compiler --release: 11
Runtime matrix: Java 11 and Java 21
Framework: unchanged
~~~

Store:

- Gradle/Maven Wrapper and plugins.
- Compiler flags/toolchain.
- Artifact hash A.
- Unit/integration test reports on both runtimes.
- Dependency lockfiles.
- New compiler warnings.

### Step B — Upgrade Dependencies, Remove Internal APIs

~~~text
Compiler JDK: 21
Compiler --release: 17
Updated libraries
Reduce --add-opens/--add-exports workarounds
~~~

Store:

- Dependency graph diff.
- `jdeps` report.
- Public API diff.
- Before/after runtime flags.
- Artifact hash B and test results.

### Step C — Upgrade Framework/Jakarta

~~~text
Framework: generation supporting the new JDK
Servlet/JPA: jakarta.* if required by framework
Application server: compatible generation
~~~

Store:

- WAR/container digest.
- Provider/server version.
- HTTP/API consumer contract tests.
- DB migration compatibility.
- Annotation processor/generated source configuration.
- Mixed-version V1/V2 test results.

### Step D — Java 21 Runtime and Canary

~~~text
Runtime JDK: exact approved update
GC: verified actual collector
Deployment: staged canary
~~~

Store:

- Runtime image digest.
- Effective JVM flags/heap.
- GC logs and benchmark.
- Canary metrics and decision.
- Rollback rehearsal.
- Production deployment record.

### 31.1. Sample Tracking Table

| Step | Artifact | Test gate | Deploy gate | Decision |
|---|---|---|---|---|
| A | Hash A | PASS | PASS | Proceed |
| B | Hash B | PASS | PASS | Proceed |
| C | Hash C | PASS | HOLD | Investigate |
| C2 | Hash D | PASS | PASS | Proceed |
| D | Hash E | PASS | PASS | Promote |

This is an example of a tracking structure, not an actual run result. Each `PASS`/`HOLD` must point to a specific report.

### 31.2. Keep Failed Steps for Investigation

If the initial Step C failed because Hibernate/provider did not match the Jakarta generation, the Hash C record and stack traces help prove the fix in C2 rather than guessing from scratch.

## 32. Comparison Table Between Two Migration Steps

| Attribute | Step N | Step N+1 | Reason to Check |
|---|---|---|---|
| Compiler JDK | JDK A | JDK B | Different javac/plugins? |
| `--release` | 11 | 17 | Bytecode/API baseline changed |
| Dependency lock | Lock A | Lock B | Which libraries were upgraded? |
| Runtime image | Digest A | Digest B | Different OS/JDK/TLS? |
| GC | Parallel | G1 | Default/explicit behavior |
| Heap limit | 2 GiB | 2 GiB | Same memory budget? |
| Unit tests | Report A | Report B | New failures/skips? |
| Integration tests | Report A | Report B | DB/framework changes |
| Contract tests | Report A | Report B | Consumer compatibility |
| p99 latency | Metric A | Metric B | Compared under same workload? |
| API binary | Baseline | Candidate | Method descriptors changed? |
| DB revision | V33 | V34 | Can old code read it? |

The table does not by itself prove causality. It simply lists **the variables that changed** for systematic investigation.

## 33. When Evidence Is Missing: Record Explicitly Instead of Guessing

A test may require an HSM, external database, or multi-region setup that is not yet ready. The proper process:

1. Record the test ID.
2. Record the status `NOT_RUN`/`BLOCKED`.
3. Record the reason.
4. Record the risk.
5. Record the owner.
6. Record the conditions required for promotion.
7. Attach a waiver if policy allows.
8. Do not assign a fake PASS label.

Example:

~~~yaml
exception:
  gate: "hardware-hsm-integration"
  result: "NOT_RUN"
  reason: "Approved HSM test environment unavailable"
  risk: "Hardware signing behavior unverified"
  owner: "Security integration team"
  mitigation: "Block production promotion until this suite runs"
  decision: "HOLD"
~~~

An honest report with explicit gaps is more valuable than an all-PASS report without test evidence.

## 34. Investigating Production Regressions from Archived Records

Suppose some pods throw `NoSuchMethodError` after a JDK upgrade.

A good evidence system allows you to:

1. Retrieve the deployment/pod image digest.
2. Locate the JAR checksum inside the image.
3. Open the build manifest.
4. Inspect the dependency graph and toolchain.
5. Compare public API class descriptors against last-known-good.
6. Inspect the actual APIs/providers loaded by the server.
7. Check which test suites did or did not cover that flow.
8. Decide on rollback/roll-forward.
9. Store an incident summary and add a regression test.

If only the `latest` tag remains, identifying the faulty binary may no longer be certain.

### 34.1. Sensitive Diagnostic Data

Heap dumps, memory snapshots, thread dumps, and HTTP captures require separate privacy/security policies. Collect them only when truly necessary, with narrow access permissions and appropriate retention.

## 35. Common Mistakes

### 35.1. "Having the Git commit is enough to reproduce the artifact"

Not sufficient if the JDK, dependencies, plugins, or container base are not locked.

### 35.2. "The version name is enough to identify the JAR"

The same version label can contain different bytecode.

### 35.3. "CI is PASS so there's no need to store test reports"

You won't know which tests actually ran, were skipped, or were flaky.

### 35.4. "Source configuration is the effective configuration"

It can be overridden by Helm, env vars, JVM flags, and remote config.

### 35.5. "Storing all environment variables is best"

It easily leaks secrets; record only necessary metadata and redact.

### 35.6. "Only successful builds need to be archived"

Failure logs help pinpoint the first step where a regression appeared.

### 35.7. "Rebuilding the same commit and deploying it will match the tested artifact"

Not guaranteed byte-for-byte, especially with dynamic dependencies and native packaging.

### 35.8. "The container tag latest is immutable"

Not in every registry; use digests instead.

### 35.9. "Keep only performance chart PNGs"

Raw data, workload, and runtime config are needed to recalculate metrics.

### 35.10. "Rollback only needs the old container image"

Database, event/session state, and config may no longer be compatible.

### 35.11. "A successful artifact upload means it is forever retrievable"

Retention, access permissions, and corruption still need to be managed.

### 35.12. "The longer you keep everything, the better"

Not for sensitive data; policies should balance value and risk.

### 35.13. "Every skipped test is a PASS"

No. Gaps require explicit decisions.

### 35.14. "Having a digital signature means having complete provenance"

You need identity verification, builder, artifact digest, and policy enforcement.

### 35.15. "Canary monitoring only needs the overall error rate"

A small canary with a high error rate can be masked by the overall fleet; break down metrics by version.

## 36. Checklist for Each Migration Step

### Source and Build

- [ ] Have migration step ID, goal, and acceptance criteria.
- [ ] Have Git commit and clean source status.
- [ ] Have build ID and timestamp.
- [ ] Record compiler JDK vendor/update and `--release`.
- [ ] Record build plugin/Wrapper versions.
- [ ] Have resolved dependencies/lockfiles/SBOM when needed.
- [ ] Record artifact checksum and container digest.
- [ ] Do not silently rebuild between testing and deployment.

### Configuration

- [ ] Record effective non-secret config.
- [ ] Record JVM flags/GC/heap/JPMS options.
- [ ] Record server/framework/provider versions.
- [ ] Record OS/CPU/memory/container limits.
- [ ] Record feature flags.
- [ ] Redact secrets/PII.
- [ ] Have secret references instead of secret values.

### Testing

- [ ] Store unit test report.
- [ ] Store integration tests.
- [ ] Store API/event contract tests when relevant.
- [ ] Store JDK/runtime test matrix.
- [ ] Store binary/API diff if there are public changes.
- [ ] Store performance raw data and config if there is SLO risk.
- [ ] Record skipped/failed/flaky/not-run tests.
- [ ] Every report points to the exact artifact and environment.

### Deployment and Rollback

- [ ] Store staging/canary deployment ID.
- [ ] Verify the actually running digest.
- [ ] Have promotion/hold/rollback decision.
- [ ] Record runtime metrics/alerts.
- [ ] Have last-known-good artifact/config.
- [ ] DB/schema/state compatibility has been evaluated.
- [ ] Have rollback rehearsal evidence when required.
- [ ] Archive repository has retention/access policy and readback verification.

## 37. Approver Checklist

Before promoting, you must be able to answer:

1. **Which artifact will be promoted to production?** Is there a checksum/digest?
2. **Which source commit was that artifact built from?**
3. **What are the compiler JDK, target release, and runtime JDK?**
4. **Where do dependencies and configs differ from the baseline?**
5. **Which test suites were run?** Which tests were skipped/waived?
6. **Is there evidence of contract, database, and runtime compatibility?**
7. **Did performance SLOs and security gates pass?**
8. **Did staging/canary use this exact digest?**
9. **Which artifact/config do we roll back to?** Do the DB/state allow it?
10. **Can the evidence be retrieved later according to the retention policy?**

If you cannot answer these core questions, a green pipeline is not enough to declare the migration step safe.

## Conclusion

**Every Java upgrade step must leave a traceable record**: source commit, toolchain, resolved dependencies, immutable artifacts and checksums, redacted effective configuration, test reports, deployment records, promote/hold/rollback decisions, and runtime monitoring evidence.

The sustainable strategy is **build once, test that exact artifact, promote by digest, store a manifest linking all evidence, keep last-known-good along with its configuration, and evaluate state/schema rollback**. Combining access controls, retention, signing/provenance, and readback checks turns migration history into a practical operational tool: able to reproduce bugs, compare steps, explain decisions, and recover when a new JDK causes a regression.
