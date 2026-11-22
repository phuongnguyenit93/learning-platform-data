# Impact of Deprecated APIs, forRemoval, and Removed Features in Java

When upgrading the JDK or Java libraries, not every API that once worked remains a good choice. An API may be **recommended against using** (*deprecated*), **marked as scheduled for removal** (*deprecated for removal*), or **already actually gone** from the new version. These three states cause different consequences for the compiler, bytecode, runtime environment, and migration plan.

This article belongs to the **version compatibility** group of Java Advance – compilation: the focus is not only on reading the `@Deprecated` annotation, but also on understanding **when a build warns or fails, how old binaries link, what `--release` guarantees, and what to check before upgrading**.

## 1. Distinguishing Three States

| State | Meaning | When compiling source using that API | When running already-compiled binaries |
| --- | --- | --- | --- |
| API still exists, `@Deprecated(forRemoval=false)` | Should not continue to be used; no specific intent to remove declared at the time of marking | Typically an **ordinary deprecation warning** when used in contexts where warnings are enabled; not automatically an error | Usually still links/runs if the API and dependencies remain present and compatible |
| API still exists, `@Deprecated(forRemoval=true)` | Declared **intent to remove in a future version** | **Removal warning**, usually shown by default with `javac`; the annotation itself does not remove the API | Can still run while the API remains present and valid |
| API/feature has been removed in target/runtime | No longer defined or appropriately supported | Source may fail with errors like `cannot find symbol`/`package does not exist`/module not found; removed syntax or options may fail accordingly | Old binaries may encounter `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException`, `NoSuchFieldError`, module errors, or behavioral changes depending on the situation |

**Important:** `forRemoval=true` **is not an automatic deletion deadline**, does not imply "it will be removed immediately in the next release", and does not guarantee the API will be removed in a specific version. It is a signal to take action early. Conversely, `forRemoval=false` **does not promise the API will be kept forever**.

An API may be deprecated due to: a better alternative; an outdated design; safety risks; potential for misuse; or possible incompatible changes in the future. Do not infer that an API **is broken or immediately stops working** solely from the word "Deprecated".

## 2. Syntax and Meaning of `@Deprecated`

The standard annotation `java.lang.Deprecated` has existed since Java 5; the two elements `since` and `forRemoval` were added in Java 9.

~~~java
@Deprecated(since = "2.0", forRemoval = true)
public static void oldOperation() {
    // ...
}
~~~

- `since` is an **informational string** indicating the version in which the element was marked deprecated; its default value is the empty string `""`. For a custom library, `"2.0"` can be the library version, not necessarily the JDK version.
- `forRemoval` is a boolean, defaulting to `false`. `true` expresses intent to remove; `false` only advises against use without a specific removal intent at the time of annotation.
- `@Deprecated` can mark a class, interface, method, constructor, field, module, package, etc., depending on the targets supported by the annotation. Warning emission rules differ by element kind; for example, marking a local variable or parameter does not cause every use of it to emit a deprecation warning.
- The annotation has runtime retention, so reflection can read deprecation information. However, **reflection being able to read the annotation does not mean code using the API only encounters issues at runtime**: warnings related to using the API name are typically detected by the compiler directly from the source.

Equivalent syntax when not overriding the defaults:

~~~java
@Deprecated
public void oldMethod() {
    // forRemoval=false, since=""
}
~~~

And when the version deprecation started is known, without intending to remove yet:

~~~java
@Deprecated(since = "1.3", forRemoval = false)
public void oldMethod() {
}
~~~

### `@Deprecated` and Javadoc `@deprecated` are not the same

**The annotation** `@Deprecated` serves the compiler, tooling, and reflection. **The Javadoc tag** `@deprecated` (lowercase `d`) explains *why it should not be used* and *what to replace it with*.

Example of writing an API responsibly:

~~~java
/**
 * Creates a string in the old format.
 *
 * @deprecated Since 2.0, use {@link #format(String)}
 *             to unify the output format.
 */
@Deprecated(since = "2.0", forRemoval = false)
public static String oldFormat(String value) {
    return "old:" + value;
}

