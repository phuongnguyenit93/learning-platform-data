# Prerequisites and Learning Sequence for Generics in Java Core

This lesson is a **learning map and self-assessment** for beginners to Java Generics. Instead of memorizing `<T>`, `? extends T`, and `? super T` syntax piecemeal, you will start from the required prerequisites, progress through lessons in dependency order, then build a capstone program and verify your mastery.

Generics help the compiler verify **relationships between types** in data structures and APIs. The learning goal is not writing lots of angle brackets, but **reading signatures**, **predicting whether a statement will compile**, and **knowing the limits of runtime type guarantees**.

The lesson uses **Java 17+**; you can practice with just the JDK and a regular editor—no Spring, Hibernate, Maven, JUnit, or external libraries needed. If you are already comfortable with core Java, use the prerequisite check to skip stages you have already mastered.

## 1. Target Outcomes and How to Use This Roadmap

Completing the roadmap means you can independently do the following:

1. State the difference between **the static type of a variable**, **the actual runtime class of an object**, and **the type arguments** known to the compiler.
2. Read and write a `Box<T>` class, a `Store<K,V>` interface, and a `static <T> T first(List<T>)` method.
3. Distinguish **type parameter**, **type variable**, **type argument**, **parameterized type**, **raw type**, and **wildcard** using your own examples.
4. Predict valid `add`, `get`, and `set` calls on `List<T>` and understand why `List<Integer>` is not automatically a `List<Number>`.
5. Choose `? extends T` for a read source and `? super T` for a write destination when **data flow is strictly one-directional**.
6. Keep a named `T` when an API needs to link types across **multiple positions** (inputs, results, or two-way read–write operations).
7. Explain type erasure, raw/unchecked warnings, and why a `ClassCastException` may appear only when a value is used.
8. Read common standard-library generic signatures and design a method safe enough that callers do not have to cast.
9. Know when a **concrete type, an interface, or a runtime check** is needed instead of creating unnecessary generic abstractions.

A lesson is not considered “learned” simply because you finished reading an example. **Predict the outcome before running**, explain accurately why the compiler accepts or rejects it, and then modify a variant yourself to prove you understand the rule.

## 2. Prerequisite Check Before Studying

| Required Knowledge | Self-Check | Minimum Understanding Needed |
| --- | --- | --- |
| Reference types and objects | `Number n = Integer.valueOf(5);` | The variable has static type `Number`; the object has runtime class `Integer`. |
| Primitives and wrappers | How does `int` differ from `Integer`? | Generics use reference type arguments; boxing/unboxing can occur. |
| `Object` and casting | `Object x = 42; String s = (String) x;` | A cast may compile yet fail with `ClassCastException` at runtime. |
| Classes and interfaces | `Dog extends Animal`, `implements Runnable` | Distinguish subtyping, inheritance, and interface contracts. |
| Overriding and overloading | `Animal a = new Dog(); a.sound();` | Runtime dispatch uses the override; overload selection happens mainly at compile time. |
| Basic collections | `List`, `Set`, `Map`, `add`, `get` | Know that `List` stores by position and `Map` by key; understand that mutability depends on implementation. |
| Compile vs. runtime | How does an `incompatible types` error differ from `ClassCastException`? | Compile-time errors prevent producing code; exceptions occur when an operation executes. |
| Method signatures | Where do return types and parameter types sit? | Ability to read generic signatures based on ordinary method structure. |

If you are unsure about the third column, review Java Core first. In particular, if you are unfamiliar with `List.of` and `ArrayList`, remember: `List.of(...)` returns an unmodifiable list; `new ArrayList<>(...)` normally creates a list where elements can be added or replaced. This is a runtime difference in mutability, **not** a difference in generic type arguments.

### Things Not Required Yet

You do not need deep knowledge of lambdas, Streams, reflection, class loaders, AspectJ, or frameworks before learning generic classes and methods. `Function<T,R>` or reflection will appear in the advanced API-reading stage; only add what is necessary when you reach that stage.

## 3. Stage Dependency Diagram

