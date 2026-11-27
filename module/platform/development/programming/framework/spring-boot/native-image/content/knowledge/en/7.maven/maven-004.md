# Compiling native with the right Maven profile and goal configuration

## 1. Objective and three concepts to distinguish

In the **SPRING_BOOT_NATIVE_IMAGE** module, a Spring Boot application is processed by **Spring AOT** before GraalVM Native Image builds an executable. With Maven, how the build runs depends on profiles, plugins, and executions in `pom.xml`. Therefore, a command such as `mvn -Pnative native:compile` is only valid when the POM has configured the corresponding components.

- **Maven profile** is a group of configurations activated by name. `-Pnative` activates the profile named `native`; it is not a universal native flag Maven understands in every project.
- **Plugin goal** is an action provided by a plugin, such as `spring-boot:process-aot` or `native:compile`.
- **Lifecycle phase** is a stage in the build lifecycle such as `package`. A goal runs automatically in a phase only when an execution binds that goal to the phase.

This lesson shows how to choose the right command to build an executable directly, bind native compilation into the Maven lifecycle, or build a container image using Cloud Native Buildpacks.

## 2. The native processing chain in Maven

Conceptually, the process of producing a native executable consists of:

1. Maven reads profiles, plugins, dependencies, and executions.
2. Java sources and dependencies are compiled/prepared.
3. **Spring Boot Maven Plugin** runs `process-aot` to analyze the ApplicationContext and generate AOT code/metadata.
4. **GraalVM Native Build Tools Maven Plugin** provides Native Image integration goals and configures the classpath/reachability metadata.
5. GraalVM Native Image analyzes and compiles an executable for the target OS/CPU.

~~~mermaid
flowchart TB
    P["pom.xml: profiles, plugins, executions"] --> V["Maven activates profile and selects goal/phase"]
    V --> J["Compile Java + dependencies"]
    J --> A["Spring Boot: process-aot"]
    A --> G["AOT code and metadata"]
    G --> N["GraalVM Native Build Tools"]
    N --> I["GraalVM Native Image"]
    I --> E["Native executable"]
    P -. "plugin configuration" .-> A
    P -. "plugin configuration" .-> N
~~~

The diagram shows the logical relationships; actual ordering depends on plugin versions, the Maven lifecycle, and project executions. When using `spring-boot-starter-parent`, the Spring Boot Parent's `native` profile prepares key integrations, including AOT execution and default settings for Native Build Tools.

## 3. Checking the environment and POM

Native compilation requires a GraalVM JDK with compatible Native Image support in addition to Maven and Spring Boot configuration. On the build machine, check:

~~~bash
java -version
native-image --version
./mvnw --version
~~~

On Windows, you can use `mvnw.cmd --version`. If `native-image` is not found, install/select a GraalVM distribution with Native Image and configure `JAVA_HOME`/`PATH` properly. The native compiler also requires the corresponding OS toolchain, such as compiler/linker/SDK on macOS or Linux.

Common configuration example when using Spring Boot Parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>${spring-boot.version}</version>
    <relativePath/>
</parent>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

`${spring-boot.version}` is a placeholder for the Spring Boot version managed by the project. When using Spring Boot Parent, many plugin versions and defaults are already managed; do not add arbitrary versions without verifying compatibility. A real POM may also manage versions via properties or an internal parent.

**Key condition:** the plugins must be declared in the module containing the Spring Boot application. In multi-module Maven builds, library modules do not necessarily need to build their own native executables.

## 4. Common case: using spring-boot-starter-parent

If the project inherits from `spring-boot-starter-parent`, Spring Boot provides a profile named `native`. When activated, this profile:

- configures `process-aot` execution when the Spring Boot Maven Plugin is applied;
- prepares settings for native image / build image;
- provides defaults for Native Build Tools, such as using the appropriate raw classpath rather than mistaking it for the Spring Boot repackaged JAR;
- verifies a suitable GraalVM setup and supports fetching third-party reachability metadata.

Therefore, do not redeclare every execution manually if the project already uses Spring Boot Parent. The application module must declare both `spring-boot-maven-plugin` and `native-maven-plugin` to take advantage of the profile.

### 4.1. Building the executable directly with native:compile

When you want to produce the native executable on the build machine:

~~~bash
./mvnw -Pnative native:compile
~~~

| Component | Meaning |
| --- | --- |
| `./mvnw` | Project's Maven Wrapper, selecting the declared Maven version |
| `-Pnative` | Activates the Maven profile named `native` |
| `native:compile` | Invokes the `compile` goal of the `native` plugin prefix, typically `org.graalvm.buildtools:native-maven-plugin` |

The output is usually placed in `target/`; the default executable name is based on the artifact/project name or the configured `imageName` value. Check with:

