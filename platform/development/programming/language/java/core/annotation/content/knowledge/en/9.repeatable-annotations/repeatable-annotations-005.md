# Repeated Syntax and Explicit Container Syntax of Repeatable Annotations in Java

Java allows applying **multiple annotations of the same type at a single location** when that annotation type is declared with **@Repeatable** (since Java 8). There are two common ways to write them:

**Repeated syntax:**

~~~java
@Tag("alpha")
@Tag("beta")
class Repeated {}
~~~

**Explicit container syntax:**

~~~java
@Tags({
    @Tag("alpha"),
    @Tag("beta")
})
class ExplicitContainer {}
~~~

Both approaches can represent the same set of values and produce the same result via **getAnnotationsByType(Tag.class)**. However, to understand the mechanism properly, you must distinguish between the **base annotation**, the **container annotation**, how javac creates a container **implicitly**, and the reflection API for reading **a single direct annotation** versus **all repeated annotations**.

This practical guide uses Java 17+, explains the container declaration rules, compares the syntaxes, inspects bytecode, covers combinations rejected by javac, and provides a standalone runnable example with verified stdout.

## 1. When Can Multiple Annotations of the Same Type Be Applied?

By default, repeating the same annotation type at the same location causes a compile-time error:

~~~java
@interface Label {
    String value();
}

// Invalid if Label has not been declared @Repeatable:
// @Label("a")
// @Label("b")
// class Item {}
~~~

Java does not automatically infer a "two labels" meaning from writing **@Label** twice. For this syntax to be valid, the Label type must specify a **containing annotation type** that can hold the Label values.

Complete declaration:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Repeatable(Tags.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}
~~~

Components:

- **Tag** is the annotation type **allowed to be repeated**. **@Repeatable(Tags.class)** applied on Tag indicates that **Tags** is the container type.
- **Tags** is another annotation type with the required element **Tag[] value()**. That element holds an array of Tag values.
- Both have **@Retention(RUNTIME)** so they can be read via reflection at runtime. If processed only at compile time, another appropriate retention can be used.
- **@Target(TYPE)** allows applying them to class/interface/enum/annotation type declarations. You need to coordinate the targets of Tag and Tags for the intended repetition location.
- **Tag.value()** is a String, so **@Tag("alpha")** is equivalent to **@Tag(value = "alpha")**.
- **Tags.value()** is **Tag[]**, a valid array element type in Java.

**@Repeatable is a meta-annotation of Tag, not something applied to the class that uses it.** It describes how the compiler and APIs recognize that an annotation type can appear multiple times.

## 2. Repeated Syntax: Each Base Annotation Is Written Separately

When you write:

~~~java
@Tag("alpha")
@Tag("beta")
class Repeated {}
~~~

two uses of **Tag** appear consecutively on the same class declaration. The name **Repeated** here is just an illustrative class name and is unrelated to any Java keyword.

According to JLS §9.7.5, when two or more annotations of the same repeatable type appear at a single location and the target conditions are valid, javac treats it **as if an implicit container annotation were present at that location**, with the original Tag annotations in the container's **value()** element.

You can visualize it as:

~~~text
In source:
    @Tag("alpha")
    @Tag("beta")
    class Repeated {}

Compiler interpretation:
    @Tags({
        @Tag("alpha"),
        @Tag("beta")
    })
    class Repeated {}
~~~

The diagram describes the **semantics**, not that javac has to modify the source file. The author still keeps the concise, readable syntax; the compiler is responsible for representing these annotations according to the container rules.

### Is the Order of Values Preserved?

**Yes.** The base annotations are placed in the **implicit container's value() array in left-to-right order** as they appear at the annotation site. For example:

~~~java
@Tag("first")
@Tag("second")
@Tag("third")
class Ordered {}
~~~

The Tag array in the corresponding container has the order **first, second, third**. With reflection using the ByType API, the order of the annotations found reflects that container rule. This is different from assuming that **every list of annotations on every Class has a fixed order**: ordering must be read according to the appropriate API contract.

**Writing the Tag annotations consecutively is not mandatory**, although writing them consecutively is a readable convention. The key point is that they appear together in **a single declaration context or type context** where Java allows repetition.

## 3. Explicit Container Syntax: Creating the Container Manually

The same data can be written as:

~~~java
@Tags({
    @Tag("alpha"),
    @Tag("beta")
})
class ExplicitContainer {}
~~~

