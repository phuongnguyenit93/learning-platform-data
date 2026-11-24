# Preparing the `spring-context` Library and Compatible Versions

## 1. Understanding the Setup Task Correctly

To write your first Spring Core Container application using Java 17+, you need a **JDK**, a **build tool**, the **`spring-context` dependency**, and a program that creates an `ApplicationContext`. You do not need Spring Boot, an HTTP server, or a database to try out IoC/DI.

The commonly used Maven dependency coordinates are:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
    <version>7.0.9</version>
</dependency>
~~~

Here `org.springframework` is the **groupId**, `spring-context` is the **artifactId**, and `7.0.9` is the **version**. These three parts identify a released artifact on a repository such as Maven Central. The artifact name is **different** from the Java package `org.springframework.context` and **different** from the class name `ApplicationContext`.

Version `7.0.9` is pinned as a stable example, present in the official Spring Framework documentation at the time of writing. When using it in real production software, check currently supported releases, security patches, and run tests after upgrading; do not treat a version number in learning material as a version that must be kept forever.

**Target outcome:** compile imports from `org.springframework.context.annotation.*`, open an `AnnotationConfigApplicationContext`, register `@Bean` definitions, retrieve beans via `getBean`, inspect the dependency tree, and know how to troubleshoot JDK/classpath/version errors.

## 2. Why Choose `spring-context` Instead of Downloading Every JAR?

Spring Framework consists of multiple separate modules, published as Maven/Gradle artifacts:

| Artifact | Primary Responsibility | Commonly Encountered APIs/Concepts |
| --- | --- | --- |
| `spring-core` | Core utilities, resource abstraction, and foundation | `Resource`, `ClassPathResource` |
| `spring-beans` | Bean factory, bean definitions, configuration, and dependency wiring | `BeanFactory`, `BeanDefinition` |
| **`spring-context`** | Application-level container and annotation configuration | `ApplicationContext`, `AnnotationConfigApplicationContext`, `@Configuration`, `@Bean` |
| `spring-expression` | Spring Expression Language (SpEL) | `ExpressionParser` |
| `spring-aop` | Proxy/AOP mechanisms required when related features are used | Proxy infrastructure |
| `spring-webmvc` | Servlet-based MVC for HTTP applications | `DispatcherServlet` |
| `spring-tx` | Transaction management infrastructure | `PlatformTransactionManager` |

For a Core Container demo with only Java configuration and DI, declare **a single direct dependency on `spring-context`**. Maven/Gradle reads the artifact's POM metadata to automatically resolve **required transitive dependencies** (including foundational modules such as `spring-beans` and `spring-core`). You do not need to list every module manually “just to be safe,” nor should you manually download a few individual JARs and arbitrarily assemble a classpath.

**`spring-core` alone does not contain the `ApplicationContext` API.** `spring-context-support` is also not a required artifact for a standard `@Bean` demo. Spring does not have a single `spring-all` JAR containing every capability.

Libraries such as `spring-webmvc`, `spring-jdbc`, `spring-security`, database drivers, or an embedded server are **not included by default** just because you added `spring-context`.

### Direct Dependencies and Transitive Dependencies

- **Direct dependency:** declared directly in `pom.xml` or `build.gradle`.
- **Transitive dependency:** declared by a depended-upon artifact and resolved by the build tool along the dependency graph.
- **Resolved dependency:** the final version selected by the build tool after considering versions, BOMs, exclusions, and conflicts.

Seeing `spring-beans` in `dependency:tree` **does not mean** you declared it directly. Conversely, seeing a JAR downloaded to your machine **does not guarantee** that the JAR is on the compile/runtime classpath of the module you are working on.

## 3. Comparing Spring, Java, and Ecosystem Versions

Choose versions for the **entire application**, not just by picking a single number on Maven Central.

| Item | Spring Framework 6.2 | Spring Framework 7.0 |
| --- | --- | --- |
| JDK baseline | Java 17 | **Java 17** |
| Reference GA release | `6.2.19` | `7.0.9` |
| Common integration line | Corresponding Spring Boot 3.x | Corresponding Spring Boot 4.x |
| Jakarta | Jakarta generation of Framework 6.x | **Jakarta EE 11** baseline |
| Choice for examples | Usable if related modules share the 6.2 line | Use **7.0.9** with Java 17 |

Spring 7.0 still supports **Java 17 as the minimum baseline**, although the Spring project recommends using a newer LTS JDK when appropriate. Therefore, setting `maven.compiler.release=17` is valid for `ApplicationContext` API examples on Spring 7.0.

**Important compatibility rules:**

