# Primitive Arrays Do Not Substitute for Wrapper Arrays in Java Reflection

## 1. Nature of the issue: element-level boxing does not convert the type of an entire array

In Java, array types `int[]` and `Integer[]` are **two different runtime types**:

- `int[]` stores **primitive `int`** elements, with default value `0`.
- `Integer[]` stores **references to `Integer` objects**, can contain `null`, and has default value `null`.
- Java supports **element-by-element boxing/unboxing** between `int` and `Integer`, but **does not automatically convert an entire `int[]` array** into `Integer[]` or vice versa.
- Because they are different array types, they **are not interchangeable** in parameters, variable assignments, field types, or Reflection lookup signatures.

```java
int value = 7;
Integer boxedValue = value; // Element boxing: valid.
int unboxedValue = boxedValue; // Element unboxing: valid.

int[] primitives = {1, 2, 3};
Integer[] wrappers = {1, 2, 3}; // Each literal element is boxed.

// ILLUSTRATIVE CODE THAT DOES NOT COMPILE:
// Integer[] wrong1 = primitives;
// int[] wrong2 = wrappers;
```

There is no Java rule allowing `Integer[] wrappers = primitives` via an implicit array-level boxing conversion. Even casting through `Object` cannot transform the data:

```java
// Illustrative example: this statement compiles but fails at runtime.
// Integer[] invalid = (Integer[]) (Object) primitives;
// Runtime: ClassCastException.
```

Specifically in Reflection, finding the right method name yet passing the **wrong array type** usually leads to `NoSuchMethodException` at lookup time or `IllegalArgumentException` at invocation time.

## 2. Identifying both types via Class

```java
Class<?> primitiveArrayType = int[].class;
Class<?> wrapperArrayType = Integer[].class;

System.out.println(primitiveArrayType.getTypeName()); // int[]
System.out.println(wrapperArrayType.getTypeName());   // java.lang.Integer[]
System.out.println(primitiveArrayType.isArray());     // true
System.out.println(wrapperArrayType.isArray());       // true
System.out.println(primitiveArrayType.getComponentType().isPrimitive()); // true
System.out.println(wrapperArrayType.getComponentType().isPrimitive());   // false
```

This is an **illustrative snippet inside a Java method**, not a standalone runnable program. Comparing `primitiveArrayType.equals(wrapperArrayType)` returns `false`. Note that **`int[]` itself is a reference type** (hence `int[].class.isPrimitive()` is `false`), while its **component type** `int.class` is what is primitive.

| Type | `Class.getTypeName()` | `getComponentType()` | Can contain `null` as an element? |
| --- | --- | --- | --- |
| `int[]` | `int[]` | `int.class` | No |
| `Integer[]` | `java.lang.Integer[]` | `Integer.class` | Yes |
| `long[]` | `long[]` | `long.class` | No |
| `Long[]` | `java.lang.Long[]` | `Long.class` | Yes |
| `boolean[]` | `boolean[]` | `boolean.class` | No |
| `Boolean[]` | `java.lang.Boolean[]` | `Boolean.class` | Yes |

Every corresponding primitive/wrapper pair follows the same rule: `double[]` differs from `Double[]`, `char[]` differs from `Character[]`, and so on.

`Class.getName()` uses an internal naming format different from `getTypeName()`, for example `int[].class.getName()` returns `"[I"`, while `Integer[].class.getName()` returns `"[Ljava.lang.Integer;"`. Use `getTypeName()` for readable display; do not infer that two arrays are compatible merely because their component names look related.

## 3. Reflection method lookup: signature must match the exact array kind

Suppose a class has:

```java
public static int sum(int[] values) {
    return java.util.Arrays.stream(values).sum();
}
```

Correct lookup:

```java
// Illustrative snippet inside a program with class Target.
java.lang.reflect.Method sum =
        Target.class.getMethod("sum", int[].class);
```

Wrong approach:

```java
// Throws NoSuchMethodException: method sum(Integer[]) does not exist.
Target.class.getMethod("sum", Integer[].class);
```

`getMethod(name, Class<?>... parameterTypes)` and `getDeclaredMethod(...)` match **the exact `Class` of each declared parameter**. When the parameter is `int[]`, Reflection requires `int[].class`; it does not inspect elements and apply boxing to `Integer[].class`. Conversely, for a method accepting `Integer[]`, you must look up with `Integer[].class`.

