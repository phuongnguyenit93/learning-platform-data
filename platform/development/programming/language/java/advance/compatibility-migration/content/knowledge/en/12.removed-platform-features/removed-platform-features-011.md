# Verifying the Removal Catalog per JDK Instead of Inferring from Old Warnings

In a **Java Advance Compatibility Migration** project, a deprecation warning is a signal to investigate, not final proof that an API or tool has been removed. A component once marked deprecated may still exist across many Java releases; conversely, an already removed API might no longer appear in a newer JDK's deprecation report. When the runtime denies access to an internal class, the cause may also be strong encapsulation rather than the class having disappeared.

Therefore, the catalog must be built based on **source JDK, target JDK, distribution, component type, change source, and actual evidence**, rather than copying a list of warnings from an older Java version. This lesson presents how to classify, verify, and record APIs, modules, tools, and JVM options that may impact a Java upgrade.

## 1. Questions to Answer Before Concluding an API Was Removed

A useful conclusion must clearly state:

- **Which component?** The full name of the class, method, module, executable, or VM option.
- **From which version to which version?** For example, JDK 8 to JDK 17, rather than simply writing "new Java".
- **Which distribution and environment?** Full JDK or custom runtime image, OS, and CPU architecture.
- **What happened?** Failed to compile, failed to load a class, tool missing, access denied, or behavior changed.
- **What is the evidence?** Release notes, JEPs, API docs, commands on the target JDK, logs, or tests.
- **Which consumers are affected?** Application, library, plugin, code generator, build script, or Java agent.

The statement "API X does not run on Java 17" is not enough to decide how to fix it. If the API was removed from the JDK, an alternative is needed; if the API still exists but the package is not opened, JPMS access permissions must be addressed or internal reflection removed. These two cases differ in nature.

## 2. Distinguishing Commonly Confused Statuses

| Status | Meaning | Verification approach |
|---|---|---|
| Available | Component is present on the inspected JDK | API docs, module list, tool checks, and compilation |
| Deprecated | Component still exists but is discouraged for new code | Annotations, Javadoc, and deprecation reports |
| Deprecated for removal | Vendor announces intent to remove in the future | Deprecation documentation and release notes; do not infer a removal date |
| Removed | Component is no longer provided in the JDK release under review | Release notes/JEPs and direct inspection of the target JDK |
| Strongly encapsulated | Member or package still exists but access is restricted | JPMS messages, exports, opens, and reflection tests |
| Unbundled | Component is no longer bundled with the JDK by default; external packages may be available | Release notes and standalone dependencies |
| Disabled or unsupported | Traces of API/tool remain, but the old mechanism no longer works or is unsupported | Documentation and runtime behavior |
| Vendor-specific | Component depends on the JDK distribution or build | Vendor policy, package lists, and exact version |

An item may change status across releases. However, **deprecated for removal** does not mean "removed in the next release", and "absent from the runtime image" does not mean "removed from the Java SE specification".

### 2.1. Example of Deprecated but Not Yet Removed

~~~java
/**
 * @deprecated Use the replacement method instead.
 */
@Deprecated(since = "2.1", forRemoval = true)
public void oldOperation() {
    // Existing implementation.
}
~~~

In the release containing the declaration above, the method still exists and callers can continue invoking it if access conditions are met. The annotation informs tools of the deprecation intent; it does not automatically remove the method from class files.

If a subsequent release actually removes the method, source consumers may fail to recompile, while old bytecode consumers may encounter `NoSuchMethodError` when calling it. The migration catalog should separately record **the milestone where deprecation started** and **the milestone where removal was confirmed**.

### 2.2. Example of Inaccessible but Not Necessarily Removed

~~~java
import java.lang.reflect.Field;

Field field = String.class.getDeclaredField("value");
field.setAccessible(true);
~~~

On a modern JDK, `setAccessible(true)` may throw `InaccessibleObjectException` because `java.base` does not open `java.lang` to the calling module. This is an **access restriction** issue. Do not mark that private field as "removed" solely due to lacking deep reflection permission.

If `getDeclaredField` throws `NoSuchFieldException`, that is a different sign: a member with that searched name does not exist under that lookup. Internal details of `String` can change between JDKs, so relying on internal fields is discouraged.

## 3. Old Warnings Only Reflect a Single Point in Time

A compiler warning might look like this:

~~~text
[removal] oldMethod() has been deprecated and marked for removal
~~~