Here, the code author **declares Tags directly**, rather than writing two independent Tag annotations at the class location. The Tag annotations are **inside the value of the Tags.value() element**.

You can write it using the full element-name syntax:

~~~java
@Tags(value = {
    @Tag(value = "alpha"),
    @Tag(value = "beta")
})
class ExplicitContainer {}
~~~

The two snippets above are equivalent in element-value. Because the element name is **value()**, Java allows omitting **value =** on both the container and each Tag.

### Container with One or Zero Elements

An explicit container does not have to contain two or more Tag annotations:

~~~java
@Tags({@Tag("single")})
class OneInsideContainer {}

@Tags({})
class EmptyContainer {}
~~~

**OneInsideContainer** has a direct **Tags** containing one Tag. **EmptyContainer** has a direct Tags, but **value()** is an empty array. When calling **getAnnotationsByType(Tag.class)** on EmptyContainer, the result is an **empty Tag[] array**, even though a **Tags** annotation is still present.

This differs from:

~~~java
@Tag("single")
class OneDirectTag {}

class NoTag {}
~~~

- **OneDirectTag** has one direct Tag; there is no need for the compiler to synthesize Tags, because there are not multiple Tag annotations to group.
- **NoTag** has neither Tag nor Tags.
- **EmptyContainer** has Tags, but no Tag inside.
- Both EmptyContainer and NoTag yield **getAnnotationsByType(Tag.class).length == 0**, but **getDeclaredAnnotation(Tags.class)** distinguishes them.

Therefore, *"no Tag found by the ByType API"* is not always the same as *"no container declared"*.

## 4. Comparing the Two Syntaxes by Source and Metadata

| Characteristic | Repeated syntax | Explicit container |
| --- | --- | --- |
| How it is written | **@Tag("a") @Tag("b")** | **@Tags({@Tag("a"), @Tag("b")})** |
| Which annotation does the author place directly on the class? | Two **Tag** annotations in source | One **Tags** annotation in source |
| Container in compilation semantics | Implicitly generated by the compiler when needed | Directly declared by the author |
| Order preservation | According to the order the Tag annotations are written | According to the element order of the Tags.value() array |
| Retrieving all Tag annotations with RUNTIME retention | **getAnnotationsByType(Tag.class)** | **getAnnotationsByType(Tag.class)** |
| Retrieving Tags directly via reflection | Can find the compiler-generated container | Finds the author-declared container |
| Switching syntax when data is equal | Can produce equivalent ByType results | Can produce equivalent ByType results |
| Can an empty container be written? | Cannot have "zero @Tag occurrences" and auto-generate a container | Yes: **@Tags({})** |
| What does it focus on? | Readability of individual labels, concise syntax | Clearly shows the containing array structure, convenient with some legacy code |

**You must not conclude that the two approaches are always identical in every respect.** The compiler only creates a container when multiple Tag annotations are repeated at the same location; if there is only one Tag, the direct metadata differs from the metadata of **@Tags({@Tag(...)})**. Additionally, a container may declare extra elements with defaults, or be handled specially by tooling, making the choice of syntax meaningful beyond the Tag values returned by **ByType**.

### A Common Misconception

The syntax:

~~~java
@Tag("a")
@Tag("b")
class Repeated {}
~~~

**does not mean** the two Tag annotations are definitely written as two separate direct Tag annotations in the class file's **RuntimeVisibleAnnotations**. When repeated, javac represents them via the **Tags container**. Therefore, a legacy API that only calls **getAnnotation(Tag.class)** may return null even though **getAnnotationsByType(Tag.class)** returns two Tag annotations.

## 5. Standalone Java 17+ Example: Comparing Reflection Results

Create a single file **src/demo/RepeatSyntaxDemo.java**:

~~~java
package demo;

import java.lang.annotation.*;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("alpha")
@Tag("beta")
class Repeated {}

@Tags({@Tag("alpha"), @Tag("beta")})
class ExplicitContainer {}

@Tag("solo")
class Single {}

@Tags({})
class EmptyContainer {}

class NoTag {}

public class RepeatSyntaxDemo {
    public static void main(String[] args) {
        print(Repeated.class);
        print(ExplicitContainer.class);
        print(Single.class);
        print(EmptyContainer.class);
        print(NoTag.class);
    }

