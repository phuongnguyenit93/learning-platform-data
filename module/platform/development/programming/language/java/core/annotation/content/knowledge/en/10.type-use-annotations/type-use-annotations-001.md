# Distinguishing Declaration Annotations from Type Annotations in Java

Java allows annotations to be used to describe **a declared program element** (*declaration*) or **a location where a type is used** (*type use*). Both share the **@** syntax, but the metadata is attached to two different entities. Therefore, when reading annotations via reflection or designing source code analysis tools, you must accurately determine whether an annotation applies to **the declaration** or to **the type at the point where it appears**.

Example:

~~~java
@FieldTag String name;
~~~

If **FieldTag** is declared with **@Target(ElementType.FIELD)**, this annotation belongs to **the declaration of field name**. If declared with **@Target(ElementType.TYPE_USE)**, it belongs to **the type-use location of String for field name**. If FieldTag permits **both FIELD and TYPE_USE**, the @ annotation at this location can be treated as **both a declaration annotation and a type annotation** according to the Java Language Specification (JLS §9.7.4).

Consequently, simply seeing that the @ appears before the word **String** is not enough to determine what the annotation applies to; you must check **the @Target of the annotation type**.

## 1. What Are Declarations and Type Uses?

A **declaration** creates or defines a program entity, such as a class, method, field, constructor, parameter, or type parameter:

~~~java
class Customer {
    String name;

    String displayName(String prefix) {
        return prefix + name;
    }
}
~~~

In the snippet above:

- **class Customer** is a class declaration.
- **String name** is the declaration of field **name**, and also contains a use of the type **String** as the field's type.
- **displayName(...)** is a method declaration, while the first **String** is the method's return type.
- **String prefix** is the declaration of parameter **prefix**, and also contains a use of the String type as the parameter type.

A single syntactic position can contain both a declaration and the type used to define that declaration. This is precisely why annotations on fields, method returns, or formal parameters are easily confused.

A **type use** does not require creating a new declaration. For example, **String** in **List<String>**, **Number** in **T extends Number**, or **String** in the cast **(String) obj** are all places where a type appears:

~~~java
java.util.List<String> names;
class Holder<T extends Number> {}
Object raw = "hello";
String text = (String) raw;
~~~

Annotations with the TYPE_USE target can be placed at these type locations, which annotations targeting only FIELD, METHOD, or PARAMETER cannot cover.

## 2. @Target Determines What an Annotation Applies To

The three declarations below illustrate the basic boundary:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface FieldTag {
    String value();
}

@Target(ElementType.TYPE_USE)
@interface TypeTag {
    String value();
}

@Target({ElementType.FIELD, ElementType.TYPE_USE})
@interface BothTag {
    String value();
}
~~~

When used:

~~~java
class Account {
    @FieldTag("field declaration")
    @TypeTag("String type")
    String owner;

    @BothTag("field and type")
    String identifier;
}
~~~

Conclusions:

1. **FieldTag** applies only to **the declaration of field owner**.
2. **TypeTag** applies only to **the String type** of field owner, i.e., a *type-use annotation*.
3. **BothTag** allows both **FIELD and TYPE_USE**. With the syntax placed before the field type as shown above, the annotation can belong to both the declaration of field identifier and its corresponding String type location.

**The same placement position does not necessarily have the same meaning.** The compiler checks the valid target set and then represents the metadata according to the specified applicability kind.

An annotation can have multiple targets:

~~~java
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.TYPE_USE
})
@interface TraceInfo {}
~~~

With this kind of annotation, you must inspect the specific location and sometimes both forms of metadata. Allowing multiple targets only specifies where the annotation can be placed; it does not automatically create any auditing or tracing behavior.

## 3. Comparing Declaration Targets with TYPE_USE

| Target | What Is Annotated? | Example |
| --- | --- | --- |
| **TYPE** | Class, interface, enum, or annotation type declaration | **@EntityTag class Order {}** |
| **FIELD** | Field declaration | **@FieldTag String name;** |
| **METHOD** | Method declaration | **@MethodTag String getName() { ... }** |
| **PARAMETER** | Method/constructor parameter declaration | **void send(@ArgTag String name)** |
| **CONSTRUCTOR** | Constructor declaration | **@CtorTag Service() {}** |
| **TYPE_PARAMETER** | Generic type parameter declaration, e.g., T in class Box<T> | **class Box<@ParamTag T> {}** |
| **TYPE_USE** | A type at a point of use, e.g., field type, generic argument, return type, cast | **List<@TypeTag String>** |

