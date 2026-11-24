# Using a BOM When a Spring Boot Project Already Has Its Own Maven Parent

## 1. Real-World Problem and Goals

In a simple Spring Boot project, Maven typically inherits `org.springframework.boot:spring-boot-starter-parent` to receive a set of defaults: library versions, Java/compiler configuration, Maven plugin management, packaging mechanics, and resource filtering rules. However, enterprise systems often have an **internal parent POM** enforcing JDK, plugin versions, repositories, quality gates, or conventions. A Maven project can have **only one direct parent**. So how do you keep `company-parent` while still receiving Spring Boot's curated library versions?

The solution is to **import the Spring Boot BOM** (`org.springframework.boot:spring-boot-dependencies`) into `<dependencyManagement>` of the project or an appropriate parent, keeping the chosen `<parent>`. The BOM provides **version management** for dependencies; plugin configuration and build lifecycle must be controlled separately.

After this lesson, you will be able to:

- Distinguish `<parent>`, `<dependencyManagement>`, BOM import, and `<dependencies>`.
- Know when to place the Spring Boot BOM in a project, module, or intermediate parent.
- Configure a complete POM when a corporate parent is already present and `spring-boot-starter-parent` is not used.
- Understand why importing a BOM does not automatically configure the Spring Boot Maven Plugin, Java compiler, or `repackage`.
- Inspect the effective POM, dependency tree, and executable JAR.
- Resolve version conflicts among BOMs, parents, and direct dependencies; avoid incorrect overrides.
- Upgrade Spring Boot BOM and Maven Plugin versions in a verifiable change.

**Examples use Spring Boot 3.5.16 and Java 17** for concrete versions, without claiming these are right for every project. When applying to a real system, choose a Boot release, Java, and Maven version supported by your organization, and consult the official documentation for that release line.

## 2. Three Concepts That Must Be Separated

### 2.1. Maven Parent

A project's parent is declared in `<parent>`:

~~~xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
</parent>
~~~

Maven constructs the **effective POM** by merging configuration from the Super POM, inherited parents, active profiles, and the module's POM. A custom parent can manage plugin versions, compiler, tests, repositories, properties, and dependency management.

A Maven project **has only one `<parent>` element**; you cannot specify both `company-parent` and `spring-boot-starter-parent` as two direct parents simultaneously.

### 2.2. Dependency Management

`<dependencyManagement>` supplies versions, scopes, or managed configuration for dependencies when they are used. It **does not automatically add libraries to the classpath**.

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>sample-library</artifactId>
            <version>1.2.3</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

This is an illustrative POM snippet only. `sample-library` is not automatically downloaded and placed on the classpath just because it appears in this management section. To use it, the project still must declare the dependency in `<dependencies>`, or it must be pulled in transitively.

### 2.3. BOM Import

A BOM (Bill of Materials) is a **POM artifact** that provides a curated set of dependency management entries. Spring Boot publishes `spring-boot-dependencies` to manage versions of Spring modules, starters, and third-party libraries compatible with that Boot release.

Use a dependency with **`<type>pom</type>`** and **`<scope>import</scope>`** inside **`<dependencyManagement>`** to bring managed dependencies from the BOM into the project:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`scope=import` is only meaningful for dependencies of type `pom` inside `dependencyManagement`; it is not `runtime`, `compile`, or `test`. It does not turn the BOM into a runtime library and does not activate a Spring Boot application by itself.

### 2.4. Visualizing the Configuration Flow

~~~text
                         boot-app/pom.xml
                                |
          <parent> com.example:company-parent:1.0.0
                                |
                      Maven POM inheritance
            compiler / surefire / company conventions
                                |
       <dependencyManagement> in app or parent
                                |
          import spring-boot-dependencies:3.5.16
                                |
             version management for libraries
                                |
             <dependencies> actually used by app
             starter-web, starter-test, jdbc driver...
                                |
                  Maven resolves dependency graph
                                |
                    compile -> test -> package
~~~

Parent and BOM answer **two different questions**: "Who does the module inherit build rules from?" and "Where is the curated set of library versions managed?".

## 3. Standard Syntax When Using a Corporate Parent

Suppose a child POM already has its own parent:

~~~xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

