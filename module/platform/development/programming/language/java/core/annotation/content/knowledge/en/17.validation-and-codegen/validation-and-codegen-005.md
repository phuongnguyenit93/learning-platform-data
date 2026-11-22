# Naming, Package, and Originating Element Rules When an Annotation Processor Generates Java Code

## 1. Why Must a Processor Manage Names, Packages, and Origins?

In Java, an **annotation processor** runs during the compilation phase and can inspect declarations, produce diagnostics, and generate Java source files, class files, or resources. When a processor uses the `javax.annotation.processing.Filer` API to generate code, the following three pieces of information determine the outcome:

1. **Generated file/type name**: must have a deterministic rule, be valid according to Java, and not collide with types or files that already exist within the same processing run.
2. **Target package**: which package does the generated type belong to? The fully qualified name passed to `Filer` must match the `package` statement and the class name in the source content.
3. **Originating elements**: which `Element` in the input program model caused the processor to generate that file? This information helps build tools determine the relationship between the input and the generated output.

For example, a source class:

```java
package demo.model;

@GenerateGreeting
public class AccountConfig {}
```

can cause the processor to generate the type:

```java
package demo.model;

public final class AccountConfigGreeting {
    public static String message() {
        return "Generated for demo.model.AccountConfig";
    }
}
```

The two snippets above are **illustrative**; compiling them requires the `GenerateGreeting` annotation along with a suitable processor. In this example, the generated type name is `demo.model.AccountConfigGreeting`, located in the `demo.model` package; the primary originating element is the `TypeElement` representing `demo.model.AccountConfig`.

**Principle:** A generated file must have a deterministic target name, Java content matching that name, and accurately declared originating relationships. `Filer` only handles file creation according to the compiler mechanism; it does not design class names, packages, or a collision-avoidance policy for the application.

## 2. Concepts to Distinguish

| Concept | Meaning | Example |
| --- | --- | --- |
| Simple name | Type name without the package | `AccountConfigGreeting` |
| Package name | Java package name, not a manually entered file path | `demo.model` |
| Fully qualified type name | Type name including the package; used when creating a Java source file | `demo.model.AccountConfigGreeting` |
| Generated source | The `.java` file created by the processor | `generated-src/demo/model/AccountConfigGreeting.java` |
| Generated class file | Bytecode created by the compiler after compiling the generated source | `out/demo/model/AccountConfigGreeting.class` |
| Originating element | An input `javax.lang.model.element.Element` that contributes to producing the output | `TypeElement` of `AccountConfig` |
| Output location | Output location managed by the compiler/file manager | `SOURCE_OUTPUT` or `CLASS_OUTPUT` |

In Java, a **package** is represented by a dot-separated name; mapping paths to the corresponding directories is handled by `Filer` and the file manager. Do not pass the path string `demo/model/AccountConfigGreeting.java` to the `createSourceFile` API and treat it as a fully qualified Java type name.

Distinguishing `Element` and `TypeMirror`:

- `Element` describes a **declaration**: class, interface, field, method, parameter, package, module...
- `TypeMirror` describes a **Java type at a location**: declared type, array, primitive, type variable, wildcard...
- The `originatingElements` parameter of `Filer` is **`Element...`**, not reflection's `Class<?>` and not a `TypeMirror` array. For an annotated class, pass that `TypeElement` itself.

## 3. Naming Generated Sources with Filer.createSourceFile

Primary API signature:

```java
JavaFileObject createSourceFile(
        CharSequence name,
        Element... originatingElements
) throws IOException;
```

The code above is an **abbreviated API signature**, not a method you declare yourself in the processor.

The `name` parameter represents the **canonical/fully qualified name of a type** to be created (per the Java `Filer` contract); for example:

```java
JavaFileObject file = processingEnv.getFiler()
        .createSourceFile("demo.model.AccountConfigGreeting", sourceElement);
```