~~~text
JAVA FOUNDATIONS
Static/runtime types ── Object/cast ── class/interface
           │                  │
           └──── Collection/Method ─────┐
                                        ▼
STAGE 1: Why generics?  List<String> vs List<Object>
                                        ▼
STAGE 2: Type parameter, type argument, generic class/interface
                                        ▼
STAGE 3: Generic method, inference, bounded type variable
                                        ▼
STAGE 4: Invariance, wildcard, PECS, read/write relationship
                                        ▼
STAGE 5: Type erasure, raw type, warnings, runtime boundaries
                                        ▼
STAGE 6: Reading JDK signatures and API design decisions
                                        ▼
STAGE 7: Mini-project, regression tests, self-assessment
~~~

One **stage** does not correspond to a fixed day of study. Move to the next stage once you can produce the deliverables and pass the checks of the previous stage; if you get stuck on wildcards, revisit **subtyping and invariant generic collections** rather than trying to memorize the PECS slogan.

## 4. Stage 1 — Why Is a Type Contract Needed?

**Goal:** recognize the problem when an API only returns `Object` or a collection lacks a type constraint.

Practice tasks:
- Create a `List<Object>` containing `"Java"` and `17`. Read the first element by casting to `String`; identify why that cast succeeds.
- Read the second element as `String`; predict the exception. Then fix it with `List<String>` so the compiler rejects `add(17)` at compile time.
- Distinguish **a generic collection with type argument `Object`** from **a raw collection `List`**: neither enforces the “String-only” contract, yet raw `List` also bypasses generic checking on certain operations.

Question to answer: “Did the program have a type bug when inserting the data, or only at the cast when using it? Which declaration tells the compiler the rule that must be enforced?”

**Stage pass criterion:** write two tests yourself (one compile error, one runtime exception) and pinpoint the operation causing each.

For beginners, this is the crucial lesson on **motivation for using Generics**. You do not need to dive into bytecode at this stage; just see that accurately describing types in an API moves many errors to an earlier phase.

## 5. Stage 2 — The Language of Generic Types

**Goal:** understand signatures before combining multiple mechanisms. Classify each component below:

~~~java
final class Box<T> {
    private final T value;

    Box(T value) { this.value = value; }

    T get() { return value; }
}

// From a calling method:
// Box<String> box = new Box<>("Java");
~~~

- `T` in `class Box<T>`: declared **type parameter**.
- Occurrences of `T` in the field, constructor, and return type: referenced **type variable**.
- `String` in `Box<String>`: concrete **type argument**.
- `Box<String>`: a **parameterized type**.
- `new Box<>()`: **diamond**, the compiler infers the type argument from context; not raw instantiation.
- `Box` without type arguments in a type usage position: may be a **raw type** in that context, weakening type checking.
- `Box<?>`: a parameterized type with a **wildcard** for an unknown concrete type argument, different from raw `Box`.

Practice tasks:
1. Write `Pair<K,V>`, test `Pair<String,Integer>` and `Pair<Integer,String>`.
2. Write an interface `Formatter<T>` with `String format(T value)` and an implementation accepting `Integer`.
3. Label which parts are type parameter names and which are arguments in `Map<String,List<Integer>>`.
4. Explain why `List<int>` is invalid whereas `List<Integer>` is valid.

**Stage pass criterion:** read both type arguments accurately in a nested parameterized type and do not confuse a class's `T` scope with an object's actual runtime type.

## 6. Stage 3 — Generic Methods, Type Inference, and Bounds

**Goal:** understand when a method needs **a type parameter of its own**.

~~~java
static <T> T last(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("empty");
    }
    return values.get(values.size() - 1);
}
~~~

`<T>` appears **before the return type** and states that the result has the same element type as the input list. The compiler can infer `T` from the argument and call context. If a `static` method is inside a generic class, it must still declare any type variables it uses itself rather than automatically borrowing the class's instance `T`.

