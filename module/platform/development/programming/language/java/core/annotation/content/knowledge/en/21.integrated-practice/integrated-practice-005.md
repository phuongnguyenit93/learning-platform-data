# Writing an Annotation Processor to Detect Invalid Declarations in Java

## 1. Practice Goal

An **annotation processor** can run right during the `javac` compilation process to inspect annotated declarations and emit error messages with exact source locations. As a result, a business rule or architectural convention can be **checked before the application runs**, instead of waiting until runtime.

In this lesson, we design the `@Route` annotation for a method that handles a path. Its simple contract is:

- Used only on **class methods**, not on fields or interface methods.
- The method must be **`public`, not `static`, not `abstract`**.
- The method **has no parameters**.
- The return type must be **exactly `java.lang.String`**.
- The `path` value must match the regular expression `/[a-z][a-z0-9/-]*`, for example `/health` or `/users`.
- Within **the same class**, no two valid methods may use the same `path`.

**Valid** example:

~~~java
@Route(path = "/health")
public String health() {
    return "ok";
}
~~~

**Invalid** example:

~~~java
@Route(path = "health")
private static int health(int code) {
    return code;
}
~~~

The second example violates multiple rules at the same time. The processor detects them using the standard `javax.annotation.processing` and `javax.lang.model` APIs, and then sends `Diagnostic.Kind.ERROR` to the compiler. `javac` returns a non-zero exit code when errors occur; the program is not considered to have built successfully.

**Scope of this lesson:** validating **annotated declarations**, without arbitrarily modifying the AST, adding methods to classes, or creating an HTTP server application. `@Route` is only an example annotation defined by us; it is not a built-in JDK annotation or part of a web framework.

## 2. Tools in Java Annotation Processing

Java SE 17 provides JSR 269 in the `java.compiler` module. The main components are:

| API | Role in this lesson |
|---|---|
| `AbstractProcessor` | Base class for implementing an annotation processor |
| `@SupportedAnnotationTypes` | Declares the annotation type names supported by the processor |
| `@SupportedSourceVersion` | Declares the language version supported by the processor |
| `process(annotations, round)` | Entry point invoked by the compiler during processing rounds |
| `RoundEnvironment.getElementsAnnotatedWith(...)` | Retrieves elements carrying the annotation in the current round |
| `Element.getKind()` / `ElementKind` | Distinguishes between method, field, class, record, etc. |
| `ExecutableElement` | Reads a method's modifiers, parameters, and return type |
| `TypeMirror` and `Types.isSameType(...)` | Compares types according to the type system model |
| `AnnotationMirror`, `AnnotationValue` | Reads annotation values at compile time |
| `Elements.getElementValuesWithDefaults(...)` | Retrieves both explicit and `default` values |
| `Messager.printMessage(...)` | Reports errors, warnings, or notes to the compiler |

A typical processor **does not need `java.lang.reflect.Method` or `Class.forName` to analyze source classes**. While the compiler is still analyzing the source, the target class does not even have a `.class` file yet for runtime reflection to load.

The processor also does not need the annotation to have `RetentionPolicy.RUNTIME`. For compile-time checks, `SOURCE` retention is completely appropriate.

### Two Types of Rules to Separate

1. **Syntax and language rules already checked by `javac`:** for example, `@Target(ElementType.METHOD)` causes `@Route` placed on a field to be rejected by the compiler.
2. **Rules designed by ourselves:** for example, the path must start with `/`, the method must not be `static`, or two routes in a class must not be duplicates. The processor is responsible for checking these.

There is no need to rewrite the entire Java compiler inside an annotation processor; only check the constraints that the annotation type and the language do not yet sufficiently describe.

## 3. Defining the `@Route` Contract

File **`src/demo/Route.java`**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.METHOD)
public @interface Route {
    String path() default "";
}
~~~

Intentional choices:

- `@Target(METHOD)` restricts where the annotation can be placed to method declarations. If `@Route` is placed on a class/field, the compiler reports that the annotation is not applicable to that declaration kind, before or during the compilation process; there is no need for the processor itself to detect an element that is not allowed to carry the annotation.
- `@Retention(SOURCE)` means the metadata is only needed at compile time. It can be observed by the processor through the compiler's model; there is no need to retain it at runtime merely to validate declarations.
- `String path() default ""` makes the `@Route` syntax **valid from an annotation interface standpoint** even when `path` is not provided. The processor then proactively reports an error for the empty string. This is an example of **separating valid Java syntax from the business contract**.
- The `path` value must be a compile-time constant expression of type `String`. A method call such as `System.getenv(...)` is not a valid annotation value at the language level itself.

