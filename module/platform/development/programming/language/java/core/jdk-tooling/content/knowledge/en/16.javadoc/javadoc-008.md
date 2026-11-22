# Custom Doclets in Javadoc

A doclet is the component that determines how Javadoc collects information from Java source code and what output it produces. By default, Javadoc uses the Standard Doclet to generate HTML documentation. When you need a custom documentation format, want to extract an API into JSON/Markdown, generate audit reports, or integrate documentation into another system, you can write a **custom doclet** using the `jdk.javadoc.doclet` API.

A custom doclet receives the language model of packages, classes, methods, fields, and Javadoc comments. It can traverse selected elements, read `@param`, `@return`, and `@throws` content, inspect modifiers and data types, and emit results in a format defined by your project.

## 1. What is a Doclet?

Javadoc is a tool that reads Java source code and documentation comments to generate documentation. A doclet is the extension that Javadoc invokes to process the documentation model.

In a typical command:

~~~bash
javadoc -d docs -sourcepath src com.acme.api
~~~

Javadoc uses the default Standard Doclet and generates HTML pages. The Standard Doclet is responsible for page layout, navigation, indexes, API links, stylesheets, and many formatting options.

When specifying a custom doclet:

~~~bash
javadoc -doclet com.acme.tools.ApiDoclet -docletpath build/doclet
~~~

Javadoc loads the project-provided doclet class and invokes its API. The custom doclet decides how to traverse elements and generate output. It can print text reports or generate Markdown, JSON, XML, or HTML as needed.

Some scenarios where you should write a custom doclet:

- Generating a public API catalog for an internal library.
- Exporting class/method signatures as JSON for consumption by other tools.
- Enforcing documentation conventions, such as requiring public methods to have `@param` and `@return`.
- Generating documentation following an organization's custom template.
- Collecting metadata from annotations and documentation comments.
- Integrating Javadoc with a custom documentation system or build pipeline.

If you only want to customize how a specific Javadoc tag is rendered in standard HTML documentation, a Taglet is usually a better fit. A custom doclet replaces the output processor; a Taglet extends how the Standard Doclet handles a particular tag.

## 2. The Modern Doclet API

The modern doclet API resides in the JDK module `jdk.javadoc`, package:

~~~java
jdk.javadoc.doclet
~~~

The central interface is:

~~~java
public interface Doclet
~~~

This API has been available since Java 9. When developing for Java 17+, use `jdk.javadoc.doclet.Doclet` and the `javax.lang.model` language model. Older doclets based on the `com.sun.javadoc` package belong to the legacy API and should not be used for new projects.

A custom doclet typically implements five main methods:

| Method | Role |
|---|---|
| `init(Locale, Reporter)` | Receives the locale and reporter object provided by Javadoc. |
| `getName()` | Returns the doclet name for display in tool information. |
| `getSupportedOptions()` | Declares the custom options accepted by the doclet. |
| `getSupportedSourceVersion()` | Declares the Java syntax version supported by the doclet. |
| `run(DocletEnvironment)` | Performs traversal of the documentation model and generates output. |

The `run` method returns `true` if the doclet completes successfully and `false` if processing fails. You should not return `true` when critical errors have been detected that make the output unreliable.

## 3. Lifecycle When Javadoc Runs a Custom Doclet

General workflow:

1. Javadoc reads command-line options and identifies the doclet class via `-doclet`.
2. The tool loads the doclet from `-docletpath` or the corresponding module mechanism.
3. Javadoc initializes the doclet using `init`, passing the locale and `Reporter`.
4. The tool queries the name, source version, and options supported by the doclet.
5. Javadoc parses the source, resolves types, and builds the documentation model.
6. Javadoc calls `run` with `DocletEnvironment`.
7. The doclet traverses selected elements, reads comments, and generates output.
8. The doclet returns a success/failure status; Javadoc exits with the corresponding result.

Processing model:

~~~text
Java source + Javadoc comments
             |
             v
          javadoc
             |
             v
      Load custom Doclet
             |
             v
       init(locale, reporter)
             |
             v
   Parse and select source elements
             |
             v
       DocletEnvironment
             |
             v
       run(environment)
             |
             v
   Inspect elements and comments
             |
             v
     Custom output / diagnostics
