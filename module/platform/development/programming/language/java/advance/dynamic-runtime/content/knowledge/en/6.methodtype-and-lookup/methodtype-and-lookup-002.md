# 6.2 Describing Parameters, Return Type, and Receiver with `MethodType`

In Java, `java.lang.invoke.MethodType` describes the **ordered list of parameter types** and the **return type** of a method or dynamic call. It is a foundational component of `MethodHandle`, `MethodHandles.Lookup`, and `invokedynamic` call linking. The easiest point to confuse: **the declared signature of an instance method does not have a `this` parameter, but a `MethodHandle` calling an instance method usually has the `receiver` as the first parameter**.

This lesson explains how to create, read, and transform `MethodType`, how the receiver appears when looking up a method, the differences between static/instance/constructor, and why `invokeExact` requires a signature matching down to every single type.

> **Environment:** Standalone examples use Java **17+** (the `java.lang.invoke` API has existed since earlier versions). Compile with `javac --release 17` or `javac` from JDK 17+. The complete programs below have had their outputs verified by actual compilation and execution.

## 1. Learning Objectives

After this lesson, you can:

- Create a `MethodType` from a Java return type and parameter types and accurately explain the order of arguments in `methodType(...)`.
- Read `returnType()`, `parameterCount()`, `parameterType(index)`, `parameterArray()`, `parameterList()`, and convert to a JVM method descriptor.
- Distinguish the **signature of the declared method** from the **invocation signature of the MethodHandle** after `findStatic`, `findVirtual`, `findConstructor`, and `bindTo`.
- Understand what a receiver is, why it is present at the beginning of the handle's parameter list when calling an instance method, and in which cases there is no receiver.
- Use `changeParameterType`, `changeReturnType`, `insertParameterTypes`, `appendParameterTypes`, `dropParameterTypes` to create a new signature without confusing it with modifying executable code.
- Analyze `WrongMethodTypeException` errors, and distinguish `invokeExact`, `invoke`, and `asType`.

## 2. What Does `MethodType` Actually Represent?

`MethodType` is an **immutable** value consisting of:

```text
MethodType = (parameterType[0], parameterType[1], ..., parameterType[n-1])
             -> returnType

Example:
             (String, int) -> boolean
MethodType:  (String,int)boolean
Descriptor:  (Ljava/lang/String;I)Z
```

Each type component is represented by a `Class<?>` object, such as `String.class`, `int.class`, `long.class`, `String[].class`, or `void.class`. **The return type is passed first**, followed by the parameter types:

```java
MethodType type = MethodType.methodType(
        boolean.class, String.class, int.class);
```

This is an **illustrative snippet**, with `import java.lang.invoke.MethodType`. The result describes a method taking `(String, int)` and returning `boolean`. There is no method name in this object.

### 2.1. What `MethodType` Does Not Contain

A `MethodType` does not store:

- Method name (for example `parse` or `send`), or the class or interface declaring the method.
- Modifiers such as `public`, `static`, `private`, or `synchronized`; it does not imply access permissions.
- Parameter names such as `username`, `count`, or default values.
- Generic type arguments, for example `List<String>` differs from `List<Integer>` at compile time, but both use `List.class` in the runtime method descriptor.
- Annotations, checked exceptions, or bytecode body.
- A special label saying the first parameter is a receiver. The receiver is only **inferred from the kind of handle or how the handle was constructed**; a `MethodType` by itself only knows positional types.

Two methods with different names but the same parameter types and return type can share an equivalent `MethodType`. Conversely, differing in just one parameter type, order, or return type results in a different `MethodType` signature.

### 2.2. Immutable, Equal by Content, Potentially Cached

`MethodType` does not allow directly modifying a created type list. Operations like `change...`, `insert...`, `drop...` create or return a new `MethodType` in value semantics; the original object does not change.

`equals(...)` compares each parameter type and the return type in exact positional order. You should not use `==` as an identity rule because the factory **may cache**, but the API does not guarantee that two creations of the same type always return the exact same object.

Example:

```java
MethodType a = MethodType.methodType(int.class, String.class);
MethodType b = MethodType.methodType(int.class, String.class);
boolean same = a.equals(b); // true
```

This is a non-standalone fragment; the result comment is based on the API's comparison rules. Using `Class<?>` is also tied to class loader identity: two classes with the same binary name but defined by different loaders are still two different runtime types, leading to two `MethodType` instances possibly being **not equal** even though their descriptor strings are identical.

## 3. Creating a Signature: Return Type First, Parameters in Order

