# Direct dependencies, transitive dependencies, and the resolved classpath

In a Spring Boot project, the build file often contains only a few lines of dependency declarations, yet at compile time or runtime, the application may use dozens or hundreds of libraries. This happens because one library can require other libraries, those libraries have their own dependencies, and the build tool must **resolve the entire dependency graph** before constructing the classpath for each task.

To properly understand a Spring Boot project, you need to distinguish three layers:

1. **Direct dependency**: a library the project explicitly declares that it wants to use.
2. **Transitive dependency**: a library brought in because another dependency requires it.
3. **Resolved classpath**: the set of JAR paths, class directories, and resources that a compilation task or runtime environment actually sees after dependencies are resolved.

These three layers are related but **not identical**. Seeing a dependency in the build file does not guarantee it will appear on every classpath. Conversely, a JAR may be on the runtime classpath even though you never directly declared its name.

## 1. Starting from a Spring Boot example

Suppose a project uses Gradle and has configured the Java and Spring Boot plugins along with an appropriate dependency version management mechanism. The following declaration block illustrates a REST application using validation, PostgreSQL, and a testing toolkit:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The four lines above declare **four direct dependencies** across different configurations. However, when Gradle resolves them, the dependency tree expands.

For example, in a Spring Boot 3.x release line using Spring MVC, the web starter typically pulls in:

- **spring-web** and **spring-webmvc** to provide Spring Framework web components.
- Core Spring Boot components.
- JSON support libraries, usually via Jackson.
- A default embedded Servlet container, typically Tomcat.
- Additional dependencies required by those libraries.

The exact list depends on the **Spring Boot version, starters, metadata, and build configuration**. This is a conceptual example, not a guarantee that every Spring Boot version has the exact same JAR structure.

A simplified visualization:

~~~text
Spring Boot Application
├── [DIRECT] spring-boot-starter-web
│   ├── [TRANSITIVE] Spring Web MVC components
│   ├── [TRANSITIVE] JSON components
│   ├── [TRANSITIVE] embedded Servlet container
│   └── [TRANSITIVE] other supporting libraries
├── [DIRECT] spring-boot-starter-validation
│   └── [TRANSITIVE] compatible validation libraries
├── [DIRECT] PostgreSQL JDBC driver (runtimeOnly)
└── [DIRECT] spring-boot-starter-test (testImplementation)
    └── [TRANSITIVE] testing libraries
~~~

In a real graph, branches can converge on **the same module**. Therefore, the resolved graph is typically a DAG rather than always being a strictly disjoint tree with no shared nodes.

## 2. What is a direct dependency?

A direct dependency is a requirement **explicitly declared by the project itself** to the build tool.

For example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Here, the project declares the web starter as a direct dependency. In the JVM ecosystem, an external module is typically identified by **group:artifact:version** coordinates:

~~~text
org.example:example-library:1.4.2
│           │               │
group       artifact        version
~~~

In addition to external modules, Gradle also supports dependencies on another project within the same multi-project build:

~~~groovy
dependencies {
    implementation project(':shared-domain')
}
~~~

In this case, the direct dependency is a **project dependency**. Depending on configuration, Gradle uses the outputs and appropriate dependencies of the **shared-domain** project to construct the classpath for the consuming project.

### 2.1. Direct declaration does not mean writing the entire list of JARs manually

If a project declares an HTTP client library, that library might need a cryptography library, a logging API, or a data parser. When dependency metadata describes those transitive requirements and resolution rules permit them, Gradle looks up those additional modules automatically.

You do not need to manually copy every dependency of a starter into the build file. Using a **starter** is a way of selecting a group of capabilities designed to work together.

### 2.2. Direct dependencies express intent of use

The following two declarations express two different intents:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

- **implementation**: application code is compiled against this dependency and its exposed dependencies according to the configuration's rules. This dependency also participates in the regular runtime classpath.
- **runtimeOnly**: a library needed at runtime but not required on the main code's compile classpath; typically suited for drivers or providers used via standard APIs or runtime registration.

In the PostgreSQL example, application code can work through **DataSource**, JDBC, or Spring Data abstractions without directly referencing driver implementation classes in source code. However, if the code directly calls a class belonging to the PostgreSQL driver, **runtimeOnly** may not be sufficient to compile.

