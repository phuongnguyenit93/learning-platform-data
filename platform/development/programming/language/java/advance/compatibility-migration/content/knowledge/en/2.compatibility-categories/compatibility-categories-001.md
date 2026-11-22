# Source Compatibility: Recompiling Old Code with a New Version

When upgrading Java, libraries, or a build platform, a key question is: **does source code written for the old version still compile with the new version?** That capability is called *source compatibility*.

Source compatibility is especially critical in projects with many modules, multiple development teams, or libraries shared across many applications. A single API change can force dozens of projects to edit code at the same time. Conversely, if library maintainers preserve source compatibility, users can upgrade dependencies and recompile with minimal code edits.

## 1. What Is Source Compatibility?

A new version is source-compatible with an older version when previously valid source code can still be compiled in the new environment under equivalent compilation settings and with the necessary dependencies.

For example, an application uses version 1 of the `text-kit` library:

```java
String displayName = TextKit.normalize(input);
```

When upgrading to version 2, if `normalize(String)` still exists and keeps a compatible usage contract, the application can recompile without editing that line of code. If the method is removed, renamed, or changes parameter/return types so the call becomes invalid, the old source code is no longer compatible.

The key detail is that **source code is recompiled**. A pre-compiled program may still run with the new library even when its source code no longer compiles; that situation concerns binary compatibility, distinguished in the next section.

Source compatibility does not mean every old file will automatically run properly in every new environment. Compilation outcomes also depend on JDK version, Java language level, permitted platform APIs, dependencies, compiler options, annotation processors, and build configuration.

## 2. Distinguishing Source Compatibility from Other Compatibility Types

During an upgrade, distinguish at least three concepts:

| Compatibility Type | Question Answered | What Is Checked |
|---|---|---|
| Source compatibility | Does old source code compile with the new version? | Syntax, data types, APIs, overloads, dependencies, and compiler configuration |
| Binary compatibility | Does previously compiled bytecode link and run with the new library? | Class names, method names, descriptors, fields, constructors, and JVM-level linkage structures |
| Behavioral compatibility | Does the program continue producing the same outputs and effects as before? | Outputs, exceptions, processing order, defaults, execution timing, and side effects |

These three types are related but not interchangeable.

- Source code may compile cleanly while behavior changes because the new version altered default values or algorithms.
- Old bytecode may run against the new library while recompiling old source fails because a new overload makes a call ambiguous.
- Source code may be updated to compile against the new API while old bytecode still fails to link because a method descriptor changed.

Therefore, a complete migration plan must test recompilation, linkage of legacy binaries when binary compatibility must be maintained, and runtime behavior separately.

## 3. Factors Determining Source Compatibility

### 3.1. Java Language Version and Compiler

Each Java release adds syntax, language rules, and new capabilities. A newer compiler can usually compile code targeting older language levels, depending on build options.

For example, code can use `var` for local variables from Java 10 onward:

```java
var names = List.of("An", "Bình", "Chi");
```

If a project requires compilation at the Java 8 language level, this snippet is invalid. Conversely, standard Java 8 code can still be compiled by a newer JDK if the compiler is configured to accept the Java 8 release level and used APIs stay within Java 8's scope.

Thus, separate two questions:

1. Does the compiler understand the syntax and language rules used by the source code?
2. Does the source code call only APIs present in the target Java version?

Setting `source` and `target` alone may not fully answer the second question. When using a newer JDK to build bytecode for an older JDK, use `--release` if supported by the compiler. This option aligns language level, bytecode level, and platform APIs for the chosen release.

### 3.2. Public Library APIs

This is the most common cause of failures when recompiling an application after upgrading a dependency. External source code may depend on:

- Package, class, interface, enum, and annotation names.
- Public or protected constructors and methods.
- Method names, parameter counts, parameter order, and parameter types.
- Return types, generic types, and *type bounds*.
- Declared checked exceptions.
- Constants, fields, and access levels.
- Nested types, superclasses, and interfaces implemented by a class.

If the library removes or renames a member the application calls, the compiler cannot find it. If the library changes a return type, the call may no longer assign to a variable of the old type. Adding an overload can turn a previously valid call ambiguous.

