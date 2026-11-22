# 6.7 Creating getters, setters, and converting a Method or Constructor to a handle with unreflect

In Java, a `MethodHandle` is a strongly typed reference to an executable operation: invoking a method, instantiating an object, reading or writing a field. `MethodHandles.Lookup` provides two important ways to create handles:

- **Direct lookup by class + name + type**: `findGetter`, `findSetter`, `findStaticGetter`, `findStaticSetter`, `findVirtual`, `findStatic`, and `findConstructor`.
- **Converting from existing Reflection metadata**: `unreflectGetter(Field)`, `unreflectSetter(Field)`, `unreflect(Method)`, and `unreflectConstructor(Constructor<?>)`.

This lesson focuses on how to **create a getter/setter for a field** and **convert a Field, Method, or Constructor into a MethodHandle**, then use the `MethodType`, receiver, return type, access permissions, and errors properly. This is an essential skill in mappers, serializers, DI frameworks, plugin invokers, or systems that execute code based on runtime configuration.

Goal: when holding a `Field`, `Method`, or `Constructor<?>` in hand, you know how to choose the appropriate `unreflect` operation, understand the resulting handle signature accurately, and avoid mistakes such as passing a receiver into a static getter, assuming a setter returns a value, or calling `invokeExact` with a mismatched type.

## 1. Core mindset: A MethodHandle has its own MethodType

A `MethodHandle` does not carry a method name for the caller to select an overload at each call site. When created, it has **one fixed `MethodType`**: a list of parameter types and one return type. Read it with `handle.type()`.

For example, given a class:

```java
class Counter {
    public int count;
    public static int total;
    public Counter(String label, int count) { this.count = count; }
    public String describe(String prefix) { return prefix + count; }
}
```

This is an illustrative declaration, not a standalone Java file. The corresponding operations have handle types:

| Operation | Handle's `MethodType` | Arguments when invoking |
| --- | --- | --- |
| Read instance `count` | `(Counter)int` | One `Counter` receiver, returns `int` |
| Write instance `count` | `(Counter,int)void` | Receiver then new value, returns no result |
| Read `static total` | `()int` | No receiver, no parameters |
| Write `static total` | `(int)void` | Only the new value |
| Call `describe(String)` | `(Counter,String)String` | Receiver before original parameter |
| Call static method `static String category(int)` | `(int)String` | No receiver |
| Call constructor `Counter(String,int)` | `(String,int)Counter` | Constructor arguments; **returns new instance** |

For an instance method, the receiver becomes the **first parameter** in the handle. For a constructor, `java.lang.reflect.Constructor` represents the object construction operation; the resulting handle returns the **instantiated class type**, unlike the `<init>` constructor descriptor in the JVM which has a `void` return type.

**Note:** `MethodHandle.type()` uses actual `Class<?>` objects; `(Counter,int)void` is the friendly string representation of `MethodType.toString()`. When programming without relying on strings, use `type().parameterType(i)`, `returnType()`, and `parameterCount()`.

## 2. Creating getters and setters when knowing the class, field name, and field type

Four `Lookup` methods are dedicated to field operations by name:

| API | Targets | Typical handle type |
| --- | --- | --- |
| `findGetter(C.class, "f", T.class)` | Instance field `T f` | `(C)T` |
| `findSetter(C.class, "f", T.class)` | Writable instance field `T f` | `(C,T)void` |
| `findStaticGetter(C.class, "f", T.class)` | Static field `static T f` | `()T` |
| `findStaticSetter(C.class, "f", T.class)` | Writable static field `static T f` | `(T)void` |

In the table, `C` is the actual receiver type of the handle (typically the class type you look up; in some `protected` cases it can be narrower due to access rules), and `T` is the exact type of the field.

Direct example with a class having public fields:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle getCount =
        lookup.findGetter(Counter.class, "count", int.class);
MethodHandle setCount =
        lookup.findSetter(Counter.class, "count", int.class);
MethodHandle getTotal =
        lookup.findStaticGetter(Counter.class, "total", int.class);
MethodHandle setTotal =
        lookup.findStaticSetter(Counter.class, "total", int.class);
