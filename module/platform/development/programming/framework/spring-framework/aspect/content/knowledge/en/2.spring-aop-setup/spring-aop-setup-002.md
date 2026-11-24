# Managing Spring Framework-Compatible Dependency Versions When Setting Up Spring AOP

## 1. Goal and scope

When setting up **Spring AOP**, declaring the right libraries is only the first step. A project must also use **mutually compatible Spring Framework modules**, a suitable AspectJ version, and a dependency management mechanism suited to whether the project uses plain Spring Framework or Spring Boot.

This lesson focuses on **dependency versions for proxy-based Spring AOP in Spring Framework**, covering artifact selection, Maven BOMs, Gradle platforms, Spring Boot dependency management, inspecting the dependency graph, resolving conflicts, and verified upgrades. This is Spring AOP configuration knowledge; it does not delve into general Aspect theory or AspectJ compiler/weaving configuration.

After this lesson, you can:

1. Identify the minimal dependencies to use `@Aspect` and `@EnableAspectJAutoProxy` in Spring Framework.
2. Keep `org.springframework` artifacts on the same version via a BOM or Spring Boot.
3. Distinguish dependencies between **Spring Boot 3.x** and **Spring Boot 4.x** when enabling AOP.
4. Read a dependency tree to find unintended pulled-in versions and fix them at the version management source.
5. Prove with a runnable program that the dependencies actually allow advice to execute.

## 2. Identifying what manages the versions of AOP artifacts

When a project uses Spring AOP with `@Aspect`, the three main components are typically **`spring-context`** (container), **`spring-aop`** (proxy infrastructure), and **`aspectjweaver`** (annotation types, `@AspectJ` pointcut parsing and matching). Dependencies may arrive via a starter or transitively; what must be checked is the **version actually resolved** on the runtime classpath.

| Dependency group | Version management source in plain Spring Framework | Version management source in Spring Boot |
| --- | --- | --- |
| `org.springframework:spring-context`, `spring-aop` along with `spring-core`, `spring-beans`, `spring-expression` | A unified `spring-framework-bom` | Boot parent/BOM synchronizes Spring modules |
| `org.aspectj:aspectjweaver` | Declare a compatible AspectJ version separately and verify | Boot BOM manages the version via the AOP/AspectJ starter |
| `org.springframework:spring-aspects` (only for specialized weaving integrations) | Spring Framework BOM, if actually needed | Boot BOM, if used |
| `org.aspectj:aspectjtools` (only when compiling/weaving with AspectJ) | AspectJ version/toolchain, not part of Spring Framework BOM | Not needed for regular Spring proxy AOP |

**The key takeaway of version management:** `org.springframework:spring-*` modules must stay synchronized with a Spring Framework release, whereas AspectJ has its own release cycle and version numbering. For example, `spring-aop:7.0.9` alongside `aspectjweaver:1.9.25.1` is normal when the BOM manages that combination. The presence of `aspectjweaver` **does not automatically enable AspectJ weaving**; an application enabling `@EnableAspectJAutoProxy` still uses Spring proxy AOP.


## 3. Version selection principles

### 3.1. Choose the platform first, then let the platform manage dependencies

- **Spring Boot applications:** choose the **Spring Boot** version suitable for your project, and let the **Spring Boot parent/BOM and plugins manage Spring Framework and AspectJ versions**. Usually do not insert `<version>` or `:version` manually for individual AOP modules.
- **Plain Spring Framework applications:** choose **one Spring Framework version**, import `org.springframework:spring-framework-bom`, and declare `org.springframework` modules **without individual versions**; manage `org.aspectj:aspectjweaver` with an appropriate standalone version.
- **Multi-module projects:** manage the BOM/constraints in one unified location and inspect resolved dependencies in each runnable module.
- **When upgrading:** update the single platform, then compile, run application tests, and inspect the dependency tree; do not upgrade `spring-aop` alone to a different version from `spring-context`.

### 3.2. Examples of published combinations

The table illustrates versions declared in release documentation/metadata. It is **not** a rule for predicting future versions; in real projects you must cross-check the BOM in use.

| Platform | Spring Framework version managed by platform | Spring AOP Starter | AspectJ Weaver managed by platform |
| --- | --- | --- | --- |
| Spring Boot **3.5.16** | **6.2.19** | `org.springframework.boot:spring-boot-starter-aop` | **1.9.25.1** |
| Spring Boot **4.0.8** | **7.0.9** | `org.springframework.boot:spring-boot-starter-aspectj` | Managed by Boot 4.0.8 BOM; inspect effective dependency graph |

