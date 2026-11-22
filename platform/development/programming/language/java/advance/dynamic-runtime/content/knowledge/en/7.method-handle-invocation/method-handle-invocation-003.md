# 7.3 `invoke`: type adaptation according to `asType` rules

In Java's `java.lang.invoke` API, each `MethodHandle` carries an **exact** method type (`MethodType`), consisting of a list of parameter types and a **return type**. However, a call to `handle.invoke(...)` can accept types at the call site that differ from the handle's type when they can be **adapted according to the rules of `MethodHandle.asType(...)`**. This is the key difference between `invoke` and `invokeExact`.

This lesson explains the two types to distinguish, how the JVM constructs the *call-site descriptor*, the allowed and disallowed conversions, boxing/unboxing scenarios, reference types, return types, common errors, as well as how to move from an `invoke` call to a reusable `asType` adapter. The example code is compatible with Java 17 and later.

## 1. The right mental model: the handle's type and the call's type

Suppose we have a Java method:

~~~java
static long add(long a, long b) {
    return a + b;
}
~~~

A handle created with `MethodHandles.Lookup.findStatic` for the method above has the type:

~~~text
(long,long)long
~~~

That information is returned by `handle.type()`. It is described by `MethodType.methodType(long.class, long.class, long.class)`: the first argument of `methodType` is the **return type**, and the subsequent arguments are the **parameter types**.

When writing the call:

~~~java
long result = (long) handle.invoke(3, 4);
~~~

the two expressions `3` and `4` have static type `int`. The return type required by the `(long)` cast is `long`. Therefore, the **type at the call site** (*call-site descriptor*, or symbolic method type) is:

~~~text
(int,int)long
~~~

It differs from the handle type `(long,long)long`. `invoke` can execute because `int` can **widen** to `long` for each parameter.

Conversely:

~~~java
long result = (long) handle.invokeExact(3, 4);
~~~

does not succeed: `invokeExact` requires the call-site type to **match** `(long,long)long` **exactly**. `(int,int)long` does not match, so it throws `WrongMethodTypeException`. To use `invokeExact`, you need to write `3L`, `4L`:

~~~java
long result = (long) handle.invokeExact(3L, 4L);
~~~

**Three terms to remember:**

| Term | Example | Role |
| --- | --- | --- |
| **Target method type** | `(long,long)long` | The actual type of the `MethodHandle`, read via `type()` |
| **Call-site type** | `(int,int)long` | The types of the arguments and the return type at the `invoke`/`invokeExact` expression itself emitted by the compiler |
| **Adapted method type** | `(int,int)long` | The type that `asType` can create to bridge from the call site to the target |

A common misconception is assuming that `invoke` inspects the **runtime values** of every argument and automatically picks the best overload. In reality, the compiler records the **static types at the call site**; at runtime, the runtime checks and applies conversions according to `asType` on the **already-selected handle**. It does not re-invoke `findStatic`, `findVirtual`, or select another overloaded method.

## 2. Where do `invokeExact` and `invoke` differ?

Both `invokeExact(Object... args)` and `invoke(Object... args)` are **signature-polymorphic** methods of `MethodHandle`. Do not interpret the `Object...` signature displayed in JavaDoc as a regular Java call taking an `Object[]` array. For normal Java source calls, the compiler emits a symbolic descriptor based on the **type of each expression** passed in and the return type context.

| Characteristic | `invokeExact` | `invoke` |
| --- | --- | --- |
| Checks method type? | Yes, **must equal** `handle.type()` **exactly** | Yes, **must equal exactly or be adaptable** via `asType` |
| Automatically widens `int` to `long`? | No | Yes, if the conversion is valid |
| Performs boxing/unboxing via adapter? | No | Yes, in cases permitted by `asType` |
| Casts reference types at runtime? | Does not adapt call-site type; method body still has its own casts | Can insert `checkcast` via adapter; fails if actual value has wrong type |
| Does return type at call site matter? | Very important, must match | Yes, and it can be adapted |
| Intended use | Calls whose types are completely known, needing no adapter | Calls needing a controlled set of conversions |
| If types are invalid | `WrongMethodTypeException` | `WrongMethodTypeException` if conversion cannot be formed; may encounter `ClassCastException`/`NullPointerException` during runtime conversion |

When the call-site type already **matches** the target type, both `invoke` and `invokeExact` go straight to the target behavior. When the types differ, `invoke` behaves **as if** it had called `handle.asType(callSiteType)` and then invoked the adapter with `invokeExact`. The JVM is permitted to optimize this, so **it does not necessarily allocate a physical adapter object for every call**.

