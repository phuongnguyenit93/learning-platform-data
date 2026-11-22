# 13.4 Direct Method Handle Constraints, Parameter Types, and Return Types of metafactory

**Module:** Java Advance - dynamic-runtime  
**Parent Topic:** 13. Lambdas and String Concatenation  
**Focus API:** `java.lang.invoke.LambdaMetafactory.metafactory`, `MethodHandle`, `MethodType`, and `CallSite`  
**Environment:** Java 17+.

## Objectives

`LambdaMetafactory` serves the mechanism for creating function objects for lambda expressions and method references. It links a **direct method handle** to a functional interface, can fix certain arguments when creating the object (capture), and only allows parameter/return type combinations that satisfy a precise set of conditions.

After this lesson, you will be able to:

1. Distinguish between **`factoryType`**, **`interfaceMethodType` (SAM)**, **`implementation.type()`**, and **`dynamicMethodType` (instantiated)**.
2. Explain why the implementation requires a **direct MethodHandle** to a method/constructor, and why an arbitrary adapter cannot be used as the implementation.
3. Compute and verify `K+N=M`, captured type equality `D_i=A_i`, parameter adaptation, and return adaptation of metafactory.
4. Distinguish the three phases **linkage → capture → invocation**, along with the errors that appear in each phase.
5. Write Java 17+ code with capturing lambdas, non-capturing lambdas, receiver method references, generic SAMs, and `void` returns; test the rejected cases.
6. Recognize the `LambdaMetafactory` bootstrap of `invokedynamic` in `javap` without confusing it with the `StringConcatFactory` string concatenation bootstrap.

## 1. What does metafactory create?

Consider a lambda:

~~~java
java.util.function.Function<String, String> f =
        value -> "[" + value + "]";
~~~

The compiler can lower the lambda into an `invokedynamic` leading to the `LambdaMetafactory.metafactory` bootstrap. The linkage result is a `CallSite`. **The target of the CallSite is a factory handle that creates a function object**, while the `implementation` passed to metafactory is a direct handle containing the logic that runs when the functional method is called.

~~~text
Lambda / method reference in Java
        |
        v
javac emits invokedynamic + bootstrap information
        |
        v
JVM links -> LambdaMetafactory.metafactory(...)
        |
        v
CallSite, type = factoryType
        |
        +-- target: factory MethodHandle
                      |
                      | CAPTURE: pass K captured values
                      v
              function object implements functional interface
                      |
                      | INVOCATION: pass N parameters of SAM
                      v
              direct implementation method/constructor
~~~

A non-capturing factory has a type such as `()TextOp`. A factory capturing `prefix` has a type `(String)TextOp`. Both **return a function object**, not the direct result of the implementation method. `TextOp.apply(...)` must still be called to execute the logic.

Metafactory may generate a class at runtime or reuse a suitable class. You must not assume the class name/identity of the lambda object is stable, nor use `==` between two lambda objects as a business contract.

## 2. The six parameters of `LambdaMetafactory.metafactory`

The API signature is presented for study:

~~~java
public static CallSite metafactory(
        MethodHandles.Lookup caller,
        String interfaceMethodName,
        MethodType factoryType,
        MethodType interfaceMethodType,
        MethodHandle implementation,
        MethodType dynamicMethodType
) throws LambdaConversionException;
~~~

This is an API-descriptive signature, **not code to rewrite the JDK class**. Some documentation uses equivalent names `invokedType`, `samMethodType`, `implMethod`, `instantiatedMethodType`.

| Parameter | Function | Example |
| --- | --- | --- |
| `caller` | `Lookup` of the function-creating party; must have **full privilege access** | `MethodHandles.lookup()` in a valid class |
| `interfaceMethodName` | Name of the functional interface method to be implemented | `"apply"` |
| `factoryType` | MethodType of the CallSite target: takes captured arguments, returns interface | `(String)TextOp` |
| `interfaceMethodType` | MethodType of the SAM method to be implemented | `(String)String` |
| `implementation` | **Direct** handle pointing to the implementation method/constructor | `join(String,String)String` |
| `dynamicMethodType` | Instantiated MethodType checked at invocation | `(String)String` |

### 2.1. In what order is `MethodType` written?

~~~java
MethodType factoryType =
        MethodType.methodType(TextOp.class, String.class);
MethodType samType =
        MethodType.methodType(String.class, String.class);
MethodType implType =
        MethodType.methodType(
                String.class, String.class, String.class);
~~~

