# Consistently passing arguments, profiles, and managing plugin versions

## 1. Why manage build arguments and versions?

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring AOT prepares the Spring Boot application at build time, then GraalVM Native Image performs reachability analysis and compiles the native executable. The outcome depends on many inputs: JDK/GraalVM, Spring Boot, Native Build Tools, and Maven versions, profile configurations, properties, and compiler arguments.

If developer machines, CI, and builder containers each use a different set of inputs, the same commit can yield different results: a different Spring profile changes the bean graph, a different plugin version changes task behavior, or different build arguments alter how Native Image analyzes and links. Therefore, **deliberate and reproducible management of build inputs** is essential.

This lesson focuses on three areas:

- **Maven arguments:** `-P`, `-D`, `-pl`, `-am`, `-DskipTests`, debug flags, and how properties are passed.
- **Profiles:** Maven profiles control build configuration; Spring profiles control application configuration. They can interact during AOT, yet remain distinct mechanisms.
- **Plugin versions:** managing versions of Spring Boot Maven Plugin, GraalVM Native Build Tools, and supporting plugins; using parent/BOM/properties to reduce drift.

## 2. Common Maven argument types

Maven accepts several kinds of inputs passed in different ways:

| Syntax | Meaning | Example |
|---|---|---|
| `-P<id>` | Activate a Maven profile | `-Pnative` |
| `-Dname=value` | Set a Maven user property | `-DskipTests=true` |
| `-pl module` | Select project(s) in the reactor | `-pl service-api` |
| `-am` | Also build dependent projects in the reactor | `-pl service-api -am` |
| `-f path/pom.xml` | Select a specific POM | `-f app/pom.xml` |
| `-s settings.xml` | Use a specific settings file | `-s ci-settings.xml` |
| `-B` | Batch mode for CI | `-B` |
| `-X` | Detailed debug logging | `-X` |
| `-Dstyle.color=never` | Disable log colors (environment dependent) | `-Dstyle.color=never` |

Example CI native build command:

```bash
./mvnw -B -Pnative -DskipTests=false native:compile
```

`-DskipTests=false` explicitly states the intent to run tests if the project binds test checks to the corresponding lifecycle. However, invoking `native:compile` directly does not guarantee every test lifecycle phase ran; if test verification is required, run `verify` or a dedicated pipeline stage and inspect the actual executions.

Never treat `-DskipTests` as a default way to "fix" a native build. While debugging a compiler failure, you may skip tests temporarily, but you must re-run tests before accepting an artifact.

## 3. Maven properties and where values are defined

A property can be defined in multiple places: POM, parent POM, profiles, settings, command line, or environment variables read by plugins. For the same property name, exact precedence depends on property type and plugin handling; **user properties passed via `-D` are typically used to override POM properties**.

Example centralized version declaration:

```xml
<properties>
    <java.version>21</java.version>
    <spring-boot.version>3.x.y</spring-boot.version>
    <native-build-tools.version>0.x.y</native-build-tools.version>
</properties>
```

The version strings above are illustrative placeholders; replace them with real verified compatible releases. When using `spring-boot-starter-parent`, the Spring Boot version is usually declared directly in `<parent>`, and many dependencies/plugins are managed by the parent. Avoid creating duplicate version properties when the parent already manages that exact version.

Properties can be referenced inside plugin configuration:

```xml
<configuration>
    <imageName>${native.image.name}</imageName>
</configuration>
```

And passed at build time:

```bash
./mvnw -Pnative -Dnative.image.name=orders-service native:compile
```

How property substitution occurs depends on plugin configuration; not every GraalVM CLI flag automatically becomes a Maven property. You must declare the mapping inside plugin configuration if you want to control an option via `-D`.

## 4. Centralized plugin version management

A Spring Boot Native Image project usually relies on at least two key plugins:

- `org.springframework.boot:spring-boot-maven-plugin`: provides Spring Boot goals, including `process-aot`.
- `org.graalvm.buildtools:native-maven-plugin`: integrates the Native Image compiler with Maven.

You can centralize the Native Build Tools version:

```xml
<properties>
    <native-build-tools.version>0.x.y</native-build-tools.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>

        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
            <version>${native-build-tools.version}</version>
        </plugin>
    </plugins>
</build>
```

`0.x.y` is a placeholder, not a literal version. Pick a release compatible with your Maven, JDK/GraalVM, and Spring Boot versions. Spring Boot parent manages certain plugin versions, yet do not assume it always manages the exact Native Build Tools version your project needs.

In multi-module Maven builds, consider declaring versions in `pluginManagement` inside the parent POM so all modules share the same version:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.graalvm.buildtools</groupId>
                <artifactId>native-maven-plugin</artifactId>
                <version>${native-build-tools.version}</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Note: `pluginManagement` only manages default versions/configurations; a module must still declare the plugin under `build/plugins` for it to participate in the build. This is a common reason developers see a version in the parent yet no goals executing.