    private static void print(Class<?> type) {
        Tag[] all = type.getDeclaredAnnotationsByType(Tag.class);
        Tag direct = type.getDeclaredAnnotation(Tag.class);
        Tags container = type.getDeclaredAnnotation(Tags.class);

        String values = Arrays.toString(
                Arrays.stream(all)
                      .map(Tag::value)
                      .toArray(String[]::new));

        System.out.println(type.getSimpleName()
                + ": values=" + values
                + ", direct=" + (direct != null)
                + ", container=" + (container != null));
    }
}
~~~

Compile and run from the directory containing **src**:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/RepeatSyntaxDemo.java
java -cp out demo.RepeatSyntaxDemo
~~~

**Verified stdout:**

~~~text
Repeated: values=[alpha, beta], direct=false, container=true
ExplicitContainer: values=[alpha, beta], direct=false, container=true
Single: values=[solo], direct=true, container=false
EmptyContainer: values=[], direct=false, container=true
NoTag: values=[], direct=false, container=false
~~~

The example was **actually compiled/run using JDK 21 javac with --release 17**. It uses syntax and APIs available in Java 17, though if deploying on a specific toolchain, you should still run tests on that exact JDK.

### Line-by-Line Explanation

**Repeated:** there are two **@Tag** annotations in source. Because they are repeated, javac generates the **Tags** container according to JLS rules. Reflection via **getDeclaredAnnotationsByType(Tag.class)** unwraps the container and returns a Tag[] containing alpha/beta. **getDeclaredAnnotation(Tag.class)** does not treat the two Tag annotations inside the container as direct Tag annotations, so it returns null. **getDeclaredAnnotation(Tags.class)** finds the container.

**ExplicitContainer:** in source it has **@Tags({...})** directly. In the class file there is also a Tags containing two Tag annotations. The results of the three queries above are the same as for Repeated.

**Single:** there is only one **@Tag("solo")**. It is kept as a direct Tag; there is no need to auto-generate a container. Therefore **direct=true**, **container=false**, and **getDeclaredAnnotationsByType** still returns one element.

**EmptyContainer:** the Tags container is present, but the value array is empty, so **values=[]**, **container=true**.

**NoTag:** neither the base annotation nor the container is present; **values=[]**, **direct=false**, **container=false**.

**Why use getDeclaredAnnotationsByType?** The example only compares annotations declared/contained on each class itself, without superclasses or @Inherited. The **Declared...ByType** API retrieves the Tag[] either directly or indirectly inside a container, without interference from annotations on a parent class.

## 6. Inspecting the Class File with javap

After compiling, use:

~~~bash
javap -v -p out/demo/Repeated.class
javap -v -p out/demo/ExplicitContainer.class
javap -v -p out/demo/Single.class
~~~

Observe the **RuntimeVisibleAnnotations** section:

- **Repeated.class** has **demo.Tags** metadata with its **value** element containing two **demo.Tag** annotations.
- **ExplicitContainer.class** also has **demo.Tags** containing two Tag annotations.
- **Single.class** has a direct **demo.Tag** annotation; no Tags container is needed.

You should not compare bytecode character by character or constant pool indices, because they can differ across compiler versions. The goal is to confirm that **repeated Tag annotations are represented by a container annotation**, rather than two independent direct Tag entries.

An illustrative excerpt from **javap -v** after compiling Repeated:

~~~text
RuntimeVisibleAnnotations:
  ...
    demo.Tags(
      value=[@demo.Tag(
        value="alpha"
      ),@demo.Tag(
        value="beta"
      )]
    )
~~~

The **...** here represents constant-pool indices/other details omitted from the excerpt, **not the complete verbatim output of javap**. The annotation names and values are the key content.

### What Does "Implicit" Mean?

**Implicit container** only means that the author does not type **@Tags** directly at the class site. The compiler still emits metadata with container semantics. **There is no runtime mechanism that gathers multiple Tag annotations by scanning @ characters in source**; when the program runs, reflection works with the class file metadata created by the compiler.

## 7. How Does getAnnotation Differ from getAnnotationsByType?

This is the most important difference when consuming repeatable annotations.

**getAnnotation(Tag.class)** queries for a Tag annotation **present** on the element according to the **AnnotatedElement** contract. It **does not automatically unwrap the Tags container** to return each indirectly contained Tag.

**getAnnotationsByType(Tag.class)** is an API that supports repeatable annotations and can **unwrap the container** to return all matching Tag annotations. For Class and annotation types with @Inherited, this API also follows the **associated** annotation rules per the Javadoc.

