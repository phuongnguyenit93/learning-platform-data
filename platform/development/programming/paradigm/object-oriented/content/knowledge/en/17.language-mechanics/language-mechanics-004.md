# Static types, dynamic types, and type checking in Java

> **Topic:** OOP → Language Mechanics → Static types, dynamic types, and type checking.  
> **Goal:** Distinguish *statically typed* from *dynamically typed* languages; understand **compile-time types** versus **actual runtime object classes**; explain why Java combines static type checking with dynamic polymorphism; identify when runtime checks are needed; and handle generic-type limitations.

## 1. What does “type” refer to?

A **data type** describes the values an expression may represent and the operations permitted on it. Java has primitive types such as `int`, `boolean`, and `double`, and reference types such as `String`, `List<String>`, `User`, or the `PaymentService` interface.

A type system prompts at least three distinct questions:

1. **What is the expression/variable's compile-time type?** Java uses it to check assignments, method calls, operators, and most generic constraints.
2. **What is the actual class of the referenced object at runtime?** A variable with an interface static type can refer to different implementations.
3. **What checks remain necessary at runtime?** Downcasts, array writes, input validation, *reflection*, and many business constraints can only be confirmed during execution.

The terms “static/dynamic” can describe either **type checking** or **method dispatch**, which are different concepts. Java uses **static type checking** but supports **dynamic dispatch** for overridden instance methods.

## 2. Statically typed and dynamically typed languages

In a **statically typed** language, expression types are analyzed and many type relationships are checked **before execution**. Java belongs to this category: incompatible assignments and calls are rejected at compilation in ordinarily compiled source code.

In **dynamically typed** languages, variable names are generally not tied to one declared type as in Java; more operations are checked **during execution**. Python and JavaScript are familiar examples. Dynamic typing does not mean “no types”: values still have types, and unsupported operations can fail at runtime.

| Criterion | Java (static typing) | Python/JavaScript (dynamic typing, broadly) |
|---|---|---|
| Checks before execution | Compiler checks many expression, assignment, and method-call types | Many type-related mistakes appear only when affected code executes |
| Reassignment | Local variables have fixed types; new values must be compatible | Names may be successively bound to values of different types |
| Polymorphism | Yes: an interface variable can reference different implementations | Achievable through language-specific mechanisms |
| Runtime failures | Still possible: `ClassCastException`, `ArrayStoreException`, invalid input, etc. | Unsupported operations on values can still fail |
| Tooling | `javac` performs compile-time checks | Optional type checkers/linters exist; ecosystem policies vary |

A short syntax comparison:

~~~java
// Java: kiểu của biến được xác định tại compile time.
Object value = "hello";
value = 123; // Hợp lệ vì cả String và Integer đều là Object.

// String name = "hello";
// name = 123; // LỖI BIÊN DỊCH: không gán int cho String.
~~~

~~~python
# Python: tên value lần lượt trỏ tới các giá trị khác kiểu.
value = "hello"
value = 123
# Một thao tác không được đối tượng hỗ trợ có thể báo lỗi khi chạy.
~~~

Java allowing `Object value` to hold first a `String` and later an `Integer` **does not make Java dynamically typed**. The **variable's type** remains `Object`; operations remain limited to the `Object` API until a valid cast or type check.

**Avoid overgeneralizing:** “Static typing” does not mean “every type error is caught at compile time,” and “dynamic typing” does not mean “errors only occur at runtime.” Analysis tools, annotations, optional type systems, and runtime checks can be combined.

## 3. From Java source to runtime

~~~mermaid
flowchart TD
    A["Mã nguồn .java"] --> B["javac: phân tích cú pháp, tên và kiểu"]
    B --> C{"Ràng buộc kiểu tĩnh hợp lệ?"}
    C -->|Không| D["Lỗi biên dịch: không sinh chương trình hợp lệ"]
    C -->|Có| E["Bytecode .class"]
    E --> F["JVM tải và xác minh bytecode"]
    F --> G["Chạy chương trình"]
    G --> H["Runtime checks: cast, array store, input..."]
    G --> I["Dynamic dispatch: chọn implementation override"]
    H --> J["Kết quả hoặc lỗi runtime"]
    I --> J
~~~

The Java compiler does more than “check for matching method names”: it considers expression types, accessibility, overload resolution, subtypes, generic constraints, and other language rules.

