# Identifying Raw Types, Unchecked Warnings, and Type Erasure in Java

> **Module:** Java Core — class/object  
> **Knowledge group:** Generic classes  
> **Topic:** Identifying raw types, unchecked warnings, and type erasure  
> **Version:** Java 17+. The examples run standalone without enabling preview features.

## 1. The problem: why do cast errors still occur even when writing generics?

Java generics enable APIs to be reused with multiple data types while still having type relationships checked by the compiler.

Example:

~~~java
class Box<T> {
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
}
~~~

`Box<String>` is a box understood by the compiler to hold String. `Box<Integer>` is a box holding Integer. However, Java retains **raw types** for compatibility with legacy code:

~~~java
Box raw = new Box("hello");
~~~

When using a raw reference, the compiler loses the type information `T` in operations going through it. For example, a raw reference can put an Integer into an object that another variable declared as `Box<String>`. When reading it back as a String, the program can throw `ClassCastException`.

That leads to three concepts that need to be distinguished:

- **Raw type:** the name of a generic class/interface used **without passing type arguments** in a raw-type semantics context, such as `List` instead of `List<String>`.
- **Unchecked warning:** the compiler does not have enough proof that a generic call, conversion, or cast will preserve type safety.
- **Type erasure:** the mechanism by which the Java compiler removes most type-parameter information from runtime signatures, replaces type variables with bounds/Object, and may insert casts and generate bridge methods.

**Type erasure occurs even in programs that write generics properly and have no warnings.** A raw type is a source-level choice that weakens type checking; it is not “inevitable because the JVM uses erasure”.

## 2. Identifying generic declarations, parameterized types, and raw types

Consider:

~~~java
interface Repository<ID, ENTITY> {
    ENTITY find(ID id);
}
~~~

This is an **interface fragment**. The two type parameters are `ID` and `ENTITY`.

| Syntax | Classification | Meaning |
| --- | --- | --- |
| `Repository<ID,ENTITY>` in declaration | Generic declaration | Defines two type parameters |
| `Repository<String,User>` | Parameterized type | Chooses String for ID, User for ENTITY |
| `Repository<?,?>` | Parameterized type with wildcards | Knows this is a generic repository, but the type arguments are unknown |
| `Repository` | Raw type | Omits the type arguments of the generic declaration |
| `List<Object>` | Parameterized type | Exact element type is Object |
| `List<?>` | Parameterized type | An unknown element type |
| `List` | Raw type | Omits the type argument E |
| `String` | Ordinary non-generic type | Not raw |

### 2.1. The character `T` is not synonymous with raw

Inside the body of `class Box<T>`, `T` is a **valid type variable**. The compiler knows that occurrences of T must be consistent across the field, getter, and setter. It is not a raw type.

### 2.2. The diamond operator is not a raw type

~~~java
List<String> names = new ArrayList<>();
~~~

`<>` is the **diamond** operator, which allows the compiler to infer type arguments from the context. This declaration preserves generic type safety.

Compare:

~~~java
List<String> names = new ArrayList(); // Raw construction, warning.
~~~

On the right-hand side, there is neither a diamond nor type arguments, so `new ArrayList()` is a raw construction. The compiler may accept it via an unchecked conversion, but it should not be written that way in new code.

### 2.3. `var` does not turn a generic into a raw type either

~~~java
var names = new ArrayList<String>();
~~~

The compiler infers `ArrayList<String>`. Whereas:

~~~java
var names = new ArrayList<>();
~~~

when target type context is missing, the element type is typically inferred as Object. This is an **inference issue**, not a raw `ArrayList`.

## 3. Where raw types commonly appear

Raw usage can appear in:

~~~java
List values;                   // Raw variable.
Set flags = new HashSet();     // Raw variable and constructor.
Map cache;                     // Raw field/local if written inside a class/method.
Class type = String.class;     // Raw Class.
Comparable candidate = "A";    // Raw Comparable.
Box box = new Box("A");        // Raw Box.
~~~

These snippets are **fragments** and require appropriate imports and declarations.

Their typed counterparts:

~~~java
List<String> values;
Set<String> flags = new HashSet<>();
Map<String, Integer> cache;
Class<?> type = String.class;
Comparable<String> candidate = "A";
Box<String> box = new Box<>("A");
~~~

### 3.1. Public raw APIs have a cascading impact

A legacy method:

~~~java
public List fetchAll()
~~~

does not state the element type. Every caller has to guess, cast, or pass along the raw List. If you are permitted to modify the API and the data truly consists only of User, returning `List<User>` is better because the compiler protects callers.

### 3.2. Raw superclass or interface

~~~java
class LegacyComparator implements Comparable {
    @Override
    public int compareTo(Object other) {
        return 0;
    }
}
~~~

This is a fragment. `Comparable` is actually `Comparable<T>`. If the class only compares against other LegacyComparator instances, you can write `implements Comparable<LegacyComparator>` with `compareTo(LegacyComparator other)` to make the type contract clearer.

### 3.3. The case of Class literals

`String.class` and `List.class` are valid; there is no `List<String>.class` syntax to create a Class object reified by element type. However, the fact that reflection uses `List.class` **does not justify APIs everywhere accepting a raw List**. When a type-agnostic Class is needed, use `Class<?>`; when generic nested types are needed, consider Type/ParameterizedType or a type descriptor.

## 4. Distinguishing `rawtypes` and `unchecked`

These are two related but not identical diagnostic categories.

### 4.1. `rawtypes`: omitting type arguments

Example:

~~~java
List raw = new ArrayList();
~~~

Enable lint:

~~~bash
javac -Xlint:rawtypes SomeFile.java
~~~

The compiler can point out the places where `List`/`ArrayList` names are used in raw form.

### 4.2. `unchecked`: operations that cannot be fully verified

~~~java
List raw = new ArrayList();
raw.add("A");
List<String> names = raw;
~~~

You may encounter:

- **Unchecked call:** `raw.add("A")` is invoked through a raw receiver.
- **Unchecked conversion:** `List<String> names = raw` converts a raw List to a parameterized type where the compiler cannot check every element.

These warnings do not themselves produce a runtime exception at compile time. A Java program may still run properly with a compatible dataset and fail when different data is supplied.

### 4.3. Compiler flags worth knowing

~~~bash
javac -Xlint:rawtypes,unchecked SomeFile.java
javac -Xlint:all SomeFile.java
javac -Xlint:rawtypes,unchecked -Werror SomeFile.java
~~~

`-Werror` requires the build to fail if there are warnings. It is suitable for already cleaned-up modules, whereas legacy projects should usually inventory and fix warnings in phases.

### 4.4. Do not document raw diagnostics as fixed stdout