## 3. What is a transitive dependency?

A **transitive dependency** is a dependency pulled in through one or more edges of the dependency graph.

Suppose:

~~~text
Application A
  └── B
       └── C
            └── D
~~~

If A declares B directly, and B declares C and C declares D under relationships that allow transitivity, then:

- B is a direct dependency of A.
- C and D are transitive dependencies with respect to A.

From A's perspective, C is still a transitive dependency even though it is a direct dependency of B. The concepts **direct** and **transitive** are always evaluated **relative to a consuming project**.

### 3.1. Where do libraries declare their dependencies?

For external modules, the information usually comes from:

- **Maven POM**: describes dependencies, scopes, and related metadata.
- **Gradle Module Metadata**: can describe variants, attributes, capabilities, and dependencies in finer detail.
- Other metadata provided by the repository/artifact or build rules.

Gradle reads metadata from configured repositories, builds the dependency graph for the configuration being resolved, selects the appropriate module/variant, and downloads the selected artifacts if needed.

**Not every dependency declared in a POM will appear on every classpath of the consuming project.** Scopes, optional flags, exclusions, variants, and Gradle rules can alter which edges propagate.

### 3.2. A module can be pulled in through multiple branches

~~~text
Application
├── Library A
│   └── Library C
└── Library B
    └── Library C
~~~

This does not necessarily mean there are two independent copies of C on the same resolved classpath. Gradle typically resolves multiple requests for the same module into a single **appropriate version and variant selection** for the configuration in question, based on conflict resolution rules.

Moreover, two different classpaths in the same project can select two different sets of artifacts. For example, the compile classpath and the test runtime classpath have their own extra dependencies, so you should not infer the entire runtime environment from a single graph.

### 3.3. A transitive dependency is not an API contract you can rely on long-term

Suppose application code directly imports a class from Library C, while only declaring Library A, and C happens to be pulled in through A. Today the code compiles; tomorrow A changes its implementation, no longer depends on C, and the application's build starts failing.

**Design principle:** when application code actively uses C's API, consider declaring **C as a direct dependency** with proper version management. That expresses the actual usage contract and reduces coupling to A's internal structure.

In Spring Boot, you do not need to declare every JAR inside a starter; however, if your source code intentionally uses an API outside the usage contract of the starter or library your project directly depends on, declaring your intent explicitly makes upgrades easier to control.

## 4. From declaration to resolved classpath: what does Gradle do?

One way to view the process:

~~~text
build.gradle
   │
   ├─ Direct dependencies
   └─ Configurations and build rules
                   │
                   ▼
       Dependency resolution
       ├─ Read module metadata
       ├─ Expand transitive dependencies
       ├─ Consider constraints / BOM / platforms
       ├─ Select matching version and variant
       ├─ Apply exclusions / substitutions / rules
       └─ Select artifacts for the requested configuration
                   │
                   ▼
       Resolved dependencies / artifacts
                   │
                   ├─ compileClasspath
                   ├─ runtimeClasspath
                   ├─ testCompileClasspath
                   └─ testRuntimeClasspath
                   │
                   ▼
       Compiler, test runner, Java process,
       Spring Boot packaging / execution
~~~

The sequence above is a conceptual model, not a fixed internal order of every Gradle API. The key point is that **dependency declarations are inputs**, while the **resolved configuration is the output** of multiple rules.

When a configuration is resolved, Gradle typically uses:

1. Directly declared or inherited dependencies.
2. Permitted metadata and transitive dependencies.
3. Version requirements and constraints.
4. Variant/capability/artifact selection rules.
5. Repositories where artifacts can be located.

If there is a version conflict, Gradle must choose an outcome according to the active resolution policy. If a module or artifact is missing from the repositories, resolution can fail before the application runs.

## 5. What is the classpath?

The **classpath** in Java is the set of locations that the compiler or runtime uses to look up classes and resources. These locations can be:

- Directories containing **.class** files.
- **.jar** files containing classes and resources.
- Other paths added via an appropriate classpath mechanism.

Conceptual example:

~~~text
Runtime classpath
├── build/classes/java/main/
├── build/resources/main/
├── spring-webmvc-<version>.jar
├── spring-context-<version>.jar
├── jackson-databind-<version>.jar
├── postgresql-<version>.jar
└── ...
~~~

