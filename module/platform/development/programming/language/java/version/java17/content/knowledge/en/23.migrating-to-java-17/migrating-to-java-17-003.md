# Upgrading Build Tools and Libraries to JDK 17-Compatible Versions

**Topic:** Java 17 → Migrating to Java 17  
**Focus:** Upgrading Gradle/Maven, build plugins, test frameworks, annotation processors, bytecode analysis libraries, and application frameworks to JDK 17-compatible versions; configuring toolchains and compiler release for reproducible builds; verifying compilation, testing, packaging, and runtime environments.

Upgrading an application to Java 17 is not merely changing JAVA_HOME or adding the --release 17 flag. A Java project typically involves multiple components running across different JVMs: the build tool, compiler, test runner, annotation processors, plugins, coverage tools, bytecode libraries, and the packaged application itself. If even one legacy component does not understand JDK 17 class files or APIs, the build can fail even when the application source code has no issues.

The upgrade process should verify three compatibility layers:

1. **The build runs on JDK 17:** Gradle/Maven and their plugins must start, execute tasks, and access JDK 17 properly.
2. **Tooling handles Java 17:** compilers, test frameworks, annotation processors, bytecode libraries, agents, and analysis tools must understand the required syntax, class files, and APIs.
3. **The application runs on JDK 17:** all direct and transitive dependencies must be runtime-compatible; module configuration, reflection, TLS, logging, and system integrations must also be verified.

Do not look solely at the JDK version listed in a library's description. Determine which phase the library runs in, what bytecode version it targets, whether it uses JDK internals, and which release is confirmed as supported by the vendor.

## 1. Distinguish build JDK, compile JDK, and runtime JDK

A project may use multiple Java versions for different purposes:

| Component | Role | Question to verify |
| --- | --- | --- |
| JVM running Gradle/Maven | Runs the build daemon, plugins, and build tool tasks. | Does the build tool run on JDK 17? |
| JDK toolchain/compiler | Provides javac and compilation tools. | Is the compiler JDK 17? |
| --release | Constrains language level, platform APIs, and target bytecode. | Does code strictly use only Java 17 APIs? |
| JVM running tests | Executes unit/integration tests and agents. | Do forked test JVMs use JDK 17? |
| Runtime JVM | Runs the application in containers, VMs, or servers. | Do all dependencies run on JDK 17? |
| IDE JDK | Runs the IDE or Gradle/Maven integration inside the IDE. | Do IDE builds use the same configuration as CI? |

Check the current environment:

~~~shell
java -version
javac -version
mvn -version
gradle --version
~~~

If the project uses Maven Wrapper or Gradle Wrapper, check the wrappers as well:

~~~shell
./mvnw -version
./gradlew --version
~~~

On Windows, use mvnw.cmd and gradlew.bat. Output from mvn -version or gradle --version typically shows the JVM running the build tool; it does not prove compiler/test tasks use that same JDK if the project configures a separate toolchain.

### 1.1. Why changing JAVA_HOME alone is not enough

JAVA_HOME usually affects the default JVM of command-line tools. However:

- Gradle may use a different JVM for its daemon or have a separate Gradle JVM configured by the IDE.
- Gradle toolchains may select a different JDK for compiling, testing, and generating Javadoc.
- Maven Toolchains may select a compiler JDK independently of the JVM running Maven.
- Surefire/Failsafe may fork separate JVMs to run tests.
- Plugins may run inside the build tool JVM, in a forked JVM, or via a native executable.
- CI/containers may have multiple JDKs installed and select a different one than developer machines.

Therefore, specify the JDK explicitly for each phase and verify actual build output.

## 2. Build tool compatibility milestones

### 2.1. Gradle

Per the official compatibility matrix:

- **Gradle 7.3** is the first release supporting running Gradle on JDK 17.
- Gradle 7.3 also supports Java 17 toolchains.
- Gradle 9 requires JDK 17 or higher to run Gradle itself.
- Running Gradle on one JDK and compiling/testing on another JDK are managed separately via toolchains.

Consequently, Gradle older than 7.3 is not suitable for running builds on JDK 17. However, 7.3 is only the historical minimum compatibility milestone; it does not mean all current plugins or frameworks still support Gradle 7.3. Choose a maintained Gradle release that satisfies the compatibility matrix of your project's core plugins.

Verify:

~~~shell
./gradlew --version
./gradlew wrapper --gradle-version 9.9.1
./gradlew --stop
./gradlew --version
~~~

