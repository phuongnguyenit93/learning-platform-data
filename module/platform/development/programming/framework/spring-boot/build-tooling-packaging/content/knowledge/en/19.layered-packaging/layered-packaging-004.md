# Enabling, Disabling, and Customizing Layers with the Maven Plugin

## 1. Problem Statement and Goals

When packaging Spring Boot into an executable JAR, Maven normally creates an archive containing **application classes**, **resources**, the **Spring Boot loader**, and many **dependency JARs**. If you place the entire archive into a Docker image as a single file and then change one Java class, the container build may need to recreate the layer holding the **entire** executable JAR, even though most dependencies have not changed.

**Layered packaging** (*layered JAR*) allows the Spring Boot Maven Plugin to record additional metadata grouping the entries in the archive. Build tools or extraction tools can use that metadata to create separate container layers for parts with different rates of change. Stable libraries usually sit in base layers; application classes and resources usually sit in the final layer.

This topic answers three practical questions directly:

1. How do you **enable** layering in `spring-boot-maven-plugin`, and where can you verify it actually appears?
2. How do you **disable** layering when Docker layering is not needed, while still keeping a JAR runnable via `java -jar`?
3. How do you **customize** layer names, dependency groups, layer ordering, and how entries are assigned via a `layers.xml` file?

After this lesson, you will be able to create a Spring Boot 4.1.2 application with Java 17, package it with Maven, inspect `BOOT-INF/layers.idx`, use `jarmode=tools` to list/extract layers, modify rules in XML, verify app functionality after changing layering, and recognize situations where container caching **does not improve automatically**.

**Versions:** examples use Spring Boot Maven Plugin **4.1.2**, Java **17+**, and a Maven version compatible with Spring Boot 4.1.x. In this version, the extraction tool uses **`-Djarmode=tools`** and the plugin option **`<includeTools>`**. Do not blindly copy `layertools`/`includeLayerTools` from tutorials targeting older versions without checking the active plugin.

## 2. What Is a Layered JAR — and What Is It Not?

A standard Boot executable JAR contains:

~~~text
layer-demo-1.0.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── dev/example/layer/LayerDemoApplication.class
    │   ├── dev/example/layer/LayerMessage.class
    │   └── application.properties
    └── lib/
        ├── spring-boot-*.jar
        ├── spring-core-*.jar
        └── ...
~~~

When **layering is enabled**, the archive still follows **the exact same `BOOT-INF/classes` and `BOOT-INF/lib` layout** for execution. The main difference is added metadata, typically:

~~~text
BOOT-INF/layers.idx
~~~

The `layers.idx` file describes **which entry belongs to which layer** and the order of layers. It does **not** mean each layer becomes its own JAR inside the archive, nor is it a prebuilt Docker image. Only when a Dockerfile, Cloud Native Buildpacks, or another tool **consumes the layering metadata** to split filesystem/container layers does layered caching take effect.

### What Layering Does Not Automatically Change

- Does not alter Java APIs, business logic output, or Spring MVC mappings.
- Does not change normal execution: `java -jar target/layer-demo-1.0.0.jar` remains the primary command.
- Does not make the application start up faster simply because `layers.idx` exists.
- Does not lock dependency versions or make builds reproducible; `outputTimestamp`, toolchains, and generated contents are separate concerns.
- Does not create a Docker image by itself. `spring-boot:build-image` is a separate feature from `spring-boot:repackage`; a Dockerfile is also an independent option.
- Does not guarantee every container build reuses cache. Performing per-layer Docker COPYs, layer order, and what contents actually change are what determine cache reuse.

## 3. Four Default Layers of the Spring Boot Maven Plugin

When Spring Boot 4.1.2 repackages an executable JAR, layered archives **are enabled by default** and have four standard layers:

| Default layer | Contents | Expected change frequency |
| --- | --- | --- |
| `dependencies` | Dependencies without `SNAPSHOT` in their version | Usually changes infrequently |
| `spring-boot-loader` | Spring Boot loader classes | Usually changes only when Spring Boot changes |
| `snapshot-dependencies` | Dependencies with `SNAPSHOT` in their version | Can change often |
| `application` | Application classes/resources and local module dependencies in the same build | Usually changes the most |

Default order in `layerOrder`:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Less frequently changing parts are prioritized earlier so container tools can cache those layers across builds.

### An Easy-to-Miss Detail in Multi-Module Maven

Spring Boot identifies **module dependencies** as modules **belonging to the current Maven build/reactor**. A dependency resolved from a module already installed into `~/.m2` that is **not in the current reactor** may be treated as a **regular dependency**, rather than a module dependency. Therefore, `mvn -pl web-app -am package` and building the app standalone against a pre-installed core can yield **different dependency layer assignments**, despite identical artifact coordinates.

Inspect `layers.idx` under your **actual CI build style**. This change in classification does not mean the code is wrong, but it can affect cache utilization.

## 4. Maven Plugin: Three Configuration Groups to Distinguish

In `spring-boot-maven-plugin`, the relevant settings are:

| Parameter | Location | Meaning |
| --- | --- | --- |
| `layers.enabled` | `<layers><enabled>...</enabled></layers>` | Enables/disables writing layering metadata |
| `layers.configuration` | `<layers><configuration>path</configuration></layers>` | Reads an XML file describing layer rules |
| `layers.configurationName` | `<layers><configurationName>name</configurationName></layers>` | Loads a named configuration `name` from the **Maven plugin** classpath |
| `includeTools` | `<configuration><includeTools>...</includeTools></configuration>` on the plugin, **outside `layers`** | Whether to include Spring Boot JAR tools inside the executable archive |
| `repackage` | Goal of the Boot Maven Plugin | Creates the executable archive and applies layering |
| `outputTimestamp` | `repackage` goal / `project.build.outputTimestamp` | Stabilizes archive entry timestamps; **not a layering switch** |
| `classifier` | `repackage` goal | Separates the executable artifact from the ordinary main JAR; **does not decide layer rules** |

**Correct syntax for Spring Boot 4.1.x** when enabling, in plugin configuration:

~~~xml
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
~~~

With **`spring-boot-starter-parent`**, the `repackage` execution is preconfigured by the parent; the child only needs to declare the plugin and any desired overrides. With a corporate parent or plain BOM, see section 13 since you must bind the `repackage` goal explicitly.

### Enabled by Default vs. Explicitly Enabled

If `<layers>` is omitted from plugin configuration, Spring Boot 4.1 still generates a layered archive by default. Setting `<enabled>true</enabled>` is useful for learners, pipeline policies, and testing toggling behavior, though it is not required to obtain `layers.idx`.

## 5. Runnable Sample Project with Java 17 and Spring Boot 4.1.2

The example uses a simple command-line application without opening an HTTP server so running and comparing outputs is convenient. We will change **only the packaging configuration** without changing Java code, then verify `java -jar` still works.

### 5.1. Project Structure

~~~text
layer-demo/
├── pom.xml
├── src/
│   ├── layers.xml                        # only used in the customization section, outside resources
│   ├── main/
│   │   ├── java/dev/example/layer/
│   │   │   ├── LayerDemoApplication.java
│   │   │   └── LayerMessage.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
│       └── java/dev/example/layer/
│           └── LayerMessageTest.java
└── target/                                # generated by Maven after build
~~~

The `src/layers.xml` file in the example **is not needed yet** for the default-enabled step. Create that file only before moving to the custom configuration in section 10. Do not put it under `src/main/resources` if you only intend it as **build plugin configuration**; putting it in resources would unintentionally package it into the application classpath.

### 5.2. Complete `pom.xml` — Explicitly Enabling Layers

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>layer-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <layers.enabled>true</layers.enabled>
        <layers.tools.enabled>true</layers.tools.enabled>
        <project.build.outputTimestamp>1704067200</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
                        <enabled>${layers.enabled}</enabled>
                    </layers>
                    <includeTools>${layers.tools.enabled}</includeTools>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Explanation of each decision:**

1. Starter parent `4.1.2` manages versions and the preconfigured `repackage` execution, so there is no need to add another execution with a different ID.
2. `<layers.enabled>true</layers.enabled>` is a **custom property defined in the POM**, not a built-in Maven flag. `<enabled>${layers.enabled}</enabled>` allows switching via `-Dlayers.enabled=false` on the command line.
3. `<layers.tools.enabled>true</layers.tools.enabled>` is also a property defined by this example to control `includeTools`. It has no effect if you forget to wire it into `<includeTools>${layers.tools.enabled}</includeTools>`.
4. `<includeTools>` sits alongside `<layers>`, **not** inside `<layers>`. In Spring Boot 4.1.2, the extraction tool is named `spring-boot-jarmode-tools`.
5. `project.build.outputTimestamp=1704067200` is a fixed timestamp equivalent to `2024-01-01T00:00:00Z`; it stabilizes archive entry timestamps for comparison and is **not required to enable layering**. Do not use wall-clock timestamps on every build if reproducibility is the goal.
6. The project does not use the web starter; we will use `CommandLineRunner` to print output and exit. Layer packaging works for CLI apps, HTTP apps, JARs, or WARs according to plugin-supported layouts.

**XML property syntax:** in the actual POM snippet, the exact values are `${layers.enabled}` and `${layers.tools.enabled}`; Maven performs property interpolation. Changing properties on the CLI **works only because the POM references them**.

### 5.3. Java Class — `src/main/java/dev/example/layer/LayerMessage.java`

~~~java
package dev.example.layer;

public final class LayerMessage {

    private LayerMessage() {
    }

    public static String text() {
        return "LAYER_DEMO_OK";
    }
}
~~~

`LayerMessage` is a pure Java 17 class with no Spring dependencies, making logic testing independent.

### 5.4. Spring Boot Application — `LayerDemoApplication.java`

Complete file: `src/main/java/dev/example/layer/LayerDemoApplication.java`.

~~~java
package dev.example.layer;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LayerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayerDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showMessage() {
        return args -> System.out.println(LayerMessage.text());
    }
}
~~~

When the app runs, Spring Boot executes `CommandLineRunner` and prints the string from the Java API. No HTTP server thread keeps the process alive, since the configuration below sets `web-application-type=none`.

### 5.5. `src/main/resources/application.properties`

~~~properties
spring.application.name=layer-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
~~~

These properties reduce logging in the example. They **do not guarantee** that no runtime/JDK or third-party library writes anything to stderr. When verifying, focus on the line printed by `LayerDemoApplication` rather than assuming the entire console output consists of a single line.

### 5.6. Unit Test — `src/test/java/dev/example/layer/LayerMessageTest.java`

~~~java
package dev.example.layer;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LayerMessageTest {

    @Test
    void messageIsStable() {
        assertEquals("LAYER_DEMO_OK", LayerMessage.text());
    }
}
~~~

