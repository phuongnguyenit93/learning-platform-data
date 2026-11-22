# Relationship Between Annotation Types and `java.lang.annotation.Annotation` in Java

## 1. What Type Does `@interface` Actually Declare?

When writing a custom annotation:

~~~java
@interface Checkpoint {
    String value();
}
~~~

Java does not create an ordinary class. The syntax **`@interface` declares an annotation type**, which is a **special kind of interface** in Java's type system.

According to the Java Language Specification (JLS §9.6), **the direct superinterface of every annotation type is always `java.lang.annotation.Annotation`**. This relationship is implicitly defined by the language; programmers neither need to nor are allowed to add an `extends` clause to an `@interface` declaration.

The type structure can be visualized as follows:

~~~text
java.lang.annotation.Annotation     (ordinary interface in the JDK)
                  ^
                  | extends implicitly defined by the language
                  |
            @interface Checkpoint    (annotation type)
                  ^
                  | type of the annotation value being read
                  |
           @Checkpoint("start")       (a usage)
~~~

The last arrow indicates the relationship between **type** and **value**, not an inheritance relationship of the annotated class: a class carrying `@Checkpoint` does not thereby `extends Checkpoint` or `implements Annotation`.

For example:

~~~java
@Checkpoint("start")
class Job {
}
~~~

`Job` remains the class `Job` in the normal inheritance hierarchy. The `@Checkpoint("start")` metadata is attached to **the `Job` declaration**; the relationship with `Annotation` belongs to **the `Checkpoint` annotation type**, not to `Job`.

The key point is to distinguish three concepts:

1. **`Annotation`**: the root interface in the standard library that defines the common contract for objects representing annotations.
2. **`Checkpoint`**: the annotation type we declare with `@interface`, which implicitly has `Annotation` as its superinterface.
3. **`@Checkpoint("start")`**: the annotation usage syntax to attach metadata to a program element.

## 2. Why Not Declare `extends Annotation`?

Let's compare the two kinds of declarations.

**Ordinary Java interface:**

~~~java
interface Named {
    String name();
}

interface Labeled extends Named {
    int level();
}
~~~

An ordinary interface can explicitly state `extends` according to Java syntax. Conversely, an annotation declaration must follow this pattern:

~~~java
@interface Marker {
}

@interface Label {
    String value();
}
~~~

Attempting to write the following form is **syntactically invalid**:

~~~java
// Illustrates INVALID code; do not include in a runnable program file:
//
// @interface Bad extends java.lang.annotation.Annotation {
// }
~~~

The reason is that the `@interface` grammar does not allow an `extends` clause and also does not support type parameters like a generic interface. The compiler itself already knows that the superinterface of every annotation type is `java.lang.annotation.Annotation`.

Therefore, it is not that Java “forgot to write” `extends Annotation`; it is a language rule designed to define a special category of types with its own restrictions on members and usage.

Two things that are easy to confuse:

- **`java.lang.annotation.Annotation` is an interface, but not an annotation type.** You cannot use `@Annotation` as a valid annotation simply because it is the root interface.
- An ordinary interface that extends an annotation interface does not automatically become an annotation type either. **Only a declaration using the `@interface` syntax** declares an annotation type.

## 3. Testing the Type Relationship Using Reflection

Given an annotation type named `Checkpoint`, the following checks have different meanings:

| Expression | Result | Explanation |
| --- | --- | --- |
| `Checkpoint.class.isInterface()` | `true` | An annotation type is a form of interface |
| `Checkpoint.class.isAnnotation()` | `true` | This is a type declared with `@interface` |
| `Annotation.class.isInterface()` | `true` | `Annotation` is an ordinary JDK interface |
| `Annotation.class.isAnnotation()` | `false` | `Annotation` is not an annotation type |
| `Annotation.class.isAssignableFrom(Checkpoint.class)` | `true` | The `Checkpoint` type is a subtype of `Annotation` |