There are two subtleties in the JLS:

- **TYPE_USE is also permitted on a type parameter declaration** such as **class Box<@TypeTag T>**, despite the name “type use”. Therefore, TYPE_PARAMETER and TYPE_USE are not two completely disjoint sets of locations.
- **TYPE_USE also allows annotating type declarations** (for example, on a class). Therefore, you need to understand the JLS rules for type or type parameter declarations properly; you should not infer that TYPE_USE can *only* be used before a type argument.

The table above shows the intended purpose of each target, but it does not mean every program location is permitted to receive only one single kind of annotation. Overlapping regions must be considered.

## 4. On the Same Field Line: Declaration and Type Used

Consider:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface AuditField {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NotBlankType {}

class Profile {
    @AuditField
    @NotBlankType String username;
}
~~~

Assuming **Retention**, **RetentionPolicy**, **Target**, and **ElementType** have been imported from **java.lang.annotation**:

- **@AuditField** describes the field **username** itself.
- **@NotBlankType** describes **String** at that field's type position.
- An annotation on the String type of **username** does not automatically become an annotation on the **java.lang.String** declaration. If another field also uses String without attaching NotBlankType, it does not receive this annotation.

You can use reflection to read them separately:

~~~java
java.lang.reflect.Field field =
        Profile.class.getDeclaredField("username");

boolean declarationHasTag =
        field.isAnnotationPresent(AuditField.class);

boolean typeUseHasTag =
        field.getAnnotatedType()
                .isAnnotationPresent(NotBlankType.class);
~~~

When the annotations have **RUNTIME** retention, both variables above are **true**.

The API separation is crucial:

- **Field.getAnnotation(...)** or **Field.getDeclaredAnnotations()** queries annotations on **the field declaration**.
- **Field.getAnnotatedType()** returns an **AnnotatedType** representing **the field's type-use location**. You can call **getAnnotation(...)** on that AnnotatedType to read the annotation at that location.
- **Field.getType()** returns the Class representing the field's type. **field.getType().getAnnotation(NotBlankType.class)** queries the String class declaration, so it cannot be used to read an annotation placed on the type use of username.

You must distinguish between **AnnotatedElement** (field declaration) and **AnnotatedType** (type-use location), even though both have a similar **getAnnotation** API.

## 5. Methods: Method Annotations Differ from Return Type Annotations

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Endpoint {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface ResponseType {}

class Controller {
    @Endpoint
    @ResponseType String getStatus() {
        return "OK";
    }
}
~~~

**@Endpoint** marks **the getStatus method declaration**. **@ResponseType** marks **String used as the return type**. Reflection example:

~~~java
java.lang.reflect.Method method =
        Controller.class.getDeclaredMethod("getStatus");

boolean onMethod = method.isAnnotationPresent(Endpoint.class);
boolean onReturnType =
        method.getAnnotatedReturnType()
                .isAnnotationPresent(ResponseType.class);
~~~

If both annotations use runtime retention, both variables are **true**.

This distinction is useful when designing APIs: metadata meaning “this endpoint needs auditing” attaches to the **method declaration**; metadata meaning “the return value must satisfy a certain type property” attaches to the **return type use**. Both can appear before a return type, while their meaning is determined by the target and the interpreting tool.

If an annotation has both METHOD and TYPE_USE, when placed before the return type it can apply to both. In that case, a metadata-reading tool needs to check both **Method.getAnnotation(...)** and **Method.getAnnotatedReturnType().getAnnotation(...)**, depending on the information needed.

## 6. Parameters: PARAMETER Is Not the Same as TYPE_USE

For a method parameter:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface RequestArgument {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TrimmedType {}

class Handler {
    void handle(@RequestArgument @TrimmedType String input) {
    }
}
~~~

Here:

- **@RequestArgument** applies to the formal parameter declaration **input**.
- **@TrimmedType** applies to **the String type** of parameter input.

With reflection, they are read through two different paths:

~~~java
java.lang.reflect.Method method =
        Handler.class.getDeclaredMethod("handle", String.class);

boolean onParameter =
        method.getParameters()[0]
                .isAnnotationPresent(RequestArgument.class);

boolean onParameterType =
        method.getAnnotatedParameterTypes()[0]
                .isAnnotationPresent(TrimmedType.class);
~~~

Both expressions evaluate to **true** with runtime retention. There is no need to cast to String or search for metadata on **String.class**.

**ElementType.PARAMETER** is not **ElementType.TYPE_PARAMETER**. PARAMETER refers to a formal parameter entity such as **String input**; TYPE_PARAMETER refers to a type variable declared in generics such as **<T>**. Distinguish these three positions:

~~~java
class Converter<@TypeTag T> {
    T convert(T input) {
        return input;
    }
}
~~~

If TypeTag has the TYPE_USE target, **@TypeTag T** in **<T>** is valid because TYPE_USE also permits type parameter declarations. The **T** used as the return type of **convert** and the type of **input** are two **type uses**, which do not automatically receive annotations attached to the declaration of T. An annotation does not automatically propagate from a type variable declaration to every occurrence of that type variable.

## 7. Common Type-Use Contexts

To recognize TYPE_USE, pay attention to the position of a type inside a larger construct:

~~~java
import java.util.List;
import java.util.Map;

class Usage {
    List<@TypeTag String> names;

    Map<@TypeTag String, @TypeTag Integer> sizes;

    <T extends @TypeTag Number> void process(T input) {
        @TypeTag String label = input.toString();
        System.out.println(label);
    }

    Object raw = "sample";

    String cast() {
        return (@TypeTag String) raw;
    }

    @TypeTag String @TypeTag [] items;
}
~~~

The locations:

- **List<@TypeTag String>**: metadata on the type argument String.
- **Map<@TypeTag String, @TypeTag Integer>**: each type argument carries its own annotation.
- **T extends @TypeTag Number**: metadata on the bound type Number of generic T.
- **@TypeTag String label**: metadata on the String type of a local variable; type-use annotations can be stored as method metadata in the class file, but standard reflection does not provide a general API to read all local variable annotations.
- **(@TypeTag String) raw**: metadata on the String type used in a cast.
- **@TypeTag String @TypeTag [] items**: the annotation before String applies to the element type String; the annotation before the brackets applies to a dimension of the array type. These are different type paths.

**Note on arrays:** annotation placement matters. For multidimensional arrays, an @ before different **[]** pairs can refer to different array dimensions. To understand the metadata accurately, you need to inspect the **AnnotatedArrayType** structure or the type path information in the class file.

An annotation with only FIELD/METHOD/PARAMETER cannot be used at all of the type argument, type bound, or cast locations mentioned above. Only a type-use annotation declared with **@Target(TYPE_USE)** applies broadly to these locations.

## 8. Complete Java 17+ Program: Correctly Reading Both Kinds of Annotations

Create a single file **src/demo/DeclarationVsTypeUseDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface ParameterMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.TYPE_USE})
@interface DualMark {
    String value();
}

class Example {
    @FieldMark("field")
    @TypeMark("field-type")
    String name = "Ada";

    List<@TypeMark("list-item") String> aliases = List.of("Ada");

    @DualMark("both")
    String identifier = "U-01";

    @MethodMark("method")
    @TypeMark("return-type")
    String echo(
            @ParameterMark("parameter")
            @TypeMark("parameter-type")
            String input) {
        return input;
    }
}

public class DeclarationVsTypeUseDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Field name = Example.class.getDeclaredField("name");
        System.out.println("field declaration="
                + name.getAnnotation(FieldMark.class).value());
        System.out.println("field type="
                + name.getAnnotatedType()
                        .getAnnotation(TypeMark.class).value());

        Field aliases = Example.class.getDeclaredField("aliases");
        AnnotatedParameterizedType listType =
                (AnnotatedParameterizedType) aliases.getAnnotatedType();
        System.out.println("list item type="
                + listType.getAnnotatedActualTypeArguments()[0]
                        .getAnnotation(TypeMark.class).value());

        Field identifier = Example.class.getDeclaredField("identifier");
        System.out.println("dual declaration="
                + identifier.getAnnotation(DualMark.class).value());
        System.out.println("dual type="
                + identifier.getAnnotatedType()
                        .getAnnotation(DualMark.class).value());

        Method echo = Example.class.getDeclaredMethod(
                "echo", String.class);
        System.out.println("method declaration="
                + echo.getAnnotation(MethodMark.class).value());
        System.out.println("method return type="
                + echo.getAnnotatedReturnType()
                        .getAnnotation(TypeMark.class).value());
        System.out.println("parameter declaration="
                + echo.getParameters()[0]
                        .getAnnotation(ParameterMark.class).value());
        System.out.println("parameter type="
                + echo.getAnnotatedParameterTypes()[0]
                        .getAnnotation(TypeMark.class).value());
    }
}
~~~

