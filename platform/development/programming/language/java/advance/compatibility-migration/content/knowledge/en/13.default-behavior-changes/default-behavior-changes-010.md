# Distinguishing Legacy Application Bugs from Intentional Platform Changes

When migrating an application from an older JDK to a new JDK, "same source code yet different results" does not automatically prove the new JDK has a bug. Different results can come from a change announced by the Java Platform; a bug fix causing previously erroneous behavior to no longer occur; a dependency outside the JDK; or the legacy application itself relying on unguaranteed behavior.

This is a common challenge in **Java Advance Compatibility Migration**, especially in the **default behavior** category: charset, locale, TLS, GC, reflective access permissions, collection iteration order, and module packaging can change between releases. If every discrepancy is concluded to be a "JDK regression," the team easily wastes time debugging in the wrong place or trying to preserve old behavior that is no longer safe. Conversely, if every issue is attributed to an "intentional change," the team may miss a real bug in the JVM, a library, or the application.

This lesson presents reasoning based on **behavioral contracts**, designing controlled experiments, categorizing root causes, and selecting verifiable remediations. The goal is not merely getting the application running again, but distinguishing **what changed**, **why it changed**, and **who needs to fix it**.

## 1. Four Questions to Separate

When a test case fails after upgrading the JDK, ask four questions:

1. **What was observed?** What result, exception, performance, output bytes, or behavior differs from before?
2. **What is the true contract?** What do the API documentation, Java specification, business criteria, or external protocols require?
3. **Which component altered the behavior?** The JDK, configuration, libraries, operating system, data, time, or application code?
4. **Is that change intentional and supported?** Are there release documents, JEPs, specifications, fixed issues, or security policies as evidence?

A single symptom can carry **two accurate labels simultaneously**. For example, the JDK strengthening encapsulation of internal packages is an intentional change; yet the legacy application arbitrarily using deep reflection into that package is also a design weakness in the application. "Intentional change" describes the cause on the platform side, while "legacy application bug" describes an invalid assumption on the consumer side. The two conclusions do not necessarily exclude each other.

## 2. Root Cause Categories to Distinguish

| Category | Nature | Typical Signs | Who Typically Handles It? |
|---|---|---|---|
| Intentional platform change | The JDK alters default behavior, API support, or policies according to an announced plan. | Backed by a JEP, release notes, migration guide, or new specification. | Application team adjusts code/configuration, sometimes replacing libraries. |
| Latent application bug exposed | The application depended on unguaranteed behavior or worked by accident previously. | Uses internal APIs, relies on unspecified ordering, lacks explicit encoding/locale. | Application team. |
| Actual bug in the JDK or update | The new JDK violates a still-valid contract or introduces an unintended regression. | Small reproducer, controlled comparison case, possibly linked to bug tracker. | JDK vendor; the application may need a temporary workaround. |
| Change in dependency/framework | A library, build plugin, agent, or auxiliary runtime changed APIs, algorithms, or transitive dependencies. | Issue occurs only when changing library versions or classpath configuration. | Dependency owner and application team. |
| Environment or data difference | Different OS, architecture, timezone, locale, certificate store, environment variables, or input files. | Same JDK produces different results on two machines/containers. | Configuration, operations, or data administration team. |
| Underspecified behavior | The old result was just one of several valid results. | Documentation states "no guarantees," "unspecified," or does not commit to order/timing. | Application team must drop the invalid assumption. |

Do not use a label as an intuitive judgment. Every conclusion needs repeatable evidence and a pointer to the affected contract.

## 3. Behavioral Contracts Matter More Than Old Outputs

A common mistake is treating the application's output on the old JDK as the *sole truth*:

```text
Old JDK returns A
New JDK returns B
=> New JDK is wrong
```

This reasoning is incomplete. There are at least three possibilities:

- The specification requires A: B may be a regression, if other variables have been controlled.
- The specification permits both A and B: an application relying on A depended on unguaranteed behavior.
- The specification or policy changed from A to B: identify the intentional change and migration rules.

**Contracts can exist at multiple layers:**

| Contract Layer | Reference Source | Examples |
|---|---|---|
| Java language | Java Language Specification (JLS). | Casting rules, evaluation order, checked exceptions. |
| JVM and class files | Java Virtual Machine Specification (JVMS). | Linkage, bytecode, class loading, JVM exceptions. |
| Java SE API | Javadoc of the exact Java release. | Contracts of `List`, `Map`, `Charset`, `File`. |
| Platform policy | JEP, release notes, migration guide, security guide. | Default UTF-8, strong encapsulation, module removal. |
| Protocols and data | HTTP, TLS, JSON schema, file formats, or business standards. | File encoding, certificates, date-time formats. |
| Application contract | Product requirements, SLAs, contract tests, company API docs. | No data loss, currency rounding policy. |

