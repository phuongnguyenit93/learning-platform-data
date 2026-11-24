# Finding Why Resources Exist in the IDE Run Yet Are Missing in the JAR

A Spring Boot application may run normally inside IntelliJ IDEA, Eclipse, or VS Code yet report a missing file when executed via `java -jar app.jar`. The cause usually lies in the difference between **the classpath the IDE builds** and **the files Gradle/Maven actually packages into the JAR**.

In an IDE, resources may be read directly from source folders, generated folders, or a separately configured resource root. When packaging, the build tool includes only resources belonging to configured source sets/resource directories that pass include, exclude, filtering, copy, and packaging rules.

An effective diagnostic path checks each stage in order:

~~~text
Resource in project
       |
       v
Declared in main resource source set?
       |
       v
Gradle processResources / Maven process-resources
       |
       v
build/resources/main or target/classes
       |
       v
bootJar / package
       |
       v
BOOT-INF/classes/ inside executable Spring Boot JAR
       |
       v
ClassLoader / Spring Resource API when running java -jar
~~~

**Key principle:** finding a resource on the filesystem in the IDE does not prove the resource is inside the JAR. Inspect the actual artifact with `jar tf` and read resources via classpath APIs rather than relying on source paths like `src/main/resources/...` at runtime.

## 1. Distinguishing Resources, Source Code, and Classpath

### 1.1. Resources Are Data Read by the Application at Runtime

Resources can include:

- `application.properties` or `application.yml`.
- JSON/XML/YAML used as configuration or sample data.
- HTML templates, email templates, and localization files.
- Images, fonts, CSS, JavaScript, schema files, or public certificates.
- SQL migration scripts, message bundles, or seed data.
- Metadata such as `META-INF/services/...`.

Java sources (`.java`) are turned into class files (`.class`) by the compiler. Resources are not Java sources; the build tool copies/transforms them into the output directory and places them on the runtime classpath.

Common layout example:

~~~text
orders-api/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/orders/OrdersApplication.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── config/
│   │       │   └── pricing-rules.json
│   │       ├── templates/
│   │       │   └── receipt.html
│   │       └── static/
│   │           ├── app.css
│   │           └── logo.svg
│   └── test/
│       └── resources/
│           └── fixtures/orders.json
├── build.gradle
└── settings.gradle
~~~

`src/main/resources` is the default location for production/main source set resources in the Gradle Java plugin and standard Maven projects. `src/test/resources` belongs to the test classpath; it is not included by default in the production executable JAR.

### 1.2. The IDE May Be Adding Its Own Resource Directory

IDEs typically import Gradle/Maven configuration and mark resource roots. However, a project may also have manual configuration:

- A directory outside the project marked as Resources Root.
- An uncommitted or Git-ignored local folder.
- A generated directory created by the IDE before running.
- Another module added to the IDE classpath.
- A leftover file in an old output directory from an earlier build.

Therefore, succeeding inside the IDE may prove only that **the IDE runtime classpath contains that file**. A clean CI build or the packaged JAR might lack the file.

Always configure resources in Gradle/Maven so the IDE re-imports the exact source sets. Do not rely on a resource root that exists only in local IDE configuration.

### 1.3. Classpath Is Not the Working Directory

The classpath is the set of directories/JARs where the classloader searches for classes and resources. The working directory is the directory the process runs from, typically represented by `user.dir`.

Example:

~~~text
Working directory: /srv/orders
Classpath:
  /srv/orders/app.jar
  (nested dependencies via Spring Boot Loader)
~~~

A relative file like `config/pricing-rules.json` opened with `Files.readString(Path.of(...))` is looked up relative to the working directory. It is not automatically searched inside the JAR.

Conversely, `ClassLoader.getResource("config/pricing-rules.json")` searches for the resource on the classpath, regardless of which directory the JAR is launched from. These two access patterns address two different kinds of resources.

## 2. Where Does a Spring Boot Executable JAR Place Resources?

In a Spring Boot executable JAR, application classes and resources sit in `BOOT-INF/classes`; dependencies sit in `BOOT-INF/lib`.

~~~text
orders-api.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
└── BOOT-INF/
    ├── classes/
    │   ├── application.yml
    │   ├── config/pricing-rules.json
    │   ├── templates/receipt.html
    │   ├── static/app.css
    │   └── com/example/orders/OrdersApplication.class
    └── lib/
        ├── spring-boot-*.jar
        └── other-dependency.jar
~~~

This is an illustrative layout. Actual files depend on artifact, plugin version, and project contents. Spring Boot Loader knows how to put `BOOT-INF/classes` and nested dependency JARs onto the runtime classpath when running the executable archive. <Link ref="turn698805search1" title="Spring Boot: Nested JARs"/>.

