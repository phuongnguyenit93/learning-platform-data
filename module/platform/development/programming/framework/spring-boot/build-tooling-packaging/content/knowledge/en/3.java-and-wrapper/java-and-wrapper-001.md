# Choosing a Compatible Version Set Across Java, Spring Boot, Maven, and Gradle

## 1. Why Must You Choose Versions as a Set?

A Spring Boot project can compile cleanly on a developer's machine yet fail immediately when running a build in CI or deploying to a server. A common cause is that the tools and Java environments use **incompatible versions**. For example:

- Upgrading Spring Boot to a new branch while keeping a Gradle Wrapper that is too old: the Spring Boot plugin does not support that Gradle version.
- Setting Java 21 for the application while running Gradle 8.4 on a Java 21 JVM: this Gradle version is not yet confirmed to support **running Gradle itself** on Java 21.
- Compiling the application with Java 21 and then deploying on Java 17: the JVM on the server cannot read the newer class files.
- One person runs a machine-wide installation of Maven/Gradle while another runs the Wrapper that pins the project's own version: build results can differ.

The goal of this lesson is to know how to **select and verify a working combination**, explain why that combination is valid, and save the choice into the project configuration so that personal machines, IDEs, and CI use it consistently.

**You do not need to use both Maven and Gradle to build the same application.** Typically, each project chooses **one** tool: Maven **or** Gradle. When referring to a "Java – Spring Boot – Maven/Gradle set," we need to check Spring Boot's compatibility with Java and with the **chosen** build tool, then check the specific constraints of that tool.

## 2. Distinguishing the Four Involved Versions

| Component | Role | Where It Is Typically Configured / Observed |
| --- | --- | --- |
| **Java/JDK** | JDK to run the build tool, compile, and run tests; JVM/JRE to execute the application | JAVA_HOME, IDE/CI settings, Gradle toolchain, Maven toolchains, base image |
| **Spring Boot** | Application framework and set of dependencies/plugins | Spring Boot parent/BOM and Maven Plugin; Gradle plugin/BOM |
| **Maven** | Dependency management, lifecycle, compilation, testing, and packaging for Maven projects | pom.xml, Maven Wrapper in .mvn/wrapper |
| **Gradle** | Dependency management, task graph, compiler/toolchain, testing, and packaging for Gradle projects | build.gradle(.kts), Gradle Wrapper in gradle/wrapper |

Do not lump every Java version into a single number. At a minimum, you need to identify:

1. **Java running Maven/Gradle**: the JVM used by the build process; for Maven it can be inspected via **./mvnw -version**, for Gradle via **./gradlew --version**.
2. **Java used to compile/test**: the JDK selected by the Gradle Java toolchain or Maven toolchains; it can differ from the JVM running the build tool.
3. **Java language/API/target bytecode level**: configured via **--release** or equivalent; determines which syntax and APIs the program may use.
4. **Java running the application at deployment**: the JVM in the VM, container image, or platform runtime.

A "correct" combination must satisfy all relevant places; merely seeing **java -version** on a laptop is not enough to draw a conclusion.

## 3. Checking Compatibility via the Intersection of Conditions

You can visualize how to choose versions as follows:

~~~text
Step 1: Choose a Spring Boot branch/patch accepted by the project
                 |
                 v
Step 2: Choose a Java version within Boot's supported range
                 |
                 v
Step 3: Choose Maven OR Gradle from Boot's supported list
                 |
                 v
Step 4: If using Gradle, verify Gradle can run on the build JVM
                 |
                 v
Step 5: Verify compile Java, target bytecode, and deploy JVM
                 |
                 v
Step 6: Pin the Wrapper, run build/test, and test the actual artifact
~~~

Each compatibility document solves only one part:

- **Spring Boot System Requirements**: the minimum/maximum supported Java versions and the explicitly supported Maven/Gradle versions for a **specific Boot branch**.
- **Gradle Java Compatibility Matrix**: which Gradle versions can **run on a given JVM** and which support Java via a **toolchain** for compiling/testing.
- **Maven and project plugin documentation**: the minimum JDK to run Maven, plus requirements of the Maven Compiler Plugin, Spring Boot Maven Plugin, and other plugins.
- **Deployment environment**: whether the JVM is new enough to run the bytecode and the libraries/frameworks.

The method is to take the **intersection** of these conditions. You cannot infer from "Spring Boot supports Java 21" that "every Gradle version allowed by Spring Boot can run under Java 21."