The wrapper update command is just an example using a current Gradle version; before applying it, check whether your project's plugins, Android Gradle Plugin, Kotlin plugin, and convention plugins are compatible with the chosen version. Avoid upgrading Gradle across major versions simultaneously with multiple major plugins unless you have a reliable test suite.

### 2.2. Maven

Maven core and Maven Compiler Plugin are two separate components:

- Maven 3.9.x can run on JDK 17.
- Maven Compiler Plugin should have its version pinned and release configured explicitly.
- Test plugins, Javadoc plugin, enforcer, shade, code quality, and other plugins each have their own release lifecycles.

Current Apache Maven documentation recommends using maven.compiler.release and pinning maven-compiler-plugin; current examples use Compiler Plugin 3.16.0. This plugin supports configuring release 17. For Maven projects, use Maven Wrapper so every developer and CI runner uses the exact same Maven distribution.

Verify:

~~~shell
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
~~~

help:effective-pom reveals the effective plugin configuration after inheritance from the parent POM and profiles; dependency:tree identifies which library versions were selected after Maven resolves dependencies.

### 2.3. Do not choose a build tool solely by a minimum version number

The Gradle 7.3 milestone indicates Gradle can run on JDK 17, but a newer framework may require Gradle 8.14 or 9.x. Similarly, Maven core may run on JDK 17 while an older plugin calls internal javac APIs or fails to parse newer class files.

For example, Spring Boot 3.5.x requires Java 17 and publishes its own build tool requirements; Spring Boot 4.1.x also requires Java 17 but mandates Gradle 8.14+ or 9.x. When upgrading a framework, read the system requirements of the exact framework version selected rather than inferring them from JDK requirements alone.

## 3. Configure the compiler to truly target Java 17

The JDK running the compiler and the Java version supported by its output are two separate decisions. If you want to compile with JDK 17 and produce an application targeting JDK 17, configure release 17.

### 3.1. Why use --release?

javac --release 17 simultaneously constrains:

- Supported Java language syntax/features.
- Generated class file version.
- The set of public Java SE APIs source code may reference.

Setting only -source 17 and -target 17 does not guarantee code avoids APIs introduced only in newer JDKs. --release validates against the target release's platform APIs as well.

Java 17 uses class-file major version **61**. If a library is compiled for a newer JDK, JVM 17 cannot load that class and throws UnsupportedClassVersionError.

### 3.2. Combining toolchains with release

Toolchains select the compiler JDK; release constrains the target APIs and bytecode. When targeting Java 17, both should be 17:

~~~text
JDK toolchain 17
       |
       v
     javac
       |
       | --release 17
       v
Class file version 61
       |
       v
Runtime JDK 17
~~~

This configuration is much more explicit than relying on the default JDK of a developer laptop or CI machine.

## 4. Upgrade and configure Gradle

### 4.1. Update the Gradle Wrapper

Gradle Wrapper stores the distribution version in gradle/wrapper/gradle-wrapper.properties. For example:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.1-bin.zip
~~~

The wrapper ensures all environments use the same Gradle version:

~~~shell
./gradlew --version
./gradlew clean build
~~~

Commit both the wrapper scripts and the distribution properties file to source control. In CI, invoke the wrapper instead of a globally installed Gradle on the runner.

### 4.2. Configure Java toolchain and release in Groovy DSL

In build.gradle:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

toolchain instructs Gradle to locate JDK 17 for supported Java tasks. options.release restricts APIs/bytecode to Java 17. useJUnitPlatform() enables JUnit Platform if the project uses JUnit Jupiter or a compatible engine.

### 4.3. Kotlin DSL

In build.gradle.kts:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

tasks.test {
    useJUnitPlatform()
}
~~~

If the project uses Kotlin, Scala, or Groovy, configure their respective compilers/toolchains accordingly. The java toolchain block does not automatically guarantee third-party plugins use the same JDK if those plugins do not integrate with Gradle toolchains.

### 4.4. Inspect Gradle daemon and toolchains

Useful commands:

~~~shell
./gradlew --version
./gradlew javaToolchains
./gradlew buildEnvironment
./gradlew dependencies
./gradlew dependencyInsight --dependency byte-buddy
~~~

- --version reports the JVM running Gradle.
- javaToolchains lists JDKs detected by Gradle.
- buildEnvironment displays buildscript/plugin classpath dependencies.
- dependencies displays dependencies across configurations.
- dependencyInsight explains why a particular dependency version was resolved.

After changing toolchains or the daemon JVM, stop the daemon so subsequent builds start fresh:

~~~shell
./gradlew --stop
~~~

Do not treat org.gradle.java.home as a substitute for toolchains in all cases. That property controls the JVM running Gradle; toolchains control the JDK used for compile/test/javadoc tasks.