Note: `Class.isAssignableFrom` checks **the type compatibility relationship** between two `Class` objects. It does not ask whether a specific class is **annotated** with an annotation. To find out which annotations a declaration carries, you must use APIs on `AnnotatedElement`, such as `Class.getAnnotation(...)` or `isAnnotationPresent(...)`.

### Standalone Java 17 Example

Create a single file **`AnnotationTypeRelationDemo.java`** with the following content:

~~~java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Checkpoint {
    String value();
    int order() default 1;
}

@Checkpoint("ready")
class FirstJob {
}

@Checkpoint(value = "ready", order = 1)
class SecondJob {
}

public class AnnotationTypeRelationDemo {
    public static void main(String[] args) {
        System.out.println("Checkpoint is interface: "
                + Checkpoint.class.isInterface());
        System.out.println("Checkpoint is annotation: "
                + Checkpoint.class.isAnnotation());
        System.out.println("Annotation is annotation: "
                + Annotation.class.isAnnotation());
        System.out.println("Checkpoint extends Annotation: "
                + Annotation.class.isAssignableFrom(Checkpoint.class));

        Checkpoint first = FirstJob.class.getAnnotation(Checkpoint.class);
        Checkpoint second = SecondJob.class.getAnnotation(Checkpoint.class);

        Annotation common = first;
        System.out.println("Annotation type: "
                + common.annotationType().getSimpleName());
        System.out.println("Value: " + first.value());
        System.out.println("Order: " + first.order());
        System.out.println("Equal values: " + first.equals(second));
        System.out.println("Equal hash codes: "
                + (first.hashCode() == second.hashCode()));
    }
}
~~~

Compile/run with Java 17+:

~~~bash
javac AnnotationTypeRelationDemo.java
java AnnotationTypeRelationDemo
~~~

Resulting **stdout**:

~~~text
Checkpoint is interface: true
Checkpoint is annotation: true
Annotation is annotation: false
Checkpoint extends Annotation: true
Annotation type: Checkpoint
Value: ready
Order: 1
Equal values: true
Equal hash codes: true
~~~

Part-by-part explanation:

1. The four `Class` checks confirm the **type** relationship between `Checkpoint` and `Annotation`.
2. `@Retention(RUNTIME)` retains the information long enough for `getAnnotation(Checkpoint.class)` to read it in the running program.
3. The variable `first` has type `Checkpoint`, so it can invoke the self-declared elements `value()` and `order()` along with the methods provided by `Annotation`.
4. The statement `Annotation common = first;` is valid because every value of type `Checkpoint` conforms to the parent type `Annotation`. On the `common` variable, you can use the common contract such as `annotationType()`; to call `value()`, you need a variable or a cast to `Checkpoint`.
5. `FirstJob` and `SecondJob` attach the annotation using two different syntaxes, but they have **the same type and the same element values** (`value = "ready"`, `order = 1`), so the two annotation objects are equal according to `equals`, and their `hashCode` values are also equal.

The example uses two annotated classes to illustrate that **equality of annotation values does not mean the two annotated classes are the same class**. `FirstJob.class == SecondJob.class` is still `false`.

## 4. What Does the `java.lang.annotation.Annotation` Contract Include?

`java.lang.annotation.Annotation` resides in the `java.lang.annotation` package and declares the common contract for objects representing annotations. The key methods are:

| Method | Meaning |
| --- | --- |
| `Class<? extends Annotation> annotationType()` | Returns **the annotation type represented** by the object |
| `boolean equals(Object other)` | Compares **the annotation type and the values of all corresponding elements** |
| `int hashCode()` | Computes the hash code according to the rules specified for annotation elements |
| `String toString()` | Returns a string describing the annotation; detailed formatting depends on the implementation |

`equals`, `hashCode`, and `toString` share names with the familiar methods on `Object`, but the `Annotation` API **further specifies a concrete contract** for how an annotation is represented.

