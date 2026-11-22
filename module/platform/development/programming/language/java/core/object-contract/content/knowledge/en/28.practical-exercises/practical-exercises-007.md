# Designing a Class Containing Arrays and Testing Defensive Copying

## 1. The Problem: Is a Class Containing an Array Truly Immutable?

We need to build a **SensorSnapshot** class containing a **String** device code and an **int[]** sequence of measurements. After creating a snapshot, mutating the source array or an array obtained from a getter must not alter the snapshot's data. This is a comprehensive practice on the **object contract**: designing data with clear ownership, testing **equals**, **hashCode**, and **toString**, and avoiding breaking stability when the object resides in a **HashSet/HashMap**.

Target outcomes:
- Explain **aliasing**: multiple references pointing to the same mutable array.
- Perform defensive copying at both boundaries: **constructor input** and **getter return**.
- Compare/hash arrays by **element values**, not by reference identity.
- Properly handle **int[][]** by copying each row; understand why **Object[]** containing mutable elements is harder.
- Use tests that actively mutate source data and getter data to prove these guarantees.

Arrays are mutable objects. **private** prevents external code from accessing the field directly, while **final** only prevents reassigning the field reference; neither **forbids mutating array elements**. A class can use a **private final int[]** field and still be mutated from outside.

## 2. Inspecting the Bug Before Designing the Correct Version

~~~java
// Intentionally buggy example, not part of the main program.
final class UnsafeSnapshot {
    private final int[] values;

    UnsafeSnapshot(int[] input) {
        this.values = input;   // Bug: retains caller's alias.
    }

    int[] values() {
        return values;         // Bug: exposes internal array.
    }
}

// Caller can do:
int[] original = {10, 20};
UnsafeSnapshot unsafe = new UnsafeSnapshot(original);
original[0] = 999;         // Data inside unsafe also changes.
unsafe.values()[1] = 888;  // Getter creates a direct mutation path.
~~~

Two independent bugs:
1. **Input:** the constructor keeps the source reference; the caller still owns the array and can mutate it later.
2. **Output:** the getter returns the internal reference; code receiving the getter's result can mutate the object's state.

Correct pattern for a one-dimensional primitive array:

~~~java
this.values = Objects.requireNonNull(input, "input").clone();

// Getter of the class:
return values.clone();
~~~

Each clone call creates a new array. Because **int** elements are primitives, values are copied independently; there are no element references to mutable objects requiring further copying. **Arrays.copyOf** and **System.arraycopy** are also valid options when used with the right length/type, though they do not automatically deep-copy object elements.

The contract of **SensorSnapshot** is explicitly defined: **sensorId** is non-null and non-blank; **readings** is non-null but may be empty; measurement order is significant; all value-reading operations must see the same data from creation time; callers are free to mutate copies returned by getters.

## 3. Complete Java 17+ Program