**Do not prepend `BOOT-INF/classes/` to resource lookups in Java code.** That is the physical location inside the executable archive. Applications still request resources by classpath-relative name:

~~~java
Resource resource = new ClassPathResource("config/pricing-rules.json");
~~~

or:

~~~java
InputStream input = getClass()
        .getClassLoader()
        .getResourceAsStream("config/pricing-rules.json");
~~~

### 2.1. Plain JARs vs. Executable Spring Boot JARs

A regular Java JAR places classes/resources at the root:

~~~text
library.jar
├── com/example/SomeClass.class
└── config/library.properties
~~~

An executable Spring Boot JAR places application classes/resources under `BOOT-INF/classes` and nested dependencies under `BOOT-INF/lib`. Do not write code that opens the outer JAR directly and looks for `config/...` at the root when the resource actually lives at `BOOT-INF/classes/config/...`.

When reading resources, use classpath APIs so Spring Boot Loader handles the layout. When verifying packaging placement, use `jar tf` to inspect archive entries.

### 2.2. Executable WAR

In an executable WAR, application classes/resources normally reside under `WEB-INF/classes`; dependencies reside in `WEB-INF/lib` and potentially `WEB-INF/lib-provided`. When deployed to a servlet container, how the container handles the WAR and classloaders can differ from running the standalone executable WAR. <Link ref="turn698805search1" title="Spring Boot executable JAR and WAR layout"/>.

## 3. Loading Resources Properly in Java

### 3.1. Using `ClassLoader.getResourceAsStream`

For a resource relative to the classpath root:

~~~java
InputStream input = getClass()
        .getClassLoader()
        .getResourceAsStream("config/pricing-rules.json");
~~~

Names passed to `ClassLoader`:

- Use forward slashes `/` as separators.
- Do not start with a leading slash.
- Are resolved from the classpath root.
- Must match the exact letter casing of the entry in the JAR.

If the resource does not exist, the method returns `null`. Always check and report errors with the specific resource name.

### 3.2. Using `Class.getResourceAsStream`

With `Class`, paths have two forms:

~~~java
// Absolute from classpath root:
InputStream rootResource =
        OrdersApplication.class.getResourceAsStream(
                "/config/pricing-rules.json");

// Relative to the class's package:
InputStream packageResource =
        OrdersApplication.class.getResourceAsStream(
                "defaults.json");
~~~

If the class is in `com.example.orders`, the relative path `defaults.json` is looked up at `com/example/orders/defaults.json`. A leading slash starts the lookup from the root. This is a common pitfall when switching code from `ClassLoader` to `Class` while keeping the same path string.

The JDK specifies resource names as `/`-separated paths and `getResourceAsStream` returns `null` if the resource cannot be found or accessed. <Link ref="turn698805search0" title="Java 17 ClassLoader API"/>.

### 3.3. Complete Example: Java 17 Resource Probe

This program checks whether a resource is present on the runtime classpath and reads its content as a stream. It runs standalone without Spring.

Structure:

~~~text
resource-probe/
├── src/main/java/com/example/resourceprobe/ResourceProbe.java
└── src/main/resources/config/app.properties
~~~

File `src/main/resources/config/app.properties`:

~~~properties
app.name=resource-demo
app.mode=packaged
~~~

File `src/main/java/com/example/resourceprobe/ResourceProbe.java`:

~~~java
package com.example.resourceprobe;

import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public final class ResourceProbe {

    private static final String RESOURCE =
            "config/app.properties";

    private ResourceProbe() {
    }

    public static void main(String[] args) throws IOException {
        ClassLoader loader =
                ResourceProbe.class.getClassLoader();

        URL location = loader.getResource(RESOURCE);
        System.out.println("RESOURCE_URL_FOUND=" +
                (location != null));

        if (location == null) {
            System.err.println(
                    "RESOURCE_MISSING=" + RESOURCE);
            System.exit(1);
            return;
        }

        try (InputStream input =
                     loader.getResourceAsStream(RESOURCE)) {
            if (input == null) {
                System.err.println(
                        "RESOURCE_STREAM_MISSING=" + RESOURCE);
                System.exit(1);
                return;
            }

            String content = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8);

            String normalized = content
                    .replace("\r\n", "\n")
                    .replace('\r', '\n')
                    .strip()
                    .replace("\n", ";");

            System.out.println(
                    "RESOURCE_CONTENT=" + normalized);
        }
    }
}
~~~

Compile and run directly with JDK 17 on Linux/macOS:

~~~bash
mkdir -p out
javac -d out src/main/java/com/example/resourceprobe/ResourceProbe.java
cp -R src/main/resources/. out/
java -cp out com.example.resourceprobe.ResourceProbe
~~~

On PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out .\src\main\java\com\example\resourceprobe\ResourceProbe.java
Copy-Item -Recurse .\src\main\resources\* .\out\
java -cp out com.example.resourceprobe.ResourceProbe
~~~

Stdout when the resource exists:

~~~text
RESOURCE_URL_FOUND=true
RESOURCE_CONTENT=app.name=resource-demo;app.mode=packaged
~~~

If the file is missing, the program prints:

~~~text
RESOURCE_URL_FOUND=false
~~~

and exits with code 1. If the resource exists yet the stream cannot open, the program reports `RESOURCE_STREAM_MISSING`. The example reads bytes via `InputStream` and therefore does not assume the resource is a physical file on disk.

### 3.4. Using Spring `ClassPathResource`

In a Spring application, you can use:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;

public class PricingRulesReader {

    public String read() throws IOException {
        ClassPathResource resource =
                new ClassPathResource(
                        "config/pricing-rules.json");

        if (!resource.exists()) {
            throw new IllegalStateException(
                    "Missing classpath resource: " +
                    "config/pricing-rules.json");
        }

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
~~~

`ClassPathResource` uses the specified classloader or class to locate the resource. It supports streams and URLs. However, a resource inside an unexploded JAR **cannot necessarily be resolved to a `java.io.File`**. Spring docs clearly note that `getFile()` is only appropriate when the resource actually resides on the filesystem; for resources inside a JAR, use `getInputStream()` or URLs. <Link ref="turn388927search0" title="Spring Framework Resource abstraction"/>.

### 3.5. Do Not Use Source Paths in Production Code

Here is a pattern that works easily in an IDE yet usually fails when running the JAR:

~~~java
Path path = Path.of(
        "src/main/resources/config/app.properties");
String content = Files.readString(path);
~~~

This path only resolves to a file in the project working directory if that folder happens to exist. Once only the JAR is delivered to a server, the source tree does not necessarily exist.

If the data belongs as a packaged resource, use classpath APIs. If the data must be managed externally (e.g., environment-specific config files, uploads, or large data), use an explicitly configured filesystem path, volume mount, or external configuration.

## 4. Gradle: How Do Resources Flow Through `processResources`?

The Gradle Java plugin creates the `main` source set and the `processResources` task. By default, the task copies resources from `src/main/resources` to `build/resources/main`. Outputs are included on the main runtime classpath and in JAR packaging. For other source sets, the task is named `process<SourceSet>Resources`. <Link ref="turn698805search2" title="Gradle Java projects: Managing resources"/>.

~~~text
src/main/resources/
        |
        v
  processResources
        |
        v
build/resources/main/
        |
        +----> test/runtime classpath
        |
        +----> bootJar
                    |
                    v
          BOOT-INF/classes/
~~~

### 4.1. Inspect Resource Output Before Packaging

Linux/macOS:

~~~bash
./gradlew clean processResources
find build/resources/main -type f
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean processResources
Get-ChildItem -Recurse .\build\resources\main
~~~

If the resource is missing from `build/resources/main`, the issue lies before or inside `processResources`: source directory, source set, include/exclude, generated resources, or task ordering.

If the file exists in output yet is missing from the JAR, inspect packaging steps, `bootJar`/`jar` configuration, custom tasks, and the actual archive file.

### 4.2. Declaring Additional Resource Directories

If resources live in a separate folder, declare it in the source set:

~~~groovy
sourceSets {
    main {
        resources {
            srcDir 'src/main/config-resources'
        }
    }
}
~~~

Gradle will now include resources from both the default directory and the additional directory in main resource output. Avoid configuring folders only in the IDE; the Gradle build must know about them.

### 4.3. Include and Exclude Patterns Can Drop Resources

Example configuration:

~~~groovy
tasks.named('processResources') {
    exclude '**/*.bak'
    exclude 'local-only/**'
}
~~~

If a needed resource accidentally matches an exclude pattern, it will not be copied. When include patterns are present, only files matching an include enter the output.

`ProcessResources` supports `includes` and `excludes` properties; inspect all build script configuration, convention plugins, and parent build logic. <Link ref="turn388927search1" title="Gradle ProcessResources API"/>.

### 4.4. Resources Generated During the Build

If the IDE generates a file before running, yet Gradle does not generate it in the task graph, the JAR will miss the resource. Register the output directory and task dependency explicitly.

Illustrative example:

~~~groovy
def generatedResourcesDir =
        layout.buildDirectory.dir(
                'generated/resources/main')

tasks.register('generateAppResources', Copy) {
    from 'src/resource-templates'
    into generatedResourcesDir
}

sourceSets {
    main {
        resources {
            srcDir generatedResourcesDir
        }
    }
}

tasks.named('processResources') {
    dependsOn tasks.named('generateAppResources')
}
~~~

This example illustrates copying template files into generated resources. If content must be generated dynamically, replace `Copy` with an appropriate task and declare outputs using Gradle Providers so Gradle understands the dependency graph. Do not write generated files directly into `src/main/resources` during the build.

### 4.5. Filtering in Gradle

Gradle `Copy`/`ProcessResources` can transform text resources with `expand` or filters. If the build script substitutes placeholders using project properties, the packaged file may differ from the file seen in the IDE.

Example:

~~~groovy
tasks.named('processResources') {
    filesMatching('build-info.properties') {
        expand(version: project.version)
    }
}
~~~

Use filtering only on text files designed with placeholders. Never apply filtering to images, fonts, PDFs, binaries, or compressed files; their contents can be corrupted. Be careful with Spring's dollar-brace placeholders: if Gradle filtering recognizes the same delimiter, the build may substitute values or fail before Spring runtime processes them.

## 5. Maven: Resources from `src/main/resources` to `target/classes`

The Maven Resources Plugin runs in the `process-resources` phase of the default lifecycle. Under standard configuration, resources are copied from `src/main/resources` to `target/classes`; JAR/WAR packaging then puts them into the archive.

~~~text
src/main/resources/
        |
        v
maven-resources-plugin
        |
        v
target/classes/
        |
        v
maven-jar-plugin / spring-boot-maven-plugin
        |
        v
Executable Boot JAR
        |
        v
BOOT-INF/classes/
~~~

### 5.1. Inspecting Maven Output

~~~bash
mvn clean process-resources
find target/classes -type f
~~~

PowerShell:

~~~powershell
mvn clean process-resources
Get-ChildItem -Recurse .\target\classes
~~~

If the file is missing from `target/classes`, check `<resources>`, resource directories, includes/excludes, filtering, and lifecycle executions.

### 5.2. Overriding `<resources>` Can Drop the Default Folder

When a POM declares `<build><resources>`, that list dictates which resource directories are used. If you declare only a custom folder and forget `src/main/resources`, default resources may disappear from the output.

Explicit declaration example:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
        <resource>
            <directory>src/main/config-resources</directory>
            <filtering>false</filtering>
        </resource>
    </resources>
</build>
~~~

This configuration applies when both folders must be packaged. Do not add a source directory merely so the IDE sees a file; determine which module/variant truly owns the resource.

### 5.3. Include and Exclude

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
            <excludes>
                <exclude>**/*.bak</exclude>
                <exclude>local-only/**</exclude>
            </excludes>
        </resource>
    </resources>
</build>
~~~

Check `<includes>`, `<excludes>`, and Maven Resources Plugin executions. Any file matching an exclude will be absent from `target/classes`. Maven documentation provides official examples for including and excluding resource files. <Link ref="turn698805search4" title="Maven Resources Plugin: Include and Exclude"/>.

### 5.4. Filtering in Maven

Maven resource filtering replaces dollar-brace placeholders (such as variable `name`) or `@name@` with project/system/filter properties. Resource filtering is off by default; when enabled, the output text file may differ from the source file. <Link ref="turn698805search6" title="Maven: Filtering Resources"/>.

Do not filter binary files such as images, PDFs, or fonts; Maven warns this can corrupt their contents. If text filtering is needed, separate filtered and non-filtered folders:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
        <resource>
            <directory>src/main/resources-filtered</directory>
            <filtering>true</filtering>
            <includes>
                <include>**/*.properties</include>
                <include>**/*.yml</include>
            </includes>
        </resource>
    </resources>
</build>
~~~

If `application.yml` contains Spring placeholders (such as environment variable `DATABASE_URL` in dollar-brace syntax), check filtering delimiters so they stay intact for Spring to resolve at runtime. Never bake environment-specific database URLs/secrets into the artifact.

## 6. Inspecting the Actual JAR, Not Just Build Output

### 6.1. List JAR Contents

With Gradle:

~~~bash
./gradlew clean bootJar
jar tf build/libs/orders-api.jar
~~~

With Maven:

~~~bash
mvn clean package
jar tf target/orders-api.jar
~~~

The filename may include a version, e.g., `orders-api-1.8.0.jar`; use the actual output filename.

In the executable Spring Boot JAR, look for:

~~~text
BOOT-INF/classes/application.yml
BOOT-INF/classes/config/pricing-rules.json
BOOT-INF/classes/static/app.css
BOOT-INF/classes/templates/receipt.html
~~~

If the resource is absent from `jar tf` output, the classloader cannot find it from that JAR. Go back and inspect source sets/`processResources` or packaging.

### 6.2. Find a Specific Resource

Linux/macOS:

~~~bash
jar tf build/libs/orders-api.jar | grep 'pricing-rules.json'
~~~

Windows PowerShell:

~~~powershell
jar tf .\build\libs\orders-api.jar | Select-String 'pricing-rules.json'
~~~

Expected result for a Boot JAR:

~~~text
BOOT-INF/classes/config/pricing-rules.json
~~~

If no line matches, the resource was not packaged. If multiple lines share the same name, duplicate resources may exist in the application and a dependency JAR; inspect classloader resolution.

### 6.3. Read Resource Content from the JAR to Compare

Use JDK tools or an appropriate ZIP utility to inspect. For an executable Boot JAR, application resources reside under `BOOT-INF/classes`:

~~~bash
unzip -p build/libs/orders-api.jar BOOT-INF/classes/config/pricing-rules.json
~~~

This command only reads entries from the outer archive. Do not pass the classpath-root path `config/...` to `unzip -p` when the file actually lives inside `BOOT-INF/classes/config/...`.

If the resource lives inside a nested dependency JAR under `BOOT-INF/lib`, open that specific nested JAR to inspect the entry. Do not confuse an application resource with a resource supplied by a library.

### 6.4. Comparing IDE, Build Output, and JAR

| Check Point | Resource Exists? | Conclusion |
| --- | --- | --- |
| Project source directory | Yes | File exists in the workspace |
| IDE runtime classpath | Yes | IDE knows the resource root or has an output file |
| Gradle `build/resources/main` / Maven `target/classes` | Yes | Resource processing copied the file |
| `BOOT-INF/classes/` inside JAR | Yes | Resource is packaged in the application archive |
| Runtime `getResourceAsStream` | Yes | Classloader finds and opens the resource |

Pinpointing the failing stage:

- Exists in source, missing from IDE classpath: IDE/module/source root config.
- Exists in IDE, missing from Gradle/Maven output: build configuration, generator task, includes/excludes, or resource folder.
- Exists in build output, missing from JAR: packaging task or custom archive configuration.
- Exists in JAR, lookup returns null: wrong resource path, wrong letter casing, classloader/module, or running the wrong JAR.
- Lookup succeeds, parsing fails: encoding, filtering contents, or parser/configuration—not a missing file error.

## 7. Common Reasons the IDE Works While the JAR Misses Resources

### 7.1. Resource Placed in the Wrong Source Set

`src/test/resources` is only for the test runtime classpath. If production code reads a fixture stored there, tests may pass while the production JAR lacks the file.

**Fix:** move production resources to `src/main/resources` or declare an appropriate source set if it belongs to integration tests/custom distributions.

### 7.2. Custom Folder Configured Only in the IDE

The IDE might mark `config-data/` as a Resources Root while Gradle/Maven knows nothing about that folder.

**Fix:** add it to `sourceSets.main.resources` or `<build><resources>`, then verify the output directory again.

### 7.3. Uncommitted or Ignored Local Files

A developer has `local.properties` locally so the IDE reads it, yet a clean CI checkout lacks it. Another case is a file excluded by `.gitignore`.

Check:

~~~bash
git status --short
git ls-files src/main/resources
git check-ignore -v src/main/resources/config/local.properties
~~~

`git check-ignore` helps when suspecting an ignored file. Do not package local secrets into the JAR to fix the error; provide secrets via a runtime secret store.

### 7.4. Include/Exclude Accidentally Filters It Out

Patterns like `**/*.json` or `**/config/**` may be excluded by configuration in a parent Gradle convention plugin or Maven POM. Read all configuration applied to the module, not just the root build file.

**Fix:** narrow excludes, add accurate includes, or separate filtered folders from untouched folders.

### 7.5. Generated Resource Does Not Run in CI

An IDE plugin or manual step generated the file, yet the generator task is not wired into `processResources`/the Maven lifecycle.

**Fix:** declare task outputs and dependencies explicitly. Run a clean build to confirm the file regenerates from committed sources/inputs.

### 7.6. Letter Casing Mismatch in Resource Path

Windows filesystems are typically case-insensitive by default; Linux filesystems are typically case-sensitive. For example, the real file is:

~~~text
config/PricingRules.json
~~~

but the code looks up:

~~~java
getResourceAsStream("config/pricingrules.json")
~~~

**Fix:** standardize filenames and resource strings, and verify via `jar tf` in Linux CI.

### 7.7. Using Filesystem Paths for Classpath Resources

~~~java
new File("src/main/resources/config/app.properties")
~~~

This relies on the working directory and source tree. When only the JAR is deployed to a server, the source tree is absent.

**Fix:** use `ClassLoader`/`ClassPathResource`. If the file must live outside the JAR for independent administration, configure an explicit filesystem path and mount/copy the file into the runtime environment.

### 7.8. Resource Corrupted by Filtering or Encoding

The resource may exist, yet placeholders were wrongly substituted, text encoding changed, line endings differed, or filtering corrupted a binary file. Specifically check Maven `<filtering>true</filtering>`, Gradle `expand`, and delimiters colliding with Spring placeholders.

**Fix:** filter only required text, keep binary resources in non-filtered folders, specify charsets explicitly, and inspect bytes/contents after packaging.

### 7.9. Running an Old JAR by Mistake

The IDE runs fresh classes/resources from the output directory, while the command line launches a stale JAR from another directory.

Check the absolute path and timestamp/hash of the running file. Run a clean build and launch the exact output just produced:

~~~bash
./gradlew clean bootJar
java -jar build/libs/orders-api-1.8.0.jar
~~~

Do not assume a file named `app.jar` is always the latest artifact; verify the exact path.

### 7.10. Resource Lives in Another Dependency Module

A library module may contain `config/defaults.json` in its own JAR. That resource is found via the dependency classpath if the dependency is present at the right version. However, it is not automatically copied into the application's `BOOT-INF/classes`; it resides inside the nested dependency JAR under `BOOT-INF/lib`.

**Fix:** verify the dependency is inside the final archive and look it up via the classloader. If multiple JARs contain the same resource name, results can depend on classloader delegation/order; use namespaced resource paths like `com/example/pricing/defaults.json`.

### 7.11. Confusing Resource Files with Spring Static Content or Templates

Spring Boot serves static content by default from classpath locations such as `/static`, `/public`, `/resources`, and `/META-INF/resources`, depending on configuration/version. Placing a file in an arbitrary folder does not automatically create an HTTP route for it.

Templates in `templates/` are rendered only if the app has a matching template engine and proper configuration. A file may already be in the JAR yet the controller/view resolver cannot find or render it. Separate the question **“is the resource packaged?”** from **“is the framework configured to handle it as expected?”**.

### 7.12. Duplicate Resources

Two dependencies may both contain `META-INF/services/...` or the same config filename. For service providers, `ServiceLoader` can read multiple entries; for a single-resource lookup, the classloader returns one resource according to its delegation/search behavior.

Use `ClassLoader.getResources(name)` to list all matching resources and pinpoint their origins. Do not use a generic resource name like `config.json` across multiple modules if contents can conflict.

## 8. Multi-Module Projects and Custom Source Sets

In a Gradle multi-project build:

~~~text
root/
├── settings.gradle
├── app/
│   └── src/main/resources/application.yml
└── pricing/
    └── src/main/resources/com/example/pricing/defaults.json
~~~

`app` may depend on `pricing`. Resources in a library module are packaged into that module's JAR, not automatically copied into `app/build/resources/main`. When `app` consumes the dependency JAR, the classloader can find the resource via the dependency classpath if the dependency is properly packaged.

Inspect both artifacts:

~~~bash
./gradlew :pricing:jar :app:bootJar
jar tf pricing/build/libs/pricing.jar
jar tf app/build/libs/app.jar
~~~

In the executable Boot JAR, inspect both `BOOT-INF/classes` and `BOOT-INF/lib`. A dependency JAR under `BOOT-INF/lib` is a nested archive; inspect that nested entry separately if the resource belongs there.

### Custom Source Sets

For example, `integrationTest` has its own resources. They belong to the integration test classpath, not production `main` by default. Do not move test fixtures into production just to silence a lookup error; identify the right consumer and source set.

## 9. Automatically Catching Resource Errors in CI

Errors that appear only when running the JAR can slip past unit tests if tests run directly against build output directories. Add post-packaging checks for that reason.

### 9.1. Smoke-Test the Packaged Artifact

Minimal workflow:

1. Clean build.
2. Run unit/integration tests.
3. Build the executable JAR.
4. Verify required resources inside the JAR.
5. Run the exact JAR in a smoke test.
6. Send a request/check output and fail if a resource is missing.

Shell check example for an entry:

~~~bash
set -eu

./gradlew clean test bootJar

JAR="build/libs/orders-api-1.8.0.jar"

jar tf "$JAR" | grep -Fx \
  "BOOT-INF/classes/config/pricing-rules.json"

java -jar "$JAR" --spring.main.web-application-type=none
~~~

The final command is only an example for apps with a matching startup mode; a real web service may need background startup, readiness probes, and endpoint smoke tests instead of exiting immediately. Do not treat that command as a complete test if the app needs a database or external services.

### 9.2. Testing Resources with Java

You can place `ResourceProbe` in tests or a smoke-test module and run it with the **actual artifact's runtime classpath**. For a Spring Boot executable JAR, the simplest approach is starting the app and calling a health/test endpoint that verifies the resource, or writing a test using `java -jar`/a container process to mimic deployment.

Running JUnit tests against `build/classes/java/main` and `build/resources/main` is useful, yet insufficient to prove the nested executable JAR has the right layout. Include at least one check directly against the artifact.

### 9.3. Mandatory Checks for Critical Resources

For resources without which the application cannot function (e.g., schemas, mappings, or public certificates), write an assertion test:

~~~java
assertNotNull(
        getClass().getClassLoader()
                .getResource("config/pricing-rules.json"),
        "pricing-rules.json must be packaged");
~~~

This is a **test snippet**, not a standalone program. If the resource is a private config/secret, do not package it; test runtime secret mounts/configs separately.

## 10. Step-by-Step Diagnostic Workflow

When encountering `FileNotFoundException` or `getResourceAsStream() returns null` after packaging, follow this order:

### Step 1 — Record the Exact Resource Name

Example:

~~~text
config/pricing-rules.json
~~~

Check whether code uses `ClassLoader` or `Class`, whether there is a leading slash, and whether there is a wrong package-relative path.

### Step 2 — Check Source Files and Git

~~~bash
git status --short
git ls-files src/main/resources
~~~

Confirm the file exists in a clean checkout, has the right casing, and belongs to the module being built.

### Step 3 — Check Resource Processing

Gradle:

~~~bash
./gradlew clean processResources
find build/resources/main -type f
~~~

Maven:

~~~bash
mvn clean process-resources
find target/classes -type f
~~~

If missing here, fix source sets/resources/includes/excludes/filtering/generator tasks first.

### Step 4 — Inspect the JAR

~~~bash
jar tf build/libs/orders-api-1.8.0.jar
~~~

Look for entry `BOOT-INF/classes/config/pricing-rules.json`. If present in build output yet missing from the JAR, check packaging customizations and archive tasks.

### Step 5 — Run the Exact Artifact

~~~bash
java -jar build/libs/orders-api-1.8.0.jar
~~~

Do not run from the IDE or `bootRun` and treat it as the same environment. `java -jar` tests the executable archive you plan to release.

### Step 6 — Check Runtime Configuration

If the resource is read from the filesystem/external config, print the working directory and resolved path, and verify volumes/mounts/permissions. If it is a classpath resource, log the resource URL (never log secret contents) and verify the classloader.

### Step 7 — Check Environment Differences

Compare IDE, local clean build, Linux CI, container filesystem, working directory, user permissions, case sensitivity, Java version, and artifact digest. Run the exact same verified JAR to isolate the cause.

## 11. Symptom and Resolution Table

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Works in IDE, `java -jar` cannot find resource | IDE has custom resource root or source path used directly | Put resource in main source set and use classpath APIs |
| Missing from `build/resources/main` | Wrong source directory, include/exclude, generator task | Fix `sourceSets` and `processResources` |
| Present in `build/resources/main`, missing in Boot JAR | Custom `bootJar`/packaging rule | Check `jar tf` and archive task |
| Fails only on Linux CI | Case mismatch or ignored local file | Check Git tracked files and exact entry path |
| Resource in `src/test/resources` | Belongs only to test runtime classpath | Move production resource to main if appropriate |
| `getResourceAsStream` returns null | Wrong slash, wrong path, or resource not on classpath | Distinguish `ClassLoader` and `Class` lookups |
| `FileNotFoundException` with `new File` | Path depends on working directory/source tree | Use classpath stream or explicit external path |
| `getFile()` fails when running JAR | Resource is inside JAR, not a filesystem `File` | Use `getInputStream()` or URL |
| JSON/YAML parse error | Filtering, encoding, or altered content | Read bytes from JAR, diff source/output, set charset |
| Image/font/PDF corrupted | Binary resource was filtered | Separate binaries from filtered resources |
| File generated in IDE, missing in CI | Generator task not wired into Gradle/Maven lifecycle | Register task dependency and output directory |
| App module cannot see library resource | Dependency absent from runtime archive or wrong lookup | Check `BOOT-INF/lib` and dependency graph |
| Resource returns unexpected content | Duplicate name across multiple JARs | Use `getResources()` and namespace resources |
| Static URL returns 404 despite file in JAR | Wrong static location or path mapping | Check static resource locations and servlet mappings |
| Template does not render | Missing template engine or wrong resolver/config | Check dependencies and view resolver |
| Runs locally, fails in container | Stale JAR, different mount/permissions/working directory | Check digest, image, mounts, and runtime logs |

## 12. Pre-Release Checklist

- [ ] Production resources live in `src/main/resources` or an explicitly declared source directory.
- [ ] Resources do not exist solely on a developer's machine/IDE.
- [ ] Files are committed or generated by a task with explicit dependencies.
- [ ] Resources are not mistakenly placed in `src/test/resources`.
- [ ] Gradle `processResources` or Maven `process-resources` copies the right files.
- [ ] Include/exclude patterns do not drop needed resources.
- [ ] Filtering applies only to required text files, never binaries.
- [ ] Spring runtime placeholders are not unintentionally altered by build filtering.
- [ ] Resource paths use proper slashes and casing.
- [ ] Code uses classpath APIs for packaged resources.
- [ ] Code does not assume classpath resources are always `java.io.File`.
- [ ] `jar tf` confirms the entry exists inside the executable archive.
- [ ] Smoke test runs the exact JAR after a clean build.
- [ ] CI runs on a case-sensitive filesystem when appropriate.
- [ ] The tested artifact is the exact artifact to publish/deploy, identified by checksum/digest.

## 13. Self-Check Questions

**Question 1.** Why does an application run in the IDE yet miss resources when running the JAR?

**Answer:** The IDE may add resource roots or output directories that Gradle/Maven does not package. Check the main resource source set, `processResources`, and JAR contents.

**Question 2.** Where does the Gradle Java plugin copy resources by default?

**Answer:** From `src/main/resources` via `processResources` to `build/resources/main`, whose outputs enter the runtime classpath/JAR.

**Question 3.** How does Maven handle production resources by default?

**Answer:** The Maven Resources Plugin copies `src/main/resources` to `target/classes` during `process-resources`; packaging puts them into the JAR/WAR.

**Question 4.** Where do application resources reside inside a Spring Boot executable JAR?

**Answer:** Under `BOOT-INF/classes`; dependencies reside in `BOOT-INF/lib`.

**Question 5.** Does `ClassLoader.getResourceAsStream("config/app.properties")` need a leading slash?

**Answer:** No. `ClassLoader` takes paths relative to the classpath root without a leading slash. `Class.getResourceAsStream("/config/app.properties")` uses a leading slash to mean the root.

**Question 6.** Why is `new File("src/main/resources/app.properties")` usually wrong in production?

**Answer:** It depends on the working directory and source tree. When deploying only the JAR, the source folder may not exist.

**Question 7.** Can `Resource.getFile()` be used for every classpath resource?

**Answer:** No. A resource inside a JAR is not necessarily a filesystem file. Use `getInputStream()` or URLs.

**Question 8.** Why should images/fonts/PDFs not be filtered?

**Answer:** Filtering can alter bytes and corrupt binary resources. Only filter text files designed with placeholders.

**Question 9.** Why might Windows work while Linux CI reports a missing resource?

**Answer:** Letter casing mismatch in the path or an uncommitted/ignored local file. Inspect the exact entry with `jar tf`.

**Question 10.** Does running unit tests against Gradle class directories prove the executable JAR has all resources?

**Answer:** No. Inspect the archive with `jar tf` and run a smoke test with the exact JAR to be released.

## 14. Official Documentation

- Oracle Java 17 — [ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): resource lookup, `getResource`, `getResourceAsStream`, and classloader behavior.
- Spring Boot — [Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html): executable JAR/WAR layout, `BOOT-INF/classes`, and `BOOT-INF/lib`.
- Spring Framework — [Resources](https://docs.spring.io/spring-framework/reference/core/resources.html): `Resource`, `ClassPathResource`, `FileSystemResource`, stream, and URL access.
- Gradle — [Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): source sets, `processResources`, and resource directories.
- Gradle — [ProcessResources API](https://docs.gradle.org/current/dsl/org.gradle.language.jvm.tasks.ProcessResources.html): include, exclude, filtering, and copy behavior.
- Apache Maven — [Maven Resources Plugin: Include and Exclude](https://maven.apache.org/plugins/maven-resources-plugin/examples/include-exclude.html): configuring resource selection and exclusion.
- Apache Maven — [Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html): resource filtering, delimiters, and binary resource warnings.

**Remember:** The IDE runtime classpath is not proof that a resource was packaged. Trace the file from source directory through `processResources`/`process-resources`, verify its entry inside `BOOT-INF/classes` with `jar tf`, and read it via a classpath stream when running the executable JAR. If the file lives inside a JAR, treat it as a **classpath resource**, not as a file path on disk.