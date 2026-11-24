# Configuring `mainClass`, `finalName`, and Output Directories in Maven with Spring Boot

## 1. Why Do You Need to Understand These Three Settings?

When building a Spring Boot application with Maven, `mvn package` can produce multiple files: compiled classes, test reports, a regular JAR, and an executable JAR repackaged by the Spring Boot Maven Plugin. To run or deploy the right file automatically, you need to answer three separate questions:

- **`mainClass`:** which Java class is the application entry point?
- **`finalName`:** what is the base name of the locally generated artifact?
- **Output directories:** where do classes, intermediate files, and the final JAR reside?

These three settings relate to one another but do not replace one another. Renaming the archive **does not** change the main class. Changing where compiled classes are stored **does not** automatically move where the JAR is written. Configuring the right class without binding the `repackage` goal can still produce a plain JAR that cannot run via `java -jar`.

This lesson belongs to **Maven with Spring Boot** under **Spring Boot Build Tooling Packaging**. It focuses on how Maven and the Spring Boot Maven Plugin create, name, place, and verify executable archives. Runtime configuration and CI/CD topics are brought in where they directly affect packaging outcomes.

After this lesson, you will know how to write `pom.xml` to select the main class, set the JAR name, and change build directories; run a Java 17+ example; inspect the manifest and JAR structure; and diagnose errors that arise when renaming or relocating artifacts.

## 2. Distinguishing Concepts Before Configuring

| Concept | Typical Configuration Location | Meaning | Example |
| --- | --- | --- | --- |
| Maven coordinates | `<groupId>`, `<artifactId>`, `<version>` | Module identity for install/deploy and declaring dependencies | `example.learning:packaging-demo:1.0.0` |
| Application main class | `<mainClass>` on Spring Boot Maven Plugin | Class with the `main` method invoked by the launcher | `demo.Application` |
| Local artifact base name | `<build><finalName>` | Local package filename before extension/classifier | `demo-service` |
| General build directory | `<build><directory>` | Root for build files and intermediate outputs | `target` |
| Compiled main classes | `<build><outputDirectory>` | Location for production classes and resources after compile/process-resources | `target/classes` |
| Compiled test classes | `<build><testOutputDirectory>` | Location for test classes/resources | `target/test-classes` |
| Repackage output directory | `<outputDirectory>` **inside** `spring-boot-maven-plugin` | Location where `repackage` writes its archive | Defaults to `project.build.directory` |

Standard Maven default values are:

~~~text
project.build.directory       = target
project.build.outputDirectory = target/classes
project.build.testOutputDirectory = target/test-classes
project.build.finalName       = artifactId-version
~~~

In a real POM, these values can be changed by a parent, plugins, or project properties. To know actual values, inspect the **effective POM** rather than guessing from folder names.

### 2.1. Multiple Elements Named `outputDirectory`

This is the most common mistake. Setting:

~~~xml
<build>
    <outputDirectory>build/classes</outputDirectory>
</build>
~~~

means **changing the compiled classes directory**, not causing the JAR file to appear at `build/classes/app.jar`.

Conversely, setting:

~~~xml
<build>
    <directory>build-output</directory>
</build>
~~~

changes the **overall build directory**, so Maven and plugins using `project.build.directory` generally write into that area.

If `<outputDirectory>` appears **inside the Spring Boot Maven Plugin configuration** and the goal supports that parameter, it sets the plugin goal's output path. The two look similar in syntax yet belong to two different configuration layers and must not be swapped.

## 3. Maven `package` and Spring Boot `repackage`

For a `<packaging>jar</packaging>` project, the typical flow is:

~~~text
src/main/java + src/main/resources
                  |
                  v
      Maven resource/compile phases
                  |
                  v
             target/classes
                  |
                  v
         Maven jar:jar (package)
                  |
                  v
      Plain JAR from project code
                  |
                  v
    Spring Boot repackage goal
                  |
                  v
 Executable JAR + Boot launcher
                  |
                  v
              java -jar
~~~

The Maven lifecycle has many other phases and goals; this diagram highlights only the steps relevant to this lesson. `spring-boot:repackage` takes the archive created during the `package` phase, arranges classes and runtime dependencies in the Spring Boot executable layout, and configures the manifest for the launcher.

A JAR holding only the application's classes does not automatically include all runtime dependencies. For a Spring Boot application, an executable JAR typically contains:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/...
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

