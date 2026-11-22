# String in Collections: The equals–hashCode Contract and Hash Collisions

When using **String** as an element of **HashSet** or as a key of **HashMap**, Java needs to know whether two strings are considered **the same value**. The two methods **equals(Object)** and **hashCode()** work together to answer that question. Understanding their contract properly helps prevent lost keys, incorrect element counts, and misunderstandings about **hash collisions**.

One principle to remember from the start: **having the same hashCode does not mean two Strings are equal; however, two Strings that are equal according to equals must have the same hashCode.**

## 1. String.equals Compares Content, Not Memory Addresses

String overrides the **equals(Object)** method to compare **character content**. Two different String objects are still considered equal if they contain the exact same sequence of UTF-16 code units in the same order.

~~~java
String a = new String("java");
String b = "java";

System.out.println(a == b);      // false
System.out.println(a.equals(b));  // true
~~~

Explanation:

- **a == b** checks whether two references point to the **same object**; an object explicitly created with **new String(...)** is distinct from a string literal object.
- **a.equals(b)** compares content, so it returns **true**.
- String content comparison is **case-sensitive**: **"Java".equals("java")** is **false**.
- **"java".equals(null)** is **false**. If a reference might be null, **Objects.equals(a, b)** can be used to compare two possibly null values safely.

Having the same content does not necessarily mean sharing the same reference. The *string pool* mechanism or **intern()** does not change the content-comparison rules of equals; do not use **==** to decide whether two strings represent the same key in an application.

## 2. What Is the equals–hashCode Contract?

Every Java class that can be used as a key in a hash-based collection must adhere to two sets of rules.

### 2.1. Basic Rules of equals

For non-null objects when relevant state does not change:

1. **Reflexive:** **x.equals(x)** is true.
2. **Symmetric:** **x.equals(y)** and **y.equals(x)** must return the same result.
3. **Transitive:** if x equals y and y equals z, then x must also equal z.
4. **Consistent:** as long as data used for comparison does not change, repeated calls to equals must return the same result.
5. **With null:** **x.equals(null)** must be false.

String already implements these rules. You never need to rewrite equals for String.

### 2.2. Rules of hashCode

The **hashCode()** contract includes:

- Within the same execution of an application, if the data participating in equals does not change, calls to **hashCode()** on the same object must return the same integer.
- **If x.equals(y) is true, then x.hashCode() and y.hashCode() must be equal.**
- **If x.equals(y) is false, their hashCodes are allowed to be equal.** Two unequal values are **not required** to produce different hash codes.

The implication direction can be expressed precisely:

~~~text
x.equals(y) == true   ⇒   x.hashCode() == y.hashCode()

x.hashCode() == y.hashCode()   ⇏   x.equals(y) == true
~~~

The second statement is why a hash-based collection must use **equals** to distinguish objects that share the same hash code. If it only checked the hash number, valid data would be mistakenly treated as duplicates.

## 3. How Does String.hashCode Work?

**String.hashCode()** computes an **int** value from the String's content. Semantically, the formula has the form:

~~~text
h = 0
Iterate over each UTF-16 code unit c of the string:
    h = 31 * h + c
The result is h as a 32-bit Java int.
~~~

For an empty string, hashCode is **0**. For Strings with equal content, computing over the same sequence of UTF-16 code units always yields the same hashCode. The number **31** is the multiplier in the hashCode algorithm defined by Java for String.

Example:

~~~text
"Aa" = 31 × code('A') + code('a')
     = 31 × 65 + 97
     = 2112

"BB" = 31 × code('B') + code('B')
     = 31 × 66 + 66
     = 2112
~~~

Because hashCode is only a **32-bit int** while the number of possible strings is infinite, there inevitably exist distinct strings that produce the same hash code. hashCode can also be negative due to 32-bit integer overflow; this is not a bug.

**hashCode is not a unique identifier, not a secure fingerprint, and not a cryptographic hash function.** Do not use it to verify that data has not been tampered with, generate unique IDs, or check security-sensitive integrity.

## 4. From Hash Code to Actual Lookup

`HashSet<String>` and `HashMap<String, V>` use **both the hash code and equivalence comparison**. The hash code locates a candidate group; `equals` confirms the exact key. Because the table has a finite number of buckets, even **two different hashCodes** can land in the same bucket; that is an implementation detail handled internally by the collection. When two keys share the same hash but differ by `equals`, both values must still be distinguished.

~~~java
Map<String, Integer> map = new HashMap<>();
map.put("Aa", 10);
map.put("BB", 20); // "Aa" and "BB" have the same hashCode
System.out.println(map.size());      // 2
System.out.println(map.get("Aa"));   // 10
System.out.println(map.get("BB"));   // 20

Set<String> set = new HashSet<>();
System.out.println(set.add("Aa"));   // true
System.out.println(set.add("BB"));   // true
System.out.println(set.add(new String("Aa"))); // false
System.out.println(set.size());      // 2
~~~