## 4. Reference Version Ranges from Official Documentation

The table below records examples from the System Requirements page of **each branch/patch** (cross-checked on 2026-11-09). These ranges are compatibility information published by the Spring Boot project; **this does not mean every branch is still under maintenance support at the time you read this**. When applying in practice, open the page for the exact version your project uses and check its support status and latest patch.

| Spring Boot Branch Looked Up | Java Versions Published as Supported by That Branch | Maven Versions Published as Supported | Gradle Versions Published as Supported |
| --- | --- | --- | --- |
| **3.3.13** | Java 17 to 23 | Maven 3.6.3+ | Gradle 7.x from 7.5 or Gradle 8.x |
| **3.5.16** | Java 17 to 25 | Maven 3.6.3+ | Gradle 7.x from 7.6.4 or Gradle 8.x from 8.4 |
| **4.0.9** | Java 17 to 27 | Maven 3.6.3+ | Gradle 8.x from 8.14 or Gradle 9.x |
| **4.1.2** | Java 17 to 27 | Maven 3.6.3+ | Gradle 8.x from 8.14 or Gradle 9.x |

Sources for self-verification:
- Boot 3.3: https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Boot 3.5: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Boot 4.0: https://docs.spring.io/spring-boot/4.0/system-requirements.html
- Boot 4.1 / current documentation: https://docs.spring.io/spring-boot/system-requirements.html

**Note 1 — Check the right branch:** If the project uses Boot 3.5, do not take rules from the "latest" page belonging to the 4.x branch to conclude what Gradle/Java can be used for Boot 3.5. A patch release within a branch may also update the list of supported Java versions.

**Note 2 — Maven 3.6.3+ does not mean ignoring plugins:** The table shows the support level published by Boot. For a real project, also check the versions of the Maven Compiler Plugin, Surefire, Kotlin/Lombok, or company plugins. When choosing Maven 3.x, prefer a newer 3.x version allowed by your organization and pin it with the Maven Wrapper.

**Note 3 — Java support has an upper bound:** If Boot 3.3.13 publishes support up to Java 23, upgrading the runtime on your own to Java 25 is a change **outside the confirmed range**; you should not claim it is supported simply because the application happens to start up at times.

## 5. Gradle Java Compatibility: Distinguishing the JVM Running Gradle from the Toolchain

This is a point where mistakes happen easily when choosing versions. According to the Gradle Compatibility Matrix, some common Java compatibility thresholds are:

| Java Under Consideration | Gradle Version First Supporting **Running Gradle** on That Java | Gradle Version First Supporting **Java Toolchain** for That Java |
| --- | --- | --- |
| Java 17 | Gradle 7.3 | Gradle 7.3 |
| Java 21 | Gradle 8.5 | Gradle 8.4 |
| Java 25 | Gradle 9.1.0 | Gradle 9.1.0 |
| Java 27 | Gradle 9.8.0 | Gradle 9.8.0 |

Source: https://docs.gradle.org/current/userguide/compatibility.html

The difference between the two columns is critical. **Gradle 8.4 supports Java 21 as a toolchain for compilation**, but according to the matrix it **does not yet support running Gradle itself on a Java 21 JVM**. If you must keep Gradle 8.4, you can run Gradle on JDK 17 and use a Java 21 toolchain for compilation, provided your project's plugins allow it. If you want to **run Gradle on JDK 21**, you need Gradle **8.5 or newer** and it must still fall within the range supported by the Spring Boot plugin.

Examples of intersecting conditions:

- **Boot 3.5.16 + Java 21 + Gradle 8.14**: falls within Boot 3.5's supported range and Gradle 8.14 can run on Java 21. This is a reasonable set.
- **Boot 4.1.2 + Java 21 + Gradle 8.14**: also fits the ranges above.
- **Boot 4.1.2 + Java 25 + Gradle 9.1**: Boot 4.1 allows Java 25, Boot 4.1 allows Gradle 9.x, and Gradle 9.1 can run on Java 25.
- **Boot 4.1.2 + Java 21 + Gradle 8.10**: incompatible even though Gradle 8.10 can run on Java 21, because Boot 4.1 requires Gradle 8.x from **8.14**.
- **Boot 3.5.16 + Java 21 + Gradle 8.4 running on JDK 21**: incompatible at the JVM layer running Gradle. You can consider JDK 17 to run Gradle with a Java 21 toolchain, or upgrade Gradle within Boot's supported range.

