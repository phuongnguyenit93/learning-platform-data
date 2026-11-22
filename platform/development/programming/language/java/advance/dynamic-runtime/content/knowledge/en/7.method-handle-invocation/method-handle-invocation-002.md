# 7.2 `invokeExact`: exact matching of both argument types and result type

`java.lang.invoke.MethodHandle` is a typed reference to a callable operation at runtime. When using `invokeExact(...)`, the JVM requires the **type of the entire call site** to **match exactly** with the handle's `MethodType`: **the number of parameters, the type of each parameter in exact order, and the return type**. Runtime value types that appear compatible, or automatic boxing/widening that Java could perform in a normal method call, are not sufficient to satisfy this requirement.

For example: a handle with `type() == (int,int)int` can only be called via `invokeExact` with exactly two arguments of static type `int` and a call site expecting an **`int` result**. If the call site expects `long`, `Object`, or `void`, the JVM throws `WrongMethodTypeException`, even though the two input numbers are still `int`.

This lesson focuses on the **exact matching at the call site** mechanism and how to write correct Java 17+ code, helping you handle errors without accidentally losing the type checking of `invokeExact`.

After studying, you can:

- Read `handle.type()` and fully explain the `(parameterTypes)returnType` form.
- Understand how the compiler infers **parameter types from argument expressions** and **the result type from a direct cast or statement context**.
- Identify mismatches in arguments, reference subtypes, primitives/wrappers, receivers, and return types.
- Distinguish `invokeExact`, `invoke`, and the `asType` adapter; choose the appropriate fix.
- Write code that calls static/virtual method handles, `void`-returning handles, helpers with concrete signatures, and diagnose `WrongMethodTypeException`.
- Run, observe, and explain two Java 17+ examples with deterministic stdout.

## 1. `MethodType` includes the result

Each `MethodHandle` has an immutable `java.lang.invoke.MethodType`, read via `type()`. Conceptually:

```text
              [input parameters]     [result type]
(int, int)int         int,int   ->       int
(String)String        String    ->       String
(String)void          String    ->       void
(String,int)String    String,int->       String
```

`MethodType` describes **the type of the handle itself**, not the type of a specific instance passed at runtime. It holds a `Class<?>` for each parameter and return, and can distinguish `int.class` from `Integer.class`, `String.class` from `CharSequence.class`, and `void.class` from `Void.class`.

Example declaring a method and looking up a handle:

```java
static int add(int a, int b) {
    return a + b;
}

MethodHandle h = MethodHandles.lookup().findStatic(
        Example.class, "add",
        MethodType.methodType(int.class, int.class, int.class));
```

These two snippets are **illustrative code** placed inside class `Example` and require importing `java.lang.invoke.*` or the corresponding classes, plus handling lookup exceptions. The `methodType` method takes the **return type first**, followed by the parameter types. `h.type().toString()` has the form:

```text
(int,int)int
```

The three `int`s in `methodType(int.class, int.class, int.class)` are respectively **return**, **first argument**, **second argument**. Do not mistake the first position for the first parameter.

An exact call:

```java
int value = (int) h.invokeExact(2, 3);
```

The compiler generates a call site with descriptor `(int,int)int`; the returned result is `5`. The `(int)` cast right before the **`h.invokeExact(...)` expression** does not merely change the expression's type in source: it helps the compiler place the **expected result type** into the call-site descriptor.

## 2. Checking happens at the call site, no automatic type adaptation

`invokeExact` is a **signature-polymorphic method**. In the call's bytecode, the compiler writes a descriptor based on the **static types** of the arguments and the result type from the calling context. The JVM compares that descriptor with `h.type()`. Both sides must be strictly equal; there is no automatic boxing, unboxing, widening, or downcasting during exact invocation.

```text
Java source:
    int result = (int) h.invokeExact(2, 3);
                         |
                         v
Compiler writes call-site descriptor: (int,int)int
                         |
                         v
Runtime reads handle.type():          (int,int)int
                         |
             equality? yes ------+------> invoke target
                         |
             equality? no --------------> WrongMethodTypeException
```

Even though Java normally allows passing an `int` to a method expecting `long`, that rule is **method invocation conversion for normal method calls**; it does not replace the type equality condition of `invokeExact`.

This table assumes `h.type()` is `(int,int)int`:

| Code at the call site | Relevant descriptor | Outcome |
| --- | --- | --- |
| `int x = (int) h.invokeExact(2, 3);` | `(int,int)int` | **Valid**, `x = 5` |
| `long x = (long) h.invokeExact(2, 3);` | `(int,int)long` | **Wrong** return type |
| `int x = (int) h.invokeExact(2L, 3);` | `(long,int)int` | **Wrong** first argument type |
| `Object x = (Object) h.invokeExact(2, 3);` | `(int,int)Object` | **Wrong** return type |
| `h.invokeExact(2, 3);` as a statement | `(int,int)void` | **Wrong** because the handle returns `int` |
| `long x = (int) h.invokeExact(2, 3);` | `(int,int)int` | **Valid**: Java widens the result after the call |
| `Object x = (int) h.invokeExact(2, 3);` | `(int,int)int` | **Valid**: Java boxes after the call |
| `int x = (int) h.invokeExact((int) 2L, 3);` | `(int,int)int` | **Valid**: argument cast before the call |

The "wrong" rows in the table are **runtime mismatches** and throw `java.lang.invoke.WrongMethodTypeException`; they usually **compile** because `invokeExact` is signature polymorphic. Unlike normal Java method calls, the compiler does not use the target signature to automatically convert each argument.

### 2.1. Why must the result type also be exact?

This is the easiest point to overlook. Many people check `h.type().parameterArray()` or count arguments, see that they match, and still get `WrongMethodTypeException`. The reason is that the JVM descriptor includes the **return type**, and `invokeExact` requires the return type to match as well.

Example:

```java
// h.type() == (int,int)int
long wrong = (long) h.invokeExact(2, 3);   // WrongMethodTypeException
long right = (int) h.invokeExact(2, 3);    // Succeeds: int is widened after the call
```

The second line does not force the handle to return `long`; it asks the handle to return **`int`**, and then Java assigns the `int` result to the `long` variable using normal conversion **outside** the call site.

Similarly:

```java
// h.type() == (int,int)int
Object wrong = (Object) h.invokeExact(2, 3); // WrongMethodTypeException
Object right = (int) h.invokeExact(2, 3);    // Integer boxing after invokeExact
```

Wanting to hold the result in an `Object` variable does **not** turn the handle's return type into `Object`. Converting the result after an exact call is a different matter from asking `invokeExact` itself to return `Object`.

### 2.2. Without a direct cast, what does the compiler do?

Rules in Java source:

- If the `invokeExact(...)` call is the **direct operand of a cast**, the target type of the cast determines the return type at the call site (after erasure when needed).
- If the call is used as a standalone **expression statement**, the return type at the call site is **`void`**.
- If the call is used as an expression **without a direct cast**, the return type is inferred as **`Object`** according to the signature-polymorphic rules of this API.

Therefore, do not just look at the variable type on the left of `=` and hope the compiler picks that return type automatically. The clearest, easiest-to-verify, and least error-prone way with `invokeExact` is to place the return type cast **directly on the call**, for example `(int) h.invokeExact(...)` or `(String) h.invokeExact(...)`.

## 3. Complete Java 17+ program: matching types and four mismatch forms

Create file **`InvokeExactDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class InvokeExactDemo {
    private static int add(int left, int right) {
        return left + right;
    }

    private static String wrap(String value) {
        return "[" + value + "]";
    }

    private static void announce(String message) {
        System.out.println("announce: " + message);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle add = lookup.findStatic(
                InvokeExactDemo.class, "add",
                MethodType.methodType(int.class, int.class, int.class));
        System.out.println("add.type: " + add.type());
        int sum = (int) add.invokeExact(10, 20);
        System.out.println("sum: " + sum);

        try {
            long wrongReturn = (long) add.invokeExact(10, 20);
            System.out.println(wrongReturn);
        } catch (WrongMethodTypeException e) {
            System.out.println("wrong return: " + e.getClass().getSimpleName());
        }

        try {
            int wrongArgument = (int) add.invokeExact(10L, 20);
            System.out.println(wrongArgument);
        } catch (WrongMethodTypeException e) {
            System.out.println("wrong argument: " + e.getClass().getSimpleName());
        }

        try {
            add.invokeExact(10, 20);
        } catch (WrongMethodTypeException e) {
            System.out.println("discarded result: " + e.getClass().getSimpleName());
        }

        MethodHandle wrap = lookup.findStatic(
                InvokeExactDemo.class, "wrap",
                MethodType.methodType(String.class, String.class));
        String input = "Ada";
        String wrapped = (String) wrap.invokeExact(input);
        System.out.println("wrap.type: " + wrap.type());
        System.out.println("wrapped: " + wrapped);

        CharSequence broader = "Bea";
        try {
            String wrongReference = (String) wrap.invokeExact(broader);
            System.out.println(wrongReference);
        } catch (WrongMethodTypeException e) {
            System.out.println("wrong reference: " + e.getClass().getSimpleName());
        }

        MethodHandle adapted = add.asType(
                MethodType.methodType(long.class, int.class, int.class));
        System.out.println("adapted.type: " + adapted.type());
        long widened = (long) adapted.invokeExact(10, 20);
        System.out.println("adapted result: " + widened);

        long flexible = (long) add.invoke(10, 20);
        System.out.println("invoke result: " + flexible);

        MethodHandle announce = lookup.findStatic(
                InvokeExactDemo.class, "announce",
                MethodType.methodType(void.class, String.class));
        announce.invokeExact("done");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 InvokeExactDemo.java
java InvokeExactDemo
```

