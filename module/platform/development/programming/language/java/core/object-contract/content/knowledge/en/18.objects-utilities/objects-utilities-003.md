# `Objects.hashCode()` for a single object

## 1. Objective: computing a null-safe hashCode for exactly one object

In Java, the **hashCode()** method belongs to **java.lang.Object**. It returns an **int** integer, commonly used alongside **equals(Object)** in **HashMap**, **HashSet**, **LinkedHashMap**, and other hash-based data structures. The syntax **value.hashCode()** has a common issue: if **value == null**, the program throws **NullPointerException**.

The utility class **java.util.Objects** provides a static method:

~~~java
public static int hashCode(Object o)
~~~

Its semantics are equivalent to:

~~~java
return o == null ? 0 : o.hashCode();
~~~

These two snippets describe the API signature and logic, not a standalone Java program. If **null** is passed, the result is **0**; if a non-**null** object is passed, Java invokes that object's own **hashCode()** method via dynamic dispatch. It **does not invent a new hash algorithm**, does not automatically combine multiple fields, does not verify the equals contract, and does not turn a mutable type into an immutable one.

Quick example:

~~~java
Objects.hashCode(null)   // 0
Objects.hashCode("A")    // 65
"A".hashCode()           // 65
~~~

These are illustrative expressions and require importing **java.util.Objects** when placed in real code. The hash of String **"A"** is 65 according to the String.hashCode algorithm; however, **not every object has a hash that is stable and predictable** in this way.

**Remember immediately:** **Objects.hashCode(x)** means "if x has a value, use x.hashCode(); if null, use 0".

## 2. Runnable Java 17 example: null, String, and equivalent objects

Create the file **SingleObjectHashDemo.java**:

~~~java
import java.util.Objects;

