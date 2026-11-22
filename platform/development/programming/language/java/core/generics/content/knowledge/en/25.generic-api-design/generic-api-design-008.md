# Impact of Bound Changes and Bound Ordering on Binary Compatibility in Java Generics

## 1. The problem: changing a generic signature can break compiled clients

Consider a public generic method:

~~~java
public static <T extends java.io.Serializable
        & Comparable<T>> T echo(T value) {
    return value;
}
~~~

A library might want to "clean up" the signature by reordering the bounds:

~~~java
public static <T extends Comparable<T>
        & java.io.Serializable> T echo(T value) {
    return value;
}
~~~

Both signatures accept `String` because `String` satisfies both `Serializable` and `Comparable<String>`. In Java source, they look nearly identical in terms of the allowed set of types. However, **bound ordering affects type erasure**: the first type in the bound list determines the erasure of the type variable.

- Old version: `erasure(T)` is `java.io.Serializable`.
- New version: `erasure(T)` is `java.lang.Comparable`.
- The JVM links methods by **name + bytecode descriptor**, not by an abstract notion that "two generic bounds have the same intersection set".
- Because `T` is both parameter and return type, **both the parameter descriptor and the return descriptor change**.
- A client already compiled against the old method will look for the exact old descriptor at runtime, while the new library class no longer has that method: failing with `NoSuchMethodError`.

This is a **binary compatibility break**, even if the client source could be recompiled against the new library version and run normally.

This topic focuses on **designing and evolving generic APIs**:
1. Which bound does a type variable's erasure depend on?
2. Does bound ordering affect bytecode descriptors and JVM linkage?
3. How does changing a bound while keeping the first bound differ from changing the first bound?
4. How does binary compatibility differ from source compatibility and behavioral compatibility?
5. How to verify using `javac`, `javap`, Reflection, and running an old client against a new library.
6. How to design, version, and test public generic APIs to avoid accidentally breaking users.

## 2. Three compatibility layers to distinguish

When saying "changing a generic signature is still compatible", ask clearly which kind:

| Compatibility kind | Right question | Verification example |
| --- | --- | --- |
| **Source compatibility** | Can old Java code **recompile** against the new API? | Recompiling `Client.java` after bumping a dependency version. |
| **Binary compatibility** | Can **already-compiled** client bytecode link and run against the new library binary? | Keeping the old `Client.class`; replacing only `Api.class`. |
| **Behavioral compatibility** | Once running, does the API still exhibit the expected behavior/semantics? | Checking exceptions, side effects, results, contracts. |

A bound-ordering change can:

- **Remain source-compatible** for a concrete call, such as using `String`.
- **Break binary compatibility** if the method descriptor changes and the library does not retain the old descriptor.
- **Change behavior** if the new implementation casts or calls different methods based on new bounds, even if the descriptor stays unchanged.

During library upgrades, large applications often have modules compiled at different times. That is why **"my source compiles" does not prove "old binaries still run"**.

### 2.1. Why doesn't the JVM use the Generic Signature to link methods?

The Java compiler generates **descriptors** for fields and methods using post-erasure JVM types. Class files can also store a **Signature attribute** carrying type parameters and actual generic types for tools and future compiler passes.

The two serve different roles:

~~~text
Method descriptor:
    (Ljava/io/Serializable;)Ljava/io/Serializable;

Generic Signature:
    describes <T extends Serializable & Comparable<T>> T echo(T)
~~~

The descriptor is the key information for JVM method resolution. The Generic Signature is supplementary metadata; it does not create a separate JVM method per type argument. The JVM does not have two runtime classes `List<String>` and `List<Integer>` merely because source code uses generics.

Hence changing generic metadata **might** only alter source/reflection contracts if the descriptor stays identical; however, changing the erasure to another type typically **changes the descriptor**, risking broken linkage with old clients.

## 3. Erasure rules for type variables

Java Generics use **type erasure**. For a type variable with upper bounds, erasure is determined by its **leftmost bound**, i.e., the first bound, after applying the relevant erasure rules.

Examples:

| Type parameter declaration | Erasure of T |
| --- | --- |
| `<T>` | `Object` |
| `<T extends Number>` | `Number` |
| `<T extends java.io.Serializable>` | `Serializable` |
| `<T extends java.io.Serializable & Comparable<T>>` | `Serializable` |
| `<T extends Comparable<T> & java.io.Serializable>` | `Comparable` |
| `<T extends Number & java.io.Serializable & Comparable<T>>` | `Number` |
| `<T extends Number & Comparable<T> & java.io.Serializable>` | `Number` |

**Critically important:** Java requires that if there is a **class bound** like `Number`, it must appear **first** before any interface bounds. You cannot swap `Number` after an interface and remain syntactically valid.

~~~java
// Valid: class first, then interfaces.
<T extends Number & java.io.Serializable & Comparable<T>>

// Invalid in the language:
// <T extends java.io.Serializable & Number & Comparable<T>>
// Class Number cannot appear after an interface bound.
~~~

If there is no explicit class bound, all bounds are interface bounds, and **the first interface determines erasure**.

### 3.1. An intersection type is not "an intersection JVM class"

`T extends Serializable & Comparable<T>` means `T` must satisfy both interfaces during compile-time type checking.

It does not create a special runtime class `SerializableAndComparable`. The JVM uses the first erased type in descriptors; when code needs to invoke a method from a secondary bound, the compiler can insert appropriate `checkcast` instructions.

Thus the claim "both interfaces are required so order does not matter" is **false with respect to erasure and binary compatibility**.

### 3.2. Bounds also determine which members may be used

~~~java
static <T extends java.io.Serializable & Comparable<T>>
int compare(T a, T b) {
    return a.compareTo(b);
}
~~~

The compiler accepts `compareTo` because `Comparable<T>` appears in the bounds, even though it is not the first bound.

