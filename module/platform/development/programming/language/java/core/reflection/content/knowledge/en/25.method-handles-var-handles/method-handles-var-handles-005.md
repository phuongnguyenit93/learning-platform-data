# `MethodType` and Signature Checking in Java

## 1. What Does `MethodType` Describe?

In Java, `java.lang.invoke.MethodType` is an **immutable descriptor of a method type signature**: exactly one return type and an ordered list of parameter types. It belongs to the `java.lang.invoke` API group and is used when looking up and invoking `MethodHandle`s, adapting dynamic invocations, and querying the access signature of a `VarHandle`.

For example, the signature `String label(String name, int count)` is represented by:

```java
import java.lang.invoke.MethodType;

MethodType signature = MethodType.methodType(
        String.class, String.class, int.class);
System.out.println(signature); // (String,int)String
```

In the `methodType` call, **the first argument is the return type**; the next two arguments are the types of `name` and `count`, respectively. The signature `(String,int)String` reads as "accepts `String` and `int`, returns `String`". It does **not** include the method name `label`.

`MethodType` does not store the declaring class, method name, parameter names, modifiers (`public`/`static`), generic type arguments, annotations, or `throws` lists. For instance, `List<String>` and `List<Integer>` are both represented by `List.class` due to type erasure; `MethodType` cannot replace a `ParameterizedType`.

Comparing concepts:

| API | Primary Data | Purpose |
| --- | --- | --- |
| `MethodType` | Return type and runtime parameter types | Describe, match, create/modify type signatures |
| `MethodHandle` | An invocable operation, along with `type()` | Execute dynamic invocations |
| `java.lang.reflect.Method` | Named method, declaring class, modifiers, and metadata | Find and invoke methods via Core Reflection |
| `VarHandle` | Access to a variable/field/array element | `GET`, `SET`, CAS, and other access modes |

**Note:** `MethodType` only describes types; by itself it contains no executable code and has no invocation operation like `invokeExact`.

## 2. How to Create and Inspect a `MethodType`

Several overloads of the `MethodType.methodType(...)` factory:

```java
MethodType none = MethodType.methodType(void.class);
MethodType unary = MethodType.methodType(int.class, String.class);
MethodType binary = MethodType.methodType(
        String.class, String.class, int.class);
MethodType fromArray = MethodType.methodType(
        String.class, new Class<?>[] { String.class, int.class });
```

These are illustrative code snippets to be placed inside a class/method with `import java.lang.invoke.MethodType;`; a complete program appears in a later section.

Common query methods:

- `returnType()` returns a `Class<?>` describing the result type; `void.class` is permitted when there is no result.
- `parameterCount()` counts parameters; `parameterType(i)` accesses the `i`-th parameter, zero-indexed.
- `parameterArray()` and `parameterList()` list parameter types in order; mutating the returned array does not mutate the `MethodType`.
- `toString()` displays a human-readable form, such as `(String,int)String`.
- `toMethodDescriptorString()` converts to a JVM descriptor, such as `(Ljava/lang/String;I)Ljava/lang/String;` (`I` represents primitive `int`).
- `MethodType.fromMethodDescriptorString(descriptor, loader)` parses a JVM descriptor using the supplied class loader to resolve reference types.

**Return type `void` is valid, parameter type `void` is invalid.** `MethodType.methodType(String.class, void.class)` throws `IllegalArgumentException`. If the return type or a parameter type is passed as `null`, the API throws `NullPointerException`. For `parameterType(i)`, an out-of-range index throws `IndexOutOfBoundsException`.

Primitive types and wrapper types are **two distinct types**: `int.class` differs from `Integer.class`. Array types are distinct types: `String[].class` differs from `String.class`. `MethodType` considers the actual `Class` objects, including class loaders, not just class-name strings.

## 3. Exact Comparison and Transforming Signatures

`MethodType` is immutable. Adjustment methods return another `MethodType` (or may reuse the current instance if contents are unchanged) without modifying the original object:

| Method | Effect |
| --- | --- |
| `changeReturnType(Class<?>)` | Replaces the return type |
| `changeParameterType(index, Class<?>)` | Replaces the type of one parameter |
| `insertParameterTypes(index, Class<?>...)` | Inserts parameters at a given position |
| `appendParameterTypes(Class<?>...)` | Appends parameters |
| `dropParameterTypes(start, end)` | Drops the parameter slice from `start` up to before `end` |
| `wrap()` / `unwrap()` | Converts primitives to wrappers or vice versa in the descriptor |
| `equals(Object)` | Checks that the return type and each parameter type match exactly |