~~~bash
ls -la target
~~~

On Windows, use `dir target`. Run the actual executable, for example:

~~~bash
./target/<executable-name>
~~~

Replace `<executable-name>` with the actual filename. This is a native binary for the build/target platform, not a JAR launched with `java -jar`.

### 4.2. Building via the Maven lifecycle with package

Another approach is binding the `compile-no-fork` goal of Native Build Tools to the `package` phase. Once the execution is configured, you can run:

~~~bash
./mvnw -Pnative package
~~~

Illustrative configuration example:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <version>${native.maven.plugin.version}</version>
    <extensions>true</extensions>
    <executions>
        <execution>
            <id>build-native</id>
            <phase>package</phase>
            <goals>
                <goal>compile-no-fork</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <mainClass>com.example.Application</mainClass>
        <imageName>billing-service</imageName>
    </configuration>
</plugin>
~~~

The version is a project-managed property; replace `com.example.Application` with your real main class. `extensions` enables the plugin to participate in Maven lifecycle/artifact handling extensions required by Native Build Tools.

**Never assume `package` always produces a native executable.** That only happens when a native execution is bound to this phase and the profile containing that execution is active. If the POM declares only the plugin without an execution, `./mvnw -Pnative package` may produce only a regular JAR. If Spring Boot Parent already manages the profile, inspect the effective configuration before adding an execution manually to avoid building native twice.

## 5. When not using spring-boot-starter-parent

Some projects inherit a corporate parent POM, import a BOM, or manage their own lifecycle. You cannot assume the `native` profile from Spring Boot Parent already exists.

In that case, you must configure the required parts yourself:

1. Attach the `process-aot` execution to `spring-boot-maven-plugin`.
2. Configure Native Build Tools and its executable-building goal (either invoke `native:compile` directly or bind `compile-no-fork` to an appropriate phase).
3. Integrate reachability metadata, such as the `add-reachability-metadata` goal of Native Build Tools.
4. Manage compatible versions of Spring Boot, Native Build Tools, and GraalVM.

Example AOT declaration:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>process-aot</id>
            <goals>
                <goal>process-aot</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Conceptual Native Build Tools configuration example:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <version>${native.maven.plugin.version}</version>
    <extensions>true</extensions>
    <executions>
        <execution>
            <id>reachability-metadata</id>
            <goals>
                <goal>add-reachability-metadata</goal>
            </goals>
        </execution>
        <execution>
            <id>build-native</id>
            <phase>package</phase>
            <goals>
                <goal>compile-no-fork</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <mainClass>com.example.Application</mainClass>
    </configuration>
</plugin>
~~~

This sample shows the goals to integrate, not a complete POM for every project. Check plugin versions, dependencies, execution ordering, and the actual classpath. If invoking `native:compile` directly, ensure AOT and metadata have already run beforehand or are integrated into the lifecycle.

### Declaring your own native profile

When not inheriting Spring Boot Parent, you can group the configuration in your own profile:

~~~xml
<profiles>
    <profile>
        <id>native</id>
        <build>
            <plugins>
                <!-- Place the corresponding Spring Boot AOT and Native Build Tools
                     executions inside this profile. -->
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Then `-Pnative` activates the project-defined profile. Keeping native configuration separate from JVM builds ensures developer machines do not run native compilation on every routine `mvn package`.

## 6. Choosing the right goal and packaging approach

The commands below are not interchangeable:

| Goal/command | Provider | Effect | When to use |
| --- | --- | --- | --- |
| `spring-boot:process-aot` | Spring Boot Maven Plugin | Runs Spring AOT alone on the application | Inspecting or diagnosing the AOT step |
| `native:compile` | GraalVM Native Build Tools | Invokes Native Image to compile the executable | Building native directly per plugin config |
| `native:compile-no-fork` | GraalVM Native Build Tools | Goal suitable for lifecycle binding without forking another lifecycle | Custom execution config, e.g., bound to `package` |
| `spring-boot:build-image` | Spring Boot Maven Plugin/Buildpacks | Creates a container image; builder can build a native executable inside container environment | Needing an image for container deployment |
| `mvn -Pnative package` | Maven lifecycle | Runs goals bound to the lifecycle inside the `native` profile | POM already has appropriate executions configured |

### 6.1. Running Spring AOT alone for diagnostics

~~~bash
./mvnw -Pnative spring-boot:process-aot
~~~

This goal isolates Spring AOT errors from GraalVM compiler errors. If AOT fails due to bean/condition configuration or initialization code, running `native:compile` afterward will not fix the root cause. The default generated output directory of Spring Boot Maven Plugin may lie under `target/spring-aot/main/`, containing sources, classes, and resources folders; the path can be configured in the plugin.