If **`Comparable<T>` is removed** from the bound set, the body is no longer guaranteed to have `compareTo`. If only **bound order is changed** while keeping both, the corresponding source-level capabilities from those interfaces generally remain available; however, erasure and bytecode signatures can change.

## 4. What do parameter and return type T erase to?

Example:

~~~java
class Library {
    static <T extends Number> T identity(T value) {
        return value;
    }
}
~~~

In source:

~~~text
<T extends Number> T identity(T value)
~~~

After erasure, the corresponding JVM descriptor is:

~~~text
(Ljava/lang/Number;)Ljava/lang/Number;
~~~

With:

~~~java
static <T extends java.io.Serializable & Comparable<T>>
T echo(T value) {
    return value;
}
~~~

JVM descriptor:

~~~text
(Ljava/io/Serializable;)Ljava/io/Serializable;
~~~

After swapping the first interface:

~~~java
static <T extends Comparable<T> & java.io.Serializable>
T echo(T value) {
    return value;
}
~~~

The JVM descriptor changes to:

~~~text
(Ljava/lang/Comparable;)Ljava/lang/Comparable;
~~~

**The descriptor includes both parameters and the return type**. For a field typed with a type variable, the field descriptor is also based on that variable's erasure.

Do not assume changing bounds only alters "documentation-like" information. In the example above, it changed the method's **binary identity** for linking compiled code.

## 5. Experiment 1: keeping the same two bounds while swapping their order

### 5.1. Old API

Create a directory containing the source file `api/Api.java`:

~~~java
package api;

public class Api {
    public static <T extends java.io.Serializable & Comparable<T>>
    T echo(T value) {
        return value;
    }
}
~~~

With Java 17, `javap -s -p api.Api` after compiling will show `echo`'s descriptor includes:

~~~text
descriptor: (Ljava/io/Serializable;)Ljava/io/Serializable;
~~~

### 5.2. Client compiled against the old API

File `Client.java`:

~~~java
import api.Api;

public class Client {
    public static void main(String[] args) {
        System.out.println("result=" + Api.echo("ok"));
    }
}
~~~

`String` implements both `Serializable` and `Comparable<String>`, so the call is valid.

Example commands using **Bash** from the directory containing `api/Api.java` and `Client.java`:

~~~bash
mkdir -p out/api out/client
javac --release 17 -d out/api api/Api.java
javac --release 17 -cp out/api -d out/client Client.java
java -cp out/client:out/api Client
~~~

Stdout:

~~~text
result=ok
~~~

On Windows, the classpath separator is `;` instead of `:`:

~~~text
java -cp "out/client;out/api" Client
~~~

**Keep the file `out/client/Client.class` intact** for the next step. Do not recompile `Client` when swapping the library.

### 5.3. New API: only changing bound order

Replace the contents of `api/Api.java` with:

~~~java
package api;

public class Api {
    public static <T extends Comparable<T> & java.io.Serializable>
    T echo(T value) {
        return value;
    }
}
~~~

Both type bounds are identical, only their positions changed. Recompile **only the library**:

~~~bash
javac --release 17 -d out/api api/Api.java
javap -classpath out/api -p -s api.Api
~~~

New descriptor:

~~~text
descriptor: (Ljava/lang/Comparable;)Ljava/lang/Comparable;
~~~

Run the **old `Client.class`**:

~~~bash
java -cp out/client:out/api Client
~~~

As a result, the program fails with a linkage error:

~~~text
java.lang.NoSuchMethodError:
'java.io.Serializable api.Api.echo(java.io.Serializable)'
~~~

Actual output may include the `Exception in thread "main"` prefix and a stack trace, with file/line details depending on the environment. This lesson excerpts only the core diagnostic without pretending stack trace lines are always identical.

**Cause**: `Client.class` was compiled to call the old descriptor taking/returning `Serializable`. The new `Api` class only has the descriptor taking/returning `Comparable`. The JVM cannot find a method matching the old descriptor, even though client source still reads `Api.echo("ok")` and can recompile cleanly.

### 5.4. Recompiling the client is completely different from keeping the old binary

If `Client.java` is recompiled against the new `Api`:

~~~bash
javac --release 17 -cp out/api -d out/client Client.java
java -cp out/client:out/api Client
~~~

The output is again:

~~~text
result=ok
~~~

Because the compiler now emits a call to the new `Comparable` descriptor. This proves:
- Concrete client **source** may remain valid.
- Old client **binary** is incompatible with the new `Api` version.
- Doing a "clean build" of an entire project sometimes hides a breaking change that will still fail in plugins, modules, or shipped libraries that users do not recompile.

This is not mere theory: when tested with a real JDK, compiling v1/v2 succeeds, running the old client with v1 prints `result=ok`, and swapping in only `Api.class` v2 triggers `NoSuchMethodError` exactly as described.

## 6. Experiment 2: reordering **secondary bounds** while keeping the first bound

Suppose a class bound comes first:

~~~java
static <T extends Number
        & java.io.Serializable
        & Comparable<T>> T echo(T value) {
    return value;
}
~~~

If only the two interfaces after `Number` are swapped:

~~~java
static <T extends Number
        & Comparable<T>
        & java.io.Serializable> T echo(T value) {
    return value;
}
~~~

Both signatures have **`erasure(T) = Number`**, because the leftmost bound is still `Number`.

Therefore the descriptor of `echo(T) : T` in both cases remains:

~~~text
(Ljava/lang/Number;)Ljava/lang/Number;
~~~

**Bounded conclusion:** swapping only secondary bounds without changing erasure **does not on its own alter the descriptor of this simple method**. Already-compiled clients can still link if the method keeps the same descriptor and other binary linkage conditions hold.

Even so, the change is still observable via:
- Generic `Signature` metadata.
- Order of `TypeVariable.getBounds()` in Java Reflection.
- Schema generators, API documentation tools, or frameworks with logic depending on metadata/order.
- Source contracts in other changes involving secondary bounds, especially adding/removing bounds rather than merely swapping.