## 5. Upgrade and configure Maven

### 5.1. Use Maven Wrapper

Maven Wrapper pins the Maven version for the project. Build commands should run via:

~~~shell
./mvnw -version
./mvnw clean verify
~~~

The wrapper prevents CI and developers from accidentally using different Maven versions. A compatible JDK must still be installed; the wrapper does not ensure every plugin uses the right compiler JDK unless the project configures toolchains.

### 5.2. Configure Maven Compiler Plugin

Example relevant section in pom.xml:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <junit.version>6.0.3</junit.version>
</properties>

<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
                <configuration>
                    <release>17</release>
                    <encoding>UTF-8</encoding>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.6.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

This is an example configuration; if a parent POM already manages plugin versions, update them in the appropriate place rather than duplicating declarations. Pinning plugin versions prevents builds from silently changing when Maven or the parent POM is updated.

### 5.3. Add JUnit Jupiter

If the project uses JUnit 6:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>6.0.3</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

JUnit 6 requires Java 17 as its baseline. JUnit 5 still supports Java 8 and higher and runs on JDK 17; therefore **you do not have to upgrade JUnit 5 to JUnit 6 merely to run an application on Java 17**. Only jump major versions when the project is ready to handle the changes in the migration guide.

Maven Surefire/Failsafe needs a version supporting the JUnit Platform and engine your project uses. Surefire 3.6.x supports running JUnit Platform with Jupiter/Vintage and TestNG via the corresponding providers. Keep the platform, engine, and plugin versions aligned.

### 5.4. Use Maven Toolchains

Maven Toolchains allow Maven to run on one JDK while toolchain-aware plugins use another JDK. This is helpful when developers have multiple JDKs or an organization's Maven runtime is managed separately.

Example configuration in POM:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>3.3.0</version>
            <executions>
                <execution>
                    <goals>
                        <goal>toolchain</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <toolchains>
                    <jdk>
                        <version>17</version>
                    </jdk>
                </toolchains>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

On the build machine, ~/.m2/toolchains.xml declares installed JDKs:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Replace jdkHome and vendor with the actual installation on your environment. The version in provides must match the criteria requested by the POM; Maven Toolchains does not verify on its own that a directory labeled 17 genuinely contains JDK 17. Build environment administration must still guarantee that.

### 5.5. Distinguish Maven runtime from toolchain

mvn -version reports the JVM running Maven. Maven Toolchains can select JDK 17 for compiler/test plugins without changing that JVM. If you want all of Maven and its plugins to run directly on JDK 17, configure JAVA_HOME/the runner accordingly and verify again with mvn -version.

## 6. Upgrade test frameworks and test plugins

A test stack typically consists of several layers:

1. Test authoring APIs such as JUnit Jupiter or TestNG.
2. Test execution engines such as Jupiter Engine, Vintage Engine, or TestNG engine.
3. Launcher/platform orchestrating test discovery and execution.
4. Build plugins such as Maven Surefire/Failsafe or Gradle Test.
5. Agents, mocking libraries, and instrumentation loaded in the test JVM.

These layers must be compatible with each other and with JDK 17.

### 6.1. JUnit 5 vs. JUnit 6

| Line | Java requirement | When to use |
| --- | --- | --- |
| JUnit 5 | Java 8 or higher | Projects wanting to stay compatible with older JDKs while running tests on JDK 17. |
| JUnit 6 | Java 17 or higher | Projects that have chosen Java 17 as baseline and are ready for major migration work. |

JUnit 6 unifies Platform/Jupiter/Vintage version numbers and removes several legacy APIs/modules. If upgrading from JUnit 5, read the migration guide and review extensions, engines, test runners, and IDE integrations.

### 6.2. Maven Surefire and Failsafe

- Surefire runs unit tests during the test lifecycle phase.
- Failsafe runs integration tests during the integration-test and verify phases.
- Both require versions compatible with JUnit Platform, TestNG, or whichever framework is in use.

If tests are not discovered, do not just swap JUnit versions. Check the selected provider, discovery class naming conventions, forked JVM settings, and reports in target/surefire-reports or target/failsafe-reports.

### 6.3. Mockito, Byte Buddy, and mocking/instrumentation

Mockito and several mocking frameworks rely on Byte Buddy to generate classes or instrument bytecode. As the JDK advances, these libraries must understand newer class files and avoid encapsulated internal APIs.

