# Reading Library Release Notes and Breaking Changes

Upgrading the JDK is only one part of Java migration; the rest often lies in the libraries that the application uses. A program that compiles on a new JDK can still fail when changing the version of a framework, JSON serializer, JDBC driver, logging library, HTTP client, or build plugin. Conversely, an old library may start up yet carry security risks, lack JPMS support, or only happen to work because of JDK internal access.

Therefore, **reading release notes and breaking changes** is an essential dependency management skill. The goal is not to skim a list of new features, but to turn the library author's release information into a **verifiable list of impacts** on the application's own source code, binaries, configuration, data, runtime environment, and release process.

This lesson presents a practical workflow from identifying the running version, finding official documentation, classifying changes, reading migration guides across multiple versions, to building an impact matrix and testing the rollout. Illustrative hypothetical examples will be explicitly marked as such to avoid confusing them with the actual release history of a specific library.

## 1. What Are Release Notes and Why Read Them?

**Release notes** are documents describing notable points of a release: new features, bug fixes, API changes, platform requirements, known issues, and sometimes migration instructions. Depending on the project, this information is organized into:

- **Release page:** describes each release, possibly tied to a tag and artifact.
- **CHANGELOG:** a change log by version, sometimes only a list of commits or issues.
- **Migration/upgrade guide:** a version transition guide, focusing on changes that require updating old code.
- **Compatibility matrix:** a table of supported combinations of JDK, framework, server, driver, or plugin versions.
- **Deprecation policy:** when an API is warned about, replaced, and potentially removed.
- **API reference/Javadoc:** detailed contract of each method, class, and module.
- **Security advisories:** affected versions, fixes, and risk mitigation measures.
- **Issue tracker/commit/tag diff:** supplemental evidence when release notes are not clear enough.

Not every project provides all of the above documents. Reading only a "Bug fixes and improvements" line is usually insufficient to conclude that an upgrade has no breaking changes.

### 1.1. Three Questions to Answer After Reading

1. **What changed?** APIs, defaults, dependencies, minimum JDK, data formats, security, or operations?
2. **Does the application use that part?** Are any imported classes, API calls, enabled features, transferred data, or indirect dependencies affected?
3. **How do we prove nothing is broken?** What code fixes, configuration updates, dependency changes, compatibility tests, or deployment ordering are required?

Reading the documentation without answering these three questions has not yet turned release notes into an actionable migration plan.

## 2. Start from the Dependencies Actually Used

Before looking up release notes, you need to know the exact library version the application is running. `pom.xml` or `build.gradle` only expresses **declared requirements**; dependency resolution may pick a different version due to BOMs, dependency management, version constraints, conflict resolution, or transitive dependencies.

Suppose an application directly declares `com.example:report-core:1.4.0`, yet a framework or dependency management overrides the resolved version. If you read the changelog for the declared version without verifying the resulting artifact, the team may analyze the wrong upgrade range.

### 2.1. Maven: Inspecting the Dependency Tree

```bash
mvn dependency:tree
```

To focus on a specific artifact:

```bash
mvn dependency:tree \
    -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

The command in the example uses the Maven Dependency Plugin when the plugin and build environment are ready. Inspect the output to see which path pulls the dependency in and which version is selected.

For multi-module projects, run it in the appropriate module or use Maven's module selection option. Additionally, `mvn help:effective-pom` lets you observe the configuration after inheriting the parent POM and dependency management, though **the effective POM alone does not replace the dependency tree** in explaining which artifacts are actually resolved.

### 2.2. Gradle: Inspecting a Specific Configuration

```bash
./gradlew dependencies --configuration runtimeClasspath
```

To see why a library is selected:

```bash
./gradlew dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath
```

`compileClasspath` and `runtimeClasspath` configurations may differ; Android, Kotlin, or multi-project builds also have other configurations. Choose the configuration reflecting where the issue actually occurs.

On Windows, use `gradlew.bat` or the appropriate Gradle invocation for the project. These commands are examples for dependency management workflows; reading release notes does not require modifying the project or running a build immediately.

### 2.3. Record Complete Artifact Coordinates

For Maven, identify a dependency by:

```text
groupId : artifactId : version [: classifier]
```

Example:

```text
com.fasterxml.jackson.core:jackson-databind:2.x.y
```

`2.x.y` here is a placeholder notation, not an actual version. When creating a migration record, record the **exact version** as well as the repository/source providing the artifact.

You should also record:

- Artifact checksum when traceability is needed.
- Related libraries in the same family and their versions.
- The framework/BOM managing versions.
- The module/scope where the dependency is used (compile, runtime, test, or plugin classpath).
- Supported runtime and compiler JDKs.
- All places where the dependency is present: services, batch jobs, plugins, container images.

**Do not confuse:** libraries sharing the same name yet differing in groupId, classifier, or artifact packaging can be different products; a fork's changelog does not automatically apply to the official artifact.

## 3. Finding Trustworthy Sources of Release Notes

Start from the project's official channels:

1. Vendor documentation or release page.
2. Official repository with tags/releases and `CHANGELOG.md`.
3. The migration guide matching the exact version pair.
4. Javadoc/API reference for both old and new versions.
5. Compatibility matrix with JDK and frameworks.
6. Official security advisories or project-confirmed vulnerability records.
7. Related commits/issues/PRs when clarification is needed.

Sources such as Maven Central or artifact repositories help verify coordinates/versions and metadata. They do not necessarily provide full explanations of breaking changes. Personal blogs, tool-generated summaries, or forum answers can help point you in the right direction, yet must be cross-checked against official documentation before serving as the basis for production decisions.

### 3.1. Verify the Exact Version, Branch, and Tag

A project may have:

```text
1.8.x  : maintenance branch
2.0.x  : new major line
2.1.x  : current feature line
```

The changelog on the `main` branch may not match version `1.8.7` currently used by the application. Identify the documentation applicable to the **released tag/version**, not just the latest source code.

For example, upgrading from `1.8.7` to `2.1.3` may require reading:

- Release entries between `1.8.7` and the last `1.8.x`, if needed.
- The migration guide from `1.x` to `2.0`.
- Breaking changes and fixes in `2.0.x`.
- Subsequent changes from `2.0` to `2.1.3`.

Do not skip intermediate major versions merely because the final target is a newer version.

### 3.2. Read "Known issues" and "Upgrade notes"

This information often directly affects rollout:

- A bug present in the target version.
- An old configuration that must be removed.
- An incompatible driver/agent version.
- A data migration command that must run before starting the new version.
- A feature disabled by default for security reasons.

If the upgrade target has a known issue affecting a core flow, you may need to pick another patch version on the same branch or change the rollout order. Do not merely skim the list of new features and ignore deployment notes.

## 4. Understand SemVer Properly, Yet Never Blindly Trust Version Numbers

Semantic Versioning is typically described as:

```text
MAJOR.MINOR.PATCH
```

Under SemVer, major is typically tied to incompatible API changes, minor to backwards-compatible features, and patch to backwards-compatible bug fixes. However:

- Not every Java library follows SemVer.
- A project may use date-based versioning, release trains, or a custom scheme.
- `1.0` may have a different policy from `0.x`.
- A security fix in a patch release may intentionally reject old unsafe behavior.
- Transitive dependency updates in a minor/patch release can still affect runtime.
- "Binary-compatible" is not synonymous with "behavior-compatible" in every case.

Therefore, **version numbers are a signal to prioritize reading**, not a substitute for release notes and testing.

### 4.1. Reading Priority Levels

| Upgrade type | Initial attention level | What to prioritize |
|---|---|---|
| Patch within the same branch | Lower, yet do not skip. | Security fixes, behavioral regressions, dependency changes, JDK fixes. |
| Minor/feature | Medium. | API additions, default changes, deprecations, transitive dependencies. |
| Major | High. | Removed/renamed APIs, constructor changes, configuration migration, Java baseline, data format. |
| Switching framework or serializer family | Very high. | Entire contract, ecosystem integration, and deployment strategy. |
| Changing groupId/artifact or fork | High. | Provenance, license, security, namespace, and compatibility policy. |

In practice, jumping from an old patch to a new patch after several years can accumulate more changes than a very small minor upgrade.

## 5. Classifying Breaking Changes by Compatibility Layer

A library can be "incompatible" in several senses:

| Category | Symptom | Example |
|---|---|---|
| **Source compatibility** | Old code fails to recompile. | Class/method deleted, signature or package changed. |
| **Binary compatibility** | Previously compiled bytecode fails to link when loaded/run with the new library. | `NoSuchMethodError`, `NoClassDefFoundError`, `AbstractMethodError`. |
| **Behavioral compatibility** | Code still runs yet produces different results. | Default timeout, retry policy, or validation differs. |
| **Configuration compatibility** | Property names, default flags, or config files change. | An old option is renamed, a security option is turned off. |
| **Data/wire compatibility** | Consumers fail to read new/old data properly. | JSON field, XML namespace, database schema, or message format changes. |
| **Runtime/JDK compatibility** | Library requires a newer Java version or new module permissions. | Higher class file version; reflection blocked by JPMS. |
| **Operational compatibility** | Startup, metrics, thread pools, deployment, or resources change. | New shutdown mechanism, logging format changes. |
| **Security compatibility** | Old data/behavior is no longer accepted due to safety controls. | Weak algorithms blocked or unsafe input rejected. |
| **Dependency ecosystem** | Bundled library versions are incompatible. | Framework pulls in a new driver/parser version. |

These categories can occur simultaneously. A major release may change Java APIs while also changing the JSON format. If you only fix compile errors and ignore the data contract, the migration is still incomplete.

## 6. Source API Breaking Changes

**Hypothetical** example: library `com.example:billing-client` changes its API between 1.x and 2.x:

**Old API:**

```java
public final class BillingClient {
    public Receipt charge(String accountId, long amountMinorUnits) {
        // Old API
        throw new UnsupportedOperationException();
    }
}
```

Application call site:

```java
Receipt receipt = client.charge("A-100", 5000L);
```

**New API:**

```java
public final class BillingClient {
    public Receipt submitPayment(PaymentRequest request) {
        // New API
        throw new UnsupportedOperationException();
    }
}
```

The old code will fail to compile because `charge(String, long)` no longer exists.

### 6.1. How to Read API Migration Notes

When release notes state "rename `charge` to `submitPayment`", still check:

1. Did input types and validation rules change?
2. Did monetary units change (minor units vs. decimal string)?
3. Did return types or synchronous/asynchronous contracts change?
4. Did checked exceptions or error codes change?
5. Did idempotency/transaction semantics change?
6. Is a deprecated adapter still available for a transitional version?

A simple API rename on paper can hide larger behavioral changes.

### 6.2. Check Imports and Package Relocation

Release notes sometimes state:

```text
Old package: com.example.billing.v1
New package: com.example.billing.api
```

This is an illustrative example. For real projects, confirm the artifact ID, package, module name, and automated migration guide (if provided). Do not assume every package rename is supported by forwarding classes in the library.

## 7. Binary Compatibility Breaking Changes

Binary compatibility concerns the ability of previously compiled class files to link against a new library without recompiling.

Suppose the application was compiled against a library with:

```java
public String normalize(String input)
```

Later at runtime, the library only has:

```java
public String normalize(CharSequence input)
```

At the source level, the call may remain valid after recompilation. However, old bytecode contains a method descriptor referencing `normalize(Ljava/lang/String;)Ljava/lang/String;`; if the new library no longer has that method, the JVM can throw `NoSuchMethodError` at execution time.

### 7.1. Common Runtime Linkage Errors

| Error | Preliminary meaning | Investigation step |
|---|---|---|
| `NoSuchMethodError` | Method descriptor called by bytecode does not exist in runtime class. | Compare API/binary, dependency tree, and runtime classpath. |
| `NoSuchFieldError` | Field referenced by bytecode is no longer compatible. | Compare field type/name and the artifact actually loaded. |
| `NoClassDefFoundError` | Required class could not be present/initialized at runtime. | Check classpath, module path, transitive dependencies, and root cause error. |
| `ClassNotFoundException` | Class loader could not find the requested class by name. | Check artifact packaging and class loader hierarchy. |
| `AbstractMethodError` | An instance lacks an implementation matching the method being called. | Check interface/API evolution and old implementations. |
| `IllegalAccessError` | Linkage encountered invalid class/member access permissions. | Check public/protected/package access, JPMS exports. |
| `UnsupportedClassVersionError` | Class file uses a newer major version than the JVM understands. | Check the library's minimum Java version. |

A runtime exception does not always mean the **target release itself is broken**. For example, `NoSuchMethodError` can occur when two versions of a library coexist on the classpath or when dependency resolution selects a version incompatible with the framework.

### 7.2. API Comparison Tools

Helpful tools include:

- `japicmp`: compares Java APIs and checks binary/source incompatibilities between old and new JARs.
- `Revapi`: checks API compatibility using configurable rules and extensions.
- `jdeps`: inspects class/package/module dependencies and internal APIs.
- `javap`: inspects method descriptors and class file metadata.

Example of inspecting method structure once you have the artifact:

```bash
javap -classpath library.jar -s com.example.billing.BillingClient
```

Tool output is only part of the evidence. API diff tools cannot automatically know business contracts, data formats, timeouts, security flaws, or reflection mechanisms. Never treat a "binary compatible" report as a guarantee that the entire migration is safe.

## 8. Behavioral Breaking Changes Are Dangerous Because They Often Raise No Errors

This category slips past compilation and simple unit tests most easily.

**Hypothetical** example of an HTTP client changing its policies:

| Case | Old version | New version |
|---|---|---|
| Default connection timeout | Unspecified / unbounded | 10 seconds |
| Automatic retry | Retries on certain responses | Retry disabled by default |
| Redirect | Allows a redirect type | Requires opt-in |
| TLS validation | Accepts legacy configuration | Rejects weak algorithms |

These values are illustrative, **not release notes of any real HTTP client**.

Each "Changed default retry policy" line should be turned into questions:

- Which requests are allowed to retry?
- Are requests idempotent?
- Who performs retries: client, service mesh, or gateway?
- Do overall timeout and per-phase timeouts differ?
- Does losing retries increase transient errors?
- Does keeping the old retry behavior risk creating duplicate transactions?

A single changed default option may require updating tests, metrics, SLOs, and circuit-breaker configuration.

### 8.1. Avoid Unconditionally Restoring Old Defaults

If a change was made to fix a bug or security issue, re-enabling old behavior may be inappropriate. Before setting a flag, determine:

1. Why did the library change the default?
2. Is there a deprecation or security warning?
3. Does the system rely on the old behavior as part of a business contract?
4. Is there a safer long-term solution?
5. If using a temporary workaround, is there an owner and a removal timeline?

## 9. Configuration and Defaults: Search for Both Old and New Names

A release note may say "property X is renamed to Y", "option Z is removed", or "default is now false".

Hypothetical example:

```properties
# Old configuration
example.client.retry.enabled=true
example.client.timeoutMillis=30000
```

And:

```properties
# New configuration
example.client.retry.mode=idempotent-only
example.client.request-timeout=30s
```

This is not merely a key swap. The value `true` is not wholly equivalent to `idempotent-only`, timeout units may change, and frameworks may silently ignore old keys without warning.

A helpful migration table:

| Old configuration | New configuration | Semantic change | Action |
|---|---|---|---|
| `retry.enabled=true` | `retry.mode=idempotent-only` | Retries idempotent operations only. | Evaluate transaction flows. |
| `timeoutMillis=30000` | `request-timeout=30s` | Timeout scope may differ. | Test connect/read/total timeouts. |
| Old key removed | No replacement key | Feature removed. | Remove config and update design. |

Release notes typically list only the changed names; the application team's job is to find **everywhere configuration is assigned**: source code, deployment manifests, environment variables, secret stores, feature flags, test fixtures, and operational templates.

## 10. Minimum JDK and Runtime Compatibility Issues

A library may raise its minimum supported Java version. This is a critical breaking change when an application still must run on multiple JDKs.

**Hypothetical** example:

```text
library 1.x -> supports Java 8+
library 2.x -> requires Java 17+
```

If the product still supports a Java 11 runtime, you cannot use that 2.x artifact inside a Java 11 process merely by configuring `--release 11` for application code. Library class files may use major version 61 (Java 17), which Java 11 cannot load.

Key class file major version milestones:

| Java | Major version |
|---:|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

Check class metadata when you have the JAR:

```bash
javap -verbose -classpath library.jar com.example.library.Api
```

Look for `major version`. This value gives a clue about the class file, though compatibility also depends on APIs, native libraries, reflection, preview features, and supporting components.

### 10.1. "Works On" Differs from "Supported On"

A library might happen to run on a new JDK, yet its authors **only test or support** a specific set of versions. Read the official compatibility matrix:

- Minimum JDK required to run.
- JDKs covered by the project's CI/test matrix.
- JDKs usable to compile the library.
- Related framework, servlet container, driver, or Jakarta EE versions.
- Supported operating systems/architectures if the library contains JNI/native code.

"The JAR loads on JDK 21" does not by itself prove the vendor supports all of its features on JDK 21.

## 11. JPMS, Reflection, and Service Loading

When upgrading from an older JDK or a non-modular library to a newer release, note:

- `module-info.java` may be introduced or modified.
- The automatic module name may differ from the declared module name.
- Package `exports`/`opens` changes can break reflective code.
- ServiceLoader provider metadata may move from `META-INF/services` to `provides ... with ...`.
- Modules may no longer be resolved automatically.
- A library may change packages without changing its artifact name, or vice versa.

Example:

```text
java.lang.reflect.InaccessibleObjectException:
  module com.example.model does not "opens ..."
