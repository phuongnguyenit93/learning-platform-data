# `getModifiers()` and How to Decode Flags with `Modifier` in Java Reflection

When using Java Reflection to inspect the declaration of a class, method, constructor, or field, we may need to answer: is the member `public`, is it `static`/`final`, is the field `volatile`, is the method `synchronized`? Java does not provide a separate object for each of these keywords in the `getModifiers()` API. Instead, it returns **an `int` integer containing a set of flag bits**. The utility class `java.lang.reflect.Modifier` is used to decode those bits.

Importantly, **flags describe the declaration**; they do not automatically indicate whether a reflective call or access is actually permitted, nor do they represent every class file characteristic or every newer Java keyword.

## 1. What does `getModifiers()` return?

The `getModifiers()` APIs appear on:

| Reflection object | How to get the flags | Element described |
| --- | --- | --- |
| `Class<?>` | `SomeClass.class.getModifiers()` | Class or interface |
| `Field` | `field.getModifiers()` | Data field |
| `Method` | `method.getModifiers()` | Method |
| `Constructor<?>` | `constructor.getModifiers()` | Constructor |
| `Parameter` | `parameter.getModifiers()` | Formal parameter flags, e.g., `final` |

The return value is a **bitmask**, meaning each bit is used to indicate the presence of a flag. If multiple modifiers coexist, they are combined using bitwise OR `|`; for example:

```java
int flags = Modifier.PUBLIC | Modifier.STATIC | Modifier.FINAL;
System.out.println(flags); // 25
```

In this example, `PUBLIC = 0x0001`, `STATIC = 0x0008`, and `FINAL = 0x0010`; OR produces `0x0019`, which is `25` in decimal.

**You should not treat the integer `25` as a formatting contract to display to users.** Decoding with `Modifier` both clarifies the meaning and avoids incorrect integer comparisons.

For example, a declaration `public static final int LIMIT` can be checked with:

```java
Field field = SomeClass.class.getDeclaredField("LIMIT");
int modifiers = field.getModifiers();

boolean publicField = Modifier.isPublic(modifiers);
boolean staticField = Modifier.isStatic(modifiers);
boolean finalField = Modifier.isFinal(modifiers);
String humanReadable = Modifier.toString(modifiers);
```

The snippet above is an **API illustration**, assuming `SomeClass` has a field `LIMIT`; the complete standalone program is in section 5.

## 2. `Modifier`: checking individual flags

`java.lang.reflect.Modifier` is a utility class containing bit constants and `static` methods. Common groups:

| Group | Flag constants | Check method | Where commonly seen |
| --- | --- | --- | --- |
| Access | `PUBLIC`, `PROTECTED`, `PRIVATE` | `isPublic`, `isProtected`, `isPrivate` | Class/member |
| Class-level member | `STATIC` | `isStatic` | Field, method, nested type |
| Change/inheritance restriction | `FINAL` | `isFinal` | Class, field, method |
| Implementation requirement | `ABSTRACT` | `isAbstract` | Class, method |
| Interface marker | `INTERFACE` | `isInterface` | Class representing an interface |
| Synchronization | `SYNCHRONIZED` | `isSynchronized` | Method |
| Native linkage | `NATIVE` | `isNative` | Method |
| Field excluded by default from Java object serialization | `TRANSIENT` | `isTransient` | Field |
| Shared memory semantics | `VOLATILE` | `isVolatile` | Field |
| Floating-point semantics | `STRICT` | `isStrict` | `strictfp` (historical) |

A few semantic notes:

- The access flags `public`, `protected`, and `private` cannot coexist on the same valid declaration. **There is no `PACKAGE_PRIVATE` flag**: the absence of all three flags means *package-private* for an appropriate class/member.
- `Modifier.isInterface(classFlags)` recognizes the interface flag on `Class`; usually `Class.isInterface()` expresses this intent more directly.
- `synchronized` belongs to methods; `volatile` and `transient` belong to fields. Do not check these flags outside their appropriate context.
- `final` is not synonymous with an immutable object; with `final List<String> list`, the reference cannot normally be reassigned, but the contents of the `List` can be mutated.
- `volatile` guarantees the visibility and ordering properties specified by the Java Memory Model; it does **not** make `count++` atomic.
- On Java 17+, `strictfp` no longer changes floating-point expression results as it previously did because floating-point semantics are always strict; you may still encounter this concept when reading older data.

## 3. Two ways to decode: predicates and bitwise operators

### Preferred approach — `Modifier.isXxx(int)`

```java
int flags = field.getModifiers();

if (Modifier.isPrivate(flags)) {
    System.out.println("Field is declared private");
}
if (Modifier.isStatic(flags) && Modifier.isFinal(flags)) {
    System.out.println("Field has both static and final");
}
```