`LayerMessageTest` is picked up by Maven Surefire via the `*Test` pattern during the `test` phase. Logic tests **do not prove** `layers.idx` exists or is configured properly; packaging QA must inspect the archive after the `package` phase.

## 6. Enabling Layering and Reading the Layer Index

In the project directory containing `pom.xml`:

~~~bash
java -version
mvn -version
mvn clean verify
~~~

Default executable artifact:

~~~text
target/layer-demo-1.0.0.jar
~~~

**Inspect entries in the archive:**

~~~bash
jar tf target/layer-demo-1.0.0.jar
~~~

When layering is enabled, notable entries should include:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/dev/example/layer/LayerDemoApplication.class
BOOT-INF/classes/dev/example/layer/LayerMessage.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/...
BOOT-INF/layers.idx
org/springframework/boot/loader/...
~~~

The full list depends on the transitive dependencies of the specific Boot version. `BOOT-INF/layers.idx` is **direct evidence** of layering metadata.

### 6.1. Viewing `layers.idx` Contents

On Linux/macOS, if `unzip` is available:

~~~bash
unzip -p target/layer-demo-1.0.0.jar BOOT-INF/layers.idx
~~~

The content contains layer names and paths, conceptually similar to:

~~~text
- "dependencies":
  - "BOOT-INF/lib/..."
- "spring-boot-loader":
  - "org/springframework/boot/loader/..."
- "snapshot-dependencies":
- "application":
  - "BOOT-INF/classes/"
~~~

**This is a shortened illustration**, not the byte-for-byte content of `layers.idx`: a real JAR has many artifact names and entry paths, and an empty layer appears if the demo has no SNAPSHOTs. Do not rely on indentation or this listing to write a custom parser; use `jarmode=tools` or a ZIP tool that supports the format.

If `unzip` is unavailable on Windows, create a temporary directory, run `jar xf` **inside that directory**, and read `BOOT-INF/layers.idx`. Do not extract carelessly into the project root or a directory holding important data.

### 6.2. Listing Layers with Spring Boot JAR Tools

When `includeTools=true` and an executable layered JAR exists:

~~~bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar list-layers
~~~

Expected layer names in default mode (in order):

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

The command above **does not run the business app** and does not print `LAYER_DEMO_OK`. It launches the special `tools` mode to read archive metadata.

### 6.3. Extracting Layers

~~~bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar \
    extract --layers --destination target/layer-extract
~~~

On Windows PowerShell, use a single line:

~~~powershell
java -Djarmode=tools -jar target\layer-demo-1.0.0.jar extract --layers --destination target\layer-extract
~~~

The result creates an extraction directory containing corresponding layers, for example:

~~~text
target/layer-extract/
├── dependencies/
├── spring-boot-loader/
├── snapshot-dependencies/
└── application/
~~~

**An empty directory may have no substantial contents** when the project uses no SNAPSHOT dependencies. Use file listing commands to inspect which entries each layer contains. This is filesystem output generated by the tools command; it is **not** a separate directory structure already stored inside the JAR prior to extraction.

If you want to run `extract` again, choose another **empty destination**, or clean up specifically the directory created by the exercise. Never overwrite a directory containing unrelated data.

### 6.4. Running the Application Normally

~~~bash
java -jar target/layer-demo-1.0.0.jar
~~~

**Line printed by Java code:**

~~~text
LAYER_DEMO_OK
~~~

**Key point:** the presence of `layers.idx` does not alter the app's output. Packaging metadata serves container/repackaging tools and does not change the value returned by `LayerMessage.text()`.

## 7. Disabling Layering While Keeping an Executable JAR

**Direct approach:** in plugin configuration, set:

~~~xml
<configuration>
    <layers>
        <enabled>false</enabled>
    </layers>
</configuration>
~~~

This is a **fragment** that belongs inside `spring-boot-maven-plugin`. When applied to the complete POM from section 5, simply override the corresponding property:

~~~bash
mvn clean verify -Dlayers.enabled=false
~~~

Because `<enabled>${layers.enabled}</enabled>` is wired to the Maven property, the command disables **layer metadata generation** during Boot repackaging. This is **not** a standard system property that works automatically across arbitrary POMs; if you copy the command into a POM without this interpolation, inspect the effective POM or use the XML fragment directly.

### PASS Evidence When Disabled

1. `target/layer-demo-1.0.0.jar` is still generated because the `repackage` goal still runs.
2. `jar tf target/layer-demo-1.0.0.jar` **no longer contains the `BOOT-INF/layers.idx` entry**.
3. `BOOT-INF/classes` and `BOOT-INF/lib` remain present; that is the normal executable JAR layout.
4. `java -jar target/layer-demo-1.0.0.jar` still prints `LAYER_DEMO_OK`.
5. Do not use `java -Djarmode=tools ... list-layers` as the primary QA check for the disabled state, since the archive may lack tools or layer data to list. Inspect the index and runtime directly.

**Do not confuse ways of disabling:**

| Method | What it actually does | Produces an executable JAR? |
| --- | --- | --- |
| `layers.enabled=false` | Skips generating the layer index | **Yes**, if `repackage` still runs |
| `includeTools=false` | Omits jar tools for extraction | **Yes**, layering may still be enabled with `layers.idx` present |
| `spring-boot.repackage.skip=true` | Skips the repackage goal | No **Boot executable output from that goal** |
| Removing the Boot plugin completely | No Boot repackage execution under standard config | A plain JAR may still be produced |
| `layout=NONE` | Packages dependencies without the Boot launcher | Not a standard `java -jar` executable JAR |

