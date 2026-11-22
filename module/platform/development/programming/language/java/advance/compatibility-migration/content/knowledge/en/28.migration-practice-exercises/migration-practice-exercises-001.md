# Creating a Compatibility Matrix and Current-State Report for a Java Project

When starting **Java Advance Compatibility Migration**, the first question should not merely be "Will switching `JAVA_HOME` to JDK 21 run?". A Java system also depends on the build tool, compiler target, runtime libraries, application server, Java agents, bytecode readers, native libraries, TLS security, data systems, and deployment method. Upgrading the JDK is only safe when you know **which components have been verified on which versions, where the evidence resides, and what gaps remain**.

This exercise guides you through creating two concrete outputs:

1. **Compatibility matrix**: a table cross-referencing each component, environment, and JDK version with verified, evidence-backed results.
2. **Current-state report**: a document summarizing the baseline, risks/gaps, readiness level, remediation priorities, and measurable migration next steps.

For practice, we use a hypothetical project **OrderHub**, a Java order-processing service. All figures, system names, versions, test results, and report paths in the example are **illustrative data**, not results executed on a real repository. When applying this to your own project, replace them with actual verification results.

## 1. Learning objectives and deliverables

After this lesson, you can:

- Distinguish **the JDK running the build tool**, **compiler/toolchain**, **bytecode target**, **test JVM**, and **production JVM**.
- Build an inventory of dependencies and integrations that could impede migration.
- Construct a matrix combining JDKs, build tools, libraries, containers, test suites, and deployment environments.
- Gather evidence from Maven/Gradle, `java`, `javap`, `jdeps`, runtime logs, and CI.
- Record `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`, or `UNKNOWN` statuses without turning assumptions into conclusions.
- Associate each gap with a risk level, owner, remediation action, and verification criteria.
- Write a current-state report sufficient for approvers to decide: **ready for canary**, **needs blocker resolution**, or **needs additional evidence**.

### 1.1. Suggested deliverables

In a real project, you can use a structure like:

```text
migration-assessment/
├── 01-inventory.csv
├── 02-compatibility-matrix.csv
├── 03-risk-register.csv
├── 04-current-state-report.md
├── 05-evidence-index.md
└── evidence/
    ├── jdk-runtime.txt
    ├── maven-version.txt
    ├── dependency-tree.txt
    ├── jdeps-report.txt
    ├── unit-tests.txt
    ├── integration-tests.txt
    └── baseline-metrics.txt
```

This is only a **suggested structure**. You may use Google Sheets, Excel, Markdown, Jira, a database, or your organization's evidence management system. What matters is that **every conclusion in the report traces back to its evidence source**.

### 1.2. Definition of Done

An exercise is considered complete when:

- Scope is defined: application, current version, target JDK, integrated systems.
- Every key conclusion cell has a status and evidence.
- Unverified items are marked `NOT_RUN`/`UNKNOWN`, never leaving readers with the false impression that they passed.
- A prioritized risk list with owners exists.
- There is a path for resolving blockers, re-testing, and proposed rollout/rollback steps.
- Every piece of evidence includes its timestamp, environment, and corresponding artifact/version.

## 2. Hypothetical project scenario: OrderHub

OrderHub is an order management service of a hypothetical organization, comprising a REST API, business processing, PostgreSQL persistence, and event publishing to a broker.

```text
Client / Gateway
       |
       v
OrderHub REST API
       |
       +--> Database: PostgreSQL
       |
       +--> Outbound Payment HTTPS API
       |
       +--> Event broker
       |
       +--> Scheduled reconciliation job
```

Initial assumptions (must be verified when used on a real project):

| Attribute | Hypothetical data |
|---|---|
| Application name | OrderHub |
| Current production runtime | JDK 11 |
| Target runtime | JDK 17 first, JDK 21 later |
| Build tool | Maven Wrapper and Maven Compiler Plugin |
| Framework | Spring Boot 2.7.x |
| Servlet API | `javax.servlet.*` generation |
| Data access | JDBC/JPA |
| Database | PostgreSQL |
| Message integration | Broker and client library |
| Outbound network | HTTPS, one partner with mTLS |
| Deployment | Container image |
| CI | Unit tests, integration tests, Docker build |
| Monitoring | Java APM agent |
| Native dependency | Possible — unverified |

**Do not infer JDK support levels from the Spring Boot name or Maven major version alone.** Check the official support matrix of the exact release and run real tests. This lesson focuses on **how to verify**, not on certifying an unverified version combination.

### 2.1. Scoped migration goal

The first phase aims only to:

> Prove OrderHub can be built and run on JDK 17 without changing public REST/event schemas, database schemas, or business processing logic.

The subsequent phase considers JDK 21, framework upgrades, and Javax → Jakarta migration if needed.

A narrow scope avoids mixing multiple causes:

```text
Step A: inventory and standardize evidence
Step B: unit/integration tests on JDK 17
Step C: upgrade incompatible dependencies
Step D: run JDK 17 container in staging/canary
Step E: consider JDK 21 + framework upgrade per separate plan
```

### 2.2. Questions that must be answered

- Which Java version are source/bytecode currently compiled for?
- Which JVM is the Maven process running under?
- Which JVM are tests running on?
- Which Java version do the production image and application process actually use?
- Which dependencies are incompatible with the new runtime?
- Can Java agents or plugins read the new class files?
- Are JDK internal APIs or reflection affected by encapsulation in use?
- Do HTTPS/mTLS work with the target JDK's truststore and security properties?
- Which tests ran on the final artifact instead of freshly built source?
- Can we roll back to the old runtime if data formats have not changed?

## 3. A compatibility matrix is not a "yes/no" table

A useful matrix needs at least three dimensions:

1. **Subject under verification** — component or integration.
2. **Version/environment** — current JDK, candidate JDK, OS/container, build/runtime.
3. **Evidence-backed outcome** — PASS/FAIL/BLOCKED/NOT_RUN/UNKNOWN, test ID, logs, and execution date.

A cell saying "JDK 21: Yes" fails to state who tested, which test ran, in what environment, and up to which patch version. When a dependency or JDK update changes, that conclusion may no longer hold.

### 3.1. Standard statuses

