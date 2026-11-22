# Traversing `AnnotatedParameterizedType`, `AnnotatedArrayType`, and Related Types with Reflection

In Java 8 and later, annotations can be placed not only on **class, field, or method declarations** but also at **type-use positions**: inside `List<...>`, before an array level `[]`, on a wildcard `?`, on an `extends` bound, or at the use site of a type variable `T`. When you need to read that metadata at runtime, `Field.getAnnotations()` or `Field.getGenericType()` is not enough.

Java provides the `java.lang.reflect.AnnotatedType` family of interfaces to represent **the type tree along with the annotations attached to each node**. To read everything, you must start from the root node and traverse down through branches such as `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedWildcardType`, and `AnnotatedTypeVariable`.

This article focuses on the mechanism of **traversing the `AnnotatedType` structure at runtime**, distinguishing the API classes, writing a traverser that works with Java 17+, and recognizing cases that are easy to miss.

## 1. Why Traverse the Type Tree?

Consider the field:

```java
@Mark("collection") List<@Mark("item") String> names;
```

The field has type `List<String>`, but the two annotations are in **different positions**:

- `@Mark("collection")` is on the type-use position of `List<String>` itself.
- `@Mark("item")` is at the type-use position of the type argument `String` inside `List<...>`.

Calling `field.getGenericType()` returns generic type information (`Type`), but **does not provide an API to read type annotations on each part**. Calling `field.getAnnotations()` targets **annotations on the field declaration**, which is also not the way to traverse the type-use annotation tree.

The appropriate approach:

```java
AnnotatedType root = field.getAnnotatedType();
```

From `root`, check whether it is an `AnnotatedParameterizedType`, then retrieve the annotated arguments via `getAnnotatedActualTypeArguments()`.

Similarly:

```java
String @Mark("outer") [] @Mark("inner") [] grid;
```

The two annotations preceding the two pairs of `[]` belong to **two separate array levels**, so you need to descend twice via `AnnotatedArrayType.getAnnotatedGenericComponentType()` to explore the structure. A single `AnnotatedType` does not automatically flatten all annotations in child levels.

## 2. The `AnnotatedType` API Framework

Every object in this family implements `java.lang.reflect.AnnotatedType`, and `AnnotatedType` extends `AnnotatedElement`.

| API | Purpose |
| --- | --- |
| `getType()` | Returns the underlying `Type` of the node (`Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType`, depending on the case). |
| `getAnnotation(Mark.class)` | Retrieves an annotation of type `Mark` **attached to the current node itself**, if present. |
| `getAnnotations()` / `getDeclaredAnnotations()` | Lists the annotations present on the type node under inspection, without descending into generic arguments or array components. |
| `getAnnotationsByType(...)` | Useful if the type annotation supports `@Repeatable`; can return occurrences applied via a container. |
| `getAnnotatedOwnerType()` | For member/nested types, provides the annotated *owner type* when present; many other type forms return `null`. |

`AnnotatedType` is an **interface**. The actual generic, array, or wildcard type determines the subinterface needed to traverse to the next nodes:

```text
AnnotatedType (current node)
├─ AnnotatedParameterizedType
│    └─ getAnnotatedActualTypeArguments() → each AnnotatedType
├─ AnnotatedArrayType
│    └─ getAnnotatedGenericComponentType() → component AnnotatedType
├─ AnnotatedWildcardType
│    ├─ getAnnotatedUpperBounds() → AnnotatedType[]
│    └─ getAnnotatedLowerBounds() → AnnotatedType[]
└─ AnnotatedTypeVariable
     └─ getAnnotatedBounds() → AnnotatedType[]
```

A plain type node such as `String`, `int`, or `Number` may only require reading the annotations on the node itself, with **no child branches** corresponding to the four interfaces above.

## 3. Obtaining the Root Node from Reflection

Depending on the Java element you want to read, the entry point is a different API:

