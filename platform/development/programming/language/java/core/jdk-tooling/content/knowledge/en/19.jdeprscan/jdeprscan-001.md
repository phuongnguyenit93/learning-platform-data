# The jdeprscan Command in the JDK

`jdeprscan` is a command-line tool included with the JDK for scanning Java bytecode and finding references to APIs marked as deprecated. It helps development teams inspect applications and libraries before upgrading the JDK, identify outdated APIs currently in use, and prioritize APIs that have been marked for removal.

Unlike `javac` deprecation warnings during source compilation, `jdeprscan` can inspect already built class files and JARs, including third-party library artifacts. It reports where bytecode references deprecated APIs so the development team can investigate and plan replacements.

## 1. What is jdeprscan used for?

Java marks an API as deprecated when it is no longer recommended for use. The API may still work, but developers should migrate to a newer or safer alternative.

For example, `java.util.Date.getYear()` has long been deprecated. Some APIs are also marked with `forRemoval=true` to signal that they are scheduled to be removed in a future Java version.

`jdeprscan` supports the following tasks:

- Scanning compiled class files for references to deprecated APIs.
- Scanning a directory containing a compiled package hierarchy.
- Scanning an application or library JAR file.
- Scanning a class by its fully qualified name if the class can be located via the classpath.
- Displaying only deprecated APIs marked for removal using `--for-removal`.
- Listing the set of deprecated APIs present in a Java SE release using `--list`.
- Selecting a reference release baseline using `--release`.
- Printing additional processing details using `--verbose`.

The tool is useful for migration assessments, auditing legacy libraries, preparing for JDK upgrades, and adding compatibility checks to CI.

## 2. How do Deprecation and forRemoval differ?

The `java.lang.Deprecated` annotation has two important attributes:

| Attribute | Meaning |
|---|---|
| `since` | The Java version in which the API was marked as deprecated. |
| `forRemoval` | Indicates whether the API has been marked for removal in a future release. |

Example:

~~~java
@Deprecated(since = "9")
public void oldMethod() {
}
~~~

The API above is deprecated, but does not declare `forRemoval=true`.

An API marked for removal:

~~~java
@Deprecated(since = "1.2", forRemoval = true)
public void stop() {
}
~~~

When using `jdeprscan`:

- A standard scan finds references to deprecated APIs.
- `--for-removal` restricts results to APIs with `forRemoval=true` in the selected release.
- APIs marked for removal should be evaluated with higher priority due to greater compatibility risk.

Deprecated does not mean the API has already been deleted. `jdeprscan` helps locate usages; the development team still needs to consult the API documentation to choose the right replacement.

## 3. Checking the JDK and Basic Syntax

`jdeprscan` is a JDK tool. Verify your environment:

~~~bash
java -version
jdeprscan --version
~~~

View help:

~~~bash
jdeprscan --help
~~~

General syntax:

~~~text
jdeprscan [options] {dir|jar|class} ...
~~~

Input arguments can be:

- The root directory of a package tree containing class files.
- A JAR file.
- A path to a class file.
- A fully qualified class name, such as `com.acme.LegacyApiDemo`.

Nested class names use `$` as the separator, for example `java.lang.Thread$State`. In shells that expand variables, such as Bash, wrap the class name in single quotes so the `$` character is not interpreted by the shell.

`jdeprscan` scans compiled bytecode. It does not accept `.java` source files as direct scan inputs. Compile the source first, then scan the output class directory or JAR.

## 4. Commonly Used Options

Options provided by JDK 24.0.2:

| Option | Function |
|---|---|
| `--class-path PATH` | Specifies the path to search for dependent classes during resolution. |
| `--for-removal` | Scans or lists only deprecated APIs marked for removal. |
| `--full-version` | Prints the full version string of the tool. |
| `--help`, `-h`, `-?` | Prints usage instructions. |
| `--list`, `-l` | Lists the set of deprecated APIs without scanning any inputs. |
| `--release N` | Selects the Java SE release used as the API baseline for scanning. |
| `--verbose`, `-v` | Prints additional information during processing. |
| `--version` | Prints the abbreviated version of the tool. |