public static String format(String value) {
    return "new:" + value;
}
~~~

This is **an illustrative method snippet inside a class**, not yet a standalone program. You should use **both the annotation and the Javadoc tag**: the annotation so tools recognize the status, and the documentation so users know the migration path. When a method changes behavior, the documentation must clearly explain the differences; simply writing "use X instead" without explaining semantics can cause logic bugs.

## 3. Java 17+ Practice: Ordinary Warnings and Removal Warnings

The complete example consists of **two files** in the `training` package.

**File `src/training/LegacyApi.java`:**

~~~java
package training;

public final class LegacyApi {
    private LegacyApi() {
    }

    /**
     * @deprecated Use {@link #format(String)} instead.
     */
    @Deprecated(since = "1.0", forRemoval = false)
    public static String oldFormat(String name) {
        return "hello " + name;
    }

    /**
     * @deprecated Use {@link #limit()} instead.
     */
    @Deprecated(since = "2.0", forRemoval = true)
    public static int oldLimit() {
        return 10;
    }

    public static String format(String name) {
        return "modern " + name;
    }

    public static int limit() {
        return 20;
    }
}
~~~

**File `src/training/Client.java`:**

~~~java
package training;

public final class Client {
    public static void main(String[] args) {
        System.out.println(LegacyApi.oldFormat("An"));
        System.out.println(LegacyApi.oldLimit());
        System.out.println(LegacyApi.format("An"));
        System.out.println(LegacyApi.limit());
    }
}
~~~

From the directory containing `src`, using **JDK 17+**:

~~~bash
mkdir out
javac -encoding UTF-8 --release 17 -Xlint:deprecation -Xlint:removal -d out src/training/LegacyApi.java src/training/Client.java
java -cp out training.Client
~~~

If `out` already exists, skip the `mkdir out` command.

**Program stdout:**

~~~text
hello An
10
modern An
20
~~~

When `javac` compiles `Client.java`, it recognizes:

- `oldFormat(String)` is deprecated, but `forRemoval=false` ⇒ warning labeled **`[deprecation]`** when `-Xlint:deprecation` is enabled.
- `oldLimit()` is marked `forRemoval=true` ⇒ **`[removal]`** warning when `-Xlint:removal` is enabled.
- `format` and `limit` are not deprecated ⇒ neither warning above is emitted.

Compiler warnings typically appear **on stderr**, not on `java`'s stdout. Exact line numbers, file paths, and formatting vary by `javac` version, so do not treat them as fixed stdout. For this example source, the compiler will point out the two usages of the old API in `Client`; the program still runs after the build succeeds.

A concise summary is:

~~~text
[deprecation] oldFormat(String) ... has been deprecated
[removal] oldLimit() ... has been deprecated and marked for removal
~~~

The two lines above are merely **a simulation of the key message parts**, not a verbatim copy of stderr from a specific machine.

## 4. `javac` Rules for the Two Warning Categories

According to the JDK documentation, ordinary deprecation and deprecation-for-removal are **two independent warning categories**.

| Option | Meaning |
| --- | --- |
| `-Xlint:deprecation` | Print detailed ordinary deprecation warnings |
| `-Xlint:removal` | Print detailed warnings for APIs marked for removal |
| `-Xlint:-deprecation` | Disable the ordinary deprecation category |
| `-Xlint:-removal` | Disable the removal category |
| `-Xlint:all` | Enable all applicable lint categories, not only deprecation |
| `-Werror` | Cause compilation to fail if any warning is emitted |
| `-Xmaxwarns 100` | Control the maximum number of warnings displayed; **does not fix errors** |

In modern `javac`, **`-Xlint:removal` is enabled by default**, while ordinary deprecation may only be reported by a summary line "uses or overrides a deprecated API" if `-Xlint:deprecation` is not enabled. Do not claim a source has no issues simply because the output lacks individual detailed warning lines.

Try a strict build:

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:deprecation -Xlint:removal -Werror -d out src/training/LegacyApi.java src/training/Client.java
~~~

