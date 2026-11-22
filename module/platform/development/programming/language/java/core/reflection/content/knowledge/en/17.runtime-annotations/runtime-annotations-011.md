# `equals`, `hashCode`, and `annotationType` of Annotations in Java

## 1. Three methods answering three different questions

When Reflection reads an annotation at runtime, the result is not merely a few metadata fields; it is an **object implementing the annotation interface**. Every annotation interface implicitly extends `java.lang.annotation.Annotation`, so the obtained object has three core methods:

| Method | Question to answer | Meaning |
| --- | --- | --- |
| `annotationType()` | “Which **annotation interface** declared this annotation?” | Returns `Class<? extends Annotation>` of the annotation type, such as `Info.class` |
| `equals(Object other)` | “Do two annotations have the **same type and the same member values**?” | Compares by **semantic value**, not object address |
| `hashCode()` | “What is the hash value compatible with the annotation's `equals` rule?” | Specified by a formula over all members, including members using default values |

Example:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Info {
    String name();
    int level() default 1;
}
~~~

This is an illustrative declaration requiring `import java.lang.annotation.*`. An `@Info(name = "core")` annotation has **two members** in its comparison contract: `name = "core"` and `level = 1`. Omitting `level` in source code **does not remove this member** from `equals` or `hashCode`.

At runtime, annotations are typically retrieved via `AnnotatedElement` APIs:

~~~java
Info info = SomeClass.class.getAnnotation(Info.class);
if (info != null) {
    System.out.println(info.annotationType() == Info.class);
}
~~~

The illustrative snippet above assumes a class `SomeClass` and an `@Info` annotation retained until runtime. `getAnnotation` returns `null` if no matching annotation is found; do not call `equals`, `hashCode`, or `annotationType` before handling that case.

## 2. How does `annotationType()` differ from `getClass()`?

A runtime annotation is typically implemented by the JDK as an **object of a runtime-generated implementation class**, rather than an instance whose concrete class matches the annotation interface.

- `info.annotationType()` returns **`Info.class`** directly.
- `info.getClass()` returns the **runtime implementation class**, which may be a JDK-dependent proxy/implementation class. You should not make assumptions about its package name, class name, or implementation format.
- `info.annotationType() == Info.class` is the proper way to check which annotation interface is represented.
- `info.getClass() == Info.class` is not a valid check for the annotation type: `Info` is an interface, not the object's implementation class.

Use `Class<? extends Annotation>` for a general annotation type:

~~~java
Annotation any = element.getAnnotation(Info.class);
if (any != null) {
    Class<? extends Annotation> kind = any.annotationType();
    System.out.println(kind == Info.class);
}
~~~

This is an illustrative snippet inside a method that has `AnnotatedElement element` and `Info` in scope. Do not use `getClass()` as a key identifying annotation types when building metadata-scanning frameworks.

**Additional distinction:** `annotationType()` does **not** return the class where the annotation is placed. If `@Info` sits on `Service`, `annotationType()` is still `Info.class`, **not** `Service.class`. To know which target holds the annotation, keep the corresponding `AnnotatedElement` reference separately.

## 3. The `equals` contract: when are two annotations equal?

The `java.lang.annotation.Annotation` Javadoc specifies that two annotations are equal if and only if:

1. The compared object represents the **same annotation interface**.
2. **All corresponding members have equal values** according to the rules for each type.

There is no requirement that both annotations sit on the same class, same field, or same method. There is no requirement that the two values be written identically in source code if they carry the same value after applying defaults.

### 3.1. Default values also participate in comparison

~~~java
@Info(name = "core")
class A { }

@Info(name = "core", level = 1)
class B { }
~~~

Suppose `Info.level()` has `default 1` as in section 1. The annotations on `A` and `B` are **equal** under `equals` because all member values are identical. When calling `level()` on `A`'s annotation, the API returns 1.

This differs from comparing verbatim source code: `@Info(name = "core")` and `@Info(name = "core", level = 1)` are not identical textually, yet they have **equivalent annotation values**.

### 3.2. Comparing each member type

| Member type | Annotation `equals` rule |
| --- | --- |
| Primitive `boolean`, `byte`, `short`, `char`, `int`, `long` | Compared by value with `==` |
| `float`, `double` | By `Float.valueOf(x).equals(Float.valueOf(y))` or `Double.valueOf(x).equals(Double.valueOf(y))` |
| `String`, `Class`, enum | Uses `equals` of the corresponding value |
| Nested annotation inside annotation | Compared **recursively** with `equals` |
| One-dimensional array of permitted types | Uses the appropriate overload of `Arrays.equals` |

Note the **floating-point special case**: under the annotation contract, `NaN` is considered equal to itself, while `+0.0` and `-0.0` are distinguished when comparing `float`/`double` members. This rule differs from ordinary Java arithmetic `==`.

