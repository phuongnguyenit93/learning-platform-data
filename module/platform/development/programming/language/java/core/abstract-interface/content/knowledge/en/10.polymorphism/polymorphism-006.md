# `instanceof`, pattern matching, and checking before casting in Java

## 1. Background: polymorphism and the need for type checking

In Java, a reference variable can have a supertype (a class or an interface), while the actual object belongs to a specific subclass or implementation class. That is one foundation of **polymorphism**:

~~~java
interface Animal {
    void makeSound();
}

final class Dog implements Animal {
    @Override
    public void makeSound() {
        System.out.println("Gâu");
    }

    public void fetch() {
        System.out.println("Nhặt bóng");
    }
}

// Inside a running method:
Animal animal = new Dog();
animal.makeSound(); // Valid: the method belongs to the Animal contract.
// animal.fetch();  // Does not compile: the reference type Animal does not declare fetch().
~~~

`animal` has the **static type** `Animal`, but the actual object is a `Dog`. To call `fetch()`, the compiler needs to know that the expression has type `Dog`; the developer can cast the reference (downcast). The problem is that a variable of type `Animal` can also refer to a different implementation class, and an incorrect cast will throw a `ClassCastException`.

The **`instanceof`** keyword lets you check whether an object is compatible with a reference type at runtime. Since Java 16, **pattern matching for `instanceof`** has been a standard feature: you can check the type and declare a variable of the narrowed type in the same expression. Java 17 provides stable support for this syntax.

This lesson focuses on runtime type checking, safe casting, pattern variable scope, and common mistakes. Examples with `main` specify their file name so they can be compiled and run with Java 17+.

## 2. Traditional `instanceof`

### 2.1. Syntax and meaning

~~~java
referenceExpression instanceof ReferenceType
~~~

The result is `boolean`:

- `true` when the reference value is **not `null`** and the object is compatible with the type on the right. Compatibility includes that class itself, its subclasses, or a class that implements the interface being checked.
- `false` when the reference value is `null`, or the object does not belong to the type being checked.
- The compiler checks the validity of the test: not every pair of static types can be converted for checking. Completely unrelated types in a given case can cause a compile-time error right from the start.

Standalone example:

~~~java
Object a = "Java";
Object b = Integer.valueOf(17);
Object c = null;

System.out.println(a instanceof String);       // true
System.out.println(a instanceof CharSequence); // true
System.out.println(a instanceof Integer);      // false
System.out.println(b instanceof Number);       // true
System.out.println(c instanceof Object);       // false
~~~

With `a` being a `String` object, the `CharSequence` check is also true because `String` implements the `CharSequence` interface. When `c` is `null`, even `instanceof Object` returns `false`.

`instanceof` does not check “whether the class names are strictly equal”. For example, `new java.util.ArrayList<String>() instanceof java.util.List` returns `true` because the object implements `List`.

### 2.2. Testing and casting are two different steps

`instanceof` **only checks**; it does not automatically change the variable's static type in the old syntax:

~~~java
Object value = "Xin chào";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
~~~

`(String) value` is an **explicit cast**. Checking beforehand ensures that the referenced object can be converted to `String` in that branch. If you omit the check:

~~~java
Object value = Integer.valueOf(42);
String text = (String) value; // Compiles; throws ClassCastException at runtime.
~~~

With a syntactically valid downcast where the actual object is incompatible, the error occurs **at runtime**, not when Java compiles.

Further distinctions to note:

- An **upcast** from a subclass to a superclass/interface is normally a safe widening conversion and does not require `instanceof`: `Animal a = new Dog();`.
- A **downcast** from a supertype/interface to a subclass requires checking when the actual type is not guaranteed: `Dog d = (Dog) a;`.
- Reference casting `(Dog) null` produces `null`; the cast itself does not throw `ClassCastException`; only calling a method on the `null` result can throw `NullPointerException`.
- You should check and cast on **the same stable reference/value**; if between the two operations you replace the reference value with another object, the earlier check result no longer guarantees the subsequent cast.

## 3. Pattern matching for `instanceof` (Java 16+, used on Java 17)

### 3.1. Shorthand syntax

Traditional syntax:

~~~java
Object data = "Java 17";

if (data instanceof String) {
    String text = (String) data;
    System.out.println(text.toUpperCase());
}
~~~

Equivalent pattern matching syntax:

~~~java
Object data = "Java 17";

if (data instanceof String text) {
    System.out.println(text.toUpperCase());
}
~~~

The new part is **`String text`**: `String` is the type to match, and `text` is a **pattern variable** that is only brought into scope when the test guarantees a match. In the `if` branch when the check succeeds, `text` already has type `String`, so there is no need to write `(String) data`.

This pattern is a **type pattern**, not a way to automatically convert arbitrary types. It does not create a new object; `text` references the exact object being checked.

**Do not confuse this with `switch` pattern matching**: in Java 17, pattern matching for `instanceof` is a standard feature, whereas pattern matching for `switch` is still a preview feature and has different syntax and rules. The examples in this lesson do not require enabling `--enable-preview`.

### 3.2. Combining conditions with `&&` (short-circuit)

This is the most common scenario:

~~~java
Object input = "OpenJDK";

if (input instanceof String text && text.length() >= 5) {
    System.out.println("Chuỗi dài: " + text);
}
~~~

Stdout:

~~~text
Chuỗi dài: OpenJDK
~~~

The `&&` operator evaluates the right-hand side only if the left-hand side is `true`. Therefore, when the program executes `text.length()`, `text` is guaranteed to have been assigned by the pattern on the left-hand side. This is **flow scoping** (variable scope that depends on control flow).

Incorrect:

~~~java
// if (input instanceof String text || text.isBlank()) {
//     // Does not compile: the right-hand side of || can run when the pattern does not match.
// }
~~~

With `||`, the right-hand side is evaluated only when the left-hand side is **false**, so `text` cannot be guaranteed to have been assigned. You can replace this with two separate branches or restructure the condition according to your intent. It is not that `||` itself is forbidden; the error here is **using a pattern variable in a branch where it is not guaranteed**.

## 4. Pattern variable scope: conditions and execution flow

### 4.1. Inside an `if` branch

~~~java
static void show(Object candidate) {
    if (candidate instanceof String text) {
        System.out.println(text.trim());
    } else {
        System.out.println("Không phải chuỗi");
    }

    // text is not in scope here.
}
~~~

The variable `text` can be used wherever the compiler proves that the pattern matched. In `else` and after a regular `if`, the check may have failed, so `text` cannot be used.

### 4.2. Negation and early return

Thanks to flow analysis, Java can allow using a pattern variable **after** a negated `if` if the non-matching branch always terminates:

~~~java
static void printUppercase(Object candidate) {
    if (!(candidate instanceof String text)) {
        System.out.println("Bỏ qua: không phải chuỗi");
        return;
    }

    System.out.println(text.toUpperCase());
}
~~~

The key point: by the time the program reaches the final line, the non-matching pattern branch has executed `return`, so `text` is guaranteed to exist with type `String`. If that branch does not terminate the flow appropriately, the same inference cannot be made.

### 4.3. Combining negation, conditions, and other variables

~~~java
static boolean hasValidName(Object candidate) {
    return candidate instanceof String name
            && !name.isBlank()
            && name.length() <= 30;
}
~~~

The checks to the right of `&&` run only when the pattern has succeeded; `null` returns `false` right at the first test. This style reduces repetitive casting and avoids accessing an incompatible type.

### 4.4. Where a pattern is declared, and avoiding unnecessary redeclaration

A variable introduced by a pattern has its scope computed by Java based on the branches where the pattern “definitely matches”. Do not assume a pattern variable has the same scope as a local variable declared at the top of a block. If the compiler reports that the variable does not exist or shares a name with a variable already in scope, give the pattern a distinct name or restructure the condition.

**Intentionally wrong** example:

~~~java
// Object candidate = "Java";
// if (candidate instanceof String text) {
//     System.out.println(text);
// }
// System.out.println(text); // Error: text is no longer in guaranteed scope.
~~~

A specific limitation of type patterns: when the static type is already a subtype of the tested type, declaring a pattern may be rejected by the compiler because the test becomes unnecessary:

~~~java
// String value = "Java";
// if (value instanceof String text) { // Compile error: expression already has type String.
//     System.out.println(text);
// }
~~~

When the variable already has the right type, use that variable directly. This rule applies to the **pattern variable** declaration form; do not apply it mechanically to all traditional `instanceof` syntax.

## 5. Complete example with abstract class, interface, and polymorphism

The following example uses an abstract class `Device`, two subclasses `Phone`/`Printer`, and an interface `Rechargeable` to demonstrate:

- A supertype variable can hold multiple concrete object types.
- `instanceof` checks a subclass **or** an interface.
- A pattern variable lets you access methods specific to the matched type.
- `&&` allows additional checks after the type has been confirmed.
- Checking `null` as a separate branch is useful when you want a clear message.
- Traditional casting remains valid when guarded by `instanceof`.

Save the full code to the file **`Main.java`**:

~~~java
interface Rechargeable {
    int batteryPercent();
}

abstract class Device {
    abstract String description();
}

final class Phone extends Device implements Rechargeable {
    private final int battery;

    Phone(int battery) {
        this.battery = battery;
    }

    @Override
    String description() {
        return "Điện thoại";
    }

    @Override
    public int batteryPercent() {
        return battery;
    }
}

final class Printer extends Device {
    private final int ink;

    Printer(int ink) {
        this.ink = ink;
    }

    @Override
    String description() {
        return "Máy in";
    }

    int inkLevel() {
        return ink;
    }
}

public class Main {
    static void printInfo(Device device) {
        if (device == null) {
            System.out.println("Không có thiết bị");
            return;
        }

        System.out.println(device.description());

        if (device instanceof Phone phone
                && phone.batteryPercent() >= 50) {
            System.out.println("Điện thoại đủ pin: "
                    + phone.batteryPercent() + "%");
        }

        if (device instanceof Rechargeable rechargeable) {
            System.out.println("Sạc được: "
                    + rechargeable.batteryPercent() + "%");
        }

        if (device instanceof Printer printer) {
            System.out.println("Mực: " + printer.inkLevel() + "%");
        }
    }

    public static void main(String[] args) {
        Device[] devices = {
                new Phone(70),
                new Printer(30),
                null
        };

        for (Device device : devices) {
            printInfo(device);
        }

        Device candidate = new Phone(70);

        // Traditional approach: check first, then cast.
        if (candidate instanceof Phone) {
            Phone phone = (Phone) candidate;
            System.out.println("Ép kiểu truyền thống: "
                    + phone.batteryPercent() + "%");
        }
    }
}
~~~

Run in the directory containing `Main.java` with JDK 17 or higher:

~~~bash
javac Main.java
java Main
~~~

**Exact stdout:**

~~~text
Điện thoại
Điện thoại đủ pin: 70%
Sạc được: 70%
Máy in
Mực: 30%
Không có thiết bị
Ép kiểu truyền thống: 70%
~~~

Detailed explanation:

1. `Device[]` holds `Phone`, `Printer`, and `null`. The static type of the loop variable `device` is `Device`.
2. `device.description()` is a polymorphic call: for `Phone` it prints “Điện thoại”, and for `Printer` it prints “Máy in”.
3. `device instanceof Phone phone` matches only the `Phone` object here. `&&` ensures `phone.batteryPercent()` is called safely; battery 70 satisfies the condition of 50 or above.
4. `device instanceof Rechargeable rechargeable` matches `Phone` because this class implements `Rechargeable`, even though the expression currently has static type `Device`.
5. `device instanceof Printer printer` matches `Printer` and allows calling `inkLevel()` without an explicit cast.
6. `null` is handled by the first branch of `printInfo`, and the subsequent accesses are not executed.
7. `candidate instanceof Phone` is the traditional check syntax; `(Phone) candidate` is the cast after checking. For this exact object, the cast succeeds.

**Design note:** if all clients keep having to ask “is this a Phone or a Printer?” to decide the device's primary behavior, consider moving the common behavior into the superclass or an interface and using polymorphic dispatch. `instanceof` is useful when you need to access an **optional capability** (`Rechargeable`), handle input of an unknown type, or interact with an API you cannot modify.

## 6. Special cases when using `instanceof`