Basic import:

```java
import java.lang.invoke.MethodType;
```

Patterns:

| Declaration/method to describe | How to create `MethodType` | Readable form |
| --- | --- | --- |
| `void reset()` | `methodType(void.class)` | `()void` |
| `int size()` | `methodType(int.class)` | `()int` |
| `String name(int id)` | `methodType(String.class, int.class)` | `(int)String` |
| `boolean verify(String token, int retries)` | `methodType(boolean.class, String.class, int.class)` | `(String,int)boolean` |
| `long sum(long a, long b)` | `methodType(long.class, long.class, long.class)` | `(long,long)long` |
| `String[] split(String regex)` | `methodType(String[].class, String.class)` | `(String)String[]` |
| `void print(String... values)` | `methodType(void.class, String[].class)` | `(String[])void` |

Every `methodType` call in the table can be written as `MethodType.methodType(...)`; the table shortens the class name for readability.

**Important notes:**

1. `void.class` is only valid for the **return type**, to indicate a method that returns no value; it cannot be used as a parameter type.
2. Parameters can be primitive, array, or reference types; `int.class` is **not** `Integer.class`, and `String.class` is **not** `Object.class`.
3. `String...` in source code becomes a `String[]` parameter in the method descriptor. The `varargs` flag of a method belongs to separate metadata; `MethodType` only represents the array type.
4. `MethodType.methodType(Object.class, Object.class, Object.class)` differs from `MethodType.genericMethodType(2)` in how it is created, though they can be equivalent in type; `genericMethodType(2)` uses `Object` for two parameters and the return type.
5. The number of **parameter slots** is limited in the JVM. A `long` or `double` consumes two slots, while other types normally take one slot. `parameterCount()` is the **number of parameter types**, not the number of slots; creating a `MethodType` exceeding the limit may throw `IllegalArgumentException`.

## 4. Reading a `MethodType`

Commonly used methods:

| API | Return / meaning |
| --- | --- |
| `returnType()` | `Class<?>` of the result; can be `void.class` |
| `parameterCount()` | Number of parameters as an `int` |
| `parameterType(index)` | Parameter type at **0-based** index |
| `parameterArray()` | `Class<?>[]` array containing the types in order |
| `parameterList()` | `List<Class<?>>` containing the types in order |
| `toString()` | Short form using simple class names, e.g. `(String,long)int` |
| `toMethodDescriptorString()` | JVM method descriptor in class file syntax, e.g. `(Ljava/lang/String;J)I` |
| `descriptorString()` | Equivalent API to get the descriptor, available since modern JDKs |
| `equals(Object)` | Compares the entire sequence of parameter types and result type |

When wanting to display "what is the first parameter?", remember that the parameter order of `MethodType` is the **input order of the call that the object is describing**. For a MethodType used to find an instance method, these are the declared parameters; for `handle.type()`, these are all parameters of the **handle**, which may include the receiver at position 0.

### 4.1. A JVM Method Descriptor Is Not a Method Name

Common notations:

| Java type | JVM descriptor |
| --- | --- |
| `void` (return only) | `V` |
| `int` | `I` |
| `long` | `J` |
| `boolean` | `Z` |
| `double` | `D` |
| `String` | `Ljava/lang/String;` |
| `Object` | `Ljava/lang/Object;` |
| `int[]` | `[I` |
| `String[][]` | `[[Ljava/lang/String;` |

For example, `(Ljava/lang/String;J)I` means "take `String` then `long`; return `int`". The parameters are **inside** the parentheses; the return type is **after** the parentheses. That string does not include the method name, owner class, or `static` flag.

`MethodType.fromMethodDescriptorString(descriptor, loader)` parses a descriptor back into a `MethodType`. For reference class names, `loader` determines which runtime type is resolved. A valid descriptor whose class cannot be found may result in `TypeNotPresentException`; invalid descriptor syntax results in `IllegalArgumentException`. Do not treat descriptor parsing as a method invocation or a request to initialize the described classes.

**Note on round-trip:** `toMethodDescriptorString()` and `fromMethodDescriptorString(...)` match well when classes are all visible through the same loader. They are **not absolute inverses** in every multi-loader environment or with `Class<?>` kinds that cannot be nominally described.

## 5. Practice 1: Creating, Reading, and Transforming `MethodType`

Create the file **`MethodTypeIntrospectionDemo.java`**:

```java
import java.lang.invoke.MethodType;

public class MethodTypeIntrospectionDemo {
    public static void main(String[] args) {
        MethodType signature = MethodType.methodType(
                int.class, String.class, long.class);
        System.out.println("type: " + signature);
        System.out.println("return: " + signature.returnType().getSimpleName());
        System.out.println("arity: " + signature.parameterCount());
        System.out.println("parameters: "
                + signature.parameterList().stream()
                        .map(Class::getSimpleName).toList());
        System.out.println("descriptor: "
                + signature.toMethodDescriptorString());

        MethodType decoded = MethodType.fromMethodDescriptorString(
                "(Ljava/lang/String;J)I",
                MethodTypeIntrospectionDemo.class.getClassLoader());
        System.out.println("descriptor round-trip: " + signature.equals(decoded));

        MethodType changed = signature
                .changeParameterType(0, Object.class)
                .changeReturnType(long.class);
        System.out.println("changed: " + changed.toMethodDescriptorString());
        System.out.println("appended: "
                + signature.appendParameterTypes(boolean.class)
                        .toMethodDescriptorString());
        System.out.println("insert/drop round-trip: "
                + signature.insertParameterTypes(
                        0, MethodTypeIntrospectionDemo.class)
                        .dropParameterTypes(0, 1).equals(signature));
        System.out.println("erased: " + signature.erase().toMethodDescriptorString());
        System.out.println("wrapped: "
                + MethodType.methodType(int.class, boolean.class)
                        .wrap().toMethodDescriptorString());
        try {
            MethodType.methodType(int.class, void.class);
        } catch (IllegalArgumentException exception) {
            System.out.println("void parameter: rejected");
        }
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 MethodTypeIntrospectionDemo.java
java MethodTypeIntrospectionDemo
```

**Stdout:**

```text
type: (String,long)int
return: int
arity: 2
parameters: [String, long]
descriptor: (Ljava/lang/String;J)I
descriptor round-trip: true
changed: (Ljava/lang/Object;J)J
appended: (Ljava/lang/String;JZ)I
insert/drop round-trip: true
erased: (Ljava/lang/Object;J)I
wrapped: (Ljava/lang/Boolean;)Ljava/lang/Integer;
void parameter: rejected
```

Explanation:

1. `signature` takes `String, long` and returns `int`. `parameterCount() == 2` even though `long` uses two JVM local-variable/argument slots at the bytecode level.
2. The string `(Ljava/lang/String;J)I` contains **enough type information** to reconstruct the MethodType when given an appropriate loader.
3. `changeParameterType(0, Object.class)` changes the **first parameter** from `String` to `Object`; `changeReturnType(long.class)` changes the result type. The old `signature` is unchanged.
4. `appendParameterTypes(boolean.class)` adds a parameter at the **end**; `insertParameterTypes(0, ...)` adds at the **beginning**, and `dropParameterTypes(0, 1)` removes the half-open range `[0, 1)`.
5. `erase()` replaces reference types with `Object` while keeping primitive types `long` and `int`. `wrap()` converts primitives `boolean`, `int` into `Boolean`, `Integer`.
6. Java rejects `void.class` in a parameter position; `void.class` is valid in the return position.

These are changes to **type descriptor objects**, not operations on an actual method, not method lookups, and not changes to how the program calls a method.

## 6. Receiver: The Difference Between Declared Method and Method Handle

Consider the Java source:

```java
class Service {
    String repeat(String text, int times) {
        return text.repeat(times);
    }
}
```

This is an **illustrative fragment**, without `main`. The method declared in source takes **two explicit parameters** `String` and `int`, and returns `String`. Therefore, the member signature, or JVM method descriptor of the method, is:

```text
(String,int)String
(Ljava/lang/String;I)Ljava/lang/String;
```

However, to actually invoke an instance method, the JVM must know the **target object**: `this`/receiver. A method handle created by `Lookup.findVirtual(Service.class, "repeat", ...)` typically has the form:

```text
MethodType used as findVirtual argument:
    (String, int)String
    [NO receiver]

MethodType from handle.type() after findVirtual:
    (Service, String, int)String
     ^^^^^^^
     receiver at parameterType(0)

Calling the handle:
    handle.invokeExact(serviceObject, "ha", 3)
                        ^^^^^^^^^^^^^
                        receiver
```

This is a **fundamental difference**:

- **MethodType of a declared method:** consists only of the parameters in the declaration and the return type. `this` does not appear in the JVM method descriptor of an instance method.
- **MethodType of a handle calling an instance method:** the receiver is modeled as the first parameter. A `MethodHandle.invokeExact` call passes the receiver before the declared parameters.
- **Do not include the receiver in the `MethodType` argument passed to `findVirtual`**. `Lookup` itself prepends the receiver to the resulting handle.
- The receiver has a reference type of the class/interface required by the handle, typically the `refc` passed to `findVirtual` (cases with protected access and certain lookup forms may have a stricter receiver type).
- The receiver is **not a parameter name** and is not specially marked inside `MethodType`. Its role as receiver only has meaning based on the origin of the handle/operation.

### 6.1. Static Methods Have No Receiver

For `static long sum(long a, long b)`, `Lookup.findStatic` is called with `methodType(long.class, long.class, long.class)`. The resulting handle normally takes exactly `(long, long)` and returns `long`. No `Service.class` argument is added just because the method resides in class `Service`.

### 6.2. Binding a Receiver to a Handle

`MethodHandle.bindTo(serviceObject)` binds a receiver reference to the first parameter position of a compatible handle and returns a new handle:

```text
Before bindTo: (Service, String, int)String
After  bindTo: (String, int)String

The receiver is fixed, so the caller does not pass it again.
```

Calling `bindTo` **does not modify the method definition** or turn the method into `static`. It creates another callable whose target object is pre-supplied. `bindTo` applies to a first parameter of reference type; to bind a primitive argument or at another position, combinators such as `MethodHandles.insertArguments` can be used according to their contract.

### 6.3. `findSpecial` and `unreflect`

`Lookup.findSpecial(...)` also produces a handle with a receiver, but the invocation mechanism is `invokespecial` style with its own access and dispatch rules. Do not treat it as `findVirtual` with a different method name. `Lookup.unreflect(Method)` can obtain a handle from Reflection metadata: for an instance method, the handle type also includes the receiver; for a static method, it does not.

In practice, the surest way to check after a lookup/adapter operation is to read **`handle.type()`**, rather than inferring completely from the method name string.

## 7. Practice 2: Observing the Receiver with `findVirtual` and `bindTo`

Create the file **`MethodTypeReceiverDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class MethodTypeReceiverDemo {
    static class Handler {
        String echo(String text, int times) {
            return text.repeat(times);
        }

        static long add(long left, long right) {
            return left + right;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType declared = MethodType.methodType(
                String.class, String.class, int.class);
        MethodHandle virtual = lookup.findVirtual(
                Handler.class, "echo", declared);

        System.out.println("declared parameter count: " + declared.parameterCount());
        System.out.println("virtual parameter count: " + virtual.type().parameterCount());
        System.out.println("receiver: " + virtual.type().parameterType(0).getSimpleName());
        System.out.println("receiver prefixed: "
                + virtual.type().equals(
                        declared.insertParameterTypes(0, Handler.class)));
        System.out.println("virtual result: "
                + (String) virtual.invokeExact(new Handler(), "ha", 3));

        MethodHandle bound = virtual.bindTo(new Handler());
        System.out.println("bound matches declaration: " + bound.type().equals(declared));
        System.out.println("bound result: " + (String) bound.invokeExact("go", 2));

        MethodHandle staticHandle = lookup.findStatic(
                Handler.class, "add",
                MethodType.methodType(long.class, long.class, long.class));
        System.out.println("static parameter count: "
                + staticHandle.type().parameterCount());
        System.out.println("static result: "
                + (long) staticHandle.invokeExact(4L, 6L));
    }
}
```

```bash
javac --release 17 MethodTypeReceiverDemo.java
java MethodTypeReceiverDemo
```

**Stdout:**

```text
declared parameter count: 2
virtual parameter count: 3
receiver: Handler
receiver prefixed: true
virtual result: hahaha
bound matches declaration: true
bound result: gogo
static parameter count: 2
static result: 10
```

How to read the output:

1. `declared` describes `Handler.echo(String,int): String` with **2** declared parameters. `Lookup.findVirtual` automatically prepends `Handler`, so `virtual.type()` has **3** parameters.
2. Comparing `virtual.type()` with `declared.insertParameterTypes(0, Handler.class)` yields `true`. This is a **signature-form verification**, not an instruction that we must manually add the receiver to `findVirtual`.
3. Calling `virtual.invokeExact(new Handler(), "ha", 3)` passes `Handler` first; `String.repeat(3)` produces `hahaha`.
4. `bindTo(new Handler())` binds the receiver, making the new handle have the exact form `(String,int)String`.
5. `findStatic` for the `add` method has no receiver; the handle's 2 parameters are exactly the 2 declared parameters.

