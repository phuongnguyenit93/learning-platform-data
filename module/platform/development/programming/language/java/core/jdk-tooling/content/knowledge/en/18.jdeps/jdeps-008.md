# Detecting and Handling JDK Internal APIs with jdeps

## 1. What is a JDK internal API?

**JDK internal APIs** are classes, interfaces, or packages intended for internal JDK implementation. They are not part of the public Java SE API contract that applications can rely on long-term.

Some common examples:

- sun.misc.Unsafe
- jdk.internal.misc.Unsafe
- jdk.internal.reflect.*
- com.sun.org.apache.xerces.internal.*
- com.sun.image.codec.jpeg.*

These APIs may change, become more tightly encapsulated, or be removed between JDK releases. Code that depends on them might run on one JDK but fail when upgrading to another.

You should not conclude that every package starting with sun or com.sun is internal based solely on its name. For example, com.sun.net.httpserver is a publicly provided API in the jdk.httpserver module. Use jdeps analysis results and the JDK API documentation to determine this accurately.

## 2. Why detect internal APIs before upgrading the JDK?

An internal dependency can introduce several risks:

- **Version compatibility:** classes or methods may disappear, change signatures, or change behavior.
- **Encapsulation:** the module system may block access to internal packages.
- **Compilation:** the compiler may warn about proprietary APIs or deny access to unexported packages.
- **Runtime:** the JVM may throw IllegalAccessError or InaccessibleObjectException.
- **Maintainability:** the application depends on implementation details of a specific vendor or JDK build.
- **Platform portability:** code may fail to run on another JDK distribution even on the same Java release.

Since Java 9, JPMS introduced module boundaries and exports/opens mechanisms. JDK 16 and 17 further enforced strong encapsulation for many internal APIs. Some critical APIs are still retained for compatibility, but that does not make them stable Java SE APIs.

Therefore, checking for internal APIs is an important part of JDK upgrades, library upgrades, and preparing modular applications.

## 3. How does jdeps help detect internal APIs?

**jdeps** is a tool for analyzing dependencies of class files, class directories, or JARs. The key option for this topic is:

~~~bash
jdeps --jdk-internals app.jar
~~~

You can also use the older alias:

~~~bash
jdeps -jdkinternals app.jar
~~~

The **--jdk-internals** option instructs jdeps to find class-level dependencies on JDK internal APIs. The output typically shows:

- The artifact or module being analyzed.
- The class in the application that creates the dependency.
- The internal class or package referenced by the application.
- The JDK module containing that API.
- Suggestions or reference links for alternatives, if available.

Example output line:

~~~text
app.jar -> jdk.unsupported
   demo.InternalApiSample -> sun.misc.Unsafe JDK internal API (jdk.unsupported)
~~~

This line indicates that the class demo.InternalApiSample has a dependency on sun.misc.Unsafe, and that dependency resides in the jdk.unsupported module.

jdeps analyzes compiled bytecode rather than reading Java source files directly. Therefore, make sure to build the right artifact before running the tool.

## 4. Creating an example with an internal API dependency

Create the source file at src/demo/InternalApiSample.java:

~~~java
package demo;

import sun.misc.Unsafe;

public class InternalApiSample {
    public static void main(String[] args) {
        System.out.println("Internal type: " + Unsafe.class.getName());
    }
}
~~~

This is an example that intentionally references sun.misc.Unsafe to demonstrate detection. Real-world applications should not use this class just to retrieve a type name.

Compile with JDK 17 or later:

~~~bash
mkdir -p out

javac --release 17 -encoding UTF-8 \
    -d out \
    src/demo/InternalApiSample.java
~~~

The compiler may emit a warning that Unsafe is an internal proprietary API and may be removed in a future release. Successful compilation does not prove that an API is supported long-term.

Run the example:

~~~bash
java -cp out demo.InternalApiSample
~~~

Stdout:

~~~text
Internal type: sun.misc.Unsafe
~~~

Create a JAR for analysis:

~~~bash
jar --create \
    --file app.jar \
    -C out .
~~~

Run jdeps on the JAR:

~~~bash
jdeps --jdk-internals app.jar
~~~

With JDK 24.0.2, this example is detected as a dependency on sun.misc.Unsafe in the jdk.unsupported module. jdeps returns the calling class, the internal API, and a warning about compatibility risks.

The output may vary in paths, formatting, or suggested alternatives depending on the JDK version; focus on the calling class name and the reported internal API.

## 5. Reading and interpreting jdeps output

Example output:

~~~text
app.jar -> jdk.unsupported
   demo.InternalApiSample -> sun.misc.Unsafe JDK internal API (jdk.unsupported)

Warning: JDK internal APIs are unsupported and private to JDK implementation
that are subject to be removed or changed incompatibly and could break your application.
~~~

How to read it:

1. **app.jar:** the analyzed artifact.
2. **jdk.unsupported:** the JDK module providing the referenced internal class.
3. **demo.InternalApiSample:** the application-side class creating the dependency.
4. **sun.misc.Unsafe:** the internal class used by the application.
5. **JDK internal API:** jdeps identifies this as an internal API.

This information helps trace from the dependency back to the source class that needs to be fixed. If a JAR contains multiple packages, do not just look at the module name; read each class-level dependency line.

If multiple classes use the same internal API, group the results by API to determine the scope of changes. A third-party library may introduce a dependency even if the application source does not directly import that API.

jdeps may display replacement suggestions or links to migration documentation. A suggestion is not always a 1:1 replacement; evaluate the actual purpose of the code using the API.

## 6. Analyzing both the application and dependency JARs

An application typically depends on multiple JARs. Analyzing only the main JAR may miss internal APIs located in dependent libraries.

Example structure:

~~~text
project/
├── target/
│   └── app.jar
└── lib/
    ├── legacy-util.jar
    └── vendor-client.jar
~~~

Analyze the application along with the dependency classpath:

~~~bash
jdeps --jdk-internals \
    --class-path "lib/*" \
    target/app.jar
~~~

Depending on the operating system, the classpath separator for multiple paths differs:

- Windows uses a semicolon.
- Linux and macOS use a colon.

In Windows PowerShell, you can write:

~~~powershell
jdeps --jdk-internals --class-path "lib\*" target\app.jar
~~~

jdeps can analyze classes in the input and classpath according to the tool's rules. For large projects, ensure all dependencies that need checking are actually included in the analysis scope.

For libraries resolved via the module path, pass the appropriate module path:

~~~bash
jdeps --jdk-internals \
    --module-path mods \
    --module com.example.app
~~~

If analyzing a standalone library, pass the path to that library's JAR or class directory directly.

## 7. Direct and recursive dependency analysis

Some useful jdeps options:

| Option | Purpose |
|---|---|
| --jdk-internals | Find dependencies on JDK internal APIs. |
| --class-path | Specify the classpath to resolve class dependencies. |
| --module-path | Specify the module path. |
| --module | Select the root module to analyze. |
| -R or --recursive | Recursively analyze runtime dependencies. |
| --no-recursive | Do not traverse dependencies recursively. |
| -include regex | Restrict analyzed classes using a regex. |
| --multi-release | Select the entry version in a multi-release JAR. |
| --api-only | Only analyze dependencies appearing in public/protected APIs. |

Example of recursive analysis:

~~~bash
jdeps --jdk-internals -R \
    --class-path "lib/*" \
    target/app.jar
~~~

Recursive analysis extends runtime dependency traversal according to jdeps' capabilities. Even so, you still need to include the required artifacts on the classpath or module path for the tool to resolve them properly.

If you want to inspect a subset of classes:

~~~bash
jdeps --jdk-internals \
    -include "com.example.*" \
    target/app.jar
~~~

The --jdk-internals option cannot be combined with the -p, -e, and -s filters due to jdeps limitations. If filtering is needed, use -include to restrict the classes being analyzed.

## 8. Multi-release JARs and bytecode versions

A multi-release JAR can contain different versions of classes under the META-INF/versions directory. Which class is selected may depend on the Java version running it.

When analyzing such a JAR, specify the release to inspect:

~~~bash
jdeps --jdk-internals \
    --multi-release 17 \
    app.jar
~~~

The --multi-release value can be an integer from 9 upwards, or base to select the root content of the JAR.

If the application supports multiple JDK releases, you should analyze the releases that the project actually distributes. One version of a class might use an internal API while another version has already replaced it with a public API.

You should not inspect only the base entry and conclude that the entire multi-release JAR is safe.

## 9. Internal APIs in public signatures

A class might not call an internal API in its method bodies, yet still expose an internal type in its public/protected signatures.

For example, a library's public method might accept or return a type that is not part of the public JDK API. In that case, consumers may also be forced to depend on the internal type.

The **--api-only** option helps focus on dependencies appearing in the signatures of public/protected members:

~~~bash
jdeps --api-only --verbose:class app.jar
~~~

This provides an additional perspective when checking library API stability. It does not replace a full scan with --jdk-internals, because internal APIs can still be used inside method bodies or private classes.

