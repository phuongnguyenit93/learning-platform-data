# Scanning Deprecated APIs with the jdeprscan Tool

## 1. What Is a Deprecated API?

A deprecated API is an API that Java developers recommend stopping using in new code. The API may still exist and function, but there may be a better alternative, design issues, maintenance difficulties, or plans to remove it in the future.

Java marks deprecated APIs with the `@Deprecated` annotation. This annotation has two important attributes:

- `since` indicates the Java version in which the API was marked deprecated.
- `forRemoval` indicates whether the API is marked for removal in a future version. The default value is `false`.

Example:

~~~java
/**
 * @deprecated Use {@link #newOperation()} instead.
 */
@Deprecated(since = "17", forRemoval = true)
public void oldOperation() {
    // Legacy behavior
}
~~~

It is important to distinguish the `@Deprecated` annotation from the `@deprecated` Javadoc tag:

- `@Deprecated` is metadata in bytecode, read by the compiler and analysis tools.
- `@deprecated` is an explanation for documentation readers, usually stating the reason and the replacement API.
- Both should be used when marking your own project's APIs.

Deprecated does not mean already deleted. An API can continue to exist across many versions. `forRemoval = true` expresses the intent to remove it, but does not provide a definite removal date or version.

## 2. What Is jdeprscan Used For?

`jdeprscan` is a JDK tool used to scan bytecode and find references to Java SE APIs that are deprecated in a selected release. The tool supports scanning class directories, JAR files, individual class files, or fully qualified class names.

The tool is useful when:

- Upgrading an application to a new JDK.
- Auditing legacy libraries before updating dependencies.
- Finding APIs marked deprecated in compiled bytecode.
- Separating APIs that are only deprecated from APIs marked `forRemoval`.
- Generating technical reports to plan the replacement of legacy APIs.

`jdeprscan` analyzes compiled bytecode. It does not accept `.java` source files as input and does not automatically modify source code. For source code being compiled, combine it with `javac -Xlint:deprecation` and `javac -Xlint:removal`.

The tool also does not replace running tests on the target JDK. An API may remain deprecated yet behave differently in a new runtime; conversely, a reference not reported by the scanner does not prove the application is fully compatible.

## 3. Installation and Checking the Tool Version

`jdeprscan` is located in the JDK's `bin` directory. If `JAVA_HOME` points to the JDK, you can run:

~~~bash
jdeprscan --version
jdeprscan --full-version
jdeprscan --help
~~~

Options:

- `--version` prints the short version.
- `--full-version` prints the full version string.
- `--help` displays syntax, input types, and supported releases.

In the verification environment for this article, the tool is from JDK 24.0.2. The help output lists selectable releases from Java 8 through Java 24. This list depends on the installed JDK version; check `jdeprscan --help` on the build machine instead of assuming every JDK supports the same set of releases.

If the command is not recognized, check:

~~~bash
java --version
javac --version
jdeprscan --version
~~~

All three commands should point to the same JDK toolchain in CI. If `java` and `jdeprscan` come from two different JDK directories, the analysis results may not match the intended runtime environment.

## 4. Syntax and Input Types

General syntax:

~~~bash
jdeprscan [options] {dir|jar|class} ...
~~~

Main input types:

| Input | Example | Meaning |
|---|---|---|
| Directory | `build/classes` | Scans the package/class tree starting from the specified directory. |
| JAR | `build/app.jar` | Scans the classes inside the archive. |
| Class file | `build/classes/demo/Main.class` | Scans a specific class. |
| Class name | `demo.Main` | Scans a class by its fully qualified name; may require a class path to locate the class. |

Examples of scanning each type:

~~~bash
# Scan an entire class directory
jdeprscan --release 17 build/classes

# Scan a JAR
jdeprscan --release 17 build/app.jar

# Scan a single class file
jdeprscan --release 17 build/classes/demo/Main.class

# Scan by class name
jdeprscan --release 17 --class-path build/classes demo.Main
~~~

Nested class names use `$` to separate the outer class and inner class. Example:

~~~bash
jdeprscan --release 17 --class-path build/classes 'demo.Outer$Nested'
~~~

`jdeprscan` does not accept source files directly. If you only have source code, compile it into class files first before scanning.