**Remember:** A handle's `MethodType` describes how to **invoke the handle**, not how the Java compiler writes the source signature. This is a common cause of parameter-count confusion when debugging dynamic invocation.

## 8. Constructor: Lookup Takes `void`, Handle Returns the Object

For a Java constructor:

```java
class Box {
    Box(String value) { /* ... */ }
}
```

This is an illustrative fragment. A constructor in the JVM is represented as an `<init>` method returning `void`, so when looking it up with `Lookup.findConstructor(Box.class, type)`, the `type` argument must have **return type = `void.class`**:

```java
MethodType constructorType = MethodType.methodType(
        void.class, String.class);
MethodHandle constructor = MethodHandles.lookup()
        .findConstructor(Box.class, constructorType);
```

This is a fragment assuming `Box` exists and the caller has lookup access.

After a successful lookup, `constructor.type()` instead **returns `Box.class`** rather than `void.class`: this handle creates an object and returns the new object. The form is as follows:

```text
Constructor in class file: (String)void
MethodType passed to lookup: (String)void
MethodType of the handle:    (String)Box
```

There is no input receiver object because the object is created **during the constructor invocation**. Do not apply the rule "every instance member prepends a receiver" to a constructor handle.

## 9. `MethodType` Is the Type Contract of a `MethodHandle` Call

A `MethodHandle` holds a `MethodType` queried via `handle.type()`. However, **having a valid MethodType** does not mean an actual method exists or that calling it is permitted; `Lookup` must resolve the name/owner and check access permissions.

Important invocation approaches:

| API | How types are matched |
| --- | --- |
| `handle.invokeExact(...)` | Each argument type **and the return type requested by the call context** must match `handle.type()` exactly. |
| `handle.invoke(...)` | May perform compatible conversions via an `asType`-equivalent mechanism before invoking, within the limits allowed by the API. |
| `handle.asType(newType)` | Creates an **adapter handle** with `newType`, if the parameter/result conversions are valid. The original `handle` retains its old type. |
| `handle.invokeWithArguments(...)` | Flexible invocation via `Object`/list, convenient for tooling but incurs conversions/overhead and lacks the same static constraints as `invokeExact`. |

### 9.1. The Return Type Is Also Part of `invokeExact`

A subtle mistake:

```java
// Illustrative example: assume twiceHandle.type() is (long)long
long ok = (long) twiceHandle.invokeExact(7L);
Object wrong = twiceHandle.invokeExact(7L); // WrongMethodTypeException
```

`invokeExact` is **signature-polymorphic**: the compiler determines the call-site descriptor from the static types of the arguments and the **expected return type at the call site**. In the first statement, the requested result type is `long`. The second statement requests an `Object` result, which does not match `long`, even though Java normally allows boxing a primitive to `Object` in many other contexts.

Use the result explicitly, for example `(long) handle.invokeExact(7L)`, and check `handle.type()`. For a handle returning `void`, a call in a `void` context must be compatible.

### 9.2. `invoke` and `asType` Convert, But Not Arbitrarily

For an actual `(long)long` handle:

- `(long) handle.invokeExact(7L)`: exact match.
- `(long) handle.invoke(7)`: the call site has an `int` argument; `invoke` can use a compatible **`int -> long` widening** conversion.
- `MethodHandle changed = handle.asType(MethodType.methodType(long.class, int.class))`: the adapter accepts `int`, converts it to `long`, and calls the target; `changed.type()` is `(int)long`.

`asType` does not modify the original `handle`, does not transform business logic, and does not support every type conversion. An unrepresentable conversion request can cause `WrongMethodTypeException` when creating the adapter or invoking; an invalid reference cast at runtime can throw `ClassCastException`. Do not expect `asType` to automatically parse the string `"42"` into the number `42`.

## 10. Practice 3: Constructor, Receiver, and `invokeExact`