### Diagram of a single `invoke` call

~~~text
Java source: (long) handle.invoke(3, 4)
          |
          v
Compiler records call-site type: (int,int)long
          |
          v
Actual type handle.type():        (long,long)long
          |
          v
Do the two types match? -- Yes --> invoke target
          |
          No
          |
          v
Is asType((int,int)long) possible?
          |
      +---+-----------------------+
      |                           |
     Yes                         No
      |                           |
      v                           v
Widen int -> long          WrongMethodTypeException
Widen int -> long
      |
      v
Invoke target add(long,long)
      |
      v
Return long per call-site type
~~~

The diagram only illustrates semantics. An implementation may compile/inline and eliminate intermediate steps, but must preserve observable behavior according to the API contract.

## 3. Complete example: `invoke` adapts, `asType` creates an explicit adapter

Save the following code to **`InvokeAdaptDemo.java`**:

~~~java
import java.lang.invoke.*;

public class InvokeAdaptDemo {
    static long add(long a, long b) {
        return a + b;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle sum = MethodHandles.lookup().findStatic(
            InvokeAdaptDemo.class, "add",
            MethodType.methodType(long.class, long.class, long.class)
        );

        System.out.println("targetType=" + sum.type());
        System.out.println("exact=" + (long) sum.invokeExact(3L, 4L));
        System.out.println("invoke=" + (long) sum.invoke(3, 4));

        Object boxed = sum.invoke(
            Integer.valueOf(5), Long.valueOf(6)
        );
        System.out.println(
            "boxed=" + boxed.getClass().getSimpleName() + ":" + boxed
        );

        MethodHandle generic = sum.asType(
            MethodType.methodType(
                Object.class, Object.class, Object.class
            )
        );

        Object result = generic.invokeExact(
            (Object) Integer.valueOf(7),
            (Object) Long.valueOf(8)
        );

        System.out.println("adapterType=" + generic.type());
        System.out.println("adapter=" + result);
        System.out.println("originalType=" + sum.type());
    }
}
~~~

Compile with Java 17 (or a newer compiler targeting 17) and run:

~~~sh
javac --release 17 InvokeAdaptDemo.java
java InvokeAdaptDemo
~~~

**Stdout:**

~~~text
targetType=(long,long)long
exact=7
invoke=7
boxed=Long:11
adapterType=(Object,Object)Object
adapter=15
originalType=(long,long)long
~~~

Explanation:

1. `sum.type()` has the type `(long,long)long` and does not change throughout the program.
2. `sum.invokeExact(3L, 4L)` succeeds because both parameters and the return type are exact `long`.
3. `sum.invoke(3, 4)` has call site `(int,int)long`; `invoke` accepts widening both parameters `int → long`.
4. `Object boxed = sum.invoke(Integer.valueOf(5), Long.valueOf(6))` uses call-site type `(Integer,Long)Object`. The adapter unboxes `Integer` to `int` then widens to `long`, unboxes `Long` to `long`, and **boxes the `long` return value into `Long`** to fit the `Object` type.
5. `sum.asType((Object,Object)Object)` creates a **new handle** accepting two `Object` parameters and returning `Object`. When passed an `Integer` and a `Long`, the adapter performs unboxing + widening, then boxing of the return value. This is a conditional conversion, not accepting arbitrary `Object`s.
6. `generic.invokeExact(...)` works because both arguments are **statically cast to `Object`** and the result is assigned to a variable of type `Object`. The call-site type is exact `(Object,Object)Object`.
7. `sum.type()` at the end is still `(long,long)long`: `MethodHandle` is immutable. `asType` does not modify the old handle. If `asType` is called with the exact current type, the API is permitted and by specification will return that same handle.

In the snippet above, the `(Object)` casts before `Integer` and `Long` are **very important for `invokeExact`**. If the casts are omitted, the Java compiler records a descriptor with `Integer`/`Long` parameters, which no longer matches `generic.type()` and the exact call will fail.

## 4. `asType` rules: converting from the **new type** to the **old type**

With `original.asType(newType)`, the adapter accepts arguments according to `newType`, converts them to the **parameter types of `original.type()`**, invokes original, and then converts **original's result** to the return type of `newType`.

For a normal fixed-arity handle, parameter types are matched **position by position** and the number of parameters must correspond. If the handle is a *variable-arity collector*, there are rules for collecting arguments into an additional array; see the later section.

Example:

~~~text
Original: (long,long)long
New:      (Object,Object)Object