Not every API change breaks compatibility. For instance, adding an unrelated method usually does not break existing call sites. Still, evaluate overload resolution rules and types at call sites as a whole rather than only checking whether the new API added or removed members.

### 3.3. Data Types, Generics, and Overloads

Java checks data types at compile time. Consequently, seemingly small changes in API declarations can affect callers.

Situations to watch out for:

- Changing a return type from `String` to `CharSequence` can prevent code assigning the result directly to a `String` variable from compiling.
- Changing a parameter from a specific type to a more general type can change which overload gets selected.
- Changing generic types can surface type errors uncaught by older compilers or alter the type received by callers.
- Adding an overload can render a previously valid call ambiguous.
- Narrowing visibility from `public` or `protected` to a more restricted level can block external access.

Example of an overload breaking source compilation of older code:

Version 1 of the library:

```java
public final class Messenger {
    private Messenger() {}

    public static void send(String message) {
        System.out.println(message);
    }
}
```

Application usage:

```java
Messenger.send(null);
```

At this point only one method matches, so the compiler picks `send(String)`. In version 2, the library adds:

```java
public static void send(Integer code) {
    System.out.println(code);
}
```

`null` is assignable to both `String` and `Integer`. Neither overload is a subtype of the other, so the compiler cannot choose a more specific method. `Messenger.send(null)` fails with *reference to send is ambiguous*.

This is a change that breaks source compatibility even though the library only added a method. If an old binary was compiled earlier, its call still references the exact descriptor of `send(String)`; since that method still exists, the binary can keep linking. This example shows why source compatibility and binary compatibility must be assessed separately.

The application can clarify intent via a cast:

```java
Messenger.send((String) null);
```

However, if a library has many users, keeping APIs free of ambiguity usually makes upgrades much smoother.

### 3.4. Checked Exceptions

Checked exceptions are part of the source-level contract. When a method starts declaring an additional checked exception, callers may need a `try-catch` block or a `throws` clause.

Version 1:

```java
public String read(String path) {
    return loadFromCache(path);
}
```

Calling code:

```java
String content = reader.read("config.txt");
```

Version 2:

```java
public String read(String path) throws IOException {
    return Files.readString(Path.of(path));
}
```

When recompiling, legacy calling code must handle `IOException`:

```java
try {
    String content = reader.read("config.txt");
} catch (IOException exception) {
    // Handle file-reading error appropriately for the application.
}
```

An important detail: checked exceptions are not part of the method descriptor the JVM uses for method linkage. Thus, adding `throws IOException` does not by itself alter the method descriptor, and older bytecode may still link. However, runtime behavior may have changed because the new exception can now escape in cases where it did not previously. That is why both source compatibility and behavioral compatibility must be verified.

### 3.5. JDK APIs and Runtime Environment

When upgrading the JDK, more than the compiler changes; platform APIs and bundled modules can change too. Some APIs become deprecated, removed, or no longer bundled with the JDK.

For example, since Java 11, several Java EE/CORBA technologies previously bundled inside the JDK were removed from the JDK. Old code referencing packages such as JAXB may fail to compile if the project lacks corresponding dependencies. In some cases, you can continue using that API by adding a suitable standalone library; in other cases, moving to a replacement API is required.

Do not conclude a package no longer exists merely because the newer JDK no longer bundles it. Check the actual classpath or module path and project-provided dependencies.

### 3.6. Dependencies, Annotation Processors, and Generated Code

Application source code rarely depends only on the JDK. A single upgrade can simultaneously change:

- Direct libraries and *transitive dependencies*.
- Plugin or build tool versions.
- Annotation processors, compiler plugins, and auto-generated code.
- Module descriptors, classpath, or module path.
- Warning/lint checks and rules treating warnings as errors.

For instance, a newer annotation processor may generate different method names or class structures than the prior version. Application code stays untouched, yet recompilation fails because generated code changed. Similarly, upgrading one library can pull in a transitive dependency version incompatible with the rest of the application.

When investigating errors, determine the exact version the build resolved. Declaring a version directly in a config file is not sufficient proof that the dependency used at compile time is the intended version.

## 4. Example: API Changes Breaking Old Source Compilation

Suppose version 1 of a library has this API:

```java
public final class NameFormatter {
    private NameFormatter() {}

    public static String normalize(String value) {
        return value.trim();
    }
}
```

Application calling the API:

```java
String name = NameFormatter.normalize(rawName);
```

In version 2, the maintainers rename the method:

```java
public final class NameFormatter {
    private NameFormatter() {}

    public static String canonicalize(String value) {
        return value.trim();
    }
}
```

When compiling the old application against version 2, the compiler reports it cannot find `normalize(String)`. This is a source compatibility error: old source code still references an API that no longer exists.

To give users transition time, the library can retain the old method as an adapter:

```java
public final class NameFormatter {
    private NameFormatter() {}

    public static String canonicalize(String value) {
        return value.trim();
    }

    @Deprecated(since = "2.0", forRemoval = true)
    public static String normalize(String value) {
        return canonicalize(value);
    }
}
```

Old code continues compiling while the old method forwards to the new API. `@Deprecated` informs users that they should migrate; `forRemoval = true` indicates the API may be removed in a future release. When actually removing it, library maintainers should clearly announce the version and provide migration guidance.

An adapter is appropriate only when it preserves the semantics and contract of the old API. If the old behavior is no longer safe or cannot be emulated, clearly document the change and offer an alternative migration path.

## 5. Configuring Compilation to Verify the Exact Target Version

A compatibility check is meaningful only when the compiler and target APIs are configured accurately. Using a new JDK does not mean the application has been verified for all older Java versions.

### 5.1. Using `javac --release`

On JDK 9 and newer, `--release` specifies the target Java release:

```bash
javac --release 11 -d out src/com/example/App.java
```

That command instructs the compiler to compile code per Java 11 and restrict platform APIs to that release. If sources use newer syntax or call APIs introduced in a newer JDK, the compiler reports an error.

`--release` controls Java platform APIs. It does not automatically verify third-party library compatibility; dependencies must still have versions compatible with the target release.

### 5.2. Maven Configuration