With the two deprecated calls in `Client.java`, compilation **fails because warnings are treated as errors**. Whether the compiler leaves behind some intermediate artifacts is not something to rely on; use a clean build in CI when you need to confirm the result.

**Enabling warnings helps detect risks**, but is not a guarantee that the compiler will find every risky API: code invoked via reflection, service loaders, method handles, native interop, or runtime-only execution paths may require separate inspection.

### Can `@SuppressWarnings` be used?

Yes, but you must use **the right key**:

~~~java
@SuppressWarnings("deprecation")
static void callOldFormat() {
    LegacyApi.oldFormat("An");
}

@SuppressWarnings("removal")
static void callOldLimit() {
    LegacyApi.oldLimit();
}

@SuppressWarnings({"deprecation", "removal"})
static void callBoth() {
    LegacyApi.oldFormat("An");
    LegacyApi.oldLimit();
}
~~~

The three methods above are **an illustrative snippet placed in a class in the same package or with appropriate imports**, not a standalone program.

`"deprecation"` does **not** automatically suppress `"removal"`; `"removal"` also does not suppress ordinary deprecation. Suppression takes effect within the annotated scope according to compiler rules; keep the scope small, document the reason, and set a replacement timeline.

**Suppression only hides warnings; it does not restore removed APIs.** When a method/class no longer exists in the target API, the source still will not compile or the binary will still fail at link time. Silencing warnings does not make code more compatible.

## 5. Switching to the New API: Semantics Must Be Verified

If you change the two calls in `Client`:

~~~java
System.out.println(LegacyApi.format("An"));
System.out.println(LegacyApi.limit());
~~~

then the output of the two lines is respectively:

~~~text
modern An
20
~~~

The code no longer depends on the two deprecated methods, yet the program's output has **changed** compared to `oldFormat` and `oldLimit`. This illustrates that migration is not always a mechanical method-name replacement.

A safe replacement strategy:

1. Read the Javadoc of the old and new APIs, especially differences in input, output, null handling, exceptions, threading, timezone, charset, default values, and security behavior.
2. Write tests for real use cases and edge cases.
3. Migrate call sites in batches; if the old API must still be supported, create a small, clearly scoped adapter layer.
4. Enable lint and verify the build on the target JDKs.
5. Remove temporary suppressions once migration is complete.

If an API is deprecated because of a **security risk**, keeping the old API solely to "avoid changing output" may not be an acceptable option. Conversely, a replacement with a similar functional name but different semantics can also introduce bugs in production. Decisions must be based on the specific API contract.

## 6. What Happens When an API Is Removed?

**Deprecated** is still part of the current API; **removed** means a class, method, field, module, tool, option, or behavior is no longer provided as before.

The impact typically unfolds across two different scenarios.

### 6.1. Compiling old source against a new library/JDK

For example, source calling a removed method:

~~~java
String message = LegacyApi.oldFormat("An");
~~~

When the compiler only sees a version of `LegacyApi` **from which `oldFormat` has been removed**, it encounters an error like `cannot find symbol`. If the entire package or module was removed, you may see `package ... does not exist` or `module not found`. Deprecation warnings are no longer the main issue: **the compiler can no longer find a valid declaration**.

If the source code uses a **language syntax** not supported by the target release, the error is syntax/source-level. If it uses a removed **launcher/compiler option**, the build command may be rejected. Do not lump these errors together as a "deprecated warning".

### 6.2. Old binary running with a new library version

Java bytecode typically retains symbolic references to classes, methods, and fields using the compiled names/descriptors. If the library deployed at runtime no longer satisfies an emitted reference, the JVM may throw **linkage errors**.

| Changed element | Possible symptom |
| --- | --- |
| Class removed from runtime | `NoClassDefFoundError` when bytecode needs that class; `ClassNotFoundException` when actively looking it up via APIs like `Class.forName` |
| Method removed / descriptor changed | `NoSuchMethodError` when the call site is resolved |
| Field removed / descriptor changed | `NoSuchFieldError` |
| Incompatible static/instance change or declaration type change | May cause `IncompatibleClassChangeError` or related linkage errors |
| Module dependency removed or unresolved | Module resolution/initialization error, depending on how it is launched |
| Runtime too old for class-file version | `UnsupportedClassVersionError`, not necessarily related to deprecation |

