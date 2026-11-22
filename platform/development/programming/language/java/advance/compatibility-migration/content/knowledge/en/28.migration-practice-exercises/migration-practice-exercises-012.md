
# Performing a Phased JDK Upgrade with Testing and a Rollback Plan

Upgrading Java in a running system is not just changing `JAVA_HOME` or placing a new JDK into a Dockerfile. A JDK change can affect the compiler, class-file version, frameworks, dependencies, TLS, charset, garbage collection (GC), JPMS, native libraries, and rolling deployments running multiple versions concurrently. A system may **build successfully yet fail at startup**, or **start up yet cause errors when reading data from a previous version**. Without preparing a rollback, a small bug can prolong recovery time.

This lab belongs to *Java Advance Compatibility Migration*, chapter *Practice Exercises*, building a phased **Java 11 → Java 17 → Java 21** upgrade workflow. We will create a small Java application, capture a baseline, swap toolchains and runtimes step by step, run a testing matrix, design a canary, preserve evidence, and rehearse rollback.

JDKs 11/17/21 are **example milestones**; real projects must choose runtime, library, and application server versions supported by their vendor/organization. Commands in this lesson are intended for an isolated lab or staging environment. This document **does not claim** those commands, tests, or rollouts have already been executed.

## 1. Learning Objectives

Upon completion, learners can:

1. Distinguish the **JDK running the build**, the **compiler's `--release` level**, and the **JDK running the application**.
2. Inventory source code, dependencies, plugins, JVM flags, containers, and external services.
3. Preserve a baseline including Git SHA, artifact checksums, test results, and runtime configuration.
4. Upgrade the JDK in steps with specific acceptance criteria.
5. Run unit, CLI smoke, contract, integration, runtime matrix, and performance tests.
6. Identify bytecode errors, missing APIs/providers, JPMS/reflection issues, and unsupported JVM flags.
7. Test a service while old/new versions operate concurrently.
8. Build and rehearse a rollback covering the application image, configuration, database, and event state.
9. Record a `GO`, `HOLD`, or `ROLLBACK` decision based on evidence, not guesswork.

### 1.1. Lab deliverables

Workspace template:

~~~text
jdk-migration-lab/
├── pom.xml
├── src/
│   ├── main/java/lab/migration/ReceiptCli.java
│   └── test/java/lab/migration/ReceiptCliTest.java
├── fixtures/expected-output.txt
├── deploy/
│   ├── runtime-java11.env.example
│   ├── runtime-java17.env.example
│   └── runtime-java21.env.example
└── evidence/
    ├── s0-baseline/
    ├── s1-build-jdk17/
    ├── s2-runtime17/
    ├── s3-runtime21/
    ├── s4-target21-optional/
    └── rollback/
~~~

This directory tree is an **exercise to create**, not an assertion that the files already exist. Each evidence directory must be linked to the exact artifact and environment, avoiding overwriting results into `latest`.

## 2. Three Dimensions to Separate When Upgrading the JDK

| Dimension | Example | What does it determine? |
|---|---|---|
| Build/compiler JDK | JDK 21 | Which Java version the compiler/tooling runs on |
| Compiler `--release` | 17 | Target API level and class-file version of compiled sources |
| Runtime JDK | JDK 17/21 | JVM that loads and runs the actual artifact |

For example, JDK 21 compiling with `--release 17` produces class-file major version typically **61**, not 65. However, this **does not downgrade bytecode of dependencies** that were already precompiled with Java 21.

An application can run on Java 21 while keeping a Java 17 target to support clients or rolling deployments. There is no mandatory rule saying "if you upgrade the runtime, upgrade the source target immediately".

### 2.1. Phased plan

| Stage | Build JDK | Compiler target | Runtimes tested | Goal |
|---|---|---|---|---|
| S0 | 11 | 11 | 11 | Baseline |
| S1 | 17 | 11 | 11 and 17 | Upgrade build JDK, preserve binary contract |
| S2 | 17 | 17 | 17 | Raise minimum runtime |
| S3 | 21 | 17 | 17 and 21 if 17 still supported | Move runtime to JDK 21, keep bytecode |
| S4 (optional) | 21 | 21 | 21 | Use Java 21 API/language features |

### 2.2. Testing gate workflow

~~~mermaid
flowchart TD
    A["S0 baseline and inventory"] --> B["S1 compiler JDK 17, target 11"]
    B --> C{"Runtime 11/17 and tests pass?"}
    C -->|No| X["HOLD: fix candidate or return to baseline"]
    C -->|Yes| D["S2 minimum runtime 17"]
    D --> E{"Consumers, dependencies supported?"}
    E -->|No| X
    E -->|Yes| F["S3 runtime 21, target 17"]
    F --> G{"Integration, SLO, and rollback pass?"}
    G -->|No| X
    G -->|Yes| H["Canary → promote"]
    H --> I["S4 target 21 only when needed"]
~~~

**Do not skip stages** merely because the final JDK runs a simple feature.

## 3. Safety Principles

- Use a lab workspace, disposable database, and controlled staging; do not edit production directly.
- Keep a last-known-good copy of the binary, runtime image, config, and data/schema compatibility.
- Do not bundle too many unrelated changes into a single stage.
- Do not disable TLS certificate validation or security controls just to "turn tests green".
- Do not use `-XX:+IgnoreUnrecognizedVMOptions` to hide legacy JVM flag errors.
- Do not run risky DDL or roll back real data without backups/approval.
- Do not store credentials, tokens, private keys, or raw customer data in reports.
- Do not mark unexecuted tests as PASS.
- When a mandatory gate fails, the default choice is **HOLD**, not promote.

