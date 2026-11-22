# Testing Processors with Valid Generated Code and Invalid Inputs

## 1. What do we learn from a compilation test?

An **annotation processor** processes annotations while the Java compiler runs. It can generate source code, create resources, or report errors for declarations violating rules. Processor testing must verify **the entire compilation pass**, because a successful call to the process method does not yet guarantee the generated source is valid.

Two scenarios must be proven:

1. **Valid input:** the compiler loads the processor; the processor generates the right name, package, and content; the generated source compiles; the generated API behaves properly.
2. **Invalid input:** the compiler actually runs the processor; the processor reports an error for the right cause on the relevant source; compilation fails; the processor does not generate forbidden files.

This lesson uses a Java 17+ annotation processor and a test program built with the **Java Compiler API**. The example requires no JUnit or external libraries so it can run with JDK 17 or JDK 21. For real projects, assertions can be migrated to JUnit or a compile-testing library while keeping the same contract.

## 2. Annotation processing has multiple rounds

~~~text
Initial Java source
       |
       v
javac parses and finds annotations
       |
       v
Processor.process(annotations, roundEnv)
        |                           |
        |                           +-- Messager -> NOTE/WARNING/ERROR
        +-- Filer -> new source/resource
       |
       v
Next round if new source exists
       |
       v
Compile initial source + new source
       |
       v
Diagnostics, success/failure status, .java, .class
~~~

| API | Role |
| --- | --- |
| AbstractProcessor | Base class for declaring annotations handled by the processor |
| ProcessingEnvironment | Provides Messager, Filer, and type-model utilities |
| RoundEnvironment | Elements belonging to the current round, processingOver state |
| Element / TypeElement | Semantic model of Java declarations |
| Filer | Creates sources/resources; prevents creating the same file twice in one compilation |
| Messager | Emits diagnostics, attachable to source elements |
| JavaCompiler | Builds real compilation tasks |
| StandardJavaFileManager | Converts source files into JavaFileObjects and handles the file manager |
| DiagnosticCollector | Collects ERROR, WARNING, and other diagnostics |

**A `true` return value from process() is not the compilation result.** True means the processor claims the annotations; if the processor has printed a Diagnostic.Kind.ERROR, the entire compilation will normally fail. The primary result to assert lies in **CompilationTask.call()**.

Do not test a processor by parsing source text with regex. The Java compiler already provides the corresponding element and annotation model, allowing the processor to work properly even when source formatting changes.

## 3. Example contract: GenerateGreeting

We create an **@GenerateGreeting** annotation applicable to Java types. The processor accepts only **classes** and non-blank strings. For a class **sample.Good** annotated with @GenerateGreeting("Hello"), the processor generates **sample.GoodGreeting** containing a public static String message() method returning "Hello".

| Case | Input | Expected result |
| --- | --- | --- |
| Valid | @GenerateGreeting("Hello") on class Good | Compile true, generates GoodGreeting.java and GoodGreeting.class, message() returns Hello |
| Invalid value | @GenerateGreeting("   ") on class Bad | Compile false, ERROR contains GREETING_001, does not generate BadGreeting.java |
| Invalid element | @GenerateGreeting("Hello") on interface WrongKind | Compile false, ERROR contains GREETING_002, does not generate WrongKindGreeting.java |

You must verify **the error cause**, because a compilation returning false due to a missing annotation dependency or a processor failing to load is not evidence that the processor rejected the input under business rules.

Example structure:

~~~text
processor-demo/
└── src/
    └── demo/
        ├── annotations/
        │   └── GenerateGreeting.java
        ├── processor/
        │   └── GreetingProcessor.java
        └── test/
            └── ProcessorCompilationTest.java
~~~

## 4. Writing the annotation

File **src/demo/annotations/GenerateGreeting.java**:

~~~java
package demo.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {
    String value();
}
~~~

**RetentionPolicy.SOURCE** is sufficient for compile-time processing. **ElementType.TYPE** allows the annotation to appear on interfaces, while the processor actively reports GREETING_002 because the business rule supports only classes. If a narrow @Target caused the compiler itself to block the invalid case immediately, the test could not expect the processor's diagnostic as in this example.

## 5. Writing the processor

File **src/demo/processor/GreetingProcessor.java**:

~~~java
package demo.processor;

import demo.annotations.GenerateGreeting;
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

