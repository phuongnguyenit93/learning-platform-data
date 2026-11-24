# Reading the dependency tree to find conflicts or unexpectedly pulled libraries

In Spring Boot, declaring a starter is usually very concise, yet the libraries actually used can number dozens or hundreds of artifacts. A single line declaring `spring-boot-starter-web` can pull in Spring MVC, JSON processing libraries, logging, and an embedded web server; a single `spring-boot-starter-data-jpa` can pull in Spring Data, Hibernate, persistence-related APIs, and transactions.

When an application encounters `NoSuchMethodError`, `ClassNotFoundException`, logging conflicts, behavioral changes after a version bump, or an unwanted library appearing in the packaged artifact, the key is locating the **path from a directly declared dependency to the problematic artifact**. The most useful tool to start with is the **dependency tree**.

This lesson guides you through reading dependency trees in Spring Boot projects using **Maven** or **Gradle**, distinguishing direct and transitive dependencies, interpreting version selection markers, finding unexpectedly pulled libraries, and resolving conflicts cleanly.

## 1. What does a dependency tree tell us?

A **dependency** is a library or component used by a project during compilation, runtime, or testing. Dependencies can be declared directly or pulled in via another dependency:

- **Direct dependency**: declared by the project in `pom.xml` or `build.gradle`/`build.gradle.kts`.
- **Transitive dependency**: a library needed by another dependency, so the dependency manager includes it in the graph.
- **Resolved dependency**: the artifact version selected after Maven or Gradle applies version management rules, conflict resolution, scopes/configurations, and related conditions.
- **Classpath**: the set of classes and resources used by a compiler, the JVM, or a specific task. A project can have multiple distinct classpaths.

Illustrative example (not literal output from a specific Spring Boot version):

~~~text
bookstore
└── spring-boot-starter-web
    ├── spring-boot-starter
    │   └── spring-boot-starter-logging
    ├── spring-web
    ├── spring-webmvc
    └── spring-boot-starter-tomcat
~~~

Looking at the tree, we see `spring-webmvc` or `spring-boot-starter-tomcat` is present because `spring-boot-starter-web` pulled it in. If we need to answer “who added Tomcat?”, the answer lies in the **parent branch**, not solely in the leaf library name.

Distinguish three questions:

1. **Who requested this library?** Trace the branches leading from the root project to the artifact.
2. **What is the final version?** Read the *resolution* result and version management rules.
3. **Is the artifact present in the failing context?** Check the exact scope/configuration and classpath in use—for example, application runtime rather than the test classpath.

The dependency tree is a **snapshot of the dependency graph computed by the build tool**. It does not replace inspecting the actual JAR, container-provided libraries, or dynamically loaded classes, yet it is usually the fastest and most valuable starting point.

## 2. Why do starters make reading the dependency tree so important?

Spring Boot provides numerous *starters* to bring in groups of libraries by need:

| Common starter | Purpose | Library groups that may appear in the tree |
|---|---|---|
| `spring-boot-starter-web` | Building web applications based on Spring MVC | Spring Web, Spring MVC, JSON, embedded servlet server |
| `spring-boot-starter-webflux` | Building reactive web applications | Spring WebFlux, Reactor, and related components |
| `spring-boot-starter-data-jpa` | Accessing data via Spring Data JPA | Spring Data, Hibernate ORM, Spring ORM, JDBC, transactions |
| `spring-boot-starter-security` | Integrating Spring Security | Applicable Spring Security modules |
| `spring-boot-starter-validation` | Bean Validation | Validation API and implementation |
| `spring-boot-starter-test` | Testing support | Spring Test, JUnit, Mockito, and related test libraries |

Exact components and versions can change across Spring Boot releases. Therefore, instead of memorizing every transitive artifact name, read the **tree of your actual project and version**.

A starter alone does not prove a component will be instantiated by Spring. The dependency tree confirms **classes/libraries can be present**; Spring Boot's auto-configuration still evaluates classpath, properties, defined beans, and other conditions. For instance, simply having a JDBC driver on the classpath does not mean database connections will succeed.

## 3. Reading the dependency tree in Maven

### 3.1. Maven project example

A Spring Boot project might declare dependencies like this when using the Spring Boot parent or equivalent version management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

To display the dependency graph, run in the directory containing `pom.xml`:

~~~bash
./mvnw dependency:tree
~~~

