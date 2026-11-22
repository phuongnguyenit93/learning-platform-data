# Evaluation Order of Type Conversion, Boxing, and Varargs in Java Method Overloading

## Learning Objectives

After this lesson, you can:

- Explain why a call like `f(5)` may match multiple overloads, yet the compiler must choose according to **deterministic rules**, rather than an intuition of “which type is closest”.
- Correctly state the **three phases** of method applicability checking according to the Java Language Specification (JLS): **strict invocation** (no boxing/unboxing), **loose invocation** (allowing boxing/unboxing), and **variable arity invocation** (varargs).
- Distinguish between **primitive widening**, **reference widening**, **boxing**, **unboxing**, **unboxing followed by primitive widening**, and conversion chains that are not used implicitly in a call.
- Explain why a **fixed-arity overload can be chosen before varargs** even when it requires boxing, and why a method declared with `...` is sometimes evaluated **right in the fixed-arity phase**.
- Accurately predict the selected overload or an **ambiguous method call** error, including when passing `null`, an array, a wrapper type, or a primitive value.
- Read `no suitable method found` and `reference ... is ambiguous` error messages, and fix the call or design clearer overloads.

## 1. Why Is an Overload Evaluation Order Needed?

Given two declarations:

~~~java
static String choose(long value) {
    return "long";
}

static String choose(Integer value) {
    return "Integer";
}
~~~

Within the same class, both share the name `choose` but have different parameter types, so **method overloading** is valid.

The call `choose(5)` has an `int` literal argument. Java can:

- Convert `int` to `long` via **primitive widening**.
- Convert `int` to `Integer` via **boxing**.

So which overload is chosen? **`choose(long)`**. The reason is not that the `long` type is intuitively “more like an integer”; the reason is that Java searches for applicable methods across **multiple phases**, and primitive widening is evaluated in an earlier phase than boxing.

The core principle is:

> Once Java finds at least one applicable method in a phase, it **does not move on to a later phase** just to look for a seemingly more attractive overload.

Within the selected phase, the compiler then determines the **most specific** method. These two layers of rules must be distinguished: **selecting the applicable phase** first, and **selecting the most specific method within that phase** second.

Note: **declaring multiple overloads** and **selecting an overload at a call site** are two different problems. The examples in this lesson focus on overload resolution at **compile time**. Once an instance method is selected, determining the overriding implementation at runtime is a separate step.

## 2. The Three Phases of Overload Resolution

In the JLS, when evaluating a call with a method name and an argument list, the compiler identifies the potential accessible methods, and then checks applicability in order:

| Phase | Name in JLS | What Is Primarily Allowed? | Typical Examples |
| --- | --- | --- | --- |
| **1** | Strict invocation applicability | Fixed arity; identity, primitive widening, reference widening, and corresponding rules for generic inference; **no boxing/unboxing required** | `int` → `long`; `String` → `Object` |
| **2** | Loose invocation applicability | Fixed arity; adds **boxing/unboxing** and specified conversion chains, such as boxing followed by reference widening, or unboxing followed by primitive widening | `int` → `Integer`; `int` → `Object`; `Integer` → `long` |
| **3** | Variable arity applicability | If neither of the previous two phases has an applicable method, evaluates a **varargs** invocation with a variable number of arguments; each element must have a compatible type | `sum(1, 2, 3)` for `sum(int...)` |

**The evaluation order is 1 → 2 → 3.** Java does not implicitly “score” all conversions and pick the method with the lowest total score. If phase 1 already has an applicable candidate, phases 2 and 3 will not be used to compete against phase 1.

For each phase:

1. The candidate set also depends on **name, parameter count/order, accessibility, generic type inference**, and the form of the invocation.
2. The compiler selects the **most-specific** method among the applicable methods in that phase.
3. If a unique choice cannot be found according to the rules, the call may be **ambiguous** and cause a compilation error.
4. Only if phase 1 has no applicable candidates is phase 2 checked; and only if phase 2 also has none is phase 3 checked.

The fact that “an earlier phase beats a later phase” **does not mean** the parameter types of all candidates in an earlier phase are always narrower or closer to the value than candidates in a later phase. It is a priority policy to preserve compatibility for Java calls that existed before boxing and varargs were introduced.

### 2.1. Mental Model Diagram

~~~text
Method call: f(arg1, arg2, ...)
            |
            v
Applicable method with FIXED ARITY,
without boxing/unboxing?  -- Yes --> Select most-specific in phase 1
            |
           No
            v