~~~

A doclet does not replace the compiler itself. Javadoc uses the compiler infrastructure to parse source code and resolve types. The doclet works with the model prepared by the tool.

## 4. Key Components of the Doclet API

### DocletEnvironment

`DocletEnvironment` is the primary input object to `run`. It provides:

- `getSpecifiedElements()`: elements specified directly in the Javadoc input.
- `getIncludedElements()`: elements selected for inclusion in the documentation.
- `isIncluded(element)`: checks whether an element is included in the documentation.
- `isSelected(element)`: checks whether an element is selected according to the processing configuration.
- `getDocTrees()`: accesses the tree structure of documentation comments.
- `getElementUtils()`: utility for looking up and analyzing Java elements.
- `getTypeUtils()`: utility for analyzing type relationships and transformations.
- `getSourceVersion()`: the Java source version being processed.
- `getJavaFileManager()`: the file manager used by Javadoc.

Use `getIncludedElements()` when you need to process elements selected by Javadoc. This list is affected by options such as `-public`, `-protected`, `-package`, or `-private`.

### Element and TypeElement

The `javax.lang.model.element` model represents Java constructs:

| Interface | Represents |
|---|---|
| `Element` | General Java element. |
| `PackageElement` | Package. |
| `TypeElement` | Class, interface, enum, record, or annotation type. |
| `ExecutableElement` | Method or constructor. |
| `VariableElement` | Field, parameter, or variable. |
| `TypeParameterElement` | Generic type parameter. |
| `ModuleElement` | Module and module directives. |

`Element.getEnclosedElements()` returns elements declared directly inside the current element. For example, for a `TypeElement`, the list may contain fields, constructors, methods, and nested types.

`ElementFilter` in the `javax.lang.model.util` package helps filter elements by kind:

~~~java
ElementFilter.typesIn(elements)
ElementFilter.methodsIn(elements)
ElementFilter.fieldsIn(elements)
ElementFilter.constructorsIn(elements)
~~~

These methods help avoid manually casting each element.

### Elements and Types

`Elements` provides declaration-level operations:

- Looking up a package or type by name.
- Getting the binary name of a type.
- Getting all members of a type, including inherited members.
- Reading documentation comments as plain text.
- Checking whether an element is deprecated.
- Retrieving annotation values with defaults applied.

`Types` provides type-level operations:

- Checking subtype relationships.
- Checking whether two types are equivalent.
- Getting a type after type erasure.
- Checking assignability or type conversions.
- Working with declared types, array types, wildcards, and type variables.

Use `Element` to ask what a declaration is; use `TypeMirror` and `Types` to analyze the type of that declaration. Avoid comparing generic types solely by comparing their display strings when exact semantic checks are required.

### DocTrees and DocTree

`DocTrees` provides a tree structure for documentation comments. It is useful when a doclet needs to read tags or analyze content instead of just retrieving raw text.

Example:

~~~java
DocTrees docTrees = environment.getDocTrees();
DocCommentTree commentTree = docTrees.getDocCommentTree(element);
~~~

`DocCommentTree` represents the description, block tags, and inline tags. Common tag types include:

- `@param`
- `@return`
- `@throws` or `@exception`
- `@since`
- `@deprecated`
- `@see`
- `{@link ...}`
- `{@code ...}`

You can traverse nodes in the tree using a visitor from the `com.sun.source.doctree` package. When you need to accurately inspect `@param` tags, parameter names, and content, tree-based processing is generally safer than matching strings with regular expressions.

## 5. Reporter and Error Reporting

Javadoc passes a `Reporter` into `init`. The doclet uses this object to emit messages by severity level:

- `Diagnostic.Kind.NOTE`: informational message.
- `Diagnostic.Kind.WARNING`: warning.
- `Diagnostic.Kind.MANDATORY_WARNING`: mandatory warning.
- `Diagnostic.Kind.ERROR`: error.
- `Diagnostic.Kind.OTHER`: other notification.

Example:

~~~java
reporter.print(
    Diagnostic.Kind.WARNING,
    element,
    "Public method is missing a documentation comment."
);
~~~

