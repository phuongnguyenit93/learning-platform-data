# Deprecated for removal APIs in Java and how to check them with jdeprscan

## 1. What does Deprecated for removal mean?

In Java, an API is marked **deprecated** when JDK or library developers advise against continuing to use that API. The API may still exist and run normally, but there may be a better, safer, or more suitable approach for the current design.

Since Java 9, the `@Deprecated` annotation has two important attributes:

- `since`: the version in which the API was first deprecated.
- `forRemoval`: indicates that the API has been marked for potential removal in a future release.

Example:

~~~java
@Deprecated(since = "17", forRemoval = true)
public void oldOperation() {
    // Legacy implementation
}
~~~

`forRemoval = true` means the API is marked as **deprecated for removal**. This is a stronger signal than ordinary deprecation: new code should not depend on that API, and existing code should have a replacement plan.

If you only write:

~~~java
@Deprecated(since = "17")
public void legacyOperation() {
}
~~~

then `forRemoval` defaults to `false`. The API is deprecated, but has not been marked for removal.

Two states to distinguish:

| State | Meaning | Recommended action |
|---|---|---|
| Deprecated | Discouraged from further use | Prefer the replacement API when modifying or extending code |
| Deprecated for removal | Marked for removal in the future | Plan migration and remove the dependency early |

Marking an API for removal does not mean it will disappear immediately in the very next version. The annotation does not specify a guaranteed removal date or version. Check the Javadoc and release notes of the target JDK version to learn the reason, replacement guidance, and current status.

## 2. The @Deprecated annotation and @deprecated Javadoc tag

The `@Deprecated` annotation provides metadata for the compiler, IDE, and analysis tools. The `@deprecated` block tag in Javadoc explains to API users why it should no longer be used and what to migrate to.

Example of a legacy API with a replacement path:

~~~java
/**
 * Returns the legacy identifier.
 *
 * @deprecated Use {@link #identifier()} instead.
 */
@Deprecated(since = "17", forRemoval = true)
public String oldIdentifier() {
    return identifier();
}

/** Returns the current identifier. */
public String identifier() {
    return "current";
}
~~~

A good documentation comment should state:

- Why the API was deprecated.
- The replacement API or approach, if one exists.
- Behavioral differences to watch out for when migrating.
- The version since which it was deprecated, if that information is helpful.

Not every API deprecated for removal has an equivalent replacement method. If there is no direct replacement, describe the design direction to move toward rather than suggesting a semantically incorrect substitute.

## 3. How the compiler distinguishes deprecation and removal warnings

The compiler can warn when source code uses deprecated APIs. For APIs marked `forRemoval = true`, the warning is typically classified as a **removal warning**.

Two useful lint groups:

| javac option | Purpose |
|---|---|
| `-Xlint:deprecation` | Displays warnings for using deprecated APIs |
| `-Xlint:removal` | Displays warnings for using APIs deprecated for removal |

Both can be enabled together:

~~~bash
javac --release 17 -Xlint:deprecation,removal -d build/classes src/demo/LegacyApiScan.java
~~~

The compiler may display output like:

~~~text
warning: [deprecation] getYear() in Date has been deprecated
warning: [removal] privilegedThreadFactory() in Executors has been deprecated and marked for removal
2 warnings
~~~

`-Xlint:removal` is useful because it helps distinguish APIs that are merely deprecated from APIs already marked for removal. You can use `-Werror` in the build if project policy requires warnings to fail the build; resolve warnings before enabling strict mode across the entire project.

The compiler only warns when source code is recompiled. A JAR compiled long ago may contain references to APIs about to be removed without producing any compile logs in the current build. This is why bytecode scanning with `jdeprscan` is needed.

## 4. What is jdeprscan?

`jdeprscan` is a command-line tool included with the JDK, used to analyze class files, class directories, or JARs and find usage of deprecated Java platform APIs.

The tool is especially useful when:

- An application has many modules, packages, or precompiled JARs.
- Source code is no longer complete or cannot be compiled immediately.
- You want to inventory deprecated APIs in artifacts before upgrading the JDK.
- You want to focus on APIs marked for removal.
- You want to compare the API list against a target Java version.