```

Such an error does not automatically mean the serializer is broken. The upgrade may have started running on the module path, or the new library may attempt to access private members instead of using public constructors/getters.

To inspect a modular JAR's descriptor:

```bash
jar --describe-module --file library.jar
```

To inspect module-level dependencies:

```bash
jdeps --print-module-deps --module-path mods application.jar
```

If release notes state "module name changed", review `requires`, `opens ... to ...`, command-line flags, and `jlink` custom runtime images. Changing a module name is a packaging and runtime graph issue, not merely fixing Java imports.

## 12. Transitive Dependencies and BOM Changes

A framework release can update dozens of libraries even though the application only changes a single version in the parent POM or platform.

**Hypothetical** example:

```text
Framework 3.x
  -> HTTP client A 4.x
  -> JSON serializer B 2.x
  -> Logging API C 1.x

Framework 4.x
  -> HTTP client A 5.x
  -> JSON serializer B 3.x
  -> Logging API C 2.x
```

Breaking changes may reside in:

1. Framework APIs.
2. Transitive APIs inadvertently called directly by the application.
3. New auto-configuration mechanisms.
4. Version mismatches caused by dependency overrides.
5. Different classpath or SPI/providers.
6. Libraries that still run yet change wire formats or exceptions.

Therefore, for framework/BOM upgrades, compare the **resolved dependency graph before and after**, not just a single entry in the build file.

### 12.1. What Happens When Pinning a Transitive Dependency?

An application might pin `serializer B` to an older version to avoid behavioral changes. Yet the new framework may have been compiled and tested against the new API, causing `NoSuchMethodError` at runtime. Conversely, forcing a newer version when an older framework does not support it can cause similar errors.

Only override versions when:

- You know the API requirements of both the framework and the dependency.
- You have checked the compatibility matrix and dependency constraints.
- You have integration tests covering calls between the framework and that library.
- There is a clear reason, such as a security fix when no compatible framework release exists.

Overriding a dependency is an engineering decision requiring evidence, not a trick to silence Maven/Gradle conflict warnings.

## 13. Security Notes Are Not Merely "Supplemental" Items

Release notes may contain entries like:

- Reject malformed input previously accepted.
- Disable insecure protocols/ciphers.
- Restrict polymorphic deserialization.
- Tighten path traversal validation.
- Change unsafe default.

These can be **intentional changes that must be kept**. An old test relying on accepting invalid data may fail after the update, yet that is not necessarily a regression.

When reading a security advisory, record:

1. Advisory/CVE ID or project identifier.
2. Affected version range.
3. Fixed version and backport branches if applicable.
4. Exploitation conditions relevant to how the application uses the library.
5. Vendor-recommended mitigation.
6. Impact of the fix on existing configuration, protocols, and legacy data.

Do not rely solely on the CVSS score: application risk also depends on attack surface reachability, data handled, and existing safeguards. At the same time, do not dismiss an advisory merely because the library is used indirectly.

**Principle:** If a fix causes an old input to be rejected, first check whether that input violates standards or security policies. Do not disable security checks or downgrade the library as a default choice.

## 14. License, Artifact Relocation, and Maintenance Status

Release notes and project info also reveal non-API changes:

- New license or different distribution terms.
- Repository or groupId change.
- Project discontinued, archived, or transferred to new maintainers.
- Namespace migration from `javax.*` to `jakarta.*`.
- Requiring a standalone artifact instead of a JDK-bundled module.
- Dropping support for a platform/native architecture.

These changes can determine **whether the upgrade is permitted** within the organization, even if all unit tests pass.

For example, moving from JAXB formerly bundled with older JDKs to a standalone dependency after JDK 11 is a packaging and dependency change. Moving modern Jakarta APIs to `jakarta.xml.bind.*` is a source/binary namespace change. The two are related yet are not the same change; read the proper migration guide for each step.

Do not use copyright/licensing information from an unofficial blog as legal authority. When needed, consult the license file of the exact tag/artifact and your organization's review process.

## 15. How to Read Release Notes Systematically

To avoid missing anything, read in four passes:

### Pass 1 — Scope and Support Conditions

Look for:

- Minimum JDK and supported versions.
- Required framework/driver/toolchain versions.
- Artifact name, module name, or package relocation.
- License, platform support, and known issues.

If a foundational condition is not met, pause migration design to pick an appropriate path before diving deep into APIs.

### Pass 2 — Breaking Changes and Deprecations

Read carefully:

- Removed/renamed classes, methods, fields, constructors.
- Changed signatures/generics/checked exceptions.
- Deprecated APIs transitioning to removed.
- Changed or removed configuration keys.
- Behavioral defaults, security policies, and data formats.

Do not confuse `deprecated` with `removed`. A deprecated API may still work in the current version while carrying warnings and a removal roadmap; a removed API can fail compilation or binary linkage immediately.

### Pass 3 — Dependency Changes and Interoperability

Inspect:

- Library versions upgraded indirectly.
- New APIs or modules requiring integration.
- ServiceLoader/SPI changes.
- JDK baseline and bytecode compatibility.
- Serialization schemas and wire protocols.
- Plugins, annotation processors, build plugins, or agent compatibility.

### Pass 4 — Bug Fixes and Known Regressions

Read bug fixes that might alter previous outputs. If the application had a workaround for a now-fixed bug, check whether the workaround must be removed, because keeping a workaround can sometimes cause errors once the library fixes the root cause.

For known regressions, consider choosing a different patch release or adding targeted tests and a rollback plan.

## 16. Turning Release Notes into an Impact Matrix

Do not copy hundreds of changelog lines verbatim into a ticket. It is better to build a concise table mapping directly to code and clear decisions.

**Hypothetical** example when upgrading `com.example:billing-client`:

| Release note | Category | Used by application? | Impact / handling | Completion evidence |
|---|---|---|---|---|
| Removed `charge(String,long)` | Source + binary | Yes, billing adapter module. | Migrate to `submitPayment(PaymentRequest)`. | Compile + payment integration test. |
| Retry disabled by default | Behavioral/config | Yes, outbound requests. | Configure per idempotency policy. | Retry tests and metrics. |
| Java 17 minimum | Runtime | Yes, one worker still runs Java 11. | Upgrade worker first or pick another library line. | Runtime matrix on Java 17+. |
| New JSON field `transactionType` | Wire contract | Yes, external consumers. | Add tolerant reader before producer emits field. | Two-way contract tests. |
| Fix for unsafe redirect | Security | Possibly. | Keep security behavior, update old test. | Security/integration test. |
| New tracing hooks | Feature | Not yet used. | No code changes required. | Record as not applicable. |

Useful columns:

- Change ID, version introduced.
- Link to release note, API diff, or issue.
- Compatibility category.
- Affected code/config/data locations.
- Risk level and owner.
- Decision: fix, defer, conditionally accept, or not applicable.
- Tests/verification and status.

An item marked "not applicable" should still document its reason: for instance, the application does not use that module and the dependency does not appear on the runtime classpath.

## 17. How to Check Whether the Application Uses a Breaking API

Release notes describe the library, yet the application codebase may use only a small subset.

Several techniques:

### 17.1. Direct Search in Source

Search for methods, packages, annotations, or properties named in the release note. For example, if a note states `LegacyParser` is removed, search for:

```text
LegacyParser
legacy-parser.enabled
parseLegacy
```

Watch out for reflection, `Class.forName(...)`, configuration strings, and code generation. Not every dependency surfaces via `import`.

### 17.2. Recompile Against the Target Version

Compilation can detect removed APIs, changed generic constraints, or incompatible annotation processors. However, successful compilation **does not prove** behavioral/runtime/data compatibility.

### 17.3. Compare Public APIs

Use `japicmp` or `Revapi` to inspect changed public/protected declarations, especially when the application cannot read every individual release note of a large JAR.

### 17.4. Runtime Linkage Analysis

Run integration tests and monitor for linkage errors in code paths executed only while the application is running. Plugins, drivers, and service providers may be loaded lazily, so startup tests alone are insufficient.

### 17.5. Compare Serialized Output

If release notes touch JSON/XML/protocols, use golden fixtures from the old version and run round-trip tests with the new version. A format change may never appear in an API diff.

## 18. Creating a Small-Step Upgrade Plan

A sound migration roadmap:

```text
Inventory current dependencies
            |
            v