`sourceElement` is a real `Element` in the compiler model, assumed to have already been obtained in the processor logic. `Filer` creates the file at the compiler's source output location; if using `javac -s generated-src`, the typical result is `generated-src/demo/model/AccountConfigGreeting.java`.

The content written to the file must be consistent with the target name:

```java
package demo.model;

public final class AccountConfigGreeting {
}
```

If `Filer` is asked to create `demo.model.AccountConfigGreeting` while the content declares `package demo.other;` or a different public class name, the compiler will not have a valid matching Java source file and the build may fail. `Filer` **does not automatically fix** the `package` line or class name based on the content you write.

### 3.1. Deriving Names from the Program Model Rather Than Slicing Path Strings

Given a `TypeElement source`:

```java
String packageName = processingEnv.getElementUtils()
        .getPackageOf(source).getQualifiedName().toString();

String generatedSimple = source.getSimpleName() + "Greeting";
String generatedName = packageName + "." + generatedSimple;
```

This is an illustrative snippet assuming `source` has already been obtained by the processor and that the example **only allows named packages**. It works for `demo.model.AccountConfig`:

- `getPackageOf(source)` retrieves the `PackageElement` of the source without relying on guessed folder structures.
- `getQualifiedName()` on `PackageElement` returns the canonical package name.
- `getSimpleName()` on `TypeElement` returns the simple name of the declaration.
- `generatedName` becomes `demo.model.AccountConfigGreeting`.

Use the compiler model instead of manually extracting source paths with `String.substring`, because the directory tree can be affected by generated sources, source roots, IDEs, module layouts, or build steps.

### 3.2. Java Identifier Validity Rules

A Java type or package name cannot be an arbitrary name from configuration:

- The simple name must be a **valid Java identifier** and not a keyword under the applicable language level.
- Each component of the package, such as `demo` and `model`, must be valid in a package name context.
- The generated name must not collide with an existing type name in the same package; Java does not allow two top-level types with the same qualified name in the same program.
- A Java identifier is not synonymous with the ASCII pattern `[A-Za-z_][A-Za-z0-9_]*`; Java allows other Unicode characters according to the language rules. You should not use a simple ASCII regex to declare all non-ASCII identifiers invalid.
- In particular, for names received from user options or annotation elements, **validate the value** instead of inserting it directly as a class name.

`javax.lang.model.SourceVersion` provides helpers such as `isIdentifier(...)` and `isKeyword(...)`; consider the source-level version that the processor actually supports. Building on an already-valid declaration name from the compiler model and appending a fixed suffix (such as `Greeting`) is usually much simpler and safer than allowing arbitrary file name input.

### 3.3. Default Package vs. Named Package

`PackageElement.getQualifiedName()` for an **unnamed package** can be an empty string. In that case, `packageName + "." + generatedSimple` would start with a dot and be invalid.

There are two valid design approaches to handle this:

1. **Explicitly disallow the unnamed package** and emit a clear error message; this is the policy of the runnable example below.
2. If the application truly supports the default package, construct the name using only the simple name, omit the `package ...;` line, and consider the limitations of the unnamed package.

You cannot take an empty package name and always prepend a dot. For reusable libraries, prefer **named packages** to avoid name collisions and manage APIs cleanly.

## 4. Package of Generated Code: Same Package or Separate Package?

Two common strategies:

**Generating in the same package as the original class:**

- `demo.model.AccountConfig` → `demo.model.AccountConfigGreeting`.
- Easy to trace the naming relationship; generated code can access package-private declarations in the same package if permitted by the relevant Java/module rules.
- Requires managing name collisions within each package and avoiding generating classes that clash with user sources.

**Generating into a dedicated package:**

- `demo.model.AccountConfig` → `demo.generated.AccountConfigGreeting`.
- Easy to group generated code and separate the generated API from the original model.
- Requires handling situations where multiple classes in different packages share the same simple name; the `Greeting` suffix alone may not be enough to make the name unique. You can incorporate qualified name information into the naming strategy, use a subpackage structure, or report a collision error.
- A separate package changes access rights to package-private members; do not assume generated code has the same privileges as the original class.

