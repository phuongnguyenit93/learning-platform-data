# TypeNotPresentException, EnumConstantNotPresentException, and Annotation Contract Change Errors in Java

## 1. The Problem: An Annotation That Once Compiled Successfully Now Fails When Read

Java annotations are **metadata encoded into class files** according to the `@Retention` policy. When the retention is `RUNTIME`, a program can retrieve the annotation via reflection and invoke its elements (annotation elements), such as `config.provider()`, `config.mode()`, or `config.level()`.

Risk arises when **a class containing an annotation was compiled against library version A**, while at runtime only **an incompatible library version B** is present. Java may be able to load the compiled class and may even return an object representing the annotation; however, when reading an element, the JVM/reflection library can no longer decode the old data according to the new definition.

Two core errors:

- **`java.lang.TypeNotPresentException`**: the annotation stores a reference to a type that can no longer be resolved at the time the metadata is read or in a similar context. For an element of type `Class<?>`, for example `provider = OldProvider.class`, if `OldProvider` is no longer present at runtime, retrieving `provider()` may throw this error.
- **`java.lang.EnumConstantNotPresentException`**: the metadata stores the name of an enum constant, but the enum type available at runtime **does not contain that constant**. For example, the old annotation stored `Mode.LEGACY`, whereas the new `Mode` only has `BASIC`.

Other errors reflect **changes to the annotation type's contract**:

- **`java.lang.annotation.AnnotationTypeMismatchException`**: the value encoded in the class file **is incompatible with the new return type** of an annotation element, for example changing `int level()` to `String level()`.
- **`java.lang.annotation.IncompleteAnnotationException`**: the new annotation definition requires an element that **has no value** in the old metadata and **has no default** to fall back on, for example adding `String owner();`.
- In addition, you may encounter `NoSuchMethodError` or other linkage errors when **code invokes an accessor whose name/binary signature was changed**, which is distinct from errors when decoding annotation values.

What they have in common: **compiling successfully at one point in time does not guarantee that old metadata can always be read with dependencies from another point in time**. This lesson will explain the causes, how to reproduce the issue using Java 17, the differences among the exceptions, and testing practices when releasing a library.

## 2. An Annotation Element Is Not an Ordinary Java Field

Example annotation definition:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Contract {
    Class<?> provider();
    Mode mode();
}
~~~

This is **an illustrative declaration snippet**; the `Mode` enum and related declarations are required to compile a complete program.

Annotation elements have a syntax similar to parameterless methods, but the values `provider = SomeType.class` and `mode = Mode.LEGACY` are encoded by the compiler into the metadata of **the site where the annotation is applied**, rather than becoming instance fields on a business object.

When executing:

~~~java
Contract contract = SomeClass.class.getAnnotation(Contract.class);
Class<?> type = contract.provider();
Mode mode = contract.mode();
~~~

the program reads a **runtime representation** of the annotation. On common JDKs, decoding unresolvable values may be deferred until the corresponding element is invoked. Therefore, merely seeing `contract != null` **does not prove** that all elements are valid.

The "typically throws when calling the accessor" behavior must not be treated as a guarantee that every implementation, every class loader, and every form of faulty metadata will always fail on one fixed line. When writing a metadata scanner, errors must be handled across **both the lookup operation and the reading of the required elements**, and an accurate diagnostic must be produced.

## 3. Distinguishing the Error Categories

| Scenario | Typical Error | Root Cause | Useful Diagnostic Data |
| --- | --- | --- | --- |
| An annotation value of type `Class<?>` refers to an unresolvable type | `TypeNotPresentException` | The type name remains in the old annotation, but the type is missing/cannot be resolved at runtime | `typeName()`, `getCause()` |
| An enum annotation value refers to a constant no longer present in the runtime enum | `EnumConstantNotPresentException` | The enum constant name does not match the currently available version | `enumType()`, `constantName()` |
| The element return type changed incompatibly with the encoded value | `AnnotationTypeMismatchException` | The stored value no longer matches the element type | `element()`, `foundType()` |
| A new required element is added, and old metadata carries no value for it | `IncompleteAnnotationException` | There is neither a stored value nor a default | `annotationType()`, `elementName()` |
| An old consumer calls an element method signature that no longer exists in the new annotation interface | `NoSuchMethodError` | The binary method descriptor changed or the member was removed | Accessor name/signature in the calling bytecode |
| The annotation class file is corrupted/invalid | `AnnotationFormatError` may occur | Structurally invalid metadata; not merely an enum/type change | Stack trace, class file, and build |