Identify target versions + support constraints
            |
            v
Read notes for every release between old and new
            |
            v
Build change-impact matrix
            |
            v
Upgrade dependency in controlled branch
            |
            v
Compile + API + integration + contract tests
            |
            v
Canary/rollout + observe + rollback readiness
```

### Step 1 — Lock Down the Baseline

Save current artifacts, dependency graphs, runtime, compiler, configurations, and test results. Avoid upgrading too many library groups simultaneously if doing so destroys the ability to isolate root causes.

### Step 2 — Choose a Valid Target

Cross-check the target release against your JDK baseline and framework version. If you must support Java 11 yet the new library requires Java 17, you must either raise the baseline or choose another library branch; this cannot be solved merely by forcing compiler flags.

### Step 3 — Read Release Notes Across Each Leg

Find the migration guide for each major release, then read the minor/patch releases within the range. Record upcoming deprecations slated for removal as well.

### Step 4 — Estimate Impact and Assign Owners

Assign each change to a code owner, data owner, or security owner. If protocols change across multiple services, coordinate deployment order.

### Step 5 — Make Small Changes and Run Tests

Update the dependency on a dedicated branch, update code/config per the matrix, and run appropriate compile/linkage tests and integration/contract tests.

### Step 6 — Observe Before/After

Monitor error rates, latency, retry rates, serialization failures, resource usage, logging, and rare paths. Do not look only at a green deployment status.

### Step 7 — Remove Workarounds and Document Lessons

If the new library fixes an old bug, remove the workaround after verification. Save evidence in an upgrade record so future upgrades do not have to start research from scratch.

## 19. When to Upgrade Individually vs. Together?

### 19.1. Upgrading Dependency by Dependency

Appropriate when libraries are relatively independent, such as a parser or utility not tightly managed by a framework. The advantage is easier regression isolation and independent rollback.

However, check transitive dependencies and shared APIs to prevent version mismatches.

### 19.2. Upgrading via a BOM/Framework Release Train

Appropriate when a framework publishes a jointly tested set of versions. For example, a framework with a parent POM or Gradle platform managing multiple related dependencies.

The advantage is reducing the risk of unsupported combinations. On the other hand, many libraries can change at once; therefore, you still need to read the framework's overall migration guide plus the release notes of components critical to the application.

### 19.3. Splitting Large Upgrades into Stages

When jumping from version 1.x to 4.x, consider:

```text
1.x -> 2.x -> 3.x -> 4.x
```

You do not necessarily need to release to production at every stage. However, stepping through stages on an experimental branch helps isolate breaking APIs and pinpoint when changes were introduced, especially when migration guides only cover adjacent versions.

## 20. Data Compatibility Strategies and Multi-Service Rollout

Release notes for a serializer, ORM, messaging library, or HTTP framework can affect data exchanged across multiple service versions.

Suppose service A's new version emits a message with an added field:

```json
{
  "eventId": "evt-42",
  "status": "READY",
  "sourceSystem": "gateway"
}
```

Old consumers may fail if their reader rejects unknown fields. In that case, do not upgrade producers before consumers support the new schema.

A common strategy is **expand → migrate → contract**:

1. **Expand:** consumers accept both old and new formats.
2. **Migrate:** producers transition gradually while monitoring remaining old messages.
3. **Contract:** once no old consumers/data remain, remove temporary compatibility logic.

For persisted data (databases, caches, queues, object storage), determine rollback feasibility. Old code versions may not be able to read data written by the new serializer version. Rolling back a dependency does not automatically roll back stored data.

## 21. What Should Be Tested After Reading Breaking Changes?

You do not need to run every test at every step, yet you need a risk-based coverage strategy.

| Change type | Priority tests |
|---|---|
| API/source | Compilation, unit tests at call sites, API/binary compatibility tests if publishing a library. |
| Binary/transitive | Integration tests on runtime artifacts, classpath/module path, plugin loading. |
| Configuration/default | Tests with new config, missing config, legacy config, startup failure. |
| Serialization/protocol | Golden fixtures, backward/forward compatibility, schema validation. |
| Security | Negative tests with invalid input, access controls, TLS/certificates. |
| Performance | Baseline throughput, P95/P99 latency, CPU/memory, resource leaks. |
| JDK baseline | Tests on minimum supported JDK and target JDK. |
| Operational lifecycle | Startup/shutdown, graceful drain, retries, scheduled jobs, and rollback. |

### 21.1. A Simple Contract Test Example

For example, verifying an upgraded library still parses data per contract:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class PaymentContractTest {
    @Test
    void minorUnitsArePreserved() {
        PaymentRequest request =
                new PaymentRequest("A-100", 5000L);

        assertEquals(5000L, request.amountMinorUnits());
    }
}
```

