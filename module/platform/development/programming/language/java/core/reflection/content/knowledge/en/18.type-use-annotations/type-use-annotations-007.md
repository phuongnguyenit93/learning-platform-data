# getAnnotatedReturnType, getAnnotatedExceptionTypes, and Receiver Type in Java Reflection

When learning Java Reflection, reading a method's metadata does not stop at `getReturnType()` or `getExceptionTypes()`. Java also allows attaching annotations directly to **type-use positions**, such as annotations on the return type, exception types in the `throws` clause, or the `this` type of an instance method.

Three important APIs on `java.lang.reflect.Executable` are:

- `getAnnotatedReturnType()`: reads **the return type use** along with its type-use annotations.
- `getAnnotatedExceptionTypes()`: reads **the exception type uses in `throws`**, preserving declaration order and annotations at each position.
- `getAnnotatedReceiverType()`: reads **the receiver type** (the type of `this` per language rules), including annotations on an *explicit receiver parameter* when present; the result may be `null` if the executable cannot have a receiver parameter.

All three work with `AnnotatedType` or `AnnotatedType[]`; **there is no need to invoke the target method** to obtain this information. They describe declaration-time metadata and **do not** automatically enforce any business validation on the annotations.

## 1. Conditions to read type-use annotations at runtime

An annotation targeting a **type-use** position must allow `ElementType.TYPE_USE`. For Reflection to see it at runtime, `RetentionPolicy.RUNTIME` is also required:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface Mark {
    String value();
}
```

The snippet above is an **illustrative declaration**; the standalone program below will declare the `Mark` annotation inside its own class.

`@Target(TYPE_USE)` allows syntax such as:

```java
public @Mark("result") String read() { return "ok"; }
public void save() throws @Mark("io") java.io.IOException {}
```

These two lines only illustrate type-use positions; they are not a standalone runnable program, and method `save` does not throw `IOException` even though it declares `throws`. Java permits declaring a checked exception without the method body necessarily throwing that exception.

**Distinction:** an annotation attached to **a method declaration** with `ElementType.METHOD` is read via `Method.getAnnotation` or `getDeclaredAnnotations()`. An annotation attached to **a return type** requires `getAnnotatedReturnType()`. Similarly, an annotation on a **parameter declaration** differs from an annotation on **the parameter's type**. Do not infer that `Method.getAnnotations()` returns every annotation inside a generic return type or a `throws` clause.

## 2. Overview of `Executable` APIs

`Executable` is the superclass of `Method` and `Constructor`. It provides APIs for parameter lists, exceptions, receivers, and annotated types.

| Question | API | Reflection return type |
| --- | --- | --- |
| What type does the method return after erasure? | `Method.getReturnType()` | `Class<?>` |
| What generic structure does the return type have? | `Method.getGenericReturnType()` | `Type` |
| Where are type-use annotations on the return type? | `Method.getAnnotatedReturnType()` | `AnnotatedType` |
| Which exception types are in `throws`? | `Executable.getExceptionTypes()` | `Class<?>[]` |
| What generic declarations do the exception types have? | `Executable.getGenericExceptionTypes()` | `Type[]` |
| Annotations on each exception type in `throws`? | `Executable.getAnnotatedExceptionTypes()` | `AnnotatedType[]` |
| Which annotations does the receiver type have? | `Executable.getAnnotatedReceiverType()` | `AnnotatedType` or `null` |
| Type-use annotations on formal parameter types? | `Executable.getAnnotatedParameterTypes()` | `AnnotatedType[]` |

Each `AnnotatedType` represents a **node in the type-use tree**. The `getType()` method returns the underlying `Type`, while `getAnnotation(SomeAnnotation.class)` reads the annotation located **right at that node**. If the annotation sits on a deeper type argument or bound, you must step into child nodes using specialized APIs such as `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`.

This is not a runtime value evaluator: `getAnnotatedExceptionTypes()` does not wait for the method to throw an exception, and `getAnnotatedReturnType()` does not wait for the method to return a value.

## 3. getAnnotatedReturnType(): annotations on the return type

Suppose a method declares:

```java
public @Mark("result") List<@Mark("element") String> read() {
    return List.of("ok");
}
```

This is an illustrative snippet in a context where `List` and `Mark` exist.

- `method.getReturnType()` returns `List.class` (generics are **erased**).
- `method.getGenericReturnType()` represents `List<String>` with generic parameters, but does not directly expose annotations at each position.
- `method.getAnnotatedReturnType()` represents **the use of `List<String>`**; on the outer node there is `@Mark("result")`.
- Because the outer type is parameterized, you can use `AnnotatedParameterizedType` and `getAnnotatedActualTypeArguments()[0]` to reach the **`String`** node; that is where `@Mark("element")` sits.

Example metadata access path:

```java
Method method = Service.class.getDeclaredMethod("read");
AnnotatedType returnUse = method.getAnnotatedReturnType();
Mark outer = returnUse.getAnnotation(Mark.class);

