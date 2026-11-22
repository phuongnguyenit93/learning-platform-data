# Separating Application Dependencies from Annotation Processor Dependencies in a Java Build

## 1. Learning Objectives

In a Java project, libraries that **the application needs to compile or run** are not necessarily the libraries that **javac needs to load to process annotations during the build**. If everything is placed on the same classpath, the project might still build, yet it easily suffers from classpath bloat, unintended processor execution, version conflicts, build supply-chain security risks, and hard-to-diagnose runtime errors.

This lesson explains how to clearly separate:

- **Annotation API**: annotation types that application sources import and apply to classes, methods, or fields.
- **Annotation processor implementation**: code running **during compilation**, typically extending AbstractProcessor and using Filer, Messager, Elements, and Types.
- **Application compile-time dependencies**: classes/JARs javac needs to type-check application sources.
- **Application runtime dependencies**: classes/JARs the JVM actually needs to run the compiled program.
- **Processor runtime dependencies**: classes/JARs the annotation processor itself needs in order to run inside the compilation process.
- **Generated code and its dependencies**: new sources created by a processor can be compiled together with the application and have their own dependency requirements.

The central example uses **Java 17+** with three separated parts: annotation-api, processor, and app. We manually run javac with separate paths, verify code generation and stdout, and then map to Gradle and Maven. At the end of the lesson are decision diagrams, real-world errors, and exercises.

**The most important point:** an annotation processor is **build-time executable code**. It should not automatically be put into the application runtime just because application sources use an annotation that the processor understands.

## 2. A Java Build Has Multiple Class Lookup Paths

Consider the three places where javac/the JVM must look up components:

~~~text
                     BUILD TIME
+--------------------------------------------------+
| Application source: Order.java, Main.java        |
|          |                                       |
|          +--> Compile classpath                  |
|          |       Annotation API                  |
|          |       APIs imported by sources        |
|          |                                       |
|          +--> Processor path                     |
|                  MetaProcessor implementation    |
|                  Processor dependencies          |
|                           |                      |
|                           v                      |
|                    Filer creates OrderMeta.java  |
|                           |                      |
|                           v                      |
|                javac creates .class files        |
+--------------------------------------------------+
                           |
                           v
                     RUNTIME
                  Application JVM
                           |
                           v
                  Main.class + OrderMeta.class
                  + required runtime dependencies
~~~

Compile classpath and processor path have distinct purposes:

| Path/configuration | Who uses it? | What does it contain? |
| --- | --- | --- |
| javac -classpath or -cp | Compiler when resolving source types | Annotation API, libraries imported by application code, APIs needed by generated sources |
| javac -processorpath | Annotation processor loading mechanism | Processor implementation and dependencies the processor needs to run |
| javac -d | Compiler writing output | Compiled classes of the application and generated sources |
| javac -s | Filer/compiler writing generated sources | New Java sources, e.g., OrderMeta.java |
| java -classpath or -cp | JVM when running the application | Application classes and genuinely needed runtime dependencies |
| --module-path / --processor-module-path | Named modules mechanism when configuring JPMS | Module artifacts and processor modules in the appropriate context |

**-d is not -cp.** Specifying an output directory does not automatically let every compiler input or runtime find classes there. Similarly, merely placing a processor JAR on the compile classpath is not an explicit configuration for the compiler to load the processor.

The same JAR can be used on multiple paths when genuinely needed; the point is **separating roles**, not forcing every JAR to appear on strictly one path in all situations.

## 3. Why Should the Annotation API and Processor Implementation Be Separated?

A simple annotation type might only be:

~~~java
package demo.ann;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateMeta {
}
~~~

For application sources to write @GenerateMeta, javac must see **demo.ann.GenerateMeta** on the compile classpath or appropriate module path. However, when the program runs, an annotation with SOURCE retention is not kept in the class file, and if generated code does not use this annotation then runtime normally **does not need** annotation-api.

Conversely, a processor implementation like demo.proc.MetaProcessor contains programmatic logic to inspect elements, access compiler utilities, and create files. This is code **executed by javac at compile time**. Simply having finished generated source does not mean the JVM needs to load MetaProcessor.

### Recommended Artifact Structure

~~~text
annotation-api/
    GenerateMeta.java  --> annotation-api.jar

processor/
    MetaProcessor.java --> processor.jar

app/
    Order.java
    Main.java          --> app classes / app.jar
                            + generated OrderMeta.class
~~~

Desired relationships:

~~~text
app source  --------compile-time-------> annotation-api
javac       --------processor-path-----> processor
processor   --------build dependency---> processor utilities, if any
generated output ----runtime dependency-> only the APIs the output actually calls
~~~

Separating artifacts clarifies dependency scopes. With a large processor, the implementation may pull in parsers, codegen libraries, or private utilities. Those JARs should not end up in the application package merely because the processor uses them.

### Cases Where Annotations Are Needed at Runtime

Not every annotation API has a compile-time-only role:

- **RetentionPolicy.SOURCE**: the annotation is stripped from .class; if there are no other runtime references, annotation-api may only be needed at compile time.
- **RetentionPolicy.CLASS**: metadata can be retained in .class, though runtime Reflection normally does not expose it the way runtime-retained annotations are exposed. Whether annotation-api needs packaging depends on tools and how the class is used.
- **RetentionPolicy.RUNTIME**: the annotation can be accessed via Reflection; if the program/framework needs to load the annotation type at runtime, annotation-api may be a true **runtime dependency**.