On Windows PowerShell or Command Prompt, using the Maven Wrapper:

~~~powershell
.\mvnw.cmd dependency:tree
~~~

If the project uses a globally installed Maven, you can replace `./mvnw` with `mvn`.

The command invokes the `dependency:tree` goal from the Maven Dependency Plugin. Output can vary across Maven versions, plugin versions, and project setups.

### 3.2. Analyzing an output snippet

The following example only simulates the shape of the output; version strings like `X.Y.Z` are placeholders and do not represent a real release:

~~~text
[INFO] com.example:bookstore:jar:1.0.0
[INFO] +- org.springframework.boot:spring-boot-starter-web:jar:X.Y.Z:compile
[INFO] |  +- org.springframework:spring-web:jar:A.B.C:compile
[INFO] |  +- org.springframework:spring-webmvc:jar:A.B.C:compile
[INFO] |  \- org.springframework.boot:spring-boot-starter-tomcat:jar:X.Y.Z:compile
[INFO] +- org.postgresql:postgresql:jar:P.Q.R:runtime
[INFO] \- org.springframework.boot:spring-boot-starter-test:jar:X.Y.Z:test
~~~

Each Maven dependency line typically follows the format:

~~~text
groupId:artifactId:type:version:scope
~~~

A `classifier` may also appear, such as `groupId:artifactId:type:classifier:version:scope`. In the example:

- `org.springframework.boot` is the starter's **groupId**.
- `spring-boot-starter-web` is the **artifactId**.
- `jar` is the artifact type.
- `X.Y.Z` is the resolved version.
- `compile`, `runtime`, and `test` show the Maven scope in that tree output.
- `+-` and `\-` along with `|` and indentation show parent–child relationships.

Read **left to right and top to bottom**: `spring-webmvc` sits beneath `spring-boot-starter-web`, so it is pulled in via this starter's branch. The indentation structure tells you “why the library is present.”

### 3.3. Filtering for a group of libraries

When a tree is too long, you can ask Maven to display only branches involving a specific artifact:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-webmvc
~~~

Or filter by group:

~~~bash
./mvnw dependency:tree -Dincludes=org.slf4j:*
~~~

You can narrow by scope depending on your goal:

~~~bash
./mvnw dependency:tree -Dscope=runtime
~~~

Note: filtering yields a **narrow view of the tree** and does not prove other branches do not exist elsewhere in the project. When investigating bugs, read the full tree at least once and confirm the exact scope you need.

In some PowerShell versions, special characters and `-D...` arguments may parse differently than in Bash. When needed, wrap the entire argument in quotes such as `"-Dincludes=org.slf4j:*"` to pass the literal value to Maven.

### 3.4. Reading branches omitted due to conflicts

Maven can receive multiple requests for the **same artifact with different versions**. The version actually chosen might differ from a version sitting deeper inside an intermediate dependency's tree.

With Maven Dependency Plugin versions supporting display of omitted branches, you can run:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Illustrative example:

~~~text
com.example:bookstore:jar:1.0.0
+- com.example:payment-sdk:jar:2.0:compile
|  \- com.example:json-helper:jar:3.1:compile
\- com.example:legacy-client:jar:1.0:compile
   \- (com.example:json-helper:jar:2.5:compile - omitted for conflict with 3.1)
~~~

This means:

- `payment-sdk` requests `json-helper:3.1`.
- `legacy-client` requests `json-helper:2.5`.
- Maven selected `3.1` in this example scenario.
- The `2.5` branch is shown to explain the conflict; **it does not mean both versions are loaded onto the runtime classpath**.

Exact markers and visibility of omitted branches depend on the plugin version. If you do not see `omitted for conflict`, do not assume there is zero version contention: you may need the right tree options, the effective POM, or other resolution details.

### 3.5. Why did Maven choose that version?

A foundational Maven principle is **nearest definition**: in ordinary transitive dependency conflicts, a shorter path from the root project to a version is generally preferred. At equal depth, declaration order can decide which version wins first. However, `dependencyManagement` can govern/override dependency versions and change the outcome; directly declared dependencies also carry clear precedence.

Hypothetical example:

~~~text
bookstore
├── module-a
│   └── library-x:2.0
└── module-b
    └── module-c
        └── library-x:1.0
~~~

Without version management rules affecting it, `library-x:2.0` on the shorter branch is likely selected. However, if the project manages `library-x` via a BOM or `dependencyManagement`, inspect the **actual resolved output** rather than inferring solely from tree depth.

