# Java Annotation `equals` Semantics: Same Type and Element-by-Element

An annotation in Java is not compared by where it is applied, the name of the annotated class, or the string representation of the annotation. According to the contract of the `java.lang.annotation.Annotation` interface, **two annotation objects are logically equal (`equals` returns `true`) when they belong to the same annotation interface and every corresponding element has an equal value according to the rule specific to that element's type**.

For example:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Role {
    String value();
    int priority() default 1;
}

@Role("ADMIN")
class AdminPage {}

@Role(value = "ADMIN", priority = 1)
class AdminDashboard {}
```

When reading the two annotations via reflection, `equals` returns `true`: same `Role` type, same `value()`, and same `priority()` (one uses the default value, while the other specifies it explicitly). The fact that the annotations appear on **two different classes** does not make them different.

Conversely, if even **a single element** differs in value, `equals` will return `false`; annotations with the same element names and the same values but belonging to **two different annotation interfaces** are also not equal.

## 1. An Annotation Is an Interface Type with Its Own equals Contract

The annotation declaration:

```java
@interface Config {
    String name();
    int retries() default 3;
}
```

defines an **annotation interface** named `Config` with two elements `name()` and `retries()`. When `@Config(name = "job")` is used on a class, `name()` receives `"job"` and `retries()` receives the default `3`.

If `@Config` has `@Retention(RUNTIME)` and is applied where Java reflection supports it, we can obtain the annotation object:

```java
Config config = SomeClass.class.getAnnotation(Config.class);
```

The variable `config` is a reference to an object implementing the `Config` annotation interface. Java/JDK may use an internal implementation class (often proxy-based), but **implementation details are not the basis for comparison**. The `Annotation` API specifies `equals(Object)`, `hashCode()`, `toString()`, and `annotationType()` for these objects.

Key points to remember:

- `==` asks whether two references refer to **the same object**.
- `equals(Object)` asks whether two annotations logically have **the same type and the same set of element values**.
- `annotationType()` indicates the exact **annotation interface** of an object; `getClass()` may point to an internal implementation class and is not a substitute for `annotationType()`.
- `hashCode()` must follow a specific formula so that equal annotations have equal hash codes.

Do not use `==`, `System.identityHashCode`, `getClass()`, or `toString()` to define equivalence between annotations yourself.

## 2. Formal Rules of Annotation.equals

The contract in Java SE 17 can be expressed as a logical condition:

```text
a.equals(b) == true
    if and only if:
    1. b is an annotation object belonging to the same annotation interface as a;
    2. for each element m of that interface:
       the value a.m() equals the value b.m() according to the rules for m's type.
```

The comparison is **by each element with a defined name and value**, not based on the order in which `name = value` pairs are written in the source.

Rule table:

| Element return type | Rule for comparing two element values |
|---|---|
| `boolean`, `byte`, `short`, `char`, `int`, `long` | Equivalent to the `==` operator for the two corresponding primitive values |
| `float` | `Float.valueOf(x).equals(Float.valueOf(y))` |
| `double` | `Double.valueOf(x).equals(Double.valueOf(y))` |
| `String` | `x.equals(y)` |
| `Class` (e.g., `Class<?>`, `Class<? extends X>`) | `x.equals(y)` |
| Enum | `x.equals(y)`; the same enum constant of the same type will be equal |
| Nested annotation | `x.equals(y)` **recursively according to the annotation contract** |
| One-dimensional array of a valid element type | Appropriate overload of `Arrays.equals(x, y)` |

These are **rules specified by the Java API**, not a framework option or the way the JDK happens to print annotations in logs.

### Different Annotation Types: Stopping at the First Condition

```java
@interface Primary {
    int value();
}

@interface Secondary {
    int value();
}

@Primary(7)
class A {}

@Secondary(7)
class B {}
```

Even though both have a `value()` element holding the number `7`, the two objects reflected from `@Primary` and `@Secondary` **are not equal** because `Primary` and `Secondary` are different annotation interfaces.

Even when two annotation interfaces have the same simple name in **two different packages**, they are still two different Java types. In complex class loader scenarios, Java type identity also depends on the class loader that defines that type; equality cannot be determined from the display name alone.

## 3. Default Values Are Fully Included in the Comparison

An annotation element can have a `default`:

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Job {
    String name();
    int attempts() default 3;
    String[] labels() default {};
}

@Job(name = "sync")
class JobA {}

@Job(name = "sync", attempts = 3, labels = {})
class JobB {}
```

