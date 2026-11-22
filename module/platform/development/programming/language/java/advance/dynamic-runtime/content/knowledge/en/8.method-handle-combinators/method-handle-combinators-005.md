# 8.5 Distinguishing `collectArguments` from `foldArguments` via Data Flow

The two combinators `java.lang.invoke.MethodHandles.collectArguments` and `MethodHandles.foldArguments` both build a new `MethodHandle` by **running a preprocessing handle first**, and only then calling `target`. Both can turn the output of the preprocessing step into an argument of `target`, but they differ at the decisive point: **whether the inputs to the preprocessing step are forwarded intact to `target` or not**.

- **`collectArguments`:** `filter` processes a **separate** group of arguments; this group is **replaced** by the result of the filter when calling target. The arguments that the filter receives do not automatically pass forward to target.
- **`foldArguments`:** `combiner` processes a group of arguments **shared with target**. The result of the combiner is **inserted before that group of arguments** when calling target; the original arguments themselves still pass forward.

This is the core content of the lesson. Read the `MethodType` signatures and the path of **each value** instead of only looking at the final result, because many simple examples produce the same result even though the call structures differ.

This lesson uses **Java 17+**. The functions presented are in `java.lang.invoke.MethodHandles`; a `MethodHandle` is a typed reference to the ability to invoke a method/constructor/field or a combinator chain.

## 1. Four Concepts to Know First

| Term | Role |
| --- | --- |
| `target` | The handle that will be called **last**, receives the final inputs and determines the return type of the adapter |
| `filter` of `collectArguments` | Processes a separate set of arguments, can return **a value** to replace one argument position of target |
| `combiner` of `foldArguments` | Processes some arguments **that are simultaneously forwarded to target**, can return an additional value |
| `pos` | Starting position in the parameter list; **0-based**, counted on the type of `target` |

Both combinators **create a new handle**; creating the adapter does not yet call the filter, combiner, or target. They execute when the adapter is invoked. When preprocessing throws an exception, target will **not be called** in that invocation. The normal sequence is *preprocess first, target after*, not target first and then filtering the return value.

Further distinction: `filterReturnValue` processes **the result of target**, whereas the two combinators being studied process **the inputs before calling target**. `asCollector` is used to pack multiple arguments into an array, which also differs from `collectArguments`.

## 2. Looking at the Same target and the Same filter

Define two Java methods with types:

~~~java
static String prepare(String a, String b) {
    return "<" + a + "+" + b + ">";
}

static String target(String merged, String left, String right) {
    return merged + " | " + left + " | " + right;
}
~~~

These are **two illustrative methods**, not a standalone program. When using `MethodHandles.Lookup.findStatic` to obtain the handles:

~~~text
prepare.type() = (String,String)String
target.type()  = (String,String,String)String
~~~

Consider `A`, `B`, `C`, `D` as **four different input strings**. If you want `prepare(A,B)` to produce the string `<A+B>` and then pass `C,D` into the remaining two parameters of target, use `collectArguments`. If you want target to receive **`A,B` themselves again**, alongside `<A+B>`, use `foldArguments`.

### 2.1. Data Flow of `collectArguments`

~~~java
MethodHandle collected = MethodHandles.collectArguments(targetHandle, 0, prepareHandle);
~~~

Call flow:

~~~text
caller: collected(A, B, C, D)
             │  │  │  │
             └──┘  │  │
                │   │  │
       prepare(A, B) │  │
                │    │  │
             "<A+B>" │  │
                └────┴──┘
                      │
              target("<A+B>", C, D)
                      │
                "<A+B> | C | D"
~~~

`prepare` receives `A,B`; `target` only receives **the result** `<A+B>` and two **other** arguments `C,D`. The adapter must accept **four** parameters:

~~~text
targetHandle.type() = (String,String,String)String
prepareHandle.type()= (String,String)String
collected.type()    = (String,String,String,String)String
~~~

Specifically, position 0 of target was originally `merged` of type `String`; `collectArguments` **replaces one parameter** `merged` with **two parameters** `a,b` needed to run the filter. After the filter returns `String`, target receives three arguments of its exact types again.

### 2.2. Data Flow of `foldArguments`

~~~java
MethodHandle folded = MethodHandles.foldArguments(targetHandle, prepareHandle);
~~~

Call flow:

~~~text
caller: folded(A, B)
              │  │
              ├──┤
              │  └─────┐
              ▼        │
       prepare(A, B)   │
              │        │
           "<A+B>"     │
              │        │
              └──┐     │
                 ▼     ▼
          target("<A+B>", A, B)
                 │
            "<A+B> | A | B"