**Important:** `TypeNotPresentException` is not synonymous with `ClassNotFoundException`. The former is a runtime exception with API semantics indicating **a named type is not present**; `ClassNotFoundException` is a checked exception commonly seen in APIs such as `Class.forName(...)`. They may relate to the same missing type, but where they originate and how they are caught are different.

Similarly, `EnumConstantNotPresentException` is **not** an `IllegalArgumentException` caused by an explicit `Enum.valueOf` call with an invalid string. It is a dedicated exception for when an enum constant no longer has a match while reading an annotation element at runtime.

## 4. Experiment 1: Reproducing Both Main Exceptions Simultaneously

We will create **version V1** of an annotation and its related types:

- Annotation `@Contract` with `Class<?> provider()` and `Mode mode()`.
- Enum `Mode` with `BASIC`, `LEGACY`.
- Class `OldProvider` still exists at compile time.
- `Annotated` annotated with `@Contract(provider = OldProvider.class, mode = Mode.LEGACY)`.

Next, create **version V2** of the `Mode` enum containing only `BASIC`, simulating a deployment missing `OldProvider.class`. The `Annotated.class` file remains the bytecode compiled against V1. This is an intentionally version-mismatched environment to reproduce the errors.

### 4.1. Source Structure

~~~text
src/
├── v1/
│   └── demo/
│       ├── Contract.java
│       ├── Mode.java
│       ├── OldProvider.java
│       ├── Annotated.java
│       └── Main.java
└── v2/
    └── demo/
        └── Mode.java
~~~

No libraries outside the JDK are needed. Files containing a `public` type must match the name of that public type.

### V1 — `src/v1/demo/Contract.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Contract {
    Class<?> provider();
    Mode mode();
}
~~~

`RUNTIME` is the condition that allows the `getAnnotation(Contract.class)` method to see the annotation usage at runtime. `@Target(TYPE)` allows placing the annotation on a class.

### V1 — `src/v1/demo/Mode.java`

~~~java
package demo;

public enum Mode {
    BASIC,
    LEGACY
}
~~~

### V1 — `src/v1/demo/OldProvider.java`

~~~java
package demo;

public final class OldProvider {
}
~~~

The `OldProvider` class does not need any methods, because the experiment only uses the **class literal** `OldProvider.class` in the annotation. The compiler verifies that the type exists when compiling the source.

### V1 — `src/v1/demo/Annotated.java`

~~~java
package demo;

@Contract(provider = OldProvider.class, mode = Mode.LEGACY)
public final class Annotated {
}
~~~

Inside `Annotated.class`, there is metadata containing a reference to the type `demo.OldProvider` and the enum constant name `LEGACY`, according to the definition at compile time.

### V1 — `src/v1/demo/Main.java`

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        Contract c = Annotated.class.getAnnotation(Contract.class);
        System.out.println("annotation present: " + (c != null));

        try {
            System.out.println("provider: " + c.provider().getName());
        } catch (TypeNotPresentException e) {
            System.out.println("missing type: " + e.typeName());
        }

        try {
            System.out.println("mode: " + c.mode());
        } catch (EnumConstantNotPresentException e) {
            System.out.println("missing enum: "
                    + e.enumType().getName() + "." + e.constantName());
        }
    }
}
~~~

In this example, each element read is placed in a separate `try/catch`. This allows the learner to see **both errors**, rather than the first error terminating the program and masking the second one. A production program must have a stricter handling policy; the example only prints to demonstrate API behavior.

### V2 — `src/v2/demo/Mode.java`

~~~java
package demo;

public enum Mode {
    BASIC
}
~~~

Version V2 **preserves the binary name of the enum `demo.Mode`** while removing the `LEGACY` constant. This is completely different from deleting `Mode.class` altogether: here the enum type can still be loaded, and only the constant referenced by the old metadata is gone.

