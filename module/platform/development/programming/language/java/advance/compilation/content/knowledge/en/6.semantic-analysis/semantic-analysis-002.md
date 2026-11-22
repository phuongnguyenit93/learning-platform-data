# Overload Resolution and Compile-Time Type Influence

When multiple methods share the same name but have different parameter lists, Java allows **overloading**. The crucial point is that **`javac` chooses the method signature to call based on compile-time type information**: the static type of the receiver expression, the types of the arguments, the number of arguments, type conversion possibilities, the availability of each method, and the rules for selecting the most specific method.

The runtime value of an object **does not cause Java to automatically choose a different overload**. Runtime may use **overriding** to select the implementation of *the exact signature that was already chosen*, but that is a separate step.

This article explains `javac`'s overload resolution process, the influence of static types, primitive widening, boxing/unboxing, varargs, `null`, generics, ambiguity, how to distinguish overloading from overriding, and diagnostic methods. The standalone examples use Java 17+.

## 1. What is overloading?

Two methods can share the same name if their **signatures** differ in parameter type lists (and elements related to type parameters according to JLS rules):

```java
static void print(int value) {
    System.out.println("int: " + value);
}

static void print(String value) {
    System.out.println("String: " + value);
}
```

These are two overloaded methods: `print(int)` and `print(String)`. When writing `print(12)`, the argument expression has type `int`, so `print(int)` is the direct candidate; with `print("hello")`, `print(String)` is more suitable.

**Changing only the return type is not enough to overload**:

```java
// DOES NOT COMPILE when both declarations are placed in the same class.
int read(String key) { return 1; }
String read(String key) { return key; }
```

The two methods above have the same name and the same parameter types, so they are duplicate declarations. Return type is not a way to create two overloads with the same parameter list. Intentionally erroneous examples in this article are clearly marked and should not be placed together with runnable Java code.

Some points to remember:

- Overloads do not have to have the same return type; they require valid, distinct declared signatures.
- Overloading can involve `static` or instance methods, though access, inheritance, hiding, and availability rules still apply.
- Two methods cannot be distinguished solely by parameter names: `take(int a)` and `take(int b)` still have duplicate signatures.
- `int[]` and `int...` represent the same array parameter type `int[]` at the declared signature level; these two forms alone cannot be used to create two overloads in the same class.

## 2. Complete example: same data, different static types

Create the file `OverloadWalkthrough.java`:

```java
public class OverloadWalkthrough {
    static void label(Object x) {
        System.out.println("Object");
    }

    static void label(String x) {
        System.out.println("String");
    }

    static void number(long x) {
        System.out.println("long");
    }

    static void number(Integer x) {
        System.out.println("Integer");
    }

    static void number(int... x) {
        System.out.println("int... " + x.length);
    }

    static class Parent {
        void show(Object x) {
            System.out.println("Parent Object");
        }
    }

    static class Child extends Parent {
        @Override
        void show(Object x) {
            System.out.println("Child Object");
        }

        void show(String x) {
            System.out.println("Child String");
        }
    }

    public static void main(String[] args) {
        Object o = "text";
        String s = "text";

        label(o);
        label(s);
        label(null);

        number(7);
        Integer boxed = 7;
        number(boxed);
        number();
        number(7, 8);

        Parent ref = new Child();
        ref.show("text");
        ((Child) ref).show("text");
    }
}
```

From the directory containing the file, using JDK 17+:

```bash
javac --release 17 -encoding UTF-8 -d out OverloadWalkthrough.java
java -cp out OverloadWalkthrough
```

**Exact stdout**:

```text
Object
String
String
long
Integer
int... 0
int... 2
Child Object
Child String
```

The Java code above was verified with `javac` and `java` on JDK 21 targeting `--release 17`. These output lines help observe three different mechanisms: **static types**, **the order of overload phases**, and **overridden method dispatch**.

The following sections explain them one by one, especially why `number(7)` chooses `long` instead of `Integer`, and why `ref.show("text")` calls `Child.show(Object)` even though the actual class is `Child`.

## 3. The static type of the argument determines the overload

In the example:

