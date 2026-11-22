# Packaging an Annotation Library and an Annotation Processor and Using Them from Another Project

The goal of this hands-on practice is to build **two JAR libraries with separate responsibilities**, and then use them from an independent Java project: one JAR provides the annotation for application source code to import; the other JAR contains the annotation processor that runs during compilation to generate Java code. After this lesson, you will be able to package, publish, configure, and test a processor as a reusable library, instead of only running the processor inside the same project that creates it.

The example uses **Java 17+**, the `@AutoGreeting` annotation, the `GreetingProcessor` processor, and the `App` application. When the compiler encounters `@AutoGreeting` on the `App` class, the processor generates `demo.consumer.AppGreeting`. The application calls `AppGreeting.text()` and prints `Hello from generated source`.

## 1. Three-Project Architecture and Compilation Paths

```text
annotation-api/                              # API library imported by users
  src/main/java/demo/api/AutoGreeting.java
greeting-processor/                          # Processor library, compiled before the application
  src/main/java/demo/processor/GreetingProcessor.java
  src/main/resources/META-INF/services/
    javax.annotation.processing.Processor
consumer/                                    # Independent application project using the two JARs
  src/main/java/demo/consumer/App.java
```

Dependency relationships:

```text
consumer source ──compile classpath──> annotation-api.jar
                                            ^
                                            | processor also needs the annotation definition
compiler ──processor path──> greeting-processor.jar + annotation-api.jar
                                            |
                                            v
                          GreetingProcessor is loaded in javac
                                            |
                               generates AppGreeting.java
                                            |
                         javac compiles into AppGreeting.class
```

**Separating the API and the processor** is very useful: application code needs the annotation API at compile time but does not necessarily need the processor classes at runtime. The processor is a **compile-time** tool; in this scenario, the processor JAR is not a runtime dependency of the application. Publishing the annotation API library independently allows consumer projects to import the annotation without pulling the compiler extension into runtime.

Clearly distinguish these three concepts:

| Component | Function | Placement |
| --- | --- | --- |
| Annotation API | Declares `@AutoGreeting`, the part that application code references | Compile classpath of the consumer; compile dependency of the processor |
| Annotation processor | Implements `javax.annotation.processing.Processor`, reads the source model via `javax.lang.model`, and generates code | Processor path of the compiler |
| Service registration | Allows `javac` to automatically discover the processor via `ServiceLoader` | `META-INF/services/javax.annotation.processing.Processor` inside the processor JAR |

The processor runs on the compiler tool's JVM. Therefore, it must be compatible with the **JDK executing the compiler**; the application's source level can differ. For example, `javac` running on JDK 21 with `--release 17` for the application is a valid scenario.

## 2. Building the Annotation API Library

Create `annotation-api/src/main/java/demo/api/AutoGreeting.java`:

```java
package demo.api;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface AutoGreeting {
}
```

`@Target(TYPE)` allows placing the annotation on type declarations. `RetentionPolicy.SOURCE` is sufficient for the annotation processor to read the annotation while `javac` processes the source code; this lesson does not need runtime reflection. The annotation API resides in its own package (`demo.api`) so that the consumer does not depend directly on the processor's implementation package.

If a real-world library adds attributes to the annotation (for example, the generated class name or configuration), clearly define default values, valid types, and a version compatibility policy. Changing the annotation's name or package will simultaneously affect both the application code and `@SupportedAnnotationTypes` in the processor.

## 3. Building GreetingProcessor to Generate Java Source

Create `greeting-processor/src/main/java/demo/processor/GreetingProcessor.java`:

```java
package demo.processor;

import demo.api.AutoGreeting;
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.api.AutoGreeting")
public final class GreetingProcessor extends AbstractProcessor {

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return false;
        }

        for (Element element : roundEnv.getElementsAnnotatedWith(AutoGreeting.class)) {
            if (element.getKind() != ElementKind.CLASS
                    || element.getEnclosingElement().getKind() != ElementKind.PACKAGE) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@AutoGreeting chỉ hỗ trợ top-level class",
                        element);
                continue;
            }

            TypeElement type = (TypeElement) element;
            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(type).getQualifiedName().toString();
            String generatedSimpleName = type.getSimpleName() + "Greeting";
            String generatedName = packageName.isEmpty()
                    ? generatedSimpleName
                    : packageName + "." + generatedSimpleName;

            try {
                JavaFileObject sourceFile = processingEnv.getFiler()
                        .createSourceFile(generatedName, type);

                try (Writer out = sourceFile.openWriter()) {
                    if (!packageName.isEmpty()) {
                        out.write("package " + packageName + ";\n\n");
                    }
                    out.write("public final class " + generatedSimpleName + " {\n");
                    out.write("    private " + generatedSimpleName + "() {}\n");
                    out.write("    public static String text() {\n");
                    out.write("        return \"Hello from generated source\";\n");
                    out.write("    }\n");
                    out.write("}\n");
                }

                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.NOTE,
                        "Generated " + generatedName,
                        element);
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + generatedName + ": " + ex.getMessage(),
                        element);
            }
        }
        return true;
    }
}
```

Key points to understand before packaging:

- `@SupportedAnnotationTypes("demo.api.AutoGreeting")` uses the **fully qualified type name**. If you change the annotation's package without updating this metadata, the processor may still be discovered but will not process the intended annotation.
- `getSupportedSourceVersion()` returns the latest source version supported by the current compiler itself; using `SourceVersion.RELEASE_17` also works when intentionally limiting the version, though it may produce warnings when the application compiles newer source versions.
- `RoundEnvironment` describes the elements in the current processing round; `processingOver()` marks the final round, and the example does not generate new source files in that round.
- `getElementsAnnotatedWith(AutoGreeting.class)` returns matching source elements. The processor intentionally restricts this to **top-level classes** so that generating the `AppGreeting` name stays simple and avoids complex nested-class naming rules.
- `Filer.createSourceFile(generatedName, type)` creates a new source file and specifies the originating element, helping build tools associate the output with the source that triggered the processor.
- Write the source out through `Writer` and let the compiler automatically compile that source in subsequent rounds. There is no need to invoke `javac` a second time just to compile `AppGreeting.java` in this example.
- Return `true` to indicate that the processor has claimed responsibility for the matching annotations. When multiple processors handle the same annotation, the claim decision must be compatible with the contract between them.
- If a source file with the same name already exists, `FilerException` is a type of `IOException`; logging errors with context helps distinguish name collisions from path errors. This sample assumes no handwritten `AppGreeting.java` file exists yet.

**Limitation of the example:** generating Java code strings using `Writer` is suitable when the content is always fixed as above. For annotations containing arbitrary user-provided strings, you must properly escape Java literals or use a proven code generation library. Do not concatenate arbitrary data into Java source without encoding.

## 4. Registering the Processor via Service Provider

Create a file **with no file extension**:

```text
greeting-processor/src/main/resources/META-INF/services/javax.annotation.processing.Processor
```

Verbatim contents, one line:

```text
demo.processor.GreetingProcessor
```

The name of the service file is the fully qualified name of the `javax.annotation.processing.Processor` interface (using the Java `javax` API; do not change it to `jakarta`). The line inside is the fully qualified name of the processor class. The file must be packaged in the exact location under the JAR root:

```text
greeting-processor.jar
  demo/processor/GreetingProcessor.class
  META-INF/services/javax.annotation.processing.Processor
  META-INF/MANIFEST.MF
```

For a **processor on the classpath**, the service file helps the compiler discover the processor without needing the `-processor` option. If you specify `-processor demo.processor.GreetingProcessor`, the compiler loads that exact class directly; this also serves as a test to isolate service discovery failures from class loading failures.

If you package the processor as a **JPMS named module** and use `--processor-module-path`, register the provider with `provides javax.annotation.processing.Processor with demo.processor.GreetingProcessor;` in `module-info.java` and configure the corresponding module dependencies. The hands-on example here uses JARs on the **processor classpath**, not the module path.