**getDeclaredAnnotation(Tag.class)** only checks directly declared Tag annotations, excluding inherited results.

**getDeclaredAnnotationsByType(Tag.class)** checks direct Tag annotations **and indirectly contained Tag annotations** in a container on the element itself, ignoring superclasses.

**getAnnotation(Tags.class)** or **getDeclaredAnnotation(Tags.class)** queries for the **Tags container** as its own annotation type. It does not return the Tag array directly; you must call **container.value()** to get the array.

Table when all annotations have RUNTIME retention and no @Inherited:

| Case | getAnnotation(Tag.class) | getAnnotationsByType(Tag.class) | getAnnotation(Tags.class) |
| --- | --- | --- | --- |
| Two repeated Tag annotations | **null** | **[alpha, beta]** | Tags containing two Tag annotations |
| Explicit Tags container containing two Tag annotations | **null** | **[alpha, beta]** | Tags containing two Tag annotations |
| One direct Tag | Tag("solo") | **[solo]** | null |
| Empty Tags container | null | **[]** | Tags containing an empty array |
| Neither Tag nor Tags applied | null | **[]** | null |

A correct statement to retrieve all Tag annotations:

~~~java
Tag[] tags = SomeType.class.getAnnotationsByType(Tag.class);
for (Tag tag : tags) {
    System.out.println(tag.value());
}
~~~

This is illustrative code; **SomeType** must be an existing class. When using repeatable annotations, you should not write a scanner that only uses **getAnnotation(Tag.class)** and then concludes that null means there are no Tag annotations.

### isAnnotationPresent(Tag.class) Has the Same Limitation

According to the **AnnotatedElement** contract, **isAnnotationPresent(Tag.class)** produces the same boolean result as **getAnnotation(Tag.class) != null**. Therefore, it can also be **false when two Tag annotations are inside a container**.

~~~java
boolean onePresent =
        Repeated.class.isAnnotationPresent(Tag.class);
Tag[] all =
        Repeated.class.getAnnotationsByType(Tag.class);

// onePresent == false
// all.length == 2
~~~

**Do not use isAnnotationPresent(Tag.class) to decide whether a class has at least one repeatable Tag in any form.** If you need to answer that question, use **getAnnotationsByType(Tag.class).length > 0**.

## 8. Rule Against Mixing Multiple Tag Annotations with a Container at the Same Location

Java does not allow freely combining all repeated and container forms. According to JLS §9.7.5:

**Invalid:** having **multiple @Tag base annotations** together with **any @Tags container annotation** in the same declaration/type context:

~~~java
// Compile-time error: two Tag annotations and one container on the same class.
// @Tag("a")
// @Tag("b")
// @Tags({@Tag("c")})
// class InvalidMix {}
~~~

Reason: two base Tag annotations already force the compiler to create an implicit container. If an explicit container were also present, the result would have overlapping containment layers or ambiguous merging rules.

**May be valid:** one **@Tag** base annotation appearing together with **one @Tags container**:

~~~java
@Tag("direct")
@Tags({@Tag("nested")})
class MixedButLegal {}
~~~

This syntax is **permitted by the JLS** and has been verified with javac --release 17. Because there is only one base Tag, it does not need to generate an implicit container from multiple Tag annotations. However, having both a direct Tag and a Tags container at the same location makes the metadata model harder to explain; for public APIs, a consistent representation should be preferred.

**Invalid:** one base Tag accompanied by **multiple @Tags containers** at the same location, for example:

~~~java
// Compile-time error according to the JLS:
// @Tag("direct")
// @Tags({@Tag("first")})
// @Tags({@Tag("second")})
// class InvalidContainers {}
~~~

An ordinary Tags container cannot itself be repeated, unless it is also designed to be repeatable with another containment level; even with another level, the JLS still restricts ambiguous mixing cases.

**Recommendation:** in normal code, choose either **multiple @Tag** or **one @Tags({...})**, and do not combine them without a special requirement. This reduces discrepancies between APIs that read Tag directly and APIs that unwrap the container.

## 9. Required Conditions for a Container Annotation Type

Not just any annotation with a Tag array becomes a valid containing annotation type. JLS §9.6.3 establishes the constraints.

### 9.1. The value() Element Must Return the Exact Base Annotation Array

~~~java
@interface Tags {
    Tag[] value();
}
~~~

