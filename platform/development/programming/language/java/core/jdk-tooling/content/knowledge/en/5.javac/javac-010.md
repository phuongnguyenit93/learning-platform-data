# Java Compilation Errors

Compilation errors occur when the Java compiler `javac` cannot translate source code into valid bytecode. When this happens, the compilation command exits with a non-zero status and typically fails to produce all required `.class` files. The cause may lie in syntax, data types, class/method names, access permissions, packages, dependencies, modules, or Java version configuration.

Knowing how to read `javac` diagnostics helps you fix the actual root cause instead of guessing. Start from the first meaningful message, identify the location and expression involved, and recompile to verify. A single root error can trigger many subsequent messages, so fixing one cause at a time in order is usually more effective than trying to fix a batch of error lines at once.

## 1. Distinguishing Compilation Errors, Warnings, and Runtime Errors

The following three types of outcomes have different meanings:

- **Compile-time error:** the source code violates language syntax or type/language rules, or the compiler cannot find a required class or method. `javac` cannot complete compilation.
- **Compiler warning:** the code can still compile, but the compiler warns about a suspicious, unsafe, or potentially error-prone construct. Warnings do not necessarily cause the command to fail unless `-Werror` is enabled or the build tool is configured to treat warnings as errors.
- **Runtime error/exception:** the code has compiled and the program starts running, but an issue occurs during execution, such as `NullPointerException`, `ArithmeticException`, or `FileNotFoundException`.

For example, assigning a string to an `int` variable is a type error and is caught at compile time. Calling a method on a reference that is currently `null` typically only raises a `NullPointerException` when that statement is executed.

| Phase | Example | Tool / Detection Point |
|---|---|---|
| Compilation | Missing `;`, wrong type, symbol not found | `javac` |
| Startup / Class loading | Missing class at runtime, incompatible class version | Java launcher / JVM |
| Execution | `NullPointerException`, I/O error, logic error | JVM and application |

Not every message containing “Java error” is a compilation error. For instance, `ClassNotFoundException` can occur at runtime due to a missing dependency on the classpath, whereas `package ... does not exist` is typically a compilation error when the compiler cannot find the required package.

## 2. Reading `javac` Error Messages

A diagnostic typically provides:

1. Source file name.
2. Line number and possibly column position.
3. The offending source code line.
4. A `^` caret pointing to the position where the compiler detected the problem.
5. The diagnostic kind and explanatory message.

Illustrative example:

~~~text
src/Main.java:4: error: incompatible types: String cannot be converted to int
        int age = "twenty";
                  ^
1 error
~~~

How to read it:

- `src/Main.java:4` indicates the file and line with the problem.
- `error` indicates this is an error that caused compilation to fail.
- `incompatible types` indicates that the two data types are incompatible.
- `String cannot be converted to int` states the invalid conversion direction.
- The `^` marker highlights the expression the compiler is pointing to.

Exact wording, line wrapping, and the position of the `^` marker may vary across JDK versions. Rely on the diagnostic content and the actual source code rather than depending strictly on a fixed message string.

### In What Order Should You Read Errors?

- Read the first error in a file you wrote or a file directly related to the change you just made.
- Inspect the indicated line and a few lines before it; the error marker may appear where the compiler noticed the problem, while the real cause may be in an earlier declaration.
- Check symbol names, data types, method signatures, and packages.
- Fix one root cause and rerun the compiler.
- Only address subsequent errors after the first error has been resolved.

A missing curly brace or a malformed declaration at the top of a file can cause the compiler to misparse many lines that follow. When there are dozens of consecutive diagnostics, look for the first syntax or declaration error rather than fixing the last messages one by one.

## 3. Common Categories of Compilation Errors

### 3.1. Syntax Errors

Syntax errors occur when source code does not conform to Java grammar. Common causes include:

- Missing semicolon `;`.
- Missing or extra braces/parentheses/brackets `{}`, `()`, or `[]`.
- Misplaced `else`, `catch`, or `finally`.
- Malformed class, method, or statement declarations.
- Using keywords in the wrong context.