That describes how the compiler of the currently used release views oldMethod, not its full history. Specifically:

1. The API may only be newly deprecated and still run.
2. The API may already be removed in the target JDK even though there was previously only a warning.
3. The API may no longer be in the API set for `jdeprscan` to report.
4. The warning may come from a third-party dependency rather than a JDK API.
5. A removed tool may not produce a compile warning because the pipeline only invokes an executable.
6. Reflection using class names in strings may not create symbolic references that static analysis can find.

Therefore, warnings must become **candidates in the investigation catalog**, not a pre-assigned "REMOVED" label.

## 4. Do Not Use a Single Common Java Version Number for All Components

The Java SE feature release, JDK update/build, and JDK distribution are distinct pieces of information. For instance, Java 17 identifies the platform generation, yet JDK 17 releases from different vendors may differ in patches, packaging tools, and supported OS scope.

When recording results, include at a minimum:

~~~yaml
source:
  javaFeature: 8
  vendor: "record actual vendor"
target:
  javaFeature: 17
  updateBuild: "record exact build"
  vendor: "record actual vendor"
  os: "linux-x64"
subject:
  kind: "jdk-module"
  name: "example.module"
~~~

This YAML example only illustrates the record structure, not proof that a specific module has been removed.

You must also distinguish a full JDK from a runtime image created with `jlink`. A module omitted from an application's runtime image may still be provided in the full JDK of the same release.

## 5. Cross-Referencing Release Documentation per JDK

Important sources include:

| Source | Used to verify | Should not infer |
|---|---|---|
| Target JDK release notes | Features, tools, modules, and options changed or removed | Not a catalog of every consumer issue |
| JDK Migration Guide | Key points to watch and transition guidance | Not guaranteed to cover every non-Java SE API |
| JDK Enhancement Proposal (JEP) | Scope, rationale, and design of a change | A proposal is not guaranteed to be delivered in the originally expected release |
| Java SE API docs | Whether a class/method is present, deprecated, or for removal | Absence alone does not pinpoint the exact first release of removal |
| Module descriptors and JDK module list | Modules and package exports/opens in a specific runtime | Does not prove all APIs or behavior |
| Vendor release notes | Differences in builds, packaging, and support | Does not replace actual consumer testing |
| Logs, compiler, and tests | Impact on a specific application | Only covers the tested JDK, code paths, and environment |

When using a JEP, confirm which release it was integrated into, rather than taking a JEP still under discussion as proof that an API has disappeared. For future changes, use the status **planned** or **proposed**, not **removed**.

## 6. Illustrative Historical Milestones: Classifying Correctly

The following table only illustrates common types of changes; **it is not an exhaustive catalog for each JDK**.

| Release | Component | Nature of change |
|---|---|---|
| JDK 9 | `rt.jar` and `tools.jar` under the JDK 8 layout | Runtime/tooling layout change when moving to a modular runtime image |
| JDK 11, JEP 320 | Java EE and CORBA modules previously bundled in the JDK | Removal of modules and related components from the JDK |
| JDK 14, JEP 367 | Pack200 API and pack200/unpack200 tools | Removal of the Pack200 API and packaging tools |
| JDK 15, JEP 372 | Nashorn JavaScript engine and jjs tool | Removal of engine/tool; not removal of the entire Java Scripting API |
| JDK 17, JEP 407 | RMI Activation | Removal of RMI Activation, not all of Java RMI |
| JDK 17, JEP 403 | Strong encapsulation of JDK internals | Tightening access control, not automatically equivalent to deleting classes |

Several examples show why statuses must be written accurately.

### 6.1. JDK 9 and Runtime Layout

On many JDK 8 installations, scripts may reference paths like:

~~~text
$JAVA_HOME/jre/lib/rt.jar
$JAVA_HOME/lib/tools.jar
~~~

In JDK 9, the runtime image was organized by modules. The old JAR paths are no longer valid, but that **does not mean every class previously in rt.jar was deleted**. The change may lie in how build tools or scripts locate runtime classes.

The solution is to use supported compilers, APIs, and module/classpath mechanisms rather than relying directly on the old JDK installation layout.

### 6.2. JDK 11 and Java EE/CORBA Modules

A JDK 8 application might use:

~~~java
import javax.xml.bind.JAXBContext;

JAXBContext context = JAXBContext.newInstance(Customer.class);
~~~

