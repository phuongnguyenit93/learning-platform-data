# Evolving Annotation Contracts in Java: Adding Elements, Changing Types, and Modifying Defaults

## 1. An Annotation Is a Public Contract, Not Just @ Syntax

An annotation interface (`@interface`) declares a **set of elements** that other code or tools can provide and read. For example:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Rule {
    String name();
    int retries() default 2;
    String mode() default "safe";
}
~~~

Code using the annotation:

~~~java
@Rule(name = "payment", mode = "strict")
class PaymentService {}
~~~

The contract of `Rule` includes multiple components:

- **Element names and types:** `name()` returns `String`, `retries()` returns `int`, `mode()` returns `String`.
- **Whether elements are required or optional:** `name()` has no `default`, so usage sites must provide a value; `retries()` and `mode()` have default values.
- **Default values and meaning:** `2` may represent the retry count; `"safe"` represents the default policy defined by the library.
- **`@Target` / `@Retention`:** where the annotation is allowed to be placed, and whether it is visible via reflection at runtime.
- **How metadata-consuming code interprets it:** an annotation processor, validator, serializer, DI framework, runtime reflection, or build tool can read the elements and execute its own logic.

Therefore, changing the `@interface Rule` definition once a library is already in use is like **changing a public API**. A change might keep old code compiling while causing runtime behavior to change, or cause a class file generated from an older version to no longer have its metadata read correctly when combined with the new version of the annotation type.

This article focuses on **three main evolution operations**:

1. **Adding an element**: adding `int timeout()` or `int timeout() default 30`.
2. **Changing an element's type**: `String mode()` to `Mode mode()`, `int retry()` to `long retry()`, or `String tag()` to `String[] tags()`.
3. **Changing a default value**: `retries() default 2` to `retries() default 5`.

The goal is to distinguish **source compatibility, binary linkage compatibility, the ability to read old annotations, and semantic compatibility** to choose a safe version upgrade approach.

## 2. Three Compatibility Layers to Examine Separately

| Layer | Question to Answer | Failure Detection Example |
|---|---|---|
| **Source compatibility** | Does source code using `@Rule(...)` recompile against the new annotation type? | Adding a new element without `default` causes old usage sites to lack an argument |
| **Binary/linkage compatibility** | Can already-compiled client/library `.class` files link against the new API? | An old caller invoking the annotation method using the old descriptor may throw `NoSuchMethodError` if the return type is changed |
| **Runtime metadata compatibility** | When reading metadata stored in an old class file, do the values and types still match the new annotation interface? | `IncompleteAnnotationException` or `AnnotationTypeMismatchException` |
| **Behavioral/semantic compatibility** | Even if it runs, does the actual policy change? | Changing `default 2` to `default 5` causes clients that do not specify a value to start retrying 5 times |

The layers can produce different results. **"No compilation errors" does not mean "safe upgrade."** For example, changing a default value preserves the method signature, yet causes the framework to read the annotation and change behavior without recompiling the client.

**Be careful with the term "binary compatible."** A change to an annotation interface may be classified according to Java's binary compatibility rules, yet still cause an exception when **reading an annotation element stored in an older version**. These two checks do not replace each other. To evaluate accurately, you must examine the caller bytecode, the annotation data stored in the class file, and the reflection/processor API doing the reading.

## 3. Element Types and Valid Value Rules

Before designing the migration process, keep in mind that annotation elements are not arbitrary Java methods. Valid return types of an element belong to the following groups:

- Primitive types, such as `int`, `boolean`.
- `String`.
- `Class` or an appropriate parameterized `Class<?>` form.
- An `enum` type.
- Another annotation interface.
- A **one-dimensional array** of the types listed above.

Types such as `Object`, `List<String>`, `LocalDate`, or multidimensional arrays are not valid annotation element types.

Values used at annotation placement sites are also restricted:

- For primitives or `String`: an appropriate **compile-time constant expression**.
- For `Class<?>`: a class literal such as `String.class`.
- For enums: an enum constant such as `Mode.STRICT`.
- For nested annotations: `@Nested(...)`.
- For arrays: `{"a", "b"}` or single-element syntax when permitted.
- **`null` is invalid**, even when the element type is a reference type.