The JVM performs **bytecode verification** to enforce safety constraints on loaded bytecode. This does not replace business-data validation, access authorization, or application logic. Runtime still resolves actual object classes and verifies relevant casts.

## 4. Variables' static types and objects' runtime classes

Consider two classes implementing the same interface:

~~~java
interface Message {
    String render();
}

final class EmailMessage implements Message {
    @Override
    public String render() {
        return "[EMAIL] Thông báo đơn hàng";
    }

    public String addressDomain() {
        return "example.com";
    }
}

final class SmsMessage implements Message {
    @Override
    public String render() {
        return "[SMS] Thông báo đơn hàng";
    }
}
~~~

This code declares:

~~~java
Message msg = new EmailMessage();
~~~

- **Static type of the variable expression `msg`**: `Message`. The compiler permits `msg.render()` because `Message` declares that method.
- **Actual class of the currently referenced object**: `EmailMessage`. The JVM runs `EmailMessage.render()`.
- `msg.addressDomain()` **does not compile** because `Message` does not expose `addressDomain()`, even though the actual object has it.
- When assigning `msg = new SmsMessage()`, **the variable's static type remains `Message`**, but it now refers to an `SmsMessage`.

Related concepts:

| Concept | Determined when | Example |
|---|---|---|
| **Declared/static variable type** | Compile time | `Message msg` |
| **Actual/runtime object class** | Runtime | `new EmailMessage()` |
| **Subtype/polymorphism** | Type relationship checked at compile time; behavior executed at runtime | `EmailMessage implements Message` |
| **Dynamic dispatch** | At runtime for overridden instance methods | `msg.render()` invokes `EmailMessage.render()` |
| **Downcast** | Cast possibility checked at compile time; reference cast validated at runtime | `(EmailMessage) msg` |

**Important:** An object created with `new EmailMessage()` does not “change its class” to `SmsMessage`. Instead, `msg` refers to **another object** after reassignment. Primitives such as `int` do not have referenced objects with runtime classes in this model.

## 5. Java 17 program: compile-time checks, dynamic dispatch, casts, and overloads

Save the following to **`TypeCheckingDemo.java`**. It runs on JDK 17 or later without external libraries.

~~~java
import java.util.ArrayList;
import java.util.List;

interface Notification {
    String format();
}

final class EmailNotification implements Notification {
    @Override
    public String format() {
        return "EMAIL: đơn hàng đã được xác nhận";
    }

    public String channelSpecificInfo() {
        return "SMTP";
    }
}

final class SmsNotification implements Notification {
    @Override
    public String format() {
        return "SMS: đơn hàng đã được xác nhận";
    }
}

public class TypeCheckingDemo {
    static String describe(Object input) {
        return "overload(Object)";
    }

    static String describe(String input) {
        return "overload(String)";
    }

    static void deliver(Notification notification) {
        // Instance method được dispatch theo object thực tế.
        System.out.println(notification.format());
    }

    public static void main(String[] args) {
        Notification notification = new EmailNotification();

        deliver(notification);
        System.out.println(
                "Runtime class: " + notification.getClass().getSimpleName());

        // Biên dịch sai vì declared type Notification không có method này:
        // notification.channelSpecificInfo();

        // Java 17: instanceof pattern matching vừa kiểm tra vừa bind biến.
        if (notification instanceof EmailNotification email) {
            System.out.println("Kênh đặc thù: "
                    + email.channelSpecificInfo());
        }

        notification = new SmsNotification();
        deliver(notification); // Cùng dòng gọi, implementation khác.

        Object value = "Java";
        System.out.println(describe(value));
        System.out.println(describe((String) value));

        Object untrusted = 42;
        if (untrusted instanceof String str) {
            System.out.println("Text: " + str);
        } else {
            System.out.println("Giá trị không phải String");
        }

        try {
            String bad = (String) untrusted; // Cast hợp lệ về cú pháp.
            System.out.println(bad);
        } catch (ClassCastException ex) {
            System.out.println("Cast sai ở runtime");
        }

        var count = 10; // Compiler suy luận int, không phải kiểu động.
        count = 11;
        // count = "mười"; // LỖI BIÊN DỊCH.

        List<String> codes = new ArrayList<>();
        codes.add("ORD-1");
        // codes.add(123); // LỖI BIÊN DỊCH do generic type.

        System.out.println("Code: " + codes.get(0));
    }
}
~~~

