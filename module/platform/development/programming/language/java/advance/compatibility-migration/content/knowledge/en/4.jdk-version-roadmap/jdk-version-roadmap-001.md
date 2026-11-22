# Reading JDK Feature, Interim, Update, and Patch Versions

When upgrading a Java application, simply saying the server runs "Java 21" is often not enough. Two environments both using JDK 21 can differ in security updates, bug fixes, vendors, and build numbers. Those differences can affect bug reproduction, vulnerability checks, CI/CD environment standardization, and upgrade timing decisions.

Since JDK 10, JDK version numbering uses four numeric components according to the JEP 322 convention:

```text
FEATURE.INTERIM.UPDATE.PATCH
```

Each component describes a different type of release milestone. Reading these components accurately helps distinguish a feature release, an update release, and a patch release, while avoiding confusing a build number or an LTS label with the main version numbers.

## 1. Why Do We Need to Read the Full JDK Version?

Suppose two machines both show JDK 21. One runs `21.0.1` and the other runs `21.0.2`. Both belong to the same feature release 21, but the second machine has received a newer update. If a bug was fixed in that update, program execution results may differ.

When investigating an incident or preparing a migration, you need to know at least:

- The feature release the application is running on, e.g., 17, 21, or 25.
- The interim, update, and patch components, if present.
- The build number of the specific JDK build.
- The JDK vendor and distribution.
- The actual runtime version of the process, not just the version installed on the machine.

Complete version information helps the development team determine whether environments share the same update level, cross-reference security advisories, and reproduce bugs on the exact runtime build.

## 2. JDK Version Convention Since JDK 10

JEP 322 standardizes version strings into the following components:

| Component | Meaning | How It Changes |
|---|---|---|
| `FEATURE` | The JDK feature release number. This is the number commonly referenced when speaking of JDK 17, JDK 21, or JDK 25. | Increments when a new feature release is shipped. |
| `INTERIM` | The interim release number within the same feature release. | Increments when an interim release occurs under the release convention. For typical modern feature releases, this component is usually `0`. |
| `UPDATE` | The update release number within the corresponding feature/interim release. | Increments when an update release is shipped, typically containing bug fixes and security updates. |
| `PATCH` | The patch release number issued to address a specific problem requiring a dedicated fix. | Increments when a patch release occurs; usually `0` in standard releases. |

A full version string has the form:

```text
21.0.2.1
│  │ │ └── PATCH
│  │ └──── UPDATE
│  └────── INTERIM
└───────── FEATURE
```

In this example, `21` is the feature release, `0` is interim, `2` is update, and `1` is patch. Many real-world version strings omit trailing `0` components. Therefore, `21`, `21.0`, `21.0.2`, and `21.0.2.0` can represent the same component values under version normalization rules.

The key point is that the four components do not have the same meaning. For example, `21.0.2` means feature 21, interim 0, update 2, patch 0. The `2` shown at the end of the string is not the patch component; it is the update component because the trailing patch component is 0 and omitted.

## 3. Feature Release

`FEATURE` identifies the major JDK feature generation. For example:

- `17` is feature release 17.
- `21` is feature release 21.
- `25` is feature release 25.

Since the six-month release cadence was adopted, new feature releases typically appear around March and September. A feature release can add Java language features, APIs, tools, JVM capabilities, change defaults, or remove previously deprecated components according to schedule.

Consequently, upgrading from JDK 17 to JDK 21 crosses feature releases. This carries a larger impact scope than upgrading from `21.0.1` to `21.0.2`. The development team needs to read release notes, review relevant JEPs, run test suites, and verify dependent libraries before deploying a new feature release to production.

### Feature Releases and LTS

LTS stands for *Long-Term Support*. This is a support policy label from a JDK vendor or distribution. LTS is not one of the four numeric components in `FEATURE.INTERIM.UPDATE.PATCH`.

For example, when speaking of "JDK 21 LTS", the number `21` is still the feature component. The LTS label indicates the release belongs to the long-term supported group under the vendor's policy. Support duration, patch eligibility, and end-of-support schedules can vary across vendors; do not infer support durations solely from the numeric version string.