Create a file named exactly **DefensiveCopyDemo.java**. The two nested classes **SensorSnapshot** and **MatrixSnapshot** demonstrate two levels of copying. The **check** helper throws **AssertionError** if a contract fails, independent of whether **-ea** is enabled.

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class DefensiveCopyDemo {
    static final class SensorSnapshot {
        private final String sensorId;
        private final int[] readings;

        SensorSnapshot(String sensorId, int[] readings) {
            this.sensorId = Objects.requireNonNull(sensorId, "sensorId");
            if (sensorId.isBlank()) {
                throw new IllegalArgumentException("sensorId must not be blank");
            }
            this.readings = Objects.requireNonNull(readings, "readings").clone();
        }

        String sensorId() {
            return sensorId;
        }

        int size() {
            return readings.length;
        }

        int readingAt(int index) {
            return readings[index];
        }

        int[] readings() {
            return readings.clone();
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof SensorSnapshot that)) {
                return false;
            }
            return sensorId.equals(that.sensorId)
                    && Arrays.equals(readings, that.readings);
        }

        @Override
        public int hashCode() {
            return 31 * sensorId.hashCode() + Arrays.hashCode(readings);
        }

        @Override
        public String toString() {
            return "SensorSnapshot{sensorId='" + sensorId
                    + "', readings=" + Arrays.toString(readings) + "}";
        }
    }

    static final class MatrixSnapshot {
        private final int[][] values;

        MatrixSnapshot(int[][] source) {
            values = copyRows(source);
        }

        private static int[][] copyRows(int[][] source) {
            Objects.requireNonNull(source, "source");
            int[][] result = new int[source.length][];
            for (int row = 0; row < source.length; row++) {
                result[row] = Objects.requireNonNull(
                        source[row], "source[" + row + "]").clone();
            }
            return result;
        }

        int get(int row, int column) {
            return values[row][column];
        }

        int[][] toArray() {
            return copyRows(values);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof MatrixSnapshot that)) {
                return false;
            }
            return Arrays.deepEquals(values, that.values);
        }

        @Override
        public int hashCode() {
            return Arrays.deepHashCode(values);
        }

        @Override
        public String toString() {
            return "MatrixSnapshot" + Arrays.deepToString(values);
        }
    }

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
        System.out.println("PASS: " + label);
    }

    public static void main(String[] args) {
        int[] input = {4, 8, 15};
        SensorSnapshot snapshot = new SensorSnapshot("S-1", input);

        input[0] = 999;
        check(snapshot.readingAt(0) == 4, "constructor copy");

        int[] getterResult = snapshot.readings();
        getterResult[1] = 888;
        check(snapshot.readingAt(1) == 8, "getter copy");

        SensorSnapshot same = new SensorSnapshot(
                "S-1", new int[] {4, 8, 15});
        check(snapshot.equals(same) && same.equals(snapshot),
                "value equality");
        check(snapshot.hashCode() == same.hashCode(),
                "equal objects share hashCode");

        Set<SensorSnapshot> set = new HashSet<>();
        set.add(snapshot);
        int[] anotherGetterResult = snapshot.readings();
        anotherGetterResult[2] = -1;
        check(set.contains(same) && set.contains(snapshot),
                "stable HashSet lookup");

        check(snapshot.toString().contains("[4, 8, 15]"),
                "content-based toString");

        int[][] source = {{1, 2}, {3, 4}};
        MatrixSnapshot matrix = new MatrixSnapshot(source);
        source[0][0] = 77;
        source[1] = new int[] {88, 99};
        check(matrix.get(0, 0) == 1 && matrix.get(1, 0) == 3,
                "deep constructor copy");

        int[][] exported = matrix.toArray();
        exported[0][1] = 77;
        exported[1] = new int[] {0};
        check(matrix.get(0, 1) == 2 && matrix.get(1, 0) == 3,
                "deep getter copy");

        MatrixSnapshot sameMatrix = new MatrixSnapshot(
                new int[][] {{1, 2}, {3, 4}});
        check(matrix.equals(sameMatrix)
                        && matrix.hashCode() == sameMatrix.hashCode(),
                "deep value equality and hashCode");

        System.out.println("All 9 checks passed.");
    }
}
~~~

Compile and run with Java 17 or higher:

~~~text
javac DefensiveCopyDemo.java
java DefensiveCopyDemo
~~~

Expected stdout:

~~~text
PASS: constructor copy
PASS: getter copy
PASS: value equality
PASS: equal objects share hashCode
PASS: stable HashSet lookup
PASS: content-based toString
PASS: deep constructor copy
PASS: deep getter copy
PASS: deep value equality and hashCode
All 9 checks passed.
~~~

### Why are the 9 checks meaningful?