During migration, check both questions:

- Are any internal APIs exposed in the public/protected contract?
- Are any internal APIs used inside the implementation?

If an internal type is exposed in a public API, prioritize changing the contract before releasing the next compatible version.

## 10. jdeps and module dependency analysis

jdeps has several module analysis modes. Some commonly used commands:

~~~bash
jdeps --list-deps app.jar
~~~

Prints the module dependencies required by the artifact. The output may include internal modules such as jdk.unsupported if a class references sun.misc.Unsafe.

~~~bash
jdeps --print-module-deps app.jar
~~~

Prints a comma-separated list of module dependencies. The result can be used as input for jlink --add-modules when creating a runtime image.

~~~bash
jdeps --check com.example.app
~~~

Checks the module descriptor and module dependency graph of the specified module.

Distinguish the goals clearly:

- **--jdk-internals:** find class-level dependencies on internal APIs.
- **--list-deps:** view module dependencies.
- **--print-module-deps:** get the module list for creating a runtime image.
- **--check:** verify the module descriptor and dependency relationships.

Seeing jdk.unsupported in the module list is not enough to know which class is using an internal API. Run --jdk-internals to find class-level references.

## 11. Why might jdeps miss some internal API usages?

jdeps analyzes dependencies expressed in class files. Certain dynamic access patterns may not produce class-level references that the tool can detect.

For example:

~~~java
String name = "jdk.internal.misc.Unsafe";
Class<?> type = Class.forName(name);
System.out.println(type.getName());
~~~

The class name is stored as a string. jdeps may not treat that string as a standard class dependency.

Other cases requiring additional checks:

- Class.forName with class names constructed from configuration.
- Reflection based on string package/class names.
- MethodHandles.Lookup and privateLookupIn.
- Native code calling JNI or accessing internal symbols.
- Frameworks/plugins dynamically loading classes from configuration.
- Dependencies loaded at runtime from locations not present on the classpath/module path during analysis.

Therefore, an output with no internal API lines is a good sign, but not absolute proof. Combine jdeps with source search, configuration checks, dependency analysis, and integration tests.

You can search for suspicious package names in the source:

~~~bash
rg -n "sun\.|com\.sun\.|jdk\.internal\." src
~~~

This is only a screening step. Inspect each match, as some APIs with the com.sun prefix are still supported public APIs.

## 12. Choosing replacement APIs

Replacing an internal API should be based on the purpose for which the code is using it, not just the class name.

| Internal API or purpose | Public replacement direction |
|---|---|
| sun.misc.BASE64Encoder / BASE64Decoder | java.util.Base64. |
| Field access and atomic/ordering operations via Unsafe | VarHandle, java.lang.invoke, and appropriate concurrency APIs. |
| Native/off-heap memory access via Unsafe | Foreign Function & Memory API in modern JDKs; check the application's JDK baseline. |
| Internal XML parser/transformer | JAXP, javax.xml.parsers, javax.xml.transform, org.w3c.dom, and org.xml.sax. |
| Internal JPEG codec | javax.imageio.ImageIO. |
| Creating instances bypassing constructors via ReflectionFactory or Unsafe | Design explicit constructors/factories or use supported serialization APIs if applicable. |

Some internal APIs do not have an exact equivalent replacement. For example, Unsafe provides many low-level capabilities; VarHandle and the Foreign Function & Memory API only replace their respective groups of use cases.

For native memory access in newer JDKs, the Foreign Function & Memory API resides in the java.lang.foreign package and was finalized in JDK 22. If the application still supports older JDKs, choose a solution compatible with the baseline or adjust the upgrade plan.

You should not replace one internal API with another internal API just because the new one seems more convenient. The goal is to move to a public, documented contract with a clear compatibility policy.

## 13. Temporary workarounds with --add-exports and --add-opens

During migration, it is sometimes necessary to keep the application running while dependencies cannot yet be replaced immediately.

The **--add-exports** option allows a module to export an additional package to another module:

~~~bash
java --add-exports java.base/jdk.internal.misc=ALL-UNNAMED \
    -cp app.jar \
    com.example.Main
~~~

The example above grants access to public types in the jdk.internal.misc package of the java.base module for code on the classpath (the unnamed module).

The **--add-opens** option is for deep reflection at runtime:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
    -cp app.jar \
    com.example.Main
~~~

The two options serve different purposes:

- --add-exports allows access to public types/members in the additionally exported package.
- --add-opens allows deep reflection into non-public members of the package at runtime.

For named modules, replace ALL-UNNAMED with the appropriate target module name.