1. If you add multiple Spring artifacts directly (for example `spring-context`, `spring-jdbc`, `spring-tx`), manage them with the **same Framework release** or an appropriate **BOM**.
2. **Do not force** `spring-beans:6.2.x` under `spring-context:7.0.9` just to silence a Maven conflict; doing so can cause runtime linkage errors.
3. When upgrading **6.2 → 7.0**, read the migration/release notes and review removed APIs, Jakarta EE 11, and servlet/integration libraries. “Both run on Java 17” **does not prove** that all older Java dependencies are compatible.
4. If the project uses **Spring Boot**, let Boot's BOM/parent/plugin manage the corresponding Spring Framework version. Do not manually add a `spring-context` version out of sync with Boot's release line without understanding all consequences.
5. GA releases published to Maven Central typically do not require configuring snapshot/milestone repositories. Avoid `SNAPSHOT`, `-M...`, and `-RC...` in introductory exercises unless you intentionally want to test preview releases.

**Framework vs. Boot:** `spring-context` is the core IoC module of Spring Framework; `spring-boot-starter` is a curated set of dependencies for a type of Spring Boot project. This lesson uses Framework directly so you can see how the container is created.

## 4. Verifying the JDK and Build Tool

Open a new terminal and run:

~~~bash
java -version
javac -version
mvn -version
~~~

Verify that `java` and `javac` belong to a JDK **17 or higher**. `mvn -version` also displays the Java home that Maven actually uses; do not conclude that Maven is running Java 17 just because your IDE has Java 17 selected.

On Linux/macOS you can check:

~~~bash
echo "$JAVA_HOME"
which java
which javac
~~~

On Windows PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command java
Get-Command javac
~~~

The output of these check commands is **machine-dependent** and has no fixed stdout. After changing `JAVA_HOME` or `PATH`, open a new terminal and re-verify.

The **JDK** is the toolkit/SDK; **Maven** is the build tool; the **Maven Compiler Plugin** invokes the Java compiler; **Spring JARs** are precompiled libraries; **Maven Central** is the repository serving artifacts. They are not interchangeable.

You should use the Maven Wrapper (`mvnw`) or Gradle Wrapper (`gradlew`) if the project provides one: the wrapper pins the build tool version for the entire team. Since the following example is a newly created project, use the `mvn` command after installing Maven 3.9+.

## 5. Complete Java 17 Maven Project with `spring-context`

Create this exact structure:

~~~text
spring-context-first/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringContextFirst.java
~~~

### 5.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-context-first</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.framework.version>7.0.9</spring.framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.framework.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.SpringContextFirst</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**POM Explanation:**

- `spring-context` uses Maven's default **compile** scope: the Spring API is present at both compile time and runtime.
- `maven.compiler.release=17` tells the compiler to target Java 17 APIs/bytecode, preventing accidental calls to newer JDK APIs in your source code.
- The `spring.framework.version` property centralizes the Framework version in one place. When using multiple Spring modules, a BOM is even better than repeating the version property.
- `maven-compiler-plugin` executes the compilation step; `exec-maven-plugin` launches the main class with the dependency classpath.
- Do not omit `version` in this dependency unless the POM actually inherits or imports appropriate **dependency management**.

You do not need to declare `spring-core`, `spring-beans`, or `spring-expression` separately in this demo as long as Maven resolves the graph through `spring-context`.

