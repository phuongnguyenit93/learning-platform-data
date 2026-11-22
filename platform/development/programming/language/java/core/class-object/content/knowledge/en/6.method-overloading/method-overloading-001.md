# Purpose and Conditions of Method Overloading in Java

## 1. What Is Method Overloading?

**Method overloading** is declaring **multiple methods with the same name but different parameter lists**, so that a single behavior name can support multiple reasonable ways of calling it. For example, a message output utility can support sending a single string, sending a string with a priority level, or sending multiple strings.

```java
class MessagePrinter {
    void print(String message) {
        System.out.println(message);
    }

    void print(String message, int priority) {
        System.out.println("P" + priority + ": " + message);
    }

    void print(int value) {
        System.out.println("number=" + value);
    }
}
```

The `print` methods above have the same name but accept:

- One argument of type `String`.
- Two arguments in the order `String, int`.
- One argument of type `int`.

Those are **three valid overloads**. The Java compiler uses the accessible methods and **the types of the argument expressions at compile time** to choose the appropriate declaration, according to the overload resolution rules.

Overloading has two main purposes:

1. **Keeping a consistent behavior name:** `print` still means "output information"; the method name does not have to be changed to `printText`, `printTextWithPriority`, or `printNumber` just because the parameters differ.
2. **Improving usability and API extensibility:** you can add variants that accept different parameters, or provide default values by having one overload call another.

On the other hand, if you write too many overloads with very similar parameter types, calls can become **hard to predict or ambiguous**. Overloading is only useful when the methods genuinely express the same group of behaviors.

> **Core principle:** two methods with the same name must have different **parameter type lists** according to the language rules. Changing only the return type, parameter names, modifiers, or `throws` list **does not create a valid distinct overload**.

## 2. Complete Runnable Java 17+ Example: Using One Name in Three Ways

Create the file **`OverloadingBasicsDemo.java`**:

```java
class Formatter {
    String format(int quantity) {
        return "quantity=" + quantity;
    }

    String format(double price) {
        return "price=" + price;
    }

    String format(String product, int quantity) {
        return product + " x " + quantity;
    }

    String format(String product) {
        return format(product, 1);
    }
}

public class OverloadingBasicsDemo {
    public static void main(String[] args) {
        Formatter formatter = new Formatter();

        System.out.println(formatter.format(3));
        System.out.println(formatter.format(2.5));
        System.out.println(formatter.format("Pen", 4));
        System.out.println(formatter.format("Book"));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac OverloadingBasicsDemo.java
java OverloadingBasicsDemo
```

Exact output:

```text
quantity=3
price=2.5
Pen x 4
Book x 1
```

How each call is selected:

| Call | Selected Method | Reason |
| --- | --- | --- |
| `format(3)` | `format(int)` | The literal `3` has type `int`, matching directly. |
| `format(2.5)` | `format(double)` | The literal `2.5` has type `double`. |
| `format("Pen", 4)` | `format(String, int)` | The two arguments have matching types and order. |
| `format("Book")` | `format(String)` | One `String` argument; this overload calls `format(product, 1)`. |

`format(String)` is an example of a **convenience overload**: it specifies a default quantity of `1` and then forwards to the two-parameter implementation. This avoids repeating string concatenation in multiple places, while also making the API easier to call.

Note that the `Formatter` class here is not `public`; the only `public` class is `OverloadingBasicsDemo`, so the file must be saved with the exact name `OverloadingBasicsDemo.java`.

## 3. Conditions for Two Methods to Form an Overload

Within a class, methods with the same name must have **different signatures** according to Java's rules. When examining a typical non-generic overload, check the **number, types, or order of types** of the parameters.

### 3.1. Different Number of Parameters

```java
class Calculator {
    int sum(int a, int b) {
        return a + b;
    }

    int sum(int a, int b, int c) {
        return a + b + c;
    }
}
```

`sum(2, 3)` and `sum(2, 3, 4)` select two different overloads because the number of parameters differs. Both methods return `int`, though **having the same return type is not a requirement** of overloading.

### 3.2. Different Parameter Types

```java
class InputReader {
    String read(int index) {
        return "index=" + index;
    }

    String read(String key) {
        return "key=" + key;
    }
}
```

