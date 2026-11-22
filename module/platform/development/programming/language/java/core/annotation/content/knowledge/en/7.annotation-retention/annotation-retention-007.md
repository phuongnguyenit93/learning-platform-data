# Distinguishing the Lifecycle of an Annotation from the Lifecycle of an Annotated Object in Java

## 1. Two “Lifecycle” Concepts to Distinguish

In Java, an **annotation** is metadata attached to a location in source code: a class, interface, method, field, constructor, parameter, package, or module declaration, or a type-use location, depending on `@Target`. A **Java object** is an instance created during program execution, for example `new OrderService()`. The two have a descriptive relationship, but they **do not share the same lifecycle**.

- **Annotation lifecycle** in the context of `@Retention` refers to the extent to which annotation information is retained by the compiler: only in source, in the class file, or retrievable via reflection at runtime.
- **Object lifecycle** refers to when an instance is created, referenced/used by the program, and eventually becomes unreachable so that it can be reclaimed by the garbage collector.
- **Class** is at a different level from an object: multiple instances can be created from the same class, whereas an annotation on a class declaration describes the **type**, not each specific instance.

Example:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audited {}

@Audited
class OrderService {
    int count;
}

OrderService first = new OrderService();
OrderService second = new OrderService();
```

The snippet above only illustrates the relationship and is not a standalone runnable program. `@Audited` sits on the **class declaration** `OrderService`. Even though the two objects `first` and `second` are two distinct instances, they do not receive two independent copies of the class annotation. `first.count` and `second.count`, on the other hand, are two separate instance values.

What must be avoided is the reasoning: “Whenever a new object is created, another annotation on the class is also created, and when the object is garbage-collected, the annotation on the class is lost.” Neither idea matches how Java metadata works.

## 2. Three Annotation Retention Policies: SOURCE, CLASS, RUNTIME

`@Retention` determines whether an annotation is retained after compilation and whether it can be observed by Java reflection at runtime.

| Policy | Present in source code? | Stored in `.class` of the annotated element? | Readable by standard reflection at runtime? |
| --- | --- | --- | --- |
| `RetentionPolicy.SOURCE` | Yes | No | No |
| `RetentionPolicy.CLASS` | Yes | Yes | No |
| `RetentionPolicy.RUNTIME` | Yes | Yes | Yes, when on the right target and the annotation is present |

Example:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceHint {}

@Retention(RetentionPolicy.CLASS)
@interface ClassHint {}

@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeHint {}
```

The declarations above are an illustrative code snippet; to compile, they must be placed in valid positions inside a Java file along with the imports. If `@Retention` is omitted for an annotation type, the **default policy is `CLASS`**.

**SOURCE:** the compiler sees the annotation while processing the source; this annotation is not retained as an annotation of the compiled program. It is suitable for checks and conventions enforced at compile time. For instance, `@Override` is a classic annotation with `SOURCE` retention. The fact that the annotation is no longer in the class file **says nothing about how long instances of the class can exist**.

**CLASS:** the compiler retains the annotation in the class file, but standard reflection APIs such as `Class.getAnnotation(...)` do not expose it. Bytecode analysis tools can read this metadata from the class file. It also does not depend on whether a specific instance is still alive or has been garbage-collected.

**RUNTIME:** the compiler stores the annotation so the Java runtime can observe it using reflection, for example via `Class.getAnnotation`, `Field.getAnnotation`, or `Method.getAnnotation` matching the location where the annotation is attached. “RUNTIME” **does not mean** the annotation is an object that lives until the JVM shuts down, nor does it mean Java automatically executes logic written in the annotation's name.

The retention policy belongs to the **annotation type definition** and applies to all valid uses of that annotation type. Two uses of the same annotation type cannot choose different retentions at the point of application.

## 3. Timeline: From Source to Object

You can visualize the following independent progressions:

```text
Java source
  │   @SourceHint  @ClassHint  @RuntimeHint
  ▼
javac compiles
  ├── SOURCE: does not emit the corresponding annotation in the class file
  ├── CLASS:  stores metadata in the class file
  └── RUNTIME: stores metadata supported by reflection
  ▼
.class is loaded/defined as a class at runtime
  │
  ├── Can inspect class metadata via reflection (RUNTIME)
  │
  ├── new Example() ──► object A ──► used ──► may become eligible for GC
  │
  └── new Example() ──► object B ──► used ──► may become eligible for GC
```

This is an educational diagram, not a description of every detail of class loading or the garbage collector.

- **Compilation:** checks annotations according to type/target rules, may serve annotation processing tools, and then stores metadata according to retention. A class can be compiled even when no instances exist yet.
- **Class loading:** the JVM creates/maintains the runtime representation of the class when the class is loaded and used according to JVM rules. `RUNTIME` annotations on the class, methods, fields, etc. can be retrieved by reflection. A class does not necessarily need to be instantiated into an instance in order to inspect annotations on `Class<?>`.
- **Instance instantiation:** each `new` creates an object with its own instance state. `@Retention` does not determine when an object is created, whether a constructor is invoked, or the object's lifecycle.
- **Instance reclamation:** an object can become unreachable and eligible for GC. Collection timing is not guaranteed and cannot be inferred from annotations on the class. Class metadata is not “partially deleted” just because one instance goes away.
- **Class/class loader unloading:** the JVM may release data associated with a class/class loader when it is no longer in use according to runtime conditions. That is a matter of class and class loader lifecycle, **different** from individual instance lifecycle and also different from retention policy.

A `Class` at runtime is identified by its binary name **and its defining class loader**. You should not simply say “there is only one Class object per class name across the entire JVM” when multiple class loaders are involved. However, within a normal class-loading context, multiple instances created from the same class all point to the same runtime representation of that class.

## 4. Complete, Runnable Java 17+ Example

The following example uses three different retentions on the **same class**. The program then creates two instances to demonstrate that instance state can differ while the metadata of the class declaration remains unchanged.

Save the entire snippet below into the file **`AnnotationVsObjectDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
@interface SourceMarker {}

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.CLASS)
@interface ClassMarker {}

@Target({ElementType.TYPE, ElementType.FIELD})
@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeLabel {
    String value();
}

@SourceMarker
@ClassMarker
@RuntimeLabel("report-service")
final class ReportService {
    @RuntimeLabel("instance-counter")
    private int counter;

    ReportService(int counter) {
        this.counter = counter;
    }

    void increment() { counter++; }
    int counter() { return counter; }
}

public class AnnotationVsObjectDemo {
    public static void main(String[] args) throws NoSuchFieldException {
        ReportService first = new ReportService(1);
        ReportService second = new ReportService(10);
        Class<?> type = ReportService.class;
        Field field = type.getDeclaredField("counter");

        System.out.println("SOURCE via reflection: " + type.isAnnotationPresent(SourceMarker.class));
        System.out.println("CLASS via reflection: " + type.isAnnotationPresent(ClassMarker.class));
        System.out.println("RUNTIME via reflection: " + type.isAnnotationPresent(RuntimeLabel.class));
        System.out.println("Class label: " + type.getAnnotation(RuntimeLabel.class).value());
        System.out.println("Field label: " + field.getAnnotation(RuntimeLabel.class).value());
        System.out.println("Before: " + first.counter() + ", " + second.counter());
        first.increment();
        System.out.println("After: " + first.counter() + ", " + second.counter());
        System.out.println("Same runtime Class: " + (first.getClass() == second.getClass()));
    }
}
```

With **JDK 17 or later**, open a terminal in the directory containing the file:

```bash
javac --release 17 AnnotationVsObjectDemo.java
java AnnotationVsObjectDemo
```

**Exact stdout:**

```text
SOURCE via reflection: false
CLASS via reflection: false
RUNTIME via reflection: true
Class label: report-service
Field label: instance-counter
Before: 1, 10
After: 2, 10
Same runtime Class: true
```

