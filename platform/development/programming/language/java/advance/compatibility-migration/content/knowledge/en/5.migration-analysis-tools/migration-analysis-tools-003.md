# Finding Internal APIs with `jdeps --jdk-internals`

When upgrading Java, a major source of risk is an application or library using JDK internal APIs. These APIs may have existed and worked for years, yet they are not part of the public Java SE contract that the vendor commits to keeping compatible across every version. When the JDK changes module packaging, package encapsulation, or enforces strong encapsulation, such dependencies can produce warnings, access errors, or stop working.

`jdeps` is a static dependency analysis tool provided in the JDK. The `--jdk-internals` option helps find bytecode references to JDK internal APIs. This is a useful step during inventory and migration, especially before upgrading from older Java releases to Java 9 and newer or when preparing to adopt a new feature release.

## 1. What Are JDK Internal APIs?

The JDK provides packages and classes as the standard Java SE API. This is the surface applications can rely on under the platform's specification and compatibility policy. Alongside it, the JDK also contains APIs serving the JVM's own implementation, JDK tools, or internal components of the platform libraries.

Internal APIs typically have one or more characteristics:

- Not documented as public Java SE APIs.
- May change or be removed between feature releases.
- May reside in packages/modules not exported to regular applications.
- May be retained only for compatibility with certain legacy tools or components.
- May have required access-opening flags in some earlier JDK versions, then became more strongly encapsulated in newer versions.

Examples of APIs previously used by many applications include `sun.misc.Unsafe`, `sun.misc.BASE64Encoder`, `sun.reflect.Reflection`, or classes in other internal packages. The exact list depends on the JDK and version being analyzed.

Do not conclude that every package starting with `com.sun` or `sun` has the same status. Some APIs have historical package names yet remain documented APIs in a specific JDK module; conversely, some internal APIs are not easy to spot from the package name alone. Use the JDK's analysis output and official documentation to determine each API's status.

## 2. Why Do Internal APIs Pose Migration Risks?

Applications using internal APIs depend on an implementation detail of the JDK. The JDK vendor may change that detail when fixing bugs, improving security, changing architecture, or removing legacy components.

Risks typically appear in the following forms:

1. **Fails to compile:** the internal class or method no longer exists or is no longer accessible.
2. **Fails to link at runtime:** bytecode references a removed class or method, leading to linkage errors such as `NoClassDefFoundError`, `NoSuchMethodError`, or related errors.
3. **Inaccessible due to module encapsulation:** the package is not exported/opened to the calling module, which can trigger `IllegalAccessError` or reflective access errors.
4. **Changed behavior:** the API still exists, yet its behavior, limits, thread safety, or execution details changed.
5. **Hard to switch vendors or runtimes:** the application relies on behavior present only in a specific build, configuration, or implementation.

Starting in Java 9, the Java Platform Module System (JPMS) established clear module boundaries. JEP 260 set the direction for encapsulating most internal APIs. JEP 403, applied in Java 17, completed strong encapsulation of most JDK internals. Some packages are kept in the `jdk.unsupported` module to support APIs like `sun.misc.Unsafe`, yet that existence does not make them stable Java SE APIs.

Therefore, an application running on an old JDK does not prove it will run on a new JDK. Dependencies must be found and addressed before switching production environments.

## 3. What Does `jdeps` Do?

`jdeps` analyzes dependencies at the class/package/module level based on Java bytecode. When `--jdk-internals` is enabled, the tool searches for static references to internal APIs it recognizes in the JDK.

Basic command:

```bash
jdeps --jdk-internals path/to/application.jar
```

The input can be a `.class` file, a directory containing compiled classes, or a JAR file. You can analyze individual libraries or application artifacts. Use `jdeps` from the target JDK or a JDK whose analysis baseline matches the target migration version, because the set of internal APIs and module info changes across JDK versions.

Example on Linux/macOS:

```bash
"$JAVA_HOME/bin/jdeps" --jdk-internals build/libs/application.jar
```

Example on Windows PowerShell:

```powershell
& "$env:JAVA_HOME\bin\jdeps.exe" --jdk-internals .\build\libs\application.jar
```

If `jdeps` is already on `PATH`, you can invoke it directly without specifying the path to the `bin` directory.

## 4. Reading `--jdk-internals` Output

When references are found, `jdeps` typically groups results under a section named `JDK Internal API`. Depending on the JDK version, output may display the application class, referenced internal API, related module, and suggested replacement.

Illustrative example of the kind of information to watch for:

```text
JDK Internal API
   com.example.buffer.LegacyBuffer -> sun.misc.Unsafe
   com.example.codec.LegacyCodec   -> sun.misc.BASE64Encoder

Warning: JDK internal APIs are unsupported and may be removed
```

This is an abbreviated example to explain how to read it; exact content, grouping, and messages depend on the `jdeps` version and the analyzed classes.

When reading a result, identify:

- **Class using the API:** which class in the application or library is making the reference.
- **Internal API:** which JDK class, interface, or method is being used.
- **Dependency source:** whether the reference resides in the project's source code or in a third-party dependency.
- **Suggested replacement:** whether the tool provides a public API or replacement module.
- **Impact level:** whether the API still exists in the target JDK, whether it is strongly encapsulated, and whether a replacement path matching current behavior exists.

Do not treat warnings as proof that the application will definitely fail immediately. A warning indicates a dependency on an API without stability guarantees. Combine the findings with the target JDK version, how the API is accessed, and runtime testing to determine concrete risk.

## 5. Commonly Used Analysis Options

### 5.1. Analyzing an Application JAR

```bash
jdeps --jdk-internals build/libs/application.jar
```

This is a simple starting point. It helps detect internal references in the bytecode of the specified artifact.

### 5.2. Recursive Dependency Analysis

```bash
jdeps --jdk-internals --recursive \
  --class-path "lib/*" \
  build/libs/application.jar
```

`--recursive` requests analyzing dependencies across the provided classpath scope. `--class-path` helps `jdeps` find external dependencies the application references. On Windows, the classpath entry separator is a semicolon (`;`); on Linux/macOS it is typically a colon (`:`). Classpath wildcards like `lib/*` include the JARs in that directory within the analysis scope.

If the application uses the module path, provide the appropriate module path via `--module-path`:

```bash
jdeps --jdk-internals --recursive \
  --module-path "mods:lib" \
  --module com.example.application
```

Module names, paths, and syntax must be adjusted to match actual packaging. For standard classpath applications, do not add `--module-path`.

### 5.3. Analyzing a Compiled Class Directory

```bash
jdeps --jdk-internals build/classes/java/main
```

This command is useful when wanting to check compilation output before creating a JAR. For multi-module projects, analyze each corresponding output directory or artifact; running once on a single module does not represent the entire repository.

### 5.4. Analyzing Multi-Release JARs

Multi-release JARs can contain different classes per Java version in directories like `META-INF/versions/9/` or higher. When needing to analyze a specific runtime's view, use `--multi-release`:

```bash
jdeps --jdk-internals --multi-release 21 library.jar
```

Select the value matching the JDK version being evaluated and the multi-release JAR structure. Without specifying the right version, output may not reflect the class variant selected by the target JVM.

### 5.5. Saving Output for Comparison

```bash
jdeps --jdk-internals application.jar > jdeps-internals.txt 2>&1
```

Saving output enables before/after migration comparisons and ties evidence to the commit, JDK build, artifact hash, and analysis environment. Do not save only screenshots or copy a few warning lines while dropping tool version details.

## 6. Workflow for Finding Internal APIs in a Real Project

Running `jdeps` once on the main JAR is usually insufficient. The application may use internal APIs through a third-party library, plugin, or another internal module.

### Step 1: Select the JDK Used for Analysis

Identify the target feature release and run `jdeps` from that corresponding JDK. Record the tool version:

```bash
jdeps --version
java -version
```

If compatibility across multiple feature releases must be checked, run separate analyses for each target JDK and keep outputs separate.

### Step 2: Identify All Artifacts to Scan

List:

- JARs produced by the current module.
- Internal modules that the application depends on.
- Third-party dependencies on the runtime classpath.
- Plugins or agents loaded in the actual environment if within migration scope.
- Artifacts loaded dynamically or deployed separately from the main application.

Do not assume dependencies outside the source repository do not need checking. A third-party library can still contain references to internal APIs and cause the application to fail on the target JDK.

### Step 3: Run Analysis with Appropriate Dependency Paths

Run `jdeps --jdk-internals` on the main artifact, then expand to the required classpath or module path. If dependencies fail to resolve, verify paths and artifacts before interpreting results. Do not ignore resolution errors and conclude the report covers the entire dependency graph.

### Step 4: Record Every Finding

Create a list with fields: artifact, calling class, internal API, dependency owner, detecting JDK, target JDK, suggested replacement, priority level, and resolution status.

### Step 5: Identify the Owner

If the reference is in the team's own source code, the team can replace it proactively. If it is in a third-party library, check newer versions, issue trackers, and library release notes. If no fix exists yet, consider upgrading, swapping the library, isolating the dependency, or deferring migration with a time limit.