With Maven Compiler Plugin, declare the release in `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Verify the Maven Compiler Plugin version in use and the actual JDK running Maven. A property configuration may not take effect as expected if the plugin is too old or the build overrides compiler options elsewhere.

### 5.3. Gradle Configuration

With the Gradle Java plugin, configure a toolchain and set release on compile tasks:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

The toolchain selects the JDK running the compiler. `options.release` sets the Java level and platform APIs that source code may use. Both settings address separate aspects of the compilation environment.

Setting only `sourceCompatibility` and `targetCompatibility` allows the compiler to emit bytecode for an older level while still seeing APIs from the newer JDK running the compiler. Code can then compile cleanly yet fail at runtime on an older JDK due to calling APIs absent in the target environment. `options.release` prevents this for Java platform APIs.

## 6. Source Compatibility Testing Workflow During Migration

A controlled workflow helps pinpoint which change actually prevents old source code from compiling.

### Step 1: Record the Baseline

Before upgrading, save the working commit and record:

- The build JDK and runtime JDK.
- Target Java source/API level.
- Gradle or Maven version and related plugins.
- Direct dependencies and resolved versions of transitive dependencies.
- Active compiler options, annotation processors, and build profiles.

The baseline enables reproducing failures and identifying exactly what changed.

### Step 2: Define the Target Environment

Lock the compiler JDK, supported Java release, actual runtime, and dependency versions targeted for upgrade. Avoid changing many versions at once without clear reason, as root-cause attribution becomes difficult when errors appear.

### Step 3: Recompile Unmodified Source Code

Keep sources at the baseline and switch the environment to the new configuration. Run a clean compile to surface all errors completely rather than incrementally building a single module with cached outputs.

Example with Gradle:

```bash
./gradlew clean compileJava
```

In multi-module projects, ensure all relevant modules compile. One module may compile independently yet fail when used alongside another module due to mismatched APIs or dependencies.

### Step 4: Classify Compiler Errors

Read the first error along the dependency chain and group errors by cause:

| Error Category | Common Symptoms | Investigation Direction |
|---|---|---|
| Removed or renamed API | `cannot find symbol`, package or class not found | Compare old and new APIs; find replacement or adapter |
| Type change | `incompatible types`, generic or conversion errors | Check parameter types, return types, and generic bounds |
| Ambiguous overload | `reference to ... is ambiguous` | Inspect new overloads and expression types at call sites |
| Checked exception | `unreported exception` | Check `throws` declarations and add proper error handling |
| Missing JDK API | Platform package or method not found | Check `--release`, target JDK, and API-providing dependencies |
| Generated code | Errors inside generated sources or processor-created symbols | Check annotation processor version and configuration |
| Dependency or module | Artifact cannot resolve, package not exported/read | Check dependency graph, classpath, and module path |

Do not apply bulk fixes from error messages without understanding the root cause. One upstream error can cascade into dozens of downstream errors; fixing the root cause first often clears most remaining errors.

### Step 5: Choose Fixes According to Contract

For each error, determine which codebase owns the changed contract:

- If the application calls a changed API, update the call site to the new API and verify business semantics.
- If the library is developed by your own team, consider keeping a compatible adapter or overload during a transition phase.
- If a transitive dependency upgraded unexpectedly, review dependency constraints or pick a compatible version.
- If the error stems from the target Java level, confirm runtime requirements before changing compiler release.
- If an old API was removed for security or design reasons, do not restore it mechanically; adopt the supported replacement API.

Do not add `catch (Exception)` or arbitrary casts just to silence compiler errors. Fixes must preserve contracts and handle errors properly for business requirements.

### Step 6: Recompile Everything and Run Tests

After fixing, run clean builds across all relevant modules, followed by unit tests, integration tests, and application-specific tests. Test success paths, error paths, boundary data, and behavior relying on JDK or library defaults.

If binary compatibility must be maintained, take a consumer already compiled with the old library version and verify linking/running it against the new library. Clean compilation from source does not substitute for that check.

### Step 7: Record Migration Outcomes

Record JDK version, release level, upgraded dependencies, replaced APIs, confirmed behavioral changes, and remaining limitations. This helps other modules or teams perform the same upgrade consistently.

## 7. Common Mistakes

### Running Only Incremental Builds

Incremental builds may reuse outputs or caches from previous runs. They do not always force every source file to recompile with the new compiler and dependencies. When verifying migrations, run clean builds in a defined environment.

### Confusing `source`/`target` with Target APIs

Setting a low bytecode target does not automatically restrict all APIs visible to the compiler. Use `--release` or equivalent configuration to enforce platform APIs.

### Assuming Clean Compilation Means Full Compatibility

The compiler cannot prove the program still produces identical outputs, throws no runtime errors, or maintains performance. Those require behavioral tests and tests on the real runtime environment.

### Checking Only Direct Dependencies

A transitive dependency can shift when upgrading another library. Inspect the resolved dependency graph and check the compile task's classpath/module path.

### Fixing Errors with Casts or Broad Exception Catching

Casts can mask data-type changes; overly broad exception catches can turn real failures into ambiguous states. Understand the new contract first and choose proper handling.

### Ignoring Deprecation Warnings

Deprecation warnings often signal future removal. Identify replacement APIs and plan migration before the next release deletes them.

## 8. Upgrade Checklist

Before concluding old source code is compatible with the new version, confirm:

- [ ] Identified compiler JDK and target runtime JDK.
- [ ] Configured the right Java release level and platform APIs to support.
- [ ] Recorded build tool, plugin, and resolved dependency versions.
- [ ] Ran a clean compile on unmodified source code before editing sources.
- [ ] Compiled all relevant modules and auto-generated sources.
- [ ] Resolved API, data-type, overload, checked-exception, and module/classpath errors.
- [ ] Audited deprecation warnings and potentially removable APIs.
- [ ] Executed unit tests, integration tests, and behavioral tests on the target runtime.
- [ ] Tested binary compatibility separately if previously compiled binaries must be supported.
- [ ] Documented changes and remaining limitations.

## 9. Conclusion

Source compatibility answers whether old source code can be recompiled in a new environment. Outcomes depend simultaneously on the Java language, JDK APIs, library APIs, data types, overloads, checked exceptions, dependencies, and build configuration.

During migration, recompile unmodified source code in the defined target environment, classify errors by cause, fix according to API contracts, and test after compilation. This establishes compatibility at the source level; binary compatibility and behavioral compatibility still require separate verification whenever system requirements encompass those dimensions.
