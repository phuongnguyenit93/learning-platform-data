# `instanceof` Type Checking and Results When the Object Is `null` in Java

> **Java core — language-basics / Type Patterns**  
> **Environment:** Java 17+, preview disabled, single-file program using only the JDK.  
> **Goal:** Understand how `instanceof` checks an object's runtime type, know that `null instanceof T` is always `false`, use `instanceof` pattern matching for safe handling, and avoid casting errors, pattern variable scope issues, and generic limitations.

## 1. What Does `instanceof` Check?

The `instanceof` operator returns a **`boolean`**, checking whether a reference points to an object of the target reference type. Basic syntax:

~~~java
Object value = "Java";

boolean isText = value instanceof String;       // true
boolean isSequence = value instanceof CharSequence; // true
boolean isNumber = value instanceof Number;    // false
~~~

`value` is declared with type `Object`, but the **actual runtime** object is `String`. Because `String` implements `CharSequence`, both of the first two checks are true.

`instanceof` does not check the content or equality of two objects; it is a **runtime type relationship check**. Do not confuse it with `==`, `equals()`, or `getClass() == SomeType.class`.

| Check | Question |
| --- | --- |
| `x instanceof T` | Is `x` non-null and is its runtime object compatible with `T`? |
| `x == null` | Is the reference currently null? |
| `x.getClass() == T.class` | Is the runtime class **exactly** `T`, excluding subclasses? |
| `x.equals(y)` | Are the two objects equal according to the class's `equals` semantics? |

`getClass()` will throw `NullPointerException` when `x == null`; by contrast, `instanceof` is **null-safe**.

## 2. `null instanceof T` Always Returns `false`

`null` means **no object**. Therefore, a null reference is not an instance of any class, interface, or array type.

~~~java
Object value = null;

System.out.println(value instanceof Object); // false
System.out.println(value instanceof String); // false
System.out.println(value instanceof Runnable); // false
System.out.println(value instanceof int[]); // false
~~~

This result holds even for `Object`: `null instanceof Object` is also false. The operator **does not throw `NullPointerException`**, and a check returning true simultaneously confirms that the reference is non-null.

Example:

~~~java
Object maybeText = null;

if (maybeText instanceof String) {
    System.out.println("String");
} else {
    System.out.println("Null or another type");
}
// Prints: Null or another type.
~~~

**The `else` branch does not prove the object is null**: it also receives every object that is not a `String`. If you need to distinguish three states, check for null separately:

~~~java
if (maybeText == null) {
    System.out.println("MISSING");
} else if (maybeText instanceof String) {
    System.out.println("TEXT");
} else {
    System.out.println("OTHER_TYPE");
}
~~~

## 3. Subclasses, Interfaces, and Array Types

`instanceof` considers inheritance and interface implementation relationships, not just the exact class:

~~~java
class Animal {}
interface Named {}
class Dog extends Animal implements Named {}

Animal pet = new Dog();

boolean isAnimal = pet instanceof Animal; // true
boolean isDog = pet instanceof Dog;       // true
boolean isNamed = pet instanceof Named;   // true
~~~

The runtime object is `Dog`, so it is also an `Animal` and a `Named`. If an `Animal` reference points to a `Cat` that does not implement `Named`, checking for `Dog` or `Named` will be false.

Arrays are also objects:

~~~java
Object data = new int[] {1, 2};
boolean primitiveArray = data instanceof int[];   // true
boolean object = data instanceof Object;          // true
boolean referenceArray = data instanceof Object[]; // false
~~~

`int[]` is not an `Object[]`: a primitive array holds `int` values, not object references. With `String[]`, checking `instanceof Object[]` is true because its elements are references.

## 4. Checking the Type Before Casting

Reference casting **does not perform a safety check for you before casting**; if the runtime object is incompatible, Java throws `ClassCastException`:

~~~java
Object value = Integer.valueOf(7);

// String text = (String) value;
// If executed: ClassCastException.
~~~

The traditional pattern is written as:

~~~java
Object value = "Java";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length()); // 4
}
~~~

`instanceof String` is the **guard condition** before the cast. If `value` is null, the branch does not run; if the value is not a String, no cast happens either.

A subtle detail: **casting a null reference can be valid**:

~~~java
Object nothing = null;
String text = (String) nothing; // text remains null; cast does not throw CCE.
// text.length(); // If called: NullPointerException.
~~~

In other words, `instanceof` checks whether there is a compatible object; casting null does not create a new object and does not call methods on its own.

## 5. Java 17: Pattern Matching with `instanceof`

Java 17 supports **type pattern** syntax directly inside the check:

~~~java
Object value = "hello";

if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // HELLO
}
~~~

Here `text` is a **pattern variable**: when the check is true, Java automatically binds the reference with type `String`. As a result, you do not have to write an explicit cast again.

A pattern variable can only be used where Java determines that the type check succeeded (**flow scoping**):

~~~java
Object value = " Java ";

if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.trim()); // Java
}
~~~

With `&&`, the right-hand side is evaluated only when the type check is true, so `text` is valid and non-null on the right-hand side. Conversely:

~~~java
// DOES NOT COMPILE: text is not guaranteed to have a value on the right-hand side.
// if (value instanceof String text || text.isBlank()) { }
~~~

In `||`, the right-hand side runs only when the left-hand side is false, meaning the pattern variable `text` cannot have been assigned yet. Do not use a pattern variable outside the scope confirmed by the compiler.

## 6. Pattern Variables After `return` and Type Limitations

A clean Java 17 idiom is returning early when the pattern does not match:

~~~java
static String uppercaseIfString(Object input) {
    if (!(input instanceof String text)) {
        return "NOT_TEXT";
    }
    return text.toUpperCase(); // text is definitely matched.
}
~~~

If the negated condition is true, the method has already executed `return`. When control flow reaches the final line, Java knows `input instanceof String text` is true, so `text` is available and non-null.

**Limitations to remember:**

- `instanceof` applies to **reference types** in Java 17; you cannot write `int x = 3; x instanceof Integer`. To place an integer into an `Object`, autoboxing can create an `Integer`.
- The type on the right-hand side must be compatible with runtime checking constraints. You cannot directly test `instanceof List<String>` because generic type argument information is erased (`type erasure`); you can use `List<?>`.
- With a **type pattern**, Java 17 rejects certain cases where the static type of the expression is already a subtype of the pattern type (an unconditional check). For example, `String s = "a"; if (s instanceof String t)` is a compile error; if the type is already known to be `String`, such a pattern is unnecessary.
- Pattern matching for `instanceof` in Java 17 only introduces type patterns, not the record pattern syntax from newer Java versions.

Example with generics:

~~~java
Object value = java.util.List.of("A", "B");

if (value instanceof java.util.List<?> list) {
    System.out.println(list.size()); // 2
}

// DOES NOT COMPILE: type argument String cannot be checked at runtime.
// if (value instanceof java.util.List<String> list) { }
~~~

Checking `List<?>` does not prove that all elements are Strings. If business logic needs to verify the element type, you must inspect the elements individually rather than relying on `instanceof List<String>`.

## 7. Standalone Java 17+ Program

Create a file named **InstanceofNullDemo.java**:

~~~java
import java.util.List;

public final class InstanceofNullDemo {
    interface Named {}

    static class Animal {}
    static final class Dog extends Animal implements Named {}
    static final class Cat extends Animal {}

    private static String describe(Object input) {
        if (input instanceof String text) {
            return "text:" + text.length();
        }
        if (input instanceof Dog dog) {
            return "dog:" + dog.getClass().getSimpleName();
        }
        return "other-or-null";
    }

    private static String safeUpper(Object input) {
        if (!(input instanceof String text)) {
            return "NOT_TEXT";
        }
        return text.toUpperCase();
    }

