# Checked exceptions in Java instance initializers and constructors

In Java, an object can perform initialization **before the body of its constructor runs**: instance field initialization expressions and **instance initializer blocks** (`{ ... }` at class level). If these initialization segments can throw **checked exceptions**, Java enforces a special rule: for a **named class**, there must be at least one explicitly declared constructor, and **all explicitly declared constructors of the class** must have a `throws` clause covering the checked exceptions that can arise from the instance initializers. **Anonymous classes** have a special exception mechanism because programmers cannot explicitly declare a constructor for an anonymous class.

An easily overlooked rule:

~~~java
import java.io.IOException;

class Config {
    String data = read(); // read() throws IOException.

    Config() throws IOException {
        // Valid if read() is defined appropriately.
    }

    static String read() throws IOException {
        throw new IOException("không đọc được");
    }
}
~~~

With the class above, an `IOException` can be thrown **during the creation of `new Config()`**, before the body of `Config()`. Therefore, the constructor must declare it, so that the caller of `new Config()` can `catch` or `throws` it according to the checked exception rules.

This article presents the complete relationship between **instance field initializers, instance initializer blocks, constructors, constructor chaining, and callers**; distinguishes them from **static initializers**; and explains **multiple constructors**, **default constructors**, **anonymous classes**, execution order, and handling initialization failures. The runnable programs have been verified at the Java 17 language level.

## 1. Four code locations easily mistaken for the same constructor

Consider a simple class:

~~~java
class Profile {
    // 1. Instance field initializer:
    String name = loadName();

    // 2. Instance initializer block:
    {
        verifyProfile();
    }

    // 3. Constructor body:
    Profile() {
        System.out.println("Constructor body");
    }

    // 4. Static initializer block:
    static {
        System.out.println("Class initialization");
    }

    static String loadName() {
        return "guest";
    }

    void verifyProfile() {
        // Check state.
    }
}
~~~

This is an **illustrative class**, which compiles when placed in an appropriate Java file. The four components do different things:

| Component | Timing / Target | Can be part of each instance's initialization path? |
| --- | --- | --- |
| Instance field initializer: `String name = loadName()` | Initializes the field on each object, in the corresponding textual order | Yes |
| Instance initializer block: `{ verifyProfile(); }` | Runs during each instance's initialization, interleaved in textual order with instance field initializers | Yes |
| Constructor body: `Profile() { ... }` | Executes the body of the invoked constructor, after that class's instance initialization phase, except for `this(...)` forwarding explained later | Yes |
| Static initializer: `static { ... }` | Initializes the **class**, does not run every time an object is created | No, fundamentally different |

A class can have multiple instance initializer blocks, multiple instance fields with initializers, and multiple overloaded constructors. For a normal instance initialization pass, **instance field initializers and instance initializer blocks of the same class run in the order they appear in the source code**.

If an instance-level segment can throw a checked exception, the responsibility for declaring it does not lie in a "block signature" (blocks have no signature), but is checked across **all constructors of the named class** according to JLS §11.2.3.

## 2. Checked exceptions and the catch-or-declare rule

Checked exceptions are `Throwable` types that are **not** under the `RuntimeException` or `Error` branches. Common types include:

- `IOException`, `FileNotFoundException`: I/O errors that the caller may need to handle.
- `SQLException`: errors when accessing through a database API.
- `ClassNotFoundException`: class not found in a class-loading mechanism.
- `InterruptedException`: operation interrupted.
- Application-defined classes that `extends Exception` without being under `RuntimeException`.

Conversely, `IllegalStateException`, `IllegalArgumentException`, `NullPointerException`, `Error`, and subclasses in the unchecked branch **are not required by the compiler to be caught or declared** under the same rule.

For a constructor:

~~~java
import java.io.IOException;

class Client {
    Client() throws IOException {
        if (System.currentTimeMillis() < 0) {
            throw new IOException("lỗi khởi tạo");
        }
    }
}
~~~

`Client()` is allowed to declare a checked exception in `throws`. When the caller writes:

~~~java
try {
    Client client = new Client();
    System.out.println("Tạo thành công");
} catch (IOException ex) {
    System.out.println("Không tạo được: " + ex.getMessage());
}
~~~

the compiler can verify that the caller has handled the checked type that the constructor allows to propagate out. That holds **whether the error occurs in the constructor body, in a `super(...)` call, in a `this(...)` call, or in an instance initializer executed during object creation**.

`throws IOException` must not be understood as a command that throws an error. `throws` only **declares the possibility of a checked exception escaping**, whereas `throw` or calling a failing API actually creates the abnormal execution path.

## 3. The special rule for named classes under JLS §11.2.3

If an **instance variable initializer** or **instance initializer block** of a **named class** *can throw* a checked exception of type E according to compile-time analysis, Java simultaneously requires:

1. The named class has **at least one explicitly declared constructor** in the source code.
2. **Each explicitly declared constructor** of the named class has a `throws` clause specifying E **or a superclass covering E**.
3. Execution paths in the constructor body also satisfy the usual checked exception rules; calling `super(...)` and `this(...)` does not exempt it from this.

