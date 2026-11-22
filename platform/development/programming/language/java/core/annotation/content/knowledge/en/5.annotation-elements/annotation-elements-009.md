# Impact of Changing Default Values on Compiled Annotations in Java

A surprising characteristic of annotations in Java is that **changing the `default` of an annotation element can change the value read from a previously compiled class**, even without recompiling that class.

This happens when the annotation use site **does not explicitly declare** a value for the element in question. If the use site has declared an explicit value, that value is stored in the metadata of the using class and is not replaced by the new `default`.

The Java Language Specification (JLS) §9.6.2 clearly specifies that default values are not compiled into individual annotation use sites; they are applied dynamically when the annotation is read. Therefore, a small change in the annotation type can alter the behavior of previously compiled code, frameworks, or metadata-processing tools.

## 1. Distinguishing Explicit Values and Default Values

Consider the annotation type:

~~~java
package demo;

public @interface Dispatch {
    String channel() default "standard";
    int retries() default 1;
}
~~~

Two different usages:

~~~java
@Dispatch
class Unspecified {
}

@Dispatch(channel = "priority")
class Explicit {
}
~~~

- **Unspecified** does not declare `channel` or `retries`. When the annotation is read, both elements are supplied from the default values of the Dispatch type being used.
- **Explicit** declares **channel = "priority"** but does not declare `retries`. Thus, `channel` has the explicit value "priority"; `retries` is still taken from `default`.
- The **@Dispatch** syntax is completely valid because both elements of Dispatch have default values.

If the declaration is updated to:

~~~java
public @interface Dispatch {
    String channel() default "balanced";
    int retries() default 3;
}
~~~

then a program reading metadata against the new Dispatch version can observe:

| Annotated class | `channel()` with Dispatch v1 | `channel()` with Dispatch v2 | `retries()` v1 → v2 |
| --- | --- | --- | --- |
| **Unspecified** using `@Dispatch` | `standard` | `balanced` | `1` → `3` |
| **Explicit** using `@Dispatch(channel = "priority")` | `priority` | `priority` | `1` → `3` |

The results above do not require recompiling **Unspecified** or **Explicit**, provided that at runtime the program uses the correct new version of the **demo.Dispatch** type and keeps the remaining classes unchanged.

## 2. Why Does a Compiled Class Still Receive the New Default?

It is necessary to distinguish between two pieces of metadata located in **two different class files**:

**Annotation type — `Dispatch.class`:** declares the list of elements, their return types, and their corresponding default values. In the JVM class file format, the default value of each annotation element can be recorded in the **AnnotationDefault** attribute on the corresponding method.

**Using classes — `Unspecified.class`, `Explicit.class`:** record the annotation being used and the **explicitly specified** name–value pairs. With the appropriate retention, these pairs reside in the annotation metadata of the class file. The compiler does not need to copy the default of `channel()` or `retries()` into each use site.

Visualizing the reading process:

~~~text
                    Dispatch.class
                 ┌──────────────────────────┐
                 │ channel default=balanced │
                 │ retries default=3        │
                 └─────────────┬────────────┘
                               │
       when reading an element without an explicit value
                               │
  Unspecified.class            ▼              Explicit.class
  ┌────────────────┐      Value read          ┌──────────────────────────┐
  │ @Dispatch      │     from metadata        │ @Dispatch(channel=       │
  │ (not passed)   │                          │   "priority")            │
  └────────────────┘                          └──────────────────────────┘
  channel=balanced                            channel=priority
  retries=3                                   retries=3
~~~

This diagram illustrates the meaning of the metadata, not an exact byte-by-byte representation of the bytecode.

Key points:

1. **Without an explicit value** at the use site, the `default` is resolved when the annotation is read.
2. **When an explicit value is present**, that value is used; modifying the default does not overwrite explicit metadata.
3. Changing `default` alters the class file of the **annotation type**, rather than automatically modifying the bytecode of the classes annotated with it.
4. The application must actually use the **new annotation definition** in the runtime environment. Merely editing the source code while still running with the old Dispatch.class file will not change the result.
5. For reflection, **RUNTIME** retention is required to read annotations on a class via `Class.getAnnotation(...)`. The rule regarding `default` is not reflection-specific behavior; it is specified in the Java language for when an annotation is read.

**Distinguishing from an interface default method:** The syntax `String channel() default "balanced";` in an annotation declares an **element default value**. It is not a Java 8 **default method** with a body in a regular interface.

## 3. Java 17+ Experiment: Running Old Classes with a New Annotation Type

This experiment consists of **two compilation passes**. The first pass compiles all sources under version v1. The second pass recompiles only **Dispatch.java** under version v2. Keep the `Unspecified.class`, `Explicit.class`, and `Main.class` files untouched to demonstrate that the change occurs when the annotation is read.

Create the structure:

~~~text
src/
└── demo/
    ├── Dispatch.java
    ├── Unspecified.java
    ├── Explicit.java
    └── Main.java
~~~

### Step 1 — Version v1

**File `src/demo/Dispatch.java`:**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Dispatch {
    String channel() default "standard";
    int retries() default 1;
}
~~~

**File `src/demo/Unspecified.java`:**

~~~java
package demo;

@Dispatch
public class Unspecified {
}
~~~

**File `src/demo/Explicit.java`:**

~~~java
package demo;

@Dispatch(channel = "priority")
public class Explicit {
}
~~~

**File `src/demo/Main.java`:**

~~~java
package demo;

import java.lang.reflect.Method;

public class Main {
    public static void main(String[] args) throws NoSuchMethodException {
        Method method = Dispatch.class.getMethod("channel");
        System.out.println("annotation default=" + method.getDefaultValue());

        printConfig(Unspecified.class);
        printConfig(Explicit.class);
    }

    private static void printConfig(Class<?> type) {
        Dispatch annotation = type.getAnnotation(Dispatch.class);
        if (annotation == null) {
            System.out.println(type.getSimpleName() + ": missing @Dispatch");
            return;
        }

        System.out.println(type.getSimpleName()
                + ": channel=" + annotation.channel()
                + ", retries=" + annotation.retries());
    }
}
~~~

In the directory containing **src**, compile all four files at once:

~~~bash
javac -encoding UTF-8 -d out src/demo/Dispatch.java src/demo/Unspecified.java src/demo/Explicit.java src/demo/Main.java
java -cp out demo.Main
~~~

**Stdout of the v1 run:**

~~~text
annotation default=standard
Unspecified: channel=standard, retries=1
Explicit: channel=priority, retries=1
~~~

The first line comes from **Method.getDefaultValue()**, which reads the `default` declared on the `channel()` element of the Dispatch type. The next two lines come from the annotation attached to each class.

### Step 2 — Change Only the Annotation Type to v2

Keep the package name, type name, element list, return types, and **@Retention/@Target** unchanged. In the **src/demo/Dispatch.java** file, modify only the two values:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Dispatch {
    String channel() default "balanced";
    int retries() default 3;
}
~~~

The snippet above is the **modified declaration part**, keeping the `package demo;` line and the four imports of the file from step 1 intact. Do not modify the other three source files.

Compile **only the Dispatch.java file** into the same `out` directory and run again:

~~~bash
javac -encoding UTF-8 -d out src/demo/Dispatch.java
java -cp out demo.Main
~~~

**Stdout of the v2 run:**

~~~text
annotation default=balanced
Unspecified: channel=balanced, retries=3
Explicit: channel=priority, retries=3
~~~

Verification points:

- **Main.class**, **Unspecified.class**, and **Explicit.class** are still the binaries from the v1 compilation pass.
- Only **Dispatch.class** was updated. When starting a new JVM process and reading the annotation, `Unspecified` receives the v2 default values.
- `Explicit.channel()` remains "priority" because that value was explicitly declared when Explicit.class was compiled.
- `Explicit.retries()` changes from 1 to 3 because it was never explicitly declared.
- **getDefaultValue()** reads the current default value of the annotation method, independently of the values provided at use sites.

