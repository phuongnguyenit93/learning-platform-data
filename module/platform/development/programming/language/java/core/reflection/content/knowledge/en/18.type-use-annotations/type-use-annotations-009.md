# Building a Type Tree Traverser While Preserving Annotation Positions

In Java Reflection, a type such as **List<String>** does not just have a type name and type arguments: each **type-use** position can carry its own annotations. Especially in nested generics, wildcards, arrays, owner types, and type-variable bounds, the annotation **position** matters just as much as the annotation **value**. A traverser that merely collects annotations into a flat list loses semantics.

This lesson belongs to the **Type-Use Annotations** topic and shows how to build a *visitor* that walks an **AnnotatedType** tree, records the path for each node, and avoids confusing annotations on the root type with annotations on child types. The goal is to make it usable in metadata viewers, serializers, validators, generic analyzers, or schema generators.

## 1. Declaration annotations and type-use annotations

Two kinds of positions must be distinguished:

- **Declaration annotations** attach to a declaration of a class, field, method, constructor, parameter, or type parameter. For example, an annotation targeting `FIELD` is read from `Field.getDeclaredAnnotations()`.
- **Type-use annotations** attach to a type-use position, for example `List` having its own annotation, `String` inside `List` having its own annotation, or an array dimension having its own annotation. This metadata is accessed via `AnnotatedType` and its variants.

Illustrative Java example:

~~~java
import java.lang.annotation.*;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Column {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Tag {
    String value();
}

class Example {
    @Column
    @Tag("list") List<@Tag("element") String> names;
}
~~~

Here **@Column** attaches to the field declaration; **@Tag("list")** belongs to the root type node `List<String>`; **@Tag("element")** belongs to the type argument `String`. If you inspect only `Field.getDeclaredAnnotations()`, you will not capture the annotation tree attached across all generic positions.

**Important condition:** core Reflection at runtime sees only annotations with `RetentionPolicy.RUNTIME`. Annotations with `SOURCE` or `CLASS` retention can exist in source/class files yet are not exposed through the corresponding runtime Reflection calls. When deeper class-file analysis is needed, another bytecode tool must be used.

## 2. Why traversing only `Type` is not enough

**Type** along with **ParameterizedType**, **TypeVariable**, **WildcardType**, and **GenericArrayType** provide the structure of a type. However, walking `Field.getGenericType()` and splitting `Type` components does not preserve all annotations attached at each type use.

Instead of:

~~~java
Type onlyStructure = field.getGenericType();
~~~

obtain the annotated root:

~~~java
AnnotatedType annotatedRoot = field.getAnnotatedType();
~~~

**AnnotatedType.getType()** still returns the `Type` structure of the current node, while **AnnotatedType.getAnnotationsByType(...)** and **getDeclaredAnnotations()** read annotations at **that exact node**. To descend into type arguments, array dimensions, bounds, or owners, you must use specialized APIs on the subtypes.

For instance:

~~~text
@Tag("list") List<@Tag("element") String>
                 |
field            |      annotation = list
└── field.arg[0] |      annotation = element
~~~

You must not report that both annotations sit on `List` or both sit on `String`. Distinguishing the two nodes is the main purpose of the visitor.

## 3. Node kinds that must be supported

| Reflection node kind | Sample structure | Child-retrieval call | Path convention |
|---|---|---|---|
| AnnotatedParameterizedType | List<String>, Map<K,V> | getAnnotatedActualTypeArguments() | .arg[0], .arg[1] |
| AnnotatedArrayType | String[] or String[][] | getAnnotatedGenericComponentType() | .component |
| AnnotatedWildcardType | ? extends Number; ? super Integer | getAnnotatedUpperBounds(), getAnnotatedLowerBounds() | .upper[0], .lower[0] |
| AnnotatedTypeVariable | T in List<T> | getAnnotatedBounds() | .bound[0] |
| AnnotatedType with owner | Outer.Inner<String> | getAnnotatedOwnerType() | .owner |
| Leaf node | String, Number, int | Do not traverse children | Keep node and annotations at node |

In every branch, the visitor executes in this order: **read and emit annotations at the current node**, then **enter child nodes**. An annotation on a parent node does not automatically inherit down to child nodes.

For **Map<@A String, @B List<@C Integer>>**, the corresponding paths are:

~~~text
field.arg[0]                 -> @A on String
field.arg[1]                 -> @B on List<Integer>
field.arg[1].arg[0]          -> @C on Integer
~~~

Paths are built from real edges in the Reflection model, not by searching substrings inside `Type.getTypeName()`.

## 4. Designing nodes and paths

In a real tool, the record for each node at minimum includes:

| Attribute | Example | Purpose |
|---|---|---|
| path | field.arg[0].upper[0] | Preserves exact position |
| kind | WILDCARD, PARAMETERIZED, ARRAY... | Describes node kind |
| typeName | java.lang.Number | Type at node |
| annotations | Tag("upper") | Annotations at this node only |
| declarationSource | Field, return, parameter... | Avoids mixing different roots |

Java 17 allows using a record to represent this:

~~~java
record TypeNode(
    String path,
    String kind,
    String typeName,
    java.util.List<String> annotations
) {}
~~~

This is an illustrative record declaration; the visitor in the next section prints directly to minimize boilerplate. When you need JSON output, tree rendering, or database storage, replace print statements with creating the corresponding `TypeNode` instances.

**Do not use `Class.getAnnotations()` on the raw class of a type argument as a substitute.** A type-use annotation on `String` in this field belongs to **the `String` position in the field**, not a declaration annotation on class `java.lang.String`, nor a permanent property of the `String.class` object.

## 5. Complete Java 17+ example: visitor with cycle protection

Create the file **AnnotatedTypeTreeDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedTypeVariable;
import java.lang.reflect.AnnotatedWildcardType;
import java.lang.reflect.TypeVariable;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class AnnotatedTypeTreeDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE_USE, ElementType.TYPE_PARAMETER})
    @interface Tag {
        String value();
    }

    static class Sample<
            @Tag("declaration") T extends @Tag("bound") Number> {

        @Tag("container")
        List<@Tag("element") String> names;

        List<@Tag("wildcard") ? extends @Tag("upper") Number> numbers;

        String @Tag("outer") [] @Tag("inner") [] matrix;

        List<@Tag("use-T") T> generic;
    }

    static String tags(AnnotatedType node) {
        List<String> values = new ArrayList<>();
        for (Tag tag : node.getAnnotationsByType(Tag.class)) {
            values.add(tag.value());
        }
        return values.isEmpty() ? "-" : String.join(",", values);
    }

    static String kind(AnnotatedType node) {
        if (node instanceof AnnotatedParameterizedType) {
            return "PARAMETERIZED";
        }
        if (node instanceof AnnotatedArrayType) {
            return "ARRAY";
        }
        if (node instanceof AnnotatedWildcardType) {
            return "WILDCARD";
        }
        if (node instanceof AnnotatedTypeVariable) {
            return "TYPE_VARIABLE";
        }
        return "CLASS";
    }

    static void walk(AnnotatedType node, String path,
                     Set<TypeVariable<?>> active) {
        System.out.println(path + " [" + kind(node)
                + "] @" + tags(node));

        AnnotatedType owner = node.getAnnotatedOwnerType();
        if (owner != null) {
            walk(owner, path + ".owner", active);
        }

        if (node instanceof AnnotatedParameterizedType p) {
            AnnotatedType[] args = p.getAnnotatedActualTypeArguments();
            for (int i = 0; i < args.length; i++) {
                walk(args[i], path + ".arg[" + i + "]", active);
            }
        } else if (node instanceof AnnotatedArrayType a) {
            walk(a.getAnnotatedGenericComponentType(),
                    path + ".component", active);
        } else if (node instanceof AnnotatedWildcardType w) {
            AnnotatedType[] upper = w.getAnnotatedUpperBounds();
            for (int i = 0; i < upper.length; i++) {
                walk(upper[i], path + ".upper[" + i + "]", active);
            }
            AnnotatedType[] lower = w.getAnnotatedLowerBounds();
            for (int i = 0; i < lower.length; i++) {
                walk(lower[i], path + ".lower[" + i + "]", active);
            }
        } else if (node instanceof AnnotatedTypeVariable tv) {
            TypeVariable<?> variable = (TypeVariable<?>) tv.getType();
            if (!active.add(variable)) {
                System.out.println(path + ".bounds [CYCLE]");
                return;
            }
            try {
                AnnotatedType[] bounds = tv.getAnnotatedBounds();
                for (int i = 0; i < bounds.length; i++) {
                    walk(bounds[i], path + ".bound[" + i + "]",
                            active);
                }
            } finally {
                active.remove(variable);
            }
        }
    }

    static void inspect(String fieldName) throws Exception {
        System.out.println("=== " + fieldName + " ===");
        AnnotatedType root =
                Sample.class.getDeclaredField(fieldName)
                        .getAnnotatedType();
        walk(root, "field", new HashSet<>());
    }

    public static void main(String[] args) throws Exception {
        inspect("names");
        inspect("numbers");
        inspect("matrix");
        inspect("generic");

        TypeVariable<?> declared =
                Sample.class.getTypeParameters()[0];
        System.out.print("T declaration @");
        Tag tag = declared.getAnnotation(Tag.class);
        System.out.println(tag == null ? "-" : tag.value());
    }
}
~~~

