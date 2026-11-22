# Testing Different Implementations of the Same Interface in Java

## 1. The Problem to Solve

In object-oriented programming, an **interface** may have multiple implementations. For example, an integer-set interface might be implemented using HashSet, TreeSet, or a custom data structure. These classes use different algorithms, but callers must observe **the same promised behavior** through the interface.

If each class has a completely separate test suite, it is easy to omit a case for one implementation or accidentally accept conflicting semantics. **Contract testing** addresses this by defining a shared behavioral test suite and running it unchanged against every implementation.

Lesson objectives:
- Distinguish **observable contracts** from internal implementation details.
- Write shared tests using a **factory** that creates implementations.
- Test state, return values, boundary cases, and independence between objects.
- Recognize where implementation-specific tests are needed in addition to the common contract suite.

## 2. Define the Contract Before Writing Tests

We define an IntSet interface that stores integers without duplicates. The contract is defined at the interface level, so HashIntSet and TreeIntSet must both comply.

| Operation | Testable Shared Contract |
| --- | --- |
| new IntSet | Initially empty; size() = 0. |
| add(x) | Returns true for a newly added element, false if x already exists; duplicate adds do not increase size. |
| contains(x) | Reports whether x is currently present without changing state. |
| remove(x) | Returns true if x was removed, false if not found; updates size correctly. |
| size() | Always equals the count of **distinct** elements and is never negative. |
| Value domain | Supports every int value, including negatives, 0, MIN_VALUE, and MAX_VALUE. |
| Instance independence | Operations on one object do not affect another newly created object. |

**Do not add** iteration order, tree/hash-table choice, execution time, or memory details to this contract because the interface does not promise them. Do not assert unpromised properties.

Testing flow:

~~~mermaid
flowchart TD
  A["Hợp đồng IntSet"] --> B["Bộ contract test JUnit 5"]
  B --> C["Factory: HashIntSet"]
  B --> D["Factory: TreeIntSet"]
  C --> E["Cùng các trường hợp kiểm thử"]
  D --> E
  E --> F{"Mọi implementation đều đạt?"}
  F -->|Có| G["Phù hợp với hợp đồng đã kiểm"]
  F -->|Không| H["Xác định implementation và ca vi phạm"]
~~~

## 3. Runnable Example: Java 17 + Maven + JUnit 5

Project structure:

~~~text
oop-contract-test/
├── pom.xml
└── src/
    ├── main/java/example/IntSet.java
    └── test/java/example/IntSetContractTest.java
~~~

### 3.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>oop-contract-test</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.11.4</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 3.2. src/main/java/example/IntSet.java

~~~java
package example;

import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

/**
 * Tập hợp các giá trị int phân biệt.
 * Mỗi đối tượng mới phải rỗng; mọi giá trị int đều hợp lệ.
 */
public interface IntSet {
    /** true chỉ khi giá trị được thêm mới. */
    boolean add(int value);

    /** Không làm thay đổi tập hợp. */
    boolean contains(int value);

    /** true chỉ khi phần tử có tồn tại và đã bị xóa. */
    boolean remove(int value);

    /** Số phần tử phân biệt hiện đang có. */
    int size();
}

final class HashIntSet implements IntSet {
    private final Set<Integer> values = new HashSet<>();

    @Override
    public boolean add(int value) {
        return values.add(value);
    }

    @Override
    public boolean contains(int value) {
        return values.contains(value);
    }

    @Override
    public boolean remove(int value) {
        return values.remove(value);
    }

    @Override
    public int size() {
        return values.size();
    }
}

final class TreeIntSet implements IntSet {
    private final Set<Integer> values = new TreeSet<>();

    @Override
    public boolean add(int value) {
        return values.add(value);
    }

    @Override
    public boolean contains(int value) {
        return values.contains(value);
    }

    @Override
    public boolean remove(int value) {
        return values.remove(value);
    }