In Spring Boot projects, the parent POM or `spring-boot-dependencies` BOM usually manages the versions of many core libraries. A starter omitting a version number in `pom.xml` does not mean Maven picks one arbitrarily; the version is supplied through this management mechanism.

## 4. Reading the dependency tree in Gradle

### 4.1. Gradle project example

Example with Groovy DSL in `build.gradle`, assuming the Spring Boot plugin and dependency management mechanism are properly configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Unlike Maven, Gradle uses **configurations** to define where dependencies are used. Common configurations in Java projects:

| Configuration | Practical meaning |
|---|---|
| `implementation` | Dependencies used to compile and run main code, not exposed as the public API of a Java library |
| `api` | Used with the `java-library` plugin to mark dependencies belonging to the public API |
| `compileOnly` | Present on the compile classpath, not automatically placed into runtime |
| `runtimeOnly` | Needed at runtime, not needed when compiling main code |
| `testImplementation` | Dependencies for compiling/running tests per test configuration |
| `testRuntimeOnly` | Dependencies needed only when running tests |
| `runtimeClasspath` | Resolved classpath for main code runtime |
| `testRuntimeClasspath` | Resolved classpath for test runtime |

If a bug occurs only when running the application, inspecting `runtimeClasspath` is usually more informative than looking only at `implementation`. If it occurs only in tests, inspect `testRuntimeClasspath`.

### 4.2. Displaying the tree for a specific classpath

On Unix-like operating systems:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

On Windows:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

For tests:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Output depends on Gradle version, plugins, configurations, and declared constraints. The snippet below only illustrates the format:

~~~text
runtimeClasspath - Runtime classpath of source set 'main'.
+--- com.example:feature-a:1.0
|    \--- com.example:shared-lib:1.5 -> 2.1
+--- com.example:feature-b:3.0
|    \--- com.example:shared-lib:2.1
\--- org.springframework.boot:spring-boot-starter-web:...
~~~

The line `com.example:shared-lib:1.5 -> 2.1` indicates that this branch requested `1.5`, yet **the selected version is `2.1`**. This is key information when hunting conflicts. Looking at the version to the left of the arrow and concluding the app runs `1.5` is incorrect.

Gradle can display markers such as:

- `->`: the resolved version or target differs from the initial request.
- `(*)`: dependency branch already expanded elsewhere in the report and not repeated.
- `(c)`: line referring to a dependency constraint.
- `(n)`: dependency or configuration not resolved in the manner being displayed.

Markers can vary across Gradle versions. Check the legend at the bottom of the output and match it to your project's Gradle version.

### 4.3. Querying a specific dependency with dependencyInsight

Once you know the suspect artifact, `dependencyInsight` helps determine **who requested it** and **why Gradle selected the active version**:

~~~bash
./gradlew dependencyInsight \
  --dependency com.example:shared-lib \
  --configuration runtimeClasspath
~~~

On PowerShell, you can write it on one line:

~~~powershell
.\gradlew.bat dependencyInsight --dependency com.example:shared-lib --configuration runtimeClasspath
~~~

The output can list the different requesting paths and *selection reasons* such as conflict resolution, constraints, rules, or other version selection rules. Exact output depends on your Gradle setup.

Hypothetical scenario: `feature-a` requests `shared-lib:1.5`, `feature-b` requests `2.1`. If Gradle resolves to `2.1`, `dependencyInsight` reveals both requests and why `2.1` was chosen. This is a major advantage over merely reading `build.gradle`, where `shared-lib` might not be declared directly at all.

**Note:** By default, Gradle typically selects the highest version when resolving dynamic/transitive version conflicts, yet constraints, platforms/BOMs, strict versions, forced versions, metadata, and resolution rules can alter the outcome. Do not deduce the actual version from a general rule alone; inspect the resolution output.

## 5. Reading scope accurately: a dependency can appear in tests without existing at runtime

A common mistake is seeing a library in the dependency tree and assuming the deployed artifact definitely contains it.

### Maven scopes