## 5. Maven profiles vs. Spring profiles

Two profile types have easily confused names:

| Profile type | Activation | Purpose |
|---|---|---|
| Maven profile | `-Pnative` | Selects plugins, executions, properties, and build configuration |
| Spring profile | `-Dspring.profiles.active=prod` or matching environment variable | Selects beans/configurations for the Spring application |

Example native build with a Maven profile:

```bash
./mvnw -Pnative native:compile
```

Example running a JVM application with a Spring profile:

```bash
java -Dspring.profiles.active=prod -jar target/orders.jar
```

During Spring AOT, Spring profiles/properties can affect the analyzed application context. If beans are enabled or disabled based on a Spring profile during AOT, generated code will reflect that configuration. Changing `SPRING_PROFILES_ACTIVE` when running the native binary does not necessarily restore a bean excluded from the context during the build.

You can pass Spring properties into the Maven process:

```bash
./mvnw -Pnative -Dspring.profiles.active=production native:compile
```

However, a property only affects Spring AOT if it reaches the right JVM/plugin process and is consumed by the Spring Boot plugin for AOT. Verify via logs, plugin configuration, and generated outputs; never assume every Maven user property is automatically forwarded.

## 6. Organizing the native profile in the POM

Condensed example of grouping native executions:

```xml
<profiles>
    <profile>
        <id>native</id>
        <properties>
            <spring.aot.enabled>true</spring.aot.enabled>
        </properties>
        <build>
            <plugins>
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

                <plugin>
                    <groupId>org.graalvm.buildtools</groupId>
                    <artifactId>native-maven-plugin</artifactId>
                    <version>${native-build-tools.version}</version>
                    <extensions>true</extensions>
                    <executions>
                        <execution>
                            <id>native-compile</id>
                            <goals>
                                <goal>compile-no-fork</goal>
                            </goals>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
```

This is an illustrative structure, not a mandatory configuration for all versions. A property like `spring.aot.enabled` only has an effect when the specific plugin/version reads it; do not add properties simply because their names look plausible. Always consult the Spring Boot Maven Plugin and Native Build Tools docs for your project's versions.

In supported integrated setups, the Spring Boot plugin and Native Build Tools coordinate executions, classpath, and AOT outputs automatically. When configuring manually, verify both **execution ordering** and **actual Native Image inputs**; merely declaring `dependsOn` or ordering does not prove generated classes/resources were passed properly.

## 7. Passing build arguments to GraalVM Native Image

You can configure build arguments inside the plugin instead of scattering them across shell scripts. Example:

```xml
<configuration>
    <buildArgs>
        <buildArg>--verbose</buildArg>
        <buildArg>--no-fallback</buildArg>
    </buildArgs>
</configuration>
```

Options must be checked against your GraalVM Native Image version. `--verbose` prints extra build details. `--no-fallback` instructs the build not to generate a fallback image in cases where the tool version supports fallbacks; exact behavior and availability depend on the GraalVM version. Never add options blindly just because you saw them in an old snippet.

If you want to control an option via a property:

```xml
<properties>
    <native.verbose>false</native.verbose>
</properties>

<configuration>
    <buildArgs>
        <buildArg>${native.build.arg}</buildArg>
    </buildArgs>
</configuration>
```

The snippet above requires defining `native.build.arg` and an explicit mapping. Another approach is a dedicated profile containing the verbose configuration. Never let an empty or malformed property produce invalid compiler arguments.

## 8. Maven Wrapper, settings, and CI environments

For reproducible builds, use the repository's Maven Wrapper:

```bash
./mvnw -version
```

The wrapper pins the Maven distribution, but it does not pin the JDK, GraalVM, or OS compiler/linker. CI pipelines should pin:

- Commit and Maven Wrapper distribution.
- JDK/GraalVM distribution, version, and architecture.
- Spring Boot parent/plugin versions.
- Native Build Tools plugin version.
- Builder image and OS development packages.
- Profiles and properties passed to the build.

When using private repositories or mirrors, supply settings files in a controlled way:

```bash
./mvnw -s ci-settings.xml -B -Pnative native:compile
```

Never commit credentials to `pom.xml` or shell history. Use CI secret stores and configure server IDs in Maven settings. When reporting builds, record profile names and versions without leaking tokens or passwords.

Maven local repository caches speed up downloads in CI, but caching is not proof that plugin versions are pinned. Your POM and wrapper must still declare explicit versions.

## 9. Inspecting effective configuration before building

When combining multiple parents, profiles, and properties, never guess the final configuration. Use the Maven Help Plugin:

```bash
./mvnw help:active-profiles -Pnative
./mvnw help:effective-pom -Pnative
./mvnw help:effective-settings
```