**Pitfall when building JARs manually:** compiling the processor directly in a single javac pass when the service file is already on the compiler classpath can cause the compiler to attempt loading the processor before `GreetingProcessor.class` exists. Compile the processor classes first, and then add the service file into the JAR; in Gradle/Maven projects, resources are packaged into the artifact during `jar` / `package`.

## 5. Independent Consumer Using the Annotation and Generated Class

Create `consumer/src/main/java/demo/consumer/App.java`:

```java
package demo.consumer;

import demo.api.AutoGreeting;

@AutoGreeting
public class App {
    public static void main(String[] args) {
        System.out.println(AppGreeting.text());
    }
}
```

`AppGreeting` **does not exist in the handwritten source**. The compiler can only resolve this type if the annotation processor runs successfully, generates `demo.consumer.AppGreeting.java`, and includes the generated file in the same compilation run.

After processing, the generated code has equivalent content to:

```java
package demo.consumer;

public final class AppGreeting {
    private AppGreeting() {}
    public static String text() {
        return "Hello from generated source";
    }
}
```

Placing the `consumer` files in **another repository/project** is completely valid: the consumer project only receives the two built/published artifacts and declares them in the appropriate configurations; there is no need to copy the processor source into the application.

## 6. Hands-On Packaging with javac and jar (Java 17+)

The commands below are run from the parent directory containing the three directories `annotation-api`, `greeting-processor`, and `consumer` created above. The examples use Bash/macOS/Linux; in Windows PowerShell, create directories with `New-Item -ItemType Directory -Force ...` and use `;` as the classpath separator.

**Step 1: Compile and package the annotation API.**

```bash
mkdir -p build/api-classes build/processor-classes build/consumer-classes build/generated
javac --release 17 -d build/api-classes \
  annotation-api/src/main/java/demo/api/AutoGreeting.java
jar --create --file build/annotation-api.jar -C build/api-classes .
```

**Step 2: Compile the processor with the annotation API on the compile classpath.**

```bash
javac --release 17 -cp build/annotation-api.jar \
  -d build/processor-classes \
  greeting-processor/src/main/java/demo/processor/GreetingProcessor.java

jar --create --file build/greeting-processor.jar \
  -C build/processor-classes . \
  -C greeting-processor/src/main/resources META-INF

jar --list --file build/greeting-processor.jar
```

`jar --list` must include at least `demo/processor/GreetingProcessor.class` and `META-INF/services/javax.annotation.processing.Processor`. `annotation-api.jar` must contain `demo/api/AutoGreeting.class`. If the service file is in the wrong location, the processor JAR can still be built successfully, but discovery will fail.

**Step 3: Compile the consumer with two independent paths.**

```bash
javac --release 17 \
  -cp build/annotation-api.jar \
  -processorpath build/greeting-processor.jar:build/annotation-api.jar \
  -processor demo.processor.GreetingProcessor \
  -XprintRounds -XprintProcessorInfo \
  -s build/generated \
  -d build/consumer-classes \
  consumer/src/main/java/demo/consumer/App.java
```

Exact explanation of each role:

- `-cp` contains the annotation API so that the `App.java` source can import `demo.api.AutoGreeting`.
- `-processorpath` contains **both** the processor JAR and the annotation API JAR, because the processor class directly references `AutoGreeting.class` at execution time. Any dependencies of the processor must also be on this path if the processor uses other libraries.
- `-processor` selects a specific processor; this ensures consistent execution across JDK 17+ as well as JDK 23+, where the default annotation processing policy is stricter.
- `-s` specifies the directory for writing generated **sources**; `-d` specifies the directory for compiled **classes**.
- `-XprintRounds` and `-XprintProcessorInfo` print processing traces. Detailed logs depend on the JDK version; diagnostics include the phrase `Generated demo.consumer.AppGreeting`.

At this point, the paths `build/generated/demo/consumer/AppGreeting.java` and `build/consumer-classes/demo/consumer/AppGreeting.class` must exist.

**Step 4: Run the consumer.**

