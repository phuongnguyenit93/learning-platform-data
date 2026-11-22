# Null Values, Operation Limits on `T`, and the Default `Object` Type in Java Generics

## 1. Objectives

When writing **class Box<T>** or **static <T> T identity(T value)**, we have not yet specified whether T is String, Integer, Number, or another type. This is why Java allows only operations guaranteed to be valid for every type that T could represent.

Three foundational questions of this lesson:

1. **Can T hold null?** Yes. Type arguments in Java generics are normally reference types, and null can be assigned to the corresponding reference-type variables; there is no default “non-null” guarantee.
2. **With an unbounded T, which methods can be called?** Primarily the methods available on Object, because T has an implicit upper bound of Object. You cannot assume T has the API of String, Number, or a custom interface.
3. **Is T literally Object?** No. T is a **type variable** that preserves type relationships across multiple positions in a declaration. The Object upper bound indicates the minimum allowed operations; it does not replace T with Object in source-level type checking.

This lesson uses Java 17+; programs with filenames and run commands are standalone examples, while snippets marked “compilation error illustration” intentionally fail to compile.

## 2. An Unbounded `T` Has a Default Upper Bound of `Object`

Consider the declaration:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

In **class Box<T>**, the symbol T declares an **unbounded type parameter**. In terms of upper bounds, Java treats it equivalently to:

~~~java
class Box<T extends Object> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Here **extends Object** is an explicit upper bound; writing it out still does not turn T into Object. Java accepts a type argument of any reference type compatible with the bound, such as String, Integer, StringBuilder, an interface type, an array type, or a parameterized type. **Box<String>** and **Box<Integer>** are two valid usages of the same declaration.

Usage example inside a method:

~~~java
Box<String> text = new Box<>("hello");
Box<Integer> count = new Box<>(42);
Box<int[]> numbers = new Box<>(new int[] { 1, 2, 3 });

String s = text.get();
Integer n = count.get();
int[] a = numbers.get();
~~~

Conversely, **Box<int>** is invalid: int is a primitive type and cannot directly serve as a type argument to a generic class. Use the wrapper type **Integer** or another reference type.

The **default Object upper bound** has two distinct aspects:

- **In Java source:** the compiler can only trust that every value of T is compatible with Object and has the APIs guaranteed by that upper bound. In a concrete usage like Box<String>, the compiler still knows get() has static type String.
- **In generics implementation:** an unbounded T usually undergoes *type erasure* to Object in bytecode. Type erasure enables runtime compatibility; it does not remove source-code type checking prior to compilation.

A generic declaration does not automatically supply specialized behavior for T. To let the compiler allow calling a method of Number or CharSequence, you must declare an appropriate bound or supply an external operation for T.

## 3. `null` with Type Parameter `T`

In Java, **null** is a special reference value indicating no object is referenced. Null can be converted to any reference type, including a type represented by T in standard generics.

~~~java
class Holder<T> {
    T value;

    Holder(T value) {
        this.value = value;
    }

    void clear() {
        value = null; // Valid since T is a reference type
    }

    boolean isNull() {
        return value == null;
    }
}
~~~

All of the following compile once class Holder is declared:

~~~java
Holder<String> name = new Holder<>(null);
Holder<Integer> size = new Holder<>(null);
Holder<Number> amount = new Holder<>(null);

String text = name.value;   // text receives null
Integer number = size.value; // number receives null
~~~

Even when the type argument is Integer, **null** is not the integer 0. Integer is a wrapper/reference type, and any Integer reference can still be null.

Constraining with **extends** does not implicitly exclude null:

~~~java
class NumberHolder<T extends Number> {
    T value;

    NumberHolder(T value) {
        this.value = value;
    }
}

// Inside a method body:
// NumberHolder<Integer> n = new NumberHolder<>(null); // Valid
~~~

The Number bound only restricts the **type** that T is permitted to represent. It does not guarantee that an **actual value** is always present. Likewise, **<T extends Comparable<T>>**, **<T extends CharSequence>**, and **<T extends Runnable>** do not automatically create a non-null constraint.