### 3.3. Array members compare **contents**, not identity

If an annotation has a member:

~~~java
int[] ids() default {1, 2};
~~~

then `ids = {1, 2}` equals `ids = {1, 2}` even if the arrays are created on separate accesses. However, `{1, 2}` **does not equal** `{2, 1}`, because `Arrays.equals` compares **element by element in order**.

Do not use `array1 == array2` or `array1.equals(array2)` to simulate the annotation contract yourself: both compare array references only. For `int[]`, use `Arrays.equals(int[], int[])`; for valid reference arrays, use the `Arrays.equals(Object[], Object[])` overload. The annotation contract selects the appropriate overload automatically.

In particular, an annotation member **cannot be a multidimensional array**; the permitted types are restricted to primitives, `String`, `Class`, enums, annotation interfaces, and one-dimensional arrays of those types. A member value cannot be `null`.

### 3.4. Matching member names alone is not enough

Two different annotation interfaces:

~~~java
@interface Alpha { String value(); }
@interface Beta  { String value(); }
~~~

even when used as `@Alpha("x")` and `@Beta("x")`, are **not equal**. `annotationType()` differs, so the first condition of `equals` fails. Identical member names or contents do not turn two distinct annotation types into one.

## 4. The annotation `hashCode` contract

`Annotation.hashCode()` is **not** the identity hash code of the proxy object. It is defined as the sum of hash values of **all annotation members**, including members using defaults.

For a member with name `n` and value `v`:

~~~text
memberHash = (127 * n.hashCode()) XOR valueHash(v)

annotationHash = sum of memberHash over all members
~~~

- `n.hashCode()` is `String.hashCode()` of the **member name**, e.g. `"name"`, not the annotation interface name.
- For primitives, `valueHash(v)` is `hashCode()` of the corresponding wrapper: `Integer`, `Boolean`, `Float`, `Double`, ...
- For `String`, `Class`, enum, or nested annotation, use `v.hashCode()` (nested annotations follow the same contract).
- For array members, use the corresponding overload of `Arrays.hashCode`; **do not use `Object.hashCode` on the array**.
- Arithmetic addition in Java uses `int` integers; overflow is allowed under Java integer arithmetic rules.

Annotation example:

~~~java
@interface Info {
    String name();
    int[] ids() default {1, 2};
}
~~~

For `@Info(name = "core")`, the corresponding hash formula is:

~~~java
int expectedHash =
        (127 * "name".hashCode() ^ "core".hashCode()) +
        (127 * "ids".hashCode() ^ Arrays.hashCode(new int[]{1, 2}));
~~~

This is an illustrative snippet inside a method importing `java.util.Arrays`, not a standalone application. The XOR operator `^` applies per member, and then the two memberHashes are **added**. The default `ids` value `{1, 2}` **still participates** in `hashCode`.

