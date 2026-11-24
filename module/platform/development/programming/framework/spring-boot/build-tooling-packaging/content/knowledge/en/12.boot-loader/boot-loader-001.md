# Why the JVM Needs Boot Loader to Run a JAR with Nested Libraries

## 1. The Problem: One JAR File, Containing Many Other JARs Inside

When developing a Spring Boot application, we commonly add dependencies such as Spring Framework, Jackson, logging, and an embedded servlet container. Running in an IDE or via Maven/Gradle seems simple because the build tool automatically builds a **classpath** containing the application's class directory and many separate downloaded JAR files.

When deploying the application to a server, having to copy dozens or hundreds of dependency JARs into the right directory with the right versions and writing the exact **java -cp ...** command is error-prone. Spring Boot solves this by creating an **executable JAR**: a single distribution file containing the application, its runtime dependencies, and dedicated startup code.

For example, a Spring Boot JAR might have the following structure:

~~~text
loader-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── ... Spring Boot Loader classes ...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/loaderdemo/LoaderDemoApplication.class
    │   ├── com/example/loaderdemo/NestedController.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-....jar
    │   ├── spring-context-....jar
    │   ├── jackson-databind-....jar
    │   └── ...
    ├── classpath.idx  (if present)
    └── layers.idx     (if present)
~~~

