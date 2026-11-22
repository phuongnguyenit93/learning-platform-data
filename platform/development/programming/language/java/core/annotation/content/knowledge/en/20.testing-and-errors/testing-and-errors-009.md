# AnnotationFormatError, FilerException, and How to Isolate the Root Cause

## 1. Two Errors Both Related to Annotations but Occurring at Different Stages

In Java, annotations can be **read from bytecode at runtime** or **processed by an annotation processor at compile time**. The two errors below occur in two different mechanisms:

| Criterion | AnnotationFormatError | FilerException |
| --- | --- | --- |
| Exception type | java.lang.annotation.AnnotationFormatError extends Error | javax.annotation.processing.FilerException extends IOException |
| Typical timing | JVM/reflection library reads annotations from a .class file | javac or a build tool is running an annotation processor |
| Detecting component | Java runtime annotation parser | Filer provided by the annotation processing environment |
| Nature | Annotation data in the class file is invalid/cannot be parsed in the proper format | Processor requests to re-create a file or type name that Filer does not allow creating |
| What to inspect first | Actual loaded class file, annotation metadata, bytecode-modifying tools | Generated file name, which processor created it, which processing round, input files |
| Resolution approach | Identify the corrupted/invalid class file, fix the generating source or bytecode transformation, and rebuild | Ensure each output name is created at most once per processing run, and clearly define file creation ownership |

**Do not conflate the two errors.** An error occurring when reflection reads an annotation is not enough to conclude that a processor has a problem; conversely, FilerException does not prove that annotation bytecode is corrupted.

## 2. AnnotationFormatError: Causes and Trigger Conditions

### 2.1. How Are Annotations Stored in .class Files?

Annotations have retention policies:

- **SOURCE:** used at compile time and not retained to be read via reflection at runtime.
- **CLASS:** recorded in the class file, though typically not exposed through reflection APIs that read runtime annotations.
- **RUNTIME:** recorded in the class file and can be exposed by the JVM for reflection.

At the class file level, annotations reside in attributes such as **RuntimeVisibleAnnotations** and **RuntimeInvisibleAnnotations**; annotations on methods, parameters, or type uses have corresponding metadata locations. The annotation parser must properly read the structure, value types, and constant pool references. If the encoded annotation data is corrupted or structurally malformed, the Java runtime may throw AnnotationFormatError.

Causes commonly worth investigating:

1. **Improperly transformed .class files:** bytecode instrumentation, weaving, obfuscation, shading, or post-processing tools generate invalid annotation attributes.
2. **Corrupted or inconsistently assembled artifacts:** a class file in a JAR differs from the expected version, was incorrectly replaced, or was corrupted during the release process.
3. **Bytecode generation tools manually constructing invalid metadata:** for example, using ASM or a class-file manipulation library but writing an incorrect element type or annotation format.
4. **Class loader loading a different version:** the application inspects new source code, yet at runtime an old class or a different JAR on the classpath is loaded.

Not every runtime annotation error should be called AnnotationFormatError. For example, missing a required annotation element when reading can lead to **IncompleteAnnotationException**; a value that is no longer compatible with the annotation declaration can cause **AnnotationTypeMismatchException**; a missing enum constant can lead to **EnumConstantNotPresentException**; and a referenced type that does not exist can lead to **TypeNotPresentException**. Each of these errors has its own diagnostic meaning.

### 2.2. Example of Working Reflection in Java 17+

The following example is a **normal execution path**, intended to pinpoint when the reflection API asks the runtime to read an annotation. This valid Java source code does not attempt to create corrupted bytecode to trigger AnnotationFormatError.

File **demo/InspectAnnotations.java**:

~~~java
package demo;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Role("service")
public class InspectAnnotations {
    public static void main(String[] args) {
        Role role = InspectAnnotations.class.getAnnotation(Role.class);
        System.out.println("role=" + role.value());
    }
}
~~~