With Spring Boot **4.0**, the `spring-boot-starter-aop` starter was **renamed** to `spring-boot-starter-aspectj`. Do not copy Boot 3 dependencies verbatim into a Boot 4 project and assume the old artifact is still managed by the BOM. The new name **does not mean** every application must configure AspectJ bytecode weaving: the starter still provides `spring-aop` and `aspectjweaver` for Spring's `@AspectJ` support.

Spring Framework **6.x and 7.x** both require at least **Java 17**, though Spring 7 also raises the baseline of several related Jakarta technologies; when upgrading from Boot 3 to Boot 4, you must inspect the **entire application**, not just AOP. The listed versions are for learning dependency management; do not upgrade solely from this table while ignoring version support status and project requirements.

**Important compatibility principle:** `org.springframework:spring-*` dependencies within *one application* should normally be aligned to the **exact same release version**, for example all on Spring Framework **7.0.9**. Seeing `spring-context:7.0.9` together with `spring-aop:6.2.19` is a red flag that must be investigated, even if the code still compiles.

## 4. Plain Spring Framework with a Maven BOM

When not using Spring Boot, the way to prevent version drift is to import the **Spring Framework BOM** in the `dependencyManagement` section. Example running on **Java 17+**, Spring Framework **7.0.9**, and AspectJ Weaver **1.9.25.1**:

**Complete `pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-version-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Here, neither `spring-context` nor `spring-aop` needs a version because the BOM manages them. Transitive Spring dependencies like `spring-core` and `spring-beans` are also aligned by the BOM. `aspectjweaver` belongs to a **different group**, so the Spring Framework BOM should not be treated as the version source for this library; we pick an explicit version and verify compatibility.

### 4.1. Program to verify the AOP setup

Project directory:

```text
spring-aop-version-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── MessageService.java
    ├── AuditAspect.java
    └── Main.java
```

**`MessageService.java`**

```java
package example;

public class MessageService {
    public void send() {
        System.out.println("Service: send");
    }
}
```

**`AuditAspect.java`**

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.MessageService.send(..))")
    public void beforeSend() {
        System.out.println("Aspect: before");
    }
}
```

**`AppConfig.java`**

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy
public class AppConfig {
    @Bean
    public MessageService messageService() {
        return new MessageService();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }
}
```

**`Main.java`**

```java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            MessageService service = context.getBean(MessageService.class);
            System.out.println("AOP proxy: " + AopUtils.isAopProxy(service));
            service.send();
        }
    }
}
```

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

Lines printed by `Main` and the example methods, in order:

```text
AOP proxy: true
Aspect: before
Service: send
```

**Why does the example prove dependency compatibility?** If Maven resolves the artifacts, compiles successfully, the context starts up, an AOP proxy is automatically created, and the advice executes properly, then the `spring-context` → `spring-aop` → `aspectjweaver` path works for this case. That result **does not replace** full-application regression testing after an upgrade.

Note: `@EnableAspectJAutoProxy` only enables proxy processing for the corresponding context; `AuditAspect` is registered via `@Bean`. If the libraries are on the classpath but the AOP enablement step or aspect bean registration is missing, resolving dependencies successfully **will not make advice run automatically**.

### 4.2. If using Gradle instead of Maven

In a Java project using **Gradle Groovy DSL**, an equivalent `build.gradle` looks like:

```groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework:spring-framework-bom:7.0.9')
    implementation 'org.springframework:spring-context'
    implementation 'org.springframework:spring-aop'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'example.Main'
}
```

Place the four Java files at the same paths as in section 4.1, then run:

```bash
./gradlew run
```

On Windows PowerShell use `./gradlew.bat run`; this requires the project to have the Gradle Wrapper. The business output remains the same three lines of the example. With Gradle, `platform(...)` provides **version constraints**, yet resolution can choose a higher version when another dependency introduces a stricter requirement; therefore **you must still check the actual versions** after resolution. Avoid forcing `enforcedPlatform` indiscriminately onto a library distributed to other applications.

## 5. Spring Boot applications: prefer Boot starters and BOM

### 5.1. Spring Boot 4.x (Maven Boot 4.0.8 example)

This is a minimal Maven configuration for a Boot 4 application using `@Aspect`. The parent already manages the versions of the required dependencies:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.8</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>boot-aop-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aspectj</artifactId>
        </dependency>
    </dependencies>
</project>
```