if (returnUse instanceof AnnotatedParameterizedType pt) {
    AnnotatedType stringUse =
            pt.getAnnotatedActualTypeArguments()[0];
    Mark inner = stringUse.getAnnotation(Mark.class);
}
```

This snippet requires `import java.lang.reflect.*`, declared `Service` and `Mark`, and handling `NoSuchMethodException`; a complete runnable example is in section 6.

**Remember:** `getAnnotatedReturnType()` still returns an `AnnotatedType` for a method with no annotations on its return type. An empty `getAnnotations()` array only means the current node carries no reflected annotations, not that no return type exists.

For a `void ping()` method, the return type is still represented by `void.class`; `getAnnotatedReturnType().getType()` represents `void`. It is **not** `null` or `Void.class`.

`Executable.getAnnotatedReturnType()` also applies to **constructors**, though with different semantics: the `AnnotatedType` object represents **the type of the constructed object**, rather than a return type declared like a method. You cannot call `getReturnType()` on `Constructor`, because that method belongs to `Method`, not `Constructor`.

## 4. getAnnotatedExceptionTypes(): annotations in throws

Example of a method declaration:

```java
public void load()
        throws @Mark("io") IOException,
               @Mark("state") IllegalStateException {
}
```

This snippet illustrates a method declaration, assuming `IOException` and `Mark` are imported. Even though the method body is empty, the two types appearing in the `throws` clause remain readable metadata.

`method.getAnnotatedExceptionTypes()` returns **`AnnotatedType[]` in the exact order the exception types are listed in the `throws` clause**:

| Index | Element's `getType()` | Annotation at element |
| --- | --- | --- |
| `0` | `java.io.IOException` | `@Mark("io")` |
| `1` | `java.lang.IllegalStateException` | `@Mark("state")` |

Contrast:

- `getExceptionTypes()` returns `Class<?>[]`, reporting the declared exception classes without carrying type-use annotation metadata directly in the `Class` elements.
- `getGenericExceptionTypes()` returns `Type[]` when general type information is needed, such as a type variable like `E extends Exception` in `throws E`.
- `getAnnotatedExceptionTypes()` returns `AnnotatedType[]`, allowing annotations to be read on each exception type use, and when applicable allowing traversal of `AnnotatedTypeVariable` forms.

**Very important limitation:** This array contains the exception types **declared in `throws`**, not the list of all actual errors that could occur when the method runs. A method with `throws IOException` that never throws it still returns metadata; conversely, a method without `throws` can still throw a `RuntimeException` or `Error`. If there are no exception types in `throws`, the resulting array has length **0**, not `null`.

The `AnnotatedType[]` array of exception types preserves **declaration order**, unlike certain Reflection APIs returning arrays of methods/fields whose order is not guaranteed to match source order.

## 5. What is a receiver type? Why is it different from a normal parameter?

For an instance method, the **receiver** is the object on which the method will execute, usually referred to as `this`. Java allows writing an **explicit receiver parameter** to attach type-use annotations to the receiver type:

```java
class Service {
    public void action(@Mark("receiver") Service this) {
        // this is the object receiving the action() call.
    }
}
```

This is an illustrative snippet in a context where `Mark` is declared. A receiver parameter has syntax resembling a parameter in the signature, yet it is **not** a formal parameter carrying an independent value passed by the caller. In the example:

- `action()` is still invoked as `service.action()`, **without passing an extra argument** for `this`.
- `Method.getParameterCount()` of `action` remains **0**.
- `Method.getParameterTypes()` and `getAnnotatedParameterTypes()` do not add an element for the explicit receiver.
- `getAnnotatedReceiverType()` provides the `AnnotatedType` that can contain `@Mark("receiver")`.
- Adding a receiver parameter does not change the method's overload signature and does not allow calling a static method with a receiver.

For an annotated `read(@Mark("receiver") Service this)` method, we can read:

```java
AnnotatedType receiverUse = method.getAnnotatedReceiverType();
Mark tag = receiverUse.getAnnotation(Mark.class);
```

**Cases to distinguish** according to the JDK 21 contract:

| Executable kind | `getAnnotatedReceiverType()` |
| --- | --- |
| Instance method with explicit receiver annotation | An `AnnotatedType` containing annotations on the receiver type |
| Instance method without a written receiver parameter (or with an unannotated receiver) | Still an `AnnotatedType`, but **without annotations** on the receiver |
| Static method | `null` because it cannot have a receiver parameter |
| Constructor of a top-level class or static member class | `null` |
| Constructor of a non-static inner member class | May return an `AnnotatedType` representing **the enclosing receiver type**, even without an explicit receiver annotation |
| Constructor of a local/anonymous class | `null` per the API contract |

Therefore, **`getAnnotatedReceiverType() == null` does not mean "no annotation was written"**. An instance method without a written explicit receiver still returns an *unannotated* `AnnotatedType`; whereas a static method returns `null` because it has no receiver due to the executable kind. Conversely, an unannotated `AnnotatedType` does not prove that an explicit receiver parameter was declared in source.

For an inner-class constructor, the receiver syntax rules differ from a normal instance method (the receiver refers to the enclosing instance), so you cannot mechanically write `Inner this` as with a method. Consult the JLS if you need to analyze constructor receivers in detail.

**Receiver type is not the runtime type of a concrete object:** `getAnnotatedReceiverType()` describes the declared receiver type; it does not inspect `receiver.getClass()` at runtime, nor does it alter dynamic dispatch.

## 6. Complete, runnable Java 17+ example

Create the file `AnnotatedExecutableDemo.java`:

```java
import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Method;
import java.util.List;

