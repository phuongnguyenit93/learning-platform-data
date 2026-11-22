# `Field.get()` returns a wrapper when the field has a primitive type

## 1. The problem: the field is `int`, why is the result of `get()` an `Integer`?

When using Java Reflection to read a field, the most important API signature is:

~~~java
public Object get(Object obj) throws IllegalArgumentException, IllegalAccessException
~~~

`Field.get(Object)` has a return type of **`Object`**, while Java has eight primitive types (`boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`). Primitives are not objects, so they cannot directly serve as an `Object` return value. Therefore, if a field is declared as primitive, Java reads the primitive value and **boxes** it into an object of the corresponding wrapper class.

Example:

~~~java
class Counter {
    public int count = 42;
}

Counter counter = new Counter();
java.lang.reflect.Field field = Counter.class.getField("count");

Object result = field.get(counter);           // Integer holding 42
System.out.println(field.getType());          // int
System.out.println(result.getClass());        // class java.lang.Integer
int count = (Integer) result;                 // cast + unboxing
~~~

The code above is illustrative. `Field.getType()` returns the type **declared in the class** (`int.class`), while `result.getClass()` returns the class **of the boxed object** (`Integer.class`). The original field is not changed from `int` to `Integer` inside the `Counter` object.

The right mental model is:

~~~text
Field declared as int -> read int value -> box into Integer -> return Object
                                              |
                             getType() is still int.class
~~~

For reference-type fields, `get()` returns the current reference value itself (or `null`), without creating any extra wrapper just because the method's return type is `Object`.

## 2. Primitive-to-wrapper mapping table

| Field's declared type | Object returned by `Field.get()` when field is primitive |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

This is a type mapping, not a guarantee that every call must allocate a new wrapper object. Do not rely on `==` between two `Field.get()` results to check "whether they have the same primitive value". If you need to compare data, unbox to use primitive operators or use appropriate value comparison.

Some points to distinguish:

- An `int number` field always stores a primitive `int` value; `Field.get` represents the result as `Integer`. A primitive field cannot hold `null`.
- An `Integer number` field is already a **reference type**. `Field.get` returns the existing `Integer` reference or `null`; the field itself is not primitive.
- A `String name` field yields a `String`, not a "wrapper of String".
- An `int[] numbers` field is a **reference array type**. `Field.get` returns the `int[]` object; it does not automatically box each element into `Integer[]`. To retrieve a single element via Reflection, see `java.lang.reflect.Array.get`; for primitive elements, that operation also represents the value using a wrapper.

## 3. Compilable and runnable Java 17+ example

Create file `FieldGetBoxingDemo.java`:

~~~java
import java.lang.reflect.Field;

public class FieldGetBoxingDemo {
    public static class Data {
        public int count = 42;
        public boolean enabled = true;
        public char letter = 'J';
        public long large = 3_000_000_000L;
        public Integer nullable = null;
        public String label = "Java";
        public static double factor = 1.5;
    }

