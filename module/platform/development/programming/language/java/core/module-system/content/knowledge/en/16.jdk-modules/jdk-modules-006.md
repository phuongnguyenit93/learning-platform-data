# Detecting JDK Module Dependencies with jdeps

## 1. What Is jdeps Used For?

**jdeps** is a command-line tool bundled with the JDK for analyzing dependencies expressed in Java bytecode. The tool can read **.class** files, JARs, or directories of class files, then report which packages, classes, and modules the compiled code references.

In the Java Platform Module System (JPMS, since Java 9), jdeps helps answer practical questions:

- Which JDK modules does the application need, such as **java.base**, **java.sql**, or **java.logging**?
- Does a JAR use any internal JDK APIs?
- When moving an application from the classpath to the module path, which dependencies need to be declared?
- When creating a minimal runtime image with **jlink**, which JDK modules need to be included in the image?
- Why is jdeps unable to resolve certain classes, and which libraries must be added to the classpath or module path?

jdeps performs **static analysis**. It inspects bytecode and references identifiable from bytecode without running the application. Consequently, the results reflect the dependencies the tool detects in the artifact at the time of analysis.

## 2. Preparation and Analysis Scope

jdeps is located in the JDK's **bin** directory. You can check its version and syntax with:

~~~bash
jdeps --version
jdeps --help
~~~

General syntax:

~~~bash
jdeps [options] <path>
~~~

The **<path>** argument can be a class file, a JAR, or a directory containing classes. Multiple artifacts can be analyzed in a single invocation. Use a jdeps version matching the application's target JDK, especially when artifacts contain classes compiled for multiple Java versions.

An analysis pass typically starts from the packaged JAR. Analyzing the final artifact avoids overlooking differences between source code and what is actually included in the release.

## 3. Workflow for Finding JDK Module Dependencies

### Step 1: View a Dependency Overview

Run summary mode:

~~~bash
jdeps --summary build/libs/app.jar
~~~

The output typically shows which modules the artifact depends on. Illustrative example:

~~~text
app.jar -> java.base
app.jar -> java.logging
app.jar -> java.sql
~~~

This indicates that bytecode in the JAR references APIs belonging to the listed modules. **java.base** appears in almost every Java application because it is the foundational module implicitly read by other modules under JPMS rules.

Summary mode is well suited for a quick inventory. When you need to know which class or package creates a dependency, switch to verbose modes.

### Step 2: Trace Dependencies to Packages or Classes

Analyze at the package level:

~~~bash
jdeps --verbose:package build/libs/app.jar
~~~

Analyze at the class level:

~~~bash
jdeps --verbose:class build/libs/app.jar
~~~

Package mode helps narrow down the area to inspect. Class mode is useful when finding the exact class referencing an API. Detailed output is usually significantly longer than the summary, so use it after identifying a module or package of interest.

### Step 3: List Required JDK Modules

Use **--list-deps** to list module dependencies:

~~~bash
jdeps --list-deps build/libs/app.jar
~~~

Use **--print-module-deps** when you need a comma-separated list of modules:

~~~bash
jdeps --print-module-deps build/libs/app.jar
~~~

Example output might be:

~~~text
java.base,java.logging,java.sql
~~~

This list is useful as input when configuring **jlink**. Treat it as the module set inferred from references jdeps could analyze; you still need to test the application inside the actual runtime image.

### Step 4: Check for JDK Internal APIs

Run:

~~~bash
jdeps --jdk-internals build/libs/app.jar
~~~

This option searches for references to internal JDK APIs, such as packages prefixed with **sun.*** or certain **com.sun.*** APIs. Output can identify the class using the API, the referenced internal API, and a suggested replacement if the tool knows an appropriate alternative.

Internal APIs are not public compatibility contracts. They may change or have access restricted across JDK versions. When a reference is detected, locate the corresponding public API and update the calling code. For example, some uses of **sun.misc.Unsafe** can be migrated to **VarHandle**, **java.util.concurrent**, or other public APIs; the exact choice depends on the code's purpose.

Do not treat the absence of jdeps errors as absolute proof that the application uses no internal APIs. Dynamically constructed references or references hidden in configuration may lie beyond static analysis.

### Step 5: Detect Missing Dependencies

Run:

~~~bash
jdeps --missing-deps build/libs/app.jar
~~~

If a class is referenced yet not found in the artifact, classpath, or module path provided, jdeps may report a missing dependency. When that happens, check whether a library was omitted from the analysis command or whether the application genuinely references a class that no longer exists.

You can use **--ignore-missing-deps** to let analysis continue when some dependencies cannot be resolved:

~~~bash
jdeps --ignore-missing-deps --print-module-deps build/libs/app.jar
~~~

This option only ignores missing status during analysis; it does **not** locate, download, or supply missing libraries. Do not use it to mask resolution errors when you need to confirm an accurate module list.

## 4. Supplying the Right Classpath and Module Path

Results are only meaningful when jdeps can resolve the libraries referenced by the application.

### Applications or Libraries on the Classpath

Use **--class-path** to provide dependent JARs:

~~~bash
jdeps --class-path "lib/*" --summary build/libs/app.jar
~~~

The separator for multiple path entries depends on the operating system: Windows uses a semicolon (**;**), whereas Linux and macOS use a colon (**:**). Wildcard syntax and quoting also depend on the shell in use.

When libraries are missing from the classpath, jdeps may report classes not found or fail to infer complete dependencies. Add the exact libraries the application needs to the analysis classpath.

### Applications Using Named Modules

Use **--module-path** to specify where named modules reside. You can request analysis of a specific module with **--module**:

~~~bash
jdeps --module-path mods --module com.example.app
~~~

