# Distinguishing `plugins` from `pluginManagement` and Configuring `executions` in Maven (Spring Boot)

In a Maven-based Spring Boot project, three concepts frequently sit next to one another in `pom.xml` yet serve distinct purposes:

- **`<build><plugins>`:** declares/configures the build plugins that the project actively uses. Plugin goals bound to the lifecycle can run when Maven reaches the corresponding phase; plugins can also run when a goal is invoked directly.
- **`<build><pluginManagement>`:** centrally manages **default versions, configuration, and default executions** for plugins. For a plugin not yet activated or without lifecycle-bound goals, this management section **does not create a new task to run on its own**.
- **`<executions>` on a plugin:** defines **which goals** run, **in which phase**, with **what configuration**, and uses **`id`** to identify an execution (for configuration, inheritance, and overriding).

For Spring Boot, the practical checkpoint is **`spring-boot-maven-plugin:repackage`**: a project can build a plain Java JAR, or an **executable Spring Boot JAR** containing the launcher and dependencies to run via `java -jar`. To understand whether `repackage` runs or not, you must inspect `plugins`, `pluginManagement`, `executions`, and parent POM inheritance together.

## 1. Grasp the Maven Model First: Plugin, Goal, Lifecycle, Phase, Execution

A **plugin** is an artifact implementing tasks for Maven. For example:

| Plugin | Common Goals | Role |
| --- | --- | --- |
| `maven-compiler-plugin` | `compile`, `testCompile` | Compiles Java source code |
| `maven-surefire-plugin` | `test` | Runs unit tests |
| `maven-jar-plugin` | `jar` | Builds a standard JAR |
| `maven-failsafe-plugin` | `integration-test`, `verify` | Runs and verifies integration tests when configured |
| `spring-boot-maven-plugin` | `run`, `repackage` | Runs a Boot app, repackages the archive into executable form |
| `maven-antrun-plugin` | `run` | Runs custom Ant tasks during the lifecycle |

A **goal** is a specific task provided by a plugin, such as `compiler:compile` or `spring-boot:repackage`. A **lifecycle** is the build process; a **phase** is a milestone within a lifecycle, such as `compile`, `test`, `package`, `verify`. An **execution** is a configuration using one or more goals, optionally bound to a specific phase.

Execution flow when calling:

~~~bash
mvn clean package
~~~

~~~text
clean lifecycle
  └─ clean → cleans previous build output

default lifecycle (runs required phases up to package)
  validate → ... → compile → ... → test → package
                          |           |         |
                    compiler goal  surefire   jar goal (with packaging=jar)
                                                 |
                                                 └─ spring-boot:repackage
                                                    if properly bound
~~~

The diagram highlights key steps, not an exhaustive list of every phase. With `<packaging>jar</packaging>` (or the default when packaging is omitted), Maven **already has default goals bound to the lifecycle**. That is why Maven compiles and creates a JAR even when `pom.xml` does not explicitly list `maven-compiler-plugin` and `maven-jar-plugin`. That does not mean every plugin runs automatically: an additional plugin only runs if its goal is bound to the lifecycle or invoked directly.

Comparing two command forms:

~~~bash
mvn package
mvn spring-boot:run
~~~

- `mvn package` tells Maven to execute phases up to `package` and run **all goals bound to those phases**.
- `mvn spring-boot:run` directly invokes the `run` goal of the Spring Boot Maven Plugin (requires the plugin to resolve and sufficient app configuration); it is **not equivalent** to packaging a JAR file and running that artifact.
- `mvn package spring-boot:repackage` builds the package first and then explicitly invokes `repackage`. If the project already binds a `repackage` execution to `package`, calling the goal separately can run `repackage` twice; do not add it mechanically.

Maven clearly distinguishes **phases** from **goals**: `package` is a phase, whereas `spring-boot:repackage` is a goal. `<execution>` bridges the two.

## 2. `<build><plugins>`: Adding Plugins to the Active Build Configuration

