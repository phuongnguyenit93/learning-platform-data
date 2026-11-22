# 6.3. Creating, Comparing, and Transforming MethodType; Distinguishing void from Void

## Learning Objectives

After this lesson, you can:

1. Accurately describe the meaning of `java.lang.invoke.MethodType` in the `MethodHandle` system: a return type and a sequence of parameter types in **order**, containing no method name or execution body.
2. Create a `MethodType` using the `methodType(...)` and `genericMethodType(...)` factories, and from a JVM method descriptor.
3. Read, compare, and transform types using `returnType`, `parameterType`, `parameterCount`, `equals`, `changeParameterType`, `changeReturnType`, `insertParameterTypes`, `appendParameterTypes`, `dropParameterTypes`, `erase`, `generic`, `wrap`, and `unwrap`.
4. Clearly distinguish between `void.class` and `Void.class`, especially when creating return types, parameter types, wrapper conversions, and call binding.
5. Explain why changing a `MethodType` **does not** automatically change the signature of the real method or of an existing `MethodHandle`; only bind/adapt the handle when the type contract matches.

**Context:** When using `MethodHandles.Lookup` to find a method or constructor, Java needs an exact runtime representation of the signature. The same method name can have multiple overloads; `MethodType` helps identify the parameter types and result type. It also appears in call site binding, bytecode descriptors, and `MethodHandle` transformation APIs.

## 1. What Does MethodType Represent?

A `MethodType` has the logical form:

```text
(P0, P1, ..., Pn)R
```

Where `P0..Pn` are the parameter classes/types in order, and `R` is the return type. There can be **0 parameters**. Every component is represented by a `Class<?>` object, such as `String.class`, `int.class`, or `void.class`.

Example:

```java
MethodType signature = MethodType.methodType(
        String.class, String.class, int.class);
System.out.println(signature);  // (String,int)String
```

This snippet requires importing `java.lang.invoke.MethodType`. It describes a call that takes a `String`, an `int`, and returns a `String`. It **does not** contain a method name, does not reference an owning class, does not find or execute a method on its own, and also does not contain checked exceptions in `throws`, generic type parameters, or annotations.

Key distinctions:

| Object | What information does it hold? | What is it used for? |
| --- | --- | --- |
| `MethodType` | Return type and list of parameter types | Describing/comparing/transforming JVM method handle signatures |
| `MethodHandle` | An invokable target along with its method type | Executing the call, after finding or creating/adapting the handle |
| `MethodHandles.Lookup` | Access-checking context and APIs for finding methods/fields/constructors | `findStatic`, `findVirtual`, `findConstructor`, ... |
| `java.lang.reflect.Method` | Reflective member of a class, name, modifiers, parameters ... | Querying metadata, `invoke` via reflection |

### 1.1. Static Methods, Instance Methods, and the Receiver

Given:

```java
class TextTools {
    static String join(String a, String b) { return a + b; }
    String echo(String value) { return value; }
}
```

This is a standalone illustration of **class declarations**, not a program with `main`. When looking up:

- `lookup.findStatic(TextTools.class, "join", MethodType.methodType(String.class, String.class, String.class))`: the lookup type describes the two `String` parameters of the static method, and the handle takes those two parameters.
- `lookup.findVirtual(TextTools.class, "echo", MethodType.methodType(String.class, String.class))`: the type passed to lookup describes the parameters **declared** by the instance method. The resulting handle typically has an additional `TextTools` **receiver** at the first parameter position of the handle, for example `(TextTools,String)String`.

Do not manually add the receiver to the `MethodType` passed to `findVirtual`; however, you **must** account for the receiver when using `invokeExact` on the returned handle. Constructor lookup, on the other hand, uses the return type `void.class` to represent the constructor being looked up, while the resulting handle returns an instance of the constructed class. Those relationships are contracts of each `Lookup` API, not a rule that “MethodType always adds a receiver”.

## 2. Creating MethodType with Factories

`MethodType` is **final, immutable**, and created via factories, with no public `new MethodType(...)` call.

### 2.1. Creating Signatures Without or With Parameters

```java
import java.lang.invoke.MethodType;

MethodType a = MethodType.methodType(void.class);                     // ()void
MethodType b = MethodType.methodType(int.class, long.class);         // (long)int
MethodType c = MethodType.methodType(
        String.class, String.class, int.class);                      // (String,int)String
```

