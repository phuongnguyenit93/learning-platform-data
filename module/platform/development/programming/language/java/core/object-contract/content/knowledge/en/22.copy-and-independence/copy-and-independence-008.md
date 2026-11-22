# Checking Whether Mutating a Copy Affects the Original

## 1. Goal: Verifying Copy Independence

When copying a Java object, the important question is not merely “do two variables point to two different objects?”, but: **if mutable state is modified on the copy, does the observable state of the original change as well, and vice versa?**

For example, a profile object has a name (String), an address (Address), and a list of skills (List<String>). Two profiles can be two different objects yet still point to the same Address or the same List. When editing the address or list on the copy, the original is still affected.

Two concepts must be distinguished:

- **Different identity:** checked with the **==** or **!=** operators on references. **copy != original** only proves the outermost objects are different.
- **Mutable state independence:** components required to be independent have no shared reference paths allowing an edit on one side to change the other side. This is behavior that must be tested with concrete mutation and observation operations.

Not every shared reference is a bug: immutable objects like String, Integer, or a truly immutable value object can be shared without creating shared-mutation risk. The required degree of independence depends on the **copy contract** of the class/API; “deep copy” usually means copying the mutable part of the graph owned by the object, not necessarily creating a new instance for every immutable value.

## 2. Why Can a Copy Affect the Original?

Reference-type variables hold a reference to an object, not the entire child object structure. Assigning a variable or copying a reference field can leave two access paths reaching the same mutable object.

| Creation method | Outermost object | Inner mutable reference fields | Result upon mutation |
| --- | --- | --- | --- |
| **alias = original** | Exact same object | Shared | Every state change via alias is visible through original |
| **Shallow copy** | Usually a new object | Usually still shares child objects | Modifying a shared child object can affect the original |
| **Deep copy** | New object | Copies mutable parts within the scope needing independence | Modifications to copied parts are independent between both sides |
| **Immutable / safe-sharing design** | May be new or shared | Shared data cannot be mutated through valid APIs | No mutable change exists to propagate across shared parts |

A String variable assigned to a copy can safely share the String object, because String is immutable. Conversely, if the same Address object is held in two profile objects, the statement **copy.address.city = "Huế"** modifies the very Address that the original holds; this is not reassigning the copy's own address field.

Similarly, calling **new ArrayList<>(original.skills)** creates a new List but only copies element references. If the elements are Strings, element sharing is safe; if the elements are mutable Address objects, changes to an Address's contents can still propagate across both lists.

## 3. Proper Testing Procedure

1. **Identify the contract:** which fields must the copy be independent on? List nested objects, arrays, collections, mutable elements, and state modifiable through getters or other methods.
2. **Arrange – create observable original data:** for example city “Hà Nội”, list [Java]. Create the copy using the exact method/API under test. Capture pre-mutation values with an independent snapshot or immutable expected values; avoid calling an aliased reference a “snapshot”.
3. **Check reference structure when appropriate:** **assertNotSame(original, copy)** is not enough; for mutable components that must be separated, also check **assertNotSame(original.address, copy.address)** and related collections or elements. If the contract intentionally shares a resource, do not force every reference to differ.
4. **Act – mutate the copy directly:** assign mutable fields, modify child object state, add/remove elements, mutate mutable elements. **Assert – verify the original did not change** per the contract.
5. **Test the reverse direction:** mutate the original itself and confirm the corresponding part of the copy does not change. Both directions catch shared references even when only one side exposes a mutating API.
6. **Repeat across key mutable branches:** multiple nesting levels, arrays, List, Map, mutable elements, null/empty collections, and cyclic structures if the data model supports them.

Separate **mutating a child object** from **reassigning a reference**. For example, **copy.address = new Address("Huế")** only changes the copy's address field, so the original does not change even if both previously shared an Address. To test for a shallow copy, you must use **copy.address.city = "Huế"** or a method that actually mutates the existing Address object.

## 4. Java 17+ Example: Comparing Alias, Shallow Copy, and Deep Copy