### 3.1. Statuses to use

~~~text
PENDING:  Not started.
RUNNING:  In progress.
PASS:     Test ran and passed.
FAIL:     Test ran and failed.
SKIPPED:  Test was skipped.
BLOCKED:  Prerequisites to run missing.
HOLD:     Stage not yet eligible to advance.
GO:       Stage approved.
ROLLBACK: Revert to approved state.
~~~

A build job exiting 0 does not prove all integration tests, rollback tests, and performance gates passed.

## 4. Environment Preparation

Requires Git, Maven, JDK 11/17/21, shell/PowerShell, and permissions to store artifacts. If doing the deployment extension, a container runtime plus a test database/queue are required.

### 4.1. Checking toolchain

~~~bash
java -version
javac -version
mvn -version
git --version
~~~

Record actual output: vendor, version/update, and architecture. With Gradle, record separately the JVM running the Gradle daemon and the Java toolchain compiler.

### 4.2. Switching JDK explicitly

Linux/macOS:

~~~bash
export JAVA_HOME=/path/to/approved-jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
java -version
mvn -version
~~~

Windows PowerShell:

~~~powershell
$env:JAVA_HOME = "C:\jdks\jdk-17"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
mvn -version
~~~

Paths are illustrative only. In CI, select JDKs via version-pinned toolchains/container images instead of assuming PATH is right.

## 5. Creating the Sample Maven Project

A simple application helps verify the exact difference between build and runtime. It accepts an amount and timestamp, outputting a wire-format line with a decimal dot and UTC.

Contract:

~~~text
Input:  12.345 2026-11-12T00:00:00Z
Output: amount=12.34;at=2026-11-12T00:00:00Z
~~~

The `HALF_EVEN` rule and two decimal places are only **assumed lab requirements**. In real business domains, monetary policies must be decided by the domain.

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>lab.migration</groupId>
    <artifactId>jdk-migration-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>11</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>lab.migration.ReceiptCli</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The plugin/JUnit versions are a teaching example set; real projects must verify supported versions matching the JDK/vendor. `maven.compiler.release` can be overridden at execution time:

~~~bash
mvn -B -ntp clean verify -Dmaven.compiler.release=17
~~~

Running Maven with JDK 21 using the property above **does not mean** the runtime JDK is already 17 or 21. Check `mvn -version`.

### 5.2. ReceiptCli.java

~~~java
package lab.migration;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;

public final class ReceiptCli {
    private ReceiptCli() {
    }

    public static String render(BigDecimal amount, Instant at) {
        String money = amount.setScale(
                2, RoundingMode.HALF_EVEN).toPlainString();

        return "amount=" + money + ";at=" + at;
    }

    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println(
                    "Usage: <amount> <UTC-ISO-8601-instant>");
            System.exit(2);
        }

        try {
            BigDecimal amount = new BigDecimal(args[0]);
            Instant at = Instant.parse(args[1]);
            System.out.println(render(amount, at));
        } catch (RuntimeException invalidInput) {
            System.err.println("Invalid input: " +
                    invalidInput.getClass().getSimpleName());
            System.exit(2);
        }
    }
}
~~~

Place the file at `src/main/java/lab/migration/ReceiptCli.java`.

Notable points:

- `BigDecimal(String)` avoids binary floating-point precision errors.
- `toPlainString()` and `HALF_EVEN` preserve formatting per contract.
- `Instant` represents a UTC point in time.
- Does not use the system locale to format numbers.
- Exit codes help schedulers/scripts identify invalid inputs.

### 5.3. ReceiptCliTest.java

~~~java
package lab.migration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import org.junit.jupiter.api.Test;

class ReceiptCliTest {
    private static final Instant AT =
            Instant.parse("2026-11-12T00:00:00Z");

    @Test
    void keepsHalfEvenDecimalContract() {
        assertEquals(
                "amount=12.34;at=2026-11-12T00:00:00Z",
                ReceiptCli.render(new BigDecimal("12.345"), AT));
        assertEquals(
                "amount=12.36;at=2026-11-12T00:00:00Z",
                ReceiptCli.render(new BigDecimal("12.355"), AT));
    }

    @Test
    void formatsZero() {
        assertEquals(
                "amount=0.00;at=2026-11-12T00:00:00Z",
                ReceiptCli.render(BigDecimal.ZERO, AT));
    }

    @Test
    void rejectsMalformedTimestamp() {
        assertThrows(DateTimeParseException.class,
                () -> Instant.parse("not-a-timestamp"));
    }
}
~~~

Place the file at `src/test/java/lab/migration/ReceiptCliTest.java`.

### 5.4. Fixture

`fixtures/expected-output.txt`:

~~~text
amount=12.34;at=2026-11-12T00:00:00Z
~~~

Pay attention to newlines and charset when comparing exact bytes. If the output contract is a logical line, an explicit newline normalization rule can be defined across OSes.

## 6. Stage S0 — Capturing the Java 11 Baseline

With JDK 11:

~~~bash
java -version
mvn -version
git rev-parse HEAD
git status --porcelain

mvn -B -ntp clean verify -Dmaven.compiler.release=11