### 6.1. `null` never matches

~~~java
Object object = null;
System.out.println(object instanceof String);
~~~

The result is `false`. Therefore, a check like `if (obj instanceof String s)` already covers excluding `null` for the matching branch. Use `obj != null` separately only when you want to handle `null` with its own message or independent branch.

### 6.2. Accounting for subclasses and interfaces

~~~java
Object value = new java.util.ArrayList<String>();

System.out.println(value instanceof java.util.ArrayList);
System.out.println(value instanceof java.util.List);
System.out.println(value instanceof java.util.Collection);
~~~

All three lines print `true`. `instanceof` does not require the runtime type to equal the **exact** type on the right; inheritance and interface implementation relationships are taken into account. In contrast, `obj.getClass() == SomeClass.class` compares the exact runtime class; `getClass()` also throws `NullPointerException` if `obj` is `null`. The two checks serve two different purposes.

### 6.3. Primitive types

`instanceof` checks **reference types** and cannot be applied directly to primitive expressions:

~~~java
// int number = 7;
// boolean ok = number instanceof Integer; // Compile error.
~~~

To check the type of data received through `Object`, the primitive value must be boxed into an object. When the primitive type is already known for certain, a runtime type check usually makes no sense.

### 6.4. Arrays

Arrays are reference objects. They can be checked with `instanceof`:

~~~java
Object value = new String[] {"Java", "JVM"};

if (value instanceof String[] words) {
    System.out.println(words.length);
}
~~~

Output: `2`. The array pattern introduces the variable `words` with type `String[]`, so you can access `length` or array elements in the matching branch.

### 6.5. Generics and type erasure

You cannot directly check the specific type argument of a generic collection at runtime because of **type erasure**:

~~~java
// Object value = java.util.List.of("Java");
// if (value instanceof java.util.List<String> names) { // Compile error.
//     System.out.println(names);
// }
~~~

You can check a **reifiable** type such as `List<?>`:

~~~java
Object value = java.util.List.of("Java", "JVM");

if (value instanceof java.util.List<?> items) {
    System.out.println(items.size());
}
~~~

Stdout: `2`. The test tells you that the object is a `List`; **it does not verify that all elements are `String`**. If the program needs to check element types, it must inspect each element and handle mistyped data.

### 6.6. Distinguishing compile-time errors from `ClassCastException`

The two kinds of errors are very different:

- **Rejected at compile time:** a match or cast that makes no sense given the static type relationships Java can determine; using a pattern when the static type is already a subtype of the pattern type; or referencing a pattern variable in a branch where it is not guaranteed.
- **Runtime `ClassCastException`:** the cast syntax is accepted because a compatible object could exist, yet the **actual object** does not belong to the target type. For example, casting an `Object` holding an `Integer` to `String`.
- **Runtime `NullPointerException`:** if a cast yields `null` and you then call an instance method on it. `instanceof` itself simply yields `false` for `null`.

Do not use `try/catch (ClassCastException)` as a routine substitute for type checking when program flow is predictable. Checking with `instanceof` or using a clear polymorphic design is easier to understand in normal cases.

## 7. Common mistakes and misconceptions

| Mistake/misconception | Why it is incorrect | Correct approach |
|---|---|---|
| Casting to a subclass immediately when only the supertype of the variable is known | The actual object may belong to a different subclass. | Check with `instanceof` first, or use a polymorphic method from the supertype. |
| Thinking `instanceof` changes the variable's static type across the whole method | The old test only returns `boolean`; a pattern variable is flow-scoped. | Use `if (x instanceof Type t)` and use `t` in the valid region. |
| Using a pattern variable after an `if` that does not guarantee a match | The compiler cannot prove the variable exists. | Use it inside the matching branch or after a proven early-return branch. |
| `if (x instanceof String s \|\| s.isBlank())` | When the left side is false, `s` has not been assigned. | Use `&&` when the extra condition needs `s`; if the intent differs, split the conditions. |
| Comparing only `getClass()` to look for subtypes/interfaces | `getClass()` checks the exact runtime class and does not automatically include subtypes. | Use `instanceof` if you want to accept subclasses or implementations. |
| Assuming `null instanceof Object` returns `true` | `null` is not a concrete object. | Handle `null` separately if needed. |
| Writing `obj instanceof List<String> list` | Generic element types cannot be checked with `instanceof` after type erasure. | Test `List<?>`, then check the elements if needed. |
| `int n = 3; n instanceof Integer` | The left operand is a primitive value. | Check reference types when needed; do not test primitive types this way. |
| Using `switch` pattern matching as a standard Java 17 feature | In Java 17, pattern `switch` is still preview. | Use the standard `instanceof Type name`, with no preview needed. |
| Using `instanceof` in every object-handling branch | Makes code depend on many concrete subclasses and hard to extend. | Prefer polymorphism for shared behavior; use `instanceof` when you genuinely need to check a specific capability or type. |