### 6.2. Building a container image with Buildpacks

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

This is the **container packaging** path. Spring Boot Maven Plugin coordinates Cloud Native Buildpacks; the builder image performs the steps required to produce the image. This differs from creating a local executable directly with `native:compile`. Check the Docker daemon, builder/run images, CPU platform, and resources allocated to the container engine.

If the goal is a local executable for benchmarking, `native:compile` is typically more direct. If the goal is a container deployment artifact, `build-image` is more appropriate.

## 7. How Maven profile and Spring profile affect AOT

Spring AOT prepares the ApplicationContext at build time, so conditions affecting the bean graph are evaluated in the build environment. For example:

~~~java
@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {
    @Bean
    @ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true"
    )
    AuditService auditService() {
        return new AuditService();
    }
}
~~~

If AOT runs with `feature.audit.enabled=false`, the bean may not be included in the AOT output. Changing the value to `true` when running the native executable will not automatically reconstruct the bean graph.

The Maven `native` profile is strictly a build profile. It is **not synonymous** with application Spring profiles such as `dev`, `staging`, or `prod`:

- `-Pnative` selects the Maven build configuration.
- `spring.profiles.active` or the corresponding Spring parameter selects the application profile.

Be explicit about which Spring profiles are used during AOT, especially if they alter the bean graph. Normal runtime values such as URLs, timeouts, or credentials are not automatically frozen just because AOT is used; distinguish values read at runtime from conditions that decide bean structure at build time.

## 8. Customizing Native Image via the Maven plugin

Native Build Tools lets you configure Native Image parameters in `pom.xml`. Example:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <imageName>billing-service</imageName>
        <verbose>true</verbose>
        <buildArgs>
            <buildArg>--no-fallback</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

This is an illustrative example; actual configuration may live inside the `native` profile or be managed by the parent. `--no-fallback` forces the build to fail if a true native image cannot be produced instead of generating a fallback image; understand each option's meaning before enabling it.

Reachability metadata can come from:

- Spring AOT and built-in integrated libraries;
- the metadata repository supported by Native Build Tools;
- native configuration files in the project's resources;
- hints registered by the application itself, e.g., `RuntimeHintsRegistrar`.

If the native executable fails on reflection or resources, identify where metadata is missing. Avoid blindly adding broad metadata or unnecessary build arguments by default.

## 9. Checking effective configuration and execution order

Before running a time-consuming build, check which profiles and plugins Maven actually activates:

~~~bash
# List active profiles.
./mvnw help:active-profiles -Pnative

# Display the inherited/merged POM configuration.
./mvnw help:effective-pom -Pnative -Doutput=target/effective-pom.xml

# Check the Maven/JDK environment.
./mvnw --version
~~~

`help:effective-pom` helps determine plugin versions, executions, and configurations inherited from the parent. You can open `target/effective-pom.xml` to inspect `process-aot`, `native-maven-plugin`, `compile-no-fork`, and related profiles. This is diagnostic output in `target`, not a source POM to edit.

When deep diagnostics are required:

~~~bash
./mvnw -Pnative -X native:compile
~~~

`-X` logs are very verbose and may include paths or sensitive configuration values; strip secrets/tokens before sharing logs.

## 10. Testing and error classification

A successful native build does not mean every feature is compatible:

| Stage | Error symptom | What to check first |
| --- | --- | --- |
| Maven profile | `No plugin found for prefix 'native'` or inactive profile | Whether plugin is declared, prefix mapping, and `-Pnative` spelling |
| Spring AOT | `process-aot` fails creating ApplicationContext | Spring config, build-time profiles/conditions, beans initialized at build time |
| Metadata | Missing reflection/resource/proxy config | Reachability metadata, runtime hints, and native-compatible dependencies |
| Native Image | `native-image` not found, compiler/linker failure, or build crash | GraalVM JDK, Native Image, OS toolchain, version compatibility |
| Native runtime | Binary starts but a business branch fails | Reflection, resources, serialization, proxies, JNI, and native tests |
| Container | Image build/run fails or wrong architecture | Docker/Buildpacks, builder/run image, target OS/CPU, and system libraries |

Run JVM tests for a baseline:

~~~bash
./mvnw test
~~~

Native Build Tools can support compiling and running tests on Native Image if native test execution and a compatible JUnit Platform setup are configured:

~~~bash
./mvnw -Pnative test
~~~

The command above only runs native tests if the corresponding execution is configured in the plugin/profile. When you want to skip native tests while still running JVM tests, Native Build Tools supports `-DskipNativeTests`; `-DskipTests` has broader scope and may skip JVM tests too.

