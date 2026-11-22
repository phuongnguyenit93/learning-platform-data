# Why Can't You Overload Solely with `List<String>` and `List<Integer>`? Choosing Alternative API Designs

Suppose a service must process two kinds of lists:

- `List<String>` containing employee names; needs to join the names into a report.
- `List<Integer>` containing scores; needs to sum the scores into a total.

The initial idea is to write two methods with the same name:

~~~java
import java.util.List;

class InvalidProcessor {
    void process(List<String> names) {
        System.out.println(String.join(", ", names));
    }

    void process(List<Integer> scores) {
        System.out.println(scores.stream().mapToInt(Integer::intValue).sum());
    }
}
~~~

**This class intentionally does not compile.** In Java Generics, `List<String>` and `List<Integer>` differ under source-level type-checking rules, but both undergo **type erasure** to `java.util.List` in bytecode. Both methods attempt to have distinct source signatures while sharing the exact same erased parameter list:

~~~text
process(List<String>)    -> process(List)
process(List<Integer>)   -> process(List)
~~~

When two declarations sit in the same class without forming a valid override relationship, the compiler reports a **name clash**. This lesson focuses on the programmer's next step: **choosing an API that matches the business intent instead of trying to bypass the compiler**.

## 1. What the Compiler Actually Needs for Overloading

Overload resolution happens at compile time using method names and parameter types according to Java rules, not by the JVM inspecting elements inside a `List` to pick a branch at runtime.

If both methods return `void`, their hypothetical descriptors would both be:

~~~text
(Ljava/util/List;)V
~~~

`(Ljava/util/List;)` describes a `java.util.List` parameter, and `V` is `void`. The type arguments `String` and `Integer` do not produce two separate erased parameter types. In a class file, generic `Signature` metadata can record type arguments of **valid methods**; it does not allow Java to declare two colliding overloads merely by attaching different generic signatures.

Distinguish three concepts:

| Concept | Example | Impact on the issue |
| --- | --- | --- |
| Generic type argument | `List<String>` differs from `List<Integer>` | Used by the compiler to check elements; both erase to `List`. |
| Overload parameter type | `process(String)` and `process(Integer)` | Two distinct erased parameter types; valid overload. |
| Override | `Parent<T>.save(T)` overridden by `Child extends Parent<String>` with `save(String)` | Compiler can generate a bridge to preserve dispatch, **not** two overloads differing by type arguments. |

**Do not try to fix this** by changing `void` to different return types, renaming variables `names`/`scores`, adding a `<T>` type parameter to one method, or adding `@SuppressWarnings("unchecked")`. None of those create a parameter list distinguishable after erasure.

### Verifying the compile error separately

Save the `InvalidProcessor` code above as **InvalidProcessor.java**, and run:

~~~bash
javac --release 17 InvalidProcessor.java
~~~

Expected result: **`javac` fails**, with a diagnostic mentioning name clash or same erasure. Do not try to paste this file into Section 6's runnable program: it is meant as a **negative compilation test**, not a runtime example.

## 2. Choose One of Four Strategies Based on Actual Need

| Real requirement | Preferred design | Why |
| --- | --- | --- |
| Two **completely different** behaviors | Two meaningful method names, such as `joinNames` and `sumScores` | Names describe the contract and avoid surprising overloads. |
| **One algorithm** usable across element types | One `<T>` method or a method taking `List<?>` | Avoids duplicating logic just to distinguish element types. |
| One shared pipeline, **different per-element behavior** | Generic method accepting `Function`/`Consumer` | Compiler type-checks the callback at each call site. |
| Must keep the **same `process` name**, while inputs are two distinct domain concepts | Two separate wrapper types, e.g., records `Names` and `Scores` | JVM sees two distinct erased parameter classes. |
| Need to **verify** element types when receiving untrusted data | One method paired with `Class<?>`/validator | Runtime token validates data; does not make two `List` overloads valid. |

These are choices about **API contracts**, not mere syntax tricks to get past `javac` errors. Changing a published public signature `process(List...)` to `process(Names)` can be a **breaking change** for existing callers/binaries; evolving a library requires a migration plan, Java-permitted adapter overloads, versioning, and compatibility testing.

## 3. Option A: Name Methods After Business Intent

When the algorithms are inherently different, the clearest code usually has **two distinct names**:

~~~java
static String joinNames(List<String> names) {
    return String.join(", ", names);
}

static int sumScores(List<Integer> scores) {
    return scores.stream().mapToInt(Integer::intValue).sum();
}
~~~

The meanings of `joinNames` and `sumScores` are immediately visible in the API. No casts are needed, and no ambiguous generic method name is overloaded for unrelated operations.