Create the file **`MethodTypeConstructorAndInvokeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodTypeConstructorAndInvokeDemo {
    static class Box {
        private final String value;

        Box(String value) {
            this.value = value;
        }

        String value() {
            return value;
        }
    }

    static long twice(long input) {
        return input * 2;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType constructorType = MethodType.methodType(void.class, String.class);
        MethodHandle constructor = lookup.findConstructor(Box.class, constructorType);
        System.out.println("constructor lookup return: "
                + constructorType.returnType().getSimpleName());
        System.out.println("constructor handle return: "
                + constructor.type().returnType().getSimpleName());
        System.out.println("constructor handle parameters: "
                + constructor.type().parameterCount());

        Box box = (Box) constructor.invokeExact("box-1");
        MethodHandle getter = lookup.findVirtual(
                Box.class, "value", MethodType.methodType(String.class));
        System.out.println("getter receiver: "
                + getter.type().parameterType(0).getSimpleName());
        System.out.println("getter result: "
                + (String) getter.invokeExact(box));

        MethodHandle twiceHandle = lookup.findStatic(
                MethodTypeConstructorAndInvokeDemo.class,
                "twice", MethodType.methodType(long.class, long.class));
        System.out.println("invokeExact: " + (long) twiceHandle.invokeExact(7L));
        System.out.println("invoke widening: " + (long) twiceHandle.invoke(7));
        MethodHandle adapted = twiceHandle.asType(
                MethodType.methodType(long.class, int.class));
        System.out.println("asType then exact: "
                + (long) adapted.invokeExact(7));
        try {
            Object incorrect = twiceHandle.invokeExact(7L);
            System.out.println(incorrect);
        } catch (WrongMethodTypeException exception) {
            System.out.println("wrong return context: "
                    + exception.getClass().getSimpleName());
        }
    }
}
```

```bash
javac --release 17 MethodTypeConstructorAndInvokeDemo.java
java MethodTypeConstructorAndInvokeDemo
```

**Stdout:**

```text
constructor lookup return: void
constructor handle return: Box
constructor handle parameters: 1
getter receiver: Box
getter result: box-1
invokeExact: 14
invoke widening: 14
asType then exact: 14
wrong return context: WrongMethodTypeException
```

**Analysis:** `findConstructor` takes the type `(String)void` but creates a `(String)Box` handle; `findVirtual` for a getter declaring no parameters produces a handle with one `Box` parameter as the receiver. `invokeExact` must also match the return type, whereas `invoke` and `asType` handle the `int -> long` case when permitted. In the erroneous call, the compiler infers the result type `Object` from the target variable, making it differ from `long` and raising `WrongMethodTypeException`, which the program intentionally catches to demonstrate.

## 11. Signature Modification Operations and Proper Usage

`MethodType` has methods that **do not mutate the current object**:

| Operation | Meaning | Example if original is `(String,int)boolean` |
| --- | --- | --- |
| `changeReturnType(long.class)` | Change return type | `(String,int)long` |
| `changeParameterType(1, long.class)` | Replace type at index 1 | `(String,long)boolean` |
| `insertParameterTypes(0, Service.class)` | Insert before index 0 | `(Service,String,int)boolean` |
| `appendParameterTypes(Object.class)` | Append at the end | `(String,int,Object)boolean` |
| `dropParameterTypes(0, 1)` | Remove positions in range `[0,1)` | `(int)boolean` |
| `erase()` | Replace all reference types with `Object`, keep primitives | `(Object,int)boolean` |
| `generic()` | Replace both primitive and reference types with `Object` (in the generic form per API) | `(Object,Object)Object` |
| `wrap()` | Convert primitives to wrappers when present | `(String,Integer)Boolean` |
| `unwrap()` | Convert corresponding wrappers to primitives | Depends on actual wrappers present |

This is a table of **type representation results**, not MethodHandles being invoked. Some operations may throw an error if an index is out of bounds, `void.class` is put in a parameter, or the slot limit is exceeded.

### 11.1. Why a New `MethodType` Does Not Automatically Change How a Method Is Called

Suppose we have `MethodType oldType = methodType(String.class, String.class, int.class)`. Calling `oldType.changeParameterType(1, long.class)` creates a different signature, but **does not create a new method `echo(String,long)`**. If this wrong type is used for `lookup.findVirtual(Handler.class, "echo", ...)`, lookup may throw `NoSuchMethodException` because the method has a different declared type. If an existing handle is available, only valid adapters (such as `asType`) create an invocation path that accepts a different type according to conversion rules.

Similarly, adding a receiver with `insertParameterTypes(0, Handler.class)` only produces **a type sequence equivalent to the expected handle type**; it does not perform a lookup or bind a receiver.

### 11.2. Common Index Pitfalls

- `parameterType(0)` reads the **first parameter**, not the return type.
- `dropParameterTypes(start, end)` is **end-exclusive**, so `dropParameterTypes(0, 1)` removes exactly one parameter.
- `insertParameterTypes(0, ...)` inserts before the first element; to add at the end, use `appendParameterTypes(...)`.
- `parameterCount() == 0` is valid for `()void` or `()String`; do not automatically infer that the method is static, because an instance method can have zero declared parameters while its handle still has a receiver.
- Do not assume `List<String>` becomes a distinct type in `MethodType`: the JVM sees raw `List.class` here; generic information lives in other Reflection or bytecode structures.

