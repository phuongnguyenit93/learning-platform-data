# Relationships Among Reflection, Inheritance, Generics, and Annotations in Java

## Learning Objectives

After this lesson, you will be able to explain **what reflection sees at runtime** when a class has a superclass, generic types, and annotations; choose the right API to read metadata; distinguish declaration metadata from actual behavior when invoking a method; and recognize common limitations when writing Java frameworks, libraries, or code-analysis tools.

Four related concepts with different roles:

| Concept | Role in a Program | What Reflection Can Observe |
| --- | --- | --- |
| **Inheritance** | Establishes parent–child class relationships; members can be inherited or overridden | Type hierarchy, declared/accessible members, declaring class of a member |
| **Generics** | Compile-time type checking; describes parameterized types | Erased runtime types and a portion of generic declaration information stored in metadata |
| **Annotations** | Attaches structured metadata to declarations or type-use positions | Annotations retained at runtime, depending on `@Retention` and the querying API |
| **Reflection** | Reads metadata and can dynamically operate on objects/members | `Class`, `Method`, `Field`, `Constructor`, `Type`, `Annotation` objects |

**Key point:** reflection does not replace inheritance rules, does not turn generics into full runtime type checking, and does not automatically execute the business meaning of annotations. It only provides a mechanism to observe or invoke members according to the rules Java has defined.

## 1. Inheritance Determines the Set of Members That Reflection Can See

### 1.1. Two Easily Confused API Groups

| Need | Representative API | Meaning |
| --- | --- | --- |
| Get `public` methods, including inherited ones | `clazz.getMethods()`, `clazz.getMethod(name, types...)` | Considers `public` methods of the type and `public` methods inherited from superclasses/interfaces |
| Get methods **declared directly** in the inspected class | `clazz.getDeclaredMethods()`, `clazz.getDeclaredMethod(...)` | Includes `private`, `protected`, package-private, and `public`; does not automatically walk up to superclasses |
| Get `public` fields, including inherited ones | `clazz.getFields()`, `clazz.getField(name)` | Does not include non-`public` fields |
| Get directly declared fields | `clazz.getDeclaredFields()`, `clazz.getDeclaredField(name)` | Does not automatically search superclass fields |
| Get constructors | `clazz.getConstructors()` or `clazz.getDeclaredConstructors()` | Only constructors of the class itself: **constructors are not inherited** |
| Inspect parent/interface relationships | `getSuperclass()`, `getInterfaces()` | Returns the direct superclass and direct interfaces |
| Preserve generic information of parent relationships | `getGenericSuperclass()`, `getGenericInterfaces()` | Returns `Type`, which may be a `ParameterizedType` or `Class` |

For example: if `Child extends Parent` and `Parent` has a method `public void ping()`, then `Child.class.getMethod("ping")` finds it, whereas `Child.class.getDeclaredMethod("ping")` throws `NoSuchMethodException` if `Child` does not redeclare `ping`. When searching for declared metadata across superclasses as well, traverse `getSuperclass()` and read `getDeclaredMethods()` level by level.

### 1.2. Overriding, Hiding, and Declaring Class Are Three Different Things

- **Overriding:** a matching instance method in a subclass overrides a superclass method. When using `Method.invoke(object, args)` for an instance method, Java still performs **dynamic dispatch** based on the actual type of the object; a `Method` obtained from the superclass can still invoke the overridden implementation in the subclass.
- **Overloading:** same name but different parameter list; reflection requires **exact parameter types** when calling `getMethod(name, parameterTypes...)`. You cannot rely on the method name alone.
- **Field hiding:** a field with the same name in a subclass *hides* the superclass field rather than dispatching polymorphically like methods. `Field.getDeclaringClass()` tells you which field is actually being read.
- **Static method hiding:** `static` methods are not overridden like instance methods; `Method.invoke` uses the declared static method rather than dispatching dynamically by object.
- **Accessibility:** finding a `private` member does not mean you are permitted to read/invoke it. `setAccessible(true)` or `trySetAccessible()` must obey access checks and module boundaries (JPMS).

The lists returned by `getMethods()` or `getDeclaredMethods()` **have no guaranteed order**. If you need stable display or code generation, sort them explicitly by a clear rule.

## 2. Generics: Declaration Metadata Remains, While Type Arguments Are Mostly Erased at Runtime

### 2.1. Type Erasure Directly Affects Reflection

In Java, `List<String>` and `List<Integer>` typically share the same raw runtime class `List`/`ArrayList`. You cannot ask a `new ArrayList<String>()` object to reliably give back `String` from `object.getClass()` alone. The compiler checks generics, inserts casts where needed, and erases most type-argument information in the runtime representation.

However, **declarations** can retain a generic signature:

- `Field.getType()` returns the `Class<?>` of the erased type, whereas `Field.getGenericType()` returns a `Type` that may contain `List<String>`.
- `Method.getReturnType()` and `getParameterTypes()` return the erased types; `getGenericReturnType()` and `getGenericParameterTypes()` return the declared generic types.
- `Class.getSuperclass()` returns the raw superclass, whereas `Class.getGenericSuperclass()` can preserve a relationship such as `Parent<String>`.
- `Class.getTypeParameters()` and `Method.getTypeParameters()` return type variables like `T`, `E` declared on the class/method.

Do not equate `Type` with `Class<?>`. Important forms of `Type`:

| Form | Declaration Example | Meaning |
| --- | --- | --- |
| `Class<?>` | `String`, `int[]` | A concrete type that is not parameterized in that representation |
| `ParameterizedType` | `List<String>` | A raw type together with its actual type arguments |
| `TypeVariable<?>` | `T` in `class Box<T>` | A type variable and its bounds |
| `WildcardType` | `? extends Number` | A wildcard and its upper/lower bounds |
| `GenericArrayType` | `T[]` | An array type whose component is a generic type not yet resolved to a concrete `Class` |

### 2.2. Generics on a Superclass vs. Generics on a Superclass Method

Suppose `class Parent<T> { T read(); }` and `class Child extends Parent<String>`. When calling `Child.class.getGenericSuperclass()`, the metadata of the *extends relationship* may contain `String`. However, `Parent.class.getDeclaredMethod("read").getGenericReturnType()` is still the type variable `T` declared by `Parent`: reflection **does not automatically substitute `T` with `String` in `Parent`'s own metadata**.

A tool that needs to infer the actual return type of `read` in the context of `Child` must build a `T -> String` mapping itself and apply that mapping across each inheritance level (possibly through multiple classes and interfaces). With raw type declarations or when generic information is no longer retained, inference does not always succeed.

### 2.3. Bridge Methods Are the Intersection of Inheritance and Erasure

To preserve overriding when signatures are erased, the compiler may generate a **bridge method**. For instance, `Parent<T>.convert(T)` has the erased parameter `Object`, while `Child extends Parent<String>` overrides it with `convert(String)`. The compiler generates a bridge such as `convert(Object)` in `Child` so that calls through type `Parent` still reach the `convert(String)` implementation.

Reflection can see both the source method and the bridge method in `getDeclaredMethods()`. When scanning methods to build APIs, routing, logging, or validation, you often need to check `Method.isBridge()` and `Method.isSynthetic()` to avoid duplicate registration. However, when invoking methods, do not delete or alter bridge methods: they exist for compatibility and JVM dispatch.

## 3. Annotations: Class or Member Metadata Have Their Own Inheritance Rules

### 3.1. Retention and Target Must Be Appropriate

- `@Retention(SOURCE)`: the annotation exists only in source code and is absent from the class file.
- `@Retention(CLASS)`: present in the class file, but **not accessible via standard runtime reflection**; this is the default if `@Retention` is omitted.
- `@Retention(RUNTIME)`: can be queried via Reflection APIs while the program is running.
- `@Target(TYPE)` applies to type declarations; `METHOD`, `FIELD`, `PARAMETER` apply to each respective member kind; `TYPE_USE` is for **type-use positions** such as `List<@Checked String>`.

Annotations only declare data. For example, `@Audit` does not automatically write logs; code must actively look up the annotation and perform the corresponding behavior.

### 3.2. `@Inherited` Has a Narrow Scope

`@Inherited` is placed **on the annotation type declaration**, and only takes effect when querying annotations on the **class declaration** of a subclass; Java searches along the superclass chain if the subclass does not declare that annotation.

Therefore:

- `Child.class.getAnnotation(Audited.class)` can receive the `@Audited` annotation from a superclass if `Audited` is marked with `@Inherited`.
- `Child.class.getDeclaredAnnotation(Audited.class)` inspects only `Child`, so it may be `null`.
- `@Inherited` **does not propagate annotations from interfaces that a class implements**, does not apply automatically to annotations on methods/fields/constructors, and does not cause a superclass method's annotation to appear on an overriding method.
- To handle annotations on interfaces, overridden methods, or application-defined meta-annotations, a framework must actively traverse the hierarchy and define metadata-merging rules.

For repeatable annotations (`@Repeatable`), use `getAnnotationsByType(...)` / `getDeclaredAnnotationsByType(...)` when you want to retrieve multiple values; avoid assuming `getAnnotation(...)` always represents all repeated annotations.

### 3.3. Declaration Metadata and Type-Use Metadata Are Different