**Stdout verified by actual Java compilation/execution:**

```text
add.type: (int,int)int
sum: 30
wrong return: WrongMethodTypeException
wrong argument: WrongMethodTypeException
discarded result: WrongMethodTypeException
wrap.type: (String)String
wrapped: [Ada]
wrong reference: WrongMethodTypeException
adapted.type: (int,int)long
adapted result: 30
invoke result: 30
announce: done
```

### Step-by-step analysis

1. `lookup.findStatic(...)` obtains a handle for `private static int add(int,int)`. `lookup` is inside `InvokeExactDemo` itself, so it has access to its own class's private methods.
2. `(int) add.invokeExact(10, 20)` creates call-site `(int,int)int`, matching `add.type()`, returning `30`.
3. `(long) add.invokeExact(10, 20)` has return `long`, mismatching the handle's `int` return: `WrongMethodTypeException`.
4. `(int) add.invokeExact(10L, 20)` has first argument `long`, mismatching `int`: `WrongMethodTypeException`.
5. `add.invokeExact(10, 20);` stands alone as a statement so the caller expects return `void`, which also mismatches `int`.
6. `wrap` takes exact `String`, returns exact `String`; the call with variable `String input` succeeds.
7. `CharSequence broader` points to an object that is a `String`, but the **static** type of the argument expression is `CharSequence`. Descriptor `(CharSequence)String` does not match `(String)String`; the actual runtime object does not make `invokeExact` cast automatically.
8. `add.asType((int,int)long)` creates a **new handle** that can widen the target's `int` result to `long`. The caller now expects `long`, and it matches `adapted.type()`.
9. `add.invoke(10,20)` has a flexible conversion mechanism equivalent to using `asType` when needed, so `(int,int)long` can work with target `(int,int)int`.
10. `announce` has type `(String)void`; when calling `announce.invokeExact("done");` as a statement, the caller also has return `void`. This is the right way to call a `void`-returning method.

The `try/catch` blocks in the example only demonstrate **intentional mismatches**. In real code, do not intentionally make wrong calls and catch `WrongMethodTypeException` to figure out the right call. Inspect `handle.type()` and fix the signature at the point where the call is designed.

## 4. Arguments use static types, not the runtime object's type

For a `(String)String` handle:

```java
String exact = "hello";
CharSequence broad = "hello";
Object generic = "hello";
```

All three variables can refer to a `String` object, yet for `invokeExact` they are not equivalent:

```java
// h.type() == (String)String
String a = (String) h.invokeExact(exact);          // valid
String b = (String) h.invokeExact(broad);          // WrongMethodTypeException
String c = (String) h.invokeExact(generic);        // WrongMethodTypeException
String d = (String) h.invokeExact((String) broad); // valid if value is actually String
```

This is an **illustrative snippet**, assuming `h` has been initialized with the corresponding `MethodType`. The `(String) broad` cast occurs **before invocation**, changing the static argument type to `String`. If the object is not a `String`, Java may throw `ClassCastException` at that cast, before the handle is called; not `WrongMethodTypeException`.

### 4.1. Primitive vs wrapper and widening

Assume `h.type() == (int,int)int`:

```java
int a = 1;
Integer boxed = 1;
short small = 2;

int ok = (int) h.invokeExact(a, 2);                  // valid
int noBox = (int) h.invokeExact(boxed, 2);           // wrong: (Integer,int)int
int noWiden = (int) h.invokeExact(small, 2);         // wrong: (short,int)int
int fixedBox = (int) h.invokeExact(boxed.intValue(), 2); // valid
int fixedShort = (int) h.invokeExact((int) small, 2);    // valid
```

Key point: `Integer` is not automatically unboxed to `int` **inside** `invokeExact`; `short` is not automatically widened to `int`. If conversion is required, do it **explicitly before the call** or create an adapter with the desired type.

An integer literal like `2` defaults to type `int`; `2L` has type `long`. They produce different call-site descriptors even though both represent the number two.

### 4.2. `null` and reference types

A bare `null` literal in a signature-polymorphic call has special typing rules and cannot be assumed to mean `String`. When a handle expects `String`, pass `(String) null` if `null` is a valid value for the target:

```java
// h.type() == (String)String
String value = (String) h.invokeExact((String) null);
```

The call above **passes the exact type check**, because the parameter type is represented as `String`. However, the target method may throw `NullPointerException` when processing a null value. **A matching `MethodType` does not guarantee valid business data**.

