# Overloading: primitive promotion, boxing, and combination limits in Java

When a class has multiple methods with the same name but different parameter lists (**overloads**), Java selects which signature to call **at compile time** based on the static types of the arguments. This choice depends on which conversions are permitted at each stage of overload resolution. Three key concepts are **widening primitive conversion**, **boxing/unboxing**, and the limits on combining them.

After this lesson, you will be able to predict why `m(7)` selects `m(long)` rather than `m(Integer)`; why `int` does not automatically become `Long`; and when the compiler prefers a fixed-arity overload over varargs.

## 1. Understanding the three conversion groups

### Widening primitive conversion

Widening primitive conversion expands a primitive type to one with a different representation range: `byte → short → int → long → float → double`; `char → int → long → float → double`; `short → int → long → float → double`. There is no automatic numeric conversion from `boolean`; `char` does not widen to `short`.

~~~java
static void write(long value) { }

byte number = 7;
write(number); // byte -> long: valid
write(7);      // int -> long: valid
~~~

Widening primitive conversion usually does not lose value range, though it **can lose precision** when large integers are converted to `float` or `double`. This is not narrowing primitive conversion: `long → int` requires an explicit cast.

### Boxing and unboxing

Boxing converts a primitive value into its corresponding wrapper, such as `int → Integer`, `long → Long`, `byte → Byte`. Unboxing converts the reverse, such as `Integer → int`. Wrappers are objects and can be `null`; if `null` is unboxed, Java throws `NullPointerException` at runtime.

~~~java
static void takeInteger(Integer value) { }

takeInteger(7);         // boxing int -> Integer
Integer boxed = 7;     // boxing in assignment
int plain = boxed;     // unboxing Integer -> int
~~~

`Integer` and `Long` are two separate wrapper classes with no inheritance relationship between them; passing one wrapper for another wrapper parameter is not a widening reference conversion.

### Widening reference conversion

`Integer → Number → Object` are widening reference conversions. They require no unboxing.

~~~java
static void takeNumber(Number value) { }

Integer x = 7;
takeNumber(x); // Integer -> Number: widening reference
~~~

If a primitive `int` is passed to an `Object` parameter, Java can **box `int → Integer` and then apply widening reference conversion `Integer → Object`**.

## 2. Java resolves overloads in three phases

According to Java Language Specification `15.12.2`, the compiler searches for applicable methods in the following order:

| Phase | When applied | Conversions |
| --- | --- | --- |
| 1 — strict invocation | Fixed number of arguments; no boxing/unboxing and no varargs expansion | Exact match, widening primitive, widening reference |
| 2 — loose invocation | If phase 1 has no candidates; still fixed number of arguments | Adds boxing/unboxing and valid conversion chains |
| 3 — variable arity | If the previous two phases have no candidates | Invokes varargs with individual element arguments |

**Once candidates are found in a phase, the search stops at that phase without checking later phases.** Within the phase under consideration, if multiple overloads are applicable, Java selects the **most specific** method. If no single most specific choice can be determined, an `ambiguous method call` error occurs; if no overload applies, a compile error occurs.

This explains the rule of thumb "widening before boxing, boxing before varargs" in simple examples. However, "winning" here refers to the **applicability phase**; it does not replace the most-specific selection rule when multiple signatures compete in the same phase.

A method declared `void f(int... values)` actually has an `int[]` array parameter. When an `int[]` is passed to the method, it is treated as a fixed-arity call right in phase 1; only when individual elements are passed for Java to pack into an array is phase 3 needed.

## 3. Why does `int` prefer `long` over `Integer`?

~~~java
static String choose(long value) {
    return "long";
}
static String choose(Integer value) {
    return "Integer";
}
~~~

- `choose(7)`: literal `7` has type `int`. `int → long` is a widening primitive conversion, so the `long` overload is applicable in phase 1. `int → Integer` is boxing, which is only considered in phase 2. `long` is chosen.
- `byte b = 7; choose(b)`: `byte → long` is a widening primitive conversion in phase 1. There is no direct `byte → Integer` boxing. `long` is chosen.
- `choose(Integer.valueOf(7))`: the argument has type `Integer`. The `Integer` overload is an exact match in phase 1, whereas `long` requires unboxing `Integer → int` and then widening `int → long` in phase 2. `Integer` is chosen.

The key point to remember is the **static type of the argument expression**, not just its numeric value. `7`, `7L`, and `Integer.valueOf(7)` do not have the same type.

## 4. Permitted and disallowed conversion chains

In a method invocation context, `method invocation conversion` rules do not allow arbitrarily chaining any conversions together.