If the application is packaged into multiple JARs or modules, the same principle applies: the binary of the annotation use site and the binary defining the annotation type can be built at two different times. You need to know which version of the class file is actually loaded in the running process; the classpath, module path, and class loaders determine that.

### Inspecting Class Files with javap

After the v2 compilation, run:

~~~bash
javap -v -p out/demo/Dispatch.class
javap -v -p out/demo/Unspecified.class
javap -v -p out/demo/Explicit.class
~~~

Look for the relevant sections in the verbose output of `javap`:

- **Dispatch.class:** the `channel()` and `retries()` elements have **AnnotationDefault** information corresponding to "balanced" and 3.
- **Unspecified.class:** metadata for `demo.Dispatch` is present, but contains no explicit **channel = ...** or **retries = ...** pairs.
- **Explicit.class:** metadata has the **channel = "priority"** pair, but has no explicit `retries = ...` pair.

There is no need to rely on constant-pool entry numbers or how `javap` prints indices, as they can differ across compilers/JDK versions. What needs to be verified is that **explicit element-value pairs reside at the use site**, whereas **default values reside in the annotation type**.

## 4. What Happens When an Element Is Passed Explicitly?

If a class is compiled as follows:

~~~java
@Dispatch(channel = "manual", retries = 7)
class FullyExplicit {}
~~~

then changing `default "standard"` to `default "balanced"`, or changing `default 1` to `default 3`, **does not change the two observed values** on the compiled binary of FullyExplicit. Both "manual" and 7 have already been specified explicitly.

Mixed case:

~~~java
@Dispatch(channel = "priority")
class PartlyExplicit {}
~~~

only `channel` is fixed with an explicit value. `retries` still depends on the default declaration of the Dispatch version currently in use.

The scope of impact is therefore **per annotation element**, not for the annotation as a whole. A single annotation can both contain an element-value recorded in the class file and rely on a dynamic default for another element.

## 5. Does Changing a Default Break Binary Compatibility?

Two concepts must be separated:

**Binary compatibility:** a compiled binary can still be linked and executed by the JVM with the new type definition within the permitted scope of changes.

**Behavioral compatibility:** the program or framework still observes the same values and makes the same business decisions.

When **only changing the `default` value**, keeping the names/types/methods of the annotation elements unchanged, the binary of the using class can continue running without recompilation. **However, behavior can change** when code reads an element that was omitted.

Example:

~~~java
@interface Feature {
    boolean enabled() default false;
}
~~~

Suppose a framework enables a feature when it reads `enabled() == true`. Changing the default to **true** causes old classes that only wrote **@Feature** to potentially have the feature enabled, even though there was no change in the source or binary of those classes.

This can impact:

- **Feature flags:** old classes begin to be treated as having the feature enabled.
- **Validation:** changing the default value of a threshold can cause the same data to be accepted or rejected differently than before.
- **Retry, timeout, cache:** changing default parameters alters the number of retries, wait times, or cache expiration times without modifying the using class.
- **Security-sensitive metadata:** changing defaults such as `required`, `allowAnonymous`, or `roles` can change policies if the framework reads and interprets those elements.

The examples above refer to the **behavior of the annotation consumer**. Java does not automatically enable features, perform retries, or enforce permissions merely because an annotation is present.

## 6. When Adding a New Element or Removing a Default

Two related changes need to be evaluated separately from **only changing a default value**.

### Adding a New Element with a Default

From:

~~~java
@interface Audit {
    String category() default "general";
}
~~~

to:

~~~java
@interface Audit {
    String category() default "general";
    boolean required() default false;
}
~~~

A class previously compiled with **@Audit** does not have a `required = ...` pair in its metadata. With the new Audit version, when reading **required()** on that annotation, the default value **false** is used.