This snippet assumes `TextOp` is already in scope; it is not a standalone file. With `MethodType.methodType(returnType, parameters...)`, **the return type is in the first position**, unlike how parameter lists are read in Java source:

~~~text
factoryType = (String)TextOp
samType     = (String)String
implType    = (String,String)String
~~~

The wrong order in `methodType(...)` can cause `Lookup.findStatic` not to find the method, or metafactory to reject linkage.

### 2.2. Factory type and implementation type are not the same

If the implementation is:

~~~java
static String join(String prefix, String value) {
    return prefix + value;
}
~~~

This is an illustrative method placed inside a class. The factory receives `prefix` and returns `TextOp`. A call to `TextOp.apply(value)` then supplies `value` to the implementation. The corresponding syntax when a CallSite is available:

~~~java
TextOp op = (TextOp) site.getTarget().invokeExact("pre:");
String output = op.apply("java");
~~~

This snippet is also illustrative in a scope having `site` and `TextOp`. `site.getTarget().type()` is `(String)TextOp`; **not** `(String,String)String` of the implementation. When calling the factory with `invokeExact`, both **the captured argument types and the return cast** at the call site must match the factory type.

## 3. Notation K, N, M and the four MethodTypes

Denote the types as in the Java SE 17 Javadoc:

| Kind | Structure | Meaning |
| --- | --- | --- |
| `factoryType` | `(D1,...,Dk) Rd` | K captured arguments, return `Rd` is the interface |
| `interfaceMethodType` | `(U1,...,Un) Ru` | N parameters of the SAM |
| `implementation.type()` | `(A1,...,Am) Ra` | M parameters of the execution method |
| `dynamicMethodType` | `(T1,...,Tn) Rt` | N parameters and return of the instantiated SAM |

With `String join(String prefix,String value)` and `TextOp.apply(String)String`:

~~~text
factoryType        = (String)TextOp          K=1
interfaceMethodType= (String)String          N=1
implementation     = (String,String)String   M=2
dynamicMethodType  = (String)String          N=1
K+N=M              = 1+1=2                  true
~~~

**Exact linkage constraints:**

1. **`Rd` must be an interface** that the function object implements. A `factoryType` returning `String` or a regular class is invalid.
2. **`implementation` must be a direct method handle** pointing to a method or constructor.
3. `interfaceMethodType` and `dynamicMethodType` have **the same number of parameters N**. For each position `i`, `Ti == Ui`, or both are reference types and `Ti` is a subtype of `Ui`.
4. Return type `Rt == Ru`, or both are reference types and `Rt` is a subtype of `Ru`.
5. **`K + N = M`**. Captured parameters and invocation parameters must equal the total number of implementation arguments.
6. For the leading captured parameters of the implementation: **`Di = Ai`** for `i=1..K`, requiring **type equality** rather than just subtyping.
7. For invocation parameters: **`Ti` adaptable to `A(K+i)`** according to metafactory rules.
8. For the return type: **`Rt == void`**, or `Ra != void` and **`Ra` adaptable to `Rt`**.
9. If the implementation is an **instance method** and has captured arguments (`K>0`), the first captured argument acting as the receiver **must be non-null** per the API contract.

Do not replace these conditions with an intuition that "the runtime value type looks compatible". These conditions are mostly checked immediately at **linkage**, before any function object exists.

### 3.1. Captured types match **exactly**

Invalid example:

~~~text
factoryType           = (Object)TextOp
interfaceMethodType   = (String)String
implementation.type() = (String,String)String
dynamicMethodType     = (String)String
~~~

`D1=Object` whereas `A1=String`; therefore the condition `D1=A1` fails, and **`LambdaConversionException`** occurs at linkage. Even if at runtime `"pre:"` (a String) is passed to the factory, the compiler described the captured parameter type as `Object`, so it cannot be saved.

To be valid, set the factory captured type to `String`, or write a **direct helper method** that actually accepts `Object` at the capture position and handles the cast internally.

### 3.2. Parameter count mismatch is not fixed by varargs

If the implementation has `M=2`, the SAM has `N=1`, but the factory captures nothing `K=0`, then `K+N=M` becomes `0+1≠2`. Metafactory rejects it. It does not automatically pack/unpack varargs to make up for missing arguments.

For a direct handle pointing to an instance method, `MethodHandle.type()` already includes the **receiver** as the first parameter; it must be counted in `M`. The receiver can be in `K` (captured when the factory runs) or in `N` (passed by the SAM at invocation) if the interface signature matches.

### 3.3. Return type is an independent part of the contract