Incorrect example:

~~~java
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello")
    }
}
~~~

The `println` line is missing `;`. Fixed:

~~~java
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
~~~

Compile and run:

~~~text
javac Main.java
java Main
~~~

Stdout:

~~~text
Hello
~~~

When encountering `';' expected`, `')' expected`, `illegal start of expression`, or similar messages, check the structure of the current statement and the brackets/braces on the immediately preceding lines. Do not assume that the `^` marker always points to the exact character that needs to be inserted.

### 3.2. Symbol Not Found — `cannot find symbol`

The compiler cannot find a variable, method, class, or field name referenced by the code.

Incorrect example:

~~~java
public class Main {
    public static void main(String[] args) {
        System.out.println(mesage);
    }
}
~~~

The declared or intended variable name is `message`, but the print line writes `mesage`. The compiler cannot find that symbol.

Fixed:

~~~java
public class Main {
    public static void main(String[] args) {
        String message = "Hello";
        System.out.println(message);
    }
}
~~~

Other causes:

- Variable has not been declared or is out of scope.
- Incorrect capitalization; Java identifiers are case-sensitive.
- Misspelled method or field name.
- Missing class import.
- Class is not on the source path/classpath/module path.
- Using an API that does not exist in the target Java version.
- An earlier declaration failed, preventing the compiler from recognizing symbols later on.

When reading `cannot find symbol`, pay attention to the `symbol:` and `location:` parts of the diagnostic if present. They tell you what kind of element the compiler is looking for and in which class/scope.

### 3.3. Type Mismatch — `incompatible types`

Java is a statically typed language. The compiler checks the types of expressions and requires them to match where they are used.

Incorrect example:

~~~java
public class Main {
    public static void main(String[] args) {
        int quantity = "five";
    }
}
~~~

`"five"` has type `String`, whereas `quantity` has type `int`.

There are two ways to fix this depending on intent:

~~~java
int quantity = 5;
~~~

Or:

~~~java
String quantity = "five";
~~~

Do not cast just to silence an error message. Only use a cast when the conversion is meaningful and valid. For example, casting from `Object` to a specific type can cause a `ClassCastException` at runtime if the actual object is not of that type.

### 3.4. Wrong Method Signature or Argument Count

The compiler reports messages such as `method ... cannot be applied to given types` when it cannot find an overload matching the number, order, or types of arguments.

Example:

~~~java
public class Main {
    static void greet(String name, int times) {
        System.out.println(name + " " + times);
    }

    public static void main(String[] args) {
        greet("Lan");
    }
}
~~~

The method requires two parameters, but the call passes only one. Fix by passing all required arguments:

~~~java
greet("Lan", 2);
~~~

When calling a method, check:

- Method name and the class containing the method.
- Number of parameters.
- Order and type of each argument.
- Whether the method is `static` or requires an object instance to call.
- Access permissions and generic types if overloads exist.

You cannot pass `null` to primitive types. For example, `int` does not accept `null`; `Integer` is a reference type and can accept `null`, though you must handle the possibility of null when using it.

### 3.5. Access Errors — `has private access` or `... is not public`

A member may exist yet be inaccessible from the call site due to access modifier rules.

Example:

~~~java
class Account {
    private int balance = 100;
}

public class Main {
    public static void main(String[] args) {
        Account account = new Account();
        System.out.println(account.balance);
    }
}
~~~

`balance` is `private`, so `Main` cannot access it directly. You can provide a public method to read the value:

~~~java
class Account {
    private int balance = 100;

    public int getBalance() {
        return balance;
    }
}

public class Main {
    public static void main(String[] args) {
        Account account = new Account();
        System.out.println(account.getBalance());
    }
}
~~~

Stdout:

~~~text
100
~~~