@SupportedAnnotationTypes("demo.annotations.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "GREETING_002: @GenerateGreeting requires a class",
                        element);
                continue;
            }

            String message = element.getAnnotation(
                    GenerateGreeting.class).value();

            if (message.isBlank()) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "GREETING_001: message must not be blank",
                        element);
                continue;
            }

            TypeElement type = (TypeElement) element;
            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(type)
                    .getQualifiedName()
                    .toString();
            String generatedName = type.getSimpleName() + "Greeting";
            String qualifiedName = packageName.isEmpty()
                    ? generatedName
                    : packageName + "." + generatedName;

            try {
                JavaFileObject generated = processingEnv.getFiler()
                        .createSourceFile(qualifiedName, element);

                try (Writer writer = generated.openWriter()) {
                    if (!packageName.isEmpty()) {
                        writer.write("package " + packageName + ";\n");
                    }
                    writer.write("public final class "
                            + generatedName + " {\n");
                    writer.write("  private " + generatedName + "() {}\n");
                    writer.write("  public static String message() {\n");
                    writer.write("    return \"" + escape(message) + "\";\n");
                    writer.write("  }\n}\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "GREETING_003: cannot generate "
                                + qualifiedName + ": " + ex.getMessage(),
                        element);
            }
        }

        return true;
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }
}
~~~

**Technical points to note:**

- @SupportedAnnotationTypes takes the fully qualified annotation name; @SupportedSourceVersion(RELEASE_17) declares the release supported by the example's processor.
- The processor reads **getElementsAnnotatedWith** via the compiler model, avoiding dependence on source formatting.
- Checking element kind and **isBlank()** happens before Filer. Invalid inputs receive only diagnostics and generate no corresponding files.
- **Messager.printMessage(ERROR, ..., element)** attaches the error to the element, giving the compiler and tests a source location. This is a more suitable way to report validation errors than throwing RuntimeException.
- Filer accepts the fully qualified generated type and originating element. The originating element helps build systems, yet does not by itself guarantee all incremental processing is valid.
- The escape helper handles several common Java string characters; production processors should additionally handle control characters/Unicode and colliding class/package names.
- A file created in the first round appears in the next round. Because the generated class does not carry @GenerateGreeting, this snippet does not loop generation in subsequent rounds.
- Returning true from the processor means claiming the annotation; it does not mean compilation has a true outcome.

A large processor must guard against creating the same fully qualified name twice. **FilerException** can occur when the same file is created again; swallowing exceptions without recording diagnostics hides the root cause.

## 6. Java Compiler API test harness

Create **src/demo/test/ProcessorCompilationTest.java**:

~~~java
package demo.test;