| Argument | Parameter | Result | Reason |
| --- | --- | --- | --- |
| `byte` | `long` | Valid | Widening primitive |
| `int` | `Integer` | Valid | Boxing |
| `int` | `Object` | Valid | Boxing then widening reference: `int → Integer → Object` |
| `Integer` | `long` | Valid | Unboxing then widening primitive: `Integer → int → long` |
| `Integer` | `Number` | Valid | Widening reference |
| `int` | `Long` | **No** | No automatic widening primitive then boxing: `int → long → Long` |
| `byte` | `Integer` | **No** | No automatic widening primitive then boxing: `byte → int → Integer` |
| `Integer` | `Long` | **No** | No automatic unbox, widen, then re-box |
| `long` | `int` | **No** | Narrowing primitive requires a cast |

Two valid combination patterns to remember are **boxing + widening reference** and **unboxing + widening primitive**. In addition, loose invocation rules in the JLS also include widening reference followed by unboxing (potentially followed by widening primitive), though this does not mean an arbitrary `Object` is automatically unboxed as any desired type: the type relationship and wrapper must be valid.

The following example shows a very specific limitation:

~~~java
static void acceptLong(Long number) { }

// acceptLong(7);          // ERROR: int does not automatically become Long
acceptLong(7L);            // long -> Long: valid
acceptLong((long) 7);      // cast produces a long expression, then boxing
acceptLong(Long.valueOf(7L));
~~~

For `acceptLong(7)`, the compiler **does not** automatically perform `int → long → Long`. Choose the `7L` literal or convert the expression to `long` before calling if the API requires `Long`. Similarly, an `Integer` variable does not automatically become `Long`.

**Small integer constants are not automatically narrowed in method calls.** `byte b = 7` is a valid assignment due to constant rules, but `acceptByte(7)` is invalid if the method only accepts `byte`, because the literal `7` still has type `int`. You must call `acceptByte((byte) 7)`.

## 5. Widening reference can be chosen before unboxing

Consider two overloads:

~~~java
static String fromWrapper(Number value) {
    return "Number";
}
static String fromWrapper(long value) {
    return "long";
}
~~~

With `Integer x = 7; fromWrapper(x)`, the `Number` overload applies via widening reference `Integer → Number` in phase 1, whereas the `long` overload requires unboxing followed by widening `Integer → int → long` in phase 2. Therefore Java selects `fromWrapper(Number)`.

If the class **only had** `fromWrapper(long)`, calling it with `Integer` would still be completely valid because `Integer → int → long` is an allowed chain in the loose invocation phase. Selecting `Number` above results from the **phase ordering**, not because every object parameter always outranks primitives.

## 6. Complete Java 17+ example

Save the file as `OverloadConversions.java`:

~~~java
public class OverloadConversions {
    static String choose(long x) {
        return "long";
    }
    static String choose(Integer x) {
        return "Integer";
    }

    static String fromWrapper(Number x) {
        return "Number";
    }
    static String fromWrapper(long x) {
        return "long";
    }

    static String unboxAndWiden(long x) {
        return "long";
    }
    static String receiveObject(Object x) {
        return "Object";
    }

    static String dispatch(int x) {
        return "fixed int";
    }
    static String dispatch(int... xs) {
        return "varargs " + xs.length;
    }

    static String boxed(Integer x) {
        return "Integer";
    }

    public static void main(String[] args) {
        byte b = 7;
        System.out.println("choose(7)=" + choose(7));
        System.out.println("choose(b)=" + choose(b));
        System.out.println("choose(Integer.valueOf(7))="
                + choose(Integer.valueOf(7)));
        System.out.println("fromWrapper(Integer)="
                + fromWrapper(Integer.valueOf(7)));
        System.out.println("unboxAndWiden(Integer)="
                + unboxAndWiden(Integer.valueOf(7)));
        System.out.println("receiveObject(7)="
                + receiveObject(7));
        System.out.println("dispatch(7)=" + dispatch(7));
        System.out.println("dispatch(7, 8)=" + dispatch(7, 8));
        System.out.println("boxed(7)=" + boxed(7));
    }
}
~~~

Compile and run with Java 17 or higher:

~~~bash
javac OverloadConversions.java
java OverloadConversions
~~~

Stdout:

~~~text
choose(7)=long
choose(b)=long
choose(Integer.valueOf(7))=Integer
fromWrapper(Integer)=Number
unboxAndWiden(Integer)=long
receiveObject(7)=Object
dispatch(7)=fixed int
dispatch(7, 8)=varargs 2
boxed(7)=Integer
~~~