Valid: **Tag[]** is the return type of **value()**.

Invalid:

~~~java
// Not a valid containing type for Tag:
// @interface Tags {
//     Object[] value();
// }
~~~

**Object[]** is an invalid annotation element type and does not satisfy the Tag[] requirement. **String[]** also cannot substitute for **Tag[]** if the container is declared for Tag.

### 9.2. All Additional Elements in the Container Must Have Defaults

The container may declare additional elements:

~~~java
@interface Tags {
    Tag[] value();
    String source() default "local";
}
~~~

**source()** has a default, so when the compiler creates an implicit container, it does not force the author of each @Tag to provide source.

Invalid as a container for Tag:

~~~java
// @interface Tags {
//     Tag[] value();
//     String source(); // missing default
// }
~~~

If there is a required additional element, javac does not know what value to use when auto-generating the container from repeated @Tag annotations, so it rejects the repeatable type definition that uses this container.

**A design consequence:** the repeated syntax and explicit container syntax can have additional differences if the container has extra elements. With repeated syntax, the implicit container uses the default value of the extra element; with an explicit container, the author can provide a non-default value. Therefore, when building tools, you need to decide whether you care only about the base annotations or also about the metadata on the container.

### 9.3. The Container's Retention Must Not Be Shorter Than the Base's Retention

Example suitable for runtime reading:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Tags {
    Tag[] value();
}
~~~

This only illustrates **retention** and omits the @Repeatable/@Target needed for a complete program. The condition is that **the containing type must have a retention at least as long as the base annotation type** along SOURCE, CLASS, RUNTIME.

If Tag has **RUNTIME** but Tags only has **CLASS**, the container could disappear from runtime reflection as soon as Tag is repeated — that configuration is disallowed by the JLS.

**The default retention is CLASS** if @Retention is not specified. Therefore, for repeatable annotations that need to be read via reflection, you should declare **@Retention(RUNTIME)** consistently on both the base and the container.

### 9.4. Targets of the Base and Container Must Be Compatible

The container cannot arbitrarily be applied to locations that the base annotation does not allow. The JLS requires compatible locations according to the @Target compatibility rules, including the special cases of **ANNOTATION_TYPE**, **TYPE**, **TYPE_PARAMETER**, and **TYPE_USE**.

The simplest practice: if you want to repeat Tag on **TYPE**, give both **Tag** and **Tags** **@Target(TYPE)**.

~~~java
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag { String value(); }

@Target(ElementType.TYPE)
@interface Tags { Tag[] value(); }
~~~

This snippet only describes the target configuration, omitting imports and retention for brevity. If you want to use it on METHOD, FIELD, PARAMETER, or TYPE_USE, check the targets of both and write a corresponding javac test. An annotation type with a @Target valid for a single use **is not necessarily allowed to repeat at every location**, because repeating requires the container to also be valid in that context.

### 9.5. @Documented and @Inherited Must Be Coordinated

If the base annotation type has **@Documented**, the container must have **@Documented**. If the base has **@Inherited**, the container must have **@Inherited**. The JLS allows the container to have these meta-annotations even when the base does not, but does not allow the base to require them while the container omits them.

These rules exist so that repeated metadata does not lose its meaning when the compiler represents the base via the container.

## 10. Repeatable Annotations and @Inherited

**@Inherited** allows a subclass to be queried for metadata from its superclass under Java's defined conditions. When combining repeatable annotations with @Inherited, it is important to understand the difference between **present** and **associated**.

Example declarations (abbreviated, assuming appropriate imports):

~~~java
@Inherited
@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}

@Role("reader")
@Role("auditor")
class Base {}

class Child extends Base {}
~~~

When calling **Child.class.getAnnotationsByType(Role.class)**, you can receive the two Role annotations from Base through AnnotatedElement's **associated annotations** rules. **Child.class.getDeclaredAnnotationsByType(Role.class)** returns an empty array because Child does not directly declare the Role annotations.

**Do not confuse** that with **Child.class.getAnnotation(Role.class)**: because the two Role annotations on Base are represented via a container, a query asking for a single *present* Role may not find a direct Role, whereas ByType still finds the contained and inherited values.

If Child declares Role directly or indirectly, the values on Child take precedence under the associated rules; Base's list is not automatically merged with Child's. A framework that wants to aggregate Role annotations across class hierarchy levels must define its own rules.