A plugin declared at the build level typically looks like:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.3.5</version>
        </plugin>
    </plugins>
</build>
~~~

This is a **snippet inside `pom.xml`**, not a standalone POM. The project has declared the Spring Boot plugin, yet `groupId`, `artifactId`, and `version` alone do not execute **every** plugin goal in every phase. Maven needs a binding, a configured execution, an inherited execution, or a direct goal invocation. For instance, `repackage` might be configured by the Spring Boot parent or by the project's `<executions>`.

Unlike `<dependencies>`, a plugin is not an application library used in Java code. `spring-boot-maven-plugin` runs **during the build**, whereas `spring-boot-starter`/`spring-boot-starter-web` are dependencies supporting the **application**.

### Plugins Placed in a Parent POM Can Be Inherited

If a parent declares a plugin under `<build><plugins>`, child modules generally inherit that plugin configuration (unless `<inherited>false</inherited>` or specific inheritance rules apply). The plugin then **becomes an active plugin** in child modules without those children declaring it. This differs from managing a plugin via `pluginManagement`, which only establishes rules for when the plugin is used.

Practical impact: in multi-module Maven builds, avoid placing a plugin with an application-specific execution directly under `<plugins>` in a shared parent if you do not want every child module to run that execution. Use `pluginManagement` to manage versions/configs and let each module opt in by declaring the plugin.

## 3. `<pluginManagement>`: Centralized Management Without Spawning New Goals

Example parent POM managing the Spring Boot Maven Plugin:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>3.3.5</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

This snippet sets the **managed version** for the plugin. It does not mean Maven automatically adds `spring-boot:repackage` to the `package` phase. A child module wanting to use the plugin can declare a shorter entry:

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

Here, management from the parent supplies `version=3.3.5` to the child's plugin declaration. **However**, for `repackage` to run during `package`, there must still be a valid execution/binding, such as a managed/inherited execution with the `repackage` goal.

### Exception to Understand Correctly: Plugins Already Bound by Maven

Do not oversimplify `pluginManagement` into an absolute rule like "if a plugin isn't listed in `<plugins>`, management has zero effect". With `packaging=jar`, Maven binds goals of compiler, resources, surefire, jar, etc., into the default lifecycle. `pluginManagement` can affect the version and configuration of **plugins/goals already invoked by the default lifecycle**, even when they are not explicitly listed in the module's `<plugins>`.

Distinguish two cases:

1. **Already bound by default or already active plugin:** management can customize that plugin's version and behavior.
2. **A completely new plugin with no binding or goal invoked:** placing it solely in management creates no execution task.

For `spring-boot-maven-plugin` and `repackage`, do not guess from the plugin name; inspect active plugins and actual executions in the effective POM.

### Do Not Confuse `pluginManagement` with `dependencyManagement`

| Section | Managed Target | Example |
| --- | --- | --- |
| `<dependencies>` | Libraries directly used by the app | `spring-boot-starter-web` |
| `<dependencyManagement>` | Versions/rules for app dependencies | `spring-boot-dependencies` BOM |
| `<build><plugins>` | Plugins performing build actions | `spring-boot-maven-plugin` |
| `<build><pluginManagement>` | Versions/configs/executions for build plugins | Pinning Spring Boot or Surefire plugin versions |

**Importing the Spring Boot BOM via `<dependencyManagement>` does not bring in the plugin management of `spring-boot-starter-parent`.** That is why configuring the Spring Boot Maven Plugin differs depending on whether you use the starter parent.

## 4. `<executions>`: Controlling When and How Goals Run

General structure:

~~~xml
<plugin>
    <groupId>...</groupId>
    <artifactId>...</artifactId>
    <version>...</version>
    <configuration>
        <!-- Shared plugin-level configuration -->
    </configuration>
    <executions>
        <execution>
            <id>unique-execution-id</id>
            <phase>phase-name</phase>
            <goals>
                <goal>goal-name</goal>
            </goals>
            <configuration>
                <!-- Configuration specific to this execution -->
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