A real Boot application still needs other starters according to its features (web, data, test, etc.). The takeaway here is **how to declare AOP and who owns the versions**:

- The `spring-boot-starter-parent:4.0.8` parent uses Boot 4.0.8's dependency management.
- The `spring-boot-starter-aspectj` starter brings in `spring-aop` and `aspectjweaver` matching the platform.
- Do not inject `spring-aop:6.x` or an arbitrary `aspectjweaver` version into a Boot 4 example without a verified reason.
- Spring Boot has auto-configuration supporting AOP; with AspectJ on the classpath, normally **you do not need to write `@EnableAspectJAutoProxy`**. The `@Aspect` class must be registered as a Spring bean via `@Component` or `@Bean`.

If a **Gradle Boot 4** project already configures the Spring Boot plugin and standard dependency management/BOM, the AOP part usually only needs:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

Only omit the starter version when the **BOM is actually being applied**; simply declaring the Spring Boot plugin in a custom build does not always mean dependency management is properly configured. Inspect the resolved graph.

### 5.2. Spring Boot 3.x (Boot 3.5.16 example)

For applications using Spring Boot 3, dependencies are managed by the Boot 3 parent/BOM and the starter keeps its older name:

```xml
<!-- Inside <dependencies> of a project using Boot 3.5.x BOM/parent -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

The equivalent for Gradle Boot 3 (after applying the Boot BOM):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

**Do not mix the two generations:** Boot **3.5.16** manages Spring Framework **6.2.19**, while Boot **4.0.8** manages Spring Framework **7.0.9**. Do not copy Spring Framework 7 configuration directly into a Boot 3 project to "update only AOP". When moving from Boot 3 to Boot 4, execute an application-wide framework upgrade plan and switch to the corresponding AOP starter.

### 5.3. Using only the Spring Boot BOM without the parent

In a Maven project that has its own parent, import the Boot BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.0.8</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Then add `spring-boot-starter-aspectj` **without a version** under `<dependencies>`. Importing the BOM **only manages versions**; it does not automatically supply compile/run plugins, Boot parent defaults, or add application dependencies that were not declared.

In Gradle, you can use `platform('org.springframework.boot:spring-boot-dependencies:4.0.8')` inside `dependencies` to manage versions for the related dependencies. Projects using the `io.spring.dependency-management` plugin have their own BOM import syntax; do not stack multiple management mechanisms without understanding their precedence order and resolved outcome.

## 6. Checking **resolved** versions, not just declared versions

A `pom.xml` or `build.gradle` file that looks right can still suffer conflicts from transitive dependencies, other parents/BOMs, constraints, explicit versions, plugins, or submodules.

### 6.1. Maven

Run inside the exact Maven module containing Spring AOP:

```bash
mvn dependency:tree
mvn help:effective-pom
```

Look for these entries:

```text
org.springframework:spring-aop
org.springframework:spring-context
org.springframework:spring-core
org.springframework:spring-beans
org.aspectj:aspectjweaver
```

Verify that Spring Framework artifacts resolve to **the same version** (in the plain Maven example, `7.0.9`), and that `aspectjweaver` is actually on the classpath. If you suspect the BOM is not being applied, check `effective-pom` and its `dependencyManagement` section. Pay attention to versions omitted by Maven due to version mediation; looking only at direct dependencies is not enough.

### 6.2. Gradle

Run on the application module, for example:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-aop --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-context --configuration runtimeClasspath
./gradlew dependencyInsight --dependency aspectjweaver --configuration runtimeClasspath
```

On Windows use `./gradlew.bat` or run the task with the module path, such as `:app:dependencyInsight`, when `app` is the application Gradle subproject.

Example meaning of a hypothetical output:

```text
org.springframework:spring-aop:6.2.19 -> 7.0.9
```

The `->` symbol in the Gradle dependency tree indicates **the requested version was replaced by the resolved version**. Find the **reason that version was chosen** via `dependencyInsight`; do not treat this line as automatic proof of a bug if all Spring modules are ultimately aligned and that combination is supported.

### 6.3. Checking AOP presence and operation

Even when the graph is valid, check `AopUtils.isAopProxy(bean)` on an appropriate bean or write a test calling an advised method. If the program fails with `ClassNotFoundException`, `NoClassDefFoundError`, or `NoSuchMethodError`, inspect **which class is missing**, the actual versions, the runtime classpath, and the packaging step. These errors **may** stem from dependency mismatches, but do not attribute the cause from the exception name alone.

## 7. Common configuration errors and fixes