`jdeprscan` reads references in bytecode and matches them against the Java SE deprecated API catalog for the selected release. It does not replace the compiler, unit tests, or runtime testing.

An important point about scope: `jdeprscan` focuses on deprecated Java platform APIs known to the tool according to its release catalogue. It is not a general-purpose scanner for finding every `@Deprecated` annotation across all third-party libraries or internal project-defined APIs. Use the compiler, IDE, static analysis, or library-specific tools as well when you need to check those APIs.

## 5. Syntax and key options

General syntax:

~~~bash
jdeprscan [options] {dir|jar|class} ...
~~~

The input target can be:

- A root directory containing a package hierarchy and class files.
- A JAR.
- A class file.
- A fully qualified class name, such as `demo.LegacyApiScan`.

For nested classes, the class name can use `$`, such as `java.lang.Thread$State`.

Important options:

| Option | Function |
|---|---|
| `--for-removal` | Report only APIs deprecated for removal |
| `--release N` | Select the deprecated API catalog for Java SE release N |
| `--class-path PATH` | Specify where to find dependent classes to resolve references |
| `--list` or `-l` | List deprecated APIs in the catalog without scanning artifacts |
| `--verbose` or `-v` | Display more detailed processing information |
| `--version` | Print the short version of the tool |
| `--full-version` | Print the full version string |
| `--help`, `-h`, `-?` | Display help |

Examples of viewing help and version:

~~~bash
jdeprscan --help
jdeprscan --version
jdeprscan --full-version
~~~

Supported options and releases depend on the installed JDK. Check `jdeprscan --help` for the exact JDK you are using before adding commands to CI.

## 6. Finding only APIs deprecated for removal

This is the most direct feature for this topic:

~~~bash
jdeprscan --for-removal build/classes
~~~

This command scans bytecode in the `build/classes` directory, but only displays references to APIs marked for removal.

If you omit `--for-removal`:

~~~bash
jdeprscan build/classes
~~~

the tool displays both ordinarily deprecated APIs and APIs deprecated for removal. Report lines include the suffix `(forRemoval=true)` when a reference belongs to the removal group.

Example output format:

~~~text
Directory build/classes:
class demo/LegacyApiScan uses deprecated method java/util/concurrent/Executors::privilegedThreadFactory()Ljava/util/concurrent/ThreadFactory; (forRemoval=true)
~~~

The result line shows:

- `demo/LegacyApiScan` is the class using the API.
- `java/util/concurrent/Executors` is the JDK class containing the called API.
- `privilegedThreadFactory()` is the method being used.
- `(forRemoval=true)` confirms the API is marked for removal.

`jdeprscan` is a static reporting tool. Having results does not mean the application has already been executed or will definitely fail immediately; it points out dependencies that need review.

## 7. Selecting the API catalogue with --release

If the application runs on Java 17, you should check against the Java 17 catalog:

~~~bash
jdeprscan --release 17 build/classes
~~~

Filter only for-removal APIs in that release:

~~~bash
jdeprscan --for-removal --release 17 build/classes
~~~

If `--release` is omitted, the tool uses the current JDK's catalog. Specifying `--release` ensures the results reflect deprecated APIs for the target Java version rather than just the JDK running the tool.

The catalog can differ between releases. An API may be marked for removal in a newer Java version while an older version only records it as ordinarily deprecated. Therefore:

- Choose the release corresponding to the runtime your application supports.
- Re-run the scan when raising the target Java version.
- Do not compare results between two JDKs without explicitly specifying `--release`.
- Update the scanner JDK when you need to check a newer release that an older tool version does not yet support.

Example of listing for-removal APIs in Java 17:

~~~bash
jdeprscan --list --release 17 --for-removal
~~~

`--list` only prints the API catalog. Do not pass directories, classes, or JARs in this mode, because you are listing the catalogue rather than scanning an application.

## 8. Scanning JARs and dependent classes

Scan a JAR:

~~~bash
jdeprscan --for-removal --release 17 build/libs/application.jar
~~~