In an application packaged as a Spring Boot executable JAR, physical paths inside the archive can differ: the Spring Boot plugin packages runtime dependencies into dedicated areas inside the archive and uses a launcher/class loader to run them. Thus, the list above only illustrates the **logical contents of the runtime classpath**, not the required structure of an executable JAR.

### 5.1. Compile classpath and runtime classpath are different

The **compile classpath** is where the compiler looks for classes needed to compile source code. The **runtime classpath** is where the application or a task looks for classes when running.

A dependency present on the compile classpath is not necessarily present on the runtime classpath. For instance, **compileOnly** provides APIs at compile time but is not automatically added to the regular runtime classpath.

Conversely, a dependency in **runtimeOnly** does not need to appear on the compile classpath, yet is still needed at runtime.

For example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Lombok is a familiar example of a library used during compilation and annotation processing. Declaring **compileOnly** and **annotationProcessor** serves two distinct roles. Annotation processors themselves use a separate processing path; merely adding a processor to the regular classpath does not guarantee Gradle will use it as an annotation processor.

### 5.2. The test classpath differs from the main application classpath

With the Java plugin in Gradle, familiar configurations include:

| Configuration | Typical meaning |
|---|---|
| **implementation** | Main code dependencies, used for compile and runtime per Java plugin configuration. |
| **compileOnly** | Needed to compile main code; not automatically placed on the main runtime classpath. |
| **runtimeOnly** | Needed when running main code; not automatically placed on the main compile classpath. |
| **annotationProcessor** | Dependencies serving annotation processors for main code. |
| **testImplementation** | Dependencies used for test sources. |
| **testCompileOnly** | Dependencies needed only to compile tests. |
| **testRuntimeOnly** | Dependencies needed only when running tests. |

For example, **JUnit** and utilities in the test starter are needed for testing, not by default as runtime dependencies of the production application. Running tests might succeed because a library is present on **testRuntimeClasspath**, while running the actual application fails because that library is absent.

That is why when investigating an error you must ask: **which task's classpath?** You cannot take test classpath results and conclude that the application's runtime classpath is equivalent.

### 5.3. API and implementation in reusable libraries

When using the **java-library** plugin in Gradle, a library can declare:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.example:public-contract:1.2.0'
    implementation 'org.example:internal-helper:2.0.0'
}
~~~

- **api**: dependencies that are part of the API contract exported to consuming projects and typically required on the consumer's compile classpath.
- **implementation**: dependencies used internally by the library; Gradle can keep them off the consumer's compile classpath under the appropriate variant model, while still supplying them at runtime when needed.

For instance, if a library's public signature returns a class from **public-contract**, the consumer must see that type at compile time. If **internal-helper** is only used inside a method body, it does not need to be exposed on the consumer's compile classpath.

This is one example of why **transitive** dependencies do not simply mean “declared somewhere, therefore visible everywhere.”

### 5.4. The compile classpath is not everything that can be loaded at runtime

In the JVM, there are also class loaders, module paths, environment-specific classpaths, libraries loaded dynamically via reflection, ServiceLoader, or plugin mechanisms. Some classes never appear directly in Java imports yet are needed at runtime.

Therefore, successful compilation does not prove runtime has every dependency. And an artifact present on the runtime classpath can still fail to load if it lacks another dependency, has an incompatible binary version, or encounters an unsuitable class loader configuration.

## 6. Where do Spring Boot starters fit into this picture?

A **starter** is a dependency that helps select a group of libraries for a common need. For example:

- **spring-boot-starter-web**: used for building Spring MVC web applications in Boot release lines that include this starter.
- **spring-boot-starter-validation**: supports validation integration.
- **spring-boot-starter-data-jpa**: brings in components commonly needed for JPA/Spring Data JPA.
- **spring-boot-starter-test**: gathers common testing tools.
- **spring-boot-starter-actuator**: adds observability and management endpoints depending on configuration.

A starter primarily defines a **set of dependencies**. It does not directly define your business logic. Spring Boot's automatic setup of appropriate beans is handled by **auto-configuration**, which is triggered by multiple conditions, including the classpath.

For example:

~~~text
You declare the web starter
          │
          ▼
Gradle resolves transitive dependencies
          │
          ▼
Classpath has Spring MVC and appropriate web runtime
          │
          ▼
Spring Boot evaluates auto-configuration
          │
          ▼
If conditions are met, Boot configures
DispatcherServlet and web infrastructure
          │
          ▼
Your controller has an environment to handle HTTP
~~~

Two points should be kept separate:

1. **Having a JAR on the classpath** satisfies the library-presence condition; it does not guarantee every related feature is enabled.
2. **Conditional auto-configuration**: depending on classpath, existing beans, properties, and application type, Boot may enable, skip, or adjust a configuration.

For example, adding a JDBC driver does not automatically provide the database URL and credentials. Similarly, adding the validation starter does not automatically write business rules such as requiring an order quantity to be greater than 0.

### 6.1. Starters are usually not the primary executable code

A starter may contain mainly metadata/dependency declarations to pull in a compatible group of libraries. The actual code handling HTTP lives in Spring MVC, the Servlet container, Jackson, and other components. Reading only the starter name without checking the transitive graph can lead to misunderstanding which library performs a given behavior.

### 6.2. Does using multiple starters cause duplicate libraries?

Multiple starters can request the same Spring core or logging module. Gradle resolves edges for the same module per configuration; typically, those requests converge to a single selected module. You do not need to manually exclude every duplicate transitive path.

However, if two starters pull in **competing implementations** or modules with conflicting capabilities, you still need to understand usage intent and build configuration; do not assume every combination of starters is always sensible.

## 7. Version management: who decides the final version?

Imagine:

~~~text
Application
├── Library A → Library C version 1.2
└── Library B → Library C version 1.5
~~~

The graph has two different version requests for the same module C. The build tool must decide **which version is selected** for the configuration being resolved.

In Gradle, the default conflict resolution policy for many common cases is to **select the higher version among the requested versions**, though the outcome is also influenced by constraints, rich versions, platforms, capabilities, metadata, forced versions, dependency substitutions, and other rules. **Do not mechanically assume** “Gradle always picks the newest version in the repository”: Gradle resolves based on *the provided requests and rules*, rather than arbitrarily upgrading to the latest version available online.

Maven has a different dependency mediation mechanism; in typical conflicts it may apply the **nearest definition** rule, alongside influences from dependencyManagement. Therefore, you should not blindly apply a Maven rule to explain a Gradle result.

### 7.1. Spring Boot BOM and dependency management

Spring Boot publishes a **BOM (Bill of Materials)** containing a managed version list for many related libraries. The BOM helps Spring components and popular libraries use versions selected to work together.

For example, a project with the Spring Boot plugin and **io.spring.dependency-management** properly configured can declare:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Dependencies without version numbers can only resolve successfully when **the build already supplies appropriate version management metadata**. In setups combining the Boot plugin with the dependency-management plugin, the corresponding BOM is usually imported automatically. When using a Gradle native platform, you must declare the platform/BOM properly according to your project's setup.

**Merely applying the Spring Boot plugin is not a universal guarantee that every versionless dependency will automatically be managed in every build style.** The project's specific dependency management mechanism determines that.

### 7.2. The BOM does not automatically pull every library onto the classpath

A BOM mainly defines **version constraints or version recommendations** for module coordinates. It does not mean every module listed in the BOM is downloaded and packaged into the application.

~~~text
BOM manages versions of A, B, C, D
                   │
      Project declares dependency B
                   │
                   ▼
       Selects version of B
       and its resolved dependencies
                   │
                   ▼
       A, C, D appear only if there is
       an appropriate dependency path
~~~

That is the difference between **managing versions** and **requiring a library to be present**.

### 7.3. Overriding versions can cause conflicts

You can declare or constrain a version different from the one Boot manages. However, a newer or older library might expect an API or binary contract incompatible with the remaining libraries.

For example:

~~~text
Spring Boot BOM: selects compatible version of library X
Application: forces X to another version
                           ↓
                 Dependency resolution
                           ↓
          A version may be selected, yet
          still cause binary errors at runtime
~~~

Successful resolution only proves the build tool **found and selected artifacts**. It does not prove all classes and APIs used are compatible at runtime.