### 5.2. `src/main/java/demo/SpringContextFirst.java`

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class SpringContextFirst {
    private SpringContextFirst() {
    }

    interface Formatter {
        String greet(String name);
    }

    static final class EnglishFormatter implements Formatter {
        @Override
        public String greet(String name) {
            return "Hello, " + name + "!";
        }
    }

    static final class GreetingService {
        private final Formatter formatter;

        GreetingService(Formatter formatter) {
            this.formatter = formatter;
        }

        String greet(String name) {
            return formatter.greet(name);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        Formatter formatter() {
            return new EnglishFormatter();
        }

        @Bean
        GreetingService greetingService(Formatter formatter) {
            return new GreetingService(formatter);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            GreetingService first =
                    context.getBean(GreetingService.class);

            System.out.println("message=" + first.greet("An"));
            System.out.println("sameSingleton="
                    + (first == context.getBean(GreetingService.class)));
            System.out.println("context="
                    + context.getClass().getSimpleName());
        }
    }
}
~~~

**Why is this a real verification?** When `spring-context` is missing, the compiler cannot find the Spring imports. When configured properly, `AnnotationConfigApplicationContext` reads `AppConfig` and registers `formatter` and `greetingService`; Spring resolves the `Formatter` bean to pass to `@Bean greetingService(...)`. The default singleton scope ensures two lookups return the same reference within this context.

`@Configuration(proxyBeanMethods=false)` works here because the two factory methods do not directly call each other. `try-with-resources` closes the context properly. You do not need Spring Boot, an HTTP server, `@Autowired` fields, or component scanning for a Java configuration demo with explicit `@Bean` declarations.

### 5.3. Build and Run

From inside the `spring-context-first` directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

Maven downloads dependencies (on the first run), uses the Maven Compiler Plugin to invoke **`javac`**, and runs the program with the Spring classpath. Running `javac SpringContextFirst.java` directly **is not sufficient** unless you manually supply the full Spring JAR classpath.

**The three stdout lines printed by the application code itself** (excluding Maven logs or logging backend output):

~~~text
message=Hello, An!
sameSingleton=true
context=AnnotationConfigApplicationContext
~~~

If the application prints additional library logs in your own environment, distinguish those logs from the exact three `System.out.println` statements in `main`.

## 6. Setup Using Gradle Instead of Maven

If your project uses Gradle, you do not need to create both `pom.xml` and `build.gradle`. The following example reuses the **exact `SpringContextFirst.java` from Section 5.2** as its source, so the application output matches Section 5.3.

~~~text
spring-context-gradle/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SpringContextFirst.java
~~~

The `settings.gradle` file:

~~~groovy
rootProject.name = 'spring-context-gradle'
~~~

The `build.gradle` file (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:7.0.9'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.SpringContextFirst'
}
~~~

Use a Gradle version that supports Java 17 and configure a compatible JDK/toolchain. If a **Gradle Wrapper already exists**, on Linux/macOS run:

~~~bash
./gradlew run
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat run
~~~

If a new project **does not have a wrapper yet**, install a compatible Gradle version and run `gradle run` or generate the wrapper; do not assume a `gradlew` file appears on its own. The `run` task of the Application Plugin sets up the runtime classpath containing the project's direct and transitive dependencies.

**Application code stdout**:

~~~text
message=Hello, An!
sameSingleton=true
context=AnnotationConfigApplicationContext
~~~

Gradle may print additional task and build status lines beyond those three lines.

## 7. Inspecting the Dependency Graph and BOM

After a successful Maven build, inspect the Spring artifacts resolved by the project:

~~~bash
mvn dependency:tree -Dincludes=org.springframework
~~~

You will typically see `spring-context` along with several underlying modules pulled in by it. **Do not hardcode the list or count of transitive dependencies** because the graph can change across patch versions and features. Use:

~~~bash
mvn help:effective-pom
~~~

to view the POM model after parent/dependency management/plugins are applied. When you suspect a version conflict, read `dependency:tree` to see which module pulled in the wrong dependency version. On Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-context --configuration runtimeClasspath
~~~

The `./gradlew` command syntax applies only if the project has a wrapper; on Windows, use `gradlew.bat` instead.

### When a Project Needs Multiple Spring Artifacts

One way to control versions in a **non-Boot Framework project** is to import `spring-framework-bom`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>7.0.9</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
    </dependency>
</dependencies>
~~~

**This is an alternative approach**, not something you are required to insert into the POM in Section 5.1. A BOM only **manages versions** for dependencies you declare; a BOM **does not** automatically add every Spring module to your classpath.

When an application uses **Spring Boot**, prefer Boot's BOM/parent/plugin so that Spring Framework, web, data, and integration libraries stay synchronized. Do not mix a Framework 7 release with individually version-pinned Spring 6.2 modules and treat that as a valid dependency set.

## 8. Diagnosing Setup Errors Immediately

| Symptom | What to Check | Resolution |
| --- | --- | --- |
| `package org.springframework.context... does not exist` | `spring-context` missing from compile classpath or IDE out of sync | Declare the dependency properly, reload Maven/Gradle, compile with the build tool |
| `Could not find artifact org.springframework:...` | Wrong artifact/version, network, mirror, proxy, offline mode | Check GAV coordinates, Maven Central, `settings.xml`, or internal repository |
| `release version 17 not supported` | Maven compiler running on a JDK older than 17 | Check `mvn -version`, `JAVA_HOME`, toolchain |
| `UnsupportedClassVersionError` | Java runtime too old for the compiled class files | Align the runtime and bytecode/JDK versions |
| `NoClassDefFoundError` | Runtime classpath missing a JAR or dependency | Inspect the resolved graph and execution command |
| `NoSuchMethodError` | Possible mixed versions or binary mismatch | Check dependency tree, BOM, and exclusions |
| `NoSuchBeanDefinitionException` | Class or bean not registered in the context | Check `@Bean`, scan configuration, type, and context |
| `NoUniqueBeanDefinitionException` | Multiple candidate beans of the same type | Check `@Qualifier`, `@Primary`, and bean names |
| IDE shows red imports while Maven builds cleanly | IDE index/module config not reloaded | Refresh Maven/Gradle and verify source roots/modules |
| Console app exits immediately | `main` finished and the context closed | May be expected behavior; a DI demo needs no HTTP server |

**Distinguish clearly:** a Maven download error is different from a `javac` missing-package error; a runtime classpath error is different from Spring failing to resolve a bean. Do not wipe your entire Maven cache out of habit; identify which layer the error belongs to before changing versions or cleaning caches.

If you only installed `spring-core` and importing `ApplicationContext` still fails, choose **`spring-context`**, rather than arbitrarily altering Java package names.

### Manual JAR Downloads and JPMS

You can use `javac`/`java` with `-classpath` and all required JARs, but you must download the **exact transitive dependencies** and manage classpath path separators (`;` on Windows, `:` on Linux/macOS). This is prone to missing JARs and hard to upgrade; learning Spring with Maven/Gradle is much safer.

The example above uses the **standard classpath** without creating a `module-info.java`. JPMS/module path is a separate topic; do not move Spring JARs and reflection/proxy usages onto the module path expecting identical behavior without checking module metadata and openness.

## 9. Recommended Workflow for Real Projects

1. Choose a Java version supported by your runtime/CI, and synchronize IDE/Maven/Gradle.
2. Choose a supported Spring release line and one dependency management strategy (Framework BOM or the corresponding Boot BOM).
3. Add the exact artifacts for your needs — for Core Container, start with `spring-context`.
4. Create a small console demo with `@Configuration`, `@Bean`, and `ApplicationContext` and verify stdout.
5. Inspect the dependency graph and verify that multiple Spring major versions are not mixed.
6. Add JUnit/tests, CI, and check upgrade notes when introducing web/data/AOP/transactions into the project.
7. Use the wrapper to reproduce builds on other machines; apply security patch upgrades with tests and a rollback plan.

**You do not have to create a Spring Boot project** just to try out `AnnotationConfigApplicationContext`. However, when building a large web/data app, Boot can reduce configuration boilerplate. Both paths use Spring Framework's container, not two separate DI engines.

## 10. Exercises and Self-Check Questions

- **Swap implementation:** add a `VietnameseFormatter` returning `"Xin chao, " + name + "!"` and replace the `formatter()` bean. Predict `message=Xin chao, An!` without modifying `GreetingService`.
- **Remove the dependency on a copy:** temporarily remove `spring-context` from the POM, run `mvn compile`, and record the `package org.springframework... does not exist` error. Restore the POM immediately after the experiment.
- **Test a nonexistent version:** try a nonexistent version on a copy and observe the Maven resolution failure, without confusing it with a Java compiler error.
- **Add a second bean:** create another `Formatter`, observe potential ambiguous injection, and learn how to use `@Qualifier`/`@Primary`.
- **Change scope:** configure `GreetingService` as prototype, retrieve the bean twice, and predict `sameSingleton=false`; rename the label to `sameInstance` for semantic accuracy.
- **Inspect the JDK:** check `java -version`, `javac -version`, and `mvn -version`; explain why a build tool JVM different from the runtime causes errors.
- **Read the dependency tree:** identify the directly declared artifact and transitive modules, and verify the resolved Spring version.
- **Try Gradle:** run the same Java class via the `application` plugin; compare the three stdout lines with Maven.

You have mastered this lesson if you can answer: how `spring-context` differs from `spring-core`; what the three parts of `org.springframework:spring-context:7.0.9` are; why Java 17 fits Spring 7; when to use a BOM; and how to prove the container injected a dependency.

## 11. Summary and References

**Remember:** setting up Spring Core Container is more than downloading a single JAR. Choose the right **`spring-context` module**, a **version line compatible with your JDK and other dependencies**, use Maven/Gradle to resolve transitives, and verify with a real program that creates an `ApplicationContext`.

Official documentation:

- [Spring Framework Artifacts](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Artifacts)
- [Spring Framework Reference](https://docs.spring.io/spring-framework/reference/)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)
- [Spring IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html)
- [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle Dependency Management](https://docs.gradle.org/current/userguide/dependency_management.html)

**Conclusion:** If `mvn -q clean compile exec:java` compiles and prints the exact three lines from Section 5.3, you have a working Core Container environment, ready to continue learning bean registration, DI, scopes, and lifecycle.