Choosing between compileOnly, provided, or implementation must be based on **actual runtime needs**, not merely because an artifact contains annotations.

## 4. Processor Path Is a Type of Execution Dependency

In javac, a processor can be explicitly selected with:

~~~sh
-processorpath build/processor -processor demo.proc.MetaProcessor
~~~

This tells javac where to load the implementation and which processor class will be executed. If the processor needs additional helper JARs at its runtime, those dependencies must be present via the appropriate processor loading mechanism.

**A processor is not just metadata**: the processor's Java code executes during compilation. If a plugin is untrusted, it can run with the build process's permissions, access files, and cause side effects. Therefore separating the processor path also helps audit the **build supply chain** and control versions.

A processor usually extends AbstractProcessor, receives ProcessingEnvironment in init, and creates files via Filer when process is called. These API classes belong to the JDK's java.compiler module and do not require a separate external JAR merely because the namespace starts with javax.

### Distinguishing Discovery and Explicit Selection

There are two common ways to select a processor:

1. **Specifying with -processor**: lists the qualified class name, is deterministic, and does not require a service descriptor.
2. **Service discovery**: the processor JAR has META-INF/services/javax.annotation.processing.Processor listing implementation names, and the compiler/toolchain is configured to allow finding processors.

Do not assume that simply putting a processor JAR on the classpath makes every JDK run it automatically. Starting from Java 23, javac's default regarding annotation processing was tightened: processor/processor path or processing mode should be configured **explicitly**. Build tools also have their own policies. Examples throughout this lesson use -processor so behavior does not depend on discovery.

## 5. Complete Java 17 Project with Three Independent Parts

Create the directory **annotation-deps-lab** with structure:

~~~text
annotation-deps-lab/
├── src/
│   ├── annotation-api/
│   │   └── demo/ann/GenerateMeta.java
│   ├── processor/
│   │   └── demo/proc/MetaProcessor.java
│   └── app/
│       └── demo/app/
│           ├── Order.java
│           └── Main.java
└── build/
    ├── api/             # Annotation .class
    ├── processor/       # Processor .class
    ├── generated/       # Generated .java
    └── app/             # Application and generated .class
~~~

Each Java file below has complete contents. This lesson intentionally selects a processor that can read annotations using **TypeElement** without importing the annotation class. Thanks to that, the processor implementation can compile independently of annotation-api in the example, helping us clearly see the separation of paths. In another processor that directly uses GenerateMeta.class or annotation values through a concrete annotation type, the implementation **may need annotation-api on its own processor path**; this is normal and does not break the goal of role separation.

### 5.1. src/annotation-api/demo/ann/GenerateMeta.java

~~~java
package demo.ann;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateMeta {}
~~~

@Target(TYPE) allows attaching the annotation to type declarations. The sample processor only accepts **classes**, because it actively checks ElementKind.CLASS and reports a diagnostic if the target is anything else.

### 5.2. src/processor/demo/proc/MetaProcessor.java

~~~java
package demo.proc;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.ann.GenerateMeta")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class MetaProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) {
            return true;
        }

        for (TypeElement annotationType : annotations) {
            for (Element element :
                    round.getElementsAnnotatedWith(annotationType)) {
                if (element.getKind() != ElementKind.CLASS) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "Only classes supported", element);
                    continue;
                }

                TypeElement type = (TypeElement) element;
                String pkg = processingEnv.getElementUtils()
                        .getPackageOf(type).getQualifiedName().toString();
                String simple = type.getSimpleName() + "Meta";
                String qualified =
                        pkg.isEmpty() ? simple : pkg + "." + simple;

                try {
                    JavaFileObject file = processingEnv.getFiler()
                            .createSourceFile(qualified, type);
                    try (Writer writer = file.openWriter()) {
                        if (!pkg.isEmpty()) {
                            writer.write("package " + pkg + ";\n");
                        }
                        writer.write("public final class "
                                + simple + " {\n");
                        writer.write("  private " + simple + "() {}\n");
                        writer.write(
                                "  public static String text() { return "
                                + "\"Meta for " + type.getSimpleName()
                                + "\"; }\n");
                        writer.write("}\n");
                    }
                } catch (IOException ex) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "Generation failed: " + ex.getMessage(),
                            element);
                }
            }
        }
        return true;
    }
}
~~~

**Key points in the processor:**

1. SupportedAnnotationTypes declares the annotation's qualified name as a string. The processor does not need to import demo.ann.GenerateMeta in its own source code.
2. SupportedSourceVersion declares the supported Java 17 level.
3. processingEnv is a field provided by AbstractProcessor after the compiler calls init.
4. RoundEnvironment and Set<TypeElement> provide the round's annotations; process may be invoked multiple times.
5. getElementsAnnotatedWith(TypeElement) finds elements bearing the annotation in the round.
6. Elements.getPackageOf helps find the exact package of the source class.
7. Filer.createSourceFile creates a new source file by qualified name, here OrderMeta.
8. Writer is closed by try-with-resources. The generated source contents will be fed by the compiler into the next round when appropriate.
9. Messager reports ERROR if the target is invalid or output cannot be created.
10. return true **claims the annotation**, rather than being a Boolean saying the whole build is guaranteed to succeed.

