# How must source and target types be compatible in Java pattern matching?

## 1. Distinguishing between the declared type and the actual object's type

When using **pattern matching for instanceof**, Java needs to answer two different questions:

1. **At compile time:** does the static type of the expression on the left (**source type**) allow testing against the type written in the type pattern on the right (**target/pattern type**)?
2. **At runtime:** is the actual value a non-**null** object compatible with the target type?

Java 17 example:

~~~java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Source type **S = Object**, target type **T = String**. The compiler allows the expression because an **Object** reference can point to a **String**. At runtime, the value here is indeed a **String**, so the match succeeds, the variable **text** has static type **String**, and **length()** returns **4**.

Changing the data without changing the source type:

~~~java
Object value = 42;
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

The program **still compiles**: compatibility is determined by the static type **Object**. At runtime, the actual object is an **Integer**, not a **String**, so **instanceof** returns **false**, and the **if** block does not execute. The test fails normally; it does not throw a **ClassCastException** on its own.

Keep in mind: **compilable** does not mean **guaranteed to match at runtime**. On the other hand, a test that Java can prove is invalid or unnecessary may also be rejected by the compiler before execution.

## 2. Three key rules for instanceof type patterns in Java 17

For the expression **expression instanceof T variable**, let **S** be the static type of **expression** and **T** be the type of the pattern.

**Rule 1 — the left-hand side must have a reference type or the null type.** In Java 17, type patterns in **instanceof** use reference types, such as **String**, **Number**, **Runnable**, or **String[]**; primitive type patterns such as **int x** are not used directly.

~~~java
Object value = 10;
if (value instanceof Integer number) {
    System.out.println(number + 1);
}
~~~

**Integer** is a reference wrapper type. **10** is boxed into an **Integer** when assigned to **Object**. Conversely, **int value = 10; if (value instanceof Integer n) ...** is invalid in Java 17 because the left-hand side has the primitive type **int**.

**Rule 2 — S must be cast-convertible (checkcast-compatible) to T.** The Java 17 specification refers to this as **downcast compatible** (or testing whether a casting conversion exists). Practically speaking: at compile time, there must still be a possibility that a valid object exists that can be viewed as **T** when the expression has type **S**. S and T do not have to be in a direct parent–child relationship; two interfaces can also be compatible if a class can implement both at the same time.

**Rule 3 — for type patterns in Java 17 instanceof, S must not be a subtype of T.** If the expression already has static type **T** or a subtype of **T**, the compiler reports an error for a pattern type that is too general. Such a check adds no necessary type-classification information.

~~~java
String text = "hello";

// Invalid in Java 17: String is already a subtype of CharSequence.
// if (text instanceof CharSequence sequence) { ... }

// Invalid in Java 17: source type and pattern type are the same.
// if (text instanceof String same) { ... }

// Valid: call the method directly on a variable whose type is already specific enough.
System.out.println(text.length());
~~~

Do not confuse Rule 3 with the traditional **instanceof** that does not declare a pattern variable. The expression **text instanceof CharSequence** (without **sequence**) is valid type comparison syntax in Java 17, whereas **text instanceof CharSequence sequence** is a type pattern rejected by the compiler when the static source type is already a subtype of the target.

The three rules above apply to **instanceof type patterns in Java 17**. Newer Java versions may add other pattern forms and checks; when learning Java 17, use the rules and compiler of Java 17 itself.

## 3. Common type relationships

| Source type S (declared) | Pattern type T | Valid for Java 17 instanceof type pattern? | Reason |
| --- | --- | --- | --- |
| **Object** | **String** | Yes | Object can hold a String |
| **CharSequence** | **String** | Yes | String implements CharSequence; runtime concrete-type check is needed |
| **Number** | **Integer** | Yes | Integer is a subtype of Number |
| **Object** | **String[]** | Yes | Arrays are reference types; Object can hold a String array |
| **Object** | **List<?>** | Yes | Can check for a list type without requiring knowledge of the element type |
| **InterfaceA** | **InterfaceB** | Possibly | A class may exist that implements both interfaces |
| **String** | **Integer** | No | Two final classes cannot have a common object that is both a String and an Integer |
| **String** | **CharSequence** | No | S is already a subtype of T; this type pattern is too general in Java 17 |
| **String** | **String** | No | S and T are identical; type pattern is rejected in Java 17 |
| **int** | **Integer** | No | int is not a reference type on the left-hand side of instanceof in Java 17 |
| **Object** | **List<String>** | No | Cannot check the generic String element type with this type pattern due to type erasure |