`Reporter` also provides `getStandardWriter()` for printing standard output and `getDiagnosticWriter()` for printing diagnostic output. When generating text reports, use the writer provided by Javadoc instead of writing directly to `System.out`; this makes the output more compatible with the tool's runtime environment.

Documentation content errors should be reported via `Reporter`, attached to the relevant element whenever possible. This helps users pinpoint the exact class or method that needs fixing.

## 6. Custom Doclet Options

A doclet can declare custom options through `getSupportedOptions()`. Each option implements `Doclet.Option`.

An option must provide:

- `getNames()`: option names, which may include multiple aliases.
- `getArgumentCount()`: number of arguments following the option.
- `getParameters()`: how arguments are described in help output.
- `getDescription()`: description of functionality.
- `getKind()`: option category.
- `process(option, arguments)`: processes the received values.

For example, a doclet might support:

~~~bash
javadoc -doclet doclet.ApiSummaryDoclet \
  -docletpath build/doclet \
  --api-heading "Customer API" \
  --source-path src \
  -subpackages com.acme.api
~~~

In this example, `--api-heading` is a custom doclet option. `Doclet.Option.Kind.OTHER` is appropriate for doclet-defined options; do not use names that collide with options already owned by Javadoc or another doclet.

`process` returns `true` when the value is accepted. If an argument is invalid, the doclet can return `false` so Javadoc reports an option error. For options with multiple arguments, verify the argument count and validate each value before storing it in the doclet's state.

## 7. Complete Example: Creating an API Summary Doclet

The following example writes a small doclet that lists types selected by Javadoc, prints each class's documentation comment, and prints the signatures of public/protected methods. The doclet provides an `--api-heading` option to customize the title.

Directory structure:

~~~text
custom-doclet-demo/
└── src/
    ├── doclet/
    │   └── ApiSummaryDoclet.java
    └── com/
        └── acme/
            └── api/
                └── Greeting.java
~~~

File `src/doclet/ApiSummaryDoclet.java`:

~~~java
package doclet;

import java.io.PrintWriter;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.Modifier;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.ElementFilter;
import jdk.javadoc.doclet.Doclet;
import jdk.javadoc.doclet.DocletEnvironment;
import jdk.javadoc.doclet.Reporter;

public final class ApiSummaryDoclet implements Doclet {
    private Reporter reporter;
    private String heading = "API Summary";

    @Override
    public void init(Locale locale, Reporter reporter) {
        this.reporter = reporter;
    }

    @Override
    public String getName() {
        return "API Summary Doclet";
    }

    @Override
    public Set<? extends Option> getSupportedOptions() {
        Option headingOption = new Option() {
            @Override
            public int getArgumentCount() {
                return 1;
            }

            @Override
            public String getDescription() {
                return "Heading printed before the API summary";
            }

            @Override
            public Kind getKind() {
                return Kind.OTHER;
            }

            @Override
            public List<String> getNames() {
                return List.of("--api-heading");
            }

            @Override
            public String getParameters() {
                return "<text>";
            }

            @Override
            public boolean process(String option, List<String> arguments) {
                heading = arguments.get(0);
                return true;
            }
        };

        return Set.of(headingOption);
    }

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean run(DocletEnvironment environment) {
        PrintWriter out = reporter.getStandardWriter();
        out.println(heading);

        for (TypeElement type :
                ElementFilter.typesIn(environment.getIncludedElements())) {
            out.println(type.getQualifiedName());

            String comment =
                    environment.getElementUtils().getDocComment(type);
            if (comment != null) {
                out.println("  " + comment.replace('\n', ' ').trim());
            }

            for (ExecutableElement method :
                    ElementFilter.methodsIn(type.getEnclosedElements())) {
                Set<Modifier> modifiers = method.getModifiers();
                boolean visible =
                        modifiers.contains(Modifier.PUBLIC)
                        || modifiers.contains(Modifier.PROTECTED);

                if (visible) {
                    String parameters = method.getParameters().stream()
                            .map(parameter -> parameter.asType().toString())
                            .collect(Collectors.joining(", "));

                    out.println(
                            "  " + method.getReturnType() + " "
                            + method.getSimpleName()
                            + "(" + parameters + ")"
                    );
                }
            }
        }

        out.flush();
        return true;
    }
}
~~~

