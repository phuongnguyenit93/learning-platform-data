# 14.6. Describing Dynamic Constants with `DynamicConstantDesc` and Resolving with `Lookup` Permissions

A **dynamic constant** (*dynamically-computed constant*, abbreviated as *condy*) allows a constant entry in a class file to be computed via a bootstrap method when the JVM resolves that constant entry, instead of requiring a pre-stored literal value. In Java 17, `java.lang.constant.DynamicConstantDesc<T>` is the **nominal descriptor** for a dynamic constant, while `java.lang.invoke.MethodHandles.Lookup` provides the **name-lookup and access-checking context** when we explicitly call `resolveConstantDesc(lookup)`.

Three things to keep in mind from the start:

1. `DynamicConstantDesc` describes **bootstrap + constant name + constant type + bootstrap arguments**. Creating a descriptor does not run the bootstrap and cannot automatically read private fields or methods.
2. Only `resolveConstantDesc(lookup)` resolves the descriptor using the permissions/class loader/module of the `Lookup`. **The same descriptor** may resolve successfully with a Lookup that has private access, yet fail with a Lookup whose permissions have been reduced.
3. **Resolution via the Java API does not cache the result.** This differs from the JVM's caching mechanism when resolving an actual `CONSTANT_Dynamic` entry in the runtime constant pool. A bootstrap with side effects can run on every call to `resolveConstantDesc`.

This article presents how to create descriptors with the Java 17 API, the resolution mechanism, access permission boundaries, common pitfalls, and a hands-on program compiled with `javac --release 17`.

## 1. Two Layers: `CONSTANT_Dynamic` in the Class File and `DynamicConstantDesc` in Java

In the class file format, `CONSTANT_Dynamic_info` is a symbolic reference to a dynamically-computed constant. It specifies a bootstrap method and a set of static arguments, along with the constant's name/type information. When a dynamic constant entry needs to be resolved, the JVM invokes the appropriate bootstrap and checks the result. This is a mechanism in the **runtime constant pool** of a loaded class.

`DynamicConstantDesc<T>`, on the other hand, is a **Java object describing** that same information at the `java.lang.constant` API level. Tools that read, analyze, or generate bytecode use descriptors to represent class-file-level data. Applications can also construct descriptors and test resolving them with `resolveConstantDesc(lookup)` without manually generating a class file containing an `ldc` instruction pointing to `CONSTANT_Dynamic`.

| Concept | What is it? | When is the value computed? |
| --- | --- | --- |
| `CONSTANT_Dynamic_info` | Nominal entry in the class file's constant pool | Computed by the JVM when resolving that symbolic reference |
| `DynamicConstantDesc<T>` | Java object **describing** a dynamic constant | Not yet computed when calling factories `ofNamed` or `of` |
| `resolveConstantDesc(Lookup)` | API that uses a lookup to reflectively resolve a descriptor | When the API is called; **not automatically cached** for subsequent calls |
| `ConstantDesc` | Common interface for nominal descriptors | Each implementation defines the appropriate resolution behavior |

**Do not confuse with `static final`:** this modifier locks reassignment of a field in Java; it does not automatically turn a field into a `CONSTANT_Dynamic` entry. Although a standard bootstrap can be used to read a `static final` field, the two concepts are not identical.

**Do not confuse with `invokedynamic`:** a bootstrap for a dynamic call site takes three prefix parameters `Lookup, String, MethodType` and must produce a `CallSite`; a bootstrap for a **dynamic constant** takes `Lookup, String, Class<?>` and produces a constant value compatible with the described type. `DynamicCallSiteDesc` is a different kind of descriptor.

The condy mechanism was introduced into Java 11 class files (JEP 309). The nominal constant descriptors API, including `DynamicConstantDesc`, appeared starting in Java 12 (JEP 334).

## 2. Structure of a Descriptor

A `DynamicConstantDesc<T>` contains four nominal parts:

```text
DynamicConstantDesc<T>
  ├─ bootstrapMethod  : DirectMethodHandleDesc
  ├─ constantName     : String
  ├─ constantType     : ClassDesc
  └─ bootstrapArgs    : ConstantDesc[] (can be empty)
```