This listing is an **abbreviated illustration**, not verbatim stdout of `jar tf`. In Spring Boot 3.3, launchers such as `org.springframework.boot.loader.launch.JarLauncher` belong to the Boot loader. Exact names depend on the Boot version and archive type.

### 3.1. When Does the `repackage` Goal Run?

- If the project uses `spring-boot-starter-parent` and declares `spring-boot-maven-plugin` under `<build><plugins>`, the `repackage` execution is already configured for the lifecycle by the parent.
- If the project **does not use the Boot parent**, you typically need to bind `repackage` to the `package` lifecycle yourself using `<executions>`, while also managing the plugin version.
- Calling `spring-boot:repackage` alone in a freshly cleaned directory with no source JAR to repackage can fail. When invoking explicitly, run `mvn package spring-boot:repackage` so `package` executes first, or configure an execution and run `mvn package` once per standard workflow.

Do not append `spring-boot:repackage` after a `mvn package` command that already binds that goal unless you have a clear reason. Running it redundantly can make outputs and logs confusing to diagnose.

## 4. `mainClass`: Selecting the Java Entry Point

### 4.1. What Is an FQCN?

Example Java file:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

The class is declared in package `demo`, so its **fully qualified class name (FQCN)** is `demo.Application`. In `mainClass`, use the FQCN—**not** `Application.java`, `src/main/java/demo/Application.java`, or `Application` when the class belongs to a package.

The Spring Boot Maven Plugin can auto-detect a class containing a `main` method when `mainClass` is omitted. When a project has multiple main classes, auto-detection can produce unexpected results; configure it explicitly.

### 4.2. Where Does `mainClass` Go?

In `pom.xml`, place the following under `<build><plugins>`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>demo.Application</mainClass>
    </configuration>
</plugin>
~~~

The Spring Boot Maven Plugin writes entry-point metadata during `repackage`. For a Spring Boot 3.3 executable JAR with standard layout, the manifest typically has two key entries:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.Application
~~~

- **`Main-Class`** is the launcher class invoked directly by the JVM on `java -jar`. The Spring Boot launcher knows how to load classes and nested JARs inside the executable archive.
- **`Start-Class`** is the application main class invoked by the launcher once the classpath is prepared.

Therefore, to change the **application class**, configure `mainClass` on the Spring Boot Maven Plugin. **Do not** try setting `Main-Class: demo.Application` via `maven-jar-plugin` to bypass the Boot loader. When `repackage` runs, the Boot plugin rewrites both `Main-Class` and `Start-Class` according to its layout.

### 4.3. One Module with Multiple Main Classes

Suppose a project has `demo.Application` to run a service and `demo.ImportTool` to run a CLI tool. If the published artifact is the server, set `demo.Application`. If you need two independent runnable apps, it is usually cleaner to split into two modules/artifacts or configure multiple controlled executions/classifiers. Never rely on compiler class ordering as a stable main-class selection contract.

### 4.4. `mainClass` Is Not Runtime Configuration

`mainClass` does not determine the HTTP port, profile, database URL, or `application.yml`. For example:

~~~bash
java -jar target/demo-service.jar --spring.profiles.active=dev
~~~

With the manifest already packaged, the entry point remains `demo.Application`. Spring Boot reads `spring.profiles.active` when the application starts. Switching profiles and switching main classes are two separate responsibilities.

## 5. `finalName`: Local Filename Differs from Maven Coordinates

Maven defaults to naming a regular JAR as `artifactId-version.jar`. Suppose the POM declares:

~~~xml
<groupId>example.learning</groupId>
<artifactId>packaging-demo</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>
~~~

Without changing `finalName`, the local packaged file is normally:

~~~text
target/packaging-demo-1.0.0.jar
~~~

To set a shorter name:

~~~xml
<build>
    <finalName>demo-service</finalName>
</build>
~~~

The local packaged file will normally be:

~~~text
target/demo-service.jar
~~~

**Do not include `.jar` inside `finalName` just to specify the extension**: with JAR packaging, Maven plugins append the extension for the artifact type. Setting `finalName` to `demo-service.jar` risks producing `demo-service.jar.jar` or plugin-dependent behavior.

### 5.1. `finalName` Does Not Change GAV

Even when the local archive is named `target/demo-service.jar`, the Maven coordinates remain:

~~~text
example.learning:packaging-demo:1.0.0
~~~

`mvn install` installs the artifact under the repository layout based on `groupId/artifactId/version`, typically:

~~~text
~/.m2/repository/example/learning/packaging-demo/1.0.0/packaging-demo-1.0.0.jar
~~~