The library names and versions are illustrative only; the actual dependency versions are chosen by the build resolver. **BOOT-INF/classes/** contains the application's classes and resources, and **BOOT-INF/lib/** contains **intact JAR files nested inside the outer JAR**. The classes in **org/springframework/boot/loader/** handle startup.

**Central question:** If **loader-demo-1.0.0.jar** is a valid JAR file, why can't Java/JVM automatically find all classes in **BOOT-INF/lib/**? Why are **Spring Boot Loader** and **JarLauncher** necessary?

The short answer: **Java's standard classpath/JAR mechanism does not automatically treat a JAR file inside another JAR file as a classpath entry**. Spring Boot Loader adds the capability to access and load nested JARs, constructs the appropriate class loader, and then invokes the application's **main()**.

The key point to remember: **the JVM does not need Spring Boot Loader for every Java application**. It only needs an equivalent mechanism when executing **Spring Boot's nested-JAR archive format** without unpacking every library into separate files. You can also run Java with external JARs on the classpath or use another packaging approach.

## 2. How Does the JVM Normally Find Classes?

### 2.1. The Classpath Is a Set of Locations to Search for Classes/Resources

A Java application with main class **com.example.Main** and external library **my-lib.jar** can be run in the standard way:

~~~bash
java -cp "classes:lib/my-lib.jar" com.example.Main
~~~

On Windows, the classpath separator is usually **;**, for example:

~~~powershell
java -cp "classes;lib/my-lib.jar" com.example.Main
~~~

Here:
- **classes/** is a directory containing the package structure **com/example/Main.class**.
- **lib/my-lib.jar** is **a separate JAR file on the filesystem**.
- The JVM and standard class loaders can locate classes/resources through the provided classpath entries.
- **-cp** specifies classpath locations; it **does not create** new libraries and does not recursively search all JARs nested inside each JAR.

A basic JAR typically places **com/example/Main.class** directly along the package path at the **archive root**. If the Main class is placed under a separate nested directory like **BOOT-INF/classes/com/example/Main.class**, a regular class loader treating the outer JAR as a classpath entry **does not automatically treat BOOT-INF/classes as a separate classpath root**.

### 2.2. java -jar Mode Uses the Manifest

A regular JAR has a manifest specifying:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
~~~

When running:

~~~bash
java -jar app.jar
~~~

The Java launcher reads **META-INF/MANIFEST.MF**, identifies **Main-Class**, loads that class according to JAR execution rules, and calls **public static void main(String[] args)**.

When using **-jar**, user-supplied classpath settings via **-cp / -classpath** or **CLASSPATH** are not used the way they are when passing a main class name directly. If external JARs are needed for an ordinary executable JAR, **Class-Path** can be configured in the manifest pointing to appropriate external JARs. However, **Class-Path does not turn nested JAR files in BOOT-INF/lib into JARs that Java opens recursively**.

Thus **java -jar** solves finding the main entry point, **not** handling the **JAR-containing-JAR** format on its own.

### 2.3. Why Putting a .jar File Inside Another .jar File Is Not Enough

Suppose an archive contains:

~~~text
plain-app.jar
├── META-INF/MANIFEST.MF
├── com/example/Main.class
└── BOOT-INF/lib/utility.jar
                  └── (inside utility.jar is com/example/Utility.class)
~~~

**jar tf plain-app.jar** will see the entry **BOOT-INF/lib/utility.jar**, but **Utility.class** is not a direct entry at the root of **plain-app.jar**. The standard Java launcher does not treat the **utility.jar** entry as an independent module/classpath root. If **Main** calls **Utility**, the runtime may throw **NoClassDefFoundError** or another class-loading error.

This is not an issue of "the JVM doesn't support ZIP" — Java can read JAR/ZIP files in many contexts. The issue is that **standard classpath rules do not automatically open a JAR inside a JAR and merge all inner files into the class lookup path**.

## 3. Spring Boot Executable JAR Keeps Libraries as Nested JARs

The Spring Boot format preserves the boundaries of each dependency:

| Location in archive | What does it contain? | Purpose |
| --- | --- | --- |
| **META-INF/MANIFEST.MF** | Startup metadata | Points to the Boot launcher and the real main class |
| **org/springframework/boot/loader/** | Boot Loader classes | Entry point and classes supporting nested JAR loading |
| **BOOT-INF/classes/** | Application compiled classes + main resources | Application classpath root |
| **BOOT-INF/lib/*.jar** | Runtime dependency archives | Spring, Jackson, logging, server... |
| **BOOT-INF/classpath.idx** (depending on config) | Order in which JARs are added to the classpath | Helps the launcher preserve classpath order like the build system |
| **BOOT-INF/layers.idx** (depending on config) | Layer index | Used for splitting Docker/OCI image layers, not a mandatory class list |

The path **BOOT-INF/lib/jackson-databind-...jar** is a **file entry** of the outer JAR; the contents inside are still Jackson's JAR structure. Spring Boot uses a nested access mechanism instead of extracting all dependencies to a temporary directory before every run.

This provides:
- A single executable archive that is easy to copy and deploy.
- Ability to distinguish each dependency by JAR name/version instead of mixing all classes together.
- Preservation of most metadata/resources of each JAR according to its original archive.
- The ability to use the same packaging approach across multiple JVM-supported environments.

It is important to distinguish a **Spring Boot executable JAR** from a **thin/plain JAR**: a plain JAR usually contains only the project's own classes/resources and relies on an external classpath for dependencies. Both are JAR files, but their **class layout and execution model** differ.

## 4. What Boot Loader Is and What It Is Not

**Spring Boot Loader** is Java code that bootstraps a Spring Boot archive. It is not:
- A new JVM replacing HotSpot/OpenJ9.
- A Spring **ApplicationContext** or bean-managing container.
- A dependency version management tool like Maven/Gradle.
- A mechanism that automatically downloads missing libraries from the internet at runtime.
- A reason to skip choosing a compatible JDK.

In Spring Boot 3.5, the launcher classes are described in the **org.springframework.boot.loader.launch** package:

- **JarLauncher**: uses the executable JAR structure with **BOOT-INF/classes** and **BOOT-INF/lib**.
- **WarLauncher**: uses the executable WAR structure, e.g., **WEB-INF/classes**, **WEB-INF/lib**, and **WEB-INF/lib-provided**.
- **PropertiesLauncher**: can add library paths via loader configuration such as **loader.path / LOADER_PATH**, suitable for certain models requiring controlled classpath expansion.

**Package names may vary by Spring Boot version.** Some older Boot articles use **org.springframework.boot.loader.JarLauncher**. Starting from Boot 3.2, the common name is **org.springframework.boot.loader.launch.JarLauncher**; when debugging, always inspect **the manifest of the actual artifact**, rather than copying launcher names from years-old examples.

### 4.1. The Launcher Runs Before the Application

In a Spring Boot executable JAR, **Main-Class** is not necessarily **com.example.MyApplication**. It is typically **JarLauncher**:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.loaderdemo.LoaderDemoApplication
~~~

**Main-Class** is invoked first by the Java launcher; **Start-Class** is used by Boot Loader to find the real main class. This is a bridging solution: Java understands the manifest and runs a class accessible right at the archive root; Boot Loader then understands Boot's custom nested-JAR structure.

Do not confuse the two attributes: if **Main-Class** points directly to the application while that class resides in **BOOT-INF/classes**, the standard Java launcher may fail to find it. **Start-Class** is not a default attribute interpreted by the Java launcher like **Main-Class**; it is a Spring Boot Loader convention.

### 4.2. Who Is Responsible for What?

| Component | Primary responsibility |
| --- | --- |
| **java launcher / JVM** | Reads the manifest in -jar mode, starts the Java runtime, loads the entry point class by standard rules |
| **Boot JarLauncher** | Understands Boot archive structure; builds the necessary classpath entries from application classes and nested libs |
| **Boot nested-JAR support / ClassLoader** | Reads classes and resources from JARs located inside the outer archive |
| **Application main()** | Calls SpringApplication.run or the application's Java logic |
| **SpringApplication / ApplicationContext** | Creates the context, registers beans, runs auto-configuration, starts the web server if present |
| **Embedded Tomcat/Jetty/Netty** | Handles requests per runtime configuration when the corresponding dependency is present |

Boot Loader **solves packaging and class loading**. Spring Framework and the Spring Boot application infrastructure **solve application execution and business configuration**. These are two separate layers.

## 5. Sequence When Running java -jar application.jar

~~~text
$ java -jar loader-demo-1.0.0.jar
                  |
                  v
  Java reads META-INF/MANIFEST.MF
                  |
                  v
  Finds Main-Class = ...launch.JarLauncher
                  |
                  v
  Loads and invokes launcher main()
                  |
                  v
  Boot Loader accesses BOOT-INF/classes and BOOT-INF/lib/*.jar
                  |
                  v
  Creates nested-JAR-capable class loader, builds classpath
                  |
                  v
  Finds Start-Class = com.example.loaderdemo.LoaderDemoApplication
                  |
                  v
  Invokes LoaderDemoApplication.main(args)
                  |
                  v
  SpringApplication.run(...); Spring context + server
~~~

Notes:
1. **There is no default "open and extract all JARs to disk" step**. Boot's nested JAR support can load content directly from the outer archive.
2. Passing **--server.port=9090** after the JAR name is an argument to the Spring Boot application; it **does not replace** Main-Class or Boot Loader.
3. The classpath when launching a Boot archive differs from how an IDE or **spring-boot:run / bootRun** builds the classpath. IDEs typically use **build/classes** and dependency JARs resolved as separate files in the Gradle/Maven cache.
4. Spring Boot Loader is the bootstrap layer and does not guarantee the application will succeed: a missing JDK, main class error, missing dependency, bean error, or database configuration issue can still stop the runtime.

## 6. How Boot Reads Nested JARs Directly

### 6.1. Technical Challenge with Two-Level ZIP/JAR

JAR is based on ZIP. The outer JAR has a list of entries, including an entry **BOOT-INF/lib/dependency.jar**. That entry itself is **an independent ZIP/JAR** with its own list of classes/resources. Standard Java APIs do not provide a default classpath mechanism to traverse both layers when running **java -jar**.

Spring Boot provides nested archive support classes, typically **NestedJarFile**. According to the Boot specification, when reading the archive, the loader can map entries of a nested JAR to **physical offsets** within the outer JAR file. When a specific class/resource is needed, it seeks to the corresponding position **without having to extract the entire archive to disk** or load the entire JAR into RAM.

Illustrative diagram:

~~~text
outer.jar
+------------------------------------------------+
| BOOT-INF/classes/... | BOOT-INF/lib/tool.jar   |
|   Main.class         | +---------------------+ |
|                      | | LibA.class          | |
|                      | | LibB.class          | |
|                      | +---------------------+ |
+------------------------------------------------+
          ^                         ^
  entry in outer           entries of nested JAR
                                    |
                              offset mapping
                                    |
                           class loader reads bytes
~~~

**NestedJarFile** is not an API that replaces all JVM class loader behavior. It is a component for accessing entries; Spring Boot's class loader uses appropriate URLs/resource sources to load classes/resources according to the Java class-loading contract.

### 6.2. Why Must Nested JAR Entries Be STORED?

The Spring Boot executable JAR specification requires that **the entry containing a nested JAR inside the outer ZIP must use the ZipEntry.STORED method** (the outer entry itself is uncompressed). The goal is to allow seeking directly to byte offsets inside the nested JAR to read its entries.

A common misconception: **STORED applies only to the JAR entry inside the outer JAR**; **entries inside the nested JAR itself can still be compressed**. Other entries of the outer JAR can also use appropriate compression. You do not need to disable compression across the entire Spring Boot archive.

Maven **spring-boot:repackage** and Gradle **bootJar** produce the compliant format. If you manually edit the JAR with a regular zip tool and recompress nested jar entries improperly, Boot Loader may fail when opening the libraries; do not manually alter the ZIP compression method or restructure **BOOT-INF/lib** without understanding the packaging constraints.

### 6.3. Nested URLs and Resource Access

Spring Boot Loader supports URLs for nested content. In recent Boot versions, the documentation illustrates the form:

~~~text
jar:nested:/path/myapp.jar/!BOOT-INF/lib/mylib.jar!/com/example/Library.class
~~~

This URL illustrates a class **Library.class** inside **mylib.jar**, where **mylib.jar** is inside the outer **myapp.jar**. Boot provides a way to open connections compatible with Java APIs such as **JarURLConnection**/URL-based class loading.