Therefore, you cannot "fix migration errors" by writing `default null` or `default System.getenv("...")`. If a sentinel is needed, clearly define the meaning of `""`, `{}`, `Void.class`, or `UNSPECIFIED`.

## 4. Adding a New Element: With `default` and Without `default`

Suppose v1:

~~~java
public @interface Rule {
    String name();
    int retries() default 2;
}
~~~

### 4.1. Adding an Element with a Default — The Most Compatible Option

In v2:

~~~java
public @interface Rule {
    String name();
    int retries() default 2;
    int timeoutSeconds() default 30;
}
~~~

The following old code still compiles when using v2:

~~~java
@Rule(name = "payment")
class PaymentService {}
~~~

- `name` continues to be provided explicitly.
- `retries` takes the default `2`.
- `timeoutSeconds` takes the new default `30`.
- The class file of `PaymentService` compiled against v1 does not have the `timeoutSeconds=...` data pair, yet when reflection reads the annotation under the v2 definition, `timeoutSeconds()` can return the default `30` without recompiling the old class.

**This approach reduces syntax and missing-data risks**, but does not necessarily preserve behavior. If the consumer starts applying a timeout of `30` where previously there was no timeout at all, the system can still change significantly.

You should choose the default according to **semantics that inherit the old behavior**. If there was previously no timeout limit, you may need a sentinel indicating "not applicable" instead of arbitrarily picking a timeout that could break long-running tasks.

### 4.2. Adding an Element Without a Default — A Breaking Change for Usage Sites

In v2:

~~~java
public @interface Rule {
    String name();
    int retries() default 2;
    int timeoutSeconds();
}
~~~

Old source:

~~~java
@Rule(name = "payment")
class PaymentService {}
~~~

When **recompiling** against v2, the compiler requires a value for `timeoutSeconds`. The code must change, for example:

~~~java
@Rule(name = "payment", timeoutSeconds = 30)
class PaymentService {}
~~~

**For class files already compiled against v1**, the old annotation does not contain `timeoutSeconds`. If runtime reflection accesses `rule.timeoutSeconds()` on an annotation instance of the old class, Java may throw **`java.lang.annotation.IncompleteAnnotationException`**. The error may appear when **reading the missing element**, not necessarily immediately when loading the class or when `getAnnotation(...)` returns the proxy.

**Adding a required method should not be considered a compatible migration.** If you need to require new clients to enter a value, consider adding an element with a default/sentinel during a transition phase, providing migration guidance, and controlling the contract by version.

## 5. Changing `default`: Behavior Can Still Change Without Recompiling Old Classes

This is an extremely important point from JLS 9.6.2: **default values are not compiled into explicit values at each annotation usage**; they are applied **dynamically at the time the annotation is read**.

V1:

~~~java
public @interface Rule {
    int retries() default 2;
}
~~~

A class using it without specifying the element:

~~~java
@Rule
class Job {}
~~~

V2:

~~~java
public @interface Rule {
    int retries() default 5;
}
~~~

If you only replace the v1 annotation type with v2 while keeping **`Job.class`** compiled against v1, the call:

~~~java
Rule rule = Job.class.getAnnotation(Rule.class);
System.out.println(rule.retries());
~~~

may print **`5`**, not `2`. The class file `Job.class` never stored an explicit value for `retries`, so the value is taken from the current default of the annotation interface being loaded.

Conversely:

~~~java
@Rule(retries = 2)
class ExplicitJob {}
~~~

If `ExplicitJob.class` already recorded the value `retries=2`, after upgrading the annotation interface to v2, it **continues to read `2`** for that element. **Defaults only take effect when an annotation usage has no explicit value**.

### 5.1. Why Can This Be a Behavioral Breaking Change?

Suppose the annotation controls:

- Number of retries when calling an API.
- Whether validation is enabled/disabled.
- Transaction mode, cache mode, timeout.
- Access permissions, logging scope, or serialization policy.

