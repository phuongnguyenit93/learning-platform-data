# Handling Deprecated Warnings with jdeprscan

`jdeprscan` is a command-line tool included with the JDK to scan class files, class directories, and JARs for references to Java SE APIs that have been marked as deprecated. The tool is useful when preparing for a JDK upgrade, evaluating legacy libraries, and prioritizing APIs at risk of removal.

`jdeprscan` performs static bytecode analysis; it does not run the application and does not automatically modify source code. The output shows which classes reference which deprecated APIs. Developers need to locate the source position, read the migration documentation, choose a replacement API, update the code or upgrade dependencies, and then re-scan and test.

It is important to distinguish:

- `jdeprscan` finds references in bytecode to deprecated Java platform APIs.
- `javac -Xlint:deprecation` and `-Xlint:removal` warn when compiling source code that uses deprecated APIs.
- Javadoc and migration guides explain why an API was deprecated, the replacement API, and migration notes.

Combining these approaches helps detect issues both in source code being compiled and in references already present in binary dependencies.

## 1. What Is a Deprecated API?

An API is marked as deprecated when platform or library authors recommend against using that API in new code. The API may still work, but it may have an outdated design, security issues, hard-to-maintain behavior, or a better replacement API.

The `@Deprecated` annotation marks a declaration:

```java
@Deprecated
public void oldOperation() {
    // Legacy implementation
}
```

Since Java 9, the annotation has `since` and `forRemoval` attributes:

```java
@Deprecated(since = "17", forRemoval = true)
public void legacyOperation() {
    // API is planned for removal
}
```

- `since` records the version in which the API was first deprecated.
- `forRemoval = false` or omitting it indicates that the API is deprecated but has not been explicitly marked for removal.
- `forRemoval = true` indicates the intent to remove the API in a future release.

In Javadoc, the `@deprecated` tag provides an explanation for users and should state the replacement API:

```java
/**
 * Performs the legacy operation.
 *
 * @deprecated Use {@link #newOperation()} instead.
 */
@Deprecated(since = "17", forRemoval = true)
public void oldOperation() {
    newOperation();
}
```

The annotation provides metadata for compilers and tooling; the Javadoc tag explains the reason and migration path for documentation readers.

Deprecated does not mean already removed. An API may continue to exist for many releases after being deprecated. However, APIs with `forRemoval = true` should be prioritized because the risk of removal is higher.

## 2. What Does jdeprscan Check?

`jdeprscan` scans class files in the input and matches found references against the list of deprecated Java SE APIs in the selected release.

The input can be:

- A `.class` file.
- A directory containing class files.
- A JAR file.
- A set of classes or archives specified on the command line.

The tool can find references to deprecated methods, constructors, fields, or types. The output typically indicates the class containing the reference and the deprecated API being used. Detailed message formatting may vary by JDK version.

Important scope notes:

- `jdeprscan` focuses on deprecated Java SE/JDK platform APIs.
- It is not a general-purpose tool for finding all deprecated APIs in third-party libraries.
- It analyzes bytecode rather than reading the semantics of all source code.
- It does not execute the application and does not check all runtime execution paths.
- It may find references in methods that are not called during normal execution, because the bytecode still exists in the class file.

If you need to check deprecated APIs in third-party libraries or internal organizational APIs, use compiler warnings, library documentation, IDE inspections, or appropriate static-analysis rules.

## 3. Starting and Viewing Help

`jdeprscan` is shipped with the JDK. Check the version and help:

```sh
jdeprscan --version
jdeprscan --help
```

General syntax:

```text
jdeprscan [options] {dir|jar|class}
```

Scan a JAR:

```sh
jdeprscan app.jar
```

Scan a class file directory:

```sh
jdeprscan build/classes
```

Scan a specific class:

```sh
jdeprscan build/classes/com/example/LegacyService.class
```

If no release is specified, the tool uses the API set of the current JDK according to the tool version's rules. When checking for upgrades, you should explicitly specify the release for reproducible results.