**There is no guarantee every old binary breaks** immediately when an API is removed: only execution paths that need to resolve the missing reference can trigger the corresponding error. A binary that no longer calls that method may keep working; apps using reflection/native access are also subject to their own mechanisms.

### 6.3. Binary compatibility experiment: removing a method without recompiling the client

Create three source files in three separate source roots:

~~~text
compat-lab/
├── api-v1/lib/Greeter.java
├── api-v2/lib/Greeter.java
└── client/app/Main.java
~~~

**File `api-v1/lib/Greeter.java`:**

~~~java
package lib;

public final class Greeter {
    @Deprecated(since = "1.0", forRemoval = true)
    public static String greet() {
        return "legacy";
    }
}
~~~

**File `api-v2/lib/Greeter.java`:**

~~~java
package lib;

public final class Greeter {
    public static String welcome() {
        return "modern";
    }
}
~~~

**File `client/app/Main.java`:**

~~~java
package app;

import lib.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.greet());
    }
}
~~~

Create the output directories `build/v1`, `build/v2`, and `build/client` beforehand. From the `compat-lab` directory, compile **the two API versions separately**:

~~~bash
javac -encoding UTF-8 --release 17 -d build/v1 api-v1/lib/Greeter.java
javac -encoding UTF-8 --release 17 -d build/v2 api-v2/lib/Greeter.java
javac -encoding UTF-8 --release 17 -cp build/v1 -d build/client client/app/Main.java
~~~

The client compile command sees `build/v1`, where `greet()` still exists. On Windows, run:

~~~bash
java -cp "build/client;build/v1" app.Main
~~~

On Linux/macOS, run:

~~~bash
java -cp "build/client:build/v1" app.Main
~~~

Stdout in both cases:

~~~text
legacy
~~~

**Try intentionally using the new API binary without recompiling the client:**

Windows:

~~~bash
java -cp "build/client;build/v2" app.Main
~~~

Linux/macOS:

~~~bash
java -cp "build/client:build/v2" app.Main
~~~

The call to `lib.Greeter.greet()` no longer has a target method in `build/v2`. When the JVM needs to resolve the method, the application fails with **`java.lang.NoSuchMethodError`**. The stack trace, paths, or module details depend on the runtime; this is the expected error of **an intentionally incompatible experiment**, not the normal output of a successful program.

If `Main.java` is recompiled with `-cp build/v2`, the compiler reports that method `greet()` cannot be found. The two experiments demonstrate:

- **Source incompatibility:** old code does not compile against the new API.
- **Binary incompatibility:** previously compiled binaries fail when linking/calling against the new API.

In practice, ensuring the deployment uses the right **library version** is just as important as building successfully.

## 7. What Can `--release` Do and What Can It Not Do?

Suppose you are using a newer JDK, but the application must be compatible with Java 17:

~~~bash
javac --release 17 -d out src/training/LegacyApi.java src/training/Client.java
~~~

`--release 17` targets **the syntax/language, class-file target, and supported platform API set of Java 17** according to `javac`'s mechanism. It is useful for avoiding accidental calls to a **Java platform API** only present in newer JDKs.

Comparison:

- `-source 17` controls the source syntax level and does not automatically ensure every Java platform API called exists in Java 17.
- `-target 17` controls the class-file target and does not independently guarantee API compatibility.
- `--release 17` combines control of source level, target, and Java platform APIs for that release.

**Important limitations:**

1. `--release 17` does not turn a JAR of **a third-party library version 5** into the API of version 3. Dependencies must be managed by specific artifact/version.
2. `--release 17` does not prove a future runtime will still keep that API if a later runtime version removed the API, changed behavior, or altered configuration.
3. `--release` does not check all behaviors only detected at runtime such as reflection, native libraries, TLS defaults, filesystem permissions, or service providers.
4. The JDK compiler only supports a **specific set of release targets**. Check with `javac --help`; do not assume a newer compiler can target arbitrarily old Java versions.
5. When targeting the platform API of an older release, do not use options that break platform API encapsulation to bypass `--release` constraints.