java -jar target/jdk-migration-lab-1.0.0.jar \
  12.345 2026-11-12T00:00:00Z
~~~

Expected stdout:

~~~text
amount=12.34;at=2026-11-12T00:00:00Z
~~~

### 6.1. Inspecting bytecode

~~~bash
jar tf target/jdk-migration-lab-1.0.0.jar

javap -verbose \
  -classpath target/jdk-migration-lab-1.0.0.jar \
  lab.migration.ReceiptCli
~~~

Java 11 classfiles have major version **55**.

### 6.2. Computing checksum

Linux/macOS:

~~~bash
sha256sum target/jdk-migration-lab-1.0.0.jar
~~~

Windows PowerShell, written on one line to avoid shell escaping confusion:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "target\jdk-migration-lab-1.0.0.jar"
~~~

Record the result alongside build ID/source commit. A rebuilt JAR can have a different hash even when version/name remain identical.

### 6.3. Gate S0

- [ ] JVM and Maven are using JDK 11.
- [ ] Unit tests ran with clear pass/fail/skip counts.
- [ ] CLI output matches the fixture.
- [ ] Invalid input produces a non-zero exit code.
- [ ] JAR has main class and major 55.
- [ ] Git commit, dependencies, and JDK update recorded.
- [ ] Artifact checksum and config saved.
- [ ] Last-known-good exists to revert to.

If the baseline still has bugs or unclassified flaky tests, **HOLD** before upgrading.

## 7. Stage S1 — Upgrading Build JDK to 17, Keeping Java 11 Target

With the selected JDK 17:

~~~bash
java -version
mvn -version
mvn -B -ntp clean verify -Dmaven.compiler.release=11
~~~

### 7.1. Important requirements

Check `javap -verbose`: major remains **55**. Compiler is new, yet bytecode still targets runtime 11.

Run the **exact same JAR** on both runtimes:

~~~bash
/path/to/jdk-11/bin/java \
  -jar target/jdk-migration-lab-1.0.0.jar \
  12.345 2026-11-12T00:00:00Z

/path/to/jdk-17/bin/java \
  -jar target/jdk-migration-lab-1.0.0.jar \
  12.345 2026-11-12T00:00:00Z
~~~

Do not re-run Maven to build a new JAR between the two smoke tests.

### 7.2. Errors that may appear

- Maven plugin/annotation processor does not yet support the new JDK compiler.
- Build script uses internal JDK APIs.
- Tests depend on default locale/charset.
- Reflection into JDK private packages.
- Dynamic dependency versions resolve differently.
- Maven/test runner JVM flags are no longer valid.

### 7.3. Acceptance criteria

| Check | Condition |
|---|---|
| Build JDK | Maven actually runs on JDK 17 |
| Compiler target | Java 11/major 55 |
| Java 11 smoke | Output and exit code pass |
| Java 17 smoke | Output and exit code pass |
| Tests | Mandatory tests PASS |
| Artifact | Hash and reports bound to the same JAR |
| Recovery | Can reuse S0 |

## 8. Stage S2 — Moving Minimum Runtime to Java 17

Once confident no mandatory consumer/runtime remains on Java 11, the target can be raised.

~~~bash
mvn -B -ntp clean verify -Dmaven.compiler.release=17
~~~

Java 17 class-file major version is **61**.

### 8.1. Intentional failure

Running a target-17 JAR on Java 11 may report:

~~~text
java.lang.UnsupportedClassVersionError:
class file version 61.0 is not supported by this runtime
~~~

The exact message depends on the JVM. This is a valid boundary: **Java 11 cannot load Java 17 bytecode**. Do not fix by adding JVM flags. To roll back to a Java 11 runtime, you need the saved **target-11 artifact**.

### 8.2. Mandatory runtime inventory

- HTTP services and workers.
- Scheduled jobs.
- Plugins/application servers.
- Batch utilities.
- Customer-hosted installations.
- CI test launchers.
- Custom `jlink` images.
- Monitoring agents/native libraries.

If any place must still run Java 11, do not release a target-17 artifact to that environment.

### 8.3. Gate S2

- [ ] Minimum runtime 17 announced and deployed.
- [ ] Artifact target 17/major 61.
- [ ] Integration tests on JDK 17 pass.
- [ ] Dependencies/agents/providers support JDK 17.
- [ ] No mandatory consumer still runs Java 11.
- [ ] Last-known-good JDK 11 artifact/config exists.
- [ ] Data/schema rollback evaluated.

## 9. Stage S3 — Upgrading Runtime/Build to JDK 21, Keeping Target 17

To separate runtime migration from bytecode changes:

~~~bash
mvn -B -ntp clean verify -Dmaven.compiler.release=17
~~~

Maven runs JDK 21, yet classfile major remains **61**.

### 9.1. Running on both JVMs

~~~bash
/path/to/jdk-17/bin/java \
  -jar target/jdk-migration-lab-1.0.0.jar \
  12.345 2026-11-12T00:00:00Z

/path/to/jdk-21/bin/java \
  -jar target/jdk-migration-lab-1.0.0.jar \
  12.345 2026-11-12T00:00:00Z
~~~

Record binary hashes and actual runtimes for each test. `--release 17` **does not guarantee** third-party JARs, native libraries, or Java agents are also Java 17 compatible.

### 9.2. Risk layers to verify