The regex `/[a-z][a-z0-9/-]*` in this lesson is **a sample policy**: starting with a slash, followed by a lowercase letter and allowed characters. For example, `/health` and `/v1/users` are valid; `health`, `/`, and `/with space` are invalid. This policy **is not a comprehensive URI standard**, and does not handle path variables, URL encoding, consecutive slashes, percent escapes, or internationalization. When deploying to a real system, a clearer specification is needed.

## 4. Standalone Project Structure for Experimentation

Use the following structure, relative to the `project/` directory:

~~~text
project/
├── RouteProcessor.java
├── src/
│   └── demo/
│       ├── Route.java
│       ├── ValidRoutes.java
│       ├── App.java
│       └── InvalidRoutes.java
├── processor/       # Created during build
├── valid-classes/   # Created during build
└── invalid-classes/ # Created during build
~~~

`RouteProcessor.java` is in the **default package** solely to simplify the command line. The source to be checked resides in the `demo` package. In a real project, the processor should have its own package, be packaged as a JAR, be configured via `annotationProcessor`/`processorpath`, and be tested as an independent module.

Practice sequence:

1. Compile the **processor** first.
2. Compile the **valid** example and specify the processor using `-processor RouteProcessor`.
3. Run the application; verify stdout.
4. Compile the **invalid** example using that processor; inspect diagnostics and the exit code.
5. Understand why the compiler blocks the build and how to improve the messages.

## 5. Complete Code: `RouteProcessor.java`

This file is **standalone and compiles with Java 17**. The processor inspects declarations, reads the annotation argument, and reports errors at the violating method itself.

~~~java
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.AnnotationValue;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.Modifier;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.Route")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class RouteProcessor extends AbstractProcessor {
    private final Set<String> registered = new HashSet<>();

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        if (round.processingOver()) {
            return true;
        }

        TypeElement route = processingEnv.getElementUtils()
                .getTypeElement("demo.Route");
        TypeElement string = processingEnv.getElementUtils()
                .getTypeElement("java.lang.String");

        if (route == null || string == null) {
            return false;
        }

        for (Element element : round.getElementsAnnotatedWith(route)) {
            if (element.getKind() != ElementKind.METHOD) {
                error(element, "@Route requires a method");
                continue;
            }

            ExecutableElement method = (ExecutableElement) element;
            boolean ok = true;

            if (method.getEnclosingElement().getKind()
                    != ElementKind.CLASS) {
                error(method, "@Route requires a method in a class");
                ok = false;
            }

            Set<Modifier> modifiers = method.getModifiers();
            if (!modifiers.contains(Modifier.PUBLIC)
                    || modifiers.contains(Modifier.STATIC)
                    || modifiers.contains(Modifier.ABSTRACT)) {
                error(method,
                        "@Route method must be public, instance and concrete");
                ok = false;
            }

            if (!method.getParameters().isEmpty()) {
                error(method, "@Route method must have no parameters");
                ok = false;
            }

            if (!processingEnv.getTypeUtils().isSameType(
                    method.getReturnType(), string.asType())) {
                error(method, "@Route method must return String");
                ok = false;
            }

            String path = readPath(method, route);
            if (path == null
                    || !path.matches("/[a-z][a-z0-9/-]*")) {
                error(method, "@Route path must match /[a-z][a-z0-9/-]*");
                ok = false;
            }

            if (ok) {
                String key = method.getEnclosingElement().toString()
                        + "#" + path;
                if (!registered.add(key)) {
                    error(method,
                            "Duplicate @Route path in the same class: " + path);
                }
            }
        }

        return true;
    }

    private String readPath(
            ExecutableElement method,
            TypeElement annotationType) {

        for (AnnotationMirror mirror : method.getAnnotationMirrors()) {
            if (!mirror.getAnnotationType().asElement()
                    .equals(annotationType)) {
                continue;
            }

            for (Map.Entry<? extends ExecutableElement,
                           ? extends AnnotationValue> entry
                    : processingEnv.getElementUtils()
                        .getElementValuesWithDefaults(mirror).entrySet()) {

                if (entry.getKey().getSimpleName().contentEquals("path")) {
                    return (String) entry.getValue().getValue();
                }
            }
        }
        return null;
    }

    private void error(Element element, String message) {
        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.ERROR,
                "[ROUTE] " + message,
                element);
    }
}
~~~

