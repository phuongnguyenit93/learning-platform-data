# Boxing When Reading Primitive Arrays with `Array.get` in Java Reflection

## 1. The Situation to Understand

`java.lang.reflect.Array.get(Object array, int index)` has return type **`Object`**, even when the array element is primitive such as `int` or `double`. For primitive arrays, Reflection must represent the read value with the corresponding wrapper; for reference arrays, it returns the exact reference stored in that slot.

~~~java
int[] scores = {42};
Object item = java.lang.reflect.Array.get(scores, 0);

System.out.println(item);                    // 42
System.out.println(item.getClass().getName()); // java.lang.Integer
~~~

Visualize the data flow:

~~~text
int[] -- read a slot --> int 42 -- boxing --> Integer(42) -- return Object
Integer[] -- read a slot --> reference Integer(42) --------> return Object
~~~

Both cases can yield the same observed result of an `Integer` object, but **their origins differ**: in `int[]`, the number is stored in primitive form; in `Integer[]`, the array stores a reference to an existing `Integer` object. This lesson focuses on that distinction, the possibility of encountering `null`, how to distinguish origins, and when to use a specialized primitive getter.

## 2. Rule Based on the Direct Component Type

The table below describes the **direct element type** of the array and the object type returned from `Array.get`:

| Array Type | Component Type | Result When Reading a Valid Element |
| --- | --- | --- |
| `boolean[]` | `boolean` | `Boolean` |
| `byte[]` | `byte` | `Byte` |
| `short[]` | `short` | `Short` |
| `char[]` | `char` | `Character` |
| `int[]` | `int` | `Integer` |
| `long[]` | `long` | `Long` |
| `float[]` | `float` | `Float` |
| `double[]` | `double` | `Double` |
| `Integer[]` | `Integer` | Reference `Integer` or `null` |
| `String[]` | `String` | Reference `String` or `null` |
| `int[][]` | `int[]` | Reference to an `int[]` or `null` |

To inspect the *reading mechanism*, use:

~~~java
Object unknown = new int[] {42};
Class<?> component = unknown.getClass().getComponentType();

System.out.println(component == int.class);  // true
System.out.println(component.isPrimitive()); // true
~~~

`getComponentType()` strips only **one layer**. For example, `int[][].class.getComponentType() == int[].class`; because `int[]` is also an object, `int[][].class.getComponentType().isPrimitive()` returns `false`. Reading the outer layer with `Array.get` yields an `int[]` subarray; only when continuing to read **inside the subarray** is an `int` number boxed into `Integer`.

## 3. When Two Objects Share the Same Class but Have Different Semantics

~~~java
Object primitiveArray = new int[] {7};
Object wrapperArray = new Integer[] {7};

Object a = java.lang.reflect.Array.get(primitiveArray, 0);
Object b = java.lang.reflect.Array.get(wrapperArray, 0);

System.out.println(a.getClass() == b.getClass()); // true
System.out.println(a.equals(b));                  // true
~~~

The results above **do not allow concluding** that both arrays have the same kind. Checking the component gives `int.class` and `Integer.class`. This matters for a serializer or data mapper: a primitive array cannot have a `null` element, whereas a wrapper array can.

~~~java
int[] primitive = new int[1];
Integer[] reference = new Integer[1];

System.out.println(java.lang.reflect.Array.get(primitive, 0)); // 0
System.out.println(java.lang.reflect.Array.get(reference, 0)); // null
~~~

Do not call `getClass()` directly on an element without checking `null` first. In addition, **`Character` and `Boolean` do not extend `Number`**. If a tool classifies results with `item instanceof Number`, it misses these two wrappers. When needing to support all eight primitives, rely on **the component type of the source array**, then choose the appropriate conversion policy.

### Boxing Does Not Mean the Array Was Converted

Even though `Array.get(new int[]{7}, 0)` returns `Integer`, the source array object is still `int[]`. It does not become `Integer[]` and cannot be cast to `Object[]`. If an API truly needs a reference array, you must **allocate a new array and copy/box each value**. A cast does not perform an entire-array conversion.

## 4. Standalone Program: Comparing Four Cases

Save as `ArrayBoxingFocusDemo.java`, run with JDK 17+:

~~~java
import java.lang.reflect.Array;

public class ArrayBoxingFocusDemo {
    static void describe(String name, Object source, int index) {
        Class<?> component = source.getClass().getComponentType();
        Object item = Array.get(source, index);
        System.out.println(name
                + ": component=" + component.getTypeName()
                + ", primitive=" + component.isPrimitive()
                + ", value=" + (item instanceof int[] ? "int[]" : item)
                + ", resultType=" + (item == null
                        ? "null" : item.getClass().getTypeName()));
    }

