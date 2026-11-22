# Distinguishing Method Signatures by Parameter Count, Type, and Order in Java

In Java, **method overloading** allows declaring multiple methods with the **same name** but **different method signatures**. The three most important criteria for distinguishing overloads in practice are **parameter count**, **parameter types**, and **parameter type order**. Parameter names, return types, or `throws` clauses cannot create a new overload on their own.

This lesson helps you read signatures, predict which method is selected at a call site, analyze duplicate declaration and ambiguity errors, and understand limitations caused by arrays, varargs, and generics. Examples run on **Java 17 and later**.

## 1. What Is a Method Signature?

Consider three declarations placed in the same class:

~~~java
void print(int value) { }
void print(String value) { }
void print(int value, String label) { }
~~~

All three methods are named `print`, but their parameter type lists are respectively:

~~~text
print(int)
print(String)
print(int, String)
~~~

They can coexist because their signatures are different.

According to the Java Language Specification (JLS), a method's signature includes its **name**, **type parameters if any**, and the **list of types of its formal parameters** according to type parameter adaptation rules. For ordinary non-generic methods, a quick and accurate way to read it is:

~~~text
signature ≈ method name + number and order of parameter types
~~~

The `≈` symbol serves as a reminder that generic syntax and *subsignature* rules have additional details; the JLS rules should not be oversimplified into a raw string comparison.

**Components that are not used to differentiate signatures** include: the return type, parameter variable names, mere generic type parameter names, access level, `static`, `final`, `synchronized`, and `throws`. Some components still affect call access or overriding, but they do not turn two methods with identical signatures into two valid overloads.

| Declaration | Readable Signature | Can Differ from `process(int)`? |
| --- | --- | --- |
| `void process(int x)` | `process(int)` | The baseline signature itself |
| `void process(int x, int y)` | `process(int, int)` | Yes: different count |
| `void process(long x)` | `process(long)` | Yes: different type |
| `void process(String x)` | `process(String)` | Yes: different type |
| `int process(int number)` | `process(int)` | No: only changed return type/parameter name |
| `static void process(int x)` | `process(int)` | No: only added `static` |

The rows in the table are **declarations for comparison**, not complete code that can all be placed together in a single class.

## 2. Different Parameter Counts

The simplest approach is to use the same name with a different **number of formal parameters**:

~~~java
class Formatter {
    String format() {
        return "(empty)";
    }

    String format(String text) {
        return text;
    }

    String format(String text, int count) {
        return text.repeat(count);
    }
}
~~~

The three signatures are `format()`, `format(String)`, and `format(String, int)`. They are valid because they have 0, 1, and 2 parameters, respectively. In Java 17, `String.repeat(int)` repeats the string according to `count`, throwing `IllegalArgumentException` when `count` is negative.

You can call `formatter.format()`, `formatter.format("A")`, or `formatter.format("A", 3)` on a `Formatter` object. The compiler examines the **number** and **types of arguments** to find the matching method.

**It is not necessary** for every method with the same name to perform an operation with a completely different meaning. Overloading often provides convenient ways to supply inputs to carry out the same meaning, such as `format()` using a default value and `format(String, int)` allowing additional parameters to be specified.

The `Formatter` snippet is **an illustrative class**, without `main`.

## 3. Same Parameter Count but Different Parameter Types

Consider:

~~~java
static String describe(int number) {
    return "int: " + number;
}

static String describe(long number) {
    return "long: " + number;
}

static String describe(String text) {
    return "text: " + text;
}
~~~

All three methods share the same name and take **one parameter**, but `int`, `long`, and `String` are different parameter types:

~~~text
describe(int)
describe(long)
describe(String)
~~~

These are valid overloads when placed in the same class, because their signatures differ. Calling `describe(7)` typically selects `int`, `describe(7L)` selects `long`, and `describe("A")` selects `String`.