This is an **XML schema template**, not runnable configuration: `...` are placeholders. Meaning of each part:

| Element | Meaning |
| --- | --- |
| `<id>` | Execution identifier within the plugin; used to merge/override configuration during POM inheritance and read logs |
| `<phase>` | Phase where Maven executes the goal, e.g., `validate`, `process-resources`, `package` |
| `<goals>` | One or more goals belonging to the **current plugin** |
| `<configuration>` at plugin level | Configuration shared across applicable goal invocations |
| `<configuration>` at execution level | Execution-specific configuration that can override matching plugin-level parameters |
| `<inherited>` | Controls whether configuration/execution is inherited from parent |

**`<phase>` can be omitted when the goal defines a default phase in its plugin descriptor.** For example, `spring-boot:repackage` has a default phase of `package`; if a goal has no default phase and `<phase>` is omitted, the execution typically **will not run during the lifecycle**. Distinguish declaring a goal inside `<executions>` from invoking a goal directly via CLI.

### Runnable Example: Binding a Goal to `validate`

Inside `<build><plugins>` of a POM, add:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <executions>
        <execution>
            <id>show-build-marker</id>
            <phase>validate</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <echo message="VALIDATE_PHASE_REACHED"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Run in a Maven project with a valid POM:

~~~bash
mvn validate
~~~

Maven output will include **`VALIDATE_PHASE_REACHED`** printed by Ant echo alongside other build/plugin logs; do not treat the entire Maven stdout as fixed. If you run `mvn package`, `validate` also executes before `package`, so this execution runs as part of the build.

Experiment:

1. Move the entire plugin/`show-build-marker` config into `<build><pluginManagement><plugins>...` and remove the plugin from `<build><plugins>`: the `antrun:run` goal is not triggered from management alone.
2. Add `maven-antrun-plugin` to `<build><plugins>`, declaring only `groupId`/`artifactId`: it inherits the managed configuration and the goal binds to `validate`.
3. Run `mvn validate` again and observe the marker appear.

This mechanism explains why parents often manage many plugins while each child module enables only the plugins required for its own tasks.

### Plugin-Level Configuration vs. Execution-Level Configuration

Suppose a plugin has two different executions: `<plugin><configuration>` holds shared parameters, while `<execution><configuration>` holds parameters specific to one execution. When the same parameter appears at both levels, the execution-specific configuration generally takes precedence for that invocation after Maven merges configurations. XML merging rules also respect inheritance and attributes such as `combine.self`/`combine.children` when present; inspect the effective POM for complex setups.

If a goal is also invoked directly from the CLI, **do not assume** settings placed solely inside an arbitrary execution automatically apply to CLI invocations. CLI invocations have their own execution handling (typically involving `default-cli`) and plugin-level configuration; check the plugin descriptor and effective invocation to decide where parameters belong.

## 5. Spring Boot with `spring-boot-starter-parent`: Why Does `repackage` Run Without Writing an Execution?

The Spring Boot starter parent supplies dependency management and build/plugin defaults, including the `repackage` execution of `spring-boot-maven-plugin` with **execution id `repackage`**. Consequently, when a child project uses the starter parent, it usually only needs to declare the Spring Boot Maven Plugin under `<build><plugins>` to activate the managed execution.

Complete example, assembled from two files:

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>packaging-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/com/example/demo/PackagingDemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PackagingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PackagingDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showMessage() {
        return args -> System.out.println("PACKAGING_OK");
    }
}
~~~

Java code is valid for **Java 17+**. Boot version `3.3.5` is pinned so the example is reproducible; it is not presented as the latest version. Compatible Maven, JDK 17+, and dependency repository access are required for the first build. Run in the directory containing `pom.xml`:

~~~bash
mvn clean package
java -jar target/packaging-demo-1.0.0.jar \
  --spring.main.banner-mode=off \
  --logging.level.root=OFF
~~~

