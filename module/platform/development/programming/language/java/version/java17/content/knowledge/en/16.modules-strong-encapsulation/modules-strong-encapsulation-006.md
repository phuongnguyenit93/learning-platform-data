# Detecting Internal Dependencies with jdeps --jdk-internals in Java 17

**Topic:** Java 17 → Modules and Strong Encapsulation  
**Focus:** Using the `jdeps` tool with the `--jdk-internals` option to find classes in an application or library that depend on JDK internal APIs; reading the output, understanding the limits of static analysis, and planning replacements with supported APIs.

Java 17 strongly encapsulates JDK internal components under the module system. Some classes or libraries that previously accessed internal packages may no longer work when running on Java 17. To find these dependencies before release, the JDK provides the `jdeps` tool. The `--jdk-internals` option (short form `-jdkinternals`) searches for class-level dependencies on JDK internal APIs and may suggest replacements.

`jdeps` analyzes compiled bytecode; it does not directly analyze `.java` source files, nor does it execute the application. Therefore, it is an important check during a JDK upgrade, though it does not replace testing the application on Java 17.

## 1. What Are JDK Internal APIs?

The JDK contains many classes and packages intended solely for implementing the platform itself. Some classes were previously used directly by applications or third-party libraries even though they are not part of publicly supported Java SE APIs.

Such dependencies carry risk because:

- Class names, methods, fields, or internal structures may change across JDK releases.
- Packages may be encapsulated in modules and no longer exported to application code.
- Components may be removed as the JDK evolves.
- Internal behavior has no compatibility guarantee like public APIs.
- An application may compile on one JDK yet fail to link or run on another JDK.

Not every package prefixed with `com.sun` or `sun` can be classified merely by looking at its name. Certain special APIs are exported to support the ecosystem, while many packages under the same namespace remain internal. Use `jdeps` and JDK documentation to verify specific dependencies rather than judging solely from package prefixes.

### 1.1. Strong encapsulation in Java 17

The Java Platform Module System was introduced in Java 9. Modules can export packages allowed for public access; unexported packages are encapsulated from external code.

In Java 17, JEP 403 completes **strongly encapsulating JDK internal components by default**. Some critical APIs, such as `sun.misc.Unsafe`, remain exceptions exported in module `jdk.unsupported`, but that does not make them stable, supported Java SE APIs.

Therefore, distinguish carefully:

| Concept | Meaning |
| --- | --- |
| Public, supported API | Has an API contract and compatibility guarantees under platform policy. |
| Encapsulated internal API | Code outside the module cannot access that package through normal means. |
| Internal API still exported as an exception | May remain accessible in some configurations, but lacks compatibility commitments of public APIs. |
| Removed API | No longer present in the target JDK; dependency can cause linkage or runtime errors. |

`jdeps --jdk-internals` helps locate bytecode references to the internal API group. It does not guarantee that every reference will immediately fail on Java 17; some exception APIs remain accessible. Reported results still deserve attention because depending on JDK implementation details is an upgrade risk.

## 2. What Is the jdeps Tool?

`jdeps` is the Java Dependency Analysis Tool included with the JDK. It analyzes dependencies of class files, class directories, or JARs at the package or class level.

Common input forms:

- A `.class` file.
- A directory containing compiled class files.
- A JAR file.
- A group of JARs or an application's class path.
- Modules or a module path when analyzing modular applications.

The `--jdk-internals` option instructs `jdeps` to find **class-level dependencies** on JDK internal APIs. Output typically shows:

1. Which artifact or module contains the analyzed class.
2. Which application class references the internal class.
3. The name of the referenced internal API.
4. The JDK module containing that package, if determinable.
5. A table of suggested replacements when the JDK has corresponding information.

`jdeps` is located in the JDK's `bin` directory. If `JAVA_HOME` points to JDK 17 and `bin` is in `PATH`, you can run:

~~~shell
jdeps --version
jdeps --help
~~~

On Windows PowerShell, if the JDK is not yet in `PATH`:

~~~powershell
& "$env:JAVA_HOME\bin\jdeps.exe" --version
~~~

Verify which JDK the running tool belongs to. When analyzing an application targeting Java 17, use JDK 17's `jdeps` so results reflect the target version's modules and APIs.

## 3. Basic Syntax of --jdk-internals

Common syntax:

~~~shell
jdeps --jdk-internals path
~~~

Examples:

~~~shell
jdeps --jdk-internals build/classes
jdeps --jdk-internals build/libs/application.jar
jdeps --jdk-internals target/application.jar
~~~