When discovering a discrepancy, identify which layer owns the requirement before assigning blame. A Java class that satisfies Javadoc yet violates a business rule is still an application issue. Conversely, a JVM violating behavior guaranteed by the language is a candidate for a platform bug.

## 4. "Unspecified," "Implementation-Specific," and "Undefined"

Not every observable behavior is part of the contract. Java documentation uses important phrasing:

- **Specified:** behavior is explicitly specified; applications may rely on it within the stated conditions.
- **Unspecified:** the specification does not commit to a specific outcome under certain conditions.
- **Implementation-specific:** implementations are free to choose a specific policy or value; this may vary across vendors/versions.
- **Deprecated/for removal:** an API or feature is announced as no longer recommended and may be removed on a schedule.

For example, `HashMap` does not guarantee iteration order. If a loop happens to return elements in a particular order on an older JDK, the application cannot treat that as a contract:

```java
import java.util.HashMap;
import java.util.Map;

public class AccidentalOrder {
    public static void main(String[] args) {
        Map<String, Integer> scores = new HashMap<>();
        scores.put("banana", 2);
        scores.put("apple", 1);
        scores.put("cherry", 3);

        scores.forEach((key, value) ->
                System.out.println(key + "=" + value));
    }
}
```

Do not use the line-by-line output of the example above as a golden result across all JDKs. Ordering is unguaranteed; a change in ordering across environments does not by itself prove the new JDK is wrong.

If meaningful order is needed, fix the data contract:

```java
Map<String, Integer> insertionOrder = new java.util.LinkedHashMap<>();
Map<String, Integer> sortedByKey = new java.util.TreeMap<>();
```

`LinkedHashMap` preserves insertion order under normal usage; `TreeMap` maintains order by a comparator or natural ordering. Choose the right container for the desired contract instead of hardcoding an accidental `HashMap` output.

## 5. Designing Controlled Experiments to Isolate the Root Cause

To know whether the JDK is the cause, keep other variables as constant as possible. Casually comparing a developer's Windows JDK 8 environment against a Linux JDK 21 container is insufficient: OS, locale, encoding, certificate store, data, and dependency versions have also changed.

A useful controlled comparison matrix:

| Experiment | Artifact | Runtime | Significance |
|---|---|---|---|
| A — baseline | Previously released build | Old JDK | Confirms known behavior. |
| B — swap runtime | **Exact same artifact file** as A | New JDK | Isolates runtime impact; applies only when bytecode and APIs still run. |
| C — recompile | Recompile same source/dependencies | New JDK | Observes compiler/toolchain and new runtime effects. |
| D — environment control | Keep artifact/JDK, vary one config at a time | Same JDK | Pinpoints timezone, encoding, provider, OS, startup flags. |

If B differs from A while C matches B, the change most likely lies in the runtime or accompanying data/environment. If B matches A while C differs, check compiler options, annotation processing, toolchain, and dependency resolution. These are only **starting hypotheses**, not final conclusions.

Sometimes the old artifact cannot run on the new JDK due to removed APIs; sometimes the new artifact cannot run on the old JDK due to class-file version. Clearly mark which cells are "not applicable" rather than forcing infeasible comparisons.

### 5.1. Locking Down Easily Overlooked Variables

At a minimum, record:

- JDK vendor, full version/build, and architecture.
- OS and container/base image, CPU architecture.
- Classpath/module path, dependency tree, Java agents, and build plugins.
- JVM arguments, system properties, and environment variables.
- Timezone, locale, default charset.
- TLS provider, truststore, security properties, certificates/keystores.
- Database, network endpoints, input data, date/time, random seeds.
- Thread count, load level, GC options, CPU/memory limits, and filesystem.

Do not collect secrets into public logs. If comparing configurations containing credentials, replace them with fingerprints or store only property names.

### 5.2. Basic Commands

```bash
java -version
javac -version
java -XshowSettings:properties -version
```

If using Maven:

```bash
mvn -version
mvn dependency:tree
```

If using Gradle:

```bash
./gradlew --version
./gradlew dependencies
```

On Windows, use `gradlew.bat` where appropriate. The build commands above should only be run in an actual investigation workflow with the proper module/configuration; not every dependency configuration is necessarily displayed identically.