**Do not manually split URLs to derive a real file path**: a nested URL does not mean **/path/myapp.jar/BOOT-INF/lib/mylib.jar** is a directory that can be opened with the File API. Instead, use class loader/resource APIs, or use a dedicated packaging API if you genuinely need to manipulate the archive.

## 7. Why Thread Context ClassLoader Matters

In Java, there are multiple class loaders with different roles: bootstrap/platform, application/system, and additional class loaders created by frameworks. Spring Boot Loader sets up the environment so the main application can find classes/resources from **BOOT-INF/classes** and nested libs.

Libraries that use **Thread.currentThread().getContextClassLoader()** usually work properly in this model. Many SPI mechanisms and resource lookups rely on the **Thread Context ClassLoader (TCCL)**. However, a library trying to load a nested dependency via:

~~~java
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();
Class<?> type = systemLoader.loadClass(
        "com.fasterxml.jackson.databind.ObjectMapper");
~~~

may fail to find the class in **BOOT-INF/lib** when running **java -jar** on a Boot archive. The reason: **the system class loader does not automatically share visibility with the class loader that Boot Launcher uses to load nested JARs**. Do not treat the snippet above as the proper way to load Spring Boot dependencies.

A better approach when using SPI/resource APIs is to use TCCL:

~~~java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();

Class<?> type = loader.loadClass(
        "com.fasterxml.jackson.databind.ObjectMapper");

System.out.println(type.getName());
~~~

This is an **illustrative method-body snippet**, not a standalone compilable Java class. If placed in a method declaring or handling **ClassNotFoundException**, with Jackson present on the runtime classpath of the example below, the expected stdout line is:

~~~text
com.fasterxml.jackson.databind.ObjectMapper
~~~

However, not every library needs to write manual code like this. With Spring, you should generally let dependency injection, ServiceLoader with the right class loader, or framework APIs perform the loading. The purpose of the snippet above is to understand class visibility scope.

**The Spring Boot specification notes** that libraries attempting to use **ClassLoader.getSystemClassLoader()** to load classes in nested JARs may fail. In cases where a library requires the JAR to exist as a separate file on the filesystem, see the **requiresUnpack** section or another packaging approach.

## 8. Runnable Example: Spring Boot Using Jackson from BOOT-INF/lib

We will use an endpoint that requires **com.fasterxml.jackson.databind.ObjectMapper**. The **ObjectMapper** class comes from the Jackson dependency in starter-web and is packaged as a JAR under **BOOT-INF/lib**. From there we can verify in practice that Boot Loader loads nested dependencies without needing a manual **-cp** list.

Example versions: **Java 17, Spring Boot 3.5.16**. This is a combination chosen to illustrate Boot 3.5's executable JAR format; for new projects, use a supported branch per your organization's policy. Use **Maven or Gradle**, not both at once. The Java files are shared between both options.

### 8.1. Directory Structure

~~~text
loader-demo/
├── pom.xml                    (if using Maven)
│   or
├── build.gradle               (if using Gradle)
├── settings.gradle            (if using Gradle)
├── mvnw / mvnw.cmd / .mvn/wrapper/...         (Maven Wrapper)
├── gradlew / gradlew.bat / gradle/wrapper/... (Gradle Wrapper)
└── src/
    ├── main/java/com/example/loaderdemo/
    │   ├── LoaderDemoApplication.java
    │   └── NestedController.java
    ├── main/resources/application.properties
    └── test/java/com/example/loaderdemo/
        └── NestedControllerTests.java
~~~

Wrapper scripts and metadata must be generated via Spring Initializr or the corresponding Wrapper tool. Merely creating **pom.xml** or **build.gradle** will not automatically generate **./mvnw** or **./gradlew**.

### 8.2. Main Class

File **src/main/java/com/example/loaderdemo/LoaderDemoApplication.java**:

~~~java
package com.example.loaderdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoaderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoaderDemoApplication.class, args);
    }
}
~~~

This class does not load nested JARs by itself. That happens before this class's **main()** is called when running the executable archive with **java -jar**.

### 8.3. Controller Using Jackson

File **src/main/java/com/example/loaderdemo/NestedController.java**:

~~~java
package com.example.loaderdemo;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class NestedController {

    private final ObjectMapper objectMapper;

    public NestedController(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @GetMapping("/nested")
    public String nested() {
        return objectMapper.createObjectNode()
                .put("message", "nested-ok")
                .path("message")
                .asText();
    }
}
~~~

**ObjectMapper** is auto-configured as a bean by Spring Boot when Jackson is on the classpath. The code does not manually craft a JSON string to fake it; it actually invokes a **Jackson ObjectMapper** method and extracts a property from the Jackson tree model.

Spring Boot starter-web (3.5 line in this example) brings Jackson into the dependency graph. When packaged as an executable JAR, Jackson classes reside inside **one or more nested dependency JARs** under **BOOT-INF/lib**, rather than being copied as flat classes at the root of the outer JAR.

### 8.4. application.properties

File **src/main/resources/application.properties**:

~~~properties
spring.application.name=loader-demo
server.port=8080
~~~

The value 8080 is set explicitly to make testing the endpoint easy. If port 8080 is already in use by another process, you can run **java -jar ... --server.port=9090** and adjust the test URL accordingly.

### 8.5. HTTP Endpoint Test

File **src/test/java/com/example/loaderdemo/NestedControllerTests.java**:

~~~java
package com.example.loaderdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class NestedControllerTests {

    @Autowired
    private MockMvc mvc;

    @Test
    void canUseNestedJacksonDependency() throws Exception {
        mvc.perform(get("/nested"))
                .andExpect(status().isOk())
                .andExpect(content().string("nested-ok"));
    }
}
~~~

The test verifies that the endpoint uses ObjectMapper through the Spring context. It is not yet direct proof that the executable JAR loads nested libs, because tests usually run on the classpath constructed by the build tool. **You need to run the JAR itself** after packaging to additionally verify the Boot Loader layer.

## 9. Packaging with Maven and Spring Boot Loader

Create **pom.xml**:

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
    <artifactId>loader-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
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

Maven **spring-boot-starter-parent** provides dependency management and a preconfigured **repackage** execution when the Spring Boot Maven Plugin is declared. The **spring-boot:repackage** goal **converts the plain JAR into an executable Boot JAR**, adding the necessary layout and loader. If you do not use the parent, you must configure the plugin's execution/version appropriately.

Run from the root:

~~~bash
./mvnw --version
./mvnw clean verify
java -jar target/loader-demo-1.0.0.jar
~~~

On Windows use **mvnw.cmd**. **clean verify** includes the package phase in the Maven default lifecycle and runs configured tests; package/repackage generates the archive in **target/**. If tests/build fail, do not assume the JAR was produced successfully.

From another terminal:

~~~bash
curl http://localhost:8080/nested
~~~

Expected response body, without quotes:

~~~text
nested-ok
~~~

Meaning: when actually running **java -jar target/loader-demo-1.0.0.jar**, Java first invokes the launcher per the manifest; the launcher loads the application classes and the nested Jackson JAR; the Spring context starts up, and the endpoint uses ObjectMapper and returns the result.

## 10. Packaging the Same Application with Gradle

If choosing Gradle, **do not use pom.xml** from the previous section. Create **settings.gradle**:

~~~groovy
rootProject.name = 'loader-demo'
~~~

Create **build.gradle** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The Spring Boot Gradle Plugin creates the **bootJar** task, using the application's classpath/dependencies to produce an executable archive with the Boot layout and launcher. The Spring Dependency Management Plugin receives the managed dependency versions from the Spring Boot plugin. Test-only libraries are normally not packaged into the production executable JAR.

With a suitable Gradle Wrapper, such as Gradle **8.14** within Boot 3.5's supported range, run:

~~~bash
./gradlew --version
./gradlew clean test bootJar
java -jar build/libs/loader-demo-1.0.0.jar
~~~

Windows uses **gradlew.bat**. Once startup succeeds, call:

~~~bash
curl http://localhost:8080/nested
~~~

The expected response body is also:

~~~text
nested-ok
~~~

**build/libs/loader-demo-1.0.0.jar** is the default name based on the project name and version, which may differ if the project customizes archive naming. Do not look for the JAR in **target/** in a Gradle project or in **build/libs/** in a Maven project unless the actual build script changed the path.

## 11. Self-Check: Where Are the Manifest and Real Libraries Located?

A JAR file ending in **.jar** does not guarantee it was repackaged properly. You must check for the signs.

### 11.1. List Entries in the Artifact

With Maven:

~~~bash
jar tf target/loader-demo-1.0.0.jar
~~~

With Gradle:

~~~bash
jar tf build/libs/loader-demo-1.0.0.jar
~~~

In the long list, look for entries like:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/loaderdemo/LoaderDemoApplication.class
BOOT-INF/classes/com/example/loaderdemo/NestedController.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/spring-boot-....jar
BOOT-INF/lib/jackson-databind-....jar
BOOT-INF/lib/...
~~~

These are **the paths to look for**, not the entire output or a promise about JAR counts/versions. **jar tf** lists file entries of the outer archive: it does not automatically open each nested JAR and print every Jackson class inside. To see the actual Jackson classes inside a nested dependency, read the nested archive with an appropriate tool or extract a **copy** for inspection.

For example, on Linux/macOS you can filter the output:

~~~bash
jar tf target/loader-demo-1.0.0.jar | grep 'BOOT-INF/lib/jackson-databind'
jar tf target/loader-demo-1.0.0.jar | grep 'loader/launch/JarLauncher.class'
~~~

The commands above assume you chose Maven. For Gradle, change the JAR path to **build/libs/**. A dependency graph can change the Jackson implementation depending on the Boot version; always check the actually resolved libraries instead of assuming all library names are fixed.

On PowerShell:

~~~powershell
jar tf .\target\loader-demo-1.0.0.jar |
    Select-String 'BOOT-INF/lib/jackson-databind'
~~~

### 11.2. Inspect Main-Class and Start-Class in MANIFEST.MF

Use a ZIP viewer or extract just that entry from the archive into a **temporary directory** to avoid overwriting files in the repository.

Linux/macOS with the Maven JAR:

~~~bash
mkdir -p jar-inspect
cd jar-inspect
jar xf ../target/loader-demo-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
cd ..
~~~

The Gradle JAR is correspondingly at **../build/libs/loader-demo-1.0.0.jar**. In a Boot 3.5 manifest, expect fields similar to:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.loaderdemo.LoaderDemoApplication
Spring-Boot-Version: 3.5.16
~~~

The manifest may also contain other fields (implementation-title/version, Build-Jdk-Spec, layers indexes...) and values configured by plugins. **Do not perform an exact verbatim match on the entire manifest**; checking the **Main-Class** (launcher) and **Start-Class** (application) pair is the focus.

**Do not confuse jar xf with running the application:** jar xf extracts ZIP files and does not start main. It writes files into the current directory, so only do this in an allowed location. If the archive contains sensitive data, do not unnecessarily share or upload the extracted contents.

### 11.3. Why Is Class-Path Not Needed in the Manifest?

For a Boot executable JAR, **JarLauncher** locates the nested JARs according to Boot's layout, so the manifest does not need to list **Class-Path: lib/a.jar lib/b.jar**. Manifest Class-Path is meant for external JARs at relative locations; it is **not the standard way to point to BOOT-INF/lib/*.jar as internal ZIP entries**.

A common debugging mistake is seeing a missing **Class-Path** and concluding the executable JAR has no dependencies. For a Boot archive, check **BOOT-INF/lib**, Boot Loader classes, and **Main-Class/Start-Class**.

## 12. Pure Java Experiment: Nested JARs Do Not Automatically Become Classpath

This is a standalone experiment independent of Spring Boot, suitable for Java 17+; it directly illustrates the **JAR-in-JAR** problem before applying Boot Loader.

Suppose we prepare:
- File **lib-src/demo/lib/Formatter.java**;
- File **app-src/demo/app/Main.java**.

### 12.1. Library Class

~~~java
package demo.lib;

public class Formatter {
    public static String text() {
        return "library-loaded";
    }
}
~~~

### 12.2. Main Class Calling the Library

~~~java
package demo.app;

import demo.lib.Formatter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Formatter.text());
    }
}
~~~

### 12.3. Compile, Create Two JARs, and Run with Normal Classpath

In a separate experiment workspace on Linux/macOS:

~~~bash
mkdir -p lib-classes app-classes BOOT-INF/lib

javac -d lib-classes lib-src/demo/lib/Formatter.java
jar --create --file BOOT-INF/lib/demo-lib.jar -C lib-classes .

javac -cp BOOT-INF/lib/demo-lib.jar -d app-classes app-src/demo/app/Main.java
jar --create --file plain-app.jar --main-class demo.app.Main -C app-classes .

java -cp "plain-app.jar:BOOT-INF/lib/demo-lib.jar" demo.app.Main
~~~

Exact stdout of the last line:

~~~text
library-loaded
~~~

The **demo-lib.jar** library is currently a standalone file on the filesystem and was listed directly on the classpath — therefore Java finds the **Formatter** class.

### 12.4. Put the Library Inside the App JAR, Then Run java -jar

~~~bash
jar --update --file plain-app.jar -C . BOOT-INF/lib/demo-lib.jar

jar tf plain-app.jar
java -jar plain-app.jar
~~~

The update command merely inserts **demo-lib.jar** as the **BOOT-INF/lib/demo-lib.jar** entry of the outer JAR; it **does not add Spring Boot Loader**, does not change the manifest to start through JarLauncher, and does not make the Java launcher automatically list nested libs.

**Expected result of java -jar:** the program does not print **library-loaded** successfully, but fails with a class loading error (usually containing **NoClassDefFoundError: demo/lib/Formatter**). The exact stack trace wording and line positions depend on the JDK, so do not treat the full message as fixed stdout.

Reason: the manifest still points directly to **demo.app.Main**, while **demo.lib.Formatter** is only present in the nested JAR, not on the classpath visible to java -jar. Naming a folder **BOOT-INF/lib** **is not enough**; running in Boot layout requires the loader, manifest, and Boot archive constraints.

**Windows:** the normal classpath command example in the first step must change the **:** separator to **;**:

~~~powershell
java -cp "plain-app.jar;BOOT-INF/lib/demo-lib.jar" demo.app.Main
~~~

On Windows you can create the directories via PowerShell/Explorer; the **javac** and **jar** commands have similar options. Do not use this experiment to modify production archives; perform it in a separate workspace.

## 13. Common Mistake: java -cp boot.jar com.example.Main

A Spring Boot executable JAR places compiled application classes under:

~~~text
BOOT-INF/classes/com/example/loaderdemo/LoaderDemoApplication.class
~~~

When invoking:

~~~bash
java -cp loader-demo-1.0.0.jar com.example.loaderdemo.LoaderDemoApplication
~~~

The Java launcher uses the outer JAR as the classpath root and usually fails to find **com/example/loaderdemo/LoaderDemoApplication.class** at the archive root, because it resides deeper under **BOOT-INF/classes**. The result is usually **Could not find or load main class** or **ClassNotFoundException**.

Even if you try pointing **-cp** directly to **BOOT-INF/lib** inside the JAR filename, a path like **loader-demo.jar/BOOT-INF/lib/...** is not a separate JAR file on the filesystem. Standard CLI classpath handling does not process Boot's nested layout.

**Correct command for a Boot executable JAR**:

~~~bash
java -jar loader-demo-1.0.0.jar
~~~

If you are in the Maven/Gradle root directory, use the exact **target/...** or **build/libs/...** path as generated. When you want to manage the Java classpath manually instead of using Boot Loader, you need a **properly extracted layout** or another packaging method, and must provide every actual classpath entry.

**Do not add -cp after java -jar expecting it to fix the classpath.** In **-jar** mode, external classpath options do not behave like **-cp mainClass** mode; arguments after the JAR name may be passed to the main method.

## 14. Why Do IDE Runs and bootRun Still Work Without an Executable JAR?

When running Spring Boot directly in an IDE, Eclipse/IntelliJ, or:

~~~bash
./mvnw spring-boot:run
~~~

or:

~~~bash
./gradlew bootRun
~~~

the build tool usually constructs a standard classpath consisting of:
- the application's compiled classes/resources directories;
- dependency JARs stored separately in the Maven/Gradle cache;
- an appropriate main application class.

In this situation, **there is no need to load nested JARs inside an archive** because dependencies have not been packaged inside **BOOT-INF/lib**. Visualize it as:

~~~text
Running from IDE / bootRun:
  build/classes/java/main/ + build/resources/main/
      + ~/.gradle/caches/.../jackson-....jar
      + ~/.gradle/caches/.../spring-....jar
      -> Application.main

Running executable JAR:
  loader-demo.jar
      + BOOT-INF/classes/
      + BOOT-INF/lib/jackson-....jar
      + BOOT-INF/lib/spring-....jar
      -> Boot JarLauncher -> Application.main
~~~

Note that cache paths may vary across machines and build tools. Both startup paths may lead to SpringApplication.run, but their **classpath layout** and resource URLs are not completely identical.

This is why some bugs only appear after packaging: a library uses **File** instead of a stream/resource API, or hardcodes IDE-style classpath paths. You should run a smoke test with **java -jar on the actual artifact** before releasing.

## 15. JarLauncher, WarLauncher, PropertiesLauncher: When to Choose Which?

### 15.1. JarLauncher

The common format with Gradle **bootJar** or Maven **spring-boot:repackage**:

~~~text
BOOT-INF/classes/
BOOT-INF/lib/
~~~

The launcher reads the archive's classpath according to this layout and uses **Start-Class** in the manifest. For a typical HTTP service application, this is the appropriate default choice.

### 15.2. WarLauncher

The common executable WAR format:

~~~text
WEB-INF/classes/
WEB-INF/lib/
WEB-INF/lib-provided/
~~~

**WEB-INF/lib-provided/** contains dependencies needed when running the WAR in executable/embedded mode that should not be exposed to a traditional servlet container as ordinary application libraries. This format helps support WAR models with special requirements. Do not convert a JAR to a WAR just by changing the file extension: build plugins, packaging, and application initialization must match.

### 15.3. PropertiesLauncher

**PropertiesLauncher** allows partial control over additional classpath locations outside the standard layout; it can accept values such as **loader.path**, **LOADER_PATH**, or **loader.properties**. Conceptual configuration example:

~~~properties
loader.path=external-lib/
~~~

This is a **loader configuration snippet**, not a line to put in **application.properties** expecting Spring Boot to switch launchers automatically. It only takes effect when the archive is configured with a **Main-Class** matching PropertiesLauncher and the loader receives the config from an appropriate source. This model allows supplying some JARs/configs externally, but also makes deployment depend on external files that must be managed separately.

Most new Spring Boot applications **do not need PropertiesLauncher**; using the default JarLauncher is simpler and more consistent. Only use a specialized launcher when you understand why classpath expansion is needed.

## 16. BOOT-INF/classpath.idx and layers.idx Do Not Replace the Loader's Role

### 16.1. Classpath Index

**BOOT-INF/classpath.idx** can be generated by the Maven/Gradle plugin to record **the order in which nested JARs** are added to the classpath. Syntax example:

~~~text
- "BOOT-INF/lib/first.jar"
- "BOOT-INF/lib/second.jar"
~~~

This is **illustrative syntax** only, not real JAR names. The Spring Boot specification notes that **classpath.idx** is used by Boot when the archive is run with **java -jar**, whereas when running in an IDE, **spring-boot:run**, or **bootRun**, it is not used this way.

Classpath order matters if the same resource/class name appears in multiple sources; however, the index **does not turn a regular JAR into an executable Boot JAR**. The launcher and nested-JAR support are still required. Do not manually edit the order of classpath.idx to mask dependency conflicts; inspect the dependency graph first.

### 16.2. Layers Index

**BOOT-INF/layers.idx** describes how to split the archive into layers when building Docker/OCI images, for example separating stable dependencies from application code or snapshot dependencies. It is **not a mandatory list of classes for the JVM to read** and **does not create a class loader**.

An application can start with JarLauncher even without layers.idx. Conversely, manually creating layers.idx in a JAR without Boot Loader **does not** make nested JARs supported by the Java launcher.

## 17. When Is It Necessary to Unpack a Nested JAR?

Most Java libraries can be accessed directly by Boot Loader while inside **BOOT-INF/lib**. However, some libraries **explicitly require a real JAR file path on the filesystem**, or have their own incompatible ZIP/nested loading mechanism.

Spring Boot Maven/Gradle packaging supports marking specific dependencies with **requiresUnpack** so they are extracted to a temporary directory when the executable archive runs. In Boot's documentation, **JRuby** is an example of a library with special requirements.

**Illustrative XML example for the Maven plugin** (placed inside **configuration** of spring-boot-maven-plugin in a real POM):

~~~xml
<configuration>
    <requiresUnpack>
        <dependency>
            <groupId>org.jruby</groupId>
            <artifactId>jruby-complete</artifactId>
        </dependency>
    </requiresUnpack>
</configuration>
~~~

This is not required for the Jackson example in Section 8. Do not add the JRuby dependency to a project just to "enable unpack". Only configure it when using that library and the issue has been verified.

Important constraints:
- Must have permission to create/read files in an appropriate **java.io.tmpdir**.
- Do not delete unpacked files while the application is still using them.
- Do not assume the temporary directory always has sufficient space and permissions on restricted containers/servers.
- Do not unpack every dependency just to fix an undiagnosed error.

## 18. Comparing Spring Boot Nested JAR with Shaded/Uber JAR and External Libraries

| Packaging approach | Where do dependencies live? | How does the JVM find classes? | Pros/cons |
| --- | --- | --- | --- |
| **Plain/thin JAR + external lib** | Many separate JARs on the filesystem | java -cp, or valid manifest Class-Path | Easy to understand by standard Java rules, but requires managing many files |
| **Shaded/uber JAR** | Classes/resources from libraries are merged "flat" into one archive | Standard classloader reads entries at the root | Single file, but risks resource/metadata collisions and obscures original libraries |
| **Spring Boot executable nested JAR** | App classes in BOOT-INF/classes; intact dependency JARs in BOOT-INF/lib | Boot Loader + nested JAR class loader | Single file, preserves library boundaries; requires proper launcher/layout |
| **Exploded Spring Boot application** | Archive is extracted into dirs/JAR files | Can run launcher or a properly constructed custom classpath | Useful for container layers; requires exact file placement and command |

Therefore, **Boot Loader is not the only way to run an app containing dependencies**. It is the solution Spring Boot chose for **its nested JAR-in-JAR distribution format**. Maven Shade Plugin or Gradle Shadow plugin can produce shaded JARs under a different architecture; do not blindly replace bootJar/repackage with a shaded JAR without evaluating resource merging, service metadata, duplicates, and launcher behavior.

A valid plain JAR **is not necessarily runnable with java -jar**; it must have an appropriate Main-Class and be able to locate dependencies. A valid Spring Boot executable JAR additionally requires the proper classpath/layout for the loader.

## 19. Technical Limitations You Must Know

### 19.1. Native Libraries/JNI

A Java dependency may contain native **.so**, **.dll**, **.dylib** files or JNI code. The JVM usually needs native libraries to be loaded via a **corresponding file path**; do not assume Java code inside a nested JAR directly supports all forms of native loading like an unpacked JAR. When encountering **UnsatisfiedLinkError**, check CPU architecture, operating system, native library loading permissions, and the extraction process supported by the library/framework.

### 19.2. ClassLoader.getSystemClassLoader() Does Not See All Nested Dependencies

When a library looks up classes via the system class loader, it may fail even if the class exists in **BOOT-INF/lib**. Check whether **TCCL**, the Spring Resource API, or appropriate SPI/loader APIs can be used. Do not fix this by randomly stuffing classes into the root JAR.

### 19.3. Each JAR Entry Has Specific Compression Requirements

With Boot, **nested JAR ZipEntry entries must be STORED** so offset-seeking is supported per the specification. Using a zip tool to change compression or archive metadata may prevent the loader from reading the contents. It is best to build the artifact using the official Maven/Gradle Spring Boot plugin.

### 19.4. Classpath Differences Can Expose Conflicts

A build with multiple versions of the same library, duplicate classes, or service descriptors may behave differently when classpath order changes. **classpath.idx** can help keep the order close to the build system, but it is not a tool for fixing the dependency graph. Resolve conflicts with **mvn dependency:tree** or **gradlew dependencies/dependencyInsight**, and pin tested managed versions.

### 19.5. Boot Loader Does Not Automatically Protect Artifacts from Attacks

The nested JAR layout is a **deployment format**, not encryption, sandboxing, or library security control. Anyone with the JAR can inspect libraries and application classes using archive tools; protect secrets via runtime configuration and apply SBOM, vulnerability scanning, and signing/verification per project policy.

## 20. Diagnostic Table by Startup Layer

| Symptom | Layer to check | Common cause | Resolution |
| --- | --- | --- | --- |
| **no main manifest attribute** | java -jar/manifest | Running a plain JAR without Main-Class | Identify the proper bootJar/repackaged JAR; check manifest |
| **Could not find or load main class ...JarLauncher** | Manifest/Boot Loader | Main-Class points to wrong launcher for version or launcher classes missing | Inspect manifest and jar tf; use plugin matching Boot branch |
| **ClassNotFoundException: com.example....Application** | Start-Class/app classes | Wrong main class FQCN, missing compiled class, app class not in BOOT-INF/classes | Check Start-Class, jar tf, and mainClass configuration |
| **NoClassDefFoundError: ...jackson...** | Nested dependencies | JAR excluded from runtime classpath, archive missing BOOT-INF/lib, or loader failed to read | Check jar tf and Maven/Gradle runtime deps |
| **ClassNotFoundException when using -cp boot.jar app.Main** | Java standard classpath | Class is in BOOT-INF/classes, not root JAR | Use java -jar on the boot archive |
| **Nested JAR file cannot be opened / cannot seek** | Nested JAR format | Outer JAR was improperly repacked, entry compression not STORED, or archive corrupted | Rebuild with Boot plugin; check recompression tools |
| **UnsupportedClassVersionError** | JVM bytecode compatibility | Classes built with a newer Java than the deployment JVM | Align compile/runtime JDK and Spring Boot requirements |
| **UnsatisfiedLinkError** | Native library loading | JNI/native libs not extracted or wrong platform | Check native library and unpack mechanism |
| **java -jar works but IDE behaves differently** | Classpath/resources/profile | IDE bootRun uses external JARs and different source paths | Compare properties, classpath, active profiles, resource URLs |
| **jar tf shows library but code still throws ClassNotFound** | Class loader/SPIs | Library uses system loader or custom resource resolution | TCCL, supported APIs, and Boot-compatible libraries |
| **No BOOT-INF/lib** | Packaging | Accidentally running plain JAR or dependencies excluded | Check bootJar/repackage task and output artifact |
| **Class-Path missing in manifest** | Misunderstanding Boot format | Boot does not need manifest Class-Path like external libs | Inspect BOOT-INF/lib and JarLauncher |
| **Port already in use** | Spring runtime | Boot Loader already finished; web server cannot bind port | Change server.port or stop process holding the port |
| **BeanCreationException** | Spring ApplicationContext | DI/config error after classes are loaded | Read nested cause and config; do not assume loader bug |

Read logs in sequence: **Java launcher → Boot launcher → ClassLoader → application main → Spring context → web server**. If you already see the Spring banner and a bean error, Boot Loader has usually completed its initial startup role; do not blame everything on nested JARs.

## 21. Verifying Whether the Loader Was Packaged Properly

A practical pre-deploy checklist:

1. **Know the exact file to run:** in Maven usually **target/<artifactId>-<version>.jar**, in Gradle **build/libs/<project>-<version>.jar** (names may be customized).
2. **Verify boot packaging:** Maven has spring-boot-maven-plugin and appropriate repackage execution; Gradle executes bootJar.
3. **Check archive entries:** contains **BOOT-INF/classes**, **BOOT-INF/lib**, and loader classes.
4. **Read the manifest:** **Main-Class** points to the launcher, **Start-Class** points to the application main class.
5. **Check runtime dependencies:** required Jackson/Spring/libs are actually in BOOT-INF/lib; test-only dependencies do not belong there.
6. **Run java -jar:** use a JVM compatible with the Spring Boot version/class files; observe startup logs.
7. **Call a smoke endpoint/batch job:** verify the application can actually use nested dependencies, not just print the banner.
8. **Do not modify the JAR with uncontrolled zip tools** after building; if re-signing/repackaging is required, preserve Boot Loader compatibility.
9. **Do not use -cp boot.jar app.Main** in place of java -jar; if an exploded classpath is desired, design for it explicitly.
10. **Distinguish class loading errors from Spring startup errors**, using the right logs/tools for each layer.

### Separately Checking the Dependency Graph Before Packaging

Maven:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Having a dependency in the runtime graph **is necessary**, but does not by itself prove it ended up in **the actual deployed executable archive** if packaging is customized. Conversely, seeing a JAR in BOOT-INF/lib does not by itself prove app code can call every API from it if the class loader, version compatibility, or runtime config is wrong.

## 22. Self-Assessment Questions

**Question 1.** Why can Java run **java -cp main.jar:lib.jar Main** yet not automatically run a **lib.jar** located inside **main.jar/BOOT-INF/lib**?

**Answer:** In the first classpath command, main.jar and lib.jar are two separate files declared as classpath entries. In the nested case, lib.jar is just a ZIP entry inside the outer JAR; standard classpath/JAR loading does not recursively look up JAR entries and load classes from them.

**Question 2.** In a Spring Boot executable JAR, how do **Main-Class** and **Start-Class** differ?

**Answer:** **Main-Class** usually points to Boot's **JarLauncher** for Java to invoke first. **Start-Class** points to the main application class invoked by Boot Loader after setting up a class loader capable of loading nested dependencies.

**Question 3.** Does the JVM really need Spring Boot Loader to run any application that uses Jackson?

**Answer:** No. If the Jackson JAR is external and declared directly on the Java classpath, the JVM can load its classes via standard mechanisms. Boot Loader is needed when using **Spring Boot's nested JAR-in-JAR archive layout** to run as a single file with java -jar.

**Question 4.** A JAR contains **BOOT-INF/lib/jackson-databind.jar**; why doesn't **jar tf** print each Jackson class?

**Answer:** **jar tf** lists entries of the outer JAR, so it sees a single entry named after the nested JAR. To view entries inside the inner JAR, you need to read/open another archive layer or use a tool aware of the nested layout.

**Question 5.** Why might **ClassLoader.getSystemClassLoader()** fail while **Thread.currentThread().getContextClassLoader()** finds the same class?

**Answer:** Boot Launcher creates or configures a class loader that sees **BOOT-INF/classes** and **BOOT-INF/lib**. The system loader does not automatically see nested libs, whereas the TCCL set on the thread by the application launcher can see them.

**Question 6.** Why is **ZipEntry.STORED** important for nested JARs?

**Answer:** So Spring Boot Loader can seek by physical byte offsets within the outer JAR when reading entries of the inner JAR without unpacking the entire outer archive. The nested JAR inside can still contain individually compressed ZIP entries.

**Question 7.** Is **BOOT-INF/layers.idx** the reason the JVM finds Jackson?

**Answer:** No. layers.idx is layering metadata for image/build tooling. The loader and nested-JAR class loader are responsible for finding classes in nested JARs; classpath.idx (if present) assists with JAR ordering under java -jar.

**Question 8.** Why might **./gradlew bootRun** succeed while **java -jar build/libs/app.jar** fails?

**Answer:** The two launch modes use different classpaths/layouts. bootRun uses classes/resources and separate dependency JARs on the filesystem; the executable JAR uses Boot Loader with nested archives. You need to inspect the manifest, BOOT-INF/lib, packaging config, classloader, and application resource APIs.

**Question 9.** If jar tf shows all nested JARs, can we skip integration testing?

**Answer:** No. Having the archives in the right place is packaging evidence, not proof that versions are compatible, bean wiring is correct, the web server starts, or business logic works. Tests and a smoke test on the real artifact are still required.

## 23. Conclusion: "The JVM Needs Boot Loader" Must Be Understood in Context

**In the context of Spring Boot's executable JAR with nested JARs**, the Java launcher can load Boot Loader at the archive root, but **does not automatically know how to open each JAR inside BOOT-INF/lib as a classpath source**. Spring Boot Loader sets up the appropriate classpath and class loader for application classes and runtime libraries, then invokes **Start-Class.main()**.

~~~text
java -jar app.jar
    -> manifest Main-Class
    -> org.springframework.boot.loader.launch.JarLauncher
    -> BOOT-INF/classes + BOOT-INF/lib/*.jar
    -> nested-JAR class loader
    -> manifest Start-Class
    -> Application.main()
    -> SpringApplication.run()
~~~

Remember that **Spring Boot Loader solves a packaging-format problem** rather than replacing the JVM or Spring Framework. If switching to a plain JAR with external libs, a shaded JAR, or an exploded deployment, classpath configuration and launcher setup will differ. To deploy with confidence, verify **the manifest, nested entries, and an actual java -jar run**.

## 24. Official References

- Spring Boot 3.5 — Executable JAR Format: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/index.html
- Spring Boot 3.5 — Nested JARs: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html
- Spring Boot 3.5 — Spring Boot's NestedJarFile Class: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/jarfile-class.html
- Spring Boot 3.5 — Launching Executable Jars: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html
- Spring Boot 3.5 — Executable JAR Restrictions: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/restrictions.html
- Spring Boot 3.5 — Create Executable JAR & requiresUnpack: https://docs.spring.io/spring-boot/3.5/how-to/build.html
- Spring Boot 3.5 — Maven Plugin Packaging: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Gradle Plugin Packaging: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Oracle Java — Java launcher command (-jar and classpath): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java — JAR File Specification: https://docs.oracle.com/javase/8/docs/technotes/guides/jar/jar.html
