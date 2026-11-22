# Method References and `throws` Compatibility in Java

A **method reference** (`::`) is a shorthand syntax for using a method or constructor as the implementation of a **functional interface**. When the referenced method can throw a **checked exception**, Java does not only check parameters and return type: the compiler also compares **the checked exceptions that the invocation can throw** against **the `throws` clause of the single abstract method (SAM)** in the target type.

One core rule:

> **A method reference with checked exceptions is compatible with a functional interface only if the relevant checked exceptions are permitted by the SAM's `throws` clause**, taking Java's type and generic inference rules into account. There is no automatic "catch", "add `throws`", or "wrap into RuntimeException" conversion simply because the `::` syntax is used.

For example, `Callable<T>.call() throws Exception` can accept a method reference to a method declared with `throws IOException`. Conversely, `Supplier<T>.get()` and `Runnable.run()` declare no checked exceptions, so they cannot directly accept a method reference whose referenced method declares `throws IOException`.

This article explains how Java checks method references with `throws` on Java 17+, distinguishes static/bound/unbound/constructor references, tests with programs that have exact outputs, shows how to fix compilation errors, covers generic functional interfaces with exception type parameters, adapters to standard APIs, overloading, and design boundaries to watch out for.

## 1. Recalling the Parts of a Method Reference

A method reference does not immediately produce an invocation when written. It is an expression that is **target-typed** (*target typing*) and creates an object behaving according to the chosen functional interface.

For example:

```java
Runnable task = service::run;
```

This is **illustrative code**; it requires a `service` variable with a suitable `run()` method. Here:

- `service::run` is the **method reference expression**.
- `Runnable` is the **target type**.
- `Runnable.run()` is the **SAM**, with signature `void run()`, declaring no checked exceptions.
- The instance method `service.run()` is the **referenced method**; it must be compatible with the SAM.
- When `task.run()` is called, the referenced behavior actually executes.

The parts that must match include **parameter count/types, return type convertibility, and the set of checked exceptions allowed to escape**. A method with `throws` is not a separate overload solely because of its `throws` clause.

**Distinguish three moments in time:**

1. **Compilation**: Java checks whether the method reference is compatible with the target SAM, including checked exceptions.
2. **Reference evaluation**: creates/captures the appropriate reference; normally does not invoke the target method.
3. **SAM invocation**: the target method executes and exceptions can actually be thrown, caught, or propagated.

For a bound reference such as `object::instanceMethod`, evaluating the receiver has its own rules; a `null` receiver can cause a `NullPointerException` right when creating the reference. This is distinct from compile-time checked-exception checking.

## 2. Four Common Forms of Method References

| Form | Meaning | Illustrative example |
| --- | --- | --- |
| `ClassName::staticMethod` | Static method reference | `Parser::parse` |
| `instance::instanceMethod` | Method reference on an existing receiver | `reader::read` |
| `ClassName::instanceMethod` | Unbound method reference; receiver becomes a SAM parameter | `String::length` |
| `ClassName::new` | Constructor reference | `InputStreamReader::new` |

All four forms are subject to target-type checking. If the actual invocation represented by the reference expression can throw a checked exception that the SAM does not permit, **compilation fails**, even if the method reference looks concise or is never called in the program.

For example, `String::length` matches `Function<String, Integer>` via boxing from `int` to `Integer`, because `String.length()` declares no checked exceptions. Conversely, a factory with `throws IOException` cannot automatically be used as a `Function<String, Resource>` if `Function.apply` does not allow checked exceptions.

## 3. What Role Does the SAM's `throws` Clause Play?

A functional interface must have exactly one abstract method under Java's rules; that method provides the functional signature that the method reference will implement.

Two different interfaces:

```java
@FunctionalInterface
interface PlainAction {
    void run();
}

@FunctionalInterface
interface CheckedAction {
    void run() throws java.io.IOException;
}
```

These are **two complete interfaces**, without `main`. If a method declares `throws IOException`, it can fit `CheckedAction`, but it does not fit `PlainAction` merely because both interfaces name their method `run()`.

The set of checked exceptions that the method reference can throw must fall within the types permitted by the SAM's declaration. The rule uses **assignability / subtype** relationships:

- Referenced method `throws FileNotFoundException`; SAM `throws IOException` → **valid**, because `FileNotFoundException extends IOException`.
- Referenced method `throws IOException`; SAM `throws Exception` → **valid**, because `IOException extends Exception`.
- Referenced method `throws Exception`; SAM only `throws IOException` → **invalid**, because `Exception` is too broad.
- Referenced method `throws IOException, SQLException`; SAM only `throws IOException` → **invalid**, because `SQLException` is not a subtype of `IOException`.
- Referenced method only throws `RuntimeException` or `Error` → not required to be declared in the SAM.

**Do not assume that "having a SAM with some similarly named exception type" is enough**; every relevant checked exception from the target method must be permitted under the compatibility rules.

## 4. Complete Java 17 Example: Same Method, Compatible and Incompatible SAMs

Save **`ThrowsCompatibilityDemo.java`**:

```java
import java.io.IOException;

public class ThrowsCompatibilityDemo {
    @FunctionalInterface
    interface CheckedAction {
        void run() throws IOException;
    }

    static void load() throws IOException {
        System.out.println("Đang tải");
        throw new IOException("Không đọc được cấu hình");
    }

    public static void main(String[] args) {
        CheckedAction action = ThrowsCompatibilityDemo::load;
        System.out.println("Reference đã tạo");

        try {
            action.run();
        } catch (IOException e) {
            System.out.println("Đã bắt: " + e.getMessage());
        }

        System.out.println("Kết thúc");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 ThrowsCompatibilityDemo.java
java ThrowsCompatibilityDemo
```

**Exact stdout**:

```text
Reference đã tạo
Đang tải
Đã bắt: Không đọc được cấu hình
Kết thúc
```

Explanation:

1. `CheckedAction.run() throws IOException` is the target's contract.
2. `ThrowsCompatibilityDemo.load() throws IOException` is permitted by that contract.
3. Assigning `ThrowsCompatibilityDemo::load` only creates an executable expression according to the SAM; it does not call `load`, so the line `Đang tải` does not appear yet.
4. When `action.run()` is called, the `load` method runs and throws `IOException`.
5. The caller must catch or declare the checked `IOException` at the call site of `action.run()`.

If you replace the assignment line with:

```java
Runnable action = ThrowsCompatibilityDemo::load;
```

this is an **intentional counterexample that does not compile**. `Runnable.run()` does not declare `throws IOException`. The method reference is rejected because `load`'s checked exception is not permitted by the SAM. Java **does not create a `Runnable` and silently swallow the error**.