In **that same project**, add the BOM import:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Then declare dependencies as usual:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Both starters **omit `<version>`** because the Spring Boot BOM manages them. However, **the BOM does not automatically create these `<dependency>` entries**: importing only the BOM without declaring the Web starter will not give the project Spring MVC or an embedded server.

Maven allows storing the BOM version in a project property:

~~~xml
<properties>
    <spring-boot.version>3.5.16</spring-boot.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`${spring-boot.version}` is **standard Maven property interpolation syntax**. Defining this property in the POM to select the **BOM's own version** is valid; it differs from attempting to override a property **inside an already imported BOM**, which is covered in Section 8.

## 4. How Does Importing a BOM Differ from Inheriting `spring-boot-starter-parent`?

| Capability | Inheriting `spring-boot-starter-parent` | Own Parent + Spring Boot BOM Import |
| --- | --- | --- |
| Direct parent | Boot starter parent | Organization's parent |
| Managed dependency versions from Spring Boot | Yes | Yes |
| Declare starters without version | Yes | Yes, when managed by the BOM |
| Maven plugin management of Boot parent | Yes via inheritance | **Not imported along** |
| `spring-boot:repackage` goal bound by starter parent | Yes | **Must configure manually** when an executable archive is needed |
| Compiler/JDK defaults of Boot parent | Yes | Own parent or module must ensure them |
| Encoding, `-parameters`, Boot parent resource filtering | Has default configurations | Does not automatically receive the same defaults |
| Ability to keep corporate parent | Cannot simultaneously be direct parent | Yes |

Without the Spring Boot parent, **dependency version management remains intact** thanks to the BOM, but Spring Boot packaging and plugin versions must be explicitly declared or properly managed by the corporate parent.

Also do not think of **BOM import** as "adding all Spring modules to the classpath": `dependencyManagement` only manages dependencies that may be resolved later.

## 5. Complete, Runnable Example: Custom Parent + Boot Application

Create a sample project consisting of a parent POM and a child module as follows:

~~~text
company-demo/
├── pom.xml
└── boot-app/
    ├── pom.xml
    └── src/
        ├── main/java/com/example/bootapp/
        │   ├── BootAppApplication.java
        │   └── PingController.java
        └── test/java/com/example/bootapp/
            └── BootAppApplicationTests.java
~~~

**Run prerequisites:** JDK 17 or a newer compatible JDK, suitable Maven 3.9+, Maven repository access, and port 8080 free of other services. The example declares a local parent so **it does not require fetching `company-parent` from an internal repository**.

### 5.1. Complete Parent POM: `company-demo/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>boot-app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                    <configuration>
                        <release>17</release>
                        <parameters>true</parameters>
                    </configuration>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.2.5</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

Meaning:

- The parent has `<packaging>pom</packaging>`, making it a configuration/aggregator module rather than a JAR application.
- `<modules>` specifies child modules in the Maven reactor build; it **does not replace** the child declaring `<parent>`.
- `<pluginManagement>` holds default versions/compiler settings for Maven plugins. Lifecycle-bound plugins (such as compiler and surefire for JAR packaging) use the managed configuration when executed. `pluginManagement` does not cause arbitrary goals to run automatically.
- The compiler uses `<release>17</release>` and `<parameters>true</parameters>`. These are examples of defaults a corporate parent should consider managing itself.
- Surefire 3.2.5 supports running JUnit Jupiter in the sample module.

In a real organization, **do not modify a shared parent just for one module if you do not own that parent**; place required settings in the module or an intermediate parent per project conventions.

### 5.2. Complete Child POM: `company-demo/boot-app/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>company-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>boot-app</artifactId>
    <packaging>jar</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>3.5.16</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>3.5.16</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

This is the key structure of the lesson:

1. The child **inherits only `company-parent`**, without a second Spring Boot starter parent.
2. The child imports the **Boot BOM** to obtain versions of dependencies like `spring-boot-starter-web`.
3. The child explicitly adds **`spring-boot-maven-plugin`**, pins its version, and binds the `repackage` goal so `mvn package` generates an executable Spring Boot JAR.
4. The child inherits compiler and Surefire settings from the example's corporate parent.

`relativePath` points to the local parent `../pom.xml`. If the actual parent is published in a repository and does not reside in the parent directory, the project can use `<relativePath/>` to avoid Maven looking in the wrong default path; you must still ensure repositories/credentials can resolve the parent.

