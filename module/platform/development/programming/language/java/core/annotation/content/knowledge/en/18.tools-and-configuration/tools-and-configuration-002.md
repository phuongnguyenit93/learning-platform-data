# Registering an annotation processor in the Java module system (JPMS)

Starting with Java 9, the **Java Platform Module System (JPMS)** allows packaging an annotation processor as a **named module** and publishing it as a **service provider**. Instead of only placing the processor class name in a **META-INF/services** file, the module providing the processor declares it in **module-info.java**:

~~~java
module demo.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with demo.proc.GreetingProcessor;
}
~~~

When configured with **--processor-module-path**, the **javac** tool can discover and load the processor from the module that has published the service. This does not mean the application must have a runtime dependency on the processor module. The processor runs during compilation, whereas the application being compiled has its own modules and module path.

This article thoroughly presents how to register, package, and execute a processor in JPMS, the javac options, the differences from the traditional classpath, and a **Java 17+ example verified by actual compilation/execution in --release 17 mode**.

## 1. Three concepts to distinguish

**Annotation type** is a type declared with **@interface** and applied to source code, such as **@GenerateGreeting**.

**Annotation processor** is a class that implements **javax.annotation.processing.Processor**, usually extending **AbstractProcessor**. It receives the declaration/type model from the compiler, analyzes annotations, and can generate source files or report diagnostics.

**Named module** is a named modular unit declared with **module-info.java**. JPMS determines dependencies and service providers through directives such as **requires**, **exports**, **uses**, and **provides**.

A project can separate these roles as follows:

~~~text
demo.annotations                    demo.processor
  declares @GenerateGreeting          implements GreetingProcessor
  exports demo.api                    requires java.compiler
          │                           provides Processor with ...
          ▼                                      │
demo.app                                         │
  requires demo.annotations                      │
  uses @GenerateGreeting                         │
          │                                      │
          └─────── javac at compile time ────────┘
                        │
             Processor generates source
                        │
           demo.generated.Greeting
           belongs to module demo.app
~~~

