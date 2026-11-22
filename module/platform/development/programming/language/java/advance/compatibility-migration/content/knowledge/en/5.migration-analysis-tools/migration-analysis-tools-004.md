# Scanning Deprecated and forRemoval APIs with jdeprscan

## 1. The Role of jdeprscan in Java Migration

When upgrading the JDK, a common risk is that source code or libraries still call Java APIs marked deprecated. A deprecated API may still work in the current version, yet platform developers have announced that the API is no longer recommended for use. In some cases, the API is also marked for removal in a future Java version.

jdeprscan is a command-line tool bundled with the JDK, used to scan Java bytecode and find references to JDK APIs deprecated in the selected platform version. The tool helps teams identify items needing review before upgrading the runtime, replacing libraries, or moving to a new target Java version.

During migration, jdeprscan is especially useful for:

- Finding classes and methods in the application's artifacts that reference deprecated JDK APIs.
- Separating APIs marked for removal to prioritize handling.
- Locating reference sites in bytecode, tracing back to the relevant source code or dependency.
- Comparing scan results across JDK versions and tracking the reduction of risky references.
- Producing technical evidence for an API replacement plan before the API is removed.

jdeprscan is a static analysis step on class files. It does not replace the compiler, unit tests, integration tests, runtime testing, or reading JDK/framework migration guides. Results must be combined with those evidence sources to decide on fixes.

## 2. What Do Deprecated and forRemoval Mean?

Java provides the java.lang.Deprecated annotation to mark APIs no longer recommended for use. The annotation can apply to types, methods, constructors, fields, or supported elements per language rules.

Starting in Java 9, the annotation gained two important attributes:

- since: the version in which the API was marked deprecated.
- forRemoval: indicates the API is deprecated and scheduled for removal in a future Java version.

Example:

~~~java
@Deprecated(since = "9")
public void legacyOperation() {
    // The old API still exists, yet is no longer recommended.
}

@Deprecated(since = "17", forRemoval = true)
public void operationScheduledForRemoval() {
    // The API should be prioritized for replacement before it is removed.
}
~~~

These two states should not be treated as equivalent:

| Status | Meaning | Handling in Migration |
|---|---|---|
| Deprecated | The API is no longer recommended; no announcement yet that it will be removed. | Identify replacement APIs, assess cost, and plan an appropriate transition. |
| Deprecated for removal | The API is explicitly marked as planned for removal in the future. | High priority; find replacements and check the target JDK version before upgrading. |
| Removed | The API no longer exists in the target platform. | References can cause compile, linkage, or runtime errors; must move to a still-supported API. |

forRemoval is a signal of intent to remove, not a guarantee that the API will vanish in the very next Java release. The team must check the documentation of the specific JDK version for timing, replacement APIs, and migration guidance.

An API may stay deprecated for many versions without yet being removed. Conversely, once an API has been removed from the target JDK, scanning against a platform version that no longer has that API can yield different results from scanning against a version where the API still existed. Therefore, choose the release matching the question under test and do not interpret every unresolvable message as a “deprecated” finding.

## 3. What jdeprscan Scans and Does Not Scan

jdeprscan reads class files in a directory, a JAR, or a specified class, and compares bytecode references against the deprecated JDK API list of the chosen release. The tool can report references to deprecated APIs in compiled code without recompiling source code.

### 3.1. Detection Scope

Typically, the tool can find direct references in bytecode such as:

- Calls to deprecated methods.
- References to deprecated constructors or fields.
- References to platform types or members marked deprecated.
- References appearing in class files inside the scanned artifact, provided the tool can analyze and resolve them.

Output usually indicates the class containing the reference and the deprecated API used. Depending on the case, you may need to inspect the corresponding source code or dependency tree to identify the component owning the call.

### 3.2. What the Tool Cannot Prove

jdeprscan is not an analyzer of every application behavior. It has limitations that must be clearly understood:

- The tool focuses on JDK APIs. It is not a general tool for finding all deprecated APIs declared by third-party libraries.
- The tool scans class files; it does not fully analyze uncompiled source code.
- It does not guarantee detecting calls built dynamically via reflection, class/method names stored as strings, runtime configs, or code generated after scan time.
- It does not prove the execution path of a reference. A class may contain a deprecated call yet that code branch never executes in production.
- It does not replace binary compatibility testing, functional testing, security testing, or performance measurement.
- If dependencies needed to resolve types are missing, output may contain incomplete information or resolution-related warnings. Supply an appropriate classpath and distinguish resolution errors from actual deprecated findings.

