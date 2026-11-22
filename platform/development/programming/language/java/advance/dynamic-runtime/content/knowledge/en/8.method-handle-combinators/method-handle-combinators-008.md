# 8.8 Describing loops with loop, countedLoop, and iteratedLoop

`java.lang.invoke.MethodHandles` does not only combine calls in the style of `filterArguments`, `guardWithTest`, or `foldArguments`; it also has **loop combinators** to express loops completely using `MethodHandle`. Three core APIs:

- **`MethodHandles.loop(...)`** — combines one or more *clauses*, each clause having `init`, `step`, `pred`, `fini` handles. Suitable when there are multiple state variables and complex exit logic.
- **`MethodHandles.countedLoop(...)`** — a loop with an integer `int` counter, with a determined number of iterations or index range. Suitable when the iteration count/bounds are known or computable from parameters.
- **`MethodHandles.iteratedLoop(...)`** — sequentially fetches elements from an `Iterator` (by default from an `Iterable`). Suitable when the input is a collection of elements to process.

All three exist since Java 9 and can be used on **Java 17+**. They *create a new handle describing control flow*, rather than immediately running the loop when calling the factory. The loop executes when you call `handle.invokeExact(...)` or `handle.invoke(...)`.

## 1. Mental map: a loop handle receives inputs, holds state, returns a result

~~~text
                MethodHandles factory
     handles init / step / pred / fini / iterator
                         |
                         v
                 MethodHandle loop
                 type: (A...)R
                         |
                   invokeExact(a...)
                         |
           +-------------+--------------+
           |                            |
     loop runs                     loop terminates
     on state (V...)               returns R / void
           |
     calls child handles
~~~

There are three groups of types that are easily confused:

| Symbol | Meaning | Where does it go in the signature? |
| --- | --- | --- |
| `A...` | **External arguments**, invariant arguments passed into the loop on invocation | Are the parameters of the loop handle `(A...)R`; can also be passed to clauses |
| `V...` | **Loop variables**, state variables updated after each step | Internal to the loop; `step`/`pred`/`fini` handles can receive them, but they do **not** automatically become public parameters of the loop |
| `R` | Final value of the loop | Return type of the loop handle; in `countedLoop` and `iteratedLoop` it is usually `V` of the accumulator |

A loop combinator **does not directly invoke Java code like `for` or `while` passed as a string**. You prepare `MethodHandle`s with the exact signatures; the combinator verifies and composes them into an invocable method.

### Quick comparison

| Aspect | `loop` | `countedLoop` | `iteratedLoop` |
| --- | --- | --- | --- |
| Continuation condition | One or more `pred` returning `boolean` | Counter `i` compared against iteration count/bound | `Iterator.hasNext()` |
| Exit condition | `pred` returns `false`; calls `fini` of the same clause | Out of indices/iterations | Iterator runs out of elements |
| State | Multiple clauses, multiple types `V1, V2...` | `int` counter and optional accumulator `V` | Element value `T` and optional accumulator `V` |
| Update function | `step` of each clause | `body(V,i,A...)` | `body(V,T,A...)` |
| Complexity | Most flexible, hardest to match types correctly | Less boilerplate | Natural expression of element traversal |
| Result signature | `(A...)R` with `R` from `fini` | `(A...)V` or `void` | `(A...)V` or `void` |

## 2. `MethodHandles.loop` — most general, but requires understanding clauses and order

API declaration:

~~~java
public static MethodHandle loop(MethodHandle[]... clauses)
~~~

Each clause is a `MethodHandle[]` array of 0 to 4 elements, interpreted in order:

~~~text
{ init, step, pred, fini }
    |      |      |      |
    |      |      |      +--> produces the return value when this clause's pred is false
    |      |      +---------> decides continue / stop (boolean)
    |      +----------------> updates the clause's loop variable (if any)
    +-----------------------> produces the initial state value
~~~

Trailing positions can be omitted with `null`. Clauses shorter than 4 elements are padded with `null` at the end. For example, `new MethodHandle[]{null, increment}` only provides `step`, leaving `init` as default and having no separate `pred`/`fini`.

A sample call:

~~~java
MethodHandle loop = MethodHandles.loop(
        new MethodHandle[] { null, increment },
        new MethodHandle[] { seed, accumulate, keepGoing, finish });
~~~

This is a **structural snippet**, not a standalone program: the handle variables are created in the full example below. The first clause holds the counter; the second clause holds the accumulator and decides when to finish.

### 2.1. Signatures of component handles

Suppose there are two loop variables `i:int` and `acc:int`, and one external argument `limit:int`:

~~~text
loop variable types:      (int i, int acc)
external arguments:       (int limit)

