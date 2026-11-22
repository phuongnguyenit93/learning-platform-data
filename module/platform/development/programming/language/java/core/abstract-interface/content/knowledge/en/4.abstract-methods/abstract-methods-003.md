# Abstract Methods in Java: Parameters, Return Type, and the throws Clause

## 1. Three Components That Make Up a Method's Contract

An `abstract` method declares **what a subclass or implementing class must provide** without having a method body. Alongside the method name, the declaration specifies three key aspects:

- **Parameter list**: the data that the caller must pass in, in a specified order and types.
- **Return type**: the result type that the caller is allowed to receive (or `void` if no value is returned).
- **`throws` clause**: the checked exceptions that the call may need to handle or declare further.

Example declaration in an abstract class:

~~~java
import java.io.IOException;

abstract class DocumentStore {
    public abstract CharSequence load(String id, int version) throws IOException;
}
~~~

In this declaration, `id` is a `String`, `version` is an `int`, the result is a `CharSequence`, and `IOException` is the declared checked exception. The `;` terminates the declaration; an abstract method **must not have a `{ ... }` body**.

The same idea in an interface:

~~~java
import java.io.IOException;

interface DocumentStore {
    CharSequence load(String id, int version) throws IOException;
}
~~~

A regular method declared in an interface as shown above is implicitly `public abstract` (which can be written explicitly). When implemented, the corresponding method must be `public`. Conversely, an abstract class can declare an abstract method as `public`, `protected`, or package-private, depending on the API design. An abstract method cannot simultaneously be `private`, `static`, or `final`: those modifiers prevent overriding.

## 2. Parameters: Types, Order, and Overridability

### 2.1. Formal Parameters and Actual Arguments

In the declaration `load(String id, int version)`, `id` and `version` are **formal parameters**. In the call `store.load("manual", 2)`, `"manual"` and `2` are **arguments**. The caller must supply arguments matching the types, order, and number of parameters; Java checks this at compile time.

Parameter names improve code readability, but they **do not determine overriding**. For example, the declaration `process(String input, int count)` can be implemented as `process(String text, int times)` because the two type lists still correspond.

Java passes parameters by **value**: for primitive types, the method receives a copy of the value; for reference types, the method receives a copy of the reference value. Therefore, it is possible to modify the state of the mutable object that the references both point to, but reassigning the parameter does not make the reference variable at the call site point to a new object.

### 2.2. Key Rules When Overriding

When implementing an abstract method, the overriding method must have a matching name and parameter type list according to Java's method signature/subsignature rules. For examples without generics, consider that **the number, order, and types of parameters must remain unchanged**:

~~~java
abstract class MessageFormatter {
    abstract String format(String content, int width);
}

class PlainFormatter extends MessageFormatter {
    @Override
    String format(String text, int width) {
        return text.trim();
    }
}
~~~

`@Override` causes the compiler to verify that this is genuinely an override. If you accidentally change `String` to `Object`, or swap the order of parameters, the declaration can become a different **overload**, while the original abstract method remains unimplemented. A concrete subclass in that situation will not compile.

Additional rules:

- **Renaming parameters**: allowed; parameter names are not part of the method signature.
- **Adding/removing/changing parameter types**: cannot substitute for the original abstract method; may create an overload.
- **`String...` (varargs)**: may only be placed on the last parameter; at the array type level, `String...` corresponds to `String[]`.
- **`final` on a parameter**: only prevents reassigning the parameter variable inside the method body; it does not alter the override contract.
- **Generics**: override rules additionally involve the concepts of subsignature and type erasure; do not assume that every syntactic difference in generic parameters is a valid overload.

In particular, **the return type and `throws` do not participate in distinguishing two overloaded methods**. There cannot be two methods with the same name and the same parameter list that differ only in return type or `throws`.

## 3. Return Type: Contract and Covariance

The return type determines what the caller can use after the call. A method with a return type other than `void` must return an expression of a compatible type on every execution path that completes normally; a `void` method does not return a value.

When overriding an abstract method:

| Original method return type | Type in the overriding method | Result |
| --- | --- | --- |
| `int` | `int` | Valid |
| `int` | `long` | Invalid (primitive types are not automatically widened when overriding) |
| `void` | `void` | Valid |
| `void` | `String` | Invalid |
| `Number` | `Integer` | Valid: reference subtype, **covariant return** |
| `CharSequence` | `String` | Valid: `String` implements `CharSequence` |
| `String` | `Object` | Invalid: broader return type |