A feature release is not automatically LTS. When planning a migration, check the support policy of the exact JDK vendor your system uses.

## 4. Interim Release

`INTERIM` indicates the sequence number of an interim release within a feature release. This component is reserved for intermediate release milestones under the JDK versioning convention. For regular feature releases that Java teams typically install, the interim value is currently `0`.

Illustrative example of reading a string with a non-zero interim:

```text
23.1.0
│  │ └── UPDATE = 0
│  └──── INTERIM = 1
└─────── FEATURE = 23
```

This example illustrates component positions, not an assertion that a specific JDK build carries that version number. When encountering a real-world string with a non-zero interim, consult the vendor's release documentation to understand the scope and contents of that interim release.

Do not interpret `INTERIM = 0` as meaning the JDK has no updates. Update releases are represented by the `UPDATE` component. For example, `21.0.2` has interim `0` but update `2`, meaning two update milestones have been counted in that feature release's version sequence.

## 5. Update Release

`UPDATE` indicates the update release number. Update releases typically ship on a quarterly cycle and focus on bug fixes, security updates, stability improvements, and necessary adjustments. They are not new feature releases.

Examples:

| Version String | Feature | Interim | Update | Patch |
|---|---:|---:|---:|---:|
| `17.0.8` | 17 | 0 | 8 | 0 |
| `17.0.9` | 17 | 0 | 9 | 0 |
| `21.0.1` | 21 | 0 | 1 | 0 |
| `21.0.2` | 21 | 0 | 2 | 0 |

When moving from `21.0.1` to `21.0.2`, the feature release remains 21. The application does not transition to a new feature generation, yet the runtime has received a new update. An update may contain fixes for JVM bugs, the standard library, or security issues. Therefore, sharing the same feature release does not mean two machines behave identically.

For production environments, maintain a periodic update intake process: monitor vendor advisories, evaluate update contents, run regression tests, and roll out across environments. Do not defer security updates indefinitely just because the application still runs on the old version.

## 6. Patch Release

`PATCH` is the fourth component. It indicates a patch release issued to address a specific problem requiring a dedicated fix, typically a critical issue needing resolution outside the regular update cadence.

Illustrative example:

```text
21.0.2.1
│  │ │ └── PATCH = 1
│  │ └──── UPDATE = 2
│  └────── INTERIM = 0
└───────── FEATURE = 21
```

In this example, feature is still 21 and update is still 2; the patch component increased to 1. Comparing with `21.0.2`, we know this is a patch release based on the `21.0.2` update milestone.

The patch component is usually `0` and may be omitted in version strings. Not every distribution issues patch releases in the same way or uses identical display labels. Read vendor announcements rather than assuming every emergency fix necessarily appears as a fourth number.

## 7. Reading Additional Parts in the Version String

A JDK version string may contain additional information beyond the four numeric components. These parts help identify pre-release builds, build numbers, or distribution-specific metadata.

### 7.1. Build Number After `+`

Example:

```text
21.0.2+13
```

Here:

- `21.0.2` is the version number part.
- `+13` is the build number.

The build number identifies the specific build of the release. It is neither `PATCH` nor `UPDATE`. Thus, `21.0.2+13` has a patch component of `0`, not patch 13.

When reproducing an environment, record the build number as well. Two builds from different vendors may have different packaging, additional patches, or build metadata even when sharing the same feature, interim, and update components.

### 7.2. Pre-Release Label

An unreleased JDK build may carry an experimental label such as `ea` (early access). Illustrative example:

```text
25-ea+12
```

`25` is the feature component, `ea` is the pre-release label, and `12` is the build number. Early access builds serve for testing, compatibility evaluation, and feedback prior to general availability. Do not use EA builds for production by default.

### 7.3. Additional Metadata After `-`

Some distributions may append extra information after the build part, such as build-identifying details or vendor tags. Exact formatting varies by distribution. Such strings do not alter the meaning of the four numeric components.

Similarly, an LTS label is often displayed as support information or distribution metadata. Do not read it as a fifth numeric component of the JDK version.

## 8. Complete Version Parsing Example

Consider the string:

```text
21.0.2+13
```

We parse it as:

| Part | Value | Interpretation |
|---|---:|---|
| Feature | 21 | Belongs to JDK 21 feature release. |
| Interim | 0 | No non-zero interim component. |
| Update | 2 | Belongs to the 2nd update in this release series. |
| Patch | 0 | No non-zero patch component. |
| Build | 13 | Build number 13. |

Another string:

```text
17.0.10.1+1
```

is read as feature 17, interim 0, update 10, patch 1, build 1. The `10` is the update component; the `1` after it is the patch component; the `1` after the `+` sign is the build number. These three numbers carry three distinct meanings.

When reading a version string, separate the numeric portion first, then read pre-release, build, and metadata. Do not mechanically count numeric groups while ignoring the positions of dots and plus signs.

## 9. Reading JDK Versions via Command Line

### 9.1. Checking the Runtime

Run:

```bash
java -version
```

This command displays the version of the `java` executable currently resolved by the shell. An illustrative output might look like:

```text
openjdk version "21.0.2" 2024-01-16
OpenJDK Runtime Environment (build 21.0.2+13)
OpenJDK 64-Bit Server VM (build 21.0.2+13, mixed mode)
```

In this example, the version number is `21.0.2` and the build number is `13`. The runtime has feature 21, interim 0, update 2, and patch 0.

### 9.2. Checking the Compiler

Run:

```bash
javac -version
```

This command reports the version of the `javac` compiler the shell invokes. Never assume the compiler and runtime always come from the same installation directory. On machines with multiple JDKs, `java` and `javac` can resolve from different paths if `PATH` or `JAVA_HOME` is configured inconsistently.

### 9.3. Viewing Runtime Properties

More environment details can be viewed with:

```bash
java -XshowSettings:properties -version
```

Useful properties include:

| Property | Information |
|---|---|
| `java.version` | Java version string reported by the runtime. |
| `java.runtime.version` | More detailed runtime version string, potentially including build metadata. |
| `java.vendor` | Runtime vendor. |
| `java.home` | Installation directory of the running runtime. |
| `os.arch` | Operating system architecture detected by the JVM. |

Properties can vary across vendors and versions. When investigating production issues, save the actual output rather than writing only "Java 21".

### 9.4. Checking Paths on Windows

In PowerShell, inspect the resolved commands with:

```powershell
Get-Command java | Select-Object Source
Get-Command javac | Select-Object Source
$env:JAVA_HOME
```

On Linux or macOS, use:

```bash
which java
which javac
echo "$JAVA_HOME"
```

These commands identify which JDK the shell uses. In Maven, Gradle, or an IDE, toolchains or project configurations can select a different JDK from the terminal's default. When a local build behaves differently from CI, inspect the JDK used by the actual build process.

## 10. Reading Version Components Using the Java API

Since Java 9, you can retrieve the current runtime's version object via `Runtime.version()`. The methods `feature()`, `interim()`, `update()`, and `patch()` reflect the four components under the JEP 322 convention and have been in the API since Java 10.

```java
public class JdkVersionInfo {
    public static void main(String[] args) {
        Runtime.Version version = Runtime.version();

        System.out.println("Version: " + version);
        System.out.println("Feature: " + version.feature());
        System.out.println("Interim: " + version.interim());
        System.out.println("Update: " + version.update());
        System.out.println("Patch: " + version.patch());

        System.out.println("Pre-release: "
                + version.pre().orElse("none"));
        System.out.println("Build: "
                + version.build().map(String::valueOf).orElse("none"));
        System.out.println("Optional: "
                + version.optional().orElse("none"));
    }
}
```

For instance, if the program runs on runtime `21.0.2+13`, the printed numeric components are feature `21`, interim `0`, update `2`, and patch `0`. `build()` provides the build number if the version string includes it. The `pre()` and `optional()` methods return `Optional`, as an official release may omit pre-release labels or supplemental metadata.

If you need to parse a configuration-supplied version string, use `Runtime.Version.parse`:

```java
public class ParseJdkVersion {
    public static void main(String[] args) {
        Runtime.Version version = Runtime.Version.parse("21.0.2+13");

        System.out.println("Feature = " + version.feature());
        System.out.println("Interim = " + version.interim());
        System.out.println("Update = " + version.update());
        System.out.println("Patch = " + version.patch());
        System.out.println("Build = "
                + version.build().map(String::valueOf).orElse("unknown"));
    }
}
```

