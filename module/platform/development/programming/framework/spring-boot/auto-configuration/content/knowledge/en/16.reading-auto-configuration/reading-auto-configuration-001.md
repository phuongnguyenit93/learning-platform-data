# Finding the Auto-Configuration Class for a Feature and the Exact Running Version

## 1. Why Must You Find the Exact Class and the Exact Version?

A Spring Boot feature may be provided by an auto-configuration located inside Spring Boot itself, a third-party starter, or an internal library. When you need to understand where a feature is enabled, which conditions create beans, and why behavior differs from documentation, you need to determine:

1. **Which artifact** provides the feature: a starter, an auto-config module, or a core library?
2. **Which auto-configuration class** is responsible for registering beans or related configuration?
3. **Which JAR** on the runtime classpath does that class belong to?
4. **Which version is actually resolved and running**, rather than only looking at the version declared in the build file?
5. In the running version, do the class and conditions still keep the same name/location, or have they been moved, split, or replaced?

Do not start by guessing a class name from the feature name. A feature whose documentation mentions "web", "cache", or "security" may be split across multiple auto-configurations; a starter only pulls dependencies onto the classpath and does not necessarily contain the class that performs configuration.

**Principle:** determine the runtime dependency/version first, find the auto-configuration entry point in the right JAR, then read the source/bytecode and verify with the Condition Evaluation Report or a context test.

## 2. Distinguishing Starters, Auto-Configuration, and Implementation Libraries

A feature is typically separated into these roles:

| Component | Role | Question to Answer |
| --- | --- | --- |
| Starter artifact | Convenience dependency aggregating required dependencies | Which modules has the application pulled onto the runtime classpath? |
| Auto-configuration artifact | Contains auto-configuration classes and discovery metadata | Which classes register beans, and which conditions are evaluated? |
| Core/runtime library | Contains the API and implementation used by beans | Which classes do the created beans use, and where does the behavior live? |
| Configuration metadata | Describes properties for IDE/documentation suggestions | Which configuration keys exist, and what are their types/defaults/deprecations? |
| Spring Boot loader/build plugin | Packages and launches the application | Which artifacts are actually loaded when running the JAR? |

A starter may only have a nearly empty POM declaring dependencies to other modules. Therefore, running a command to list the contents of a starter JAR and not seeing an auto-configuration class **does not prove the feature has no auto-configuration**. You must trace dependencies down to the JAR containing the classes.

Similarly, spring-boot-autoconfigure contains many Spring Boot auto-configurations, but some features are split into separate modules or provided by other projects. Artifact names, class names, and property names do not necessarily match.

## 3. Step 1 — Determine the Actual Spring Boot Version

### 3.1. Maven: Inspect the Dependency Tree

Run from the directory containing pom.xml:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot
~~~

To inspect a specific module and also see dependencies omitted due to conflicts:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework.boot:spring-boot-autoconfigure
~~~

Look for these signs:

- The resolved version in the dependency graph.
- Dependencies whose version was changed by dependency management or a BOM.
- A version omitted due to conflict (Maven may print omitted for conflict).
- Which starter pulls in spring-boot-autoconfigure or a specialized artifact.

You can inspect the effective POM:

~~~bash
mvn help:effective-pom
~~~

The effective POM shows which dependency management, parent, and properties have been applied. However, **the effective POM does not replace the dependency tree**: the tree shows the dependency versions actually resolved in the graph.

If the project uses the Spring Boot parent or BOM, Spring Boot modules are typically managed under the same release line. Do not manually override spring-boot-autoconfigure alone to a version different from spring-boot without a clear reason and compatibility testing.

### 3.2. Gradle: Inspect runtimeClasspath

Run:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

To see which dependency pulls a module in and why a specific version was chosen:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
~~~

On Windows:

~~~powershell
.\gradlew.bat dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
~~~

dependencyInsight is useful when multiple starters request different versions or when a rule/platform forces a version. For multi-project applications, run the task in the exact subproject building the executable; another module's dependency graph does not prove the current application's classpath.

### 3.3. Do Not Confuse the Declared Version with the Runtime Version

For example, pom.xml has a parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
</parent>
~~~

This is the declared parent version. If the project overrides dependencies, uses another BOM, or packages a different artifact, the runtime version needs to be confirmed separately.

You can print the Spring Boot version while the application is running:

~~~java
import org.springframework.boot.SpringBootVersion;

System.out.println("Spring Boot version: "
        + SpringBootVersion.getVersion());
~~~

Place this snippet in main or a runner. In a standard Spring Boot application, SpringBootVersion.getVersion() returns the version of the loaded Spring Boot class. If the result is null in a custom packaging environment, check the manifest/JAR and class origin.