### 5.1. Why Not Read the Annotation via Reflection?

`method` is an **`ExecutableElement`** provided by the compiler, not a `java.lang.reflect.Method`. An annotation with `SOURCE` retention may not exist in the compiled class file; invoking runtime reflection to analyze this declaration is inappropriate.

In the example, `readPath(...)` iterates through `AnnotationMirror` to find the `demo.Route` annotation type and retrieve the `path` element. Comparing `mirror.getAnnotationType().asElement().equals(annotationType)` is based on the symbol model of the same compilation environment.

`getElementValuesWithDefaults(mirror)` is important because `@Route` **without specifying `path`** must be read as `""` and then rejected by the validation rule. If only `mirror.getElementValues()` were used, elements using a default value **would not appear in the map**, easily causing the code to skip the check.

For a syntactically valid annotation, the `path` value is type-checked by Java as `String`, so the cast `(String) entry.getValue().getValue()` in the example is appropriate. A more general-purpose processor needs to handle multiple `AnnotationValue` kinds (primitives, enums, classes, nested annotations, arrays) instead of assuming everything is a String.

### 5.2. Why Use `Types.isSameType`?

If we call:

~~~java
method.getReturnType().toString().equals("java.lang.String")
~~~

we are comparing **string representations of types**, rather than the compiler's type system rules. The proper example uses:

~~~java
processingEnv.getTypeUtils().isSameType(
        method.getReturnType(),
        string.asType())
~~~

to require an exact `java.lang.String`. Methods returning `Object`, `CharSequence`, `int`, `void`, or `StringBuilder` are all rejected. This is intentional in this lesson: the contract requires **exactly String**, not “anything that can be converted to a string”.

It is necessary to distinguish **equality** from **assignability**: if the contract requires a subtype of an interface, you can look into `Types.isAssignable(...)` or an equivalent check instead of `isSameType(...)`. Decide based on the design intent, rather than swapping arbitrarily.

### 5.3. Why Check `ElementKind` Before Casting?

`RoundEnvironment.getElementsAnnotatedWith(...)` returns `Element` instances. To call `getParameters()` and `getReturnType()`, we need an `ExecutableElement`, but an unconditional cast could throw a `ClassCastException` if the processor is modified or the annotation target differs.

Therefore:

~~~java
if (element.getKind() != ElementKind.METHOD) {
    error(element, "@Route requires a method");
    continue;
}
ExecutableElement method = (ExecutableElement) element;
~~~

The example's `@Target(METHOD)` already eliminates other locations at the compiler layer, but the defensive branch is sensible when the processor is extended or has to process source code with existing errors.

### 5.4. Why Report Errors on `Element`?

`Messager.printMessage(Diagnostic.Kind.ERROR, message, element)` instructs the compiler to associate the diagnostic with the relevant declaration. With `javac`, the message typically points to the method line and displays a caret `^`.

Do not use `System.out.println("ERROR")` as a substitute: a line on stdout **does not by itself cause the compiler to treat the build as failed**. Only `Diagnostic.Kind.ERROR` expresses a compilation error through the standard processor interface.

### 5.5. Why Store Seen Paths?

The processor builds a key from **the declared class name + path**, and then adds it to a `HashSet`. If a second valid method uses the same key, `Set.add(...)` returns `false` and emits the diagnostic:

~~~text
[ROUTE] Duplicate @Route path in the same class: /dupe
~~~

The demo only checks for **duplicates within the same class**, without forbidding the same path in two classes. It also does not account for inherited route methods, overload hierarchies, complex module/package scoping, or route normalization. Those are API decisions that require further design in a real application.

`registered` is **state of the processor instance within a single compilation task**, so it helps detect duplicates when the compiler processes annotated elements across multiple rounds. Do not treat this `Set` as a database reused across different builds.

## 6. Valid Example: `ValidRoutes.java` and `App.java`

Create **`src/demo/ValidRoutes.java`**:

~~~java
package demo;

public final class ValidRoutes {
    @Route(path = "/health")
    public String health() {
        return "ok";
    }

    @Route(path = "/users")
    public String users() {
        return "users";
    }
}
~~~