| Status | Meaning | Can serve as a gate? |
|---|---|---|
| `PASS` | Verification executed and met stated criteria | Yes, while evidence remains valid |
| `FAIL` | Verification executed and failed | Blocks if within mandatory scope |
| `BLOCKED` | Cannot run/complete because a precondition is blocked | No |
| `NOT_RUN` | Verification has not been conducted yet | No |
| `UNKNOWN` | Insufficient facts to conclude or test method not yet determined | No |
| `NOT_APPLICABLE` | Does not apply, with reason explained | Can be excluded from denominator if justified |

`PASS` must be tied to **test results and verified scope**. It does not mean every behavior and every client path has been proven compatible.

### 3.2. Do not equate "vendor claims supported" with "verified"

Two separate fields can be used:

```text
Vendor support status: SUPPORTED / UNSUPPORTED / UNKNOWN
Local test status: PASS / FAIL / BLOCKED / NOT_RUN / UNKNOWN
```

A library may be declared by the vendor as supporting JDK 21, yet your application still fails due to truststore or conflicting dependencies. Conversely, a library release without declared support might temporarily pass a smoke test, yet that **does not make it supported for production**.

### 3.3. Separate mandatory from optional

Example:

- Payment HTTPS connection: **mandatory**.
- End-of-month CSV export: **mandatory**, yet untested if the cycle has not run.
- Cache optimization benchmark: **supplementary**, does not necessarily block a runtime-only step.
- Migrating to virtual threads: **out of scope** for the first phase.

This classification prevents reporting "100% pass" when critical items have not executed.

## 4. Step 1 — Gather initial inventory

Before building the matrix, compile a complete list of components that could affect JDK upgradeability.

### 4.1. Inventory categories

| Category | What to record |
|---|---|
| Build | Maven/Gradle version, Wrapper, plugins, daemon/build JVM |
| Compilation | Java compiler version, toolchain, `--release`/source/target |
| Runtime | JDK vendor/update, Java home, OS/architecture, container digest |
| Dependencies | group/artifact/version, direct/transitive, scope, BOM |
| Java EE/Jakarta | Servlet/JPA/JAX-RS/Validation namespace and providers |
| Bytecode tools | ASM, Byte Buddy, JaCoCo, Mockito, enhancement/agents |
| Security | TLS versions, cipher suites, certpath policy, truststore/keystore |
| JVM internals | `sun.*`, `com.sun.*`, reflection, `--add-opens` |
| Native | JNI/JNA libraries, OS ABI, CPU architecture |
| Data integration | Database driver, ORM, message broker, serialization |
| Operations | JVM flags, logging, monitoring, rollout, rollback |
| Testing | Unit, integration, contract, load, canary, and latest status |

### 4.2. Sample inventory CSV

```csv
component_id,category,name,observed_version,used_by,environment,owner,evidence_id,notes
CMP-001,runtime,JDK,11.0.x,OrderHub,production,Platform,EVD-001,Update number requires verification
CMP-002,build,Maven,3.x,OrderHub,CI,BuildTeam,EVD-002,Wrapper in repository
CMP-003,framework,Spring Boot,2.7.x,OrderHub,all,AppTeam,EVD-003,Exact patch to record
CMP-004,api,Servlet API,javax generation,OrderHub,production,AppTeam,EVD-004,Container contract
CMP-005,agent,APM Java agent,unknown,OrderHub,production,Observability,,Needs inventory
CMP-006,security,Truststore,custom PKCS12,Outbound TLS,production,Security,EVD-006,Path and CA owner
```

In the example, the empty evidence field for the APM agent is a **gap**, not a pass signal. In real use, enforce a rule forbidding `PASS` when `evidence_id` is missing.

### 4.3. Add ownership information

A component may be managed by another team: platform team owns JDK images, security team owns CA truststores, app team owns source, vendor owns the APM agent.

If the inventory lacks owners, migration can stall when an external component needs upgrading.

## 5. Step 2 — Identify build JVM, compiler, and runtime JVM

A project may run Maven on JDK 17 while targeting Java 11 compilation, running tests on JDK 21, and running production on JDK 11. Do not record just one "Java Version" column.

### 5.1. On a workstation or CI

Linux/macOS:

```bash
java -version
javac -version
echo "$JAVA_HOME"
./mvnw -version
```

Windows PowerShell:

```powershell
java -version
javac -version
$env:JAVA_HOME
.\mvnw.cmd -version
```

If the repository lacks Maven Wrapper, run `mvn -version` from the controlled build environment.

### 5.2. Runtime of the real process

On a host/container, `java -version` in a shell may differ from the Java binary running the service. If the system allows, observe the command line, `java.home`, runtime version, or process metadata:

```java
public final class RuntimeFingerprint {
    public static void main(String[] args) {
        System.out.println("java.version=" +
                System.getProperty("java.version"));
        System.out.println("java.runtime.version=" +
                System.getProperty("java.runtime.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));
        System.out.println("java.home=" +
                System.getProperty("java.home"));
        System.out.println("os.arch=" +
                System.getProperty("os.arch"));
    }
}
```

When executed inside the application process itself, metadata carries more weight than reading an external shell.

### 5.3. Maven Compiler Plugin and release target

Example configuration:

```xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>
```

Configuring `release` requires a compiler supporting the option and is affected by Maven Compiler Plugin/toolchain. It constrains source level, class file level, and Java SE platform APIs during that compilation.

It **does not** guarantee that third-party JARs were compiled for Java 11 or that the test JVM also uses JDK 11.

### 5.4. If the project uses Gradle

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew dependencies --configuration runtimeClasspath
```

In `build.gradle`:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

This example can use JDK 17 `javac` to emit Java 11 target class files. **The JVM running the Gradle daemon may still differ from the compiler toolchain.**

### 5.5. Output of this step

Record completely:

```text
EVD-001:
  environment: CI linux-x64
  build_tool: Maven Wrapper
  build_jvm: JDK 17
  compiler_jdk: JDK 17
  compiler_release: 11
  test_jvm: requires verification
  production_jvm: JDK 11.0.x
  captured_at: <timestamp>
```

Do not assume `test_jvm = build_jvm` without checking Surefire/Failsafe/toolchains and the actual JVM executing tests.

## 6. Step 3 — Capture the dependency graph

### 6.1. Maven

Run from the project root:

```bash
./mvnw dependency:tree
```

Save output if needed:

```bash
./mvnw dependency:tree -DoutputFile=dependency-tree.txt
```

Depending on the plugin/version, output can include scopes, selected versions, and some omitted dependency info. Run with **the exact profiles and modules** used by the CI production build.

To inspect a relevant library:

```bash
./mvnw dependency:tree -Dincludes=net.bytebuddy:byte-buddy
./mvnw dependency:tree -Dincludes=org.ow2.asm:asm
```

### 6.2. Gradle

```bash
./gradlew dependencies --configuration runtimeClasspath
```

To analyze a version:

```bash
./gradlew dependencyInsight \
  --dependency byte-buddy \
  --configuration testRuntimeClasspath