The fact that Boot supports a very new Java version **does not guarantee** that every Gradle version listed by Boot can run/toolchain with that Java version. You must take the intersection of both matrices, not read only one table.

## 6. Process for Choosing a Version Set for a New or Existing Project

### Step 1: Identify Requirements Before Choosing

State clearly: whether the project is new or under maintenance; whether a Boot upgrade is required; which JDKs exist in the runtime environment; whether Maven or Gradle is mandatory; which JDKs CI can install; and whether additional plugins/frameworks have their own limits. A project that must run on Java 17 cannot simply choose Java 21 bytecode just because a developer has Java 21 installed.

For systems already running in production, **prioritize identifying the current set and supported versions before upgrading**. Do not pick every latest version independently and then try to piece them together afterward.

### Step 2: Choose an Appropriate and Maintained Spring Boot Version

Check the documentation/versioned release page for the Boot branch, its support status, and library dependency compatibility. Each major branch can change Java, Spring Framework, the servlet API, Jakarta namespaces, and plugin requirements. Jumping across major branches requires reviewing the migration guide and retesting the source code, not just changing the version in `pom.xml` or `build.gradle`.

After selecting a branch, lock in a verified patch release. In Maven projects, the version of **spring-boot-starter-parent** or BOM is usually aligned with **spring-boot-maven-plugin**. In Gradle projects, align the Spring Boot Gradle Plugin with the corresponding dependency management/BOM. Do not inadvertently mix multiple Boot branches on the classpath.

### Step 3: Choose the Target Java Version

Choose a Java version within Boot's supported range that also matches the deployment runtime. Java 17, 21, and 25 are examples of LTS branches; which branch you pick also depends on organizational policy, security patches, and other plugins.

For Spring Boot applications requiring Java 17 or higher, **setting `--release 11` does not make the entire application Java 11-compatible**: Boot's libraries still require the corresponding minimum Java level. You can only lower the bytecode target to a version that the entire framework, dependencies, and runtime truly support.

### Step 4: Choose Maven or Gradle Within Boot's Supported Range

**If using Maven:** pick a Maven version supported by Boot that matches the JDK running Maven, then pin the Maven Wrapper. Maven requires a JDK to build Java; Maven plugins may require their own JDK version.

**If using Gradle:** pick a version that simultaneously satisfies:
1. Falls within the Gradle range allowed by the Spring Boot plugin.
2. Supports the JVM that will run Gradle in the IDE, terminal, and CI.
3. Supports the Java toolchain and any required additional plugins.

Do not assume "Gradle 9 is newer than Gradle 8 so it definitely works with all Spring Boot 3.x": an older Boot branch may only publish support for Gradle 7.x/8.x. Likewise, a newer Boot release may drop support for older Gradle versions.

### Step 5: Lock In the Compile Java and Runtime Java

If Java 21 is needed at deployment, configure the toolchain and compiler target at level 21; the deployment JVM must be compatible with that bytecode and within the Java range supported by Boot. For an artifact compiled at Java 21 level, merely changing `JAVA_HOME` on the server to Java 17 will not resolve startup failures.

CI should build and test the artifact in a controlled Java environment and test the final artifact directly on the intended deployment runtime.

### Step 6: Pin, Test, and Document the Decision

Commit the build files, Wrapper, toolchain/Java release settings, and CI configuration to version control. Clearly document the chosen version set along with the rationale and reference links in the project README. Run build/test with the **Wrapper**, then run the artifact on the target runtime. When upgrading any single component, revisit the entire intersection of conditions.

## 7. Java Toolchain, `--release`, `JAVA_HOME`, and IDE: Four Different Things

### 7.1. Gradle Java Toolchain

Example **build.gradle** (Groovy DSL), the Java configuration section of a Gradle project with the Java plugin:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

