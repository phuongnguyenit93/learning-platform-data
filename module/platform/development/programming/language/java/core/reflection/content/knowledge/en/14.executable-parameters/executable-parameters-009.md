# getAnnotatedParameterTypes and getAnnotatedReceiverType in Java Reflection

## 1. What Do These Two Methods on `Executable` Read?

`Method` and `Constructor` both inherit from `java.lang.reflect.Executable`. Beyond APIs returning raw or generic types, `Executable` has two APIs for reading **annotations at type-use positions** (*type-use annotations*):

~~~java
AnnotatedType[] types = executable.getAnnotatedParameterTypes();
AnnotatedType receiver = executable.getAnnotatedReceiverType();
~~~

This is illustrative code given an existing `executable` variable of type `Executable`; classes from `java.lang.reflect` must be imported.

- **`getAnnotatedParameterTypes()`** returns an `AnnotatedType` array in the order of the executable's formal parameter types. It reflects annotations placed directly on the type or nested inside generic/array structures.
- **`getAnnotatedReceiverType()`** returns the `AnnotatedType` of the receiver type (`this` for an instance method, the enclosing instance for the constructor of a non-static inner member class), or `null` when the executable cannot have a receiver parameter.
- This is **metadata**, not an operation for invoking a method, creating an instance, granting access, or validating data automatically.

To be readable at runtime, the annotation must have `@Retention(RetentionPolicy.RUNTIME)`. Annotations with `SOURCE` or `CLASS` retention do not appear in the corresponding runtime queries.

## 2. Declaration Annotations vs. Type-Use Annotations

Java permits annotations on **parameter declarations** (`ElementType.PARAMETER`) and on **the type-use site itself** (`ElementType.TYPE_USE`).