Compile and run in the directory containing the file with JDK 17 or newer:

~~~bash
javac AnnotatedTypeTreeDemo.java
java AnnotatedTypeTreeDemo
~~~

**Expected stdout per standard Java 17+ APIs:**

~~~text
=== names ===
field [PARAMETERIZED] @container
field.arg[0] [CLASS] @element
=== numbers ===
field [PARAMETERIZED] @-
field.arg[0] [WILDCARD] @wildcard
field.arg[0].upper[0] [CLASS] @upper
=== matrix ===
field [ARRAY] @outer
field.component [ARRAY] @inner
field.component.component [CLASS] @-
=== generic ===
field [PARAMETERIZED] @-
field.arg[0] [TYPE_VARIABLE] @use-T
field.arg[0].bound[0] [CLASS] @bound
T declaration @declaration
~~~

Paths do not depend on internal JVM implementation class names, because the visitor classifies nodes through Reflection interfaces. In the example, all fields are declared directly in `Sample`, so `getDeclaredField(...)` is appropriate.

### Explaining field names

The declaration **@Tag("container") List<@Tag("element") String> names** creates two separate positions:

- **field** is `List<String>` and carries the `container` annotation.
- **field.arg[0]** is `String` and carries the `element` annotation.

If you only call `Field.getAnnotations()`, you cannot reconstruct this path. If you only look at `GenericType`, you know `String` is there but lose the annotation at the use position.

### Explaining field numbers

The declaration **List<@Tag("wildcard") ? extends @Tag("upper") Number>** consists of:

- The `List` node, itself without a `Tag`.
- The wildcard node as the first generic argument, carrying `Tag` `wildcard`.
- The upper bound `Number` of the wildcard, carrying `Tag` `upper`.

Access the wildcard via `AnnotatedWildcardType`; **upper bounds** come from `getAnnotatedUpperBounds()`. If using **? super Integer**, you must enter **getAnnotatedLowerBounds()** and represent the lower branch; if you traverse only upper bounds, you will miss annotations on lower bounds.

### Explaining field matrix

With **String @Tag("outer") [] @Tag("inner") []**, the two pairs of square brackets belong to two different array levels. Reflection represents this with **two AnnotatedArrayType** nodes:

- `field`: outer dimension carrying `Tag` `outer`.
- `field.component`: inner dimension carrying `Tag` `inner`.
- `field.component.component`: component class `String`, which has no `Tag` in the example.

If you concatenate annotations into a combined list `[outer, inner]`, you no longer know which label belongs to which dimension. When processing multidimensional arrays or per-dimension type-use validation, this distinction matters.

### Explaining field generic and type parameter T

The field **List<@Tag("use-T") T> generic** has an argument that is an `AnnotatedTypeVariable`. The `use-T` annotation attaches to **the use position of T in List**, distinct from:

- **@Tag("declaration")** attached to **the type-parameter declaration T** of `Sample`, read via `TypeVariable.getAnnotation(Tag.class)`.
- **@Tag("bound")** attached to **the bound Number** of `T`, read via `AnnotatedTypeVariable.getAnnotatedBounds()` or `TypeVariable.getAnnotatedBounds()`.