```

Inspect `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`, build plugin classpaths, and packaged artifacts as needed.

### 6.3. The build graph does not always match the production classpath

For example, Gradle/Maven resolves the right JDBC driver, yet a Dockerfile or application server copies an older JAR into a shared library directory. Runtime can still load the wrong class version.

Observe:

```text
Build output
    |
    +--> compile/test classpaths
    |
    +--> packaged JAR/WAR
    |
    +--> container image filesystem
    |
    +--> classloader of the running process
```

Those are four places that can diverge.

### 6.4. Listing JAR/WAR contents

```bash
jar tf target/orderhub.jar
```

For a WAR:

```bash
jar tf target/orderhub.war
```

For framework-packaged executable JARs, dependencies may live inside separate nested JAR directories. Check the actual layout produced by your packaging plugin.

## 7. Step 4 — Inspect bytecode and JDK APIs

### 7.1. Class file major version

Use:

```bash
javap -verbose \
  -classpath target/classes \
  com.example.orderhub.Main
```

Find the `major version` line. Common milestones:

| Java target | Major version |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

Bytecode major 61 only shows the class file targets Java 17; it does not assert that every runtime dependency is JDK 17 compatible or that code avoids dynamic reflection.

### 7.2. Scan dependencies on JDK internals

With a JDK providing `jdeps`:

```bash
jdeps --jdk-internals target/orderhub.jar
```

When the artifact has dependencies outside the JAR:

```bash
jdeps --jdk-internals \
  --class-path "lib/*" \
  target/orderhub.jar
```

Some applications use fat/executable JARs with nested dependencies; running `jdeps` on the outer JAR file may not scan all nested JARs as desired. Extract or assemble appropriate classpaths for analysis.

### 7.3. Limitations of `jdeps`

It analyzes static references and is not guaranteed to find all:

- `Class.forName("sun.misc...")` via string.
- Reflection invoking private JDK members.
- Native/JNI.
- Dynamically loaded `ServiceLoader` providers.
- Annotation-driven integration.
- Scripts/configuration generating class names.
- Instrumentation from Java agents.

Therefore, `jdeps` finding no internal APIs **does not mean compatibility is guaranteed**.

### 7.4. Record findings as inventory rows

```text
component_id: CMP-009
category: jdk-internals
finding: Static dependency to internal JDK API
status: FAIL
evidence_id: EVD-009
severity: HIGH
owner: AppTeam
next_action: Replace with supported Java SE API
```

Use `FAIL` only if a specific criterion was checked and failed; if the artifact has not been scanned yet, record `BLOCKED` or `NOT_RUN`.

## 8. Step 5 — Check Java EE/Jakarta APIs

Changing the JDK runtime **does not equal** migrating from Java EE to Jakarta EE.

### 8.1. Distinguish namespaces

- Java EE and Jakarta EE 8 use many APIs in the `javax.*` namespace.
- Jakarta EE 9 onward moved Jakarta EE APIs to `jakarta.*`.
- Java SE packages such as `javax.net.ssl`, `javax.crypto`, `javax.sql`, and `javax.xml.parsers` **did not** change accordingly.

Example:

```java
// Java EE/Jakarta EE 8 generation Servlet:
import javax.servlet.Filter;

// New generation Jakarta Servlet:
import jakarta.servlet.Filter;
```

The two interfaces are two distinct binary types.

### 8.2. Matrix questions

| Question | If unclear, what to record? |
|---|---|
| Which Servlet API level does the target container use? | `UNKNOWN` |
| Which Jakarta EE generation does the framework version support? | `UNKNOWN` |
| Are there filters/listeners compiled against Javax? | `NOT_RUN` for verification check |
| Are there JPA entities using `javax.persistence.*`? | Inventory finding |
| Are there REST/Validation providers from the older API generation? | Dependency gap |
| Has the WAR deployed successfully on the target container? | `NOT_RUN` if not yet tried |

For the hypothetical OrderHub, JDK 11 → 17 migration can be verified separately from upgrading Spring Boot 2.x → 3.x. If the real plan forces upgrading both simultaneously, classify **two independent risk groups**.

## 9. Step 6 — Check JSSE/TLS and truststores

A newer JDK may update disabled algorithms, certificate path constraints, or CA truststores. A runtime migration is verified only once critical secure connections have been tested.

### 9.1. Secure connection inventory

```csv
endpoint_id,host_role,requires_tls,mtls,trust_material_owner,status,evidence_id
TLS-001,Payment HTTPS API,yes,yes,SecurityTeam,NOT_RUN,
TLS-002,Internal inventory API,yes,no,PlatformTeam,NOT_RUN,
TLS-003,Message broker,yes,unknown,MessagingTeam,UNKNOWN,
```

For mTLS, verify all of:

- Client truststore trusts the server certificate chain.
- Client keystore contains the private key and certificate for client authentication.
- Server trusts the client CA.
- Hostname/SNI, validity, and EKU are valid.

### 9.2. Capture JDK policy

Example:

```java
import java.security.Security;