Each `isXxx` returns `true` if the corresponding flag is present, regardless of other flags. This is the most readable approach when checking policies or generating metadata.

### Bitwise approach — using `Modifier.Xxx` constants

The constants are distinct bits; checking a single flag:

```java
boolean isStatic = (flags & Modifier.STATIC) != 0;
```

Checking **all** required flags simultaneously:

```java
int required = Modifier.PUBLIC | Modifier.STATIC | Modifier.FINAL;
boolean containsAll = (flags & required) == required;
```

Checking **at least one** of the required flags:

```java
int either = Modifier.PUBLIC | Modifier.PROTECTED;
boolean containsAny = (flags & either) != 0;
```

Evaluating package-private for the member under inspection:

```java
boolean packagePrivate = !Modifier.isPublic(flags)
        && !Modifier.isProtected(flags)
        && !Modifier.isPrivate(flags);
```

**Classic mistake:** writing `flags == Modifier.PUBLIC` to ask whether a member is `public`. If a field is `public static final`, that check is false because the integer also has the `STATIC` and `FINAL` bits set. Similarly, `(flags & required) != 0` only proves *at least one flag* is present, not *all* of them.

Do not use bitwise negation `~flags` and then decode it as if it were a valid set of Java modifiers; bits outside the defined group may appear.

## 4. Displaying flags with `Modifier.toString()`

`Modifier.toString(int)` converts a bitmask into a space-separated string of ordered keywords:

```java
int flags = Modifier.PUBLIC | Modifier.STATIC | Modifier.FINAL;
System.out.println(Modifier.toString(flags));
// public static final
```

If none of the flags represented by `toString` are present, the string can be empty. That does **not** say the class/member "does not exist" or "has no characteristics."

`Modifier.toString()` is a **decoder and formatter**, not a validator for whether a Java declaration is legal. You can OR conflicting flags such as `PUBLIC | PRIVATE` and still get a string, even though valid Java source code cannot declare a member as both `public` and `private`.

The methods `Modifier.classModifiers()`, `interfaceModifiers()`, `fieldModifiers()`, `methodModifiers()`, `constructorModifiers()`, and `parameterModifiers()` return the mask of source modifiers applicable to *the corresponding declaration kind*. They are useful when you need to filter a group of flags before displaying them:

```java
int fieldWords = field.getModifiers() & Modifier.fieldModifiers();
System.out.println(Modifier.toString(fieldWords));
```

Do not treat `Modifier.toString()` as a complete record of every access flag in a class file: some internal flags, `synthetic`, `bridge`, `varargs`, `enum`, and newer attributes are not necessarily represented by `Modifier` keywords.

## 5. Complete Java 17+ example

