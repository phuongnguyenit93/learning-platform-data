# Diagnosing Task Graph, Maven Execution, and Overridden Plugin Configuration Errors

## 1. Goal Under the Troubleshooting Group

A short Maven command such as `mvn clean verify` can trigger multiple lifecycle phases, plugin goals, executions inherited from a parent POM, executions inside profiles, and settings pulled from Maven settings. When a build fails, reading only the current module's `pom.xml` is often insufficient to explain why a plugin ran twice, did not run, used the wrong version, or received a value different from the configuration you just edited.

This lesson focuses on three failure groups:

1. **Task graph / execution plan:** which phases and plugin goals does Maven run, in what order, which goals are bound to the lifecycle, and which are invoked directly?
2. **Maven execution:** under which execution ID does a goal run, where is it triggered from, does it run across multiple phases, and is it invoked again by a forked lifecycle?
3. **Overridden or merged plugin configuration:** does configuration come from the Super POM, parent POM, `pluginManagement`, `build/plugins`, profiles, child POM, or command line; does the execution ID match to override the intended execution or create a brand-new execution?

The goal is to build a repeatable diagnostic workflow for the Spring Boot Maven Plugin, Maven Compiler, Surefire/Failsafe, JAR/WAR plugins, and other build plugins.

### Learning Outcomes

After this lesson, you will be able to:

- Distinguish Maven lifecycle, phase, plugin, goal, execution ID, and execution plan.
- Read the execution order of the `clean`, `default`, and `site` lifecycles.
- Determine whether a plugin goal is bound automatically by packaging or added in the POM.
- Use `help:effective-pom`, `help:active-profiles`, `help:effective-settings`, and `help:describe` to find the actual configuration.
- Distinguish `pluginManagement` from `build/plugins` and understand execution merging rules by ID.
- Detect why Spring Boot `repackage` runs twice or fails to run.
- Choose properly between `build-image` and `build-image-no-fork`.
- Diagnose profiles, versions, skip flags, reactor behavior, plugin repositories, and JDK mismatches.
- Create a minimal reproducer, fix the right configuration source, and add CI quality gates.

**Scope:** Maven 3.x/4.x and Spring Boot Maven Plugin **4.1.2**. Examples focus on Maven; Maven's phase/goal/execution concepts should not be confused with Gradle's task graph.

## 2. Execution Model: lifecycle → phase → plugin goal → execution

Maven has three built-in lifecycles:

| Lifecycle | Purpose | Example Phases |
| --- | --- | --- |
| `clean` | Delete outputs from the previous build | `pre-clean`, `clean`, `post-clean` |
| `default` | Validate, compile, test, package, verify, install, deploy | `validate`, `compile`, `package`, `verify`, `install`, `deploy` |
| `site` | Generate and publish project documentation | `pre-site`, `site`, `post-site`, `site-deploy` |

A **phase** is a milestone in a lifecycle. A **plugin goal** is a specific task performing work. A goal may be bound by default via packaging, bound via `<executions>` in the POM, declare a default phase in the plugin, or run only when invoked directly.

For example, with `jar` packaging, Maven has these common bindings:

| Phase | Default Goal |
| --- | --- |
| `process-resources` | `resources:resources` |
| `compile` | `compiler:compile` |
| `process-test-resources` | `resources:testResources` |
| `test-compile` | `compiler:testCompile` |
| `test` | `surefire:test` |
| `package` | `jar:jar` |
| `install` | `install:install` |
| `deploy` | `deploy:deploy` |

The Spring Boot Maven Plugin can add `spring-boot:repackage` to `package` via the parent POM or an execution in the POM. Thus, the `package` phase can execute multiple goals at the same milestone.

### 2.1. How Are Maven Commands Interpreted?

~~~bash
mvn clean verify
~~~

Maven runs the `clean` lifecycle up to the `clean` phase, then runs the `default` lifecycle from the beginning up to the `verify` phase, including preceding phases such as validate, compile, test, and package.

The following command means something different:

~~~bash
mvn verify clean
~~~

Phases execute in the order they appear on the command line: `verify` first, then `clean`. The final state can trick you into thinking no package was produced because `clean` deleted outputs after `verify`.

**Standard habit:** use `mvn clean verify` for a clean build; use `mvn verify` for quick iterations when wiping outputs is unnecessary.

### 2.2. A Phase Is Not a Goal

~~~bash
mvn package
~~~

`package` is a phase. Maven runs all preceding phases of the default lifecycle and the goals bound to those phases.

~~~bash
mvn spring-boot:repackage
~~~