File `src/com/acme/api/Greeting.java`:

~~~java
package com.acme.api;

/** A small greeting service. */
public class Greeting {

    /** Returns a greeting for the given name. */
    public String greet(String name) {
        return "Hello, " + name + "!";
    }

    private void internalCheck() {
    }
}
~~~

### Step 1: Compile the Custom Doclet

From the `custom-doclet-demo` root directory:

~~~bash
mkdir -p build/doclet
javac -d build/doclet src/doclet/ApiSummaryDoclet.java
~~~

On PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/doclet | Out-Null
javac -d build/doclet src/doclet/ApiSummaryDoclet.java
~~~

The doclet class is generated at `build/doclet/doclet/ApiSummaryDoclet.class`. This is the class that Javadoc will load using `-docletpath`.

### Step 2: Run Javadoc with the Custom Doclet

Linux/macOS:

~~~bash
javadoc -quiet \
  -doclet doclet.ApiSummaryDoclet \
  -docletpath build/doclet \
  --api-heading "Customer API" \
  --source-path src \
  -subpackages com.acme.api
~~~

Windows PowerShell:

~~~powershell
javadoc -quiet -doclet doclet.ApiSummaryDoclet -docletpath build/doclet --api-heading "Customer API" --source-path src -subpackages com.acme.api
~~~

Javadoc searches for sources in `src`, selects the `com.acme.api` package, loads `ApiSummaryDoclet` from `build/doclet`, and passes the value `Customer API` to the `--api-heading` option.

### Step 3: Check the Output

With JDK 24.0.2, the output of the example is:

~~~text
Customer API
com.acme.api.Greeting
  A small greeting service.
  java.lang.String greet(java.lang.String)
~~~

The `internalCheck()` method does not appear because the doclet only prints methods with `public` or `protected` modifiers. `getDocComment(type)` retrieves the class description from the Javadoc comment. `getReturnType()` and `getParameters()` provide the method's return type and parameter types.

The example generates a text report via `Reporter.getStandardWriter()`. It does not produce an HTML site like the Standard Doclet. If you want to generate HTML/JSON into files, the doclet needs to define how the output directory is selected and write those files itself.

## 8. Traversing Elements and Avoiding Missing APIs

When building a real-world doclet, you must decide precisely which kinds of elements need to be processed.

### Specified Elements vs. Included Elements

`getSpecifiedElements()` is useful when you need to know which packages or sources the user specified on the command line. `getIncludedElements()` is useful when you need to process the types/modules that Javadoc selected for documentation.

Do not assume every type on the source path is selected. Visibility, package, module, and source selection options affect the set of included elements.

### Directly Declared Members vs. Inherited Members

In the example, `type.getEnclosedElements()` only returns members declared directly inside the type. If you need to list inherited methods as well, use:

~~~java
environment.getElementUtils().getAllMembers(type)
~~~

Then filter the elements with `ElementFilter.methodsIn(...)` and handle modifiers and overridden/hidden members according to your report's requirements.

If the goal is to export a public API, decide whether to include inherited methods, bridge methods, synthetic members, constructors, record components, and nested types. Do not treat the list of directly declared members as the entire API visible to clients.

### Types and Generics

`ExecutableElement.getReturnType()` and `getParameters()` provide types as `TypeMirror`. `TypeMirror.toString()` is useful for simple reports, but it is not a stable serialization format for all purposes.

If you need to handle generics, subtypes, or erasure, use `Types` instead of string parsing. If you need canonical type names, use `Elements.getBinaryName()` or `getQualifiedName()` depending on your purpose. Binary names and qualified names differ for nested classes.

## 9. Reading and Validating Javadoc Tags

A custom doclet often needs to verify whether documentation is complete. You can read comments as plain text:

~~~java
String comment = environment.getElementUtils().getDocComment(element);
~~~

This approach is convenient when you only need a simple description. When you need to distinguish tags, use `DocTrees`:

~~~java
DocTrees docTrees = environment.getDocTrees();
DocCommentTree tree = docTrees.getDocCommentTree(element);
~~~