Compiler diagnostic text and line numbers may vary by JDK, flags, and source positions. In this lesson, only **stdout from `java Program`** is recorded exactly; lint diagnostics will be described by category, without claiming that every compiler line is always identical.

## 5. Complete program 1 — raw type causing a delayed cast error

Create the file **`RawBoxFailureDemo.java`**:

~~~java
public class RawBoxFailureDemo {
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
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    static void legacyWrite(Box box) {
        box.set(42);
    }

    public static void main(String[] args) {
        Box<String> typed = new Box<>("Lan");
        System.out.println("Before = " + typed.get());

        legacyWrite(typed);

        try {
            String value = typed.get();
            System.out.println("After = " + value);
        } catch (ClassCastException ex) {
            System.out.println("Delayed ClassCastException");
        }

        System.out.println("Runtime class = "
                + Box.class.getSimpleName());
    }
}
~~~

Commands to run:

~~~bash
javac -encoding UTF-8 RawBoxFailureDemo.java
java RawBoxFailureDemo
~~~

**Exact stdout:**

~~~text
Before = Lan
Delayed ClassCastException
Runtime class = Box
~~~

### 5.1. The compiler trusts that `Box<String>` holds String

For the `typed` variable, the compiler knows `get()` returns String according to the source-level generic type. However, the `legacyWrite` method accepts a raw `Box` and calls `set(42)`, breaking the relationship T=String.

### 5.2. Why doesn't set throw an error immediately?

The erased setter of an unbounded Box takes Object. Integer is a valid Object reference. Only when reading into a String variable does the compiler-inserted cast inspect the runtime object and detect that Integer is not a String.

### 5.3. `@SuppressWarnings` does not fix the bug

The annotation only hides warnings within the scope of the legacyWrite method. Using suppression here **intentionally demonstrates dangerous code**. In production, you should not keep a helper that violates a type invariant like this; use a typed API or validate data.

### 5.4. The term “heap pollution”

`Box<String>` now has a field containing an Integer. The object and the type argument are mismatched due to raw access, which is an example of **heap pollution**. The failure can appear far away from where the wrong data was inserted.

## 6. Complete program 2 — looking at compiler warnings

