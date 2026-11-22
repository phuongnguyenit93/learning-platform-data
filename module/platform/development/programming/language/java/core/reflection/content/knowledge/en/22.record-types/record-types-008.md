# `RecordComponent.getAnnotatedType()` and annotations on component types

A record component can carry annotations on the declaration itself, on the outermost type, or deep inside generic types, arrays, and type bounds. Reading only `RecordComponent.getAnnotations()` is not enough to see all those locations.

`getAnnotatedType()` takes you to **the type structure that can hold annotations** for the component. From there, a program can navigate to the exact marked location instead of flattening every annotation into a single list.

This is useful when writing data validators or type-structure analyzers: "the list must not be empty", "elements must not be null", and "the array has some property" can be different requirements at different type positions.

## 1. Three ways to view a component's type

[The `RecordComponent` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html) provides different levels of information:

| API | Result | Main use case |
| --- | --- | --- |
| `getType()` | `Class<?>` | Type in class form, used for many Reflection lookup operations |
| `getGenericType()` | `Type` | Declared type structure with generics, type variables, or wildcards |
| `getAnnotatedType()` | `AnnotatedType` | Declared type structure together with annotations on each type use position |

For example, for `List<@TypeNote("item") String> tags`, `getType()` gives `List.class`, while `getGenericType()` describes `List<String>`. To find the annotation attached to the `String` position inside the list, you must enter the `AnnotatedType` structure.

`getAnnotatedType()` describes **the declared type**; it does not read the value of a record object and does not automatically turn a generic type variable into the runtime type of the contained data.

## 2. Declaration annotations and type-use annotations

The two annotation types in the experiment have separate targets:

- `ComponentNote` has `@Target(RECORD_COMPONENT)`: marks the record component itself.
- `TypeNote` has `@Target(TYPE_USE)`: marks a type use position.

`TYPE_USE` allows placing annotations at positions such as the component type, generic type arguments, or array element types; this is the context categorized in [`ElementType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/ElementType.html#TYPE_USE).

For a component that has both `@ComponentNote` and `@TypeNote`, these two calls do not query the same place:

```java
component.getDeclaredAnnotation(ComponentNote.class);
component.getAnnotatedType().getAnnotation(TypeNote.class);
```

This is an excerpt when you already have a `RecordComponent component` variable and the corresponding annotation types. The first call reads the component's declaration metadata; the second reads the annotation at the root of the component's type.

Both annotations in the example have `@Retention(RUNTIME)` to be readable at runtime. Target applicability and retention lifetime are two independent conditions.

## 3. Viewing the type structure position by position

[`AnnotatedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedType.html) represents a type use that can carry annotations. It does not necessarily have annotations on the outermost node itself.

| Structural form | Reflection interface | Next step |
| --- | --- | --- |
| Generic type such as `List<String>` | `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()` |
| Array type | `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` |
| Wildcard such as `? extends Number` | `AnnotatedWildcardType` | `getAnnotatedUpperBounds()` and `getAnnotatedLowerBounds()` |
| Type variable such as `T` | `AnnotatedTypeVariable` | `getAnnotatedBounds()` |

Do not cast every `AnnotatedType` to `AnnotatedParameterizedType`. A `String`, `String[]`, or `T` component has a different shape. Use `instanceof` to select the appropriate traversal.

## 4. Complete experiment on Java 17+

The program marks each position with a distinct string so it is clear which annotation belongs to which node. It does not need to create record objects, because it only analyzes type metadata.