## 5. `Runnable`, `Supplier`, `Function`, and `Consumer` Do Not Allow Checked Exceptions

Common JDK functional interfaces are typically used where an API wants a simple callback:

| Interface | SAM | Checked `throws` clause |
| --- | --- | --- |
| `Runnable` | `void run()` | No |
| `Supplier<T>` | `T get()` | No |
| `Function<T,R>` | `R apply(T t)` | No |
| `Consumer<T>` | `void accept(T t)` | No |
| `Predicate<T>` | `boolean test(T t)` | No |
| `BiFunction<T,U,R>` | `R apply(T t, U u)` | No |
| `Callable<V>` | `V call() throws Exception` | **Yes, Exception** |

A method reference to a method that only throws unchecked exceptions can be valid with non-`throws` interfaces if **all other type elements match**.

The following example is **illustrative code**:

```java
java.util.function.Supplier<Integer> supplier = String::length;
```

This line is **invalid**, but **not because of `throws`**: `String::length` is an **unbound instance method** that needs a `String` receiver, whereas `Supplier.get()` takes no parameters. The right way:

```java
java.util.function.Function<String, Integer> length = String::length;
```

This example highlights that a method reference must satisfy **both the parameter/return signature and checked exceptions**. When diagnosing compile errors, do not blame everything on `throws`.

## 6. `Callable<V>` Allows the Broad Checked Exception `Exception`

`java.util.concurrent.Callable<V>` has the SAM:

```java
V call() throws Exception;
```

Therefore, a method `String read() throws IOException` can be referenced via `Callable<String>`, because `IOException` is a subtype of `Exception`.

Save **`CallableReferenceDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.Callable;

public class CallableReferenceDemo {
    static String readData() throws IOException {
        System.out.println("Đọc dữ liệu");
        return "OK";
    }

    public static void main(String[] args) {
        Callable<String> callable = CallableReferenceDemo::readData;

        try {
            System.out.println("Kết quả: " + callable.call());
        } catch (Exception e) {
            System.out.println("Lỗi: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 CallableReferenceDemo.java
java CallableReferenceDemo
```

**Exact stdout**:

```text
Đọc dữ liệu
Kết quả: OK
```

At the assignment site, `Callable<String>` accepts a method declared with `throws IOException`. However, at the point of **calling through the `Callable<String>` variable**, the signature `call() throws Exception` is the static signature the caller sees. Hence the example catches `Exception` rather than only `IOException`.

**Key distinction:**

- **Checking the method reference assignment:** `throws IOException` fits within `throws Exception` → valid.
- **Checking the SAM call:** `call()` is declared `throws Exception` → the caller must satisfy that broad contract.

This does not mean `readData` suddenly becomes capable of throwing any `Exception`. It only means that when viewed through the target type `Callable`, the compiler checks calls against the target interface's signature.

## 7. Narrowing the Contract in a Custom Functional Interface

If you want to keep a more precise checked-exception obligation than `Callable`, you can define your own SAM:

```java
@FunctionalInterface
interface IoSupplier<T> {
    T get() throws java.io.IOException;
}
```

Standalone example **`IoSupplierDemo.java`**:

```java
import java.io.IOException;

public class IoSupplierDemo {
    @FunctionalInterface
    interface IoSupplier<T> {
        T get() throws IOException;
    }

    static String obtain() throws IOException {
        throw new IOException("Nguồn chưa sẵn sàng");
    }

    static String use(IoSupplier<String> supplier)
            throws IOException {
        return supplier.get();
    }

    public static void main(String[] args) {
        IoSupplier<String> supplier = IoSupplierDemo::obtain;

        try {
            System.out.println(use(supplier));
        } catch (IOException e) {
            System.out.println("I/O: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 IoSupplierDemo.java
java IoSupplierDemo
```

**Exact stdout**:

```text
I/O: Nguồn chưa sẵn sàng
```

`IoSupplier.get() throws IOException` is more precise than `Callable.call() throws Exception` if the API only needs to describe I/O errors. It helps callers handle the exact checked exception type without unnecessarily widening to `Exception`.

Note: there is no need to create a new functional interface for every simple method; only do so when the interface represents a genuinely needed **callback contract with checked failure**.

## 8. Comparison with Lambdas: Same `throws` Rules

Two ways to write it:

```java
IoSupplier<String> first = DataStore::read;
IoSupplier<String> second = () -> DataStore.read();
```

This is **illustrative code**, assuming `DataStore.read() throws IOException` and `IoSupplier<T>` has `get() throws IOException`. For checked-exception compatibility, both expressions must satisfy the SAM contract.

A lambda is not a "backdoor" to bypass the rules. The following form **intentionally does not compile** if `DataStore.read() throws IOException`:

```java
java.util.function.Supplier<String> s =
        () -> DataStore.read();
```

Reason: the lambda body contains a call that can throw checked `IOException`, yet `Supplier.get()` declares no checked exceptions. The method reference form:

```java
java.util.function.Supplier<String> s = DataStore::read;
```

also **does not compile** for the exact same `throws` reason. Syntactic differences do not alter checked-exception obligations.

However, a lambda **can** contain a `try/catch` to handle or translate the error:

```java
java.util.function.Supplier<String> s = () -> {
    try {
        return DataStore.read();
    } catch (IOException e) {
        return "fallback";
    }
};
```

This is **illustrative code**, with a fallback only valid when the business contract genuinely allows it. This snippet fits `Supplier` because **no checked `IOException` escapes from the lambda body**.

Choose between a method reference and a lambda based on clarity, not on the assumption that `::` has "looser" exception rules.

## 9. Static Method References with Checked Exceptions

Syntax:

```java
TargetAction action = UtilityClass::operation;
```

When `UtilityClass.operation()` is static, Java checks its compatibility with `TargetAction`'s SAM, including checked exceptions.

A standalone Java 17 example **`StaticReferenceDemo.java`**:

```java
import java.io.IOException;

public class StaticReferenceDemo {
    @FunctionalInterface
    interface Parser {
        int parse(String input) throws IOException;
    }

    static int parsePort(String input) throws IOException {
        int port = Integer.parseInt(input);
        if (port < 1 || port > 65535) {
            throw new IOException("Port ngoài giới hạn");
        }
        return port;
    }

    public static void main(String[] args) {
        Parser parser = StaticReferenceDemo::parsePort;

        try {
            System.out.println("Port: " + parser.parse("8080"));
            System.out.println("Port: " + parser.parse("70000"));
        } catch (IOException e) {
            System.out.println("Lỗi: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 StaticReferenceDemo.java
java StaticReferenceDemo
```

