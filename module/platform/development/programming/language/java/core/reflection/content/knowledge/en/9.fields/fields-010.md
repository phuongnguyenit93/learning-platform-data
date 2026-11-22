# `null` values with reference and primitive fields in Java Reflection

When working with `java.lang.reflect.Field`, you must distinguish **the field's declared type**, **its actual value**, and **the object containing the field**. A reference-type field can hold `null`; a primitive-type field cannot hold `null`. However, both are read via `Field.get(Object)`, which has **return type `Object`**. That very fact easily causes misunderstandings when writing mappers, serializers, or Reflection frameworks.

This lesson explains why `Field.get()` on a primitive returns a wrapper instead of `null`, why `Field.set(..., null)` fails on a primitive, the difference between `Integer` and `int`, how Reflection converts numeric types, and the completely different meaning of a `null` receiver parameter.

## 1. First: `null` is a reference value, not a primitive value

Java has eight primitive types: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`. A primitive stores a value within its type's range; **there is no `null` state**. Conversely, a reference-type field such as `String`, `Integer`, `List<String>`, or an application type can hold an object reference or `null`.

| Declared field | Actual field type | Default value before explicit assignment | Can `null` be assigned? |
|---|---|---|---|
| `String name;` | `String` reference | `null` | Yes |
| `Integer age;` | `Integer` wrapper reference | `null` | Yes |
| `int age;` | Primitive `int` | `0` | No |
| `boolean enabled;` | Primitive `boolean` | `false` | No |
| `char letter;` | Primitive `char` | `'\\u0000'` | No |
| `double amount;` | Primitive `double` | `0.0` | No |

In the example above, default values apply to **instance fields** of an allocated object or **static fields** when preparing a class per JVM rules; **local variables** are not automatically assigned default values for immediate use.

Do not confuse these two declarations:

```java
Integer quantity = null; // valid: Integer is a reference type
int count = 0;           // valid: int is primitive
// int missing = null;   // compile error: null cannot convert to int
```

`Integer` is a wrapper class for `int`, yet `Integer.class.isPrimitive()` returns `false`. An `Integer` wrapper can be `null`; a primitive `int` cannot.

## 2. Reading with `Field.get`: primitives are boxed

Important signature:

```java
Object value = field.get(receiver);
```

`Field.get(Object obj)` returns `Object`. If the field is a reference type, the result is the reference value the field currently holds, **which may be `null`**. If the field is primitive, Reflection **boxes** the value into the corresponding wrapper before returning.

| Declared field type | Value in field | `Field.get(...)` returns |
|---|---|---|
| `String` | `null` | `null` |
| `Integer` | `null` | `null` |
| `Integer` | `Integer.valueOf(5)` | An `Integer` with value `5` |
| `int` | `5` | An `Integer` with value `5`; not `null` |
| `boolean` | `false` | A `Boolean` with value `false` |
| `char` | `'A'` | A `Character` with value `'A'` |

Therefore, checking `if (field.get(obj) == null)` can detect a **null reference**, but **cannot** detect an "unassigned" state on a primitive. If a primitive holds `0`, `false`, or `'\\u0000'`, that is still a **valid value** of the field.

In particular, Java Reflection **does not** treat `0` or `false` as `null`. If a system wants to represent a "no data" state, it needs its own convention, a nullable wrapper, an appropriate `Optional` type, or other metadata; it cannot rely on a primitive to hold `null`.

### Reading primitive types with specialized getters

`Field` has methods `getBoolean`, `getByte`, `getShort`, `getChar`, `getInt`, `getLong`, `getFloat`, and `getDouble`. These methods return the corresponding **primitive**, not a wrapper or `null`.

```java
Field score = Person.class.getField("score"); // assuming public int score
int result = score.getInt(person);
```

This is an illustrative snippet, assuming `Person` and `person` have already been declared. `getInt` can read primitive fields convertible to `int` via **widening primitive conversion** (e.g., `byte` or `short` fields); it does **not** automatically unbox a **field declared as `Integer`**.

For example, with a field declared `Integer nullableScore`, `field.get(person)` returns `Integer` or `null`; meanwhile, `field.getInt(person)` throws **`IllegalArgumentException`**, even when `nullableScore` is actually non-`null`. The check is based on **the field's declared type**, not a wrapper object that happens to be inside it.

## 3. Writing with `Field.set`: handling `null` by target type

Signature:

```java
field.set(receiver, value);
```

`receiver` is the object owning the **instance field**, or can be `null` for a **static field**. `value` is the value **to be written to the field**. These two parameters have completely different roles.

### Reference fields accept `null`

```java
Field name = Person.class.getField("name"); // assuming public String name
name.set(person, null);                     // valid if writable
```

A reference can accept `null`, including wrappers like `Integer` or `Boolean`. Aside from `null`, the written value must be compatible with the field's declared type under assignment/Reflection rules. A `String` field cannot accept an `Integer` simply because both are `Object`.

### Primitive fields reject `null`

```java
Field age = Person.class.getField("age"); // assuming public int age
age.set(person, null);                    // throws IllegalArgumentException
```

Because `int` has no `null`, `Field.set` cannot turn `null` into `0` or another default value. The operation throws **`IllegalArgumentException`**. This is an error **converting the value to write**, not because Reflection failed to find the field.

Avoid the inference "Java auto-unboxes, so `null` turns into the primitive default": unboxing a `null` wrapper in a regular Java expression also does not produce a valid value.

### Writing primitives via wrappers and widening

When `value` is a **non-null** wrapper, `Field.set` can unbox and then perform a **widening primitive conversion** if the target type allows:

```java
Field count = Person.class.getField("count"); // assuming public int count
count.set(person, Integer.valueOf(11));       // succeeds
count.set(person, Short.valueOf((short) 12)); // succeeds: short -> int
count.set(person, Long.valueOf(13L));         // throws IllegalArgumentException
```

This is an illustrative example. `long -> int` is **narrowing**, so it is not automatically converted in `Field.set`. Reflection also never automatically calls `String.valueOf` or parses strings:

```java
// Assuming count has type int:
count.set(person, "42"); // does NOT auto-parse; throws IllegalArgumentException
```

If external data is a `String`, the **parse and validate** step must occur before writing. If the input is `null` while the target field is primitive, the mapper must define an explicit rule: reject missing data, skip the assignment to keep the current value, or pick a specified default; do not silently convert `null` to `0`/`false` without a data contract.

### Specialized setters

`Field.setInt(receiver, 10)` or `Field.setBoolean(receiver, true)` accepts a **primitive** directly in its second parameter, leaving no room for `null`. Type conversion still follows the appropriate rules of specialized setters. `setInt` is not used to assign a field **declared as type `Integer`**, because that field is a reference type.

## 4. Complete Java 17+ example, verified for compilation and stdout

Save as file **`FieldNullDemo.java`**:

```java
import java.lang.reflect.Field;