If the instantiated SAM requires `String` while the implementation returns `int`, there is no valid adaptation from primitive `int` to `String`. Conversely, if the instantiated type returns `void`, metafactory can accept an implementation that returns a value and **discard that value**. Distinguish:

~~~text
SAM:        (String)void
impl:       (String)String
instantiated:(String)void   -> can be valid, discard return

SAM:        (String)String
impl:       (String)void
instantiated:(String)String -> cannot synthesize a String return
~~~

This rule does not mean "arbitrary return type"; the direction of return value adaptation must be evaluated according to the Javadoc.

## 4. Direct MethodHandle: an unbypassable constraint

### 4.1. Direct handle and adapter handle

An appropriate `Lookup` creates a direct handle to a member:

~~~java
MethodHandle directStatic = lookup.findStatic(
        MetafactoryContractDemo.class, "upper",
        MethodType.methodType(String.class, String.class));

MethodHandle directVirtual = lookup.findVirtual(
        Prefixer.class, "join",
        MethodType.methodType(String.class, String.class));
~~~

This is an illustrative snippet inside `MetafactoryContractDemo` in section 8. `directStatic.type()=(String)String`. `directVirtual.type()=(Prefixer,String)String` because an instance method handle has the receiver as its first parameter.

`Lookup.findConstructor` also creates a direct handle for a constructor, with the handle's return type being the constructed class. Some handles from `Lookup.unreflect` can be direct references if access permissions allow.

An **adapter handle**, even if callable and having the right type, is **not automatically** a direct handle:

~~~java
MethodHandle bound = MethodHandles.insertArguments(
        join, 0, "bound:");
~~~

`join` is direct `(String,String)String`. `bound` is an adapter `(String)String` with one pre-bound argument. If `bound` is passed to `metafactory` as the implementation, it is rejected because it is **not direct** (verified in the demo). Other combinators such as `filterArguments`, `guardWithTest`, `bindTo`, and `asType` generally create adapters, and do not automatically turn a pipeline into a direct member reference.

**Do not identify directness by type alone.** A transformation that does not change the type may return the original handle in some cases; having equal types still does not prove the direct nature of a handle.

### 4.2. The right fix when arguments are pre-bound

Do not use `insertArguments(join, 0, "pre:")` and try to force metafactory to accept it. Let metafactory handle the capture:

~~~java
CallSite site = LambdaMetafactory.metafactory(
        lookup, "apply",
        MethodType.methodType(TextOp.class, String.class),
        MethodType.methodType(String.class, String.class),
        join,
        MethodType.methodType(String.class, String.class));
TextOp op = (TextOp) site.getTarget().invokeExact("pre:");
~~~

Here `join` remains direct, and the factory type expresses the **prefix capture** accurately. This snippet assumes `lookup`, `join`, and `TextOp` exist as in the full demo.

If a pipeline has already been built with multiple combinators and needs a functional API, consider a **direct helper method** that invokes the pipeline under a clear contract, or just use MethodHandle/adapters instead of using `LambdaMetafactory` as a general-purpose tool.

### 4.3. How to observe a direct handle

`Lookup.revealDirect(handle)` can return `MethodHandleInfo` when the handle is truly direct and the lookup has permission to crack the handle; for non-direct adapters, this check does not succeed. This is a **diagnostic** tool, not something that turns an adapter into a direct handle.

Besides directness, `caller` of metafactory must have **full privilege access**. `MethodHandles.publicLookup()` only allows accessing public members within its limits, so it does not satisfy the caller requirement here; the demo verifies `LambdaConversionException`. Do not use metafactory to bypass `private`, package access, or JPMS module boundaries.

## 5. Three phases of a metafactory-generated function

### 5.1. Linkage

`LambdaMetafactory.metafactory(...)` receives the lookup, method name, MethodTypes, and direct handle; it checks the contract and returns a `CallSite`. Class generation or class reuse controlled by the runtime may occur.

With direct API calls, linkage errors usually report **`LambdaConversionException`**. If metafactory is invoked as the bootstrap of an `invokedynamic` instruction, bootstrap/resolution errors may surface as **`BootstrapMethodError`** from the instruction side.

### 5.2. Capture

~~~java
TextOp first  = (TextOp) site.getTarget().invokeExact("pre:");
TextOp second = (TextOp) site.getTarget().invokeExact("tag:");
~~~

This is an illustrative snippet with site `(String)TextOp`. Each factory call supplies K captured values. All those values will be used by the function object when the SAM is called.