- **toolchain.languageVersion** requests a JDK 21 installation to execute Java tasks that support toolchains. Gradle can detect installed JDKs; automatic JDK downloads only happen when an appropriate toolchain repository is configured.
- **options.release = 21** instructs the compiler to emit bytecode and check Java APIs against level 21, avoiding accidental use of newer APIs when `javac` comes from a higher JDK.
- Do not treat this snippet as a standalone build project: it must live inside a **build.gradle** that already applies the Java plugin (and the application's required plugins).

A toolchain **does not automatically change the JVM running the Gradle daemon**. Gradle can run on JDK 17 and compile with a JDK 21 toolchain, provided the Gradle/plugin versions allow it and JDK 21 is available or provisioned. Therefore, you must check both **./gradlew --version** and the toolchain list.

Reference: https://docs.gradle.org/current/userguide/toolchains.html

### 7.2. Maven: Compiler Release and Toolchains

In a project inheriting from **spring-boot-starter-parent**, you can typically set the target Java version as:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>
~~~

Depending on the parent/plugin, **maven.compiler.release** can be configured directly to guarantee the target API/bytecode level. Example of a simple compiler release configuration in a POM:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

This is an **illustrative XML snippet**; it must be placed properly inside the `<properties>` section of a complete POM and checked against the effective parent/plugin configuration. The `release` property does not install JDK 21 and does not determine which JVM Maven itself runs on. For projects that need a compile JDK different from the JDK running Maven, look into the **Maven Toolchains Plugin** and your organization's toolchain configuration. When toolchains are not used, Maven typically uses the JDK running Maven to compile.

### 7.3. JAVA_HOME and IDE

**JAVA_HOME** typically affects the default JDK used to run Maven/Gradle; IDEs may have separate **Gradle JVM** or **Maven Runner JRE** selectors. Someone might see `java -version` in the terminal as 21 while the IDE is running Gradle with a different JDK. With newer Gradle versions, Daemon JVM criteria or environment JVM rules can also govern the JDK running Gradle. Always verify using the actual build command executed in each environment.

### 7.4. Deployment Runtime

A Java artifact contains bytecode for the Java level it was compiled against. Common examples:

| Compile Java Level | Class File Major Version | Minimum JVM to Read That Class File |
| --- | --- | --- |
| Java 17 | 61 | Java 17 |
| Java 21 | 65 | Java 21 |
| Java 25 | 69 | Java 25 |

This is only the **bytecode condition**. The JVM must still fall within the range supported by Spring Boot, runtime libraries, and infrastructure. Using Java 25 to run Java 21 classes may satisfy the bytecode check, but you still have to verify compatibility with Boot and dependencies.

## 8. Wrapper: Pinning the Build Tool So Every Environment Uses the Same Version

The **Wrapper** consists of scripts and configuration stored in the repository to fetch/launch the project's version of Maven or Gradle. The Wrapper helps avoid situations where a laptop has a different Gradle/Maven version than the CI server. It **does not pin the JDK as well**, so Java still has to be managed in parallel.

### 8.1. Gradle Wrapper

A typical layout:

~~~text
project/
├── build.gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

In **gradle/wrapper/gradle-wrapper.properties**, the **distributionUrl** field points to the pinned Gradle release; for instance, a Gradle 8.14 URL must point to the 8.14 distribution ZIP. When changing versions, run the Wrapper task following Gradle's upgrade procedure to update the scripts, JAR, and properties accordingly:

~~~bash
./gradlew wrapper --gradle-version 8.14
./gradlew wrapper --gradle-version 8.14
./gradlew --version
~~~

Running the task twice may be needed to fully synchronize the wrapper scripts/JAR per Gradle's guidance. This is an **illustration of upgrading/pinning a project that is permitted to use Gradle 8.14**; do not run the command when you have not yet verified whether the current project's plugins support 8.14.

When upgrading the Wrapper, verify the distribution download source, the SHA-256 hash if used, and the integrity of **gradle-wrapper.jar**. Only commit Wrapper files from trusted sources. Documentation: https://docs.gradle.org/current/userguide/gradle_wrapper.html

### 8.2. Maven Wrapper

A typical layout:

~~~text
project/
├── pom.xml
├── mvnw
├── mvnw.cmd
└── .mvn/
    └── wrapper/
        └── maven-wrapper.properties
~~~

Some Maven Wrapper distribution types also include **maven-wrapper.jar** or a downloader, depending on how the Wrapper was generated. The properties file specifies the Maven distribution the Wrapper should launch. Verify with:

~~~bash
./mvnw --version
./mvnw clean verify
~~~

Use **mvnw.cmd** on Windows; use **gradlew.bat** for Gradle on Windows. On Linux/macOS, the Wrapper script requires execute permissions. When running the Wrapper, CI usually only needs to provide the JDK, network/cache, and necessary environment variables; it does not need to install an arbitrary Maven/Gradle distribution and invoke it directly.

Documentation: https://maven.apache.org/wrapper/ and https://maven.apache.org/install.html

## 9. Concrete Example: Choosing Java 21 and Spring Boot 3.5.16

Suppose the requirement is a **new experimental application**, Java 21 runtime, and the team wants to use Maven or Gradle; after checking the maintenance policy for a real project, we take the **Spring Boot 3.5.16** branch as a technical example.

- Boot 3.5.16: supports Java 21.
- If choosing **Maven 3.9.x**, this version exceeds the minimum Maven version published by Boot and can use JDK 21; project plugins must still be checked.
- If choosing **Gradle 8.14**, Boot 3.5 allows Gradle 8.x from 8.4 and Gradle 8.14 can run on Java 21.
- Configure target Java 21; CI builds and the server runs on Java 21; save the corresponding Wrapper.

The two configurations below are **two alternative choices** for the same application idea. Only create **pom.xml** when choosing Maven, or **build.gradle** when choosing Gradle.

### 9.1. Maven Option: Minimal Complete POM

File **pom.xml** at the project root:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>version-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
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

The Spring Boot parent manages many compatible dependency and plugin versions, so the example does not specify a version for the starter directly. The Boot plugin is declared to create an executable JAR via the lifecycle configured by the parent. **A Java 21 JDK must be available**, or the Maven environment must use an appropriate toolchain.

### 9.2. Gradle Option: Minimal Complete build.gradle

File **build.gradle** (Groovy DSL) at the project root:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

A Gradle project also needs **settings.gradle** and a matching Gradle Wrapper. The Spring Boot plugin and dependency management handle managed dependency versions; do not manually set a separate Spring Framework version that mismatches Boot. In this example, Gradle 8.14 and Java 21 satisfy both checked matrices.

### 9.3. Java Code Shared by Both Options

File **src/main/java/com/example/demo/VersionDemoApplication.java**:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VersionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(VersionDemoApplication.class, args);
    }
}
~~~