| API | Meaning |
| --- | --- |
| `bootstrapMethod()` | Descriptor of the method handle pointing to the bootstrap method |
| `constantName()` | Dynamic constant name, appearing in the `NameAndType` information |
| `constantType()` | `ClassDesc` describing the type of value to produce, e.g., `String` or `int` |
| `bootstrapArgs()` | Array of static bootstrap arguments of type `ConstantDesc` |
| `bootstrapArgsList()` | Unmodifiable list of bootstrap arguments via the List API |
| `resolveConstantDesc(lookup)` | Resolves the descriptor with `Lookup` permissions and returns the actual value |

The types here are **not yet runtime entities**: `ClassDesc` is not yet a loaded `Class<?>`; `DirectMethodHandleDesc` is not yet a resolved `MethodHandle`. A descriptor can be constructed and its metadata read without having permission to invoke the bootstrap or access the described field.

Illustrative snippet in a context that has a variable `desc`:

```java
System.out.println(desc.constantName());
System.out.println(desc.constantType());
System.out.println(desc.bootstrapMethod());
System.out.println(desc.bootstrapArgsList());
```

The four statements above **only read metadata** and do not run the bootstrap. This snippet is not standalone because `desc` has not been created yet; the full program in section 7 will build and resolve a real descriptor.

### 2.1. Constant Name and Constant Type

The name must be a **valid unqualified name** according to JVM rules, not an arbitrary path. `ofNamed` can throw `IllegalArgumentException` immediately when creating the descriptor if the name is malformed. The name `"greeting"` in the example is only passed to the bootstrap; it does not automatically mean the name of a Java field.

`constantType()` is a `ClassDesc`. `ConstantDescs.CD_String` describes `String`, and `ConstantDescs.CD_int` describes `int`. Upon resolution, the system must convert the type descriptor into the appropriate `Class<?>` and check whether the bootstrap result can be used as a constant value of that type.

The generic `<T>` helps express intent in Java source code, but **does not replace resolution/type checks**. You can create an invalid descriptor or reference a method lacking permissions even if the variable is declared as `DynamicConstantDesc<String>`.

### 2.2. Static Bootstrap Arguments

Additional arguments must be values representable in the `ConstantDesc` system, such as `String` literals, appropriate primitive wrappers, `ClassDesc`, `MethodHandleDesc`, or nested descriptors. For an argument that is itself a descriptor, the resolution process may require accessing additional classes/methods/fields according to the `Lookup`.

You cannot directly pass `new Object()` or a runtime DTO without an appropriate constant representation into `ConstantDesc...` and expect the JVM to serialize it automatically. If the bootstrap needs special runtime data, design a valid representation using constants/descriptors, or choose a different data-passing mechanism.

## 3. Three Factories: `ofNamed`, `of`, `ofCanonical`

### 3.1. `ofNamed`: Full Description

```java
static <T> DynamicConstantDesc<T> ofNamed(
        DirectMethodHandleDesc bootstrapMethod,
        String constantName,
        ClassDesc constantType,
        ConstantDesc... bootstrapArgs)
```

Example in a context where the class `DynamicConstantLookupDemo` already exists:

```java
ClassDesc owner = ClassDesc.of("DynamicConstantLookupDemo");
DirectMethodHandleDesc bsm = ConstantDescs.ofConstantBootstrap(
        owner, "counted", ConstantDescs.CD_String,
        ConstantDescs.CD_String);

DynamicConstantDesc<String> description = DynamicConstantDesc.ofNamed(
        bsm, "greeting", ConstantDescs.CD_String, "world");
```

`owner` describes the class containing the bootstrap; `bsm` describes the method `counted`; `constantName` is `"greeting"`; the constant type is `String`; and the static arg `"world"` also has type `String`. This is not yet calling `counted`: `ofNamed` only builds the descriptor.

