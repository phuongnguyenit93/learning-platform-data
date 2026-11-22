# Testing Annotation Processors with JavaCompiler and Generated Files

## 1. Objectives and Scope

An annotation processor is a program that runs **at compile time**, typically based on the JSR 269 API in the javax.annotation.processing package. It can inspect annotated declarations, emit compilation errors, generate new source code via Filer, or create resource files. Testing a processor therefore differs from testing a regular Java method: you must launch a **real compilation pass**, run the processor during that pass, and observe the results.

After this lesson, you will be able to:

- Run a processor directly using javax.tools.JavaCompiler, without depending on an IDE or Gradle/Maven.
- Pass a small Java source into the compiler and activate the exact processor under test using CompilationTask.setProcessors.
- Use separate paths for generated source files (SOURCE_OUTPUT) and compiled classes (CLASS_OUTPUT).
- Assert that the .java file is generated, its content is accurate, the corresponding .class file compiles successfully, and its runtime behavior is correct.
- Test misuse scenarios for an annotation: compilation returns false, produces a Diagnostic.Kind.ERROR with the expected message, and does not generate invalid files.
- Explain common errors involving multiple processing rounds, FilerException, classpath, generated sources that have not been compiled, and cleaning up the test environment.

The examples run on **JDK 17 or higher**, use the classpath (not module-path), and require no external test libraries outside the JDK. This is a small integration test written using a main method; in real-world projects, the assertions can be migrated to JUnit.

## 2. What Needs to Be Verified?

The typical flow of a compilation pass with annotation processing:

1. The compiler parses the input source code into language elements (Element).
2. The selected processor receives the annotations it supports and processes the elements across one or more rounds.
3. The processor may use Messager to emit diagnostics, Filer.createSourceFile to generate .java files, or Filer.createResource to generate resources.
4. New source code is typically examined in the next round. During a full compilation (without -proc:only enabled), the compiler proceeds to compile classes from both the input source code and the generated sources.
5. JavaCompiler.CompilationTask.call returns a Boolean: true when compilation succeeds; errors emitted by the processor usually cause the result to be false.

A reliable test needs to check **three distinct layers of evidence**:

| Verification Layer | Observation | Why It Is Needed |
| --- | --- | --- |
| Compilation | task.call() succeeds or fails as expected; diagnostics are accurate | Confirms the processor actually ran inside a real compiler |
| Artifact | The .java/.class/resource files exist in the right directories with the right content | Catches naming, package, escaping, path, and Filer errors |
| Behavior | Load the generated class and invoke its methods | Catches generated code that produces files but behaves incorrectly |

You should not just search for strings in a .java file: that does not prove the generated code compiles. Conversely, merely asserting that compilation succeeds does not guarantee the processor was actually invoked; the compiler can finish without running the processor if discovery is misconfigured.

## 3. Example Processor Under Test

We build a type-level annotation @GenerateHello and a processor that generates two outputs when the annotation is placed on a class: the source class CustomerHello.java with message(), and the resource META-INF/hello/Customer.txt. If the annotation is applied to an interface, the processor emits a compilation error. The test suite will verify both the success branch and the error branch.

File structure to create:

~~~text
src/
├── demo/
│   ├── GenerateHello.java
│   └── HelloProcessor.java
└── ProcessorIntegrationTest.java
~~~

**src/demo/GenerateHello.java**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateHello {
}
~~~

RetentionPolicy.SOURCE is sufficient for an annotation intended only for the compiler. @Target(TYPE) allows the annotation to appear on both classes and interfaces; this enables the processor to report a specific error itself when encountering an interface.

**src/demo/HelloProcessor.java**

~~~java
package demo;

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
import javax.tools.FileObject;
import javax.tools.JavaFileObject;
import javax.tools.StandardLocation;