Object #1 --cast/unbox/widen--> long \
                                      -> original.add(long,long) -> long
Object #2 --cast/unbox/widen--> long /                           |
                                                                    v
                                                               box Long -> Object
~~~

### Table of valid conversions and limits

| Conversion direction | `asType` rule | Example |
| --- | --- | --- |
| Primitive → same primitive | Kept unchanged | `long → long` |
| Primitive → different primitive | **Widening primitive** only, per Java method invocation conversion | `byte → int`, `int → long`, `float → double` |
| Primitive → narrower primitive | **Not** supported via `asType` | `long → int`, `int → short` will not be adapted |
| Primitive → reference | Boxing to wrapper, then reference widening if needed | `int → Integer`, `int → Number`, `long → Object` |
| Reference → reference | Runtime cast to target reference type if needed | `Object → String` can create an adapter, but the actual object must be `String` or `null` |
| Wrapper → primitive | Unboxing, may continue with widening | `Integer → long`; `Long → double` |
| `Object`/suitable supertype → primitive | Runtime unboxing of actual wrapper then suitable widening; static type must be capable of holding a valid wrapper | `Object` holding `Integer(5)` → `long` |
| `null` → primitive | No value to unbox | Throws `NullPointerException` at execution |
| Reference of wrong actual type | Reference cast or unboxing fails | Throws `ClassCastException` at execution |
| Return a value → `void` | Discard result | `(int)int → (int)void`: computation still runs but result is discarded |
| Return `void` → reference | Produce `null` | `(String)void → (String)Object` |
| Return `void` → primitive | Produce primitive default value | `void → int` yields `0`; `void → boolean` yields `false` |

**Read the table in the right direction.** When calling `asType(newType)`, **parameters** convert from **newType → old type**, whereas the **result** converts from **old type → newType**. Reversing the direction leads to wrong conclusions about narrowing/widening.

### Conversions that `asType` does not perform

- Does not convert numeric strings to numbers: `"123" → int` is not an `asType` conversion. To parse, write `Integer.parseInt` or a separate filter/adapter.
- Does not silently narrow `long` to `int` or `double` to `float`. If you want explicit cast-style conversion, look into `MethodHandles.explicitCastArguments(...)` or perform an explicit conversion before invoking.
- Does not treat `boolean` and `int` as interchangeable under `asType`; there is no primitive widening `boolean → int`.
- Does not automatically reorder parameters, drop/add parameters, or select an overloaded method. Those transformations require combinators such as `permuteArguments`, `dropArguments`, or a different handle.
- Does not guarantee that every reference can be unboxed into a primitive. For instance, `String` is neither a numeric wrapper nor a supertype of a numeric wrapper.
- Does not assume every `Object` holding a numeric wrapper can convert to every primitive: a `Long` cannot be *narrowed* to `int` via `asType`.

### Why can a reference cast be created even when two types are unrelated?

According to the `asType` JavaDoc, when both ends are reference types, the adapter can insert a runtime cast to the target type. Creating the adapter **does not necessarily fail immediately** if the static types are unrelated: the runtime value could be `null`. When actually passing through the adapter, a value that is not a suitable instance will cause the cast to throw `ClassCastException`.

For example, `String` and `Integer` do not have a subtype relationship. A reference-cast adapter may exist in some configurations; that does not mean an arbitrary `Integer` will become a `String`. **A cast is not a format conversion.**

## 5. Two different kinds of failure: unadaptable types vs. bad data during conversion

Distinguish two phases:

- **No valid type conversion at the signature level:** `asType` or `invoke` cannot form a valid bridge between the static method types. The result is typically `WrongMethodTypeException`.
- **Valid bridge, but runtime value fails conditions:** the adapter was created, yet the reference cannot be cast/unboxed or is `null` when a primitive is needed. You may get `ClassCastException` or `NullPointerException`.

These are two errors with different causes and fixes.

### Example 2: `WrongMethodTypeException` vs. `ClassCastException`/`NullPointerException`

Save **`InvokeErrorsDemo.java`**:

~~~java
import java.lang.invoke.*;

public class InvokeErrorsDemo {
    static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle handle = MethodHandles.lookup().findStatic(
            InvokeErrorsDemo.class, "add",
            MethodType.methodType(int.class, int.class, int.class)
        );

        System.out.println("exact=" + (int) handle.invokeExact(1, 2));
        System.out.println("invokeAsLong=" + (long) handle.invoke(1, 2));

