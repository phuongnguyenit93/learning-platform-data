# TYPE_PARAMETER and TYPE_USE in Java Annotations

When writing **@Target** for a custom annotation, **ElementType.TYPE_PARAMETER** and **ElementType.TYPE_USE** allow placing the annotation in type-related positions, but these two constants do not have the same meaning.

- **TYPE_PARAMETER**: used for the **type parameter declaration** of a generic class, interface, method, or constructor, for example, the letter **T** declared in **class Box<T>**.
- **TYPE_USE**: used for a **type-use context**, for example, **String** in **List<String>**, a method return type, or the component type in an array. According to the Java specification, TYPE_USE also includes type declarations and type parameter declarations to support type-checking tools.

The easiest point to confuse: **declaring T** in **class Box<T>** and **using T** in **T value;** are two different positions. An annotation that only allows TYPE_PARAMETER does not automatically become a valid annotation for every position where the letter T appears. Conversely, TYPE_USE has a broader scope and **can appear on a type parameter declaration**.

## 1. Declaring two annotations with different @Target values

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_PARAMETER)
@interface ParameterTag {
    String value();
}

@Target(ElementType.TYPE_USE)
@interface TypeTag {
    String value();
}
~~~

The **@Target** symbol is a Java meta-annotation belonging to the **java.lang.annotation** package. It specifies the syntactic positions where an annotation type can be used. **TYPE_PARAMETER** and **TYPE_USE** are two enum constants of **ElementType**, introduced in Java 8.

Usage:

~~~java
class Box<@ParameterTag("item") T> {
    @TypeTag("stored-value") T value;
}
~~~

- **@ParameterTag("item")** is placed immediately before **T** in the type parameter declaration list **<T>**. This is the TYPE_PARAMETER target.
- **@TypeTag("stored-value")** is placed before **T** in **T value;**. This is an annotation on the **type used** to declare the value field, which belongs to TYPE_USE.
- These two annotations do not alter generic rules, type bounds, or assignments at runtime merely by the presence of the @ symbol. To enforce a null-checking policy, you must have an annotation processor, type checker, framework, or application code that interprets the metadata.

## 2. TYPE_PARAMETER: annotating the type parameter declaration itself

TYPE_PARAMETER applies to the declaration of a **type variable** of a generic class/interface/method/constructor:

~~~java
@Target(ElementType.TYPE_PARAMETER)
@interface DocumentedVariable {
    String value();
}

class Cache<@DocumentedVariable("key") K,
            @DocumentedVariable("value") V> {
}

interface Mapper<@DocumentedVariable("input") I,
                 @DocumentedVariable("output") O> {
}

class Utility {
    <@DocumentedVariable("result") T> T keep(T input) {
        return input;
    }
}
~~~

For **Cache**, K and V are two type parameters **declared** inside the angle brackets. For **Utility.keep**, T is a type parameter **declared by the method**, independent of the class's type parameters.

A generic constructor can also declare its own type parameter:

~~~java
class Container {
    <@DocumentedVariable("constructor") T> Container(T initial) {
        System.out.println(initial);
    }
}
~~~

In this example, **T** appearing in the generic constructor declaration part is TYPE_PARAMETER. The letter **T** in **T initial** is a **type use**; the DocumentedVariable annotation can only be written on the **declaration of T** because its @Target does not include TYPE_USE.

**Valid/invalid comparison:**

~~~java
class Valid<@DocumentedVariable("declared") T> {
    T item;
}

// Invalid: DocumentedVariable does not have the TYPE_USE target.
// class Invalid<T> {
//     @DocumentedVariable("type-used") T item;
// }

// Invalid: String is a type argument being used, not
// a new type parameter declaration.
// java.util.List<@DocumentedVariable("argument") String> names;
~~~

The invalid examples are placed in comments so they do not prevent the program from compiling. To annotate a field's type or a generic argument, use an annotation with the **TYPE_USE** target.

Do not equate TYPE_PARAMETER with **ElementType.PARAMETER**. PARAMETER is a **formal parameter of a method/constructor**, for example, **String input** in **void send(String input)**. TYPE_PARAMETER is a **generic type parameter**, for example, **T** in **<T> void send(T input)**.

## 3. TYPE_USE: annotating type-use positions