Multidimensional parameters behave the same way: `int[][].class` differs from `Integer[][].class`; do not look up `process(int[][])` with `Integer[][].class`.

### Distinguishing lookup from Method.invoke

After obtaining the `Method`, the correct invocation is:

```java
int[] values = {1, 2, 3};
Object answer = sum.invoke(null, (Object) values); // Static method.
```

Here `(Object) values` ensures `values` is **a single argument** of the target method because `Method.invoke(Object, Object...)` is itself a varargs API. With an `Integer[]` not cast to `Object`, Java may treat that `Object[]` array as the varargs argument list, causing an argument count error in addition to the type error. An explicit cast helps keep the two issues separate.

If you use `Integer[] wrappers = {1, 2, 3}` and then call:

```java
// Given Method sum representing sum(int[]).
sum.invoke(null, (Object) wrappers); // IllegalArgumentException.
```

**There is no whole-array conversion** at the `invoke` step: even though `Integer` can unbox to `int` when a parameter is directly `int`, an `int[]` parameter does not accept `Integer[]`. `invoke` does not automatically select another overload and does not construct a new array.

## 4. Constructor and Field also do not convert primitive arrays to wrapper arrays

The same rule applies when Reflection works with constructors and fields.

### Constructor

```java
public Target(int[] values) {
    this.primitiveField = values;
}
```

Lookup:

```java
Constructor<Target> constructor =
        Target.class.getConstructor(int[].class); // Correct.
```

Using `Target.class.getConstructor(Integer[].class)` will throw `NoSuchMethodException` if there is no `(Integer[])` constructor. After finding the right one, `constructor.newInstance((Object) new int[] {1, 2})` is valid. Passing `Integer[]` to a constructor taking `int[]` will throw `IllegalArgumentException` due to invalid argument type.

### Field

Suppose:

```java
public int[] primitiveField;
```

`Field.getType()` returns `int[].class`. Calling `field.set(target, new int[] {4, 5})` is valid if the caller has permission to write that field, whereas `field.set(target, new Integer[] {4, 5})` is invalid and throws `IllegalArgumentException`. Reflection cannot assign a wrapper array into a slot holding a primitive array.

In the program in the next section, Method lookup, Constructor lookup, and Field assignment are all demonstrated using a single `Target` class.

## 5. Complete Java 17+ program: contrasting all cases

Save the exact code to **`PrimitiveWrapperArraysDemo.java`**:

```java
import java.lang.reflect.Array;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;

public class PrimitiveWrapperArraysDemo {
    public static class Target {
        public int[] primitiveField;

        public Target(int[] input) {
            primitiveField = input;
        }

        public static int sum(int[] values) {
            return Arrays.stream(values).sum();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("same class: "
                + int[].class.equals(Integer[].class));
        System.out.println("int[]: " + int[].class.getTypeName());
        System.out.println("Integer[]: " + Integer[].class.getTypeName());
        System.out.println("int component primitive: "
                + int[].class.getComponentType().isPrimitive());
        System.out.println("Integer component primitive: "
                + Integer[].class.getComponentType().isPrimitive());
        System.out.println("Object[] accepts int[]: "
                + Object[].class.isAssignableFrom(int[].class));

        int[] ints = {1, 2, 3};
        Integer[] wrappers = {1, 2, 3};
        Method method = Target.class.getMethod("sum", int[].class);

        System.out.println("method: "
                + method.getParameterTypes()[0].getTypeName());
        System.out.println("sum(int[]): "
                + method.invoke(null, (Object) ints));

        try {
            Target.class.getMethod("sum", Integer[].class);
        } catch (NoSuchMethodException e) {
            System.out.println("lookup Integer[]: NoSuchMethodException");
        }
        try {
            method.invoke(null, (Object) wrappers);
        } catch (IllegalArgumentException e) {
            System.out.println("invoke Integer[]: IllegalArgumentException");
        }

        Constructor<Target> constructor =
                Target.class.getConstructor(int[].class);
        Target target =
                constructor.newInstance((Object) new int[] {4, 5});
        System.out.println("constructor: "
                + Arrays.toString(target.primitiveField));
        try {
            Target.class.getConstructor(Integer[].class);
        } catch (NoSuchMethodException e) {
            System.out.println(
                    "constructor Integer[]: NoSuchMethodException");
        }

        Field field = Target.class.getField("primitiveField");
        try {
            field.set(target, wrappers);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "field.set(Integer[]): IllegalArgumentException");
        }
        field.set(target, ints);
        System.out.println("field after set(int[]): "
                + Arrays.toString(target.primitiveField));

        System.out.println("Array.get int[] element class: "
                + Array.get(ints, 0).getClass().getSimpleName());
        Array.set(ints, 0, Integer.valueOf(9));
        System.out.println("Array.set int[] from Integer: "
                + Arrays.toString(ints));
        try {
            Array.set(ints, 0, Long.valueOf(9));
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "Array.set int[] from Long: IllegalArgumentException");
        }

        System.out.println("Array.newInstance int[]: "
                + Array.newInstance(int.class, 2).getClass().getTypeName());
        System.out.println("Array.newInstance Integer[]: "
                + Array.newInstance(Integer.class, 2)
                        .getClass().getTypeName());

        Integer[] boxed =
                Arrays.stream(ints).boxed().toArray(Integer[]::new);
        System.out.println("boxed: " + Arrays.toString(boxed));
        int[] unboxed =
                Arrays.stream(boxed).mapToInt(Integer::intValue).toArray();
        System.out.println("unboxed: " + Arrays.toString(unboxed));

        wrappers[0] = null;
        try {
            Arrays.stream(wrappers)
                    .mapToInt(Integer::intValue).toArray();
        } catch (NullPointerException e) {
            System.out.println("unbox null: NullPointerException");
        }

        Number[] numbers = new Integer[1];
        try {
            numbers[0] = Double.valueOf(2.5);
        } catch (ArrayStoreException e) {
            System.out.println("covariance: ArrayStoreException");
        }
    }
}
```