Applicable method with FIXED ARITY,
allowing boxing/unboxing? -- Yes --> Select most-specific in phase 2
            |
           No
            v
Applicable VARARGS method
with variable arity?      -- Yes --> Select most-specific in phase 3
            |
           No
            v
        Error: no applicable method
~~~

This is a simplified study diagram. The JLS also includes constraints on generic inference, the compatibility of lambda expressions/method references, and rules for choosing the most specific method. Do not use this diagram as a substitute for the full specification when encountering complex generic overloads.

## 3. Phase 1: Fixed Arity and Strict Invocation

In **phase 1**, the compiler looks for methods with a **fixed number of parameters matching the number of arguments** and allows strict conversions, primarily:

- **Identity conversion**: `int` → `int`; `String` → `String`.
- **Primitive widening**: `byte` → `short`/`int`/`long`...; `int` → `long`/`float`/`double`; `float` → `double`.
- **Reference widening**: `String` → `Object`, `ArrayList<String>` → corresponding valid supertypes.
- Accompanying inference/checking rules for generic methods based on context.

**Boxing (`int` → `Integer`) and unboxing (`Integer` → `int`) do not make a method a candidate in phase 1.**

Example:

~~~java
static String calc(long x) { return "long"; }
static String calc(double x) { return "double"; }
~~~

`calc(10)` with an `int` literal has two candidates in phase 1: `calc(long)` and `calc(double)`. Java selects **`calc(long)`**: here `long` can widen to `double`, so the `long` overload is considered more specific in this comparison.

If `calc(int)` is added:

~~~java
static String calc(int x) { return "int"; }
~~~

then `calc(10)` selects `calc(int)` according to the most-specific principle in phase 1; not because the compiler only looks at the first overload in the file. **The declaration order of methods in the source does not determine which overload is selected.**

### 3.1. What Is Primitive Widening?

Table of common primitive widening conversions to remember:

| From Type | Can Widen To |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |

`boolean` cannot be converted to numeric types. There is no primitive widening from `char` to `short`, from `short` to `char`, from `double` to `float`, or from `int` to `byte`.

**Widening is not a guarantee against precision loss**: some large integers converted to a floating-point type such as `float` may be rounded. Overload rules still use the validity of the conversion under the language rules, rather than whether the current value preserves exact precision.

### 3.2. Reference Widening Without Boxing

Example:

~~~java
static String display(Object x) { return "Object"; }
static String display(CharSequence x) { return "CharSequence"; }
~~~

`display("Java")` has an argument type of `String`; `String` is a subtype of both `Object` and `CharSequence`. Both overloads are applicable in phase 1, but `CharSequence` is more specific than `Object`, so the result is `"CharSequence"`.

If the argument is a variable declared as `Object value = "Java";`, the call `display(value)` instead selects `display(Object)` because the overload is decided by the **static type `Object`**, not by the object's `String` class at runtime.

## 4. Phase 2: Fixed Arity with Boxing and Unboxing

When **no method is applicable in phase 1**, the compiler moves to phase 2. Common conversions include:

- **Boxing**: `int` → `Integer`, `long` → `Long`, `boolean` → `Boolean`…
- **Unboxing**: `Integer` → `int`, `Long` → `long`…
- **Boxing followed by reference widening**: `int` → `Integer` → `Number` or `Object`.
- **Unboxing followed by primitive widening**: `Integer` → `int` → `long`/`double`, when the target permits.

Phase 2 still applies **fixed arity**: a method requiring three parameters does not automatically accept one or four arguments just because boxing is available.

### 4.1. Widening Is Evaluated Before Boxing

Suppose:

~~~java
static String choose(long value) { return "long"; }
static String choose(Integer value) { return "Integer"; }
~~~

For `choose(5)`:

1. The argument `5` has type `int`.
2. Phase 1: `choose(long)` is applicable via `int` → `long`.
3. `choose(Integer)` requires boxing, so it is not applicable in phase 1.
4. The compiler already has a phase 1 candidate, so **it does not need to evaluate phase 2**.
5. The selected method is `choose(long)`, even though there is an overload taking the `Integer` wrapper.

With `choose(Integer.valueOf(5))`, the argument already has static type `Integer`; the `choose(Integer)` overload is applicable in phase 1 via identity conversion. It beats `choose(long)`, which would require unboxing followed by widening in phase 2.

**There is no rule that “primitive always beats wrapper” in every call.** The decision depends on the type of the argument expression and which phase has candidates.