Changing the default can affect thousands of classes that do not explicitly specify that element, even when there is not a single source diff in those classes. The system still compiles/links normally, so regressions can be missed if you only run compiler tests.

**Principle:** treat changing a default that carries runtime or build-time policy meaning as a **semantic contract change**, even though the method signature does not change.

### 5.2. Processors and Defaults

With annotation processing, `AnnotationMirror.getElementValues()` contains only the elements provided **explicitly** at the usage site. `Elements.getElementValuesWithDefaults(mirror)` returns a map that also includes default values according to the current annotation type definition.

When upgrading the annotation type version, a processor can also read the new default value and generate different source. Therefore, the impact of changing a default is **not limited to runtime reflection**; it can also alter **generated code at build time**.

## 6. Changing an Element Type: Why Is It Not a Harmless Refactoring?

V1:

~~~java
@interface Policy {
    String mode() default "safe";
}

@Policy(mode = "strict")
class Service {}
~~~

After one version, the API wants to use an enum:

~~~java
enum Mode { SAFE, STRICT }

@interface Policy {
    Mode mode() default Mode.SAFE;
}
~~~

This change has the following impacts:

1. **Source:** `@Policy(mode = "strict")` **does not recompile**; it must be changed to `@Policy(mode = Mode.STRICT)`.
2. **Bytecode callers:** the `mode()` method of the annotation interface changes its return descriptor from `()Ljava/lang/String;` to `()L.../Mode;`. Callers compiled against the old signature may encounter **`NoSuchMethodError`** when running alongside the new API.
3. **Old metadata:** a class file from v1 may contain the element-value `mode="strict"` in `String` form, which is incompatible with the enum element type of v2. When Java reflection reads that element under the new definition, it may throw **`AnnotationTypeMismatchException`**.
4. **Behavior:** even if you update the new source, consumers must handle the enum instead of String. Mapping and defaults may also change.

You should not assume that the compiler/JVM will automatically convert the string `"strict"` to `Mode.STRICT` when reading an old annotation. Metadata in class files has different value representations; there is no system for arbitrary type conversion based on business intent.

### 6.1. Not Just `String -> enum`

Other changes are also risky:

| Old Type | New Type | Issue |
|---|---|---|
| `int count()` | `long count()` | Method descriptor changes; old callers and element values may be incompatible |
| `String tag()` | `String[] tags()` | Name and data shape change; old code must migrate, and old annotations do not automatically turn a scalar into an array |
| `Class<?> handler()` | `String handler()` | Different type and contract; class literals are not automatically stringified |
| `Mode mode()` | `NewMode mode()` | Different enum type; enum constant mapping must be designed |
| `boolean enabled()` | `String enabled()` | Type change affecting annotation usages and readers |
| `String[] names()` | `String name()` | Does not automatically take a single element from old array data |

Errors can vary depending on the call site and stored data. **Do not promise a single exception** for every type-change case; the verification examples below intentionally separate the reader compiled with the new API from the old caller to show the kind of error that reflects the old annotation data itself.

### 6.2. Changing Enums and Class Literals Also Carries Its Own Risks

If an old annotation has an **enum constant** or **class literal** that can no longer be resolved in the new environment, reading the annotation may encounter `EnumConstantNotPresentException` or `TypeNotPresentException` when accessing the related element.

This is an error in the **annotation value component** being read, not merely a source syntax change. Renaming an enum constant, moving a class, or changing a dependency package can cause impacts even when the return type of the annotation element remains unchanged.

## 7. Compatibility Experiment Example: Keeping Old Class Files When Changing the API

This example uses **the same `demo.Legacy` class compiled against v1**, then runs three versions of the annotation interface to observe the consequences. `Legacy.java` is not recompiled in the v2/v3/v4 runs.

### 7.1. Version v1 — Declaration and Usage

File `v1/src/api/Rule.java`:

~~~java
package api;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Rule {
    String name();
    int retries() default 2;
    String mode() default "safe";
}
~~~

File `v1/src/demo/Legacy.java`:

~~~java
package demo;

@api.Rule(name = "alpha", mode = "strict")
public class Legacy {}
~~~

Note: `Legacy` provides `name` and `mode` explicitly, but **does not provide `retries`**.