The output has been verified by compiling with `javac --release 17` and running the program on a compatible JDK.

### Output Analysis

1. `ReportService` has three annotations on its **type declaration**. `SourceMarker` has `SOURCE` retention; `ClassMarker` has `CLASS` retention; `RuntimeLabel` has `RUNTIME` retention.
2. `isAnnotationPresent(SourceMarker.class)` returns `false`. The compiler omitted that annotation from the class file metadata; the existence of the objects `first` and `second` cannot make it appear.
3. `isAnnotationPresent(ClassMarker.class)` also returns `false`. That **does not prove that CLASS metadata is absent from the file**; it only means the runtime reflection API here does not expose `CLASS`-retention annotations.
4. `isAnnotationPresent(RuntimeLabel.class)` returns `true`. The `value()` element of the class annotation has the value `"report-service"`.
5. `Field` represents the **field declaration** `counter` and carries its own runtime annotation `"instance-counter"`. Even though `first.counter` is `1` and `second.counter` is `10`, there is still only one field declaration in the class; the field annotation is not stored separately per field value.
6. `first.increment()` only changes the state of the `first` object from `1` to `2`; the state of the `second` object remains `10`. The metadata values on the class and field also do not change.
7. `first.getClass() == second.getClass()` is `true`: both instances share the same runtime class in this example, regardless of the lifecycle and state of each individual object.

### CLASS Retention Can Be Observed in Bytecode

If you want to verify further after compilation, run the following command (the output is verbose and formatting varies by JDK version, so a fixed stdout is not shown):

```bash
javap -v ReportService
```

In the verbose output of the class file, the `javap` tool can show `RuntimeInvisibleAnnotations` with `ClassMarker` and `RuntimeVisibleAnnotations` with `RuntimeLabel`. `SourceMarker` is not emitted as an annotation of `ReportService` in the class file. The word **“Invisible”** here refers to **visibility through reflection**, not that an annotation attached to an object has been deleted.

## 5. Separating the Three Kinds of Data in the Example

| Information | What does it belong to? | Does it change when calling `new ReportService(...)` again? |
| --- | --- | --- |
| `@RuntimeLabel("report-service")` | Metadata of the `ReportService` declaration | Does not create a new class annotation just because another instance exists |
| `@RuntimeLabel("instance-counter")` | Metadata of the `counter` **field declaration** | Does not create separate field metadata for each object |
| `first.counter` | Own state of the `first` object | The new object has its own initial value |
| `second.counter` | Own state of the `second` object | Not modified when operating on `first.counter` |
| Reference variables `first`, `second` | References to instances during program execution | Can change, go out of scope, or stop keeping an object reachable |
| `ReportService.class` | Runtime representation of the type in the active class loader | Does not create a new class on each `new` |

An annotation placed on a **method declaration** likewise describes the method, not each individual method call. For example, `@Tracked` on `void handle()` does not generate a new annotation for the first call, second call, and so on. An annotation placed on a **parameter declaration** describes the parameter in the signature, not a new annotation created for each argument passed at call time.

For **type-use annotations** (for example, annotating a type-use position with `ElementType.TYPE_USE`), where the metadata is represented and how it is retrieved may differ from declaration annotations. However, it is still metadata attached to a declaration/type-use position in the compiled program, **not inherently per-object dynamic state**.

## 6. Does Reading an Annotation at Runtime Create an Object?

There are two concepts to keep separate:

- **Stored metadata:** with `RUNTIME`, the annotation and its values are stored in the compiled representation and supported for retrieval by the runtime via the reflection API.
- **Object representing the annotation:** when calling `ReportService.class.getAnnotation(RuntimeLabel.class)`, the JVM/reflection library may create or supply an object implementing the annotation interface so that Java code can invoke `value()`.

