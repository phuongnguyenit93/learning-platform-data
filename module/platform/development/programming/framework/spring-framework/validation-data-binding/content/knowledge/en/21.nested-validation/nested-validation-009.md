# Cyclic Graphs and Traversal Scope in Jakarta Bean Validation

## 1. Real-World Scenario: An Object Graph Is Not Always a Tree

Objects in a Spring application often reference one another in multiple directions. `Order` references `Customer`; `Customer` has a list of `Order`s; an employee has a `manager`, while the manager has a list of `reports` pointing back. Two fields `billingAddress` and `shippingAddress` can also reference **the exact same instance**. Those relationships form an **object graph**, sometimes containing cycles.

Jakarta Bean Validation uses `@Valid` to **cascade** validation from a root bean to referenced beans. Many developers worry that a cycle like `A → B → A` will cause a stack overflow, or assume the engine marks every visited instance globally and never validates it again. Neither understanding is quite right:

- A compliant provider must **break cycles along the current navigation path** so cascading terminates.
- The same instance can be **reached via different branches**; those branches can produce violations with different **property paths**.
- How far the engine traverses also depends on `@Valid`, `null`, constraint groups, container value extractors, and `TraversableResolver`.

Lesson goal: understand traversal rules, predict errors on cyclic graphs or shared objects, build a Java 17 demo, and know how to adjust validation scope in Spring MVC/JPA.

| Term | Meaning |
| --- | --- |
| **Root bean** | Object passed directly to `validator.validate(root)` |
| **Association** | Field/getter/reference, e.g., `order.customer` |
| **Cascaded validation** | Traversing from parent object to child across a `@Valid`-marked relationship |
| **Navigation path** | A chain of `@Valid` relationships from root to the instance being examined |
| **Constraint violation** | Error result of a constraint; has `propertyPath`, message, root/leaf bean |
| **Property path** | Logical location leading to the error, e.g., `customer.address.street` |
| **Validation group** | Set of constraints to execute (`Default`, `Create`, `Publish`...) |

## 2. `@Valid` Defines Which Edges Are Traversed

Illustrative Java example:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

class Employee {
    @NotBlank
    String name;

    @Valid
    Employee manager;
}
```

This snippet is for explaining the field, not a complete executable file. When calling:

```java
Set<ConstraintViolation<Employee>> errors =
        validator.validate(employee);
```

the provider checks the `name` constraint on `employee` itself. If `manager` is non-null, it follows `@Valid` to `manager`; if `manager` also has a `manager` marked with `@Valid`, validation can continue.

**Boundary rules:**

1. The root is validated when calling `validate(root)`; **no `@Valid` annotation is needed on the root variable**.
2. `@Valid` requests descending through declared references/associations, not "validating every object reachable in the Java heap."
3. A field referencing a child but **missing `@Valid`** does not automatically trigger the child's constraints.
4. `@Valid` skips **null references**; to forbid null, also add `@NotNull`.
5. `@Valid` can apply to collections, arrays, and **type arguments** `List<@Valid Child>`, `Map<K,@Valid Child>` when matching value extractors exist.
6. Constraints are selected according to the active **validation group**; a constraint outside the active group will not produce an error just because `@Valid` is present.
7. When cascading to an actual subclass instance, the provider uses constraint metadata of that runtime object type.

Boundary example:

```java
class Department {
    @Valid Employee lead; // Validates inside lead

    Employee reviewer;    // Does not automatically descend into reviewer
}
```

If `reviewer.name=""` and `lead.name="Mai"`, `validator.validate(department)` will not produce an error for `reviewer` because that field lacks `@Valid`. To validate `reviewer`'s fields, declare cascading on the **appropriate edge**.

## 3. Why Doesn't a Cycle `A → B → A` Run Infinitely?

Consider the graph:

```text
        root: A (name = "Alice")
                |
            @Valid next
                |
                v
             B (name = "")
                |
            @Valid next
                |
                v
             A (same root instance)