        try {
            long unused = (long) handle.invokeExact(1, 2);
        } catch (WrongMethodTypeException ex) {
            System.out.println(
                "invokeExactReturn=" + ex.getClass().getSimpleName()
            );
        }

        try {
            int unused = (int) handle.invoke(1L, 2L);
        } catch (WrongMethodTypeException ex) {
            System.out.println(
                "invokeLongArgs=" + ex.getClass().getSimpleName()
            );
        }

        try {
            short unused = (short) handle.invoke(1, 2);
        } catch (WrongMethodTypeException ex) {
            System.out.println(
                "invokeNarrowReturn=" + ex.getClass().getSimpleName()
            );
        }

        try {
            handle.asType(
                MethodType.methodType(
                    short.class, int.class, int.class
                )
            );
        } catch (WrongMethodTypeException ex) {
            System.out.println(
                "asTypeNarrowReturn=" + ex.getClass().getSimpleName()
            );
        }

        Object bad = "two";
        try {
            int unused = (int) handle.invoke(bad, 2);
        } catch (ClassCastException ex) {
            System.out.println(
                "badObject=" + ex.getClass().getSimpleName()
            );
        }

        Object absent = null;
        try {
            int unused = (int) handle.invoke(absent, 2);
        } catch (NullPointerException ex) {
            System.out.println(
                "nullObject=" + ex.getClass().getSimpleName()
            );
        }
    }
}
~~~

~~~sh
javac --release 17 InvokeErrorsDemo.java
java InvokeErrorsDemo
~~~

**Stdout:**

~~~text
exact=3
invokeAsLong=3
invokeExactReturn=WrongMethodTypeException
invokeLongArgs=WrongMethodTypeException
invokeNarrowReturn=WrongMethodTypeException
asTypeNarrowReturn=WrongMethodTypeException
badObject=ClassCastException
nullObject=NullPointerException
~~~

Cases to understand individually:

1. `invokeExact(1,2)` cast to return `int` succeeds because the signature is exact `(int,int)int`.
2. `(long) handle.invoke(1,2)` is valid: the old return type `int` can widen to the call-site return type `long`.
3. `(long) handle.invokeExact(1,2)` throws `WrongMethodTypeException`: even though ordinary Java lets you assign `int` to `long`, `invokeExact` does **not** allow a different return type.
4. `handle.invoke(1L,2L)` requires parameter conversion `long → int`, which is forbidden primitive narrowing. The error is `WrongMethodTypeException`.
5. Both `(short) handle.invoke(1,2)` and `asType((int,int)short)` require result conversion `int → short`, which is forbidden, so they throw `WrongMethodTypeException`.
6. `Object bad = "two"`: the call site uses parameter type `Object`. The `Object → int` adapter **can be created** because an `Object` *could* hold an `Integer`; however, the actual value is a `String`, so unboxing throws `ClassCastException`.
7. `Object absent = null`: the adapter is valid, but unboxing `null` into `int` throws `NullPointerException`.

Both `WrongMethodTypeException` and cast/unbox errors can occur **before the target body runs**. However, when the target body throws an error of the same kind, you need to inspect the stack trace to distinguish the source. `MethodHandle.invoke` does not automatically wrap exceptions from the target in `InvocationTargetException` like `java.lang.reflect.Method.invoke`; the `throws Throwable` signature lets exceptions from the target propagate out.

## 6. How does the Java compiler determine the types at the call site?

A subtle pitfall is that `MethodHandle.invoke` is called via **signature polymorphism**: the argument types and return type at the call site directly determine the symbolic descriptor the JVM emits in bytecode. The compiler **does not perform ordinary Java method invocation conversions on the arguments** before generating the descriptor; instead, `invoke` is responsible for adapting when appropriate.

Consider a handle `(int)int` and these calls:

| Java source expression | Call-site descriptor | Meaning |
| --- | --- | --- |
| `int x = (int) h.invokeExact(2);` | `(int)int` | Exact match |
| `long x = (long) h.invokeExact(2);` | `(int)long` | Exact mismatch |
| `long x = (long) h.invoke(2);` | `(int)long` | Widen return `int → long` |
| `int x = (int) h.invoke((short) 2);` | `(short)int` | Widen argument `short → int` |
| `Object x = h.invoke(2);` | `(int)Object` | Box return `int → Integer` then receive as `Object` |
| `h.invoke(2);` as a **statement** | `(int)void` | `invoke` discards the result if target returns a value |
| `h.invokeExact(2);` as a **statement** | `(int)void` | Mismatch if handle returns `int` |