## 4. Selecting the API Release with --release

The `--release` option selects the Java SE release used as the baseline for checking deprecated APIs:

```sh
jdeprscan --release 17 app.jar
```

The list of supported releases depends on the JDK running `jdeprscan`. Check `jdeprscan --help` for valid values.

Choose the release based on your goal:

| Goal | How to Choose |
|---|---|
| Check deprecated APIs against the current JDK | Use the release matching the current JDK or omit the option if appropriate |
| Check an application running on Java 17 | Use `--release 17` |
| Prepare to upgrade an application from Java 17 to Java 21 | Use `--release 21` to detect APIs deprecated in the target platform |
| Compare changes across releases | Run multiple times with each supported release |

Example when preparing to upgrade to Java 21:

```sh
jdeprscan --release 21 app.jar
jdeprscan --release 21 --for-removal app.jar
```

The first command finds APIs deprecated as of release 21; the second focuses on APIs marked for removal in that release. If you only scan against an older release, you may miss APIs newly deprecated in the target release.

## 5. Finding Only APIs Deprecated for Removal

The `--for-removal` option restricts results to APIs marked to be removed:

```sh
jdeprscan --for-removal --release 21 app.jar
```

Use this option to build a priority list for an upgrade plan. These APIs need to be addressed earlier than ordinary deprecated APIs.

You can view the list of deprecated APIs for a release without scanning a specific application using `--list`:

```sh
jdeprscan --list --release 21
```

List only APIs marked for removal:

```sh
jdeprscan --list --for-removal --release 21
```

The `--list` commands are useful when looking up an API or compiling a list of changes between releases. Results depend on the JDK and the specified release.

## 6. Reading Scan Results

A finding typically reports:

1. The name of the class file containing the reference.
2. The reference kind, such as method or field.
3. The API name and signature used by the class file.
4. The deprecated/for-removal status for the selected release.

Illustrative example of finding content:

```text
LegacyDateExample uses deprecated method
java/util/Date::getYear()I
```

This is a simplified illustration; actual output formatting may differ across JDK versions.

When reading a finding, determine:

- Which API is being referenced?
- Since which release has the API been deprecated?
- Is it marked for removal?
- Which class makes the reference?
- Does that class belong to application source or a third-party library?
- Does the replacement API preserve the required semantics and behavior?

Do not merely count warnings. A single reference in a legacy library can affect many applications; a deprecated API in a rarely used code branch may have a different priority. Combine findings with usage frequency, updatability, and release plans.

## 7. Example: Detecting a Deprecated API in Source

The `Date.getYear()` method is a legacy deprecated API. It returns the year minus 1900, so legacy code often has to add 1900 to get the full year.

Create the file `src/LegacyDateExample.java`:

```java
import java.util.Date;

public class LegacyDateExample {
    public static int year(Date date) {
        return date.getYear() + 1900;
    }

    public static void main(String[] args) {
        System.out.println(year(new Date(1592222400000L)));
    }
}
```

Compile with deprecation warnings:

```sh
javac -Xlint:deprecation -d out src/LegacyDateExample.java
```

The compiler will warn about using `Date.getYear()`. Once the class file is generated, scan it:

```sh
jdeprscan --release 21 out
```

The output identifies that class `LegacyDateExample` references the deprecated method `java.util.Date.getYear()`. Formatting details may vary by JDK.

Run the legacy program:

```sh
java -cp out LegacyDateExample
```

Stdout:

```text
2020
```

The example uses a mid-2020 instant so that `Date.getYear()` produces the same year consistently across common timezones. The legacy method still depends on the default timezone; it should not be used for new date/time logic.

## 8. Replacing Deprecated APIs with java.time

For new code, use the Java Date and Time API in `java.time` instead of legacy date/time operations.

Create the file `src/ModernDateExample.java`:

```java
import java.time.ZoneId;
import java.util.Date;

public class ModernDateExample {
    public static int year(Date date) {
        return date.toInstant()
                   .atZone(ZoneId.of("UTC"))
                   .getYear();
    }

    public static void main(String[] args) {
        System.out.println(year(new Date(1592222400000L)));
    }
}
```