| Scope | Common meaning | Impact on investigation |
|---|---|---|
| `compile` | Available at compile time and related classpaths | Can be packaged into runtime artifacts depending on packaging |
| `runtime` | Needed when running, not required to compile | Fits JDBC drivers needed only at runtime |
| `test` | For testing | Should not be expected inside normal application JARs |
| `provided` | Available during compilation, expected to be supplied by runtime/container | Can cause missing classes if the actual environment omits it |
| `system` | Points to a local JAR by explicit path | Usually harms build reproducibility; generally avoid |
| `import` | Used in `dependencyManagement` with POM-type BOMs | Manages versions; does not automatically mean a runtime library |

Scopes follow Maven's dependency transitivity rules, so the scope shown in tree output may result from parent–child scope interaction rather than copying every original declaration verbatim.

### Gradle configurations

In Gradle, `implementation` does not mean “all dependencies of this kind exist on every classpath.” Ask precisely which configuration was resolved:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

If a dependency only exists in `testRuntimeClasspath`, do not use its presence to explain behavior in the production application. Conversely, a library missing from `runtimeClasspath` can cause `NoClassDefFoundError` even if code compiled earlier via `compileOnly` or differences in build setup.

## 6. Finding an unexpectedly pulled library

Suppose a Spring Boot project intends to use WebFlux with Reactor Netty, yet inspecting the dependency tree reveals embedded Tomcat. Or the project intends to use one logging stack, yet an unwanted binding appears. The investigation does not start by deleting dependencies at random; trace the branch pulling that artifact in.

### Step 1: identify the exact artifact

The library name in logs may not match the dependency name word for word. For example:

- Logging error mentions `SLF4J`: find the corresponding group and artifacts for providers/bindings.
- Log mentions `Tomcat`: find Tomcat artifacts and web starters that might pull them in.
- Jackson error: look for `jackson-databind`, `jackson-core`, and related modules.
- Java class error: identify which artifact provides the class before filtering.

If you do not know the artifact yet, inspect the full tree or check the relevant library's metadata. Do not guess `groupId` from a Java package name without verifying.

### Step 2: find the path bringing the artifact in

In Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.apache.tomcat.embed:*
~~~

In Gradle:

~~~bash
./gradlew dependencyInsight --dependency tomcat-embed-core --configuration runtimeClasspath
~~~

A conceptual path example:

~~~text
bookstore
└── spring-boot-starter-web
    └── spring-boot-starter-tomcat
        └── tomcat-embed-core
~~~

Thus, Tomcat did not “appear out of nowhere”: it came from the web starter. If the project intentionally uses `spring-boot-starter-web`, Tomcat may be completely expected. If the project wants only WebFlux/Netty, review the added starters or the branch bringing it in.

### Step 3: inspect the actual configuration

Sometimes a library appears on the **test classpath** but not on the **runtime classpath**; sometimes a subproject contributes the dependency; sometimes a BOM only manages the version without pulling the artifact in. Therefore, check the right configuration/scope and distinguish “requested,” “selected,” and “packaged into artifact.”

### Step 4: assess impact before removing

A transitive dependency may be an essential piece of its parent library. Removing `tomcat-embed-core` from the servlet web starter without substituting another embedded server can prevent the HTTP server from starting. Removing a logging provider requires verifying that a working logging implementation remains. Removing a Jackson module can alter serialization of corresponding types.

Therefore, identify **the path bringing the library in and its role** before adding an exclusion.

## 7. Version conflicts: symptoms and how to analyze them

Two dependencies can request different versions of the same artifact:

~~~text
bookstore
├── payment-sdk:2.0
│   └── shared-json:3.2
└── inventory-client:1.4
    └── shared-json:2.7
~~~

During normal resolution, Maven/Gradle selects one version for those module coordinates according to its rules. The chosen version might be binary-incompatible with a library compiled against the other version.

### Common symptoms

| Symptom | Possible dependency-related cause | Next check |
|---|---|---|
| `java.lang.NoSuchMethodError` | Code calls a method absent in the loaded library version | Inspect runtime classpath and resolved artifact version containing the method |
| `java.lang.NoClassDefFoundError` | Required class unavailable at runtime or failed initialization | Inspect classpath, scopes, and nested root causes |
| `ClassNotFoundException` | Dynamically requested class could not be found | Find the artifact supplying the class and check runtime classpath |
| `NoSuchFieldError` | Runtime class differs from compile-time expectations | Compare compiled and resolved versions |
| Auto-configuration error after adding a starter | New classes/beans changed auto-configuration conditions | Check starters, dependency tree, beans, and condition report |
| Multiple SLF4J providers/bindings | Multiple logging implementations or providers on classpath | Find all providers and the branches pulling them in |
| Unit tests pass, packaged app fails | Dependency exists only on test or compile classpath | Compare `testRuntimeClasspath` with `runtimeClasspath` |