### Step 6: Fix and Test

Replace the internal API with a suitable standard or supported API. Then run builds, tests, and integration tests on the target JDK. Re-run `jdeps --jdk-internals` to confirm the static reference has been eliminated within the scan scope.

### Step 7: Store Migration Evidence

Save the JDK version, distribution, executed commands, scanned artifacts, classpath/module path, outputs, and list of approved exceptions. The report must clearly state unanalyzed areas to avoid creating a false sense of complete coverage.

## 7. Examples of Replacing Common Internal APIs

`jdeps` may suggest replacement APIs for certain findings. Suggestions must be evaluated against the intended use and the project's minimum Java version.

| Common Internal API | Supported API/Approach to Consider | Migration Notes |
|---|---|---|
| `sun.misc.BASE64Encoder` and `sun.misc.BASE64Decoder` | `java.util.Base64` | Choose basic, URL-safe, or MIME encoder/decoder matching the legacy data format. |
| `sun.misc.Cleaner` | `java.lang.ref.Cleaner` | Evaluate lifecycle, cleanup timing, and resource management; cleanup does not replace deterministic `close()`. |
| `sun.reflect.Reflection` to get caller | `StackWalker` | Identify the actual goal, as stack inspection can differ in performance and frame representation. |
| `sun.misc.Unsafe` for memory/field access | `VarHandle`, `java.lang.invoke` APIs, or Foreign Function & Memory API when appropriate | Not every operation has a one-to-one replacement; verify memory ordering, alignment, lifetime, and performance. |
| `com.sun.image.codec.jpeg` | `javax.imageio.ImageIO` | Check image quality, metadata, color model, and encode/decode behavior. |

Example migrating Base64 to the standard API:

```java
import java.util.Base64;

public final class TokenCodec {
    public String encode(byte[] value) {
        return Base64.getEncoder().encodeToString(value);
    }

    public byte[] decode(String encoded) {
        return Base64.getDecoder().decode(encoded);
    }
}
```

If legacy data uses MIME line wrapping or URL-safe alphabet, select `getMimeEncoder()` or `getUrlEncoder()` accordingly. Simply renaming the class without checking format can make tokens, files, or messages incompatible with stored data.

Example using `StackWalker` instead of an internal API to inspect the caller:

```java
import java.lang.StackWalker;

public final class CallerInspector {
    private static final StackWalker WALKER =
            StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);

    public Class<?> callerClass() {
        return WALKER.walk(frames -> frames
                .skip(1)
                .findFirst()
                .map(StackWalker.StackFrame::getDeclaringClass)
                .orElse(Object.class));
    }
}
```

This example only illustrates how to inspect the stack with a public API. Adjust the number of skipped frames to match the real call path and consider whether business logic should depend on the caller at all.

## 8. The Case of `sun.misc.Unsafe` and Module `jdk.unsupported`

`sun.misc.Unsafe` is an important example because it can still appear in modern JDKs through module `jdk.unsupported`. Several high-performance libraries previously used this class for memory operations, atomic operations, or field access.

That the class still exists does not mean it is a supported, stable Java SE API. `jdeps --jdk-internals` can still report this reference to warn consumers relying on an internal API.

When handling an `Unsafe` finding, identify the exact operation used:

- Atomic access and memory ordering may fit `VarHandle`.
- Offset-based field access requires evaluating `VarHandle`, supported reflection, or redesigning the abstraction.
- Off-heap memory management should consider the Foreign Function & Memory API per target feature release.
- Operations relying on JVM-specific layout or behavior may require redesign and performance testing.

Do not mechanically replace all of `Unsafe` with a single other API. In particular, the Foreign Function & Memory API evolved across Java releases before becoming a stable API; consult the documentation of the exact target JDK to pick the appropriate API.

## 9. Limitations of `jdeps --jdk-internals`

`jdeps` is a static bytecode analysis tool. It is very useful, yet does not prove the application has zero dependence on internal APIs.

### 9.1. Does Not Fully Detect Dynamic Reflective Access

Example:

```java
Class<?> type = Class.forName("sun.misc.Unsafe");
```

The class name is a string. Bytecode may not contain a symbolic reference in the way `jdeps` recognizes as a regular class dependency. Similarly, calls to `Class.getDeclaredMethod`, `setAccessible`, method handles built from string names, or reflection configurations may not be fully detected.

### 9.2. Does Not Analyze Native Code

JNI, native libraries, C/C++ code, or native agents can access JVM and OS internals outside the scope of Java bytecode analyzed by `jdeps`.

### 9.3. Cannot Know Every Dynamically Loaded Class

