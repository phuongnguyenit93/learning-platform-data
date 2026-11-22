# Stale `.class` files, inlined constants, and risks of outdated outputs

## 1. Real-world problem

When editing Java code, saving a `.java` file does not cause a running program to automatically pick up changes. `javac` compiles source code into `.class` files; the build tool packages those files into a JAR/WAR or output directory; the JVM then loads classes from the *artifact* residing on the classpath/module path. Thus, a program can run successfully yet behave like an old version if one link in the chain still contains old bytecode.

Especially dangerous is **compile-time constant inlining**. An already-compiled application can continue printing the old value of a constant provided by a library, even when the library's `.class` file has been recompiled and the JVM is genuinely loading the new library version. This is behavior specified by the Java language specification, not necessarily a bug in the JVM or a cache.

After this lesson, you must be able to distinguish three situations often lumped together as “build did not update”:

| Symptom | Where is the old copy located? | Useful verification step |
| --- | --- | --- |
| Output `.class` file is still old | Compile directory or artifact has not been rebuilt | Check timestamp/hash, `javap`, and JAR contents |
| Library is new yet application still uses old constant | Value was placed directly into the bytecode of the **calling class** when the caller was compiled earlier | `javap -c` on the calling class, then recompile the calling class |
| New artifact exists yet runtime loads a different copy | Classpath/module path, old dependency version, old deployment image, or JVM not restarted | Identify the actual class load location and artifact version |

The fix must be based on where the stale bytecode or value lives. “Re-running a build command” may not suffice if dependencies, packaging, or the execution environment remain out of sync.

## 2. From source code to the classes the JVM uses

A simple build flow:

```text
BuildInfo.java --javac--> build/lib/demo/BuildInfo.class --package--> library.jar
Client.java    --javac--> build/app/demo/Client.class  --package--> app.jar
                                                                   |
                                        runtime classpath/module path
                                                                   |
                                                         JVM loads classes
```

At the compilation step, `Client.java` needs to see `BuildInfo`'s API, via source code or bytecode on the compile classpath. After compilation, `Client.class` is an independent output: running `Client.class` does not mean the JVM will recompile `Client.java`.

Several causes commonly produce outdated outputs:

- Recompiling only the library, without recompiling dependent application classes.
- Incremental build missing a dependency relationship, or using caches/outputs generated from old configurations.
- Source file was renamed/deleted, yet the old `.class` file remains in the output directory because the compile step does not automatically clean removed classes.
- A new JAR was created yet the run/deploy step still points to an older JAR, directory, container image, or dependency version.
- Multiple copies of the same class exist on the classpath; resolution order causes the JVM to use an unintended copy.
- Modifying a JAR file on disk while the JVM is running; already-loaded classes remain in the current JVM/class loader unless a dedicated class-reloading mechanism is present.

**You cannot conclude “there is a source code bug” merely because runtime output did not change.** First determine which `.class` was compiled, packaged, and loaded.

## 3. Which constants get inlined at compile time?

According to the Java Language Specification (JLS `4.12.4 and `15.29), a *constant variable* is a `final` variable of primitive type or `String` initialized with a compile-time constant expression. `public static final` fields of this kind are typically replaced by javac with their value directly at usage sites.

```java
public final class Constants {
    public static final int PORT = 8080;          // Compile-time constant
    public static final String REGION = "apac";    // Compile-time constant
    public static final int LIMIT = 10 * 2;        // Compile-time constant

    public static final int FROM_METHOD = load();  // Not a compile-time constant
    public static final Integer BOXED = 20;        // Integer is not a primitive/String type
    public static final String COPY = new String("apac"); // Not a constant expression

    private static int load() {
        return 20;
    }
}
```

The first three fields can be inlined in the bytecode of using classes. The latter three remain fields that must be read at runtime (excluding separate runtime optimizations that do not alter binary compatibility rules). `static final` **is not** synonymous with “always inlined”; the deciding condition is whether the type and initializer expression satisfy the definition of a *constant variable*. Constant fields in an `interface` also require attention because they are implicitly `public static final`.