Illustrative example (independent of the `Main` program in the later section):

~~~java
abstract class Metric {
    public abstract Number measure(String input);
}

class LengthMetric extends Metric {
    @Override
    public Integer measure(String input) {
        return input.length();
    }
}
~~~

The subclass can return `Integer` because it is a subtype of `Number`. A caller viewing the variable through the `Metric` type still has a static contract of `Number`, while code inside `LengthMetric` specifically knows the type `Integer`.

With generics, the compiler also applies return-type-substitutability rules; sometimes compatibility requires considering generic types or produces unchecked warnings. Do not rely on arbitrary casts to bypass declaration errors: design the return type properly from the original contract.

## 4. The throws Clause: What Is Allowed to Be Thrown?

### 4.1. `throws` Is a Declaration, While `throw` Is an Action

`throws IOException` belongs in the **method declaration**, informing the compiler and the caller that the operation may complete with this checked exception. Inside the **method body**, the statement `throw new IOException("...")` actually throws an exception.

~~~java
import java.io.IOException;

abstract class FileSource {
    abstract String read(String path) throws IOException;
}
~~~

There is no method body to throw an exception here, yet the declaration still constrains how the caller handles it. A method can list multiple checked exception types separated by commas, for example `throws IOException, java.text.ParseException`, if the contract genuinely needs both.

**Checked exceptions** such as `IOException` and `ParseException` must be caught with `try/catch` or declared further with `throws` on the calling method (for the checked exceptions that may be thrown). **Unchecked exceptions** are `RuntimeException` along with its subclasses and `Error` along with its subclasses; Java does not require declaring or catching these types. You can include an unchecked exception in `throws` to document the API, but doing so creates no additional obligation for the caller to catch it.

You should not declare `throws Exception` indiscriminately: an overly broad type obscures specific error cases and forces callers to handle errors too generically. Do not declare a checked exception merely as a "fallback list" if the API does not need that contract.

### 4.2. throws Constraints When Overriding

An overriding method may:

1. Keep the declared checked exceptions unchanged.
2. Declare **narrower checked types** (subtypes of the checked types permitted by the overridden method).
3. Omit the `throws` clause altogether if the implementation does not throw checked exceptions.
4. Throw or declare appropriate unchecked exceptions regardless of the original declaration, though the API should document meaningful cases.

An overriding method **must not broaden** the list of checked exceptions with a wider or completely new checked type compared to the contract of the overridden method.

Valid example:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

abstract class Resource {
    abstract String open(String path) throws IOException;
}

class MissingResource extends Resource {
    @Override
    String open(String path) throws FileNotFoundException {
        throw new FileNotFoundException(path);
    }
}

class FixedResource extends Resource {
    @Override
    String open(String path) {
        return "constant";
    }
}
~~~

`FileNotFoundException` is a subtype of `IOException`; meanwhile, `FixedResource` omits `throws` because its implementation does not need to throw a checked exception.

An **invalid, intentionally non-compiling** example:

~~~java
import java.io.IOException;

abstract class Job {
    abstract void execute() throws IOException;
}

class InvalidJob extends Job {
    @Override
    void execute() throws Exception { // ERROR: Exception is broader than IOException
    }
}
~~~

Although both are checked exceptions, `Exception` is broader than `IOException`, so Java rejects that override. If the base class declares no checked exception, the subclass cannot add `throws IOException` on its own for the same overriding method.

### 4.3. The Caller Sees the Static Type, Not Just the Implementation

If a variable is declared with an interface or abstract class type featuring `throws IOException`, calls made through that variable are still governed by the checked exception contract, **even when the concrete object overrides it with a method that declares no `throws`**. The compiler checks based on the method declaration selected according to the static type at the call site.

For example, if `Resource resource = new FixedResource();`, then `resource.open("x")` must still be placed inside a `try/catch` or the calling method must declare `throws IOException`; whereas `new FixedResource().open("x")` does not require that.

## 5. Java 17+ Example: Connecting All Three Parts of the Contract

The following example combines an interface, an abstract class, a parameter list, a return type, `throws`, `throw`, and exception handling. Save everything to the file **Main.java**.

~~~java
import java.io.IOException;

interface Reader {
    String read(String id) throws IOException;
}

abstract class BaseReader implements Reader {
    protected abstract int sizeOf(String text);

    protected String prefix() {
        return "data:";
    }
}

