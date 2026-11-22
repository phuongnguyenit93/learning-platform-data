# `Integer`, `Long`, `Double`, `Boolean`, and Other Wrapper Classes — Java 17+

Java has eight **primitive types** (*primitives*) used to store values such as numbers, characters, and booleans (true/false). Each primitive has a corresponding **wrapper class** in the `java.lang` package. Wrappers are **reference types**: a variable can reference a wrapper object or hold the value `null`. Wrappers allow passing primitive values into APIs that work with objects, especially collections and generics.

~~~java
int count = 42;          // int: primitive value.
Integer boxed = count;   // Integer: autoboxing.
int again = boxed;       // int: unboxing.
~~~

`Integer` is not just a longer way to write `int`: the two types have **different semantics**, especially regarding `null`, comparisons, created objects, and boxing/unboxing cost.

## 1. Table of All Eight Primitive ↔ Wrapper Pairs

| Primitive | Wrapper in `java.lang` | Example |
| --- | --- | --- |
| `byte` | `Byte` | `Byte.valueOf((byte) 7)` |
| `short` | `Short` | `Short.valueOf((short) 300)` |
| `int` | `Integer` | `Integer.valueOf(42)` |
| `long` | `Long` | `Long.valueOf(9L)` |
| `float` | `Float` | `Float.valueOf(1.25f)` |
| `double` | `Double` | `Double.valueOf(3.5)` |
| `char` | `Character` | `Character.valueOf('J')` |
| `boolean` | `Boolean` | `Boolean.valueOf(true)` |

A few things to keep in mind:

- `int` and `Integer` are two **different types**; Java can automatically convert between them in appropriate contexts.
- Wrappers are **immutable**: there is no method to change the numeric/boolean/character value inside the same wrapper. Assigning `boxed = 43` makes the variable reference a different boxing result; it does not modify the contents of the old `Integer` object.
- `boolean`/`Boolean` cannot be cast to the numbers `0`/`1` using a Java cast. To map them, you must write a rule, for example `flag ? 1 : 0`.
- `Void` is a special class representing the `void` keyword in some reflection APIs; **it is not a ninth wrapper containing a primitive `void` value**.

## 2. Runnable Java 17+: All Wrappers, Parsing, Comparisons, and `null`

Save the file **`WrapperTypesDemo.java`** with the following source code:

~~~java
import java.util.List;

