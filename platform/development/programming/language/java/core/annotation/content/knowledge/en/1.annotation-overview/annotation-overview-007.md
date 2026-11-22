# Foundational Knowledge and Learning Sequence for Annotations in Java Core

Annotations in Java are a way to attach structured **metadata** to source code. To understand annotations in Spring, JPA, or testing libraries, you first need to know which stage Java language annotations persist to, who reads them, and what mechanism actually produces behavior.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain that an annotation is metadata, not self-executing logic.
- Read built-in annotations and declare your own annotations using `@interface`.
- Distinguish between `@Target`, `@Retention`, `SOURCE`, `CLASS`, and `RUNTIME`.
- Create a Java 17+ program that reads annotations using Reflection.
- Distinguish between compiler checks, annotation processors, and runtime processing.
- Determine your own learning sequence so that you have a solid foundation when reading framework annotations later.

## 2. What Is an Annotation?

A familiar example:

~~~java
@Override
public String toString() {
    return "Hello";
}
~~~

`@Override` notifies the **compiler** that the method must override/implement a matching method. If the signature is wrong, `javac` reports an error. `@Override` itself does not contain the validation logic and does not call `toString()` on its own.

You should ask four questions whenever you encounter any annotation: **where is it attached → how long is it retained → who reads it → what does the reader do?**

| Component | Timing | What It Can Do |
| --- | --- | --- |
| Java compiler | At compile time | Check `@Override`, handle deprecation warnings, apply `@SuppressWarnings` |
| Annotation processor | At compile time | Validate constraints, generate code or resources |
| Application/library using Reflection | At runtime | Read annotations with `RUNTIME` retention, then execute custom logic |
| Bytecode inspection tool | Post-compilation | Analyze annotation information in `.class` files |

**An annotation does not execute logic on its own.** If you create `@Log` yourself and attach it to a method, no logs will appear unless you build or use a processor that understands that annotation. Annotations differ from comments in that their syntax and types are checked and they can be processed by tools; they also do not replace methods, interfaces, or algorithms.

## 3. Syntax and Built-in Annotations

Some usage forms:

~~~java
@Override
@Deprecated(since = "17")
@SuppressWarnings({"rawtypes", "unchecked"})
~~~

The example above shows three standalone annotations to illustrate syntax, not a complete Java declaration. The syntax `@Name` takes no arguments; `@Name(element = value)` passes an element; an element named `value` can be shortened to `@Name(value)` when appropriate.

Foundational annotations:

- `@Override`: the compiler checks method overriding/implementation.
- `@Deprecated`: marks an API as no longer recommended for use, but does not block calls on its own.
- `@SuppressWarnings`: instructs the compiler to suppress supported warning categories within the specified scope; it does not fix the underlying issue.
- `@FunctionalInterface`: instructs the compiler to verify that the interface satisfies the functional interface contract.

These are Java Core annotations. Spring/JPA annotations may have identical syntax, but their behavior depends on the library/framework code that processes them.

## 4. Defining Custom Annotations with `@interface`

~~~java
@interface LessonInfo {
    String author();                // Required when used.
    int level() default 1;         // Has a default value.
    String[] topics() default {};  // Array element.
}
~~~

Annotation elements have a syntax similar to parameterless methods: `author()`, `level()`, `topics()`. They declare **metadata attributes**, not execution bodies. `default` allows users to omit specifying that element; an element without `default` is required.

Usage example:

~~~java
@LessonInfo(author = "Team Java", level = 2, topics = {"core", "metadata"})
class FirstLesson {}
~~~

Valid return types for an element: primitive types, `String`, `Class`, `enum` types, an annotation type, or one-dimensional arrays of these types. Forms such as `List<String>`, `Map`, arbitrary objects, multidimensional arrays, or elements with parameters/`throws` are invalid. Values must be usable at compile time; you cannot pass the result of a runtime method call into an annotation. `null` is also not a valid value for an element.

If an annotation defines an element named `value`, you can write:

~~~java
@interface Label {
    String value();
}

@Label("intro")
class Intro {}
~~~

`@Label("intro")` is shorthand for `@Label(value = "intro")`.

## 5. The First Two Meta-Annotations to Learn

A meta-annotation is an annotation used to describe another **annotation type**.

### 5.1. `@Target` Specifies Where an Annotation Can Be Attached

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@interface ReviewTag {
    String value();
}
~~~

`@ReviewTag` can be attached to type or method declarations, but not to fields/parameters under this `@Target` declaration. Common `ElementType` values:

| Value | Applies To |
| --- | --- |
| `TYPE` | Class, interface, enum, and annotation type declarations |
| `METHOD` | Method declarations |
| `FIELD` | Field declarations |
| `PARAMETER` | Method/constructor parameters |
| `CONSTRUCTOR` | Constructors |
| `LOCAL_VARIABLE` | Local variables |
| `ANNOTATION_TYPE` | Annotation type declarations |
| `TYPE_PARAMETER` | Type parameters such as `<T>` |
| `TYPE_USE` | Locations where a type is used (including within some generics) |

`TYPE` and `TYPE_USE` are not synonymous: declaring a class is different from using a type in a variable, return type, or generic. When `@Target` is omitted, an annotation can be used in appropriate declaration contexts, but you should not assume it applies to every `TYPE_USE` location.

### 5.2. `@Retention` Specifies Metadata Lifetime

| Policy | Present in Source | Present in `.class` | Readable by Standard Runtime Reflection? |
| --- | --- | --- | --- |
| `SOURCE` | Yes | No | No |
| `CLASS` | Yes | Yes | No |
| `RUNTIME` | Yes | Yes | Yes |

- `SOURCE`: the information is only needed during source processing/compilation.
- `CLASS`: stored in bytecode so `.class`-reading tools can process it, but not exposed through standard Reflection.
- `RUNTIME`: retains metadata to be queried via Reflection at runtime.

**By default, an annotation without a `@Retention` declaration has the `CLASS` policy.** Being written in source code does not mean `getAnnotation(...)` can find it at runtime.

Example:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface AuditLabel {
    String value();
}
~~~

Additional meta-annotations to learn next when needed: `@Documented` includes the annotation in Javadoc; `@Inherited` supports querying superclass annotations on a **class declaration** according to Java rules, without automatically inheriting annotations attached to methods, fields, or interfaces; `@Repeatable` allows applying the same annotation multiple times at a single location with an appropriate container annotation.

## 6. Runnable Java 17+ Example: Annotations and Reflection

Create the **`AnnotationTour.java`** file below. All declarations are in the same file; only `AnnotationTour` is public.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface LessonInfo {
    String author();
    int level() default 1;
    String[] topics() default {};
}

@LessonInfo(author = "Team Java", topics = {"metadata", "reflection"})
class Lesson {
    @LessonInfo(author = "Team Java", level = 2)
    public void run() {
        System.out.println("Lesson is running");
    }
}