When used:

~~~java
String report = joinNames(List.of("Lan", "Mai"));
int total = sumScores(List.of(5, 7));
~~~

`report` is `"Lan, Mai"`, and `total` is `12`. Because the two methods have different names, there is no risk of an erased-signature collision.

**Trade-off:** If multiple variants actually perform **the same traversal** and differ only in a callback, splitting into many methods can duplicate code. In that case, a shared generic method is usually better.

## 4. Option B: One Generic Method with Passed-In Behavior

A method **that does not need to know `T` concretely** can process `List<T>` using the same algorithm:

~~~java
static <T, R> List<R> mapAll(
        List<? extends T> source,
        java.util.function.Function<? super T, ? extends R> transform) {

    List<R> output = new ArrayList<>();

    for (T item : source) {
        output.add(transform.apply(item));
    }

    return output;
}
~~~

It does **not** create two overloads `mapAll(List<String>)` and `mapAll(List<Integer>)`; this is **one** generic method whose type arguments are inferred by the compiler at each call site.

~~~java
List<Integer> lengths = mapAll(
        List.of("a", "abcd"), String::length
);

List<Integer> squares = mapAll(
        List.of(2, 3), n -> n * n
);
~~~

Result:

~~~text
lengths=[1, 4]
squares=[4, 9]
~~~

At the first call site, the compiler knows the source elements are `String` and the callback returns `Integer`. At the second call site, the elements are `Integer` and the lambda produces `Integer`. The callback uses wildcard bounds `? super T` and `? extends R` to fulfill its roles of consuming `T` and producing `R` as needed.

### Why not make every method generic?

If the body only does `System.out.println(value)` and does not relate the input element type to the return type or another argument, a `List<?>` parameter may suffice. If the business logic truly needs methods available only on `String` or `Integer`, an unbounded `<T>` **does not allow calling `String.length()` or `Number.intValue()` on arbitrary `T`**. In that case, choose a callback, an appropriate bound, or separate methods by business intent.

**Conclusion:** a generic method is only good when it accurately expresses a **shared algorithmic structure**, not as a trick to dodge a name clash.

## 5. Option C: Wrapper Types Enable Valid Overloads and Clarify Domain Data

Sometimes a single entry point named `process` is designed to accept **two kinds of requests with distinct domain meanings**. You can use dedicated records:

~~~java
record Names(List<String> items) {}
record Scores(List<Integer> items) {}

static String process(Names request) {
    return String.join("|", request.items());
}

static String process(Scores request) {
    int total = 0;
    for (int value : request.items()) {
        total += value;
    }
    return "scores=" + total;
}
~~~

The two methods have parameter types `Names` and `Scores`. These are **two separate runtime classes**, so their erased descriptors also differ. The overload is valid without relying on runtime generic arguments.

At call sites:

~~~java
process(new Names(List.of("Lan", "Mai")));
process(new Scores(List.of(5, 7)));
~~~

The compiler selects the overload from the actual class of the argument. Because the records have no subtype relationship with each other, a bare call `process(null)` **can be ambiguous**: both overloads accept `null` with neither being more specific. That is a general API issue when overloading with two sibling reference types, **not** an erasure error.

### Records are not automatically deep-immutable

`record Names(List<String> items)` has a final reference field (*final component*), yet a mutable `List` can still be modified through an external alias. If the API contract requires an independent unmodifiable snapshot, use a **compact constructor**:

~~~java
record Names(List<String> items) {
    Names {
        items = List.copyOf(items);
    }
}
~~~

`List.copyOf` creates an unmodifiable list and rejects `null` elements; this is a *shallow copy* of the element references. The record contract protects the collection structure, though it does not automatically make mutable element objects immutable.

**When to choose wrappers:** when the input type carries domain rules, metadata, or validation that adds real value. Do not introduce two extra classes merely to avoid naming a small helper cleanly like `joinNames`/`sumScores`.

## 6. Complete Java 17 Program: Comparing Wrappers, Callbacks, and Runtime Validation