**Exact stdout**:

```text
Port: 8080
Lỗi: Port ngoài giới hạn
```

`Parser.parse` has the same parameter/return types as `parsePort` and permits `IOException`. Catching `IOException` in `main` applies to the call through `parser`.

**An important note:** `Integer.parseInt` can throw `NumberFormatException`, which is unchecked. It can propagate even though `Parser.parse` only declares `throws IOException`. The SAM's `throws` clause does not block unchecked exceptions and does not guarantee that every invalid input turns into an `IOException`.

## 10. Bound Instance Method Reference: `object::method`

A **bound reference** fixes the receiver at the time the expression is created:

```java
ReaderService service = new ReaderService();
CheckedAction action = service::reload;
```

This is **illustrative code**; `ReaderService.reload() throws IOException` is assumed compatible with `CheckedAction.run() throws IOException`.

In this form, the SAM **does not need to take the receiver as an argument**, because the receiver `service` is already chosen. Checked exceptions are evaluated from the target method according to the contract.

Complete example **`BoundReferenceDemo.java`**:

```java
import java.io.IOException;

public class BoundReferenceDemo {
    static class Worker {
        private final String name;

        Worker(String name) {
            this.name = name;
        }

        void execute() throws IOException {
            System.out.println("Worker: " + name);
            throw new IOException("Chưa có dữ liệu");
        }
    }

    @FunctionalInterface
    interface CheckedAction {
        void run() throws IOException;
    }

    public static void main(String[] args) {
        Worker worker = new Worker("A");
        CheckedAction action = worker::execute;

        try {
            action.run();
        } catch (IOException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 BoundReferenceDemo.java
java BoundReferenceDemo
```

**Exact stdout**:

```text
Worker: A
Bắt: Chưa có dữ liệu
```

The `execute` method still declares checked `IOException`, so you cannot switch the target to `Runnable` merely by using `worker::execute`.

### A `null` Receiver Is a Separate Issue from `throws`

With a bound reference `worker::execute`, Java checks the receiver at **method reference evaluation time**. If the receiver is `null`, a `NullPointerException` can occur **before the SAM is ever called**.

This is an unchecked exception, not an `IOException` that needs to be added to the interface's `throws` clause. Do not confuse an error creating a bound reference due to a null receiver with an error raised by the referenced method when the SAM runs.

## 11. Unbound Instance Reference: `Type::instanceMethod`

The unbound form uses **the receiver as the first argument of the SAM**. For example:

```java
java.util.function.Function<String, Integer> length =
        String::length;
```

When `length.apply("abc")` runs, the argument `"abc"` becomes the receiver to invoke `String.length()`. For a method with checked exceptions, the SAM must also declare the ability to throw those checked exceptions.

Java 17 example **`UnboundReferenceDemo.java`**:

```java
import java.io.IOException;

public class UnboundReferenceDemo {
    static class Document {
        private final String name;

        Document(String name) {
            this.name = name;
        }

        String read() throws IOException {
            if ("bad".equals(name)) {
                throw new IOException("Không mở được tài liệu");
            }
            return "Nội dung " + name;
        }
    }

    @FunctionalInterface
    interface Reader {
        String read(Document document) throws IOException;
    }

    public static void main(String[] args) {
        Reader reader = Document::read;
        try {
            System.out.println(reader.read(new Document("good")));
            System.out.println(reader.read(new Document("bad")));
        } catch (IOException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 UnboundReferenceDemo.java
java UnboundReferenceDemo
```

**Exact stdout**:

```text
Nội dung good
Bắt: Không mở được tài liệu
```

Analysis: `Document::read` is not bound to any pre-existing `Document` object. The SAM `Reader.read(Document)` supplies the receiver at invocation time, and permits checked `IOException`.

If you use `Function<Document, String> fn = Document::read;`, Java rejects it because `Function.apply` does not declare `throws IOException`. This is an exception-contract error, even though the parameter and return type match.

## 12. Constructor References Also Check Checked Exceptions

The `Type::new` syntax can instantiate an object through a constructor compatible with the SAM. If the constructor declares a checked exception, **the factory interface's SAM must permit that exception**.

Complete Java 17 example **`ConstructorReferenceDemo.java`**:

```java
import java.io.IOException;

public class ConstructorReferenceDemo {
    static class Connection {
        private final String address;

        Connection(String address) throws IOException {
            if (address.isBlank()) {
                throw new IOException("Địa chỉ trống");
            }
            this.address = address;
        }

        String address() {
            return address;
        }
    }

    @FunctionalInterface
    interface ConnectionFactory {
        Connection open(String address) throws IOException;
    }

    public static void main(String[] args) {
        ConnectionFactory factory = Connection::new;
        try {
            System.out.println("Đã tạo: "
                    + factory.open("db.internal").address());
            factory.open("");
        } catch (IOException e) {
            System.out.println("Lỗi factory: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 ConstructorReferenceDemo.java
java ConstructorReferenceDemo
```

**Exact stdout**:

```text
Đã tạo: db.internal
Lỗi factory: Địa chỉ trống
```

`Connection::new` is compatible with `ConnectionFactory.open(String) throws IOException`. If you write:

```java
java.util.function.Function<String, Connection> factory =
        Connection::new;
```

this is an **intentional counterexample that does not compile** because the constructor `Connection(String) throws IOException`, whereas `Function.apply` does not permit checked exceptions.

**A constructor reference does not invoke the constructor when the reference is assigned.** The constructor runs when `factory.open(...)` is called. Exceptions from the constructor are checked statically at the reference-assignment step and actually thrown at the call step.

## 13. Compatibility via Exception Inheritance Hierarchy

The SAM does not need to declare the exact same exception name. A **valid supertype** can cover the target method's checked exception.

Illustrative example:

```java
static void openSpecific() throws java.io.FileNotFoundException {
    throw new java.io.FileNotFoundException("Không tìm thấy");
}
```

If you have the interface:

```java
@FunctionalInterface
interface GeneralIoAction {
    void run() throws java.io.IOException;
}
```

then `GeneralIoAction action = Example::openSpecific;` (assuming the method is in `Example`) is **valid** because `FileNotFoundException` is a subtype of `IOException`.

The reverse direction is invalid:

```java
@FunctionalInterface
interface SpecificIoAction {
    void run() throws java.io.FileNotFoundException;
}
```

If the referenced method only declares the broader `throws IOException`, Java cannot guarantee that every `IOException` is a `FileNotFoundException`, so a method reference to it is incompatible with `SpecificIoAction`.