```

The snippet above uses the illustrative `Counter` class along with imports `MethodHandle`, `MethodHandles`. Handle lookup methods check permissions **at creation time**. If the field name or type is wrong, `NoSuchFieldException` is the typical case; if permissions are missing, static/instance is mismatched, or you attempt to find a setter for a `final` field using `findSetter`/`findStaticSetter`, `IllegalAccessException` can be thrown.

There is no method named `findFieldGetter` in this API; use the exact four names in the table.

### 2.1. The field type must be exact

The field `int count` is looked up with `int.class`, **not** with `Integer.class` or `Object.class`. Similarly, `String[] names` must use `String[].class`, not `String.class`. This is a member lookup by declared type, not an overload resolution mechanism via assignment compatibility.

If you already have a `Field`, a more reliable approach is to get `field.getType()` directly or call `unreflectGetter(field)`, because you do not need to re-enter the name and type manually.

### 2.2. Difference between reading/writing instance and static fields

For an instance field, the receiver is the first parameter: `getCount.invokeExact(counter)` expects a result of type `int`, and `setCount.invokeExact(counter, 7)` returns `void`. For a static field, no receiver may be passed: `getTotal.invokeExact()` and `setTotal.invokeExact(99)`.

Invoking a static field handle may trigger class initialization if the class has not yet been initialized. `MethodHandle` does not turn a field into a virtual property or call a JavaBeans "getter" method; it accesses the corresponding field directly, following Java's field semantics.

## 3. From Field to getter/setter: unreflectGetter and unreflectSetter

Suppose a library has already scanned `Field` objects using Reflection. Instead of extracting the name and looking it up again, convert that metadata directly into a handle:

```java
Field field = Counter.class.getField("count");
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle getter = lookup.unreflectGetter(field);
MethodHandle setter = lookup.unreflectSetter(field);
```

This is an illustrative snippet, not a standalone program. `getField` finds public fields (including matching public inherited fields); `getDeclaredField` finds fields declared directly on the class, including private ones, but **merely finding it does not mean having access permission**.

The `unreflectGetter` and `unreflectSetter` APIs:

- Use an existing `Field` directly. Do not require entering the name or data type a second time.
- Create a handle whose type depends on `field.getType()`, `Modifier.isStatic(field.getModifiers())`, and the declaring class type of the field.
- Check `Lookup` permissions at handle creation time if the `Field`'s suppress-access flag is not enabled. The `setAccessible` flag does not guarantee bypassing module boundaries or rules for final fields.
- A getter can read `final` fields as well if permissions are sufficient. A setter is only created successfully when **access legality and finality allow writing**. For `static final` fields, a writable setter cannot be created through this path.

**Selection cue**: if you have a `Field` from a scanning/annotation/serialization tool, use `unreflectGetter`/`unreflectSetter`; if you only have the class, name, and exact type, use `findGetter`/`findSetter`. Both ultimately produce the corresponding field read/write operation, but the accessible flag rules of an already-adjusted `Field` differ from looking up by name.

### 3.1. A final field is not a normal setter

`findSetter` and `findStaticSetter` reject `final` fields. `unreflectSetter` only has a narrow exception if a `Field` satisfies the write conditions under `Field.set` and has been granted appropriate access. That is not a general license to mutate immutable state: some final fields cannot be written through Reflection, such as **static final**, final fields in a **record**, and fields in a **hidden class**. Mutating final fields after initialization also carries risks regarding semantics, JVM optimizations, and consistency.

When building a mapper or DI, prefer constructors to assign final state; only create setters for genuinely writable fields. If you need synchronized/atomic memory operations, look at `VarHandle` rather than expecting a getter/setter handle to provide `compareAndSet` on its own.

## 4. Converting Method and Constructor to handles

### 4.1. unreflect(Method)

When you already have an exact `java.lang.reflect.Method`, call:

```java
Method reflected = Counter.class.getMethod("describe", String.class);
MethodHandle handle = MethodHandles.lookup().unreflect(reflected);
```

If `describe` is an instance method `String describe(String prefix)`, the handle has type `(Counter,String)String`. If the method is static, **there is no receiver**. For overridable instance methods, `unreflect(Method)` preserves normal **dynamic dispatch**: the implementation is selected based on the receiver at call time, rather than freezing the implementation to a parent-type `Method` object.

`unreflect(Method)` is the natural choice when an API has already returned a `Method` (from `getMethod`, `getDeclaredMethod`, annotation scanning, or overload selection). If you only know the class + name + `MethodType`, `findVirtual`/`findStatic` are usually more direct and clearer.

**Invocation difference:** `Method.invoke` returns `Object`, boxes primitives, and wraps exceptions **thrown by the target method** in `InvocationTargetException`. `MethodHandle.invokeExact`/`invoke` have stronger signatures; exceptions from the target method **propagate directly**, without automatic wrapping like Reflection.

### 4.2. unreflectConstructor(Constructor<?>)

`java.lang.reflect.Constructor<?>` describes a specific constructor, not a `Method`, and must not be passed to `unreflect(Method)`. Use:

```java
Constructor<Counter> ctor =
        Counter.class.getConstructor(String.class, int.class);