Create the file **`RawWarningExample.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RawWarningExample {
    public static void main(String[] args) {
        List raw = new ArrayList();
        raw.add("A");
        List<String> names = raw;

        System.out.println("First = " + names.get(0));
    }
}
~~~

Compile and run normally:

~~~bash
javac -encoding UTF-8 RawWarningExample.java
java RawWarningExample
~~~

Run this command **separately** to see the categorized diagnostics:

~~~bash
javac -encoding UTF-8 -Xlint:rawtypes,unchecked RawWarningExample.java
~~~

**Program stdout:**

~~~text
First = A
~~~

### 6.1. Places where lint will warn

There is a raw `List` and a raw construction `ArrayList()`; calling `raw.add("A")` has an unchecked call; assigning the raw List to `List<String>` has an unchecked conversion.

### 6.2. Why does this execution not throw an error?

The List currently contains only the String "A", so the compiler-inserted cast when reading a String succeeds. However, if an Integer is added to the raw List, the program can throw ClassCastException. A warning indicates a **risk of missing guarantees**, not a guaranteed failure on every input.

### 6.3. Do not use `-Werror` and expect to run the program

If `-Werror` is used while warnings still exist, the build can fail. That is the intention of a quality gate; the program runs afterward only when a valid class file exists from a successful compilation.

## 7. Raw List, List<Object>, and List<?> are not equivalent

| Property | `List` | `List<Object>` | `List<?>` |
| --- | --- | --- | --- |
| Declaration kind | Raw | Parameterized | Parameterized with wildcard |
| `get(0)` is seen as | Object | Object | Object |
| `add("A")` | Can compile with an unchecked warning | Compiles | Does not compile |
| `add(42)` | Can compile with an unchecked warning | Compiles | Does not compile |
| `add(null)` | Can compile | Compiles if the API allows | Compiles if the API allows |
| Accepts a reference from List<String>? | Yes, via raw | No, due to invariance | Yes |
| Use in new code | Avoid | If the contract is arbitrary Object | If the element type is unknown |

### 7.1. Why is List<?> safer than raw?

`List<?>` actually has a type argument, though it is unknown. The compiler does not allow adding an arbitrary non-null element because the actual element type may differ. Raw List bypasses that constraint.

### 7.2. Why is List<?> not synonymous with immutable?

It can still point to a mutable ArrayList. The `clear()` method or valid remove operations can still modify the List; the wildcard primarily restricts non-type-safe operations such as adding an arbitrary String.

### 7.3. Why does List<Object> not accept List<String>?

Java generics are invariant. If a List<String> were assigned to List<Object>, someone could add an Integer through the List<Object> alias, causing List<String> to hold the wrong type. The compiler prevents this situation.

### 7.4. Wildcards differ from named type parameters

A wildcard represents an unknown element type; a generic method `<T> void copy(List<? extends T>, List<? super T>)` informs the compiler of the relationship between producer/consumer. You should not switch to raw when a wildcard causes difficulty: a `<T>` helper may be needed to capture the type.

## 8. Complete program 3 — using wildcards safely

File **`RawVsWildcardDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RawVsWildcardDemo {
    static int count(List<?> values) {
        return values.size();
    }

    static String firstText(List<?> values) {
        return String.valueOf(values.get(0));
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("Lan", "Mai"));
        List<?> unknown = names;

        System.out.println("Count = " + count(unknown));
        System.out.println("First = " + firstText(unknown));
        System.out.println("Same list = " + (unknown == names));

        names.add("An");

        System.out.println("After mutation = " + unknown);

        // unknown.add("X"); // Intentionally does not compile.
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 RawVsWildcardDemo.java
java RawVsWildcardDemo
~~~

**Exact stdout:**

~~~text
Count = 2
First = Lan
Same list = true
After mutation = [Lan, Mai, An]
~~~

### 8.1. List<?> does not copy the List

`unknown` and `names` are references to the same ArrayList; state changes made through names are visible through unknown.

### 8.2. Why can't you assign `String first = unknown.get(0)`?

The compiler only knows that the element type is unknown, so the get method returns a value safely readable as Object. If you actually want a String, you must check/cast at the boundary based on the input invariant.

### 8.3. Do not use a raw type to bypass the compiler

The fact that `unknown.add("X")` does not compile is type safety itself. Converting unknown to a raw List just to add will break the contract instead of solving the design.

## 9. Unchecked conversion does not iterate over all elements

Look at:

~~~java
List raw = obtainLegacyList();
List<String> names = raw;
~~~

This is a **fragment**; `obtainLegacyList` is a hypothetical existing legacy API.

The compiler may warn about an unchecked conversion, but **it does not insert an automatic loop checking that every element is a String**. Erasure only allows the runtime to know the object is a List. The data inside may be wrong.

Similarly:

~~~java
List<String> names = (List<String>) raw;
~~~

the cast does not check all list contents. If the Object is a List containing Integer, casting to List<String> can “succeed” at the time of the cast, yet reading an element into a String afterward triggers ClassCastException.

### 9.1. An unchecked cast differs from a checked cast

`String.class.cast(value)` actually checks that value is of the String runtime class, whereas casting a List<?> to List<String> does not verify the erased generic element argument.

### 9.2. Do not use a double cast to “remove the warning”

`(List<String>)(List<?>) source` may shift/reduce diagnostics in some source patterns, but it adds no runtime validation. The essential question remains: **who guarantees that all elements are truly String?**

### 9.3. Not every mix of Objects is pollution

`List<Object>` containing String and Integer is valid by contract. Heap pollution is a mismatch with a **promised parameterized type**, not simply having multiple runtime classes in a collection.

## 10. Complete program 4 — validating data and then returning a typed collection

File **`CheckedGenericBoundaryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CheckedGenericBoundaryDemo {
    static <T> List<T> checkedCopy(
            List<?> input, Class<T> type) {
        List<T> output = new ArrayList<>();

        for (Object item : input) {
            output.add(type.cast(item));
        }

        return List.copyOf(output);
    }

    public static void main(String[] args) {
        List<?> good = List.of("Lan", "Mai");
        List<String> names = checkedCopy(good, String.class);

        System.out.println("Names = " + names);

        try {
            List<?> bad = List.of("Lan", 7);
            checkedCopy(bad, String.class);
        } catch (ClassCastException ex) {
            System.out.println("Invalid element rejected");
        }

        System.out.println("Original count = " + good.size());

        try {
            names.add("An");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Result unmodifiable");
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CheckedGenericBoundaryDemo.java
java CheckedGenericBoundaryDemo
~~~

**Exact stdout:**

~~~text
Names = [Lan, Mai]
Invalid element rejected
Original count = 2
Result unmodifiable
~~~

### 10.1. Where does the boundary's type safety come from?

`Class<T>.cast` checks each element at runtime. Only when all match is the List<T> constructed. There is no unchecked cast of the entire List.

### 10.2. Why use List.copyOf?

The result becomes an unmodifiable structural snapshot; it does not depend on the underlying input List afterward. This is an ownership/mutability policy, **distinct from** the task of checking element types.

### 10.3. Null contract of the demo

`Class.cast(null)` can return null, whereas `List.copyOf` rejects null elements. In the demo, the `List.of` input contains no null. Production code must clearly define whether null elements are accepted.

### 10.4. Class<T> does not reify nested generic arguments

`String.class` exists, while `List<String>.class` does not. If each element requires the type `List<Integer>`, you need to check the List runtime type and the inner elements, or use a type descriptor/framework with appropriate validation.

## 11. Type erasure: what does the compiler do with T?

Java generics primarily have an **erased runtime representation**. Given:

~~~java
class Holder<T> {
    private T value;

    T get() {
        return value;
    }
}
~~~

you can think of the equivalent erased runtime signatures as:

~~~java
class Holder {
    private Object value;

    Object get() {
        return value;
    }
}
~~~

**The two snippets only illustrate the mechanism**; they are not two classes that can both be declared in one file. The compiler may also store generic metadata, insert checkcasts, or generate bridge methods.

### 11.1. Erasure of an unbounded parameter

`<T>` has no explicit bound, so T erases to Object.

### 11.2. Erasure of a bounded parameter

`<N extends Number>` has erasure Number. A field `N number` will have runtime reflection Field.getType() equal to Number.

### 11.3. Multiple bounds

With `<T extends Number & Comparable<T>>`, the first bound Number determines the erasure of T. When there is no class bound and the first bound is an interface, that first interface can be the erasure.

### 11.4. Generic method erasure

`static <T> T identity(T input)` typically has erased Object parameter/return when T is unbounded. However, the compiler still ensures the call `String s = identity("A")` is properly typed in source.

### 11.5. Erasure does not necessarily remove all metadata

The compiler can write generic `Signature` attributes for classes/fields/methods. Reflection such as `getTypeParameters` or `getGenericParameterTypes` can read declaration metadata, even though at runtime there is no separate class specialization for Box<String>.

## 12. Complete program 5 — looking at erasure via reflection

File **`TypeErasureReflectionDemo.java`**:

~~~java
import java.lang.reflect.Field;
import java.util.Arrays;

public class TypeErasureReflectionDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static final class NumberBox<N extends Number> {
        private final N number;

        NumberBox(N number) {
            this.number = number;
        }

        N get() {
            return number;
        }
    }

    public static void main(String[] args) throws Exception {
        Box<String> text = new Box<>("Java");
        Box<Integer> count = new Box<>(17);

        Field valueField = Box.class.getDeclaredField("value");
        Field numberField =
                NumberBox.class.getDeclaredField("number");

        System.out.println("Same runtime class = "
                + (text.getClass() == count.getClass()));
        System.out.println("Box field = "
                + valueField.getType().getSimpleName());
        System.out.println("NumberBox field = "
                + numberField.getType().getSimpleName());
        System.out.println("Type parameters = "
                + Arrays.toString(Box.class.getTypeParameters()));
        System.out.println("Text = " + text.get());
        System.out.println("Count = " + count.get());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 TypeErasureReflectionDemo.java
java TypeErasureReflectionDemo
~~~

**Exact stdout:**

~~~text
Same runtime class = true
Box field = Object
NumberBox field = Number
Type parameters = [T]
Text = Java
Count = 17
~~~

### 12.1. Why do the two Box objects have the same getClass?

Both `new Box<String>` and `new Box<Integer>` use the runtime class Box; type arguments do not create two separate runtime Class objects.

### 12.2. Why does reflection know T?

`Box.class.getTypeParameters()` reads **generic declaration metadata**. It indicates that Box declares T, not that T of the object text equals String in all runtime contexts.

### 12.3. When can reflection find a concrete argument?

A non-generic subclass `class StringBox extends Box<String>` can store a generic superclass signature reflecting String. That is metadata on the subclass declaration, not Box<T> reifying the type argument itself on each arbitrary Box instance.

## 13. Erasure and compiler-inserted casts

In typed code:

~~~java
Box<String> text = new Box<>("Core");
String value = text.get();
~~~

The erased `get()` can return Object. The compiler inserts a checkcast to String when needed to ensure the expression is used as String.

This explains the error in RawBoxFailureDemo: the raw setter inserts an Integer, while the typed getter/caller ultimately demands a String.

### 13.1. Not every source-level get causes an explicit checkcast in bytecode

The compiler and JIT can optimize. What you should rely on is that the Java runtime must ensure a type check where the conversion is actually needed; an invalid result can throw ClassCastException.

### 13.2. Null and casts

Casting null to String returns null and does not throw ClassCastException. A null-related NPE has a different mechanism from heap pollution.

### 13.3. Type erasure does not allow the compiler to drop all type checks

Typed Java source still has strict compile-time constraints. Only operations passing through raw/unchecked/reflective unsafe paths cause certain guarantees to no longer be proven.

## 14. Bridge methods preserve polymorphism under type erasure

A generic superclass:

~~~java
class Parent<T> {
    T get() {
        return null;
    }
}
~~~

and a specialized subtype:

~~~java
class Child extends Parent<String> {
    @Override
    String get() {
        return "Core";
    }
}
~~~

The erased Parent.get returns Object, while Child.get returns String. The compiler can generate a **bridge method** in Child so that polymorphic calls through the erased Parent signature still dispatch to the Child override.

### 14.1. A bridge is not a sign of a raw-type error

Bridges commonly appear in completely valid generic code with no unchecked warnings. It is a compatibility mechanism between generic overriding semantics and JVM method descriptors.

### 14.2. Reflection can see bridge methods

`java.lang.reflect.Method.isBridge()` distinguishes compiler-generated bridge methods. When writing reflection scanners, avoid treating a bridge as an independent duplicate business method.

## 15. Complete program 6 — finding a bridge with reflection

File **`GenericBridgeMethodDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;

public class GenericBridgeMethodDemo {
    static class Parent<T> {
        T get() {
            return null;
        }
    }

    static final class Child extends Parent<String> {
        @Override
        String get() {
            return "Core";
        }
    }

    public static void main(String[] args) throws Exception {
        Parent<String> source = new Child();

        System.out.println("Value = " + source.get());
        System.out.println("Erased return = "
                + Parent.class.getDeclaredMethod("get")
                        .getReturnType().getSimpleName());

        boolean bridge =
                Arrays.stream(Child.class.getDeclaredMethods())
                        .anyMatch(Method::isBridge);

        System.out.println("Has bridge = " + bridge);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericBridgeMethodDemo.java
java GenericBridgeMethodDemo
~~~

**Exact stdout:**

~~~text
Value = Core
Erased return = Object
Has bridge = true
~~~

### 15.1. Why does get() return Core through Parent<String>?

The actual object is Child; the override is dispatched via the bridge so the method matches the erased Parent.get signature.

### 15.2. Do not hard-code synthetic method names

The compiler generates bridges according to rules, but the names and order of methods in a reflection scan are not a stable domain API. Use `Method.isBridge()` when filtering is needed.

## 16. Same erasure causes method signature conflicts

The following two overloads:

~~~java
void process(List<String> names) {
}

void process(List<Integer> values) {
}
~~~

both erase their parameter to List, so **they cannot coexist in the same class**. The compiler reports a name clash/same erasure.

### 16.1. The proper fix

If the logic differs, give the methods different names:

~~~java
void processNames(List<String> names) {
}

void processCounts(List<Integer> values) {
}
~~~

If the logic is the same for every type:

~~~java
static <T> int count(List<T> values) {
    return values.size();
}
~~~

Do not add unchecked casts to force both overloads to coexist; the source signatures already conflict.

### 16.2. Some generic overloads are still valid

`process(List<String>)` and `process(Set<String>)` erase to List and Set, which are different parameter types, so they can overload if other rules are satisfied.

## 17. Complete program 7 — generic metadata on method declarations

File **`GenericSignatureDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.util.List;

public class GenericSignatureDemo {
    static void processNames(List<String> names) {
        System.out.println("Names = " + names.size());
    }

    static void processCounts(List<Integer> numbers) {
        System.out.println("Numbers = " + numbers.size());
    }

    public static void main(String[] args) throws Exception {
        processNames(List.of("A", "B"));
        processCounts(List.of(1, 2, 3));

        Method method = GenericSignatureDemo.class
                .getDeclaredMethod("processNames", List.class);

        System.out.println("Erased type = "
                + method.getParameterTypes()[0].getSimpleName());
        System.out.println("Generic type = "
                + method.getGenericParameterTypes()[0].getTypeName());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 GenericSignatureDemo.java
java GenericSignatureDemo
~~~

**Exact stdout on JDK 17:**

~~~text
Names = 2
Numbers = 3
Erased type = List
Generic type = java.util.List<java.lang.String>
~~~

### 17.1. Why can getGenericParameterTypes read String?

It reads declaration signature metadata, which does not mean the JVM created a separate runtime class List<String>. `getParameterTypes()` still yields the erased type List.

### 17.2. Why does reflection metadata not allow overloading with the same erasure?

The compiler checks Java method signatures and JVM descriptors; having different String/Integer generic metadata does not create two independent runtime parameter classes.

## 18. Reifiable and non-reifiable types: consequences of erasure

A **reifiable type** is a type with enough runtime information to be checked under Java rules.

Some examples:

- `String`, `String[]` — reifiable.
- Raw `List` — reifiable.
- `List<?>` — reifiable because all type arguments are unbounded wildcards.
- `List<String>` — **non-reifiable**.
- `T` (an ordinary generic type variable) — non-reifiable.

### 18.1. `instanceof List<String>` does not compile

~~~java
Object value = new ArrayList<String>();

if (value instanceof List<String>) {
}
~~~

This code **intentionally does not compile**. A runtime check cannot prove the String element type from an arbitrary List instance.

### 18.2. `instanceof List<?>` compiles

~~~java
Object value = new ArrayList<String>();

if (value instanceof List<?> list) {
    System.out.println(list.size());
}
~~~

This is a valid Java 17 fragment using an instanceof pattern. It checks whether the object implements List; it does **not** iterate through elements to check for String.

### 18.3. Cannot write `T.class`

~~~java
class Factory<T> {
    Class<T> type() {
        return T.class; // Intentionally does not compile.
    }
}
~~~

T is not a runtime Class literal. If validation is needed, accept `Class<T>` from the caller or a type descriptor.

### 18.4. Cannot do `new T()` from a generic type parameter alone

Type erasure does not provide an arbitrary constructor for an unknown T. Use `Supplier<? extends T>`, a typed factory, or controlled reflection.

### 18.5. Cannot create a generic array directly

Both `new T[10]` and `new List<String>[10]` are invalid; Java arrays reify their component type whereas generic parameterized arguments like List<String> are non-reifiable.

## 19. Array covariance versus generic invariance

Arrays are covariant:

~~~java
String[] words = {"A"};
Object[] items = words;
~~~

However, storing an Integer through items causes an **ArrayStoreException**, because the runtime array knows its component type is String.

Generics are invariant:

~~~java
List<String> words = new ArrayList<>();
List<Object> objects = words; // Intentionally does not compile.
~~~

Because the generic element type argument is not reified like a runtime array component, the compiler rejects the assignment that would risk adding arbitrary Objects into List<String>.

### 19.1. ArrayStoreException differs from ClassCastException

ArrayStoreException is thrown at runtime during an **array store**, when an object does not match the array's runtime component type. ClassCastException is thrown when casting an invalid reference, such as a String read from a raw-corrupted List.

### 19.2. A wildcard is not a new typed array

`List<?>` helps read containers with an unknown type argument in generic APIs; it does not replace runtime array component checking, nor does it make ArrayList immutable.

## 20. Complete program 8 — runtime checks of arrays and Lists

File **`ArrayAndGenericCheckDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ArrayAndGenericCheckDemo {
    public static void main(String[] args) {
        String[] strings = {"A"};
        Object[] objects = strings;

        try {
            objects[0] = 7;
        } catch (ArrayStoreException ex) {
            System.out.println("Array rejected Integer");
        }

        System.out.println("Array = " + strings[0]);

        Object value = new ArrayList<String>();
        if (value instanceof List<?> list) {
            System.out.println("List recognized = true");
            System.out.println("List size = " + list.size());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ArrayAndGenericCheckDemo.java
java ArrayAndGenericCheckDemo
~~~

**Exact stdout:**

~~~text
Array rejected Integer
Array = A
List recognized = true
List size = 0
~~~

### 20.1. Why is the List<?> check valid?

It only needs to know that the runtime type implements List. It does not insert a String via an unchecked add and does not assume the List contains String.

### 20.2. Why is String[] not changed into Integer[]?

The Object[] variable still points to an array of runtime type String[]. The JVM blocks the Integer right at the array store, so the first element remains "A".

## 21. Generic varargs and heap pollution

A varargs method:

~~~java
static <T> void process(T... values) {
}
~~~

typically has a varargs array at runtime. If T is non-reifiable, the compiler may warn about possible heap pollution. This is especially important for parameterized types such as `List<String>...`.

### 21.1. Risks when the varargs array is used unsafely

A method could cast/expose the varargs array as Object[] and then insert an incompatible parameterized object. Because the JVM does not reify generic element arguments, the runtime array store check does not protect List<String> from List<Integer> in all non-reifiable array scenarios.

### 21.2. `@SafeVarargs` is a promise

The `@SafeVarargs` annotation tells the compiler that the developer has verified the method performs no unsafe operations on the varargs parameter and does not allow the varargs array to escape in a dangerous way. It **does not change runtime behavior** and does not fix flawed logic.

In Java 17, the annotation is permitted on appropriate static/final/private instance methods or constructors, and must not be used arbitrarily on overridable instance methods.

### 21.3. Do not confuse safe varargs with deep immutability

Even if you copy varargs elements into an unmodifiable List, if the elements are mutable objects, the object graph can still change. Type safety, array ownership, and object immutability are separate concerns.

## 22. Complete program 9 — safely copying generic varargs

File **`SafeVarargsCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeVarargsCopyDemo {
    @SafeVarargs
    static <T> List<T> immutableCopy(T... values) {
        List<T> output = new ArrayList<>();

        for (T value : values) {
            output.add(value);
        }

        return List.copyOf(output);
    }

    public static void main(String[] args) {
        List<String> names = immutableCopy("Lan", "Mai");
        List<Integer> numbers = immutableCopy(1, 2, 3);

        System.out.println("Names = " + names);
        System.out.println("Numbers = " + numbers);

        try {
            names.add("An");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Unmodifiable");
        }
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 SafeVarargsCopyDemo.java
java SafeVarargsCopyDemo
~~~

**Exact stdout:**

~~~text
Names = [Lan, Mai]
Numbers = [1, 2, 3]
Unmodifiable
~~~

### 22.1. Why is the annotation justified?

The method only reads from the varargs array, copies elements into a new List, does not cast the array to Object[] to mutate it, and does not return or retain the varargs array itself. This is an implementation with a varargs-safe contract regarding generic element types.

### 22.2. Null policy

`List.copyOf` does not accept null elements. If the method must support null, you need to design a different output container and document it clearly. Null is not an issue specific to raw types.

## 23. Wildcard capture: replacing raw types with a generic helper

Sometimes a method accepting `List<?>` cannot directly perform a seemingly reasonable operation such as swapping two elements because it does not know the element type. Do not switch to a raw `List` just to get the compiler to accept calling `set`.

Use a helper:

~~~java
static void swap(List<?> values, int a, int b) {
    captureSwap(values, a, b);
}

private static <T> void captureSwap(
        List<T> values, int a, int b) {
    T held = values.get(a);
    values.set(a, values.get(b));
    values.set(b, held);
}
~~~

The generic helper tells the compiler that reads and writes on the same List share a single captured type T. It does not insert an arbitrary Object of another type.

### 23.1. Complete program 10 — wildcard capture

File **`WildcardCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureDemo {
    static void swapFirstTwo(List<?> values) {
        swap(values, 0, 1);
    }

    private static <T> void swap(
            List<T> values, int a, int b) {
        T held = values.get(a);
        values.set(a, values.get(b));
        values.set(b, held);
    }

    public static void main(String[] args) {
        List<String> letters =
                new ArrayList<>(List.of("A", "B", "C"));

        swapFirstTwo(letters);

        System.out.println("Letters = " + letters);
        System.out.println("First = " + letters.get(0));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 WildcardCaptureDemo.java
java WildcardCaptureDemo
~~~

**Exact stdout:**

~~~text
Letters = [B, A, C]
First = B
~~~

### 23.2. Limitations other than the generic type

The List must be mutable and have at least two elements; otherwise it may throw UnsupportedOperationException or IndexOutOfBoundsException. Wildcard capture solves **type consistency**, not list size or mutability.

## 24. `@SuppressWarnings` must have bounded scope and proof

`@SuppressWarnings("rawtypes")` and `@SuppressWarnings("unchecked")` are annotations that suppress compiler diagnostics in the corresponding code region.

They **do not**:

- Automatically validate element types.
- Turn an unchecked cast into a checked cast.
- Change type erasure.
- Prevent ClassCastException.
- Guarantee that the API is free of heap pollution.

### 24.1. Good order for handling warnings

1. Identify precisely whether the warning arises at a declaration or an operation.
2. Locate the boundary where type arguments are lost.
3. Replace the raw signature with a parameterized type if you have permission to modify it.
4. Use a wildcard if the type is genuinely unknown.
5. If external input needs a typed form, validate/copy each element.
6. If an unchecked cast is still unavoidable, prove the invariant and isolate it in a small helper.
7. Suppress only that exact warning inside that helper.
8. Write tests for both valid and invalid data.

### 24.2. Flawed pattern: assuming checking the List interface is enough

~~~java
@SuppressWarnings("unchecked")
static <T> List<T> trust(Object candidate) {
    if (!(candidate instanceof List<?>)) {
        throw new IllegalArgumentException("Not a list");
    }
    return (List<T>) candidate;
}
~~~

This is a **fragment that intentionally does NOT guarantee the element type**. It only establishes that candidate is a List; it does not know whether the List contains T. Without an external invariant, you should not expose List<T> this way.

### 24.3. Avoid suppressing at the entire class/module level

Broadly scoped suppression will also hide unsafe operations written later. Keep suppression as narrow as possible, accompanied by a note explaining why the unchecked cast is safe in the specific situation.

### 24.4. A temporary workaround is not a complete solution

A wrapper method using an unchecked cast may be necessary because of an old library, but preconditions must be guarded at the boundary; in the long run, you should fix the API or replace the legacy data representation.

## 25. Migrating legacy APIs without breaking data

Suppose the old source is:

~~~java
List loadNames() {
    List values = new ArrayList();
    values.add("Lan");
    return values;
}
~~~

This is a **method fragment**; import List/ArrayList when placing it inside a class.

If the contract definitely contains only String:

~~~java
List<String> loadNames() {
    List<String> values = new ArrayList<>();
    values.add("Lan");
    return values;
}
~~~

### 25.1. Do not fix only the caller

If the source method still returns a raw List, every call site will continue to have warnings/conversions. It is best to fix the type arguments **right at the original declaration** whenever possible.

### 25.2. If a List genuinely contains multiple runtime types

Do not arbitrarily assign `List<String>` just to eliminate the warning. Consider `List<Object>` if heterogeneous contents are intentional by design, or a sealed interface/value abstraction if the variants have clear business meanings. If you only need to traverse without knowing the element types, use `List<?>`.

### 25.3. Third-party APIs that cannot be modified

Write a typed adapter and validate data at a small boundary. Only write raw/unchecked code in the adapter when truly forced to, accompanied by tests.

### 25.4. Migration is not automatically 100% compatible

Adding generics may keep many erased binary descriptors similar to the legacy version, but source overload resolution, bounds, inherited signatures, warnings, callers, and type inference can change. Test source/binary compatibility against the actual API; do not promise that every generics refactor is “non-breaking”.

### 25.5. Choosing a direction to tighten warnings

Start with `-Xlint:rawtypes,unchecked`, inventory modules/files, fix upstream declarations, and then apply `-Werror` to the cleaned areas. Do not turn warnings into system-wide errors immediately while legacy dependencies still lack a migration path.

## 26. Complete program 11 — adapter for legacy Map data

File **`LegacyMapAdapterDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class LegacyMapAdapterDemo {
    static <K, V> Map<K, V> checkedCopy(
            Map<?, ?> source,
            Class<K> keyType,
            Class<V> valueType) {

        Map<K, V> output = new HashMap<>();

        for (Map.Entry<?, ?> entry : source.entrySet()) {
            K key = keyType.cast(entry.getKey());
            V value = valueType.cast(entry.getValue());
            output.put(key, value);
        }

        return Map.copyOf(output);
    }

    public static void main(String[] args) {
        Map<Object, Object> legacy = new HashMap<>();
        legacy.put("id", 17);

        Map<String, Integer> checked =
                checkedCopy(legacy, String.class, Integer.class);

        System.out.println("ID = " + checked.get("id"));
        System.out.println("Size = " + checked.size());

        legacy.put("bad", "not an integer");

        try {
            checkedCopy(legacy, String.class, Integer.class);
        } catch (ClassCastException ex) {
            System.out.println("Wrong value rejected");
        }

        System.out.println("Saved ID = " + checked.get("id"));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LegacyMapAdapterDemo.java
java LegacyMapAdapterDemo
~~~

**Exact stdout:**

~~~text
ID = 17
Size = 1
Wrong value rejected
Saved ID = 17
~~~

### 26.1. Why is the input Map<Object,Object> instead of raw Map?

The program simulates a boundary holding heterogeneous values by declaring its types explicitly. A real legacy API might return a raw Map; the adapter accepts `Map<?,?>` and explicitly checks that the key and value match the right types. No raw receiver is needed in the typed domain layer.

### 26.2. Why not print the entire HashMap?

HashMap iteration order is not guaranteed; the demo uses exact-key lookup and size so stdout is stable. The bad entry is detected regardless of iteration order because it is the only entry of the wrong type.

### 26.3. Map.copyOf only protects the Map structure

The returned Map is an unmodifiable structural snapshot. If V is a mutable object, the object's contents can still change; type safety is not equivalent to deep immutability.

## 27. How do compiler errors differ from runtime exceptions?

| Case | Timing | Cause |
| --- | --- | --- |
| `raw.add(...)` with -Xlint:unchecked | Compile warning | Missing proof of element type |
| `List<String> = raw` | Compile warning | Unchecked conversion |
| `List<String> → List<Object>` | Compile error | Generics invariance |
| `new List<String>[10]` | Compile error | Non-reifiable generic array creation |
| `value instanceof List<String>` | Compile error | Non-reifiable type test |
| Two overloads List<String>/List<Integer> | Compile error | Same erasure |
| `T.class` or `new T()` | Compile error | Non-reified type variable |
| Reading String from a raw-corrupted List | Runtime ClassCastException | Invalid cast |
| Storing Integer into String[] via Object[] | Runtime ArrayStoreException | Runtime array component mismatch |
| Mutating List.of(...) | Runtime UnsupportedOperationException | Unmodifiable collection contract |

### 27.1. Why is this table important?

You should not explain warnings as “an error that will blow up immediately” or a runtime ClassCastException as “the compiler already reported a compile error”. Java generics have a compile-time checking layer and several distinct runtime check layers.

### 27.2. Warnings and errors require different strategies

Compiler errors must be fixed to build. Warnings may not yet block the build, but they should be addressed because they point to areas not protected by the generic type system. Do not hide all warnings with annotations without evaluating the invariant.

## 28. Common mistakes and how to fix them

1. **Treating raw List as List<Object>.** Fix: distinguish parameterized Object from omitting generic info.
2. **Treating diamond `<>` as raw.** Fix: understand type inference.
3. **Assuming List<?> allows adding a String because String is an Object.** Fix: unknown type is not synonymous with Object.
4. **Treating a wildcard as an immutable List.** Fix: generic add restrictions differ from API mutability.
5. **Using a raw type to bypass compiler invariance.** Fix: use wildcards or copy.
6. **Ignoring a raw return type in a public API.** Fix: update the typed contract at the source.
7. **Confusing raw diagnostics with unchecked calls.** Fix: enable both lint categories.
8. **Thinking warnings are runtime exceptions.** Fix: distinguish compile diagnostics from execution.
9. **Seeing a successful execution and concluding unchecked is safe.** Fix: examine all data paths.
10. **Casting a raw List to List<String> and thinking elements were checked.** Fix: validate each element.
11. **Seeing ClassCastException at a getter and fixing only the getter.** Fix: find the raw/unchecked writer causing heap pollution.
12. **Assuming Java erasure creates a separate Box<String> class.** Fix: check getClass and reflection.
13. **Assuming reflection retains no generic metadata at all.** Fix: distinguish getType from getGenericType.
14. **Assuming type erasure prevents the compiler from blocking an unsafe set.** Fix: typed source is still checked.
15. **Assuming bounded T always erases to Object.** Fix: check the first bound.
16. **Thinking a bridge method was accidentally overloaded by you.** Fix: understand compiler-generated overriding compatibility.
17. **Creating two overloads differing only in List<String>/List<Integer>.** Fix: rename or use a generic method.
18. **Using `instanceof List<String>`.** Fix: use List<?> and validate elements.
19. **Looking for `List<String>.class`.** Fix: a runtime class token carries only the erased type.
20. **Using `new T()` or `new T[]`.** Fix: Supplier<T>/typed factory/List<T>.
21. **Treating arrays and generics as having the same variance.** Fix: arrays are covariant, generics are invariant.
22. **Ignoring heap pollution of parameterized varargs.** Fix: inspect the varargs body/array escape.
23. **Adding @SafeVarargs without proving the method is safe.** Fix: do not modify the varargs array improperly.
24. **Overly broad SuppressWarnings.** Fix: narrow the scope and document the reason.
25. **Wrapping an unchecked cast in a method named “safe” without checking elements.** Fix: Class<T>.cast each element.
26. **Using Class<T>.cast expecting it to automatically validate a nested List<String>.** Fix: validate nested structures.
27. **Choosing List<Object> when the real contract is List<User>.** Fix: keep the specific type.
28. **Not checking for null when using List.copyOf/Map.copyOf.** Fix: define the null policy.
29. **Thinking a generic List is always thread-safe.** Fix: the concurrency contract is independent.
30. **Assuming an unmodifiable List is deep immutable.** Fix: account for mutable elements.
31. **Thinking -Werror changes Java runtime behavior.** Fix: it only controls the build.
32. **Using HashMap iteration to produce fixed stdout.** Fix: avoid relying on an unguaranteed order.
33. **Refactoring public generic APIs without testing compatibility.** Fix: check callers and dependency versions.
34. **Not using IDE/compiler lint in a legacy audit.** Fix: incorporate lint into the workflow.
35. **Not documenting which boundary has been proven type-safe.** Fix: clear tests/invariants/contract.

## 29. Decision table: how to handle a raw API?

| What do you need to do? | Usually appropriate approach | Avoid |
| --- | --- | --- |
| Accept any List to read its size | `List<?>` | Raw List |
| Accept List<Integer>/List<Double> to read Number | `List<? extends Number>` | Casting to List<Number> |
| Add Integer to List<Integer>/List<Number> | `List<? super Integer>` | Raw add |
| Store all Strings | `List<String>` | Unnecessary List<Object> |
| Handle genuinely heterogeneous values | `List<Object>`/domain union | Pretending List<String> |
| Legacy API returns raw but data type is known | Fix the upstream declaration | Suppressing all call sites |
| Third-party API cannot be modified | Typed adapter | Spreading raw across service/domain |
| External List<?> needs to become List<String> | Validate elements, copy | Unchecked cast of the whole List |
| Generic T needs runtime Class validation | Accept `Class<T>` | `T.class` |
| Generic methods suffer same erasure | Rename/generic abstraction | Overloading differing only by type arg |
| Wildcard makes calling set with the same type difficult | Generic helper `<T>` | Casting to raw |
| Non-reifiable varargs | Safe implementation + correct annotation | Blind @SafeVarargs |
| CI has warnings | Audit/lint; Werror once clean | Ignoring warnings forever |

## 30. Self-check exercises with answers

**Question 1.** What is a raw type?

**Answer:** Using a generic class/interface while omitting type arguments, such as raw List.

**Question 2.** Why does Java still support raw types?

**Answer:** For compatibility with code/libraries written before generics.

**Question 3.** Is `List<String> list = new ArrayList<>()` raw?

**Answer:** No. The diamond is inferred from the target type.

**Question 4.** Is `List<?>` the same as raw List?

**Answer:** No. The wildcard preserves compiler checks for an unknown element type.

**Question 5.** Does `List<Object>` accept List<String> under normal assignment?

**Answer:** No, due to generic invariance.

**Question 6.** Does `List<?>` allow adding "A" directly?

**Answer:** No; the actual element type is unknown.

**Question 7.** Does `List<?>` make an ArrayList immutable?

**Answer:** No.

**Question 8.** Which javac flag finds raw uses?

**Answer:** `-Xlint:rawtypes`.

**Question 9.** Which javac flag finds unchecked operations?

**Answer:** `-Xlint:unchecked`.

**Question 10.** Can the two flags be combined?

**Answer:** Yes, `-Xlint:rawtypes,unchecked`.

**Question 11.** Does `-Werror` make runtime data safe?

**Answer:** No; it turns warnings into build errors.

**Question 12.** Does an unchecked call necessarily throw an exception immediately?

**Answer:** No. It indicates the compiler lacks a type-safety guarantee.

**Question 13.** What is heap pollution?

**Answer:** When actual data does not match the parameterized type contract due to unsafe operations.

**Question 14.** Does casting a raw List to List<String> scan the elements?

**Answer:** No.

**Question 15.** Why can an error explode at a typed getter later than the raw add site?

**Answer:** The cast required when reading a String is what first detects the runtime Integer.

**Question 16.** What is the erasure of unbounded T?

**Answer:** Usually Object.

**Question 17.** What is the erasure of T extends Number?

**Answer:** Number.

**Question 18.** Do Box<String> and Box<Integer> create two runtime classes?

**Answer:** No, for an ordinary generic class Box.

**Question 19.** Can reflection see the declaration type variable T?

**Answer:** Yes, via getTypeParameters/signature metadata.

**Question 20.** Why does the runtime Class of Box<String> not say T=String?

**Answer:** The type argument is not reified for an arbitrary generic instance.

**Question 21.** What is a bridge method used for?

**Answer:** Preserving overriding/polymorphism when erased signatures differ from source-specialized signatures.

**Question 22.** Is a bridge broken raw code?

**Answer:** No; bridges also appear in type-safe generic inheritance.

**Question 23.** Can two methods `f(List<String>)` and `f(List<Integer>)` overload in the same class?

**Answer:** No, name clash after erasure.

**Question 24.** Can you use `instanceof List<String>`?

**Answer:** No; the type is non-reifiable.

**Question 25.** Does `instanceof List<?>` check all String elements?

**Answer:** No; it only checks whether the object is a List.

**Question 26.** Why is `T.class` invalid?

**Answer:** A type variable has no class literal/runtime reification like a concrete class type.

**Question 27.** Can you do `new T()`?

**Answer:** Not based solely on an erased generic type parameter.

**Question 28.** Can you do `new List<String>[10]`?

**Answer:** No, due to generic array creation restrictions.

**Question 29.** What error is thrown when storing an Integer into String[] via Object[]?

**Answer:** ArrayStoreException.

**Question 30.** What error is usually thrown when typed code reads an Integer as a String?

**Answer:** ClassCastException.

**Question 31.** Does `@SuppressWarnings` validate types?

**Answer:** No; it only suppresses compiler diagnostics.

**Question 32.** Does `@SafeVarargs` automatically make an unsafe method safe?

**Answer:** No; the author must ensure the implementation is actually safe.

**Question 33.** When you need to swap two elements in List<?>, do you have to use raw?

**Answer:** No; use a generic wildcard-capture helper.

**Question 34.** When receiving untrusted List<?> data, how do you get a List<String>?

**Answer:** Check each element with String.class.cast and create a new List<String>, handling null according to contract.

**Question 35.** Does a Class<T> token automatically validate a nested List<String> type?

**Answer:** No; elements must be checked separately.

**Question 36.** Do raw types make generic APIs easier to maintain?

**Answer:** Usually no; they discard type information and push risk onto callers.

**Question 37.** Does having code with no raw warnings guarantee business validation?

**Answer:** No; generics check types, whereas domain invariants require dedicated logic.

**Question 38.** Do Java generics automatically solve null, mutability, and concurrency?

**Answer:** No; those are separate contracts.

**Question 39.** What should you do first when encountering a warning?

**Answer:** Categorize the warning, locate the boundary where type information is lost, and check the actual data contract before casting/suppressing.

**Question 40.** What is the core takeaway?

**Answer:** Raw loses compiler generic checks; unchecked flags operations not proven safe; erasure explains the runtime representation. For type safety, use typed APIs, wildcards/generic helpers, and validation at boundaries.

## 31. Practice exercises

### Exercise 1 — identifying warning locations

Create RawWarningExample.java as above and run `javac -Xlint:rawtypes,unchecked`. Record the warnings at the raw declaration, unchecked call, and conversion. Change the type to List<String> with diamond and recompile.

### Exercise 2 — intentionally creating heap pollution

Write Box<T> and a raw helper set(42) into Box<String>. Track when ClassCastException occurs. Then replace the helper with `static <T> void set(Box<T> box, T value)` so the compiler prevents the wrong type.

### Exercise 3 — replacing raw with wildcard

Write a method accepting List<?> and printing its size/contents. Try calling it with List<String> and List<Integer>. Demonstrate at compile time that add("A") is disallowed, then update the API with bounded wildcards if reading Number is needed.

### Exercise 4 — runtime validation

Use List<?> from external input. Write checkedCopy with Class<T>.cast for each element, and test valid Strings, an invalid Integer, and the null policy.

### Exercise 5 — observing erasure

Create Box<T> and NumberBox<N extends Number>. Print Field.getType and Class.getTypeParameters; explain how Object/Number/T differ.

### Exercise 6 — observing bridges

Override Parent<T>.get in Child extends Parent<String>, check Method.isBridge via reflection, and call it through a Parent<String> reference.

### Exercise 7 — generic method name clash

Try compiling two overloads differing only in List<String>/List<Integer>. Read the compiler error, rename the methods, or create a single generic method if the logic can be shared.

### Exercise 8 — quality gate

Introduce `-Xlint:rawtypes,unchecked` to a module, reduce warnings with typed APIs, scoped validation, and migration tests. Consider `-Werror` only once the module is clean.

## 32. End-of-lesson checklist

1. Does every raw generic declaration have a clear compatibility reason?
2. Can it be replaced with a concrete parameterized type?
3. If unknown, has the wildcard `<?>` been considered?
4. Is any typed contract lost in a public method return/parameter?
5. Is there a raw superclass/interface or Class declaration?
6. Are both the rawtypes and unchecked lint categories enabled?
7. Is unchecked call distinguished from unchecked conversion?
8. Are warnings suppressed too broadly?
9. Are all unchecked casts justified by an invariant or validation?
10. Is there any raw add/put causing heap pollution?
11. Is Class<T>.cast used per element for external data?
12. Have you avoided assuming a whole-List cast checks all elements?
13. Are negative inputs and delayed ClassCastException tested?
14. Are generic compile warnings distinguished from runtime exceptions?
15. Do you understand how unbounded/bounded Type erasure differs?
16. Have you avoided inferring the runtime Class from the Box<String> argument?
17. Do you understand that generic declaration metadata still exists for reflection?
18. Are you aware that the compiler can insert casts and bridge methods?
19. Do any method signatures conflict due to same erasure?
20. Are instanceof List<String> and new generic arrays avoided?
21. Are array covariance and generic invariance distinguished?
22. Have unsafe varargs and the @SafeVarargs contract been reviewed?
23. Is there a wildcard capture helper when a typed set/get for the same unknown T is needed?
24. Are null policy/ownership/mutability kept separate?
25. Is source/binary compatibility checked when modifying legacy generic APIs?
26. Is raw/unchecked logic kept inside an adapter instead of spreading into the domain?
27. Is using raw just to get past the compiler avoided?
28. Are proper generic bounds and variance considered when the API needs them?
29. Do tests/CI audit warnings per module?
30. Is it clearly documented which boundary is compile-time checked and which boundary requires runtime validation?

## Conclusion

A **raw type** is a usage of a generic class/interface that omits type arguments; it exists primarily to maintain compatibility with legacy Java and can permit **unchecked operations** that give rise to **heap pollution**. The Java compiler can warn via `-Xlint:rawtypes,unchecked`, yet at runtime a `ClassCastException` sometimes appears only when typed code reads invalid data, quite far from where the raw writer inserted the data.

**Type erasure** is how Java generics are compiled: type variables generally erase to their bound/Object, the compiler inserts casts and bridge methods as needed, and parameterized Box<String>/Box<Integer> share a single runtime class. This is not a reason to abandon generics; proper generic source code is still strongly checked at compile time.

When encountering raw or unchecked code, do not simply use casts/suppression to hide warnings. Instead, **restore type arguments on the API**, use `List<?>` when the element type is unknown, use type bounds/wildcards/generic helpers when needed, and **validate data at boundaries** before promising callers that a List is truly a List<String>. These steps help Java 17+ code leverage generics safely, preserve controlled compatibility, and avoid late-appearing type errors.