**Choose a strategy before generating:** a rule based solely on the simple name runs into trouble when both `alpha.User` and `beta.User` generate into `demo.generated.UserGreeting`. Design a naming function that is consistent across the entire project, rather than choosing arbitrarily based on the order in which the processor discovers elements.

With JPMS (Java Platform Module System), you must also consider named modules, `requires` and `exports` relationships, and how the compiler organizes a module's source output. The package name in source code does not by itself decide which modules are permitted to read the generated type. The full example below uses the **classpath** to keep the focus on `Filer`; do not automatically apply those same build commands as-is to a `module-info.java` project without adjusting the processor/module configuration.

## 5. What Are Originating Elements?

When creating a file, `Filer` allows passing zero or more originating `Element`s:

```java
processingEnv.getFiler().createSourceFile(
        generatedName,
        annotatedType
);
```

Here `annotatedType` is the `TypeElement` of the source that caused the processor to create `generatedName`.

For an output aggregated from **multiple declarations**, multiple originating elements can be passed:

```java
processingEnv.getFiler().createSourceFile(
        "demo.generated.CombinedIndex",
        customerType,
        invoiceType
);
```

This is an API illustration; the variables `customerType` and `invoiceType` are assumed to be valid `Element`s within the processor.

### Why Are originatingElements Important?

- **Dependency tracking:** build tools can record "which source declaration this generated file depends on".
- **Supporting incremental processing/builds:** some build systems use originating element information to determine which generated outputs need to be regenerated when inputs change.
- **Describing real relationships:** if an output is based on one class, pass that class; if an output aggregates multiple classes, you must account for all data sources that actually participate rather than passing just one element as a formality.

**Important limitations:**

1. `originatingElements` is only **hint information for the code-generation environment and build tools**; the Java compiler API does not guarantee that every build tool will automatically perform optimal incremental compilation based on this parameter.
2. It is **not a special annotation** attached to the generated class, not a list of `Class<?>` references at runtime, and not an element of Java source syntax.
3. It **does not replace** dependency determination by the build system, managing generated sources, or designing the processor to satisfy each tool's incremental requirements.
4. This varargs parameter can be omitted according to the API, but a processor aiming for clear incremental support should typically pass the `Element`s that actually caused the output.
5. For an output aggregated from **the entire source set** or data outside the compiler model, passing an arbitrary single `TypeElement` can misrepresent the dependencies. You must follow the contract of the actual incremental tool; in some situations, the processor should be considered **aggregating** rather than **isolating**.
6. A processor can generate a file from a source `Element` with `@Retention(SOURCE)`; the retention of the triggering annotation **does not prevent** passing the originating `Element` at compile time.

In the `AccountConfig` → `AccountConfigGreeting` example, this is a **one input declaration → one output source file** relationship; passing the `TypeElement` of `AccountConfig` is a direct and sensible way to record the origin.

## 6. Complete Java 17+ Example: Using Filer to Generate Sources with the Correct Name, Package, and Origin

This example uses a `@GenerateGreeting` annotation with `SOURCE` retention. The processor reads the annotation on **top-level classes in a named package**, retrieves the package and simple name using the compiler model, creates a new class in the same package with the `Greeting` suffix, and passes the source `TypeElement` to `createSourceFile`.

### 6.1. Initial Directory Structure

Create the files as follows:

```text
src/
├── demo/
│   ├── annotations/
│   │   └── GenerateGreeting.java
│   ├── model/
│   │   └── AccountConfig.java
│   └── app/
│       └── Main.java
└── tools/
    └── GreetingProcessor.java
```

This is a **classpath** example using a simple project without `module-info.java`.

### File 1 — `src/demo/annotations/GenerateGreeting.java`

```java
package demo.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {}
```

`SOURCE` is sufficient because the processor needs to read the annotation during compilation. `@Target(TYPE)` allows attaching it to type declarations; the processor will **narrow this down itself** to top-level classes.