### 4.1. `annotationType()` Differs from `getClass()`

Suppose we have:

~~~java
Checkpoint checkpoint = FirstJob.class.getAnnotation(Checkpoint.class);
~~~

Distinguish between:

- `checkpoint.annotationType()` returns **`Checkpoint.class`**, which is the metadata kind that the object represents.
- `checkpoint.getClass()` returns the **actual implementation class** of the object. That class is provided by the runtime/library; implementation details depend on the environment and **are not guaranteed to be `Checkpoint.class`**.

Common JDKs may use proxy objects or internal mechanisms to represent annotations. Application logic should rely on `annotationType()` when determining the annotation type, rather than relying on the runtime class name or assuming a specific implementation.

For example:

~~~java
Annotation annotation = FirstJob.class.getAnnotation(Checkpoint.class);

if (annotation.annotationType() == Checkpoint.class) {
    System.out.println("Đúng kiểu Checkpoint");
}
~~~

This snippet is **illustrative code** that can be placed inside the `main` method of the example above; when executed, it prints:

~~~text
Đúng kiểu Checkpoint
~~~

The condition using `==` between `Class` objects is appropriate for identifying the exact same loaded type.

### 4.2. `equals()` Is Content-Based, Not Object-Address-Based

Two annotations are considered equal when:

- They represent **the same annotation type**.
- The values of **all elements with the same name** are equal according to the annotation contract.
- For array-typed elements, the array contents are compared using the corresponding `Arrays.equals`, not merely by comparing the two array references.

Default values are also included. For example, `@Checkpoint("ready")` and `@Checkpoint(value = "ready", order = 1)` are equivalent because `order()` has an effective value of `1` in both.

You should not use `==` to check **whether two annotation reads have the same content**. `==` only compares object reference identity. The contract guaranteed to compare annotation semantics is `equals()`.

### 4.3. `hashCode()` Maintains Consistency with `equals()`

The Java contract specifies that an annotation's hash is based on **the sum of the contributions of its elements**, where each element has a calculation based on its name and value (including `default` values). Therefore, annotations with `equals() == true` must have the same `hashCode()`.

Practical consequence: if you use annotation objects as keys in a `HashMap` or elements in a `HashSet`, equality behavior follows **annotation values** rather than object identity. However, do not infer from equal hash codes that the contents are definitely equal: collisions can still occur.

### 4.4. `toString()` Should Only Be Used for Display, Not Arbitrary Parsing

An implementation might display an annotation in a form such as `@package.Checkpoint(value="ready", order=1)`. However, the element order, formatting, and other details **are not a stable data exchange format guaranteed by all implementations**. When you need to read information, call `annotationType()` and the specific element methods.

## 5. Why Is `Annotation` Not “the Elements” of a Custom Annotation?

A common confusion is seeing that `Checkpoint` extends `Annotation` and then thinking that the methods `annotationType()`, `equals()`, `hashCode()`, and `toString()` are also elements that must be filled in when writing:

~~~java
@Checkpoint("ready")
class Sample {
}
~~~

**That is not the case.** In the JLS, **annotation elements are only the elements explicitly defined by the `@interface` declaration itself**. In this example:

~~~java
@interface Checkpoint {
    String value();
    int order() default 1;
}
~~~

We have exactly **two elements**:

- `value()`: required, unless the usage site provides it.
- `order()`: has `default 1`, so it may be omitted at the usage site.

`annotationType()`, `equals()`, and `hashCode()` are not elements, even though a `Checkpoint` object has the corresponding methods.

That is why `@Checkpoint(annotationType = ...)` is invalid: `annotationType` is not an element declared in `Checkpoint`. The names `equals`, `hashCode`, `toString`, and `annotationType` are also not valid names for a custom annotation to redefine as annotation elements.

This keeps the metadata model clear: **the elements of an annotation type are configuration data**, while **the methods of `Annotation` are the common interface for all annotation objects**.