Overloads allow passing parameters via `Class<?>[]` or `List<Class<?>>`. Parameter order matters: `(String,int)String` **differs** from `(int,String)String`. For a method declared to return `String`, you must pass `String.class` as the **first** argument to the factory, followed by the parameter types.

Example using a list:

```java
MethodType fromList = MethodType.methodType(
        String.class, java.util.List.of(String.class, int.class));
```

The snippet above is an illustration in a context where `MethodType` is already imported; it creates the same signature as variable `c` above.

### 2.2. Creating Generic Types

```java
MethodType generic = MethodType.genericMethodType(2);
// (Object,Object)Object

MethodType varargsStyle = MethodType.genericMethodType(2, true);
// (Object,Object,Object[])Object
```

This is a **signature with `Object` components**, not a Java generic method like `<T>`, and it cannot perform type inference for arbitrary methods. The variant with a trailing `Object[]` parameter is useful in certain dynamic argument-collection mechanisms. This type does not mean you can skip casting or runtime checks.

### 2.3. From a JVM Method Descriptor

A method descriptor is a bytecode-level representation, for example:

```text
(Ljava/lang/String;I)Ljava/lang/String;
```

It corresponds to `(String,int)String`. In a descriptor:
- `I` = `int`, `J` = `long`, `Z` = `boolean`, `V` = `void` (used only for the return type).
- `Ljava/lang/String;` represents a reference to `java.lang.String`.
- `[I` is `int[]`; `[Ljava/lang/String;` is `String[]`.
- The parentheses `(...)` contain the **parameter list**; the symbol after `)` is the return type.

```java
MethodType fromDescriptor = MethodType.fromMethodDescriptorString(
        "(Ljava/lang/String;I)Ljava/lang/String;",
        MethodType.class.getClassLoader());
String descriptor = fromDescriptor.toMethodDescriptorString();
```

This is an illustration using `MethodType` after importing it. `fromMethodDescriptorString` requires an appropriate `ClassLoader` to resolve reference names; using the wrong class loader can cause `TypeNotPresentException` or compatibility issues when multiple loaders define the same class name. A descriptor is a **JVM type**, not the human-readable `toString()` form.

## 3. Reading a Signature: Parameters and Return Type

Suppose:

```java
MethodType type = MethodType.methodType(
        String.class, String.class, int.class);
```

You can query:

| API | Value |
| --- | --- |
| `type.returnType()` | `String.class` |
| `type.parameterCount()` | `2` |
| `type.parameterType(0)` | `String.class` |
| `type.parameterType(1)` | `int.class` |
| `type.parameterList()` | Unmodifiable list `[String.class, int.class]` |
| `type.parameterArray()` | An array containing the parameter types; modifying the returned array does not modify `type` |
| `type.toString()` | `(String,int)String` |
| `type.toMethodDescriptorString()` | `(Ljava/lang/String;I)Ljava/lang/String;` |

The index for `parameterType(index)` starts at 0 and lies in `[0, parameterCount())`. Going out of bounds throws `IndexOutOfBoundsException`.

`lastParameterType()` returns the last parameter type, but for a signature with **no parameters**, it returns the **sentinel `void.class`** (which does not mean the signature has a `void` parameter). This is convenient for some varargs operations; when exact logic is needed, you should still check `parameterCount()`.

## 4. Comparing MethodType and Immutability

Two `MethodType` instances are equal according to `equals` if they have:

1. **The same return type**, and
2. **The same number, order, and types of all parameters**.

```java
MethodType first = MethodType.methodType(
        String.class, String.class, int.class);
MethodType second = MethodType.methodType(
        String.class, new Class<?>[] { String.class, int.class });
MethodType different = MethodType.methodType(
        String.class, int.class, String.class);

System.out.println(first.equals(second));    // true
System.out.println(first.equals(different)); // false
```

This is an illustrative example with `MethodType` imported. Do not use `first == second` as a contractual comparison rule: the factory **may cache** instances, but it does not guarantee that two creations of the same signature always return the same object. `equals`/`hashCode` are the basis for `Map<MethodType, ...>` keys and logical comparison.

