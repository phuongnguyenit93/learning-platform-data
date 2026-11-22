# Classpath Analysis with jdeps

§jdeps§ is a JDK tool for analyzing dependencies of Java class files. When working with an application or library running on the classpath, §jdeps§ helps identify which packages and classes are referenced, which external libraries are needed to resolve those references, and which Java platform modules are used.

Classpath analysis is useful when inspecting a JAR before release, finding missing dependencies, detecting the use of JDK internal APIs, preparing to migrate a library to JPMS, or determining the modules required for a runtime image with §jlink§.

This article uses JDK 17 or later. It covers everything from selecting inputs and providing the classpath to package/class analysis levels, filtering results, detecting missing dependencies, exporting graphs, and interpreting the limitations of static analysis.

## 1. What does jdeps analyze?

§jdeps§ reads bytecode in class files and finds identifiable dependency references. Inputs can be:

- A §.class§ file.
- A directory containing class files.
- A JAR containing compiled classes.
- Multiple classes, directories, or JARs passed as input.

General syntax:

~~~text
jdeps [options] path ...
~~~

Each input is a component to be analyzed. The §--class-path§ option provides additional locations for §jdeps§ to search for classes referenced by the input.

Example:

~~~powershell
jdeps app.jar
~~~

This command analyzes the visible dependencies in §app.jar§. The default output focuses on the package level, showing which packages depend on which packages or modules.

Key distinctions:

- **Input path:** the class file, directory, or JAR that you want to analyze.
- **Class path:** additional directories/JARs used to resolve classes referenced from the input.
- **Module path:** where to find named modules when analyzing an application that uses JPMS.

If a library is located at §lib/customer.jar§, passing only §app.jar§ as input is not enough for §jdeps§ to resolve all references to that library. Provide the library via §--class-path§.

## 2. Preparing an example with an external dependency

Let's create a classpath application consisting of two JARs:

- §customer.jar§ containing the §com.example.model.Customer§ class.
- §app.jar§ containing the main class §com.example.app.Main§ and referencing §Customer§.

Structure:

~~~text
project/
├── src/
│   ├── lib/
│   │   └── com/example/model/Customer.java
│   └── app/
│       └── com/example/app/Main.java
├── build/
│   ├── lib-classes/
│   └── app-classes/
├── lib/
│   └── customer.jar
└── app.jar
~~~

Contents of §src/lib/com/example/model/Customer.java§:

~~~java
package com.example.model;

public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

Contents of §src/app/com/example/app/Main.java§:

~~~java
package com.example.app;

import com.example.model.Customer;
import java.time.LocalDate;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Ada" : args[0];
        Customer customer = new Customer(name);
        System.out.println(customer.name() + " | " + LocalDate.of(2026, 1, 1));
    }
}
~~~

From the §project§ root directory, compile and package the library first.

PowerShell on Windows:

~~~powershell
New-Item -ItemType Directory -Force -Path build/lib-classes, build/app-classes, lib | Out-Null
javac -d build/lib-classes src/lib/com/example/model/Customer.java
jar --create --file lib/customer.jar -C build/lib-classes .
~~~

Compile the application with the library on the classpath:

~~~powershell
javac --class-path lib/customer.jar -d build/app-classes src/app/com/example/app/Main.java
jar --create --file app.jar --main-class com.example.app.Main -C build/app-classes .
~~~

Run the application:

~~~powershell
java --class-path "app.jar;lib/customer.jar" com.example.app.Main Grace
~~~

Stdout:

~~~text
Grace | 2026-01-01
~~~

On Linux/macOS, the classpath separator is a colon:

~~~bash
java --class-path "app.jar:lib/customer.jar" com.example.app.Main Grace
~~~

This example has one external dependency, §com.example.model.Customer§, and one platform dependency, §java.time.LocalDate§. It is a suitable input for seeing how §jdeps§ analyzes the classpath.

## 3. Providing the classpath to jdeps

Use §--class-path§ (with aliases §-cp§ or §-classpath§) to specify where to find dependent class files.

Windows:

~~~powershell
jdeps --class-path "lib/customer.jar" app.jar
~~~

Linux/macOS:

~~~bash
jdeps --class-path "lib/customer.jar" app.jar
~~~

If there are multiple libraries, separate them according to the operating system.

Windows:

~~~powershell
jdeps --class-path "lib/customer.jar;lib/logging.jar;lib/model.jar" app.jar
~~~

Linux/macOS:

~~~bash
jdeps --class-path "lib/customer.jar:lib/logging.jar:lib/model.jar" app.jar
~~~

You can use a wildcard for JARs in a directory:

~~~powershell
jdeps --class-path "lib/*" app.jar
~~~

A complete classpath is very important. If dependencies are missing, §jdeps§ may report classes as not found or list unresolved dependencies. Results produced with an incomplete class path do not reflect the full dependency graph of the application.

Do not confuse §--class-path§ with the input to be analyzed. For example, in the command:

~~~powershell
jdeps --class-path "lib/*" app.jar
~~~

§app.jar§ is the archive being analyzed; §lib/*§ is where its dependent classes are located.

## 4. Reading the default output and dependency summary

Run:

~~~powershell
jdeps --class-path "lib/customer.jar" app.jar
~~~

The default output shows dependency relationships at the package level. The output format typically includes target archive/module lines and source package lines, for example:

~~~text
app.jar -> java.base
app.jar -> lib/customer.jar
   com.example.app -> java.lang
   com.example.app -> java.time
   com.example.app -> com.example.model
~~~

Archive names, paths, and line grouping may vary depending on the JDK, input, and classpath. Use your project's actual output to draw conclusions.

Meaning:

- §java.base§ provides foundational classes such as §java.lang§.
- §java.time§ is a package belonging to the §java.base§ module.
- §com.example.model§ comes from the §customer.jar§ library.
- The archive-level dependency lines indicate that §app.jar§ references external libraries and JDK modules.

Print only the dependency summary:

~~~powershell
jdeps --summary --class-path "lib/customer.jar" app.jar
~~~

The short alias is:

~~~powershell
jdeps -s --class-path "lib/customer.jar" app.jar
~~~

Use summary when you need to know which archives/modules the application depends on without needing to see individual packages or classes yet.

## 5. Choosing package or class detail level

### 5.1. Package-level analysis

§-verbose:package§ shows which source packages depend on which target packages:

~~~powershell
jdeps -verbose:package --class-path "lib/customer.jar" app.jar
~~~

The package level is suitable when:

- You want an overview of how areas of the application depend on each other.
- You want to find dependencies between packages in the architecture.
- You want to identify which packages require an external library.
- You want to avoid overly long output when an archive has many classes.

### 5.2. Class-level analysis

§-verbose:class§ displays specific dependencies between classes:

~~~powershell
jdeps -verbose:class --class-path "lib/customer.jar" app.jar
~~~

The class level is useful when:

- Finding the exact class that pulls in a library.
- Investigating unexpected dependencies.
- Finding classes belonging to JDK internal APIs.
- Reviewing the impact of a specific class before refactoring.

### 5.3. Showing all class dependencies

~~~powershell
jdeps -verbose:class -filter:none --class-path "lib/customer.jar" app.jar
~~~

The equivalent §-v§ option displays all class-level dependencies and does not filter out internal relationships by default.

Class-level output can be very large. Start with summary or package view, then switch to class view once you have identified the area to investigate.

## 6. Filtering dependencies and limiting analyzed classes

§jdeps§ provides options to narrow down results.

| Option | Effect |
|---|---|
| §-p§ or §--package§ | Find only dependencies related to the specified package |
| §-e§ or §--regex§ | Filter dependencies by regular expression |
| §--require§ | Filter dependencies by module name |
| §-include§ | Restrict source classes analyzed by regex |
| §-f§ or §-filter§ | Filter dependencies in the output |
| §-filter:package§ | Filter relationships within the same package; this is the default |
| §-filter:archive§ | Filter dependencies within the same archive |
| §-filter:module§ | Filter dependencies within the same module |
| §-filter:none§ | Disable default package/archive filters |

Example showing only dependencies related to the §com.example.model§ package:

~~~powershell
jdeps --package com.example.model --class-path "lib/*" app.jar
~~~

Example using a regex to filter packages under §com.example§:

~~~powershell
jdeps --regex "com\.example\..*" --class-path "lib/*" app.jar
~~~

§--package§ and §--regex§ are mutually exclusive in the same command. Choose one appropriate filtering method.

Use §-include§ to restrict source classes:

~~~powershell
jdeps -include "com\.example\.app\..*" --class-path "lib/*" app.jar
~~~

Distinguish between the two:

- §-include§ determines which classes in the input are analyzed.
- §--package§ and §--regex§ filter the dependencies that are found.

## 7. Recursive dependency analysis

By default, you typically start from the direct dependencies of the input. When you need to traverse deeper through the libraries the application depends on, use §-R§ or §--recursive§:

~~~powershell
jdeps --recursive --class-path "lib/*" app.jar
~~~

Recursive analysis is useful when:

- You want to know the transitive dependencies of libraries.
- Evaluating the entire chain of archives the application requires.
- Finding a platform dependency pulled in through another library.
- Preparing to migrate a multi-JAR system to the module path.

You can disable recursive analysis with:

~~~powershell
jdeps --no-recursive --class-path "lib/*" app.jar
~~~

Recursive analysis can produce longer output and take more time when the classpath contains many libraries. Use only the level needed for the question under investigation.

## 8. Finding missing dependencies

One of the primary goals of classpath analysis is detecting classes that bytecode references but cannot be found.

Use:

~~~powershell
jdeps --missing-deps --class-path "lib/*" app.jar
~~~

This command finds unresolved dependencies. If the output lists missing class names, check:

1. Which JAR that class belongs to.
2. Whether the JAR is already in the dependency directory.
3. Whether the JAR path has been included in §--class-path§.
4. Whether that version of the JAR contains the class.
5. Whether the dependency is loaded dynamically based on configuration.

You can ignore missing dependencies with §--ignore-missing-deps§ in certain intentional analysis cases:

~~~powershell
jdeps --ignore-missing-deps --class-path "lib/*" app.jar
~~~

This option only changes how the tool handles unfound dependencies. It does not add libraries and does not prove the application can run. When preparing a release, fix the actual classpath or dependencies instead of using this option to hide errors.

Do not conclude that every missing dependency is a guaranteed runtime error. Bytecode might reference a class in a rarely used branch or an optional implementation. However, you need to determine the reason before accepting an unresolved dependency.

## 9. Finding JDK internal API usage

An application may compile successfully yet depend on JDK internal APIs, such as packages under §sun.*§ or §com.sun.*§ that are not part of the guaranteed public API.

Use:

~~~powershell
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

In JDK 17, the short alias is §-jdkinternals§:

~~~powershell
jdeps -jdkinternals --class-path "lib/*" app.jar
~~~

The output helps identify which classes reference JDK internal APIs. This is a sign that action is needed because internal APIs may change or be encapsulated in other JDK versions.

When detected:

1. Identify the internal class and package being referenced.
2. Find a public Java SE API that can replace it.
3. Check the corresponding migration documentation or replacement guide.
4. Update the library or source code.
5. Re-run §jdeps§ and test on the target JDK.

Do not use §--add-exports§ as a long-term solution if a public API alternative exists. This option only adjusts module access permissions when necessary; it does not turn an internal API into a stable API.

## 10. Analyzing dependencies only in the public API

§--api-only§ restricts analysis to dependencies appearing in the public/protected API signatures of public classes, for example:

- Public/protected field types.
- Method parameter types.
- Return types.
- Declared checked exception types.

Command:

~~~powershell
jdeps --api-only --class-path "lib/*" app.jar
~~~

This option is useful when evaluating dependencies that library consumers must know about or have available in order to compile code that uses the API.

API-only analysis does not represent all runtime dependencies. An internal implementation may use another library even if that dependency does not appear in public signatures. Therefore, use it together with full package/class analysis.

## 11. Analyzing multi-release JARs

A multi-release JAR can contain multiple class variants for different Java versions under the §META-INF/versions§ directory.

Use §--multi-release§ to specify the version to analyze:

~~~powershell
jdeps --multi-release 17 --class-path "lib/*" app.jar
~~~

You can use §base§ to analyze the classes in the base version:

~~~powershell
jdeps --multi-release base --class-path "lib/*" app.jar
~~~

If you omit this option, the results may not correspond to the class variant the application actually uses on the target runtime. When evaluating a multi-release library, analyze the exact Java version you will deploy.

## 12. Exporting dependency diagrams with DOT

To generate graph files, use §--dot-output§:

~~~powershell
jdeps --dot-output build/deps --class-path "lib/*" app.jar
~~~

§jdeps§ creates DOT files describing archive dependencies and a §summary.dot§ file showing relationships between archives.

You can open DOT files with Graphviz to render them as images:

~~~powershell
dot -Tpng build/deps/summary.dot -o build/deps/summary.png
~~~

Diagrams are useful when:

- Presenting dependencies across multiple JARs.
- Finding dependency cycles between components.
- Seeing which packages/archives have many connections.
- Discussing module or library splitting with the development team.

If Graphviz is not installed, DOT files are still structured text and can be opened in an editor. The §--dot-output§ option of §jdeps§ only exports graph data; it does not generate PNGs by itself.

## 13. From classpath analysis to module dependencies

§jdeps§ also supports module dependency analysis. For classpath applications, you can use §--print-module-deps§ to print the list of required JDK modules according to the analysis:

~~~powershell
jdeps --print-module-deps --class-path "lib/*" app.jar
~~~

The output is a comma-separated list of module names. This list can be used as input for §jlink --add-modules§ when creating a custom runtime.

Example workflow:

~~~powershell
jdeps --print-module-deps --class-path "lib/*" app.jar
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules java.base,java.logging --output runtime
~~~

In practice, replace the module list in the §jlink§ command with the verified output from §jdeps§. Do not copy the §java.base,java.logging§ example if the application needs different modules.

Note: a runtime image created by §jlink§ contains linked Java modules; it does not automatically bundle the application JAR and all external classpath libraries. When distributing the application, you still need to package §app.jar§ and dependency JARs, and configure the appropriate launcher/classpath.

If you want to analyze a module that already has a module descriptor, use §--module-path§ and module options such as §--module§ or §--check§. §jdeps --generate-module-info§ can also generate a draft §module-info.java§ for a JAR, but you must manually review the directives before using it as an official module descriptor.

## 14. Commonly used options

| Option | Purpose |
|---|---|
| §--class-path§, §-cp§ | Provide directories/JARs to resolve classes |
| §--module-path§ | Provide named modules |
| §-summary§, §-s§ | Print dependency summary only |
| §-verbose:package§ | Print dependencies at the package level |
| §-verbose:class§ | Print dependencies at the class level |
| §-R§, §--recursive§ | Analyze dependencies recursively |
| §--no-recursive§ | Do not traverse dependencies deeply |
| §--missing-deps§ | Find unresolved dependencies |
| §--ignore-missing-deps§ | Ignore missing dependencies during analysis |
| §--jdk-internals§ | Find references to JDK internal APIs |
| §--api-only§ | Analyze dependencies only in public/protected APIs |
| §--multi-release§ | Select the class variant of a multi-release JAR |
| §--dot-output§ | Export dependency graph in DOT format |
| §--print-module-deps§ | Print module list suitable for jlink workflows |
| §--generate-module-info§ | Generate a draft module descriptor for a JAR |
| §--check§ | Analyze the module graph of a named module |

View the help for the exact JDK you are using:

~~~powershell
jdeps --help
~~~

Some options may differ between JDK versions. Check §jdeps --help§ and the manual for your target JDK before putting commands into build scripts.

## 15. Limitations of static analysis

§jdeps§ analyzes dependencies identifiable in bytecode. It is not a tool for observing every class actually loaded during a run.

Cases that require separate verification:

- **Reflection:** class names constructed from strings or configuration files may not appear as normal class references.
- **ServiceLoader:** providers are discovered via the service mechanism; you need to check service configurations and provider modules.
- **Plugins:** plugins discovered in directories or loaded by configuration may not be included in the analysis input.
- **JNI/native code:** native dependencies are not fully described by Java class references.
- **Resources:** resources loaded by name do not necessarily show up as class dependencies.
- **Conditional code:** classes used only in a specific configuration or environment might not be exercised in the current analysis.

Therefore, §jdeps§ results provide a valuable static dependency map, but they do not replace integration tests, configuration checks, and runtime class-loading monitoring.

## 16. Common errors in classpath analysis

| Symptom | Common cause | Resolution |
|---|---|---|
| §Class ... not found§ or missing dependency | Classpath does not contain the referenced library | Add the right JAR/directory with §--class-path§ |
| Output only shows JDK dependencies | External libraries were not provided or there are no static references to them | Check the classpath and input bytecode |
| Output is too long | Using class-level or recursive analysis across many libraries | Start with §-summary§ or §-verbose:package§ |
| Reflection dependencies not visible | Class names are dynamically constructed from strings/config | Check runtime configuration and test reflection paths |
| Multi-release results do not match runtime | Wrong class variant analyzed | Use §--multi-release§ matching the deployed version |
| Internal dependencies are hidden | Default filters omit certain relationships within the same package/archive | Use §-filter:none§ when you need to see everything |
| JDK internal API detected | Code or library depends on internal packages | Find a public API replacement and upgrade the library |
| §--print-module-deps§ misses runtime modules | Static analysis does not see dynamic dependencies or providers | Add modules based on runtime configuration and test the image |
| DOT fails to generate an image | Graphviz is not installed or wrong file path specified | Check the DOT file; install Graphviz if PNG/SVG is needed |

## 17. Classpath analysis workflow in a project

Follow this sequence:

1. Select the JAR or class directory that is actually deployed as the input.
2. List external dependencies and pass them to §--class-path§.
3. Run default §jdeps§ or §-summary§ to get the big picture.
4. Switch to §-verbose:package§ to find relevant packages.
5. Use §-verbose:class§ and §-filter:none§ to pinpoint specific classes.
6. Run §--missing-deps§ to find unresolved references.
7. Run §--jdk-internals§ to detect internal APIs.
8. Use §-R§ if you need to analyze transitive dependencies.
9. Use §--multi-release§ if the input is a multi-release JAR.
10. Export §--dot-output§ if you need a dependency diagram.
11. Use §--print-module-deps§ to assist with creating a runtime image when appropriate.
12. Verify reflection, services, plugins, resources, and native code separately using actual configuration and tests.

## 18. Checklist before concluding

- [ ] Input is the class file, class directory, or JAR matching the deployed artifact.
- [ ] All dependent libraries have been provided via §--class-path§.
- [ ] Selected summary, package, or class level appropriate to the question.
- [ ] Checked default filters before concluding a dependency does not exist.
- [ ] Ran §--missing-deps§ to find unresolved references.
- [ ] Checked for JDK internal APIs using §--jdk-internals§.
- [ ] Used §-R§ if transitive dependencies are needed.
- [ ] Selected the right §--multi-release§ for multi-release JARs.
- [ ] Verified reflection, service, plugin, resource, and native dependencies separately.
- [ ] If using §--print-module-deps§, reviewed the list before passing it to §jlink§.
- [ ] Recorded the command and JDK version so results can be reproduced.

Classpath analysis with §jdeps§ helps clarify which packages, classes, libraries, and platform modules an application references. Start with the right input and a complete classpath, read the summary/package view first, and then use class view, recursive analysis, and missing-dependency checks for deeper investigation. Combine static results with runtime testing so dynamically loaded dependencies are not missed.

## References

- Oracle, The jdeps Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- Oracle, Module jdk.jdeps, Java SE 17 API: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jdeps/module-summary.html
- Oracle, The javac Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