    @Override
    public int size() {
        return values.size();
    }
}
~~~

To keep the example compact and compilable from one file, both concrete classes here are package-private (not declared public). In real applications, each could be moved to its own file.

### 3.3. src/test/java/example/IntSetContractTest.java

~~~java
package example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.function.Supplier;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class IntSetContractTest {

    // Mỗi test nhận một nhà máy tạo đối tượng mới.
    static Stream<Arguments> variants() {
        return Stream.of(
            Arguments.of("HashIntSet", (Supplier<IntSet>) HashIntSet::new),
            Arguments.of("TreeIntSet", (Supplier<IntSet>) TreeIntSet::new)
        );
    }

    @ParameterizedTest(name = "{0}: tap moi phai rong")
    @MethodSource("variants")
    void initiallyEmpty(String name, Supplier<IntSet> factory) {
        IntSet set = factory.get();

        assertEquals(0, set.size());
        assertFalse(set.contains(5));
        assertFalse(set.remove(5));
        assertEquals(0, set.size());
    }

    @ParameterizedTest(name = "{0}: them trung khong tang size")
    @MethodSource("variants")
    void addIsIdempotent(String name, Supplier<IntSet> factory) {
        IntSet set = factory.get();

        assertTrue(set.add(7));
        assertTrue(set.contains(7));
        assertEquals(1, set.size());

        assertFalse(set.add(7));
        assertEquals(1, set.size());
    }

    @ParameterizedTest(name = "{0}: xoa va them lai")
    @MethodSource("variants")
    void removeAndReAdd(String name, Supplier<IntSet> factory) {
        IntSet set = factory.get();

        assertTrue(set.add(10));
        assertTrue(set.add(20));
        assertTrue(set.remove(10));
        assertFalse(set.contains(10));
        assertTrue(set.contains(20));
        assertEquals(1, set.size());

        assertFalse(set.remove(10));
        assertTrue(set.add(10));
        assertEquals(2, set.size());
    }

    @ParameterizedTest(name = "{0}: gia tri bien va so am")
    @MethodSource("variants")
    void acceptsAllIntValues(String name, Supplier<IntSet> factory) {
        IntSet set = factory.get();
        int[] inputs = {
            Integer.MIN_VALUE, -1, 0, Integer.MAX_VALUE
        };

        for (int x : inputs) {
            assertTrue(set.add(x));
            assertTrue(set.contains(x));
        }
        assertEquals(inputs.length, set.size());

        for (int x : inputs) {
            assertFalse(set.add(x));
        }
        assertEquals(inputs.length, set.size());
    }

    @ParameterizedTest(name = "{0}: cac doi tuong doc lap")
    @MethodSource("variants")
    void independentInstances(String name, Supplier<IntSet> factory) {
        IntSet first = factory.get();
        IntSet second = factory.get();

        assertTrue(first.add(42));
        assertTrue(first.contains(42));
        assertFalse(second.contains(42));
        assertEquals(0, second.size());
    }
}
~~~

How the tests run:
1. The variants() method enumerates **implementation names + Suppliers**.
2. JUnit 5 invokes **each @ParameterizedTest method once per data row** from @MethodSource.
3. Each invocation calls factory.get() to create **a fresh object**, preventing earlier tests from contaminating later ones.
4. The same 5 cases run against 2 implementations, for **10 expected test invocations**. The implementation name appears in failure output.

Run from the directory containing pom.xml:

~~~bash
mvn test
~~~

With the classes above, Maven Surefire should complete successfully with 10 passing test invocations. If an implementation violates the contract, JUnit identifies the failing case and variant.

## 4. Why Is a Shared Test Suite Valuable?

Suppose a faulty implementation defines add as follows:

~~~java
@Override
public boolean add(int value) {
    values.add(value);
    return true; // Sai khi value đã tồn tại!
}
~~~

The addIsIdempotent test fails on the second add(7), even though size remains 1. This violates the **return-value contract**, not the storage structure.

