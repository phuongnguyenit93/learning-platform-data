# Generic Varargs Are Represented by Arrays in Java

## 1. Understanding the True Nature of T...

Varargs (*variable-length arguments*) allow calling a method with a variable number of arguments without manually constructing an array at every call site:

~~~java
static void log(String... messages) {
    for (String message : messages) {
        System.out.println(message);
    }
}

log("Java", "Generics", "Varargs");
~~~

Key technical point: `String...` **does not create a new storage mechanism**. Inside the method, the `messages` parameter is a **`String[]` array**.

Similarly, a generic method:

~~~java
static <T> void printAll(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
~~~

has a `values` parameter whose static type is **`T[]`**, i.e., an **array of T**, rather than a separate dynamic list.

The `T...` signature has a practical reading:

> The method accepts a final parameter of array type T[], and varargs syntax lets the compiler pack individual arguments into an array at the call site when invoked as a variable-arity call.

This is the root of both the convenience and the warnings when `T` is a non-reifiable generic type.

## 2. Varargs Is Neither an ArrayList Nor Multiple Independent Parameters

Compare:

~~~java
static int count(String... items) {
    return items.length;
}
~~~

It can be called as:

~~~java
count();                       // Zero elements.
count("A");                    // One element.
count("A", "B");               // Two elements.
count(new String[] {"A","B"}); // Pass an array directly.
~~~

Inside the method body, `items` is always a **`String[]`**. It has a `length` field, supports index access `items[0]`, and has no `add` method like a `List`.

The expression `count("A", "B")` is compiled under the variable-arity invocation rules, semantically equivalent to passing a two-element `String[]`. Meanwhile, `count(new String[]{"A","B"})` passes an array already created by the caller.

Do not imagine that a varargs method receives two separate variables named `items0` and `items1`. **At runtime, it is still a single array parameter.**

For generic varargs, the corresponding rule holds:

~~~java
static <T> int countGeneric(T... items) {
    return items.length;
}
~~~

`items` has static type `T[]`. However, because `T` is a type variable handled by Java generics through type erasure, we must be careful about the **runtime component type** of the array created at the call site.

## 3. Rules for Declaring Varargs in Methods and Constructors

In a method declaration, the varargs parameter must be in the **last** position:

~~~java
static <T> void describe(String title, T... items) {
    System.out.println(title + ": " + items.length);
}
~~~

Both call styles are valid:

~~~java
describe("Languages", "Java", "Go");
describe("Numbers", 1, 2, 3);
~~~

The compiler infers `T` from the arguments and invocation context. Both are passed into the method via the array parameter.

The following forms **intentionally fail to compile**:

~~~java
// static <T> void wrong(T... items, String title) { }
// A varargs parameter cannot appear before another parameter.

// static void wrong(String... first, Integer... second) { }
// A parameter list cannot have two varargs parameters.
~~~

The `...` syntax declares an array parameter with a convenient calling convention. It is not a second kind of generic and does not turn `T` into a runtime value that can be deeply checked.

## 4. Two Stages: Java Source and the Bytecode Method

Suppose:

~~~java
static <T> void inspect(T... values) {
    System.out.println(values.length);
}
~~~

In **Java source**:
- `T` is the method's type parameter.
- `T...` is varargs, meaning a `T[]` parameter inside the method body.
- When a caller passes individual arguments, the compiler selects and prepares an appropriate array according to type inference and varargs invocation rules.

After **type erasure**:
- If `T` has no explicit bound, the erasure of `T` is `Object`.
- The method descriptor has parameter **`Object[]`**.
- A call site can pass a concrete runtime array such as `String[]`, because **`String[]` is a subtype of `Object[]`**.

Example:

~~~java
inspect("Java", "Kotlin");
~~~

In a typical compilation, the compiler can create a **`String[]`** at the caller and pass it as `Object[]` via array subtyping to invoke the erased method. The method still receives an array whose runtime component class is `String`, even though the erased parameter signature is `Object[]`.

These are two different things:
1. **The erased parameter type in the method descriptor** can be `Object[]`.
2. **The actual runtime type of the array object passed in** can be `String[]` or `List[]`.

Do not interpret "T is erased to Object" as "every array passed through T... has runtime component Object." That is false because the runtime class of the array created at the caller is preserved.

### How T's Bound Affects Erasure

~~~java
static <T extends Number> void inspectNumbers(T... numbers) {
    System.out.println(numbers.length);
}
~~~

Here `T` is erased to its bound `Number` rather than `Object`, so the erased parameter type is `Number[]`. When called with `Integer` arguments, the caller can still pass a runtime `Integer[]` array compatible with `Number[]`.

Therefore, to analyze bytecode accurately, you must inspect **T's bound**, the argument types, and the call context, rather than always claiming generic varargs is just `Object[]`.

## 5. Why Can T... Produce a Generic Array Creation Warning?

Java allows the declaration:

~~~java
static void consume(List<String>... groups) {
    System.out.println(groups.length);
}
~~~

This form is valid in source code; inside, `groups` has static type **`List<String>[]`**.

Yet Java does not allow direct array creation:

~~~java
// List<String>[] groups = new List<String>[2];
// Error: generic array creation.
~~~

`List<String>` is not a **reifiable type**: a runtime `List` object does not carry the generic type argument `String` for the JVM to verify each element.

When calling:

~~~java
consume(List.of("A"), List.of("B"));
~~~

the compiler still has to pack the varargs arguments into **an array**. It creates an array whose runtime component is **`List`**, not a separate runtime class `List<String>`. Consequently, the compiler may warn:

~~~text
unchecked generic array creation for varargs parameter of type List<String>[]
~~~

The exact message may vary across `javac` versions. The warning indicates that array creation for the varargs call cannot preserve full type-argument guarantees.

This is how Java lets convenient generic varargs APIs exist while warning in cases where the compiler cannot prove safety.

## 6. Generic Array Creation Is Forbidden in Source Yet Varargs Can Still Be Called

The two statements below are not equivalent under language rules:

~~~java
// List<String>[] direct = new List<String>[2]; // Does not compile.

consume(List.of("A"), List.of("B")); // Compiles with a warning.
~~~

The first line is an **explicit array creation expression** with a non-reifiable component type, which Java forbids.

The second line is a **variable-arity invocation** of a method declared with varargs. The compiler is permitted to synthesize an appropriate array to execute the call, though it may emit an unchecked warning about the unsafety of the backing generic array.

Therefore, do not memorize the oversimplification that "Java cannot create any array for generics." More accurately:

> Java forbids certain array creation expressions with non-reifiable component types; a varargs call can be compiled into passing an array with erased generics, accompanied by warnings and potential heap pollution.

If the method uses that array properly and does not expose dangerous aliases, the API can operate safely. If the method body or external code abuses array covariance or raw references, wrong-type data can slip in.

## 7. Who Owns the Varargs Array?

In a call with individual arguments:

~~~java
inspect("A", "B");
~~~

the compiler typically creates an array at the **call site** and passes the reference into the method. The method receives a reference to that array; there is no rule requiring all elements to be copied before use.

With:

~~~java
String[] existing = {"A", "B"};
inspect(existing);
~~~

the call can proceed as a **fixed-arity invocation**: the caller passes the `existing` array directly as the final parameter. In that case, if the method body modifies `values[0]`, it can modify `existing[0]` itself.

Aliasing relationships matter when designing APIs:
- A method that only reads the array and computes a result is usually easier to prove safe.
- A method that mutates the array, stores it in a static/instance field, or returns it directly can cause caller and callee to observe each other's mutations.
- With a **non-reifiable component type**, aliasing the array through `Object[]` is an especially dangerous path to **heap pollution**.

Never assume "because the parameter is declared T..., Java automatically copies the elements." Varargs primarily changes call-site syntax and how the compiler packs arguments; it **does not automatically provide ownership or immutability**.

## 8. Consequences of Representing Generic Varargs with Arrays

In a **method** receiving `List<String>... groups`, the parameter's source type is `List<String>[]`, but the array's runtime component is `List`. Hence an `Object[]` alias can replace a slot with a `List<Integer>` object and still pass the runtime store check:

```java
static void unsafe(List<String>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(99);           // Still a List at runtime.
    String text = groups[0].get(0);   // ClassCastException.
}
```

Use this snippet **only to reproduce the bug**, with `import java.util.List;` and the call `unsafe(List.of("safe"))`; it intentionally triggers unchecked warnings at the declaration and call site. When the real array is `String[]`, writing an `Integer` through `Object[]` fails with `ArrayStoreException` right at the write because the JVM knows the `String` component type. With a `List[]` array, however, the JVM cannot check the `String` type argument inside each list.

Distinguish **the array created by the compiler for a variable-arity invocation** from **an array passed directly by the caller in a fixed-arity invocation**: the method does not automatically copy the array in every case. Assigning through an alias only replaces a slot in the array and does not necessarily modify the contents of the original `List` object. This lesson focuses on how **varargs → array** works; later lessons analyze alias writes, array exposure, and reading compiler diagnostics in detail.

## 9. Runnable Java 17+ Program

Save the following as **GenericVarargsDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;

public class GenericVarargsDemo {
    // Only inspect the array; do not modify or expose the reference.
    @SafeVarargs
    static <T> void inspect(String tag, T... values) {
        System.out.println(
                tag + " length=" + values.length
                        + " component="
                        + values.getClass()
                                .getComponentType()
                                .getTypeName()
        );
    }

    // Do not return the varargs array itself; create a copy via List.copyOf.
    @SafeVarargs
    static <T> List<T> safeCopy(T... values) {
        return List.copyOf(Arrays.asList(values));
    }

    // Read the List<String> elements without modifying the array or returning an alias.
    @SafeVarargs
    static void showGroups(List<String>... groups) {
        System.out.println(
                "groups component="
                        + groups.getClass()
                                .getComponentType()
                                .getTypeName()
        );
        System.out.println(
                "groups=" + Arrays.toString(groups)
        );
    }

    // INTENTIONALLY UNSAFE: to demonstrate heap pollution.
    static void unsafe(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(99);

        try {
            String first = groups[0].get(0);
            System.out.println(first);
        } catch (ClassCastException error) {
            System.out.println("unsafe=ClassCastException");
        }
    }

    public static void main(String[] args) {
        // The compiler creates an array when called with separate arguments.
        inspect("strings", "Java", "Go");

        // Pass an existing array owned by the caller.
        String[] explicit = {"A", "B"};
        inspect("explicit", explicit);

        // When T is List<String>, the runtime component is raw List.
        inspect("lists", List.of("x"), List.of("y"));

        // Safe snapshot for ordinary String arguments.
        System.out.println(
                "copy=" + safeCopy("red", "blue")
        );

        // Do not modify or expose the varargs array.
        showGroups(List.of("A"), List.of("B"));

        // Trigger a controlled failure to observe the safety boundary.
        unsafe(List.of("safe"));
    }
}
~~~

Compile at Java 17 language level:

~~~bash
javac --release 17 -Xlint:unchecked GenericVarargsDemo.java
java GenericVarargsDemo
~~~

**Expected compiler warnings** on `unsafe` and the call `unsafe(List.of("safe"))` because the unsafe method uses `List<String>...` with a non-reifiable component. The warnings read along the lines of:

~~~text
Possible heap pollution from parameterized vararg type List<String>
unchecked generic array creation for varargs parameter of type List<String>[]
~~~

These warnings are not part of program stdout.

**Exact stdout:**

~~~text
strings length=2 component=java.lang.String
explicit length=2 component=java.lang.String
lists length=2 component=java.util.List
copy=[red, blue]
groups component=java.util.List
groups=[[A], [B]]
unsafe=ClassCastException
~~~

### Key Takeaways from the Output

**`strings ... java.lang.String`:** when `T` is inferred as `String` and the caller passes two separate strings, the actual array has component type `String`.

**`explicit ... java.lang.String`:** passing an existing `String[]` also yields runtime component `String`. The output matches, though the parameter-passing path differs: the caller already constructed the array instead of the compiler packing individual arguments.

**`lists ... java.util.List`:** when `T` is inferred as `List<String>`, the runtime component of the created array is `List`. This does not prove at runtime that every array element is a `List<String>`.

**`copy=[red, blue]`:** the method copies elements into a `List` that does not allow mutation through standard methods. With non-null inputs as in the example, `List.copyOf` succeeds. This is a useful design to avoid returning the varargs array itself.

**`groups ... java.util.List`:** `showGroups` reads the `List[]` array created by the compiler; the method provides no write path into the backing array.

**`unsafe=ClassCastException`:** a `List<Integer>` was placed into an array treated as `List<String>[]` via an `Object[]` alias, and the error was caught when reading that element as a `String`.

## 10. What Does @SafeVarargs Mean?

`@SafeVarargs` is an annotation used by a method or constructor author to assert that the implementation **performs no operations that compromise type safety with respect to the varargs parameter**. It can suppress the corresponding varargs/unchecked warnings at the declaration and appropriate call sites.

Reasonable example:

~~~java
@SafeVarargs
static <T> List<T> snapshot(T... values) {
    return List.copyOf(Arrays.asList(values));
}
~~~

The method only reads elements and creates a new `List`; it does not return the array, write mismatched types into it, or store a mutable alias to it. Given appropriate inputs, this usage is safe against varargs array heap pollution.

**No new runtime checks** are generated by the annotation. `@SafeVarargs` does not make `List<String>` reifiable, does not turn the array component into `List<String>` at runtime, and does not automatically validate individual `List` elements.

If you attach `@SafeVarargs` to the `unsafe` method, the annotation does not make that body safe. It merely makes **a false promise** that can hide warnings at call sites; the code can still throw `ClassCastException`. `javac` may emit additional warnings or fail to catch every unsafe pattern, so **the API author must prove** that the method upholds the contract.

### Where Java 17 Permits @SafeVarargs

The annotation can be applied to:
- Varargs constructors.
- `static` varargs methods.
- `final` varargs methods.
- `private` varargs methods.

Do not use `@SafeVarargs` on a regular **overridable** instance method, because a guarantee on the current implementation does not prove that subclass overrides are also safe.

A method that is `static` or `final` without varargs is also not a valid target for this annotation.

### Are @SafeVarargs and @SuppressWarnings the Same?

Not entirely:

- `@SafeVarargs` declares the safety of a **varargs declaration**, affecting warnings at call sites as well.
- `@SuppressWarnings("unchecked")` is a directive to suppress unchecked warnings in its annotated scope; it makes no semantic guarantee proven by the compiler.
- Neither **checks generic arguments at runtime**.

Never use any annotation to hide warnings on a method known to mutate the array through an unsafe `Object[]` alias.

## 11. Inspecting Varargs in Bytecode with javap

After compiling:

~~~bash
javap -p GenericVarargsDemo
javap -c -p GenericVarargsDemo
javap -v -p GenericVarargsDemo
~~~

Things to observe:

1. The method signature in the class-file disassembler displays the varargs syntax, yet it remains an **array parameter**.
2. For `<T> void inspect(String,T...)`, the method is erased to a descriptor taking `String` and `Object[]` because `T` has no bound.
3. In `main`, variable-arity calls can be compiled by `javac` into array creation via bytecode instructions such as `anewarray java/lang/String` and `anewarray java/util/List`.
4. For `List<String>...`, the descriptor for the varargs array uses `List[]` after erasure.
5. `javap -v` shows method flags such as **ACC_VARARGS** where applicable.

Do not rely on exact instruction offsets or bytecode ordering from a particular `javac` build. What matters is understanding that every varargs call reduces at runtime to passing **one array parameter**, and generic arguments are not preserved in the array's component class.

### Fixed Arity vs. Variable Arity

With the signature:

~~~java
static void emit(String... values) { }
~~~

These two calls can follow two different forms:

~~~java
String[] existing = {"A", "B"};

emit(existing); // Pass an existing array.
emit("A", "B"); // The compiler packs two arguments into an array.
~~~

The compiler does not "always allocate an extra array" on every varargs call. If the caller passes a single matching array and the call resolves as fixed-arity, that array is passed directly.

## 12. Generic Varargs with Wildcards and Reifiable Types

Not every varargs parameter containing generic syntax produces an unchecked warning.

Example:

~~~java
static void inspectUnknown(List<?>... groups) {
    for (List<?> group : groups) {
        System.out.println(group.size());
    }
}
~~~

`List<?>` is a parameterized type with an **unbounded wildcard**, which is considered a **reifiable type**. Hence Java allows the expression:

~~~java
List<?>[] groups = new List<?>[2];
~~~

And the method `inspectUnknown(List<?>... groups)` can use this array parameter type without running into the problem of creating an array with non-reifiable component type `List<String>`.

However, `List<?>` does not guarantee that each list's elements are `String`, `Number`, or any specific type. "Reifiable" here only means the runtime can check that the object is a `List` without **checking a concrete generic type argument**.

Similarly:
- `Map<?, ?>...` has unbounded wildcard type arguments.
- `List<String>...` has the concrete type argument `String`, which is non-reifiable.
- `List<? extends Number>...` has a bounded wildcard, so it is not in the unbounded-wildcard case.

Do not equate "has `<...>`" with "must emit a warning." You need to check **whether the generic parameter type is reifiable**.

## 13. Varargs of List<String> vs. List<List<String>>

For the same goal of "accepting multiple string lists," two APIs have different shapes:

~~~java
static void processVarargs(List<String>... groups) {
    for (List<String> group : groups) {
        System.out.println(group.size());
    }
}

static void processList(List<List<String>> groups) {
    for (List<String> group : groups) {
        System.out.println(group.size());
    }
}
~~~

`processVarargs` is convenient when callers have a few separate `List` instances:

~~~java
processVarargs(List.of("A"), List.of("B"));
~~~

However, the compiler must construct or accept a `List<String>[]` array under varargs rules; with a non-reifiable component, this can introduce unchecked warnings and aliasing/heap-pollution risks if the method handles it unsafely.

`processList` accepts a **`List` of `List<String>`**:

~~~java
processList(List.of(List.of("A"), List.of("B")));
~~~

There is no forced `List<String>[]` creation step. The compiler still checks generic types properly across the API. When varargs syntax is unnecessary, nested collections often help APIs avoid generic arrays and the associated warnings.

Do not assume `List<List<String>>` makes data completely immune to unchecked casts or raw types. Still, it **does not require a varargs array with a non-reifiable component** in normal call paths.

## 14. Why Returning T[] Directly from a Varargs Method Can Be Dangerous

Consider:

~~~java
@SafeVarargs // Placing this here is not a valid safety guarantee.
static <T> T[] expose(T... values) {
    return values; // Exposes the backing array to the caller.
}
~~~

If the caller passes an existing array, returning it can expose that same reference. If the caller passes arguments with non-reifiable generic types, the backing array can be an array with a raw runtime component that differs from what code expects regarding immutability or generic arguments.

A method that merely runs `return values` will not necessarily fail in every situation; the risk depends on the call path and what the caller subsequently does with the array. Still, **returning an alias to the varargs array directly** is a design that is hard to prove generally safe, especially if others can later mutate it via array covariance or a raw reference.

If a collection result is needed, copy it:

~~~java
@SafeVarargs
static <T> List<T> toListCopy(T... values) {
    return List.copyOf(Arrays.asList(values));
}
~~~

This snippet preserves the element generic type in the API signature and does not return the backing array. `List.copyOf` rejects `null` elements and performs a shallow copy: the `T` objects inside remain the same instances if they are mutable.

If a new array is required, you must consider the concrete **runtime component type**; you cannot assume casting `new Object[values.length]` to `T[]` will work when a caller expects `String[]`.

## 15. When Does null Interact with Varargs?

Varargs syntax has an edge case involving **`null`**:

~~~java
static void show(String... values) {
    System.out.println(values == null ? "null array" : values.length);
}
~~~

A call `show()` passes an empty array as a variable-arity call; however, `show((String[]) null)` intentionally passes **`null` as the array parameter itself**, not an array containing one `null` element.

~~~java
show();                  // Prints 0.
show((String[]) null);   // Prints "null array".
show((String) null);     // One null element: prints 1.
~~~

An uncast call `show(null)` can trigger an ambiguous varargs/array-parameter warning depending on the method and overloads. To avoid confusion, distinguish clearly between a **null array** and an **array containing a null element**.

In `safeCopy`, if a caller passes `(String[]) null`, the call can pass a `null` array into the body; `Arrays.asList(values)` does not behave like a normal array in that case, so the API should define null handling explicitly or use `Objects.requireNonNull(values)` before processing.

This is not directly a type-erasure issue, but a consequence of the fact that **a varargs parameter is really an array**.

## 16. How to Read Compiler Warnings

With `javac --release 17 -Xlint:unchecked`, an unsafe generic varargs method can produce two categories of warnings:

**Warning at the declaration**:

~~~text
Possible heap pollution from parameterized vararg type List<String>
~~~

It states that the method uses varargs with a non-reifiable generic component, which may cause heap pollution. It does not mean the compiler proved data is actually corrupted at every call.

**Warning at the call site**:

~~~text
unchecked generic array creation for varargs parameter of type List<String>[]
~~~

It states that preparing the array to execute the variable-arity call cannot guarantee full generic safety.

Methods marked safe with `@SafeVarargs` may suppress these warnings, yet that rests on the **author's contract**, not because the JVM checks generic arguments automatically.

Warnings are not application stdout. When writing documentation or tests, separate compilation diagnostics from runtime output.

## 17. Checklist for Designing Safe Generic Varargs

When writing `<T> f(T... values)` or `f(List<String>... groups)`, check:

1. **Is varargs truly necessary?** If callers usually already have a collection, accepting `List<T>` or `Collection<T>` can be clearer and safer.
2. **Is the array element type reifiable?** `String` and `List<?>` differ from `List<String>`.
3. **Does the body assign through `Object[]` or a raw alias?** That is a sign of heap pollution.
4. **Does the body store or directly return the array?** Doing so can leak an alias and make element types hard to control.
5. **Is the array passed to code that could mutate it?** Safety must be checked **transitively**, not just across a few lines in the current method.
6. **Does it copy or just hold a reference?** `Arrays.asList(values)` is a fixed-size `List` view backed by the array, whereas `List.copyOf` creates an unmodifiable `List` without continuing to expose the array directly.
7. **Are null arrays or null elements possible?** Define an explicit contract.
8. **Is `@SafeVarargs` used?** Only apply it after proving safety. The annotation does not turn a non-reifiable type into a reifiable one.
9. **Have you tested with compiler warnings enabled?** Turn on `-Xlint:unchecked` and inspect generic varargs call sites carefully.
10. **Are there aliases and multiple untrusted callers?** If so, prefer designs that prevent uncontrolled writes to the backing array.

If example code needs intentionally unsafe behavior for teaching purposes, isolate it clearly from production APIs and catch errors at the right boundary so the demo program can continue running.

## 18. Common Misconceptions

### "T... is preserved by Java as an unspecified number of runtime parameters"

Incorrect. A varargs parameter is **a single array parameter**; the compiler turns multi-argument calls into array-passing calls as needed.

### "T... always becomes Object[] at runtime"

Incorrect. The erased method descriptor may use `Object[]` or an array of the bound, while the runtime array passed in can be `String[]` or `List[]` depending on how the caller constructs it.

### "If new List<String>[n] is forbidden, then List<String>... must also be forbidden"

Incorrect. Java permits **declaring a non-reifiable varargs parameter** and uses generic array creation at call sites with warnings when needed.

### "@SafeVarargs validates every element in List<String>"

Incorrect. The annotation performs no runtime validation; it only relates to the safety contract for how the method handles the varargs array and to compiler warnings.

### "ArrayStoreException will stop any List<Integer> from entering List<String>[]"

Incorrect. After erasure, the array's runtime component may simply be `List`; a `List<Integer>` is still a `List`. Wrong generic arguments typically surface when reading an element as `String`, throwing `ClassCastException`.

### "Returning Arrays.asList(values) definitely does not expose the array"

Incorrect. `Arrays.asList` returns a fixed-size list **backed by the input array**. Modifying the list via `set` or modifying the array affects the other. If the goal is to avoid aliasing, use a proper copy like `List.copyOf`, while still considering mutable elements.

### "A method with @SafeVarargs is guaranteed to be safe"

Incorrect. The compiler cannot exhaustively prove how every body and every called helper handles data. If the annotation author breaks the contract, heap pollution risk remains.

## 19. Self-Check Questions

**1.** In `static <T> void f(T... xs)`, what is the type of `xs` inside the method body?

**Answer:** `T[]` in Java source. After erasure, the descriptor uses an array of `erasure(T)`, defaulting to `Object[]` if `T` has no explicit bound.

**2.** What does the compiler need to create when a caller writes `f("A", "B")`?

**Answer:** Under variable-arity invocation, the compiler packs the two `String` values into a suitable array and passes it as the varargs parameter. At runtime, the method receives a single array.

**3.** Why can `f(List.of("A"), List.of("B"))` create a runtime array with component type `List` instead of `List<String>`?

**Answer:** `List<String>` is non-reifiable due to erasure. The runtime component can only represent raw `List`; an unchecked generic array creation warning may be emitted.

**4.** Why can `Object[] alias = groups; alias[0] = List.of(123);` succeed inside a method receiving `List<String>...`?

**Answer:** The backing array has runtime component `List`, so `List<Integer>` still matches the required runtime class for assignment. The array store check does not verify `String` in the generic argument.

**5.** What error can occur when executing `String s = groups[0].get(0)` after the array has been polluted?

**Answer:** `ClassCastException` when the runtime discovers that the `Integer` element cannot be used as a `String`.

**6.** Does `@SafeVarargs` make `new List<String>[2]` valid?

**Answer:** No. The annotation does not alter the array creation rules for non-reifiable component types.

**7.** Does passing a `String[]` into `f(T... values)` create an automatic copy?

**Answer:** Not necessarily. If the call resolves as fixed-arity with a compatible array, the method can receive the exact array created by the caller.

**8.** For the problem of "accepting multiple lists of strings" without needing varargs syntax, which structure usually avoids generic array risks?

**Answer:** `List<List<String>>`, because it does not require building a `List<String>[]` at the call site.

**9.** Are `List<?>...` and `List<String>...` the same in terms of reifiability?

**Answer:** No. `List<?>` contains only an unbounded wildcard and is therefore reifiable; `List<String>` has a concrete type argument and is non-reifiable.

**10.** Why is `List.copyOf(Arrays.asList(values))` often worth considering instead of returning `values` directly?

**Answer:** It produces a `List` that disallows modification through standard APIs and stops exposing the backing varargs array. However, the copy is shallow, rejects `null`, and does not replace validating data inside mutable objects.

## 20. Key Takeaways

**`T...` is varargs syntax for a `T[]` parameter.** At runtime, the JVM receives an array; with generic type variables, the method signature undergoes type erasure, while call sites can construct an array with either a concrete runtime component or a raw component when type arguments are non-reifiable.

The hazard stands out clearly with `List<String>...`: the runtime backing array can be `List[]`, letting an `Object[]` alias insert a `List<Integer>` and violate the `List<String>[]` guarantee. Unchecked warnings reflect that risk.

When designing APIs:
- Do not modify or expose the varargs backing array when doing so could break type invariants.
- Apply `@SafeVarargs` only after proving that the body and related call paths are safe.
- Prefer copying or accepting `List<T>`/`List<List<T>>` when varargs is unnecessary.
- Inspect compiler warnings and know clearly where array store checks happen versus where casts happen when reading generic values.

Understanding the chain **varargs → array → erasure → unchecked warnings → heap pollution** helps you use generic varargs properly and avoid bugs that surface only late at runtime.
