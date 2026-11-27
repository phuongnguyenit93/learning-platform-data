# Combining `And`, `Or`, and Limitations of Grouped Conditions in Spring Data JPA

When writing **derived query methods**, Spring Data JPA lets you join multiple conditions using `And` and `Or`. A common pitfall is that method names **do not have parentheses syntax to explicitly choose how conditions are grouped**. Therefore, you must understand the exact condition tree Spring Data builds, especially when a business requirement contains both “and” and “or”.

## 1. How do `And` and `Or` work?

In a repository such as `JpaRepository<Customer, Long>`, the part after `By` in `findBy...` describes conditions on entity properties. Example:

```java
List<Customer> findByNameAndStatus(String name, Status status);
List<Customer> findByNameOrEmail(String name, String email);
```

These two methods correspond logically to:

```text
name = ?1 AND status = ?2
name = ?1 OR  email  = ?2
```

Spring Data Commons uses the `PartTree` parser: it splits the expression by `Or` into branches, then splits each branch by `And`. Consequently, **`And` has higher precedence than `Or`** in derived queries. You can view the general form as:

```text
AAndBOrCAndDOrE
        ↓
(A AND B) OR (C AND D) OR E
```

This is the method-name parsing rule, regardless of how the author *intended* to group the conditions.

| Method name (part after `By`) | Parsed logical condition |
| --- | --- |
| `NameAndStatus` | `name AND status` |
| `NameOrEmail` | `name OR email` |
| `NameAndStatusOrEmail` | `(name AND status) OR email` |
| `NameOrEmailAndStatus` | `name OR (email AND status)` |
| `NameAndStatusOrEmailAndStatus` | `(name AND status) OR (email AND status)` |

Note: the table describes **filter logic**; `?1`, `?2` illustrate positional parameters, not that method names generate arbitrary parentheses.

## 2. Real bug: wanting `(A OR B) AND C` but writing `A OR (B AND C)`

Suppose the `Customer` entity has these properties:

- `name`: customer name (`String`).
- `email`: email address (`String`).
- `status`: status (`Status`, e.g., `ACTIVE` or `SUSPENDED`).

Requirement: **Find customers whose name *or* email matches the input, and whose status must equal `ACTIVE`.**

The required expression is:

```text
(name = :name OR email = :email)
AND status = :status
```

The following method **does not satisfy** the requirement:

```java
List<Customer> findByNameOrEmailAndStatus(
        String name, String email, Status status);
```

Spring Data interprets it as:

```text
name = ?1 OR (email = ?2 AND status = ?3)
```

Because the `name = ?1` branch stands outside the status condition, a customer whose name matches can still be returned even when `status` is `SUSPENDED`.

Example with arguments `name = "Lan"`, `email = "lan@example.com"`, `status = ACTIVE`:

| Record | Matches name (A) | Matches email (B) | Status ACTIVE (C) | `A OR (B AND C)` | `(A OR B) AND C` |
| --- | --- | --- | --- | --- | --- |
| Lan, other@example.com, SUSPENDED | True | False | False | **True** | **False** |
| Lan, other@example.com, ACTIVE | True | False | True | True | True |
| Minh, lan@example.com, ACTIVE | False | True | True | True | True |
| Minh, other@example.com, ACTIVE | False | False | True | False | False |

The first row is the key test case: the two groupings return different results.

## 3. Expressing an OR group via method name: distributing the AND condition

In Boolean algebra, we have:

```text
(A OR B) AND C
≡ (A AND C) OR (B AND C)
```

Thus, you can express the requirement above by repeating `status` in **both branches** of the method name:

```java
List<Customer> findByNameAndStatusOrEmailAndStatus(
        String name,
        Status statusForName,
        String email,
        Status statusForEmail);
```

Illustrative call:

```java
repository.findByNameAndStatusOrEmailAndStatus(
        "Lan",
        Status.ACTIVE,
        "lan@example.com",
        Status.ACTIVE);
```

This method has the logic:

```text
(name = ?1 AND status = ?2)
OR
(email = ?3 AND status = ?4)
```

When passing the same status for `?2` and `?4`, the expression is equivalent to `(name OR email) AND status`. The two status parameters **are two separate positions**: if different values are accidentally passed, the query meaning changes.

Distribution works when there are only a few short branches. With multiple nested groups, method names quickly become long, repeat properties, and become hard to verify.

## 4. Method name limitation: no arbitrary grouping parentheses

You cannot insert `(` and `)` into a derived query method name to change precedence; for instance, there is no supported syntax like:

```text
findBy(NameOrEmail)AndStatus(...)
```

This is **not** a valid derived-query method for expressing the group `(name OR email)`.

Nor can you arbitrarily rearrange `And` and `Or` expecting Spring Data to infer your intent. For example:

```text
AOrBAndC       → A OR (B AND C)
AAndBOrC       → (A AND B) OR C
AAndCOrBAndC   → (A AND C) OR (B AND C)
```

However, “no parentheses” **does not mean every grouped expression is impossible**. Some can be rewritten as an *OR of AND groups* (disjunctive normal form, DNF) using the distributive law. For example:

```text
(A OR B) AND (C OR D)
≡ (A AND C) OR (A AND D) OR (B AND C) OR (B AND D)
```

Logically it can be represented, but the number of branches and repeated parameters grows rapidly. The more `OR` groups combined with `AND`, the harder the method name becomes to read, maintain, and verify without missing a combination.

Rule of thumb: for short, clear filters, use derived queries; when complex grouping or multiple optional conditions are needed, switch to declared queries or query-building APIs.

## 5. When explicit parentheses are needed: use `@Query` with JPQL