TYPE_USE allows an annotation to appear in contexts where Java syntax uses a type. Representative examples:

~~~java
import java.util.List;
import java.util.Map;

class TypeExamples {
    @TypeTag("field-type")
    String title;

    List<@TypeTag("list-element") String> names;

    Map<@TypeTag("map-key") String,
        @TypeTag("map-value") Integer> counts;

    @TypeTag("return-type")
    String normalize(@TypeTag("argument-type") String input) {
        @TypeTag("local-type") String result = input.trim();
        return result;
    }

    @TypeTag("element-type") String
            @TypeTag("array-dimension") [] items;
}
~~~

How to read it:

- **@TypeTag("field-type") String title**: annotates the **String** type used for the field title.
- **List<@TypeTag("list-element") String>**: annotates the **type argument String** itself in the parameterized type **List<String>**.
- **Map<@TypeTag("map-key") String, @TypeTag("map-value") Integer>**: each generic argument has independent metadata.
- **@TypeTag("return-type") String normalize(...)**: annotates the **String return type**, distinct from an annotation placed directly on the method declaration.
- **@TypeTag("argument-type") String input**: annotates the **String type** of the input parameter, distinct from an annotation placed on the parameter declaration using the PARAMETER target.
- **@TypeTag("local-type") String result**: annotates the type used by the local variable.
- **String @TypeTag("array-dimension") []**: annotates the **array dimension**, whereas an annotation before String annotates the **String component type**. The position of the @ symbol changes the type component to which metadata is attached.

TYPE_USE also covers contexts such as generic **bounds** types, types specified in **cast** expressions, types used in **implements/extends**, and other positions according to JLS §4.11. For arrays or nested generics, the @ symbol must be placed right next to the type component you want to represent.

Example of annotating a generic bound:

~~~java
class NumericBox<T extends @TypeTag("upper-bound") Number> {
}
~~~

Here **Number** is a type used in the **extends** clause of T, not the name of a new type parameter. Therefore, TYPE_USE is the appropriate target.

## 4. The intersection: TYPE_USE also allows type parameter declarations

Although the name **TYPE_USE** suggests only usage positions, the Java documentation for **ElementType.TYPE_USE** specifies two additional allowed declaration cases: **type declarations** and **type parameter declarations**.

Therefore, the following snippet is valid:

~~~java
@Target(ElementType.TYPE_USE)
@interface CheckedType {
}

class Holder<@CheckedType T> {
    @CheckedType T value;
}
~~~

**@CheckedType T** in **Holder<...>** is an annotation on the **type parameter declaration**, permitted by TYPE_USE. **@CheckedType T value** is an annotation on **the use of T as the field's type**. Even with the same @ syntax, where the metadata is placed is not the same.

Comparison table:

| Syntactic position | TYPE_PARAMETER | TYPE_USE |
| --- | --- | --- |
| **class Box<@A T>** — declaration of T | Yes | Yes |
| **<@A T> T identity(T x)** — method's declaration of T | Yes | Yes |
| **T value;** — using T as a field type | No | Yes |
| **List<@A String>** — generic type argument | No | Yes |
| **T extends @A Number** — generic bound | No | Yes |
| **@A String method()** — return type | No | Yes |
| **@A class Service {}** — class type declaration | No | Yes (declaration exception included by TYPE_USE) |

**Do not conclude that TYPE_PARAMETER and TYPE_USE are completely disjoint in syntactic positions**; they overlap at type parameter declarations. However, in terms of design intent, TYPE_PARAMETER helps describe specifically the definition of a type variable, whereas TYPE_USE targets information at positions where types appear.

If you want an annotation explicitly intended for both purposes, you can declare:

~~~java
@Target({ElementType.TYPE_PARAMETER, ElementType.TYPE_USE})
@interface TypeInfo {
    String value();
}
~~~

In terms of **valid position scope**, TYPE_USE already includes the places where TYPE_PARAMETER is allowed to appear. Listing both can be useful when reading design intent or serving analysis tools, but it is not necessary solely to permit the syntax on type parameter declarations.

## 5. TYPE_USE differs from TYPE, FIELD, METHOD, and PARAMETER

These are different ElementType constants:

| Target | What does it annotate? | Example |
| --- | --- | --- |
| **TYPE** | Declaration of a class, interface, enum, or annotation type | **@ServiceMarker class Service {}** |
| **TYPE_PARAMETER** | Generic type parameter declaration | **class Box<@ParamTag T> {}** |
| **TYPE_USE** | Type used in expressions/declarations and two additional declaration contexts | **List<@NonNull String>** |
| **FIELD** | Declaration of a field | **@AuditField String name;** |
| **METHOD** | Declaration of a method | **@Audited String read() {...}** |
| **PARAMETER** | Method/constructor parameter declaration | **void send(@Bind String value) {...}** |

For example, the same declaration line can refer to both a **field declaration** and a **type use**. If an annotation has target FIELD, it describes the field declaration. If it only has target TYPE_USE, the annotation before String is interpreted as an annotation on the **String type**. This distinction matters when tools read metadata: the reflection API used to look up a field's annotations and the API used to read annotations on the field's type are two different access paths.

~~~java
@Target(ElementType.FIELD)
@interface FieldNote {}

@Target(ElementType.TYPE_USE)
@interface TypeNote {}

class User {
    @FieldNote
    @TypeNote String name;
}
~~~

To read the corresponding metadata:

~~~java
java.lang.reflect.Field field = User.class.getDeclaredField("name");

boolean declarationMarked =
        field.isAnnotationPresent(FieldNote.class);

boolean typeMarked =
        field.getAnnotatedType().isAnnotationPresent(TypeNote.class);
~~~

Both booleans are true when **@Retention(RUNTIME)** is declared on both FieldNote and TypeNote. If @Retention is omitted, the default is CLASS, and the reflection example above cannot guarantee reading the annotations at runtime. The snippet above is illustrative code within a context that permits **NoSuchFieldException**, not a standalone runnable program.

## 6. Complete Java 17+ example with verified output

This example uses two annotations: **ParameterLabel** with only the TYPE_PARAMETER target, and **TypeLabel** with only the TYPE_USE target. Both use **@Retention(RUNTIME)** so the metadata can be observed via reflection.

Create the file **src/demo/AnnotationTargetsDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.TypeVariable;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface ParameterLabel {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeLabel {
    String value();
}

class Repository<
        @ParameterLabel("entity") T
        extends @TypeLabel("bound") Number> {

    @TypeLabel("container")
    List<@TypeLabel("item") String> names = List.of("A");

    @TypeLabel("result")
    String echo(@TypeLabel("argument") String input) {
        return input;
    }

    <@ParameterLabel("method-variable") U> U identity(U input) {
        return input;
    }
}

public class AnnotationTargetsDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        TypeVariable<?> typeParameter =
                Repository.class.getTypeParameters()[0];

        System.out.println("type parameter="
                + typeParameter.getName() + ":"
                + typeParameter.getAnnotation(ParameterLabel.class).value());

        System.out.println("bound="
                + typeParameter.getAnnotatedBounds()[0]
                        .getAnnotation(TypeLabel.class).value());

        Field names = Repository.class.getDeclaredField("names");
        AnnotatedParameterizedType fieldType =
                (AnnotatedParameterizedType) names.getAnnotatedType();

        System.out.println("field type="
                + fieldType.getAnnotation(TypeLabel.class).value());

        System.out.println("type argument="
                + fieldType.getAnnotatedActualTypeArguments()[0]
                        .getAnnotation(TypeLabel.class).value());

        Method echo = Repository.class.getDeclaredMethod(
                "echo", String.class);

        System.out.println("return type="
                + echo.getAnnotatedReturnType()
                        .getAnnotation(TypeLabel.class).value());

        System.out.println("parameter type="
                + echo.getAnnotatedParameterTypes()[0]
                        .getAnnotation(TypeLabel.class).value());

        Method identity = Repository.class.getDeclaredMethod(
                "identity", Object.class);

        System.out.println("method type parameter="
                + identity.getTypeParameters()[0]
                        .getAnnotation(ParameterLabel.class).value());
    }
}
~~~

From the directory containing **src**, compile and run:

~~~bash
javac -encoding UTF-8 -d out src/demo/AnnotationTargetsDemo.java
java -cp out demo.AnnotationTargetsDemo
~~~

**Expected stdout:**

~~~text
type parameter=T:entity
bound=bound
field type=container
type argument=item
return type=result
parameter type=argument
method type parameter=method-variable
~~~