Therefore, **compiling with `--release 17` is a necessary but insufficient step** in a multi-JDK-version upgrade workflow.

### The same source against two API baselines

Code calling an API present in Java 17 that was removed in a later JDK can compile successfully with `--release 17`. That does not mean it will run on every newer JDK: the newer runtime must still provide the classes and methods referenced by the bytecode.

Conversely, if you compile the source **targeting a new release that removed the API**, the compiler can reject it immediately. Do not confuse "compiles for Java 17" with "fully tested on Java 17 and every newer Java version".

## 8. Removed APIs, Modules, Tools, and Features Span Different Scopes

Java evolves across versions; what gets deprecated/removed is not limited to just a method.

| Scope | Example impact | How to check |
| --- | --- | --- |
| **Method / field / class in API** | Call site can no longer compile or link | Javadoc, binary compatibility, build, and smoke tests |
| **Package / JDK module** | `requires` fails to resolve; imported package disappears; class is gone | Module graph, module path, dependency artifacts |
| **JDK tools** | CI script calls an executable that no longer exists | Migration guide, `java -version`, check build scripts |
| **Compiler/launcher/JVM options** | Startup or build is rejected; option may only warn or be ignored | Test the CLI commands directly on target JDKs |
| **Language/source features** | Syntax not supported by target source version | `javac --release N`, JLS for N |
| **Runtime behavior** | Same bytecode but different defaults/deployment capabilities | Integration tests, release notes, runtime configuration |

### Historical examples in the JDK

- **Java 11:** Java EE/CORBA modules previously shipped with the JDK such as `java.xml.bind`, `java.xml.ws`, and `java.corba` were removed from the JDK under **JEP 320**. Legacy code may need to add external dependencies or migrate to newer APIs. With JAXB, note there are different namespace/artifact generations, not merely a single import swap.
- **Java 15:** The Nashorn JavaScript engine and the `jjs` tool were removed under **JEP 372**. An application using `ScriptEngineManager` that expects a default JavaScript engine may need a different engine; the Java Scripting API itself and losing a specific engine are two different issues.
- **Java 17:** The Java RMI Activation API was removed following its removal roadmap. That does not mean **all of RMI** was removed from Java.

These historical examples show that "deprecated for removal" can lead to **actual removal**, without establishing a fixed rule for "how many releases before removal". Check the exact JEP/migration guide/release notes of **the release in use** before concluding the status of any specific API.

## 9. Tools for Detecting Deprecation and Removal

### 9.1. `javac`: seeing where source calls old APIs

When compiling source code:

~~~bash
javac --release 17 -Xlint:deprecation -Xlint:removal -d out src/training/LegacyApi.java src/training/Client.java
~~~

Read all warnings to locate call sites; after migrating, you can enable `-Werror` in CI to prevent introducing new usages of deprecated APIs. Control this per module/package if the codebase has a large backlog of legacy warnings, so the roadmap does not stall team development.

### 9.2. `jdeprscan`: scanning references to deprecated Java platform APIs

`jdeprscan` is a JDK tool that can scan compiled classes/JARs/directories to report references to deprecated Java platform APIs for a specified release. For example, surveying the list of APIs marked for removal in Java 17:

~~~bash
jdeprscan --release 17 --list --for-removal
~~~

Or scan the project's output (`out` must contain class files):

~~~bash
jdeprscan --release 17 --for-removal out
~~~

Available tool options/releases depend on the running JDK version; check `jdeprscan --help`. When scanning, a sufficient classpath is needed to resolve dependencies, otherwise errors or incomplete results may occur. `jdeprscan` targets **deprecated Java platform APIs**, not arbitrary deprecated APIs in third-party JARs, and it does not detect every dynamic invocation via reflection.

### 9.3. `jdeps` and class-file inspection

`jdeps` is useful for package/module-level dependency analysis, helping identify references to internal APIs and related migration points. However, it is not the sole method for determining whether a method was removed or whether a replacement is semantically equivalent.