For an instance direct handle with a captured receiver, the documentation requires the receiver to be non-`null`. **Do not rely on a specific NPE throw time** to check the contract: the JVM/runtime may only surface the error when attempting to invoke the method; validate the receiver before capture if the API needs to be explicit.

### 5.3. Invocation

~~~java
System.out.println(first.apply("java"));
System.out.println(second.apply("java"));
~~~

When calling the SAM, the implementation receives **captured arguments first**, followed by **invocation arguments**. For example, with `join(String prefix,String value)`:

~~~text
factory("pre:") -> holds prefix
    -> apply("java") -> join("pre:", "java")
    -> "pre:java"
~~~

If the SAM is generic-erased and the instantiated type is narrower, the adapter may cast at invocation. Valid linkage does not mean every runtime object passed by a raw caller is valid.

## 6. Generic SAM and instantiated type

`java.util.function.Function<T,R>` has the source method `R apply(T value)`, but after erasure the runtime signature of the SAM is `(Object)Object`. For `Function<String,String>`, the instantiated method type can be `(String)String`.

~~~text
factoryType          = ()Function
interfaceMethodType  = (Object)Object
implementation.type  = (String)String
dynamicMethodType    = (String)String
~~~

The conditions:

- `K=0`, `N=1`, `M=1`.
- SAM `U1=Object`, instantiated `T1=String`: valid reference subtype.
- SAM return `Ru=Object`, instantiated return `Rt=String`: valid subtype.
- Invocation `T1=String` adaptable to implementation parameter `A1=String`; return `Ra=String` adaptable to `Rt=String`.

A `Function<String,String>` using proper generics will only accept `String` at compile-time source. However, if code uses a **raw Function** and passes `Integer`, the adapter can throw **`ClassCastException`** at invocation. This error is **different** from `LambdaConversionException` at linkage.

### 6.1. Instantiated type cannot arbitrarily "rename" types

A SAM `(String)String` and instantiated `(Integer)String` do **not** satisfy the rule `Ti == Ui` or `Ti` subtype of `Ui`, because `Integer` is not a subtype of `String`. Both having `Object` as a common supertype is not enough to link.

### 6.2. Adaptation rules from Q to S

The Java 17 Javadoc defines a specific adaptability table:

| Source Q → Target S | General adaptability | Notes |
| --- | --- | --- |
| Primitive → primitive | Widening primitive is valid, e.g., `int → long` | No arbitrary narrowing |
| Primitive → reference | Boxing according to matching wrapper relationship | Not every reference type accepts every primitive |
| Reference → primitive | Unboxing + widening possible per rules | Runtime may encounter cast/null failure |
| Reference → reference | Follows link-time subtype check and corresponding invocation-time cast | Link may pass, runtime object can still have wrong type |
| Implementation return → instantiated return | Adapt in the return direction; special case `Rt=void` | Cannot produce non-void result from void implementation |

Adaptability of **parameters** and of **returns** must not be inferred as a symmetric comparison. When an important case involves wrappers/primitives, consult the full table in the Java 17 `LambdaMetafactory` Javadoc.

Metafactory **does not perform varargs adaptations** the way a regular Java caller might expect; the compiler or a helper method must resolve the shape before linking.

## 7. Instance methods and captured receiver

For:

~~~java
final class Prefixer {
    String join(String value) { return "obj:" + value; }
}
~~~

This is a standalone snippet illustrating the idea; in the full demo, `Prefixer` holds the prefix in a field. With `Lookup.findVirtual(Prefixer.class,"join", MethodType.methodType(String.class,String.class))`, the direct handle has type:

~~~text
(Prefixer,String)String
~~~

If we want `TextOp.apply(String)String`, the factory captures the receiver:

~~~text
factoryType          = (Prefixer)TextOp       K=1
interfaceMethodType  = (String)String         N=1
implementation.type  = (Prefixer,String)String M=2
dynamicMethodType    = (String)String
~~~

`D1=Prefixer == A1`; `K+N=M`. The function object is created from a `Prefixer` instance and then receives `String` when `apply` is called.

If **not capturing the receiver**, the SAM must pass the receiver as a matching parameter, meaning the functional interface needs a two-argument signature, e.g., `(Prefixer,String)String`. Do not forget the receiver when counting M just because the source method defines one formal parameter `String`.

For a constructor direct handle, the handle's type returns the **new class instance**. When mapping to a non-capturing `Supplier<Foo>`, SAM `()Foo` can link to the direct constructor `()Foo`; the type/lookup conditions must still be satisfied.

## 8. Java 17 Practice: one program for multiple constraints

This example tests simultaneously:

- A factory capturing `prefix` and two distinct function objects.
- A non-capturing factory, direct implementation `upper(String)String`.
- Receiver capture for instance method `Prefixer.join`.
- `Function<String,String>` with erased SAM `(Object)Object`.
- `void` return of `Sink.accept` able to discard the `String` return from the implementation.
- Six type/handle configuration errors and one lookup privilege error, all observed at linkage.

**Standalone file:** `MetafactoryContractDemo.java`

~~~java
import java.lang.invoke.*;
import java.util.Locale;
import java.util.function.Function;

public final class MetafactoryContractDemo {
    @FunctionalInterface
    interface TextOp { String apply(String value); }

    @FunctionalInterface
    interface Sink { void accept(String value); }

    static final class Prefixer {
        private final String prefix;
        Prefixer(String prefix) { this.prefix = prefix; }
        String join(String value) { return prefix + value; }
    }

    private static String join(String prefix, String value) {
        return prefix + value;
    }

    private static String upper(String value) {
        return value.toUpperCase(Locale.ROOT);
    }

    private static int size(String value) {
        return value.length();
    }

    private static void invalid(String label, MethodType factory, MethodType sam,
                                MethodHandle implementation, MethodType instantiated) {
        try {
            LambdaMetafactory.metafactory(
                    MethodHandles.lookup(), "apply",
                    factory, sam, implementation, instantiated);
            System.out.println(label + "=UNEXPECTED_SUCCESS");
        } catch (LambdaConversionException expected) {
            System.out.println(label + "=LambdaConversionException");
        }
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType stringToString =
                MethodType.methodType(String.class, String.class);
        MethodHandle join = lookup.findStatic(
                MetafactoryContractDemo.class, "join",
                MethodType.methodType(
                        String.class, String.class, String.class));

        CallSite captured = LambdaMetafactory.metafactory(
                lookup, "apply",
                MethodType.methodType(TextOp.class, String.class),
                stringToString,
                join,
                stringToString);
        System.out.println("capturedSite=" + captured.type());
        System.out.println("capturedTarget=" + captured.getTarget().type());
        TextOp a = (TextOp) captured.getTarget().invokeExact("pre:");
        TextOp b = (TextOp) captured.getTarget().invokeExact("tag:");
        System.out.println("captureA=" + a.apply("java"));
        System.out.println("captureB=" + b.apply("java"));

        MethodHandle direct = lookup.findStatic(
                MetafactoryContractDemo.class, "upper", stringToString);
        CallSite none = LambdaMetafactory.metafactory(
                lookup, "apply", MethodType.methodType(TextOp.class),
                stringToString, direct, stringToString);
        TextOp upper = (TextOp) none.getTarget().invokeExact();
        System.out.println("noCapture=" + upper.apply("java"));

        MethodHandle virtual = lookup.findVirtual(
                Prefixer.class, "join", stringToString);
        CallSite receiverSite = LambdaMetafactory.metafactory(
                lookup, "apply",
                MethodType.methodType(TextOp.class, Prefixer.class),
                stringToString, virtual, stringToString);
        TextOp receiver = (TextOp) receiverSite.getTarget()
                .invokeExact(new Prefixer("obj:"));
        System.out.println("instanceCapture=" + receiver.apply("java"));

        MethodType genericSam =
                MethodType.methodType(Object.class, Object.class);
        Function<String, String> fn = (Function<String, String>)
                LambdaMetafactory.metafactory(
                    lookup, "apply",
                    MethodType.methodType(Function.class),
                    genericSam, direct, stringToString)
                    .getTarget().invokeExact();
        System.out.println("generic=" + fn.apply("java"));
        try {
            Function raw = fn;
            Object ignored = raw.apply(42);
            System.out.println("genericCast=UNEXPECTED_SUCCESS:" + ignored);
        } catch (ClassCastException expected) {
            System.out.println("genericCast=ClassCastException");
        }

        MethodType voidSam =
                MethodType.methodType(void.class, String.class);
        Sink sink = (Sink) LambdaMetafactory.metafactory(
                    lookup, "accept", MethodType.methodType(Sink.class),
                    voidSam, direct, voidSam)
                    .getTarget().invokeExact();
        sink.accept("java");
        System.out.println("discardReturn=ok");

        invalid("notDirect", MethodType.methodType(TextOp.class),
                stringToString,
                MethodHandles.insertArguments(join, 0, "bound:"),
                stringToString);
        invalid("wrongArity", MethodType.methodType(TextOp.class),
                stringToString, join, stringToString);
        invalid("wrongCapture", MethodType.methodType(TextOp.class, Object.class),
                stringToString, join, stringToString);
        invalid("wrongReturn", MethodType.methodType(TextOp.class),
                stringToString,
                lookup.findStatic(MetafactoryContractDemo.class, "size",
                                  MethodType.methodType(int.class, String.class)),
                stringToString);
        invalid("wrongInstantiated", MethodType.methodType(TextOp.class),
                stringToString, direct,
                MethodType.methodType(String.class, Integer.class));
        invalid("nonInterfaceFactory", MethodType.methodType(String.class),
                stringToString, direct, stringToString);
        try {
            LambdaMetafactory.metafactory(
                    MethodHandles.publicLookup(), "apply",
                    MethodType.methodType(TextOp.class),
                    stringToString, direct, stringToString);
            System.out.println("weakLookup=UNEXPECTED_SUCCESS");
        } catch (LambdaConversionException expected) {
            System.out.println("weakLookup=LambdaConversionException");
        }
    }
}
~~~