Practice tasks:
- Call `last(List.of("A","B"))` and `last(List.of(10,20))`. Predict the static type and return value.
- Try `String invalid = last(List.of(1,2));` and observe the compiler error.
- Try the method `static <T extends Number> double twice(T x)` using `doubleValue()`.
- Compare a generic method with a method taking `Object` and returning `Object`: which method **preserves the type relationship** for callers?

**Stage pass criterion:** explain why `<T>` syntax is required in the declaration and why `T extends Number` enables calling `Number` methods. Do not equate **generic bounds** with declaring class inheritance.

## 7. Stage 4 — Invariance, Wildcards, and Data Flow

This is usually the stage requiring the most call-site practice. The fact that `Integer extends Number` does **not** make `List<Integer> extends List<Number>`. If direct assignment were possible, an API receiving `List<Number>` could add a `Double` to a `List<Integer>`, breaking the caller's data contract.

Choose a signature based on the **role** of the collection:

| Purpose | Suggested Signature | Safe Operations |
| --- | --- | --- |
| Element type does not matter | `List<?>` | Check size, read as `Object`; cannot arbitrarily add non-null values. |
| Source read only as `Number` | `List<? extends Number>` | Read `Number` from `List<Integer>`/`List<Double>`. |
| Destination accepting `Integer` | `List<? super Integer>` | Add `Integer` into `List<Integer>`/`List<Number>`/`List<Object>`. |
| Both reading and writing the same type | `List<T>` | Retrieve `T` and write `T` back into the same list when the implementation permits. |
| One-way source/destination transfer | `List<? extends T>` and `List<? super T>` | Copy `T` values in the producer → consumer direction. |

The mnemonic **PECS (Producer Extends, Consumer Super)** is only a guide for picking the right form when data flows one way; it does **not** recommend putting wildcards on every collection.

Practice tasks:
- Write a sum function that accepts both `List<Integer>` and `List<Double>`, reading elements only.
- Write a function that adds `Integer` to destination `List<Number>` and `List<Object>`.
- Write a `copyInto` method with a shared `T` for source and destination, using wildcards in the proper directions.
- Compare with a **two-way value swap** between two `List<T>` instances; explain why two independent `List<?>` parameters do not directly allow cross-swapping elements.

**Stage pass criterion:** for every compiler error on `add/get`, pinpoint “what could the actual target type be?” instead of mechanically reciting “extends is read-only, super is write-only”.

### Note That Collection Operations Must Still Be Permitted at Runtime

`List<? super Integer>` permits calling `add(1)` according to **the type system**, yet if the object is an unmodifiable list, the operation can still throw `UnsupportedOperationException`. Generics do not describe the mutability of every implementation.

## 8. Stage 5 — Erasure and Runtime Safety Boundaries

**Goal:** understand what the compiler protects, what the JVM can check, and when separate validation is needed.

~~~text
List<String> (compile-time contract)
       │ checks add/get against String
       ▼
Runtime class is usually just ArrayList
       │ raw/unchecked aliases can break the invariant
       ▼
Typed read / inserted checkcast
       └── can throw ClassCastException
~~~

Rules to prove to yourself:
- Unbounded `T` usually erases to `Object`; `T extends Number` erases to `Number`.
- Two `ArrayList` instances created with `new ArrayList<String>()` and `new ArrayList<Integer>()` normally share the same runtime class.
- `instanceof List<?>` checks runtime `List`; `instanceof List<String>` cannot be used to verify specific type arguments from an `Object` variable.
- You cannot directly create `new T()`, `new T[10]`, or `new List<String>[10]` in the ordinary way.
- Raw `List` or unchecked casts can allow wrong-type data to exist **before** a typed read triggers `ClassCastException`.
- Generic types do not automatically enforce null policies, schema validity, or access permissions.

Practice tasks:
1. Use `-Xlint:rawtypes,unchecked` to observe warnings from a raw alias intentionally created in a test file.
2. Clearly separate **the wrong write** and **the read as `String`** in a test; explain why compile-time warnings do not block the write automatically.
3. If receiving a `List<?>` from an untrusted source, check each element with `instanceof String` and build a typed copy. Do not treat `(List<String>) unknown` as a “validator”.
4. Contrast with array covariance: an `Object[]` alias to a `String[]` rejects `Integer` with `ArrayStoreException` right at the write site, unlike many generic collection cases.