@SupportedAnnotationTypes("demo.GenerateHello")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class HelloProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateHello.class)) {
            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateHello chỉ áp dụng cho class",
                        element);
                continue;
            }

            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(element).getQualifiedName().toString();
            String simpleName = element.getSimpleName().toString();
            String generatedSimpleName = simpleName + "Hello";
            String qualifiedName = packageName.isEmpty()
                    ? generatedSimpleName
                    : packageName + "." + generatedSimpleName;

            try {
                JavaFileObject source = processingEnv.getFiler()
                        .createSourceFile(qualifiedName, element);
                try (Writer writer = source.openWriter()) {
                    if (!packageName.isEmpty()) {
                        writer.write("package " + packageName + ";\n");
                    }
                    writer.write(
                            "public final class " + generatedSimpleName + " {\n");
                    writer.write(
                            "    private " + generatedSimpleName + "() {}\n");
                    writer.write(
                            "    public static String message() { return "
                            + "\"Hello, " + simpleName + "\"; }\n");
                    writer.write("}\n");
                }

                FileObject resource = processingEnv.getFiler().createResource(
                        StandardLocation.CLASS_OUTPUT,
                        "",
                        "META-INF/hello/" + simpleName + ".txt",
                        element);
                try (Writer writer = resource.openWriter()) {
                    writer.write("Hello, " + simpleName + "\n");
                }
            } catch (IOException error) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Không tạo được tệp cho " + simpleName
                                + ": " + error.getMessage(),
                        element);
            }
        }
        return true;
    }
}
~~~

Key design decisions:

- @SupportedAnnotationTypes declares the fully qualified name of the annotation; setProcessors in the test will **directly specify** the processor instance, so META-INF/services/javax.annotation.processing.Processor is not required.
- Filer.createSourceFile uses the package-qualified type name, not an arbitrary file path. The compiler/Filer decides where to store it based on SOURCE_OUTPUT.
- Filer.createResource(CLASS_OUTPUT, "", "META-INF/hello/Customer.txt", ...) generates the resource under the class output directory; it **does not** trigger an additional Java source processing round.
- The originating element helps build tools track the relationship between input and output elements, which is useful for incremental builds.
- A file can only be created once per compilation pass. The processor only iterates over elements bearing the annotation and does not recreate CustomerHello when processing the round for the generated source code; attempting to create the same name a second time throws a FilerException.
- Never swallow IOException or return success while failing to produce essential outputs: the example converts file creation failures into Diagnostic.Kind.ERROR.
- return true indicates that this annotation has been handled by the processor; that **does not** mean the entire compilation automatically succeeds.

## 4. Integration Harness with javax.tools.JavaCompiler

The test creates Java compilation units **in memory**, but instructs the compiler/Filer to write actual outputs to a temporary directory. Each case uses separate classes and generated directories to prevent artifacts from previous runs from causing false passes. DiagnosticCollector captures messages from the compiler and processor, while StandardJavaFileManager determines where outputs are stored.

**src/ProcessorIntegrationTest.java**

