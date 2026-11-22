# `throws` Syntax on Methods and Constructors in Java

The **`throws`** clause appears in the declaration of a **method** or **constructor** to indicate the exception types that a call may propagate to the caller. This is part of the API contract and is especially important for **checked exceptions**: the compiler forces the caller to catch the exception or continue declaring an appropriate exception.

Three concepts should be distinguished right from the start:

- `new IOException("...")` **creates an exception object**.
- `throw new IOException("...");` **throws** the object, causing the current execution flow to terminate abruptly.
- `void read() throws IOException { ... }` **declares** the possibility that the method may let an `IOException` escape. Merely declaring `throws` does not create, throw, or handle an exception.

This lesson guides you on how to write the position, list, and exception types in the `throws` clause of methods and constructors on Java 17+, along with runnable examples, related rules when calling and inheriting, and common compilation errors.

## 1. `throws` Syntax on Methods

The general form of a method declaration with a body:

~~~java
[modifiers] ReturnType methodName(ParameterType parameter, ...)
        throws ExceptionType1, ExceptionType2 {
    // Method body
}
~~~

In the syntax above:

- `[modifiers]` represents optional keywords such as `public`, `protected`, `private`, `static`, or `final`, depending on the context. Square brackets are only used to annotate the syntax pattern; **do not type them literally** in Java.
- `ReturnType` is the return type, or `void`.
- `methodName(...)` is the name and parameter list.
- `throws` stands **after the closing `)` of the parameter list**, before the opening `{` of the body.
- `ExceptionType1, ExceptionType2` are exception types separated by commas, not by `|`, `+`, or `;`.
- If there are no exceptions to declare, **omit `throws` completely**; do not write `throws` with an empty list.

Single-exception example:

~~~java
import java.io.IOException;

// Placed inside a class.
public static String read(String filename) throws IOException {
    return java.nio.file.Files.readString(java.nio.file.Path.of(filename));
}
~~~

Multiple-exception example:

~~~java
import java.io.IOException;
import java.sql.SQLException;

// Code illustrating the signature and corresponding throw, placed inside a class.
static void execute(boolean databaseError) throws IOException, SQLException {
    if (databaseError) {
        throw new SQLException("Database unavailable");
    }
    throw new IOException("Input unavailable");
}
~~~

`throws IOException, SQLException` creates a **list of exception types in the signature**; it does not mean that every call throws two errors or that Java will automatically generate them one after another. When the method is called, only the actual execution path determines which exception occurs.

Interface/abstract method declarations without a body also place `throws` after the parameters, then end with a `;`:

~~~java
import java.io.IOException;

interface DocumentReader {
    String read() throws IOException;
}

abstract class AbstractImporter {
    public abstract void importData() throws IOException;
}
~~~

`throws` belongs to the **method declaration**, not as a separate part of a `try` block or a statement that can be inserted into the middle of the body.

### Valid and Invalid Ways to Write It

| Syntax | Valid? | Explanation |
| --- | --- | --- |
| `void work() throws IOException { ... }` | Yes | `throws` after the parameter list. |
| `void work() throws IOException, SQLException { ... }` | Yes | List of multiple types, separated by commas. |
| `void work() { ... }` | Yes | Writing `throws` is not required if there is nothing to declare. |
| `void work() throws { ... }` | No | The list after `throws` cannot be empty. |
| `void work() throws IOException | SQLException { ... }` | No | `|` belongs to multi-catch syntax, not used in `throws`. |
| `throws IOException void work() { ... }` | No | `throws` is placed in the wrong position. |

In the table, `...` is just shorthand notation referring to a valid body, **not a standalone compilable snippet**.

## 2. `throws` Syntax on Constructors

A constructor can also throw checked exceptions when object initialization fails—for example, when a file cannot be opened, configuration cannot be loaded, or calling a superclass constructor fails.

General form:

~~~java
[modifiers] ClassName(ParameterType parameter, ...)
        throws ExceptionType1, ExceptionType2 {
    // Object initialization
}
~~~

Points specific to constructors:

1. The constructor name must match the class name and has **no return type** — do not write `void` or an object type before the constructor name.
2. `throws` stands after the parameter list and before `{`, in the same position as on a method.
3. A constructor can declare multiple checked exceptions using a comma-separated list.
4. Constructors are not inherited and cannot be `override`n like methods. However, a subclass constructor **calls a superclass constructor**, so it must obey the checked exception rules of that call.
5. When a `new SomeClass(...)` expression invokes a constructor that declares checked exceptions, the caller must catch or declare them, just like calling a method with `throws`.

Simple syntax example:

~~~java
import java.io.IOException;

class ResourceSession {
    ResourceSession(boolean available) throws IOException {
        if (!available) {
            throw new IOException("Cannot open resource");
        }
    }
}
~~~

`new ResourceSession(false)` can throw `IOException`, so the call site must have an appropriate `try/catch` or declare `throws IOException`. The fact that `new` is an object creation operation does not exempt it from exception checking rules.

### Noticeable Difference Between a Method and a Constructor

~~~java
// Illustrating two declarations placed in the same class named Example.
Example() throws java.io.IOException {
    // Constructor: no return type.
}

void run() throws java.io.IOException {
    // Method: has return type void.
}
~~~

If you write `void Example() throws IOException` inside class `Example`, this is a **method named Example**, not a constructor. You should check the return type part when a declaration that looks like a constructor behaves differently from expected.

## 3. Complete Example: `throws` on Methods and Constructors