**Distinguishing primitive and wrapper types:** `int` differs from `Integer`, and `long` differs from `Long`. For example, `m(int)` and `m(Integer)` are two valid overloads; boxing/unboxing may participate in method selection during call resolution, rather than erasing the difference between the two signatures.

**The declared type of the parameter is the basis**, not the parameter name. Writing `int points`, `int score`, or `int number` all produce the same `int` parameter type.

## 4. Same Component Types but Different Parameter Order

Type order is part of the formal parameter list:

~~~java
static String convert(int quantity, long price) {
    return "int-long";
}

static String convert(long price, int quantity) {
    return "long-int";
}
~~~

The two signatures are `convert(int, long)` and `convert(long, int)`. They differ because the positions of `int` and `long` are swapped, even though they **both have two parameters** and use the same two types.

This **does not guarantee that every call will be uniquely resolved by the compiler**:

~~~java
convert(1, 2L);  // int, long -> first overload
convert(1L, 2);  // long, int -> second overload
convert(1, 2);   // error: can be ambiguous between the two overloads
~~~

The lines above illustrate calls within the scope where the two `convert` overloads exist; the final call is intentionally written to demonstrate an error. For `convert(1, 2)`, the first method matches the first `int` parameter and requires widening `int` to `long` for the second parameter; the second method has the reverse correspondence. Neither method is more specific than the other across the **entire parameter list**, so the call is ambiguous.

Therefore, changing parameter order can produce valid signatures, but it can also easily make an API difficult to use. Parameters of the same type swapped in position are even more dangerous: if both parameters are `String`, swapping the meaning of `source` and `destination` **does not create a new signature**, and the compiler cannot automatically detect when a caller reverses them.

## 5. Things That Do Not Distinguish Overloads

### Renaming Parameter Variables

~~~java
void update(int amount) { }
void update(int value) { }
~~~

**Invalid when placed in the same class.** Both are `update(int)`. The names `amount` and `value` are only used inside the body and documentation, not as an overloading criterion.

### Changing Only the Return Type

~~~java
int count() {
    return 1;
}

long count() {
    return 2L;
}
~~~

**Invalid within the same class:** both are `count()`. Java does not select overloads based on the type of the variable receiving the result, such as `int x = count();` versus `long y = count();`. Changing `int` to `long` in the `return type` does not make the two signatures different.

### Changing Only the Access Modifier or `static`

~~~java
private void ping(int id) { }
public void ping(int id) { }
~~~

These are also **two declarations with identical signatures**, so they cannot coexist in the same class. If one method is `static` and the other is an instance method, with the same name and the same parameters, they still do not form two distinct overloads.

### Changing Only `throws`

~~~java
void load(String path) throws java.io.IOException { }
void load(String path) throws java.sql.SQLException { }
~~~

The two declarations above also collide on `load(String)` and cannot be placed together in the same class. The list of checked exceptions can affect the caller's error-handling obligations, but it is **not a part that helps distinguish signatures**.

### Changing Only Annotations or `final`

A declaration with a `@Deprecated` annotation or a `final` modifier does not thereby create a new overload of a declaration with the same name and the same parameters. These elements serve their own purposes, not a way to make the parameter type list different.

**Quick review rule:** strip out the parameter variable names and the return type, keeping only the method name and the parameter type list. If two declarations remain identical (after accounting for relevant generic/erasure rules), they cannot be considered overloads merely because information outside the signature changed.

## 6. Standalone Runnable Program: Count, Type, and Order

Create the file **`OverloadSignatureDemo.java`**:

~~~java
class Printer {
    static String select(int number) {
        return "one-int";
    }

    static String select(int left, int right) {
        return "two-int";
    }

    static String select(long number) {
        return "one-long";
    }

    static String select(String text) {
        return "one-String";
    }

    static String select(Object object) {
        return "one-Object";
    }

    static String select(int first, long second) {
        return "int-long";
    }

    static String select(long first, int second) {
        return "long-int";
    }

    static String select(int... numbers) {
        return "varargs:" + numbers.length;
    }
}