`ConstantDescs.ofConstantBootstrap(owner, name, returnType, staticArgTypes...)` is a factory specifically for dynamic constant bootstraps. It automatically prepends the **prefix signature `Lookup, String, Class`** to the method descriptor, then appends the provided static argument types. Do not confuse it with the API for creating a CallSite bootstrap, where the third parameter is `MethodType`.

### 3.2. `of`: Default Name, Type from Bootstrap

`DynamicConstantDesc.of(bootstrap)` and `DynamicConstantDesc.of(bootstrap, bootstrapArgs...)` use `ConstantDescs.DEFAULT_NAME`. The constant type is set according to the **return type described on the bootstrap method**, not based on a bootstrap value that has not run yet.

Use `of` if the bootstrap does not care about a specific constant name and the type can be accurately inferred from the signature. Use `ofNamed` if you need control over a specific name, constant type, or static arguments matching the class file format.

### 3.3. `ofCanonical` May Return a Different Subtype

`DynamicConstantDesc.ofCanonical(...)` returns **`ConstantDesc`**, without promising it will always be a `DynamicConstantDesc`. For certain well-known bootstraps, the API may convert the descriptor into a more specialized kind, such as a `ClassDesc` or an enum/VarHandle-related descriptor.

When writing a constant pool reader tool, `ofCanonical` can be useful to represent the canonical meaning of a constant. However, **do not blindly cast** the result to `DynamicConstantDesc<?>`; if it actually returns a `ClassDesc`, the cast will fail.

## 4. Bootstrap Method Signature for Dynamic Constants

A custom-written bootstrap typically has the pattern:

```java
public static String counted(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type,
        String suffix) {
    return name + ":" + suffix;
}
```

The code above is an example of the signature, not a standalone program. Meaning:

1. **`lookup`:** the name-resolution and access-checking context; not full permissions by default.
2. **`name`:** the name of the constant being resolved.
3. **`type`:** the class mirror representing the constant type to return, determined by `constantType`.
4. **`suffix`:** the resolved static bootstrap argument, for example the string `"world"`.

The bootstrap may ignore `name` or `type` if the contract allows, but ignoring them does not hide errors during the resolution of the class, method, or static args. The final result must be compatible with the constant type.

The method descriptor of the bootstrap in the complete example is:

```text
(MethodHandles.Lookup, String, Class, String)String
```

This is a **bootstrap method** signature, not the type of a target `MethodHandle` for `invokedynamic`. Parts like `ClassDesc` and `DirectMethodHandleDesc` only describe symbols; upon resolution, the bootstrap is looked up as a real method according to `Lookup` permissions.

### 4.1. Bootstraps Can Execute Code with Side Effects

`resolveConstantDesc` can invoke a custom-defined method, and that method can read fields, increment counters, allocate objects, or throw exceptions. Therefore, a descriptor **is not merely harmless display data once you decide to resolve it**. Before resolving a descriptor coming from a plugin or untrusted input, you must check the permission policy and avoid granting an unintentionally high-privilege `Lookup`.

A good "constant" bootstrap usually has stable results for fixed inputs, but the API does not forbid examples with side effects. The program below intentionally increments a counter to demonstrate the difference between descriptor resolution and constant pool caching.

## 5. `Lookup` Determines Permissions at Resolution Time

The actual signature on `DynamicConstantDesc` in Java 17:

```java
public T resolveConstantDesc(MethodHandles.Lookup lookup)
        throws ReflectiveOperationException;
```

`resolveConstantDesc` uses `lookup` as the **access and name-lookup context**. Conceptually, resolution may need to:

1. Resolve the `ClassDesc` of the constant type, related classes, and static arguments.
2. Resolve the bootstrap `DirectMethodHandleDesc` into an actual `MethodHandle`.
3. Check whether the caller context has permission to access the required method/field/class.
4. Prepare the `Lookup`, name, type, and resolved static arguments to invoke the bootstrap.
5. Execute the bootstrap and check that the returned result is compatible with `constantType`.

This is an explanatory diagram, not an assertion of the exact order of every linking operation across all JVM implementations. The formal rules for resolution and access control are in JVMS `5.4.3.6` and `5.4.4`.

