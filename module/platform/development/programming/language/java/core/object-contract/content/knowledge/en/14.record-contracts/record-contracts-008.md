# Customizing Accessors, Normalization, or Defensive Copying Must Preserve the Record Contract

## 1. Records Are Value-Carrying Types and Component Transparency

In Java 17+, a **record** is used to represent a fixed group of values, with a set of **record components** declared in the header:

~~~java
record ProductKey(String tenantId, String sku) {}
~~~

From this declaration, the compiler provides (unless you manually declare the corresponding members):

- **`private final` fields** corresponding to each component, here **tenantId** and **sku**.
- **Canonical constructor** taking all components in the exact order and types.
- Public **accessors** **tenantId()**, **sku()**; unlike JavaBean getters such as **getSku()**.
- **equals(Object)**, **hashCode()**, **toString()** derived from the **component fields**.
- Records are implicitly **final**; you cannot create a subclass extending a record to add instance state fields.

The fields are **final**, yet this is **shallow immutability**: if a component holds a reference to a **List**, **Map**, array, or mutable object, the contents of those objects can still change. Therefore, a record does not automatically turn an entire object graph into deeply immutable state.

Records aim for **state transparency**: accessors must describe state consistently with what the canonical constructor stores, and equals/hashCode/toString must match that value. Java allows customizing constructors, accessors, and equals/hashCode, yet the responsibility for maintaining the contract belongs to the author.

## 2. The Most Important Copy Invariant of a Record

The contract of **java.lang.Record** requires: for a record **R** with components **c1, c2, ..., cn**, if a copy is constructed by passing the accessor results of r into the canonical constructor:

~~~java
R copy = new R(r.c1(), r.c2(), ..., r.cn());
~~~

then **r.equals(copy)** must be **true**.

This is **general pseudocode**, not a compilable Java file because R and the component names are placeholders. For a concrete record:

~~~java
ProductKey copy = new ProductKey(original.tenantId(), original.sku());
boolean sameValue = original.equals(copy); // must be true
~~~

The snippet above is used in a context where an **original** variable of type **ProductKey** already exists.

Beyond the record-specific invariant, any equals/hashCode override must preserve the general Object contract:

1. **Reflexive:** a.equals(a) is true.
2. **Symmetric:** a.equals(b) yields the same result as b.equals(a).
3. **Transitive:** if a equals b and b equals c, then a equals c.
4. **Consistent:** results remain stable as long as the values used in comparison do not change.
5. **Null:** a.equals(null) is false.
6. **Hash:** if a.equals(b) is true then a.hashCode() == b.hashCode(); equal hashes do not require equals to be true.

For ordinary records with immutable components and auto-generated equals/hashCode, these conditions are usually guaranteed by each component's own contract. Overriding an accessor to **transform data on read**, or copying an array while continuing to use default equals by **reference identity**, can break the copy invariant without any compiler error.

**A decisive detail:** the record's implicitly generated equals/hashCode/toString rely on **component field values**, which **does not mean** they call custom accessors before comparing or computing the hash. Hence modifying an accessor alone does not change equals semantics.

## 3. Mistake 1: Normalizing Only in the Accessor Makes Copies Differ from the Original

Suppose we want product codes to be uppercase with leading and trailing whitespace removed. An easy mistake to make is **keeping the original string in the field**, while returning the normalized string in the accessor.