`spring-boot:repackage` is a plugin goal invoked directly. This goal requires a source archive already produced by the `package` phase. If run standalone in a clean workspace, it may report that no JAR/WAR was found.

~~~bash
mvn package spring-boot:repackage
~~~

This command runs the `package` phase first and then invokes the goal directly. However, if the parent POM already bound `repackage` to the `package` phase, the goal may run a second time. Do not use this as a default command before checking the effective POM.

### 2.3. Why Can a Goal Run Multiple Times?

A plugin can have multiple executions: the same goal in multiple phases; multiple executions with different IDs bound to one phase; an execution inherited from the parent plus a new execution in the child; a lifecycle-bound goal also invoked directly; or a goal forking a lifecycle and indirectly triggering other goals.

Seeing two log lines with the same plugin name does not automatically mean Maven has a bug. Read the **execution ID, phase, and configuration source** of each run.

## 3. Reading the Execution Plan and Maven Logs

Maven does not use a Gradle-style task graph. To understand what a build is running, combine the effective POM with debug logs and plugin execution details.

### 3.1. Controlled Debug Execution

~~~bash
mvn -X -e -B -ntp clean verify
~~~

- `-X` enables debug logging, showing the Maven project/session, plugin resolution, and mojo execution details.
- `-e` prints exception stack traces.
- `-B` enables batch mode, suitable for CI.
- `-ntp` suppresses transfer progress so logs are easier to read.

In debug output, look for lines like:

~~~text
[DEBUG] Tasks:   [clean, verify]
[INFO] --- maven-clean-plugin:...:clean (...) @ catalog-service ---
[INFO] --- maven-resources-plugin:...:resources (...) @ catalog-service ---
[INFO] --- maven-compiler-plugin:...:compile (...) @ catalog-service ---
[INFO] --- spring-boot-maven-plugin:4.1.2:repackage (repackage) @ catalog-service ---
~~~

This is an **illustrative example**; formatting and line counts vary by Maven/plugin version. The line `--- groupId:artifactId:version:goal (execution-id) @ project ---` identifies the goal, execution ID, and module being built.

When suspecting a missing or duplicate goal, record the command line, Maven/Java versions, project/module, phases, bound goals, execution IDs, active profiles, direct/forked goals, and the first error. Do not read only the last 30 lines of the log; the root error usually appears before the `BUILD FAILURE` line.

### 3.2. Enable Logging for a Specific Module

~~~bash
mvn -pl :catalog-service -am -X -e -B -ntp verify
~~~

`-pl :catalog-service` selects the module by artifactId. `-am` also builds modules that the selected module depends on in the reactor. Omitting `-am` can fail if dependencies have not been installed in the local repository yet.

### 3.3. Distinguishing Plugin Invocations

For example, the log shows:

~~~text
spring-boot-maven-plugin:4.1.2:repackage (repackage)
spring-boot-maven-plugin:4.1.2:build-image (default-cli)
~~~

These are two different goals. One packages the executable JAR and the other builds an OCI image, which can be intended behavior. Distinguish goal, execution ID, and phase before concluding a duplicate execution occurred.

## 4. Four Most Important Help Plugin Commands

### 4.1. View the Effective POM

~~~bash
mvn help:effective-pom -Dverbose -Doutput=target/effective-pom.xml
~~~

The effective POM is the result after Maven processes the Super POM, parent inheritance, property interpolation, plugin management/declarations, active profiles, and Maven model merging rules.

`-Dverbose` requests comments indicating the origin of elements where supported. Open `target/effective-pom.xml` and inspect plugin coordinates, versions, executions, phases, goals, configurations, and skips.

**Effective POM is not an execution log.** It shows the merged Maven configuration; to know whether a goal actually ran, cross-check debug output.

### 4.2. View Active Profiles

~~~bash
mvn help:active-profiles
mvn help:all-profiles
~~~

The first command reports which profiles are active and their activation source such as POM, user settings, or global settings. The second lists available profiles.

~~~bash
mvn -Pdev,container clean verify
~~~

Profiles can activate by JDK, OS, property, or file existence. A local machine and CI can activate different profiles despite identical command lines.

### 4.3. View Effective Settings

~~~bash
mvn help:effective-settings -Doutput=target/effective-settings.xml
~~~

Settings can affect local repository paths, mirrors, repositories, plugin repositories, active settings profiles, proxies, and server credentials.

**Security:** effective settings may contain sensitive information. Never upload the raw file to public tickets/chats; redact server credentials, tokens, internal URLs, and proxy secrets.