```bash
java -cp build/consumer-classes:build/annotation-api.jar demo.consumer.App
```

Exact stdout:

```text
Hello from generated source
```

On Windows, replace `:` in `-processorpath` and runtime `-cp` with `;`, and wrap arguments containing `;` in quotes if the shell requires it.

**Step 5: Test automatic discovery using the service file.** To verify proper registration, re-run Step 3 after cleaning the output directories, **omitting `-processor demo.processor.GreetingProcessor`** and adding `-proc:full` to the `javac` command. Depending on the JDK 17 update release, the `-proc:full` option may not be available yet; in that case, keep the `-processor` check above or use a modern JDK that supports `-proc:full`. Starting from JDK 23, you should explicitly enable annotation processing instead of relying on implicit processing from the compile classpath. The explicit execution in Step 3 serves as a baseline verification independent of the discovery mechanism.

## 7. Reusing with Gradle in Another Project

Suppose the three projects are declared in a Gradle multi-project build for testing. `settings.gradle`:

```groovy
rootProject.name = 'greeting-workspace'
include 'annotation-api', 'greeting-processor', 'consumer'
```

A simple Groovy DSL `build.gradle` at the root:

```groovy
subprojects {
    apply plugin: 'java'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(17)
        }
    }
}

project(':greeting-processor') {
    dependencies {
        implementation project(':annotation-api')
    }
}

project(':consumer') {
    dependencies {
        implementation project(':annotation-api')
        annotationProcessor project(':greeting-processor')
        annotationProcessor project(':annotation-api')
    }
}
```

Save the Java files and resources following the exact `src/main/java` / `src/main/resources` layout above. Run:

```bash
./gradlew :consumer:clean :consumer:compileJava
./gradlew :consumer:run
```

**Note:** the `:consumer:run` task is only available when the consumer applies the `application` plugin and configures `mainClass`. With the `java`-plugin-only configuration above, the required command to verify the build is `./gradlew :consumer:clean :consumer:compileJava`; to run the application, add to `consumer/build.gradle`:

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.consumer.App'
}
```

Then `./gradlew :consumer:run` will print `Hello from generated source`. `annotationProcessor` defines a separate processor path. The consumer's `implementation` only contains the annotation API (and any other dependencies a real application needs); the processor JAR is not a runtime dependency.

To use them from an **independent Gradle repository**, publish both artifacts using `maven-publish` and replace `project(...)` with dependency coordinates. The following example assumes `demo:annotation-api:1.0.0` and `demo:greeting-processor:1.0.0` have already been published to `mavenLocal()` or an accessible repository:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenLocal()
    mavenCentral()
}

dependencies {
    implementation 'demo:annotation-api:1.0.0'
    annotationProcessor 'demo:greeting-processor:1.0.0'
    annotationProcessor 'demo:annotation-api:1.0.0'
}

application {
    mainClass = 'demo.consumer.App'
}
```

**Producer configuration for publishing:** each library needs the `java-library` (or `java`) and `maven-publish` plugins, declaring `group = 'demo'`, `version = '1.0.0'`, and a publication from `components.java`, for example:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'demo'
version = '1.0.0'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
```

Add this configuration to each producer project (`annotation-api` and `greeting-processor`), then run `publishToMavenLocal` for each project after declaring the processor → annotation-api dependency. Make sure **the processor JAR actually contains the service file** before publishing. In real projects, publish to an internal or external repository according to your organization's policy; avoid using `mavenLocal()` as CI's sole dependency source because other build machines may not have the artifacts.

If you only need a quick local test, multi-project dependencies are sufficient; to reuse across multiple repositories/machines, an artifact repository and versioning serve as the distribution contract.

## 8. Reusing with Maven in Another Project

With Maven 3 and `maven-compiler-plugin` 3.x, `consumer/pom.xml` requires two distinct declaration sections:

1. The `annotation-api` dependency inside `<dependencies>` so that consumer source code can import `AutoGreeting`.
2. `annotationProcessorPaths` in the compiler plugin so that the compiler loads `greeting-processor` along with the annotation API. You can explicitly specify the processor with `annotationProcessors`, which is useful for JDK 23+.

Example POM snippet for an **independent consumer**, after running `install` / `deploy` on the producer artifacts:

```xml
<dependencies>
  <dependency>
    <groupId>demo</groupId>
    <artifactId>annotation-api</artifactId>
    <version>1.0.0</version>
  </dependency>