`PaymentRequest` here is a hypothetical application DTO. Real tests must invoke the upgraded adapter/serializer or API to verify the affected path, rather than merely instantiating an object and asserting its getter as in this structural example.

### 21.2. JDK × Dependency Version Matrix

When a product supports multiple JDKs:

| Dependency | JDK 11 | JDK 17 | JDK 21 |
|---|---|---|---|
| Library 1.x | Per project support matrix | Per support matrix | Per support matrix |
| Library 2.x | May be unsupported | Per support matrix | Per support matrix |

Do not fill in "yes" merely because a trial run started. Verify vendor support policies, class file versions, and test on the lowest runtime committed by the product.

### 21.3. Testing Negative Cases

Pay special attention to cases rejected after security fixes, such as JSON containing disallowed type IDs, XML containing external entities, or TLS using disabled algorithms. This may be the **correct behavior** of the new library; tests must assert the expected rejection rather than treating every exception as a regression.

## 22. Distinguishing Upgrade-Induced Bugs from Pre-existing Application Bugs

An incident appearing after swapping a dependency does not necessarily mean the library's new code is faulty. It may expose an implicit assumption:

- The application used an internal class instead of a supported API.
- The application relied on an unguaranteed iteration order.
- Legacy security configuration skipped necessary validation.
- A consumer assumed a JSON field was always present even though the schema marked it optional.
- Multiple libraries shared the same dependency yet required different versions.