## 5. Selecting the API Catalog with --release

The `--release` option specifies the Java SE release's deprecated API set to check against:

~~~bash
jdeprscan --release 17 build/classes
~~~

This helps check against the release on which the application will run. If preparing to upgrade from Java 17 to Java 24, you can run both passes:

~~~bash
jdeprscan --release 17 build/classes
jdeprscan --release 24 build/classes
~~~

Do not confuse `jdeprscan --release` with `javac --release`:

- `jdeprscan --release` selects the deprecated API catalog of the Java SE release to check against.
- `javac --release` selects the API set and language rules that the compiler uses when compiling source code.

Results can change across releases because deprecation metadata is updated across versions. An example verified with JDK 24.0.2: `Thread.stop()` is reported as deprecated when scanning against release 17, but in the release 24 catalog it is also marked `forRemoval=true`. Therefore, the same bytecode can yield different information when the selected release changes.

Choose the actual target release, document it explicitly in CI scripts, and do not compare two reports generated from different API catalogs without noting the difference.

## 6. Key Options

| Option | Purpose |
|---|---|
| `--release N` | Selects the Java SE release as the source of deprecated API metadata. |
| `--for-removal` | Reports only APIs marked deprecated for removal. |
| `--class-path PATH` | Provides the path to resolve dependent classes. |
| `--list` or `-l` | Lists the deprecated API set for the release; does not scan classes/JARs. |
| `--verbose` or `-v` | Prints additional information about the processing. |
| `--version` | Prints the short version of the tool. |
| `--full-version` | Prints the full version. |
| `--help`, `-h`, `-?` | Prints help. |

`--list` is catalog-listing mode. When using this option, do not pass directories, JARs, or classes to scan:

~~~bash
jdeprscan --list --release 17
~~~

List only APIs marked for removal:

~~~bash
jdeprscan --list --release 17 --for-removal
~~~

Scan only references marked for removal:

~~~bash
jdeprscan --release 17 --for-removal build/classes
~~~

In JDK 24.0.2, the help notes that `--for-removal` cannot be used with release 6, 7, or 8. Read the help output of the running version before combining this option with an older release.

## 7. Practical Example: Scanning Classes and JARs

Create the structure:

~~~text
jdeprscan-demo/
├── src/
│   └── demo/
│       └── LegacyApiDemo.java
├── build/
│   └── classes/
└── app.jar
~~~

File `src/demo/LegacyApiDemo.java`:

~~~java
package demo;

import java.util.Date;

public class LegacyApiDemo {

    @SuppressWarnings({"deprecation", "removal"})
    public static int legacyYear(Date date) {
        return date.getYear();
    }

    @SuppressWarnings({"deprecation", "removal"})
    public static void stopLegacyThread(Thread thread) {
        thread.stop();
    }
}
~~~

This example intentionally keeps references to two legacy APIs so the scanner can find them in bytecode. Do not call `stopLegacyThread` in a real application; `Thread.stop()` can terminate a thread at an arbitrary point and leave shared data in an inconsistent state.

Compile using the JDK 17 API:

~~~bash
mkdir -p build/classes
javac --release 17 -d build/classes src/demo/LegacyApiDemo.java
~~~

Scan the class directory:

~~~bash
jdeprscan --release 17 build/classes
~~~

The key output looks like:

~~~text
Directory build/classes:
class demo/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
class demo/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V
~~~

Rescan using the Java 24 catalog:

~~~bash
jdeprscan --release 24 build/classes
~~~

Output from JDK 24.0.2 looks like:

~~~text
Directory build/classes:
class demo/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
class demo/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Package the classes into a JAR:

~~~bash
jar --create --file app.jar -C build/classes .
~~~

Scan the JAR:

~~~bash
jdeprscan --release 17 app.jar
~~~

The JAR scan results contain the same two deprecated references as scanning the class directory. You can use this approach to inspect packaged artifacts before release.

## 8. Reading jdeprscan Output

A result line has the form:

~~~text
class demo/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
~~~

Meaning:

- `class demo/LegacyApiDemo` is the class in the application containing the reference.
- `java/util/Date` is the class that owns the called API.
- `getYear` is the method name.
- `()I` is the JVM method descriptor: no parameters and returns `int`.