public class FieldNullDemo {
    public static class Sample {
        public String nickname;
        public Integer nullableCount;
        public int count = 7;
        public boolean enabled;
        public static String appName;
        public static int globalCount = 3;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Sample sample = new Sample();
        Class<Sample> type = Sample.class;
        Field nickname = type.getField("nickname");
        Field nullableCount = type.getField("nullableCount");
        Field count = type.getField("count");
        Field enabled = type.getField("enabled");
        Field appName = type.getField("appName");
        Field globalCount = type.getField("globalCount");

        System.out.println("reference initial: " + nickname.get(sample));
        System.out.println("wrapper initial: " + nullableCount.get(sample));
        Object countObject = count.get(sample);
        System.out.println("primitive get: " + countObject + " / " + countObject.getClass().getSimpleName());
        System.out.println("boolean get: " + enabled.get(sample));
        System.out.println("types: " + count.getType().getName() + ", " + nullableCount.getType().getName());
        System.out.println("count primitive: " + count.getType().isPrimitive());
        System.out.println("nullableCount primitive: " + nullableCount.getType().isPrimitive());

        nickname.set(sample, null);
        nullableCount.set(sample, null);
        System.out.println("both reference null: " + (nickname.get(sample) == null && nullableCount.get(sample) == null));

        try {
            count.set(sample, null);
        } catch (IllegalArgumentException e) {
            System.out.println("primitive rejects null: " + e.getClass().getSimpleName());
        }