Example:

```java
MethodType oldType = MethodType.methodType(
        String.class, String.class, int.class);
MethodType newType = oldType.changeReturnType(Object.class)
        .insertParameterTypes(1, long.class);

// oldType: (String,int)String
// newType: (String,long,int)Object
```

Use `equals` to compare signatures by content; **do not use `==` in place of equivalence checks**. Types, positions, and parameter count all matter. Changing only `int` to `Integer` or changing the return type makes two `MethodType`s unequal.

Transforming a `MethodType` **does not automatically transform the behavior or type of an existing `MethodHandle`**. To produce a handle with a new type and the corresponding adapter, use `handle.asType(newType)` when the conversion is permitted.

## 4. `MethodHandle` Type, Receiver, and `invokeExact`

`MethodHandle.type()` returns the `MethodType` that the handle expects at invocation. For a `static` method looked up with `Lookup.findStatic`, the handle type normally matches the method type described at lookup.

With `Lookup.findVirtual`, there are two signature levels to distinguish:

```java
// Declared signature of String.substring(int, int):
MethodType declared = MethodType.methodType(
        String.class, int.class, int.class);
MethodHandle handle = MethodHandles.lookup()
        .findVirtual(String.class, "substring", declared);

// handle.type(): (String,int,int)String
//              ^ String receiver is placed first
```

The example above requires importing `MethodHandle`, `MethodHandles`, `MethodType` and placing it in a method that handles checked exceptions. `findVirtual` takes the declared type without a receiver. However, when **invoking the handle**, the receiver becomes the first parameter. `bindTo(receiver)` can pre-bind a receiver on an eligible handle and reduce the parameter count of the resulting handle.

`MethodHandle.invokeExact(...)` requires the signature at the **call site** to match `handle.type()` exactly: parameter count, order, parameter types, **and return type**. The compiler determines the call site's return type from the expression context. For example:

```java
// handle.type() is (String,int,int)String:
String yes = (String) handle.invokeExact("abcdef", 1, 3);
// Object no = (Object) handle.invokeExact("abcdef", 1, 3);
// The second line may compile, yet throws WrongMethodTypeException.
```

The latter case requests **Object** at the call site, whereas the handle returns **String**. Even though `String` is a subtype of `Object`, `invokeExact` does not accept that conversion. When a call stands alone as a statement and its value is discarded, the call site has return type `void`; that can also fail to match.

`MethodHandle.invoke(...)` is more flexible: if the signatures differ, the JVM can perform conversions equivalent to `asType` (such as reference casts and boxing/unboxing within the supported range). `invokeExact` skips this adaptation step. When adaptation is not possible, `WrongMethodTypeException` may be thrown; a specific cast failure can cause `ClassCastException`.

## 5. Standalone Java 17+ Example: Comparing Signatures, Error Checking, and Adaptation