**Compile and run with JDK 17+:**

~~~bash
javac --release 17 -d out MetafactoryContractDemo.java
java -cp out MetafactoryContractDemo
~~~

`javac -d out` can create the `out` directory if it does not already exist. `@SuppressWarnings` is used only so the compiler does not warn about the intentional raw `Function` snippet for illustration.

**Stdout verified with the exact source code above:**

~~~text
capturedSite=(String)TextOp
capturedTarget=(String)TextOp
captureA=pre:java
captureB=tag:java
noCapture=JAVA
instanceCapture=obj:java
generic=JAVA
genericCast=ClassCastException
discardReturn=ok
notDirect=LambdaConversionException
wrongArity=LambdaConversionException
wrongCapture=LambdaConversionException
wrongReturn=LambdaConversionException
wrongInstantiated=LambdaConversionException
nonInterfaceFactory=LambdaConversionException
weakLookup=LambdaConversionException
~~~

### 8.1. Explanation of the success group

**`capturedSite=(String)TextOp` and `capturedTarget=(String)TextOp`:** The CallSite holds the factory target; both have `factoryType`. The target does **not** have `(String,String)String`, because the implementation is not the CallSite's target.

**`captureA=pre:java` / `captureB=tag:java`:** A direct method `join` takes two parameters, but only `value` comes from the SAM; `prefix` was captured via the factory.

**`noCapture=JAVA`:** The factory `()TextOp` needs no arguments. The direct implementation `upper` has one parameter for the SAM.

**`instanceCapture=obj:java`:** The `findVirtual` handle contains the receiver `Prefixer` as the first parameter. The factory starts by capturing the receiver, then `apply` supplies the `String`.

**`generic=JAVA`:** `Function.apply` erased takes `Object`/returns `Object`, instantiated `String`/`String`. **`genericCast=ClassCastException`:** A raw caller sending `Integer` causes the runtime adapter value check to fail; the earlier linkage was completely valid.

**`discardReturn=ok`:** The instantiated SAM returns `void`, so the `String` returned by the `upper` implementation is not returned from `Sink.accept`.

### 8.2. Explanation of the linkage error group

| Output line | Cause | How to fix |
| --- | --- | --- |
| `notDirect` | `insertArguments` creates an adapter handle, not direct | Put prefix in `factoryType`, keep `join` direct |
| `wrongArity` | `K=0,N=1,M=2` makes `K+N≠M` | Capture one argument or choose a one-parameter direct impl |
| `wrongCapture` | Factory captured `Object`, impl prefix is `String` | Use captured `String` for exact type equality |
| `wrongReturn` | Implementation returns `int`, instantiated requires `String` | Choose a direct method with an adaptable return |
| `wrongInstantiated` | SAM takes `String`, instantiated takes `Integer` | Choose a valid subtype/identical type |
| `nonInterfaceFactory` | Factory return is class `String`, not an interface | Return `TextOp` or a suitable interface |
| `weakLookup` | `publicLookup` lacks full privilege access | Use an authorized caller lookup |

All print `LambdaConversionException`, but their natures differ. When debugging, do not catch broadly and ignore `factoryType`/`interfaceMethodType`/`implementation.type()`/`dynamicMethodType`.

## 9. `invokedynamic`, bytecode, and direct implementation handle

A capturing lambda example helps visualize the compiler's work.

**Standalone file:** `LambdaBytecodeView.java`

~~~java
import java.util.function.Function;

public final class LambdaBytecodeView {
    static Function<String,String> withPrefix(String prefix) {
        return value -> prefix + value;
    }

