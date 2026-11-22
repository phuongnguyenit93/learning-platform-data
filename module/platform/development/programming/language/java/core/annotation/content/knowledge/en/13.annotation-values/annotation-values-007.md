# Annotation Type Identity When Using Multiple Class Loaders in Java

## 1. The Problem: Same Annotation Name, but Value Not Found

A Java application can load code from multiple sources: the main program, plugins, extension modules, development tools, or the application runtime environment. In such cases, code may be loaded by **different class loaders**.

Suppose a class is annotated:

```java
@Feature("payment")
public class PaymentPlugin {}
```

The `Feature` annotation already declares `@Retention(RetentionPolicy.RUNTIME)`, yet code in the main program can still receive `null`:

```java
Feature feature = pluginClass.getAnnotation(Feature.class);
```

One major reason is that **`Feature.class` in the main program does not have the same type identity as the `Feature` used in the plugin class**. They may have the same *binary name*, the same bytecode, and the same elements, but are defined by different class loaders.

In Java, the fully qualified name is **not enough** to uniquely identify a type at runtime. This lesson focuses on the meaning of annotation type identity, its impact on annotation values read via reflection, diagnostic checks, and how to design class loader boundaries.

## 2. Runtime Identity of a Java Type

According to the JVM model, the runtime identity of a class or interface is determined by its **binary name** and the **class loader that defines that type** (*defining class loader*).

This can be expressed as:

```text
Runtime type identity = (binary name, defining class loader)
```

The same applies to an annotation type, because an annotation type is a specialized form of interface.

For example, two independent class loaders:

```text
Loader A                              Loader B
   │                                     │
   ├── demo.Feature  [Feature@A]         ├── demo.Feature  [Feature@B]
   └── demo.Plugin   [Plugin@A]          └── demo.Plugin   [Plugin@B]

Feature@A.getName() == Feature@B.getName()   → true
Feature@A == Feature@B                       → false
```

Here `Feature@A` and `Feature@B` are only illustrative notation for two different `Class<?>` objects, not Java type name syntax.

Within a single JVM:

- `Class.getName()` can return the same string, such as `demo.Feature`, for two separate types.
- Comparing `Class<?>` objects with `==` checks **exact type identity**, so the result is `false` if the two defining loaders are actually different.
- `Class.getClassLoader()` indicates the loader that defines the corresponding class; for some platform classes defined by the bootstrap loader, this API may return `null`.
- Two separate types are not automatically compatible when casting, calling `isInstance`, or passing as an argument to `getAnnotation`, even though their bytecode and element names are identical.

### Defining Loader Differs from Initiating Loader

A class loader can **delegate** class loading to a parent loader. The loader that initially receives the request may not be the loader that **defines** the returned class.

For example, the Plugin Loader calls `loadClass("api.Feature")`, but if parent delegation forwards the request up to the App Loader and the App Loader defines `api.Feature`, then both sides can receive the same `Class<?>` object. In that case, **two type identities do not occur** for `api.Feature`.

Therefore, do not conclude that “a plugin has its own class loader” means “every class of the plugin is redefined”. What decides it is **which loader actually defines the annotation type**.

## 3. Annotation Types Also Have an Identity Independent of Name