- Class loading/module access/reflection.
- Security providers/TLS/truststore.
- Charset/locale/TZDB.
- JDBC/ORM/transactions.
- JSON/XML/event serialization.
- JNI/native components.
- Java agents/instrumentation.
- GC/heap/CPU ergonomics.
- Startup/readiness/shutdown.
- API contracts and shared data formats.

### 9.3. Gate S3

| Category | Evidence |
|---|---|
| Build JDK | JDK 21 compiler/toolchain report |
| Target | Major 61 |
| Runtime | Smoke 17 and 21 |
| Integration | DB/broker/framework/provider tests |
| Security | TLS/auth/driver/provider tests |
| Business | Contract and data invariants |
| Performance | SLO and resource budget |
| Rollback | Last-known-good, rehearsal |
| Traceability | Artifact hash, manifest, test IDs |

## 10. Stage S4 — Target Java 21 When Genuinely Needed

~~~bash
mvn -B -ntp clean verify -Dmaven.compiler.release=21
~~~

Java 21 has class-file major **65**. A target-21 JAR does not run on Java 17.

Execute S4 only if Java 21 runtime is the supported minimum and brings clear benefits (new API/source features, new dependency requirements, or support policy changes). If Java 17 still must be supported, target 17 can be kept even after production runtime moves to Java 21.

## 11. Binary and Runtime Matrix

| Artifact | Target | Java 11 | Java 17 | Java 21 |
|---|---|---|---|---|
| S0 | 11 | Test | Test if supported | Test if supported |
| S1 | 11 | Test | Test | Test if supported |
| S2 | 17 | Unsupported | Test | Test if supported |
| S3 | 17 | Unsupported | Test if supported | Test |
| S4 | 21 | Unsupported | Unsupported | Test |

"Test" does not mean default PASS. Actual results must exist for the combinations the product declares supported.

### 11.1. Do not infer from classfile version alone

A target-17 JAR may pull in a target-21 dependency. Conversely, a low target classfile does not guarantee non-Java-SE APIs or native providers are compatible. Inspect **both the dependency graph and runtime behavior**.

## 12. Inventorying Dependencies, JDK Internals, and JPMS

~~~bash
mvn dependency:tree

jdeps --jdk-internals --recursive \
  --class-path "lib/*" app.jar

jdeps --print-module-deps \
  --class-path "lib/*" app.jar
~~~

`jdeps` analyzes static references and misses reflection strings, dynamic plugins, or JNI. In application servers, server-provided dependencies may also sit outside the Maven dependency tree.

### 12.1. Categories to inspect

| Category | Risk |
|---|---|
| JDK internals | `sun.*` and internal APIs restricted/removed |
| JPMS | `--add-opens`, `--add-exports`, reflection |
| Annotation processors | Compiler/plugin JDK compatibility |
| Bytecode tooling | ASM/agents failing to understand newer classfiles |
| Java EE/Jakarta | `javax.*`/`jakarta.*` and server generations |
| Logging | Different API/provider binding |
| JDBC/ORM | Driver, transaction, provider versions |
| TLS/security | Certificate/algorithm/provider behavior |
| Native | JNI/JNA, ABI/architecture |
| Plugin host | Host-provided APIs and classloader identity |

### 12.2. Do not use module flags to fix wrong-layer errors

`InaccessibleObjectException` relates to JPMS/deep reflection; `NoClassDefFoundError` is usually a missing class or initialization error; `NoSuchMethodError` is usually a binary mismatch. Investigate the exact root cause.

## 13. JVM Flags That Can Cause Startup Failures

Legacy configuration may contain:

~~~text
-XX:+UseConcMarkSweepGC
-XX:+PrintGCDetails
-Xloggc:logs/gc.log
--illegal-access=permit
~~~

CMS was removed from HotSpot starting in JDK 14; many flags/logging options change across releases. Some settings stop the JVM **before `main()` runs**.

Sources to inventory: Docker entrypoints, Helm/Kubernetes values, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, service scripts, Maven/Gradle test runners, and monitoring agents.

### 13.1. Verifying effective JVM settings

HotSpot/JDK supports:

~~~bash
java -XX:+PrintCommandLineFlags -version
java -XX:+PrintFlagsFinal -version
java --list-modules
~~~

For a running process:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.version
~~~

Command lines may contain secrets; redact before saving reports. Do not use IgnoreUnrecognizedVMOptions to "ignore and make it run"; remove invalid flags and confirm the actual collector.

## 14. Testing Layers of a Migration

| Test | What to prove |
|---|---|
| Build/static | Source/bytecode/dependencies are valid |
| Unit | Business behavior preserved |
| CLI/smoke | Artifact can start and return output |
| Runtime matrix | Supported JDK versions all run |
| Contract | Old clients/producers/consumers understand the new protocol |
| Integration | Database, queue, framework, native providers |
| Security | TLS, auth, truststore, algorithm policy |
| Performance | p99, throughput, GC, CPU/RSS |
| Deployment | Canary, rolling, graceful shutdown |
| State rollback | Shared DB/event/session readable after rollback |

Do not use a single passing unit test to substitute for all other layers.

### 14.1. CLI smoke and error path

~~~bash
java -jar target/jdk-migration-lab-1.0.0.jar \
  12.345 2026-11-12T00:00:00Z
~~~

Expect a single output line matching the fixture. Invalid case:

~~~bash
java -jar target/jdk-migration-lab-1.0.0.jar \
  bad-number 2026-11-12T00:00:00Z