**Steps can fail in different ways:** class not found, missing bootstrap method, mismatched signature, module not opened/exported as required, Lookup lacking private access, bootstrap throwing an error itself, invalid static arg, or result not matching the type.

### 5.1. `MethodHandles.lookup()` Is Not Equal to `publicLookup()`

`MethodHandles.lookup()` returns a `Lookup` based on the **caller class at the call site**, which may carry private access to that class and its corresponding nestmates. `MethodHandles.publicLookup()` only represents public-level access under conditions permitted by the class/module/loader; it is not a "superuser" and sometimes uses a different context class loader.

To isolate mainly **private access** without introducing additional class-loader differences into the article, the test example uses:

```java
MethodHandles.Lookup full = MethodHandles.lookup();
MethodHandles.Lookup restricted =
        full.dropLookupMode(MethodHandles.Lookup.PRIVATE);
```

Both are created inside the example's class. `restricted` is a **downgraded** Lookup, so it no longer has the privilege to access private fields in that very class. `dropLookupMode` has rules for reducing related access modes; do not assume the remaining state always differs by only a single bit. You can inspect `lookup.lookupClass()` and `lookup.lookupModes()` to see the actual context.

### 5.2. Resolving Public and Private Fields from the Same Descriptor Family

`ConstantDescs.BSM_GET_STATIC_FINAL` describes the standard bootstrap `ConstantBootstraps.getStaticFinal`. It can read an eligible static final field and is subject to access checks according to the passed `Lookup`.

Given:

```java
public static final String OPEN = "open";
private static final String SECRET = "hidden";
```

If the same class uses a full Lookup, both fields can be resolved via the standard bootstrap. With a Lookup that has dropped `PRIVATE`, `OPEN` can still be accessed via public access (assuming appropriate class/module), but `SECRET` is **not** allowed. This is a **permission constraint**, not a difference between `final` and non-final, nor an issue with the `String` type.

Creating:

```java
DynamicConstantDesc<String> secret = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_GET_STATIC_FINAL,
        "SECRET", ConstantDescs.CD_String,
        ClassDesc.of("DynamicConstantLookupDemo"));
```

does not automatically grant private access and does not read the field immediately. Only resolving with `full` or `restricted` determines readability. In practice, the standard bootstrap can even report `IllegalAccessError` with `IllegalAccessException` as its cause; **you should not rely on a single exception name to describe the entire contract**.

### 5.3. Modules, Packages, and Class Loaders Are Also Part of the Context

`Lookup` is not just a `private` flag. It has a lookup class, access modes, package/module rules, and the ability to resolve classes via a class loader. Two classes with the same binary name loaded by two different class loaders can be **two different runtime types**. `ClassDesc` by itself describes a name, without carrying a uniquely bound `Class<?>` object.

In JPMS, readability/exports/opens are relevant to the kind of access you need. `MethodHandles.privateLookupIn(...)` is only valid when the caller/module is permitted; it is not a workaround to arbitrarily cross module boundaries. If `resolveConstantDesc` is denied, verify the lookup context, package, and member kind before changing JVM flags.

### 5.4. Do Not Grant a High-Privilege `Lookup` to Untrusted Descriptors

A descriptor only holds metadata at creation time, but when **resolving** it, bootstrap code can execute with the supplied access context. Therefore, resolving a descriptor obtained from an external source needs to be evaluated much like an operation that can **execute code**. Do not pass `fullLookup` to an arbitrary plugin and hope the generic `DynamicConstantDesc<String>` guarantees safety.

## 6. Descriptors Do Not Cache; the JVM's Runtime Constant Pool Does

The Javadoc for `DynamicConstantDesc.resolveConstantDesc` explicitly states that it **does not cache resolved values**. For example, a bootstrap that increments a counter:

```java
String first = description.resolveConstantDesc(full);  // "greeting:world:1"
String second = description.resolveConstantDesc(full); // "greeting:world:2"
```

`description` is the same object on both lines, yet the bootstrap can be called again. Two distinct descriptor objects for which `equals(...)` returns `true` also do not automatically share a result cache: `equals` here compares **bootstrap method descriptor + name + type + static arguments**.