**@Inherited does not apply along interface implementation paths**, and does not automatically propagate annotations on overridden methods. This is a general limitation of @Inherited and does not change simply because the annotation type has @Repeatable.

## 11. Explicit Containers and Legacy Code Migration

You may encounter code that uses a container before the annotation type is marked **@Repeatable**:

~~~java
@Tags({
    @Tag("internal"),
    @Tag("beta")
})
class OldStyle {}
~~~

If Tag and Tags are validly declared but Tag does not yet have @Repeatable, the explicit container syntax can still work as an ordinary annotation: **Tags** is simply an annotation type owning a **Tag[] value()** element. The author does not need to repeat @Tag directly on the class.

After changing Tag to be repeatable with **@Repeatable(Tags.class)**, the **getAnnotationsByType(Tag.class)** APIs can begin recognizing and unwrapping Tags as the containing annotation type. This is a behavioral difference in the reflection API if the system previously only read Tag/Tags using its own custom mechanism.

**Do not conflate source compatibility, binary compatibility, and behavioral compatibility.** Upgrading an annotation type from non-repeatable to repeatable may preserve binary linking compatibility, yet change the results of the ByType API when the container was not previously treated as a repeatable annotation container.

For libraries:

- When you simply want users to write multiple labels, the repeated syntax **@Tag("x") @Tag("y")** is usually natural and easy to read.
- When working with legacy systems that have their own container structure, the **@Tags({...})** syntax can help preserve the existing contract.
- When you need to read all labels in a new API, prefer **getAnnotationsByType(Tag.class)** and test direct Tag, implicit container, and explicit container cases.
- When you want to distinguish which form the source code used, **standard runtime reflection cannot reconstruct the exact original syntax**. You need to analyze the source with appropriate tooling; the two forms with identical post-compilation metadata may be indistinguishable via reflection.

## 12. Repeated Annotations on METHOD, FIELD, and TYPE_USE

The runnable example above applies Tag to a class to focus on container syntax. However, @Repeatable is not only for classes; it can be used in many places if the target allows it.

**On methods:**

~~~java
@Target(ElementType.METHOD)
@Repeatable(Checks.class)
@interface Check {
    String value();
}

@Target(ElementType.METHOD)
@interface Checks {
    Check[] value();
}

class Service {
    @Check("authenticated")
    @Check("logged")
    void process() {}
}
~~~

If you intend to read them via runtime reflection, you must add **@Retention(RUNTIME)** to both Check and Checks. Then obtain the Method from the Class and call **method.getAnnotationsByType(Check.class)** to retrieve the rules.

**On type use:**

~~~java
@Target(ElementType.TYPE_USE)
@Repeatable(Qualifiers.class)
@interface Qualifier {
    String value();
}

@Target(ElementType.TYPE_USE)
@interface Qualifiers {
    Qualifier[] value();
}

class Repository {
    java.util.List<@Qualifier("readonly")
                   @Qualifier("trusted") String> names;
}
~~~

The illustration shows the syntax; you need to import the meta-annotations and add runtime retention if you want reflection to read the type use site. For type annotations, read via the **AnnotatedType** or **AnnotatedParameterizedType** of the field/method instead of calling **Field.getAnnotation(Qualifier.class)** directly.

**Common point:** repetition is only allowed at locations where **both the base and the container are applicable** according to the JLS. Repeated syntax does not bypass target rules.

## 13. Common Errors and How to Fix Them

| Issue | Cause | Solution |
| --- | --- | --- |
| Repeating @Tag twice causes javac to report it is not repeatable | Missing **@Repeatable(Tags.class)** | Register the proper container on Tag |
| @Repeatable points to a container with **String[] value()** | The container must have **Tag[] value()** | Fix the type of the value element |
| Container has an extra element without a default | Compiler cannot generate an implicit container | Add a valid default or remove the element |
| Tag has RUNTIME retention while Tags only has CLASS | Container retention is shorter than base retention | Use RUNTIME for Tags |
| @Tag works, but repeating it at some location is rejected | Container target is incompatible with the location | Check @Target of both |
| Repeating @Tag while also writing @Tags at the same location | Multiple Tag annotations + container violates JLS | Choose either repeated syntax or one explicit container |
| Calling only getAnnotation(Tag.class) and concluding there are no labels | The API does not unwrap containers | Use getAnnotationsByType(Tag.class) |
| isAnnotationPresent(Tag.class) returns false even though two @Tag annotations are visible | Equivalent to getAnnotation(Tag.class) != null | Use **ByType.length > 0** |
| Expecting a single Tag to auto-generate a container | Compiler does not need a container for just one Tag | Check the direct form as well |
| Expecting an empty container to be completely identical to having no annotation | Tags is still present in metadata | Query Tags separately if that state matters |
| Assuming @Tags({...}) means Tags is also repeatable | A container is not automatically repeatable just because it holds Tag[] | Only a base type with @Repeatable can be repeated |
| Missing @Retention(RUNTIME) while calling reflection | Default retention is CLASS | Apply RUNTIME properly on base/container |
| Using Class.getAnnotation for a type-use annotation | Querying the wrong metadata location | Use the appropriate AnnotatedType API |
| Guessing order via unrelated getDeclaredAnnotations() | Not the API defining all Tag ordering rules | Use getAnnotationsByType and the container rules |