Both methods are `public`, instance, concrete, have no parameters, return exactly `String`, and have different paths matching the regex.

Create **`src/demo/App.java`**:

~~~java
package demo;

public class App {
    public static void main(String[] args) {
        ValidRoutes routes = new ValidRoutes();
        System.out.println(routes.health());
        System.out.println(routes.users());
    }
}
~~~

The `@Route` annotation in the example **does not create an HTTP routing mechanism**; the methods are still invoked via regular Java. The processor's function is to guard the contract at compile time, not to change how the JVM invokes methods.

### 6.1. Compiling the Processor

In the `project/` directory, in Bash:

~~~bash
mkdir -p processor valid-classes invalid-classes

javac --release 17 -d processor RouteProcessor.java
~~~

This command compiles the processor first so that `javac` in the next step can load the `RouteProcessor` class. It does not need to load `demo.Route` when compiling the processor because the processor **looks up the annotation type by name at processing time**, rather than importing the annotation type as a compile-time Java dependency.

### 6.2. Compiling the Valid Example

~~~bash
javac --release 17 \
  -processorpath processor \
  -processor RouteProcessor \
  -d valid-classes \
  src/demo/Route.java \
  src/demo/ValidRoutes.java \
  src/demo/App.java
~~~

Options:

- `--release 17`: applies the Java 17 source/API target.
- `-processorpath processor`: where the compiler loads the annotation processor from.
- `-processor RouteProcessor`: explicitly selects the processor; does not rely on the service discovery mechanism.
- `-d valid-classes`: where `.class` output is stored.
- Three source files comprising the annotation type, the valid class, and the test program.

A valid build command **is not required to print any message**. Having no diagnostics is not an issue; check the exit code with the build tool/shell (success is 0).

### 6.3. Running the Result

~~~bash
java -cp valid-classes demo.App
~~~

Exact stdout:

~~~text
ok
users
~~~

These two lines were run and verified using `javac --release 17` and `java`. They are printed by `App`, **not** by the annotation processor.

## 7. Invalid Example: `InvalidRoutes.java`

Create **`src/demo/InvalidRoutes.java`** with independent violations:

~~~java
package demo;

class InvalidRoutes {
    @Route(path = "relative")
    public String relative() { return "bad"; }

    @Route(path = "/hidden")
    private String hidden() { return "bad"; }

    @Route(path = "/static")
    public static String staticMethod() { return "bad"; }

    @Route(path = "/params")
    public String withArg(String x) { return x; }

    @Route(path = "/number")
    public int number() { return 3; }

    @Route(path = "/dupe")
    public String first() { return "a"; }

    @Route(path = "/dupe")
    public String second() { return "b"; }

    @Route
    public String missingPath() { return "bad"; }
}

interface InvalidInterface {
    @Route(path = "/interface")
    String interfaceMethod();
}

abstract class AbstractRoutes {
    @Route(path = "/abstract")
    public abstract String abstractMethod();
}
~~~

All annotations in the example above **are allowed by Java with respect to `@Target(METHOD)`**: they are all placed on method declarations. However, they violate **the contract defined by this lesson's processor**, so a compiler running the processor properly will report errors.

Standalone compilation command:

~~~bash
javac --release 17 \
  -processorpath processor \
  -processor RouteProcessor \
  -d invalid-classes \
  src/demo/Route.java \
  src/demo/InvalidRoutes.java
~~~

**Expected:** the `javac` command fails (non-zero exit code). The processor may emit multiple diagnostics in the same compilation; exact file line numbers/paths/carets depend on the machine and source positions.

### 7.1. Verified List of Diagnostics

In an actual run targeting Java 17, the processor emitted **10 errors**:

| Declaration | Error reported by the processor |
|---|---|
| `relative()` | `@Route path must match /[a-z][a-z0-9/-]*` |
| `hidden()` | `@Route method must be public, instance and concrete` |
| `staticMethod()` | `@Route method must be public, instance and concrete` |
| `withArg(String)` | `@Route method must have no parameters` |
| `number()` | `@Route method must return String` |
| `second()` | `Duplicate @Route path in the same class: /dupe` |
| `missingPath()` | `@Route path must match /[a-z][a-z0-9/-]*` |
| `interfaceMethod()` | `@Route requires a method in a class` |
| `interfaceMethod()` | `@Route method must be public, instance and concrete` |
| `abstractMethod()` | `@Route method must be public, instance and concrete` |