**Stage pass criterion:** trace a `ClassCastException` by **dataflow** and know how to prevent it at the boundary instead of just adding a `catch` at the end of the pipeline.

## 9. Stage 6 — Reading JDK APIs and Design Choices

Read standard API signatures **one parameter at a time**, rather than just copying examples:

| API to Read | Identify |
| --- | --- |
| `List<E>.add(E)`, `List<E>.get(int)` | What does `E` accept and return? |
| `Map<K,V>.put(K,V)`, `entrySet()` | How do `K`/`V` describe the key–value relationship? |
| `Optional<T>.map(Function<? super T,? extends U>)` | At which step does `T` turn into `U` via the function? |
| `Collections.copy(List<? super T>,List<? extends T>)` | Destination receives, source supplies `T`; why must the destination already have enough elements? |
| `Comparator<? super T>`, `Comparable<? super T>` | Why can a supertype's comparator be used? |
| `Stream.map` and `Stream.flatMap` | How do a single `R` and a `Stream<R>` differ? |

A practical API note: `Collections.copy` **overwrites by index** rather than calling `addAll` at the end; the destination must already be large enough. Reading generic signatures accurately is **not enough** if you overlook mutability and data contracts.

Practice tasks:
- Take the real signatures of two JDK APIs and **mark where `T` is consumed and where `R` is produced**.
- Read a pipeline `Stream<String> → map(String::length) → Stream<Integer> → toList()` and predict the type at each step.
- Compare `print(Object)` with `<T> void print(T)`: if it only converts any value to `String` and has no other type relationship, why might `T` be unnecessary?

**Stage pass criterion:** explain **signatures before running them**, while stating assumptions about nulls, empty collections, mutability, and exception behavior.

## 10. Stage 7 — Capstone Exercise Connecting Concepts

The goal of the capstone is **not repeating a series of isolated Box/PECS demos**, but purposefully connecting: a generic record, a generic method with input→output linkage, a one-way data copy, an output transformation, and observing runtime classes.

Save as **GenericsRoadmapDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.function.Function;

public class GenericsRoadmapDemo {
    record Attempt<T>(String topic, T value) {}

    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("empty");
        }
        return values.get(0);
    }

    static <T> void copyInto(
            List<? extends T> source,
            List<? super T> target) {
        for (T item : source) {
            target.add(item);
        }
    }

    static <T, R> List<R> transform(
            Collection<? extends T> source,
            Function<? super T, ? extends R> mapper) {
        List<R> output = new ArrayList<>();
        for (T item : source) {
            output.add(mapper.apply(item));
        }
        return output;
    }

    public static void main(String[] args) {
        Attempt<List<String>> lesson = new Attempt<>(
                "syntax", List.of("Type", "Bound")
        );

        System.out.println("first=" + first(lesson.value()));

        List<CharSequence> copied = new ArrayList<>();
        copyInto(lesson.value(), copied);
        System.out.println("copied=" + copied);

        List<Integer> sizes = transform(
                copied, CharSequence::length
        );
        System.out.println("lengths=" + sizes);

        System.out.println(
                "sameClass=" +
                (new ArrayList<String>().getClass()
                        == new ArrayList<Integer>().getClass())
        );
    }
}
~~~

Compile and run with Java 17:

~~~bash
javac --release 17 -Xlint:all GenericsRoadmapDemo.java
java GenericsRoadmapDemo
~~~

Stdout:

~~~text
first=Type
copied=[Type, Bound]
lengths=[4, 5]
sameClass=true
~~~

### Explaining the Type Flow