```

The traversal path from A has these steps:

1. Check constraints on A.
2. Traverse `A.next` to B.
3. Check constraints on B (e.g., `@NotBlank` on `name` detects the empty string).
4. Prepare to cascade via `B.next` back to **the exact same instance A**.
5. Because A is already on the **navigation path of this branch**, the provider **skips the cascade back to A**.

This rule is stated explicitly in Jakarta Bean Validation 3.0, section *Object graph validation*: a provider must skip cascading to an instance **already validated along the current navigation path**, preventing infinite loops. This still allows the engine to check B's constraints before encountering the back-edge.

Do not mistakenly think Spring needs a special flag configured to stop recursion: cycle avoidance belongs to the **Jakarta Validation specification**, which compliant providers must obey. Hibernate Validator's `fail-fast` is a separate option for stopping after the first error, not a required tool for preventing object graph cycles.

### Identity Matters More Than `equals()`

Two distinct instances with the same `id` or where `equals()` returns `true` **are not the same instance**. The cycle rule here refers to **object identity**, not value equality. When building JPA models, an entity proxy and another entity instance with the same database key can be two separate objects; do not infer cycle-breaking behavior from `id` alone.

## 4. Why Can a Shared Object Produce Multiple Errors?

The following graph **has no cycles along any individual branch**:

```text
                 Root
                /    \
           @Valid    @Valid
             left    right
               \      /
                Shared
            (name = "")
```

Suppose `Root.left == Root.right` (the same `Shared` instance), and `Shared.name` violates `@NotBlank`.

Different navigation paths:

```text
Root → left  → Shared
Root → right → Shared
```

Each path can produce a `ConstraintViolation` with a different property path:

```text
left.name
right.name
```

Both refer to the same object, yet they are **two distinct error locations in the data model from root**. If you only marked "Shared seen" in a *global* visited-set and skipped the second branch, you could lose paths that must be reported to the user.

The specification does not mandate re-executing the same constraint in every case: implementations may optimize, **as long as the correct set of violations is returned**. What must not be lost are the error paths required by the contract.

| Scenario | Expected Understanding |
| --- | --- |
| `A.next = B`, `B.next = A` | Cuts the back-edge to an instance already **on the current branch** |
| `Root.left = X`, `Root.right = X` | Two valid branches; can yield both `left.*` and `right.*` |
| Two children with equal values but separate instances | Not treated as the same node |
| `child = null` with `@Valid` only | No cascade, no null error reported |
| `@NotNull @Valid child = null` | `@NotNull` reports error, `@Valid` does not descend |
| Edge missing `@Valid` | Does not cross that edge to validate child |

**Do not use `ConstraintViolation.getLeafBean()` as a unique key** to deduplicate UI messages: two violations can share a leaf bean while having different `propertyPath`s. If display optimization is needed, decide by path and error code rather than arbitrarily discarding data.

## 5. Cycles with Lists, Arrays, Maps, and Nested Branches

Not just direct references — containers can also hold objects pointing back:

```java
class Team {
    java.util.List<@Valid Member> members;
}

class Member {
    @Valid Team team;
}
```

These are abbreviated illustrative classes; import `jakarta.validation.Valid` and add remaining model members for real use.

With `Team.members[0].team` pointing back to the original `Team` instance, the provider follows `Team → members[0] → Member` and then cuts the edge back to `Team` per the cycle-prevention rule.

If the same `Member` instance appears at two positions in a `List`, each index has its own navigation path. With a `Map`, two different keys pointing to the same value object also form two paths.

```java
class ContainerRequest {
    java.util.List<@Valid Member> members;