```java
Object o = "text";
String s = "text";

label(o); // label(Object)
label(s); // label(String)
```

Both `o` and `s` point to a `String` object. However:

- `o` has **declared type `Object`**. `javac` does not choose `label(String)` merely because at runtime the value happens to be a `String`. `label(Object)` matches an argument of type `Object`.
- `s` has **declared type `String`**. Both `label(Object)` and `label(String)` can accept a value of type `String`, but `label(String)` is more specific, so it is selected.
- `label(null)` is valid for both reference-type parameters; since `String` is a subtype of `Object`, `label(String)` is selected as the more specific overload.

You cannot deduce overload selection from `x.getClass()` and apply it backward to the compilation process. `x.getClass()` is runtime information, whereas overloading is resolved when the compiler processes the invocation expression.

### Casting changes how javac sees the expression

```java
Object value = "hello";

label(value);           // label(Object)
label((String) value);  // label(String)
```

The cast form `(String) value` makes **the expression at the argument position have static type `String`**. If the value is not actually a `String`, the cast may throw `ClassCastException` before the call occurs. Casting is not a way to automatically "enable" runtime-based overloading; it is an expression with its own checking rules.

Another example:

```java
Object value = new Object();
// label((String) value); // If uncommented, this compiles, but
// throws ClassCastException at runtime before calling label(String).
```

If you need behavior that depends on the actual type, use explicit type checks and branches:

```java
if (value instanceof String text) {
    label(text);  // text has type String in the true branch.
} else {
    label(value);
}
```

This is an **illustrative** snippet placed inside a method that has `label` and the variable `value` in scope; it is not a standalone program. With Java 17's `instanceof` pattern matching, the variable `text` is used within the scope where it is guaranteed to have matched the type.

## 4. How does javac find and choose an overload?