You can inspect the version from the command line or build info, but **the runtime classpath is the primary source of truth** for the classes the JVM actually loads.

## 4. Step 2 — Find the Artifact Providing the Feature

Start from the feature name in documentation, a property, or an observed bean. Find related dependencies:

~~~bash
mvn dependency:tree -Dverbose
~~~

Or with Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Look for these clues:

- A starter named after the feature.
- A module with the autoconfigure suffix.
- A module with the starter suffix.
- The runtime/API library that the bean depends on.
- An official Spring Boot integration module.

Hypothetical example:

~~~text
com.acme:acme-report-starter
  \- com.acme:acme-report-autoconfigure
      \- com.acme:acme-report-core
~~~

In this example, the auto-configuration classes most likely reside in acme-report-autoconfigure, while the API/implementation lives in acme-report-core. This is an **illustrative structure**, not the artifact names of a specific library.

Do not infer a JAR solely from a package name. Check the actual artifacts on the runtime classpath and inspect the JAR contents.

## 5. Step 3 — Find the Auto-Configuration Entry Point in the JAR

### 5.1. Spring Boot 3.x: AutoConfiguration.imports

In Spring Boot 3.x, the standard discovery mechanism for auto-configuration is the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The resource contains the fully qualified names of auto-configuration classes, one class per line. Once you know the candidate JAR, inspect its contents:

~~~bash
jar tf path/to/library-autoconfigure.jar
~~~

Find the imports file:

~~~bash
jar tf path/to/library-autoconfigure.jar | grep AutoConfiguration.imports
~~~

Read the resource content inside the JAR:

~~~bash
unzip -p path/to/library-autoconfigure.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

On Windows PowerShell, if unzip is unavailable, you can use jar to list and then extract the file from the JAR into a temporary directory:

~~~powershell
jar tf path\to\library-autoconfigure.jar
jar xf path\to\library-autoconfigure.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
Get-Content META-INF\spring\org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

When you find the class name, record the **fully qualified class name**, for example:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

Then locate the corresponding class in the JAR:

~~~bash
jar tf path/to/library-autoconfigure.jar | grep ReportsAutoConfiguration
~~~

Do not assume that every line in imports creates beans. This file lists candidates; the class may still use ConditionalOnClass, ConditionalOnProperty, ConditionalOnBean, or other conditions.

### 5.2. Spring Boot 2.x: spring.factories

In Spring Boot 2.x versions, auto-configuration is typically registered via:

~~~text
META-INF/spring.factories
~~~

In this resource, look for the EnableAutoConfiguration key:

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

You can read it with:

~~~bash
unzip -p path/to/library-autoconfigure.jar META-INF/spring.factories
~~~

**Do not mechanically apply Boot 3 lookup steps to Boot 2 or vice versa.** Spring Boot 3 moved auto-configuration discovery to AutoConfiguration.imports; a library compatible with multiple major versions may need to package appropriate metadata for each release line according to the library's documentation.

spring.factories files may still be used for other SPIs/extensions in newer Boot versions; the distinction to remember is that the legacy EnableAutoConfiguration key is no longer Boot 3's standard auto-configuration registration mechanism.

### 5.3. Inspect Supplementary Metadata

Some JARs also include:

- META-INF/spring-autoconfigure-metadata.properties: metadata supporting early auto-configuration filtering in certain Boot versions/mechanisms.
- META-INF/spring-configuration-metadata.json: metadata about properties, types, descriptions, defaults, and deprecations.
- META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports: the Boot 3.x candidate list.

Do not confuse configuration metadata with the auto-configuration list. spring-configuration-metadata.json helps find **property names**; it is not the canonical source for knowing which classes register beans.

## 6. Step 4 — Read the Class and Conditions for the Exact Version

After finding the class name from the JAR, verify the exact artifact/version before looking up source code. A class may have been moved to a different package, renamed, split into multiple classes, or removed in a newer release.

### 6.1. Open Source in the IDE

In IntelliJ IDEA:

1. Open External Libraries or Maven/Gradle dependencies.
2. Select the exact resolved artifact and version.
3. Search for the class by its fully qualified name from AutoConfiguration.imports or spring.factories.
4. Open the source attachment if the IDE has downloaded the sources JAR.
5. If sources are unavailable, view the decompiled bytecode and verify against the actual artifact.

In Eclipse, open Maven Dependencies/Gradle Dependencies, find the JAR with the exact version, and open the class. You can attach the sources JAR to read the original code.

**Do not read source from the GitHub main branch and conclude that it is the running code.** main may have changed after the release, or classes may have moved in newer versions. Open the corresponding tag/commit or the sources JAR for the exact version.