### 7.4. Version conflict and duplicate class are two distinct issues

- **Version conflict**: multiple edges in the graph request **the same module** at different versions.
- **Duplicate class**: **two different artifacts** both contain classes with identical package and class names, or packaging/shading causes overlap.

Gradle resolving the version of a single module does not guarantee there are no duplicate classes across differently named modules. Duplicate classes can lead to class-loading-order-dependent behavior and hard-to-diagnose errors.

## 8. Configurations decide where dependencies go

A dependency does not just have a name and version; it is placed in a **configuration** with its own rules and inheritance relationships.

For example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

For a typical Java application:

~~~text
compileClasspath
  ├─ outputs / classpath needed for compilation
  └─ implementation dependencies

runtimeClasspath
  ├─ main application output
  ├─ implementation dependencies
  └─ runtimeOnly dependencies

testCompileClasspath
  ├─ outputs + dependencies needed to compile tests
  └─ testImplementation and related dependencies

testRuntimeClasspath
  ├─ application outputs + test outputs
  ├─ application runtime dependencies
  └─ test runtime dependencies
~~~

This is an intuitive diagram and does not show every plugin `extendsFrom`/variant detail. In particular, test classpaths also depend on the active plugins and source sets. A custom **integrationTest** source set may have its own configurations; do not assume it behaves identically to **test**.

### 8.1. Why do tests pass while bootJar fails?

Suppose code invokes a library at runtime, but that library was accidentally added only to **testImplementation**. Tests can see the library, whereas the main application runtime cannot. If main code directly imports the class, main compilation usually catches the missing class; however, with reflection, ServiceLoader, or dynamic class loading by name, the wrong configuration may only surface at runtime.

Conversely, if a library is declared **compileOnly** when runtime actually needs it, code can compile yet fail at runtime. The error may be **NoClassDefFoundError** or a similar class-loading failure.

### 8.2. Annotation processors are not runtime dependencies

Annotation processors run during compilation to generate code or inspect annotations. For instance, Lombok is declared in **annotationProcessor** to participate in compilation. That does not mean runtime needs to load Lombok itself to execute the compiled bytecode.

In other cases, a processor generates source code that must be compiled and packaged, while a runtime library providing annotations or implementations is a separate dependency. Therefore, read the tool's contract instead of blindly moving every annotation processor into **implementation**.

## 9. The resolved classpath changes depending on how the application is run

Do not treat the **resolved classpath** as a single number or a single list that exists uniformly across the entire project. There are multiple environments:

| Context | Classpath/artifact to inspect |
|---|---|
| Compiling main sources | **compileClasspath** and related compilation configurations. |
| Running unit tests | **testRuntimeClasspath**. |
| Running app from IDE | The classpath built by the IDE from the Gradle model and run configuration. |
| Running Gradle bootRun | The runtime classpath of the Boot task with its associated settings. |
| Packaging executable bootJar | Runtime artifacts selected by the Boot plugin for packaging, plus application outputs. |
| Running executable JAR | Classes/resources actually loaded from the archive by the launcher and class loader. |
| Deploying WAR to an external container | Class loading also depends on the container and dependencies marked via appropriate mechanisms. |

Because execution methods differ, **running in an IDE can succeed while running the JAR fails**. In such cases, looking at dependency declarations alone is not enough; you must compare the packaged artifact and actual runtime.

### 9.1. Spring Boot Executable JAR

For a typical Spring Boot executable JAR, the logical layout may look like:

~~~text
application.jar
├── META-INF/
├── BOOT-INF/
│   ├── classes/
│   │   ├── application classes
│   │   └── application resources
│   └── lib/
│       ├── library A.jar
│       ├── library B.jar
│       ├── library C.jar
│       └── ...
└── launcher components
~~~

The Boot launcher supports loading classes from nested JARs inside the archive. This set of artifacts reflects the task's packaging rules and appropriate runtime dependencies, rather than copying the entire Gradle cache directory or all test dependencies into the JAR.

Across different versions, layouts, or packaging types, exact details may vary. The underlying concept remains **packaging what is needed for the chosen execution model**.

### 9.2. A plain JAR and an executable JAR are not the same

A JAR built by the regular **jar** task typically contains only the project's code and resources, whereas **bootJar** creates an executable archive including dependencies arranged in Boot's layout.