The modules previously built into the JDK were removed under JEP 320 in JDK 11. Without adding appropriate dependencies, consumers may encounter compile errors such as:

~~~text
package javax.xml.bind does not exist
~~~

or runtime errors such as:

~~~text
java.lang.NoClassDefFoundError: javax/xml/bind/JAXBContext
~~~

This does not prove JAXB technology is completely unusable. You can select an independently distributed JAXB API and implementation, and check versions, classpath, module path, and compatibility. Note that the `javax.xml.bind` namespace differs from `jakarta.xml.bind` in newer generations; swapping dependencies is not necessarily a one-to-one binary drop-in replacement.

### 6.3. JDK 14 and Pack200

If the pipeline uses the `pack200` or `unpack200` executables, or references the `java.util.jar.Pack200` API, verify the change against JEP 367 and on the target JDK. Because this is a packaging tool, the main Java application may still compile while the build/release pipeline breaks.

The inventory item needs to identify the owner of the packaging script and the replacement plan, rather than checking only Java imports.

### 6.4. JDK 15 and Nashorn

The Java Scripting API may be used as follows:

~~~java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("nashorn");
~~~

When Nashorn is no longer bundled with the JDK, the Java Scripting API does not necessarily disappear; the `getEngineByName("nashorn")` method may return `null` if no matching engine is on the classpath/module path. Therefore, the accurate report is **Nashorn engine/tool removed**, not `ScriptEngineManager` removed.

### 6.5. JDK 17 and RMI Activation

JEP 407 removed RMI Activation. An application using RMI must distinguish whether it genuinely uses the activation mechanism or only other RMI features. Writing "Java RMI was removed in Java 17" conflates the scope and can lead to unnecessary changes.

### 6.6. JDK 17 and Strong Encapsulation

JEP 403 enforces strict strong encapsulation on JDK internals. An older library may fail on `setAccessible(true)` even though the class still exists. Record the status as **access restricted**, not **removed**, and then consider upgrading the library or eliminating access to private internals.

## 7. First Step: Identify the JDK Actually Being Used

Run the appropriate commands for the right process/environment:

~~~bash
java -version
javac -version
jdeps --version
~~~

If the build uses Gradle, check the Gradle runtime:

~~~bash
./gradlew -version
~~~

However, the Java toolchain for compilation, the Gradle daemon, the test JVM, and the production JVM may differ. A migration catalog must thoroughly record:

- Java feature/update/build and vendor of the compiler.
- Java feature/update/build and vendor of the actual runtime.
- OS, architecture, container image, or custom runtime image.
- Versions of build tools/plugins/agents that might use internal JDK APIs.
- Classpath/module path and dependency graph.

Do not use a single `java -version` output on a personal machine to declare production verified.

## 8. Building a Candidate List from Source, Dependencies, and Scripts

Before looking up release notes, identify what the project actually uses:

- Imports and method calls to old JDK APIs.
- Classes loaded via `Class.forName`.
- Private field access via `getDeclaredField` and `setAccessible`.
- JDK tools invoked from Gradle/Maven, shell scripts, or CI.
- JVM options in Dockerfiles, startup scripts, and service managers.
- JNI/native code or Java agents.
- Binary dependencies and shaded/fat JARs.

Example preliminary search using ripgrep, if installed:

~~~bash
rg -n "javax\.xml\.bind|javax\.xml\.ws|java\.util\.jar\.Pack200" src
rg -n "sun\.|jdk\.internal\.|Class\.forName|setAccessible" src
rg -n "rt\.jar|tools\.jar|pack200|jjs|--illegal-access" .
~~~

Results are only **candidates**. Code inside external JARs may not appear in the source repository, while comments or documentation may produce false positives. When needed, supplement with inventories of dependencies, modules, and automatically generated code.

## 9. Checking Modules Directly on the Target JDK

The commands below must be run on the **JDK/runtime image being evaluated**:

~~~bash
java --list-modules
~~~

You can view the description of a specific module:

~~~bash
java --describe-module java.xml
~~~

If a module does not exist in the runtime, that proves **the runtime under test does not provide that module**. To know the first release that removed it, cross-reference historical documentation. If checking only an image created with `jlink`, the missing module may be due to the image builder intentionally excluding it.

Distinguish between:

- Module not found.
- Module exists, but the package is not exported.
- Package is exported, but not opened for deep reflection.
- API resides in an external dependency rather than a JDK module.