## 12. Comparing Four Common Invocation Forms

Suppose class `Worker` has valid members and `lookup` has corresponding access permissions:

| Member / action | `MethodType` passed to Lookup | Actual `MethodType` of the handle | Receiver? |
| --- | --- | --- | --- |
| `static int calc(String x)` via `findStatic` | `(String)int` | `(String)int` | No |
| `String render(int n)` via `findVirtual` | `(int)String` | `(Worker,int)String` | Yes, position 0 |
| `new Worker(String id)` via `findConstructor` | `(String)void` | `(String)Worker` | No, object is newly created |
| `render` after `bindTo(worker)` | Existing handle `(Worker,int)String` | `(int)String` | Receiver already bound, no longer passed |

The table above describes the standard rule when lookup succeeds. For protected methods, certain other handle kinds, or special adapters, the receiver type may be stricter than `Worker`; checking `handle.type()` is the immediate source of verification.

### 12.1. Reflection's Receiver Is Not a Separate `MethodType` Parameter

Java has annotated receiver parameter syntax in valid cases, for example `void m(@Readonly Example this)` (syntax illustration only, assuming the annotation exists). Reflection can read receiver annotations via `Executable.getAnnotatedReceiverType()`. However, receiver annotation metadata does not cause the `MethodType` of the **declared signature** to add a `this` parameter. When describing a handle that calls an instance method, the receiver is present in the handle signature due to the **invocation mechanism**, not due to a modifier or parameter name.

This is an important point when combining `Method.getParameterTypes()` with `MethodHandles.Lookup.findVirtual`: the declared parameter type array does not contain the receiver; the handle type after lookup does.

## 13. Application Scenario: Writing a Signature Checker for Runtime Invocation

A loader or framework selects a method by configuration, such as class name, method name, input type list, and return type. A sensible workflow:

1. Resolve the class containing the method and the parameters into `Class<?>` objects from the **intended class loader**; do not treat string names as sufficient to prove two types are the same.
2. Build `MethodType` in the **order `returnType`, then `parameterTypes`**.
3. Choose the right lookup method: `findStatic` for static methods, `findVirtual` for instance methods, `findConstructor` for constructors.
4. After lookup, read `handle.type()` to identify the inserted **receiver** or the replaced **constructor return type**.
5. If there is a fixed instance, use `bindTo` according to its contract; if the caller's input types differ, only use `asType` when the conversion is safe and supported.
6. Log the descriptor or class type list along with the class loader when diagnosing, and separate lookup errors from invocation errors.

For logging tools, it is helpful to log all of:

```text
requested member: Handler.echo(String,int):String
lookup type:       (String,int)String
handle type:       (Handler,String,int)String
bound handle type: (String,int)String
```

Do not generate method names from `MethodType` or infer access permissions from `handle.type()`. To interpret generics, parameter names, annotations, or modifiers, read the corresponding Reflection APIs outside `MethodType`.

### 13.1. Mapping `java.lang.reflect.Method` to `MethodType`

Given an existing `java.lang.reflect.Method reflected`, you can build the **declared** signature:

```java
// Fragment: reflected is an existing java.lang.reflect.Method object.
MethodType declaredType = MethodType.methodType(
        reflected.getReturnType(), reflected.getParameterTypes());
```

`getParameterTypes()` contains the **erased types of the declared parameters**, without automatically including a receiver. If the method is an instance method and you look it up with `findVirtual(reflected.getDeclaringClass(), reflected.getName(), declaredType)`, the handle receives the receiver first if lookup succeeds. For a static method, the handle signature does not add a receiver. The `Lookup.unreflect(reflected)` option is useful when you already have a `Method`; appropriate access permissions are still required.

### 13.2. Choosing a Contract Display Format for Humans or Machines

- `MethodType.toString()` is short and suitable for learning/diagnostics; class names use **simple names**, so they can collide across different packages.
- `toMethodDescriptorString()` is suitable for matching bytecode and storing descriptor forms per JVMS, but **does not store class loader identity**.
- If you need to uniquely identify a method, combine at least the owner class, method name, parameter types, and return type, along with loader/module context when needed.
- Do not use `MethodType.toString()` as an immutable serialization protocol across versions or systems.