Compile and run:

```sh
javac -d out src/ModernDateExample.java
java -cp out ModernDateExample
```

Stdout:

```text
2020
```

The new code converts `Date` to an `Instant` and then converts the instant to UTC before retrieving the year. Choosing UTC makes the example output consistent and independent of the machine's default timezone.

When replacing date/time APIs, do not ignore timezones. If business logic requires the year in the user's or business location's timezone, use the corresponding `ZoneId` instead of always using UTC. Replacing an API must preserve business semantics, not merely make the warning disappear.

## 9. Handling a Finding Step by Step

When `jdeprscan` reports a deprecated API, follow these steps:

1. **Locate:** record the reported class, method/field, and signature.
2. **Find the source:** locate the corresponding declaration or call site in the source code.
3. **Read documentation:** open the API's Javadoc and read the `@deprecated` section, replacement, or migration guide.
4. **Assess severity:** determine whether the API has `forRemoval`, the release in which deprecation started, and the target runtime.
5. **Choose a replacement:** prefer officially supported APIs that preserve the correct semantics.
6. **Update the code:** update methods, imports, types, and related exception handling.
7. **Test:** add tests for outputs, boundary values, timezones, encoding, resources, or behavior that may change.
8. **Re-scan:** recompile and run `jdeprscan` on the new artifact.
9. **Document:** record any remaining findings, the reason they are unresolved, and the planned upgrade version.

If the API has no direct replacement, look for a migration guide or redesign that part of the functionality. Do not create a wrapper that merely renames the call while still invoking the deprecated API underneath; the finding in the bytecode will still remain.

## 10. Handling Warnings from Third-Party Libraries

A finding may come from a class file in an external library rather than source code owned by the project team.

Workflow:

- Identify the JAR containing the reported class.
- Check the current library version and the latest compatible version.
- Read the vendor's changelog/migration guide.
- Upgrade the dependency if a newer version has already replaced the deprecated API.
- If no fix is available, assess the risk and look for an alternative library.
- Run integration tests after upgrading the version.

`--class-path` helps `jdeprscan` resolve dependencies needed during analysis:

```sh
jdeprscan --release 21 --class-path "lib/*" app.jar
```

On Windows, the separator for multiple classpath entries is a semicolon; Linux/macOS uses a colon.

Note: `--class-path` provides dependencies to resolve references. It does not mean all JARs on the classpath are automatically scanned as inputs. If you want to scan a library, pass that JAR itself as the target to analyze:

```sh
jdeprscan --release 21 lib/legacy-library.jar
```

If the library is a third-party binary, the application team may not be able to modify its bytecode. In that case, upgrade the version, replace the library, or document the remaining risk; do not arbitrarily patch released JARs.

## 11. Distinguishing Source Warnings from Binary Findings

`jdeprscan` and the compiler play complementary roles:

| Tool | Timing | Primary Scope |
|---|---|---|
| `javac -Xlint:deprecation` | When compiling source | Deprecated calls visible to the compiler in the source being compiled |
| `javac -Xlint:removal` | When compiling source | Calls to APIs marked for removal |
| `jdeprscan` | After classes/JARs exist | Deprecated references stored in bytecode |
| IDE inspection | During development | Source and dependencies depending on IDE capabilities |
| Javadoc/migration guide | During investigation | Deprecation rationale and replacement guidance |

Enable compiler warnings:

```sh
javac -Xlint:deprecation -Xlint:removal -d out src/com/example/*.java
```

If you want the build to fail on warnings, consider `-Werror` after addressing existing warnings:

```sh
javac -Xlint:deprecation -Xlint:removal -Werror -d out src/com/example/*.java
```

`-Werror` turns compiler warnings into build errors. This is a build policy, not a `jdeprscan` option. Check wildcard syntax for the shell in use; PowerShell does not expand wildcards for all native commands in the same way as Bash.

