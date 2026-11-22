# Pass-by-Value for Primitives and References in Java Methods

## 1. Core Rule: Java Always Passes by Value

In Java, when calling a method, **the value of each argument expression** is used to initialize the **method's own parameter variable**. This mechanism is called *pass-by-value* and applies **to both primitive types and reference types**.

- **Primitive types** (`int`, `double`, `boolean`, `char`, ...): the parameter receives a copy of the value itself, such as `10` or `true`. Modifying the parameter does not change the variable at the call site.
- **Reference types** (`Person`, `String`, `int[]`, ...): the parameter receives a copy of the **reference value** pointing to the object. Two variables can reference the same object; operations that mutate the object's state through the parameter can be observed at the call site. However, **reassigning the parameter** does not change the caller's reference variable.

There is no `ref`, `out`, or “pass-by-reference” parameter syntax in Java method signatures. The phrase “pass by reference” is sometimes used inaccurately to describe arguments of reference types. Strictly speaking, Java **passes a copy of the reference value**, not the caller's variable itself for the method to reassign.

## 2. Passing Primitives: Changing the Parameter Only Takes Effect Inside

The example below is an illustrative snippet placed inside a class:

```java
static void increase(int value) {
    value += 10; // Only updates the local parameter
}

int x = 5;
increase(x);
// x is still 5
```

When calling `increase(x)`, the value `5` is copied into parameter `value`. The statement `value += 10` turns the parameter into `15`, yet the caller's variable `x` does not change.

Even when the parameter and the caller's variable have the same name, they are still two distinct variables in different scopes. The passed value is determined only **at the call**; changing the parameter afterward does not sync back to the original variable.

For `byte`, `short`, `char`, `int`, `long`, `float`, `double`, and `boolean`, the rule is the same (with appropriate type conversions under method invocation rules, such as `int` to `long`). To have the caller receive the new value, **return it and reassign**:

```java
static int increased(int value) {
    return value + 10;
}

int x = 5;
x = increased(x);
// x == 15
```

A `void` method cannot automatically push an update of a parameter back to the caller.

## 3. Passing References: Shared Object, Separate Parameter Variable

Consider a method taking an object with mutable state:

```java
class Person {
    String name;

    Person(String name) {
        this.name = name;
    }
}

static void rename(Person person) {
    person.name = "Lan"; // Mutates the shared object
}

static void replace(Person person) {
    person = new Person("Hoa"); // Reassigns the parameter variable
}
```

At the call site:

```java
Person p = new Person("Minh");
rename(p);  // p.name becomes "Lan"
replace(p); // p still points to the object whose name is "Lan"
```

When calling `rename(p)`, the reference value of `p` is copied into parameter `person`. Both variables point to the same object, so `person.name = "Lan"` changes the `name` field on that object.

When calling `replace(p)`, assigning `person = new Person("Hoa")` only changes the variable `person` **inside the method** to point to the new object. Variable `p` keeps the old reference. For the same reason, `person = null` does not make the caller's variable `p` become `null`.

You can visualize it as:

```text
Before reassigning the parameter:
  p -----------+---> Person("Lan")
  person ------+

After person = new Person("Hoa"):
  p ----------------> Person("Lan")
  person -----------> Person("Hoa")
```

The diagram only illustrates reference relationships, without asserting specific physical locations of variables or objects in memory.

## 4. Arrays Clarify Object Mutation vs. Parameter Reassignment

An `int[]` array is an **object**, so the parameter receives a copy of the **array reference**, not an automatic copy of each element.

~~~java
static void changeFirst(int[] numbers) { numbers[0] = 99; }
static void rebind(int[] numbers) { numbers = new int[]{7, 8}; }

int[] data = {1, 2};
changeFirst(data);
rebind(data);
System.out.println(java.util.Arrays.toString(data)); // [99, 2].
~~~

`changeFirst` mutates the shared object; `rebind` only changes the parameter variable. With two-dimensional arrays, replacing `matrix[1]` mutates an **element of the outer array**, whereas assigning `matrix = other` reassigns the parameter. The next lesson analyzes multidimensional arrays, aliasing, `clone()`, and array-mutation/return contracts separately.


## 5. Complete Java 17+ Example, Run and Verify Output

Create the file **`PassByValueDemo.java`**:

```java
import java.util.Arrays;

public class PassByValueDemo {
    static class Person {
        String name;

        Person(String name) {
            this.name = name;
        }
    }

    static void changeNumber(int number) {
        number = 99;
        System.out.println("Trong changeNumber: " + number);
    }

    static void changeElement(int[] values) {
        values[0] = 99;
    }

    static void replaceArray(int[] values) {
        values = new int[]{7, 8};
        System.out.println("Trong replaceArray: " + Arrays.toString(values));
    }

    static void rename(Person person) {
        person.name = "Lan";
    }

    static void replacePerson(Person person) {
        person = new Person("Hoa");
        System.out.println("Trong replacePerson: " + person.name);
    }

    static void changeString(String text) {
        text = text.toUpperCase();
        System.out.println("Trong changeString: " + text);
    }

    static int[] doubledCopy(int[] source) {
        int[] copy = source.clone();
        for (int i = 0; i < copy.length; i++) {
            copy[i] *= 2;
        }
        return copy;
    }

    public static void main(String[] args) {
        int number = 10;
        changeNumber(number);
        System.out.println("Sau changeNumber: " + number);

        int[] values = {1, 2};
        changeElement(values);
        System.out.println("Sau changeElement: " + Arrays.toString(values));
        replaceArray(values);
        System.out.println("Sau replaceArray: " + Arrays.toString(values));

        Person person = new Person("Minh");
        rename(person);
        System.out.println("Sau rename: " + person.name);
        replacePerson(person);
        System.out.println("Sau replacePerson: " + person.name);

        String word = "java";
        changeString(word);
        System.out.println("Sau changeString: " + word);

        int[] doubled = doubledCopy(values);
        System.out.println("Mang goc: " + Arrays.toString(values));
        System.out.println("Ban sao gap doi: " + Arrays.toString(doubled));
    }
}
```