public class AnnotatedExecutableDemo {
    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface Mark {
        String value();
    }

    public static class Service {
        public @Mark("result") List<@Mark("element") String> read(
                @Mark("receiver") Service this)
                throws @Mark("io") IOException,
                       @Mark("state") IllegalStateException {
            return List.of("ok");
        }

        public String plain() {
            return "plain";
        }

        public static void ping() {}

        public void noThrows() {}

        public Service() {}
    }

    private static String mark(AnnotatedType type) {
        if (type == null) {
            return "null";
        }
        Mark ann = type.getAnnotation(Mark.class);
        return ann == null ? "none" : ann.value();
    }

    public static void main(String[] args) throws Exception {
        Method read = Service.class.getDeclaredMethod("read");

        AnnotatedType ret = read.getAnnotatedReturnType();
        System.out.println(
                "return.raw=" + read.getReturnType().getTypeName()
        );
        System.out.println("return.tag=" + mark(ret));

        AnnotatedType elem =
                ((AnnotatedParameterizedType) ret)
                .getAnnotatedActualTypeArguments()[0];
        System.out.println(
                "return.argument="
                + elem.getType().getTypeName() + ":" + mark(elem)
        );

        AnnotatedType[] exceptions =
                read.getAnnotatedExceptionTypes();
        System.out.println("exceptions=" + exceptions.length);

        for (int i = 0; i < exceptions.length; i++) {
            System.out.println(
                    "throws[" + i + "]="
                    + exceptions[i].getType().getTypeName()
                    + ":" + mark(exceptions[i])
            );
        }

        AnnotatedType receiver = read.getAnnotatedReceiverType();
        System.out.println("receiver.tag=" + mark(receiver));
        System.out.println(
                "receiver.type="
                + ((Class<?>) receiver.getType()).getSimpleName()
        );
        System.out.println(
                "receiver.isFormalParameter=" + read.getParameterCount()
        );

        Method plain = Service.class.getDeclaredMethod("plain");
        System.out.println(
                "plain.receiver.tag="
                + mark(plain.getAnnotatedReceiverType())
        );

        Method ping = Service.class.getDeclaredMethod("ping");
        System.out.println(
                "static.receiver=" + mark(ping.getAnnotatedReceiverType())
        );
        System.out.println(
                "static.return.type="
                + ping.getAnnotatedReturnType().getType().getTypeName()
        );

        Method noThrows = Service.class.getDeclaredMethod("noThrows");
        System.out.println(
                "noThrows=" + noThrows.getAnnotatedExceptionTypes().length
        );

        System.out.println(
                "constructor.receiver="
                + mark(Service.class.getDeclaredConstructor()
                        .getAnnotatedReceiverType())
        );
    }
}
```

Compile and run from the directory containing the file:

```bash
javac AnnotatedExecutableDemo.java
java AnnotatedExecutableDemo
```

Expected output on Java 17+:

```text
return.raw=java.util.List
return.tag=result
return.argument=java.lang.String:element
exceptions=2
throws[0]=java.io.IOException:io
throws[1]=java.lang.IllegalStateException:state
receiver.tag=receiver
receiver.type=Service
receiver.isFormalParameter=0
plain.receiver.tag=none
static.receiver=null
static.return.type=void
noThrows=0
constructor.receiver=null
```

Explanation:

1. `getReturnType()` gives `List.class` after erasure. `getAnnotatedReturnType()` preserves `@Mark("result")` at the outer node of the return type.
2. `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]` descends to `String` to find `@Mark("element")`, rather than mixing container and element annotations.
3. `getAnnotatedExceptionTypes()` returns the two types `IOException` and `IllegalStateException` in declaration order, with values `io` and `state` respectively.
4. `read`'s `getAnnotatedReceiverType()` retains the `receiver` annotation on `Service this`. The receiver's underlying class has simple name `Service`.
5. `getParameterCount() == 0` proves that an explicitly declared receiver is **not** a formal parameter that callers must pass.
6. `plain()` is an instance method without an explicit receiver written: the API still returns an `AnnotatedType`, but without a `Mark` annotation, so the label is `none`.
7. `ping()` is a static method: receiver type is `null`; return type is `void`.
8. `noThrows()` has no `throws`: the `getAnnotatedExceptionTypes()` array is empty.
9. Constructor `Service()` belongs to a **static member class**, so it has no enclosing-instance receiver and `getAnnotatedReceiverType()` returns `null`.

The program only reads metadata; it does not call `read()` or `plain()`, and does not need to instantiate `Service`. Each method is looked up by exact name, so it does not depend on the ordering of `getDeclaredMethods()`.

## 7. If the return/exception type is generic or compound

`AnnotatedType` is a family of interfaces. Reading annotations on the **outer node** with `getAnnotation` is insufficient if annotations sit on inner components.

For a return type with generic arguments:

```java
public List<@Mark("item") String> items() {
    return List.of();
}
```

You need to check `getAnnotatedReturnType() instanceof AnnotatedParameterizedType`, then iterate `getAnnotatedActualTypeArguments()` to retrieve the annotation on `String`.

When the return type is an array, wildcard, or type variable, the other branches of the `AnnotatedType` family require dedicated handling:

| Node kind | API to traverse child info |
| --- | --- |
| `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()` and when applicable `getAnnotatedOwnerType()` |
| `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` |
| `AnnotatedWildcardType` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` |
| `AnnotatedTypeVariable` | `getAnnotatedBounds()` |