This is a complete Java class that compiles when the project has the Spring Boot dependencies above. The application does not declare any web endpoints, so when run it simply starts the Spring application context and can exit normally; do not expect an HTTP server on port 8080. Spring Boot logs vary by version and environment, so no fixed stdout is prescribed.

For a **Maven project that already has Maven Wrapper**:

~~~bash
./mvnw --version
./mvnw clean verify
java -jar target/version-demo-0.0.1-SNAPSHOT.jar
~~~

For a **Gradle project that already has Gradle Wrapper 8.14**:

~~~bash
./gradlew --version
./gradlew clean build
java -jar build/libs/version-demo-0.0.1-SNAPSHOT.jar
~~~

These commands are for Linux/macOS; switch to **mvnw.cmd** or **gradlew.bat** on Windows. Running the JAR verifies the executable artifact. The JAR filename is based on the group/artifact/version in the example; if your build customizes the archive name, use the actual output file.

**Limitations of the example:** the Maven/Gradle configurations describe two alternative projects, not running both Wrappers on the same project. Generating the Wrapper is a project setup step; the Java snippet cannot compile directly with `javac` without the Spring dependencies. To evaluate real runtime compatibility, you must run the build and artifact on the target JDK/CI/container.

## 10. Upgrade Scenarios and How to Decide

### Scenario A — Upgrading Java 17 to Java 21 While Keeping Spring Boot 3.5

1. Check the current Boot 3.5 patch release and verify its documentation supports Java 21.
2. If the Gradle Wrapper is **8.4** and Gradle runs on Java 21, upgrade to Gradle **8.5+ within Boot's supported range** (e.g., 8.14), or keep the Gradle JVM on 17 and configure a Java 21 toolchain if appropriate.
3. Switch the Gradle/Maven Java target to 21 when you want to use Java 21 features/bytecode. There is no need to raise the target if the only goal is to run the application on a Java 21 JVM while still supporting JVM 17.
4. Check CI, IDE, Docker base image, or actual server JDK; build and run the artifact to confirm.

### Scenario B — Upgrading Spring Boot 3.5 to 4.1 While Wanting to Keep Gradle 8.10

Boot 4.1 requires Gradle 8.x from **8.14** or Gradle 9.x. Even though Gradle 8.10 can run on Java 21, **the combination Boot 4.1 + Gradle 8.10 is outside the range published as supported by Boot 4.1**. You must choose Gradle 8.14+ or 9.x and check other plugins first, then upgrade Boot. Also read Boot's migration guide to fix related API/configuration changes.