The list of supported releases depends on the installed JDK version. On JDK 24.0.2 used to verify this guide, `--release` supports values from 8 through 24.

Avoid hardcoding the release list into long-lived scripts. When switching JDKs, run `jdeprscan --help` to check the release range supported by the new tool version.

## 5. Selecting a Release with --release

`--release` selects the Java SE version used as the baseline for identifying deprecated APIs. This is a critical option when evaluating an application for a specific upgrade target.

Example:

~~~bash
jdeprscan --release 17 build/classes
~~~

This command instructs the tool to compare bytecode references against the deprecated API set of Java SE 17.

Scanning against a newer release:

~~~bash
jdeprscan --release 24 build/classes
~~~

The same API can have different deprecation statuses across releases. Verified example on JDK 24.0.2:

- In the for-removal API list for release 17, `java.lang.Thread.stop()` does not appear.
- In the for-removal API list for release 24, this method appears with `@Deprecated(since="1.2", forRemoval=true)`.

Therefore, when preparing to upgrade to JDK 24, you should scan against release 24 to see APIs marked for removal in that release. Choosing a release close to your migration target makes the results more meaningful.

If `--release` is omitted, the tool uses the API set of the running JDK. For reproducible CI results, specify the release explicitly rather than relying implicitly on the JDK installed on the build agent.

In JDK 24, `--for-removal` cannot be combined with `--release 8`. Check the help output of your tool version before combining options.

## 6. Scanning a Class File Directory

After compiling the application, you can scan the entire output directory:

~~~bash
javac -d build/classes src/com/acme/LegacyApiDemo.java
jdeprscan --release 24 build/classes
~~~

The directory passed in is the root of the package tree. The tool traverses the class files underneath to find deprecated references.

Example structure:

~~~text
build/
└── classes/
    └── com/
        └── acme/
            ├── LegacyApiDemo.class
            └── service/
                └── LegacyService.class
~~~

Scanning `build/classes` can find results in both `LegacyApiDemo.class` and `LegacyService.class`.

If you only want to scan a specific class file:

~~~bash
jdeprscan --release 24 build/classes/com/acme/LegacyApiDemo.class
~~~

This approach is useful when investigating a specific class or narrowing down a large report.

## 7. Scanning JAR Files

`jdeprscan` accepts a JAR path directly:

~~~bash
jdeprscan --release 24 build/legacy-demo.jar
~~~

JARs typically contain multiple packages and classes. Scanning a JAR helps verify the packaged artifact, matching what is actually intended for distribution.

Example of creating a JAR from a class directory:

~~~bash
jar --create --file build/legacy-demo.jar -C build/classes .
jdeprscan --release 24 build/legacy-demo.jar
~~~

You can scan multiple inputs in a single run:

~~~bash
jdeprscan --release 24 build/classes build/legacy-demo.jar
~~~

When multiple inputs are provided, results are grouped by each directory or JAR. If the same class appears in multiple inputs, the report may repeat findings for each scanned artifact.

You should scan the actual artifact your team plans to release. Scanning both the class directory and the JAR helps validate at two different stages of the build pipeline.

## 8. Scanning Classes by Name and Classpath

You can pass a fully qualified class name instead of a class file path:

~~~bash
jdeprscan --release 24 --class-path build/classes com.acme.LegacyApiDemo
~~~

`--class-path` specifies where to locate classes and dependencies that the tool needs to resolve. The class name must include the full package name; do not use a simple name if the class resides in a package.

If there are multiple dependencies, separate them according to the operating system's classpath rules:

Linux/macOS:

~~~bash
jdeprscan --release 24 \
  --class-path "build/classes:lib/customer-api.jar:lib/common.jar" \
  com.acme.LegacyApiDemo
~~~

Windows PowerShell:

~~~powershell
jdeprscan --release 24 --class-path "build/classes;lib/customer-api.jar;lib/common.jar" com.acme.LegacyApiDemo
~~~

Nested class names use `$`:

~~~bash
jdeprscan --release 24 --class-path build/classes 'com.acme.Outer$Inner'
~~~

Distinguish the two roles:

- The trailing argument such as `com.acme.LegacyApiDemo` specifies the class to scan.
- `--class-path` helps locate classes and dependencies needed for resolution.

The classpath does not replace the list of inputs to scan. If you want to inspect an entire library, pass that library's JAR or class directory as a scan argument.

## 9. Finding Only APIs Marked for Removal

When preparing for a JDK upgrade, teams often want to prioritize APIs at risk of being removed.

Use:

~~~bash
jdeprscan --release 24 --for-removal build/classes
~~~

The results contain only deprecated references marked for removal under the selected release.

This can also be combined with a JAR:

~~~bash
jdeprscan --release 24 --for-removal build/legacy-demo.jar
~~~

`--for-removal` can also be used with `--list` to view the list of APIs in this category:

~~~bash
jdeprscan --release 24 --for-removal --list
~~~

The command above only lists APIs; it does not scan classes, directories, or JARs. Do not pass scan input arguments when using `--list` mode.

If you need a complete picture of deprecation, run another pass without `--for-removal`. Scanning only for removal may miss regular deprecated APIs that your team still wants to replace gradually.

## 10. Listing Deprecated APIs with --list

`--list` displays the set of deprecated APIs known in the selected release:

~~~bash
jdeprscan --release 24 --list
~~~

This command does not scan class files. It is useful when looking up which APIs are marked deprecated in a given Java version.

Filtering the for-removal list:

~~~bash
jdeprscan --release 24 --for-removal --list
~~~

A line in the list may look like this:

~~~text
@Deprecated(since="1.2", forRemoval=true) void java.lang.Thread.stop()
~~~

This line shows that `Thread.stop()` has been marked deprecated since version 1.2 and currently has `forRemoval=true` in the selected release's API set.

On PowerShell, you can filter the output to look up a specific API:

~~~powershell
jdeprscan --release 24 --list | Select-String "java.lang.Thread.stop"
~~~

On Linux/macOS, you can use `grep`:

~~~bash
jdeprscan --release 24 --list | grep 'java.lang.Thread.stop'
~~~

When piping, only the matching subset is displayed. The original `--list` command remains the complete data source.

## 11. Reading and Understanding Scan Results

Example of actual output from JDK 24.0.2 when scanning a class directory:

~~~text
Directory out:
class com/acme/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
class com/acme/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

How to read it:

- `Directory out:` indicates the scanned input is a directory.
- `class com/acme/LegacyApiDemo` is the class containing the reference to the deprecated API.
- `java/util/Date::getYear()I` identifies the owning class, method name, and JVM descriptor.
- `java/lang/Thread::stop()V` identifies the reference to `Thread.stop()`.
- `(forRemoval=true)` indicates the API is marked for removal.

Class names in descriptors use forward slashes instead of dots. The part after the method name is the JVM descriptor:

| Symbol | Meaning |
|---|---|
| `()I` | No parameters, returns `int`. |
| `()V` | No parameters, returns `void`. |
| `(Ljava/lang/String;)I` | Takes one `String`, returns `int`. |
| `(I)Ljava/lang/String;` | Takes one `int`, returns `String`. |

Descriptors help distinguish overloads and pinpoint the exact signature referenced by the bytecode.

JAR output has a different header:

~~~text
Jar file legacy-demo.jar:
class com/acme/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
class com/acme/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

If `--for-removal` is used, the `Date.getYear()` line is excluded from the report, while `Thread.stop()` still appears.

## 12. Complete Example: Compiling and Scanning Deprecated APIs

This example uses two APIs with different statuses:

- `Date.getYear()` is a standard deprecated API.
- `Thread.stop()` is marked for removal in JDK 24.

Create the directory structure:

~~~text
jdeprscan-demo/
└── src/
    └── com/
        └── acme/
            └── LegacyApiDemo.java
~~~

File `src/com/acme/LegacyApiDemo.java`:

~~~java
package com.acme;

import java.util.Date;

