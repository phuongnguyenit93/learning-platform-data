# 19.4 Keying Caches by `Class` and Signature; Avoiding Confusing Same-Named Types from Different Loaders

In Java systems using Reflection, `MethodHandle`, dynamic proxies, serializers, or plugin runtimes, looking up a method/constructor/field by name can be expensive if repeated many times. Caching lookup results is often helpful, but **keying the cache incorrectly can cause code to invoke the wrong member or confuse a type from another class loader**.

For example, two plugins both provide a class named `plugin.Greeter`, but each plugin runs with **its own defining `ClassLoader`**. The two classes have the same `Class.getName()`, the same bytecode, and the same signature text, yet **they are not the same runtime type**. A `Method` or `MethodHandle` found from a class in loader A cannot be treated as a method of the class defined by loader B.

**Core rule:** a resolution cache must use the **exact runtime `Class<?>` of the owner**, a **sufficiently precise signature**, the **operation kind** (static, virtual, constructor, field getter, etc.), and the **access/lookup policy boundary**. Never use only the class name, method name, or a descriptor string as the key.

This lesson builds a safe cache model in Java 17+, explaining class identity, `MethodType`, class loaders, `ClassValue`, memory leaks, thread safety, and `MethodHandles.Lookup` permissions. Three complete programs have been compiled with `javac --release 17` and executed for verification.

## 1. Why cache reflection/runtime lookup operations?

A framework may receive a request such as:

```text
operation = "format"
receiver type = com.example.Service
arguments = [42]
```

To execute it, it needs to look up the appropriate method, check permissions, choose the invocation kind, and prepare how to call it. For example, when using Java Reflection:

```java
// Illustrative code; Service and receiver must be declared beforehand.
Method method = Service.class.getMethod("format", int.class);
Object value = method.invoke(receiver, 42);
```

If the lookup is repeated across millions of calls with the **same class, same method, and same signature**, a cache can reduce the work of searching metadata, building adapters, and handling member selection.

However, the following operations **cannot** be conflated:

- `Service.format(int)` and `Service.format(String)`: same name, but different parameter types.
- `Service.format(long)` static and `Service.format(int)` instance: different invocation kinds.
- `plugin.Greeter` defined by loader A and `plugin.Greeter` defined by loader B: same binary name, but two different `Class<?>` objects.
- A method handle created with a privileged `Lookup` and a call from a consumer with only public permissions: a **granted capability** should not be leaked freely.
- An unbound `MethodHandle` and a handle that has called `bindTo(specificReceiver)`: caching a bound handle under a key containing only the class can target the wrong object.
- An original `MethodHandle` and an `asType` adapter: they may have different call-site types, so if adapters are cached they must have different keys.

**Getting the cache key right is a correctness requirement, not just an optimization.** Good performance while calling the wrong class or leaking class loaders is a design bug.

## 2. Class identity in the JVM: not just the class name

According to the Java Virtual Machine Specification, a non-array class/interface at runtime is identified by the **pair (binary name, defining loader)**. Therefore:

```text
Class 1:
  binary name:  plugin.Greeter
  defining loader: LoaderA

Class 2:
  binary name:  plugin.Greeter
  defining loader: LoaderB

Same name, bytes may be identical,
but LoaderA != LoaderB -> two different runtime classes.
```

This can be checked with:

```java
// Illustrative code; classA/classB are previously loaded Class<?>.
System.out.println(classA.getName().equals(classB.getName()));
System.out.println(classA == classB);
System.out.println(classA.getClassLoader() == classB.getClassLoader());
```

If `classA` and `classB` are defined by two separate defining loaders from the same class file, the three lines are typically `true`, `false`, `false`, as shown in the full example in section 6.

### 2.1. Same binary name does not mean compatible types

Suppose:

```java
Class<?> a = /* plugin.Greeter from loader A */;
Class<?> b = /* plugin.Greeter from loader B */;
```

An instance created by `a.getConstructor().newInstance()` is not automatically an instance of `b`, even though both classes have the same code and the same method names. Therefore:

- `a.isInstance(objectB)` will be `false` if `objectB` was created from class B and there is no special type assignability relationship.
- A `Method` obtained via `a.getMethod("hello")` will not accept object B as a valid target instance.
- A virtual `MethodHandle` getter/method from class A has a receiver type corresponding to A, and cannot implicitly accept object B.
- Serializing an object and deserializing it with another loader can lead to a type mismatch if the framework does not preserve the proper type resolution context.

From the JVM's perspective, the name is only a **label**, not the entire type identity. When used as a cache key, the `Class<?>` object represents the exact resolved identity.

### 2.2. Defining loader is different from initiating loader

In the delegation mechanism, a custom loader may be asked to load `java.lang.String` and then **delegate** to the parent/bootstrap loader. Two different initiating loaders can return the **same `Class<String>`**. Therefore, the claim that "every `loadClass` call with a different loader creates a new type" is false.

- **Defining loader** is the loader that actually defined the class.
- **Initiating loader** may simply forward the request and receive a class defined by its parent.
- `Class.getClassLoader()` reflects the defining loader (bootstrap classes may return `null`).
- Do not use the loader object that was asked to load the class as a reliable proxy for class identity.

The example in this lesson intentionally keeps `plugin.Greeter` **off the runtime classpath**, because if the parent already finds that class, both child loaders would receive **the same parent-defined class**, defeating the purpose of the test.

### 2.3. Runtime package and module do not replace Class identity

Two classes with the same `package plugin;` text can live in two different loaders, resulting in different runtime packages and different access rules. JPMS also adds module/readability/exports/opens constraints, but when caching the `Class<?>` object, you are holding the **resolved runtime type**, including its defining loader/module context.

Using `Class.getName()` together with a `module.getName()` string is also **not enough** to infer the same class: multiple module layers, loaders, or plugin environments can contain the same nominal names. When an API already provides `Class<?>`, prefer using that object itself as the key or using `ClassValue`.

## 3. "Signature" must be understood completely: name + parameter types + return type + kind

A method is not properly identified by the name `"format"` alone. Distinguish:

- **Member name:** `format`, `hello`, `<init>` (constructor at the JVM level).
- **Parameter types:** `int`, `String`, `long`, order, and count.
- **Return type:** `void`, `int`, `String`, etc. `MethodType` always includes the return type.
- **Invocation kind:** instance virtual, static, interface, special invocation, constructor, field getter/setter; depending on the API.
- **Declaring/lookup owner `Class<?>`:** where the method is looked up, affecting inheritance and access.
- **Lookup/access context:** the caller's permissions and JPMS rules. That is a policy dimension, not just a name/signature pair.

A MethodHandle cache key for basic lookups can be:

```java
enum Kind { VIRTUAL, STATIC }

record Key(Class<?> owner, Kind kind,
           String name, MethodType memberType) {}
```

This is **illustrative declaration code** in a Java file that imports `java.lang.invoke.MethodType`. Because this is a Java 17 `record`, the key's `equals` and `hashCode` inspect all components. For the `Class<?>` component, equality is based on runtime class identity; for `MethodType`, equality checks each parameter/return `Class<?>`.

If a cache only stores one fixed kind of lookup (for example, **public virtual methods only**), you can omit `Kind` from the key because the cache/namespace itself already fixes the kind. However, in a cache shared across multiple kinds, **the kind must be explicitly included**.