    public static void main(String[] args) {
        describe("primitive", new int[] {42}, 0);
        describe("wrapper", new Integer[] {42}, 0);
        describe("empty-reference", new Integer[1], 0);
        describe("nested", new int[][] {{42}}, 0);

        Object row = Array.get(new int[][] {{42}}, 0);
        describe("nested-leaf", row, 0);

        System.out.println("getInt(byte[])="
                + Array.getInt(new byte[] {7}, 0));
        System.out.println("getLong(int[])="
                + Array.getLong(new int[] {7}, 0));

        try {
            Array.getInt(new Integer[] {7}, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("getInt(wrapperArray)=rejected");
        }
    }
}
~~~

~~~bash
javac --release 17 ArrayBoxingFocusDemo.java
java ArrayBoxingFocusDemo
~~~

Output:

~~~text
primitive: component=int, primitive=true, value=42, resultType=java.lang.Integer
wrapper: component=java.lang.Integer, primitive=false, value=42, resultType=java.lang.Integer
empty-reference: component=java.lang.Integer, primitive=false, value=null, resultType=null
nested: component=int[], primitive=false, value=int[], resultType=int[]
nested-leaf: component=int, primitive=true, value=42, resultType=java.lang.Integer
getInt(byte[])=7
getLong(int[])=7
getInt(wrapperArray)=rejected
~~~

When running, compare `primitive` and `wrapper`: `resultType` is the same, but `component` and `primitive` differ. In `nested`, the read value is a subarray, not yet a number; `nested-leaf` is what reads the primitive value. The `null` result of `empty-reference` is valid, not a Reflection error.

## 5. Why Does `getInt` Differ from `get`?

Specialized getters (`getBoolean`, `getByte`, `getShort`, `getChar`, `getInt`, `getLong`, `getFloat`, `getDouble`) have a **primitive** return type on the API signature. For instance:

~~~java
int[] source = {10};
Object boxed = Array.get(source, 0);   // Object referencing Integer.
int exact = Array.getInt(source, 0);   // int value.
long wider = Array.getLong(source, 0); // int -> long valid.
~~~

The snippet above requires importing `java.lang.reflect.Array` and is placed inside a method.

Typed getters allow **identity or primitive widening** from the array's component type **to the return type**. `getInt` accepts `byte[]`, `short[]`, `char[]`, `int[]`, but does not read `long[]` because that is narrowing. `getDouble` accepts valid numeric primitive arrays (not `boolean[]`), though `long -> double` widening can still lose precision. Typed getters **do not automatically unbox reference arrays**: `Array.getInt(new Integer[]{10}, 0)` is rejected.

To find the full conversion directions for all getters/setters, see the lesson `Array.get, Array.set, and Primitive Variants`; here keep one rule: **`get` boxes according to the actual element type, whereas `getXxx` returns a primitive along the widening path permitted by the API**.

## 6. When Does Boxing Have Practical Impact?

**General APIs:** An inspector/serializer handling `Object unknownArray` can use `Array.get` to receive elements as `Object` without knowing the numeric type in advance. This is simple, but you must distinguish a freshly boxed wrapper from an already-existing reference object.

**Hot loops:** If code knows the source is `int[]` and needs to sum millions of numbers, accessing `typedArray[i]` is usually more reasonable than reading as `Object`, casting/unboxing, and then adding. `Array.getInt` makes the `int` return type explicit, though actual cost still depends on the JVM, JIT, and how the caller uses the result. Do not guess allocated object counts from syntax alone; measure in the actual environment when performance issues arise.

**Comparisons:** Do not rely on `==` between two boxed results; wrappers may be reused/cached and object identity is not a contract for comparing array values. Compare values with `equals` or unbox with the appropriate type; do not cast every element to `Integer` when the source could be `long[]` or `char[]`.

**Reading and writing:** When `Array.set` writes to a primitive array, `Object value` is evaluated based on the source wrapper, unboxing, and valid widening before storing. That conversion direction **differs from the read direction** of `getXxx`; an `Integer` value does not automatically convert into a `Long` object to be written into `Long[]`. The lesson on widening conditions during assignment explains this part in depth.

## 7. Error Boundaries to Distinguish

| Situation | Consequence | Lesson |
| --- | --- | --- |
| `Array.get(new int[]{7}, 0)` | `Integer` | Boxing matches the primitive type |
| `Array.get(new Integer[]{null}, 0)` | `null` | Reference arrays allow null elements |
| `(Integer) Array.get(new long[]{7}, 0)` | `ClassCastException` | Actual result is `Long` |
| `Array.getInt(new Integer[]{7}, 0)` | `IllegalArgumentException` | Typed getters do not work on reference arrays |
| `Array.get(new int[0], 0)` | `ArrayIndexOutOfBoundsException` | Valid array, but index 0 does not exist |
| `Array.get(null, 0)` | `NullPointerException` | No array object |
| `Array.get("text", 0)` | `IllegalArgumentException` | Object is not an array |

If receiving input of unknown type, check `array != null`, `array.getClass().isArray()`, and `Array.getLength(array)` before accessing elements. Then check `component.isPrimitive()` or `item == null` before processing the result. This protects data boundaries, though it does not replace type validation in business logic.

## 8. Self-Check Questions

1. Why do `Array.get(new int[]{1}, 0)` and `Array.get(new Integer[]{1}, 0)` both return `Integer` yet have different origins?
2. Why does reading the outer layer of `int[][]` via `Array.get` **not box `int`**?
3. What wrapper is the result of `Array.get(new boolean[]{false}, 0)`? Why does `instanceof Number` fail to detect it?
4. Is `Array.getLong(new int[]{10}, 0)` valid? What about `Array.getInt(new long[]{10}, 0)`?
5. Why doesn't `getInt` work with `Integer[]`, even though the first element currently holds `Integer(10)`?
6. In a general framework, why is checking `component.isPrimitive()` more reliable than guessing the array origin from the class of the object returned by `Array.get`?

**Core answer:** `Array.get`'s boxing decision depends on **the array's direct component type**. Specialized primitive getters return primitives via valid identity/widening; a reference array remains a reference array, regardless of what wrappers it stores.

Standard references: [Java SE 17 — `java.lang.reflect.Array`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html), [JLS §5.1.7 — Boxing](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7).