**Explanation of each result:**

1. **Repository.class.getTypeParameters()[0]** returns the **TypeVariable** for T declared on Repository. **TypeVariable.getAnnotation(ParameterLabel.class)** reads the annotation at the type parameter declaration position.
2. **typeParameter.getAnnotatedBounds()[0]** represents the **Number** bound annotated with TYPE_USE, so it returns the label "bound".
3. **Field.getAnnotatedType()** holds the metadata at the field's type-use position, namely **List**. Because the field contains generics, it can be cast to **AnnotatedParameterizedType**.
4. **getAnnotatedActualTypeArguments()[0]** inspects the type argument **String** in **List<String>** to read the label "item". This metadata is distinct from the "container" label on the outer List.
5. **Method.getAnnotatedReturnType()** reads the annotation on the return type, while **getAnnotatedParameterTypes()[0]** reads the annotation on the method parameter's type.
6. **Method.getTypeParameters()[0]** reads the declaration of U on the generic method. Because U has no explicit bound, the erased type of U is **Object**, so the method is looked up via reflection with the parameter **Object.class**.

The example deliberately does not use **field.getAnnotation(TypeLabel.class)** to read "container", because this is an annotation on the field's **type use**, not metadata belonging to the FIELD declaration.

## 7. Metadata retention and reading it properly via reflection

**@Retention** is a decision independent of **@Target**:

- **SOURCE**: the annotation is retained only in source code and is not kept in the class file for reflection to read.
- **CLASS**: the annotation is written to the class file but is not normally made available to the Java runtime via reflection; this is the default retention if @Retention is omitted.
- **RUNTIME**: metadata can be read by Java reflection from the loaded class; the complete example uses this mode.

Even when using reflection in all cases, the metadata resides in different places:

| Metadata to read | Appropriate API |
| --- | --- |
| Annotation on **type parameter declaration** T | **Class.getTypeParameters()**, **Method.getTypeParameters()**, then **TypeVariable.getAnnotation(...)** |
| Annotation on the **generic bound** of T | **TypeVariable.getAnnotatedBounds()** |
| Annotation on the **field type** | **Field.getAnnotatedType()** |
| Annotation on a field's **generic argument** | **AnnotatedParameterizedType.getAnnotatedActualTypeArguments()** |
| Annotation on the **return type** | **Method.getAnnotatedReturnType()** |
| Annotation on a **method parameter type** | **Method.getAnnotatedParameterTypes()** |

Do not confuse **Field.getType()** or **Method.getReturnType()** with the methods that return **AnnotatedType**. The former calls provide basic type information; calls prefixed with **getAnnotated...** provide access to annotations at **type-use positions**.

The same class such as **String** can be used in many positions with different annotations. They do not automatically turn into annotations on the declaration of **java.lang.String** itself. Therefore, querying annotations on **String.class** does not mean reading all annotations from every position where String is used in the program.

## 8. Limitations and notes when applying to type checkers

TYPE_USE is commonly seen in static analysis tools. A library might define **@NonNull** or **@ReadOnly** with target TYPE_USE to attach to various type positions, such as elements in a List or return types. However, the standard Java compiler only checks the validity of syntax, targets, and the types of annotation values; it **does not automatically infer and enforce** any domain constraints of a custom annotation.

Example:

~~~java
@Target(ElementType.TYPE_USE)
@interface NonNull {}

class Example {
    @NonNull String name;
}
~~~

This **does not automatically prevent** the assignment **name = null** or intentionally add a NullPointerException. A corresponding tool is needed to read the annotation and apply checking rules, or application code must execute runtime checking logic.

Additionally:

- **TYPE_PARAMETER** and **TYPE_USE** do not replace the generics system. An annotation on T does not create a new bound, does not alter type erasure, and does not cause Java to retain full generic type arguments of every object at runtime.
- When an annotation has both TYPE_USE and a declaration target such as FIELD/METHOD/PARAMETER, how it applies and its metadata can involve multiple contexts depending on placement. Design the intent clearly and use the appropriate API for retrieval.
- Annotations on **TYPE_USE** can appear deep inside complex structures: nested generics, wildcard bounds, array dimensions, or owner types. When reading via reflection, you need to traverse **AnnotatedType** structurally rather than only checking the outermost annotation.
- If you omit **@Target** completely, a custom annotation applies by default to the **declaration** contexts specified by Java, but it is not permitted to appear in a **type context** merely because no target was declared. Therefore, you must specify TYPE_USE if you want to annotate type arguments or types in casts.