Plugins, script engines, custom class loaders, runtime-generated bytecode, or remotely loaded artifacts may not be in the input file set. Without including them in the scan scope, output cannot reflect their dependencies.

### 9.4. Does Not Prove Runtime Behavior

Finding a static reference does not tell you whether that code path executes in production. Conversely, finding no references does not prove every execution path is safe. Combine static analysis with tests and runtime observation.

### 9.5. Does Not Fully Evaluate Unresolved Dependencies

If the classpath lacks required JARs or modules, analysis may not cover the dependency graph as intended. Address warnings or resolution errors, document missing parts, and re-run with exact paths.

### 9.6. Does Not Classify All Non-Java-SE APIs

`--jdk-internals` focuses on JDK internal APIs. Third-party dependencies, framework APIs, legacy `javax.*` APIs, or vendor-proprietary APIs are not necessarily reported as JDK internal APIs. Those dependency groups require separate tools and inventory processes.

## 10. Supplementing Checks Beyond `jdeps`

To increase coverage, combine `jdeps` with the following methods:

| Method | Purpose |
|---|---|
| Source search | Find `sun.*` imports, internal packages, class names in strings, and reflection calls. |
| Dependency inventory | Identify all JARs, plugins, agents, and native libraries shipped with the application. |
| API compatibility tool | Check public API changes across library versions. |
| Static analysis/forbidden API rules | Prevent new source code from referencing prohibited internal packages/APIs. |
| Integration tests on target JDK | Catch access, linkage, and behavioral errors that appear only at runtime. |
| Runtime observation | Monitor reflective access errors, linkage errors, class loading, and JVM warnings in production-like environments. |

You can use source search as a screening step:

```bash
rg -n "sun\\.|com\\.sun\\.|Class\.forName|setAccessible" src
```

Search results can contain false positives and also do not cover compiled code in dependencies. Inspect each finding, distinguishing true internal APIs from supported APIs with historical package names.

A rule such as Forbidden APIs can fail the build when new source code references prohibited APIs. Rules should be configured per project policy, feature release, and approved exceptions. Do not add overly broad ban lists that block valid public APIs.

## 11. Handling When Internal APIs Cannot Be Removed Yet

Sometimes a third-party library has no replacement version yet, or replacing an internal API requires significant architectural changes and performance testing. In such cases, manage the finding as technical debt with an owner and due date.

An exception record should include:

- Artifact and version containing the internal API.
- API name and calling class.
- Current JDK and affected target JDKs.
- Affected consumers and business flows.
- Reason it cannot be replaced yet and options considered.
- Mitigations, such as pinning dependency versions or isolating the module.
- Owner, next review date, and criteria for closing the exception.

Do not treat `--add-exports` or `--add-opens` as default long-term migration solutions. These options can open access for specific cases, yet they add runtime/build configuration and depend on the JDK's module structure. If temporary use is unavoidable, document the package/module, reason, target environments, owner, and removal plan.

With Java 17 and newer, the `--illegal-access` flag no longer restores global relaxation as in the earlier transition era. Do not rely on this flag to address internal access errors on modern JDKs. Identify the exact package/module and choose a replacement or minimally scoped access opening if the situation truly demands it.

## 12. Checklist Before Completing Internal API Checks

- [ ] Ran `jdeps --jdk-internals` using the target JDK and saved the tool version.
- [ ] Scanned the main artifact, internal modules, and necessary dependencies.
- [ ] Supplied the exact classpath or module path; resolved unresolved dependencies.
- [ ] Recorded calling class, internal API, artifact owner, and suggested replacements.
- [ ] Distinguished references in project source code from references in third-party libraries.
- [ ] Replaced with suitable public APIs or filed an exception with owner and expiry.
- [ ] Checked reflection, JNI, dynamic loading, and areas `jdeps` cannot cover.
- [ ] Ran builds, unit tests, and integration tests on the target JDK.
- [ ] Re-ran analysis after fixes and saved the final output.
- [ ] Explicitly noted unscanned scope and remaining risks.

## Conclusion

`jdeps --jdk-internals` helps detect static bytecode references to JDK internal APIs, helping isolate risks before upgrading Java. Results should be read by artifact, calling class, referenced API, and target JDK; then determine replacement APIs, owners, and appropriate tests. Because `jdeps` does not fully cover dynamic reflection, JNI, runtime-loaded classes, or unresolved dependencies, it must be part of an analysis workflow combining source search, dependency inventory, and testing on the target JDK. Recording commands, tool versions, scan scope, and exceptions lets the team turn internal API discovery into a repeatable migration control step.