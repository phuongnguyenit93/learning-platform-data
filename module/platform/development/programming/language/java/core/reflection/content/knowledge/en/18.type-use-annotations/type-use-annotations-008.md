# Annotations on Declared Superclasses and Interfaces

## 1. The problem: is the annotation on *a used type* or on *a type declaration*?

In Java, an annotation can be attached to **a class/interface declaration** or to **a type-use position** in `extends` and `implements` clauses. These are two distinct locations even though both relate to inheritance relationships.

~~~java
// Syntax illustration snippet. Annotations are assumed to be properly defined.
@Category("domain")                    // Declaration annotation: Base
class Base {}

class Child extends @Edge("inheritance") Base {}
//                  ^ Annotation on the "Base" type use on edge Child -> Base.
~~~

- `@Category` describes the `Base` declaration; queried via `Base.class.getAnnotation(Category.class)`.
- `@Edge` describes **the use of type `Base` as the superclass of `Child`**; it does not attach to `Base.class` and is not a declaration annotation of `Child`.
- If there is `AnotherChild extends @Edge("another") Base`, the two edges can carry different annotations while `Base` remains a single declaration.
- For `implements Interface` or `interface Sub extends Interface`, the idea is identical: the annotation is on the interface usage edge, not an annotation on the interface declaration itself.

This topic belongs to **type-use annotations** (`@Target(ElementType.TYPE_USE)`), supported since Java 8. Java Reflection uses `AnnotatedType` to return annotations at type-use positions rather than returning only `Class<?>`.

## 2. Primary APIs: getAnnotatedSuperclass and getAnnotatedInterfaces

| Java Reflection API | Result | Scope |
| --- | --- | --- |
| `clazz.getSuperclass()` | `Class<?>` of the direct superclass (if any) | No type-use annotations, does not preserve generic args. |
| `clazz.getGenericSuperclass()` | `Type` of the direct superclass | Has generic declaration, **does not contain type-use annotations**. |
| `clazz.getAnnotatedSuperclass()` | `AnnotatedType` describing *the superclass use* of the class | Can read `TYPE_USE` annotations on `extends` and on nested generic arguments. |
| `clazz.getInterfaces()` | `Class<?>[]` containing **direct** superinterfaces | Does not contain `TYPE_USE` annotations or generic args. |
| `clazz.getGenericInterfaces()` | `Type[]` containing direct superinterfaces | Preserves generic args, but does not contain `TYPE_USE` annotations. |
| `clazz.getAnnotatedInterfaces()` | `AnnotatedType[]` containing direct *interface uses* | Has `TYPE_USE` annotations on `implements`/`extends` and on type arguments. |

The `getAnnotatedSuperclass()` and `getAnnotatedInterfaces()` APIs are declared on `java.lang.Class`. These two APIs differ completely from `Class.getAnnotations()` and `Class.getDeclaredAnnotations()`: the latter read **declaration annotations of the Class object**, not annotations on superclass/interface edges.

Under the Java SE 17 contract:

- For an ordinary class, `getAnnotatedSuperclass()` describes its direct superclass. If the superclass has no declared annotations, it can still return an `AnnotatedType` with an **empty** annotation array. For instance, a class that does not write `extends` still has an implicit `Object` superclass.
- `getAnnotatedSuperclass()` returns **null** for `Object.class`, interfaces, array classes, primitives, and `void.class`.
- `getAnnotatedInterfaces()` returns an array in **declaration order** from the `implements` or interface `extends` clause. If there are no direct superinterfaces, the array is empty.
- The `getAnnotatedInterfaces()` API does not automatically concatenate all indirect interfaces implemented by superclasses. To traverse the transitive hierarchy, a tool author must continue walking parent nodes.

For example, in `class Child implements A, B`, `getAnnotatedInterfaces()[0]` reflects the use of `A`, and element `[1]` is `B`. You should not rely blindly on indices when source order might change; compare `AnnotatedType.getType()` against the target type or track an explicit path.

## 3. Declaring annotations properly for TYPE_USE

An annotation on a superclass/interface use must allow target `TYPE_USE`. If you want to read it via Reflection at runtime, `@Retention(RetentionPolicy.RUNTIME)` is required. Example:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Edge {
    String value();
}
~~~

