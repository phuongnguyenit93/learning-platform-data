# Calls with `null` and Ambiguous Method Selection Errors in Java

When a class has multiple methods with the same name (**method overloading**), Java selects the method to call based on the **name, number of arguments, argument types, and compile-time overload resolution rules**. One situation that easily causes confusion is calling a method with the `null` literal:

~~~java
print(null);
~~~

`null` can be converted to many reference types, but cannot be converted directly to a primitive type such as `int`. If there is one clearest matching overload, the compiler selects it. If two or more overloads apply and there is no single most specific choice according to Java's rules, the program **does not compile** and typically reports an error such as `reference to print is ambiguous`.

This lesson focuses on **calls with `null` and how to handle ambiguous overloads**, including inheritance relationships, interfaces, arrays, varargs, boxing, casts, and API design decisions. Standalone programs use Java 17+-compatible syntax.

## 1. Prerequisites: What Is Method Overloading?

Two methods are **overloaded** when they are declared with the same name within an appropriate type scope but have different parameter lists according to Java signature rules:

~~~java
static void log(String text) {
    System.out.println("String: " + text);
}

static void log(Integer number) {
    System.out.println("Integer: " + number);
}
~~~

This is an illustrative snippet placed inside a class; the snippet itself does not have `main`. `log("hello")` uses the `String` version; `log(Integer.valueOf(5))` uses the `Integer` version. However, `log(null)` has a problem: both `String` and `Integer` are reference types compatible with null, while neither type is a subtype of the other. There is no more specific overload to choose, so the call is **ambiguous at compile time**.

**Note:**

- You cannot overload solely by **differing parameter names**. `log(String text)` and `log(String message)` have the same signature.
- You cannot overload solely by **return type**. `int load(String)` and `String load(String)` cannot coexist just because they return different types.
- Overloading differs from **overriding**: overloading selects the signature using compile-time information, whereas overriding of an instance method selects the implementation matching the runtime receiver after the signature has been determined.
- The `null` literal differs from the string `"null"`, the number `0`, or the reference `new Object()`.

## 2. What Type Does `null` Have and Why Do Multiple Overloads Match?

Java has a **null literal** (`null`). According to the language specification, this expression belongs to the *null type*, a special type without a name for declaring ordinary variables. A null value can be assigned to a variable of a **reference type** and can be used as an argument for a parameter of a compatible reference type.

Example:

~~~java
String name = null;
Integer count = null;
Object unknown = null;
CharSequence text = null;
int[] numbers = null;
Runnable task = null;
~~~

The assignments above are valid. Meanwhile:

~~~java
int count = null;       // Compilation error.
boolean ready = null;   // Compilation error.
~~~

This is a **compilation error example**, not code to include in a runnable program. The `int` and `boolean` types are primitives and cannot hold a null value.

A call `method(null)` **has no specific reference type information from the literal itself** to narrow the choice down to `String` or `Integer`. If the compiler sees that both signatures apply, it needs to use the rules for selecting a more specific method.

## 3. The Simplest Case: `Object` and `String`

Create the file **`NullMostSpecificDemo.java`**:

~~~java
public class NullMostSpecificDemo {
    static void print(Object value) {
        System.out.println("Object");
    }

    static void print(String value) {
        System.out.println("String");
    }