### 4.4. Inspect Plugin Goals and Parameters

~~~bash
mvn help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin:4.1.2 -Dgoal=repackage -Ddetail
~~~

Run similar commands for `build-image` or other plugins. Output confirms goals, parameter names/types/defaults, and user properties if supported by the goal.

Do not guess property names from XML parameter names. A plugin may map `skip` to user property `spring-boot.build-image.skip`; user property names do not always match XML element names.

## 5. Maven Configuration Sources: Which One Wins?

When a plugin receives an unexpected value, inspect the sources Maven merged:

~~~text
Super POM
   |
Parent POM chain
   |
pluginManagement + build/plugins
   |
Active profiles (POM / settings / global settings)
   |
Child module POM and its active profile effects
   |
Command-line properties and plugin-supported user properties
   |
Effective plugin configuration for this execution
~~~

This is a conceptual diagram, not an absolute override order for every parameter. Maven applies model merge rules and property interpolation; specific parameters also depend on the plugin and user properties declared by the mojo. **Effective POM + `help:active-profiles` + debug logs** form the basis for determining the final value.

### 5.1. Parent POM

A parent can declare plugin versions, configurations, and executions. When a plugin/execution is inherited, a child module receives behavior without seeing all of that configuration in the module's own POM.

Check parent coordinates/version, whether the parent resolves via `relativePath` or a repository, intermediate corporate parents, execution IDs, and `inherited=false`.

### 5.2. `pluginManagement` vs. `build/plugins`

| Location | Role |
| --- | --- |
| `build/pluginManagement/plugins` | Manages versions/default configuration for a plugin when that plugin is declared for use |
| `build/plugins` | Declares plugins used in the build; executions here can bind goals to the lifecycle |

Parent POM example:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration><release>17</release></configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Child POM declares the plugin to activate the managed configuration:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

If a plugin appears only in `pluginManagement` without a declaration under `build/plugins` (or another packaging/configuration activating it), do not expect it to run as an additional execution.

### 5.3. Profiles

Profiles can be defined in the project POM, user settings `~/.m2/settings.xml`, or global Maven settings `${maven.home}/conf/settings.xml`. Profiles can activate via explicit `-Pprofile-id`, JDK version, OS, system/CLI properties, packaging, or file presence/absence.

Profile definitions are not inherited verbatim as a raw block into child POMs; **the effects of active profiles**, such as plugins/configurations injected into the effective model, can affect child modules.

### 5.4. Command-Line Properties

~~~bash
mvn -Dspring-boot.build-image.skip=true verify
~~~

This works only if the goal/parameter actually declares that user property. Verify with `help:describe` or documentation for the exact plugin version.

Do not assume `mvn -Dskip=true verify` skips every plugin. Property `skip` may belong to one plugin while having zero effect on another; many plugins use their own property names.

## 6. Rules for Merging Executions by ID

Maven merges plugin executions by ID:

- **Same execution ID** in parent and child: the child's configuration merges/overrides per model merge rules for that execution.
- **Different execution IDs:** both executions are preserved separately and can both run.
- **Multiple execution IDs in the same POM:** can run multiple times, each with its own phase/configuration.
- Profiles can also add or alter plugin executions.

Example where parent has:

~~~xml
<plugin>
    <groupId>org.example</groupId>
    <artifactId>demo-plugin</artifactId>
    <version>1.0.0</version>
    <executions>
        <execution>
            <id>generate-report</id>
            <phase>prepare-package</phase>
            <goals><goal>report</goal></goals>
            <configuration><format>json</format></configuration>
        </execution>
    </executions>
</plugin>
~~~

Child wants to change `format` for that exact execution:

~~~xml
<plugin>
    <groupId>org.example</groupId>
    <artifactId>demo-plugin</artifactId>
    <executions>
        <execution>
            <id>generate-report</id>
            <configuration><format>xml</format></configuration>
        </execution>
    </executions>
</plugin>
~~~

Matching ID `generate-report` lets the child customize the inherited execution. If the child uses a different ID, e.g., `generate-report-xml`, Maven can keep both executions and run both JSON and XML.

### 6.1. Wrong ID Creates a Duplicate Execution

Suppose the parent defines ID `repackage`, and the child adds:

~~~xml
<execution>
    <id>custom-repackage</id>
    <goals><goal>repackage</goal></goals>
</execution>
~~~

The child keeps the parent's `repackage` execution and adds `custom-repackage`. Both can run during the lifecycle, causing repackage log entries to appear twice, artifacts to be overwritten/attached unexpectedly, or different classifiers to be produced.