public final class SecurityReport {
    public static void main(String[] args) {
        for (String name : new String[] {
                "jdk.tls.disabledAlgorithms",
                "jdk.certpath.disabledAlgorithms"
        }) {
            System.out.println(name + " = " +
                    Security.getProperty(name));
        }
    }
}
```

Do not print passwords, private keys, or secrets. Run on the target JDK, compare policies against the current JDK, and test TLS endpoints.

### 9.3. JSSE debugging in controlled environments

```bash
java -Djavax.net.debug=ssl,handshake -jar orderhub.jar
```

This is an example diagnostic command; logs can contain sensitive information and massive volume. Do not leave enabled long-term in production.

### 9.4. Classify errors by evidence

| Error | Hypothesis to test |
|---|---|
| `PKIX path building failed` | Missing trust chain/trust anchor or certpath constraints |
| `Algorithm constraints check failed` | Key/signature/disabled algorithms |
| `No appropriate protocol` | Incompatible TLS version/cipher |
| `No subject alternative DNS name matching` | Hostname/SAN mismatch |
| `Received fatal alert: bad_certificate` | Peer rejected certificate, possibly mTLS |

Do not fix errors by disabling `TrustManager` or hostname verification. **A connection is accepted only when it both works and properly validates identity and policy.**

## 10. Step 7 — Check agents, bytecode tools, and native libraries

A newer JDK affects not only application code; components that read bytecode can fail even when the JVM supports the new classfile.

### 10.1. Items to inventory

- Java APM/tracing/monitoring agents.
- Coverage agents such as JaCoCo.
- Mocking/proxy frameworks and Byte Buddy.
- ASM readers inside build plugins.
- ORM bytecode enhancement.
- Annotation processors.
- JNI/JNA/native drivers.
- Profilers, obfuscators, or security agents.

An `Unsupported class file major version 65` error can originate from an **old ASM parser**, even while the JDK 21 JVM runs classfile major 65 fine.

### 10.2. The matrix must track plugins/agents separately

```text
Row: Monitoring Java agent
Current version: unknown
Target: JDK 17 / JDK 21
Vendor support: UNKNOWN
Local startup test: NOT_RUN
Instrumentation correctness: NOT_RUN
Owner: Observability
Decision: BLOCKED until artifact/version identified
```

**Application dependencies and Gradle/Maven plugin dependencies have different classpaths**. Upgrading ASM in runtime dependencies will not necessarily fix a parser shaded inside a plugin/agent.

### 10.3. Native integration

For `.so`, `.dll`, `.dylib`, record:

- OS and architecture.
- Vendor-published JDK/ABI support.
- Native library file version/digest.
- Native load path.
- Mandatory test exercising code paths using JNI.
- Impact of the container base image/OS libraries.

A smoke test that never calls native functions is insufficient to prove compatibility.

## 11. Step 8 — Design a layered test suite

A good matrix specifies **which test suite** verifies each part.

### 11.1. Test categories

| Test ID | Test layer | Function |
|---|---|---|
| TST-001 | Compile | Project and annotation processors compile |
| TST-002 | Unit | Business logic and edge cases |
| TST-003 | Integration | Database, broker, and HTTP partners |
| TST-004 | Contract | REST/event/serialization backward compatibility |
| TST-005 | Binary | Old consumer JAR running against new provider |
| TST-006 | Security | TLS, mTLS, truststore, algorithm policies |
| TST-007 | Packaging | JAR/WAR/container image and launcher |
| TST-008 | Agent | Tracing, metrics, coverage/instrumentation |
| TST-009 | Native | JNI/JNA/OS integration |
| TST-010 | Load/performance | Throughput, p95/p99, heap, GC, pool waits |
| TST-011 | Rollback | Deploy old artifact and verify data compatibility |
| TST-012 | Scheduled paths | Batch/cron, retry, recovery/timeout |

These are illustrative IDs for consistent use in reports.

### 11.2. Baseline must precede candidate

If JDK 17 fails TST-003, you must know whether the JDK 11 baseline passed. A database credential failure occurring in both environments should not be reported as a Java 17 regression.

Model:

```text
Same source + same dependencies + same test fixture
          |
          +--> JDK 11 baseline
          |
          +--> JDK 17 candidate
          |
          +--> Compare failure and metrics