Therefore, errors such as “running `java -jar` and a library is missing” also require checking **which artifact you are running**, not just inspecting `build.gradle`.

## 10. Real-world scenario: seeing a class without knowing where it came from

Suppose you did not directly declare a JSON library, yet your project can still import classes from it. It may have been pulled in by the web starter.

Do not guess based on “Spring Boot probably includes it.” Find the **dependency path**:

~~~text
Application
  └─ spring-boot-starter-web
       └─ starter JSON component
            └─ Jackson module
~~~

The actual path must be verified from the resolved dependency graph. If the JSON library is used directly in your public API or source code, consider declaring the appropriate module directly. If it is solely an internal implementation detail inside auto-configuration, you usually do not need to declare every module manually.

### 10.1. Useful Gradle commands for inspection

In a Gradle project, the **dependencies** task shows the graph per configuration. On a machine with a Unix shell:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat :app:dependencies --configuration runtimeClasspath
~~~

**:app** is an example Gradle project name. For a single-project build, you can omit the project path prefix:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

This command reads the resolution result of the selected configuration; it does not automatically run the Spring Boot application.

When you want to know **why a module appears and which version was selected**, use **dependencyInsight**:

~~~bash
./gradlew :app:dependencyInsight \
  --configuration runtimeClasspath \
  --dependency jackson-databind
~~~

In PowerShell, you can write it on one line:

~~~powershell
.\gradlew.bat :app:dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
~~~

The output typically reports the selected version and relevant dependency paths; details vary by Gradle version, dependency metadata, and configuration. If you see one version replaced by another, investigate the selection/constraint reason instead of immediately forcing a version.

**Do not run diagnostic commands blindly in every project:** some builds have configuration or generator tasks with side effects. When conducting a real investigation, read the project structure and documentation first, then choose the appropriate command.

### 10.2. With Maven

The direct/transitive/runtime concepts are similar, though configurations and version selection rules differ. A common command:

~~~bash
mvn dependency:tree
~~~

Maven has scopes such as **compile**, **runtime**, **test**, **provided**, and **system** with semantics that differ from Gradle configurations. Do not mechanically translate each Maven scope into an identically named Gradle configuration.

### 10.3. Reading dependency tree output

An illustrative tree might show:

~~~text
+--- com.example:library-a:1.0
|    \--- com.example:shared-lib:1.2 -> 1.5
\--- com.example:library-b:2.0
     \--- com.example:shared-lib:1.5
~~~

The meaning of **1.2 -> 1.5** in this display style is that an initial request for `1.2` on that edge was resolved to **1.5**. You cannot conclude “both JARs 1.2 and 1.5 are present” just because both numbers appear in the output.

Markers such as **(*)** or other notations in a Gradle tree may represent repeated branches and task display conventions; interpret them according to the Gradle version in use.

## 11. Exclusions: intentionally cutting a transitive edge

When a dependency pulls in an unwanted library, Gradle provides an **exclude** mechanism. Illustrative example:

~~~groovy
dependencies {
    implementation('com.example:legacy-client:1.0') {
        exclude group: 'com.example', module: 'old-logging-bridge'
    }
}
~~~

This requests excluding the dependency with the specified group/module **along that specific declaration path**. However, understand that:

1. An excluded module may still appear if **another path** in the graph continues to request it.
2. Excluding does not automatically replace code that actually needs the removed library.
3. Removing a library just because its name appears twice in the dependency tree can break runtime.
4. Depending on the case, the right fix may be replacing the original dependency, using a different variant, adjusting version alignment, or updating code.

For example, if library A genuinely requires classes from library C, removing C from the graph without providing an alternative will cause class-loading failures.

### 11.1. Replacing a default starter

In a Spring Boot application, there may be a need to use a different web server from the starter's default. The solution typically involves **excluding the default server component pulled in** and **adding the appropriate replacement starter/server**. However, you must verify the exact Boot version and current dependency graph before applying it; module names and starter structures can change between Boot lines.

Key point: **an exclusion must serve a concrete architectural choice**, not a habit of “trimming the dependency tree to look shorter.”

## 12. Why can errors still happen even when dependencies resolve?