The `--jdk-internals` option has a short alias `-jdkinternals`:

~~~shell
jdeps -jdkinternals build/libs/application.jar
~~~

In new scripts, prefer the long name `--jdk-internals` for readability and clear intent.

According to JDK 17 documentation:

- This option finds class-level dependencies on JDK internal APIs.
- By default, the tool analyzes classes in the input files and classes specified via `--class-path`, unless restricted using `-include`.
- This option cannot be combined with `-p`, `-e`, and `-s`.

`--jdk-internals` is not a code-fixing command. It detects and reports dependencies so the development team can decide how to replace them.

## 4. Example: Finding References to an Internal API

To demonstrate the tool, you can create a class referencing `sun.misc.Unsafe`. This is a special internal API still exported in JDK 17 via module `jdk.unsupported`. It is **not a choice to use in new application code**; the example simply creates a dependency observable by `jdeps`.

Create file `src/UnsafeReference.java`:

~~~java
import sun.misc.Unsafe;

public final class UnsafeReference {
    private static Unsafe unsafe;
}
~~~

Compile with JDK 17:

~~~shell
javac -d out src/UnsafeReference.java
~~~

The compiler may emit a warning that `Unsafe` is a JDK proprietary internal API. Because `sun.misc` is exported via `jdk.unsupported`, this reference example can compile on JDK 17 without opening another package via extra flags.

Run the analysis:

~~~shell
jdeps --jdk-internals out
~~~

Illustrative output looks like:

~~~text
out -> jdk.unsupported
   UnsafeReference -> sun.misc.Unsafe JDK internal API (jdk.unsupported)

Warning: JDK internal APIs are unsupported and private to JDK implementation
that are subject to be removed or changed incompatibly and could break your
application.
~~~

Artifact names, classes, and warning formatting may vary by input and JDK build. The items to read are:

- `UnsafeReference` is the application class with the internal reference.
- `sun.misc.Unsafe` is the detected internal API.
- `jdk.unsupported` is the module containing this package.

Such a finding is still worth addressing even though the package is currently exported. Internal APIs lack compatibility guarantees equivalent to public APIs; an application working today does not guarantee the methods it uses will remain supported in future JDK versions.

## 5. Reading the Suggested Replacement Table

When replacement guidance is available, `jdeps` may print a table:

~~~text
JDK Internal API                 Suggested Replacement
----------------                 ---------------------
<internal API>                   <replacement or migration reference>
~~~

This table is an **investigation hint**, not an automatic patch:

- Some internal APIs have a direct standard replacement API.
- Some APIs require changing the design or data-access approach.
- Some APIs have no single equivalent replacement.
- A suggestion may point to a JEP or migration guide rather than a replacement class name.

Do not just swap the import name and assume migration is finished. Compare behavior, synchronization model, performance, access permissions, and edge cases of the old API against the standard API.

### 5.1. Example with Unsafe

`sun.misc.Unsafe` remains a notable exception in Java 17, but its methods are internal APIs, not long-term supported public contracts.

If code uses `Unsafe` for reading, writing, or performing atomic operations on fields/arrays, `java.lang.invoke.VarHandle` can be evaluated. `VarHandle` is a standard API since Java 9, allowing variable access with well-defined memory modes and atomic operations.

Example of a counter using VarHandle:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class Counter {
    private volatile int value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public int incrementAndGet() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }

    public int get() {
        return (int) VALUE.getVolatile(this);
    }
}
~~~

This is a suitable replacement for a category of field access/atomic operations with corresponding semantics. It is **not a replacement for every feature of Unsafe**. If code uses raw memory allocation, native addresses, or other internal operations, evaluate each feature individually and pick appropriate supported APIs.

## 6. Analyzing External JARs and Dependencies

An application typically depends on many libraries. Scanning only the application's class files can miss internal references inside dependencies.

Use `--class-path` to include libraries to analyze on the class path:

~~~shell
jdeps --jdk-internals --class-path "lib/*" build/libs/application.jar
~~~

In this example:

- `build/libs/application.jar` is the application artifact.
- `lib/*` are the dependency JARs placed on the class path.
- `--jdk-internals` asks to find references to internal APIs in the analyzed classes.

On Windows, the separator for multiple class path entries is a semicolon (`;`). When using wildcards like `lib/*`, wrap the path in double quotes so the shell does not expand the wildcard differently.

If you need to analyze dependencies recursively, you can use `--recursive`:

~~~shell
jdeps --jdk-internals --recursive --class-path "lib/*" build/libs/application.jar
~~~

Which classes are analyzed depends on the paths and options passed. Supply the exact runtime dependencies in the command; `jdeps` cannot find a library outside the provided inputs and analysis paths.

### 6.1. Scanning build directories

If the build places class files in a directory:

~~~shell
jdeps --jdk-internals build/classes/java/main
~~~

With Maven, the classes directory is typically:

~~~shell
jdeps --jdk-internals target/classes
~~~

With Gradle, the classes directory is typically:

~~~shell
jdeps --jdk-internals build/classes/java/main
~~~

Actual paths depend on build configuration. If there are multiple source sets, modules, or output directories, scan each relevant artifact.

### 6.2. Multi-release JARs

A multi-release JAR can contain different versions of classes under directories like `META-INF/versions/17`. When analyzing this type of JAR, specify the release to inspect:

~~~shell
jdeps --jdk-internals --multi-release 17 app-mr.jar
~~~

`--multi-release` accepts an integer 9 or greater, or `base`. Selecting the target version ensures `jdeps` analyzes the bytecode used for that runtime rather than relying solely on the base JAR contents.

## 7. Modular Applications and the Module Path

A Java 17 application can be packaged as named modules. When analyzing, supply the appropriate module path and root module.

Example command form:

~~~shell
jdeps --jdk-internals --module-path "mods;lib" --module com.example.app
~~~

Here `com.example.app` is the application's module name; `mods` and `lib` are locations containing modules or corresponding dependencies. Adjust path separators for the operating system.

If analyzing a JAR on the class path, use `--class-path` instead of assuming it is a named module. Choose the artifact's actual packaging model.

A modular application can declare `requires` on a module containing internal packages, yet reading the module does not mean every package of that module is exported. Module readability and package accessibility are two separate conditions.

## 8. What Does jdeps Detect and What Does It Miss?

`jdeps` is a **static analysis tool**. It analyzes dependency references recognizable from bytecode. This is very useful, but the output cannot be treated as an exhaustive list of every way an application might touch JDK internals.

### 8.1. Dependencies commonly detected

- Bytecode with type references to internal classes.
- Field or method signatures containing internal types.
- Application classes invoking or using an internal API in a way that creates a class-file dependency.
- Classes in dependency libraries with direct references to JDK internal APIs, if those dependencies are within the analyzed scope.

### 8.2. Cases that may be missed

`jdeps` does not execute the application to observe all execution paths. Thus, it may miss:

- Reflection accessing classes or members by string names.
- `Class.forName` with dynamically constructed class names.
- Custom class loading or class names read from external configuration.
- Native code/JNI calling into JDK components.
- Dynamically loaded dependencies or service providers outside the class files analyzed by the command.
- Behavior occurring only on a rare runtime branch.

For example, the snippet:

~~~java
Class<?> type = Class.forName(configuredClassName);
~~~

does not necessarily emit a direct bytecode reference to the class named by the configuration string. If the configured value points to an internal class, `jdeps` may not recognize that dependency.

Therefore, a warning-free result only means **no internal references were detected within the analyzed scope**, not absolute proof that the application uses no internal APIs at all.

### 8.3. Combining verification sources

For higher confidence:

1. Scan application class files and JARs with `jdeps`.
2. Scan third-party libraries on the runtime class path/module path.
3. Audit reflection configuration, service loading, and native integration.
4. Run integration tests on JDK 17 with the default module configuration.
5. Inspect warning logs and access errors at runtime.
6. Review the dependency tree to identify which library brings internal APIs into the application.

## 9. Why Can jdeps and Runtime Give Different Results?

There are three different concepts:

| Tool/mechanism | Question answered |
| --- | --- |
| `jdeps --jdk-internals` | Does bytecode in the analyzed scope have class-level references to internal APIs? |
| Module system/runtime | Are modules and packages permitted to be accessed under the running configuration? |
| Integration tests | Do real application flows work properly on the target runtime? |

An internal API may be reported by `jdeps` yet still be accessible in JDK 17 because that package belongs to an exported exception group. Conversely, an application may encounter `InaccessibleObjectException` due to reflection on an unopened member even when `jdeps` reports no direct references.

Do not use the result of one tool to completely replace the other two checks.

## 10. Distinguishing --add-exports and --add-opens

In some legacy migration scenarios, an application may need temporary access while awaiting dependency replacement. The module system provides two options with different scopes:

| Option | Purpose | Typical usage |
| --- | --- | --- |
| `--add-exports module/package=target` | Exports a specific package so code in the target module can access public types in that package. | When code needs access to public types in an otherwise unexported package. |
| `--add-opens module/package=target` | Opens a package for deep reflection into non-public members. | When a reflection library needs access to non-public fields/methods/constructors. |

Syntactic examples:

~~~shell
java --add-exports java.base/some.internal.package=ALL-UNNAMED -jar app.jar
java --add-opens java.base/some.internal.package=ALL-UNNAMED -jar app.jar
~~~

`some.internal.package` is only an illustrative name; replace it with the actual package and module. Do not copy these commands without identifying the exact cause of access.

Both options are intentional access-granting mechanisms; they **do not turn internal APIs into supported APIs**. Nor do they stop `jdeps` from reporting the dependency. Use narrow open/export permissions during the transition period and prioritize removing internal dependencies from the long-term architecture.

## 11. Workflow for Acting on jdeps Output

When the tool reports an internal dependency, handle it step by step:

### Step 1: Identify the class owning the dependency

Read the report line to see whether an application class or a library class references the internal API. If the dependency comes from a third-party library, note the artifact and library version.

### Step 2: Identify the API and its containing module

Find the reported package, class, and module. Check that API:

- Does it still exist in JDK 17 or has it been removed?
- Is it exported or encapsulated?
- Is there a standard replacement API?
- Are there hints in JDK documentation or related JEPs?

### Step 3: Choose the replacement direction

Prefer public Java SE APIs or an external library with a clear support contract. If no direct replacement exists, re-evaluate the implementation rather than keeping an internal dependency merely because runtime flags can open the package.

### Step 4: Update third-party dependencies

If the reference resides in a library:

- Look for a newer version that has removed the internal API usage.
- Check vendor release notes.
- If no fix exists yet, evaluate alternative libraries or restrict usage scope.
- Do not patch bytecode or copy JDK internal classes into the application to bypass the module system.

### Step 5: Re-run analysis and tests

After replacing:

~~~shell
jdeps --jdk-internals build/libs/application.jar
~~~

Continue running unit tests, integration tests, and smoke tests on JDK 17. The goal is having no remaining internal dependencies beyond justified accepted exceptions, while ensuring application behavior remains correct.

## 12. Integrating into Build and CI Workflows

`jdeps` can be added as a verification step prior to packaging or release. Example shell script:

~~~shell
#!/usr/bin/env sh
set -eu

APP_JAR="build/libs/application.jar"
DEPS_DIR="build/dependencies"

jdeps --jdk-internals \
  --class-path "$DEPS_DIR/*" \
  "$APP_JAR"
~~~

The command prints results for developers to review. If CI needs to fail on internal policy criteria, write a custom check parsing the output or use an appropriate build plugin/integration. Do not assume every version of `jdeps` provides a universal flag like `--fail-on-internal`; define CI policy and output parsing explicitly.

A practical pipeline might look like:

~~~text
Compile application and dependencies
                |
                v
        Run jdeps --jdk-internals
                |
                v
       Review reported dependencies
                |
        +-------+-------+
        |               |
      Found           None found
        |               |
        v               v
 Upgrade/replace    Continue tests
        |               |
        v               v
    Re-run jdeps   Integration tests
        |               |
        +-------+-------+
                |
                v
       Package and release
~~~

Save analysis outputs across builds so newly introduced internal dependencies from code changes or library upgrades are easy to spot.

## 13. Related Options

| Option | Purpose |
| --- | --- |
| `--jdk-internals` | Finds dependencies on JDK internal APIs. |
| `--class-path path` | Specifies where to find class files and libraries on the class path. |
| `--module-path path` | Specifies where to find modules. |
| `--recursive` | Recursively traverses runtime dependencies. |
| `--multi-release version` | Selects the class version when processing multi-release JARs. |
| `--include regex` | Restricts analyzed input classes by regular expression. |
| `--version` | Prints tool version. |
| `--help` | Prints usage help. |

Some combinations are restricted. Specifically, Java 17 documentation states `--jdk-internals` cannot be used with `-p`, `-e`, or `-s`. When filtering is needed, check syntax and restrictions for the exact JDK version in use.

## 14. Common Mistakes