### File 2 — `src/tools/GreetingProcessor.java`

```java
package tools;

import demo.annotations.GenerateGreeting;
import java.io.IOException;
import java.io.Writer;
import java.util.HashSet;
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
    private final Set<String> created = new HashSet<>();

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {
            if (element.getKind() != ElementKind.CLASS
                    || element.getEnclosingElement().getKind()
                            != ElementKind.PACKAGE) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Only top-level classes are supported", element);
                continue;
            }

            TypeElement source = (TypeElement) element;
            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(source).getQualifiedName().toString();

            if (packageName.isEmpty()) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "A named package is required", source);
                continue;
            }

            String simpleName = source.getSimpleName() + "Greeting";
            String fullName = packageName + "." + simpleName;

            if (!created.add(fullName)) {
                continue;
            }

            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile(fullName, source);
                try (Writer writer = file.openWriter()) {
                    writer.write("package " + packageName + ";\n\n");
                    writer.write("public final class " + simpleName + " {\n");
                    writer.write("    private " + simpleName + "() {}\n");
                    writer.write("    public static String message() {\n");
                    writer.write("        return \"Generated for "
                            + source.getQualifiedName() + "\";\n");
                    writer.write("    }\n}\n");
                }
            } catch (IOException error) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + fullName + ": "
                                + error.getMessage(),
                        source);
            }
        }
        return true;
    }
}
```

**Meaning of the key lines:**

- `@SupportedAnnotationTypes` indicates the annotation type that the processor declares it handles. `@SupportedSourceVersion(RELEASE_17)` specifies the supported language version.
- `getElementsAnnotatedWith(GenerateGreeting.class)` retrieves the `Element`s annotated in the current compilation round.
- `getKind() == ElementKind.CLASS` and `getEnclosingElement().getKind() == PACKAGE` restrict the example to **top-level classes**. This is a **rule of the demo**, not a mandatory limitation of all annotation processors.
- `getPackageOf(source)` retrieves the canonical package from the compiler model, rather than from a path string.
- `source.getSimpleName() + "Greeting"` produces a unique name **within the example**. A processor cannot guarantee against name collisions merely by appending a suffix, because another project might already declare a class with the same name.
- `created` keeps track of names already attempted in the processor instance to avoid recreating the same name in a subsequent processing round; it does **not** replace handling collisions with input/user sources or other processors.
- `createSourceFile(fullName, source)` creates the Java file under the fully qualified name and reports that **`source` is the originating element**.
- The `try (Writer writer = ...)` block closes the writer upon completion. The compiler can continue processing and compiling the generated file in the appropriate rounds.
- `IOException` is converted into a compiler diagnostic attached to `source` instead of printing a stack trace and treating the build as successful.
- `return true` indicates that the processor has **claimed the matching annotation types** in the round, per the `Processor` contract; it does not guarantee that no other processor is triggered by its own conditions.

In the demo, the generated string literal contains the **qualified name obtained from the compiler model**, with no arbitrary user data. If generating a Java string from an annotation element that contains quotes, control characters, or backslashes, you must **properly escape the literal according to Java rules**; never insert raw text directly into a string literal assuming it will always compile.

### File 3 — `src/demo/model/AccountConfig.java`

```java
package demo.model;

import demo.annotations.GenerateGreeting;

@GenerateGreeting
public class AccountConfig {}
```

This is the **originating element** of the generated class. The processor reads it at compile time even though `@GenerateGreeting` has `Retention(SOURCE)`.

### File 4 — `src/demo/app/Main.java`

```java
package demo.app;

import demo.model.AccountConfigGreeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(AccountConfigGreeting.message());
    }
}
```

`Main` uses a class **not yet present in the `src` directory when compilation begins**, but the processor will generate its source during the second `javac` pass.

### 6.2. Compiling the Processor First, Then Activating the Processor

In the directory containing `src`, if using Bash:

```bash
mkdir -p processor-out generated-src out
javac --release 17 -d processor-out src/demo/annotations/GenerateGreeting.java src/tools/GreetingProcessor.java
javac --release 17 -cp processor-out -processorpath processor-out -processor tools.GreetingProcessor -s generated-src -d out src/demo/model/AccountConfig.java src/demo/app/Main.java
java -cp out demo.app.Main
```

With Windows PowerShell, replace the first directory-creation line with:

```powershell
New-Item -ItemType Directory -Force processor-out, generated-src, out | Out-Null
```

Then run the three corresponding `javac`, `javac`, `java` commands in PowerShell.

**Exact stdout of the final `java` command:**

```text
Generated for demo.model.AccountConfig
```

The example was compiled with `javac --release 17` on a Java 17-compatible JDK and executed successfully. The compilation commands print no diagnostic lines in the valid case of the example.

### 6.3. Generated and Compiled Files

After the `javac` pass with the processor, the generated file is located under `-s generated-src`:

```text
generated-src/
└── demo/
    └── model/
        └── AccountConfigGreeting.java
```

Generated content in the example:

```java
package demo.model;

public final class AccountConfigGreeting {
    private AccountConfigGreeting() {}
    public static String message() {
        return "Generated for demo.model.AccountConfig";
    }
}
```

Under `out` are the bytecode files `demo/model/AccountConfigGreeting.class` and `demo/app/Main.class` along with the required classes from the second compilation pass. This pass can compile code referencing the generated class because the processor created the source in the right round/compiler-managed output.

The `-s` and `-d` options are very important:

- `-s generated-src`: specifies where the compiler writes **generated Java source files**.
- `-d out`: specifies where the compiler writes **compiled class files**.
- `-processorpath processor-out`: where the compiler locates and loads the **annotation processor**.
- `-processor tools.GreetingProcessor`: explicitly selects the processor without relying on auto-discovery/`META-INF/services`.
- `-cp processor-out`: supplies the `GenerateGreeting` annotation type for the application source compilation pass.
- `--release 17`: selects the Java 17 language/API target.

Do not run `java -cp generated-src demo.app.Main`; `generated-src` contains the Java source of the generated type, **not** the bytecode directory to run. In the demo, the executable classes are in `out`.

## 7. Why Must You Handle Rounds and Duplicate Generated Names?

Annotation processing can run across **multiple rounds**:

```text
Round 1: compiler brings AccountConfig into the model
         └── @GenerateGreeting triggers GreetingProcessor
             └── creates AccountConfigGreeting.java via Filer
Round 2: compiler brings generated source into processing/compilation
         └── may discover more annotations from generated sources
Final round: roundEnv.processingOver() == true
         └── no more sources are generated in the demo
```

This is an overview diagram; the actual number of rounds depends on the inputs and the work performed by other processors.

Key points:

1. A processor should not **recreate the same qualified name on every round**. `Filer` has a mechanism to prevent recreating the same name within the same processing run and can throw `FilerException` (a form of `IOException`).
2. `Set<String> created` in the example reduces the risk of recreating a name due to processor logic. However, it does **not** make generated names safe against existing user-defined type names or types being generated by other processors.
3. If the same generated name is requested from **two different source elements**, do not silently pick whichever is visited first and discard the other; in a production processor, you must clearly report the collision or use a naming strategy that guarantees uniqueness.
4. Do not write files directly via `FileWriter` into the build directory to bypass `Filer`. Doing so can break the compiler's output management, provenance, round ordering, and how build tools track generated files.
5. When generating **multiple per-element files**, you can create all files with distinct names in a single round. When generating an **aggregated file**, you should determine when the input set is complete and how to handle origins and incrementality so the same name is not emitted multiple times.

### FilerException Is Not a Random Error

Several situations commonly trigger this error:

- The processor calls `createSourceFile("demo.model.AccountConfigGreeting", ...)` twice in the same processing run.
- The generated name collides with a source/class file already treated by the compiler as an input or output in the current processing run.
- Two processors generate the same qualified name.
- A single processor computes the same target name for two annotated classes without detecting the collision.