The demo is designed for a simple top-level class. In a production processor, you must account for nested classes, duplicate generated names, multiple targets, annotation values, and source escaping rules. In particular, never generate the same qualified output twice within the same invocation; Filer may throw FilerException upon collision.

### 5.3. src/app/demo/app/Order.java

~~~java
package demo.app;

import demo.ann.GenerateMeta;

@GenerateMeta
public final class Order {}
~~~

Order.java **must** see the annotation API when compiling, because it directly imports and uses GenerateMeta.

### 5.4. src/app/demo/app/Main.java

~~~java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println(OrderMeta.text());
    }
}
~~~

Main.java intentionally references **OrderMeta**, a class not yet present in the initial sources. The processor generates OrderMeta.java while javac performs annotation processing, and then the generated source is compiled into OrderMeta.class before the application runs.

### Why Is the Processor Not Imported into Main?

Main does not use MetaProcessor and does not need to know the processor implementation. It only calls a method on the **generated class**. This is precisely the boundary between a **build-time code generator** and **application runtime**.

## 6. Three-Stage Compilation with javac

Open a terminal at the root of annotation-deps-lab and confirm JDK 17+ is used:

~~~sh
javac -version
java -version
~~~

Create the output directories. Use only one variant suitable for your shell.

~~~bash
# Bash on macOS/Linux
mkdir -p build/api build/processor build/generated build/app
~~~

~~~powershell
# PowerShell on Windows
New-Item -ItemType Directory -Path build/api,build/processor,build/generated,build/app -Force | Out-Null
~~~

### 6.1. Compiling the Annotation API

~~~sh
javac --release 17 -d build/api src/annotation-api/demo/ann/GenerateMeta.java
~~~

Output:

~~~text
build/api/demo/ann/GenerateMeta.class
~~~

Only the annotation class is in the API output. This is the minimal compile dependency that source Order.java needs to be type-checked.

### 6.2. Compiling the Processor Implementation

~~~sh
javac --release 17 -d build/processor src/processor/demo/proc/MetaProcessor.java
~~~

Output:

~~~text
build/processor/demo/proc/MetaProcessor.class
~~~

This command **does not need -cp build/api** because the sample processor receives TypeElement from the annotations parameter and uses the annotation name in SupportedAnnotationTypes, without directly referencing GenerateMeta.class.

In a real processor if it imports demo.ann.GenerateMeta or uses other dependencies, the processor compile command must provide them on the appropriate compile classpath; and the processor loading stage must also have those runtime dependencies on the processor path.

### 6.3. Compiling the Application and Triggering the Processor

~~~sh
javac --release 17 -cp build/api -processorpath build/processor -processor demo.proc.MetaProcessor -s build/generated -d build/app src/app/demo/app/Order.java src/app/demo/app/Main.java
~~~

Meaning of each flag:

| Flag | Role group | Explanation |
| --- | --- | --- |
| --release 17 | Compiler target | Checks API/language and generates Java 17 compatible bytecode |
| -cp build/api | Application compile classpath | Source Order.java sees demo.ann.GenerateMeta |
| -processorpath build/processor | Build-time processor classpath | Compiler loads demo.proc.MetaProcessor |
| -processor demo.proc.MetaProcessor | Processor selection | Does not rely on default discovery |
| -s build/generated | Generated source output | OrderMeta.java created by Filer |
| -d build/app | Class output | Order.class, Main.class, OrderMeta.class |
| Order.java and Main.java | Source input | Initial application sources |

**Outputs to verify:**

~~~text
build/generated/demo/app/OrderMeta.java
build/app/demo/app/Order.class
build/app/demo/app/Main.class
build/app/demo/app/OrderMeta.class
~~~

Expected generated source:

~~~java
package demo.app;
public final class OrderMeta {
  private OrderMeta() {}
  public static String text() { return "Meta for Order"; }
}
~~~

In this example, there is **no** demo/proc/MetaProcessor.class file in build/app. It stays inside build/processor. That is proof that application output is separated from the processor implementation.

**Re-run warning:** if you previously created generated sources from another build, use a clean separate output or clean only the four build directories of this lesson before redoing it. Do not manually create OrderMeta.java inside src/app because it can collide with Filer.

### 6.4. Running the Application

~~~sh
java -cp build/app demo.app.Main
~~~

**Exact stdout of the example (verified with javac --release 17):**

~~~text
Meta for Order
~~~

Runtime only needs build/app. In this demo, there is no need to place build/processor or build/api on the runtime classpath: generated code does not call MetaProcessor and the annotation has SOURCE retention.

If you change the annotation to one read by runtime code via Reflection, or generated sources call another runtime library, **the required runtime dependencies must be provided**. Do not generalize the demo's minimal setup into a rule for every annotation processor.

## 7. Three Questions to Determine Where a Dependency Belongs

For any given artifact, ask:

**Question 1: Do application sources import/reference types in this artifact?** If yes, that artifact needs to be on the **application compile classpath** (or module path) accordingly. Example: Order.java imports GenerateMeta and therefore needs the annotation API.