Generic method example:

```java
public <E extends Exception> void call() throws E {}
```

This is an illustrative snippet, not a standalone program. `getGenericExceptionTypes()` can return a `TypeVariable` representing `E`, while `getAnnotatedExceptionTypes()` represents **the use of `E` in `throws`** as an `AnnotatedType`, which can be an `AnnotatedTypeVariable`. An annotation placed on the **bound** `E extends Exception` is information at **the bound position**, distinct from an annotation placed on **the use of `E` in `throws`**.

If writing a recursive metadata traverser over bounds, watch out for type-variable cycles (such as `T extends Comparable<T>`) and include an appropriate visited-set mechanism. Do not cast every `AnnotatedType` to `AnnotatedParameterizedType`.

## 8. Three kinds of annotations easily misread

A framework inspecting annotations on methods should separate at least three questions:

| Location to read | Appropriate API | Illustrative example |
| --- | --- | --- |
| Annotation on **method declaration** | `method.getAnnotation(DeclarationAnnotation.class)` | `@Deprecated` right before the method declaration |
| Annotation on **return type** | `method.getAnnotatedReturnType().getAnnotation(TypeUseAnnotation.class)` | `@Mark("result") List<String> read()` |
| Annotation on **return type argument** | `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[i]` | `List<@Mark("item") String>` |
| Annotation on **exception type** | `method.getAnnotatedExceptionTypes()[i].getAnnotation(...)` | `throws @Mark("io") IOException` |
| Annotation on **receiver type** | `method.getAnnotatedReceiverType().getAnnotation(...)` (if non-`null`) | `method(@Mark("this") C this)` |
| Annotation on **formal parameter type** | `method.getAnnotatedParameterTypes()[i]` | `save(@Mark("argument") String s)` |

In the receiver row, `C` stands for the declaring class of the instance method; the illustrative code only shows syntax and is not meant as a standalone Java class.

If an annotation is declared with **multiple targets** (`METHOD`, `PARAMETER`, `TYPE_USE`...), inspect the syntactic position and compiler metadata recording rules rather than assuming it is stored under a single API. Without `@Retention(RUNTIME)`, not seeing an annotation via runtime Reflection does not prove the annotation is absent from source or the class file.

## 9. Common mistakes and fixes