The two annotations have logically equal values because `JobA` receives the default values, while `JobB` declares those exact same values explicitly.

A frequently misunderstood point is that **"not writing an element" does not mean "missing a value when equals runs"**. If an element has a `default`, the annotation's accessor returns the default value; `equals` and `hashCode` also include that element just like any other element.

Therefore:

- `@Job(name="sync")` equals `@Job(name="sync", attempts=3, labels={})`.
- `@Job(name="sync", attempts=4)` is **not** equal to the two annotations above.
- `@Job(name="sync", labels={"x"})` is **not** equal to an annotation with an empty `labels()` array.

Java does not keep an "author explicitly wrote the value flag" as part of the `Annotation.equals` condition. Two different ways of writing the annotation that resolve to the same values are considered equivalent.

### Order of Element Pairs Makes No Difference

```java
@Job(name = "sync", attempts = 3, labels = {"ops"})
class OrderedA {}

@Job(labels = {"ops"}, attempts = 3, name = "sync")
class OrderedB {}
```

The two cases are equal. Even if the order in which the element pairs are listed in the source changes, the **elements with the same name** still carry the same values.

This is **different** from the order of elements **inside an array**: section 5 explains why `{"a", "b"}` differs from `{"b", "a"}`.

## 4. Primitives, float/double: Watch Out for NaN and the Sign of Zero

For integer, character, and boolean element types, the rule is equivalent to the `==` operator. However, Java has special rules for `float` and `double` to satisfy the consistency properties of equality:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Rate {
    double value();
}

@Rate(0.0)
class PositiveZero {}

@Rate(-0.0)
class NegativeZero {}

@Rate(Double.NaN)
class NotANumberA {}

@Rate(Double.NaN)
class NotANumberB {}
```

For the `Rate` objects reflected from the four classes above:

| Comparison | Result |
|---|---|
| `@Rate(0.0)` and `@Rate(-0.0)` | `false` |
| `@Rate(Double.NaN)` and `@Rate(Double.NaN)` | `true` |
| `0.0 == -0.0` with normal primitive comparison | `true` |
| `Double.NaN == Double.NaN` | `false` |

Why? The `Annotation.equals` contract for `double` invokes the logic `Double.valueOf(x).equals(Double.valueOf(y))`, rather than using the `==` operator directly. Similarly, for `float`, it uses `Float.valueOf(...).equals(...)`. These two wrappers distinguish `+0.0` and `-0.0`, while treating `NaN` values as equal by definition of equality.

This is an **essential exception**; one should not reuse the `==` rule for all primitives if implementing an object compatible with the `Annotation` interface yourself.

The symbols `Double.NaN` and `Float.NaN` are appropriate constants when declaring annotation elements. If you want to verify this, the complete example in section 7 checks both the NaN and signed zero cases.

## 5. Arrays: Arrays.equals, Not Object.equals

Annotations allow elements whose type is a **one-dimensional array** of valid element types:

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Permissions {
    String[] roles();
}

@Permissions(roles = {"READ", "WRITE"})
class EndpointA {}

@Permissions(roles = {"READ", "WRITE"})
class EndpointB {}

@Permissions(roles = {"WRITE", "READ"})
class EndpointC {}
```

The annotation contract compares array contents with the corresponding overload of `Arrays.equals`:

- `EndpointA` and `EndpointB` are equivalent because the elements have the same count, matching positions, and equal values.
- `EndpointA` and `EndpointC` are **different** because the order of the two strings is reversed.
- An array `{}` equals another array `{}`, even though they are two separate array objects.
- An array `{"READ"}` differs from `{"READ", "WRITE"}`.

**Do not use `array1.equals(array2)` to simulate `Annotation.equals` yourself**. Java arrays do not override `Object.equals` to compare contents: two arrays with different references generally have `array1.equals(array2) == false` even if `Arrays.equals(array1, array2) == true`.