    public static void main(String[] args) {
        print(null);
        print("Java");

        String text = null;
        print(text);

        Object unknown = null;
        print(unknown);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 NullMostSpecificDemo.java
java NullMostSpecificDemo
~~~

Stdout:

~~~text
String
String
String
Object
~~~

### Why Does `print(null)` Select `print(String)`?

- `null` matches both the `Object` and `String` parameters.
- `String` is a subtype of `Object`.
- In this case, `print(String)` is **more specific** than `print(Object)`, so the compiler selects the `String` version.
- If `text` is **declared as `String`** but holds a null value, `print(text)` still selects `print(String)`.
- If the variable `unknown` is **declared as `Object`**, `print(unknown)` selects `print(Object)`, even though the variable's runtime value is null.

This is an important rule: **overload resolution uses the compile-time type of the argument expression; it does not test-run runtime values to re-select a signature**.

### Quick Prediction Table

With the two overloads `print(Object)` and `print(String)`:

| Call | Selected overload | Reason |
| --- | --- | --- |
| `print(null)` | `String` | Both are valid; `String` is more specific |
| `print("hello")` | `String` | The argument has type `String` |
| `String s = null; print(s);` | `String` | The declared type of `s` is `String` |
| `Object o = null; print(o);` | `Object` | No automatic assignment conversion `Object → String` |
| `print((Object) null)` | `Object` | The cast specifies the expression type as `Object` |
| `print((String) null)` | `String` | The cast specifies the expression type as `String` |

With `print((Object) null)`, selecting `Object` does not happen because the actual object changes. Both expressions still carry a **null value**; the cast changes the **compile-time type** information used for overload resolution.

## 4. When Two Parameters Are Types Without a Subtype Relationship

Consider the class:

~~~java
class Printer {
    static void print(String text) {
        System.out.println("String");
    }

    static void print(Integer number) {
        System.out.println("Integer");
    }
}
~~~

This is a valid class declaration, but it does not yet have `main`. `String` does not extend `Integer`, and `Integer` does not extend `String`. Therefore:

~~~java
Printer.print(null); // Compilation error: reference to print is ambiguous.
~~~

The call snippet above is marked as **intentionally non-compiling**. Looking solely at the null value, Java has no basis to prefer String over Integer. The declaration order of the two methods and the order in which they appear in the file **do not determine** the selection.

### Fix 1: Pass a Typed Value

~~~java
Printer.print("hello");               // Selects String.
Printer.print(Integer.valueOf(42));   // Selects Integer.
~~~

If the actual logic is to print a string, pass a string; if it is a wrapper-type integer, pass the corresponding value. This is the clearest approach when the caller already has the data.

### Fix 2: Cast `null` to Specify the Intended Overload

~~~java
Printer.print((String) null);   // Selects String.
Printer.print((Integer) null);  // Selects Integer.
~~~

Casting makes the **argument expression type** String or Integer. Then only the corresponding overload takes a parameter with a matching type. In this example, there is no longer any ambiguity.

**Warning:** Casting null only resolves the **compilation** issue. If the method body calls `text.length()` or unboxes `Integer` without checking for null, the program can still throw a `NullPointerException` at runtime. A good API needs to decide and clearly state whether null is valid.

### Fix 3: Explicitly Typed Variables

~~~java
String text = null;
Integer number = null;

Printer.print(text);
Printer.print(number);
~~~

Variables with clearly declared types allow the compiler to select the right overload. This approach is useful when null represents data that is not yet available, though a null-handling policy inside the method is still required.

## 5. Complete Example: Ambiguity and Fixing It with a Cast

Create the file **`AmbiguousNullSolutionDemo.java`**:

~~~java
public class AmbiguousNullSolutionDemo {
    static void describe(String value) {
        System.out.println("String=" + value);
    }

    static void describe(Integer value) {
        System.out.println("Integer=" + value);
    }

    public static void main(String[] args) {
        // describe(null); // Intentionally uncommenting will cause an ambiguous error.

        describe((String) null);
        describe((Integer) null);
        describe("Java");
        describe(Integer.valueOf(7));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 AmbiguousNullSolutionDemo.java
java AmbiguousNullSolutionDemo
~~~

Stdout:

~~~text
String=null
Integer=null
String=Java
Integer=7
~~~

Each method only performs string concatenation so it can display null without dereferencing it. Therefore, calls with a selected overload can run normally; if replaced with `value.length()` or `value.intValue()`, null raises an exception.

If you uncomment the line `describe(null);`, the compiler reports an ambiguity **before producing a program to run**, even though both implementations appear to print “null” properly. The compiler does not test-run method bodies to choose a convenient branch.

## 6. With Three Overloads: Adding `Object` Does Not Necessarily Eliminate Ambiguity

Suppose:

~~~java
static void write(Object value) {
    System.out.println("Object");
}

static void write(String value) {
    System.out.println("String");
}

static void write(Integer value) {
    System.out.println("Integer");
}
~~~

These are three illustrative methods placed in the same class. The call `write(null)` is still **ambiguous** because:

1. `Object`, `String`, and `Integer` all apply.
2. Both `String` and `Integer` are more specific than `Object`.
3. There is no subtype relationship between `String` and `Integer`.
4. There is no single most specific method.

The compiler does **not** select `Object` to “avoid a conflict”. Adding a general overload usually increases the list of candidates rather than creating a default precedence rule.

The calls are clearly distinguished:

~~~java
write((Object) null);    // Object
write((String) null);    // String
write((Integer) null);   // Integer
~~~

When designing a public API, also test the case where callers pass a null literal. Adding a new overload that accepts a reference type can turn a previously valid `write(null)` call into a **compilation error** in client source code.

## 7. Interfaces and Subtype Relationships: Consider the Entire Type Hierarchy

Overloads do not necessarily take classes; interfaces are also reference types and can lead to ambiguity.

Example:

~~~java
static void view(CharSequence value) {
    System.out.println("CharSequence");
}

static void view(String value) {
    System.out.println("String");
}
~~~

Because `String` implements `CharSequence`, the call `view(null)` selects the `String` overload. This is a case with a clear subtype relationship.

However:

~~~java
static void view(CharSequence value) {
    System.out.println("CharSequence");
}

static void view(java.io.Serializable value) {
    System.out.println("Serializable");
}
~~~

With the following two overloads:

- `view(null)` is **ambiguous** because both `CharSequence` and `Serializable` are reference types, yet neither interface is a subtype of the other.
- `view("Java")` is also **ambiguous** in this pair of overloads: the `String` argument implements both interfaces, and neither method is more specific.
- `view((CharSequence) null)` selects `CharSequence`; `view((java.io.Serializable) null)` selects `Serializable`.
- **`view((String) null)` is still ambiguous**, because a value whose compile-time type is `String` can convert to **both interfaces**, and casting to String does not make one interface more specific than the other.

The last point is especially important: **casting to a specific type does not always resolve ambiguity**. A cast only helps when it changes the set of applicable methods or their specificity so that a single method wins.

### Standalone Runnable Example with Interfaces

Save the file **`InterfaceNullDemo.java`**:

~~~java
public class InterfaceNullDemo {
    static void show(CharSequence value) {
        System.out.println("CharSequence");
    }

    static void show(java.io.Serializable value) {
        System.out.println("Serializable");
    }

    public static void main(String[] args) {
        // show(null);          // Ambiguous.
        // show("Java");        // Also ambiguous.
        // show((String) null); // Still ambiguous.

        show((CharSequence) null);
        show((java.io.Serializable) null);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceNullDemo.java
java InterfaceNullDemo
~~~

Stdout:

~~~text
CharSequence
Serializable
~~~

Another design option is to give the two methods different names, such as `showCharacters(CharSequence)` and `showSerializable(Serializable)`, when the two behaviors are genuinely different. This avoids requiring callers to cast just so the compiler knows their intent.

## 8. `null` and Arrays: Arrays Are Also Reference Types

`String[]`, `Integer[]`, `int[]`, and all other array types are object types, so an array-typed parameter can accept null.

~~~java
static void inspect(String[] values) {
    System.out.println("String[]");
}

static void inspect(Integer[] values) {
    System.out.println("Integer[]");
}
~~~

`inspect(null)` is ambiguous because the two array types are different and there is no subtype relationship between `String[]` and `Integer[]`. You can choose explicitly:

~~~java
inspect((String[]) null);
inspect((Integer[]) null);
~~~

If there are `inspect(Object)` and `inspect(String[])`, `inspect(null)` selects `String[]` because every array is a subtype of `Object`.

Note how to distinguish between two situations:

- `inspect((String[]) null)`: **the array reference itself is null**.
- `inspect(new String[] {null})`: there is **an actual array object** containing **one null element**.

These two values have compile-time types compatible with `String[]`, but are completely different at runtime. `values.length` on a null array causes a `NullPointerException`; with an array of one null element, `values.length` is 1.

## 9. `null` and Varargs: A Single null Can Be an Array or One Element

A varargs parameter such as `String... names` is actually used like a `String[]` array inside the method body.

~~~java
static void printNames(String... names) {
    if (names == null) {
        System.out.println("array is null");
    } else {
        System.out.println("length=" + names.length);
    }
}
~~~

This is an illustrative method snippet. The two calls below have different meanings:

~~~java
printNames((String[]) null); // Passes a null array reference.
printNames((String) null);   // Passes one null String element.
~~~

In the first call, the parameter `names` is null. In the second call, the varargs mechanism wraps one `String` element holding a null value into an array; `names.length` is 1.

### Complete Program

Save the file **`VarargsNullDemo.java`**:

~~~java
public class VarargsNullDemo {
    static void printNames(String... names) {
        if (names == null) {
            System.out.println("array is null");
            return;
        }

        System.out.println("length=" + names.length);
        if (names.length > 0) {
            System.out.println("first=" + names[0]);
        }
    }

    public static void main(String[] args) {
        printNames((String[]) null);
        printNames((String) null);
        printNames();
        printNames("An", "Binh");
    }
}
~~~

~~~bash
javac -encoding UTF-8 VarargsNullDemo.java
java VarargsNullDemo
~~~

Stdout:

~~~text
array is null
length=1
first=null
length=0
length=2
first=An
~~~

If written without a cast, the call `printNames(null)` is treated by the compiler as a non-varargs call to `String[]`, because null can be converted to an array, and it usually emits a warning suggesting a cast to distinguish the usage. In these cases, you should not rely on the intention that “null is one element” when the syntax can also represent **a null array**. Write the exact cast or an explicit array:

~~~java
printNames(new String[] {null}); // An array with a null element.
~~~

### Two Varargs Overloads Can Also Cause Ambiguity

~~~java
static void send(String... values) { /* ... */ }
static void send(Integer... values) { /* ... */ }
~~~

`send(null)` is ambiguous when considering two array types with no subtype relationship. `send()` can also be ambiguous when both versions apply with an empty varargs list. The way to avoid this is to let callers select one version using a typed argument or to design the API so it does not force users to distinguish branches by unrelated array types.

## 10. Primitives, Wrappers, Boxing, and `null`

A primitive such as `int` cannot accept null. However, the wrapper `Integer` is a reference type and can accept null:

~~~java
static void test(int value) {
    System.out.println("int");
}

static void test(Integer value) {
    System.out.println("Integer");
}
~~~

In this set of overloads:

- `test(5)` selects `test(int)` because the argument `5` is an `int`.
- `test(Integer.valueOf(5))` selects `test(Integer)` because the argument has type `Integer`.
- `test(null)` selects **`test(Integer)`** because `int` cannot accept null, whereas `Integer` can.
- `test((Integer) null)` selects `Integer`; that method must handle the possibility of null if needed.
- `test((int) null)` **does not compile**, because null cannot be cast directly to the primitive `int`.

If only `test(int)` exists, the call `test(null)` has no applicable method; the error message is about an incompatible argument type, **not ambiguity among multiple overloads**.

### Standalone Runnable Java 17+ Example

Save the file **`PrimitiveWrapperNullDemo.java`**:

~~~java
public class PrimitiveWrapperNullDemo {
    static void test(int value) {
        System.out.println("int=" + value);
    }

    static void test(Integer value) {
        System.out.println("Integer=" + value);
    }

    public static void main(String[] args) {
        test(5);
        test(Integer.valueOf(5));
        test(null);
        test((Integer) null);
    }
}
~~~

~~~bash
javac -encoding UTF-8 PrimitiveWrapperNullDemo.java
java PrimitiveWrapperNullDemo
~~~

Stdout:

~~~text
int=5
Integer=5
Integer=null
Integer=null
~~~

The snippet `"Integer=" + value` converts a null wrapper into the string `"null"` during string concatenation; the code does not unbox this value, so it does not throw a `NullPointerException`.

Conversely, if a caller has a variable `Integer x = null;` and passes it to a method **that only takes `int`**, the compiler can insert unboxing at the call site, leading to a `NullPointerException` **before the method body is executed**. Successful compilation does not guarantee that a null wrapper value can be used safely where a primitive is required.

## 11. Why Doesn't the Compiler Choose Based on the Method Body?

Consider:

~~~java
static void parse(String text) {
    if (text == null) {
        System.out.println("No text");
        return;
    }
    System.out.println(text.length());
}

static void parse(Integer number) {
    if (number == null) {
        System.out.println("No number");
        return;
    }
    System.out.println(number.intValue());
}
~~~

The bodies of both overloads handle null safely. However, `parse(null)` is still **ambiguous**.

Java **does not inspect method bodies to guess which overload is more useful**, nor does it automatically prioritize a branch with a catch or null handling. Overload resolution uses type rules and applicability before the program runs. Therefore:

- An overload that handles null better does not get prioritized.
- The return type is also not a switch to choose between two methods that differ only in `String`/`Integer` parameters in a normal call.
- You cannot fix ambiguity by changing the declaration order of methods or moving one overload higher up.
- You may need to change the **expression type at the call site**, the **method name**, or the **set of overloads**.

If the API needs a unified way to handle null, a general `parse(Object)` overload or a `parseMissing()` method may be suitable in design, though you must evaluate whether that changes the meaning of other calls.

## 12. Overload Resolution Has Phases: Fixed First, Varargs Later

Java does not take every overload and measure a simple “similarity”. From an introductory perspective, the compiler proceeds through phases to find applicable methods; roughly speaking:

1. Find applicable methods using **strict conversions** for fixed-arity calls (without boxing/unboxing).
2. If there are no suitable candidates, consider **looser** conversions such as boxing/unboxing for fixed arity.
3. If there are still no matching candidates, consider calls with **varargs**.
4. In the first phase that finds applicable candidates, apply the **most specific** rule; if a single choice cannot be determined and tie-break rules cannot resolve it, report ambiguity.

This is a practical summary; the specification has detailed rules on generic methods, subtypes, accessibility, variable arity, and signatures. What to remember is **never to invent a custom priority order such as “primitive over reference”, “static over instance”, or “the method declared first wins”**.

For `null`, many situations are already ambiguous right among methods taking reference types in the first phase. The existence of another varargs method does not automatically save the call from this ambiguity.

### Case Where One Overload Inherits a More Specific Parameter

~~~java
static void handle(Object value) { /* ... */ }
static void handle(CharSequence value) { /* ... */ }
static void handle(String value) { /* ... */ }
~~~

`handle(null)` selects `handle(String)` because `String <: CharSequence <: Object`. A clear subtype chain ensures there is a single most specific candidate.

However, if `String` is replaced with `Integer`:

~~~java
static void handle(Object value) { /* ... */ }
static void handle(CharSequence value) { /* ... */ }
static void handle(Integer value) { /* ... */ }
~~~

`handle(null)` is ambiguous between `CharSequence` and `Integer`. `Object` is a supertype of both, so it is not the most specific choice.

These snippets only illustrate overload structure and do not use all six methods simultaneously in a single class.

## 13. Why Is `Object value = null` Different from the `null` Literal?

Standalone runnable example, file **`StaticTypeOfArgumentDemo.java`**:

~~~java
public class StaticTypeOfArgumentDemo {
    static void choose(Object value) {
        System.out.println("Object");
    }

    static void choose(String value) {
        System.out.println("String");
    }

    public static void main(String[] args) {
        Object generic = "Java";
        Object missing = null;
        String specific = null;

        choose(generic);
        choose(missing);
        choose(specific);
        choose(null);
        choose((Object) null);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticTypeOfArgumentDemo.java
java StaticTypeOfArgumentDemo
~~~

Stdout:

~~~text
Object
Object
String
String
Object
~~~

Even though `generic` refers to an actual `String` at runtime, the compiler still sees that the argument has declared type `Object` when choosing an overload. `choose(generic)` therefore calls `choose(Object)`. **Do not confuse the dynamic dispatch of overriding with the compile-time selection of overloading.**

If you need to handle objects according to their runtime type, consider polymorphism and instance method overriding, pattern matching with `instanceof`, or other descriptive APIs instead of trying to create a set of overloads and waiting for Java to guess the argument's runtime type.

### Combining Overloading and Overriding: Two Independent Steps

A parent class can define `process(Object)` and `process(String)`, while a subclass overrides `process(String)`. The compiler first selects the applicable overload signature based on the type at the call site; if that signature is an instance method with a matching override, the runtime selects the implementation of the actual object. **Changing the object's contents or having a null value does not make the compiler re-select the overload signature.**

## 14. Null with Generic Methods: Type Inference Does Not Always Eliminate Ambiguity

Generic methods can make overload selection more complex because the compiler infers type variables.

Illustrative example:

~~~java
static <T> void consume(T value) {
    System.out.println("generic");
}

static void consume(String value) {
    System.out.println("String");
}
~~~

With `consume(null)`, in this example the `String` overload is more specific than the generic overload that could accept an appropriate type, so the `String` version is selected. You should not interpret this to mean that every generic method “loses” to a non-generic method; selection depends on the signature and applicability of each overload.

Another situation:

~~~java
static void use(java.util.List<String> values) { /* ... */ }
// Cannot also declare:
static void use(java.util.List<Integer> values) { /* ... */ }
~~~

After **type erasure**, the two signatures `use(List<String>)` and `use(List<Integer>)` both correspond to `use(List)`, so they **cannot coexist as two separate overloads** in this way. The error occurs right at declaration time, before even considering `use(null)`.

When you want an API to handle two kinds of lists, you can choose:
- One generic method for shared handling when the operations are genuinely the same.
- Two descriptive method names if the logic differs.
- A request class/record holding data with its own domain type.
- An intentional branching mechanism inside the method if runtime data types need to be inspected.

### When Lambdas and Method References Appear

Lambdas, method references, and generic method invocations can be expressions evaluated with a target type (**target typing**). If there are multiple overloads taking different functional interfaces, method selection also depends on the function signatures of those interfaces and inference rules. In particular, passing `null` instead of a lambda/function object can create new ambiguity. When encountering this kind of error, the practical fix is usually to declare a variable with the **specific functional interface**, add an intentional cast, or use two different method names.

Do not assume the compiler will pick an overload just because the lambda body seems to fit the method name. Determine the actual type signature.

## 15. Constructor Overloading Is Also Subject to Rules with `null`

It is not only ordinary methods; overloaded constructors can also be ambiguous.

~~~java
class Message {
    Message(String text) { /* ... */ }
    Message(Integer code) { /* ... */ }
}
~~~

`new Message(null)` causes the error **reference to Message is ambiguous** (exact phrasing depends on the compiler version). Both constructors apply and neither is more specific.

How to resolve this when you need to try a specific constructor:

~~~java
Message a = new Message((String) null);
Message b = new Message((Integer) null);
~~~

This is an **illustrative snippet**, not a standalone runnable program. In a real application, a constructor receiving null may reject it immediately through validation; the cast only helps choose the right constructor.

### Static Factories Are a Clearer Design Choice

Instead of overloading two constructors with unrelated reference types, you can provide static factories with names that express intent:

~~~java
static Message fromText(String text) { /* create Message */ }
static Message fromCode(Integer code) { /* create Message */ }
~~~

The two declarations are **API pseudocode**, without a class implementation yet. When a caller writes `Message.fromText(null)`, the choice of behavior is expressed by **name**, without relying on the compiler to infer types across multiple constructors. Factories can also place validation and default values suited to the domain.

## 16. `null` Differs from the String "null", Empty Objects, and Default Values

Some design errors stem from using the same value to represent multiple different states:

| Argument | Expression type | Potential meaning |
| --- | --- | --- |
| `null` | Null type | No reference / not provided, depending on the contract |
| `"null"` | `String` | A string consisting of the four characters n-u-l-l |
| `""` | `String` | Empty string, which is a string object |
| `new String[0]` | `String[]` | Empty String array, not null |
| `new String[] {null}` | `String[]` | Array with one null element |
| `Integer.valueOf(0)` | `Integer` | Wrapper object representing the number 0 |
| `Optional.empty()` | `Optional<T>` | An object representing absence according to the Optional API |

The compiler chooses an overload by the **type of the expression**; it does not automatically treat `""` as “missing string” or `0` as “no number”. It is the method contract that determines whether a value is valid.

One way to clarify when an API has an optional data field:

~~~java
static String displayName(String name) {
    return name == null || name.isBlank() ? "(unknown)" : name;
}
~~~

This is an illustrative method; it accepts null according to a specific rule. If null has no valid meaning, you can reject it early using `Objects.requireNonNull(name, "name")` instead of silently falling back to a default name.

## 17. How Should Ambiguous Overloads Be Fixed?

There are three layers of solutions, from the call site to API design.

### Solution A — Make the Argument Type Clear at the Call Site

Use this when the overloads genuinely have different meanings and the caller knows which one it needs:

~~~java
handle((String) null);
handle((Integer) null);
~~~

Alternatively, declare a variable with a specific type and pass it in. Note that `(String) null` **is not guaranteed** to resolve the issue if both overloads accept different superinterfaces of `String` (such as `CharSequence` and `Serializable`). In that case, you need to cast to the exact desired interface or change the design.

### Solution B — Use Method Names That Express Domain Intent

~~~java
findByUsername(String username);
findByNumericId(Integer id);
~~~

These are **illustrative API signatures**, clearly differing in data role. For `null`, the caller still needs to choose a valid policy, but the method name already indicates which query is intended. This approach is usually better when two overloads carry **two different behaviors** rather than merely two forms of the same data.

### Solution C — A Parameter Object or Domain Type

~~~java
record SearchRequest(String query, Integer limit) {
    SearchRequest {
        if (query == null || query.isBlank()) {
            throw new IllegalArgumentException("query is required");
        }
        if (limit != null && limit <= 0) {
            throw new IllegalArgumentException("limit must be positive");
        }
    }
}
~~~

This is an illustrative Java 17+ type declaration. A method taking `SearchRequest` has a clear signature with one request object, and that type specifies that `query` is required and `limit` is optional. It does not need two overloads with the same name `search(String)` and `search(Integer)`. However, you should not merge two completely independent behaviors into a single request object just to reduce ambiguity errors; the design must still accurately reflect the domain.

### How Should You Not Fix It?

- Do not arbitrarily delete a public overload already used elsewhere without checking compatibility.
- Do not cast null to an arbitrary type just to silence the compiler; you must determine the desired behavior and null policy.
- Do not add an `Object` overload hoping Java will fall back to it when specialized overloads are ambiguous.
- Do not change the return type to try to “distinguish” two methods with the same signature.
- Do not rely on declaration order or on the runtime object type to select an overload.

## 18. Diagnostic Process for `reference to ... is ambiguous` Errors

When encountering a call such as `operation(null)` that reports ambiguity, follow these steps:

1. **List candidate overloads** with the same name and matching call form, including inherited methods if any. Check constructor overloads if using `new`.
2. **Determine the compile-time type of each argument**. The null literal differs from the variables `Object value = null` and `String value = null`.
3. **Filter applicable methods** by parameter count and allowed conversions. Primitives cannot directly accept null; reference types can.
4. **Examine subtype relationships among parameter types**. `String` is more specific than `Object`; `String` and `Integer` have no subtype relationship; two interfaces without an inheritance relationship can both apply.
5. **Consider varargs/boxing/generics when needed**; do not assume that just because there is a method taking `Object` or `Object...`, it wins.
6. **Decide whether to fix the call site or the API**. Cast only when you want a specific overload; rename the method or use a parameter object if ambiguity is a recurring usage issue.
7. **Run null tests** after the code compiles, because resolving ambiguity does not mean the method body handles null correctly.

When the compiler reports conflicting candidates, read the **method signatures** in the error message as well. That is the clue indicating which pair of overloads cannot be distinguished by the current argument types.

### Distinguishing Three Types of Null-Related Errors

| Situation | Error or outcome |
| --- | --- |
| Only `f(int)` exists, calling `f(null)` | No applicable method for the null argument; **not** ambiguity |
| Both `f(String)` and `f(Integer)` exist, calling `f(null)` | Neither candidate can be selected as most specific: **ambiguous** |
| `f(String)` is selected, null is passed, and the body calls `text.length()` | Compilation may succeed; **`NullPointerException` at runtime** |

You must address the right type of error. If there is no applicable method, fix the argument type or value. If it is ambiguous, clarify the overload selection. If it is a `NullPointerException`, check the contract and null handling in the execution flow.

## 19. API Compatibility: Adding an Overload Can Cause Existing Code to Stop Compiling

Suppose the initial version only has:

~~~java
static void submit(Object value) { /* ... */ }
static void submit(String value) { /* ... */ }
~~~

The call `submit(null)` selects `submit(String)`. Later, the library adds:

~~~java
static void submit(Integer value) { /* ... */ }
~~~

Now **recompiled source code** containing `submit(null)` may encounter ambiguity between `String` and `Integer`. This is an example of a **source compatibility** change: a new overload makes an old call site indeterminate.

You must distinguish between recompiled source code and previously compiled binaries. A compiled class usually stores the call to the descriptor of the selected overload; **adding** a new overload to a library generally does not cause the JVM to re-run overload resolution for existing bytecode. However, changing or removing other signatures or behaviors can still cause their own compatibility issues, so public libraries need to be evaluated before release.

Ways to mitigate the risk:

- Use different names for behaviors that take unrelated types.
- Add overloads only when the use case is clear and there are compile-time tests for critical call sites, especially null literals.
- For APIs that grow with many options, use a request object or builder with a consistent null policy.
- Do not view an overload as merely “adding a harmless option”: the compiler must choose among the **entire set of candidates** in the new source context.

## 20. Compiler Prediction Practice

Before reading the answers, try marking “compiles and calls which overload” or “does not compile”.

### Exercise 1 — Parent-Child Relationship

~~~java
static void call(Object value) {
    System.out.println("Object");
}

static void call(Number value) {
    System.out.println("Number");
}

static void call(Integer value) {
    System.out.println("Integer");
}
~~~

With `call(null)`, the result is **Integer** because `Integer` extends `Number`, and `Number` extends `Object`. If you pass `Number n = null; call(n);`, the compiler selects **Number** because the argument's declared type is `Number`.

### Exercise 2 — Two Unrelated Reference Types

~~~java
static void call(String value) {
    System.out.println("String");
}

static void call(StringBuilder value) {
    System.out.println("StringBuilder");
}
~~~

`call(null)` is **ambiguous**. `call((String) null)` selects **String**, and `call((StringBuilder) null)` selects **StringBuilder**. `String` and `StringBuilder` can both hold text, but there is no direct subtype relationship between these two classes.

### Exercise 3 — Primitives and Wrappers

~~~java
static void call(long value) {
    System.out.println("long");
}

static void call(Integer value) {
    System.out.println("Integer");
}
~~~

`call(null)` selects **Integer**; `long` cannot accept null. `call(5)` selects **long** because the `long` method applies via primitive widening in a phase that takes precedence before `int → Integer` boxing.

### Exercise 4 — Overlapping Interfaces

~~~java
static void call(CharSequence value) {
    System.out.println("CharSequence");
}

static void call(java.io.Serializable value) {
    System.out.println("Serializable");
}
~~~

`call("Java")` is ambiguous, because `String` implements both interfaces. `call((String) null)` is still ambiguous. `call((CharSequence) null)` selects **CharSequence** and `call((java.io.Serializable) null)` selects **Serializable**.

### Exercise 5 — Compile-Time Reference Type

~~~java
static void call(Object value) {
    System.out.println("Object");
}

static void call(String value) {
    System.out.println("String");
}
~~~

Inside a method:

~~~java
Object a = "Java";
String b = null;
call(a);
call(b);
~~~

The result is:

~~~text
Object
String
~~~

The runtime object of `a` is String, yet the overload is still selected according to the argument's **declared type Object**.

Exercises 1–5 provide **illustrative method snippets**, not a single standalone program if placed all together in the same file, due to duplicate names and signatures across the exercises. Test each exercise in its own class when practicing.

## 21. Practice Exercises and Self-Assessment Criteria

**Exercise A — Compiler diagnostics:** Create a class with `parse(String)` and `parse(Integer)`, write `parse(null)`, and run `javac` to read the error. Next, fix it by casting to the exact type while keeping explicit null checks in the methods.

**Exercise B — Adding an overload to an API:** Start with `send(Object)` and `send(String)`; test `send(null)`. Add `send(Integer)` and try recompiling. Explain why `send(null)` previously compiled but is now ambiguous.

**Exercise C — Interfaces:** Create overloads `format(CharSequence)` and `format(Serializable)`. Predict the outcome for `format("x")`, `format((CharSequence) null)`, and `format((String) null)`. Explain why casting to String is not enough.

**Exercise D — Varargs:** With `show(String... values)`, test `show((String[]) null)`, `show((String) null)`, `show(new String[] {null})`, and `show()`; print both the `values == null` state and the length when non-null. Do not call `values.length` before checking for null.

**Exercise E — Redesigning an API:** Replace the two overloads `find(String code)` and `find(Integer id)` with `findByCode(String code)` and `findById(int id)`, or a model with a dedicated ID type. Write test cases to ensure null is not interpreted as a valid identifier.

End-of-lesson checklist:

- [ ] I can explain that the null literal works with reference types and cannot be used directly with primitive types.
- [ ] I know that the compiler selects `f(String)` over `f(Object)` for `f(null)` when only those two overloads exist.
- [ ] I know that `f(String)` and `f(Integer)` make `f(null)` ambiguous.
- [ ] I can distinguish between the compile-time type of a variable `Object o = null` and the `null` literal.
- [ ] I know that casting can resolve ambiguity, yet casting to `String` is still insufficient when two overloads take `CharSequence` and `Serializable`.
- [ ] I can distinguish between a null array, an empty array, and an array containing a null element in varargs.
- [ ] I know that a primitive `int` overload cannot accept null, whereas `Integer` can.
- [ ] I can distinguish between a compile-time ambiguity error and a runtime `NullPointerException`.
- [ ] I know that adding a new overload can cause an existing null call to no longer compile.
- [ ] I know when to rename methods, use a domain type, or use a parameter object to avoid forcing callers to cast null.

**Core takeaway:** A call containing `null` does not create a “default version” of a method. Java selects an overload using the **applicable and most-specific rules at compile time**. When multiple parameters have reference types that cannot be compared in specificity, the compiler must report ambiguity to require the programmer to clarify. Understanding this mechanism helps you read errors accurately and design less surprising Java APIs.
