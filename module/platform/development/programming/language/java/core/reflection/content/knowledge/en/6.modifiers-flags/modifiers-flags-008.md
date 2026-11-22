# AccessFlag, accessFlags(), and JDK Version Differences in Java Reflection

## 1. From Java modifiers to JVM access flags

A Java declaration can have keywords such as `public`, `private`, `static`, `final`, `abstract`, `synchronized`, and `volatile`. When compiled, the JVM class file stores many properties of classes, fields, methods, and other structures as **bit flags**. However, not every concept in Java syntax corresponds to a bit flag, and some flags appear only at the JVM level.

Two perspectives must be separated:

- **Java language modifiers**: what `java.lang.reflect.Modifier` and `getModifiers()` primarily model, suitable when reading access rights, `static`, `final`, `volatile`, etc. per Java language rules.
- **JVM access/module flags**: flags at specific locations in the class file, including `SYNTHETIC`, `BRIDGE`, `VARARGS`, `ANNOTATION`, `ENUM`, `MANDATED`, `MODULE`, and module-related flags. Starting in **JDK 20**, the `java.lang.reflect.AccessFlag` API along with `accessFlags()` brings this perspective into core reflection.

For example, a compiler-generated bridge method has the `ACC_BRIDGE` flag without a directly corresponding Java keyword; meanwhile `sealed` is represented by the class file's `PermittedSubclasses` metadata, with **no** `ACC_SEALED` flag.

You must not treat every flag simply as a "modifier written before a declaration." A class, field, method, method parameter, or module entry has **different sets of valid flags**.

## 2. Two APIs: getModifiers() and accessFlags()

### The older and still useful way: getModifiers() + Modifier

`Class.getModifiers()`, `Field.getModifiers()`, `Method.getModifiers()`, `Constructor.getModifiers()`, and `Parameter.getModifiers()` return a bit-mask `int`. Static methods in `Modifier` decode them according to language intent:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

class Demo {
    public static final int LIMIT = 10;
}

Field field = Demo.class.getDeclaredField("LIMIT");
int modifiers = field.getModifiers();

boolean isPublic = Modifier.isPublic(modifiers);
boolean isStatic = Modifier.isStatic(modifiers);
boolean isFinal = Modifier.isFinal(modifiers);
String readable = Modifier.toString(modifiers);
```

The snippet above is an **illustrative code fragment** to place inside a method declaring `throws ReflectiveOperationException`; this file alone is not a standalone runnable program. `Modifier.toString(modifiers)` is useful when displaying source modifiers, yet `getModifiers()` is not a reader for all flags in a class file.

Advantages of `getModifiers()`: available since older JDKs, easy to check common modifiers, compatible with libraries running on JDK 8/11/17. If you only need `public/static/final` for a field, it is often a sensible choice.

### Since JDK 20: accessFlags()

`accessFlags()` returns an unmodifiable `Set<AccessFlag>`, for example checking:

```java
Set<AccessFlag> flags = field.accessFlags(); // JDK 20+
boolean isVolatile = flags.contains(AccessFlag.VOLATILE);
```

The set may be empty; do not assume elements appear in a fixed order when printing the `Set`. Compare using `contains`/`containsAll` rather than converting to strings. Because `AccessFlag` is an `enum`, flag names clearly distinguish `VOLATILE` (field) from `BRIDGE` (method) even when their bit masks collide.

Common call sites since JDK 20:

| Reflection object | How to read flags | Notes |
| --- | --- | --- |
| `Class<?>` | `clazz.accessFlags()` | Class/interface flags; arrays, primitives, and `void` are handled per `Class` rules. |
| `Field` | `field.accessFlags()` | E.g., `PUBLIC`, `STATIC`, `FINAL`, `VOLATILE`, `TRANSIENT`, `ENUM`, `SYNTHETIC` depending on the field. |
| `Method` | `method.accessFlags()` | E.g., `SYNCHRONIZED`, `NATIVE`, `ABSTRACT`, `BRIDGE`, `VARARGS`, `SYNTHETIC`. |
| `Constructor<?>` | `constructor.accessFlags()` | Inherits implementation from `Executable`; applies flags valid for constructors. |
| `Parameter` | `parameter.accessFlags()` | Parameter metadata; must consider whether parameter data is present in the class file. |

`Member` defines `default accessFlags()` for API compatibility, yet the default implementation throws `UnsupportedOperationException`. The standard core reflection implementations of `Field`/`Method`/`Constructor` provide this method; do not assume every custom `Member` implementation supports it.

**Remember:** `accessFlags()` does not return source modifiers as strings, does not automatically check whether you have `setAccessible` permission, and does not replace every specialized API such as `Method.isBridge()`, `Class.isRecord()`, or `Class.isSealed()`.

## 3. Runnable Java 20+ program comparing the two APIs

Save to `AccessFlagLessonDemo.java`:

```java
import java.lang.reflect.AccessFlag;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;

