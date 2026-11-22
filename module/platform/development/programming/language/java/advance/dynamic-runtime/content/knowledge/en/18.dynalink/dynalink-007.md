# 18.7. Operating on Java Objects, Type Conversions, and `NoSuchDynamicMethodException` in Dynalink

When a dynamic language runtime running on the JVM encounters an expression such as `object.color`, `object.join(value)`, `list[index]`, or `new JavaClass()`, the actual Java type of the object may only be known **at runtime**. `jdk.dynalink` (Java 9+) provides the infrastructure to link those high-level operations to the corresponding `MethodHandle`. **`BeansLinker`** is the built-in linker for operating on ordinary Java objects: JavaBean properties, public fields, methods, record accessors, `List`, `Map`, arrays, static members, and constructors.

It is also necessary to understand the limits: Dynalink **does not convert every value into every type**, does not arbitrarily access every private member, and does not automatically guarantee that every operation name exists. When no linker can resolve an appropriate operation, the system may throw **`jdk.dynalink.NoSuchDynamicMethodException` at invocation time**, which differs from overload selection errors, type conversion errors, and `MethodHandle.invokeExact` descriptor errors.

This lesson belongs to group **18. Dynalink** and focuses on three questions:

1. How does Dynalink represent, link, and execute operations **on Java objects**?
2. How do `BeansLinker` and type conversion services select method overloads and adapt arguments/return values?
3. When does `NoSuchDynamicMethodException` actually occur, and how is it distinguished from `NoSuchMethodException`, `ClassCastException`, and `WrongMethodTypeException`?

There is a **standalone** Java 17+ program, using no external libraries, illustrating all of those groups of scenarios, along with compile commands and 20 lines of verified `stdout`.

## 1. Dynalink is a dynamic linking library, not a language itself

The standard **JDK** module is `jdk.dynalink`. The core types include:

- `DynamicLinkerFactory`: configures/creates a `DynamicLinker`.
- `DynamicLinker`: coordinates linkers to find a way to perform an operation at a call site.
- `Operation`, `StandardOperation`, `StandardNamespace`, `NamedOperation`: describe operations such as reading the `color` property, reading an element, or calling a dynamic method.
- `CallSiteDescriptor`: describes the `Lookup`, operation, and `MethodType` of the call site.
- `SimpleRelinkableCallSite`: an implementation of `RelinkableCallSite` that can switch targets when the runtime encounters a different receiver.
- `BeansLinker`: the fallback linker for Java objects; it maps operations to getters/setters/fields/methods/elements/constructors.
- `LinkerServices`, `GuardingTypeConverterFactory`, and related APIs: support type adaptation and integration of converters from other languages.

`jdk.dynalink` builds on the primitives in `java.lang.invoke` but at a **higher level of abstraction**. A `MethodHandle` only knows how to invoke a typed target; Dynalink also understands the question "get the `color` property of the current object" and can choose a different getter when the object changes type at runtime.

```text
Application / language runtime
          |
          | Operation: GET:PROPERTY:color
          | MethodType: (Object)Object
          v
CallSiteDescriptor + RelinkableCallSite
          |
          v
      DynamicLinker
          |
    prioritized linkers (if any)
          |
    discovered linkers (if any)
          |
    BeansLinker fallback
          |
          v
guard + target MethodHandle
          |
          v
execute getter/field on Java receiver
          |
          +-- If receiver class differs:
                  guard fails -> relink
```

If no linker accepts the operation and performs the linkage at the call site, Dynalink cannot "guess" a substitute method on its own. When the caller executes that call site, `NoSuchDynamicMethodException` is a possibility according to the contract.

### 1.1. No need to generate `invokedynamic` bytecode manually to test the API

Dynalink is typically used in the bootstrap of the `invokedynamic` instruction, but you can also create a `RelinkableCallSite` in regular Java code and then use `dynamicInvoker()` to run it. The example in section 7 takes this approach for easy testing, without needing ASM or bytecode generation tools.

**Do not confuse:** `DynamicLinker.link(...)` sets up a relinkable call site, but cases with no valid operation may **not report an error immediately when building the descriptor or calling `link`**. Linkage errors usually appear when **actually invoking** and `DynamicLinker` searches for a linker for the runtime values.

## 2. Representing operations: `StandardOperation` and `StandardNamespace`

Dynalink does not accept arbitrary language strings like `"obj.color"` and parse them on its own. The integrator must construct the appropriate **Operation**.

The standard operations defined by the Java 17 Javadoc:

| Operation | Meaning | Logical signature |
| --- | --- | --- |
| `GET` + namespace | Get property/element/method | `(receiver, name) → value`, or `(receiver) → value` when `named(...)` is used |
| `SET` + namespace | Set property/element | `(receiver, name, value) → void`, or `(receiver, value) → void` when `named(...)` is used |
| `REMOVE` + namespace | Remove element | `(receiver, name) → void`, or `(receiver) → void` when `named(...)` is used |
| `CALL` | Call a callable object | `(callable, receiver, arguments...) → result` |
| `NEW` | Create an object from a constructor object | `(constructor, arguments...) → result` |

**`GET`, `SET`, and `REMOVE` require a namespace**. For Java, the common namespaces are:

| Namespace | Interpretation | Java objects supported by `BeansLinker` |
| --- | --- | --- |
| `StandardNamespace.PROPERTY` | Property by name | JavaBean getter/setter, public field, record accessor, synthetic property like `length` |
| `StandardNamespace.METHOD` | Method by name | Gets a **dynamic method object**, then `CALL` to execute |
| `StandardNamespace.ELEMENT` | Element by key/index | Native array, `List`, `Map` |

A property getter named `color` can be expressed as:

```java
Operation getColor = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY)
        .named("color");
```