The actual local Maven repository path can be customized, and artifacts may carry classifiers. Do not use `finalName` to rename a module that downstream projects depend on. To change Maven identity, update the coordinates and assess downstream dependency impacts.

### 5.2. Classifiers Can Produce Multiple JARs

If you configure `spring-boot-maven-plugin`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>demo.Application</mainClass>
        <classifier>exec</classifier>
    </configuration>
</plugin>
~~~

alongside `finalName=demo-service`, the build can generate:

~~~text
target/demo-service.jar
target/demo-service-exec.jar
~~~

In this setup keeping a plain artifact next to an executable artifact, `-exec.jar` is the repackaged archive; `demo-service.jar` is the plain JAR. This means scripts using `target/*.jar` risk picking the wrong file. Never guess which archive is runnable solely from the extension: check the manifest or test running the exact deployment file.

Without a classifier, Spring Boot `repackage` replaces the main artifact with the executable archive by default, saving the original plain JAR with an `.original` suffix. The plugin also has an `attach` parameter affecting whether the repackaged artifact is attached during install/deploy. Use `classifier`/`attach` when artifact semantics differ, not merely to rename a local file.

## 6. Hands-On: A Runnable Spring Boot Executable JAR

The following standalone example uses **Java 17**, **Spring Boot 3.3.5**, and compatible Maven. It needs no web server or database. The goal is packaging `demo-service.jar`, confirming `mainClass=demo.Application`, and running it from the command line.

Create the structure:

~~~text
packaging-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          Application.java
~~~

### 6.1. Complete POM

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

    <groupId>example.learning</groupId>
    <artifactId>packaging-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <finalName>demo-service</finalName>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>demo.Application</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Notes:

- `spring-boot-starter-parent` supplies dependency management and Maven plugin management; because the example declares the Spring Boot plugin, `repackage` joins the `package` lifecycle via the parent.
- `spring-boot-starter` provides the core Spring Boot runtime **without** adding a servlet HTTP server.
- `java.version` sets a Java baseline compatible with Boot 3.3; a compatible JDK must still be installed.
- `finalName` sets the local filename to `demo-service.jar`.
- `mainClass` selects `demo.Application`.
- `<build><directory>` is omitted, so it uses Maven's default `target`.

### 6.2. Complete Java File