~~~

Verify a non-zero exit code and no partial side effects. Actual exception messages can vary between JDKs, so if the contract only requires an error category, do not hardcode the entire exception text.

### 14.2. Boundary data testing

- Decimals `12.345` and `12.355` with HALF_EVEN.
- Zero, negative numbers, and very large numbers.
- Decimal comma if the protocol only accepts a dot.
- Invalid timestamps, timezone offsets, and DST when local calendars exist.
- Unicode/Vietnamese and raw UTF-8 bytes.
- JSON null/missing/unknown fields when the application uses JSON.
- Duplicate requests/events and idempotency.
- Old and new sessions/caches during mixed-version deployments.

## 15. Testing Charset, Decimals, and Time

Changes may not fail compilation yet **alter data meaning**.

### 15.1. Charset

~~~java
byte[] bytes = "Tiếng Việt".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);
String text = new String(
        bytes, java.nio.charset.StandardCharsets.UTF_8);
~~~

Use explicit charsets for file/wire contracts. JDK 18 changed the default charset per JEP 400, so legacy data must be decoded according to the actual encoding used, not automatically assumed to be UTF-8.

### 15.2. Decimal

~~~java
BigDecimal amount = new BigDecimal("12.345");
String wire = amount.setScale(
        2, RoundingMode.HALF_EVEN).toPlainString();
~~~

Do not use `new BigDecimal(12.345)` to model decimal money amounts because the double input is already binary floating-point.

### 15.3. Date/time

~~~java
Instant timestamp =
        Instant.parse("2026-11-12T00:00:00Z");
~~~

Do not use the JVM default timezone as part of the protocol. For local calendars, preserve zone/offset and test DST where applicable.

## 16. Integration with Frameworks and Databases

CLI only proves basic compile/runtime mechanics. For a real service, run:

- JDBC/transaction tests.
- ORM entity scanning and mapping.
- Servlet/REST request/filter tests.
- JSON/XML/event serialization.
- ServiceLoader/provider discovery.
- TLS handshakes and authentication.
- Agent/bytecode instrumentation.
- JNI/native integration.
- Startup/readiness, threads/shutdown.
- Custom runtime image modules if using `jlink`.

### 16.1. Testing on production-equivalent environments

If production runs in containers with resource limits and a minimal JDK image, integration tests run only on a developer laptop/full JDK may miss missing modules/providers, CPU throttling, or native library mismatches.

### 16.2. Do not use uncontrolled production data

Test migrations on a disposable DB or anonymized data; backups/snapshots must follow policy. Do not run destructive schema operations on real databases in this lab.

## 17. Mixed-Version Deployments

A rolling deployment can simultaneously have:

~~~text
T0: [V1/Java17, V1/Java17, V1/Java17]
T1: [V1/Java17, V1/Java17, V2/Java21]
T2: [V1/Java17, V2/Java21, V2/Java21]
T3: [V2/Java21, V2/Java21, V2/Java21]
~~~

Both directions must be tested:

- V1 client calling V2 server.
- V2 client calling V1 server if topology allows.
- V1 producer → V2 consumer.
- V2 producer → V1 consumer.
- V1/V2 reading/writing the same database/cache.
- Retries from V1 to V2 not creating duplicate orders.
- Sessions/tokens written by V2 remaining readable when rolling back to V1.
- Graceful shutdown/drain during rolling updates.

### 17.1. HTTP contracts differ from bytecode compatibility

Two independent JVMs can communicate via JSON/gRPC even across different Java major versions. What must be preserved are **wire protocol, schema, and semantic behavior**. However, if Java native serialization is used, binary class names and `serialVersionUID` become another concern to test.

### 17.2. Low-traffic canaries still have broad impact

A canary with only 5% HTTP traffic can emit a new event schema to all consumers. Therefore, "enable readers understanding the new format first, enable writers emitting the new format later" is usually a safer strategy.

## 18. Database Expand–Migrate–Contract

If V1 uses `customer_name` while V2 wants `first_name`/`last_name`, do not drop the old column while V1 is still running.

~~~sql
ALTER TABLE orders ADD COLUMN first_name VARCHAR(100);
ALTER TABLE orders ADD COLUMN last_name VARCHAR(100);
~~~

Procedure:

~~~mermaid
flowchart TD
    A["Schema S1 + app V1"] --> B["Expand S2: add schema"]
    B --> C["Test V1 still reads/writes"]
    C --> D["V1/V2 run simultaneously"]
    D --> E["Backfill + controlled dual-read/write"]
    E --> F["All old consumers drained"]
    F --> G["Contract S3: remove old structure"]
~~~

### 18.1. Mandatory tests

- V1 inserts/updates on the expanded schema.
- V2 reads data written by V1.
- V1 reads data written by V2 during the rollback window.
- Constraints/defaults do not break V1.
- Backfill does not cause data loss or overly long locks.
- If dual-write, handles partial failures and consistency.
- Once the contract schema has run, is V1 rollback still valid?

**Rolling back a container image does not automatically restore the database schema.**

## 19. Performance Baseline and GC

A new JDK can change GC ergonomics, JIT, and container awareness.