~~~java
import demo.HelloProcessor;
import java.io.IOException;
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class ProcessorIntegrationTest {
    private record Outcome(
            boolean success,
            List<Diagnostic<? extends JavaFileObject>> diagnostics) {
    }

    private static final class Source extends SimpleJavaFileObject {
        private final String content;

        Source(String className, String content) {
            super(URI.create("string:///"
                    + className.replace('.', '/')
                    + JavaFileObject.Kind.SOURCE.extension),
                    JavaFileObject.Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    private static Outcome compile(
            String className, String content, Path testDir)
            throws IOException {

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Cần chạy test bằng JDK 17+");
        }

        Path classes = Files.createDirectories(testDir.resolve("classes"));
        Path generated = Files.createDirectories(testDir.resolve("generated"));
        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        collector, Locale.ROOT, StandardCharsets.UTF_8)) {

            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(classes));
            manager.setLocationFromPaths(
                    StandardLocation.SOURCE_OUTPUT, List.of(generated));

            JavaFileObject input = new Source(className, content);
            List<String> options = List.of(
                    "--release", "17",
                    "-classpath", System.getProperty("java.class.path"),
                    "-encoding", "UTF-8");

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, collector, options, null, List.of(input));
            task.setProcessors(List.of(new HelloProcessor()));

            boolean success = Boolean.TRUE.equals(task.call());
            return new Outcome(
                    success, List.copyOf(collector.getDiagnostics()));
        }
    }

    private static void require(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    private static String messages(Outcome result) {
        return String.join("\n", result.diagnostics().stream()
                .map(d -> d.getKind() + ": " + d.getMessage(Locale.ROOT))
                .toList());
    }

    private static void deleteTree(Path root) throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            for (Path path :
                    paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempDirectory("processor-test-");
        try {
            String valid = """
                    package demo;
                    @GenerateHello
                    public class Customer {}
                    """;
            Outcome good = compile(
                    "demo.Customer", valid, temp.resolve("valid"));
            require(good.success(), "Compilation lỗi:\n" + messages(good));

            Path source = temp.resolve(
                    "valid/generated/demo/CustomerHello.java");
            Path bytecode = temp.resolve(
                    "valid/classes/demo/CustomerHello.class");
            Path resource = temp.resolve(
                    "valid/classes/META-INF/hello/Customer.txt");

            require(Files.isRegularFile(source), "Thiếu .java được sinh");
            String expectedSource = """
                    package demo;
                    public final class CustomerHello {
                        private CustomerHello() {}
                        public static String message() { return "Hello, Customer"; }
                    }
                    """;
            require(expectedSource.equals(
                    Files.readString(source, StandardCharsets.UTF_8)),
                    "Nội dung nguồn sinh không khớp");
            System.out.println("PASS: generated .java");

            require(Files.isRegularFile(bytecode), "Thiếu .class được sinh");
            require(Files.isRegularFile(resource), "Thiếu resource");
            require("Hello, Customer\n".equals(
                    Files.readString(resource, StandardCharsets.UTF_8)),
                    "Resource sai nội dung");

            URL classesUrl = temp.resolve("valid/classes").toUri().toURL();
            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] {classesUrl},
                    ClassLoader.getPlatformClassLoader())) {
                Class<?> type = Class.forName(
                        "demo.CustomerHello", true, loader);
                Object message = type.getMethod("message").invoke(null);
                require("Hello, Customer".equals(message),
                        "Lớp được sinh chạy sai");
            }
            System.out.println("PASS: generated .class, resource and runtime");

            String invalid = """
                    package demo;
                    @GenerateHello
                    public interface InvalidType {}
                    """;
            Outcome bad = compile(
                    "demo.InvalidType", invalid, temp.resolve("invalid"));
            require(!bad.success(),
                    "Interface không hợp lệ phải làm compilation thất bại");
            boolean hasExpectedError = bad.diagnostics().stream()
                    .anyMatch(d ->
                            d.getKind() == Diagnostic.Kind.ERROR
                            && d.getMessage(Locale.ROOT)
                                    .contains("@GenerateHello chỉ áp dụng cho class"));
            require(hasExpectedError,
                    "Thiếu diagnostic đúng:\n" + messages(bad));
            require(!Files.exists(temp.resolve(
                    "invalid/generated/demo/InvalidTypeHello.java")),
                    "Không được sinh nguồn cho interface không hợp lệ");
            System.out.println("PASS: negative diagnostics");
        } finally {
            deleteTree(temp);
        }
    }
}
~~~

### Purpose of Each Operation

**In-memory source:** SimpleJavaFileObject provides a URI matching className and returns the source code in getCharContent. This way, the test does not need to save the input Customer.java to disk, yet the compiler still parses the code as a Java compilation unit.

**Processor selection:** task.setProcessors(List.of(new HelloProcessor())) activates the exact processor under test. This reduces reliance on automatic processor discovery via service registration or JDK-specific variations. If you are testing processor auto-registration itself, a dedicated test is needed using the processor path and service file without calling setProcessors.