Each error has the `[ROUTE]` prefix added by the `error(...)` method. Because the processor **does not stop at the very first error**, `interfaceMethod()` has two distinct errors: the enclosing element is `INTERFACE` and the method is `ABSTRACT`.

A typical portion of the output (only diagnostic content is excerpted; paths and line numbers are omitted):

~~~text
error: [ROUTE] @Route path must match /[a-z][a-z0-9/-]*
error: [ROUTE] @Route method must be public, instance and concrete
error: [ROUTE] @Route method must have no parameters
error: [ROUTE] @Route method must return String
error: [ROUTE] Duplicate @Route path in the same class: /dupe
...
10 errors
~~~

This is **not the application's stdout output**. Diagnostics are typically written by `javac` to **stderr**; a build script or IDE needs to evaluate the exit code/diagnostics rather than only reading stdout.

### 7.2. Why Is `@Route` Without `path` Also Caught by the Processor?

`Route.path()` has `default ""`, so `@Route` does not violate Java's required-element declaration rules. However, the processor uses `getElementValuesWithDefaults`, retrieves `""`, and applies the regex. The empty string does not match, so `missingPath()` is reported as an error.

If `default` is removed from `Route.path()`, the compiler will require annotation users to provide `path` everywhere. Which approach is better depends on API design: if you want the **compiler** to check for missing required values, omit the default; if you want the **processor** to check the path and emit a custom message, you can use a sentinel and validate it.

### 7.3. The Compiler Can Catch Errors Earlier Than the Processor

Another **intentionally invalid** example that does not need to be run in the test set:

~~~java
class WrongPlace {
    @Route(path = "/x")
    String field; // WRONG: @Route only has @Target(METHOD) and does not apply to FIELD
}
~~~

In this case, the compiler will report that the annotation is not applicable to a field, because `@Target` is a language rule. One should not expect the processor to always receive `FIELD` in `round.getElementsAnnotatedWith(Route)` on source code that already violates target rules. The `ElementKind.METHOD` check branch in the processor is **defensive**, not a replacement for `@Target`.

## 8. Explanation of the Validation Mechanisms by Group

### 8.1. Declaration Kind and Enclosing Element

~~~java
element.getKind() == ElementKind.METHOD
method.getEnclosingElement().getKind() == ElementKind.CLASS
~~~

- The first condition indicates that the element is a method declaration.
- The second condition only accepts methods **inside a class**.
- Methods in an interface have the enclosing kind `INTERFACE` and are rejected.
- Methods in a record have the enclosing kind `RECORD` and, under the current demo contract, are also rejected.
- Methods in an annotation type have the enclosing kind `ANNOTATION_TYPE` and are likewise not class methods under this contract.

If you want to allow methods in records or interfaces, you must **explicitly change the contract** and rewrite the validation accordingly; do not turn `ElementKind.RECORD` into `CLASS` in the equality comparison.

### 8.2. Modifiers: Distinguishing public, static, and abstract

~~~java
Set<Modifier> modifiers = method.getModifiers();

if (!modifiers.contains(Modifier.PUBLIC)
        || modifiers.contains(Modifier.STATIC)
        || modifiers.contains(Modifier.ABSTRACT)) {
    error(method, "...");
}
~~~

Because a public concrete instance method is required, all three conditions need to be checked. We cannot rely solely on `@Target(METHOD)` because Java allows attaching the annotation to private/static/abstract methods when the target is METHOD.

A method in an interface is treated by the compiler as having the corresponding modifiers per interface method rules, yet in this lesson it is also rejected because its enclosing kind is not CLASS. Emitting two errors on the same declaration is consistent with the example's algorithm.

### 8.3. Parameters

~~~java
method.getParameters().isEmpty()
~~~

This checks **the method's declared parameter list**, not whether the class has fields or generic type parameters. The method `String withArg(String x)` fails even though it returns exactly String and has a valid path.

### 8.4. Return Type

~~~java
processingEnv.getTypeUtils().isSameType(
        method.getReturnType(),
        string.asType())
~~~

This checks the actual type using the compiler model. `int` is not equivalent to `java.lang.String`. `Object` or `CharSequence` is also not strictly String. If the contract is meant to accept a set of return types, change the rule to use `Types.isAssignable` or a specific check, and then add tests.

### 8.5. Regex