`FilerException` is a signal to re-examine your **output identifiers and code-generation rules**, not a reason to delete files or keep overwriting recklessly. File write permissions, invalid output paths, or I/O failures can also raise other `IOException`s.

## 8. How Do createSourceFile, createClassFile, and createResource Differ?

`Filer` provides API groups corresponding to each output kind:

| API | Purpose | Name/Destination |
| --- | --- | --- |
| `createSourceFile(name, origins...)` | Creates a `.java` Java source file that the compiler can process further | Package-qualified Java type name, e.g., `demo.model.AccountConfigGreeting` |
| `createClassFile(name, origins...)` | Creates a class file directly when valid bytecode is available | Corresponding Java type name; not for writing Java text |
| `createResource(location, moduleAndPkg, relativeName, origins...)` | Creates a resource that is not a Java source or class file | Output location, package or module-and-package when applicable, relative file name |

Example of creating a resource associated with a source element:

```java
FileObject file = processingEnv.getFiler().createResource(
        StandardLocation.CLASS_OUTPUT,
        "demo.model",
        "metadata.txt",
        sourceType
);
try (Writer out = file.openWriter()) {
    out.write("generated for demo.model.AccountConfig");
}
```

This is illustrative code **inside a processor**: it requires importing `javax.tools.FileObject`, `javax.tools.StandardLocation`, and `java.io.Writer`, and declaring `sourceType`. It can create a resource under the class output area for the `demo.model` package, without creating a Java type named `metadata`.

Rules for resources:

- `relativeName` must be a valid relative name, not an arbitrary absolute path or a string using `../` to escape the output location.
- `moduleAndPkg` in module-aware environments has additional rules regarding modules and packages; if the build uses JPMS, configure the appropriate module output rather than assuming an arbitrary folder is a Java package/module.
- `CLASS_OUTPUT` is typically where resources packaged with compiled classes go; `SOURCE_OUTPUT` is for generated source output depending on the resource type/tooling.
- Pass appropriate originating elements for **both generated sources and resources** to describe the actual inputs that caused each output.

`createClassFile` requires **bytecode in valid JVM class file format**, not `writer.write("public class ...")`. If you only need to generate Java source, use `createSourceFile` and let `javac` compile it.

## 9. Originating Elements vs. @Generated and Annotations on the Generated Type

Two mechanisms are often conflated:

**`originatingElements`**: passed to `Filer` at file-creation time. It describes the relationship between the generated output and source declarations in the **compilation/build environment**.

**`@Generated`**: in Java 9+ environments, the `javax.annotation.processing.Generated` annotation can be emitted into generated source code as a marker indicating "tool-generated code", such as processor information. It is **metadata on the generated source**, does not replace the originating elements parameter, and does not by itself tell build tools all the input sources that were used.

Illustrative syntax example:

```java
@javax.annotation.processing.Generated("tools.GreetingProcessor")
public final class ExampleGenerated {}
```

The snippet above illustrates how to mark a generated type; it is not code that creates a file via `Filer`. `@Generated` has `SOURCE` retention and is not a runtime reflection mechanism for inferring originating elements. Even with `@Generated`, the processor still needs to specify the accurate origins for `createSourceFile` if the build tool relies on this information.

A processor can emit `@Generated` metadata to help humans and source-reading tools distinguish generated code from hand-written code, **while simultaneously** passing `originatingElements` to describe provenance for the build. These two complement rather than replace each other.

## 10. Rules for Designing a Reliable Processor

### 10.1. Deterministic Naming

Given the same set of inputs, a processor should compute the **same qualified output name** regardless of element traversal order or round order. Do not use timestamps, random values, element order in a collection without guaranteed order, or arbitrary global state as required components of a generated Java type name.

If a name depends on multiple inputs, you need a stable rule to combine or identify those inputs. When emitting an aggregated file, you can use a controlled fixed name such as `demo.generated.Registry`, provided you resolve collisions and coordinate with other processors.