### 5.3. Java: Main Application Class

Create `boot-app/src/main/java/com/example/bootapp/BootAppApplication.java`:

~~~java
package com.example.bootapp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BootAppApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootAppApplication.class, args);
    }
}
~~~

This class is valid Java source when compiled inside a Maven project with Boot dependencies. It will not compile standalone with `javac BootAppApplication.java` because the Spring imports require the Maven-resolved classpath.

### 5.4. Java: HTTP Controller

Create `boot-app/src/main/java/com/example/bootapp/PingController.java`:

~~~java
package com.example.bootapp;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

The controller resides in the same package as the application so component scanning finds it. Spring Web supplies the required annotations and web runtime. On the default port 8080 when running cleanly, HTTP GET `/ping` returns the exact response body `pong`.

### 5.5. Java: Context Startup Test

Create `boot-app/src/test/java/com/example/bootapp/BootAppApplicationTests.java`:

~~~java
package com.example.bootapp;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class BootAppApplicationTests {

    @Test
    void contextLoads() {
        // Passes if the Spring ApplicationContext can be initialized.
    }
}
~~~

JUnit Jupiter and Spring Boot Test are supplied by `spring-boot-starter-test` on the **test classpath**. Surefire runs the test during the `test` phase. Do not expect identical stdout from JUnit across setups; log lines and formatting vary by plugin and environment.

### 5.6. Commands and Verifiable Output

Open a terminal in the `company-demo/` root directory:

~~~bash
java -version
javac -version
mvn -version
mvn clean package
~~~

Upon a successful build, the expected executable JAR is `boot-app/target/boot-app-1.0.0.jar` based on the example's artifact/version. Run:

~~~bash
java -jar boot-app/target/boot-app-1.0.0.jar
~~~

From another terminal:

~~~bash
curl -s http://localhost:8080/ping
~~~

The **response body**, if running on the default port, is:

~~~text
pong
~~~

Spring Boot and Maven logs vary across machines, so assert only on the endpoint response body. If port 8080 is occupied or `server.port` is changed, use the actual port.

Command to build the module via the reactor:

~~~bash
mvn -pl boot-app -am clean package
~~~

`-pl` selects the `boot-app` module; `-am` builds required reactor projects. Because the manual example has no Maven Wrapper, `mvn` is used. If a real project already includes a Wrapper, use `./mvnw` (Linux/macOS) or `.\mvnw.cmd` (Windows PowerShell) with the corresponding arguments.

## 6. Why Must You Still Declare the Maven Plugin When Importing the BOM?

The `spring-boot-dependencies` BOM manages **dependencies**. When imported under `<dependencyManagement>`, Maven **does not import the `pluginManagement` of the Spring Boot parent** and does not automatically bring in executions provided by the starter parent.

Specifically:

- `spring-boot-maven-plugin` is a **Maven build plugin**, not a regular application dependency.
- If the corporate parent does not manage this plugin's version, the project must pin the version in `<build><plugins>` or an appropriate `<pluginManagement>`.
- If you want an executable JAR/WAR from `mvn package`, the `repackage` goal must be bound. With the Boot starter parent, this execution is already pre-configured; with a custom parent, you must configure it explicitly or inherit it from an internal parent with an equivalent setup.
- Java compiler release, `-parameters`, resource filtering, and plugin versions must also be supplied by the corporate parent or module; the BOM does not set them.
- If a project only writes a **Java library** using Spring Boot dependencies without needing to run as a Boot application, adding `spring-boot-maven-plugin` is not required.

A standalone snippet to pin the plugin and bind executable packaging:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.5.16</version>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

This is a POM snippet, **not a standalone POM**. If the custom parent already manages the plugin and execution, check the effective POM to avoid unnecessary duplicate configuration.

## 7. Distinguishing BOM-Managed Versions from Actually Resolved Versions

### 7.1. Inspecting the Effective POM

The Maven Help Plugin can output the effective POM after inheritance/import/profiles:

~~~bash
mvn -pl boot-app help:effective-pom
~~~

When reading the output, look for `dependencyManagement`, `spring-boot-starter-web`, `spring-boot-maven-plugin`, compiler, Surefire, and `repackage`. Focus on the **`boot-app` module**, since the root parent has `pom` packaging and is not where the Boot app runs.

