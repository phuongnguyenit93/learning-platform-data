# Balancing Flexibility, Readability, and Type Inference in Java Generic APIs

An API can be sound under the type system yet **hard to call, hard to read, and hard to upgrade**. Conversely, an overly simple signature can force callers to copy data or cast unsafely. When publishing a generic API, the goal is balancing three factors:

1. **Right-sized flexibility:** accept sources/destinations with different type arguments while preserving necessary constraints.
2. **Clear contract:** just by reading the method name, parameters, and result, readers understand data flow, mutability, and required preconditions.
3. **Easy compiler inference:** most call sites do not need casts, explicit type witnesses, or lambda casts for `javac` to select a call.

This lesson is **a synthesis based on an API review scenario**, without repeating every proof of invariance, PECS, or wildcard capture. Together we will design an event-processing pipeline, evaluate alternative signatures, test call-site inference, verify a Java 17 example, and identify risks when changing a public API.

## 1. Start from the call site: every decision serves a requirement

Suppose an application has two event types:

~~~java
interface Tagged {
    String tag();
}
record Alert(String tag) implements Tagged {}
record Note(String tag) implements Tagged {}
~~~

Requirements:
- Select `Alert` instances whose tag starts with `"a"`.
- Transform them into a list of `String`s for display.
- Append the selected results into a general tracking collection.
- Edit the contents of a mutable `Alert` list while **preserving the `Alert` type argument**.
- Combine `Alert` and `Note` into one `Tagged` list without corrupting the original collections.

Before writing `<T>`, sketch the desired call sites:

~~~java
List<Alert> alerts = List.of(
        new Alert("alpha"),
        new Alert("beta"),
        new Alert("atlas"));

Predicate<Tagged> beginsA =
        event -> event.tag().startsWith("a");

List<Tagged> chosen = select(alerts, beginsA);
List<String> labels = mapAll(chosen, Tagged::tag);

List<Object> audit = new ArrayList<>();
appendAll(chosen, audit);
~~~

The goal is writing those calls **without unchecked casts and without copying merely to work around type-argument incompatibility**. API signatures are designed backward from identified needs.

### Three questions to answer for every method

- **Where does data flow?** Read-only source, write-only destination, or both read and write in the same place?
- **Where are types linked?** Is the same `T` needed between source and output, or just a common interface like `Tagged`?
- **What contract does the return value belong to?** A new `List<T>`, `Optional<T>`, a count, or a side effect on an existing collection?

Not every method needs a type variable. For instance, simply counting elements should suffice with:

~~~java
static int count(Collection<?> values) {
    return values.size();
}
~~~

This signature is no less safe than `<T> int count(Collection<T>)` when only calling `size()`; on the contrary, it tells readers the element type is irrelevant.

## 2. Score a signature along three dimensions

| Criterion | Review question | Unhealthy sign |
| --- | --- | --- |
| **Flexibility** | Can it accept `List<Alert>`, `List<Note>`, `List<Tagged>` when the algorithm only needs `Tagged`? | Callers must copy into `List<Tagged>` just to call a read function. |
| **Clarity** | Which parameter is modified? Does the result alias the source? | Named `copy` yet appends to destination, or named `select` yet returns an undocumented mutable view. |
| **Type inference** | Does Java infer `T`/`R` automatically from arguments, callbacks, and expected type? | Most callers must write `.<Tagged>` or cast lambdas because signatures/overloads are ambiguous. |
| **Runtime constraints** | Are nulls, empty inputs, mutability, ordering, exceptions, and partial failures clear? | Generic signature is sound yet implementation violates data expectations. |
| **Compatibility** | Does changing the signature alter the erased descriptor, call sites, or overload resolution? | A PECS improvement breaks old binary clients with missing methods. |

You do not need the "most general possible" API: a method serving only a specific domain should usually accept the specific domain interface. Type parameters and wildcards are tools to express contracts, not trophies to maximize.

## 3. Designing the read source: `? extends T` and supertype callbacks

For filtering, we want callers to pass a list of `Alert`s **and** a `Predicate` that knows how to work with the `Tagged` interface.