### 6.2. Use a Sources JAR or Decompiler

Maven can download source artifacts:

~~~bash
mvn dependency:sources
~~~

If no sources JAR is available, you can use the IDE's decompiler or javap to inspect basic signatures/annotations:

~~~bash
javap -classpath path/to/library-autoconfigure.jar -p com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

javap helps confirm that the class exists, along with its methods and signatures. It does not present source as readably as a sources JAR and does not explain the full semantics of conditions by itself.

When reading the class, focus on:

- AutoConfiguration or Configuration.
- ConditionalOnClass and ConditionalOnMissingClass.
- ConditionalOnProperty.
- ConditionalOnBean and ConditionalOnMissingBean.
- ConditionalOnWebApplication.
- Import, ImportAutoConfiguration, and nested configurations.
- Bean methods and their return types.
- before, after, beforeName, afterName, or ordering metadata.
- Configuration properties registered via EnableConfigurationProperties.

An auto-configuration class might only import other classes or register properties. The actual beans may reside in nested configurations or methods on imported classes. Follow the reference chain until you reach where the beans are registered.

## 7. Step 5 — Verify the Class Belongs to the Right JAR and Runtime Classpath

When multiple versions of the same library appear together in the dependency graph, having the same class name is not enough. You need to determine where the JVM is loading the class from.

### 7.1. Print the Class Origin Using Java

The following snippet shows the CodeSource of a class:

~~~java
Class<?> type = com.acme.reports.autoconfigure.ReportsAutoConfiguration.class;

System.out.println("Class: " + type.getName());
System.out.println("Origin: "
        + (type.getProtectionDomain().getCodeSource() == null
                ? "unknown"
                : type.getProtectionDomain().getCodeSource().getLocation()));
~~~

Put this snippet in temporary diagnostic code inside the application, using an actual class present in your dependencies. In an executable Spring Boot JAR, nested JARs and classloaders can make the displayed URL look different from a standalone JAR; some custom environments may not provide a CodeSource. Therefore, combine this with the dependency tree and runtime classpath rather than treating a single URL as sole proof.

You can check the class resource:

~~~java
String resource =
        "com/acme/reports/autoconfigure/ReportsAutoConfiguration.class";

System.out.println(type.getClassLoader().getResource(resource));
~~~

The result typically shows the resource URL found by the classloader. If multiple classloaders exist, verify using the exact classloader of the class being used.

### 7.2. Inspect the Packaged JAR

In a Spring Boot executable JAR, dependencies typically live under:

~~~text
BOOT-INF/lib/
~~~

List contents:

~~~bash
jar tf target/my-app.jar
~~~

Find the artifacts and versions, for example:

~~~text
BOOT-INF/lib/spring-boot-autoconfigure-3.3.5.jar
BOOT-INF/lib/acme-report-autoconfigure-1.4.2.jar
~~~

These names are **illustrative examples** only. Cross-check against the actual packaged JAR, because the runtime version may differ from what you assume from the build file.

If you need to inspect a resource inside a nested JAR, extract the executable JAR to a temporary directory first, then open the corresponding inner JAR with jar tf or unzip -p. Do not confuse application resources with resources inside a dependency.

## 8. Step 6 — Verify with the Condition Evaluation Report

Once you have identified the class and version, enable the report:

~~~bash
java -jar target/my-app.jar --debug
~~~

Search for the class name in these sections:

- **Positive matches:** conditions that matched.
- **Negative matches:** conditions that did not match and why.
- **Exclusions:** excluded auto-configurations.
- **Unconditional classes:** configurations without corresponding conditions.

If a class found in the JAR does not appear in the report, check:

1. Does the discovery resource actually contain that class?
2. Is the dependency on the runtime classpath of the right application?
3. Is the auto-configuration excluded?
4. Was the class filtered out prior to evaluation by conditions or metadata?
5. Are you running the exact artifact/JAR/version you just inspected?

If the class appears in the report but a bean method does not match, read the specific condition on that method. If the condition matches yet the bean still fails to be created, inspect the stack trace and initialization errors.

For applications with Actuator, the /actuator/conditions endpoint can expose condition evaluation details over HTTP when the dependency, exposure, and access permissions are configured. This endpoint is a separate tool; --debug does not install Actuator or expose the endpoint automatically.

## 9. Example Workflow for Tracing Auto-Configuration by Feature

Suppose an application uses the cache feature and you need to know which class actually configures caching.

### Step 1: Identify Resolved Dependencies

Maven:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework.boot,com.example
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
~~~

Determine the Spring Boot version and related cache artifacts. Do not assume there is only one JAR: a starter may pull separate auto-config, API, and implementation modules.

