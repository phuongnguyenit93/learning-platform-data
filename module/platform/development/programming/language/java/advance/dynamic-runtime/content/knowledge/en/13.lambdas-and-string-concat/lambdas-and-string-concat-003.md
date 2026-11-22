# 13.3 Distinguishing `factoryType`, `interfaceMethodType`, `implementation`, and `dynamicMethodType`

In Java 8 and later, the compiler often uses the `invokedynamic` bytecode instruction together with `java.lang.invoke.LambdaMetafactory.metafactory` to implement lambda expressions and method references. When viewing `javap -v`, you will see several `MethodType`s along with a `MethodHandle` describing **completely different things**:

- **`factoryType`** describes how to **create the function object**, i.e., the type of the `invokedynamic` call site itself.
- **`interfaceMethodType`** describes the **JVM signature of the SAM method** that the function object must implement, usually the *erased* signature.
- **`implementation`** is a **direct MethodHandle** pointing to the method/constructor that actually executes the behavior, which may include captured parameters and a receiver.
- **`dynamicMethodType`** describes the **specialized** (*instantiated method type*) signature used to check parameters/return value when invoking the SAM, for example `(String)String` instead of the erased SAM `(Object)Object`.

These four pieces of information are not synonymous, even though a few signatures may occasionally happen to look the same. The differences between them determine whether lambda linkage succeeds, when variables are captured, how the body is invoked, runtime type checking, and the causes of `LambdaConversionException` or `ClassCastException`.

This article uses Java 17 as the baseline; the code runs with `javac --release 17` and JDK 17+. All examples use the official `java.lang.invoke` API, without needing ASM or internal JDK source code.

## 1. The Contract of `LambdaMetafactory.metafactory`

This is the actual signature of the bootstrap method:

~~~java
public static CallSite metafactory(
    MethodHandles.Lookup caller,
    String interfaceMethodName,
    MethodType factoryType,
    MethodType interfaceMethodType,
    MethodHandle implementation,
    MethodType dynamicMethodType
) throws LambdaConversionException
~~~

The snippet above is an **API signature for reading**, not a declaration for learners to paste into a class. The rest focuses on the four parameters after `caller` and `interfaceMethodName`.

| Component | What does it describe? | Example when creating `Function<String,String>` from `String upper(String)` |
| --- | --- | --- |
| `factoryType` | Type of the **factory call site** that creates the function object; parameters are **captured values**, return type is the functional interface | `()Function` if nothing is captured |
| `interfaceMethodType` | SAM signature **implemented by the function object at the JVM level**, with the name from `interfaceMethodName`; may have generics erased | `(Object)Object` because `Function.apply(T)` erases to `apply(Object):Object` |
| `implementation` | Direct method handle to the body method/constructor; full type includes receiver if instance method and captured parameters if any | `(String)String` pointing to `upper(String)` |
| `dynamicMethodType` | **Instantiated/specialized** SAM signature for runtime checking before/after invoking the implementation | `(String)String` |

In the non-capturing example above, `implementation.type()` and `dynamicMethodType` are both `(String)String`; **that is just a coincidence in signature**, not two identical roles. As soon as one variable is captured, the implementation gains an extra parameter while the dynamic method still only describes the arguments of `apply`.

### The other two implicit parameters

- `caller` is a `MethodHandles.Lookup` with the privileges of the **class containing the invokedynamic instruction**. According to the `metafactory` API, it requires a lookup with **full privilege access**. When the JVM invokes the BSM for `invokedynamic`, the JVM supplies the lookup itself; when calling directly from Java source as in section 5's example, use `MethodHandles.lookup()` in a class with appropriate privileges.
- `interfaceMethodName` is the **method name** that the function object needs to implement, such as `"apply"` for `Function`, `"map"` for a custom interface, or `"applyAsInt"` for `ToIntFunction`. This name does not have to match the implementation method name.

When actually linking via `invokedynamic` bytecode, the JVM passes **three standard arguments**: `caller`, `interfaceMethodName`, and `factoryType`, inferred from the call instruction context/name-and-type. The three **static bootstrap arguments** of `LambdaMetafactory.metafactory` are `interfaceMethodType`, `implementation`, and `dynamicMethodType`. They reside in the class file's `BootstrapMethods` metadata and are not counted as captured runtime variables.

## 2. Three phases: linkage, capture, and invocation

`LambdaMetafactory` has three distinct points in time, and misreading the phase often leads to misunderstanding `factoryType`.

~~~text
(1) LINKAGE — JVM resolves the invokedynamic site
    caller = Lookup of the class containing the site
    name = SAM name, e.g. "apply"
    factoryType = (String)Function
    interfaceMethodType = (Object)Object
    implementation = MH (String,String)String
    dynamicMethodType = (String)String
                     |
                     v
           LambdaMetafactory.metafactory(...)
                     |
                     v
        CallSite type = (String)Function
                     |
                     v
(2) CAPTURE — invoke CallSite target with runtime prefix "Hi-"
        factory("Hi-") -> Function object
                     |
                     v
(3) INVOCATION — invoke SAM method on the function object
        function.apply("Ada")
                     |
             dynamic (String)String
                     |
             implementation(prefix,text)
                     |
                     v
                   "Hi-Ada"
~~~

**Linkage**: The BSM receives the types/name/handle/metadata, validates constraints, and returns a `CallSite`. `CallSite.type()` must equal `factoryType`. The JVM may bootstrap before the first execution; do not rely hard on the exact timing for side effects.