    public static void main(String[] args) {
        Function<String,String> f = withPrefix("id:");
        System.out.println(f.apply("17"));
    }
}
~~~

Compile, run, and inspect:

~~~bash
javac --release 17 -d out LambdaBytecodeView.java
java -cp out LambdaBytecodeView
javap -v -c -p -classpath out LambdaBytecodeView
~~~

Stdout:

~~~text
id:17
~~~

Look for the following structures in `javap` (excerpt omits index/offset because they vary by artifact):

~~~text
InvokeDynamic ... apply:(Ljava/lang/String;)Ljava/util/function/Function;
BootstrapMethods:
  ... REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory:...
  ... REF_invokeStatic LambdaBytecodeView.lambda$withPrefix$0:
      (Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
~~~

Explanation:

- `withPrefix(prefix)` has a factory capturing one `String`, returning `Function`.
- The synthetic method `lambda$withPrefix$0` can take **prefix String + value String**, which is the direct implementation method referenced by the bootstrap.
- The two implementation arguments correspond to **K=1 capture** and **N=1 invocation**.
- In Java 17, `prefix + value` can also emit **another `invokedynamic`** for string concatenation, whose bootstrap may be `StringConcatFactory`. Same opcode, but **two different bootstrap protocols**.
- Constant pool indices and synthetic method names are not public API; bytecode contents may change across compilers. Learn to recognize the structure rather than memorizing the name `lambda$withPrefix$0`.

**Distinction:** Manually calling `LambdaMetafactory.metafactory(...)` in `main` as in the section 8 demo is a static API call, and **does not itself generate an `invokedynamic` instruction** for that call. `invokedynamic` only exists when the compiler/bytecode generator actually emits the corresponding instruction.

## 10. Distinguishing errors by phase

| Phase | Common error | Symptom | Verification step |
| --- | --- | --- | --- |
| Finding implementation | Wrong member name/type/access | `NoSuchMethodException`, `IllegalAccessException` | `Lookup.findStatic/findVirtual`, module visibility |
| Direct metafactory linkage | Non-direct handle, wrong K/N/M, wrong capture/return, lacking full privilege | `LambdaConversionException` | Four MethodTypes + directness + Lookup |
| Linkage via `invokedynamic` bytecode | Wrong bootstrap, throws error or returns CallSite violating contract | `BootstrapMethodError` in many cases | `javap`, BootstrapMethods, nested cause |
| Factory capture | `invokeExact` wrong factory descriptor | `WrongMethodTypeException` | `site.getTarget().type()` |
| Instance receiver capture | `null` receiver violates API precondition | Precondition violated; error may not appear immediately at capture | Validate receiver beforehand |
| Generic invocation | Runtime value incompatible with instantiated type | `ClassCastException` | Erased SAM/instantiated, actual data type |
| Implementation invocation | Target method logic throws error | Target method's exception | Distinguish business error from linkage error |

### 10.1. Checklist applicable immediately

1. Write down `interfaceMethodName`, `factoryType`, `interfaceMethodType`, `implementation.type()`, `dynamicMethodType`, `callerLookup`.
2. Check that the factory return is an interface; the implementation handle has a **direct member reference** and the lookup has sufficient privileges.
3. Count the arguments: `K + N = M`. For an instance method, count the **receiver** in M.
4. Compare each captured type `D_i=A_i`. Do not treat `Object`/`String` as "close enough".
5. Check that SAM and instantiated have the same N, `Ti` is identical/subtype of `Ui`, `Rt` is identical/subtype of `Ru`.
6. Check that `Ti` is adaptable to `A(K+i)`, and return `Ra` is adaptable to `Rt` or the instantiated return is `void`.
7. Only after successful linkage, check the signature when calling the factory target, the captured receiver, and runtime objects when invoking the SAM.

Do not "fix" `LambdaConversionException` by swallowing the exception and using a function object that was never created. Fix the linkage inputs.

## 11. Common misconceptions

1. **"A handle with the right type is direct."** False. An adapter can have the right type without being direct.
2. **"`insertArguments` is the equivalent way to capture in metafactory."** It creates an adapter, which does not satisfy direct implementation; proper capture is described in the factory type.
3. **"The factory target is the implementation handle."** False. The factory returns a function object; the implementation only runs when the SAM is called.
4. **"SAM and instantiated type are always identical."** False when the generic SAM is erased to `Object` while the concrete lambda requires `String`.
5. **"A captured String can be declared as Object because at runtime it is still a String."** False; captured type equality uses the type in `MethodType`.
6. **"Missing parameters can be filled in automatically with varargs."** False; `K+N=M` must hold, varargs adaptation is not done automatically by metafactory.
7. **"An instance method's receiver does not appear in MethodType."** False. A `findVirtual` handle has the receiver as an argument.
8. **"A runtime cast error is LambdaConversionException."** False. Adapter invocation can throw `ClassCastException` after linkage succeeds.
9. **"`publicLookup` is sufficient for metafactory if the implementation is public."** False; metafactory requires a full-privilege caller lookup.
10. **"Every function object allocates a new object."** There is no corresponding identity guarantee.
11. **"`invokedynamic` in string concatenation always uses LambdaMetafactory."** False, string concat has its own bootstrap.
12. **"Metafactory should replace all MethodHandles combinators."** False; it is designed for the lambda/method reference creation protocol.

## 12. How to apply in projects

For regular Java code, prefer lambda syntax and method references so the compiler infers the functional interface and generates the bootstrap according to the contract. Calling `metafactory` manually is useful when studying compilers, runtime dynamic linking, or emitting custom bytecode.

If designing a bytecode generator:

- Emit the exact **factory/capture descriptor**, do not mix it with the implementation signature.
- Choose a **direct method/constructor handle** that the caller has access to.
- Record the **erased SAM MethodType** matching the functional interface and the instantiated MethodType matching the generics.
- Compute K/N/M, receiver, primitive/reference conversions, and return policy accurately.
- Test all three phases: linkage, capture, invoke; test generic/raw misuse and exception propagation.
- Do not pass a `filterArguments`/`guardWithTest` pipeline directly into metafactory as the implementation. If needed, write a direct helper method with a suitable signature or use another MethodHandle API.

An incompatible runtime protocol should not be patched with broader Reflection permissions or uncontrolled `--add-opens`. Directness, type arity, and accessibility errors are **distinct issues**; identify the exact root cause.

## 13. Exercises

1. Given implementation `(Config,String,int)boolean`, we want the factory to capture `Config` and SAM `(String,int)boolean`. Determine `K,N,M` and a valid `factoryType`.
2. Given `findVirtual(Formatter.class,"format",MethodType.methodType(String.class,String.class))`, compute the actual `MethodType` of the direct handle. If capturing the receiver, what must the factory type be?
3. Why can `insertArguments(join,0,"x:")` and direct `upper(String)String` have the same type, yet only the direct one is accepted by metafactory?
4. When the erased SAM is `(Object)Object` and instantiated is `(String)String`, what happens if a raw `Function` receives an `Integer`?
5. If `Rt=void` and `Ra=String`, how is the implementation result handled? What if `Rt=String` but `Ra=void`?
6. Modify the demo so `factoryType=(Object)TextOp` while the implementation has a captured prefix `String`. List the violated invariant and predict the exception.
7. Read `javap -v -c` for `LambdaBytecodeView`: find the `LambdaMetafactory` bootstrap, the direct implementation handle, and the separate string concatenation opcode.
8. A bytecode generator needs to use a `guardWithTest` pipeline as behavior. Why cannot that adapter be passed directly as `implementation`? Propose a direct helper or alternative API.
9. Create a direct implementation returning `Number` while instantiated requires `String`. Check which return adaptation/link-time rule and runtime cast are actually applied.
10. Explain why `LambdaConversionException` (linkage) and `ClassCastException` (invocation) need to be handled by two different kinds of tests.

## 14. Key Takeaways

- `LambdaMetafactory` links a **direct MethodHandle** to a functional interface.
- `factoryType` describes **capture** and returns the interface; `interfaceMethodType` describes the SAM; `implementation.type()` describes the target method; `dynamicMethodType` describes the concrete type to enforce.
- **`K+N=M`**; captured prefix types must satisfy **`D_i=A_i` exactly**.
- SAM/instantiated types can differ due to **generic erasure**, but must satisfy subtype/adaptability rules.
- For an instance implementation, the receiver is a parameter of the direct handle and can be captured; a captured receiver must be non-null.
- **Linkage, capture, invocation** are three phases with different error types.
- The `CallSite` returned by metafactory has a target that is a **factory creating function objects**, not the implementation handle itself.
- String concatenation and lambdas can both use `invokedynamic`, but they use **different bootstraps**.

## Official Documentation

- [Java SE 17 — `LambdaMetafactory` and linkage/adaptation table](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html)
- [Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 17 — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Java SE 17 — `CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [Java SE 17 — `StringConcatFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html)
- [JVMS 17 `5.4.3.6` — Dynamic call site resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)