Successful resolution means Gradle found a result satisfying **dependency resolution rules**. It does not prove your code uses them properly or that they are compatible across every execution path.

Typical errors:

### 12.1. ClassNotFoundException

~~~text
java.lang.ClassNotFoundException: com.example.SomeClass
~~~

Usually occurs when a class-loading mechanism by name cannot find the class using the active class loader. Check the runtime classpath, packaged artifact, and relevant class loader.

### 12.2. NoClassDefFoundError

~~~text
java.lang.NoClassDefFoundError: com/example/SomeClass
~~~

This is an **Error** that can occur when the JVM cannot define or use a class expected to be present at runtime—for instance, when the class was present at compile time but missing from runtime dependencies. It can also stem from an earlier class initialization failure; do not assume every `NoClassDefFoundError` is merely a “forgotten JAR.”

A clue worth checking: whether the module was declared **compileOnly** or only in **testImplementation**, when runtime needs it.

### 12.3. NoSuchMethodError and NoSuchFieldError

~~~text
java.lang.NoSuchMethodError: ...
~~~

This type of error typically indicates that a class at runtime **does not provide a member** expected by the compiled bytecode. A common cause is **binary incompatibility** between library versions. Look up the actual resolved version and the actual loaded artifact, rather than just checking the version written in one declaration line.

### 12.4. Service/provider not working

An application can compile and start, yet a feature fails to work due to a missing provider, implementation, metadata, or auto-configuration condition. For example:

- Missing an appropriate JDBC driver at runtime.
- Missing a required provider for an integrated API.
- Having the dependency, but configuration properties have not been supplied.
- A bean declared outside the component scan scope.

In these situations, adding dependencies does not solve every cause. You need to inspect the **classpath**, **configuration**, and **which Spring components are being initialized**.

### 12.5. Duplicate APIs or implementations on the classpath

Two libraries may contain overlapping class/package names due to repackaging or because an older library bundles a copy of an API. In that case, even if each module only has one selected version, the class loader can encounter unpredictable behavior or binary errors.

Determine which physical artifacts contain the class, which dependency paths pull them in, and whether an alignment/relocation solution is required rather than arbitrary exclusions.

## 13. Auto-configuration depends on the classpath, but not only on the classpath

Spring Boot uses many conditional configurations, such as checking class presence with **@ConditionalOnClass**, existing beans via **@ConditionalOnMissingBean**, properties via **@ConditionalOnProperty**, and web application type.

A simplified model:

~~~text
Appropriate dependencies resolved?
              │
              ▼
Required classes present on classpath?
              │
              ▼
Other auto-configuration conditions met?
              │
       ┌──────┴───────┐
       │              │
      Yes            No
       │              │
       ▼              ▼
 Configuration     Configuration
 may be applied    is skipped
~~~

Therefore:

- Having **spring-webmvc** on the classpath does not guarantee all controllers are registered.
- Having a JDBC driver does not guarantee Boot configures the right `DataSource`.
- Having Actuator does not guarantee all management endpoints are exposed.
- Having two different starters can alter how Boot detects application type or selects auto-configuration.

When a bean does not appear as expected, inspect both the **resolved classpath** and **actual conditions**, not just the starter name in the build file.

## 14. Diagnostic example: an error that only happens after packaging

Suppose a service uses a provider at runtime via reflection. When running tests in the IDE, the feature works, but the executable JAR reports:

~~~text
java.lang.ClassNotFoundException: com.example.provider.JsonProvider
~~~

A reasonable investigation path:

1. **Identify the error context**: which artifact is the Java process running? Is it a JAR produced by **bootJar** or a plain JAR?
2. **Check the dependency configuration**: is the provider library declared in **testImplementation**, **compileOnly**, **runtimeOnly**, or **implementation**?
3. **Inspect the actual runtimeClasspath**: is the provider resolved for the main source set?
4. **Inspect the packaged artifact**: is the provider JAR inside the runtime dependency area of the executable JAR?
5. **Inspect classes inside the artifact**: is the class/package name from the right version, or has it been renamed/relocated?
6. **Check class loading**: which class loader does the application use, and does it require separate metadata/service registration?