- `active-profiles`: shows which profiles are currently active.
- `effective-pom`: displays the POM after inheritance and profile resolution, including plugin versions and executions.
- `effective-settings`: shows resolved user/global settings; review carefully before sharing since it may contain internal details.

You can check specific plugin versions via the effective POM or plugin help. To inspect detailed execution logs:

```bash
./mvnw -Pnative -X native:compile
```

Debug logs can be huge and expose properties, file paths, or environment details. Enable only when needed and redact sensitive information before sharing.

## 10. Example of an explicit, parameterized CI command

A straightforward CI command might look like:

```bash
./mvnw -B -Pnative \
  -DskipTests=false \
  -Dnative.image.name=orders-service \
  native:compile
```

Conditions required for this command to behave as intended:

1. The `native` profile exists and declares the right executions/plugins.
2. The plugin configuration actually references the `native.image.name` property.
3. The Native Build Tools version is compatible with GraalVM and Maven.
4. The JDK used by Maven has Native Image and the OS toolchain ready.
5. Tests run in the proper lifecycle/CI stage; invoking the native goal directly does not replace `verify`.

In a release pipeline, a cleaner workflow separates stages: JVM tests, native build, native smoke/integration tests, verifying the binary in the runtime image, and finally publishing the artifact. This makes it clear which stage failed and prevents untested binaries from being released merely because compilation succeeded.

## 11. Common errors and how to handle them

| Symptom | Possible cause | How to inspect |
|---|---|---|
| `-Pnative` has no effect | Wrong profile ID, profile in another POM, or conditional activation | Run `help:active-profiles`, verify which POM is executed |
| `-D...` property does not change image name | Plugin does not reference that property or expects a different property name | Inspect plugin configuration / effective POM |
| Unexpected plugin version | Overridden by parent / `pluginManagement` / profile | Inspect effective POM |
| Plugin does not run despite being in `pluginManagement` | Plugin not declared under `build/plugins` | Declare the plugin in the module being built |
| Maven uses a different JDK than the shell | `JAVA_HOME`, toolchains, or CI environment | Run `./mvnw -version`, check toolchains |
| AOT picks the wrong beans/profile | Spring property did not reach AOT or wrong build config | Inspect AOT logs, Spring profiles, and generated output |
| Native compiler rejects an option | Option invalid for this version or malformed XML config | Check Native Image version and plugin help |
| Local and CI builds behave differently | Different versions, architecture, environment, or profiles | Record all inputs and diff effective POMs |

Always classify errors by layer: **Maven model/profile**, **plugin execution**, **Spring AOT**, **Native Image compiler/linker**, or **runtime**. Do not try to fix missing reflection metadata by altering Maven profiles if the profile was already applied correctly.

## 12. Hands-on exercise: standardizing the native build

**Context:** A Spring Boot application already has a working JVM baseline and needs a standardized native pipeline.

**Step 1 — Record input versions.** Capture Maven Wrapper version, JDK/GraalVM version, Spring Boot parent version, Native Build Tools version, OS, and architecture.

**Step 2 — Create the profile.** Use ID `native` and declare the Spring AOT and Native Build Tools executions per the docs for your active versions.

**Step 3 — Centralize versions.** Use parent/`pluginManagement`/properties appropriately. Remove duplicate version declarations and verify with the effective POM.

**Step 4 — Parameterize arguments.** Configure image name and build options via explicitly mapped properties. Document the exact CI command.

**Step 5 — Verify profile/configuration.** Run `help:active-profiles` and `help:effective-pom`; confirm active profiles, plugin versions, and executions.

**Step 6 — Build and test.** Run native compile, native smoke tests, compare endpoints against the JVM build, then measure readiness and RSS in the same environment.

Sample results table:

| Input/output | Value to record |
|---|---|
| Maven Wrapper | Version |
| JDK/GraalVM | Distribution, version, architecture |
| Spring Boot parent | Version |
| Native Build Tools | Version |
| Maven profile | Activated ID |
| Spring profile for AOT | Value and how it was passed |
| Native Image args | Actual list of flags |
| Artifact | Executable name and path |
| Testing | JVM/native pass-fail |
| Performance measurement | Readiness, RSS, workload, and iteration count |

## 13. Conclusion

Maven arguments, profiles, and plugin versions are critical inputs to the Spring Boot Native Image pipeline. **`-P` selects build configuration, `-D` passes properties, Spring profiles select application configuration, and plugin versions govern how Maven executes goals.** Using parent POMs and `pluginManagement` properly centralizes management, while inspecting the effective POM confirms the final resolved setup.

When building native, pin versions and environments, pass explicitly mapped parameters, verify Spring AOT receives the right configuration, and re-run your test suite on the native executable. That workflow keeps local and CI artifacts consistent while making startup and memory measurements explainable and reproducible.