Compile v1:

~~~bash
mkdir -p v1/classes
javac --release 17 -d v1/classes \
  v1/src/api/Rule.java v1/src/demo/Legacy.java
~~~

Result: `v1/classes/api/Rule.class` and `v1/classes/demo/Legacy.class`.

### 7.2. Version v2 — Adding an Element with a Default and Changing an Old Default

File `v2/src/api/Rule.java`:

~~~java
package api;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Rule {
    String name();
    int retries() default 5;         // v1 was 2
    String mode() default "safe";
    String owner() default "team";   // new element with default
}
~~~

File `v2/src/demo/Read.java`:

~~~java
package demo;

public class Read {
    public static void main(String[] args) {
        api.Rule rule = Legacy.class.getAnnotation(api.Rule.class);

        System.out.println("name=" + rule.name());
        System.out.println("retries=" + rule.retries());
        System.out.println("mode=" + rule.mode());
        System.out.println("owner=" + rule.owner());
    }
}
~~~

Compile **only Rule v2**, copy the **old** `Legacy.class`, then compile the new reader:

~~~bash
mkdir -p v2/classes/demo
javac --release 17 -d v2/classes v2/src/api/Rule.java
cp v1/classes/demo/Legacy.class v2/classes/demo/
javac --release 17 -cp v2/classes -d v2/classes v2/src/demo/Read.java
java -cp v2/classes demo.Read
~~~

Actual stdout:

~~~text
name=alpha
retries=5
mode=strict
owner=team
~~~

Explanation:

- `name=alpha` remains the explicit element value from the old annotation.
- `retries=5` takes **the v2 default** even though `Legacy.class` is still the v1 binary.
- `mode=strict` continues to be the **explicit value** in the old class and is not replaced by the default `"safe"`.
- `owner=team` is a new element, yet because it has a default, the old class can still be read.

This is the most important demonstration of the difference between **data explicitly stored in the annotation usage** and **defaults retrieved from the annotation interface loaded at runtime**.

### 7.3. Version v3 — Adding a Required Element Without a Default

File `v3/src/api/Rule.java` has the v2 elements and adds:

~~~java
int timeout(); // NO default
~~~

Place the line above **inside the Rule annotation interface**. This line by itself is not a standalone file.

New reader in `v3/src/demo/Read.java` (compiled against Rule v3):

~~~java
package demo;

public class Read {
    public static void main(String[] args) {
        api.Rule rule = Legacy.class.getAnnotation(api.Rule.class);
        try {
            System.out.println(rule.timeout());
        } catch (java.lang.annotation.IncompleteAnnotationException ex) {
            System.out.println("missing=" + ex.elementName());
        }
    }
}
~~~

Keep the old `Legacy.class` from v1 (it does not have `timeout`). When the reader calls `timeout()`, the verified result is:

~~~text
missing=timeout
~~~

`IncompleteAnnotationException` indicates that code is accessing an element added after the annotation usage was compiled, which lacks both a value and a default in the current definition.

To reproduce this version, create the complete v3 `Rule.java` from v2 by adding `int timeout();`, then use the same command pattern as v2 with `v3/classes`. Do not recompile `Legacy.java` against v3 when you want to test the old binary: the compiler will report that the old source is missing `timeout`.

### 7.4. Version v4 — Changing the Type of a Stored Value

File `v4/src/api/Rule.java`:

~~~java
package api;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Rule {
    String name();
    int retries() default 5;
    int mode() default 9; // previously String mode()
}
~~~

New reader `v4/src/demo/Read.java`:

~~~java
package demo;

public class Read {
    public static void main(String[] args) {
        api.Rule rule = Legacy.class.getAnnotation(api.Rule.class);
        try {
            System.out.println(rule.mode());
        } catch (java.lang.annotation.AnnotationTypeMismatchException ex) {
            System.out.println("mismatch=" + ex.element().getName());
        }
    }
}
~~~

This uses `Legacy.class` from v1 with `mode="strict"` stored as `String`, while the v4 annotation interface requires `int`. Verified result:

~~~text
mismatch=mode
~~~

**Note:** This is a **new reader compiled against v4**. If instead you keep an already-compiled old reader binary to call `String mode()` from the v1 API, changing the return type of `mode()` can cause **method linkage** errors such as `NoSuchMethodError`. Both scenarios need to be tested if releasing a library for precompiled clients.

### 7.5. Experiment Results Matrix

| Configuration | `Legacy.class` | `Rule.class` | Reader | Observation |
|---|---|---|---|---|
| V2: add `owner` with default, change `retries` default | V1 | V2 | Freshly compiled against V2 | `name=alpha`, `retries=5`, `mode=strict`, `owner=team` |
| V3: add required `timeout` | V1 | V3 | Freshly compiled against V3 | `IncompleteAnnotationException` when calling `timeout()` |
| V4: change `mode` from `String` to `int` | V1 | V4 | Freshly compiled against V4 | `AnnotationTypeMismatchException` when calling `mode()` |

The four versions are **independent test snapshots**, not different `api.Rule` classes simultaneously on one classpath. Each run has only **one** `api.Rule` definition matching the scenario. Mixing multiple JARs containing the same binary name can cause the classpath/classloader to pick an unintended version and skew the results.

## 8. Renaming or Removing an Element

V1:

~~~java
@interface Config {
    String value();
}
~~~

If V2 replaces it with:

~~~java
@interface Config {
    String path();
}
~~~

this is not merely renaming a local variable: for an annotation element, **the method name is the element name in metadata**, and bytecode callers may depend on the method signature.

Impacts:

- Old source `@Config("abc")` or `@Config(value="abc")` does not automatically map to `path`; the usage syntax must be changed.
- If `path()` has no default, old usage sites are missing a required value.
- Old readers calling `value()` may fail when the new binary no longer has that method.
- Old annotation usages store an element named `value`; changing it to `path` has no automatic renaming mechanism in class-file metadata.
- If the new name has a default, the system can read the default, but **there is no automatic conversion from the old value to the new value**.

Similarly, **removing an element** breaks source uses and old callers that depend on the removed element. Old metadata pairs not defined by the new annotation interface do not substitute for the removed method either. Do not take the fact that a piece of reflection "can still read the annotation" to conclude that removing an element is compatible.

**Recommendation:** If you want to rename a widely used element, consider keeping the old name during a transition phase, adding the new name with a default, and updating consumers to read according to a transparent precedence policy.

## 9. Safe Migration Strategy When a Type Change Is Needed

If an API goes from:

~~~java
@interface Settings {
    String mode() default "safe";
}
~~~

to a new enum, do not directly change `String mode()` to `Mode mode()` in a minor upgrade. A two-step strategy:

~~~java
enum Mode {
    UNSPECIFIED, SAFE, STRICT
}

@interface Settings {
    @Deprecated
    String mode() default "";  // old element, signature preserved
    Mode modeV2() default Mode.UNSPECIFIED; // new element
}
~~~

At new usage sites:

~~~java
@Settings(modeV2 = Mode.STRICT)
class NewClient {}
~~~

**Why choose the `UNSPECIFIED` sentinel?** So the consumer can distinguish "a new client selected an enum value" from "no enum provided, need to check the legacy element or old default." However, this is only an **API convention**: the annotation itself does not enforce precedence and does not automatically convert strings into enums.

Consumers can apply the following policy:

1. If `modeV2() != UNSPECIFIED`, use the new enum.
2. Otherwise, if `mode()` is non-empty, explicitly map the legacy `"safe"/"strict"` values to the enum.
3. If neither is specified, use the **documented fallback policy**.
4. If both are specified and conflict, report a clear error instead of picking arbitrarily.

Snippet illustrating the reading logic:

~~~java
static Mode resolve(Settings settings) {
    if (settings.modeV2() != Mode.UNSPECIFIED) {
        return settings.modeV2();
    }
    return switch (settings.mode()) {
        case "", "safe" -> Mode.SAFE;
        case "strict" -> Mode.STRICT;
        default -> throw new IllegalArgumentException(
                "Unknown legacy mode: " + settings.mode());
    };
}
~~~