public class OverloadSignatureDemo {
    public static void main(String[] args) {
        System.out.println(Printer.select(7));
        System.out.println(Printer.select(7L));
        System.out.println(Printer.select("Java"));
        System.out.println(Printer.select(new Object()));

        System.out.println(Printer.select(4, 5));
        System.out.println(Printer.select(4, 5L));
        System.out.println(Printer.select(4L, 5));

        System.out.println(Printer.select());
        System.out.println(Printer.select(1, 2, 3));
        System.out.println(Printer.select(new int[] {8, 9}));
    }
}
~~~

From the directory containing the file, run:

~~~bash
javac -encoding UTF-8 OverloadSignatureDemo.java
java OverloadSignatureDemo
~~~

Stdout:

~~~text
one-int
one-long
one-String
one-Object
two-int
int-long
long-int
varargs:0
varargs:3
varargs:2
~~~

Analysis by group:

1. `select(7)` selects `select(int)`, because the integer literal `7` has type `int`; `select(7L)` selects `select(long)`.
2. `select("Java")` selects `select(String)`, which is a more specific type than `Object` for a `String` argument; `select(new Object())` selects `select(Object)`.
3. `select(4, 5)` has an overload that accepts exactly two `int`s; this two-argument call **does not fall back to** `int...` because an applicable and specific fixed-arity overload already exists.
4. `select(4, 5L)` best matches `select(int, long)`; `select(4L, 5)` best matches `select(long, int)`.
5. `select()` takes no arguments, yet `select(int...)` accepts an **empty varargs array**, so it prints `varargs:0`.
6. `select(1, 2, 3)` passes three numbers into `int...`, so the length is 3; `select(new int[] {8, 9})` passes an existing array to the same overload, so the length is 2.

The example has many overloads to clarify the selection criteria. In applications, you should use overloads when they share the **same operational meaning**, rather than turning a single shared name into a collection of unrelated functions.

## 7. Valid Signatures Are Not Enough for a Valid Call

Java separates **two conceptual steps**:

1. **Declaration:** do the methods with the same name have signatures that can coexist?
2. **Invocation:** given the actual arguments at a call site, can the compiler find **one applicable and most-specific method**?

The two methods `convert(int, long)` and `convert(long, int)` in Section 4 are valid declarations. However, `convert(1, 2)` is invalid due to an **ambiguous invocation**. That is an error at the call site, not two declarations with duplicate signatures.

Java evaluates applicable methods across multiple phases during overload resolution. For Java 17, when simplified for common cases, the important order is:

- First, try calls with a **fixed number of parameters**, allowing matching *strict invocation conversions*, which include primitive widening without yet relying on boxing/unboxing.
- If no matching candidate is found yet, proceed to search for fixed-arity calls with *loose invocation conversions*, including boxing/unboxing according to the rules.
- When the preceding phases yield no applicable method, **variable arity** (varargs) is then considered, in which the compiler may pack individual arguments into an array.

After each phase, among the applicable candidates, Java uses the **most-specific method** rule to make the selection; it is not simply “use the first matching name” or “the method declared earlier takes precedence”.

**The compiler resolves overloads at compile time**, based on the static types of expressions and relevant contextual information; it does not wait for the concrete runtime object value to choose a new parameter list.

## 8. Type Conversions at Call Time Differ from Signatures at Declaration

The two declarations `pick(long)` and `pick(Integer)` can coexist because their **parameter type lists are different**. When calling `pick(5)`, the literal 5 has type `int`: widening `int → long` can be applied in the strict invocation phase before boxing `int → Integer`. That rule resolves **a call**, without changing the declared signature.

Similarly, `log(String...)` has one parameter with array type `String[]` in its signature. The ability to call `log("A", "B")` is a *varargs invocation* convenience, not the creation of a second method signature. The three-phase strict/loose/variable-arity cases and most-specific selection are analyzed in depth in the lesson on type conversion order.

