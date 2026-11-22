# The `equals` Contract: Consistency When Comparison Data Does Not Change

## 1. What Does Consistency Mean?

In Java, the **Object.equals(Object)** method has a requirement for *consistency*:

> For any two non-null object references x and y, multiple invocations of x.equals(y) must consistently return true or consistently return false, **provided no information used in equals comparisons on the objects is modified**.

This is a conditional requirement, not a promise that the result of equals can never change over an object's lifetime. If the state actually used for comparison changes, a different result on a subsequent call can be completely valid.

Consider two objects both representing a book code and a revision number:

- Call 1: x.equals(y) returns true.
- Do not modify the book code, revision, or any comparison information on x or y.
- Call 2, call 3, ...: x.equals(y) must still return true.

If x.equals(y) was initially false and all comparison information remains unchanged, subsequent calls must also return false. There is no rule that the result must be true; the requirement is **stability given the same comparison data**.

Consistency is one of the conditions of the equals contract, alongside reflexivity, symmetry, transitivity, and x.equals(null) always returning false. This lesson focuses on the consistency condition.

## 2. What Does "Information Used in Comparisons" Include?

Suppose equals uses the code and revision fields:

~~~java
return revision == other.revision
        && Objects.equals(code, other.code);
~~~

When code and revision on **both objects** do not change, the comparison result must remain the same. When either of those fields changes, the condition "no comparison information is modified" no longer holds.

Note these distinctions:

| Scenario | Modifies information used by equals? | Is equals result allowed to change? |
| --- | --- | --- |
| Calling x.equals(y) multiple times with all comparison data unchanged | No | No; must be consistent |
| Modifying a field that equals compares in x or y | Yes | May change |
| Modifying a description/notes field not used by equals at all | No | Must not change solely due to that field |
| Object keeps the same reference to a List, but a List element used in equals is modified | Yes | May change |
| No data modified, yet equals uses time, randomness, or an incrementing counter to return different results | Result depends on unstable factors | Design violates consistency expectations |

The phrase "not modified" pertains to the **values/information being compared**, not merely whether reference variables x and y still point to the same two objects. A mutable object can keep the same address while its internal data has changed. Conversely, modifying a field completely unrelated to equals is not a valid reason for the equals result to differ.

For nested object fields, you must consider the state used by that field's equals method. For example, if equals compares a List using List.equals, modifying an element can change the result even though the List reference itself remains the same.

## 3. Runnable Java 17+ Example: Stable Data vs. Modified Data

Create the file **EqualsConsistencyDemo.java**:

~~~java
import java.util.Objects;

public class EqualsConsistencyDemo {
    public static void main(String[] args) {
        BookCode fixedA = new BookCode("JAVA", 17);
        BookCode fixedB = new BookCode("JAVA", 17);

        System.out.println("fixed #1: " + fixedA.equals(fixedB));
        System.out.println("fixed #2: " + fixedA.equals(fixedB));

        MutableLabel left = new MutableLabel("ready");
        MutableLabel right = new MutableLabel("ready");

        System.out.println("before edit: " + left.equals(right));
        right.setText("busy");
        System.out.println("after edit: " + left.equals(right));
        right.setText("ready");
        System.out.println("after restore: " + left.equals(right));
    }

    static final class BookCode {
        private final String code;
        private final int revision;

        BookCode(String code, int revision) {
            this.code = Objects.requireNonNull(code);
            this.revision = revision;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof BookCode that)) {
                return false;
            }
            return revision == that.revision
                    && code.equals(that.code);
        }

        @Override
        public int hashCode() {
            return Objects.hash(code, revision);
        }
    }

    static final class MutableLabel {
        private String text;

        MutableLabel(String text) {
            this.text = text;
        }

        void setText(String text) {
            this.text = text;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof MutableLabel that)) {
                return false;
            }
            return Objects.equals(text, that.text);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(text);
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac EqualsConsistencyDemo.java
java EqualsConsistencyDemo
~~~

Expected output:

~~~text
fixed #1: true
fixed #2: true
before edit: true
after edit: false
after restore: true
~~~

**Explanation:**

1. BookCode has final fields and an immutable String object; after initialization, code and revision are not modified. Repeated comparisons of the same pair fixedA, fixedB always return true.
2. Before editing, left and right both have text = "ready", so equals returns true.
3. After right.setText("busy"), right's comparison data changes. Returning false **does not violate** consistency.
4. After restoring "ready", the data matches again, so returning true is also valid.
5. Both classes override hashCode compatibly with the fields used in equals. This satisfies another important condition when objects are used in hash structures.

Do not interpret this example as saying mutable is always wrong or final automatically makes equals correct. A mutable class can still uphold the consistency contract: each check must rely on the current data and never alter its result on its own while comparison data stands still. Using final makes keeping comparison state stable easier, but the quality of the equals implementation still needs verification.

## 4. Faulty Example: Result Changes Without Modifying Object Data

The following snippet **only illustrates an incorrect implementation**, not a standalone program; the method also violates other equals conditions in certain scenarios:

~~~java
final class BadKey {
    private static boolean flip;

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof BadKey)) {
            return false;
        }
        flip = !flip;
        return flip;
    }
}
~~~

With two BadKey objects having different references, consecutive comparisons can alternate between true and false even without changing any information representing the two objects. The flip variable is state used to make the result oscillate, not a value property of the compared objects. This is an unsuitable design for equals.

Error patterns of the same nature:

- Reading random values, the system clock, or frequently changing external data to decide equality when the object's intrinsic value has not changed.
- Incrementing counters, toggling flags, or mutating comparison fields inside equals, causing an earlier check to alter the result of the next check.
- Comparing fields computed with unstable logic or depending on uncontrolled global state.
- Calling getters with side effects that mutate comparison data; the name getter does not guarantee it is read-only.

Conversely, computing a derived value in a **pure and deterministic** way from stable fields, and using that value in equals, can still be consistent. For example, normalizing a code with a fixed rule remains stable if the input data and rule do not change.

## 5. Why Consistency Matters When Using hashCode and HashSet/HashMap

Two related but distinct contracts:

- **equals:** If information used in comparisons is not modified, repeating the comparison on the same objects must yield the same result.
- **hashCode:** During a single Java execution, if information used in equals is not modified, calling hashCode multiple times on the same object must return the same integer. Two objects equal according to equals **must** have the same hashCode; two unequal objects may still collide on hashCode.

In the BookCode example, equals examines code and revision, so hashCode is also based on those two fields. If you only override equals and omit hashCode, hash-based collections like HashSet and HashMap can fail the expectation that "two equal keys are one key".

Even when equals and hashCode are written properly, **mutating a field used in equals/hashCode on an object already acting as a HashMap key or added to a HashSet** can break retrieval because its stored bucket/hash value no longer matches. This is an issue with using mutable keys, not that every change in equals result after mutation violates consistency.

Practical rule: prefer immutable keys; if you must modify an identifying property of an entry already inside a hash collection, typically remove the entry using the old key/state first, modify it, and then re-insert it. Do not expect the collection to relocate an element automatically after its key state changes.

## 6. Common Misconceptions

**Misconception 1: "If equals once returned true, it must return true forever."**

False. The premise of the contract is that the information used for comparison has not been modified. If y changes from "ready" to "busy", a later comparison may return false.

**Misconception 2: "Variables x and y were not reassigned, so the data did not change."**

False. The variables still reference the same objects, yet mutable fields, array elements, List elements, or sub-objects used in equals may have changed.

**Misconception 3: "Modifying an uncompared field allows equals to change."**

False. If equals truly depends only on code and revision, modifying description must not change the result. If the result changes, inspect whether the implementation accidentally depends on description, external state, or a getter with side effects.

**Misconception 4: "Making reference fields final is enough."**

False. final prevents reassigning the field reference to another object, but if the field points to a mutable object (such as an ArrayList), that object's contents can still change. To keep comparison data immutable, you must account for any relevant sub-objects as well.

**Misconception 5: "A consistent equals is automatically thread-safe under concurrent access."**

False. The equals contract does not replace synchronization mechanisms. If one thread mutates comparison data while another thread calls equals, reads may observe mutated/unsynchronized state. Use immutable data or appropriate synchronization when concurrent access is required.

**Misconception 6: "Only equals needs to be right; hashCode does not matter."**

False for objects used as hash keys. When overriding equals, you must override a compatible hashCode. Doing so does not automatically solve mutable-key issues after insertion into HashSet/HashMap.

## 7. How to Verify That an equals Method Is Consistent

When reviewing or writing tests, answer in order:

1. Which fields and derived values on **both** objects does the method use to decide equality?
2. Do repeated calls with the same values across all of that data produce the same result? Test both equal (true) and unequal (false) pairs.
3. Is there any unnecessary dependency on time, randomness, global data, call order, or operations with side effects?
4. If the objects are mutable, when modifying **only** relevant fields, is the new result explained by the data change? When modifying only unrelated fields, does the result stay unchanged?
5. If the class is used as a HashMap/HashSet key, are the fields participating in equals kept stable while the key is in the collection, and does hashCode use the corresponding information?

A quick check for objects not modified during the test interval:

~~~java
boolean first = x.equals(y);
boolean second = x.equals(y);
if (first != second) {
    throw new AssertionError("equals is inconsistent when comparison data remains unchanged");
}
~~~

This is an illustrative snippet placed in a context where x and y already exist; it does not prove the entire equals contract, and is meaningful only when comparison data truly does not change between the two calls. Good testing should repeat across multiple state pairs while also checking reflexivity, symmetry, transitivity, null handling, and the equals/hashCode relationship.

## 8. Key Takeaways

**Exact condition:** *Same two objects + no change to information used by equals → repeated equals results must stay the same.*

Changing comparison data can legitimately change the result. What must be avoided is letting equals return erratic results while value data remains intact. Prefer deterministic, side-effect-free comparisons; for keys in hash structures, keep identifying properties stable for the entire time the key is stored.