| Metric | Baseline | Candidate | Gate |
|---|---|---|---|
| Throughput | Measured | Measured | Per business SLO |
| p95/p99 latency | Measured | Measured | Per latency SLO |
| Error/timeout rate | Measured | Measured | Per error budget |
| GC pause p99/max | Measured | Measured | Per pause budget |
| CPU/throttling | Measured | Measured | Has headroom |
| RSS/native memory | Measured | Measured | Under memory limit |
| Startup/readiness | Measured | Measured | Within rollout budget |

Do not compare Java 11 metrics on a 16-core machine against Java 21 in a 1-vCPU pod quota and blame the collector.

### 19.1. Benchmark conditions

- Same workload/dataset/concurrency when possible.
- Sufficient warm-up.
- Clear JDK vendor/update.
- Clear GC flags and heap limits.
- Equivalent resource limits/architecture.
- Stable database/network dependencies.
- Multiple attempts and raw measurements.
- Monitor p99/errors alongside CPU/RSS, not just GC count.

Example HotSpot GC log:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -jar app.jar
~~~

Do not enable heavy profiling in production without approval.

## 20. Evidence for Each Stage

~~~text
evidence/
└── s3-runtime21/
    └── ci-8124/
        ├── manifest.yaml
        ├── app.jar
        ├── app.jar.sha256
        ├── toolchain.txt
        ├── dependency-tree.txt
        ├── jvm-flags.redacted.txt
        ├── unit-report.xml
        ├── smoke-jdk17.txt
        ├── smoke-jdk21.txt
        ├── integration-report.xml
        ├── performance.json
        ├── rollback-rehearsal.txt
        └── decision.yaml
~~~

### 20.1. Sample manifest

~~~yaml
migration:
  stage: "S3"
  objective: "Upgrade runtime to JDK 21, keep target 17"
  predecessor: "S2"

source:
  commit: "EXACT_GIT_COMMIT"

build:
  id: "ci-8124"
  compiler_jdk: "EXACT_JDK21_VENDOR_AND_UPDATE"
  maven_version: "EXACT_MAVEN_VERSION"
  release_target: 17

artifact:
  path: "app.jar"
  sha256: "EXACT_SHA256"

tests:
  unit: "unit-report.xml"
  runtime17: "smoke-jdk17.txt"
  runtime21: "smoke-jdk21.txt"
  integration: "integration-report.xml"
  performance: "performance.json"

decision:
  status: "PENDING"
  rollback_artifact: "LAST_KNOWN_GOOD_SHA"
  owner: "RELEASE_OWNER"
~~~

`EXACT_*` values are placeholders. Do not use the sample manifest as real test evidence.

### 20.2. Build once, promote the same artifact

Avoid:

~~~text
Build A → Test A → Rebuild B → Deploy B
~~~

Prefer:

~~~text
Build A → SHA A → Test A → Staging A → Canary A → Production A
~~~

If signing or repackaging creates a new binary, save separate checksums/provenance.

### 20.3. Failed tests still require evidence

A valid status can be:

~~~text
TEST_STATUS=FAIL
EVIDENCE_UPLOAD=SUCCESS
RELEASE_GATE=BLOCKED
~~~

Do not delete failure logs or keep only the passing retry attempt. Redact secrets/PII and manage retention.

## 21. Designing Release Gates

| Gate | Criteria | If not met |
|---|---|---|
| Source/build | Commit, toolchain, dependencies clear | HOLD |
| Artifact | Binary hash/digest matches tested version | HOLD |
| Unit/contract | Required tests actually PASS | HOLD |
| Runtime matrix | Supported JDKs run | HOLD |
| Integration | DB/broker/provider/security pass | HOLD |
| Shared data | State/schema rollback-compatible | HOLD |
| Performance | SLO/resource budget met | HOLD |
| Canary | Metrics stable per version | HOLD/ROLLBACK |
| Recovery | Last-known-good can be restored | Do not promote |

### 21.1. SKIPPED differs from PASS

If an HSM test is skipped because hardware is unavailable, record `SKIPPED`/`BLOCKED` and the reason. Do not add this test to PASS counts. If there is a waiver, it needs an owner, risk, mitigation, approver, and expiration date.

## 22. Controlled Canary Rollout

After staging, a service can:

1. Deploy candidate V2/JDK21 to a subset of instances.
2. Keep V1/JDK17 as last-known-good.
3. Route a small percentage of requests to V2 per policy.
4. Monitor error rate, p99, CPU/RSS/GC per version.
5. Check whether database/event/queue consumers encounter errors.
6. Increase traffic in stages if gates hold.
7. Stop/roll back immediately upon hitting an approved trigger.
8. Record deployment ID, digest, config, and decision.

Health/readiness returning 200 only proves the health endpoint meets probe conditions, **not substituting** for end-to-end contracts, shared-state tests, and business invariants.

## 23. Rollback Must Be Designed in Advance

A rollback plan includes:

- Trigger: business, SLO, security, or data failure.
- Last-known-good artifact/image digest.
- Corresponding runtime JDK and JVM flags.
- Config/feature flags of the old version.
- DB/event/session state compatibility.
- How to shift traffic and stop dangerous writers.
- Decision maker and executor.
- Smoke/contract/data verification after rollback.
- Evidence and incident follow-up.

### 23.1. Rollback layers

**Binary:** revert to the old JAR/container image.

**Runtime:** revert to the old JDK/runtime image when the artifact is compatible.

**Configuration:** restore JVM flags, endpoints, and feature flags.

**State:** roll back database/queue/cache only when a tested plan exists; many changes cannot be safely reversed.