| Metadata source | API to retrieve the annotated type |
| --- | --- |
| Field type | `Field.getAnnotatedType()` |
| Method return type | `Method.getAnnotatedReturnType()` |
| Method or constructor parameter types | `Executable.getAnnotatedParameterTypes()` |
| Method/constructor exception types | `Executable.getAnnotatedExceptionTypes()` |
| Receiver type (if present) | `Executable.getAnnotatedReceiverType()` |
| Declared superclass of a class | `Class.getAnnotatedSuperclass()` |
| Implemented interfaces | `Class.getAnnotatedInterfaces()` |
| Bounds of a type variable | `TypeVariable.getAnnotatedBounds()` |

The APIs above provide the **starting point**, after which you traverse the branches on `AnnotatedType` according to the actual type. An ordinary constructor **has no return type**, so it cannot be handled like `Method.getAnnotatedReturnType()`.

For method parameters, the order of `getAnnotatedParameterTypes()` corresponds to the order of the parameter types. Whether parameters have names or not, you can still read type annotations by position. For type-use metadata to exist at runtime, the annotation must have an appropriate retention policy, typically `@Retention(RetentionPolicy.RUNTIME)`.

## 4. `AnnotatedParameterizedType`: Descending into Generic Arguments

Example:

```java
List<@Mark("item") String> names;
Map<@Mark("key") String, List<@Mark("value") Integer>> lookup;
```

A generic type like `Map<String, List<Integer>>` has a **nested structure**:

```text
Map<String, List<Integer>>
  ├─ argument 0: String
  └─ argument 1: List<Integer>
       └─ argument 0: Integer
```

`AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` returns the `AnnotatedType` for each argument. You must traverse **recursively**, because an argument may itself be an `AnnotatedParameterizedType`, `AnnotatedArrayType`, wildcard, or type variable.

Illustrative code pattern, assuming `type` has already been determined:

```java
if (type instanceof AnnotatedParameterizedType parameterized) {
    AnnotatedType[] args =
            parameterized.getAnnotatedActualTypeArguments();

    for (int i = 0; i < args.length; i++) {
        visit(args[i], path + ".arg" + i);
    }
}
```

Difference between the two APIs:

- `((ParameterizedType) field.getGenericType()).getActualTypeArguments()` yields a plain `Type[]`.
- `((AnnotatedParameterizedType) field.getAnnotatedType()).getAnnotatedActualTypeArguments()` yields an `AnnotatedType[]` **that preserves type-use metadata**.

Do not cast blindly: a raw `List` has no concrete type arguments to descend into like `List<String>`, and `field.getAnnotatedType()` is not guaranteed to be an `AnnotatedParameterizedType`. Each branch must be identified using `instanceof`.

## 5. `AnnotatedArrayType`: Stepping Through Each Array Dimension

Consider the declaration:

```java
@Mark("element") String @Mark("outer") [] @Mark("inner") [] grid;
```

This is a two-dimensional array. From root to leaf:

```text
String[][]          annotation: outer
  └─ String[]       annotation: inner
       └─ String    annotation: element
```

`AnnotatedArrayType.getAnnotatedGenericComponentType()` moves from the **current array type** to its **immediate component type**, meaning it strips one `[]` level. Therefore, you must keep calling it while the component is still an `AnnotatedArrayType`:

```java
AnnotatedType root = field.getAnnotatedType();

AnnotatedType inner =
        ((AnnotatedArrayType) root).getAnnotatedGenericComponentType();

AnnotatedType element =
        ((AnnotatedArrayType) inner).getAnnotatedGenericComponentType();
```

Do not assume `getAnnotatedGenericComponentType()` immediately returns the final element type for every array. For a three-dimensional array, there will be three `AnnotatedArrayType` levels before reaching the non-array element.