An important point is input scope. When scanning an application JAR, the tool inspects class files in that JAR. Dependencies on the classpath help resolve references; adding a dependency to the classpath does not mean every class in that dependency is automatically scanned too. To inspect a third-party library, scan that library's artifact as a separate input.

### 3.3. Distinguishing from Other Tools

JDK analysis tools have different scopes:

| Tool | Primary Purpose | Question Answered |
|---|---|---|
| jdeprscan | Scans class files to find references to deprecated JDK APIs. | Does the artifact use deprecated or forRemoval JDK APIs? |
| javac with deprecation warnings | Emits warnings while compiling source code. | Does the source code being compiled call deprecated APIs? |
| jdeps --jdk-internals | Analyzes dependencies on JDK internal APIs. | Does the artifact depend on JDK internal APIs? |
| Unit/integration tests | Executes selected application flows. | Does the application's behavior remain correct on the target environment? |

An artifact might have zero deprecated findings yet still depend on JDK internal APIs. Conversely, a deprecated reference is not necessarily a reference to an internal API. Thus, jdeprscan and jdeps address two different classes of risk.

## 4. Preparing the Scan Environment

jdeprscan is provided with the JDK. Use a JDK containing this tool and check its version before scanning:

~~~bash
jdeprscan --version
~~~

On Windows PowerShell:

~~~powershell
Get-Command jdeprscan -All | Select-Object Source
jdeprscan --version
~~~

If the command is not found, check the JDK's bin directory and PATH. You can invoke the executable directly in JAVA_HOME:

~~~powershell
& "$env:JAVA_HOME\bin\jdeprscan.exe" --version
~~~

On Linux/macOS:

~~~bash
"$JAVA_HOME/bin/jdeprscan" --version
~~~

Record the full version and vendor of the JDK providing the tool. The jdeprscan version determines which releases the tool can compare against. If scanning against a newer release unsupported by the current tool, use jdeprscan from a newer JDK that supports that release.

Before running, prepare:

1. A successfully built artifact, such as an application JAR or class-file directory.
2. The JDK release to compare against.
3. A classpath containing dependencies needed to resolve references.
4. A list of artifacts to scan, including the application and critical dependencies if scope requires.
5. Storage for logs along with tool version, scan timestamp, commit, or artifact version.

Do not scan only a source directory or a leftover old JAR in the workspace. Ensure input artifacts belong to the exact commit and build configuration being evaluated.

## 5. Key jdeprscan Options

Commonly used options include:

| Option | Purpose |
|---|---|
| --release RELEASE | Selects the Java release used as the deprecated-API reference baseline. |
| --for-removal | Focuses only on deprecated APIs marked forRemoval. |
| --class-path PATH | Supplies classpath for the tool to resolve related types and references. |
| --list | Lists deprecated APIs of the selected release instead of scanning a specific artifact. |
| --verbose | Displays more detailed information during scanning. |
| --version | Displays tool version. |
| --full-version | Displays full version information. |
| --help | Displays usage help for the running tool version. |

The supported release set and option details depend on the installed JDK version. When needing exact syntax, always check jdeprscan --help on the exact JDK used in the pipeline.

### 5.1. Selecting a release

--release determines the Java version whose deprecated API list serves as the baseline. Example:

~~~bash
jdeprscan --release 17 app.jar
~~~

The command above scans the artifact against Java 17's deprecated API list. When migrating to a newer version, choose a release matching the target to evaluate and what the installed jdeprscan supports.

You can scan the same artifact against multiple releases supported by the tool to observe how deprecation status changes over time. However, results for each release must be saved separately, since the API set and deprecation status can differ.

### 5.2. Scanning Only forRemoval APIs

To focus on high-priority APIs:

~~~bash
jdeprscan --release 17 --for-removal app.jar
~~~

The --for-removal option limits results to APIs marked deprecated for removal in the selected release. This is a useful way to build a prioritized remediation list in migration.

Zero forRemoval findings does not mean the artifact uses zero deprecated APIs. Run a regular scan pass as well if the goal is inventorying all deprecated APIs.

### 5.3. Listing Deprecated APIs of a Release

You can view the API list that jdeprscan recognizes in a specific release:

~~~bash
jdeprscan --list --release 17
~~~

To list only the group marked forRemoval:

~~~bash
jdeprscan --list --release 17 --for-removal
~~~