</dependencies>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.14.1</version>
      <configuration>
        <release>17</release>
        <annotationProcessorPaths>
          <path>
            <groupId>demo</groupId>
            <artifactId>greeting-processor</artifactId>
            <version>1.0.0</version>
          </path>
          <path>
            <groupId>demo</groupId>
            <artifactId>annotation-api</artifactId>
            <version>1.0.0</version>
          </path>
        </annotationProcessorPaths>
        <annotationProcessors>
          <annotationProcessor>demo.processor.GreetingProcessor</annotationProcessor>
        </annotationProcessors>
      </configuration>
    </plugin>
  </plugins>
</build>
```

The snippet above represents **elements inside `<project>`** of a valid Maven POM, not a standalone POM file. Producers can use `mvn install` to publish locally in order—annotation API first, then the processor; the consumer uses `mvn clean compile` and inspects `target/generated-sources/annotations/demo/consumer/AppGreeting.java`. Artifact coordinates are examples; they must match the actual `groupId`, `artifactId`, and `version` when publishing.

In Maven 4 + Compiler Plugin 4.x, dependency declarations such as `processor` / `classpath-processor` / `modular-processor` differ from 3.x; do not arbitrarily mix configurations between the two major versions. When switching toolchains, consult the official documentation of the plugin in use.

## 9. Verifying Artifacts and the Release Contract

Before handing the JARs over to another project, create a **clean consumer fixture** containing only the artifacts intended to be published. This is how you catch accidental dependencies on `build/classes`, IDE caches, or the processor's source code.

Useful verification checks:

| Check | Expected Evidence |
| --- | --- |
| `jar --list --file annotation-api.jar` | Contains `demo/api/AutoGreeting.class` |
| `jar --list --file greeting-processor.jar` | Contains `demo/processor/GreetingProcessor.class` and `META-INF/services/javax.annotation.processing.Processor` |
| Read the service file inside the JAR | A single line with the fully qualified name `demo.processor.GreetingProcessor`, with no typos or different package |
| `javac` with `-processor ...` and proper processor path | Logs `Generated demo.consumer.AppGreeting` |
| `javac` with service discovery only | Runs the processor when AP is explicitly enabled and the processor path is configured |
| `build/generated/.../AppGreeting.java` | Source is generated in the consumer package |
| `build/consumer-classes/.../AppGreeting.class` | Generated source has been compiled by the compiler |
| `java demo.consumer.App` | Stdout `Hello from generated source` |

For an actual release, you should additionally verify the **Java bytecode version of the JAR**, version compatibility between `annotation-api` and `greeting-processor`, artifact coordinates, POM/module metadata files, checksums, and licenses. Do not expose the processor's own types as public API unless the library contract actually requires it.

The versioning scheme should be clear: both artifacts share `1.0.0` in the example for easy synchronization; in practice, they can be versioned independently, provided you clearly document which processor version is compatible with which annotation API version. Adding a required property to the annotation or renaming the generated class can be a breaking change for consumer code.

### Generated Code Contract and Repeatability

- Do not place generated Java sources into the consumer's `src/main/java`. Let `Filer` and the build tool manage the output directory; avoid committing generated artifacts unless there is a specific reason.
- The processor must produce the same output for the same input; do not embed timestamps, machine details, or randomness into generated source unnecessarily. This improves build reproducibility and caching.
- Each source file created by `Filer` should have a unique name within the compilation run; do not write the same name across multiple rounds. In the example, a top-level class `App` generates `AppGreeting`; if the user manually defines the same name, report a clear error.
- For Gradle incremental annotation processing, labeling as `isolating` / `aggregating` must satisfy the actual contract. For example, a generated file derived from a single annotated class already passes the originating element to `Filer`, but you should only register incremental metadata after properly testing the incremental build cases.
- Do not invoke the processor directly at runtime or pull the processor dependency into `runtimeOnly` just to process annotations. An annotation processor must operate at **compile time**.

## 10. Common Errors When Using from Another Project

**Error `cannot find symbol: class AutoGreeting`:** the annotation API JAR is missing from the consumer's **compile classpath** or the imported package is wrong. The processor path alone does not replace the source code's API dependency.

**Error `Annotation processor 'demo.processor.GreetingProcessor' not found`:** the processor JAR is not on the processor path, the class name is wrong, the class is not public or cannot be loaded, or the processor bytecode requires a newer JDK than the compiler. Check `jar --list`, the paths, and the processor's dependencies.

**Error `NoClassDefFoundError: demo/api/AutoGreeting` when the processor runs:** the processor depends on the annotation API, but the API library is not on the **processor path**. Having the API as a compile dependency of the processor during packaging does not mean that dependency is automatically embedded into a manually built processor JAR.

**Compiler succeeds but `AppGreeting` is missing:** annotation processing did not run, the service file was not included in the JAR, the annotation type does not match `@SupportedAnnotationTypes`, or the compiler did not compile `App.java`. Add `-processor`, `-XprintProcessorInfo`, `-XprintRounds`, and diagnostics via `Messager`. With JDK 23+, never rely on automatic AP activation simply because the classpath happens to contain a processor.

**Error `Attempt to recreate a file for type ...`:** there is a class or generated source with the same name, multiple annotated elements produce the same name, or the processor repeatedly generates it across multiple rounds. Inspect `Filer.createSourceFile`, fully qualified names, and round logic; do not fix this by arbitrarily deleting files in another module.

**IDE does not show the generated class while the CLI build works:** verify that annotation processing is enabled, whether the IDE delegates builds to Gradle/Maven, and that the JDK toolchain and generated sources directory are recognized by the IDE. Avoid copying generated files into the source tree as a long-term solution.

**Consumer compiles but throws runtime `ClassNotFoundException` for the processor library:** in this architecture, runtime does not need the processor; only the generated class needs to be inside the consumer artifact. If the generated code actually references a helper from the processor, extract the helper into a **separate runtime library** and declare the runtime dependency explicitly.

**Clean Maven/Gradle build fails even though it works on a personal machine:** the `annotation-api` / `greeting-processor` artifacts have not been published to a repository readable by CI, the service file is missing from the published JAR, or producer and consumer use incompatible versions. Test a clean consumer using artifacts fetched from the actual repository rather than sources from the same checkout.

## 11. Practice Completion Checklist

1. Two JARs are packaged independently: the annotation API and the processor.
2. The processor JAR contains the exact service provider file at `META-INF/services/javax.annotation.processing.Processor`.
3. The consumer only imports the annotation API in source code, and declares the processor on the processor path.
4. Building from clean source generates `AppGreeting.java` via `Filer`, compiles `AppGreeting.class`, and runs to output `Hello from generated source`.
5. Both JARs can be published to a Maven repository and consumed by version coordinates in **another project**, without depending on the producer source.
6. Verified compiler JDK/toolchain, publication metadata, versions, and diagnostics when the processor is not discovered.
7. Understood which parts belong to the compile classpath, processor path, and runtime classpath; artifacts and generated sources are managed in their proper lifecycles.

## References

- Java SE, `Processor`, `AbstractProcessor`, `RoundEnvironment`, `Filer` APIs: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html
- `javac` options (`-processor`, `-processorpath`, `-s`, `-proc`): https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html
- Gradle Java annotation processing: https://docs.gradle.org/current/userguide/java_plugin.html#sec:java_compile_avoidance
- Gradle Maven Publish plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
- Maven Compiler Plugin 3.x annotation processing: https://maven.apache.org/plugins/maven-compiler-plugin-3.14.1/compile-mojo.html