Run:

~~~bash
javac TypeCheckingDemo.java
java TypeCheckingDemo
~~~

Output:

~~~text
EMAIL: đơn hàng đã được xác nhận
Runtime class: EmailNotification
Kênh đặc thù: SMTP
SMS: đơn hàng đã được xác nhận
overload(Object)
overload(String)
Giá trị không phải String
Cast sai ở runtime
Code: ORD-1
~~~

### 5.1. Why does `deliver(notification)` invoke the correct implementation?

The compiler confirms that `notification` has static type `Notification`, whose interface declares `format()`. Runtime selects the overridden implementation on the actual class: `EmailNotification.format()` or `SmsNotification.format()`.

This is **dynamic polymorphism (runtime polymorphism)**. It exists **within statically typed Java**, so dynamic dispatch is not evidence that “Java is dynamically typed.”

### 5.2. Why do the two `describe(...)` calls differ?

In this example:

~~~java
Object value = "Java";
System.out.println(describe(value));          // overload(Object)
System.out.println(describe((String) value)); // overload(String)
~~~

**Overloading** is resolved **using expression types at compile time**. `describe(value)` selects `describe(Object)` because `value` has static type `Object`; the compiler does not inspect the runtime object to select the `String` overload.

`describe((String) value)` uses an **expression after casting** whose static type is `String`, so the compiler selects `describe(String)`. The reference cast itself is still checked at runtime.

**Overriding** is different: once the appropriate instance-method signature has been selected, the JVM can dispatch to an override based on the actual runtime class. Keep these stages distinct when overloads interact with inheritance.

### 5.3. Is `var` dynamically typed?

No. Java `var` (introduced in Java 10) enables **local variable type inference**; it does not let a variable change to an incompatible type:

~~~java
var score = 100;       // int
score = 120;           // Đúng
// score = "cao";      // Sai compile time

var label = "READY";   // String
// label = false;      // Sai compile time
~~~

Furthermore, `var` cannot replace declared types everywhere:

~~~java
// int calculate(var value) { ... } // Không hợp lệ: var
// không dùng làm kiểu formal parameter của method thông thường.

// var field = 1; // Không hợp lệ cho field thông thường.
~~~

One syntax exception lets `var` appear in some **lambda** formal parameters under specific language rules; do not confuse this with ordinary declared-method parameters.

## 6. Compile-time type checking: what does it catch and miss?

Some mistakes are routinely rejected by `javac`:

~~~java
String label = "READY";
// label = 42;        // Không thể gán int cho String.
// label.toUpperCase(1); // Sai danh sách tham số của method.

List<Integer> scores = new java.util.ArrayList<>();
scores.add(90);
// scores.add("A");   // Sai generic element type.

interface Printer { void print(); }
class ConsolePrinter implements Printer {
    public void print() { System.out.println("ok"); }
}
~~~

Java checks many constraints using **declarations, signatures, generic usage, accessibility, and subtyping**. Yet the compiler cannot know actual inputs from networks, files, databases, HTTP responses, or users ahead of time.

| Scenario | Can compile-time checks reject it? | What must happen at runtime? |
|---|---|---|
| Assigning `String` directly to `int` | Yes | Code cannot run until the error is fixed |
| Calling an absent method on a static type | Yes | Code cannot run until the error is fixed |
| Adding `String` to a correctly declared `List<Integer>` | Yes | Code cannot run until the error is fixed |
| Downcasting an `Object` containing `Integer` to `String` | Cannot determine the actual object with certainty | Cast is checked and may throw `ClassCastException` |
| Writing `Double` to an actual `Integer[]` array through a `Number[]` reference | Compiler allows covariance of arrays | May throw `ArrayStoreException` |
| Whether an email from a user has valid formatting | No | Business validation required |
| `100 / divisor` with a runtime-provided `divisor` | Cannot validate all cases | May throw `ArithmeticException` on integer division by 0 |
| Class loaded/created by reflection | Cannot fully prove runtime class names | May require checking `Class<?>` and handling reflection exceptions |

**Not all errors are type errors:** `NullPointerException`, `IndexOutOfBoundsException`, validation failures, and incorrect logic can all occur in correctly statically typed programs. Successful compilation does not guarantee correct execution.

## 7. `instanceof`, pattern matching, and safe casts