~~~java
path.matches("/[a-z][a-z0-9/-]*")
~~~

`String.matches` matches the entire string. `/health` and `/v1/users` are valid; `relative`, `/`, `/WhiteSpace`, and `""` are invalid. The contract is intentionally kept simple for learning processors.

### 8.6. Duplicate Paths Within a Class

~~~java
String key = method.getEnclosingElement().toString() + "#" + path;
if (!registered.add(key)) {
    error(method, "Duplicate @Route path in the same class: " + path);
}
~~~

By including the enclosing class in the key, `/health` in two different classes **is not treated as a duplicate**. In a real routing system, you might need application-wide scope instead of per-class scope, class-level route prefixes, HTTP methods, or path normalization. In that case, the key model must be redesigned.

The example only adds the key if the **other rules are already valid**, so that a method with an invalid path or return type does not occupy the slot of a valid route.

## 9. How to Test a Processor Professionally

A quality processor needs both **positive tests** and **negative tests**:

- **Positive:** valid source compiles successfully, the processor emits no ERROR, and the application runs properly when runtime code is present.
- **Negative:** invalid source fails to compile; the compiler has at least a diagnostic with the correct content and pointing to the right declaration.
- **Boundary:** empty path, path with spaces, modifier combinations, methods in interfaces/records, generic methods, and overloads/duplicate names.
- **Multiple rounds:** if there are generated sources, verify that no false duplicates or unnecessary repeated errors are reported.
- **Isolation:** run the processor with an explicit `-processorpath`, without relying on a processor loaded incidentally from the classpath.
- **Version:** run with `--release 17` or the actual source version to which the project is committed.
- **Result code:** negative tests need to assert that compilation **failed**, not merely search for an error string in the console.

With a Bash terminal, you can check the exit code after `javac`:

~~~bash
javac --release 17 \
  -processorpath processor \
  -processor RouteProcessor \
  -d invalid-classes \
  src/demo/Route.java \
  src/demo/InvalidRoutes.java

echo "$?"
~~~

When `javac` emits `Diagnostic.Kind.ERROR`, the exit code value is **non-zero**. Some shells/build tools print diagnostics differently; do not hardcode tests that depend strictly on paths, line numbers, or message ordering.

### 9.1. Do Not Demand a Fixed Error Count Across All Refactors

With **this exact set of examples and processor in the lesson**, 10 diagnostics were observed. However, when adding rules or changing code, the count may change: a single declaration can violate multiple rules, and different compilers may attach additional language diagnostics.

In unit tests of a real processor, you should verify **which error was emitted for which declaration**, rather than matching the entire stderr output verbatim. Compilation testing frameworks can support asserting diagnostics in a structured way; no external tools beyond the JDK are needed to understand this lesson.

## 10. `process`, Processing Rounds, and the Meaning of `return true`

The `process(...)` method may be called by the compiler across multiple rounds. In the example:

~~~java
if (round.processingOver()) {
    return true;
}
~~~

prevents the processor from processing annotated elements again in the **final round**. No sources are generated in this lesson, but in other processors, generated sources/classes can trigger new rounds.

The rounds are typically visualized as:

~~~text
Initial round:
  compiler knows the source declarations
  RouteProcessor receives methods with @Route
  validates -> Messager ERROR if invalid

Potential subsequent rounds:
  only when the tool/compiler has additional matching generated sources/classes

Final round:
  round.processingOver() == true
  processor finishes processing
~~~

`@SupportedAnnotationTypes("demo.Route")` specifies the supported annotation type. `return true` means the processor **claims the annotations in the set it handles during the round**; it does not mean the compiler automatically generates code or modifies the source. With multiple processors, claiming can affect which processors still receive the annotation for processing, so it must be chosen intentionally.

### 10.1. `-processor` and Processor Discovery via Service Metadata

The practice command uses:

~~~bash
-processor RouteProcessor
~~~

so the compiler knows the exact processor class to load. In a real processor JAR, you can publish the processor name via `META-INF/services/javax.annotation.processing.Processor` or an equivalent build configuration. In that case, processor selection depends on the build/toolchain configuration. Declaring `@SupportedAnnotationTypes` **does not automatically register the processor on the classpath** across all execution modes.

If processor configuration is missing, `javac` may compile Java-syntactically valid source code **without running our custom validation**. This is a very notable integration pitfall when a project transitions from CLI to an IDE or CI.