~~~java
static <T> List<T> select(
        Iterable<? extends T> source,
        Predicate<? super T> predicate) {

    List<T> result = new ArrayList<>();

    for (T value : source) {
        if (predicate.test(value)) {
            result.add(value);
        }
    }

    return result;
}
~~~

Deliberate structure:
- `Iterable<? extends T>`: only needs to iterate elements from a producer, needing neither indexing nor mutation.
- `Predicate<? super T>`: the predicate consumes `T`, so it can be a predicate accepting a supertype like `Tagged`.
- `List<T>`: callers receive a **new collection** with an inferred element type; not a wildcard result imposing unnecessary restrictions on operations.

At the call site:

~~~java
List<Tagged> chosen = select(alerts, beginsA);
~~~

The compiler can pick a `T` compatible with `Alert` in the source, `Tagged` in the predicate, and **target type `List<Tagged>`**. Consequently, callers do not need to cast `List<Alert>` to `List<Tagged>` — a cast that is invalid under invariance anyway.

A variant:

~~~java
List<Alert> chosenAlerts = select(alerts, beginsA);
~~~

can also be valid. In this case `T` is inferred compatibly with `Alert`. The same generic method supports both output expectations without mistyping the source's type arguments.

### `var` and target typing

~~~java
var selected = select(alerts, beginsA);
~~~

`var` does not explicitly state an expected type `List<Tagged>` on the left-hand side. The compiler infers from the remaining constraints, and the result can differ from a call with an explicit target type. Do not assume `var` always deduces the caller's **business intent**.

If downstream code needs `List<Tagged>` specifically, declaring the explicit target type is usually better than forcing callers to add unchecked casts later.

## 4. Transforming results: name `T`/`R` by data direction

A mapper reads data of type `T` and **produces a new result type `R`**:

~~~java
static <T, R> List<R> mapAll(
        Iterable<? extends T> source,
        Function<? super T, ? extends R> mapper) {

    List<R> result = new ArrayList<>();

    for (T value : source) {
        result.add(mapper.apply(value));
    }

    return result;
}
~~~

There are two constraints worth naming:
- `T` links source elements to the mapper's input.
- `R` links the mapper's output to the result list's elements.

Call:

~~~java
List<String> names = mapAll(chosen, Tagged::tag);
~~~

`Tagged::tag` is a method reference whose target functional interface is inferred from the call. Neither `Function<Object,Object>` nor casting the entire list down to `Object` is needed.

**However**, if the API only has the specific job "extract tags from `Tagged`", a method `List<String> tags(Iterable<? extends Tagged>)` can be easier to understand than generic `mapAll`. Only introduce a general helper when it genuinely reduces duplication and serves multiple sensible use cases.

### Do not misuse overly broad interfaces

If a method needs `get(index)` or `replaceAll`, accept `List<T>` rather than `Iterable<T>` because `List` behavior is required. Conversely, a method that only iterates should not force callers to supply a random-access list.

An interface too broad **in allowed operations** leaves the implementation lacking contract guarantees; an interface too narrow **in collection shape** forces callers to write pointless adapters.

## 5. Data destination: use PECS without hiding side effects

When wanting to append events to a tracking collection:

~~~java
static <T> void appendAll(
        Iterable<? extends T> source,
        Collection<? super T> destination) {

    for (T value : source) {
        destination.add(value);
    }
}
~~~

The signature describes one direction:
- `source` yields `T`.
- `destination` accepts `T` or an appropriate supertype of `T`.
- One `<T>` links both sides; two completely independent `?` wildcards **do not prove** they can exchange elements.

Example:

~~~java
List<Object> audit = new ArrayList<>();
appendAll(chosen, audit);
~~~

There is no intent to read values from `audit` and write them back into `source`. If bidirectional exchange between lists is needed, a stronger contract must be designed, likely requiring `List<T>` on both sides.

Naming it `appendAll` makes clear that `destination` **grows with additional elements**. The JDK method `Collections.copy(dest,src)` also uses PECS yet **replaces by index** and requires `destination` to have sufficient size; do not imitate the name `copy` while changing the behavior.