If an artifact already targets Java 21, running it on Java 17 will not work. If V2 already wrote a new schema that V1 cannot read, swapping only the binary is insufficient.

## 24. Illustrative Rollback Runbook

~~~text
DETECT
  1. Alert or invariant fails.
  2. Confirm artifact version, JDK, and scope.

FREEZE
  3. Stop increasing canary traffic.
  4. Prevent additional incompatible writes if needed.
  5. Record image digest, JVM flags, DB revision, and logs.

ROLLBACK
  6. Shift traffic back to last-known-good.
  7. Restore approved binary/runtime/config.
  8. Do not automatically down-migrate untested DB schemas.
  9. Preserve the candidate artifact and incident evidence.

VERIFY
  10. Run smoke/contract tests.
  11. Verify DB, events, and cache/session invariants.
  12. Confirm error/latency/resource metrics recover.
  13. Record the decision and post-incident lessons.
~~~

### 24.1. Kubernetes staging example

~~~bash
kubectl rollout status deployment/receipt-service \
  -n staging --timeout=180s

kubectl rollout history deployment/receipt-service \
  -n staging

kubectl rollout undo deployment/receipt-service \
  -n staging
~~~

**Execute only in an authorized environment.** `rollout undo` does not automatically roll back DB schemas, ConfigMaps, Secrets, or external side effects.

### 24.2. When rollback is unsafe

If V2 already created records/events that V1 does not understand:

- Mark status `ROLLBACK_UNSAFE`.
- Consider a roll-forward fix.
- Use an adapter or maintain old-reader compatibility.
- Feature-gate creation of new data.
- Use backup/restore with data-loss assessment if mandatory.
- Do not declare rollback successful merely because the V1 container starts.

## 25. Incident Rehearsal Exercises

### Exercise A — Removed JVM flag

The new candidate JDK fails to start with a legacy GC flag.

1. Save redacted startup stderr.
2. Trace the flag from scripts/containers/env.
3. Do not ignore the unknown option.
4. Restore last-known-good runtime/config.
5. Remove/update the flag in the candidate.
6. Re-run the startup test.
7. Save both failed and corrected run IDs.

**Passed when:** the exact root cause is identified, rollback stays intact, and the new candidate is verified.

### Exercise B — Bytecode higher than JVM

A Java 21-targeted JAR is mistakenly run on Java 17.

1. Read `UnsupportedClassVersionError`.
2. Use `javap` to check major 65.
3. Record runtime JDK/artifact hash.
4. Choose a lower build target or upgrade the runtime fleet.
5. Re-run the matrix.

**Passed when:** recognizing this is a target error, not missing `--add-opens`.

### Exercise C — Locale-skewed decimal wire format

Contract:

~~~text
amount=12.34;at=2026-11-12T00:00:00Z
~~~

Candidate outputs:

~~~text
amount=12,34;at=2026-11-12T00:00:00Z
~~~

Old consumer uses a dot.

1. Write a regression fixture.
2. Identify the default locale/formatter.
3. Use the decimal representation per the wire contract.
4. Run tests across multiple locales and JDKs.
5. Save the report; do not promote while the contract fails.

### Exercise D — State breaks rollback

Suppose V2 emits enum `REFUNDED` whereas V1 only knows `CREATED/PAID/CANCELLED`.

1. Test V2 producer → V1 consumer.
2. Identify the parse/semantic failure.
3. Mark rollback unsafe if V1 cannot read the state.
4. Propose reader-first/write-later.
5. Design an adapter or roll-forward.
6. Record the exact point when the compatibility layer can be removed.

## 26. Decision Record

~~~yaml
decision:
  stage: "S3"
  artifact_digest: "sha256:EXACT_HASH"
  status: "HOLD"
  reason: "Required integration test failed"
  report: "integration-report.xml"
  rollback_target: "LAST_KNOWN_GOOD_DIGEST"
  owner: "Assigned release owner"
  decided_at: "ISO_8601_TIMESTAMP"
~~~

This is an example, not a real approval/test result.

## 27. CI Pipeline with Evidence Gate

~~~mermaid
flowchart TD
    A["Pinned source commit + stage ID"] --> B["Toolchain + dependency resolution"]
    B --> C["Unit/build"]
    C --> D["Artifact + checksum"]
    D --> E["Cross-JDK, contract, integration, performance"]
    E --> F["Archive reports even on FAIL"]
    F --> G{"Mandatory gates pass?"}
    G -->|No| H["HOLD"]
    G -->|Yes| I["Staging/canary same digest"]
    I --> J{"SLO and recovery pass?"}
    J -->|Yes| K["Promote by digest"]
    J -->|No| L["Rollback + incident evidence"]
~~~

A real pipeline must pin toolchains, dependency versions, artifact checksums, DB/broker images, and runtime configurations. Build caches are not immutable release repositories.

## 28. Error Diagnosis Table

