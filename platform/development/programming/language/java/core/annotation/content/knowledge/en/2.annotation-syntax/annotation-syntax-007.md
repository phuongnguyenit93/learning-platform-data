# Combining Multiple Annotations on a Single Declaration in Java

## 1. Meaning and Basic Syntax

In Java, **a single declaration can carry multiple annotations of different types at the same time**. Each annotation adds its own piece of information or requirement to the class, method, field, constructor, parameter… to which it is permitted to apply. This is a common way to attach multiple aspects (for example: API description, authorization, testing, framework processing) to the same element.

The syntax is to write the annotations one after another directly before the declaration. You can place each annotation on its own line or multiple annotations on the same line:

```java
@Deprecated
@Override
public String toString() {
    return "example";
}
```

Here both annotations are attached to **the toString() method**. **@Override** instructs the compiler to check whether the method actually overrides/implements a method from a supertype; **@Deprecated** marks the method as no longer recommended for use. The two annotations have different meanings and coexist on a single declaration.

The syntax `@A @B` **does not mean** that A wraps B or that B runs before A. To Java, they are separate annotations associated with the same element; actual behavior also depends on the compiler, annotation processor, library, or framework reading them.

## 2. Conditions for a Valid Combination

### 2.1. Each Annotation Must Be Permitted at That Location

A custom-declared annotation can use the **@Target** meta-annotation to specify valid locations. For example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface OnlyMethod {}

@Target({ElementType.METHOD, ElementType.CONSTRUCTOR})
@interface OnCallable {}

class Sample {
    @OnlyMethod
    @OnCallable
    void execute() {}

    @OnCallable
    Sample() {}
}
```

- Both **@OnlyMethod** and **@OnCallable** allow METHOD, so placing them simultaneously on execute() is valid.
- **@OnCallable** also allows CONSTRUCTOR, so it can be attached to a constructor.
- If you attach **@OnlyMethod** to a class, field, or constructor, there will be a **compilation error**, because that location is not in @Target.

Some common values: **TYPE** (class, interface, enum, annotation type, record), **METHOD**, **FIELD**, **CONSTRUCTOR**, **PARAMETER**, **LOCAL_VARIABLE**, **ANNOTATION_TYPE**, **TYPE_PARAMETER**, **TYPE_USE**, and **RECORD_COMPONENT**. It is necessary to distinguish an annotation on a *declaration* from an annotation on a *used type*: for example, an annotation for METHOD is not necessarily usable before a type at a TYPE_USE location.

If an annotation does not declare @Target, it can essentially be used on the permitted declaration locations for annotations; that does not automatically turn it into an annotation for every TYPE_USE or type parameter location.

### 2.2. Different Types and the Same Type Are Two Different Cases

Annotations of **different types** can generally be placed next to each other, provided each one is valid on that element:

```java
@Override
@Deprecated
public String toString() {
    return "legacy";
}
```

On the contrary, writing **the same type twice** such as `@Tag("fast")` and `@Tag("smoke")` on the same declaration is only valid when that annotation type is declared **@Repeatable** (see section 5). Do not confuse “multiple annotations of different types” with “repeating a single annotation”.

### 2.3. Annotations Carry Different Retention Levels

**@Retention** determines how long annotation data is retained:

| RetentionPolicy | Meaning | Readable via reflection at runtime? |
| --- | --- | --- |
| SOURCE | For processing at source/compile time, not retained in the class file | No |
| CLASS | Retained in the class file, not provided to runtime reflection by default | No |
| RUNTIME | Retained in the class file and can be read via reflection at runtime | Yes |

Combining multiple annotations **does not change the @Retention of each one**. For example, when placing **@Override** alongside a custom-defined annotation with RUNTIME on a method, reflection can see the custom-defined annotation, but cannot see @Override because @Override only has SOURCE retention.

## 3. Complete Java 17+ Example: Two Annotations on the Same Method

Create the file **AnnotationCombinationDemo.java** with the entire contents below:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Route {
    String path();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface RequireRole {
    String value();
}

public class AnnotationCombinationDemo {
    @Route(path = "/reports")
    @RequireRole("ADMIN")
    public String report() {
        return "Bao cao";
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Method method = AnnotationCombinationDemo.class
                .getDeclaredMethod("report");

        Route route = method.getAnnotation(Route.class);
        RequireRole role = method.getAnnotation(RequireRole.class);

        System.out.println(route.path());
        System.out.println(role.value());
        System.out.println(new AnnotationCombinationDemo().report());
    }
}
```