1. `Attempt<T>` takes `List<String>` as `T`, so `lesson.value()` has type `List<String>`, not `Object`.
2. `first` receives `List<String>`, so `T` is inferred as `String` and returns `String`.
3. `copyInto` takes source `List<String>` and destination `List<CharSequence>` following PECS, copying the two elements without requiring `List<String>` to be a `List<CharSequence>`.
4. `transform` receives `CharSequence` elements, applies `CharSequence::length` to each element, and builds a new `List<Integer>` without modifying the source.
5. Comparing `getClass` only shows that two `ArrayList` instances share the same runtime class; it does **not** prove the variables' type arguments are the same.

### Variants to Verify Mastery

- Replace `List<CharSequence> copied` with `List<Object>` and explain why `copyInto` can still add `String`; replace with `List<Integer>` and explain why no valid `T` allows that copy.
- Replace `CharSequence::length` with a function returning `Boolean`, and predict what type `List<R>` becomes.
- Replace the destination list with `List.of(...)` and explain the difference between *compiling* and *failing when calling `add`*.
- Pass an empty list to `first` and identify the exception without calling it a “Generics bug”.
- Create a raw alias in a **separate test file** to see how a typed read can fail late; do not put raw aliases into production examples.

## 11. Stage-by-Stage Competency Matrix

| Stage | Capability to Demonstrate Without Looking at Solutions | Proof of Completion |
| --- | --- | --- |
| Prep | Explain variable type vs. runtime class and `Object`/cast | Distinguish a compile error from a runtime exception |
| 1 | Identify the need for typed collection contracts | Properly convert a casted `List<Object>` to `List<String>` |
| 2 | Read `T`/`K`/`V` and parameterized types | Correctly declare generic `Box`/`Pair`/interfaces |
| 3 | Write a generic method whose return depends on input | No casts needed at callers; explicit empty-input policy |
| 4 | Choose wildcards based on producer/consumer | Copy `List<Integer>` to `List<Number>` with no unchecked cast |
| 5 | Explain erasure and heap pollution conditions | Accurately predict which operation triggers CCE |
| 6 | Read JDK signatures with wildcards and mappers | Identify `T`, `R`, read/write direction, and output type |
| 7 | Design and verify a small API | Runnable example with outputs and edge cases predicted beforehand |

If you still make mistakes at Stage 4, go back to **invariance and subtype relationships**. If you make mistakes at Stage 5, separate **compile-time generic metadata** from **runtime object classes**. If you understand the theory yet cannot compile Stage 7, try writing each method with explicit types first before assembling the whole program.

## 12. Comprehensive Questions and Short Answers

**Question 1.** How do `Box<T>` and `Box<String>` differ?

**Answer:** `<T>` in the class declaration declares the type parameter; `String` is the type argument at the usage site, forming the parameterized type `Box<String>`.

**Question 2.** Is `List<Integer>` a subtype of `List<Number>`?

**Answer:** No. This generic parameterization is invariant; use `? extends Number` when reading from different numeric lists.

**Question 3.** Why does `static <T> T identity(T value)` preserve type information better than `Object identity(Object value)`?

**Answer:** The same `T` connects the call's input type and result type; the caller receives the compiler-inferred type, usually without casting.

**Question 4.** For `List<? super Integer>`, why is `add(1)` valid while `Integer x = get(0)` is not guaranteed?

**Answer:** The actual type argument may be `Integer`, `Number`, or `Object`. You can write `Integer`; reading out only guarantees `Object`.

**Question 5.** Is `List<?>` the same as raw `List`?

**Answer:** No. `List<?>` keeps an unknown captured element type, and the compiler forbids writing arbitrary non-null elements. Raw `List` loses many generic checks and can generate unchecked warnings.

**Question 6.** Are `String[]` and `List<String>` the same regarding runtime element type checks?

**Answer:** No. `String[]` has a reified runtime component type `String` and array-store checks. An ordinary `ArrayList<String>` does not have a dedicated `String` runtime token checked on every `add`.

**Question 7.** When should you use a generic method vs. a concrete type?

**Answer:** Use a named type parameter when there is a type relationship to preserve across inputs/outputs; use a concrete type when logic pertains only to a single entity or a fixed contract. Do not add `<T>` just to look “generic”.