        count.set(sample, Integer.valueOf(11));
        System.out.println("count via wrapper: " + count.getInt(sample));

        count.set(sample, Short.valueOf((short) 12));
        System.out.println("count via widening: " + count.getInt(sample));

        try {
            count.set(sample, Long.valueOf(13L));
        } catch (IllegalArgumentException e) {
            System.out.println("narrowing rejected: " + e.getClass().getSimpleName());
        }

        try {
            nullableCount.getInt(sample);
        } catch (IllegalArgumentException e) {
            System.out.println("typed getter on wrapper field: " + e.getClass().getSimpleName());
        }

        System.out.println("static reference before: " + appName.get(null));
        appName.set(null, "demo");
        System.out.println("static reference after: " + appName.get(null));
        System.out.println("static primitive: " + globalCount.getInt(null));

        try {
            nickname.get(null);
        } catch (NullPointerException e) {
            System.out.println("instance receiver null: " + e.getClass().getSimpleName());
        }
    }
}
```

Compile and run in the directory containing the file, using JDK 17 or newer:

```bash
javac FieldNullDemo.java
java FieldNullDemo
```

**Stdout:**

```text
reference initial: null
wrapper initial: null
primitive get: 7 / Integer
boolean get: false
types: int, java.lang.Integer
count primitive: true
nullableCount primitive: false
both reference null: true
primitive rejects null: IllegalArgumentException
count via wrapper: 11
count via widening: 12
narrowing rejected: IllegalArgumentException
typed getter on wrapper field: IllegalArgumentException
static reference before: null
static reference after: demo
static primitive: 3
instance receiver null: NullPointerException
```

**Output explanation:**

1. `nickname` and `nullableCount` are both **reference fields**, defaulting to `null`. `enabled` is a primitive boolean, so it defaults to `false`.
2. `count` is declared `int` and holds `7`; `Field.get` boxes it into `Integer`. Thus `countObject.getClass().getSimpleName()` prints `Integer`, with no `null` value.
3. `Field.getType()` gives **the declared type**: `int` for `count`, `java.lang.Integer` for `nullableCount`. `isPrimitive()` distinguishes the two cases even though both can be read via `Object`.
4. Writing `null` to the two reference fields succeeds. Writing `null` to primitive `count` throws `IllegalArgumentException`.
5. `Integer(11)` is unboxed to `int`; `Short(12)` is unboxed and widened from `short` to `int`; `Long(13)` cannot narrow to `int` under this API.
6. `nullableCount.getInt(sample)` fails **because the declared type is `Integer`**, not because the field value happens to be `null`. Even if the field held `Integer.valueOf(5)`, this specialized getter still cannot read a reference field.
7. `appName.get(null)` and `appName.set(null, "demo")` operate on a **static field**; `null` here is the **receiver**, not the value to write. Conversely, `nickname.get(null)` is an instance field with a `null` receiver, so it throws `NullPointerException`.

## 5. Two `null` positions in `Field.get`/`Field.set` have different meanings

Look at the signatures:

```java
Object read = field.get(receiver);
field.set(receiver, value);
```

Distinguish two completely independent cases.

| Operation | `receiver` | `value` | Result |
|---|---|---|---|
| Reading instance field | Valid object instance | Not applicable | Succeeds if read permission exists |
| Reading instance field | `null` | Not applicable | `NullPointerException` |
| Reading static field | `null` | Not applicable | Valid; receiver is ignored |
| Writing instance reference field | Valid object instance | `null` | Valid if field is writable |
| Writing instance primitive field | Valid object instance | `null` | `IllegalArgumentException` |
| Writing static reference field | `null` | `null` | Valid if field is writable |
| Writing static primitive field | `null` | `null` | `IllegalArgumentException` |

For a static field, the `receiver` parameter of `Field.get`/`Field.set` **is not used to specify an instance** and `null` can be passed. When accessing a static field, the JVM may need to **initialize the declaring class** if not yet initialized; retrieving `Field` metadata beforehand does not automatically mean the static initializer has already run.

For an instance field, `receiver` must be an instance compatible with the field's declaring class. Passing **an incompatible object** may cause Reflection to throw `IllegalArgumentException`. If `receiver` is `null`, the error is `NullPointerException`. Do not confuse these two receiver errors with `IllegalArgumentException` caused by **a value incompatible with a primitive type** in `Field.set`.

An example very easy to misread:

```java
Field global = Sample.class.getField("appName");
global.set(null, null); // null receiver: valid for static;
                        // null value: valid because appName is String