| Mistake | Why it fails | Resolution |
| --- | --- | --- |
| Running `jdeps` on `.java` files | The tool analyzes compiled class files. | Compile first, then scan the output directory or JAR. |
| Scanning only the application JAR | Third-party dependencies may contain internal APIs. | Provide class path/module path and scan runtime libraries. |
| Using a JDK other than the target version | Module/API lists may differ. | Use `jdeps` from JDK 17 or specify the appropriate system image. |
| Thinking empty output proves no internal APIs are used | Static analysis misses dynamic reflection/class loading. | Check configurations, runtime tests, and dependency trees. |
| Assuming all `sun.*` packages behave identically | Some exception packages are exported; other internal packages are closed. | Rely on analysis output and module documentation. |
| Seeing `sun.misc.Unsafe` is still accessible and treating it as stable API | It is an internal exception lacking Java SE commitments. | Evaluate standard replacements per operation. |
| Using `--add-opens` to fix every module error | That option is for deep reflection, not every export/type-access issue. | Distinguish `--add-exports` from `--add-opens`. |
| Treating replacement hints as automatic fixes | Hints may point to docs/JEPs and are not full equivalents. | Verify semantics and test after migration. |
| Leaving broad package opens as a long-term solution | Increases coupling to internal details and weakens encapsulation. | Scope temporary permissions and remove the dependency. |
| Running jdeps only once before release | New dependencies may enter in later builds. | Integrate scanning into regular CI workflows. |

## 15. Example Workflow on a JAR

Suppose the application has been packaged:

~~~text
project/
  build/
    libs/
      application.jar
  lib/
    dependency-a.jar
    dependency-b.jar
~~~

First, verify the JDK:

~~~shell
java --version
jdeps --version
~~~

Scan the application along with libraries:

~~~shell
jdeps --jdk-internals \
  --class-path "lib/*" \
  build/libs/application.jar
~~~

If dependencies are reported, record the referencing class, internal package, and module containing that API. Then verify whether the source is application code or an external library.

After updating code or upgrading libraries, rebuild and re-run the exact same command. A clean result is a positive signal for statically recognized dependencies, though you still must run the application and tests on JDK 17 to check dynamic accesses.

## 16. Frequently Asked Questions

**Does `jdeps --jdk-internals` analyze source code?**  
No. It analyzes bytecode in class files, class directories, or JARs. Compile before running the tool.

**Is `--jdk-internals` the only flag name?**  
No. Java 17 also supports the alias `-jdkinternals`. The long name is more readable in scripts.

**Can the tool find internal APIs in dependencies?**  
Yes, if dependency classes are included in the inputs or supplied class path/module path and fall within the analysis scope. Supply the proper runtime dependencies.

**Does no output mean the application definitely uses no internal APIs?**  
No. Reflection, dynamically constructed class names, native code, and dependencies outside the scan scope may not be detected.

**Why is `sun.misc.Unsafe` still accessible in Java 17 yet still triggers a warning?**  
It is an exception exported via `jdk.unsupported`. It remains an internal API without compatibility guarantees like standard APIs.

**Does `jdeps` fix dependencies automatically?**  
No. It only reports dependencies and may offer suggestions. Replacements must be implemented and tested by the development team.

**Can `--add-exports` or `--add-opens` replace migration?**  
They can grant narrow access to aid transition in some cases, but they do not turn internal APIs into stable APIs. Prioritize removing the dependency.

**Should `jdeps` be run on every build?**  
Integrate it into CI or key dependency verification milestones to catch new dependencies before release.

## 17. Official References

- [The jdeps Command — Java SE 17 Tool Specifications](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): syntax, `--jdk-internals`, class path, module path, multi-release JARs, and option combination limits.
- [Preparing for Migration — Oracle JDK 17 Migration Guide](https://docs.oracle.com/en/java/javase/17/migrate/preparing-migration.html): guidance on running `jdeps` on applications and caveats on static analysis limits.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): rationale and scope of strongly encapsulating JDK internal components.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): module mechanism, package exports, and cross-module access rules.
- [Java SE 17 API — java.lang.invoke.VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): standard API for variable access and atomic operations with defined memory semantics.
- [Java SE 17 API — Module jdk.jdeps](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jdeps/module-summary.html): module containing dependency analysis tools such as `jdeps`.

**Practical rule:** Run `jdeps --jdk-internals` on your application's bytecode and relevant dependencies to find references to JDK internal APIs. Read the output by class, package, and module; replace them with suitable public APIs; then re-run analysis and test on Java 17. Treat `jdeps` as an essential static dependency detection tool, not sole proof of runtime compatibility.