MethodHandle make = MethodHandles.lookup().unreflectConstructor(ctor);
```

For the constructor `Counter(String,int)`, `make.type()` is `(String,int)Counter`. Invoking the handle creates a **new Counter**. There is no leading receiver on a constructor, because no instance exists yet; unlike `(Counter,String)String` of an instance method.

Compared to `Lookup.findConstructor(Counter.class, MethodType.methodType(void.class, String.class, int.class))`, `unreflectConstructor` fits when you already have a `Constructor` object. Do not confuse them: the `MethodType` argument passed to `findConstructor` uses **return type `void`**, whereas the `MethodType` of the returned handle is `Counter`.

### 4.3. Quick conversion map

| Available metadata or facts | Choose API | Target element invoked |
| --- | --- | --- |
| `Field f` for reading | `lookup.unreflectGetter(f)` | Reads instance/static field |
| `Field f` for writing | `lookup.unreflectSetter(f)` | Writes modifiable instance/static field |
| Instance field name + type | `lookup.findGetter` / `lookup.findSetter` | Reads/writes instance field |
| Static field name + type | `lookup.findStaticGetter` / `lookup.findStaticSetter` | Reads/writes static field |
| `Method m` | `lookup.unreflect(m)` | Invokes that exact method |
| `Constructor<?> c` | `lookup.unreflectConstructor(c)` | Creates an object using that constructor |
| Method name + signature | `lookup.findVirtual` or `lookup.findStatic` | Selects member via `MethodType` |
| Type + constructor signature | `lookup.findConstructor` | Creates instance by signature |

Do not use `unreflectSpecial` as a default replacement for `unreflect`. `unreflectSpecial(method, specialCaller)` mimics `invokespecial` semantics (which can bypass overrides) and requires special caller/permissions, appropriate only when a special invocation is genuinely intended.

## 5. Complete Java 17+ example: getter, setter, method, constructor

Create a file **`LookupHandlesDemo.java`** with the full content below:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class LookupHandlesDemo {
    public static class Counter {
        public String label;
        public int count;
        public static int total = 10;
        public final String id;

        public Counter(String label, int count) {
            this.label = label;
            this.count = count;
            this.id = "X-" + label;
        }

        public String describe(String prefix) {
            return prefix + label + ":" + count;
        }

        public static String category(int number) {
            return "C" + number;
        }

        public String explode() {
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle getter = lookup.findGetter(Counter.class, "count", int.class);
        MethodHandle setter = lookup.findSetter(Counter.class, "count", int.class);

        Field field = Counter.class.getField("count");
        MethodHandle reflectedGetter = lookup.unreflectGetter(field);
        MethodHandle reflectedSetter = lookup.unreflectSetter(field);
        MethodHandle staticGetter = lookup.findStaticGetter(Counter.class, "total", int.class);
        MethodHandle staticSetter = lookup.findStaticSetter(Counter.class, "total", int.class);

        MethodHandle constructor = lookup.unreflectConstructor(
                Counter.class.getConstructor(String.class, int.class));
        Method method = Counter.class.getMethod("describe", String.class);
        MethodHandle described = lookup.unreflect(method);
        MethodHandle staticMethod = lookup.unreflect(Counter.class.getMethod("category", int.class));

        Counter counter = (Counter) constructor.invokeExact("alpha", 2);
        System.out.println("ctor type=" + constructor.type());
        System.out.println("getter type=" + getter.type());
        System.out.println("setter type=" + setter.type());
        System.out.println("static getter type=" + staticGetter.type());
        System.out.println("static setter type=" + staticSetter.type());
        System.out.println("method type=" + described.type());
        System.out.println("before=" + (int) getter.invokeExact(counter));
        setter.invokeExact(counter, 7);
        System.out.println("after=" + (int) reflectedGetter.invokeExact(counter));
        reflectedSetter.invokeExact(counter, 9);
        System.out.println("after unreflect setter=" + (int) getter.invokeExact(counter));
        System.out.println("method=" + (String) described.invokeExact(counter, "item="));
        System.out.println("static method=" + (String) staticMethod.invokeExact(4));
        System.out.println("static before=" + (int) staticGetter.invokeExact());
        staticSetter.invokeExact(99);
        System.out.println("static after=" + (int) staticGetter.invokeExact());

        MethodHandle boundGetter = getter.bindTo(counter);
        System.out.println("bound type=" + boundGetter.type());
        System.out.println("bound value=" + (int) boundGetter.invokeExact());

        MethodHandle objectGetter = getter.asType(MethodType.methodType(Object.class, Object.class));
        System.out.println("adapted=" + objectGetter.invokeExact((Object) counter));

        try {
            lookup.findSetter(Counter.class, "id", String.class);
        } catch (IllegalAccessException exception) {
            System.out.println("final setter=" + exception.getClass().getSimpleName());
        }

        MethodHandle exploding = lookup.unreflect(Counter.class.getMethod("explode"));
        try {
            String unused = (String) exploding.invokeExact(counter);
        } catch (IllegalStateException exception) {
            System.out.println("exception=" + exception.getClass().getSimpleName()
                    + ":" + exception.getMessage());
        }
    }
}
```