A normal annotation definition:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Feature {
    String value();
}
```

If the same `demo/Feature.class` file is defined by two independent loaders, we have two annotation interfaces at runtime. Each type has a `value()` element returning `String`, the same name `demo.Feature`, and the same `RUNTIME` retention, yet the JVM still treats them as **two different types**.

For an annotation usage on the class `demo.Plugin` loaded by Loader A, the metadata is resolved to the type `Feature@A` according to the loading and resolution environment of that class. When the main program's API passes `Feature@B.class` to `getAnnotation`, the API must look for an annotation **of the exact type `Feature@B`**, rather than searching merely by name string.

This is an important principle:

> Runtime reflection looks up annotations by the **annotation type's `Class` object**, not merely by name string.

A match in `value()`, retention, or the path of the `.class` file does not turn two types from different loaders into a single type.

## 4. Conditions for Reading Annotations via Reflection

Even when the right class loader is already used, the usual conditions still apply:

1. **The annotation type has `@Retention(RetentionPolicy.RUNTIME)`.** If it uses the default `CLASS` or is set to `SOURCE`, `Class.getAnnotation(...)` cannot see the metadata through standard reflection.
2. **The queried target is the annotated element.** `Class<?>` reads class-level annotations; annotations on a method require querying the corresponding `Method`, and annotations on a package require querying `Package`.
3. **The passed annotation type must match the runtime identity.** `pluginClass.getAnnotation(annotationClass)` uses the exact `Class<A>` passed to it.
4. **The class and annotation type must load/resolve successfully.** Classpath issues, missing dependencies, or a class loader being unable to read metadata can cause errors during reflection.
5. **For repeated annotations, choose the appropriate API.** `getAnnotationsByType(...)` can read values inside a repeatable container; `getAnnotation(...)` does not automatically unwrap a container holding multiple annotations.

A `null` result from `getAnnotation` does not indicate a single unique cause. It could be due to the annotation not being present, an unsuitable retention policy, querying the wrong location, only a repeatable container being present, or an annotation type from a different class loader.

A reliable way to investigate is to inspect **which element the annotation is declared on**, **the actual runtime type of the annotation**, and **the class loader that defines each type**.

## 5. Complete Java 17+ Program: Two Loaders Loading the Same Annotation Type

The example below demonstrates the difference using two independent `URLClassLoader` instances loading **the same class file directory**. They have a `null` parent so they do not delegate the `demo.Feature` type to the application class loader. Core Java platform classes are still provided by the JVM via bootstrap loading.

Create the structure:

```text
src/
├── LoaderIdentityDemo.java
└── demo/
    ├── Feature.java
    └── Plugin.java
```

### File `src/demo/Feature.java`

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Feature {
    String value();
}
```

### File `src/demo/Plugin.java`

```java
package demo;

@Feature("isolated")
public class Plugin {
}
```

### File `src/LoaderIdentityDemo.java`

```java
import java.lang.annotation.Annotation;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderIdentityDemo {
    public static void main(String[] args) throws Exception {
        Path output = Path.of(args[0]).toAbsolutePath();
        URL location = output.toUri().toURL();
        URL[] paths = {location};

        try (URLClassLoader first = new URLClassLoader(paths, null);
             URLClassLoader second = new URLClassLoader(paths, null)) {

            Class<? extends Annotation> featureA =
                    Class.forName("demo.Feature", true, first)
                         .asSubclass(Annotation.class);
            Class<? extends Annotation> featureB =
                    Class.forName("demo.Feature", true, second)
                         .asSubclass(Annotation.class);

            Class<?> pluginA = Class.forName("demo.Plugin", true, first);
            Class<?> pluginB = Class.forName("demo.Plugin", true, second);

            Annotation foundWithA = pluginA.getAnnotation(featureA);
            Annotation foundWithB = pluginA.getAnnotation(featureB);

            System.out.println("same name="
                    + featureA.getName().equals(featureB.getName()));
            System.out.println("same Class="
                    + (featureA == featureB));
            System.out.println("same Plugin Class="
                    + (pluginA == pluginB));
            System.out.println("same defining loader="
                    + (featureA.getClassLoader() == featureB.getClassLoader()));
            System.out.println("found with own type="
                    + (foundWithA != null));
            System.out.println("found with foreign type="
                    + (foundWithB != null));
            System.out.println("annotationType matches own="
                    + (foundWithA.annotationType() == featureA));
            System.out.println("foreign type accepts annotation="
                    + featureB.isInstance(foundWithA));
            System.out.println("annotation value="
                    + featureA.getMethod("value").invoke(foundWithA));
        }
    }
}
```

From the directory containing `src`, using JDK 17 or later:

```bash
javac -d out src/demo/Feature.java src/demo/Plugin.java src/LoaderIdentityDemo.java
java -cp out LoaderIdentityDemo out
```

**Expected stdout, in order:**

```text
same name=true
same Class=false
same Plugin Class=false
same defining loader=false
found with own type=true
found with foreign type=false
annotationType matches own=true
foreign type accepts annotation=false
annotation value=isolated
```

### Why Does the Program Produce That Output?