If the application uses containers, check `java -version` **inside the container**. The JDK version on the host machine does not reliably identify the runtime of the running Java process.

## 6. Writing a Minimal Reproducer

A long stack trace from a production system often contains many noisy layers. A minimal reproducer is a small program demonstrating only the discrepancy needing explanation.

For example, if a text file containing Vietnamese characters becomes garbled after a JDK upgrade, do not start with the entire data import pipeline. Isolate the byte reading/writing operation:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class CharsetReproducer {
    public static void main(String[] args) {
        String input = "Tiếng Việt";

        System.out.println("Default charset: "
                + Charset.defaultCharset());

        byte[] implicit = input.getBytes();
        byte[] explicit = input.getBytes(StandardCharsets.UTF_8);

        System.out.println("Implicit bytes: "
                + Arrays.toString(implicit));
        System.out.println("UTF-8 bytes: "
                + Arrays.toString(explicit));
    }
}
```

Run the exact same class file on both runtimes in a controlled environment, recording the default charset and byte output. If the default charset differs, you have a verifiable clue. Still, to conclude the root cause, confirm the JDK version, operating system, configuration, and original data.

A good reproducer has **fixed inputs**, **clear execution steps**, **observed output**, **expected contract output**, and **environment versions**. If it only reproduces inside a large application, confidence in the conclusion is lower.

## 7. Example: Default Charset Switching to UTF-8

A clear example of an intentional change is **JEP 400 — UTF-8 by Default**. Starting in JDK 18, UTF-8 is the standard default charset for Java SE APIs that depend on the default charset, instead of depending on the locale/operating system as before. Certain specialized compatibility configuration mechanisms still exist; do not infer that every terminal device or every I/O API shares the exact same encoding.

### 7.1. Symptom

Legacy application writes:

```java
String content = "Hóa đơn";
byte[] bytes = content.getBytes();
```

Or reads:

```java
String content = Files.readString(path);
```

**Note:** `Files.readString(Path)` since Java 11 defaults to UTF-8 per its API, unlike `new String(byte[])` or `String.getBytes()` which use the default charset. When investigating, identify the exact overload and contract of each API rather than lumping every I/O call together as "using the default charset."

With `String.getBytes()` or `new String(byte[])`, if the old environment's default charset was a non-UTF-8 encoding, byte representations can differ when running on JDK 18+. Legacy files written in the old encoding may be decoded incorrectly if the program reads them using the new default.

### 7.2. Classification Grounds

- JEP 400 announces an intentional change.
- The application relied on the default charset without specifying it in the file contract.
- Differences appear conditionally based on the old encoding, configuration, and input data.

Appropriate conclusion: **an intentional platform change exposed an implicit assumption in the application**.

### 7.3. Sustainable Fix

Select the exact encoding for the data format and specify it explicitly:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class TextIO {
    public static void save(Path file, String content)
            throws java.io.IOException {
        Files.writeString(file, content, StandardCharsets.UTF_8);
    }

    public static String load(Path file)
            throws java.io.IOException {
        return Files.readString(file, StandardCharsets.UTF_8);
    }
}
```

If existing files genuinely use a legacy encoding, read them with that encoding and plan a format migration. Do not force-read all old data as UTF-8 if the original bytes are not valid UTF-8.

Compatibility measures such as `-Dfile.encoding=COMPAT` on JDKs supporting that option can help with testing or transition, yet should not become a long-term data contract. Property documentation and support behavior may change across releases, so prioritize explicit charsets in code and formats.

## 8. Example: Strong Encapsulation of JDK Internal APIs

Modern JDK releases restrict direct access to internal packages and members. JEP 261 introduced JPMS in JDK 9; JEP 396 strengthened default strong encapsulation in JDK 16; JEP 403 reinforced this in JDK 17 by removing the mechanism allowing broad relaxation via `--illegal-access`.

### 8.1. Symptom

Legacy code uses deep reflection:

```java
import java.lang.reflect.Field;

public final class InternalFieldAccess {
    public static void main(String[] args) throws Exception {
        Field value = String.class.getDeclaredField("value");
        value.setAccessible(true);
        System.out.println(value.getType());
    }
}
```

When running on a JDK with strong encapsulation and without appropriate package opening permissions, `setAccessible(true)` can throw `java.lang.reflect.InaccessibleObjectException`. Older releases may have permitted it or warned while still allowing access; that does not turn the internal detail `String.value` into a public API.

### 8.2. Classification Grounds