```

Here `global.set(null, null)` is completely valid if the field is **static, reference-typed, and writable**.

## 6. Checking the declared type before handling nullable data

In generic mapper code, the field's type is a more reliable source of truth than inferring from the current value:

```java
// Illustrative snippet in a mapper: field has been found,
// target is a compatible instance; incoming comes from outside.
Class<?> targetType = field.getType();

if (incoming == null && targetType.isPrimitive()) {
    throw new IllegalArgumentException(
            "Missing value for primitive field: " + field.getName());
}

field.set(target, incoming);
```

This snippet **is not a standalone runnable program**; variables `field`, `target`, and `incoming` are inputs to the mapper logic. It proactively rejects `null` input before calling `Field.set` on a primitive. When `incoming` is non-`null`, you still need to ensure the object has a type compatible with the field (including valid unboxing/widening); a `null` check **does not replace full validation**.

If the system needs to distinguish **"no value provided"** from **"value `0` provided"**, a primitive field alone is insufficient. Common approaches:

- Use `Integer`, `Boolean`, `Double`, etc. to represent nullable state; decide when `null` must be rejected.
- Track input presence via key presence, request data, or a separate flag field, instead of treating `0` as "absent".
- Apply defaults **at the business validation layer** intentionally. For instance, for an `int retries` field, missing data can be rejected or assigned `3` by contract. Reflection itself does not decide that default.
- For immutable objects or records, prefer constructors/factories to establish valid state rather than trying to deep-write `final` fields.

Be careful when data from JSON/databases distinguishes `null` from a missing value: `null`, missing key, and `0` are **three different states** depending on the schema. Reflection only reads/writes according to Java types; it does not infer business semantics on its own.

## 7. Access, `final`, and errors unrelated to `null`

Before a read/write succeeds, Reflection also checks visibility and module access:

- `getField("name")` looks up a **public** field; `getDeclaredField("name")` looks up a directly declared field, including `private`. Finding a private field **does not automatically grant permission** to read/write it.
- `Field.get`/`Field.set` may throw **`IllegalAccessException`** if the caller lacks sufficient permissions. With named modules, `setAccessible(true)` may be rejected with **`InaccessibleObjectException`** if the package is not appropriately `opens`-ed.
- `final` does not change a field's `null` rules; however, **writing** `final` via Reflection has its own restrictions. In particular, do not treat `setAccessible(true)` as a guaranteed way to mutate every final field, record component, or internal state.
- `getType()` retrieves the declared type; it does not read values and requires no receiver. `Field.get(null)` on a static field can trigger initialization of the target class.
- If an error occurs during static initialization, operating on a static field can fail due to the class initializer; that is not proof that a `null` static receiver is forbidden.

| Error | Typical context | Distinguishing from a `null` value |
|---|---|---|
| `IllegalArgumentException` | Writing `null` to a primitive, writing an incompatible wrapper, forbidden narrowing, or wrong receiver type | Need to identify whether the error is due to **value** or **receiver** |
| `NullPointerException` | Calling `Field.get(null)`/`Field.set(null, ...)` on an **instance field** | `null` in **receiver**, not the field value |
| `IllegalAccessException` | Not permitted to read/write the member | Access error, not primitives lacking null |
| `NoSuchFieldException` | Field not found with that name/lookup scope | Occurs at the lookup step |
| `InaccessibleObjectException` | Cannot enable deep access under JPMS via `setAccessible(true)` | Encapsulation error |
| `ExceptionInInitializerError` | Static initializer throws an exception during class initialization | May appear when actually using a static field |

## 8. Common misconceptions

1. **"`Field.get` returns `Object`, so primitive fields can also yield `null`."** False: primitives are **boxed** into non-null wrappers.
2. **"`Integer` is a primitive."** False: `Integer` is a reference type and can hold `null`.
3. **"`Field.set(obj, null)` automatically assigns `0` to `int`."** False: the operation throws `IllegalArgumentException`.
4. **"`Field.getInt` can read a field declared as `Integer` if the wrapper is non-null."** False: this specialized getter requires a **primitive** type with a valid conversion.
5. **"`Field.set` accepts any numeric type and automatically coerces it to the primitive."** False: only valid unboxing/widening is performed; **narrowing** does not happen automatically.
6. **"`Field.get(null)` returns null because the receiver is null."** False: for **static fields**, a null receiver is valid and the result depends on the field's value. For instance fields, a null receiver causes an error.
7. **"`0` is equivalent to a field with no data."** False: `0` is a valid primitive value; missing/null must be represented at another model/schema level if meaningful.
8. **"Public fields are always writable."** Not enough: module permissions, `final`, value type, and receiver compatibility can all affect it.
9. **"`null` always leads to `NullPointerException`."** False: for `Field.set(receiver, null)` on a primitive, it is normally **`IllegalArgumentException`**; `NullPointerException` applies when an instance receiver is `null`.
10. **"Calling `getClass()` on a newly read value is always safe."** False: for a **reference field currently holding null**, `field.get(receiver)` returns `null`; calling `getClass()` on that result causes `NullPointerException`. Use `field.getType()` if you want the **declared type**.

## 9. Self-check questions

**Question 1.** A class has `public int n;` (not explicitly assigned). What value does `Field.get(object)` return?

**Answer:** An `Integer` with value `0` due to boxing primitive `int`. Not `null`.

**Question 2.** A class has `public Integer n;` (not explicitly assigned). How do `Field.get(object)` and `Field.getInt(object)` differ?

**Answer:** `get` returns `null`. `getInt` throws `IllegalArgumentException` because the declared type is `Integer` (reference), even if the field is later assigned a non-null wrapper.

**Question 3.** Does `Field.set(instance, null)` always cause an error?

**Answer:** No. For a writable reference field, assigning `null` is valid. For a primitive field, `null` is rejected with `IllegalArgumentException`.

**Question 4.** Does `field.get(null)` always cause `NullPointerException`?

**Answer:** No. For static fields, `null` is a valid receiver. For instance fields, a null receiver leads to `NullPointerException`.

**Question 5.** Can field `public int n;` accept `Short.valueOf((short) 5)` via `Field.set`? Can it accept `Long.valueOf(5L)`?

**Answer:** `Short` is unboxed and widened `short -> int`, so it can be assigned. `Long` requires narrowing `long -> int`, so `Field.set` throws `IllegalArgumentException`.

**Question 6.** A serializer receives JSON `{"age": null}` while the Java model declares `int age`. How does Reflection handle it on its own?

**Answer:** `Field.set(target, null)` cannot set primitive `int` to null and will throw `IllegalArgumentException`. The serializer/application must apply the schema: reject, set an explicit default, or change the model to `Integer` if nullable is a valid state.

## Standard documentation

- Java SE API — `java.lang.reflect.Field`: `get(Object)`, `getInt(Object)`, `set(Object, Object)`, `setInt(Object, int)`, `getType()`, and exceptions.
- Java SE API — `java.lang.Class`: `isPrimitive()`.
- Java Language Specification — §4.2 Primitive Types and Values; §4.3 Reference Types and Values; §4.12.5 Initial Values of Variables; §5.1.2 Widening Primitive Conversion; §5.1.7 Boxing Conversion; §5.1.8 Unboxing Conversion.

**Remember:** `null` is a state of a **reference**; primitives cannot store `null`. `Field.get` boxes primitives into non-null wrappers; `Field.set(receiver, null)` is only valid if **the field type** and write permissions allow it. `receiver == null` is a different matter: usable for **static fields**, but cannot be used to read/write **instance fields**.