public class SingleObjectHashDemo {
    public static void main(String[] args) {
        Object missing = null;
        String first = new String("A");
        String second = new String("A");

        System.out.println("null hash: " + Objects.hashCode(missing));
        System.out.println("first hash: " + Objects.hashCode(first));
        System.out.println("direct hash: " + first.hashCode());
        System.out.println("same value: " + first.equals(second));
        System.out.println("same hash: " +
            (Objects.hashCode(first) == Objects.hashCode(second)));

        System.out.println("one-field Objects.hash: " +
            Objects.hash(first));
        System.out.println("single-null Objects.hash: " +
            Objects.hash((Object) null));
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac SingleObjectHashDemo.java
java SingleObjectHashDemo
~~~

Output:

~~~text
null hash: 0
first hash: 65
direct hash: 65
same value: true
same hash: true
one-field Objects.hash: 96
single-null Objects.hash: 31
~~~

**Line-by-line explanation of key points:**

1. **Objects.hashCode(missing)** does not throw an exception and returns **0**.
2. **Objects.hashCode(first)** directly uses **String.hashCode()**, so it equals **first.hashCode()**.
3. The two separately created String instances have **equals** true because they have the same character sequence. Because String obeys the equals/hashCode contract, the two hashes are equal.
4. **Objects.hash(first)** returns **96**, not **65**, because this is a **different** API: it hashes a **varargs parameter array**, even when there is only one argument.
5. **Objects.hash((Object) null)** returns **31** because this is **one null element** inside a parameter array of length one. Casting **(Object)** makes the intent to pass **a single null object** explicit, avoiding ambiguity with passing a null **Object[]** array.

Do not use these example results to conclude that hashCode is a unique ID or a security signature: many different objects can share the same 32-bit hash.

## 3. Distinguishing Objects.hashCode(Object) from Objects.hash(Object...)

The two method names differ only slightly, yet their mechanisms are very different:

| Criterion | **Objects.hashCode(Object)** | **Objects.hash(Object...)** |
| --- | --- | --- |
| Number of objects semantically | **One** object, possibly null | **Multiple** values passed as varargs |
| Mechanism | **o == null ? 0 : o.hashCode()** | Based on **Arrays.hashCode(Object[])** of the arguments |
| A single String **"A"** | **65** | **96** because 31 × 1 + 65 |
| One null argument cast to Object | **0** | **31** |
| No arguments passed | No zero-argument overload | **Objects.hash()** returns **1** |
| Where to use | Null-safe delegate to a single value's hashCode | Convenient for combining hashes of multiple fields |

To understand the result 96:

~~~text
Objects.hash("A")
    = Arrays.hashCode(new Object[]{"A"})
    = 31 * 1 + "A".hashCode()
    = 31 + 65
    = 96
~~~

This does **not** mean **Objects.hash** computes wrongly. It is designed to combine the arguments of **a tuple of values**, for example a class with **name**, **age**, and **department**. Meanwhile, **Objects.hashCode** is for handling the hashCode **of a single object** in a null-safe manner.

### Two easily confused null cases

~~~java
Objects.hashCode((Object) null)    // 0
Objects.hash((Object) null)        // 31
Objects.hash((Object[]) null)      // 0
~~~

These are illustrative expressions. With **Objects.hash((Object[]) null)**, the varargs parameter is a **null array**, and **Arrays.hashCode((Object[]) null)** returns 0. With **Objects.hash((Object) null)**, the varargs parameter is an **array with one null element**, so the result is 31.

When calling **Objects.hash(null)** directly, Java may choose a varargs interpretation that causes a compiler warning or behavior that misleads readers; explicitly write the **(Object)** or **(Object[])** cast depending on intent.

### Choosing the right one

- To replace **obj.hashCode()** while avoiding NullPointerException: use **Objects.hashCode(obj)**.
- To combine hashes of **multiple value components**: use **Objects.hash(field1, field2, ...)** or a carefully hand-written 31-multiplier formula.
- To hash array contents: use **Arrays.hashCode** or **Arrays.deepHashCode** matching the array comparison; do not blindly substitute either of the two APIs above.

## 4. Role of equals: hashCode does not determine whether two objects are equal

The general contract of **Object** requires:

1. If **a.equals(b)** is **true**, then **a.hashCode() == b.hashCode()** must hold, provided the data used for comparison does not change.
2. If **a.equals(b)** is **false**, the two hashes are **allowed** to be equal: hash collisions are normal.
3. As long as the information used in equals has not changed, calling hashCode multiple times on the same object must return consistent results within a single application execution according to the Java contract.
4. There is no requirement for an object's hashCode to remain the same across different **JVM launches**.

Because **Objects.hashCode(x)** simply calls **x.hashCode()** for non-null x, the rules above apply intact. If a class implements **equals** itself and forgets to override the corresponding **hashCode**, wrapping with **Objects.hashCode** **does not fix the bug**.

### Do not use hashCode as an equality check

Wrong:

~~~java
// Illustrative expression only, not a standalone file:
boolean same = Objects.hashCode(a) == Objects.hashCode(b);
~~~

Two different objects can have the same hash code. To perform a null-safe comparison between **two objects**, use **Objects.equals(a, b)**; to build value-keyed maps/sets, implement equals/hashCode properly on the key class.

~~~java
boolean same = Objects.equals(a, b);
~~~

In a real program, **a** and **b** must be declared variables. If both are null, **Objects.equals(a, b)** returns true. If only one side is null, it returns false. If both are non-null, it calls equals on the first object. This is a **different** task from Objects.hashCode.

**Note:** **Objects.hashCode(null) == 0** does not mean hash 0 is reserved exclusively for null. Many valid objects can return hash 0; to check for null, you must use **obj == null**.

## 5. Example: implementing equals/hashCode for nullable fields

Suppose a **CustomerKey** key consists of **tenantId** and **customerCode**; both are Strings, and in this illustrative example we allow null. Two keys are equal when each corresponding field is equal, including when both fields are null.

Create the file **NullableCustomerKeyDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class NullableCustomerKeyDemo {
    static final class CustomerKey {
        private final String tenantId;
        private final String customerCode;

        CustomerKey(String tenantId, String customerCode) {
            this.tenantId = tenantId;
            this.customerCode = customerCode;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof CustomerKey other)) {
                return false;
            }
            return Objects.equals(tenantId, other.tenantId)
                && Objects.equals(customerCode, other.customerCode);
        }

        @Override
        public int hashCode() {
            int result = Objects.hashCode(tenantId);
            result = 31 * result + Objects.hashCode(customerCode);
            return result;
        }
    }