Another example:

~~~text
class demo/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

`()V` means the method takes no parameters and returns `void`. The `forRemoval=true` part indicates the API is marked for removal in the release catalog being scanned.

The output may start with `Directory` or `Jar file` to indicate the input type. When `--verbose` is enabled, the tool prints additional information about processed classes and resolution progress.

Not every output line means the application will fail immediately at runtime. These are warnings about API dependencies that need to be evaluated and scheduled for replacement.

## 9. Distinguishing Deprecated and Deprecated for Removal

`@Deprecated` can be used without marking for removal. The two states have different meanings:

| State | Meaning | Action |
|---|---|---|
| Deprecated | The API is no longer recommended; may remain available long-term. | Find a replacement API and schedule it in maintenance plans. |
| Deprecated for removal | The API is marked with the intent to remove it in the future. | Prioritize handling, check the target release, and avoid adding new dependencies on it. |
| Removed | The API has already been removed from the release in use. | Must replace it or use a compatible library/runtime; the scanner cannot make a removed API exist again. |

`--for-removal` filters for APIs in the second row. You should not run only this mode: ordinary deprecated APIs may still need to be replaced before major upgrades.

A sensible migration workflow is to run both the full report and the for-removal report, then prioritize APIs with a high risk of removal.

## 10. Scanning Classes with Dependencies Using --class-path

A class may reference other classes in dependent libraries. Use `--class-path` to provide the path to locate those classes:

~~~bash
jdeprscan --release 17 \
  --class-path "build/classes;lib/*" \
  build/app.jar
~~~

On Windows, the class path separator is a semicolon (`;`). On Linux/macOS, the separator is a colon (`:`):

~~~bash
jdeprscan --release 17 \
  --class-path "build/classes:lib/*" \
  build/app.jar
~~~

The class path helps the tool resolve types referenced by bytecode. It is not a module path and does not replace providing required dependencies in the build environment.

If the scanner cannot resolve a dependent class, check:

- Whether the JAR is actually on the class path.
- Whether wildcards are passed properly by the shell.
- Whether the package/class name is correct.
- Whether the dependency was built into compatible class files.
- Whether the dependency version matches the artifact being scanned.

Do not ignore resolution warnings just to get a shorter report. Record unresolved classes to avoid concluding that the entire dependency graph has been checked.

## 11. Listing the Deprecated API Catalog

`--list` is useful when you need to find which APIs are marked deprecated in a release without needing a sample application.

List the entire catalog:

~~~bash
jdeprscan --list --release 17
~~~

List only APIs marked for removal:

~~~bash
jdeprscan --list --release 17 --for-removal
~~~

On PowerShell, filter specific APIs:

~~~powershell
jdeprscan --list --release 17 |
    Select-String -Pattern "java.util.Date.getYear|java.lang.Thread.stop"
~~~

On Linux/macOS:

~~~bash
jdeprscan --list --release 17 |
    grep -E "java.util.Date.getYear|java.lang.Thread.stop"
~~~

The catalog is usually large, so filter by the class or API under investigation. This command only displays JDK metadata; it does not prove that the application uses that API.

To know whether the application references an API, you must scan the actual classes/JARs.

## 12. Finding Replacements for Deprecated APIs

`jdeprscan` only reports reference locations. It does not automatically suggest a correct replacement for every case. When replacing an API, you must understand the legacy semantics, exception handling, and compatibility requirements of the program.

Some common replacement directions:

| Legacy API | Replacement Direction | Notes |
|---|---|---|
| `Date.getYear()` and legacy date/time operations | `java.time` such as `LocalDate`, `ZonedDateTime`, `Instant` | Pay attention to timezone and that `Date.getYear()` returns the year minus 1900. |
| `Class.newInstance()` | `getDeclaredConstructor().newInstance()` | Check constructors, access permissions, and new exceptions. |
| `Thread.stop()` | `interrupt()`, task cancellation flags, or `ExecutorService` | Use cooperative cancellation; do not stop a thread at an arbitrary point. |
| `Thread.suspend()` / `resume()` | Coordination mechanisms using locks, conditions, or task state | Redesign synchronization to avoid deadlocks. |
| Legacy security APIs | Current security APIs and supported runtime configurations | Review the application's security model instead of mechanically renaming methods. |