All three annotation sources relate to `T`, yet **they do not sit on the same node**. A general tool can store the declaration part in a separate record instead of placing it in the field tree.

## 6. Avoiding infinite recursion when traversing type variables

A generic bound can self-reference:

~~~java
class Node<T extends Comparable<T>> {
    T value;
}
~~~

If the visitor expands `T`, then `Comparable<T>`, then argument `T`, and repeatedly expands bound `Comparable<T>`, it will not terminate:

~~~text
T
└── bound[0] Comparable<T>
    └── arg[0] T
        └── bound[0] Comparable<T>
            └── ...
~~~

The main example uses **Set<TypeVariable<?>> active** to track type variables currently on the active traversal branch. Upon encountering an already active variable again, the visitor prints a **[CYCLE]** marker instead of expanding bounds infinitely.

This technique has two important characteristics:

1. The visitor **still emits the current node occurrence** before detecting the cycle at the bound-expansion step, so annotations attached to that occurrence are not lost.
2. Using **finally** removes the type variable from the `active` set after finishing that branch. Another `T` appearing on a separate independent branch will still be fully traversed; it will not be skipped merely because `T` was seen earlier elsewhere in the program.

A more complex resolver can cache by `(generic declaration, type-variable binding)` pairs, node identity, and depth limits. Either way, there must be a strategy for handling cycles in type bound trees; unbounded looping is unacceptable.

## 7. Owner types and nested generic types

Nested classes can carry type-use annotations on the **outer owner**, **inner type**, and **inner type arguments**. Illustrative example:

~~~java
class Outer {
    class Inner<U> {}
}

// Placed after declaring Tag with TYPE_USE target inside a valid class:
@Tag("owner") Outer.@Tag("inner") Inner<@Tag("argument") String> ref;
~~~

Proper position representation:

~~~text
field             -> inner annotation, on Inner<String>
field.owner       -> owner annotation, on Outer
field.arg[0]      -> argument annotation, on String
~~~

In Java 9+, **AnnotatedType.getAnnotatedOwnerType()** lets the visitor access the owner if one exists. A dotted type name is not a sufficient method for determining owner annotations. You cannot retrieve `Outer`'s annotation by assigning it to `Inner` for convenience.

**Not every node has an owner**. `getAnnotatedOwnerType()` can return `null`. The structure of top-level classes, static nested classes, inner classes, and parameterized owners can differ. The visitor must traverse according to actual metadata rather than fabricating artificial owners.

For owners containing generic arguments, the owner branch can also be an `AnnotatedParameterizedType` and must be traversed recursively; otherwise, annotations of type arguments on the outer type will disappear.

## 8. Other roots beyond Field

To apply the traverser across an entire class, you can call the same `walk(...)` function from multiple sources:

| Declaration site | API returning AnnotatedType or AnnotatedType[] |
|---|---|
| Field | Field.getAnnotatedType() |
| Method return | Method.getAnnotatedReturnType() |
| Method parameters | Method.getAnnotatedParameterTypes() |
| Constructor parameters | Constructor.getAnnotatedParameterTypes() |
| Method/constructor throws | Executable.getAnnotatedExceptionTypes() |
| Superclass | Class.getAnnotatedSuperclass() |
| Implemented interfaces | Class.getAnnotatedInterfaces() |
| Type parameter bounds | TypeVariable.getAnnotatedBounds() |

For instance:

~~~java
class Service {
    public java.util.List<@Tag("returned") String> read(
            java.util.List<@Tag("input") String> values) {
        return values;
    }
}
~~~

This is an illustrative class example, requiring `Tag` with `TYPE_USE` and `RUNTIME` retention. With:

~~~java
Method m = Service.class.getMethod("read", java.util.List.class);
AnnotatedType out = m.getAnnotatedReturnType();
AnnotatedType in = m.getAnnotatedParameterTypes()[0];
~~~

You can call **walk(out, "return", active)** and **walk(in, "parameter[0]", active)**. The `returned` annotation sits at **return.arg[0]**, whereas `input` sits at **parameter[0].arg[0]**. Even though both are `List<String>`, they are two **different declaration positions**.

Both snippets are illustrative and are not part of the standalone runnable file in section 5; when integrating into a program, add `Method`/`AnnotatedType` imports and handle `NoSuchMethodException`.