You can write the output to a file (for self-practice; exact path depends on working directory/module):

~~~bash
mvn -pl boot-app help:effective-pom -Doutput=effective-pom.xml
~~~

The Maven Help Plugin prints the written file path; follow the actual message to locate it. Seeing the BOM in the source POM does not prove all managed dependencies are in effect; the effective POM helps verify configuration after Maven merges all sources.

### 7.2. Inspecting the Dependency Tree

~~~bash
mvn -pl boot-app dependency:tree
mvn -pl boot-app dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web
~~~

The first command shows the module's dependency graph; the second filters by the starter coordinates. On Windows PowerShell, wrap `-Dincludes=...` in double quotes if the shell parses arguments differently than expected.

Example of the **output line format**, not a fixed full log:

~~~text
[INFO] com.example:boot-app:jar:1.0.0
[INFO] \- org.springframework.boot:spring-boot-starter-web:jar:3.5.16:compile
~~~

If an unexpected version differs from the BOM version in practice, inspect parent inheritance, other BOMs, explicit dependency management, direct dependency versions, and dependency mediation. Do not randomly tweak versions just to force output to match expectations.

### 7.3. Checking the Executable Artifact

~~~bash
mvn -pl boot-app -am clean package
jar tf boot-app/target/boot-app-1.0.0.jar
~~~

A typical executable Spring Boot JAR contains `BOOT-INF/classes/` (application code) and `BOOT-INF/lib/` (libraries), plus the Spring Boot loader. If only a regular JAR is built and `java -jar` fails to run, check the Spring Boot Maven Plugin and the `repackage` execution. `mvn package` can succeed without the Boot plugin configured, yet the artifact will lack an executable layout.

## 8. Overriding Dependency Versions When Importing a BOM

### 8.1. Understanding the Limitation of Property Overrides

When **inheriting** `spring-boot-starter-parent`, certain property-controlled versions can be overridden by the child project per Boot guidance. However, when only **importing** `spring-boot-dependencies`, you **cannot expect** defining a property with the same name as an internal BOM property to override all managed versions.

For example, merely adding:

~~~xml
<properties>
    <slf4j.version>2.0.17</slf4j.version>
</properties>
~~~

is not a reliable way to override the SLF4J version managed by an imported BOM. **Do not assume a version has changed without verifying via effective POM and dependency tree.**

### 8.2. Overriding with an Explicit `dependencyManagement` Entry

When you must use a verified version different from the BOM, Spring Boot recommends placing the managed dependency **before the BOM import entry**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

**The SLF4J version here illustrates syntax only**; never treat forcing a version as general advice. Swapping low-level libraries can cause `NoSuchMethodError`/`ClassNotFoundException` or conflicts with Spring modules. Verify compatibility, security advisories, and end-to-end tests.

A version declared directly under `<dependencies>` can also override the managed version for that direct dependency; however, this can leave the graph inconsistent when multiple components share a library. For consistent management across transitive paths, `dependencyManagement` is clearer.

## 9. When the Parent Manages Dependencies or the Project Imports Multiple BOMs

Organizations may already import a company BOM, a framework BOM, or the Spring Cloud BOM. These BOMs may manage the same artifact coordinates.

### 9.1. Import Order

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>company-dependencies</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

When two BOMs are imported **at the same POM level** and manage the same dependency, **the BOM imported earlier generally takes precedence** for overlapping coordinates, provided the current POM has no explicit overriding managed entry. Official Maven docs give the example: importing BOM X then Y, both managing artifact A, selects the definition from X.

However, do not deduce that "the earlier BOM always wins in every situation": inherited `dependencyManagement` from a parent, direct child declarations, explicit dependency versions, and transitive paths also affect the **effective** version. Verify with `help:effective-pom` and `dependency:tree`.

### 9.2. Place the BOM in the Parent or in Individual Modules?

**Place in a shared parent:** sensible when all modules inheriting that parent must use the same Spring Boot release line and the parent is maintained by the owning team. Changing the parent can affect many modules, so review the blast radius.

**Place in individual Boot modules:** sensible when a shared parent serves Boot apps, plain Java libraries, and other services alike. Each Boot module imports the BOM itself, managing versions without imposing them on non-Boot modules.