`map.put(new String("Aa"), 30)` (if called next) updates the `"Aa"` entry because `equals` is true, without changing the `"BB"` entry. Application code does not need to call `hashCode` or traverse buckets manually; `Map`/`Set` specify these semantics. The complete example in section 6 tests both duplicate content and collisions.

## 5. A Real Hash Collision: "Aa" and "BB"

The two Strings **"Aa"** and **"BB"** have different content yet **equal hashCodes**. This is a short, stable, and easy-to-verify example of a hash collision:

~~~java
String first = "Aa";
String second = "BB";

System.out.println(first.hashCode()); // 2112
System.out.println(second.hashCode()); // 2112
System.out.println(first.equals(second)); // false
~~~

**Collisions do not cause data loss.** HashSet still stores both "Aa" and "BB" because equals returns false. HashMap still distinguishes them and retrieves the right value for each key.

This does not contradict the equals–hashCode contract. The contract requires **equal objects to have the same hashCode**, and never requires **same hashCode to mean equal objects**.

In modern Java, buckets with many colliding elements are managed with appropriate internal mechanisms; HashMap can convert sufficiently crowded buckets into tree structures when implementation conditions are met. Do not write code that depends on bucket iteration order or assumes every operation in every scenario takes constant time.

## 6. Complete Java 17+ Program

Create the file **StringHashContractDemo.java**:

~~~java
import java.util.HashMap;
import java.util.HashSet;

public class StringHashContractDemo {
    public static void main(String[] args) {
        String a = new String("java");
        String b = "java";

        System.out.println("same reference: " + (a == b));
        System.out.println("equal content: " + a.equals(b));
        System.out.println("same hash: "
                + (a.hashCode() == b.hashCode()));

        HashSet<String> languages = new HashSet<>();
        System.out.println("add first: " + languages.add(a));
        System.out.println("add equal: " + languages.add(b));
        System.out.println("size: " + languages.size());
        System.out.println("contains: " + languages.contains("java"));

        String first = "Aa";
        String second = "BB";

        System.out.println("collision hashes: "
                + first.hashCode() + " / " + second.hashCode());
        System.out.println("collision equals: "
                + first.equals(second));

        HashMap<String, Integer> counts = new HashMap<>();
        counts.put(first, 1);
        counts.put(second, 2);
        counts.put(new String("Aa"), 3);

        System.out.println("map size: " + counts.size());
        System.out.println("Aa: " + counts.get("Aa"));
        System.out.println("BB: " + counts.get("BB"));
    }
}
~~~

Compile and run:

~~~bash
javac StringHashContractDemo.java
java StringHashContractDemo
~~~

Stdout:

~~~text
same reference: false
equal content: true
same hash: true
add first: true
add equal: false
size: 1
contains: true
collision hashes: 2112 / 2112
collision equals: false
map size: 2
Aa: 3
BB: 2
~~~

How to read the output:

- The two objects **a** and **b** have different references, yet identical content and hashCode.
- **HashSet** only accepts the first element because the second addition is equal according to equals.
- The two keys **"Aa"** and **"BB"** share the same hashCode but are not equal, so HashMap still holds **two** entries.
- Calling **put(new String("Aa"), 3)** updates the value of the key equivalent to **"Aa"**, without affecting **"BB"**.
- The example only retrieves data via explicit keys; it does not rely on the iteration order of **HashMap** or **HashSet** because that order is not guaranteed.

This directly demonstrates that **hashCode guides the lookup while equals determines key equivalence** in hash-based collections.

## 7. Key Stability After Insertion

A key inside a hash structure must keep the fields that determine `equals/hashCode` unchanged while it remains stored. For a custom type with mutable fields, modifying such a field after `put` can make `get` unable to find the key even though the entry is still there.

`String` avoids this risk because its content is immutable. Reassigning `key = key.toUpperCase()` only switches the reference variable to a different `String`; the old value inside the map remains intact. If you need a composite key with multiple fields, consider an immutable value object with a proper `equals/hashCode` contract instead of using a mutable key.

## 8. Distinguishing HashSet and HashMap from Other Collections

Not every collection uses hashCode to detect duplicates:

| Collection | How elements/keys are identified | Effect of String.hashCode |
| --- | --- | --- |
| **HashSet<String>** | Hash first, then compare with equals when needed | Used to organize lookups |
| **HashMap<String, V>** | Hash and equals for keys | Used to organize lookups |
| **ArrayList<String>** | **contains**, **indexOf** rely on equals | Does not use hashCode for these operations |
| **TreeSet<String>** | **compareTo** or Comparator to determine order and duplicates | Does not use hashCode to detect duplicate elements |
| **TreeMap<String, V>** | **compareTo** or Comparator for keys | Does not use hashCode to detect duplicate keys |

For String in natural order, **compareTo** returns 0 when String content is equal according to equals. However, if a custom Comparator is passed, such as **String.CASE_INSENSITIVE_ORDER**, TreeSet may treat **"Java"** and **"java"** as the same element even though **String.equals** returns false. This is a rule chosen by the Comparator, not a bug in hashCode.

If you only need a list that may contain duplicate values, use List. If you need a set of unique values according to **String.equals**, use HashSet. If you need a mapping table from String to values, use HashMap. If you need a set/map ordered by a Comparator, consider TreeSet/TreeMap.