A compiler may emit literal-loading instructions such as `iconst_1` or `ldc`, and may fold string concatenation with constants into a single literal. In that situation, the calling class's bytecode **does not need to execute `getstatic`** to fetch the new value from the constant-defining class.

Important consequences:

1. Changing `public static final int VERSION = 1` to `... = 2` and recompiling **only** the declaring class does not guarantee existing calling classes will see 2.
2. This value change may remain **binary compatible**: the program throws no linkage error, yet uses outdated logic. “Runs” does not prove “right version”.
3. Reading an inlined constant might not even trigger initialization of the declaring class at runtime. Do not infer that a class has been loaded or ran `<clinit>` merely because source references `Constants.PORT`.
4. Fields used in `case` labels or annotation values have specific constant-expression requirements; they cannot arbitrarily be replaced with runtime method calls.

## 4. Reproducing experiment: new library, application still prints old constant

Using Java 17 or higher, create the following layout in a separate test directory:

```text
src/
  demo/
    BuildInfo.java
    Client.java
build/
  lib/             (created by javac)
  app/             (created by javac)
```

**File `src/demo/BuildInfo.java` — version 1:**

```java
package demo;

public final class BuildInfo {
    public static final int FORMAT = 1;
    public static final String CHANNEL = "alpha";

    private BuildInfo() { }

    public static int runtimeFormat() {
        return 1;
    }
}
```

**File `src/demo/Client.java`:**

```java
package demo;

public final class Client {
    public static void main(String[] args) {
        System.out.println("FORMAT=" + BuildInfo.FORMAT);
        System.out.println("CHANNEL=" + BuildInfo.CHANNEL);
        System.out.println("runtimeFormat=" + BuildInfo.runtimeFormat());
    }
}
```

In PowerShell, run from the directory containing `src`:

```powershell
New-Item -ItemType Directory -Force build/lib, build/app | Out-Null
javac -d build/lib src/demo/BuildInfo.java
javac -cp build/lib -d build/app src/demo/Client.java
java -cp "build/app;build/lib" demo.Client
```

Run 1 result:

```text
FORMAT=1
CHANNEL=alpha
runtimeFormat=1
```

Now **edit only `BuildInfo.java`**: change `FORMAT = 2`, `CHANNEL = "beta"`, and `return 2;`. Complete contents after editing:

```java
package demo;

public final class BuildInfo {
    public static final int FORMAT = 2;
    public static final String CHANNEL = "beta";

    private BuildInfo() { }

    public static int runtimeFormat() {
        return 2;
    }
}
```

**Recompile only the library**, keeping `build/app/demo/Client.class` intact:

```powershell
javac -d build/lib src/demo/BuildInfo.java
java -cp "build/app;build/lib" demo.Client
```

Run 2 result:

```text
FORMAT=1
CHANNEL=alpha
runtimeFormat=2
```

This is the expected result per compilation mechanics:

- `Client.class` was compiled when `FORMAT` was 1 and `CHANNEL` was `"alpha"`; the old literals sit inside its bytecode.
- Calling `BuildInfo.runtimeFormat()` is a runtime method call, so the JVM executes the new method returning 2.
- No need to suspect the JVM loaded the wrong `BuildInfo.class`: the same single run already read the method's new logic, yet still used the two old constants.

Inspect with `javap`:

```powershell
javap -classpath build/app -c demo.Client
javap -classpath build/lib -verbose demo.BuildInfo
```

In the bytecode of `Client.main`, you will see literals equivalent to `"FORMAT=1"` and `"CHANNEL=alpha"` (javac can fold string concatenation right at compile time), whereas calling `runtimeFormat()` is an `invokestatic` instruction. In the info of the new `BuildInfo`, the constant fields have `ConstantValue` attributes holding 2 and `"beta"`. Exact instruction/constant-pool details may differ across compiler versions; the core point is that **the old literals reside inside `Client.class`**.

Finally, **recompile the calling class**:

```powershell
javac -cp build/lib -d build/app src/demo/Client.java
java -cp "build/app;build/lib" demo.Client
```

Run 3 result:

```text
FORMAT=2
CHANNEL=beta
runtimeFormat=2
```

The experiment uses `;` as the classpath separator per Windows/PowerShell. On Linux/macOS, replace with `:`, e.g. `java -cp "build/app:build/lib" demo.Client`. Directory creation commands can also be replaced with `mkdir -p build/lib build/app`.

### Why do some runs yield different results?

If you run `javac` without controlling source path/classpath, the compiler may locate dependent sources and compile them automatically. The experiment above intentionally separates library and application outputs to control precisely which class gets recompiled. Per `javac` documentation, when both source and class exist on search paths, choosing source or class also depends on paths and source-selection rules. Therefore, use `-d`, `-cp`, `-sourcepath` when needed and verify the actual build commands executed; do not deduce solely from file modification timestamps.

## 5. Stale in bytecode, stale on classpath, or stale in JVM?

### 5.1. Orphan `.class` files in output directories

Suppose the old version had `src/demo/LegacyTool.java`, and later you renamed the source to `ModernTool.java`. Running `javac -d build/classes src/demo/ModernTool.java` creates `ModernTool.class`; that command **does not automatically delete** `build/classes/demo/LegacyTool.class` created earlier. If the packager scans the entire output directory, the artifact may still contain `LegacyTool.class`.

Similarly, when deleting a nested class, renaming a package, or changing a code generator, old generated files can linger. They are not necessarily loaded by the JVM, yet pose a risk worth inspecting because they cause the artifact to carry unintended bytecode.

The remedy is cleaning **only the output directory owned by the build** and recompiling/repackaging. Do not arbitrarily delete source directories or outputs shared with other steps. With build tools providing a `clean` task, run the project's standard task before rebuilding when orphan files are suspected.

### 5.2. Compile classpath differs from runtime classpath

A module may compile against `lib-v2.jar` yet run against `lib-v1.jar`; or conversely, two JARs contain the same class name and the old one is found first. In that case it is not merely *constant inlining*: running code is linking against a different class/library than expected.

To determine class sources when running Java 17+:

```powershell
java -Xlog:class+load=info -cp "build/app;build/lib" demo.Client
```

Logs can be very long; filter by the target class name when investigating. Inside a diagnostic program, you can print the bytecode origin of a class using:

```java
System.out.println(
    BuildInfo.class.getProtectionDomain().getCodeSource()
);
```

This snippet is **illustrative code to place inside a method**, not a standalone runnable Java program. `CodeSource` can be `null` in certain environments (e.g., specially loaded classes); do not treat it as absolute proof across all loaders.

### 5.3. New artifact exists yet the process is still old

Once a JVM process has loaded a class, replacing the JAR on disk does not automatically swap running bytecode. You normally must redeploy the packaged version and restart the process or use an explicitly designed reload mechanism. Verify which JAR is actually inside the container/image, which path the server uses, and whether the process was started from the new artifact.

Do not confuse this with constant bugs: **merely restarting the JVM can still print `FORMAT=1`** if `Client.class` has not been recompiled; restarting cannot erase literals already inlined inside the client's bytecode.

## 6. Binary compatibility: no linkage error can still mean wrong results