**Capture**: The `CallSite`'s target handle is invoked with **the runtime values of captured variables**. It returns an object of the functional interface type. Capture may create a new object or reuse a suitable one; do not assume a specific identity or allocation behavior.

**Invocation**: The caller invokes the SAM method such as `f.apply(input)`. The function object forwards the captured values (stored at capture time) and the invocation arguments to the implementation, with any necessary type checks/conversions.

Specifically:

- `factoryType` governs **capture-time**: the number/types of captured arguments and the returned function object type.
- `interfaceMethodType` governs the **actual method signature that must be implemented** on the function object.
- `dynamicMethodType` governs the **type constraints checked when calling the SAM**.
- `implementation` governs the **actual behavior** of the method body.

Do not confuse "captured values" with "static bootstrap arguments": a captured value is usually an object/primitive taken from the program **each time the factory runs**, whereas static arguments are metadata in the **constant pool** used at linkage time.

## 3. Non-capturing example: why `()Function` and `(Object)Object`?

Take the Java method:

~~~java
static String upper(String text) {
    return text.toUpperCase(java.util.Locale.ROOT);
}
~~~

And the method reference:

~~~java
java.util.function.Function<String, String> f = MyClass::upper;
~~~

The two snippets above are just **illustrative snippets** (class `MyClass` is not defined here); the complete program is in section 6.

### Type analysis

1. `Function<T,R>.apply(T)` has the JVM signature after erasure **`(Object)Object`**. Generic type arguments `<String,String>` do not change the JVM descriptor of `Function.apply`.
2. `dynamicMethodType` specializes the SAM type to **`(String)String`**, because the compiler knows the invocation expects a `String` argument/result.
3. Implementation `MyClass.upper` is a direct static method of type **`(String)String`**.
4. This method reference **captures no variables**. Therefore, the factory type has no inputs and returns a functional interface object: **`()Function`**.

The four fields:

~~~text
factoryType          = ()Function
interfaceMethodType  = (Object)Object
implementation.type  = (String)String
dynamicMethodType    = (String)String
~~~

When code calls `f.apply("java")`, the JVM uses the erased interface call `apply(Object):Object`, and the function object can perform a **runtime cast to `String`** before calling the implementation. The actual return value is a String and is used under the appropriate generic type.

**Why isn't `interfaceMethodType` `(String)String`?** Because the generic `Function.apply` actually has the descriptor `(Object)Object` after erasure. If it implemented a method with a different descriptor on the object while omitting the erased method, a caller executing `invokeinterface Function.apply(Object)Object` would not find the promised method.

**Why isn't `factoryType` `(String)String`?** The factory site **creates the Function object**, it does not directly call `upper`. The call `f.apply(...)` happens later.

## 4. Capturing example: `K + N = M` and parameter order

Consider:

~~~java
static String combine(String prefix, String text) {
    return prefix + text;
}
~~~

A creator method:

~~~java
Function<String, String> withPrefix(String prefix) {
    return text -> combine(prefix, text);
}
~~~

This is also just an **illustrative snippet**; the complete programs below declare full types and classes.

The lambda above has:

- `K=1` captured parameter: `prefix` of type `String`, hence `factoryType=(String)Function`.
- `N=1` SAM invocation parameter: `text` of type `String` (in erased form `Object`), hence `interfaceMethodType=(Object)Object`, `dynamicMethodType=(String)String`.
- `M=2` implementation parameters: `prefix` and `text`, hence `implementation=(String,String)String`.

The fundamental linkage formula of `LambdaMetafactory` is:

\[
K+N=M
\]

Where **K** is the number of capture arguments received by the factory, **N** is the number of parameters of the SAM method when invoking the function object, and **M** is the number of parameters in the **implementation MethodHandle**, **including the receiver of an instance method** when applicable.

~~~text
factoryType (String)Function             K = 1
               |
               | prefix = "Hi-"
               v
          Function object
               |
               | .apply(text="Ada")       N = 1
               v
implementation (String,String)String      M = 2
                prefix,text
                "Hi-","Ada"
               |
               v
              "Hi-Ada"
~~~

Do not add captured parameters to `dynamicMethodType`: it only describes the **SAM invocation**. Also do not add `text` to `factoryType`: at capture time, the input `text` has not appeared yet.

## 5. Complete program: calling `LambdaMetafactory.metafactory` directly

This section **calls the BSM API directly in Java** to see the exact four parameters, rather than generating an invokedynamic opcode. A real `invokedynamic` bytecode example is shown in section 6.

Save **`MetaFactoryTypesDemo.java`**:

~~~java
import java.lang.invoke.*;

public class MetaFactoryTypesDemo {
    @FunctionalInterface
    public interface Mapper<T> {
        T map(T value);
    }