| Symptom | Cause worth checking | Resolution |
| --- | --- | --- |
| `NoClassDefFoundError` related to `org.aspectj.*` | Missing `aspectjweaver` on the runtime classpath, wrong scope, or packaging excluded the dependency | Add the starter for the right Boot generation or the AspectJ dependency in a plain Spring app; inspect `runtimeClasspath` |
| `NoSuchMethodError` appears after upgrading Spring | Multiple `spring-*` versions mixed or a third-party library is incompatible | Cross-check the dependency tree; align the Spring BOM/platform; review integration libraries |
| Maven reports missing version for `spring-boot-starter-aop` on Boot 4 | Using the old artifact no longer managed by the Boot 4 BOM | Switch to `spring-boot-starter-aspectj` when applying the Boot 4 BOM |
| Spring context starts but `@Before` does not execute | Aspect is not a bean, AOP is not enabled, pointcut does not match, or call bypasses proxy | Check aspect declaration, `@EnableAspectJAutoProxy`/Boot auto-configuration, proxy, and call path |
| Both Spring 6 and Spring 7 appear in the dependency graph | Direct override, different parent/BOM, transitive dependencies, or resolution rules | Pick one consistent platform, remove redundant version overrides, and inspect the effective graph |
| Build compiles fine but fails at runtime on a different JDK | Java/bytecode baseline of the framework and libraries does not match the runtime environment | Check `java -version`, compiler/toolchain configuration, and the actual runtime JVM |

**Three mistakes to avoid:**

1. **Writing versions on every dependency:** easily causes `spring-aop`, `spring-context`, and other Spring modules to drift across releases. Use a BOM/parent first.
2. **Assuming adding `spring-aspects` replaces `spring-aop`:** they serve different roles; proxy-based Spring AOP does not need `spring-aspects` by default.
3. **Upgrading AspectJ or Spring AOP independently of the platform:** do not conclude compatibility merely because Maven/Gradle downloaded the artifacts cleanly.

## 8. Safe Spring AOP upgrade workflow in a project

1. **Identify the version management source:** Spring Boot parent/BOM, Spring Framework BOM, Gradle platform, dependency management plugin, corporate parent, or version catalog.
2. **Record the current graph:** note the versions of `spring-aop`, `spring-context`, `spring-core`, `spring-beans`, `aspectjweaver`, and JDK; in multi-module builds, inspect the runnable module.
3. **Choose a supported version set:** upgrade Boot as a complete platform, or swap a unified Spring Framework BOM when not using Boot; verify the JDK baseline.
4. **Keep dependency declarations simple:** remove unnecessary version overrides; pick the starter matching Boot 3 or Boot 4.
5. **Resolve and cross-check again:** Maven `dependency:tree`/`help:effective-pom` or Gradle `dependencies`/`dependencyInsight`. Do not rely only on build file text.
6. **Run Spring AOP tests:** at least one bean with a matching `@Aspect` and a call through the proxy; also run the application's integration tests to catch compatibility changes.
7. **Consider the upgrade complete only when both build and runtime pass:** ensure the packaged artifact contains the required dependencies and the deployment environment runs a compatible Java version.

### Practice exercise

A project uses Boot `4.0.8` and declares `spring-boot-starter-aop`, `spring-aop:6.2.19`, and `aspectjweaver:1.9.25.1` at the same time. Identify what needs to be fixed.

**Answer:** Use Boot 4's `spring-boot-starter-aspectj` starter; remove the `spring-aop:6.2.19` version declaration because Boot 4.0.8 manages Spring Framework `7.0.9`; remove the manual `aspectjweaver` declaration if the starter already provides it and there is no special requirement. Finally, inspect the Maven/Gradle resolved graph and run a real `@Aspect` test. Pinning `aspectjweaver:1.9.25.1` might happen to match the BOM-managed version, yet it introduces an extra override point that can easily drift during future Boot upgrades.

## 9. Official references for version cross-checking

- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): Spring proxy configuration and AspectJ classpath requirements.
- [Spring Framework — Spring Framework Artifacts](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Artifacts): artifacts, dependencies, and version-specific overrides.
- [Spring Framework BOM on Maven Central](https://central.sonatype.com/artifact/org.springframework/spring-framework-bom): check actual BOM releases.
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): Spring and AspectJ versions managed by Boot 3.5.
- [Spring Boot 4.0 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html): Spring and starters managed by Boot 4.0.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): AOP/AspectJ starter rename.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): Spring AOP auto-configuration and proxies.