```

The "same" condition may not be strictly achievable if the old JDK does not support a newer build plugin; in that case, record **the exact difference** and potential confounding effects when comparing.

### 11.3. Test against the final artifact

Source-level unit tests are necessary, yet confirming deployment requires testing:

- Exact released JAR/WAR.
- Container image with the matching JDK update.
- Startup flags, truststores, and config mounts.
- Application server/launcher classloader.
- Embedded or mounted native libraries and agents.
- Per-environment credential/secret handling.

An artifact tested in CI may differ from the deployed container if the Dockerfile copies an older JAR or the base image changed.

## 12. Step 9 — Create the initial compatibility matrix

A *long-form* CSV format is easy to filter, import into Sheets/Excel, or analyze with scripts.

### 12.1. Proposed schema

| Column | Meaning |
|---|---|
| `row_id` | Immutable ID of a check |
| `component_id` | Links to inventory |
| `component` | Component name |
| `environment` | local/CI/staging/production |
| `jdk` | Actual JDK version/vendor |
| `scenario` | Behavior verified |
| `expected` | Pass criteria |
| `status` | PASS/FAIL/BLOCKED/NOT_RUN/UNKNOWN |
| `evidence_id` | Link to log/report/artifact |
| `tested_at` | Verification timestamp |
| `owner` | Responsible person/team |
| `risk_id` | Links to risk register |
| `next_action` | Next action |

You can add `build_id`, `git_sha`, `artifact_digest`, `os_arch`, `framework_version`, and `support_claim` if the project is complex.

### 12.2. Initial example CSV

```csv
row_id,component_id,component,environment,jdk,scenario,expected,status,evidence_id,tested_at,owner,risk_id,next_action
MAT-001,CMP-001,OrderHub,CI,JDK 11,unit tests,all tests pass,PASS,EVD-101,example-date,AppTeam,,retain baseline
MAT-002,CMP-001,OrderHub,CI,JDK 17,unit tests,all tests pass,PASS,EVD-102,example-date,AppTeam,,run integration
MAT-003,CMP-001,OrderHub,staging,JDK 17,production image smoke,health and core flows,NOT_RUN,, ,Platform,RISK-01,deploy candidate
MAT-004,CMP-005,APM agent,staging,JDK 17,tracing instrumentation,critical spans present,BLOCKED,, ,Observability,RISK-02,identify agent version
MAT-005,CMP-006,Payment mTLS,staging,JDK 17,mTLS handshake,server and client validated,NOT_RUN,, ,Security,RISK-03,prepare trust material
MAT-006,CMP-001,OrderHub,CI,JDK 21,compile and tests,all required tests pass,NOT_RUN,, ,AppTeam,RISK-04,plan later phase
```

**`PASS` statuses in the table are hypothetical to illustrate recording format**, not execution results. Rows currently `NOT_RUN` or `BLOCKED` must leave result evidence empty until evidence exists.

For real CSV files, standardize timestamp representation (ISO 8601), avoid writing `" "` as an empty value, and use a standard CSV parser when fields contain commas.

### 12.3. Pivot view for easier reviewer reading

The data above can be summarized as a pivot table:

| Item | JDK 11 baseline | JDK 17 candidate | JDK 21 candidate |
|---|---|---|---|
| Compile | PASS (example) | PASS (example) | NOT_RUN |
| Unit tests | PASS (example) | PASS (example) | NOT_RUN |
| Integration DB | PASS (example) | NOT_RUN | NOT_RUN |
| Payment mTLS | PASS (example) | NOT_RUN | NOT_RUN |
| APM agent | PASS (example) | BLOCKED | UNKNOWN |
| Container smoke | PASS (example) | NOT_RUN | NOT_RUN |
| Performance | Baseline available | NOT_RUN | NOT_RUN |
| Rollback rehearsal | NOT_APPLICABLE | NOT_RUN | NOT_RUN |

All `PASS` entries in this table are **hypothetical scenarios**. In a real report, each cell must trace back to a long-form record with an `evidence_id`.

### 12.4. Why keep both long-form and pivot?

- Long-form: supports audits, filtering, automation, and multi-environment data.
- Pivot: lets stakeholders quickly spot gaps by JDK.
- Risk register: shows who is handling each blocker and when to re-test.

Do not cram everything into a single cell containing a long paragraph, as it is hard to trace and update.

## 13. Step 10 — Record evidence with a consistent convention

A test result must carry **metadata identifying what it verified**.

Example:

```yaml
evidence_id: EVD-102
scenario_id: MAT-002
environment: ci-linux-x64
application_commit: "<git-sha>"
application_artifact: "orderhub.jar"
artifact_sha256: "<digest>"
jdk_vendor: "<vendor>"
jdk_version: "17.0.x"
build_tool: "Maven Wrapper"
command: "./mvnw -B test"
started_at: "<ISO-8601>"
completed_at: "<ISO-8601>"
exit_code: 0
result: PASS
log_location: "evidence/ci-jdk17-unit-tests.log"
notes: "Example only; replace with real execution data"
```

The `result: PASS` field is **a hypothetical value in the template**; it cannot be used verbatim without execution.

### 13.1. Evidence IDs can be referenced in the report

Example:

```text
MAT-002 -> EVD-102
MAT-005 -> no evidence yet
RISK-03 -> MAT-005
```

Readers can navigate from report → matrix → evidence. A finding lacking a source should carry `UNKNOWN` status or be marked **preliminary assessment**.

### 13.2. Evidence scope has limits

For example, `./mvnw test` exiting 0 does not automatically prove:

- Integration tests ran if test classes were not discovered.
- Tests executed on the intended JVM.
- Tests ran with the production truststore.
- Native code or mTLS was invoked.
- The production artifact was deployed.

When reporting, state **the exact test suites discovered and executed** along with the test runtime.

### 13.3. Protect data

Do not put private keys, truststore passwords, API tokens, access keys, user personal data, or production credentials into evidence. Logs require redaction and appropriate access controls.

## 14. Step 11 — Assess risks and gaps

Do not rank purely by counting FAIL cells. One `FAIL` on a critical payment path can outweigh dozens of optional `NOT_RUN` tests.

### 14.1. Simple risk model

Two 1–5 scales can be used:

- `Impact`: severity if an error occurs.
- `Likelihood`: reasonable probability based on evidence/unknowns.

```text
Risk score = Impact × Likelihood
```

Example:

| Score | Illustrative label | Action |
|---|---|---|
| 1–4 | Low | Monitor, can schedule in a future sprint |
| 5–9 | Medium | Create remediation and test plan |
| 10–16 | High | Must address before broad canary |
| 17–25 | Critical | Do not release without formal approval decision |

The thresholds are **illustrative conventions**, not mandatory standards. Follow your organization's risk framework if one exists.

### 14.2. Sample risk register

| Risk ID | Issue | Impact | Likelihood | Score | Owner | Mitigation |
|---|---|---:|---:|---:|---|---|
| RISK-01 | JDK 17 container has not passed smoke test | 4 | 3 | 12 | Platform | Deploy final artifact to staging |
| RISK-02 | APM agent version unidentified | 4 | 4 | 16 | Observability | Inventory agent, verify vendor support and instrumentation |
| RISK-03 | Payment mTLS untested on JDK 17 | 5 | 3 | 15 | Security | Test truststore/keystore and partner endpoint |
| RISK-04 | JDK 21 not yet in test matrix | 3 | 3 | 9 | App | Defer to later phase, do not claim support |
| RISK-05 | Container rollback not rehearsed | 4 | 3 | 12 | SRE | Staging rehearsal and data-compat check |

This is a hypothetical table. **Likelihood must not be treated as a statistical measurement** without data; it is a qualitative assessment with an owner and review date.

### 14.3. Distinguish blockers from untested risks

- **Technical blocker**: test already failed or mandatory precondition unmet.
- **Coverage gap**: test not run or environment unavailable.
- **Policy blocker**: vendor/runtime disallowed by policy.
- **Operational risk**: rollback, monitoring, or certificate ownership unready.

These categories need different treatments rather than calling everything a "broken dependency".

## 15. Step 12 — Calculate completion without misleading metrics

Do not report "95% compatible" just because 95% of cells are green if one payment endpoint remains untested.

### 15.1. Coverage and pass rate are two different numbers

Example set of 20 mandatory checks:

```text
PASS:        12
FAIL:         2
BLOCKED:      3
NOT_RUN:      3
```

Execution coverage:

\[
\text{Executed coverage} = \frac{12+2}{20} = 70\%
\]

Pass rate among executed checks:

\[
\text{Pass rate among executed} = \frac{12}{12+2} \approx 85.7\%
\]

Reporting only 85.7% misleads readers into thinking the system is nearly fully tested, while 30% of mandatory checks have not run at all.

### 15.2. Report gate criteria separately

Example rollout policy:

```text
Required:
- All critical functional and security checks PASS.
- No unresolved high-severity FAIL.
- No BLOCKED test on mandatory production path.
- Production image smoke PASS.
- Rollback rehearsal PASS.
- SLO threshold and monitoring defined.
```

A migration may have 90% test coverage yet be **not ready for canary** because mTLS has not been tested. That conclusion is sound if the missing scope is critical.

### 15.3. When many tests do not apply

`NOT_APPLICABLE` may be excluded from the denominator only with justification, e.g., a CLI tool does not use a Servlet container. Do not use `NOT_APPLICABLE` to exclude hard or failing tests.

## 16. Step 13 — Write the current-state report

The report should help decision-makers understand **readiness level, evidence, gaps, and next actions** without reading the entire dependency tree.

Appropriate structure:

1. Executive summary.
2. Scope and migration goals.
3. Current baseline.
4. Component, JDK, and dependency inventory.
5. Compatibility matrix summary.
6. Findings/risk register.
7. Verification evidence and limitations.
8. Prioritized remediation recommendations.
9. Rollout/rollback readiness.
10. Decision requested and owners.

### 16.1. Practice report sample: OrderHub

> **Note:** all content below is an **illustrative** report. Do not treat figures as executed test results.

#### A. General information

```text
Project: OrderHub (fictional)
Assessment date: <date>
Current runtime: JDK 11
Target candidate: JDK 17
Future target: JDK 21 (out of current release scope)
Build: Maven Wrapper
Deployment: container
Owners: Application / Platform / Security / SRE
Assessment version: v0.1
```

#### B. Executive summary

The project has a hypothetical Java 11 baseline and partial JDK 17 testing. Currently, **evidence is insufficient to approve a JDK 17 production canary**, because the final container artifact, payment mTLS, APM agent, and rollback rehearsal remain untested. JDK 21 is outside the verification scope of this phase.

Do not declare "JDK 17 compatible" while critical checks are incomplete. Recommend completing inventory and verification before shifting live traffic.

#### C. Environment status

| Component | Illustrative baseline | Candidate | Assessment |
|---|---|---|---|
| Production JDK | 11 | 17 | Not yet rolled out |
| Compiler release | 11 | 11 | Preserves bytecode/API target |
| Unit tests | Hypothetical PASS | Hypothetical PASS | Insufficient to prove runtime |
| Database integration | Hypothetical PASS | NOT_RUN | Gap |
| TLS/mTLS | Hypothetical PASS | NOT_RUN | Critical gap |
| APM instrumentation | Hypothetical PASS | BLOCKED | Need to identify agent |
| Container startup | Hypothetical PASS | NOT_RUN | Gap |
| Rollback rehearsal | N/A | NOT_RUN | Operational gap |

#### D. Key findings

- **F-01:** No smoke test yet on the final JDK 17 image; startup/config/packaging cannot be confirmed yet.
- **F-02:** APM agent has not been inventoried for version and vendor support.
- **F-03:** mTLS connection to payment gateway lacks evidence with JDK 17 JSSE and the production truststore.
- **F-04:** No image rollback test after a candidate has processed messages.
- **F-05:** JDK 21 lacks test evidence; exclude from support claims.

#### E. Remediation recommendations

| Priority | Action | Owner | Completion criteria |
|---|---|---|---|
| P0 | Identify agent version and test instrumentation | Observability | Logs and trace evidence with candidate |
| P0 | Run payment mTLS on production-equivalent staging | Security + App | Certificate validation passes and negative test fails properly |
| P0 | Build/deploy exact JDK 17 image for smoke/integration | Platform + App | Critical flows and health pass |
| P1 | Rehearse container rollback + handling in-flight events | SRE | Runbook tested |
| P1 | Capture p95/p99, GC, DB pool waiter baselines | SRE | Comparison thresholds established |
| P2 | Build JDK 21 matrix and phased framework upgrade | Tech Lead | Separate roadmap approved |

#### F. Proposed decision

```text
Decision: HOLD production canary
Reason: Mandatory mTLS, APM and image smoke evidence missing
Next gate: Re-evaluate when P0 checks PASS and rollback path is ready
JDK 21 declaration: NOT ASSESSED
```

This is a conclusion **based on an illustrative scenario**, not a conclusion about a real project.

## 17. Rules for objective current-state reporting

### 17.1. Do not write "compatible" without tests

Any claim must answer:

- Who executed it?
- When?
- Which artifact hash?
- Which runtime vendor/update?
- Which command/test suite?
- Which pass criteria?
- Are there scope limitations?

If some information is missing, record the test as **executed but evidence below standard**, instead of deleting or altering original results.

### 17.2. Distinguish interpretation from evidence

Example:

```text
Evidence:
  Test suite TST-003 failed with PKIX path building failed.