Save as **ListOverloadApiDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class ListOverloadApiDemo {
    record Names(List<String> items) {
        Names {
            items = List.copyOf(items);
        }
    }

    record Scores(List<Integer> items) {
        Scores {
            items = List.copyOf(items);
        }
    }

    static String process(Names batch) {
        return "names=" + String.join("|", batch.items());
    }

    static String process(Scores batch) {
        int total = 0;
        for (int score : batch.items()) {
            total += score;
        }
        return "scores=" + total;
    }

    static <T, R> List<R> mapAll(
            List<? extends T> source,
            Function<? super T, ? extends R> transform) {

        List<R> output = new ArrayList<>();
        for (T value : source) {
            output.add(transform.apply(value));
        }
        return output;
    }

    static boolean allElements(
            List<?> values, Class<?> elementType) {

        for (Object value : values) {
            if (!elementType.isInstance(value)) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        System.out.println(
                process(new Names(List.of("Lan", "Mai")))
        );

        System.out.println(
                process(new Scores(List.of(5, 7)))
        );

        System.out.println(
                "lengths=" + mapAll(
                        List.of("a", "abcd"),
                        String::length
                )
        );

        System.out.println(
                "squares=" + mapAll(
                        List.of(2, 3),
                        number -> number * number
                )
        );

        System.out.println(
                "strings=" + allElements(
                        List.of("a", "b"), String.class
                )
        );

        System.out.println(
                "mixed=" + allElements(
                        List.of(1, "b"), String.class
                )
        );

        System.out.println(
                "sameRuntimeClass=" +
                (new ArrayList<String>().getClass()
                        == new ArrayList<Integer>().getClass())
        );
    }
}
~~~

Compile/run with Java 17:

~~~bash
javac --release 17 -Xlint:all ListOverloadApiDemo.java
java ListOverloadApiDemo
~~~

**Verified stdout:**

~~~text
names=Lan|Mai
scores=12
lengths=[1, 4]
squares=[4, 9]
strings=true
mixed=false
sameRuntimeClass=true
~~~

Reading the output in terms of contracts:

1. **`names` and `scores`:** share the name `process`, yet the two parameters **are genuinely `Names` and `Scores`**, with distinct runtime classes and erasures. The record compact constructors prevent the list from being mutated through the input reference after building the snapshot.
2. **`lengths` and `squares`:** **one `mapAll` method** called twice; the callback determines the concrete transformation for each call.
3. **`strings` and `mixed`:** `Class<?>.isInstance` checks **each actual element** of `List<?>`. It is not a way to create two overloads with `List<String>` and `List<Integer>`.
4. **`sameRuntimeClass`:** `ArrayList` objects of both parameterizations use the same runtime class. Do not infer from class equality any subtype relationship between `List<String>` and `List<Integer>`.

### Limitations of validation using `Class`

`allElements` returns `false` when encountering any object that is not an instance of the class token (including `null`). This is an **illustrative validation policy**; other business rules might allow `null`, or collect all errors instead of returning a boolean.

`Class<String>` allows checking that each object is a `String`, whereas `Class<List<String>>` has no class literal equivalent to `List<String>.class` to prove an entire nested list has the right type arguments. Validating nested generic structures requires element-by-element validators or an appropriate schema.

## 7. Option D: Passing a Type Token or Meaningful Strategy

If your API needs **a single method** and wants callers to state the expected element type, you can choose:

~~~java
static <T> boolean validate(
        List<T> values, Class<T> elementType) {

    for (T value : values) {
        if (!elementType.isInstance(value)) {
            return false;
        }
    }
    return true;
}
~~~

This signature is one generic method; the compiler ties the type argument of `List` and `Class` to the same `T` at the call site. Even a well-typed source call must account for the fact that **raw/unchecked aliases can break the contract**, so runtime element checks remain useful for untrusted data.

Avoid this misconception:

~~~java
// STILL INVALID: both methods have the same erased parameters (List, Class).
// void process(List<String> items, Class<String> token) {}
// void process(List<Integer> items, Class<Integer> token) {}
~~~

Changing `Class<String>` to `Class<Integer>` only changes the type argument of yet another generic class; its erasure is still `Class`. A token is useful **as data/validation for one method**, not as a new overload axis when raw parameter types stay unchanged.

Another option is a **strategy interface**: the caller passes a processor object that the API invokes through a contract. A strategy fits better when behavior has state, configuration, multiple steps, or needs reuse, whereas a `Function`/`Consumer` is more concise for simple transformations.

## 8. Overloads That Are Allowed Yet Misleading

The two methods below have different erased parameter types and can coexist:

~~~java
static void process(java.util.Collection<String> names) {}
static void process(java.util.List<Integer> scores) {}
~~~

Their erasures are `Collection` and `List`, respectively; they do not collide like two `List` parameters. However, this design **easily misleads readers**:

- Method selection depends on the static type of the argument and overload resolution; it does not inspect runtime element types to pick a branch.
- A list of `String` might be viewed through `Collection<String>` or an intermediate type; collection subtypes and wildcards make call sites hard to reason about.
- Certain calls involving type inference or `null` may encounter surprising overload selection or inapplicability.

Therefore, if the business intent is genuinely to **separate names and scores**, two clear method names or two wrapper classes are far more durable than forcing differences via raw container types.

Adding a dummy `boolean isString` parameter just to change arity because the compiler forbids two `List` overloads also confuses callers. Only add a discriminator if it represents **an essential business attribute** and is clearly validated and expressed.

## 9. Do Not Confuse Name Clashes with Override Bridges

A method in a generic superclass:

~~~java
class Box<T> {
    T echo(T value) {
        return value;
    }
}

class StringBox extends Box<String> {
    @Override
    String echo(String value) {
        return value.toUpperCase();
    }
}
~~~

`StringBox.echo(String)` **validly overrides** the method specialized from `Box<String>`. The compiler can generate an `echo(Object)` bridge to preserve dynamic dispatch after erasure.

This is **different** from two side-by-side declarations:

~~~java
// INTENTIONALLY INVALID:
// void echo(List<String> names) {}
// void echo(List<Integer> numbers) {}
~~~

A bridge method only preserves an **already valid override** from Java source when descriptors must be connected. It cannot rescue an invalid pair of overloads that share the same erasure. Do not add manual bridges or rely on runtime generic arguments for dispatch.

## 10. API Evolution: Choose Ergonomic Calls, Not Just Compilable Signatures

Before settling on an approach, ask:

1. **Are the two behaviors truly different?** If yes, names like `joinNames` and `sumScores` express intent far better than a generic `process`.
2. **Do they share a single pipeline?** If yes, a generic method with a callback avoids duplicated logic.
3. **Do inputs represent two distinct domain models?** If yes, distinct wrapper records/classes can provide valid overloads and house proper validation.
4. **Does the data come from raw code/JSON/Reflection?** If yes, perform real runtime validation; do not treat unchecked casts or `List<?>` as a validator.
5. **Is the code already published or newly designed?** For published APIs, changing method descriptors can break existing binary clients with `NoSuchMethodError`. Choose an appropriate migration path rather than breaking the contract immediately.
6. **Will a third element type be added later?** If you anticipate expanding to many types, callbacks/strategies or domain interfaces scale more cleanly than multiplying overloads and wrappers.

When binary compatibility must be maintained, an adapter carrying the **old name and descriptor** can keep precompiled callers working; this requires real testing with old and new class files. Do not assume that adding a new overload never changes source-level overload resolution or caller behavior upon recompilation.

## 11. Self-Check

**Question 1.** Why are `process(List<String>)` and `process(List<Integer>)` in the same class invalid?

**Answer:** The erasure of both parameters is `List`, causing a name clash. Type arguments only help the compiler check source code; they do not create separate runtime classes for each `List<E>`.

**Question 2.** Can two distinct records `Names` and `Scores` serve as parameters for two `process` overloads?

**Answer:** Yes. The two erased parameter types are genuinely distinct; `null` without a specific target can still cause overload ambiguity.

**Question 3.** If you want one algorithm to process multiple kinds of lists with different callbacks, what should you use?

**Answer:** A generic method accepting `Function<? super T,? extends R>` or `Consumer<? super T>` suited to the data flow, rather than creating two `List<E>` overloads.

**Question 4.** Does adding `Class<String>` and `Class<Integer>` as a second parameter resolve the erased collision by itself?

**Answer:** No. `Class<String>` and `Class<Integer>` both erase to `Class`, so both methods still have the erased parameter list `(List, Class)`.

**Question 5.** Does two `ArrayList` instances having the same runtime class prove their generic type arguments are equal?

**Answer:** No. Erasure means ordinary runtime classes do not carry type arguments that way. Do not use `getClass()` to infer `List<String>` from data.

**Question 6.** Are `process(Collection<String>)` and `process(List<Integer>)` valid with respect to parameter types?

**Answer:** Yes, they can be, because their erased parameter types are `Collection` and `List`. However, as an API design this is error-prone; you must consider overload resolution and actual static types.

**Question 7.** Do bridge methods help declare two overloads differing only by `List<String>`/`List<Integer>`?

**Answer:** No. Bridges serve dynamic dispatch of valid overrides; a name clash prevents the source from compiling in the first place.

**Question 8.** If a library previously published a public method taking `List` and now changes it to a `Names` wrapper, will old `.class` clients keep running automatically?

**Answer:** You cannot assume so. The method descriptor changed, so you need an adapter/compatibility plan or client rebuilds; test old binary clients against the new library.

**Key takeaway:** **do not try to distinguish two overloads using generic type arguments that undergo erasure**. Decide whether the API needs two **business names**, **one generic pipeline**, or **two genuine domain types**; use a runtime token only when it serves validation or well-designed logic, not as an overloading trick.
