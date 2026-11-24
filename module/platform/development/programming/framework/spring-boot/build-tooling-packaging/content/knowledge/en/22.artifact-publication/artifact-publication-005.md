# Choosing Plain JAR, Boot JAR, WAR, or Source JAR Artifacts to Publish

## 1. Start from the Recipient and How They Will Use the Artifact

In a Java/Spring Boot project, a build can produce multiple files ending in `.jar` or `.war`. They are not arbitrarily interchangeable. A Java library used as a dependency by another project needs a **plain JAR**; a Spring Boot service deployed standalone typically needs an **executable Boot JAR**; a Servlet web application under an organization's deployment contract may need a **WAR**; developers or library consumers who need to read/debug source code may need a **source JAR**.

Choosing the wrong artifact usually does not fail the build task. The problem surfaces only when consumers download the file:

- Another project declares a dependency on the Boot JAR, yet the compiler cannot find the application's classes.
- The pipeline only publishes a plain JAR, so the operations team cannot run it with java -jar as expected.
- Infrastructure requires deploying to a Servlet container, while the release team only has an executable JAR.
- The IDE cannot download source code while debugging because the artifact with classifier sources is missing.
- Maven publishes an executable file overwriting the library JAR, breaking the classpath of consumers depending on that GAV.
- A WAR bundles an embedded server with the wrong scope, conflicting with the server provided by the organization.

This lesson helps you pick **the right artifact type**, understand how Maven/Gradle name and publish them, preserve plain archives when needed, package source JARs, and verify actual contents before releasing.

**Practice versions:** Java 17, Spring Boot 3.3.5, Maven 3.9.x or Gradle 8.5. These are fixed versions for the examples so outputs can be cross-checked; they are not claims of being the latest releases.

## 2. Quick Decision Table

| Recipient's need | Appropriate artifact | How it is used | Should it be a compile dependency? |
| --- | --- | --- | --- |
| Another application imports library classes | **Plain JAR (library JAR)** | Build tool adds JAR and dependency metadata to classpath | **Yes** |
| Running a standalone Spring Boot application | **Executable Boot JAR** | java -jar application.jar or container image | **No** |
| Deploying a Servlet web app to external Tomcat/Jetty | **WAR** suited for Servlet containers | Deploy WAR to container; can be an executable Boot WAR | **No** |
| Source code needed for reading/debugging/IDE attach | **Source JAR** | IDE or documentation tools fetch via classifier sources | **No** |
| Both library and standalone runnable needed | **Plain JAR + separate Boot JAR** | Publish two artifacts with clear conventions | Plain JAR only |

**Selection rules:**

1. Ask whether the recipient will **import classes** or **launch the application**.
2. If importing classes, prefer a plain library JAR accompanied by POM/Gradle Module Metadata.
3. If launching a Spring Boot service, use an executable Boot JAR or Boot WAR depending on the deployment environment.
4. If the deployment contract requires a Servlet container, determine the Servlet/Jakarta version and configure a compatible WAR.
5. If debugging or source distribution is needed, publish a source JAR with the exact same version as the binary.
6. If multiple purposes are needed, publish multiple artifacts with clear names/classifiers; never use one file for everything.

## 3. Understanding the Four Artifact Types

### 3.1. Plain JAR: Library or Java Archive Without a Boot Loader

A **JAR (Java Archive)** is a ZIP archive containing classes, resources, and metadata. A standard Java library has the structure:

~~~text
catalog-core-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/example/catalog/
    ├── CatalogFormatter.class
    └── CatalogRecord.class
~~~

Classes sit at standard package paths relative to the JAR root. When an application declares a dependency on this library, the compiler/runtime locates classes via the standard classpath.

A library JAR normally **does not bundle all transitive dependencies** inside it. For example, if CatalogFormatter uses Commons Lang, the library must publish dependency metadata so Maven/Gradle consumers download Commons Lang separately. That is why a plain library JAR must be published with matching **POM or Gradle Module Metadata**.

A plain JAR can also contain a main class. However, if it does not carry required dependencies, running it with java -jar may fail unless dependencies are provided on the classpath. **Having a .jar file does not mean it is an executable application package.**

**When to choose:**

- Modules sharing classes across multiple applications.
- SDKs, utilities, domain models, starters, or adapters.
- Core modules in multi-module projects.
- Artifacts intended for consumers to place on their compile/runtime classpath via dependency metadata.

**Do not confuse a plain JAR with a shaded/uber JAR.** A shaded JAR typically merges classes from multiple dependencies into one archive, which may require handling duplicate resources, service descriptors, and license files. Plain JARs from the Java Library plugin do not do that automatically.

### 3.2. Executable Spring Boot JAR: Self-Starting Application

An **Executable Boot JAR** is an archive repackaged by the Spring Boot plugin so it can run with:

~~~bash
java -jar app-1.0.0.jar
~~~

A typical JAR:

~~~text
app-1.0.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/app/Application.class
    └── lib/
        ├── spring-boot-*.jar
        ├── spring-context-*.jar
        └── ...
~~~

Key differences:

- Application classes reside in **BOOT-INF/classes/**.
- Runtime dependencies reside as nested JARs in **BOOT-INF/lib/**.
- The Spring Boot loader is used to launch and load nested dependencies.
- Manifest typically has **Main-Class** set to the Spring Boot launcher and **Start-Class** set to the application main class.

Because application classes reside in BOOT-INF/classes, **do not use an executable Boot JAR as a regular Java library dependency**. Another application's compiler or classloader does not treat BOOT-INF/classes as the package root of a plain JAR.

Boot JARs fit:

- REST APIs/services, batch apps, schedulers, command-line applications.
- Container images or platforms running a Java process.
- Releasing an application with runtime dependencies packaged alongside it.
- Operations teams needing a single file runnable consistently via java -jar.

**A Boot JAR is not a JAR that unpacked all dependencies into one flat pile of classes.** Spring Boot typically keeps dependencies as nested JARs and uses its own launcher.

### 3.3. WAR: Web Application for a Servlet Container

A **WAR (Web Application Archive)** is defined for Servlet-based web applications. A traditional WAR has the layout:

~~~text
web-portal.war
├── META-INF/
└── WEB-INF/
    ├── classes/
    │   └── com/example/web/PortalApplication.class
    ├── lib/
    │   ├── application-library.jar
    │   └── ...
    └── web.xml (if used by the app)
~~~

A WAR is deployed into a running Servlet container, such as Tomcat/Jetty. The container manages the web application lifecycle, Servlet registration, request dispatching, and classloaders per the Servlet specification.

A **Spring Boot executable WAR** can support both modes of execution:

- Deploying to an external Servlet container, when the application and dependencies are properly configured.
- Running directly via java -jar, when the archive has been repackaged by Spring Boot.

A Boot executable WAR can place server dependencies marked as provided under **WEB-INF/lib-provided/** so they do not conflict with an external Servlet container yet remain available when launched standalone via the Boot launcher.

**A WAR is not the default choice for every web application.** If the organization allows running standalone services or container images, an executable Boot JAR is usually simpler. A WAR makes sense when infrastructure, deployment contracts, or legacy systems require an external Servlet container.

With Spring Boot 3.x, check **Jakarta Servlet** compatibility and the container version. An older Servlet container using the javax namespace cannot be assumed compatible simply because the file ends in .war.

### 3.4. Source JAR: Distributing Source Code Alongside Binaries

A **Source JAR** is an archive containing the module's source code, typically named:

~~~text
catalog-core-1.0.0-sources.jar
~~~

Inside are files such as:

~~~text
com/example/catalog/CatalogFormatter.java
com/example/catalog/CatalogRecord.java
~~~

Source JARs are useful for:

- IDEs displaying source code when navigating into dependencies.
- Debuggers mapping source lines to bytecode.
- Users reading API implementations or checking how behavior works.
- Source code distribution workflows per project policy.
- Reviewing and matching source against the exact binary version.

A Source JAR **does not replace a library JAR**, is not an executable artifact, does not bundle runtime dependencies, and is not used as a standard compile/runtime dependency.

A Source JAR must match **the exact version/commit of the binary**. Never publish newer sources under the same version as an older JAR; when the debugger attaches mismatched sources, line numbers and logic will not align with bytecode.

Not all source code is permitted to be public. Before publishing a source JAR, check licenses, proprietary code, secrets, generated sources, and your organization's distribution policy.

## 4. Distinguishing Artifacts, Extensions, Classifiers, and Publishing Coordinates

A Maven artifact is typically identified by:

~~~text
groupId : artifactId : version : classifier @ extension
~~~

Examples:

~~~text
com.example : catalog-core : 1.0.0
com.example : catalog-core : 1.0.0 : sources @ jar
com.example : catalog-app : 1.0.0 : exec @ jar
com.example : portal : 1.0.0 : exec @ war
~~~

Filenames typically follow:

~~~text
artifactId-version[-classifier].extension
~~~

Examples:

| File | Meaning |
| --- | --- |
| catalog-core-1.0.0.jar | Main JAR of the library |
| catalog-core-1.0.0-sources.jar | Source JAR of the library |
| catalog-app-1.0.0.jar | Plain JAR of the app if retained as main artifact |
| catalog-app-1.0.0-exec.jar | Executable Boot JAR tagged with classifier exec |
| portal-1.0.0.war | Plain/deployable WAR |
| portal-1.0.0-exec.war | Executable Boot WAR with classifier exec |

**Classifier** distinguishes supplementary files sharing the same module coordinates. It does not create a completely different module and does not alter dependency metadata by itself. Common classifiers:

- **sources**: source JAR.
- **javadoc**: Javadoc archive.
- **tests** or **test-jar**: test classes/artifacts per configuration.
- **exec** or **boot**: executable artifact named per organizational convention.
- **plain**: plain archive when plugins generate an executable archive in parallel.

Classifier names are a project convention, as long as Maven/Gradle publications and consumers agree on them.

### 4.1. Classifiers Do Not Turn a Boot JAR into a Library

If you publish:

~~~text
com.example:catalog-app:1.0.0:exec
~~~

consumers can download that classified artifact, but **its contents remain a Boot executable archive**. The classifier only identifies the variant; it does not move classes from BOOT-INF/classes back to the package root.

Likewise, renaming app.jar to app-library.jar does not alter the archive layout. Inspect JAR contents with jar tf before deciding how consumers will use it.

### 4.2. One GAV Can Publish Multiple Files

A Maven module can publish a main artifact along with classifiers:

~~~text
catalog-core-1.0.0.jar
catalog-core-1.0.0-sources.jar
catalog-core-1.0.0-javadoc.jar
catalog-core-1.0.0.pom
~~~

This is a single library module with binary, source/documentation artifacts, and a shared POM.

An application can publish a plain artifact alongside a Boot classifier artifact if needed. However, because the shared POM can cause users to mistake the app JAR for a library, document it clearly in the repository README or separate the coordinates/registry for distribution artifacts.

## 5. Choosing Artifacts by Product Type

### 5.1. Shared Java Library

**Should publish:**

- Plain JAR as the main artifact.
- POM or Gradle Module Metadata describing dependencies.
- Source JAR if policy permits.
- Javadoc JAR if providing API documentation.

**Not needed:** Boot JAR or WAR. Libraries do not launch SpringApplication on their own and do not need a Servlet container.

### 5.2. Spring Boot Service or Batch Application

**Should publish:**

- Executable Boot JAR as the deployment artifact.
- Optionally a source JAR if needed for debugging/source distribution.
- SBOM/checksum/provenance per release process.

**Should not:** use the Boot JAR as a compile dependency for another module. If code needs to be shared, extract a core/library module as a plain JAR.

### 5.3. Spring MVC Application Deployed to a Servlet Container

**Should publish:**

- WAR configured for container compatibility.
- Optionally an executable/deployable Boot WAR if supporting both java -jar and external deployment.
- Source JAR if source distribution is needed.

Spring Boot WAR applications typically require **SpringBootServletInitializer** and embedded Servlet container dependencies declared properly as provided/providedRuntime. The external container must support the Jakarta Servlet API required by the Boot version.

### 5.4. Products Requiring Both Binaries and Sources

Publish **binary JAR + source JAR with the same version**. Put the source JAR under classifier sources; never put source files directly inside runtime dependencies. Verify sources are published from the right commit and contain no sensitive files.

### 5.5. If Multiple Artifact Types Are Needed Simultaneously

A project can have multiple modules:

~~~text
platform/
├── core-library/      # plain JAR + sources
├── web-service/       # Boot JAR
├── legacy-web/        # WAR
└── docs/              # documentation
~~~

This is usually cleaner than forcing a single module to act simultaneously as a library, a service, and a WAR. Each module gets its own packaging, dependency graph, lifecycle, and consumer contract.

## 6. Java 17 Sample: Core Library and Spring Boot Application

We use a small library to illustrate why plain JARs must be kept separate from Boot JARs.

### 6.1. Multi-Module Project Structure

~~~text
artifact-demo/
├── pom.xml                 # Maven root, if choosing Maven
├── settings.gradle         # Gradle root, if choosing Gradle
├── core/
│   └── src/main/java/com/example/core/CatalogFormatter.java
└── app/
    └── src/main/java/com/example/app/CatalogApplication.java
~~~

Choose Maven or Gradle. Both Java files below are shared.

### 6.2. Library Class

File **core/src/main/java/com/example/core/CatalogFormatter.java**:

~~~java
package com.example.core;

import java.util.Locale;

public final class CatalogFormatter {

    private CatalogFormatter() {
    }

    public static String format(String raw) {
        return "CATALOG-" + raw.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

This is a complete Java 17 class. It uses JDK APIs with no Spring Boot or external dependencies. Given input **"  book-42  "**, the result is **CATALOG-BOOK-42**.

Core builds into a plain JAR. The class sits at the standard package path:

~~~text
com/example/core/CatalogFormatter.class
~~~

### 6.3. Spring Boot Application Class

File **app/src/main/java/com/example/app/CatalogApplication.java**:

~~~java
package com.example.app;

import com.example.core.CatalogFormatter;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner runCatalog() {
        return args -> System.out.println(
                CatalogFormatter.format("  book-42  "));
    }
}
~~~

App uses core as a dependency. We use only basic **spring-boot-starter** without an HTTP server to illustrate packaging.

When running the proper executable Boot JAR:

~~~bash
java -jar app-1.0.0.jar
~~~

Stdout line printed by the application itself:

~~~text
CATALOG-BOOK-42
~~~

Spring Boot may print a banner/logs before or after this line. That is the business output, not the entire terminal output.

**Point to confirm:** app can call CatalogFormatter because the core JAR is on the classpath. If core were repackaged into an executable Boot JAR, the class would sit under BOOT-INF/classes and no longer be loaded by consumers as a regular plain dependency.

## 7. Maven: Publishing a Library JAR with a Source JAR

### 7.1. Root POM for Both Modules

File **artifact-demo/pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>artifact-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
~~~

The root POM is an aggregator and parent. It produces no application JAR because packaging is **pom**.

### 7.2. Complete core/pom.xml

File **artifact-demo/core/pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>artifact-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-source-plugin</artifactId>
                <version>3.4.0</version>
                <executions>
                    <execution>
                        <id>attach-sources</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>jar-no-fork</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

This is a **library module**:

- Packaging **jar** creates a plain JAR.
- Spring Boot Maven Plugin is not declared in core.
- Maven Source Plugin attaches the source JAR to the lifecycle at phase **verify**.
- Goal **jar-no-fork** creates the source archive and attaches it for install/deploy alongside the binary.
- The source JAR carries classifier **sources**.

After building, expected outputs:

~~~text
core/target/
├── core-1.0.0.jar
└── core-1.0.0-sources.jar
~~~

### 7.3. Building and Inspecting the Maven Library

From root:

~~~bash
mvn -pl core -am clean verify
~~~

If using Maven Wrapper:

~~~bash
./mvnw -pl core -am clean verify
~~~

On Windows, use **mvnw.cmd**. Then inspect:

~~~bash
jar tf core/target/core-1.0.0.jar
jar tf core/target/core-1.0.0-sources.jar
~~~

The binary JAR must contain **CatalogFormatter.class**. The source JAR must contain **CatalogFormatter.java** at the corresponding package path.

**verify** builds the source JAR but does not automatically deploy to a remote repository. Use **install** to install into the local Maven repository or **deploy** to publish to a configured repository.

## 8. Maven: Boot JAR Keeping Plain JAR and Publishing Executable with Classifier

### 8.1. Complete app/pom.xml

File **artifact-demo/app/pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>artifact-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
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
</project>
~~~

Because the root uses **spring-boot-starter-parent**, the **repackage** execution is already configured in the parent. We only add classifier **exec** to the execution with id repackage.

The result produces two archives with different purposes:

~~~text
app/target/
├── app-1.0.0.jar
└── app-1.0.0-exec.jar
~~~

- **app-1.0.0.jar**: plain JAR created by Maven package, keeping classes at the package root.
- **app-1.0.0-exec.jar**: Boot executable JAR created by repackage, containing the Boot loader, BOOT-INF/classes, and BOOT-INF/lib.

If **no classifier is set**, repackage replaces the main artifact with the executable archive by default; the original artifact is renamed to **.original** in target. That is sensible for a module representing strictly an application, though care is needed if the module is also consumed as a dependency.

### 8.2. Build and Run

~~~bash
mvn clean verify
java -jar app/target/app-1.0.0-exec.jar
~~~

Or:

~~~bash
./mvnw clean verify
java -jar app/target/app-1.0.0-exec.jar
~~~

Business output line:

~~~text
CATALOG-BOOK-42
~~~

Inspect both archives:

~~~bash
jar tf app/target/app-1.0.0.jar
jar tf app/target/app-1.0.0-exec.jar
~~~

In the plain JAR, look for **com/example/app/CatalogApplication.class**. In the Boot JAR, look for **BOOT-INF/classes/com/example/app/CatalogApplication.class** and **BOOT-INF/lib/**.

**Publication note:** classifier exec keeps both files during Maven install/deploy. However, the module's POM remains shared. Consumers are discouraged from declaring the Boot executable classifier as a Java dependency. If the app has no need to be consumed as a library, consider publishing it to a separate distribution/artifact registry rather than placing a plain app JAR in a shared library repository.

### 8.3. When You Only Want to Deploy the Original Artifact

Spring Boot Maven Plugin provides **attach=false**. In that case, the plugin still builds the executable file in build output but does not attach it for install/deploy; the published artifact remains the original JAR/WAR.

Example execution configuration fragment:

~~~xml
<execution>
    <id>repackage</id>
    <configuration>
        <attach>false</attach>
    </configuration>
</execution>
~~~

This is an option when the deployment workflow must preserve the original main artifact while still producing an executable for local/CI runs. Verify exactly which artifact gets installed/deployed; **a file existing in target does not mean it gets published**.

## 9. Maven: Choosing WAR for Servlet Applications

### 9.1. When to Use WAR?

Choose WAR if the deployment contract requires the web application to run inside a **pre-existing Servlet container**. A typical case is a Spring MVC application where the container manages the Servlet lifecycle.

With Spring Boot 3.x, the external container must support the compatible Jakarta Servlet API. The application normally needs to extend **SpringBootServletInitializer** so the container boots the Spring application context.

### 9.2. Main Class for Boot WAR

A variant of the app class:

~~~java
package com.example.app;

import com.example.core.CatalogFormatter;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(CatalogApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner runCatalog() {
        return args -> System.out.println(
                CatalogFormatter.format("  book-42  "));
    }
}
~~~

**configure()** lets the Servlet container initialize the application via SpringBootServletInitializer. **main()** still permits running the application via the executable Boot archive path when the WAR is configured properly.

This is a **Servlet/MVC** example. Do not assume every web stack supports WAR in the same way; for instance, Spring Boot traditional WAR support for WebFlux has specific limitations.

### 9.3. Maven WAR POM: Core Configuration

In the WAR app module, use:

~~~xml
<packaging>war</packaging>

<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>core</artifactId>
        <version>${project.version}</version>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-tomcat</artifactId>
        <scope>provided</scope>
    </dependency>
</dependencies>

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

This is a **replacement fragment for the packaging/dependencies/build of the JAR app in section 8**, not to be combined with jar packaging in the same POM.

- **packaging war** instructs the Maven WAR Plugin to create a web archive.
- **spring-boot-starter-web** selects the Servlet/Spring MVC stack.
- **spring-boot-starter-tomcat** with scope **provided** ensures the external container supplies Tomcat upon deployment.
- Spring Boot repackage creates an executable WAR with classifier exec.
- In the executable WAR, provided server dependencies can be placed under **WEB-INF/lib-provided/** so they do not conflict with an external server while remaining available for java -jar.

If using the Spring Boot parent, the repackage execution already exists; keep the exact id **repackage** when overriding the classifier configuration.

### 9.4. WAR Results and How to Run

When classifier exec is configured, expect:

~~~text
app/target/
├── app-1.0.0.war
└── app-1.0.0-exec.war
~~~

- **app-1.0.0.war**: plain WAR for deploying into an external Servlet container.
- **app-1.0.0-exec.war**: executable Boot WAR, runnable via java -jar.

Run the executable variant:

~~~bash
java -jar app/target/app-1.0.0-exec.war
~~~

Business stdout line:

~~~text
CATALOG-BOOK-42
~~~

Deploy the plain WAR to the container per your environment's procedure. URLs typically depend on the context path assigned by the container based on the WAR name or deployment configuration; do not assume endpoints sit at the root domain.

### 9.5. Do Not Put the Embedded Server in the Wrong Scope

If embedded Tomcat is placed inside the WAR as a normal runtime dependency, an external Tomcat may hit class/version conflicts. If the server must be provided by an external container, use provided scope per Boot WAR configuration.

Spring Boot repackage has special handling for provided dependencies: an executable WAR can place them in **WEB-INF/lib-provided/**. Therefore, **provided does not mean the server disappears from every archive form**; it means the server is handled separately so both execution modes (external container and java -jar) can coexist.

## 10. Gradle: Plain JAR and Source JAR for a Library

### 10.1. settings.gradle

File **artifact-demo/settings.gradle**:

~~~groovy
rootProject.name = 'artifact-demo'
include 'core', 'app'
~~~

### 10.2. Complete core/build.gradle

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
}

repositories {
    mavenCentral()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            pom {
                name = 'Catalog Core'
                description = 'Reusable Java library'
            }
        }
    }
    repositories {
        maven {
            name = 'localTest'
            url = uri("${rootProject.projectDir}/build/repository")
        }
    }
}
~~~

This is a complete **core/build.gradle** using Groovy DSL:

- **java-library** creates a plain JAR and API/runtime configurations for the library.
- **withSourcesJar()** creates the **sourcesJar** task with classifier **sources**.
- The source JAR is registered as a documentation variant of the Java component.
- **maven-publish** with **from components.java** publishes the Java component, including both binary and source variants.
- Repository **localTest** is a directory-based Maven repository for testing publications without an external server.

### 10.3. Build and Publish Library

From root:

~~~bash
./gradlew :core:clean :core:build
./gradlew :core:publishMavenJavaPublicationToLocalTestRepository
~~~

when a compatible Gradle Wrapper is present. On Windows, use **gradlew.bat**.

Expected artifacts:

~~~text
core/build/libs/
├── core-1.0.0.jar
└── core-1.0.0-sources.jar
~~~

Local repository:

~~~text
build/repository/com/example/core/1.0.0/
├── core-1.0.0.jar
├── core-1.0.0-sources.jar
├── core-1.0.0.pom
└── core-1.0.0.module
~~~

If **withSourcesJar()** is omitted, the sourcesJar task and source variant are not created automatically this way. You can define a JAR task manually, though preferring the standard Java plugin API is recommended.

## 11. Gradle: Executable Boot JAR and Plain JAR

### 11.1. Complete app/build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
    id 'maven-publish'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
}

repositories {
    mavenCentral()
}

dependencies {
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter'
}

tasks.named('jar') {
    archiveClassifier = ''
}

tasks.named('bootJar') {
    archiveClassifier = 'exec'
}

publishing {
    publications {
        appArtifacts(MavenPublication) {
            from components.java
            artifact(tasks.named('bootJar'))
            pom {
                name = 'Catalog Application'
                description = 'Spring Boot application and executable distribution'
            }
        }
    }
    repositories {
        maven {
            name = 'localTest'
            url = uri("${rootProject.projectDir}/build/repository")
        }
    }
}
~~~

**The classifier configuration in this example is intentional:**

- The Boot Gradle plugin normally configures the plain **jar** task with classifier **plain** when bootJar also exists.
- We set an empty classifier on **jar** so the plain archive keeps the main artifact name.
- We set classifier **exec** on **bootJar** so the executable archive carries the -exec suffix.
- **from components.java** publishes the plain Java component and source variant.
- **artifact(tasks.named('bootJar'))** adds the executable Boot JAR to the publication as a secondary artifact.
- This publication demonstrates publishing both files; the app should still be treated as an **application/distribution**, not a library for other modules to import classes from.

If publishing the executable artifact to a Maven repository is unnecessary, remove **maven-publish** and the **publishing** block; simply run the bootJar task to produce the deployment file.

### 11.2. Build and Inspect Results

~~~bash
./gradlew :app:clean :app:build
~~~

With the Spring Boot Gradle plugin, outputs may include:

~~~text
app/build/libs/
├── app-1.0.0.jar
├── app-1.0.0-exec.jar
└── app-1.0.0-sources.jar
~~~

- **app-1.0.0.jar**: plain archive from the Java jar task.
- **app-1.0.0-exec.jar**: executable Boot JAR from bootJar.
- **app-1.0.0-sources.jar**: source archive if withSourcesJar is enabled.

Run the executable:

~~~bash
java -jar app/build/libs/app-1.0.0-exec.jar
~~~

Business output:

~~~text
CATALOG-BOOK-42
~~~

Inspect the plain JAR:

~~~bash
jar tf app/build/libs/app-1.0.0.jar
~~~

Inspect the Boot JAR:

~~~bash
jar tf app/build/libs/app-1.0.0-exec.jar
~~~

**Do not publish or deploy the plain file just because it appears first in the directory listing.** Always pick the exact task/archive matching the consumer contract.

## 12. Gradle: WAR and Executable Boot WAR

To produce a WAR, add the **war** plugin and configure Servlet dependencies in the app module.

### 12.1. Gradle WAR Configuration

Plugins section:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}
~~~

Dependencies:

~~~groovy
dependencies {
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

With the app class extending **SpringBootServletInitializer** as in section 9.2, Gradle creates the **bootWar** task when the war plugin is applied.

If plain WAR and executable WAR need to coexist:

~~~groovy
tasks.named('war') {
    archiveClassifier = ''
}

tasks.named('bootWar') {
    archiveClassifier = 'exec'
}
~~~

These are alternative task configurations replacing the JAR setup in section 11. Do not configure the same module to run both bootJar and bootWar unless the project deliberately intends to build both packaging variants and control publication.

### 12.2. Build and Inspect

~~~bash
./gradlew :app:clean :app:bootWar
~~~

Expected outputs:

~~~text
app/build/libs/
├── app-1.0.0.war
└── app-1.0.0-exec.war
~~~

Inspect the executable WAR:

~~~bash
jar tf app/build/libs/app-1.0.0-exec.war
~~~

You should see:

~~~text
WEB-INF/classes/com/example/app/CatalogApplication.class
WEB-INF/lib/...
WEB-INF/lib-provided/...
~~~

Run directly:

~~~bash
java -jar app/build/libs/app-1.0.0-exec.war
~~~

Or deploy the plain WAR to an external Servlet container per organizational procedure. The container must be compatible with the Spring Boot/Jakarta Servlet version and the WAR must have proper Servlet bootstrapping.

### 12.3. Publishing a Boot WAR

If publishing the Boot WAR, the Spring Boot Gradle Plugin lets you add task output to MavenPublication:

~~~groovy
publishing {
    publications {
        bootApplication(MavenPublication) {
            artifact(tasks.named('bootWar'))
        }
    }
}
~~~

This is a **publication fragment**. The module needs the **maven-publish** plugin and a suitable publishing repository. If a plain WAR is needed as the main artifact alongside an executable WAR classifier, configure classifiers/Java-Web components and inspect the final POM/artifacts rather than assuming one artifact line generates all desired metadata automatically.

## 13. Comparing File Structures to Identify the Right Artifact

| Characteristic | Plain JAR | Boot JAR | Plain WAR | Boot WAR | Source JAR |
| --- | --- | --- | --- | --- | --- |
| Primary package | .jar | .jar | .war | .war | .jar |
| Java classes | package root path | BOOT-INF/classes | WEB-INF/classes | WEB-INF/classes | normally no product .class files |
| Runtime dependencies | separate metadata, usually not nested | BOOT-INF/lib | WEB-INF/lib per packaging | WEB-INF/lib and lib-provided | no runtime deps packaged |
| Spring Boot loader | No | Yes | Not necessarily | Yes | No |
| java -jar | Not by default | Yes | Not by default | Yes for executable Boot WAR | No |
| External Servlet container | No | Not intended | Yes | Yes if configured deployably | No |
| Use as compile dependency | Yes | Should not | No | Should not | No |
| Primary purpose | Library | App distribution | Web deployment | Boot app + Servlet deployment | Source/debugging |

**Structure is fast proof.** Filenames and classifiers can be customized; archive contents reveal the true artifact type.

## 14. How to Inspect Manifests and Entries of a JAR/WAR

### 14.1. Listing Archive Entries

Using the JDK:

~~~bash
jar tf core/target/core-1.0.0.jar
jar tf app/target/app-1.0.0-exec.jar
jar tf app/target/app-1.0.0-exec.war
~~~

The **jar tf** command lists entries without extracting or modifying the file.

### 14.2. Viewing the Manifest

Using unzip:

~~~bash
unzip -p app/target/app-1.0.0-exec.jar META-INF/MANIFEST.MF
~~~

A Boot JAR manifest typically contains:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.app.CatalogApplication
~~~

The exact launcher name depends on the Spring Boot version/loader implementation. Do not hardcode this value as a universal contract across all Boot releases; inspect the actual manifest of the artifact being released.

In a plain JAR, the manifest may contain only version/creator or Main-Class if configured. Do not expect a Spring Boot Start-Class.

### 14.3. Source JAR

~~~bash
jar tf core/target/core-1.0.0-sources.jar
~~~

Verify matching source paths and confirm no unauthorized files are present. A source JAR is for IDE attachment, not a runtime copy of the library.

### 14.4. Comparing Checksums and Sizes

You can compute SHA-256:

~~~bash
sha256sum core/target/core-1.0.0.jar
sha256sum core/target/core-1.0.0-sources.jar
sha256sum app/target/app-1.0.0-exec.jar
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "app\target\app-1.0.0-exec.jar"
~~~

Record checksums alongside release metadata if release policy requires. Having different hashes between a plain JAR and a Boot JAR is normal because their contents/packaging differ; do not compare them to judge build reproducibility.

## 15. Placing the Right Artifact into Maven/Gradle Publications

### 15.1. Maven install/deploy

Maven lifecycle:

- **package**: creates archive files in target.
- **verify**: runs checks and bound plugins, such as attaching the source JAR.
- **install**: installs artifacts/POM/classifiers into the local Maven repository.
- **deploy**: publishes artifacts/POM/classifiers to a remote repository.

With multi-module:

~~~bash
mvn clean verify
mvn install
mvn deploy
~~~

These commands are environment-specific steps and are not necessarily run back-to-back in every pipeline. **deploy** requires configured distributionManagement, credentials, and repository permissions.

Check install/deploy logs to confirm all of:

- Main JAR or WAR.
- Classifier **sources**.
- Classifier **exec** if present.
- POM with exact coordinates.
- Checksums/signatures if generated by repository or policy.

### 15.2. Gradle Publication

Gradle uses **MavenPublication**:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

With a Java component having **withSourcesJar()**, the source variant is included in the publication. When publishing a Boot JAR/Boot WAR separately, attach the task output via **artifact(tasks.named(...))** with the proper classifier.

Specific publication task names are generated from publication name and repository name, e.g.:

~~~bash
./gradlew :core:publishMavenJavaPublicationToLocalTestRepository
~~~

Do not assume task names are identical across projects; check tasks or Gradle logs for the actual name.

### 15.3. One Publication or Multiple Publications?

Choose based on purpose:

| Case | Recommended publishing approach |
| --- | --- |
| Core library | Java component plain JAR + sources + metadata |
| Deploy-only Boot service | Boot JAR via artifact registry/build output |
| Need both plain app JAR and Boot JAR under same Maven GAV | Plain JAR as main artifact, Boot JAR with clear classifier like exec |
| Servlet app | Deployable WAR; optionally add executable Boot WAR classifier |
| Source code | Classifier sources attached to the exact matching binary version |

If an application artifact is stored in a Maven repository, clearly note in release documentation that classifier exec is a **deployment artifact**, not a library dependency.

## 16. Selecting Artifacts in CI/CD and Release Pipelines

A good release pipeline knows clearly which file is the primary output:

1. **Library pipeline:** compile/test, build JAR, build sources JAR, validate POM/Module Metadata, publish binary + source.
2. **Boot service pipeline:** test app, build bootJar, smoke test java -jar, generate SBOM/checksum, publish deployment artifact or container image.
3. **WAR pipeline:** test on matching Servlet/Jakarta API, build WAR, inspect WEB-INF and provided libraries, test deploy into target container.
4. **Source release:** verify sources belong to exact commit, contain no secrets/private generated files, and match binary classifier/version.

### 16.1. Preventing Publishing the Wrong File

Never use wildcard commands like **upload all *.jar in build/libs** when the directory holds plain, executable, and source JARs. Specify exact paths or task outputs.

Example:

~~~text
Library:
  core/build/libs/core-1.0.0.jar
  core/build/libs/core-1.0.0-sources.jar

Application:
  app/build/libs/app-1.0.0-exec.jar
~~~

If Gradle/Maven uses different names due to classifier/finalName, the pipeline must pull the exact artifact path from the task/build configuration.

### 16.2. Consumer Smoke Tests

- For libraries: create an independent consumer project, declare the GAV, and compile a class calling the public API.
- For Boot JARs: run java -jar on the artifact and verify health/output.
- For WARs: deploy to a compatible Servlet container and verify endpoints/context path.
- For source JARs: open the archive and confirm source files match the version.

**Build success does not mean publication is correct.** Verify the final artifact, classifier, metadata, and how consumers actually use the file.

## 17. Common Mistakes and Fixes

**1. Using a Boot JAR as a dependency of another Java module.** Classes live under BOOT-INF/classes. **Fix:** publish a plain JAR of a library module and keep Boot JARs for deployment.

**2. Publishing only a plain JAR of a Spring Boot app while expecting java -jar to work.** Plain JARs usually lack the Boot loader and nested runtime dependencies. **Fix:** publish an executable Boot JAR or package a deliberate standalone classpath.

**3. Publishing a Boot JAR overwriting a library artifact.** Consumers of that GAV may download an archive without a standard package root. **Fix:** use a separate library module or classifier exec, and inspect the main artifact before deploying.

**4. Thinking classifier exec makes the artifact an independent module coordinate.** A classifier only distinguishes a secondary artifact within the same GAV. **Fix:** use separate coordinates if the product needs a distinct metadata/consumer contract.

**5. Using a WAR for a Java library.** WARs are for web applications. **Fix:** choose a plain JAR for libraries.

**6. Choosing WAR but forgetting SpringBootServletInitializer.** External Servlet containers may fail to initialize the Boot context as expected. **Fix:** configure the initializer for traditional Servlet deployment and test in a real container.

**7. Putting embedded Tomcat into a WAR as a normal runtime dependency.** External containers may hit class/server conflicts. **Fix:** use provided/providedRuntime in Maven/Gradle and inspect WEB-INF/lib-provided in executable Boot WARs.

**8. Thinking every Boot WAR deploys to every Tomcat.** Jakarta Servlet/API compatibility depends on Boot and container versions. **Fix:** verify container version and namespace compatibility.

**9. Picking a WAR just because the filename ends in .war.** A WAR might lack bootstrapping or required dependencies. **Fix:** check Servlet initialization, archive layout, and run a deploy smoke test.

**10. Publishing only the source JAR and forgetting the binary JAR.** Consumers cannot use a source archive as a compiled product dependency. **Fix:** publish the source JAR as a supplementary artifact alongside the binary.

**11. Source JAR not generated in Maven.** Simply listing the filename in README does not build the archive. **Fix:** configure Maven Source Plugin goal jar-no-fork in the appropriate lifecycle phase.

**12. Forgetting withSourcesJar() in Gradle.** No source variant is added automatically to the Java component. **Fix:** enable java.withSourcesJar() and inspect publication outputs.

**13. Source JAR does not match binary version.** The debugger shows wrong source lines. **Fix:** build sources and binaries from the same commit, version, and source set.

**14. Source JAR accidentally contains secrets or proprietary internal sources.** Source archives are typically downloaded just as easily as other artifacts. **Fix:** review include/exclude patterns, licenses, and policies before releasing.

**15. Default Maven repackage replaces the main artifact.** The original file is kept as .original in target, which is not a published classifier. **Fix:** configure a classifier if the plain archive must be retained in install/deploy.

**16. Using attach=false while expecting the Boot JAR to be deployed.** The plugin creates a local executable file but does not attach it for install/deploy. **Fix:** remove attach=false or publish the file via a separate distribution step.

**17. Maven declares classifier exec but execution id does not match repackage.** The configuration may not apply to the parent-defined execution. **Fix:** check the execution id in the Spring Boot parent and the plugin's effective POM.

**18. Gradle runs only the jar task when expecting a Boot JAR.** The jar task produces a plain archive. **Fix:** run bootJar for the executable archive.

**19. Gradle runs only bootJar when needing a source archive.** Boot JAR does not replace sourcesJar. **Fix:** enable withSourcesJar and build sourcesJar/assemble/build per configuration.

**20. Gradle does not set explicit classifiers when publishing in parallel.** The plugin may assign a plain classifier to the default jar/war task. **Fix:** configure archiveClassifier on both plain and executable tasks, then inspect filenames.

**21. Publishing all archives with a wildcard.** Consumers might download -plain.jar, -sources.jar, or Boot JARs by mistake. **Fix:** declare exact artifact tasks/paths.

**22. Relying solely on filename to confirm artifact type.** Classifiers can be renamed arbitrarily. **Fix:** use jar tf, manifest inspection, and archive layout.

**23. Assuming a plain JAR bundles dependencies.** Plain library JARs normally contain only the module's classes/resources. **Fix:** publish POM/Gradle Module Metadata and let consumers resolve dependencies.

**24. Using a source JAR as a runtime dependency.** It provides no compiled product bytecode. **Fix:** attach sources only for IDE/debugging; use the binary JAR in the dependency graph.

**25. Publishing a Boot JAR with incomplete POM dependency metadata.** An executable artifact can run standalone, yet consumer metadata remains incomplete. **Fix:** distinguish deployment packages from library publications and inspect the POM.

**26. Using an executable WAR with WebFlux assuming traditional Boot WAR is supported.** WebFlux has specific Spring Boot WAR deployment limitations. **Fix:** check reactive deployment docs; for Boot WebFlux, prefer executable JARs as supported.

**27. Failing to test against a real external container.** A WAR can build fine yet fail due to Servlet version, classloader, or context path. **Fix:** smoke test on the environment's exact container/version.

**28. Assuming a source JAR automatically includes Javadoc.** Source archives contain sources; Javadoc is a separate documentation artifact type. **Fix:** if API docs are needed, configure a separate Javadoc JAR.

**29. Changing a classifier without updating the release pipeline.** CI may keep uploading the old path or miss the new artifact. **Fix:** check output names, publication config, and consumer contracts.

**30. Publishing under the same GAV while overwriting with different bytes.** Maven/Gradle caches can leave consumers seeing inconsistent old/new artifacts. **Fix:** keep release versions immutable; bump the version whenever binary contents change.

## 18. Pre-Release Checklist

- [ ] Determine whether the recipient will **import classes**, **run the app**, **deploy a WAR**, or **read sources**.
- [ ] Pick the right artifact type: plain JAR, Boot JAR, WAR, or source JAR.
- [ ] Keep library modules separate from executable application modules.
- [ ] Verify GAV and classifiers are consistent across build, publication, and consumers.
- [ ] Maven: verify jar/war packaging, repackage execution, classifier, attach, and source plugin.
- [ ] Gradle: verify jar/bootJar or war/bootWar, archiveClassifier, and withSourcesJar().
- [ ] Never use a Boot executable JAR as a compile dependency.
- [ ] For WARs, confirm SpringBootServletInitializer and Servlet/Jakarta container compatibility.
- [ ] For executable WARs, check provided dependencies and WEB-INF/lib-provided.
- [ ] Source JARs must match the binary's exact version/commit.
- [ ] Source distributions contain no secrets or unauthorized code.
- [ ] Run jar tf and inspect the manifest/layout of the final artifact.
- [ ] Run java -jar for Boot JAR/Boot WAR.
- [ ] Deploy the WAR into the target container if that is the release contract.
- [ ] An independent consumer resolves the right binary and dependency metadata.
- [ ] CI uploads exact artifacts, never wildcarding all files in the output directory.
- [ ] Record checksum/SBOM/signature/provenance per release policy.
- [ ] Release versions are immutable; byte changes require a new version.

## 19. Official References

- Spring Boot 3.3 — Packaging Executable Archives (Maven): https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Packaging Executable Archives (Gradle): https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Publishing an Application with Gradle: https://docs.spring.io/spring-boot/3.3/gradle-plugin/publishing.html
- Maven Source Plugin — Usage and source JAR attachment: https://maven.apache.org/plugins/maven-source-plugin/usage.html
- Maven Source Plugin — jar-no-fork goal: https://maven.apache.org/plugins/maven-source-plugin/jar-no-fork-mojo.html
- Gradle 8.5 — Java Plugin and sources JAR: https://docs.gradle.org/8.5/userguide/java_plugin.html
- Gradle 8.5 — Maven Publish Plugin: https://docs.gradle.org/8.5/userguide/publishing_maven.html
- Maven — POM Reference: https://maven.apache.org/pom.html
- Maven — Maven Deploy Plugin: https://maven.apache.org/plugins/maven-deploy-plugin/
- Java 17 — Jar tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html

**Conclusion:** choose the artifact based on **how the recipient will use the product**. A **plain JAR** is the binary for libraries, a **Boot JAR** is a self-running deployment package, a **WAR** is a web archive for Servlet containers, and a **source JAR** is source code accompanying the binary. Maven/Gradle can build and publish multiple artifact types under the same version using classifiers, yet a classifier does not change the internal structure of a file. Always verify **coordinates, classifier, archive layout, dependency metadata, and actual runtime/deployment behavior** before marking a release complete.