If bytecode references other classes that need to be resolved, add a classpath:

~~~bash
jdeprscan --for-removal --release 17 --class-path "lib/*" build/libs/application.jar
~~~

Scan a class by fully qualified name:

~~~bash
jdeprscan --for-removal --release 17 --class-path build/classes demo.LegacyApiScan
~~~

`--class-path` is the search path for dependent classes to resolve references. It does not mean every JAR on the classpath automatically becomes an input to be scanned. Pass each directory or JAR you want to analyze in the argument list.

On Windows, multiple paths in the classpath are typically separated by semicolons `;`. Linux and macOS use colons `:`.

In the help output of JDK 24.0.2, `jdeprscan` provides `--class-path` but does not list a `--module-path` option. When working with modular applications, check how artifacts and dependencies are organized according to the exact tool version; do not add an unsupported option.

## 9. Complete Java 17 example

The example below uses two JDK APIs to show the difference:

- `Date.getYear()` is an ordinarily deprecated API.
- `Executors.privilegedThreadFactory()` is marked deprecated for removal as of Java 17.

Structure:

~~~text
project/
  src/
    demo/
      LegacyApiScan.java
  build/
    classes/
~~~

File `src/demo/LegacyApiScan.java`:

~~~java
package demo;

import java.util.Date;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

/** Demonstrates ordinary deprecation and deprecation for removal. */
public final class LegacyApiScan {
    /**
     * Creates and reports legacy API values.
     *
     * @return whether a thread factory was created
     */
    public boolean run() {
        Date date = new Date(0L);
        int legacyYear = date.getYear();

        ThreadFactory factory = Executors.privilegedThreadFactory();

        System.out.println("legacyDateYear=" + legacyYear);
        System.out.println("factoryCreated=" + (factory != null));

        return factory != null;
    }

    /**
     * Runs the example.
     *
     * @param args command-line arguments (not used)
     */
    public static void main(String[] args) {
        new LegacyApiScan().run();
    }
}
~~~

Compile for Java 17 compatibility:

~~~bash
javac --release 17 -Xlint:deprecation,removal \
    -d build/classes src/demo/LegacyApiScan.java
~~~

The compiler reports two warning groups: one for `Date.getYear()` and one for `Executors.privilegedThreadFactory()` which is marked for removal.

Run the program:

~~~bash
java -cp build/classes demo.LegacyApiScan
~~~

Exact stdout:

~~~text
legacyDateYear=70
factoryCreated=true
~~~

Scan all deprecated APIs:

~~~bash
jdeprscan --release 17 build/classes
~~~

The output contains two references, one to `Date.getYear()` and one to `Executors.privilegedThreadFactory()`.

Scan only for-removal APIs:

~~~bash
jdeprscan --for-removal --release 17 build/classes
~~~

Key output line:

~~~text
class demo/LegacyApiScan uses deprecated method java/util/concurrent/Executors::privilegedThreadFactory()Ljava/util/concurrent/ThreadFactory; (forRemoval=true)
~~~

`Date.getYear()` no longer appears in the filtered output because it is deprecated but not marked for removal in the Java 17 catalogue. This is the distinction that the `--for-removal` option highlights.

## 10. Combining jdeprscan with javac in an upgrade workflow

A useful verification workflow has two layers:

1. `javac -Xlint:deprecation,removal` warns when compiling source code.
2. `jdeprscan --for-removal` checks compiled classes/JARs.

Example:

~~~bash
javac --release 17 -Xlint:deprecation,removal \
    -d build/classes src/demo/*.java

jdeprscan --for-removal --release 17 build/classes
~~~

In CI, you can run the scan on:

- The application's compiled class output directory.
- JARs produced by the project.
- Internal JARs packaged with the product.
- Dependency artifacts that the team is responsible for maintaining.

Keep the scan output as a build artifact to compare across releases. If new findings appear, create migration tasks for the relevant module or class.

You should not check only the main source code and conclude the entire product is clean. A precompiled dependency may continue calling a legacy API even if the application's own source code does not use it directly.

## 11. How to handle scan results

When `jdeprscan` reports a for-removal API:

1. Identify the class in the application that calls the API.
2. Look up the exact JDK API and read the Javadoc for the target release.
3. Check the deprecation reason and the recommended replacement.
4. Determine whether the dependency is direct or transitive.
5. Replace the API and verify behavioral changes.
6. Recompile, run tests, and re-scan the artifacts.

Do not replace APIs mechanically based solely on method names. Two similarly named APIs may have different semantics, permissions, security guarantees, or lifecycles.

For example, `Thread.stop()` is an unsafe API because it can terminate a thread while it is holding shared state. If code relies on forcefully stopping a thread, the fix is usually cooperative cancellation: set a cancellation flag, call `interrupt()` where appropriate, and let the running code check cancellation state at safe points.

For `Executors.privilegedThreadFactory()`, review why the code needed an access-control context and the application's current security design. Do not swap in a different factory if doing so alters permission assumptions or security boundaries.

After fixing, re-run both functional tests and the scan. The goal is to eliminate unsuitable dependencies while preserving correct behavior and security policy.

## 12. Limitations of jdeprscan

`jdeprscan` is a bytecode inventory tool, not complete proof that an application is compatible with a new JDK.

It has several limitations:

- Only reports deprecated APIs belonging to the Java catalog known to that scanner version.
- Does not automatically detect all deprecated APIs in third-party libraries or project-authored APIs.
- Cannot infer all calls constructed dynamically via reflection, string class names, scripts, or configuration.
- Does not verify business logic or actual runtime behavior of the application.
- Does not replace unit tests, integration tests, security testing, and testing on the target JDK.
- Only scans the artifacts passed to it; the classpath helps resolve dependencies and does not automatically request scanning every dependency.
- Results depend on the release catalogue and the JDK version of the tool.

Therefore, use `jdeprscan` alongside compiler lints, dependency checks, static analysis, and test suites. If a third-party library has its own APIs marked `@Deprecated(forRemoval=true)`, rely on its documentation, compiler warnings, or tools that understand that library's metadata.

## 13. Common mistakes and how to fix them

### No results even though source code uses deprecated APIs

`jdeprscan` scans bytecode, not `.java` files. Compile the source first, then scan the class directory or JAR.

### Forgetting the --for-removal option

Without `--for-removal`, the scanner may also report ordinarily deprecated APIs. If you only need the list of APIs marked for removal, add this option.

### Choosing the wrong --release

If the application runs on Java 17 but the scanner defaults to the JDK 24 catalogue, some APIs may have a different status. Select `--release 17` to check against the target platform.

### Scanner cannot resolve dependencies

Add the required dependencies to `--class-path`. Verify the correct directory or JAR and the OS-specific path separator.

### Thinking that --list scans the application

`--list` only lists deprecated APIs in the catalogue. To scan, omit `--list` and pass the directory, JAR, or class to check.

### Thinking a clean scan means no risky APIs remain

A clean scan only means no references belonging to the selected catalogue were found in the scanned artifacts. It does not prove there is no reflection, unscanned dependencies, deprecated third-party APIs, or other runtime issues.

## 14. Pre-JDK-upgrade checklist

- [ ] Identify the application's target runtime JDK.
- [ ] Use a `jdeprscan` version that supports the release to be checked.
- [ ] Compile source code with `-Xlint:deprecation,removal`.
- [ ] Scan the application's class directories and JARs.
- [ ] Use `--for-removal` to focus on APIs at risk of being removed.
- [ ] Use `--release` matching the target runtime.
- [ ] Check dependencies maintained by the team.
- [ ] Read Javadoc to find replacements and deprecation reasons.
- [ ] Re-evaluate behavioral changes and security policies when replacing APIs.
- [ ] Run unit tests, integration tests, and tests on the target JDK.
- [ ] Save scan results for comparison in CI and future releases.

`@Deprecated(forRemoval=true)` is a signal to plan a migration. `jdeprscan --for-removal` helps locate references to Java SE APIs carrying that signal in bytecode, while compiler lints catch them immediately when source code is compiled. Combining both approaches reduces the risk of depending on APIs that may be removed in future Java releases.