~~~

The adapter receives **only two arguments** `A,B`. They are used **twice along the data flow**: sent into `prepare` first, then forwarded intact to `target` alongside the result `<A+B>`.

~~~text
targetHandle.type() = (String,String,String)String
prepareHandle.type()= (String,String)String
folded.type()       = (String,String)String
~~~

From `target(merged,left,right)`, `foldArguments` causes the `merged` value to be **computed from** `left,right`. The call site does not have to additionally supply `merged`.

### 2.3. Direct Comparison Table

| Comparison Point | `collectArguments(target,0,filter)` | `foldArguments(target,combiner)` |
| --- | --- | --- |
| Preprocessing handle | `filter(String,String) -> String` | `combiner(String,String) -> String` |
| What does the adapter receive? | `A,B,C,D` | `A,B` |
| Return value of the previous step | `<A+B>` | `<A+B>` |
| What does target receive? | `target(<A+B>,C,D)` | `target(<A+B>,A,B)` |
| Are the preprocessing inputs themselves forwarded to target? | **No**, unless separate other arguments are designed to carry the same values | **Yes**, according to the fold type contract |
| Number of adapter arguments | 4 | 2 |
| Illustrative result | `<A+B> | C | D` | `<A+B> | A | B` |

Both handles still have the **same return type as target**; the difference lies in the **adapter inputs** and how arguments are forwarded.

## 3. General Rules When `filter`/`combiner` Has a Result

Let `T` denote the return type of target, `V` the intermediate value type, `P...` the preceding parameters, `A...` the parameters of the preprocessing function, and `S...` the remaining parameters.

**`collectArguments(target, pos, filter)`:**

~~~text
target(P..., V, S...) -> T
filter(A...)         -> V

adapter(P..., A..., S...) -> T:
    v = filter(A...)
    return target(P..., v, S...)
~~~

The filter takes **the new argument group of the adapter at `pos`**, replacing a single argument of type `V` of target. `A...` **is no longer present** in the target call, unless other positions of the adapter bring the same values.

**`foldArguments(target, pos, combiner)`:**

~~~text
target(P..., V, A..., S...) -> T
combiner(A...)             -> V

adapter(P..., A..., S...) -> T:
    v = combiner(A...)
    return target(P..., v, A..., S...)
~~~

The combiner computes `v` from **the exact `A...` group that is still used by target**. The `A...` group is not lost after the preprocessing step.

Both require `V` to **match exactly** the target argument type at `pos`. The corresponding parameter types of combiner/fold must also match exactly the positions it uses. Combinators **do not automatically run `asType`** to fix type mismatches. Invalid shapes usually throw `IllegalArgumentException` **immediately when creating the adapter**.

### 3.1. Parameter Count Formulas

Let `N` be the number of parameters of target and `M` be the number of parameters of filter/combiner.

| Preprocessing Step | `collectArguments` | `foldArguments` |
| --- | --- | --- |
| Returns a value (non-`void`) | Adapter has `N - 1 + M` parameters | Adapter has `N - 1` parameters |
| Returns `void` | Adapter has `N + M` parameters | Adapter has **`N`** parameters |

`foldArguments` with a non-`void` result usually does not change the total parameter count by `M`: it drops one parameter of target because that parameter has been computed by the combiner, while the source parameter group `A...` already belongs to target.

These are **signature** formulas, not descriptions of the number of objects created or execution cost. Actual performance depends on target, combiner, JIT, and runtime circumstances.

## 4. Non-Zero `pos`: Looking at Data Flow to Avoid Confusion

Consider another target:

~~~java
static String withPrefix(String prefix, String merged,
                         String left, String right) {
    return prefix + ": " + merged + " | " + left + " | " + right;
}
~~~

The target handle has type `(String,String,String,String)String`. Choose `pos = 1`: `String merged` is the position where the preprocessing result is inserted/replaced, while `prefix` is the parameter **before** that position.

~~~java
MethodHandle collectAt1 =
        MethodHandles.collectArguments(prefixTarget, 1, prepareHandle);
MethodHandle foldAt1 =
        MethodHandles.foldArguments(prefixTarget, 1, prepareHandle);
~~~

Two results:

~~~text
collectAt1.type() = (String,String,String,String,String)String
foldAt1.type()    = (String,String,String)String
~~~

Calls and the path of values:

~~~text
collectAt1("P", "A", "B", "C", "D")
  prepare("A","B") -> "<A+B>"
  withPrefix("P","<A+B>","C","D")
  => "P: <A+B> | C | D"