To avoid confusion: **(1)** compare declaration signatures; **(2)** check the static types at the call site; **(3)** evaluate type conversions and most-specific selection. Do not use a “fewest conversion steps” shortcut as a general JLS rule.

## 9. `null`: Valid Signatures Do Not Guarantee a Valid Call

~~~java
static void show(Object value) { }
static void show(String value) { }
// show(null) selects show(String): String is more specific than Object.
~~~

If another class has `show(String)` and `show(Integer)`, the two signatures are still different, yet `show(null)` is **ambiguous**: neither type is a subtype of the other. `show((String) null)` selects the String overload based on the static type provided by the cast; the value is still null, so the body must not arbitrarily dereference it.

The dedicated lesson on null examines interfaces, arrays, varargs, and generics in further detail. Here, the lesson is that **declarations without duplicate signatures** and **uniquely resolving invocations** are two separate requirements.

## 10. Varargs: The Ellipsis Does Not Create a Separate Signature from an Array

Given the declaration:

~~~java
void log(String... messages) { }
~~~

The parameter `messages` has type `String[]` inside the body. Therefore, this declaration has the same signature as:

~~~java
void log(String[] messages) { }
~~~

**Both cannot be placed in the same class**; they are not treated as two overloads. The `...` syntax differs from `[]` in **invocation** convenience, not by creating a new parameter type in the signature.

A varargs method allows:

~~~java
log();
log("A");
log("A", "B");
log(new String[] {"A", "B"});
~~~

If only `log(String[])` is declared, calls passing multiple separate `String`s such as `log("A", "B")` are invalid. With varargs, `log()` uses an empty array under variable-arity invocation semantics. Passing an existing array `log(new String[] {...})` uses a corresponding array argument.

### Varargs and Overloads Have Different Precedence

We already saw that `select(int, int)` takes precedence for `select(4, 5)` before the compiler needs to fall back to the variable-arity form `select(int...)`. However, **varargs can still be applied in fixed-arity form** if the last argument is a compatible array, such as `select(new int[]{8, 9})`.

Do not assume that every call to a method declared with `T...` automatically creates a new array; if the caller already passes a matching `T[]` array, the parameter variable can use that exact array reference. Modifying array elements can affect the caller.

### Zero-Argument Calls Can Also Be Ambiguous

These two declarations **have different signatures and can coexist**:

~~~java
static void collect(String... values) { }
static void collect(Integer... values) { }
~~~

However, `collect()` can result in an **ambiguous method call** because both accept 0 elements, and neither `String[]` nor `Integer[]` has a more-specific relationship for selection. You can explicitly pass `new String[0]` or `new Integer[0]` to select the intended overload.

## 11. Generics: Parameterized Types and Type Erasure

With generics, you also need to understand that **overloads cannot be distinguished solely by type arguments of the same generic type** in many cases. For example:

~~~java
void save(java.util.List<String> names) { }
void save(java.util.List<Integer> numbers) { }
~~~

The two declarations above **cause a name clash error** in the same class. After *type erasure*, both parameter types correspond to `List`; the JVM does not retain `String` and `Integer` as two separate parameter types in the descriptor to distinguish these methods.

However, the following two declarations are valid:

~~~java
void save(java.util.List<String> names) { }
void save(java.util.Set<String> names) { }
~~~

`List` and `Set` are two different raw/erased types, so these are two distinguishable overloads. **The call `save(null)` can still be ambiguous**, because neither `List<String>` nor `Set<String>` is a subtype of the other.

### Renaming Generic Type Parameters Does Not Help Either

~~~java
<T> void accept(T value) { }
<U> void accept(U value) { }
~~~

These are two **invalid declarations in the same class**: `T` and `U` are merely type parameter names, and signatures are compared after adapting the corresponding type parameters. Changing the letter `T` to `U` does not create a different method.

Similarly, a generic method `<T> void handle(T value)` typically conflicts with `void handle(Object value)` in the same class due to erasure and the corresponding signature rules. Do not rely on generic type arguments to craft overloads that the runtime cannot distinguish.