Do not conclude "because the descriptors are identical, all behavior is definitely identical". Check the implementation, inherited members, code generation, and components relying on generic metadata.

### 6.1. Why must the `Number` bound come first?

Java enforces that if a type variable has both class and interface bounds, the class appears first:

~~~java
// Valid:
<T extends Number & java.io.Serializable & Comparable<T>>

// Invalid:
// <T extends java.io.Serializable & Number & Comparable<T>>
~~~

This restricts valid arrangements. When a type parameter has a class bound, **reordering trailing interfaces** generally preserves class erasure; however, when **changing the class bound itself**, erasure can still change.

If there are only interface bounds, such as `Serializable & Comparable<T>`, swapping interfaces can **immediately change erasure**.

## 7. Java 17+ program inspecting erasure and bounds via Reflection

Save as **BoundOrderDemo.java**:

~~~java
import java.io.Serializable;
import java.lang.reflect.Method;
import java.lang.reflect.Type;
import java.util.Arrays;

public class BoundOrderDemo {
    static class SerializableFirst {
        static <T extends Serializable & Comparable<T>>
        T echo(T value) {
            return value;
        }
    }

    static class ComparableFirst {
        static <T extends Comparable<T> & Serializable>
        T echo(T value) {
            return value;
        }
    }

    static class NumberFirstA {
        static <T extends Number & Serializable & Comparable<T>>
        T echo(T value) {
            return value;
        }
    }

    static class NumberFirstB {
        static <T extends Number & Comparable<T> & Serializable>
        T echo(T value) {
            return value;
        }
    }