**Compile errors are based on declared exceptions and static type analysis, not on which runtime branch throws what in a single test run.**

## 14. Multiple Checked Exceptions Must All Be Covered by the SAM

A method can declare multiple error types:

```java
static void synchronize() throws java.io.IOException,
                                 java.sql.SQLException {
    // ...
}
```

This is an **illustrative method**, with its body omitted because no implementation logic is needed. A compatible SAM:

```java
@FunctionalInterface
interface SyncAction {
    void run() throws java.io.IOException,
                      java.sql.SQLException;
}
```

Or a SAM with `throws Exception` can cover both:

```java
@FunctionalInterface
interface GeneralAction {
    void run() throws Exception;
}
```

However, a SAM with only `throws IOException` is **insufficient** if the referenced method can throw checked `SQLException`. Collapsing into `throws Exception` may be easy to implement, but it forces callers of the SAM to handle/declare a **broader** type. When an API needs callers to distinguish error categories, specific declarations are usually more useful.

A standalone example **`MultipleThrowsReferenceDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultipleThrowsReferenceDemo {
    @FunctionalInterface
    interface SyncAction {
        void run() throws IOException, SQLException;
    }

    static void sync(boolean dbFailure)
            throws IOException, SQLException {
        if (dbFailure) {
            throw new SQLException("DB lỗi");
        }
        throw new IOException("Tệp lỗi");
    }

    public static void main(String[] args) {
        SyncAction io = () -> sync(false);
        SyncAction db = () -> sync(true);

        for (SyncAction action : new SyncAction[] {io, db}) {
            try {
                action.run();
            } catch (IOException e) {
                System.out.println("I/O: " + e.getMessage());
            } catch (SQLException e) {
                System.out.println("SQL: " + e.getMessage());
            }
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 MultipleThrowsReferenceDemo.java
java MultipleThrowsReferenceDemo
```

**Exact stdout**:

```text
I/O: Tệp lỗi
SQL: DB lỗi
```

This snippet uses a **lambda** to pass a fixed `boolean` argument; using a method reference directly would require a SAM with the same parameter list as `sync(boolean)`, e.g., `void run(boolean) throws IOException, SQLException`. The main point is that multiple checked exceptions must still all be covered by the target.

## 15. Method References When the Original Method Has Additional Parameters

A method reference must match the SAM in its parameters. If you want to assign `Demo::sync` directly instead of a lambda with a fixed boolean, you can define:

```java
@FunctionalInterface
interface SyncOperation {
    void run(boolean dbFailure)
            throws java.io.IOException, java.sql.SQLException;
}
```

Then, in a context where `sync(boolean)` belongs to class `Demo`:

```java
SyncOperation operation = Demo::sync;
```

This is **illustrative code**, not a standalone program. Java will check:

- One `boolean` parameter on the SAM maps to `sync(boolean)`.
- The `void` return type is compatible.
- `throws IOException, SQLException` on the SAM covers the checked exceptions of `sync`.

If any of the three conditions is not met, the assignment can fail. **A method reference does not drop parameters on its own**; use a lambda to fix, adapt, or supply additional logic if needed.

## 16. Overloading and Method Reference Resolution

When a class has **overloaded methods**, the compiler looks for a compatible method based on the target type, parameter count, type relationships, and overload resolution rules.

For example:

```java
class Reporter {
    static void report(String text) {
        System.out.println("Text: " + text);
    }

    static void report(Integer code) {
        System.out.println("Code: " + code);
    }
}
```

This is an **illustrative class**, without `main`. The targets:

```java
java.util.function.Consumer<String> a = Reporter::report;
java.util.function.Consumer<Integer> b = Reporter::report;
```

are resolved to the overloads with matching parameter types, not based on `throws`, since neither method declares checked exceptions.

**You cannot overload two methods that differ only by their `throws` clause**:

```java
// Intentionally invalid if placed in the same class:
void process() throws IOException { }
void process() throws SQLException { }
```

Even though the two `throws` lists differ, Java treats two methods with the same name and parameter list as having the same signature for this purpose. Thus, `throws` is not a way to create overload choices.

If you encounter an ambiguous or incompatible method reference, inspect the **target type**, the selected overload, and all checked exceptions of that specific method. Do not assume the compiler will pick an overload just because its `throws` clause "fits" the SAM.

## 17. Generic Functional Interfaces Parameterizing the Exception Type

A useful pattern when a library needs to support many kinds of checked exceptions is parameterizing the exception type:

```java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T input) throws E;
}
```

Here:

- `T` is the input type.
- `R` is the result type.
- `E extends Exception` is the exception type permitted in the contract.
- When `E = IOException` is chosen, the SAM is understood as `R apply(T) throws IOException` under Java's type-checking rules.
- When `E = Exception` is chosen, the SAM permits more kinds of checked exceptions, but the caller's contract is broader.

Standalone Java 17 example **`GenericThrowingFunctionDemo.java`**:

```java
import java.io.IOException;

public class GenericThrowingFunctionDemo {
    @FunctionalInterface
    interface ThrowingFunction<T, R, E extends Exception> {
        R apply(T input) throws E;
    }

    static Integer parseFile(String text) throws IOException {
        if (text.isBlank()) {
            throw new IOException("Không có nội dung");
        }
        return Integer.parseInt(text);
    }

    static <T, R, E extends Exception> R execute(
            ThrowingFunction<T, R, E> fn, T value) throws E {
        return fn.apply(value);
    }

    public static void main(String[] args) {
        ThrowingFunction<String, Integer, IOException> parser =
                GenericThrowingFunctionDemo::parseFile;

        try {
            System.out.println("Số: " + execute(parser, "25"));
            execute(parser, "");
        } catch (IOException e) {
            System.out.println("I/O: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 GenericThrowingFunctionDemo.java
java GenericThrowingFunctionDemo
```

**Exact stdout**:

```text
Số: 25
I/O: Không có nội dung
```

This pattern preserves the specific checked exception via the generic interface and the `execute` method. Because `execute` declares `throws E`, when `E` is `IOException`, the caller still must handle `IOException`.

**A design limitation:** a single `E extends Exception` parameter expresses a group of exceptions well if they can be covered by one type. If a callback throws multiple checked exceptions **that have no useful narrow superclass**, you may need `throws` with multiple specific types, a common domain exception, or a different result contract. A generic exception type does not automatically solve every problem.

## 18. Adapting a Checked Function to `Function`

A standard API such as `Stream.map` accepts `Function`, which does not allow checked exceptions. If you have `ThrowingFunction<T,R,IOException>`, you need to choose an error-conversion or handling policy.