When a value has a broad static type like `Object`, **check its actual type** before accessing subtype-specific behavior:

~~~java
static String describeValue(Object value) {
    if (value instanceof String text) {
        return "String: " + text.toUpperCase();
    }
    if (value instanceof Integer number) {
        return "Integer: " + number;
    }
    return "Other or null";
}
~~~

The example uses **pattern matching for `instanceof`** (available in Java 17). The `text` variable is in scope only where the compiler knows the pattern matched, under **flow scoping**. `null instanceof String` returns `false`, so the last branch also handles `null`.

Sometimes a downcast is justified by a validated business contract, but do not guess the class:

~~~java
Object incoming = Integer.valueOf(42);

// String text = (String) incoming;
// Compiler cho phép cast từ Object, nhưng runtime ném ClassCastException.

if (incoming instanceof Integer number) {
    System.out.println(number + 1);
}
~~~

Java casts serve **different purposes**. `(String) someObject` is a reference cast that may be checked at runtime; `(int) 3.9` is a primitive numeric narrowing conversion yielding `3`, **not** a `ClassCastException`. Do not treat all casts alike.

### 7.1. Avoid excessive `instanceof` checks

If code repeatedly does this:

~~~java
if (notification instanceof EmailNotification) {
    // xử lý email
} else if (notification instanceof SmsNotification) {
    // xử lý sms
}
~~~

when an interface already provides the common operation, have classes **override the method** and invoke through the interface. Use `instanceof` for genuine **data classification**, unknown-type input validation, or special capabilities that cannot reasonably be expressed by the abstraction.

**Practical rule:** Use interfaces and polymorphism for **shared behavior**; use controlled pattern matching/casts at **heterogeneous-data boundaries** or where different cases require different handling.

## 8. Generics: compile-time type arguments versus external runtime data

```java
List<String> codes = new ArrayList<>();
codes.add("ORD-1");
// codes.add(123); // Sai ngay khi biên dịch.
System.out.println(codes.get(0)); // ORD-1
```

But `ArrayList<String>` and `ArrayList<Integer>` use the same runtime class; Java cannot test `instanceof List<String>`, only `List<?>` with element checks when needed. Raw types and unchecked casts can cause **heap pollution** and a `ClassCastException` on retrieval.

For data received from JSON/plugins/legacy APIs, do not cast to `(List<String>)` merely to silence a compiler error. Validate values individually and construct a new typed collection:

~~~java
static List<String> requireStrings(List<?> source) {
    Objects.requireNonNull(source);
    List<String> result = new ArrayList<>();
    for (Object item : source) {
        if (!(item instanceof String text)) {
            throw new IllegalArgumentException("Expected String");
        }
        result.add(text);
    }
    return List.copyOf(result);
}
~~~

`null` is also rejected because it does not match `String`. The new list is unmodifiable, but that is **an API choice**, not a wildcard property. The **Type relationships in generic constructs** lesson covers variance/capture and erasure; here the focus is **the boundary between static type checks and untrusted runtime data**.

## 9. Reflection, JSON, and untrusted data: how far does type checking reach?

Receiving `Object` from a plugin, mapped JSON values, or reflection-created objects introduces runtime data that compile-time checks cannot fully verify.

For example, use `Class<T>` to check an object's runtime class before casting:

~~~java
final class TypedReaders {
    private TypedReaders() {}

    static <T> T requireType(Object input, Class<T> expected) {
        if (!expected.isInstance(input)) {
            throw new IllegalArgumentException(
                    "Expected " + expected.getSimpleName());
        }
        return expected.cast(input);
    }
}

// Ví dụ gọi:
String name = TypedReaders.requireType("Lan", String.class);
// TypedReaders.requireType(42, String.class) -> IllegalArgumentException.
~~~

`Class<T>.isInstance` and `Class<T>.cast` provide useful runtime type checking. However, `Class<List<String>>` cannot be represented directly as `List<String>.class`. JSON frameworks may use *type tokens*, `Type`, or `ParameterizedType` to describe parameterized generic structures and map nested data. **Do not** assume `List.class` validates the types of elements in `List<String>`.

Checking the correct class is **still insufficient for data validity**. For example, a `String email` may have type `String` yet be `""`; a `BigDecimal amount` may have the right type but be negative; a properly deserialized request may violate business limits. Distinguish:

1. **Type checking:** Is the value of the expected type or an acceptable subtype?
2. **Validation:** Does it satisfy business meaning, formats, ranges, and permissions?
3. **Business rules:** Is the action allowed in the current state?

Do not use casting as a substitute for validation or check `instanceof` everywhere when static types already express the contract.

## 10. Frequently confused concepts

| Concept pair | Correct distinction | Example |
|---|---|---|
| **Static typing vs dynamic typing** | When expression types are determined/checked under the language's type system | Java vs Python |
| **Static type vs runtime class** | Compiler-known expression type versus the referenced object's actual class | `Notification n = new EmailNotification()` |
| **Type inference vs dynamic typing** | Compiler **infers one static type** versus more flexible runtime bindings | `var x = 1` still has type `int` |
| **Overloading vs overriding** | Overload signature usually selected at compile time; overridden instance implementation selected at runtime | `describe(Object)` / `describe(String)` vs `format()` |
| **Subtype vs cast** | Type relationships guarantee some assignments; reference casts require validation | `EmailNotification` is a `Notification`; `(EmailNotification) n` |
| **Type safety vs logical correctness** | Preventing incompatible-type operations versus ensuring correct business outcomes | `List<String>` does not prevent blank emails |
| **Generic type vs runtime generic check** | Compiler verifies type relationships; erasure does not retain every runtime type argument | `List<String>`, `instanceof List<?>` |
| **Static method vs dynamically dispatched instance method** | Static methods are hidden, not overridden polymorphically | `Parent.print()` vs `child.render()` |

### Static member hiding is not dynamic dispatch

The following small example runs in any method given these two classes:

~~~java
class Parent {
    static String category() { return "Parent"; }
    String name() { return "Parent"; }
}

class Child extends Parent {
    static String category() { return "Child"; } // method hiding
    @Override
    String name() { return "Child"; }             // overriding
}

Parent item = new Child();

System.out.println(item.category()); // Parent: theo static type Parent.
System.out.println(item.name());     // Child: dispatch theo object.
~~~

Java permits calling a static method through an instance, but **prefer** explicit `Parent.category()` or `Child.category()` to avoid confusing it with polymorphism. Identically named fields in parent and child classes are also **hidden**, not overridden like instance methods.

## 11. When Java compiles but runtime still fails

This table helps choose appropriate safeguards rather than adding casts blindly:

| Symptom | Example cause | Prevention |
|---|---|---|
| `ClassCastException` | Downcasting `Object` to an incompatible subtype | Use common interfaces or checked `instanceof`/`Class.cast` |
| `ArrayStoreException` | Writing incompatible runtime element types into a covariant array | Prefer generic collections where appropriate; avoid writing through a supertype array reference into a subtype array |
| `NullPointerException` | Treating a null reference as a valid object | Define a null policy; use `Objects.requireNonNull` at boundaries or model optionality |
| `ArithmeticException` | Integer division by 0 or invalid arithmetic | Check mathematical preconditions |
| `IndexOutOfBoundsException` | Index exceeds array/list bounds | Validate indices or iterate safely |
| `IllegalArgumentException` | Java type is correct but violates a business rule | Validate at boundaries and test edge cases |
| `NoSuchMethodException` / other reflection errors | Runtime member name missing/incompatible | Limit ad hoc reflection; validate APIs and handle dynamic-loading failures |

Static typing reduces type-related errors but cannot replace unit tests, integration tests, exception handling, or explicit contracts.

## 12. Testing important type boundaries

Demonstrate compile-time rules with **noncompiling examples** (comments in the demo), API documentation, or compile-testing tools for libraries that need them. Ordinary JUnit cannot run code already rejected by `javac`.

Runtime tests can verify that different object types implement the same interface and validate unknown-type inputs. For JUnit Jupiter 5, use the classes from `TypeCheckingDemo.java` and place tests in the same package:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RuntimeTypingTest {
    @Test
    void interfaceReferenceCanHoldDifferentImplementations() {
        Notification notification = new EmailNotification();
        assertTrue(notification.format().startsWith("EMAIL:"));

        notification = new SmsNotification();
        assertTrue(notification.format().startsWith("SMS:"));
    }

    @Test
    void downcastIsCheckedByRuntime() {
        Object number = Integer.valueOf(42);

        assertFalse(number instanceof String);
        assertThrows(ClassCastException.class, () -> {
            String text = (String) number;
            System.out.println(text);
        });
    }

    @Test
    void checkedConversionRejectsOtherTypes() {
        assertEquals("Lan",
                TypedReaders.requireType("Lan", String.class));
        assertThrows(IllegalArgumentException.class,
                () -> TypedReaders.requireType(42, String.class));
    }
}
~~~