- Both Loader A and Loader B read the same `demo.Feature` bytecode. Their `getName()` strings are equal.
- Because each `URLClassLoader` is created independently and each defines `demo.Feature` itself, `featureA == featureB` is `false`.
- `demo.Plugin` is also defined separately in each loader, so `pluginA != pluginB`.
- `@Feature("isolated")` in `Plugin@A` is resolved to the annotation type `Feature@A`.
- `pluginA.getAnnotation(featureA)` finds the annotation. `pluginA.getAnnotation(featureB)` does not find it because a type from Loader B is passed.
- `foundWithA.annotationType()` returns the exact `featureA` type object.
- `featureB.isInstance(foundWithA)` is `false` because that annotation instance does not implement the `Feature@B` interface.
- Reflection invoking `value()` on **`featureA` itself** returns the string `"isolated"` without needing a compile-time import of `demo.Feature` in the driver program.

The example places `demo.Feature` and `demo.Plugin` in the same output directory for easy experimentation. In practice, two loaders may read from different JARs or two copies of a dependency; the nature of type identity remains the same.

**Intentional limitation:** The driver program does not cast the result to `demo.Feature` at compile time. It uses the standard `Annotation` interface and reflection to work with the annotation type returned by the corresponding loader.

## 6. `Annotation.annotationType()`: Distinguishing the Actual Type from the Display Name

Once an annotation instance has been read:

```java
Annotation annotation = someAnnotation;
Class<? extends Annotation> actualType = annotation.annotationType();
```

`annotationType()` returns **the `Class` object representing the exact annotation interface** of that instance. This is a more reliable basis than merely extracting the name from `toString()`.

Example of a diagnostic check in a helper:

```java
import java.lang.annotation.Annotation;

class AnnotationDiagnostic {
    static void printIdentity(Annotation annotation) {
        Class<? extends Annotation> type = annotation.annotationType();
        ClassLoader loader = type.getClassLoader();
        System.out.println("annotation name: " + type.getName());
        System.out.println("defining loader: " + loader);
    }
}
```

This helper is illustrative and will compile when placed in an `AnnotationDiagnostic.java` file; the output of `ClassLoader.toString()` is environment-dependent, so **there is no single fixed stdout string** to memorize.

To compare exact types:

```java
boolean sameRuntimeType =
        left.annotationType() == right.annotationType();
```

If you only compare:

```java
boolean sameBinaryName =
        left.annotationType().getName()
                .equals(right.annotationType().getName());
```

then you only know that **their names are equal**, which does not prove the two annotations share the same type identity.

### Do Not Use `toString()` or `hashCode()` to Distinguish Class Loaders

`Annotation.toString()` is primarily intended for human-readable representation; the output can look identical even when the two types are different. An annotation's `hashCode()` is specified based on element names and values; it is not a loader identity key.

`Annotation.equals(...)` also has a contract that compares the annotation type and its elements. Two annotation instances with different type identities do not become annotations of the same type just because they share the same name and the same values. If you need to detect loader boundaries, compare `annotationType()` or use `Class.isInstance(...)` as appropriate.

## 7. Why Can Casting an Annotation Cause a `ClassCastException`?

Suppose the application compiles against an annotation type `api.Flag` defined by the application's loader, while a plugin contains a copy of `api.Flag` defined by the plugin loader.

The host side might write:

```java
// Illustrative example: annotation provided by the plugin.
Annotation candidate = obtainPluginAnnotation();

// May throw ClassCastException if candidate belongs to api.Flag from a different loader.
Flag flag = (Flag) candidate;
```

This is only an illustrative code snippet, assuming `Flag` and `obtainPluginAnnotation()` already exist. The error can manifest as two types bearing the same package and class name but belonging to two different loaders.

A safer way to check:

```java
if (Flag.class.isInstance(candidate)) {
    Flag flag = Flag.class.cast(candidate);
    System.out.println(flag.value());
} else {
    System.out.println("Incompatible annotation runtime type");
}
```

`isInstance` checks **assignability according to the actual runtime identity**, rather than inferring from the name. If the types do not match, you need to fix the class loader structure or how the API is shared; you should not force a cast or assume the two annotation types are unified.

A `ClassCastException` can also occur when interfaces/classes in an **element value** or plugin contract have duplicate definitions; class loaders affect many types, not just annotations.

## 8. Relationship with `Class<?>` in Annotation Values