Hypothesis:
  Candidate container may use a truststore missing the partner CA.

Not yet proven:
  Whether missing CA is the root cause, versus missing intermediate
  or algorithm constraints.
```

Sound reasoning **does not promote a hypothesis to root cause** before analysis.

### 17.3. Explicitly record what was not tested

A test lacking a payment sandbox environment is marked `BLOCKED`, not "pass because vendor supports TLS 1.2".

Another row without anyone having run it uses `NOT_RUN`. Distinguish these to manage planning.

## 18. Implementing the matrix with Maven CI

For a Maven project, you can build a multi-JDK CI matrix using **the same source commit and dependency configuration**.

Example commands across different CI runners:

```bash
./mvnw -B -version
./mvnw -B clean verify
```

On each runner, store:

- `java -version` and `./mvnw -version`.
- Maven plugin versions.
- Compiler release and test runtime.
- Exit code and discovered tests.
- Surefire/Failsafe reports if present.
- Artifact digest.

Do not assume `verify` automatically runs integration tests unless the project properly configures Failsafe or integration-test goals.

### 18.1. The baseline step should not change too many variables

Example test wave:

```text
CI Job A:
  Runtime JVM: JDK 11
  Source/dependencies: baseline
  Suites: unit + integration

CI Job B:
  Runtime JVM: JDK 17
  Source/dependencies: same commit/config
  Suites: unit + integration
```

If you must change the compiler/plugin to build on JDK 17, explicitly note that as an **additional changed variable**, rather than claiming the test differs only by runtime.

### 18.2. `mvn -version` is not enough

The Maven process may use one JVM while compiler/test forks use another toolchain. If the project configures Maven Toolchains, Compiler Plugin, Surefire/Failsafe `jvm`, or plugin runtimes, record the JDK for each role.

## 19. Implementing the matrix with Gradle CI

Groovy DSL example when targeting Java 11 compilation:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

CI can run:

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean test
```

To test a Java 11 runtime instead of the toolchain default, configure `Test.javaLauncher`:

```groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(11)
    }
}
```

If you want a JDK 11/17/21 test matrix, CI can pass a parameter and set the corresponding launcher per job, or define explicit test tasks. Crucially, **do not let two jobs accidentally run on the same JVM and record results in two different columns**.

### 19.1. Dependency graph by configuration

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

If a failure occurs in a Gradle plugin rather than application code, these configurations do not fully reflect the plugin classpath. Analyze Gradle wrapper/plugin versions separately.

## 20. Measuring performance on the new runtime

Compatibility is not just zero linkage errors. A JDK migration can change GC ergonomics, CPU scheduling, TLS overhead, charset defaults, compiler/JIT behavior, and native interactions.

