# Direct Dependencies, Transitive Dependencies, and the Spring Boot Version in Use

## 1. Why understand dependencies before studying auto-configuration?

Spring Boot provides many default configurations based on **which classes are actually on the classpath**. Yet an application's classpath is shaped by both the dependencies a developer declares directly and the dependencies pulled in by other libraries. Therefore, before explaining why an auto-configuration is activated, you must know **which libraries the application is running with and their actual versions**.

A common case: in Gradle, an application declares only **spring-boot-starter-web**, yet it can still use Spring MVC's **DispatcherServlet** and Jackson's **ObjectMapper**. Both classes come from dependencies brought in through the starter, without necessarily being listed directly in build.gradle. If a transitive library is replaced, excluded, or resolved to a different version, **@ConditionalOnClass**, **@ConditionalOnMissingBean**, and auto-configuration behavior can change.

Three questions must be kept distinct:

1. **Which dependencies do I declare?** Inspect the **dependencies** block of build.gradle or equivalent declarations.
2. **Which dependencies does Gradle choose for compilation and runtime?** Inspect the dependency graph of the right configuration, especially **runtimeClasspath** and **dependencyInsight**.
3. **Which Spring Boot version is actually in use?** Distinguish the plugin version, dependency-management BOM, resolved Boot artifacts, and the Boot library version actually present at runtime.

This lesson explains how to answer all three with commands and evidence, helping you read auto-configuration accurately.

## 2. Direct dependencies

A **direct dependency** is a dependency **explicitly declared** by the project in its build configuration. In Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Here the project directly declares two dependencies:

- **spring-boot-starter-web** is an application-code dependency in the **implementation** configuration; it participates in the compile classpath and runtime classpath as defined by the Gradle Java plugin.
- **spring-boot-starter-test** is a dependency used when compiling and running tests; normally it is not packaged as a runtime dependency of the production application.

Key point: a direct dependency **does not mean** a dependency whose code lives inside your own module. The web starter is largely a way to **bundle dependencies and establish library usage conventions**. The starter itself does not perform component scanning or register Spring MVC beans on its own.

A direct dependency also does not necessarily have a version written next to its **group:artifact** coordinates. If the project imports a BOM or uses dependency constraints, the version can be determined by the dependency management mechanism.

### 2.1. Key configurations in Gradle

| Declaration | Purpose | Included in main app runtime by default? |
| --- | --- | --- |
| **implementation** | Libraries needed for main code implementation | Yes, per project dependency resolution. |
| **api** (java-library) | Libraries exposed in the public API of a Java library | Yes; also propagated onto consumers' compile classpaths. |
| **compileOnly** | Needed only at compile time; another environment must provide it at runtime if needed | No. |
| **runtimeOnly** | Needed only at runtime, e.g., a JDBC driver | Yes, though absent from the normal compile classpath. |
| **testImplementation** | Test code, test frameworks, assertion libraries | Not included on the main runtime classpath; used for tests. |
| **testRuntimeOnly** | Components needed only when running tests | Not included on the main runtime classpath. |

The rows above describe **configuration roles**. They do not tell you which artifact is actually selected if conflicts, constraints, or other rules exist. Always inspect the resolution result.

### 2.2. Why is classifying direct dependencies useful?

When you see an import statement in application code, know whether the dependency supplying that API is declared directly or only present incidentally through another library. Relying on a transitive dependency for APIs that your application calls directly can break code when the intermediate library changes its dependencies.

For example, if an application **writes code that directly uses ObjectMapper**, consider declaring a direct dependency on the relevant Jackson artifact or an appropriate starter instead of implicitly relying on an unrelated library to keep pulling Jackson in forever. Conversely, do not turn every transitive dependency into a direct dependency just to make the list look complete; doing so undermines centralized version management.

## 3. Transitive dependencies

A **transitive dependency** is a dependency that appears because **another dependency requires it**. In Gradle, when module A depends on B and B depends on C (and metadata indicates C is needed for that configuration), C can become part of A's dependency graph even though A never declared C.

Simplified diagram for a web application:

~~~text
Demo project
  └─ direct: spring-boot-starter-web
       ├─ transitive: spring-boot-starter
       ├─ transitive: spring-boot-starter-json
       │    └─ transitive: jackson-databind (via dependency graph)
       ├─ transitive: spring-boot-starter-tomcat
       │    └─ transitive: tomcat-embed-core
       ├─ transitive: spring-web
       └─ transitive: spring-webmvc
            └─ transitive: spring-core / Spring Framework components