final class MemoryReader extends BaseReader {
    @Override
    public String read(String id) throws IOException {
        if (id == null || id.isBlank()) {
            throw new IOException("invalid id");
        }
        return prefix() + id;
    }

    @Override
    protected int sizeOf(String text) {
        return text.length();
    }
}

public class Main {
    public static void main(String[] args) {
        BaseReader reader = new MemoryReader();

        try {
            String text = reader.read("notes");
            System.out.println(text);
            System.out.println(reader.sizeOf(text));
            reader.read("");
        } catch (IOException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
    }
}
~~~

Compile and run (JDK 17 or later):

~~~text
javac -encoding UTF-8 Main.java
java Main
~~~

Expected output:

~~~text
data:notes
10
caught: invalid id
~~~

Explanation:

- `Reader.read(String id)` declares **one parameter of type `String`**, a `String` result, and `throws IOException`; this is the interface's contract.
- `BaseReader` is an abstract class, so it is permitted to leave `read` unimplemented and add its own abstract method `sizeOf(String)` with a return type of `int`.
- `MemoryReader` is a concrete class: it overrides both methods. `read` uses `public` access matching the method from the interface; `sizeOf` keeps `protected`.
- When `id` is empty, `read` actually throws `IOException` using `throw`. The `catch` block handles the exception and prints the message.
- `"data:notes"` has 10 characters. The call `reader.read("")` transfers control to `catch`, so there is no fourth output line.

## 6. Compatibility Checklist When Implementing

| Component | Requirement when overriding an abstract method | Common mistake |
| --- | --- | --- |
| Name + parameters | Match the method signature/subsignature; keep the appropriate count, order, and types | Changing `String` to `Object` and thinking it is an override |
| Parameter names | Can be changed | Mistaking names as part of the signature |
| Return type | Same `void`/primitive type; reference types may be covariant per Java rules | Changing `int` to `long`, or `String` to `Object` |
| Checked `throws` | Keep unchanged, narrow, or omit; do not add checked types exceeding the original contract | Changing `IOException` to `Exception` |
| Unchecked exceptions | Not governed by the checked `throws` narrowing rule | Assuming `RuntimeException` must be declared |
| Access level | Do not reduce accessibility when overriding | Implementing an interface method as `protected` |
| Method body | Abstract declaration ends with `;`; concrete implementation has a body | Putting `{ ... }` after `abstract` or missing the override |
| `@Override` | Should be used so the compiler checks intent | Mistyping parameters, causing an unintended overload |

## 7. Misconceptions to Avoid

**Confusing overloading and overriding.** Two methods with the same name but different parameter types or order are overloads. Writing an additional overload does not fulfill the obligation to implement an existing abstract method. Attach `@Override` and fix the compiler error rather than removing the annotation.

**Mistaking `throws` for a promise to always throw an error.** `throws IOException` allows the corresponding checked error condition to propagate outward; it does not require an exception to be thrown on every run, nor does it require every implementing class to repeat the same `throws` clause.

**Mistaking the return type as part of an overload signature.** You cannot handle two behaviors using two methods that differ only in `String`/`Object` as the return value. If you need two different operations, change the name or parameter list according to a clear design.

**Narrowing the access level of an interface method.** A declaration `String read(String id);` in an interface is implicitly `public abstract`. An implementing class must declare `public String read(String id)`; it cannot use package-private or `protected`.

**Overlooking the caller's static type.** Even if a concrete class omits `throws`, a call through a parent-type variable is still checked against the parent's declaration. When designing an API, meaningful checked exceptions should be included in the shared contract from the start.

## 8. Self-Check

1. Can a method `abstract Number evaluate(String text) throws IOException;` be overridden by `Integer evaluate(String input)`? **Yes** (assuming a valid access level): `Integer` is a covariant return type, parameter names do not matter, and `throws` can be omitted.
2. Can you change the parameter to `Object input` and use `@Override`? **No**, because this is no longer the same method under standard signature rules; if the concrete subclass has not implemented `evaluate(String)`, it will fail to compile.
3. Can you change `throws IOException` to `throws Exception`? **No**, because the checked exception on the override is broader than the original contract.
4. Is it necessary to catch `IOException` when calling through a parent-type reference whose declaration includes `throws IOException`? **Yes**, or continue declaring `throws` on the calling method, regardless of whether the concrete implementation actually throws an error.

When reading an abstract declaration, identify **inputs**, **result**, and **checked exceptions** separately; when implementing it, verify them along with the access level using `@Override`. That is how to keep the polymorphism contract consistent between the caller and every subclass.