Compile and run while in the directory containing the **demo** subdirectory:

~~~bash
javac -d out/classes demo/InspectAnnotations.java
java -cp out/classes demo.InspectAnnotations
~~~

Exact output when the code and class file are intact:

~~~text
role=service
~~~

The **Class.getAnnotation(Role.class)** call is an example of a metadata access point. In real programs, the stack trace may originate from calls such as **getDeclaredAnnotations()**, from an annotation-scanning framework, or from an internal Java reflection class. Simply declaring an annotation in Java source does not by itself cause AnnotationFormatError.

### 2.3. Evidence-Based Isolation of AnnotationFormatError

Follow these steps in order to find the **actual offending class file**:

1. **Preserve the full stack trace**, including the **Caused by** chain if present. Identify which operation is reading the annotation: component scanning, reflection on a class, method, field, or parameter, or a mapping library.
2. **Identify where the class is loaded from.** In diagnostic code, you can print **SomeClass.class.getProtectionDomain().getCodeSource()** when a CodeSource is available; or inspect the classpath/module path and JAR contents. Do not assume the class comes from the build directory you just compiled.
3. **Inspect the metadata in the exact failing artifact** using **javap -v -p**. For example:

~~~bash
javap -classpath app.jar -v -p demo.InspectAnnotations
~~~

Examine the **RuntimeVisibleAnnotations** and **RuntimeInvisibleAnnotations** attributes, the constant pool, and the corresponding class/method locations. If javap cannot parse the class file, that is also a sign worth investigating; the actual message depends on the JDK version and the form of corruption.

4. **Compare before and after bytecode transformation.** If the output compiled by javac works fine but the artifact after instrumentation/obfuscation fails, temporarily disable transformation steps one by one to isolate the tool causing the corruption. Compare checksums of the .class/JAR versions.
5. **Perform a clean build and test a minimal artifact** on the exact JDK/classpath experiencing the error. Only after preserving the evidence should you delete old outputs, update dependencies, or restore artifacts.
6. **Check compatibility between bytecode-modifying libraries and the class file format.** If an older tool does not understand the format generated by a newer JDK version, upgrade the tool or adjust its configuration appropriately; do not randomly alter annotations in source code to mask invalid bytecode.

Example of an isolation trace in Java (illustrative snippet placed where **demo.InspectAnnotations** can be referenced):

~~~java
Class<?> target = demo.InspectAnnotations.class;
var source = target.getProtectionDomain().getCodeSource();
System.out.println(source == null ? "<unknown code source>" : source.getLocation());
target.getDeclaredAnnotations(); // a point that may trigger metadata parsing
~~~

This snippet is **not a standalone program**; the printed output depends on where the class is actually loaded from. If the application uses multiple class loaders, you must also verify the class loader and module.

Because AnnotationFormatError is an **Error**, the standard handling is to fix the class file data or the tool that produced it. Only catch the error at a diagnostic tool boundary if you need to record evidence; do not swallow the Error and let the application keep running as if the metadata were valid.

## 3. FilerException: Causes and File Creation Rules

### 3.1. How Filer Operates in Annotation Processing

Annotation processors run inside javac via the **javax.annotation.processing** API. The **ProcessingEnvironment** provides a **Filer**, an object used to create sources, classes, and resources:

- **createSourceFile(qualifiedName, originatingElements...)**: requests creation of a Java source file by type name.
- **createClassFile(qualifiedName, originatingElements...)**: requests creation of a class file.
- **createResource(location, packageName, relativeName, originatingElements...)**: requests creation of a resource at the specified location and path.

An annotation processing run may consist of **multiple rounds**. When a processor creates new source code, javac may pass that source code into the next round. Within the same annotation processing invocation, Filer tracks the names/files already created; creating the same name again or attempting to create a type that is part of the initial input set can throw **FilerException**. Different processors can also collide if they generate the same name.