### 4.2. Boxing and Reference Widening Can Occur Together

Example:

~~~java
static String select(Object x) { return "Object"; }
static String select(Integer x) { return "Integer"; }
~~~

`select(7)` has no phase 1 candidates because `int` is not a reference subtype of `Object` or `Integer`, and both overloads require boxing. In phase 2:

- `select(Object)` is applicable via `int` → `Integer` → `Object`.
- `select(Integer)` is applicable via `int` → `Integer`.

Within the same phase, `Integer` is more specific than `Object`, so **`select(Integer)` is selected**.

Do not generalize that “phase 2 picks the overload using the fewest conversion steps”; it is the **most-specific** relationship that determines the choice in this case.

### 4.3. Unboxing Followed by Primitive Widening

Suppose there is only:

~~~java
static void consume(long value) {
    System.out.println(value);
}
~~~

An expression of type `Integer` such as `Integer boxed = 12;` can be passed to `consume(boxed)` via the chain **`Integer` → `int` → `long`**. This is a permitted conversion in the loose invocation phase.

If the `boxed` variable is `null`, unboxing throws a `NullPointerException` at runtime. **The fact that the compiler accepts the type does not mean the runtime value is always safe.**

### 4.4. Not Every Arbitrary Conversion Chain Exists

The easiest mistake to make is assuming:

> “`int` can become `long`, and `long` can be boxed to `Long`, so an `int` argument can automatically be passed to a `Long` parameter.”

This reasoning is **wrong** for normal method calls. Method invocation conversion **does not allow primitive widening followed by boxing** into a different wrapper via that chain.

~~~java
static void receive(Long value) {
    System.out.println(value);
}

// Placed inside a method:
// receive(7);  // Wrong: int does not automatically convert to Long
// receive(7L); // Correct: a long literal can be boxed to Long
~~~

If the original value is `int n = 7;`, you can write `receive((long) n)` so the compiler performs boxing after an explicit cast expression; or `receive(Long.valueOf(n))` for an intentional conversion.

Similarly, **primitive narrowing followed by boxing** does not happen automatically: a `byte` method parameter does not directly accept an `int` literal just because the value is within the byte range.

~~~java
static void tiny(byte value) {
    System.out.println(value);
}

// Inside a method:
// tiny(10);         // Invalid: int -> byte is narrowing
// tiny((byte) 10);  // Valid because there is an explicit cast
~~~

**Distinguish from variable assignment:** `byte small = 10;` is an assignment of an `int` constant with its own assignment conversion rules; that does not make `tiny(10)` automatically valid.

## 5. Phase 3: Variable Arity Invocation (Varargs)

A varargs method has its **last parameter** in the form `T... values`. Inside the method body, this parameter is an **array `T[]`**; when the call uses variable arity, Java can accept 0 or more individual values for the trailing part.

~~~java
static String join(String separator, String... items) {
    return String.join(separator, items);
}
~~~

Calls that match in argument count/type:

~~~java
join(",");                         // The items part has 0 values
join(",", "A");                    // 1 value
join(",", "A", "B");               // 2 values
join(",", new String[] {"A","B"}); // A single String[] array argument
~~~

**Key point:** phase 3 is only attempted **if there is no applicable method in either phase 1 or phase 2**. A fixed-arity overload can beat a variable-arity call even when that fixed-arity overload has to use boxing.

### 5.1. Boxing Can Take Precedence Over Varargs

Consider these declarations:

~~~java
static String route(Object value) { return "Object"; }
static String route(int... values) { return "varargs"; }
~~~

The call `route(5)` with an `int` argument:

- `route(Object)` **is not applicable in phase 1**, but is applicable in **phase 2** through `int` → `Integer` boxing and reference widening → `Object`.
- `route(int...)` does not accept a single `int` as **an `int[]`** in the fixed-arity phase; it only applies when phase 3 evaluates the varargs elements.
- Since phase 2 already has a candidate, the compiler selects **`route(Object)`**.

Conversely, `route(5, 6)` has two arguments, so the single-parameter `route(Object)` overload is not applicable. Phase 3 evaluates `route(int...)` with two `int` elements, so the varargs overload is selected.

**Do not interpret “varargs is evaluated last” as “every method with `...` is only evaluated in phase 3”.** A varargs method can also be invoked in fixed-arity form when passing exactly one compatible array.

### 5.2. Varargs Is Also Evaluated as an Array in Phase 1 or 2