Therefore, the **Java object representing an annotation during reflection** and the **annotated instance of `ReportService`** are objects serving two different purposes. Do not rely on how many annotation representation objects are created, caching behavior, or reference comparison `==` between two reflection calls: that is not a contract needed to understand retention. When you need to inspect annotation values, use the API and element contents rather than inferring the identity of the representation object.

An annotation type is a form of interface in the language model; reflection returns a value of the corresponding annotation type. However, annotation elements **have no setters to mutate metadata on the class**. Values read from an annotation are declarative data, not instance variables of the annotated object.

For example, the snippet below illustrates usage inside a method that has access to `ReportService` and `RuntimeLabel`:

```java
RuntimeLabel label = ReportService.class.getAnnotation(RuntimeLabel.class);
System.out.println(label.value()); // report-service
```

Calling `new ReportService(100)` before or after this snippet does not make `label.value()` become `"100"`. If a program needs to store custom metadata **per instance**, use a field, an external data structure mapping instances to metadata, or a runtime mechanism suited to the problem; an annotation on the class does not serve that role.

## 7. RUNTIME Annotations and Garbage Collection: Key Misconceptions

Suppose an object is created:

```java
ReportService service = new ReportService(10);
service = null;
```

This code snippet is only illustrative and is not sufficient to assert when an object is actually collected. Assigning `null` to a variable only drops one reference; if another strong reference remains, the object can still be reachable. If the object is already unreachable, the garbage collector **may** reclaim it at an appropriate time.

However, the fact that this object is reclaimed:

- **Does not change the retention** of `SourceMarker`, `ClassMarker`, or `RuntimeLabel`.
- **Does not remove the annotation** `@RuntimeLabel("report-service")` from the `ReportService` type description while that class remains loaded and accessible at runtime.
- **Does not imply that the class is unloaded**. Class unloading concerns the eligibility to reclaim the class representation and class loader, governed by its own JVM conditions.
- **Does not prove whether the annotation has been executed or not**. Business logic only appears when there is code that actually consumes the annotation.

Conversely, `SOURCE` retention **does not make objects live shorter**, `CLASS` retention **does not make objects exist only during compilation**, and `RUNTIME` retention **does not keep every instance of the class alive until the JVM terminates**. The names of the retention levels only indicate the scope of annotation retention **across compile-time/runtime phases**, not an object memory management algorithm.

**Do not use `System.gc()` to “prove” annotation lifecycle**: that call does not guarantee that GC will run or collect a specific object. Reading a class annotation before/after an instance becomes unreachable can help explain the concept, but you do not need to rely on GC timing to confirm retention rules.

## 8. Does @Inherited Turn an Annotation into an Instance Property?

No. `@Inherited` is a **meta-annotation** that affects the lookup rules for annotations on a **class** when a subclass does not directly declare an annotation of the same type.

Example (a valid illustrative snippet, not a program with `main`):

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface Team {
    String value();
}

@Team("core")
class BaseService {}