### Is Overloading Based on Generic Types Safe?

A single method can be written as a **generic method**:

~~~java
static <T> void saveAll(java.util.List<T> items) {
    System.out.println(items.size());
}
~~~

This is **one** declaration accepting `List<T>`, which can be used with `List<String>`, `List<Integer>`, and other appropriately typed lists. When you need the same operation across multiple element types, a generic method can be a better solution than trying to create multiple overloads that collide after erasure.

## 12. Distinguishing Overload Declarations from Overriding and Static Hiding

**Overloading**: same name, **different parameter signatures**. **Overriding**: a subclass provides a new implementation for an eligible inherited instance method, keeping a matching subsignature. **Static method hiding** is not a dynamic override.

Given `BaseGreeter ref = new ChildGreeter()`, the compiler resolves visible overloads via the **static type BaseGreeter**. At runtime, the selected instance method can then be dispatched to the overriding body of ChildGreeter. The runtime class of the receiver is not used to supply extra overloads absent from the static receiver type.

In-depth examples of overriding, static hiding, field hiding, and shadowing are covered in the lesson comparing the three mechanisms. The signature focus here: **different parameters to overload; valid replacement implementation to override**.

## 13. Primitives and Wrappers Are Distinct Signature Types

~~~java
static String type(int value) { return "primitive"; }
static String type(Integer value) { return "wrapper"; }
~~~

The two signatures `type(int)` and `type(Integer)` are different. `type(5)` selects int; `type(Integer.valueOf(5))` selects Integer. `type((Integer) null)` resolves to the Integer version, but the body is still responsible for null safety.

You should distinguish the **parameter type of the declaration** from **boxing/unboxing at invocation**: primitive and wrapper types are sufficient to create two distinct signatures, whereas which method gets selected is a separate question depending on applicability phases and most-specific resolution.

## 14. Parameter Order and API Design Pitfalls

These are two distinguishable signatures:

~~~java
void schedule(String title, int hour) { }
void schedule(int hour, String title) { }
~~~

However, providing both overloads just by swapping positions usually offers little benefit and causes confusion when reading code. Worse, if both parameters have the **same type**:

~~~java
void move(String source, String destination) { }
~~~

then changing variable names to `move(String destination, String source)` **does not create an overload**, because both have the signature `move(String, String)`. A swapped-argument mistake at the call site such as `move(destination, source)` will still compile successfully while producing incorrect business logic.

To make APIs easy to use:

1. Choose a consistent parameter order, placing identifying/contextual data first and options afterward when reasonable.
2. Use meaningful parameter names; parameter names **do not create signatures**, but they help with reading source code and displaying IDE hints.
3. When two parameters have the same type but completely different meanings, consider using domain-meaningful types such as `SourcePath`, `DestinationPath`, or a configuration object.
4. Only add overloads when there is a new way of calling that is meaningful to users, not for the sake of maximizing the number of signatures.

### Be Careful with Overloads Accepting `null`

If an API declares `send(String)` and `send(Integer)` merely for calling convenience, callers writing `send(null)` will encounter ambiguity. A different method name or a more descriptive data type is usually easier to use.

## 15. Diagnosing Signature-Related Compile Errors

| Symptom | Example | Cause | How to Fix |
| --- | --- | --- | --- |
| Method is already defined | `f(int a)` and `f(int b)` | Differs only in parameter name | Rename the method or change parameter types/count |
| Method is already defined | `int size()` and `long size()` | Differs only in return type | Keep one declaration, or use a different name |
| Name clash | `f(List<String>)`, `f(List<Integer>)` | Erasure collision | Use a single generic method or separate names |
| Cannot declare both | `f(String[])`, `f(String...)` | Varargs corresponds to array type | Choose one declaration form |
| Reference to method is ambiguous | `f(int,long)`, `f(long,int)`, calling `f(1,1)` | Both overloads apply, neither is more specific | Pass explicit types or change the API |
| Reference to method is ambiguous | `f(String)`, `f(Integer)`, calling `f(null)` | `null` matches both types with no subtype relationship | Cast `null` or change the API |
| Cannot find suitable method | Only `f(int,int)` exists, but `f("A")` is called | No overload accepts the matching argument type/count | Fix the call or add a sensible overload |