**Do not use `skip` or `layout=NONE` to “disable layers”** if the goal is still to have an executable JAR. Those change the packaging contract entirely.

## 8. Disabling Extraction Tools While Keeping Layers

In Spring Boot 4.1.2, when building a layered JAR, the plugin can include `spring-boot-jarmode-tools` inside the executable archive. This is the tool supporting `list-layers` and `extract`; it is **not required for the application to run via `java -jar`**.

If release requirements exclude tools, set **at the plugin configuration level**:

~~~xml
<configuration>
    <layers>
        <enabled>true</enabled>
    </layers>
    <includeTools>false</includeTools>
</configuration>
~~~

With the complete POM from section 5:

~~~bash
mvn clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=false
~~~

**Expected signs:**

- The archive still contains `BOOT-INF/layers.idx` because layering is enabled.
- The archive **does not bundle `spring-boot-jarmode-tools`**, so do not expect `java -Djarmode=tools -jar ... list-layers` to work.
- The application still runs via `java -jar` and prints `LAYER_DEMO_OK`.
- Any Dockerfile relying on `jarmode=tools extract` will need a different workflow or tools enabled in a build stage; you cannot both strip tools from the archive and assume internal extract commands remain available.

**Rule:** `layers.enabled` controls **layer metadata**; `includeTools` controls the **layer-handling tools**. These are two switches with independent purposes. In Spring Boot 4.1.x documentation, use the name **`includeTools`**, not the old `includeLayerTools` parameter.

## 9. Why Do We Need a `layers.xml` File?

The four default layers suffice for many applications, yet not every dependency changes at the same frequency. For example:

- A project depends on multiple `org.springframework` modules that rarely change within a release train.
- There is a group of internal dependencies `com.acme:*` that change according to their own release policy.
- Some local modules in the reactor change alongside application source, so keeping them in the `application` layer makes sense.
- Some SNAPSHOT dependencies are rebuilt more often than release dependencies.

**The goal of customization** is to group contents with similar change schedules together and place stable groups before frequently changing ones. The `layers.xml` file is used **when `spring-boot:repackage` runs**, not as runtime Spring `application.properties` configuration.

### How to Enable a Custom File

Inside `spring-boot-maven-plugin`:

~~~xml
<configuration>
    <layers>
        <enabled>true</enabled>
        <configuration>${project.basedir}/src/layers.xml</configuration>
    </layers>
</configuration>
~~~

`${project.basedir}` points to the directory of the **current POM**. In a multi-module build, each module has its own `project.basedir`; when using this snippet in the `web-app` module, the XML file must be at `web-app/src/layers.xml` or you must supply the corresponding path.

**Do not place `layers.xml` into `<resources>` just so the plugin finds it.** This file is build-time plugin configuration. Packaging a configuration inside a **plugin dependency JAR** is a different mechanism (`configurationName`), discussed separately in section 12.

## 10. Valid `src/layers.xml` File for Spring Boot 4.1.x

The example below **actually splits out a `spring-framework` layer** for dependencies with groupId `org.springframework`. Even in an app using only `spring-boot-starter`, Spring Framework modules such as `spring-core` belong to this groupId and can be inspected in that layer.

### 10.1. Complete XML Content