Document additionally if public:
- `destination` must support `add`; not every `Collection` is mutable.
- If `source`/`destination` alias each other and appending happens while iterating, behavior may fail or behave unexpectedly; disallow aliasing or take a snapshot.
- If `add` throws an exception midway, some elements may already have been added; do not implicitly promise an atomic operation.
- The collection may not preserve duplicates or iteration order in the way users expect.

Generics only solve **element compatibility**, not all of these runtime conditions.

## 6. When reading and writing back the same type is needed, keep `List<T>`

An in-place edit:

~~~java
static <T> void rewrite(
        List<T> values,
        UnaryOperator<T> editor) {

    values.replaceAll(editor);
}
~~~

This signature deliberately uses an **exact named `T`**: read `T`, transform to `T`, write `T` back to **the same list**. It is not an independent "source producer, target consumer" problem.

Example:

~~~java
List<Alert> editable = new ArrayList<>(alerts);

rewrite(editable,
        alert -> new Alert(alert.tag().toUpperCase()));
~~~

If changed to `List<? extends Tagged>`, the compiler could not guarantee an arbitrary `Tagged` could be written into a list that is actually `List<Alert>`. If `List<? super Alert>` were used, the read side would only be guaranteed as `Object`. A single named `T` relationship is the part of the contract that must be preserved.

Choose `List<T>` or `Map<K,V>` when a method must read and update under the same type contract; use wildcards when flexibility is one-directional. **Do not use raw casts to deceive the type system.**

## 7. A complete Java 17 example evaluating the entire pipeline

Save the file **GenericApiDecisionDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.UnaryOperator;

public class GenericApiDecisionDemo {
    interface Tagged {
        String tag();
    }

    record Alert(String tag) implements Tagged {}
    record Note(String tag) implements Tagged {}

    static int count(Collection<?> values) {
        return values.size();
    }

    static <T> List<T> select(
            Iterable<? extends T> source,
            Predicate<? super T> predicate) {

        List<T> result = new ArrayList<>();
        for (T value : source) {
            if (predicate.test(value)) {
                result.add(value);
            }
        }
        return result;
    }

    static <T, R> List<R> mapAll(
            Iterable<? extends T> source,
            Function<? super T, ? extends R> mapper) {

        List<R> result = new ArrayList<>();
        for (T value : source) {
            result.add(mapper.apply(value));
        }
        return result;
    }

    static <T> void appendAll(
            Iterable<? extends T> source,
            Collection<? super T> destination) {

        for (T value : source) {
            destination.add(value);
        }
    }

    static <T> void rewrite(
            List<T> values, UnaryOperator<T> mapper) {

        values.replaceAll(mapper);
    }