If you encounter errors such as Unsupported class file major version, IllegalAccessError, InaccessibleObjectException, or agent attachment failures, inspect the underlying Byte Buddy/ASM dependencies as well. Avoid overriding a transitive dependency with an arbitrary version if the framework already manages compatible versions.

## 7. Upgrade annotation processors and compiler extensions

Annotation processors run during compilation, typically inside the compiler JVM. They may depend on:

- javax.annotation.processing and javax.lang.model.
- Internal details of javac.
- ASTs or compiler internals.
- APIs for generating source code, class files, or metadata.

Common libraries include Lombok, MapStruct, QueryDSL, Error Prone, Checker Framework, and custom project processors.

### 7.1. Lombok

Lombok integrates deeply with the compiler. Version **1.18.22** was the milestone announcing JDK 17 support. That is a historical minimum for spotting overly old dependencies; it should not be treated as the version to stay on today. Choose a currently maintained Lombok release compatible with your project's JDK/compiler and IDE.

After upgrading, check:

- Does the Maven/Gradle compiler load the right Lombok annotation processor?
- Does the IDE have a compatible Lombok plugin?
- Do command-line builds and IDE builds generate identical code?
- Are annotations on records or sealed types properly supported in the version used?

### 7.2. MapStruct and other processors

For processors generating mappers or code, check release notes for JDK 17 and compiler compatibility. If a processor supports only older JDKs, errors can occur at compile time even when the runtime library has no issues.

In Maven, declare processors in annotationProcessorPaths of the Compiler Plugin when the project needs separate processor path control. In Gradle, use the annotationProcessor configuration. Avoid placing processors on the runtime classpath just so the compiler can find them.

### 7.3. Inspect the processor path

Maven:

~~~shell
./mvnw dependency:tree -Dscope=compile
./mvnw help:effective-pom
~~~

Gradle:

~~~shell
./gradlew dependencies --configuration annotationProcessor
./gradlew dependencyInsight --dependency lombok --configuration annotationProcessor
~~~

If a processor runs inside a forked compiler, confirm the actual forked JDK. Having the build tool run on JDK 17 does not guarantee a separate compiler executable is also JDK 17.

## 8. Upgrade bytecode manipulation and instrumentation libraries

Java 17 generates class file major version 61. Libraries that read, analyze, modify, or generate bytecode must understand this class file version and any new constructs the compiler emits.

Components to check:

- ASM.
- Byte Buddy.
- Javassist.
- CGLIB or proxy libraries.
- Mockito and mocking frameworks.
- JaCoCo and coverage agents.
- APM/profiling/security agents.
- Obfuscation, shading, weaving, or enhancement tools.

Several published Java 17 support milestones:

| Component | Noted Java 17 support milestone | How to apply |
| --- | --- | --- |
| ASM | 9.1 added JDK 17 support. | Use the version supported by dependent libraries; avoid forcing ASM directly if frameworks shade or manage their own version. |
| Byte Buddy | 1.10.19 added Java 17 class file support. | Check the version pulled in by Mockito, agents, or plugins. |
| JaCoCo | 0.8.8 officially supported Java 17. | Use a current maintained release; 0.8.8 is only the historical minimum. |

As of 2026, these projects have released many newer versions beyond their initial milestones. Pick a currently maintained release with the latest bug fixes and security patches within a branch compatible with your application; do not pin to the very first release that added Java 17 support.

### 8.1. Coverage agents and class instrumentation

The JaCoCo agent loads into the test JVM or application JVM. If the agent cannot parse class files or transforms bytecode improperly, tests can fail before application code runs.

When upgrading JaCoCo:

- Update both the Maven/Gradle plugin and the corresponding agent/runtime.
- Verify report goals/tasks use the same version.
- Verify compatibility with the Kotlin compiler, records, sealed classes, and generated code.
- Re-run unit tests, integration tests, and report generation.

### 8.2. Do not check direct dependencies only

For example, a project might not declare ASM directly, yet Mockito or a bytecode plugin pulls ASM in. If dependency resolution picks an overly old version, errors still happen. Use dependency trees and dependency insight to trace the true origin of resolved versions before making changes.

## 9. Upgrade frameworks and application libraries

A successful build does not prove all runtime dependencies are compatible. Read your core framework's system requirements and inspect transitive dependencies.

### 9.1. Spring Boot

Spring Boot 3.x sets Java 17 as the minimum requirement. Newer Spring Boot lines also publish their own build tool matrices; for example, Spring Boot 4.1.x requires Java 17, Maven 3.6.3+, and Gradle 8.14+ or 9.x. Spring Boot 3.5.x also requires Java 17, though with different published Gradle versions.