## 14. Common Errors and How to Diagnose Them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `NoSuchMethodException` on `findVirtual` | Passing a type **that includes the receiver** to lookup, or wrong parameter/return types, wrong method name | Remove the receiver from the requested type, read the exact declared signature |
| `NoSuchMethodException` on `findStatic` | Method is not static, or type/name differs | Choose the right lookup and signature |
| `IllegalAccessException` at Lookup | Class/member or module does not grant corresponding access | Use a lookup with valid privileges, check visibility/module exports/opens |
| `WrongMethodTypeException` at `invokeExact` | Call-site type differs from `handle.type()`, possibly due to the **return type** | Print `handle.type()`, check casts and static types of each argument |
| `WrongMethodTypeException` at `asType`/`invoke` | No valid conversion per the API | Design a proper adapter or convert data intentionally before invoking |
| `ClassCastException` on invoke/adapt | Invalid reference type conversion at runtime | Check runtime types and contracts |
| `IllegalArgumentException` creating `MethodType` | `void.class` parameter or slot limit exceeded | Fix type declarations and parameter count |
| `IndexOutOfBoundsException` from `parameterType`/`dropParameterTypes` | Index out of range | Check `parameterCount()` and half-open range |
| `TypeNotPresentException` from descriptor | Reference class in descriptor cannot be resolved by loader | Check class loader, classpath/module path |
| Still passing receiver after calling `bindTo` | Receiver is already fixed, handle parameter count decreased | Invoke according to the actual `bound.type()` |

**Distinguishing phases:** `NoSuchMethodException` and `IllegalAccessException` usually occur during **lookup**; `WrongMethodTypeException` occurs when **matching types/invoking/adapting a handle**; business logic errors inside the invoked method are a separate matter. `MethodType` alone is only a type description; it does not execute the target method's code.

## 15. Self-Check Questions

1. For `MethodType.methodType(void.class, String.class, int.class)`, what is the return type and what is `parameterCount()`?
2. A method declared as `String query(int id)` in class `Repository` is looked up with `findVirtual`. Should `Repository.class` be added to the `MethodType` passed to lookup? What could `handle.type()` be?
3. Why does `findConstructor(Widget.class, methodType(void.class, String.class))` produce a handle returning `Widget`?
4. When calling `bindTo` with a receiver, does the handle's `parameterCount()` increase or decrease?
5. `(long) handle.invokeExact(7L)` succeeds for a `(long)long` handle. Why might `Object x = handle.invokeExact(7L)` fail?
6. In the descriptor `(Ljava/lang/String;J)I`, what do `J` and `I` represent? Are the method name and receiver included in the descriptor?
7. Does `MethodType` distinguish `List<String>` and `List<Integer>` as two different runtime parameter types?
8. How do `MethodType.erase()` and `generic()` differ for a signature containing `int`?
9. When logging two `MethodType` instances whose descriptor strings are identical yet `equals()` is `false`, what should be checked at runtime?
10. If an instance method takes **0 declared parameters**, does the `findVirtual` handle also have `parameterCount() == 0`?

**Suggested answers:** (1) `void`, with 2 parameters. (2) No; lookup takes `(int)String`, handle is typically `(Repository,int)String`. (3) A JVM constructor has return `void` in its declaration, while the handle creates and returns a `Widget` object. (4) Decreases by one when binding the first parameter. (5) `invokeExact` also matches the contextual return type; `Object` differs from `long`. (6) `J=long`, `I=int`; neither name nor receiver is included. (7) No; generic types undergo erasure to `List.class` when creating the descriptor. (8) `erase()` preserves primitives, `generic()` converts them to `Object`. (9) Class loader / `Class<?>` identity. (10) No; the handle still requires the receiver.

## 16. Authoritative References

- [Java SE 21 API — `java.lang.invoke.MethodType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html): factories, immutability, `equals`, reading parameters/return type, descriptors, transformations, and limits.
- [Java SE 21 API — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findStatic`, `findVirtual`, `findConstructor`, and receiver rules.
- [Java SE 21 API — `MethodHandle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, `bindTo`, `asType`.
- [JVM Specification 21, `4.3.3 Method Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.3): descriptor syntax and argument slot limits.
- [Oracle Java Magazine — Method handles: a better way to do Java reflection](https://blogs.oracle.com/javamagazine/java-reflection-method-handles/): illustrates method signatures and receivers after lookup.

The key takeaway when using `MethodType` is to always ask: **does this type describe the declared method, or does it describe the invocation of a specific `MethodHandle`?** Simply distinguishing those two contexts correctly will let you determine the exact parameters, return type, and receiver when looking up, binding, or invoking in the Java dynamic runtime.