`javac` error messages may vary slightly depending on version and context; inspect the **declared parameter types**, the **types of expressions passed**, and the error location. Do not mistakenly change the return type when the compiler reports duplicate signatures.

### Checklist for Ambiguity Errors

1. List the overloads with the same name that are **accessible** at the call site.
2. Note the **compile-time type** of each argument expression; distinguish `5` (`int`) from `5L` (`long`), `null`, `Object`, and `String`.
3. Match the number and order of parameters in each signature.
4. Evaluate primitive widening, boxing/unboxing, and varargs in phases; eliminate non-applicable candidates.
5. If multiple candidates remain, check which method is **most specific**; if there is no unique choice, the call is ambiguous.
6. Make the input or API clearer instead of scattering unnecessary casts everywhere.

## 16. Self-Check: Which Declarations Are Valid, and Which Method Does Each Call Select?

**Question 1.** In the same class there are `m()`, `m(int)`, `m(int,int)`, and `m(String)`. How many distinct signatures are there? Which one does `m(3,4)` select?

**Question 2.** Can the two declarations `void pay(int amount)` and `int pay(int cents)` coexist? Explain the role of the return type and parameter names.

**Question 3.** Are `void set(int code,long value)` and `void set(long code,int value)` valid? What happens when calling `set(1,2)`?

**Question 4.** Are `void f(List<String>)` and `void f(List<Integer>)` overloads that the JVM distinguishes by generic arguments?

**Question 5.** Why can't `void log(String... xs)` be declared alongside `void log(String[] ys)`?

**Question 6.** Given `void show(Object)` and `void show(String)`, which method does `show(null)` select? Does the result change if the second overload is `show(Integer)` instead of `show(String)`?

**Question 7.** Given `pick(long)`, `pick(Integer)`, and `pick(int...)`, which overload does `pick(5)` select, and why?

**Question 8.** In the `BaseGreeter`/`ChildGreeter` example, why does `baseView.greet("An")` print `child-object`, while `childView.greet("An")` prints `child-string`?

**Answer Key:**

1. There are four signatures; `m(3,4)` selects `m(int,int)`.
2. Invalid: both are `pay(int)`; `void`/`int` and `amount`/`cents` do not distinguish signatures.
3. Both declarations are valid because of different **type order**; `set(1,2)` is ambiguous because neither overload is uniquely more specific.
4. No. Type erasure causes them to collide; you can use a generic method or different names instead.
5. In a method signature, `String...` corresponds to `String[]`.
6. `show(String)` is more specific than `show(Object)` and is selected; if the overload set is `show(Object)` and `show(Integer)`, then `show(Integer)` is selected because it is more specific than `Object`. **Only if both `show(String)` and `show(Integer)` are present at the same time** is the call `show(null)` ambiguous.
7. `pick(long)`; widening from `int` to `long` is considered before boxing and variable arity.
8. Overloads are selected based on the static type of the variable at compile time; instance method overrides are dispatched based on the actual runtime type of the object.

## 17. References

- [Java Language Specification 17, §8.4.2 — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2): signatures, subsignatures, override-equivalence, and erasure relationships.
- [Java Language Specification 17, §8.4.9 — Overloading](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.9): rules for overloading declarations.
- [Java Language Specification 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): finding applicable methods, selecting the most-specific overload, and invocation semantics.

**Key takeaway:** when reading an overload, focus on **method name + parameter count, types, and order**. Changing parameter variable names, return types, modifiers, or `throws` does not create a new signature. Two declarations with different signatures can still cause an **ambiguous call**; and with generics, you also need to check **type erasure**. Properly distinguishing signatures from call-selection rules helps design clearer APIs and avoid confusing compilation errors.