**Note:** the errors above do not have dependency issues as their sole cause. `NoClassDefFoundError` can also stem from class initialization failures; Spring bean errors can come from configuration or component scanning. The dependency tree is only one part of diagnosis.

### Distinguishing “multiple version requests” from “multiple actual JARs”

Seeing both `shared-json:2.7` and `shared-json:3.2` in a *verbose* report does not necessarily mean two runtime JARs exist: one version may be an omitted request. Conversely, two artifacts with **different coordinates** can still package identically named classes, and a dependency tree alone does not rule out classpath collisions or shading.

To know which version the JVM actually used in a specific error, beyond the resolved tree you may need to inspect the packaged JAR and class-loading source. That is a deeper step after understanding the dependency graph.

## 8. Spring Boot BOM and version management

Spring Boot actively manages a set of compatible dependency versions per framework release via the `spring-boot-dependencies` BOM. Whether the project uses the Maven parent, imports the BOM, or uses Gradle platforms/dependency management determines which version management rules apply.

### Maven: dependencyManagement

Example Maven project importing the BOM when not using the managed parent:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version><!-- your project's Spring Boot version --></version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

In a real POM, `<version>` must be a valid value or property; the comment above merely illustrates where configuration belongs, not a complete copy-pasteable file.

With the BOM imported, a managed dependency can omit its own version:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
~~~

The BOM **manages versions**; it does not automatically place every managed library onto the classpath. A library only appears when a direct dependency or transitive path pulls it in.

### Gradle: platform/BOM and version management mechanisms

One way to use the BOM with Gradle:

~~~groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:VERSION'
    )
    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
~~~

`VERSION` is a placeholder that must be replaced with a version matching your project. If a Spring Boot project already has version management configured via existing plugins/settings, do not stack another mechanism on top without understanding the resolution outcome.

Depending on the setup, Gradle may report a version selected due to a platform/constraint or conflict resolution. Use `dependencyInsight` to see why.

### Why shouldn't you tweak versions randomly?

Suppose you discover `jackson-databind` is on an unexpected version. Setting the latest version on every dependency is not guaranteed to fix errors, because related Jackson modules often must align and an integration library may depend on specific APIs. In Spring Boot, the sensible starting point is checking **dependency management for your exact Spring Boot version**, existing overrides, and any third-party library requesting a different version.

If you must override due to compatibility or a security patch, understand the blast radius and ensure related libraries resolve consistently. In some cases, upgrading Spring Boot or the appropriate starter reduces the overrides you need to maintain.

## 9. How to fix the issue once the cause is found

Not every conflict is fixed with the same action. Choose your approach based on **who owns the dependency**, **why it was pulled in**, and **which version is compatible**.

### 9.1. Prefer aligning dependencies with the Spring Boot version

If two libraries in the Spring ecosystem declare manual versions that differ from what Boot manages, review those declarations first. In a properly managed project, many starters can omit explicit versions inside `dependencies`.

For example, instead of pinning an unnecessary starter version:

~~~xml
<!-- When an appropriate BOM/parent already manages versions -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

### 9.2. Exclude a genuinely unneeded transitive dependency

Maven supports `exclusions` on the dependency introducing the library:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-client</artifactId>
    <version>1.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>unused-logging-adapter</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Gradle supports similar exclusions:

~~~groovy
dependencies {
    implementation('com.example:legacy-client:1.0') {
        exclude group: 'com.example', module: 'unused-logging-adapter'
    }
}
~~~

The coordinates above are fictional examples showing syntax. Exclusions typically apply to **the specified dependency branch**. If another branch also pulls in the same artifact, it can still appear in the dependency tree. Therefore, after adding an exclusion, re-check which paths still request that artifact in the project's resolution output.

Do not exclude a library simply because its name looks unfamiliar. First determine what feature uses it and whether the parent library needs it at runtime.

### 9.3. Manage versions intentionally

In Maven, you can use `dependencyManagement` to pin the version used for an artifact; in Gradle, you can use constraints/platforms or a project-appropriate version management strategy. Only pin a version once you know the libraries requesting it are compatible.

Maven example:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared-json</artifactId>
            <version>3.2</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

In Gradle:

~~~groovy
dependencies {
    constraints {
        implementation('com.example:shared-json:3.2') {
            because 'Need to align version across dependency branches'
        }
    }
}
~~~

**A constraint is not the same as force.** Depending on Gradle and existing constraints, the selected version may still differ from the request. To understand or impose stricter requirements, check specific constraint/`strictly` mechanisms and `dependencyInsight` output. `resolutionStrategy.force` also exists, yet forcing versions can mask incompatibilities and should only be used with clear justification.

### 9.4. Change starters when technology needs genuinely differ

If the project only needs the reactive stack, declaring both servlet and reactive starters can bring in an unintended web stack. Identify the required APIs and runtime, then select the matching starter. Similarly, an application that does not need JPA should not keep `spring-boot-starter-data-jpa` just because it was copied from a template; if using only JDBC, pick a more fitting starter.

This changes **application capabilities**, so do not remove starters merely to shorten the dependency tree.

### 9.5. Update the parent library when the problem originates from its dependency

An outdated SDK may pull in an obsolete transitive library version. Instead of overriding repeatedly, updating the SDK to a version supporting the current stack is sometimes more sustainable. When the SDK does not yet support the newer version, weigh compatibility and scope of changes.

## 10. Practice scenario 1: dependency conflict after adding an SDK

Suppose a Spring Boot application is working normally. After adding `payment-sdk`, calling the payment API throws:

~~~text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.json.JsonUtil.toJson(java.lang.Object)'
~~~

This is a hypothetical error example. We can trace it:

**Step 1 — identify the artifact containing `JsonUtil`.** Based on package names and SDK documentation, identify `com.example:shared-json` as the suspect artifact.

**Step 2 — inspect paths requesting the artifact.** With Maven:

~~~bash
./mvnw dependency:tree -Dincludes=com.example:shared-json -Dverbose
~~~

With Gradle:

~~~bash
./gradlew dependencyInsight --dependency shared-json --configuration runtimeClasspath
~~~

Suppose version resolution reports:

~~~text
payment-sdk:2.0 -> shared-json:3.0 (requested)
legacy-reports:1.1 -> shared-json:1.8 (requested)
runtimeClasspath -> shared-json:1.8 (selected)
~~~

In this hypothetical scenario, the application runs `1.8` at runtime, whereas the SDK was compiled against APIs requiring `3.0`. That *could* explain the missing method error; you still verify which version actually contains the method.

**Step 3 — find why `1.8` was selected.** With Maven, inspect direct dependencies, branch depths, and `dependencyManagement`; with Gradle, read the selection reason and constraints in `dependencyInsight`. Do not apply “Maven picks the nearest” to Gradle.

**Step 4 — choose an appropriate fix.** You might upgrade `legacy-reports`, update the SDK, adjust versions via BOM/constraints, or remove an obsolete branch that is truly unused. Which option fits depends on compatibility of the two libraries and the Spring Boot version. Do not assume “just bump `shared-json` to the highest version” is automatically safe.

**Step 5 — verify the resolution result.** After editing dependency declarations, re-read the exact `runtimeClasspath` tree (or matching Maven tree) to verify the selected version. Testing the failing feature on a real build belongs to verification, separate from merely reading the tree.

## 11. Practice scenario 2: multiple logging providers

A Spring Boot application uses default logging; after adding a third-party SDK, warnings appear regarding multiple SLF4J providers. Multiple implementations/providers present together can cause warnings and unintended logging behavior.

Analyze in Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.slf4j:*,ch.qos.logback:*,org.apache.logging.log4j:*
~~~

In Gradle, you can start with:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Then query each suspect artifact using `dependencyInsight`.

Find the branches pulling providers in, distinguishing:

- **Logging API** (such as SLF4J API) called by code and frameworks.
- **Provider/implementation** used at runtime to write logs.
- **Bridge/adapter** routing calls between logging systems.

Do not exclude a required API just to silence warnings; nor should you delete a bridge without understanding the logging forwarding direction. In Spring Boot, verify which logging setup is active and ensure only the implementation suite matching that setup remains.

## 12. Practice scenario 3: seeing Tomcat even though the project uses WebFlux

Suppose a project declares:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Having both starters puts components from both Spring MVC and WebFlux into the graph. Under Spring Boot's common default auto-configuration rules, when both stacks are present, the servlet/MVC application type generally takes precedence over the reactive web application type unless explicitly configured otherwise. Thus “I added WebFlux” is not enough to conclude the app will run the Netty reactive server.