Conversely, when the JVM resolves an actual `CONSTANT_Dynamic` entry in the runtime constant pool, the linking result is **recorded for the corresponding symbolic reference**; subsequent accesses to the already-resolved entry do not re-invoke the bootstrap. Even failed resolution attempts have JVM error-recording rules.

| Operation | Runs bootstrap automatically? | Is the result cached automatically? |
| --- | --- | --- |
| `DynamicConstantDesc.ofNamed(...)` | No | No value to cache |
| `description.resolveConstantDesc(full)` 1st call | Can run | **Not** cached for 2nd call |
| `description.resolveConstantDesc(full)` 2nd call | Can run again | **Not** cached for 3rd call |
| JVM resolves a `CONSTANT_Dynamic` in a class file | Yes, when first needing resolution | **Yes**, for that symbolic reference |
| `description.equals(other)` | No | Only compares metadata |

**Note:** The JVM caches per associated symbolic reference entry, not a "global cache by constant name". Two classes/constant-pool entries do not automatically share the same result just because their metadata is identical. If an application caches descriptor resolution itself, it must account for `Lookup` permissions, class-loader identity, concurrency, and side effects — it cannot simply use `constantName` as the key.

## 7. Complete Java 17+ Example: Description, Resolution, Permissions, and No-Cache

Save the **entire** source below into the file `DynamicConstantLookupDemo.java`. This is a public class in the unnamed package to run standalone with `javac` and `java`. `counted` is a custom bootstrap method; the other two descriptors use `ConstantDescs.BSM_GET_STATIC_FINAL`; the last descriptor uses `BSM_NULL_CONSTANT`.

```java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.DirectMethodHandleDesc;
import java.lang.constant.DynamicConstantDesc;
import java.lang.invoke.MethodHandles;

public class DynamicConstantLookupDemo {
    public static final String OPEN = "open";
    private static final String SECRET = "hidden";
    private static int counter;

    public static String counted(MethodHandles.Lookup lookup,
                                 String name, Class<?> type, String suffix) {
        if (type != String.class) {
            throw new IllegalArgumentException("expected String");
        }
        return name + ":" + suffix + ":" + (++counter);
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        MethodHandles.Lookup full = MethodHandles.lookup();
        MethodHandles.Lookup restricted =
                full.dropLookupMode(MethodHandles.Lookup.PRIVATE);
        ClassDesc owner = ClassDesc.of("DynamicConstantLookupDemo");

        DirectMethodHandleDesc bsm = ConstantDescs.ofConstantBootstrap(
                owner, "counted", ConstantDescs.CD_String,
                ConstantDescs.CD_String);
        DynamicConstantDesc<String> description = DynamicConstantDesc.ofNamed(
                bsm, "greeting", ConstantDescs.CD_String, "world");
        DynamicConstantDesc<String> sameDescription = DynamicConstantDesc.ofNamed(
                bsm, "greeting", ConstantDescs.CD_String, "world");

        System.out.println("name=" + description.constantName());
        System.out.println("type=" + description.constantType().displayName());
        System.out.println("bootstrap=" + description.bootstrapMethod().methodName());
        System.out.println("args=" + description.bootstrapArgsList().size());
        System.out.println("equal=" + description.equals(sameDescription));
        System.out.println("created.counter=" + counter);
        System.out.println("first=" + description.resolveConstantDesc(full));
        System.out.println("second=" + description.resolveConstantDesc(full));

        DynamicConstantDesc<String> open = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_GET_STATIC_FINAL, "OPEN",
                ConstantDescs.CD_String, owner);
        DynamicConstantDesc<String> secret = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_GET_STATIC_FINAL, "SECRET",
                ConstantDescs.CD_String, owner);

        System.out.println("open.full=" + open.resolveConstantDesc(full));
        System.out.println("open.restricted=" + open.resolveConstantDesc(restricted));
        System.out.println("secret.full=" + secret.resolveConstantDesc(full));

        boolean denied = false;
        try {
            secret.resolveConstantDesc(restricted);
        } catch (ReflectiveOperationException | LinkageError e) {
            denied = true;
        }
        System.out.println("secret.restricted.denied=" + denied);

        DynamicConstantDesc<String> nullable = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_NULL_CONSTANT, "empty", ConstantDescs.CD_String);
        System.out.println("null.result=" + (nullable.resolveConstantDesc(full) == null));
    }
}
```