```java
import java.util.Arrays;

String[] left = {"READ", "WRITE"};
String[] right = {"READ", "WRITE"};

System.out.println(left.equals(right));           // false
System.out.println(Arrays.equals(left, right));    // true
```

Similarly, for `int[]`, `double[]`, `Class<?>[]`, `enum[]`, or arrays of nested annotations, the contract uses the **correct overload** of `Arrays.equals`. For an array of annotations, comparing each element in turn invokes `equals` on the nested annotation, creating a recursive mechanism.

Annotation elements **cannot** be declared as `String[][]` or arbitrary multidimensional arrays. Therefore, do not suggest using `Arrays.deepEquals` as a general rule for annotations: the specification requires `Arrays.equals`, which matches the one-dimensional arrays that annotations support.

## 6. String, Class, enum, and Nested Annotations

Valid reference types of annotation elements are compared using `x.equals(y)`:

**String:** same character sequence according to `String.equals`; it does not matter where the two literals come from.

**Class:** compares class tokens. For example, `String.class` equals `String.class`, but `String.class` does not equal `Integer.class`. In addition to type relationships, class token identity is determined by Java's class loading mechanism; do not compare using `getSimpleName()`.

**Enum:** enum constants of the same type and the same value are equal; having the same constant name in **two different enum types** does not make them the same type.

**Nested annotations:** comparison continues by applying the same set of rules to the elements of the child annotation.

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Owner {
    String team();
}

@Retention(RetentionPolicy.RUNTIME)
@interface ServiceInfo {
    Class<?> type();
    Owner owner();
}

@ServiceInfo(type = String.class, owner = @Owner(team = "core"))
class ServiceA {}

@ServiceInfo(type = String.class, owner = @Owner(team = "core"))
class ServiceB {}

@ServiceInfo(type = String.class, owner = @Owner(team = "billing"))
class ServiceC {}
```

`ServiceA` equals `ServiceB` under `ServiceInfo.equals`. `ServiceC` differs because `owner()` is an `Owner` annotation whose `team()` does not match. Essentially:

```text
ServiceInfo A vs ServiceInfo B
  same annotationType(ServiceInfo)
  type(): Class equals -> true
  owner(): Owner.equals -> true
     Owner.team(): String.equals -> true
  ==> ServiceInfo.equals -> true
```

A nested annotation can further contain arrays or sub-annotations; the rules still apply according to each element's type. However, every leaf branch must use value types permitted by the JLS for annotation elements; you cannot declare a `Map<String, Object>` to hold arbitrary data and expect the `Annotation.equals` contract to handle it.

## 7. Runnable Java 17+ Example: Testing the Full Contract

Create a single file **`AnnotationEqualsDemo.java`**:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.util.Arrays;

enum Stage { DEV, PROD }

@Retention(RetentionPolicy.RUNTIME)
@interface Details {
    String owner();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Policy {
    String name();
    int level() default 3;
    String[] roles() default {};
    Class<?> target() default String.class;
    Stage stage() default Stage.DEV;
    Details details() default @Details(owner = "team");
    double rate() default 0.0;
    double sample() default Double.NaN;
}

@Policy(name = "reader", roles = {"USER", "AUDITOR"})
class First {}

@Policy(
    sample = Double.NaN,
    rate = +0.0,
    details = @Details(owner = "team"),
    stage = Stage.DEV,
    target = String.class,
    roles = {"USER", "AUDITOR"},
    level = 3,
    name = "reader"
)
class SameValues {}

@Policy(name = "reader", roles = {"AUDITOR", "USER"})
class DifferentOrder {}

@Policy(name = "reader", roles = {"USER", "AUDITOR"}, rate = -0.0)
class NegativeZero {}

@Policy(name = "reader", roles = {"USER", "AUDITOR"},
        details = @Details(owner = "ops"))
class DifferentNested {}

@Retention(RetentionPolicy.RUNTIME)
@interface Label { int value(); }

@Retention(RetentionPolicy.RUNTIME)
@interface OtherLabel { int value(); }

@Label(7)
class Labeled {}

@OtherLabel(7)
class OtherLabeled {}

public class AnnotationEqualsDemo {
    public static void main(String[] args) {
        Policy a = First.class.getAnnotation(Policy.class);
        Policy b = SameValues.class.getAnnotation(Policy.class);
        Policy c = DifferentOrder.class.getAnnotation(Policy.class);
        Policy d = NegativeZero.class.getAnnotation(Policy.class);
        Policy e = DifferentNested.class.getAnnotation(Policy.class);

        System.out.println("same type and values: " + a.equals(b));
        System.out.println("same hashCode: " + (a.hashCode() == b.hashCode()));
        System.out.println("default values included: "
                + (a.level() == b.level()));
        System.out.println("array contents: "
                + Arrays.equals(a.roles(), b.roles()));
        System.out.println("array Object.equals: "
                + a.roles().equals(b.roles()));
        System.out.println("different array order: " + a.equals(c));
        System.out.println("plus zero vs minus zero: " + a.equals(d));
        System.out.println("different nested value: " + a.equals(e));
        System.out.println("nested annotation equals: "
                + a.details().equals(b.details()));
        System.out.println("NaN member equals: "
                + Double.valueOf(a.sample())
                        .equals(Double.valueOf(b.sample())));
        System.out.println("different annotation types: "
                + Labeled.class.getAnnotation(Label.class)
                    .equals(OtherLabeled.class.getAnnotation(
                            OtherLabel.class)));
        System.out.println("null equals: " + a.equals(null));
        System.out.println("annotationType: "
                + (a.annotationType() == Policy.class));
    }
}
```