When an error involves access modifiers, check `private`, package-private, `protected`, and `public` visibility, package relationships, and inheritance relationships. In modular applications, also check whether the module `exports` the package being accessed.

### 3.6. Calling Instance Members from a Static Context

The traditional `main` method is `static`, so it has no `this` and cannot directly access instance members without an object instance.

Incorrect example:

~~~java
public class Main {
    private String name = "Java";

    public static void main(String[] args) {
        System.out.println(name);
    }
}
~~~

`name` belongs to a `Main` object, whereas `main` belongs to the class. Create an object first and then access the member:

~~~java
public class Main {
    private String name = "Java";

    public static void main(String[] args) {
        Main app = new Main();
        System.out.println(app.name);
    }
}
~~~

Or if the data is genuinely shared at the class level, consider declaring it `static`. Do not turn every field into `static` just to quiet the compiler; choose state scope according to your object model.

### 3.7. Unhandled Checked Exceptions

Some exceptions are checked exceptions. A method that can throw a checked exception must declare `throws` or handle it with `try-catch` according to Java rules.

Incorrect example:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class Main {
    public static void main(String[] args) {
        String text = Files.readString(Path.of("data.txt"));
        System.out.println(text);
    }
}
~~~

`Files.readString` can throw `IOException`. Fix by handling or declaring the exception:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class Main {
    public static void main(String[] args) throws IOException {
        String text = Files.readString(Path.of("data.txt"));
        System.out.println(text);
    }
}
~~~

Or use `try-catch` if the application needs to handle it locally. Declaring `throws` does not make an I/O error disappear; it delegates handling responsibility to the caller. Choose the approach based on the application's goals.

### 3.8. File Name and Public Class Name Mismatch

A source file can have only one public top-level class matching the file name. For example, if you declare:

~~~java
public class Customer {
}
~~~

then the file must be named `Customer.java`. If the public class is named `Customer` while the file is `Main.java`, the compiler reports a file name mismatch error.

Check that:

- The file name and public class name match, including letter case on case-sensitive systems.
- Each public top-level class is in a file with the matching name.
- The package declaration matches the project structure and build setup.
- There are no two classes with the same fully qualified name in the same compilation unit/run.

### 3.9. Package and Import Errors

The message `package ... does not exist` usually indicates that the compiler cannot find the required package or dependency on the source path, classpath, or module path.

For example, the code has:

~~~java
import com.example.util.Texts;
~~~

but the directory containing `Texts.class` or `Texts.java` is not on the path the compiler is searching.

How to resolve:

- Check the `package` statement at the top of the source file.
- Ensure the directory structure reflects the package name.
- Add the root directory containing the package to the classpath/source path.
- Check whether the dependency JAR has been added to the classpath.
- If using modules, check the module path and `requires` declarations.

`import` does not download libraries from the Internet. It only lets source code use shorter type names; the compiler still needs to locate the class definition in a configured location.

### 3.10. Generics and Type Inference Errors

Generics allow the compiler to check element types of collections and generic APIs. An incompatible type declaration can cause `incompatible types`, `no suitable method found`, or inference errors.

Example:

~~~java
import java.util.ArrayList;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        names.add(10);
    }
}
~~~

`List<String>` only accepts `String` values, so `names.add(10)` is invalid.

Fix by adding a string:

~~~java
names.add("10");
~~~

If you need to store multiple data types, choose an appropriate common type or model explicit classes/interfaces. Avoid using raw types like `List` to bypass type checking; that loses part of the safety benefit of generics and typically produces warnings.

### 3.11. Lambda and Method Reference Errors

A lambda requires a suitable target type, usually a functional interface. If the compiler cannot infer the type or the signature does not match, it will report an error about types, overloads, or the lambda expression.

Valid example:

~~~java
import java.util.function.Predicate;

public class Main {
    public static void main(String[] args) {
        Predicate<String> nonEmpty = text -> !text.isEmpty();
        System.out.println(nonEmpty.test("Java"));
    }
}
~~~