This list helps look up API names and prepare comparisons, yet is not an application scan result. It does not tell you which artifacts use those APIs.

## 6. Scanning JARs and Class-File Directories

### 6.1. Scanning an Application JAR

After building, run jdeprscan on the JAR to evaluate:

~~~bash
jdeprscan --release 21 build/libs/application.jar
~~~

Adjust the release and artifact path to match the real project. If the application produces multiple JARs, clearly distinguish deployment artifacts from shared libraries.

To find only forRemoval APIs:

~~~bash
jdeprscan --release 21 --for-removal build/libs/application.jar
~~~

Run both passes when a complete baseline is needed:

1. Scan all deprecated APIs for the overall picture.
2. Scan separately for forRemoval to create a prioritized remediation list.

### 6.2. Scanning a Class-File Directory

If the build emits class files into a directory:

~~~bash
jdeprscan --release 21 build/classes/java/main
~~~

For another module layout, replace the path with the directory containing compiled class files. Point to the exact output directory of the source set or module to scan; a root directory without class files will not provide useful evidence.

### 6.3. Providing the Classpath

A class file may reference types declared in another dependency. Providing the classpath helps jdeprscan resolve those references:

~~~bash
jdeprscan --release 21 --class-path "lib/*" build/libs/application.jar
~~~

If specifying multiple paths, use the OS classpath separator:

- Windows: semicolon (;).
- Linux and macOS: colon (:).

Example on Linux/macOS:

~~~bash
jdeprscan --release 21 --class-path "lib/a.jar:lib/b.jar" build/libs/application.jar
~~~

Example on Windows:

~~~powershell
jdeprscan --release 21 --class-path "lib\a.jar;lib\b.jar" build\libs\application.jar
~~~

The classpath helps the tool resolve references. It does not turn every JAR on the classpath into a scan target. To check deprecated APIs used inside third-party libraries, run jdeprscan directly on each library JAR.

### 6.4. Scanning Application Dependencies

For a broader picture, list the application's runtime or packaged dependencies, then scan critical artifacts individually. For each dependency, record:

- Artifact name and version.
- Source of the dependency and checksum if available.
- Usage scope: compile, runtime, test, or build-time.
- Release used for scanning.
- Deprecated and forRemoval findings.

Prioritize foundational libraries with heavy JDK interaction such as frameworks, ORMs, database drivers, HTTP clients, logging, serialization, security, bytecode manipulation, and integration libraries. An unscanned dependency must be explicitly noted; do not infer that the dependency is clean merely because the application's classpath was supplied.

## 7. Workflow for Processing Scan Results

jdeprscan output is input for investigation. Do not swap APIs immediately based solely on printed names; first determine which source code, dependency, and release the reference comes from.

### 7.1. Identifying the Class Owning the Reference

When the tool reports a class using a deprecated API:

1. Determine whether the class belongs to an application artifact or an external dependency.
2. If it belongs to the application, find the corresponding source in the module and inspect the call.
3. If it belongs to a dependency, identify the direct or transitive dependency owning the class.
4. Cross-check against the release where the API was marked deprecated or forRemoval.
5. Check JDK documentation for replacement APIs and migration conditions.

The class name in the report is usually the lookup starting point. If the class is auto-generated, find the generator, annotation processor, or code-generation library instead of editing generated output that will be overwritten on the next build.

### 7.2. Classifying Findings

Findings can be classified by source and severity:

| Group | Example | Handling Direction |
|---|---|---|
| Project-owned source, deprecated | A method in a module calls an old JDK API. | Find replacement API, update code, and add tests. |
| Project-owned source, forRemoval | A call to an API scheduled for removal. | Prioritize fixing before JDK upgrade; verify replacement on target release. |
| Direct dependency | A project-declared library contains a class calling a deprecated API. | Check for a library upgrade or replace the dependency. |
| Transitive dependency | Another library pulls in a component with a deprecated reference. | Use dependency insight/tree to find the origin and align compatible versions. |
| Generated code | A class generated from a schema, processor, or generator. | Upgrade/configure the generator and regenerate code; do not only edit temporary output. |
| Unknown source | Report lists a class yet lacks artifact or classpath details. | Add build evidence, classpath, and artifact list, then re-scan. |

### 7.3. Choosing a Replacement API

Not every deprecated API can be replaced by a method of the same name or a completely equivalent new class. When replacing, consider:

- Method signatures and input/output data types.
- Default values, exceptions, and error-handling rules.
- Behavior regarding timezone, locale, encoding, and data formatting.
- Thread safety, lifecycle, resource management, and performance.
- Compatibility with other JDK versions the project still supports.
- Impact on stored data, protocols, and public APIs.

For instance, replacing an old date/time API with java.time may change data types and timezone representation. In that case, beyond fixing compilation, verify serialization, database mapping, and HTTP contracts if those layers use the affected types.

If a deprecated API has no direct replacement, read the JDK migration documentation, evaluate how to redesign the usage, and record the technical decision. Do not merely suppress warnings or keep forRemoval references without a clear reason and plan.

## 8. Organizing Scans Across Multiple JDK Stages

In migration, a single scan pass usually cannot answer every question. Define the purpose of each pass clearly:

| Stage | Reference Release | Goal |
|---|---|---|
| Current baseline | Currently used release or supported artifact release | Record existing deprecated APIs in the artifact. |
| Priority review | Same baseline release with --for-removal | List APIs at risk of removal to address first. |
| Target evaluation | Target JDK release supported by the tool | Identify APIs deprecated in the target platform and findings to investigate. |
| After fixes | Same release and options as baseline | Compare before/after results under identical scan conditions. |

If an API has already been removed from the target release, scanning against that release does not always produce a clear deprecation report. Resolution issues may appear because the API is no longer in the platform. Cross-check against a release where the API still existed and was marked deprecated/forRemoval, and build and test directly on the target JDK to confirm removal.

When the tool does not support the target release, use jdeprscan from a newer JDK that supports that release. Do not run an old tool and conclude that zero findings means the artifact is compatible with future JDKs.

## 9. Integrating jdeprscan into CI

Adding a scan step to CI lets results be reproduced on the exact same artifact and stored alongside build evidence. A basic job can include:

1. Select a JDK providing jdeprscan and supporting the release to check.
2. Build the artifact from the active commit.
3. Identify the exact JAR or class-file directory.
4. Scan all deprecated APIs.
5. Scan forRemoval APIs separately.
6. Store logs, tool version, release, commit, and artifact identifier.
7. Evaluate results per project policy.

Example with shell in a pipeline:

~~~bash
jdeprscan --version
jdeprscan --release 21 build/libs/application.jar
jdeprscan --release 21 --for-removal build/libs/application.jar
~~~

If reports need to be saved:

~~~bash
jdeprscan --release 21 build/libs/application.jar \
  > build/reports/jdeprscan-all.txt 2>&1

jdeprscan --release 21 --for-removal build/libs/application.jar \
  > build/reports/jdeprscan-for-removal.txt 2>&1
~~~

With PowerShell:

~~~powershell
jdeprscan --version
jdeprscan --release 21 build\libs\application.jar *> build\reports\jdeprscan-all.txt
jdeprscan --release 21 --for-removal build\libs\application.jar *> build\reports\jdeprscan-for-removal.txt
~~~

The report directory must exist before writing. Check the tool's exit code and log output for the active version; do not assume every deprecated finding makes jdeprscan return a non-zero exit code. If the organization wants to fail the pipeline when forRemoval APIs exist, build a dedicated policy step based on verified results and distinguish findings from tool or resolution errors.

### 9.1. Tiered CI Policy

A practical policy can divide into tiers:

- **Newly appearing forRemoval:** require investigation and remediation before accepting migration, or require time-bounded exception approval.
- **Newly appearing regular deprecated:** emit a warning or require explanation depending on impact.
- **Pre-existing findings:** maintain a baseline so the count does not grow; remediate gradually per plan.
- **Scan failure or missing artifact:** treat as missing evidence, never interpret as “no deprecated APIs”.

If applying a baseline, store results by commit or artifact fingerprint, scanned release, jdeprscan version, and scan type. Only compare two results with equivalent conditions. When changing the tool JDK, reference release, or classpath, record the change to avoid flawed comparisons.

### 9.2. Scanning Multiple Modules

In a multi-module repository, each module can produce its own artifact and dependency graph. Identify which modules have Java code, which package JARs, and which are aggregator or platform modules. Scan each meaningful artifact rather than scanning only one representative JAR.

Keep results per module so findings can be traced back to the owning team. If multiple modules pull in the same dependency, you can scan that dependency once at the artifact level while still recording which modules use it. Do not merge all logs and lose origin information.

## 10. Interpreting Output and Avoiding Wrong Conclusions