### Step 2: Locate the Discovery Resource

For Boot 3.x, open META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports in the relevant JARs. Look for candidates whose names relate to cache.

For Boot 2.x, check the EnableAutoConfiguration key in META-INF/spring.factories of the artifact at the exact version.

### Step 3: Open the Class at the Exact Version

Use the matching sources JAR/tag to read the classes declared in the resource. Look for condition annotations and Bean methods. If a class only imports child configurations, follow through to those child classes.

### Step 4: Enable the Report at Runtime

~~~bash
java -jar target/my-app.jar --debug
~~~

Search for the auto-configuration name in Positive/Negative matches. Compare the conditions against current properties, classpath, and beans.

### Step 5: Confirm Behavior

Use an isolated test or integration test to verify the presence/absence of beans when changing properties and prerequisites. Do not stop at finding the class name: you must prove that the class belongs to the right version and that the conditions actually match at runtime.

## 10. Common Pitfalls When Tracing Classes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Inspected starter JAR and found no auto-configuration class | The starter only declares dependencies | Follow the dependency tree to the auto-config artifact |
| Docs mention a class, but current JAR lacks it | Docs are for another version, or the class was renamed/moved | Check runtime version and corresponding sources JAR/tag |
| AutoConfiguration.imports lacks the expected class | Looking at the wrong JAR or wrong major version | Locate the right artifact; for Boot 2 inspect spring.factories |
| Class is in JAR but missing from report | Not discovered, excluded, or filtered out | Check resource, classpath, exclusions, and conditions |
| Class appears in report, but bean is absent | Condition on the bean method did not match | Read the Negative match for that exact method |
| Dependency tree shows two versions | Conflict or override via BOM/platform | Use dependencyInsight/verbose tree and align versions |
| Source on GitHub differs from decompiler in JAR | Viewing a branch/tag that does not match the release | Use the sources JAR or tag for the exact version |
| Condition matches, but startup fails | Bean initialization failure after condition passed | Read the stack trace, constructor, and factory method |
| Changed dependency version, yet class stays the same | Runtime JAR not updated or running stale artifact | Clean/rebuild/redeploy the right app and verify executable JAR |
| Only read spring-configuration-metadata.json to find classes | That metadata describes properties, not the auto-config list | Check AutoConfiguration.imports or spring.factories by version |

## 11. Pre-Conclusion Checklist

When documenting an investigation of a feature, record complete evidence:

- Running application/module name.
- Actual Spring Boot version (runtime).
- Artifact and version containing the auto-configuration class.
- Discovery resource and the line declaring the class.
- Fully qualified class name and imported child configuration classes.
- Conditions at class and bean method levels.
- Positive/Negative match results when running with the actual configuration.
- Final presence/absence of the bean and verification test.

You can record results using this template:

~~~text
Feature: <feature name>
Spring Boot runtime: <version>
Provider artifact: <group:artifact:version>
Discovery: <AutoConfiguration.imports or spring.factories>
Auto-configuration class: <fully-qualified-class-name>
Bean method: <ConfigurationClass#beanMethod>
Conditions: <relevant conditions>
Runtime report: <Positive/Negative match and reason>
Verification: <test or bean observation in context>
~~~

Do not record a class simply because its name looks right. Verify that the class belongs to the exact artifact version and is processed by discovery/conditions in the actual runtime.

## 12. Self-Check Questions

**Question 1.** Why can't you just open the starter JAR to find auto-configuration classes?  
**Answer:** A starter often only pulls other artifacts into the dependency graph; the classes may reside in a separate autoconfigure module.

**Question 2.** Through which resource does Boot 3.x typically publish auto-configurations?  
**Answer:** META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports. Boot 2.x typically uses the EnableAutoConfiguration key in META-INF/spring.factories.

**Question 3.** Why must you confirm the runtime version instead of only checking the version in pom.xml?  
**Answer:** Dependency management, BOMs, conflict resolution, and overrides can cause the resolved version to differ from initial assumptions.

**Question 4.** If the class exists in the JAR but no bean is created, what is the next step?  
**Answer:** Confirm the class is discovered, check exclusions, and read the Condition Evaluation Report at the bean method level; if the condition matches, check initialization errors.

**Question 5.** What can CodeSource be used for?  
**Answer:** To inspect where a class is loaded from at runtime, then cross-check against the dependency tree and actual JARs. In custom executable JARs, the URL may be non-trivial or unavailable.

**Key takeaway:** To find the right auto-configuration for a feature, follow the chain **runtime version → dependency/artifact → discovery resource → class and conditions → Condition Evaluation Report → bean verification**. Do not rely on guessed class names, main-branch source code, or a declared version alone.