Create the file **AccessorNormalizationDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class AccessorNormalizationDemo {
    record BadCode(String code) {
        @Override
        public String code() {
            return code.strip().toUpperCase(Locale.ROOT);
        }
    }

    record GoodCode(String code) {
        GoodCode {
            code = Objects.requireNonNull(code, "code")
                .strip()
                .toUpperCase(Locale.ROOT);

            if (code.isEmpty()) {
                throw new IllegalArgumentException("code is empty");
            }
        }
    }

    public static void main(String[] args) {
        BadCode bad = new BadCode(" ab-7 ");
        BadCode badCopy = new BadCode(bad.code());

        System.out.println("bad accessor: " + bad.code());
        System.out.println("bad copy equals: " + bad.equals(badCopy));

        GoodCode good = new GoodCode(" ab-7 ");
        GoodCode goodCopy = new GoodCode(good.code());
        GoodCode same = new GoodCode("AB-7");

        System.out.println("good accessor: " + good.code());
        System.out.println("good copy equals: " + good.equals(goodCopy));
        System.out.println("normalized equals: " + good.equals(same));
        System.out.println("matching hash: " +
            (good.hashCode() == same.hashCode()));

        Set<GoodCode> codes = new HashSet<>();
        codes.add(good);
        codes.add(same);
        System.out.println("unique codes: " + codes.size());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac AccessorNormalizationDemo.java
java AccessorNormalizationDemo
~~~

Output:

~~~text
bad accessor: AB-7
bad copy equals: false
good accessor: AB-7
good copy equals: true
normalized equals: true
matching hash: true
unique codes: 1
~~~

### Why Is BadCode Wrong?

The component field of **bad** actually stores **" ab-7 "**. The **bad.code()** accessor returns **"AB-7"** without updating the stored field. When using the accessor value to construct **badCopy**, the field in the copy stores **"AB-7"**. Because the implicitly generated equals compares the two actual String fields, **bad.equals(badCopy)** returns false.

This bug exists even though **bad.code()** and **badCopy.code()** both return **"AB-7"**. Callers see two identical accessor values, yet equals says they differ; the record is no longer transparent with respect to the copy contract.

### Why Is GoodCode Right?

The **GoodCode** record normalizes **before storing** in the **compact canonical constructor**:

~~~java
GoodCode {
    code = Objects.requireNonNull(code).strip().toUpperCase(Locale.ROOT);
}
~~~

In a compact constructor, the component parameter **code** can be reassigned; after the block finishes, the compiler assigns the final parameter value into the corresponding field. **Do not assign this.code directly** inside the compact constructor body. The default accessor afterward reads out the normalized value that is actually stored.

Result: every spelling considered the same code by the business domain produces a record with the same value; a copy constructed from the accessor also has the same value; and auto-generated equals and hashCode remain consistent.

**Business note:** Only use **toUpperCase(Locale.ROOT)** when codes are specified as case-insensitive; do not apply it automatically to case-sensitive data, personal names, or codes with different normalization rules. For complex Unicode or account identifiers, specify exact normalization rules before applying them.

## 4. Customizing the Canonical Constructor Properly

### Compact Constructor and Explicit Canonical Constructor

Both styles below serve input validation/normalization, though their field-assignment mechanics differ.

**Compact constructor** is the concise form when processing individual components:

~~~java
record Port(int number) {
    Port {
        if (number < 1 || number > 65535) {
            throw new IllegalArgumentException("invalid port");
        }
    }
}
~~~

**Explicit canonical constructor** declares the full parameter list and assigns all fields manually:

~~~java
record Port(int number) {
    public Port(int number) {
        if (number < 1 || number > 65535) {
            throw new IllegalArgumentException("invalid port");
        }
        this.number = number;
    }
}
~~~

The two blocks above are **two alternative definitions for the same record**, not to be placed together in the same file. For a top-level record with package-private visibility, a compact constructor may omit an access modifier; an explicit canonical constructor using **public** is also valid because it widens accessibility. When the record itself is declared **public**, an explicit canonical constructor must also have at least **public** accessibility.

You cannot declare both canonical constructors for the same signature. Other constructors, if any, must delegate to the canonical constructor (following record constructor rules).

### Normalization Must Remain Stable When Reconstructed

If the normalizer is a function **N**, by design we must maintain:

~~~text
N(N(x)) = N(x)
~~~

This is **idempotence**: normalizing once or multiple times yields the same result. If the constructor normalizes a second time and transforms the value again, a copy built from the accessor may not equal the original.

For example, **strip** and **toUpperCase(Locale.ROOT)** on a simple code are idempotent. Operations such as automatically incrementing a version, attaching the current timestamp, prepending a repeated prefix, or generating a new ID on every constructor call are **not** idempotent when feeding accessor output back into the constructor.

When a constructor validates multiple components, check **combinations of components** too, not just individual fields in isolation.

## 5. Normalizing Multiple Components Together: Preserving the Invariant with the Canonical Constructor

Some values have multiple equivalent representations, such as numeric ranges whose endpoints do not depend on input order. You can normalize **the pair together** right inside the constructor.

Create the file **RangeRecordDemo.java**:

~~~java
public class RangeRecordDemo {
    record IntRange(int start, int end) {
        IntRange {
            if (start > end) {
                int temp = start;
                start = end;
                end = temp;
            }
        }

        public boolean contains(int value) {
            return value >= start && value <= end;
        }
    }

    public static void main(String[] args) {
        IntRange reversed = new IntRange(9, 2);
        IntRange forward = new IntRange(2, 9);

        IntRange copy =
            new IntRange(reversed.start(), reversed.end());

        System.out.println("range: " + reversed);
        System.out.println("equal: " + reversed.equals(forward));
        System.out.println("copy equal: " + reversed.equals(copy));
        System.out.println("contains five: " + reversed.contains(5));
    }
}
~~~

Run:

~~~bash
javac RangeRecordDemo.java
java RangeRecordDemo
~~~

Output:

~~~text
range: IntRange[start=2, end=9]
equal: true
copy equal: true
contains five: true
~~~

The two arguments were swapped, yet the record's state was normalized to the same pair **(2, 9)**, so default equals/hashCode match the new meaning. If swapped only when accessors are called while the fields still store **(9, 2)**, copies would break the invariant just like **BadCode**.

**Limitation:** This rule only makes sense when the business domain treats reversed-endpoint intervals as the same range. If endpoint order carries meaning (such as direction of travel), swapping automatically is a domain bug even while keeping the Java contract.

## 6. Mistake 2: Defensively Copying an Array While Keeping Default equals

A record with a **byte[]** component easily causes confusion:

~~~java
record RawPacket(byte[] payload) {}
~~~

**byte[]** arrays do not override **Object.equals/hashCode** by contents. Therefore, two RawPacket instances containing two different arrays with the same bytes will not be equal under default record behavior.

If fixed by cloning the array in the constructor and cloning again in the accessor, safety against external data mutation improves, **yet the record copy contract can still be violated**: a copy built from the accessor has an array with a different identity, while the implicit equals still compares references.

Create the file **ArrayCopyContractDemo.java**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ArrayCopyContractDemo {
    record BadPacket(byte[] payload) {
        BadPacket {
            payload = Objects.requireNonNull(payload).clone();
        }

        @Override
        public byte[] payload() {
            return payload.clone();
        }
    }

    record GoodPacket(byte[] payload) {
        GoodPacket {
            payload = Objects.requireNonNull(payload).clone();
        }

        @Override
        public byte[] payload() {
            return payload.clone();
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof GoodPacket other
                && Arrays.equals(payload, other.payload);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(payload);
        }

        @Override
        public String toString() {
            return "GoodPacket[payload=" +
                Arrays.toString(payload) + "]";
        }
    }

    public static void main(String[] args) {
        BadPacket bad = new BadPacket(new byte[]{1, 2, 3});
        BadPacket badCopy = new BadPacket(bad.payload());

        System.out.println("bad content equal: " +
            Arrays.equals(bad.payload(), badCopy.payload()));
        System.out.println("bad record equal: " + bad.equals(badCopy));

        byte[] source = {1, 2, 3};
        GoodPacket good = new GoodPacket(source);
        GoodPacket copy = new GoodPacket(good.payload());

        System.out.println("good record equal: " + good.equals(copy));
        System.out.println("good hash equal: " +
            (good.hashCode() == copy.hashCode()));

        Set<GoodPacket> unique = new HashSet<>();
        unique.add(good);
        unique.add(copy);
        System.out.println("unique packets: " + unique.size());

        source[0] = 9;
        byte[] returnedCopy = good.payload();
        returnedCopy[1] = 8;
        System.out.println("after external edits: " + good);
    }
}
~~~

Compile/run:

~~~bash
javac ArrayCopyContractDemo.java
java ArrayCopyContractDemo
~~~

Output:

~~~text
bad content equal: true
bad record equal: false
good record equal: true
good hash equal: true
unique packets: 1
after external edits: GoodPacket[payload=[1, 2, 3]]
~~~

### Why Is GoodPacket Right?

- **Compact constructor** clones the input array: callers mutating **source** afterward do not alter the record's state.
- **Accessor** returns a cloned array: callers do not receive a reference to the internal array.
- **equals** uses **Arrays.equals(byte[], byte[])** to compare byte-by-byte.
- **hashCode** uses **Arrays.hashCode(byte[])** to hash the same contents.
- **toString** is customized into a readable form. Left at default, the array representation can look like **[B@...** because arrays use Object's toString.
- A copy built from the accessor has an array with a different reference yet identical contents, so the **r.equals(new R(r.component()))** invariant holds.
- When the record is used as a HashMap/HashSet key, its hash cannot be changed through either external mutation path that has been blocked.

**Do not fix by comparing contents in equals while keeping auto-generated hashCode.** If equals uses Arrays.equals yet the record's hashCode still derives from the array component by identity, two content-equal records can have different hash codes. When changing a record's equals criterion, you must **update hashCode accordingly**.

## 7. Multi-Dimensional Arrays and Nested Mutable References

For **int[][]**, cloning only the outer array **is not enough**: individual **int[]** rows can still be shared and mutated. If equals uses **Arrays.deepEquals**, then hashCode must use **Arrays.deepHashCode**, and each child array must be copied when promising content immutability.

A pattern applied inside a record holding a matrix:

~~~java
// Excerpts inside a record with component int[][] matrix.

static int[][] copyMatrix(int[][] src) {
    Objects.requireNonNull(src);
    int[][] result = new int[src.length][];
    for (int i = 0; i < src.length; i++) {
        result[i] = src[i] == null ? null : src[i].clone();
    }
    return result;
}

// Inside the compact canonical constructor:
matrix = copyMatrix(matrix);

// Inside the accessor public int[][] matrix():
return copyMatrix(matrix);

// Inside equals(Object) after checking the exact record type:
return Arrays.deepEquals(matrix, other.matrix);

// Inside hashCode():
return Arrays.deepHashCode(matrix);
~~~

The snippets above only illustrate **different parts of the same record**, not a standalone Java program; **java.util.Arrays** and **java.util.Objects** must be imported. The deepEquals/deepHashCode pair is chosen when value semantics mean **nested array contents**. For 1D **int[]**, use Arrays.equals/hashCode accordingly.

If an array contains **mutable objects** deep inside, cloning the array alone is not sufficient. Deep immutability requires copying or using immutable types for each leaf object; do not claim full defensive copying if mutable references from callers are still retained.

## 8. List and Map: Defensive Copying Still Allows Default equals/hashCode

A record containing **List<String>** can be safer and simpler than an array: **List.equals** and **List.hashCode** are already defined by elements, and **List.copyOf** can create an unmodifiable representation.

Create the file **ImmutableListRecordDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ImmutableListRecordDemo {
    record UserRoles(String userId, List<String> roles) {
        UserRoles {
            userId = Objects.requireNonNull(userId, "userId").strip();
            roles = List.copyOf(Objects.requireNonNull(roles, "roles"));

            if (userId.isEmpty()) {
                throw new IllegalArgumentException("userId is empty");
            }
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("reader"));
        UserRoles first = new UserRoles(" u-1 ", source);
        UserRoles copy = new UserRoles(first.userId(), first.roles());

        System.out.println("user: " + first.userId());
        System.out.println("copy equal: " + first.equals(copy));
        System.out.println("hash equal: " +
            (first.hashCode() == copy.hashCode()));

        source.add("admin");
        System.out.println("after editing source: " + first.roles());

        try {
            first.roles().add("owner");
        } catch (UnsupportedOperationException ex) {
            System.out.println("accessor list cannot be modified");
        }

        System.out.println("final roles: " + first.roles());
    }
}
~~~

Run:

~~~bash
javac ImmutableListRecordDemo.java
java ImmutableListRecordDemo
~~~

Output:

~~~text
user: u-1
copy equal: true
hash equal: true
after editing source: [reader]
accessor list cannot be modified
final roles: [reader]
~~~

**Why is overriding equals/hashCode unnecessary?** List.copyOf creates a list that disallows structural modification and contains no nulls, with immutable String elements in this example. **List.equals** compares elements in order and **List.hashCode** is compatible. Thus the record's auto-generated equals/hashCode are appropriate.

**Limitations of List.copyOf/Map.copyOf:**

- This is a **shallow** copy. If a List element is a mutable object, or a Map value can change, the record can still observe changes inside leaf objects.
- List.copyOf does not allow null elements; Map.copyOf does not allow null keys/values. Choose the data policy upfront, rather than silently substituting null.
- **List.equals** is sensitive to order and multiplicity. If the business domain treats roles as an unordered set, use a Set-typed value with the corresponding contract, or normalize the structure before storing.
- Other immutable collection structures with suitable equals/hashCode contracts may be used; always verify domain semantics.

## 9. Customizing equals/hashCode and Record Limitations

### Do Not Drop a Component in equals and Forget to Fix hashCode

For example, the following record contains a customer code and a version:

~~~java
record RevisionedKey(String code, int version) {}
~~~

By default, two instances are equal only when both **code** and **version** match. If the business domain only treats **code** as the identifier and you manually override equals based solely on code, the auto-generated hashCode—which includes both components—can differ between two records considered equal.

A better approach is usually to **design a separate key record** with the right scope, rather than overriding the semantics of a record representing full data:

~~~java
record CustomerCode(String code) {}
record CustomerRevision(CustomerCode id, int version) {}
~~~

Code grouping by customer will take **CustomerCode**, while version information can be kept in CustomerRevision. If overriding equals is genuinely needed, override hashCode over the exact same set of fields and still preserve the copy invariant.

### Component Types with Special equals Meanings

- **BigDecimal**: **new BigDecimal("1.0")** does not equal **new BigDecimal("1.00")**, even though compareTo returns 0. If the business domain wants numeric equivalence, normalize the component in the constructor (e.g., stripTrailingZeros where appropriate), then keep consistent default equals/hashCode.
- **double/float**: a record's implicit equals for primitive components uses **Double.compare/Float.compare** semantics accordingly, paying attention to NaN and the difference between **+0.0** and **-0.0**. Do not arbitrarily switch equals to **==** without synchronizing hashCode and domain requirements.
- **Collection**: List compares in order; Set compares as a set of elements; Map compares key–value pairs. Choose the right component so implicit equals has the right meaning.
- **Array**: default equals/hashCode do not compare array contents; use a value wrapper or manually override the method pair.

### toString Must Also Be Honest About Values

Records have an implicit toString based on component fields. If an accessor transforms data without changing the field, the implicit toString can expose the mismatch between "stored value" and "value seen by caller".

When overriding toString, clearly represent the meaningful value and avoid relying on fluctuating external state; under the java.lang.Record contract, equal records are expected to have equal string representations (with rare exceptions when components are equivalent yet their component strings differ). Do not rely on the toString string structure to reverse-parse data: the specific format is not a serialization protocol.

## 10. Other Flawed Designs to Avoid

### Getter Clamping/Masking Data While Constructor Does Not

For example, an accessor returning **Math.min(x, 100)** while the field stores 200. A copy built from the accessor has 100, making equals false against the original value. If x ≤ 100 should always be enforced, do it right inside the canonical constructor so the field actually stores the canonical value.

### Normalization with Side Effects or Non-Idempotence

A constructor that auto-increments a sequence, generates the current timestamp, or appends a suffix per call can make a copy unequal to the original. If metadata such as creation time must be preserved, pass it as an explicit component; do not silently regenerate it whenever recreating a copy.

### Protecting Input Only, Forgetting the Accessor

~~~java
record UnsafeData(int[] values) {
    UnsafeData {
        values = values.clone();
    }
}
~~~

The record above prevents mutating the initial input array, yet the default generated **values()** accessor returns the exact reference to the internal array; callers can still mutate its contents. If true value immutability is needed, decide on an appropriate accessor and equals/hashCode policy.

### Protecting the Accessor Only, Forgetting the Constructor

If the constructor stores the raw input array directly, callers can still keep the array variable and mutate its contents after the record is created. Cloning in the accessor on read does not fix aliasing from the constructor.

### Believing final Prevents Mutating Nested Objects

Record fields are final, yet **List<MutableItem>** and **Map<String, MutableItem>** can change through element objects. If deep immutability is desired, control inner values as well.

### Testing Only equals While Ignoring hashCode

HashMap/HashSet require equal keys to have identical hashes. Pairs of records equal via Arrays.equals yet having reference-based hashCode can produce wrong and hard-to-reproduce results. Always test with **two independently allocated arrays**.

### Inverting the Purpose of an Accessor

If a display representation differing from the stored value is desired, usually add a **clearly named method**, such as **formattedCode()**, **displayName()**, **normalizedForSearch()**, rather than making a component accessor return a value contradicting the field. An auxiliary method can customize presentation without breaking the record's copy invariant.

## 11. Systematically Testing the Record Contract

For a record **R(c1, c2, ..., cn)**, write tests across the following categories.

### A. Reconstructibility from Accessors

Create **r** from input likely to trigger normalization, then construct a copy:

~~~java
R copy = new R(r.c1(), r.c2(), ..., r.cn());
~~~

In real code, replace R and component names with the record under test. Verify **r.equals(copy)** is true, **r.hashCode() == copy.hashCode()**, and corresponding accessors yield logically consistent values. This directly tests the record-specific contract.

### B. Idempotence of Normalization

- Construct records from representations specified as equivalent, such as **" A1 "** and **"a1"** for case-insensitive codes.
- Reconstruct from accessors; no second-pass change must occur.
- Test null inputs, empty strings, and constraint-violating component pairs; verify sensible exception types or messages.
- Do not assume every normalization is valid for the business domain.

### C. Defensive Copying

- Use an **initial mutable array/List** to construct, then mutate the source.
- Retrieve the component via the accessor and attempt to mutate the result.
- If the record claims immutability, observable state, equals, and hashCode must remain stable after those tests.
- For multi-dimensional arrays, mutate **elements at every level**; for List/Map containing mutable objects, try changing the state of leaf objects.
- Compare a copy with the original when they hold separately cloned arrays.

### D. Object and Collection Contracts

- Test **r.equals(r)**; **r.equals(null)** is false; reversed pairs yield the same result.
- With at least three objects, verify transitivity if two consecutive equals checks are true.
- If equals is true then hashCode must be equal; do not require unequal pairs to have different hashes.
- Insert equal instances into a **HashSet**; HashMap key lookup using a copy constructed from accessors must succeed.
- If overriding toString, consider cases where two objects are equal yet toString differs due to mutable references or external state.

### E. File Naming, Runnability, and API

For records declared **inside a demo class**, name the file after the enclosing **public class**. For records declared **public at top-level**, name the file after the record. Use **Java 17+**; compact canonical constructors and records are standard features since Java 16. Custom accessors you declare must be **public**, take no parameters, and match the component type.

## 12. Choosing an Implementation by Component Type

| Requirement | Appropriate Implementation | Mandatory Verification |
| --- | --- | --- |
| Component is an immutable String/primitive/Instant and equals semantics already fit | Keep auto-generated accessors and equals/hashCode | Copy invariant, null cases, and normalization |
| Input needs stripping, case folding, or clamping to a canonical range | **Normalize in the canonical constructor** | N(N(x)) = N(x), reconstructing from accessors yields equals true |
| Component is List/Map with immutable elements | **List.copyOf/Map.copyOf** in constructor, usually keep default equals/hashCode | Block input aliasing, no unintended nulls, copy invariant |
| Component is an array yet **content** comparison is wanted | Clone on input/output and override **both equals and hashCode** using corresponding Arrays methods | Copy invariant, two separate arrays with identical contents, HashSet |
| Component is a multi-dimensional array or nested mutable structure | Copy every necessary level; **deepEquals/deepHashCode** when rule is deep comparison | No remaining mutable aliases, contract of each leaf object |
| Only a display/computed string differing from stored field is needed | Add a **separate method** instead of altering the component accessor | Accessor still reflects the value used to reconstruct the record |
| Want equals based on only a subset of information | Prefer a **separate key record**, or override consistently if truly necessary | Synchronized equals/hashCode, copy invariant unbroken |

**Key Takeaway:** Records allow customizing constructors, accessors, and equals/hashCode, yet these parts form **a single unified contract**. State observed through accessors must suffice to reconstruct a value equal to the original; normalization should happen **before storing**, while defensive copying must be designed alongside the component's **equals/hashCode semantics**. For arrays, cloning alone is not enough to preserve the contract: compare/hash by contents if accessors return copies. For collections with value-based equals and immutable elements, immutable copying usually lets you keep the record's auto-generated methods intact.

Specification reference: [java.lang.Record, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).