**Question 2: Does the processor implementation load/call classes in this artifact during build?** If yes, that artifact needs to be on the **processor execution path**, and on the processor's compile classpath when building the processor itself. Example: if MetaProcessor uses a code generation library, that library serves the processor and does not automatically become a runtime dependency of the application.

**Question 3: Does application bytecode or generated code need this artifact at runtime?** If yes, the artifact must appear on the **application runtime classpath** or module path. Example: if OrderMeta.text() calls a helper in com.example.runtime.Helper, that helper is a true runtime dependency.

These are three separate checks. **The same artifact can answer yes to multiple questions**. The goal is placing it only where genuinely needed, avoiding scope mixing.

### Example Decision Table

| Artifact | Compile app | Execute processor | Run app |
| --- | --- | --- | --- |
| annotation-api.jar with the demo's SOURCE annotation | Yes | Not needed in demo | Not needed |
| processor.jar of demo | No | Yes | No |
| processor-util.jar used only by processor | No | Yes if processor depends on it | No |
| runtime-helper.jar called by generated class | Yes if generated source imports it | No, unless processor also uses it | Yes |
| logging library called by both app and processor | Yes for app if source imports | Yes for processor | Yes for app if bytecode calls |
| JDK java.compiler API | Provided by JDK when building processor | Provided by JDK | Processor classes not needed when app runs |

Do not confuse **artifact dependencies of the processor project** with **dependencies needed by the app at runtime**. A build tool may download both during the build, yet they do not belong to the same classloader or classpath.

## 8. When the Processor Needs annotation-api to Run

The demo chose TypeElement so the implementation does not reference GenerateMeta.class directly. However, a typical processor might write:

~~~java
for (Element element :
        round.getElementsAnnotatedWith(GenerateMeta.class)) {
    // Read or process the annotation.
}
~~~

This is only a **non-standalone** snippet, assuming the processor already imported GenerateMeta and has an appropriate round variable. In that case:

1. The processor project needs a **compile dependency** on annotation-api.
2. When loading the processor, the compiler must find GenerateMeta.class in **processor execution dependencies**.
3. App sources also need annotation-api on the **application compile path**.
4. App runtime **only** needs annotation-api if the application actually uses it at runtime.

The same annotation-api.jar can appear on two different classpaths while still being a proper separated design. Do not cause missing class errors during processor loading just because annotation-api is already on the application classpath: the processor's classloader/path may be isolated.

Conversely, do not place processor.jar on the app compile classpath just to work around a missing annotation-api error. Create a separate annotation-api artifact and put only the API on the compile path.

## 9. Gradle Java: compileOnly, implementation, and annotationProcessor

With the Gradle Java plugin, common configurations:

| Configuration | Primary meaning | In default app runtime? |
| --- | --- | --- |
| implementation | Dependency used by application code and potentially needed at runtime | Yes, in runtime dependency graph |
| api | API dependency exposed to consumers when using java-library plugin | Yes, and also affects downstream compile classpath |
| compileOnly | Needed only to compile current sources | No |
| runtimeOnly | Not needed for compile, needed at runtime | Yes |
| annotationProcessor | Dependency to execute javac annotation processor | Does not automatically become implementation/runtime |
| testImplementation | Dependency for compiling/running tests | In test scope, not app main runtime |
| testAnnotationProcessor | Processor used when compiling test sources | Does not automatically enter app main runtime |

**Ideal configuration for the demo app:**

~~~groovy
dependencies {
    compileOnly project(':annotation-api')
    annotationProcessor project(':processor')
}
~~~

Here annotation-api serves code compilation, and processor serves generator execution. Having annotationProcessor project(':processor') does not automatically allow app sources to import GenerateMeta; they must see annotation-api in a separate compile scope.

### Gradle Multi-Project Structure

Convert the demo sources to the standard Java plugin layout:

~~~text
annotation-deps-gradle/
├── settings.gradle
├── build.gradle
├── annotation-api/
│   └── src/main/java/demo/ann/GenerateMeta.java
├── processor/
│   └── src/main/java/demo/proc/MetaProcessor.java
└── app/
    └── src/main/java/demo/app/
        ├── Order.java
        └── Main.java
~~~

**settings.gradle:**

~~~groovy
rootProject.name = 'annotation-deps-gradle'
include 'annotation-api', 'processor', 'app'
~~~

**build.gradle at root:**

~~~groovy
subprojects {
    apply plugin: 'java'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(17)
        }
    }
}

project(':app') {
    dependencies {
        compileOnly project(':annotation-api')
        annotationProcessor project(':processor')
    }

    tasks.named('compileJava', JavaCompile) {
        options.compilerArgs += [
            '-processor', 'demo.proc.MetaProcessor'
        ]
    }
}
~~~

This is a Gradle **Groovy DSL configuration for the Java sources above**. It selects the processor explicitly; therefore adding a service file to the processor project is not mandatory. The toolchain requires a compatible Gradle/JDK, and the environment needs Gradle (or wrapper) to run. The example processor code does **not** directly use the annotation class, so the processor project does not need to declare a dependency on annotation-api; if you change how the processor is implemented, update dependencies accordingly.

With the proper setup, run from the project root:

~~~sh
gradle :app:classes
gradle :app:run
~~~

**Note:** the :app:run command only exists when you additionally configure the **application** plugin and mainClass for app; the minimal Java plugin project above **does not yet define a run task**. To avoid depending on unconfigured tasks, use the build command that actually applies:

~~~sh
gradle :app:classes
~~~

Afterwards you can run the application from Gradle's class outputs via the path used by your version/toolchain, or add the application plugin configuration as below.

### Adding the application Plugin to Run with Gradle

Replace the project(':app') block in root with the following equivalent form:

~~~groovy
project(':app') {
    apply plugin: 'application'

    application {
        mainClass = 'demo.app.Main'
    }

    dependencies {
        compileOnly project(':annotation-api')
        annotationProcessor project(':processor')
    }

    tasks.named('compileJava', JavaCompile) {
        options.compilerArgs += [
            '-processor', 'demo.proc.MetaProcessor'
        ]
    }
}
~~~

Once the application plugin is added, run:

~~~sh
gradle :app:run
~~~

**Main program stdout** remains:

~~~text
Meta for Order
~~~

Gradle will print additional task logs, build status, or environment info, so total terminal output **does not consist of only the single line** above. Do not treat this as the exact output of the entire Gradle CLI.

### If the Processor Has Its Own Dependencies in Gradle

Suppose MetaProcessor needs a code processing library at build time:

~~~groovy
project(':processor') {
    dependencies {
        implementation 'com.example:processor-util:1.0.0'
    }
}
~~~

The snippet above is a **configuration illustration**, not a real dependency created in the demo project. When app declares annotationProcessor project(':processor'), required runtime dependencies of the processor project are usually placed on the processor configuration via the appropriate dependency resolution graph. They do **not** automatically appear in app implementation simply because app uses the processor.

If generated code ends up calling processor-util, it must be treated as an app runtime dependency and declared separately per the actual contract. Processor implementation dependencies and generated-code runtime dependencies are not identical.

### Why Not Declare the Processor Under implementation?

~~~groovy
dependencies {
    implementation project(':processor')  // Not suitable for the demo
}
~~~

This line places the processor project into the application's dependency graph without **clearly expressing the intent that javac must run the processor**. It can cause the app runtime to carry the implementation and auxiliary libraries, increasing package size or causing conflicts.

Fix it by using annotationProcessor for the processor, and compileOnly/implementation for the annotation API depending on retention/runtime requirements.

## 10. Maven: Regular Dependencies and annotationProcessorPaths

With Maven, app dependencies are declared inside dependencies, while annotation processors can be configured separately inside **maven-compiler-plugin**.

Suppose a Maven reactor contains three corresponding modules and you have the artifacts:

~~~text
demo:annotation-api:1.0.0
demo:processor:1.0.0
demo:app:1.0.0
~~~

These are **illustrative coordinates for your project**, not artifacts promised to exist on Maven Central.

In **app's pom.xml**, for example with Maven Compiler Plugin 3.x:

~~~xml
<dependencies>
    <dependency>
        <groupId>demo</groupId>
        <artifactId>annotation-api</artifactId>
        <version>1.0.0</version>
        <scope>provided</scope>
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
                        <artifactId>processor</artifactId>
                        <version>1.0.0</version>
                    </path>
                </annotationProcessorPaths>
                <annotationProcessors>
                    <annotationProcessor>
                        demo.proc.MetaProcessor
                    </annotationProcessor>
                </annotationProcessors>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

**This is a configuration snippet intended for a POM that already has matching project coordinates and Maven reactor**, not a complete standalone pom.xml. The goal is showing the different places where **annotation-api** and **processor** are declared. Plugin version 3.14.1 is an example version from the 3.x branch, not a claim that it is the latest at all times. Maven Compiler Plugin 4.x/Maven 4 introduce new ways to declare processor dependencies; refer to the documentation of the exact version you use when upgrading.

In the demo, the annotation API has SOURCE retention and is not used by runtime code, so scope provided lets the app compile without requiring that dependency in the ordinary runtime graph. If runtime genuinely needs the annotation API, use a scope suited to runtime needs instead of provided.

**annotationProcessorPaths** is the processor execution path constructed by the compiler plugin. If the processor has runtime dependencies, those dependencies must also be fully resolved on the processor path. For a processor that imports annotation-api directly, it may be necessary to add annotation-api to the processor artifact's dependency graph or processor path, depending on how it is published.

### Processor Selection Rules in Maven

- annotationProcessorPaths specifies which processor artifacts are used during compilation.
- annotationProcessors allows selecting processor classes explicitly, similar to javac's -processor.
- If using service discovery, the processor JAR must have a valid descriptor and the plugin/JDK version must be configured to permit discovery.
- Do not merely add a processor to dependencies with scope compile and expect it to be loaded/run as an annotation processor in every configuration.

### Be Careful with Maven Scopes

| Maven scope | Closest concept | Notes |
| --- | --- | --- |
| compile | Compile and usually runtime dependency | Not equivalent to annotation processor execution path |
| provided | Present for compile/test, usually omitted from ordinary runtime | Suitable when supplied by runtime/container or compile-only dependency |
| runtime | Not needed to compile sources, needed at runtime | Generated code or runtime services may need it |
| test | Only for test code/lifecycle | Processors for tests may need separate configuration |