You can then check whether:

- Methods have `@param` for their parameters.
- Methods returning a value have `@return`.
- Methods declaring checked exceptions have corresponding `@throws` tags.
- Deprecated APIs have a `@deprecated` explanation.
- Classes have the required description, examples, and cross-reference links.

Avoid using simple regular expressions on raw comments to parse all tags. Javadoc syntax supports inline tags, HTML, links, and nested structures; the DocTree API preserves the structure for more accurate handling.

You can report warnings at the offending element:

~~~java
reporter.print(
    Diagnostic.Kind.WARNING,
    element,
    "Missing @param documentation."
);
~~~

A quality-checking doclet can accumulate error/warning counts, print element locations, and return `false` if policy requires the build to fail when errors are found.

## 10. Generating Custom Output Files

A custom doclet can produce output outside the console, such as Markdown or JSON. Two decisions are required:

1. Determine the output path via a custom option, such as `--output-dir <path>`.
2. Create directories and write files with an explicit encoding, typically UTF-8.

Example of writing a file using Java NIO:

~~~java
Path output = Path.of(outputDirectory, "api-summary.md");
Files.createDirectories(output.getParent());
Files.writeString(output, markdown, StandardCharsets.UTF_8);
~~~

In production code, handle `IOException`, validate paths, and report errors via `Reporter`. Do not assume the Standard Doclet's `-d` option automatically applies to a custom doclet. If your doclet does not support that option, declare a dedicated output option or explicitly integrate an appropriate file manager.

If generating HTML, escape characters from source/comments before inserting them into HTML. Do not embed Javadoc content or element names directly into HTML without escaping special characters. If generating JSON, use a proper JSON serializer instead of manual string concatenation.

For large documentation sets, build intermediate data models first and then render Markdown/HTML/JSON. This separates analyzing the Java model from presentation and makes output testing easier.

## 11. Custom Doclet, Standard Doclet, and Taglet

These three options address different needs:

| Tool | When to Use |
|---|---|
| Standard Doclet | You need Javadoc's standard HTML documentation, navigation, and API links. |
| Custom Doclet | You need to change how the model is traversed and generate output in a custom format. |
| Taglet | You need to process a custom Javadoc tag or extend how a tag is rendered in standard documentation. |

For example, if you want the `@apiNote` tag rendered in a custom way while keeping all standard HTML output, a Taglet is usually the smaller extension point. If you want to export the entire API into a standalone JSON schema, a custom doclet is a better fit.

A custom doclet does not automatically inherit options from the Standard Doclet. Options like `-d`, `-windowtitle`, `-link`, `-stylesheetfile`, and many HTML options belong to the Standard Doclet. When using a custom doclet, only pass options supported by the Javadoc tool or the active doclet.

## 12. Running Doclets with Packages, Classpath, and Modules

Javadoc input options affect how sources and dependencies are resolved:

| Option | Purpose |
|---|---|
| `-sourcepath` or `--source-path` | Location to search for source packages. |
| `-classpath` or `--class-path` | Location to search for dependency classes/JARs. |
| `-doclet` | Fully qualified name of the custom doclet class. |
| `-docletpath` | Location containing the doclet class or JAR. |
| `-subpackages` | Selects a package and its subpackages for processing. |
| `-private` | Requests inclusion of private members in the selected documentation set. |
| `--module-path` | Location to search for application modules. |
| `--module` | Specifies the module to document. |

On Windows, multiple paths in a classpath or module path are separated by semicolons. On Linux/macOS, colons are used.

For a doclet packaged in a JAR:

~~~bash
javadoc -doclet doclet.ApiSummaryDoclet \
  -docletpath build/api-doclet.jar \
  --source-path src \
  -subpackages com.acme.api
~~~

If the doclet or sources belong to a module, configure the module path and module accordingly. Ensure the JDK running Javadoc includes the `jdk.javadoc` module.

## 13. Testing a Custom Doclet

A custom doclet should be tested like any source-processing program, not just verified to compile.

Useful test categories:

- **Option parsing:** valid options, missing arguments, empty values, and unsupported options.
- **Selection:** public/protected/private, packages, nested types, and modules.
- **Element model:** classes, interfaces, enums, records, annotations, fields, constructors, and overloads.
- **Inheritance:** directly declared methods and inherited methods.
- **Documentation comments:** descriptions, block tags, inline tags, links, and HTML.
- **Diagnostics:** warnings/errors have the right kind and are attached to the right element.
- **Output:** UTF-8 encoding, escaping, deterministic ordering, and output content.
- **Failure handling:** invalid source code, unresolved types, and unwritable output paths.

Maintain small source fixtures with expected output saved as golden files. When modifying the doclet, compare new output against the fixtures to catch unintended changes.

You can run Javadoc with `-verbose` when you need to inspect processing:

~~~bash
javadoc -verbose -doclet doclet.ApiSummaryDoclet \
  -docletpath build/doclet \
  --source-path src \
  -subpackages com.acme.api
~~~

When CI needs to block warnings, Javadoc supports `-Werror` to fail on any warning. Enable it only after the team agrees on which warnings must be addressed and has verified the output on the target JDK.

## 14. Common Issues and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `Cannot find doclet class` | Wrong class name or `-docletpath` does not point to the directory/JAR containing the doclet. | Verify the package, class name, and doclet path. |
| `ClassNotFoundException` at startup | The doclet has dependencies not on the corresponding load path. | Bundle dependencies or configure the classpath/module path for the doclet. |
| `invalid flag` for custom option | Option is not returned by `getSupportedOptions()` or option name conflicts. | Check `getNames()`, `getArgumentCount()`, and `process()`. |
| Doclet misses expected classes | Package not selected, wrong source path, or visibility filter excludes elements. | Check `-sourcepath`, `-subpackages`, `-private`, and `getIncludedElements()`. |
| Missing inherited methods | Only traversing `getEnclosedElements()`. | Use `Elements.getAllMembers(type)` if inherited APIs are needed. |
| Cannot read `@param` or `@return` | Only using raw comment strings or mishandling tag structure. | Use `DocTrees` and `DocCommentTree`. |
| Duplicate members in output | Traversing both direct members and all inherited members without filtering overrides/hides. | Define API export rules and use `Elements.overrides()`/`hides()` as appropriate. |
| Corrupted characters in HTML output | Source content inserted directly into HTML without escaping. | Escape HTML or use a safe rendering library. |
| Invalid JSON output | Manual string concatenation without escaping quotes, newlines, or Unicode. | Use a JSON serializer. |
| Doclet runs on newer JDK with source version warning | `getSupportedSourceVersion()` declares a lower version than the source being processed. | Return the source version the doclet actually supports and test on the target JDK. |

## 15. Custom Doclet Development Workflow

A practical workflow:

1. Define the output to generate: text report, Markdown, HTML, or JSON.
2. Define the element kinds to read and visibility rules.
3. Design custom options for output paths, package filters, or report modes.
4. Implement `Doclet`, `Doclet.Option`, and `run`.
5. Use `DocletEnvironment`, `Elements`, `Types`, and `DocTrees` to read the Java model.
6. Use `Reporter` to emit warnings and errors with source locations.
7. Create source fixtures covering classes, methods, generics, inheritance, and Javadoc tags.
8. Compile the doclet and run Javadoc in tests.
9. Compare output against expected results.
10. Re-run on the JDK versions supported by your project and verify options/diagnostics.

Do not build source-parsing logic by reading `.java` files and matching strings with regex when your goal is to understand Java structure. Javadoc already provides the element model and comment trees; using these APIs handles overloads, generics, annotations, nested types, and tags much more accurately.

## 16. Summary

A custom doclet is Javadoc's extension point for controlling how the source code model is read and how output is generated. `Doclet` defines the lifecycle; `DocletEnvironment` provides the selected elements; `Elements` and `Types` support declaration and type analysis; `DocTrees` processes documentation comments; `Reporter` emits diagnostics; and `Doclet.Option` declares custom options.

When you only need to add a new tag type to standard HTML output, consider a Taglet. When you need to generate a custom report or documentation format from Java sources, a custom doclet lets you organize a clear, testable workflow that integrates cleanly into your build.
