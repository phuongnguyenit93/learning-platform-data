# Inheriting `spring-boot-starter-parent` and Customizing Build Properties

## 1. Problem: Why Do Maven-Based Spring Boot Applications Need a Parent POM?

A Spring Boot application typically needs the Spring Framework, web libraries, JSON, logging, testing libraries, and multiple Maven plugins to compile, test, and build JARs. If developers manually picked versions for every library and plugin, they would have to check compatibility across all of them by hand. Two teammates could write two different POMs for the same requirement; a single upgrade could also accidentally introduce dependency conflicts or alter packaging behavior.

**spring-boot-starter-parent** is a **Maven parent POM** provided by Spring Boot. When a project declares it in the **parent** tag, the project inherits Maven configuration prepared by Spring Boot: versions of common dependencies, various plugin configurations, Java compiler settings, encoding, resource filtering, and configuration supporting executable JAR/WAR creation.

As a result, the application's POM focuses more on **which dependencies the project actually needs** and **what it wants to customize**, instead of copying a long list of versions, goals, and build settings. The parent helps reduce boilerplate and increase consistency; it does not guarantee that every third-party library outside the ecosystem or every arbitrary change will be compatible.

### Lesson Objectives

- Understand how **parent POM inheritance** differs from adding a dependency or importing a BOM.
- Write the **parent** and **properties** sections in **pom.xml** properly.
- Know the defaults commonly provided by the Spring Boot parent and the scope within which they can be overridden.
- Distinguish managed dependency versions, configured plugins, Java target, and runtime configuration.
- Use **help:effective-pom**, **help:evaluate**, and **dependency:tree** to verify actual values.
- Know when to use the parent and when to import **spring-boot-dependencies** because the project already has another parent.

## 2. Relationship Between `spring-boot-dependencies`, `spring-boot-starter-parent`, and the Application

Typical inheritance diagram:

~~~text
org.springframework.boot:spring-boot-dependencies
              |
              | parent / inheritance
              v
org.springframework.boot:spring-boot-starter-parent
              |
              | <parent> in the project's pom.xml
              v
com.example:parent-demo
              |
              +--> <dependencies>: starter-web, starter-test, ...
              +--> <properties>: java.version, encoding, ...
              +--> <build><plugins>: spring-boot-maven-plugin, ...
~~~

**spring-boot-dependencies** contains the dependency management curated by Spring Boot so common libraries work together with that Spring Boot release. **spring-boot-starter-parent** inherits this management set and adds defaults, plugin configurations, resource filtering, and goal bindings related to building applications. The **application POM** sets this parent to receive those values and can override only the parts it genuinely needs to change.

Do not confuse three concepts:

| Component | Where Is It Placed? | Primary Effect |
| --- | --- | --- |
| **spring-boot-starter-parent** | **project > parent** | Inherits POM configuration, dependency management, plugin management, and build defaults |
| **spring-boot-dependencies** | Usually an indirect parent; or **dependencyManagement** with **type=pom, scope=import** | Manages dependency versions; when imported, brings in only the BOM's dependency management |
| **spring-boot-starter-web** (or another starter) | **dependencies** | Brings in libraries needed for an application capability, such as web MVC |

A parent POM **does not automatically place all starters on the classpath**. To write a web application, you still declare the web starter; to use JDBC, Batch, Security, or Test, you declare the corresponding dependencies. The parent determines many **versions**, while the **dependencies** element determines **which libraries the application uses**.

## 3. Declaring the Parent Properly

Examples in this lesson use the **Spring Boot 3.5** line, specifically the published documentation version **3.5.16** for consistent examples:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>
~~~

Meaning:

- **groupId + artifactId** specifies the parent POM published by Spring Boot.
- **version** selects the Spring Boot version the project uses as its baseline for dependencies/build. In the example this is 3.5.16; in real projects, choose the release line/patch according to your upgrade policy and check that line's documentation.
- **relativePath/** left empty is standard for a parent published on a Maven repository. Maven will not attempt to read a default parent from the relative path **../pom.xml** in the sibling/parent folder, avoiding accidentally picking up an unintended parent POM.

A Maven project has only **one parent element**. You cannot directly inherit both **spring-boot-starter-parent** and another **corporate-parent** in the same POM. If your organization requires a corporate parent, use the BOM approach in a later section and configure required plugins manually.

**A parent is build configuration, not a runtime dependency.** It does not appear as a functional library called from Java application code; part of the parent's role is determining the effective versions of dependencies declared in the project.

## 4. What the Parent Commonly Provides Out of the Box

According to the Spring Boot 3.5 Maven Plugin guide, the parent provides the following defaults:

| Area | Inherited Value/Capability | Benefit |
| --- | --- | --- |
| **Java** | Default Java level 17; uses compiler release per parent configuration | Provides a consistent baseline for Java code |
| **Encoding** | UTF-8 for source/resources | Reduces character encoding differences across environments |
| **Compiler** | Compiles with **-parameters** | Preserves parameter name metadata useful for binding/reflection |
| **Dependencies** | Managed versions from **spring-boot-dependencies** | Eliminates the need to specify versions for most Spring Boot starters and managed libraries |
| **Plugins** | Default configuration/versions for many compatible Maven plugins | Reduces the need to declare plugin versions manually |
| **Packaging** | Pre-configured **repackage** execution id for the Spring Boot Maven Plugin | When the plugin is declared, the `package` phase can build an executable JAR/WAR |
| **Resources** | Sensible filtering for application configuration | Allows substituting Maven property values into `application.properties/yml` at build time |
| **Native** | Pre-configured **native** profile to support Native Image builds | Avoids manually configuring the entire foundation when native builds are needed |

Do not conclude **"declaring the parent makes Maven automatically produce an executable JAR"**. For a Maven application project, you still need to declare **spring-boot-maven-plugin** under `plugins` so the **repackage** execution is activated by convention. If you only have the parent without declaring the plugin, do not assume the `package` output is a Boot executable JAR.

Similarly, **pluginManagement** typically defines default versions/configurations for plugins; it does not mean every plugin inside it is automatically invoked. Whether a plugin goal actually runs depends on the Maven lifecycle, execution bindings, packaging, and declared/activated plugins.

## 5. Complete Example: Maven POM Inheriting Parent and Changing Java Target

The following example builds a small HTTP application with a **GET /info** endpoint. To run the Wrapper commands directly, create the Maven project via **Spring Initializr** or an equivalent project template that already includes **mvnw**, **mvnw.cmd**, and the **.mvn/wrapper** directory. The example uses Java 17; you need a JDK 17+ compatible with Spring Boot 3.5 on the build machine and a compatible runtime when running the JAR.

### 5.1. File Structure

~~~text
parent-demo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...
└── src/
    ├── main/
    │   ├── java/com/example/parentdemo/ParentDemoApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/parentdemo/ParentDemoApplicationTests.java
~~~

### 5.2. Complete `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>parent-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>parent-demo</name>
    <description>Demonstrates Spring Boot Maven parent inheritance</description>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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
            </plugin>
        </plugins>
    </build>
</project>
~~~

Key details to observe:

1. **parent version 3.5.16** selects the Boot release line and build conventions.
2. Both **starter dependencies** omit the **version** tag because the parent provides dependency management.
3. **java.version=17** is a property used by the parent. In this example, it explicitly matches the default Java baseline; to target Java 21, change it to **21** and ensure a matching compiler/runtime JDK.
4. **project.build.sourceEncoding=UTF-8** is written explicitly to illustrate override syntax; the parent already provides UTF-8 so normal projects can omit this line.
5. **spring-boot-maven-plugin** does not need a **version** tag or a redeclaration of the **repackage** execution when using the parent by convention.
6. **starter-test** is in `test` scope only and is not a runtime dependency packaged into the executable JAR.

### 5.3. Complete Java Code

Save **src/main/java/com/example/parentdemo/ParentDemoApplication.java**:

~~~java
package com.example.parentdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ParentDemoApplication {

    @Value("${app.build.version}")
    private String buildVersion;

    @Value("${app.greeting}")
    private String greeting;

    public static void main(String[] args) {
        SpringApplication.run(ParentDemoApplication.class, args);
    }

    @GetMapping("/info")
    public String info() {
        return greeting + " / " + buildVersion;
    }
}
~~~

This class contains the main method and a REST endpoint. The Java source does not bundle Spring Framework itself: it compiles because Maven resolved **spring-boot-starter-web** using the parent's dependency management. **@Value** is a Spring annotation used to inject configuration values at runtime.

Save **src/main/resources/application.properties**:

~~~properties
spring.application.name=parent-demo
app.build.version=@project.version@
app.greeting=${APP_GREETING:hello}
~~~

This example combines two distinct mechanisms:

- **@project.version@** is a Maven **build-time resource filtering** placeholder; during `process-resources`, Maven replaces it with **0.0.1-SNAPSHOT** from the POM.
- **${APP_GREETING:hello}** is a Spring **runtime** configuration placeholder; when the **APP_GREETING** environment variable is absent, Spring falls back to the default **hello**.

To test context startup, save **src/test/java/com/example/parentdemo/ParentDemoApplicationTests.java**:

~~~java
package com.example.parentdemo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ParentDemoApplicationTests {

    @Test
    void contextLoads() {
        // Succeeds if the Spring application context starts without errors.
    }
}
~~~

This test runs with the declared **spring-boot-starter-test**; it checks context startup and the presence of required configuration values. It does not replace real HTTP tests.

### 5.4. Build and Observe Output

From the project root directory, on Linux/macOS run:

~~~bash
./mvnw --version
./mvnw clean verify
java -jar target/parent-demo-0.0.1-SNAPSHOT.jar
~~~

On Windows, use **mvnw.cmd** correspondingly. Once the application starts on the default port 8080 (assuming no other port configuration), in a second terminal run:

~~~bash
curl http://localhost:8080/info
~~~

When the **APP_GREETING** environment variable is unset, the exact response body of the endpoint in this example is:

~~~text
hello / 0.0.1-SNAPSHOT
~~~

If you set **APP_GREETING=welcome** for the application process and restart it, the greeting changes to **welcome** while the project version filtered from the Maven POM remains **0.0.1-SNAPSHOT**. Maven values are baked into the artifact at build time; changing the POM version afterward **does not automatically update** an already packaged JAR.

**Interpreting the output properly:** **clean verify** runs Maven phases up to `verify` according to active plugins/executions and creates the artifact in **target**. With the parent and Boot plugin declared in the example, the **repackage** goal produces a JAR runnable via **java -jar**. Maven logs do not have identical stdout across all machines because they depend on plugin versions, caches, and environment; the HTTP output above is what is deterministically defined by the lesson's code and configuration.

## 6. How Does Maven Inherit and Override Properties?

### 6.1. Parent and Child POM

In Maven, the application (child) POM receives inheritable configuration from the parent POM. The child can redeclare a property with the same name to change the effective value in configurations that reference that property.

For example, the parent sets Java 17 by default. To switch the Java target to 21 in a Boot 3.5 project that supports Java 21, in **pom.xml**:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>
~~~

After making this change, you must use a JDK/compiler capable of generating Java 21 classes and a matching runtime to run the artifact, as well as verify plugin and CI environment compatibility. **java.version** in the POM does not install a JDK or upgrade a server's JVM. If your deployment environment is still on Java 17, compiling Java 21 bytecode will not be suitable.

In the Spring Boot parent, **java.version** feeds compiler settings, including **maven.compiler.release** per parent conventions. Do not invent arbitrary variables like **jdk.version** expecting the parent to read them: only properties actually referenced by Maven or plugins take effect.

### 6.2. Maven-Understood Properties, Plugin-Understood Properties, and Custom Properties

| Example | Who Consumes It? | Effect |
| --- | --- | --- |
| **java.version** | Spring Boot parent configuration | Sets the baseline Java compilation level via parent config |
| **maven.compiler.release** | Maven Compiler Plugin | Enforces bytecode level and standard APIs for the target Java version |
| **project.build.sourceEncoding** | Plugins that read the encoding property | Specifies source/resource encoding when supported by plugins |
| **slf4j.version** | Spring Boot dependency management in supported release lines | Selects the managed SLF4J version in a POM inheriting the parent |
| **resource.delimiter** | Parent resource filtering configuration | Adjusts the Maven token delimiter when filtering resources |
| **app.message** | Project-defined custom property | Takes effect only when referenced by POM/plugins/resources |
| **spring-boot.run.profiles** | Spring Boot Maven Plugin when running `run` | Selects Spring profiles when invoking the Spring Boot `run` goal |

A custom property like **app.message=hello** does not automatically pass runtime information to Spring Boot. It must be wired via **resource filtering**, system properties, environment variables, or plugin configuration. Likewise, do not confuse Maven property names with **spring.* ** keys read from **application.properties**.

### 6.3. Overriding Properties That Manage Dependency Versions

Suppose a library is managed in the Spring Boot BOM via the **slf4j.version** property (this property exists in the Boot 3.5 line). In a project directly inheriting **spring-boot-starter-parent**, you can redefine that property in the child POM:

~~~xml
<properties>
    <java.version>17</java.version>
    <slf4j.version>2.0.17</slf4j.version>
</properties>
~~~

This is an **override syntax example**, not a blanket recommendation to switch SLF4J to 2.0.17. Before applying a non-default version, verify compatibility with your Spring Boot release, other logging libraries, security policies, and actual tests. Spring Boot tests a curated set of versions together; arbitrary overrides can cause runtime failures even when Maven resolves them cleanly.

To verify whether a property is actually supported in your Boot release line, check **Dependency Versions Properties** for that **exact release line/version**. Do not assume a property from an older article still exists in every newer branch.

### 6.4. Overriding a Dependency Version Directly on the Dependency Tag

You can declare **version** directly inside a dependency if a specific version is needed:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
    <version>2.0.17</version>
</dependency>
~~~

This is also an **illustrative XML snippet**, which must be placed inside **dependencies** of a complete POM. An explicit version on that dependency can take precedence over the BOM's managed default. However, changing a single artifact within a tightly coupled library family can leave the dependency graph inconsistent. When changing a library group/version train, evaluate the entire BOM and inspect **dependency:tree**.

## 7. Customizing the Compiler: `java.version`, `release`, `source`, and `target`

### 7.1. Most Common Configuration

For a Boot 3.5 project using Java 21, the standard configuration is:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>
~~~

**maven.compiler.release** is configured by the parent based on the Java target. When the Java compiler uses **--release**, it not only sets the class file version but also restricts access to standard Java APIs to the target release, preventing accidental use of newer JDK APIs when compiling on a newer JDK.

**Example:** if you compile on JDK 21 and want to build a Java 17-compatible library, you can use **--release 17** in a pure Java project with compatible dependencies. However, **Spring Boot 3.5** itself requires at least Java 17 at runtime; simply lowering **release** to 11 will not make a Spring Boot 3.5 application run on Java 11.

### 7.2. When Do You Need to Customize the Maven Compiler Plugin?

Usually the parent handles the required settings. If you have special compiler requirements (annotation processors, warnings, flags), you can declare the plugin in **build/plugins** and set only the fields you want to change so the rest remain managed:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <showWarnings>true</showWarnings>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

This is an **additional build snippet**; do not paste a second **build** section into the same POM. When applying it to a real project, merge this plugin into your existing `plugins` list.

In special cases where you must use **--add-exports**, **--add-reads**, or **--patch-module** to access system modules, the Spring Boot Maven Plugin documentation notes that using **maven.compiler.release** can block those options. The documentation suggests dropping `release` and using **maven.compiler.source/target** instead. This is an exception that should be evaluated carefully because `source`/`target` do not enforce standard Java API restrictions like `--release`; avoid changing it without a justified need.

### 7.3. Maven Wrapper and Toolchains Are Different Matters

**mvnw** pins the **Maven** version (when the project has a Wrapper), whereas **java.version** controls the compilation target; neither installs nor selects the host machine's JDK automatically. You may need the right JDK on `PATH`/`JAVA_HOME` or the **Maven Toolchains Plugin** to select a compiler JDK independently from the JVM running Maven.

Always verify with:

~~~bash
java -version
./mvnw --version
./mvnw help:evaluate -Dexpression=java.version -q -DforceStdout
./mvnw help:evaluate -Dexpression=maven.compiler.release -q -DforceStdout
~~~

The two **help:evaluate** commands use the Maven Help Plugin; when configured properly, the expected output for the example POM is **17** for both the Java target and compiler release. Console output may include Maven logs/info depending on version and execution mode.

## 8. Reading the Effective Configuration via Effective POM

A POM that is only a few dozen lines long **is not the complete configuration Maven actually uses**. Plugin versions and executions can come from the parent POM, Super POM, active profiles, or module POMs. Essential tools are:

~~~bash
./mvnw help:effective-pom
./mvnw help:effective-pom -Dverbose=true
./mvnw help:active-profiles
./mvnw dependency:tree
~~~

In the **help:effective-pom** output, inspect:

- **properties**: final versions/values for **java.version**, **maven.compiler.release**, and other properties.
- **dependencyManagement**: managed versions by `groupId`/`artifactId`.
- **build/pluginManagement**: default plugin versions/configurations.
- **build/plugins** and **executions**: which plugins are declared and which goals are bound to the lifecycle.
- **resources**: actual directories and filtering options.
- **profiles** (when activated): configuration sections altered by selected profiles.

**help:effective-pom -Dverbose=true** can include configuration origin comments, helping answer "which parent did this line come from?". **help:active-profiles** reports which profiles are active for the current invocation. **dependency:tree** checks resolved dependency versions and transitive dependencies; a managed version in the POM does not mean that library is on the classpath if the project does not depend on it.

Examples using the POM from Section 5:

~~~bash
./mvnw help:evaluate -Dexpression=project.version -q -DforceStdout
./mvnw help:evaluate -Dexpression=java.version -q -DforceStdout
./mvnw dependency:tree -Dincludes=org.springframework.boot
~~~

The logical values of the first two expressions are **0.0.1-SNAPSHOT** and **17**, respectively. Dependency lists can be long and vary by Spring Boot version; do not hardcode a static dependency tree assuming every machine will produce identical output.

Help Plugin commands are primarily for inspection, **not a Maven dry-run of the entire lifecycle**; they may still access repositories/cache to resolve plugins. Viewing the effective POM does not prove that compile, test, or repackage will succeed.

## 9. Customizing Packaging via Spring Boot Maven Plugin

### 9.1. Declaring the Plugin to Activate `repackage`

In a POM inheriting the parent, you normally only need:

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

The parent already prepares an execution with **id=repackage**, so when this goal is activated during `package`, the standard archive is packaged into an executable JAR/WAR. Do not declare an extra unnecessary **repackage** execution that would run the goal twice or create unintended artifacts.

**spring-boot:repackage** operates on the archive built during the `package` phase. If you need to invoke the goal manually when it is not bound, Boot documentation recommends running the `package` phase beforehand, such as **mvn package spring-boot:repackage**. With a properly configured parent, **./mvnw package** is sufficient to trigger `repackage`.

### 9.2. When You Need Both a Plain JAR and an Executable JAR

When a project needs to produce both artifacts, you can configure a **classifier** on the execution with id **repackage**:

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

This is an **alternative** to the `build/plugins` block in the initial example, not a snippet to paste alongside it and duplicate the plugin declaration. When the project uses the parent, specifying the exact execution id **merges your configuration with the inherited execution**. With the example artifact name/version, this configuration typically creates **parent-demo-0.0.1-SNAPSHOT.jar** as a plain JAR and **parent-demo-0.0.1-SNAPSHOT-exec.jar** as an executable JAR. Run commands must point to the **-exec.jar** file; do not assume every JAR in `target` is bootable.

Do not arbitrarily use an executable JAR as a dependency of another Java application: Boot JAR layout places classes under **BOOT-INF/classes** and differs from a plain JAR. Depending on the use case, a library module should remain a plain JAR.

### 9.3. Renaming the Output Archive File

If you want an output filename independent of `artifactId`/`version`, configure the Maven build:

~~~xml
<build>
    <finalName>my-service</finalName>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

With `jar` packaging and no classifier, the output in **target** is typically **my-service.jar**. This uses the **build/finalName element**, not an arbitrary **final.name** property; you must edit the exact XML element. Changing the filename does not change **groupId:artifactId:version**, which remains the artifact's Maven identity.

## 10. Resource Filtering: Customizing Build-Time Values Without Breaking Spring Placeholders

This is the most easily misunderstood feature when using the parent.

### 10.1. Two Placeholder Syntaxes Processed at Two Different Times

Consider **application.properties**:

~~~properties
app.build.version=@project.version@
app.build.java=@java.version@
app.greeting=${APP_GREETING:hello}
~~~

| Syntax | Processor | Timing | Example After Processing |
| --- | --- | --- | --- |
| **@project.version@** | Maven Resources Plugin per parent config | During build/`process-resources` | 0.0.1-SNAPSHOT |
| **@java.version@** | Maven Resources Plugin | During build/`process-resources` | 17 |
| **${APP_GREETING:hello}** | Spring Environment / placeholder resolution | When app starts/reads property | `hello` if `APP_GREETING` is unset |

The Spring Boot parent uses **@...@** delimiters for Maven filtering to avoid colliding with Spring's **${...}** syntax in configuration files. Enabling Maven filtering that replaces **${...}** can easily overwrite placeholders meant for runtime resolution. You can customize the **resource.delimiter** property, but you must carefully assess its impact on all filtered config files.

### 10.2. Watch Resource Paths

According to Spring Boot documentation, default filtering applies primarily to **production application config** under **src/main/resources**; **src/test/resources** is not automatically filtered in the same way by the parent. Do not assume any file anywhere in the project can contain `@...@` tokens and will certainly be substituted.

To check whether a file has been filtered, run the Maven lifecycle up to **process-resources** or `package` and inspect the output:

~~~bash
./mvnw process-resources
~~~

Then inspect **target/classes/application.properties**. With the example POM, the processed file will contain:

~~~properties
spring.application.name=parent-demo
app.build.version=0.0.1-SNAPSHOT
app.greeting=${APP_GREETING:hello}
~~~

This confirms Maven substituted the **@project.version@** token while leaving the Spring expression intact. If `spring-boot:run` is configured with **addResources=true**, it can place the original source resources directly on the classpath and **bypass the filtering step**, making `run` behave differently from the packaged artifact. When verifying resource filtering, test the packaged JAR itself.

### 10.3. Be Careful with Binary Files and Secrets

Do not blindly enable **filtering=true** for all resources: binary files such as images, fonts, certificates, keystores, or archives can be corrupted. Likewise, never bake **passwords**, **tokens**, or **environment-specific secrets** directly into the JAR via property filtering; filtered values become part of the artifact and can be extracted. Use environment variables, a secret manager, or appropriate runtime configuration for sensitive data.

## 11. Distinguishing Maven Build Properties, Maven Profiles, and Spring Profiles

These three concepts sit close together yet have distinct responsibilities:

- **Maven properties**: values used to configure the POM and plugins, such as **java.version** or **project.build.sourceEncoding**.
- **Maven profiles**: conditional build configuration branches activated via **-Pprofile-id** that can alter dependencies, plugin executions, repositories, or build properties.
- **Spring profiles**: sets of runtime configuration/beans for the application, such as **dev**, **test**, **prod**, handled by the Spring `Environment`.

Example of an illustrative Maven profile setting a property:

~~~xml
<profiles>
    <profile>
        <id>dev-build</id>
        <properties>
            <app.build.label>development</app.build.label>
        </properties>
    </profile>
</profiles>
~~~

If **application.properties** contains **app.build.label=@app.build.label@** with appropriate filtering configuration, running **./mvnw -Pdev-build package** builds an artifact with **development** filtered at build time. If the property has no default and the profile is not activated, the token may remain unreplaced; define a default value for real-world usage.

Meanwhile, the Spring Boot Maven Plugin supports running the application with a runtime profile:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
~~~

This flag affects **the Spring profile when the `run` goal starts the application**; it does not activate a Maven profile named `dev`. And **java -jar app.jar --spring.profiles.active=prod** configures the Spring runtime of the already built artifact. Therefore, avoid treating **-Pprod**, **-Dspring-boot.run.profiles=prod**, and **--spring.profiles.active=prod** as interchangeable alternatives.

A maintainable practice is to build a single tested artifact and supply environment differences via runtime configuration/properties rather than building separate JARs containing secrets for each environment.

## 12. When a Project Already Has a Corporate Parent: How to Use the BOM Alternative?

Maven allows only **one direct parent**. If a project must inherit an organization's parent POM, the standard way to keep using Spring Boot's **managed dependencies** is importing the BOM:

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

This is **a fragment for a POM using a different parent**, not something to add to the POM already inheriting **spring-boot-starter-parent** in Section 5.

**Importing the BOM brings in dependency management, not the parent's plugin management, resource filtering, or build defaults**. Therefore, in that setup the project must explicitly ensure:

- Spring Boot Maven Plugin is declared with an appropriate version.
- The **repackage** execution is bound if an executable JAR/WAR is desired.
- Maven Compiler Plugin and the Java target level are set accurately.
- Maven Resources Plugin/resource filtering is configured appropriately.
- Essential Maven plugins have stable, managed versions.

Example showing only how to bind `repackage` without the parent:

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

When importing the BOM and wanting to **override a library version**, merely setting a property with the same name in the child POM usually **does not work like parent inheritance**. Per Spring Boot guidance, the safe and explicit way is declaring a dedicated entry in **dependencyManagement** before importing the Boot BOM, or ordering BOMs according to Maven precedence rules and verifying with **dependency:tree**.

Keep these differences in mind:

| Decision | Inheriting `starter-parent` | Importing `spring-boot-dependencies` BOM |
| --- | --- | --- |
| Receive managed dependency versions | Yes | Yes |
| Receive Boot parent plugin management | Yes | No |
| Receive Boot parent compiler/encoding/resource defaults | Yes | No |
| Receive pre-configured `repackage` execution | Yes (when plugin is declared properly) | No; must configure |
| Override managed version via parent property | Yes for Boot-supported properties | Not via the same mechanism; requires proper `dependencyManagement` |
| Keep another corporate parent | Cannot be simultaneous direct parent | Yes |

Do not choose BOM-only thinking it is "100% equivalent" to the parent. The two approaches have different responsibilities and inheritance scopes.

## 13. How to Verify That a Configuration Has Taken Real Effect

Reading configuration is the first step; verifying the artifact is the final step.

### Checking Boot Version and JDK

~~~bash
./mvnw --version
./mvnw help:evaluate -Dexpression=project.parent.version -q -DforceStdout
./mvnw help:evaluate -Dexpression=java.version -q -DforceStdout
~~~

For the demo POM, the last two expressions evaluate to **3.5.16** and **17**, respectively. If the values differ from expectations, inspect the effective POM along with profiles and properties passed by CI.

### Checking Dependency Versions

~~~bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.boot
~~~

If a dependency is not declared and no transitive path pulls it in, its managed version may still exist in the POM while the dependency itself does not appear in the tree. A parent/BOM managing a version **does not force that library into the application**.

### Checking Plugin Execution

~~~bash
./mvnw help:effective-pom -Dverbose=true
./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail=true
~~~

Look for **spring-boot-maven-plugin** in **build/plugins**, the **repackage** execution, and the managed plugin version. Describing the goal explains what the goal does; the effective POM shows how it is configured for the project. To inspect actual execution logs, run **./mvnw clean package** in a permitted build environment and look for the **spring-boot:repackage** goal line.

### Checking the Artifact and Resource Filtering

~~~bash
./mvnw clean package
java -jar target/parent-demo-0.0.1-SNAPSHOT.jar
~~~

A typical executable Boot JAR contains **BOOT-INF/classes** and **BOOT-INF/lib**. Packaged resources must contain the filtered app config. When the Java process starts successfully but the endpoint behaves unexpectedly, check profiles/env/runtime config and **target/classes/application.properties**; do not jump to assuming the parent chose the wrong dependency.

### Checking Tests

~~~bash
./mvnw clean verify
~~~

This is an actual build, not just a plan view. Maven runs lifecycle-bound plugin goals and configured tests. Avoid claiming a single **BUILD SUCCESS** replaces comprehensive integration tests or production smoke tests.

## 14. Common Errors and How to Handle Them

| Symptom | Common Cause | How to Check/Fix |
| --- | --- | --- |
| Maven requires a version for **spring-boot-starter-web** | Parent/BOM not resolved, typo in dependency name, or unmanaged artifact | Inspect parent/BOM effective POM and Maven repository |
| **Non-resolvable parent POM** | Wrong version, repository/network/proxy issue, or `relativePath` pointing to wrong location | Check parent coordinates, use empty `relativePath` when fetching from repository |
| Changed **java.version** but still using another JDK | Property does not install/switch the JDK running Maven | Check `./mvnw --version`, JDK/toolchain, and compiler target |
| **release version 21 not supported** | Maven is running on a compiler JDK that does not support Java 21 | Provide JDK 21 or an appropriate toolchain |
| **UnsupportedClassVersionError** on `java -jar` | Deployment JVM is too old for class files/Boot dependencies | Align compiler target and runtime JVM |
| **no main manifest attribute** | Running plain JAR or Spring Boot `repackage` did not run | Declare plugin and check execution/output archive |
| **@project.version@** remains in `application.properties` after build | Resource filtering did not run on the active file or paths changed | Inspect `target/classes`, resources plugin, `addResources` |
| Runtime **${...}** replaced before running | Maven filtering uses a delimiter conflicting with Spring | Use `@...@` and check `resource.delimiter` |
| Added **slf4j.version** but version did not change | Project only imports BOM or property is no longer managed in that Boot line | Check exact Version Properties, `dependencyManagement`, and `dependency:tree` |
| Same parent but CI resolves different libraries than laptop | Different Maven settings/profiles, repository, version overrides, snapshots, or cache | Compare commands, active-profiles, effective POM, and tree |
| Compile passes but tests lack dependencies | Missing test starter/wrong scope or tests skipped | Check dependency scope and Surefire/test reports |
| Plugin configured in **pluginManagement** but goal does not run | Plugin not declared/activated or no execution bound | Inspect `build/plugins` and lifecycle |
| **-Pprod** does not activate Spring runtime profile `prod` | Maven profile is not Spring profile | Use `spring-boot.run.profiles` or `spring.profiles.active` appropriately |

### Notes on Test-Skipping Flags

**-DskipTests** typically tells Surefire/Failsafe to skip running tests, whereas **-Dmaven.test.skip=true** can also skip compiling tests; they are not equivalent and should not be used as the default release build path. Likewise, do not conclude tests actually ran merely because `package`/`verify` phases exist: inspect test plugins and logs/reports. When failures occur, fix the root cause instead of treating skipped tests as proof of a valid build.

## 15. Practice Checklist and Self-Check Questions

### Checklist

- [ ] POM has **one** appropriate parent, with accurate **groupId/artifactId/version** and **relativePath**.
- [ ] Selected a Spring Boot patch supported by the project; build/runtime Java matches the Boot release line.
- [ ] Only required dependencies are declared, omitting versions on libraries already managed by Boot.
- [ ] **java.version**, encoding, and plugin configurations are customized deliberately without copying the entire parent config.
- [ ] **spring-boot-maven-plugin** is declared when an executable JAR/WAR is needed; **repackage** execution verified.
- [ ] Verified resource filtering of **application.properties/yml** via output in **target/classes**; distinguished Maven `@...@` from Spring `${...}`.
- [ ] Inspected **effective POM**, **active profiles**, and **dependency tree** when changing versions.
- [ ] Ran tests, `package`, and **java -jar** on the actual artifact; used Maven Wrapper in CI.
- [ ] If the organization mandates its own parent, imported the Boot BOM and added missing plugin/build defaults manually.

### Question 1: With a parent already set, can I omit all dependencies?

No. The parent provides defaults and version management; the project still must declare **starter-web**, **starter-data-jpa**, **starter-test**, or whichever dependencies it uses. Missing a dependency means the classpath lacks the corresponding library capabilities.

### Question 2: Can I put both `corporate-parent` and `spring-boot-starter-parent` in one POM?

No. Each Maven POM has one direct parent. You can choose your organization's standard parent and import the **spring-boot-dependencies** BOM; in that case you must manage plugin management and required build conventions yourself.

### Question 3: Why is the parent present yet Maven did not produce an executable JAR?

Check whether **spring-boot-maven-plugin** is in **build/plugins**, whether the **repackage** execution was inherited/activated properly, whether packaging is appropriate, and whether the project has a main class. The parent provides execution configuration; declaring the plugin and running the appropriate lifecycle produces the executable artifact.

### Question 4: Is changing Java 17 to Java 21 via the property alone enough?

Not enough. The property adjusts the compilation level through the parent, but it does not upgrade the JDK on your build machine, CI, or server. You must check compiler, Boot/plugin compatibility, toolchain, and runtime.

### Question 5: Why does `application.properties` use `@project.version@` instead of `${project.version}`?

The parent intentionally uses the **@...@** delimiter for Maven filtering to avoid conflicting with Spring's **${...}** placeholders at runtime. The two token types belong to two different stages of the application.

### Question 6: When importing the BOM, why do property version overrides behave differently than when inheriting the parent?

Because importing a BOM brings only dependency management into the POM, without inheriting all properties and plugin configurations via parent structure. To override a managed dependency in a BOM-only setup, place a higher-precedence **dependencyManagement** entry appropriately and verify the result.

## 16. Mechanism Summary and Official References

An easy-to-remember chain of responsibility:

~~~text
Child POM declares <parent>
      |
      +--> Inherits defaults / managed versions / plugin settings
      |
      +--> <properties> overrides required values
      |
      +--> <dependencies> selects libraries to use
      |
      +--> <build><plugins> activates and customizes build behavior
      |
      v
Maven resolves effective POM -> dependency graph -> compile/test/package
      |
      v
Spring Boot Maven Plugin: repackage -> executable archive
      |
      v
java -jar + runtime configuration -> running application
~~~

**spring-boot-starter-parent** lets you start from defaults designed by Spring Boot to work together. Declaring only what needs changing in **properties** or plugin configuration, inspecting the **effective POM**, and verifying the **actual artifact** is a safer, more controllable, and more maintainable way to use the parent.

### Official Documentation

- Spring Boot 3.5 — Maven Plugin, Using the Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html
- Spring Boot 3.5 — Dependency Version Properties: https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/properties.html
- Spring Boot 3.5 — Build Systems: https://docs.spring.io/spring-boot/3.5/reference/using/build-systems.html
- Spring Boot 3.5 — Build (Executable JAR): https://docs.spring.io/spring-boot/3.5/how-to/build.html
- Spring Boot 3.5 — Properties and Configuration (Maven filtering): https://docs.spring.io/spring-boot/3.5/how-to/properties-and-configuration.html
- Spring Boot — Maven Plugin Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Apache Maven — POM Reference (Inheritance, Properties, Plugin Management): https://maven.apache.org/pom.html
- Apache Maven — Introduction to Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven Help Plugin — Effective POM: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Maven Help Plugin — Evaluate: https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html