How to locate Tomcat's source:

~~~bash
./gradlew dependencyInsight --dependency tomcat-embed-core --configuration runtimeClasspath
~~~

Or Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.apache.tomcat.embed:*
~~~

If the output points to `spring-boot-starter-web`, evaluate whether the MVC stack is truly needed. If the application uses only WebFlux, removing the unneeded servlet web dependency may be appropriate, though you must check controllers, filters, clients, and MVC-dependent components before changing starters.

The same dependency tree shows **which components are present** without confirming on its own **which web server Spring Boot chooses at runtime**. To verify runtime behavior, check auto-configuration conditions and startup logs.

## 13. Inspecting packaged artifacts when the tree and runtime seem out of sync

In Spring Boot, packaging plugins can build an **executable JAR** containing libraries in a layout like `BOOT-INF/lib/`, depending on artifact type and build setup.

With the JDK's `jar` command, you can list the contents of a specific JAR:

~~~bash
jar tf build/libs/your-app-name.jar
~~~

For Maven projects, the file may sit under `target/` instead of `build/libs/`. File name and internal layout also depend on build configuration, whether it is an executable JAR, and tool versions.

Example directory layout of a typical executable JAR:

~~~text
BOOT-INF/
├── classes/
│   └── com/example/...
└── lib/
    ├── spring-web-....jar
    ├── spring-webmvc-....jar
    └── ...
~~~

If the dependency tree shows a library present at runtime, yet the deployed build lacks that library, possible explanations include:

- The deployed artifact is an older build or produced with a different configuration.
- You are inspecting a configuration that does not match the application's runtime.
- Packaging has exclusions or custom configuration.
- Running a WAR or an environment where the container supplies dependencies separately.
- The library comes from an external classpath outside the artifact or a different launcher.

Similarly, simply seeing an artifact name in `BOOT-INF/lib` does not prove which class the JVM loaded if multiple classloader sources exist. The dependency tree mainly explains **resolution**, whereas inspecting the JAR verifies **packaging**.

## 14. An effective tree-reading workflow when troubleshooting

When encountering a dependency issue in a Spring Boot project, follow this sequence of questions:

~~~text
Error symptom or unexpected library
                 |
                 v
     Identify suspect artifact
                 |
                 v
   Select right scope / configuration
                 |
                 v
      Display dependency tree
                 |
                 v
   Find all paths pulling artifact in
                 |
                 v
   Identify final resolved version
                 |
                 v
 Find version selection rule / pull source
                 |
                 v
  Fix root dependency, BOM/constraint,
   exclusion, or appropriate version
                 |
                 v
  Re-read tree and verify real artifact
~~~

You can use the table below as a quick tool selector:

| Need to know | Maven | Gradle |
|---|---|---|
| Full dependency tree | `./mvnw dependency:tree` | `./gradlew dependencies --configuration runtimeClasspath` |
| Who pulls an artifact in? | `dependency:tree -Dincludes=group:artifact` | `dependencyInsight --dependency artifact --configuration runtimeClasspath` |
| Which version was selected? | Resolved tree; use verbose if needed | Tree with `->` markers and `dependencyInsight` |
| Why is there a conflict? | Inspect branches, `dependencyManagement`, direct dependencies, nearest definition | Inspect selection reason, constraints, platforms, resolution rules |
| Concerned only with runtime? | `dependency:tree -Dscope=runtime` | `dependencies --configuration runtimeClasspath` |
| Concerned only with tests? | `dependency:tree -Dscope=test` and test context | `dependencies --configuration testRuntimeClasspath` |

Do not explain Maven results using Gradle's version selection rules or vice versa. Both tools resolve module graphs, yet have different models and syntax.

## 15. Common mistakes when reading dependency trees

### “Seeing a dependency name in POM/build.gradle means it is at runtime”

Often false. Scopes like `test`/`provided` or Gradle configurations like `compileOnly` can keep a library out of the application runtime. Exclusions and packaging steps also apply.

### “Seeing two versions in the tree means the JVM loads both at once”

Not necessarily. Output may indicate one version was omitted or a request was resolved to the selected version. Distinguish **requested**, **selected**, and **packaged**.

### “Checking direct dependencies alone is enough”