`MethodType` is immutable: every `change...`, `insert...`, `drop...`, `erase`, `wrap`, `unwrap` method returns a **conceptually new** `MethodType`, or may reuse an existing object if the signature does not change. There is no “in-place” mutation; holding the original variable does not automatically update it.

Also note: `Class<?>` is tied to class identity and class loader. Two classes with the **same name** but defined by two different class loaders are two different types; the corresponding two `MethodType` instances may not be `equals`, even if their `toString` or descriptor output looks identical.

## 5. Transforming Parameters and Return Type

Suppose the base signature is:

```java
MethodType base = MethodType.methodType(
        String.class, String.class, int.class); // (String,int)String
```

### 5.1. Changing a Parameter: `changeParameterType`

```java
MethodType changed = base.changeParameterType(1, long.class);
// (String,long)String
```

`1` is the index of the `int` parameter; it is replaced with `long`. The return type and other parameters remain unchanged. A non-existent index throws `IndexOutOfBoundsException`; `void.class` is invalid as a parameter and throws `IllegalArgumentException`.

### 5.2. Changing the Return Type: `changeReturnType`

```java
MethodType noReturn = base.changeReturnType(void.class);
// (String,int)void
```

`void.class` **is valid in the return position**. Replacing it with `Void.class` creates a different signature: `(String,int)Void`.

### 5.3. Inserting and Appending Parameters

```java
MethodType inserted = base.insertParameterTypes(1, boolean.class);
// (String,boolean,int)String

MethodType appended = base.appendParameterTypes(double.class);
// (String,int,double)String
```

`insertParameterTypes(pos, ...)` inserts **before** position `pos`, accepting `pos` from `0` to `parameterCount()` (including the end position); `appendParameterTypes(...)` appends to the end of the parameter list. Both reject the `void.class` parameter type.

### 5.4. Dropping a Range of Parameters

```java
MethodType dropped = base.dropParameterTypes(1, 2);
// (String)String
```

The range `[start, end)` has **start inclusive, end exclusive**: it drops the parameter at index 1 and keeps index 0. Do not mistake `dropParameterTypes(1,2)` for dropping two parameters; it drops exactly one parameter. With `start == end`, no parameters are dropped. Invalid indices/ranges throw `IndexOutOfBoundsException`.

### 5.5. Visual Comparison Table

| Transformation on `(String,int)String` | Resulting signature |
| --- | --- |
| `changeParameterType(1, long.class)` | `(String,long)String` |
| `changeReturnType(void.class)` | `(String,int)void` |
| `insertParameterTypes(1, boolean.class)` | `(String,boolean,int)String` |
| `appendParameterTypes(double.class)` | `(String,int,double)String` |
| `dropParameterTypes(1, 2)` | `(String)String` |

**Important warning:** the transformations above only create **signature descriptions**. They **do not** automatically change the actual implementation of a method from `int` to `long`, nor do they insert/drop arguments of an existing `MethodHandle`. When you need to change the actual signature of a handle, use contract-compliant adapters such as `asType`, `MethodHandles.dropArguments`, `insertArguments`, `filterArguments`, etc., depending on the specific case, and you must check whether the conversion is valid.

## 6. `erase()`, `generic()`, `wrap()`, and `unwrap()`

This is a group of transformations that are often misunderstood, especially when primitives and `void` are involved.

### 6.1. `erase()` — Replace References with Object, Keep Primitives

```java
MethodType t = MethodType.methodType(
        String.class, String.class, int.class);
System.out.println(t.erase()); // (Object,int)Object
```

`String` (reference) becomes `Object` in both parameters and return type. `int` (primitive) **remains unchanged**. If the return type is `void`, `erase` still returns `void`.

### 6.2. `generic()` — All Components Become Object

```java
System.out.println(t.generic()); // (Object,Object)Object
```

`generic` replaces **both primitives and references** with `Object`, keeping the same number of parameters. It is equivalent to the result of `t.wrap().erase()`. The name “generic” here describes a general `Object`-based signature; this is **not** a Java `<T>` generic type declaration. Therefore `erase()` and `generic()` are not equivalent if the signature contains primitives.

### 6.3. `wrap()` — Primitives to Wrappers

```java
System.out.println(t.wrap()); // (String,Integer)String
```