### 20.1. Baseline metrics

Collect from a controlled environment:

- Request throughput.
- p50/p95/p99 latency.
- HTTP error rate.
- CPU usage/throttling.
- Heap committed/used and allocation rate.
- GC pauses/frequency.
- Thread/pool queue depth.
- Database pool waiters/timeouts.
- Message consumer lag.
- Retry rate and downstream errors.

### 20.2. Compare under matching conditions

Do not compare a JDK 11 test at 5,000 req/s against JDK 17 at 500 req/s and conclude JDK 17 has better latency. Control traffic mix, instance size, DB capacity, payload, load shape, and warmup.

### 20.3. Record gaps properly

If no load test exists yet, `Performance JDK 17: NOT_RUN`. Do not infer production performance readiness from passing unit tests or a single local run.

### 20.4. Designing a performance gate

Example **illustrative thresholds**:

```text
Required:
- No critical functional failures.
- p95 latency increase <= 10% against comparable baseline.
- No sustained increase in error rate.
- No database pool saturation.
- No unexplained GC or memory regression.
```

Numbers must be tuned to real SLOs; do not treat 10% as a mandatory standard of Java migration.

## 21. Binary regression testing with old consumer artifacts

For a library used by many applications, **recompiling all consumer source** does not prove the new library is compatible with already-released consumer JARs.

Model:

```text
Provider v1.jar ----> Compile consumer-old.jar once
                              |
                              v
                        Freeze bytes/hash
                              |
                    +---------+---------+
                    |                   |
                    v                   v
          Run with provider v1   Run with provider v2
             (control)             (candidate)
```

If provider v2 removes a method/constructor or changes a descriptor, the old consumer binary may fail with `NoSuchMethodError`.

### 21.1. Add a binary compatibility row

```text
MAT-020:
  component: shared-order-api
  scenario: Precompiled consumer v1 running with provider v2
  expected: No linkage errors; contract assertions pass
  status: NOT_RUN
  evidence: none
  owner: LibraryTeam
```

This test is needed if the system claims the new provider JAR is a **drop-in replacement**.

## 22. Assessing rollback and data compatibility

A matrix containing only unit tests can miss an important risk: if the new application writes data that the old version cannot read, **runtime rollback is no longer safe**.

### 22.1. Bidirectional checks are required

| Producer | Consumer | What must be proven |
|---|---|---|
| Old | Old | Baseline |
| Old | New | New version reads old data |
| New | New | New version works |
| New | Old | Rollback can still read new data |

For JSON/event/database schemas, if the `New → Old` row fails, you need a compatibility window, adapter, or another roll-forward plan; do not promise a JAR rollback within minutes.

### 22.2. Record a rollback row

```text
MAT-030:
  component: OrderHub deployment
  scenario: JDK17 candidate -> restore JDK11 image
  expected:
    - old image starts
    - existing messages remain processable
    - no data/schema incompatibility
  status: NOT_RUN
  owner: SRE
  risk_id: RISK-05
```

### 22.3. Immutable artifacts

Rollback must rely on verified image digests, release artifacts, and configuration snapshots. A mutable container tag `latest` is not a reliable source for exact recovery.

## 23. Step-by-step practice exercise

Use **a Java project you are authorized to inspect**. If no project is available, use the hypothetical OrderHub scenario to complete the matrix design; when doing so, record all unexecuted results as `NOT_RUN`/`UNKNOWN`.

### Task A — Write the scope

Record:

```text
Project:
Application version:
Current JDK:
Target JDK:
Migration type: runtime-only / compiler / framework / full
Build tool:
Deployment type:
Critical business flows:
Excluded changes:
Owner:
```

**Output:** a scope statement that engineering and operations teams can jointly sign off on.

### Task B — Capture the environment fingerprint

Use the corresponding Maven or Gradle commands and observe the runtime process. Save timestamped evidence.

**Output:** at least one row each for build JVM, compiler JDK, test JVM, and production JVM.

### Task C — Capture dependencies

Save the dependency tree, application server/container versions, agents, native libraries, and framework integrations.

**Output:** inventory with component ID, version, and owner. Unknown items marked `UNKNOWN`.

### Task D — Run the baseline

Execute existing test suites on the current JDK. Do not fabricate passing counts if unable to run.

**Output:** baseline evidence, or state the reason for `BLOCKED`/`NOT_RUN`.

### Task E — Run the candidate

Use the target JDK, holding other variables fixed where possible. Capture logs/exit codes/test reports.

**Output:** the same set of test IDs with candidate results.

### Task F — Check artifacts and security

Inspect packaged JAR/WAR, bytecode major version, `jdeps`, Java agents, TLS truststores, and critical integration points.

**Output:** matrix rows and evidence-backed findings.

### Task G — Build the risk register

For each critical error/gap, record:

```text
Risk ID:
Finding:
Evidence or uncertainty:
Impact:
Likelihood:
Owner:
Mitigation:
Verification plan:
Due date:
```

**Output:** a prioritized list, not just a pile of logs.

### Task H — Write the current-state report

Write the summary, matrix summary, blockers, unknowns, proposed next step, rollback readiness, and decision requested.

**Output:** a report where someone who did not directly run the commands can understand why migration is or is not yet approved.

## 24. Fillable template table

Copy the template below into your own document and fill in with results from a real project.

| Test ID | Item | Baseline JDK | Candidate JDK | Environment | Status | Evidence | Owner |
|---|---|---|---|---|---|---|---|
| TST-001 | Build and compile |  |  | CI | UNKNOWN |  |  |
| TST-002 | Unit tests |  |  | CI | NOT_RUN |  |  |
| TST-003 | DB integration |  |  | staging | NOT_RUN |  |  |
| TST-004 | REST/event contract |  |  | staging | NOT_RUN |  |  |
| TST-005 | Consumer binary |  |  | test | NOT_RUN |  |  |
| TST-006 | TLS/mTLS |  |  | staging | NOT_RUN |  |  |
| TST-007 | Package/container |  |  | staging | NOT_RUN |  |  |
| TST-008 | Java agents |  |  | staging | NOT_RUN |  |  |
| TST-009 | JNI/native |  |  | test | UNKNOWN |  |  |
| TST-010 | Performance |  |  | load test | NOT_RUN |  |  |
| TST-011 | Rollback |  |  | staging | NOT_RUN |  |  |
| TST-012 | Scheduled jobs |  |  | staging | NOT_RUN |  |  |