`TypedReaders` appears in a separate reflection example; to run the final test, place it in the test's package. Other classes come from the demo. Add `org.junit.jupiter:junit-jupiter` and configure the project's JUnit runner.

A `ClassCastException` test shows the JVM checks casts at runtime; it **does not** make incorrect downcasts good design. Prefer clearly typed interfaces/generic APIs on main execution paths to minimize casts.

## 13. Comparing Java, TypeScript, and Python

Java has static typing and dynamically dispatched overrides. **TypeScript** checks shapes/annotations at compilation but erases most types when generating JavaScript; `JSON.parse(...) as User` **does not** validate the resulting object's shape. **Python** checks many operations at runtime, though tools such as mypy/Pyright can analyze type hints for some errors earlier.

~~~typescript
type User = { id: number; name: string };
function displayUser(user: User) {
    console.log(user.name.toUpperCase());
}
// Giá trị từ JSON vẫn cần runtime validation trước khi gọi.
~~~

~~~python
value = 42
value = "forty-two"  # Một tên có thể lần lượt giữ giá trị khác kiểu.
print(value.upper())
~~~

This comparison emphasizes **check timing and runtime contracts**; it does not rank one language as universally safer. The **Language differences when implementing the same OOP design** lesson compares a ShippingPolicy model implemented in Java/Kotlin/Python/TypeScript/C# in detail.

## 14. Exercise: processing heterogeneous notification data

An API receives data that another system converted into `List<?>`; some entries are `String`, some `Integer`, and some `null`. Build display labels for them.

**Requirements:**

1. Implement `static List<String> labels(List<?> input)`.
2. For nonblank `String` after `trim()`, append `"TEXT: " + value`.
3. For nonnegative `Integer`, append `"NUMBER: " + value`.
4. For other elements or null, throw `IllegalArgumentException` indicating the element position.
5. Return an unmodifiable list; handle `null` inputs deliberately.
6. Test valid values, negative numbers, blank strings, null elements, and unexpected types.
7. Explain why `List<?>` does not guarantee every element is already `String` and why `instanceof` is more appropriate here than casting to `(List<String>) input`.

Suggested scaffold:

~~~java
static java.util.List<String> labels(java.util.List<?> input) {
    java.util.Objects.requireNonNull(input, "input");

    java.util.List<String> result = new java.util.ArrayList<>();
    for (int i = 0; i < input.size(); i++) {
        Object value = input.get(i);

        if (value instanceof String text && !text.trim().isEmpty()) {
            result.add("TEXT: " + text.trim());
        } else if (value instanceof Integer number && number >= 0) {
            result.add("NUMBER: " + number);
        } else {
            throw new IllegalArgumentException(
                    "Invalid item at index " + i);
        }
    }
    return java.util.List.copyOf(result);
}
~~~

The scaffold is also a reference solution. Rework it without scattered `instanceof` checks across multiple layers: classify at the boundary, convert to a strongly typed model (for example, a `sealed interface` with two record subtypes), and handle that model consistently in business logic.

### Self-check questions

1. Given `Message msg = new EmailMessage()`, what is the **variable's** type and the **object's** actual class?
2. Why doesn't `var x = 10; x = "ten";` compile?
3. Why is `print(Object)` selected for `print(value)` even when the runtime object is `String`?
4. When are **overloading** and **overriding** decisions made?
5. Why can `List<String>` and `List<Integer>` use the same runtime class while the compiler still checks element types?
6. When is `instanceof` useful for boundary validation, and when does it signal missing polymorphism?
7. How can you distinguish **wrong Java types**, **invalid data formats**, and **violated business rules**?

**Remember:** Java **statically** checks many operations and calls, but interface references may point to objects with **different runtime classes**; overriding uses dynamic dispatch. `var` only infers a static type. External data, casts, reflection, array covariance, and generics boundaries still require runtime type checks or validation. Good design maximizes compiler-verified type relationships while checking at runtime precisely what the compiler cannot know in advance.