### Passing `null` to a Generic Method

A generic method can accept null as an argument:

~~~java
static <T> T echo(T input) {
    return input;
}
~~~

A call like **String result = echo(null)** can be valid; the compiler uses the target-type context to infer an appropriate T and the received result is null. You can also specify the type explicitly to state intent:

~~~java
String name = GenericNullDemo.<String>echo(null);
~~~

The line above illustrates an explicit call when **echo** is an accessible static method in a class named GenericNullDemo. The **<String>** at the call site is a method type argument; **<T>** before the return type in the declaration is a type parameter.

Do not assume null identifies a single unique type on its own. In expressions with overloading or complex type inference, null can make method selection ambiguous or require additional type information for the compiler. In that case, a target variable type, type witness, or cast can clarify; the right fix depends on the signatures in play.

## 4. Safe Null Checks on `T`

Because T is a reference type, we can compare it against null with **==** or **!=**:

~~~java
static <T> boolean missing(T value) {
    return value == null;
}

static <T> boolean present(T value) {
    return value != null;
}
~~~

These two comparisons require no bound. When T variables are non-null, **==** between two references checks whether they point to the same object; it is **not** equivalent to content comparison via equals.

A common pattern when needing to read properties of T:

~~~java
static <T> String describe(T value) {
    if (value == null) {
        return "(không có giá trị)";
    }
    return value.getClass().getSimpleName() + ": " + value;
}
~~~

The if branch avoids calling **getClass()** on null. The String concatenation expression with value uses string conversion per string concatenation semantics; it does not imply T supports any arithmetic operations.

If content comparison is needed and either value could be null, use **Objects.equals(a, b)**:

~~~java
import java.util.Objects;

class Equality {
    static <T> boolean same(T left, T right) {
        return Objects.equals(left, right);
    }
}
~~~

**Objects.equals** returns true when both are null, false when only one side is null, and when both are non-null calls equals per the left-hand object's contract. It prevents NullPointerException from calling **left.equals(right)** directly when left may be null.

Note that equals(Object) does not have a generic signature guaranteeing both arguments belong to the same type; type parameter T in the same example expresses a relationship between the two parameters for compiler inference, yet Object.equals(Object) still accepts any Object.

### `null` Differs from “No Element Present”

A custom generic container may use null as a “no data yet” signal, but that is an **API convention**, not a rule of generics.

~~~java
final class Slot<T> {
    private T item;

    void put(T value) {
        item = value;
    }

    boolean hasNonNullValue() {
        return item != null;
    }
}
~~~

If an API needs to distinguish **“not yet assigned”** from **“assigned the value null”**, inspecting item == null alone is insufficient. You must add a state flag or use an appropriate presence/absence representation. For example:

~~~java
final class NullableSlot<T> {
    private boolean assigned;
    private T value;

    void put(T value) {
        this.value = value;
        this.assigned = true;
    }

    boolean isAssigned() {
        return assigned;
    }

    T get() {
        if (!assigned) {
            throw new IllegalStateException("Chưa gán");
        }
        return value;
    }
}
~~~

A NullableSlot on which put(null) was called still has isAssigned() == true and get() returns null; it differs from the state where put was never called. Do not confuse a generic type's ability to store null with a container's data-representation policy.

## 5. Default `Object` Operations Available on `T`

With **an explicitly unbounded T**, public members of Object can be called on a T variable if access rules are satisfied. The most commonly useful methods are **toString()**, **equals(Object)**, **hashCode()**, and **getClass()**.

~~~java
static <T> String asText(T value) {
    return value.toString();
}

static <T> boolean matches(T value, Object other) {
    return value.equals(other);
}

static <T> int hash(T value) {
    return value.hashCode();
}

static <T> Class<?> runtimeClass(T value) {
    return value.getClass();
}
~~~

All of these methods **compile** with an unbounded T. However, passing null will cause each of those methods to throw **NullPointerException** at invocation time. “Which methods may be called on T” is a **static type** question; “whether the receiver is null” is a **runtime value** question.