`int` becomes `Integer`, while references like `String` remain unchanged. Specifically, the **`void` return type** is replaced with `java.lang.Void`. `wrap()` does not create wrapper objects or perform an invocation; it only creates a signature description with wrapper types.

### 6.4. `unwrap()` — Wrappers to Primitives

```java
System.out.println(t.wrap().unwrap()); // (String,int)String
```

`Integer` becomes `int`. Specifically, the **`Void` return type** is replaced with `void`. For a parameter of type `Void.class`, `unwrap()` **keeps `Void.class`** because `void` is not allowed as a parameter type. Do not treat `unwrap()` as a conversion that can be safely applied automatically to every runtime value.

### 6.5. Flags for Checking Primitive and Wrapper Types

- `hasPrimitives()` indicates whether the signature has a primitive in its parameters or result. **The `void` return type is also counted as a primitive** when checking this flag.
- `hasWrappers()` indicates whether there is a wrapper type. **`Void.class` in the return position** is counted as a wrapper.
- These two flags describe signature components; they **do not** confirm that the target method can accept another type or that a conversion adapter already exists.

## 7. Accurately Distinguishing `void` and `java.lang.Void`

This is the core point of the lesson.

| Criterion | `void` / `void.class` | `java.lang.Void` / `Void.class` |
| --- | --- | --- |
| Nature | Java keyword representing **no return value**; `void.class` is the `Class` object representing that special type | A **reference class** in `java.lang`, used as a stand-in for `void` in contexts requiring a `Class` object |
| Can declare a value variable? | No: `void x` is not a valid declaration | Yes: `Void x = null;` is valid; `Void` has no useful instance to construct in the usual way |
| For `MethodType` return type | Valid: `methodType(void.class)` → `()void` | Valid: `methodType(Void.class)` → `()Void` |
| For `MethodType` parameter type | **Invalid**: `methodType(int.class, void.class)` throws `IllegalArgumentException` | **Structurally valid**: `methodType(int.class, Void.class)` → `(Void)int`, though rarely useful |
| JVM return descriptor | `V` | `Ljava/lang/Void;` |
| Calling a Java method | A `void` method returns no object | A method returning `Void` is a reference-returning method; normally `return null;` |
| `wrap()/unwrap()` on return type | `wrap` changes `void` to `Void` | `unwrap` changes `Void` to `void` |
| Comparing class literals | `void.class == Void.TYPE` is `true` | `Void.class != void.class` is `true` |

**Example of two different signatures:**

```java
MethodType noValue = MethodType.methodType(void.class, String.class);
MethodType nullableReference = MethodType.methodType(Void.class, String.class);

System.out.println(noValue);          // (String)void
System.out.println(nullableReference); // (String)Void
System.out.println(noValue.equals(nullableReference)); // false
```

The two signatures are **not the same**, even though many APIs use `Void` to represent “no useful result”. Java does not allow overloading two methods that differ only by return type at the source level; when defining two runnable examples, we use **two separate method names**.

### 7.1. Do Not Confuse `Void.TYPE` with `Void.class`

`Void.TYPE` is the `Class` object representing the primitive-like type `void`, equivalent to `void.class`. However, `Void.class` is the actual `java.lang.Void` class. Those two `Class` objects are different:

```java
boolean a = (Void.TYPE == void.class);   // true
boolean b = (Void.class == void.class);  // false
```

### 7.2. There Is No “Boxing Value” of `void`

For `int`, you can box the value `7` into `Integer.valueOf(7)`. However, `void` represents **no value**, so there is no “void value” to actually box into a `Void` object. `MethodType.wrap()` is a **signature** transformation, not an operation that creates a `Void` object. When an API has a generic result `Void`, code authors typically use `null` to represent completion without a payload.

This differs from `Optional<Void>`, `CompletableFuture<Void>`, or a callback with result type `Void`; those constructs conventionally represent successful completion with the value `null`, but `Void` itself does not turn into a real method's `void` return type.

### 7.3. `void` in Practical MethodHandle Usage

When finding a method with `findStatic`, `MethodType` must match the **actual return type of the method**:

```java
public static void ping(String text) { System.out.println(text); }
public static Void boxedPing(String text) {
    System.out.println(text);
    return null;
}
```

