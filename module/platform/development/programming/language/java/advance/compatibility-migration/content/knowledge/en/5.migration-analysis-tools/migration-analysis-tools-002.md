# Analyzing Class, Package, and Module Dependencies with jdeps

When upgrading the JDK or migrating a Java application to the Java Platform Module System (JPMS), one of the most important questions is: which classes, packages, and modules do the current source code and bytecode depend on? A seemingly standalone library may be calling JDK internal APIs, using packages from a module no longer included by default, or pulling in many indirect dependencies.

`jdeps` is a static dependency analysis tool bundled with the JDK. The tool reads class files, JARs, or modules to find references across classes, packages, archives, and modules. Results help development teams understand dependency structure, detect references to JDK internal APIs, prepare module descriptors, and identify the set of modules needed for a custom runtime.

`jdeps` analyzes compiled bytecode. It complements reading source code and using Maven or Gradle dependency management tools; each tool answers a different kind of question. This lesson covers choosing analysis levels, supplying classpaths/module paths, reading output, and using `jdeps` during migration.

## 1. What Is jdeps Used For?

`jdeps` (Java Dependency Analysis Tool) is provided in the JDK. It analyzes dependency references the tool can recognize from class files and module descriptors.

Common tasks include:

- Inspecting which platform modules or libraries a JAR depends on.
- Finding packages and classes referenced by a class.
- Extending analysis to indirectly referenced dependencies.
- Detecting missing classes or packages on the classpath/module path.
- Finding usage of JDK internal APIs at risk of being restricted or removed.
- Checking `requires` relationships in module descriptors.
- Generating draft `module-info.java` files when modularizing a library.
- Listing modules needed to build a runtime image with `jlink`.

For example, an application might directly call `java.sql.Connection`, use `com.example.common.Strings` from an internal library, and indirectly require `java.xml` via another library. `jdeps` clarifies those relationships in bytecode.

## 2. How Class, Package, and Module Dependencies Differ

Before running the tool, understand the three representation levels:

| Level | Analyzed Entity | Typical Question |
|---|---|---|
| Class | Specific class or interface | Which classes does `OrderService` reference? |
| Package | Group of classes sharing a namespace | Which packages does package `com.example.service` depend on? |
| Module | JPMS packaging and dependency-declaration unit | Which modules does module `com.example.orders` require? |

Suppose there is a structure:

```text
com.example.orders
├── service
│   └── OrderService
├── model
│   └── Order
└── persistence
    └── OrderRepository
```

`OrderService` may reference `Order`, `OrderRepository`, and `java.sql.Connection`. At the class level, the tool reports the exact referenced classes. At the package level, references are grouped into relationships like `service -> model` and `persistence -> java.sql`. At the module level, packages belonging to different modules are aggregated into module relationships.

These three levels do not replace one another. Class-level is useful for locating the exact place to fix; package-level helps inspect architectural boundaries; module-level assists in designing `module-info.java` and verifying runnability in a modular environment.

## 3. Preparing the Environment and Inputs

### 3.1. Checking That jdeps Is Available

`jdeps` is located in the `bin` directory of the JDK. Open a terminal and run:

```bash
jdeps --version
```

If the shell reports command not found, check `JAVA_HOME` and `PATH`, or invoke the executable directly inside the JDK directory:

```text
<JDK_HOME>/bin/jdeps
```

On Windows, the executable is typically `jdeps.exe` in `<JDK_HOME>\bin`. Use a JDK containing this tool; a minimal runtime image may not include all development tools.

### 3.2. Types of Inputs That Can Be Analyzed

Typically, you can pass to `jdeps`:

- A `.class` file.
- A directory containing compiled classes.
- A JAR file.
- A module or a set of archives/modules matching the resolution paths.

For example, after building the project, you can analyze the JAR:

```bash
jdeps build/libs/orders-app.jar
```

Or analyze the compiled class directory:

```bash
jdeps build/classes/java/main
```

Results depend on the dependencies the tool can locate. If the application uses external libraries, supply the appropriate classpath or module path to avoid incomplete results or `not found` warnings.

### 3.3. Distinguishing Classpath and Module Path

`--class-path` (short form `-cp`) specifies where to locate classes and JARs loaded via the classpath mechanism. `--module-path` specifies where to locate named modules per JPMS. These two paths serve two different resolution models.

Example:

```bash
jdeps --class-path "lib/*" -verbose:package app.jar
```

The command above analyzes `app.jar` and searches for dependencies on classpath `lib/*`.

For a modular application:

```bash
jdeps --module-path "mods" -verbose:module app.jar
```

The command above lets the tool resolve modules from the `mods` directory. When analyzing a real modular application, use the exact module path that the application or production launch command uses.

On Windows, you may need to wrap paths in double quotes so the shell handles spaces. The separator between multiple entries in classpath/module path also depends on the OS: `;` on Windows and `:` on Linux/macOS.

## 4. Overview Dependency Analysis

### 4.1. Summary mode

Basic command:

```bash
jdeps -summary app.jar
```

Or use the long form:

```bash
jdeps --summary app.jar
```

Summary mode groups results at the archive level, allowing a quick look at which archives or modules a JAR depends on. This is a good starting point when inspecting a large library.

An illustrative output:

```text
orders-app.jar -> java.base
orders-app.jar -> java.sql
orders-app.jar -> common-utils.jar
```

In the example, the application has dependency relationships with `java.base`, `java.sql`, and `common-utils.jar`. Actual names and formatting depend on inputs, classpath/module path, and JDK version.

Summary does not immediately show which class created each relationship. When needing to trace the origin of a dependency, switch to package or class level.

### 4.2. Recursive Analysis

A JAR can depend on another library, which in turn depends on a third library. The `-R` (recursive) option extends analysis to dependencies found on the resolution path:

```bash
jdeps -R -summary --class-path "lib/*" app.jar
```

Recursive analysis is useful when wanting to understand dependency scope beyond a single archive. However, output can be large and should be read layer by layer. It does not mean the tool discovers every dependency loaded dynamically when the program runs.

## 5. Package-Level Dependency Analysis

Use `-verbose:package` to display relationships between packages:

```bash
jdeps -verbose:package app.jar
```

Illustrative output example:

```text
com.example.orders.service -> com.example.orders.model
com.example.orders.service -> com.example.orders.persistence
com.example.orders.persistence -> java.sql
com.example.orders.service -> java.util
```

The output shows that package service uses model and persistence; package persistence uses `java.sql`; package service also uses `java.util`.

### 5.1. Using Package Dependencies to Inspect Architectural Boundaries

Package dependencies are useful when checking architectural rules:

- Does a domain package depend on a web or persistence package?
- Does a shared package accidentally depend back on a specific application?
- Are there dependency cycles between package groups?
- Does a package depend on too many external packages?

For example, if the intended architecture is:

```text
web -> application -> domain
                  -> persistence
```

yet output shows:

```text
domain -> web
```

then there may be a reverse dependency to investigate. `jdeps` only provides evidence of reference relationships; the development team must decide whether that relationship violates the architecture.

### 5.2. Filtering Results

When a project has many packages, you can use `jdeps` filter options to reduce noise. Example:

```bash
jdeps -verbose:package -filter:archive app.jar
```

Filters like `-filter:archive`, `-filter:package`, `-filter:module`, or `-filter:none` control which relationships are kept or excluded from output. `-filter:none` is useful when needing to see internal relationships that default filtering might hide. Read the Options section of `jdeps --help` on the active JDK to confirm exact filtering behavior for that version.

Do not filter too aggressively on the initial pass. An internal relationship between two packages inside the same archive can still matter when checking cyclic dependencies or module boundaries.

## 6. Class-Level Dependency Analysis

When needing to know exactly which class references which class, use `-verbose:class`:

```bash
jdeps -verbose:class app.jar
```

To see more relationships, including some internal dependencies normally filtered out, run:

```bash
jdeps -verbose:class -filter:none app.jar
```

Illustrative output example:

```text
com.example.orders.service.OrderService
  -> com.example.orders.model.Order
  -> com.example.orders.persistence.OrderRepository
  -> java.sql.Connection

com.example.orders.persistence.JdbcOrderRepository
  -> java.sql.PreparedStatement
  -> java.sql.ResultSet
```

Class-level is especially useful when:

- Finding classes using a deprecated API or internal API.
- Determining why a package needs a specific module.
- Finding the class causing a dependency on an unwanted library.
- Splitting a large library into modules with clear boundaries.

### 6.1. Providing Dependent Libraries

If referenced classes reside in external JARs, supply the classpath:

```bash
jdeps -verbose:class --class-path "lib/*" app.jar
```