`void route(int... values)` has an actual formal parameter of type `int[]`. For the call `route(new int[] {1, 2})`:

- There is **one** `int[]` argument.
- The method `route(int...)` is evaluated **as a method taking `int[]` with fixed arity**; it already matches in phase 1.
- If an overload `route(Object)` also exists, both are applicable in phase 1 (an `int[]` array is a reference type subtype of `Object`).
- `int[]` is more specific than `Object`, so the `route(int...)` overload is selected.

In cases where a fixed-arity call is possible, the compiler does not need to create an additional array containing the array as a single element; the array is passed directly as one argument.

The `...` syntax can only be used on the **last parameter**, and a method can declare at most one varargs parameter. `sum(int... values, int mode)` is invalid syntax. Nor can `sum(int... values)` and `sum(int[] values)` be declared simultaneously in the same class to create two overloads, because they have corresponding signatures of the form `sum(int[])`.

## 6. Complete Example: Verifying the Three Phases via stdout

Save to **`OverloadPhasesDemo.java`**:

~~~java
public class OverloadPhasesDemo {
    static String choose(long value) {
        return "long";
    }

    static String choose(Integer value) {
        return "Integer";
    }

    static String pick(Object value) {
        return "Object";
    }

    static String pick(Integer value) {
        return "Integer";
    }

    static String route(Object value) {
        return "Object";
    }

    static String route(int... values) {
        return "varargs:" + values.length;
    }

    static String prefer(long value) {
        return "long";
    }

    static String prefer(int... values) {
        return "varargs:" + values.length;
    }

    static String numeric(long value) {
        return "long";
    }

    static String numeric(float value) {
        return "float";
    }

    public static void main(String[] args) {
        System.out.println("choose(5)=" + choose(5));
        System.out.println("choose(Integer)=" + choose(Integer.valueOf(5)));
        System.out.println("pick(5)=" + pick(5));
        System.out.println("route(5)=" + route(5));
        System.out.println("route(5,6)=" + route(5, 6));
        System.out.println("route(array)=" + route(new int[] {5, 6}));
        System.out.println("prefer(5)=" + prefer(5));
        System.out.println("prefer()=" + prefer());
        System.out.println("numeric(5)=" + numeric(5));
    }
}
~~~

Run with Java 17+ in the directory containing the file:

~~~bash
javac OverloadPhasesDemo.java
java OverloadPhasesDemo
~~~

Result:

~~~text
choose(5)=long
choose(Integer)=Integer
pick(5)=Integer
route(5)=Object
route(5,6)=varargs:2
route(array)=varargs:2
prefer(5)=long
prefer()=varargs:0
numeric(5)=long
~~~

Line-by-line explanation:

| Call | Phase That Produced Selected Candidate | Selected Overload and Reason |
| --- | --- | --- |
| `choose(5)` | 1 | `choose(long)`: `int` widens to `long`; no boxing needed |
| `choose(Integer.valueOf(5))` | 1 | `choose(Integer)`: the argument is already `Integer`; `choose(long)` requires unboxing |
| `pick(5)` | 2 | `pick(Integer)`: both `Integer` and `Object` apply only after boxing; `Integer` is more specific |
| `route(5)` | 2 | `route(Object)`: boxing + reference widening; `int...` requires variable arity in phase 3 |
| `route(5,6)` | 3 | `route(int...)`: two `int` elements; the `Object` overload takes only one argument |
| `route(new int[]{5,6})` | 1 | `route(int...)` as fixed-arity `int[]`, more specific than `Object` |
| `prefer(5)` | 1 | `prefer(long)`: widening, applied before varargs |
| `prefer()` | 3 | `prefer(int...)`: accepts 0 elements, while `prefer(long)` requires one argument |
| `numeric(5)` | 1 | `numeric(long)`: both `long` and `float` can accept `int`, but `long` is more specific |

Here, some overloads **are selected in phase 2** and **phase 3**, even though the same program contains methods with identical names. This shows that the rules must be applied **per individual call**, based on the static types and argument count of that specific call.

### 6.1. Be Careful with Static Type Instead of Runtime Type

With `pick(Object)` and `pick(Integer)`:

~~~java
Object x = Integer.valueOf(5);
System.out.println(pick(x));
~~~

This snippet is placed in `main` of `OverloadPhasesDemo`; the result is:

~~~text
Object
~~~