The Java Language Specification (JLS `15.12) describes the process with rule-based steps:

1. **Determine the type to search for methods** from the invocation form and receiver (for example `ref.method(...)`, `Type.method(...)`, or an unqualified call).
2. **Find candidates with matching name and potentially matching argument count**, including methods accessible from the type to search and inherited methods, considering special rules for generics, lambdas, or method references.
3. **Determine applicability** across three ordered phases. It only moves to the next phase when no applicable method is found in the previous phase.
4. **Select the most specific method** from the applicable set in the first successful phase. If no applicable method exists or multiple optimal methods exist without a unique choice under JLS rules, the compiler reports the corresponding error.
5. **Check the appropriateness of the invocation** against additional requirements. The selected signature information participates in the invocation expression and runtime dispatch path.

This is a more accurate model than a memorized rule like "Java always picks the method with the fewest conversions." The compiler does not simply add points for each conversion and pick the smallest total; the JLS explicitly defines **phases**, applicability, and the *more specific* relationship.

### Three phases of overload resolution

| Phase | Name in JLS | Conversions considered at a high level | Varargs expansion |
| --- | --- | --- | --- |
| 1 | Strict invocation | Type match, primitive widening, reference widening, and other strict compatibilities; **no boxing/unboxing needed** | Not expanded |
| 2 | Loose invocation | Adds boxing/unboxing and valid loose invocation conversions | Not expanded |
| 3 | Variable arity | Allows applying a variable-arity call to a `...` method, along with permitted conversion rules | Yes |

**If a candidate is found in phase 1, phase 2 is not checked to "compete" with a boxing candidate.** If phase 1 has no candidates, only then is phase 2 checked. Similarly, varargs expansion is normally deferred until phase 3.

At each phase, a varargs method can still be considered as **fixed arity** if the argument is directly compatible with the array parameter, such as passing an `int[]` to `m(int...)`. Therefore, do not misunderstand that every call to a method declared with `...` always falls into phase 3.

In generic methods or calls with lambdas/method references, determining "applicability" is more complex than the summary table; the compiler also uses inference and target typing. When concluding on a tricky case, consult the JLS instead of mechanically applying only those three sentences.

## 5. Primitive widening, boxing, and unboxing: order matters

Consider the overloads in `OverloadWalkthrough`:

```java
static void number(long x) { System.out.println("long"); }
static void number(Integer x) { System.out.println("Integer"); }
static void number(int... x) { System.out.println("int... " + x.length); }
```

With the call:

```java
number(7);
```

The literal `7` has type `int`. Possible conversion paths to consider:

- `int -> long`: **primitive widening**, applicable in phase 1.
- `int -> Integer`: **boxing**, considered in phase 2 if phase 1 has no matching method.
- `int -> int...` as a single element: **varargs expansion**, considered in phase 3 if previous phases have no matching method.

**The result is `number(long)`.** Because phase 1 already found a candidate, the compiler does not need to consider boxing or varargs expansion.

With:

```java
Integer boxed = 7;
number(boxed);
```

The argument has static type `Integer`. Overload `number(Integer)` is directly compatible in phase 1, whereas converting `Integer -> long` requires unboxing followed by widening and thus cannot beat a phase 1 candidate. The output prints `Integer`.

With:

```java
number();      // zero arguments -> int... 0
number(7, 8);  // two arguments -> int... 2
```

Only the varargs overload `number(int...)` can accept the corresponding number of arguments via the `...` expansion mechanism. The actual value received is an `int[]` array of 0 or 2 elements.

### Widening can be chosen before boxing

A useful rule of thumb: **if a fixed-arity overload is already applicable via strict conversion (such as widening), it does not reach the boxing phase**. However, this does not establish an absolute ordering table for *every* type and every overload.

Another example (illustrative code in the same class):

```java
static void route(Number n) {
    System.out.println("Number");
}
static void route(long n) {
    System.out.println("long");
}

Integer value = 10;
route(value); // route(Number): reference widening in phase 1.
```

Here `Integer -> Number` is reference widening, whereas `Integer -> long` requires unboxing and primitive widening. The result is `Number`.

### Numeric literals do not automatically narrow for overloads

A literal `1` has type `int` unless specified otherwise. Java has cases of **constant assignment** for `byte` or `short` when the value fits, but that rule **does not mean** the compiler automatically tries primitive narrowing for method invocations:

```java
static void onlyByte(byte x) {}

byte b = 1;       // Valid constant assignment within byte value range.
onlyByte(b);      // Valid.
onlyByte((byte) 1); // Valid thanks to cast.
// onlyByte(1);   // COMPILE ERROR: int -> byte does not automatically narrow on call.
```

The snippet above is an example **inside an appropriate class/method**, not a standalone source file. This principle explains many overload phenomena that seem different from assignment.

## 6. What is the most specific method?

If multiple methods are applicable within the same phase, the compiler chooses the **most specific** overload **according to JLS `15.12.2.5**. For classes with an easy-to-understand parent–child relationship, a method taking a subclass is usually more specific than a method taking a superclass.

```java
static void label(Object o) { System.out.println("Object"); }
static void label(String s) { System.out.println("String"); }
```

For `label("abc")`, type `String` can be converted to `Object`. Both overloads apply in phase 1, but `String` is more specific than `Object`, so `label(String)` is chosen.

For `label(null)`, the `null` literal is compatible with reference types and `String` is still more specific than `Object`; therefore `label(String)` is also chosen.

However, if the parameter types **do not have a clear more-specific relationship**, the compiler may have no unique winning overload. That case is *ambiguous*; it does not randomly choose the overload that appears first in the file.

### Ambiguity due to null

The following two overloads can coexist:

```java
static void select(String value) {
    System.out.println("String");
}
static void select(Integer value) {
    System.out.println("Integer");
}
```

The calls:

```java
select("a");             // String
select(Integer.valueOf(1)); // Integer
// select(null);          // COMPILE ERROR: ambiguous.
select((String) null);   // String
select((Integer) null);  // Integer
```

`null` does not have a concrete String or Integer runtime type for the compiler to rely on. Both overloads can accept `null`, and `String` is not a subtype of `Integer` (nor vice versa), so there is no unique winning method under the rules applicable here. **A cast explicitly specifies the static type of the expression**, thereby resolving the ambiguity.

Do not "fix" it by reversing the declaration order: appearance order in source code does not decide overloads.

### Ambiguity due to symmetric parameters

```java
static void mix(int a, long b) {}
static void mix(long a, int b) {}

// mix(1, 1); // COMPILE ERROR: both apply, neither is more specific.
mix(1, 1L);   // Selects mix(int, long).
mix(1L, 1);   // Selects mix(long, int).
```

In the call `mix(1, 1)`, each overload has one position matching `int` and one position widening `int -> long`. There is no rule "treat the first parameter as priority" to eliminate ambiguity. The literals with suffix `L` in the next two calls change the static types of the arguments, leading to a clear selection.

## 7. Varargs are also part of overload resolution

Varargs are declared with `...`, yet the method actually has an array parameter. For example:

```java
static void sum(int... numbers) {
    System.out.println(numbers.length);
}
```

There are two valid ways to call it:

```java
sum(1, 2, 3);                 // Varargs expansion: 3 elements.
sum(new int[] {1, 2, 3});    // Pass an int[] array directly.
```

Both forms print `3`. The case passing an array can be handled as a fixed-arity invocation; the case with three separate integer arguments uses variable-arity invocation.

An example of fixed-arity priority:

```java
static void send(int x) {
    System.out.println("fixed");
}
static void send(int... values) {
    System.out.println("varargs");
}

send(5);    // fixed
send(5, 6); // varargs
```

`send(5)` selects the fixed-arity version `send(int)` in phase 1; varargs expansion is not used yet. `send(5, 6)` does not match `send(int)` because the number of arguments differs, so the varargs version matches in phase 3.

**Be careful with the `null` literal and reference-type varargs:** for example, a call `m(null)` to `m(Object...)` may be treated as passing **a null `Object[]` array**, not an array containing one null element; the compiler may emit a warning. If you want to pass one null element, use `m((Object) null)`; if you intentionally want to pass a null array, use `m((Object[]) null)`. Do not access `array.length` when the array can be null.

## 8. Receiver static type and the difference between overloading and overriding

This is the easiest place to get confused. Returning to the example:

```java
static class Parent {
    void show(Object x) {
        System.out.println("Parent Object");
    }
}

static class Child extends Parent {
    @Override
    void show(Object x) {
        System.out.println("Child Object");
    }

    void show(String x) {
        System.out.println("Child String");
    }
}

Parent ref = new Child();
ref.show("text");
((Child) ref).show("text");
```

In the call `ref.show("text")`:

1. **The static type of the receiver is `Parent`**, so the overload lookup step is performed based on the methods present/available according to type `Parent`. Here the compiler finds `show(Object)`, while the overload `show(String)` is declared only on `Child` and thus is not in the candidate set when the static receiver is `Parent`.
2. **The compiler selects the signature `show(Object)`**. The actual argument being `String` simply allows reference widening to `Object`.
3. **Runtime sees the actual receiver is `Child`**, so for an overridden instance method, the JVM executes the `Child.show(Object)` implementation. The output is `Child Object`.

In the call `((Child) ref).show("text")`, the receiver expression has been cast to `Child`. The compiler sees both `show(Object)` and `show(String)`; the overload `show(String)` is more specific. The output is `Child String`.

| Question | Overload resolution | Override dispatch |
| --- | --- | --- |
| Where is the decision made? | At compile time | At runtime for instance methods with dynamic dispatch |
| What is it based on? | Static types of receiver/arguments, candidate list, and JLS rules | Runtime type of the receiver and the chosen signature |
| Can the chosen signature change after compilation? | No, runtime type does not decide it | No; it only chooses the matching implementation for the same signature |
| Example | `show(Object)` or `show(String)` | `Parent.show(Object)` or `Child.show(Object)` |

**Technical conclusion:** A single call can have **statically resolved overloading**, followed by **dynamically resolved overriding**. Simply saying "Java method binding is all static" or "Java always calls methods by runtime type" misses the conditions.

`static` methods use a different mechanism (method hiding, with no dynamic dispatch like instance overriding). `private` methods and certain special invocation forms also do not follow ordinary virtual dispatch intuition. This lesson focuses on method call overloading and common instance overriding examples.

## 9. Generics and static types of collections

Generics make declaring variables via interfaces even more important. Create the file `GenericView.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class GenericView {
    static void inspect(Collection<?> c) {
        System.out.println("Collection");
    }

    static void inspect(List<?> l) {
        System.out.println("List");
    }

    public static void main(String[] args) {
        Collection<String> asCollection = new ArrayList<>();
        List<String> asList = new ArrayList<>();

        inspect(asCollection);
        inspect(asList);
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 -d out GenericView.java
java -cp out GenericView
```

Exact stdout:

```text
Collection
List
```

Both runtime values are `ArrayList`, but the first variable has static type `Collection<String>`, so only the overload taking `Collection<?>` applies from that variable's type in this example. The second variable has static type `List<String>`; since `List` is a subtype of `Collection`, the overload `inspect(List<?>)` is more specific.

**Type erasure** also restricts how generics can be overloaded. The following two methods **cannot be declared together in one class**:

```java
// COMPILE ERROR: name clash due to same erasure.
static void consume(java.util.List<String> values) {}
static void consume(java.util.List<Integer> values) {}
```

After erasure, both have the effective parameter list `List`, causing a conflict. Do not assume Java has separate overloads for `List<String>` and `List<Integer>` based solely on the generic type argument inside angle brackets.

### Generic methods and type inference

For a generic method such as:

```java
static <T extends Number> void accept(T value) {
    System.out.println("number");
}
```

The compiler must infer the type parameter `T` to satisfy bounds and the call context. When a generic overload competes with other overloads, Java does not just compare raw class names; **type inference, bounds, wildcards, and poly expressions** can participate in determining which candidates apply and which candidate is more specific.

The `accept` code above is an illustration of generic inference, **not a standalone runnable program**. For complex generic calls, consult JLS `18 (Type Inference) along with `15.12, rather than trying to deduce from a "runtime type" rule.

## 10. Lambdas, method references, and overloading

Lambdas/method references receive their type via a **target type**, which is a functional interface. If there are overloads with two different functional interfaces, the compiler must consider the lambda shape, inferable parameter types, result type, and candidate specificity.

Illustrative example with two overloads:

```java
static void execute(Runnable r) {
    r.run();
}

static void execute(java.util.concurrent.Callable<String> c)
        throws Exception {
    System.out.println(c.call());
}
```

Call:

```java
execute(() -> System.out.println("running"));
```

This lambda matches the `void`-returning behavior of `Runnable`, so it chooses the `execute(Runnable)` overload and prints `running`. Whereas:

```java
execute(() -> "result");
```

The lambda returns a `String`, so it matches `Callable<String>` better; this overload prints `result`. The example snippets above only run when placed inside a class where the calling method handles or declares `throws Exception` for the `Callable` branch; they are not standalone Java files like `OverloadWalkthrough.java`.

A lambda with an undetermined body/type can make overload applicability depend on target typing, and some combinations lead to ambiguity. **You cannot just look at the runtime lambda object** to choose an overload. Some lambdas or method references are evaluated under specific "pertinent to applicability" rules in JLS `15.12 and `15.27; the simple example above does not replace all of those rules.

## 11. When does a call report an ambiguous error or fail to find an overload?

Two common yet distinct errors:

- **No suitable method / cannot be applied:** no candidate can accept the arguments under valid conversion rules; for example, only `read(byte)` exists but `read(1000)` is called with an `int` argument—Java does not automatically narrow for method invocations.
- **Reference to ... is ambiguous:** at least two candidates apply, but no single winner can be determined; for example, `select(String)` and `select(Integer)` when calling `select(null)`.

For example, `java.lang.String.valueOf(...)` has many overloads. When analyzing real code, read **the exact overload list of the API and the exact JDK version**, determine the static type of each argument, and apply the resolution procedure; do not guess the compiler's behavior from the printed value.

### The compiler checks static types, not by "test-running" arguments

`javac` does not execute the program to know:

- Whether an `Object` variable definitely holds a String at runtime.
- Which `if` branch will be executed based on runtime data.
- Which runtime subtype object a function's return value will have.
- Whether a cast to a subtype will succeed or throw `ClassCastException` on a specific run.

The compiler can use other static information such as the flow-sensitive type of a pattern variable, generic inference, or expression kinds, but that is still **compile-time language analysis**.

### How to fix ambiguity purposefully

1. Verify the overloads and the actual static types of each argument at the call site.
2. Use a variable with a specific type or a **safe, deliberate** cast if you want to select a deterministic signature.
3. If two overloads make an API frequently ambiguous, consider **using clearer method names** or redesigning the parameters.
4. Do not expect a later-declared overload to be preferred.
5. Do not add an unchecked cast just to silence the compiler and end up causing a `ClassCastException` at runtime.

## 12. Inspecting bytecode to see the chosen signature

After compiling `OverloadWalkthrough.java`, run:

```bash
javap -classpath out -c OverloadWalkthrough
```

`javap -c` displays the instructions of the class file, including call instructions and target method information such as `label:(Ljava/lang/Object;)V`, `label:(Ljava/lang/String;)V`, `number:(J)V`, or `number:(Ljava/lang/Integer;)V` (exact output formatting depends on `javap`/JDK).

These descriptors illustrate that **the overload signature is decided at compile time**:

- `(Ljava/lang/Object;)V`: takes an `Object`, returns `void`.
- `(Ljava/lang/String;)V`: takes a `String`, returns `void`.
- `(J)V`: takes a primitive `long`, returns `void`.
- `(Ljava/lang/Integer;)V`: takes an `Integer`, returns `void`.
- `([I)V`: takes an `int[]` array, returns `void`, corresponding to the `int...` parameter.

The purpose of `javap` here is to verify the selected signature, not to interpret every JVM instruction in detail. Bytecode can vary across compiler versions; overload selection per the JLS must still be preserved in observable behavior.

For an overridden instance method, the bytecode contains a reference to **the chosen descriptor**; runtime virtual dispatch picks the corresponding implementation of the runtime receiver if applicable. It does not try again to switch from `show(Object)` to `show(String)`.

## 13. Common misconceptions

| Misconception | What is true | Example |
| --- | --- | --- |
| "The value is a String so the String overload will run" | Must consider the **static** type of the argument | `Object o = "x"; label(o)` calls `label(Object)` |
| "Java always prefers boxing over widening" | Strict invocation is checked before boxing | `number(7)` selects `number(long)` |
| "Varargs takes priority because it accepts many arguments" | Fixed arity is checked before varargs expansion | `send(5)` selects `send(int)` |
| "Overloading is decided by the runtime class" | Overload is static; override is dynamic for virtual methods | `Parent ref = new Child(); ref.show("x")` |
| "null always selects Object" | Selects the most specific candidate or reports ambiguous | `label(null)` selects String; `select(null)` is ambiguous |
| "Differing only by return type is an overload" | Same parameter list is a duplicate signature | Two `read(String)` with different return types error |
| "List<String> and List<Integer> are two separate overloads" | Erasure causes a name clash when differing only in generic type arguments | Two `consume(List<...>)` error |
| "An int literal automatically narrows for a byte parameter" | Method invocation does not automatically perform constant narrowing like assignment | `onlyByte(1)` errors |
| "The compiler picks the method that appears first" | Declaration order is not a selection criterion | `select(null)` is still ambiguous |
| "If compilation succeeds, the cast will definitely run" | A runtime cast can still throw an error | `(String) new Object()` |

## 14. Process for analyzing a difficult overload call

When you see a surprising call, answer in order:

1. **What is the method name and invocation form?** For example `receiver.act(x)` or `Type.act(x)`; is it instance/static, qualified or unqualified?
2. **What is the static type of the receiver?** Do not use the runtime type as the answer. This type determines the class/interface to search for members.
3. **What is the type of each argument expression?** Including `int`/`long` literals, `Object`/`String` variables, `null`, casts, generics, and lambdas.
4. **Which overloads are valid and accessible?** Check argument count, inheritance, `static`/instance, access rights, and the actual signature.
5. **Does phase 1 have candidates?** Check strict invocation, primitive/reference widening, fixed arity.
6. **If not, does phase 2 have candidates?** Check boxing/unboxing and loose invocation rules.
7. **If still none, does phase 3 have candidates?** Check variable arity for varargs.
8. **What is the most specific method in the winning phase?** If there is no unique winner, report ambiguity; do not guess.
9. **If it is a virtual instance call, which override does runtime dispatch to?** Ask this question **only after** determining the overload signature.
10. **Verify if needed:** create a minimal example, compile with `javac`, inspect diagnostics and `javap -c`.

When the compiler reports ambiguity and the output differs from expectations, you can use:

```bash
javac -Xdiags:verbose -encoding UTF-8 Example.java
```

`Example.java` here is an illustrative filename and must be replaced with the actual file. `-Xdiags:verbose` helps provide additional diagnostic information in `javac` versions that support it. **There is no way to run an ambiguity example that failed compilation** before fixing the error, and specific error message syntax may vary by JDK.

## 15. Self-check exercises

### Exercise 1: Variable type or value?

```java
static void p(Object x) { System.out.println("O"); }
static void p(String x) { System.out.println("S"); }

Object x = "abc";
p(x);
p((String) x);
```

Answer: `O` then `S`. The cast in the second call changes the static type of the argument to `String`. The illustrative snippet needs the method declarations placed inside a class and the calls inside a method.

### Exercise 2: Widening, boxing, varargs

With the overloads `number(long)`, `number(Integer)`, `number(int...)` from the runnable file:

```java
number(3);
Integer i = 3;
number(i);
number(3, 4);
```

Answer: `long`, `Integer`, `int... 2`. The first call is chosen in the strict phase; the second matches `Integer`; the third must use variable arity.

### Exercise 3: Are these two overloads ambiguous?

```java
static void f(String x) {}
static void f(Integer x) {}

// f(null);       // Ambiguous error.
f((String) null); // Valid.
```

Answer: `String` and `Integer` have no subtype relationship with each other, so `null` does not identify a most specific method. Casting to `String` selects one overload.

### Exercise 4: Overloading or overriding?

```java
Parent p = new Child();
p.show("hello");
((Child) p).show("hello");
```

Answer: the first call selects **`show(Object)` at compile time**, and then runtime executes **`Child.show(Object)`**; the second call selects **`show(String)`** due to the static receiver `Child`.

### Exercise 5: Differences in generic view

A variable `Collection<String> c = new ArrayList<>();` and a variable `List<String> l = new ArrayList<>();` are passed to two overloads `inspect(Collection<?>)` and `inspect(List<?>)`. Answer: `inspect(c)` chooses `Collection<?>`, `inspect(l)` chooses `List<?>`. Do not rely on both having runtime class `ArrayList`.

### Exercise 6: State the limits of the three-phase approach

If a call contains a lambda, generic inference, or a method reference, can the formula "widening > boxing > varargs" be applied mechanically? Answer: **No**. The three phases remain the core structure, but which candidates are valid and which method is most specific are also governed by type inference, functional interface, and target typing rules.

## 16. Conclusion and authoritative sources

**Overload resolution is a compile-time decision**, based on declarations visible from **static types** and Java's method applicability rules. The rules are not simply "the most similar type": `javac` checks strict invocation, loose invocation, and variable arity in order, and then chooses the most specific method in the successful phase. **Override dispatch is a separate runtime mechanism** for virtual instance calls with **the chosen signature**.

Authoritative technical sources:

- [Java Language Specification, Java SE 21 — `15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12): determining the class/interface to search, applicability phases, choosing the most specific method, and runtime invocation.
- [Java Language Specification, Java SE 21 — `5.3 Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.3): valid type conversions when invoking a method.
- [Java Language Specification, Java SE 21 — `8.4 Method Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4): signatures, overloading, overriding, and declaration restrictions.
- [Java Language Specification, Java SE 21 — `18 Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html): type inference for generics and interaction with overloading.
- [Oracle JDK 21 — javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): using the compiler and diagnostic options when verifying.

When unsure why Java chooses an overload, **write down the static types, the candidate set, the winning applicability phase, and the most specific relationship**, and only then consider runtime overriding. That explanation helps both code readers and debuggers reach conclusions consistent with `javac`.