An adapter that converts `IOException` into unchecked `UncheckedIOException` is one option when the contract allows it:

```java
static <T, R> java.util.function.Function<T, R> uncheckedIo(
        ThrowingFunction<T, R, IOException> fn) {
    return value -> {
        try {
            return fn.apply(value);
        } catch (IOException e) {
            throw new java.io.UncheckedIOException(e);
        }
    };
}
```

This is an **illustrative method**, assuming `ThrowingFunction` is already declared; import `java.io.IOException` if not written fully qualified. Using the adapter:

```java
java.util.function.Function<String, Integer> fn =
        uncheckedIo(Parser::parse);
```

This is also **skeleton code**; `Parser.parse(String) throws IOException` is assumed. After conversion:

- `Function.apply` does not declare checked `IOException`.
- If the callback throws `IOException`, the adapter catches it and throws **`UncheckedIOException`** (an unchecked exception).
- `UncheckedIOException.getCause()` preserves the original I/O exception.
- Callers via `Function` do not have to declare `throws IOException`, but they still need a handling strategy if a failure actually occurs.
- Changing the exception type **does not recover automatically** and does not guarantee the operation succeeds.

Do not wrap every `Exception` in `RuntimeException` just to silence the compiler. Choose a conversion that fits the API contract and preserves `cause`.

## 19. Runnable Java 17 Example: Adapter Preserving `cause`

Save **`AdapterReferenceDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.function.Function;

public class AdapterReferenceDemo {
    @FunctionalInterface
    interface IoFunction<T, R> {
        R apply(T value) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(IoFunction<T, R> fn) {
        return value -> {
            try {
                return fn.apply(value);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        };
    }

    static String read(String name) throws IOException {
        if ("bad".equals(name)) {
            throw new IOException("Không đọc được bad");
        }
        return "OK:" + name;
    }

    public static void main(String[] args) {
        Function<String, String> fn =
                unchecked(AdapterReferenceDemo::read);

        System.out.println(fn.apply("good"));
        try {
            fn.apply("bad");
        } catch (UncheckedIOException e) {
            System.out.println("Wrapper: "
                    + e.getClass().getSimpleName());
            System.out.println("Cause: "
                    + e.getCause().getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 AdapterReferenceDemo.java
java AdapterReferenceDemo
```

**Exact stdout**:

```text
OK:good
Wrapper: UncheckedIOException
Cause: Không đọc được bad
```

Thanks to `IoFunction.apply throws IOException`, the method reference `AdapterReferenceDemo::read` is accepted before the adapter converts it to `Function`. `UncheckedIOException` preserves the original `IOException` object in `getCause()`, avoiding loss of the original stack trace and message.

This adapter **shifts the error contract from checked to unchecked**. That is a design choice that should be documented, not an automatic feature of method references.

## 20. Stream API and Lazy Operations

`Stream.map` accepts `Function<? super T, ? extends R>`, and `forEach` accepts `Consumer<? super T>`. Those SAMs **do not declare checked exceptions**.

Therefore, code like:

```java
// Illustrative snippet, intentionally does not compile:
stream.map(Files::readString)
      .toList();
```

if `stream` is a `Stream<Path>` and `Files.readString(Path)` has `throws IOException`, the method reference is incompatible with `Function<Path,String>` due to checked `IOException`. Having the terminal operation `toList()` at the end does not make Java catch the error automatically.

There are clear alternatives:

1. **Read sequentially using a loop with `throws IOException` or `try/catch`** if you want the caller to handle checked I/O.
2. **Use an adapter** converting `IOException` into `UncheckedIOException` with `cause` if the pipeline only suits unchecked exceptions.
3. **Return a stateful result** (e.g., success/error) if each element can fail and the task needs to collect both results and errors.
4. **Handle the error inside a lambda** if there is a genuinely valid fallback for an element.
5. **Separate I/O operations from the pipeline**, when doing so makes the error flow clearer and resource control easier.

A stream pipeline can be **lazy**: many intermediate operations do not run until a terminal operation is invoked. However, checked-exception rules are enforced **right at compile time for the method reference expression**, without waiting for the pipeline to run.

## 21. `Function` or `Callable` Does Not Automatically Create a Retry Policy

Any method reference only describes **invocable behavior**; it does not automatically add retries or compensating actions.

For example:

```java
Callable<String> task = Client::read;
```

this is **illustrative code**: if `Client.read() throws IOException` is a zero-argument static method, `Callable.call() throws Exception` accepts the reference. If `task.call()` later throws `IOException`, whether to retry depends on the calling code.

Do not infer that choosing a broad `throws Exception` SAM means Java "handles errors in the background" for you. If you use `ExecutorService.submit(Callable)`, the asynchronous mechanism may **wrap errors when retrieving the result via `Future.get()`**, such as in `ExecutionException`, but that is the executor/future contract, **not a property of method references or `throws` syntax**.

Callback responsibilities and error-handling policies should be designed at two separate layers: **the target signature** for compile-time validity, and **the caller/framework** for runtime reaction.

## 22. Referenced Methods with a Broad `throws Exception`

If a target method declares `throws Exception`, Java does not infer that it only actually throws `IOException` inside so that it can be assigned to a SAM that only permits `IOException`.

For example:

```java
static void legacyOperation() throws Exception {
    throw new java.io.IOException("I/O lỗi");
}
```

This is an **illustrative method**. Even though the current implementation only throws `IOException`, the static contract of the method is `throws Exception`. Assigning:

```java
IoAction action = Example::legacyOperation;
```

where `IoAction.run() throws IOException` is **invalid** simply because the target method advertises a type that is too broad. In a future version, `legacyOperation` could throw a checked `Exception` other than `IOException` in accordance with its contract.

Reasonable ways to handle this:

- If you own the method, **narrow the `throws` signature** when the contract genuinely allows it.
- If the target permits `Exception`, use a target with `run() throws Exception`.
- If you need to translate error types, write an **adapter/lambda with `try/catch`** and choose explicitly how to preserve or change the contract.
- Do not blindly cast from `Exception` to `IOException`; doing so can raise a `ClassCastException` right inside error handling.

This is the general principle: **the compiler trusts the static contract**, rather than predicting every future runtime behavior of a library.

## 23. A Target SAM Declaring `throws Exception` Does Not Force the Reference to Throw a Checked Exception

The reverse direction is still valid: the target SAM has `throws Exception`, while the referenced method throws **no** checked exceptions.

For example:

```java
@FunctionalInterface
interface Task {
    String run() throws Exception;
}
```

