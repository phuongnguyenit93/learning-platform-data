# The Diamond Operator `<>` and How It Differs from Raw Types in Java

## 1. The Problem to Solve

Generics allow the compiler to check element types in collections or general-purpose classes. When instantiating a generic object, Java has two ways of writing it that look similar yet **differ in type safety**:

```java
List<String> names = new ArrayList<>(); // Diamond: the compiler infers String.
List<String> old   = new ArrayList();   // Raw type: omits type parameters, unchecked warning.
```

On the first line, `<>` is the **diamond operator**: the list is instantiated with its type parameter inferred from context (`String`). On the second line, `new ArrayList()` is a **raw type**: the constructor is called via the non-parameterized `ArrayList` type. That line can still compile to support legacy Java code compatibility, but it loses part of the type checking and produces warnings about unchecked conversions.

Goals after this lesson:

- Clearly distinguish `List<String>`, `new ArrayList<String>()`, `new ArrayList<>()`, `new ArrayList()`, and `List<?>`.
- Understand that `<>` infers types **at compile time** from context such as variable declarations, method parameters, or return types.
- See why raw types produce `rawtypes` and `unchecked` warnings and risk **heap pollution / ClassCastException**.
- Know how to use the diamond in Java 17+ code, distinguish cases with a target type from `var` declarations, and gradually migrate legacy code to type-safe APIs.

`<>` was introduced in Java 7 to reduce repeating type parameters in `new` expressions. The diamond still follows all rules of generics and does not turn Java into a dynamically typed language.

## 2. Five Easily Confused Forms

| Syntax | Meaning | Generic Type Checking? |
| --- | --- | --- |
| `List<String> a` | Variable with element type `String` | Yes |
| `new ArrayList<String>()` | Instantiation explicitly specifying `String` | Yes |
| `new ArrayList<>()` | Instantiation letting the compiler **infer** the type parameter | Yes |
| `new ArrayList()` | Uses a **raw type**, completely omitting type parameters | Incomplete; may emit warnings |
| `List<?> any` | List of an unknown type, yet still a **parameterized type** | Yes; restricts write operations to protect type safety |

The first two lines below are equivalent regarding the generic contract visible through the variable `names`:

```java
// These statements can be placed inside a Java method.
List<String> names1 = new ArrayList<String>();
List<String> names2 = new ArrayList<>();
names1.add("Lan");
names2.add("Minh");
// names2.add(42); // Compilation error because List<String> does not accept Integer.
```

The diamond is **not** a shorthand that drops type parameters like a raw type. `new ArrayList<>()` asks the compiler to solve type parameter inference for the `ArrayList<E>` class; the result is still checked as a generic expression. By contrast, `new ArrayList()` opts into raw `ArrayList`, with generic signatures viewed in erased form.

One point worth remembering: both the **left-hand side** type and the **right-hand side** type matter.

```java
List<String> safe = new ArrayList<>(); // Both sides preserve the String constraint.
List<String> weak = new ArrayList();   // Unchecked assignment from raw to List<String>.
List raw = new ArrayList<>();          // Raw variable still allows unchecked add calls.
```

On the last line, the diamond in the `new` expression **cannot make the `raw` variable safe**: code using that variable only knows it as a raw `List`. That is why you must check variable signatures, parameters, and return types across the entire data flow.

## 3. How Does the Diamond Work?

A generic type declares **type parameters**, such as `ArrayList<E>` or `Map<K,V>`. In an instantiation expression `new ArrayList<>()`, `<>` tells the compiler to infer `E` from available constraints.

### 3.1. Inference from a Variable's Target Type

```java
List<String> letters = new ArrayList<>();
Set<Long> ids = new HashSet<>();
Map<String, Integer> ages = new HashMap<>();
```

The compiler checks whether the constructor can produce an expression compatible with `List<String>`, `Set<Long>`, and `Map<String,Integer>`. Type parameters on the right side usually do not need to be repeated because the left side provides the constraint.

Note: the diamond does not mean the compiler mechanically copies the exact letters from the left-hand side. Type inference also depends on the constructor, passed argument types, usage, and Java's compatibility constraints.

### 3.2. Inference from a Method Parameter

```java
// Snippet inside a Java class, assuming java.util.* is imported.
static void acceptNames(List<String> names) {
    System.out.println(names.size());
}

// Inside another method:
acceptNames(new ArrayList<>());
```

The call has a target context of `List<String>` from the signature of `acceptNames`, so `new ArrayList<>()` can be inferred accordingly. Assigning to an intermediate variable is not necessary.