From the directory containing **src**:

~~~bash
javac -encoding UTF-8 -d out src/demo/DeclarationVsTypeUseDemo.java
java -cp out demo.DeclarationVsTypeUseDemo
~~~

**Expected stdout:**

~~~text
field declaration=field
field type=field-type
list item type=list-item
dual declaration=both
dual type=both
method declaration=method
method return type=return-type
parameter declaration=parameter
parameter type=parameter-type
~~~

**Analysis:**

1. **name.getAnnotation(FieldMark.class)** reads metadata on the declaration of field **name**. **name.getAnnotatedType().getAnnotation(TypeMark.class)** reads metadata on the **String type** of that same field.
2. **aliases.getAnnotatedType()** represents **List<String>**; casting it to **AnnotatedParameterizedType** allows retrieving the annotation on **String** inside List, as opposed to an annotation on the outer List type.
3. **identifier** has DualMark with both FIELD and TYPE_USE. Because this annotation is written before the String type in the field declaration, both **Field.getAnnotation(DualMark.class)** and **Field.getAnnotatedType().getAnnotation(DualMark.class)** find DualMark. This is the case where **a single written annotation belongs to both forms** according to its target.
4. **echo.getAnnotation(MethodMark.class)** reads the annotation on the method declaration; **echo.getAnnotatedReturnType()** reads the annotation on the String type used as the return type.
5. **getParameters()[0]** returns the Parameter object, which is used to read the annotation on the formal parameter declaration; **getAnnotatedParameterTypes()[0]** reveals the annotation at the parameter's String type location.
6. All annotations in the example use **@Retention(RUNTIME)**. Without runtime retention, you cannot expect the reflection APIs above to return the corresponding metadata.