In the `Status` column, separate **baseline result** and **candidate result** into two distinct columns in a real table if each side can independently PASS/FAIL. This compact table is only a starting point to populate.

## 25. Common mistakes when building a matrix

### 25.1. Listing only JDK versions

Example:

```text
Java 11: OK
Java 17: OK
Java 21: OK
```

No environment, tests, dependency versions, or evidence. Insufficient for a production approval report.

### 25.2. Treating vendor support claims as local test results

Vendor-announced Java 21 support does not mean custom agent configs, truststores, or app business flows pass. Keep two separate columns.

### 25.3. Conflating build JVM and runtime JVM

`mvn -version` reporting JDK 17 does not prove the production Docker image uses JDK 17; `gradlew --version` does not prove the compiler toolchain version.

### 25.4. Recompiling consumers when testing binary compatibility

Without retaining the compiled consumer JAR from the old provider, the test can miss ABI breaks.

### 25.5. Failing to mark `NOT_RUN` or `BLOCKED`

Leaving blank cells easily misleads reviewers into assuming "no problem". Use meaningful statuses and reasons for missing evidence.

### 25.6. Failing to distinguish migration failures from baseline failures

A downstream outage appearing on both old and new JDKs does not prove the new JDK is broken. You need a control run under matching test conditions.

### 25.7. Recording passes from a developer workstation as production-ready

Developer machines have different CA stores, OSes, and proxies than production. For TLS/JPMS/JNI, this is especially dangerous.

### 25.8. Testing only startup

An application may start up yet fail on JPA mapping, message deserialization, mTLS requests, scheduled jobs, or shutdown.

### 25.9. Computing pass rates excluding unexecuted tests

Easily produces an overly optimistic report. Report coverage and pass rate separately, highlighting critical gaps.

### 25.10. Missing artifact identity

If container image tags, dependency snapshots, or plugin versions change, tests cannot be repeated. Record hashes/digests and build IDs.

### 25.11. Assigning no owner

Findings without owners tend to linger indefinitely. Each blocker needs an action, an owner, and a re-check date.

### 25.12. Failing to define rollback

A runtime candidate may run cleanly while new data or event formats become unreadable to the old runtime. Test rollback prior to rollout if reversibility is required.

## 26. How to make decisions based on the matrix

A good report should end with **a concrete decision**, rather than merely describing progress.

### 26.1. `GO` — Proceed to scoped rollout

Consider only if:

- Critical compatibility checks PASS.
- Build/runtime JDKs and artifacts are identified.
- Relevant integration/TLS/agent tests are complete.
- No high-severity unresolved failures remain.
- Monitoring, SLOs, and a verified rollback plan exist.
- An owner approves the next stage.

`GO` may mean only "approved for 5% canary", **not full production rollout**.

### 26.2. `HOLD` — Additional evidence needed

Applies when critical tests are `NOT_RUN`, `BLOCKED`, or the runtime/classloader/truststore in use is unknown.

This matches the hypothetical OrderHub report since mTLS and the agent remain untested.

### 26.3. `NO-GO` — Proven blocker exists

For example, a critical payment transaction fails on the candidate JDK or security policy is violated. Do not expand rollout without a fix and regression evidence.

### 26.4. `RE-SCOPE` — Target must be split smaller

If trying to upgrade JDK 11 → 21 simultaneously with Jakarta, DB schema changes, and virtual threads creates excessive risk, split into phases:

```text
Phase 1: inventory + CI JDK17 test
Phase 2: upgrade incompatible dependencies
Phase 3: runtime JDK17 canary
Phase 4: framework/Jakarta migration
Phase 5: JDK21 and execution-model improvements
```

This is an illustrative roadmap; actual sequencing must follow dependency requirements and support policy.

## 27. Final checklist

### Scope and inventory

- [ ] Identified project, version, environments, current JDK, and target JDK.
- [ ] Separated build JVM, compiler JDK, bytecode target, test JVM, and production runtime.
- [ ] Inventoried frameworks, servers, dependencies, and plugins.
- [ ] Recorded Java agents, bytecode tools, and native libraries.
- [ ] Identified critical integrations: DB, HTTPS/mTLS, messaging, jobs.
- [ ] Assigned owners for each component group.

### Evidence and matrix

- [ ] Clearly defined PASS/FAIL/BLOCKED/NOT_RUN/UNKNOWN.
- [ ] Separated vendor support claims from local verified status.
- [ ] Executed or explicitly recorded unexecuted baseline and candidate runs.
- [ ] Every key PASS/FAIL has an evidence ID and artifact/runtime identity.
- [ ] Checked classfile level, JDK internal APIs, and runtime packaging.
- [ ] Checked certificates/truststores and security policies on the target JVM.
- [ ] Checked reflection, Javax/Jakarta, classloaders, and binary compatibility where relevant.
- [ ] Tested exact artifact deployment, not just source build.
- [ ] Documented non-applicable tests with justification.
- [ ] Checked data/event compatibility and rollback readiness.

### Report and decision

- [ ] Executive summary states readiness level without exaggerating from smoke tests.
- [ ] Includes matrix summary and separate coverage/pass rate.
- [ ] Findings prioritized by impact and uncertainty.
- [ ] Each risk has an owner, action, and closure criteria.
- [ ] Proposes next migration stage.
- [ ] States `GO`, `HOLD`, `NO-GO`, or `RE-SCOPE` with specific scope.
- [ ] Includes a re-verification plan after dependency/JDK/config changes.
- [ ] Report includes date, version, and links to secret-free evidence.

## 28. Conclusion

**A compatibility matrix** is a map of the JDK, build tool, framework, dependency, runtime, integration, and deployment combinations **that have been verified**. **A current-state report** turns that map into an engineering and operational decision: what is ready, what lacks evidence, which risks must be tackled first, and which migration step is small enough to execute safely.

When building a matrix for a Java project, do not stop at "build passes" or "the application starts". Collect facts from **the exact JVM**, inspect the final artifact, tie every outcome to tests/evidence, classify `NOT_RUN` and `BLOCKED` honestly, and check TLS, agents, native integrations, data, and rollback. A report with unfinished items that clearly identifies owners and closure criteria **is more trustworthy** than an all-green table with no traceable evidence.

The goal of this exercise is not producing a pretty spreadsheet; it is building **a verification basis to decide on upgrading the JDK step by step, knowing when to proceed and when to stop**.