### 4.3. Arrays and generic erasure

If a handle takes `String[]`, the call site must use an expression with static type `String[]`; an `Object[]` variable that happens to point to a `String[]` still causes the call-site descriptor to mismatch. For a method taking `java.util.List<String>`, `MethodType` uses `List.class` because of erasure; there is no `List<String>.class`.

Similarly, a handle taking `Object` will **not** automatically accept a variable of static type `String` via `invokeExact`:

```java
// h.type() == (Object)Object
Object response = (Object) h.invokeExact((Object) "hello"); // valid signature-wise
```

Casting the argument to `Object` produces a matching descriptor. Just because Java allows assigning a `String` to `Object` does not mean `invokeExact` will automatically convert it to `Object`.

## 5. A virtual method's receiver is also an argument that must match

With `MethodHandles.Lookup.findVirtual`, the `MethodType` passed during **lookup** lists the declared parameters of the instance method, **excluding the receiver**. However, the resulting handle has the **receiver as its first parameter**:

```java
MethodHandle substring = MethodHandles.publicLookup().findVirtual(
        String.class, "substring",
        MethodType.methodType(String.class, int.class));
System.out.println(substring.type()); // (String,int)String
```

Even though `String.substring(int)` in Java source appears to have only one `int` parameter, calling the handle with `invokeExact` requires **two arguments**: the `String` receiver, then the `int` index. Both the receiver type and the return type must match.

### 5.1. Complete Java 17+ program: receiver, `bindTo`, static type errors

Create **`ReceiverExactDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class ReceiverExactDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle substring = MethodHandles.publicLookup().findVirtual(
                String.class, "substring",
                MethodType.methodType(String.class, int.class));
        System.out.println("virtual.type: " + substring.type());

        String text = "method";
        String tail = (String) substring.invokeExact(text, 2);
        System.out.println("tail: " + tail);

        Object objectReceiver = text;
        try {
            String wrong = (String) substring.invokeExact(objectReceiver, 2);
            System.out.println(wrong);
        } catch (WrongMethodTypeException e) {
            System.out.println("receiver mismatch: " + e.getClass().getSimpleName());
        }

        MethodHandle bound = substring.bindTo(text);
        System.out.println("bound.type: " + bound.type());
        String result = (String) bound.invokeExact(2);
        System.out.println("bound result: " + result);
    }
}
```

Run:

```bash
javac --release 17 ReceiverExactDemo.java
java ReceiverExactDemo
```

Verified stdout:

```text
virtual.type: (String,int)String
tail: thod
receiver mismatch: WrongMethodTypeException
bound.type: (int)String
bound result: thod
```

Explanation:

- `substring.type()` is `(String,int)String`: `String` receiver plus `int` index, returning `String`.
- `String tail = (String) substring.invokeExact(text,2)` uses a receiver with static type `String`; succeeds.
- `Object objectReceiver` actually holds a `String`, but the call site requires `(Object,int)String`; it does not match and throws `WrongMethodTypeException`.
- `bindTo(text)` pre-binds the receiver and **removes the first parameter** from the new handle's type. `bound.type()` becomes `(int)String`, so `bound.invokeExact(2)` is valid. `bindTo` is used for a compatible leading reference parameter, not as a means for arbitrary automatic insertion/casting.

**Checking tip:** When seeing `WrongMethodTypeException` on a virtual handle, look at `handle.type()` **after creating the handle and after any adapter/binding steps**, not just at the original Java method signature.

## 6. `void` results and statement-style calls

At the call site, the statement:

```java
handle.invokeExact(arg);
```

does not use the return value; the compiler chooses **return type `void`** for the call's descriptor. That is only valid for a handle whose return type is `void`. If the handle returns `int`, the call above is mistyped; the JVM does not silently discard the result when using `invokeExact`.

Example from the first program:

```java
// add.type() == (int,int)int
add.invokeExact(10, 20); // WrongMethodTypeException: call site wants void

// announce.type() == (String)void
announce.invokeExact("done"); // valid: both statement and handle return void
```

If you want to **intentionally discard the result**, you can still make an exact call with the original return type and not use the variable's value in subsequent statements; or create an `asType` adapter with return type `void` to discard the result per the adapter contract. Do not fix it with a `(void)` cast: Java does not allow casting an expression to `void`.

### 6.1. `void.class` differs from `Void.class`

`MethodType.methodType(void.class, String.class)` describes a method that **returns no value**. `MethodType.methodType(Void.class, String.class)` describes a method returning **a `java.lang.Void` reference type**. The two types are different; `invokeExact` does not automatically convert `void` to `Void` or vice versa.