foldAt1("P", "A", "B")
  prepare("A","B") -> "<A+B>"
  withPrefix("P","<A+B>","A","B")
  => "P: <A+B> | A | B"
~~~

In `foldAt1`, `pos=1` is not arbitrarily the position of the first argument passed to `prepare` in the final call: that position determines **the insertion point of the result** into the target signature; the parameters immediately following type `V` must match the combiner inputs. With `collectAt1`, the two filter inputs sit at positions 1 and 2 of the **adapter**, and are then replaced by a single result at position 1 of target.

With `foldArguments(target, combiner)` without a `pos` parameter, Java implicitly assumes `pos = 0`.

## 5. The Case Where Preprocessing Returns `void`

When `filter` or `combiner` returns no result, **no value is inserted into target**. However, the way arguments are passed still differs clearly. This is a common case for logging, tracing, or auditing.

Given:

~~~java
static void audit(String a, String b) {
    System.out.println("audit(" + a + "," + b + ")");
}

static String pair(String a, String b) {
    return a + "/" + b;
}
~~~

With `pairHandle.type() == (String,String)String` and `auditHandle.type() == (String,String)void`:

~~~java
MethodHandle collectedAudit =
        MethodHandles.collectArguments(pairHandle, 0, auditHandle);
MethodHandle foldedAudit =
        MethodHandles.foldArguments(pairHandle, auditHandle);
~~~

**`collectArguments` with a void filter:**

~~~text
collectedAudit("auditA","auditB","A","B")
  audit("auditA","auditB")  // arguments ONLY for audit
  pair("A","B")             // two DIFFERENT arguments
  => "A/B"

type: (String,String,String,String)String
~~~

**`foldArguments` with a void combiner:**

~~~text
foldedAudit("A","B")
  audit("A","B")  // sees the exact values target will receive
  pair("A","B")
  => "A/B"

type: (String,String)String
~~~

Choose **void fold** to log/inspect the values about to be used by target **without requiring the caller to pass an extra set of parameters**. Choose **void collect** when the preprocessing task needs **a separate set of inputs**, such as dedicated audit information not passed to target.

Do not interpret `void` as "no change at all": side effects of the audit function, if any, still occur before the target call. If audit throws an exception, target does not run.

## 6. Complete Runnable Java 17 Program

Create the file **`CollectFoldDemo.java`** with the following content. All `static` methods are in the same class so `MethodHandles.lookup().findStatic` can obtain their handles.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public final class CollectFoldDemo {
    static String prepare(String a, String b) {
        System.out.println("  prepare(" + a + "," + b + ")");
        return "<" + a + "+" + b + ">";
    }

    static String target(String merged, String left, String right) {
        System.out.println("  target(" + merged + "," + left + "," + right + ")");
        return merged + " | " + left + " | " + right;
    }

    static String withPrefix(String prefix, String merged, String left, String right) {
        System.out.println("  withPrefix(" + prefix + "," + merged + "," + left + "," + right + ")");
        return prefix + ": " + merged + " | " + left + " | " + right;
    }

    static void audit(String a, String b) {
        System.out.println("  audit(" + a + "," + b + ")");
    }

    static String pair(String a, String b) {
        System.out.println("  pair(" + a + "," + b + ")");
        return a + "/" + b;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle filter = lookup.findStatic(CollectFoldDemo.class, "prepare",
                MethodType.methodType(String.class, String.class, String.class));
        MethodHandle render = lookup.findStatic(CollectFoldDemo.class, "target",
                MethodType.methodType(String.class, String.class, String.class, String.class));
        MethodHandle collect = MethodHandles.collectArguments(render, 0, filter);
        MethodHandle fold = MethodHandles.foldArguments(render, filter);

        System.out.println("render: " + render.type());
        System.out.println("filter: " + filter.type());
        System.out.println("collect: " + collect.type());
        System.out.println("fold: " + fold.type());

        System.out.println("collect call:");
        String collected = (String) collect.invokeExact("A", "B", "C", "D");
        System.out.println("collect result: " + collected);

        System.out.println("fold call:");
        String folded = (String) fold.invokeExact("A", "B");
        System.out.println("fold result: " + folded);

        MethodHandle prefixTarget = lookup.findStatic(CollectFoldDemo.class, "withPrefix",
                MethodType.methodType(String.class, String.class, String.class, String.class, String.class));
        MethodHandle collectAt1 = MethodHandles.collectArguments(prefixTarget, 1, filter);
        MethodHandle foldAt1 = MethodHandles.foldArguments(prefixTarget, 1, filter);
        System.out.println("collect at pos=1: " + collectAt1.type());
        System.out.println("fold at pos=1: " + foldAt1.type());
        System.out.println("collect pos1 call:");
        System.out.println("collect pos1 result: " + (String) collectAt1.invokeExact("P", "A", "B", "C", "D"));
        System.out.println("fold pos1 call:");
        System.out.println("fold pos1 result: " + (String) foldAt1.invokeExact("P", "A", "B"));

        MethodHandle logger = lookup.findStatic(CollectFoldDemo.class, "audit",
                MethodType.methodType(void.class, String.class, String.class));
        MethodHandle pair = lookup.findStatic(CollectFoldDemo.class, "pair",
                MethodType.methodType(String.class, String.class, String.class));
        MethodHandle collectVoid = MethodHandles.collectArguments(pair, 0, logger);
        MethodHandle foldVoid = MethodHandles.foldArguments(pair, logger);
        System.out.println("collect void: " + collectVoid.type());
        System.out.println("fold void: " + foldVoid.type());
        System.out.println("collect void call:");
        System.out.println("collect void result: "
                + (String) collectVoid.invokeExact("auditA", "auditB", "A", "B"));
        System.out.println("fold void call:");
        System.out.println("fold void result: " + (String) foldVoid.invokeExact("A", "B"));

        try {
            MethodHandles.collectArguments(render, 0, MethodHandles.identity(int.class));
            throw new AssertionError("expected incompatible filter");
        } catch (IllegalArgumentException expected) {
            System.out.println("bad collect shape: " + expected.getClass().getSimpleName());
        }
        try {
            MethodHandles.foldArguments(render, MethodHandles.identity(int.class));
            throw new AssertionError("expected incompatible combiner");
        } catch (IllegalArgumentException expected) {
            System.out.println("bad fold shape: " + expected.getClass().getSimpleName());
        }
        try {
            String ignored = (String) fold.invokeExact("A", "B", "C");
            throw new AssertionError("expected wrong invocation");
        } catch (WrongMethodTypeException expected) {
            System.out.println("bad invoke type: " + expected.getClass().getSimpleName());
        }
    }
}
~~~

