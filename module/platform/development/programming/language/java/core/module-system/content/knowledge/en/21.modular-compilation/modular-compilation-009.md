# Distinguishing Compile Classpath from Processor Path

## Objectives

After this lesson, you will be able to distinguish the library path that `javac` uses to compile source code from the path that `javac` uses to load annotation processors; configure both paths using the appropriate options; and understand how processors are discovered, executed, generate source code, and participate in the compilation process.

## 1. Two Paths Serving Two Different Roles

When compiling Java, `javac` may need to find two groups of components:

1. **Compile classpath**: classes or JARs that the source code being compiled references, such as libraries containing data types, interfaces, annotations, or superclasses.
2. **Processor path**: classes or JARs containing annotation processors that the compiler itself must load and run during annotation processing.

Both groups may consist of JARs, yet they do not share the same responsibility.

| Criterion | Compile classpath | Processor path |
|---|---|---|
| Purpose | Find types and classes needed to check and compile source code | Find annotation processor classes and processor dependencies |
| Javac option | -classpath, --class-path, or -cp | -processorpath or --processor-path |
| Typical contents | API libraries, models, annotations, third-party libraries used by source | JARs implementing javax.annotation.processing.Processor and libraries needed by the processor |
| Used to | Resolve types, check method signatures, parameter types, inheritance, and references in source | Load processors, invoke annotation processing rounds, and create sources/classes/resources |
| Does it replace the other path? | Does not replace processor path | Does not replace compile classpath |
| Does it automatically become an application runtime dependency? | No; runtime must be configured separately | No; processors are typically needed only during the build |

Remember: the compile classpath helps `javac` understand the source code being compiled; the processor path tells `javac` which annotation processing tools to load.

## 2. What Is the Compile Classpath Used For?

Suppose an application uses the type `com.acme.model.Customer` located in the JAR `model-api.jar`:

~~~java
package com.acme.app;

import com.acme.model.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("An");
        System.out.println(customer.name());
    }
}
~~~

`javac` needs to find `Customer.class` to verify constructors, return types, methods, and related type rules. We place the JAR containing that type on the compile classpath:

~~~bash
javac \
    -classpath lib/model-api.jar \
    -d build/classes \
    src/com/acme/app/Main.java
~~~

The options:

- `-classpath` (short form `-cp`, or full form `--class-path`) specifies where `javac` looks for classes and JARs used for compilation.
- `-d` specifies the directory for output class files.
- Source files are passed at the end of the command.

If there are multiple libraries, separate the paths with the operating system's path separator:

~~~bash
# Linux or macOS: colon
javac -cp "lib/model-api.jar:lib/logging.jar" -d build/classes src/com/acme/app/Main.java
~~~

~~~powershell
# Windows: semicolon
javac -cp "lib\model-api.jar;lib\logging.jar" -d build\classes src\com\acme\app\Main.java
~~~

The compile classpath only applies to that `javac` invocation. When running the application, the `java` command has its own classpath; libraries needed at runtime must be provided to the running process. A JAR appearing in `javac -cp` does not automatically package that JAR into the application.

If the sources are organized as named modules, consider `--module-path` to locate module dependencies. `--class-path` and `--module-path` serve two different resolution models; a modular JAR placed on the classpath will not be resolved as a named module under JPMS.

## 3. What Is an Annotation Processor?

An annotation processor is a component that runs during compilation. It reads annotations and program structure information provided by the compiler, and can then validate conventions or generate additional source code, class files, and resources.

For example, a library has an annotation:

~~~java
package com.acme.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateBuilder {
}
~~~

A developer marks a class that needs a generated builder:

~~~java
package com.acme.app;

import com.acme.annotations.GenerateBuilder;

@GenerateBuilder
public class Customer {
    private final String name;
    private final int age;

    public Customer(String name, int age) {
        this.name = name;
        this.age = age;
    }
}
~~~

A processor can detect `@GenerateBuilder`, inspect the members of the `Customer` class, and then generate `CustomerBuilder.java`. The compiler feeds the generated source into subsequent processing rounds and compiles it alongside other sources when the process finishes.

An annotation processor is not a library that the application calls as a method at runtime. It is executable code loaded by `javac` in the build environment. A processor may generate code used by the application, yet the processor JAR itself typically does not need to be present at runtime.

## 4. What Is the Processor Path Used For?

`javac` needs to know the location of classes implementing `javax.annotation.processing.Processor`. When the processor resides in a separate JAR, we use `-processorpath`:

~~~bash
javac \
    -classpath "lib/model-api.jar:lib/acme-annotations.jar" \
    -processorpath tools/acme-processor.jar \
    -processor com.acme.processor.CustomerProcessor \
    -s build/generated-sources \
    -d build/classes \
    src/com/acme/app/Customer.java
~~~

Here:

- `-classpath` provides the types used by the source, including the model API and annotation API.
- `-processorpath` tells `javac` where to find the processor implementation.
- `-processor` specifies the fully qualified name of the processor to run. When using this option, there is no need to rely on automatic processor discovery via a service file.
- `-s` specifies the directory containing generated sources.
- `-d` specifies the directory containing class files.