Without supplying required libraries, output may contain `not found` or report missing dependencies. This does not necessarily prove the source JAR is broken; the analysis command may simply lack sufficient paths.

Use the same set of libraries and dependency versions the application actually uses. Supplying a different version on the classpath can produce analysis results that do not reflect production.

## 7. Detecting Missing Dependencies

The `--missing-deps` option instructs `jdeps` to list dependencies that cannot be resolved:

```bash
jdeps --missing-deps --class-path "lib/*" app.jar
```

An illustrative situation:

```text
app.jar -> not found
   com.example.orders.ReportService -> com.vendor.reporting.PdfWriter not found
```

This information helps identify classes referenced by bytecode that the tool cannot find on the supplied paths.

When encountering missing dependencies, follow this sequence:

1. Identify the reported missing class and the module/package expected to contain it.
2. Check whether the dependency was included in the build.
3. Check whether the `jdeps` command's classpath/module path matches the application's launch configuration.
4. Check the JAR version and module name, especially when a library has been modularized.
5. Re-run analysis after fixing paths or dependencies.

`--ignore-missing-deps` can be used in certain analysis/generation tasks when the operator deliberately accepts ignoring unresolved dependencies. Do not use it to mask environment errors during a full check.

## 8. Detecting JDK Internal API Usage

A major risk when upgrading the JDK is an application depending on internal packages such as `sun.*`, `com.sun.*`, or APIs outside Java SE's stability guarantees.

Run:

```bash
jdeps --jdk-internals app.jar
```

To analyze external dependencies on the classpath as well:

```bash
jdeps --jdk-internals --class-path "lib/*" app.jar
```

Output can pinpoint classes referencing internal APIs and suggest replacement APIs if the tool has corresponding mapping data.

Example of an illustrative output snippet:

```text
JDK Internal API                         Suggested Replacement
----------------                         ---------------------
sun.misc.BASE64Encoder                   java.util.Base64
```

This is only an illustrative report-format example; actual listings depend on the JDK and analyzed class files.

### 8.1. Why Are Internal APIs Dangerous?

Public Java SE APIs have a documented compatibility contract. Internal APIs are usually JDK implementation details without the same stability guarantees. They can be encapsulated, access-restricted, changed, or removed across releases.

JEP 260 and JEP 403 are major milestones in encapsulating and closing access to many internal APIs. Thus, an application that ran on an older JDK may encounter access errors or fail to compile on a newer JDK.

### 8.2. How to Handle Them

When `jdeps --jdk-internals` finds references:

1. Locate the classes and packages in the application using that API.
2. Read suggested replacements and corresponding public API documentation.
3. Replace with standard APIs when available, such as using `java.util.Base64` instead of old internal encoders/decoders.
4. If no replacement API exists, evaluate a supported external library or redesign the dependency.
5. Run tests on the target JDK and check for reflective access warnings.

Options such as `--add-exports` or `--add-opens` can keep legacy applications running during a transition phase. They should be treated as controlled temporary compatibility configurations, not long-term substitutes for removing internal API dependencies.

## 9. Analyzing Modules and JPMS Relationships

Starting in Java 9, JPMS introduced named modules, module descriptors, and dependency/accessibility controls. `jdeps` can aggregate dependencies by module to assist migrating an application from classpath to module path.

### 9.1. Displaying Module Dependencies

Use `-verbose:module`:

```bash
jdeps -verbose:module --module-path mods app.jar
```

Output shows which modules are referenced. Illustrative example:

```text
orders.app -> java.base
orders.app -> java.sql
orders.app -> com.example.persistence
```

If an archive does not yet have a module descriptor, how the tool derives the module name can rely on `Automatic-Module-Name` in the manifest or the JAR filename. For explicitly declared modules, the module name is read from the descriptor.

### 9.2. Analyzing a Specific Module

When the module is already on the module path, you can specify the module name to analyze:

```bash
jdeps --module-path mods --module com.example.orders -verbose:module
```

This command focuses on module `com.example.orders` and the relationships the tool can analyze from that module. If the module cannot be resolved, check the module path and the name in `module-info.java`.

### 9.3. Understanding Module Descriptors

A module descriptor may contain declarations such as:

```java
module com.example.orders {
    requires java.sql;
    requires com.example.persistence;

    exports com.example.orders.api;
}
```

Key directives:

| Directive | Meaning |
|---|---|
| `requires` | The current module depends on another module. |
| `requires transitive` | The required module is also made readable to modules depending on the current module. |
| `requires static` | Dependency is required at compile time yet may be optional at runtime. |
| `exports` | Allows other modules to access public types in the exported package. |
| `opens` | Allows deep reflective access to the package within the declared scope. |
| `uses` | Declares that the module uses a service. |
| `provides ... with ...` | Declares a provider for a service. |

`jdeps` helps uncover reference relationships, yet the module designer still decides which packages to export, which dependencies need `transitive` or `static`, and which services to declare. Do not turn every package the tool sees into a publicly exported package.

### 9.4. Checking Module Descriptors with `--check`

`--check` analyzes the specified module and provides information about dependencies in the module graph, including potentially redundant requirements or indirect dependencies:

```bash
jdeps --module-path mods --check com.example.orders
```

This is a useful step after creating `module-info.java`. Read the output alongside the current descriptor to determine which declarations must truly be kept. Do not delete `requires` merely because a single report suggests the dependency can be implied indirectly; consider the module's public API and downstream modules.

## 10. Listing Modules Needed for Runtime

When creating a minimal runtime image with `jlink`, you need to know which platform modules the application uses.

### 10.1. Listing Module Dependencies

```bash
jdeps --list-deps --module-path mods app.jar
```

This option lists required module dependencies per the tool's analysis.

### 10.2. Printing a Compact Module List

```bash
jdeps --print-module-deps --module-path mods app.jar
```

`--print-module-deps` prints a comma-separated list of module names suitable as input for building a runtime image. For example, if the output is:

```text
java.base,java.sql
```

you can use that list as a basis for:

```bash
jlink --add-modules java.base,java.sql --output runtime-image
```

This is a minimal example; real applications may require additional modules due to service binding, providers, locales, charsets, logging, or dynamic loading mechanisms. Test the runtime image across all business flows before distributing.

### 10.3. Distinguishing Full Dependencies from Reduced Dependencies

`--list-deps` lists analyzed module dependencies. `--list-reduced-deps` attempts to omit dependencies that can be inferred via `requires transitive` relationships in the module graph. Both outputs serve different purposes; when creating a runtime image, understand which list is used and test the actual image.

Do not treat `jdeps` output as an absolute guarantee that the runtime image is sufficient for every execution path. Classes loaded via reflection, plugin configurations, JNI, or services/providers depending on implementation may require additional checks.

## 11. Generating Module Descriptors with jdeps

When a JAR lacks `module-info.java`, you can use `--generate-module-info` to create a draft descriptor:

```bash
jdeps --generate-module-info generated-modules legacy-library.jar
```

The tool generates a directory/source file for the module descriptor in `generated-modules` based on the dependencies and packages it analyzes. This is a starting point for modularization.

An example draft might look like:

```java
module legacy.library {
    requires java.base;
    requires java.logging;

    exports com.example.legacy.api;
    exports com.example.legacy.model;
}
```

Module names and export lists in the example are illustrative only. Inspect the generated file in the actual project.

### 11.1. Why Must Generated module-info.java Be Reviewed?

`jdeps` infers relationships from bytecode, yet does not fully understand API design intent. A package containing public classes does not mean that package should be exported. A dependency appearing in API signatures may need `requires transitive`; an internally used dependency may only need regular `requires`. Certain services require `uses` or `provides` declarations by design.

After generating the descriptor, you should:

1. Check the module name and `Automatic-Module-Name` if present.
2. Review every `requires`, removing unneeded dependencies and confirming needed dependencies are not missing.
3. Export only packages that are supported APIs.
4. Determine `requires transitive`, `requires static`, `opens`, `uses`, and `provides` per the library's contract.
5. Recompile on the module path and run tests from a client module.

For libraries needing to support reflection frameworks, examine which packages must be `opens` and to which modules. `exports` and `opens` serve different purposes; do not substitute them arbitrarily.

### 11.2. Open Module

When all packages need to be opened for deep reflection, `jdeps` provides `--generate-open-module` to generate an open module descriptor. This is a broad choice and needs careful evaluation because it weakens JPMS reflective encapsulation. Use it only when framework requirements or design genuinely demand opening the whole module.

## 12. Exporting Dependency Graphs

When dependency relationships are too numerous to read in plain text, you can use `--dot-output` to export DOT files:

```bash
jdeps --dot-output dependency-report --class-path "lib/*" -R app.jar
```

The `dependency-report` directory will contain graph representations viewable with Graphviz/DOT-compatible tools. Graphs help identify:

- Packages or archives with high dependency counts.
- Tightly coupled package groups.
- Dependency relationships between modules.
- Indirect dependency paths to investigate.

DOT describes nodes and edges. You can convert `.dot` files to images using Graphviz if installed:

```bash
dot -Tpng dependency-report/app.jar.dot -o dependency-report/app-dependencies.png
```

Actual generated DOT filenames depend on the archive and tool version; check the directory contents after running `jdeps` and use the exact filename.

## 13. Multi-Release JARs

A multi-release JAR can contain multiple class versions for different Java versions in the same archive. The structure typically has a `META-INF/versions/<N>` directory alongside base classes.

When analyzing this type of JAR, you can specify the target version:

```bash
jdeps --multi-release 21 -verbose:package library.jar
```

The `--multi-release` option instructs the tool to examine contents matching the specified Java version. This matters when a library provides separate implementations for newer JDKs.

If migrating to JDK 21, analyze under the appropriate target and inspect which classes the runtime will choose. Analyzing only base classes can miss dependencies of implementations dedicated to newer JDKs.

## 14. Commonly Used jdeps Options

| Option | Purpose |
|---|---|
| `-summary` | Displays dependencies at summary level. |
| `-verbose:package` | Displays dependencies at package level. |
| `-verbose:class` | Displays dependencies at class level. |
| `-verbose:module` | Displays dependencies at module level. |
| `-R` | Recursively analyzes discovered dependencies. |
| `--class-path` / `-cp` | Specifies the classpath containing dependencies. |
| `--module-path` | Specifies the module path. |
| `--module` | Selects the module to analyze. |
| `--missing-deps` | Lists unresolvable dependencies. |
| `--jdk-internals` | Finds references to JDK internal APIs. |
| `--api-only` | Restricts analysis to public/protected APIs. |
| `--check` | Checks dependencies/module descriptor of a module. |
| `--list-deps` | Lists module dependencies. |
| `--list-reduced-deps` | Lists module dependencies reduced via the module graph. |
| `--print-module-deps` | Prints compact module list for building runtime images. |
| `--generate-module-info` | Generates draft `module-info.java`. |
| `--generate-open-module` | Generates an open module descriptor. |
| `--dot-output` | Exports dependency graph in DOT format. |
| `--multi-release` | Selects the version for analyzing a multi-release JAR. |
| `--ignore-missing-deps` | Ignores missing dependencies in tasks supporting this option. |

Short and long option names may vary by JDK. Always check `jdeps --help` on the actual JDK in the pipeline before placing commands into shared scripts.

## 15. Dependency Analysis Workflow During Migration

A practical workflow can proceed in the following order.

### Step 1: Build the Exact Artifact

Build the application with the chosen configuration and JDK. Analyze the exact JAR/class output that will be released. Avoid analyzing a stale build directory containing leftover classes from a previous compilation.

### Step 2: Supply Full Dependencies

Collect the classpath or module path matching runtime. With Maven/Gradle, take resolved dependencies from the build configuration; do not arbitrarily pick JARs with matching names.

### Step 3: Run Summary and Package Analysis

```bash
jdeps -summary --class-path "lib/*" app.jar
jdeps -verbose:package --class-path "lib/*" app.jar
```

Review package groups and external dependencies. If unwanted relationships appear, switch to class-level to locate the exact class creating the relationship.

### Step 4: Check Class-Level and Missing Dependencies

```bash
jdeps -verbose:class --class-path "lib/*" -filter:none app.jar
jdeps --missing-deps --class-path "lib/*" app.jar
```

Identify missing classes, libraries omitted from the build, or references that are no longer valid.

### Step 5: Find JDK Internal APIs

```bash
jdeps --jdk-internals --class-path "lib/*" app.jar
```

Prioritize eliminating internal API dependencies before upgrading feature releases, especially in older un-updated libraries.

### Step 6: Evaluate Modularization

If moving to JPMS, analyze at the module level, inspect module descriptors, and generate drafts if needed. Carefully review `requires`, `exports`, `opens`, and service declarations.

### Step 7: Test on the Actual Runtime

Compile and run unit/integration tests on the target module path or runtime image. Add tests for plugins, reflection, service loading, and production-only flows.