JLS `13 describes binary compatibility of compiled classes. For a `static` field that is a *constant variable*, changing the constant value or dropping `final` might not prevent old client binaries from running; those client binaries simply retain the inlined value until recompiled.

Distinguish two families of failures:

| Change | What might old binary clients experience? |
| --- | --- |
| Changing value of `public static final int LIMIT = 10` to 20 | Often runs normally yet still reads 10 if inlined |
| Removing or changing signature of a called method | Can throw `NoSuchMethodError` when linkage/invocation occurs |
| Removing a field that client bytecode actually accesses via `getstatic`/`getfield` | Can throw `NoSuchFieldError` |
| Changing a field from `static` to instance or vice versa | Can throw `IncompatibleClassChangeError` |
| Changing a constant to another value while old client holds no runtime field reference | May raise no error at all, just produce wrong results |

The table describes typical cases; exact errors also depend on the bytecode the client compiled and the specific API change. Do not apply “removing a field always breaks all old clients” to instructions that already inlined literals, because no runtime field reference may remain.

**Source** compatibility (whether it recompiles), **binary** compatibility (whether old binaries link/run), and **semantic** compatibility (whether running produces right results) are three distinct questions. A change can pass the first two yet fail the third.

## 7. Incremental builds, caching, and dependency compilation

Build systems like Gradle/Maven have strategies to decide which tasks must run and which files can be reused. Incremental compilation, build caches, and dependency resolution save time, yet require accurate dependency and input configurations. Do not conclude all incremental compilers mishandle constant inlining: some tools have mechanisms tracking constants affecting dependent classes and triggering necessary compilations.

Issues can still arise when:

- Client and library are built, cached, published, or deployed by **two independent pipelines**.
- Dependencies changed in an external library yet the client artifact was not rebuilt/republished.
- A custom task fails to declare complete inputs/outputs, or stale outputs go uncleaned.
- Local builds use the new library version while CI/deployment resolves to an old version, or reuses the same version for different artifact contents.
- The same class name appears in multiple dependencies and resolution results differ between compile and runtime.

For Gradle, inspect the dependency graph, whether tasks executed or were `UP-TO-DATE`/`FROM-CACHE`, Java compilation settings, and artifact contents. For Maven, verify dependency versions, compile/package phases, and outputs in `target/classes`. **Do not enforce `clean` on every build**: it is a useful diagnostic or recovery step when stale outputs are suspected, whereas fixing root causes requires correcting dependencies, inputs/outputs, versions, or release processes.

## 8. Repeatable diagnostic workflow

When “source changed yet output remained old”, execute in this order to isolate:

1. **Pin down the symptom.** Record expected/actual, build/run commands, JDK, branch, commit, dependency versions, and running artifact. Use an easily recognizable change to verify.
2. **Identify which class is used.** Inspect classpath/module path, resolved dependencies, actual JARs, and class-loading logs. For JARs, `jar tf path/to/library.jar` lists entry names; for packaged copies, use `javap -classpath path/to/library.jar -verbose demo.BuildInfo` to inspect real bytecode.
3. **Compare provider class and caller class.** Inspect `javap -c` of the client for old literals or `getstatic`/`invokestatic` instructions; check `ConstantValue` in the defining class if present. If the literal is inside the client, updating only the library is not enough.
4. **Recompile/repackage affected parts.** Synchronize dependencies, recompile constant-dependent clients, and build a consistent artifact. If orphan outputs or stale input caches are suspected, run a clean build of the exact module and re-verify outputs.
5. **Verify the artifact after building.** Check JAR entries, bytecode, version/build identifiers, and hashes when needed. A successful build does not guarantee the program runs that artifact.
6. **Verify deployment.** Ensure the process/container/worker actually runs the verified build; restart when necessary. Re-run tests/compare logs on the exact artifact being deployed.
7. **Find the root cause.** Why were dependencies, outputs, caches, or releases not updated? Document and fix in the build graph, tasks, or release process so it does not recur.

Example quick-check commands, substituting project paths:

```powershell
javac -version
java -version
javap -classpath build/app -c demo.Client
javap -classpath build/lib -verbose demo.BuildInfo
Get-FileHash build/lib/demo/BuildInfo.class
Get-FileHash build/app/demo/Client.class
```

If using a JAR:

```powershell
jar tf path/to/library.jar
javap -classpath path/to/library.jar -verbose demo.BuildInfo
```

Do not rely solely on timestamps to assert two binaries are identical/different: file copies, filesystems, and build caches can make timestamps misleading. Hashes help compare contents, while `javap` explains bytecode meaning.

## 9. API design and preventive strategies

### 9.1. Use compile-time constants only for genuinely immutable values

Constants carrying immutable API meaning, such as fixed protocol identifiers or mathematical values, can be appropriate to expose via `public static final`. However, if a value can change by release, environment, or configuration, exposing it as a compile-time constant creates stale-client risks.

For example, instead of using `public static final int CURRENT_FORMAT = 1` if this number is frequently updated across releases, switch to an accessor:

```java
package demo;