- JPMS and strong encapsulation are announced, intentional platform changes.
- Application code relied on the private structure of a JDK class.
- The public API contract of `String` does not guarantee the name, type, or accessibility of this field.

Conclusion: **a design flaw depending on internals in the application, exposed by platform encapsulation policy**.

### 8.3. Remediation

Replace the reflective operation with a public API if available. If an external library causes the error, prioritize upgrading to a library version fixed for new-JDK compatibility.

During a transition period, you can open **a specific package** to a target module:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -cp app.jar com.example.Main
```

This example applies only when the consumer is code on the classpath (unnamed module). For named modules, use the actual target module name instead of `ALL-UNNAMED`. `--add-opens` only relaxes reflective access for the specified package and does not guarantee internal API stability. Do not use it as a long-term solution or open packages broadly without restraint.

## 9. Example: Collection Iteration Order Changes

Suppose a system generates a digital signature from a string concatenating elements of a `HashMap`:

```java
StringBuilder payload = new StringBuilder();
for (String key : map.keySet()) {
    payload.append(key).append('=').append(map.get(key)).append('&');
}
String signatureInput = payload.toString();
```

If the program signs the payload in iteration order, a change in order when the JDK, element count, hashing, or data differs will produce a different signature. However, `HashMap` does not guarantee order; the application placed a stability requirement on an unguaranteed property.

**Classification:** a compatibility issue caused by a false assumption in the application. There may have been an implementation change in the platform, yet you do not need to prove "the JDK deliberately changed the order" to identify the contract violation.

**Remediation:** define a canonical ordering (for example, sorting keys using a standardized comparator) before serialization and signing:

```java
import java.util.Map;
import java.util.TreeMap;

Map<String, String> ordered = new TreeMap<>(map);
StringBuilder payload = new StringBuilder();

ordered.forEach((key, value) -> {
    payload.append(key).append('=').append(value).append('&');
});
```

In real systems, also specify character escaping, delimiters, Unicode normalization, `null` representation, and key order. Merely switching `HashMap` to `TreeMap` may be insufficient if the signing protocol does not define a canonical format.

## 10. Example: Java EE and CORBA Modules No Longer Bundled with the JDK

JEP 320 removed several Java EE and CORBA modules from JDK 11, including JAXB. An application using:

```java
import javax.xml.bind.JAXBContext;
```

may fail to compile or run on JDK 11+ if the artifact does not carry the necessary dependency.

This is an **intentional platform packaging change**, not that the JDK compiler "no longer supports XML" or that Java lost all XML libraries. The application must declare the appropriate JAXB dependency or switch to a supported stack/API, checking compatibility between the `javax.xml.bind` and `jakarta.xml.bind` namespaces according to the framework version in use.

How to investigate:

1. Search for imports, reflective references, and dependencies related to JAXB.
2. Read JEP 320 along with the target JDK's migration guide.
3. Check `mvn dependency:tree` or Gradle reports to see if the artifact has the JAXB API and implementation.
4. Choose dependencies compatible with both the framework and the JDK baseline.
5. Run integration tests for marshalling/unmarshalling, schemas, and exception mapping.

Not every error reporting `ClassNotFoundException` is caused by removed modules; verify the exact class name, classloader, and classpath/module path.

## 11. Example: Restricted TLS and Security Algorithms

An application making HTTPS connections may work on an older JDK update yet fail after an update with `SSLHandshakeException`. Do not immediately conclude that the HTTP client in the new JDK is broken.

There may be several causes:

- A JDK update disabled an algorithm, cipher suite, protocol, or key size that is no longer secure.
- The server uses an old TLS configuration, an expired certificate, or an invalid certificate chain.
- Truststore or certificate authority differs between the two environments.
- A proxy, middlebox, or load balancer sends an unexpected handshake.
- The HTTP/client or security library was upgraded simultaneously.
- There is an actual regression in the TLS provider, though evidence is required.

In the JDK, security properties such as `jdk.tls.disabledAlgorithms` and `jdk.certpath.disabledAlgorithms` can affect TLS negotiation and certificate verification. These policies can change in update releases as well, not only across feature releases.

A safe investigation approach:

1. Record the full JDK version/build and client/server TLS configuration.
2. Inspect the certificate chain, expiration date, hostname, and truststore.
3. Compare release notes and security properties across both JDK builds.
4. Reproduce against a team-controlled test server, not just a production endpoint.
5. Try updating the server to use supported protocols/ciphers.

**Do not** disable hostname verification, skip certificate validation, or re-enable weak algorithms in production merely to "prove the JDK has a bug." If a temporary workaround is needed, it must have security approval, a narrow scope, and a clear removal date.

## 12. Example: Locale, Timezone, and Cultural Data

The following code depends on the default locale:

```java
String normalized = input.toUpperCase();
```

Results can differ across certain locales, such as uppercasing rules involving Turkish. The issue can appear when a container/JDK changes the default locale, even if the Java source does not change.

For identifiers, protocol names, enum tokens, or non-natural-language keys, typically use:

```java
import java.util.Locale;