### Step 8: Save Results as a Baseline

Save executed commands, JDK version, classpath/module path, dependency reports, and resolution conclusions. In future upgrades, you can compare to detect new dependencies or returning internal APIs.

## 16. jdeps Does Not Replace Maven/Gradle Dependency Trees

`jdeps` analyzes references at the bytecode and module level. Maven/Gradle dependency reports focus on dependencies declared and resolved during the build.

| Tool | Question Answered |
|---|---|
| `jdeps` | Which classes/packages/modules reference which classes/packages/modules in bytecode? |
| `mvn dependency:tree` | Which Maven artifacts are declared directly or pulled transitively, by group/artifact/version? |
| `gradle dependencies` | Which dependencies are resolved in Gradle configurations and via which relationships? |
| Unit/integration tests | Do tested execution paths behave properly at runtime? |

A dependency can appear in the dependency tree yet never be used by bytecode. Conversely, a class reference cannot be resolved by `jdeps` if its JAR is missing from the classpath. Combine build reports and bytecode analysis to understand both the artifact graph and the class reference graph.

## 17. Limitations of Static Analysis

`jdeps` does not observe everything happening when a program runs. It cannot guarantee finding all classes loaded by string name, reflection, plugins, external configuration, JNI, or custom class loaders.

Example:

```java
String className = configuration.get("driver.class");
Class<?> driverClass = Class.forName(className);
```

If the `driver.class` value appears only in a config file at runtime, bytecode does not necessarily contain a direct reference to the concrete driver class. `jdeps` may not infer this dependency.

Similarly, frameworks may scan packages, read service provider files, or load implementations by configuration. Add checks for:

- Integration tests in a production-like environment.
- Checking `META-INF/services` files and service providers.
- Checking plugin, driver, logging, serializer, and provider configs.
- Monitoring class loading or startup logs when needed.
- Checking native libraries and dedicated JNI components.

Therefore, a `jdeps` report is an important piece of static evidence, not an exhaustive list of every runtime dependency.

## 18. Common Mistakes When Using jdeps

**Not supplying classpath/module path.** Results show `not found` because required libraries are missing. Verify paths before concluding the artifact is broken.

**Analyzing the wrong artifact.** A JAR in a build directory might not be the final deployed artifact. Analyze the exact released file.

**Looking only at summary.** Summary does not reveal the class causing the relationship. Use package/class verbosity to isolate it.

**Confusing package dependency with module readability.** A package reference does not automatically mean the current module can access that package. JPMS also enforces `requires`, `exports`, and `opens`.

**Treating generated module-info as complete.** Tool-generated descriptors are only drafts. Review APIs and encapsulation intent.

**Ignoring internal APIs in third-party libraries.** Analyze dependencies on the classpath as well and update libraries if internal references exist.

**Assuming no findings means no dependencies.** Inputs may be wrong, paths missing, class files not built yet, or dependencies loaded dynamically.

**Using jdeps output as a runtime image without testing.** Reflection, service loading, plugins, and native libraries may require additional components.

## 19. Dependency Analysis Checklist

- [ ] Used the exact artifact/class output of the build to be released.
- [ ] Recorded the JDK version and `jdeps` command used.
- [ ] Supplied complete classpath or module path.
- [ ] Reviewed overview dependencies.
- [ ] Analyzed at package-level to understand architectural boundaries.
- [ ] Used class-level to trace suspect dependencies.
- [ ] Addressed `not found` dependencies.
- [ ] Ran `--jdk-internals` and evaluated replacement APIs.
- [ ] Checked module descriptors if the project uses JPMS.
- [ ] Reviewed every auto-generated `module-info.java`.
- [ ] Accounted for dynamic loading, reflection, service providers, and JNI.
- [ ] Ran tests on the target runtime/module path.
- [ ] Stored reports for comparison in future migrations.

## Conclusion

`jdeps` analyzes Java dependencies across multiple levels: class to pinpoint specific references, package to evaluate architectural boundaries, and module to prepare or verify JPMS. Options such as `--missing-deps`, `--jdk-internals`, `--check`, `--print-module-deps`, `--generate-module-info`, and `--dot-output` support different migration steps. For reliable conclusions, analyze the exact artifact with a complete classpath/module path, combine with Maven/Gradle dependency reports, and verify dynamic paths with runtime testing.