The code above is an **illustrative helper** and needs to be placed in a class with visibility of `Settings` and `Mode`. It handles new and old sources with the legacy element, but it cannot automatically recover metadata already removed from binaries or handle every error caused by arbitrary ABI changes.

When rolling out the migration:

- Release version **A** adding `modeV2() default UNSPECIFIED` while keeping `mode()`.
- Update the processor/framework to understand both and warn about using the old value.
- Gradually migrate annotation usages to `modeV2`; test classes/JARs that have not been recompiled.
- Only consider **removing the legacy element** in an intentionally contract-breaking release, after clients have been updated.
- If the consumer has a security/validation policy, do not arbitrarily switch from a safe mode to a permissive default.

## 10. Changing `@Target`, `@Retention`, `@Inherited`, and `@Repeatable` Is Also Contract Evolution

Although the main focus is on elements/defaults/types, an annotation interface has several other parts of its contract that can cause breaking changes.

### 10.1. Changing `@Target`

If originally:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Marker {}
~~~

and then v2 only allows `METHOD`, sources that place `@Marker` on classes will no longer compile. **Narrowing the target** is usually a breaking source change. Widening the target can help new users, but you need to ensure consumers know how to handle metadata at the new locations.

### 10.2. Changing `@Retention`

Changing `RUNTIME` to `CLASS` prevents Java reflection from seeing the annotation as before, even though the metadata still resides in the class file under the `RuntimeInvisible...` group. Changing `SOURCE` to `RUNTIME` for new compilations does not cause old class files—which never stored `SOURCE` annotations—to suddenly gain runtime metadata; usages that need to preserve the annotation must be recompiled.

### 10.3. Changing `@Inherited`

Changing the `@Inherited` configuration can alter the result of `Class.getAnnotation(...)` on subclasses when the annotation type is read. However, `@Inherited` applies only along superclasses for annotations on classes; it does not automatically apply to overridden methods or interfaces that a class `implements`.

### 10.4. Changing `@Repeatable` and Containers

When allowing an annotation type to repeat, you must define an appropriate container: it must have a `value()` element whose type is an array of the original annotation, other methods must have suitable defaults, and retention/target must follow the language rules. Code using `getAnnotation(Foo.class)` may not see repeated annotations represented via the container, whereas `getAnnotationsByType(Foo.class)` handles them.

Changing the container, retention, or target of a repeatable annotation can affect source compilation, class-file representation, and reader frameworks. **You should not turn a singleton annotation API into a repeatable one merely by looking at the `@Repeatable` syntax while skipping compatibility tests**.

## 11. Annotation Defaults in Class Files and `javap -v`

When compiling the annotation interface:

~~~java
@interface Limit {
    int retries() default 2;
}
~~~

The compiler stores the **element default** in the `AnnotationDefault` attribute attached to the `retries()` method in the class file of the **annotation interface**.

Meanwhile, for:

~~~java
@Limit
class Service {}
~~~

The annotation usage on `Service` does not need to store an element-value pair `retries=2`. If you change the default in `Limit.class` to `5`, the element read from the old `Service.class` will take `5` according to the new definition.

To verify this yourself when you have a JDK:

~~~bash
javac --release 17 Limit.java Service.java
javap -v -p Limit
javap -v -p Service
~~~

- In `Limit.class`, look for `AnnotationDefault` on the element method.
- In `Service.class`, look for `RuntimeVisibleAnnotations` if `Limit` has `RUNTIME` retention; if `@Retention` is not declared, the default is `CLASS`, so look for `RuntimeInvisibleAnnotations`.
- With an explicit `@Limit(retries=2)`, `Service.class` contains the corresponding value in the annotation usage.

**Do not misread** constant-pool references or default values in the annotation interface as an explicit value in each client annotation.

## 12. Consequences for Annotation Processors, Code Generators, and Frameworks

There are two common types of consumers:

**(A) Compile-time annotation processor**

~~~java
AnnotationMirror mirror = /* metadata from Element */;
var explicit = mirror.getElementValues();
var effective = processingEnv.getElementUtils()
        .getElementValuesWithDefaults(mirror);