Compile and run:

```bash
javac PrimitiveWrapperArraysDemo.java
java PrimitiveWrapperArraysDemo
```

Exact stdout in a standard Java 17+ environment:

```text
same class: false
int[]: int[]
Integer[]: java.lang.Integer[]
int component primitive: true
Integer component primitive: false
Object[] accepts int[]: false
method: int[]
sum(int[]): 6
lookup Integer[]: NoSuchMethodException
invoke Integer[]: IllegalArgumentException
constructor: [4, 5]
constructor Integer[]: NoSuchMethodException
field.set(Integer[]): IllegalArgumentException
field after set(int[]): [1, 2, 3]
Array.get int[] element class: Integer
Array.set int[] from Integer: [9, 2, 3]
Array.set int[] from Long: IllegalArgumentException
Array.newInstance int[]: int[]
Array.newInstance Integer[]: java.lang.Integer[]
boxed: [9, 2, 3]
unboxed: [9, 2, 3]
unbox null: NullPointerException
covariance: ArrayStoreException
```

**Reading the results mechanism by mechanism:**

1. `int[].class.equals(Integer[].class)` returns `false`, and `getComponentType().isPrimitive()` distinguishes the two element types.
2. `getMethod("sum", int[].class)` is right; `getMethod("sum", Integer[].class)` cannot find the signature.
3. `Method.invoke` accepts `int[]` as one argument yet rejects `Integer[]`, without unboxing the whole array.
4. The constructor taking `int[]` and the field declared as `int[]` also reject substituting `Integer[]`.
5. `Array.get(ints, 0)` **boxes the individual element value** into `Integer`; `Array.set(ints, 0, Integer.valueOf(9))` can unbox the element and write it into the `int[]` array.
6. `Array.set(ints, 0, Long.valueOf(9))` does not perform **narrowing `long` to `int`**. Supporting boxing/unboxing at **an element position** does not prove the ability to convert the type of **the entire array**.
7. `Array.newInstance(int.class, 2)` creates `int[]`; `Array.newInstance(Integer.class, 2)` creates `Integer[]`. The passed-in element type determines the created array type.
8. `IntStream.boxed()` and `Stream.mapToInt(...)` are two ways to **intentionally convert each element** to build a new array.
9. Wrapper arrays can contain `null`, so unboxing `null` can throw `NullPointerException`.

## 6. Why do Array.get and Array.set seem to "support boxing"?

The `java.lang.reflect.Array` API operates on **elements**, without changing the array kind:

```java
int[] values = {3, 4};

Object element = Array.get(values, 0); // Integer(3) via boxing.
Array.set(values, 1, Integer.valueOf(7)); // Unbox Integer to int.
```