## 6. Using `Annotation` as a Common Type When Processing Metadata

When you know in advance which annotation to look for, you can keep the specific type:

~~~java
Checkpoint checkpoint =
        FirstJob.class.getAnnotation(Checkpoint.class);

String phase = checkpoint.value();
~~~

This is **an excerpt that depends on the `Checkpoint` and `FirstJob` declarations in the full example**.

When writing tools that need to traverse **many different annotation types**, using the common `Annotation` type is more suitable:

~~~java
import java.lang.annotation.Annotation;

class AnnotationInspector {
    static void inspect(Class<?> type) {
        for (Annotation annotation : type.getDeclaredAnnotations()) {
            System.out.println(annotation.annotationType().getSimpleName());
        }
    }
}
~~~

This snippet is a helper, not a standalone program because it lacks `main`. If you add the call `AnnotationInspector.inspect(FirstJob.class);` to `main` in the Section 3 example, it prints:

~~~text
Checkpoint
~~~

Each element in the `Annotation[]` array represents an annotation directly present on the inspected class. Thanks to the `Annotation` contract, a tool can identify **the annotation kind** even without declaring variables for each individual type.

A practical way to handle this:

~~~java
for (Annotation annotation : FirstJob.class.getDeclaredAnnotations()) {
    if (annotation instanceof Checkpoint checkpoint) {
        System.out.println("Checkpoint: " + checkpoint.value());
    }
}
~~~

This is also a snippet that can be placed inside `main` of the Section 3 example. In Java 17, **pattern matching for `instanceof`** as shown above is a supported feature. The printed output is:

~~~text
Checkpoint: ready
~~~

Thus, a framework can traverse metadata under the parent type `Annotation`, and only use the specific element API once it identifies the kind it needs to handle.

### Two Boundaries to Keep in Mind

**Boundary 1: the root type does not execute business logic on its own.** The fact that annotation types all extend `Annotation` does not cause `@Checkpoint` to trigger an action automatically. Scanning and processing code must be written or configured separately.

**Boundary 2: runtime reflection does not see every annotation.** Calls like `getAnnotation(...)` are only appropriate when the annotation is available for reflection at runtime, typically via `@Retention(RUNTIME)`. An annotation used only at compile time can be detected by an annotation processor through the APIs of `javax.annotation.processing` and `javax.lang.model`, but it does not necessarily have a runtime `Annotation` object to read.

Specifically, `javax.lang.model.element.AnnotationMirror` is **the annotation model in source-code/compile-time processing tools**, not another name for a runtime `java.lang.annotation.Annotation` object. They serve different phases.

## 7. Distinguishing Type Inheritance from Metadata Inheritance

We have two completely different axes:

**Type axis:**

~~~text
Annotation
    ^
    |
Checkpoint
~~~

This axis always exists because of the language rule when declaring `@interface Checkpoint`.

**Annotated declaration axis:**

~~~text
@Checkpoint("ready")
class Parent {
}

class Child extends Parent {
}
~~~

`Child` **does not automatically become** a `Checkpoint`; nor is `Parent` a subtype of `Annotation` just because it is annotated. The question of “whether looking up metadata on a subclass sees an annotation on the superclass” is governed separately by `@Inherited`, the reflection APIs called, and the kind of element receiving the annotation.

For instance, `@Inherited` can affect annotation lookup on a subclass through the appropriate API, but it does not change the `Checkpoint extends Annotation` relationship; conversely, the `Checkpoint extends Annotation` relationship does not automatically propagate metadata from `Parent` down to `Child`.

Similarly, the fact that an interface is a superinterface of a class does not mean annotations attached to that interface are automatically treated as annotations present on the implementing class. **Type inheritance** and **annotation metadata inheritance** are two different mechanisms.

## 8. Some Common Misconceptions