public class AnnotationTour {
    public static void main(String[] args) throws ReflectiveOperationException {
        LessonInfo onClass = Lesson.class.getAnnotation(LessonInfo.class);
        LessonInfo onMethod = Lesson.class
                .getDeclaredMethod("run")
                .getAnnotation(LessonInfo.class);

        System.out.println(onClass.author());
        System.out.println(onClass.level());
        System.out.println(Arrays.toString(onClass.topics()));
        System.out.println(onMethod.level());
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac AnnotationTour.java
java AnnotationTour
~~~

Exact stdout:

~~~text
Team Java
1
[metadata, reflection]
2
~~~

Explanation: the annotation on `Lesson` has `author = "Team Java"`, `topics` with two elements, while `level` takes the default value `1`. The annotation on `run()` overrides `level` to `2`. `Lesson.class.getAnnotation(...)` reads from the class; `getDeclaredMethod("run").getAnnotation(...)` reads from the method. There is no `new Lesson().run()`, so the line `Lesson is running` **does not appear**. Reading metadata does not invoke the annotated method.

Try changing `@Retention(RUNTIME)` to `@Retention(CLASS)`. The program still compiles, but `getAnnotation` returns `null`; this code will throw a `NullPointerException` when accessing `onClass.author()`. When writing real code, you should check whether an annotation is present (for example, using `isAnnotationPresent(...)` or comparing against `null`) before reading its elements.

## 7. Compile-Time Annotation Processing vs. Runtime Reflection

**Compile-time processing:** an annotation processor (typically extending `javax.annotation.processing.AbstractProcessor`) is invoked by the compiler when properly configured/discovered. It uses the compiler's element model to validate, report errors/warnings, and generate source files, classes, or resources. The processor runs at compile time and does not require calling `main()`. Having `RUNTIME` retention is **not a requirement** for a processor to read an annotation, because the processor participates while the compiler is processing the code.

**Runtime Reflection:** running code calls APIs such as `Class.getAnnotation(...)`, `Method.getDeclaredAnnotations()`, or `isAnnotationPresent(...)`. With standard Reflection APIs, an annotation must have `RUNTIME` retention to be present. However, the part that decides what action to take is still written by the application or library.

~~~text
.java source
   |
   +--> javac / annotation processor
   |      checks; may generate code, errors, or resources
   |
   +--> .class file / JVM class loading
               |
               +--> runtime code using Reflection
                       |
                       +--> reads RUNTIME annotations
                       +--> determines behavior if a processor is present
~~~

A framework may combine Reflection, classpath scanning, or bytecode analysis. At the Java Core level, what you need to understand is the boundary between **metadata** and the **component that processes metadata**.

## 8. Recommended Learning Sequence

| Step | What to Learn | Self-Check |
| --- | --- | --- |
| **1. Recognition** | Role of metadata, `@...` syntax, distinguishing annotations from comments and method calls | Explain why `@Override` checks the signature without executing the method |
| **2. Built-in** | `@Override`, `@Deprecated`, `@SuppressWarnings`, `@FunctionalInterface` | Intentionally declare an invalid override; observe the compiler error; test a functional interface |
| **3. Declaration** | `@interface`, required elements, `default`, `value`, valid types/arrays | Write `@LessonInfo` yourself with a few elements |
| **4. Meta-annotations** | `@Target`, `@Retention`; effects of `TYPE`/`METHOD` and `CLASS`/`RUNTIME` | Change target and retention, and compare compiler errors and Reflection values |
| **5. Reflection** | `Class`, `Method`, `getAnnotation`, `getDeclaredAnnotation`, `isAnnotationPresent` | Run `AnnotationTour.java` and predict stdout before running |
| **6. Extensions** | `@Documented`, `@Inherited`, `@Repeatable`, `TYPE_USE` | Test subclasses, repeatable annotations, and distinguish declaration sites from type-use sites |
| **7. Processing/framework** | Compile-time processors vs. runtime processors/Reflection | Sketch the path from `@Something` to the code that actually processes it |

Only move to the next step when you can answer: **where** is the annotation attached, **how long** is it retained, **who reads it**, and **what action does reading it lead to**? This sequence helps you avoid memorizing framework annotation names without understanding what happens.

## 9. Common Mistakes

1. **Thinking annotations create logic on their own.** `@Log` does not write logs without a processor. Find where the framework or application actually reads the metadata.
2. **Using `CLASS` retention and then reading via runtime Reflection.** When you get `null`, check the retention policy and verify that you are querying the exact class, method, or field element.
3. **Attaching an annotation to the wrong target.** `@Target(METHOD)` cannot be used on a field; `TYPE` does not implicitly include all `TYPE_USE` locations.
4. **Declaring an element with an invalid type.** `List<String>` or `default null` is not valid. Use types and arrays permitted by Java.
5. **Misunderstanding `@Inherited`.** It does not mean annotations on methods, fields, or interfaces automatically propagate down to all subclasses. Use `getDeclaredAnnotation` and `getAnnotation` to observe the difference on classes when appropriate.
6. **Confusing annotation processors with Reflection.** Distinguish between compile time and runtime before deciding on the retention policy and reading API.
7. **Overusing `@SuppressWarnings`.** Only suppress warnings after you understand the root cause; an annotation does not make an invalid cast or unsafe logic correct.

## 10. Practice Exercises

1. Create a subclass, intentionally place `@Override` on a misspelled method name, and predict and explain the error from `javac`.
2. Create `@Owner` restricted to `TYPE`, with a required `String value()` and `int priority() default 0`. Try both `@Owner("backend")` and the named-element form.
3. Create `@Marker` with `RUNTIME` retention on a method, read it via Reflection, and perform a safe `null` check. Switch to `CLASS` and compare the results.
4. Change `@Target` and try attaching the annotation to a class, method, field, and a `TYPE_USE` location. Record which cases compile and which do not.
5. Suppose a framework provides `@Route("/hello")`. Describe the components required for an HTTP request to actually invoke the annotated method; identify who reads the metadata and who invokes the method.

## 11. Checklist Before Learning Framework Annotations

- I can explain why attaching `@...` does not make code self-execute.
- I can distinguish between the compiler, an annotation processor, and runtime Reflection.
- I know that `@Target` restricts placement and `@Retention` restricts lifetime; the default is `CLASS`.
- I can write an annotation type with required elements, `default` values, and array elements.
- I can run a `RUNTIME` example with Reflection, accurately explain its stdout, and handle missing annotations.
- I know that when encountering a new annotation, I must look for its **processor** and execution rules rather than inferring behavior from its name.

Mastering the points above provides the foundation to continue studying annotations in Spring, JPA, and other Java libraries.