Each case leads to a different solution.

## 10. Testing with the Target JDK Compiler and Runtime

A source probe can help verify whether an API is available for compilation:

~~~java
import javax.xml.bind.JAXBContext;

public class ApiProbe {
    JAXBContext context;
}
~~~

If the goal is to see whether the full target JDK still provides the package, try compiling **without adding external dependencies**:

~~~bash
javac ApiProbe.java
~~~

The error `package ... does not exist` is a concrete observation. However, it does not tell you whether the API never existed, was removed, is a missing dependency, or simply failed to resolve. Cross-reference documentation and the classpath/module path.

If using a newer compiler to select the Java SE API set of a lower release:

~~~bash
javac --release 17 ApiProbe.java
~~~

`--release` sets the language level, class-file target, and Java SE API set allowed by the compiler. It does not prove that every library outside Java SE, JDK modules outside that scope, or the production runtime image are compatible. To confirm a specific tool/module is provided on the target JDK, check separately using that JDK.

### 10.1. Binary and Runtime Evidence

If old bytecode calls a member no longer present in the new JDK, the error may be `NoSuchMethodError` or `NoSuchFieldError`. When a class fails to load, `NoClassDefFoundError` may occur. However, these errors can also come from external libraries or a misconfigured classpath.

Some errors that are easily lumped together:

| Error | First check direction |
|---|---|
| `cannot find symbol` | Source signature, compiler, API, and dependencies |
| `NoClassDefFoundError` | Classpath/module path, missing dependency, class loading |
| `NoSuchMethodError` | Binary API change or version conflict |
| `InaccessibleObjectException` | JPMS opens and deep reflection |
| `IllegalAccessError` | JVM access/linkage and exports |
| `UnsupportedClassVersionError` | Class-file version higher than the runtime JVM |
| `Unrecognized VM option` | JVM option not recognized by the current build |

Do not collapse all of them into a single "removed JDK API" label.

## 11. `jdeprscan`: Detecting Deprecation, Not Reconstructing Removal History

`jdeprscan` helps find bytecode references to deprecated Java SE APIs according to the release data provided by the tool.

Example:

~~~bash
jdeprscan --release 17 app.jar
~~~

To focus on APIs marked for removal:

~~~bash
jdeprscan --release 17 --for-removal app.jar
~~~

Before running, check the releases and options supported by that tool version:

~~~bash
jdeprscan --help
~~~

This tool is useful for finding which consumers rely on APIs flagged at the deprecation level. However, remember:

1. `--for-removal` does not provide a guaranteed removal date.
2. An API already removed from the analyzed release does not necessarily appear in the deprecated catalog.
3. Dynamic reflection and native code may go undetected.
4. The tool does not replace checking executables, JVM options, or dependencies outside Java SE.
5. Results depend on the artifacts and dependency paths supplied.

Therefore, the appropriate label is **deprecated / deprecated for removal detected**, not automatically converted to **removed in target**.

## 12. `jdeps`: Finding Static References to Internal JDK APIs

To inventory bytecode dependencies on JDK internals:

~~~bash
jdeps --jdk-internals app.jar
~~~

With runtime libraries on the classpath:

~~~bash
jdeps --jdk-internals --recursive \
  --class-path "lib/*" app.jar
~~~

A warning pointing to `sun.misc.Unsafe` shows that the application depends on an internal API recognized by the tool. It **does not by itself confirm the class has disappeared**. Some critical internal APIs may still be provided via the `jdk.unsupported` module in modern releases, but without a public Java SE contract like standard APIs.

Furthermore, `jdeps` performs static analysis. It does not guarantee detection of code accessed only via strings/reflection, dynamically generated bytecode, JNI, or plugins excluded from the scan set.

You can use:

~~~bash
jdeps --list-deps app.jar
~~~

to assist in inspecting module dependencies. This list also does not cover every dependency that is loaded only dynamically.

## 13. Checking Executables and JVM Options Separately from Java APIs

A build pipeline may invoke old JDK tools even when the source code does not import any related API. Therefore, inspect the bin directory of the target JDK directly.

Linux/macOS example:

~~~bash
"$JAVA_HOME/bin/java" -version
ls "$JAVA_HOME/bin"
~~~

PowerShell example:

~~~powershell
& "$env:JAVA_HOME\bin\java.exe" -version
Get-ChildItem "$env:JAVA_HOME\bin"
~~~