Save the entire code into **`RecordAnnotatedTypeDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedTypeVariable;
import java.lang.reflect.AnnotatedWildcardType;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.TypeVariable;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class RecordAnnotatedTypeDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface TypeNote {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface ComponentNote {
        String value();
    }

    public record Sample<T extends @TypeNote("bound") Number>(
            @ComponentNote("declaration-only") @TypeNote("text") String name,
            @TypeNote("list") List<@TypeNote("item") String> tags,
            @TypeNote("array-element") String @TypeNote("array") [] codes,
            List<? extends @TypeNote("upper") Number> numbers,
            List<? super @TypeNote("lower") Integer> sinks,
            @TypeNote("use-T") T quantity,
            String plain) {
    }

    public record Recursive<T extends Comparable<T>>(T value) {
    }

    private static String notes(AnnotatedType type) {
        return Arrays.stream(type.getAnnotationsByType(TypeNote.class))
                .map(TypeNote::value)
                .sorted()
                .toList()
                .toString();
    }

    private static void walk(String path, AnnotatedType type,
            Set<TypeVariable<?>> activeVariables) {
        System.out.println(path + ": " + type.getType().getTypeName()
                + " notes=" + notes(type));

        if (type instanceof AnnotatedTypeVariable variableType) {
            TypeVariable<?> variable = (TypeVariable<?>) type.getType();
            if (!activeVariables.add(variable)) {
                System.out.println(path + ".bounds: cycle stopped");
                return;
            }
            AnnotatedType[] bounds = variableType.getAnnotatedBounds();
            for (int i = 0; i < bounds.length; i++) {
                walk(path + ".bound[" + i + "]", bounds[i], activeVariables);
            }
            activeVariables.remove(variable);
            return;
        }

        AnnotatedType owner = type.getAnnotatedOwnerType();
        if (owner != null) {
            walk(path + ".owner", owner, activeVariables);
        }

        if (type instanceof AnnotatedParameterizedType parameterized) {
            AnnotatedType[] arguments = parameterized.getAnnotatedActualTypeArguments();
            for (int i = 0; i < arguments.length; i++) {
                walk(path + ".arg[" + i + "]", arguments[i], activeVariables);
            }
        } else if (type instanceof AnnotatedArrayType array) {
            walk(path + ".element",
                    array.getAnnotatedGenericComponentType(), activeVariables);
        } else if (type instanceof AnnotatedWildcardType wildcard) {
            AnnotatedType[] upper = wildcard.getAnnotatedUpperBounds();
            for (int i = 0; i < upper.length; i++) {
                walk(path + ".upper[" + i + "]", upper[i], activeVariables);
            }
            AnnotatedType[] lower = wildcard.getAnnotatedLowerBounds();
            for (int i = 0; i < lower.length; i++) {
                walk(path + ".lower[" + i + "]", lower[i], activeVariables);
            }
        }
    }

    private static void inspect(Class<?> recordType) {
        RecordComponent[] components = recordType.getRecordComponents();
        if (components == null) {
            throw new IllegalArgumentException("Expected a record declaration");
        }
        System.out.println("Record " + recordType.getSimpleName());
        for (RecordComponent component : components) {
            ComponentNote declaration =
                    component.getDeclaredAnnotation(ComponentNote.class);
            System.out.println("component " + component.getName()
                    + " | raw=" + component.getType().getTypeName()
                    + " | generic=" + component.getGenericType().getTypeName()
                    + " | declaration="
                    + (declaration == null ? "none" : declaration.value()));
            walk("type", component.getAnnotatedType(), new HashSet<>());
        }
    }

    public static void main(String[] args) {
        inspect(Sample.class);
        inspect(Recursive.class);
        System.out.println("String class TypeNote = "
                + String.class.getAnnotation(TypeNote.class));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 --release 17 -Xlint:all -Werror RecordAnnotatedTypeDemo.java
java RecordAnnotatedTypeDemo
```

Output:

```text
Record Sample
component name | raw=java.lang.String | generic=java.lang.String | declaration=declaration-only
type: java.lang.String notes=[text]
component tags | raw=java.util.List | generic=java.util.List<java.lang.String> | declaration=none
type: java.util.List<java.lang.String> notes=[list]
type.arg[0]: java.lang.String notes=[item]
component codes | raw=java.lang.String[] | generic=java.lang.String[] | declaration=none
type: java.lang.String[] notes=[array]
type.element: java.lang.String notes=[array-element]
component numbers | raw=java.util.List | generic=java.util.List<? extends java.lang.Number> | declaration=none
type: java.util.List<? extends java.lang.Number> notes=[]
type.arg[0]: ? extends java.lang.Number notes=[]
type.arg[0].upper[0]: java.lang.Number notes=[upper]
component sinks | raw=java.util.List | generic=java.util.List<? super java.lang.Integer> | declaration=none
type: java.util.List<? super java.lang.Integer> notes=[]
type.arg[0]: ? super java.lang.Integer notes=[]
type.arg[0].upper[0]: java.lang.Object notes=[]
type.arg[0].lower[0]: java.lang.Integer notes=[lower]
component quantity | raw=java.lang.Number | generic=T | declaration=none
type: T notes=[use-T]
type.bound[0]: java.lang.Number notes=[bound]
component plain | raw=java.lang.String | generic=java.lang.String | declaration=none
type: java.lang.String notes=[]
Record Recursive
component value | raw=java.lang.Comparable | generic=T | declaration=none
type: T notes=[]
type.bound[0]: java.lang.Comparable<T> notes=[]
type.bound[0].arg[0]: T notes=[]
type.bound[0].arg[0].bounds: cycle stopped
String class TypeNote = null
```

In the output, `notes` is the list of values for only the `TypeNote` annotation at the node under inspection. `declaration` is the value of only `ComponentNote` on the component declaration, or `none` when that annotation is absent.

The path labels `type`, `arg`, `element`, `upper`, `lower`, `bound` are chosen by the program to explain positions; they are not names required by the API.

## 5. Reading annotations on ordinary types and generic types

### Component `name`

The output has `declaration=declaration-only` from `ComponentNote`, and `type: java.lang.String notes=[text]` from `TypeNote`.

Both annotations are written close together in the header yet read through two different metadata objects. Do not use the result of one query to conclude that the other query must have the same annotation.

The last line `String class TypeNote = null` also shows that an annotation on a `String` type use in a record is not attached globally to `String.class`. It describes **the type use at this component**, without modifying the `String` class declaration.

### Component `tags`

The outermost type `List<...>` has `notes=[list]`. The first type argument `String` has `notes=[item]`, read at `type.arg[0]`.

To reach that position, the code uses [`AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html). The two annotations reside on two independent nodes; reading root annotations does not collect element annotations.

If a tool wants to apply different rules for the list and for the elements, it must retain the path of each annotation instead of only collecting a set of annotation names.

### Component `plain`

`plain` still has an `AnnotatedType` object describing `String`, even though the `TypeNote` list there is empty. The word "annotated" in the API name does not mean the type must carry at least one annotation.

Nor should you use the internal implementation class name of a Reflection object to infer type shape. The `AnnotatedType` interface and its subinterfaces are the surface to rely on.

## 6. Arrays: annotations on the array differ from annotations on the element

Component `codes` is declared:

```java
@TypeNote("array-element") String @TypeNote("array") [] codes
```

This is a header excerpt from the program, not a standalone field declaration to copy verbatim into a class.

The position before `String` marks the element type; the position before `[]` marks the array type. Therefore:

- The `type` node has `notes=[array]`.
- The `type.element` node has `notes=[array-element]`.

Stepping from the array to the element type uses [`AnnotatedArrayType.getAnnotatedGenericComponentType()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html). For multidimensional arrays, continue stepping through each array level rather than treating all square brackets as the same position.

This distinction has practical significance: a rule about the array reference and a rule about each element value are not the same requirement.

## 7. Wildcards: annotations can live on bounds

### Upper bounds

`numbers` has type `List<? extends @TypeNote("upper") Number>`. Neither the `List` node nor the wildcard node has `TypeNote`; the annotation is found on the upper bound `Number`, at `type.arg[0].upper[0]`.

If you query only the root of `AnnotatedType`, you will see an empty array and miss the needed metadata inside.

### Lower bounds

`sinks` has type `List<? super @TypeNote("lower") Integer>`. The output has an unmarked upper bound `Object`, together with a lower bound `Integer` carrying `notes=[lower]`.