Important note: **an already-existing file from a previous build does not automatically guarantee a FilerException**. The deciding factor is the file-creation state in the **current processing run**, Filer's rules, and the input names. Deleting the generated directory can be helpful when investigating dirty builds, but it will not fix a repeated **createSourceFile** call within the same compilation pass.

### 3.2. Minimal Example Intentionally Triggering FilerException

You can run the example below on **JDK 17 or higher**. This is an **intentional** error: the processor creates the same source name twice. The three files are placed in the **demo** directory.

File **demo/GenerateMarker.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateMarker {
}
~~~

File **demo/App.java**:

~~~java
package demo;

@GenerateMarker
public class App {
    public static void main(String[] args) {
        System.out.println("App started");
    }
}
~~~

File **demo/DuplicateProcessor.java**:

~~~java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.FilerException;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.GenerateMarker")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class DuplicateProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateMarker.class)) {
            String name = "demo.GeneratedApp";
            try {
                JavaFileObject file =
                        processingEnv.getFiler().createSourceFile(name, element);
                try (Writer writer = file.openWriter()) {
                    writer.write("package demo;\n"
                            + "public class GeneratedApp {}\n");
                }

                // Intentionally incorrect: this name was already created in the same processing run.
                processingEnv.getFiler().createSourceFile(name, element);
            } catch (FilerException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Duplicate output: " + ex.getClass().getSimpleName(),
                        element);
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, "I/O: " + ex.getMessage(), element);
            }
        }
        return true;
    }
}
~~~

Create the three output directories **out/processor**, **out/classes**, and **out/generated** beforehand, then run from the parent directory of **demo**:

~~~bash
javac -proc:none -d out/processor demo/GenerateMarker.java demo/DuplicateProcessor.java
javac -cp out/processor -processorpath out/processor -processor demo.DuplicateProcessor -s out/generated -d out/classes demo/App.java
~~~

The first command succeeds. The second command is **expected to fail**; the core part of the diagnostic contains:

~~~text
Duplicate output: FilerException
~~~

The location line, error count, and additional explanation may vary by javac/JDK. There is no stdout from **java demo.App** for the failed compilation case. The exact conclusion is that **the second createSourceFile call in the same run causes FilerException**, even though the first call properly closed the Writer.

On Windows, directories can be created with PowerShell **New-Item -ItemType Directory -Force**; on Unix shells, use **mkdir -p**. The two **javac** commands above do not depend on the classpath separator character because each path contains only one entry.

### 3.3. Fixing the Processor: Stable Output Names and Writing Only Once

Replace **demo/DuplicateProcessor.java** with the **demo/SafeProcessor.java** version below (keeping **GenerateMarker.java** and **App.java**). Each annotated class receives a name derived from the class name; the **generatedNames** set helps guard against the processor encountering the same name again across rounds.

~~~java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.HashSet;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.FilerException;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.GenerateMarker")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class SafeProcessor extends AbstractProcessor {
    private final Set<String> generatedNames = new HashSet<>();

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateMarker.class)) {
            if (!(element instanceof TypeElement type)) {
                continue;
            }

            String name = "demo.Generated" + type.getSimpleName();
            if (!generatedNames.add(name)) {
                continue; // Already created or decided to create this name.
            }

            try {
                JavaFileObject file =
                        processingEnv.getFiler().createSourceFile(name, type);
                try (Writer writer = file.openWriter()) {
                    writer.write("package demo;\n"
                            + "public class Generated" + type.getSimpleName()
                            + " {}\n");
                }
            } catch (FilerException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Tên đầu ra bị trùng: " + name + " - " + ex.getMessage(),
                        type);
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Không tạo được " + name + ": " + ex.getMessage(),
                        type);
            }
        }
        return true;
    }
}
~~~

Compile the fixed processor, then compile the application:

~~~bash
javac -proc:none -d out/processor demo/GenerateMarker.java demo/SafeProcessor.java
javac -cp out/processor -processorpath out/processor -processor demo.SafeProcessor -s out/generated -d out/classes demo/App.java
java -cp out/classes demo.App
~~~

Exact output of the **java** command:

~~~text
App started
~~~

The generated file is **out/generated/demo/GeneratedApp.java** and the corresponding class is compiled into **out/classes**. If you need to rerun the example from scratch to remove test artifacts, save any necessary logs and then build in a new output directory or clean the exact test output directories.

**Limitation of this fix:** The Set here only prevents **SafeProcessor** itself from creating duplicate names. It does not resolve collisions with other processors, with input type names, or cases where multiple classes in different packages share the same simple name and thus map to the same **demo.GeneratedX**. In a real system, you need to design name mapping from a qualified name or appropriate identifier key, explicitly define rules for who owns each output, and avoid having multiple processors write over the same path.

### 3.4. Common FilerException Scenarios

| Scenario | Symptom | Resolution |
| --- | --- | --- |
| The same processor calls createSourceFile twice for the same name | Logs show the same qualified name appearing twice in a single compile | Track created names; call creation only once |
| A processor runs across multiple rounds and re-creates an earlier name | Subsequent occurrence has the same name but in a different round | Inspect roundEnv, log the round and name; avoid rewriting |
| Two processors generate the same type or resource | Same path, two processors/triggers | Define output ownership, configure processors, rename appropriately |
| A processor attempts to create a source colliding with an input type | Generated name matches a file currently being compiled by javac | Do not generate over input sources; change the output name |
| Output name derived from simple name is not unique | Two different inputs resolve to the same GeneratedX | Use the fully qualified name or a mapping scheme that guarantees uniqueness |
| Incremental build re-runs a step and causes overlap | Fails only with a specific build configuration or processor | Distinguish duplicate errors within a single invocation from stale output; check processor path, generated-source roots, cache, and run history |

**originatingElements** passed to createSourceFile tells incremental processing tools which input an output is tied to, but it is **not** an automatic deduplication key. Do not rename files with random numbers to evade FilerException: doing so makes output non-reproducible and tends to accumulate junk files.

## 4. Quick Isolation Workflow When You Only Have Error Logs

### Step 1: Identify the Stage

- Did the error occur in the **javac** command, Maven compile, Gradle compileJava, or kapt/ksp accordingly? Look for **FilerException** first and analyze the processor. Do not rush to conclude that the source annotation is structurally malformed.
- Did the error occur while the JVM was running tests/the app, typically alongside **java.lang.reflect** or framework annotation-scanning logic? Look for **AnnotationFormatError** and trace the runtime class file.
- If both errors appear in the build/test pipeline, handle them one by one by stage and artifact; there is not yet sufficient evidence to assert a single root cause.

### Step 2: Narrow the Scope with Targeted Commands

For **FilerException**, rerun the compile command with processing round information enabled (the JDK supports these options):

~~~bash
javac -XprintRounds -XprintProcessorInfo -cp out/processor -processorpath out/processor -processor demo.DuplicateProcessor -s out/generated -d out/classes demo/App.java
~~~

Read the triggered processor name, received annotations, and processing rounds. The two options above **do not automatically print each createSourceFile call**; add logging for **processor class / round / output qualified name / originating element** right before the creation call. In Gradle/Maven projects, apply the compiler args to the actual compile task; do not assume the sample javac command is identical to what the build tool runs.

For **AnnotationFormatError**, run **javap -v -p** on the class/JAR version actually loaded at runtime, then compare it against the original compiled output. You can temporarily isolate a weave/transform plugin, strip down the classpath, or build a small reflection test to reproduce the error.

### Step 3: Build an Evidence Table Before Fixing

Record concisely for each reproduction:

| Field to record | AnnotationFormatError | FilerException |
| --- | --- | --- |
| Stage | JVM/test startup/reflection | javac/processor round |
| Primary target | Class, method, annotation, JAR source | Output qualified name/path, processor |
| Relevant versions | JDK runtime, JAR, bytecode transformer | JDK compiler, build tool, processor |
| Useful comparison | Original class vs. post-transformation class | Output names in the previous round vs. the current round |
| Fix verification criteria | Reflection on the exact artifact no longer fails | Compiling with the same input/processor path produces no duplicates and generates output properly |

### Step 4: Fix the Root Cause and Verify Against Regression

- For invalid annotation bytecode: restore or regenerate a valid artifact; fix the bytecode transformation/generation tool; rerun annotation reflection tests against the distribution artifact.
- For FilerException: define predictable output names; ensure at most one creation per processing invocation; check input sources and competing processors; test from a clean output as well as an incremental build if the project uses one.
- Do not handle FilerException by **catching and ignoring** it: compilation may report success while generated files are missing or stale. Emit a clear diagnostic using **Messager** or let the build fail informatively.

## 5. Misconceptions to Avoid

1. **“AnnotationFormatError is an annotation syntax error in Java source.”** False: syntax errors, invalid @Target, or wrong element types are normally already reported by javac at compile time; AnnotationFormatError pertains to parsing metadata in a class file.
2. **“Simply deleting the build directory fixes every FilerException.”** False: two calls creating the same name in a single compilation still collide even when the output directory starts out empty.
3. **“Duplicate files on disk always cause FilerException.”** False: you must check Filer's contract and state in the current processing run, along with the input source/class set.
4. **“@Retention(SOURCE) can be retrieved via reflection just like RUNTIME.”** False: SOURCE is not retained for runtime reflection to return.
5. **“Whenever you hit FilerException, just rename the file with a timestamp.”** False: this breaks determinism, causes artifact buildup, and can mask two processors claiming ownership of the same output.
6. **“A deduplication Set is enough for all builds.”** False: you also need uniqueness across inputs, clear ownership among processors, and proper build/incremental configuration.
7. **“Catching AnnotationFormatError and continuing is fine.”** Unsafe: the error usually signals class file metadata that needs fixing; recovering at a diagnostic boundary is no substitute for addressing the root cause.

## 6. Self-Check

**Question 1.** A processor calls createSourceFile for a name in round 1 and then calls it again with the same name in round 2. Which error should you look for first?  
**Answer:** FilerException. Check for duplicate name creation across rounds within the same annotation processing run.

**Question 2.** A framework only fails when calling getDeclaredAnnotations on an obfuscated class; the pre-obfuscation .class file reads normally. Which inspection step is most valuable?  
**Answer:** Identify the actual loaded artifact/JAR, use javap -v -p to compare the annotation attributes of the two versions, and then inspect the obfuscation tool.

**Question 3.** Does switching @Retention(SOURCE) to RUNTIME automatically fix improperly encoded annotation bytecode?  
**Answer:** No. Retention determines persistence and reflection accessibility; malformed bytecode must be fixed in the compilation/transformation/release pipeline.

**Question 4.** Why can a processor still encounter FilerException even after using a Set to record the names it creates?  
**Answer:** That name may collide with an input source, another processor's output, or a non-unique name-mapping rule across elements. The Set only covers calls tracked by that processor itself.

**Question 5.** Should you ignore FilerException so that Gradle reports a successful compilation?  
**Answer:** No. Clearly diagnose the output name and root cause, fix the duplicate creation, and verify that the output is generated properly; swallowing the error can leave stale or missing classes/sources.

## 7. Key Takeaways to Apply

**AnnotationFormatError → isolate the class file, annotation metadata, classpath/class loader, and bytecode transformation tools. FilerException → isolate the processor, round, output file/type name, initial inputs, and repeated Filer calls.** Read the stack trace alongside the actual artifact, reproduce in a minimal environment, and confirm the fix by rerunning the exact stage that previously failed.