Open a terminal in the directory containing the file. With **JDK 17 or later**, run identically on Windows (PowerShell/CMD) or Linux/macOS:

```bash
javac -encoding UTF-8 PassByValueDemo.java
java PassByValueDemo
```

**Exact stdout output** (a successful `javac` command prints no lines):

```text
Trong changeNumber: 99
Sau changeNumber: 10
Sau changeElement: [99, 2]
Trong replaceArray: [7, 8]
Sau replaceArray: [99, 2]
Sau rename: Lan
Trong replacePerson: Hoa
Sau replacePerson: Lan
Trong changeString: JAVA
Sau changeString: java
Mang goc: [99, 2]
Ban sao gap doi: [198, 4]
```

The pairs of results illustrate three different situations:

1. **Modifying an `int` parameter variable** in `changeNumber`: the outer value remains `10`.
2. **Mutating the shared object** in `changeElement` and `rename`: the array contents and `Person` field genuinely change.
3. **Reassigning a reference parameter to another object** in `replaceArray` and `replacePerson`: the caller continues using the original object.

The `doubledCopy` method illustrates how to create a copy for computation without modifying the input array.

## 6. Why Do `String` and `Integer` Often Cause Confusion?

`String` is an **immutable object**. The expression `text.toUpperCase()` creates/returns a corresponding string without modifying the existing `String` object; the subsequent assignment `text = ...` only reassigns the **local parameter**. Therefore, after `changeString(word)`, the caller's variable `word` still holds `"java"`.

`Integer` is also immutable; in addition, Java supports **autoboxing/unboxing**, making syntax look as if it mutates the object:

```java
static void addOne(Integer value) {
    value++; // Unboxes, increments int, boxes into Integer, then reassigns parameter
}

Integer count = 3;
addOne(count);
// count is still 3
```

This is illustrative code inside a class/method. The expression `value++` does not modify the original `Integer` object. If `value` is `null`, this unboxing operation throws a `NullPointerException`.

Do not infer that “reference-type arguments always change outer variables”: only **state mutation on the same mutable object** produces an effect observable through another reference. If the object is immutable or the method only reassigns the parameter, the outer object/variable does not change.

## 7. Limits of Reference Parameters in APIs

`final` forbids **reassigning the parameter variable**, and does not turn the referenced object into an immutable one:

~~~java
static void setFirst(final int[] data) {
    data[0] = 5;          // Valid.
    // data = new int[2]; // Error: final parameter.
}
~~~

A `null` argument is also passed **by value**; accessing `person.name` when the parameter is null causes `NullPointerException`. Assigning `person = new Person(...)` inside the method does not change the caller's variable that was null.

To return an array result without modifying the source, create a copy and **return** it; for example, `int[] copy = input.clone();` on an `int[]` creates a new array holding independent primitive values. For an object array, `clone()` only **shallow-copies** the element references; `int[][].clone()` still shares the rows.

API names like `sortInPlace` and `sortedCopy` should make clear whether they **mutate the input data** or **return a new array**. This topic explains the general rule for primitives/references; the array-parameter lesson goes deeper into mutating elements, reassigning rows of multidimensional arrays, and safe copying.


## 8. Common Mistakes and Review Questions

| Statement | True/False | Explanation |
| --- | --- | --- |
| “Java passes `int` by value, but passes `Person` by reference.” | **False** | Both are passed by value; for `Person`, the copied value is the reference. |
| “Assigning `person = new Person(...)` changes the caller's argument variable.” | **False** | It only reassigns the separate parameter variable. |
| “`person.name = ...` can change the object observed at the call site.” | **True** | When both references point to the same object with mutable state. |
| “Assigning `numbers[0] = 99` differs from assigning `numbers = new int[]{...}`.” | **True** | One modifies an element of the shared array object, while the other only changes the local reference. |
| “A `final int[]` parameter forbids modifying array elements.” | **False** | `final` only forbids reassigning the parameter variable. |
| “`String` does not change after `text = text.toUpperCase()` in a method because Java passes by value.” | **True**, regarding the caller's variable | `String` is immutable; the caller's variable still points to the old value. |

**Key Takeaway:** Always separate three actions: **(1)** copying the argument's value into the parameter, **(2)** mutating the state of a shared object, and **(3)** reassigning the parameter variable itself. Only (2) can change data observed through the caller's reference without needing a return value.