Both accept a single argument, yet `read(3)` selects `read(int)` while `read("name")` selects `read(String)`. This is a valid overload because the parameters have different types.

### 3.3. Different Order of Parameter Types

```java
class RequestBuilder {
    String make(String path, int retries) {
        return path + ":" + retries;
    }

    String make(int retries, String path) {
        return retries + ":" + path;
    }
}
```

`make("/users", 3)` and `make(3, "/users")` differ in the order of types (`String, int` versus `int, String`), so they can coexist.

You should not overuse this kind of overloading if the two calls represent similar meanings where argument positions can easily be mixed up. A clear API sometimes needs different method names or a parameter object with specific field names.

### 3.4. Method Signatures Do Not Include the Return Type

An example that is **intentionally invalid and does not compile**:

```java
// class WrongReturnType {
//     int parse(String text) {
//         return Integer.parseInt(text);
//     }
//
//     long parse(String text) {
//         return Long.parseLong(text);
//     }
// }
```

Both methods are named `parse` and have the parameter `(String)`. Replacing `int` with `long` as the return type **does not make the parameter signature different**; the compiler reports a duplicate declaration. Even if the caller writes `long result = parse("12");`, Java still does not choose an overload based solely on the variable receiving the result.

How to fix it: use different meaningful names (`parseInt` and `parseLong`), or design parameters that clearly indicate the conversion target if such an API is needed.

### 3.5. Changing Parameter Names, Modifiers, or `throws` Is Also Not Enough

Invalid example regarding **parameter names**:

```java
// class WrongNames {
//     void save(int id) { }
//     void save(int key) { } // Error: still save(int).
// }
```

Invalid example regarding **`throws`**:

```java
// class WrongThrows {
//     void load(String path) { }
//     void load(String path) throws java.io.IOException { }
//     // Duplicate declaration error for load(String).
// }
```

Invalid example regarding **`static`**:

```java
// class WrongStatic {
//     void check(int value) { }
//     static void check(int value) { }
//     // Duplicate declaration error for check(int).
// }
```

Within the same class, turning an instance method into a static method (or vice versa), changing the `public`/`private` access level, adding `final`/`synchronized`, or changing the exception list also does not create a new overload if the parameter list remains equivalent.

### 3.6. `varargs` Is a Form of Array Parameter

`int... values` uses the **variable arity parameter** syntax. A method can be called with multiple individual matching arguments, while internally it receives an **array**.

```java
class Totalizer {
    int total(int... values) {
        int result = 0;
        for (int value : values) {
            result += value;
        }
        return result;
    }
}
```

The calls `total()`, `total(2)`, `total(2, 3, 4)`, and `total(new int[]{2, 3})` can all be valid with **a single method** `total(int...)`. Having many ways to call a method **does not mean there are multiple overloads**.

Important: you cannot simultaneously declare `void add(int... values)` and `void add(int[] values)` in **the same class** as two separate overloads, because `int...` corresponds to the array parameter type `int[]` in the signature:

```java
// class BadVarargs {
//     void add(int... values) { }
//     void add(int[] values) { } // Error: equivalent signature.
// }
```

A varargs method has only **one varargs parameter**, and that parameter must be the **last parameter** in the list.

## 4. What Is a "Method Signature" in Java?

When learning basic overloading, you can remember that a method signature consists of **the name and the parameter types in exact order**; it does not include the return type, parameter variable names, or method body.

Example:

| Declaration | Readable Signature | Duplicates `log(String)`? |
| --- | --- | --- |
| `void log(String text)` | `log(String)` | Itself |
| `void log(String value)` | `log(String)` | **Duplicate** |
| `String log(String text)` | `log(String)` | **Duplicate** |
| `void log(Object text)` | `log(Object)` | **Different** |
| `void log(String text, int level)` | `log(String, int)` | **Different** |
| `void log(int level, String text)` | `log(int, String)` | **Different** |