Object also has public synchronization-related methods such as wait() and notify(), though those are not APIs you should invoke just because T has an Object bound. Protected methods like clone() do not automatically become publicly callable in every context; Java access restrictions still apply.

Sample operations table:

| Expression where T is unbounded | Compiles? | Condition/meaning |
| --- | --- | --- |
| value == null | Yes | Reference check |
| value != null | Yes | Reference check |
| Object o = value | Yes | T has upper bound Object |
| String s = value.toString() | Yes | Object has toString(); null causes NPE |
| int h = value.hashCode() | Yes | Object has hashCode(); null causes NPE |
| boolean b = value.equals(other) | Yes | Object has equals(Object); null causes NPE |
| Class<?> c = value.getClass() | Yes | Object has getClass(); null causes NPE |
| value.length() | No | Object does not declare length() |
| value.intValue() | No | Object does not declare intValue() |
| value.compareTo(other) | No | Object does not declare compareTo() |
| value + 1 | No for general numeric addition | T is not known to be a numeric type |
| new T() | No | Cannot instantiate a type variable directly |
| T.class | No | Type variables cannot be used in class literals |
| new T[3] | No | Generic array creation |
| value instanceof T | No | Regular T is not reifiable at runtime |

**getClass()** returns the actual runtime class of the object (when non-null), not guaranteed information about the type argument T from the variable declaration. For example, when a T actually holds an ArrayList<String>, getClass() returns the ArrayList class; you cannot deduce from it the specific String type argument used at the source.

### `toString` and `String.valueOf` Differ on `null`

**value.toString()** throws NullPointerException if value is null. Meanwhile, **String.valueOf(value)** is a null-safe alternative: it accepts an Object reference and returns the string **"null"** when the argument is null.

~~~java
static <T> String safeToText(T value) {
    return String.valueOf(value);
}
~~~

If you need a custom label when data is absent, check explicitly:

~~~java
static <T> String display(T value) {
    return value == null ? "(trống)" : value.toString();
}
~~~

Do not overuse toString() for business logic or comparisons: it primarily serves string representation and can be overridden with unstable formatting.

## 6. Why Doesn't the Compiler Allow Calling `String` or `Number` APIs on `T`?

Look at the intentionally broken code:

~~~java
// Compilation error illustration; do not save as a runnable program.
class InvalidOperations<T> {
    int size(T value) {
        return value.length();    // Error: T might not be a CharSequence
    }

    double convert(T value) {
        return value.doubleValue(); // Error: T might not be a Number
    }

    T plus(T a, T b) {
        return a + b;             // Error: no general arithmetic addition for T
    }
}
~~~

Even if you **intend to use only InvalidOperations<String>**, the class itself must be valid for **every type argument** satisfying T's bound. A generic class body cannot compile solely on the assumption that it will be used with a single subtype.

Likewise, the compiler does not infer methods from how T is named. **T** is not short for “Text”, **N** does not automatically imply Number, and **V** does not enable addition. Only type/bound declarations and the methods guaranteed by them determine valid operations.

One special case to read properly: string concatenation **value + "!"** can compile with T because it is **string concatenation** with a String operand, not arithmetic addition on T. It does not mean value supports the plus operator.

### Approach 1: Add an Appropriate Bound

To call **length()** on a general character sequence:

~~~java
static <T extends CharSequence> int lengthOf(T value) {
    return value.length();
}
~~~

CharSequence declares length(), so the compiler knows T has that method. For instance, both String and StringBuilder implement CharSequence.

To read a numeric representation:

~~~java
static <T extends Number> double doubled(T value) {
    return value.doubleValue() * 2.0;
}
~~~

Number provides doubleValue(); extracting a double and multiplying by 2.0 is valid. However, **value + value** is still not a valid generic operator: the Number bound does not turn T into a primitive type and does not define `+` operator overloading.

To order values of the same type T:

~~~java
static <T extends Comparable<T>> T max(T left, T right) {
    return left.compareTo(right) >= 0 ? left : right;
}
~~~