Save the following content to `ModifierDemo.java`, then run it with `javac` and `java`. The program includes a nested class, several fields/methods with different modifiers, a constructor, and a default method in an interface.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ModifierDemo {
    public static class Sample {
        public static final int MAX = 10;
        private transient String token;
        protected volatile long revision;

        public Sample() {}

        public synchronized void refresh() {}

        private native void nativeHook();
    }

    public interface Processor {
        default void process() {}
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Sample.class;
        System.out.println("class: "
                + Modifier.toString(type.getModifiers()));

        Field max = type.getDeclaredField("MAX");
        int maxFlags = max.getModifiers();
        System.out.println("MAX: " + Modifier.toString(maxFlags));
        System.out.println("MAX public/static/final: "
                + (Modifier.isPublic(maxFlags)
                && Modifier.isStatic(maxFlags)
                && Modifier.isFinal(maxFlags)));

        int required = Modifier.PUBLIC | Modifier.STATIC | Modifier.FINAL;
        System.out.println("MAX bitmask: "
                + ((maxFlags & required) == required));

        Field token = type.getDeclaredField("token");
        System.out.println("token: "
                + Modifier.toString(token.getModifiers()));

        Field revision = type.getDeclaredField("revision");
        System.out.println("revision: "
                + Modifier.toString(revision.getModifiers()));

        Method refresh = type.getDeclaredMethod("refresh");
        System.out.println("refresh: "
                + Modifier.toString(refresh.getModifiers()));
        System.out.println("refresh synchronized: "
                + Modifier.isSynchronized(refresh.getModifiers()));

        Method hook = type.getDeclaredMethod("nativeHook");
        System.out.println("nativeHook: "
                + Modifier.toString(hook.getModifiers()));

        Constructor<?> ctor = type.getDeclaredConstructor();
        System.out.println("constructor: "
                + Modifier.toString(ctor.getModifiers()));

        Method process = Processor.class.getDeclaredMethod("process");
        System.out.println("default method modifiers: "
                + Modifier.toString(process.getModifiers()));
        System.out.println("isDefault(): " + process.isDefault());

        System.out.println("interface flag: "
                + Modifier.isInterface(Processor.class.getModifiers()));
    }
}
```

Commands:

```bash
javac ModifierDemo.java
java ModifierDemo
```

Output:

```text
class: public static
MAX: public static final
MAX public/static/final: true
MAX bitmask: true
token: private transient
revision: protected volatile
refresh: public synchronized
refresh synchronized: true
nativeHook: private native
constructor: public
default method modifiers: public
isDefault(): true
interface flag: true
```

Explanation:

1. `Sample` is a **member class** declared `public static`, so `Class.getModifiers()` reflects both flags. For a top-level class, the `static` modifier cannot appear as in the member class example.
2. `MAX` carries the three flags `public static final`; using three predicates or ANDing with the mask both return the correct result.
3. `token` is declared `private transient`; `revision` is declared `protected volatile`. The flags reflect the declaration rather than proving serialization logic or thread safety of the whole program.
4. `refresh` has the `synchronized` flag; `nativeHook` has the `native` flag, **without needing to call** the native method to read metadata. The example only reads the name and modifiers, so no native library is needed.
5. The default method `process()` has `getModifiers()` showing `public`, while `isDefault() == true`. The `default` keyword of an interface method **does not have a `Modifier.DEFAULT` constant**.

`getDeclaredField`, `getDeclaredMethod`, and `getDeclaredConstructor` in the example all only **retrieve metadata**. Retrieving metadata of a `private` member does not mean reading/writing/invoking that member is already permitted.

## 6. Distinguishing *declared* vs *public/inherited* before reading modifiers

The member-selection methods affect **whose** flags you will decode:

| API | Key search scope |
| --- | --- |
| `getDeclaredFields()` | Directly declared fields, all access levels; does not include inherited fields |
| `getFields()` | `public` fields within visible member scope, including inherited ones |
| `getDeclaredMethods()` | Directly declared methods, all access levels; does not include inherited methods |
| `getMethods()` | `public` methods reflected from the class/interface and inheritance |
| `getDeclaredConstructors()` | Constructors declared in the class, all access levels |
| `getConstructors()` | `public` constructors of the class; constructors are not inherited |

Therefore, if you write a metadata scanner and want to find `private transient` fields, you usually must use `getDeclaredFields()`. If you only scan `getFields()`, you will miss `private` fields.

Sketch of a filter (assuming `type` is the `Class<?>` to scan):

```java
for (Field field : type.getDeclaredFields()) {
    int mod = field.getModifiers();
    if (Modifier.isStatic(mod) && Modifier.isFinal(mod)) {
        System.out.println(field.getName() + ": "
                + Modifier.toString(mod));
    }
}
```

For broader APIs, consider compiler-generated fields/methods and bridge methods; do not assume every element from `getDeclaredXxx()` corresponds verbatim to a visible declaration in source code.

## 7. Characteristics you should not infer solely from `Modifier`

Java has states or markers that require dedicated APIs:

| Characteristic to ask about | Appropriate API | Why `Modifier` is not enough |
| --- | --- | --- |
| Default method in an interface | `Method.isDefault()` | There is no `Modifier.DEFAULT` |
| Bridge method generated by compiler | `Method.isBridge()` | Bridge is a method/class-file characteristic |
| Method with varargs | `Executable.isVarArgs()` | There is no `Modifier.VARARGS` |
| Compiler-generated member | `Member.isSynthetic()` | There is no `Modifier.isSynthetic` predicate |
| Class is an enum | `Class.isEnum()` | There is no `Modifier.ENUM` |
| Class is an annotation type | `Class.isAnnotation()` | There is no `Modifier.ANNOTATION` |
| Class is a record | `Class.isRecord()` | There is no `Modifier.RECORD` |
| Class/interface is sealed | `Class.isSealed()` | There is no `Modifier.SEALED` |

Note: the APIs above do not mean all of them are "modifiers" in Java syntax; some represent class-file information or language-model characteristics.

Starting in Java 20, the `Class.accessFlags()` and `Member.accessFlags()` APIs provide a typed `AccessFlag` set, convenient for reading access flags beyond the classic modifier set. However, **in a project that must run on Java 17**, use `getModifiers()` + `Modifier` and the available dedicated checks; do not call `accessFlags()` if Java 17 support is required.

`Modifier.STRICT`/`isStrict` also needs to be interpreted by Java version: since Java 17, floating-point expressions are strict by default, so the presence or absence of this flag is not a test for "whether the code computes floating-point numbers accurately."

## 8. Modifiers are not the same as effective access rights

These are two different questions:

1. **What does the member declare?** Read `field.getModifiers()`, then `Modifier.isPrivate(...)` or `Modifier.isPublic(...)`.
2. **Can this caller access the member on a specific receiver?** Use `AccessibleObject.canAccess(receiver)`, considering Java access check rules and module boundaries.

Example:

```java
Field field = type.getDeclaredField("token");