Arrays containing generics are also valid in reference declarations, such as `List<@Mark("arg") String> @Mark("array") [] values;`. During traversal, the root branch is an `AnnotatedArrayType`, while the inner component is an `AnnotatedParameterizedType`. This is why the traverser must handle **combinations of multiple interfaces**, rather than checking only the root type name once.

## 6. `AnnotatedWildcardType`: Traversing `? extends` and `? super`

A wildcard is a generic argument with the syntax `?`, commonly used with an upper bound or a lower bound:

```java
List<@Mark("wild") ? extends @Mark("upper") Number> upperNumbers;
List<@Mark("wild") ? super @Mark("lower") Integer> lowerNumbers;
```

When accessing type argument index 0 of `List`, that node can be an `AnnotatedWildcardType`.

- `getAnnotatedUpperBounds()` returns the upper bounds that may carry annotations. For `? extends Number`, that is `Number`.
- `getAnnotatedLowerBounds()` returns the lower bounds; for `? super Integer`, that is `Integer`.
- When **no explicit upper bound is written**, the wildcard has an unannotated default upper bound of `Object`. Thus, for `? super Integer`, you can typically see an upper bound of `Object` and a lower bound of `Integer`.
- For an unbounded wildcard `?`, the lower bound is an empty array and the default upper bound is `Object`.

Annotations on `?` itself are not also annotations on `Number` or `Integer`. They are separate nodes; to see everything, you must read the wildcard's annotations and **continue traversing the bounds**.

```java
if (type instanceof AnnotatedWildcardType wildcard) {
    AnnotatedType[] upper = wildcard.getAnnotatedUpperBounds();
    AnnotatedType[] lower = wildcard.getAnnotatedLowerBounds();

    for (int i = 0; i < upper.length; i++) {
        visit(upper[i], path + ".upper" + i);
    }
    for (int i = 0; i < lower.length; i++) {
        visit(lower[i], path + ".lower" + i);
    }
}
```

## 7. `AnnotatedTypeVariable`: Distinguishing Uses of `T` from the Bounds of `T`

A type variable such as `T` is declared in a class or method. It can also be annotated at a **type-use position**:

```java
class Box<T extends @Mark("bound") Number> {
    @Mark("use") T item;
}
```

Here:

- `@Mark("use")` marks **the `T` node at field `item`**.
- `@Mark("bound")` marks **the `Number` type** in the declared bound `T extends Number`.
- `Field.getAnnotatedType()` of `item` can be an `AnnotatedTypeVariable`. Calling `getAnnotation(Mark.class)` on that node reads the marker at the use site of `T`; calling `getAnnotatedBounds()` descends into the bounds of the type variable.
- You can retrieve the bounds directly from the type parameter declaration via `Box.class.getTypeParameters()[0].getAnnotatedBounds()`.

Do not infer that an annotation on a **use of `T`** will automatically appear on the **declaration of type parameter `T`**, or vice versa. These use and declaration positions have distinct meanings.

A type variable with no explicit bound written has an unannotated default bound of `Object`. If there are intersection types, such as `T extends Number & Comparable<T>`, `getAnnotatedBounds()` can return **multiple bounds** in declaration order.

### Note on Recursion and Cycles

A recursive traverser can run indefinitely without safeguards, for example:

```java
class Recursive<T extends Comparable<T>> {
}
```

When following the bound of `T`, you encounter `Comparable<T>`; its generic argument is `T` again, which can lead back to the `Comparable<T>` bound once more.

For a general-purpose tool used in production, you should track the **type variables/bounds currently being traversed on the active branch**, or set a depth limit appropriate for the use case and record cycles. Do not use `getType().getTypeName()` as the sole key in all cases, because two **type uses** can have the same name yet carry different annotations.

## 8. Java 17+ Program: Traversing All Four `AnnotatedType` Forms

The following example implements a recursive `walk` method on type structures that do not create cycles. The method prints the path and `@Mark` value at **nodes that are actually marked**; it still passes through unannotated nodes to look for children.