## 9. Key Equality Also Depends on Data Policy

`String.equals` distinguishes letter case, whitespace, and Unicode encoding forms. Therefore, `"Java"` and `"java"` are two distinct keys in a `HashSet`, even though a `TreeSet` using `String.CASE_INSENSITIVE_ORDER` may treat them as the same key due to the comparator rule.

~~~java
Set<String> raw = new HashSet<>();
raw.add("Java");
raw.add("java");
System.out.println(raw.size()); // 2
~~~

When business logic wants two variants to map to a single identifier, normalize **before storing and looking up** according to an explicit policy. `toLowerCase(Locale.ROOT)` is one option for technical codes, though it does not cover every language/Unicode rule. Data normalization is not part of the hashing algorithm and does not fix hash collisions. A dedicated lesson on canonical keys covers that choice along with preserving display labels.

## 10. Common Misconceptions

### "Equal hashes mean equal data"

**False.** "Aa" and "BB" both have hashCode 2112 yet equals is false. Hash collisions are allowed and must be handled. Never write logic like:

~~~java
// WRONG for equality semantics:
boolean same = a.hashCode() == b.hashCode();
~~~

When comparing content, use **a.equals(b)** (if a is guaranteed non-null) or **Objects.equals(a, b)**.

### "Two different String objects are two different keys"

**False for HashMap<String, ...> and HashSet<String>.** They rely on equals, not **==**. A new String holding the exact same content can look up or update an existing entry.

### "HashSet loses keys when a collision occurs"

**False.** HashSet uses equals to distinguish elements that are genuinely different. Collisions can add extra lookup work, but they do not mean the collection merges unequal Strings.

### "String hashCode can be used as a unique ID"

**False.** A 32-bit output cannot uniquely represent all possible strings. HashCode is neither a business ID nor a security checksum. If an ID is needed, use an ID generator or a data-derived identifier that fits the requirements.

### "I can use == because literals live in the string pool"

**Unsafe.** Strings read from files, requests, concatenation, or created with **new** can have different references despite having the same content. **intern()** is a separate mechanism and should not be used to replace content comparison.

### "HashMap/HashSet will iterate in insertion order"

**Not guaranteed.** Hashing and collision mechanics do not establish a stable iteration order. When insertion order must be preserved, consider **LinkedHashMap/LinkedHashSet**; when sorted order is needed, consider **TreeMap/TreeSet** with an appropriate ordering.

### "All lookup cases are O(1)"

**No absolute guarantee.** With good hash distribution and appropriate table sizing, HashMap/HashSet achieve very good average lookup performance. If many keys fall into the same bucket, operations must inspect multiple candidates; Java has internal optimizations for dense buckets, but actual performance still depends on the data and runtime structure.

## 11. How to Debug String Issues in Collections

When **contains**, **get**, or **put** returns unexpected results, try checking in this order:

1. Print the String value in a way that clearly reveals whitespace, letter case, and hidden characters. **"java"** and **"java "** are not equal.
2. Check **equals** directly between the two values and compare **hashCode** for verification. If equals is true while hashCode differs on two objects of the same class, a custom class may violate the contract; standard String never has this issue.
3. Determine whether the collection uses the **equals/hashCode** contract or a **Comparator**. HashMap/HashSet differ from TreeMap/TreeSet.
4. For technical keys, verify whether consistent normalization is applied at both write time and lookup time.
5. Avoid diagnosing bugs based on HashMap iteration order, since that order is not guaranteed.
6. Check null values separately if the API must distinguish **missing key** from **key mapped to null**. For a Map, **containsKey** can provide information beyond just checking the result of **get**.

Small example showing the difference between a **missing key** and a **null value**:

~~~java
Map<String, String> map = new HashMap<>();
map.put("present", null);

// map.get("present") == null and map.get("missing") == null
// but map.containsKey("present") == true,
// whereas map.containsKey("missing") == false.
~~~

This is a matter of Map semantics rather than a hash collision, yet it is frequently confused when debugging String lookups.

## 12. Knowledge Check

Given three strings:

~~~java
String a = "Aa";
String b = "BB";
String c = new String("Aa");
~~~

Predict the results:

| Expression | Result | Reason |
| --- | --- | --- |
| **a.hashCode() == b.hashCode()** | true | Same hash code 2112 |
| **a.equals(b)** | false | Different content |
| **a == c** | false | c is a newly created object |
| **a.equals(c)** | true | Same content "Aa" |
| **a.hashCode() == c.hashCode()** | true | equals being true implies equal hashCodes |

If **a**, **b**, and **c** are added to a **HashSet<String>**, the final size is **2**: a and c are considered the same value, while b is a different value despite sharing the hashCode. If used as HashMap keys, **put(c, value)** will update the mapping corresponding to a; b remains a separate key.

Remember the implication direction accurately: **equal by equals ⇒ equal hashCode; equal hashCode ⇏ equal by equals**. String enforces the contract, while HashSet/HashMap are designed to handle collisions while keeping genuinely different strings separate.