boolean declaredPrivate =
        Modifier.isPrivate(field.getModifiers());

// 'instance' is an appropriate object for the instance field 'token'.
boolean currentlyAccessible = field.canAccess(instance);
```

`declaredPrivate` does not change when accessibility checks are suppressed. If you try to access a `private` field from an unauthorized caller, merely knowing the `private` flag does not make the access API succeed. `trySetAccessible()` can request suppressing Java language access checks **when the module system allows it**; it may return `false`. `setAccessible(true)` may throw `InaccessibleObjectException`. These settings also do not turn `private` into `public` and do not make `getModifiers()` return a different value.

Conversely, a member with the `public` flag may still be inaccessible from another module if its enclosing class is not accessible or the package is not appropriately `exports`ed by the module. Therefore, **do not use `Modifier.isPublic(member.getModifiers())` as the sole decision that a reflective invocation will succeed**.

If the goal is to check accessibility before a call, identify the receiver, member kind (static/instance), declaring class, and module/caller context. `canAccess(null)` is appropriate for a static member or constructor, whereas an instance member requires a matching receiver; passing the wrong receiver causes an error.

## 9. Common mistakes and how to fix them

### Mistake A — Comparing the integer mask directly

Wrong:

```java
boolean isPublic = field.getModifiers() == Modifier.PUBLIC;
```

A `public static` field is also `public`, yet the expression returns false. Correct: `Modifier.isPublic(field.getModifiers())` or `(mask & Modifier.PUBLIC) != 0`.

### Mistake B — Confusing "has any flag" with "has all flags"

Wrong when checking both `static` and `final` simultaneously:

```java
boolean staticAndFinal =
        (field.getModifiers() & (Modifier.STATIC | Modifier.FINAL)) != 0;
```

This expression is also true when only `static` is present. Fix:

```java
int required = Modifier.STATIC | Modifier.FINAL;
boolean staticAndFinal = (field.getModifiers() & required) == required;
```

### Mistake C — Inferring access from the `public` flag

`public` is only part of the conditions of Java's access control mechanism. With reflection, the caller, package, declaring class, and Java Platform Module System are all involved. Check `canAccess` or `trySetAccessible` when you actually need to operate on the member.

### Mistake D — Thinking `final`/`volatile` are general solutions for immutability or thread safety

`final` protects specific constraints on a variable, method, or class depending on context. `volatile` specifies visibility/ordering for a field; for read-modify-write operations like `count++`, appropriate synchronization or atomic tools are required.

### Mistake E — Displaying `Modifier.toString(mask)` as complete metadata

A method may be `bridge`, `synthetic`, or `default` without the modifier string recording enough detail. Check `isBridge()`, `isSynthetic()`, `isDefault()` accordingly; for `sealed` and `record`, use the APIs on `Class`.

### Mistake F — Choosing the wrong member set

Calling `getMethods()` and concluding a class has no `private` methods is wrong because that method only returns `public` methods. Use `getDeclaredMethods()` to scan directly declared methods, and handle inheritance separately when needed.

## 10. Checklist when writing Reflection tools

When writing a class analyzer, method registration framework, or field inspection tool:

1. Identify whether you want metadata for a **class, field, method, constructor, or parameter**.
2. Choose `getDeclaredXxx` or `getXxx` matching the member scope.
3. Store `int modifiers = member.getModifiers()` and use `Modifier.isXxx` for single conditions; use a bitmask when combined checks are needed.
4. Print `Modifier.toString(modifiers)` for readability; do not use this string as a substitute for all API information.
5. Supplement with specialized APIs: `isSynthetic`, `isBridge`, `isDefault`, `isVarArgs`, `isRecord`, `isSealed` depending on your goal and Java version.
6. Before actually accessing/invoking, perform an **access check** for the exact caller/receiver/module; declaration flags are not operational permission.

**Key takeaway:** `getModifiers()` returns **bits describing the declaration**; `Modifier.isXxx()` is how to check the meaning of each bit; `Modifier.toString()` is a familiar way to display them. Reading modifiers accurately requires knowing **which member** is being inspected and **whether the question is about metadata or actual access permission**.