~~~

This is a **conceptual diagram with branches omitted**. Exact edges and versions must come from metadata and Gradle reports for the specific starter version. Do not treat this diagram as a snapshot of every application's dependency tree.

An artifact can be both a direct dependency and reachable through multiple transitive paths. Gradle **resolves a single set of components per configuration**, rather than downloading a separate JAR for every path in the tree by default.

### 3.1. Transitive dependencies explain why auto-configuration runs

In a Spring Boot application, an auto-configuration may check class presence using a condition like **@ConditionalOnClass**. That class may appear because of a transitive dependency—such as Spring MVC or Jackson brought in by the web starter.

When the class appears, a classpath condition can match. Yet **merely having the class on the classpath is not enough to conclude a bean will be created**: auto-configuration also checks properties, existing beans, application type, and other conditions.

Conversely, if a transitive dependency is excluded, a classpath condition may stop matching. Other libraries might still reference the missing class and trigger compile or runtime errors. Thus **exclusions have effects beyond shrinking the JAR**.

### 3.2. Dependency graph is not class loading sequence

Gradle dependency resolution determines which components/artifacts are needed for a configuration. The classpath is the list of artifacts after resolution. The JVM and Spring then use those classes during startup.

Do not deduce that "a dependency appearing earlier in the tree" means Spring creates its beans first. Bean order depends on Spring's configuration and lifecycle, while auto-configuration ordering has its own mechanism. The dependency graph answers **what is present and which version**; the condition report answers **why a configuration was applied**.

## 4. Declared version, managed version, and selected version

Versioning is more involved than reading a single number in build.gradle. Distinguish three levels:

| Level | Example | What it tells you |
| --- | --- | --- |
| **Requested/declared version** | Directly specifying coordinates with a version, or a plugin version | Version requested at a particular declaration site. |
| **Managed/constraint version** | Version managed by the Spring Boot BOM/platform or constraints | Rules/recommendations/constraints participating in version selection. |
| **Resolved/selected version** | Specific artifact appearing on runtimeClasspath | Version Gradle actually selected for that configuration. |

If a project uses a BOM, you can declare:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

without writing a version on the **implementation** line. Gradle can still resolve the starter and its dependencies thanks to the BOM/management configured in the project.

If an artifact is requested at multiple versions, Gradle performs conflict resolution according to metadata, constraints, and build rules. The result **can differ from the version a reader guesses from a single declaration line**. Common reasons include: a transitive branch requesting a newer version, a constraint enforcing a version, a platform, dependency substitution, or a resolution strategy. Never assume "direct always beats transitive" or "the BOM can never be overridden".

### 4.1. What does the Spring Boot BOM manage?

Spring Boot publishes the **spring-boot-dependencies** BOM with a curated, tested set of versions for many libraries Boot integrates with: Spring Framework, Jackson, logging, embedded servers, and many other technologies. Using a consistent BOM avoids manually matching versions across modules.

In Gradle there are two common approaches:

- The **io.spring.dependency-management** plugin integrated with the Spring Boot Gradle plugin, which can import the BOM matching the Boot plugin version.
- Gradle's native **platform** mechanism, which can import a Maven BOM: **implementation platform('org.springframework.boot:spring-boot-dependencies:...')** or another appropriate configuration. **enforcedPlatform** carries stronger semantics and should be used carefully when publishing libraries.

Do not mix version management mechanisms without understanding precedence and conflict behavior. When using the dependency management plugin, how it applies versions and how native Gradle constraints participate in resolution may behave differently across scenarios. The final verdict must come from **dependencyInsight on the real configuration**.

### 4.2. The phrase "Spring Boot version" can refer to several things

There are at least four related versions with different roles:

1. **Spring Boot Gradle plugin version**, e.g. on the line **id 'org.springframework.boot' version '3.3.13'**. It controls Gradle tasks, bootJar, bootRun, and build integration.
2. **Spring Boot BOM version**, e.g. **org.springframework.boot:spring-boot-dependencies:3.3.13**, managing dependency versions according to its compatibility matrix.
3. **Resolved Spring Boot library version**, e.g. the **spring-boot**, **spring-boot-autoconfigure**, and **spring-boot-starter-web** artifacts on runtimeClasspath.
4. **Spring Boot runtime version** reported by **org.springframework.boot.SpringBootVersion** from the Spring Boot library loaded at runtime.