Maven provided is **not an exact replica** of Gradle compileOnly across all transitivity and packaging rules. Inspect the dependency tree, artifact packaging, and actual runtime execution rather than relying on “similar-looking” scope names.

## 11. Annotation Processors and Generated Code Can Need Two Different Dependency Sets

For instance, a processor uses **JavaPoet** or a template library to generate Java source. That library serves the **generator**. A generated class consisting solely of Java SDK calls does not need JavaPoet at runtime.

Conversely, a generator might emit code:

~~~java
package demo.app;

public final class OrderMeta {
    public static String text() {
        return com.example.runtime.Texts.format("Order");
    }
}
~~~

This is an **illustrative generated source snippet**, not part of the verified runnable demo. Because OrderMeta.class references com.example.runtime.Texts, the app runtime must have the library containing Texts; compiling the generated source also needs to see it. Adding this library **only** to the annotationProcessor configuration will not suffice.

Mental model:

~~~text
Generator uses helper A to generate source
  -> A is needed on the processor execution path.

Generated source calls helper B at runtime
  -> B is needed on the application compile + runtime dependency path.

Annotation type C is only used at compile time
  -> C is needed on the application compile path; runtime depends on retention/usage.
~~~

Special cases such as generated classes using annotations with RUNTIME retention or interfaces from an annotation processor runtime library must be evaluated separately. There is no rule saying “every annotation-related library is compileOnly”.

## 12. Risks of Mixing Processor Loading Paths with the App

### Classpath Pollution

If processor.jar and all its dependencies are placed into app implementation, the classpath contains many classes unnecessary at runtime. This can bloat the package/JAR, raise the risk of library version collisions, or create accidental dependencies on build-only APIs.

### Unintended Processor Activation

A processor JAR with a service descriptor may be discovered by the compiler in some configurations, causing the build to run the processor when the author did not intend it. Configuring a separate processor path and explicit selection makes behavior easier to verify.

### Version Conflicts

The application uses version X of a library, while the processor needs version Y for code generation. If both are dumped onto a single classpath, conflicts can arise immediately during build or in the runtime package. Separating configurations allows managing separate dependency graphs and testing independently.

### Build Security

Annotation processors execute code while compilation occurs. A compromised processor dependency is not “just an annotation”; it can execute logic inside the build process. You must pin/control versions, artifact sources, and plugin trust, review processor changes, and avoid running processors of unknown provenance.

### Reproducibility

When the compiler picks up processors automatically from an uncontrolled classpath, an added dependency can alter generated output. Configure processor path, versions, and selectors explicitly; keep generated source deterministic and avoid unnecessary timestamps/randomness.

## 13. If the Build Uses Java Modules (JPMS)

The runnable example in sections 5–6 uses the classpath to isolate each role. When switching to named modules, you must additionally distinguish:

- **Application module path**: modules read by app source to compile or resolved by app runtime.
- **Processor module path**: named modules containing processors and their dependencies when using module-aware processor loading.
- **Regular processor path**: processors loaded via classpath-based mechanism, usually with -processorpath.
- **module-info.java**: requires/exports/opens of the application or processor module depending on design.

Do not confuse **--processor-module-path** with the application's **--module-path**. Those are two different resolution contexts. A processor can be packaged as a named module supplying the javax.annotation.processing.Processor service via provides, yet that is a separate packaging approach requiring consulting the exact JDK documentation.

An annotation API used by an app via JPMS must also have a module descriptor or appropriate automatic module name and a requires relationship in the app. Simply changing -cp to --module-path does not automatically resolve the dependency graph, split packages, or service discovery.

**In summary:** JPMS adds module constraints, yet does not change the principle of separating **compiler/plugin execution dependencies** from **application runtime dependencies**.

## 14. Common Configuration Mistakes and How to Fix Them

| Symptom | Possible configuration error | Check/fix |
| --- | --- | --- |
| cannot find symbol GenerateMeta | Annotation API missing from application compile classpath | Add annotation-api to compileOnly/appropriate compile scope |
| Annotation processor not found | Processor implementation missing from processor path, wrong class name | Check -processorpath, -processor, and processor artifact |
| NoClassDefFoundError when loading processor | Processor needs library or annotation type missing from processor path | Add processor's dependencies to processor execution path |
| cannot find symbol OrderMeta | Processor did not run or did not generate file | Check processor selection, -s, diagnostics, and generated source |
| FilerException: Attempt to recreate a file | Duplicate generated output or stale build pipeline | Check naming, rounds, input sources, and clean output |
| Generated source fails to compile due to missing type | Generated code calls API missing from app compile classpath | Add the generated code's proper API/runtime library |
| App build passes yet runtime NoClassDefFoundError | Runtime classpath lacks dependency called by app or generated bytecode | Check runtime dependency graph and packaging |
| Processor in app jar | Mistakenly used implementation instead of annotationProcessor/provided | Move to processor-specific configuration |
| Processor does not auto-run on newer JDK | Relied on default discovery | Select processor and processor path explicitly |
| Test classes lack generated types | Test annotation processing or separate output not configured | Check testAnnotationProcessor and test source set |
| Gradle :app:run does not exist | Only Java plugin used, missing application plugin | Configure application plugin/mainClass or run java directly |
| Maven processor present yet app still lacks annotation type | annotationProcessorPaths does not automatically put API on application source compile path | Declare annotation-api in dependencies with proper scope |