Compile and run with Java 17 (or a newer JDK that supports `--release 17`):

```bash
javac --release 17 -Xlint:all AnnotationEqualsDemo.java
java AnnotationEqualsDemo
```

Exact output:

```text
same type and values: true
same hashCode: true
default values included: true
array contents: true
array Object.equals: false
different array order: false
plus zero vs minus zero: false
different nested value: false
nested annotation equals: true
NaN member equals: true
different annotation types: false
null equals: false
annotationType: true
```

This program tests multiple points at once:

1. **Two different classes, one annotation value:** `First` and `SameValues` are annotated with `Policy` where all elements have equivalent values. One relies on defaults, while the other specifies them explicitly and reorders the pairs. `a.equals(b) == true`.
2. **Consistent `hashCode`:** because `a.equals(b)` is true, the two hash codes must be equal.
3. **Arrays:** `Arrays.equals(a.roles(), b.roles())` is true; `a.roles().equals(b.roles())` is false because that is `Object.equals` on the two returned arrays. The order of `roles` in `DifferentOrder` differs, so `a.equals(c)` is false.
4. **Floating-point numbers:** `+0.0` and `-0.0` are treated as different according to `Double.equals`. `Double.NaN` on both sides is treated as the same value.
5. **Nested annotations:** two `@Details(owner="team")` instances are equivalent; differing with `"ops"` makes the entire `Policy` unequal.
6. **Two different interfaces:** `@Label(7)` and `@OtherLabel(7)` are different, regardless of having the same `value()` element equal to 7.
7. **Comparing with null:** `a.equals(null)` is false.
8. **Type identity:** `a.annotationType() == Policy.class` returns true.

Because the code applies `@Retention(RUNTIME)` to all the annotations to be read, reflection can retrieve them. Do not take a `null` result from `getAnnotation(...)` on a SOURCE/CLASS annotation to draw conclusions about the comparison; when no runtime object exists, there are not yet two annotations on which to call `equals`.

## 8. Aligning equals with hashCode

The `Annotation.hashCode()` contract is also specifically defined. For an annotation with elements `m`, the hash code is the sum of the contributions of each element, **including elements receiving default values**.

Formula for each element:

```text
memberHash =
    (127 * memberName.hashCode()) XOR memberValueHash

annotationHash = sum of memberHash across all elements
```

Here `XOR` is the bitwise XOR of integers (`^` in Java). Multiplication/summation operates on Java `int` integers.

`memberValueHash` is computed according to the value type:

| Value | How the hash is obtained |
|---|---|
| Primitive | Hash via the corresponding wrapper: `Integer.valueOf(v).hashCode()`, `Float.valueOf(v).hashCode()`, etc. |
| `String`, `Class`, enum, nested annotation | `v.hashCode()` (nested annotation is further computed according to the annotation rule) |
| Array | `Arrays.hashCode(v)` with the appropriate overload |

Example illustrating how each member is calculated:

```java
import java.util.Arrays;

int namePart = (127 * "name".hashCode()) ^ "reader".hashCode();
int rolesPart = (127 * "roles".hashCode())
        ^ Arrays.hashCode(new String[]{"USER", "AUDITOR"});
```

These are only two contributions of the `Policy` annotation in the runnable example. To compute the **entire** hash code, you must also add the elements `level`, `target`, `stage`, `details`, `rate`, and `sample`, even when they use `default` values.

Practical consequences:

- If `a.equals(b) == true`, then `a.hashCode() == b.hashCode()` is **mandatory**.
- Two annotations **may** have the same hash code without being equal (hash collision), so do not use `hashCode` alone to replace `equals`.
- You cannot omit array contents, default values, or nested annotations when computing the hash code of an object claiming compatibility with the `Annotation` interface.
- `Arrays.hashCode` for arrays must match the corresponding `Arrays.equals` operation; using only the array's identity hash code will break the contract.

In a `HashMap<Policy, Value>` or `HashSet<Policy>`, the `equals/hashCode` logic explains why two annotations from **two different placement locations** can behave as an equivalent key. You can use annotations as keys if it makes sense for your design, but you should clearly understand how annotation versions/definitions and class loader scope affect type identity.

## 9. equals Does Not Depend on Placement, How It Is Written, or Formatting

The equals condition **does not ask**:

- Whether the annotation is placed on class `A` or class `B`.
- Whether an element is written explicitly or uses `default`.
- The order of `key = value` pairs in the source.
- Whitespace, line breaks, or character formatting of the annotation in the source.
- The order in which a tool displays the elements via `toString()`.
- How many other places in the program use an annotation with the same contents.

For example:

```java
@Role(value = "ADMIN", priority = 1)
class MenuOne {}

@Role(priority = 1, value = "ADMIN")
class MenuTwo {}
```

If `Role` has RUNTIME retention, the two values retrieved from `MenuOne` and `MenuTwo` are equivalent. A metadata-reading tool that needs semantic comparison should use `equals`, rather than performing string comparison based on `annotation.toString()`.

`Annotation.toString()` is standardized to the extent of returning **a string representation**, but **the representation details depend on the implementation**. It is useful for debugging, not as a serialization standard/identifier for equality.

## 10. @Inherited and @Repeatable Do Not Change the equals Contract

The `@Inherited` and `@Repeatable` meta-annotations affect **how annotations are discovered**, rather than changing the equals definition of a pair of retrieved annotation objects.

### @Inherited: The Source of the Retrieved Annotation May Differ

```java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Capability {
    String value();
}

@Capability("read")
class Parent {}

class Child extends Parent {}
```

`Child.class.getAnnotation(Capability.class)` can return an annotation **inherited** from the superclass because `Capability` has `@Inherited`. This object, when compared with `Parent.class.getAnnotation(Capability.class)`, still follows the same equals rules: same annotation interface, and every element equal.

Do not conclude that all annotations on methods or interfaces are propagated by `@Inherited`: annotation discovery via a class's superclass has its own rules, whereas equality does not use information about "whether the annotation is inherited or directly present".

### @Repeatable: Multiple Objects Retrieved, Compared Individually

```java
import java.lang.annotation.*;

@Repeatable(Tags.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("api")
@Tag("core")
class Endpoint {}
```

`Endpoint.class.getAnnotationsByType(Tag.class)` returns the corresponding array of `Tag` instances. Each `Tag` element is still compared according to `Annotation.equals`. If comparing two **container** `Tags` annotations, the `value()` element is a `Tag[]` array and is compared via `Arrays.equals`, so **the order of Tags in the container can affect the container's equality**.