This is a temporary compatibility workaround, not a way to turn an internal API into a supported one. Document the opened/exported package/module, the reason, the dependent component, and the target removal date.

The --illegal-access option is no longer a general mechanism for restoring broad access to internal APIs on modern JDKs. Do not rely on it as a migration plan.

## 14. Internal dependency migration workflow

A practical workflow can follow these steps:

1. Build the entire application and libraries at the exact version intended for release.
2. Run jdeps --jdk-internals on the main JAR and key dependencies.
3. Record the calling class, internal API, JDK module, and related dependency artifact.
4. Determine whether the dependency comes from the application's source or a third-party library.
5. Examine the actual use case to select an appropriate public Java SE or JDK API.
6. Replace the implementation and update dependencies if external libraries already have fixes.
7. Remove --add-exports or --add-opens options that are no longer needed.
8. Compile and run tests on the lowest JDK baseline supported by the project.
9. Re-run jdeps to confirm internal dependencies are gone or have documented exceptions.
10. Integrate the check into CI to catch new dependencies before merge/release.

If the dependency comes from a third-party library, you may need to upgrade the library, replace it, or request a fix from the vendor. Do not patch the JDK to keep the application running with internal APIs.

## 15. Integrating internal API checks into CI

You can add an analysis step after building the JAR:

~~~bash
jdeps --jdk-internals \
    --class-path "target/lib/*" \
    target/application.jar
~~~

Read the output and save the log as a build artifact. If the organization wants to block new dependencies, write a CI script to inspect the jdeps output and fail when a JDK internal API line is detected.

A CI pipeline can include:

- Building the JAR/module.
- Collecting dependencies matching the runtime packaging.
- Running jdeps --jdk-internals.
- Checking against approved dependencies or those with migration tickets.
- Running unit tests and integration tests on the target JDK.
- Storing the dependency report alongside the release artifacts.

Do not use --quiet to suppress warnings when checking for internal APIs. Keep the diagnostics so you know which class and API create the dependency.

If temporary exceptions are allowed, clearly record the owner, reason, related library version, and expected removal date. Periodically re-run jdeps after upgrading the JDK or dependencies.

## 16. Common issues when analyzing internal APIs

| Symptom | Possible cause | Resolution |
|---|---|---|
| jdeps does not report an internal API even though the source imports it | Analyzing the wrong artifact or forgetting to rebuild. | Rebuild and run on the correct class/JAR. |
| Only the jdk.unsupported module is shown | Viewing module dependencies only, without a class-level report. | Use --jdk-internals. |
| Unable to resolve dependency classes | Missing classpath or module path. | Pass the correct --class-path or --module-path. |
| Multi-release JAR gives different results | Version-specific entry not selected. | Use --multi-release with the release to inspect. |
| jdeps misses Class.forName | Dependency is constructed dynamically from a string. | Search source/config and run integration tests. |
| Internal API still runs on the current machine | Some APIs are still retained for compatibility. | Still treat it as a risk and plan a replacement. |
| --add-exports does not fix reflection errors | Package needs to be opened for deep reflection. | Identify the exact use case and consider temporary --add-opens. |
| Some com.sun packages are flagged as suspicious | Using the prefix as the sole criterion. | Check jdeps output and the API documentation for that specific package. |
| Third-party library introduces the dependency | The internal API is inside a dependency JAR. | Upgrade, replace the library, or request a fix. |
| No direct replacement exists | The internal API provides specific low-level behavior. | Analyze the use case and redesign using appropriate public APIs. |

## 17. Pre-release checklist

- [ ] Ran jdeps --jdk-internals on the built JAR or module.
- [ ] Analyzed key dependencies on the classpath/module path as well.
- [ ] Recorded calling classes, internal APIs, and containing modules.
- [ ] Checked multi-release JARs if used by the project.
- [ ] Distinguished between direct dependencies, library dependencies, and dynamic access.
- [ ] Checked source/config for reflection or string-based class names.
- [ ] Selected replacement public APIs based on actual use cases.
- [ ] Removed unnecessary --add-exports/--add-opens options.
- [ ] Tested on the JDK releases supported by the project.
- [ ] Integrated jdeps into CI or the dependency upgrade workflow.
- [ ] Documented owners and deadlines for any remaining exceptions.
- [ ] Re-ran analysis after changing the JDK or dependencies.

jdeps helps detect static dependencies on JDK internal APIs and pinpoints the classes creating those links. By combining this report with source inspection, selecting public replacement APIs, and testing on the target JDK, teams can reduce runtime upgrade risks and maintain long-term compatibility.