Stdout:

~~~text
true
~~~

If a lambda expression does not have a clear target type, declare the variable with a specific functional interface or provide parameter types where needed. When using a method reference, verify the parameter count and types accepted by the referenced method.

### 3.12. Duplicate Declarations

The compiler does not allow declaring two local variables with the same name in the same scope, two methods with the same signature in the same class, or two classes with the same fully qualified name in the same source set.

Example:

~~~java
public class Main {
    public static void main(String[] args) {
        int count = 1;
        int count = 2;
        System.out.println(count);
    }
}
~~~

Fix by declaring once and reassigning if needed:

~~~java
int count = 1;
count = 2;
~~~

For methods, Java does not distinguish overloads based solely on return type. Two methods with the same name and parameter type list cannot be distinguished just because one returns `int` and the other returns `String`.

## 4. Errors Caused by Java Version and APIs

Source code may be valid on a newer JDK but fail to compile when the project targets an older Java version. The cause is usually using language syntax or APIs not yet available in the target version.

For example, if the project must run on Java 17, compile with `--release 17`:

~~~text
javac --release 17 -d out src/Main.java
~~~

`--release` configures the language level, class file version, and corresponding public platform API set. This is the proper way to verify compatibility with a target Java version when using a newer JDK.

Do not rely solely on `-source 17 -target 17` when you need to control the target platform APIs. Those two options control syntax level and class file format, but they do not automatically restrict platform APIs in the same way `--release` does.

Related messages:

- `... is not supported in -source ...`: the syntax is not supported at the selected language level.
- `cannot find symbol` for a newer API: the API may not exist in the target release or the dependency was not found.
- `invalid source release`: the current JDK compiler does not support the requested source/release level.
- `class file has wrong version`: the compiler is reading a class file generated by a newer version than it supports.

Check the compiler currently in use:

~~~text
java --version
javac --version
~~~

If your IDE uses a different JDK than your terminal, check the Project SDK, Java compiler, and build tool settings. The version shown in the terminal does not guarantee the IDE is using the same compiler.

## 5. Classpath, Module Path, and Dependency Errors at Compile Time

The compiler must be able to locate the classes referenced by your source code. For classpath-based applications, use `-cp` or `--class-path`:

~~~text
javac -cp "lib/*" -d out src/Main.java
~~~

On Windows, the separator between multiple classpath entries is `;`; on macOS/Linux, it is `:`. The `*` wildcard in the example adds the JARs in the `lib` directory to the classpath.

For modular applications, use the module path:

~~~text
javac --module-path mods -d out src/module-info.java src/com/example/Main.java
~~~

The exact syntax depends on the module layout and source file locations. Used modules must be present on the module path, and the module descriptor must declare the required relationships, such as `requires`. Packages that need to be accessed from other modules must be exported appropriately.

Distinguishing common situations:

| Diagnostic | Possible Cause | What to Check |
|---|---|---|
| `package ... does not exist` | Missing dependency or wrong classpath/source path | JARs, package directories, `-cp` |
| `module not found` | Module not on module path | `--module-path`, module name |
| `module ... does not read ...` | Missing readability relationship | `requires` or module configuration |
| `package ... is not visible` | Package not exported or not read | `exports`, module descriptor |
| `cannot access ...` | Incompatible class file, missing dependency, or access permissions | JDK version, classpath, modules |

A dependency may be present at runtime yet missing at compile time, or vice versa. Ensure that the classpath/module path used for `javac` and at runtime align with the same set of application dependencies.

## 6. Annotation Processing Errors

An annotation processor is a component that runs during compilation to read annotations and optionally generate additional source code or resources. Libraries such as MapStruct or certain code-generation tools may rely on annotation processing.

Common symptoms:

- The compiler reports missing expected types or methods because code generation has not run.
- Messages indicating an annotation processor could not be found.
- The processor emits an `error` diagnostic due to invalid annotation configuration or input.
- Generated code is missing from the output/source output directory.