The module path helps jdeps resolve module descriptors and module dependencies. Ensure the specified directory contains the right modules for the application version under analysis.

Classpath and module path play different roles: libraries on the classpath belong to the unnamed module, whereas libraries on the module path can be recognized as named modules if they have an appropriate module descriptor. Do not move a library from one to the other merely to silence warnings; understand how the application is actually launched and how classes are resolved.

### Analyzing Multi-Release JARs

A multi-release JAR can contain different classes for each Java version. Use **--multi-release** to instruct jdeps to analyze the classes targeting a specific release:

~~~bash
jdeps --multi-release 17 --print-module-deps build/libs/app-mr.jar
~~~

Choose the exact Java version the application will run on. Analyzing classes for a different version may produce a dependency list that does not reflect the target runtime.

## 5. Reading and Interpreting Results

When reading output, distinguish three levels of information:

- **Artifact -> module:** summary shows which modules the JAR or directory references.
- **Package -> package:** package-level verbose mode shows which code areas create the dependency link.
- **Class -> class:** class-level verbose mode helps trace the exact reference site for fixing or inspection.

A line such as **app.jar -> java.sql** means jdeps found a reference from bytecode in **app.jar** to an API belonging to the **java.sql** module. It does not mean every class in the **java.sql** module is used by the application.

The module list is also not a list of all third-party libraries. Non-JDK dependencies may be represented as separate JARs or modules and must be provided via classpath or module path for complete analysis.

If recursive mode is used, jdeps can follow resolved dependencies to expand the analysis scope. Results may then include modules needed by dependent libraries, not just modules directly referenced by application bytecode. Choose the scope suited to the question you need answered.

## 6. Using Results to Build a Runtime Image with jlink

A common purpose of **--print-module-deps** is determining which JDK modules to include in a runtime image.

First, obtain the list:

~~~bash
jdeps --print-module-deps build/libs/app.jar
~~~

Suppose the illustrative output is:

~~~text
java.base,java.logging,java.sql
~~~

You can use that list in a **jlink** command:

~~~bash
jlink --add-modules java.base,java.logging,java.sql --output runtime-image
~~~

In a real project, replace the illustrative list with the output for your actual artifact. For a non-modular application running on the classpath, the application JAR still needs to be distributed and placed on the classpath at launch; **jlink** creates a runtime image from JDK modules rather than packaging classpath JARs that way.

Before releasing, run the application using the new runtime image and exercise key functional flows. If a feature loads classes dynamically or only runs under a specific configuration, the required module might not appear in the initial static analysis output.

## 7. Assisting Migration of JARs to Modules

For JARs that do not yet have **module-info.java**, jdeps can generate a draft module descriptor with **--generate-module-info**:

~~~bash
jdeps --generate-module-info generated-modules build/libs/library.jar
~~~

The tool produces an initial **module-info.java** structure based on detected dependencies. This is a starting point for converting a library, not a fully designed and verified descriptor.

After generating the draft, review the module name, **requires** declarations, **exports**, and the library's encapsulation requirements. Separate packages that must be public from packages meant for internal use only. If the library needs to support both the classpath and module path, verify compatibility behavior based on how the library is distributed and used.

## 8. Limitations to Keep in Mind

jdeps is very useful for mapping bytecode dependencies, but it does not replace application testing:

1. **Static analysis does not see all runtime behavior.** Classes loaded via reflection, class names read from configuration strings, plugins, custom classloaders, or runtime-generated code may not be fully detected.
2. **It does not prove whether a dependency is actually executed.** A reference in bytecode may sit on a rarely executed branch; conversely, a dependency appearing only in another deployment configuration may not be present in the analyzed artifact.
3. **Missing libraries produce incomplete results.** Provide the complete classpath and module path. Warnings about unfound classes should be investigated before drawing conclusions.
4. **Results depend on the JDK version and artifact.** Analyze the right JAR, the right multi-release version, and the right target JDK.
5. **A module list does not replace runtime testing.** Dynamic loading features, services, environment configurations, and optional code paths must be verified through real testing.

## 9. Recommended Practical Workflow

When auditing an application before release or migrating to JPMS, follow this sequence:

1. Select the JAR or class directory from the release build.
2. Run **jdeps --summary** to get an overview.
3. Run **jdeps --verbose:package** or **--verbose:class** when needing to trace the origin of a dependency.
4. Run **jdeps --list-deps** or **--print-module-deps** to extract detected JDK modules.
5. Run **jdeps --jdk-internals** to find uses of internal APIs.
6. Run **jdeps --missing-deps** and supply the right classpath/module path if there are unresolved dependencies.
7. If creating a runtime image, pass the module list as input to **jlink**, then test the application on the image.
8. Record the commands, JDK version, artifact, and output so the analysis can be repeated in CI.

These commands can be added to the pipeline after the JAR packaging step. That way, every build has its dependencies checked on the exact artifact type users receive. In particular, the **--jdk-internals** check can be configured as a warning or build gate depending on the project's compatibility policy.

## 10. Takeaways

- **--summary**: quick dependency overview.
- **--verbose:package / --verbose:class**: locate the package or class creating a dependency.
- **--list-deps / --print-module-deps**: list required JDK modules.
- **--jdk-internals**: detect references to internal JDK APIs.
- **--missing-deps**: find unresolved class dependencies.
- **--class-path / --module-path**: provide the right locations containing libraries.
- **--multi-release**: select the Java-version-specific classes in a multi-release JAR.

Use jdeps to understand and narrow down the dependency graph, then verify with builds and runtime tests. Combining both helps catch unwanted JDK dependencies early, prepare module declarations, and build smaller runtime images while preserving application behavior.