The compiler uses the **declared type `Object` of variable `x`**, so it selects `pick(Object)`. It does not inspect the runtime object as `Integer` and re-select the overload. If you need to call the overload taking `Integer`, the developer must provide an expression with a compatible static type, for example `Integer x = 5;`.

## 7. Varargs Both Serves as an Array-Accepting Method and Supports a Variable Number of Arguments

Save this separate example as **`VarargsFormsDemo.java`**:

~~~java
public class VarargsFormsDemo {
    static String describe(Object value) {
        return "Object";
    }

    static String describe(String... values) {
        return values == null ? "String...:null"
                : "String...:" + values.length;
    }

    static String label(String name, String... tags) {
        return name + ":" + tags.length;
    }

    public static void main(String[] args) {
        System.out.println(describe("X"));
        System.out.println(describe(new String[] {"A", "B"}));
        System.out.println(describe("A", "B"));
        System.out.println(describe((String[]) null));

        System.out.println(label("no-tags"));
        System.out.println(label("with-tags", "a", "b"));
    }
}
~~~

Compile/run:

~~~bash
javac VarargsFormsDemo.java
java VarargsFormsDemo
~~~

Output:

~~~text
Object
String...:2
String...:2
String...:null
no-tags:0
with-tags:2
~~~

Analysis:

- `describe("X")`: the `describe(Object)` overload is applicable in phase 1 fixed arity via reference widening `String` → `Object`; `describe(String...)` requires variable arity, so it is not yet evaluated.
- `describe(new String[]{"A","B"})`: the expression has type `String[]`; both `describe(Object)` and `describe(String[])` match in phase 1 fixed arity, but `String[]` is more specific than `Object`.
- `describe("A","B")`: two `String` arguments mean only the varargs form of `describe(String...)` applies in phase 3.
- `describe((String[]) null)`: the cast specifies that the argument has type `String[]`, selecting the overload taking `String[]` with fixed arity, though the actual value is `null`. The method body has a null check, so it prints `String...:null`.
- `label("no-tags")`: `name` receives the string, while the `tags` part has 0 elements.
- `label("with-tags","a","b")`: two elements go to `tags`.

If you omit the cast and call `describe(null)` when these declarations are present, you may receive a warning regarding an inexact varargs call and the overload taking `String[]` is selected via fixed-arity applicability; avoid relying on an untyped `null` because it easily causes confusion between “a single null element” and “a null array”. If you truly want **a single null String element**, you can write `describe((String) null)` to explicitly indicate a `String` argument. In that case, in an example that also has `describe(Object)`, the overload selection result will follow the fixed applicability phases explained above.

## 8. Most-Specific: Must Be Evaluated After Determining the Phase

Suppose there are two overloads:

~~~java
static String display(Object item) {
    return "Object";
}

static String display(CharSequence item) {
    return "CharSequence";
}
~~~

The call `display("hello")` puts both overloads into phase 1: `String` widens to `Object` or `CharSequence`. Since `CharSequence` is a subtype of `Object`, `display(CharSequence)` is more specific.

However, with:

~~~java
static String h(long x) { return "long"; }
static String h(Integer x) { return "Integer"; }
~~~

`h(5)` does not put the two overloads into the same phase to compare “most-specific”, because `h(long)` already applies in phase 1 while `h(Integer)` only applies in phase 2. **Phase selection** happens before **specificity comparison**.

### 8.1. Two Overloads Both Apply Without a Most-Specific One

Example:

~~~java
static void accept(String value) { }
static void accept(Integer value) { }
~~~

Both are valid methods and each has one reference parameter. However, the call:

~~~java
// accept(null); // Compilation error: reference to accept is ambiguous
~~~

`null` can convert to both `String` and `Integer`, and these two types have no subtype relationship with each other. The compiler does not pick arbitrarily by declaration order. If the API truly needs to be called with null, the intent must be specified explicitly:

~~~java
accept((String) null);
accept((Integer) null);
~~~

The lines above are an illustrative snippet placed inside a class that has both `accept` overloads. **The cast clarifies the type of the expression** and does not turn `null` into a non-null object; the method body still needs to follow the null-handling contract.

### 8.2. Two Varargs Overloads Can Be Ambiguous

If you have:

~~~java
static void log(int... numbers) { }
static void log(Integer... numbers) { }
~~~

The call `log()` has no arguments for the variable-arity part, so both varargs methods can apply in phase 3. In this case, Java cannot select a most-specific overload and reports an **ambiguous method call**.

