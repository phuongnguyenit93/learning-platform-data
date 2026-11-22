# Mutating State Differs from Reassigning a Reference Variable in Java

> **Java core — language-basics / References and null**  
> **Requirements:** JDK 17 or higher; uses only the Java standard library.  
> **Goal:** Distinguish **modifying an object's state** (*mutation*) from **reassigning a reference variable** (*reassignment*); accurately predict effects across aliases, method parameters, `final`, arrays, and `String`.

## 1. Two Operations, Two Different Targets Affected

Consider a class with mutable state:

~~~java
class Meter {
    int value;
    Meter(int value) { this.value = value; }
}
~~~

Then:

~~~java
Meter first = new Meter(10);
Meter second = first;

second.value = 15;       // Mutation: modifies the object referenced by both variables.
second = new Meter(7);   // Reassignment: only changes the reference stored in second.
~~~

- **Mutation:** `second.value = 15` changes the `value` field of the **existing Meter object**. While `first` and `second` still point to the same object, reading `first.value` yields **15**.
- **Reassignment:** `second = new Meter(7)` creates a new object and then replaces **the reference value of the `second` variable**. The `first` variable still points to the old object with `value = 15`.
- **The assignment `second = first`** by itself only copies the reference value, **without creating an object copy**.

Before the reassignment operation:

~~~text
first  ─┐
        ├──> Meter(value = 15)
second ─┘
~~~

After `second = new Meter(7)`:

~~~text
first  ────> Meter(value = 15)
second ────> Meter(value = 7)
~~~

**Key takeaway:** Mutation changes the **data inside an object**; reassignment changes **which object a reference variable points to**. One operation does not automatically trigger the other.

## 2. Behavior Prediction Table

Suppose we start with `Meter a = new Meter(10); Meter b = a;`:

| Next statement | `a.value` | `b.value` / relationship | Explanation |
| --- | ---: | --- | --- |
| `b.value = 12;` | 12 | 12; `a == b` is true | Same object modified |
| `b = new Meter(20);` | 12 | 20; `a == b` is false | Only b receives a new reference |
| `b.value = 25;` | 12 | 25 | Modifies b's new object |
| `b = a;` | 12 | 12; `a == b` is true | b points back to the old object |
| `b = null;` | 12 | b is null | Only b no longer points to an object |

These rows are executed **in order** from top to bottom. `a == b` is a **reference identity** comparison, not a check for whether two objects have identical data.

Assigning `b = null` also **does not destroy the object**: if `a` still holds a reference, the object can still be used. Do not treat `null` as an immediate memory-freeing command.

## 3. Standalone Runnable Java 17+ Program

Create the file **`MutationVsReassignmentDemo.java`**:

~~~java
public final class MutationVsReassignmentDemo {
    private static final class Meter {
        private int value;

        Meter(int value) {
            this.value = value;
        }

        void increase(int amount) {
            value += amount;
        }

        int value() {
            return value;
        }
    }

    private static void mutate(Meter meter) {
        meter.increase(3);
    }

    private static void redirect(Meter meter) {
        meter = new Meter(99);
        System.out.println("insideRedirect=" + meter.value());
    }