When upgrading from Spring Boot 2.x to 3.x or newer, anticipate major changes beyond the JDK:

- Migrating many Java EE APIs from `javax.*` namespaces to `jakarta.*`.
- Updating Spring Framework, Hibernate, servlet containers, and starters.
- Reviewing security configuration, validation, persistence, and integration libraries.
- Auditing third-party starters that do not yet support the new major version.

Do not bump only the Spring Boot parent while ignoring the compatibility matrix of starters and plugins.

### 9.2. Dependency categories to audit

| Category | Examples to check | Why |
| --- | --- | --- |
| Web/framework | Spring, Jakarta APIs, servlet containers, REST clients | JDK and platform API requirements can change across major releases. |
| Persistence | Hibernate, JDBC drivers, migration tools | May rely on reflection, bytecode enhancement, or native drivers. |
| Serialization | Jackson, JAXB, Kryo, protobuf | May rely on reflection, generated code, or class metadata. |
| Logging | Logback, Log4j, SLF4J bindings | APIs and implementations must align; old agents/bridges can conflict. |
| Network/security | Netty, TLS providers, crypto providers | May depend on native libraries, module access, or security providers. |
| Cloud/messaging | Kafka, AMQP, cloud SDKs | Must verify runtime support and dependency alignment. |
| Database | JDBC drivers, pools, ORMs | Drivers must support JDK 17 and the corresponding database/server version. |
| Observability | APM agents, tracing, metrics | Agents frequently instrument classes and may require JDK-compatible builds. |

For each group, verify minimum supported Java version, maximum tested Java version, module/reflective access, native dependencies, and release notes. "Runs on Java 17" does not equate to "vendor-supported in production."

## 10. Manage dependencies and plugins with control

### 10.1. Create an inventory

Record:

- Build tool and wrapper versions.
- Plugin versions and buildscript dependencies.
- Direct runtime dependencies.
- Transitive runtime dependencies.
- Test-only dependencies.
- Annotation processors.
- Agents and native tools.
- Container base image and JDK distribution.

Do not scan only pom.xml or build.gradle; plugins may be declared in a parent POM, version catalog, pluginManagement, convention plugins, or custom build logic.

### 10.2. Use BOMs and dependency constraints

A BOM (Bill of Materials) aligns artifacts within an ecosystem, such as Spring Boot dependency management or the JUnit BOM. In Gradle, version catalogs and constraints centralize version management.

Do not force every library onto a single arbitrary version just to silence an error. Use versions supported by your frameworks/plugins, inspect dependency convergence reports, and avoid mixing incompatible major versions.

### 10.3. Distinguish plugin dependencies from application dependencies

Plugins load into the build tool's classloader, whereas application dependencies are packaged or placed onto the application's runtime classpath. These two groups can share the same library name yet require different versions.

For instance, ASM inside a build plugin may differ from ASM inside the application. When encountering NoSuchMethodError or ClassNotFoundException, identify the classloader and dependency graph of the exact failing phase.

### 10.4. Use dependency trees to trace origins

Maven:

~~~shell
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.ow2.asm:asm
./mvnw dependency:tree -Dincludes=net.bytebuddy:byte-buddy
~~~

Gradle:

~~~shell
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency asm --configuration runtimeClasspath
./gradlew dependencyInsight --dependency byte-buddy --configuration testRuntimeClasspath
~~~

Switch configurations to match the target scope: compileClasspath, runtimeClasspath, testRuntimeClasspath, annotationProcessor, or buildscript/plugin classpath.

## 11. Check whether libraries contain bytecode newer than Java 17

JVM 17 cannot load class files compiled for newer Java versions. Java 17 uses major version 61; a library compiled for Java 21, for instance, has major version 65 and will not run on JVM 17.

You can inspect a class file using:

~~~shell
javap -verbose -classpath library.jar com.example.SomeClass
~~~

Look for the major version line. For JDK 17, target class files must not exceed 61 unless the JAR is multi-release and runtime 17 selects an appropriate base/versioned entry.

### 11.1. Multi-release JARs

A JAR can contain classes targeting multiple Java releases under META-INF/versions/. The JVM selects entries matching the active runtime. Therefore, inspecting a single class entry or top-level JAR metadata may be insufficient; check the Multi-Release: true manifest attribute and archive structure.

Dependency analysis tools such as jdeps accept --multi-release 17 to analyze entries corresponding to the target release in multi-release JARs.

### 11.2. Check JDK internals

A library may compile yet access JDK internal packages via reflection or bytecode. Java 17 enforces strong encapsulation on internal components. Run:

~~~shell
jdeps --jdk-internals --recursive path/to/application.jar
~~~