| Symptom | Possible cause | Investigation |
|---|---|---|
| Maven fails with new JDK | Plugin/compiler mismatch | Maven/JDK versions |
| `UnsupportedClassVersionError` | Bytecode too new | `javap`, runtime Java |
| `NoClassDefFoundError` | Missing class/module/provider | Dependencies, runtime image |
| `NoSuchMethodError` | Binary library mismatch | Method descriptors, graph |
| `InaccessibleObjectException` | Deep reflection blocked | JPMS, frameworks |
| `ServiceConfigurationError` | SPI/provider resolution | Services/module graph |
| Unrecognized VM option | Obsolete/removed flag | Startup arguments |
| TLS handshake fails | Truststore/security mismatch | Certificates, algorithms |
| CSV decimal/time differs | Locale/timezone/charset | Wire fixtures |
| p99 increases | GC/CPU/DB/network | Metrics, traces, resource limits |
| Binary rolls back yet DB errors | Incompatible schema/state | Expand/contract, backup |
| Canary HTTP green, queue errors | Event schema mismatch | Consumer errors, DLQ |
| Tests fail only in CI | Different env/JDK/locale | Toolchain snapshot |

## 29. Stage-by-Stage Checklists

### S0

- [ ] JDK 11/vendor/update recorded.
- [ ] Build, unit, smoke PASS.
- [ ] Classfile major 55.
- [ ] Artifact checksum and Git SHA saved.
- [ ] Last-known-good config remains retrievable.

### S1

- [ ] Build JDK 17, target 11.
- [ ] Major remains 55.
- [ ] Same artifact runs on Java 11/17.
- [ ] Test results and dependency graph saved.
- [ ] Path back to S0 exists.

### S2

- [ ] Minimum runtime moved to Java 17.
- [ ] Target 17/major 61.
- [ ] Consumers, plugins, and agents all have compatibility plans.
- [ ] Integration tests pass.
- [ ] Binary/config/data rollback evaluated.

### S3

- [ ] Build/runtime JDK21, target 17/major 61.
- [ ] Runtime matrix 17/21 passes per support policy.
- [ ] TLS, serialization, locale, timezone tests pass.
- [ ] JVM flags and GC confirmed.
- [ ] Performance/resource budgets met.
- [ ] Canary and rollback rehearsal have evidence.

### S4 if applicable

- [ ] Minimum Java21 announced.
- [ ] Target 21/major 65.
- [ ] No dependency requires runtime 17 for the new artifact.
- [ ] Tested artifact on actual runtime 21.
- [ ] Last-known-good exists for the new stage.

## 30. Pre-Production Promotion Checklist

### Artifact and testing

- [ ] Clean source commit, pinned build toolchain.
- [ ] Resolved dependencies and artifact digest clear.
- [ ] Staging/canary uses the exact artifact to be promoted.
- [ ] Required tests PASS; skips/waivers have decisions.
- [ ] Contract/mixed-version/state tests applied when needed.
- [ ] Test runner environment and JDK runtime recorded.

### Performance and safety

- [ ] Throughput/p99/error rate meet SLO.
- [ ] CPU/RSS/GC/oom limits retain headroom.
- [ ] TLS/security/provider checks pass.
- [ ] Observability distinguishes Java and app versions.
- [ ] Graceful shutdown/draining tested.

### Rollback

- [ ] Last-known-good image/artifact and config remain ready.
- [ ] DB/event/session state is rollback-safe or has a dedicated plan.
- [ ] Rollback triggers, owner, and runbook approved.
- [ ] Rehearsed rollback in an appropriate environment.
- [ ] Verification tests exist for the system after rollback.
- [ ] Location exists to store logs, checksums, decisions, and incident evidence.

## 31. Self-Assessment Questions

1. Why does a JDK 21 compiler with `--release 17` not produce Java 21 bytecode?
2. Does a major-61 JAR run on Java 11?
3. If JUnit PASSES yet an old client's API contract FAILS, can we GO?
4. Why must we save the SHA-256 of the tested artifact?
5. If V2 writes new data, is rolling back to V1 always safe?
6. How can a small canary cause old event consumers to fail?
7. Why is measuring GC count alone insufficient to evaluate performance?
8. How do you detect unsupported JVM flags before production?
9. When should target Java 17 be kept even when production uses JDK 21?
10. What evidence proves a rollback properly restored the system?

When answering, cite corresponding test cases, artifact hashes, runtimes, and decision records, rather than merely repeating concepts.

## 32. Extension Exercises

### 32.1. Framework migration

Add a framework/database dependency with a clear support matrix, record the baseline, and attempt upgrading by group. Check public APIs, reflection, providers, and binary compatibility.

### 32.2. Custom runtime image

Create a runtime image with `jlink`/`jdeps` if applicable, then test dynamic services. An image missing a service provider can start up yet fail on rare features.

### 32.3. Multi-service topology

Set up V1/V2 on two test endpoints with a disposable database and message broker. Test retries, cache/session, event compatibility, and rollback after V2 writes.

### 32.4. Security change

Simulate a TLS policy/certificate mismatch on staging, inspect error logs and policy-compliant trust update procedures. Do not disable certificate validation to get tests to pass.

## Conclusion

**A phased JDK upgrade** separates compiler errors, bytecode targets, runtimes, dependencies/frameworks, and data. The path **Java 11 baseline → JDK 17 build with target 11 → minimum runtime 17 → JDK 21 runtime with target 17 → target 21 when needed** preserves compatibility windows and collects reproducible evidence.

To release safely, a green JAR build alone is not enough. You need **artifact checksums, a runtime testing matrix, contract/integration tests, performance SLOs, canary observation, and rehearsed rollback**. When a mandatory gate fails, choose **HOLD** and investigate. If a rollout hits a rollback trigger, prioritize restoring last-known-good **without corrupting database, event, and session state**. That is a JDK transition that is measurable, traceable, and recoverable.