**Notes to make the program run:** Only the class **DeclarationVsTypeUseDemo** is public in the file; the annotations and helper classes are package-private top-level types. The **List** import uses the **List.of** API available since Java 9, so running with Java 17+ is appropriate. **ReflectiveOperationException** covers member lookup errors that may occur at compile time; all members used in the example exist, so the program prints the exact lines shown above.

## 9. Where Do Annotations Live in the Class File?

When an annotation has appropriate retention, the information is encoded in the class file, but **the storage and retrieval paths differ**.

A **declaration annotation** attached to a class, field, method, or parameter can reside in the corresponding class-file annotation attributes, such as **RuntimeVisibleAnnotations** for class/field/method or **RuntimeVisibleParameterAnnotations** for formal parameters.

A **type annotation** records additional metadata identifying **the type-use target** and **the path to the annotated part of the type** (*type path*), in attributes such as **RuntimeVisibleTypeAnnotations**. For example, an annotation on **List<@TypeMark String>** must specify that the annotation belongs to **String** as the first type argument, not the outer List.

With the compiled Java example, try:

~~~bash
javap -v -p out/demo/Example.class
~~~

In the output, you can locate the relevant metadata entries:

- **FieldMark** in the metadata of the **field declaration**.
- **TypeMark** in the **type annotation** metadata on the field type or type argument.
- **DualMark** can appear in both the field declaration annotations and the type-use annotations because @Target permits both.
- **MethodMark** on the method declaration; **TypeMark** on the return type or parameter type; **ParameterMark** on the formal parameter declaration.

Do not rely on specific constant pool numbers or indices displayed by **javap**: they may differ across compiler versions. The goal is to see that the metadata **is encoded under different target categories**.