After `named("color")`, there is no longer a need to pass the string `"color"` as a runtime argument. Therefore, a `CallSiteDescriptor` of type `(Object)Object` suffices for `GET:PROPERTY:color`. Conversely, an element getter **without a fixed key** can use type `(Object,Object)Object` to pass the receiver and key/index on each call.

Distinguish clearly:

```java
StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY).named("color");
StandardOperation.GET
        .withNamespace(StandardNamespace.METHOD).named("join");
StandardOperation.GET
        .withNamespace(StandardNamespace.ELEMENT);
```

These three expressions create **three different operations**, even though all have the `GET` prefix. This is illustrative code, not a standalone runnable Java file.

### 2.1. `CALL` is not `GET:METHOD`

For a Java object `bean` with method `join(String)`:

1. `GET:METHOD:join` returns a **dynamic method object** recognized by `BeansLinker`. It does not invoke `join` yet.
2. `CALL` takes that **callable object**, the **receiver**, and the arguments, then selects the appropriate overload.

Why pass the receiver twice in the sequence of operations? Because the first time, the receiver is needed to **look up** the dynamic method; the `CALL` invocation needs the receiver to **execute** the method on the object. With the standard API, the signature of `CALL` has the form `(callable, receiver, args...)`. Do not assume that the method object retrieved from `GET:METHOD` is always a Java `Method` or a `MethodHandle` with the receiver already bound.

The following example is actually verified:

```java
Object callable = getJoin.invokeExact((Object) bean);
Object result = call.invokeExact(
        callable, (Object) bean, (Object) "abc");
```

This is a snippet extracted from the program in section 7; `getJoin` and `call` are already linked with the appropriate descriptors in that program.

## 3. `BeansLinker`: linking Java members and collections

`DynamicLinkerFactory` prepares a `BeansLinker` as the final fallback by default, if you have not actively replaced the set of fallback linkers. This allows handling Java objects even when you have not built a separate linker for another language.

### 3.1. JavaBean getters/setters and public fields

With the class:

```java
public static class ColorBean {
    private String color = "red";

    public String getColor() { return color; }
    public void setColor(String value) { color = value; }
}
```

`GET:PROPERTY:color` will map to the getter `getColor()`, and `SET:PROPERTY:color` to the setter `setColor(...)`. The `color` field here is **private**; Dynalink does not need to access the private field directly because it uses the **public accessors**.

`BeansLinker` also supports **public fields** as properties. If a name has both a public field and a getter/setter, JavaBean accessors take precedence according to the linker rules. There is no promise that using Dynalink can read/write every private field as when enabling `setAccessible(true)`; visibility and module permission checks are still enforced.