The following is a complete program. **UserProfile.shallowCopy()** creates a new UserProfile object while keeping the Address and List references unchanged. **UserProfile.deepCopy()** creates a new Address and a new List. Because the List's elements are immutable Strings, this way of copying the List suffices for independence of the mutable fields in the example.

Save to **`CopyIsolationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CopyIsolationDemo {

    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }

        Address(Address other) {
            this.city = other.city;
        }
    }

    static final class UserProfile {
        String name;
        Address address;
        List<String> skills;

        UserProfile(String name, Address address, List<String> skills) {
            this.name = name;
            this.address = address;
            this.skills = skills;
        }

        UserProfile shallowCopy() {
            return new UserProfile(name, address, skills);
        }

        UserProfile deepCopy() {
            return new UserProfile(
                    name,
                    new Address(address),
                    new ArrayList<>(skills)
            );
        }
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        UserProfile original = new UserProfile(
                "An",
                new Address("Hà Nội"),
                new ArrayList<>(List.of("Java"))
        );

        UserProfile alias = original;
        UserProfile shallow = original.shallowCopy();

        System.out.println("Alias cùng đối tượng: " + (alias == original));
        System.out.println("Shallow khác đối tượng: " + (shallow != original));
        System.out.println("Shallow dùng chung Address: "
                + (shallow.address == original.address));
        System.out.println("Shallow dùng chung List: "
                + (shallow.skills == original.skills));

        shallow.address.city = "Huế";
        shallow.skills.add("SQL");
        System.out.println("Gốc sau sửa shallow: "
                + original.address.city + " | " + original.skills);

        require("Huế".equals(original.address.city),
                "Shallow phải nhìn thấy thay đổi trên Address dùng chung");
        require(original.skills.contains("SQL"),
                "Shallow phải nhìn thấy thay đổi trên List dùng chung");

        UserProfile source = new UserProfile(
                "Bình",
                new Address("Hà Nội"),
                new ArrayList<>(List.of("Java"))
        );
        UserProfile deep = source.deepCopy();

        require(deep != source, "Đối tượng ngoài cùng phải khác");
        require(deep.address != source.address, "Address phải khác");
        require(deep.skills != source.skills, "List phải khác");

        deep.address.city = "Đà Nẵng";
        deep.skills.add("Spring");
        System.out.println("Gốc sau sửa deep: "
                + source.address.city + " | " + source.skills);

        require("Hà Nội".equals(source.address.city),
                "Sửa Address của deep không được sửa bản gốc");
        require(source.skills.equals(List.of("Java")),
                "Sửa List của deep không được sửa bản gốc");

        source.address.city = "Cần Thơ";
        source.skills.add("SQL");
        System.out.println("Deep sau sửa gốc: "
                + deep.address.city + " | " + deep.skills);

        require("Đà Nẵng".equals(deep.address.city),
                "Sửa Address gốc không được sửa deep");
        require(deep.skills.equals(List.of("Java", "Spring")),
                "Sửa List gốc không được sửa deep");

        System.out.println("Các phép kiểm tra đã thành công.");
    }
}
~~~

Compile and run (in a terminal with JDK 17+):

~~~bash
javac -encoding UTF-8 CopyIsolationDemo.java
java CopyIsolationDemo
~~~

Exact stdout result:

~~~text
Alias cùng đối tượng: true
Shallow khác đối tượng: true
Shallow dùng chung Address: true
Shallow dùng chung List: true
Gốc sau sửa shallow: Huế | [Java, SQL]
Gốc sau sửa deep: Hà Nội | [Java]
Deep sau sửa gốc: Đà Nẵng | [Java, Spring]
Các phép kiểm tra đã thành công.
~~~

**Output explanation:**

- **alias == original** is true: both variables point to the same UserProfile.
- **shallow != original** is true, yet both shallow's Address and List still point to original's child objects; mutations through shallow appear in original.
- **deep.address != source.address** and **deep.skills != source.skills**. After mutating deep, source keeps its old data. After mutating source, deep keeps its own data. This demonstrates independence for the mutable fields tested in this model.
- The **require(...)** method throws AssertionError if the condition is false, independent of the **-ea** runtime flag unlike Java's assert statement. The example intentionally asserts that shallow *does* have shared side effects to illustrate behavior, while deep *does not* have shared side effects to prove the independence requirement.

Note: `deepCopy` above is only correct within the scope of the example because Address has no other nested mutable fields and List holds Strings. If Address contains a mutable object inside or List holds mutable elements, those branches must continue to be copied per the contract.

## 5. Turning the Above Criteria into Automated Tests

In a project with **JUnit Jupiter (JUnit 5)**, you can write a separate test with explicit assertions. The snippet below assumes the test class is in the **same package** as CopyIsolationDemo and the project already declares the JUnit 5 dependency; this is supplementary test code, not a program runnable directly with the `java` command.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class CopyIsolationDemoTest {

    @Test
    void deepCopyIsIndependentInBothDirections() {
        var original = new CopyIsolationDemo.UserProfile(
                "An",
                new CopyIsolationDemo.Address("Hà Nội"),
                new ArrayList<>(List.of("Java"))
        );
        var copy = original.deepCopy();

        assertNotSame(original, copy);
        assertNotSame(original.address, copy.address);
        assertNotSame(original.skills, copy.skills);

        copy.address.city = "Huế";
        copy.skills.add("SQL");
        assertEquals("Hà Nội", original.address.city);
        assertEquals(List.of("Java"), original.skills);

        original.address.city = "Đà Nẵng";
        original.skills.add("Docker");
        assertEquals("Huế", copy.address.city);
        assertEquals(List.of("Java", "SQL"), copy.skills);
    }
}
~~~

When testing a real copy method in a project, replace **original.deepCopy()** with the actual API, pick a dataset covering mutable branches, and assert according to the contract. A single test for a flat object can miss sharing on a rarely used field.

## 6. Matrix of Scenarios to Test

| Data type / structure | Mutation to attempt | Sign the copy is not yet independent |
| --- | --- | --- |
| Primitive fields **int**, **boolean** | Modify field on copy then check original | Normally cannot propagate across primitive value copy; if it does, you may be operating on the same outer object |
| **String**, immutable wrapper types | Assign a new value to the field on copy | Reassigning a field does not mutate the String/Integer object; no need to deep-copy them |
| Nested mutable object, e.g. **Address** | Modify **copy.address.city** | **original.address.city** changes along with it |
| Primitive array, e.g. **int[]** | Modify **copy.values[0]** | Element of original array changes too if the array is shared |
| **List<String>** | **copy.skills.add(...)**, remove, set | Original list changes too if the same List is shared |
| **List<Address>** | Modify **copy.addresses.get(0).city** | New List, yet Address elements are still shared |
| **Map<K, MutableValue>** | Mutate a value, add/remove entry | Original value changes if element is shared; entry add/remove propagates if Map is shared |
| Getter returning mutable reference | Grab **copy.getAddress()** then mutate | Original changes even though the field may be declared private |
| Graph with shared branches / reference cycles | Mutate deeper elements, test both directions | A branch remains shared outside contract scope; naive recursive copying may loop infinitely |

For List, Map, and arrays, you must distinguish **copying the container shell** from **copying elements**. For example:

~~~java
List<Address> original = new ArrayList<>();
original.add(new Address("Hà Nội"));

List<Address> copy = new ArrayList<>(original); // New List, old Address
copy.get(0).city = "Huế";

// original.get(0).city is also "Huế" because the Address element is shared.
~~~

This snippet is illustrative and uses the Address class defined in the previous example; it is not a standalone Java file. If independence from changes to each Address is desired, create a new Address for each element, such as iterating over source and calling **new Address(item)**, while handling nulls and reference relationships per the contract.

## 7. Choosing a Copy Strategy and Limits of Each API

- **Copy constructor / factory method:** easily expresses exactly how fields are copied. For classes with mutable fields, decide whether to copy recursively, keep immutable, or intentionally share a resource. A copy constructor that only reassigns references may still be a shallow copy.
- **clone():** **Object.clone()** shallow-copies field state; it does not automatically create independent copies for all child objects. To use clone under a deep contract, appropriate handling of mutable fields must be implemented. A class supporting Cloneable does not mean the object graph is deep-copied.
- **Arrays:** **array.clone()** or **Arrays.copyOf(...)** creates a new array; for arrays holding references, elements can still point to mutable objects.
- **Collections:** **new ArrayList<>(source)** creates a new List, yet elements are still shared by reference. **List.copyOf(source)** creates a list disallowing modification via its List operations, without deep-copying mutable elements; it also rejects nulls in input elements. **Collections.unmodifiableList(source)** is a view disallowing edits through the view, yet it can reflect changes from the underlying source list.
- **Java record:** reference components can still point to mutable objects. Record syntax does not automatically create deep copies or guarantee deep immutability; constructors and accessors may need defensive copies if the goal is protecting state.
- **Immutable objects:** can be safely shared when immutability is genuine (including exposed sub-parts). Do not try to copy every String or immutable value object merely to make every identity distinct.
- **Complex graphs:** with circular references, references shared across multiple fields, or resource-managing objects (files, sockets, threads), “full deep copy” needs a clear definition. Some components must remain shared or cannot reasonably be copied; design the API and tests around the ownership contract.

Example of limiting leaks through a getter: instead of returning an internal mutable List directly, you can return **List.copyOf(internalList)** if elements are safe to share. For mutable elements, copy each element or provide a truly read-only interface per the contract.

## 8. Common Mistakes When Concluding a “Copy Is Independent”

1. **Only checking copy != original:** false conclusion because the outermost objects differ while mutable branches may share references.
2. **Only checking equals():** **equals()** answers value equality as defined by the class, not whether two object graphs are independent. Two copies can have `equals()` return true right after copying and still be independent.
3. **Only reassigning a field on copy:** changing an individual reference does not test sharing of child objects. You must mutate *inside* the mutable child object.
4. **Only testing the copy → original direction:** may miss update paths through the original or getters; test both directions when the contract requires it.
5. **Using an aliased snapshot:** for example **var before = original.address;** then reading **before.city** after mutation is not saving the initial value. Save the String city or create an independent snapshot.
6. **Confusing an unmodifiable collection with immutable elements:** a List disallowing add/remove can still hold mutable Address objects and share those Address instances with the original.
7. **Skipping indirect access paths:** setters, getters, array elements, Map values, and deep sub-branches can still mutate shared state.
8. **Relying on regular assert statements without enabling -ea:** Java ignores assert statements if assertions are disabled. Use JUnit assertions or always-active checks like **require(...)** in the example.
9. **Forgetting the hashCode/equals contract with mutable objects:** mutating fields participating in equals/hashCode while the object is a HashMap key or HashSet element can make lookups behave unexpectedly. This is an additional reason to design copies and immutability carefully; it is not a replacement test for independence.

## 9. Result Evaluation Checklist

A copy-independence test should only conclude **PASS for the tested scope** when:

- The copy is produced by the exact mechanism used in production and the outermost object has an identity matching the contract.
- Mutable branches needing separation have the right identity relationships; if sharing exists, it is permitted sharing and causes no contract-violating state effects.
- Directly mutating each required group of mutable state on the copy does not change the corresponding state of the original.
- Mutating the original does not change the corresponding part of the copy.
- Critical cases such as collections with mutable elements, null, empty data, and multi-level nesting are covered according to real structure; expected values are stored independently.
- Observed assertion results can fail when the copy code is broken; tests genuinely detect unintended shallow sharing.

**Conclusion:** To answer “does mutating a copy affect the original?”, **act on the copied mutable state, check original state before/after, and test the reverse direction too**. Checking identity helps pinpoint the cause, while behavioral testing and the ownership contract determine whether the copy is independent as required.