Place in `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CommandLineRunner printResult() {
        return args -> System.out.println("Demo packaged OK");
    }
}
~~~

`CommandLineRunner` executes once the application context initializes. Since the example has no web server or long-running background task, the process exits after printing the verification line.

### 6.3. Build and Run

In the directory containing `pom.xml`:

~~~bash
mvn clean package
java -jar target/demo-service.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

If the project has a Maven Wrapper, replace `mvn` with `./mvnw` on Linux/macOS or `.\mvnw.cmd` in Windows PowerShell.

With banner and root logging turned off via command-line arguments as above, the program prints the exact line:

~~~text
Demo packaged OK
~~~

Maven logs during `mvn clean package` are not the program's own stdout. If you do not see that line, inspect startup messages, the manifest, and the actual executable JAR path. **Do not invoke `javac` manually**: Maven compile manages the classpath with dependencies and plugins.

### 6.4. Inspecting the Packaged Archive

~~~bash
jar tf target/demo-service.jar
~~~

For a typical Spring Boot 3.3 executable JAR, the listing includes paths like:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/demo/Application.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

The `...` indicates abbreviated content, **not exact stdout** of `jar tf`. `jar tf` uses the JDK's `jar` tool to list archive contents.

If `unzip` is available on your machine, you can inspect the manifest:

~~~bash
unzip -p target/demo-service.jar META-INF/MANIFEST.MF
~~~

Check for `Start-Class: demo.Application` and the Boot launcher `Main-Class`. On Windows without `unzip`, use a ZIP viewer or extract the manifest to a temp folder. Running `java -jar` is the final test of executability.

## 7. Changing the Overall Output Directory

To place all module build outputs under `build-output` instead of `target`, update the POM:

~~~xml
<build>
    <directory>${project.basedir}/build-output</directory>
    <finalName>demo-service</finalName>
    <!-- Other plugin configurations of the project remain intact -->
</build>
~~~

This is an **illustrative fragment**, not a replacement for the entire `<build>` block in the complete POM. Once integrated into the full POM, the typical layout is:

~~~text
packaging-demo/
  pom.xml
  src/...
  build-output/
    classes/
    test-classes/
    demo-service.jar
    ...
~~~

Because `project.build.outputDirectory` defaults relative to `project.build.directory`, compiled classes generally move along with it. The `outputDirectory` parameter of `spring-boot:repackage` defaults to `project.build.directory`, so the repackaged archive goes into the new directory as well.

Rebuild and run from the new path:

~~~bash
mvn clean package
java -jar build-output/demo-service.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

The program output in the example remains:

~~~text
Demo packaged OK
~~~

**What must be updated when changing `directory`:** artifact paths in deployment scripts, Dockerfiles, pipeline upload/download steps, test commands, custom tooling, and test-report readers. `mvn clean` will also clean the configured build directory. Do not change the build directory merely to rename the output file: use `finalName` for that.

### 7.1. Changing Only the Compiled Classes Directory

This represents **a different intent**:

~~~xml
<build>
    <outputDirectory>${project.build.directory}/custom-classes</outputDirectory>
</build>
~~~

Normally `project.build.outputDirectory` points to `target/custom-classes` if the build directory is unchanged. Standard Maven plugins use this value to locate compiled classes, whereas scripts or custom plugins hardcoding `target/classes` can break.

Do not use this setting when the requirement is **"put the JAR in `build-output/`"**. It does not directly relocate the final JAR.

### 7.2. Changing Only the Output of Spring Boot `repackage`

Spring Boot Maven Plugin provides an `outputDirectory` parameter **on the `repackage` goal**. Example syntax:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>demo.Application</mainClass>
        <outputDirectory>${project.build.directory}/repackaged</outputDirectory>
    </configuration>
</plugin>
~~~

The intent here is directing where the **`repackage` goal** writes its archive, without altering the compiler's `project.build.outputDirectory`. Because packaging ties together source JAR creation, repackaging, attaching, and install/deploy, if you configure a plugin-specific output directory, **verify actual behavior on your plugin version**: check whether the source archive stays intact, where the repackaged file lands, which file gets installed/deployed, and whether CI scripts pick the right archive.

For typical projects, leave `repackage`'s `outputDirectory` at its default `project.build.directory`. If a pipeline wants a dedicated artifact publishing directory, copy the built file to a staging directory in the pipeline without changing Maven's compile/repackage paths.

## 8. Projects Without `spring-boot-starter-parent`

Some modules inherit a company-internal parent POM or another non-Boot parent. In those cases, there is **no default** `repackage` execution bound to `package` as in the starter-parent example.

Plugin configuration typically requires an explicit version and execution:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.5</version>
    <configuration>
        <mainClass>demo.Application</mainClass>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

This is a **fragment inside `<build><plugins>`**, not a complete POM. The project still needs Spring Boot dependencies, version management (such as importing the `spring-boot-dependencies` BOM), compatible JDK/compiler settings, and a valid main class. If multiple plugin executions run in `package`, inspect the effective POM and logs to verify ordering.

The `repackage` goal does not build a source JAR from source code. When running explicitly on a project without a bound execution, use:

~~~bash
mvn package spring-boot:repackage
~~~

This runs the `package` phase first and then invokes the goal. When the plugin execution is already bound, `mvn clean package` alone suffices. Never run standalone `mvn spring-boot:repackage` right after `clean` expecting it to compile and package the entire app.

## 9. Verifying Effective POM and Actual Paths

To see the merged Maven configuration after parent/inheritance/properties, run from the exact module:

~~~bash
mvn help:effective-pom
mvn help:evaluate -Dexpression=project.build.finalName -q -DforceStdout
mvn help:evaluate -Dexpression=project.build.directory -q -DforceStdout
mvn help:evaluate -Dexpression=project.build.outputDirectory -q -DforceStdout
mvn help:evaluate -Dexpression=project.build.testOutputDirectory -q -DforceStdout
~~~

Values printed by the Maven Help Plugin confirm build properties. However, `effective-pom` **does not prove** the JAR exists, was repackaged, or runs cleanly: inspect the actual artifact.

| Question | Evidence to Inspect |
| --- | --- |
| Which `finalName` is Maven using? | `help:evaluate` for `project.build.finalName` |
| Where is the actual build directory? | `help:evaluate` for `project.build.directory` |
| Where was Java code compiled? | `project.build.outputDirectory` and `.class` files on disk |
| Which phase is `repackage` bound to? | `help:effective-pom` and `mvn package` log |
| Where is the executable JAR? | Actual file after clean/package and classifier/output config |
| Which main class is in the archive? | `META-INF/MANIFEST.MF`, specifically `Start-Class` |
| Are runtime dependencies packaged? | Contents of `BOOT-INF/lib` in `jar tf` |
| Is the deliverable file runnable? | `java -jar` with the target JDK in the runtime environment |

For Linux/macOS:

~~~bash
ls -l target/demo-service.jar
jar tf target/demo-service.jar
java -jar target/demo-service.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

For Windows PowerShell:

~~~powershell
Get-Item .\target\demo-service.jar
jar tf .\target\demo-service.jar
java -jar .\target\demo-service.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

If you changed the build directory, replace `target` in the commands with the actual path. If using a classifier, specify the **exact executable filename**. Do not use a wildcard like `target/*.jar` without checking the listing: builds can contain plain JARs, executable JARs, and archives from other executions.

## 10. Relationship Between `mainClass` and Manifest Across Different Layouts

A `.jar` file is a ZIP archive with a manifest. Yet not every JAR with a `Main-Class` is a Spring Boot executable archive. The Spring Boot loader resolves nested dependencies inside `BOOT-INF/lib` according to the layout created by the Maven plugin.

- For executable **JAR**, production code is typically in `BOOT-INF/classes`, dependencies in `BOOT-INF/lib`, and the launcher is typically `JarLauncher`.
- For executable **WAR**, code and libraries follow `WEB-INF` layout, with a different launcher (such as `WarLauncher`) and different rules for provided dependencies.
- For custom layouts such as `ZIP` or `NONE`, packaging and startup differ. In particular, `NONE` provides no bootstrap launcher to self-execute like a standard executable JAR.

If the application must be deployed as a WAR to an external servlet container, changing `finalName` from `.jar` to `.war` is not enough. You must set `<packaging>war</packaging>` and configure the application and container properly.

`mainClass` on the Spring Boot Maven Plugin selects the application class; choosing a layout can change the launcher `Main-Class`, without changing your application code.

## 11. CI/CD, Multi-Module Maven, and Dockerfile

### 11.1. Scripts Depending on Filenames

Before changing `finalName`, a pipeline might reference:

~~~text
target/packaging-demo-1.0.0.jar
~~~

After changing it to `demo-service`, it must reference:

~~~text
target/demo-service.jar
~~~

Without cleaning, stale files can linger locally and cause scripts to run an old build. Good verification workflows therefore start from a clean workspace or `mvn clean package`, then **verify the exact file** before uploading and deploying.

### 11.2. Multi-Module Maven Reactor

A Maven parent/aggregator project might have:

~~~text
project/
  pom.xml
  api/
    pom.xml
    target/
  service/
    pom.xml
    target/
  shared/
    pom.xml
    target/
~~~

Each module has its own `target/` directory by default. If the `service` module sets `<finalName>demo-service</finalName>`, the file lives at `service/target/demo-service.jar`, not `target/demo-service.jar` at the aggregator root. CI paths must point to the exact module containing the Boot executable archive. Library modules generally do not need repackaging into executable JARs.

### 11.3. JAR Artifacts Differ from Container Images

`spring-boot:build-image` can build an OCI image using Buildpacks. Container image names and tags must be configured for the `build-image` goal and registry; `finalName` is not a general mechanism for naming/tagging container images. Likewise, changing the compiler's `outputDirectory` does not make a container image appear as a JAR in `target`.

## 12. Common Errors and Resolutions

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| `mvn package` passes green yet no file appears in `target/` | Build directory was changed or module does not produce a JAR | Check `project.build.directory`, packaging, and actual output |
| Artifact filename is wrong | `finalName` not taking effect or plugin uses a classifier | Print `project.build.finalName`, check generated filenames |
| `no main manifest attribute` on `java -jar` | Running plain JAR or `repackage` did not execute | Inspect effective POM, goal logs, and manifest of the exact file being run |
| `ClassNotFoundException` for application main | `mainClass` has wrong package, class not packaged, or wrong archive | Check FQCN, `BOOT-INF/classes`, and `Start-Class` |
| Two files `demo-service.jar` and `demo-service-exec.jar` exist | Classifier configuration keeps plain and repackaged artifacts separate | Check manifest/contents; pick the runnable archive |
| App runs via `spring-boot:run` but `java -jar` fails | Development classpath differs from archive, missing repackage, or missing runtime dependency | Check `package` lifecycle, `BOOT-INF/lib`, and startup logs |
| Set `<outputDirectory>dist</outputDirectory>` yet JAR stays in `target` | Changed compiled classes location, not archive directory | Use `<build><directory>` or an artifact copy step |
| JAR is not installed/deployed as expected | Classifier, `attach=false`, plugin-specific output, or plugin execution | Check `repackage` config, artifact attachment, and repository |
| Changing `directory` causes CI upload to miss the JAR | CI hardcoded the old `target` path | Update artifact paths in the pipeline |
| Build plugin reports source archive not found | `repackage` ran before `package` or broken execution | Run proper lifecycle; ensure jar plugin creates archive first |
| Maven install filename differs from local `finalName` | Coordinates still follow GAV | Understand repo layout by `groupId/artifactId/version` |
| Accidentally ran an old artifact after renaming | Workspace retained files from a previous build | Build cleanly, verify file hash/version and exact filename |

**Note on errors:** a `ClassNotFoundException` or `NoClassDefFoundError` can also stem from runtime classpath issues, binary incompatibility, or application configuration. Never diagnose a `mainClass` error from the exception name alone; combine manifest, archive inspection, and the full stack trace.

## 13. Verification Workflow After Changes

When modifying main class, filename, and build paths together, follow this order:

1. **Identify project and module:** building JAR, WAR, or multi-module? Using `spring-boot-starter-parent`?
2. **Verify main class:** check package, the [[public static void main(String[] args)]] signature, and deliverable target; set `<mainClass>` when pinning is needed.
3. **Set local filename:** use `<build><finalName>`, do not change `artifactId` just to rename a file.
4. **Set the right output setting:** use `<build><directory>` to move the build root, keep `<build><outputDirectory>` for compiled classes; change plugin `outputDirectory` only if you understand its full impact.
5. **Check lifecycle:** verify `spring-boot:repackage` is bound to `package` or invoked explicitly in proper order.
6. **Clean build:** run `mvn clean package`, never relying on stale files.
7. **Inspect:** confirm exact path/name, manifest, `BOOT-INF/classes`, and `BOOT-INF/lib`.
8. **Run:** run `java -jar` with the right JDK and environment, checking exit code and stdout.
9. **Update consumers:** Dockerfiles, CI artifact paths, deploy scripts, and launch commands must point to the exact file.
10. **Check repository artifacts when needed:** if running `mvn install`/`mvn deploy`, confirm GAV/classifier/attach match downstream consumer contracts.

### Knowledge Self-Check

**Question A.** A POM declares `artifactId=orders`, `version=2.1.0`, and `finalName=order-service`. Default build directory, JAR packaging. What is the typical local archive name?

**Answer:** `target/order-service.jar`, while Maven coordinates remain `orders:2.1.0`.

**Question B.** Does changing `<build><outputDirectory>` to `target/classes-v2` cause the JAR to be written into `target/classes-v2`?

**Answer:** No. That setting primarily moves compiled production classes and resources. The JAR location depends on the build directory and packaging plugins.

**Question C.** In an executable JAR, why is `Main-Class` usually not `demo.Application`?

**Answer:** The JVM needs the Spring Boot launcher to load libraries nested inside the archive; the application main class is typically recorded in `Start-Class`.

**Question D.** Why might `java -jar target/demo-service-exec.jar` succeed while `java -jar target/demo-service.jar` fails?

**Answer:** A `classifier=exec` setup creates a separate executable archive alongside the plain artifact; check each file's manifest and contents.

**Question E.** Does changing `finalName` rename the file in the Maven repository under a new `artifactId`?

**Answer:** No. The local package name is not Maven coordinates; `mvn install`/`deploy` resolves artifact paths by GAV, extension, and classifier.

## 14. Official References

- Maven POM Reference — `directory`, `outputDirectory`, `finalName`: https://maven.apache.org/pom.html
- Maven Standard Directory Layout: https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html
- Maven Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven Help Plugin — `effective-pom`: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Maven Help Plugin — `evaluate`: https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot — Executable JAR Format: https://docs.spring.io/spring-boot/specification/executable-jar/index.html

When an application uses an older or newer Spring Boot/Maven version than the examples, check the documentation **for that exact plugin version**, especially launcher class names, goal parameters, and `repackage` defaults.

**Memory aid:** `mainClass` selects the application class invoked by the launcher; `finalName` sets the base name of the local archive; `project.build.directory` sets the root build directory; `project.build.outputDirectory` sets where the compiler puts classes. Only by verifying **effective POM → artifact → manifest → `java -jar`** do you have complete evidence that packaging works as intended.