Do not simply invoke `pack200` or `jjs` via PATH because PATH may point to a different JDK or a separately installed executable. Record the exact JDK and path used for verification.

Similarly, JVM options can be deprecated, obsoleted, ignored, renamed, or rejected. For example, the `--illegal-access` mechanism from the JPMS transition period no longer works as a way to enable global access in JDK 17 and later. This is a **change in option capability**, not a removal of the entire Java reflection API.

When reading an "Unrecognized VM option" log, verify the option, vendor/build, startup command line, and runtime documentation. Do not modify Java imports if the error actually lies in a startup script.

## 14. Distinguishing JDK Changes from Third-Party Library Changes

Some APIs carry `javax.*` package names without necessarily belonging to Java SE. When a module previously packaged with the JDK is no longer available, the solution may be selecting a supported external library and verifying the namespace.

For example:

~~~java
import javax.xml.bind.JAXBContext;
~~~

and:

~~~java
import jakarta.xml.bind.JAXBContext;
~~~

are not two names that are binary-compatible by default. When moving to a new Jakarta version, evaluate imports, dependencies, serializer behavior, and module/classpath configuration.

If a method is removed by a framework or ORM when upgrading dependencies, record it as a **third-party API change**, not wrongly attributed to a Java feature release. If a JAR is missing from a new container yet present in the old system, it may be a **packaging/deployment change**. Correct classification helps assign the right owner.

## 15. Status Catalog Template per Target JDK

Each record should be specific enough for someone else to re-verify:

| Field | Data to record |
|---|---|
| Component | Exact fully qualified name or tool/flag |
| Kind | Java SE API, JDK internal, JDK module, executable, VM option, third-party |
| Source JDK | Feature, update/build, vendor |
| Target JDK | Feature, update/build, vendor, runtime image |
| First removed in | Fill in only when confirmed by historical evidence |
| Status on target | Present, deprecated, for-removal, removed, encapsulated, unbundled, unsupported, unknown |
| Consumer | Module, application, plugin, script |
| Evidence reference | Release notes/JEP/API docs and test logs |
| Impact | Compile, linkage, runtime, build, behavior |
| Replacement | New API, dependency, tool, or design |
| Owner | Responsible team and target timeframe |

An example record:

~~~yaml
component: "javax.xml.bind.JAXBContext"
kind: "historically bundled JDK module API"
sourceJdk:
  feature: 8
  vendor: "to be filled"
targetJdk:
  feature: 17
  vendor: "to be filled"
statusOnTarget: "not bundled with target JDK"
historicalReference: "JDK 11 release notes / JEP 320"
consumer:
  name: "example-service"
  owner: "example-team"
evidence:
  compileWithoutExternalDependency: "NOT_YET_RUN"
  compileWithReplacementDependency: "NOT_YET_RUN"
replacement: "supported JAXB API/implementation"
~~~

This illustrative data is not yet a test result. During actual verification, save the commands, logs, artifact checksums, dependency versions, OS, and execution date.

### 15.1. JDK Matrix

| Component | JDK 8 | JDK 11 | JDK 17 | JDK 21 | Notes |
|---|---|---|---|---|---|
| Old `rt.jar` layout | Present in common JDK 8 builds | No longer uses old layout | No longer uses old layout | No longer uses old layout | Do not infer all APIs are gone |
| JDK-bundled JAXB | Present in many JDK 8 builds | Removed from JDK | Not bundled with JDK | Not bundled with JDK | May require external dependencies |
| JDK Pack200 | Present | Present, but targeted for removal | Removed from JDK | Removed from JDK | Affects tooling |
| Built-in Nashorn | Present in JDK 8 | Present | Removed from JDK | Removed from JDK | Scripting API is a separate issue |
| RMI Activation | Present in older releases | Still present before removal milestone | Removed per JEP 407 | Old mechanism absent | Does not mean all of RMI is gone |
| JPMS strong encapsulation | No JPMS yet | JPMS present with transitional mechanism | Stricter enforcement | Continues to apply | Distinguish permission vs. removal |

The table only illustrates the components discussed, not a certification for all JDK distributions. If targeting another JDK, verify it separately rather than copying the JDK 21 column onto newer versions.

## 16. Repeatable Verification Process

### Step 1: Lock Down Source and Target