**Intermediate parent:** if there are multiple Boot modules, you can create a module-level parent inheriting the corporate parent and holding Boot BOM/Boot plugin policies; application modules then inherit that intermediate parent. Each module still has **only one direct parent**, while the inheritance chain can span multiple levels.

If using Spring Cloud, choose a release train compatible with your Spring Boot version and import the Spring Cloud BOM per official documentation. **Do not add the Spring Cloud BOM** if the project does not use Spring Cloud.

## 10. Important Notes on Maven Versions, Resources, and Deployment

- **Java/JDK:** Spring Boot 3.5 requires at least Java 17. Your custom parent must configure a suitable compiler plugin/release, and Maven must run on a compatible JDK. In the example, the parent sets release 17; CI can run JDK 17 or a newer compatible JDK.
- **Maven plugins:** Importing a BOM does not update Maven Compiler/Surefire/Resources/Jar/War Plugins. Inspect `mvn -version` and the effective POM when build errors occur.
- **Resource filtering:** The Spring Boot starter parent configures filtering rules for `application.properties`/`application.yml`; a corporate parent might use different Maven delimiters. If Spring placeholders like `${spring.datasource.url}` are modified or corrupted during `package`, inspect filtering configuration rather than blaming the BOM.
- **Executable archive:** Spring Boot Maven Plugin `repackage` builds an executable layout. For a WAR deployed to an external container, pick the right packaging and handle container dependencies per contract rather than copying the JAR setup verbatim.
- **Do not try to manage plugin versions with the dependency BOM:** `spring-boot-maven-plugin` version must be configured in `<build>` or parent `pluginManagement`. Use the matching Boot release version as in the example for predictability.
- **Maven Wrapper:** if a project already includes `mvnw` and `mvnw.cmd`, prefer the wrapper in CI and on developer machines. The wrapper pins only the Maven runtime; appropriate Java and repository access are still required.

## 11. Safe Upgrade Path for the Spring Boot BOM

When upgrading the Spring Boot line in a project with a custom parent, inspect the **BOM**, **Boot Maven Plugin**, **JDK**, **compiler/test plugins**, and **any potentially overlapping BOMs**.

1. Choose a supported Spring Boot release matching system requirements.
2. Read the system requirements for that exact release: Java, Maven, and major breaking changes.
3. Check the corporate parent: does it lock Maven plugin versions or Java release; does its `dependencyManagement` override Boot libraries?
4. Update the `spring-boot-dependencies` BOM version in the module or BOM-owning parent.
5. Update/verify the `spring-boot-maven-plugin` version and `repackage` execution; do not update only the BOM.
6. Compare the effective POM before/after and use `dependency:tree` to inspect versions of starters and key dependencies.
7. Run unit/integration tests, build the executable archive, and run the packaged artifact in a realistic deployment setup.
8. Only after QA passes, update CI, metadata/version management per team process.

Do not arbitrarily bump all of Spring Framework or Jackson just to "keep up" with Boot; the Boot BOM is engineered to coordinate many artifacts together. Overrides should be done only when needed and verified.

## 12. Common Errors and Diagnosis

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `Non-resolvable parent POM` | Custom parent has wrong coordinates/version, missing in local/remote repo, or wrong `relativePath` | Verify parent GAV, path, and repository credentials first |
| Maven requires `<version>` for `spring-boot-starter-web` | BOM not imported, wrong `type/scope`, or source POM unresolved | Check `dependencyManagement`, `type=pom`, `scope=import`, and effective POM |
| Spring Web missing from compile classpath despite BOM import | BOM only manages versions, does not add libraries | Add the actual starter/dependency under `<dependencies>` |
| `mvn package` succeeds but `java -jar` fails to run | Missing Spring Boot Maven Plugin or `repackage` | Pin plugin version and bind goal; verify `BOOT-INF` |
| Unexpected plugin version changes | Corporate parent/BOM does not manage the plugin version as assumed | Inspect `build/plugins` and `pluginManagement` in effective POM |
| `invalid target release: 17` | JDK running Maven is older than compiler Java release | Check `mvn -version` and `JAVA_HOME` |
| JUnit Jupiter tests do not run | Surefire/plugin configuration too old or wrong provider | Verify Surefire 3.x and test classpath |
| Setting `<slf4j.version>` does not change the version | Importing BOM does not enable internal property overrides like inheritance | Declare explicit `dependencyManagement`, check effective POM |
| Jackson/Spring version differs from expected BOM | Parent BOM, direct declaration, or other management takes precedence | Inspect effective POM, dependency tree, and import order |
| App runs locally but throws `NoSuchMethodError` on deploy | Incompatible dependency overrides or mixed artifact versions | Audit dependency tree, BOM versions, actual package, and CI |
| Spring properties corrupted during packaging | Corporate parent resource filtering differs from Boot parent | Check Maven Resources Plugin and delimiter; avoid leaking secrets while debugging |
| Unable to download BOM | Repository/proxy/credentials issue or nonexistent version | Confirm artifact/version and `settings.xml`, check connectivity |