Compile with the Java 17 API and run in the same directory:

```bash
javac --release 17 DynamicConstantLookupDemo.java
java DynamicConstantLookupDemo
```

`stdout` of the example:

```text
name=greeting
type=String
bootstrap=counted
args=1
equal=true
created.counter=0
first=greeting:world:1
second=greeting:world:2
open.full=open
open.restricted=open
secret.full=hidden
secret.restricted.denied=true
null.result=true
```

This source compiled successfully with the `--release 17` option and was verified running on OpenJDK 24. The API used is the standard Java 17 API; the `denied=true` flag avoids tying the example to the specific exception name of a failed resolution on a particular JVM version.

### 7.1. Why Do the Lines Produce These Results?

**`name=greeting`, `type=String`, `bootstrap=counted`, `args=1`:** these are the metadata provided to `ofNamed`, not the result of running the bootstrap.

**`equal=true`:** two separate descriptors have the same structure; the equality criterion is not object identity or equality of results across individual resolutions.

**`created.counter=0`:** creating the descriptor and inspecting its metadata does not invoke the `counted` bootstrap. If the counter had already incremented upon creating the descriptor, that would be due to other code explicitly running a side effect, not `ofNamed` by contract.

**`first=greeting:world:1`, `second=greeting:world:2`:** calling `resolveConstantDesc(full)` twice causes `counted` to run twice. This is the direct difference between **non-caching descriptor resolution** and **runtime constant pool caching**.

**`open.full=open` / `open.restricted=open`:** `OPEN` is a public field, successfully resolved by the standard `getStaticFinal` bootstrap with a Lookup either with or without private access, in the class/package context of the example.

**`secret.full=hidden`:** `full` was created inside `DynamicConstantLookupDemo` itself, so it has sufficient permission to access private members of that class.

**`secret.restricted.denied=true`:** the same `SECRET` descriptor, but `restricted` has lost `PRIVATE` permission; resolution is denied. The specific exception may be represented via `ReflectiveOperationException` or `LinkageError` depending on the stage and cause chain; the tested OpenJDK version reported `IllegalAccessError` with `IllegalAccessException` as its cause, so the example only prints the stable "denied" information.

**`null.result=true`:** `BSM_NULL_CONSTANT` can return null for a **reference type** like `String`. Do not assume that a primitive constant like `int` can hold null, or that an arbitrary `null` can be passed as a bootstrap argument in the factory.

## 8. Stage-by-Stage Error Checking

| Stage | Common Symptoms | How to Handle |
| --- | --- | --- |
| Descriptor creation | `IllegalArgumentException` with malformed name | Check that `constantName` is a valid unqualified name |
| Class resolution | `ClassNotFoundException`/`LinkageError` | Check `ClassDesc`, lookup class loader, and module readability |
| Bootstrap handle resolution | Method does not exist or is inaccessible | Check owner, method name, static modifier, signature, and Lookup permissions |
| Bootstrap args resolution | Nested descriptor fails to resolve | Check each `ConstantDesc` and the access context |
| Bootstrap invocation | Bootstrap itself throws a runtime exception/error | Inspect stack trace/cause; do not confuse with a descriptor error |
| Result type check | Wrong type returned or null for a primitive | Align `constantType` and the bootstrap contract |
| Private access | May see `IllegalAccessError` with cause `IllegalAccessException` | Verify `lookupModes`/module/owner; do not automatically elevate permissions |
| Second call | Counter changes, no caching | Matches `resolveConstantDesc` contract; if caching is needed, design it separately |

`resolveConstantDesc` declares the checked `ReflectiveOperationException`, but **that does not mean every error is a checked exception**. Linking errors can be `LinkageError`/`BootstrapMethodError`; the bootstrap itself can throw exceptions or errors. `catch (Exception e)` code does not catch every `Error`.