**Mandatory consequence:** if `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must be `true`. The converse is **not guaranteed**, because two distinct values can still collide in hash code. Never use `hashCode` alone as proof that two annotations are equal.

Do not hardcode a specific integer hash code when writing business logic; use `equals`, and if computing by hand for learning, follow the exact Javadoc formula.

## 5. Complete Java 17+ example: equality, defaults, arrays, and HashMap

Create the file **`AnnotationIdentityDemo.java`**:

~~~java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

public class AnnotationIdentityDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Info {
        String name();
        int[] ids() default {1, 2};
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface OtherInfo {
        String name();
        int[] ids() default {1, 2};
    }

    @Info(name = "core")
    static class DefaultValues { }

    @Info(name = "core", ids = {1, 2})
    static class ExplicitValues { }

    @Info(name = "core", ids = {2, 1})
    static class Reordered { }

    @Info(name = "other")
    static class DifferentName { }

    @OtherInfo(name = "core")
    static class DifferentType { }

    public static void main(String[] args) {
        Info first = DefaultValues.class.getAnnotation(Info.class);
        Info equivalent = ExplicitValues.class.getAnnotation(Info.class);
        Info reordered = Reordered.class.getAnnotation(Info.class);
        Info different = DifferentName.class.getAnnotation(Info.class);
        Annotation other = DifferentType.class.getAnnotation(OtherInfo.class);

        int expectedHash =
                (127 * "name".hashCode() ^ "core".hashCode()) +
                (127 * "ids".hashCode() ^ Arrays.hashCode(new int[]{1, 2}));

        Map<Info, String> index = new HashMap<>();
        index.put(first, "found");

        System.out.println("same annotation type: " +
                (first.annotationType() == Info.class));
        System.out.println("getClass is annotation type: " +
                (first.getClass() == Info.class));
        System.out.println("omitted default equals explicit: " +
                first.equals(equivalent));
        System.out.println("matching hashCode: " +
                (first.hashCode() == equivalent.hashCode()));
        System.out.println("contract hash formula: " +
                (first.hashCode() == expectedHash));
        System.out.println("reversed array: " + first.equals(reordered));
        System.out.println("different member: " + first.equals(different));
        System.out.println("different annotation interface: " +
                first.equals(other));
        System.out.println("map lookup: " + index.get(equivalent));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 AnnotationIdentityDemo.java
java AnnotationIdentityDemo
~~~

Output:

~~~text
same annotation type: true
getClass is annotation type: false
omitted default equals explicit: true
matching hashCode: true
contract hash formula: true
reversed array: false
different member: false
different annotation interface: false
map lookup: found
~~~

**Explaining each check:**

1. `first.annotationType() == Info.class` is `true`. Conversely, `first.getClass() == Info.class` is `false` because `getClass()` points to the annotation object's implementation class, not the annotation interface itself.
2. `@Info(name = "core")` and `@Info(name = "core", ids = {1, 2})` share the same type and all member values. The default `ids` is included in the contract, so `equals` is `true`.
3. Two equivalent annotations have equal `hashCode`s. The formula `127 * memberName.hashCode() XOR memberValueHash`, summed across all members, produces `first`'s exact hash.
4. `{2, 1}` and `{1, 2}` hold the same set of elements in **different order**, so `equals` returns `false`.
5. Changing `name` from `"core"` to `"other"` changes a member value, so `equals` returns `false`.
6. `@OtherInfo(name = "core")` has the same name and default member values yet is a **different annotation interface**; `equals` remains `false`.
7. `HashMap<Info, String>` stores under `first` and retrieves via `equivalent` successfully thanks to the `equals`/`hashCode` contract, **without requiring the same object identity**.

The example intentionally avoids printing the proxy class name or `toString()` order, because those are not properties to rely upon in application design.

## 6. Difference between annotation interface and annotation value

An annotation interface is a type declaration, for example:

~~~java
@interface Security {
    String role();
    boolean enabled() default true;
}
~~~

Each runtime annotation object holds **member values** matching that declaration. `role()` and `enabled()` are zero-parameter member methods, not ordinary Java fields whose values can be mutated arbitrarily.

- `Security.class`: type token (annotation interface).
- `someAnnotation.annotationType()`: type token of the annotation the object represents.
- `someAnnotation.role()`: reads a member value from the annotation object.
- `someAnnotation.equals(other)`: compares **both the type and all member values**.
- `someAnnotation.hashCode()`: hash from all member values per the standard formula.

On an annotation interface, member methods can declare a `default` value. This differs from the `default` keyword on Java interface methods with bodies. Annotation members do not execute dynamic business logic like regular methods.

**`@Retention(RetentionPolicy.RUNTIME)` is required** when retrieving annotations via runtime Reflection APIs such as `Class.getAnnotation`, `Method.getDeclaredAnnotation`, and `Field.getAnnotation`. Annotations with `SOURCE` or `CLASS` retention are not exposed as normal runtime annotations through these APIs.

`@Target` defines where an annotation can be placed. It does not change the `equals` and `hashCode` formulas for annotations of the same type once read.

## 7. Using `annotationType()`, `equals`, and `hashCode` in frameworks

### Grouping annotations by type

A framework scanning multiple members may use:

~~~java
Annotation annotation = element.getAnnotation(Security.class);
if (annotation != null) {
    Class<? extends Annotation> type = annotation.annotationType();
    // type is Security.class.
}
~~~

This is an illustrative snippet inside a method that already has `AnnotatedElement element`, with `Security` declared as in the example above and retained until runtime.

If you need a set of **present annotation interfaces**, use `Set<Class<? extends Annotation>>` containing `annotationType()`, rather than `getClass()`. The same annotation interface can appear under many different annotation objects; type and value are two separate data dimensions.

### Using annotations as keys

Thanks to the value-based comparison contract, a runtime annotation can be used as a `Map` key or `Set` element, within appropriate annotation data boundaries:

~~~java
Map<Info, String> descriptions = new HashMap<>();
descriptions.put(infoA, "configuration");
String found = descriptions.get(infoB);
~~~

This snippet illustrates with `infoA` and `infoB` already typed as `Info`. If they are `equals`, the lookup finds the same entry.

Even so, **do not use `annotation.hashCode()` instead of `equals` to determine equivalence**: hashes can collide. If creating a custom implementation of an annotation interface, follow the full `Annotation` contract (especially array comparison, default values, annotation type, and hash formula). An inaccurate implementation can cause `HashMap` or `HashSet` to behave incorrectly.

### When you just want all annotations?

`element.getAnnotations()`, `getDeclaredAnnotations()`, and `getAnnotationsByType(...)` handle **finding annotations** under distinct rules for direct declarations, inheritance, or repeatable annotations. Once you have an annotation object, its `equals`, `hashCode`, and `annotationType` contracts remain the contract in `java.lang.annotation.Annotation`.

Do not confuse **filtering where an annotation is placed** with **comparing annotation values**. Two identical annotations placed on different classes can still have `equals == true`.

## 8. Common mistakes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| Using `a == b` to verify two annotations have the same contents | `==` compares object identity | Use `a.equals(b)` |
| Using `a.getClass()` to identify the annotation type | Returns implementation class | Use `a.annotationType()` |
| Comparing only explicitly written members | Members using defaults also have values | Compare all members per contract |
| Using `intArray.equals(otherIntArray)` | Arrays do not override `Object.equals` to compare contents | Use `Arrays.equals` |
| Treating `ids={1,2}` as equal to `ids={2,1}` | Order in array members matters | Compare position by position |
| Using equal `hashCode` to assert annotations are equal | Hash collisions can occur | Compare with `equals` |
| Confusing `annotationType()` with the annotated class | One is the annotation type, the other is the annotated element | Track `AnnotatedElement` separately |
| Depending on `annotation.toString()` or proxy class names | Javadoc requires no fixed display string/implementation | Read member values via API |
| Computing array hash with `array.hashCode()` | Identity hash violates the contract | Use the appropriate `Arrays.hashCode` |
| Not checking `getAnnotation` for `null` | When absent, calling a member throws NPE | Check for `null` first |

### Advanced note: `float` and `double`

For an annotation with a `double threshold()` member, do not simulate `equals` using purely the `==` operator. Per the `Annotation.equals` Javadoc:

- `Double.NaN` compared with `Double.NaN` is considered **equal** for annotation members.
- `+0.0` and `-0.0` are considered **not equal** for annotation members.
- `hashCode` for floating-point members uses `Float.hashCode` / `Double.hashCode` via the wrapper, consistent with the `equals` rule.

This is why you should rely on the `Annotation` contract instead of writing a “looks equivalent” comparator yourself.

## 9. Checklist when working with runtime annotations

1. Confirm the annotation has `@Retention(RUNTIME)` and an appropriate target.
2. Retrieve the annotation using the right Reflection API: `getAnnotation`, `getDeclaredAnnotation`, or `getAnnotationsByType` as needed.
3. Check that the result is non-`null`.
4. If you need to **identify the annotation interface**, use `annotationType()`.
5. If you need to **compare two annotations**, use `equals()`, not identity and not `toString()` comparison.
6. If using as keys in `HashMap`/`HashSet`, rely on the spec-compliant `equals`/`hashCode` pair; never use a hash number as a unique identifier.
7. When testing, include at least one **default value** case, one **array member** case, and one **different annotation interface** case.
8. Do not write logic depending on the class name or internal implementation structure of annotation proxies.

### Self-check questions

**1.** Is `@Config(value="x")` with `int level() default 1` equal to `@Config(value="x", level=1)`?  
**Yes**, if they are the same annotation interface and all other member values also match.

**2.** Can two annotations placed on two different classes be `equals`?  
**Yes**, because where an annotation is placed is not a member value participating in comparison.

**3.** One annotation has `int[] ids()` returning `{1,2}`, another returns `{2,1}`. Are they equal?  
**No**, because `Arrays.equals` considers element order.

**4.** When `a.equals(b)` is `true`, must `a.hashCode() == b.hashCode()` be `true`?  
**Yes**. However, matching hashCodes are **not** sufficient to imply `equals`.

**5.** To know whether an annotation was declared by `@interface Role` or `@interface Policy`, which API should be used?  
**`annotationType()`**, not `getClass()`.

**6.** Is an array member's hash code computed via `array.hashCode()` or `Arrays.hashCode(array)`?  
**`Arrays.hashCode(array)`**, using the overload matching the array type.

**7.** If an annotation lacks `@Retention(RUNTIME)`, will Reflection definitely see it at runtime?  
**No.** Appropriate retention must be configured for standard Reflection APIs to return the annotation.

**Final takeaway:** `annotationType()` identifies the **annotation type**; `equals()` compares **type and all member values** (including defaults and array contents); `hashCode()` encodes that exact contract. All three belong to `java.lang.annotation.Annotation`—do not rely on object identity or runtime implementation class names.

### Official references

- [Java SE 17 — `java.lang.annotation.Annotation`: `equals`, `hashCode`, `annotationType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html)
- [Java SE 17 — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [Java SE 17 — `RetentionPolicy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html)
- [Java Language Specification §9.6 — Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6)