- **constructor copy:** setting **input[0] = 999** only modifies data still held by the caller; the snapshot still holds measurement 4.
- **getter copy:** mutating **getterResult[1]** does not change the internal array; reading again yields 8. If the copy in the getter is removed, this check fails.
- **value equality:** two arrays with different references yet the same sequence **4, 8, 15** must produce equal snapshots when **sensorId** also matches. **Arrays.equals** compares elements, whereas **==** on arrays compares references.
- **equal objects share hashCode:** the Java contract requires that when **a.equals(b)** is true, **a.hashCode() == b.hashCode()**. The converse is not required: hash collisions are permitted.
- **stable HashSet lookup:** after adding the snapshot to a HashSet, mutating the input and getter-returned arrays must not change the fields contributing to equals/hashCode. If the hashCode of an object in a set changes, lookups can fail.
- **content-based toString:** **Arrays.toString(int[])** displays elements such as **[4, 8, 15]**; **readings.toString()** only prints an array identity descriptor like **[I@...**.
- **deep constructor copy:** mutating **source[0][0]** or replacing the entire row **source[1]** does not affect the stored matrix.
- **deep getter copy:** mutating a cell of the exported array or reassigning a row in the getter result also does not affect the internal matrix.
- **deep value equality and hashCode:** identical matrix data yields true for equals and matching hashCode thanks to **Arrays.deepEquals/deepHashCode**.

## 4. Why Distinguish Shallow Copy and Deep Copy?

**int[]** only holds primitive values, so **clone()** suffices to create an independent copy. However, **int[][]** is actually *an array of references to int[] arrays*. Cloning only the outer array preserves the references to the rows.

~~~java
int[][] original = {{1, 2}, {3, 4}};
int[][] shallow = original.clone();
shallow[0][0] = 99;
// original[0][0] is also 99: same reference to row 0.

int[][] copied = new int[original.length][];
for (int row = 0; row < original.length; row++) {
    copied[row] = original[row].clone();
}
copied[1][0] = 77;
// original[1][0] is still 3.
~~~

**MatrixSnapshot.copyRows** checks that the outer array and every row are non-null, allocates a new outer array, and clones each row. This example's contract accepts empty rows and *jagged arrays*, while rejecting **null** rows. Because each row holds primitives, this two-level depth isolates all mutable data involved.

With **MutablePoint[]**, things differ: cloning the array only copies references to each Point; the caller can still mutate **points[0].x**. You must capture each Point's data in an independent object and also copy when the getter returns; you can replace mutable Points with an immutable record/snapshot holding primitives. If Point itself contains an array or another mutable object, Point's copy constructor must handle those fields as well.

~~~java
// Illustration, not yet a standalone program:
// MutablePoint must declare a MutablePoint(MutablePoint) constructor.
static MutablePoint[] copyPoints(MutablePoint[] source) {
    Objects.requireNonNull(source, "source");
    MutablePoint[] result = new MutablePoint[source.length];
    for (int i = 0; i < source.length; i++) {
        result[i] = new MutablePoint(
                Objects.requireNonNull(source[i], "point"));
    }
    return result;
}
~~~

Do not call a method "deep copy" without knowing the mutability contract of each child object. Even **List.copyOf(...)** or **Collections.unmodifiableList(...)** does not automatically deep-copy elements that are mutable objects.

| Internal data | Appropriate copy | Risk if incomplete |
| --- | --- | --- |
| **int[]** | Clone once at each input/output boundary | Source or getter array aliasing |
| **String[]** | Clone the array, since String is immutable | Array aliasing if not cloned |
| **int[][]** | Clone outer array and each row | Inner row aliasing |
| **MutablePoint[]** | Clone array and create copies of each mutable Point | Alias to element objects |
| Record containing **int[]** | Copy array in constructor and accessor, customize equals/hashCode | Record component still holds a mutable array; default equality does not compare element values |

## 5. Object Contract: equals, hashCode, toString, and Immutability

The **equals** contract of **SensorSnapshot** uses **sensorId.equals** and **Arrays.equals(readings, that.readings)**. If the order of measurements changes, two snapshots are not equal; this is the declared business decision. If unordered set semantics were actually desired, you would change the model and contract rather than arbitrarily altering comparison code.

**hashCode** uses the exact same information as equals: **31 * sensorId.hashCode() + Arrays.hashCode(readings)**. Do not use **readings.hashCode()** because that hashes by array identity and can differ between two arrays with identical values. **MatrixSnapshot** uses the corresponding pair **Arrays.deepEquals** and **Arrays.deepHashCode**.

**toString** is only a human-readable and inspection representation, not a stable storage format. For 1D arrays use **Arrays.toString**, and for nested arrays use **Arrays.deepToString**. Do not automatically log sensitive data if real snapshots contain confidential information.

**Object.clone()** is not the default solution for creating immutable objects: cloning an array creates a new outer array, yet for reference arrays it still shares child objects. This practice uses constructors with explicit validation and copying so the contract is easy to read.

**final** on a class prevents subclasses from altering behavior in ways that break immutability assumptions. **final** on a field protects reference identity inside the class but does not freeze the referenced object. Every path by which mutable state could escape must be examined.

**record** does not solve this automatically: a record with an **int[]** component still accepts/returns a mutable array in its default accessor, and the auto-generated equality/hashCode for an array component does not switch to content comparison. To use a record, you must guard the constructor/accessor and override the comparison contract appropriately.

## 6. What Should Defensive Testing Actually Do?

When testing a class containing arrays, testing **assertEquals** on data right after the constructor is not enough. You must attack from both sides as well as nested elements:

1. Create a snapshot from a source array, **mutate the source after creation**, and verify the snapshot retains old values.
2. Call the getter, mutate the returned array, read the snapshot again, and verify data did not change.
3. Call the getter twice, verifying **first != second** when the contract specifies returning a fresh copy each time, while contents match.
4. Create two snapshots from two arrays **with different identities but equal contents**, testing bidirectional equals and matching hashCode.
5. Add the snapshot to a HashSet, mutate source/getter data, and verify it is still found using an equivalent snapshot.
6. For matrices, mutate **source[0][0]**, reassign **source[1]**, and perform the same actions on the array returned by the getter.
7. Test **null**, empty arrays, jagged arrays, null rows, and out-of-bounds indices per the chosen API rules.
8. If using mutable object elements, mutate *inside the element* rather than merely assigning a new element into the array.

You can add the following checks **inside main** of the section 3 program (they use the classes and variables already declared there):

~~~java
SensorSnapshot empty = new SensorSnapshot("S-0", new int[0]);
check(empty.size() == 0, "empty readings accepted");

int[] first = snapshot.readings();
int[] second = snapshot.readings();
check(first != second && Arrays.equals(first, second),
        "fresh getter array");

int[][] jagged = {{1}, {2, 3, 4}};
MatrixSnapshot jaggedCopy = new MatrixSnapshot(jagged);
jagged[1][0] = 100;
check(jaggedCopy.get(1, 0) == 2, "jagged rows copied");
~~~

This is a **non-standalone** extension; when adding these three **check** calls, the count printed at the end of the program must be updated from 9 to 12.

## 7. Designing APIs with Responsible Data Ownership

Copying long arrays incurs **O(n)** time and memory cost; copying matrices costs proportional to total element count. Not every API needs to return an entire copy on every read: you can provide **size()**, **readingAt(i)**, or an aggregate computation so callers avoid copying large arrays. If you genuinely must hand over array ownership without copying, publish an explicit ownership/transfer contract and accept that "immutable snapshot" in this lesson's sense no longer holds.

Also state the exact accepted data domain. This sample intentionally rejects **null/blank sensorId**, **null readings**, null matrices, or null rows; it permits empty **int[]** and jagged matrices. Other rules may make sense in other products, but they must be written into the contract and matching tests.

For multi-threaded data, defensive copying protects **ownership after copying finishes**; it does not make concurrently reading a source array being modified by another thread an atomic snapshot. The caller must ensure the source is stable during the copy or coordinate synchronization before handing it over.

## 8. Hands-On Exercises and Questions

**Exercise A — breaking boundaries:** temporarily remove clone from **SensorSnapshot**'s constructor and predict which check fails. Restore the constructor, then remove clone from the getter and explain why a different check fails. Finish with all 9 checks passing.

**Exercise B — shallow matrix:** replace **MatrixSnapshot.copyRows** with **return source.clone()** (after null validation). Try mutating **source[0][0]** and reassigning **source[1]**. How do the two actions affect the snapshot differently? Restore per-row cloning.

**Exercise C — adding a field to the value object:** add **String batchId**. Update constructor, equals, hashCode, and toString consistently; prove different batchIds are unequal even when arrays match.

**Exercise D — mutable element objects:** write **MutablePoint**, create **PointSnapshot** taking **MutablePoint[]**, and deliberately mutate a Point in the source and in the getter. Prove you must copy each Point and account for mutable fields inside Point.

Self-check questions:
1. Why does **private final int[] readings** not guarantee immutable data?
2. If you clone only in the constructor or only in the getter, what aliasing path remains?
3. How does **Arrays.equals** differ from **==** on arrays?
4. Why must **hashCode** also hash by content when **equals** compares content?
5. Why does **int[][]** require per-row copying while **int[]** needs only a single clone?
6. Why does a **MutablePoint[]** array require an extra decision about copying elements?
7. Which checks protect storing a value object in a **HashSet**?
8. Does defensive copying automatically solve another thread mutating the source mid-copy?

**Key takeaway:** A class containing arrays has a safe snapshot contract only when the class **owns copied data**, exposes no mutable aliases, copies deeply enough for nested structures, and keeps **equals/hashCode/toString** aligned with observable content. Tests must actively mutate both source and getter results and verify the snapshot remains unchanged.