    public static void main(String[] args) {
        CustomerKey first = new CustomerKey(null, "A");
        CustomerKey second = new CustomerKey(null, new String("A"));
        CustomerKey different = new CustomerKey("X", "A");

        System.out.println("first equals second: " +
            first.equals(second));
        System.out.println("hash equal: " +
            (first.hashCode() == second.hashCode()));
        System.out.println("first hash: " + first.hashCode());
        System.out.println("first equals different: " +
            first.equals(different));

        Set<CustomerKey> keys = new HashSet<>();
        keys.add(first);
        keys.add(second);
        keys.add(different);
        System.out.println("unique keys: " + keys.size());
    }
}
~~~

Run:

~~~bash
javac NullableCustomerKeyDemo.java
java NullableCustomerKeyDemo
~~~

Output:

~~~text
first equals second: true
hash equal: true
first hash: 65
first equals different: false
unique keys: 2
~~~

**Analysis:**

- **Objects.equals** handles null for both fields in equals.
- **Objects.hashCode(tenantId)** of the first key is **0**, because tenantId is null.
- **Objects.hashCode(customerCode)** is **65** for String **"A"**, so the hand-written hash function for that key produces **31 × 0 + 65 = 65**.
- Two String "A" instances with different references still produce the same hash because String's equals is content-based.
- The key with a different tenantId does not equal the first key; HashSet retains two logical keys.

This is only **one valid hash-combining formula**. The Java contract does not force every class to use multiplier 31. The formula can differ and still be correct as long as all equal object pairs produce identical hashes. **Objects.hash(tenantId, customerCode)** is also a concise option, as it hashes multiple components consistently when those components have hashCodes compatible with equals.

**Domain decision:** A real system typically does not want null in identifiers; in that case, use **Objects.requireNonNull** in the constructor to reject invalid input. Allowing null here is meant to clearly illustrate the mechanism of **Objects.hashCode(Object)**, not to recommend using null as a customer key.

## 6. When a field already has hashCode or an object is wrapped in a record

### A nullable field inside a larger calculation

For a class with one nullable object field and one primitive field:

~~~java
// Snippet inside hashCode() of a class with fields name, version:
int result = Objects.hashCode(name);
result = 31 * result + Integer.hashCode(version);
return result;
~~~

**Integer.hashCode(int)** is suitable for primitive int without boxing. Do not write **Objects.hashCode(version)** when only hashing an int: that call requires boxing to Integer; the result may be equivalent, but that overhead/complexity is unnecessary.

For **long**, **boolean**, **double**, and other primitives, use **Long.hashCode**, **Boolean.hashCode**, **Double.hashCode**, etc. when hashing a primitive value directly. For an object such as String, enum, LocalDate, another record, or a nullable object, Objects.hashCode is very useful.

### Records usually do not need to override hashCode

~~~java
record TicketKey(String eventId, int seatNumber) {}
~~~

Records automatically generate equals/hashCode from their components. If value semantics are **same eventId and seatNumber**, keeping the generated methods is appropriate. **Objects.hashCode(ticket)** will delegate to the record-generated hashCode.

Do not override equals using one subset of components and forget to change hashCode; if you want to group by eventId while ignoring seatNumber, a **separate key record** with only eventId is usually clearer.

### When a nullable value references another object

When a field is a record or custom class with proper equals/hashCode, **Objects.hashCode(field)** delegates hashing to that class. If the field is null, it returns 0. It does not inspect nested fields inside the object on its own; the hash number depends entirely on the actual **hashCode** of the field's class.

## 7. Pitfall: `Objects.hashCode(array)` does not hash array contents

Java arrays are objects, but they do not override `equals()`/`hashCode()` to use element contents. Therefore, `Objects.hashCode(array)` delegates to the identity-based hash of **the array itself**. If a class compares array fields using `Arrays.equals` or `Arrays.deepEquals`, the class's `hashCode()` method must also be content-based using `Arrays.hashCode` or `Arrays.deepHashCode` accordingly.

```java
int[] a = {1, 2};
int[] b = {1, 2};
System.out.println(java.util.Arrays.equals(a, b)); // true
System.out.println(java.util.Arrays.hashCode(a)
        == java.util.Arrays.hashCode(b));            // true
```