Example replacing `Class.newInstance()`:

~~~java
Class<?> type = String.class;
Object value = type.getDeclaredConstructor().newInstance();
~~~

The new approach can throw `NoSuchMethodException`, `InvocationTargetException`, `InstantiationException`, or `IllegalAccessException`. Adjust exception handling to match the new contract.

For `Date.getYear()`, example getting the actual year from an instant:

~~~java
int year = date.toInstant()
        .atZone(ZoneId.systemDefault())
        .getYear();
~~~

`Date.getYear()` returns the year minus 1900, whereas `LocalDate.getYear()` returns the full year. If you need to preserve the legacy value for compatibility, convert it intentionally; do not swap methods and assume identical results.

## 13. Replacing Thread.stop() with Cooperative Cancellation

`Thread.stop()` is dangerous because a thread can be stopped in the middle of updating shared state. The standard approach is to ask the thread to terminate itself using an interrupt or a cancellation flag.

Standalone compilable and runnable example:

~~~java
import java.util.concurrent.CountDownLatch;

public class CooperativeCancellation {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            started.countDown();

            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Thread.sleep(50);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }

            System.out.println("worker stopped cooperatively");
        });

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 CooperativeCancellation.java
java CooperativeCancellation
~~~

Stdout:

~~~text
worker stopped cooperatively
~~~

The thread checks the interrupt status, exits the loop, and terminates at a point under its own control. For applications using thread pools, consider `ExecutorService.shutdown()` or `shutdownNow()` and design tasks to respond to interruption.

Do not swallow `InterruptedException` without reason. If you cannot terminate immediately, restore the interrupt status or propagate the exception to an appropriate caller layer.

## 14. Combining jdeprscan with Compiler Lint

`jdeprscan` scans bytecode; compiler lint checks deprecated calls in source code being compiled. The two tools complement each other.

Example:

~~~bash
javac --release 17 -Xlint:deprecation -d build/classes src/demo/LegacyApiDemo.java
~~~

You can turn warnings into errors in CI:

~~~bash
javac --release 17 -Xlint:deprecation -Werror \
  -d build/classes \
  src/demo/LegacyApiDemo.java
~~~

For APIs with removal warnings on the release in use, add the corresponding lint option:

~~~bash
javac --release 24 -Xlint:deprecation -Xlint:removal -Werror \
  -d build/classes \
  src/demo/LegacyApiDemo.java
~~~

In testing with JDK 24.0.2, `Class.newInstance()` appears in the `jdeprscan --list` catalog and the `javac -Xlint:deprecation` compiler emits a warning. However, the scanner did not report that reference in the test class, even though the bytecode contained the method call. This is an observed limitation in the tested tool version; do not rely solely on `jdeprscan` to conclude there are no deprecated APIs.

Therefore, for your own project's source code, enable compiler lint. For compiled binaries and libraries, run `jdeprscan`. Combine these with tests on the target JDK and dependency analysis tools when needed.

## 15. Limitations of Bytecode Scanning

Scanner results should be understood within the scope of data it can read:

- The scanner analyzes compiled bytecode; it does not read source code like the compiler.
- It checks against the deprecated API catalog of the selected Java SE release.
- It cannot automatically understand class/method strings built from configuration and invoked via reflection.
- Code generated dynamically at runtime or loaded from locations not included in the input may not appear in the report.
- References to deprecated APIs in third-party libraries require tools or catalogs suited to those libraries; `jdeprscan` is not a comprehensive report for every `@Deprecated` annotation in all dependencies.
- Missing dependent classes can affect resolution capabilities and report quality.
- The report does not evaluate whether replacement APIs preserve business behavior.

Another important observation: an API's deprecation status can change between releases. Always record the scanned release, the tool's JDK version, and the list of input artifacts alongside the report.

## 16. Migration Workflow in CI

You can add a deprecated API scanning step to the pipeline after compilation and before packaging:

~~~bash
# 1. Build bytecode for the target release
javac --release 17 -Xlint:deprecation \
  -d build/classes \
  @sources.txt