### Scenario C — Wanting to Use Java 25 with Spring Boot 4.1

Boot 4.1 supports Java 25. If you want to **run Gradle itself on a Java 25 JVM**, you need Gradle **9.1+** (while still staying on a Gradle 9.x branch supported by Boot 4.1). Do not pick Gradle 8.14 and assume it suffices just because Boot allows Gradle 8.14: Gradle 8.14 is not confirmed to run on Java 25.

With Maven, you must pick a Maven/plugin version compatible with Java 25, check the Maven Wrapper, then re-run tests and try the executable artifact. Spring Boot supporting Java 25 does not mean every annotation processing tool or library in your project already supports it.

### Scenario D — Unable to Change Java 17 in the Deployment Environment

Choose a Spring Boot version and dependencies that still support Java 17, set the target bytecode to Java 17, and test the application on a Java 17 JVM. You may use a newer JDK to build if the compiler is configured with **--release 17** and both the build plugins and Boot still fit, though this needs real testing; a newer JDK on CI does not automatically make an artifact Java 17-compatible.

## 11. Checking Running Versions with Concrete Commands

Run these from the project root and record the output from the **exact machine and pipeline** performing the build.

~~~bash
java -version
javac -version
~~~

These two commands show the default Java on `PATH` in the terminal. They are **not enough** to determine which JDK the Gradle toolchain or Maven Toolchains will use.

**If using Gradle:**

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean test bootJar
~~~

- **--version**: inspect the Gradle version and associated JVM information.
- **javaToolchains**: list the Java installations Gradle detects for Java toolchains.
- **clean test bootJar**: compile, run tests in the project, and create the executable JAR when the Spring Boot Gradle Plugin is applied. A passing build does not replace a smoke test on the deployment runtime.

**If using Maven:**

~~~bash
./mvnw --version
./mvnw clean verify
~~~

- **--version**: inspect the Maven version run by the Wrapper and the Java info of the Maven process.
- **clean verify**: run the lifecycle up to `verify` according to the configured plugins. With the Spring Boot parent and Boot Maven Plugin as in the example, the `package` phase produces the executable JAR via `repackage`.

**After the build**, run the JAR with its exact output filename and check startup logs, configuration/profiles, service connections, health endpoint (if the project has one), and critical business behavior. Re-run checks in CI whenever upgrading the JDK, Boot, or Wrapper.

### Reading Errors to Identify Which Version Mismatches

| Symptom | Where Is the Mismatch Usually? | Verification Step |
| --- | --- | --- |
| **UnsupportedClassVersionError** on `java -jar` | Target Java runtime is older than the class files of the app or a library | `java -version`, Java target/release, and Boot's Java range |
| **Unsupported Java / Could not determine java version** from Gradle | Old Gradle running on a JVM that is too new | `./gradlew --version` and Gradle Compatibility Matrix |
| **Spring Boot Gradle plugin requires Gradle ...** | Gradle Wrapper is outside the Boot plugin's supported range | Boot System Requirements, `gradle-wrapper.properties` |
| **invalid target release** or **release version ... not supported** | Compiler JDK does not support the requested `--release` level | `javac -version`, Gradle toolchain/Maven compiler |
| **No matching toolchains found** | Matching JDK not found and provisioning is not configured | `./gradlew -q javaToolchains`, installed JDKs, toolchain repositories |
| **UnsupportedClassVersionError** during a build plugin step | JVM running the build tool or plugin is too old for the plugin's bytecode | `./mvnw --version` or `./gradlew --version`, plugin requirements |
| CLI build succeeds but IDE fails | IDE uses a different JDK/Gradle JVM or importer than CLI | IDE Gradle JVM/Maven Runner JRE and Wrapper |
| Tests PASS but JAR fails on server | Different Java runtime, environment config, dependencies, or packaging | Run the exact JAR with the target JVM and inspect logs |

Do not jump straight to adding random dependencies or disabling tests. Identify **which step** failed (starting Gradle/Maven, resolution, compilation, testing, packaging, running) and cross-check the exact versions involved.

## 12. Common Mistakes and Good Practices