String normalized = input.toUpperCase(Locale.ROOT);
```

For user-facing text, use a `Locale` selected according to the user or business requirement; do not always choose `Locale.ROOT`.

Beyond environment variables, Java has changed how locale data is sourced across releases; JEP 252 made CLDR the default locale data source starting in JDK 9. A difference in date/month formatting, language names, or separators may stem from new locale data policies, CLDR versions, or locale configuration.

**Classification must be based on the specific source of change:** seeing a different date string alone is insufficient to say "JDK intentional change." Inspect the input locale, timezone, formatter, provider, and locale data. If the business contract requires a fixed format, choose an explicit formatter and locale rather than locking in an accidental environment output.

## 13. Example: Default GC and Performance Changes

JEP 248 made G1 the default garbage collector in JDK 9 for many server-class configurations. When migrating from an older JDK, CPU utilization, pause times, heap behavior, or throughput may differ even with identical code and data.

However, a performance difference is not automatically a JVM bug:

- The default GC may change intentionally.
- Heuristics, JIT compilation, tiered compilation, or container awareness may have been tuned.
- Legacy JVM flags may have been changed, deprecated, or removed.
- Container CPU/memory limits may differ, leading to different heap sizing or parallelism.
- Thread scheduling, I/O, database response, and actual load may differ.

To find the cause, measure metrics under the same load scenario: throughput, P50/P95/P99 latency, pause time, allocation rate, heap, and CPU. Capture actual GC behavior with logging/metrics appropriate for the target JDK.

With Unified JVM Logging in modern JDKs, an example can be:

```bash
java -Xlog:gc*:file=gc.log:time,level,tags \
     -jar app.jar
```

Do not restore legacy JVM flags wholesale from old configurations before collecting measurements. Forcing the old GC back on may retain certain performance characteristics, yet is not necessarily the optimal or long-term supported solution.

## 14. When Should You Suspect an Actual JDK Bug?

A JDK bug is more suspect when multiple signs align:

- There is a **still-valid contract** that the new JDK appears to violate.
- A small reproducer, independent of the large application, with fixed inputs.
- The same artifact/source across multiple JDK builds shows a clear regression boundary.
- The result cannot be explained by changes in configuration, data, dependencies, locale, OS, or access permissions.
- No release documentation or specification change permits the new result.
- A corresponding issue exists in the JDK Bug System, or the failure reproduces on another update build with reliable data.

Hypothetical example: a Java SE method's Javadoc requires returning result X for input Y, yet in a specific JDK build it returns Z while earlier/later builds return X. If the reproducer is standalone and controls enough variables, that is a candidate for an actual bug.

**Warning:** The fact that release notes do not mention a difference is insufficient to conclude the JDK has a bug. There could still be unguaranteed behavior, a dependency change, or a published fix not yet found. Keep the investigation status as "undetermined" until evidence is strong enough.

### 14.1. Packaging an Actionable Bug Report

A good report typically includes:

```text
Title: [JDK version] Contract violation in [API/component]

Environment:
  JDK vendor and full build:
  OS / architecture:
  JVM arguments:
  Dependencies:

Minimal reproducer:
  Exact source:
  Build command:
  Run command:

Expected:
  Behavior according to specification/API contract:

Actual:
  Output / exception / trace:

Comparison:
  Known working JDK build:
  Known failing JDK build:
  Other controlled observations:

References:
  Javadoc / JLS / JVMS:
  Release notes / JEP / related JBS issue:
```

Do not include secrets, production databases, or customer information in a public reproducer.

## 15. Decision Tree When Observing Different Behavior

```text
      Does application behavior differ after JDK upgrade?
                          |
                          v
                Is it reproducible?
                   /               \
                 No                 Yes
                  |                  |
          Collect more data          v
                        Are environment, artifact,
                              and input fixed?
                               /          \
                             No           Yes
                              |             |
                      Create baseline       v
                                    What does the contract specify?
                                      /             \
                               Not guaranteed       Guaranteed
                                    |                  |
                         Fix application             v
                         assumptions          Is there a published
                                                platform change?
                                                  /         \
                                                Yes        Unclear
                                                 |            |
                                        Evaluate migration    v
                                                       Minimize reproducer,
                                                       check JBS and vendor