## 11. Limitations of the Demo Version

### 11.1. Only Inspects Annotated Declarations

The processor does not scan every method in a class and infer which method “should” have `@Route`. It only iterates over the `Element` instances returned by `RoundEnvironment` because they carry the annotation. If you want to require a certain class to have a route, you need to check at the class level or scan types/members according to a separate contract.

### 11.2. Does Not Modify User Code

Standard JSR 269 does not provide a mechanism to add methods, modify modifiers, or remove annotations directly from a class being compiled. The processor reports errors so the developer **fixes the source**, or it can use `Filer` to **generate new files** in other use cases.

### 11.3. Incomplete Multi-Module / Multi-Compilation Checking

`registered` only sees methods processed by the processor within **the current compilation task**. If multiple modules are compiled separately, the processor does not automatically maintain a system-wide list of routes. To check for duplicates across an entire application, you need to design a registry/build aggregation or handle it with a tool that checks a broader scope.

### 11.4. Does Not Analyze Inheritance

`getElementsAnnotatedWith(route)` processes elements carrying the annotation in the round. It does not automatically traverse all inherited methods, overridden methods, or interface default methods according to an arbitrary “route policy”. You need to analyze `Elements.getAllMembers(...)`, `Elements.overrides(...)`, or the type hierarchy when application rules require it.

### 11.5. Does Not Inspect Logic Inside the Method

The processor only inspects the declaration/signature and annotation values. It does not prove that the `health()` method actually handles requests, never throws errors, never leaks data, or always returns a valid response. Analyzing the syntax tree of a method body requires AST tooling; verifying behavior requires additional runtime/integration tests.

### 11.6. The Regex Is Not an HTTP Routing Parser

The sample regex can allow `//` later in the path and does not support `{id}`. HTTP frameworks typically have their own rules for URI templates, URL encoding, HTTP methods, route precedence, and conflict detection. Extending the contract requires adding a parser and tests, not just editing a regex string.

### 11.7. Diagnostics Are Attached Only to the Method, Not Yet to the `path` Argument

Currently, using `printMessage(kind, message, element)`, the caret typically sits on the method declaration. If you want the error to point directly to the `path` value in `@Route(path = "...")`, `Messager` provides overloads that also accept `AnnotationMirror` and `AnnotationValue`. Therefore, you can upgrade `readPath(...)` to return the mirror/value as well and use the specialized overload.

### 11.8. Processor State and Code Generation

A processor can generate additional sources across rounds, so it is necessary to distinguish between reading elements per round and already-processed state. The `registered` set in this lesson is initialized per processor instance and is not guaranteed to automatically act as a persistence layer across builds.

## 12. Extending the Practice Exercise

Once the example runs properly, you can upgrade it step by step:

### 12.1. Validate a Valid Path Without Supporting Nested Routes

Replace the regex with a parser or stricter rules; add negative tests for `//`, trailing slashes, Unicode characters, query strings, or path variables. This is an opportunity to practice **compile-time input validation** without needing to build a web server.

### 12.2. Require Methods Not to Declare Checked Exceptions

Use `ExecutableElement.getThrownTypes()` and the `Types`/`Elements` APIs to analyze the exception list. You should not conclude “no checked exceptions” merely because `getThrownTypes().isEmpty()`: a method can declare unchecked exceptions; the classification must be determined accurately.

### 12.3. Allow Records or Interface Default Methods

Change the enclosing kind and modifier rules to allow `ElementKind.RECORD` or `INTERFACE` under the new policy. Then test record accessors, interface default methods, abstract methods, and generated code consuming them.

### 12.4. Validate Routes Returning `CompletionStage<String>`

If you want a method to return a generic type, you need to work with `DeclaredType`, `TypeElement`, and `Types` to compare generic arguments properly; do not merely compare `TypeMirror.toString()`. You need to test raw types, wildcards, and erasure when designing this.

### 12.5. Turn Error Results Into Regression Tests

Create tests that compile multiple source snippets and verify:

- `javac` exit code 0 for valid code.
- Non-zero `javac` exit code for invalid code.
- A diagnostic containing `[ROUTE]` and the corresponding rule is present.
- The processor does not produce false-positive duplicates when compiling multiple classes.
- The messages point to the appropriate declaration locations.

Tests of this kind are very useful for maintaining the annotation API as the team adds new rules or upgrades the JDK.