**The return part is an integral part of the descriptor.** Passing the same argument `2` while assigning to `int`, `long`, `Object`, or discarding the result can change the descriptor. Do not treat `(long)` before `invokeExact` like a cast on a result that has already been returned: here it participates in **determining the call-site return type before the invocation actually takes place**.

Example:

~~~java
Object number = Integer.valueOf(5);
int result = (int) h.invoke(number);
~~~

The call site has parameter **`Object`**, not `Integer`, even though the runtime value is an `Integer`. If the target takes `int`, the adapter can unbox the runtime `Integer`. But with `invokeExact`, `Object` differs from `int`, so it is still a mismatch.

### Note on passing literal `null`

An uncast `null` in a signature-polymorphic call has symbolic type `java.lang.Void` according to JavaDoc, not automatically `Object` or the type the target expects. When you want to control the call-site descriptor, cast explicitly, such as `(String) null` or `(Object) null`; with `invoke`, reference cast rules still apply and the target body may reject `null` for its own reasons.

Do not look up `invokeExact` via Reflection to call it like a normal method. `MethodHandle.invokeExact`/`invoke` have special JVM rules; `invokeWithArguments` is for dynamic `Object` list scenarios and has different semantics.

## 7. `findVirtual`: the receiver is also a parameter that must be adapted

A handle obtained via `Lookup.findVirtual` usually has the **receiver as its first parameter**, in addition to the parameters that Java source shows inside the parentheses of the instance method. Therefore, when calling an instance method through a method handle, the receiver type is also subject to `asType` adaptations.

For example, `String.substring(int)` has handle type:

~~~text
(String,int)String
~~~

even though the instance method's source only takes one `int`. The `String` in the first position is the receiver.

### Example 3: casting the receiver, widening an argument, and boxing/unboxing together

Save **`ReceiverAdaptDemo.java`**:

~~~java
import java.lang.invoke.*;

public class ReceiverAdaptDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle substring = MethodHandles.lookup().findVirtual(
            String.class, "substring",
            MethodType.methodType(String.class, int.class)
        );

        System.out.println("handleType=" + substring.type());

        Object receiver = "abcdef";
        Object inexact = substring.invoke(receiver, (short) 2);
        System.out.println("inexact=" + inexact);

        String exact = (String) substring.invokeExact("abcdef", 2);
        System.out.println("exact=" + exact);

        MethodHandle general = substring.asType(
            MethodType.methodType(
                Object.class, Object.class, Object.class
            )
        );
        Object result = general.invokeExact(
            (Object) "hello",
            (Object) Integer.valueOf(1)
        );
        System.out.println("general=" + result);

        try {
            Object wrongReceiver = Integer.valueOf(42);
            Object unused = substring.invoke(wrongReceiver, 1);
        } catch (ClassCastException ex) {
            System.out.println(
                "wrongReceiver=" + ex.getClass().getSimpleName()
            );
        }
    }
}
~~~

~~~sh
javac --release 17 ReceiverAdaptDemo.java
java ReceiverAdaptDemo
~~~

**Stdout:**

~~~text
handleType=(String,int)String
inexact=cdef
exact=cdef
general=ello
wrongReceiver=ClassCastException
~~~

**Explanation:**

- `substring.type()` is `(String,int)String`; the first `String` represents the receiver.
- `Object receiver = "abcdef"`; when calling `substring.invoke(receiver, (short) 2)`, the call site is `(Object,short)Object`. `asType` inserts a cast `Object → String`, widens `short → int`, and widens the reference return `String → Object`. The result is `"cdef"`.
- `substring.invokeExact("abcdef",2)` with return cast `String` has a completely matching descriptor, so it runs directly.
- `general` accepts `(Object,Object)Object`; the second `Object` holds `Integer(1)` so it unboxes to `int`, and the first `Object` holds a `String` so it casts to the `String` receiver.
- `wrongReceiver` holds an `Integer`: the adapter can be constructed from static `Object` to `String`, but the runtime cast fails with `ClassCastException`.

The wrong-receiver case is not "the JVM automatically searches for a matching `substring` on `Integer`". The handle still describes `String.substring(int)` itself; the conversion fails because the runtime `Object` is not a `String`.

## 8. Adapting the return type: boxing, discarding the result, and `void`

The return type directly affects the call. `asType` has three special rules for `void`:

1. **Target returns a value, call site wants `void`:** the result is discarded; the target still executes.
2. **Target returns `void`, call site wants a reference:** the adapter produces `null`.
3. **Target returns `void`, call site wants a primitive:** the adapter produces the default value; for example `0` for `int`, `false` for `boolean`.