A property is usually inferred from `getXxx()`, `isXxx()`, or `setXxx(...)` methods (per `BeansLinker`'s contract), without requiring an `xxx` field to exist in the object.

### 3.2. Java records

Since Java 16, records provide component accessors whose names are the component names themselves, for example:

```java
public record Box(String title) {}
```

Java 17's `BeansLinker` allows `GET:PROPERTY:title` to read the value using the `Box.title()` accessor even though it is not a getter named `getTitle()`.

In the standalone program, `GET:PROPERTY:title` on `new Box("record")` returns `"record"`. Do not generalize that every public method with some argument automatically becomes a valid property: the API specifies clearly the cases supported by `BeansLinker`.

### 3.3. Arrays, `List`, `Map`

`GET/SET` in the `ELEMENT` namespace can access elements:

```java
// Link GET:ELEMENT with MethodType (Object,Object)Object
Object second = getElement.invokeExact(
        (Object) list, (Object) Integer.valueOf(1));

// Link SET:ELEMENT with MethodType (Object,Object,Object)void
setElement.invokeExact(
        (Object) map, (Object) "key", (Object) 42);
```

`List` typically uses an index, `Map` uses a key, and arrays use an index. For `Map`, `REMOVE:ELEMENT` can remove an entry. For `List`, removing can change the size/indices; for fixed-size arrays, do not assume elements can be removed.

`BeansLinker` also provides the synthetic property `length` for arrays, `Collection`, and `Map`:

```java
Operation length = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY)
        .named("length");
```

On the array `{"x","y"}`, this operation returns length `2`. If you want to read `Map.size()` via the method namespace, that is a different choice from using the virtual property `length`; do not confuse method/property/element even when they share similar parameter patterns.

### 3.4. Static members and constructors require `StaticClass`

An ordinary `Class<?>` is **not** treated directly by `BeansLinker` as a static member namespace. For example, `ColorBean.class` is a Java `Class` object with methods such as `getName()` and `getSuperclass()`. To perform `GET:METHOD:banner` on a static method or `NEW` to create an instance, use:

```java
StaticClass staticFacet = StaticClass.forClass(ColorBean.class);
```

`StaticClass` is a wrapper recognized by `BeansLinker` and used to select static methods, static properties, and constructors of the represented class. `StandardOperation.NEW` with an appropriate `StaticClass` can select a valid Java constructor, including when overloaded.

**Do not** assume that `StandardOperation.NEW` on **any Java object** will create a new object. With `new ColorBean()` as the receiver for `NEW`, if no linker supports it, Dynalink may throw `NoSuchDynamicMethodException`.

## 4. How to create a dynamic call site

A Java program can build a `DynamicLinker`:

```java
DynamicLinker linker = new DynamicLinkerFactory().createLinker();
```

Then create a `CallSiteDescriptor` with `MethodHandles.Lookup`, `Operation`, and `MethodType`:

```java
CallSiteDescriptor descriptor = new CallSiteDescriptor(
        MethodHandles.lookup(),
        StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named("color"),
        MethodType.methodType(Object.class, Object.class));
```

`SimpleRelinkableCallSite` is a call site form that can update its target. After linking:

```java
MethodHandle getter = linker.link(
        new SimpleRelinkableCallSite(descriptor)).dynamicInvoker();
```

`getter` has type `(Object)Object` as in the descriptor, rather than automatically accepting any Java signature. When calling `getter.invokeExact((Object)bean)` with the return expression assigned to an `Object` variable, the caller's descriptor matches. If you call `getter.invokeExact(...)` and discard the result as a **statement**, the compiler generates a call-site descriptor with a `void` return; this can cause `WrongMethodTypeException` because the actual handle returns `Object`. That is an `invokeExact` error, **not** a missing Java member error.

**Relationship with relinking:** If the same getter is called with two different receiver classes, the target linked for the first class has a guard. When the guard no longer matches, `DynamicLinker` can relink for the second class. `SimpleRelinkableCallSite` typically stores the linkage for the most recently encountered type (*monomorphic*); `ChainedCallSite` can retain multiple guard-target pairs (*polymorphic*), suitable for scenarios where the receiver frequently changes types. This is a linkage caching policy choice, not a change to the getter semantics you requested.

### 4.1. Call and error flow diagram

```text
1. linker.link(relinkableCallSite)
             |
             +--> creates initial target to link when needed
2. caller invokes dynamicInvoker.invokeExact(receiver, args...)
             |
             v
3. Does Dynalink have a matching linkage for the current receiver?
             |
       +-----+-----+
       |           |
      Yes          No
       |           |
       |       ask GuardingDynamicLinkers
       |           |
       |       +---+----------------+
       |       |                    |
       |      Yes                   No
       |       |                    |
       |     guard + target         NoSuchDynamicMethodException
       |       |
       +-------+
               |
               v
4. Adapt arguments/return according to MethodType and conversions
               |
               +--> conversion/overload may fail separately
               |
               v
5. Invoke actual Java method/field/constructor
               |
               +--> exceptions thrown by the Java method itself may propagate out
```

The diagram illustrates the **conceptual** stages; the JIT and linkers may optimize, combine, or defer steps. It is not a fixed stack trace or a promise that every exception is raised at the exact line shown in the diagram.

## 5. Type conversions: adaptation exists, but not "arbitrary coercion"

Dynalink has `LinkerServices` so linkers can adapt a `MethodHandle` to the signature at the dynamic call site. With the default linker for Java objects, conversions following Java method-handle semantics are the foundation; other language runtimes can provide `GuardingTypeConverterFactory` and `MethodTypeConversionStrategy` to define specialized coercions.

For an application, **distinguish three type layers**:

1. **Types of the actual receiver/arguments:** `String`, `Integer`, `Short`, `ColorBean`...
2. **`MethodType` of the dynamic call site:** for example `(Object,Object,Object)Object` for `CALL`, or `(Object,short)void` for a setter.
3. **Target Java member types:** `join(String)`, `join(int)`, `setCount(int)`.

What is valid is that Dynalink finds/adapts a compatible way to invoke according to the contract, not a conversion that "works for every engine" regardless of the data.

### 5.1. Primitive widening: `short` → `int`

A JavaBean has a setter:

```java
public void setCount(int value) { count = value; }
```

We can link `SET:PROPERTY:count` with descriptor `(Object,short)void` and then invoke:

```java
setCount.invokeExact((Object) bean, (short) 7);
```

`BeansLinker` selects the setter taking `int`; `short` is **widened** to `int`. In the real example, `bean.getCount()` returns `7`. This is an intentional and safe type conversion under the method-handle adaptation system.

### 5.2. Boxing/unboxing and runtime overload selection

Suppose there are two overloads:

```java
public String join(String text) { return "text:" + text; }
public String join(int value)   { return "number:" + value; }
```

A `CALL` call site is declared `(Object,Object,Object)Object`, where the last argument is passed as type `Object` but the **runtime value** can be `String` or `Integer`. Dynalink uses dynamic information to select the method:

```java
Object a = call.invokeExact(
        callable, (Object) bean, (Object) "abc");
Object b = call.invokeExact(
        callable, (Object) bean, (Object) Integer.valueOf(3));
```

In the program in section 7, `a == "text:abc"` and `b == "number:3"`. With `Integer`, the linker can unbox to call `join(int)`. This does not mean every overload is uniquely resolved automatically: when multiple overloads apply equally, selection can be ambiguous, depending on the signatures and conversion rules provided by the runtime.

### 5.3. No default "`String` → `int` via number parsing"

`"7"` is a `String`; `7` is a primitive `int`; `Integer.valueOf(7)` is a wrapper `Integer`. Dynalink/`BeansLinker` **does not promise** to automatically call `Integer.parseInt("7")` when a setter expects `int`.

In the test program, using `SET:PROPERTY:count` with a dynamic parameter type `Object` and then passing `"7"` causes `ClassCastException` when the conversion plan cannot be executed. If an embedded language wants to automatically parse strings into numbers, it must provide its **own conversion policy** via a linker/type converter or convert beforehand before calling.

Even though the JVM allows certain primitive conversions, do not assume every object value that looks "printable as a number" will be validly converted. Invalid type conversions can fail **during handle adaptation**, during overload selection, or at invocation time.

### 5.4. `LinkerServices` and custom conversions

`LinkerServices.asType(MethodHandle, MethodType)` combines `MethodHandle.asType` rules with converters provided by `GuardingTypeConverterFactory`. `canConvert(from, to)` asks whether a conversion **can exist**, without guaranteeing that every runtime value will succeed. `compareConversion` gives linkers additional information to resolve overloads when multiple targets can accept the arguments.

For example, a language runtime with its own `BigNumber` type may allow conversion to `int` under a specific overflow/clamping/exception policy. **That is the policy of the integrated runtime**, not the default behavior of every `BeansLinker` or JavaScript engine.

Similarly, `setAutoConversionStrategy(...)` on `DynamicLinkerFactory` allows customizing conversion behavior when coordinating linking. If you replace a strategy, you need to thoroughly test primitive widening/narrowing, boxing/unboxing, null, overloads, and return types; do not test only one happy case.

### 5.5. `invokeExact` signature and operation signature

Even when the linker has produced the right target, the caller must still call `invokeExact` with a descriptor that **matches `MethodHandle.type()` exactly**. This is not a JavaBean overload rule, but a rule of `java.lang.invoke.MethodHandle` itself.

For example, `getColor` has type `(Object)Object`:

```java
Object ok = getColor.invokeExact((Object) bean); // Correct.
getColor.invokeExact((Object) bean);             // Wrong return descriptor: void.
```

The second line is deliberately placed inside a `try/catch` block in the standalone example and throws `WrongMethodTypeException`. It cannot be fixed by adding a new `GuardingDynamicLinker` because the failure occurs **at the handle invocation signature**. If you want adaptation based on call-site context, look into `invoke` or `asType` with their own semantics and control over conversion cost/types.

## 6. What does `NoSuchDynamicMethodException` mean?

**Signature/meaning:** `jdk.dynalink.NoSuchDynamicMethodException` is a `RuntimeException`, documented as: thrown **at invocation** if no available `GuardingDynamicLinker` can link that call site.

This is broader than "no Java method named X found": the operation could be `GET:PROPERTY`, `SET:ELEMENT`, `NEW`..., and the issue is that **there is no matching linkage path** for the current receiver, operation, and signature.

Verified examples with the default `BeansLinker`:

- `GET:METHOD:absent` on `ColorBean` which does not have that method → `NoSuchDynamicMethodException`.
- `GET:PROPERTY:absent` on `ColorBean` which does not have that readable property → `NoSuchDynamicMethodException`.
- `NEW` on an **ordinary instance** of `ColorBean` instead of `StaticClass` → `NoSuchDynamicMethodException`.

The exception **does not necessarily occur immediately when calling `link(...)`**; actual linking depends on runtime values at invocation time. Nor is there necessarily an error if a custom linker or a `MissingMemberHandlerFactory` has been installed to provide a fallback for missing members.

### 6.1. Comparison with three easily confused errors

| Error | Common reason | Verified example |
| --- | --- | --- |
| **`NoSuchDynamicMethodException`** | No linker provides linkage for the operation at the call site | `GET:METHOD:absent`; `NEW` on an ordinary Java instance |
| **`NoSuchMethodException`** | The dynamic method exists, but no overload can be selected matching the runtime argument list | `CALL` with `join(String)`/`join(int)` but passing `new Object()` |
| **`ClassCastException`** | A call/conversion path exists, but the runtime value does not match the conversion placed into the handle | `SET:PROPERTY:count` receiving `"7"` for an `int` setter in the example |
| **`WrongMethodTypeException`** | The `invokeExact` call-site descriptor differs from `MethodHandle.type()` | Calling a getter returning `Object` as a statement returning `void` |

**Important point:** `NoSuchMethodException` is a checked exception in the Java reflection API, but in the Dynalink example it can be thrown **during invocation/overload resolution of the dynamic method object** and propagate to a caller declaring `throws Throwable`. Do not deduce that every "missing method" error in Dynalink is always `NoSuchDynamicMethodException` or vice versa. During overload selection, interactions between converters, varargs, and types can determine the specific error type.

Similarly, `ClassCastException` is not proof that all conversions are handled after the linker has found the method; it is the **observed result** in the example with a `String` value, an `int` target setter, and the descriptor used.

### 6.2. Access errors and exceptions from the target method

`BeansLinker` works with members permitted by Java/`Lookup` policies. It does not turn private members into public ones. A method may fail to link due to access constraints or module restrictions, even if the name exists in reflection. Conversely, a **validly linked** Java target can itself throw `IllegalArgumentException`, `IOException`, or another business exception — this is an error **inside the target method**, not an error caused by Dynalink failing to find the operation.

When debugging, separate the four steps: **operation descriptor → receiver class/lookup → overload/conversion → execution target**, then read the stack trace and cause chain rather than guessing from the exception name alone.

### 6.3. `MissingMemberHandlerFactory` changes missing-member semantics

`BeansLinker` has a constructor taking a `MissingMemberHandlerFactory`. It allows a language runtime to define a fallback when a property/method does not exist. A language that wants "missing property returns undefined" can put that policy into the linker; in that case, a missing property may **not** produce `NoSuchDynamicMethodException` as in the default configuration.

Do not write a `catch (NoSuchDynamicMethodException)` and blindly return `null` for **all** operations: that would hide configuration errors, constructor errors, property name errors, and API contract errors. If the language requires "missing → undefined" semantics, design it explicitly in the policy/linker and distinguish it from runtime errors that must be reported.

## 7. Runnable Java 17+ program: property, element, method, constructor, conversion, exceptions

The following program uses `DynamicLinkerFactory` and `SimpleRelinkableCallSite`; there is no need to generate `invokedynamic` bytecode. A `link(...)` helper creates a `CallSiteDescriptor` for each operation and returns `dynamicInvoker()`. All examples use the **default `BeansLinker`**, with no custom converter or missing-member handler.

Save the entire code under the name **`DynalinkJavaObjectsDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.NoSuchDynamicMethodException;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.beans.BeansLinker;
import jdk.dynalink.beans.StaticClass;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkJavaObjectsDemo {
    public static class ColorBean {
        private String color = "red";
        private int count;

        public String getColor() { return color; }
        public void setColor(String value) { color = value; }
        public int getCount() { return count; }
        public void setCount(int value) { count = value; }
        public String join(String text) { return "text:" + text; }
        public String join(int value) { return "number:" + value; }
        public static String banner() { return "STATIC"; }
    }

    public record Box(String title) {}

    private static final DynamicLinker LINKER =
            new DynamicLinkerFactory().createLinker();

    private static MethodHandle link(Operation operation, MethodType type) {
        CallSiteDescriptor descriptor = new CallSiteDescriptor(
                MethodHandles.lookup(), operation, type);
        return LINKER.link(new SimpleRelinkableCallSite(descriptor))
                .dynamicInvoker();
    }

    public static void main(String[] args) throws Throwable {
        ColorBean bean = new ColorBean();

        MethodHandle getColor = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.PROPERTY).named("color"),
                MethodType.methodType(Object.class, Object.class));
        MethodHandle setColor = link(
                StandardOperation.SET.withNamespace(
                        StandardNamespace.PROPERTY).named("color"),
                MethodType.methodType(void.class, Object.class, Object.class));

        Object oldColor = getColor.invokeExact((Object) bean);
        setColor.invokeExact((Object) bean, (Object) "blue");
        Object newColor = getColor.invokeExact((Object) bean);
        System.out.println("property=" + oldColor + "->" + newColor);

        MethodHandle setCount = link(
                StandardOperation.SET.withNamespace(
                        StandardNamespace.PROPERTY).named("count"),
                MethodType.methodType(void.class, Object.class, short.class));
        setCount.invokeExact((Object) bean, (short) 7);
        System.out.println("shortToInt=" + bean.getCount());

        MethodHandle getJoin = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.METHOD).named("join"),
                MethodType.methodType(Object.class, Object.class));
        Object callable = getJoin.invokeExact((Object) bean);
        System.out.println("isDynamicMethod=" + BeansLinker.isDynamicMethod(callable));

        MethodHandle call = link(
                StandardOperation.CALL,
                MethodType.methodType(
                        Object.class, Object.class, Object.class, Object.class));
        Object stringResult = call.invokeExact(
                callable, (Object) bean, (Object) "abc");
        Object integerResult = call.invokeExact(
                callable, (Object) bean, (Object) Integer.valueOf(3));
        System.out.println("overload.string=" + stringResult);
        System.out.println("overload.integer=" + integerResult);

        MethodHandle exactJoin = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.METHOD).named("join(String)"),
                MethodType.methodType(Object.class, Object.class));
        Object selected = exactJoin.invokeExact((Object) bean);
        Object selectedResult = call.invokeExact(
                selected, (Object) bean, (Object) "xyz");
        System.out.println("explicitSignature=" + selectedResult);

        MethodHandle getElement = link(
                StandardOperation.GET.withNamespace(StandardNamespace.ELEMENT),
                MethodType.methodType(
                        Object.class, Object.class, Object.class));
        MethodHandle setElement = link(
                StandardOperation.SET.withNamespace(StandardNamespace.ELEMENT),
                MethodType.methodType(
                        void.class, Object.class, Object.class, Object.class));
        MethodHandle removeElement = link(
                StandardOperation.REMOVE.withNamespace(StandardNamespace.ELEMENT),
                MethodType.methodType(void.class, Object.class, Object.class));

        List<String> list = Arrays.asList("one", "two");
        Object second = getElement.invokeExact(
                (Object) list, (Object) Integer.valueOf(1));
        System.out.println("list[1]=" + second);

        Map<String,Object> map = new HashMap<>();
        setElement.invokeExact((Object) map, (Object) "key", (Object) 42);
        Object mapValue = getElement.invokeExact((Object) map, (Object) "key");
        removeElement.invokeExact((Object) map, (Object) "key");
        System.out.println("map.value=" + mapValue);
        System.out.println("map.removed=" + !map.containsKey("key"));

        String[] array = {"x", "y"};
        Object arrayValue = getElement.invokeExact(
                (Object) array, (Object) Integer.valueOf(1));
        MethodHandle getLength = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.PROPERTY).named("length"),
                MethodType.methodType(Object.class, Object.class));
        Object length = getLength.invokeExact((Object) array);
        System.out.println("array.value=" + arrayValue);
        System.out.println("array.length=" + length);

        MethodHandle getTitle = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.PROPERTY).named("title"),
                MethodType.methodType(Object.class, Object.class));
        Object title = getTitle.invokeExact((Object) new Box("record"));
        System.out.println("record.title=" + title);

        StaticClass staticFacet = StaticClass.forClass(ColorBean.class);
        MethodHandle getBanner = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.METHOD).named("banner"),
                MethodType.methodType(Object.class, Object.class));
        Object banner = getBanner.invokeExact((Object) staticFacet);
        MethodHandle callNoArgs = link(
                StandardOperation.CALL,
                MethodType.methodType(
                        Object.class, Object.class, Object.class));
        Object bannerResult = callNoArgs.invokeExact(
                banner, (Object) staticFacet);
        System.out.println("static.banner=" + bannerResult);

        MethodHandle construct = link(
                StandardOperation.NEW,
                MethodType.methodType(Object.class, Object.class));
        Object created = construct.invokeExact((Object) staticFacet);
        System.out.println("new.class=" + created.getClass().getSimpleName());

        MethodHandle missingMethod = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.METHOD).named("absent"),
                MethodType.methodType(Object.class, Object.class));
        try {
            Object ignored = missingMethod.invokeExact((Object) bean);
            System.out.println("missing.method=unexpected:" + ignored);
        } catch (NoSuchDynamicMethodException e) {
            System.out.println("missing.method=" + e.getClass().getSimpleName());
        }

        MethodHandle missingProperty = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.PROPERTY).named("absent"),
                MethodType.methodType(Object.class, Object.class));
        try {
            Object ignored = missingProperty.invokeExact((Object) bean);
            System.out.println("missing.property=unexpected:" + ignored);
        } catch (NoSuchDynamicMethodException e) {
            System.out.println("missing.property=" + e.getClass().getSimpleName());
        }

        try {
            Object ignored = construct.invokeExact((Object) bean);
            System.out.println("new.onInstance=unexpected:" + ignored);
        } catch (NoSuchDynamicMethodException e) {
            System.out.println("new.onInstance=" + e.getClass().getSimpleName());
        }

        try {
            Object ignored = call.invokeExact(
                    callable, (Object) bean, (Object) new Object());
            System.out.println("overload.bad=unexpected:" + ignored);
        } catch (NoSuchMethodException e) {
            System.out.println("overload.bad=" + e.getClass().getSimpleName());
        }

        MethodHandle setCountFromObject = link(
                StandardOperation.SET.withNamespace(
                        StandardNamespace.PROPERTY).named("count"),
                MethodType.methodType(
                        void.class, Object.class, Object.class));
        try {
            setCountFromObject.invokeExact((Object) bean, (Object) "7");
            System.out.println("stringToInt=unexpected");
        } catch (ClassCastException e) {
            System.out.println("stringToInt=" + e.getClass().getSimpleName());
        }

        try {
            getColor.invokeExact((Object) bean); // invokeExact expects void here
            System.out.println("wrongDescriptor=unexpected");
        } catch (WrongMethodTypeException e) {
            System.out.println("wrongDescriptor=" + e.getClass().getSimpleName());
        }
    }
}
```

Compile/run commands from the directory containing the file:

```bash
javac --release 17 --add-modules jdk.dynalink DynalinkJavaObjectsDemo.java
java --add-modules jdk.dynalink DynalinkJavaObjectsDemo
```

**Why `--add-modules jdk.dynalink`?** `jdk.dynalink` is a specific JDK module, not a package in `java.base`. For classpath applications that do not declare `module-info.java`, explicitly requesting this module helps the compiler and launcher resolve the public APIs properly. For a valid **named module**, you need to declare `requires jdk.dynalink;` in the module descriptor and run with the appropriate module-path/module options.

**Exact verified** `stdout`:

```text
property=red->blue
shortToInt=7
isDynamicMethod=true
overload.string=text:abc
overload.integer=number:3
explicitSignature=text:xyz
list[1]=two
map.value=42
map.removed=true
array.value=y
array.length=2
record.title=record
static.banner=STATIC
new.class=ColorBean
missing.method=NoSuchDynamicMethodException
missing.property=NoSuchDynamicMethodException
new.onInstance=NoSuchDynamicMethodException
overload.bad=NoSuchMethodException
stringToInt=ClassCastException
wrongDescriptor=WrongMethodTypeException
```

The code has been **compiled successfully with `javac --release 17`** and executed on **OpenJDK 24**; all 20 lines of output match. Because the verified execution environment is OpenJDK 24, if running on a different vendor/JDK, use the API semantics in the Java 17 documentation as the baseline and note that policies/linkers/conversions may differ if custom extensions are present.

### 7.1. Reading the output by operation group

- **`property=red->blue`:** `GET/SET:PROPERTY:color` invoked the public JavaBean getter/setter even though the internal field is private.
- **`shortToInt=7`:** Dynalink adapted the primitive `short` at the call site to the `int` argument of the setter.
- **`isDynamicMethod=true`:** `GET:METHOD:join` returned a dynamic method object recognized by `BeansLinker`, not the result of calling `join`.
- **`overload.string` / `overload.integer`:** `CALL` selected the overload based on runtime types: `String` or `Integer` unboxed to `int`.
- **`explicitSignature=text:xyz`:** the operation named `join(String)` selected the explicit method signature; useful when overloads are complex or dynamic selection is not desired.
- **`list[1]=two`, `map.value=42`, `map.removed=true`:** `ELEMENT` is a separate namespace; `REMOVE:ELEMENT` removes a `Map` key.
- **`array.value=y` / `array.length=2`:** array elements are accessed by index; `length` is a synthetic property in `BeansLinker`.
- **`record.title=record`:** the record component accessor is mapped to a property getter.
- **`static.banner=STATIC` / `new.class=ColorBean`:** `StaticClass` represents the static facet and constructor, not an ordinary Java `Class<?>`.
- **Three `NoSuchDynamicMethodException` lines:** no matching operation/linker for the absent member or `NEW` on an instance that is not a constructor object.
- **`overload.bad=NoSuchMethodException`:** the dynamic method object was found, but the Java overload list does not accept `new Object()`.
- **`stringToInt=ClassCastException`:** the value `"7"` is not automatically parsed into a number for the `int` setter.
- **`wrongDescriptor=WrongMethodTypeException`:** `invokeExact` of a getter returning `Object` was called in a `void` expression context. Caller descriptor error, not a Dynalink missing-operation error.

## 8. Why can a method overload be selected differently across calls?

For a method group named `join`, `GET:METHOD` can return a dynamic method object representing **multiple Java overloads**. On the first `CALL` seeing argument `"abc"`, the linker selects `join(String)`; on the next call seeing `Integer.valueOf(3)`, the linker can relink or select target `join(int)` according to runtime values and conversion rules.

In other words:

```text
CALL site: (callable, receiver, Object argument) -> Object
       |
       +-- runtime argument String  -> join(String)
       |
       +-- runtime argument Integer -> unbox -> join(int)
       |
       +-- runtime argument Object  -> no applicable overload
                                      -> NoSuchMethodException (example)
```

Do not equate `callSite.type()` with the signature of every member the linker will select. The `MethodType` of the call site remains fixed, while the target is relinked depending on guards and actual argument classes. A set of converters provided by a language runtime can make the set of applicable overloads broader or different; therefore, you should test conversion types, ambiguity, and null.

**Explicit signature selection:** `GET:METHOD:join(String)` pre-selects `join(String)`. The `BeansLinker` Javadoc allows names in explicit signature form, such as `parseInt(String,int)`; simple type names are generally accepted when unambiguous, while fully qualified names are needed when two types share the same simple name.

**Varargs:** `BeansLinker` supports calling Java varargs methods and constructors. However, not every overloaded/varargs selection matches how the Java compiler resolves overloads at compile time, because runtime value/type conversions may differ. Test cases with overloads taking `Object`, primitive vs wrapper, null, varargs, and error results.

## 9. When you need to control linkers and conversions

`DynamicLinkerFactory` allows configuring the list of `GuardingDynamicLinker`s:

1. **Prioritized linkers:** give your language runtime's object model priority.
2. **Auto-discovered linkers:** if there are `GuardingDynamicLinkerExporter` providers loaded by `ServiceLoader`.
3. **Fallback linkers:** includes `BeansLinker` by default if you have not changed this configuration.

When building a JavaScript-like runtime or a custom DSL, you can place linkers for the language's objects first, so that ordinary Java objects fall through to `BeansLinker`. Do not call `BeansLinker` directly for everything when the system needs multiple languages/coercion policies; `DynamicLinker` is the coordinator.

### 9.1. `setFallbackLinkers` and configuration errors

If you replace the fallback set with a list **that does not contain `BeansLinker`**, operations that previously worked with JavaBeans may no longer have any supporting linker. In that case, `NoSuchDynamicMethodException` can appear even for real public Java members.

Therefore, when you see this exception:

- Check the **operation**: have you chosen the right namespace/property/method/element?
- Check the **receiver**: what class is it, and is it actually `StaticClass` when you want `NEW` or a static member?
- Check the **linker chain**: is the default `BeansLinker` still present? Is a custom linker shadowing the fallback?
- Check the **`Lookup`** in `CallSiteDescriptor`: are permissions sufficient for caller-sensitive methods or JPMS access?
- Check the **`MethodType`**: `GET:METHOD` typically returns a dynamic method object, and `CALL` needs the receiver and arguments of the right types.
- Check the **converters**: a missing conversion makes the overload inapplicable, though the final error may be `NoSuchMethodException`/`ClassCastException` rather than always `NoSuchDynamicMethodException`.

Do not "fix" this by calling `setAccessible(true)` on every member. Dynalink has its own lookup/guards/module mechanisms; abusing reflection is neither a general nor a safe solution.

### 9.2. `MissingMemberHandlerFactory` must be an explicit policy

If a language wants a nonexistent `GET` operation to return `undefined`, design a proper sentinel or fallback according to the contract. Do not return `null` indiscriminately for `GET`, `SET`, `CALL`, and `NEW` — doing so can mask programming errors or access-control errors.

When adding a missing-member handler, test separately:
- reading a nonexistent property;
- calling a nonexistent method;
- a real getter that returns `null`;
- a real method receiving wrong arguments;
- a non-public member;
- a `null` receiver and types that do not support the operation.

These cases differ in purpose and should lead to different outcomes in many languages.

## 10. Layer-by-layer diagnostic checklist

| Question | How to check | If there is an issue |
| --- | --- | --- |
| Does the operation have the right namespace? | Print `descriptor.getOperation()` | Do not mix up `PROPERTY` with `METHOD` |
| Does `MethodType` match the operation? | Print `descriptor.getMethodType()` or `handle.type()` | Fix the count/types of receiver, name, value, return |
| What is the actual receiver? | `receiver.getClass()` if non-null | Use the right Java object or `StaticClass` |
| Is the member public and visible from the caller? | Compare Java API visibility, module exports | Do not assume private members are always accessible |
| Does the linker support Java objects? | Check `DynamicLinkerFactory` configuration | Keep `BeansLinker` fallback when needed |
| Is there an overload accepting the actual argument types? | Check Java method signatures; `GET:METHOD`/`CALL` | Valid conversion or explicit signature |
| Is there a conversion from source type to target type? | Check `LinkerServices.canConvert`/custom strategy | Do not auto-parse numeric `String` without a converter |
| At which stage was the exception raised? | Stack trace, cause, and exception type | Distinguish link, adapt, `invokeExact`, target execution |
| Was the guard invalidated when the receiver changed? | Observe different receiver types and cache policy | Choose `ChainedCallSite`/appropriate cache strategy |
| Did the application's own method throw the error? | Trace stack trace into the actual Java method | Do not change the linker when the error is business logic |

**Debug in minimal order**: record the operation, `MethodType`, receiver runtime class, method signatures/candidate conversions, and exception/cause. Do not overuse logging when scripts run with sensitive data; log metadata and mask/hide confidential values.

Useful API inspection example:

```java
System.out.println("type=" + getColor.type());
System.out.println("properties="
        + BeansLinker.getReadableInstancePropertyNames(ColorBean.class));
System.out.println("methods="
        + BeansLinker.getInstanceMethodNames(ColorBean.class));
```

This snippet is a **contextual** example, using the `getColor` variable and `ColorBean` class already present in the program in section 7. The returned `Set` of public names may also include inherited members; you should not hard-code the entire list as fixed expected output.

## 11. Application design: use the right tool, do not "make everything dynamic"

**Use Dynalink when** you are writing a runtime/DSL or a linker operating on objects whose types are unknown at compile time, need dispatch across multiple object models, want guards/relinking, and have overload/conversion policies.

**Do not necessarily use Dynalink when** Java code already knows `ColorBean` and only needs to call `bean.getColor()`: the Java compiler/JVM will use ordinary method invocation, which is simpler. Dynalink is not a default replacement for all reflection or `MethodHandle` usage.

### 11.1. Return types, null, and exceptions

The result of a dynamic property/method call can be `null` if the member actually returns null or a fallback intentionally does so. When client code must unbox a primitive, null can lead to `NullPointerException`. This alone does not prove the linker failed to find the method.

If the Java target throws a business exception, do not automatically turn every error into `NoSuchDynamicMethodException`; this exception means **failed to link the call site**, not "execution failed in general".

### 11.2. Concurrency and caching

A call site can relink when encountering new types. Holding a dynamic invoker `MethodHandle` does not mean every mutable Java object is thread-safe. The state of `ColorBean`, `List`, `Map`, and custom linkers still requires its own concurrency discipline (locks, immutable snapshots, concurrent collections...). `ChainedCallSite` can improve caching for multiple receiver classes, but it is not a synchronization mechanism for object state.

### 11.3. Security and access control

Dynamic linking allows scripts/dynamic languages to **discover and invoke public Java methods** according to the linker's capabilities; it is not a sandbox. If exposing objects with sensitive methods to untrusted scripts, the policy must restrict objects/members rather than relying on the caller not knowing method names. `MethodHandles.Lookup` can carry different privileges; caller-sensitive methods require a sufficiently privileged lookup per the `BeansLinker` Javadoc. A production runtime should check trust boundaries, JPMS exports, deserialization, resource limits, and auditing, while restricting the exposed object graph.

## 12. Self-check exercises

**A.** Are `GET:PROPERTY:color` and `GET:METHOD:color` equivalent? If you want to call `bean.join("x")` via Dynalink, which operations are involved?

**B.** `SET:PROPERTY:count` has target setter `setCount(int)`. The call-site value descriptor is type `short`, passing `(short) 7`. Is this valid? Why?

**C.** For the same `int` setter, `"7"` is passed as `Object`. Does the API promise to parse the string into an int? What error occurs in the example?

**D.** `GET:METHOD:absent` on a JavaBean that has no such method. With the default `BeansLinker` and no custom fallback, what type of error appears at invocation?

**E.** `GET:METHOD:join` succeeds and returns a dynamic method object. `CALL` passes `new Object()` while only `join(String)` and `join(int)` exist. Why can this be `NoSuchMethodException` rather than `NoSuchDynamicMethodException`?

**F.** Is using `StandardOperation.NEW` on `ColorBean.class` or a `ColorBean` instance the right way to do the same thing as `NEW` on `StaticClass.forClass(ColorBean.class)`?

**G.** `getColor` has `MethodType` `(Object)Object`. What error can occur if you call `getColor.invokeExact((Object) bean);` as a statement? Why?

**H.** `record Box(String title)` has no `getTitle()` method. Can `BeansLinker` expose `title` as a property getter?

**I.** A custom language runtime just replaced the fallback linkers, removing `BeansLinker`, and Java object operations started failing. What should you check before concluding the JavaBean class is broken?

**J.** `List` and `Map` both use the `ELEMENT` namespace. Are keys/indices and remove semantics automatically identical? Why?

### Answers

- **A:** No. `PROPERTY` reads a property getter/field; `METHOD` retrieves a dynamic method object. To call `join`, use `GET:METHOD:join` followed by `CALL(callable, receiver, args...)`.
- **B:** Yes, per the example: primitive widening `short` → `int` is a valid conversion; `BeansLinker` selects the setter.
- **C:** No. `"7"` is not automatically parsed into an `int`; the test example throws `ClassCastException`.
- **D:** `NoSuchDynamicMethodException` at invoke time, if no linker can link the operation.
- **E:** The dynamic method object already exists; the error occurs when selecting an overload for an incompatible argument, which in the example is `NoSuchMethodException`.
- **F:** No. For static methods/constructors, use `StaticClass`. Java `Class<?>` is an ordinary object; `NEW` on a Java instance has no constructor meaning under `BeansLinker`.
- **G:** `WrongMethodTypeException` because the `invokeExact` descriptor in a statement context returns `void`, which differs from the handle's `Object` return type.
- **H:** Yes. Java 17 `BeansLinker` exposes public record component accessors as property getters.
- **I:** Check `DynamicLinkerFactory`, prioritized/autoloaded/fallback linkers, and the removal of `BeansLinker`; also check the operation/`Lookup`/conversions.
- **J:** No. `List` uses an index and `Map` uses a key; `REMOVE:ELEMENT` has the semantics of the respective container, and does not turn an array into a structure whose elements can be removed.

## 13. Official Java 17 documentation

- [Oracle JDK 17 — module `jdk.dynalink`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/module-summary.html): Dynalink model, `RelinkableCallSite`, object property operations, and fallback Java linker.
- [Oracle JDK 17 — `BeansLinker`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/beans/BeansLinker.html): JavaBean properties, public fields, records, arrays/List/Map, dynamic methods, overload resolution, missing members.
- [Oracle JDK 17 — `StaticClass`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/beans/StaticClass.html): static facet and constructor operation.
- [Oracle JDK 17 — `StandardOperation`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/StandardOperation.html): `GET`, `SET`, `REMOVE`, `CALL`, and `NEW` with their signatures.
- [Oracle JDK 17 — `DynamicLinkerFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html): prioritized, autodiscovered, and fallback linkers, conversion strategy.
- [Oracle JDK 17 — `NoSuchDynamicMethodException`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/NoSuchDynamicMethodException.html): runtime exception when no available linker can link the call site.
- [Oracle JDK 17 — `LinkerServices`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/LinkerServices.html): `asType`, `canConvert`, `compareConversion`, and language-specific converter support.
- [Oracle JDK 17 — `MethodHandle.invokeExact`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): signature-polymorphic invocation and `WrongMethodTypeException`.

**Key takeaway:** `BeansLinker` helps Dynalink link operations on Java objects to getters/setters, methods, elements, and constructors. `LinkerServices` can adapt types and use runtime converters, but does not promise arbitrary type coercion. **`NoSuchDynamicMethodException` means the dynamic operation could not be linked at invocation**; overload selection errors, argument conversion errors, wrong `invokeExact` signatures, or errors from the actual Java method must be diagnosed separately.