Specify the classpath or module path for dependencies when widening analysis scope. Because jdeps is static analysis, it can miss reflection using dynamically constructed class names, native code, and dependencies outside the scanned scope. Combine it with integration tests on JDK 17 and runtime log inspection.

## 12. Verify CI, container, and IDE configurations

### 12.1. CI must use the same JDK and wrapper

The pipeline should:

- Install an organization-approved JDK 17 distribution.
- Invoke ./gradlew or ./mvnw rather than an uncontrolled global build tool.
- Run compilers and tests using the declared JDK/toolchain.
- Cache dependencies keyed by wrapper and avoid reusing caches from mismatched environments.
- Execute unit tests, integration tests, packaging, and smoke tests.
- Log the active JDK and build tool versions in build output.

Example general verification steps:

~~~shell
java -version
./gradlew --version
./gradlew clean test
./gradlew check
~~~

Or Maven:

~~~shell
java -version
./mvnw -version
./mvnw clean verify
~~~

### 12.2. Container images

Check the JDK/JRE in both the build image and runtime image. A multi-stage Docker build might compile with JDK 17 yet accidentally copy the artifact into a runtime image carrying an older JRE or a different vendor.

Example:

~~~dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace
COPY . .
RUN ./gradlew clean build

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/app.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

Image tags shown here are examples. In production, pin an image digest or specific patch tag per your organization's security patching process, and align build/runtime vendors and support policies as needed.

### 12.3. IDE

Configure:

- Project SDK/language level matching Java 17.
- Gradle JVM or Maven runner JDK matching the build tool.
- Compiler/toolchain aligned with the project configuration.
- Compatible IDE versions of annotation processors and plugins.

If terminal builds pass while the IDE fails, check which JDK the IDE uses to run Gradle/Maven and inspect annotation processing settings. Conversely, if the IDE builds while CI fails, inspect the wrapper, toolchain provisioning, environment variables, and plugin versions on the runner.

## 13. Common errors when upgrading to JDK 17

| Error / message | Common cause | Resolution |
| --- | --- | --- |
| Unsupported class file major version 61 | Old bytecode parser/plugin cannot parse Java 17 class files. | Upgrade ASM/Byte Buddy/Javassist or the plugin bundling them. |
| UnsupportedClassVersionError | Dependency compiled for a JDK newer than runtime 17. | Pick an artifact with Java 17-compatible bytecode or use the required runtime. |
| invalid target release: 17 | Actual compiler is too old or the build selected the wrong JDK. | Check the toolchain and compiler executable. |
| InaccessibleObjectException | Library uses reflection to access an encapsulated package/member. | Upgrade the library; if temporary transition is needed, open the exact package under control and plan removal. |
| IllegalAccessError | Link to a type/member no longer accessible under module/access rules. | Identify the module/package, update the dependency, or adjust the module descriptor. |
| NoSuchMethodError | Runtime dependency version differs from what a plugin/framework expects. | Inspect the dependency tree, BOM, and classloaders; align versions. |
| NoClassDefFoundError | Missing class or prior class initialization failure. | Inspect the first root cause in logs, runtime dependencies, and JDK-specific code paths. |
| Lombok/processor compile failure | Old processor relies on javac internals or lacks JDK 17 support. | Upgrade the processor and reconfigure the processor path. |
| Tests not discovered | Incompatible Surefire/Failsafe/provider or JUnit engine. | Check plugin versions, engines, and test discovery rules. |
| Coverage report failure | Old JaCoCo/ASM cannot parse new class files or instrumentation. | Upgrade JaCoCo and its plugin/agent together. |
| Terminal and IDE builds disagree | Different JVMs, toolchains, wrappers, or annotation processors in use. | Align JDKs and build configurations. |
| App runs locally but fails in container | Runtime image uses a different JRE/JDK or lacks native dependencies. | Inspect the actual image, java -version, modules, and native libraries. |

### 13.1. Do not use --add-opens to mask every error

--add-opens can let some legacy libraries continue performing deep reflection during transition. However, it does not:

- Make old bytecode parsers understand newer class files.
- Fix UnsupportedClassVersionError.
- Resolve dependency version conflicts.
- Turn JDK internal APIs into supported APIs.
- Fix every missing module readability or native access issue.

If temporary package opening is needed, document the module/package/consumer, keep scope minimal, and track an issue to upgrade the library. The long-term solution is using library versions that support JDK 17.

## 14. Step-by-step upgrade workflow

A controlled roadmap makes it easy to identify which change broke the build:

### Step 1: Snapshot the current state