class DerivedService extends BaseService {}
```

`DerivedService.class.getAnnotation(Team.class)` can return the `@Team("core")` annotation inherited for lookup purposes. However:

- This applies according to `@Inherited` rules when looking up annotations on a **class declaration via its superclass**, not by copying a new annotation for each instance.
- `@Inherited` does not cause annotations from an interface to automatically apply to an implementing class.
- `@Inherited` does not automatically apply the same inheritance rule to annotations on methods, fields, or parameters.
- It does not determine the lifetime of a `new DerivedService()` object.

For example, adding a subclass object and then losing the reference to that object does not change how `DerivedService.class.getAnnotation(Team.class)` is determined.

## 9. How Can Frameworks Alter Object Behavior from Annotations?

Some frameworks use reflection, classpath scanning, bytecode instrumentation, or annotation processing to read metadata and decide configuration or behavior. For example, a framework might see a `@Managed` annotation on a class, create an instance and place it in a container, or attach additional behavior when calling methods.

Here, three steps should be separated:

1. **Defining/placing the annotation:** describing metadata in source code.
2. **Retaining the annotation according to retention:** specifying which mechanisms can observe the metadata in source, class files, or at runtime.
3. **Having code that consumes the metadata:** a compiler plugin, annotation processor, framework, or logic you write reads the annotation and decides **whether to create objects, hold references, invoke methods, or destroy resources**.

For example, `@Retention(RUNTIME)` alone creates no objects and registers no beans. A framework may use annotations to manage objects, but **the lifecycle is managed by the framework and application code**, not automatically operated by retention itself.

If an annotation type has `SOURCE` retention, an annotation processor can still read it during source-processing rounds at compile time. If it has `CLASS` retention, bytecode analysis tools can observe the metadata. If it has `RUNTIME` retention, reflection can read it at runtime. Each tool must use the appropriate mechanism; do not equate “the annotation is stored” with “the annotation is automatically processed”.

## 10. Scenarios to Check Understanding

**Scenario A: a class has an annotation, with no objects created yet.**

You can still retrieve `ReportService.class.getAnnotation(RuntimeLabel.class)` when the class is validly used at runtime. You do not need to call `new ReportService(...)` beforehand for the class declaration annotation to appear.

**Scenario B: creating 1,000 objects from an annotated class.**

You have 1,000 instances (when they are actually created), each with its own state. That does not equate to 1,000 independent annotations attached to the class declaration. Reflection on the same runtime `Class` still reads the class declaration information.

**Scenario C: clearing the reference to an object.**

If the object is no longer reachable, it can be collected. The annotation attached to the class declaration remains defined according to the retention/class metadata while the class exists; you must not conclude that the retention changed to `SOURCE` or that the annotation disappeared.

**Scenario D: using a CLASS annotation but expecting `getAnnotation(...)` to retrieve its value.**

The reflection result is that the annotation is absent. If you want to read it via the reflection API at runtime, change the annotation definition to `@Retention(RetentionPolicy.RUNTIME)` and compile the corresponding code. Keeping `CLASS` can still be useful for tools that read class files.

**Scenario E: annotating a field whose value differs across objects.**

The annotation describes the **field declaration**. The instance field value can vary per object. If a processor wants to see the actual value of the field at a given moment, it needs to perform an extra step to read the field's value on the specific instance; the data from `Field.getAnnotation(...)` does not contain that runtime value.

**Scenario F: reading an annotation on a method after multiple method calls.**

`Method.getAnnotation(...)` still returns the metadata attached to the method declaration (if it has an appropriate retention). It does not reflect the invocation count, computed results, execution duration, or arguments passed in, unless another system collects them itself.

## 11. Practical Project Checklist

When designing or explaining an annotation, ask yourself:

1. **Where is the annotation attached?** Class, field, method, parameter, type use, package, or module? Use the appropriate `@Target`.
2. **Who needs to read the annotation and at what stage?** Compiler/annotation processor, bytecode inspection tool, or Java reflection at runtime? Choose `@Retention` to match the need.
3. **Is the data fixed declaration metadata or dynamic per-instance state?** Use annotations for metadata; use fields or a suitable runtime mechanism for dynamic state.
4. **Who actually uses the metadata to perform behavior?** Clearly identify the processor/framework/logic. Do not assume that attaching an annotation performs the task on its own.
5. **Are class/class loader lifecycles being confused with object lifecycle?** Object creation and GC are one process; class loading/unloading and metadata retention are another.
6. **Is the example verifiable?** Compile with JDK 17+, check stdout for reflection and object state, and use `javap -v` when you need to distinguish `CLASS` from `RUNTIME` metadata.

**Remember:** `SOURCE`, `CLASS`, and `RUNTIME` describe the **retention lifecycle of annotation metadata**, whereas `new`, references, and garbage collection describe the **lifecycle of instances created from a class**. These two axes are independent. An annotation attached to a class, field, or method declaration does not become per-object state simply because more objects are instantiated.