In a standard project configuration, these core Boot versions are typically **aligned**. However, they are not the same definition, and a customized build or one with conflicts can still end up selecting an inconsistent set of artifacts.

The **Spring Framework version** (e.g. **spring-context**, **spring-core** artifacts) is also **not** the Spring Boot version. Java/JDK and Gradle versions are two more separate versions. Do not answer "which Spring Boot version is the app using?" with "Java 21", "Gradle 8", or a Spring Framework artifact number.

## 5. Runnable Gradle example: exploring Spring Boot's dependency graph

Create a small Java 21 project to verify these ideas. Version **3.3.13** below is **a pinned baseline for the example**, not a claim about the latest version or another project's version. When applying this to a real project, check the actual version instead of copying this baseline blindly.

### 5.1. Structure

~~~text
dependency-lab/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/dependencylab/
    └── DependencyLabApplication.java
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'dependency-lab'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Points to observe:

- Direct runtime dependency: **spring-boot-starter-web**.
- Direct test dependency: **spring-boot-starter-test**.
- Boot Gradle plugin version: **3.3.13**.
- The dependency-management plugin alongside the Boot plugin applies the dependency management table from the matching BOM in standard setups.
- **No version written** directly on the starter-web line. The starter's version is resolved by the management mechanism.
- Java toolchain 21 is the example's JDK choice, not the Spring Boot version.

Code in **src/main/java/com/example/dependencylab/DependencyLabApplication.java**:

~~~java
package com.example.dependencylab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootVersion;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class DependencyLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(DependencyLabApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectClasspath() {
        return args -> {
            ClassLoader loader =
                DependencyLabApplication.class.getClassLoader();

            System.out.println(
                "Spring Boot runtime version: "
                    + SpringBootVersion.getVersion()
            );
            System.out.println(
                "Spring MVC DispatcherServlet available: "
                    + ClassUtils.isPresent(
                        "org.springframework.web.servlet.DispatcherServlet",
                        loader
                    )
            );
            System.out.println(
                "Jackson ObjectMapper available: "
                    + ClassUtils.isPresent(
                        "com.fasterxml.jackson.databind.ObjectMapper",
                        loader
                    )
            );
        };
    }
}
~~~

This is a complete Spring Boot program in the project layout above. **ClassUtils.isPresent** checks whether a class can be loaded via the application's classloader; there is no need to import DispatcherServlet or ObjectMapper in source code. As a result, the example still compiles when we swap starters in the next experiment.

### 5.2. Running the application and reading the output

With Gradle installed and JDK 21 available, from the root directory:

~~~bash
gradle bootRun
~~~

If the project includes the Gradle Wrapper, you can run:

~~~bash
./gradlew bootRun
~~~

On Windows use **.\gradlew.bat bootRun**. When the application starts successfully with the declared dependencies, the lines expected from ApplicationRunner are:

~~~text
Spring Boot runtime version: 3.3.13
Spring MVC DispatcherServlet available: true
Jackson ObjectMapper available: true
~~~

These may appear amid startup logs; this is **not the entire Gradle stdout**. In this aligned-version example, runtime version prints **3.3.13**. If a project overrides dependencies, the result may differ; if library package metadata is stripped in unusual packaging environments, **SpringBootVersion.getVersion()** might not return the expected version string. Always cross-check the dependency graph as well.

### 5.3. Inspecting all runtime dependencies

At the root:

~~~bash
gradle dependencies --configuration runtimeClasspath
~~~

When using the Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

This command outputs the dependency tree for **runtimeClasspath**. With the web starter, trace branches down to **spring-webmvc**, **spring-boot-autoconfigure**, **jackson-databind**, and the corresponding embedded server. Do not memorize an entire tree from a single example since versions and metadata can change.

Read the report like this:

~~~text
dependency-lab
 └─ spring-boot-starter-web      (direct)
      ├─ ... Spring MVC          (transitive)
      ├─ ... JSON/Jackson        (transitive)
      └─ ... embedded server     (transitive)
~~~

In real Gradle output, you may see **->** (requested version resolved to a different version), **(*)** (a branch already rendered earlier), and **(c)** (dependency constraint, depending on version/report format). These are signals to read further, not default error messages.

### 5.4. Tracing a single artifact with dependencyInsight