The calls above are illustrative inside a method. Two arrays with different references can have different identity hashes, so do not replace `Arrays.hashCode(a)` with `Objects.hashCode(a)` when equality examines contents. If a class wrapping an array is used as a `HashMap` key, make defensive copies whenever the data can change. The lesson **Objects.deepEquals() differs from Objects.equals() on array arguments** presents the equality/hash pair for nested arrays, while the lesson **Objects.hash() for multiple values and passing arrays** specifically explains `Object[]` and `int[]` varargs.

## 8. Bugs with hashCode of mutable objects as Map or Set keys

**Objects.hashCode(obj)** calls obj's current method, so if hashCode depends on mutable fields, the hash number can change. HashMap typically picks a bucket by hash upon insertion; after a key is mutated, looking up the key may fail to find the stored entry.

Example scenario:

~~~java
// Illustration: class MutableKey has equals/hashCode based on a modifiable id.
MutableKey key = new MutableKey("A");
map.put(key, "value");

key.setId("B");

// map.get(key) may fail to find the inserted entry.
// Objects.hashCode(key) does not fix this problem.
~~~

This is a **non-standalone illustrative** snippet, not a runnable program; it requires a MutableKey class and a map variable. What needs to be avoided is not just NullPointerException: **the values used in equals and hashCode must remain stable while the object serves as a key**.

Safe options:

- Use **String**, **Integer**, **UUID**, **Instant**, or a record containing only immutable components as keys when appropriate for the domain.
- Use a key class with final fields and genuinely immutable components; if it holds mutable arrays/collections, apply appropriate defensive copying.
- If changing an identifier is required by business logic, **remove the old entry and reinsert with the new key**, or rebuild the map under the new rules.
- Do not store a precomputed hashCode and assume it replaces the key value or can act as an ID.

**Distinguish stability from uniqueness:** A stable hash function can still collide. Hash structures must use **equals** after checking the hash to distinguish keys that share the same hash.

## 9. Comparing Object.hashCode, Objects.hashCode, Objects.hash, and System.identityHashCode

| API | Input accepted | Meaning |
| --- | --- | --- |
| **obj.hashCode()** | A non-null obj | Calls dynamic hashCode of the object itself; null causes NullPointerException |
| **Objects.hashCode(obj)** | An object or null | Null-safe delegate: null → 0, otherwise → obj.hashCode() |
| **Objects.hash(a, b, ...)** | Multiple varargs values | Combines argument hashes via Arrays.hashCode(Object[]) |
| **System.identityHashCode(obj)** | Object, possibly null | Identity-based hash, ignoring overridden hashCode; null → 0 |

**System.identityHashCode** is sometimes useful for mechanisms requiring object identity semantics, such as reference diagnostics or identity-based implementations. However, it is **not** a substitute for Objects.hashCode when a class's equals compares by value. Using an identity hash in a class with value-based equals can cause equal instances to have different hashes.

**Note:** The numeric value of **System.identityHashCode** is not a guaranteed memory address, nor is it guaranteed to be unique across all objects.

## 10. Small but sufficient tests to distinguish the APIs

Several scenarios should be included in tests for a custom class's hashCode method:

1. **Null field:** Objects.hashCode(null) is 0; the key's hashCode method does not throw NullPointerException when null is an allowed input.
2. **Two value-equal objects that are distinct instances:** if equals is true, hashCode must be equal; test two separately created Strings, two records with the same components, or two array wrappers with the same contents.
3. **Collisions:** do not conclude equality from hash alone; HashSet/HashMap must distinguish different keys even when they share a hash.
4. **Mutable fields:** test modifying data after acting as a key; if the class promises immutability, hashCode and equals must remain unchanged.
5. **Right API for the structure:** single object → Objects.hashCode; multiple fields → Objects.hash or compatible formula; array contents → Arrays.hashCode/deepHashCode.
6. **Do not treat hash magnitude as strength:** negative, positive, or 0 hash codes are all valid results; do not manually take absolute values because **Math.abs(Integer.MIN_VALUE)** is still negative.
7. **Do not require distinct hashes for every distinct object:** this is not a condition of the Object contract.
8. **Cross-check equals and hashCode:** if modifying equals to change the set of fields determining value, review hashCode at the same time.