```

The decision tree is only an investigation tool. You may need to revisit earlier steps when uncovering additional uncontrolled environment variables or finding a bug in a library rather than the JDK.

## 16. Working with Release Documentation and Evidence Sources

When you need to confirm whether a difference is intentional, consult sources in an appropriate order:

1. **Javadoc/JLS/JVMS of the target release** to determine the contract.
2. **JEPs** for major platform changes such as default UTF-8, JPMS, or encapsulation.
3. **Release notes and migration guides** for both feature releases and update releases.
4. **JDK Bug System (JBS)** to search for regressions, bug fixes, CSRs, and fix statuses.
5. **JDK vendor documentation** if using a build/vendor with different patches or support policies.
6. **Dependency changelogs** if the application upgraded frameworks, drivers, or plugins simultaneously.

Do not lump all changes under "Java 17 differs from Java 8." Many changes appeared incrementally in JDK 9, 11, 16, 17, or 18; some occurred only in an update release. Identifying the **starting milestone of the change** helps explain the cause and select a fix.

One way to record evidence:

| Evidence ID | Source | What It Proves | Limitations |
|---|---|---|---|
| E1 | Java API Javadoc | The method's contract. | May not describe all environment configurations. |
| E2 | JEP / release note | An intentional change or published bug fix. | Does not replace testing on the specific application. |
| E3 | A/B reproducer | Runtime-dependent behavior difference under controlled conditions. | Only proves the tested conditions. |
| E4 | Log / heap / GC / TLS trace | Technical trace at the time of failure. | May lack information from other dependencies. |
| E5 | Contract test | Whether business behavior is right or wrong. | Tests must originate from real requirements, not just old outputs. |

**Principle:** A release note confirms the reason for a change; it does not by itself verify whether the application handles it properly or improperly. A reproducer proves the phenomenon; specifications and contracts decide the criteria for correctness.

## 17. Do Not "Fix" Intentional Changes by Disabling Protections

When seeing an application fail, some tempting quick fixes are:

- Opening all internal packages with numerous `--add-opens`.
- Re-enabling weak ciphers/TLS algorithms or disabling certificate validation.
- Keeping machine-dependent `file.encoding` without defining a data format.
- Pinning an old JDK that receives no security updates.
- Swallowing exceptions to make integration tests pass.
- Locking in an accidental result order via a snapshot test.

These measures can turn visible errors into silent risks. A temporary workaround should only be accepted when:

1. The root cause and impact are clearly identified.
2. Its applicability scope is as narrow as possible.
3. Approval is obtained for the associated security/operational risk.
4. Tests confirm the workaround does not alter the business contract.
5. There is a ticket, owner, and target removal date.

If a JDK rollback is required to keep production stable, still evaluate the security impact and support lifetime of the rolled-back build. Rollback is an operational measure, not a technical explanation in itself.

## 18. When Application Contracts Must Evolve Alongside the Platform

Sometimes the platform changes intentionally, and the application needs to **proactively update its contract** rather than preserving legacy behavior at all costs.

Examples:

- Legacy-formatted files are permanently converted to UTF-8 with an incremented format version.
- Plugins using internal APIs are replaced with public APIs or a stable SPI.
- The server enforces modern TLS, and legacy clients must be upgraded.
- Business APIs returning collections "in HashMap order" are standardized to an explicit order.

When changing a contract, plan data versioning and bidirectional compatibility:

| Question | Example Answers to Decide |
|---|---|
| Will old data still be readable? | Yes, via a legacy reader using the designated charset. |
| Does new data need to be readable by the old app version? | During rolling rollouts, a compatibility window may be needed. |
| Is a feature flag needed for gradual migration? | Yes, if not all data can be converted at once. |
| Do external clients need notification? | Yes, if the new API or format changes results. |
| On rollback, how is new data handled? | There must be a rollback procedure or dual-read mechanism. |

A successful migration is not always about preserving every old output. It must preserve **the commitments that must remain**, while updating commitments changed under controlled governance.

## 19. Testing to Distinguish Regressions from Deliberate Changes

Do not write every test in the style of "assert against old JDK output." Separate three test layers:

### 19.1. Contract Tests

Describe what the API or business logic must do, regardless of runtime:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class ExportEncodingTest {
    @Test
    void exportsUtf8IndependentlyOfDefaultCharset() {
        byte[] bytes = "Việt Nam"
                .getBytes(StandardCharsets.UTF_8);

        assertEquals(
                "Việt Nam",
                new String(bytes, StandardCharsets.UTF_8));
    }
}
```