Example with E = `FileNotFoundException`:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

class Document {
    String content = load();

    Document() throws IOException { }             // Covers E.
    Document(int id) throws FileNotFoundException { } // E itself.

    static String load() throws FileNotFoundException {
        throw new FileNotFoundException("thiếu tài liệu");
    }
}
~~~

Here both constructors declare `FileNotFoundException`, either directly or via the superclass `IOException`. Looking specifically at the checked exception rule in initializers, this example is valid.

**Every constructor does not necessarily have to declare the exact same `throws IOException` list.** The condition is that **each checked exception that can escape from an initializer is covered by a type in the `throws` clause of every constructor**.

If an initializer can produce both `IOException` **and** `SQLException`, every constructor needs to declare both types or suitable superclasses covering them. You could write `throws Exception`, but for a public API declaring too broadly often makes it harder for callers to determine a handling strategy.

### One constructor missing `throws` makes the entire class invalid

~~~java
import java.io.IOException;

// INTENTIONALLY INVALID:
class OneMissingThrowsBad {
    String value = fetch();

    OneMissingThrowsBad() throws IOException { }
    OneMissingThrowsBad(int mode) { } // Does not declare IOException.

    static String fetch() throws IOException {
        throw new IOException();
    }
}
~~~

Even though the no-argument constructor declares `IOException`, the constructor taking `int` still does not satisfy the rule. Even if the programmer intends to "only use the first constructor", **the compiler still checks all declared constructors**.

Running `javac OneMissingThrowsBad.java` will fail with an uncaught/undeclared checked exception error; the error location reported may point to `fetch()` in the initializer.

## 4. Why is the default constructor not enough?

If a named class **does not write any constructor**, Java can provide a **default constructor** according to language rules. However, this default constructor **cannot have a `throws IOException` clause attached to its implicit declaration by the programmer**.

Therefore:

~~~java
import java.io.IOException;

// INTENTIONALLY INVALID:
class NoConstructorBad {
    String value = fetch(); // Can throw checked IOException.

    static String fetch() throws IOException {
        throw new IOException();
    }
}
~~~

is a compile error. It cannot be solved by relying on the default constructor.

One way to fix it:

~~~java
import java.io.IOException;

class HasConstructor {
    String value = fetch();

    HasConstructor() throws IOException { }

    static String fetch() throws IOException {
        return "ready";
    }
}
~~~

When calling `new HasConstructor()`, the caller must handle or declare `IOException` according to the constructor signature, even though `fetch()` in the fixed example always returns a stable value at runtime. The compiler applies throwability analysis based on the `fetch() throws IOException` signature, rather than proving that every runtime branch inside that method will always succeed.

**Another fix:** handle the checked exception directly inside the initializer with `try/catch`, if there is a valid fallback value or recovery path. When the checked exception can no longer escape from the initializer, it is not necessary to add `throws` to the constructors just because of that initializer.

## 5. An `instance initializer` cannot declare its own `throws`

An instance-level block is part of the class body:

~~~java
import java.io.IOException;

class Example {
    {
        initialize();
    }

    Example() throws IOException { }

    static void initialize() throws IOException {
        // Can throw IOException.
    }
}
~~~

The snippet above is valid because the constructor declares `throws IOException`. There is no valid Java syntax like:

~~~java
// INTENTIONALLY INVALID: an instance initializer block has no throws signature.
{
    throws IOException;
    initialize();
}
~~~

You cannot attach `throws` to the header of an initializer block; it is not a method or constructor. Therefore, the place to declare checked exceptions is the constructors, while the place to **handle them immediately** can be a `try/catch` inside the block.

Another note: a Java instance initializer block must be **able to complete normally**, according to the separate reachability rule for the end of a block. Writing a block containing only an unconditional `throw new IOException(...);` makes it unable to complete normally; this error is **different** from the error of missing `throws` on a constructor. If you want to create a conditional failure path, use a conditional statement or a method that can throw, as in the runnable examples below.

## 6. Execution order: superclass, instance initializers, constructor body

When creating an object of a regular named class, the initialization flow needs to be understood in layers, not simply as "the constructor runs before all initializers".

A common model:

~~~text
new Child(...)
    │
    ├─ Evaluate arguments and enter the relevant constructor
    ├─ Invoke another constructor along the this(...) / super(...) chain
    ├─ Complete appropriate superclass initialization
    ├─ Execute Child's instance field initializers and instance initializer
    │  blocks in textual order
    └─ Execute the remaining statements in Child's constructor body
~~~

**Details:** Java also has allocation steps, default field assignment, constructor invocation processing, and outer instance rules. The diagram above only highlights what is important for this lesson: **a class's instance initializers run before the main execution body of that class's constructor, after the superclass constructor and related forwarding calls have been properly executed**.

If an instance field initializer throws `IOException`:

- Subsequent initializers of that class **do not run**.
- The constructor body of that class **does not run**.
- The `new Child(...)` creation path terminates abnormally; the caller can catch the checked exception.
- Side effects that already occurred before the throw point **are not automatically rolled back**.
- An object that was not successfully created is not returned from the `new` expression.

Do not confuse exceptions during instance initialization with failures of **static class initialization**; they have different checking rules and error reporting mechanisms.

## 7. Complete Java 17 program: errors in field and block before constructor body

File `NamedInitializerDemo.java`:

~~~java
import java.io.IOException;

public class NamedInitializerDemo {
    static boolean failField;
    static boolean failBlock;
    final String value = loadField();

    static String loadField() throws IOException {
        System.out.println("Khởi tạo field");
        if (failField) throw new IOException("field lỗi");
        return "ready";
    }

    {
        System.out.println("Khối khởi tạo");
        if (failBlock) throw new IOException("block lỗi");
    }

    NamedInitializerDemo() throws IOException {
        System.out.println("Thân constructor rỗng");
    }

    NamedInitializerDemo(String label) throws IOException {
        this();
        System.out.println("Thân constructor có tham số: " + label);
    }

    public static void main(String[] args) {
        try {
            System.out.println("Giá trị: " + new NamedInitializerDemo("A").value);
        } catch (IOException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }

        failField = true;
        try {
            new NamedInitializerDemo();
        } catch (IOException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }

        failField = false;
        failBlock = true;
        try {
            new NamedInitializerDemo();
        } catch (IOException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 NamedInitializerDemo.java
java NamedInitializerDemo
~~~

**Exact stdout:**

~~~text
Khởi tạo field
Khối khởi tạo
Thân constructor rỗng
Thân constructor có tham số: A
Giá trị: ready
Khởi tạo field
Lỗi: field lỗi
Khởi tạo field
Khối khởi tạo
Lỗi: block lỗi
~~~

### Analysis of the three object creation runs

**Run 1 — success:** `failField=false`, `failBlock=false`.

1. `value = loadField()` runs and prints `Khởi tạo field`.
2. The instance initializer block prints `Khối khởi tạo`.
3. Constructor `NamedInitializerDemo()` is called via `this()` and prints `Thân constructor rỗng`.
4. The rest of `NamedInitializerDemo(String)` prints `Thân constructor có tham số: A`.
5. The `new ...` expression completes; the caller reads `value` as `ready`.

**Run 2 — field initializer error:** `failField=true`.

1. `loadField()` prints `Khởi tạo field` and then throws checked `IOException("field lỗi")`.
2. The subsequent block does not run, and no lines from the constructor body run.
3. The caller catches `IOException` and prints `Lỗi: field lỗi`.

**Run 3 — instance initializer block error:** `failField=false`, `failBlock=true`.

1. The field initializer completes normally.
2. The block prints `Khối khởi tạo` and then throws `IOException("block lỗi")`.
3. The constructor body does not run; the caller catches it and prints `Lỗi: block lỗi`.

Both constructors of the named class declare `throws IOException`. That is the condition for the compiler to accept checked exceptions that can arise from both the field initializer and the block.

### Impact of `this()` on the initialization pass

The constructor taking `String` uses `this()` to forward to the no-argument constructor. Constructor chaining **does not cause the instance field initializers and instance initializer blocks of the same object to run twice**. They are executed in one pass during that class's initialization, before the constructor bodies complete in forwarding order.

Because the `NamedInitializerDemo(String)` constructor calls `this()`, it also has a path that receives `IOException` from the target constructor. Thus, both the policy of **declaring on every constructor due to the initializer** and the obligation of **handling/declaring checked exceptions from the `this()` call** must be observed.

## 8. Checking multiple constructors and constructor chaining

If there is only one constructor, the rule is simple:

~~~java
class Single {
    String data = load();

    Single() throws java.io.IOException { }

    static String load() throws java.io.IOException {
        return "OK";
    }
}
~~~

With two overloaded constructors:

~~~java
class Multiple {
    String data = load();

    Multiple() throws java.io.IOException { }

    Multiple(int mode) throws java.io.IOException {
        this();
        // Continue after the target constructor completes.
    }

    static String load() throws java.io.IOException {
        return "OK";
    }
}
~~~

Both declare `IOException`. If `Multiple(int)` does not declare it, the compiler may report an error **from the initializer** and/or **the `this()` call**. Do not assume that a forwarding constructor does not need `throws` because all the initialization code is "in the other constructor".

A class can have both a constructor calling `super(...)` and a constructor calling `this(...)`. **Every constructor** of a named class whose initializer can throw a checked exception must still satisfy the JLS declaration requirement.

If the superclass constructor also declares another checked exception, the subclass constructor calling it must also handle or declare **the checked types escaping from `super(...)`**. That responsibility is the standard constructor invocation rule, in addition to the specific rule for the subclass's initializers.

## 9. Callers of `new` are bound by the constructor contract

Suppose:

~~~java
class DocumentReader {
    String content = openDocument();

    DocumentReader() throws java.io.IOException { }

    static String openDocument() throws java.io.IOException {
        return "text";
    }
}
~~~

Caller:

~~~java
try {
    DocumentReader reader = new DocumentReader();
    System.out.println(reader.content);
} catch (java.io.IOException ex) {
    System.err.println("Không tạo được reader: " + ex.getMessage());
}
~~~

`IOException` can be propagated to the caller from the **instance initializer**, even though the constructor is empty. This is why a constructor signature does not only describe the statements **written directly inside the constructor's curly braces**. It also describes the checked errors that can arise when **completing the object creation operation**.

If the caller neither catches nor has an appropriate `throws IOException`, the compiler reports an error. `new DocumentReader()` itself is a **class instance creation expression** that can throw checked exceptions from the selected constructor.

When a library evolves and begins creating additional resources in an instance field initializer, adding a checked exception to a public constructor can affect **source compatibility** for clients. Therefore, you should not arbitrarily move an I/O operation that can fail into an instance initializer without considering the object creation contract.

## 10. How to fix it when you don't want constructors to declare checked exceptions

You can **handle the error directly in the initializer**, with a genuinely valid recovery path. This is not "dodging the compiler" by ignoring errors; you must decide whether the fallback state is safe.

Program `HandledInitializerDemo.java`:

~~~java
import java.io.IOException;

public class HandledInitializerDemo {
    final String state;

    static String fetch() throws IOException {
        throw new IOException("nguồn không sẵn");
    }

    {
        String result;
        try {
            result = fetch();
        } catch (IOException ex) {
            System.out.println("Đã xử lý: " + ex.getMessage());
            result = "fallback";
        }
        state = result;
    }

    HandledInitializerDemo() {
        System.out.println("Constructor: " + state);
    }

    public static void main(String[] args) {
        System.out.println("Kết quả: " + new HandledInitializerDemo().state);
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 HandledInitializerDemo.java
java HandledInitializerDemo
~~~

Stdout:

~~~text
Đã xử lý: nguồn không sẵn
Constructor: fallback
Kết quả: fallback
~~~

Here `fetch()` throws checked `IOException`, but `try/catch` in the instance initializer **catches and resolves it with a fallback value**. Because the initializer no longer lets `IOException` escape, the `HandledInitializerDemo()` constructor does not need `throws IOException` just because of `fetch()`.

**Note:** the example assumes the string `"fallback"` is a valid state. In a real application, if it cannot operate without the initialization data, you should not swallow `IOException` and create an object that looks like it succeeded. When there is no recovery path, keep the checked exception or wrap it into an exception that matches the contract.

## 11. Should you convert checked exceptions to unchecked exceptions in an initializer?

Sometimes an API does not want its public constructors to declare a checked exception and chooses to wrap the error in an unchecked exception:

~~~java
class ConfigurationUnavailableException extends RuntimeException {
    ConfigurationUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}

class Configuration {
    final String content;

    {
        String value;
        try {
            value = readConfiguration();
        } catch (java.io.IOException ex) {
            throw new ConfigurationUnavailableException(
                    "Không khởi tạo được cấu hình", ex);
        }
        content = value;
    }

    Configuration() { }

    static String readConfiguration() throws java.io.IOException {
        return "mode=prod";
    }
}
~~~

This is **illustrative code consisting of corresponding classes**, valid under normal compilation conditions. When `IOException` occurs, the initializer wraps the error into `ConfigurationUnavailableException` (**unchecked**) and the constructor does not need to declare `throws IOException`.

However, this is a **contract design** decision, not an always-right fix:

- Callers are no longer forced by the compiler to handle initialization errors.
- The thrown exception type needs to accurately express the abstraction and failure scenario.
- The **cause** should be preserved via `super(message, cause)` so the original `IOException` is not lost.
- If object creation can fail along an expected path and callers must recover, a checked exception or a **factory method** may be more appropriate.

You can move the I/O logic out of the initializer into a **factory method** with `throws IOException`, and only create the object after the failure-prone steps have succeeded. This approach often allows clearer management of resources and initialization state.

## 12. Differences from a regular constructor body

A constructor body can directly throw a checked exception:

~~~java
import java.io.IOException;

class Parser {
    Parser() throws IOException {
        if (System.nanoTime() < 0) {
            throw new IOException("khởi tạo thất bại");
        }
    }
}
~~~

In this case, the `throws IOException` obligation arises **from the constructor body**. The class is not required to have any initializer.

If you omit `throws IOException` while still throwing:

~~~java
import java.io.IOException;

// INTENTIONALLY INVALID:
class ConstructorBodyBad {
    ConstructorBodyBad() {
        throw new IOException("body");
    }
}
~~~

it will be a compile-time error: uncaught or undeclared checked exception.

Thus there are two related but distinct contexts:

| Point that can throw a checked exception | Required rule |
| --- | --- |
| Constructor body | That constructor must catch or declare the type allowed to escape |
| `super(...)` or `this(...)` call | The constructor containing the call must follow catch-or-declare per constructor invocation rules |
| Instance field initializer of a named class | **Must have an explicit constructor; every explicit constructor** must declare checked exceptions that can escape from the initializer |
| Instance initializer block of a named class | Same rule as instance field initializer |
| Instance initializer that already catches and handles all checked exceptions | That checked exception no longer escapes; no need to declare it just because the call is inside the block |
| Unchecked exception in an initializer | Does not require catch-or-declare under checked rules, but can cause `new` to fail at runtime |

**Remember:** for initializers of a named class, having one individual constructor declare it properly does not exempt the remaining constructors from declaring it.

## 13. Anonymous classes are a notable exception to the named class rule

An anonymous class is an unnamed class declared directly inside an object creation expression:

~~~java
interface Action {
    void run();
}

Action action = new Action() {
    @Override
    public void run() {
        System.out.println("Action");
    }
};
~~~

Programmers **cannot explicitly declare a constructor** for an anonymous class. Therefore, if the condition "must have an explicitly declared constructor" were applied mechanically, an anonymous class could never have an initializer with checked exceptions.

Java has a **special rule**: checked exceptions that can arise from an anonymous class's instance initializer are reflected by the compiler in the anonymous class's **implicitly generated constructor** and in the throwability analysis of the **anonymous class creation expression**. Consequently, the call site of `new Interface() { ... }` may need to catch or declare that checked exception.

The complete example in the next section clarifies this.

## 14. Complete Java 17 example: anonymous class with an initializer throwing `IOException`

File `AnonymousInitializerDemo.java`:

~~~java
import java.io.IOException;

public class AnonymousInitializerDemo {
    interface Action {
        void run();
    }

    static String prepare(boolean fail) throws IOException {
        System.out.println("Khởi tạo anonymous");
        if (fail) throw new IOException("anonymous lỗi");
        return "OK";
    }

    static Action create(boolean fail) throws IOException {
        return new Action() {
            final String label = prepare(fail);

            @Override
            public void run() {
                System.out.println("Chạy: " + label);
            }
        };
    }

    public static void main(String[] args) {
        try {
            Action action = create(false);
            action.run();
            create(true);
        } catch (IOException ex) {
            System.out.println("Bắt lỗi: " + ex.getMessage());
        }
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 AnonymousInitializerDemo.java
java AnonymousInitializerDemo
~~~

Exact stdout:

~~~text
Khởi tạo anonymous
Chạy: OK
Khởi tạo anonymous
Bắt lỗi: anonymous lỗi
~~~

Notes:

1. `new Action() { ... }` creates an **anonymous class** implementing the `Action` interface.
2. `final String label = prepare(fail)` is an instance field initializer of the anonymous class; `prepare` can throw `IOException`.
3. The anonymous class has no explicit constructor, but this case **is allowed** under JLS §11.2.3.
4. The anonymous class creation expression in `create()` can throw `IOException`, so the `create(boolean)` method declares `throws IOException`.
5. The caller `main()` handles `IOException` with `catch`.
6. If creating the anonymous class fails, the `run()` method of the new object **is not called**, because the object was not successfully created.

**Do not confuse:** the fact that `Action.run()` does not declare `throws IOException` does not prevent the **anonymous class's implicitly generated constructor** from throwing `IOException` during object creation. However, if you place `throw new IOException(...)` directly inside the **`run()` method body**, you still have to obey the override contract of `Action.run()`, which does not allow this checked exception to escape.

## 15. Differences from static field initializers and static initializer blocks

This is a very important contrast. For a **named class or interface**, a static field initializer or static initializer **must not let a checked exception escape**. It cannot be fixed by adding `throws IOException` to instance constructors, because static initialization is the **class initialization** mechanism.

Invalid example:

~~~java
import java.io.IOException;

// INTENTIONALLY INVALID:
class StaticInitializerBad {
    static String value = fetch();

    static String fetch() throws IOException {
        throw new IOException();
    }
}
~~~

Running `javac StaticInitializerBad.java` fails with an uncaught/undeclared checked exception error; there is no `static { ... } throws IOException` syntax for class-level blocks.

An approach that handles it:

~~~java
import java.io.IOException;

class SafeStatic {
    static final String value;

    static {
        try {
            value = read();
        } catch (IOException ex) {
            throw new IllegalStateException("Không khởi tạo được class", ex);
        }
    }

    static String read() throws IOException {
        return "OK";
    }
}
~~~

This snippet is a **valid Java class**, but note: when a static initializer actually throws an unchecked exception that is not an `Error`, the class initialization failure at runtime may be wrapped in `ExceptionInInitializerError`; subsequent uses of the class may also encounter errors related to the class initialization state. This is the **runtime contract of class initialization**, not the checked `throws` mechanism of instance constructors.

| Mechanism | Can a checked exception escape via constructor `throws`? |
| --- | --- |
| Instance initializer of a **named class** | Yes, if all explicit constructors declare it appropriately and the class has at least one explicit constructor |
| Instance initializer of an **anonymous class** | Has its own mechanism via the implicitly generated constructor and the anonymous `new` expression |
| Static initializer of a named class/interface | No; checked exceptions must be handled in place |
| Constructor body | Yes; declare it appropriately on that constructor |
| Regular method body | Yes, per method catch-or-declare rules |

Do not think of a checked exception caused by a **static initializer** as a case that "can be fixed by adding `throws IOException` to the constructor".

## 16. How many times do instance initializers run with `this()` and inheritance?

A normally completing object creation pass includes the initialization chain of the classes in the hierarchy. Under normal flow:

- The superclass has its instance initializers; they run when the superclass is initialized for the object.
- After the relevant superclass initialization completes, the subclass's instance initializers run.
- With constructors of the same class chained via `this(...)`, they **do not cause that class's own initializers to run multiple times** on the same object.
- If an initializer fails, initializers or constructor body parts after it in the same execution path may not run.
- The caller does not receive a successful `new` result when initialization terminates abnormally.

Example illustrating the order:

~~~java
class Base {
    {
        System.out.println("Base initializer");
    }

    Base() {
        System.out.println("Base constructor");
    }
}

class Derived extends Base {
    {
        System.out.println("Derived initializer");
    }

    Derived() {
        System.out.println("Derived constructor");
    }

    Derived(String label) {
        this();
        System.out.println("Derived constructor " + label);
    }
}
~~~

If placed in a program and `new Derived("A")` is called, the relevant output order is:

~~~text
Base initializer
Base constructor
Derived initializer
Derived constructor
Derived constructor A
~~~

This snippet is a **two-class illustration**, without a `main` method; stdout is deduced from the constructor chaining order, not the output of a standalone file. The behavior aligns with the complete runnable program `NamedInitializerDemo` in section 7.

If `Base`'s constructor throws a checked exception, the `Derived` constructor calling it must handle/declare it according to constructor invocation rules. If `Derived`'s instance initializer can also throw another checked type, **every explicit constructor of `Derived`** must declare that type.

## 17. Checked exceptions when creating resources in initializers: cleanup responsibility

A design trap: an instance initializer can open resources such as streams, sockets, or JDBC connections. If opening a child resource succeeds and a later initialization operation fails, **the enclosing object has not been successfully created** and the caller has no reliable reference on which to call `close()`.

Code illustrating the issue:

~~~java
// Illustration in a class that declares Path, IOException, and the checkHeader API.
class FragileReader implements AutoCloseable {
    java.io.InputStream in;

    {
        in = java.nio.file.Files.newInputStream(path);
        checkHeader(in); // If it throws IOException, creating FragileReader fails.
    }

    FragileReader() throws java.io.IOException { }

    @Override
    public void close() throws java.io.IOException {
        if (in != null) in.close();
    }
}
~~~

This snippet is **not standalone** (it requires defining `path` and `checkHeader`). It illustrates a hazard: the caller's `try (FragileReader r = new FragileReader())` **only automatically closes `r` if the resource expression initializes successfully**. If an error occurs **in `FragileReader`'s initializer**, `r` has not been assigned a complete object; `try-with-resources` at the caller does not automatically `close()` the partially opened internal resource `in`.

Safer approaches:

1. Place allocation and validation in a **factory method** or a controlled constructor.
2. If a step after opening a resource fails, **close the allocated resource right where it was allocated**.
3. Use `try-with-resources` for child resources if an ownership-transfer path can be safely designed.
4. Preserve primary errors and secondary closing errors via cause/suppressed when appropriate.
5. Avoid "publishing" the `this` reference of an incompletely initialized object to external code.

Checked exception rules inform callers that failure is possible, but **do not automatically roll back state or close partially allocated resources**.

## 18. A factory method can make the contract clearer

Instead of placing a failure-prone open operation in a field initializer:

~~~java
class FragileClient {
    final String configuration = readConfiguration();

    FragileClient() throws java.io.IOException { }

    static String readConfiguration() throws java.io.IOException {
        return "mode=prod";
    }
}
~~~

you can perform the I/O step first, and then create the object with only the prepared data:

~~~java
import java.io.IOException;

final class Client {
    private final String configuration;

    private Client(String configuration) {
        this.configuration = configuration;
    }

    static Client open() throws IOException {
        String configuration = readConfiguration();
        return new Client(configuration);
    }

    static String readConfiguration() throws IOException {
        return "mode=prod";
    }

    String configuration() {
        return configuration;
    }
}
~~~

This is a valid standalone Java class, though without `main`. Callers use `Client.open()`, catching or declaring `IOException`; the private constructor has no checked exceptions. Advantages:

- The data opening/preparation path is clearly visible in a named method with an explicit `throws`.
- Each constructor does not have to declare errors from a complex initializer.
- Temporary resources can be handled in the factory before transitioning to a complete object state.
- Easy to write tests for each success/failure path and identify the ownership transfer point.

Not every class with I/O is required to use a factory. If a constructor publicly means "create an object that may fail with I/O", declaring `throws IOException` on the constructors is also a valid design. Which approach to choose depends on API boundaries and failure-state management.

## 19. Intentionally invalid files to recognize compiler errors

The following snippets are **negative compilation test examples**, not runnable programs.

### 19.1. Missing explicit constructor

~~~java
import java.io.IOException;

class NoConstructorBad {
    String value = fetch();
    static String fetch() throws IOException {
        throw new IOException();
    }
}
~~~

`javac` reports something like:

~~~text
error: unreported exception IOException; must be caught or declared to be thrown
~~~

The cause is that the named class's initializer can throw checked `IOException`, but the class has no explicit constructor declaring it.

### 19.2. One of multiple constructors does not declare it

~~~java
import java.io.IOException;

class OneMissingThrowsBad {
    String value = fetch();
    OneMissingThrowsBad() throws IOException { }
    OneMissingThrowsBad(int mode) { }
    static String fetch() throws IOException {
        throw new IOException();
    }
}
~~~

`javac` also rejects this. Having the first constructor declare it properly **does not compensate for the second constructor**.

### 19.3. Static initializer with unhandled checked exception

~~~java
import java.io.IOException;

class StaticInitializerBad {
    static String value = fetch();
    static String fetch() throws IOException {
        throw new IOException();
    }
}
~~~

`javac` rejects this; this is the **static initialization** rule, which cannot be fixed merely by declaring `throws` on instance constructors.

### 19.4. Constructor body throws an undeclared checked exception

~~~java
import java.io.IOException;

class ConstructorBodyBad {
    ConstructorBodyBad() {
        throw new IOException("body");
    }
}
~~~

`javac` rejects this because the constructor body directly throws checked `IOException` without handling or declaring it. This is the regular constructor body rule, not the "every constructor" condition of instance initializers.

All four cases were verified with `javac --release 17`; messages may point to different expressions, but the cause in all of them relates to checked exception throwability not matching the context.

## 20. Distinguishing errors in object initializers from class initialization errors

The "initializer" names are very easy to misunderstand:

| Property | Instance initializer | Static initializer |
| --- | --- | --- |
| Associated with | Each individual object | Class/interface per class initialization rules |
| Examples | `String x = load();`, `{ check(); }` | `static String x = load();`, `static { check(); }` |
| Runs again on successive object creations? | Yes, for each corresponding object initialization | Does not automatically re-run for each `new` |
| Checked exception escaping in a named class | Possible, if all explicit constructors declare coverage | Not allowed to escape directly |
| Common handling point | Caller of `new` or constructor/factory | `try/catch` block in static initialization, or unchecked failure at runtime |
| Can prevent object creation from completing? | Yes | Can cause the class to fail initialization, preventing usage |

If a static initializer causes class initialization to fail, callers may see `ExceptionInInitializerError` or class-state-related errors, depending on the situation. **Seeing `ExceptionInInitializerError` does not mean it is an instance initializer error**; this exception name specifically relates to class initialization.

## 21. Common mistakes and how to fix them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Instance field initializer calls a checked API, but the class has no constructor | Compiler error | Write an explicit constructor with `throws`, or handle the checked exception in the initializer |
| Only the no-arg constructor has `throws`, while overloaded constructors do not | Compiler error for named class | Every explicit constructor must declare checked exceptions from the initializer |
| Thinking `this(...)` already calls another constructor so the current constructor doesn't need `throws` | Ignores checked exception obligations from the initializer and target constructor call | Declare/design properly in every constructor |
| Putting `throws IOException` after `{ ... }` of an instance initializer | Invalid Java syntax | `throws` belongs in constructor/method declarations |
| Placing an unconditional checked `throw` in an instance initializer | May violate the rule that the block must be able to complete normally | Use a conditional path and follow checked exception rules |
| Thinking the constructor body always runs before field initializers | Wrong prediction of stdout or state | Follow the order: superclass → same-class initializers → constructor body |
| Thinking a failing instance initializer still continues running subsequent initializers | Misreading control flow | Treat the throw point as an abnormal exit path |
| Catching a checked exception in an initializer and leaving it empty | Creates an object in an invalid state, hiding real errors | Recover validly or propagate a meaningful error |
| Wrapping `IOException` into unchecked while dropping the cause | Loses technical trace | Use the `(message, cause)` constructor |
| Using instance `throws` to fix an error in a static initializer | Has no effect | Catch checked errors inside the static initializer or redesign |
| Assuming an anonymous class must declare an explicit constructor | Anonymous classes cannot declare constructors | Rely on the implicitly generated constructor mechanism and catch-or-declare at the `new` expression |
| Partially initializing a resource and then throwing, expecting the caller to call `close()` | Can leak resources | Manage cleanup at the allocation site before transferring ownership |
| Confusing checked with unchecked exceptions | Missing or unnecessary `throws` declarations | Check the type hierarchy against `RuntimeException`/`Error` |
| Putting heavy I/O logic across multiple field initializers | Hard to control errors, side effects, and tests | Consider a factory or step-by-step initialization in a constructor |

## 22. Checklist when designing a class with potentially failing initializers

1. **Identify exactly where a checked exception can be thrown:** field initializer, instance block, constructor body, `super` call, `this` call, or static initializer?
2. **Is this a named class or an anonymous class?** The two cases have different error declaration rules.
3. For a named class, **is there at least one explicit constructor?**
4. **Does every explicit constructor have `throws` covering each checked exception escaping from initializers?**
5. If an initializer calls an I/O API, **does the caller of `new` have a proper `catch` or `throws` path?**
6. Do the initializers run **in the right source-code order**? Is there any dependency on a field not yet assigned a value?
7. If an initializer fails, **how is previously allocated state/resources released**?
8. If initialization code can recover, does the fallback value truly **preserve the object's invariants**?
9. **Should complex operations be moved to a factory** to represent errors and resource ownership more clearly?
10. For an anonymous class, is the checked exception from the initializer **caught/declared at the object creation expression**?
11. **Do not confuse with static initializers** or `ExceptionInInitializerError`.
12. **Test the success path, field error path, and block error path** with examples and verify whether the constructor body runs.

## 23. Self-check questions

**Question 1.** A named class has `String value = load();` with `load() throws IOException`, but declares no constructor. Does it compile?

**Answer:** No. A named class must have at least one explicitly declared constructor, and every explicit constructor must have an appropriate `throws` for checked exceptions from initializers.

**Question 2.** A named class has two constructors; only one constructor has `throws IOException`. An instance initializer can throw `IOException`. Is this valid?

**Answer:** No. **Every** explicit constructor must declare `IOException` or a suitable superclass.

**Question 3.** Can `throws IOException` be attached directly to the braces of an instance initializer block?

**Answer:** No. Blocks have no signature; it must be declared on the constructors or handled inside the block.

**Question 4.** If an initializer catches `IOException` and returns a valid fallback, is the constructor required to have `throws IOException`?

**Answer:** No, provided no path from the initializer can let `IOException` escape and there is no other checked exception obligation.

**Question 5.** Why might `new Example()` have to `catch IOException` even when the body of `Example()` is empty?

**Answer:** Because an instance field initializer or instance block running during object creation can throw a checked exception and it is declared via the constructor.

**Question 6.** Constructor A calls `this()` to constructor B; do the instance initializers of the same class run twice?

**Answer:** No; they run once for a single instance initialization process of that class.

**Question 7.** An instance field initializer throws an exception before an instance block. Does the subsequent block run?

**Answer:** No; same-class initialization terminated abnormally at the throw point.

**Question 8.** Can an anonymous class have a field initializer calling a method that `throws IOException`?

**Answer:** Yes; Java infers the checked exception in the implicitly generated constructor and requires handling/declaring it when the anonymous class creation expression can throw.

**Question 9.** Does adding `throws IOException` to a constructor fix a **static field initializer** that throws checked `IOException`?

**Answer:** No. A static initializer must handle checked exceptions itself or change the design.

**Question 10.** If an object is partially initialized after opening a stream, is a caller using `try-with-resources` on that object guaranteed to close the stream?

**Answer:** No. The caller does not yet have a complete object; the constructor/factory must manage allocated resources itself on failure.

**Question 11.** Does wrapping a checked exception into an unchecked one automatically preserve the original error?

**Answer:** No. You need to pass the `cause` explicitly, for example `new IllegalStateException("không khởi tạo được", original)`.

**Question 12.** Does a checked exception in a constructor body require **every overloaded constructor** to declare that type?

**Answer:** Not solely because the error is in **one constructor's body**. The "every constructor" rule is a special requirement for checked exceptions escaping from **an instance initializer of a named class**. Other constructors still have their own obligations if they call that constructor via `this(...)` or perform checked operations themselves.

## 24. References

- [Java Language Specification 17 — §11.2.3, Exception Checking](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.3): the **every explicit constructor** rule of named classes and the special exception for anonymous classes.
- [Java Language Specification 17 — §8.3.2, Field Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2): field initialization expressions.
- [Java Language Specification 17 — §8.6, Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): instance initializer block rules and ability to complete normally.
- [Java Language Specification 17 — §8.8, Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructors, explicit constructor invocations, and `throws` clauses.
- [Java Language Specification 17 — §12.5, Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): order and conditions of instance initialization.
- [Java Language Specification 17 — §15.9.5, Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5): anonymous class semantics and implicitly generated constructors.
- [Java Language Specification 17 — §8.7, Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): distinguishing static initialization from instance initialization.

**Conclusion:** checked exceptions can occur **before the constructor body** in an instance field initializer or instance initializer block. For a **named class**, Java requires **at least one explicit constructor** and **every explicit constructor** to declare those checked exceptions in `throws`, or handle them so they do not escape from the initializer. For an **anonymous class**, the compiler uses an implicitly generated constructor and shifts the catch-or-declare obligation to the object creation expression. Understanding this boundary properly helps you design safe constructors, factories, resources, and error contracts.