Another defect is using a shared static variable to store elements across instances. The independentInstances test detects interference between two objects. Testing each operation in isolation might miss this behavior.

| Scenario | Checking Only the Final Result | Better Contract Testing |
| --- | --- | --- |
| Adding the same value twice | size may still be 1. | Assert both boolean results and size. |
| Removing a missing element | An incorrect return value may go unnoticed. | Require false and unchanged state. |
| Adding MIN_VALUE | Easily forgotten in ordinary tests. | Cover the declared int domain. |
| Two instances exist simultaneously | Easy to miss when only one object is created. | Ensure no unpromised shared state. |

## 5. Contract Tests Versus Implementation-Specific Tests

**Contract tests** protect requirements common to every implementation: valid inputs, outputs, promised exceptions, state invariants, and repeated-call behavior.

**Implementation-specific tests** verify requirements unique to an implementation. A database-backed class may need real connection, transaction, rollback, and mapping tests. A cache may require TTL, eviction, and thread-safety tests **when these are class requirements**.

**Integration tests** use real system configuration to verify adapters interacting with external resources. Passing contract tests against a fake or in-memory implementation cannot establish that a JDBC implementation works with the real database.

For example, if Repository has InMemoryRepository and JdbcRepository implementations, the contract suite can be reused through factories:

~~~java
// Ý tưởng tổ chức, không phải mã độc lập của dự án IntSet.
abstract class RepositoryContractTest {
    protected abstract Repository newRepository();

    // Các @Test chỉ gọi hàm trên Repository,
    // không phụ thuộc InMemoryRepository hay JdbcRepository.
}
~~~

Ensure resource setup/cleanup (schema creation, seed data, rollback, or per-test deletion) and prevent parallel tests from conflicting over the same data. Exercise real implementations in CI so a fake passing tests cannot hide different SQL behavior.

## 6. Principles for Writing Trustworthy Contracts

- **Specify behavior first:** interface documentation/Javadoc and business requirements define correctness. Two implementations returning the same wrong result do not make that result correct.
- **Test from the caller's perspective:** invoke public operations through an interface-typed variable; avoid reading private fields or downcasting merely to assert internal structure.
- **Keep tests independent:** create fresh fixtures per case; control clocks, random seeds, test order, and external resources when relevant.
- **Test operation sequences:** add → find → duplicate add → remove → add again often catches state bugs that single-operation tests miss.
- **Cover partitions and boundaries:** empty, present/absent, duplicate, negative, MIN_VALUE/MAX_VALUE; for interfaces accepting references, specify null handling too.
- **Assert exceptions deliberately:** if the contract requires IllegalArgumentException for invalid input, use assertThrows for *every* implementation; do not infer error behavior from one concrete class.
- **Avoid asserting unpromised details:** do not compare HashSet iteration order to TreeSet; if ordering is a requirement, document it on the interface and test that requirement.
- **Do not overuse mocks:** mocks help isolate a dependency while testing its consumer, but cannot replace verification that actual implementations satisfy the contract.
- **A new implementation belongs in the same suite:** for example, add LinkedHashIntSet and one Arguments.of entry to variants(); do not duplicate the five test methods.
- **Understand limitations:** a shared suite establishes that selected cases pass, not that every input and every nonfunctional property is correct.

## 7. Self-Practice

1. Add LinkedHashIntSet using LinkedHashSet<Integer> and declare implements IntSet. Register its factory in variants() and rerun; expect 15 test invocations.
2. Deliberately change remove() to always return false, run the tests to identify the detecting cases, then restore the correct code.
3. Add a contract test for add(3), add(4), remove(3), add(3), checking size and contains at each step.
4. If you add values() returning Collection<Integer>, explicitly decide whether ordering is promised. Write tests for the stated contract, not accidental data-structure behavior.

**Completion criterion:** Every class declaring implements IntSet should run the same test suite, and every failure should identify the violated contractual behavior.