With a method that has no checked exceptions:

```java
static String greeting() {
    return "Xin chào";
}
```

the assignment `Task t = Example::greeting;` is valid. The SAM declares **the set of errors that may be permitted**, not a requirement that an implementation must throw an exception.

However, at the call site `t.run()`, the compiler still sees the **SAM's** `throws Exception`, so the caller must catch/declare `Exception` per the contract. That is the cost of choosing a broad target, even when the concrete implementation is very simple.

Do not force the use of `Callable` just because it is built in if your API needs a specific checked-exception contract to support callers.

## 24. Method References and Unchecked Exceptions

`RuntimeException` and `Error` belong to the unchecked group and are not subject to the catch-or-declare rule. Thus, a method reference can be valid with `Runnable` even if the method can throw `IllegalStateException`.

Standalone example **`UncheckedReferenceDemo.java`**:

```java
public class UncheckedReferenceDemo {
    static void enforce() {
        throw new IllegalStateException("Trạng thái không hợp lệ");
    }

    public static void main(String[] args) {
        Runnable task = UncheckedReferenceDemo::enforce;
        try {
            task.run();
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 UncheckedReferenceDemo.java
java UncheckedReferenceDemo
```

**Exact stdout**:

```text
Bắt: Trạng thái không hợp lệ
```

`Runnable.run()` declares no checked exceptions, yet it does not prevent unchecked `IllegalStateException` from escaping. `main` can still catch the exception to respond meaningfully.

**Do not interpret** using `Runnable` as making all unexpected errors disappear. The target type only specifies checked-exception bounds at compile time; it does not create an automatic `RuntimeException`-catching mechanism.

## 25. `InterruptedException` and Callbacks That Do Not Declare Checked Exceptions

An easy-to-miss case in multithreaded applications:

```java
static void waitForSignal() throws InterruptedException {
    Thread.sleep(100);
}
```

The method reference `SomeClass::waitForSignal` is **not** compatible with `Runnable` because `Runnable.run()` does not allow checked `InterruptedException`.

If the API allows it, design a custom SAM `void run() throws InterruptedException` and let the caller decide how to handle it. When `Runnable` must be used, you typically need a lambda/adapter that handles interruption intentionally:

```java
Runnable task = () -> {
    try {
        waitForSignal();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Tác vụ bị ngắt", e);
    }
};
```

This is **illustrative code inside the class containing `waitForSignal`**. Some waiting APIs such as `Thread.sleep` clear the interrupt status when throwing `InterruptedException`; calling `Thread.currentThread().interrupt()` again is often necessary so the cancellation signal is not lost.

However, **do not apply this wrapper mechanically**: if a framework has its own cancellation policy, follow its contract. The principle is not to swallow `InterruptedException` or turn it into a fake success just to assign a method reference to `Runnable`.

## 26. `Files::readString` and Checking `throws` When Using JDK APIs

Since Java 11, `java.nio.file.Files.readString(Path)` declares `throws IOException` and returns `String`. It can be used in Java 17 with a suitable target:

```java
@FunctionalInterface
interface FileReader {
    String read(java.nio.file.Path path)
            throws java.io.IOException;
}
```

In a context where the interface exists:

```java
FileReader read = java.nio.file.Files::readString;
```

this is **illustrative code**, independent of any specific file at reference-creation time. When calling `read.read(path)`, the program must catch/declare `IOException` because the SAM `FileReader.read(Path)` advertises it.

Conversely:

```java
java.util.function.Function<java.nio.file.Path, String> read =
        java.nio.file.Files::readString;
```

is an **intentional counterexample that does not compile**: the target `Function.apply` does not declare checked `IOException`.

If you need behavior that only reads from a fixed `Path`, you can use the lambda `() -> Files.readString(path)` with `IoSupplier<String>`. A method reference `Files::readString` cannot turn a method taking `Path` into a zero-argument SAM without a mechanism to supply the argument.

## 27. Can You Catch the Exception Outside the SAM Call?

Yes. If the target SAM has checked `throws`, you **catch at the call site**:

```java
IoSupplier<String> supplier = Store::load;

try {
    String value = supplier.get();
    System.out.println(value);
} catch (IOException e) {
    System.out.println("I/O: " + e.getMessage());
}
```

This is **illustrative code**, assuming `IoSupplier<T>.get() throws IOException` and `Store.load() throws IOException`. The outer `catch` wraps **the call `supplier.get()`**, where the exception is actually allowed to escape.

However, you cannot fix an **incompatible** assignment merely by wrapping *the assignment line* in `try/catch`:

```java
try {
    Runnable r = Store::load; // Still a compile error if Store.load() throws IOException.
} catch (IOException e) {
    // Does not make the method reference valid.
}
```

This is an **intentional counterexample that does not compile**. Because `Runnable` does not allow checked exceptions, the compiler rejects the reference before any call is even considered. A `try/catch` around the assignment does not add `throws` to the SAM, and the referenced method is not even called at the assignment line.

**The placement of a handler must match where the checked exception can actually arise and the SAM's contract**, not merely near the `::` syntax.

## 28. Method References and Runtime Polymorphism

Checked-exception analysis is determined from the **static types** of the referenced method and the target SAM. At runtime, however, Java may invoke the **actual overriding implementation** via polymorphism.

For example:

```java
interface Repository {
    String fetch() throws IOException;
}

class MemoryRepository implements Repository {
    public String fetch() {
        return "cache";
    }
}
```

This is **illustrative code**, requiring an import of `IOException`. If a variable has static type `Repository repo = new MemoryRepository();`, the method reference `repo::fetch` is checked against the contract `Repository.fetch() throws IOException`, even though the `MemoryRepository.fetch()` implementation declares no checked exceptions.

This means:

- `IoSupplier<String> supplier = repo::fetch;` is valid.
- `Supplier<String> supplier = repo::fetch;` can be rejected because the static type `Repository` advertises `IOException`.
- If the variable is declared with type `MemoryRepository concrete`, the reference `concrete::fetch` has no checked `IOException` per `MemoryRepository.fetch()`'s signature, so it can be valid with `Supplier<String>`.

**Do not use the knowledge that "at runtime it is always MemoryRepository" to bypass the static type contract.** That is a core part of API design and polymorphism.

## 29. Constructor `throws` and Generic Factories

A generic factory with a checked exception can be expressed with an interface:

```java
@FunctionalInterface
interface Factory<T, E extends Exception> {
    T create(String name) throws E;
}
```

If the constructor is `Resource(String) throws IOException`, you can choose:

```java
Factory<Resource, IOException> factory = Resource::new;
```