### 10.2. Validate Inputs Before Opening a Writer

Before calling `createSourceFile`:

1. Check that the element is of a supported kind (`ElementKind`, nesting, package).
2. Compute the package and qualified name from the compiler model, not from a manually constructed path.
3. Verify that the name is valid and does not conflict with known names in the input set controlled by the processor.
4. Identify the originating elements that are genuinely involved.
5. Only then call `Filer` and open the writer; finally, close the writer using try-with-resources.

Do not create half a file only to discover invalid data afterward: partially generated output can cause the compiler to report additional confusing errors.

### 10.3. Emit Diagnostics at the Right Location

Use `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, message, element)` to report errors at the relevant source declaration. Project users will see a compiler diagnostic attached to the element, which is easier to fix than `System.out.println` or a stack trace.

`Diagnostic.Kind.WARNING` is suitable for issues where processing can continue; `ERROR` is suitable when valid code cannot be generated. When writing a generated file fails, never silently treat the process as successful.

### 10.4. Stability and Incremental Compilation

If an output depends on **exactly one annotated element**, the one-to-one relationship is usually easy to track. If an output depends on **all annotated elements** (for example, a unified registry), you must construct the dependency/aggregation model properly for the build tool. `Filer` allows declaring originating elements, but it **does not automatically turn every processor into an isolating/incremental processor**.

Additionally, changing an annotation element, package name, or source class name can change the generated qualified name. The build system must clean up stale outputs and handle dependencies correctly; the processor should not write ad-hoc logic to arbitrarily delete paths outside `Filer`.

### 10.5. Do Not Default to Generating into the Unnamed Package

A library should explicitly specify whether it supports the unnamed package. If not supported, emit a diagnostic as in the demo. If supported, compute the name and the `package` line separately for the package-less case.

### 10.6. Generated Code Must Still Obey Java and JPMS

Generated Java source is ordinary Java source. It is subject to the rules governing public class and file names, packages, visibility, generic types, imports, module accessibility, and compiler flags. `Filer` does not automatically grant access to private members or bypass `exports`/`requires`.

Avoid generating code by copying raw class or field names without handling keywords, special characters, escaping, and collisions. Distinguish between errors caused by Filer output placement and errors caused by invalid generated Java source.