If the target returns a primitive and the call site requests a suitable reference, the adapter can **box** the primitive return value. If the target returns a wrapper and the call site requests a primitive, the adapter can unbox (and widen if valid).

### Example 4: the result changes depending on the return type context

Save **`ReturnAdaptDemo.java`**:

~~~java
import java.lang.invoke.*;

public class ReturnAdaptDemo {
    static void log(String s) {
        System.out.println("log=" + s);
    }

    static int doubleIt(int n) {
        return n * 2;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle logger = MethodHandles.lookup().findStatic(
            ReturnAdaptDemo.class, "log",
            MethodType.methodType(void.class, String.class)
        );

        Object value = logger.invoke("alpha");
        System.out.println("voidAsObject=" + value);

        int zero = (int) logger.invoke("beta");
        System.out.println("voidAsInt=" + zero);

        MethodHandle doubleIt = MethodHandles.lookup().findStatic(
            ReturnAdaptDemo.class, "doubleIt",
            MethodType.methodType(int.class, int.class)
        );

        Object boxed = doubleIt.invoke(3);
        System.out.println(
            "boxed=" + boxed.getClass().getSimpleName() + ":" + boxed
        );

        doubleIt.invoke(4);
        System.out.println("ignoredResult=done");

        MethodHandle voidAdapter = doubleIt.asType(
            MethodType.methodType(void.class, int.class)
        );
        voidAdapter.invokeExact(5);
        System.out.println("voidAdapterType=" + voidAdapter.type());
    }
}
~~~

~~~sh
javac --release 17 ReturnAdaptDemo.java
java ReturnAdaptDemo
~~~

**Stdout:**

~~~text
log=alpha
voidAsObject=null
log=beta
voidAsInt=0
boxed=Integer:6
ignoredResult=done
voidAdapterType=(int)void
~~~

- In `Object value = logger.invoke("alpha")`, the target returns `void` and the call site requests `Object`, so the result is **produced as `null`**.
- In `int zero = (int) logger.invoke("beta")`, the target returns `void` and the call site wants `int`, so the result is `0`. This is an adapter-specific rule; **it does not mean** normal Java source allows casting a `void` method to `int`.
- `doubleIt.invoke(3)` is used with return type `Object`, so the number `6` is boxed into `Integer`.
- `doubleIt.invoke(4);` is an expression statement; the compiler generates call-site return type `void`. `invoke` accepts discarding the target's result. `voidAdapter` is the explicit equivalent for an `(int)void` handle.
- `voidAdapter.invokeExact(5);` must be written in statement context to have an exact `void` return. If you write `Object result = voidAdapter.invokeExact(5);`, the return mismatches and it will throw `WrongMethodTypeException`.

Do not confuse "a `void` target adapted to return `int`" with "a target that actually returns `int`". Supplying the default value is performed by the adapter, not by the method body.

## 9. Comparing `invoke`, `asType`, `invokeWithArguments`, and `explicitCastArguments`

Using the right API helps limit unintended conversions and avoid bugs caused by unclear call-site types.

| API | Meaning | When appropriate |
| --- | --- | --- |
| `handle.invokeExact(...)` | Does not adapt call-site type; requires exact match on both parameters and return | Need an exact type contract, call site known statically |
| `handle.invoke(...)` | Adapts as if `handle.asType(callSiteType)` when needed | Method handle is known, but caller uses some convertible types |
| `handle.asType(newMethodType)` | Creates a new handle with an explicit type; pairwise adapter per `asType` rules | Standardizing multiple type sources to a common API or reusing an adapter |
| `handle.invokeWithArguments(...)` | Takes an argument list as `Object[]`/`List<?>`; handles via generic invocation and API conversions | Number/types of arguments are built completely dynamically; tooling, scripts, bridge code |
| `MethodHandles.explicitCastArguments(target,newType)` | Allows additional **casting** operations beyond `asType` such as primitive narrowing | Explicit type conversion is intentionally required and data-loss risks are handled |

**Do not confuse `invokeWithArguments` with regular `invoke`.** `invokeWithArguments` performs conversion from dynamic arguments in an `Object` list and has special rules for variable-arity handles; it does not use the call-site descriptor generated by the compiler for a signature-polymorphic call. Switching APIs can change performance and where exceptions are thrown, so verify against the real signatures.

### Pattern for using `asType` in an adapter layer

This is an **illustrative snippet**, assuming a `MethodHandle target` with exact type `(long,long)long`, created as in example 3:

~~~java
MethodType api = MethodType.methodType(
    Object.class, Object.class, Object.class
);
MethodHandle adapter = target.asType(api);

// From here, the code uses the exact Object,Object -> Object API.
Object result = adapter.invokeExact(
    (Object) Integer.valueOf(10),
    (Object) Long.valueOf(20)
);
System.out.println(result); // 30
~~~

This snippet is not a standalone program because `target` is assumed to already exist. The idea is to pick **one type-normalization point**, obtain the adapter upfront, store it, and then have callers satisfy the adapter's exact descriptor. This makes the type contract easier to read and verify; there is no need to claim performance is always better without measuring with a benchmark.

### Varargs collector is an exception to consider separately

The pairwise analysis in section 4 applies to a **fixed-arity handle**. A `MethodHandle` with `isVarargsCollector()==true` can accept variable-arity calls at the trailing position, collecting arguments into an array per API rules. Therefore, you should not claim that `asType` always requires the same arity in **every** case.

If you need to avoid unexpected varargs transformations, you can use `asFixedArity()` to treat the handle as fixed arity; calls must then match the definite parameter count, or use combinators `asCollector` / `asSpreader` to express array collection/spreading explicitly. The main focus of this article is **type adaptation**, whereas collection/spreading is a separate topic and should not be used as a reason to confuse widening with changing arity.

## 10. Practical troubleshooting principles

When encountering `WrongMethodTypeException`, do not look only at runtime values. Check in order:

1. **Print `handle.type()`.** Write out both parameters and return type in full. For a virtual handle, do not forget the leading receiver.
2. **Deduce the call-site descriptor from source:** the static type of each argument expression (including `(short)`, `(Object)`, boxed wrappers, or literal `null`) and the return type from cast/assignment/statement context.
3. **If using `invokeExact`**, compare the two signatures **100%**: parameter count, each `Class<?>`, and return type. A Java source cast on the result does not fix a mismatch via post-call conversion.
4. **If using `invoke`**, check the validity of `asType(callSiteType)`, in the right direction for parameters and return. Primitive narrowing or wrong parameter count for a fixed-arity handle are common causes of `WrongMethodTypeException`.
5. **If you see `ClassCastException`**, the adapter may be valid at the type level, but the runtime object is not the right wrapper/reference type. Check `arg.getClass()` when `arg != null` and the type the target actually needs.
6. **If you see `NullPointerException`**, look for where `null` is unboxed to a primitive; also rule out an NPE originating inside the target method itself.
7. **If you see other errors**, determine whether it is an access error when creating the handle (`findStatic`/`findVirtual`/`Lookup`), a converter error, or an exception thrown by the target. `invoke` declares `throws Throwable`, so target exceptions can propagate directly.
8. **If using a varargs collector**, check `handle.isVarargsCollector()`, the trailing array parameter type, and whether `asFixedArity()`/`asCollector(...)` is needed.
9. **When fixing**, choose explicit conversion in one place: change the call site to the right type, build an `asType` adapter with a clear contract, or perform separate data conversion (such as string parsing). Do not overuse `Object` to mask every mismatch.

### Common error table

| Symptom | Typical cause | How to fix |
| --- | --- | --- |
| `invokeExact` with `3` instead of `3L` | Call site is `int` while handle takes `long` | Use `3L` or cast `(long) 3`, or deliberately use `invoke` |
| `invokeExact` in a statement, handle returns `int` | Call-site return type `void` differs from `int` | Use `int x = (int) h.invokeExact(...)` or choose `invoke` to discard the result |
| `invoke` receives `long` while target takes `int` | Primitive narrowing is forbidden | Check value range and cast deliberately before the call |
| `invoke` needs `short` return from an `int` target | Return narrowing is forbidden | Receive `int` then convert the value in a controlled way, or use an explicit casting API |
| `invoke` receives `Object` holding `String` while target takes primitive `int` | Runtime unboxing fails | Parse `String` to `Integer`/`int` first, or fix data/contract |
| `invoke` receives `Object null` for a primitive | Unboxing null | Validate input and handle null explicitly |
| `invoke` on a virtual handle with a receiver of the wrong class | Receiver cast fails | Obtain the right instance, check `handle.type().parameterType(0)` |
| Calling `invokeWithArguments` expecting the same behavior as `invokeExact` | `Object` list/variable arity differs from exact descriptor | Choose the API and conversion strategy per contract |
| `findVirtual`/`findStatic` throws `IllegalAccessException` | Lookup lacks access | Check class/method access, package/module, lookup privileges |
| Expecting `asType` to automatically parse strings | Adapter has no string-to-number conversion | Perform parsing or a separate filter |