Triage workflow:

1. Reproduce the failure on a pinned artifact and fixed environment.
2. Cross-check release notes and API contracts.
3. Compare the before/after dependency graphs.
4. Write a minimal reproducer if possible.
5. Check the library's issue tracker and known regressions.
6. Conclude with an explicit confidence level: intentional change, application relying on unsupported behavior, integration mismatch, or library bug.

Do not label every error an "intentional breaking change" merely because a version bump occurred. If the new library violates a still-valid API contract, it may be a genuine regression worth reporting to maintainers.

## 23. Choosing the Target Version: Latest Is Not Always Best

Upgrading to the latest version can solve many issues, yet the decision must weigh:

- Minimum JDK and product runtime baseline.
- Supported framework/BOM versions.
- Security fixes and support lifecycle.
- Required major migrations.
- Known issues/known regressions in the target.
- API stability and business requirements.
- Licensing and distribution terms.
- Rollback feasibility and testing budget.

If the latest version requires Java 21 while the system still has Java 17 production nodes, you may need to upgrade the JDK first or select a library branch still supported on Java 17. Do not arbitrarily keep an end-of-life old version; evaluate the risk and plan the next upgrade step.

## 24. A Sample Upgrade Record That Can Live Alongside the Project

A concise, verifiable record is better than scattered notes:

```yaml
changeId: DEP-MIG-023
component: "billing-client"
coordinates: "com.example:billing-client"
fromVersion: "1.8.7"
toVersion: "2.1.3"
sourceOfTruth:
  - "Release notes v2.0"
  - "Migration guide 1.x -> 2.x"
  - "Release notes v2.1.3"
runtime:
  minimumJdkRequired: 17
  applicationMinimumJdk: 17
changes:
  - id: BC-01
    category: source
    summary: "Renamed charge API"
    affectedCode: "billing adapter"
    action: "Replace with submitPayment"
    proof: "Compile + integration tests"
  - id: BC-02
    category: behavior
    summary: "Changed retry defaults"
    affectedCode: "outbound payment requests"
    action: "Define idempotency-aware retry policy"
    proof: "Retry contract tests"
securityNotes:
  - "Review redirect validation change"
rollout:
  strategy: "Canary with rollback"
  metrics: "Request failures, retries, latency"
owner: "Billing team"
status: "In verification"
```

All coordinates, versions, and changes in this template are **hypothetical data only** to illustrate record keeping; they should not be treated as actual release notes of any real artifact.

Each change in a real record links to specific documentation or issues. Also record paths to code/tests so pull request reviewers can verify decisions instead of seeing only an "upgrade complete" claim.