This helps extend the annotation structure without requiring all existing use sites to pass the new element. Even so, adding a field with a default can still alter framework logic if the framework begins interpreting the new field.

### Adding a Required Element or Removing an Existing Default

From:

~~~java
@interface Audit {
    String category() default "general";
}
~~~

to:

~~~java
@interface Audit {
    String category();
}
~~~

For new source code using **@Audit** without declaring category, the compiler reports a missing required element. For **an old class compiled** when category still had a default, it may still be possible to read the annotation object via reflection, but when calling **category()** without a recorded element-value and with no remaining default, Java reflection may throw **java.lang.annotation.IncompleteAnnotationException**.

This is a clear example of why the fact that the **JVM can still link the binary** is not sufficient to guarantee runtime safety. Depending on other changes such as changing a type, removing a method, or altering a referenced enum, the observed error may differ; one should not equate all annotation API changes with changing a `default` value.

## 7. Inspecting Defaults via Reflection and Limitations of Inspection

For an annotation type with **RUNTIME** retention, two commonly used APIs serve different purposes:

~~~java
Dispatch annotation = Unspecified.class.getAnnotation(Dispatch.class);
String effectiveChannel = annotation.channel();

Object declaredDefault =
        Dispatch.class.getMethod("channel").getDefaultValue();
~~~

- **annotation.channel():** retrieves the effective value at **a specific use site**. This can be either an explicit value or the current default value.
- **Method.getDefaultValue():** retrieves the default value declared on the **annotation element itself**, regardless of what explicit value a particular class passes. If the element does not declare a default, the result is **null**.
- For primitive elements such as **int retries()**, **getDefaultValue()** returns a boxed value, such as **Integer**, instead of a primitive.

**Do not infer that the two results are always equal.** In the v2 experiment, `Dispatch.channel()` on Explicit returns "priority", whereas `getDefaultValue()` on the channel method returns "balanced".

A reflection API for the effective value does not necessarily indicate directly whether that element-value was explicitly written in source code or filled in from a default. To accurately inspect the difference at the binary level, you can use `javap -v` or a class-file metadata reader tool. Standard Java reflection is geared toward reading effective values rather than reconstructing source syntax.

It is also necessary to distinguish **retention**:

- **RUNTIME:** the annotation can be accessed via reflection at runtime; the experiment example uses this policy.
- **CLASS:** the annotation is recorded in the class file, but is normally not accessible via reflection at runtime.
- **SOURCE:** the annotation is not retained in the class file after compilation.

The JLS rule regarding defaults is tied to when the annotation is read, but observability via a specific API also depends on retention and the metadata-processing component. Do not use a `getAnnotation(...) == null` result from a CLASS/SOURCE retention annotation to conclude that the default value has been frozen into the binary.

## 8. Common Reasoning Mistakes

| Statement or practice | Issue | Correct understanding |
| --- | --- | --- |
| “Every annotation use site contains a copy of the default at compile time.” | Incorrect regarding class file mechanics | The default resides in the annotation type definition and is applied at read time |
| “Changing a default requires recompiling all using classes.” | Not true when only changing the default value | Old classes can receive the new default via the new annotation definition |
| “Without recompilation, behavior is guaranteed not to change.” | Conflates binary compatibility and behavioral compatibility | Omitted elements and the consuming component must be checked |
| “Modifying a default overwrites values specified in @Annotation.” | Ignores explicit value pairs | Explicit values take precedence for that specific element |
| “Updating the annotation source alone is enough.” | The JVM might still load the old annotation class | Verify the exact binary/version/classpath or module path at runtime |
| “Annotations automatically enforce default changes.” | Annotations hold metadata | Code/frameworks/tools are needed to read and act upon the metadata |
| “Removing the default on an existing element is completely safe.” | Old classes may lack the element-value and fail under reflection | Evaluate the risk of throwing IncompleteAnnotationException |
| “getDefaultValue() returns the value declared on the using class.” | Confuses where the value is read from | getDefaultValue() reads the default on the annotation type's method |