    public static void main(String[] args) {
        Meter original = new Meter(10);
        Meter alias = original;

        System.out.println("initialSame=" + (original == alias));
        alias.increase(5);
        System.out.println("afterMutation=" + original.value());

        mutate(original);
        System.out.println("afterMethodMutation=" + alias.value());

        redirect(original);
        System.out.println("afterMethodRedirect=" + original.value());

        alias = new Meter(7);
        System.out.println("sameAfterReassign=" + (original == alias));
        System.out.println("original=" + original.value());
        System.out.println("alias=" + alias.value());

        alias = null;
        System.out.println("aliasNull=" + (alias == null));
        System.out.println("originalStill=" + original.value());

        final Meter fixed = original;
        fixed.increase(2);
        System.out.println("finalObjectValue=" + original.value());

        int[] firstArray = {1, 2};
        int[] secondArray = firstArray;
        secondArray[0] = 9;
        System.out.println("sharedArray=" + firstArray[0]);
        secondArray = new int[] {4, 5};
        System.out.println("afterArrayReassign=" + firstArray[0]
                + "," + secondArray[0]);

        String text1 = "Hi";
        String text2 = text1;
        text2 = text2.concat("!");
        System.out.println("strings=" + text1 + "," + text2);
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 MutationVsReassignmentDemo.java
java MutationVsReassignmentDemo
~~~

**Exact expected output:**

~~~text
initialSame=true
afterMutation=15
afterMethodMutation=18
insideRedirect=99
afterMethodRedirect=18
sameAfterReassign=false
original=18
alias=7
aliasNull=true
originalStill=18
finalObjectValue=20
sharedArray=9
afterArrayReassign=9,4
strings=Hi,Hi!
~~~

Reading each milestone:

1. `alias = original` makes both variables point to Meter 10, so `initialSame=true`.
2. `alias.increase(5)` modifies the shared object to 15; `mutate(original)` modifies it further to 18. Both variables see it.
3. `redirect(original)` receives a **copy of the reference value** through its parameter. The line `meter = new Meter(99)` only changes the **`meter`** variable inside the method; upon returning, `original.value()` is still 18.
4. `alias = new Meter(7)` changes the object that alias points to. `original` does not change, so `sameAfterReassign=false`.
5. `alias = null` only drops alias's reference; `original` still reads 18.
6. `fixed` is a `final` reference pointing to the same object as `original`. Calling `fixed.increase(2)` is allowed, so the object's value increases to 20.
7. Arrays are objects too: modifying `secondArray[0]` turns `firstArray[0]` into 9. However, assigning `secondArray = new int[] {...}` only changes the variable secondArray; firstArray's element remains 9.
8. `String` is immutable: `concat` does not modify the string `"Hi"`. The variable `text2` is assigned a reference to the resulting string `"Hi!"`; `text1` still yields `"Hi"`.


## 4. Boundary Between In-Place Mutating Methods and Returning a New Object

A method receiving a `Meter` receives a **copy of the reference value**. Calling `meter.increase(3)` inside the method mutates the shared object; assigning `meter = new Meter(99)` only changes the parameter variable. If an independent version is needed, the method can return `new Meter(old.value() + 1)` and the caller decides whether to write `original = nextMeter(original)`. The method signature/interface should make clear whether it **mutates** the input or **returns a new object**.


## 5. `final` Locks the Variable, Not the Object

`final Meter meter = new Meter(1);` allows `meter.increase(1)` if the API supports it, but does not allow `meter = new Meter(2)`. By the same logic, `final int[] numbers = {1, 2};` still allows `numbers[0] = 9`. To prevent data from being modified through another alias, you must rely on immutable design, access control, and how the API exposes state; simply putting `final` on a variable is not enough.


## 6. Designing APIs Around Intended State Changes

An API like `void increase(Meter meter)` expresses an operation that modifies shared state; an API like `Meter increased(Meter old)` can create and return a new value so the caller chooses whether to reassign the variable. For mutable objects, API documentation should clearly state whether inputs are modified and whether the result shares references with the old data.

If you do not want outsiders to modify internal state, consider a *defensive copy* or an immutable type. Copying a reference array with `clone()` creates a new array but can still share mutable object elements, so examine the data structure before choosing how to copy.

## 7. Common Mistakes and Exercises

| Misconception | Correct understanding |
| --- | --- |
| "`b = a` copies the entire object." | False: it only copies the **reference value** |
| "Modifying via b only affects b." | False if a and b reference the same mutable object |
| "`b = new Meter(...)` changes a too." | False: only variable b receives a new reference |
| "A method assigning `param = new ...` changes the caller's variable." | False: Java passes parameters by value |
| "`b = null` deletes the object." | False: only changes variable b; other aliases still use the object |
| "`final` forbids all changes to the object." | False: `final` forbids reassigning the variable, not mutation |
| "`String.concat` modifies the old String." | False: `String` is immutable; the result is a string value that may be new/reused depending on the API |

**Exercise 1.** Initialize `Meter a = new Meter(3); Meter b = a;`, then call `b.increase(2)`. Predict `a.value()` and `a == b`.

**Exercise 2.** After Exercise 1, execute `b = new Meter(10);` and `b.increase(1)`. Which operations affect a, and which affect only b?

**Exercise 3.** Pass a into `changeValue` and `changeVariable`. Predict before running: does a's object change? Does variable a point to a different object?

**Exercise 4.** Given `final int[] nums = {1, 2};`, try `nums[1] = 7;` and `nums = new int[]{3, 4};`. Which line is valid, and why?

**Exercise 5.** Write `String a = "X"; String b = a; b += "Y";` and print a and b. Why is this **reassigning a reference to the result** rather than mutating a String object?

### Summary

**Mutation** changes the state of an existing object and is observable through **every alias** to that object. **Reassignment** changes the reference stored in **a single variable**, without modifying the old object or reassigning other variables. When reading Java code, always ask: **"Does this line modify an object or change which object a variable points to?"** — that is the key to accurately predicting behavior.