counter init:             (int limit)int       (or null -> 0)
counter step:             (int i, int acc, int limit)int

accumulator init:         (int limit)int
accumulator step:         (int i, int acc, int limit)int
accumulator pred:         (int i, int acc, int limit)boolean
accumulator fini:         (int i, int acc, int limit)int

result loop type:         (int limit)int
~~~

Note: **`loop` does not require every handle to take all parameters**. Missing parameters at the *end* of the list can be added as if by `dropArguments`, provided the lists have *effectively identical* structure: identical or one list is a **prefix** of the longest list in the matching group. Do not interpret this as the combinator arbitrarily reordering or converting parameter types; the types that are present must still match the prescribed order.

With multiple clauses, **non-init** handles receive loop variables `V...` in **clause order**, followed by external arguments `A...`. An `init` does not receive `V...` because at initialization there is no state yet; it only receives a prefix of `A...`.

### 2.2. Actual execution mechanism: `step` comes before `pred`

The most important point of `MethodHandles.loop`: **after initializing all state, the combinator goes through each clause in order; at each clause it runs `step` first and then checks `pred` (if present)**. This is not a regular `while (pred) { step; }` loop.

~~~text
1. Save external arguments A...
2. Call init handles in clause order to create V1, V2, ...
3. Start cycle:
   - clause 1: step1 -> update V1 -> pred1 (if present)
       if pred1=false: run fini1 and return
   - clause 2: step2 -> update V2 -> pred2 (if present)
       if pred2=false: run fini2 and return
   - ...
4. If no clause stops: repeat the next cycle.
~~~

The `step` value updates the state **immediately**, so subsequent clauses see the new state of preceding clauses. If there are multiple predicates, **the first predicate that returns `false` determines which finalizer is called**. If no predicate can return `false`, the loop can run infinitely (barring errors/exceptions). There must be **at least one non-null `pred`**; a predicate must return primitive `boolean`.

Defaults when elements are omitted:

- Missing `init`: the loop variable receives the **default value** corresponding to its type (`int=0`, reference=`null`...).
- Missing `step`: uses an identity operation that keeps the corresponding state unchanged.
- Missing `pred`: treated as always `true`, so that clause cannot exit on its own.
- Missing `fini`: returns the default value of the **common return type** of the finalizers; if there are no finalizers, the loop result is `void`.
- Completely null clauses are ignored; the structure must not lack any predicate capable of deciding exit.

### 2.3. Why is `loop` different from `whileLoop`?

`MethodHandles.whileLoop(init,pred,body)` is built on the general combinator but is explicitly designed to **check the predicate before the body**, like `while` in Java. `doWhileLoop(init,body,pred)` checks the predicate after the body. Meanwhile, `loop` with the presented clauses executes **`step` before `pred` in clause-by-clause order**, allowing arbitrary multiple loop variables to be described.

Therefore, **do not mechanically copy** a Java `while` loop into a single clause `{init,step,pred,fini}` and assume the execution order is equivalent. If the goal is just a regular `while`/`do-while` loop, using the specialized factory will be easier to read and less error-prone.

## 3. Multi-clause `loop` example: computing factorial

Goal for `limit >= 0`:

~~~java
int factorial(int limit) {
    int product = 1;
    for (int i = 1; i <= limit; i++) {
        product *= i;
    }
    return product;
}
~~~

This is a **regular Java function for comparison**, not a standalone method handle. With generic `loop`, use two states:

- `i` defaults to 0, `step` increments by 1.
- `product` initializes to 1, `step` multiplies by the incremented `i`.
- `predicate` checks `i < limit` **after multiplying**.
- `fini` returns `product`.

Thus, the final cycle when `i == limit` still performs the multiplication before the predicate returns `false`; for `limit=5` the product is `1*2*3*4*5=120`. `limit=0` also returns 1 (the first multiplication by 1 does not change product), matching the convention `0!=1`. Real-world examples need to check `limit >= 0` and `int` overflow: factorial 13 and above overflows `int`.

Helpers in the full program:

~~~java
private static int one(int limit) { return 1; }
private static int next(int i, int acc, int limit) { return i + 1; }
private static int multiply(int i, int acc, int limit) { return i * acc; }
private static boolean keepGoing(int i, int acc, int limit) { return i < limit; }
private static int result(int i, int acc, int limit) { return acc; }
~~~

When creating static handles with `Lookup.findStatic(...)` and then calling:

~~~java
MethodHandle factorial = MethodHandles.loop(
        new MethodHandle[] { null, inc },
        new MethodHandle[] { initFactorial, mult, predicate, finish });
~~~