### 4.2. Compiling with Java 17 and Running the Consistent V1 Build

Below are the **Bash commands on Linux/macOS** executed from the directory containing `src`. For PowerShell, use `New-Item -ItemType Directory -Force` and `Copy-Item` for directory creation/copying operations instead of `mkdir -p`/`cp`; the `javac` and `java` commands remain unchanged.

~~~bash
mkdir -p build/v1 build/v2 build/runtime/demo

javac --release 17 -d build/v1 src/v1/demo/*.java
javac --release 17 -d build/v2 src/v2/demo/Mode.java

java -cp build/v1 demo.Main
~~~

**Stdout when running consistent V1:**

~~~text
annotation present: true
provider: demo.OldProvider
mode: LEGACY
~~~

In the full V1 version, both the type `demo.OldProvider` and the enum `Mode.LEGACY` are present; reading both elements succeeds.

### 4.3. Assembling an Incompatible Runtime Without Recompiling Annotated

Copy exactly the **three V1 classes** needed to look up the annotation and run the program; do not copy `OldProvider.class` and do not copy V1's `Mode.class`. Then copy `Mode.class` from V2:

~~~bash
cp build/v1/demo/Contract.class build/runtime/demo/
cp build/v1/demo/Annotated.class build/runtime/demo/
cp build/v1/demo/Main.class build/runtime/demo/
cp build/v2/demo/Mode.class build/runtime/demo/

java -cp build/runtime demo.Main
~~~

**Exact stdout of the runtime with an intentionally altered contract:**

~~~text
annotation present: true
missing type: demo.OldProvider
missing enum: demo.Mode.LEGACY
~~~

This is the result compiled with `javac --release 17` and tested on a JDK supporting Java 17.

### 4.4. Explaining Why Each Error Occurs

**Line 1 — annotation present: true**

`Annotated.class` still carries `@Contract` with `RUNTIME` retention; the `demo.Contract` annotation type is also present. The runtime can return the annotation representation. That **does not yet guarantee** that every value inside can be resolved.

**Line 2 — missing type: demo.OldProvider**

In the metadata, the `provider` element is the class literal for `OldProvider`. However, we did not include `OldProvider.class` in `build/runtime`. When `c.provider()` needs to return `Class<?>`, the runtime has to resolve the stored class name, fails to find it, and throws `TypeNotPresentException`. `e.typeName()` records the exact missing type.

**Line 3 — missing enum: demo.Mode.LEGACY**

`c.mode()` must return a `Mode` value. The runtime loads `demo.Mode` from V2, but this enum only contains `BASIC`. The constant name `LEGACY` present in the old annotation no longer has a match, so the runtime throws `EnumConstantNotPresentException`. `e.enumType()` and `e.constantName()` provide the enum type and constant information for diagnosis.

**Key takeaway:** the two errors differ because one is missing a **class type**, while the other is missing an **enum constant within an enum type that can still be loaded**. Merely checking `getAnnotation(...) != null` is not sufficient as a compatibility test.

## 5. Experiment 2: Changing the Annotation Type Itself

Another common error comes from changing the `@interface` definition instead of changing an enum or a dependency. Suppose V1 is:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Config {
    int level();
}
~~~

A V1 class uses:

~~~java
@Config(level = 7)
public class OldAnnotated {}
~~~

After release, library V2 changes the contract to:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Config {
    String level();
    String owner();
}
~~~

The snippets above are **illustrations comparing the two versions** and lack complete imports and package declarations to run standalone. We will clarify this with a complete Java 17 fixture:

- `int level()` changes to `String level()`: the value `7` still stored in the old class file has a mismatched type; accessing it through the new accessor may throw `AnnotationTypeMismatchException`.
- `String owner()` is a new **required** element without a `default`; V1's `OldAnnotated.class` does not store an owner, so calling `owner()` may throw `IncompleteAnnotationException`.

### 5.1. V1 Files

**`src/v1/demo/Config.java`** (this fixture is **independent of experiment 1**; use a separate build directory if running both):

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Config {
    int level();
}
~~~

**`src/v1/demo/OldAnnotated.java`**:

~~~java
package demo;

@Config(level = 7)
public final class OldAnnotated {
}
~~~

### 5.2. V2 Files and Verification Program

**`src/v2/demo/Config.java`**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Config {
    String level();
    String owner();
}
~~~

**`src/v2/demo/Probe.java`**:

~~~java
package demo;

import java.lang.annotation.AnnotationTypeMismatchException;
import java.lang.annotation.IncompleteAnnotationException;

public final class Probe {
    public static void main(String[] args) throws ClassNotFoundException {
        Class<?> old = Class.forName("demo.OldAnnotated");
        Config config = old.getAnnotation(Config.class);
        System.out.println("present: " + (config != null));

        try {
            System.out.println("level: " + config.level());
        } catch (AnnotationTypeMismatchException e) {
            System.out.println("mismatch element: "
                    + e.element().getName());
        }

        try {
            System.out.println("owner: " + config.owner());
        } catch (IncompleteAnnotationException e) {
            System.out.println("incomplete element: "
                    + e.elementName());
        }
    }
}
~~~

`Probe` is compiled **against Config V2**; `OldAnnotated.class` is kept unchanged **from V1**. We deliberately use `Class.forName("demo.OldAnnotated")` instead of referencing V1 source during V2 compilation, and then construct a runtime containing only the exact classes needed.

### 5.3. Compiling, Assembling the Runtime, and Running

Use a new working directory for experiment 2, with its own `src/v1/demo` and `src/v2/demo` layout:

~~~bash
mkdir -p build/v1 build/v2 build/runtime/demo

javac --release 17 -d build/v1 \
    src/v1/demo/Config.java src/v1/demo/OldAnnotated.java

javac --release 17 -d build/v2 \
    src/v2/demo/Config.java src/v2/demo/Probe.java

cp build/v1/demo/OldAnnotated.class build/runtime/demo/
cp build/v2/demo/Config.class build/runtime/demo/
cp build/v2/demo/Probe.class build/runtime/demo/

java -cp build/runtime demo.Probe
~~~

**Verified stdout:**

~~~text
present: true
mismatch element: level
incomplete element: owner
~~~

This experiment produces **two different error types** from the same runtime annotation representation: the stored value `level = 7` no longer matches `String`, while `owner` is a completely new element without a default.

If we replace `String owner();` in V2 with:

~~~java
String owner() default "unknown";
~~~

then the missing owner in the V1 metadata is resolved by the new default and does not necessarily cause `IncompleteAnnotationException`. However, the **default semantics** of `"unknown"` must be designed carefully; "no more exceptions" does not mean the upgrade preserved the business semantics.

## 6. How Does AnnotationTypeMismatchException Differ from NoSuchMethodError?

Changing `int level()` to `String level()` has two aspects:

1. **Old metadata:** in `OldAnnotated.class`, the `level` annotation element holds a primitive int value. When the runtime reads it using the V2 `Config` definition that has the `String level()` method, the data is incompatible, which can throw `AnnotationTypeMismatchException`.
2. **Old consumer bytecode:** a class compiled to call `Config.level():int` still references the **old JVM signature**. If that consumer class is executed against an annotation interface that only has `String level()`, the JVM may report `NoSuchMethodError` because the old descriptor no longer exists. This is a **binary linkage** error, not the annotation proxy decoding a stored value.

Experiment 2 deliberately **compiled `Probe` against V2** to clearly illustrate group (1). When testing binary compatibility for a large application, you must test **both the annotated classes** and **the compiled consumers/processors that invoke the annotation elements**. Simply trying to recompile a small program against the new API is not sufficient to prove binary compatibility for the entire system.

Renaming `level()` to `priority()` is also a major API change: source code calling the old `level()` will fail to recompile, while old binary consumers may encounter linkage errors. If an annotated class file has a `level` value while the new definition only has a required `priority`, reading `priority` may throw `IncompleteAnnotationException`.

## 7. What Happens When Adding, Removing, and Modifying Elements and Defaults?

Changes to an annotation type must be treated as public API changes, because every annotation usage is checked by the compiler and written into class files.

| Annotation Definition Change | For Source Using the Annotation on Recompilation | For Previously Compiled Annotations |
| --- | --- | --- |
| Add element `String owner();` (no default) | Existing usages must provide `owner`, otherwise the compiler reports an error | Accessing `owner()` may throw `IncompleteAnnotationException` |
| Add element `String owner() default "unknown";` | Existing source usually still compiles | The runtime can use the new default, though semantics may change |
| Change default from `"A"` to `"B"` | Source that omits the element remains valid | The value observed on access may shift to the currently active annotation type definition |
| Change element type, such as `int` → `String` | All usages must conform to the new type | Old values may cause `AnnotationTypeMismatchException`; old consumers may hit `NoSuchMethodError` |
| Remove or rename an element | Source usages specifying the old element are generally no longer valid | Old consumers may encounter linkage errors; old values may be ignored depending on the read operation and new elements |
| Remove/rename a class literal used in an element | Source needs a replacement type | `TypeNotPresentException` when reading the old unresolvable type |
| Remove/rename an enum constant used in an element | Source needs to use a valid constant | `EnumConstantNotPresentException` when reading the old constant |
| Change `@Retention` `RUNTIME` → `CLASS` | Source applying the annotation may still compile | Compiled bytecode must be inspected; new usages are no longer available to runtime reflection |
| Narrow `@Target` | Disallowed target locations become invalid on recompilation | Old class files are not automatically rewritten; consuming tools must be tested |
| Change annotation type package/name | Imports and usages must be updated | Old bytecode still references the previous type name; metadata may be missed when looking up the new type |

**Important regarding defaults:** Annotation defaults are stored in **the annotation type definition**, rather than always being copied as explicit values at every usage site. Therefore, changing a default can affect compiled classes that did not explicitly specify the element. This is a source of **silent behavioral changes** even when no exception is thrown.

Do not equate "binary linkage still runs" with "semantic compatibility is preserved". For example, changing the default of a permission or policy flag can cause more severe consequences than an easily detected exception.

## 8. Why Can Exceptions Appear Late?

The standard Java Reflection API returns an annotation representation whose elements the program can invoke. In many cases, faulty data is only detected when that specific element is actually accessed:

~~~java
Contract contract = Annotated.class.getAnnotation(Contract.class);
System.out.println(contract != null); // May still be true
contract.provider();                   // May throw TypeNotPresentException
contract.mode();                       // May throw EnumConstantNotPresentException
~~~

This is an illustrative snippet based on experiment 1, **not a standalone program**.

There are three consequences for testing:

- Tests that only call `isAnnotationPresent(...)` or `getAnnotation(...)` may **fail to cover all element values**.
- A test that succeeds in calling one element may miss an error in another element.
- Because the exception does not necessarily appear when the JVM loads the business class, the error becomes harder to correlate with an earlier library upgrade.

If code is responsible for validating all metadata, it must access **the elements that actually belong to the contract** and verify the required values/types, rather than merely checking whether the annotation is present.

Do not assume all errors are deferred: malformed metadata, type annotation resolution, class loading, and specific reflection paths can trigger failures at different times. Handle exceptions at the appropriate scanner/framework boundary.

## 9. Diagnostic Strategy in Real-World Applications

When encountering either of the two main exceptions, a useful procedure is:

1. **Record the annotated element being read**: the fully qualified class name, field/method/constructor, annotation type, and element being accessed. Do not log just a stack trace without context.
2. **Record the JAR versions and class loader**: the annotation API version, enum, referenced type, and the annotated class file may come from different artifacts.
3. **Inspect the values in bytecode** using `javap -v` (or an equivalent bytecode reader) on **the annotated class**. Look for `RuntimeVisibleAnnotations` with the annotation type and the stored `Class`/enum values.
4. **Compare the API at compile time and runtime**. If a dependency class was removed from runtime, add the appropriate dependency or recompile with the new type. If an enum constant was removed, consider keeping the old constant or migrating the metadata to the new constant and recompiling the classes applying it.
5. **For `AnnotationTypeMismatchException`**, compare the element type before and after; do not look only at the element name. For `IncompleteAnnotationException`, check whether the new element has a valid default.
6. **Check for dependency conflicts**: multiple versions of the same library, shading/relocation, fat JARs, classpath order, and module path can cause the runtime to load a different definition than expected.
7. **Test against the final packaged artifact**. Do not run tests solely inside an IDE environment if the application is deployed using a different set of JARs.

Example helper commands provided by the JDK:

~~~bash
javap -v -classpath build/v1 demo.Annotated
javap -p -classpath build/v1 demo.Contract
javap -p -classpath build/v2 demo.Mode
~~~

The first command inspects the annotation metadata on `Annotated.class`; the second inspects the annotation element signatures in the V1 API; the third inspects the V2 runtime enum. `javap` is not a bytecode editor; it is used to **observe** what the compiler generated.

If the project uses named modules, you may need to replace `-classpath` by specifying the appropriate module path/module name; the principle remains **to inspect the exact class file and version actually loaded by the runtime**.

## 10. Error Handling in a Framework or Scanner

A metadata scanner may want to emit clear diagnostics instead of letting the application crash with an exception lacking context. For example (an illustrative snippet in an application where `Contract` and `Annotated` are already defined):

~~~java
try {
    Contract c = Annotated.class.getAnnotation(Contract.class);
    if (c == null) {
        throw new IllegalStateException("Missing @Contract");
    }
    Class<?> provider = c.provider();
    Mode mode = c.mode();
    System.out.println(provider.getName() + ":" + mode.name());
} catch (TypeNotPresentException e) {
    throw new IllegalStateException(
            "Missing provider type in @Contract: " + e.typeName(), e);
} catch (EnumConstantNotPresentException e) {
    throw new IllegalStateException(
            "Missing enum constant in @Contract: "
                    + e.enumType().getName() + "." + e.constantName(), e);
}
~~~

This snippet is **illustrative code**, not standalone. In the version-mismatched runtime of experiment 1, the first error will cause the code to throw `IllegalStateException`; to aggregate all metadata errors, each element must be checked separately like `Main` in the experiment.

A few considerations:

- If metadata governs **authorization, validation, routing, or security**, you should **fail closed** when a required value cannot be read. Do not default a broken permission to "no permission required".
- Do not catch an overly broad `Exception` and ignore it, as that hides the root cause and may allow the framework to run with an invalid configuration.
- Do not use `null` as a fallback value for an annotation element: Java annotations do not allow `null` literals, and a metadata error should not be turned into an ordinary value.
- If you choose a backward-compatibility strategy, document it: how long the old type will be retained, how old enum constants map to new ones, and which classes must be recompiled.
- Avoid embedding secret values in annotations because `CLASS`/`RUNTIME` retention can expose them inside class files and analysis tools.

For `AnnotationTypeMismatchException` and `IncompleteAnnotationException`, a scanner can emit additional messages based on `element()`/`elementName()`. However, these exceptions typically indicate **packaging/deployment or API contract errors**, not data errors that an end user can fix on their own at runtime.

## 11. How to Fix Each Scenario

### 11.1. When a Class<?> Element References a Type That No Longer Exists

If an old annotation contains `OldProvider.class`, you can:

1. **Restore the old binary type** in the runtime if compatibility can still be maintained and it is safe to use.
2. **Switch the annotated classes to the new type** in source, and recompile them.
3. If changing a package/class name, apply an explicit migration policy rather than only updating the JAR containing the annotation type. The bytecode of old annotated classes still retains the old class literal name.
4. Check class loader/module visibility if the type physically exists but cannot be resolved from the context reading the annotation.

Do not simply add an arbitrary dependency with a matching simple name: the JVM identifies classes by **binary name and class loader**, not by display file name or simple name.

### 11.2. When an Enum Constant Is Renamed or Removed

For example, V1 has `Mode.LEGACY` while V2 only has `Mode.BASIC`.

- **Keeping `LEGACY`** in the V2 enum (optionally marked deprecated) is a compatibility measure when that value still needs to be decoded.
- **Recompiling all annotated classes** to use only valid constants is the direct solution, though all artifacts using the old data must be identified.
- **Do not expect the runtime to automatically map** `LEGACY` to `BASIC`: annotation metadata stores constant names, and Java has no automatic enum aliasing.
- If the new logic has different semantics from the old constant, create an explicit conversion layer/compatibility policy in the consumer rather than silently treating the two values as identical.

Changing the **declaration order** of constants in an enum is not the same as removing or renaming a constant. Annotations store the constant name according to the class file model, so do not conclude that merely reordering an enum is the direct cause of `EnumConstantNotPresentException`.

### 11.3. When Adding a Required Element or Changing a Return Type

- To remain compatible with old annotated classes when adding an element, consider a **meaningful `default`** instead of requiring all old classes to have data that was never encoded.
- If changing an element's return type, you should generally **create a new annotation API/element** or plan to migrate/recompile all consumers and annotated classes, rather than assuming the JVM automatically converts `int` to `String`.
- Do not use a default merely to hide contract errors. For sensitive information such as permissions, mandatory owners, or policies, an arbitrary default can produce incorrect behavior.
- Do not change an existing default without checking the impact on annotated classes that omit the element; the effective value at runtime can change without raising an error.

## 12. Distinguishing from Other Annotation Errors

In large projects, there are several related scenarios with different root causes:

**`AnnotationFormatError`:** the annotation/class file metadata is invalid according to the format processed by the runtime. This is a dedicated `Error`, not a general error for reading enums/types. Do not use a catch-all `Error` handler to pretend to continue with untrusted data.

**`MirroredTypeException` in an annotation processor:** this is an exception in `javax.lang.model.type` that can occur when a **compile-time** processor accesses an element of type `Class<?>` through a typed annotation proxy and the compiler returns a `TypeMirror` instead of a runtime class. It **differs from `TypeNotPresentException`** in the context of a class failing to resolve at runtime. In a processor, the more general approach is to use `AnnotationMirror`/`AnnotationValue` or `TypeMirror` according to the compiler model.

**`NoClassDefFoundError`:** can occur when the JVM cannot load a required class during linking/initialization or another class usage path. It does not mean that every class literal stored in an annotation throws this error. Experiment 1 demonstrates that when reading an annotation element of type `Class<?>` whose class is missing, the specific exception thrown is `TypeNotPresentException`.

**`IncompleteAnnotationException`:** indicates a required element is missing from the annotation representation. It is not the same as a compile-time error when newly written source omits an element; a compile-time error occurs before bytecode generation, whereas experiment 2 demonstrates a runtime error caused by old bytecode meeting a new definition.

**`AnnotationTypeMismatchException`:** indicates that a stored annotation value has a type incompatible with the current annotation element method, not an ordinary Java type-casting error caused by an invalid user-written cast.

By distinguishing between **compiler errors**, **annotation decoding errors**, and **linkage errors**, we avoid applying the wrong fix.

## 13. Testing Process for Annotation Contract Changes

Before releasing a new API version containing an `@interface` or an enum/type used in annotations, there should be at least four test groups.

### 13.1. Source Compatibility Testing

Recompile a sample project that uses annotations from the previous version **against the new API version**. Check new required elements, changed value types, package/type names, and narrowed targets. This step readily catches breakages when source is recompiled.

### 13.2. Binary Compatibility Testing

**Keep the annotated class bytecode from the previous version unchanged**, while running it against the new API/runtime version. This is a critical test that a "full clean build" can accidentally skip: all old metadata was encoded by the compiler based on the old contract.

Experiment 1 provides a clear test case: keep V1's `Annotated.class`, remove `OldProvider.class`, and replace `Mode.class` with V2. Experiment 2 keeps V1's `OldAnnotated.class` and replaces the `Config` annotation type with V2.

### 13.3. Testing All Annotation Elements, Not Just Presence

Example verification snippet:

~~~java
Contract c = Annotated.class.getAnnotation(Contract.class);
if (c == null) {
    throw new IllegalStateException("@Contract missing");
}
c.provider();
c.mode();
~~~

This is an illustrative example, not a passing test in an intentionally broken runtime. It expresses the requirement **to exercise all significant elements** in order to uncover compatibility errors. If only `isAnnotationPresent` is used, the test may pass even though an element will fail during actual framework processing.

### 13.4. Testing Business Behavior and Defaults

Cases that do not throw an exception can still be wrong: changing a `@RequiresPermission` default, replacing an enum with the same name but different meaning, or altering an annotation-combining policy. Therefore, you must verify **actual values**, consumer behavior, and fail-safe policies, not just that "the code still runs".

A pre-release evaluation matrix:

| Change | Source Compile Test | Old-Bytecode Runtime Test | Semantic Test |
| --- | --- | --- | --- |
| Remove a provider class | Check source annotation references | Read `Class<?>` element from old class | Verify fallback/migration |
| Remove an enum constant | Recompile source using the constant | Read enum element from old class | Ensure proper semantic mapping |
| Change an element type | Check source calls/usages | Read stored value with new API; test old consumer | Evaluate new representation |
| Add a required element | Compiler reports missing usages | Read element on old class | Choose a default if safe |
| Change a default | Source may still compile | Check effective value with old class | Evaluate policy change |
| Change retention/target | Compiler and metadata of new build | Inspect how old class files are read | Confirm tools continue working |

## 14. Extension Exercises

**Exercise A — Trigger only TypeNotPresentException.** Keep V1's enum containing `LEGACY` in the runtime, but omit `OldProvider.class`. Expect `c.provider()` to fail while `c.mode()` still succeeds.

**Exercise B — Trigger only EnumConstantNotPresentException.** Keep `OldProvider.class` in the runtime, but replace `Mode.class` with V2 lacking `LEGACY`. Expect `c.provider()` to return the type while `c.mode()` fails. You can vary the set of files copied to the runtime to create both variants.

**Exercise C — Add a default.** In experiment 2, change the new element to `String owner() default "unknown";`, recompile V2, and keep V1's `OldAnnotated.class` unchanged. Verify that `owner()` can use the default while `level()` still fails with a type mismatch. This cleanly separates the two error types.

**Exercise D — Keep the element type unchanged but alter the default.** Use `@Limit(max = 10)` on one class and `@Limit` without an argument on another class; change the `max()` default in a new version. Compare the class with the explicit value against the class using the default. The `@Limit` mention is only an exercise idea; you must define `@interface Limit` with `int max() default ...` yourself before compiling.

**Exercise E — Test an old consumer.** Compile a program calling `Config.level():int` against the V1 API, then replace `Config` with the V2 API returning `String` without recompiling the caller program. Observe the difference between a method descriptor linkage error and a stored annotation value error. Do not use the outcome of V2's `Probe` to claim that a V1 consumer will necessarily throw the same `AnnotationTypeMismatchException`.

**Exercise F — Inspect with javap.** Use `javap -v -classpath build/v1 demo.Annotated` to verify that the `Contract` annotation stores the type `demo.OldProvider` and constant `LEGACY`; use `javap -p` on the V2 enum to compare against the actual constant list.

## 15. Safe Implementation Checklist

- [ ] Treat the annotation type, all element methods, enums, and class literals used as **a versioned contract**.
- [ ] Keep `@Retention(RUNTIME)` if consumers require reflection, and specify the appropriate `@Target` for application sites.
- [ ] Avoid deleting or renaming Java types or enum constants still referenced in annotations by old class files.
- [ ] When adding a required element, evaluate a meaningful `default` and its impact on source/binary compatibility.
- [ ] When changing an element's type or name, plan to **migrate** both annotated classes and consumers.
- [ ] Run `javap -v` on **the annotated class**, not only on the class defining the annotation type.
- [ ] Verify the classpath/module path and **the binaries actually deployed** to avoid mixed versions.
- [ ] Test the program with old bytecode + new dependencies, not only a clean compile against the new version.
- [ ] Read **every important annotation element** in tests, rather than merely checking whether the annotation is present.
- [ ] When a scanner encounters faulty metadata, log the type/element/version and fail safely according to policy instead of ignoring errors that could affect authorization.
- [ ] Check for **default semantics** changes even when no exception is thrown.
- [ ] Separate compile-time errors, runtime annotation decoding errors, and binary linkage errors in incident reports.

**Remember:** `TypeNotPresentException` reports that a type recorded in an annotation cannot be resolved; `EnumConstantNotPresentException` reports that an enum constant recorded in an annotation is no longer present at runtime. When the annotation contract changes, `AnnotationTypeMismatchException` and `IncompleteAnnotationException` can also occur. These exceptions may only appear **when reading an element**, so compatibility testing must retain **old bytecode**, supply **new dependencies**, and access **every meaningful element**, instead of merely confirming that the annotation is present.