The snippet above is only **method declarations inside a class**, not a standalone Java program. To look up `ping`, use `methodType(void.class, String.class)`; to look up `boxedPing`, use `methodType(Void.class, String.class)`. Do not arbitrarily replace `void` with `Void` and assume lookup treats them the same.

## 8. Why Must You Understand MethodType When Using Lookup and MethodHandle?

Consider the call to find a static method:

```java
MethodType signature = MethodType.methodType(
        String.class, String.class, int.class);
MethodHandle handle = MethodHandles.lookup().findStatic(
        MethodTypeGuide.class, "repeat", signature);
```

This snippet needs to be placed in code that actually has a `MethodTypeGuide` class containing the method `public static String repeat(String, int)`; the complete example is in the next section.

In `findStatic`:
1. `Lookup` provides the access-checking context.
2. Class + method name + `MethodType` identify the method to find.
3. Lookup may fail with `NoSuchMethodException` or `IllegalAccessException` if the method does not exist, the signature does not match, or access is denied.
4. The resulting handle has `handle.type()`, describing the signature that the caller must satisfy.

`invokeExact` requires the signature right at the **call site** to match the handle's type exactly, including parameters and result type. When mismatched, it can throw `WrongMethodTypeException`. `invoke` and `asType` support certain adaptations/conversions according to API rules, but arbitrary transformations are not supported.

For example, calling `signature.changeParameterType(1, long.class)` creates a `(String,long)String` description, which **does not make** `repeat(String,int)` accept `long`. To get a handle supporting a different signature, you must verify the conversion and create an appropriate adapter handle (if possible). Do not just change the `MethodType` variable and call the old target.

## 9. Complete Java 17+ Program and Verified Output

Save the file **`MethodTypeGuide.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodTypeGuide {
    public static String repeat(String text, int count) {
        return text.repeat(count);
    }

    public static void ping(String text) {
        System.out.println("ping=" + text);
    }

    public static Void boxedPing(String text) {
        System.out.println("boxedPing=" + text);
        return null;
    }

    public static void main(String[] args) throws Throwable {
        MethodType base = MethodType.methodType(
                String.class, String.class, int.class);
        MethodType same = MethodType.methodType(
                String.class, new Class<?>[] { String.class, int.class });

        System.out.println("base=" + base);
        System.out.println("equals=" + base.equals(same));
        System.out.println("parameters=" + base.parameterCount());
        System.out.println("second=" + base.parameterType(1).getSimpleName());
        System.out.println("return=" + base.returnType().getSimpleName());
        System.out.println("parameterChanged="
                + base.changeParameterType(1, long.class));
        System.out.println("returnChanged="
                + base.changeReturnType(void.class));
        System.out.println("inserted="
                + base.insertParameterTypes(1, boolean.class));
        System.out.println("appended="
                + base.appendParameterTypes(double.class));
        System.out.println("dropped="
                + base.dropParameterTypes(1, 2));
        System.out.println("erased=" + base.erase());
        System.out.println("generic=" + base.generic());
        System.out.println("wrapped=" + base.wrap());
        System.out.println("unwrapped=" + base.wrap().unwrap());
        System.out.println("descriptor=" + base.toMethodDescriptorString());
        System.out.println("baseStill=" + base);

        MethodType noResult = MethodType.methodType(void.class, String.class);
        MethodType boxedResult = MethodType.methodType(Void.class, String.class);
        System.out.println("voidType=" + noResult);
        System.out.println("VoidType=" + boxedResult);
        System.out.println("voidDescriptor=" + noResult.toMethodDescriptorString());
        System.out.println("VoidDescriptor=" + boxedResult.toMethodDescriptorString());
        System.out.println("voidEqualsVoid=" + noResult.equals(boxedResult));
        System.out.println("wrapVoid=" + noResult.wrap());
        System.out.println("unwrapVoid=" + boxedResult.unwrap());
        System.out.println("voidIsPrimitive=" + noResult.hasPrimitives());
        System.out.println("VoidIsWrapper=" + boxedResult.hasWrappers());

        try {
            MethodType.methodType(int.class, void.class);
        } catch (IllegalArgumentException expected) {
            System.out.println("voidParameter=" + expected.getClass().getSimpleName());
        }

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle repeatHandle = lookup.findStatic(
                MethodTypeGuide.class, "repeat", base);
        String repeated = (String) repeatHandle.invokeExact("ha", 3);
        System.out.println("invokeExact=" + repeated);

        MethodHandle pingHandle = lookup.findStatic(
                MethodTypeGuide.class, "ping", noResult);
        pingHandle.invokeExact("ok");

        MethodHandle boxedPingHandle = lookup.findStatic(
                MethodTypeGuide.class, "boxedPing", boxedResult);
        Void answer = (Void) boxedPingHandle.invokeExact("ok");
        System.out.println("boxedValue=" + answer);
    }
}
```