If the processor depends on other libraries, those JARs must also be on the processor path. For example:

~~~bash
javac \
    -classpath "lib/acme-annotations.jar:lib/model-api.jar" \
    -processorpath "tools/acme-processor.jar:tools/processor-utils.jar" \
    -processor com.acme.processor.CustomerProcessor \
    -s build/generated-sources \
    -d build/classes \
    src/com/acme/app/Customer.java
~~~

On Windows, replace `:` in the path list with `;`. The processor path only serves `javac` in loading the tool and its dependencies; it does not automatically make libraries on the processor path compile dependencies of the application.

## 5. How Does javac Find Processors?

There are two common ways to select processors:

**Specifying directly with -processor**

~~~bash
javac \
    -cp lib/acme-annotations.jar \
    -processorpath tools/acme-processor.jar \
    -processor com.acme.processor.CustomerProcessor \
    src/com/acme/app/Customer.java
~~~

This explicitly names the processor class to run. It is useful when a project has multiple processors and you only want to activate a specific subset.

**Automatic discovery via service provider configuration**

For a processor packaged on the processor classpath, the JAR can contain the file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

The file contents list the fully qualified name of each processor, one per line:

~~~text
com.acme.processor.CustomerProcessor
~~~

When `javac` is configured to perform annotation processing and scans the corresponding processor path, the service provider mechanism finds the classes registered in this file.

If the processor JAR has no service file, you can specify the processor name with `-processor`. Conversely, if using discovery, ensure the service file is at the exact path and the class names inside it are accurate.

## 6. What Does a Simple Processor Look Like?

A processor typically extends `AbstractProcessor`:

~~~java
package com.acme.processor;

import com.acme.annotations.GenerateBuilder;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import java.util.Set;

@SupportedAnnotationTypes("com.acme.annotations.GenerateBuilder")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class CustomerProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        for (var element :
                roundEnv.getElementsAnnotatedWith(GenerateBuilder.class)) {
            processingEnv.getMessager().printMessage(
                javax.tools.Diagnostic.Kind.NOTE,
                "Found @GenerateBuilder on " + element.getSimpleName(),
                element
            );

            // You can use processingEnv.getFiler()
            // to create sources, classes, or resources.
        }

        return true;
    }
}
~~~

Notable components:

- `@SupportedAnnotationTypes` declares the annotations the processor cares about.
- `@SupportedSourceVersion` declares the Java language version the processor supports.
- `process(...)` is called in each annotation processing round.
- `RoundEnvironment` provides the elements annotated in the current round.
- `processingEnv.getMessager()` sends notes or errors back to the compiler.
- `processingEnv.getFiler()` creates source files, class files, or resources.

A processor must be compiled and packaged before another `javac` command can load it via the processor path. In a real project, there are usually two build parts: build the processor JAR first, then use that JAR when compiling the application.

## 7. Annotation Processing Happens in Rounds

Annotation processing is not just a single method call. `javac` can run multiple rounds:

1. The compiler analyzes the sources and locates configured annotation processors.
2. Processors receive the relevant annotations and program elements in the current round.
3. Processors can generate new sources or resources via `Filer`.
4. Generated sources are fed into the next round for the compiler and processors to process.
5. When there are no more new sources to process, annotation processing finishes and the compiler completes compilation.

For example: in the first round, the processor detects `@GenerateBuilder` on `Customer` and creates `CustomerBuilder.java`. In the next round, `javac` can analyze `CustomerBuilder.java`, and other processors can also see the new source code.

A processor should avoid recreating the same file across multiple rounds. `Filer` will report an error if a file is created again within the same compilation. You should check annotations and round state so only necessary content is created.

## 8. Distinguishing Related javac Options

| Option | Role |
|---|---|
| -classpath, -cp, --class-path | Find classes/JARs that sources need to compile |
| -processorpath, --processor-path | Find annotation processors and processor dependencies |
| --processor-module-path | Find annotation processors packaged as named modules |
| -processor | Explicitly select the names of processors to run |
| -proc:none | Disable annotation processing |
| -proc:only | Run annotation processing without compiling sources into classes |
| -proc:full | Perform annotation processing and compilation |
| -s | Choose directory for processor-generated sources |
| -d | Choose directory for output class files |
| -Akey=value | Pass custom options to processors |

JDK version note: starting from JDK 23, you should not rely on `javac` automatically detecting and running processors simply because a processor JAR is present on the classpath. Configure processors explicitly with `-processor`, `-processorpath`, `--processor-module-path`, or request the appropriate processing mode with `-proc:full` or `-proc:only`. This keeps builds explicit and avoids unintentionally executing unintended processors.

## 9. Processors as Named Modules

In a project using JPMS, an annotation processor can also be packaged as an explicit module. In that case, the module descriptor registers the service provider:

~~~java
module com.acme.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with com.acme.processor.CustomerProcessor;
}
~~~