Branches that should be tested include JSON binding, reflection, proxies/transactions, classpath resources, serialization, database connectivity, and conditionally configured features.

## 11. Complete hands-on workflow

Suppose a Spring Boot project named `billing-service` uses `spring-boot-starter-parent` and declares both `spring-boot-maven-plugin` and `native-maven-plugin` in the application module.

**Step 1 — confirm profile and toolchain**

~~~bash
./mvnw --version
java -version
native-image --version
./mvnw help:active-profiles -Pnative
~~~

**Step 2 — verify Spring AOT**

~~~bash
./mvnw -Pnative spring-boot:process-aot
~~~

If this command fails, check build-time Spring configuration and AOT logs. Do not jump to blaming the GraalVM compiler yet.

**Step 3 — compile the native executable**

~~~bash
./mvnw -Pnative native:compile
~~~

Check `target/`, the executable name, and Native Image logs. If the project configures a `compile-no-fork` execution in the `package` phase instead of invoking `native:compile` directly, use:

~~~bash
./mvnw -Pnative package
~~~

Only choose the second command when an execution is already bound to `package`. Do not run both assuming they are two mandatory steps.

**Step 4 — run and verify functionality**

~~~bash
./target/billing-service
~~~

The binary name is an example—replace it with the actual filename. Call HTTP endpoints and run test cases for resources/reflection/proxies. If the binary has a different name, check `imageName` and actual build outputs.

**Step 5 — package as a container if needed**

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Then run the container using the configured image name and inspect ports, health endpoint, and logs. This builds an image via Buildpacks; do not treat a local macOS executable as if it were a Linux binary.

## 12. Common Maven configuration pitfalls

### `-Pnative` has no effect

Maven may still build a JVM JAR because:

- the POM neither inherits `spring-boot-starter-parent` nor defines a `native` profile itself;
- the profile exists in another POM or only in an unactivated `settings.xml`;
- the native plugin/execution is not in the module being built;
- the plugin is inside `pluginManagement` without being declared/applied in the target module's `plugins`.

Verify using `help:active-profiles` and `help:effective-pom`.

### `native:compile` cannot find goal or plugin

Check whether `org.graalvm.buildtools:native-maven-plugin` is in the effective configuration, whether Maven recognizes the `native` prefix, and whether the plugin version is compatible with the current JDK/GraalVM. If necessary, invoke the plugin using full coordinates or configure it according to your Native Build Tools version guide.

### `process-aot` does not run

If using Spring Boot Parent, confirm `spring-boot-maven-plugin` is declared in the module. If using a custom parent, configure the `process-aot` execution yourself. An empty `native` profile will not generate AOT code on its own.

### Native Image runs but is missing classes or resources

Check reachability metadata and runtime hints. For resources accessed by dynamic names, confirm the resource actually exists in the inputs and is registered for Native Image packaging. For reflection, declare the exact classes/members required; do not rely on overly broad configuration as a default fix.

## 13. Quick reference for choosing commands

| Objective | Common command | Precondition |
| --- | --- | --- |
| Run AOT alone | `./mvnw -Pnative spring-boot:process-aot` | Spring Boot Maven Plugin and matching profile/config present |
| Build executable directly | `./mvnw -Pnative native:compile` | Native Build Tools plugin and matching Spring AOT config present |
| Build native in Maven lifecycle | `./mvnw -Pnative package` | `compile-no-fork` goal bound to the `package` phase |
| Build container image via Buildpacks | `./mvnw -Pnative spring-boot:build-image` | Spring Boot plugin, Buildpacks builder, and container engine ready |
| Check profile configuration | `./mvnw help:active-profiles -Pnative` | Maven Help Plugin available or downloadable |
| View resolved config after inheritance | `./mvnw help:effective-pom -Pnative` | Maven Help Plugin available or downloadable |

**Final rule:** profiles choose configurations, goals perform actions, and lifecycle phases determine when executions run. Reading the effective POM before picking commands reveals whether Spring AOT is wired into the native build, preventing confusion between building a JAR, a native executable, and a container image.

## References

- [Spring Boot Maven Plugin — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html): configuring `process-aot`, the `native` profile of `spring-boot-starter-parent`, and Native Build Tools integration.
- [Spring Boot — Developing Your First GraalVM Native Application](https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html): building executables, Maven Parent/plugin requirements, the `native:compile` goal, and Buildpacks.
- [GraalVM Native Build Tools — Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin.html): plugin configuration, goals, metadata, and native tests.
- [GraalVM Native Build Tools — End-to-End Maven Guide](https://graalvm.github.io/native-build-tools/latest/end-to-end-maven-guide.html): plugin examples, binding `compile-no-fork` to `package`, building and running the executable.
