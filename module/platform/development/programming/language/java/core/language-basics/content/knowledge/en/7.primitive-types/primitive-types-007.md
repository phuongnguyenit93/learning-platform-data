# Distinguishing Primitive Types from Reference Types in Java 17+

Java distinguishes two groups of data types:

- **Primitive types**: a variable directly holds a value belonging to one of the eight types `byte`, `short`, `int`, `long`, `float`, `double`, `char`, `boolean`.
- **Reference types**: a variable holds a reference value pointing to an object or array, or holds `null`. Examples: `String`, `int[]`, a user-defined class, interface, enum, record, and the wrapper `Integer`.

Point to remember: **assigning a primitive variable to another variable of the same type copies the value; assigning a reference variable to another reference variable copies the reference value**, without automatically copying the object. Therefore, two names can access *the same object*.

## 1. Comparison Table

| Criterion | Primitive type | Reference type |
| --- | --- | --- |
| Examples | `int`, `double`, `char`, `boolean` | `String`, `Integer`, `int[]`, `Counter` |
| What does the variable hold? | Primitive value | Reference to an object/array, or `null` |
| Can `null` be assigned directly? | **No** | Yes |
| Assignment `b = a` | Copies the value | Copies the **reference**, does not clone the object |
| `==` | Compares values after appropriate type conversion rules | For two compatible references: checks **same object** (or both `null`) |
| Member access | Cannot call methods on a primitive value | Typically has fields/methods, depending on type |
| Default value of a **field** | `0`, `0.0`, `false`, `'\u0000'` by type | `null` |
| Uninitialized local variable | Cannot be read | Also **cannot be read** |

Java **does not automatically assign default values to local variables** of either group. A local variable must be definitely assigned before being read (*definite assignment*). Class/object fields, on the other hand, are default-initialized by type when needed.

Do not interpret the two groups as an absolute rule "primitives are always on the stack, objects are always on the heap": the JVM can optimize storage locations. What matters is understanding **value semantics and reference semantics**, not a simplified RAM diagram.

## 2. Runnable Java 17+ Program: Copying, Aliasing, and Parameters

Create the file **`ValueAndReferenceDemo.java`**:

~~~java
public class ValueAndReferenceDemo {
    static class Counter {
        int value;

        Counter(int value) {
            this.value = value;
        }
    }

    static void changePrimitive(int number) {
        number += 10;
        System.out.println("insidePrimitive=" + number);
    }

    static void changeObject(Counter counter) {
        counter.value += 10;
    }

    static void replaceReference(Counter counter) {
        counter = new Counter(99);
        System.out.println("insideReplace=" + counter.value);
    }

    public static void main(String[] args) {
        int original = 5;
        int copied = original;
        copied = 8;
        System.out.println("primitive=" + original + "," + copied);

        Counter first = new Counter(5);
        Counter alias = first;
        alias.value = 8;
        Counter independent = new Counter(8);

        System.out.println("sharedField=" + first.value);
        System.out.println("aliasIdentity=" + (first == alias));
        System.out.println("separateIdentity=" + (first == independent));
        System.out.println(
                "sameFieldValue=" + (first.value == independent.value));

        changePrimitive(original);
        System.out.println("afterPrimitive=" + original);

        changeObject(first);
        System.out.println("afterMutation=" + first.value);

        replaceReference(first);
        System.out.println("afterReassign=" + first.value);

        int[] numbers = {1, 2};
        int[] sameArray = numbers;
        sameArray[0] = 7;
        System.out.println("arrayFirst=" + numbers[0]);

        String text = "Java";
        String oldText = text;
        text = text + "17";
        System.out.println("oldText=" + oldText);
        System.out.println("newText=" + text);

        String a = new String("ok");
        String b = new String("ok");
        System.out.println("stringIdentity=" + (a == b));
        System.out.println("stringContent=" + a.equals(b));

        Integer boxed = 10;
        int unboxed = boxed;
        System.out.println("boxed=" + boxed + ",unboxed=" + unboxed);

        Integer missing = null;
        System.out.println("missingIsNull=" + (missing == null));
        try {
            int unsafe = missing;
            System.out.println("unsafe=" + unsafe);
        } catch (NullPointerException ex) {
            System.out.println("unboxing=NullPointerException");
        }
    }
}
~~~

Open Windows PowerShell or Linux/Bash in the directory containing the file. Requires **JDK 17+**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ValueAndReferenceDemo.java
java ValueAndReferenceDemo
~~~

**Expected output (in exact order):**

~~~text
primitive=5,8
sharedField=8
aliasIdentity=true
separateIdentity=false
sameFieldValue=true
insidePrimitive=15
afterPrimitive=5
afterMutation=18
insideReplace=99
afterReassign=18
arrayFirst=7
oldText=Java
newText=Java17
stringIdentity=false
stringContent=true
boxed=10,unboxed=10
missingIsNull=true
unboxing=NullPointerException
~~~

### Analyzing Common Points of Confusion

**Copying primitives:** `copied = original` receives the number `5`. Changing `copied` to `8` does not alter `original`; the two variables hold independent values.

**Copying references:** `alias = first` does not create a new `Counter`. Both variables reference the same object, so `alias.value = 8` makes `first.value` equal `8`. Meanwhile, `independent = new Counter(8)` creates a **different** object; even though both fields equal 8, `first == independent` is still `false`.

**Java always passes parameters by value:** In `changePrimitive`, the parameter receives a copy of the integer, so adding 10 does not change `original`. In `changeObject`, the parameter receives a copy of the **reference value** to the same Counter; modifying the object's field is visible to the caller as 18. In `replaceReference`, only the parameter variable `counter` is assigned a different reference: the object that `first` points to **is not replaced**, so it still has value 18.