That is why the walker checks both bound arrays via [`AnnotatedWildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html). Do not assume that seeing a wildcard means there must be an annotation on the wildcard root, or that only one bound side needs checking.

## 8. Type variables, bounds, and recursion

### Distinguishing a use of `T` from `T`'s bound

`Sample` declares `T extends @TypeNote("bound") Number`. Component `quantity` then uses `@TypeNote("use-T") T`.

The output cleanly separates:

- The `type: T` node carries `notes=[use-T]`.
- The `Number` bound node carries `notes=[bound]`.
- `getType()` of the component gives `Number`, while the declared generic type is `T`.

`getAnnotatedBounds()` on [`AnnotatedTypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedTypeVariable.html) takes you to the declared bounds of the type variable. Annotations on the type variable use and annotations on the bound are different pieces of information.

This metadata does not automatically replace `T` with `Integer` just because an object can be created with the type argument `Sample<Integer>`. If resolving types for a specific usage context is needed, the tool must receive and process that generic context additionally.

### Self-referential bounds

`Recursive<T extends Comparable<T>>` forms the relationship:

```text
T → Comparable<T> → T → Comparable<T> → ...
```

Therefore, when drilling down into bounds, the structure to process can be a graph with cycles, even though its initial presentation looks like a tree.

The walker uses `Set<TypeVariable<?>>` to track type variables currently on the active path. When encountering the same type variable again along that path, it still prints the node but stops expanding bounds and reports `cycle stopped`.

The type variable is removed from the set after finishing that branch. This is not a "seen somewhere across the whole type" set that automatically skips all future occurrences: separate uses can still carry different annotations and need to be observed.

Do not use the string name `"T"` alone as a universal identifier for a type variable, because different declarations can both name their variable `T`.

## 9. Application flow and limits of the example

When analyzing record components:

1. Confirm you have record metadata and obtain the right `RecordComponent`.
2. Read declaration annotations separately if the tool needs component-level semantics.
3. Obtain the root `component.getAnnotatedType()`.
4. At each node, read annotations on that node itself.
5. Branch on the type interface to traverse child nodes.
6. Preserve the path and include a stopping mechanism when expanding self-referential bounds.

The code also checks `getAnnotatedOwnerType()` when a type has a corresponding enclosing type. This is helpful for nested class structures with type information on the enclosing part. The main examples in this article focus on generics, arrays, wildcards, and type variables.

This is a metadata observer, not a data validator. An annotation named `NonNull` or a `TypeNote` value does not by itself cause the JVM to reject `null` or check each list element. To enforce rules, you need a processor with a clear contract.

Similarly, being able to read type metadata does not grant permission to access data fields, call accessors, or mutate state. This article does not need to interact with an instance's data.

## 10. Common pitfalls and self-check

| Pitfall | Fix |
| --- | --- |
| Reading only `RecordComponent.getAnnotations()` | Distinguish component declarations from type uses |
| Reading annotations only at the type root | Traverse to the exact generic, array, or bound position |
| Casting every type to `AnnotatedParameterizedType` | Check the actual interface with `instanceof` |
| Merging annotations on the array and element | Keep each level of `AnnotatedArrayType` separate |
| Seeing a wildcard yet ignoring bounds | Check both upper and lower bound arrays |
| Traversing generic bounds without cycle detection | Track type variables currently expanding on the active path |
| Assuming metadata on a used `String` is an annotation on `String.class` | Distinguish a type use from a class declaration |
| Assuming type metadata holds the runtime values of a record | Separate type analysis from data reading |

Try these small changes and predict the output:

1. Remove `@TypeNote("list")` while keeping `@TypeNote("item")`: why is the root empty while the element still has an annotation?
2. Swap the annotation positions between `String` and `[]` of `codes`: which nodes change?
3. Change `numbers` to an unbounded wildcard: which bound type does the walker observe?
4. Remove cycle detection and test `Recursive`: why might following only valid API calls still fail to terminate?
5. Add another `T` component with a different `TypeNote`: why should it not be skipped just because the name `T` was seen earlier?

The key point to grasp is that **an annotation belongs to a specific position in the type structure**. `getAnnotatedType()` is the entry point into that structure; the tool's job is to navigate to the right node, read the right metadata, and preserve the meaning of that position.