The table only considers statements of the form **source instanceof Target variable** in Java 17, not every form of casting or every form of **switch** pattern. For interfaces, **“Possibly”** depends on the specific relationships and constraints, especially if the source type is a **final** class that does not implement the target interface.

## 4. Parent–child relationships: the direction of the check matters

Consider the **CharSequence** interface, with implementations such as **String** and **StringBuilder**:

~~~java
CharSequence source = new StringBuilder("abc");

if (source instanceof String text) {
    System.out.println("String: " + text);
} else {
    System.out.println("Không phải String");
}
~~~

The compiler accepts this because the source type **CharSequence** can point to a **String**. At runtime, the object is a **StringBuilder**, so the **else** branch is taken. If **source = "abc"** is assigned, the type pattern matches and **text** is bound.

Going in the opposite direction in Java 17:

~~~java
String source = "abc";

// Invalid for a type pattern:
// if (source instanceof CharSequence sequence) { ... }

// Use the available method directly:
System.out.println(source.length());
~~~

With **String source**, creating the pattern **CharSequence sequence** is rejected by the rule that the source type is a subtype of the pattern type. If you genuinely need to represent a value through an interface type, you can assign it explicitly:

~~~java
CharSequence sequence = source;
System.out.println(sequence.length());
~~~

You should not cast through **Object** just to make an unnecessary type pattern compile. Doing so hurts readability without providing any useful type check.

Similarly, going from **Number** to **Integer** is a reasonable narrowing check:

~~~java
Number n = Integer.valueOf(7);
if (n instanceof Integer integer) {
    System.out.println(integer + 1);
}
~~~

The output is **8**. If **n** holds a **Double**, the **Integer** pattern does not match and the branch does not run.

## 5. Two interfaces do not need a direct inheritance relationship

A common misconception is that S and T must lie on the same parent–child chain. In reality, a class can implement **multiple interfaces**, so a reference of interface type A can hold an object that also implements interface B.

~~~java
interface Named {
    String name();
}

interface Tagged {
    String tag();
}

final class Item implements Named, Tagged {
    public String name() { return "item"; }
    public String tag() { return "v1"; }
}

static String label(Named source) {
    if (source instanceof Tagged tagged) {
        return source.name() + ":" + tagged.tag();
    }
    return source.name();
}
~~~

The snippet above illustrates declarations inside a valid class or file; it is not a complete program with **main**. The source type is **Named** and the target type is **Tagged**. Because an **Item** can exist that implements both, the check is valid. The compiler does not require **Named extends Tagged** or vice versa.

However, if the source type is a **final** class that does not implement the target interface and cannot have subclasses, that intersection type can be impossible. For example, **String** is a final class and does not implement **Runnable**, so **String value; value instanceof Runnable task** is invalid in Java 17.

## 6. Runnable Java 17 example: multiple source and target types

Create the file **TypeCompatibilityDemo.java** with the following full content:

~~~java
public class TypeCompatibilityDemo {
    interface Named {
        String name();
    }

    interface Tagged {
        String tag();
    }

    static final class Both implements Named, Tagged {
        @Override
        public String name() { return "note"; }

        @Override
        public String tag() { return "v1"; }
    }

    static final class OnlyNamed implements Named {
        @Override
        public String name() { return "plain"; }
    }

    static String describe(Object source) {
        if (source instanceof String text) {
            return "String:" + text.length();
        }
        if (source instanceof Number number) {
            return "Number:" + number.intValue();
        }
        if (source instanceof CharSequence sequence) {
            return "CharSequence:" + sequence.length();
        }
        return source == null ? "null" : "other";
    }

    static String inspectNumber(Number source) {
        if (source instanceof Integer integer) {
            return "Integer:" + (integer + 1);
        }
        return "not Integer";
    }

    static String inspectInterfaces(Named source) {
        if (source instanceof Tagged tagged) {
            return source.name() + ":" + tagged.tag();
        }
        return source.name() + ":untagged";
    }

    static String inspectArray(Object source) {
        if (source instanceof String[] values) {
            return "String[]:" + values.length;
        }
        return "not String[]";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(12));
        System.out.println(describe(new StringBuilder("abc")));
        System.out.println(describe(null));

        System.out.println(inspectNumber(7));
        System.out.println(inspectNumber(2.5));