An annotation can declare an element of type `Class<?>`:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface HandlerType {
    Class<?> value();
}
```

Usage:

```java
@HandlerType(MyHandler.class)
class HandlerOwner {}
```

When read, the value of `HandlerType.value()` is a `Class<?>` object representing the handler type referenced in the metadata. In a multi-loader environment, **the identity of `MyHandler` also depends on its defining loader**, not just its name.

This has two consequences:

- `value().getName()` may match the name of a host class, yet `value() == HostHandler.class` is still `false`.
- If the system uses this class literal to select/instantiate a handler, it needs to verify whether it actually implements the interface shared through the right loader, for example `Service.class.isAssignableFrom(handlerClass)`.

Do not treat a name string like `"demo.MyHandler"` as proof that two `Class<?>` objects are the same. Reflection is only truly reliable when you know the loader that owns the type and the corresponding inheritance relationship.

If the class referenced in the annotation value cannot be loaded or resolved when reading the element, accessing it may throw errors such as `TypeNotPresentException` or other class-loading-related errors. Errors should be handled according to the actual plugin, dependency, and classpath context.

## 9. Repeated Annotations and Containers with Multiple Loaders

A repeatable annotation is defined by a pair of types:

```java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Tags {
    Tag[] value();
}
```

`@Repeatable(Tags.class)` points to **a specific container annotation type**, and `Tags.value()` returns an array of **the exact `Tag` annotation type**. If a plugin defines both `Tag` and `Tags` using its own loader, a host defining a pair of types with the same names using a different loader will not automatically share the same identity.

Therefore, code like:

```java
Tag[] tags = pluginClass.getAnnotationsByType(Tag.class);
```

can return an empty array if `Tag.class` on the host is not the `Tag` type that `pluginClass` actually uses. `getAnnotationsByType` is capable of unwrapping a container **of the same type system**, but it does not “merge” annotation types simply because `Tag` and `Tags` from two loaders share the same names.

When supporting repeatable annotations across a plugin boundary, it is best to share **both the repeatable annotation and the container type** in a common API so that all components reference those exact `Class` objects.

### Reading via the Exact Runtime Type

In a plugin discovery program, you can look up the annotation type already loaded by the plugin:

```java
Class<?> unknown = Class.forName("demo.Tag", false, pluginLoader);
Class<? extends Annotation> actualTag =
        unknown.asSubclass(Annotation.class);

Annotation[] tags = pluginClass.getAnnotationsByType(actualTag);
```

The code is an illustrative snippet requiring `import java.lang.annotation.Annotation;` and existing `pluginLoader`/`pluginClass` variables. The result is an array of annotations that the runtime recognizes as the exact `actualTag` type. This approach is useful for generic tooling, but if the host needs to invoke elements through a statically typed Java interface, you should share the annotation definition between host and plugin instead of working only with generic `Annotation` objects.

## 10. Designing Class Loaders So Host and Plugin Share the Annotation API

Most plugin systems want the host to be able to write directly:

```java
Feature feature = pluginClass.getAnnotation(Feature.class);
```

In that case, the host and plugin **must reference the same runtime identity of `Feature`**. A common architecture:

```text
Bootstrap / Platform
        │
Application (shared API)
        ├── api.Feature
        ├── api.PluginService
        │
        ├── Plugin Loader A
        │      └── plugin.a.SomePlugin
        │
        └── Plugin Loader B
               └── plugin.b.OtherPlugin
```

Principles:

1. Place `api.Feature` and plugin contract interfaces in a **shared API artifact**, defined by a parent class loader or a common shared loader.
2. Ensure the plugin loader **delegates shared API packages** to that loader instead of defining its own copy of `api.Feature`.
3. Do not repackage the API as a separate class with the same name inside each plugin if the plugin class loader might redefine it; pay special attention to *child-first* configurations.
4. Verify at runtime using `hostFeatureClass == pluginResolvedFeatureClass` and `getClassLoader()`, rather than relying solely on the build-time dependency graph.
5. Package the plugin's internal dependencies according to an appropriate policy; only types that need to be exchanged across the host–plugin boundary are required to have a shared identity.

A shared *plugin API* allows the host to call elements directly, attach configuration, check `Service.class.isAssignableFrom(pluginClass)`, and pass objects across class loader boundaries safely.

In practice, if default parent-first delegation is used, a child loader normally receives the API version from the parent when the parent is able to load it. For child-first loaders or shaded JARs, exceptions must be configured for the API packages. **You should not assume that default delegation applies to every custom loader**.

## 11. How to Diagnose When `getAnnotation` Returns `null`

When a plugin class appears to be annotated but the host cannot read it, check systematically in order.

### Step 1 — Check Retention and Target Location

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface PluginMarker {}
```