The full tree can be long. When you only want to know "Where does Jackson come from and which version did Gradle pick?", run:

~~~bash
gradle dependencyInsight \
  --configuration runtimeClasspath \
  --dependency jackson-databind
~~~

In PowerShell, you can write it on one line:

~~~powershell
gradle dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
~~~

This command helps answer:

- **Which version was selected?**
- **Which dependency paths lead to that module?**
- **Does the requested version differ from the selected version?**
- **Was selection affected by conflicts, constraints, or rules?**

Continue inspecting the core Spring Boot libraries:

~~~bash
gradle dependencyInsight --configuration runtimeClasspath --dependency org.springframework.boot:spring-boot
gradle dependencyInsight --configuration runtimeClasspath --dependency org.springframework.boot:spring-boot-autoconfigure
gradle dependencyInsight --configuration runtimeClasspath --dependency org.springframework.boot:spring-boot-starter-web
~~~

If the project has multiple Gradle subprojects, invoke the task on the **exact application module**. For example: **gradle :api-service:dependencyInsight --configuration runtimeClasspath --dependency jackson-databind**. Results from the root or a library module do not necessarily match the runtime graph of the running service.

### 5.5. Comparing compileClasspath and runtimeClasspath

Run:

~~~bash
gradle dependencies --configuration compileClasspath
gradle dependencies --configuration runtimeClasspath
gradle dependencies --configuration testRuntimeClasspath
~~~

The goal is to recognize three graphs with distinct scopes. **testRuntimeClasspath** may contain JUnit/AssertJ or other test libraries that the production application does not use. Conversely, **runtimeOnly** dependencies appear only at runtime. Do not treat a dependency in testRuntimeClasspath as proof that production auto-configuration will see that class.

When using an executable JAR, inspect the **final packaged artifact**, as packaging/deployment can introduce differences compared to reading build.gradle alone. build.gradle and source code are not the sole sources of truth about the runtime classpath.

## 6. Experiment: changing one direct dependency to see transitive dependencies

In **build.gradle**, change:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
~~~

to:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter'
~~~

Keep **DependencyLabApplication** unchanged. Run again:

~~~bash
gradle bootRun
~~~

According to the example baseline's default dependency graph, the application no longer has Spring MVC and Jackson pulled in by the web starter. Expected classpath check lines:

~~~text
Spring Boot runtime version: 3.3.13
Spring MVC DispatcherServlet available: false
Jackson ObjectMapper available: false
~~~

**Explanation:** The core starter still provides what a basic Boot application needs, yet does not pull in all web/JSON libraries. The application can run as a non-web application and exit after ApplicationRunner completes. Before concluding about Jackson or MVC in another project, check whether any **other** dependency still brings them onto the classpath.

After swapping the starter, run again:

~~~bash
gradle dependencies --configuration runtimeClasspath
gradle dependencyInsight --configuration runtimeClasspath --dependency spring-webmvc
gradle dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
~~~

If the artifact is no longer present in the configuration, dependencyInsight will show no selected dependency path for that artifact. Comparing before/after gives direct evidence of transitive dependency impact.

### 6.1. Adding a direct dependency to test a separate condition

Starting from the state with only **spring-boot-starter**, update to:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'com.fasterxml.jackson.core:jackson-databind'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is a **full replacement snippet for the dependencies block** in the example. Re-running, we expect **Jackson ObjectMapper available: true**, while **Spring MVC DispatcherServlet available: false**, assuming no other dependency brings MVC in. Jackson is now a **direct** dependency of the project rather than appearing solely via the web starter.

A class being present can satisfy a certain **@ConditionalOnClass** condition. However, Jackson's class presence **does not guarantee the application needs or will automatically create MVC/HTTP beans**. Other conditions and the application type continue to govern what gets configured.

After the experiment, restore the original dependencies block to continue verification commands in the standard web state.

## 7. How do you accurately determine the Spring Boot version in use?

No single command answers every case completely. Combine **build declarations**, **resolved runtime dependencies**, and **runtime evidence**.

### Step 1 — Read version management locations

In Gradle, inspect:

- The **org.springframework.boot** plugin and version applied to the module.
- The **io.spring.dependency-management** plugin, BOM imports, or **platform**/**enforcedPlatform**.
- Any versions, constraints, **resolutionStrategy**, version catalogs, convention plugins, and dependency substitutions used by the project.
- In multi-module builds, declaring the plugin at the root with **apply false** is not necessarily where the BOM/runtime version is applied to each subproject.

With Maven, equivalents are **spring-boot-starter-parent**, **dependencyManagement** BOM imports, direct dependencies, and overrides. A parent or BOM describes version management, yet does not replace checking the dependency tree when conflicts are suspected.

### Step 2 — Inspect versions of resolved Boot artifacts

Run in the right module:

~~~bash
gradle dependencyInsight --configuration runtimeClasspath --dependency org.springframework.boot:spring-boot
gradle dependencyInsight --configuration runtimeClasspath --dependency org.springframework.boot:spring-boot-autoconfigure
~~~

To answer "which version does runtime actually have?", the version selected on **runtimeClasspath** is more authoritative than just reading the version in the plugin block. If core Spring Boot artifacts resolve to differing versions, treat that as a warning sign to investigate rather than assuming everything is compatible.

### Step 3 — Check the running application

In Java code you can use:

~~~java
String runtimeVersion = org.springframework.boot.SpringBootVersion.getVersion();
System.out.println("Spring Boot runtime version: " + runtimeVersion);
~~~

This is an **illustrative Java snippet**, run inside an application with the Spring Boot dependency. It reads the version info of the Boot library the JVM is running—distinct from reading build file declarations. It is helpful for runtime verification, though in unusual manifest/package-metadata setups it may not yield a reliable string. Cross-check against resolved artifacts and the actually deployed artifact.

Applications also commonly show the Boot version in startup logs/banners, yet logs can be disabled, banners replaced, or output customized. **Do not rely solely on the banner string** when investigating conflicts.

### Step 4 — Inspect the deployed artifact

For the example project:

~~~bash
gradle bootJar
jar tf build/libs/dependency-lab-0.0.1-SNAPSHOT.jar
~~~

In a standard executable Spring Boot JAR, runtime libraries normally appear under **BOOT-INF/lib/**, e.g. entries like **spring-boot-...jar**, **spring-boot-autoconfigure-...jar**, and other dependencies. Inspect the filenames to see which artifacts were actually packaged into the release. Exact output layout depends on packaging mode and customizations; layered JARs still generally contain library entries. If deploying via Docker images, WARs, or external containers, inspect the classpath/artifacts of **the actually deployed environment** rather than inferring from an old local build JAR.

**Never assume the JAR just built is the JAR running in production.** The current build, release artifact, and running container may have been produced at different times.

### Step 5 — Compare and record evidence

Recommended checklist:

| Evidence | Verification source | Example for illustrative project |
| --- | --- | --- |
| Boot Gradle plugin | plugins block / plugin resolution | 3.3.13 |
| Managing BOM | dependency management/BOM/platform | spring-boot-dependencies:3.3.13 |
| Selected Spring Boot libraries | runtimeClasspath dependencyInsight | Target alignment 3.3.13 |
| Spring Boot runtime library | SpringBootVersion.getVersion() | 3.3.13 with standard library metadata |
| Spring Framework / Jackson / Tomcat | dependencyInsight for those artifacts | Depends on BOM, graph, and overrides |
| Executing JDK | java -version and runtime environment | Do not infer solely from Spring Boot version |

"The application uses Spring Boot 3.3.13" is a valid conclusion **after** verifying that the Boot plugin/BOM and core libraries actually resolve to that version, not merely from seeing a version string in the root project.

## 8. Dependency conflicts: why does the selected version differ from the requested version?

Suppose one library requests one version of Jackson while another requests a different version. Gradle resolves them according to the rules and metadata active on the configuration. For dependency paths with conflicts, the dependencies report can display version transitions with **->**; **dependencyInsight** shows the selected component and why it was chosen.

Factors to distinguish:

- **Version constraint / platform:** conveys allowed, preferred, or strictly enforced versions depending on how it is declared.
- **Transitive request:** adds version requests from downstream dependencies.
- **Dependency substitution:** replaces one module with another module or project when build rules specify it.
- **Resolution strategy:** can force/select a specific version, yet requires a clear justification.
- **Dependency lock:** if the project enables locking, lockfiles help keep the resolved graph stable within locked configurations.

There is no universal rule that "highest version is always best". Gradle has default conflict resolution, yet constraints, strict versions, and rules can alter the outcome; a newer version is not guaranteed to be compatible with the current Spring Boot/BOM. Any override must be tested for binary compatibility and runtime behavior.

### 8.1. An override example to read carefully

Suppose a build imports the Boot BOM yet someone adds:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}
~~~

This example illustrates a **direct requested version** for Jackson, not a recommendation to apply this override across every Boot release. The version selected after resolution **may** depend on the BOM/constraints, other dependencies, and specific rules. Do not conclude from the declaration line alone that version 2.17.2 is definitely present at runtime.

After making the edit, run:

~~~bash
gradle dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
gradle dependencies --configuration runtimeClasspath
~~~

Verify the **selected version** and compare it with Boot's managed version set. If an override is for a security patch, evaluate compatibility across related Jackson artifacts as well, not just a single artifact.

### 8.2. When should you exclude a transitive dependency?

**Exclude** is appropriate when evidence shows a library pulls in an unneeded dependency, causes a conflict, or requires an intentional alternative implementation. Syntax example:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
}
~~~

This snippet only illustrates how to exclude the Tomcat starter. A **Servlet** application needs an appropriate web server/container to run; if you remove Tomcat without providing an alternative or running inside a suitable container, the application may not work as expected. Do not copy this exclusion to "optimize dependencies" without a clear goal and tests.

Remember: a dependency can enter via **multiple paths**. Excluding it on one branch does not guarantee the artifact disappears from the graph if another branch still pulls it in. Verify with dependencyInsight and runtime checks.

## 9. Direct connection to Spring Boot auto-configuration

Spring Boot auto-configuration evaluates the classpath **after build/dependency resolution has produced the runtime environment**. The two layers operate differently yet are tightly coupled:

~~~text
build.gradle / BOM / constraints
             |
             v
Gradle resolves dependency graph
             |
             v
Actual runtimeClasspath
             |
             v
Spring Boot scans/imports candidate auto-configurations
             |
             v
@ConditionalOnClass, @ConditionalOnBean,
@ConditionalOnProperty, web app type, ...
             |
             v
Bean created or configuration skipped
~~~

What looks like "Spring Boot isn't auto-configuring" can originate at the dependency layer:

**Example A — missing class:** An auto-configuration requires class X, yet the dependency containing X is absent from runtimeClasspath. The classpath condition fails to match, so the configuration is skipped.

**Example B — class present, wrong version:** A class with the right name exists, yet a different library version has an incompatible API. A condition checking only class presence **does not guarantee binary compatibility of every API**. The app may fail when loading classes, instantiating beans, or invoking methods.

**Example C — class from test:** The class appears in testRuntimeClasspath yet is absent from the main application's runtimeClasspath. Tests can run with a different classpath than production. Check the right configuration.

**Example D — dependency present, yet still no bean:** Another condition fails to match, such as a disabled property, a user-defined bean causing **@ConditionalOnMissingBean** to back off, or an incompatible web application type. DependencyInsight cannot substitute for the condition report.

**Example E — mixed stacks from starters:** An application bringing in Spring MVC alongside Reactive components can alter how Boot determines the application type. Do not inspect a single starter in isolation and guess the entire runtime; check the full classpath, web application type settings, and actual conditions.

### 9.1. Ordered diagnostic methodology

When a bean that should be auto-configured is missing:

1. **Confirm the right application module and configuration:** read **runtimeClasspath**, not testClasspath or the root build's tree by mistake.
2. **Trace the dependency:** identify which artifact provides the required class; use **dependencyInsight** to see its version and paths.
3. **Check the selected Boot version:** verify **spring-boot** and **spring-boot-autoconfigure**, then check versions of related libraries.
4. **Read the Condition Evaluation Report:** enable **--debug** on launch, or use the Actuator conditions endpoint when safely configured for access.
5. **Inspect beans and properties:** check which beans the user declared, which properties override defaults, and which profiles are active.
6. **Apply the minimal fix and re-verify:** after every dependency change, run build/tests and compare the graph and condition report.

Avoid solving everything by adding manual dependencies, enabling bean overriding, or excluding transitives wholesale. Such changes can mask real errors.

## 10. Common misconceptions

**"build.gradle shows only one dependency, so runtime has only one JAR."** False. A direct dependency can pull in many transitive dependencies. Count JARs from runtimeClasspath, not lines in the implementation block.

**"A starter is auto-configuration."** False. Starters typically aggregate dependencies. Auto-configuration consists of conditional configuration classes discovered/imported by Spring Boot from appropriate resources.

**"Omitting a version in implementation means Gradle always fetches the latest release."** False. Versions can be governed by a BOM, constraints, or resolution rules; it does not default to upgrading to the newest release on the Internet.

**"The Boot plugin version line proves all Boot runtime dependencies share that version."** Insufficient. The plugin, BOM, and resolved Boot libraries can be managed differently. Read runtimeClasspath and runtime evidence.

**"Direct dependencies always beat transitive dependencies."** Not a universal rule. Selection depends on resolution mechanics and specific constraints.

**"A library only in test scope is also auto-configured by Boot in production."** False. Test classpath and main runtime classpath differ.

**"Keeping every newer transitive dependency is always safe."** Not necessarily. A dependency might be unnecessary or cause conflicts; yet removals must be backed by classpath/compatibility evidence.

**"Adding @ConditionalOnClass guarantees an integration is compatible."** False. Class presence does not prove API or behavioral compatibility across versions.

**"An empty dependencyInsight means the class cannot exist."** Not necessarily. You might be inspecting the wrong configuration, wrong artifact name, or the class might come from another artifact/shading. Verify the actual classpath.

**"Startup logs are the only proof of Spring Boot version."** Advisable not to rely on them alone. Banners can be customized or disabled; verify with both resolved dependencies and runtime library info.

## 11. Self-check practical exercises

### Exercise 1 — Trace Jackson's path

In the project using the web starter, run:

~~~bash
gradle dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
~~~

Record which **direct dependency** creates the path to Jackson, the selected version, and the selection reason. Then check whether Jackson is declared directly in build.gradle. Your answer must be based on the actual graph, not on assuming every starter has the same dependency tree across versions.

### Exercise 2 — Compare two classpaths

Run:

~~~bash
gradle dependencies --configuration runtimeClasspath
gradle dependencies --configuration testRuntimeClasspath
~~~

Find at least two test libraries present only on testRuntimeClasspath. Explain why test classpath results do not prove production has the same classes.

### Exercise 3 — Verify runtime version

Use **SpringBootVersion.getVersion()** in the example. Compare it with the plugin version and the **org.springframework.boot:spring-boot** artifact selected via dependencyInsight. If the three values do not match, trace the cause across the BOM, overrides, dependency conflicts, or the artifact actually running.

### Exercise 4 — Predict before swapping starters

Predict the boolean values for **DispatcherServlet** and **ObjectMapper** after replacing starter-web with starter. Re-run and compare against runtimeClasspath. If the result differs from your prediction, find which dependency supplied the class.

### Exercise 5 — Find why a bean is absent

Suppose a service lacks an expected Jackson bean. Split the investigation into two halves: **does the dependency graph contain ObjectMapper?** and **does the condition report show Jackson auto-configuration matched?** Answer both questions before deciding to write a custom bean.

## 12. Completion checklist

- [ ] Can distinguish direct dependencies from transitive dependencies using examples from runtimeClasspath.
- [ ] Know the primary roles of implementation, api, runtimeOnly, compileOnly, and testImplementation.
- [ ] Can explain why the web starter brings Spring MVC/Jackson into the project even when build.gradle does not list each artifact directly.
- [ ] Can use **dependencies** and **dependencyInsight** to confirm dependency paths and selected versions.
- [ ] Can distinguish the Boot Gradle plugin version, BOM, resolved Boot artifacts, and runtime SpringBootVersion.
- [ ] Do not confuse Spring Framework version, JDK version, or Gradle version with Spring Boot version.
- [ ] Can inspect BOOT-INF/lib inside an executable JAR when verifying packaged artifacts.
- [ ] Can predict and verify classpath changes when swapping direct dependencies.
- [ ] Can explain why the classpath can cause an auto-configuration condition to match or fail to match.
- [ ] Know how to combine dependencyInsight with the Condition Evaluation Report when diagnosing a missing bean.

## Conclusion

**Direct dependencies** are what the application declares. **Transitive dependencies** are what other dependencies pull in. The **actual version in use** is determined by dependency resolution of the right runtimeClasspath and the artifacts the application actually loads or packages, not merely by a version number written in build.gradle.

For Spring Boot auto-configuration, understanding the dependency graph is foundational: the classpath partly determines which conditions can be satisfied; the condition report explains why beans were or were not created. Mastering both sources of evidence lets you diagnose configuration quickly, avoid guesswork dependency edits, and keep Boot applications consistent across library upgrades.