**Classpath and output paths:** The classpath is taken from java.class.path of the test runner process so the compiler can locate demo.GenerateHello; SOURCE_OUTPUT holds generated source code; CLASS_OUTPUT holds .class files and resources. The success and failure compilation runs use distinct subdirectories. Depending on a modular project setup, MODULE_PATH/PROCESSOR_PATH may be needed accordingly, but this example uses the classpath explicitly.

**Diagnostics:** DiagnosticCollector records the diagnostic kind (ERROR, WARNING, etc.), the message text, and—when available—the source, line, and column. For the error branch, you must check both the false result and that the message contains the expected meaning; checking only for false would allow an unrelated syntax or classpath error to make the test "pass".

**Artifacts and behavior:** The test matches the full content of CustomerHello.java, reads the resource using UTF-8, verifies that the .class bytecode exists, loads the class from the output directory via URLClassLoader, and invokes message() reflectively. This proves the generation and compilation steps are complete. The test closes the file manager and class loader and cleans up the temporary directory even if an assertion fails.

## 5. Compiling and Running the Test

Open a terminal in the directory containing src and run:

~~~bash
javac -encoding UTF-8 --release 17 -d out src/demo/GenerateHello.java src/demo/HelloProcessor.java src/ProcessorIntegrationTest.java
java -cp out ProcessorIntegrationTest
~~~

These commands work when javac and java belong to **JDK 17+** and the current working directory has the exact structure shown above. Java 17 provides records, text blocks, Stream.toList, and the StandardJavaFileManager.setLocationFromPaths API used in the example. If placing the code in a Gradle/Maven project, keep the processor class on the test classpath or configure the processor path for the compilation phase.

Stdout when all assertions pass:

~~~text
PASS: generated .java
PASS: generated .class, resource and runtime
PASS: negative diagnostics
~~~

The corresponding "PASS" line is not printed if an earlier check fails; the program throws an AssertionError, prints the stack trace to stderr, and exits with a non-zero status. The interface compilation pass is an **intentional negative test**: JavaCompiler reports the error through the collector, and the harness inspects the error instead of printing it to stdout.

To inspect the artifacts manually, temporarily remove the finally/deleteTree block or set a breakpoint before cleanup. During normal execution, the paths reside under a temporary directory created by Files.createTempDirectory and are deleted after the test.

## 6. Alternative: Testing with javac on the Command Line

If you have an input file src/demo/Customer.java with the following content:

~~~java
package demo;

@GenerateHello
public class Customer {
}
~~~

You can run the processor using the javac CLI after compiling demo.GenerateHello and demo.HelloProcessor into the out directory:

~~~bash
javac -cp out -processor demo.HelloProcessor -s generated -d classes src/demo/Customer.java
~~~

Run from the project root; create the generated and classes directories beforehand if required by your system or build command. The -s option specifies the location for generated Java source files; -d specifies the location for compiled classes and CLASS_OUTPUT resources. With a full compilation, the generated source class is also compiled. The -processor option specifies the processor by its fully qualified name, allowing quick CLI behavior checks; the JavaCompiler harness above is better suited for automated assertions and reading structured diagnostics.

If you only want to inspect the generated sources **without producing class files**, you can pass -proc:only when invoking javac; in that case, do not expect CustomerHello.class to appear. To verify bytecode and runtime behavior as in the test above, you must perform a full compilation.

## 7. Error Scenarios to Add to a Real-World Test Suite

| Scenario | Recommended Assertions |
| --- | --- |
| Valid input | Compilation succeeds; no unexpected ERROR diagnostics; generated source/resource files are correct; .class is runnable |
| Annotation placed on wrong type | Compilation fails; ERROR points to the invalid element; no spurious valid artifacts are generated |
| Missing classpath/annotation | Distinguish "cannot find symbol" or missing package errors from processor domain errors |
| Different class/package names | Generated class path and package match the input type name; not hardcoded to demo.Customer |
| Two classes with the same simple name in different packages | Generated source names use the fully qualified name to avoid file collisions |
| Multiple annotated elements in one pass | Generate all artifacts for every element; no duplicate generation across rounds |
| Recompilation with existing output | Use a clean directory to eliminate stale artifacts, or explicitly verify the incremental build strategy |
| Processor emits warning/note | Assert the exact Kind, message, and location if they are part of the contract |
| Unable to write output or FilerException | Processor converts I/O errors into ERROR, and compilation does not succeed |
| Unregistered processor | Have a dedicated test verifying service discovery, separate from tests that call setProcessors directly |