Record JDK, Maven/Gradle, wrapper, plugin, framework, test framework, annotation processor, agent versions, and the dependency tree. Save current build logs as a baseline.

### Step 2: Upgrade the build tool and wrapper

Select a Gradle/Maven version supported on JDK 17 and compatible with your plugins/frameworks. Pin the wrapper and verify the build tool boots before changing numerous dependencies.

### Step 3: Switch the compiler to Java 17

Configure the JDK 17 toolchain and --release 17. Confirm main source, test source, generated source, and modules compile cleanly at that release.

### Step 4: Upgrade build plugins

Prioritize compiler, test, Javadoc, coverage, code quality, packaging, shading, enhancement, and deployment plugins. Check which JVM each plugin runs in and its JDK 17 support.

### Step 5: Upgrade the test stack and annotation processors

Align JUnit/TestNG, engines, Surefire/Failsafe or Gradle Test; upgrade Lombok/MapStruct and other processors; run a small test subset early to catch compile or test discovery failures.

### Step 6: Upgrade bytecode libraries and agents

Review ASM, Byte Buddy, Javassist, JaCoCo, mocking frameworks, APM/security agents, and instrumentation tools. Check both transitive dependencies and plugin classpaths.

### Step 7: Upgrade frameworks and runtime dependencies

Review compatibility matrices for frameworks, database drivers, ORMs, messaging, web servers, logging, and cloud SDKs. Address breaking changes per major release.

### Step 8: Run builds and tests on JDK 17

Run clean builds, unit tests, integration tests, coverage, packaging, smoke tests, and dependency checks. Do not stop at compilation.

### Step 9: Verify images and deployment environments

Ensure containers/VMs run the intended JDK 17 and that startup commands, agents, module flags, native libraries, and environment variables are updated.

### Step 10: Test under load and monitor

Compare startup time, memory, GC, latency, throughput, connection errors, and logs. Cut over completely only after critical business flows are verified in a production-like environment.

## 15. Sample compatibility matrix

The table below lists published reference milestones; they do not replace the compatibility matrix for your project's exact versions:

| Component | Noted JDK 17 support milestone | Notes |
| --- | --- | --- |
| Gradle | 7.3 | First release running Gradle on JDK 17; Gradle 9 requires JDK 17 as minimum runtime. |
| Maven Compiler Plugin | 3.16.0 as current example | Configure release=17; pin plugin version. |
| JUnit 5 | Java 8+ | Can continue to be used on JDK 17. |
| JUnit 6 | Java 17+ | Choose when ready for major migration. |
| Lombok | 1.18.22 | First milestone announcing JDK 17 support; use a currently maintained release. |
| ASM | 9.1 | JDK 17 support milestone; upgrade alongside libraries using ASM. |
| Byte Buddy | 1.10.19 | Added Java 17 class file support; check transitive versions. |
| JaCoCo | 0.8.8 | First release officially supporting Java 17; prefer newer maintained versions. |
| Spring Boot | 3.0+ | Java 17 is baseline for 3.x; newer lines have separate build tool requirements. |

When selecting versions:

1. Prefer stable, actively maintained releases.
2. Check minimum and maximum supported JDK runtimes.
3. Check Gradle/Maven plugin compatibility.
4. Inspect the dependency tree and BOMs.
5. Read release notes/migration guides for major changes.
6. Verify with actual builds and tests on JDK 17.

Avoid upgrading all dependencies to latest simultaneously if the project uses multiple major frameworks. Upgrade in coupled dependency groups and preserve before/after version records for easy rollback.

## 16. Consolidated verification commands

### Gradle

~~~shell
java -version
./gradlew --version
./gradlew javaToolchains
./gradlew buildEnvironment
./gradlew dependencies
./gradlew clean check
./gradlew test
~~~

### Maven

~~~shell
java -version
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw clean verify
~~~

### Bytecode and JDK internals

~~~shell
javap -verbose -classpath path/to/library.jar com.example.SomeClass
jdeps --multi-release 17 --jdk-internals --recursive path/to/application.jar
~~~

If dependencies live outside the input JAR, supply --class-path or --module-path as needed. jdeps does not replace runtime tests, especially for reflection and dynamic class loading.

## 17. Common mistakes