When receiving output, distinguish four situations:

1. **Deprecated finding:** the tool found a reference to a deprecated JDK API within the scan scope.
2. **forRemoval finding:** a reference to an API marked scheduled for removal; needs priority investigation.
3. **Unresolved reference:** the tool lacks classpath entries or the API does not exist in the reference release; find the cause before concluding.
4. **No findings:** no matching references were found in the scanned class files under that release and input scope.

“No findings” is meaningful only within the scanned scope. If dependencies, generated code, plugins, or dynamically loaded classes were not scanned, the result does not prove the entire system uses zero deprecated APIs.

When a scan reports errors, do not discard the report or treat it as a clean result. Record the command, jdeprscan version, release, artifact, classpath, and error message. Then fix scan conditions or clearly mark what could not be analyzed.

## 11. Example Workflow for Handling a forRemoval Finding

Suppose jdeprscan reports a class in the application referencing a JDK API marked forRemoval:

1. Identify which module and source file own the class.
2. Locate the corresponding call or reference in source; if absent, inspect generated code or bytecode packaged from a dependency.
3. Read JDK documentation to determine deprecation release, forRemoval status, and replacement API.
4. Check the replacement API on the target JDK and other JDKs the project still supports.
5. Update source or upgrade the dependency/generator owning the call.
6. Run compile, unit tests, and integration tests covering the changed behavior.
7. Rebuild the artifact with the same configuration.
8. Re-run jdeprscan with the same release, classpath, and options as the baseline.
9. Save the new report and explain any remaining findings.

If the finding resides in a third-party library, check whether a newer library version removes that reference. If no fix exists yet, evaluate swapping the library, swapping the adapter, or maintaining a time-bounded exception. Do not patch bytecode inside third-party JARs as a normal practice because such changes are hard to reproduce and can break library signatures or behavior.

## 12. Scan Result Record Template

A report should retain enough data for others to re-run and understand the limits of the results:

| Field | Content |
|---|---|
| Module / artifact | Module name, JAR path, or class-file directory. |
| Artifact identity | Artifact version, commit SHA, or fingerprint. |
| jdeprscan version | Tool version and JDK providing the tool. |
| Reference release | --release value used. |
| Scan mode | All deprecated or --for-removal only. |
| Classpath | Dependencies supplied to resolve references. |
| Findings | List of detected classes/APIs and owning source if identified. |
| Resolution issues | Warnings or resolution errors, missing classpath, or unreadable artifacts. |
| Decision | Fix, upgrade dependency, replace, accept exception, or investigate further. |
| Evidence | Logs, executed commands, timestamp, and execution environment. |

Example tracking table:

| Artifact | Deprecated API | forRemoval | Source | Decision | Status |
|---|---|---|---|---|---|
| application.jar | API listed in report | Yes/No | Module or dependency | Replace API / upgrade library / investigate | Open / Resolved / Exception |

Do not enter assumed API names or results into the report. If the source has not been identified yet, write “unknown” and continue tracing via classpath, dependency tree, or artifact contents.

## 13. Operational Checklist for a Scan Pass

Before running:

- Identify the JDK providing jdeprscan and check the tool version.
- Identify the reference release and confirm the tool supports that release.
- Build the exact commit and identify input artifacts.
- Prepare the classpath needed for resolution.
- Determine whether dependencies need scanning separately.

During execution:

- Run a full deprecated API scan pass.
- Run a separate pass with --for-removal.
- Save verbatim commands and outputs, including warnings or errors.
- Do not include secrets in logs or reports.

After running:

- Distinguish deprecated findings, forRemoval findings, and resolution errors.
- Identify the class and artifact owning each reference.
- Look up replacement APIs and assess behavior.
- Create migration items, test, and re-scan.
- Save the baseline and exceptions with owner, reason, and due date.

## 14. Conclusion on Using jdeprscan

jdeprscan helps Java migration teams detect references to deprecated JDK APIs in bytecode. The --for-removal option highlights APIs that should be prioritized for replacement because they show signs of upcoming removal. When combined with --release, proper classpaths, and per-artifact scanning, teams can build a clear baseline for the application and critical dependencies.

The tool's value depends on input scope and how results are interpreted. Distinguish project source from dependencies, deprecated APIs from internal APIs, true findings from resolution errors, and bytecode target from runtime. Re-scanning after each change under identical conditions proves remediation progress; building and testing on the target JDK is what confirms the application can continue operating in the expected environment.