## 11. Common Pitfalls and How to Fix Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `FilerException: Attempt to recreate a file` | The same name is created multiple times in a processing run or collides with a compiler-managed file | Use deterministic naming, prevent duplicates, and check for collisions; do not overwrite |
| Java compiler reports package/type mismatch | `createSourceFile` receives `a.b.X`, but the source declares `package c.d;` or a public class other than `X` | Emit `package a.b;` and declare `X` properly |
| Name starts with a leading dot like `.AccountGreeting` | Unconditionally concatenating an empty package with `"."` | Handle the unnamed package separately or report it as unsupported |
| Two classes in different packages generate the same output | Using the simple name and discarding package/source info | Use sufficiently distinguishing names; emit a diagnostic on collision |
| Processor runs but generates no code | Processor is not registered/activated, unsupported annotation type, or no matching annotated elements | Use `-processor`, `-processorpath`, and check supported types and rounds |
| Generated class cannot be found | Incorrect package name, class name, source output, or compilation command | Check `-s`, `-d`, generated qualified name, and compiler errors |
| Partial file generated, build fails mysteriously | Writer not closed or I/O error during writing | Use try-with-resources and convert `IOException` into a diagnostic |
| Passing an arbitrary originating element for an aggregated file | Provenance does not match actual inputs | Record contributing sources and choose an appropriate incremental model |
| Assuming `@Generated` replaces originatingElements | They are two independent mechanisms | Add `@Generated` if desired; still pass origins to Filer |
| Writing Java directly into `createClassFile` | This API is meant for binary class files | Use `createSourceFile` to generate Java source |
| Relying on file system paths as package names | Source roots/module layouts and the package model differ from path strings | Use `Elements.getPackageOf` |
| Generating Java literals from unescaped strings | Characters like `"`, `\`, and newlines break the generated source | Escape according to Java source syntax or use a compatible JavaPoet library |

## 12. Self-Verification with the Complete Example

You can perform the following small experiments (each experiment modifies the fixture and recompiles, rather than applying changes simultaneously):

**Experiment A — change the source package.** Move `AccountConfig` to `demo.domain`, and update its path, package declaration, and dependency in `Main`. If the processor retrieves the package properly from the compiler model, the generated source must be in the `demo.domain` package. If the generated code still ends up in `demo.model`, it means the processor hard-coded the package.

**Experiment B — rename the source class.** Rename `AccountConfig` to `UserConfig` along with its input file name. The generated name must change to `demo.model.UserConfigGreeting` following the suffix rule. Remember to clean/reset output directories in your test environment when needed to avoid confusing stale class files with new outputs.

**Experiment C — use the unnamed package.** Apply `@GenerateGreeting` to a top-level class without a `package` declaration. The demo processor will emit the message `A named package is required`. This is **the designed behavior of the example**, and does not prove that Filer always forbids the unnamed package.

**Experiment D — nested class.** Apply `@GenerateGreeting` to a nested class. The demo processor reports `Only top-level classes are supported`. If a project needs to support nested classes, it must compute collision-free generated names from `getQualifiedName`/the enclosing chain and consider the placement of the generated type.

**Experiment E — name collision.** Add a hand-written user source `demo.model.AccountConfigGreeting` and try compiling. The compiler/`Filer` may report a conflict error. Fix this by changing the naming strategy or reporting a clear error; **do not** delete the user's source.

**Experiment F — SOURCE retention.** Keep `@GenerateGreeting` as `SOURCE`. Run `javap -v -classpath out demo.model.AccountConfig`: the SOURCE annotation usage does not appear in the annotation attributes on the source class, yet the generated class `AccountConfigGreeting` is still produced because the processor handled it at compile time.

**Experiment G — origins from multiple classes.** If generating an `AllConfigs` file based on two annotated classes, pass both originating elements and verify whether the build tool in use properly supports this dependency model or requires the processor to be configured as aggregating. Do not infer solely from the fact that the basic Java example compiles successfully.

## 13. Checklist Before Adding a Processor to a Project

- [ ] Identify annotations used for **compile-time validation/code generation** and set the proper retention (usually `SOURCE` if no runtime metadata is needed).
- [ ] Identify accurately which `ElementKind`s the processor supports; handle nested/top-level classes and empty packages separately if needed.
- [ ] Generated type names follow a rule that is **valid, stable, and unique within the build scope**.
- [ ] `createSourceFile` receives a **qualified type name**, not a manually constructed path; the source content contains the matching package and class name.
- [ ] Processor passes **actual originating elements** for each output when available; do not assume `@Generated` replaces them.
- [ ] Processor checks for collisions and does not create duplicates across rounds or between annotated elements.
- [ ] Writer is closed, and `IOException`/`FilerException` errors become compiler diagnostics.
- [ ] Build commands explicitly configure processor path, discovery/`-processor`, `-s`, and `-d`; generated sources are processed by the compiler.
- [ ] If using JPMS or incremental builds, verify dependency/package/module rules and origin metadata with the specific build tool.
- [ ] Include tests covering: valid sources, empty package, nested classes, collisions, multiple rounds, renamed inputs, and stale outputs.

**Key takeaway:** `Filer.createSourceFile("pkg.Type", originatingElement)` creates a Java source file by **package-qualified type name**, and the content must properly declare `package pkg;` and `Type`. `originatingElements` describes **the input declarations leading to the generated file**, which is useful for build tools but does not by itself guarantee incremental compilation. Deterministic naming, retrieving packages from the compiler model, and managing collisions/rounds are the foundation for reliable Java code generation in annotation processors.