For example, in the field `List<@Checked String> names`: the `@Checked` annotation belongs to the **type argument `String`**, not directly to the field declaration `names`. Therefore, `Field.getAnnotation(Checked.class)` does not read it; you must use `Field.getAnnotatedType()`, validly cast it to `AnnotatedParameterizedType`, and access `getAnnotatedActualTypeArguments()`.

Similarly, Java provides `Method.getAnnotatedReturnType()`, `getAnnotatedParameterTypes()`, and `Class.getAnnotatedSuperclass()` when annotations in type-use positions are needed. These annotations must also have `RUNTIME` retention to be observable via reflection.

## 4. Integrated Java 17+ Example: Inheritance + Generics + Annotations + Reflection

Save the following as **KnowledgeReflectionDemo.java**. The program uses a generic superclass, a subclass specializing the type `String`, a class annotation marked `@Inherited`, and an annotation placed on a superclass method.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.util.Arrays;
import java.util.Locale;

public class KnowledgeReflectionDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Audited {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Label {
        String value();
    }

    @Audited
    static class Parent<T> {
        @Label("parent")
        public T convert(T input) {
            return input;
        }

        public String ping() {
            return "parent";
        }
    }

    static class Child extends Parent<String> {
        @Override
        public String convert(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws Exception {
        Class<Child> type = Child.class;

        System.out.println("Inherited annotation: "
                + type.isAnnotationPresent(Audited.class));
        System.out.println("Declared annotation: "
                + (type.getDeclaredAnnotation(Audited.class) != null));

        ParameterizedType parentType =
                (ParameterizedType) type.getGenericSuperclass();
        System.out.println("Actual parent argument: "
                + parentType.getActualTypeArguments()[0].getTypeName());

        Method parentMethod = Parent.class.getMethod("convert", Object.class);
        Method childMethod = Child.class.getDeclaredMethod("convert", String.class);
        System.out.println("Base method generic return: "
                + parentMethod.getGenericReturnType().getTypeName());
        System.out.println("Child override has @Label: "
                + childMethod.isAnnotationPresent(Label.class));
        System.out.println("Parent method label: "
                + parentMethod.getAnnotation(Label.class).value());

        Method inherited = type.getMethod("ping");
        System.out.println("Inherited method declared by Parent: "
                + (inherited.getDeclaringClass() == Parent.class));

        long bridges = Arrays.stream(type.getDeclaredMethods())
                .filter(Method::isBridge)
                .count();
        System.out.println("Bridge methods in Child: " + bridges);

        Object result = parentMethod.invoke(new Child(), "java");
        System.out.println("Reflective call result: " + result);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac KnowledgeReflectionDemo.java
java KnowledgeReflectionDemo
~~~

Output:

~~~text
Inherited annotation: true
Declared annotation: false
Actual parent argument: java.lang.String
Base method generic return: T
Child override has @Label: false
Parent method label: parent
Inherited method declared by Parent: true
Bridge methods in Child: 1
Reflective call result: JAVA
~~~

**Explanation of observations:**

1. `Audited` is marked `@Inherited`, so querying `Child` sees `Parent`'s annotation, while a *declared* query on `Child` does not.
2. The metadata `Child extends Parent<String>` retains the argument `java.lang.String`. Conversely, the declared return type of `Parent.convert(T)` remains `T`.
3. `@Label("parent")` exists on `Parent`'s method; `Child.convert(String)` does not automatically inherit the annotation of the overridden method.
4. `ping()` is an inherited `public` method; `getMethod("ping")` retrieves a `Method` whose `getDeclaringClass() == Parent.class`.
5. The bridge `convert(Object)` lets calls through type `Parent` reach `Child.convert(String)`. Because `Method.invoke` on an instance applies dynamic dispatch, the result is `JAVA` even though the `Method` was obtained from `Parent`.

Note: `getDeclaredMethods()` may contain both source methods and bridge/synthetic methods; do not rely on array element order to infer which method to use.

## 5. Separate Example of a Generic Field and a Type-Use Annotation

The previous example used annotations on **class/method declarations**. This example clarifies a field with a generic signature and an annotation **on a type argument**. Save as **TypeUseDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.util.List;

public class TypeUseDemo {
    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Checked {}

    static class Input {
        List<@Checked String> names;
    }

    public static void main(String[] args) throws Exception {
        Field field = Input.class.getDeclaredField("names");
        ParameterizedType genericType =
                (ParameterizedType) field.getGenericType();
        AnnotatedParameterizedType annotatedType =
                (AnnotatedParameterizedType) field.getAnnotatedType();

        System.out.println("Raw field type: "
                + field.getType().getTypeName());
        System.out.println("Type argument: "
                + genericType.getActualTypeArguments()[0].getTypeName());
        System.out.println("Type-use annotation: "
                + annotatedType.getAnnotatedActualTypeArguments()[0]
                        .isAnnotationPresent(Checked.class));
    }
}
~~~

~~~bash
javac TypeUseDemo.java
java TypeUseDemo
~~~

~~~text
Raw field type: java.util.List
Type argument: java.lang.String
Type-use annotation: true
~~~

`getType()` sees only the erased `List`, `getGenericType()` sees `String` on the field declaration, and `getAnnotatedType()` accesses annotations on type-use positions. None of these steps proves that every element placed into the list at runtime is actually a `String`; that remains the responsibility of the type system and data-validation logic.

## 6. Applying This When Building Reflection-Based Tools

Consider a library that needs to find methods annotated with `@Action` on an object with multiple superclasses. A verifiable workflow:

1. **Define the desired inheritance rules.** Read only accessible `public` methods via `getMethods()`, or scan all declarations level by level via `getDeclaredMethods()`? Should annotations on overridden methods be *actively* pulled from parent methods?
2. **Traverse types deliberately.** When using `getDeclaredMethods()`, walk superclasses sequentially with `getSuperclass()`; inspect interfaces separately if required. Record `getDeclaringClass()` to identify the metadata source.
3. **Handle bridge/synthetic methods and overrides.** Check `isBridge()`/`isSynthetic()`, and compare name + parameter types + override relationships to avoid registering the same behavior twice. Do not assume all methods with the same name are the same.
4. **Read annotations by location.** `getDeclaredAnnotation()` only gets direct annotations; `getAnnotation()` on a class may respect `@Inherited`; for parent methods/interfaces, you must define your own lookup algorithm. Annotations attached to generic type arguments require the `AnnotatedType` API.
5. **Resolve generic types in context.** First inspect `Type` with `instanceof`; if you encounter a `TypeVariable`, traverse the `ParameterizedType` relationships between the concrete class and the declaring class and substitute type variables according to the mapping, including nested and multi-level generic cases.
6. **Execute under control.** Check modifiers, access permissions, parameters, receiver type, and potential exceptions. `Method.invoke` can throw `IllegalAccessException`, `IllegalArgumentException`, or `InvocationTargetException` (wrapping errors from the target method itself). In Java modules, opening `private` members may be denied.
7. **Choose and test conflict policies.** If both subclass and superclass methods have annotations, specify which takes precedence; if an interface has annotations, include them only when business rules specify; if an annotation is repeatable, handle all applicable values.

**Practical example:** a data-mapping framework looks at `Field.getGenericType()` to infer the element type of `List<User>`, inspects annotations on the field or on `User` to decide conversion, and then selects an appropriate `public` setter or constructor. If an entity class inherits from a parent entity, the framework must decide whether to scan parent fields and how to handle hidden fields. Reflection provides the data for decisions; the framework itself owns those rules.

## 7. Common Misconceptions and How to Self-Check

| Misconception | Reality / How to Verify |
| --- | --- |
| "`getDeclaredMethods()` includes every usable method of an object." | It returns only methods declared in the `Class` under inspection; for inherited members, use `getMethods()` or walk superclasses. |
| "A `Method` from a superclass always runs the superclass method body." | For overridden instance methods, `invoke` still dispatches dynamically by receiver. Static methods behave differently. |
| "Reflection can retrieve `T=String` from any generic object." | Type erasure removes much runtime information; `extends Parent<String>` relationship metadata only resolves certain contexts. |
| "`@Inherited` applies to methods and interfaces." | It applies only to annotations **on classes** looked up via **superclasses**. |
| "Not finding an annotation means the annotation does not exist in code." | The annotation may lack `RUNTIME` retention, be on a parent method, or sit on a type-use position rather than the declaration. |
| "Every method in `getDeclaredMethods()` corresponds to one source method." | The compiler may add bridge/synthetic methods. |
| "`setAccessible(true)` can always open private members." | Access checks, JPMS modules, and runtime policies can reject it. |
| "Having an annotation makes the feature run automatically." | There must be code that reads the annotation and implements the behavior. |

To self-check, answer three questions: (a) how do `getMethod` and `getDeclaredMethod` differ when a method exists only in a superclass? (b) why does `Parent<T>.convert(T)` still have generic return type `T` even though `Child extends Parent<String>`? (c) why does `@Inherited` produce different results between `Child.class.getAnnotation(...)` and `Child.class.getDeclaredAnnotation(...)`? If you can explain all three using the example above, you have mastered the boundary between declaration metadata, inheritance relationships, and runtime behavior.

### Official API Documentation

- Java SE 21, `Class`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- Java SE 21, `Method`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 21, `Inherited`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Inherited.html