When checking diagnostics, prioritize Kind.ERROR, stable domain messages, and the associated element. Avoid snapshotting the entire diagnostic text because line/column numbers, temporary paths, locale, and compiler wording can vary across JDK versions. In this example, checking the message emitted by **the processor itself** is stable.

When generated code depends on element iteration order, the current timestamp, or absolute paths, file snapshots become flaky. Design the processor to produce deterministic output: sort elements if necessary, use explicit line endings and charsets, and avoid embedding timestamps or randomness. For large files, you can parse the generated content or compare the AST and required properties; for small fixed files like in this example, exact text matching is appropriate.

## 8. Common Pitfalls and How to Handle Them

1. **Confusing "source exists" with "compiled successfully".** The fact that Filer created a .java file does not guarantee it is valid. Verify task.call() and the .class file, and even better, load and run the class.
2. **Processor not actually running.** The default javac command may fail to find the processor (especially when changing build/JDK configurations). Use setProcessors or -processor explicitly; if testing auto-discovery, prepare the service file and processor path accordingly.
3. **Recreating the same file across multiple rounds.** Filer allows a file to be created only once per compilation pass. Do not generate files when processingOver() is true, process the appropriate set of elements per round, and avoid calling createSourceFile repeatedly for the same name.
4. **Mixing up output locations.** SOURCE_OUTPUT is for generated source code; CLASS_OUTPUT is for bytecode and runtime resources; CLASS_PATH/ANNOTATION_PROCESSOR_PATH are used for locating classes, not as artifact destinations.
5. **Sharing output directories between test cases.** Stale files cause Files.exists to return true even if the current processor generated nothing. Create a fresh temporary directory for each case and clean up after the test.
6. **Catching errors while still reporting compilation success.** An exception not reported via Messager can hide domain failures. For unrecoverable errors, emit Diagnostic.Kind.ERROR and verify that task.call() returns false.
7. **Overly brittle diagnostic assertions.** Do not assert against full stack traces, compiler locations, or compiler-generated phrasing when you only need to verify processor-emitted errors.
8. **Closing the file manager too early or leaking file handles.** Read artifacts only after task.call(), and close StandardJavaFileManager and URLClassLoader; on Windows, the loader must be closed before deleting the temporary directory tree.
9. **Confusing runtime tests with compile-time tests.** RetentionPolicy.SOURCE means the annotation does not need to be present at runtime. The runtime targets to test are the generated classes/resources, not the original annotation.
10. **Using -proc:only when .class files are required.** -proc:only performs annotation processing without fully compiling into bytecode; run a full compilation whenever you want to assert .class files or runtime behavior.

## 9. Acceptance Checklist

- The test suite generates both valid and invalid input sources; both invoke the real JavaCompiler.
- Each compilation specifies the processor, classpath, SOURCE_OUTPUT, and CLASS_OUTPUT.
- The valid case asserts true, the content of the generated .java, the generated .class, the resource, and actual runtime behavior.
- The invalid case asserts false, the expected Diagnostic.Kind.ERROR, and no invalid generated source.
- Processing rounds and Filer errors are handled properly without relying on leftover files from previous tests.
- The example code compiles and runs on JDK 17+, and the stated stdout reflects the output of the success path.

This testing approach establishes a complete chain of proof: **input source → processor inside the compiler → diagnostics and artifacts → bytecode/actual runtime behavior**. It catches code-generation bugs that unit tests calling process() directly on mock Element instances often miss.