## 9. Common mistakes and how to fix them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Using a TYPE_PARAMETER-only annotation on **List<@A String>** | String is a type argument in a type-use position | Change the target to TYPE_USE |
| Placing a TYPE_PARAMETER-only annotation before **T field;** | This is a use of T as a field type | Use a TYPE_USE annotation |
| Assuming TYPE_USE cannot be placed on a T declaration | TYPE_USE also includes type parameter declarations | You can write **class Box<@A T>** when A has TYPE_USE |
| Confusing TYPE_PARAMETER with PARAMETER | A type variable is different from a method/constructor parameter | Contrast the letter T in **<T>** with **String name** |
| Using **@Target(TYPE)** and then writing **List<@A String>** | TYPE applies to class/interface/enum/annotation type declarations, not generic arguments | Use TYPE_USE |
| Using **@Target(FIELD)** and trying to read it with **getAnnotatedType()** | A FIELD declaration annotation is different from a type-use annotation | Set the right target and use **Field.getAnnotation(...)** for FIELD |
| Using **Field.getType().getAnnotation(TypeTag.class)** | Queries the class of the field type, ignoring the type-use position | Use **Field.getAnnotatedType().getAnnotation(...)** |
| Omitting @Retention(RUNTIME) while expecting reflection to find it | Runtime metadata is not retained with SOURCE/CLASS | Add **@Retention(RUNTIME)** if reflection is truly needed |
| Expecting **@NonNull** to block null automatically | Custom annotations do not implicitly generate runtime checks | Integrate a tool/type checker or handling logic |
| Assuming every annotation placed before a method targets METHOD | An annotation at the return type position may belong to TYPE_USE | Check @Target and the metadata-reading API |

## 10. Self-check exercises

**Exercise 1.** Given **@Target(TYPE_PARAMETER)**, which snippet is valid?

~~~java
class Bag<@ParameterTag("decl") T> {}
// List<@ParameterTag("argument") String> a; // Invalid
~~~

The first line is valid because it declares T; the second line is invalid because String is a type argument. Explain why both appear inside angle brackets yet have different meanings: one is **declaring a generic parameter**, while the other is **passing a generic argument**.

**Exercise 2.** Given **@Target(TYPE_USE)**, which positions are permitted?

~~~java
class Bag<@TypeTag("declaration") T> {
    java.util.List<@TypeTag("argument") T> elements;
}
~~~

Both are valid: TYPE_USE permits the type parameter declaration position and the position where T is used as a type argument.

**Exercise 3.** Can you read the **@TypeTag("x")** annotation on **List<@TypeTag("x") String>** by calling **String.class.getAnnotation(TypeTag.class)**? **No.** The annotation is on a **type-use position of String** and is not automatically attached to the String class declaration.

**Exercise 4.** If you want to inspect the annotation on the bound of **T extends @TypeTag("bound") Number**, which API must you use? Use **TypeVariable.getAnnotatedBounds()** and then read the annotation on the corresponding bound's **AnnotatedType** element.

**Exercise 5.** Why does the snippet **@Target(TYPE_USE) @interface NonNull {}** not guarantee that every variable annotated with @NonNull cannot hold null? Because annotations only carry metadata; Java needs an additional tool to understand and check the non-null rule you define.

## 11. References

- **Java SE 17 — ElementType**, describing TYPE_PARAMETER, TYPE_USE, and how TYPE_USE includes type parameter declarations: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html
- **Java Language Specification §4.11 — Where Types Are Used**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.11
- **Java Language Specification §9.6.4.1 — @Target**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1
- **Java SE 17 — AnnotatedParameterizedType**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html

When encountering TYPE_PARAMETER and TYPE_USE, determine precisely **whether the placement of the @ symbol is declaring a type variable or annotating a type-use position**, and then cross-check it against @Target. For an annotation intended solely for type variable declarations, TYPE_PARAMETER is the narrow and clear choice; for metadata about type-use positions, TYPE_USE is the broader choice and also includes type parameter declarations.