**There is no mandatory \`requires demo.processor\` relationship in module demo.app.** The annotation library and the processor are two distinct roles. The application needs to see the **@GenerateGreeting** type at compile time, while the processor is loaded by **javac** from a separate path in the build environment.

In this example, we place all three roles into three named modules to clearly illustrate the boundaries. For a small project, you can also place the annotation type and the processor in the same module, provided that dependencies and the service are declared properly.

## 2. The processor's module-info.java: requires and provides

A minimal processor module:

~~~java
module demo.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with demo.proc.GreetingProcessor;
}
~~~

Explanation of each component:

- **module demo.processor**: the name of the named module containing the processor implementation class.
- **requires java.compiler**: allows the module to use the APIs exported by the standard **java.compiler** module: **javax.annotation.processing**, **javax.lang.model**, **javax.tools**.
- **provides javax.annotation.processing.Processor with demo.proc.GreetingProcessor**: publishes **GreetingProcessor** as the provider for the **Processor** service; the service lookup mechanism in the compiler environment can discover it.
- **demo.proc.GreetingProcessor** must actually be defined in module **demo.processor** and fulfill the Processor contract.
- For a typical processor class, it must be a **public class** with a **public no-argument constructor** (a public default constructor if the public class declares no other constructors). **AbstractProcessor** provides most of the implementation skeleton.

**\`exports demo.proc\` is not needed just to publish the processor via \`provides\`.** JPMS allows a service provider to be declared in a module without exporting the implementation package to ordinary consuming modules.

Distinction:

~~~java
// Correct for a module containing a processor implementation:
provides javax.annotation.processing.Processor
    with demo.proc.GreetingProcessor;

// Cannot replace provides:
// exports demo.proc;
~~~

**exports** allows other modules to access public types in the package under normal module readability rules. **provides** registers a **service provider** so that the service loading mechanism can find it. They serve two different functions.

### Why requires java.compiler instead of requires jdk.compiler?

**java.compiler** is the module containing the **public APIs** for annotation processing and the language model. **jdk.compiler** is the module containing the compiler implementation/tooling such as javac. A processor that only uses the standard **javax.annotation.processing** and **javax.lang.model** APIs typically needs **requires java.compiler** and does not need to depend on javac's internal APIs.

If the module dependency is declared incorrectly, compilation of the processor module may report that a package is not visible or inaccessible. You should prefer the standard APIs rather than importing internal **com.sun.tools.javac.*** classes simply because the processor is executed by javac.

## 3. How does module processor registration differ from a traditional service file?

Before JPMS, and for processors running on the traditional **classpath/processor path**, service discovery typically relied on the resource:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Its content is the fully qualified name of the provider class:

~~~text
demo.proc.GreetingProcessor
~~~

For a **named module loaded via the processor module path**, the appropriate registration mechanism is the **provides ... with ...** directive in **module-info.java**. That META-INF/services file is not needed in the processor module example in this article.

| Criterion | Traditional classpath processor | Named module processor |
| --- | --- | --- |
| How the service is published | **META-INF/services/javax.annotation.processing.Processor** | **provides ... with ...** in module-info.java |
| How to specify the path to javac | **-processorpath** or **--processor-path** | **--processor-module-path** |
| Annotation processing API dependency | java.compiler is present in the JDK; classpath does not declare requires | **requires java.compiler** |
| Packaging boundary | Unnamed module / traditional classpath | Named module with a descriptor |
| Where the provider resides | Class loaded from the processor path | Provider class belongs to the module that published it |
| Does the application need to require the processor? | No | No |

Merely having a **module-info.java** in a JAR is not enough to guarantee that javac will auto-discover the processor. **You must declare provides with the correct service type and implementation class, and configure the processor module path properly.**

### Do not confuse the four paths

**--module-path** (or **-p**) is used to resolve **the modules that the program being compiled depends on**.

**--processor-module-path** is used to locate **processors in named modules** for javac to load and execute during the compilation session.

**--processor-path** is used to locate **processors using the classpath/unnamed module mechanism**.

**--class-path** is the traditional classpath mechanism for the application's types; in some legacy configurations, it also serves as the search path for processors if no separate processor path is specified.

A properly built processor named module that is only placed on the application's **--module-path** **does not guarantee that javac will discover and run it**. Nor should you arbitrarily put the application's runtime dependencies on the processor path; the two environments serve different purposes.

## 4. Complete Java 17+ example: three named modules and an auto-discovered processor

The experiment uses:

- **demo.annotations**: the module exposing the **@GenerateGreeting** annotation.
- **demo.processor**: the module containing **GreetingProcessor** registered via **provides**.
- **demo.app**: the application module using the annotation and the **Greeting** class generated by the processor.

The processor generates **demo.generated.Greeting** with a **TEXT** constant. The application module accesses this constant at runtime. Thus, javac's auto-discovery of the processor can be observed through **the generated source file and stdout**, without relying on internal javac class names.

### 4.1. Source directory structure

~~~text
project/
└── src/
    ├── annotations/
    │   ├── module-info.java
    │   └── demo/
    │       └── api/
    │           └── GenerateGreeting.java
    ├── processor/
    │   ├── module-info.java
    │   └── demo/
    │       └── proc/
    │           └── GreetingProcessor.java
    └── app/
        ├── module-info.java
        └── demo/
            └── app/
                └── Main.java
~~~

Here, **src/annotations**, **src/processor**, and **src/app** are **source organization directory names chosen by this example**; the actual module names are determined by **module-info.java**, which are **demo.annotations**, **demo.processor**, and **demo.app**, respectively.

### 4.2. Module containing the annotation type

**File src/annotations/module-info.java:**

~~~java
module demo.annotations {
    exports demo.api;
}
~~~

**File src/annotations/demo/api/GenerateGreeting.java:**

~~~java
package demo.api;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {
}
~~~

**exports demo.api** allows module demo.app to use the public annotation type **demo.api.GenerateGreeting**. **@Target(TYPE)** allows it to be applied to class declarations. **@Retention(SOURCE)** is sufficient for the processor to read during source compilation, while the annotation is not retained in the class file for runtime reflection.

Module **demo.annotations** does not need **requires java.compiler**, because this annotation's code only uses the **java.lang.annotation** package, which belongs to **java.base**, a module implicitly read by all modules.

### 4.3. Module containing the processor and service registration

**File src/processor/module-info.java:**

~~~java
module demo.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with demo.proc.GreetingProcessor;
}
~~~

**File src/processor/demo/proc/GreetingProcessor.java:**

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
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.api.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {

        if (round.processingOver() || generated) {
            return true;
        }

        for (TypeElement annotation : annotations) {
            for (Element element :
                    round.getElementsAnnotatedWith(annotation)) {

                try {
                    JavaFileObject file = processingEnv.getFiler()
                            .createSourceFile(
                                    "demo.app/demo.generated.Greeting",
                                    element);

                    try (Writer writer = file.openWriter()) {
                        writer.write("package demo.generated;\n");
                        writer.write("public final class Greeting {\n");
                        writer.write("  private Greeting() {}\n");
                        writer.write(
                                "  public static final String TEXT = "
                                + "\"generated by demo.processor\";\n");
                        writer.write("}\n");
                    }

                    generated = true;
                    return true;

                } catch (IOException ex) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "Generation failed: " + ex.getMessage(),
                            element);
                    return true;
                }
            }
        }

        return true;
    }
}
~~~

**Significance for module registration:**

1. **GreetingProcessor** extends **AbstractProcessor**, meaning it is capable of fulfilling the **Processor** service contract.
2. **@SupportedAnnotationTypes("demo.api.GenerateGreeting")** declares the annotation type that the processor is interested in. It does not replace **provides**: one provides annotation filtering information, while the other is service registration.
3. **@SupportedSourceVersion(RELEASE_17)** specifies the language level that the processor declares it supports.
4. **round.getElementsAnnotatedWith(annotation)** finds declarations annotated with **@GenerateGreeting** in a processing round.
5. **processingEnv.getFiler().createSourceFile(...)** creates the source file. The **demo.app/** prefix is **the name of the module containing the generated class**, indicating the destination when processing a named module; the remainder **demo.generated.Greeting** is the fully qualified name of the generated type.
6. **generated** prevents attempting to generate the same source file multiple times across processing rounds. A processor can be invoked multiple times during a single compilation.
7. **return true** indicates that the processor claims the annotation types it receives; it is not a success signal for the java command running the application.
8. When a file-writing error occurs, **Messager** receives **Diagnostic.Kind.ERROR** so the compiler reports an informative error.

The example intentionally processes only **one class** annotated with GenerateGreeting to guarantee generating a single file. A production processor needs to handle multiple annotated elements, multiple input modules, file name collisions, round states, and more comprehensive diagnostics.

**There is no import of demo.api.GenerateGreeting in the processor.** It receives the annotation type via **TypeElement** and the fully qualified name declared in **@SupportedAnnotationTypes**. Therefore, demo.processor does not need **requires demo.annotations**; this is how the example keeps the dependency between the processor and the annotation library simple.

### 4.4. Application module using the annotation

**File src/app/module-info.java:**

~~~java
module demo.app {
    requires demo.annotations;
}
~~~

**File src/app/demo/app/Main.java:**

~~~java
package demo.app;

import demo.api.GenerateGreeting;
import demo.generated.Greeting;

@GenerateGreeting
public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.TEXT);
    }
}
~~~

The application has **requires demo.annotations** to see the exported annotation type. **There is no requires demo.processor**, because the processor is only a build-time tool.

When Main.java is first created, the **demo.generated.Greeting** class does not yet exist in the source code we wrote. It will be generated by the processor when javac compiles the application. This experiment demonstrates that the service registered in module-info.java was loaded properly by the compiler.

### 4.5. Three-step compilation

Inside the **project** directory, create the output directories. On Linux/macOS with bash:

~~~bash
mkdir -p mods/demo.annotations mods/demo.processor mods/demo.app generated
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force mods/demo.annotations,mods/demo.processor,mods/demo.app,generated | Out-Null
~~~

**Step A: compile the annotation module.**

~~~bash
javac --release 17 -proc:none -d mods/demo.annotations src/annotations/module-info.java src/annotations/demo/api/GenerateGreeting.java
~~~

Key output:

~~~text
mods/demo.annotations/module-info.class
mods/demo.annotations/demo/api/GenerateGreeting.class
~~~

**-proc:none** avoids unintended annotation processing while building these initial tooling modules.

**Step B: compile the processor module.**

~~~bash
javac --release 17 -proc:none -d mods/demo.processor src/processor/module-info.java src/processor/demo/proc/GreetingProcessor.java
~~~

Key output:

~~~text
mods/demo.processor/module-info.class
mods/demo.processor/demo/proc/GreetingProcessor.class
~~~

Both modules have been compiled into named modules because the compiled class files include **module-info.class**. The **mods** directory acts as a module path containing two separate modules, each in its own subdirectory.

**Step C: compile the application module with the processor module path.**

~~~bash
javac --release 17 --module-path mods --processor-module-path mods -d mods/demo.app -s generated src/app/module-info.java src/app/demo/app/Main.java
~~~

This is the **key command**:

- **--module-path mods**: the compiler resolves the application's **requires demo.annotations**.
- **--processor-module-path mods**: the compiler searches for **named modules** publishing an implementation of **javax.annotation.processing.Processor**.
- In this example, **demo.processor** has **provides**, so it is discovered **without** specifying **-processor demo.proc.GreetingProcessor**.
- **-d mods/demo.app**: places the compiled class files of the application and the generated type into the module output.
- **-s generated**: places the Java source files generated by the processor into the specified directory.
- **--release 17**: checks Java SE 17 source/APIs and generates corresponding bytecode.

With a **single-module app** compilation layout like this example, the generated source typically has the path:

~~~text
generated/demo/generated/Greeting.java
~~~

And the class is compiled to:

~~~text
mods/demo.app/demo/generated/Greeting.class
~~~

Do not mistake the **demo.app/** prefix in the name passed to **Filer.createSourceFile** for a folder that always appears in the physical path under generated-src: Filer uses that prefix to **specify the target named module receiving the output**. The actual path depends on how javac/Filer manages output locations and whether compilation is in single-module or multi-module mode. When using this configuration with javac, the verified result is the file **generated/demo/generated/Greeting.java**.

**Step D: run the application using the module path.**

~~~bash
java --module-path mods --module demo.app/demo.app.Main
~~~

**Stdout of the java command:**

~~~text
generated by demo.processor
~~~

The compilation commands are not shown as Main's stdout. To observe whether javac actually invokes the processor, you can temporarily use:

~~~bash
javac --release 17 --module-path mods --processor-module-path mods -XprintProcessorInfo -d mods/demo.app -s generated src/app/module-info.java src/app/demo/app/Main.java
~~~

The **-XprintProcessorInfo** option instructs javac to print information about the processor being run and the annotations it processes; this output is intended for diagnostics, not as stable output for application testing. If you rerun the command, you should clean **generated** and **mods/demo.app** first to avoid leftover stale sources or duplicate generated files.

### Empirical verification

The example above was **successfully compiled and run using javac/JDK 21 with --release 17**: javac discovered **demo.proc.GreetingProcessor** via the named module's service registration, generated **Greeting.java**, compiled the application, and printed the exact string **generated by demo.processor**. The --release 17 mode checks Java 17 source/API compatibility; if you need absolute assurance for a specific JDK 17 distribution, you should run the same commands on your actual deployment toolchain.

## 5. Packaging the processor module as a modular JAR

For real-world applications, a processor is typically packaged as a **modular JAR**. After Step B, you can run:

~~~bash
mkdir -p jars
jar --create --file jars/demo.processor.jar -C mods/demo.processor .
~~~

On PowerShell, create the directory using **New-Item -ItemType Directory -Force jars** before running the jar command. The JAR file contains **module-info.class** and **demo/proc/GreetingProcessor.class**.

You can place the processor JAR in a dedicated directory, for example **processor-libs**; then change the compiler option to:

~~~bash
javac --release 17 --module-path mods --processor-module-path jars/demo.processor.jar -d mods/demo.app -s generated src/app/module-info.java src/app/demo/app/Main.java
~~~

This is the option of using a **JAR instead of an exploded module directory**. If the processor depends on other library modules, the required dependency modules must be placed on the appropriate processor module path so JPMS can resolve them. Since the example processor only requires **java.compiler** (a JDK module), the JAR containing the processor is sufficient to load the service.

**Environment note:** If Step C has already been run and generated/class outputs still exist, clean the target output before verifying a different packaging configuration. Otherwise, a successful result might merely reflect leftover artifacts rather than proving that the processor inside the JAR was reloaded properly.

### How to tell whether a JAR is a named module

You can inspect the module descriptor using:

~~~bash
jar --describe-module --file jars/demo.processor.jar
~~~

The key declarations to look for are **requires java.compiler** and **provides javax.annotation.processing.Processor with demo.proc.GreetingProcessor**. The exact labels of the lines displayed in the output depend on the tool, but the service registration content must be present.

A JAR merely residing on the application's **--module-path** does not mean it is an executed processor. You must configure **--processor-module-path** or the equivalent build tool setting.

## 6. JPMS ServiceLoader: how do uses and provides differ?

Syntax for providing a service:

~~~java
module demo.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
        with demo.proc.GreetingProcessor;
}
~~~

**provides** is written in the module **containing the provider**. Under JPMS, the **javax.annotation.processing.Processor** service is consumed by the compiler/tooling through the corresponding service loading mechanism.

A module **written to consume a service itself** via **ServiceLoader.load(Processor.class)** usually needs to declare **uses javax.annotation.processing.Processor** in its own module-info.java, depending on the design and module readability. However:

- **demo.app is not a service consumer** in this example: it is only the module being compiled and does not need **uses Processor**.
- **demo.processor is the provider**, so it uses **provides**; do not write **uses** in place of provides.
- **javac**/the compiler infrastructure is responsible for the processor discovery/instantiation mechanism; you do not need to add **uses** to the app just for javac to invoke the provider.

**A common misconception:** Adding **uses javax.annotation.processing.Processor** to the application's **module-info.java** does not cause javac to automatically find a suitable processor. You must register the provider in the module containing the processor and configure the processor search path.

## 7. When should you use -processor explicitly?

In this example, **--processor-module-path mods** and the **provides** directive are sufficient for javac to discover the processor.

In some projects, you may want to specify an explicit list of processors via:

~~~text
-processor demo.proc.GreetingProcessor
~~~

The javac **-processor** option explicitly specifies **the processor class names to run**, instead of scanning available processors through default discovery. It is useful when you want to precisely control the set of processors, limit the impact of other providers on the search path, or perform diagnostics.

However, **-processor** does not fix a broken module descriptor, nor does it make missing module dependencies appear on their own. If the processor is packaged as a named module, you still have to use a compatible module path configuration so the compiler can load the provider class and its dependencies. For this article, you should learn the standard **provides + --processor-module-path** approach first.

**The -proc:none option** disables annotation processing during compilation. **-proc:only** instructs javac to perform only annotation processing without generating class files for the program via the full compilation pipeline. With JDK 17, when you want the processor to generate source and still have the program compiled, use the normal processing configuration as in Step C without adding -proc:only.

**-Akey=value** passes an option to a processor that declares/reads that option via **ProcessingEnvironment.getOptions()**. It does not replace module registration. The current example does not define a custom -A option.

A cross-version difference: newer javac releases may change how annotation processors are enabled by default to avoid running processors unintentionally. For reproducible builds, you should explicitly configure the processor search path and processing behavior according to the javac documentation of **the JDK version in use**. The example was verified in **--release 17** mode and discovers the provider via **--processor-module-path**.

## 8. How can a processor read annotations from another named module?

Inside the processor:

~~~java
@SupportedAnnotationTypes("demo.api.GenerateGreeting")
public final class GreetingProcessor extends AbstractProcessor {
    // ...
}
~~~

The fully qualified name of the annotation appears in the annotation-type filter. In the runnable example, **demo.processor has no requires demo.annotations** and does not directly import GenerateGreeting; it receives a TypeElement from the compiler model.

~~~java
for (TypeElement annotation : annotations) {
    for (Element element :
            round.getElementsAnnotatedWith(annotation)) {
        // Analyze the annotated declaration.
    }
}
~~~

Thanks to **TypeElement** and **Element**, the processor can inspect the symbols of the code being compiled without necessarily having a runtime dependency on that annotation class.

If the processor wants to use the **GenerateGreeting.class** class literal directly in its own code, the annotation type must be made available to the processor at compile time and load time, along with adding the appropriate module dependency if it is a named module. This option can be useful in large programs but increases coupling; the compiler API model is usually a flexible way to write processors that inspect many types.

**Do not use reflection to try to load uncompiled application classes** via Class.forName inside a processor. During source processing, the declaration may not yet exist as a class file. You must use **TypeElement**, **TypeMirror**, **AnnotationMirror**, and related APIs.

### Which named module should code be generated into?

A specific aspect of generating source in JPMS:

~~~java
processingEnv.getFiler().createSourceFile(
    "demo.app/demo.generated.Greeting",
    originatingElement);
~~~

The string before the **/** is **the named module's name**; the part after is **the fully qualified name of the class to generate**. Explicitly specifying the module is helpful when compiling multiple named modules or when the compiler cannot determine the generation target on its own.

In some situations, the compiler can infer the module from the **originating elements**, though you should not rely on guesswork in complex multi-module projects. If the module name or source output path is wrong, Filer may report an error or generate code in the wrong location. For a real processor, you should check the Filer API and the build tool's module compilation mode.

## 9. Diagnosing configuration errors from symptoms

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Processor module fails to compile because package **javax.annotation.processing** is not visible | Missing **requires java.compiler** | Add requires to the processor's module-info.java |
| Provider class exists, yet the processor does not run | Missing **provides ... with ...**, wrong service type, or wrong processor path | Check the module descriptor and **--processor-module-path** |
| App cannot see **@GenerateGreeting** | demo.app is missing **requires demo.annotations**, or demo.annotations does not export the package | Add requires/exports and place the annotation module on --module-path |
| App reports **demo.generated.Greeting** cannot be found | Processor did not run, generation failed, or the old generated class was cleaned up/in the wrong module | Check javac diagnostics, -XprintProcessorInfo, -s, and Filer |
| Added **requires demo.processor** in the app, yet the processor still does not run | requires does not register a service for javac | Use provides and the processor module path |
| Only added **META-INF/services**, while the processor is a named module on the module path | Service publication method is incorrect for the JPMS case | Declare **provides** in module-info |
| Only wrote **exports demo.proc** | exports is not equivalent to provides | Declare provides with the correct service |
| Provider class is not public or has an unsuitable constructor | The service provider does not satisfy the contract | Define a public processor with a public no-arg constructor |
| Calling **createSourceFile(...)** with the same name across multiple processing rounds | Filer does not allow creating the same file repeatedly | Use state/a stable output identifier |
| Using **--processor-path** for a named modular processor while expecting JPMS discovery | Choosing the classpath/unnamed module mechanism | Use **--processor-module-path** |
| Using **--module-path** for the processor without placing it on the processor module path | The application module resolution path is not the processor search path | Configure both paths explicitly |
| Using **-proc:none** in Step C | Disables annotation processing | Remove -proc:none when compiling the app |
| Assuming the processor must be on the runtime module path | The processor is for build time, not required by the compiled application | Clearly separate build-time and runtime |
| Repeated testing with old generated files | Results are skewed by leftover artifacts | Clean the generated directory and app output before each run |

**Sequential verification tip:** first verify that the processor's **module-info.class** contains provides, then verify that the module appears on **--processor-module-path**, and finally check whether javac invokes the processor and generates new source files. Do not start by adding a bunch of unnecessary **--add-opens**, **--add-exports**, or **requires** directives; they easily mask the root configuration error.

## 10. Difference between build-time modules and runtime modules

When **javac** processes an application, the compiler's execution environment and the environment of the program being compiled are **two different contexts**.

- **The processor** is executed by javac during the build. It needs to be able to read the **java.compiler** API and the processor's own module dependencies.
- **The application code** being compiled is resolved according to **--module-path** and the requires/exports of **demo.app**.
- **The generated code** in this article is emitted into **demo.app**, and then javac compiles it into classes in the same module as the application.
- When running **java --module-path mods --module demo.app/demo.app.Main**, main reads the generated class. It does not call **GreetingProcessor.process(...)**.

You can deploy at runtime with only module **demo.app** and module **demo.annotations** if the application still declares requires demo.annotations. The processor module does not need to be supplied as a runtime dependency if the application does not reference it. Optimizing runtime dependencies is a common reason to separate the annotation library and the processor module.

**Note:** An annotation declared with **RetentionPolicy.SOURCE** is still visible to the compiler and processor during source processing; it is not present in the class file to be read back via runtime reflection. Annotation processing is not synonymous with runtime reflection, even though both involve annotations.

## 11. Things to keep in mind when using Maven, Gradle, and IDEs

With build tools, the exact javac command is usually generated automatically. Whether using Maven, Gradle, or an IDE, make sure the same principles are followed:

1. The packaged processor has a **module-info.java / module-info.class** with the exact **provides Processor with ProviderClass**, if running under the named module mechanism.
2. The processor is placed on the **annotation processor module path** or equivalent configuration that the build tool actually passes to javac.
3. The annotation/API modules imported by application code are present on the **compilation module path**, exported, and requested via **requires**.
4. Generated code is placed into the correct **module** and compilation output, not mistakenly copied into the processor module's directory.
5. Enable processor diagnostics and inspect the generated source after a clean build.
6. Incremental/repeated builds must properly clean up stale artifacts and avoid generating duplicate classes/sources with the same name.

**Do not conclude that the processor ran just because you see the processor dependency in the build file.** Different versions of build tools/IDEs have their own processor discovery options and JPMS handling mechanisms. Check the actual configuration passed to javac, especially the distinction between the classpath processor path and the processor module path.

Some projects still use processors via the classpath mechanism even when application code is built as named modules. This is a valid configuration, but **it is not equivalent to a processor registered as a named module via provides**. The topic of this article is the standard JPMS route with **--processor-module-path**.

## 12. Self-check exercises

**Exercise 1.** In the module containing **GreetingProcessor**, which directive is required to provide the processor service?

~~~java
module training.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
        with training.proc.GreetingProcessor;
}
~~~

Answer: **provides ... with ...** is the directive that registers the service; **requires java.compiler** allows the processor implementation to use the standard APIs.

**Exercise 2.** If you only add **exports training.proc**, will javac automatically discover GreetingProcessor on the processor module path? **Not merely because of exports**; an exported package does not automatically register a provider. There must be an appropriate **provides** directive or a valid mechanism specifying the processor.

**Exercise 3.** Why does the application module using **@GenerateGreeting** need **requires demo.annotations**, yet usually does not need **requires demo.processor**? The annotation type is the API referenced by the application source, whereas the processor is a tool loaded by the compiler at build time from a separate path.

**Exercise 4.** Distinguish:

~~~text
--module-path mods
--processor-module-path mods
~~~

Both use the same **mods** path value in the experiment, yet their meanings differ: the first line is used to resolve modules of the program being compiled, while the second line is used to locate processor modules published via a service.

**Exercise 5.** If you remove **provides** from demo.processor's module-info.java and recompile the processor and app, when relying only on processor discovery, what symptom may appear? **The processor is not found or invoked**, causing the generated class not to exist and the app to fail to resolve **demo.generated.Greeting**.

**Exercise 6.** If the processor calls **createSourceFile("demo.app/demo.generated.Greeting", element)**, what is the role of the part before the /? It is **the name of the named module that will receive the generated source**; it is not a package.

**Exercise 7.** Why can an annotation with SOURCE retention still be used by the processor in the example? Because the processor operates on sources/symbols at compile time. A SOURCE annotation is not retained in the class file for regular Java reflection to query at runtime.

**Exercise 8.** Can a modular processor be loaded from the app's **--module-path** instead of **--processor-module-path**? Simply putting the processor on the app's module resolution path is not the standard way to configure annotation processor discovery in this example; you should use **--processor-module-path** so javac loads the service provider in its proper role.

## 13. Official documentation and references

- **Java SE 17 — The javac Command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html — sections on **Annotation Processing**, **--processor-module-path**, **--processor-path**, **--module-path**, **-processor**, **-s**, **-d**, **--release**, **-proc:none**, **-proc:only**.
- **Java SE 17 — Module java.compiler:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/module-summary.html — the javax.annotation.processing, javax.lang.model, and javax.tools packages exported by this module.
- **Java SE 17 — Interface Processor:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html — instantiation contract and processing rounds.
- **Java SE 17 — Filer:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html — rules for creating source files and module prefixes for named modules.
- **JLS Java 17 §7.7.4 — Service Provision:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.4 — meaning of **provides ... with ...** in module declarations.
- **Java SE 17 — ServiceLoader:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html — mechanism for locating/loading service providers.

**Conclusion:** For an annotation processor packaged in a **named module**, declare **requires java.compiler** and **provides javax.annotation.processing.Processor with ...** in the processor's **module-info.java**; build that module first, and then configure **javac --processor-module-path** to locate the provider. **--module-path** resolves the application code's dependencies, whereas the processor module path resolves the compile-time processing tooling. If you keep these two roles separate, registering and verifying processors in JPMS will be clear, reproducible, and easy to diagnose.