~~~

- `explicit` contains only the elements explicitly declared at the usage site.
- `effective` additionally includes defaults according to the current annotation type definition.
- Adding an element/default or changing a default can change generated files as soon as you rebuild.
- Changing types/names also causes processors that look up elements by name, type, or annotation proxy to fail if they are not migrated.
- The processor should report clear diagnostics if the annotation is used invalidly or if legacy values conflict.

**(B) Runtime framework using reflection**

~~~java
Rule rule = serviceClass.getAnnotation(Rule.class);
int retries = rule.retries();
~~~

- Changing a default can affect class files that have not been recompiled.
- Adding a required element without a default can cause `IncompleteAnnotationException` when accessed.
- A stored data type that is no longer compatible can cause `AnnotationTypeMismatchException`.
- Changing an enum constant/class literal can encounter the corresponding type-resolution errors.
- Changing retention/target/inheritance alters the presence of metadata.

Do not only test that the annotation interface "compiles"; test **precompiled client + new annotation type + new/old reader**. For frameworks that cache metadata, you also need to examine the lifecycle of the cache and class loader to avoid comparing results from two mismatched versions.

## 13. Versioning Strategy and Regression Testing

### 13.1. Pre-Release Decision Table

| Change | Old Source Compatibility | Runtime/Behavior Risk | Strategy |
|---|---|---|---|
| Add element **with default** | Usually preserved | New default may alter semantics | Choose a default that preserves old behavior, test binaries |
| Add element **without default** | **No** at old usages | `IncompleteAnnotationException` when reading old annotation | Breaking release or migration with default |
| Change default value | Usually preserved | **High if controlling policy**; affects old classes | Version the contract, audit implicit usages |
| Change element type | Usually **no** | Mismatch/linkage | Add new element alongside, deprecate old one |
| Rename element | Usually **no** | Old clients and data using old name | Alias/bridge with a transition period |
| Remove element | **No** if source uses element | Old callers may lose the method | Major/breaking release per project policy |
| Narrow `@Target` | No for excluded usages | Source build fails | Avoid unless usages have been migrated |
| Change `RUNTIME -> CLASS` | Syntax may remain valid | Reflection lacks metadata | Breaking release and test frameworks |
| Change an enum constant in use | No for code referencing old constant | `EnumConstantNotPresentException` may occur | Keep constant or perform intentional migration |

The word "usually" in the table is a reminder about **context**: an API also involves nested types, generic bounds, annotation inheritance, processor settings, and bytecode callers. This table is a review guideline, not a substitute for the JLS or actual testing.

### 13.2. Recommended Test Suite

1. **Recompile old source clients** against the new annotation interface to detect source incompatibilities.
2. **Keep the old `.class` files unchanged**, swap in the new annotation interface, and read via reflection; do not accidentally recompile everything.
3. **Run old reader binaries** against the new API if the library must support already-released artifacts.
4. **Verify explicit/default distinction**: `@Rule(retries=2)` and `@Rule` behave differently when the default changes.
5. **Test specific exceptions**: missing required element, type mismatch, enum constant/class literal no longer valid.
6. **Run the annotation processor** with old/new source versions; compare generated files and diagnostics.
7. **Test the framework's API contract**: target, retention, superclass, interface, repeatable annotation, metadata caching.
8. **Test across the actual JDK/build versions** supported by the product; do not rely solely on testing a single JVM.
9. **Document a migration guide** and how to transition annotation usages, including modules/JARs that cannot be recompiled immediately.

### 13.3. Avoiding a "Silent Semantic Break"

A default change from `false` to `true` on an annotation controlling a feature or security check can have serious impact without any compiler error. Such changes require review equivalent to changing the default configuration of a product API.

Consider:

- Using a **new element name** to represent a new meaning, instead of arbitrarily redefining an old value.
- If there is policy versioning, using a separate element such as `policyVersion() default 1` and reading conditionally, while controlling the risk of the default itself.
- Designing migrations using **default/sentinel + warning + intentional removal**, without changing the type immediately.
- Documenting the exact meaning of a value when unspecified, avoiding having consumers infer it from an arbitrary string.