**Arrays and strings:** `int[]` is a **reference type** even though its elements are primitive `int` values; modifying through `sameArray` affects the shared array. `String` is also a reference type, but the string object itself is **immutable**: `text + "17"` creates new string content and reassigns `text`, without modifying the old string content of `oldText`.

## 3. `==`, `equals`, and Comparing with the Right Meaning

~~~java
int x = 100;
int y = 100;
System.out.println(x == y); // true: int values are equal.

String left = new String("hi");
String right = new String("hi");
System.out.println(left == right);      // false: two different objects.
System.out.println(left.equals(right)); // true: contents are equal.
~~~

- For primitive numbers, `==` compares values after necessary numeric conversions. For `boolean`, it compares two logical values.
- For two references of comparable types, `==` checks **object identity**, not content equality.
- `equals` is a **method**; how equality is compared is decided by the class. `String.equals` compares contents, whereas a class like `Counter` in the example that **does not override `equals`** inherits `Object`'s identity-checking behavior.

**Do not use `==` to compare the contents of two arbitrary `String` objects**, even if `"a" == "a"` sometimes returns true due to Java's string literal interning mechanism. To handle strings that might be null, use `java.util.Objects.equals(left, right)` where appropriate.

## 4. `null`, Boxing, and Unboxing

`null` represents a reference that does not point to any object:

~~~java
String missing = null; // Valid.
Integer number = null; // Valid: Integer is a reference type.

// int count = null;    // Compile error: int is a primitive.
// boolean ok = null;   // Compile error.
~~~

`Integer` is the **wrapper class** for `int`, not a new primitive. Java can perform automatic **boxing** and **unboxing**:

~~~java
Integer boxed = 7;   // boxing: int -> Integer.
int raw = boxed;     // unboxing: Integer -> int.
~~~

If `boxed == null`, unboxing to `int` **throws `NullPointerException` at runtime**. This is the difference between a **compile-time** error (`int x = null;` is rejected) and a **runtime** error (`int x = nullableInteger;` is accepted by the type system but can fail).

A wrapper can also make `==` misleading: comparing **wrapper references with each other** is not a good choice for checking numeric values. When the goal is the value, use `equals` appropriately or unbox with a null check. Do not rely on the JVM possibly reusing certain wrapper objects.

## 5. `final` Does Not Necessarily Make an Object Immutable

~~~java
final int limit = 3;
// limit = 4; // Error: final primitive cannot be reassigned.

final int[] scores = {1, 2};
scores[0] = 9; // Valid: mutates the array object.
// scores = new int[]{3}; // Error: cannot reassign final reference.
~~~

`final` constrains **variable reassignment**. With reference types, the referenced object can still mutate if its API/type allows it; with `String`, object immutability comes from the **design of the String class**, not because every reference to it is `final`.

## 6. Common Mistakes and Fixes

| Symptom | Why? | How to handle |
| --- | --- | --- |
| `int n = null;` does not compile | Primitives do not accept `null` | Choose a valid value or a reference type if absence of value is truly needed |
| `String s = null; s.length();` | Dereferencing a null reference | Check `s != null` or enforce non-null input contracts |
| `Integer x = null; int n = x;` | Unboxing a null value | Check for null before converting |
| Two variables mutate the same object | Both point to one object | Make an actual copy when independent data is needed |
| `new String("x") == new String("x")` gives false | `==` compares two objects | Use `equals` to compare strings |
| Reassigning parameter to `new` does not change caller's variable | Parameter receives a copy of the reference | Return the new reference and reassign on the caller side if needed |
| `int[]` is treated as primitive | Arrays are always reference types | Distinguish the array type from its element type |

### Practical Checklist Rules

1. Ask **does the variable hold a direct value or a reference?** That is the first step to predicting the effect of assignment.
2. Ask **do two variables point to the same object?** When they do, mutating the object's state is observable through both names.
3. Ask **is the object mutable?** Sharing a reference to a `String` differs from sharing a reference to an array or an object with mutable fields.
4. Ask **can the reference be null?** Check before calling methods, accessing fields, or unboxing.

## 7. Self-Check Exercises

**Exercise 1.** Given `int a = 3; int b = a; b++;`, what is `a`?  
*Answer:* 3. `b` receives a copy of the value.

**Exercise 2.** Given `int[] a = {1}; int[] b = a; b[0] = 5;`, what is `a[0]`?  
*Answer:* 5. Both variables point to the same array.

**Exercise 3.** Why is `new String("ok") == new String("ok")` false while `equals` is true?  
*Answer:* The two `new` expressions create two objects; `==` checks identity, whereas `String.equals` compares contents.

**Exercise 4.** Can you pass an object into a Java method and assign `param = new Counter(...)` to replace the caller's variable as well?  
*Answer:* No. Java passes **a copy of the reference value**; reassigning the parameter does not change the original variable.

**Exercise 5.** Why is `Integer n = null;` valid while `int x = n;` can fail?  
*Answer:* `Integer` is a reference type that accepts null; unboxing null to `int` causes a `NullPointerException`.

## Key Takeaways

**Primitive variables hold values; reference variables hold reference values.** Java always passes parameters by value, so passing an object means copying the *reference*, not cloning the object. Distinguish `==` (identity for references) from `equals` (as defined by the class), watch out for `null`/unboxing, and check whether an object's state is mutable. This is the foundation for understanding arrays, `String`, objects, methods, and data sharing in Java.