### 3.3. Inference from a Return Type

```java
static Map<String, List<Integer>> emptyGrades() {
    return new HashMap<>();
}
```

The `return` context supplies the target type `Map<String,List<Integer>>`; the compiler verifies the returned expression. For a generic method, method-call inference and constructor inference can interact, though they are two distinct syntax rules.

### 3.4. Nested Generics: Concise Yet Type-Clear

```java
Map<String, List<Integer>> grades = new LinkedHashMap<>();
grades.put("Lan", new ArrayList<>());
grades.get("Lan").add(8);
grades.get("Lan").add(9);
// grades holds data corresponding to "Lan" -> [8, 9].
```

The compiler infers `Map<String,List<Integer>>` for `LinkedHashMap<>` and can infer `ArrayList<Integer>` for the `put` call because the second parameter must be compatible with `List<Integer>`. The generics system continues to check the depth of nested collections.

### 3.5. Incorporating Constructor Arguments into Inference

```java
List<String> names = new ArrayList<>(List.of("Lan", "Mai"));
Map<String, Integer> ages =
        new HashMap<>(Map.of("Lan", 20, "Mai", 21));
```

The compiler combines the target type and constructor arguments. `List.of` and `Map.of` in the example are **generic static factory methods**; they infer their own method type parameters. They **do not use the diamond**; the diamond is syntax tied to object instantiation with `new`.

## 4. Diamond and `var`: When There Is No Explicit Target Type

Since Java 10, `var` lets the compiler infer the **local variable** type from the initializer expression. This creates a different situation from `List<String> names = ...`:

```java
var a = new ArrayList<>();         // a is ArrayList<Object>.
a.add("Java");                     // Valid.
a.add(2026);                       // Also valid because the element type is Object.

var b = new ArrayList<String>();   // b is ArrayList<String>.
b.add("Java");
// b.add(2026);                    // Compilation error.
```

When writing `var a = new ArrayList<>()` without useful data or a target type, the compiler infers the unconstrained type argument as `Object`. This is still a **parameterized type** (`ArrayList<Object>`), **not a raw type** (`ArrayList`). The difference is that an `Object` list can hold various reference types according to its contract, whereas a raw type discards type parameter information and can break the contract of a list declared as `List<String>`.

The preferred way if you want a list of strings with `var`:

```java
var names = new ArrayList<String>();
names.add("Lan");
```

If you want to hide the implementation behind an interface, use an explicit declaration:

```java
List<String> names = new ArrayList<>();
```

The second approach usually makes the API easier to switch from `ArrayList` to another implementation and expresses the requirement to store only `String` right at the declaration.

**Do not assume `var` defaults to `Object` in every case.** For instance, `var names = List.of("Lan")` usually infers `List<String>` from the return type and argument of the generic factory `List.of`. The specific issue is `new ArrayList<>()` having no concrete enough constraint when placed immediately after `var`.

## 5. Raw Types: Compatibility Legacy from Pre-Generics Java

Before Java 5, collections such as `List` and `ArrayList` had no type parameters. When generics arrived, Java kept raw forms so legacy code could continue working:

```java
List legacy = new ArrayList();
legacy.add("hello");
legacy.add(42);
Object item = legacy.get(0);
```

Raw types generally eliminate the compile-time check that an element must be `String`, `Integer`, or a specific type. Later, callers may have to cast from `Object`, risking runtime errors if the actual value is incompatible.

In contrast, the generic version below provides checking before execution:

```java
List<String> messages = new ArrayList<>();
messages.add("hello");
// messages.add(42);       // Error right at compile time.
String item = messages.get(0); // No manual cast needed.
```

### 5.1. Heap Pollution: A Variable Sees the Wrong Type for Its Contents

*Heap pollution* is a situation where a variable of a parameterized type points to data that does not match that type parameter. Raw types are a common path to this problem:

```java
List<String> words = new ArrayList<>();
words.add("Java");

List raw = words;       // Accessing the same object through a raw variable.
raw.add(99);            // Unchecked warning, yet it can run.

String second = words.get(1); // Throws ClassCastException at runtime.
```

The danger is that `words` still has the declared type `List<String>`, yet the raw variable slipped an `Integer` into the same list object. Reading an element through `words.get(1)` causes the compiler to insert the appropriate cast; that cast fails when encountering `Integer`.

When running `javac -Xlint:rawtypes -Xlint:unchecked`, you can see two groups of warnings:

- `[rawtypes]`: declaring or using a generic type in raw form, such as `List raw`.
- `[unchecked]`: an operation where the compiler cannot verify the correctness of type parameters, such as `raw.add(99)` or assigning a raw list to `List<String>`.

Warnings are not a guarantee that the code will automatically fix data. They mark a spot a developer must inspect.

### 5.2. Raw Types on the Right-Hand Side Are Also Dangerous

```java
List<String> names = new ArrayList();  // Unchecked conversion.
names.add("Lan");
```

The compiler may allow the assignment for compatibility with legacy code, but the constructor here does not carry generic information across the expression. The proper way to eliminate the warning is to use `new ArrayList<>()` or `new ArrayList<String>()`. You should not merely add `@SuppressWarnings("unchecked")`, because that annotation does not restore type checking.

### 5.3. Raw Types Bring No Speed or Memory Benefit

Java generics are primarily implemented via **type erasure**: the typical runtime representation shares the same `ArrayList` class for `ArrayList<String>` and `ArrayList<Integer>`. Therefore, raw types are not a performance optimization; choosing raw usually just discards information used for compile-time checking.

```java
boolean sameClass =
    new ArrayList<String>().getClass() == new ArrayList<Integer>().getClass();
// sameClass is true.
```

Type erasure also explains why you cannot use `instanceof List<String>` to verify the `String` argument at runtime. When you need to check whether something is a list, `instanceof List<?>` is a valid check; checking the actual elements must be done separately when needed.

## 6. Do Not Confuse `<>`, `<?>`, and Raw Types

Three forms use angle brackets or omit them with different meanings:

```java
List<String> strings = new ArrayList<>(); // Diamond: infers type on new.
List<?> unknown = strings;               // Wildcard: unknown element type.
List raw = strings;                      // Raw: strips type parameter information.
```

With `List<?>`, the compiler still protects type safety:

```java
Object value = unknown.get(0);  // Valid: read as Object.
// unknown.add("more");         // Compilation error: element type unknown.
// unknown.add(42);             // Compilation error.
unknown.add(null);              // Valid per add signature, if the implementation allows null.
```

Note: `List<?>` does not mean `List<Object>`. With `List<Object>`, you can add any `Object`-compatible reference value, yet you cannot directly assign `List<String>` to `List<Object>` because Java generics are **invariant**:

```java
List<String> names = new ArrayList<>();
List<?> readable = names;       // Valid.
// List<Object> writable = names; // Compilation error.
List<Object> objects = new ArrayList<>();
objects.add("Lan");
objects.add(42);
```

When an API only needs to view/read data of unknown type, `List<?>` is usually better than raw `List`. When an API needs to accept objects of a specific type, express the exact type or use bounded wildcards (`? extends T`, `? super T`) depending on the operation.

| Kind | Reading Elements Out | Adding Elements | What to Remember |
| --- | --- | --- | --- |
| `List<String>` | `String` | `String` | Full type checking. |
| `List<Object>` | `Object` | Any reference object | Still generic, not raw. |
| `List<?>` | `Object` | Cannot add concrete objects; `null` is allowed type-wise | Safe for accessing unknown types. |
| Raw `List` | `Object` | Calls `add` without generic checks, usually with unchecked warnings | Can corrupt the contract of another generic variable. |

## 7. Where Is the Diamond Valid and Where Is It Invalid?

The diamond is an **empty type argument list in a generic class instantiation expression**:

```java
List<String> a = new ArrayList<>(); // Valid.
Map<String, Integer> b = new HashMap<>(); // Valid.
// List<> c = new ArrayList<>();      // Invalid: declaration side must have a type.
// List<String> d = new List<>();     // Invalid: List is an interface, cannot instantiate with new.
```

`<>` cannot be written everywhere generics are used. When declaring a class or method, you must write **type parameter names**:

```java
class Holder<T> {
    private final T value;
    Holder(T value) { this.value = value; }
    T get() { return value; }
}

static <T> List<T> singleton(T item) {
    return new ArrayList<>(List.of(item));
}
```

When calling a generic method, the compiler normally infers types from arguments and context, without using `method<>()` syntax:

```java
List<String> one = singleton("Java");  // Infers T = String.
// List<String> wrong = singleton<> ("Java"); // No diamond here.
List<String> empty = Collections.<String>emptyList(); // Specifies a type witness.
```

Additional conditions and limitations:

1. The diamond is used when **a constructor instantiates a suitable class**; it cannot directly instantiate an interface or abstract class.
2. Generic type parameters only accept **reference types**: `new ArrayList<Integer>()` is valid, while `new ArrayList<int>()` is invalid. Boxing and unboxing help when putting integers into `List<Integer>`.
3. The diamond does not bypass bounds: for example, `NumericBox<T extends Number>` cannot be instantiated as `NumericBox<String>` by using `<>`.
4. Java 7 allowed the diamond with constructors that do not create anonymous classes; since **Java 9**, the diamond can be used with anonymous classes subject to type inference constraints. In modern code, only use the anonymous-class variant if truly needed and you understand its limits; lambdas or named implementations are usually easier to read.
5. Do not rely on the diamond to hide a confusing type: when inference causes errors or hurts clarity, declare the type explicitly on the left, add explicit type arguments on `new`, or simplify nested generic classes.

## 8. Practical Scenario: Improving Legacy APIs Without Losing Safety

Suppose an old function returns a raw `List` from a pre-Java 5 library:

```java
// Illustrating legacy API only.
static List loadLegacy() {
    List data = new ArrayList();
    data.add("Lan");
    data.add("Mai");
    return data;
}
```

The following approach may compile with warnings, yet it **does not prove** every element is a `String`:

```java
List<String> names = loadLegacy(); // Unchecked conversion.
```

A safer checked conversion at the boundary is to accept `Collection<?>`, iterate through each element, verify its type, and put it into a new list:

```java
// Placed inside a class that has imported java.util.*.
static List<String> copyStrings(Collection<?> input) {
    List<String> out = new ArrayList<>();
    for (Object value : input) {
        if (!(value instanceof String s)) {
            throw new IllegalArgumentException("Expected String element");
        }
        out.add(s);
    }
    return out;
}

// List<String> names = copyStrings(loadLegacy());
```

This snippet intentionally rejects `null` as well because `null instanceof String` is `false`. If the data contract permits `null`, handle it explicitly rather than accidentally accepting or skipping it. Creating a new list prevents a raw alias from continuing to insert wrong-typed elements into the checked list itself.

When you control the legacy source code, the best fix is to update the signature directly at its declaration:

```java
static List<String> loadNames() {
    List<String> names = new ArrayList<>();
    names.add("Lan");
    names.add("Mai");
    return names;
}
```

You do not have to erase every old call site in one step; you can build a validating adapter at the boundary, then gradually migrate parameters, return types, and internal variables to generic types.

## 9. Runnable Program: Diamond, `var`, and Raw Type Errors

Create the file **`DiamondVsRaw.java`** as follows. The raw type portion is kept intentionally to illustrate risk; new code should prefer type-safe generics.

```java
import java.util.*;

public class DiamondVsRaw {
    static final class Box<T> {
        private final T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        names.add("Minh");
        System.out.println("typed: " + names);

        Box<Integer> score = new Box<>(9);
        System.out.println("box: " + score.get());

        Map<String, List<Integer>> grades = new LinkedHashMap<>();
        grades.put("Lan", new ArrayList<>());
        grades.get("Lan").add(9);
        System.out.println("map: " + grades);

        var noTarget = new ArrayList<>();
        noTarget.add("text");
        noTarget.add(42);
        System.out.println("inferred: " + noTarget);

        List<String> legacy = new ArrayList<>();
        legacy.add("OK");
        List raw = legacy;
        raw.add(123);
        try {
            String value = legacy.get(1);
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println("raw: ClassCastException");
        }
    }
}
```

Compile on **JDK 17+**; the `-Xlint` option asks the compiler to pinpoint warning locations:

```bash
javac -Xlint:rawtypes -Xlint:unchecked DiamondVsRaw.java
java DiamondVsRaw
```

When running `javac`, the compiler will report `[rawtypes]` at `List raw` and `[unchecked]` at `raw.add(123)`. Full phrasing and line numbering in warnings depend on the compiler version; those are **diagnostics**, not program stdout.

Stdout result of `java DiamondVsRaw` (compiled and tested on JDK 21):

```text
typed: [Lan, Minh]
box: 9
map: {Lan=[9]}
inferred: [text, 42]
raw: ClassCastException
```

Explanation:

- `names` and `score` receive accurate generic constraints. The diamond on `ArrayList<>` and `Box<>` avoids repeating declarations.
- `grades` demonstrates the diamond for `Map<String,List<Integer>>` with values as `ArrayList<Integer>` inferred from the `put` parameter.
- `var noTarget = new ArrayList<>()` creates `ArrayList<Object>` because there is no specific constraint; both strings and numbers boxed into `Integer` are validly added.
- `raw` points to **the exact same object** as `legacy`, so `raw.add(123)` puts an `Integer` into a `List<String>` and causes an issue when reading data. `try/catch` serves as an example printing the error type name so learning is not interrupted by environment-dependent stack traces.