`javap -v` can display `Deprecated` metadata and annotations in compiler-generated class files; exact attributes and formatting depend on the compiler/JDK. Do not rely solely on a disassembly listing to conclude runtime safety while skipping tests.

### 9.4. Documentation and CI matrix

You should combine:

- Java API documentation: read the deprecated notes, `since`, `forRemoval`, alternatives, and caveats.
- JDK migration guide, JEPs, release notes: learn which modules/tools/options/behaviors are removed in each release.
- Dependency changelogs and semantic-versioning policies of each library.
- Clean builds with warnings and tests on both **the minimum supported JDK** and **the upcoming target deployment JDK**.
- Runtime verification using the exact dependency graph, without substituting library versions different from what was tested.

## 10. Safe Migration Strategy

A long-lived project typically cannot remove all deprecated APIs in a single commit. You can proceed sequentially:

1. **Lock the baseline:** record supported Java runtime versions, compiler version, `--release` target, dependencies, and actual build/run JDKs. Avoid "works on my machine" using proper lockfiles/version management.
2. **Inventory:** enable `-Xlint:deprecation` and `-Xlint:removal`, run `jdeprscan` for JDK APIs, and categorize warnings by module and library.
3. **Prioritize risk:** `forRemoval=true` APIs, security issues, or APIs already removed in the target JDK must be prioritized over ordinary deprecations that merely have a more convenient replacement.
4. **Read replacement contracts:** return types, nullability, exception types, encoding, performance, initialization, concurrency, resource ownership, and security controls may differ.
5. **Write behavioral tests:** unit/integration tests for normal flows and error cases; binary compatibility tests when the library provides APIs to external consumers.
6. **Migrate in small areas:** replace call sites, update dependency/module descriptors, remove bridge adapters when no longer needed. If compatibility must be preserved, consider a façade with a version-aware implementation, without pretending a removed API is still present.
7. **Promote warnings to CI policy:** you can enable `-Werror` after clearing existing warnings; do not overuse `@SuppressWarnings` broadly.
8. **Verify deployment:** run tests on the new JDK with the real module/classpath, observing stack traces, module resolution, reflection, native integration, serialization, and startup options.
9. **Monitor upcoming releases:** one successful migration does not eliminate the risk of newly introduced deprecations.

### Typical priority order

| Level | Condition | Action |
| --- | --- | --- |
| P0 | Already removed from target JDK/library or causes runtime errors | Block rollout; fix build/dependency/code immediately |
| P1 | `forRemoval=true` or deprecation due to safety/security | Plan early replacement, with tests |
| P2 | Ordinary deprecation with a stable replacement | Migrate in a controlled manner within development cycles |
| Monitor | Deprecated without a replacement yet / unaffected on current target | Log the risk and re-evaluate on each version upgrade |

The P0/P1/P2 classification is a **recommended workflow**, not a standard JDK label; final priority depends on the actual system.

## 11. Common Misconceptions

**"`@Deprecated` is a compilation error."** False. Normally it is a warning; it may fail due to `-Werror` or build policies, not because the annotation immediately makes the API disappear.

**"`forRemoval=true` means the next version will definitely remove it."** False. It is a statement of intent and a risk signal, not a removal schedule guaranteed by Java.

**"`since="17"` means the API has only existed since Java 17."** False. In `@Deprecated`, `since` records **when deprecation began**, not when the API first existed. The Javadoc `@since` tag serves a different role.

**"Silencing warnings with `@SuppressWarnings` makes it compatible."** False. When the symbol is removed, compilation or linking still fails.

**"`-Xlint:deprecation` automatically includes removal warnings."** Do not assume so: these are two separate categories, controlled independently via `deprecation` and `removal`.

**"A successful build on a newer JDK proves the binary deployed on an older JDK will work."** False. Appropriate `--release`, dependency compatibility, and actual runtime testing are required.

**"Compiling with API v1 and running with API v2 is always fine if class names match."** False. The JVM also resolves method/field descriptors and modules/dependencies; linkage errors can occur.

**"Seeing no warnings means the project uses no removed APIs."** False. Lint might not be enabled, suppressions may exist, or the code may use reflection, precompiled binaries, or go through another library.