For a `void`-returning handle, use a statement call if you want strict exact invocation; do not assume `Object result = (Object) handle.invokeExact(...)` will automatically receive `null`.

## 7. `invoke`, `invokeExact`, and `asType`: three different mechanisms

`invokeExact` performs no conversions. However, Java provides other APIs when a program genuinely needs type adaptation.

| API | Type rule | When appropriate |
| --- | --- | --- |
| `handle.invokeExact(...)` | Call-site `MethodType` must equal `handle.type()` exactly | Concrete signature known, strict type checking needed and calling logic is stable |
| `handle.invoke(...)` | Can perform conversions like `handle.asType(callSiteType)` when the two types are compatible | Call site uses different types but conversion is permitted |
| `handle.asType(newType)` | Returns a **new handle** with `type() == newType`, performing supported conversions when calling the target | Want to normalize/convert explicitly once and then call the adapted handle |
| `handle.invokeWithArguments(...)` | Accepts arguments as `Object...` or a list, using generic invocation/conversion | Many types are only known dynamically and the API must work with object lists |

Example:

```java
// add.type() == (int,int)int
long viaInvoke = (long) add.invoke(10, 20); // valid, adapts return int -> long

MethodHandle adapted = add.asType(
        MethodType.methodType(long.class, int.class, int.class));
long viaExact = (long) adapted.invokeExact(10, 20); // exact with the NEW handle
```

Both cases can produce the value `30`. With `invoke`, the adaptation mechanism is specified **as if** using `asType`, rather than the API guaranteeing that an intermediate handle object is created on every call.

### 7.1. `asType` does not mutate the original `handle`

`MethodHandle` has an immutable `MethodType`. `asType` creates or returns a handle with the desired type; the original handle keeps its old type:

```java
// add.type() == (int,int)int
MethodHandle adapted = add.asType(
        MethodType.methodType(long.class, int.class, int.class));

System.out.println(add.type());     // (int,int)int
System.out.println(adapted.type()); // (int,int)long
```

The conversion in the example is **widening from an `int` result to `long`**. Do not confuse this example with `invokeExact` converting automatically: the caller matches `(int,int)long` of the **adapted handle**, no longer calling exact directly on `add`.

If a conversion cannot be performed under `asType` rules, the API may throw `WrongMethodTypeException` right when creating the adapter. For adapters using reference casts, the subsequent target invocation may throw `ClassCastException` if the runtime object does not have a compatible type. Thus, an adapter is not a way to unconditionally accept any argument.

### 7.2. When to use `invoke` instead of `invokeExact`?

If the caller genuinely wants `long` while the target returns `int`, there are two transparent options:

- Keep a strict exact call with `(int) handle.invokeExact(...)`, then let Java widen the result after the call.
- If the API goal requires a handle returning `long`, use `asType` to create a new `(int,int)long` handle, then `(long) adapted.invokeExact(...)`; or use `(long) handle.invoke(...)` for call-site adaptation.

`invoke` is appropriate when rule-based conversion is needed. `invokeExact` is appropriate when **both caller and handle agree on one specific signature**. Do not switch every failing `invokeExact` to `invoke` as a way to silently ignore mismatches; sometimes a mismatch indicates a data-type bug.

## 8. `WrongMethodTypeException`: identifying the exact cause

`java.lang.invoke.WrongMethodTypeException` is a `RuntimeException`. It can appear when `invokeExact` sees a call-site descriptor that differs from the handle type; it can also appear from `invoke`/`asType` when an unsupported conversion is required.

An effective debugging technique is to line up **expected and actual**:

```text
Handle type:       (int,int)int
Caller descriptor: (int,int)long
Mismatch:                    ^^^^ return type

Handle type:       (String)String
Caller descriptor: (CharSequence)String
Mismatch:           ^^^^^^^^^^^^ argument type

Handle type:       (String,int)String
Caller descriptor: (Object,int)String
Mismatch:           ^^^^^^ receiver type
```

The `WrongMethodTypeException` message usually gives a form like `expected ... but found ...` but **do not depend on the exact message string**: the detailed wording may differ across JDKs/implementations. The reliable approach is to inspect `handle.type()` and examine the Java expressions on the calling line.

### 8.1. Technical checklist when receiving a stack trace

1. Write down `handle.type()`, e.g. `(int,int)int`. How many parameters are there? Is there an implicit receiver that became the first parameter? What is the return type?
2. Check the static type of **each** argument expression. For example `2` is `int`, `2L` is `long`, `Integer` differs from `int`, `Object` differs from `String`.
3. Check whether the `invokeExact(...)` expression is **directly inside a cast** or stands as a statement. Without a direct cast it usually has return `Object`; as a statement it has return `void`.
4. Verify the actual handle at **the time of the call**, after `bindTo`, `asType`, `insertArguments`, `dropArguments`, combinators, or variable reassignments.
5. If using a virtual handle, determine the exact receiver type; if already bound with `bindTo`, do not pass the receiver again.
6. Choose to fix via conversion **before/after** the call, or create a clearly documented adapter; do not hide the error with `catch (WrongMethodTypeException ignored)`.