`@Repeatable` does not turn array comparison into an unordered set comparison, nor does it allow ignoring the name/type of the container annotation.

## 11. When Should You Not Use a Custom Comparison?

The following approaches are error-prone:

```java
// Semantically wrong: does not reflect annotation value equality.
boolean same1 = (annotationA == annotationB);

// Unreliable as a replacement for Annotation.equals:
boolean same2 = annotationA.toString().equals(annotationB.toString());

// Wrong when considering array contents:
boolean same3 = annotationA.roles().equals(annotationB.roles());

// Insufficient: hashCode cannot be used to definitively decide equality.
boolean same4 = annotationA.hashCode() == annotationB.hashCode();
```

If you need to compare **the same retrieved annotation type**, use:

```java
boolean same = annotationA.equals(annotationB);
```

If you want to know whether **declarations have the same metadata** on a broader scale, such as the entire set of annotations on two methods, the problem is different: you need to define filters, the annotation types of interest, inheritance, repeated annotations, multiplicity, and ordering rules. This cannot automatically be replaced by a single `equals` call on an individual annotation.

If you write an implementation of an annotation interface manually or via a dynamic proxy, that implementation must properly fulfill the **entire** `Annotation.equals/hashCode/annotationType` contract to interoperate consistently with annotations returned by the JDK. Do not assume that every custom proxy is correct simply because it implements an interface declared with `@interface`.

## 12. Corner Cases to Understand to Avoid Wrong Conclusions

### Without a Runtime Annotation, You Cannot Call equals Yet

```java
@Retention(RetentionPolicy.SOURCE)
@interface SourceMarker {}

@SourceMarker
class Item {}
```

`Item.class.getAnnotation(SourceMarker.class)` returns `null`, because a SOURCE usage is not retained for reflection to read. Do not write `getAnnotation(...).equals(...)` if the lookup result may be `null`; a `NullPointerException` will occur. Check first or use `Objects.equals` when you need to compare cases where metadata may be absent.

Note that `Objects.equals(a, b)` treats **two null values as equal**, but that is the `Objects.equals` contract for **not finding an annotation**, **not** two present annotation instances having the same contents.

### A New Annotation Interface Differs in Type from an Old One Even with the Same Elements

```java
@Retention(RetentionPolicy.RUNTIME)
@interface OldConfig { String value(); }

@Retention(RetentionPolicy.RUNTIME)
@interface NewConfig { String value(); }
```

`@OldConfig("x")` does not equal `@NewConfig("x")`. A migration system may explicitly define **business equivalence** between the two types, but that is not standard `Annotation.equals`.

### Changes to an Annotation Definition Can Affect Comparison

If an annotation interface is modified by adding an element with a `default`, the corresponding annotation objects in the new version will include that additional element when evaluating equality/hash. When working with compiled libraries, changing an annotation definition can entail binary compatibility or element accessibility issues. Do not use an annotation's hash code as a durable identifier across library versions, JDKs, or class-loading environments.

### ClassLoader and Class Tokens

If a class is loaded by different class loaders, even with the same binary name, they can be **two different Java types**. Because annotation equality checks the exact annotation interface and uses `Class.equals` for `Class` elements, having the same display name **does not guarantee** that two annotations are equal.

### Arrays Are Not Sets

If an application wants to treat `{"READ","WRITE"}` and `{"WRITE","READ"}` as **business-equivalent**, it must normalize/canonicalize the values itself or design a custom function. `Annotation.equals` always follows `Arrays.equals`, which takes element positions into account.

## 13. Debugging Process When Annotations Are Not Equal

When two annotations look similar but `equals` is `false`, follow these steps in order:

1. **Check the exact annotation type:** compare `a.annotationType()` and `b.annotationType()`; do not compare implementation classes or simple names.
2. **List all elements of the annotation interface** via `annotationType().getDeclaredMethods()`. Do not skip elements that have a `default`.
3. **Read each accessor value:** primitive, string, class token, enum, nested annotation, or array? A single differing element is enough to make equality false.
4. **For arrays, use `Arrays.equals`:** compare size, values at each index, and order.
5. **For float/double:** check `NaN`, `+0.0`, and `-0.0`; do not rely on `==` alone to explain it.
6. **For nested annotations:** recursively compare each element.
7. **Cross-check defaults and library versions:** identical source writing does not guarantee identical runtime metadata if the interface or default values changed; check the corresponding environment.
8. **Check how the data was retrieved:** `getAnnotation`, `getDeclaredAnnotation`, and `getAnnotationsByType` have different discovery rules. Obtaining the right object is a separate step from comparing it.