## 12. Limitations of Static Analysis

`jdeprscan` is useful, but it cannot replace runtime testing. Cases that may not be fully detected include:

- Class or method names stored in strings and invoked via reflection.
- Classes loaded via `Class.forName` with names taken from configuration.
- Plugins discovered and loaded dynamically.
- Bytecode generated at runtime.
- Native code calling into Java or using APIs via JNI.
- Code paths only triggered under specific configurations or data.

Example:

```java
String className = configuration.get("implementation.class");
Class<?> implementation = Class.forName(className);
```

If the configuration value points to a class that uses a deprecated API, `jdeprscan` may not infer the link from this configuration string. Check plugins, configuration files, and integration tests.

Conversely, the tool may report references in methods that are not called at runtime. This is not necessarily a false positive: the bytecode still contains the reference and may be triggered later.

## 13. Deprecated APIs in Modules and Multi-Release JARs

When scanning modules or JARs with external dependencies, provide the appropriate module path:

```sh
jdeprscan --release 21 --module-path "mods:lib" app.jar
```

`--module-path` helps the tool locate required modules to resolve references. On Windows, use a semicolon to separate module path entries.

For multi-release JARs, select the class version to analyze with `--multi-release`:

```sh
jdeprscan --release 21 --multi-release 17 library.jar
```

This option instructs the tool to inspect the appropriate versioned entries in the multi-release JAR. Choose the release corresponding to the runtime configuration being evaluated and verify that the archive is marked `Multi-Release: true` in its manifest.

If a library contains multiple implementations per Java release, deprecated dependencies may differ between base entries and versioned entries. Do not use the result for one release to conclude that all versions are clean.

## 14. Integrating jdeprscan into the Upgrade Workflow

A CI verification workflow can include:

1. Compile the application with the target JDK.
2. Enable compiler warnings for deprecation and removal.
3. Build the output JAR or class directory.
4. Run `jdeprscan` with `--release` matching the target.
5. Also run `--for-removal` to build a priority list.
6. Scan internal JARs or critical libraries separately.
7. Save logs as pipeline artifacts.
8. Run unit tests and integration tests on the target runtime.
9. Compare findings against the main branch baseline.
10. Block the introduction of new findings according to project policy.

Example Linux/macOS script:

```sh
set -e
rm -rf out
mkdir -p out
javac -Xlint:deprecation -Xlint:removal -d out src/com/example/*.java
jdeprscan --release 21 out
jdeprscan --for-removal --release 21 out
```

The script illustrates the compile-then-scan order. In multi-package/multi-module projects, use the actual build configuration instead of a simple wildcard. `jdeprscan` does not assign severity levels to individual findings; CI needs its own rules to compare and handle results.

With Maven or Gradle, you can add a step to run the tool in a task/plugin or pipeline after the artifact is built. Ensure `jdeprscan` comes from the target JDK rather than accidentally running a different JDK version from the one used to build.

## 15. Handling Your Own Project's Deprecated APIs

If a project publishes its own library and wants to mark legacy APIs so users can migrate, declare the annotation along with Javadoc:

```java
/**
 * Creates a legacy client.
 *
 * @deprecated Use {@link #createClient()} instead.
 */
@Deprecated(since = "2.0", forRemoval = true)
public static Client createLegacyClient() {
    return createClient();
}

/**
 * Creates a supported client.
 *
 * @return a new client
 */
public static Client createClient() {
    return new Client();
}
```

Guidelines:

- Record the release where deprecation begins using `since`.
- Use `forRemoval = true` only when there is an actual plan for removal.
- Use the Javadoc `@deprecated` tag to explain the replacement.
- Maintain compatible behavior during the transition period if required by the API policy.
- Optionally document a migration guide and expected removal milestone.

`jdeprscan` is not a general-purpose tool for scanning all deprecated annotations defined by custom libraries. To check usage of internal deprecated APIs, rely on compiler warnings when compiling client source, IDE/static analysis, and project tests.