        System.out.println(inspectInterfaces(new Both()));
        System.out.println(inspectInterfaces(new OnlyNamed()));

        System.out.println(inspectArray(new String[] {"A", "B"}));
        System.out.println(inspectArray(new int[] {1, 2}));
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac -encoding UTF-8 TypeCompatibilityDemo.java
java TypeCompatibilityDemo
~~~

Output:

~~~text
String:4
Number:12
CharSequence:3
null
Integer:8
not Integer
note:v1
plain:untagged
String[]:2
not String[]
~~~

**Step-by-step explanation:**

1. **describe** takes a parameter declared with type **Object**, so it can test the **String**, **Number**, and **CharSequence** patterns. The object **"Java"** matches **String** and has length 4.
2. The number **12** is autoboxed to **Integer**, matching the **Number** pattern, so **intValue()** returns 12.
3. **StringBuilder("abc")** does not match the **String** branch, but matches **CharSequence**, with length 3.
4. **null** does not match any **instanceof** type pattern, so execution reaches the branch returning **null** as a descriptive string.
5. The **Number** parameter in **inspectNumber** can be tested against the subtype **Integer**. Integer 7 matches and produces 8; Double 2.5 does not match and returns **not Integer**.
6. **Both** implements both interfaces so **Named → Tagged** matches; **OnlyNamed** does not implement **Tagged** so it takes the fallback branch.
7. **String[]** is a reference array type that a type pattern can test directly; an **int[]** object is not a **String[]**. **int[]** itself is still an array reference type, even though its elements are primitives.

This example uses no preview features and does not require Java 21. Each pattern variable is used only after it has matched, in accordance with **flow scoping** in the Java 17 compiler.

## 7. Distinguishing compile-time errors from runtime match failures

**Case A — valid at compile time, but does not match at runtime:**

~~~java
Object source = Integer.valueOf(7);
System.out.println(source instanceof String); // false
~~~

The compiler sees that the source type **Object** is general enough that it could be a **String**, so it allows the test. The actual object is **Integer**, so the result is **false**. The type pattern version **source instanceof String text** is also valid and does not bind **text** when it fails to match.

**Case B — rejected at compile time because the two types cannot meet:**

~~~java
String source = "Java";
// if (source instanceof Integer number) { ... } // Compile error
~~~

**String** and **Integer** are both final classes with no compatible subtype relationship. The compiler does not need to wait until runtime to conclude that the test has no valid outcome.

**Case C — rejected because the type pattern is too general:**

~~~java
String source = "Java";
// if (source instanceof Object object) { ... } // Compile error
// if (source instanceof String text) { ... }  // Compile error
~~~

This is a notable difference for **type patterns** in Java 17. If you only want to check for null, use **source != null**. If you need a wider-typed variable, declare **Object object = source** or **CharSequence text = source** instead of an unconditional type pattern.

**Case D — a direct cast can throw an exception:**

~~~java
Object source = Integer.valueOf(7);
// String text = (String) source; // Compiles, but throws ClassCastException at runtime.
~~~

A cast may be valid in terms of type relationships at compile time yet fail on the actual object. A type pattern lets you branch before using the properly typed variable:

~~~java
Object source = Integer.valueOf(7);
if (source instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Không phải String");
}
~~~

**Case E — null:** with **Object source = null**, both **source instanceof String** and **source instanceof String text** evaluate to **false**. This does not make the expression invalid at compile time; the static type can still be tested against String.

## 8. Generics, type erasure, and arrays

In Java 17, an **instanceof** type pattern generally tests a **raw/runtime-reifiable type**; you cannot rely on it to verify generic type arguments that have been erased.

~~~java
Object source = java.util.List.of("A", "B");

if (source instanceof java.util.List<?> values) {
    System.out.println(values.size());
}
~~~

Valid example: the compiler knows **values** is a **List<?>** and can call **size()**. However, the elements in **values** are seen with an unknown type (usually **Object** when read); the pattern does not prove that all elements are **String**.

Invalid example in Java 17:

~~~java
Object source = java.util.List.of("A", "B");

// Cannot check the String type argument of List this way:
// if (source instanceof java.util.List<String> values) { ... }
~~~

**List<String>** is not a suitable runtime-reifiable type for this check; generic type arguments undergo **type erasure**. If you need to ensure a list contains strings, check each element individually or design the API with strong parameterized types from the start.

With arrays, more component-type information is preserved at runtime, so **source instanceof String[] strings** is a valid test from an **Object** source; **int[]** is a different array type. Do not use array support to infer that Java 17 also has direct patterns for primitive **int** or can check arbitrary generic type arguments.

## 9. Common mistakes when choosing source and target types

- **Looking at the value and forgetting the declared type:** **Object source = "abc"** and **String source = "abc"** hold the same actual object but have different validity rules for **source instanceof String text**. The first is valid; the second is rejected in Java 17.
- **Thinking instanceof is like a conversion:** the pattern **String text** does not convert an **Integer** into a string and does not parse **"42"** into a number. It only tests and binds the variable if the object is already compatible.
- **Using a pattern when the variable already has the needed type:** from **String** to **CharSequence**, you can assign directly; there is no need to introduce a pattern just to change the reference type.
- **Assuming two interfaces must inherit from each other:** a class can implement two independent interfaces. However, if the source is a final class that does not implement the target interface, the test can be rejected at compile time.
- **Confusing null with a type error:** **instanceof** with null returns **false**, not **ClassCastException**. If business logic needs to distinguish null from wrong-type data, handle it separately.
- **Checking generic type arguments with instanceof:** **List<?>** is generally valid; **List<String>** cannot be verified directly from **Object** using a Java 17 type pattern.
- **Using a primitive type on the left-hand side:** Java 17 requires the left-hand side of **instanceof** to have a reference type or the null type. If the input is **int** and needs to be used as **Integer**, consider boxing or an explicitly typed API instead of forcing a pattern check.
- **Not distinguishing between kinds of instanceof:** **value instanceof SomeType** is a classic type comparison; **value instanceof SomeType name** is a pattern match and carries the additional rule against unconditional subtypes.
- **Using the pattern variable in the wrong branch:** the pattern variable can only be used where the compiler proves it has matched. The source/target types may be valid, yet the program still fails to compile if the variable is referenced on an unmatched path.

## 10. How to choose and quickly verify in practice

Before writing an **instanceof T variable** expression, follow this order:

1. Identify the **static type S** of the left-hand expression from its declaration and Java's type rules, rather than looking only at the object assigned in an example.
2. Identify the desired **pattern type T**. In Java 17, it must be a suitable reference type that can be tested at runtime.
3. Ask **can S be validly checked/cast to T?** If the two types are definitely disjoint (for example, two unrelated final classes), the expression is invalid.
4. Ask **is S already a subtype of T?** If so, Java 17 does not allow this type pattern in **instanceof**. Call the method directly or assign the reference to the needed type.
5. If compilation succeeds, remember that a **runtime match** still depends on the actual object, and **null** never matches.
6. Use the pattern variable only in scopes guaranteed to be matched; for generic data and business rules, add separate checks.
7. Test with at least one matching object, one non-matching object, and null; run **javac** with the project's exact Java version.

### Quick self-check exercise

Consider the following code snippet (Java 17):

~~~java
Object a = "text";
Number b = Integer.valueOf(3);
CharSequence c = new StringBuilder("x");
String d = "text";
~~~

Predictions:

- **a instanceof String s**: valid; matches at runtime.
- **b instanceof Integer i**: valid; matches at runtime.
- **c instanceof String t**: valid; does not match at runtime against **StringBuilder**.
- **d instanceof Object o**: compile error with a type pattern in Java 17 because the source type **String** is already a subtype of **Object**.
- **d instanceof Integer i**: compile error because **String** and **Integer** cannot both be the type of a single object.
- **d instanceof CharSequence**: valid because this is a type comparison that does not declare a pattern variable; with **d** non-null, the result is true.

These predictions help separate three concerns: **compile-time compatibility**, **runtime type matching**, and **the scope/necessity of a pattern variable**.

## Reference specifications

- [Java Language Specification 17, §14.30.1 — Kinds of Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30.1): defines type patterns and compatibility requirements.
- [Java Language Specification 17, §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): distinguishes type comparison from pattern matching, compatibility checks, and null handling.
- [Java Language Specification 17, §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): conversion relationships used in compatibility checks.

**Conclusion:** with an **instanceof type pattern** in Java 17, the source type and target type must permit a meaningful type check: the source must be compatible so it can be tested against the target, while not already being a subtype of the pattern type itself. Once the compiler allows it, whether a match occurs still depends on the actual object and the **non-null** condition. Understanding these three layers helps you choose the right pattern, predict compile errors, and avoid confusing type checking with casting.