    java.util.Map<String, @Valid Member> byDepartment;
}
```

Illustration table:

| Structure | Possible Error Locations |
| --- | --- |
| `List<@Valid Member>` | `members[0].name`, `members[1].name` |
| `Map<String,@Valid Member>` | `byDepartment[sales].name`, `byDepartment[tech].name` |
| `Map<String,List<@Valid Member>>` | One branch through Map value, then through List element |
| `@Valid Member[]` | One branch for each object in the array |
| `Map<@Valid Key,@Valid Value>` | Cascading on **key** and **value** declared separately |

The strings above illustrate meaning and do not promise identical `toString()` output across all Jakarta providers. For Maps, the legacy style `@Valid Map<K,V>` usually cascades into **values**, not automatically into keys. When using type arguments, put `@Valid` in the right spot; avoid placing it on both the container and the type argument "just in case," as that can cause duplicate cascade declarations.

### Container Constraints vs. Cascading

- `@NotEmpty List<@Valid Child>` requires the list to be non-null/non-empty and cascades into **non-null** children, but does not forbid a null element.
- `List<@NotNull @Valid Child>` both forbids null elements and cascades into existing elements.
- `Map<@NotBlank String, @NotNull @Valid Child>` validates non-blank **keys**, non-null **values**, and constraints inside values.
- For custom generic wrappers, you may need to register a `ValueExtractor` so the provider knows how to extract elements; `@Valid` does not automatically turn an arbitrary wrapper into a supported container.

### Reading Paths with Indices and Keys

`ConstraintViolation.getPropertyPath()` returns `jakarta.validation.Path`, an iterable of `Path.Node`. A node can contain container element metadata:

```java
for (jakarta.validation.Path.Node node : violation.getPropertyPath()) {
    if (node.isInIterable()) {
        Integer index = node.getIndex();
        Object key = node.getKey();
        // index/key may be null depending on container/node.
    }
}
```

This snippet assumes a `violation` variable exists. For Lists/arrays, `index` is typically useful; for Maps, `key` is typically useful. If a REST response needs to indicate error locations, convert **structured path nodes** into an API format you control. Do not parse path strings with regex and treat that as an immutable wire protocol.

## 6. Standalone Java 17: Observing Recursion and Traversal Scope

The program uses Hibernate Validator 8 as the Jakarta Validation provider. We intentionally test six cases:

- Cycle `A → B → A`.
- Shared object across two fields.
- Missing `@Valid` at an intermediate level.
- Same instance at two List positions.
- Same instance under two Map keys.
- `validateProperty(...)` checks only the property, without cascading via `@Valid`.

Gradle project:

```text
graph-cycle-validation/
├── settings.gradle
├── build.gradle
└── src/main/java/GraphCycleDemo.java
```

**`settings.gradle`**:

```groovy
rootProject.name = 'graph-cycle-validation'
```

**`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.hibernate.validator:hibernate-validator:8.0.6.Final'
    implementation 'org.glassfish.expressly:expressly:5.0.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'GraphCycleDemo'
}
```

`hibernate-validator` provides the provider; `expressly` provides the Jakarta EL implementation for message interpolation. In Spring Boot projects, prefer `spring-boot-starter-validation` and Boot's BOM to select compatible versions.

**`src/main/java/GraphCycleDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;

public class GraphCycleDemo {

    static final class Node {
        @NotBlank
        private final String name;

        @Valid
        private Node next;

        Node(String name) {
            this.name = name;
        }

        Node link(Node next) {
            this.next = next;
            return this;
        }
    }

    static final class Pair {
        @Valid private final Node left;
        @Valid private final Node right;

        Pair(Node left, Node right) {
            this.left = left;
            this.right = right;
        }
    }

    static final class ListBox {
        private final List<@Valid Node> nodes;

        ListBox(List<Node> nodes) {
            this.nodes = nodes;
        }
    }

    static final class MapBox {
        private final Map<String, @Valid Node> nodes;

        MapBox(Map<String, Node> nodes) {
            this.nodes = nodes;
        }
    }

    static final class Leaf {
        @NotBlank private final String name;

        Leaf(String name) {
            this.name = name;
        }
    }

    static final class Middle {
        private final Leaf leaf; // Missing @Valid.

        Middle(Leaf leaf) {
            this.leaf = leaf;
        }
    }

    static final class StopRoot {
        @Valid private final Middle middle;

        StopRoot(Middle middle) {
            this.middle = middle;
        }
    }