Create the file **`AnnotatedTypeWalkDemo.java`**:

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
import java.lang.reflect.Field;
import java.lang.reflect.TypeVariable;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Mark {
    String value();
}

class Sample<T extends @Mark("bound") Number> {
    @Mark("list") List<@Mark("item") String> names;

    @Mark("cell")
    String @Mark("outer") [] @Mark("inner") [] grid;

    List<@Mark("wild") ? extends @Mark("upper") Number> maximums;

    List<@Mark("wildLower") ? super @Mark("lower") Integer> minimums;

    @Mark("useT") T current;
}

public class AnnotatedTypeWalkDemo {
    static void walk(AnnotatedType type, String path) {
        Mark mark = type.getAnnotation(Mark.class);
        if (mark != null) {
            System.out.println(path + "=" + mark.value());
        }

        if (type instanceof AnnotatedParameterizedType parameterized) {
            AnnotatedType[] args =
                    parameterized.getAnnotatedActualTypeArguments();
            for (int i = 0; i < args.length; i++) {
                walk(args[i], path + ".arg" + i);
            }
        } else if (type instanceof AnnotatedArrayType array) {
            walk(array.getAnnotatedGenericComponentType(),
                    path + ".component");
        } else if (type instanceof AnnotatedWildcardType wildcard) {
            AnnotatedType[] upper = wildcard.getAnnotatedUpperBounds();
            AnnotatedType[] lower = wildcard.getAnnotatedLowerBounds();
            for (int i = 0; i < upper.length; i++) {
                walk(upper[i], path + ".upper" + i);
            }
            for (int i = 0; i < lower.length; i++) {
                walk(lower[i], path + ".lower" + i);
            }
        } else if (type instanceof AnnotatedTypeVariable variable) {
            AnnotatedType[] bounds = variable.getAnnotatedBounds();
            for (int i = 0; i < bounds.length; i++) {
                walk(bounds[i], path + ".bound" + i);
            }
        }
    }

    static void walkField(String fieldName) throws Exception {
        Field field = Sample.class.getDeclaredField(fieldName);
        walk(field.getAnnotatedType(), fieldName);
    }

    public static void main(String[] args) throws Exception {
        walkField("names");
        walkField("grid");
        walkField("maximums");
        walkField("minimums");
        walkField("current");

        TypeVariable<?> typeParameter = Sample.class.getTypeParameters()[0];
        walk(typeParameter.getAnnotatedBounds()[0], "T.declaredBound");
    }
}
```

Compile and run from the directory containing the file with JDK 17 or later:

```bash
javac -encoding UTF-8 AnnotatedTypeWalkDemo.java
java AnnotatedTypeWalkDemo
```

**Expected stdout:**

```text
names=list
names.arg0=item
grid=outer
grid.component=inner
grid.component.component=cell
maximums.arg0=wild
maximums.arg0.upper0=upper
minimums.arg0=wildLower
minimums.arg0.lower0=lower
current=useT
current.bound0=bound
T.declaredBound=bound
```

Output analysis:

1. `names=list`: the root node `List<String>` carries `@Mark("list")`; `names.arg0=item`: the generic argument `String` carries `@Mark("item")`.
2. `grid=outer`: the outermost array type is the root node. Two `.component` steps reach the sub-array with `"inner"` and the element type with `"cell"`, respectively.
3. `maximums.arg0=wild`: the first type argument of `List` is the marked wildcard. `.upper0=upper` is `Number` in `? extends Number`.
4. `minimums.arg0=wildLower`: the wildcard of `List` has a lower bound `Integer` marked `"lower"`. The default upper bound `Object` does not have `@Mark`, so there is no line for it.
5. `current=useT`: the annotation is on the use of type variable `T`. `.bound0=bound` reaches `Number` in the declaration `T extends Number`.
6. `T.declaredBound=bound`: an alternative way to read the same bound directly from the `TypeVariable` object of the class declaration.

This method intentionally **prints only nodes with `@Mark`**, so unannotated nodes are still traversed without appearing in stdout. It does not include a cycle-detection step, because the `T extends Number` type in the example does not create recursion. For code that handles arbitrary inputs, add visited tracking as explained in section 7.

## 9. Deeper Traversal with Nested Generics and Generic Arrays

A **standalone syntax-illustration** example, assuming `@Mark` has already been declared:

```java
class MoreSamples {
    java.util.Map<
        @Mark("key") String,
        java.util.List<@Mark("value") Integer>
    > index;