Run from the directory containing the file using **JDK 17 or higher**:

~~~bash
javac --release 17 CollectFoldDemo.java
java CollectFoldDemo
~~~

**Exact stdout** (lines starting with two spaces indicate calls inside `prepare`/`target`/`audit`/`pair`):

~~~text
render: (String,String,String)String
filter: (String,String)String
collect: (String,String,String,String)String
fold: (String,String)String
collect call:
  prepare(A,B)
  target(<A+B>,C,D)
collect result: <A+B> | C | D
fold call:
  prepare(A,B)
  target(<A+B>,A,B)
fold result: <A+B> | A | B
collect at pos=1: (String,String,String,String,String)String
fold at pos=1: (String,String,String)String
collect pos1 call:
  prepare(A,B)
  withPrefix(P,<A+B>,C,D)
collect pos1 result: P: <A+B> | C | D
fold pos1 call:
  prepare(A,B)
  withPrefix(P,<A+B>,A,B)
fold pos1 result: P: <A+B> | A | B
collect void: (String,String,String,String)String
fold void: (String,String)String
collect void call:
  audit(auditA,auditB)
  pair(A,B)
collect void result: A/B
fold void call:
  audit(A,B)
  pair(A,B)
fold void result: A/B
bad collect shape: IllegalArgumentException
bad fold shape: IllegalArgumentException
bad invoke type: WrongMethodTypeException
~~~

The `bad ... shape` lines occur **when building the adapter**: `identity(int)` has return type `int`, whereas target requires `String` at the replace/insert position, so the combinator rejects the shape with `IllegalArgumentException`. The `bad invoke type` line is different in nature: the `fold` adapter was created validly, but the caller tried to call `invokeExact` with three parameters instead of two, leading to `WrongMethodTypeException`. When debugging, determine whether the error is at the **handle creation step** or the **handle invocation step**.

The code catches `Throwable` in `main` because `invokeExact` declares `throws Throwable`. In real software, handle errors based on the business contract and do not swallow unexpected errors just to keep the application running.

## 7. How to Choose the Right Combinator in Applications

**When you want to convert multiple inputs into a single argument for target**, use `collectArguments`. For example, an adapter receives `(String amountText, String currency, OrderContext ctx)`; a filter turns the amount/currency pair into a `Money` object, and then target only needs `(Money, OrderContext)`. The filter receives **the first two arguments** and replaces the `Money` position that target needs. `OrderContext` is not automatically received or copied by the filter.