T must implement Comparable<T>, so the compiler allows calling compareTo(T). **max("a", "z")** is valid for String, whereas a class that does not implement a matching Comparable cannot serve as the type argument.

### Approach 2: Pass Behavior as a Parameter

Not every type has a “natural” ordering. If you do not want to require T to implement Comparable, accept **Comparator<? super T>**:

~~~java
static <T> T maxBy(T left, T right,
                   java.util.Comparator<? super T> comparator) {
    return comparator.compare(left, right) >= 0 ? left : right;
}
~~~

The passed Comparator supplies comparison behavior; T itself remains unbounded. This generic API design is often more flexible when the same type has multiple comparison criteria (length, name, priority).

You can also accept **Function<T, R>**, **Predicate<T>**, **Supplier<T>**, or your own custom interface to supply operations that Object lacks. Choosing between a bound and passing a strategy depends on the API's actual relationships.

### Approach 3: Multiple Bounds When Combining APIs

~~~java
static <T extends Number & Comparable<T>> T largerNumber(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
~~~

T must be a subtype of Number **and** implement Comparable<T>. Number is the class bound and comes before the interface bound. Inside the body, both **doubleValue()** and **compareTo()** can be used. **&** joins bounds, unlike commas between multiple type parameters.

When the bound is a single interface:

~~~java
static <T extends Runnable> void runTask(T action) {
    action.run();
}
~~~

Java still uses the **extends** keyword, not **implements**, in type parameter declarations. Even with a bound, **action can be null** and calling action.run() will throw NPE.

## 7. `T` Is Not `Object`: Type Relationships Are Stronger Than `Object`

Distinguish three signatures:

~~~java
static Object passObject(Object value) {
    return value;
}

static <T> T passGeneric(T value) {
    return value;
}

static <T> Object passGenericAsObject(T value) {
    return value;
}
~~~

- **passObject(Object)** accepts Object and only guarantees a static return type of Object. When called with String, subsequent calling code usually needs a cast to receive String.
- **passGeneric(T)** expresses **the same T** on both input and output. When the compiler infers T as String, the return value has static type String without a manual cast at the call site.
- **passGenericAsObject(T)** uses T in the parameter yet **throws away the type relationship on the return type** by declaring Object. That is usually a redundant design if T contributes to no other relationship.

Call-site examples:

~~~java
// The methods above reside in an accessible class.
Object a = passObject("Java");
String b = passGeneric("Java");
// String c = passObject("Java"); // Compile-time error: Object cannot automatically be assigned to String
~~~

In particular, from the Object upper bound you **cannot** deduce that any Object can be assigned to an arbitrary T variable:

~~~java
// Compile-time error illustration:
static <T> T wrong() {
    Object any = new Object();
    return any; // Error: Object is not guaranteed to be T
}
~~~

For a call where T is chosen as String, an arbitrary Object is not necessarily a String. Assigning **T to Object** is safe; assigning **Object to T** requires an appropriate check/conversion. If you force an unchecked cast from Object to T, you can get an unchecked warning and fail at runtime. Avoid using casts to paper over missing type relationships.

A similar confusion is treating **List<T>** like **List<Object>**. When T is String, List<String> is not a subtype of List<Object> because generic types such as List are **invariant** in their type arguments. Use **List<?>** or a bounded wildcard to express flexibility at usage sites, rather than arbitrarily replacing T with Object.

## 8. `null` Values and Calls That Lead to `NullPointerException`

Suppose T is Integer:

~~~java
static <T extends Number> double asDouble(T input) {
    return input.doubleValue();
}
~~~

Calling **asDouble(null)** still compiles yet throws NPE at **input.doubleValue()**. Adding extends Number provides an API, not a runtime value check.

With wrapper values subject to auto-unboxing, errors can even happen when code does not directly call a method:

~~~java
Integer wrapped = null;
// int primitive = wrapped; // Compiles, yet throws runtime NPE on unboxing
~~~

Likewise, **Box<Integer>** can hold null; extracting Integer and assigning it to int can throw NPE due to unboxing. Do not equate “generic type argument is Integer” with “there is always a valid integer”.

**Some ways to guard when using T:**

- Check **if (value == null)** before accessing members or unboxing.
- Use **Objects.requireNonNull(value, "value")** at API boundaries if the contract requires a value. This method returns the reference itself when non-null, and throws NullPointerException with the message when null.
- If null is a valid state, document the contract clearly and handle it conditionally. Do not silently assume non-null rules for every generic API.
- **Optional<T>** can be used in contexts suitable for representing “presence/absence of a value”, though Optional does not allow the wrapped value itself to be null. **Optional.ofNullable(value)** turns null into Optional.empty().
- If compile-time null-safety is required, standard Java 17 does not automatically enforce it for every T; project nullness annotations/analysis tools and framework contracts can be used, though they are not automatic guarantees provided solely by `<T>` syntax.

### Methods Returning `T` and Non-Null Policies

~~~java
static <T> T required(T value) {
    return java.util.Objects.requireNonNull(value, "value");
}

static <T> T orElse(T value, T fallback) {
    if (value != null) {
        return value;
    }
    return java.util.Objects.requireNonNull(fallback, "fallback");
}
~~~

**required** preserves result type T while validating that the input is non-null. **orElse** returns value if present, otherwise returns fallback and requires fallback to be non-null. Both methods enforce clear runtime policies while type parameter T preserves the static type relationship between input and output.

With an unbounded type parameter, **Objects.requireNonNull** is especially convenient: it is declared generically and preserves the static type of the expression after validation without needing a cast back to T.

## 9. Standalone Runnable Example: `null`, `Object`, and `T` Type Relationships

Save as **NullAndObjectDemo.java**:

~~~java
import java.util.Objects;

public class NullAndObjectDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }

        boolean isEmpty() {
            return value == null;
        }
    }

    static <T> String describe(T value) {
        if (value == null) {
            return "(null)";
        }
        return value.getClass().getSimpleName() + ":" + value.toString();
    }

    static <T> boolean same(T left, T right) {
        return Objects.equals(left, right);
    }

    static <T> T echo(T value) {
        return value;
    }

    public static void main(String[] args) {
        Box<String> greeting = new Box<>(null);
        System.out.println(greeting.isEmpty());
        System.out.println(describe(greeting.get()));

        greeting.set("Java");
        String message = echo(greeting.get());
        System.out.println(describe(message));

        System.out.println(same("ok", "ok"));
        System.out.println(same(null, "ok"));
        System.out.println(describe(21));
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac -encoding UTF-8 NullAndObjectDemo.java
java NullAndObjectDemo
~~~

Stdout:

~~~text
true
(null)
String:Java
true
false
Integer:21
~~~

Explanation:

1. Box<T> does not require an initial non-null value. Box<String>(null) is valid; isEmpty accurately checks **value == null**.
2. describe is called with null and returns **"(null)"**, avoiding getClass()/toString() on a null receiver.
3. After set("Java"), echo is a generic method returning the same T it received, so the compiler permits assigning the result to String.
4. The calls to same use Objects.equals, which handles null on either or both sides.
5. For the literal 21, the generic type is inferred as Integer due to autoboxing; describe receives an Integer object, calls Object.getClass() and Object.toString() (overridden by Integer), producing **Integer:21**.

**Runnability:** the file has only one public class matching the filename; all nested classes and methods are fully declared. Stdout does not depend on hashCode or nondeterministic formatting.

## 10. Standalone Runnable Example: Bounds Needed to Call Specialized Methods

Save as **BoundedOperationsDemo.java**:

~~~java
import java.util.Comparator;

public class BoundedOperationsDemo {
    static <T extends CharSequence> int characters(T value) {
        return value.length();
    }

    static <T extends Number> double twice(T value) {
        return value.doubleValue() * 2.0;
    }

    static <T extends Number & Comparable<T>> T maximum(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    static <T> T chooseLarger(T first, T second,
                              Comparator<? super T> comparator) {
        return comparator.compare(first, second) >= 0 ? first : second;
    }

    public static void main(String[] args) {
        System.out.println(characters("Java"));
        System.out.println(characters(new StringBuilder("generic")));
        System.out.println(twice(3));
        System.out.println(maximum(5, 9));
        System.out.println(chooseLarger("ant", "tiger",
                Comparator.comparingInt(String::length)));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 BoundedOperationsDemo.java
java BoundedOperationsDemo
~~~

Stdout:

~~~text
4
7
6.0
9
tiger
~~~

Analysis:

- **T extends CharSequence** allows calling length() on both String and StringBuilder.
- **T extends Number** allows calling doubleValue() and multiplying the resulting double value; T itself still cannot be used directly in generic multiplication.
- **T extends Number & Comparable<T>** allows compareTo; Integer satisfies both bounds.
- **chooseLarger** does not constrain T to be Comparable because a Comparator is supplied as a parameter; the Comparator compares strings by length and selects tiger.
- All four methods can still hit NPE if given null where an unchecked receiver method is invoked. In the runnable example, every argument used is non-null.

## 11. Standalone Runnable Example: Requiring a Non-Null Value

Save as **NullPolicyDemo.java**:

~~~java
import java.util.Objects;
import java.util.Optional;

public class NullPolicyDemo {
    static <T> T requireValue(T value) {
        return Objects.requireNonNull(value, "value");
    }

    static <T> T withFallback(T value, T fallback) {
        return value != null
                ? value
                : Objects.requireNonNull(fallback, "fallback");
    }

    static <T> Optional<T> optionalOf(T value) {
        return Optional.ofNullable(value);
    }

    public static void main(String[] args) {
        System.out.println(requireValue("ready"));
        System.out.println(withFallback(null, "guest"));
        System.out.println(optionalOf(null).isEmpty());
        System.out.println(optionalOf("Java").orElse("other"));

        try {
            requireValue(null);
        } catch (NullPointerException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 NullPolicyDemo.java
java NullPolicyDemo
~~~

Stdout:

~~~text
ready
guest
true
Java
value
~~~

**requireValue** and **withFallback** preserve T in the return type; Objects.requireNonNull rejects null instead of assuming T was already checked by the generics system. **Optional.ofNullable(null).isEmpty()** returns true, while Optional.ofNullable("Java") holds the string "Java". The exception message is clearly specified in source via **Objects.requireNonNull(value, "value")**.

## 12. Type Erasure: Default `Object` Does Not Mean Runtime Knows `T`

For unbounded generic types, the compiler implements many operations via erasure; the implicit Object bound is one reason bytecode typically handles Object-typed references. However, the Java compiler also inserts necessary casts at usage sites where type argument information is available.

Example:

~~~java
class Container<T> {
    T item;

    Container(T item) {
        this.item = item;
    }

    T get() {
        return item;
    }
}

// At the call site:
// Container<String> x = new Container<>("hello");
// String s = x.get();
~~~

Conceptually, the compiler checks in source that get() returns String in a Container<String> usage, even though post-erasure bytecode may need a cast to String when retrieving the result. The programmer does not have to write a cast in well-typed source.

You cannot rely on T to instantiate objects or create arrays of T directly:

~~~java
// Compilation error illustration, not runnable:
class Factory<T> {
    // T create() { return new T(); } // Error
    // T[] createArray() { return new T[4]; } // Error
    // Class<T> type() { return T.class; } // Error
}
~~~

The reason is that T is not a concrete class token usable directly in those expressions at runtime. If you need to instantiate T, accept a factory or Supplier<T>. If you need runtime type checking, you can accept Class<T> from callers when appropriate for the API design.

Valid example with Supplier:

~~~java
import java.util.function.Supplier;

class GenericFactory<T> {
    private final Supplier<? extends T> supplier;

    GenericFactory(Supplier<? extends T> supplier) {
        this.supplier = supplier;
    }

    T create() {
        return supplier.get();
    }
}

// Inside a method:
// GenericFactory<StringBuilder> factory =
//         new GenericFactory<>(StringBuilder::new);
// StringBuilder builder = factory.create();
~~~

The compiler allows supplier.get() to be used as T because **? extends T** denotes a result type assignable to T. Actually creating the object is Supplier's responsibility. A Supplier can still return null if its contract permits; generics itself does not forbid it.

Another error is **value instanceof T**, since type T generally lacks the runtime representation needed to check the exact type argument. Instead, you can check **value instanceof String** in valid contexts because String is a concrete class, or use **Class<T>.isInstance(value)** if the caller supplies Class<T>. Class-based runtime checks also cannot fully inspect List<String> or nested type arguments.

## 13. Common Mistakes and Misconceptions

### Mistake 1: “T defaults to Object so any Object can be assigned to T”

~~~java
// Code illustrating error:
static <T> T badReturn() {
    Object value = "text";
    return value; // Compile-time error
}
~~~

It is true that **T can be converted to Object** (T is a subtype of its Object bound). The reverse direction is not guaranteed. A call may require T = Integer while Object holds a String.

### Mistake 2: “With T extends Number, T cannot be null”

~~~java
static <T extends Number> double magnitude(T n) {
    return n.doubleValue();
}
~~~

**magnitude(null)** compiles and throws NPE at runtime. Bounds constrain the type, not whether the receiver is non-null.

### Mistake 3: “T has Object methods so calling toString on null is safe”

~~~java
static <T> String unsafeText(T value) {
    return value.toString();
}
~~~

The code compiles, yet passing null throws NPE. Use **String.valueOf(value)** or check beforehand depending on intent.

### Mistake 4: “I can call String methods because I usually pass Strings”

~~~java
class NotAlwaysString<T> {
    // int length(T value) { return value.length(); } // Compile-time error
}
~~~

Without a bound, value could be of a type that has no length(). Use **<T extends CharSequence>** if you want the length of a CharSequence, or declare the method to accept String if the API genuinely operates only on Strings.

### Mistake 5: “T can be added directly like numbers”

~~~java
class Numeric<T extends Number> {
    // T add(T a, T b) { return a + b; } // Compile-time error
}
~~~

Number does not declare a `+` operator for T. You must convert to a concrete numeric type or accept an addition function; note that converting to double can lose precision for large numbers.

### Mistake 6: “Objects.equals(a, b) and a == b are the same”

The two expressions have different semantics: **==** checks reference identity or null; **Objects.equals** checks via equals when appropriate and is null-safe. For objects with equal content yet distinct instances, Objects.equals can return true while == returns false.

### Mistake 7: “Null and generics are interchangeable for representing optionality”

A Slot<T> that allows null only shows it can store null. It does not specify whether “no data yet” means the same thing as “the chosen value is null”. The API must explicitly define states and return values/errors.

### Mistake 8: “Keeping T is enough to know exact type arguments at runtime”

Erasure means element type information does not exist as a dedicated class per List<String> or List<Integer>. An Object holding a List does not let you use getClass() to directly verify the String type argument. If elements need checking, iterate and validate them under the appropriate policy.

### Mistake 9: “To prevent NPE, just cast T”

Casting does not turn a null value into an object; casting null to a reference type still yields null. Nor does it conjure new methods on an unbounded T in a generic signature. Use null checks and appropriate bounds/strategies.

### Mistake 10: “Object has toString so I can use toString to make a generic API do anything”

toString only creates a textual representation; parsing, comparison, computation, and domain property access require dedicated APIs/contracts. When designing generic methods, declare type bounds or pass operation functions instead of relying on string formatting.

## 14. Rules for Designing Generic APIs Involving `null`

There is no single null policy for every generic API. What matters is putting the policy into the contract and enforcing it consistently:

| Requirement | How to Express |
| --- | --- |
| Allow missing values | Accept null and handle explicitly, or use an appropriate state type |
| Strictly require a non-null input | Objects.requireNonNull at API boundaries |
| Represent presence/absence explicitly | Optional<T> when fitting the API style; never store null inside Optional |
| Use methods of an interface | <T extends InterfaceName> |
| Use numeric methods | <T extends Number> or a concrete math API |
| Compare when T has no Comparable | Pass Comparator<? super T> |
| Instantiate objects of T | Pass Supplier<? extends T> or a factory |
| Check a concrete class of T | Pass Class<T> when needed; mind type erasure limits |

Example of an API that rejects null immediately upon instantiation:

~~~java
import java.util.Objects;

class NonNullBox<T> {
    private final T value;

    NonNullBox(T value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    T get() {
        return value;
    }
}
~~~

Even though T is an unbounded type variable, this class establishes its own invariant: after the constructor succeeds, the value field is non-null. This guarantee comes from **constructor logic and the final field** (within the scope of the sample code), not from **`<T>`** syntax.

If an API permits null, check before invoking any instance method on that receiver. In particular, a bound such as Comparable, Runnable, or Number lets the compiler allow calling the corresponding method, yet a null receiver still causes NPE.

## 15. Self-Check

**Question 1.** With **class Box<T>**, what is T's default upper bound? Can you write **Box<int>**?

**Answer:** T has an upper bound of Object if no explicit bound is declared. **Box<int>** is invalid; use Box<Integer> or another reference type.

**Question 2.** In **static <T> boolean empty(T x) { return x == null; }**, does the method need **T extends Object**?

**Answer:** No. T already has an implicit Object bound; comparing against null is valid because T is used as a reference type.

**Question 3.** Why does **static <T> int length(T value) { return value.length(); }** fail to compile? What is the minimal fix to accept both String and StringBuilder?

**Answer:** Object does not have length(). Add a bound: **static <T extends CharSequence> int length(T value) { return value.length(); }**. You still must handle null if the input may be null.

**Question 4.** Does **T extends Number** allow the expression **a + b** with two variables of type T?

**Answer:** No. T is a reference type variable, and Number does not define a generic addition operator. You can call doubleValue() and add as double if requirements allow.

**Question 5.** Can you assign **Object x = t** if t has unbounded type T? Can you assign back **T t = x** in general?

**Answer:** You can assign T to Object. You cannot arbitrarily assign Object to T because T may be a specific subtype of Object.

**Question 6.** Why is **String.valueOf(value)** generally safer than **value.toString()** if value may be null?

**Answer:** String.valueOf(Object) turns null into the string "null"; calling toString directly on a null receiver throws NullPointerException.

**Question 7.** Compare **value == null**, **value.equals(other)**, and **Objects.equals(value, other)**.

**Answer:** `== null` checks for an absent reference; value.equals uses the object's equals logic yet throws NPE when value is null; Objects.equals is null-safe and compares contents via equals when the objects are non-null.

**Question 8.** Why is **new T()** invalid? What should you do if a generic function needs to create a new object?

**Answer:** Type erasure does not provide a concrete constructor for T at runtime. Accept Supplier<T> or an appropriate factory so the caller supplies the creation mechanism.

**Question 9.** In **class Box<T extends Number> { T n; }**, can n == null occur?

**Answer:** Yes. Bounding the type by Number does not turn into a non-null guarantee.

**Question 10.** When should you use **<T extends Comparable<T>>**, and when should you pass a Comparator?

**Answer:** Use the bound if the API requires T to have a natural ordering via Comparable<T>; pass Comparator<? super T> if you want strategy-based comparison or support for types that do not implement a matching Comparable.

## 16. Takeaways to Apply

With an **unbounded type parameter T**, the compiler knows at minimum that T conforms to **Object**. That suffices for null checks, assigning from T to Object, and calling available Object methods on a non-null receiver. It is **not** enough to call length(), compareTo(), doubleValue(), instantiate new T(), or perform general arithmetic addition.

Nullability is independent of bounds: **T**, **T extends Number**, and **T extends Comparable<T>** can all receive null when context permits. If a non-null invariant is needed, state it in the API contract and validate at the right boundaries. When specialized operations are needed, add **extends** for the right interface/class or supply a function/strategy operating on T. Keeping this distinction clear makes generic declarations flexible, type-safe, and easy to reason about.