We get `factorial.type() = (int)int` and can invoke it with `(int) factorial.invokeExact(5)`. Even though `inc`, `mult`, `predicate`, and `finish` all have multiple parameters, **the outer function only takes `limit`**. The states `i` and `acc` are managed inside the loop handle.

## 4. `countedLoop`: looping by a counter, with two overloads

Two factories:

~~~java
public static MethodHandle countedLoop(
        MethodHandle iterations, MethodHandle init, MethodHandle body);

public static MethodHandle countedLoop(
        MethodHandle start, MethodHandle end,
        MethodHandle init, MethodHandle body);
~~~

They are convenience wrappers over generic `loop` and automatically create an `int i` counter. The difference is **the definition of the index range**:

| Overload | Index sequence `i` | Example |
| --- | --- | --- |
| `countedLoop(iterations, init, body)` | `0` to `iterations(...)-1` | `iterations=4` → `0,1,2,3` |
| `countedLoop(start, end, init, body)` | `start(...)` to `end(...)-1` | `start=2,end=5` → `2,3,4` |

Regardless of how many times it counts, **the signature of `body` has a specific order**:

~~~text
With accumulator V:
    body(V accumulator, int counter, A... externalArgs) -> V

Without accumulator:
    body(int counter, A... externalArgs) -> void
~~~

`V` is the state type and also the return type of `body` (if not void). `init`, if provided, must return `V` and only receives external arguments `A...`, not the counter. `iterations`, `start`, and `end` must return **primitive `int`**. The external parameter lists of the handles must be compatible according to the prefix rules in the Javadoc.

### 4.1. Three-handle overload: dynamic iteration count

Equivalent description (simplified syntax, accurate counting loop):

~~~java
int n = iterations(externalArgs);
int acc = init(externalArgs);
for (int i = 0; i < n; i++) {
    acc = body(acc, i, externalArgs);
}
return acc;
~~~

Here `n` is just a result computed from external arguments; it is not an argument automatically inserted into the external call. If the iteration count is 0 or negative, **`body` is not run**, and the initial accumulator value is returned; if `init=null`, the default value of `V` is used.

Example computing the sum of even numbers by **index** over `n` iterations:

~~~java
private static int iterations(int n) { return n; }
private static int initial(int n) { return 0; }
private static int evenIndexSum(int total, int i, int n) {
    return total + 2 * i;
}
~~~

The handles have types respectively:

~~~text
iterations   : (int)int
initial      : (int)int
evenIndexSum : (int,int,int)int

countedLoop  : (int)int
~~~

With `n=4`, `i=0,1,2,3` and sum `2*0+2*1+2*2+2*3=12`. With `n=0`, the loop returns 0 without calling `body`. The loop still has one external argument `n`, used by whichever components need it.

**Do not mix up the order:** `evenIndexSum(total, i, n)` receives the **accumulator first**, then the counter, then external arguments. Writing `evenIndexSum(i,total,n)` can still have the same type `(int,int,int)int` and be accepted by the combinator, but the logic will be silently wrong. Naming variables clearly by role helps avoid a very hard-to-detect bug.

### 4.2. Four-handle overload: range `[start,end)`

Equivalent:

~~~java
int endExclusive = end(externalArgs);
int begin = start(externalArgs);
V acc = init(externalArgs);
for (int i = begin; i < endExclusive; i++) {
    acc = body(acc, i, externalArgs);
}
return acc;
~~~

According to the Javadoc pseudocode, `end` is evaluated before `start` and `init`; do not rely on side effects of initialization handles to define program semantics. When `start >= end`, `body` does not run.

Example to compute `2+3+4=9`:

~~~java
private static int from(int start, int end) { return start; }
private static int to(int start, int end) { return end; }
private static int zeroRange(int start, int end) { return 0; }
private static int addIndex(int total, int i, int start, int end) {
    return total + i;
}
~~~

`from` and `to` both have type `(int,int)int`, `zeroRange` as well, while `addIndex` has type `(int,int,int,int)int`. The factory returns a handle of type `(int,int)int`. Calling `ranged.invokeExact(2,5)` yields 9; calling `ranged.invokeExact(5,2)` yields 0.

### 4.3. `init=null` and `void`-returning `body`

If `body` returns `V` and `init=null`, the combinator creates the initial state using the **default value of V**: `0` for `int`, `false` for `boolean`, `null` for references. If `body` needs an accumulator object that you did not create in `init`, `null` can cause an error when `body` dereferences the state; therefore, with `List` or `StringBuilder`, you should have an `init` that creates a valid object.