## 14. Self-Check Exercises

**Exercise 1.** Given the two declarations:

~~~java
@Tag("red")
@Tag("blue")
class A {}

@Tags({@Tag("red"), @Tag("blue")})
class B {}
~~~

**Question:** Do A and B produce the same **getDeclaredAnnotationsByType(Tag.class)** result? **Yes:** both return an array of two Tag annotations with values red/blue in source/container order.

**Exercise 2.** For A and B, does **getDeclaredAnnotation(Tag.class)** return a Tag? **No** in both cases where the two values are contained via Tags; calling this API returns null.

**Exercise 3.** For **@Tag("only") class C {}**, does reflection necessarily find **Tags**? **No.** A single direct Tag does not require an implicit container. **getAnnotationsByType(Tag.class)** still returns a one-element array.

**Exercise 4.** For **@Tags({}) class D {}**, what is **D.class.getAnnotationsByType(Tag.class).length**? **0**. However, **D.class.getAnnotation(Tags.class)** can still be non-null if Tags is retained at runtime.

**Exercise 5.** If the container contains **Tag[] value(); String source();** and source has no default, can it be the containing annotation type of Tag? **No.** Every element other than value() on the container must have a default.

**Exercise 6.** If Tag only has **@Target(METHOD)** while Tags only has **@Target(FIELD)**, can Tag be repeated on a method? **No**, because the container cannot be applied to a method and the target relationship is invalid for a containing type.

**Exercise 7.** Is it allowed to write **@Tag("one") @Tags({@Tag("two")})** on the same class? **It can be permitted by the JLS** when there is exactly one base Tag and exactly one container, though the API becomes harder to read. You may not write a second Tag alongside the container.

**Exercise 8.** To read repeated annotations on **List<@Qualifier("a") @Qualifier("b") String>** at runtime, can you call **Field.getAnnotation(Qualifier.class)**? **No** if Qualifier is only TYPE_USE. You must obtain the appropriate **AnnotatedType** and call **getAnnotationsByType(Qualifier.class)** on the exact type location.

**Exercise 9.** Is replacing repeated syntax with an explicit container always recoverable from the class file? **No.** With equivalent values, the compiler may write the same container metadata form; reflection is not a tool that preserves the original source syntax.

## 15. Official References

- **Java Language Specification §9.6.3 — Repeatable Annotation Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3 — rules for container value(), retention, target, Documented, and Inherited.
- **Java Language Specification §9.7.5 — Multiple Annotations of the Same Interface:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.5 — repeated syntax, implicit containers, ordering, and container combination restrictions.
- **Java SE 17 — java.lang.annotation.Repeatable:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html — meta-annotation for the base annotation type.
- **Java SE 17 — java.lang.reflect.AnnotatedElement:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html — direct/indirect, present/associated, getAnnotation, and getAnnotationsByType.
- **Java SE 17 — java.lang.annotation.RetentionPolicy:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html — SOURCE, CLASS, RUNTIME.

**Key takeaway:** **@Tag("a") @Tag("b")** is the repeated syntax that causes the compiler to create an **implicit Tags container**; **@Tags({@Tag("a"), @Tag("b")})** is the **explicit container declaration** syntax. Both forms typically yield the same list when read with **getAnnotationsByType(Tag.class)**, but the **getAnnotation(Tag.class)** API may not see Tag annotations held inside a container. Designing the base/container to follow JLS rules and using the right API are the keys to leveraging repeatable annotations safely.