In the nine lines above, `choose(7)` illustrates widening primitive being considered before boxing; `fromWrapper(Integer)` illustrates widening reference before unboxing; `unboxAndWiden(Integer)` and `receiveObject(7)` illustrate two valid chains; `dispatch(7)` prefers the fixed overload while `dispatch(7, 8)` requires varargs; and `boxed(7)` demonstrates valid boxing when phase 1 has no matching method. These outputs are reproducible with the code above.

## 7. Two intentional compile-error examples

The snippets below are **error-demonstration code**, not to be placed directly into the standalone runnable program in section 6.

### No widening-then-boxing chain

~~~java
static void accept(Long value) { }

accept(7); // ERROR: int does not automatically convert to Long
~~~

Fix by writing `accept(7L)` or `accept(Long.valueOf(7L))` if the method definition truly requires a `Long` wrapper. Do not add overloads merely to "appease" the compiler when API semantics are unclear.

### Two different wrappers cause ambiguity with `null`

~~~java
static void process(Integer value) { }
static void process(Long value) { }

process(null); // ERROR: ambiguous method call
~~~

Both overloads accept a `null` reference, yet `Integer` and `Long` are not subtypes of one another, so no unique most specific overload can be selected. You can clarify intent with `process((Integer) null)` or `process((Long) null)`. This snippet assumes the methods are in the same class and called from an accessible scope.

## 8. Reasoning errors and API design notes

1. **Confusing a literal's type with its value range.** `7` is `int`; `7L` is `long`; being able to assign `7` to `byte` does not prove calling `f(byte)` via `f(7)` is valid.
2. **Confusing a wrapper with a primitive of the same numeric meaning.** `Integer` is a reference, not an alias for `int`. The compiler only unboxes in permitted contexts. Unboxing a `null` wrapper throws `NullPointerException`.
3. **Expecting overload selection by runtime object type.** If `Number n = Integer.valueOf(7)`, overload resolution sees `Number`. Runtime polymorphism picks the implementation of the **already chosen signature**, rather than switching to an `Integer` overload just because the actual object is an `Integer`.
4. **Assuming varargs always wins or always ranks last in every situation.** Distinguish a varargs declaration used with an array argument in phase 1 from expanding individual arguments in phase 3. Two declarations `f(int[])` and `f(int...)` cannot coexist as distinct overloads because they have the same method signature.
5. **Assuming the return type determines overload resolution.** You cannot simultaneously declare `int f(int)` and `long f(int)` differing only in return type. Writing `long result = f(7)` does not make the compiler "look for a signature returning long" as a simple overload selection criterion.
6. **Selecting by step count.** The actual rule is phase ordering followed by finding the most specific method in the first matching phase. A valid two-step chain can be used if no overload exists in an earlier phase.
7. **Using casts to mask API mismatches.** Casting `(long) 7` creates a `long` expression; casting `(Integer) 7` creates an `Integer` expression. Casts can help deliberately pick an overload, but alter semantics if applied carelessly.
8. **Overgeneralizing conclusions to all generics/lambdas.** Generic method inference, lambdas, and method references have additional specific overload selection rules. Use the three phases as a foundation, then check relevant JLS rules and test with the compiler on concrete examples.

## 9. Checklist for inspecting an overloaded call

1. Note the exact **static type** of each argument (`7`, `7L`, wrapper, reference variable, `null`).
2. List accessible overloads with the same name and compatible parameter count.
3. Look for **phase 1** candidates using only exact match/widening, without boxing/unboxing.
4. If phase 1 is empty, examine **phase 2** with boxing/unboxing and valid chains; never insert primitive widening followed by boxing.
5. Only if phase 2 is empty, examine **phase 3** for variable arity.
6. In the first phase with candidates, choose the **most specific** method; if multiple candidates yield no unique winner, it is a compile error. Only afterward consider runtime values and `null` unboxing.

**Practice:** Given `m(long)` and `m(Integer)`. What does `m(1)` select? What does `m(Integer.valueOf(1))` select? Can a method with only the signature `use(Long)` be called with `use(1)`?

**Answer:** `m(1)` selects `m(long)` (phase 1); `m(Integer.valueOf(1))` selects `m(Integer)` (phase 1, exact match); `use(1)` does not compile because `int → long → Long` is not a valid implicit conversion chain in a method invocation.

## Official references

- [Java Language Specification §5.3 — Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.3): conversion kinds and permitted chains.
- [Java Language Specification §15.12.2 — Determine Method Signature](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2): three-phase ordering and most specific method selection.