- **Picking every "latest" version independently:** the latest Maven, Gradle, Boot, and JDK do not automatically form a supported combination. Always take the intersection of version ranges.
- **Checking only Spring Boot's minimum Java:** you must also check the **maximum confirmed Java**, the JVM running Gradle/Maven, the toolchain, and the runtime.
- **Confusing the Java running Gradle with the Java used to compile:** the toolchain can differ from the daemon JVM; this is useful, but it must be configured and verified.
- **Assuming the Wrapper pins Java too:** the Wrapper only pins the build tool; the JDK must be specified separately in CI, toolchains, and the deployment environment.
- **Mixing a Boot plugin and BOM from different branches:** easily creates an inconsistent dependency graph or unpredictable build behavior; manage with an intentional version set.
- **Not committing the Wrapper:** teammates end up depending on system-wide Gradle/Maven installations and risk running different versions than CI.
- **Running only `bootRun` or from the IDE:** can hide errors in the executable JAR and the Java runtime that production will actually use.
- **Setting the Java target higher than the actual runtime:** compilation PASSES, but deployment crashes with `UnsupportedClassVersionError`.
- **Upgrading versions while ignoring additional plugins:** Kotlin, Lombok, JaCoCo, native-image, compiler plugins, and annotation processors each have their own support matrices.

A solid version decision should record at least: **Spring Boot version + Java build/toolchain/release + Java deploy + Maven/Gradle Wrapper version + critical plugins + consulted compatibility docs + CI and smoke test results**.

## 13. Self-Check with Four Questions

**Question 1:** A Spring Boot 4.1 project uses Java 21 and Gradle 8.10. Java 21 can run Gradle 8.10, so is this valid?

**Answer:** Not yet. Boot 4.1 requires Gradle 8.x from 8.14 or Gradle 9.x, so you must upgrade Gradle into that range and check other plugins.

**Question 2:** A Boot 3.5 project uses Gradle 8.4. Can you use Java 21 as a toolchain while running Gradle on Java 17?

**Answer:** Possible according to published thresholds: Gradle 8.4 supports a Java 21 toolchain and can run on Java 17; Boot 3.5 allows Gradle 8.4. You still need to check the exact versions of plugins and actually run build/test.

**Question 3:** Does simply updating the Maven Wrapper to a newer version allow a server running Java 17 to execute Java 21 bytecode?

**Answer:** No. The Maven Wrapper selects the Maven version; it does not upgrade the server's JVM. You must lower the Java target to a valid level or upgrade the server runtime within Boot's supported range.

**Question 4:** Can you use Java 25 to run Gradle 8.14 in a Boot 4.1 project, since Boot 4.1 supports Java 25 and Gradle 8.14?

**Answer:** Not according to the Gradle matrix: Gradle 8.14 is not confirmed to run on Java 25. Choose Gradle 9.1+ in a Gradle 9.x branch supported by Boot 4.1, or choose a different JVM to run Gradle when the specific use case permits.

## 14. Checklist for Finalizing a Version Set

- [ ] Choose **one build tool** for the project: Maven or Gradle.
- [ ] Identify the exact **Spring Boot branch and patch release**; check System Requirements for that exact branch.
- [ ] Choose the target Java within Boot's supported range; confirm the deployment environment's Java runtime.
- [ ] Choose Maven/Gradle within Boot's supported range; if using Gradle, verify **Java running Gradle** and **Java toolchain** separately.
- [ ] Pin the Wrapper, plugins, and dependency management; align JDK/CI/IDE as needed.
- [ ] Run build, test, packaging, and **start the final artifact** on the target JVM.
- [ ] Record the version set and verification results in the project documentation; re-evaluate whenever upgrading.

**Remember:** Compatibility is the intersection of **Boot ↔ Java**, **Boot plugin ↔ Maven/Gradle**, **Gradle ↔ Gradle's JVM/toolchain**, and **bytecode ↔ deployment JVM**. Checking all of these relationships helps you select a version set that builds cleanly, is easy to maintain, and is reproducible from laptop to CI and deployment.

### References

- Spring Boot (current) — System Requirements: https://docs.spring.io/spring-boot/system-requirements.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 4.0 — System Requirements: https://docs.spring.io/spring-boot/4.0/system-requirements.html
- Gradle — Compatibility Matrix: https://docs.gradle.org/current/userguide/compatibility.html
- Gradle — Toolchains for JVM Projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Apache Maven — Installing Maven: https://maven.apache.org/install.html
- Apache Maven — Maven Wrapper: https://maven.apache.org/wrapper/