Insufficient when starters or SDKs pull transitive dependencies. An error in `jackson-databind` can originate from an SDK or starter even when the build file never mentions Jackson directly.

### “Just exclude every unfamiliar library”

Exclusions can strip away classes needed at runtime or break an auto-configuration. An unfamiliar name might be a required dependency of a starter. Understand why it was pulled in and what uses it.

### “Having a BOM means no conflicts can happen”

A BOM helps manage versions, yet explicit versions on direct dependencies, other BOMs, constraints, rules, or libraries outside the BOM can still cause conflicts. A BOM does not prove compatibility with every external SDK.

### “The dependency tree shows everything the JVM loads accurately”

A dependency tree describes build/resolution data for one configuration or scope. Applications running inside app servers, containers, custom launchers, or runtimes with separate classloaders can diverge from build expectations. When needed, inspect both the packaged artifact and launch setup.

### “Every `NoClassDefFoundError` is caused by a missing dependency”

This error sometimes happens because the class was present, yet its static initialization failed earlier. When reading stack traces, inspect the root cause instead of adding dependencies blindly by class name.

## 16. Exercise: finding an unexpected library

Suppose a Spring Boot project using Maven has three direct dependencies:

~~~text
bookstore
├── spring-boot-starter-web
├── document-exporter
└── spring-boot-starter-test (test)
~~~

One day the application discovers `legacy-xml-parser` on the runtime classpath, even though nobody declared it directly in `pom.xml`.

A hypothetical tree output:

~~~text
bookstore
+- spring-boot-starter-web
|  \- ...
+- document-exporter:4.0
|  \- report-engine:2.0
|     \- legacy-xml-parser:1.1
\- spring-boot-starter-test (test)
   \- ...
~~~

You can answer step by step:

1. **Where does the library come from?** From `document-exporter` via `report-engine`.
2. **Does it actually belong to runtime?** In the example yes, though you still verify the project's specific scope and resolved artifact.
3. **Should you exclude it?** Not enough information yet. `report-engine` might use that parser for document exports.
4. **What if you want to replace it?** Check newer versions of `report-engine` or `document-exporter`, configuration supporting another parser, and impact on document export features.
5. **What if it is flagged as a security risk?** Verify the exact version and actual usage, check compatible patched releases; the dependency tree only reveals the dependency path and does not assess risk severity on its own.

After the exercise, try sketching the path yourself:

~~~text
bookstore -> document-exporter -> report-engine -> legacy-xml-parser
~~~

That gives you the evidence needed to talk with the owner of the direct dependency or make an informed build change.

## 17. Useful habits when managing dependencies in Spring Boot

A readable dependency tree usually comes from a few consistent practices:

1. **Use starters that match actual needs.** Starters are convenient entry points, yet pull in whole capability groups. Removing unused starters reduces classpath complexity.
2. **Keep one clear mechanism for version management.** Avoid layering unnecessary overrides atop Spring Boot's BOM or platform.
3. **Declare important libraries directly when your source code uses them.** Do not rely on a class “happening” to appear via another library if your application genuinely depends on that API.
4. **Inspect the right runtime classpath for runtime bugs.** Test dependencies do not explain everything in production.
5. **Find all paths to an artifact before excluding it.** Excluding from one branch may not remove it if another branch still pulls it in.
6. **Do not infer compatibility solely from version numbers.** A higher version can still break an ABI or behavior that another library relies on.
7. **Know the exact artifact being deployed.** Stale builds, build profiles, or packaging configs can cause divergence from the current dependency tree.

Dependency trees are also useful for optimizing build times, spotting unused libraries, analyzing footprint, and building a software bill of materials. However, each goal requires separate evaluation: a library appearing in the tree does not prove the application calls its features.

## Conclusion

Reading dependency trees is a foundational skill when working with **dependencies and starters in Spring Boot**. Always look for **the path bringing the artifact in**, **the selected version**, **the scope/configuration in question**, and **the resolution rule that decided the result**. Maven provides `dependency:tree` and `dependencyManagement`; Gradle provides `dependencies`, `dependencyInsight`, configurations, platforms, and constraints. Both serve the same purpose while resolving conflicts differently.

Once you know “where this library came from and why this version was chosen,” fixing errors becomes an evidence-based decision: swap a starter, update a parent dependency, adjust version management, or remove a genuinely unneeded branch. That turns a long dependency tree into a practical map for understanding and controlling application behavior.