### 3.1. `MethodType` is the operation type, not just the parameter list

For example:

```java
MethodType m1 = MethodType.methodType(
        String.class, int.class);

MethodType m2 = MethodType.methodType(
        String.class, String.class);

MethodType m3 = MethodType.methodType(
        Object.class, int.class);
```

Correspondingly:

```text
m1: (int)String
m2: (String)String
m3: (int)Object
```

Both `m1 != m2` and `m1 != m3` in terms of `MethodType.equals`: the first differs in parameter type, the latter differs in return type. Normal Java source does not overload **by return type alone**, but bytecode can contain bridge/synthetic methods and situations where JVM descriptors care about the return type. Frameworks using `MethodHandle` also need to check the return type even when business operations only care about the method name.

### 3.2. `findVirtual` and `findStatic` differ in receiver signature

A common source of bugs when designing keys:

```java
// In a class with an instance method String format(int):
lookup.findVirtual(Service.class, "format",
        MethodType.methodType(String.class, int.class));

// In a class with a static method String format(long):
lookup.findStatic(Service.class, "format",
        MethodType.methodType(String.class, long.class));
```

With `findVirtual`, the `MethodType` passed to lookup describes the **method member** and **does not include the receiver**. Once lookup succeeds, the handle normally has a type **with the receiver** in the first position:

```text
member type for findVirtual: (int)String
result handle.type():       (Service,int)String
```

With `findStatic`, there is no receiver:

```text
member type for findStatic:  (long)String
result handle.type():        (long)String
```

**Do not mix** the member lookup type with the resolved handle invocation type when constructing keys: if the cache API accepts the member's `MethodType`, clearly define that it is the type **before lookup**. If the cache accepts the call-site `MethodHandle` type, normalize the receiver/adapter before building the key. Mixing them up causes misses, duplicate entries, or `WrongMethodTypeException`.

### 3.3. Generics and erasure

For the method `handle(List<String>)`, the runtime parameter `Class<?>` is `java.util.List.class` due to type erasure. `List<String>` and `List<Integer>` do not have two different runtime `Class<?>` objects and cannot be overloaded based solely on generic type arguments in Java source.

- **JVM-level dispatch caches:** use the erased runtime `Class<?>` and the corresponding `MethodType`.
- **Serializer/validator/DI caches with logic depending on generic types:** may need to additionally store `java.lang.reflect.Type`, annotated types, or parameterized metadata per the framework contract.

Do not assume `MethodType` preserves all Java generic annotations/type arguments; it holds the **runtime Class types** of the arguments and return value.

## 4. Error-prone cache keys

| Cache key | Why it is dangerous | Replacement |
| --- | --- | --- |
| `"plugin.Greeter#hello"` | Ignores defining loader; two runtime classes with the same name are merged | Owner `Class<?>` or `ClassValue` |
| `methodName` | Ignores owner and overloads | Include owner, full signature, kind |
| `className + methodName + arity` | Two overloads with the same argument count but different parameter types | Include every parameter type |
| `className + textDescriptor` | ClassLoader identity is lost if the descriptor contains same-name reference types | Keep resolved `Class<?>`/`MethodType` |
| `owner.getClassLoader() + name` | One loader defines many classes; insufficient info about owner, null bootstrap loader | Use owner `Class<?>` |
| `Class<?> + name` | Overloads and kind can differ | Include full member `MethodType` and kind |
| `MethodType` alone | Does not specify owner/name/kind | Include member identity |
| `MethodHandle.type()` alone | Many different methods share the same invocation type | Include owner/name/kind |
| `String.valueOf(MethodType)` | Displays types by name, does not preserve loader identity | Use the `MethodType` object directly |
| `ClassValue` without distinguishing lookup policy | Caches a handle with private capability, then hands it to an under-privileged caller | Separate permissions/trust boundaries, restrict sharing |
| `owner, signature` for a handle with `bindTo(receiver)` | Ignores receiver identity; easy to target the wrong object | Cache unbound handle or key by bound receiver with proper lifecycle |
| Keying adapter only by underlying method | `asType` target can change type and conversion semantics | Include requested call-site type/adaptation policy |

**Do not use String as a key just because `HashMap<String,...>` is easy to serialize.** A runtime cache capable of holding actual `Class<?>`/`MethodType` objects should use the type identity already resolved by the JVM. Strings can serve as **log/debug descriptions**, not as sufficient identity.

## 5. Proof: two `MethodType`s with the same descriptor text are not equal

`MethodType` stores reference types as `Class<?>`. If two classes have the same binary name but different defining loaders:

```java
// Illustration: a and b are two different Class<?> with the same getName().
MethodType first = MethodType.methodType(void.class, a);
MethodType second = MethodType.methodType(void.class, b);
```

Important result:

```text
first.toMethodDescriptorString()
  == second.toMethodDescriptorString()     // true

first.equals(second)                       // false
```

Both text descriptors can be `(Lplugin/Greeter;)V` because the descriptor records the **binary name**, not the defining loader object. However, `MethodType.equals` compares **`Class<?>` parameter types**, so it distinguishes `a` and `b`.

**Consequence:** converting `MethodType` into a descriptor String and using it as a key can **lose identity**. Conversely, when parsing a descriptor String with `MethodType.fromMethodDescriptorString(descriptor, loader)`, you must supply the **appropriate loader** to resolve reference types. The same descriptor with different loaders can produce different `MethodType`s.

This is a very real problem in plugin systems, hot-reload class loaders, application servers, and test harnesses that load multiple versions of the same FQCN.

## 6. Complete Example 1 — name-based cache bug and fixing it with `ClassValue`

This program defines **two copies of `plugin.Greeter` from the same bytecode** using two class loaders. It intentionally creates a broken `Map<String, Method>` cache to observe the error when using loader A's Method with an instance belonging to loader B. Then it uses `ClassValue<ConcurrentMap<Signature,MethodHandle>>` to cache separately per **runtime `Class<?>`**.

### 6.1. File structure

```text
src/
  plugin/
    Greeter.java
  LoaderCacheDemo.java

build/
  plugin/Greeter.class       # plugin bytes, DO NOT put on the runtime classpath

runtime/
  LoaderCacheDemo.class
  LoaderCacheDemo$BytesLoader.class
  LoaderCacheDemo$Signature.class
  LoaderCacheDemo$1.class    # anonymous ClassValue
  ...                      # nested/record classes if generated by the compiler
```

The `runtime` file paths above are illustrative. You do not need to manually copy each `$...class` if you use `javac -d runtime` so the compiler generates all of them.

### 6.2. File `src/plugin/Greeter.java`

```java
package plugin;

public class Greeter {
    public String hello() {
        return "greeting";
    }
}
```