This is a simple example illustrating an explicit charset contract. In a real system, the test must call the application's own export code rather than testing only the standard API in isolation.

### 19.2. Characterization Tests

Record legacy behavior to understand the current state and support migration, without **assuming by default** that it is the right behavior. For example, capture the raw bytes of a legacy file or how the program generates signatures before changing formats.

When identifying a discrepancy caused by unguaranteed behavior, update the test into a contract test for the desired behavior. Do not force the new JDK to produce an unspecified exact order or timing.

### 19.3. Cross-Runtime Tests

Run the same contract test suite across the JDKs supported by the product:

```text
Test suite / fixtures
      |
      +--> JDK baseline
      |
      +--> JDK target
      |
      +--> New JDK update (if needed)
                 |
                 v
     Compare by contract + metadata
```

Do not treat a test failing on the new JDK as a migration failure if the test enforces an accidental behavior of the old JDK. When changing a contract intentionally, update expected results together with migration notes and supporting evidence.

## 20. Sample Incident Classification Record

Can be recorded for each issue:

```yaml
incident: MIG-JDK-042
title: "CSV import đọc sai dấu tiếng Việt"
affectedFlow: "Import hồ sơ khách hàng"
baselineRuntime: "JDK cũ và build cụ thể"
targetRuntime: "JDK mới và build cụ thể"
artifact: "Checksum hoặc mã bản phát hành"
input: "File fixture đại diện đã loại dữ liệu nhạy cảm"
expectedContract: "CSV legacy dùng encoding được quy định"
observedOld: "Đọc đúng"
observedNew: "Một số ký tự bị thay thế"
controlledDifference: "Default charset đổi"
platformEvidence: "JEP 400 và release notes liên quan"
classification: "Intentional platform change + implicit app assumption"
remediation: "Đọc/ghi với charset tường minh; chuyển đổi dữ liệu legacy"
owner: "Nhóm import dữ liệu"
verification: "Contract test chạy trên cả runtime nguồn và đích"
status: "Đang khắc phục"
```

The values in the example are illustrative data. Real records must specify exact versions/builds and links to concrete evidence; do not copy generic descriptions into reports and treat the root cause as determined.

An incident may have multiple contributing factors. Include a **confidence** or **hypothesis status** field such as "hypothesis," "reproduced," "checked against specification," or "root cause confirmed" to avoid turning tentative conclusions into facts.

## 21. Distinguishing Platform Changes from Deployment Changes

Behavior can change because the runtime is configured differently, not necessarily because Java SE changed its contract.

For example, two JDK builds of the same feature release from different vendors may ship different security providers or patch sets. Two containers both running JDK 21 may have different timezone databases, truststores, or system locales. A JDK update can fix a TLS bug while application code and the feature release remain unchanged.

Therefore, separate in reports:

- **Spec change:** published specification or policy changed.
- **Implementation change:** the implementation changed while potentially remaining within the old contract.
- **Runtime configuration change:** flags/properties/providers changed.
- **Distribution difference:** vendor/build differs.
- **Application/dependency change:** code or artifacts in the application differ.

Do not attach the blanket label "JDK upgrade" to everything. Pinpointing the milestone of change and connecting it to application assumptions helps the team decide whether to fix code, fix configuration, upgrade dependencies, or file a vendor bug report.

## 22. Common Fallacies

**"It used to work before, so the new JDK must be wrong."** Check the contract first. The old behavior may have been unguaranteed or a long-standing bug.

**"There is a JEP, so no investigation is needed."** A JEP describes intent, but does not prove every observed failure was caused by that JEP.

**"Just update the expected test output to match the new output."** You might be accepting a business-incorrect result. Tests must be grounded in contracts, not merely making the pipeline green.

**"With the same class files, the new JDK is the only variable."** OS, containers, data, module path, and security properties can also differ.

**"Compiling successfully means runtime compatible."** Runtime may still lack classes, block reflection, require new providers, or produce different output.

**"An error appearing only when upgrading the JDK is definitely a JVM bug."** The trigger may be the new JDK properly enforcing a contract that the application previously violated.

**"Changing one flag completes the migration."** A flag may be a temporary workaround and cannot substitute for removing internal dependencies or implicit formats.