**Do not** fix this by swallowing `Throwable` and returning `null` in production: doing so can turn linking and access-permission errors into bogus valid-looking data while hiding the root cause.

### 8.1. Debugging with Metadata and Permissions

With valid `desc` and `lookup` variables in code:

```java
System.out.println("name: " + desc.constantName());
System.out.println("type: " + desc.constantType());
System.out.println("bootstrap: " + desc.bootstrapMethod());
System.out.println("static args: " + desc.bootstrapArgsList());
System.out.println("lookup class: " + lookup.lookupClass());
System.out.println("lookup modes: " + lookup.lookupModes());
```

This snippet **is not a standalone file**, but a logging checklist at the caller. When reporting actual errors, also log the cause chain and appropriate class loader/module; avoid logging secret values of resolved constants.

**Note:** A `ClassDesc` does not by itself pin a unique runtime `Class<?>`. The same class name in a different class loader can lead to a different class or class-not-found. If a `publicLookup()` cannot resolve the application's class, the failure may occur before checking private field permissions. That is why the example uses `dropLookupMode(PRIVATE)` on a lookup that can already resolve the class, to isolate the access issue specifically.

## 9. Standard Bootstrap Descriptors and When to Use Them

`java.lang.constant.ConstantDescs` provides several descriptors for built-in bootstraps:

| Bootstrap descriptor | Purpose | Notable Constraints |
| --- | --- | --- |
| `BSM_GET_STATIC_FINAL` | Retrieve the value of a static final field | Class/field must be visible according to `Lookup` |
| `BSM_NULL_CONSTANT` | Create a null constant | Reference types only |
| `BSM_ENUM_CONSTANT` | Retrieve an enum constant | Name/enum type must be valid |
| `BSM_PRIMITIVE_CLASS` | Retrieve the Class mirror of a primitive | Descriptor name/type must be correct |
| `BSM_INVOKE` | Invoke a MethodHandle to produce a constant | Method handle and static args must be resolvable |
| `BSM_VARHANDLE_FIELD` / `BSM_VARHANDLE_STATIC_FIELD` | Create a VarHandle for a field | Does not bypass field access boundaries |

Prefer a standard bootstrap when it matches your goal, instead of writing a custom method that reimplements the same thing without full control over signature and access. If using a custom bootstrap, use `ConstantDescs.ofConstantBootstrap(...)` to describe the prefix parameters accurately, then write the actual method with the matching signature.

Do not choose a bootstrap by guessing names subjectively; compare the method descriptor, static arguments, return type, and caller permissions. When the model can be represented by a specialized `ClassDesc`/`EnumDesc`, `ofCanonical` can provide a more appropriate descriptor type for class file analysis tools.

## 10. Mistakes to Avoid

**Mistake 1: "Having a `DynamicConstantDesc<String>` means the value is already available."** The descriptor holds metadata, not a pre-stored `String` result. Only calling `resolveConstantDesc` performs resolution.

**Mistake 2: "Calling `ofNamed` successfully means you have permission to access the field/method."** The factory validates input structure; it does not substitute for runtime name resolution or access control.

**Mistake 3: "Every `Lookup` is the same because it is just the first argument to the bootstrap."** PRIVATE/MODULE permissions, caller lookup class, and class loader make substantive differences.

**Mistake 4: "A constant is something that never runs a bootstrap more than once."** You must distinguish **JVM constant-pool resolution**, which caches, from the Java API `resolveConstantDesc`, which **does not cache**.

**Mistake 5: "`ClassDesc` is `Class<?>`."** `ClassDesc` is a name/symbolic description; only resolution determines the concrete class in a loader/module context.

**Mistake 6: "`ofCanonical` always returns `DynamicConstantDesc`."** Its return type is `ConstantDesc`; it may canonicalize to a different descriptor kind.

**Mistake 7: "You can pass any runtime object as `bootstrapArgs`."** `bootstrapArgs` requires corresponding `ConstantDesc` values, not an arbitrary DTO array.