### 6.3. File `src/LoaderCacheDemo.java`

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class LoaderCacheDemo {
    static final class BytesLoader extends ClassLoader {
        private final byte[] bytes;

        BytesLoader(byte[] bytes) {
            super(LoaderCacheDemo.class.getClassLoader());
            this.bytes = bytes.clone();
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            if (!name.equals("plugin.Greeter")) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    record Signature(String name, MethodType type) {}

    private static final ClassValue<ConcurrentMap<Signature, MethodHandle>> CACHE =
            new ClassValue<>() {
                @Override
                protected ConcurrentMap<Signature, MethodHandle>
                        computeValue(Class<?> type) {
                    return new ConcurrentHashMap<>();
                }
            };

    private static MethodHandle findPublicVirtual(
            Class<?> owner, String name, MethodType type) {
        Signature signature = new Signature(name, type);
        return CACHE.get(owner).computeIfAbsent(signature, key -> {
            try {
                return MethodHandles.publicLookup()
                        .findVirtual(owner, key.name(), key.type());
            } catch (ReflectiveOperationException error) {
                throw new IllegalStateException("Unable to resolve " + key, error);
            }
        });
    }

    public static void main(String[] args) throws Throwable {
        byte[] classBytes = Files.readAllBytes(Path.of(args[0]));
        Class<?> a = Class.forName(
                "plugin.Greeter", true, new BytesLoader(classBytes));
        Class<?> b = Class.forName(
                "plugin.Greeter", true, new BytesLoader(classBytes));

        System.out.println("same binary name: " + a.getName().equals(b.getName()));
        System.out.println("same Class object: " + (a == b));
        System.out.println("same defining loader: "
                + (a.getClassLoader() == b.getClassLoader()));

        MethodType ta = MethodType.methodType(void.class, a);
        MethodType tb = MethodType.methodType(void.class, b);
        System.out.println("same textual descriptor: "
                + ta.toMethodDescriptorString().equals(tb.toMethodDescriptorString()));
        System.out.println("same MethodType: " + ta.equals(tb));

        Object instanceA = a.getConstructor().newInstance();
        Object instanceB = b.getConstructor().newInstance();
        Map<String, Method> wrongCache = new HashMap<>();
        String keyA = a.getName() + "#hello";
        String keyB = b.getName() + "#hello";
        wrongCache.put(keyA, a.getMethod("hello"));

        try {
            wrongCache.get(keyB).invoke(instanceB);
        } catch (IllegalArgumentException error) {
            System.out.println("wrong name-only cache: IllegalArgumentException");
        }

        MethodType returnString = MethodType.methodType(String.class);
        MethodHandle ha = findPublicVirtual(a, "hello", returnString);
        MethodHandle hb = findPublicVirtual(b, "hello", returnString);

        System.out.println("loader A: " + (String) ha.invokeWithArguments(instanceA));
        System.out.println("loader B: " + (String) hb.invokeWithArguments(instanceB));
        System.out.println("cached A again: " + (ha == findPublicVirtual(
                a, "hello", returnString)));
        System.out.println("cache entries per class: "
                + CACHE.get(a).size() + " / " + CACHE.get(b).size());
    }
}
```

### 6.4. How to compile/run on Java 17+ (Bash)

Run in the directory containing `src`:

```bash
mkdir -p build runtime

javac --release 17 -d build src/plugin/Greeter.java
javac --release 17 -d runtime src/LoaderCacheDemo.java

java -cp runtime LoaderCacheDemo build/plugin/Greeter.class
```

The key point is that **`build` is not on the runtime classpath**. `plugin.Greeter` exists only in the bytes read by `LoaderCacheDemo`, and the parent loader does not find it. When the separate `BytesLoader` instances receive the request for `plugin.Greeter`, each loader defines its own copy.

If using PowerShell, replace `mkdir -p build runtime` with `New-Item -ItemType Directory -Force build,runtime`. The `javac` and `java` commands can be written as above.

### 6.5. Verified stdout from actual run

```text
same binary name: true
same Class object: false
same defining loader: false
same textual descriptor: true
same MethodType: false
wrong name-only cache: IllegalArgumentException
loader A: greeting
loader B: greeting
cached A again: true
cache entries per class: 1 / 1
```

### 6.6. Exact mechanism analysis

1. Two `new BytesLoader(classBytes)` calls create two different defining loaders. `Class.forName(...,loader)` invokes the appropriate class-loading path; because `Greeter` is not on the parent runtime classpath, each loader defines a separate class.
2. `a.getName().equals(b.getName())` returns `true` because the binary names are identical.
3. `a == b` and the defining loader comparison are both `false`. The two `Class<?>` objects are two different runtime types.
4. `MethodType.methodType(void.class,a)` and the corresponding call with `b` have the same descriptor text, yet `equals` returns `false`: type identity contains the actual resolved classes.
5. The broken cache `Map<String,Method>` stores the Method belonging to owner `a`, but because `keyA.equals(keyB)`, the code retrieves that same Method and invokes it on `instanceB`. Reflection rejects this with `IllegalArgumentException`.
6. The correct cache uses `ClassValue`: `CACHE.get(a)` and `CACHE.get(b)` are two maps attached to two different `Class<?>` objects. `findVirtual` creates MethodHandles corresponding to each owner.
7. `ha.invokeWithArguments(instanceA)` and `hb.invokeWithArguments(instanceB)` both succeed, returning `greeting`. `invokeWithArguments` is used because the receiver's type is only known **dynamically via `Class<?>`** in the host source; to use `invokeExact`, the caller needs a matching static signature or a normalized adapter.
8. `ha == findPublicVirtual(a,...)` is `true` because of a cache hit for the same owner and the same signature.
9. Both maps have one entry; that does **not** mean `a` and `b` were merged into a single cache entry.

**Illustration limit:** the cache only uses **`findVirtual` for public methods** and `MethodHandles.publicLookup()`. Because the invocation kind is fixed by the `findPublicVirtual` method itself, the record `Signature(name,type)` is sufficient for this specific cache. When caching multiple kinds or different permissions, you must expand the key or separate namespaces.

## 7. When caching uses `Method`, `Constructor`, `Field`, and `MethodHandle`

Different kinds of metadata/handles share a common trait: they are tied to a **declaring class**, method/field name, and type.

### 7.1. Reflection `Method`

`Class.getMethod(name,parameterTypes...)` returns a matching public method, including inherited public methods per its contract. `getDeclaredMethod` looks up a method declared directly in the class. A cache key should distinguish **lookup policy** (public/inherited vs. declared/private) if a single cache serves both.

For example:

```java
record ReflectionMethodKey(
        Class<?> owner,
        String name,
        java.util.List<Class<?>> parameterTypes,
        boolean declaredOnly) {}
```

This is an illustrative declaration. If using `List<Class<?>>`, you must create an **immutable copy** when constructing the key (such as `List.copyOf(...)`) so the key cannot be mutated after insertion into the `Map`. Do not use raw mutable arrays and rely on array `Object.equals`; arrays compare identity by default rather than elements.

**Return type:** `getMethod/getDeclaredMethod` only accept name and parameter types, not return type, for caller selection. If a framework needs to distinguish bridge/synthetic methods or bytecode-level descriptors with different return types, method selection/return-type checking must be designed additionally. Caching at the `MethodHandle.findVirtual/findStatic` level is often convenient because `MethodType` also represents the return type.

### 7.2. Constructors

For `Constructor<?>`, a practical key is typically owner `Class<?>` + ordered constructor parameter types + accessibility policy. With `MethodHandles.Lookup.findConstructor(owner, type)`, the input `MethodType` has a `void` return type (to represent the constructor signature) even though the resolved handle returns an object of the new class when invoked. Do not mechanically use the post-resolution method-handle type as the key for `findConstructor` without normalization.

### 7.3. Fields and VarHandles

A field lookup must consider owner, name, **field type**, static/instance kind, and access policy. If using `Lookup.findVarHandle` or `findStaticVarHandle`, the field type must match exactly. You should not use a key of just `"count"`, because a field with the same name can appear in many classes and have different types.

`VarHandle` holds a variable type and coordinate types, and allows multiple access modes. If caching `VarHandle.toMethodHandle(mode)`, you must also consider the **mode** because `GET`, `SET`, and `COMPARE_AND_SET` have different signatures/semantics.

### 7.4. MethodHandle adapters

`MethodHandle.asType`, `bindTo`, `insertArguments`, `filterArguments`, and combinators can produce **different** handles on top of the same underlying method.

- An `asType` adapter depends on the **requested `MethodType`** and conversion policy.
- `bindTo(receiver)` attaches a **specific receiver instance**; storing it globally under a `Class<?>+name` key can invoke the wrong object.
- `insertArguments` binds one or more specific values; caching must account for the bound values/identity or keep the adapter only within the owner's lifetime.
- A `MethodHandle` can represent multiple processing steps rather than just one declared method; the key must represent the actual structure you intend to reuse.

Principle: **cache unbound resolution separately, and create per-object/per-request adapters as needed**, unless you have a caching policy for bound handles with a controlled lifetime.

## 8. Complete Example 2 — keying by owner, invocation kind, and `MethodType`

This program does not use custom loaders; it demonstrates a `Service` class with **three methods sharing the same name** but differing in signature/kind. The cache uses:

```java
record Key(Class<?> owner, Kind kind,
           String name, MethodType memberType) {}
```

All four components are needed when the cache must support multiple `Lookup` kinds.

### 8.1. File `SignatureCacheDemo.java`

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class SignatureCacheDemo {
    public static final class Service {
        public String format(int n) { return "number:" + n; }
        public String format(String text) { return "text:" + text; }
        public static String format(long n) { return "static:" + n; }
    }

    enum Kind { VIRTUAL, STATIC }

    record Key(Class<?> owner, Kind kind, String name, MethodType memberType) {}

    private static final ConcurrentMap<Key, MethodHandle> CACHE =
            new ConcurrentHashMap<>();

    private static MethodHandle resolve(Key key) {
        return CACHE.computeIfAbsent(key, k -> {
            try {
                MethodHandles.Lookup lookup = MethodHandles.publicLookup();
                return switch (k.kind()) {
                    case VIRTUAL -> lookup.findVirtual(
                            k.owner(), k.name(), k.memberType());
                    case STATIC -> lookup.findStatic(
                            k.owner(), k.name(), k.memberType());
                };
            } catch (ReflectiveOperationException error) {
                throw new IllegalStateException("Cannot resolve " + k, error);
            }
        });
    }

    public static void main(String[] args) throws Throwable {
        Service receiver = new Service();
        Key intKey = new Key(Service.class, Kind.VIRTUAL, "format",
                MethodType.methodType(String.class, int.class));
        Key stringKey = new Key(Service.class, Kind.VIRTUAL, "format",
                MethodType.methodType(String.class, String.class));
        Key longKey = new Key(Service.class, Kind.STATIC, "format",
                MethodType.methodType(String.class, long.class));

        MethodHandle intCall = resolve(intKey);
        MethodHandle stringCall = resolve(stringKey);
        MethodHandle longCall = resolve(longKey);

        System.out.println("virtual int: " + (String) intCall.invokeExact(receiver, 7));
        System.out.println("virtual String: "
                + (String) stringCall.invokeExact(receiver, "Lan"));
        System.out.println("static long: " + (String) longCall.invokeExact(9L));
        System.out.println("entries: " + CACHE.size());
        System.out.println("cache hit: " + (intCall == resolve(intKey)));
        System.out.println("int handle type: " + intCall.type());
        System.out.println("long handle type: " + longCall.type());

        try {
            Object wrong = intCall.invokeExact(receiver, 7);
            System.out.println(wrong);
        } catch (WrongMethodTypeException error) {
            System.out.println("wrong return: WrongMethodTypeException");
        }
    }
}
```

Run:

```bash
javac --release 17 SignatureCacheDemo.java
java SignatureCacheDemo
```

**Verified stdout:**

```text
virtual int: number:7
virtual String: text:Lan
static long: static:9
entries: 3
cache hit: true
int handle type: (Service,int)String
long handle type: (long)String
wrong return: WrongMethodTypeException
```

### 8.2. Why are there three entries?

Each `Key` differs in `Kind` or `MethodType`:

- `format(int)`: `VIRTUAL`, member type `(int)String`.
- `format(String)`: `VIRTUAL`, member type `(String)String`.
- `format(long)`: `STATIC`, member type `(long)String`.

The resolved handle of a virtual method takes an additional receiver at the beginning, so `intCall.type()` is `(Service,int)String`. A static handle has no receiver, so `longCall.type()` is `(long)String`.

`CACHE.computeIfAbsent` reuses the handle for an existing key; that is why `cache hit: true`. In this single-threaded example, `entries` equals three.

### 8.3. A correct cache does not prevent call-site errors

At the end of the demo:

```java
Object wrong = intCall.invokeExact(receiver, 7);
```

The caller requests a return type of `Object`, whereas `intCall.type()` returns `String`. `invokeExact` requires **matching both argument types and return type**: the fact that the runtime result object will be a String does not make the static return type match automatically. Thus, `WrongMethodTypeException` is thrown.

A cache cannot fix a caller with the wrong signature. If the caller needs an `Object` return and the conversion is valid, you can explicitly create an `asType` adapter with the desired method type, or use `invoke`/`invokeWithArguments` appropriately. However, you must consider conversion semantics rather than using adaptation to mask API contract errors.

## 9. Cache correctness is distinct from `Lookup` access permissions

A `MethodHandle` created by `MethodHandles.Lookup` carries the capability to invoke the member that the lookup was allowed to access at creation time. A caller might not have permission to **resolve** a private method itself, yet if handed a handle validly created by a privileged source, the caller can **invoke that handle** as a transferred capability.

Therefore:

- The cache key `(owner,kind,name,MethodType)` is the foundation for **type correctness**.
- However, in multi-tenant, multi-plugin, or varying-caller-privilege systems, the **access policy/trust boundary** is a separate dimension.
- Do not store a privileged private handle in a **public global cache** and hand it to a consumer that should only have public access, even if the type key is completely accurate.
- You can separate the `publicLookup` cache from the privileged cache of a module/trusted component, or restrict the handle-retrieval API according to previously authenticated permissions.
- A handed-off `MethodHandles.Lookup` may have restricted modes when crossing scopes/modules; do not assume any Lookup can resolve the same member.

### 9.1. `lookupClass()` and `lookupModes()` are useful for diagnostics

When encountering `IllegalAccessException`:

```java
// Illustrative code: lookup and owner have been passed in.
System.out.println(lookup.lookupClass());
System.out.println(lookup.lookupModes());
System.out.println(owner.getModule());
```

To obtain a private handle in another module, `privateLookupIn` may be needed, but that only succeeds when the caller has permission and the target module opens the appropriate package. Do not use a cache to bypass JPMS: a cache should only hold capabilities within a clearly designed trust boundary.

### 9.2. Complete Example 3 — `publicLookup` and private lookup

Create file **`AccessScopeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class AccessScopeDemo {
    public static final class Vault {
        private String secret() { return "s3"; }
        public String open() { return "public"; }
    }

    public static void main(String[] args) throws Throwable {
        Vault vault = new Vault();
        MethodType type = MethodType.methodType(String.class);
        MethodHandles.Lookup trusted = MethodHandles.lookup();
        MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();

        MethodHandle open = publicOnly.findVirtual(Vault.class, "open", type);
        System.out.println("public method: " + (String) open.invokeExact(vault));

        try {
            publicOnly.findVirtual(Vault.class, "secret", type);
        } catch (IllegalAccessException error) {
            System.out.println("public lookup private: IllegalAccessException");
        }

        MethodHandle secret = trusted.findVirtual(Vault.class, "secret", type);
        System.out.println("trusted private: " + (String) secret.invokeExact(vault));
        System.out.println("same method type: " + secret.type().equals(open.type()));
    }
}
```

Compile/run:

```bash
javac --release 17 AccessScopeDemo.java
java AccessScopeDemo
```

**Verified stdout:**

```text
public method: public
public lookup private: IllegalAccessException
trusted private: s3
same method type: true
```

Here `Vault` is a nested class in the same **nest** as `AccessScopeDemo`. Therefore, `MethodHandles.lookup()` from `AccessScopeDemo` can look up private members of `Vault`. Meanwhile, `publicLookup()` only finds public methods and is denied access to `secret`.

The last line shows **two handles with the same `MethodType` but different members and access levels**. Keying only by handle `type()` is completely wrong. More importantly, if a system caches the privileged handle `secret` such that an untrusted consumer can retrieve it from the cache, the security boundary has been broken by **capability leakage**, not because `publicLookup` suddenly gained extra permissions.

## 10. `ClassValue`: a cache attached directly to each `Class<?>`

`java.lang.ClassValue<T>` is designed to **lazily associate a computed value with a runtime class**. It is well suited for metadata caches that need to distinguish classes by defining loader.

Fundamental pattern:

```java
private static final ClassValue<ConcurrentMap<Signature, MethodHandle>>
        CACHE = new ClassValue<>() {
    @Override
    protected ConcurrentMap<Signature, MethodHandle>
            computeValue(Class<?> owner) {
        return new ConcurrentHashMap<>();
    }
};
```

In the full example, `Signature` contains name and `MethodType`, and the cache only serves public virtual lookups. `CACHE.get(owner)` returns a separate map attached to **that exact owner `Class<?>`**. Two classes with the same name that are two different objects will not share the same ClassValue value.

### 10.1. Advantages of `ClassValue`

- **Runtime class identity** is the natural namespace, not a name string.
- Useful for plugin class loaders, schema metadata, Reflection descriptors, and method-handle dispatch tables.
- Lazily computed via `computeValue` when `get(Class<?>)` is first called.
- Avoids holding a global `ConcurrentHashMap<Class<?>,...>` with strong keys to **every plugin class**.
- Provides `remove(Class<?>)` when you want to discard the current association and recompute it on the next `get`.
- The JVM supports the ClassValue structure for per-class values; using it directly fits this lesson's scenario.

### 10.2. `computeValue` is not guaranteed to run exactly once under contention

The `ClassValue.get` documentation states that **installing the computed value on the class is atomic**, but if multiple threads simultaneously see no value yet, **`computeValue` may be called multiple times** and the JVM picks one result to use. Therefore:

- Do not put non-idempotent side effects, hard-to-release resource creation, or DB writes into `computeValue` assuming it runs once.
- `computeValue` is best used to simply create an independent cache structure, such as `new ConcurrentHashMap<>()`, or compute metadata that can be safely redone.
- If `remove` races with `get`, recomputation semantics become more complex; an appropriate lifecycle must be designed.
- In this lesson's code, `computeValue` only creates an empty map, so redundant computations due to a race (if any) do not corrupt business state.

Some people mistake `ClassValue` for a `ConcurrentHashMap` where `computeValue` is guaranteed to be invoked only once. That is **not a guarantee** to rely on.

### 10.3. `remove` is not a class-unloading system

`CACHE.remove(owner)` removes a ClassValue's association with a class so the next `get` can recompute the value. It does **not** unload the class, does not destroy `MethodHandle`s already held by other code, and does not invalidate all adapters/call sites in the JVM.

If a framework needs invalidation on plugin reload, it must decide:

1. Is the old class still alive in the old loader?
2. Are in-flight requests using the old handle allowed to finish?
3. Are any registries/weak references/pools still holding the old class?
4. Is invalidation of `CallSite`, `SwitchPoint`, or a generation pointer outside ClassValue needed?

Do not treat `ClassValue.remove` as a transaction that destroys all runtime state.

## 11. Memory leaks: a global cache can keep a class loader alive forever

A plugin container often needs to unload old versions. However, **a global strong-reference cache** can prevent unloading from happening.

Common example:

```java
// Code illustrating lifecycle risk:
static final Map<Class<?>, MethodHandle> GLOBAL = new HashMap<>();

GLOBAL.put(pluginClass, pluginMethodHandle);
```

As long as the JVM is alive and `GLOBAL` exists, the entry can keep the related `Class<?>`/`MethodHandle`/loader reachable. Even if the plugin has "stopped", the loader may never be garbage collected/unloaded. After many reloads, the heap fills with old classes.

### 11.1. Why isn't `WeakHashMap<Class<?>,MethodHandle>` an automatic fix?

`WeakHashMap` holds **keys** weakly, but **values** remain strong references. A `MethodHandle` typically holds a reference to its declaring class or types in its signature. The retention graph can look like:

```text
static cache
    |
    v
WeakHashMap entry
    |
    +-- weak key ------> Class<?> (plugin)
    |
    +-- strong value --> MethodHandle
                             |
                             v
                        Class<?> (plugin)
                             |
                             v
                       defining loader
```

If the value strongly retains the key's Class via another reference path, the weak key **never loses reachability**, and the entry is not collected as expected. This is a well-known pitfall with weak-key maps whose values reference back to the keys.

**This is not claiming every `WeakHashMap` leaks**; the issue is the **reference graph of the values**. When values retain declaring classes, a simple weak-key map may not be enough. `ClassValue` is usually better suited for **per-class cached metadata**, though you still must inspect the whole system.

### 11.2. Does `ClassValue` solve every memory leak?

No. If the app still has a global list containing `Class<?>`, an active thread with the plugin's context class loader, an unregistered listener, an executor task, a timer, or a static registry holding a plugin object, the class can still stay alive.

`ClassValue` solves **one kind of per-class cache association** better than maintaining global strong keys yourself; it does not replace lifecycle management of plugins, threads, class loaders, and references outside the cache.

### 11.3. Values inside the cache can also hold cross-loader references

A per-class cache might hold a `MethodType` referencing parameter types from **another loader**, or adapters/bound instances crossing modules/plugins. If you create an unintentionally long-lived reference graph, an old loader can be retained indirectly. Design clear boundaries: a cache attached to an owner class should only hold entries that truly belong to that lifecycle, and external registries must be released when a plugin generation is no longer needed.

## 12. Concurrent caching: `ConcurrentHashMap` and `computeIfAbsent`

If multiple threads resolve a method concurrently, using an unsynchronized `HashMap` can lead to races and corrupted/overwritten map structure. A `ConcurrentHashMap<Key,MethodHandle>` enables atomic cache population per key:

```java
return cache.computeIfAbsent(key, k -> {
    try {
        return lookup.findVirtual(
                k.owner(), k.name(), k.memberType());
    } catch (ReflectiveOperationException e) {
        throw new IllegalStateException("Lookup failed", e);
    }
});
```

This is **illustrative code** for a key record containing owner/name/memberType and a virtual-only cache. `computeIfAbsent` takes a function that cannot declare checked exceptions; if `findVirtual` throws `NoSuchMethodException` or `IllegalAccessException`, the example wraps it in an unchecked `IllegalStateException` and preserves the cause.

### 12.1. Do not automatically cache lookup failures

If the mapping function throws an exception, `ConcurrentHashMap.computeIfAbsent` does not record a successful entry for that key. The next lookup can try resolving again. This is usually the safe choice when a framework has different loading phases or access policies.

If you want to cache negative results to reduce cost, you must consider:

- **Is the error permanent?** A plugin might still be loading, a module layer might have just changed, or permissions/target versions might change.
- Cache negative results by the exact **class generation and access policy**.
- Have a timely timeout/invalidation mechanism.
- Do not turn an `IllegalAccessException` from an unprivileged consumer into "no consumer has permission" if the cache is shared across different lookup contexts.

Do not use `null` to represent both "no such method" and "not yet cached in the map" when semantics require distinguishing them. `ConcurrentHashMap` does not allow null values; you can use a sealed result/Optional (with a proper lifecycle) for intentional failure caching.

### 12.2. Mapping functions should be short and avoid mutating the same map

With `ConcurrentHashMap.computeIfAbsent`, the mapping function should not perform recursive updates into the same map or make slow, long-running network calls without accounting for contention. The program in the example only looks up a public member and returns a MethodHandle, which is easy to verify.

Beyond correctness, a lookup can involve class resolution/access checks and walking the inheritance graph. Benchmarks must measure **cache miss**, **cache hit**, and **invoke cost**, rather than looking at a single average number when hot.

### 12.3. ClassValue and ConcurrentHashMap solve two different layers

Common design:

```text
ClassValue
    |
    +-- Class<?> A --> ConcurrentMap<Signature, MethodHandle>
    |
    +-- Class<?> B --> ConcurrentMap<Signature, MethodHandle>
```

- `ClassValue` partitions by runtime `Class<?>` and ties lifecycle to the class.
- `ConcurrentMap` handles concurrent lookup/caching of **multiple signatures within the same class**.
- `Signature` includes member name, parameters, return type, and kind if the namespace is not fixed.
- Access permissions are normally enforced by the cache-creating API or a separate trust boundary, not merely by the map's existence.

## 13. Distinguishing lookup by runtime class from method selection by receiver

A cache that uses a class to resolve a method must clearly answer: **is the owner class the static type you want to look up, or the runtime type of the receiver?**

For example:

```java
class Parent {
    String name() { return "parent"; }
}
class Child extends Parent {
    @Override String name() { return "child"; }
}
```

The snippet above is illustrative, not a standalone program. If you obtain a virtual MethodHandle to `Parent.name()`, a `Child` receiver can still dispatch to the override `Child.name()` according to virtual invocation semantics. Therefore, **not every virtual call** needs a separate cache entry per subclass to achieve proper polymorphism.

Conversely, a dynamic language runtime might select **a method based on receiver.getClass()** and build a specialized adapter/guard for that class. In that case, the cache key or inline-cache guard must include the runtime class identity and an invalidation strategy.

**Do not confuse:**

- **Method resolution owner**: the class/interface passed to `findVirtual` or `getMethod`.
- **Actual receiver class**: the class of the object at call time.
- **Method selection/dispatch**: JVM rules for virtual/interface invocation; may reach a different override.
- **Cache strategy**: depends on requirements, may be keyed by resolution owner or by actual receiver class, but must be explicit.

For the `ClassValue` shown in section 6, the owner is passed directly into `findPublicVirtual(owner,...)`, so per-owner caching matches how the member is looked up. In a larger framework, if resolution takes both owner and receiver type, separate the two roles in the key or across separate stages.

### 13.1. Interfaces, default methods, and proxy classes

An interface method can be implemented by many class loaders or many proxy classes. Do not use an interface **name String** as the key for an implementation method handle specialized to a concrete proxy class.

With `Proxy.newProxyInstance(loader, interfaces, handler)`, the proxy class is generated in an appropriate class loader. Two proxy classes implementing the same interface can have different class identities. If caching by exact proxy class, use `proxy.getClass()`/`ClassValue`; if caching by interface method descriptor, understand that the target call may still dispatch through the proxy invocation handler.

Similarly, default methods, bridge methods, and inherited methods have their own resolution rules. Do not treat `Class.getDeclaredMethods()` and `Class.getMethods()` as two ways of producing the same set of entries.

## 14. Class loaders, class unloading, and hot reload

When plugin A is replaced by plugin B while keeping the same class name:

```text
generation 1
  loader L1
  plugin.Service@L1
  MethodHandle H1 (declaring type of L1)
  cached resolution V1

plugin reload

generation 2
  loader L2
  plugin.Service@L2
  MethodHandle H2 (declaring type of L2)
  cached resolution V2
```

Do not reuse `H1` to invoke an instance of `plugin.Service@L2` just because `toString()` or the method descriptors match. Even if the source code and bytecode are identical, the receiver types differ by JVM identity.

A sound lifecycle:

1. Define the plugin generation/loader clearly.
2. Each generation has its own class objects and corresponding resolution cache.
3. On reload, build the new generation and publish it atomically per the framework's API.
4. In-flight requests using the old generation can either finish or be coordinated according to a synchronization/cancellation policy.
5. Do not retain old class loaders via thread-locals, executors, static maps, listeners, bound handles, or unintended registries.
6. If call sites were optimized for the old generation, use runtime relinking/invalidation logic (such as `SwitchPoint`/`MutableCallSite` where appropriate) rather than expecting a class cache to update them automatically.

A `ClassValue` attached to the new owner class will automatically separate entries by the new class. However, `ClassValue` does **not** automatically replace `MethodHandle`s that callers are already holding from the old generation, does not change `CallSite` targets, and does not manage resource cleanup.

## 15. Recommendations for choosing a cache architecture by need

| Need | Typically suitable structure | Notes |
| --- | --- | --- |
| Small app, fixed classes, public reflection | `ConcurrentHashMap<Key,Method>` with `Class<?>` owner | Easy to understand; low loader-unload risk if owner lives for the whole process |
| Framework per-class metadata with multiple loaders | `ClassValue<Metadata>` | Ties cache to runtime class, avoids string keys |
| Framework per-class with multiple method signatures | `ClassValue<ConcurrentMap<Signature,MethodHandle>>` | Separates owner and member signature layers |
| Resolution including virtual/static/constructor/field | Key with `Kind` and type matching contract | Do not mix receiver handle type and member lookup type |
| Caching privileged lookups by module/plugin | Separate namespaces per trust/access policy | Do not leak private MethodHandles |
| Dynamic dispatch by receiver class | Cache by `receiver.getClass()`, appropriate guard/inline-cache | Must handle polymorphism, invalidation, receiver type |
| Hot reload plugins | ClassValue/per-generation cache + lifecycle coordination | Do not retain old loader via global state |
| Caching adaptations/bound handles | Key includes adapter signature and bound values if truly needed | Memory retention risk; caching the base unbound handle is usually better |

### 15.1. Should you cache `Method` or `MethodHandle`?

It depends on the actual operation:

- `Method` is useful when you need Reflection metadata, annotations, modifiers, or invocation via `Method.invoke`.
- `MethodHandle` is suitable when you need typed, composable invocation and have stable call sites that the JVM can optimize.
- Both still require resolving the member once with the right permissions. Do not assume `MethodHandle` is always faster than `Method.invoke`; performance depends on JIT, call-site shape, warm-up, virtual dispatch, adapter chains, and workload.
- If you only need to call a method directly that is already known at compile time, a **normal Java call** is usually simpler and easier to optimize than either. Do not build dynamic runtime infrastructure when unnecessary.

### 15.2. Caching by signature does not mean "caching an invocation result"

Caching a `MethodHandle` caches **how to call**; each invocation still receives actual arguments and executes the target according to its semantics. Caching the result of `service.calculate(input)` is a different **memoization** problem, requiring keys with input/state/version, TTL/invalidation, and a side-effect policy.

Do not put the result of a method call on receiver A into a method lookup cache and return it for receiver B. The method handle lookup cache and the business result cache must be kept separate.

## 16. Debugging Class/Signature cache mismatch bugs

If the application reports inexplicable errors even though the logged class/method names look right, log the following fields (without putting secrets in logs):

```java
// Illustrative code; owner, memberType, kind, and resolvedHandle are already available.
System.out.println("owner binary name: " + owner.getName());
System.out.println("owner defining loader: " + owner.getClassLoader());
System.out.println("owner module: " + owner.getModule());
System.out.println("owner identity: " + System.identityHashCode(owner));
System.out.println("member type: " + memberType);
System.out.println("operation kind: " + kind);
System.out.println("handle type: " + resolvedHandle.type());
```

`System.identityHashCode` is only useful **for diagnostics within a single process**, not as a permanent unique ID or safe cache key; hash collisions can occur. If you need to log loader identity, include the loader type and a framework-assigned generation ID, rather than assuming `loader.toString()` is always unique.

### 16.1. Symptoms and causes

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `IllegalArgumentException: object is not an instance of declaring class` on `Method.invoke` | Using a Method from loader A on an instance of a same-named class from loader B | Compare actual declaring `Class<?>` and receiver `getClass()`; fix the key |
| `ClassCastException` even though class names in the message look identical | Two loader versions of the same FQCN; casting across different type identities | Log defining loaders/module; do not cache by name |
| `WrongMethodTypeException` at `invokeExact` | Call-site static parameters/return type do not equal handle `type()` | Check both return cast and receiver type |
| `NoSuchMethodException` | Wrong overload/generic erasure lookup, wrong owner, or member visibility | Check `Class<?>` parameter types and declared/public lookup policy |
| `IllegalAccessException` on `Lookup.findVirtual` | Lookup lacks permission/JPMS restricts the package | Fix Lookup/module openness or use public API |
| Cache hit but calls the wrong overload | Key omits parameter types or kind | Use full signature |
| Cache miss despite same method name | Different loader, different receiver owner, different signature/adaptation | Inspect actual identity; it may be a legitimate miss |
| Heap grows after plugin reload | Global Map/Class/Method/MethodHandle/listeners retain old loader | Inspect GC roots, caches, thread context class loaders; manage lifecycle |
| `WeakHashMap` does not release entries | Value still retains owner Class/loader | Inspect reference graph; consider ClassValue and cleanup |
| Multiple concurrent lookups | Cache is not thread-safe or mapping function is re-invoked | ConcurrentMap + ClassValue with proper semantics; idempotent computeValue |
| Public caller receives private handle | Privileged cache capability exposed through API | Separate trust boundaries and policy checks |
| Same String descriptor but different MethodType | Same-name classes from different loaders | Use resolved MethodType / Class objects |

### 16.2. Step-by-step debugging

1. **Identify the actual target class**: print owner `Class<?>`, binary name, defining loader, and module.
2. **Identify the actual signature**: parameter types and return type of the member, not just name/arity.
3. **Identify the kind**: static or virtual, constructor, field getter/setter, special invocation.
4. **Identify the lookup context**: `Lookup.lookupClass()`, modes, public/declared/private policy, JPMS.
5. **Identify the cache entry**: which owner/loader/generation created it, and whether it bound a receiver or adapted types.
6. **Identify the caller**: what expected return type/argument types `invokeExact` has, and which loader the receiver belongs to.
7. **Identify the lifecycle**: whether a global cache is retaining an old generation, or a stale negative cache is blocking a new lookup.
8. **Retest with a cache miss** in a safe environment: if the miss path works and the hit path fails, the bug is in the key, lifecycle, or entry publishing permissions.

## 17. Unit tests to have for a loader-aware cache

A practical test suite needs more than "method lookup succeeds":

- **Same class, same signature:** cache hit and returns the right handle/metadata per policy.
- **Same class, different overload:** separate entries for `(int)String` and `(String)String`.
- **Same class, different kind:** static/virtual are not merged.
- **Same binary name, different defining loader:** two different `Class<?>` objects and separate cache entries.
- **Same descriptor String, different MethodType object equality:** distinguishes resolved reference types.
- **Method.invoke with wrong declaring class:** `IllegalArgumentException` is properly expected.
- **MethodHandle.invokeExact with wrong caller type:** `WrongMethodTypeException` at the right layer.
- **Private vs public Lookup:** public lookup cannot obtain a private method; no leaking of privileged handles.
- **Concurrent cache fill:** does not corrupt the map, idempotent per-class cache initialization.
- **Plugin reload:** does not reuse handles from the old loader; old loader can be reclaimed if no references remain.
- **Negative lookup:** handles exception/cause and does not store errors beyond policy scope.
- **Adapters/bound receiver:** a handle bound to instance A is not used as an unbound generic method on instance B.
- **Generic erasure:** does not treat `List<String>` and `List<Integer>` as two different Java runtime classes.

For unloadability/GC tests, **do not** assert that calling `System.gc()` once makes `WeakReference.get()==null` a stable assertion across all JVMs. GC scheduling is not guaranteed on demand by code. Use heap diagnostics, GC root inspection, and appropriate lifecycle tests.

## 18. Self-check questions (with answers)

**Q1.** Two classes both have `getName()=="plugin.Greeter"`. Are they guaranteed to be the same type?

**Answer:** No. Class identity depends on both the binary name and the defining loader; two separate loaders can define two independent types.

**Q2.** Why is the key `className + methodName` dangerous in a plugin runtime?

**Answer:** It ignores the class loader and method signature. You can retrieve a Method/MethodHandle from class loader A and use it on an instance belonging to loader B.

**Q3.** Are two `MethodType`s with the same `toMethodDescriptorString()` always `equals` to each other?

**Answer:** No. The text descriptor contains binary names; two same-named reference types with different defining loaders can produce two different `MethodType`s.

**Q4.** Why should you use `Class<?>` as the key instead of `Class.getName()`?

**Answer:** `Class<?>` is the runtime type already resolved with its defining loader/module context, properly distinguishing two same-named classes defined by different loaders.

**Q5.** Can a global MethodHandle cache supporting virtual and static key only by `owner,name,parameterTypes`?

**Answer:** Not in general. It should include invocation kind and return type (via `MethodType`), or separate fixed namespaces per kind.

**Q6.** Does `findVirtual(Service.class,"run",type)` require `type` to include the `Service` receiver in its parameters?

**Answer:** No. The `MethodType` passed to `findVirtual` describes the member **without the receiver**; the resolved handle type will include the receiver at the front.

**Q7.** A `MethodHandle` to a private method obtained via a privileged lookup is given to a public-only consumer. Can the consumer invoke it?

**Answer:** The handle is a validly created capability, so if the consumer receives the handle, it can invoke it according to its type/target. This is a **permission leakage** risk and requires managing trust boundaries.

**Q8.** Is `ClassValue.computeValue` guaranteed to run exactly once when multiple threads call `get` concurrently?

**Answer:** No. Multiple concurrent computations may occur, and one result is atomically installed. Do not put non-idempotent side effects in `computeValue`.

**Q9.** Does `WeakHashMap<Class<?>,MethodHandle>` guarantee class unloading when no other plugin references remain?

**Answer:** Not guaranteed: the value can hold a strong reference back to the declaring Class/loader, preventing the weak key from losing reachability.

**Q10.** Does `ClassValue.remove(owner)` cause the JVM to unload the owner class on its own?

**Answer:** No. It only removes the association in ClassValue; unloading still depends on all GC roots/lifecycle.

**Q11.** Is using only `MethodHandle.type()` as a key enough to distinguish two methods with the same signature and different names?

**Answer:** No. Two different methods can have the same type; you need owner/name/kind/member identity.

**Q12.** Should `Service.format(int)` and `Service.format(String)` share the same key if they have the same name?

**Answer:** No, because their parameter types differ; `MethodType` must be considered.

**Q13.** Is it safe to cache a virtual method handle with `bindTo(receiverA)` under the key `Service.class,"format"` and invoke it for `receiverB`?

**Answer:** No. A bound handle has attached instance A and has a different invocation signature. Cache the unbound handle or design the key/lifetime with proper receiver identity.

**Q14.** If a `ConcurrentHashMap.computeIfAbsent` mapping function throws an exception, is a valid value entry recorded?

**Answer:** No. If the computation fails with an exception, no successful entry is added; if you want a negative cache, you must explicitly design a result type and invalidation.

**Q15.** Why don't generic `List<String>` and `List<Integer>` create two different `Class<?>` objects?

**Answer:** Java generics use type erasure; at runtime `List.class` is the same class. If a framework needs to distinguish generic contracts, it must additionally inspect `Type` metadata at the business layer.

**Q16.** When a plugin reloads while still using the same FQCN, should the old MethodHandle be reused?

**Answer:** No, if the new class is created by a different defining loader. You must resolve/cache per the new class generation; old method handles belong to old types.

**Q17.** ClassLoader A and B both call `loadClass("java.lang.String")` and both receive the same `String.class`. Does this contradict type identity?

**Answer:** No. Initiating loaders can delegate to the same bootstrap defining loader. The pair of binary name + **defining loader** of the returned class remains unique.

**Q18.** Why shouldn't `System.identityHashCode(Class)` be used as a cache key instead of `Class<?>`?

**Answer:** Identity hashes can collide and do not retain/express Class object identity sufficiently for equality. Use the Class object itself as the key; `identityHashCode` is only for diagnostics.

## 19. Practice exercises

### A. Add an overload

In `SignatureCacheDemo.Service`, add:

```java
public String format(double n) { return "double:" + n; }
```

Create a new `Key` with `Kind.VIRTUAL` and `MethodType.methodType(String.class,double.class)`, resolve, and invoke it. Verify that `CACHE.size()` increases from three to four, and the old entries remain unchanged.

### B. Create a same-named class in a third loader

In `LoaderCacheDemo`, create another `new BytesLoader(classBytes)`, load `plugin.Greeter`, and call `findPublicVirtual` with the new owner. Predict that the third `Class<?>` differs from A and B, has its own ClassValue map, yet the source method can still return the same `"greeting"`. **Same output does not mean same runtime type.**

### C. Test keying only by descriptor String

Create two `MethodType.methodType(void.class,a)`/`methodType(void.class,b)` as in the demo, then put their `toMethodDescriptorString()` into a `Map<String,Object>`. Observe the text key collision, then replace it with `Map<MethodType,Object>` to properly distinguish the types.

### D. Prevent privileged handle leakage

Split the cache into two APIs: a public resolver using only `MethodHandles.publicLookup()`, and a trusted resolver with private permissions within the module. Disallow external clients from calling the API that retrieves private handles. Write a unit test proving a public caller is denied for `Vault.secret`, while the trusted component can still resolve it.

### E. Inspect memory retention after reload

Design a plugin load/unload test with `ClassValue` and a global strong map to compare reference graphs. Use heap dump/GC root analysis to find references keeping the old loader alive. Do not write a naive assertion like "`System.gc()` must unload immediately", because GC is non-deterministic.

## 20. Official documentation

- **Java SE 17 — `ClassValue`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html — lazily computed cache per `Class<?>`, `get`/`remove`, concurrent computation semantics.
- **Java SE 17 — `ClassLoader`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html — defining/initiating loader, delegation, and class-loading lifecycle.
- **Java SE 17 — `Class`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html — runtime class identity, `getName`, `getClassLoader`, `getModule`, and reflection.
- **Java SE 17 — `MethodType`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html — signature with each `Class<?>` parameter/return and descriptor conversion.
- **Java SE 17 — `MethodHandle`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html — `type`, `invokeExact`, `invoke`, `asType`, `bindTo`.
- **Java SE 17 — `MethodHandles.Lookup`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html — `findVirtual`, `findStatic`, `findConstructor`, lookup permissions.
- **Java SE 17 — `MethodHandles`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html — `lookup`, `publicLookup`, `privateLookupIn`.
- **Java SE 17 — `Method`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html — declaring class, invocation, and reflection semantics.
- **Java SE 17 — `ConcurrentHashMap`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html — `computeIfAbsent` and concurrent map semantics.
- **Java SE 17 — `WeakHashMap`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html — weak keys and warning about values retaining keys.
- **JVMS 17 `5.3 — Creation and Loading:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3 — type identity is binary name + defining loader.
- **JVMS 17 `5.4.3 — Resolution:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3 — symbolic references, member resolution.
- **JLS 17 `4.6 — Type Erasure:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6 — generic erasure and runtime types.

**Conclusion:** To cache reflection/MethodHandle safely, you must keep the **actual runtime owner `Class<?>`**, not just the class name; the **full member signature and invocation kind**, not just the method name; and the **Lookup permission boundary along with the class loader lifecycle**. `ClassValue` helps organize caches by class identity, but does not by itself fix privileged handle leakage, bound receiver mistakes, or class-loader retention in other registries. A correct cache is one that returns **the exact operation resolved for the right class generation and the right type/access contract**.