public class WrapperTypesDemo {
    public static void main(String[] args) {
        int primitive = 42;
        Integer boxed = primitive;  // Autoboxing int -> Integer.
        int unboxed = boxed;        // Unboxing Integer -> int.
        System.out.println("primitive=" + primitive);
        System.out.println("boxedInteger=" + boxed);
        System.out.println("unboxedInteger=" + unboxed);

        Long large = Long.valueOf(9_000_000_000L);
        Double fraction = Double.valueOf(3.5);
        Boolean enabled = Boolean.TRUE;
        Byte small = Byte.valueOf((byte) 7);
        Short medium = Short.valueOf((short) 32_000);
        Float ratio = Float.valueOf(1.25f);
        Character letter = Character.valueOf('J');

        System.out.println("long=" + large);
        System.out.println("double=" + fraction);
        System.out.println("boolean=" + enabled);
        System.out.println("other=" + small + "," + medium
                + "," + ratio + "," + letter);

        int parsedInt = Integer.parseInt("123");
        long parsedLong = Long.parseLong("9000000000");
        double parsedDouble = Double.parseDouble("2.5");
        boolean parsedBoolean = Boolean.parseBoolean("TrUe");
        boolean otherBoolean = Boolean.parseBoolean("yes");
        Integer boxedFromText = Integer.valueOf("123");

        System.out.println("parsedInt=" + parsedInt);
        System.out.println("parsedLong=" + parsedLong);
        System.out.println("parsedDouble=" + parsedDouble);
        System.out.println("parsedBoolean=" + parsedBoolean);
        System.out.println("parsedOtherBoolean=" + otherBoolean);
        System.out.println("valueOfInt=" + boxedFromText);

        Integer left = Integer.valueOf(1_000);
        Integer right = Integer.valueOf(1_000);
        System.out.println("sameValue=" + left.equals(right));

        Integer cachedA = Integer.valueOf(100);
        Integer cachedB = Integer.valueOf(100);
        System.out.println("cached100SameObject=" + (cachedA == cachedB));
        System.out.println("compare=" + Integer.compare(10, 20));

        List<Integer> numbers = List.of(3, 5, 7);
        int total = 0;
        for (Integer number : numbers) {
            total += number; // Unboxing to add with int.
        }
        System.out.println("listSum=" + total);
        System.out.println("charIsLetter=" + Character.isLetter(letter));

        Integer maybe = null;
        System.out.println("nullWrapper=" + (maybe == null));
        int fallback = maybe == null ? 0 : maybe;
        System.out.println("nullableDefault=" + fallback);

        try {
            int invalid = maybe; // Unboxing null.
            System.out.println("unexpected=" + invalid);
        } catch (NullPointerException ex) {
            System.out.println("unboxingNull=NullPointerException");
        }

        try {
            Integer.parseInt("abc");
        } catch (NumberFormatException ex) {
            System.out.println("badNumber=NumberFormatException");
        }

        System.out.println("nanPrimitiveEqual="
                + (Double.NaN == Double.NaN));
        System.out.println("nanWrapperEqual="
                + Double.valueOf(Double.NaN)
                        .equals(Double.valueOf(Double.NaN)));
        System.out.println("zeroPrimitiveEqual=" + (0.0 == -0.0));
        System.out.println("zeroWrapperEqual="
                + Double.valueOf(0.0).equals(Double.valueOf(-0.0)));
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file. Use **JDK 17 or later**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 WrapperTypesDemo.java
java WrapperTypesDemo
~~~

**Exact expected output** of the `java WrapperTypesDemo` command:

~~~text
primitive=42
boxedInteger=42
unboxedInteger=42
long=9000000000
double=3.5
boolean=true
other=7,32000,1.25,J
parsedInt=123
parsedLong=9000000000
parsedDouble=2.5
parsedBoolean=true
parsedOtherBoolean=false
valueOfInt=123
sameValue=true
cached100SameObject=true
compare=-1
listSum=15
charIsLetter=true
nullWrapper=true
nullableDefault=0
unboxingNull=NullPointerException
badNumber=NumberFormatException
nanPrimitiveEqual=false
nanWrapperEqual=true
zeroPrimitiveEqual=true
zeroWrapperEqual=false
~~~

The two JDK version check commands print environment-dependent information; they are not part of the expected output block above.

## 3. Wrappers and Primitives Convert via Boxing/Unboxing

**Autoboxing** boxes a primitive value into a wrapper when Java allows it; **unboxing** extracts the corresponding primitive value. In arithmetic, unboxing can happen without an explicit method call:

~~~java
Integer object = 42;           // Boxing int -> Integer.
int value = object;            // Unboxing Integer -> int.
int next = object + 1;         // Unbox then add -> 43.
~~~

A wrapper is allowed to hold `null`; therefore `Integer missing = null; int n = missing;` **compiles but throws `NullPointerException` at runtime**. Check for null before performing operations or enforce a required data contract; do not default to 0 if "missing" differs from "equal to 0". Uninitialized local variables do not automatically have the value `null` either; only fields/reference array elements receive defaults according to Java rules.

The dedicated boxing lesson explains overloads, numeric conversions, and the `++` operation in detail, while the unboxing-null lesson focuses on expressions/conditions that can cause an NPE.


## 4. String Conversion APIs: Return Types Must Be Clear

Wrapper classes have both factories returning a wrapper and parsers returning a primitive:

| Expression | Return Type |
| --- | --- |
| `Integer.parseInt("42")` | `int` |
| `Integer.valueOf("42")` | `Integer` |
| `Long.parseLong("42")` | `long` |
| `Double.parseDouble("2.5")` | `double` |
| `Boolean.parseBoolean("TrUe")` | `boolean` |
| `String.valueOf(42)` | `String` |

`Integer.parseInt("abc")` throws `NumberFormatException`; `Boolean.parseBoolean("yes")` returns `false`, so you must **validate separately** if the API only accepts `true`/`false`. When assigning the `int` returned by a parser to an `Integer`, Java boxes **after** the call; the method's return type does not change. The `parseInt()/valueOf()` lesson explains overloads/radix, and the `NumberFormatException` lesson classifies data errors.


## 5. Wrapper Value Differs from Object Identity

~~~java
Integer a = Integer.valueOf(1_000);
Integer b = Integer.valueOf(1_000);
System.out.println(a.equals(b)); // true.
~~~

For two `Integer` references, `a == b` checks **identity**, not the number inside. `Integer.valueOf(100)` is guaranteed to reuse wrappers in the `-128..127` cache range, but you cannot rely on `==` to compare values in general. Use `a.equals(b)` if `a` is non-null, or `Objects.equals(a, b)` if either side can be null. When comparing a wrapper with a **primitive**, Java can unbox, so null will again cause an NPE.

`Double.equals` and `Float.equals` also have different rules from the primitive `==` operator: two wrappers containing `NaN` are considered equal, whereas `+0.0` and `-0.0` are distinguished by `equals`. Therefore, you must clearly choose the desired semantics. The equality lesson analyzes mixed cases, while the cache lesson explains the guaranteed identity ranges for each wrapper.


## 6. Wrappers in Generics and Collections

Generics such as `List<T>` require a **reference type**:

~~~java
import java.util.List;

List<Integer> scores = List.of(3, 5, 7); // Valid.
// List<int> invalid;                    // Invalid.
~~~

Use `List<Integer>` because the elements are `Integer` objects. When adding an `int` to a `List<Integer>`, Java can box it; when retrieving an element for `int` arithmetic, Java can unbox it. `List.of(...)` creates a list that cannot be modified via add/remove operations; it **does not allow null elements**.

Compared to arrays:

~~~java
int[] primitiveArray = new int[2];        // Elements default to 0.
Integer[] wrapperArray = new Integer[2]; // Elements default to null.
~~~

If performance, memory, and avoiding null are priorities in loops processing large volumes, primitive arrays or primitive APIs may be more suitable than mass boxing. However, the choice should be based on actual requirements and measurements when needed, rather than assuming wrappers are always the wrong choice.

## 7. Wrappers Are Immutable, Reference Variables Can Still Be Reassigned

Wrappers do not allow modifying the value inside an instance. An operation on a wrapper variable may unbox, compute, box, and then **assign a resulting reference**; another variable holding the old reference is not changed:

~~~java
Integer count = 10;
Integer before = count;
count = count + 1;
System.out.println(count);  // 11
System.out.println(before); // 10
~~~

Declaring `final Integer fixed = 10;` prohibits **reassigning the variable** but is not the reason wrappers are immutable. The boxing lesson separately analyzes the `++` operator and implicit conversions.

## 8. Summary of Type Selection by Scenario

| When? | Common Suitable Types | Things to Remember |
| --- | --- | --- |
| Counters/calculations that always have a value | `int`, `long`, `double` | No null state |
| Value may not have been provided yet | `Integer`, `Long`, `Boolean` | Must define the meaning of null |
| Generic collections | `List<Integer>`, `Map<String, Long>` | Type arguments require reference types |
| Parsing numbers for calculation | `Integer.parseInt`, `Double.parseDouble` | Parsers return the corresponding primitive |

`Boolean` can represent three states—`TRUE`, `FALSE`, and `null`—if the data contract genuinely requires it. Do not automatically treat null as false or 0. The final lesson in this chapter applies these principles to models, APIs, validation, and performance.

## 9. Self-Check Exercises

1. **Matching:** What are the wrapper classes for `int`, `char`, `boolean`, and `double`?  
   *Answer:* `Integer`, `Character`, `Boolean`, and `Double`.
2. **Boxing:** What steps are involved in `Integer x = 7; int y = x;`?  
   *Answer:* Boxing `int -> Integer`, then unboxing `Integer -> int`.
3. **Null:** Does `Integer n = null; int x = n;` compile, and how does it behave at runtime?  
   *Answer:* It compiles; at runtime it throws `NullPointerException` when unboxing.
4. **Parsing:** How does `Integer.parseInt("12")` differ from `Integer.valueOf("12")`?  
   *Answer:* The former returns `int`; the latter returns `Integer`.
5. **Boolean:** What does `Boolean.parseBoolean("YES")` return?  
   *Answer:* `false`; only a string equal to `"true"` case-insensitively is treated as true.
6. **Comparison:** Why shouldn't you compare two `Integer` variables using `==`?  
   *Answer:* `==` checks object identity, which can be affected by caching; use `equals` to compare values when non-null.
7. **Floating-Point:** What does `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` return?  
   *Answer:* `true` by the definition of `Double.equals`, even though `Double.NaN == Double.NaN` is `false`.

## Memory Checklist

- [ ] Memorize the **eight primitive–wrapper pairs**, especially `char -> Character` and `int -> Integer`.
- [ ] Understand that **autoboxing/unboxing** is a conversion, not a permanent transformation of a primitive into a reference.
- [ ] Know that wrappers can be null and unboxing null causes `NullPointerException`.
- [ ] Use `parseXxx` when you want a primitive; use `valueOf` when you want a wrapper.
- [ ] Use `equals`/`Objects.equals` to compare wrapper values, without relying on `==` and caching.
- [ ] Recognize the specific rules of `Double`/`Float` for `NaN` and signed zero.
- [ ] Know that generics such as `List<Integer>` do not accept primitive type arguments like `int`.
- [ ] Choose primitives for data that always has a value, and wrappers when APIs/generics require them or null is a meaningful state.

**Conclusion:** The classes `Integer`, `Long`, `Double`, `Boolean`, `Byte`, `Short`, `Float`, and `Character` make it possible to work with primitive values in Java's object world. Use them properly: **keep data types clear, handle null before unboxing, distinguish value comparison from reference comparison, and choose the appropriate parsing/boxing method**.