### Note on constructor annotations

A constructor has no return value syntactically like a method, yet Reflection provides **Constructor.getAnnotatedReturnType()** for metadata defined by the Java API for constructors. Do not treat it as the return value of an ordinary method. Constructor parameters and exception types remain more common roots when analyzing type annotations.

## 9. Output data should be a tree, not a flat annotation set

A schema generator can store:

~~~json
{
  "path": "field.arg[0].upper[0]",
  "kind": "CLASS",
  "typeName": "java.lang.Number",
  "annotations": [
    {"name": "Tag", "value": "upper"}
  ]
}
~~~

This illustrates a JSON node; it is not an object that can be built completely just by calling `Class.getAnnotations()`. Annotations and values must be extracted from the `AnnotatedType` node at the corresponding path.

If visual display is needed, a tree can be printed using indentation; however, storing a **stable path** helps unit testing, schema diffing, and accurate error reporting. With multiple roots, include a source identifier such as field name, method signature, or parameter index.

To export to JSON practically, define a clear record structure, for example:

~~~java
record TypeUseLocation(
        String source,
        String path,
        String kind,
        String typeName,
        java.util.List<String> annotationNames) {}
~~~

Do not just serialize a `List<Annotation>` because all child positions would be lost.

## 10. Repeatable annotations and multiple annotations

Java allows an annotation with target `TYPE_USE` to be declared **@Repeatable**, in which case a single node can contain multiple annotations of the same kind. A visitor can use **getAnnotationsByType(Tag.class)** when wanting logical instances of a specific annotation, including cases grouped inside a repeatable container.

If writing a general traverser without knowing `Tag` ahead of time, read **getDeclaredAnnotations()** on each `AnnotatedType`, then process/unwrap repeatable containers as needed per standard metadata rules. Do not merge annotations with the same name across two **different nodes**; having the same annotation type does not turn two positions into one.

If a tool needs deterministic output across runs, sort annotations by fully qualified name and attribute values rather than relying on arbitrary ordering. The order of **tree branches** should be determined by argument index, array component, bound index, and owner relationship.

## 11. Important limitations

**Reflection metadata does not replace validation.** An annotation named `@NotNull` or `@Tag("element")` does not automatically check objects inside a runtime list. A framework needs its own validation logic, especially for nested generics.

**Type erasure still exists.** An `AnnotatedTypeVariable` `T` does not immediately reveal the concrete type parameter of an actual object. If `class Derived extends Base<String>`, replacing `T` with `String` in a field declared on `Base` requires resolving generic type bindings along the hierarchy while preserving annotations at their corresponding positions. That is a separate step beyond merely walking `AnnotatedType`.

**Do not assume every Type is a Class.** `AnnotatedParameterizedType` has `Type` as `ParameterizedType`; wildcards, type variables, and generic arrays all have distinct structures. Blindly casting `node.getType()` to `Class<?>` can throw `ClassCastException`.

**Module and access boundaries.** Reading metadata does not automatically grant permission to read private field values or invoke private methods. If a tool goes beyond traversing types, `Field.get()`, `Method.invoke()`, `Constructor.newInstance()`, and `setAccessible()` have separate access/JPMS checks.

**Annotations without RUNTIME retention** do not show up through the corresponding core Reflection APIs. Concluding "not seen by the visitor" only means "no runtime-visible metadata exists at that position", not proof that the source never had an annotation.

**Array dimensions** have their own annotations and must not be attached onto the component type.

**Wildcards** can have upper bounds or lower bounds; distinguish `.upper` and `.lower`.

**TypeVariable declaration** differs from occurrence: `TYPE_PARAMETER` annotations on the declaration and `TYPE_USE` annotations at each use site of `T` do not come from the same source.

**Paths must preserve root relationship**. If two fields both contain `@Tag("element")` on `String`, those annotations belong to two different declaration locations and require distinct source identifiers.

## 12. Common mistakes