If `body` returns `void`, there will be no accumulator returned. The body signature then is `(int i, A...)void`; the loop handle takes `A...` and returns `void`. Use this when you want side effects such as logging, filling an array, or updating an external object. Examples with return values are usually easier to verify than side-effect examples; prefer a functional accumulator when possible.

`countedLoop` does not automatically parallelize and does not split work across multiple threads; it executes the counted loop sequentially. If `body` is expensive or has shared state, normal concurrency and exception rules still apply.

## 5. `iteratedLoop`: using `Iterator` instead of an integer counter

Signature:

~~~java
public static MethodHandle iteratedLoop(
        MethodHandle iterator, MethodHandle init, MethodHandle body);
~~~

Parameter diagram:

~~~text
iterator: (A...)Iterator<T>    (handle returning Iterator or subtype)
init    : (A...)V              (or null -> default V)
body    : (V accumulator, T element, A... externalArgs)V
----------------------------------------------------------
result  : (A...)V

If body returns void:
body    : (T element, A... externalArgs)void
result  : (A...)void
~~~

Mechanism:

~~~java
Iterator<T> it = iterator(externalArgs);
V acc = init(externalArgs);
while (it.hasNext()) {
    T element = it.next();
    acc = body(acc, element, externalArgs);
}
return acc;
~~~

This is **pseudocode** for the non-void accumulator case. The `element` variable comes from `Iterator.next()`, not an `int` counter.

### 5.1. `iterator=null`: automatically calling `Iterable.iterator()`

When passing `null` in the `iterator` position, the combinator uses a default iterator handle that behaves like `Iterable.iterator()` on the **first external argument**. The type of the first argument must be `Iterable` or a compatible subtype; that is why the following call is valid:

~~~java
MethodHandle iterated = MethodHandles.iteratedLoop(null, initText, join);
Iterable<String> values = List.of("A", "B", "C");
String joined = (String) iterated.invokeExact(values);
~~~

These are illustrative statements after `initText` and `join` are created with the right types; the full example appears in the next section. The type of the created handle is `(Iterable)String` if the signature of `initText`/`join` uses `Iterable.class` as the external argument. When calling `invokeExact`, the variable `values` has static type `Iterable<String>` (erasure is `Iterable`), which matches the handle. If you use a variable declared as `List<String>` directly at the call site, the descriptor may be `List` and **will not match `invokeExact`**; assign/cast it to `Iterable` or use `invoke` with appropriate conversion.

There is no way to write `Iterable<String>.class` or `Iterator<String>.class`: type arguments are erased, and `MethodType` signatures use `Iterable.class`/`Iterator.class`.

### 5.2. Non-null `iterator`: explicitly creating an Iterator

You can also pass a handle such as:

~~~java
private static Iterator<String> iteratorFor(Iterable<String> data) {
    return data.iterator();
}
~~~

When looking up this helper with return type `Iterator.class` and input `Iterable.class`, you can call:

~~~java
MethodHandle explicit = MethodHandles.iteratedLoop(iteratorHandle, initText, join);
~~~

`iteratorHandle` is returned from `Lookup.findStatic(...)` and must have return type `Iterator` or a subtype; it can accept external arguments `A...`. This approach is suitable when you need to read from an adapter, choose a special iterator, or compute an iterator from a non-`Iterable` input; it still must satisfy the signature rules of the clauses.

### 5.3. Accumulator is the result, not the element

String joining example:

~~~java
private static String empty(Iterable<String> input) { return ""; }

private static String combine(String accumulated, String item,
                              Iterable<String> input) {
    return accumulated.isEmpty() ? item : accumulated + "|" + item;
}
~~~

The handle `initText` has type `(Iterable)String`; `join` has type `(String,String,Iterable)String`. Even though `input` is the first external argument of the **loop**, in `body` it comes **after** the two internal positions `accumulated` and `item`.

Traversing `["A","B","C"]` in the order returned by the iterator:

~~~text
initial acc:  ""
item A:       "A"
item B:       "A|B"
item C:       "A|B|C"
result:       "A|B|C"
~~~

With an empty list, `init` is still called, `body` is not called at all, and the result is an empty string. The loop does not guarantee a **new traversal order**: the order depends on the iterator of the collection you provide, and the iterator may be unstable if the collection is modified concurrently.

### 5.4. Runtime element types and erasure

`Iterator<String>` is only a compile-time generic contract; at the method handle level, the iterator returns elements via erased `Object`. The combinator needs to convert each element to `T` declared by `body`, using type conversion rules matching `MethodHandle.asType`.