public class AccessFlagLessonDemo {
    static class Sample {
        public volatile int state;
        public synchronized void log(String... values) { }
    }

    interface Formatter<T> { T format(T value); }

    static final class TextFormatter implements Formatter<String> {
        public String format(String value) { return value; }
    }

    public static void main(String[] args) throws Exception {
        Field field = Sample.class.getDeclaredField("state");
        Method method = Sample.class.getDeclaredMethod("log", String[].class);
        Method bridge = Arrays.stream(TextFormatter.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .findFirst()
                .orElseThrow();

        System.out.println("field Modifier.isVolatile = "
                + Modifier.isVolatile(field.getModifiers()));
        System.out.println("field AccessFlag.VOLATILE = "
                + field.accessFlags().contains(AccessFlag.VOLATILE));
        System.out.println("method VARARGS = "
                + method.accessFlags().contains(AccessFlag.VARARGS));
        System.out.println("method SYNCHRONIZED = "
                + method.accessFlags().contains(AccessFlag.SYNCHRONIZED));
        System.out.println("bridge BRIDGE = "
                + bridge.accessFlags().contains(AccessFlag.BRIDGE));
        System.out.println("field mask 0x0040 = "
                + AccessFlag.maskToAccessFlags(0x0040, AccessFlag.Location.FIELD));
        System.out.println("method mask 0x0040 = "
                + AccessFlag.maskToAccessFlags(0x0040, AccessFlag.Location.METHOD));
    }
}
```

Compile/run with JDK 20 or later; the example was compiled and run successfully with JDK 24:

```bash
javac AccessFlagLessonDemo.java
java AccessFlagLessonDemo
```

Exact stdout:

```text
field Modifier.isVolatile = true
field AccessFlag.VOLATILE = true
method VARARGS = true
method SYNCHRONIZED = true
bridge BRIDGE = true
field mask 0x0040 = [VOLATILE]
method mask 0x0040 = [BRIDGE]
```

Because `Sample.state` is declared `volatile`, both `Modifier.isVolatile` and the `AccessFlag` set recognize this property. Method `log(String... values)` is both a varargs method and `synchronized`. When the generic interface `Formatter<T>` undergoes type erasure, it requires a `format(Object)` adapter: the compiler generates a **bridge method** in `TextFormatter`. Both `Method.isBridge()` and `accessFlags().contains(AccessFlag.BRIDGE)` confirm it. This is a JVM flag that Java authors do not normally type as a modifier in source.

The last two lines are especially important: the same bit `0x0040` at location `FIELD` means `VOLATILE`, whereas at location `METHOD` it means `BRIDGE`. Decoding without context can produce seriously wrong results.

## 4. AccessFlag enum and interpreting by Location

`AccessFlag` represents flags such as `PUBLIC` (`0x0001`), `STATIC` (`0x0008`), `FINAL` (`0x0010`), `VOLATILE` (`0x0040`), `BRIDGE` (`0x0040`), `TRANSIENT` (`0x0080`), `VARARGS` (`0x0080`), `SYNTHETIC` (`0x1000`), `ANNOTATION` (`0x2000`), and `ENUM` (`0x4000`).

Typical groups:

| Location in class file | Some flags you may see | Explanation |
| --- | --- | --- |
| `CLASS` / `INNER_CLASS` | `PUBLIC`, `FINAL`, `INTERFACE`, `ABSTRACT`, `ANNOTATION`, `ENUM`, `SYNTHETIC`; `STATIC` in nested class info | Class metadata and nested-type info have different rules. |
| `FIELD` | `PUBLIC`, `PRIVATE`, `STATIC`, `FINAL`, `VOLATILE`, `TRANSIENT`, `SYNTHETIC`, `ENUM` | `VOLATILE` and `TRANSIENT` are only meaningful on fields respectively. |
| `METHOD` | `PUBLIC`, `PRIVATE`, `STATIC`, `FINAL`, `SYNCHRONIZED`, `BRIDGE`, `VARARGS`, `NATIVE`, `ABSTRACT`, `STRICT`, `SYNTHETIC` | `STRICT` depends on class-file generation. |
| `METHOD_PARAMETER` | `FINAL`, `SYNTHETIC`, `MANDATED` | Flag model in the `MethodParameters` entry, not identical to `METHOD`. |
| `MODULE`, `MODULE_REQUIRES`, `MODULE_EXPORTS`, `MODULE_OPENS` | `OPEN`, `TRANSITIVE`, `STATIC_PHASE`, `SYNTHETIC`, `MANDATED` depending on entry | Module descriptor flags; not Java field `public/private`. |

**Not every combination in the table is valid.** These are example flags by group, while the JVMS dictates exact locations, combinations, and class-file versions.

Use `AccessFlag.Location` to specify the **location** when decoding bits:

```java
AccessFlag.maskToAccessFlags(0x0040, AccessFlag.Location.FIELD);
AccessFlag.maskToAccessFlags(0x0040, AccessFlag.Location.METHOD);
```

The two calls return a set containing only `VOLATILE` and a set containing only `BRIDGE`, respectively. For a mask containing bits undefined at the requested location, `maskToAccessFlags` may throw `IllegalArgumentException`. Do not write your own loop over all enum constants to guess meaning from `(mask & flag.mask()) != 0` without checking location.

Core methods:

- `flag.mask()`: returns the int mask, **not a unique identifier** for the flag.
- `flag.sourceModifier()`: indicates whether the flag has a direct corresponding modifier in the Java language. This does not say the flag is present on a specific object.
- `flag.locations()`: set of valid locations in the current class-file version modeled by the API. The set may be empty for obsolete flags.
- `flag.locations(ClassFileFormatVersion version)`: determines valid locations for the chosen class-file generation.
- `AccessFlag.maskToAccessFlags(mask, location)`: interprets bits in context for the current version; since JDK 25 there is an overload accepting an additional `ClassFileFormatVersion`.

Example of why `mask` cannot be treated as identity:

```java
System.out.println(AccessFlag.VOLATILE.mask() == AccessFlag.BRIDGE.mask());
// true

System.out.println(AccessFlag.TRANSIENT.mask() == AccessFlag.VARARGS.mask());
// true
```

These are two standalone illustrative expression lines, not a complete Java file.

## 5. Differences across JDK versions

| JDK line | APIs and consequences |
| --- | --- |
| **JDK 8, 11, 17, 19, and older than 20** | **No** `java.lang.reflect.AccessFlag` or `accessFlags()`. Use `getModifiers()` + `Modifier`, `isBridge()`/`isSynthetic()`/`isVarArgs()`, and class-file reading tools when full JVM flags are needed. |
| **JDK 20** | Added `AccessFlag`, `AccessFlag.Location`, `Class.accessFlags()`, `Member.accessFlags()`, and `Parameter.accessFlags()`. Includes `mask()`, `sourceModifier()`, `locations()`, `locations(ClassFileFormatVersion)`, `maskToAccessFlags(mask, location)`. |
| **JDK 21** | The APIs above are available in an LTS release; the code example in this lesson runs on JDK 21. Suitable if your project requires LTS and wants enum-based flag access. |
| **JDK 24** | Added the standard **Class-File API** in package `java.lang.classfile` (JEP 484), including the `AccessFlags` interface for reading/transforming class files. `java.lang.classfile.AccessFlags` and enum `java.lang.reflect.AccessFlag` are **two APIs with different purposes**. |
| **JDK 25** | Added overload `AccessFlag.maskToAccessFlags(int, AccessFlag.Location, ClassFileFormatVersion)` to interpret a mask for a specified class-file version. APIs may continue evolving in newer JDKs; check the Javadoc for the exact version you run. |

**Read "Since" accurately:** `AccessFlag` has `Since: 20`. When a JDK 25 Javadoc page shows an overload with `Since: 25`, that is when **that overload** appeared, not when the entire new enum was created. Avoid concluding the API only existed since JDK 21 just because you are reading Java 21 documentation.

**The running JDK version does not equal the version of every loaded class file.** For example, you can run JDK 21 to load a class compiled with `javac --release 17`. You need to check the **class file major version** if you want to analyze flags that existed at the time the class file was built. `AccessFlag.locations(cffv)` describes the rules of the queried class-file generation; it does not change the version of the bytecode being inspected.

### Historical case: ACC_STRICT and strictfp

The `AccessFlag.STRICT` flag (mask `0x0800`) corresponds to `ACC_STRICT` on **methods** and is only defined by the JVMS for class-file major versions **46–60**, corresponding to Java SE 1.2–16. Since Java 17, floating-point arithmetic semantics are always strict per JEP 306; do not assume a method compiled on modern JDKs still must carry `ACC_STRICT` when expressing `strictfp`-like intent.

To analyze the legacy format on JDK 20+, query:

```java
import java.lang.reflect.AccessFlag;
import java.lang.reflect.ClassFileFormatVersion;

boolean oldVersionAllowsStrict =
        AccessFlag.STRICT.locations(ClassFileFormatVersion.RELEASE_16)
                .contains(AccessFlag.Location.METHOD);

boolean newVersionAllowsStrict =
        AccessFlag.STRICT.locations(ClassFileFormatVersion.RELEASE_17)
                .contains(AccessFlag.Location.METHOD);
```

This is an **illustrative code snippet** inside a class/method. `oldVersionAllowsStrict` is `true`, `newVersionAllowsStrict` is `false`. This describes the **class-file format**; do not use it to draw conclusions about arithmetic behavior of a current application.

### Compilation and binary compatibility

An application targeting JDK 17 **cannot compile source** importing `java.lang.reflect.AccessFlag` with `javac --release 17`, even if you have JDK 24 installed. This API did not exist in Java 17. If the runtime target is Java 17, stick to `Modifier` and compatible APIs or use a dedicated build/module approach to read class files.

If code is compiled with JDK 21 and calls `accessFlags()`, copying the compiled class to JRE 17 does not make it compatible: JRE 17 lacks the API (and newer target class bytecode may be rejected earlier with `UnsupportedClassVersionError`). Do not try merely "removing the import" to fix compatibility errors.

## 6. AccessFlag, Modifier, and other state-checking APIs are not synonymous

### Synthetic, bridge, and varargs

- `Class.isSynthetic()`, `Field.isSynthetic()`, `Method.isSynthetic()`, or `Member.isSynthetic()` answers the general question about synthetic; `AccessFlag.SYNTHETIC` reflects the access flag at the corresponding location. Synthetic is not a modifier a user types before a Java declaration.
- `Method.isBridge()` is the longstanding way to identify bridge methods; `method.accessFlags().contains(AccessFlag.BRIDGE)` is the enum representation on JDK 20+.
- `Executable.isVarArgs()` indicates a method/constructor uses variable arity; `AccessFlag.VARARGS` is the corresponding class-file flag. **A trailing `String[]` parameter does not automatically make a method varargs**; it must have a `String...` declaration or the flag from the class file.
- `Parameter.isImplicit()`, `Parameter.isSynthetic()`, and `Parameter.accessFlags()` serve parameter metadata. Part of parameter name/flag info depends on the `MethodParameters` attribute emitted by the compiler, so do not assume every older class file stores all of it.

### Sealed and record have no corresponding AccessFlag

For Java 17+:

```java
boolean isSealed = SomeType.class.isSealed();
boolean isRecord = SomeType.class.isRecord();
```

This is an illustrative snippet: `SomeType` represents a project-defined class. There is no corresponding `AccessFlag.SEALED` or `AccessFlag.RECORD`. `sealed` uses `PermittedSubclasses` metadata, while record uses the `Record` attribute and compilation conventions. Do not deduce record types from `FINAL`, or sealed types from `ABSTRACT`.

### Access flags differ from currently permitted reflective access

`AccessFlag.PRIVATE` indicates a member is private at the metadata level. It does not grant permission to read/write private fields, call private methods, or open modules. `AccessibleObject.canAccess`, `trySetAccessible()`, and module/JPMS rules still determine whether deep reflective access succeeds. Likewise, `OPEN` in a module is module metadata rather than equivalent to `private` on a field.

### Classes, nested classes, primitives, and arrays have exceptions

`Class.accessFlags()` for arrays and primitives/`void` has its own inferred rules per the Javadoc; do not assume it always reads a raw bit list directly from a corresponding `ClassFile` (primitives/void and arrays have no standalone class file like ordinary classes). For nested types, `STATIC` may be recorded in the `InnerClasses` attribute; distinguish `CLASS` and `INNER_CLASS` when decoding class files manually.

For example, `String[].class.accessFlags()` does not have the same file-structure inspection meaning as raw-reading a `String[].class` on disk: no `String[].class` file exists as a separate class declaration to open.

## 7. When you need to inspect the real class file: right tools and APIs

Reflection works on **already loaded** `Class`/`Field`/`Method` objects; it presents a view normalized by Java APIs. If the task is analyzing bytecode, byte-level flags, versions, or attributes, better choices are:

1. `javap -v SomeType`: inspect major version, `flags: (0x...)`, synthetic/bridge methods, and attributes. For the `AccessFlagLessonDemo` example, you can run `javap -v AccessFlagLessonDemo$TextFormatter`; shells have `$` escaping rules, so quote the class name appropriately. Output can be long—actively look for `flags` lines.
2. Starting in **JDK 24**, use `java.lang.classfile` and `AccessFlags` when you need structured parsing/transformation of class files in Java code. This is the Class-File API, not the `accessFlags()` method on reflection objects.
3. For systems still running JDK 17, you can use `javap` or a compatible bytecode library (e.g., ASM supporting the class-file version) when you genuinely need bridge/synthetic flags and attributes beyond `Modifier`'s scope.

Do not treat `getModifiers()` as a raw flag mask for every `AccessFlag.Location`. Where bits collide with different meanings, or JVM methods have bridge/synthetic, such a "generic" conversion is not guaranteed accurate. Nor should `AccessFlag.maskToAccessFlags` be treated as a permission check under `SecurityManager` or module access.

## 8. Workflow for choosing how to read flags

**If checking familiar modifiers and still supporting JDK 17:** use `Modifier.isPublic(field.getModifiers())`, `Modifier.isStatic(...)`, `Modifier.isFinal(...)`. For bridge/varargs/synthetic, use dedicated APIs such as `isBridge()`/`isVarArgs()`/`isSynthetic()`.

**If running JDK 20+ and wanting clear flag names:** use `field.accessFlags().contains(AccessFlag.VOLATILE)`, `method.accessFlags().contains(AccessFlag.BRIDGE)`. This easily avoids mask-collision bugs.

**If given a raw bit number:** first identify the exact `AccessFlag.Location`; next determine the class-file generation. On JDK 25+ you can use the three-argument overload to decode accurately for a version; on earlier JDKs check existing API limits along with JVMS documentation if analyzing class files from another generation.

**If needing record/sealed structure or non-access-flag metadata:** query specialized APIs (`isRecord()`, `isSealed()`) or read the full class file. Do not try to "invent" undefined flags.

**If reading fields/methods from a framework:** separate "what flags are declared" from "can it be reflectively accessed." They are two independent questions.

## 9. Common mistakes and self-check exercises

1. **Calling `accessFlags()` on JDK 17:** does not compile; the API was introduced in JDK 20.
2. **Swapping meanings of `0x0040`:** fields use `VOLATILE`, methods use `BRIDGE`.
3. **Trusting `getModifiers()` as all raw class flags:** the API leans toward Java modifiers and does not replace specialized flag/attribute APIs.
4. **Assuming `sealed` and `record` are `AccessFlag` values:** in fact other metadata/APIs must be used.
5. **Guessing flags solely from the runtime JDK:** the inspected class file may have been built with `--release` for an older generation.
6. **Depending on `Set` print order:** check with `contains` or set equality, not ordering.
7. **Understanding `SYNTHETIC` as "anything the compiler creates":** the JVMS sets flags/attributes under specific rules; rely only on metadata read from class files/APIs, not guessing via `$` names or code-generation patterns.
8. **Forgetting the difference between reading metadata and accessing private members:** flags do not unlock Reflection access or bypass module rules.

Self-check:

- `AccessFlag.TRANSIENT.mask() == AccessFlag.VARARGS.mask()` is `true`, so from a mask number alone can we conclude the flag? **No**, location is required.
- Does `AccessFlag.STRICT.locations(ClassFileFormatVersion.RELEASE_17)` contain `METHOD`? **No**, because `ACC_STRICT` only applies up to major version 60.
- Can both `method.accessFlags().contains(AccessFlag.BRIDGE)` and `method.isBridge()` be used on JDK 17? **No**: `isBridge()` existed earlier, while `accessFlags()` is only from JDK 20.
- If a class is a `record` yet has no `AccessFlag.RECORD` flag, is that a contradiction? **No**: record characteristics are represented outside the access flags set.

## 10. Official references

- [Oracle Javadoc Java 20 — AccessFlag (Since: 20)](https://docs.oracle.com/en/java/javase/20/docs/api/java.base/java/lang/reflect/AccessFlag.html)
- [Oracle Javadoc Java 21 — AccessFlag and Location](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessFlag.html)
- [Oracle Javadoc Java 21 — Class.accessFlags()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#accessFlags())
- [Oracle Javadoc Java 21 — Modifier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Modifier.html)
- [Oracle Javadoc Java 25 — AccessFlag and ClassFileFormatVersion overload](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessFlag.html)
- [Dev.java — Reading Modifiers](https://dev.java/learn/api/reflection-method-handles/reflection/modifiers/)
- [JEP 484 — Class-File API (JDK 24)](https://openjdk.org/jeps/484)
- [JEP 306 — Restore Always-Strict Floating-Point Semantics (JDK 17)](https://openjdk.org/jeps/306)