| Claim | Correct Conclusion |
| --- | --- |
| “`@interface` is just a labeling syntax, not a Java type.” | `@interface` declares an annotation type, which is a special kind of interface. |
| “To inherit from `Annotation`, you must declare `extends Annotation`.” | No. The direct inheritance relationship is implicitly defined by the compiler, and the syntax does not permit writing `extends`. |
| “`java.lang.annotation.Annotation` is also an annotation type.” | No. It is an ordinary root interface; `Annotation.class.isAnnotation()` returns `false`. |
| “Attaching `@Checkpoint` to a class makes the class implement `Annotation`.” | No. The relationship with `Annotation` belongs to **the `Checkpoint` type**, not to the annotated class. |
| “`annotationType()` is an element that must be passed like `value()`.” | No. `annotationType()` is a method from the `Annotation` contract; elements are only what `@interface` explicitly declares. |
| “`getClass()` is guaranteed to return `Checkpoint.class`.” | No. The implementation of the annotation object depends on the runtime; use `annotationType()` to get the metadata type. |
| “Two annotations on two different classes are always unequal according to `equals`.” | No. With the same type and corresponding elements having equal values, the annotation objects are equivalent. |
| “You can use `getAnnotation` to read every annotation in source code.” | No. Reflection depends on runtime retention; compile-time processing has a different model and API. |

## 9. Self-Check

**Question 1.** Why does `Annotation.class.isAssignableFrom(Checkpoint.class)` return `true` even though `@interface Checkpoint` does not contain `extends Annotation`?

**Hint:** The Java Language Specification defines the direct superinterface of every annotation type as `java.lang.annotation.Annotation`.

**Question 2.** Between the following two `Class` objects, which one has `isAnnotation() == true`: `Annotation.class` or `Checkpoint.class`?

**Answer:** Only `Checkpoint.class`.

**Question 3.** Can you call `checkpoint.value()` after writing `Annotation checkpoint = FirstJob.class.getAnnotation(Checkpoint.class);`?

**Answer:** It cannot be called directly because the static type `Annotation` does not declare `value()`. You can keep the variable typed as `Checkpoint` from the start, or perform an appropriate check/cast before calling it.

**Question 4.** Given `@Checkpoint("ready")` and `@Checkpoint(value = "ready", order = 1)` of the same annotation type, are they equal when compared with `equals()`?

**Answer:** Yes, because the effective values of all elements are equal, including `order` obtained from `default`.

**Question 5.** If you want to know what type an annotation actually belongs to in a metadata-scanning tool, should you call `annotation.annotationType()` or rely on `annotation.getClass().getName()`?

**Answer:** Use `annotationType()` because it is the method defined to return the annotation type; the implementation class is a runtime detail.

**Practice Exercise:** Run `AnnotationTypeRelationDemo.java`. Change `@Checkpoint(value = "ready", order = 1)` on `SecondJob` to `@Checkpoint(value = "ready", order = 2)`. Predict the two lines `Equal values` and `Equal hash codes`, then compare with the execution output. You should conclude with certainty that `equals()` is `false` because the `order` element differs; you should not infer that `hashCode()` is always different for every pair of unequal annotation values.

## 10. Standard Reference Documentation

- [JLS §9.6 — Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se23/html/jls-9.html#jls-9.6): specifies that an annotation type is a special interface and has `Annotation` as its direct superinterface.
- [Java SE 17 API — `java.lang.annotation.Annotation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html): the contract for `annotationType()`, `equals()`, `hashCode()`, and `toString()`.
- [Java SE 17 API — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): methods for reading annotations on program elements, including `getAnnotation`, `getDeclaredAnnotations`, and `isAnnotationPresent`.

When you encounter a type declared with `@interface`, remember that it is both **a special kind of interface** with `Annotation` as its parent type and a definition of **a metadata structure** with its own elements. These two aspects combine so that tools and frameworks can recognize, retrieve, and process annotations using consistent APIs.