~~~java
import java.lang.annotation.*;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface InputTag {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeTag {
    String value();
}

class Sample {
    void accept(@InputTag @TypeTag("list")
                List<@TypeTag("element") String> names) {}
}
~~~

The example above consists of declarations that can be placed in a single Java file; they do not yet have a standalone `main` method.

- `@InputTag` attaches to the **declaration of parameter `names`**. Read via `Parameter.getAnnotation(InputTag.class)` or `Executable.getParameterAnnotations()`.
- `@TypeTag("list")` attaches to **the `List` type at the parameter position**; read via `getAnnotatedParameterTypes()[0].getAnnotation(TypeTag.class)`.
- `@TypeTag("element")` attaches to **the type argument `String` inside `List<String>`**; you must descend into the `AnnotatedParameterizedType` tree.
- `getParameterTypes()[0]` returns raw class `List.class`, while `getGenericParameterTypes()[0]` yields generic type `List<String>`. Neither API replaces `getAnnotatedParameterTypes()` when inspecting type-use annotations.

Placing an annotation named `@NonNull`, `@Readonly`, or similar **does not automatically turn Reflection into a runtime checker**. Compiler plugins, static analyzers, or custom frameworks must interpret and enforce those rules.

## 3. The `AnnotatedType` Data Structure

`getAnnotatedParameterTypes()` returns one element per executable parameter. Each element is an `AnnotatedType` providing `getType()`, `getAnnotations()`, and `getAnnotation(...)`.

| API / Type | Reflected Information |
| --- | --- |
| `Class<?>[] getParameterTypes()` | Runtime/raw class types of parameters |
| `Type[] getGenericParameterTypes()` | Generic types, e.g., `List<String>`, `T`, wildcards |
| `AnnotatedType[] getAnnotatedParameterTypes()` | Type-use annotations on parameter types and nested structures |
| `Parameter[] getParameters()` | Per-parameter metadata, including declaration annotations and names if present |
| `Annotation[][] getParameterAnnotations()` | Declaration annotations on parameters |
| `AnnotatedType getAnnotatedReceiverType()` | Receiver type and annotations on the receiver |
| `AnnotatedType getAnnotatedReturnType()` | Type-use annotations on the return type |
| `AnnotatedType[] getAnnotatedExceptionTypes()` | Type-use annotations on types in `throws` |

Subtypes used when descending deeper:

- `AnnotatedParameterizedType` for `List<@Tag String>`: `getAnnotatedActualTypeArguments()`.
- `AnnotatedArrayType` for array types: `getAnnotatedGenericComponentType()`.
- `AnnotatedWildcardType` for wildcards: `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()`.
- `AnnotatedTypeVariable` for `T`: `getAnnotatedBounds()`.

Always use `instanceof` before casting. For instance, `int` can carry a type-use annotation yet is not an `AnnotatedParameterizedType`. `AnnotatedType.getType()` returns `Type`, which can be a `ParameterizedType` or `TypeVariable`, and cannot always be cast to `Class<?>`.

### Annotations Inside Generics Do Not Bubble Up

~~~java
AnnotatedType outer = method.getAnnotatedParameterTypes()[0];

if (outer instanceof AnnotatedParameterizedType p) {
    AnnotatedType inner = p.getAnnotatedActualTypeArguments()[0];
    TypeTag tag = inner.getAnnotation(TypeTag.class);
    if (tag != null) {
        System.out.println(tag.value());
    }
}
~~~

This is an excerpt using `method` and `TypeTag` in the context of the full example below. The annotation on `String` inside `List<String>` resides on a **child node of the type tree**, and does not appear directly in `outer.getAnnotations()`.

For arrays, `String @TypeTag("array") [] values` places the annotation at the **array level**. Annotation placement before the component type versus before the `[]` brackets has different meanings; for accurate analysis, traverse `AnnotatedArrayType`.

## 4. What Is a Receiver Parameter?

An instance method executes on a `this` object. Java allows explicitly declaring a **receiver parameter** to annotate the type of `this`:

~~~java
class Service {
    void process(@TypeTag("receiver") Service this,
                 @TypeTag("value") String value) {
        System.out.println(value);
    }
}
~~~

This is an illustrative snippet assuming annotation `TypeTag` is already defined with `@Target(TYPE_USE)`.

`Service this`:

- Must appear before the remaining formal parameters.
- **Is not an extra method-call parameter**: the `process` method only has **one** formal parameter, `String value`.
- Does not change `getParameterCount()`, `getParameterTypes()`, or lookup signature `getDeclaredMethod("process", String.class)`.
- Does not create a mechanism to reassign `this`, pass a new receiver in `args`, or alter overloading/dispatch.
- Provides a place to write type-use annotations so `getAnnotatedReceiverType()` can read them.

### Instance Methods Without an Explicit Receiver

**A very important point:** a normal instance method, even **without `Service this` in source**, still has a receiver type per the `Executable` API. Its `getAnnotatedReceiverType()` returns **a non-`null` `AnnotatedType`**, usually carrying no annotations.

Therefore, distinguish:

- `receiver == null`: the executable **cannot have** a receiver parameter, such as a static method.
- `receiver != null` and `receiver.getAnnotations().length == 0`: has a receiver type, but **no type-use annotations** are stored on the receiver.
- `receiver.getAnnotation(TypeTag.class) != null`: the receiver has the queried runtime annotation.

You cannot infer "no explicit receiver was written" solely from the result having no annotations.

## 5. Method Receivers vs. Constructor Receivers

| Executable Kind | Result of `getAnnotatedReceiverType()` |
| --- | --- |
| Instance method with receiver annotation | `AnnotatedType` carrying annotations on `this` type |
| Instance method without receiver annotation | Non-`null` `AnnotatedType`, usually with empty annotations |
| Static method | `null` |
| Top-level class constructor | `null` |
| Static nested/member class constructor | `null` |
| Local class or anonymous class constructor | `null` per Javadoc contract |
| **Non-static inner member class** constructor | `AnnotatedType` representing the enclosing instance receiver |

For inner classes, the syntax `Outer Outer.this` exists in constructor parameter lists to place annotations on **the enclosing instance receiver type**:

~~~java
class Outer {
    class Inner {
        Inner(@TypeTag("owner") Outer Outer.this,
              @TypeTag("text") String text) {}
    }
}
~~~

This is illustrative code with `TypeTag` in accessible scope. A non-static inner class needs an **enclosing instance** to be constructed. The compiler typically inserts a hidden parameter of type `Outer` into the **bytecode constructor signature**. Consequently, when looking up the constructor via Reflection, `Outer.class` may be needed before `String.class`.

**Do not conflate the two:** the explicit receiver parameter `Outer Outer.this` is a site to **annotate the type**, and does not itself create a new call parameter; the presence of the outer-instance argument on the constructor is a result of the inner class model.

## 6. Complete Java 17+ Example

Create the file **`AnnotatedExecutableDemo.java`**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.*;

public class AnnotatedExecutableDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface TypeTag {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface InputTag {}

    public static class Service {
        public Service() {}

        public void process(@TypeTag("receiver") Service this,
                            @InputTag @TypeTag("list")
                            List<@TypeTag("element") String> values,
                            @TypeTag("count") int count) {}

        public void plain(String value) {}

        public static void staticAction(
                @TypeTag("static") String value) {}
    }

    public static class Outer {
        public class Inner {
            public Inner(@TypeTag("owner") Outer Outer.this,
                         @TypeTag("label") String label) {}
        }
    }

    public static void main(String[] args) throws Exception {
        Method method = Service.class.getDeclaredMethod(
                "process", List.class, int.class);

        AnnotatedType[] parameters =
                method.getAnnotatedParameterTypes();

        System.out.println("parameters=" + parameters.length);
        System.out.println("raw0="
                + method.getParameterTypes()[0].getTypeName());
        System.out.println("declaration0="
                + method.getParameters()[0].isAnnotationPresent(
                        InputTag.class));
        System.out.println("type0="
                + parameters[0].getAnnotation(TypeTag.class).value());

        AnnotatedParameterizedType list =
                (AnnotatedParameterizedType) parameters[0];
        System.out.println("element="
                + list.getAnnotatedActualTypeArguments()[0]
                      .getAnnotation(TypeTag.class).value());

        System.out.println("type1="
                + parameters[1].getAnnotation(TypeTag.class).value());
        System.out.println("receiver="
                + method.getAnnotatedReceiverType()
                        .getAnnotation(TypeTag.class).value());

        Method plain = Service.class.getDeclaredMethod(
                "plain", String.class);
        System.out.println("plainReceiverPresent="
                + (plain.getAnnotatedReceiverType() != null));
        System.out.println("plainReceiverTags="
                + plain.getAnnotatedReceiverType().getAnnotations().length);

        Method staticMethod = Service.class.getDeclaredMethod(
                "staticAction", String.class);
        System.out.println("staticReceiverNull="
                + (staticMethod.getAnnotatedReceiverType() == null));

        Constructor<Service> ctor = Service.class.getConstructor();
        System.out.println("staticNestedCtorReceiverNull="
                + (ctor.getAnnotatedReceiverType() == null));

        Constructor<?> inner = Outer.Inner.class.getConstructor(
                Outer.class, String.class);
        System.out.println("innerReceiver="
                + inner.getAnnotatedReceiverType()
                       .getAnnotation(TypeTag.class).value());
        System.out.println("innerParameters="
                + inner.getParameterCount());
        System.out.println("innerParam0="
                + inner.getParameterTypes()[0].getSimpleName());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 AnnotatedExecutableDemo.java
java AnnotatedExecutableDemo
~~~

Stdout:

~~~text
parameters=2
raw0=java.util.List
declaration0=true
type0=list
element=element
type1=count
receiver=receiver
plainReceiverPresent=true
plainReceiverTags=0
staticReceiverNull=true
staticNestedCtorReceiverNull=true
innerReceiver=owner
innerParameters=2
innerParam0=Outer
~~~

**Explanation of each output group:**

1. `parameters=2` confirms that receiver `Service this` is not counted as a formal parameter of `process`. The two types used to look up the method are `List.class` and `int.class`.
2. `raw0=java.util.List` comes from `getParameterTypes()`; `declaration0=true` is the result of `@InputTag` on the parameter declaration.
3. `type0=list` is the annotation on `List` at the type-use position. `element=element` is the annotation on `String` nested inside the generic, read via `AnnotatedParameterizedType`.
4. `type1=count` shows that even primitive `int` can carry a type-use annotation.
5. `receiver=receiver` is the annotation on the explicitly declared receiver parameter.
6. `plainReceiverPresent=true` along with `plainReceiverTags=0`: an instance method without an explicit receiver still has an `AnnotatedType`, with no annotations.
7. `staticReceiverNull=true` and `staticNestedCtorReceiverNull=true`: static methods and constructors of static nested classes have no receiver type per the API.
8. `innerReceiver=owner` shows the annotation on the enclosing-instance receiver of the inner constructor.
9. `innerParameters=2`, `innerParam0=Outer` shows the `Outer` parameter inserted by the compiler into the bytecode constructor, followed by the `String` parameter declared in source.

The example uses APIs present in Java 17. The code was verified in practice using `javac --release 17` and run on JDK 24 with the exact stdout above.

## 7. Do Not Confuse Receiver Metadata with the Object Passed to `Method.invoke`

When using Reflection to invoke an instance method, the signature:

~~~java
Object result = method.invoke(receiver, args...);
~~~

accepts the **actual target object** in `receiver`, while `args` is the list of arguments matching the method's formal parameters.

Given `process(@TypeTag Service this, List<String> values, int count)`, an invocation could be:

~~~java
Method method = Service.class.getDeclaredMethod(
        "process", List.class, int.class);

Service service = new Service();
List<String> values = List.of("a", "b");
method.invoke(service, values, 5);
~~~

These snippets illustrate the scenario where `Service` is defined and checked exceptions are handled; they do not need to pass an extra argument for receiver parameter `Service this`. `service` is the runtime target value of `invoke`, whereas `getAnnotatedReceiverType()` only describes the **annotated receiver type**, and does not return the `service` object.

Receiver annotations also **do not alter** access rights, do not cause `Method.invoke` to automatically validate data based on annotations, and do not change overload selection.

## 8. Usage in Schema/Annotation-Reading Frameworks

A library analyzing executables can follow this workflow:

1. Obtain the exact `Method` or `Constructor` to analyze.
2. Iterate `getAnnotatedParameterTypes()` in order, reading annotations on each type and descending into generics/arrays/wildcards if needed.
3. If declaration annotations on parameters are wanted, use `getParameters()` or `getParameterAnnotations()` **separately**.
4. Call `getAnnotatedReceiverType()` and **check for `null` before reading annotations**.
5. For constructors of non-static inner member classes, inspect `getParameterTypes()` because a compiler-added outer-instance argument may appear.
6. If annotations on the return type or `throws` are needed, use `getAnnotatedReturnType()` / `getAnnotatedExceptionTypes()`.
7. Apply application rules (validation, schema, DI) in the next processing layer. Reflection only returns metadata.

### Common Mistakes

- **Treating `null` and an annotation-empty `AnnotatedType` as the same:** static methods typically return `null`, while regular instance methods return a non-`null` `AnnotatedType`.
- **Counting `this` as a formal parameter:** an explicit receiver parameter does not increase `getParameterCount()` of an instance method.
- **Using `getParameterAnnotations()` to read `List<@Tag String>`:** you must use `getAnnotatedParameterTypes()` and then inspect `AnnotatedParameterizedType`.
- **Skipping subtype checks:** casting every `AnnotatedType` to `AnnotatedParameterizedType` fails on primitives, arrays, or ordinary types.
- **Reading nested types via only outer `getAnnotations()`:** annotations on type arguments reside on child nodes.
- **Forgetting retention:** runtime Reflection cannot read annotations discarded at compile time.
- **Confusing `getAnnotatedReceiverType()` with access-control APIs:** it is unrelated to `canAccess` or `trySetAccessible`.
- **Thinking annotations automatically constrain data:** frameworks or analyzers must define semantics and enforce checks.
- **Guessing inner class constructors from source:** an outer-instance argument may exist in the runtime signature; always check parameter metadata.

## 9. Self-Check

**Question 1.** How many formal parameters does an instance method declared `void f(@Tag X this, String value)` have?  
**One** (`String value`). The receiver parameter is not in `getAnnotatedParameterTypes()`.

**Question 2.** Does an instance method without an explicit receiver declaration have `getAnnotatedReceiverType() == null`?  
**Usually no.** It returns an `AnnotatedType` representing the receiver, with empty annotations if there are no type-use annotations.

**Question 3.** Does a static method have a receiver type?  
**No**, `getAnnotatedReceiverType()` returns `null`.

**Question 4.** Where do you read the annotation on `String` inside `List<@Tag String>`?  
**`getAnnotatedParameterTypes()` → `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`**, then look up the element's annotation.

**Question 5.** Does `getParameterAnnotations()` return the same information as `getAnnotatedParameterTypes()`?  
**No.** The former reads declaration annotations, while the latter reads type-use annotations.

**Question 6.** Can a non-static inner class constructor return a receiver type?  
**Yes**; the receiver represents the enclosing instance of the outer class, even if the source constructor may not explicitly write a receiver annotation.

**Remember:** `getAnnotatedParameterTypes()` returns annotations on **parameter types**, whereas `getAnnotatedReceiverType()` returns annotations on the **receiver type**. The receiver is not an additional method-call parameter, and a `null` result must be distinguished from a receiver type with no annotations.

### Official References

- [JDK 17 — `java.lang.reflect.Executable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html)
- [JDK 17 — `java.lang.reflect.AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [JDK 17 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [JDK 17 — `Parameter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html)
- [JLS 17 §8.4.1 — Formal Parameters, Receiver Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1)