import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class ProcessorCompilationTest {

    private ProcessorCompilationTest() {
    }

    private record Compilation(
            boolean success,
            Path classes,
            Path generated,
            List<Diagnostic<? extends JavaFileObject>> diagnostics) {
    }

    public static void main(String[] args) throws Exception {
        testValidSource();
        testBlankMessage();
        testWrongElementKind();
    }

    private static void testValidSource() throws Exception {
        Compilation result = compile("Good", """
                package sample;
                import demo.annotations.GenerateGreeting;

                @GenerateGreeting("Hello")
                public class Good {
                    public static void main(String[] args) {
                        System.out.println(GoodGreeting.message());
                    }
                }
                """);

        check(result.success(), "Valid source must compile");
        check(Files.exists(result.generated()
                .resolve("sample/GoodGreeting.java")),
                "Generated .java is missing");
        check(Files.exists(result.classes()
                .resolve("sample/GoodGreeting.class")),
                "Generated .class is missing");

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] {result.classes().toUri().toURL()},
                ProcessorCompilationTest.class.getClassLoader())) {
            Class<?> generated = loader.loadClass("sample.GoodGreeting");
            String actual = (String) generated.getMethod("message")
                    .invoke(null);
            check("Hello".equals(actual),
                    "Generated method returned: " + actual);
        }

        System.out.println(
                "PASS valid: sample.GoodGreeting.message() = Hello");
    }

    private static void testBlankMessage() throws Exception {
        Compilation result = compile("Bad", """
                package sample;
                import demo.annotations.GenerateGreeting;

                @GenerateGreeting("   ")
                public class Bad {
                }
                """);

        check(!result.success(),
                "Blank message must fail compilation");
        check(hasError(result, "GREETING_001", "Bad.java"),
                "Missing GREETING_001 diagnostic on Bad.java");
        check(!Files.exists(result.generated()
                .resolve("sample/BadGreeting.java")),
                "Invalid input unexpectedly generated source");

        System.out.println(
                "PASS invalid value: GREETING_001 and compile failed");
    }

    private static void testWrongElementKind() throws Exception {
        Compilation result = compile("WrongKind", """
                package sample;
                import demo.annotations.GenerateGreeting;

                @GenerateGreeting("Hello")
                public interface WrongKind {
                }
                """);

        check(!result.success(),
                "Annotated interface must fail compilation");
        check(hasError(result, "GREETING_002", "WrongKind.java"),
                "Missing GREETING_002 diagnostic");
        check(!Files.exists(result.generated()
                .resolve("sample/WrongKindGreeting.java")),
                "Invalid kind unexpectedly generated source");

        System.out.println(
                "PASS invalid kind: GREETING_002 and compile failed");
    }

    private static Compilation compile(String name, String source)
            throws IOException {

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Run tests using a JDK, not a runtime without javac");
        }

        Path root = Files.createTempDirectory("processor-" + name + "-");
        Path sourceFile = root.resolve("src/sample/" + name + ".java");
        Path classes = root.resolve("classes");
        Path generated = root.resolve("generated");
        Files.createDirectories(sourceFile.getParent());
        Files.createDirectories(classes);
        Files.createDirectories(generated);
        Files.writeString(sourceFile, source, StandardCharsets.UTF_8);

        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             collector, Locale.ROOT,
                             StandardCharsets.UTF_8)) {

            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjects(sourceFile.toFile());

            String toolClasspath = System.getProperty("java.class.path");

            List<String> options = List.of(
                    "--release", "17",
                    "-encoding", "UTF-8",
                    "-classpath", toolClasspath,
                    "-processorpath", toolClasspath,
                    "-processor", "demo.processor.GreetingProcessor",
                    "-d", classes.toString(),
                    "-s", generated.toString());

            Boolean successful = compiler.getTask(
                    null, manager, collector, options, null, units)
                    .call();

            return new Compilation(
                    Boolean.TRUE.equals(successful),
                    classes,
                    generated,
                    List.copyOf(collector.getDiagnostics()));
        }
    }

    private static boolean hasError(
            Compilation result, String code, String filename) {

        return result.diagnostics().stream().anyMatch(d ->
                d.getKind() == Diagnostic.Kind.ERROR
                        && d.getMessage(Locale.ROOT).contains(code)
                        && d.getSource() != null
                        && d.getSource().getName().endsWith(filename));
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

### 6.1. What exactly does this test verify?

**Positive** covers three layers: compilation true; generated .java and .class exist at the right paths; reflection loads the generated class, invokes the method, and checks the Hello value. If the generated source has a syntax error, compilation is false; if the method is wrong, reflection or the assertion fails. This is stronger than merely asserting that a source file was written.

**Negative** covers compilation false, a **Kind.ERROR** diagnostic containing the business code and matching source file, and no forbidden generated source. An ERROR due to a missing classpath/annotation **must not count** as processor validation working properly.

**DiagnosticCollector** stores compiler/processor errors for the test to read cleanly; do not require fixed diagnostic ordering or verbatim wording across JDKs/locales. **Locale.ROOT** makes message rendering less dependent on the runner's locale.

### 6.2. Why are both classpath and processor path needed?

In the example, the test program runs with a classpath containing the annotation API and the processor. JavaCompiler uses:

- **-classpath:** supplies the annotation API when compiling the test source.
- **-processorpath:** lets the compiler find the processor binary and processor dependencies.
- **-processor:** selects the exact processor without relying on discovery.
- **-d:** directory containing compiled classes.
- **-s:** directory for generated Java sources.
- **--release 17:** pins language, bytecode, and Java platform APIs to release 17.

Using a single toolClasspath is only for a self-contained demo. In real projects, the source classpath and processor path typically contain different sets of dependencies.

### 6.3. Isolating outputs to avoid false positives

The compile() method creates a new temporary directory for **each** case, keeping source, classes, and generated files separate. Reusing a shared output directory could let an old BadGreeting.java fail a negative test wrongly, and an old GoodGreeting.class pass a positive test even if the processor no longer generates anything.

Temporary files are retained for convenient investigation. With JUnit or production frameworks, you can use the test framework's temp-directory management and clean up artifacts when no longer needed.

## 7. Compiling and running the example properly

Open a terminal at the **processor-demo** directory containing the exact three source files above.

**Linux/macOS:**

~~~bash
mkdir -p out/tools
javac --release 17 -encoding UTF-8 -d out/tools \
  src/demo/annotations/GenerateGreeting.java \
  src/demo/processor/GreetingProcessor.java \
  src/demo/test/ProcessorCompilationTest.java
java -cp out/tools demo.test.ProcessorCompilationTest
~~~

**Windows PowerShell** (javac command written on one line so it can be copied verbatim):

~~~powershell
New-Item -ItemType Directory -Force out/tools | Out-Null
javac --release 17 -encoding UTF-8 -d out/tools src/demo/annotations/GenerateGreeting.java src/demo/processor/GreetingProcessor.java src/demo/test/ProcessorCompilationTest.java
java -cp out/tools demo.test.ProcessorCompilationTest
~~~

**Exact stdout of the test program when all three cases pass:**

~~~text
PASS valid: sample.GoodGreeting.message() = Hello
PASS invalid value: GREETING_001 and compile failed
PASS invalid kind: GREETING_002 and compile failed
~~~

The javac command compiling the tool sources does not necessarily print stdout when successful. If an assertion fails, the test program throws AssertionError and exits with failure.

In the temporary directory of the Good case, the compiler creates:

~~~text
generated/sample/GoodGreeting.java
classes/sample/GoodGreeting.class
~~~

The generated source has content equivalent to:

~~~java
package sample;
public final class GoodGreeting {
  private GoodGreeting() {}
  public static String message() {
    return "Hello";
  }
}
~~~

The test does not merely inspect the GoodGreeting.java file, but also verifies the class and returned value. When a contract demands exact formatting, a golden-file assertion can be added; when checking only API and behavior, compile + invocation keeps tests less brittle to whitespace changes.

## 8. Manual reproduction via javac

To cross-check the compiler invocation if the API test fails, create an additional **samples/Good.java** file:

~~~java
package sample;

import demo.annotations.GenerateGreeting;

@GenerateGreeting("Hello")
public class Good {
    public static void main(String[] args) {
        System.out.println(GoodGreeting.message());
    }
}
~~~

After compiling the annotation and processor into out/tools, Linux/macOS can run:

~~~bash
mkdir -p out/manual-classes out/manual-generated
javac --release 17 -encoding UTF-8 \
  -classpath out/tools \
  -processorpath out/tools \
  -processor demo.processor.GreetingProcessor \
  -d out/manual-classes \
  -s out/manual-generated \
  samples/Good.java
java -cp out/manual-classes:out/tools sample.Good
~~~

**Stdout:** 

~~~text
Hello
~~~

The samples/Good.java file is an extra manual exercise, **not part of the three minimal files** of the test harness; create it before running the commands. On Windows, the Java classpath separates entries with **;** instead of **:** and terminal line continuation differs too.

For manual negative testing, compile a Bad.java source with @GenerateGreeting("   ") into another output directory. Verify javac returns a non-zero exit code **and** emits code GREETING_001. Seeing only a failing exit code might be caused by a missing dependency or selecting the wrong processor.

The **-proc:only** mode is useful for inspecting files generated by annotation processing, but does not replace a full positive compilation test because it does not prove the generated Java can produce valid .class files.

## 9. Edge cases worth testing

| Group | Input/test | What to Assert |
| --- | --- | --- |
| Basic | One valid class | Generated class and source match, compilation succeeds |
| Multiple inputs | Two valid classes in the same compilation | Both outputs present, no extra generation |
| Boundary values | Empty, whitespace-only | ERROR with matching code and no generation |
| Escaping | Quotes, backslash, newline, Unicode | Generated source still compiles; runtime preserves exact content |
| Element kind | Interface/enum/record per contract | Matching ERROR or corresponding compiler validation |
| Duplicate | Two declarations demanding the same generated name | Explanatory error, no overwriting |
| Processing rounds | Generated source contains annotations for further processing | No infinite loop, no duplicate generation |
| Unannotated | Plain source | Success, no unintended outputs |
| Warnings | Suboptimal yet valid input | WARNING, compile status per policy |
| Incremental | Modifying source across multiple builds | Fresh output, no stale files/caches used |

Not every processor has to generate .java files. Validation-only processors should focus on diagnostics; resource-generating processors test output resources; type-generating processors test packages, signatures, compilability, and behavior.

### Processing rounds and file collisions

Filer can throw FilerException when the same source name is created twice in one compilation. If a generated source itself carries annotations triggering the next round, the processor must avoid infinite creation or duplicate naming. One test should put multiple annotated elements into **the same compilation**, rather than only running twice separately, to catch output name-mapping bugs.

In particular, true from process() only claims annotations; do not use it to infer that Filer writes, diagnostics, and compilation succeeded.

## 10. Distinguishing processor bugs from test setup errors

| Symptom | Primary Possibility | What to Verify |
| --- | --- | --- |
| getSystemJavaCompiler() returns null | Runtime lacks compiler | Run from a full JDK |
| Processor not found | Wrong processor path/FQCN | -processorpath, -processor, binary JAR |
| package demo.annotations does not exist | Missing annotation on compile classpath | -classpath |
| Compilation false yet missing GREETING_001 | Failed due to another compiler error | Inspect detailed diagnostics |
| Generated .java exists, .class missing | Invalid generated Java or -proc:only | Status, diagnostics, mode |
| FilerException | Duplicate fully qualified name | Name mapping, rounds, originating owner |
| Test passes only after another test | Shared state or outputs | Separate directories and classloaders |
| CI differs from local machine | JDK/toolchain, encoding, paths, dependencies | Compiler logs and resolved classpath |

To inspect errors, you can add **the following method to class ProcessorCompilationTest**:

~~~java
private static void printDiagnostics(Compilation result) {
    for (Diagnostic<? extends JavaFileObject> d
            : result.diagnostics()) {
        System.err.printf("%s %s:%d %s%n",
                d.getKind(),
                d.getSource() == null
                        ? "<unknown>"
                        : d.getSource().getName(),
                d.getLineNumber(),
                d.getMessage(Locale.ROOT));
    }
}
~~~

This is a snippet added to the class, not a standalone program. A diagnostic may have no source, in which case getSource() == null and line number may be -1. Do not use diagnostic printing as a substitute for assertions.

## 11. Integrating tests into build tools and CI

**Gradle:** In a project with separate annotations and processor modules, annotation consumers usually need separated dependencies:

~~~groovy
dependencies {
    compileOnly project(':annotations')
    annotationProcessor project(':processor')
}
~~~

This snippet is only an illustrative configuration if the named modules actually exist. The processor module also needs the annotation API dependency to compile the processor. Do not assume a JAR on implementation will automatically be loaded as an annotation processor.

**Maven:** Check the maven-compiler-plugin version, processor/annotationProcessorPaths configuration in supported versions, release, toolchain, and active profiles. Discovery behavior can vary across JDKs and plugins; explicit processor selection makes tests reproducible.

**CI:** A proper job must compile the processor, run the harness, and return a non-zero exit code if any assertion fails. Pin the JDK/toolchain, keep sources/dependencies consistent, and do not let caching or task skipping mask whether the processor ran. On failure, collect compiler version, diagnostics, and needed temporary artifacts after filtering sensitive data.

**A passing negative test means the test harness proved the inner compilation failed for the right reason.** Never configure CI to ignore all compilation errors expecting every negative case to pass.

## 12. Concluding principles and checklist

- [ ] A real compiler is present and the processor is loaded with the right configuration.
- [ ] Annotation dependencies and processor dependencies are on their respective paths.
- [ ] Positive tests verify compilation success, generated source, generated class, and API/behavior.
- [ ] Negative tests verify compilation failure **for the right cause**, with Kind.ERROR, error code, source, and no forbidden outputs.
- [ ] Cases are isolated across source files, class output, generated output, and classloaders.
- [ ] Multi-element cases, multiple processing rounds, and duplicate generated names are accounted for.
- [ ] Tests do not depend on exact ordering/formatting of diagnostics emitted by javac.
- [ ] JDK, Java release, encoding, and stdout outputs match accurately.
- [ ] CI does not accidentally swallow compile errors or reuse stale artifacts.

Unit tests for escape/naming helpers remain valuable, yet cannot replace real compilation tests. A processor can emit a string-valid source that still fails when javac compiles it due to missing modules, generic types, or APIs incompatible with the Java release.

## References

- [Java SE 17 Annotation Processing API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html)
- [Java SE 17 JavaCompiler API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [Java SE 17 DiagnosticCollector](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html)
- [Java SE 17 javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [JSR 269 Pluggable Annotation Processing API](https://jcp.org/en/jsr/detail?id=269)

A reliable processor test suite must prove **code generated from valid inputs compiles and works properly**, while **invalid inputs fail compilation for the right reason without generating forbidden artifacts**.