    static void show(String label, Object root, Validator validator) {
        Set<ConstraintViolation<Object>> issues = validator.validate(root);
        System.out.println(label + ": " + issues.size());
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Node a = new Node("Alice");
            Node b = new Node("");
            a.link(b);
            b.link(a); // Create cycle: A -> B -> A.
            show("Cycle", a, validator);

            Node shared = new Node("");
            show("Shared", new Pair(shared, shared), validator);

            StopRoot stop = new StopRoot(new Middle(new Leaf("")));
            show("MissingCascade", stop, validator);

            show("List", new ListBox(List.of(shared, shared)), validator);

            show("Map", new MapBox(Map.of(
                    "billing", shared, "shipping", shared
            )), validator);

            System.out.println("Partial: "
                    + validator.validateProperty(a, "next").size());
        }
    }
}
```

Run with JDK 17+ and Gradle:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper: Linux/macOS `./gradlew run --quiet`; Windows `gradlew.bat run --quiet`.

**Expected standard output:**

```text
Cycle: 1
Shared: 2
MissingCascade: 0
List: 2
Map: 2
Partial: 0
```

Explanation:

1. `Cycle: 1`: A is valid, B has `name=""` violating `@NotBlank`; the back-edge from B to A is cut on the current branch.
2. `Shared: 2`: `left` and `right` point to the same `Node` with an empty name, forming **two distinct error paths**.
3. `MissingCascade: 0`: `StopRoot` cascades into `Middle`; `Middle.leaf` lacks `@Valid`, so `Leaf.name` is not checked.
4. `List: 2`: the same `shared` sits at index 0 and 1, each position yielding its own error path.
5. `Map: 2`: two Map keys point to the same `shared`; each value is cascaded.
6. `Partial: 0`: `Node.next` has only `@Valid` and no direct constraints on field `next`; `validateProperty(a,"next")` **does not cascade** into B.

The demo prints only violation counts without assuming `Set<ConstraintViolation<?>>` order. The provider may write startup logs to stderr; stdout above consists solely of the `System.out.println` lines.

To inspect paths, you can modify `show` with the snippet below (runs **inside the method**, not a standalone class):

```java
issues.stream()
        .map(v -> v.getPropertyPath().toString())
        .sorted()
        .forEach(System.out::println);
```

When inspecting `Shared`, you will see paths like `left.name` and `right.name`. Error paths in Lists/Maps may have different indices/keys and node names depending on the provider. In important tests, inspect node structure or use a pinned provider.

## 7. Other Traversal Boundaries to Understand

### 7.1. `validate()` vs. `validateProperty()` and `validateValue()`

```java
validator.validate(order);
validator.validateProperty(order, "customer");
validator.validateValue(Order.class, "customer", customer);
```

These are illustrative calls assuming matching variables/types exist. `validate(order)` evaluates the root and can cascade via `@Valid`. `validateProperty` and `validateValue` only evaluate **direct constraints on the property**, **without honoring `@Valid` to cascade into child beans**. Thus the result can be empty even when a child below is invalid.

Per the Jakarta Validation API, the property name passed to `validateProperty`/`validateValue` is a direct property name; do not assume a portable implementation will accept a multi-level path string like `"customer.address.street"`.

### 7.2. Validation Groups

By default, `validate(root)` checks the `jakarta.validation.groups.Default` group. If you call:

```java
validator.validate(order, PublishChecks.class);
```

while child constraints are declared only in `Default`, getting zero `PublishChecks` violations **is not due to cycle prevention**. `@Valid` propagates the active group into the child unless group conversion is configured:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

class Order {
    @Valid
    @ConvertGroup(from = Default.class, to = PublishChecks.class)
    Customer customer;
}
```

This is an illustrative declaration requiring `PublishChecks` and `Customer` to be defined. Group conversion rules only affect the associated `@Valid` edge. A group sequence can prevent a subsequent group from running if an earlier group fails.

**Do not confuse object graph cycles with group sequence cycles**: an invalid group cycle can throw `GroupDefinitionException`; do not use object cycle-prevention rules to assume every group configuration is valid.

### 7.3. `TraversableResolver`

The `jakarta.validation.TraversableResolver` SPI determines whether a property can be accessed and cascaded:

- `isReachable(...)` controls readability for validation/cascading.
- `isCascadable(...)` controls traversing a `@Valid` relationship once reachable.

In JPA environments, checking a `LAZY` association can trigger unintended data fetching. Providers and integration layers may use a resolver to limit access. Therefore, `@Valid` **does not guarantee every JPA association is accessed or automatically fetched**; test with your actual provider, transaction/persistence context, and loaded state.

### 7.4. Root, Null, and Direct Constraint Groups

A root bean is validated whenever `validate(root)` is called, regardless of any cascade relationships. Root constraints are evaluated if they belong to the active group and the property is reachable. `@Valid` on a relationship **does not report null errors by itself**, nor does it force a List to have elements. Use `@NotNull`, `@NotEmpty`, and `@Size` at the right level to enforce those requirements.

## 8. Spring MVC Integration: What Limits Should You Know?

Spring Framework 6+/Spring Boot 3+ uses the Jakarta namespace. In applications with a Jakarta provider, Spring uses `LocalValidatorFactoryBean` to integrate Bean Validation into `DataBinder`/Spring MVC.

DTO and controller example (public records need matching-named Java files; these are **integration snippets**, not a full project):

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

public record AddressInput(@NotBlank String city) {}

public record CustomerInput(
        @NotBlank String name,
        @Valid AddressInput address
) {}
```

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CustomerController {

    @PostMapping("/customers")
    public ResponseEntity<String> create(
            @Valid @RequestBody CustomerInput input) {
        return ResponseEntity.ok("accepted");
    }
}
```

Example body:

```json
{"name":"Mai","address":{"city":""}}
```

Once Jackson deserialization succeeds, `@Valid` on `CustomerInput` and on `address` lets the provider validate `AddressInput.city`, detecting the `@NotBlank` violation. With default handling, Spring MVC typically returns HTTP 400 if command object validation fails. Exact error rendering depends on exception handlers and configuration.

**JSON does not preserve Java cycle identity automatically**: `A → B → A` cycles usually appear after assembling models/entities or from JPA relationships. Bean Validation's cycle avoidance **does not fix** Jackson serializing objects with cyclic references. If JSON serialization hits a cycle, handle it with DTOs, identity/reference mapping, or appropriate Jackson configuration.

Also, a direct `@RequestBody List<Item>` endpoint has different validation semantics than a **wrapper command object** containing `List<@Valid Item>`; do not assume putting `@Valid` on a collection argument gives identical results to a wrapper DTO in all MVC versions. Test actual endpoint signatures. With `@ModelAttribute` and `BindingResult`, conversion/binding errors can differ from constraint errors.

## 9. Performance and Choosing Validation Scope

Cycle prevention does not mean validation has constant cost. A branching graph can contain a shared child along hundreds of paths; the provider still has to preserve the proper set of violation paths. Considerations:

- **High fan-out:** many containers/`@Valid` relationships multiply traversal paths and error counts.
- **Deep graphs:** deep cascading increases traversal overhead.
- **Expensive constraints:** heavy regexes, DB queries, or network calls inside custom constraints cause latency; avoid repeated I/O inside validators whenever possible.
- **JPA lazy loading:** accessing relationships can trigger fetches depending on resolver/provider. Never turn on `FetchType.EAGER` just to make validation "thorough."
- **A bean appearing in multiple branches:** may be validated across multiple contexts/paths; do not rely on "each instance is only validated once."
- **Hibernate Validator fail-fast:** is a provider-specific option that may stop after one violation without guaranteeing which error wins. It is not a substitute for intentional cascade scoping.

Good API design typically **validates a DTO scoped to the use case** rather than cascading across every domain/JPA entity relationship. Put `@Valid` on the exact edges that need checking, group constraints meaningfully, and test realistically on bidirectional/shared-reference data.

If the application uses a custom `ConstraintValidator` that inspects cyclic fields with hand-written traversal logic, avoid infinite recursion inside **your custom code**; the provider's cycle-breaking rule applies to its `@Valid` cascading mechanism, not arbitrary loops in custom Java logic.