**When target still needs the original inputs alongside the result derived from them**, use `foldArguments`. For example, target receives `(Signature signature, byte[] payload, Key key)`, and combiner receives `(byte[] payload, Key key)` to compute the signature. The adapter only requires `(payload, key)`, computes `signature`, and then calls target with **the signature plus the original data**. The `Signature` type here only illustrates the business domain; it does not mean every signing algorithm can be expressed as a simple synchronous step.

**When you need to inspect/log parameters before target processes them**, `foldArguments` with a `void` combiner can share the parameter group with target. If the parameter set for the logger is completely **separate** from the target parameters, `collectArguments` with a `void` filter is more suitable.

**If you only need to transform a single individual parameter**, `filterArguments(target,pos,filter)` usually expresses the intent more concisely: a unary filter replaces one argument of target; this case is equivalent to a `collectArguments` with a filter taking one argument and returning a corresponding value. When the filter takes **multiple** arguments to compute one value, `collectArguments` clearly shows the replacement of an argument slice.

**If you need to reorder arguments** so that the types match, these combinators do not auto-permute: use `permuteArguments` (and possibly `dropArguments` or `insertArguments`) explicitly, then compare `type()` at each step.

## 8. Limitations and Common Mistakes

| Mistake | Consequence / How to Fix |
| --- | --- |
| Choosing `collectArguments` while thinking filter inputs also go into target | The adapter signature has a separate parameter group; target only receives **the filter result** and the remaining parameters. If you want to reuse inputs, consider `foldArguments`. |
| Choosing `foldArguments` with a target that does not have a parameter group matching the combiner's input types | Adapter creation fails (`IllegalArgumentException`). Read `target.type()` and `combiner.type()`. |
| Mistaking `pos` for the source method index or class index | `pos` is a **0-based index in target's parameter list**, directly tied to the replace/insert position. |
| Assuming `foldArguments` always creates extra parameters to pass to the combiner | The combiner reuses target parameters; the adapter usually has one fewer parameter if the combiner returns a value. |
| Thinking a `void` combiner in fold drops target parameters | No. It runs first; those same parameters still go into target. |
| Thinking a `void` filter in collect replaces a target parameter | There is no result to replace with; the adapter simply **inserts** additional parameters dedicated to the filter. |
| Treating an invalid adapter shape and an invalid adapter call type as the same kind of error | Invalid shape is usually `IllegalArgumentException` during composition; calling `invokeExact` with the wrong descriptor is `WrongMethodTypeException` at runtime. |
| Confusing `collectArguments` with `filterReturnValue` | Collect processes **arguments before target**; filterReturnValue processes **the result after target**. |
| Assuming the same type name means compatible even across different class loaders | `MethodType` uses the actual `Class<?>`; you must match the exact Java types, not rely on printed names. |
| Using `invokeExact` without considering the call site's return type | Both parameters and return type must match exactly; usually print `adapter.type()` and cast the return type intentionally. |

When working with multiple consecutive combinators, print the type after each step:

~~~java
System.out.println(filter.type());
System.out.println(targetHandle.type());
System.out.println(adapter.type());
~~~

The lines above are **diagnostic hints**, not a standalone program. A `MethodHandle` can represent an instance method (with a receiver parameter), a handle with bound parameters, or multiple nested adapters. Therefore, do not guess the argument count from the original Java method signature after transformations; trust the `type()` of the current handle.

## 9. Data Flow Self-Check

Suppose `target(String result, String x, String y)` and `combine(String x,String y) -> String` both already have handles with those exact types.

1. What adapter type does `collectArguments(target,0,combine)` have? With inputs `("A","B","C","D")`, what does target receive?
2. What adapter type does `foldArguments(target,combine)` have? With inputs `("A","B")`, what does target receive?
3. Replace the combiner with `audit(String,String) -> void`, and change target to `pair(String,String) -> String`. How do the adapters `collectArguments(pair,0,audit)` and `foldArguments(pair,audit)` differ?
4. When `combine` returns `int` while target requires `String` at the replace/insert position, when does the error occur? What if the adapter is valid, but `invokeExact` is called with a mismatched number of arguments?

**Answers:** (1) `(String,String,String,String)String`, target receives `(combine("A","B"),"C","D")`; (2) `(String,String)String`, target receives `(combine("A","B"),"A","B")`; (3) void collect adds **two separate arguments dedicated to audit**, void fold uses **the exact two arguments that target receives**; (4) an invalid shape causes `IllegalArgumentException` when creating the adapter, a mismatched `invokeExact` call type causes `WrongMethodTypeException` at invocation time.

**Official Documentation:** [`MethodHandles.collectArguments` / `foldArguments` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html), [`MethodHandle.invokeExact`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html) and [`MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html).