### Diagnosing by Boundary

Start with three questions:

1. Does the compiler see the **annotation type** in sources?
2. Can the compiler load/instantiate the **processor implementation** with all of the processor's runtime dependencies?
3. Do the generated sources/classes compile and run with **application dependencies**?

If the failure is at question 1, check the app compile path. If the failure is at question 2, check the processor path. If the failure is at question 3, check generated output and the app compile/runtime path. Do not randomly alter all scopes just to make errors go away.

## 15. Verifying That the Processor Does Not Leak into the Application

The demo can be verified with a sequence of observations:

1. Before the app build stage, build/api has GenerateMeta.class.
2. build/processor has MetaProcessor.class, while build/app does not yet have the processor class.
3. After compiling app, build/generated has OrderMeta.java and build/app has OrderMeta.class.
4. Running java -cp build/app demo.app.Main yields stdout **Meta for Order**.
5. There is no demo/proc/MetaProcessor.class in build/app.

Note that the class not being in build/app **does not guarantee** that complex Gradle/Maven packaging won't pull processor.jar into the final output via another dependency. With real build tools, also inspect dependency graphs and packaged artifacts.

### Checking Gradle

In a Gradle project, useful commands:

~~~sh
gradle :app:dependencies --configuration compileClasspath
gradle :app:dependencies --configuration annotationProcessor
gradle :app:dependencies --configuration runtimeClasspath
~~~

Compare the results of the three configurations. The annotation API, processor implementation, and runtime-only dependencies should appear precisely where designed. Exact configuration names also depend on the plugins/source sets in use.

### Checking Maven

In Maven, use the app's dependency tree to inspect artifacts belonging to normal dependencies, then inspect maven-compiler-plugin configuration to see annotationProcessorPaths. Depending on plugin version, processor dependencies may not appear as an ordinary application dependency. Do not take dependency:tree as sole proof of the entire processor path.

### Cross-Checking the Packaged JAR

If the final app is an executable JAR/fat JAR, inspect the list of packaged libraries. The processor implementation should not be inside the demo's runtime bundle unless there is a genuine separate runtime reason. With Spring Boot or shadow JARs, packaging plugins have their own rules; inspect the final artifact after building.

## 16. Processor Dependencies and Test Scope

When tests use annotation processing, distinguish:

- **Main source set**: processor creates generated classes for the main application.
- **Test source set**: test sources may also use annotations to generate helpers specific to tests.
- **Processor unit tests**: the processor project itself has test dependencies and can compile test sources to verify generated files/diagnostics.

In the Gradle Java plugin, testAnnotationProcessor is for processors on the test compile path. If you only configure annotationProcessor for main compilation, test compilation might not receive the processor the way you expect. However, generated classes from main output can be used by test code because the test source set depends on main classes; that differs from re-running the processor for test sources.

A good testing strategy:

1. Testing the annotation API does not need the processor implementation.
2. Test the processor separately with valid source inputs and invalid annotation inputs.
3. Verify generated output, diagnostics, and javac exit status.
4. Test the application with real runtime dependencies, **without letting the processor implementation accidentally mask a missing runtime dependency**.
5. If test sources need a processor, explicitly configure a test-specific processor path.

## 17. Differences from Kotlin KAPT/KSP and Other Code Generators

Annotation processing in this lesson is **JSR 269/javac** for Java sources. With Kotlin, projects may use kapt or KSP, with their own configurations and code generation mechanisms.

The shared architectural point remains separating:

~~~text
Application API dependencies
        !=
Build-time code generator dependencies
        !=
Generated-code runtime dependencies
~~~

However, do not copy Gradle annotationProcessor syntax verbatim to kapt/ksp and assume it handles all Kotlin sources. In mixed Java/Kotlin projects, check the corresponding compiler plugins and source sets.

Similarly, protobuf, OpenAPI, and generators that run before javac may be build plugins rather than annotation processors. Distinguish the generator's lifecycle and outputs to configure dependencies in the right places.

## 18. Some Advanced Issues to Know

### Annotation Retention Does Not Dictate Every Runtime Dependency

Do not claim a SOURCE annotation means “annotation-api is never needed at runtime” in every project. If runtime code directly uses an interface or helper residing in the same annotation-api artifact, the dependency is still needed. Conversely, a processor does not automatically become a runtime dependency just because annotation retention is RUNTIME.

### A Processor's Dependency Graph Is Independent, Yet Not Absolute

Build tools may have different classloader sharing, worker isolation, or caching. What you must rely on is the **configuration contract provided by the tool**, rather than assumptions about a specific classloader implementation. Test whenever moving a processor to a new Gradle/Maven/JDK version.

### Incremental Compilation

Generated files should have deterministic names and clear relationships to annotated elements. Filer.createSourceFile allows passing originating elements to help build tools understand the generation source. However, whether a processor becomes incremental-safe also depends on processor type, input reading, file outputs, and build tool rules. Separating dependencies alone does not automatically make incremental builds correct.

### Processors and Build Cache