### 6.2. Matching ID Does Not Replace Every XML Element Wholesale

Maven merges XML configuration according to model rules. Certain child elements merge with the parent; list/collection configs may require merge control. When you genuinely need to replace an entire configuration tree, Maven supports attributes like `combine.self="override"` and `combine.children="append"` in certain positions.

**Do not use these attributes as guesswork fixes.** Inspect the effective POM first; use them only when you understand the configuration structure and intentionally want to change that merge behavior.

### 6.3. Plugin-Level Config vs. Execution-Level Config

~~~xml
<plugin>
    <groupId>org.example</groupId>
    <artifactId>demo-plugin</artifactId>
    <configuration><timeout>30</timeout></configuration>
    <executions>
        <execution>
            <id>fast-check</id>
            <phase>verify</phase>
            <goals><goal>check</goal></goals>
            <configuration><timeout>5</timeout></configuration>
        </execution>
    </executions>
</plugin>
~~~

Execution-level configuration provides values specific to `fast-check`; plugin-level configuration provides shared defaults. When a parameter differs from expectations, inspect both levels and the merged result.

## 7. Spring Boot Maven Plugin: `repackage` Running Twice Error

Spring Boot Maven Plugin **4.1.2** provides the `spring-boot:repackage` goal to turn a packaged JAR/WAR into an executable archive with the loader and dependencies required for `java -jar`.

### 7.1. When Using `spring-boot-starter-parent`

The Spring Boot parent already configures execution ID **`repackage`**. Therefore, enabling the plugin in a project normally requires only declaring the plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Do not add a second execution when your goal is simply to enable the parent's pre-configured setup.

### 7.2. Custom Classifier the Right Way

If you want to keep the original JAR and produce an executable JAR with classifier `exec`, customize the exact execution ID declared by the parent:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration><classifier>exec</classifier></configuration>
        </execution>
    </executions>
</plugin>
~~~

**There is no need to repeat `<goals>` or `<phase>`** in this example because the parent already supplies the `repackage` execution with its goal. The child only supplies the configuration override.

### 7.3. Error: `repackage` Runs Twice

An error-prone configuration:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>custom-repackage</id>
            <goals><goal>repackage</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

When the parent already defines ID `repackage`, ID `custom-repackage` is a separate execution. Maven can run both.

**How to diagnose:**

~~~bash
mvn help:effective-pom -Dverbose -Doutput=target/effective-pom.xml
mvn -X -B -ntp package
~~~

Look for `spring-boot-maven-plugin`, its execution IDs, and how many times the `repackage` goal appears.

**How to fix:** if using the starter parent, customize the execution with ID `repackage`; remove the extra execution if it has no distinct purpose. If not using the starter parent, declare a single execution for this goal yourself.

### 7.4. Without the Starter Parent

If the project only imports `spring-boot-dependencies` or uses another corporate parent, explicitly declare the plugin version and execution:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
    <executions>
        <execution>
            <id>repackage</id>
            <phase>package</phase>
            <goals><goal>repackage</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

Do not copy this whole execution block into a project already using the Spring Boot starter parent without checking the effective POM, as the parent may already provide an execution doing the same thing.

### 7.5. Main Class and Manifest Errors

If the executable JAR reports no main class found:

- Check whether the application has `public static void main(String[] args)`.
- Check whether multiple main classes caused the plugin to pick the wrong one.
- Use `mainClass` on the Spring Boot Maven Plugin to specify the entry point.
- Check `Main-Class` and `Start-Class` in the manifest.
- Do not edit the manifest in `maven-jar-plugin` expecting Spring Boot `repackage` to preserve it; the Spring Boot plugin manages those entries.

Configuration example:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration><mainClass>com.example.catalog.CatalogApplication</mainClass></configuration>
</plugin>
~~~

Inspect the artifact:

~~~bash
jar tf target/catalog-service-1.0.0.jar
unzip -p target/catalog-service-1.0.0.jar META-INF/MANIFEST.MF
~~~

On Windows, you can use `jar` and PowerShell to read the manifest. If `unzip` is unavailable, use an appropriate archive tool.

### 7.6. Classifier Errors and Modules Used as Dependencies

An executable Boot JAR places application classes under `BOOT-INF/classes`. Another module cannot consume this archive as a normal Java library JAR.

If a module needs both an executable archive to run and a regular artifact for other modules to compile against, retain the original JAR, attach the executable archive with a classifier, ensure consumers depend on the right artifact/classifier, and prevent `repackage` from replacing the library artifact that other modules read classes from.