**Mistake 8: "Catching `ReflectiveOperationException` catches every error."** `LinkageError` and bootstrap failures can still occur; you must preserve the cause for diagnosis.

**Mistake 9: "Using a high-privilege `Lookup` to resolve a descriptor from a plugin is just reading metadata."** Resolution can execute bootstrap code; you must control the descriptor source and the granted permissions.

## 11. Self-Check Exercises

**A.** A descriptor for a private static final field is created successfully with `ofNamed`. Can we conclude it can be resolved with any `Lookup`? Why?

**B.** Two descriptors have the same bootstrap, name, type, and args, so `equals(...)` returns true. The bootstrap increments a counter. Are two calls to `resolveConstantDesc` guaranteed to return the same value?

**C.** A bootstrap method uses `(Lookup, String, MethodType)` as its first three parameters. Is this the correct signature for a dynamic constant bootstrap?

**D.** Within the same class, `full = MethodHandles.lookup()` and `restricted = full.dropLookupMode(PRIVATE)`. With the standard field-reading bootstrap, how do `public static final` and `private static final` differ?

**E.** `DynamicConstantDesc.ofCanonical(...)` returns `ConstantDesc`. Should you cast it directly to `DynamicConstantDesc`?

**F.** The JVM has successfully resolved a `CONSTANT_Dynamic`. Does reusing that symbolic reference re-run the bootstrap? What if you call `desc.resolveConstantDesc(lookup)` again?

**G.** When a static bootstrap argument is a `ClassDesc`, does it need to be resolved according to the class loader/module/Lookup context?

**H.** Why should you not use a full-privilege `Lookup` to resolve a descriptor from an untrusted source?

**Answers:**

- **A:** No. `ofNamed` only creates metadata. Upon resolution, finding the field/BSM also depends on the Lookup's access modes, class loader, and module context.
- **B:** No. `equals` only compares descriptive information; the resolution API does not cache, so a bootstrap with side effects can produce different results.
- **C:** No. `MethodType` is the third parameter for an `invokedynamic`/CallSite bootstrap; a dynamic constant uses `Class<?>`.
- **D:** The public field can be read if the class/module is suitable; the private field is denied when the Lookup no longer has private access.
- **E:** No. `ofCanonical` may return a `ClassDesc` or another specialized descriptor; you should use the `ConstantDesc` interface or check the actual type.
- **F:** The JVM records the resolution result of that constant pool entry and does not re-run the bootstrap for the same symbolic reference. Calling the `resolveConstantDesc` Java API again can run the bootstrap each time.
- **G:** Yes. A class descriptor is not itself a loaded Class; it must be resolved in the appropriate context, which can fail if the class is not found or inaccessible.
- **H:** Because resolution can look up and execute bootstrap code; using a high-privilege Lookup can open up unintended access capabilities.

## 12. Java 17 References

- [Oracle Javadoc — `DynamicConstantDesc`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/DynamicConstantDesc.html): factories, metadata, `resolveConstantDesc`, and no-cache semantics.
- [Oracle Javadoc — `ConstantDesc`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/ConstantDesc.html): symbolic resolution and Lookup context.
- [Oracle Javadoc — `ConstantDescs`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/ConstantDescs.html): `ofConstantBootstrap` and standard BSMs.
- [Oracle Javadoc — `ConstantBootstraps`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html): `getStaticFinal`, `nullConstant`.
- [Oracle Javadoc — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): access permissions, `lookupClass`, `lookupModes`, `dropLookupMode`, and modules.
- [JVMS Java SE 17, `5.4.3.6](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6): dynamic constant/call site resolution algorithm.
- [JVMS Java SE 17, `5.4.4](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4): access control during linking.

**Summary:** `DynamicConstantDesc<T>` is **a descriptor**, not a computed value. `resolveConstantDesc(lookup)` determines the value based on **the Lookup's permissions and resolution environment**, can run the bootstrap, and **does not cache** for subsequent Java API calls. Do not confuse it with `CONSTANT_Dynamic` caching in the runtime constant pool or treat creating a descriptor as proof of permission to access a private member.