This is **illustrative code**, assuming class `Resource` is defined with the appropriate constructor. `E` represents the exception the constructor can throw. Callers invoking `factory.create(name)` must satisfy `throws IOException`.

This is valuable when a framework API has many factories and wants each factory to advertise **one specific checked exception**. If a factory has multiple independent checked exception types, do not force a single-`E` model if it distorts error semantics: choose a target with suitable `throws` or a different abstraction.

## 30. Testing Compatibility with Self-Checking Programs

A useful test should distinguish:

- **Compile-time compatibility:** the method reference assignment must be accepted by the compiler.
- **Runtime behavior:** when the SAM is called, the target method runs and throws/does not throw the expected exception.
- **Checked contract:** the caller must catch/declare at the SAM call site, not merely because the reference was assigned.

Standalone example **`MethodReferenceAssertionsDemo.java`**:

```java
import java.io.IOException;

public class MethodReferenceAssertionsDemo {
    @FunctionalInterface
    interface IoTask {
        void run() throws IOException;
    }

    static void failIo() throws IOException {
        throw new IOException("expected");
    }

    static void failUnchecked() {
        throw new IllegalStateException("unchecked");
    }

    public static void main(String[] args) {
        IoTask checked = MethodReferenceAssertionsDemo::failIo;
        Runnable unchecked = MethodReferenceAssertionsDemo::failUnchecked;

        try {
            checked.run();
            throw new AssertionError("Thiếu IOException");
        } catch (IOException e) {
            if (!"expected".equals(e.getMessage())) {
                throw new AssertionError("Sai I/O message");
            }
            System.out.println("PASS checked");
        }

        try {
            unchecked.run();
            throw new AssertionError("Thiếu unchecked");
        } catch (IllegalStateException e) {
            if (!"unchecked".equals(e.getMessage())) {
                throw new AssertionError("Sai unchecked message");
            }
            System.out.println("PASS unchecked");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 MethodReferenceAssertionsDemo.java
java MethodReferenceAssertionsDemo
```

**Exact stdout**:

```text
PASS checked
PASS unchecked
```

The test uses `AssertionError` to fail explicitly when results are wrong, without depending on the `-ea` flag for the `assert` keyword. Compile-negative tests such as `Runnable r = SomeClass::checkedMethod;` should be kept in a separate test file/project **that is expected not to compile**, rather than mixed into the runnable program above.

## 31. Common Compiler Error Messages

| Symptom | Cause to check | Resolution |
| --- | --- | --- |
| `incompatible thrown types IOException in functional expression` | Method ref has checked `IOException`; SAM does not allow it | Choose a SAM with `throws IOException` or an appropriate catching adapter/lambda |
| `unreported exception IOException; must be caught or declared` | Calling a SAM/lambda block with an unhandled checked exception | Catch at the call site or declare on the enclosing method |
| `invalid method reference` | May be wrong parameters/return type or checked exceptions | Check the entire signature, not only `throws` |
| `unexpected instance method ... found in unbound lookup` | Incorrect bound/unbound receiver usage | Use `object::method`, `Type::method`, or a lambda matching the parameter count |
| `reference to method is ambiguous` | Overloading, parameter types, or target type not clear enough | Clarify target type; replace reference with a lambda with explicit parameter types if needed |
| `bad return type in method reference` | SAM expects a return type incompatible with the target method | Choose a suitable target or a converting lambda |
| `Exception is never thrown in body of corresponding try statement` | Handler catches a checked exception where no matching call exists | Catch at the actual SAM call site or adjust the handler type |
| `cannot infer type-variable(s)` | Generic interface or generic method cannot infer type arguments | Specify type arguments/target type explicitly; ensure exception type compatibility |

**Exact error message wording depends on the compiler/JDK.** The table helps identify problem categories, not a stable list of exact strings to match in automated tools.

An error on a method reference is **not necessarily** caused by `throws`; if a method has a checked exception and also the wrong parameter count, fixing `throws` alone will not be enough.

## 32. Common Misconceptions

### 32.1. "Using `::` automatically turns checked exceptions into unchecked ones."

False. Method references do not create exception wrappers. If you want to change the contract, you must implement an adapter/lambda with an explicit policy.

### 32.2. "Target `Runnable` will swallow all exceptions."

False. `Runnable.run` disallows checked exceptions at compile time, but unchecked exceptions can still escape at runtime.

### 32.3. "`Callable` means all checked exceptions will be caught automatically."

False. `Callable.call() throws Exception` allows errors to escape; the caller or executing framework is still responsible under the contract.

### 32.4. "The compiler inspects the method body so it knows `throws Exception` only throws `IOException`."

Not in normal usage. The broad static signature is the contract that must be respected.

### 32.5. "Wrapping `Supplier s = X::read` in `try/catch` will make it valid."

No. A handler around the assignment line does not change `Supplier.get()` to allow checked `IOException`.

### 32.6. "A method reference fails only because of `throws`."

Not necessarily. Wrong receivers, parameter counts, overloads, and return types also cause errors.

### 32.7. "Declaring a SAM `throws IOException` forces implementations to throw `IOException`."

False. An implementation that throws no checked exceptions is still compatible; callers using the SAM must still satisfy that signature.

### 32.8. "A method reference invokes the method immediately upon assignment."

False in the normal case. The reference is created to be called later; a bound reference with a null receiver has evaluation-time checking rules, but that is not a business-method invocation.

### 32.9. "Checked exceptions from a target method can be ignored inside the Stream API."

False. `Function`/`Consumer` do not allow checked exceptions; choose a different contract or handle/translate the error.

### 32.10. "Every callback needs a very broad `throws Exception`."

No. When possible, keeping the exception set narrow helps callers understand and handle the API. If there is only one kind of I/O, `IoSupplier<T>` with `throws IOException` is usually clearer than an interface with `throws Exception`.

### 32.11. "Unchecked exception means the error is unimportant."

False. Unchecked is only a classification for catch-or-declare; the system must still manage state and errors according to its contract.

### 32.12. "Overloading by `throws` is valid."

False. You cannot create two methods with the same signature differing only in their checked-exception lists.

## 33. Self-Check Questions

**Question 1.** Can the method `static void load() throws IOException` be assigned directly to `Runnable` using a method reference?  
**Answer:** No. `Runnable.run()` does not allow checked `IOException`.

**Question 2.** Can `load` be assigned to `CheckedAction.run() throws IOException`?  
**Answer:** Yes, provided parameters and return type are also compatible.