If your goal is testing code, assert both equal and unequal cases: different annotation type, different primitive, different array order, different nested value, and different signed zero. Testing only with simple `String` examples while ignoring arrays/defaults can hide bugs in a custom equals implementation.

## 14. Self-Check Exercises

### Exercise 1: Same Values, Different Ways of Writing

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Task {
    String name();
    int priority() default 5;
}

@Task(name = "sync")
class Alpha {}

@Task(priority = 5, name = "sync")
class Beta {}
```

Are the two `Task` annotations reflected from `Alpha` and `Beta` equal?

**Answer:** Yes, because `priority()` returns the same value `5` and `name()` returns the same string `"sync"`. The order in which element pairs are written and whether defaults are explicitly specified do not matter.

### Exercise 2: Array Order

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Paths { String[] value(); }

@Paths({"a", "b"})
class A {}

@Paths({"b", "a"})
class B {}
```

**Answer:** Not equal. Arrays are compared using `Arrays.equals`, where element order matters.

### Exercise 3: Two Annotation Types with the Same Element Name

```java
@interface Command { String value(); }
@interface Action { String value(); }
```

Can `@Command("run")` be considered equal to `@Action("run")` under `Annotation.equals`?

**Answer:** No. They must belong to the same annotation interface before element values are evaluated.

### Exercise 4: Newly Created Arrays

Two annotations have `int[] numbers()` and each annotation returns a separate array with contents `{1, 2, 3}`. Can they be equal?

**Answer:** Yes. The annotation contract uses `Arrays.equals(int[], int[])`, not array reference identity.

### Exercise 5: float/double

Predict the equality of `@Rate(+0.0)` and `@Rate(-0.0)`; and of two `@Rate(Double.NaN)` instances.

**Answer:** The signed zero pair is not equal; the NaN pair is equal, according to `Double.equals` as used by `Annotation.equals`.

### Exercise 6: Nested Annotations

Two `@ServiceInfo` annotations have the same `type()` and two `Owner` annotations with the same `team()`. Are they equal if applied to two different classes?

**Answer:** Yes, provided no other elements differ in value. Nested annotations are compared recursively; the placement location does not participate in the equals condition.

### Exercise 7: Hash Code

If `a.equals(b) == true`, is `a.hashCode() == b.hashCode()` mandatory? If you only know that the hash codes are equal, can you conclude that equals is true?

**Answer:** The first direction is mandatory; the reverse is not, because different values can have hash collisions.

### Exercise 8: Why an Assertion Fails

Is `assert firstAnnotation.toString().equals(secondAnnotation.toString())` the standard way to test annotation equality?

**Answer:** No. The string representation depends on the implementation. Use `firstAnnotation.equals(secondAnnotation)`, with both objects already retrieved and checked for existence.

## 15. Summary and Reference Documentation

**Concise rule to remember:** `Annotation.equals` checks **same annotation interface + equality of each element**; array elements are compared with `Arrays.equals`, nested annotations are compared recursively, defaults are fully included, and float/double follow `Float.equals`/`Double.equals` instead of ordinary `==`. `hashCode` must correspond accordingly, while `toString`, `==`, and annotation placement cannot replace equals.

Official documentation:

- [Java SE 17 API — `java.lang.annotation.Annotation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html): detailed contract for `equals`, `hashCode`, `toString`, and `annotationType`.
- [Java SE 17 API — `java.util.Arrays`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): overloads of `Arrays.equals` and `Arrays.hashCode`.
- [JLS Java SE 17 — `9.6 Annotation Interfaces`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6): element types, default values, metadata, and meta-annotations.
- [Java SE 17 API — `java.lang.Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): how `Double.equals` distinguishes signed zero and handles NaN.