    private static String bounds(Method method) {
        return Arrays.stream(
                method.getTypeParameters()[0].getBounds()
        ).map(Type::getTypeName)
         .reduce((a, b) -> a + " | " + b)
         .orElse("");
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Method s = SerializableFirst.class
                .getDeclaredMethod("echo", Serializable.class);

        Method c = ComparableFirst.class
                .getDeclaredMethod("echo", Comparable.class);

        Method n1 = NumberFirstA.class
                .getDeclaredMethod("echo", Number.class);

        Method n2 = NumberFirstB.class
                .getDeclaredMethod("echo", Number.class);

        System.out.println(
                "firstA=" + s.getParameterTypes()[0].getTypeName()
        );
        System.out.println(
                "firstB=" + c.getParameterTypes()[0].getTypeName()
        );
        System.out.println(
                "returnA=" + s.getReturnType().getTypeName()
        );
        System.out.println(
                "returnB=" + c.getReturnType().getTypeName()
        );

        System.out.println("boundsA=" + bounds(s));
        System.out.println("boundsB=" + bounds(c));

        System.out.println(
                "stableA=" + n1.getParameterTypes()[0].getTypeName()
        );
        System.out.println(
                "stableB=" + n2.getParameterTypes()[0].getTypeName()
        );
        System.out.println("stableBoundsA=" + bounds(n1));
        System.out.println("stableBoundsB=" + bounds(n2));

        System.out.println(
                "values=" + SerializableFirst.echo("ok")
                        + "/" + ComparableFirst.echo("ok")
        );
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac --release 17 -Xlint:all BoundOrderDemo.java
java BoundOrderDemo
~~~

Exact stdout:

~~~text
firstA=java.io.Serializable
firstB=java.lang.Comparable
returnA=java.io.Serializable
returnB=java.lang.Comparable
boundsA=java.io.Serializable | java.lang.Comparable<T>
boundsB=java.lang.Comparable<T> | java.io.Serializable
stableA=java.lang.Number
stableB=java.lang.Number
stableBoundsA=java.lang.Number | java.io.Serializable | java.lang.Comparable<T>
stableBoundsB=java.lang.Number | java.lang.Comparable<T> | java.io.Serializable
values=ok/ok
~~~

The first lines use `Method.getParameterTypes()` and `getReturnType()` to inspect **erased classes**: `Serializable` or `Comparable` matching the leading bound.

The `boundsA/boundsB` lines use `TypeVariable.getBounds()` to read **generic declarations** in exact order and full detail. These are not types that the JVM distinguishes with a dedicated runtime class per intersection.

The two `stableA/stableB` lines show that when `Number` stays first, both erased parameter types are `Number`. Meanwhile `stableBoundsA/stableBoundsB` still differ because Reflection preserves the order of secondary bounds.

Finally, `values=ok/ok` illustrates that **both versions can run fine if clients compile against each matching version**; it does not prove an old client binary can link against a version with a different descriptor.

## 8. Distinguishing Method descriptor from Generic Signature attribute

A generic declaration carries more information than a bytecode descriptor.

Example method:

~~~java
static <T extends Serializable & Comparable<T>> T echo(T value)
~~~

There are distinct concepts:

| Layer | Meaning |
| --- | --- |
| **Source declaration** | `T` and its bounds form type-checking rules for `javac`. |
| **Erasure** | `T` turns into its leftmost bound to produce erased types. |
| **Method descriptor** | Describes parameter/return types used by the JVM during linkage, here `Serializable→Serializable`. |
| **Signature attribute** | Preserves descriptions of type parameters/bounds and generic constructs for reflection and the compiler. |

A class file can hold both an erased descriptor and a `Signature` showing both bounds in full. When reordering bounds while keeping the first bound intact, the descriptor may stay unchanged while the `Signature` metadata changes.

To inspect:

~~~bash
javap -v -p BoundOrderDemo
~~~

If the method is inside a nested class:

~~~bash
javap -v -p 'BoundOrderDemo$SerializableFirst'
~~~

The `$` in the binary name denotes a nested class. The example above uses single quotes suitable for Bash/PowerShell so special characters are not interpolated.

Look for:
- `descriptor:` — JVM types for the method.
- `Signature:` — generic signature when present.
- `Code:` — implementation instructions.
- `ACC_BRIDGE`/`ACC_SYNTHETIC` if the compiler generated bridge methods in a class hierarchy with overriding.

**Do not read Signature as though it were the descriptor used for method linkage.** What caused `NoSuchMethodError` in the experiment is precisely the mismatch between the descriptor the client calls and the descriptor the library actually provides.

## 9. Changing the first bound affects generic methods, fields, and classes

Individual generic methods are not the only things affected. A **generic class** with a type variable `T` also generates member signatures based on `erasure(T)`.

Suppose library v1:

~~~java
public class Box<T extends java.io.Serializable> {
    public T value;

    public T get() {
        return value;
    }

    public void set(T replacement) {
        value = replacement;
    }
}
~~~

Relevant erased types:
- `value` field descriptor is `Serializable`.
- `get()` return descriptor is `Serializable`.
- `set(T)` parameter descriptor is `Serializable`.

If changed to:

~~~java
public class Box<T extends Comparable<T> & java.io.Serializable> {
    public T value;

    public T get() {
        return value;
    }

    public void set(T replacement) {
        value = replacement;
    }
}
~~~

The leftmost bound becomes `Comparable`. **The erased descriptors of fields and methods using `T` will change**. An old client may fail with:
- `NoSuchFieldError` when accessing the field by the old descriptor.
- `NoSuchMethodError` when calling `get` or `set` by the old descriptor.

Key takeaway: `T` appears in many places across a public/protected bytecode API, so changing the first bound can trigger **a cascade of binary signature changes**, not just one generic annotation.

### 9.1. What if T only appears in metadata?

A generic bound change does not always break every binary client:
- If public method/field descriptors genuinely **do not change**, calls to those descriptors do not lose linkage **solely due to bound order**.
- If a change only affects `Signature` metadata, ordinary JVM calls can keep running.
- Even so, new compiler passes, reflective tools, method selection, or implementation behavior can still be affected.

Therefore, **do not** apply an absolute rule like "changing bounds is always binary-incompatible" or "not changing method names is always compatible". Check the **actual erased ABI**.

## 10. Changing secondary bounds: source compatibility can change even if the binary descriptor stays the same

Consider v1:

~~~java
static <T extends Number & java.io.Serializable>
T pass(T value) {
    return value;
}
~~~

And v2 adds an interface constraint:

~~~java
static <T extends Number & java.io.Serializable & Comparable<T>>
T pass(T value) {
    return value;
}
~~~

The first bound is still `Number`, so if the method body/remaining signature is unchanged, the erased descriptor of `pass(T):T` remains `Number→Number`.

However, **the set of source types permitted as arguments can shrink**. A `Number` subtype implementing `Serializable` without `Comparable<T>` would be accepted in v1 and rejected by `javac` in v2.

For example, an application-defined `Number` class implementing `Serializable` but not `Comparable`:

~~~java
final class Metric extends Number
        implements java.io.Serializable {

    private final int value;

    Metric(int value) {
        this.value = value;
    }

    public int intValue()    { return value; }
    public long longValue()  { return value; }
    public float floatValue(){ return value; }
    public double doubleValue(){ return value; }
}
~~~

`pass(new Metric(1))` is valid in v1 yet **fails to compile in v2** due to missing `Comparable<Metric>`. That caller's source compatibility is broken even though `T`'s erasure remains `Number`.

If a client was compiled against v1, whether the JVM can still link with v2 depends on descriptors and other implementation changes. In the simple `return value` example, the `Number→Number` descriptor is identical and the old client can still call it. Yet if v2 starts calling `compareTo` through the new bound, a `Metric` object sent by an old client can fail at runtime when the implementation casts/uses `Comparable`.

**Do not confuse "links successfully" with "behavior remains correct".** The source contract became stricter while old bytecode can keep invoking the method, because the JVM does not verify generic bounds as a full runtime contract on every invocation.

## 11. Changing from unbounded T to bounded T can change erasure

Initial API example:

~~~java
static <T> T same(T value) {
    return value;
}
~~~

`T`'s erasure is `Object`, so the descriptor is:

~~~text
(Ljava/lang/Object;)Ljava/lang/Object;
~~~

Changed to:

~~~java
static <T extends CharSequence> T same(T value) {
    return value;
}
~~~

`T`'s erasure becomes `CharSequence` and the descriptor changes:

~~~text
(Ljava/lang/CharSequence;)Ljava/lang/CharSequence;
~~~

Even though the method name `same` did not change, and many arguments like `String` still satisfy the new constraint, pre-compiled binary clients looking for the `Object` descriptor can hit `NoSuchMethodError` if no old-compatible method remains.

Conversely, **adding a secondary bound** after a stable first bound does not change erasure on its own, so it must be evaluated separately.

### 11.1. Changing the first class bound

~~~java
<T extends Number & java.io.Serializable>
~~~

to:

~~~java
<T extends Integer & java.io.Serializable>
~~~

**Is it invalid** because `Integer` is a `final` class and cannot serve as a superclass bound for a new subtype? A Java type parameter `<T extends Integer>` can actually be a valid declaration even though `Integer` is final: `T` can only be `Integer`, which the compiler can accept. Yet choosing an overly narrow bound is a design issue, not an example to rely on for general runtime behavior.

A clearer example:

~~~java
<T extends Number>
~~~

changed to:

~~~java
<T extends java.lang.Comparable<T>>
~~~

changes erasure from `Number` to `Comparable`; if the method signature uses `T`, the corresponding erased ABI can change.

**Principle:** changing the **first** bound or prepending a class bound before existing interfaces can change erasure, even when all other constraints stay intact.

## 12. `throws T` signatures and exception bounds

Java allows a suitably bounded type variable in `throws`:

~~~java
static <E extends Exception> void propagate(E ex) throws E {
    throw ex;
}
~~~

Here `E` is a type variable whose erasure relates to the `Exception` bound. If the method uses `E` as a parameter or return type, changing the first bound can change **the descriptor of that `E` position itself**.

Another point to keep separate: Java's `throws` clause **is not part of the JVM method descriptor in the sense of parameter/return types**. Changing only the list of checked exceptions in `throws` without altering erased parameter/return descriptors does not necessarily break method resolution.

However, changing `throws` can:
- Break **source compatibility** because the compiler enforces checked-exception rules.
- Change the `Exceptions` attribute or `Signature` metadata.
- Affect Reflection (`getExceptionTypes` / `getGenericExceptionTypes`).
- Affect actual behavior if the implementation throws different exceptions.

Do not generalize "every generic exception bound change causes `NoSuchMethodError`". Check whether `E` appears in **parameter/return descriptors**, then check the other contracts.

## 13. Interface methods, overriding, and bridge methods

Changing the erasure of type variables in generic interfaces or superclasses affects more than a standalone method. It can interact with **overriding** and bridge methods generated by `javac`.

Example:

~~~java
interface Store<T> {
    T get();
    void put(T value);
}

final class StringStore implements Store<String> {
    private String value;

    public String get() {
        return value;
    }

    public void put(String value) {
        this.value = value;
    }
}
~~~

After erasure of unbounded `Store<T>`, the interface methods have descriptors corresponding to `Object`. The compiler can generate **bridge methods** in `StringStore` so that a call through `Store` still reaches the implementation taking/returning `String`.

If in a later library version `Store` changes to `Store<T extends CharSequence>`, method declarations using `T` may get descriptors corresponding to `CharSequence` instead of `Object`.

Risks:
- An old client using `invokeinterface Store.get:()Ljava/lang/Object;` may fail to find the method with the old descriptor in the new interface version.
- A previously compiled implementation may no longer satisfy new contracts/bridge expectations.
- Depending on the exact interface/class change and bytecode, `NoSuchMethodError`, `AbstractMethodError`, or other linkage/behavioral errors may occur.

**Do not guess the exact error from a source snippet alone** when multiple inheritance/bridge relationships exist. The reliable approach is checking `javap -p -s -v` on both library and implementation classes before/after, and running **old client and plugin binaries** against the new library.

### 13.1. Bridge methods are not an automatic cure-all

The compiler generates bridge methods in specific situations needed to preserve dispatch under overriding and erasure rules; there is no promise that it will automatically retain **every public descriptor of an earlier API version** after a developer changes bounds.

For example, the static method `Api.echo` in section 5 **is not rescued by a bridge method** merely from reordering generic bounds. When binary compatibility is required, an explicit API/compatibility strategy is needed rather than expecting the compiler to synthesize adapters for every old signature.

## 14. Generic overloads, method lookup, and erasure clashes

Generic overload resolution occurs at **compile time** based on available methods and type constraints. After erasure, JVM method names/descriptors must satisfy non-collision rules.

Example:

~~~java
static <T extends java.io.Serializable> void use(T value) {
    System.out.println("serializable");
}
~~~

If `T`'s first bound changes to `Comparable`, the erased parameter descriptor changes. That affects not only old clients, but also how the compiler views the overload set in source.

Two distinct declarations can suffer a **name clash** when their erasures match, e.g.:

~~~java
// These methods cannot overload solely by type argument:
// void add(List<String> values) { }
// void add(List<Integer> values) { }
~~~

Both have their `List<String>`/`List<Integer>` parameter erased to raw `List` in bytecode, causing identical erased signatures.

When changing bounds, check:
- Are all overloads still valid in source?
- Do erased parameter types change?
- Which bytecode method descriptors disappear or appear?
- Do compiled clients invoke an existing descriptor?
- Do bridge/synthetic methods change?

**The same method name** is not enough to prove binary compatibility. A method that "looks equivalent" in Java source may not be the binary method old clients reference.

## 15. Reflection reads bounds in order, yet does not prove binary compatibility on its own

Useful Reflection APIs:

~~~java
Method m = SomeClass.class.getDeclaredMethod(
        "echo", java.io.Serializable.class
);

TypeVariable<Method> t = m.getTypeParameters()[0];

Type[] bounds = t.getBounds();
Class<?> erasedReturn = m.getReturnType();
Class<?>[] erasedParams = m.getParameterTypes();
Type genericReturn = m.getGenericReturnType();
~~~

If the first bound changed to `Comparable`, looking up `getDeclaredMethod("echo", Serializable.class)` can fail because the new erased parameter type is no longer `Serializable`. You must use the method's actual erased parameter type.

In the `BoundOrderDemo` program:
- `SerializableFirst` has erased parameter/return `Serializable`.
- `ComparableFirst` has erased parameter/return `Comparable`.
- `NumberFirstA` and `NumberFirstB` both have erased parameter/return `Number`, even though `getBounds()` reports different secondary bound orders.

**Reflection is very useful for inspecting metadata**, yet to confirm backward binary compatibility, use **`javap` descriptors and run old client binaries**. Frameworks relying on `TypeVariable.getBounds()` may change behavior after secondary bounds are swapped even when JVM descriptors stay unchanged.

### 15.1. `TypeVariable.getBounds` should not be sorted arbitrarily

Bound order in a generic declaration is meaningful information for erasure. A schema tool that sorts alphabetically and then uses the first element as the erasure will compute the wrong type if the original first bound differs from the post-sort first element.

When simply displaying an intersection of interfaces to human readers, you can present it nicely. Yet when computing erasure, **preserve the declared bound order** and never reorder before determining the leftmost bound.

## 16. How to test ABI before and after a library change

A practical workflow for reviewing changes:

### 16.1. Lock down the old version

Build the old library into a jar or class directory, and keep a compiled sample client:

~~~bash
javac --release 17 -d old-classes api/Api.java
javac --release 17 -cp old-classes -d client-classes Client.java
~~~

Do not keep only source. The defining point of binary compatibility is **keeping the old client `.class` file intact**.

### 16.2. Inspect erased descriptors

~~~bash
javap -p -s -classpath old-classes api.Api
javap -p -s -classpath new-classes api.Api
~~~

Compare:
- Class/interface names.
- Method names and erased parameter/return descriptors.
- Fields and descriptors.
- Visibility/access modifiers, static/instance.
- Members changed due to inheritance and compiler bridges.

To inspect generic metadata:

~~~bash
javap -p -v -classpath old-classes api.Api
javap -p -v -classpath new-classes api.Api
~~~

Compare `Signature` attributes, type parameters, bounds, and other relevant attributes.

### 16.3. Run the old binary against the new library

Do not recompile `Client.class` in this test:

~~~bash
java -cp client-classes:new-classes Client
~~~

On Windows replace `:` with `;` in the classpath. Make sure the classpath does not accidentally pick up old `Api.class` ahead of new `Api.class`, otherwise the test gives a **false pass**.

### 16.4. Recompile the client to test source compatibility

Only afterward run a separate test:

~~~bash
javac --release 17 -cp new-classes -d recompiled-client Client.java
~~~

It is possible for the old client binary to fail while source recompilation succeeds (as in the first-bound swap experiment), or conversely for generic signature changes to reject source even when the erased descriptor stayed unchanged.

### 16.5. Behavioral and reflection tests

Even if the ABI holds, you still need:
- Tests with actual subtypes accepted by the APIs.
- Tests using raw/legacy clients if the library promises compatibility.
- Reflection/schema/serialization tests if consumers read `Signature`.
- Integration tests with subclasses, implementors, proxies, plugins, and method handles when the system uses them.

Binary API diff tools can help automate checks. Still, deployment specifics like dynamic classloading, modules, bridges, and bytecode generation require appropriate tests.

## 17. Quick evaluation table for each kind of bound change

| Change | Erasure of T | Binary risk | Source/metadata risk |
| --- | --- | --- | --- |
| `<T>` → `<T extends Number>` | `Object` → `Number` | High if `T` appears in public erased descriptors. | Many callers no longer satisfy the bound. |
| `Serializable & Comparable<T>` → `Comparable<T> & Serializable` | `Serializable` → `Comparable` | High if `T` is in parameters/returns/fields. | May still accept `String`; metadata order changes. |
| `Number & Serializable & Comparable<T>` → `Number & Comparable<T> & Serializable` | `Number` → `Number` | **Does not change descriptor** of the example using `T`. | `Signature`/Reflection order changes; check other contracts. |
| `Number & Serializable` → `Number & Serializable & Comparable<T>` | `Number` → `Number` | Descriptor does not change on its own, though implementation/bridges may change. | Valid type-argument set shrinks; client recompilation may fail. |
| `Number & Serializable` → `Number` | `Number` → `Number` | Simple descriptor stays stable if everything else is unchanged. | Valid type-argument set widens; implementation may change. |
| `Number` → `CharSequence` | `Number` → `CharSequence` | Can change the ABI of members using `T`. | Callers relying on `Number` may be rejected. |
| Changing only `throws` checked exception types | Parameters/returns do not necessarily change | Does not change method descriptor solely due to `throws`. | Source checked-exception contract and Reflection change. |
| Changing member visibility, `static`, or inheritance | Depends on more than bounds | Separate risks per JVM/JLS binary rules. | Evaluate separately. |

"Binary risk" does not mean all clients fail. Clients calling only members whose descriptors stayed intact may be unaffected. However, if the public ABI loses a previously published descriptor, **that is a breaking change for binary clients depending on that descriptor**.

## 18. Designing APIs to avoid unnecessary coupling to erasure

### 18.1. Do not add intersection bounds just because they look nice

If a method only stores/forwards a value and does not actually need `Comparable`, adding `Comparable` only makes the API stricter and can affect compatibility without providing any capability that is actually used.

~~~java
static <T extends java.io.Serializable> T keep(T value) {
    return value;
}
~~~

If you only need to pass an object without using `Serializable` members, even `<T> T keep(T)` or a non-generic API might be more suitable; however, **do not arbitrarily change an already-published API**, because dropping the `Serializable` bound itself changes erasure to `Object`.

### 18.2. Treat the choice of first bound as an ABI decision

When designing a **new** API using multiple interface bounds, recognize that choosing which interface comes first is not merely aesthetic. If `T` is used in method parameter/return/field signatures, the first interface will appear in erased descriptors.

Do not expect to reorder bounds freely after release without impacting users. Pick an order for clear design reasons and keep it stable unless accepting a breaking change and corresponding versioning.

### 18.3. Keep operational requirements out of public signatures when sensible

Sometimes a method only needs to accept a wide type, then check an optional capability internally:

~~~java
static String describe(Object value) {
    return String.valueOf(value);
}
~~~

If the API genuinely does not need to assume `Comparable` or `Serializable` in its type contract, do not add those bounds "just in case". Conversely, if the algorithm strictly requires `compareTo` with compile-time type safety, a `Comparable` bound may be a genuine requirement. The goal is for **bounds to reflect real needs** and not be changed carelessly in a released ABI.

### 18.4. Do not force raw/unchecked types to "preserve compatibility"

A client failing to compile with new bounds should not be patched with arbitrary raw casts:

~~~java
// Stripping type checking with a raw type or unchecked cast
// does not bring back the old JVM descriptor.
~~~

Raw types/casts sacrifice type safety yet do not fix a `NoSuchMethodError` caused by a missing binary descriptor. You must solve **API linkage**, not silence compiler diagnostics.

## 19. Migration strategies when changing the first bound is unavoidable

If you must change the bounds and erasure of an already-published public API, options to consider:

1. **Preserve the old ABI if possible:** avoid changing the first bound; introduce the new requirement via a clear helper/overload without erasure collision.
2. **Add a new API with a different name:** e.g., `echoComparable` instead of replacing `echo` in place, letting old clients keep calling `echo`.
3. **Keep an adapter with the old descriptor when appropriate:** the old method forwards to the new logic, yet type contracts must be checked; in Java source you cannot overload differing only in return type.
4. **Version as a breaking change** if the old descriptor cannot be kept, and communicate the requirement to rebuild/relink modules.
5. **Evaluate class inheritance and bridge methods**: a manual adapter may not suffice in generic interfaces/overrides.
6. **Test old client binaries**, not just rebuilding all code from source.
7. **Test Source APIs** after the change: callers passing type arguments violating the new bounds must receive clear compile errors.
8. **Do not assume a JVM compatibility shim is always valid**: you may hit erased signature clashes or altered dispatch/overload resolution.

For the simple method in section 5, you can keep the old method named `echo` and introduce a new method named `echoComparable`, avoiding losing the old descriptor. If you want both the old name and new types, design carefully so erased signatures and overload behavior do not conflict.

### 19.1. An adapter can retain the old descriptor with a legal overload

For instance, if signatures differ in erased parameter types, a library can provide **two overloads** with the same name when Java allows it and method resolution does not collide:

~~~java
public static <T extends java.io.Serializable & Comparable<T>>
T echo(T value) {
    return value;
}

public static <T extends Comparable<T> & java.io.Serializable>
T echoComparable(T value) {
    return value;
}
~~~

This option keeps **the old name + old erased signature** and adds **a new name**, rather than a trick that magically gives one new method both descriptors. A distinct method name makes binary behavior explicit, avoiding overload ambiguity when an input like `String` implements multiple interfaces.

Do not claim a new overload of the same name with `Serializable` and `Comparable` will always resolve cleanly in Java calls: `String` is a subtype of both, while neither interface is a subtype of the other, so overloading can trigger an **ambiguous method call** upon recompilation. Versioning or a separately named API is usually easier to control.

## 20. Bound ordering and reflection/schema frameworks

Some tools inspect generic declarations via:

~~~java
TypeVariable<?> typeVar =
        SomeClass.class.getTypeParameters()[0];

Type[] bounds = typeVar.getBounds();
~~~

Even when secondary bounds are reordered and the member's JVM descriptor remains unchanged, tools that:
- log or display bounds in declaration order;
- pick the first bound as representative of the erased runtime class;
- build schemas or mapping constraints;
- compare generic signatures when constructing cache keys;
- generate code or proxies based on generic information;

can observe the difference.

When changing an API, **do not test only JVM linkage while ignoring the public metadata contract** if the library's ecosystem uses reflection. Frameworks may rely on metadata differently; not every reliance on secondary bound order is ideal, yet changing the order can still alter their results.

### 20.1. Do not parse `getTypeName` to guess erasure alphabetically

`TypeVariable.getBounds()` returns `Type[]` in order, yet bounds can be `ParameterizedType`, `Class`, or other type variables. Computing erasure accurately requires following JLS rules and `Type` structure, not sorting `String` names alphabetically or naively taking the runtime class name of a generic object.

`java.lang.reflect.Type` in generics is metadata about signatures, not runtime type checking of arbitrary data. Do not confuse reflection with full runtime reification of type arguments.

## 21. Common mistakes

### "Intersection bounds are just a set; reordering cannot cause errors"

False. With multiple interface bounds, **the leftmost bound determines erasure**. Swapping `Serializable` and `Comparable` can change erased descriptors and break old binary clients.

### "Changing bounds always causes `NoSuchMethodError`"

False. If erasure/erased descriptors stay unchanged and other binary contracts hold, a simple secondary bound change may produce no linkage error on method calls. Source/behavior/metadata must still be checked.

### "Client source still compiles means binary-compatible"

False. Recompiled Java client source can call the new descriptor, whereas old `Client.class` still references the old descriptor.

### "Methods with the same name and same `T` are the same method to the JVM"

False. The JVM distinguishes methods by name/descriptor; `erasure(T)` can change parameter or return descriptors even though source uses the same symbol `T`.

### "Changing types in `throws` definitely changes the JVM descriptor"

False. The `throws` clause is not part of parameter/return descriptors. However, if the type variable also appears in parameters/return, changing its erasure can change descriptors at those positions.

### "Adding a secondary bound has no source impact"

False. It can shrink the set of valid type arguments; e.g., `Number & Serializable` previously accepted non-`Comparable` types, whereas a version adding `Comparable<T>` does not.

### "Bridge methods always save binary compatibility"

False. Bridge methods serve specific polymorphism/erasure rules, and do not automatically preserve every old descriptor after arbitrary API redesigns.

### "A clean full-system build proves the API is non-breaking"

False. A clean build **recompiles clients** and can mask binary compatibility failures with pre-built plugins/jars. You must test old binaries separately against the new library.

### "Reflection sees two similar bounds so the runtime class is the same too"

Insufficient. Intersection constraints and Generic Signature metadata do not mean the JVM creates a new runtime class. JVM method descriptors remain governed by erasure.

### "Just suppressing warnings fixes linkage"

False. `@SuppressWarnings` does not change class-file descriptors called by `Client.class`. Fixing `NoSuchMethodError` requires providing a method with a compatible signature or shipping a breaking version and recompiling the affected scope.

## 22. Checklist when reviewing a generic bound change in a library

1. **Record old and new signatures**, including type parameter bounds and order.
2. **Identify the leftmost bound** of each type variable.
3. **Compute before/after erasure**: `Object`, class bound, first interface.
4. **List where `T` appears** in public/protected method parameters, return types, and field declarations.
5. **Compare JVM descriptors** using `javap -p -s` on real binaries.
6. **Compare generic `Signature`s** using `javap -v` and Reflection when the library has public metadata consumers.
7. **Inspect `throws`**: whether checked exceptions alter the source contract or only metadata; do not confuse with method descriptors.
8. **Check interface/superclass hierarchies**, overriding, and synthetic/bridge methods.
9. **Recompile client sources** to evaluate source compatibility, especially when adding bounds.
10. **Keep old `Client.class`** and run against the new jar to test binary compatibility.
11. **Ensure the classpath does not contain the old jar** shadowing the new class.
12. **Evaluate behavior**: casts, invokes, logic using secondary bounds, and old objects that may not satisfy new constraints.
13. **Test overloads** because changing erasure can affect overload resolution and name clashes.
14. **Test reflection/frameworks** if schemas/proxies/serialization use generic bounds.
15. **Update versioning and release notes** if the change is incompatible; announce recompilation or API migration requirements.
16. **Retain adapters with old names and descriptors if feasible**, avoiding breaking clients without clear benefit.
17. **Do not conflate compiler errors with JVM linkage errors**: which stage fails dictates the remedy.

## 23. Self-check questions

**1.** What is the erasure of `T` in `<T extends Serializable & Comparable<T>>`?

**Answer:** `Serializable`, because `Serializable` is the leftmost bound.

**2.** If swapped to `<T extends Comparable<T> & Serializable>`, what does erasure become?

**Answer:** `Comparable`. If `T` appears in parameters/return of a public method, the descriptor can change accordingly.

**3.** Does Java allow writing `<T extends Serializable & Number>` to put `Serializable` first?

**Answer:** No. If there is a class bound `Number`, the class must appear first before interface bounds.

**4.** Does swapping `Number & Serializable & Comparable<T>` to `Number & Comparable<T> & Serializable` change `erasure(T)`?

**Answer:** No. `Number` remains the first bound, so `erasure(T)` stays `Number`. Generic Signature/Reflection order still changes.

**5.** Why is `String` still source-compatible with both `Serializable`/`Comparable` orders?

**Answer:** `String` satisfies both `Serializable` and `Comparable<String>`. The same set of constraints is required, even though the order changed.

**6.** Why can old client bytecode get `NoSuchMethodError` when a library swaps two interface bounds?

**Answer:** The old client calls the descriptor taking/returning `Serializable`; the new method only has the descriptor taking/returning `Comparable`. The JVM cannot find the old method descriptor.

**7.** If recompiling `Client.java` against the new library works and runs, has binary compatibility been proven?

**Answer:** Not yet. That is source recompilation; you must run the exact old `Client.class` against the new library to check binary linkage.

**8.** When adding `Comparable<T>` after `Number` while keeping `Number` first, must the descriptor of a method using `T` change?

**Answer:** No; `erasure(T)` stays `Number`. However, callers using non-`Comparable<T>` types may no longer compile, and the new implementation could fail when handling old binaries.

**9.** What can changing a field of type `T` from `Box<T extends Serializable>` to `Box<T extends Comparable<T>>` affect?

**Answer:** The erased field descriptor changes from `Serializable` to `Comparable`; an old client accessing the field via the old descriptor can hit `NoSuchFieldError`.

**10.** Does changing only the `throws` clause automatically change the JVM method descriptor?

**Answer:** No, `throws` is not part of the JVM parameter/return descriptor. However, source exception analysis, attributes, and runtime behavior can be affected.

**11.** If a new library version has bridge methods, are all old binary callers guaranteed to run?

**Answer:** No. Bridge methods appear only in specific situations; actual descriptors and runtime compatibility must be verified.

**12.** Can Reflection reveal a swap of secondary bounds?

**Answer:** Yes. `TypeVariable.getBounds()` returns bounds in generic declaration order; even if erasure does not change, the array order can differ.

**13.** Why should tools compare both descriptors and `Signature` attributes?

**Answer:** Descriptors affect JVM linkage; `Signature` affects generic information for the compiler, Reflection, and metadata tools. The two layers can change independently.

**14.** Should a published API library arbitrarily "alphabetize bounds"?

**Answer:** No. The first bound's position can determine erasure. If improving readability, treat it as an API change, verify the ABI, and follow versioning policy.

**15.** When changing the first bound, what is the most reliable verification procedure?

**Answer:** Keep a client class compiled before the change, swap only the library binary, inspect `javap` descriptors and run the old client, while also recompiling client source separately to assess source compatibility.

## 24. Remember

**Bound order is a meaningful part of generic API design, not merely formatting.**

~~~text
<T extends Serializable & Comparable<T>>
            │ first bound
            ▼
   erasure(T) = Serializable
            │
            ▼
   erased descriptor of T uses Serializable

Swapping two interface bounds:

<T extends Comparable<T> & Serializable>
            │ new first bound
            ▼
   erasure(T) = Comparable
            │
            ▼
   erased descriptor of T uses Comparable

→ Old binary clients may look up the wrong descriptor
→ NoSuchMethodError if the old method no longer exists
~~~

When **the first bound stays unchanged** (such as `Number & Serializable & Comparable<T>` changed to `Number & Comparable<T> & Serializable`), `T`'s erasure remains `Number`: not every reordering changes descriptors. However, generic Signature/Reflection metadata changes, and adding/removing secondary constraints can also impact source compatibility, runtime behavior, and code generation.

To protect a published API, run **all three test kinds**: recompile client source, run old client binaries against the new library, and test behavior. Check `javap -s -p` for erased descriptors, `javap -v` for generic Signatures, and assess bridges/inheritance/fields if the type variable appears in multiple members.

**Practical rule:** choose bounds based on genuine needs, treat the leftmost bound as part of ABI design, avoid arbitrary reordering in public APIs, and never equate "source is still valid" with "published binaries remain compatible".