In terms of the *Java Language Specification*, the concept of a signature also takes into account **type parameters of generic methods**, type parameter substitution, and the rules for **override-equivalent signatures**/**type erasure**. Therefore, the rule of thumb "different characters on the parameter line are enough" is inaccurate for generics or varargs.

For example, the following two declarations are written differently, yet conflict at the Java level:

```java
// import java.util.List;
//
// class InvalidGenerics {
//     void accept(List<String> values) { }
//     void accept(List<Integer> values) { }
// }
```

Within the same class, both generic parameter types have the **erasure** `List`. The compiler reports a **name clash**, rather than treating this as a valid overload. This topic will be explained in more detail in the generics section.

## 5. When Does Overload Resolution Occur?

**Overload resolution** is fundamentally a **compiler** decision based on:

1. **The method name** and the set of declarations that can be found from the invocation expression, access scope, and relevant static type.
2. **The number and static types of the argument expressions**, including conversions permitted by Java.
3. **The applicable overloads** according to the appropriate checking phases.
4. **The most specific method** among the applicable overloads; if multiple candidates exist without a unique choice, the call can be **ambiguous and fail to compile**.

After the compiler selects a signature, if it is an **overridable instance method**, the runtime can still select the **subclass implementation body** based on the object receiving the call. These are two distinct steps: **selecting the overload at compile time**, and potentially **dispatching the implementation at runtime**.

### General Priority Order of the Phases

Java evaluates candidates across several phases in priority order. In a basic understanding of method invocation:

1. **Strict invocation**: applies conversions such as identity, primitive widening, and appropriate reference widening, without yet needing boxing/unboxing or varargs expansion.
2. **Loose invocation**: if the previous phase has not found an applicable overload, boxing/unboxing and appropriate conversions can be considered.
3. **Variable arity**: if the previous two phases find none, varargs methods with a variable number of arguments are considered.

Within each phase, the **most specific** rule continues to select the best-matching method; it is not simply that "Java always chooses the method whose type name looks most similar to the human eye."

To avoid confusion, **determine the static types of the arguments first**, then check which conversions are allowed, which signatures apply in the earliest phase, and whether there is a most specific candidate.

## 6. Widening, Boxing, and Varargs: Why Does Selection Order Matter?

Standard example: an integer literal `5` has type `int`. If overloads accepting `long` and `Integer` exist, Java can select `long` via **primitive widening** in the earlier phase, rather than boxing to `Integer`.

Create the file **`OverloadResolutionDemo.java`**:

```java
class Selector {
    static String choose(long value) {
        return "long";
    }

    static String choose(Integer value) {
        return "Integer";
    }

    static String choose(int... values) {
        return "int... count=" + values.length;
    }

    static String identify(Object value) {
        return "Object";
    }

    static String identify(String value) {
        return "String";
    }
}

public class OverloadResolutionDemo {
    public static void main(String[] args) {
        System.out.println(Selector.choose(5));
        System.out.println(Selector.choose(Integer.valueOf(5)));
        System.out.println(Selector.choose());
        System.out.println(Selector.choose(1, 2));
        System.out.println(Selector.identify("Java"));
        System.out.println(Selector.identify((Object) "Java"));
        System.out.println(Selector.identify(null));
    }
}
```

Compile and run:

```bash
javac OverloadResolutionDemo.java
java OverloadResolutionDemo
```

Output:

```text
long
Integer
int... count=0
int... count=2
String
Object
String
```

Explanation:

- `choose(5)`: the argument has type `int`, which can **widen** to `long` in the strict phase. Boxing to `Integer` is not prioritized over widening, so `choose(long)` is selected.
- `choose(Integer.valueOf(5))`: the argument already has type `Integer`; `choose(Integer)` matches directly, winning over the path of unboxing and widening to `long` in a later phase.
- `choose()`: not a single fixed-parameter overload fits; `choose(int...)` accepts **0** elements via variable arity.
- `choose(1, 2)`: requires the varargs overload, receiving two `int` values.
- `identify("Java")`: the argument has static type `String`; it could use the `Object` overload, but `String` is more specific, so `identify(String)` is selected.
- `identify((Object) "Java")`: the cast changes **the static type of the argument expression** to `Object`, so `identify(Object)` is selected even though the runtime object is still a `String`.
- `identify(null)`: the `null` literal matches both `Object` and `String`; `String` is a subtype of `Object` and is more specific, so Java selects `identify(String)`.

### Note on Integer Literals and Narrowing

The argument in `choose(5)` in the example has type `int`, and is not automatically treated as `byte` just because the value 5 falls within the `byte` range.

```java
class NumericChoice {
    static String select(byte value) {
        return "byte";
    }

    static String select(short value) {
        return "short";
    }
}
```

In this class, `NumericChoice.select(5)` **does not compile**: `5` has type `int`, and a normal method call does not automatically narrow `int` to `byte`/`short` the way certain constant assignments follow special rules. Writing `NumericChoice.select((byte) 5)` selects the `byte` version; writing `NumericChoice.select((short) 5)` selects the `short` version.

An **explicit cast** can alter overload selection, but it can also lose data if a numeric cast exceeds the representable range. You should not add casts merely to force the compiler to choose a branch if the API offers a clearer way to call it.

## 7. Why Can `null` Make a Call Ambiguous?

`null` can be converted to many reference types, yet **does not have a concrete runtime object type to help select an overload**. When two parameter types do not have a subtype relationship in a direction that yields a most specific candidate, the call can be ambiguous.

Example that intentionally does not compile at the commented line:

```java
class NullChoice {
    static String test(String value) {
        return "String";
    }

    static String test(Integer value) {
        return "Integer";
    }

    static void demo() {
        // System.out.println(test(null));
        // Uncomment -> error: reference to test is ambiguous.
        System.out.println(test((String) null));
        System.out.println(test((Integer) null));
    }
}
```

`test(null)` has two candidates: `test(String)` and `test(Integer)`. There is no relationship where "`String` is a subtype of `Integer`" or vice versa, so there is no unique most specific candidate. An explicit cast clarifies the expression's type and resolves the call in the example.

Another example:

```java
class RelatedChoice {
    static String select(Object value) {
        return "Object";
    }

    static String select(String value) {
        return "String";
    }
}
```

`RelatedChoice.select(null)` selects `String` because `String` is more specific than `Object`. Therefore, saying "passing `null` to any overload always fails" is incorrect; you must examine the type relationship among **the candidates that actually apply**.

**Note:** The cast `(String) null` does not create a `String` object; the value is still `null`. It only specifies the static type for overload resolution. If the method body dereferences this value, a `NullPointerException` can still occur.

## 8. `varargs` and Fixed-Parameter Overloads

A **fixed arity** overload typically wins a matching call in an earlier phase than a varargs call that must gather multiple arguments. However, a varargs declaration can also be called like a method with an array parameter taking a fixed number of arguments; therefore, you should not reduce every situation to the claim "Java always ignores varargs."

Create the file **`VarargsOverloadDemo.java`**:

```java
class Printer {
    static String show(int value) {
        return "one=" + value;
    }

    static String show(int... values) {
        return "many=" + values.length;
    }
}

public class VarargsOverloadDemo {
    public static void main(String[] args) {
        System.out.println(Printer.show(4));
        System.out.println(Printer.show(4, 5));
        System.out.println(Printer.show());
        System.out.println(Printer.show(new int[]{7, 8, 9}));
    }
}
```

Commands:

```bash
javac VarargsOverloadDemo.java
java VarargsOverloadDemo
```

Output:

```text
one=4
many=2
many=0
many=3
```

Analysis:

1. `show(4)` matches `show(int)` by fixed arity; the `show(int...)` version is not chosen when a single-`int` call already has a candidate in an earlier phase.
2. `show(4, 5)` does not match `show(int)` because there are two arguments; varargs collects the values into an `int[]`.
3. `show()` is handled by varargs with an empty array.
4. `show(new int[]{7,8,9})` passes an **array** directly to the `int[]`-typed parameter of `show(int...)`; this is a valid call in the **fixed-arity form** of a varargs method.

### Varargs Can Cause Ambiguity

```java
class AmbiguousVarargs {
    static void process(int... values) { }
    static void process(boolean... values) { }

    static void demo() {
        // process(); // Compile error: both accept 0 elements.
        process(1);    // Valid: only int... matches.
        process(true); // Valid: only boolean... matches.
    }
}
```

Adding multiple varargs overloads with unrelated element types makes zero-argument calls hard to resolve. An API should generally provide a separate no-argument overload or avoid ambiguous varargs overloads.

## 9. Overloading Across Inheritance and Differences from Overriding

A class can define new overloads alongside **validly inherited** overloads. However, **overloading** and **overriding** are two different mechanisms:

| Aspect | Overloading | Overriding |
| --- | --- | --- |
| Relationship | Multiple methods with the same name, **different valid parameter lists/signatures** | A subclass provides an implementation for a superclass instance method with a corresponding signature |
| Requires inheritance? | No; can happen within a single class | Yes; has an appropriate type/implementation relationship |
| Decision time | Overload selection occurs mainly at **compile time** | Overriding implementation is selected at **runtime** for overridable instance methods |
| Return type | Can differ, but is not sufficient to distinguish overloads | Must be compatible according to return type rules, including covariant return types when valid |
| `static` | Static methods can be overloaded with different parameter lists | Static methods **do not override**; they can hide according to the rules |
| `@Override` | Not used to mark a purely new overload | Used to ask the compiler to verify the overriding intent |

### Combined Runnable Example

Create the file **`OverloadVsOverrideDemo.java`**:

```java
class Animal {
    String sound() {
        return "animal";
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "dog";
    }
}

class Inspector {
    static String inspect(Animal animal) {
        return "Animal overload: " + animal.sound();
    }

    static String inspect(Dog dog) {
        return "Dog overload: " + dog.sound();
    }
}

public class OverloadVsOverrideDemo {
    public static void main(String[] args) {
        Animal general = new Dog();
        Dog specific = new Dog();

        System.out.println(Inspector.inspect(general));
        System.out.println(Inspector.inspect(specific));
    }
}
```

Run:

```bash
javac OverloadVsOverrideDemo.java
java OverloadVsOverrideDemo
```

Output:

```text
Animal overload: dog
Dog overload: dog
```

The first line involves **two independent decisions**:

1. `general` has **static type `Animal`**, so `inspect(Animal)` is chosen **at compile time**. Java does not choose `inspect(Dog)` just because the runtime object is a `Dog`.
2. Inside `inspect(Animal)`, the `animal.sound()` call is an overridable instance method. Because the runtime receiver is `Dog`, the `Dog.sound()` implementation returns `dog`.

The second line: `specific` has static type `Dog`, so `inspect(Dog)` is chosen from the start; calling `sound()` on the `Dog` receiver also returns `dog`.

### Inherited Overloads Can Participate in Selection

```java
class BaseNotifier {
    void notify(Object message) {
        System.out.println("object");
    }
}

class TextNotifier extends BaseNotifier {
    void notify(String message) {
        System.out.println("text");
    }
}
```

Within valid access scope, `new TextNotifier().notify("hi")` selects the `notify(String)` overload; `new TextNotifier().notify((Object) "hi")` selects the inherited `notify(Object)`.

If you declare `BaseNotifier base = new TextNotifier();` and then call `base.notify("hi")`, the compiler only sees the `notify(Object)` overload through **the static type `BaseNotifier`**, so it selects that version. `TextNotifier.notify(String)` does not override `BaseNotifier.notify(Object)` because the parameter type lists differ.

The classes above are **compilable declaration snippets without a `main` method**, used to illustrate the difference between the set of overloads visible to the compiler and the runtime object.

## 10. Overloading Static Methods and Instance Methods

Both **static methods** and **instance methods** can be overloaded when their valid signatures differ:

```java
class Parser {
    static int parse(String value) {
        return Integer.parseInt(value);
    }

    static int parse(String value, int radix) {
        return Integer.parseInt(value, radix);
    }

    String render(int value) {
        return Integer.toString(value);
    }

    String render(long value) {
        return Long.toString(value);
    }
}
```

- `Parser.parse("10")` selects the one-parameter version and returns `10`.
- `Parser.parse("10", 2)` selects the two-parameter version, interprets the string in base 2, and returns `2`.
- With `Parser parser = new Parser();`, `parser.render(10)` selects `render(int)`.
- `parser.render(10L)` selects `render(long)`.

Within the same class, you **cannot** declare `static void f(int x)` and `void f(int x)` simply because one method is static and the other is an instance method; the two signatures still collide.

When a static method in a subclass has the same signature as a validly inherited static method, that is **method hiding**, not overriding; you should not rely on an object's runtime type to select a static method.

## 11. Constructor Overloading: Same Idea, Different Usage Rules

Although the topic here is **method overloading**, constructors can also be **overloaded** by parameter list to provide multiple ways of creating an instance:

```java
class UserProfile {
    private final String name;
    private final int level;

    UserProfile(String name) {
        this(name, 1);
    }

    UserProfile(String name, int level) {
        this.name = name;
        this.level = level;
    }

    String summary() {
        return name + ":" + level;
    }
}
```

- `new UserProfile("Lan")` selects the single-`String` constructor; this constructor calls `this(name, 1)` to reuse logic.
- `new UserProfile("Lan", 3)` selects the `(String, int)` constructor.
- Constructors **have no return type** and are not regular methods.
- Once a class declares a constructor with parameters, Java **does not automatically add a default no-argument constructor**.

Constructor overloading uses the principle of selecting the appropriate signature at compile time, but constructors **are not inherited or overridden**. Constructor chaining via `this(...)` must also follow its own rules; in Java 17, an explicit `this(...)` call must appear at the start of the constructor body.

Mentioning constructors here only helps distinguish two mechanisms with similarities; in API design, you should not turn a constructor into a "method returning an object" or equate it with an instance method.

## 12. Generic Methods and Type Erasure: Signatures That Look Different Can Still Conflict

With **generic methods** and generic parameters, you need to account for **type erasure**. Parameters such as `List<String>` and `List<Integer>` carry type information at compile time, yet both have `List` as their erasure.

An **intentionally invalid** snippet:

```java
// import java.util.List;
//
// class Repository {
//     void store(List<String> values) { }
//     void store(List<Integer> values) { }
//     // Name clash error: both declarations have the same erasure.
// }
```

Fix this by choosing **distinguishable parameter types**, renaming the methods according to their meaning, or designing an appropriate generic method:

```java
import java.util.List;

class Repository {
    <T> int count(List<T> values) {
        return values.size();
    }

    int count(String text) {
        return text.length();
    }
}
```

This is a valid class declaration:

- `count(List<T>)` is a **generic method** that applies to lists with an appropriate element type.
- `count(String)` is another overload, because the `String` parameter type differs from the `List` parameter.
- With `List<String> items = List.of("a", "b");`, `new Repository().count(items)` returns `2`.
- With `new Repository().count("Java")`, the result is `4`.

It is not the case that any two methods using generics will conflict; an error occurs when the signature/erasure relationship renders the declarations **no longer validly distinguishable**. If you want to overload based on the generic element type of `List` parameters, merely changing `List<String>` to `List<Integer>` is not enough due to erasure limitations.

### Generic Methods Can Participate in Overload Selection

```java
class GenericChoice {
    static <T> String select(T value) {
        return "generic";
    }

    static String select(String value) {
        return "string";
    }
}
```

These two methods are valid: the post-erasure signature of the generic version is `select(Object)`; the other is `select(String)`. With `GenericChoice.select("hello")`, Java selects the more specific `String` version. With `GenericChoice.select(123)`, the compiler can infer an appropriate `T` and call the generic version, returning `generic`.

This is an illustrative declaration snippet **without its own `main` method**. Generic overload selection in complex situations is also governed by **type inference** and the exact most-specific rules of the JLS; you should design APIs to avoid signatures that force callers to guess the type inference logic.

## 13. When Should and Shouldn't You Overload?

An API uses overloading well when the variants share **the same meaning**, while differing in input data or convenience level:

| Case | Is Overloading Usually Appropriate? | Explanation |
| --- | --- | --- |
| `print(String)` and `print(int)` | Yes | Same information-output action, accepting different data types. |
| `connect(host)` and `connect(host, timeout)` | Yes, if the default behavior is clear | The single-parameter version can use a sensible default timeout. |
| `sum(int, int)` and `sum(double, double)` | Yes | Same addition operation across different type groups. |
| `save(Customer)` and `save(Order)` | Conditionally | Two entity types can share the `save` contract; note that `save(null)` may be ambiguous. |
| `delete(String)` where one overload "only checks" | Not recommended | The same name suggests the same behavior while having a different effect; easy to misuse. |
| Multiple overloads differing only in `String` parameters with the same parameter count | Invalid | Parameter names do not create a new signature. |
| `process(List<String>)` and `process(List<Integer>)` | Invalid within the same class | Name clash due to erasure. |

### Guidelines for Designing Friendly Overloads

1. **Overloads with the same name should express the same behavior at an abstract level.** If one version deletes while another only inspects status, use separate names.
2. **Keep parameter order consistent** across overloads, especially when multiple parameters have the same type `String` or `int`.
3. **Avoid combinations of unrelated reference types** if the API commonly accepts `null`. `save(String)` and `save(Integer)` make `save(null)` ambiguous.
4. **Prefer having fewer-parameter overloads call the full-parameter overload** so validation/behavior logic is not duplicated and variants remain consistent.
5. **Be cautious with widening, boxing, generics, and varargs.** A new overload can change the resolution result of existing calls when source code is recompiled, even without changing the method name.
6. **Do not use return types to "steer" overloading.** If you want an API to return different models for the same arguments, consider separate method names or adding a meaningful type/target parameter.
7. **Write behavior tests for representative argument types**, especially `null`, numeric literals, boxing, and varargs calls, when a real-world API has multiple closely related signatures.

## 14. Common Mistakes and How to Diagnose Them

### Mistake 1: Changing Only the Return Type

`int convert(String)` and `long convert(String)` cannot coexist in the same class as overloads. The return type **is not part of the conditions that distinguish signatures**.

### Mistake 2: Changing Parameter Variable Names

`save(int id)` and `save(int key)` still have the same signature `save(int)`. The compiler does not use parameter names to select a method.

### Mistake 3: Adding Only `throws`, `public`, `static`, or `final`

Modifiers and exception lists do not change the parameter type list; they are not enough to create a distinct overload.

### Mistake 4: Assuming Java Selects by Runtime Object Type

If `Object value = "hello";`, the call `use(value)` is resolved using the static type **`Object`**, not silently choosing `use(String)` just because the runtime value is a `String`. This is what distinguishes overloading from overriding.

### Mistake 5: Using `null` with Two Unrelated Reference Types

`method(String)` and `method(Integer)` can make `method(null)` ambiguous. You can pass a concrete value or an explicit cast if the contract allows `null`, though casting does not change the fact that the value is still `null`.

### Mistake 6: Assuming `int` Automatically Narrows to `short` in Method Calls

A method call with the literal `1` has type `int` and does not automatically select `method(short)` just because the value is small. You need an appropriate argument type or a cast when truly intended.

### Mistake 7: Thinking `int...` and `int[]` Form Two Overloads

Two declarations with the same name `f(int...)` and `f(int[])` have identical parameter types at the signature level; they cannot be declared as two separate methods in the same class.

### Mistake 8: Changing Only `List<String>` to `List<Integer>`

Generic type arguments can undergo **erasure**, causing two signatures to collide. Look at the parameter types after erasure, not just what is inside `<...>`.

### Mistake 9: Too Many Varargs Overloads

Two incompatible varargs methods such as `f(int...)` and `f(boolean...)` can both accept the call `f()`. Without a most specific choice, the compiler reports an ambiguity error.

### Mistake 10: Confusing Constructor Overloading with Method Overloading

A constructor has the class name and **no return type**; a method has a return type (including `void`). Constructors are selected when instantiating an object; methods are called on an object or via a class depending on whether they are static or instance.

### Mistake 11: Adding an Overload Without Checking Existing Calls

For example, if an API initially has only `log(Object)`, then `log("abc")` uses that version. When `log(String)` is added and **the source code is recompiled**, the call `log("abc")` will typically switch to `log(String)`. A new overloaded API can alter **behavior upon recompilation**. If a program was compiled previously, the bytecode still references the old method descriptor as long as it still exists; that is a binary compatibility perspective, distinct from source-level resolution.

### Mistake 12: Misusing `@Override` for Overloaded Methods

`@Override` requires a method to actually override or implement an appropriate method from a supertype (aside from specific language details). If you merely declare a new method with the same name but different parameters without overriding, `@Override` can cause a compile error.

## 15. Self-Check Questions and Answers

**Question 1.** Are the two methods `void draw(int size)` and `void draw(double size)` a valid overload?

**Answer:** Yes. They share the same name but have different parameter types (`int` versus `double`).

**Question 2.** Can `int read(String path)` and `String read(String path)` coexist?

**Answer:** No. Their return types differ, but their parameter lists are identical, so they do not form a valid overload.

**Question 3.** Given the methods `choose(long)` and `choose(Integer)`, what does calling `choose(7)` select?

**Answer:** `choose(long)`, because the literal `7` is an `int`, and the `int → long` conversion via primitive widening is considered before boxing `int → Integer`.

**Question 4.** Given `void save(Object)` and `void save(String)`, is calling `save(null)` ambiguous?

**Answer:** No. `String` is more specific than `Object`, so `save(String)` is selected.

**Question 5.** Given `void save(String)` and `void save(Integer)`, does calling `save(null)` compile?

**Answer:** No; neither parameter type is more specific than the other to decide a single overload. You can use a valid cast if you want to clarify your intent.

**Question 6.** Do `void write(int... values)` and `void write(int[] values)` create two overloads?

**Answer:** No. A varargs parameter is an array parameter in its corresponding signature; the two declarations conflict.

**Question 7.** Why aren't `process(List<String>)` and `process(List<Integer>)` two valid overloads in the same class?

**Answer:** Both have the erasure `process(List)`; Java reports a name clash.

**Question 8.** With `Animal a = new Dog();` and two overloads `inspect(Animal)` and `inspect(Dog)`, which version does `inspect(a)` select?

**Answer:** `inspect(Animal)`, because the compiler uses the **static type `Animal`** of `a` when selecting the overload. If an instance method overridden by `Dog` is called inside the body, runtime dispatch can still use `Dog`'s implementation.

**Question 9.** Are `sum(int, int)` and `sum(int, int, int)` a valid overload? Can they keep the same return type?

**Answer:** Yes, they are valid because the number of parameters differs. Both can return `int`; overloading does not require changing the return type.

**Question 10.** Why can adding `log(String)` to a class that already has `log(Object)` affect a program after rebuilding?

**Answer:** Calls with arguments of static type `String` will have a new, more specific candidate. Upon recompilation, they can be bound to `log(String)` and behave differently than before.

## 16. Process for Analyzing a Call with an "ambiguous" or "cannot be applied" Error

When the compiler reports difficulty choosing a method, you can follow this sequence:

1. **List the exact set of callable overloads** from the method name, the receiver's static type, access scope, and relevant declarations.
2. **Note the static type of each argument expression.** The literal `1` is `int`; `1L` is `long`; `"x"` is `String`; `null` has a special null type.
3. **Compare the number and order of parameters.** Remember that `varargs` can only expand in the appropriate phase, and there are cases where it accepts an array in fixed arity.
4. **Check allowed conversions.** Primitive widening differs from narrowing; boxing/unboxing follows a specific evaluation order; an explicit cast changes the expression's type.
5. **Apply the earliest phase with suitable candidates**, then pick the most-specific candidate. If there are multiple candidates without a unique choice, the call is ambiguous.
6. **For generics, check type inference and erasure.** A name clash error at declaration time is different from an ambiguity error at a call site.
7. **Distinguish overloading from overriding.** The runtime receiver can determine the overridden body, yet does not automatically change the overload signature already selected by the compiler.
8. **Fix with a clear API:** rename distinct behaviors, reduce unnecessary overloads, standardize parameter ordering, and use explicit types or casts when truly needed.

Quick diagnostic example:

```java
class Choice {
    static void f(String value) { }
    static void f(Integer value) { }
}
```

In another class, `Choice.f(null)` is ambiguous. The compiler does not lack information about **the number of parameters**, but rather lacks a **single most specific target type** for `null`. Fix this with `Choice.f((String) null)`, or avoid an API that requires users to distinguish between two branches with just a `null` value.

---

**Key takeaway:** **Overloading** allows multiple methods with the same name to serve **different parameter lists**. A valid overload is distinguished by its signature and generic/erasure rules, **not merely by return type or modifiers**. Overload selection happens at compile time based on **the static types of arguments**, conversion phase order, and the most specific candidate; this process differs from **overriding** based on the runtime receiver. A good API uses overloading to express a consistent behavior and avoids ambiguous signatures.