**Mistake 1 — Using `getReturnType()` to read annotations in `List<@Mark String>`.** `getReturnType()` only returns `Class<?> = List.class`; use `getAnnotatedReturnType()` and traverse down to the generic argument.

**Mistake 2 — Reading `getExceptionTypes()` and assuming you have annotations on `throws`.** The result is only `Class<?>[]`; use `getAnnotatedExceptionTypes()` to get `AnnotatedType[]`.

**Mistake 3 — Thinking `getAnnotatedExceptionTypes()` lists errors that will occur at runtime.** It reflects only the **`throws` clause**; it does not run the method or observe exceptions actually thrown.

**Mistake 4 — Equating `getAnnotatedReceiverType() == null` with an unannotated receiver.** An instance method can return an unannotated `AnnotatedType`; `null` is used when the executable **cannot have a receiver parameter**, such as a static method.

**Mistake 5 — Thinking an explicit receiver is an ordinary parameter.** `Service this` does not increase `getParameterCount()` and does not force callers to pass an extra `this`.

**Mistake 6 — Thinking the receiver type reflects a runtime subclass.** Metadata records the declared receiver type; at runtime the object may belong to a subclass, while dynamic dispatch is a separate matter.

**Mistake 7 — Failing to handle empty arrays or `null`.** `getAnnotatedExceptionTypes()` can return an empty array; `getAnnotatedReceiverType()` can return `null`. Check before indexing `[0]` or calling `getAnnotation`.

**Mistake 8 — Confusing method declaration annotations with return type annotations.** `Method.getAnnotations()` does not automatically include annotations at all type-use positions.

**Mistake 9 — Omitting `RetentionPolicy.RUNTIME`.** `TYPE_USE` only permits placing the annotation; it does not guarantee the annotation appears via Reflection if retention is inappropriate.

**Mistake 10 — Treating `AnnotatedType` as always being a simple type.** Return types can be parameterized, arrays, wildcards, or type variables; follow the type tree structure instead of casting recklessly.

## 10. Self-check

1. A method has return type `@Mark("top") List<@Mark("item") String>`. Where do you read `top`? **At `getAnnotatedReturnType()`**; read `item` at **the first type argument node**.
2. Does `throws @Mark("io") IOException` have `getExceptionTypes()[0]` return the annotation? **No**, the element is a `Class`; `getAnnotatedExceptionTypes()[0]` is needed.
3. If a method declares no `throws`, what does `getAnnotatedExceptionTypes()` return? **An empty array**, not `null`.
4. Does a static method have a receiver type? **No**, `getAnnotatedReceiverType()` returns `null`.
5. For an instance method without an explicit receiver annotation, must the receiver type be `null`? **No**; the API returns an `AnnotatedType` with no annotation on the receiver.
6. How many **formal parameters** does `void act(@Mark("x") C this)` declare? **0**; the receiver does not count as an ordinary formal parameter.
7. Is `getAnnotatedReceiverType()` the exact runtime type of the calling object? **No**; it is metadata on the declared receiver type.
8. Does `getAnnotatedReturnType()` execute the method and inspect the returned object? **No**; it only reads the declared structure.
9. For method `<E extends Exception> void call() throws E`, which API should you check to see the generic type structure in `throws`? **`getGenericExceptionTypes()`**, and use **`getAnnotatedExceptionTypes()`** when annotations on the type use are needed.
10. Why might an annotation with `@Target(TYPE_USE)` but without `@Retention(RUNTIME)` be unreadable via Reflection? **Because permission to place an annotation and retaining it until runtime are two independent properties.**

## 11. Official documentation

- [Oracle Java SE 21 — `Executable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html): contracts for `getAnnotatedReturnType()`, `getAnnotatedExceptionTypes()`, `getAnnotatedReceiverType()`, and receiver types of methods and constructors.
- [Oracle Java SE 21 — `Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): method info, return type, generic return type, and annotations.
- [Oracle Java SE 21 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedType.html): `getType()`, annotations at each type-use node.
- [Oracle Java SE 21 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html): annotations on generic arguments.
- [Java Language Specification SE 21 — §8.4.1 Formal Parameters](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.1): receiver parameters of instance methods.
- [Java Language Specification SE 21 — §9.7 Annotations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7): annotations at type-use positions.

**Remember:** `getAnnotatedReturnType()` looks at **the return type**; `getAnnotatedExceptionTypes()` looks at **the types listed in `throws`**; `getAnnotatedReceiverType()` looks at **the type of receiver `this`**. All three read *annotations at type-use positions*, not the same annotation group as the method declaration, and you must always inspect the right `AnnotatedType` node as well as handle empty arrays or `null`.