Related options:

- `-processorpath`: specifies where to find annotation processors.
- `-processor`: specifies which processors to run.
- `-proc:none`: disables annotation processing.
- `-s`: specifies the directory where generated source files are placed.
- `-Akey=value`: passes an option to an annotation processor.

Example of disabling annotation processing to isolate an error independent of processors:

~~~text
javac -proc:none -d out src/Main.java
~~~

Only use `-proc:none` to isolate an issue when you know the project does not need code generation for that compilation. If the application depends on generated code, disabling processors can introduce additional `cannot find symbol` errors because the generated classes do not exist.

## 7. Warnings and Controlling Compilation Quality

Warnings indicate that the compiler detected a noteworthy construct, though compilation can still proceed. Common warnings include:

- Using deprecated APIs.
- Using raw types or unchecked conversions.
- Redundant casts.
- Serializable class issues.
- Resource or code constructs worth inspecting.

Enable warning categories with `-Xlint`:

~~~text
javac -Xlint:all -d out src/Main.java
~~~

You can enable a specific category, for example:

~~~text
javac -Xlint:deprecation -d out src/Main.java
javac -Xlint:unchecked -d out src/Main.java
~~~

Use `-Werror` to turn warnings into errors:

~~~text
javac -Xlint:all -Werror -d out src/Main.java
~~~

`-Werror` is useful in CI to keep code quality consistent, but it should only be enabled after the project has addressed existing warnings. Enabling it immediately on a codebase with many legacy warnings can break builds even when new changes introduce no issues.

Do not broadly suppress warnings just to get a green build. If suppression is necessary, apply `@SuppressWarnings` to the smallest possible scope and document the reason when the warning carries real risk.

## 8. Complete Compilation Workflow Example with Java 17+

Create the directory structure:

~~~text
project/
  src/
    Main.java
  out/
~~~

Contents of `src/Main.java`:

~~~java
public class Main {
    public static void main(String[] args) {
        int first = 10;
        int second = 20;
        System.out.println("Total: " + (first + second));
    }
}
~~~

Compile:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/Main.java
~~~

If the compiler reports no errors, run:

~~~text
java -cp out Main
~~~

Stdout:

~~~text
Total: 30
~~~

Explanation:

- `--release 17` checks source code against Java 17.
- `-encoding UTF-8` specifies the source file encoding.
- `-Xlint:all` enables warning categories.
- `-d out` sets the output directory for class files.
- `-cp out` specifies the directory to search for classes at runtime.

In PowerShell or Command Prompt, this example uses relative paths and does not require a multi-entry classpath separator. When adding libraries, use the proper separator for your operating system.

## 9. Systematic Process for Resolving Compilation Errors

When `javac` fails, follow this process:

1. **Verify the compiler:** run `javac --version` and check the executable path.
2. **Reproduce with an explicit command:** note the full command line, working directory, classpath/module path, and target version.
3. **Read the first meaningful diagnostic:** identify the file, line, symbol, type, or package mentioned.
4. **Expand context:** read the offending line along with related declarations, imports, and method signatures.
5. **Identify the root cause:** syntax, scope, type, access, dependency, module, or annotation processing.
6. **Fix one group of related causes:** avoid changing many unrelated things at once.
7. **Recompile:** confirm the error is gone and inspect any new diagnostics.
8. **Run appropriate tests:** successful compilation does not prove logic is correct; run the program and tests to verify behavior.
9. **Record the build configuration:** store the JDK/release, dependencies, and required options in the build script so others can reproduce it.

If a build tool such as Maven or Gradle reports a failure, look for the first section containing `Compilation failure`, `Compilation error`, or diagnostics from `javac`. Dependency download failures, plugin configuration issues, or test failures may occur in other phases and need to be handled separately.

## 10. Useful `javac` Options for Diagnostics