## 8. Spring Boot `build-image`: Forked Lifecycle vs. No-Fork

This is a common execution error when binding the OCI image-building goal to the Maven lifecycle.

### 8.1. Invoking Directly from the Command Line

~~~bash
mvn spring-boot:build-image
~~~

`spring-boot:build-image` forks a lifecycle to ensure `package` has run before building the image. This is the right goal for command-line invocation.

### 8.2. Binding to the Lifecycle in the POM

If you want image building to run automatically during the `package` phase, use `build-image-no-fork`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
    <executions>
        <execution>
            <id>container-image</id>
            <phase>package</phase>
            <goals><goal>build-image-no-fork</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

`build-image-no-fork` does not fork a lifecycle. It fits when the goal is already bound to a build phase.

### 8.3. Why Does Using the Wrong Goal Cause Loops or Repeated Runs?

If you bind `build-image` to `package`, the goal forks a lifecycle to run `package`. The `package` run triggered by that execution can re-trigger the image build execution. That is why Spring Boot provides a separate no-fork goal.

| Invocation Style | Goal |
| --- | --- |
| Direct terminal invocation | `spring-boot:build-image` |
| Execution declared in POM | `spring-boot:build-image-no-fork` |

Do not combine both styles simultaneously without a clear reason, or the image may be built multiple times in one command.

### 8.4. Skip and Image Configuration

~~~bash
mvn -Dspring-boot.build-image.skip=true verify
~~~

Use this to temporarily skip image building when the plugin/goal supports this property. In CI, it is cleaner to isolate a dedicated `container-image` profile and enable it only in jobs with a Docker daemon.

Profile example:

~~~xml
<profiles>
    <profile>
        <id>container-image</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <executions>
                        <execution>
                            <id>container-image</id>
                            <phase>package</phase>
                            <goals><goal>build-image-no-fork</goal></goals>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Activate:

~~~bash
mvn -Pcontainer-image clean package
~~~

When the profile is inactive, the image-build execution is not added to the effective model. Verify with `help:active-profiles` and `help:effective-pom`.

## 9. Plugin Versions and Plugin Resolution

A build can use an unexpected plugin version if the POM does not pin the version or a parent/`pluginManagement` changes it.

### 9.1. Always Pin Plugin Versions

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
</plugin>
~~~

Place versions in the parent's `pluginManagement` so modules share the same version; modules must still declare the plugin under `build/plugins` when they need to activate that configuration.

### 9.2. Plugin Repositories Differ from Dependency Repositories

Maven uses `repositories` to download project dependencies and `pluginRepositories` to download Maven plugins/plugin dependencies.

If project dependencies download fine yet plugins fail to resolve, check `pluginRepositories`, mirrors in settings, and network/proxy. A mirror may apply to both central and plugin repositories depending on `mirrorOf`.

### 9.3. Error: “No plugin found for prefix”

~~~text
No plugin found for prefix 'spring-boot' in the current project
~~~

Common causes: plugin prefix unresolved, plugin not declared in the POM, wrong version/coordinates, network/mirror unable to reach plugin metadata, or running the command from a directory without the intended POM.

Try invoking full coordinates:

~~~bash
mvn org.springframework.boot:spring-boot-maven-plugin:4.1.2:help
~~~

If full coordinates still fail to resolve, inspect repositories/mirrors and credentials. Never add a plugin to `<dependencies>`; Maven build plugins must be configured under `<build><plugins>`.

### 9.4. Plugin Dependency Resolution Errors

If Maven reports it cannot download a plugin or plugin dependency, identify the artifact/version in the log and check `help:effective-settings`, `pluginRepositories`, proxy, certificate trust, credentials, and Maven/JDK compatibility.

Do not delete the entire local repository right away. If suspecting a corrupted cached artifact, delete only the specific artifact/version directory after verifying the path and source repository.

## 10. JDK, Maven Runtime, and Compiler Configuration

Another source of errors is Maven running on a different JDK than the project's expected Java target.

~~~bash
mvn -version
java -version
~~~

`mvn -version` shows the Maven version, Java version, and Java home used by the Maven process. `java -version` shows only the `java` executable found on PATH; the two can differ if `JAVA_HOME` and PATH are out of sync.

Java 17 Spring Boot example:

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

The Spring Boot parent normally configures compiler release from `java.version`. If using a corporate parent or custom Maven Compiler Plugin setup, check the effective POM for the final `source`, `target`, or `release` values.