Run from the directory containing the file with JDK 17 or later:

```bash
javac AnnotationCombinationDemo.java
java AnnotationCombinationDemo
```

Exact stdout output:

```text
/reports
ADMIN
Bao cao
```

**Step-by-step analysis:**

1. **@Route** describes the logical path for report(); **@RequireRole** describes the required role. Both annotations have @Target(METHOD), so they can be placed together on report().
2. **@Retention(RUNTIME)** on each annotation enables the Method class to read them at runtime.
3. **getDeclaredMethod("report")** finds the corresponding Method object; **getAnnotation(Route.class)** and **getAnnotation(RequireRole.class)** read two separate pieces of metadata from the same Method.
4. A direct call to **report()** still returns the string “Bao cao”. Merely attaching **@Route** or **@RequireRole** **does not automatically create an HTTP endpoint, does not automatically check ADMIN, and does not automatically block the call**. To have that behavior, code or a framework must read the metadata and then execute the corresponding rules.

Note: the **Route** and **RequireRole** annotations in the example are two custom-defined types from this lesson, not built-in Spring annotations.

## 4. Combining Built-In Annotations and Framework Annotations

The most familiar example in Java Core is placing **@Override** together with **@Deprecated** on a method:

```java
class Parent {
    public String name() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    @Deprecated(since = "17")
    public String name() {
        return "child";
    }
}
```

**@Override** is checked at the compilation step, while **@Deprecated** marks the API as deprecated, so that tools/compilers can issue warnings when other code uses the method. Placing two annotations does not cause the method to be called twice or cause @Deprecated to interfere with the override mechanism.

In the Spring or Jakarta Validation ecosystem, it is also common to see a declaration with multiple annotations serving multiple roles. For instance, a method can be simultaneously marked with a request-mapping annotation and an access-control annotation, **if both are valid on METHOD and the corresponding processing components have been configured**. How frameworks combine conditions, choose proxies, determine interceptor order, and handle conflicts are **framework rules**, not determined by the order in which annotations are written in Java source code.

## 5. Distinguishing from @Repeatable: Repeating the Same Annotation Type

If you need to attach *multiple values of the same annotation type* to a declaration, declare that type as **@Repeatable** along with a container annotation. The example below is illustrative code that can be placed into a Java file with the appropriate imports:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Tags {
    Tag[] value();
}