    public static void main(String[] args) throws Exception {
        Data data = new Data();

        Field count = Data.class.getField("count");
        Object value = count.get(data);

        System.out.println("field type: " + count.getType().getName());
        System.out.println("result type: " + value.getClass().getSimpleName());
        System.out.println("result: " + value);
        System.out.println("unboxed + 1: " + ((Integer) value + 1));

        System.out.println("getInt: " + count.getInt(data));
        System.out.println("getLong widening: " + count.getLong(data));

        Object flag = Data.class.getField("enabled").get(data);
        System.out.println("boolean wrapper: "
                + flag.getClass().getSimpleName() + "=" + flag);

        Object letter = Data.class.getField("letter").get(data);
        System.out.println("char wrapper: "
                + letter.getClass().getSimpleName() + "=" + letter);

        Object large = Data.class.getField("large").get(data);
        System.out.println("long wrapper: "
                + large.getClass().getSimpleName() + "=" + large);

        Object staticValue = Data.class.getField("factor").get(null);
        System.out.println("static wrapper: "
                + staticValue.getClass().getSimpleName() + "=" + staticValue);

        System.out.println("nullable value: "
                + Data.class.getField("nullable").get(data));
        System.out.println("reference type: "
                + Data.class.getField("label").get(data)
                        .getClass().getSimpleName());

        try {
            Data.class.getField("large").getInt(data);
        } catch (IllegalArgumentException e) {
            System.out.println("getInt from long: "
                    + e.getClass().getSimpleName());
        }

        try {
            Data.class.getField("nullable").getInt(data);
        } catch (IllegalArgumentException e) {
            System.out.println("getInt from Integer: "
                    + e.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac --release 17 FieldGetBoxingDemo.java
java FieldGetBoxingDemo
~~~

Output:

~~~text
field type: int
result type: Integer
result: 42
unboxed + 1: 43
getInt: 42
getLong widening: 42
boolean wrapper: Boolean=true
char wrapper: Character=J
long wrapper: Long=3000000000
static wrapper: Double=1.5
nullable value: null
reference type: String
getInt from long: IllegalArgumentException
getInt from Integer: IllegalArgumentException
~~~

### Output explanation

1. `count` is **declared** as type `int`, so `count.getType().getName()` is `"int"`. After `count.get(data)`, the `value` variable holds a reference to an `Integer` containing 42, because `get` must return `Object`.
2. `(Integer) value + 1` consists of a cast to `Integer`, followed by **auto-unboxing** when performing addition, yielding 43. Do not cast directly as `(int) value` in code requiring compatibility/explicitness because `value`'s static type is `Object` and you must ensure the value is the right wrapper; clear alternatives are `((Integer) value).intValue()` or `int n = (Integer) value;`.
3. `getInt(data)` is a specialized API returning `int` directly. `getLong(data)` is also valid for an `int` field because Java allows **widening primitive conversion** from `int` to `long`.
4. `enabled`, `letter`, `large`, and `factor` are declared respectively as `boolean`, `char`, `long`, and `double`. `Field.get` returns `Boolean`, `Character`, `Long`, and `Double`; the static field `factor` does not need an instance to read, so `get(null)` is called.
5. `nullable` is a reference field of type `Integer` with value `null`; `get` returns `null`, without supplying 0 or synthesizing a wrapper. `label` is a reference field of type `String`, so the actual result is `String`.
6. `getInt` does not accept reading a `long` field by narrowing (`long` → `int`), so it throws `IllegalArgumentException`. It also cannot read a field **declared as `Integer`**: that is a reference type, not a primitive `int` field. If a wrapper field is needed, use `get` then check/null-check and cast appropriately.

The example uses public fields to focus on boxing rules. For private fields or fields in closed modules, access permissions may need to be handled before reading; boxing does not alter access checks.

## 4. Differences between `get()` and typed getters

`Field` provides getters that return specific primitives:

~~~java
boolean getBoolean(Object obj)
byte    getByte(Object obj)
short   getShort(Object obj)
char    getChar(Object obj)
int     getInt(Object obj)
long    getLong(Object obj)
float   getFloat(Object obj)
double  getDouble(Object obj)
~~~

These methods are APIs of `java.lang.reflect.Field`, not new code you need to implement yourself. Each method accepts a receiver just like `get(obj)`, but **the return type is primitive**, making them suitable when computation is needed and you want to avoid an API returning `Object`.

### Type conversion rules

- `get()` returns `Object`: a primitive field is boxed into **the exact wrapper corresponding to the field's type**. It does not convert an `int` field into `Long` just because the caller wants a `long` number.
- `getInt()` can read a primitive field of type `byte`, `short`, `char`, or `int` via primitive widening conversion to `int`. It cannot read `long`, `float`, `double`, `boolean`, or an `Integer` reference field.
- `getLong()` can read primitive fields `byte`, `short`, `char`, `int`, or `long`; for example, an `int` field can be widened to `long`.
- `getDouble()` can read primitive numeric types eligible for widening to `double` (`byte`, `short`, `char`, `int`, `long`, `float`, `double`).
- `getBoolean()` only works with a field of primitive `boolean` type. `boolean` does not widen to numbers.
- `getByte()` only accepts `byte`; `getChar()` only accepts `char`. The remaining getters follow valid Java primitive widening rules.

Typed getters do not unbox reference-type fields. A field declared as `Integer` still needs `Field.get()`; the returned object may be `null`. This is the essential difference between **primitive widening conversion** and **wrapper unboxing**.

The example below is a snippet reusing `count` and `data` from the program above:

~~~java
int exact = count.getInt(data);     // 42, primitive int
long wider = count.getLong(data);   // 42L, int -> long
Object boxed = count.get(data);    // Integer, because get returns Object
~~~

Do not assume typed getters are a "catch-all read that coerces anything" like a data mapper's conversion mechanism. When the declared type is incompatible, they throw `IllegalArgumentException` instead of parsing numbers or performing narrowing casts.

## 5. Declared type vs. value type: how to check properly

In code working with many different fields, you often need to inspect `Field.getType()` **before** casting:

~~~java
Class<?> declared = count.getType();
if (declared == int.class) {
    int n = count.getInt(data);
    System.out.println(n);
}
~~~

This snippet reuses the `count` and `data` variables from the example. For primitive fields, `getType()` returns `int.class`, `boolean.class`, etc. (the `Class` objects representing primitive types). For wrapper-type fields, `getType()` is `Integer.class`, `Boolean.class`, etc., and `isPrimitive()` returns `false`. You can branch as follows:

~~~java
Class<?> declared = field.getType();
if (declared.isPrimitive()) {
    // The data in the field is primitive; get() will box when returning Object.
} else {
    // The field data is a reference, which may be null.
}
~~~

This is also an illustrative snippet; `field` represents an already looked-up `Field`. Do not call `result.getClass()` before checking `result != null`: for a reference field holding `null`, you will get `NullPointerException`. Conversely, a primitive field always has a primitive value (even default values 0, `false`, `'\0'`), so the `Field.get` result of a successfully read primitive field is never `null`.

Another mistake is relying on `value.getClass() == Integer.class` to infer that **the field is declared as `int`**. That is inaccurate: the `Field.get` result from an `int` field and a non-null `Integer` field can both be `Integer`. To distinguish them, you must use **`Field.getType()`**.

## 6. Factors that commonly cause field reads to fail

Boxing only occurs after a field is read successfully. Errors while finding/reading fields are a separate matter:

| Scenario | Behavior to watch out for |
| --- | --- |
| `getField("x")` when the field is not public / not in public lookup | `NoSuchFieldException`; try `getDeclaredField` on the right declaring class if a non-public member is truly needed |
| `get()` on a private field when caller lacks permission | `IllegalAccessException`; `getDeclaredField` does not automatically grant permission |
| Reading an instance field with a `null` receiver | `NullPointerException`; a target object is required |
| Passing an object not belonging to the field's declared type | `IllegalArgumentException` |
| Reading a static field with `get(null)` | Valid; the receiver is ignored for static fields, access permissions still must be satisfied |
| Calling typed getter `getInt` on an `Integer`/`long` field | `IllegalArgumentException` due to incompatible declared type |
| Accessing a private field across a named module using deep reflection | `trySetAccessible()` may return `false`; `setAccessible(true)` may throw `InaccessibleObjectException` |
| `get()` returns `null`, followed by calling `getClass()`/unboxing | `NullPointerException` in the `null`-handling code, not "boxing a primitive to null" |

With named modules, distinguish `exports` for public APIs and `opens` for deep reflection into a package when required by another module. Do not assume `setAccessible(true)` succeeds. If an application depends on private fields, prefer official accessor APIs whenever possible.

## 7. Performance, boxing, and choosing the API

If the goal is processing a large number of primitive fields on a hot execution path, `getInt`/`getLong` have primitive return types and avoid the **API forcing** an `Object` return, making them a natural choice when the type is known upfront. However, Reflection in general has runtime overhead, and the JVM may optimize boxing/allocation depending on the case; you should not conclude that `Field.get` **always** allocates a new wrapper or that a typed getter is **always** significantly faster without benchmarking.

Generally sensible choices:

1. Know the field is `int` and need computation: use `getInt(receiver)`, handling `IllegalAccessException`.
2. Need a general API reading multiple field types: use `get(receiver)`; when the field is primitive, the result will be boxed, and you handle it via `Object`/wrapper.
3. Field is actually declared as wrapper `Integer`: use `get(receiver)`, handle the `null` case; do not use `getInt`.
4. Need to classify types reliably: use `field.getType()`, checking `isPrimitive()` and specific primitive classes; do not rely solely on the class of the returned object.

**Self-check:**

- What type of object does reading a `double price = 1.25;` field via `Field.get` return? → `Double`.
- What does reading an `Integer price = null;` field via `Field.get` return? → `null`; no new wrapper is boxed.
- Is `Field.getType()` of field `int count` `Integer.class` or `int.class`? → `int.class`.
- Can `getLong` read an `int` field? → Yes, thanks to primitive widening from `int` to `long`.
- Can `getInt` read a field declared as `Integer`? → No, because typed getters do not unbox reference fields.
- Does `Field.get` reading an `int[]` field return `Integer[]`? → No, it returns a reference to `int[]`; primitive arrays do not automatically turn into wrapper arrays.

The key takeaway is that **Reflection preserves the field's declared type**. Only the value returned through `Field.get(Object)` needs to be represented as `Object`, which is why primitives are boxed into wrappers; typed getters and `getType()` checks help keep this boundary clear.