### Checking with a simple program

Create the file **HashContractCheckDemo.java**:

~~~java
import java.util.Objects;

public class HashContractCheckDemo {
    record Code(String value) {}

    public static void main(String[] args) {
        Code a = new Code("A");
        Code b = new Code(new String("A"));
        Code c = new Code("B");

        System.out.println("a equals b: " + a.equals(b));
        System.out.println("equal keys hash equal: " +
            (Objects.hashCode(a) == Objects.hashCode(b)));
        System.out.println("a equals c: " + a.equals(c));

        Object missing = null;
        System.out.println("missing hash: " + Objects.hashCode(missing));
    }
}
~~~

Run:

~~~bash
javac HashContractCheckDemo.java
java HashContractCheckDemo
~~~

Output:

~~~text
a equals b: true
equal keys hash equal: true
a equals c: false
missing hash: 0
~~~

The two **Code** instances are equal because the record compares the String component by equals. **Objects.hashCode(a)** uses Code's hashCode; therefore it obeys the record's value contract. The case where c differs from a illustrates equals false, yet we **do not require** the hashes of a and c to be different.

## 11. Frequently asked questions

**Can every call to obj.hashCode() be replaced with Objects.hashCode(obj)?**

In contexts where returning 0 when obj is null is desired, that is usually true. However, if **null is a programming bug or invalid input**, silently permitting null can mask a violation of the application's contract. In that case, **Objects.requireNonNull(obj)** beforehand may be more appropriate.

**Does Objects.hashCode(x) automatically call equals(x)?**

No. It only checks for null and calls **x.hashCode()**. The contract between equals and hashCode must be guaranteed by type x.

**Why does Objects.hash(x) differ from Objects.hashCode(x)?**

Because Objects.hash computes a hash **for a tuple of arguments** using the Arrays.hashCode(Object[]) rule. With a single non-null argument, the result is typically **31 + x.hashCode()**, which differs from x's direct hash.

**Can hashCode be 0 for a non-null object?**

Yes. For example, an object with an overridden hashCode returning 0 is completely possible; this does not by itself make equals right or wrong. Therefore **Objects.hashCode(x) == 0** does not prove x is null.

**Should hashCode be saved into a database or sent as a unique identifier?**

Java's hashCode should not be treated as a global identifier key, security signature, or cryptographic hash. It is an integer serving hash structures, can collide, and is not guaranteed by the Object contract to remain stable across JVMs. For identifiers, use business keys, UUIDs, or explicit IDs; for integrity/security, dedicated algorithms are required as needed.

**When is Objects.hashCode not needed?**

If you already have primitive int/long and corresponding APIs, use **Integer.hashCode**, **Long.hashCode**, or direct combination. If a record already generates a valid hashCode, call **record.hashCode()** when guaranteed non-null. If you need to hash an array by content, use **Arrays.hashCode** instead of Objects.hashCode.

## 12. Step-by-step application workflow

When you see a **hashCode()** call with a risk of NullPointerException, determine first:

1. Is the value to hash **a single object** or **a tuple of multiple fields**?
2. Can the object validly be null? If yes, **Objects.hashCode(Object)** returns 0. If not, **requireNonNull** can be used to fail fast.
3. **Which properties** does the object type's equals examine? That type's hashCode must be compatible with equals.
4. If the object is an **array**, does content comparison via Arrays.equals/deepEquals apply? If so, use the corresponding content hash.
5. If the object is a key for HashMap/HashSet, are the components affecting equals/hashCode immutable while stored?
6. Finally, verify with null cases, value-equal independent instances, collisions, and state changes.

**Key takeaway:** **Objects.hashCode(x)** is simply a **null-safe** way to obtain **the hashCode of a single object**. It is not the same as **Objects.hash(x)**, does not automatically compute array content hashes, does not guarantee hash uniqueness, and cannot fix a class with broken equals/hashCode. The API's real value lies in consistently using **type x's hashCode** in code that handles potentially null objects.

Reference: [Java SE 17 – java.util.Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html).