`handle.type()` is **runtime information about the handle**. It does not itself reveal the descriptor the compiler wrote for the call site. To determine the caller side, you must read the source along with the static types of the expressions, or inspect bytecode if needed.

### 8.2. Handle lookup errors differ from invokeExact errors

In programs that create handles via `lookup.findStatic` or `findVirtual`:

- `NoSuchMethodException`: the method name, kind, or `MethodType` used for lookup does not match the method to be retrieved.
- `IllegalAccessException`: `Lookup` does not have access to the target method/class in the lookup context.
- `WrongMethodTypeException`: after already having a handle, the `invokeExact` call site does not match `handle.type()` or the requested adaptation cannot be created.
- Exceptions thrown by the **target** itself: `invokeExact` lets a `Throwable` from the target propagate directly; it does not wrap it in `InvocationTargetException` by default like `Method.invoke`.

Do not use `setAccessible(true)` to cure a `WrongMethodTypeException`. Access rights and equality between two `MethodType`s are **two independent issues**.

## 9. Signature polymorphism and the role of the Java compiler

In source, `MethodHandle.invokeExact` looks much like a method taking `Object...` and returning `Object`, but the JVM handles calls to it specially. This is **signature polymorphism** according to the Java Language Specification and Java Virtual Machine Specification.

The `invokevirtual` instruction in bytecode is paired with a descriptor built specifically for **that particular call site**; the Java compiler does not default to turning arguments into `Object` and packing them into `Object[]` as with ordinary varargs APIs. At the same time, the compiler must record the call site's return type:

- `(int) h.invokeExact(1, 2)` represents return `int`.
- `(String) h.invokeExact("x")` represents return `String`.
- `h.invokeExact("x");` as a statement represents return `void`.
- `Object v = h.invokeExact("x");` usually represents return `Object`; the type of the variable on the left does **not** make the call site automatically change to the target's return type.

When the JVM links/executes `invokeExact`, it compares the call-site descriptor with the receiver handle's `MethodType`. If they are not equal, it throws `WrongMethodTypeException`. This is a runtime type-check mechanism, not overload resolution based on the argument object's class.

### 9.1. Why not call `invokeExact` via Core Reflection?

Do not try:

```java
Method m = MethodHandle.class.getMethod("invokeExact", Object[].class);
m.invoke(handle, (Object) arguments);
```

This is an **illustrative snippet of an invalid approach** (assuming `handle`, `arguments` variables and corresponding imports exist). Core Reflection sees the formal declaration of the signature-polymorphic method, but the `MethodHandle.invokeExact` API is not designed to be executed via that `Method.invoke` path: a direct call through Core Reflection can throw `UnsupportedOperationException`.

When you need a completely dynamic API taking a list of `Object`s, look at `invokeWithArguments` or design an adapter/invoker with an explicit `MethodType`; when you know the exact compile-time signature, call `invokeExact` directly.

## 10. Pitfalls in generic helpers and `Object` types

A helper written like this looks flexible but is **unsuitable for primitive-return exact handles**:

```java
// Non-standalone illustrative snippet:
static <T> T unsafe(MethodHandle h, int a, int b) throws Throwable {
    return (T) h.invokeExact(a, b);
}
```

After **type erasure**, `T` does not provide a concrete `int` return type for this call site; it usually represents return `Object`. If you pass an `(int,int)int` handle, you can hit `WrongMethodTypeException`, even if the outer caller wants `Integer` or `int`. Casting at **another call layer** cannot fix the descriptor generated by the compiler **inside the helper**.

A concrete helper with a clear contract:

```java
static int callIntBinary(MethodHandle h, int a, int b) throws Throwable {
    return (int) h.invokeExact(a, b);
}
```

This helper requires an exact `(int,int)int` handle; it works well when the program controls the handles and shares a common signature. Do not confuse the helper's `int` return type with the return type the compiler infers for `invokeExact`: the `(int)` on the **specific call** guarantees the desired descriptor.

If you need to accept genuinely different signatures, express the contract using `MethodType`, select/normalize an appropriate handle, or use a dynamic invocation API. Do not create a generic wrapper and assume `invokeExact` will use `T` at runtime to convert types.

## 11. Pre-checking `MethodType` for fixed call sites

When code has a consistent expected type, you can validate the handle right at configuration time:

```java
static int addExact(MethodHandle handle, int a, int b)
        throws Throwable {
    MethodType expected =
            MethodType.methodType(int.class, int.class, int.class);
    if (!handle.type().equals(expected)) {
        throw new IllegalArgumentException(
                "Expected " + expected + " but handle is "
                        + handle.type());
    }
    return (int) handle.invokeExact(a, b);
}
```

This snippet is an **illustrative method** inside a class that imports `MethodHandle` and `MethodType`. Comparing with `MethodType.equals` requires both parameter and return types to match, and the expression `(int) handle.invokeExact(a,b)` has the corresponding `(int,int)int` call site.

Advantage: configuration errors are caught early, with clear expected/actual information, instead of letting a `WrongMethodTypeException` surface far from where the handle was registered.

Limitation: pre-checking only proves the handle has the right `MethodType`; it does **not** guarantee the target method will succeed with specific data. Division may divide by zero, a receiver may be `null`, or the target may throw a business or I/O exception.

### 11.1. Do not check types loosely and then call exact

It is not enough to only check `parameterCount() == 2`, or `Number.class.isAssignableFrom(...)`, or only check the return type. For instance, `(Integer,Integer)Integer` and `(int,int)int` both have two parameters but are two different signatures.

`MethodType.equals` guarantees exact equality with the expected type. If valid conversions should be supported, make that an explicit policy with `asType` and handle the case where adaptation fails.

## 12. Converting at the boundary to keep exact invocation in the core

A common architecture is to **normalize data outside the core**, create a typed method handle once, and use `invokeExact` consistently in the hot call path.

For example, a source receives `Integer` while the target handle takes primitive `int`:

```java
Integer first = 10;
Integer second = 20;

// Assume handle.type() == (int,int)int
int result = (int) handle.invokeExact(
        first.intValue(), second.intValue());
```

Here unboxing happens **before** the call site. If `first` or `second` is `null`, `intValue()` throws `NullPointerException` at the conversion layer; validate inputs and report clear errors when needed.

If the handle returns `int` but an external API needs `long`:

```java
long answer = (int) handle.invokeExact(10, 20);
```

Exact invocation preserves the `int` return; Java widens to `long` **after** receiving the result. This is usually the simplest approach when conversion only serves result assignment.

If many callers genuinely need a `long` result from the same target, you can create and cache an adapter:

```java
MethodHandle toLong = handle.asType(
        MethodType.methodType(long.class, int.class, int.class));
long answer = (long) toLong.invokeExact(10, 20);
```

These snippets are **illustrative code** given a properly typed `handle` and `java.lang.invoke.*` imports. There is no need to call `asType` on every request if the target signature does not change; it can be normalized once at initialization.

### 12.1. When conversion fails

Distinguish three kinds of errors:

- **`WrongMethodTypeException`:** the call-site type or adaptation is incompatible with the handle under Method Handles rules.
- **`ClassCastException`:** a reference cast is notationally permitted, but the actual object does not have the target type.
- **Target exceptions:** the target is invoked and throws an error. `invokeExact` does not wrap every error in `InvocationTargetException`.

Only catch `WrongMethodTypeException` at configuration/diagnostics boundaries if you want to add expected/actual context and preserve the cause. In steady-state code, a mismatch is usually a **bug in the type contract**, not a normal business case.

## 13. Common mistakes and direct fixes

| Mistake | Cause | Fix |
| --- | --- | --- |
| `long x = (long) handle.invokeExact(1,2)` on an `int`-returning handle | Casting to `long` creates return type `long` at the call site | `long x = (int) handle.invokeExact(1,2)`, or create an `(int,int)long` handle via `asType` |
| `Object x = (Object) handle.invokeExact(1,2)` on an `int`-returning handle | Return `Object` differs from `int` | `Object x = (int) handle.invokeExact(1,2)` to box **after** the exact call |
| `handle.invokeExact(1,2);` on an `int`-returning handle | Expression statement expects `void` | Use the `int` return properly or an appropriate return-dropping adapter |
| Passing `Integer` to a handle taking `int` | Static argument type is `Integer` | Call `.intValue()` before the exact call, or use an adapter with unboxing rules |
| Passing a `CharSequence` variable actually holding a `String` | Descriptor receives `CharSequence`, not `String` | Cast/validate to `String` beforehand, or use `invoke`/adapter if design allows |
| Using `Object` as receiver for virtual handle `(String,int)String` | The handle's receiver must be `String` at the call site | Use a `String` variable or a checked receiver cast |
| Forgetting the receiver of `findVirtual` | The returned handle has the receiver as its first parameter | Check `handle.type()`, pass the receiver of the right type |
| Passing the receiver again after `bindTo` | `bindTo` already removed the first parameter from the new handle | Use `bound.type()` to determine the remaining arguments |
| Checking only arguments, ignoring return | `MethodType` includes the result | Compare the entire signature; check the direct cast |
| Generic helper `(T) h.invokeExact(...)` | `T` undergoes erasure; call-site return does not become a concrete type | Use a helper with a concrete return type/cast, or appropriate `invoke`/adapter |
| Switching all `invokeExact` to `invoke` | Can hide mismatch bugs and change conversions | Define a conversion policy and normalize at the boundary |
| Catching `InvocationTargetException` like `Method.invoke` | MethodHandle target exceptions propagate directly | Handle the target's `Throwable` properly per the API contract |