`Runtime.Version.parse` validates the version string syntax and creates a version object. If the string is invalid, the method throws `IllegalArgumentException`. When accepting version strings from configuration files or external systems, handle parsing errors instead of assuming valid input.

Do not manually split strings using `split("\\.")` and assume positional indices suffice. That easily misses build numbers, pre-release labels, metadata, or omitted trailing components. The `Runtime.Version` API understands the version structure and exposes components with appropriate types.

## 11. Comparing Two Versions

Comparing version strings lexicographically can yield incorrect results. For example, `"21.0.10"` can compare as less than `"21.0.9"` character-by-character because `'1'` in `"10"` comes before `'9'`.

Parse into `Runtime.Version` and use `compareTo`:

```java
public class CompareJdkVersions {
    public static void main(String[] args) {
        Runtime.Version installed = Runtime.Version.parse("21.0.10+7");
        Runtime.Version minimum = Runtime.Version.parse("21.0.9+5");

        if (installed.compareTo(minimum) >= 0) {
            System.out.println("Runtime meets the minimum version");
        } else {
            System.out.println("Runtime is older than the minimum version");
        }
    }
}
```

`compareTo` compares by version structure rather than character order. For applications enforcing a minimum version, define the comparison policy clearly: whether only the same feature release is required or a specific update/patch level must be met. If the policy also depends on vendor or build, check those fields separately because the four numeric components do not identify the full distribution.

## 12. Distinguishing the JDK Scheme from Semantic Versioning

Java libraries and many other software packages typically use Semantic Versioning (SemVer) in the form `MAJOR.MINOR.PATCH`. Since Java 10, the JDK uses `FEATURE.INTERIM.UPDATE.PATCH`. Both conventions look superficially similar in component count but differ in meaning.

| String | Interpretation |
|---|---|
| JDK `21.0.2` | Feature 21, interim 0, update 2, patch 0. |
| Library `2.1.0` per SemVer | Major 2, minor 1, patch 0 per the library's SemVer contract. |

Do not mechanically apply SemVer rules to the JDK. In SemVer, the second component is minor and the third is patch. In a JDK version string, the second component is interim and the third is update.

This also means `21.0.2` is not "JDK major 21, minor 0, patch 2" in SemVer terms. It is JDK feature 21, interim 0, update 2.

## 13. JDK Versions Prior to JDK 10

Older Java versions used different conventions, so JEP 322's four-component breakdown cannot be applied to all historical strings.

### Java 8 and Earlier

Java 8 typically appears in the form:

```text
1.8.0_402
```

In this string, `1.8` identifies Java 8 under the old convention; `_402` is the update number formatted under the legacy convention. Do not read `1.8.0_402` as `FEATURE.INTERIM.UPDATE.PATCH`.

### Java 9

JDK 9 transitioned to a new version scheme under JEP 223, with strings such as `9.0.4`. Starting in JDK 10, JEP 322 refined the scheme and explicitly defined the feature, interim, update, and patch components.

When writing scripts managing multiple JDK generations, determine the scheme based on version or use a library/parser supporting historical forms. A script that merely splits on dots can mishandle Java 8, Java 9, or strings carrying build metadata.

## 14. Relation to Migration and Application Compatibility

Reading the JDK version is the first step of migration. Version numbers do not by themselves prove an application is compatible with a new JDK. Several layers of information must be distinguished:

| Information | Which Question Does It Answer? | How to Check |
|---|---|---|
| Feature release | Which JDK generation is the application running on? | `java -version`, `Runtime.version().feature()` |
| Update/patch | Which update level within that feature release has the runtime received? | Version string, `update()`, and `patch()` |
| Build/vendor | Who provides this specific runtime and how was it built? | `java -version` output, system properties, distribution metadata |
| Compile target | Which Java release was the source code compiled to target? | Compiler configuration and `--release` option |
| Actual runtime | Which JVM is the application process actually using? | Startup logs, `Runtime.version()`, service/container config |