    public static String combine(String prefix, String text) {
        return prefix + text;
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodType factoryType =
                MethodType.methodType(Mapper.class, String.class);
        MethodType interfaceMethodType =
                MethodType.methodType(Object.class, Object.class);

        MethodHandle implementation = lookup.findStatic(
                MetaFactoryTypesDemo.class, "combine",
                MethodType.methodType(
                        String.class, String.class, String.class));

        MethodType dynamicMethodType =
                MethodType.methodType(String.class, String.class);

        CallSite site = LambdaMetafactory.metafactory(
                lookup, "map", factoryType, interfaceMethodType,
                implementation, dynamicMethodType);

        System.out.println("factoryType=" + factoryType);
        System.out.println("interfaceMethodType=" + interfaceMethodType);
        System.out.println("implementation=" + implementation.type());
        System.out.println("dynamicMethodType=" + dynamicMethodType);
        System.out.println("callSiteType=" + site.type());

        Mapper<String> mapper = (Mapper<String>)
                site.getTarget().invokeExact("Hi-");
        System.out.println("map=" + mapper.map("Ada"));

        Mapper raw = mapper;
        try {
            Object invalid = raw.map(Integer.valueOf(42));
            System.out.println("unexpected=" + invalid);
        } catch (ClassCastException ex) {
            System.out.println("rawInput=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run:

~~~sh
javac --release 17 MetaFactoryTypesDemo.java
java MetaFactoryTypesDemo
~~~

**Exact stdout:**

~~~text
factoryType=(String)Mapper
interfaceMethodType=(Object)Object
implementation=(String,String)String
dynamicMethodType=(String)String
callSiteType=(String)Mapper
map=Hi-Ada
rawInput=ClassCastException
~~~

Line-by-line analysis:

1. `factoryType` is `(String)Mapper` because the factory takes one captured `prefix` and returns a `Mapper`. It does **not** return String; String is the result of the `map` call later.
2. `interfaceMethodType` is `(Object)Object` because `Mapper<T>.map(T)` erases to `map(Object):Object`.
3. `implementation` is a direct handle to `combine(String,String):String`, obtained from `lookup.findStatic`. It takes **2** arguments.
4. `dynamicMethodType` is `(String)String`: the SAM parameter/return after specializing `T=String`.
5. `LambdaMetafactory.metafactory(...)` returns a `CallSite` of type `(String)Mapper`, matching `factoryType`.
6. `site.getTarget().invokeExact("Hi-")` performs **capture**. `"Hi-"` is a runtime value passed to the factory, not an argument to `metafactory`. Casting the call-site return to `Mapper` is required for `invokeExact`.
7. `mapper.map("Ada")` is **invocation**. The generated function object forwards `"Hi-"` and `"Ada"` to the implementation, returning `"Hi-Ada"`.
8. The `raw` variable deliberately bypasses source-level generic checking; because the erased method accepts Object, calling with `Integer(42)` gets through, but the generated implementation **casts to String** according to `dynamicMethodType` and throws `ClassCastException`. This is why the dynamic type is not merely decorative information.

`@SuppressWarnings` only suppresses raw/unchecked warnings in the demo; it **does not disable runtime checking by the type system**. In normal applications, avoid raw types and unchecked conversions.

### Equivalent semantic expression

~~~text
CallSite target (String)Mapper
          |
       "Hi-"         [capture, once when creating object]
          |
          v
       Mapper object
          |
     map("Ada")      [SAM invocation]
          |
          v
 combine("Hi-","Ada") [implementation, 2 parameters]
          |
          v
      "Hi-Ada"
~~~

This is a **semantic diagram**; it does not promise how the implementation class is generated, whether there is a hidden class or not, or whether a new object is created on every capture.

## 6. `javap` for Java source lambdas: where are the three static args?

To see the compiler generate `invokedynamic` automatically, create **`CompiledLambdaTypesDemo.java`**:

~~~java
import java.util.Locale;
import java.util.function.Function;

public class CompiledLambdaTypesDemo {
    static String upper(String text) {
        return text.toUpperCase(Locale.ROOT);
    }

    static Function<String, String> withPrefix(String prefix) {
        return text -> prefix + text;
    }

    public static void main(String[] args) {
        Function<String, String> direct =
                CompiledLambdaTypesDemo::upper;
        Function<String, String> captured = withPrefix("Hi-");

        System.out.println("direct=" + direct.apply("java"));
        System.out.println("captured=" + captured.apply("Ada"));

        String value = args.length == 0 ? "X" : args[0];
        System.out.println("concat=" + ("value=" + value));
    }
}
~~~

~~~sh
javac --release 17 CompiledLambdaTypesDemo.java
java CompiledLambdaTypesDemo
javap -v -p CompiledLambdaTypesDemo
~~~

**Stdout of the `java` command:**

~~~text
direct=JAVA
captured=Hi-Ada
concat=value=X
~~~

In the OpenJDK build used for verification, `javap -v` displays the lambda-related `InvokeDynamic` sites with their corresponding descriptors:

~~~text
apply:()Ljava/util/function/Function;
apply:(Ljava/lang/String;)Ljava/util/function/Function;
~~~

And in `BootstrapMethods` for these sites, the bootstrap method handle points to `java/lang/invoke/LambdaMetafactory.metafactory`, with **three static arguments** in order:

~~~text
1. samMethodType          (Ljava/lang/Object;)Ljava/lang/Object;
2. implMethod             REF_invokeStatic ... upper(...) or lambda$withPrefix$0(...)
3. instantiatedMethodType (Ljava/lang/String;)Ljava/lang/String;
~~~

The `#...` constant pool indices depend on how the compiler generates the class; there is no need to memorize index numbers. Remember the **role** of each piece of information:

| Site | `invokedynamic` descriptor = factoryType | Erased SAM = interfaceMethodType | Direct implementation | Instantiated SAM = dynamicMethodType |
| --- | --- | --- | --- | --- |
| `CompiledLambdaTypesDemo::upper` | `()Function` | `(Object)Object` | `upper(String)String` | `(String)String` |
| `text -> prefix + text` in `withPrefix` | `(String)Function` | `(Object)Object` | Compiler-generated `lambda$withPrefix$0(String,String)String` | `(String)String` |

**Important:** `factoryType` is in the **descriptor of `InvokeDynamic`**, not in the three static args of `LambdaMetafactory`. Conversely, the three static args are `interfaceMethodType`, direct `implementation`, and `dynamicMethodType`. The JVM supplies `caller Lookup` and `interfaceMethodName` automatically during linkage.

With different compilers or different flags, the bytecode may have an equivalent structure while generating synthetic methods or optimizing concatenation differently; do not assume synthetic names like `lambda$...` are stable public APIs.

### Why does the `implementation` of a capturing lambda have two parameters?

The compiler desugars the body `text -> prefix + text` into a method taking **captures first**, followed by SAM invocation arguments. For example:

~~~java
private static String lambda$withPrefix$0(
        String prefix, String text) {
    return prefix + text;
}
~~~

This snippet is only an **illustrative model of a compiler-generated method**, not a declaration you should add to existing source (adding it can easily collide with compiler-generated names). Its MH type is `(String,String)String`; capture holds `prefix`, and then `apply` passes `text` into the remaining slot.

**Do not confuse `prefix` with a static BSM argument:** `prefix` is a **dynamic operand** of the factory site at runtime, so it can differ per function object; whereas the three static BSM args are metadata used to configure how the function object is created.

## 7. Linkage constraints: K, N, M, and type adaptation direction

The `LambdaMetafactory` JavaDoc names:

- **K** = number of parameters of `factoryType`, types `D1...Dk`, return `Rd` (functional interface).
- **N** = number of parameters of `interfaceMethodType`, types `U1...Un`, return `Ru`.
- **M** = number of parameters of `implementation.type()`, types `A1...Am`, return `Ra`. If the implementation is an instance method, the MH type **already includes the receiver first**.
- **N** is also the number of parameters of `dynamicMethodType`, types `T1...Tn`, return `Rt`.

Core invariants:

1. **`K + N = M`.** Captured arguments and SAM invocation arguments must supply the exact number of arguments for the implementation.
2. **`Di = Ai` for i from 1 to K.** The type of each captured argument in the factory must **match exactly** the type of the corresponding leading position in the implementation handle. You cannot arbitrarily assume widening/casting for captures.
3. **`interfaceMethodType` and `dynamicMethodType` have the same N.** Each `Ti` either equals `Ui`, or both are reference types and `Ti` is a subtype of `Ui`.
4. **`Rt` either equals `Ru`, or is a reference subtype of `Ru`.** The instantiated return type must be compatible with the erased return type of the SAM method.
5. **`Ti` must be adaptable to `A(K+i)`**, meaning the specialized type at SAM invocation can be passed to the implementation argument after the capture section, according to metafactory's specific adaptation table.
6. **If `Rt` is not `void`, `Ra` must be non-`void` and adaptable to `Rt`.** If `Rt` is `void`, the implementation may return a result and discard the value.
7. The return type `Rd` of `factoryType` must be a suitable interface; `implementation` must be a **direct method handle** referencing a method or constructor that metafactory can recognize. `caller` needs a lookup with full privilege access.

Example `MetaFactoryTypesDemo`:

~~~text
K=1: factoryType          (String)Mapper
N=1: interfaceMethodType  (Object)Object
M=2: implementation       (String,String)String
N=1: dynamicMethodType    (String)String

D1 = String
A1 = String       [capture matches exactly]
T1 = String
A2 = String       [SAM argument compatible]
Ru = Object
Rt = String       [String subtype Object]
Ra = String       [implementation return compatible]
K + N = M         [1 + 1 = 2]
~~~

**Why split `K` and `N`?** An implementation having 2 parameters does not mean the SAM also has 2 parameters. One may be a captured parameter and one may appear on each SAM invocation. That is why `factoryType` and `dynamicMethodType` must be separate.

### Link-time vs invocation-time type checks

- **Link-time:** metafactory checks argument counts and type relationships according to the contract to confirm a function object can be created. Violations may throw `LambdaConversionException`.
- **Capture-time:** the factory target is invoked with K captured values; for a bound instance method reference with a captured receiver, the contract requires this receiver to be non-null.
- **Invocation-time:** the function object's SAM method performs necessary conversions and may cast/check reference arguments or return values. If a caller forces a raw interface and passes the wrong type, it may get `ClassCastException`; no lambda re-linkage is needed.

**Note on the conversion table:** `LambdaMetafactory`'s adaptation rules are not simply calling `implementation.asType(...)` across all types in every situation. It has specific conditions: primitive widening, valid boxing/unboxing, reference casts/conversions, and runtime checks; for reference parameters, linkage-time adaptation has subtype restrictions. Do not assume "whatever `asType` can do, metafactory automatically does" to bypass invariants.

### `interfaceMethodType` and `dynamicMethodType` can be identical

If the SAM has no generics and the types already match, both can be `(int)boolean` or `(String)String`. Still, their purposes differ:

- interfaceMethodType = the bytecode method that must be implemented.
- dynamicMethodType = how that method is checked/specialized at invocation.

Do not force two different MethodTypes just to prove they have different roles.

## 8. Instance methods: the receiver can be a capture or a SAM argument

`MethodHandles.Lookup.findVirtual` returns a direct MH with the receiver as the **first parameter**, even though the source method does not write the receiver in parentheses.

Example `String.length()`:

~~~java
MethodHandle implementation = MethodHandles.lookup().findVirtual(
    String.class, "length", MethodType.methodType(int.class)
);
System.out.println(implementation.type()); // (String)int
~~~

This is an **illustrative snippet** in a context with `import java.lang.invoke.*`, not a standalone program. The receiver `String` is already **one of the M parameters** of the implementation.

### Two ways to interpret the same `String.length` implementation

| Method reference | `factoryType` | `interfaceMethodType` | `implementation` | `dynamicMethodType` |
| --- | --- | --- | --- | --- |
| Unbound receiver: `String::length` with `ToIntFunction<String>` | `()ToIntFunction` | `(Object)int` | `(String)int` | `(String)int` |
| Bound receiver: `"Hello"::length` with `Supplier<Integer>` | `(String)Supplier` | `()Object` | `(String)int` | `()Integer` |

**Unbound**: the receiver is passed in as an **argument of the SAM invocation**, so `K=0,N=1,M=1`. **Bound**: the receiver is **captured when the factory runs**, so `K=1,N=0,M=1`. With `Supplier<Integer>`, the `int` from the implementation is boxed to `Integer`, while the SAM erased return type is `Object`.

Do not call `String::length` a "0-parameter implementation" just because the Java method `length()` has no source parameters. The type of the *virtual MethodHandle* is `(String)int`.

### Example 2: unbound receiver, no capture

Save **`ReceiverTypesDemo.java`**:

~~~java
import java.lang.invoke.*;
import java.util.function.ToIntFunction;

public class ReceiverTypesDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle implementation = lookup.findVirtual(
                String.class, "length",
                MethodType.methodType(int.class));

        MethodType factoryType =
                MethodType.methodType(ToIntFunction.class);
        MethodType interfaceMethodType =
                MethodType.methodType(int.class, Object.class);
        MethodType dynamicMethodType =
                MethodType.methodType(int.class, String.class);

        CallSite site = LambdaMetafactory.metafactory(
                lookup, "applyAsInt", factoryType, interfaceMethodType,
                implementation, dynamicMethodType);

        System.out.println("factoryType=" + factoryType);
        System.out.println("interfaceMethodType=" + interfaceMethodType);
        System.out.println("implementation=" + implementation.type());
        System.out.println("dynamicMethodType=" + dynamicMethodType);

        ToIntFunction<String> length =
                (ToIntFunction<String>) site.getTarget().invokeExact();
        System.out.println("length=" + length.applyAsInt("Hello"));
    }
}
~~~

~~~sh
javac --release 17 ReceiverTypesDemo.java
java ReceiverTypesDemo
~~~

**Stdout:**

~~~text
factoryType=()ToIntFunction
interfaceMethodType=(Object)int
implementation=(String)int
dynamicMethodType=(String)int
length=5
~~~

Explanation: `site.getTarget().invokeExact()` takes no arguments because the factory does not capture; then `length.applyAsInt("Hello")` passes the String receiver as the SAM argument. The generated SAM implementation receives erased `Object`, checks/casts it to `String`, calls `String.length()`, and returns primitive `int`.

### Can a captured receiver be null?

By the `LambdaMetafactory` contract, when `implementation` references an instance method and there are captured arguments (`K>0`), **the first captured argument corresponding to the receiver must be non-null**. Do not design code that depends on a specific JVM detecting `null` on the exact same source line across all implementations/scenarios. In normal Java code, a null receiver in a bound method reference is invalid input.

## 9. Four reproducible linkage failures

A `MethodHandle` that looks "callable with `invoke`" is not necessarily accepted by `LambdaMetafactory.metafactory`. Metafactory has a stricter contract, especially regarding **factory return type, arity, subtype specialization, and direct implementation handle**.

### Example 3: `LambdaConversionException`

Save **`LinkageFailuresDemo.java`**:

~~~java
import java.lang.invoke.*;

public class LinkageFailuresDemo {
    @FunctionalInterface
    public interface Mapper<T> {
        T map(T value);
    }

    public static String combine(String prefix, String text) {
        return prefix + text;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle implementation = lookup.findStatic(
                LinkageFailuresDemo.class, "combine",
                MethodType.methodType(
                        String.class, String.class, String.class));
        MethodType interfaceMethodType =
                MethodType.methodType(Object.class, Object.class);
        MethodType dynamicMethodType =
                MethodType.methodType(String.class, String.class);
        MethodType factoryType =
                MethodType.methodType(Mapper.class, String.class);

        try {
            LambdaMetafactory.metafactory(
                    lookup, "map",
                    MethodType.methodType(String.class, String.class),
                    interfaceMethodType, implementation,
                    dynamicMethodType);
        } catch (LambdaConversionException ex) {
            System.out.println(
                    "notInterface=" + ex.getClass().getSimpleName());
        }

        try {
            LambdaMetafactory.metafactory(
                    lookup, "map",
                    MethodType.methodType(Mapper.class),
                    interfaceMethodType, implementation,
                    dynamicMethodType);
        } catch (LambdaConversionException ex) {
            System.out.println(
                    "wrongArity=" + ex.getClass().getSimpleName());
        }

        try {
            LambdaMetafactory.metafactory(
                    lookup, "map", factoryType,
                    interfaceMethodType, implementation,
                    MethodType.methodType(Object.class, Object.class));
        } catch (LambdaConversionException ex) {
            System.out.println(
                    "wrongSpecialization=" +
                    ex.getClass().getSimpleName());
        }

        MethodHandle indirect = MethodHandles.insertArguments(
                implementation, 0, "Hi-");
        try {
            LambdaMetafactory.metafactory(
                    lookup, "map",
                    MethodType.methodType(Mapper.class),
                    interfaceMethodType, indirect,
                    dynamicMethodType);
        } catch (LambdaConversionException ex) {
            System.out.println(
                    "notDirect=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~sh
javac --release 17 LinkageFailuresDemo.java
java LinkageFailuresDemo
~~~

**Stdout:**

~~~text
notInterface=LambdaConversionException
wrongArity=LambdaConversionException
wrongSpecialization=LambdaConversionException
notDirect=LambdaConversionException
~~~

Explanation of the four failures:

1. **`notInterface`:** `factoryType` returns `String` instead of an interface; violates the condition on return type `Rd`.
2. **`wrongArity`:** `factoryType=()Mapper` gives `K=0`, but the SAM has `N=1` and the implementation has `M=2`. `K+N!=M`.
3. **`wrongSpecialization`:** `dynamicMethodType=(Object)Object`, while the remaining implementation argument is `String`. The `Object` form of the SAM parameter lacks the type relationship needed to satisfy adaptation to the String implementation.
4. **`notDirect`:** `MethodHandles.insertArguments` creates an adapter with a bound prefix; this handle can be invoked on its own, but **it is not a direct method handle referencing a method/constructor directly** as required by `metafactory`. Even though arity was adjusted to `K=0,N=1,M=1`, directness is still invalid.

Key takeaway: a Java method being "callable" does not mean it is a valid **direct implementation method handle** for metafactory. When you need to capture a value, express it via a **`factoryType` parameter** (`K`) rather than passing an arbitrarily `bindTo`/`insertArguments` handle as the implementation. If it does not fit metafactory's restrictions, consider designing a directly addressable bridge method and creating a handle with `findStatic`/`findVirtual`.

**In compiler-generated programs**, an exception from the BSM occurring at linkage may be reported by the JVM as a `BootstrapMethodError` with the root cause. In this example we **call the `metafactory` API directly**, so we catch `LambdaConversionException` directly. These are two different error contexts; do not use a single exception type to explain every case.

## 10. Why can runtime errors appear even when linkage succeeded?

Suppose the interface is `Mapper<String>`:

~~~java
Mapper<String> mapper = ...;
String value = mapper.map("Ada");
~~~

Generic `T=String` helps the compiler catch mistyped calls. But at the bytecode level, the erased method is still `map(Object):Object`. If code uses a raw interface or an unchecked cast:

~~~java
Mapper raw = mapper;
Object value = raw.map(Integer.valueOf(42));
~~~

**This is an illustrative snippet, not standalone**, and example 1 already ran this case. The `Integer` argument passes through the erased SAM descriptor as `Object`, but its runtime type does not match `dynamicMethodType=(String)String`. The function object checks types/casts before calling the implementation, so it can throw `ClassCastException`.

When investigating, distinguish:

| Phase | Types/values checked | Common errors |
| --- | --- | --- |
| **Bootstrap/linkage** | Factory return interface, K+N=M, direct handle, interface/dynamic/implementation type relationships | `LambdaConversionException`, or `BootstrapMethodError` at indy level |
| **Capture** | K actual captured values, matching factory target types, valid instance receiver | `WrongMethodTypeException` if invoking factory MH with wrong descriptor; null receiver error |
| **SAM invocation** | N arguments of `apply`/`map`/`applyAsInt` against dynamic method type and implementation | `ClassCastException`, unboxing/implementation logic errors |
| **Target body** | Code inside the implementation method/constructor | Exceptions thrown by the implementation itself |

Do not change `dynamicMethodType` to `(Object)Object` just to avoid a cast if the implementation actually needs `String`. Doing so can violate linkage invariants or break the functional interface contract.

## 11. Connection to string concatenation: `StringConcatFactory` does not use the lambda quadruple

Under the same topic "Lambdas and string concatenation", `StringConcatFactory` uses **a different contract**. A modern compiler can emit indy for `"value=" + x`, but the corresponding BSM is typically:

~~~java
StringConcatFactory.makeConcat(
    MethodHandles.Lookup lookup,
    String name,
    MethodType concatType
);

StringConcatFactory.makeConcatWithConstants(
    MethodHandles.Lookup lookup,
    String name,
    MethodType concatType,
    String recipe,
    Object... constants
);
~~~

These are **API signatures for comparison**, not functions to declare yourself. `concatType` is the type of the call site that directly performs **string concatenation**, e.g. `(String,int)String`; it does not create a functional interface object and does not have `LambdaMetafactory`'s four fields `factoryType/interfaceMethodType/implementation/dynamicMethodType`.

`recipe` has special placeholders in the string:

- Character `\1`: consumes one **dynamic argument** of the call site.
- Character `\2`: consumes one **constant static bootstrap argument**.
- Ordinary characters: concatenated verbatim.

The number of `\1`s must match the number of dynamic arguments in `concatType`, and the number of `\2`s must match the number of constants (per the makeConcatWithConstants contract). Do not call a recipe `dynamicMethodType` — they describe completely different things.

### Example 4: calling StringConcatFactory directly to distinguish

Save **`ConcatContractDemo.java`**:

~~~java
import java.lang.invoke.*;

public class ConcatContractDemo {
    public static void main(String[] args) throws Throwable {
        MethodType concatType = MethodType.methodType(
                String.class, String.class, int.class);

        CallSite site = StringConcatFactory.makeConcatWithConstants(
                MethodHandles.lookup(), "makeConcatWithConstants",
                concatType, "\1 + \1");

        String result = (String)
                site.getTarget().invokeExact("Ada", 7);

        System.out.println("concatType=" + site.type());
        System.out.println("result=" + result);
    }
}
~~~

~~~sh
javac --release 17 ConcatContractDemo.java
java ConcatContractDemo
~~~

**Stdout:**

~~~text
concatType=(String,int)String
result=Ada + 7
~~~

`"Ada"` and `7` are **dynamic call arguments** of the concat target; the recipe `"\1 + \1"` has two placeholders matching `concatType`. There is no `Function`/`Supplier` or SAM interface.

**This is a direct factory API call**, and does not prove this program's bytecode has an indy site for concatenating `"Ada"` and `7`. To observe a **real compiler-generated `invokedynamic` concat**, run `javap -v -p CompiledLambdaTypesDemo` from section 6; in the tested `javac --release 17` environment, it shows `makeConcatWithConstants` call sites. How the compiler generates concat can vary by JDK/flags.

Comparison table:

| Criterion | `LambdaMetafactory` | `StringConcatFactory` |
| --- | --- | --- |
| What does the call site do? | Returns a functional interface object | Directly returns the concatenated string result |
| Implicit method type | `factoryType`, usually `()Function` or `(String)Function` | `concatType`, e.g. `(String,int)String` |
| Typical static args | `interfaceMethodType`, direct `implementation`, `dynamicMethodType` | `recipe` and possibly `constants` |
| Is there a later SAM method invocation? | Yes | No |
| Captures runtime values to hold for a function object? | Possible | No lambda capture under this protocol |

This is why you should not apply the four type names of `LambdaMetafactory` to every `invokedynamic`. `invokedynamic` is the general mechanism; **the specific bootstrap method defines the metadata protocol and linkage purpose**.

## 12. Some advanced points: bridge methods and `altMetafactory`

`LambdaMetafactory.metafactory` is the standard variant, sufficient for many simple lambdas. `altMetafactory` extends the protocol with flags such as:

- `FLAG_BRIDGES`: generates additional method signatures needed so the same behavior can be invoked through multiple VM descriptors (e.g., bridges for certain generic/covariant relationships).
- `FLAG_MARKERS`: adds appropriate marker interfaces.
- `FLAG_SERIALIZABLE`: requests the function object to follow the serializable protocol (with additional rules/limitations).

`altMetafactory` still has the three basic static components corresponding to `interfaceMethodType`, `implementation`, and `dynamicMethodType`, plus `flags` and flag-dependent metadata. Multiple method signatures do not turn `factoryType` into a SAM invocation type; it still designates the **factory call site**.

**Do not rely on the lambda's runtime class name to understand generic types.** The implementation class may be a hidden class or a JVM-optimized form; identity, binary name, and class file details are not stable APIs. Infer from `BootstrapMethods`/`InvokeDynamic`, the four types, and the published functional interface method.

Similarly, function objects created from lambdas do not guarantee identity by default between two captures. Do not use `==` or `System.identityHashCode` as a logic condition when objects are created from the same lambda expression.

## 13. Checklist for reading `javap -v -p`

When you encounter a bytecode line like:

~~~text
invokedynamic ... apply:(Ljava/lang/String;)Ljava/util/function/Function;
~~~

follow this order:

1. **Read the name and descriptor right at `InvokeDynamic`**. `apply` is `interfaceMethodName`; descriptor `(String)Function` is `factoryType`. It says there is one captured `String` and it returns a `Function`.
2. **Follow the bootstrap index into `BootstrapMethods`**. Check whether it is `LambdaMetafactory.metafactory` or another BSM.
3. **First static arg:** read the `MethodType` corresponding to `interfaceMethodType`, usually `(Object)Object` for `Function.apply`.
4. **Second static arg:** read the `MethodHandle` of `implementation`; check `REF_invokeStatic`/`REF_invokeVirtual`/`REF_newInvokeSpecial` and the full descriptor. If it is a virtual handle, remember the receiver is in the first position of the handle.
5. **Third static arg:** read `dynamicMethodType` — often named *instantiatedMethodType* in output/documentation. It describes the specialization for runtime checking, not including captured args.
6. **Count K, N, M.** If `K=1,N=1` then the implementation needs 2 parameters, except in cases that do not satisfy the protocol (which will not link).
7. **Check erased vs instantiated.** `(Object)Object` and `(String)String` can validly differ. The `String` type must specialize compatibly with `Object`.
8. **Identify captured values from bytecode before indy.** For example, `aload_0` pushes the captured prefix onto the stack; it is **not** in the three static args.
9. **Distinguish the call site from SAM invocation.** `invokedynamic` creates `Function`; `invokeinterface Function.apply` later invokes the behavior.
10. **If an error occurs**, determine whether it is linkage (`LambdaConversionException`/`BootstrapMethodError`), capture (`WrongMethodTypeException`/input), invocation (`ClassCastException`), or an exception thrown by the implementation body.

### Avoid these misinterpretations

- "`factoryType` is the signature of the implementation method." — False: it is the **factory** signature.
- "`interfaceMethodType` contains the generic types from Java source." — False in the case of generic erasure: it is usually `Object`.
- "`dynamicMethodType` also contains the captured prefix." — False: it describes the **SAM invocation** after specialization.
- "`implementation` always equals `dynamicMethodType`." — False if there are captures or an instance receiver with a different role.
- "The implementation of `String::length` has 0 parameters." — False for a virtual MethodHandle: the receiver is counted.
- "Static BSM arguments are the lambda's captured variables." — False: static args are linkage metadata; captures are runtime inputs to the factory.
- "You can pass a handle through `insertArguments` and always use it as `metafactory`'s `implementation`." — False: standard metafactory requires a direct handle.
- "Any handle callable via `invoke` can be used for metafactory." — False: the protocol has strict invariants and access constraints.
- "`LambdaMetafactory` always runs again every time `f.apply(...)` is called." — False: the BSM is used to link the site; SAM invocation is a different phase.
- "A non-capturing lambda always creates a new object every time." — Not guaranteed: metafactory may reuse objects.
- "`StringConcatFactory` also has `interfaceMethodType` and `dynamicMethodType`." — False: it has `concatType` and its own recipe/constant protocol.

## 14. Self-check exercises

**Question 1.** `Function<String,String> f = MyClass::upper` is non-capturing, `upper(String)String`. What are the four components?

**Answer:** `factoryType=()Function`, `interfaceMethodType=(Object)Object`, `implementation=(String)String` direct MH, `dynamicMethodType=(String)String`.

**Question 2.** For `text -> prefix + text`, `prefix` is a captured `String`; SAM `Function<String,String>`. `implementation` is `(String,String)String`. Calculate K, N, M.

**Answer:** `K=1`, `N=1`, `M=2`, so `K+N=M`. `factoryType=(String)Function`, `dynamicMethodType=(String)String`.

**Question 3.** Why doesn't `FactoryType=(String)Function` have a String parameter representing `text` which is also a SAM argument?

**Answer:** The factory only receives `prefix` at **capture** time and returns the Function object. `text` is received **later** by `Function.apply`; it belongs to `dynamicMethodType`/implementation at invocation.

**Question 4.** An `implementation` has type `(String)int` from `findVirtual(String.class,"length",()int)`, used as `String::length` with `ToIntFunction<String>`. Why is M equal to 1?

**Answer:** The String receiver is counted as the first parameter of the virtual MethodHandle even though the `length()` method has no source parameters. `K=0,N=1,M=1`.

**Question 5.** Why can `interfaceMethodType` of `Mapper<String>.map(String)` still be `(Object)Object`?

**Answer:** This is the method descriptor of `Mapper<T>.map(T)` after generic erasure. `dynamicMethodType=(String)String` describes the specialization for type checking at invocation.

**Question 6.** `factoryType=()Mapper`, SAM has one parameter, implementation has two parameters: is this valid?

**Answer:** No, because `K=0,N=1,M=2`, violating `K+N=M`. You need to capture a value or design a different implementation.

**Question 7.** If `implementation` is created using `MethodHandles.insertArguments(...)` to pre-bind `prefix`, will standard `LambdaMetafactory.metafactory` definitely accept it?

**Answer:** No. Standard metafactory requires a **direct method handle**. Adapters created by combinators do not automatically satisfy the directness constraint.

**Question 8.** A `Function` object is created successfully, but raw `Function.apply(42)` throws `ClassCastException`. Does that prove the BSM linked incorrectly?

**Answer:** No. The erased interface method accepts Object, but `dynamicMethodType` can require String; the runtime check rejects Integer.

**Question 9.** In `javap`, why is `factoryType` in `InvokeDynamic` while the other three parts are in `BootstrapMethods`?

**Answer:** The factory type is the method descriptor of the call site itself, passed by the JVM as an implicit BSM argument; `interfaceMethodType`, `implementation`, and `dynamicMethodType` are **the three static bootstrap arguments** of LambdaMetafactory.

**Question 10.** `StringConcatFactory.makeConcatWithConstants` can return `(String,int)String`. Is this a `factoryType` that creates a `Function`?

**Answer:** No. That is the `concatType` of a call site that directly concatenates strings; it does not have a SAM interface/implementation/dynamicMethodType per the lambda contract.

## 15. Official documentation

- Java SE 17, `LambdaMetafactory` — three phases, four main parameters, K/N/M, adaptation and linkage invariants: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html
- Java SE 17, `MethodType` — parameters, return type, and how method handle signatures are written: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html
- Java SE 17, `MethodHandles.Lookup` — `findStatic`, `findVirtual`, and lookup privileges: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java SE 17, `MethodHandle` — direct handles, `invokeExact`, `invoke`, adapters, and type: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html
- Java SE 17, `CallSite` — factory target and call site type: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html
- Java SE 17, `StringConcatFactory` — concatType, recipe, static constants, differences from lambda metafactory: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html
- JVMS 17, `4.7.23` — `BootstrapMethods` attribute, linking static arguments: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.23
- JVMS 17, `5.4.3.6` — dynamically-computed call site resolution: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6

**Conclusion:** `factoryType` determines **which captured values the factory receives and which functional object it returns**; `interfaceMethodType` determines **the SAM signature at the JVM level**; `implementation` specifies **the method/constructor executing the behavior with K+N parameters**; `dynamicMethodType` determines **the specialized SAM signature checked at invocation**. Remembering the three phases **linkage → capture → invocation** and the formula **`K+N=M`** will help decode `javap`, fix `LambdaConversionException`, and accurately distinguish lambda metafactory from string-concat bootstrap.