**"A removed feature/tool means every related API is removed."** False. For instance, removing the Nashorn engine and `jjs` tool does not mean every Java Scripting API is immediately removed.

## 12. Self-Check Exercises

**1.** What does `@Deprecated(since="2.1", forRemoval=false)` indicate?

It indicates the API was marked deprecated starting in version `2.1` of the relevant component; it does not yet express a specific removal intent at the time of annotation. It does not mean the API was newly added in `2.1`.

**2.** If a method has `forRemoval=true` but still exists in the running JDK, is the call guaranteed to fail?

No. The compiler may emit a removal warning; runtime can still succeed if the symbol is present and behaves as expected. Deprecation status alone does not delete the method.

**3.** Why might `@SuppressWarnings("deprecation")` not suppress a removal warning?

Because `deprecation` and `removal` are two separate lint categories; to suppress removal warnings you must use `"removal"` (though you should address the root cause rather than suppress it).

**4.** Does `javac -Werror` cause an API to be removed?

No. It only causes compilation to fail when warnings are emitted. Classes/libraries are not deleted by this flag.

**5.** A client is compiled against library v1, and runtime uses library v2 which removed a method. What error can occur?

`NoSuchMethodError` when the JVM needs to resolve the call site to the missing method; exact behavior also depends on the API change and execution path.

**6.** Why does `--release 17` not yet guarantee third-party dependency compatibility?

Because `--release` checks the **Java platform API** level for that release; external libraries must have their versions selected and tested separately.

**7.** Does `jdeprscan` replace all unit/integration tests and static analysis?

No. It focuses on usage of deprecated Java platform APIs in compiled artifacts; it does not guarantee detection of every dynamic call or runtime behavior change.

**8.** When the JDK removes a module like `java.xml.bind`, can simply adding an import solve it?

No. You must determine the replacement dependency, module/classpath configuration, package namespace, and proper migration.

**9.** Why must a replacement method still be tested even after warnings disappear?

Because the replacement may return different values, handle nulls/exceptions differently, or carry different security/concurrency constraints.

**10.** What should be handled before upgrading production JDKs?

Inventory deprecations/removals, cross-check the migration guide, compile with the proper target, check binary dependencies, and run tests on the actual target JDK.

## 13. Final Checklist

- [ ] Distinguished **deprecated**, **deprecated for removal**, and **removed**?
- [ ] Read `since` accurately as the version **deprecation began**?
- [ ] Enabled both `-Xlint:deprecation` and `-Xlint:removal` when auditing?
- [ ] Reviewed API replacements by **semantics**, not just by name?
- [ ] Checked `--release` and the class-file target of the build?
- [ ] Verified JDK version, libraries, and module path/classpath at runtime?
- [ ] Checked the JDK migration guide for removed modules, tools, JVM flags, and behaviors?
- [ ] Tested both **recompiling from source** and **running precompiled binaries** when backward compatibility is required?
- [ ] Avoided using suppression as a long-term patch?
- [ ] Scheduled fixes for APIs marked for removal before they become blockers?

## Official References for Cross-Checking

- [Oracle Java 17 – `java.lang.Deprecated`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Deprecated.html): definition of the annotation, `since`, and `forRemoval`.
- [Oracle Java 17 – Enhanced Deprecation](https://docs.oracle.com/en/java/javase/17/core/enhanced-deprecation1.html): ordinary/removal warnings, lint keys, and `@SuppressWarnings`.
- [Oracle Java 17 – `javac` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, `-Xlint`, `-Werror`.
- [Oracle Java 17 – `jdeprscan`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeprscan.html): checking deprecated Java platform APIs.
- [JEP 320 – Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320) and [JEP 372 – Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): real-world removal examples.

**Conclusion:** `@Deprecated` is **a design/API warning**, `forRemoval=true` is **a signal to prepare for deletion**, and **removed** is a change that can prevent source from compiling or binaries from linking/running. To maintain version compatibility, combine lint warnings, release/dependency management, understanding of binary linkage, and testing on the target runtime — do not merely hide warnings or rename methods.