If the provider is only in **testImplementation**, tests seeing it makes sense; the runtime application lacks it. When the application genuinely needs the provider at runtime, declare it in the appropriate configuration, such as **runtimeOnly** if source code does not directly reference the provider's API.

If the class exists inside the runtime artifact yet the error persists, continue investigating the class loader, binary compatibility, and class-loading mechanism. Do not assume “add a JAR” is the solution to every `ClassNotFoundException`.

## 15. Diagnostic example: two libraries require different versions

An app uses two clients:

~~~text
Application
├── report-client:2.0
│   └── common-utils:1.6
└── billing-client:3.0
    └── common-utils:2.1
~~~

You read the build file and only see **report-client** and **billing-client**. At runtime, a method in `report-client` throws **NoSuchMethodError**.

A sensible investigation path:

1. Print the **runtimeClasspath dependency tree**.
2. Run **dependencyInsight** for **common-utils**.
3. Confirm the final version of `common-utils` and why it was selected.
4. Compare the API that `report-client` was compiled against with the API of the `common-utils` actually loaded.
5. Check release notes, compatibility matrices, or BOM/constraints for both clients.
6. Choose a compatible version set, update one client, or deliberately adjust dependency alignment.

Forcing `common-utils` back to **1.6** just because `report-client` requests it could break `billing-client`. Conversely, picking **2.1** under Gradle's policy does not guarantee `report-client` is compatible. **Dependency resolution** solves artifact selection by rules; **API/binary compatibility** still must be verified through actual behavior.

## 16. Some common misconceptions

**“Declaring four dependencies means only four JARs.”**  
No. Direct dependencies can pull in many transitive modules. The final JARs depend on configurations and resolution.

**“Once a starter is declared, every library in the BOM is downloaded too.”**  
No. Starters request a set of dependencies; the BOM provides version metadata for modules in use. They perform two different jobs.

**“Two dependency paths to the same module mean the classpath contains two versions.”**  
Not necessarily. Gradle typically resolves a module to one selected version per configuration, though duplicate classes across differently named modules remain a separate issue.

**“If a module is in the dependency tree, code in any source set can import it.”**  
No. You must check the **configuration** and classpath in question. **testImplementation**, **runtimeOnly**, and **compileOnly** serve different purposes.

**“A successful build means it can run.”**  
No. Compilation can succeed while runtime lacks a class/provider, hits binary incompatibility, or has misconfigured application settings.

**“Since Spring Boot manages versions, overriding any version is safe.”**  
No. The managed version set aims for compatibility; overriding requires understanding the impact across the entire graph.

**“Excluding an unwanted JAR guarantees conflicts are gone.”**  
No. Another edge may still pull the JAR in, or removing the JAR may break a library that depends on it.

**“Having a JAR on the classpath means Spring Boot automatically creates all related beans.”**  
No. Auto-configuration also depends on conditions such as existing beans, properties, environment, and application type.

**“The classpath on a developer's machine is always identical to the executable JAR.”**  
No. IDEs, test runners, `bootRun`, and packaged artifacts can use different classpaths or class-loading mechanisms.

## 17. How to think when adding or modifying a dependency

Before editing the `dependencies` block, answer four questions:

1. **Which API am I using?** If source code directly uses a library's API, that is usually a clear dependency intent that should be expressed.
2. **At which phase is the library needed?** Compile, runtime, test, or annotation processing?
3. **Who manages the version?** Spring Boot BOM/platform, a project-specific dependency constraint, or an explicitly specified version?
4. **Where does the artifact actually come from?** A direct declaration, a starter, a project dependency, or a transitive path?

From these four questions, choose the right configuration, inspect the resolved graph, and only add exclusions or version overrides when there is a concrete reason. When runtime errors happen, keep asking **what the packaged artifact and class loader actually contain**.

## Core takeaway

**Direct dependencies** express what the project declares it wants to use. **Transitive dependencies** expand those requests based on metadata and inter-library relationships. The **resolved classpath** is the resolution output for **a specific configuration and execution context**.

In Spring Boot, **starters** help declare dependency groups, **BOM/dependency management** helps select compatible versions, and **auto-configuration** uses conditions like the classpath and current configuration to set up application components. Grasping these boundaries helps you understand why a class appears without being declared directly, why a library is missing at runtime even though tests pass, and where to look when version dependency errors arise.