If Maven runs on JDK 21 yet must compile with JDK 17, Maven Toolchains Plugin can select a separate compiler toolchain. In that case `mvn -version` still reports Maven runtime JDK 21 while the compiler toolchain is JDK 17. Check toolchain and compiler plugin logs.

## 11. Skip Flags: Why Do Tests or Plugins Still Run?

Many plugins define their own skip properties. One generic property does not skip every plugin.

### 11.1. `-DskipTests`

~~~bash
mvn -DskipTests package
~~~

With Maven Surefire, this property skips running tests while still compiling test sources. It is a temporary shortcut for fast builds/packaging; it should not replace release quality gates.

### 11.2. `-Dmaven.test.skip=true`

~~~bash
mvn -Dmaven.test.skip=true package
~~~

This property is supported by Maven compiler/Surefire/Failsafe plugins to skip both test compilation and test execution. Use cautiously because test code is not compiled.

### 11.3. Integration Tests and Plugin-Specific Skips

Failsafe has its own property such as `skipITs`; verify exact plugin versions and config. Do not assume `-DskipTests` or `-DskipITs` behaves identically across all plugins.

Spring Boot `build-image` supports user property:

~~~bash
mvn -Dspring-boot.build-image.skip=true verify
~~~

If the goal still runs, check which goal is bound, whether the plugin version supports that user property, whether multiple executions or another profile added an execution, and what the effective POM shows for the final skip value.

## 12. Multi-Module Reactor and Executions Running in the Wrong Module

In a reactor, a plugin execution in the parent may be inherited by multiple modules. When building one module, Maven may run plugins on other modules depending on packaging and configuration.

~~~bash
mvn -pl :catalog-service -am verify
mvn -pl :catalog-service -amd verify
mvn -N validate
mvn -rf :catalog-service verify
~~~

- `-pl` selects the project/module.
- `-am` also builds modules the selected project depends on.
- `-amd` builds modules depending on the selected project.
- `-N` disables recursive builds.
- `-rf` resumes the reactor from the specified project.

For each failing module, run `help:effective-pom -Dverbose`, `help:active-profiles`, and `-X -e` specifically for that module. Do not inspect only the root POM; child POMs can override plugin versions or add executions/profiles.

A parent aggregator typically has `<packaging>pom</packaging>`. `pom` packaging does not bind compile/package goals like a `jar` module does. However, executions declared in the parent's `<build><plugins>` can be inherited and run in child modules if inheritance is enabled.

If a plugin should run only in one module, move the execution to that module, use a targeted profile, or set `<inherited>false</inherited>` when preventing execution/plugin config propagation to children.

## 13. Workflow to Find the Source of Overridden Configuration

When the final parameter differs from the value you set:

1. Capture state: `mvn -version`, `mvn help:active-profiles`, and `mvn help:effective-pom -Dverbose -Doutput=target/effective-pom.xml`.
2. Locate plugin coordinates, version, execution ID, phase, goals, configuration, and skip parameters.
3. Read verbose comments to determine whether each node came from parent, child, or profile.
4. Use `help:describe` to verify parameter names, defaults, and user properties.
5. Fix the right source: version in parent/`pluginManagement`; execution ID; profile activation; XML parameter/user property; or module placement.
6. Re-run `mvn clean verify`, regenerate the effective POM, and compare debug logs/artifacts.

Do not edit multiple sources at once; changing parent, child, profile, and command line in a single pass makes it hard to know which change actually resolved the issue.

## 14. Reproduction Example: Parent and Child Creating Two Executions

Parent POM has:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <goals><goal>repackage</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

Child wants to add a classifier, yet declares the wrong ID:

~~~xml
<execution>
    <id>exec-archive</id>
    <goals><goal>repackage</goal></goals>
    <configuration><classifier>exec</classifier></configuration>
</execution>
~~~

The result can be two executions: `repackage` from the parent and `exec-archive` from the child. Fix the child by reusing ID `repackage` and providing only the configuration to change:

~~~xml
<execution>
    <id>repackage</id>
    <configuration><classifier>exec</classifier></configuration>
</execution>
~~~

Then inspect the effective POM and debug logs to verify only the intended execution remains.

## 15. Reproduction Example: `build-image` Fork Loop

Wrong configuration when binding:

~~~xml
<execution>
    <id>image</id>
    <phase>package</phase>
    <goals><goal>build-image</goal></goals>
</execution>
~~~

`build-image` forks a lifecycle to ensure the `package` phase ran. When bound to `package`, it can re-trigger the packaging process and loop executions.

Correct configuration for lifecycle binding:

~~~xml
<execution>
    <id>image</id>
    <phase>package</phase>
    <goals><goal>build-image-no-fork</goal></goals>