public class LegacyApiDemo {
    public static void main(String[] args) {
        Date epoch = new Date(12L * 60 * 60 * 1000);
        System.out.println("Legacy year offset: " + epoch.getYear());
    }

    static void stopThread(Thread thread) {
        thread.stop();
    }
}
~~~

The `stopThread` method only demonstrates a bytecode reference to a for-removal API. The program does not call this method at runtime; `Thread.stop()` should not be used to stop threads in real applications.

### Step 1: Compile

From the root directory `jdeprscan-demo`:

~~~bash
javac -Xlint:deprecation -d build/classes src/com/acme/LegacyApiDemo.java
~~~

The compiler will warn that `Date.getYear()` is deprecated and that `Thread.stop()` is deprecated and marked for removal. Compiler warnings originate from the source code being compiled.

### Step 2: Run the program

~~~bash
java -cp build/classes com.acme.LegacyApiDemo
~~~

Exact stdout:

~~~text
Legacy year offset: 70
~~~

`Date.getYear()` returns the year minus 1900. For the timestamp chosen in the example, the returned value is 70.

### Step 3: Scan the class directory

~~~bash
jdeprscan --release 24 build/classes
~~~

Output:

~~~text
Directory build/classes:
class com/acme/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
class com/acme/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

### Step 4: Scan only for-removal APIs

~~~bash
jdeprscan --release 24 --for-removal build/classes
~~~

Output:

~~~text
Directory build/classes:
class com/acme/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

### Step 5: Package as a JAR and scan again

~~~bash
jar --create --file build/legacy-demo.jar -C build/classes .
jdeprscan --release 24 build/legacy-demo.jar
~~~

Output:

~~~text
Jar file build/legacy-demo.jar:
class com/acme/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
class com/acme/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

This example demonstrates that you can scan either a class directory or a JAR and detect the same deprecated references after packaging.

## 13. Verbose Output and Tool Version

Use `--verbose` to see additional information while the tool processes inputs:

~~~bash
jdeprscan --verbose --release 24 build/classes
~~~

Verbose output is helpful when you need to see which classes or dependencies the tool is processing. Detailed output may vary across JDK versions.

View the abbreviated version:

~~~bash
jdeprscan --version
~~~

View the full version string:

~~~bash
jdeprscan --full-version
~~~

When comparing results between a developer machine and CI, record both the JDK version and the release baseline. Different versions of `jdeprscan` may be aware of different sets of deprecated APIs.

## 14. Limitations of jdeprscan

`jdeprscan` analyzes references in bytecode. It does not execute the application and cannot detect every way an API might be used.

Important limitations include:

- Does not scan `.java` source files directly; compilation is required first.
- Cannot identify all API calls constructed dynamically via reflection or class/method names stored in strings.
- Does not analyze logic inside native code or JNI libraries.
- Does not detect code loaded remotely or generated after scan time if that artifact is not among the inputs.
- Does not determine which replacement API is behaviorally equivalent or safe for your application.
- Does not guarantee the application will run successfully on a newer JDK simply because the report has no findings.

If your application uses reflection, plugins, service loaders, scripting, or native libraries, supplement the scan with runtime testing and configuration reviews.

A scan with zero findings only means the tool found no deprecated references within the scanned inputs and selected release. It does not prove the entire system is free of deprecated API usage across all execution paths.

## 15. Interpreting Results and Planning Migration

When a deprecated API is found, do not replace it blindly in bulk without understanding its semantics.

A practical workflow:

1. Record the reported class, method/field, and descriptor.
2. Locate the corresponding source code or identify the dependency containing that bytecode.
3. Read the Javadoc of the deprecated API to understand the reason for deprecation and recommended alternatives.
4. Evaluate whether the new API preserves semantics, timezone handling, thread-safety, exceptions, and performance.
5. Write or update tests before making the replacement.
6. Rebuild the entire application and internal dependencies.
7. Re-run `jdeprscan` with the target release.
8. Run unit tests, integration tests, and tests on the target JDK.

Example of replacing `Date.getYear()`:

~~~java
import java.time.Instant;
import java.time.ZoneId;

int year = Instant.ofEpochMilli(0L)
        .atZone(ZoneId.of("UTC"))
        .getYear();

System.out.println(year);
~~~

Output:

~~~text
1970
~~~

This snippet uses `java.time` to get the calendar year in the UTC timezone. This is the full year value, unlike `Date.getYear()`, which returns the year minus 1900. When replacing the old API, confirm whether the application expects the full year or needs to preserve legacy logic.

For `Thread.stop()`, do not mechanically swap it for another forceful termination API. The standard way to stop a thread is to request cooperative cancellation, typically using `Thread.interrupt()` with a loop that checks the interrupt status, or an executor's cancellation mechanism.

If a finding points to a class in a third-party library, first check whether a newer library version has already removed the deprecated API usage. Do not manually patch library bytecode to suppress warnings.

## 16. Using jdeprscan in CI

You can add a scan step after the build:

~~~bash
jdeprscan --release 24 --for-removal build/classes
~~~

Then scan all deprecations:

~~~bash
jdeprscan --release 24 build/classes
~~~

A migration pipeline can be divided into two tiers:

- **High priority:** review and resolve APIs with `forRemoval=true`.
- **Maintenance:** track all deprecated APIs and schedule replacements by module or release.

Do not rely solely on the exit code to determine whether deprecations exist. In testing with JDK 24.0.2, `jdeprscan` returns exit code 0 even when the report contains deprecated references. Therefore, CI should archive and inspect the output according to project policy, such as comparing against an approved baseline or using a custom script to detect new findings.

A safe rollout approach:

1. Run the scan and save the output as a build artifact.
2. Compare the results against the existing baseline.
3. Block new for-removal references if that is project policy.
4. Track the total count of deprecated usages across builds.
5. Update the baseline after the team reviews changes.

Do not immediately fail the build on every legacy warning if the project has a large legacy codebase. Start by preventing new references from being introduced, then gradually reduce the baseline across migration waves.

## 17. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jdeprscan` is not recognized | JDK is not in PATH or a runtime-only environment is used. | Check `java -version` and the JDK location; invoke the tool from the JDK's `bin` directory if needed. |
| Class not found by name | Missing full package name or class is not on the classpath. | Use the fully qualified name and add `--class-path`. |
| No results despite source warnings | Scanning the wrong directory, JAR, or stale class files. | Verify the actual artifact and build timestamp. |
| Unable to resolve dependencies | Dependent classes are not on the search path. | Provide the appropriate classpath or scan an artifact containing full dependencies. |
| For-removal APIs not shown | The release baseline does not mark that API for removal yet. | Choose the appropriate target release and verify with `--list`. |
| `--for-removal` fails with release 8 | That option combination is not supported by the tool. | Use a compatible release or omit `--for-removal` when checking release 8. |
| Many lines from third-party libraries | The scanned JAR contains classes referencing deprecated APIs. | Identify the artifact causing the reference and update the dependency if a fixed version exists. |
| Build succeeds despite deprecation reports | Findings do not necessarily cause a non-zero exit code. | Parse the output and enforce custom policy checks in CI. |

If more diagnostic information is needed, re-run with `--verbose` and narrow the input down to the problematic class or JAR.

## 18. Recommended Verification Workflow

A reproducible workflow:

1. Choose the target JDK and release.
2. Rebuild the application so class files reflect the current source.
3. Scan the class directory with `jdeprscan --release N`.
4. Scan the distribution JAR to check the packaged artifact.
5. Run an additional pass with `--for-removal` to prioritize APIs at risk of removal.
6. Use `--list` when you need to verify the deprecation status of an API.
7. Use `--class-path` when resolving class names or dependencies.
8. Record the results and tool version in CI.
9. Investigate each reference, replace the API, and add tests.
10. Re-scan and compare the results against the baseline.

`jdeprscan` is a bytecode analysis tool for API lifecycle management. Combining it with compiler warnings, runtime testing, dependency checks, and migration documentation helps surface required changes early before a Java upgrade.