Record the JDK feature/update, distribution, OS, Java compiler/runtime, and packaging method. If the system supports both JDK 17 and 21, collect corresponding evidence for both.

### Step 2: Collect Candidates

Scan source code, dependencies, JARs, plugins, build scripts, runtime flags, and warning logs. Do not mark items as removed at this step.

### Step 3: Classify

Distinguish deprecated, for-removal, removed, unbundled, encapsulated, disabled, and third-party changes. Record each component along with its owner.

### Step 4: Consult the Exact Release Documentation

Cross-reference release notes, migration guides, JEPs, and API/module docs to determine in which version the change occurred and its scope.

### Step 5: Verify Using the Target JDK

Run module/tool inventory checks, compile probes, `jdeprscan`, `jdeps`, and runtime tests as applicable. Record commands, versions, and logs.

### Step 6: Test Consumers

Recompile source to check source compatibility; test existing consumer bytecode on the new runtime to check linkage; run integration/contract tests to verify behavior. Ensure tests exercise code paths that use the suspected components.

### Step 7: Choose a Replacement Solution

Prefer supported APIs, suitable external libraries, or new tools. If using `--add-opens` as a workaround, clearly document that it is a temporary access solution, not a restoration of a stable contract for internal APIs.

### Step 8: Record Conclusions and Limitations

Each item should have a status, tested JDK, supporting source, test results, owner, unmitigated risks, and review date. Items lacking sufficient evidence should retain the **UNKNOWN** or **NEEDS_VERIFICATION** label, rather than being grouped under REMOVED.

### Step 9: Re-verify When Changing the Target JDK

A conclusion on JDK 17 does not automatically prove the status on JDK 21 or JDK 25. When changing the target JDK, check release notes and rerun key verifications.

## 17. Mistakes to Avoid

**"For removal" means "already removed".** False: you must verify the status on the target release.

**"There are no warnings, so no APIs were removed."** Removed APIs may have already disappeared from the deprecation set.

**"InaccessibleObjectException means the class disappeared."** Usually it means deep reflection is disallowed across module boundaries.

**"No rt.jar means all APIs inside rt.jar are gone."** A runtime layout change is different from API removal.

**"No JAXB in the JDK means JAXB cannot be used."** You can select appropriate external dependencies and verify actual compatibility.

**"Nashorn removed means javax.script was removed."** The engine/tool and the scripting API are different scopes.

**"JDK 17 removed all of RMI."** JEP 407 is only about RMI Activation.

**"jdeprscan --for-removal generates a complete removal catalog."** The tool detects a set of deprecations; it does not reconstruct full history.

**"If jdeps reports nothing, there are definitely no internal APIs."** Dynamic reflection and unanalyzed dependencies remain blind spots.

**"One check on a developer machine suffices for all subsequent JDKs."** Conclusions must be tied to the tested JDK/runtime and consumers.

## 18. Checklist Before Finalizing the Catalog

- [ ] Accurately recorded source JDK, target JDK, vendor/build, and runtime image.
- [ ] Fully identified suspected classes/methods/modules/tools/flags.
- [ ] Distinguished deprecated, for-removal, removed, encapsulated, and unbundled.
- [ ] Separated JDK changes from third-party library and packaging changes.
- [ ] Cross-referenced release notes/JEPs/migration guides for the exact versions.
- [ ] Avoided assigning a first removed release without historical evidence.
- [ ] Checked modules/packages/tools on the target JDK.
- [ ] Checked compiler, runtime, classpath/module path, and dependencies.
- [ ] Understood the limitations of `jdeprscan` and `jdeps`.
- [ ] Checked reflection, JNI, build scripts, and JVM options where relevant.
- [ ] Ran consumer tests on critical code paths.
- [ ] Saved commands, outputs, JDK build, owner, and replacement plan.
- [ ] Items lacking sufficient evidence still have an explicit pending-verification status.

## Conclusion

**The removal catalog must be verified per JDK rather than inferred from old warnings.** Deprecated, deprecated for removal, removed, unbundled, encapsulated, and disabled are distinct statuses leading to different migration decisions. Compiler warnings and static tools are inputs for investigation; release notes, JEPs, API/module inventories, and compile/runtime results on the target JDK are what establish an evidence-based conclusion.

By clearly recording the component, source/target JDK, consumers, evidence, verification scope, and replacement solution, the team can handle legacy APIs and tools properly, avoid unnecessary changes, and reliably repeat verification in future Java upgrades.