File: **`src/layers.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<layers xmlns="http://www.springframework.org/schema/boot/layers"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="
          http://www.springframework.org/schema/boot/layers
          https://www.springframework.org/schema/boot/layers/layers-4.1.xsd">

    <application>
        <into layer="spring-boot-loader">
            <include>org/springframework/boot/loader/**</include>
        </into>
        <into layer="application" />
    </application>

    <dependencies>
        <into layer="application">
            <includeModuleDependencies />
        </into>

        <into layer="snapshot-dependencies">
            <include>*:*:*SNAPSHOT</include>
        </into>

        <into layer="spring-framework">
            <include>org.springframework:*</include>
        </into>

        <into layer="dependencies" />
    </dependencies>

    <layerOrder>
        <layer>dependencies</layer>
        <layer>spring-framework</layer>
        <layer>spring-boot-loader</layer>
        <layer>snapshot-dependencies</layer>
        <layer>application</layer>
    </layerOrder>
</layers>
~~~

**This is a complete XML file**, not a snippet. The namespace and **`layers-4.1.xsd`** schema match Spring Boot Maven Plugin 4.1.x. When moving to another Boot version, check the new XSD instead of keeping this schema version indefinitely.

### 10.2. Why Choose This `<into>` Order?

Spring Boot evaluates `<into>` elements **from top to bottom** within each section to “claim” entries:

- **`<application>`:** first captures Boot launcher classes with the Ant-style path pattern `org/springframework/boot/loader/**` into `spring-boot-loader`. Remaining application classes/resources go into `application`.
- **`<dependencies>`:** first places dependencies **belonging to the current reactor** into `application`. Next, dependencies with `...SNAPSHOT` versions go into `snapshot-dependencies`. Next, groupId `org.springframework` goes into `spring-framework`. Unclaimed dependencies go into `dependencies`.
- Each subsequent `<into>` evaluates only entries **not already claimed by an earlier rule**. If a dependency is both a local module and a SNAPSHOT, it is claimed by the first module dependency rule rather than falling into snapshot.
- `<into layer="dependencies" />` without `<include>` is the **catch-all** for unmatched dependencies. `<into layer="application" />` is likewise the catch-all in the application section.

**Place specific rules before the catch-all.** Putting the `dependencies` catch-all at the top claims almost everything immediately, leaving custom `spring-framework` or `snapshot-dependencies` layers below it empty. This is a very common XML configuration mistake.

### 10.3. `<layerOrder>` Differs from Matching Rule Order

The `<into>` elements define **entry selection rules**; `<layerOrder>` defines the **layer writing order** used for caching:

~~~text
dependencies
spring-framework
spring-boot-loader
snapshot-dependencies
application
~~~

All layer names referenced by `<into>` must appear in `<layerOrder>`. Forgetting `spring-framework` or misspelling a name can fail the build. Note that `spring-boot-loader` is declared inside the `<application>` XML section yet placed among the stable layers in `layerOrder`.

### 10.4. What Happens to Dependencies in the Sample Project?

- JARs under groupId `org.springframework`, such as `spring-core`, are claimed by the `spring-framework` rule unless claimed earlier.
- Other release dependencies go into `dependencies`.
- In a project without SNAPSHOT dependencies, `snapshot-dependencies` may have no substantial entries, though the layer name remains in the configuration.
- This single-module demo has no local module dependencies, so `<includeModuleDependencies />` claims nothing; keeping the rule ensures the config works properly if the project becomes a multi-module Maven build.
- `LayerDemoApplication.class`, `LayerMessage.class`, and `application.properties` belong to `application`; Boot launcher classes belong to `spring-boot-loader`.

**Do not use an example like `<include>com.acme:*</include>` and claim the new layer definitely has files** if the POM lacks such dependencies. With the `org.springframework:*` rule, the demo clearly demonstrates a non-empty custom layer.

## 11. Activating Custom XML and Verifying

After creating `src/layers.xml`, **edit the `<layers>` block** in the POM from section 5 to:

~~~xml
<layers>
    <enabled>${layers.enabled}</enabled>
    <configuration>${project.basedir}/src/layers.xml</configuration>
</layers>
~~~

Keep `<includeTools>${layers.tools.enabled}</includeTools>` outside the block. Do not add two `<layers>` blocks at the same level in a plugin configuration; there must be only **one** layer configuration block.

Run:

~~~bash
mvn clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=true
~~~

**Step A — inspect the index:**

~~~bash
jar tf target/layer-demo-1.0.0.jar
unzip -p target/layer-demo-1.0.0.jar BOOT-INF/layers.idx
~~~

You should see the new `spring-framework` layer and `org.springframework` dependency entries classified according to the XML rules. Do not assert an exact file count in the layer, because transitive dependencies vary by version and resolution.

**Step B — query JAR tools:**

~~~bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar list-layers
~~~

Expected layer list matching `layerOrder`:

~~~text
dependencies
spring-framework
spring-boot-loader
snapshot-dependencies
application
~~~

**Step C — extract into a dedicated directory:**

~~~bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar \
    extract --layers --destination target/custom-layer-extract
~~~

Inside the extraction directory, files must be separated according to the XML configuration, with `spring-framework` as the new layer name. Inspect `target/custom-layer-extract/spring-framework/` and `target/custom-layer-extract/dependencies/` to see the difference. **A new layer present in the index without files** is a signal to review the rule/pattern or actual dependencies, not necessarily a parser bug.

**Step D — verify unchanged runtime behavior:**

~~~bash
java -jar target/layer-demo-1.0.0.jar
~~~

Stdout printed by application code still contains:

~~~text
LAYER_DEMO_OK
~~~

If the app fails to start after changing layering, the issue usually lies in XML syntax, rules failing to cover certain entries, or misconfigured archive layout/plugin execution—not business code changes.

## 12. Advanced Customizations

### 12.1. Placing Internal Dependencies in a Separate Layer

When an application has an actual `com.acme:inventory-client:1.2.3` dependency, you can add a rule:

~~~xml
<into layer="company-dependencies">
    <include>com.acme:*</include>
</into>
~~~

Place it in `<dependencies>` **after higher-priority rules and before the catch-all**. At the same time, add:

~~~xml
<layer>company-dependencies</layer>
~~~

to `<layerOrder>` at a position matching the volatility of internal dependencies. If internal SNAPSHOTs should go into `snapshot-dependencies`, keep the SNAPSHOT rule before `com.acme:*`. If all `com.acme` deps, including SNAPSHOTs, belong in the company layer, move the company rule before SNAPSHOT (keeping in mind that module dependencies are already claimed by the first rule).

**Do not put `includeModuleDependencies` into the company layer while still expecting reactor project libraries to stay in `application`:** that alters the grouping policy and requires checking cache behavior when a local module changes.

### 12.2. Splitting Application Resources into Another Layer

`<application>` supports Ant-style `<include>`/`<exclude>` patterns. Rules can place stable resources/configs into a separate layer, but you must verify the **actual entry path** inside the JAR before writing globs. Do not assume source paths like `src/main/resources/...` match entry paths inside the executable archive. Inspect `jar tf` and matching semantics for your plugin version, then add specialized rules **before the `<into layer="application" />` catch-all**.

Every new layer name must be added to `layerOrder`; verify the index and extraction output. If configs/secrets are dynamically generated, splitting them into a separate layer does not make them stable: the content still changes and can invalidate cache.

### 12.3. Using `configurationName` Instead of a File Path

Spring Boot Maven Plugin 4.1.x also supports layer configurations on the **Maven plugin's own classpath**. For example, if a plugin dependency JAR contains:

~~~text
META-INF/spring/layers/custom.xml
~~~

you can configure:

~~~xml
<layers>
    <enabled>true</enabled>
    <configurationName>custom</configurationName>
</layers>
~~~

and add the JAR containing that file to `<dependencies>` of **spring-boot-maven-plugin** (plugin dependencies, not application runtime dependencies).

This mechanism fits organizations wanting to apply shared rules from a build-tool artifact. It is **not equivalent** to placing `META-INF/spring/layers/custom.xml` in the application's `src/main/resources`; the app runtime classpath and Maven plugin classpath are two different environments. Do not configure both `configuration` and `configurationName` simultaneously and rely on undocumented precedence; choose one approach.

### 12.4. Repackaging Artifacts with a Classifier

The Maven plugin can produce an executable `-exec.jar` while keeping the ordinary JAR as the main artifact. That is the `<classifier>exec</classifier>` mechanism on `repackage`, **separate from layer rules**. When using a classifier, QA must inspect `layers.idx` inside the **actual executable `-exec.jar`**, not the plain main JAR by mistake.

Similarly, a WAR uses the `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided` layout specific to servlet packaging; do not hardcode the JAR path `BOOT-INF/layers.idx` as an assumption for all WARs. The examples in this lesson use `jar` packaging.

## 13. Maven Corporate Parent or Plain BOM

When a project does **not** use `spring-boot-starter-parent` and only imports the `spring-boot-dependencies` BOM, you cannot assume the `repackage` plugin execution exists. Pin the plugin version and bind the goal in the `package` phase:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
    <configuration>
        <layers>
            <enabled>true</enabled>
            <configuration>${project.basedir}/src/layers.xml</configuration>
        </layers>
        <includeTools>true</includeTools>
    </configuration>
    <executions>
        <execution>
            <id>repackage</id>
            <phase>package</phase>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

This is a **fragment for `build/plugins`**, not a complete POM. The Maven `jar` lifecycle must build the source JAR before the Boot `repackage` goal runs; with custom Jar Plugin executions in the same phase, declare the Jar Plugin before the Spring Boot Plugin so the source artifact already exists.

To use this fragment, the project must also manage dependency versions, compiler release `17`, test plugins, and resources per corporate build policy. **Importing a BOM only manages dependency versions; it does not provide plugin executions.**

To inspect the effective configuration:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn clean verify
~~~

In the effective POM, look for exactly one `spring-boot-maven-plugin` with a `repackage` execution, one `layers` block with the expected values, and an existing `src/layers.xml` file. Never accidentally bind `repackage` on a `pom`-packaged parent or a library module lacking an application main class.

## 14. Docker Caching: When Does Layering Actually Provide Benefits?

A Dockerfile might copy the executable JAR as **one** file:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/layer-demo-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

This **does not automatically use `layers.idx` to split Docker layers**: the `COPY` instruction still takes the whole JAR file, so changing a single class usually invalidates the Docker layer containing the JAR.

To take advantage of layering, a build stage must extract it:

~~~dockerfile
FROM eclipse-temurin:17-jre AS unpack
WORKDIR /builder
COPY target/layer-demo-1.0.0.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application
COPY --from=unpack /builder/extracted/dependencies/ ./
COPY --from=unpack /builder/extracted/spring-boot-loader/ ./
COPY --from=unpack /builder/extracted/snapshot-dependencies/ ./
COPY --from=unpack /builder/extracted/application/ ./
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

**This Dockerfile illustrates the four default layers**, not a complete production security guide. It assumes layer tools are included, `layers.idx` has valid data, and the runtime uses Java 17. When switching to the **custom `spring-framework` layer**, add `COPY --from=unpack /builder/extracted/spring-framework/ ./` **in the order specified by `layerOrder`**; forgetting it can leave the runtime missing dependencies moved to that layer.

For production, add a non-root user, pinned base image digests, image scanning, provenance, `.dockerignore`, and secret-handling practices per organizational policy. In this minimal example, the sole objective is **demonstrating the relationship between the layer index and Docker COPY boundaries**.

### Three Notes on Caching

1. **Layer order matters**: placing a volatile layer before a stable layer causes subsequent layers to rebuild according to cache dependency rules.
2. **Layer content matters**: a frequently changing SNAPSHOT dependency invalidates its layer, though not necessarily stable layers before it.
3. **How the image is built matters**: layering inside a JAR **does not automatically** create extra Docker layers. The container build tool must consume `layers.idx` (via jarmode/buildpacks or equivalent). Measure `docker history`, image layers, and actual cache hits instead of claiming fixed savings upfront.

## 15. QA Procedure for the Three Modes

| Mode | Maven invocation | Expected result |
| --- | --- | --- |
| **Default/layers enabled** | `mvn clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=true` | `BOOT-INF/layers.idx` present, tools list/extract work, app runs |
| **Layering disabled** | `mvn clean verify -Dlayers.enabled=false` | No `BOOT-INF/layers.idx`, executable app still runs |
| **Custom XML** | Add `src/layers.xml` and configure `layers.configuration`, then `mvn clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=true` | `spring-framework` layer present, XML rules/`layerOrder` reflected in index/tools, app runs |
| **Layers enabled, tools omitted** | `mvn clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=false` | Index present; no jar tools in archive; app runs |

**Do not compare two modes merely by checking the JAR file count:** all four can output the exact same filename `target/layer-demo-1.0.0.jar` because `repackage` runs. The difference lies in the **layer index, tool dependency, and entry assignments**.

### Sample QA Commands on Linux/macOS: Default Layering

~~~bash
set -eu
mvn -B -ntp clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=true

JAR=target/layer-demo-1.0.0.jar
jar tf "$JAR" | grep -Fx 'BOOT-INF/layers.idx'
java -Djarmode=tools -jar "$JAR" list-layers
java -jar "$JAR" | grep -Fx 'LAYER_DEMO_OK'
~~~

`jar tf` + `grep -Fx` confirms the exact layer index entry. `java -jar` verifies runtime behavior is unchanged. **However, this test does not prove a Dockerfile uses caching**; that is a separate check during container builds.

### Sample QA Commands on Linux/macOS: Layering Disabled

~~~bash
set -eu
mvn -B -ntp clean verify -Dlayers.enabled=false

JAR=target/layer-demo-1.0.0.jar

if jar tf "$JAR" | grep -Fx 'BOOT-INF/layers.idx'; then
    echo "FAIL: layers.idx must not exist"
    exit 1
fi

java -jar "$JAR" | grep -Fx 'LAYER_DEMO_OK'
echo "LAYERING_DISABLED_AND_APP_OK"
~~~

**Shell pipeline note:** this example uses `set -eu` without `pipefail`; here `grep` checks `layers.idx` via `if` and the application has its own line. In strict CI, enable `set -o pipefail` when supported by the shell and check Java's exit code directly to avoid masking errors on the left side of a pipeline.

### Windows PowerShell: Reading Output Without `unzip`

~~~powershell
mvn clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=true
if ($LASTEXITCODE -ne 0) { throw "Maven build failed" }

jar tf target\layer-demo-1.0.0.jar |
    Select-String -SimpleMatch 'BOOT-INF/layers.idx'

java -Djarmode=tools -jar target\layer-demo-1.0.0.jar list-layers
if ($LASTEXITCODE -ne 0) { throw "Layer tools failed" }

java -jar target\layer-demo-1.0.0.jar
if ($LASTEXITCODE -ne 0) { throw "java -jar failed" }
~~~

In PowerShell, `Select-String` output indicates a match, but in CI you should ensure at least one match exists—for example by capturing it in a variable and checking for `$null`. Use Maven/Java from your pre-installed environment or the project's Wrapper if provided.

## 16. Common Errors and Diagnostics

| Symptom | Causes worth checking | Resolution |
| --- | --- | --- |
| `mvn package` builds JAR without `layers.idx` | `layers.enabled=false`, wrong plugin/version, or inspecting ordinary JAR | Check effective POM, right Boot repackaged JAR, and `jar tf` |
| Running `mvn spring-boot:repackage` standalone reports missing input JAR | `repackage` goal needs source jar/war from the package phase | Use `mvn clean package` / `mvn clean verify` |
| `java -Djarmode=tools` fails to run | `includeTools=false`, tools absent from archive, altered layout, misbuilt JAR | Check `includeTools` and `jar tf`; enable tools if extraction is needed |
| A tutorial uses `-Djarmode=layertools` | Tutorial for an older Spring Boot release | Use `-Djarmode=tools` for Boot 4.1.x |
| Custom XML rejected due to XSD | Wrong namespace, using 3.x/4.0 schema for 4.1, or invalid structure | Use `layers-4.1.xsd` and a valid `<layers>` template |
| Maven reports `src/layers.xml` not found | Wrong module `project.basedir`, file not created, filename case mismatch | Verify path relative to the current POM |
| Custom layer missing from `list-layers` | XML configuration not enabled or inspecting stale archive | Check plugin configuration and run `clean verify` |
| New layer exists by name yet is empty | `include` matches no dependency group/path | Check `dependency:tree`, `jar tf`, and XML patterns |
| SNAPSHOT accidentally placed in company layer | `<into>` order let the company rule claim it first | Move the SNAPSHOT rule earlier if that matches policy |
| Local module dependency lands in `dependencies` | Core is not in the current reactor | Run a consistent reactor build or accept different classification policy |
| `layerOrder` omits a custom layer | Referenced layer name not listed completely | Add the exact layer name to `layerOrder` |
| Custom Dockerfile missing dependencies | Added XML layer but forgot to `COPY` that layer | Update Dockerfile to match `list-layers` |
| Docker still rebuilds entire JAR on one class edit | Dockerfile only runs `COPY app.jar` as one layer | Use jarmode extract/buildpacks and per-layer COPY |
| `includeTools=false` yet expecting extract to work | Tools are optional and separate from the layer index | Run tools in a build artifact/stage or adjust workflow |
| App fails to run after packaging changes | Wrong source JAR/manifest/classifier or missing dependency from config | Check `Main-Class`, `Start-Class`, `BOOT-INF/lib`, and run `java -jar` |
| `layers.idx` differs across builds of the same commit | Different reactor membership, dependency resolution, or plugin config | Compare effective POM, dependency graph, versions, and build flags |
| Java 17 fails due to bytecode version | Misconfigured JDK/toolchain, compile target newer than runtime | Check `java -version`, Maven compiler release, and JDK policy |

**Diagnostic workflow:** (1) read which Maven goal/execution actually ran → (2) inspect effective POM → (3) verify the right archive → (4) read `BOOT-INF/layers.idx` → (5) run `list-layers`/`extract` if tools exist → (6) test `java -jar` → (7) inspect container caching. Fix **the exact layer causing the issue**; do not alter application code when only packaging metadata is wrong.

## 17. Self-Check Exercises and Answers

**1. What are the default layers of the Spring Boot Maven Plugin?**

Answer: `dependencies`, `spring-boot-loader`, `snapshot-dependencies`, and `application`; the default order also runs from typically stable layers to frequently changing layers.

**2. Does enabling layering cause `jar tf` to display a separate JAR file for each layer?**

No. Layering primarily adds `BOOT-INF/layers.idx`; extraction/container-build tools are what split filesystem or Docker layers.

**3. Does setting `<layers><enabled>false</enabled></layers>` stop the application from running with `java -jar`?**

No, provided `spring-boot:repackage` still runs and produces a valid executable JAR. It only disables layer metadata, not the Boot launcher or dependencies.

**4. What is the difference between `enabled=false` and `includeTools=false`?**

`enabled=false` skips creating the layer index; `includeTools=false` omits the JAR tools dependency even though the layer index can still exist if `enabled=true`.

**5. To use custom XML, what must be declared in the POM?**

Use `<layers><enabled>true</enabled><configuration>${project.basedir}/src/layers.xml</configuration></layers>` inside the Spring Boot Maven Plugin configuration. Create the actual XML file at the declared path.

**6. Which XML schema matches Spring Boot Maven Plugin 4.1.x?**

`https://www.springframework.org/schema/boot/layers/layers-4.1.xsd` with namespace `http://www.springframework.org/schema/boot/layers`.

**7. In XML, does the order of `<into>` elements matter?**

Yes. Rules run top to bottom; an earlier rule claims matching entries, and later rules see only the remainder. Putting a catch-all too early “swallows” contents meant for specific layers.

**8. Can `layerOrder` omit the `spring-framework` layer if the XML declares it under `<dependencies>`?**

No. Every referenced layer must be listed in `layerOrder`; layer names must match.

**9. Why can a module dependency with the same coordinates be layered differently across two builds?**

If core belongs to the same Maven reactor in one build and only exists as an installed JAR in the local repository in another, Boot can classify it as a module dependency the first time and as a regular dependency the next.

**10. If a Dockerfile only runs `COPY target/app.jar app.jar`, does it leverage the layer index?**

Not automatically. One COPY of the JAR file creates a Docker layer holding the whole archive; layered extract/COPY steps or metadata-aware build tools are required.

**11. If `includeTools=false` is set, can you still run `java -jar` normally?**

Yes. JAR tools serve layer extraction/inspection, not the business runtime of the Spring Boot app.

**12. Does the existence of `layers.idx` guarantee a smaller container image?**

No. The feature supports layer caching and optimizes rebuilds in appropriate scenarios; total image size and cache hits depend on the dependency graph, Dockerfile, base image, and change frequency.

## 18. Checklist for Applying to Real Projects

- [ ] Spring Boot Maven Plugin matches the project version; understand how the `repackage` goal is bound.
- [ ] If using starter parent, avoid adding unnecessary duplicate `repackage` executions.
- [ ] `layers.enabled` is configured intentionally as needed, not left to accidental profile overrides.
- [ ] When enabled, `jar tf` reveals `BOOT-INF/layers.idx`.
- [ ] If CI uses `jarmode=tools`, `includeTools=true`.
- [ ] When disabled, `layers.idx` is absent yet `java -jar` still runs.
- [ ] `src/layers.xml` uses the proper XML namespace and XSD compatible with Boot 4.1.
- [ ] `<into>` rules are ordered by priority, with catch-alls at the end.
- [ ] `layerOrder` lists all layer names used in the XML.
- [ ] Ran `list-layers` and verified custom layers actually capture the intended dependencies/entries.
- [ ] When adding new layers, updated Dockerfile/OCI tool copies to match the layer order.
- [ ] Module dependencies are recognized consistently under the CI reactor build.
- [ ] Do not confuse the layer index with classpath layout or Java packages.
- [ ] Separate container build privileges from runtime secrets; never package secrets into JARs.
- [ ] Verify artifact identity, Java runtime, unit tests, and app smoke tests prior to release.
- [ ] Evaluate cache hits via real container builds rather than inferring from layer counts.
- [ ] Keep reproducibility (checksums, timestamps, dependency locking) distinct from cache-layering.

**Conclusion:** The Spring Boot Maven Plugin has **three core operations** for layered executable archives: `<layers><enabled>true</enabled></layers>` to enable, `false` to disable, and `<layers><configuration>.../layers.xml</configuration></layers>` to customize. Verify via `BOOT-INF/layers.idx` and `-Djarmode=tools`, then make sure your Dockerfile or buildpacks actually consume the layer order. **Layering helps manage container caching; it does not replace testing the executable JAR and does not alter application functionality.**

## 19. Official References

1. [Spring Boot Maven Plugin 4.1.2 — Packaging Executable Archives / Layered Jar or War](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
2. [Spring Boot Maven Plugin — Repackage Goal Parameters: layers, includeTools, outputTimestamp](https://docs.spring.io/spring-boot/maven-plugin/packaging.html#spring-boot:repackage)
3. [Spring Boot — Dockerfiles / Using JAR Tools and Layers](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html)
4. [Spring Boot — Executable JAR Format and Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
5. [Spring Boot Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
6. [Spring Boot Maven Plugin — Spring Boot 4.1 Layers XSD](https://www.springframework.org/schema/boot/layers/layers-4.1.xsd)
7. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
8. [Apache Maven — Introduction to Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
9. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
10. [Spring Boot Maven Plugin — Build Image](https://docs.spring.io/spring-boot/maven-plugin/build-image.html)