Therefore, if the actual Iterator source contains an element of the wrong type, you may encounter a `ClassCastException` or another conversion error **during iteration**, rather than always seeing the error immediately when calling `iteratedLoop`. Modifying the collection while iterating can trigger iterator errors (such as `ConcurrentModificationException` with fail-fast iterators in certain situations). The combinator does not swallow those errors and also **does not automatically close** an arbitrary resource/stream; if the iterator holds a resource that needs closing, its lifecycle must be managed externally.

## 6. Complete Java 17+ program for all three combinators

Create the file **`LoopCombinatorsDemo.java`**. This example includes: a generic `loop` with two clauses, both `countedLoop` overloads, `iteratedLoop` with the default iterator and an explicit iterator, and the empty input case.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Iterator;
import java.util.List;

public class LoopCombinatorsDemo {
    private static int one(int limit) { return 1; }
    private static int next(int i, int acc, int limit) { return i + 1; }
    private static int multiply(int i, int acc, int limit) { return i * acc; }
    private static boolean keepGoing(int i, int acc, int limit) { return i < limit; }
    private static int result(int i, int acc, int limit) { return acc; }

    private static int iterations(int n) { return n; }
    private static int initial(int n) { return 0; }
    private static int evenIndexSum(int total, int i, int n) { return total + 2 * i; }

    private static int from(int start, int end) { return start; }
    private static int to(int start, int end) { return end; }
    private static int zeroRange(int start, int end) { return 0; }
    private static int addIndex(int total, int i, int start, int end) { return total + i; }

    private static String empty(Iterable<String> input) { return ""; }
    private static String combine(String accumulated, String item, Iterable<String> input) {
        return accumulated.isEmpty() ? item : accumulated + "|" + item;
    }
    private static Iterator<String> iteratorFor(Iterable<String> input) {
        return input.iterator();
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // 1. Generic loop: two clauses, state i and acc.
        MethodHandle initFactorial = lookup.findStatic(
                LoopCombinatorsDemo.class, "one", MethodType.methodType(int.class, int.class));
        MethodHandle inc = lookup.findStatic(
                LoopCombinatorsDemo.class, "next",
                MethodType.methodType(int.class, int.class, int.class, int.class));
        MethodHandle mult = lookup.findStatic(
                LoopCombinatorsDemo.class, "multiply",
                MethodType.methodType(int.class, int.class, int.class, int.class));
        MethodHandle predicate = lookup.findStatic(
                LoopCombinatorsDemo.class, "keepGoing",
                MethodType.methodType(boolean.class, int.class, int.class, int.class));
        MethodHandle finish = lookup.findStatic(
                LoopCombinatorsDemo.class, "result",
                MethodType.methodType(int.class, int.class, int.class, int.class));

        MethodHandle generic = MethodHandles.loop(
                new MethodHandle[] { null, inc },
                new MethodHandle[] { initFactorial, mult, predicate, finish });
        System.out.println("generic type = " + generic.type());
        System.out.println("factorial(5) = " + (int) generic.invokeExact(5));
        System.out.println("factorial(0) = " + (int) generic.invokeExact(0));

        // 2. Counted loop: i = 0..n-1.
        MethodHandle count = lookup.findStatic(
                LoopCombinatorsDemo.class, "iterations",
                MethodType.methodType(int.class, int.class));
        MethodHandle start = lookup.findStatic(
                LoopCombinatorsDemo.class, "initial",
                MethodType.methodType(int.class, int.class));
        MethodHandle body = lookup.findStatic(
                LoopCombinatorsDemo.class, "evenIndexSum",
                MethodType.methodType(int.class, int.class, int.class, int.class));
        MethodHandle counted = MethodHandles.countedLoop(count, start, body);
        System.out.println("counted type = " + counted.type());
        System.out.println("counted(4) = " + (int) counted.invokeExact(4));
        System.out.println("counted(0) = " + (int) counted.invokeExact(0));

        // 3. Counted loop over range [start,end).
        MethodHandle lo = lookup.findStatic(
                LoopCombinatorsDemo.class, "from",
                MethodType.methodType(int.class, int.class, int.class));
        MethodHandle hi = lookup.findStatic(
                LoopCombinatorsDemo.class, "to",
                MethodType.methodType(int.class, int.class, int.class));
        MethodHandle initRange = lookup.findStatic(
                LoopCombinatorsDemo.class, "zeroRange",
                MethodType.methodType(int.class, int.class, int.class));
        MethodHandle rangeBody = lookup.findStatic(
                LoopCombinatorsDemo.class, "addIndex",
                MethodType.methodType(int.class, int.class, int.class, int.class, int.class));
        MethodHandle ranged = MethodHandles.countedLoop(lo, hi, initRange, rangeBody);
        System.out.println("range type = " + ranged.type());
        System.out.println("range[2,5) = " + (int) ranged.invokeExact(2, 5));
        System.out.println("range[5,2) = " + (int) ranged.invokeExact(5, 2));

        // 4. Default iterator (iterator=null), external arg is Iterable.
        MethodHandle initText = lookup.findStatic(
                LoopCombinatorsDemo.class, "empty",
                MethodType.methodType(String.class, Iterable.class));
        MethodHandle join = lookup.findStatic(
                LoopCombinatorsDemo.class, "combine",
                MethodType.methodType(String.class, String.class, String.class, Iterable.class));
        MethodHandle iterated = MethodHandles.iteratedLoop(null, initText, join);
        Iterable<String> data = List.of("A", "B", "C");
        System.out.println("iterated type = " + iterated.type());
        System.out.println("joined = " + (String) iterated.invokeExact(data));
        Iterable<String> emptyItems = List.of();
        System.out.println("empty joined = [" + (String) iterated.invokeExact(emptyItems) + "]");

        // 5. User-supplied iterator handle.
        MethodHandle iterator = lookup.findStatic(
                LoopCombinatorsDemo.class, "iteratorFor",
                MethodType.methodType(Iterator.class, Iterable.class));
        MethodHandle explicit = MethodHandles.iteratedLoop(iterator, initText, join);
        System.out.println("explicit type = " + explicit.type());
        System.out.println("explicit joined = " + (String) explicit.invokeExact(data));
    }
}
~~~