# 2. Scan all deprecated Java SE APIs
jdeprscan --release 17 build/classes

# 3. Scan specifically for APIs marked for removal
jdeprscan --release 17 --for-removal build/classes

# 4. Scan the release JAR
jar --create --file build/app.jar -C build/classes .
jdeprscan --release 17 build/app.jar

# 5. Test on the target runtime
java -cp build/classes demo.Main
~~~

When migrating to a new release, run reports against both the current release and the target release:

~~~bash
jdeprscan --release 17 build/app.jar
jdeprscan --release 24 build/app.jar
jdeprscan --release 24 --for-removal build/app.jar
~~~

The review process should:

1. Save the output for each release as a CI artifact.
2. Group findings by module/package, calling class, and deprecated API.
3. Prioritize APIs marked for removal.
4. Find replacement APIs and verify semantic differences.
5. Update code and tests.
6. Rescan the new artifacts.
7. Run integration tests on the target JDK.
8. Document remaining exceptions, their reasons, and remediation plans.

Do not fail the pipeline solely because of any output line if the project is in the middle of a major migration. You can start with reporting and baselining, then set quality gates for new APIs or APIs marked for removal.

## 17. Common Errors and Troubleshooting

| Symptom | Common Cause | Solution |
|---|---|---|
| `jdeprscan` command not found | JDK `bin` is not in PATH. | Check `JAVA_HOME` and invoke the executable in the `bin` directory. |
| No results even though source has deprecated calls | Scanning source instead of classes/JARs, or bytecode does not contain a reference the scanner recognizes. | Compile source, inspect bytecode with `javap -c`, and combine with compiler lint. |
| `jdeprscan --list` does not scan the application | `--list` only lists the catalog and does not accept target inputs. | Omit `--list` when scanning classes, directories, or JARs. |
| Reports differ between two JDK releases | Deprecation catalogs and for-removal statuses change across releases. | Choose and explicitly record `--release` for each report. |
| Dependent classes are not resolved | Dependencies are not on the class path. | Add `--class-path` with the correct directories/JARs. |
| `--for-removal` fails with older releases | The combination of release and option is not supported by the tool. | Check `jdeprscan --help` and use a supported release. |
| Scanning a JAR does not detect classes in dependent libraries | The input JAR does not include dependencies. | Scan dependencies separately or provide the class path for resolution. |
| Compiler warnings do not appear | Lint is not enabled, warnings are suppressed, or the source path is not being compiled. | Use `-Xlint:deprecation`, `-Xlint:removal`, and check suppress annotations. |
| Scanner reports an API but you do not know how to fix it | The tool only detects references; it does not perform migration. | Consult API documentation, evaluate semantics, and write tests before replacing. |
| No report findings but the application still fails on a new JDK | May be due to removed APIs, reflection, dynamic configuration, or other runtime issues. | Compile/test on the target JDK and inspect dynamic loading points rather than relying only on the scanner. |

## 18. Pre-Release Checklist

- Identified the JDK toolchain used to run `jdeprscan`.
- Selected `--release` matching the runtime to be checked.
- Input is a valid class directory, JAR, class file, or class name.
- Required dependencies are provided via `--class-path`.
- Saved both the full report and the `--for-removal` report.
- Reviewed each deprecated API and identified a replacement path.
- Enabled `javac -Xlint:deprecation` for the project's source code.
- Enabled `javac -Xlint:removal` where appropriate.
- Do not treat an empty report as sole proof of compatibility.
- Reflection or dynamic class loading points have been reviewed separately.
- Ran unit and integration tests on the target JDK.
- Remaining migration exceptions have an owner, rationale, and remediation plan.
- Report explicitly records the tool version, selected release, and scanned artifacts.

## 19. References

- [The jdeprscan Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeprscan.html)
- [Deprecated Annotation — JDK 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Deprecated.html)
- [Thread API — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Thread.html)

`jdeprscan` helps detect references to deprecated Java SE APIs in bytecode and prioritize those marked for removal. Choose the right release, scan both class directories and release JARs, combine with compiler lint, evaluate the semantics of replacement APIs, and test on the target JDK before completing a migration.