The trailing `\` is line-continuation syntax **on Linux/macOS**; on Windows PowerShell, write `java -jar target/packaging-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF` on **one line**. With banner and root logging disabled and a successful startup, the program prints:

~~~text
PACKAGING_OK
~~~

During `mvn clean package`, Maven prints logs that vary by environment; there is no fixed stdout for the build itself. The project uses `spring-boot-starter` rather than the web starter, so it does not start an HTTP server and exits after running `CommandLineRunner`.

**Role breakdown:**

1. Maven selects `jar` packaging by default, compiles Java, and builds a plain JAR via default lifecycle bindings.
2. `spring-boot-starter-parent` supplies the version/configuration and `repackage` execution for the Spring Boot Maven Plugin.
3. The project's `<build><plugins>` adds the Spring Boot Maven Plugin to the active plugin list.
4. The `repackage` execution runs in the `package` phase after Maven produces the initial archive for repackaging. The result is an executable JAR containing the Spring Boot launcher and required runtime dependencies.
5. `java -jar` runs the built artifact directly. Maven and the Spring Boot Maven Plugin **do not run inside the deployed application process**.

This example **does not rewrite `<executions>` for `repackage`** because the starter parent manages it. However, if you remove the plugin from `<build><plugins>` without any other activation mechanism, do not assume Maven will build an executable Boot JAR just because `spring-boot-starter` is a dependency.

## 6. Customizing an Inherited Execution: You Must Use the Exact `id=repackage`

When using the starter parent, to customize the existing `repackage` execution, declare the same `id`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <id>repackage</id>
                    <configuration>
                        <classifier>exec</classifier>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

This snippet goes inside `<project>` of the example using the starter parent. With the matching execution id, Maven merges/overrides the inherited execution's configuration, **without needing to redeclare `<goal>repackage</goal>`**. `classifier=exec` causes the repackaged artifact to be created as `packaging-demo-1.0.0-exec.jar` alongside the original artifact in this illustrative setup; you can run:

~~~bash
java -jar target/packaging-demo-1.0.0-exec.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

**Common mistake:** creating a new execution with `<id>custom-repackage</id>` and adding `<goal>repackage</goal>` while the parent's `repackage` execution remains active. Maven treats these as **two separate executions**; the goal can run twice in the same phase and cause confusing output or packaging order issues. If your intent is only to change parent config, keep `id=repackage`.

ID rules in inheritance:

| Situation | Outcome |
| --- | --- |
| Child declares an execution with the same id as parent on the same plugin | Configurations are merged/overridden according to Maven rules |
| Child declares a new id | Adds a separate execution alongside the inherited one |
| Child omits `<id>` | Maven assigns a default id to that execution; it does not match `repackage` |
| Need to avoid an inherited execution | Consider goal-supported `skip`, `inherited` at the appropriate parent level, or module plugin layout; verify via effective POM |

Do not repeat the entire existing execution when you only need to change one parameter. Inspect version/goal/execution id in the effective POM before adding configuration.

## 7. Without Starter Parent: Importing the BOM Differs from Configuring Maven Plugins

A project may inherit a corporate parent and therefore not use `spring-boot-starter-parent`. It can still **import the Spring Boot BOM** to manage dependency versions:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

This snippet provides **dependency management** only. Do not infer that it configures `spring-boot-maven-plugin` or a `repackage` execution. For Maven to build an executable Boot JAR, configure the plugin version and goal explicitly:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.3.5</version>
            <executions>
                <execution>
                    <id>boot-repackage</id>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

This is a configuration snippet inside `<project>`; the example assumes the project also has appropriate `dependencies`, `packaging=jar`, and a compatible compiler. The `repackage` goal has a default phase of `package`, so `<phase>package</phase>` can be omitted; however, writing it explicitly is also valid when helping learners see the binding:

~~~xml
<execution>
    <id>boot-repackage</id>
    <phase>package</phase>
    <goals>
        <goal>repackage</goal>
    </goals>
</execution>
~~~

These two execution examples are **alternatives to each other**; **do not put both in the same plugin** if you only want a single repackaging step.

Without the starter parent, check the compiler plugin version/config, Java release, surefire, and other needed plugins separately. The BOM does not carry over the parent's plugin defaults. If a corporate parent manages plugins, you can inherit its versions/configs instead of duplicating everything in each module.

### Why Does `repackage` Need a JAR First?

`spring-boot:repackage` **repackages** an already-built Java archive; it does not replace `compiler:compile` or `jar:jar`. On a standard `jar` project, the `package` phase binds `jar:jar`, and the Boot execution runs after the default packaging goal in lifecycle order. If you invoke only:

~~~bash
mvn spring-boot:repackage
~~~

on a project that has no input JAR yet, repackaging may fail. The standard practice is binding `repackage` to `package` and running `mvn package`. Manually running `mvn package spring-boot:repackage` is only appropriate when you genuinely want to run `repackage` after `package` and understand which executions already ran beforehand.

## 8. Managing Plugins in Multi-Module Projects

A parent POM using `<packaging>pom</packaging>` can define plugin management for the whole organization:

**Parent POM (snippet inside `<project>`):**

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>3.3.5</version>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

**Application module (snippet inside child `<project>`):**

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

**Library module:** omit the Boot plugin so the library builds a regular JAR.

Result: the application module gets a managed `repackage` execution; the library module is not forced into packaging an executable Boot JAR just for sharing a version-managing parent. This approach gives application modules and library modules lifecycles suited to their respective roles.

### When to Put `<plugins>` in the Parent?

Put a plugin in the parent's `<build><plugins>` when **every child module truly needs** that plugin/execution (excluding modules that disable inheritance or override it). For example, build-check plugins applied across all modules may fit there; Boot `repackage` usually fits only application modules. Do not apply a rigid rule to every project without checking actual parent inheritance, packaging types, profiles, and execution ids.

### `<inherited>false</inherited>` vs. `<skip>true</skip>`

- `<inherited>false</inherited>` is part of the Maven model controlling whether plugin/execution configuration propagates down to child POMs (placed at a supported level).
- `<skip>true</skip>` is a parameter of a **specific goal**, meaningful only if that goal supports it and receives the configuration properly. Spring Boot's `repackage` goal supports a `skip` option.
- Both differ from not declaring the plugin. Whether an execution is inherited and whether the goal actually runs must be verified via effective POM and build logs.

## 9. Plugin-Level Configuration, Execution-Level Configuration, and Precedence

Example where a plugin has shared parameters and an execution has its own parameter:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <excludeDevtools>true</excludeDevtools>
    </configuration>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

This configuration snippet **assumes the starter parent is used**, so the `repackage` execution and its goal are inherited. The plugin-level `excludeDevtools` applies broadly where relevant; `classifier` applies specifically to the `repackage` execution. Parameter names must match the plugin goal and version. Do not take a parameter from another plugin and drop it into `<configuration>` just because both are XML.

In a combination of parent + child + profiles, Maven configuration merges from multiple sources. A safe way to read it:

1. Check which plugins are declared directly/inherited or bound by the default lifecycle.
2. Identify executions **by `id`**, phase, and goals.
3. Check configuration at both plugin level and execution level after inheritance.
4. Check logs during phase execution, because the effective POM describes the model while logs show which goals actually ran.

If you change `<phase>package</phase>` to `<phase>verify</phase>`, the execution runs when Maven reaches `verify` (provided the plugin goal is properly bound). `mvn package` does not reach `verify`, so the goal will not run during that invocation. For Boot `repackage`, arbitrarily changing the phase can also make the artifact produced at `package` differ from expectations, so only change it with a clear build requirement.

## 10. Diagnosing Configuration from Effective POM and Maven Logs

Three commands for reading configuration and execution are especially helpful:

~~~bash
mvn help:effective-pom
mvn help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail
mvn package
~~~

- **`help:effective-pom`**: reveals the POM model after applying parent, plugin management, profiles, and related configs; look for `spring-boot-maven-plugin` in both `pluginManagement` and `plugins`. Careful: seeing a plugin in `pluginManagement` is not proof that its goal ran.
- **`help:describe`**: describes goals, parameters, and default phase of the resolved plugin; use it to verify goal/parameter names when configuring executions.
- **`mvn package`**: watch for log lines shaped like `plugin-prefix:goal (execution-id)` to see which executions actually ran; this is the final word on the current build.

You can export the effective POM to inspect configurations more easily:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
~~~

This command writes an analysis file under `target/` in the current project; run it only when you want to generate that file. If Maven cannot create the destination path in a specific setup, choose another writable location on your filesystem.

When you need more detail on why a plugin ran or was skipped:

~~~bash
mvn -X package
~~~

`-X` prints very verbose debug logs that may contain sensitive configuration and file paths. Use it only for diagnosis when standard logs are insufficient; do not enable debug logging on every build.

### Inspecting the Packaged Artifact

After building, depending on project configuration, run:

~~~bash
jar tf target/packaging-demo-1.0.0.jar
java -jar target/packaging-demo-1.0.0.jar
~~~

For a standard **executable Boot JAR**, you typically see `BOOT-INF/classes/`, `BOOT-INF/lib/`, and the launcher in the manifest. For a **plain JAR**, the launcher or runtime dependencies needed for `java -jar` may be missing. Artifact filenames/paths and classifiers depend on `artifactId`, `version`, `finalName`, and repackage config; do not assume every project generates the same filename as the example.

Signs a build ran yet produced an unexpected artifact:

- `mvn package` succeeds but the JAR does not run directly: check whether `repackage` is bound and actually ran.
- An unexpected plugin version was used: check direct version, `pluginManagement`, and parent.
- `repackage` appears twice in logs: check for duplicate intended execution ids, especially with the starter parent.
- Application libraries missing at runtime: check `dependencies`/scopes; `pluginManagement` does not add application dependencies.

## 11. Common Errors Table and Resolutions

| Symptom | Likely Cause | How to Check/Fix |
| --- | --- | --- |
| Configured only in `pluginManagement` and custom goal does not run | Plugin not activated or lacks lifecycle binding | Declare plugin in `<build><plugins>` and configure execution goal/phase if needed |
| Plugin declared but goal missing during `mvn package` | Goal not bound; phase other than `package`; inactive profile | Inspect effective POM, goal default phase, `executions`, and Maven log |
| Has Spring Boot parent yet JAR is still a plain JAR | Spring Boot Maven Plugin not activated or `repackage` skipped/overridden | Check `<build><plugins>`, `id=repackage` execution, `repackage` log |
| Using BOM but missing Spring Boot Maven Plugin version | Importing BOM manages dependencies only | Add plugin version or inherit appropriate `pluginManagement` |
| `repackage` runs twice | Created a new execution instead of customizing inherited `id=repackage` | Use the same id if customizing the inherited execution |
| `No goals have been specified for this build` | Command omitted a valid phase/goal | Invoke `mvn package` or a specific goal |
| `No plugin found for prefix 'spring-boot'` | Plugin prefix unresolved or plugin repo/config issue | Check `pom.xml`, plugin version, repositories, network; try full plugin coordinates |
| `Plugin execution not covered by lifecycle configuration` in IDE | IDE/m2e does not know how to handle a plugin execution | Separate IDE integration issues from Maven CLI; verify `mvn package` first |
| Missing source JAR error during `repackage` | Invoked goal before archive creation or wrong packaging config | Bind to `package` after JAR/WAR creation; run `mvn package` |
| `no main manifest attribute` on `java -jar` | Likely running a plain JAR instead of an executable Boot JAR | Check manifest, filename/classifier, and `repackage` execution |
| `ClassNotFoundException` after packaging | Wrong dependency/scope/classpath or wrong archive | Check dependency tree, JAR contents, launcher, and logs |
| Compiler/Surefire run automatically even without declaring plugins | Maven binds default goals according to `packaging` | Distinguish default lifecycle plugins from unbound custom plugins |

In Spring Boot, **`spring-boot-maven-plugin` handles only the build side**. It does not replace `@SpringBootApplication`, `spring-boot-starter` dependencies, the JDK, or the JVM runtime. Troubleshooting must start at the actual failing step: plugin resolution, compile, test, archive, repackage, or `java -jar`.

## 12. Selection Workflow in Real Projects

Use this short checklist before editing `pom.xml`:

1. **Identify what task is needed:** compile, test, package JAR/WAR, Boot repackage, generate sources, or quality checks.
2. **Identify the plugin providing that goal** and its managed version; avoid confusing a Maven plugin with an application dependency.
3. **Check whether the plugin already runs via default lifecycle/parent.** If it is a new goal, add the plugin to `<build><plugins>`; if a goal is already bound, adjust only its configuration.
4. **Put shared versions/configs in `<pluginManagement>`** when multiple modules use it, leaving plugin activation to modules that need it.
5. **Configure executions clearly:** stable `id`, exact `goal`, right `phase` (or confirmed default phase); place execution-specific configuration inside the execution when needed.
6. **When inheriting Spring Boot starter parent, check the `repackage` execution before adding a new one.** Customize the existing execution using `id=repackage`.
7. **When importing only the Spring Boot BOM, manage required build plugins explicitly.** BOM dependency management does not substitute for plugin management.
8. **Inspect the effective POM and run the right phase.** Observe which goals actually execute, the final artifact filename, and test `java -jar` on the distributable artifact.

### Self-Check Questions

**Question 1:** A parent POM declares `maven-antrun-plugin` with goal `run` solely inside `<pluginManagement>`, while the child does not list the plugin in `<plugins>`. Does the custom goal run automatically during `mvn package`?

**Answer:** Not from management alone. The child must activate the plugin (or have another binding source) for a custom goal to run.

**Question 2:** Why can `maven-compiler-plugin` run even if the POM does not list it in `<plugins>`?

**Answer:** `jar` packaging has default lifecycle bindings, which include `compiler:compile`. This mechanism differs from management automatically adding a custom goal.

**Question 3:** The Spring Boot parent already manages the `repackage` execution with id `repackage`. To change the classifier to `exec`, should you create a new `id=make-exec` or reuse the existing id?

**Answer:** Use **`id=repackage`** to customize the inherited execution. A new id creates an additional execution and can cause the goal to run an extra time.

**Question 4:** A project only imports the `spring-boot-dependencies` BOM and declares `spring-boot-starter`. Can you conclude `mvn package` builds an executable JAR?

**Answer:** No. The BOM manages dependency versions; you need to configure the Spring Boot Maven Plugin and an appropriate `repackage` execution/binding.

**Question 5:** Can an execution without `<phase>` still run during `package`?

**Answer:** Yes, **if the goal defines `package` as its default phase**, such as `spring-boot:repackage`. For goals without a default phase or another binding, omitting phase may prevent them from running in the lifecycle.

**Question 6:** What does removing plugin-level `<configuration>` and placing separate configs inside executions with different ids enable?

**Answer:** It allows the same plugin to run multiple executions with different parameters; control ids and phases carefully to avoid unintended runs.

## Official References

- Maven, [Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): plugin configuration, executions, phases, and inheritance.
- Maven, [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): default lifecycle bindings and goal ordering.
- Maven, [POM Reference](https://maven.apache.org/pom.html): structure of `build`, `plugins`, `pluginManagement`, and `executions`.
- Spring Boot, [Using the Maven Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html): starter parent, BOM, and plugin configuration.
- Spring Boot, [Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html): `repackage`, execution ids, and packaging order.

**Takeaway:** **`plugins` determines which plugins are active; `pluginManagement` manages plugin versions and defaults; `execution` binds goals to phases and distinguishes runs by id.** To know what truly happens, inspect **effective POM + lifecycle bindings + Maven log + output artifact**.