In production code, **eliminate raw aliases**, and never keep catching `ClassCastException` as a routine data-handling solution.

## 10. Common Mistakes

| Symptom | Cause | How to Handle |
| --- | --- | --- |
| `List<String> a = new ArrayList();` emits `unchecked conversion` | Constructor uses raw type | Change to `new ArrayList<>()`. |
| `List raw = new ArrayList<>();` still has `rawtypes` | Variable declaration type is still raw | Write `List<String>`, `List<?>`, or a suitable type. |
| `var xs = new ArrayList<>();` accepts both `String` and `Integer` | Compiler infers `ArrayList<Object>` when no specific target type exists | Use `var xs = new ArrayList<String>()` or `List<String> xs = new ArrayList<>()`. |
| `List<> xs` does not compile | Diamond cannot substitute for the parameter list in a type declaration | Write `List<String>`, `List<?>`, or `List<T>`. |
| `new List<>()` does not compile | `List` is an interface | Instantiate `new ArrayList<>()` or a suitable implementation. |
| `List<Integer> x = new ArrayList<String>();` does not compile | Incompatible type arguments | Align the stored type on both sides. |
| `List<Number> x = new ArrayList<Integer>();` does not compile | Generics are invariant | Choose `List<Number>` on both sides or an appropriate wildcard for reading only. |
| `List<?> xs` cannot `add("a")` | Element type is unknown | Use a concrete type if writing is needed, or design an appropriate `? super T` parameter. |
| `@SuppressWarnings("unchecked")` silences warnings | Only hides diagnostics; does not validate data | Fix the generic declaration or validate/convert at the boundary. |
| `ClassCastException` occurs on `get` even though the list has a generic type | Raw alias or unchecked cast put the wrong element into the list | Trace back the source of heap pollution; remove raw types and add checks where data enters. |

### Quick Selection Rules When Writing New Code

- When a clear target type already exists such as `List<User>` or `Map<String, Long>`: prefer `new ArrayList<>()`, `new HashMap<>()` to avoid repetition.
- When using `var` with an empty generic constructor: consider writing explicit type arguments in the `new` expression; do not assume `<>` infers the exact desired type.
- When handling data of unknown type: use `List<?>`/`Collection<?>` for safe reading; check elements before converting into a typed collection.
- When encountering raw types in legacy code: enable `-Xlint:rawtypes -Xlint:unchecked`, trace warnings, and fix from the API signature if possible.
- Do not introduce raw types to work around generic errors; compile-time errors usually help reveal data-contract conflicts.

## 11. Self-Check Exercises and Guided Solutions

**Exercise 1 — Two constructors:** Why is `List<String> s = new ArrayList<>()` better than `List<String> s = new ArrayList()`? Point out where the compiler has enough information to check `String` and where warnings appear.

**Guidance:** The diamond infers `String` from the target type; the raw constructor drops type parameters and the assignment to `List<String>` is not fully checked.

**Exercise 2 — Raw or not?** Look at two declarations:

```java
var a = new ArrayList<>();
var b = new ArrayList();
```

**Guidance:** `a` is `ArrayList<Object>` (a parameterized type from inference); `b` is raw `ArrayList`. When calling `add` on `b`, the compiler can emit unchecked warnings. Both can accept multiple element types, yet their type-safety mechanisms differ.

**Exercise 3 — Fixing the API:** Given the legacy snippet:

```java
Map cache = new HashMap();
cache.put("answer", 42);
Integer n = (Integer) cache.get("answer");
```

Change it to `Map<String,Integer> cache = new HashMap<>()`, remove the cast, and try calling `cache.put(10, "wrong")`. **Guidance:** the new mistyped `put` line is rejected right at compile time.

**Exercise 4 — A raw alias:** Explain why `List<String>` can still throw `ClassCastException` when reading, even though `add(123)` via that same variable is a compilation error. **Guidance:** another reference in raw form can insert an element violating the contract into the same object; more precisely, generics only protect access paths where the compiler has sufficient type information.

When self-testing, you should be able to distinguish three core ideas: **the diamond infers type parameters**, **raw types drop type parameters for legacy compatibility**, and **wildcards remain type-safe generics for cases where the concrete parameter is unknown**. Understanding these three points helps you read compiler warnings and refactor collection APIs in Java projects without creating hard-to-trace runtime bugs.