</execution>
~~~

Or do not bind it to the lifecycle and simply run `mvn spring-boot:build-image`. Pick whichever pattern suits your pipeline; do not both bind the goal and invoke it directly in the same command unless you intend to build the image multiple times.

## 16. Symptom, Cause, and Resolution Table

| Symptom | Possible Cause | How to Check and Fix |
| --- | --- | --- |
| Plugin goal does not run in `package` | Declared only in `pluginManagement` or missing execution/binding | Check effective POM; add plugin declaration/execution in the right place |
| Plugin runs twice | Parent and child use different execution IDs; goal also invoked directly | Check IDs in debug log; merge under same ID or remove extra execution |
| Unexpected plugin version | Parent/`pluginManagement`/profile override | Check verbose effective POM and plugin coordinates |
| Child configuration has no effect | Mismatched execution ID or parameter merged from another source | Use the same execution ID; inspect effective POM |
| Configuration duplicated | Executions with different IDs merged into two executions | Check parent/child/profile IDs |
| `repackage` reports archive not found | Goal ran before `package` or wrong source classifier | Run `package` first; check phase/order/classifier |
| `repackage` does not run | Not using starter parent and missing execution declaration | Add execution for goal `repackage` in `package` |
| `repackage` runs, JAR is not executable | Wrong main class/manifest/layout/dependencies | Check `Start-Class`, `Main-Class`, and archive entries |
| `build-image` repeats or fork recurses | Bound `build-image` to lifecycle instead of no-fork | Use `build-image-no-fork` when binding |
| `build-image` skips in CI | Profile inactive or skip property enabled | `help:active-profiles`, effective POM, and skip config |
| `No plugin found for prefix` | Prefix/repository metadata unresolved | Use full coordinates, check `pluginRepositories`/mirror |
| Plugin fails to resolve dependencies | Proxy, credentials, plugin repository, or missing version | Check effective settings and debug transfer logs |
| `Unknown lifecycle phase` | Typo in phase or property parsed as goal/phase | Check command-line quoting and `mvn -h` |
| `BUILD SUCCESS` yet tests did not run | Skip property or Surefire/Failsafe config | Check test reports, `skipTests`/`skipITs` |
| Test compile still runs with `skipTests` | `skipTests` skips execution only, not test compilation | Use `maven.test.skip` if truly skipping both compile and run |
| Runs locally, fails differently in CI | Different active profiles, JDK, settings, OS, or Maven version | Compare `mvn -v`, active profiles, effective POM/settings |
| Module A runs plugin, module B does not | Different packaging/module POM/profiles/inheritance | Inspect effective POM per module |
| Parent plugin runs in every child | Execution/plugin config is inherited | Place execution in target module or set `inherited=false` |
| Maven uses wrong Java | `JAVA_HOME`/PATH/toolchains out of sync | `mvn -version`, check toolchains/compiler release |
| Build cannot find plugin after changing mirror | Plugin repository not mirrored or wrong credentials | Check `pluginRepositories` and settings mirrors |
| Build outputs stale JAR after source edit | `package` did not run or source/module outside reactor | `clean package`, verify module and output timestamp |
| `-Dskip=true` does not skip plugin | Plugin does not declare that user property | Use `help:describe` and exact goal property |
| Debug log too large or leaks secrets | Enabled `-X` and shared raw log | Redact secrets, internal URLs, tokens, and environment |

## 17. Quick Diagnostic Command Suite

~~~bash
mvn -version
mvn help:active-profiles
mvn help:effective-pom -Dverbose -Doutput=target/effective-pom.xml
mvn help:effective-settings -Doutput=target/effective-settings.xml
mvn help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin:4.1.2 -Dgoal=repackage -Ddetail
mvn -X -e -B -ntp clean verify
~~~

For multi-module builds:

~~~bash
mvn -pl :catalog-service -am -X -e -B -ntp verify
~~~

Once debugging finishes, save the exact command line and working directory, Maven version, Java runtime/toolchain, active profiles, redacted effective POM, plugin coordinates/version/execution IDs, first error, actual artifact outputs, and module pass/fail status in the reactor.

**Never post raw effective settings or debug logs to public systems.** These files can contain internal repository URLs, paths, system properties, or credential-related details.

## 18. Safe CI Troubleshooting Workflow