For example, a project can be compiled with JDK 21 while producing bytecode compatible with Java 17 via `javac --release 17`. That does not mean the application runs on JDK 17. Compile target and runtime version are two distinct pieces of information.

When upgrading a feature release:

1. Identify source and target JDKs, including vendor, build, and update level.
2. Read release notes and changes that may affect APIs, JVM, GC, modules, TLS, charset, or tools.
3. Verify whether libraries, build plugins, agents, and frameworks support the target feature release.
4. Compile with the chosen target configuration and run tests on the target runtime.
5. Deploy in staging and monitor logs, metrics, performance, and compatibility errors.

When upgrading an update or patch within the same feature release, regression testing is still required. An update may fix bugs or change behavior in scenarios that previously relied on the old bug. Patch releases should also be evaluated against fix contents and vendor advisories.

## 15. Recording Versions in Logs and Deployment Records

To ensure environment reproducibility, applications or deployment pipelines should log the runtime version at startup. Example:

```java
public final class RuntimeInfo {
    private RuntimeInfo() {
    }

    public static void logVersion() {
        Runtime.Version version = Runtime.version();

        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.runtime.version="
                + System.getProperty("java.runtime.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("java.home=" + System.getProperty("java.home"));
        System.out.println("jdk.feature=" + version.feature());
        System.out.println("jdk.interim=" + version.interim());
        System.out.println("jdk.update=" + version.update());
        System.out.println("jdk.patch=" + version.patch());
    }
}
```

In real systems, use the application logger instead of `System.out.println`. This information is helpful when comparing two pods, two servers, or two deployments. There is no need to repeat it on every request; logging once at startup is typically enough to identify the process runtime.

A deployment record can store fields such as:

- JDK distribution and vendor.
- Feature, interim, update, and patch.
- Build number and architecture.
- `JAVA_HOME` value or process runtime path.
- Compile target and toolchain version used during build.
- Update date and image/container digest if the application runs in a container.

When comparing environments, inspect the actual runtime inside the container as well. The JDK on the host machine may differ from the JDK packaged in the image.

## 16. Common Misconceptions

**Treating the last visible number as patch.** In `21.0.2`, the `2` is update; the patch component is `0` and omitted.

**Treating the number after `+` as patch.** In `21.0.2+13`, `13` is the build number.

**Treating LTS as a version component.** LTS is a support label/policy, not part of the four numeric components.

**Assuming the same feature release means the same runtime.** `21.0.1` and `21.0.2` share feature 21 yet differ in update level.

**Using SemVer rules to read JDK versions.** The JDK uses feature/interim/update/patch, not SemVer's major/minor/patch.

**Checking only `java -version` in the terminal.** IDEs, Maven, Gradle, service managers, and containers can use different JDKs. Inspect the actual runtime of the process under investigation.

**Assuming an update release is a new feature release.** Updates focus on bug fixes and security; the feature component stays the same.

**Applying the JDK 10+ scheme to Java 8.** Java 8 uses historical formats such as `1.8.0_402`; a separate parser or rule is required for legacy strings.

## 17. Checklist When Reading and Recording JDK Versions

- [ ] Retrieved the version string from the exact runtime running the application.
- [ ] Identified the feature component.
- [ ] Read interim, update, and patch in their proper positions.
- [ ] Distinguished the build number after `+` from the patch component.
- [ ] Identified pre-release or metadata if present.
- [ ] Recorded vendor, distribution, and build when environment reproduction is needed.
- [ ] Checked compiler/toolchain separately from runtime.
- [ ] Distinguished compile target from actual JVM version.
- [ ] Identified historical scheme if handling JDK 8 or earlier.
- [ ] Cross-checked release notes and support policies prior to upgrading.

## Conclusion

Since version 10, the JDK uses the `FEATURE.INTERIM.UPDATE.PATCH` convention. Feature identifies the JDK generation; interim denotes an intermediate release milestone; update denotes a periodic update release; patch denotes a dedicated fix release. Build numbers, pre-release labels, metadata, and LTS provide additional context without replacing these numeric components. During migration, read the version string from the actual runtime, record vendor/build, distinguish compile target from runtime, and test according to the change scope of each release type.