Compile and run from the directory containing the file using JDK 17 or later:

```bash
javac --release 17 LookupHandlesDemo.java
java LookupHandlesDemo
```

Verified `stdout` output:

```text
ctor type=(String,int)Counter
getter type=(Counter)int
setter type=(Counter,int)void
static getter type=()int
static setter type=(int)void
method type=(Counter,String)String
before=2
after=7
after unreflect setter=9
method=item=alpha:9
static method=C4
static before=10
static after=99
bound type=()int
bound value=9
adapted=9
final setter=IllegalAccessException
exception=IllegalStateException:boom
```

### 5.1. What does each group of results prove?

1. **Constructor handle**: `unreflectConstructor` takes `Constructor<Counter>` and creates handle `(String,int)Counter`. Casting the result of `invokeExact` to `Counter` makes the call-site signature match.
2. **Instance field**: `findGetter` and `unreflectGetter` both read the same field; `findSetter` and `unreflectSetter` both write the same field. The output `before=2` → `after=7` → `after unreflect setter=9` verifies proper operation.
3. **Static field**: `staticGetter.type()` is `()int`, `staticSetter.type()` is `(int)void`; no receiver appears. After setting `99`, reading it back returns `99`.
4. **Method**: instance `unreflect(Method)` takes `Counter` before `String`, whereas the static method takes only `int`.
5. **Bind receiver**: `getter.bindTo(counter)` pre-binds the receiver and produces a parameterless handle `()int`. This is not a static getter; it remains bound to the specific `counter`.
6. **Type adaptation**: `asType(MethodType.methodType(Object.class, Object.class))` turns the handle type into `(Object)Object`. When invoked, the runtime casts `Object` to `Counter` and boxes `int` to `Integer` if valid; the output prints `9`.
7. **Final field**: `findSetter` for `id` throws `IllegalAccessException` immediately at creation time. There is no valid path via `findSetter` even though `id` is public.
8. **Exception**: the `explode` method throws `IllegalStateException("boom")`; when invoked through the handle, `IllegalStateException` is caught directly. There is no need to unwrap `InvocationTargetException` as with `Method.invoke`.

**Syntax detail of `invokeExact`:** in the line `System.out.println((int) getter.invokeExact(counter))`, the `(int)` cast is part of the compile-time signature that the JVM checks. For an `int` getter, writing `(long) getter.invokeExact(counter)` would require the handle to have return type `long` and cause `WrongMethodTypeException`, even though normal Java can widen `int` to `long`. To perform controlled conversions, use `invoke` or `asType` properly.

## 6. Accessing private members and Lookup permissions

`getDeclaredField("code")`, `getDeclaredMethod("reveal", String.class)`, or `getDeclaredConstructor(String.class)` only provide **metadata**, without granting automatic privileges. A `Lookup` carries the identity of the lookup-creating class and a set of access permissions. When creating a method handle, access permissions are checked **at creation time**; a created handle is a capability that can be invoked later, so handles to private members should not be shared with untrusted code.

### 6.1. privateLookupIn for an eligible target class