    public static void main(String[] args) {
        Object absent = null;
        System.out.println("nullObject=" + (absent instanceof Object));
        System.out.println("nullString=" + (absent instanceof String));
        System.out.println("nullNamed=" + (absent instanceof Named));
        System.out.println("nullArray=" + (absent instanceof int[]));

        Object word = "Java";
        System.out.println("wordString=" + (word instanceof String));
        System.out.println("wordCharSequence="
                + (word instanceof CharSequence));
        System.out.println("wordNumber=" + (word instanceof Number));

        Animal pet = new Dog();
        System.out.println("dogAnimal=" + (pet instanceof Animal));
        System.out.println("dogDog=" + (pet instanceof Dog));
        System.out.println("dogNamed=" + (pet instanceof Named));

        Animal cat = new Cat();
        System.out.println("catDog=" + (cat instanceof Dog));
        System.out.println("catNamed=" + (cat instanceof Named));

        Object primitiveArray = new int[] {1, 2};
        Object referenceArray = new String[] {"A", "B"};
        System.out.println("intArray=" + (primitiveArray instanceof int[]));
        System.out.println("intObjectArray="
                + (primitiveArray instanceof Object[]));
        System.out.println("strObjectArray="
                + (referenceArray instanceof Object[]));

        Object boxedNumber = Integer.valueOf(7);
        System.out.println("boxedInteger="
                + (boxedNumber instanceof Integer));

        Object list = List.of("A", "B");
        System.out.println("listWildcard=" + (list instanceof List<?>));

        System.out.println("describeNull=" + describe(null));
        System.out.println("describeText=" + describe("hello"));
        System.out.println("describeDog=" + describe(new Dog()));
        System.out.println("upperNull=" + safeUpper(null));
        System.out.println("upperText=" + safeUpper("java"));

        Object nothing = null;
        String castNull = (String) nothing;
        System.out.println("castNull=" + (castNull == null));

        try {
            String wrong = (String) boxedNumber;
            System.out.println("castValue=" + wrong);
        } catch (ClassCastException ex) {
            System.out.println("badCast=ClassCastException");
        }

        if (word instanceof String text && !text.isBlank()) {
            System.out.println("patternValue=" + text.toUpperCase());
        }
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 InstanceofNullDemo.java
java InstanceofNullDemo
~~~

**Exact expected stdout:**

~~~text
nullObject=false
nullString=false
nullNamed=false
nullArray=false
wordString=true
wordCharSequence=true
wordNumber=false
dogAnimal=true
dogDog=true
dogNamed=true
catDog=false
catNamed=false
intArray=true
intObjectArray=false
strObjectArray=true
boxedInteger=true
listWildcard=true
describeNull=other-or-null
describeText=text:5
describeDog=dog:Dog
upperNull=NOT_TEXT
upperText=JAVA
castNull=true
badCast=ClassCastException
patternValue=JAVA
~~~

In particular, the **four `null...=false` lines** show that `instanceof` does not throw NPE when the reference is null. `intObjectArray=false` occurs because `int[]` is not an `Object[]`; `strObjectArray=true` occurs because `String[]` is a reference array. The pattern variable `text` is only used once the type has matched.

## 8. Common Mistakes and Exercises

| Situation | Result or Correct Handling |
| --- | --- |
| `null instanceof Object` | **false**, does not throw `NullPointerException` |
| `x instanceof String` is false | `x` may be null **or** belong to another type |
| Casting an object of the wrong type | Can throw `ClassCastException` |
| Casting `null` to `String` | Valid, result remains null |
| `x instanceof String s && !s.isBlank()` | Valid: `s` is available when the right-hand side runs |
| `x instanceof String s \|\| s.isBlank()` | Invalid due to pattern variable scope |
| `x instanceof List<String>` | Invalid due to type erasure; use `List<?>` when checking the raw shape |

**Exercise 1.** Given `Object x = null;`, predict `x instanceof Object`, `x instanceof String`, and `x instanceof Runnable`. When should you add `x == null`?

**Exercise 2.** Given `Object x = "Java";`, check `String`, `CharSequence`, and `Number`. Explain using type relationships.

**Exercise 3.** Write `if (x instanceof String text)` so that `text.length()` is called only when safe. Test passing null and an `Integer`.

**Exercise 4.** Explain why `List<?>` works in `instanceof` while `List<String>` does not; does that check prove every element is a String?

**Exercise 5.** Write a method that accepts an `Object` and returns one of three labels `"MISSING"`, `"TEXT"`, or `"OTHER"` without an unsafe cast and without losing the distinction for null.

### Key Takeaway

**`instanceof` returns true only when the reference is non-null and the runtime object is compatible with the target type.** Therefore, `null instanceof T` is always false. In Java 17, use `instanceof T name` to check the type and obtain a pattern variable safely; pay attention to flow scoping, generic limitations, and do not confuse `instanceof` with casting or separate null checks.
