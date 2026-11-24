# Listing and Extracting Layers with jarmode tools Mode

## 1. Why Does a Spring Boot JAR Need to Be Split into Layers?

When a Spring Boot application is built into an **executable JAR**, Maven **`spring-boot:repackage`** or Gradle **`bootJar`** typically puts application classes/resources in **`BOOT-INF/classes`**, dependencies in **`BOOT-INF/lib`**, and adds the Spring Boot Loader. Users can run the single file via:

~~~bash
java -jar target/layer-lab-1.0.0.jar
~~~

Single-file distribution is very convenient. However, if you put the whole large JAR into a Docker image, every time you modify a Java class and rebuild the JAR, the image layer holding that JAR changes, forcing re-transfer and re-storage of a large amount of data even though most third-party dependencies did not change.

Spring Boot supports **layered JAR/WAR** archives: the archive still runs as an executable archive, while carrying metadata identifying which files belong to which layer. With Spring Boot 3.5, the **`spring-boot-jarmode-tools`** tool bundled in the archive can:

- **`list-layers`** — list the layer names in the archive.
- **`extract`** — unpack application/dependencies into a layout suited for running from a directory.
- **`extract --layers`** — extract contents **by individual layer**, convenient for creating separate Docker image layers.
- **`help`** — look up options for each command.

Core commands:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar list-layers
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

**Key takeaway:** **`jarmode=tools`** runs the packaging/extraction tool in Java; it **does not execute the application's `main()`** and **does not build a Docker image by itself**. It reads the built archive and lists or writes files onto the filesystem for use in your next deployment/containerization step.

This lesson belongs to the parent topic **Layered Packaging** and explains the mechanics, exact commands, expected results, runnable Java 17 Maven/Gradle examples, multi-stage Dockerfiles, different extraction modes, and troubleshooting.

## 2. Background: A Layered Archive Is Still an Executable Archive

A Spring Boot 3.5 layered JAR has a representative structure:

~~~text
layer-lab-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── ... Boot Loader classes ...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/layerlab/LayerLabApplication.class
    │   ├── com/example/layerlab/LayerController.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-....jar
    │   ├── spring-web-....jar
    │   ├── spring-boot-jarmode-tools-....jar
    │   └── ...
    ├── classpath.idx    (may be present)
    └── layers.idx       (default when layering is enabled)
~~~

Dependency names and detailed paths are illustrative; actual contents must be inspected after building. **`layers.idx`** is metadata mapping archive components to layers and describing layer order, **not a directory containing copies of classes**.

**`spring-boot-jarmode-tools`** is a tool JAR added by the build plugin to the runtime archive by default when building a layered archive. Thanks to it, the Boot Loader can detect **`jarmode=tools`** and switch to executing tool commands before invoking the application's main method.

Distinguish three things:

| Component | Role | Is it a Docker image layer? |
| --- | --- | --- |
| **BOOT-INF/layers.idx** | Layer index file inside the Boot JAR | No |
| **Spring Boot layers** | Logical groups of entries by stability | Not yet Docker layers |
| **Docker/OCI image layers** | Filesystem layers created by the image builder from a Dockerfile/build process | Yes |

**`list-layers`** only reports the logical groups inside the archive. **`extract --layers`** creates directories representing those groups. To turn them into OCI layers, you still have to write a Dockerfile with separate **`COPY`** instructions and build the image.

## 3. Spring Boot 3.5's Four Default Layers

Spring Boot Maven and Gradle plugins typically use four layers:

| Layer | Typical contents | Volatility |
| --- | --- | --- |
| **dependencies** | Third-party dependencies without **`SNAPSHOT`** in their version | Rarely changes when editing only application code |
| **spring-boot-loader** | Spring Boot Loader classes/bootstrap | Usually changes only when upgrading Boot/plugin |
| **snapshot-dependencies** | Dependencies with **`SNAPSHOT`** in their version | May change frequently |
| **application** | Application classes/resources and local project/module dependencies | Typically changes on every application edit |

Default order:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

This order puts components with a lower probability of change first to leverage Docker layer caching. If you edit a controller without changing Spring/Jackson versions, the dependencies and loader layers can still reuse old image layers while only the application layer is updated.

**Do not interpret** layer names as meaning every file in **`BOOT-INF/lib`** always belongs to **`dependencies`**. A **`SNAPSHOT`** dependency can go into **`snapshot-dependencies`**; a Maven reactor module or Gradle project dependency belonging to the current build usually goes into **`application`**. Actual rules also depend on the build tool and any custom layer configuration file.

**Not every layer is required to have substantial files.** A project with no SNAPSHOT dependencies may have an empty or nearly empty **`snapshot-dependencies`** layer. **`list-layers`** may still list the layer name declared in the index.

### 3.1. Why Does Layer Order Matter?

In the Docker/OCI filesystem layer model, changes in one layer can force upper layers to rebuild or affect cache reuse. To optimize, stable groups like **`dependencies`** are normally placed first, while the most frequently changing application part goes last.

However, **layering does not guarantee faster image builds in every scenario**. Effectiveness depends on dependency sizes, cache hit rates, remote registries, the Docker builder, build context, and whether you copy layers in stability order. Measure before and after to draw conclusions for a specific CI pipeline.

## 4. Prerequisites for Using jarmode=tools

Before running commands, ensure you have:

1. **A compatible JDK/JRE** for Spring Boot and the application bytecode. Examples below use Java 17.
2. **A Spring Boot executable JAR/WAR** properly built via Maven `repackage` or Gradle `bootJar`/`bootWar`; do not use a plain JAR by mistake.
3. Valid **`layers.idx`** metadata if listing/extracting by layers.
4. **`spring-boot-jarmode-tools`** present in the archive; do not configure **`includeTools=false`**.
5. **No embedded launch script prefix** from a fully executable Spring Boot JAR: official docs explicitly state tools mode **does not work** with archives of that type.
6. Read permission on the JAR and write permission on the **destination directory** when extracting.
7. A **new/empty destination** or explicit cleanup when a destination already contains files, avoiding mixing old and new outputs.

Two flags that are easily confused:

~~~text
-Djarmode=tools  -> JVM system property, must be passed BEFORE -jar
-jar app.jar     -> Spring Boot archive containing Boot Loader and tools
list-layers      -> subcommand understood by tools mode
extract          -> subcommand understood by tools mode
--layers         -> chooses extraction into layers
--destination    -> location to place extracted files
~~~

**Correct:**

~~~bash
java -Djarmode=tools -jar app.jar list-layers
~~~

**Not equivalent:**

~~~bash
java -jar app.jar -Djarmode=tools list-layers
~~~

In the second command, **`-Djarmode=tools`** appears after the archive name, so it is typically passed merely as an application argument; the JVM does not receive it as a system property when selecting JarMode. The app may start up instead of printing the layer list. Always put **`-Djarmode=tools`** before **`-jar`**.

## 5. Viewing Help Directly from the Artifact

After a successful build, the simplest command to see which subcommands the JAR supports is:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar
~~~

In Spring Boot 3.5, usage output typically looks like:

~~~text
Usage:
  java -Djarmode=tools -jar my-app.jar

Available commands:
  extract      Extract the contents from the jar
  list-layers  List layers from the jar that can be extracted
  help         Help about any command
~~~

The JAR name printed in usage may be your artifact or a placeholder name; **do not compare exact bytes of the usage line** to decide whether the tool works. The three subcommands **`extract`**, **`list-layers`**, and **`help`** are what need confirmation.

View help for the `extract` command:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar help extract
~~~

Some options supported by Spring Boot tools:

| Option | Meaning |
| --- | --- |
| **--layers** | Extract contents by layer instead of only a normal layout; can specify layers to extract per tools version syntax |
| **--destination** | Target directory for extracted contents; if omitted, defaults based on archive name |
| **--libraries** | Libs directory name when using a layout without extracting the launcher; defaults to **lib/** |
| **--application-filename** | Application JAR name in the applicable layout |
| **--launcher** | Requests extracting the Spring Boot launcher in supported modes |
| **--force** | Allows extracting into a non-empty location per tools semantics |

**Do not combine options arbitrarily.** Some options take effect only when **`--launcher`** is not enabled. Layer selection syntax or default values can vary between Boot versions, so **`help extract` from the actual artifact** is the fastest reference.

In particular, **`--force`** is not a way to “fix” a dirty directory in CI: it is better to create a fresh output directory for every build so stale libraries or files from previous artifacts are not kept.

## 6. Listing Layers with list-layers

### 6.1. Command with a Maven JAR

In a project using the Spring Boot Maven Plugin:

~~~bash
./mvnw clean verify
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar list-layers
~~~

In a Spring Boot layered JAR example using the four default layers, output typically looks like:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

This is the **expected output under default definitions**, not a log captured from a live run performed in this article. If the project has a custom **`layers.xml`**, names/order can differ. Read the output directly instead of hardcoding assumptions into a pipeline when teams change layer configurations.

### 6.2. Command with a Gradle JAR

If the project uses Gradle and default `bootJar` output:

~~~bash
./gradlew clean test bootJar
java -Djarmode=tools -jar build/libs/layer-lab-1.0.0.jar list-layers
~~~

Pick **only one build tool**. Do not run Maven and look for the artifact in `build/libs`, or run Gradle and look for the file in `target`. Filenames can change depending on classifiers, `archiveBaseName`, or custom `bootJar`/`repackage` configurations.

### 6.3. list-layers Is Not list-jar-entries

**`list-layers`** prints **layer names**, not every file in each layer. To inspect entries inside the original executable JAR, use:

~~~bash
jar tf target/layer-lab-1.0.0.jar
~~~

Filtering examples on Linux/macOS:

~~~bash
jar tf target/layer-lab-1.0.0.jar | grep 'BOOT-INF/layers.idx'
jar tf target/layer-lab-1.0.0.jar | grep 'spring-boot-jarmode-tools'
~~~

On PowerShell:

~~~powershell
jar tf .\target\layer-lab-1.0.0.jar |
    Select-String 'BOOT-INF/layers.idx|spring-boot-jarmode-tools'
~~~

**`jar tf`** lists archive entries, whereas **`list-layers`** reads layer metadata. The two operations complement each other rather than replacing one another.

## 7. Extracting by Layer with extract --layers

With the Maven artifact in our example:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

Meaning:
- **`java`** starts the Boot Loader/JarMode Tools.
- **`-Djarmode=tools`** selects tools mode.
- **`extract`** performs archive extraction.
- **`--layers`** creates directories grouped by layer rather than a single merged layout.
- **`--destination extracted`** puts output under the **`extracted`** directory relative to the current working directory.

This command matches the official Spring Boot 3.5 Dockerfile example. **There is no need to run `unzip` and manually sort JARs**. Spring Boot tools use the layer index to determine each layer's contents.

### 7.1. Conceptual Output Structure

After successful extraction, you may see:

~~~text
extracted/
├── dependencies/
│   └── ... contents belonging to dependencies ...
├── spring-boot-loader/
│   └── ... contents belonging to spring-boot-loader ...
├── snapshot-dependencies/
│   └── ... contents belonging to snapshot-dependencies ...
└── application/
    └── ... contents belonging to application ...
~~~

**This is a directory grouping diagram**, not a complete file list. Extracted nested dependencies are usually arranged under **`lib/`** in the efficient runtime layout; the application portion is packaged as a small **`application.jar`** with a manifest referencing libraries. Exact directory contents also depend on the Spring Boot version, custom layers, JAR/WAR type, and options.

An important rule: **do not run `java -jar extracted/application/application.jar` directly and expect it to see all libraries**. In container guides, all four layer directories are **copied and merged into the same runtime working directory**, at which point files in **`lib/`** and **`application.jar`** resolve on the proper paths/classpath.

### 7.2. Commands to Inspect After Extraction

Linux/macOS:

~~~bash
find extracted -maxdepth 2 -type d
find extracted -type f | head -n 30
~~~

If you have **`tree`** installed, you can run:

~~~bash
tree -L 3 extracted
~~~

These commands only show structure without running the application. In CI, it is better to check layer lists and key files rather than relying on hardcoded JAR counts or versions, as dependency versions change.

Windows PowerShell:

~~~powershell
Get-ChildItem .\extracted -Directory
Get-ChildItem .\extracted -Recurse -File |
    Select-Object -First 30 FullName
~~~

When running repeatedly, use a **different destination for each build** or clean specifically the output directory created by the process; avoid mixing two library versions and concluding the current artifact contains files that do not belong to it.

### 7.3. Is --destination Required?

No. **`extract`** has a default directory derived from the JAR name. However, using an explicit name like **`extracted`** makes scripts and Dockerfiles easier to read and control.

**Never use an arbitrary absolute destination on a production machine** without checking ownership/permissions. Extraction writes files to the filesystem; perform it in a build stage or an isolated directory with appropriate permissions.

## 8. How Does extract Without --layers Differ?

This is the easiest point to confuse in modern jarmode tools.

**Mode A — default extract**:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar extract
~~~

Per Spring Boot 3.5 documentation, tools create an **efficient deployment layout**: libraries are placed into a **`lib/`** directory alongside a small application JAR containing application classes and a manifest referencing the libraries. The default destination typically matches the archive name without its extension, for example:

~~~text
layer-lab-1.0.0/
├── lib/
│   ├── ... dependencies ...
│   └── ...
└── layer-lab-1.0.0.jar
~~~

The diagram above illustrates a representative layout. To launch this layout as documented:

~~~bash
java -jar layer-lab-1.0.0/layer-lab-1.0.0.jar
~~~

**Mode B — extract --layers**:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

Tools split the same components into **`dependencies`**, **`spring-boot-loader`**, **`snapshot-dependencies`**, and **`application`** directories so each can be **`COPY`ed separately** into an OCI image. Once combined, the result still yields the proper runtime layout (libraries and application JAR).

| Criterion | **extract** | **extract --layers** |
| --- | --- | --- |
| Primary goal | Run from exploded/efficient layout | Separate components by layer for Docker/OCI caching |
| Output structure | One app directory with `lib/` and thin JAR | Multiple folders matching layer names |
| Need to merge folders before running? | No, if layout is complete and paths match | Yes, in the official Dockerfile example |
| Creates Docker image immediately? | No | No |
| Runs `SpringApplication.main()`? | No | No |
| Right tool to inspect options | `help extract` | `help extract` |

**Do not equate `jarmode=tools` with the legacy `jarmode=layertools`.** Both deal with layered archives, yet options, output layouts, and startup commands changed across versions.

## 9. Why Does the New Extraction Produce a Small application.jar?

Spring Boot 3.5 recommends a deployment layout where nested libraries are extracted as external files to reduce part of the JAR-in-JAR reading overhead at startup. **`extract`** produces a thin application JAR with metadata/classpath configured to use files in **`lib/`**.

When following the official Dockerfile, after merging each layer via `COPY`:

~~~text
/application/
├── application.jar   (JAR containing the application and manifest referencing lib)
├── lib/
│   └── multiple runtime dependency JAR files
└── ... supporting files per layout ...
~~~

Exact files depend on the build and Spring Boot plugin. The startup command for **this extracted layout** is typically:

~~~bash
java -jar application.jar
~~~

**Do not treat the extracted `application.jar` as the same binary as the original uber JAR.** The uber JAR holds all nested dependencies; the new JAR runs from the extracted layout pointing to external libraries. Copying only `application.jar` without `lib/` and required supporting components can trigger **`ClassNotFoundException`/`NoClassDefFoundError`**.

According to Spring Boot 3.5 documentation, an exploded layout can improve startup efficiency and facilitate **CDS/AOT caches**, though **you should not promise** a fixed speedup percentage. Once startup completes, do not expect runtime request handling speed to differ automatically just from extracting the JAR.

## 10. Runnable Example: Spring Boot 3.5 + Java 17

To practice **`list-layers`** and **`extract --layers`** hands-on, create a simple Spring Boot HTTP service. The example uses **Java 17**, **Spring Boot 3.5.16**, and JUnit 5. This is a specific combination for the lesson; new projects should select a supported Spring Boot branch per organizational policy.

**Use either Maven or Gradle**, not two tools managing the same artifact and mixing up outputs.

### 10.1. Project Structure

~~~text
layer-lab/
├── pom.xml                         (if using Maven)
│   or
├── build.gradle                    (if using Gradle)
├── settings.gradle                 (if using Gradle)
├── mvnw / mvnw.cmd / .mvn/wrapper/...       (Maven Wrapper)
├── gradlew / gradlew.bat / gradle/wrapper/... (Gradle Wrapper)
└── src/
    ├── main/
    │   ├── java/com/example/layerlab/
    │   │   ├── LayerLabApplication.java
    │   │   └── LayerController.java
    │   └── resources/application.properties
    └── test/java/com/example/layerlab/
        └── LayerControllerTest.java
~~~

Wrapper scripts/metadata must be generated via Spring Initializr or the respective Wrapper tool. Creating only a POM or `build.gradle` will not automatically generate **`./mvnw`** or **`./gradlew`**.

### 10.2. Main Class

File **`src/main/java/com/example/layerlab/LayerLabApplication.java`**:

~~~java
package com.example.layerlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LayerLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayerLabApplication.class, args);
    }
}
~~~

**Jarmode tools** intercepts via the Boot Loader before calling the class above; when running **`list-layers`/`extract`**, **`LayerLabApplication.main()` is not invoked**. This ensures extraction does not require database connections or starting an HTTP server.

### 10.3. Runtime Verification Endpoint

File **`src/main/java/com/example/layerlab/LayerController.java`**:

~~~java
package com.example.layerlab;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LayerController {

    @GetMapping("/layers")
    public String layers() {
        return "layer-extract-ok";
    }
}
~~~

When the Spring Boot application is actually serving HTTP, a **`GET /layers`** request returns the body:

~~~text
layer-extract-ok
~~~

Do not assume the endpoint is running merely because **`list-layers`** succeeded; tools mode does not launch a web server.

### 10.4. application.properties

File **`src/main/resources/application.properties`**:

~~~properties
spring.application.name=layer-lab
server.port=8080
~~~

If port 8080 is occupied, launch Java with **`--server.port=9090`** and adjust the check URL accordingly. This is a Spring application option, not an option for **`tools extract`**.

### 10.5. HTTP Test with MockMvc

File **`src/test/java/com/example/layerlab/LayerControllerTest.java`**:

~~~java
package com.example.layerlab;

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
class LayerControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void layersEndpointWorks() throws Exception {
        mvc.perform(get("/layers"))
                .andExpect(status().isOk())
                .andExpect(content().string("layer-extract-ok"));
    }
}
~~~

The test verifies application code and Spring context initialization. **It does not verify the extraction layout** because Maven/Gradle tests run on the build classpath. You still need to run the artifact after extraction and call the live endpoint.

## 11. Building with Maven: Layers and jarmode Tools

### 11.1. Complete pom.xml

File **`pom.xml`**:

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
    <artifactId>layer-lab</artifactId>
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
                <configuration>
                    <layers>
                        <enabled>true</enabled>
                    </layers>
                    <includeTools>true</includeTools>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Explanation:
- **`spring-boot-starter-parent`** provides Maven plugin/dependency versions and configures **`repackage`**.
- **`spring-boot-maven-plugin`** builds the executable JAR containing the Boot Loader.
- **`layers.enabled=true`** ensures the layer index is created in the example, even though Spring Boot 3.5 enables layering by default.
- **`includeTools=true`** keeps **`spring-boot-jarmode-tools`** in the archive. In Boot 3.5, this is also the default.
- **`spring-boot-starter-web`** brings Spring MVC + embedded server and runtime dependencies into the archive.
- **`starter-test`** is for testing only; test classes do not go into the production Boot JAR.

**Do not add `executable=true`** to the Maven plugin in this example. Fully executable archives with an embedded launch script **are incompatible with tools mode** per Spring Boot 3.5 documentation.

If the project uses a corporate Maven parent instead of `starter-parent`, confirm that the **`spring-boot:repackage`** goal is bound to the lifecycle, the plugin version is valid, and the application main class is resolved. **Simply declaring `includeTools=true` without running `repackage` will not turn a plain JAR into a Boot JAR.**

### 11.2. Building and Listing Layers

Linux/macOS:

~~~bash
./mvnw --version
./mvnw clean verify
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar list-layers
~~~

Windows uses **`mvnw.cmd`** instead of **`./mvnw`**. Once Maven `clean verify` succeeds, the `repackage` plugin creates the archive in **`target/`** matching the artifact/version in the POM. If the POM specifies a classifier, custom `finalName`, or `outputDirectory`, use the actual path.

After `list-layers`, extract:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

The **`extracted`** directory is the output of this extraction; it is not a default Maven build directory. In CI, place it inside an isolated workspace to avoid leftovers from earlier builds.

### 11.3. Maven repackage vs. Plain Jar Plugin

With Maven, the task creating the plain JAR runs before **`spring-boot:repackage`**. If you use a **classifier** to retain both the plain JAR and executable JAR simultaneously, extract the **exact Boot executable artifact**. A plain JAR has no Boot Loader, no `BOOT-INF/layers.idx`, and no jarmode tools in Boot format.

Common errors when selecting the wrong file:
- **`no main manifest attribute`** or **`Could not find or load main class`**.
- Missing **`BOOT-INF/layers.idx`** when inspecting with **`jar tf`**.
- Missing **`spring-boot-jarmode-tools`** in the archive.
- Java launches the application instead of tools or reports jar mode unsupported.

Do not patch this by dropping a random tools library into a plain JAR; **rebuild in the proper format** with the Spring Boot Maven Plugin.

## 12. Building with Gradle: bootJar and Layered Archive

If choosing Gradle, use the same Java source code without the POM above.

### 12.1. settings.gradle

~~~groovy
rootProject.name = 'layer-lab'
~~~

### 12.2. build.gradle Groovy DSL

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

tasks.named('bootJar') {
    layered {
        enabled = true
    }
    includeTools = true
}
~~~

**`bootJar`** creates the executable Spring Boot archive. **`layered.enabled=true`** and **`includeTools=true`** are written explicitly for illustration; in Spring Boot Gradle Plugin 3.5, default behavior already includes layering and jar tools.

**`io.spring.dependency-management`** imports Spring Boot dependency versions so dependencies do not require explicit versions. If the project chooses native Gradle BOM support, declare **`platform(...)`** accordingly rather than simply removing the plugin and expecting versions to resolve on their own.

### 12.3. Gradle Operations

With a compatible Gradle Wrapper (for example Gradle 8.14 for Spring Boot 3.5):

~~~bash
./gradlew --version
./gradlew clean test bootJar
java -Djarmode=tools -jar build/libs/layer-lab-1.0.0.jar list-layers
java -Djarmode=tools -jar build/libs/layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

On Windows use **`gradlew.bat`**. The **Gradle `jar` task** can create a plain JAR, while **`bootJar`** creates the Boot executable JAR. Pick the right output and never confuse the **`plain`**-classified JAR with `bootJar` output.

### 12.4. Equivalent Kotlin DSL for Layered Config

In **`build.gradle.kts`** with the Spring Boot Plugin already applied, add:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    layered {
        enabled.set(true)
    }
    includeTools.set(true)
}
~~~

This is a **config snippet**, not a complete `build.gradle.kts` file; plugins/dependencies/toolchain must use corresponding Kotlin DSL syntax.

Do not nest **`includeTools`** inside the **`layered`** block using legacy Gradle 2.x syntax like **`includeLayerTools`**. In Boot 3.5, the `BootArchive` task exposes **`includeTools`** directly.

## 13. Multi-Stage Dockerfile: Each Spring Boot Layer Becomes an Image Layer

With a Maven artifact **`target/layer-lab-1.0.0.jar`** built and tested successfully, create **`Dockerfile`** at the project root:

~~~dockerfile
# Stage 1: only to extract layers; Maven is not needed in the image
FROM eclipse-temurin:17-jre AS extractor
WORKDIR /builder

COPY target/layer-lab-1.0.0.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

# Stage 2: runtime image containing extracted output
FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extractor /builder/extracted/dependencies/ ./
COPY --from=extractor /builder/extracted/spring-boot-loader/ ./
COPY --from=extractor /builder/extracted/snapshot-dependencies/ ./
COPY --from=extractor /builder/extracted/application/ ./

USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

This is a **runnable Dockerfile for the properly named Maven artifact**, assuming a Docker engine and compatible base image. Replace **`COPY target/...`** with **`COPY build/libs/layer-lab-1.0.0.jar application.jar`** if built with Gradle. For real deployments, pin image tags/digests per supply-chain security policy and select the exact JDK runtime.

### 13.1. Why Are There Two FROM Instructions?

- The **extractor stage** copies the **uber JAR**, runs jarmode tools, and creates layer directories.
- The **runtime stage** copies only the extracted output and Java runtime, **without needing to hold the original uber JAR as a separate file**.
- Each **`COPY`** instruction in the runtime stage forms an image filesystem layer that the Docker/OCI builder can cache and reuse.

At runtime, the command:

~~~bash
java -jar application.jar
~~~

starts the **small JAR generated by extraction**, not the original uber JAR sitting in the extractor stage. Dependencies live on the filesystem in the matching runtime layout. This differs from a single-line Dockerfile doing **`COPY app.jar` + `java -jar /app/app.jar`**.

### 13.2. Why COPY in That Order?

~~~text
dependencies            (stable, copied first)
spring-boot-loader      (changes when upgrading framework/plugin)
snapshot-dependencies   (may change frequently)
application             (changes when editing source, copied last)
~~~

If only a Java endpoint changes, the `application` layer changes while stable `dependencies` layers can be reused. If you upgrade the Spring Boot version or change a dependency, the dependency layer and possibly subsequent layers must rebuild. Actual savings depend on Docker caching and your live image registry.

### 13.3. Building and Running the Image

After a successful Maven build:

~~~bash
docker build -t layer-lab:local .
docker run --rm -p 8080:8080 layer-lab:local
~~~

From a second terminal:

~~~bash
curl http://localhost:8080/layers
~~~

Expected response body:

~~~text
layer-extract-ok
~~~

If port 8080 is already occupied on the host, use another Docker port mapping, such as **`-p 9090:8080`**, and call **`http://localhost:9090/layers`**.

**Do not treat a successful `docker build` as proof that the Spring Boot application runs and serves requests.** The **`docker run` + `curl`** step verifies the extracted layout has all required libraries, manifest, and permissions.

### 13.4. Why Not Set Tools Mode as ENTRYPOINT?

~~~dockerfile
ENTRYPOINT ["java", "-Djarmode=tools", "-jar", "application.jar"]
~~~

That is **not** a web service entrypoint: tools mode only runs tool operations and does not call `SpringApplication.main`. At runtime, after extracting/merging layers, use **`java -jar application.jar`** as shown in the Dockerfile above.

### 13.5. Note on .dockerignore

When running Docker builds in a repository with **`target/`** or **`build/libs/`**, do not write a **`.dockerignore`** that accidentally excludes the exact JAR the Dockerfile needs to **`COPY`**. Excluding **`target/`** from the build context by default leads to **`COPY failed`** or missing artifact errors.

At the same time, avoid sending sensitive files into the context such as **`.env`**, private keys, credentials, local build caches, logs, and temp directories. Include only required artifacts/source files. Managing the Docker build context is part of pipeline stability and security.

## 14. Inspecting Output After Docker Merges the Layers

After `COPY`, the effective layout typically contains:

~~~text
/application/
├── application.jar
├── lib/
│   ├── ... Spring + third-party libraries ...
│   └── ...
└── ... layout metadata/auxiliary files, if any ...
~~~

To check that the container holds the application JAR and libraries, you can run a shell inside the image if it includes a shell:

~~~bash
docker run --rm --entrypoint sh layer-lab:local -c 'ls -la /application; ls /application/lib | head'
~~~

This command is only for **inspecting the file layout**. If the base image is **distroless** with no shell, `sh` will not run; use a debug image or build inspection per your workflow. Never add a shell to a production runtime image solely for debugging if security policy forbids it.

**Important note:** the extracted layout has a **small `application.jar` and `lib/`**, not the **`BOOT-INF/lib`** of the original uber JAR. The primary check must be **`java -jar application.jar`** plus a Spring app smoke test, not demanding the runtime layout look identical to raw ZIP contents.

## 15. list-layers and layers.idx: Verifying from Metadata

The layer index in a Spring Boot executable JAR normally resides at:

~~~text
BOOT-INF/layers.idx
~~~

Example YAML-like entries:

~~~yaml
- "dependencies":
  - "BOOT-INF/lib/spring-core-..."
  - "BOOT-INF/lib/spring-context-..."
- "spring-boot-loader":
  - "org/springframework/boot/loader/"
- "snapshot-dependencies":
  - "BOOT-INF/lib/some-snapshot-..."
- "application":
  - "BOOT-INF/classes/"
~~~

This is **illustrative syntax**, not a literal `layers.idx` to paste into an archive. The actual file generated by the plugin has entries/paths matching your project's resolved dependencies.

**`list-layers`** is the official way to ask an archive which layer names it contains. **`layers.idx`** explains the file-to-layer mapping. Read both when investigating custom layer configs. Do not edit `layers.idx` inside the ZIP after building expecting Spring Boot tools and Docker caching to stay compatible; update Maven/Gradle configuration and rebuild.

### 15.1. Does layers.idx Make Java Class Loading Faster?

Not directly. The Spring Boot Loader handles class loading/nested-JAR access for executable archives. **`layers.idx`** primarily serves deployment grouping and how tools split the archive to optimize image distribution/caching. When running the original uber JAR directly with **`java -jar`**, having layer metadata does not automatically speed up runtime request handling.

### 15.2. classpath.idx Is Not layers.idx

**`BOOT-INF/classpath.idx`** (if present) records dependency order on the classpath when running the executable archive in Boot-supported ways. **`BOOT-INF/layers.idx`** records which layer each file belongs to for deployment splitting. They serve different goals and do not replace each other.

## 16. Jarmode tools vs. Legacy layertools: Why Internet Examples Differ

Online you may encounter legacy commands:

~~~bash
java -Djarmode=layertools -jar app.jar list
java -Djarmode=layertools -jar app.jar extract
~~~

That is the **old mechanism** using **`spring-boot-jarmode-layertools`**. Starting in Spring Boot 3.3, **`spring-boot-jarmode-tools`** and **`jarmode=tools`** are the replacement. Spring Boot 3.5 docs use:

~~~bash
java -Djarmode=tools -jar app.jar list-layers
java -Djarmode=tools -jar app.jar extract --layers --destination extracted
~~~

Key differences:

| Behavior | Legacy layertools | Modern tools (Boot 3.5) |
| --- | --- | --- |
| JarMode property | **layertools** | **tools** |
| List command | **list** in older versions | **list-layers** |
| Extract layers | **extract** with legacy layout | **extract --layers** with modern layout |
| Extract efficient layout without layer folders | Not aligned with modern tools | **extract** |
| Tool JAR | **spring-boot-jarmode-layertools** | **spring-boot-jarmode-tools** |

**Do not mix the CLIs of the two systems.** Copying a Boot 2.x/3.2 Dockerfile into a Boot 3.5 app can yield different directory structures and startup behavior. In Boot 4.x, deprecated mechanisms may be removed; consult docs and **`help`** matching the Boot branch your project actually builds against.

You do not need to memorize the old syntax to complete this lesson; the table simply helps diagnose commands copied from older blog posts.

## 17. When a Project Uses a Fully Executable Archive with a Launch Script

Spring Boot also offers a Maven option:

~~~xml
<configuration>
    <executable>true</executable>
</configuration>
~~~

or Gradle:

~~~groovy
tasks.named('bootJar') {
    launchScript()
}
~~~

Both options prepend a **Unix launch script prefix** to the archive so it runs directly on compatible OSes (**`./app.jar`**). **Spring Boot 3.5 Dockerfiles documentation explicitly states `jarmode=tools` cannot be used with fully executable archives that have a script prefix.**

If you need **`extract --layers`**:
- With Maven, **do not enable `executable=true`** on the artifact consumed by the extractor.
- With Gradle, **do not call `launchScript()`** on the `BootJar` used for extraction.
- If your organization needs both, produce **two distinct artifacts** with clear names/classifiers and test them separately.
- Never strip a shebang/ZIP prefix via uncontrolled binary edits and ship that file as a release artifact.

**Do not confuse fully executable archives with standard Spring Boot executable JARs.** A Boot JAR with `Main-Class`/`Start-Class` run via **`java -jar`** does not have an embedded shell prefix by default; that standard format is the right input for tools mode.

## 18. includeTools=false and layers.enabled=false Are Not the Same

With Spring Boot Maven Plugin 3.5, there are two ways to disable different features:

**A — Disable jar tools while still keeping layer metadata:**

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <includeTools>false</includeTools>
    </configuration>
</plugin>
~~~

**B — Disable layered archive metadata:**

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layers>
            <enabled>false</enabled>
        </layers>
    </configuration>
</plugin>
~~~

These snippets are only **plugin excerpts**, not complete `pom.xml` files. In Spring Boot **3.3+**, disabling layers is not a reliable way to exclude the tools JAR automatically—**`includeTools`** is the direct setting controlling whether the tools dependency is included.

In Gradle, the meaning is analogous:

~~~groovy
tasks.named('bootJar') {
    includeTools = false
}
~~~

and:

~~~groovy
tasks.named('bootJar') {
    layered {
        enabled = false
    }
}
~~~

**If you want to use `list-layers`/`extract --layers`, do not enable the disabling settings above.** Summary behavior table:

| Configuration | Archive has layer metadata? | Jarmode tools bundled? | Can run `list-layers`/`extract --layers`? |
| --- | --- | --- | --- |
| Default Boot 3.5 | Yes | Yes | **Yes** |
| `includeTools=false` | May still exist | No | **Cannot use tools mode from that archive** |
| `layers.enabled=false`, tools still present | No | May still exist | No layers to list or extract by layer |
| Both metadata and tools present, plus fully executable prefix | Yes | Yes | **Jarmode tools not supported with prefix** |

**Do not rush to edit Java code** when tools commands fail. First inspect POM/Gradle config, manifest, the chosen JAR file, and versions; sometimes you are running a plain JAR or a stale artifact.

## 19. Customizing Layers and the Impact on list-layers

In the Spring Boot Maven Plugin, a **`layers.xml`** file can change dependency/application grouping rules, add a **`company-dependencies`** layer, or alter **`layerOrder`**. Gradle `BootJar` also supports configuring layer rules. This is helpful when an organization's internal libraries change more frequently than third-party libraries.

Logical example:

~~~text
dependencies           -> stable third-party libraries
spring-boot-loader     -> boot loader
company-dependencies  -> internal com.example libraries
snapshot-dependencies -> SNAPSHOT builds
application            -> application source/resources
~~~

These are **custom layer name examples**, not present in the default configuration. After building an archive with that configuration:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar list-layers
~~~

will output the actually defined layers. If a Dockerfile only runs **`COPY`** on the four default names while the archive includes **`company-dependencies`**, the new layer is left out of the runtime image, potentially causing missing classes.

**Safety principle:** when modifying custom layer rules, update the Dockerfile or pipeline to match the real layer list and run a smoke test on the extracted artifact. Never hardcode a four-layer assumption across all team repositories.

For CI handling many Spring Boot applications, standardize layer policies or generate `COPY` instructions via a tested build workflow. Even then, any Dockerfile generation mechanism must ensure no layers are missed and build context/inputs remain protected.

## 20. Windows PowerShell: Listing and Extracting

**Java jarmode tools is Java code**, not a Unix shell script, so it runs on Windows whenever the artifact is a **standard Spring Boot executable JAR** with a compatible Java runtime.

In a Maven project:

~~~powershell
& .\mvnw.cmd clean verify
java -Djarmode=tools -jar .\target\layer-lab-1.0.0.jar list-layers
java -Djarmode=tools -jar .\target\layer-lab-1.0.0.jar help extract
java -Djarmode=tools -jar .\target\layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

If using Gradle:

~~~powershell
& .\gradlew.bat clean test bootJar
java -Djarmode=tools -jar .\build\libs\layer-lab-1.0.0.jar list-layers
java -Djarmode=tools -jar .\build\libs\layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

These are **two build alternatives**; you do not need to run both. After extracting:

~~~powershell
Get-ChildItem .\extracted -Directory
Get-ChildItem .\extracted -Recurse -File |
    Select-Object -First 20 FullName
~~~

Pay attention to the current working directory, paths containing spaces, and write permissions. In PowerShell, **`-Djarmode=tools`** is passed as a Java argument when placed right before **`-jar`**; do not use Linux shell **`MODE=...`** prefixes instead.

## 21. Practical Issues When Inspecting Extraction Output

### 21.1. Is an Empty Layer Directory an Error?

Not necessarily. If a project has no SNAPSHOT dependencies, the **`snapshot-dependencies`** layer may have minimal or no contents. Check whether `list-layers` prints that layer and verify the remaining layers contain all required libraries.

### 21.2. Why Is a JAR Visible in BOOT-INF/lib Yet Missing from the dependencies Layer?

A module belonging to the local reactor/project can be classified into **`application`** instead of **`dependencies`**. A SNAPSHOT dependency goes into **`snapshot-dependencies`**. With custom layers, dedicated rules may move components into a new layer. Do not assume a file is “missing” solely because it is not in the expected directory.

### 21.3. Why Is the New application.jar Smaller Than the Uber JAR?

Because runtime dependency JARs sit inside **`lib/`** outside the application JAR. **Do not delete `lib/`** after extraction and do not ship `application.jar` by itself unless you intentionally changed packaging/classpath accordingly.

### 21.4. Does extract Rebuild Java Classes?

No. **`extract`** operates on an already-built artifact. It does not invoke **`javac`**, the Maven compiler, annotation processors, or JUnit. If application source has errors or tests fail, fix them in the earlier build phase. Never use `extract` to bypass pipeline verification.

### 21.5. Can Everything Be Extracted into /tmp and Copied to a Server?

You can extract into a directory you control, provided you safeguard:
- read/write permissions of the CI user;
- disk space and filesystem quotas;
- artifact provenance from a trusted source;
- cleanup and ownership/permissions;
- isolation so outputs from different releases never mix.

Do not extract untrusted archives into a shared directory with elevated privileges. For production deployments, use a staging/build stage and artifact integrity checks.

## 22. Troubleshooting Table for jarmode tools

| Symptom | Common cause | Investigation direction |
| --- | --- | --- |
| **UnsupportedClassVersionError** | Java runtime older than class files/Spring Boot | Check `java -version` and project target JDK |
| Missing **`list-layers`** in help | Older Boot/layertools version or wrong artifact | Check plugin version and jarmode help |
| **Unknown jarmode 'tools'** | Tools dependency absent or unsupported archive | Check `includeTools`, `jar tf`, and actual artifact |
| **no main manifest attribute** | Plain JAR, not repackaged/`bootJar` | Check Maven goal, Gradle `bootJar`, manifest |
| **`java -jar`** launches app instead of `list-layers` | `-Djarmode=tools` placed after `-jar` or typo | Move `-Djarmode=tools` before `-jar` |
| Missing **`BOOT-INF/layers.idx`** | Layering disabled or plain JAR | Check `layers.enabled` and right output |
| `layers.idx` present yet `list-layers` fails | Tools excluded, wrong version, or fully executable prefix | Check `includeTools`, scripts, and logs |
| JAR has **`#!`** shell prefix | Fully executable archive incompatible with tools mode | Build standard executable Boot JAR without `launchScript` |
| `extract` reports non-empty destination | Directory holds stale output | Use fresh destination; use `--force` only with control |
| **Permission denied** on extract | Lacking write permission at target | Choose writable directory, check filesystem permissions |
| **No space left on device** | Extracting many dependencies/JARs exhausted disk quota | Increase staging disk, clean appropriate output scope |
| **NoClassDefFoundError** running extracted JAR | Missed copying `lib`/layer or wrong path | Check the four `COPY` lines and runtime layout |
| Docker **COPY failed** | Artifact missing from context or `.dockerignore` excludes `target` | Inspect build context and `COPY` source paths |
| Container starts then exits | App crash or `ENTRYPOINT` still uses tools mode | Check `docker logs` and Java runtime `ENTRYPOINT` |
| Docker image fails to cache `dependencies` | Stable layer bytes changed, ordering changed, or build cache invalidated | Inspect layer changes, registry/buildkit settings |
| Custom **`company-dependencies`** exists yet missing in Dockerfile | Dockerfile hardcodes the four default layers | Use real `list-layers` output and `COPY` every layer |
| Jar tools fails on Windows | Mistakenly used Unix script or wrong Java/path | Run `java -Djarmode=tools` on a standard JAR |
| Tests pass yet container fails | Tests use build classpath; extracted runtime lacks libs/config | Docker smoke test and dependency resolution |
| Layer list unexpectedly empty | No valid layers index or wrong plugin config | `jar tf`, effective POM, Boot plugin version |

Errors during **`extract`** differ from Spring `ApplicationContext` errors: while tools mode runs, `SpringApplication.main` **has not been called**. If a container opens endpoints yet requests fail due to DB/auth/beans, the classpath may be fine and debugging belongs at the application tier.

## 23. Pre-Release Image Verification Workflow

A pipeline should verify:

1. **Build and tests PASS** on the pinned source commit and toolchain.
2. Output is genuinely a **Spring Boot executable JAR** with **`layers.idx`**, not a plain JAR.
3. Archive contains **`spring-boot-jarmode-tools`** and has no fully executable shell prefix.
4. **`list-layers`** returns the expected set of layer names per policy.
5. **`extract --layers --destination`** succeeds in a fresh directory.
6. Layer folders contain matching contents and, when merged into the runtime layout, yield **`application.jar`** with required dependencies.
7. Dockerfile **`COPY`s every layer in order**, omitting no custom layer.
8. Runtime image uses **`java -jar application.jar`**; tools mode is not used to run the service.
9. Container runs as a non-root user with compatible Java and needed filesystem permissions.
10. HTTP/job smoke test passes against the live image.
11. Image scans, SBOM/provenance, dependency vulnerability checks, and test requirements still run.
12. Track push/pull times, image sizes, and registry caching across releases rather than claiming benefits from layer counts alone.

### 23.1. Expected QA Results Table

| Check | PASS criteria |
| --- | --- |
| Maven/Gradle build | Exit 0, in-scope tests PASS |
| `list-layers` | Prints layer names present in the archive, e.g., the four defaults |
| `extract --layers` | Exit 0, destination holds per-layer folders |
| Runtime layout | `application.jar` + `lib/` and required resources |
| Docker build | Image builds cleanly with all `COPY` instructions |
| Docker run | Java process starts with no missing classes |
| HTTP request | `GET /layers` returns body **`layer-extract-ok`** |
| Cache optimization | Evidence from comparing image layer digests and before/after metrics |

**Never substitute one passing test for all other checks.** Unit tests in Gradle/Maven do not prove a Dockerfile copied every layer; `list-layers` succeeding does not prove the app can connect to a database or serve HTTP when deployed.

## 24. Self-Assessment Questions with Answers

**Q1.** Why not simply copy the whole `app.jar` into a Docker image?

**Answer:** You can copy the whole JAR, but a small edit in app code alters the uber JAR's bytes, forcing the Docker layer containing the JAR to update. Splitting application and dependencies into separate groups makes caching and transferring stable layers more efficient.

**Q2.** Does `list-layers` extract the JAR to disk?

**Answer:** No. It lists layer names from metadata. The **`extract`** command is what writes files to the filesystem.

**Q3.** Why must **`-Djarmode=tools`** come before **`-jar`**?

**Answer:** Because it is a **JVM system property**. Placed after the archive filename, the Java launcher passes it as an application argument instead of setting JarMode at startup time.

**Q4.** What are the four default layers?

**Answer:** **`dependencies`**, **`spring-boot-loader`**, **`snapshot-dependencies`**, **`application`**, in that order.

**Q5.** Do **`extract`** and **`extract --layers`** create the same directory layout?

**Answer:** No. Plain `extract` creates a compact layout with `application.jar` and a `lib` folder; `extract --layers` splits components into per-layer folders for separate Dockerfile `COPY` steps.

**Q6.** After `extract --layers`, is copying only `extracted/application/` enough to run?

**Answer:** Usually **no**. You must merge `dependencies`, `loader`, `SNAPSHOT` dependencies, and `application` per the layer policy to form a complete runtime layout.

**Q7.** If Maven sets **`includeTools=false`** while `layers.idx` still exists, will tools mode definitely run?

**Answer:** No. `includeTools=false` omits the jar tools dependency; the layer index alone does not provide the `list-layers`/`extract` CLI.

**Q8.** Can tools mode be used with a fully executable Spring Boot JAR that has a launch script?

**Answer:** Not according to Spring Boot 3.5 documentation. Build a standard Boot executable JAR without a launch-script prefix.

**Q9.** Why must the Dockerfile `COPY` the four layers one by one?

**Answer:** To assemble all runtime files while keeping independent cache boundaries. Ordering from stable to frequently changing optimizes image layer reuse.

**Q10.** What should you watch out for when running `list-layers` after customizing `layers.xml`?

**Answer:** Output may have different layer names and ordering from the defaults. Your Dockerfile or pipeline must use the exact actual layers to avoid missing dependencies.

**Q11.** Does running **`java -Djarmode=tools -jar app.jar extract`** run tests?

**Answer:** No. It reads an already-built artifact to extract files; tests belong to Maven/Gradle verification phases and must run separately.

**Q12.** What command does the post-extraction Dockerfile run to launch the Spring app?

**Answer:** **`java -jar application.jar`** matching the layout created by Spring Boot tools. It does not run the original uber JAR from the extractor stage and does not pass **`-Djarmode=tools`** at runtime.

## 25. Conclusion

To list and extract layers of a Spring Boot 3.5 executable JAR, remember this sequence:

~~~text
Maven spring-boot:repackage / Gradle bootJar
             |
             v
Spring Boot layered JAR with BOOT-INF/layers.idx
             |
             v
java -Djarmode=tools -jar app.jar list-layers
             |
             v
java -Djarmode=tools -jar app.jar extract --layers --destination extracted
             |
             v
extracted/dependencies/
extracted/spring-boot-loader/
extracted/snapshot-dependencies/
extracted/application/
             |
             v
Dockerfile COPY each layer into /application
             |
             v
java -jar application.jar
             |
             v
SpringApplication.run(...) + HTTP request
~~~

**Remember three conditions:** the archive must be a **Boot executable JAR**, include the tools dependency, and **have no fully executable launch script prefix**. **`list-layers`** only reports layers; **`extract --layers`** produces output folders; the **Dockerfile** turns those folders into image layers. Completing build/test/extract/run/smoke-test is what confirms a layered artifact works in deployment.

## 26. Official References

- Spring Boot 3.5.16 — Dockerfiles: jarmode tools, list-layers, extract --layers, and multi-stage Docker: https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.5 — Efficient Deployments: default extract and layout with application JAR + lib: https://docs.spring.io/spring-boot/3.5/reference/packaging/efficient.html
- Spring Boot 3.5.16 — Maven Plugin, Packaging Executable Archives: layered JAR/WAR, layers.idx, includeTools: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Gradle Plugin, Packaging Executable Archives: bootJar, layered archive, includeTools: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Spring Boot 3.5 — Executable JAR Format: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/index.html
- Spring Boot 3.5 — Nested JARs: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html
- Spring Boot 3.5 — Maven Plugin Using: https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html
- Spring Boot 3.5 — Gradle Plugin Getting Started: https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html
- Docker — Multi-stage builds: https://docs.docker.com/build/building/multi-stage/
- Docker — Build cache: https://docs.docker.com/build/cache/