The annotation type must have `RUNTIME` retention and the annotation must be attached to **the exact target** being queried. If the annotation is on a method, query `Method.getAnnotation(...)`. If it is repeatable, use `getAnnotationsByType(...)`.

### Step 2 — Check the Type the Host Is Querying

```java
Class<? extends Annotation> requested = PluginMarker.class;
System.out.println(requested.getName());
System.out.println(requested.getClassLoader());
```

This illustrative snippet requires importing `java.lang.annotation.Annotation`. The loader output is runtime-dependent.

### Step 3 — List the Annotations Present on the Plugin Class

```java
for (Annotation a : pluginClass.getDeclaredAnnotations()) {
    Class<? extends Annotation> actual = a.annotationType();
    System.out.println(actual.getName());
    System.out.println(actual.getClassLoader());
    System.out.println(actual == requested);
}
```

This is illustrative code assuming `pluginClass`, `requested`, and the necessary imports are present. If an annotation is found whose name equals `requested.getName()` but `actual != requested`, that is direct evidence of **two different type identities**.

Note: if the annotation is repeatable and held via a container, `getDeclaredAnnotations()` may list **the container**. In that case, you need to check the container of the matching type and then use `getDeclaredAnnotationsByType(actualRepeatableType)` or inspect the container's contents. The result also depends on retention and whether the metadata can be resolved at runtime.

### Step 4 — Check the Loader That Actually Defines the Type

```java
Class<?> fromPlugin =
        Class.forName(requested.getName(), false,
                pluginClass.getClassLoader());

System.out.println(fromPlugin == requested);
```

If the result is `false`, the same name has been resolved into two different `Class<?>` objects. If the result is `true`, then the plugin loader sees the right shared type, and you should proceed to review retention, target, placement, and compilation/packaging status.

Do not use `Class.forName(name)` without specifying a loader as a definitive test; that call typically uses the caller's class loader and may not be the loader owning the plugin class.

### Step 5 — Check Artifacts and Loading Policy

Check whether the API library has been copied into multiple JARs, shaded, bundled inside the plugin, or reloaded by a child-first loader. If a class file is modified or a class loader uses custom rules, do not infer the outcome solely from the file name.

You can inspect bytecode with `javap -v` to confirm class-level metadata when needed. However, a class file containing the annotation name **does not tell the whole story about the defining loader that will be used at runtime**; you must also observe the running environment.

## 12. Common Mistakes and Misconceptions

| Symptom | Common Misconception | How to Verify and Resolve |
|---|---|---|
| `getAnnotation` returns `null` even though the class has the annotation | Matching names are enough | Compare the actual annotation's `Class<?>` with the requested type; check retention |
| `ClassCastException` when casting an annotation or service | Two classes with the same name are considered the same type | Check `isInstance`, `isAssignableFrom`, and the defining loader |
| `getName()` is identical but `==` differs | “Same bytecode must be the same class” | Check which class loader actually defines the type |
| Plugin loader has the host as its parent yet still duplicates the type | Assuming every custom loader is parent-first | Check `loadClass`/delegation policy and duplicate API copies in JARs |
| Repeated annotations are not found by `getAnnotationsByType` | Containers automatically bridge across loaders | Share both the repeatable type and the container type; verify the exact `Class` |
| `Feature.class` from the host fails to read plugin metadata | Only fixing `@Retention` | Confirm the exact type identity; retention does not fix loader issues |
| An annotation with a `Class<?>` element causes issues | The class value's name is enough to invoke the type on the host | Inspect the `Class<?>` identity, loader, dependencies, and resolvability |
| `toString()` looks identical | Using the string representation as identity | Use `annotationType()` and `Class<?>` for checks |
| Reflection tools fail to retrieve the annotation | Concluding the metadata definitely does not exist | Distinguish between runtime reflection, bytecode scanners, and actual artifacts |

### Special Error: The Annotation Class Is Present, but the Element Method Is No Longer Compatible

When two sides use different versions of an annotation API, the error is not necessarily just `null`. You may encounter `IncompleteAnnotationException` when the runtime annotation is missing a required value according to the current type version, `AnnotationTypeMismatchException` when an element's value type has changed, or errors related to a class/enum that no longer exists.