**Question 3.** Is `Callable<String> task = Source::read` valid if `read() throws IOException` and returns `String`?  
**Answer:** Yes. `IOException` is a subtype of `Exception`, which is permitted by `Callable.call()`.

**Question 4.** When calling `task.call()` via `Callable<String>`, what checked type must the caller consider?  
**Answer:** Under the static contract `Callable.call() throws Exception`, the caller must catch/declare `Exception` (or handle it appropriately).

**Question 5.** Is assigning `String::length` to `Supplier<Integer>` valid?  
**Answer:** No. An unbound reference needs the `String` receiver as a SAM parameter; `Supplier.get()` has no parameters.

**Question 6.** Is assigning `String::length` to `Function<String,Integer>` valid?  
**Answer:** Yes. The `String` receiver is the input, and the `int` result can be boxed to `Integer`.

**Question 7.** Is a method with `throws FileNotFoundException` compatible with a SAM having `throws IOException`?  
**Answer:** Yes; `FileNotFoundException` is a subclass of `IOException`.

**Question 8.** Is a method with `throws Exception` compatible with a SAM having only `throws IOException`?  
**Answer:** No, because `Exception` is broader than `IOException`.

**Question 9.** Can the constructor `Resource(String) throws IOException` be assigned directly via `Resource::new` to `Function<String,Resource>`?  
**Answer:** No. `Function.apply` does not allow checked `IOException`.

**Question 10.** Is a method reference to a method with two checked exceptions `IOException` and `SQLException` compatible with a SAM having only `throws IOException`?  
**Answer:** No. `SQLException` is not a subtype of `IOException`.

**Question 11.** Can a method reference to a method that may throw `IllegalStateException` be used with `Runnable`?  
**Answer:** Yes, if other signature elements match; unchecked exceptions do not require checked declarations.

**Question 12.** If a method reference is rejected by the compiler for `Supplier`, does wrapping the assignment line in `try/catch(IOException)` fix it?  
**Answer:** No. `Supplier.get` still declares no checked exceptions.

**Question 13.** When should you use a lambda instead of a method reference to handle checked exceptions?  
**Answer:** When you need `try/catch`, a fallback, error translation with a cause, extra arguments, or combined logic that `::` cannot express directly.

**Question 14.** Why can `try/catch` inside a lambda allow using `Supplier`?  
**Answer:** Because the lambda can handle or translate the checked exception so that no checked exception is thrown out of the SAM execution.

**Question 15.** Does `@FunctionalInterface interface Task { void run() throws IOException; }` require every implementation to actually throw `IOException`?  
**Answer:** No. `throws` permits throwing it; it does not require it.

**Question 16.** Can two methods be overloaded differing only in `throws IOException` and `throws SQLException`?  
**Answer:** No. The `throws` list does not participate in creating distinct overload signatures.

**Question 17.** Is a reference `repo::fetch` on a variable of type `Repository` declaring `throws IOException` checked differently from a variable of an overriding implementation type that declares no checked errors?  
**Answer:** It can differ, because the static type of the receiver determines the visible method and its checked-exception contract at the reference site.

**Question 18.** When using an `UncheckedIOException` adapter, is it still a checked I/O exception for the `Function` caller?  
**Answer:** Not in the signature; `UncheckedIOException` is unchecked, though `getCause()` still holds the original `IOException` and the caller/framework must decide how to handle it.

**Question 19.** Is `Stream.map(Files::readString)` on a `Stream<Path>` directly valid?  
**Answer:** No, because `Files.readString` has checked `IOException` whereas `map`'s `Function` does not allow checked exceptions.

**Question 20.** Does a `NullPointerException` caused by a null receiver when evaluating a bound method reference require adding `throws`?  
**Answer:** No. That is an unchecked exception, distinct from the checked exceptions that the target method may throw when the SAM is called.

## 34. Checklist When Reviewing Method References with `throws`

Before assigning `Type::method` or `object::method` to a functional interface, check:

1. **What is the target functional interface?** Identify the exact SAM and its signature.
2. **What `throws` does the SAM have?** `Runnable`/`Function` are not like `Callable` or custom interfaces.
3. **What checked exceptions does the referenced method have statically?** Read the selected signature; do not guess from a single run.
4. **Are all checked exceptions permitted by the target?** Check subtype/supertype relationships.
5. **Are there multiple checked exceptions?** Do not overlook a second type just because the first one matches.
6. **Which form of method reference is it?** Static, bound, unbound, or constructor.
7. **Do parameter count, receiver, and return type match?** Do not check only `throws`.
8. **Are there overloaded methods?** Ensure the target type is clear enough to select the overload.
9. **Is there a generic exception type parameter?** Choose an appropriate type argument `E`, avoiding falling back to an overly broad `Exception` if unnecessary.
10. **If using `Stream`/`Function`/`Consumer`, is an adapter needed?** Do not swallow errors or fake success.
11. **Does the adapter preserve `cause` when converting to unchecked?** Use a wrapper with an appropriate cause.
12. **Which layer handles the error ultimately?** Caller, controller, job runner, or framework.
13. **Is `InterruptedException` involved?** Respect interruption/cancellation semantics.
14. **Is there a risk of a `null` receiver with a bound reference?** It is evaluated at reference creation time.
15. **Is the error tested at runtime by invoking the SAM?** Successful assignment does not prove successful behavior.
16. **Are there compile-negative tests for forbidden assignments?** Keep them separate from runnable examples to avoid breaking the build.
17. **Does the API documentation clearly state checked/unchecked exceptions and error semantics?** Do not rely solely on the interface name.
18. **Are you creating a new interface just to avoid a local compile error?** Consider the long-term contract before expanding the API.

## 35. Summary

**A method reference must be compatible with the target functional interface's `throws` clause**, not only with its parameter list and return type. A method declared with `throws IOException` can be referenced via `IoSupplier<T>` with `get() throws IOException` or via `Callable<T>` with `call() throws Exception`, but not directly via `Supplier<T>`, `Function<T,R>`, or `Runnable`, which declare no checked exceptions.

The actual check point is **the static signatures of the method and SAM**. Java does not automatically catch, retry, or convert checked exceptions when it sees `::`. Bound, unbound, static, and constructor references must all obey this rule; method overloading and generic type inference can make the selection step more complex.

When standard APIs do not permit checked exceptions, the right options are: **define a callback with an appropriate `throws` clause, catch and handle inside a lambda, convert to an unchecked wrapper preserving `cause` per contract, or use a stateful result type**. Do not swallow errors just to compile, and do not force a broad `throws Exception` if callers need a specific contract.

Shortest takeaway: **"`::` changes how a call is expressed, not Java's checked-exception rules."**