## 25. Common Mistakes

**Reading only the title of the latest release.** This can miss breaking changes across multiple intermediate releases.

**Assuming patches/minors are always strictly compatible.** A security fix or dependency update can still affect behavior.

**Reading the declared version instead of the resolved version.** BOMs and transitive dependencies can select a different artifact.

**Focusing only on compile errors.** Binary linkage, serialization, and runtime defaults can change without compiler warnings.

**Ignoring the minimum JDK.** A new library may ship class files that cannot run on the lowest supported runtime.

**Pinning a transitive version outside the compatibility matrix.** The framework may call methods present only in a newer version.

**Skipping known issues and security notes.** An upgrade can fail due to a known regression or because old unsafe behavior is blocked.

**Equating deprecated with removed.** Deprecated is a warning/roadmap; removed is an immediate potential breaking change.

**Marking items not affected without checking actual usage.** Reflection, SPI, configuration, and runtime plugins can invoke APIs without an explicit `import` in source.

**Prioritizing fixes in release note order.** Changelog order is not the risk order in your application.

**Rolling back code without considering data.** Payloads/schemas written by the new version may be unreadable by the old version.

**Testing only application startup.** Failure paths such as scheduled jobs, retries, plugin loading, or legacy data may surface only later.

## 26. Checklist Before Approving a Dependency Upgrade

- [ ] Confirmed artifact coordinates and actual resolved version.
- [ ] Locked source version, target version, and JDK baseline.
- [ ] Read migration guides for every major step in the upgrade range.
- [ ] Read release notes/CHANGELOGs of significant intermediate releases.
- [ ] Checked compatibility matrix, deprecations/removals, and known issues.
- [ ] Compared dependency graphs and BOMs before and after.
- [ ] Classified source, binary, behavioral, config, data, runtime, and security changes.
- [ ] Identified APIs/configurations actually used by the application.
- [ ] Reviewed minimum JDK and JPMS/reflection/SPI impacts.
- [ ] Verified serializer, schema, database, and message compatibility where relevant.
- [ ] Reviewed security advisories and input validation changes.
- [ ] Checked license, artifact relocation, and maintenance status.
- [ ] Created an impact matrix with owners, actions, and verification evidence.
- [ ] Executed compile, integration, contract, and runtime matrix tests commensurate with risk.
- [ ] Determined rollout order and code/data rollback capability.
- [ ] Documented temporary workarounds and removal criteria.
- [ ] Saved release note links, tags/commits, and decision records for future upgrades.

## References

- [Semantic Versioning](https://semver.org/): MAJOR.MINOR.PATCH rules and the limits of inferring compatibility from version numbers.
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): viewing Maven's actual dependency graph.
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependencies, mediation, and dependency management.
- [Gradle — Viewing and debugging dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies` and `dependencyInsight`.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): locking resolved versions.
- [japicmp](https://github.com/siom79/japicmp): tool for comparing public APIs/binaries between JARs.
- [Revapi](https://revapi.org/): checking API changes and compatibility rules.
- [OpenJDK jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): analyzing class/package/module dependencies.
- [JLS — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html): Java binary compatibility rules.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): example packaging change requiring applications to add dependencies.
- [GitHub — About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases): release/tag concepts when locating project documentation.
- [OSV Database](https://osv.dev/): vulnerability reference by package and version; cross-check with official advisories.

## Conclusion

Reading release notes properly is a **compatibility analysis** activity, not merely browsing a feature list. First identify the exact artifacts and versions actually used by the build and runtime, then read official documentation across every upgrade leg, classifying changes across source, binary, behavior, config, data, JDK, and security. Each breaking change must be linked to its usage site in the application, a remediation plan, and tests proving the outcome. An impact matrix, before/after dependency graphs, golden fixtures, and a rollout/rollback plan turn release information into a clear, verifiable, and long-term maintainable migration decision.