| Mistake | Why it is insufficient | Right approach |
| --- | --- | --- |
| Only changing JAVA_HOME | IDEs, daemons, toolchains, and test forks may use different JDKs. | Verify the JVM at each stage and configure toolchains. |
| Upgrading only Gradle/Maven | Plugins or transitive dependencies may still be incompatible. | Audit the full build/plugin/dependency graph. |
| Setting only source/target 17 | Does not lock down target release Java SE APIs. | Use --release 17. |
| Checking compile success only | Runtime libraries, reflection, agents, and native integrations may fail. | Run tests, integration tests, packaging, and smoke tests. |
| Bumping all libraries to latest without a plan | Major versions may break APIs or pull unrelated changes. | Upgrade in groups using BOMs and migration guides. |
| Checking only direct dependencies | Transitive dependencies may pull in old ASM/Byte Buddy. | Inspect dependency trees and plugin classpaths. |
| Assuming JUnit must jump to major 6 | JUnit 5 runs on JDK 17. | Upgrade to JUnit 6 only when ready for its Java 17 baseline and breaking changes. |
| Using --add-opens as a universal fix | Does not fix class-file versions, APIs, or version conflicts. | Upgrade libraries and open packages only for controlled transitions. |
| Not pinning plugin versions | Builds can drift when parent/tool versions change. | Manage plugin versions centrally and use wrappers. |
| Neglecting IDE/CI/containers | Local environments may differ from production. | Align JDKs, wrappers, toolchains, and image policies. |

## 18. Frequently asked questions

**Is Gradle 7.3 or higher mandatory to build Java 17?**  
To run Gradle itself on JDK 17, 7.3 is the first supported version. Specific plugins/frameworks may require newer Gradle releases; check their compatibility matrices.

**Does Maven require a major version upgrade just to run on JDK 17?**  
Not necessarily. Maven 3.9.x runs on JDK 17. What matters is using the wrapper, a compatible compiler plugin, release=17, and upgrading other plugins as needed.

**Can I compile with JDK 17 while targeting Java 11 output?**  
Yes, using a JDK 17 toolchain paired with --release 11. However, if your project targets Java 17, set release 17 to use the target platform's APIs and language features.

**Do I have to upgrade JUnit 5 to JUnit 6?**  
No. JUnit 5 requires Java 8+ and runs on JDK 17. JUnit 6 has a Java 17 baseline and breaking changes; upgrade only when you are ready for the new major version.

**Why do Mockito or coverage agents fail even when the application compiles?**  
Mocking and coverage typically instrument bytecode inside the test JVM. Inspect Byte Buddy, ASM, JaCoCo, test plugin, and agent versions.

**Why does the build pass on a developer machine but fail in CI?**  
Differences may exist in the Gradle/Maven runtime JDK, toolchain, wrapper, plugin cache, dependency resolution, environment variables, or container image. Print the versions of each component in CI to spot discrepancies.

**Can sourceCompatibility and targetCompatibility replace --release?**  
Those properties do not lock down the target release's Java SE APIs. For JDK 9 and higher, prefer --release to enforce language level, bytecode, and platform APIs together.

**Is a library claiming "Java 17 compatible" enough to conclude readiness?**  
No. Check bytecode version, minimum runtime, transitive dependencies, module/reflection usage, native libraries, framework matrices, and release notes. Then run integration tests on JDK 17.

## 19. Official references

- [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): supported Java versions for running Gradle and Java toolchains.
- [Gradle Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): configuring JDKs for compile, test, and Javadoc; distinguishing toolchains from the JVM running Gradle.
- [Gradle Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): configuring Java release and compiler compatibility.
- [Apache Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html): configuring maven.compiler.release and --release.
- [Apache Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/): versions, compiler configuration, and system requirements.
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html): selecting a JDK independently of the JVM running Maven.
- [Apache Maven Surefire — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html): integrating test engines with Surefire.
- [JUnit 6 Release Notes](https://docs.junit.org/6.0.3/release-notes.html): Java 17 baseline and changes when migrating from JUnit 5.
- [JaCoCo Change History](https://www.jacoco.org/jacoco/trunk/doc/changes.html): class file/JDK support milestones and coverage tool changes.
- [ASM Versions](https://asm.ow2.io/versions.html): history of class-file version and JDK support.
- [Byte Buddy README](https://github.com/raphw/byte-buddy/blob/master/README.md): Java class file support version table.
- [Lombok Changelog](https://projectlombok.org/changelog): JDK support history, including the JDK 17 milestone.
- [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java runtime and build tool requirements by Spring Boot version.

**Guiding principle:** Upgrade the wrapper/build tool first, configure the JDK toolchain and --release 17, then upgrade compiler/test plugins, annotation processors, bytecode tools, frameworks, and runtime dependencies according to each component's compatibility matrix. Verify transitive dependencies, CI, IDE, and containers; finally run the complete build, test suite, and smoke tests on JDK 17.