## 9. Evaluation Process When Changing an Annotation Default in a Library

If an annotation is part of the public API of a library/framework, the change should be evaluated in the following order:

1. **Identify the changed element.** Record its name, type, old default, and new default; check whether only the default changed or if the signature/elements were also modified.
2. **Find use sites that omit that element.** Locations such as **@Dispatch** and **@Dispatch(channel = "priority")** do not explicitly specify every element. Each omitted element is a place that can receive the new value.
3. **Identify the metadata consumer.** An annotation processor, reflection, a class-scanning library, or a framework will determine the actual impact of the new value.
4. **Test mixing old binaries with the new annotation type.** Keep the compiled consumer classes unchanged and update only the annotation library, similar to the v1/v2 experiment.
5. **Check policy reversals.** If the default represents a security threshold, toggle option, or sensitive behavior, evaluate changing the value as a functional change that must be clearly communicated.
6. **Make intent explicit where stability is required.** Use sites that want to lock in behavior can declare the element explicitly, for example **@Dispatch(retries = 1)**, instead of relying on a default that may evolve.
7. **Verify the version actually loaded.** In systems with multiple dependencies or class loaders, tests must reflect the set of binaries actually deployed.

If a new default is introduced intentionally to change behavior in a new version of the framework, document the behavioral change in the release notes. Do not rely solely on the fact that the program still compiles or starts up to consider the change safe.

## 10. Self-Check Exercise

Given version v1:

~~~java
@interface Schedule {
    int interval() default 10;
    String unit() default "seconds";
}

@Schedule
class A {}

@Schedule(interval = 5)
class B {}

@Schedule(interval = 5, unit = "minutes")
class C {}
~~~

Suppose classes A, B, and C have already been compiled, and then only the `Schedule.class` version is updated to:

~~~java
@interface Schedule {
    int interval() default 20;
    String unit() default "minutes";
}
~~~

The effective values when reading the annotation with the new version are:

| Class | `interval()` | `unit()` | Explanation |
| --- | ---: | --- | --- |
| **A** | 20 | minutes | No elements passed explicitly |
| **B** | 5 | minutes | interval is explicit; unit uses the new default |
| **C** | 5 | minutes | Both elements are explicit, preserving the old values |

**Question:** If **default 20** is changed to **default 30**, which class can observe a different interval when read again with the new Schedule version? **Only A**, because B and C explicitly specified **interval = 5**.

**Question:** If `default` is removed from `unit()` while still running the old binaries, which classes risk failing when calling `unit()`? **A and B**, because they lack an explicit `unit` element-value; **C** still contains its `unit = "minutes"` value.

**Question:** Why is `javap` useful here? Because you can inspect the explicit element-value pairs recorded at the use site and the defaults on the annotation type, rather than inferring from the fact that the source appears unchanged.

## 11. Authoritative References

- **Java Language Specification §9.6.2 — Defaults for Annotation Interface Elements:** https://docs.oracle.com/javase/specs/jls/se22/html/jls-9.html#jls-9.6.2 — specifies that defaults are applied dynamically when the annotation is read and can affect compiled binaries.
- **Java Language Specification §13.5.8 — Annotation Interfaces:** https://docs.oracle.com/javase/specs/jls/se22/html/jls-13.html#jls-13.5.8 — distinguishes binary linking compatibility from the impact of annotation changes on reflective APIs.
- **Java SE 17 — Method.getDefaultValue():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue() — returns the default value declared on the element, or null if none exists.

Key takeaway when designing annotations: **a default is part of the annotation type's contract interpreted at read time**, not a fixed value copied into each class that uses the annotation. Therefore, changing a `default` must be evaluated at both the binary compatibility level and the actual behavioral level, especially when multiple versions of libraries and applications are deployed independently.