1. **Inspecting only `Type.getTypeName()`** and trying to infer annotations from text: lacks type-use position data.
2. **Reading only `Field.getAnnotations()`**: misses annotations in generic arguments, wildcard bounds, or array dimensions.
3. **Merging annotations of `List` and `String`** into one list: attributes ownership to the wrong node.
4. **Not traversing `AnnotatedParameterizedType`**: skips annotations on nested generic arguments.
5. **Not traversing `AnnotatedArrayType` level by level**: loses annotations on individual array dimensions.
6. **Traversing wildcards but skipping upper/lower bounds**: loses annotations or confuses variance.
7. **Treating `TypeVariable.getBounds()` as sufficient**: taking plain `Type` can lose annotations on bounds; use `getAnnotatedBounds()`.
8. **Treating `T`'s declaration annotation as an annotation on every use-site `T`**: two different kinds of metadata.
9. **Missing cycle detection for `T extends Comparable<T>`**: the visitor can run infinitely.
10. **Skipping `getAnnotatedOwnerType()`**: annotations on the owner of a nested class are lost.
11. **Ignoring `RetentionPolicy.RUNTIME`**: failing to understand why Reflection does not see annotations present in source.
12. **Producing JSON containing only annotation names**: loses positions and cannot reconstruct type-use semantics.
13. **Using the runtime class of collection elements to look for type-use annotations**: runtime data is not declared type metadata.
14. **Dropping annotations when substituting generic type variables**: can lose schema/validation information.
15. **Believing seeing an annotation means runtime already auto-validates**: annotations are descriptions; validation is a separate mechanism.

## 13. Self-check questions

**Question 1.** For `Map<@A String, List<@B Integer>>`, if the root is `field`, where is `@B` located?

**Answer:** At **field.arg[1].arg[0]**. First enter the second type argument of `Map`, then the first type argument of `List`.

**Question 2.** For `List<@A ? extends @B Number>`, are `@A` and `@B` on the same node?

**Answer:** No. `@A` sits at **field.arg[0]** (wildcard), and `@B` sits at **field.arg[0].upper[0]** (`Number` bound).

**Question 3.** For `String @A [] @B []`, which branches must be traversed?

**Answer:** Root is `AnnotatedArrayType` for outer dimension `@A`; component is `AnnotatedArrayType` for inner dimension `@B`; the next component is `String`.

**Question 4.** For `class Box<@A T extends @B Number> { List<@C T> items; }`, where do the three annotations belong?

**Answer:** `@A` on the type-parameter declaration `T`; `@B` on the `Number` bound of `T`; `@C` on the use position of `T` inside `List`. They must not be merged.

**Question 5.** Why does the visitor need `Set<TypeVariable<?>> active`?

**Answer:** To prevent infinite bound expansion in self-referential structures such as `T extends Comparable<T>`, while still allowing the same `T` to appear validly on another branch.

**Question 6.** If an annotation has `CLASS` retention, is a runtime visitor guaranteed to see it?

**Answer:** No. Core Reflection exposes only runtime-visible annotations; a class-file reader must be used when non-runtime-visible data is needed.

**Question 7.** Which APIs should be used to read annotations on a method return and on an argument of a method parameter?

**Answer:** `Method.getAnnotatedReturnType()` and `Method.getAnnotatedParameterTypes()[i]`, then traverse each root with distinct paths so positions are not mixed.

## Standard documentation

- Java SE API: `java.lang.reflect.AnnotatedType`, `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedWildcardType`, `AnnotatedTypeVariable`.
- Java SE API: `Field.getAnnotatedType()`, `Method.getAnnotatedReturnType()`, `Executable.getAnnotatedParameterTypes()`, `Executable.getAnnotatedExceptionTypes()`.
- Java SE API: `TypeVariable.getAnnotatedBounds()`, `AnnotatedElement.getAnnotationsByType()`, `Class.getAnnotatedSuperclass()`, `Class.getAnnotatedInterfaces()`.
- Java Language Specification: type-use positions, generic type parameters, annotation targets, annotation retention, and recursive bounds.
- Java Virtual Machine Specification: runtime-visible type annotations and class-file metadata, when needed to understand how positions are stored.

**Remember:** a type-tree traverser must take **AnnotatedType as the starting point**, record **annotations directly at the current node**, follow the **arg / component / upper / lower / bound / owner** edges, while tagging the declaration source and guarding against cycles. Only then are annotations preserved with their exact **positions** instead of becoming a contextless set of names.