### Isolation Strategy

**Parent errors:** fix `<parent>`/`relativePath`/repositories first, because Maven cannot even build the effective POM to apply the BOM otherwise.

**Dependency version errors:** inspect `dependencyManagement` and `help:effective-pom`; distinguish managed versions from dependencies actually added to the classpath.

**Build task errors:** check plugin versions and lifecycle, especially Spring Boot Maven Plugin `repackage`.

**Runtime errors:** check JDK, dependencies inside the JAR/WAR, entrypoint, configuration, and actual deployment output. Do not assume every runtime bug comes from the BOM.

## 13. Self-Check Exercises

**Question 1.** A project has `company-parent`, and a developer adds `spring-boot-starter-parent` as a second parent. Will Maven accept this?  
**Answer:** No. Only one direct parent is allowed; keep the corporate parent and import the `spring-boot-dependencies` BOM.

**Question 2.** If you only import the BOM without declaring `spring-boot-starter-web`, will the HTTP server appear automatically?  
**Answer:** No. A BOM only provides version management metadata.

**Question 3.** When using a custom parent + BOM import, do you need an explicit version for Spring Boot Maven Plugin?  
**Answer:** Yes, if the custom parent does not already manage the plugin version. Importing a BOM does not bring in the starter parent's `pluginManagement`.

**Question 4.** `mvn package` builds a regular JAR, and `java -jar` reports a missing executable manifest. What should you inspect?  
**Answer:** Spring Boot Maven Plugin, the `repackage` goal, and the executable archive layout.

**Question 5.** You want to change a library version managed by an imported BOM, but a property override has no effect. What do you do?  
**Answer:** Add an explicit managed dependency entry, test compatibility, and inspect the effective POM and dependency tree.

**Question 6.** Two BOMs in the same POM manage the same artifact. What matters?  
**Answer:** Import order and any management declarations in parent/child; do not guess precedence—verify the effective version.

## 14. Adoption Checklist

- [ ] Selected the right corporate parent and avoided declaring two `<parent>` elements.
- [ ] Imported `spring-boot-dependencies` using `type=pom` + `scope=import` in `dependencyManagement`.
- [ ] Declared needed starters and dependencies under `<dependencies>`, omitting versions where managed by the BOM.
- [ ] Checked whether the parent or another BOM overrides Spring Boot dependency versions.
- [ ] Verified Maven Compiler Plugin, Surefire, Maven version, and Java release.
- [ ] For executable apps, configured the version and `repackage` on Spring Boot Maven Plugin.
- [ ] Verified the effective POM and dependency tree for the specific module.
- [ ] Built and ran tests, checked `BOOT-INF`, and executed the artifact to verify runtime behavior.
- [ ] Have a process to keep the Boot BOM and plugin synchronized when upgrading.

## 15. Official References

- Spring Boot 3.5 Maven Plugin — Using the Plugin / Without the Parent POM: https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Maven — Introduction to the Dependency Mechanism (importing BOM): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven POM Reference: https://maven.apache.org/pom.html
- Maven Help Plugin — Effective POM: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Maven Dependency Plugin — Dependency Tree: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html

**Expected outcome:** The project retains the organization's Maven parent, uses the proper managed dependency versions from the Spring Boot BOM, and directly controls Maven plugins and executable packaging. Final verification rests on the effective POM, dependency tree, and actual packaged artifact—not merely on a `<dependencyManagement>` declaration.