## 14. Common Misconceptions

### "Adding a method to `@interface` does not affect old code."

Not true if the method is a **new element without a default**. Old sources lack the required value, and annotations in old binaries may cause `IncompleteAnnotationException` when read.

### "Changing `default` only affects recompiled classes."

False. The JLS specifies that defaults are applied when the annotation is read; usages **without an explicit value** can pick up the new default even with old binaries.

### "When a `String` element is changed to an enum, old strings are converted automatically."

No. Annotation element values follow specific types/encoding schemes. Old metadata can cause a mismatch; you must write migration logic and tests.

### "Adding `@Retention(RUNTIME)` will make `SOURCE` annotations in old JARs appear."

No. If the annotation was not stored during the earlier compilation, changing the retention type later does not reconstruct lost data.

### "I renamed the element, but the framework can guess the old value."

Frameworks have no default Java rule to map every element from an old name to a new name. To support this, you must keep a bridge/sentinel or implement migration yourself across both source and stored data.

### "`@Deprecated` makes the old method disappear from the API."

`@Deprecated` marks a warning/discouragement against use, but the method still exists until it is removed. This is why a legacy element can be kept through a transition period.

### "If `getAnnotation` returns non-`null`, all elements are safe to read."

No. An annotation proxy may exist, yet accessing **a specific element** triggers `IncompleteAnnotationException`, a mismatch, or an enum/class resolution error.

### "Source compatibility and behavioral compatibility are the same thing."

No. Changing a default is often the counterexample: source remains valid and method signatures may stay identical, yet runtime policy has changed.

## 15. Checklist for Annotation API Designers

- [ ] List all element names, types, defaults, `@Target`, and `@Retention` of the current version.
- [ ] Distinguish usages that provide explicit values from usages that rely on defaults.
- [ ] If adding an element: can you provide a default consistent with the old semantics?
- [ ] If requiring clients to supply a new value: have you treated that as a breaking source change?
- [ ] If changing a type/name: do you have a plan to keep the old element and add a new one rather than modifying the signature directly?
- [ ] If changing a default: have you verified the behavior of **unrecompiled class files**?
- [ ] If changing an enum/class literal: have you checked the values previously stored in old artifacts?
- [ ] If consumers use reflection: have you tested exceptions when accessing specific elements?
- [ ] If the consumer is a processor: have you distinguished `getElementValues()` from `getElementValuesWithDefaults()`?
- [ ] If the API has repeatable/inherited annotations: have you tested container/retention/target?
- [ ] Is there a clear migration guide, compatibility tests on target JDKs, and a versioning policy?

## 16. Authoritative Reference Documentation

- [JLS Java SE 17 9.6.1 — Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.1): element types and element declaration rules.
- [JLS Java SE 17 9.6.2 — Defaults for Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2): defaults are applied when the annotation is read; changing defaults affects usages that do not specify them explicitly.
- [JLS Java SE 17 9.7.1 — Normal Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1): valid annotation values and commensurability rules.
- [JLS Java SE 17 Chapter 13 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): binary compatibility rules as Java APIs evolve.
- [Java SE 17 — `IncompleteAnnotationException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/IncompleteAnnotationException.html): accessing a new element lacking a value and default on an old annotation.
- [Java SE 17 — `AnnotationTypeMismatchException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/AnnotationTypeMismatchException.html): annotation value in a binary is incompatible with the current element type.
- [Java SE 17 — `AnnotationMirror`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html) and [`Elements.getElementValuesWithDefaults`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html): distinguishing explicit values from defaults in annotation processing.
- [Java SE 17 JVM Spec 4.7.22 — `AnnotationDefault`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.22): representation of defaults in the annotation interface's class file.

**Conclusion:** In a Java library already used by clients, **adding an element with a default** is usually the least error-prone option; **adding a required element** or **renaming/changing a type** can break client source and binary metadata; **changing a default** is especially dangerous because it can immediately alter behavior for old annotation usages that have not been recompiled. Manage annotations as a true API contract, checking source, binary, reflection, processor, and semantics before releasing.