Run from the directory containing the file with JDK 17 or later:

~~~bash
javac --release 17 LoopCombinatorsDemo.java
java LoopCombinatorsDemo
~~~

**Exact `stdout`:**

~~~text
generic type = (int)int
factorial(5) = 120
factorial(0) = 1
counted type = (int)int
counted(4) = 12
counted(0) = 0
range type = (int,int)int
range[2,5) = 9
range[5,2) = 0
iterated type = (Iterable)String
joined = A|B|C
empty joined = []
explicit type = (Iterable)String
explicit joined = A|B|C
~~~

The code was compiled with `javac --release 17` on JDK 21 and ran successfully; the output above matches the `System.out.println` statements. Using `--release 17` ensures the target language and Java SE API are compatible with Java 17.

### 6.1. Reading the results by group

**Generic loop:** `generic.type()` is `(int)int`, meaning the outside only provides `limit`, while `i` and `acc` are managed internally. The two clauses receive the same state in order and `pred` runs after multiplication, giving `factorial(5)=120`.

**Counted:** `counted.type()` is `(int)int`. `body` takes `total` then `i`, so `counted(4)=0+2+4+6=12` and `counted(0)=0`.

**Range:** `ranged.type()` is `(int,int)int` because the inputs are `start` and `end`. The range `[2,5)` has exact three indices 2,3,4; the range `[5,2)` has no elements, returning the initial state 0.

**Iterated:** `iterated.type()` and `explicit.type()` are both `(Iterable)String`. In the first case, `iterator=null` causes the combinator to use `Iterable.iterator()`; in the second case, it calls `iteratorFor`. The elements pass through `combine` in the order `A,B,C`. The empty list case returns `""`, so the output is `empty joined = []`.

## 7. Matching `MethodType` and invoking properly via `invokeExact`

The three combinators produce a `MethodHandle` whose type is computed from the signatures of its components. They do not automatically create a method that "accepts any `Object`", and `invokeExact` **does not automatically cast** parameters and return values.

Example:

~~~java
// generic.type() == (int)int
int ok = (int) generic.invokeExact(5);

// iterated.type() == (Iterable)String
Iterable<String> words = List.of("x", "y");
String joined = (String) iterated.invokeExact(words);
~~~

This is an illustrative snippet inside a method where the handles `generic` and `iterated` were created earlier. Easy-to-make wrong calls:

~~~java
// long result = (long) generic.invokeExact(5);
// Wrong: call site expects long, handle returns int.

// List<String> list = List.of("x", "y");
// String result = (String) iterated.invokeExact(list);
// Wrong: call site passes List, handle requires Iterable.
~~~

`MethodHandle.invoke(...)` can apply certain conversions according to `asType` rules, whereas `invokeExact(...)` requires the call-site descriptor to match `handle.type()` completely. When designing a library with dynamic inputs, you can use `asType`/`bindTo`/`dropArguments`/`filterArguments` if you need to **adapt intentionally**, rather than adding random casts.

Helpers used in real code must be looked up with the exact primitive and reference signatures. For example, `MethodType.methodType(boolean.class,int.class,int.class,int.class)` is the predicate signature of the generic loop, different from `MethodType.methodType(Boolean.class,...)`. A single wrong parameter type or order can cause `NoSuchMethodException` at lookup, or `IllegalArgumentException` when composing the combinator.