### Observing types at runtime

The following snippet assumes an existing `MethodHandle handle` variable and an argument `value`; this is **not a standalone program**:

~~~java
MethodType type = handle.type();
System.out.println("target=" + type);
System.out.println("parameterCount=" + type.parameterCount());
System.out.println("returnType=" + type.returnType().getTypeName());
System.out.println("varargs=" + handle.isVarargsCollector());
System.out.println("argumentRuntime=" +
    (value == null ? "null" : value.getClass().getName()));
~~~

The `argumentRuntime` line only helps explain cast/unboxing errors at runtime. It **does not replace** checking the static type of expressions at the call site; the same runtime `Object` can be passed via an expression of type `Object` or `Integer` and lead to different descriptors.

## 11. Self-check exercises

**Question 1.** A handle has type `(long)long`. Will `(long) h.invoke(5)` run? What about `(long) h.invokeExact(5)`?

**Answer:** `invoke` can widen the argument `int → long`. `invokeExact` will not run because the call-site parameter type `int` does not match `long`. Write `5L` for exact.

**Question 2.** A handle has type `(int)int`. Will `long result = (long) h.invoke(7)` run? What about `long result = (long) h.invokeExact(7)`?

**Answer:** `invoke` can widen the return `int → long`. `invokeExact` throws `WrongMethodTypeException` because the return type does not match even though the argument does.

**Question 3.** Handle `(int)int` receives `Object x = Integer.valueOf(7)`; can calling `(int) h.invoke(x)` succeed? What if `x = "7"`?

**Answer:** With `Integer`, the `Object` is unboxed to `int` and can run; with `String`, the adapter is valid at the static `Object` level, but runtime unboxing fails with `ClassCastException`. The API does not parse `"7"`.

**Question 4.** Why can an `(Object,Object)Object` adapter created from a `(long,long)long` handle still throw an exception when called with `invokeExact`?

**Answer:** The descriptor of `invokeExact` matches the adapter, but **the conversions inside the adapter** still depend on the `Object` values. An `Object` of the wrong type throws `ClassCastException`; `null` when it must be unboxed to `long` throws `NullPointerException`.

**Question 5.** An original handle `(String)void` is called with `Object result = h.invoke("hello")`; what is `result`?

**Answer:** `null`; `asType` has a rule to produce `null` when converting a `void` return to a reference. The target still executes.

**Question 6.** Why can `Object receiver = "hello"` be used with `substring.invoke(receiver,1)`, while `substring.invokeExact(receiver,1)` does not match?

**Answer:** A virtual handle has a `String` receiver parameter. With `invoke`, a runtime cast `Object → String` is possible. `invokeExact` requires the receiver argument to have static type `String` and a matching return descriptor; the `Object` variable does not match.

**Question 7.** Can `asType` change primitive `long` to `int` to satisfy a caller? When is `explicitCastArguments` needed?

**Answer:** Primitive narrowing is not allowed under `asType`. If the problem truly allows narrowing and accepts the risk of data loss, you can consider `explicitCastArguments` with an explicit type contract, or cast deliberately before calling.

**Question 8.** Does `MethodHandle.type()` change when you call `h.asType(newType)`?

**Answer:** No. `asType` returns a new adapted handle, while the original `h` remains unchanged. When `newType` equals the old type itself, the API returns the original handle.

## 12. Official references

- Java SE 17 — `java.lang.invoke.MethodHandle` (sections *Method handle compilation*, *Method handle invocation*, `invoke`, `invokeExact`, `asType`, `invokeWithArguments`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html
- Java SE 17 — `java.lang.invoke.MethodType` and `MethodHandle.type()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html
- Java SE 17 — `java.lang.invoke.MethodHandles` (`lookup`, `findStatic`, `findVirtual`, and `explicitCastArguments`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html
- Java SE 17 — `WrongMethodTypeException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html
- Java Language Specification 17 — *Method Invocation Conversion*, `5.3`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.3

**Key takeaway:** `invokeExact` requires the descriptor at the call site to match `MethodHandle.type()`, **including the return type**. `invoke` allows a different descriptor if the handle's type can be converted via `asType`: primitive widening, boxing, unboxing, reference cast, and the appropriate `void` rules. When a conversion cannot be formed, `WrongMethodTypeException` occurs; when a conversion is valid but the runtime value has the wrong type or is `null` and cannot be unboxed, `ClassCastException` or `NullPointerException` may occur.