`Array.get` returns `Object`, so primitive elements must be boxed into the appropriate wrapper; methods `Array.getInt`, `Array.getLong`, `Array.setInt`, ... provide specialized primitive operations with supported widening conversion rules. `Array.set` accepts an element object and can unbox/widen when compatible; it **does not accept arbitrary wrappers** and does not perform arbitrary narrowing.

Cases to keep separate:

| Operation | Result |
| --- | --- |
| `Array.get(new int[] {5}, 0)` | An `Integer` representing `5` |
| `Array.set(intArray, 0, Integer.valueOf(5))` | Valid |
| `Array.set(intArray, 0, Short.valueOf((short) 5))` | Valid: unbox `short`, widen to `int` |
| `Array.set(intArray, 0, Long.valueOf(5L))` | `IllegalArgumentException` because `long` does not narrow to `int` |
| `Array.set(intArray, 0, null)` | `IllegalArgumentException` because `int` cannot hold `null` |
| `Array.set(integerArray, 0, null)` | Valid: `Integer[]` can hold `null` |
| `Array.set(integerArray, 0, Long.valueOf(5L))` | `IllegalArgumentException`: `Long` is not assignable to `Integer` |

**Conclusion of this section:** elements can be boxed/unboxed per API rules, while **`int[]` and `Integer[]` remain two array objects belonging to two different classes**.

## 7. Converting arrays properly when interacting with other APIs

If a provider returns `int[]` yet an API accepts `Integer[]`, **convert explicitly** by creating a new array and boxing each element.

### From int[] to Integer[]

```java
int[] source = {10, 20, 30};
Integer[] boxed = java.util.Arrays.stream(source)
        .boxed()
        .toArray(Integer[]::new);
```

### From Integer[] to int[]

```java
Integer[] source = {10, 20, 30};
int[] primitives = java.util.Arrays.stream(source)
        .mapToInt(Integer::intValue)
        .toArray();
```

Both snippets above are **code fragments placed inside a method**, not standalone programs. The result is a **new array** copying element values; there is no cast substitute.

For `Integer[]` containing `null`, define an explicit rule: fail, filter out elements, or replace with a meaningful business default. For example, `mapToInt(Integer::intValue)` will fail upon encountering `null`; do not silently turn every `null` into `0` if the application distinguishes the two states.

When using Reflection to call a method accepting `int[]`, convert **first** and then pass the right array:

```java
// Illustrative snippet inside a method having Integer[] source and Method method.
int[] converted = java.util.Arrays.stream(source)
        .mapToInt(Integer::intValue)
        .toArray();
Object result = method.invoke(null, (Object) converted);
```

This is an intentional choice carrying allocation and O(n) cost proportional to element count; Reflection **does not perform this step automatically**.

## 8. Primitive arrays do not share covariance with wrapper arrays

Reference-type arrays in Java are *covariant*: because `Integer` extends `Number`, an `Integer[]` can be assigned to a `Number[]` variable. The JVM still checks when writing elements:

```java
Number[] array = new Integer[1];
array[0] = Double.valueOf(3.14); // ArrayStoreException at runtime.
```

Conversely:

```java
int[] primitive = {1, 2};

// Does not compile:
// Object[] elements = primitive;
// Number[] numbers = primitive;

Object singleObject = primitive; // Valid: every array is an Object.
```

An `int[]` can be stored as **one object** in an `Object` variable or in **one element** of an `Object[]`, yet **it is not itself an `Object[]`**: `int` values are not `Object` references.

Example:

```java
Object[] container = {new int[] {1, 2}, new Integer[] {3, 4}};
// container has two elements, each element is an array object.
```

Similarly, `List<int[]>` is a list of `int[]` arrays; it is not equivalent to `List<Integer>` and does not convert into `Integer[]`.

## 9. Varargs, Arrays.asList, and related traps

### 9.1. Parameter `int...` is still `int[]`

```java
public static void printAll(int... numbers) {
    System.out.println(java.util.Arrays.toString(numbers));
}
```

At runtime, `int...` is a parameter of type `int[]`; lookup:

```java
// In the context of class Example having static method printAll(int...).
Method method = Example.class.getMethod("printAll", int[].class);
```