## 8. Why isn't `loop` automatically more readable than a Java `for` loop?

For ordinary work, the program:

~~~java
int sum = 0;
for (int i = 0; i < values.length; i++) {
    sum += values[i];
}
~~~

is much clearer than building a MethodHandle graph. This snippet is only illustrative in a scope that has `int[] values`; it is not a standalone Java file. Loop combinators are valuable when **the operation itself needs to be constructed at runtime**, for example:

- A data pipeline library that stores stages as `MethodHandle`s and wants to bring loop logic into the same combinator chain.
- A runtime compiler or DSL interpreter that configures predicate/step/initializer dynamically while still wanting a `MethodHandle` call with a concrete type.
- Method handle adapters that need to compose a processing loop with `guardWithTest`, `filterArguments`, `collectArguments`, or dynamic call sites.
- A system generating data processors from a runtime schema, where steps are already handles and a `for` primitive cannot be hard-coded at compile time.

You **should not** convert every `for-each` into `iteratedLoop` to "optimize". Performance depends on how the handle is built, call site stability, JIT, object allocation, and workload. Measure with an appropriate benchmark (such as JMH); do not claim that combinators are always faster than regular Java loops.

## 9. Common errors and how to debug

| Symptom | Phase | Typical cause | How to fix |
| --- | --- | --- | --- |
| `IllegalArgumentException` when building `loop` | Handle creation | Invalid clause, missing predicate, mismatched `init`/`step` types, inconsistent finalizers | Print `type()` of each component, check `init,step,pred,fini` order |
| Loop runs wrong number of times with `loop` | Runtime | Misunderstanding that `pred` runs **before** `step` | Remember each clause runs step then pred; trace one cycle |
| Infinite loop | Runtime | No predicate returns `false` | Ensure a realistic exit path and bounded input |
| `IllegalArgumentException` when building `countedLoop` | Handle creation | `iterations`/`start`/`end` does not return `int`; `body` lacks `int` counter in right position | Check `(V,int,A...)V` or `(int,A...)void` |
| Wrong `countedLoop` result despite right types | Runtime | Swapped the two `int`s `acc` and `i`; compiler cannot catch it | Name clearly and test with small iteration counts |
| `ClassCastException` during iteration | Runtime | Iterator provides an element incompatible with `body`'s `T` after erasure | Validate data source or body type |
| `IllegalArgumentException` when building `iteratedLoop` | Handle creation | Iterator handle does not return `Iterator`, or external args are incompatible | Use return type `Iterator.class` and check `(A...)` |
| `WrongMethodTypeException` when calling `invokeExact` | Runtime | Call site type differs from `handle.type()`, including return type | Print `handle.type()`; cast/assign variable to right type or explicitly adapt |
| `NoSuchMethodException` on `Lookup.findStatic` | Lookup | Wrong helper function name or primitive/reference descriptor | Recheck method declaration and `MethodType` |
| `IllegalAccessException` on `Lookup.findStatic` | Lookup | `private` method inaccessible from the lookup class | Create lookup in a caller with access or adjust public API appropriately |
| `NullPointerException` in body | Runtime | `init=null` produces `null` reference state and body dereferences it | Provide `init` that creates valid state |
| Loop stops abruptly due to exception | Runtime | `step`/`pred`/`body`/iterator throws an error | Handle the cause; combinator does not automatically retry or roll back state |

### Systematic debugging

1. **Print types before composing:** `System.out.println(init.type())`, `body.type()`, `pred.type()`, and after creation, `loop.type()`. Type mismatches should be resolved at this step.
2. **Identify state and external args:** write out the `(V...,A...)` diagram, avoiding swapping `i` with the accumulator since both are often `int`.
3. **Test boundary inputs:** 0 iterations, `start==end`, `start>end`, empty Iterator, one-element Iterator, small `limit`. For generic `loop`, specifically test the step/pred order.
4. **Evaluate errors by phase:** `Lookup.findStatic` can throw `NoSuchMethodException`/`IllegalAccessException`; the combinator can throw `IllegalArgumentException`; invoking the handle can encounter `WrongMethodTypeException` or an exception from the target.
5. **Do not hide the cause:** `MethodHandle` usually propagates the target's exception directly, without wrapping it in `InvocationTargetException` by default like `java.lang.reflect.Method.invoke`.
6. **Limit side effects:** a `step` with side effects may have already run before `pred` detects stopping in generic `loop`. If the body performs I/O or writes data, recovery logic must be designed at the application layer.

## 10. Constraints to remember when using this API

### 10.1. Parameter types are truly a contract

Formulas to memorize:

~~~text
loop:
  clause = [init, step, pred, fini]
  result.type() = (A...)R

countedLoop(iterations, init, body):
  iterations: (A...)int
  init:       (A...)V           [or null]
  body:       (V,int,A...)V     [or (int,A...)void]
  result:     (A...)V           [or void]

countedLoop(start,end,init,body):
  start/end:  (A...)int
  init:       (A...)V           [or null]
  body:       (V,int,A...)V     [or (int,A...)void]
  result:     (A...)V           [or void]

iteratedLoop(iterator,init,body):
  iterator:   (A...)Iterator    [or null, uses first A as Iterable]
  init:       (A...)V           [or null]
  body:       (V,T,A...)V       [or (T,A...)void]
  result:     (A...)V           [or void]
~~~

**Note:** `(A...)` in the table is the full form for clarity. The Javadoc allows many handles to take effective **prefixes** of the external parameter list and pads unused trailing parameters; `iteratedLoop` also has logic to adapt from erased `Iterator.next():Object` to `T`. This is not an arbitrary argument-reordering mechanism.

### 10.2. `null` means different things in each API

- `loop`: a `null` clause position means missing `init`/`step`/`pred`/`fini` and the combinator supplies a default by rule; the entire loop is not allowed to lack a predicate.
- `countedLoop`: `init=null` is valid; `iterations` or `start/end` must not be null; `body` must not be null.
- `iteratedLoop`: **`iterator=null` is a valid design choice** to use `Iterable.iterator()` from the first external argument, `init=null` is valid, but `body=null` is invalid.

Do not apply a single rule like "any null means an empty loop" to all three. Null in required positions can throw `NullPointerException` immediately upon handle creation.

### 10.3. Do not mix error types and termination conditions

Normal termination is:

- `loop`: a `pred` returns `false` and `fini` produces the result.
- `countedLoop`: the counter has completed the iteration count or reached end-exclusive.
- `iteratedLoop`: `Iterator.hasNext()` returns `false`.

Meanwhile, a target handle throwing an exception is a **failure**, not a `false` value or an empty iteration. If you need to handle recoverable exceptions systematically, design it with error-handling combinators like `MethodHandles.catchException`, `tryFinally`, or a surrounding orchestration layer; their conditions/types must be designed appropriately rather than blindly catching every `Throwable`.

## 11. Self-check questions

**Question 1.** In a generic `loop` with `new MethodHandle[]{init,step,pred,fini}`, which function runs first in each clause: `step` or `pred`?

**Answer:** `step` first, the state is updated, and then `pred` runs. Different from the specialized `whileLoop` which has the predicate before the body.

**Question 2.** Given `countedLoop(iterations, init, body)` with `iterations=4`; which values does the counter run through?

**Answer:** `0,1,2,3`. End-exclusive, four iterations in total.

**Question 3.** For the four-handle overload `countedLoop(start,end,init,body)`, `start=3` and `end=3`, how many times does the body run?

**Answer:** Zero times; returns the accumulator created by `init` (or default `V` when `init=null`).

**Question 4.** If `body(int acc,int i,int n)` returns `int`, what type must `init` return?

**Answer:** `int` (the `V` type of `body`), and `init`'s parameters must be compatible with the external parameter list `A...`. The counter `i` is not among `init`'s parameters.

**Question 5.** Where does `iteratedLoop(null,init,body)` get its iterator from?

**Answer:** From `Iterable.iterator()` on the **first** external argument, which has type `Iterable` or a valid subtype.

**Question 6.** Can `iteratedLoop` have a `void`-returning body?

**Answer:** Yes. The body then has the form `(T,A...)void` and the loop handle returns `void`, with no result accumulator.

**Question 7.** If `body` takes `String element` but the actual iterator returns `Integer`, what happens?

**Answer:** The combinator can be created because the generic `Iterator` is erased; during iteration, converting the element type to `String` may throw `ClassCastException`.

**Question 8.** `generic.type()` is `(int)int`. Can you use `long x=(long)generic.invokeExact(5)` without adapting?

**Answer:** No. `invokeExact` requires the call-site return type to be exact `int`; use `int` and convert to `long` afterward, or use an appropriate adapter.

**Question 9.** Should `loop` be used for all iterations to improve performance?

**Answer:** No. For logic known at compile time, regular `for`/`while` is clearer; MethodHandle combinators are useful when the control flow itself is constructed from handles at runtime. Performance needs to be benchmarked.

## Official documentation

- [Java SE 21 — MethodHandles.loop, countedLoop, and iteratedLoop](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Java SE 17 — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Java SE 21 — MethodHandle.invokeExact and invoke](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 21 — MethodType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html)