| Option | Purpose |
|---|---|
| `-Xdiags:verbose` | Displays more detailed diagnostics where supported by the compiler |
| `-Xlint:all` | Enables many warning categories |
| `-Werror` | Treats warnings as compilation errors |
| `--release 17` | Compiles for the target Java version |
| `-encoding UTF-8` | Specifies source file encoding |
| `-d out` | Specifies the output directory for class files |
| `-cp` / `--class-path` | Specifies where to find classes and dependencies |
| `--module-path` | Specifies where to find modules |
| `-sourcepath` | Specifies where to find additional referenced source files |
| `-proc:none` | Disables annotation processing |
| `-verbose` | Prints additional information about compiler activity |

Example enabling verbose diagnostics and warnings:

~~~text
javac -Xdiags:verbose -Xlint:all -d out src/Main.java
~~~

Not every option applies to every JDK version. If the compiler reports an invalid option, consult `javac --help` and the documentation for the exact JDK installed. Options starting with `-X` may be advanced, version-dependent options.

## 11. Common Errors and Quick Isolation

### `';' expected` or `')' expected`

**Cause:** missing statement terminator or closing bracket/parenthesis; sometimes the actual mistake is on a preceding line.

**Fix:** check the current statement and the nearest enclosing block's brackets/parentheses. Recompile after fixing one root syntax error.

### `cannot find symbol`

**Cause:** misspelled name, undeclared identifier, wrong scope, missing import, or missing dependency.

**Fix:** check `symbol` and `location`, then verify the declaration and class lookup paths.

### `incompatible types`

**Cause:** expression type is incompatible with the variable, parameter, or return type.

**Fix:** fix the type at the source or perform an intentional conversion. Do not cast arbitrarily to hide the error.

### `method ... cannot be applied to given types`

**Cause:** wrong number, order, or types of arguments; no matching overload.

**Fix:** compare the method signature with the call site, and check generics and inferred types.

### `package ... does not exist`

**Cause:** missing library, wrong classpath/source path, or package not provided by a module.

**Fix:** verify the dependency is on the compile classpath/module path; `import` does not download libraries automatically.

### `class X is public, should be declared in a file named X.java`

**Cause:** file name does not match the public top-level class name.

**Fix:** rename the file or class so they match.

### `unreported exception ...; must be caught or declared to be thrown`

**Cause:** checked exception is neither caught nor declared.

**Fix:** add an appropriate `try-catch` block or declare `throws` on the method and let the caller handle it.

### `invalid source release` or unsupported syntax

**Cause:** JDK compiler is too old or the source/release level is incompatible.

**Fix:** use a JDK that supports the target version, or lower `--release` if the project allows it.

### `warning: ...` yet the build still fails

**Cause:** the build enables `-Werror` or a plugin configuration treats warnings as errors.

**Fix:** identify which warning is being elevated to an error. Fix the underlying cause or adjust the warning policy intentionally; do not suppress warnings blindly.

## 12. Checklist Before Concluding an Error Is Fixed

- [ ] Using the exact JDK and `javac` required by the project.
- [ ] File name, public class name, and package match.
- [ ] No remaining syntax errors or missing brackets/parentheses.
- [ ] Variables, classes, methods, and fields are declared in the proper scope.
- [ ] Argument types, return types, and generics match.
- [ ] Access permissions and inheritance relationships are correct.
- [ ] Checked exceptions are caught or declared.
- [ ] Classpath/module path contains required dependencies.
- [ ] Annotation processors are configured if the project requires code generation.
- [ ] `--release` matches the target deployment Java version.
- [ ] Warnings are reviewed according to the build policy.
- [ ] Compilation succeeds and produces class files in the expected directory.
- [ ] The program or tests run successfully after compilation.

Compilation errors are the compiler's feedback about rules that the source code does not yet satisfy. Reading diagnostics accurately, distinguishing syntax errors from type errors and dependency errors, and reproducing the issue with an explicit `javac` command will help you locate the true cause. Once compilation succeeds, continue running tests to verify the program's behavior.