These errors relate to **annotation schema evolution and binary incompatibility**, which can occur even when both sides already see the same runtime type identity. You should verify dependency versions and recompile the appropriate artifacts; do not attribute every reflection error to class loaders.

## 13. Self-Check Exercises

Consider the scenario:

```text
PluginLoader1 ──> com.acme.audit.Audited (version 1)
PluginLoader2 ──> com.acme.audit.Audited (version 1)
HostLoader    ──> com.acme.audit.Audited (version 1)
```

Suppose the three loaders **actually define the annotation type themselves** as separate copies, without sharing via a parent. The class `com.acme.payments.Payment` defined by `PluginLoader1` is annotated with `@Audited` having `RUNTIME` retention.

Answer the following:

1. Do the three `Class<?>` objects for `com.acme.audit.Audited` have the same `getName()`?
2. Is `Audited` from PluginLoader1 `==` `Audited` from HostLoader?
3. Can the host automatically read that annotation using `Payment.class.getAnnotation(HostAuditedClass)`?
4. If you look up the exact `Audited` from PluginLoader1, can you call `getAnnotation(...)` and retrieve the instance?
5. Does `annotation.annotationType().getName()` equaling the name of `HostAuditedClass` prove that the two types are the same?
6. If PluginLoader1 is configured to delegate the `com.acme.audit` package to HostLoader, and the plugin code uses the host's API properly, how might the behavior change?
7. Are two annotation instances with the same `value` but belonging to interfaces defined by two loaders considered the same runtime annotation type?
8. Is sharing only one of the two types for a repeatable annotation `@Label` and its container `@Labels` a reliable design for reflection?
9. Does changing `@Retention(CLASS)` to `RUNTIME` automatically unify two annotation interfaces defined by two loaders?
10. When the API in the host and the plugin share the same name but have different identities, what design approach is generally appropriate?

**Answers:**

1. **Yes.** Same binary name.
2. **No.** Different defining loaders produce different runtime type identities.
3. **No.** The query requires the exact annotation type from HostLoader; the metadata on the plugin uses the type from PluginLoader1.
4. **Yes**, provided the metadata and loading/resolution succeed. Query using the exact `Class<? extends Annotation>` of the type used by the plugin.
5. **No.** The name string only proves the names match; you must compare the `Class<?>` objects.
6. **They can share the same identity.** If the `Audited` type is defined by HostLoader and the plugin actually delegates to use that copy, the host and plugin will share the same `Class<?>`, making reflection and casting valid.
7. **No.** Identical element values do not change the annotation type's identity.
8. **No.** The repeatable/container pair should be shared consistently if you want the host to read them using compiled Java types.
9. **No.** Retention determines metadata visibility via reflection; it does not unify types across loaders.
10. **Place the shared annotation/API contract in a parent loader or shared loader**, configure delegation appropriately, and prevent plugins from redefining the API types that need to be exchanged.

## 14. Implementation Checklist for Plugin Applications

- Determine whether the annotation is used on a class, method, field, package, or type-use to select the right reflection target.
- Declare `@Retention(RetentionPolicy.RUNTIME)` if the consumer uses Java reflection.
- Identify the binary name **and defining loader** of the annotation type that the consumer passes to `getAnnotation`.
- Do not treat `Class.getName()` or `Annotation.toString()` as sole proof of the same type identity.
- Compare `annotation.annotationType() == requestedType` or use `Class.isInstance` when an exact check is needed.
- Distinguish between the *initiating loader* and the *defining loader*; check the actual parent delegation.
- When the host uses a statically typed annotation API, share the annotation definition through a common loader rather than bundling a separate copy in each plugin.
- For repeatable annotations, share both the repeatable type and the container type, and choose `getAnnotationsByType` when you need to read multiple values.
- For elements containing `Class<?>`, check the loadability and compatibility of the referenced type.
- Check retention, bytecode, module/build artifacts, classpath, and dependency versions if reflection still fails.
- Use a test with two genuinely independent loaders to identify the issue; do not assume a custom loader automatically creates a new type.
- Do not try to cast objects from a different loader to mask an architectural issue; redefine the boundary of the shared contract.

When working with annotations in a multi-class-loader system, the most important question is not only **“what is the annotation's name?”**, but also **“which `Class` object represents that annotation, and which loader defines it?”**. Answering these two questions accurately helps distinguish retention/lookup errors from type identity errors, leading to a more reliable metadata design between host and plugin.