## 16. Do Not Hide Warnings with Suppression

Java supports `@SuppressWarnings("deprecation")` and related warning categories in the compiler. Suppression should only be used with a specific reason, narrow scope, and an explanatory comment.

Example:

```java
@SuppressWarnings("deprecation")
static int legacyYear(java.util.Date date) {
    return date.getYear() + 1900;
}
```

Suppression can stop the compiler from warning on that source snippet. It does not replace the API, does not change the bytecode, and does not make `jdeprscan` ignore the compiled reference.

If you must keep a legacy API during a transition period:

- Isolate the call in a small method.
- Clearly document the reason and removal plan.
- Add tests to ensure compatible behavior.
- Track the release in which the API may be removed.
- Do not suppress an entire package or project when only one specific location is involved.

For APIs already removed from the target JDK, suppression will not help the code compile or run. You must replace the API or change the dependency/runtime.

## 17. Common Issues When Using jdeprscan

| Symptom | Common Cause | Resolution |
|---|---|---|
| No findings, but the compiler still warns | Source or library uses a deprecated API outside the Java SE scope recognized by jdeprscan | Use compiler lint and library analysis tools |
| Class/dependency not found | Classpath or module path is missing a JAR | Add the proper dependency and verify the path |
| Finding points to a class in an external library | Binary dependency uses a deprecated API | Upgrade the dependency or replace the library |
| Results differ when switching JDKs | The list of deprecated APIs changes across releases | Specify the JDK and use `--release` explicitly |
| APIs called via reflection are not shown | Reference only exists as a string or configuration | Check configuration, plugins, and runtime tests |
| Scanning a JAR misses versioned classes | Multi-release JAR was not analyzed for the appropriate release | Use `--multi-release` |
| Using --for-removal yields few findings | Only APIs marked for removal are reported | Run an additional pass without this option to see all deprecated APIs |
| Suppressed compiler warning, yet jdeprscan still reports it | Suppression does not remove the reference from bytecode | Replace the API or accept/document the finding in a controlled way |
| Application runs on an older JDK but fails on a newer JDK | API was removed or behavior changed | Scan against the target release and test the migration |
| Only scanned the application JAR and missed dependencies | Dependencies were not passed as scan inputs | Scan artifacts within your control separately |

When the tool reports a resolution error, check the classpath/module path before concluding that an API does not exist. When the tool reports no findings, still check reflection and external dependencies because static analysis has limitations.

## 18. Warning Handling Checklist

- [ ] Identified the JDK and target API release to check.
- [ ] Ran `jdeprscan` on the latest class directory or JAR.
- [ ] Also ran `--for-removal` to prioritize APIs at risk of removal.
- [ ] Reviewed the class and symbol reported in each finding.
- [ ] Determined whether each finding belongs to project source or an external library.
- [ ] Read the Javadoc/migration guide for the deprecated API.
- [ ] Selected a replacement that preserves semantics, timezone, and error handling.
- [ ] Upgraded or replaced the dependency if the finding comes from a third-party library.
- [ ] Reviewed reflection, service providers, plugins, and dynamic class loading.
- [ ] Enabled compiler warnings `-Xlint:deprecation` and `-Xlint:removal`.
- [ ] Recompiled and re-scanned artifacts after fixes.
- [ ] Ran unit tests and integration tests on the target JDK.
- [ ] Remaining findings have a clear reason, owner, and remediation plan.

## 19. References

- Oracle JDK 21 Tool Reference — The `jdeprscan` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeprscan.html
- Oracle Java Language Specification — Annotations and `@Deprecated`: https://docs.oracle.com/javase/specs/
- Oracle Java API Documentation — `java.lang.Deprecated`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Deprecated.html

`jdeprscan` helps detect references to deprecated Java APIs early before a JDK upgrade. By reviewing findings per release, prioritizing APIs marked for removal, replacing them with supported APIs, and retesting on the target runtime, development teams can reduce compatibility risks and prevent legacy dependencies from becoming obstacles in future upgrades.