Create the file `ThrowsSyntaxDemo.java`:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class ThrowsSyntaxDemo {
    static class Configuration {
        private final String content;

        Configuration(Path path) throws IOException {
            content = Files.readString(path);
        }

        String content() {
            return content;
        }
    }

    static Configuration load(Path path) throws IOException {
        return new Configuration(path);
    }

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("throws-demo-", ".txt");
        try {
            Files.writeString(path, "Xin chào");
            Configuration config = load(path);
            System.out.println("Nội dung: " + config.content());
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 ThrowsSyntaxDemo.java
java ThrowsSyntaxDemo
~~~

Exact stdout when creating/writing/reading/deleting the temporary file succeeds:

~~~text
Nội dung: Xin chào
~~~

Explanation:

1. `Files.createTempFile` creates a temporary file; `Files.writeString` writes data. The I/O APIs can throw `IOException`, so `main` declares `throws IOException`.
2. `Configuration(Path path) throws IOException` declares a checked exception because the `Files.readString(path)` call may fail.
3. `load(Path path) throws IOException` calls `new Configuration(path)`. It does not catch `IOException`, so it **declares it to pass responsibility to the caller**.
4. `main` calls `load` and continues propagating `IOException` outward if a failure occurs; `main` has no `catch` for this error type. Therefore, if I/O actually fails and is not caught at another layer, the program typically terminates abruptly with a stack trace.
5. `content()` only returns the stored data; it does not declare `throws` because the current implementation does not need to let any checked exception escape.
6. The `finally` block calls `Files.deleteIfExists` to attempt deleting the temporary file. This cleanup operation itself can also throw `IOException`. If both `try` and `finally` throw errors, the error from `finally` can mask the earlier error; using `try-with-resources` when managing `AutoCloseable` resources is a common way to preserve suppressed exceptions.

Using a temporary file shows that `throws` is a **commitment about the API's possibility of failure**, not a tool for creating errors. In the success case, the program prints the result normally without any exception being thrown.

## 4. What Must the Caller of a Method or Constructor with `throws` Do?

For **checked exceptions**, the caller has two common options.

### 4.1. Catch Where It Can Be Handled: `try/catch`

~~~java
import java.io.IOException;

// Placed in a class that already has Configuration and a logError method.
static void start(Path path) {
    try {
        Configuration config = new Configuration(path);
        System.out.println(config.content());
    } catch (IOException ex) {
        logError(ex);
    }
}
~~~

This is an **illustrative snippet**, depending on external `Path`, `Configuration`, and `logError` declarations. Because it catches `IOException`, `start` is not required to declare `throws IOException` just for this call, provided no other checked exception path escapes.

The catch site should perform a useful handling action: report the error to the user, provide a valid fallback path, add context, or intentionally transfer responsibility. You should not do `catch (IOException ignored) { }` and then behave as if the operation succeeded.

### 4.2. Continue Declaring `throws`

~~~java
import java.io.IOException;
import java.nio.file.Path;

// Placed in a class that has constructor Configuration(Path) throws IOException.
static Configuration start(Path path) throws IOException {
    return new Configuration(path);
}
~~~

Here `start` does not handle it; `IOException` can propagate to the next caller. If multiple layers all have `throws IOException`, the error travels back up the call chain until it encounters a matching `catch` or no catcher remains.

`throws IOException` can cover checked subclasses such as `FileNotFoundException` or `NoSuchFileException`; it is not necessary to list each subclass individually. However, `throws IOException` **does not automatically cover `SQLException`**: the two types belong to different branches. If both can escape, declare both or an appropriate supertype while considering API clarity.

### 4.3. `main` Can Also Use `throws`

The signature `public static void main(String[] args) throws IOException` is valid. However, it **does not catch** exceptions at the application boundary. If an error actually escapes from `main`, it can lead to abrupt termination and a stack trace according to the thread's default handler.

If you want a friendly message and a controlled exit code, catch the error at an appropriate point in the application. Writing `throws` only makes the responsibility of propagating up the call stack explicit in the language.

## 5. Constructor Chaining: `this(...)` and `super(...)`

In a constructor, Java provides a mechanism to call another constructor in the same class using `this(...)`, or to call a superclass constructor using `super(...)`. That call may throw checked exceptions, so the declaring constructor must also satisfy **catch-or-declare**. On Java 17, this explicit constructor invocation must be the first statement in the constructor; you cannot wrap `super(...)` in a `try/catch` in the constructor body to handle it in place in the usual way.

### Complete Example: Subclass Constructor Declaring `throws`

Create the file `ConstructorThrowsDemo.java`:

~~~java
import java.io.IOException;

class Resource {
    Resource(boolean available) throws IOException {
        if (!available) {
            throw new IOException("không có tài nguyên");
        }
    }
}

class ManagedResource extends Resource {
    ManagedResource(boolean available) throws IOException {
        super(available);
    }
}

public class ConstructorThrowsDemo {
    public static void main(String[] args) {
        try {
            new ManagedResource(false);
        } catch (IOException ex) {
            System.out.println("Không khởi tạo: " + ex.getMessage());
        }

        try {
            new ManagedResource(true);
            System.out.println("Khởi tạo thành công");
        } catch (IOException ex) {
            System.out.println("Không khởi tạo: " + ex.getMessage());
        }
    }
}
~~~

Run command:

~~~bash
javac -encoding UTF-8 ConstructorThrowsDemo.java
java ConstructorThrowsDemo
~~~

Exact stdout:

~~~text
Không khởi tạo: không có tài nguyên
Khởi tạo thành công
~~~

Analysis:

- The `Resource(boolean)` constructor declares `throws IOException`. If `available == false`, it executes `throw new IOException(...)`.
- The `ManagedResource(boolean)` constructor calls `super(available)`. Because the call to the superclass constructor can throw `IOException`, the subclass constructor declares `throws IOException`.
- When `new ManagedResource(false)` fails, object initialization does not complete normally; the `catch` block in `main` handles `IOException`.
- With `true`, no exception is thrown; initialization finishes normally.

If you remove `throws IOException` from `ManagedResource(boolean)` while still calling `super(available)`, the compiler reports an uncaught or undeclared checked exception error.

A rule worth remembering: **constructors do not participate in overriding**. The rule "a subclass constructor may only declare narrower exceptions than the superclass constructor" does not apply. A subclass constructor can declare checked types appropriate to its own operations, provided any required calls are handled according to Java's rules.

### Default Constructor and Implicit `super()` Call

If a class declares no constructors, the compiler provides a **default constructor** according to Java's rules. For a subclass, a constructor must call a superclass constructor. When a constructor does not specify `this(...)` or `super(...)`, Java 17 attempts to call `super()` implicitly.

If the superclass's no-argument constructor declares a checked exception, a subclass cannot rely on the default constructor to "automatically add `throws`". You must declare an appropriate constructor yourself and specify `throws`:

~~~java
import java.io.IOException;

class Parent {
    Parent() throws IOException {
        throw new IOException("khởi tạo Parent thất bại");
    }
}

class Child extends Parent {
    Child() throws IOException {
        super();
    }
}
~~~

This is an **illustrative snippet consisting of two classes**, without `main`. If you omit `Child`'s constructor completely, the generated default constructor does not declare `throws IOException`, so the program may fail to compile due to the implicit `super()` call.

With `this(...)`, the same reasoning applies: the delegating constructor must declare any checked exceptions that may propagate from the target constructor. If initialization fails at one link in the chain, the initialization chain also terminates abruptly.

## 6. How Do Checked and Unchecked Exceptions Affect `throws`?

The most important static rule:

- **Checked exceptions** are `Throwable` types that are not in the `RuntimeException` or `Error` branches. If a method/constructor can let them escape, the compiler normally requires declaring the appropriate checked type or handling it with `catch`.
- **Unchecked exceptions** belong to the `RuntimeException` or `Error` branches; the compiler does not require declaring them with `throws`.
- Both categories **can** be listed in `throws`, though listing unchecked ones usually serves as API documentation rather than a catching obligation for the caller.

Example:

~~~java
// Illustrative code inside a class.
static int parse(String raw) {
    return Integer.parseInt(raw); // May throw NumberFormatException, unchecked.
}

static int parseWithDeclaration(String raw)
        throws NumberFormatException {
    return Integer.parseInt(raw);
}
~~~

Both signatures are valid. Calling `parseWithDeclaration` **is not required by the compiler** to have `catch (NumberFormatException)` just because it has a `throws` clause, since this is an unchecked exception.

Conversely:

~~~java
import java.io.IOException;

// Illustrative snippet placed inside a class.
static void checkedFailure() throws IOException {
    throw new IOException("không đọc được");
}
~~~

A method that calls `checkedFailure()` without handling `IOException` or declaring it accordingly will fail to compile.

**Important:** the checked/unchecked classification is a property of the exception type, not of the `throws` keyword. There is no such thing as "adding `throws` to a runtime type to turn it into a checked exception."

## 7. Declaring Multiple Exception Types and Supertypes

Syntax for declaring multiple types:

~~~java
import java.io.IOException;
import java.sql.SQLException;

// Illustrative code belonging to a class.
static void synchronize(boolean dbMode) throws IOException, SQLException {
    if (dbMode) {
        throw new SQLException("DB error");
    }
    throw new IOException("Network error");
}
~~~

The caller needs to cover both situations if they can propagate out:

~~~java
// Illustrative snippet inside a method that has synchronize(...) in class scope.
try {
    synchronize(true);
} catch (IOException ex) {
    System.out.println("I/O: " + ex.getMessage());
} catch (SQLException ex) {
    System.out.println("SQL: " + ex.getMessage());
}
~~~

The short snippets in this section need the corresponding `import` statements and must be placed inside a class/method; they are used to illustrate signatures, not standalone Java files.

You can also write `throws Exception`, because `Exception` is a supertype of both `IOException` and `SQLException`. This syntax is valid, but it usually reduces the precision of the API contract: callers find it harder to determine which errors are recoverable and easily end up catching too broadly.

For the same exception family, `throws IOException` already includes its subclasses, so you normally do not need to write `throws IOException, FileNotFoundException` at the same time. Declaring it that way is allowed but redundant in coverage; you should prefer a sufficiently specific type or a meaningful supertype matching the API's abstraction level.

When declaring a stable API, note that **adding a new checked exception to `throws`** can cause client source code to stop compiling if they have not caught or declared it.

## 8. `throws` When Overriding Methods and Implementing Interfaces

Unlike constructors, **overriding methods** must obey the checked exception contract of the superclass or interface method.

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

interface Reader {
    String read() throws IOException;
}

class FileReaderImpl implements Reader {
    @Override
    public String read() throws FileNotFoundException {
        return "OK";
    }
}

class MemoryReaderImpl implements Reader {
    @Override
    public String read() {
        return "in-memory";
    }
}
~~~

Both implementing methods are valid:

- `FileReaderImpl.read` declares `FileNotFoundException`, which is a subclass of `IOException`.
- `MemoryReaderImpl.read` declares no checked exceptions; an override is allowed to narrow or remove checked exceptions.
- If you change an override's declaration to `throws Exception` or `throws SQLException`, the code is invalid against the contract that only allows `IOException` on the `Reader` interface.
- An overriding method can still declare unchecked exceptions without being constrained by the superclass method's checked exception list.

A practical point: the static reference type of the variable determines **the contract the compiler uses at the call site**. Even though the actual object is `new MemoryReaderImpl()`, which throws no checked exception, `Reader r = new MemoryReaderImpl(); r.read();` is still checked based on the signature `Reader.read() throws IOException`.

Example:

~~~java
// Illustrative snippet placed in a method with IOException imported.
Reader reader = new MemoryReaderImpl();
try {
    System.out.println(reader.read());
} catch (IOException ex) {
    System.out.println("Đọc thất bại");
}
~~~

If you change the variable's type to `MemoryReaderImpl`, the `reader.read()` call has a signature that declares no checked exceptions, so that call alone no longer creates an obligation to handle `IOException`.

## 9. `throws` Position with Generic Methods, Varargs, and Abstract Methods

The `throws` clause always comes **after the entire parameter list**, even when the method has type parameters, varargs, or is declared in an interface:

~~~java
import java.io.IOException;

class SyntaxExamples {
    public <T> T convert(T input) throws IOException {
        return input;
    }

    public void readAll(String... paths) throws IOException {
        for (String path : paths) {
            java.nio.file.Files.readString(java.nio.file.Path.of(path));
        }
    }
}

interface Operation {
    void run() throws IOException;
}
~~~

Points easily confused:

- `<T>` declares the method's type parameter. It stands before the return type; `throws` still stands after `)`.
- `String... paths` is varargs, which still sits **inside** the parameter list.
- A signature in an interface ends with `;`; a method with a body ends the `throws` declaration and is followed by `{`.
- `throws` is not placed inside the parameter parentheses, not inside an exception class name, and not used like an annotation.

Java also supports type variables in `throws` according to Java's type bounds; this is an advanced case. When writing typical APIs, declaring specific and meaningful exception types remains easier to understand.

## 10. Important Limitations and Notes

### 10.1. `throws` Does Not Require an Exception to Actually Be Thrown

You can declare:

~~~java
// Illustrative code inside a class.
static String version() throws java.io.IOException {
    return "1.0";
}
~~~

Even though the current body does not throw `IOException`, the syntax is still valid. However, callers evaluated against that signature still have the compile-time obligation to catch or declare the checked exception. You should only advertise exceptions that are meaningful for the contract or intended extensibility; arbitrary broad `throws` clauses make APIs inconvenient.

### 10.2. `throws` Cannot Be Placed in a Statement Block

Wrong:

~~~java
// Illustrative code that does not compile.
static void work() {
    throws java.io.IOException;
}
~~~

Right: place `throws IOException` on the method or constructor declaration. Inside the body, if you need to throw, use `throw new IOException(...);`.

### 10.3. `throws` Does Not Handle Runtime Consequences

Even when a method declares `throws IOException`, execution only switches to the error path **if an exception is actually thrown** (by `throw` or by a called operation raising an error). If there is no matching `catch` along the call chain, the exception can escape the entry point and cause the thread to terminate abruptly.

`throws` also does not automatically log, roll back data, close resources, turn checked exceptions into unchecked ones, or generate user messages. Handling, cleanup, and recovery decisions belong to control-flow structures and design at each layer.

### 10.4. `finally` and Resources Still Need Proper Handling

When a method/constructor declares `throws`, resources opened before the failure point must be cleaned up safely; merely using `throws` does not release them.

In I/O, prefer `try-with-resources` to ensure `AutoCloseable` resources are closed and secondary error information is preserved via suppressed exceptions. For a partially constructed object when a constructor throws an exception, Java does not treat construction as having succeeded to return the object to the caller; the constructor must take responsibility for resources it allocated before throwing, because the caller has not yet received a complete reference to close.

### 10.5. Rules for Static Constructors, Field Initializers, and Initializer Blocks

There is no **static constructor** concept in Java. Static initializers do not have a separate parameter list/signature to attach `throws` to; the specific rules about checked exceptions in initializers cannot be bypassed by writing `throws` after `static { ... }`.

In instance initializers or field initializers, checked exceptions are subject to specific rules tied to the relevant constructors. You should not try to place `throws` at the position of a field or initializer block; consider designing it so operations that may fail are moved into an appropriate constructor or method and declare exceptions in the proper place.

## 11. Table of Common Syntax and Compilation Errors

| Issue | Why Is It an Error or Inconvenience? | How to Fix |
| --- | --- | --- |
| `void read() throw IOException` | Missing `s`: `throw` is a statement, not an exception list declaration. | Use `void read() throws IOException`. |
| `void read(throws IOException)` | `throws` is misplaced inside the parameter parentheses. | Place after `)`: `read() throws IOException`. |
| `throws IOException | SQLException` | Mistakenly used `|` from multi-catch. | Separate with commas. |
| Constructor declared as `void ClassName()` | Becomes a method, not a constructor. | Remove the return type. |
| Subclass constructor calls `super()` with checked exception without declaring it | The superclass constructor call can let a checked exception escape. | Declare appropriate `throws` on the subclass constructor or redesign initialization. |
| Method calls an API declaring `IOException` without catching/declaring | Compiler reports `unreported exception`. | Catch the right type where it can be handled, or add a reasonable `throws`. |
| Override adds `throws SQLException` when interface only has `IOException` | Violates override checked exception constraints. | Use a checked type within the parent contract or handle it locally. |
| Writing `throws Exception` everywhere | Obscures failure types, makes things hard for callers, and makes keeping the API stable difficult. | Use specific types matching the scope of responsibility. |
| Only writing `throws IOException` and expecting no resource cleanup needed | Declaration does not perform cleanup. | Use `try-with-resources`/`finally` appropriately. |
| Writing `throws RuntimeException` and thinking callers are forced to `catch` | Unchecked exceptions are not subject to the catch-or-declare requirement. | Understand exception categories properly; document important errors. |

## 12. Self-Check Questions

1. **Where does `throws` appear in a method signature?** — After the closing `)` of the parameter list, before the `{` body or the `;` of a bodyless declaration.
2. **Does a constructor have a return type?** — No. Declaring `void ClassName()` creates a method with that name, not a constructor.
3. **If `A()` declares `throws IOException`, what must `new A()` in a calling method do?** — Catch `IOException` or declare an appropriate checked type on the calling method, unless the context cannot throw it.
4. **Can you write `throws IOException, SQLException`?** — Yes. The list is comma-separated.
5. **Does `throws IOException` throw an exception by itself?** — No. It only declares the possibility of letting the error escape.
6. **Does a method with `throws IllegalArgumentException` make `catch` mandatory?** — No. `IllegalArgumentException` is an unchecked exception.
7. **What must a subclass constructor do when `super()` declares `throws IOException`?** — On Java 17, the subclass constructor needs to declare that checked exception (or an appropriate supertype) if the call can let it escape.
8. **Can an override of a `throws IOException` method add `throws SQLException`?** — No, because `SQLException` is a checked exception from a different branch, not in the parent contract.
9. **Is `public static void main(String[] args) throws Exception` valid?** — Yes. However, an exception escaping `main` can still cause the application to terminate abruptly.
10. **When does a constructor return a complete object?** — Only when the initialization chain succeeds and the constructor finishes normally; if an exception is thrown, object creation does not complete normally.

## References

- [Java Language Specification 17, §8.4.6 — Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): syntax and rules for the method `throws` clause.
- [Java Language Specification 17, §8.8.5 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.5): constructor syntax and exception declarations.
- [Java Language Specification 17, §8.8.7.1 — Explicit Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1): `this(...)` and `super(...)` invocations in constructors.
- [Java Language Specification 17, §11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): catch-or-declare requirement for checked exceptions.
- [Java Language Specification 17, §8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): checked exception restrictions when overriding.
- [Java SE 17 API — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): examples of I/O methods declaring `IOException`.

**Remember:** for methods, write `ReturnType name(params) throws ExceptionType { ... }`; for constructors, write `ClassName(params) throws ExceptionType { ... }` with **no return type**. `throws` advertises the exception types that may propagate out; callers of checked exceptions must catch or declare them, while `throw` is what actually triggers the exception-throwing flow.