Write `log(new int[0])` or `log(new Integer[0])` when you need to clearly choose the corresponding version. The two declarations themselves are a valid example when placed together in a class; **the empty call is what is ambiguous**.

### 8.3. If a Phase Has Candidates but the Result Is Ambiguous

The compiler **does not use phase 2 or phase 3 to rescue** an ambiguous call that arose in an earlier applicable phase. The correct sequence is to take the candidate set of the **first phase that yields applicable methods**, and then resolve the most-specific one there. If a unique method cannot be determined, an error occurs.

An important API design takeaway: adding another overload **does not always make calls clearer**; it can inadvertently make previously valid `null`, lambda, or generic expression calls ambiguous.

## 9. Generic Methods and Type Inference Across Phases

With a generic method:

~~~java
static <T extends Number> String inspect(T value) {
    return "number";
}
~~~

Calling `inspect(5)` can be valid by boxing `int` to `Integer` and inferring `T` accordingly. If the same class also has an `inspect(long)` overload, then `inspect(5)` can select `inspect(long)` in phase 1 before needing the generic version taking a wrapper. Do not assume “generics always take priority” or “generics are always excluded”.

Type parameter inference also involves `extends` bounds, the static type of arguments, target typing in certain expressions, lambdas, and method references. Therefore, complex examples may not be decidable simply by counting boxing steps.

### 9.1. Generic Arguments Do Not Create Independent Overloads If Erasure Collides

The following two declarations cannot coexist in the same class:

~~~java
// Invalid if declared simultaneously:
// void use(java.util.List<String> values) { }
// void use(java.util.List<Integer> values) { }
~~~

The reason is that **type erasure** gives both the same raw parameter form `List` for name clash checking purposes. This differs from checking argument types for a specific call. Do not define two overloads differing only by `List<String>` and `List<Integer>`.

### 9.2. Not Every Implicit Generic Conversion Exists

`List<Integer>` does not automatically convert to `List<Number>`, even though `Integer` is a subtype of `Number`. Java generics are generally **invariant**. If you only need to read numbers, you can consider `List<? extends Number>`; if you need to add `Integer` values, you can consider `List<? super Integer>`. This is a type constraint independent of the evaluation order of boxing and varargs.

## 10. Four Easily Confused Scenarios Involving Boxing

### 10.1. `int` Does Not Automatically Become `Long`

~~~java
static void take(Long number) { }

// take(10);   // Wrong: int does not automatically widen and then box to Long
take(10L);     // Valid: long boxes to Long
~~~

The illustrative lines are placed inside an appropriate class and method. You can also create the object using `Long.valueOf(10)` if needed.

### 10.2. `Integer` Can Unbox and Then Widen to `long`

~~~java
static void takeLong(long number) {
    System.out.println(number);
}

// Inside a method:
Integer value = 5;
takeLong(value);
~~~

The illustrative snippet is valid. The `Integer` argument type is converted via `int` and then widened to `long` under loose invocation; note that `null` can cause an NPE when unboxing.

### 10.3. `int` Can Box and Then Reference-Widen to `Object`

~~~java
static void takeObject(Object object) {
    System.out.println(object);
}

// Inside a method:
takeObject(5);
~~~

The call is valid via `int` → `Integer` → `Object`. If a `takeObject(Integer)` overload also exists at the same time, the most-specific rule must be applied in the corresponding phase; do not rely on step count arbitrarily.

### 10.4. Integer Literals Do Not Automatically Narrow When Passed to Parameters

~~~java
static void takeByte(byte value) {
    System.out.println(value);
}

// takeByte(5);        // Wrong at method call: the literal has type int
takeByte((byte) 5);    // Valid: explicit expression cast
~~~

`byte x = 5;` compiles due to the **integer constant assignment rule**, but that does not change the method invocation conversion rules.

## 11. Avoiding Conflicts When Designing Overloads

The three-phase rule helps explain programs, but when designing an API, do not force readers to compute multiple phases for a simple call.

Practical suggestions:

1. **Prefer overloads with clear meaning**: differing in parameter count or data role; if they only differ by primitive/wrapper, consider whether both are truly needed.
2. **Avoid overloading `String` and `Integer` if callers frequently pass null**: this can cause ambiguity or unpredictable semantics.
3. **Place varargs in the last position** and document the contract for receiving 0, 1, or multiple elements; if callers may pass null, distinguish between a **null array** and an **array containing null elements**.
4. **Do not rely on meaningless casts** to force a different overload if the API can be named more clearly; casts can hide type errors and cause runtime failures.
5. **Keep static types accurately reflecting the data**: a variable declared as `Object` does not help the compiler automatically select a `String` overload based on the runtime object being a `String`.
6. **Test behavior when adding new overloads**, especially for public APIs that already have consumers. An added overload can change which overload is selected when source code is recompiled.
7. **Remember that boxing/unboxing has overhead and null risks**: in high-performance code, avoid unnecessary wrapper creation; in APIs accepting `Integer`, specify clearly whether null is allowed.

### 11.1. An Example Where Adding an Overload Changes the Result

Initially there is only:

~~~java
static String parse(long x) {
    return "long";
}
~~~

The call `parse(5)` selects `parse(long)`. If you later add:

~~~java
static String parse(int x) {
    return "int";
}
~~~

the call `parse(5)` when **recompiled** will select `parse(int)` (identity instead of widening within the same phase 1). The code still compiles, yet the new behavior differs. When designing an API, adding an overload is a change that can affect call sites, so appropriate testing is necessary.

## 12. Per-Call Reasoning Checklist

When encountering a call `service.calculate(args...)` with multiple overloads:

1. **List the accessible overloads with the same name** in the receiver's static type and related types.
2. **Determine the static type of each argument**, without guessing from runtime values. The literal `5` is typically `int`, `5L` is `long`, and `Integer.valueOf(5)` is `Integer`.
3. **Count the actual number of arguments**: an array `new int[]{1,2}` is **one** argument of type `int[]`, distinct from two arguments `1,2`.
4. **Check phase 1 fixed arity**: is there any overload that matches without boxing/unboxing? If so, find the most-specific one in that set.
5. **Only if phase 1 is empty, check phase 2 fixed arity**: boxing, unboxing, and valid conversion chains. If there are candidates, find the most-specific one.
6. **Only if both phases are empty, check phase 3 varargs**: fixed parameters must match; the remaining arguments are evaluated as compatible array elements.
7. **If multiple candidates exist in the same phase**, evaluate most-specific rules, generic inference, and specific constraints. If no unique choice can be selected, the call is ambiguous.
8. **After selecting the overload**, only then consider runtime execution and (if it is an instance method) potential dispatch to an override; `null`, unboxing, and method body behavior can still throw exceptions.

A simple diagram for quick checking:

~~~text
f(5) with f(long) and f(Integer)
  int -> long (phase 1)    => select long
  int -> Integer (phase 2) => do not evaluate further

f(5) with f(Object) and f(int...)
  int -> Integer -> Object (phase 2) => select Object
  int -> element of int... (phase 3) => do not evaluate further

f(new int[]{5}) with f(Object) and f(int...)
  int[] -> Object (phase 1)
  int[] -> int[] (phase 1, fixed-arity form)
  => select f(int...) because int[] is more specific than Object
~~~

## 13. Common Mistakes and How to Fix Them

| Misconception / Error | Correct Explanation |
| --- | --- |
| “Autoboxing takes precedence over widening.” | Wrong. The strict phase with widening is evaluated before the loose phase with boxing. |
| “If a method `f(Integer)` exists, `f(5)` always selects it.” | Only when there is no applicable candidate in an earlier phase and the most-specific rule selects it. |
| “Java tries everything and picks the overload needing the fewest conversions.” | Not the language algorithm. It must evaluate the three phases and most-specific rules. |
| “A varargs method is always evaluated in phase 3.” | Wrong if the argument is already a compatible array: a varargs method can participate in the fixed-arity phase. |
| “Fixed arity always beats varargs by method name.” | You must consider the **applicable phase** of each call and the fixed/variable-arity form of the varargs method. |
| “`int` automatically becomes `Long` via widening followed by boxing.” | The primitive widening followed by boxing chain is not implicitly allowed in normal method invocation. |
| “`Integer` cannot be passed to `long`.” | It can unbox `Integer` → `int`, and then widen → `long` in the loose phase. |
| “`f(byte)` accepts `f(10)` because 10 is small.” | There is no narrowing of an `int` literal in method invocation like there is in constant assignment. |
| “Two overloads `f(String)` and `f(Integer)` will pick one when calling `f(null)`.” | No: for two types with no mutual subtype relationship, the call is ambiguous. |
| “Varargs is always a single individual argument.” | In variable-arity form, multiple values can be packed into an array; in fixed-arity form, an existing array is passed directly. |
| “The compiler selects the overload based on the runtime object.” | Overload selection happens at compile time based on static types; dynamic dispatch selects the override afterward. |
| “Using `List<String>` and `List<Integer>` creates two valid overloads.” | Type erasure causes a name clash; a different name/API design is needed. |
| “`null` unboxes to `0`.” | Unboxing null throws a `NullPointerException` at runtime. |