Compile and run:

```bash
javac --release 17 MethodTypeGuide.java
java MethodTypeGuide
```

**Stdout:**

```text
base=(String,int)String
equals=true
parameters=2
second=int
return=String
parameterChanged=(String,long)String
returnChanged=(String,int)void
inserted=(String,boolean,int)String
appended=(String,int,double)String
dropped=(String)String
erased=(Object,int)Object
generic=(Object,Object)Object
wrapped=(String,Integer)String
unwrapped=(String,int)String
descriptor=(Ljava/lang/String;I)Ljava/lang/String;
baseStill=(String,int)String
voidType=(String)void
VoidType=(String)Void
voidDescriptor=(Ljava/lang/String;)V
VoidDescriptor=(Ljava/lang/String;)Ljava/lang/Void;
voidEqualsVoid=false
wrapVoid=(String)Void
unwrapVoid=(String)void
voidIsPrimitive=true
VoidIsWrapper=true
voidParameter=IllegalArgumentException
invokeExact=hahaha
ping=ok
boxedPing=ok
boxedValue=null
```

### Reading the Output

- `base` and `same` are created via two different `methodType` overloads yet are equal via `equals`.
- `parameterChanged`, `returnChanged`, `inserted`, `appended`, `dropped` verify parameter order and indices. `baseStill` proves that transformations do not mutate the original signature.
- `erased` keeps `int`; `generic` converts `int` to `Object`; `wrapped` converts `int` to `Integer`; `unwrapped` brings the wrapper back to the primitive type.
- The two descriptors `(Ljava/lang/String;)V` and `(Ljava/lang/String;)Ljava/lang/Void;` differ in **return type**. Therefore `voidEqualsVoid=false`.
- `voidIsPrimitive=true` and `VoidIsWrapper=true` match the specific rules of `hasPrimitives` and `hasWrappers`.
- `voidParameter=IllegalArgumentException` illustrates that `void.class` **cannot** be used as a parameter type.
- `repeatHandle.invokeExact("ha", 3)` matches `(String,int)String` and returns `hahaha`. `pingHandle` runs a method that returns no value, whereas `boxedPingHandle` returns a `Void` reference with the value `null`.

The program is written for Java 17+ (`String.repeat` has existed since Java 11). The `main throws Throwable` declaration keeps the example focused on the API; real applications should separately handle lookup/access errors, adaptation, and exceptions from the target.

## 10. API Design and Error Checking When Creating MethodType

### 10.1. Input Validation

| Configuration/programming error | Result or appropriate check |
| --- | --- |
| `rtype == null` | `methodType` throws `NullPointerException` |
| A parameter type is `null` | `NullPointerException` |
| A parameter type is `void.class` | `IllegalArgumentException` |
| Index outside the parameter list | `IndexOutOfBoundsException` |
| `insertParameterTypes` inserts past the last index | `IndexOutOfBoundsException` |
| Adding too many JVM parameters/slots | `IllegalArgumentException` |
| Malformed descriptor syntax | `IllegalArgumentException` from `fromMethodDescriptorString` |
| Class in descriptor cannot be resolved | May be `TypeNotPresentException` |
| `Lookup` uses a signature that does not match the real method | Usually `NoSuchMethodException` on lookup |
| `invokeExact` uses a call site type that does not match the handle | `WrongMethodTypeException` |

The JVM limits the number of **parameter slots** in a method descriptor; `long` and `double` occupy two slots. You should not dynamically build signatures containing hundreds of parameters from external data; validate the length and design an appropriate interface/DTO instead.

### 10.2. Separating Signature Construction from Execution

A dynamic invoker can go through these steps:

1. Read the method name and type tokens from **validated configuration**.
2. Normalize parameter order, ensuring there is no `null` or `void.class` in parameter positions; distinguish `void.class` from `Void.class` in the return position.
3. Create the `MethodType`, compare it against the expected contract using `equals`, and log the descriptor on error to avoid confusing overloads.
4. Resolve the handle via `Lookup`; verify `handle.type()` after finding it.
5. If adaptation is needed, create a new handle using adapter APIs and test the type conversion; do not merely swap out a standalone `MethodType`.
6. Invoke the handle with the exact signature and turn errors into contextual messages: class, method name, descriptor, argument types, and related configuration.

`MethodType` **does not carry class/method names or access permissions**. Therefore an `equals` check only tells you whether two signatures are the same; it does not prove that the method exists, that you have access permission, or that the target logic is correct.

## 11. Common Mistakes

1. **Putting parameters before the return type in `methodType`.** The first argument of the factory is the **return type**; subsequent arguments are the parameters in order.
2. **Using `==` to compare MethodType.** Factories may cache, but equality must use `equals`.
3. **Assuming `changeParameterType` changes the running method's parameter.** It only returns a different signature; the original handle and implementation do not change.
4. **Equating `erase` and `generic`.** `erase` keeps primitives; `generic` converts primitives to `Object` as well.
5. **Thinking `wrap()` creates wrapper objects.** It only changes the signature; `void` has no value to box.
6. **Equating `void.class` and `Void.class`.** They differ in class identity, descriptor, and call contract.
7. **Allowing a `void.class` parameter.** `void` cannot be a parameter type, whereas `Void.class` is a valid reference parameter type.
8. **Forgetting the receiver in an instance method's handle.** `findVirtual` takes the declared signature, while the returned handle has the receiver as its first parameter.
9. **Reading `toString` as a JVM descriptor.** `(String,int)String` is only a human-readable representation; the true descriptor is `(Ljava/lang/String;I)Ljava/lang/String;`.
10. **Using `MethodType` as proof that a method can be invoked.** You must still look up the right target, check permissions, and match types at the call site.

## 12. Practice Exercises

**Exercise 1 — Reading and Transforming:**

Given `MethodType t = MethodType.methodType(long.class, int.class, String.class);`. Predict `t`, `t.erase()`, `t.generic()`, `t.wrap()`, `t.dropParameterTypes(0,1)`.

**Answer:** `(int,String)long`, `(int,Object)long`, `(Object,Object)Object`, `(Integer,String)Long`, `(String)long`.

**Exercise 2 — void vs Void:**

Is `MethodType.methodType(void.class, int.class)` valid? What about `MethodType.methodType(int.class, void.class)`? What about `MethodType.methodType(int.class, Void.class)`?

**Answer:** Respectively **valid**, **invalid** (`IllegalArgumentException`), **valid** (`Void` reference parameter, though rarely useful).

**Exercise 3 — Bug Analysis:**

An actual method is `public static void log(String message)`. Code calling `findStatic(clazz, "log", MethodType.methodType(Void.class, String.class))` fails lookup. Why?

**Answer:** The return type must be `void.class`. `Void.class` describes a method returning a `Void` reference, which differs from the signature of a method returning `void`.

**Exercise 4 — Checking the Receiver:**

For `String.concat(String)`, `findVirtual(String.class, "concat", MethodType.methodType(String.class, String.class))` uses the declared signature with one `String` parameter. The resulting handle has the form `(String,String)String`; the first `String` is the receiver. Write `invokeExact` so that it returns the string `"Java17"` from receiver `"Java"` and argument `"17"`.

**Hint:** `(String) handle.invokeExact("Java", "17")`, where `handle` is the successfully looked-up `MethodHandle`.

## Official Documentation

- [Java SE 17 API — MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Java SE 17 API — MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 17 API — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 17 API — Void](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Void.html)

## Conclusion

`MethodType` is an **immutable type descriptor** of a call: the return type together with the ordered sequence of parameter types. Create it with factories, compare it via `equals`, transform it with APIs that return a different signature, and clearly distinguish operations **on signatures** from `MethodHandle` adaptation/execution. In every case where a “no return value” result is needed, remember that **`void.class` differs from `Void.class`**: `void` is a valueless return type, whereas `Void` is a reference type, and the two have different JVM signatures.