`MethodHandles.privateLookupIn(targetClass, callerLookup)` can create a lookup with private access on the target class if the module relationship, the caller's `PRIVATE`/`MODULE` access, and relevant package `opens` requirements allow it. This is not a way to bypass all security restrictions. Across different modules, the target's package needs to be opened to the calling module as required.

The following standalone example **`PrivateLookupDemo.java`** works within the same module/classpath, using a nested class to demonstrate private constructor, field, and method:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class PrivateLookupDemo {
    public static class SecretBox {
        private String code;

        private SecretBox(String code) {
            this.code = code;
        }

        private String reveal(String prefix) {
            return prefix + code;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup privileged = MethodHandles.privateLookupIn(
                SecretBox.class, MethodHandles.lookup());
        Field field = SecretBox.class.getDeclaredField("code");
        Constructor<SecretBox> ctor = SecretBox.class.getDeclaredConstructor(String.class);
        Method method = SecretBox.class.getDeclaredMethod("reveal", String.class);

        MethodHandle getter = privileged.unreflectGetter(field);
        MethodHandle setter = privileged.unreflectSetter(field);
        MethodHandle make = privileged.unreflectConstructor(ctor);
        MethodHandle reveal = privileged.unreflect(method);

        SecretBox box = (SecretBox) make.invokeExact("hidden");
        System.out.println("getter type=" + getter.type());
        System.out.println("before=" + (String) getter.invokeExact(box));
        setter.invokeExact(box, "visible");
        System.out.println("after=" + (String) getter.invokeExact(box));
        System.out.println("method=" + (String) reveal.invokeExact(box, "code="));
    }
}
```

```bash
javac --release 17 PrivateLookupDemo.java
java PrivateLookupDemo
```

`stdout`:

```text
getter type=(SecretBox)String
before=hidden
after=visible
method=code=visible
```

The program above does not need to call `setAccessible(true)` because it uses a `Lookup` with access to `SecretBox`. `privateLookupIn` can throw `IllegalAccessException` if the example is placed into a module that does not open the appropriate package. In real application code, grant access intentionally (public API or appropriate `opens`) and restrict distributing privileged lookups/handles.

### 6.2. Comparing publicLookup, lookup, and privateLookupIn

| Lookup creation | Meaning |
| --- | --- |
| `MethodHandles.publicLookup()` | Limited public access, suitable for public APIs accessible from anywhere per module rules |
| `MethodHandles.lookup()` | Permissions based on the **caller class** where `lookup()` is actually called; can access private members of the caller per rules |
| `MethodHandles.privateLookupIn(Target.class, callerLookup)` | Requests a lookup with private access on `Target`, subject to caller capabilities and module constraints |

**Two important notes:**

- Calling `MethodHandles.lookup()` inside a helper does not make it a lookup of the target class passed into the helper. To obtain permissions for another target, use the appropriate mechanism; avoid handing a privileged `Lookup` to external plugins.
- `Field.trySetAccessible()`/`setAccessible(true)` is Reflection's own access-suppression mechanism and can fail due to modules. A `Field` whose accessible flag has been validly enabled can affect `unreflectGetter`/`unreflectSetter`, but it does not make every final field writable, nor does it grant the caller general permissions over all members in a module.

## 7. invokeExact, invoke, asType, and invokeWithArguments

To use a handle, one must distinguish **the handle's type** from **the invocation expression's type in source code**.

### 7.1. invokeExact requires an exact signature match

Suppose `MethodHandle getCount` has type `(Counter)int`:

```java
int count = (int) getCount.invokeExact(counter);
```

The snippet above references variables from the `LookupHandlesDemo` example. The receiver argument must have **exact compile-time type `Counter`**, and the return value must also be used as type `int`. Writing `Object value = getCount.invokeExact(counter);` makes the call site expect `Object` instead of `int` and throws `WrongMethodTypeException` at runtime. Similarly, a setter has return type `void`, so it is usually invoked as a statement:

```java
setCount.invokeExact(counter, 42);
```

When types are unknown at compile time, `invokeExact` does not infer from `handle.type()` automatically; you need to design an appropriate adapter or dynamic API.

### 7.2. invoke allows limited type conversions

`invoke` can apply conversions supported by `MethodHandle.asType`, such as boxing/unboxing and certain valid primitive conversions. It **does not** arbitrarily change parameter order/count, and does not convert the string `"42"` into an integer like a business parser.

`asType` builds a handle with a different `MethodType` according to valid conversions. In the example, `getter.asType((Object)Object)` turns a typed setter/getter into a general-purpose callable for a framework; the runtime will still check the actual receiver before accessing the field.

### 7.3. invokeWithArguments for dynamic lists

`invokeWithArguments(Object...)` is convenient when the number and types of arguments can only be assembled into an `Object[]` at runtime. It incurs adaptation/boxing overhead and does not guarantee all arguments are valid. Do not treat it as the default choice for hot call paths whose signatures are already known.

`MethodHandle` also supports adapters such as `bindTo` to bind a receiver, `asSpreader` to accept an array of arguments, and `asCollector` for the corresponding array operation. Use them only when there is a concrete type contract, avoiding ad-hoc "shortcuts" based on arbitrary casts.

### 7.4. Reflection and handles have different error paths

| Scenario | Traditional Reflection | Method handle |
| --- | --- | --- |
| Invoke instance method | `method.invoke(receiver, args...)` | Receiver is the handle's first parameter |
| Invoke constructor | `constructor.newInstance(args...)` | `handle.invokeExact(args...)` returns typed instance |
| Read/write field | `field.get(receiver)` / `field.set(receiver, value)` | Getter/setter handle with specific `MethodType` |
| Access check | Checked at invocation time per Reflection rules; has suppress-access flag | Checked when creating handle from `Lookup` |
| Exception thrown by target code | `InvocationTargetException` wraps exception from method/constructor | Target exception propagates directly |
| Mismatched invocation type | `IllegalArgumentException`, Reflection-related errors | `WrongMethodTypeException`, `ClassCastException`, or related conversion errors |
| Return type | `Object`, primitives are boxed | Per `MethodType`, can be primitive or `void` |

## 8. Using in a runtime data mapper

When writing a serializer/mapper, you typically discover fields and annotations once, create the corresponding handles, and reuse them. Workflow:

1. **Select fields** according to a clear policy: public or declared, instance/static, whether read or write is needed, whether private is allowed.
2. **Check permissions** using an appropriate lookup. You can use `publicLookup` for public APIs or `privateLookupIn` when the application is genuinely granted permission.
3. **Create a getter** with `unreflectGetter(field)`; create a setter only if the field is writable and the operation belongs to the data contract. For `final` fields, prefer a constructor or factory to create the instance in the right state.
4. **Read `getter.type()` / `setter.type()`** to store the signature. Choose typed invocation or an `asType` adapter, preserving receiver/static rules.
5. **Cache handles** when reused many times for the same metadata, but remember that class loaders can change in plugin/hot-reload applications; a cache without lifecycle control can keep classes and loaders alive unintentionally.
6. **When a Method/Constructor is already obtained from prior selection**, call `unreflect`/`unreflectConstructor` instead of looking up by name again. Separate creation-time exceptions from execution-time exceptions.

A skeleton snippet creating a getter for a field selected from metadata:

```java
static MethodHandle makeReadable(Field field, MethodHandles.Lookup lookup)
        throws IllegalAccessException {
    return lookup.unreflectGetter(field);
}
```

This is an illustrative method requiring imports `Field`, `MethodHandle`, and `MethodHandles`; it **does not elevate permissions on its own**. In a real application, the caller decides which fields are accessed and which Lookup is permitted.

### 8.1. When should you use VarHandle?

If the problem only needs reading/writing a field through a handle, `unreflectGetter` and `unreflectSetter` are direct. If you want concurrent update operations or memory ordering (for example, volatile get/set, compare-and-set, get-and-add, acquire/release), consider `VarHandle`, created via `findVarHandle`, `findStaticVarHandle`, or `unreflectVarHandle`. Do not write `get` followed by `set` yourself as an atomic operation when there is data contention.

## 9. Special cases and common errors

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| `NoSuchFieldException` | Wrong field name, wrong type, calling instance lookup for static or vice versa needs classification | Check `getDeclaredFields()`, `field.getType()`, `Modifier.isStatic` |
| `IllegalAccessException` at `findGetter/unreflect` | Lookup lacks permission for member or module | Check modifiers, lookup class, exports/opens; design valid access permissions |
| `IllegalAccessException` at `findSetter` | `final` field or inaccessible | Do not attempt to create a setter for final; initialize via constructor |
| `WrongMethodTypeException` at `invokeExact` | Call site has wrong receiver, parameter, or return type | Print `handle.type()`, compare against the actual compile-time types of the call expression |
| `ClassCastException` when using adapted handle | Actual object cannot be cast to field/receiver type | Validate inputs and metadata types before invoking |
| `NullPointerException` when calling instance getter | Null receiver | Pass a valid instance, do not use null for an instance field |
| Static read handle has an "extra" receiver | Confusing static signature with instance signature | `staticGetter.type()` has no receiver |
| Setter used as a value-returning function | Setter handle has `void` return type | Call as a statement or adapt validly if the framework needs a different result |
| `InvocationTargetException` only appears in Reflection flow | Reflective Method/Constructor wrapping | With handles, catch the original exception directly; do not expect a wrapper |
| Reading private field works but unreflect fails | `getDeclaredField` retrieves metadata, does not grant execution permission | Use a Lookup with appropriate permissions, check module package opens |
| Handle changes behavior when passed to another plugin | Handle carries capability granted at creation time; data/receiver may differ | Control where handles are stored/shared, class loaders, and cache lifecycle |
| `findVirtual` cannot find constructor | A constructor is not a virtual method named `"<init>"` for this API | Use `findConstructor` or `unreflectConstructor` |

**Do not swallow errors** by catching `Throwable` and ignoring it: when calling `MethodHandle.invokeExact`, the target method can throw checked/unchecked exceptions or errors. Separate handle creation errors (`NoSuchFieldException`, `NoSuchMethodException`, `IllegalAccessException`) from invocation errors (`WrongMethodTypeException`, original exceptions from target code). In standalone examples, `main throws Throwable` keeps syntax concise; in real production code, build an error-handling policy at appropriate boundaries.

## 10. Self-check exercises

**Exercise A.** Given `Field amount` of `long amount` in `Account`. A library already has `Field` and wants to create a getter. What must be called? What is the handle type?

**Answer:** `lookup.unreflectGetter(amount)`; typically type `(Account)long` if this is an instance field and there is no special receiver restriction due to protected access.

**Exercise B.** Field `static String mode`. Is using `findGetter(Setting.class, "mode", String.class)` correct?

**Answer:** Incorrect because this is a static field. Use `findStaticGetter` to get `()String`, or `unreflectGetter(field)` with the corresponding Field metadata.

**Exercise C.** Given `Method` for `String format(int width)` (instance) in `Report`. After `lookup.unreflect(method)`, what is the handle signature?

**Answer:** `(Report,int)String`. The receiver appears before `width`. If the method were static, only `(int)String` remains.

**Exercise D.** Given `Constructor<User>` taking (`String`, `int`). What handle type does `unreflectConstructor` return? Is a receiver needed?

**Answer:** `(String,int)User`; no receiver is needed. A new `User` is created when invoking the handle.

**Exercise E.** `MethodHandle getAge` has type `(Person)int`, but the code writes `Object age = getAge.invokeExact(person);`. Why does it fail?

**Answer:** The `invokeExact` call site requires an `Object` result type, which does not match the handle's `int`. Use `int age = (int) getAge.invokeExact(person);` or an adapter with an appropriate type.

**Exercise F.** A framework wants to modify `public final String id` using `findSetter`. Should it rely on `setAccessible` to force success?

**Answer:** No. `findSetter` rejects final fields; `unreflectSetter` is also very strictly restricted, especially for static final and fields in record/hidden classes. Design a constructor or factory to supply the right value at object creation time.

## JDK 17 reference documentation

- [`MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findGetter`/`findSetter`/`findStaticGetter`/`findStaticSetter`, `unreflect`, `unreflectGetter`, `unreflectSetter`, `unreflectConstructor`, access rules.
- [`MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, `asType`, `bindTo`, and `invokeWithArguments`.
- [`MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()`, and `privateLookupIn`.
- [`java.lang.reflect.Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): field type, modifiers, access, and restrictions on writing final fields.
- [`java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html) and [`Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): member metadata and differences compared to handles.
- [`VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): field operations with access modes, memory ordering, and atomic operations.

**Remember:** `findGetter`/`findSetter` fit when class–name–type are known; `unreflectGetter`/`unreflectSetter` fit when a `Field` is already available. `unreflect(Method)` converts a method, `unreflectConstructor(Constructor<?>)` converts a constructor into an instance-creating handle. Always read `handle.type()`, check receiver/static, only create setters on writable fields, and treat `Lookup` as intentionally granted access permission.