## 10. Test Matrix and Common Misconceptions

### Minimum Test Table

| Test | Expectation |
| --- | --- |
| A → B → A, B invalid | Detects B, does not loop infinitely |
| `Root.left` and `Root.right` point to same invalid child | Two distinct error locations |
| Two distinct child instances with equal `equals()` | Not treated as a cycle by object identity |
| `@Valid child = null` | Skips cascade; use `@NotNull` to forbid null |
| One intermediate edge missing `@Valid` | Cascading stops at that edge |
| Same child at 2 List indices | Can produce two paths, one per index |
| Same value under 2 Map keys | Can produce two paths by key |
| `validateProperty(root,"child")` with only `@Valid` | Does not descend into child |
| Child constraint only in Publish, called with Default | Publish constraint does not run automatically |
| `@ConvertGroup` configuration | Group converts on that exact edge |
| Resolver disallows `isCascadable` | Does not traverse that association |
| Unloaded JPA lazy association | Test behavior with real provider/resolver |
| Wide and deep graph | Measure latency, error count, and data loading |

### Misconceptions to Avoid

1. **"Every object is validated only once across the whole graph."** False: the same instance can produce errors across multiple navigation paths.
2. **"Two objects equal via `equals()` form a cycle."** False: the rule is about **instance** identity.
3. **"`@Valid` forbids null."** False: add `@NotNull` if needed.
4. **"References are always cascaded."** False: the relationship must be marked and allowed by the resolver.
5. **"`validateProperty` descends along `@Valid`."** False: it is partial validation and does not cascade.
6. **"Deduplicating errors by instance is enough."** No: it easily drops path locations.
7. **"Path strings are standardized across all providers."** Use `Path.Node` when a stable protocol is needed.
8. **"Fail-fast prevents cascade stack overflows."** Jakarta providers already must prevent cycles; fail-fast only changes the error-reporting strategy.
9. **"All groups run as long as `@Valid` is present."** No: groups, group sequences, and conversions determine which constraints apply.
10. **"Spring MVC/Jackson shares the same traversal pass as Jakarta."** No: binding, serialization, and validation are separate pipelines.
11. **"Cyclic graphs require deleting bidirectional relationships."** Not necessarily; cycle cutting is built into Jakarta, while DTO/use-case scoping is a design choice.
12. **"Custom constraints can safely query the DB on every edge."** That causes N+1/latency problems; weigh the cost carefully.

### Self-Check

1. Why doesn't `A.next=B`, `B.next=A` cause infinite recursion? **A is already on the navigation path of the returning branch, so that cascade is skipped.**
2. Why can the same `Child` instance under `left` and `right` produce two errors? **Because the errors belong to two different property paths.**
3. If `@Valid` is present but the child produces no errors, what should you check? **Null values, `@Valid` placement, groups, type extractors, resolver, and which validation API was invoked.**
4. If you want to validate only one field without entering child objects, what should you use? **Appropriate `validateProperty` or `validateValue`, which do not cascade.**
5. Does `@Valid` fix JSON serialization cycles? **No**, a separate serialization/reference solution is needed.
6. If a root has two associations pointing to the same child, what is the risk of using a global visited set in a custom validator? **Dropping the error path for the second branch.**

## 11. Official Documentation

- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): Object graph validation (5.7.1), `validateProperty`/`validateValue`, groups, group conversion, and traversable properties.
- [Jakarta Validation — `Validator` API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html): `validate`, `validateProperty`, and `validateValue` overloads.
- [Jakarta Validation — `Path` API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Path.html): path metadata, indices/keys, and node kinds.
- [Hibernate Validator 8 — Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/): cascaded validation, container elements, fail-fast, `TraversableResolver`.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Jakarta provider and `LocalValidatorFactoryBean`.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, binding/validation, and HTTP exceptions.

**Key takeaway:** Jakarta Validation **cuts back-edges to an instance already on the current navigation path**, yet preserves **distinct error paths** to a shared instance. Actual execution scope depends on annotations, groups, nulls, container extractors, resolvers, and the validation API called.