**Question 8.** When raw code inserts an `Integer` into a `List<String>`, when does `ClassCastException` occur?

**Answer:** Not necessarily on the raw `add`. It can occur when a typed read/usage causes the JVM to cast the `Integer` to `String`; reading it as `Object` may still succeed.

**Question 9.** Does type erasure mean Reflection cannot read any generic declarations?

**Answer:** No. Field/method/supertype metadata can retain `Signature` attributes for Reflection to inspect declarations. However, the generic type argument of an ordinary `ArrayList` object is not automatically reified.

**Question 10.** Does the destination of `Collections.copy(dest,src)` automatically grow if the source is longer?

**Answer:** No. That API overwrites by index and requires the destination to already be large enough; unlike `addAll`.

## 13. Organizing Your Own Practice Sessions

A repeatable learning loop for each stage:

1. **Predict:** write down the expression's type and compile/run status before using the IDE.
2. **Run:** use `javac --release 17` to verify; enable `-Xlint:rawtypes,unchecked` in legacy experiments.
3. **Explain:** write 2–3 sentences about the type mechanism and when checking happens.
4. **Vary:** change a type argument, wildcard, or method return type to see what changes.
5. **Compare:** check the same concept in a JDK signature or an invalid-data test.
6. **Self-assess:** only move past a stage when you can explain a passing case, a compiler-rejected case, and a meaningful edge case.

No fixed schedule or standard hour count is required. If you are already strong in collections and OOP, you can move quickly through the early stages; wildcards and erasure are worth spending extra time on to write your own tests.

### Mistakes to Catch Yourself Before Looking at Hints

- Writing `List<int>` instead of `List<Integer>`.
- Using `List<Object>` where you actually want to accept `List<String>` and `List<Integer>` for reading only.
- Writing `static T method(T x)` in a generic class when `T` has not been declared on the static method.
- Getting a value from `List<? super T>` and treating it directly as `T`.
- Adding an arbitrary `T` to `List<? extends T>`.
- Using raw `List` and suppressing warnings instead of fixing variance.
- Thinking `new T()` is valid because the method has `<T>`.
- Confusing `List.of` with a modifiable `ArrayList`.
- Using an unchecked cast as external data validation.

## 14. Syntax Quick Reference at the Right Moment

| Syntax | When to Review |
| --- | --- |
| `class Box<T>`, `interface Store<K,V>` | Stage 2: generic type declaration |
| `Box<String>`, `Map<String,Integer>` | Stage 2: actual type arguments |
| `static <T> T first(List<T>)` | Stage 3: generic method and input/output relationship |
| `<T extends Number>` | Stage 3: upper bound to call `Number` members |
| `List<?>` | Stage 4: only inspecting a list of unknown type |
| `List<? extends Number>` | Stage 4: producer and invariance |
| `List<? super Integer>` | Stage 4: consumer and invariance |
| `Function<? super T,? extends R>` | Stages 6–7: type-transforming callback |
| `Class<T>` and `Supplier<T>` | After Stage 5: needing a runtime class token or factory |
| `@SafeVarargs` / generic array constraints | Advanced, after understanding erasure and heap pollution |

## 15. Where to Go After This Chapter

Once you can complete the mini-project and explain every self-check question, dive deeper in order according to the real problems you encounter:

- Generic inheritance, F-bounded types, and bridge methods if you design class hierarchies.
- Wildcard capture and advanced bounded wildcards if APIs need multiple sources/destinations or internal read–write operations.
- Generic varargs, heap pollution, and `@SafeVarargs` if you build varargs utilities.
- `Type`, `ParameterizedType`, and generic Reflection if you need to read declaration metadata.
- `Function`, `Predicate`, `Stream.map`, and `flatMap` if you build data transformation pipelines.
- Binary compatibility of public generic APIs if you publish libraries and evolve bounds.

For each topic, keep asking three questions: **What type relationship does the compiler know? What does the JVM still check? What is guaranteed to the API caller without casting?**

That is the foundation for moving from *using generics* to *designing purposeful, safe, and maintainable generic APIs*.