## 13. Common Mistakes When Writing Your Own Processor

**Processor does not run:** simply declaring `@SupportedAnnotationTypes` on a class is not enough for the compiler to discover the processor automatically. Specify `-processor` and `-processorpath` explicitly or package proper service registration, and verify with a negative test.

**Cannot see `SOURCE` annotations via reflection:** this is expected given the retention policy. The processor should use the compiler model; do not force the annotation to change to `RUNTIME` just to run compile-time validation.

**`ClassCastException` when casting an element:** check `getKind()` or use type-safe `ElementFilter` before casting to `ExecutableElement`/`TypeElement`.

**Only printing errors to stdout:** `System.out.println(...)` is not a substitute for `Messager`. Use `Diagnostic.Kind.ERROR` to make compilation fail.

**Mistakes when reading default elements:** `AnnotationMirror.getElementValues()` does not automatically include `default` values; use `Elements.getElementValuesWithDefaults(...)` if you want the rule to apply to every usage.

**Comparing types by display name:** the string from `asType().toString()` is not a formal type comparison. Use `Types` to avoid missing generics or qualified names.

**Using `return false` without understanding its effect:** returning false allows other processors to continue examining the annotation types; returning true claims them in the round per the contract. This is not a “build passed/failed” flag; errors are reported through `Messager`.

**Relying on diagnostic ordering:** the traversal order of elements/processing rounds should not be treated as a stable contract for designing business logic. For negative tests, check the set of messages and locations without assuming the first error is always the same method.

**Confusing compiler errors with processor errors:** when a `@Route` appears on a field, the error from the `@Target` rule may be emitted directly by the compiler without the `[ROUTE]` prefix. Do not treat that as proof that the processor did not run.

**Treating a processor as a source-code editing tool:** JSR 269 has no standard API for adding a getter to an existing declaration. A processor can emit diagnostics or generate new files using `Filer`, but it does not “patch” the original AST through `Element`.

## 14. Acceptance Checklist

- [ ] The annotation type declares appropriate `@Target` and `@Retention`.
- [ ] The processor supports the right annotation type name and source version.
- [ ] The processor is loaded via explicit compiler/build configuration.
- [ ] The code uses `RoundEnvironment` to retrieve the right annotated elements.
- [ ] Every cast of `Element` to a sub-interface checks its kind.
- [ ] Rules for modifiers, parameters, return type, and value are checked independently.
- [ ] Type checking uses `Types` instead of text comparison.
- [ ] Metadata with `default` values is read using `getElementValuesWithDefaults`.
- [ ] Errors are reported via `Messager` with `Diagnostic.Kind.ERROR`.
- [ ] Positive tests compile successfully, and the application prints `ok` and `users` as expected.
- [ ] Negative tests fail compilation and display the expected diagnostics.
- [ ] State/duplicate tracking works accurately for the chosen class and compilation task scope.
- [ ] Re-run a clean build with the target JDK without relying on stale compilation metadata.
- [ ] Do not accidentally modify sources, create out-of-scope files, or suppress diagnostics.

## 15. Authoritative References

- [Java SE 17 — `AbstractProcessor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): base class for implementing a processor.
- [Java SE 17 — `Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): contract for annotation processing, claiming, and processing rounds.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): finding annotated elements and processing rounds.
- [Java SE 17 — `Messager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): diagnostics attached to an element, annotation mirror, or annotation value.
- [Java SE 17 — `ExecutableElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ExecutableElement.html): method signatures, parameters, and return types.
- [Java SE 17 — `ElementKind`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ElementKind.html): classifying declarations.
- [Java SE 17 — `Types`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Types.html): comparing types in the compiler model.
- [Java SE 17 — `Elements`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html): looking up types and retrieving annotation values with defaults.
- [Java SE 17 — `AnnotatedConstruct`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/AnnotatedConstruct.html): accessing annotation mirrors in a compile-time context.
- [JDK 17 `javac` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): the `-processor`, `-processorpath`, `--release`, and `-d` flags.

**Summary:** A processor that detects invalid declarations has three core steps: **finding the right `Element`, checking the contract with the compiler model, and reporting `Diagnostic.Kind.ERROR` at the violating declaration**. Through the `@Route` example, you can enforce rules on modifiers, parameters, return types, annotation values, and duplicates right inside `javac`, while using positive/negative compilation tests to prove that valid code passes through and invalid code is blocked before runtime.