`java.compiler` contains annotation processing APIs such as `Processor`, `AbstractProcessor`, `RoundEnvironment`, and `ProcessingEnvironment`.

When compiling the application, use the processor module path:

~~~bash
javac \
    --class-path lib/acme-annotations.jar \
    --processor-module-path tools/com.acme.processor.jar \
    -s build/generated-sources \
    -d build/classes \
    src/com/acme/app/Customer.java
~~~

Key differences:

- `--processor-path` is typically used for processors located as classes/JARs on a classpath.
- `--processor-module-path` is used for processors organized as named modules with a service declaration in their module descriptor.
- `--module-path` is where dependency modules needed by the sources being compiled are located; do not confuse it with the processor module path.

In a modular build, you may need both a module path for source dependencies and a processor module path for processors. Each path serves its own role.

## 10. Example Comparing Two Configurations

Suppose there are three JARs:

~~~text
lib/
  customer-api.jar
  customer-annotations.jar
tools/
  customer-processor.jar
~~~

The application source uses `Customer` from `customer-api.jar` and the annotation from `customer-annotations.jar`. The processor implementation resides in `customer-processor.jar`.

Separated configuration:

~~~bash
javac \
    --class-path "lib/customer-api.jar:lib/customer-annotations.jar" \
    --processor-path tools/customer-processor.jar \
    -processor com.acme.processor.CustomerProcessor \
    -s build/generated \
    -d build/classes \
    src/com/acme/app/Customer.java
~~~

In this command:

- If `customer-api.jar` is omitted from the compile classpath, `javac` may report that it cannot find the `Customer` type or other types referenced by the source.
- If `customer-processor.jar` is omitted from the processor path and there is no processor on another configured path, `javac` cannot load `CustomerProcessor`.
- If `customer-annotations.jar` is omitted from the compile classpath, the source cannot reference `@GenerateBuilder`.
- Putting `customer-processor.jar` onto the compile classpath is not an explicit configuration to guarantee the processor runs; use the processor path or select the processor directly.

Separating paths also makes it easy to inspect which dependencies are build-only and which dependencies are genuinely required to compile the application.

## 11. Configuration in Maven and Gradle

Build tools usually provide dedicated configuration for annotation processors so you do not have to write the entire `javac` command manually.

**Maven**

In `maven-compiler-plugin`, processor dependencies can be declared using `annotationProcessorPaths`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <annotationProcessorPaths>
            <path>
                <groupId>com.acme</groupId>
                <artifactId>customer-processor</artifactId>
                <version>1.0.0</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

Libraries needed by the application's sources are still declared in `dependencies` with the appropriate scope. `annotationProcessorPaths` describes where the compiler plugin finds processors; it does not replace source dependencies.

**Gradle**

With the Java plugin, you can separate the annotation API and the processor:

~~~groovy
dependencies {
    compileOnly("com.acme:customer-annotations:1.0.0")
    annotationProcessor("com.acme:customer-processor:1.0.0")
}
~~~

`compileOnly` makes the annotation available during compilation without automatically adding it to the runtime classpath. `annotationProcessor` places the processor in the compile task's processor path configuration.

Depending on the library, the annotation API may be needed at runtime or packaged with the application; choose the scope according to retention and how the application uses the annotation. The processor implementation is usually only needed during the build.

## 12. Common Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| package ... does not exist or cannot find symbol in source | Missing library on compile classpath or module path | Add the right dependency to the source's classpath/module path |
| Processor does not run | Processor not on processor path, not selected, missing service registration, or annotation processing disabled | Check -processorpath, -processor, service file, and -proc |
| Annotation processor ... not found | Wrong processor name or JAR not on processor path | Check the fully qualified class name and JAR location |
| NoClassDefFoundError when loading processor | Missing dependency needed by the processor itself | Add that dependency to the processor path or processor module path |
| Annotation not recognized | Missing annotation JAR on compile classpath/module path or wrong annotation name used | Check imports and source dependencies |
| Generated source does not appear where expected | -s not configured or build tool uses a different generated directory | Check the source output directory of javac/build tool |
| Processor creates duplicate files | Multiple rounds or multiple processors create the same filename | Ensure each file is created only once and filenames do not conflict |
| Build runs processor on a newer JDK but did not run previously | Annotation processing activation behavior changed across JDK versions | Configure the processor explicitly and check the -proc option |

When diagnosing, determine which category the error belongs to first: the source cannot find a type, or the compiler cannot find the processor. The first relates to the compile classpath/module path; the second relates to the processor path, service registration, or annotation processing mode.

## Key Takeaways

The compile classpath (`-cp`/`--class-path`) provides the types that sources need to compile. The processor path (`-processorpath`/`--processor-path`) provides the annotation processor implementation and its dependencies for `javac` to load during the build. For processors packaged as named modules, use `--processor-module-path`. Processors can inspect annotations and generate sources via `Filer`; generated sources are fed into subsequent processing rounds. Separate application dependencies and build tools into distinct paths so builds are easy to control, reproducible, and do not accidentally execute unintended processors.