## 14. Self-check exercises

**Question 1.** A handle has `type() == (int,int)int`. Which lines are valid?

```java
int a = (int) h.invokeExact(1, 2);
long b = (long) h.invokeExact(1, 2);
long c = (int) h.invokeExact(1, 2);
Object d = (int) h.invokeExact(1, 2);
```

**Answer:** `a`, `c`, `d` are valid; `b` is wrong because the caller has return `long` while the handle returns `int`. For `c`, widening occurs after the exact call; for `d`, boxing occurs after the exact call.

**Question 2.** `String s = (String) h.invokeExact(value)` with `h.type() == (String)String`, where `CharSequence value = "ok";`. Why is this wrong even though the actual object is a `String`?

**Answer:** the call-site parameter type is `CharSequence`, which does not match `String`; `invokeExact` checks the static signature. You can use `(String) value` as the argument if the cast is valid.

**Question 3.** `h.type() == (int)void`; if you want to call it from Java source, how must the result be handled?

**Answer:** call `h.invokeExact(5);` as an expression statement, so the return descriptor is `void`. Do not use a `(Void)` or `(Object)` cast if the handle returns `void`.

**Question 4.** What handle type does `findVirtual(String.class,"substring",MethodType.methodType(String.class,int.class))` produce?

**Answer:** `(String,int)String` because the `String` receiver is the first parameter of the returned handle. If `bindTo("abcdef")`, the new type is `(int)String`.

**Question 5.** `h.type() == (int,int)int`, why does `h.invokeExact(1,2);` as a statement fail, whereas `(int) h.invokeExact(1,2)` used in an assignment succeeds?

**Answer:** the statement produces return `void` and mismatches; the `(int)` cast expects return `int`, matching the target.

**Question 6.** Why can `asType(MethodType.methodType(long.class,int.class,int.class))` solve the need to get a `long`, yet not turn the original `h` into a `long`-returning handle?

**Answer:** `asType` returns a new handle with the new signature and converts the `int` → `long` result. The original `h`'s `MethodType` is immutable and remains `(int,int)int`.

**Question 7.** If `lookup.findStatic(...)` reports `NoSuchMethodException`, should you fix `invokeExact` first or check which step?

**Answer:** check the method name, method kind, the `MethodType` used in lookup, and the declaring class. There is not yet a valid handle to call, so this is not a type mismatch error at `invokeExact`.

**Question 8.** A target `int compute(int)` throws `IllegalStateException` inside its body when called via `invokeExact` with the right signature. Does the exception become `InvocationTargetException` by default?

**Answer:** no. Method handle invocation propagates exceptions thrown by the target directly. `InvocationTargetException` is a wrapper commonly seen in Core Reflection `Method.invoke`/`Constructor.newInstance`; the two mechanisms should not be conflated.

**Question 9.** A generic helper returning `T` writes `return (T) h.invokeExact(1,2);` while the target returns `int`. Why can't a caller with `Integer value = helper(...)` fix the mismatch?

**Answer:** the `invokeExact` descriptor is generated at the **call site inside the helper**, where `T` is erased and does not specify an `int` return. A cast at another caller layer cannot change that bytecode descriptor. You need a helper with a concrete `int` type or an appropriate dynamic invocation/adaptation mechanism.

## 15. Official references

- **Java SE 21 — `MethodHandle` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html — defines `invokeExact`, `invoke`, `asType`, call-site descriptors, exact matching, and `WrongMethodTypeException`.
- **Java SE 21 — `MethodType` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html — structure of parameter lists and return types.
- **Java SE 21 — `MethodHandles.Lookup` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html — `findStatic`, `findVirtual`, and lookup access rights.
- **Java SE 21 — `WrongMethodTypeException` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html — exception when a call site or adaptation is incompatible.
- **Java Language Specification 21, §15.12:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12 — polymorphic signatures and how parameter/return types are determined in Java source.
- **Java Virtual Machine Specification 21, §6.5 `invokevirtual`:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.invokevirtual — type equality when `invokeExact` executes.

> **Remember:** With `invokeExact`, you must read `handle.type()` **from left to right and including the result type**. When the caller differs from the handle in any static type, the JVM does not convert automatically; fix the caller expression or create an adapter with an explicit `MethodType`.