## 8. Common usage patterns

### 8.1. Input data typed only as `Object`

~~~java
static String toDisplayText(Object value) {
    if (value instanceof String text) {
        return text.trim();
    }
    if (value instanceof Number number) {
        return "Số: " + number;
    }
    return value == null ? "(null)" : "(không hỗ trợ)";
}
~~~

This is an **illustrative method**, not yet a standalone program. A program could call `toDisplayText("  abc  ")` → `"abc"`, `toDisplayText(17)` → `"Số: 17"`, and `toDisplayText(null)` → `"(null)"`. Each branch has a clear pattern variable name.

### 8.2. Checking capabilities through an interface

~~~java
interface CloseableResource {
    void close();
}

static void closeIfSupported(Object value) {
    if (value instanceof CloseableResource resource) {
        resource.close();
    }
}
~~~

Here we check a **capability** (`CloseableResource`) instead of casting the object to a specific implementation class. This approach is more resilient if multiple object types implementing the interface appear later.

### 8.3. Early exit when input has the wrong type

~~~java
static int textLengthOrZero(Object value) {
    if (!(value instanceof CharSequence text)) {
        return 0;
    }
    return text.length();
}
~~~

The part after `if` can execute only when the input has matched `CharSequence`. Java allows using `text` in the final `return` statement. The `CharSequence` type is more flexible than `String` if the logic only needs `length()`.

## 9. Choosing the right approach

| Situation | Usually appropriate approach |
|---|---|
| Calling only shared behavior already declared by the superclass/interface | Call the polymorphic method directly; no `instanceof` needed. |
| Need to check a specific subclass before using its own API | `if (x instanceof Subtype sub) { ... }`. |
| Need to check an optional capability | Pattern `instanceof SomeInterface capability`. |
| Need to check the type and add a condition based on the object | `if (x instanceof Type value && value.isValid())`. |
| Want to rule out non-matching cases up front | `if (!(x instanceof Type value)) return;`. |
| Maintaining Java code prior to Java 16 | `if (x instanceof Type) { Type value = (Type) x; }`. |
| Need to distinguish `null` from an object of the wrong type | Handle `null` separately before the pattern check. |

### Self-check questions

1. Does `instanceof` return `true` for `null`? — **No, always `false`.**
2. In `Object o = "abc"; if (o instanceof String s)`, do you need to write `(String) o` as well inside the true branch? — **No; `s` already has type `String`.**
3. Why can `s.length()` be used after `instanceof String s &&`? — Because **`&&` evaluates the right-hand side only when the pattern has matched**.
4. Does a subclass of `Animal` make `animal instanceof Animal` evaluate to `true`? — **Yes**, if `animal` is not `null` and the object belongs to a compatible type hierarchy.
5. Does `instanceof List<String>` check all generic arguments? — **No; this syntax is not valid in a test like the example**, use `List<?>` and check elements if needed.
6. Should you downcast a supertype reference to a subclass solely because it was previously initialized from that subclass? — Only when **you are certain the object referenced at the time of the cast** has a compatible type; if unsure, check with `instanceof`.

**Key takeaway:** `instanceof` answers “is the current object compatible with this type?”. Pattern matching `instanceof Type variable` both checks and creates a variable of the narrowed type at places guaranteed by control flow. Use it to avoid repetitive casts and `ClassCastException` when you need to handle a specific type; use **polymorphism** when the behavior is already part of the common contract.