This is a separate declaration snippet for illustration. If combining with the standalone example in section 6, do **not** declare a duplicate `Edge` annotation.

Keep these distinct:

| Position | Example | Appropriate target | Reading API |
| --- | --- | --- | --- |
| Class declaration | `@Role class Base {}` | `TYPE` | `Base.class.getAnnotation(Role.class)` |
| Type use on superclass | `class Child extends @Edge Base {}` | `TYPE_USE` | `Child.class.getAnnotatedSuperclass().getAnnotation(Edge.class)` |
| Type use on implemented interface | `class Child implements @Edge Contract {}` | `TYPE_USE` | Iterate `Child.class.getAnnotatedInterfaces()` then `getAnnotation(Edge.class)` |
| Type use on superinterface | `interface Sub extends @Edge Contract {}` | `TYPE_USE` | `Sub.class.getAnnotatedInterfaces()` |
| Nested type argument in superclass | `extends Base<@Edge String>` | `TYPE_USE` | `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` |
| Type parameter declaration | `class Base<@Marker T> {}` | `TYPE_PARAMETER` | `TypeVariable.getAnnotations()` (declaration semantics differ from type-use). |

Do not treat `@Target(TYPE)` and `@Target(TYPE_USE)` as equivalent. You can declare an annotation with multiple targets if truly needed, but you must understand which API is required and where the annotation is placed. An annotation with `RetentionPolicy.CLASS` may exist in the class file while runtime Reflection APIs do not expose it. `RetentionPolicy.SOURCE` is not retained in the class file.

## 4. What does AnnotatedType represent?

`java.lang.reflect.AnnotatedType` is an `AnnotatedElement` describing *a type use*, so it has:

- `getType()`: the underlying `java.lang.reflect.Type`, which may be a `Class<?>` or `ParameterizedType`.
- `getAnnotation(Edge.class)`, `isAnnotationPresent(...)`, `getAnnotations()`, `getDeclaredAnnotations()`: read annotations attached to **the represented type use**.
- `getAnnotatedOwnerType()`: when it is a member type and has a represented enclosing owner type, allows inspecting the owner part (may be null).

When a superclass/interface has generic arguments, the returned type is typically `AnnotatedParameterizedType`, with `getAnnotatedActualTypeArguments()` holding annotations for each type parameter. For example:

~~~java
// Assuming Base<T>, Contract<T>, and @Edge allowing TYPE_USE exist.
class Child extends @Edge("super") Base<@Edge("arg") String>
        implements @Edge("contract") Contract<@Edge("generic-arg") Integer> {}
~~~

You must read **two levels**:

1. `Child.class.getAnnotatedSuperclass().getAnnotation(Edge.class)` reads `@Edge("super")`.
2. Cast the superclass annotated type to `AnnotatedParameterizedType` and get argument `[0].getAnnotation(Edge.class)` to read `@Edge("arg")`.

Similarly, `getAnnotatedInterfaces()[0].getAnnotation(Edge.class)` reads the annotation on the interface use, while the annotation on `Integer` is on the annotated generic argument. **Outer and inner annotations do not merge automatically**: `getAnnotations()` on the outer type use does not automatically return annotations of nested type arguments.

In addition to `AnnotatedParameterizedType`, related subtypes include `AnnotatedArrayType`, `AnnotatedWildcardType`, and `AnnotatedTypeVariable`. To support all complex generic forms, a parser must traverse recursively. Do not cast directly to `Class<?>` or `AnnotatedParameterizedType` without checking `instanceof`; raw or non-generic types are normally not annotated parameterized types.

## 5. @Inherited is NOT a mechanism for inheriting annotations on extends/implements edges

`java.lang.annotation.Inherited` often causes confusion here.

Annotation declaration:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@java.lang.annotation.Inherited
@interface Role {
    String value();
}
~~~

`@Inherited` indicates that a **declaration annotation** can be looked up along **the superclass chain** when querying a class declaration. If `Base` has `@Role`, a subclass does not directly declare `@Role`, yet `Child.class.getAnnotation(Role.class)` can return the annotation from `Base`. This does not mean the annotation is copied into `Child`'s class file: `Child.class.getDeclaredAnnotation(Role.class)` remains `null` when `Child` does not declare it directly.

Three limits to remember:

- **Not inherited from interfaces** via `@Inherited`: `class Impl implements @SomeUse Interface` does not receive the interface's declaration annotation `@Role` merely by implementing it.
- **Does not propagate type-use annotations across edges**: if `Child extends @Edge Base`, then `Grandchild extends Child` does not automatically get `@Edge` on the `Grandchild -> Child` edge. To know the annotation of edge `Child -> Base`, you must explicitly inspect `Child.class.getAnnotatedSuperclass()`.
- **Does not apply to finding annotations at arbitrary syntactic positions**: `@Inherited` is defined for querying class declaration annotations; do not use it as an `AnnotatedType` traverser or an algorithm for finding annotations on interfaces.

This is precisely why a tool designing a policy placed on inheritance edges needs to preserve the context of **the class declaring the edge**, whereas a tool handling class-level markers needs to check `getAnnotation`/`getDeclaredAnnotation` and `@Inherited` rules. Two different tasks should not share the same "annotation inheritance" rule.

## 6. Complete Java 17+ example: superclass, interface, and generic arguments

Save the file `AnnotatedHierarchyDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;

public class AnnotatedHierarchyDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Edge {
        String value();
    }

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Role {
        String value();
    }

    @Role("base-declaration")
    static class Base<T> {
    }

    @Role("interface-declaration")
    interface Contract<T> {
    }

    static class Child
            extends @Edge("superclass-edge") Base<@Edge("superclass-arg") String>
            implements @Edge("interface-edge") Contract<@Edge("interface-arg") Integer> {
    }

    static class Grandchild extends Child {
    }

    static class OnlyInterface implements Contract<String> {
    }

    interface SubContract extends @Edge("superinterface-edge") Contract<Long> {
    }

    static String edge(AnnotatedType annotated) {
        Edge value = annotated.getAnnotation(Edge.class);
        return value == null ? "-" : value.value();
    }

    static String role(Class<?> type) {
        Role value = type.getAnnotation(Role.class);
        return value == null ? "-" : value.value();
    }

    public static void main(String[] args) {
        AnnotatedType superclass = Child.class.getAnnotatedSuperclass();
        AnnotatedType interfaceUse = Child.class.getAnnotatedInterfaces()[0];

        System.out.println("Child superclass edge=" + edge(superclass));
        System.out.println("Child superclass argument="
                + edge(((AnnotatedParameterizedType) superclass)
                        .getAnnotatedActualTypeArguments()[0]));
        System.out.println("Child interface edge=" + edge(interfaceUse));
        System.out.println("Child interface argument="
                + edge(((AnnotatedParameterizedType) interfaceUse)
                        .getAnnotatedActualTypeArguments()[0]));

        System.out.println("SubContract superinterface edge="
                + edge(SubContract.class.getAnnotatedInterfaces()[0]));
        System.out.println("Base declaration role=" + role(Base.class));
        System.out.println("Child inherited role=" + role(Child.class));
        System.out.println("Child declared role="
                + (Child.class.getDeclaredAnnotation(Role.class) != null));
        System.out.println("OnlyInterface inherited role=" + role(OnlyInterface.class));
        System.out.println("Grandchild role=" + role(Grandchild.class));
        System.out.println("Grandchild direct edge="
                + edge(Grandchild.class.getAnnotatedSuperclass()));
        System.out.println("Grandchild direct interfaces="
                + Grandchild.class.getAnnotatedInterfaces().length);
        System.out.println("Interface has superclass="
                + (Contract.class.getAnnotatedSuperclass() != null));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 AnnotatedHierarchyDemo.java
java AnnotatedHierarchyDemo
~~~

Expected output on Java 17+:

~~~text
Child superclass edge=superclass-edge
Child superclass argument=superclass-arg
Child interface edge=interface-edge
Child interface argument=interface-arg
SubContract superinterface edge=superinterface-edge
Base declaration role=base-declaration
Child inherited role=base-declaration
Child declared role=false
OnlyInterface inherited role=-
Grandchild role=base-declaration
Grandchild direct edge=-
Grandchild direct interfaces=0
Interface has superclass=false
~~~

Explaining each group of results:

- `Child` has **one direct superclass** and one **direct implemented interface**, each edge carrying its own `@Edge`. Reflection returns the exact annotation at the corresponding position.
- `Base<@Edge String>` / `Contract<@Edge Integer>` keep `@Edge` on the type argument; therefore you must go through `AnnotatedParameterizedType` to read them.
- `SubContract` is an **interface** extending another interface. It has no class superclass (`getAnnotatedSuperclass()==null`), yet `getAnnotatedInterfaces()` still reflects the `extends Contract<Long>` edge.
- `Role` is a declaration annotation of `Base` and `Contract`. `Child` inherits `Role("base-declaration")` from the superclass thanks to `@Inherited`, though `getDeclaredAnnotation` on `Child` does not return it.
- `OnlyInterface` has no superclass marked with `Role`; `@Role` on `Contract` **does not transfer to an implementing class** via `@Inherited`.
- `Grandchild` can still be queried for declaration annotation `Role` along the class superclass chain, yet the direct superclass edge (`Grandchild -> Child`) has **no** `@Edge`, so `edge(...)` returns `-`.
- `Grandchild.getAnnotatedInterfaces().length == 0` because `Grandchild` **does not directly declare implements**. That does not mean a `Grandchild` is not a `Contract`: it still inherits the interface implementation through `Child` in the type hierarchy.

If you change `@Retention(RUNTIME)` on `Edge` to `CLASS`, runtime Reflection will no longer see those markers. The order of type arguments in the returned array matches the order in the declaration of `Base<T>`/`Contract<T>`.

## 7. Traversing multiple levels properly

`getAnnotatedSuperclass()` and `getAnnotatedInterfaces()` provide **the direct edges of the current node**, not the closure of the entire inheritance graph. A framework searching for type-use annotations across a hierarchy can proceed as follows:

1. Choose the root class/interface `root` to analyze.
2. At each node `current`, read `current.getAnnotatedSuperclass()` (if non-null) and process annotations of **the edge leading to the superclass**.
3. Iterate `current.getAnnotatedInterfaces()` in returned order and process annotations of **each direct interface edge**.
4. From each annotated edge, call `getType()` to determine the target type. If it is a `ParameterizedType`, use `getRawType()` to determine the next class/interface to traverse; if it is a `Class<?>`, use it directly.
5. When generic argument annotations are needed, branch on `instanceof AnnotatedParameterizedType` and traverse `getAnnotatedActualTypeArguments()`, going deeper into array/wildcard/nested owner types when appropriate.
6. Continue traversing target classes/interfaces according to application policy (class chain only, interface graph only, or both). The same interface may be reached via **multiple paths**, so track visited nodes to avoid loops if only unique nodes are needed; if business logic evaluates **each individually annotated edge**, preserve path/edge context rather than accidentally merging everything.
7. Do not automatically push annotations from parent edges down to all child edges: the semantics of `@Edge` are defined by the application; Java only stores and exposes metadata, **without enforcing runtime policies on behalf of the framework author**.

A function that only needs to determine the raw class from an `AnnotatedType` can use:

~~~java
// Snippet to place in a class with import java.lang.reflect.*.
// It only resolves raw classes for Class and ParameterizedType, not a general
// resolver for all TypeVariable, GenericArrayType, or WildcardType.
static Class<?> rawClass(AnnotatedType annotated) {
    java.lang.reflect.Type type = annotated.getType();
    if (type instanceof Class<?> cls) {
        return cls;
    }
    if (type instanceof java.lang.reflect.ParameterizedType pt
            && pt.getRawType() instanceof Class<?> cls) {
        return cls;
    }
    throw new IllegalArgumentException("Unsupported raw type: " + type);
}
~~~

The code above is an illustrative utility snippet, not a standalone program. It does not handle every `Type` and cannot replace a full generic resolver; this branching is intentional so unsupported cases fail with a clear error rather than a wrong cast.

### When encountering multiple different declaration annotations

If the goal is "does this class have `@Role`?", use `Class.getAnnotation(Role.class)` per `@Inherited` semantics. If the goal is "does this extends/implements edge have `@Edge`?", **read the annotated hierarchy edges**. A framework should document its policy clearly when:

- interface `A` is inherited indirectly through multiple branches;
- a superclass and an interface have annotations with the same name but different meanings;
- a type-use annotation resides on the outer type, a type argument, or an inner component;
- a class declares no explicit `extends` yet has `Object` as its superclass;
- annotations are not retained until runtime.

## 8. Common mistakes to avoid

| Misconception | Correct understanding |
| --- | --- |
| "`Base.class.getAnnotation(Edge.class)` reads `extends @Edge Base`." | Annotations on **Child's edge** must be read from `Child.class.getAnnotatedSuperclass()`. |
| "`getGenericSuperclass()` is enough to get `TYPE_USE` annotations." | That API returns `Type`, without the annotation layer; use `getAnnotatedSuperclass()`. |
| "An annotation on `implements` automatically appears on the interface declaration." | That is metadata of the interface use in the declaring class. |
| "`@Inherited` propagates annotations from interfaces to implementing classes." | Wrong: `@Inherited` only considers the superclass chain of class declarations. |
| "`@Inherited` copies `TYPE_USE` annotations down to all subclasses." | Wrong: type-use annotations on each edge are independent metadata. |
| "`getAnnotatedInterfaces()` lists all indirectly inherited interfaces." | Wrong: only direct superinterfaces declared by the class/interface. |
| "If `getAnnotatedSuperclass()` returns non-null, an annotation must exist." | Wrong: it can represent an unannotated superclass, such as implicit `Object`. |
| "`@Target(TYPE)` suffices for type-use in `extends/implements`." | `TYPE_USE` is required for type-use positions. |
| "`AnnotatedParameterizedType.getAnnotations()` includes annotations of all generic arguments." | Wrong: you must read each `getAnnotatedActualTypeArguments()`. |
| "Having an annotation in source means Reflection sees it." | Appropriate retention (`RUNTIME`) and valid metadata are required. |

**Practical scenario:** a dependency injection framework wanting to determine how to handle an adapter along the `implements Contract<T>` path can use edge annotations as routing metadata. Conversely, a validator looking for class-level `@Entity` may only need `Class.getAnnotation(...)` (and that annotation's `@Inherited` rule). Choosing the right metadata location prevents confusing annotations between two objects and two layers of responsibility.

## 9. Practice exercises

1. Add an interface `Loggable` and write `implements @Edge("api") Contract<String>, @Edge("log") Loggable`; print each element of `getAnnotatedInterfaces()` to observe the ordering.
2. Try `class Plain {}` and verify `Plain.class.getAnnotatedSuperclass()` is non-null yet has no `@Edge`.
3. Try `Object.class.getAnnotatedSuperclass()`, `Contract.class.getAnnotatedSuperclass()`, and `int.class.getAnnotatedSuperclass()`, and compare with a regular class.
4. Remove `@Inherited` from `Role` in the demo, rerun, and explain why `Child.class.getAnnotation(Role.class)` does not receive the marker from `Base`.
5. Keep `@Inherited` on `Role` but remove `@Role` from `Base`; keep the marker only on `Contract` and verify `OnlyInterface`/`Child` do not automatically inherit annotations from the interface.
6. Replace the type argument `String` with `List<@Edge("nested") String>` in the superclass, and implement a two-level `AnnotatedParameterizedType` traversal.
7. Create `Grandchild extends @Edge("direct-grandchild") Child`, and verify the annotation of `Grandchild -> Child` is independent of the annotation of `Child -> Base`.
8. Build a function listing direct edges: source class name, target type, annotation on the edge, and annotations on generic arguments; distinguish direct vs. transitive.
9. With `@Retention(CLASS)` or `SOURCE`, observe that the annotation does not appear via runtime Reflection even though the source syntax is valid.

## 10. Official references

- [Java SE 17 — Class.getAnnotatedSuperclass / getAnnotatedInterfaces](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): contract for direct superclass/interfaces, null behavior, and ordering.
- [Java SE 17 — AnnotatedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): type-use annotations and underlying type.
- [Java SE 17 — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html): generic arguments with their own annotations.
- [Java SE 17 — @Inherited](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): declaration annotation inheritance along the superclass chain, not through interfaces.
- [JLS Java 17 — Type Annotations `9.7.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4): annotations on type uses.
- [JLS Java 17 — Inheriting Annotations `9.6.4.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3): scope of `@Inherited`.

**Core takeaway:** `Class.getAnnotation` reads **annotations declared on the class** (with its own `@Inherited` rules), whereas `getAnnotatedSuperclass` and `getAnnotatedInterfaces` read **annotations on each direct superclass/interface use**. You must distinguish these two metadata layers, and descend into `AnnotatedParameterizedType` if the annotation is on a generic argument.