class TaggedTask {
    @Tag("fast")
    @Tag("smoke")
    void execute() {}
}
```

Here **@Tag("fast")** and **@Tag("smoke")** are **two uses of the same Tag type**, permitted by **@Repeatable(Tags.class)**. The **Tags** container holds a Tag array; the container must satisfy target and retention constraints compatible with the repeatable annotation.

With **RUNTIME retention**, you can retrieve all Tags using **method.getAnnotationsByType(Tag.class)**. When using repeatable annotations, you should prefer **getAnnotationsByType** instead of assuming **getAnnotation(Tag.class)** will always return the repeated Tags: repeated annotations are typically represented through the container in declaration/runtime metadata form.

In contrast, attaching **@Route** and **@RequireRole** in section 3 **does not require @Repeatable** because they are two different annotation types.

## 6. Order, Placement, and Scope of Effect

- **Declaration order:** Writing @Route before @RequireRole or vice versa does not dictate execution order. Do not infer processing order from the position of appearance in source or from the order returned by reflection in the annotation array.
- **Exactly one element:** Annotations written directly before a method attach to that method and do not automatically propagate to every parameter or every method of the class. To annotate a parameter, place the annotation on the **parameter declaration**, and the annotation type must allow PARAMETER.
- **Target compatibility:** If one annotation is only for TYPE and another is only for METHOD, you cannot place both on a METHOD and expect Java to automatically apply the TYPE one to the enclosing class.
- **Framework compatibility:** Java may allow multiple annotations to appear together syntactically, but a specific framework may add conditions, priorities, processing components, or report conflicts. You need to read the API contract of the annotation being used.
- **Independent retention:** An annotation that runs via an annotation processor at compile time is not necessarily still present for reflection to read at runtime. You must check the @Retention definition of each annotation.
- **No inherent behavior:** Annotations are metadata according to Java's mechanism; effects such as validation, transaction, security, routing, or logging require a compiler, tool, or runtime/framework to process them. Merely writing multiple annotations does not create a new processing mechanism.

A declaration can also carry meta-annotations when it itself **defines an annotation**, for example:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@interface Audited {}
```

Here **@Retention** and **@Target** both apply to the **@interface Audited** declaration to configure the *annotation type*; they do not mean that every method annotated with @Audited becomes a method that has @Retention or @Target.

## 7. Common Mistakes and How to Check

**Mistake 1 — Annotation has the wrong @Target.** An annotation meant only for FIELD is attached to a class or method. The compiler reports that the annotation is not applicable to that element. Open the @Target definition, then move the annotation to the correct location or adjust the annotation declaration if you own that type.

**Mistake 2 — Writing the same annotation twice without @Repeatable.** Two @Tag lines with different values are still the same type; fix this with @Repeatable and a valid container if multiple values are truly needed. If the two aspects are independent, it is usually better to use two annotation types with distinct meanings.

**Mistake 3 — Expecting reflection to see SOURCE/CLASS annotations.** RUNTIME retention is required to use common reflection APIs such as getAnnotation/getAnnotationsByType at runtime. Do not try to infer from an annotation's appearance in source code that reflection can definitely read it.

**Mistake 4 — Thinking line order determines precedence.** @A followed by @B is not equivalent to “run A before B”; to know the order, you must inspect the tool/framework processing the annotation and the relevant configuration.

**Mistake 5 — Assuming all annotations on METHOD are business-compatible.** Check the documentation of each annotation, preconditions, and processing mechanism. For example, two different AOP mechanisms may both be valid in Java yet follow separate interceptor ordering.

**Mistake 6 — Confusing annotations with function calls.** The example in section 3 only allows code to actively read metadata. No router or security layer is automatically generated by Java Core.

**Mistake 7 — Missing import or duplicate annotation names.** Two libraries may both define a short name like @Transactional. Check that the right package is imported; if necessary, use the fully qualified name to avoid confusing APIs or behavior.

## 8. Reinforcement Exercises

1. Add a custom-defined annotation **@Audit(event = "READ_REPORT")** to the report() method in section 3. Set **@Target(METHOD)** and **@Retention(RUNTIME)**, then use reflection to print the event. The output should have an additional READ_REPORT line while the output of the three existing lines remains unchanged.
2. Change the @Target of **@RequireRole** to **ElementType.TYPE** and try compiling. Explain why Java rejects keeping @RequireRole on report(), then try moving it to the class declaration to observe the difference in placement.
3. For the @Repeatable example, try changing it to a Tag annotation without @Repeatable while keeping two @Tag annotations on execute(). Identify the compilation error and the reason Java distinguishes repeating the same type from combining different annotation types.

**Key takeaway:** To place multiple annotations on the same declaration, you must accurately identify the **annotated element**, ensure **each annotation's @Target allows that element**, understand the **@Retention** of each type, and read the documentation of the mechanism that processes them. Only when repeating **the same type** do you need to consider **@Repeatable**.