1. **Keep the reproducing build command unchanged.** Do not alter multiple flags at once.
2. **Record the toolchain:** Maven, Java runtime, compiler toolchain, and OS.
3. **Identify the module:** project root, `-pl`, `-am`, packaging, and `artifactId`.
4. **Inspect active profiles:** verify whether CI activates different profiles than local.
5. **Export effective POM:** inspect plugin versions, executions, phases, configurations, and merge sources.
6. **Read debug logs:** verify which goals actually ran, execution IDs, and order.
7. **Pinpoint one specific cause:** missing binding, duplicate execution, wrong version, skip, fork, module, or plugin resolution.
8. **Fix one configuration source:** parent, `pluginManagement`, child plugin, profile, or command line.
9. **Re-run `clean verify`:** verify both tests and packaged artifacts.
10. **Compare outputs:** effective POM, execution counts, archive manifest, and image build results.
11. **Add regression checks:** fail CI if unintended executions appear or artifacts are invalid.
12. **Archive redacted diagnostics:** enable local-vs-CI comparisons next time.

### Recommended Quality Gates

- [ ] Maven/Java versions are pinned and recorded.
- [ ] Key plugin versions are explicitly managed.
- [ ] Active profiles are explicitly determined in CI.
- [ ] Effective POM can be exported for investigation.
- [ ] Spring Boot `repackage` runs only the required execution.
- [ ] `build-image` uses the right goal for its invocation style (fork when direct, no-fork when bound).
- [ ] Test reports prove tests actually executed.
- [ ] Executable JAR manifest/classifier are verified.
- [ ] Image builds are neither duplicated nor unexpectedly skipped.
- [ ] Reactor module list and build order are accurate.
- [ ] Debug logs and settings are protected/redacted.
- [ ] Build succeeds from a clean workspace without relying on stale outputs.

## 19. Self-Check Exercises

**1. How do a phase and a goal differ?**

Answer: A phase is a milestone in a lifecycle; a goal is a plugin task bound to a phase or invoked directly.

**2. Why does `mvn package` run multiple plugins?**

Answer: Default packaging binds multiple plugin goals to phases before and at `package`; the POM can add additional executions.

**3. Does `pluginManagement` automatically execute a plugin?**

Answer: It manages configuration/versions when the plugin is referenced for use; it should not be viewed as an independently activated plugin execution.

**4. Parent has execution ID `repackage`, child adds ID `custom-repackage`. What happens?**

Answer: Since the two IDs differ, both executions can coexist and run. Reuse ID `repackage` if you want to customize the inherited execution.

**5. What is `help:effective-pom -Dverbose` used for?**

Answer: Displays the POM after inheritance, interpolation, and active profiles, annotated with origin comments where supported.

**6. Why is `help:active-profiles` important?**

Answer: Profiles can add plugins, executions, or change properties; local and CI may activate different profiles.

**7. Why should you not bind `spring-boot:build-image` directly to the `package` phase?**

Answer: This goal forks the lifecycle to ensure `package` ran. When binding to the lifecycle, use `build-image-no-fork`.

**8. When is `spring-boot:repackage` used?**

Answer: After the plain JAR/WAR has been created; with the starter parent, the `repackage` execution is pre-configured.

**9. How does `-DskipTests` differ from `-Dmaven.test.skip=true`?**

Answer: `skipTests` skips running tests while still compiling test sources; `maven.test.skip` can skip both test compilation and execution.

**10. Why might a plugin fail to resolve even though project dependencies resolve?**

Answer: Plugins may require separate `pluginRepositories`/mirrors/credentials, or the plugin artifact may not exist in the current repository.

**11. Can Maven `-version` and `java -version` differ?**

Answer: Yes. The Maven process uses Java determined by `JAVA_HOME`/Maven launcher; the `java` executable on PATH may be a different installation. Compiler toolchains can also pick a separate JDK.

**12. The effective POM looks right yet the goal still runs twice—what to check next?**

Answer: Check debug logs for direct invocations, multiple executions, forked lifecycles, profiles, or another reactor module running the same plugin.

## 20. Official References

1. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
2. [Apache Maven — Introduction to the POM and Inheritance](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
3. [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
4. [Apache Maven — Guide to Configuring Default Mojo Executions](https://maven.apache.org/guides/mini/guide-default-execution-ids.html)
5. [Apache Maven Help Plugin — Plugin Details](https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html)
6. [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
7. [Apache Maven — Running Maven](https://maven.apache.org/run.html)
8. [Spring Boot 4.1.2 Maven Plugin — Goals](https://docs.spring.io/spring-boot/maven-plugin/goals.html)
9. [Spring Boot 4.1.2 — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
10. [Spring Boot 4.1.2 — Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html)
11. [Spring Boot — Using the Maven Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
12. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)