## 14. Self-Study Exercises

**Question 1.** Given `f(long)` and `f(Integer)`, which method does calling `f(3)` select?  
**Answer:** `f(long)`. The literal `3` has type `int`, and `int` → `long` widening applies in phase 1, so boxing in phase 2 is not evaluated.

**Question 2.** Given `f(Object)` and `f(Integer)`, which method does calling `f(3)` select?  
**Answer:** `f(Integer)`. Both require boxing and apply in phase 2; `Integer` is more specific than `Object`.

**Question 3.** Given `f(Object)` and `f(int...)`, which overload does calling `f(3)` select?  
**Answer:** `f(Object)`, because boxing followed by reference widening makes it applicable in phase 2, ahead of the variable-arity call in phase 3.

**Question 4.** With the same two overloads from Question 3, what happens if you call `f(new int[]{3})`?  
**Answer:** `f(int...)` is selected in phase 1 as a fixed-arity call taking `int[]`; it is more specific than `f(Object)`.

**Question 5.** Given `f(long)` and `f(float)`, what does calling `f(3)` select?  
**Answer:** `f(long)`. Both apply in phase 1, but `long` is more specific than `float` under primitive widening.

**Question 6.** Given only `f(Long)`, does calling `f(3)` compile?  
**Answer:** No. `int` does not automatically widen to `long` and then box to `Long`. Use `3L`, `(long) 3`, or an appropriate `Long` object.

**Question 7.** Given only `f(long)`, is passing a variable `Integer value = 3;` to `f(value)` valid?  
**Answer:** Yes. The loose invocation phase can unbox `Integer` to `int` and then widen to `long`. If `value == null`, runtime can throw an NPE.

**Question 8.** Given `f(String)` and `f(Integer)`, what happens when calling `f(null)`?  
**Answer:** An ambiguous error. You can write `f((String) null)` or `f((Integer) null)` if the API contract genuinely allows null.

**Question 9.** Given `f(int...)` and `f(Integer...)`, why can `f()` be ambiguous?  
**Answer:** Both can accept 0 elements in phase 3, and the array types/element types do not produce a single most-specific candidate in that case.

**Question 10.** Which phase handles `send(new String[]{"A","B"})` for a method `void send(String... parts)`?  
**Answer:** Phase 1, when evaluated as a fixed-arity call with one `String[]` parameter; no new varargs array needs to be created.

**Question 11.** If `Object o = Integer.valueOf(1)` and there are two overloads `g(Object)` and `g(Integer)`, which overload does `g(o)` select?  
**Answer:** `g(Object)`, because the static type of expression `o` is `Object`, not `Integer`.

**Question 12.** A phase 1 overload is valid, yet phase 2 contains an overload returning the type the caller wants. Does Java move to phase 2 to select that return type?  
**Answer:** No. Return type alone does not create another overload for the same signature; and the compiler does not skip a phase 1 candidate to search for a phase 2 overload just because the return type looks more convenient. Generic target typing has its own rules, but it does not reverse the three-phase evaluation order.

## References

- [Java Language Specification §15.12.2 — Compile-Time Step 2: Determine Method Signature](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2), especially §§15.12.2.2–15.12.2.5 on **strict invocation**, **loose invocation**, **variable arity invocation**, and **most-specific**.
- [Java Language Specification §5.3 — Method Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.3) to distinguish conversions permitted in method calls from assignment/casting conversions.
- [Java Language Specification §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.1), especially the section on variable arity parameters.

## Key Takeaways

Java resolves overloads by **phase order**: **(1) fixed arity with strict invocation**, **(2) fixed arity allowing boxing/unboxing**, and **(3) variable arity for varargs**. Only when the preceding phase has no applicable candidates does the compiler check the next phase; within the selected phase, Java uses the **most-specific** rule rather than name length or an imagined count of conversion steps. Therefore, `int` → `long` can beat `int` → `Integer`, boxing to `Object` can beat a varargs call, and a varargs method receiving an existing array can participate right in phase 1. Mastering these principles helps resolve overloads consistently, understand compiler errors, and design easy-to-use APIs.