If a processor reads external files unknown to the build tool, generates time-dependent content, or relies on undeclared global configuration, the cache can be wrong. Limit side effects and describe inputs explicitly. This is why maintainable processors try to produce deterministic output.

### Multi-Release JARs and JDK Versions

A processor JAR must be able to run on the JDK executing the compiler, not only on the bytecode level the app targets. For example, an app builds with --release 17 using a newer JDK; the processor may run inside that newer JDK's compiler process. Therefore you must verify both the build toolchain and the processor implementation's compatibility. Do not confuse target bytecode with the JVM executing the processor.

## 19. Practical Exercises

**Exercise 1 — Classifying dependencies.** List annotation-api, processor, processor-util, and runtime-helper. For each artifact, fill in three columns: app compile, processor execution, app runtime. Explain via actual call paths rather than library names.

**Exercise 2 — Manual compilation.** Create the Java 17 project in section 5. Run the three javac and java commands. Why does OrderMeta.java not exist before the compiler runs the processor, yet exists after compiling?

**Exercise 3 — Removing processor from runtime.** Run java -cp build/app demo.app.Main; confirm it still prints Meta for Order. Why is -cp build/app:build/processor unnecessary? Answer based on the bytecode/runtime dependencies of Main and OrderMeta.

**Exercise 4 — Testing missing annotation API.** Omit -cp build/api in the app compile stage. Predict that import demo.ann.GenerateMeta will fail. Does having the processor still on -processorpath fix the app source type resolution error?

**Exercise 5 — Testing missing processor.** Keep annotation API on -cp yet disable annotation processing with -proc:none in a clean build. Why can Main report it cannot find OrderMeta? Because the annotation type being present does not mean the generated class was created.

**Exercise 6 — Adding processor runtime dependency.** Suppose MetaProcessor uses a helper in processor-util. Which project and which path should it be declared in? If the app does not use that helper at runtime, why not add it to app runtime?

**Exercise 7 — Generated runtime dependency.** Modify the generator so OrderMeta calls a class in runtime-helper.jar. Add the proper dependency for generated source compilation and application runtime. Check what error can occur if runtime-helper is added only to the annotationProcessor configuration?

**Exercise 8 — Gradle.** Convert the structure into three subprojects, adding compileOnly and annotationProcessor in the right places. Set up the application plugin to run :app:run and verify runtimeClasspath does not automatically contain the processor project.

**Exercise 9 — Maven.** Organize three modules annotation-api/processor/app; declare annotation-api in app dependencies and processor in annotationProcessorPaths. Explain the role of provided/compile according to actual runtime needs.

**Exercise 10 — SOURCE and RUNTIME.** Change annotation retention to RUNTIME and add Reflection code reading the annotation at runtime. Why can annotation-api become a real runtime dependency, while the processor implementation still does not?

**Exercise 11 — Build security.** Which dependency group has code executed right at compile time? Why is it necessary to pin versions and only load processors from trusted sources?

**Exercise 12 — Mixed Java/Kotlin.** If some Kotlin sources use kapt or KSP, what cannot be assumed about the Gradle annotationProcessor configuration? Describe how to check the corresponding toolchain and plugins.

## 20. Clean Build Design Checklist

- Recognized that annotation API, processor implementation, and generated runtime dependencies are three distinct roles.
- App sources see the annotation API on the proper compile path.
- Processors are explicitly selected and loaded from a processor-specific path.
- Processor dependencies are complete in the environment **running the processor during build**.
- Generated sources are compiled with the APIs they reference.
- App runtime path contains the libraries genuinely needed by app/generated bytecode.
- Do not put the processor implementation into app implementation merely to make it run during compilation.
- Do not assume SOURCE-retained annotation APIs are always/never needed at runtime out of context.
- Understand that Gradle compileOnly, implementation, annotationProcessor, and testAnnotationProcessor differ.
- Understand that Maven dependency scopes differ from the compiler plugin's annotationProcessorPaths.
- Understand why Java 23+ makes explicit annotation processing configuration even more important.
- Verified clean build, generated files, app outputs, and dependency graphs.
- Verified that the processor does not accidentally appear in packaged runtime artifacts.
- Have a plan for maintaining processor versions, incremental builds, and build supply chain.

### References for Further Reading

- **Java SE 17 API: javax.annotation.processing**, AbstractProcessor, ProcessingEnvironment, Filer, and RoundEnvironment.
- **Javac documentation** of the JDK in use: -classpath, -processorpath, -processor, -proc, -s, -d, --release, --processor-module-path.
- **Gradle Java Plugin / Java Library Plugin documentation**: implementation, api, compileOnly, annotationProcessor, runtimeOnly, testAnnotationProcessor, and toolchains.
- **Maven Compiler Plugin documentation** matching the version in use: annotationProcessorPaths, annotationProcessors, release, and processor dependencies.
- **Java Platform Module System**: module path, processor module path, and requires/exports when using named modules.

**In summary:** the application and annotation processor run in **two different phases**, with different goals and dependency graphs. Put the annotation API where sources need it, put the processor's implementation/dependencies where the compiler runs it, and put runtime libraries where application bytecode actually uses them. Properly separating the three roles makes builds clear, controllable, reproducible, and less prone to conflicts.