    java.util.List<@Mark("item") String>
        @Mark("array") [] batches;
}
```

If you traverse the `index` field using the `walk` method in section 8, the path to `@Mark("value")` is **`index.arg1.arg0`**. You must go through the second argument of `Map`, then the first argument of `List`; inspecting only `Map` and one child level will miss the annotation on `Integer`.

For `batches`, the root node is an `AnnotatedArrayType` (marked `"array"`). The array component is an `AnnotatedParameterizedType` representing `List<String>`, and the `String` argument carries `"item"`. Expected paths:

```text
batches=array
batches.component.arg0=item
```

This shows that a traverser should check **the node kind at each step** and dispatch to the corresponding branch; do not assume that if a tree starts with a generic its children will always be generics, or if it starts with an array all children will remain arrays.

## 10. `getAnnotatedOwnerType()` and Nested Types

For a member type, Java also allows metadata to appear on the **owner type** (the enclosing type). For example, a structure like `Outer<T>.Inner<U>` can annotate both the owner `Outer<T>` and `Inner<U>`.

Since Java 9, `AnnotatedType.getAnnotatedOwnerType()` and the specialized interfaces support reading the annotated owner type when one exists. It is **different** from:

- `getAnnotatedActualTypeArguments()`: descends into `T` and `U`, which are the **type arguments**.
- `getAnnotatedGenericComponentType()`: steps through one array level.
- `getAnnotatedBounds()`: descends into the bounds of a wildcard or type variable.

For top-level classes/interfaces, arrays, wildcards, or type variables, the owner API typically returns `null`. A traverser that supports nested types can add:

```java
AnnotatedType owner = type.getAnnotatedOwnerType();
if (owner != null) {
    walk(owner, path + ".owner");
}
```

This is an **addition** to the `walk` method in section 8, not a standalone program. Use it only on Java 9+ if you want to maintain compatibility. Because owner structures can lead to nested type parameters, traverse branches with a cycle-prevention strategy when building a general-purpose tool.

## 11. Limitations and Common Pitfalls

| Situation | Correct Handling |
| --- | --- |
| Using `Field.getAnnotations()` and assuming type argument annotations were read | Use `Field.getAnnotatedType()` and traverse through `AnnotatedParameterizedType`. |
| Using `Field.getGenericType()` and calling `getAnnotation()` on `Type` | `Type` is a type model that does not implement the general `AnnotatedElement` interface; use `AnnotatedType` to read type-use annotations. |
| Casting every `AnnotatedType` to `AnnotatedParameterizedType` | Check `instanceof` at each node because children may be arrays, wildcards, type variables, or simple types. |
| For `String[][]`, calling `getAnnotatedGenericComponentType()` once and assuming you reached `String` | That only reaches `String[]`; you must step down one more array level. |
| Traversing only the upper bounds of a wildcard | Misses annotations on `? super ...`; examine both upper and lower bounds. |
| Inspecting only `@Mark` on `T` while ignoring the `T extends ...` bound | If bound metadata is needed, traverse `AnnotatedTypeVariable.getAnnotatedBounds()` or read from `TypeVariable.getAnnotatedBounds()`. |
| Traversing the bounds of `T extends Comparable<T>` without limits | Can cause infinite recursion; a cycle-detection mechanism is required. |
| Assuming `SOURCE`-retained annotations appear via Reflection | For runtime Reflection to read type annotations, `RUNTIME` retention is required. |
| Declaring an annotation only with `@Target(FIELD)` and placing it inside `<...>` or before `[]` | These positions require `TYPE_USE`, not just a target on field declarations. |
| Interpreting `getType()` as returning `Class<?>` in every case | It returns `Type`; it can be `ParameterizedType`, `GenericArrayType`, `WildcardType`, or `TypeVariable`. |
| Treating an annotation's runtime presence as automatic JVM nullness checking | Metadata is only information; a tool/framework is needed to interpret its meaning and enforce checks. |

### What Reflection Does Not Guarantee

Type annotations are preserved according to the annotation's retention policy and the metadata written by the compiler into the class file. Java Reflection does not turn every annotation in source code into an accessible object.

For example, standard Reflection **has no equivalent to `Field.getAnnotatedType()` for scanning every local variable inside a method body**. A tool performing deep local-variable/type-use analysis may need to process source code or bytecode using appropriate tooling. In addition, changes to generic structure after compilation (type erasure) make it impossible to retrieve **the actual generic type of individual elements in a `List` at runtime** merely by reading field type annotations.

`getAnnotatedType()` describes the type **declared on the field/method/class**, rather than inspecting the actual state or data of objects stored in the field.

## 12. How to Design a Safe `AnnotatedType` Traverser

When writing a reusable utility, you should follow this sequence:

1. **Choose the right entry point**: field, method return, parameter, superclass, or annotated bound.
2. **Read annotations on the current node** (for example, `getAnnotationsByType` for repeatable annotations or `getAnnotation` for single ones).
3. **Branch with `instanceof`** for parameterized, array, wildcard, and type variable nodes.
4. **Recursively traverse child nodes** and record the path: `.argN`, `.component`, `.upperN`, `.lowerN`, `.boundN`.
5. If needed, read the **owner type** using `getAnnotatedOwnerType()`.
6. **Guard against cycles** caused by self-referential generics and handle invalid metadata or missing dependent classes according to the tool's goals.
7. **Separate traversal from interpretation**: the traverser discovers annotations; other code decides what domain meaning an annotation like `"nullable"` or `"validated"` carries.

For a use case that only needs to read a field of type `List<@Mark String>`, you can access the first argument directly without a general-purpose recursive traverser. However, for multi-level trees such as `Map<String, List<@Mark Integer>[]>` or generics with wildcards/bounds, a structured traversal approach like the one in this article helps ensure type-use positions are not missed.

## 13. Self-Check

Given the illustrative field:

```java
java.util.List<
    @Mark("wild") ? extends @Mark("bound") Number
> @Mark("array") [] values;
```

Assume `Mark` has `@Target(TYPE_USE)` and `@Retention(RUNTIME)`. Determine:

1. Which interface does the root node `field.getAnnotatedType()` belong to? **`AnnotatedArrayType`**, because the field is an array `List<...>[]`.
2. Where is the `"array"` annotation located? **On the root array node itself**.
3. Which API moves from the array to `List<...>`? **`getAnnotatedGenericComponentType()`**.
4. Which API goes from `List<...>` to the wildcard `?`? **`getAnnotatedActualTypeArguments()[0]`** on `AnnotatedParameterizedType`.
5. Where is the `"wild"` marker located? **On the `AnnotatedWildcardType` node**.
6. Where is the `"bound"` marker located? **On `Number` returned by `getAnnotatedUpperBounds()[0]`**.
7. Can all markers be read using `Field.getAnnotations()`? **No**: those are metadata on type-use positions, so you must start from `getAnnotatedType()` and walk the tree.

Official Java 17 API documentation: [`AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html), [`AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html), [`AnnotatedArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html), [`AnnotatedWildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html), [`AnnotatedTypeVariable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedTypeVariable.html).