Save as `MethodTypeSignatureDemo.java`:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodTypeSignatureDemo {
    public static String label(String name, int index) {
        return name + "-" + index;
    }

    static void requireType(MethodHandle handle, MethodType expected) {
        if (!handle.type().equals(expected)) {
            throw new IllegalArgumentException(
                    "Expected " + expected + " but found " + handle.type());
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodType signature = MethodType.methodType(
                String.class, String.class, int.class);

        System.out.println("type=" + signature);
        System.out.println("descriptor=" +
                signature.toMethodDescriptorString());
        System.out.println("count=" + signature.parameterCount());
        System.out.println("param0=" +
                signature.parameterType(0).getSimpleName());
        System.out.println("return=" +
                signature.returnType().getSimpleName());

        MethodType changed = signature.changeReturnType(Object.class);
        MethodType inserted = signature.insertParameterTypes(1, long.class);
        System.out.println("changed=" + changed);
        System.out.println("inserted=" + inserted);
        System.out.println("original=" + signature);

        MethodType decoded = MethodType.fromMethodDescriptorString(
                signature.toMethodDescriptorString(),
                MethodTypeSignatureDemo.class.getClassLoader());
        System.out.println("roundtrip=" + decoded.equals(signature));

        MethodHandle handle = MethodHandles.lookup().findStatic(
                MethodTypeSignatureDemo.class, "label", signature);
        System.out.println("handle=" + handle.type());
        requireType(handle, signature);
        System.out.println("checked=true");

        String exact = (String) handle.invokeExact("id", 7);
        System.out.println("exact=" + exact);

        try {
            Object ignored = (Object) handle.invokeExact("id", 7);
            System.out.println("unexpected=" + ignored);
        } catch (WrongMethodTypeException e) {
            System.out.println("wrongReturn=WrongMethodTypeException");
        }

        try {
            requireType(handle, signature.changeReturnType(Object.class));
        } catch (IllegalArgumentException e) {
            System.out.println("precheck=rejected");
        }

        MethodType adaptedType = MethodType.methodType(
                Object.class, Object.class, Integer.class);
        MethodHandle adapted = handle.asType(adaptedType);
        Object boxed = (Object) adapted.invokeExact(
                (Object) "box", Integer.valueOf(5));
        System.out.println("adaptedType=" + adapted.type());
        System.out.println("adaptedResult=" + boxed);

        MethodHandle substring = MethodHandles.lookup().findVirtual(
                String.class, "substring",
                MethodType.methodType(String.class, int.class, int.class));
        System.out.println("virtualType=" + substring.type());
        String part = (String) substring.invokeExact("methodtype", 0, 6);
        System.out.println("substring=" + part);
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 MethodTypeSignatureDemo.java
java MethodTypeSignatureDemo
```

Exact stdout:

```text
type=(String,int)String
descriptor=(Ljava/lang/String;I)Ljava/lang/String;
count=2
param0=String
return=String
changed=(String,int)Object
inserted=(String,long,int)String
original=(String,int)String
roundtrip=true
handle=(String,int)String
checked=true
exact=id-7
wrongReturn=WrongMethodTypeException
precheck=rejected
adaptedType=(Object,Integer)Object
adaptedResult=box-5
virtualType=(String,int,int)String
substring=method
```

Explanation of key points:

1. `changeReturnType` and `insertParameterTypes` leave the original `signature` intact; `roundtrip=true` proves the descriptor decodes back into an equivalent signature.
2. `handle.type()` from `findStatic` matches the `(String,int)String` signature used for lookup. `requireType` checks beforehand to catch miswired contracts.
3. `String exact = (String) handle.invokeExact(...)` succeeds. Casting the result to `Object` changes the call site's return type, throwing `WrongMethodTypeException`.
4. `asType` creates an adapter with type `(Object,Integer)Object`, casts the `Object` holding a string to `String`, unboxes `Integer` to `int`, and widens the `String` result to `Object`. The adapter does not modify the original handle.
5. `findVirtual` requires the `String` receiver first. Calling `substring("methodtype", 0, 6)` returns `method`.

`requireType` is an explicit contract check; the JVM still enforces its own check when encountering an `invokeExact` call.

## 6. Relation to `VarHandle`: Signatures Depend on Access Mode

`VarHandle` does not have a single signature for every operation. `GET` reads a value, `SET` writes a value and takes an additional new-value argument, and `COMPARE_AND_SET` has its own contract. You can inspect:

- `vh.accessModeType(VarHandle.AccessMode.GET)` — the call-site type of `GET`.
- `vh.accessModeType(VarHandle.AccessMode.SET)` — the call-site type of `SET`.
- `vh.toMethodHandle(mode).type()` — the type of a MethodHandle representing the access mode.
- `vh.isAccessModeSupported(mode)` — determines whether the access mode is supported by that VarHandle instance.

For an `int[]` element, the coordinates consist of **the array** and **the index**. Save a standalone example as `VarHandleSignatureDemo.java`:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;

public class VarHandleSignatureDemo {
    public static void main(String[] args) {
        VarHandle vh = MethodHandles.arrayElementVarHandle(int[].class);
        MethodType getType = vh.accessModeType(VarHandle.AccessMode.GET);
        MethodType setType = vh.accessModeType(VarHandle.AccessMode.SET);
        MethodHandle getHandle = vh.toMethodHandle(VarHandle.AccessMode.GET);

        System.out.println("get=" + getType);
        System.out.println("set=" + setType);
        System.out.println("methodHandle=" + getHandle.type());
        System.out.println("getMatches=" + getHandle.type().equals(getType));

        int[] values = { 10, 20 };
        int value = (int) vh.get(values, 1);
        vh.set(values, 1, 42);
        System.out.println("before=" + value);
        System.out.println("after=" + values[1]);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 VarHandleSignatureDemo.java
java VarHandleSignatureDemo
```

Stdout:

```text
get=(int[],int)int
set=(int[],int,int)void
methodHandle=(int[],int)int
getMatches=true
before=20
after=42
```

`GET` has type `(int[],int)int`; `SET` has type `(int[],int,int)void` because it takes the new value as an extra argument. Access-mode calls on `VarHandle` also have signature-polymorphic semantics; checking `accessModeType` prevents mixing up coordinate count/types, the value to write, and the result type.

## 7. How to Check Signatures When Integrating Dynamic Code

In runtime call-mapping systems, plugins, adapters, or MethodHandle-generating libraries, you should:

1. Construct `MethodType expected` based on the contract of the target operation. Specify the **return type** explicitly, not just parameters.
2. Read the actual type via `handle.type()`. For instance methods, account for the receiver; for VarHandle, choose `accessModeType` for the exact mode.
3. If an exact match is required, use `expected.equals(actual)` and emit an informative error on mismatch.
4. If conversions are intentionally allowed, create an adapter via `handle.asType(expected)` and verify cast/unboxing logic; the adapter can fail immediately or at invocation time depending on the conversion.
5. When reading descriptors from bytecode or configuration, use the appropriate class loader. A matching signature **does not guarantee** the target method exists or is accessible: `Lookup.findStatic`/`findVirtual` still perform access checks and can throw `NoSuchMethodException` or `IllegalAccessException`.

For APIs where the target type is known at compile time, prefer normal Java calls; `MethodType` is useful when signatures genuinely need to be described and processed at runtime.

## 8. Common Mistakes

| Mistake | Symptom and How to Avoid |
| --- | --- |
| Misreading the first parameter of `methodType` | It is the **return type**, followed by parameter types |
| Passing `void.class` as a parameter | `IllegalArgumentException`; `void` is only valid as a return type |
| Using `==` to compare signature contents | Use `equals` |
| Confusing `int.class` and `Integer.class` | Different signatures; `invokeExact` does not auto-box |
| Omitting the receiver for `findVirtual` | `handle.type()` prepends the receiver in the first slot |
| Ignoring return type at `invokeExact` | The call site can fail even when every argument looks right |
| Thinking `asType` mutates the original handle | It returns an adapter with a new type |
| Using `toString()` as a JVM descriptor | Use `toMethodDescriptorString()` |
| Thinking `MethodType` stores generics/`throws`/method name | It only describes runtime parameter and return types |
| Using `VarHandle`'s `get` signature for `set` | Check `accessModeType(mode)` for each mode |
| Mixing types from different class loaders | `Class` identity depends on its loader; decode descriptors with the right loader |

`invokeExact` and `invoke` declare `throws Throwable`; the examples use `main throws Throwable` so the code runs standalone. `WrongMethodTypeException` usually indicates a type-contract mismatch at the call site, whereas `ClassCastException` can be a value-conversion error when using an adapter.

## 9. Self-Check

**1.** Is `MethodType.methodType(void.class, String.class)` valid? — **Yes**: accepts `String` and returns `void`. Conversely, `methodType(String.class, void.class)` is invalid.

**2.** What `handle.type()` does `findVirtual(String.class, "substring", methodType(String.class, int.class, int.class))` produce? — **`(String,int,int)String`**, because of the `String` receiver.

**3.** A handle has type `(String,int)String`; is casting the `invokeExact` result to `Object` valid? — **No**: the call site expects return type `Object`, which does not match `String`.

**4.** Why does `VarHandle` need `accessModeType` instead of using a single `MethodType`? — Because modes differ in parameter count and return type.

**Remember:** `MethodType` is an immutable type contract. When checking dynamic invocations, verify the full **return type + ordered parameter list + receiver**; use `handle.type()` and `VarHandle.accessModeType(mode)` to confirm before executing.

References: [Java 17 `MethodType` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html), [Java 17 `MethodHandle` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html), [Java 17 `VarHandle` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html).