With **@Retention(SOURCE)**, the annotation does not exist in the class file after compilation. With **@Retention(CLASS)**, it can be written into metadata that is not exposed through runtime reflection. This example chooses **RUNTIME** so that both can be observed via standard APIs.

## 10. Overlapping Locations and Exceptions to Remember

### 10.1. An Annotation Can Be Both a Declaration and a Type Annotation

JLS §9.7.4 gives the field example **@Foo int f**: if Foo applies to FIELD, then @Foo belongs to the declaration of **f**; if Foo applies to TYPE_USE, then @Foo belongs to the type **int**; if Foo has both targets, then **both receive the annotation**.

Similarly, the syntactic region where an annotation is placed immediately before a method return type, formal parameter type, field type, local variable type, or record component can serve as both a declaration modifier position and a type-use site. The valid target scope of the annotation determines how the metadata is interpreted. Therefore, an annotation declaring multiple targets can appear in more than one form at the same position.

Do not infer meaning from whitespace or whether the annotation is written on the same line or a different line: **@Target** and the syntactic structure are the deciding factors.

### 10.2. TYPE_PARAMETER, TYPE_USE, and Generic Declarations

~~~java
@Target(ElementType.TYPE_PARAMETER)
@interface GenericName {}

@Target(ElementType.TYPE_USE)
@interface TypePolicy {}

class Cache<@GenericName @TypePolicy K> {
    @TypePolicy K key;
}
~~~

- **@GenericName** applies only to **the type parameter declaration K**.
- **@TypePolicy** has TYPE_USE, so it is also valid on the declaration of K; TYPE_USE is defined to include type parameter declarations.
- **@TypePolicy K key** attaches to the use of K as a field type, not to another type parameter declaration.
- **GenericName** cannot replace TypePolicy on a field type or type argument because it does not have TYPE_USE.

An annotation on the declaration of K does not automatically propagate to all uses of K. If a library wants to propagate rules from a generic declaration to its type arguments, a tool with appropriate semantics is required.

### 10.3. TYPE_USE and Class Declarations

By definition in **ElementType** and the JLS, TYPE_USE includes type declaration contexts. An annotation with only TYPE_USE can still be written on a class declaration. Therefore, you cannot conclude that writing **@A class Service** implies A must have **@Target(TYPE)**: TYPE_USE is also a valid target for type declarations under the Java language.

However, this does not mean every type annotation at places where **Service** is used resides on the **Service** declaration itself. An annotation written at **List<@A Service>** attaches to **the location where Service is used as a generic argument**, and does not automatically modify the metadata of class Service.

## 11. Which Target Should You Choose When Designing an Annotation?

Some guidelines for choosing:

- If an annotation marks **a field for serialization, column mapping, auditing, or write protection**, and the meaning belongs to **the declared field**, the **FIELD** target usually expresses the intent more clearly.
- If an annotation marks **an endpoint, callback, or method that requires logging**, the meaning belongs to the **method declaration**, so the **METHOD** target is usually appropriate.
- If an annotation describes **how to bind a formal parameter** (for example, from an HTTP request), use the **PARAMETER** target when the parameter itself is the subject of the metadata.
- If an annotation expresses **a property of a type at each point of use** (for example, non-null, tainted, immutable), choose **TYPE_USE** to support generic arguments, field types, return types, casts, bounds, and other positions.
- If an annotation genuinely needs to represent both a declaration and a type use, declare both targets and verify your metadata-reading strategy. Especially for class/method/field, this decision can cause the same annotation to appear in both metadata groups.

Example:

~~~java
@Target(ElementType.TYPE_USE)
@interface NonNull {}

class Example {
    java.util.List<@NonNull String> names;
}
~~~

The annotation on **String** here is valid. However, a custom **@NonNull** does not cause the standard Java compiler to automatically reject null assignments. It is metadata; a type checker, annotation processor, or framework with its own rules is needed to turn that metadata into warnings or checks. This applies to both declaration and type-use annotations.

## 12. Common Mistakes and How to Verify