public final class FormatPolicy {
    private FormatPolicy() { }

    private static final int CURRENT_FORMAT = 2;

    public static int currentFormat() {
        return CURRENT_FORMAT;
    }
}
```

Clients use `FormatPolicy.currentFormat()` and invoke the method on the library version loaded at runtime. The constant value can be optimized **inside** the library itself, yet clients calling the method do not get the number 2 inlined into their bytecode via constant-variable field access. Of course, changing method signatures or deploying the wrong JAR can still break; accessors do not replace version control.

If environment-based configuration is needed, prefer reading from a runtime configuration source with clear governance and testing. Do not use `static final` merely “to shorten code” when values require frequent updates.

### 9.2. Publish a verified set of versions together

- Declare direct dependencies with explicit versions and resolution rules; avoid reusing the same version for different binaries.
- If changing a public constant value that clients depend on, recompile, test, and release affected clients, especially across multi-repo/service boundaries or third-party SDKs.
- Embed a build identifier (version/commit) into artifacts or startup logs, and verify it at runtime during investigation.
- Have CI build artifacts from traceable inputs; inspect JAR contents after packaging and run smoke/integration tests using **the actual artifact**.
- Configure inputs/outputs on custom build tasks accurately so caching/incremental builds operate reliably; consider clean builds when needing to prove reproducibility.

### 9.3. Test at the exact change boundary

A unit test compiling all new sources together may fail to expose bugs because every class is rebuilt. For libraries consumed by released clients, include compatibility tests: compile the client against the old library version, swap the runtime library to the new version, and observe behavior; then recompile the client and compare. The Section 4 experiment is a minimal version of this test.

Do not alter the API merely to avoid build bugs if the constant itself must be used in `switch case` or annotations and is forced to be a compile-time constant: in that case, treat synchronizing/recompiling clients as part of the change contract.

## 10. Self-check understanding

**Scenario A:** `Library.VERSION` is `public static final int VERSION = 1`, you change it to 2 and rebuild the library. An old program still prints 1, yet calls to new methods of the library work properly. Most likely cause?  
**Answer:** Value 1 was inlined into the old program's binary; classes using the constant must be recompiled and that artifact released/deployed.

**Scenario B:** You delete `Obsolete.java`, rebuild some sources, yet `Obsolete.class` remains inside the JAR. Why?  
**Answer:** Previous compile outputs remained in the packaging directory; compiling new files does not mean automatically cleaning all orphan class files. Clean build-owned outputs properly and repackage.

**Scenario C:** Is `public static final String NAME = System.getenv("NAME");` considered a constant variable?  
**Answer:** No; a method call is not a compile-time constant expression. The value is assigned during class initialization, and clients access the field via runtime mechanics (the value also depends on initialization timing and environment).

**Scenario D:** Does restarting the JVM always fix old constant values?  
**Answer:** No. If `Client.class` already inlined the old literal, the new JVM still runs the old bytecode. Confirm the client has been recompiled and redeployed.

**Scenario E:** Does a “binary compatible” change guarantee correct business logic behavior?  
**Answer:** No. Changing a public constant may cause no linkage error yet leave old clients using the wrong value.

## 11. Key takeaways

- `.java` is source; `.class`/JAR is what gets executed. Track the entire chain **compile output → package → runtime**.
- `final` and `static final` do not automatically mean an inlined constant; check **constant variable** per JLS.
- Changing the value of a compile-time constant can require **recompiling clients**, even when the new library is loaded.
- Orphan classes, stale dependencies, mismatched classpaths, and un-restarted processes are distinct causes requiring separate diagnosis.
- Use `javap`, JAR entry listings, class-loading logs, and tests on real artifacts to confirm; use `clean` only with reason and fix the root cause if errors recur.

### Authoritative references

- [JLS `4.12.4 — final variables, constant variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4)
- [JLS `13.4.9 — final fields and static constant variables, binary compatibility](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.9)
- [JLS `15.29 — constant expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.29)
- [javac command documentation (Java 21): classpath, source path, and -d output](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