    public static void main(String[] args) {
        List<Alert> alerts = List.of(
                new Alert("alpha"),
                new Alert("beta"),
                new Alert("atlas")
        );

        Predicate<Tagged> beginsA =
                event -> event.tag().startsWith("a");

        List<Tagged> chosen = select(alerts, beginsA);
        System.out.println(
                "chosen=" + mapAll(chosen, Tagged::tag)
        );
        System.out.println("count=" + count(chosen));

        List<Object> audit = new ArrayList<>();
        appendAll(chosen, audit);
        System.out.println("audit=" + audit.size());

        List<Alert> editable = new ArrayList<>(alerts);
        rewrite(editable,
                alert -> new Alert(
                        alert.tag().toUpperCase()));
        System.out.println(
                "edited=" + mapAll(editable, Alert::tag)
        );

        List<Note> notes = List.of(new Note("gamma"));
        List<Tagged> all = new ArrayList<>();
        appendAll(alerts, all);
        appendAll(notes, all);
        System.out.println(
                "all=" + mapAll(all, Tagged::tag)
        );
        System.out.println(
                "source=" + mapAll(alerts, Alert::tag)
        );
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -Xlint:all GenericApiDecisionDemo.java
java GenericApiDecisionDemo
~~~

**Verified stdout:**

~~~text
chosen=[alpha, atlas]
count=2
audit=2
edited=[ALPHA, BETA, ATLAS]
all=[alpha, beta, atlas, gamma]
source=[alpha, beta, atlas]
~~~

**Why is this an example of design decisions, not just a syntax demo?**

- `chosen`: the `List<Tagged>` result is inferred from the target type, even though the source is `List<Alert>`.
- `mapAll`: returns `List<String>` from the `Tagged::tag` callback without caller casting.
- `audit`: source is read as `Tagged`, destination `List<Object>` accepts it via `? super T`; the method has a clear side effect.
- `editable`: in-place edit preserves the exact `Alert` type; the `List.of` source is untouched.
- `all`: combines `Alert` and `Note` into a `Tagged` list without casting `List<Alert>` to `List<Tagged>`.
- `source`: the original source remains intact, showing which operations create a new list and which modify elsewhere.

Try replacing `Predicate<Tagged>` with a predicate that only accepts `Note`. The compiler must reject `select(alerts, predicateOfNote)` if no type `T` satisfies the constraints; do not use an unchecked cast to make a nonsensical call run.

## 8. Target typing, lambdas, and type inference: errors often live at the call site

A generic method can use information from:
- Argument types.
- Target types in assignment, return, or invocation contexts per Java rules.
- Functional interface targets of lambdas/method references.
- Bounds and wildcard constraints of type variables.

Thus, **the same method name does not guarantee every call chooses the same `T`**:

~~~java
List<Alert> onlyAlerts = select(alerts, beginsA);
List<Tagged> anyTagged = select(alerts, beginsA);
~~~

Both usages preserve compiler-checked relationships; they do not give `ArrayList`/`List` separate runtime classes per type parameter.

### When inference is unclear, fix the contract first

An acceptable debugging trick is splitting calls into intermediate variables with explicit types:

~~~java
Predicate<Tagged> selectedByTag =
        element -> element.tag().startsWith("a");

List<Tagged> filtered =
        select(alerts, selectedByTag);

List<String> labels =
        mapAll(filtered, Tagged::tag);
~~~

Do not force callers to repeatedly write `(Function<...>)`, raw `List`, or `MyApi.<Object>...` just to work around an API designed to be too hard to infer.

Even so, **some explicit type witnesses** are reasonable in rare cases, especially when the intended choice of `T` is not obvious from arguments. Evaluate APIs on everyday use cases rather than demanding miraculous inference on every expression.

## 9. Ambiguous overloads: do not create two peer functional targets

These two overloads have different erased parameters, so they can coexist:

~~~java
static void load(
        java.util.function.Supplier<String> source) {}

static void load(
        java.util.concurrent.Callable<String> source) {}
~~~

However, the call:

~~~java
// INTENTIONALLY DOES NOT COMPILE:
// load(() -> "ready");
~~~

can be **ambiguous** because a lambda does not carry a concrete functional interface class on its own. The compiler should not have to guess whether the author meant `Supplier` or `Callable` solely from a body returning `String`.

Solutions:
- Use two business-expressive names (`loadFromSupplier`, `loadFromCallable`) if their processing contracts differ.
- Pick one functional interface as the public contract if two overloads only create ambiguity.
- When two overloads are genuinely needed, callers can supply a typed variable, such as:

~~~java
java.util.function.Supplier<String> supplier =
        () -> "ready";

// load(supplier); // Will select the Supplier overload.
~~~

If two overloads take `List<String>` and `List<Integer>`, the problem strikes even earlier: due to erasure they share **the same erased signature** and cannot be declared side by side in one class. Do not try to dispatch on runtime type arguments, because Java overload resolution relies on compile-time types.

## 10. Public APIs: greater flexibility is not necessarily backward-compatible

Suppose v1 publishes:

~~~java
void inspect(List<Tagged> events)
~~~

V2 wants to accept more sources and changes it to:

~~~java
void inspect(Collection<? extends Tagged> events)
~~~

The new version may be better for **source flexibility**, yet the raw parameter class changed **`List` → `Collection`**. The JVM method descriptor therefore changes. An old `.class` client may still look for the method taking `List`, and hit linkage errors like `NoSuchMethodError` if the old descriptor is not preserved.

Meanwhile, changing a type argument/wildcard on the same raw `List` sometimes keeps an equivalent descriptor, **yet** source overload resolution, generic signature/reflection, and type inference can still change.

Do not assume "changing only text inside `<...>` is definitely compatible". Distinguish:
1. **Source compatibility:** do callers recompile against v2?
2. **Binary compatibility:** do v1 `.class` callers still link with v2?
3. **Behavioral compatibility:** do nulls, ordering, mutation, exceptions, and semantics change?
4. **Reflection/tool compatibility:** do generic `Signature` metadata or bounds differ?

### How to verify a public API change

~~~bash
# Compile v1/v2 versions into separate class directories.
javap -p -s YourLibraryClass
javap -v YourLibraryClass

# Run a client compiled against v1 with library v2,
# WITHOUT recompiling the client in the binary compatibility test.
~~~

If changing a type variable's bounds, especially the leftmost bound, erased return/parameter descriptors can change even if the method name stays identical. Once a library is published, do not change APIs based on a hunch that a signature "reads nicer"; compare class files and test old binary clients.

## 11. Things the type system does not guarantee

| What the type system expresses | What must still be stated in the contract |
| --- | --- |
| Source allows reading `T`, destination allows accepting `T`. | Whether destination is mutable, and whether append can partially fail. |
| Return type is `List<T>`. | New list or view, mutable or unmodifiable, whether data is aliased. |
| Callback accepts `T` and returns `R`. | Whether callback may throw exceptions, mutate state, or return null. |
| `Optional<T>` holds a `T` value when present. | Difference between not-found and data error; when `Optional.empty()` is used. |
| `Comparator<? super T>` can compare `T`. | Null ordering, consistency, and sort stability per contract. |
| `Class<T>` represents a runtime class. | Not a type token that auto-validates nested type arguments. |
| Type parameter has bounds. | Bounds do not describe domain semantics, limits, or authorization. |

For example, `List.copyOf(source)` disallows structural modification through normal APIs and forbids null elements, yet does not deep-copy mutable element objects. If users concurrently modify `source` without synchronization, taking a snapshot also needs a separate thread-safety policy.

An easy-to-use API needs **concise and accurate** documentation of runtime conditions instead of assuming generics solve everything automatically.

## 12. Pre-release test matrix

Do not write only a single happy path with `List<String>`. Use representative call sites:

| Case | What to prove |
| --- | --- |
| Producer subtype | `List<Alert>` can be used in a method reading `Tagged`. |
| Supertype consumer | `Collection<Object>` can accept `Tagged`. |
| Same-type mutation | `List<Alert>` disallows writing `Note` when the API keeps `T=Alert`. |
| Callback supertype | `Predicate<Tagged>` works on an `Alert` source. |
| Callback result type | Mapper `Tagged::tag` yields `List<String>`. |
| Target typing | Both `List<Alert>` and `List<Tagged>` in appropriate assignment contexts. |
| Return-only type contract | Output keeps the needed type, not `Object` causing late casts. |
| Overload ambiguity | Bare lambdas do not hit two indistinguishable functional targets. |
| Immutable source | Do not attempt direct mutation on `List.of` lists. |
| Mutable destination | `appendAll` handles appending semantics properly; aliasing/partial failure has a policy. |
| Binary compatibility | Keep old client `.class` files when testing descriptor changes. |
| Invalid generic calls | Wrong source code is rejected by the compiler; do not suppress to pass tests. |

### Negative compilation: three examples that must be rejected

Place each snippet in **its own test file**, not merged into the runnable program.

**A — Invariance:**

~~~java
List<Alert> alerts = new ArrayList<>();
// List<Tagged> notAllowed = alerts; // Compile error.
~~~

**B — Wrong data direction:**

~~~java
List<? extends Tagged> source = new ArrayList<Alert>();
// source.add(new Note("bad")); // Compile error.
~~~

**C — Writing the wrong type into an exact list:**

~~~java
List<Alert> alerts = new ArrayList<>();
// rewrite(alerts, alert -> new Note(alert.tag()));
// Compile error: UnaryOperator<Alert> must return Alert.
~~~

Because the erroneous lines are commented out, a file containing them can act as a **runnable test harness** if placed in a suitable class. To perform an actual *negative compilation test*, uncomment the specific line being tested and verify `javac` returns a nonzero exit code. Do not mistake a comment describing an error for proof that the compiler was actually tested.

## 13. Step-by-step order to fix a hard-to-use API signature

A time-saving review workflow:

1. **Write two typical valid call sites and one call site that must be rejected**. If you cannot express them, the contract may still be unclear.
2. **Choose the abstraction level**: `Iterable` for iteration, `Collection` for adding, `List` for indexing/mutation, domain interfaces when algorithms depend on domain behavior.
3. **Trace the data flow**: producer → mapper → consumer, or read/modify/write with the same `T`.
4. **Place type variables only on relationships that must hold**, avoiding redundant `<T>` on functions that only call `size()`.
5. **Apply wildcards at one-way data boundaries**, never using wildcards to hide bidirectional relationships or swap element types by casting.
6. **Give outputs a useful type**, usually `List<R>`/`Optional<T>` instead of `Object` or unnecessary wildcard results.
7. **Test Java inference** with lambdas/method references, explicit target types, and `var`.
8. **Audit overloads**: erasure collisions, ambiguous lambdas, nulls, or the compiler picking an unintended overload.
9. **Write the runtime contract**: nulls, empty cases, mutability, aliasing, ordering, error behavior.
10. **If the API is already public, check source/binary compatibility** using `javac`, `javap`, and clients compiled against the old version.
11. **Write concise Javadoc on type parameter relationships and non-type constraints**, rather than copying the signature without behavior.
12. **Optimize complexity only when practically useful**; a new generic framework is not better than a short domain method if there is only one use case.

## 14. End-of-chapter review questions

**1.** A method only counts elements in any `Collection`. Is `<T>` needed?

**Answer:** Not needed if there is no constraint with other positions; `Collection<?>` is clearer.

**2.** Why can't `List<Alert>` be directly assigned to `List<Tagged>`?

**Answer:** Generic type arguments are invariant. `List<Tagged>` can accept `Note`, whereas `List<Alert>` cannot.

**3.** Why does `select` return `List<T>` yet accept `Iterable<? extends T>`?

**Answer:** Input only supplies values usable as `T`; output is newly created with element type `T` tied to the caller/target type.

**4.** Why is the callback in `select` typed as `Predicate<? super T>`?

**Answer:** The predicate consumes `T`; a predicate accepting supertypes of `T` can still handle every `T`.

**5.** Why does `rewrite` use `List<T>` and `UnaryOperator<T>` instead of `List<? extends T>`?

**Answer:** It must read and write back the same element type on the same list; a producer wildcard forbids arbitrarily writing a new `T`.

**6.** Why can `load(() -> "ready")` be ambiguous when overloaded with `Supplier<String>` and `Callable<String>`?

**Answer:** A bare lambda is compatible with two peer functional targets, leaving `javac` without enough distinction to choose.

**7.** When is a generic helper `mapAll` genuinely worth creating?

**Answer:** When there are multiple transformations sharing the same structure and keeping the `T→R` relationship helps callers avoid duplicate code/casts; not because more complex syntax looks nicer.

**8.** Does `List<Tagged> chosen = select(alerts, beginsA)` turn `alerts` into `List<Tagged>`?

**Answer:** No. `select` builds a new result under the `T` contract; the source stays `List<Alert>` and is never forced into a different parameterized type.

**9.** Can changing a public parameter from `List` to `Collection` break compiled clients?

**Answer:** Yes. The erased method descriptor changes from `List` to `Collection`, so old binary clients may fail to find the method descriptor they linked against.

**10.** Is a generic signature enough to promise `appendAll` is atomic/thread-safe?

**Answer:** No. Type safety is one contract layer; atomicity, mutability, concurrent modification, and partial failures must be specified and verified separately.

**Conclusion:** The best generic signature is neither the longest nor the shortest. It is **the simplest signature that still captures all needed type relationships**, accepts safe call sites cleanly, lets the compiler infer naturally, and clearly explains behaviors the type system cannot describe. When an API is widely published, **compatibility** is a mandatory evaluation dimension alongside flexibility, readability, and type inference.