| Misconception or Error | Cause | How to Fix |
| --- | --- | --- |
| “An @ before String is definitely a FIELD annotation.” | This position is also a type use | Check the @Target of the annotation type |
| “TYPE_USE is only used in generic arguments.” | TYPE_USE covers many contexts, including returns, bounds, casts, and arrays | Consult JLS §4.11 |
| Applying an annotation with only FIELD to **List<@A String>** | A generic argument is not a field declaration | Use TYPE_USE |
| Applying an annotation with only METHOD to **@A String** inside a generic | This is not a method declaration | Use TYPE_USE |
| Using **field.getAnnotation(TypeMark.class)** to read an annotation on a type use | Reading the wrong reflection object | Use **field.getAnnotatedType()** |
| Using **field.getType().getAnnotation(TypeMark.class)** | Reading the class declaration of the type, not the type-use location | Use the field's **AnnotatedType** |
| Using **method.getAnnotation(...)** to read an annotation on the return type | The Method object represents the declaration | Use **method.getAnnotatedReturnType()** |
| Confusing PARAMETER and TYPE_PARAMETER | A formal parameter differs from a generic type variable | Use PARAMETER for method parameters, TYPE_PARAMETER for declaring T |
| Expecting reflection to return an annotation without RUNTIME retention | CLASS/SOURCE retention does not support standard runtime queries | Declare **@Retention(RUNTIME)** if actually needed |
| Placing a TYPE_USE annotation before a class and assuming it applies everywhere the class is used | Metadata belongs to each specific applied location | Query the appropriate declaration or AnnotatedType |
| Expecting a custom annotation to force the compiler to enforce non-null checks | Java does not interpret custom domain semantics of annotations on its own | Integrate an analysis tool or processing logic |

## 13. Self-Check Exercises

**Exercise 1.** Given an annotation type **@Target(FIELD)**, which statements are valid?

~~~java
class Product {
    @FieldMark("ok") String sku; // valid: field declaration
    // java.util.List<@FieldMark("x") String> ids; // invalid: type argument
}
~~~

Explanation: the FIELD annotation belongs to the declaration of sku; **String** in List is a type-use context and is not allowed by the FIELD target.

**Exercise 2.** Given an annotation type with only **@Target(TYPE_USE)**, can it be used in **List<@A String>** and **@A String field**? **Yes**: the first case annotates a generic argument, and the second annotates the String type of the field.

**Exercise 3.** Given **@Target({FIELD, TYPE_USE})**, when writing **@A String field**, can calling **Field.getAnnotation(A.class)** and **Field.getAnnotatedType().getAnnotation(A.class)** both find A? **Yes**, if A is retained until runtime and placed as described. This is the overlapping region defined by JLS §9.7.4.

**Exercise 4.** In **void handle(@ParameterMark("p") @TypeMark("t") String input)**, which query reads ParameterMark? **Method.getParameters()[0].getAnnotation(ParameterMark.class)**. Which query reads TypeMark? **Method.getAnnotatedParameterTypes()[0].getAnnotation(TypeMark.class)**.

**Exercise 5.** If **@Target(TYPE_USE)** is defined for the NonNull annotation and you only write **@NonNull String name**, does Java automatically forbid null assignment? **No**. The target specifies valid placement positions, whereas non-null semantics must be handled by an additional tool or processing code.

## 14. Official Java Sources

- **JLS Java 17 §9.7.4 — Where Annotations May Appear:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4 — directly states the rules distinguishing declaration annotations, type annotations, and the possibility that a single position belongs to both.
- **JLS Java 17 §4.11 — Where Types Are Used:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.11 — lists the type contexts accepted by Java.
- **Java SE 17 — ElementType:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html — defines FIELD, METHOD, PARAMETER, TYPE_PARAMETER, TYPE_USE, and other targets.
- **Java SE 17 — Field.getAnnotatedType():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#getAnnotatedType() — API for reading the type location of a field.
- **Java SE 17 — Method, AnnotatedType, and AnnotatedParameterizedType:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html and https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html

When analyzing an annotation on any line of Java, first identify **the declared entity** and **the type used on that line**, then check **@Target**. If you need to read metadata at runtime, choose the right **reflection API** for the declaration or for **AnnotatedType**. Placing the @ in the same way does not mean the metadata is stored and retrieved the same way.