`getMethod("printAll", Integer[].class)` does not match. `Method.isVarArgs()` may return `true`, yet `Method.invoke` **does not automatically spread/pack elements as normal Java call syntax does**; pass the appropriate array as one argument.

### 9.2. Arrays.asList behaves differently for primitives and wrappers

```java
int[] ints = {1, 2, 3};
Integer[] wrappers = {1, 2, 3};

var a = java.util.Arrays.asList(ints);
var b = java.util.Arrays.asList(wrappers);

System.out.println(a.size()); // 1: the sole element is the entire int[].
System.out.println(b.size()); // 3: each Integer is one element.
```

Reason: `Arrays.asList(T... a)` takes a reference-type `T[]`; `int[]` is not a `T[]` array holding `Integer` objects, so it is treated as **a single element object**.

### 9.3. System.arraycopy does not box an array

`System.arraycopy(intArray, 0, integerArray, 0, n)` **does not** copy by boxing each element; because primitive and reference element types are incompatible, it throws `ArrayStoreException`. Use an actual conversion loop or stream when needed.

### 9.4. Multidimensional arrays

`int[][]` is an array of `int[]`, whereas `Integer[][]` is an array of `Integer[]`. Although both multidimensional kinds are arrays of objects at the outer level, **the inner sub-arrays are still not interchangeable**. Conversion must walk through each row and each element, handling `null` rows as well if data permits.

## 10. Common errors and how to fix them

| Symptom | Cause | Fix |
| --- | --- | --- |
| `NoSuchMethodException` for `process(java.lang.Integer[])` | Method actually takes `int[]` | Look up exact `int[].class` |
| `Method.invoke` throws `IllegalArgumentException` despite right element count | Passed `Integer[]` instead of `int[]` | Convert elements to `int[]`, then pass `(Object) converted` |
| Statement `Integer[] array = primitiveArray` does not compile | Java does not box at the array level | Use `Arrays.stream(primitiveArray).boxed().toArray(Integer[]::new)` |
| `Constructor.newInstance` rejects `Integer[]` | Constructor declares parameter `int[]` | Look up/call exact `int[].class` signature and `int[]` value |
| `Field.set` rejects wrapper array | Field declares `int[]` | Check `getType()`, create exact array kind |
| `Array.get(intArray, 0)` returns `Integer`, mistaking entire array for `Integer[]` | API boxes **one element** | Check `array.getClass()` and `getComponentType()` |
| `mapToInt(Integer::intValue)` throws NPE | `Integer[]` has a `null` element | Define `null` handling before unboxing |
| `Arrays.asList(intArray).size()` equals `1` | Entire `int[]` becomes one list element | Use `Arrays.stream(intArray).boxed().toList()` to get `List<Integer>` |
| `System.arraycopy` throws `ArrayStoreException` | API does not box an entire array on copy | Convert using loop or stream |
| Casting `(Integer[]) (Object) intArray` throws `ClassCastException` | Actual runtime class is still `int[]` | Do not use a cast in place of conversion |

## 11. Self-check

1. **Can `void handle(int[] values)` be looked up with `getMethod("handle", Integer[].class)`?** No. You must use `int[].class` because the signature is matched by the declared array type.
2. **Why does `Array.get(new int[]{5}, 0)` return `Integer`?** Because `Array.get` returns `Object`, so it boxes **the `int` element**; that does not turn `int[]` into `Integer[]`.
3. **Is `Object obj = new int[]{1,2}` valid? What about `Object[] arr = new int[]{1,2}`?** The first is valid; the second does not compile.
4. **Can `Integer[]` contain `null` while `int[]` can?** `Integer[]` can; `int[]` cannot contain `null` as an element.
5. **How do you explicitly convert `Integer[]` to `int[]`?** Validate `null` elements per business rules, then unbox each element, for example with `Arrays.stream(values).mapToInt(Integer::intValue).toArray()`.
6. **Can `int[][]` be substituted with `Integer[][]` in Reflection?** No; the multidimensional array types still differ and there is no array-level boxing conversion.

**Takeaway:** Boxing/unboxing operates on **element values**, without converting **the type of the whole array**. In Reflection, always use the exact `Class` of the parameter/field (`int[].class` or `Integer[].class`) and perform explicit array conversion when genuinely needed.

References: [Java Language Specification §5 — Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html), [Java SE 17 `java.lang.reflect.Array`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html), [Java SE 17 `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html).