**"No exception means the behavior is right."** Discrepancies in encoding, ordering, timezone, or numeric values can cause silent data corruption.

## 23. Investigation Procedure for Real Projects

### Step 1: Record Symptoms and Impact

Distinguish startup errors, compile errors, runtime exceptions, data corruption, performance issues, or security issues. Assess impact on users and external systems.

### Step 2: Gather a Reproducible Baseline

Record the JDK version/build, artifact checksum, dependency graph, JVM args, env, input fixtures, and expected contract.

### Step 3: Conduct Controlled Comparison Experiments

Run the same artifact on source/target runtimes if feasible. Vary one variable at a time; do not upgrade the JDK, framework, OS, and configuration simultaneously before establishing a baseline.

### Step 4: Create a Minimal Reproducer

Isolate code using the relevant API, capture inputs and outputs, inspect the error class/stack trace, and avoid external system dependencies.

### Step 5: Identify the Contract

Read Javadoc/JLS/JVMS, protocol specifications, business requirements, and compatibility promises made to clients.

### Step 6: Gather Evidence of Platform Changes

Cross-check JEPs, release notes, migration guides, and bug trackers at the exact version/update milestone.

### Step 7: Assign a Classification with a Confidence Level

Choose one or more cause categories, clearly recording what is confirmed versus hypotheses needing verification. If information is insufficient, keep the status as undetermined.

### Step 8: Select a Sustainable Fix

Prioritize public APIs, explicit configuration, supported dependencies, contract tests, and versioned data migration. Use temporary workarounds only with explicit conditions and owners.

### Step 9: Test and Deploy in a Controlled Manner

Run regression/integration tests on the target runtime, measure performance, and monitor for signs of silent data errors. Prepare a rollback plan if needed.

### Step 10: Record the Decision

Record the JDK milestone, evidence, classification, and acceptance criteria. This documentation keeps future migrations from repeating the same investigation.

## 24. Checklist Before Concluding "JDK Bug" vs. "Intentional Change"

- [ ] Identified the exact symptom, rather than merely describing "the app failed after upgrade."
- [ ] Recorded version, vendor, and build of both source and target JDKs.
- [ ] Identified the artifact/source/dependencies and active flags.
- [ ] Controlled inputs, OS, timezone, locale, charset, certificates, and necessary environment variables.
- [ ] Identified which behaviors are guaranteed by public or business contracts.
- [ ] Distinguished specified behavior from unspecified/implementation-specific behavior.
- [ ] Tried a minimal reproducer or an equivalent controlled experiment.
- [ ] Checked JEPs/release notes/migration guides for the exact version.
- [ ] Checked the possibility of bugs in the JDK, dependencies, and environment configuration.
- [ ] Recorded the confidence level of the conclusion and any unverified parts.
- [ ] Designed the fix around contracts rather than unconditionally preserving old outputs.
- [ ] Added appropriate tests for data, security, and performance.
- [ ] Any temporary workarounds are scope-limited and have a removal plan.
- [ ] Saved migration notes and details to support future investigations.

## References

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset change starting in JDK 18.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): JPMS foundation starting in JDK 9.
- [JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396): default strong encapsulation starting in JDK 16.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): tightened access limits to JDK internals in JDK 17.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): removal of legacy modules from JDK 11.
- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252): default locale data source change starting in JDK 9.
- [JEP 248 — Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248): default GC change in JDK 9.
- [Oracle Java SE Migration Guides](https://docs.oracle.com/en/java/javase/): migration guides and release documentation by specific JDK.
- [Java Language Specification](https://docs.oracle.com/javase/specs/jls/se21/html/index.html): Java language contract.
- [Java Virtual Machine Specification](https://docs.oracle.com/javase/specs/jvms/se21/html/index.html): JVM and class-file contract.
- [JDK Bug System](https://bugs.openjdk.org/): bug reports, fixes, and regression-related issues.

## Conclusion

Differences after a JDK upgrade cannot be classified merely by comparing two outputs. You need to know which contract is being executed, which platform version changed, which environmental factors differ, and what evidence confirms an intentional change. Default UTF-8 charset, strong encapsulation, module removal, or TLS policies can expose implicit assumptions in legacy applications, while specification-violating behavior may still be an actual JDK bug. The reliable approach is to establish a reproducible baseline, check JEPs/Javadoc/release notes, classify with an explicit confidence level, and fix according to supported contracts. The goal of migration is not preserving every habit of the old JDK, but upholding valid commitments and adapting in a controlled manner to the new platform.