For “(name or email) and status”, writing a query with parentheses is usually much clearer. The snippet below is part of a project that already has entity `Customer`, enum `Status`, and Spring Data JPA dependencies; it is not a standalone Java program:

```java
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends JpaRepository<Customer, Long> {

    @Query("""
        select c
        from Customer c
        where (c.name = :name or c.email = :email)
          and c.status = :status
        """)
    List<Customer> searchContactsWithStatus(
            @Param("name") String name,
            @Param("email") String email,
            @Param("status") Status status);
}
```

Key points:

1. `Customer` in JPQL is the **entity name**; `name`, `email`, and `status` are **Java property names** of the entity, not necessarily SQL table/column names.
2. Parentheses around `c.name = :name or c.email = :email` capture the exact business condition grouping.
3. `@Param` binds each Java parameter to a named parameter in JPQL, so `status` does not need to be passed twice.
4. `@Query` declares the query directly on the method; it does not rely on splitting `And`/`Or` in the method name to construct the predicate.

The example above assumes all search parameters are non-null. If `null` is allowed or you want to “skip a filter when omitted”, design each parameter's semantics explicitly; do not assume `= :param` in JPQL behaves identically to passing `null` into a derived query.

## 6. Dynamic filters and multiple groups: use JPA `Specification`

When conditions vary by search screen input, `Specification` lets you build a Boolean tree directly via the Criteria API, with `and` and `or` grouped explicitly:

```java
import org.springframework.data.jpa.domain.Specification;

public final class CustomerSpecs {
    private CustomerSpecs() {}

    public static Specification<Customer> contactAndStatus(
            String name, String email, Status status) {
        return (root, query, cb) -> cb.and(
                cb.or(
                        cb.equal(root.get("name"), name),
                        cb.equal(root.get("email"), email)),
                cb.equal(root.get("status"), status));
    }
}
```

A repository that runs `Specification` needs to extend `JpaSpecificationExecutor<Customer>`:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface CustomerSearchRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
```

Once the repository bean is available, you can call:

```java
var spec = CustomerSpecs.contactAndStatus(
        "Lan", "lan@example.com", Status.ACTIVE);
var customers = customerSearchRepository.findAll(spec);
```

`cb.or(...)` is grouped inside `cb.and(...)`, matching `(A OR B) AND C`. These are **integration code snippets** meant to be placed in appropriate Java files of a Spring Data JPA application alongside the entity and dependencies. For filters with optional values, **only add predicates for criteria that are actually provided**; the example above illustrates when all three parameters are present.

If multiple `OR` values apply to the **same property**, consider the `In` keyword, such as `findByStatusIn(Collection<Status> statuses)`, instead of writing `StatusOrStatusOr...`. `In` does not replace grouping conditions across **different properties** like `name` and `email`.

## 7. Self-verifying precedence with Java 17

The following standalone program does not connect to JPA; it uses Java's Boolean operators to demonstrate the two logical expressions represented by the derived query and the business requirement.

Save to `AndOrDemo.java`:

```java
public class AndOrDemo {
    record Customer(String name, String email, String status) {}

    public static void main(String[] args) {
        Customer customer = new Customer(
                "Lan", "other@example.com", "SUSPENDED");

        String name = "Lan";
        String email = "lan@example.com";
        String status = "ACTIVE";

        boolean derived = customer.name().equals(name)
                || customer.email().equals(email)
                   && customer.status().equals(status);

        boolean intended = (customer.name().equals(name)
                || customer.email().equals(email))
                && customer.status().equals(status);

        System.out.println("Derived: " + derived);
        System.out.println("Intended: " + intended);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac AndOrDemo.java
java AndOrDemo
```

Expected output:

```text
Derived: true
Intended: false
```

In Java, `&&` has higher precedence than `||`, so the two calculations accurately mirror the two logic trees. This is a standalone logic check and **does not replace** repository integration tests against real data and the target database.

## 8. How to verify repositories to avoid business-logic bugs

Before finalizing a method containing both `And` and `Or`:

1. Write down the business condition first, **with explicit parentheses**, e.g. `(A OR B) AND C`.
2. Rewrite the method name into the form the parser actually builds: **`OR` branches**, each consisting of **`AND` conditions**.
3. Compare the two expressions with counterexample cases; specifically test `A = true, B = false, C = false` to catch `A OR (B AND C)` bugs.
4. If using distribution, verify **parameter order** and the values of every repeated parameter.
5. Write Spring Data JPA integration tests (such as `@DataJpaTest`) with a record matching name but wrong status, a record matching email and right status, and a non-matching record; verify the actual result set.
6. If the query grows long, has multiple `OR` groups, or changes often, switch to `@Query` or `Specification` to express intent clearly.

**Common mistakes:** assuming `findByNameOrEmailAndStatus` means `(name OR email) AND status`; thinking parentheses can be placed directly in method names; missing a branch when distributing; repeating the same property but passing different arguments; or testing only on data where every customer has `ACTIVE` status so the precedence bug goes unnoticed.

## 9. Takeaways

- In Spring Data JPA derived queries, `And` binds tighter than `Or`: `AOrBAndC` is parsed as `A OR (B AND C)`.
- Method names do not support parentheses syntax to **directly** specify arbitrary Boolean grouping.
- `(A OR B) AND C` can be converted to `(A AND C) OR (B AND C)`, but requires repeating conditions and, when parameterized, repeating arguments.
- For long conditions, complex grouping, or dynamic filtering, `@Query`/JPQL and `Specification` express intent accurately and are easier to test.

### References

- Spring Data JPA — Query Methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data — Repository Query Keywords: https://docs.spring.io/spring-data/jpa/reference/repositories/query-keywords-reference.html
- Spring Data Commons — `PartTree` API and `OrPart` structure: https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/parser/PartTree.html