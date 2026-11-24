# Before–After Relationship Graph in Spring Boot Auto Configuration: Transitivity and Ordering Cycles

## 1. Problem to solve

When Spring Boot starts up, multiple **auto-configuration classes** can participate in registering bean definitions. One class may register a bean only after a bean provided by another class has been processed—for instance, using `@ConditionalOnBean` to detect a dependent bean. Consequently, **ordering relationships** between auto-configurations must be expressed.

The clearest way to view them is as a **directed graph**:

- Each **vertex** is an auto-configuration, such as `DataAutoConfiguration`, `RepositoryAutoConfiguration`, and `ApiAutoConfiguration`.
- An edge **A → B** means that when both A and B are selected, Spring Boot must **process A before B**.
- A chain **A → B → C** is **transitive**: A must also come before C.
- A cycle **A → B → C → A** requires a class to precede itself along the chain, making a linear order satisfying every edge impossible.

Illustrative diagram:

~~~mermaid
flowchart LR
    A["DataAutoConfiguration"] --> B["RepositoryAutoConfiguration"]
    B --> C["ApiAutoConfiguration"]
~~~

**Important scope:** before/after is the **configuration processing order for registering bean definitions**, not bean constructor order, service call order, database initialization order, or request execution order. Spring Boot 3.3 clearly states this distinction in its auto-configuration documentation.

The goal of this lesson is to read arrow directions accurately from annotations, derive valid orderings for an acyclic graph, detect cycles, and fix dependency modeling.

## 2. Converting `before` and `after` into edges

Spring Boot 3.3 supports:
- `@AutoConfiguration(before = X.class)` and `@AutoConfiguration(after = X.class)`.
- `@AutoConfiguration(beforeName = "class.name")` and `@AutoConfiguration(afterName = "class.name")`.
- Dedicated annotations `@AutoConfigureBefore` and `@AutoConfigureAfter`.
- `@AutoConfigureOrder` for priority order when sorting auto-configurations without expressing a specific class dependency relationship.

Convention: **the arrow goes from the earlier configuration to the later configuration**.

| Declaration | Placed on | Relationship |
| --- | --- | --- |
| `@AutoConfiguration(before = B.class)` | On A | A → B |
| `@AutoConfiguration(after = A.class)` | On B | A → B |
| `@AutoConfigureBefore(B.class)` | On A | A → B |
| `@AutoConfigureAfter(A.class)` | On B | A → B |
| `@AutoConfiguration(beforeName = "com.example.BAutoConfiguration")` | On A | A → B if B participates |
| `@AutoConfiguration(afterName = "com.example.AAutoConfiguration")` | On B | A → B if A participates |

One side declaring `before` or the other declaring `after` can express the same edge. There is no need to duplicate constraints once the relationship is accurately described.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration
class DataAutoConfiguration {
}

@AutoConfiguration(after = DataAutoConfiguration.class)
class RepositoryAutoConfiguration {
}

@AutoConfiguration(after = RepositoryAutoConfiguration.class)
class ApiAutoConfiguration {
}
~~~

The three classes above are **illustrative metadata snippets**; running in a real application requires registering auto-configurations via the discovery mechanism and providing concrete beans. They define the required graph:

~~~text
DataAutoConfiguration -> RepositoryAutoConfiguration
RepositoryAutoConfiguration -> ApiAutoConfiguration
~~~

If you instead put `@AutoConfiguration(before = RepositoryAutoConfiguration.class)` on `DataAutoConfiguration`, the Data → Repository direction remains unchanged.

### When to use string class names?

`beforeName`/`afterName` let you refer to an auto-configuration in another library by its fully qualified name when avoiding a direct compile-time dependency on that class. Example:

~~~java
@AutoConfiguration(
    afterName = "com.vendor.integration.VendorAutoConfiguration"
)
class ExtensionAutoConfiguration {
}
~~~

This is a **relative constraint**: it does not make `VendorAutoConfiguration` automatically appear in the imported configuration list. If the target class is a nested class, the binary name in the string uses `$` to separate outer and nested classes.

## 3. Topological ordering

To execute a linear list satisfying all edges, the graph must be a **DAG (directed acyclic graph)**: a directed graph with no cycles.

An ordering `v1, v2, ..., vn` is a **topological order** if for every edge A → B, A precedes B.

Diamond example:

~~~mermaid
flowchart LR
    A["A"] --> B["B"]
    A --> C["C"]
    B --> D["D"]
    C --> D
~~~

Constraints that must hold: A before B; A before C; B before D; C before D. From this, A must precede D.

Both orderings are valid:

~~~text
A, B, C, D
A, C, B, D
~~~

**Do not infer B before C** since there is no edge B → C. Two configurations with no before–after constraint are **incomparable in the partial order**; an order observed in one run should not be treated as a domain contract unless the needed relationship is declared.

This leads to a core principle: add edges to express **real dependencies**, not to force every class into one long chain when no requirement exists.

## 4. Transitive relationships

Given the chain:

~~~text
A -> B
B -> C
C -> D
~~~

By transitivity we infer:

~~~text
A -> C
B -> D
A -> D
~~~

If A must precede B and B must precede C, there is no need to also add `before = C.class` on A just to "restate" what is already guaranteed by the path. Instead of storing redundant edges, **transitive reduction** keeps minimal edges to make the graph easier to read.

In Spring Boot:

~~~java
@AutoConfiguration
class AAutoConfiguration {
}

@AutoConfiguration(after = AAutoConfiguration.class)
class BAutoConfiguration {
}

@AutoConfiguration(after = BAutoConfiguration.class)
class CAutoConfiguration {
}

@AutoConfiguration(after = CAutoConfiguration.class)
class DAutoConfiguration {
}
~~~

When A, B, C, and D are all candidates, the chain A → B → C → D enforces A before D. The annotations here only express relationships; they generate no beans and set no class-selection conditions.

**Case requiring care:** If B is an optional configuration and gets filtered out of the candidate set, there is no longer a complete A → B → C path in the graph of active candidates. If C **always** needs to come after A regardless of whether B participates, declare A → C directly or reorganize configuration responsibilities. Do not rely solely on an intermediate vertex that may be absent to express a critical requirement.

Do not add every transitive edge "just in case"; add a direct edge only when it represents a dependency that must hold independently.

## 5. Ordering cycles

Consider three constraints:

~~~text
A -> B
B -> C
C -> A
~~~

Graph:

~~~mermaid
flowchart LR
    A["A"] --> B["B"]
    B --> C["C"]
    C --> A
~~~

Choosing A before B and B before C forces A before C. Yet C → A forces C before A. Thus A would have to precede itself, which is impossible in any linear order.

A source-code example that creates a cycle:

~~~java
@AutoConfiguration(after = CAutoConfiguration.class)
class AAutoConfiguration {
}

@AutoConfiguration(after = AAutoConfiguration.class)
class BAutoConfiguration {
}

@AutoConfiguration(after = BAutoConfiguration.class)
class CAutoConfiguration {
}
~~~

Reading by convention yields C → A, A → B, B → C—a cycle.

### Types of cycles to detect

| Pattern | Edges | Manifestation |
| --- | --- | --- |
| Two-node cycle | A → B, B → A | Each class requires coming before the other |
| Three-node cycle | A → B, B → C, C → A | Visible only when combining at least three metadata entries |
| Long cycle | A → B → C → D → A | Easily obscured when classes span multiple libraries |
| Self-edge | A → A | Requires a class to precede itself |
| Conflicting `before` and `after` | A before B yet A also after B | Two opposite edges from annotation declarations |

**A before–after cycle is not a bean dependency injection cycle.** For instance, bean A constructor-injecting bean B while bean B constructor-injects bean A is a circular bean dependency problem at instantiation time. An ordering cycle is a problem in **auto-configuration sorting metadata**. An ordering cycle can exist even if the beans never reference one another.

Mathematically, **no ordering satisfies all edges of a cycle**. However, do not assume every Spring Boot version throws the exact same exception for such metadata. Exact sorter behavior can depend on implementation and version. Sound design avoids cycles rather than counting on the system to pick one edge to "win."

## 6. Why doesn't changing `@Order` or `@DependsOn` fix a cycle?

The following mechanisms solve **different** problems:

| Mechanism | Used for | Does not guarantee |
| --- | --- | --- |
| `@AutoConfiguration(before/after)` or `@AutoConfigureBefore/After` | Relative relationship between auto-configuration classes | Bean instance creation order |
| `@AutoConfigureOrder` | Auto-configuration application priority when avoiding or unable to reference classes directly | Does not turn A < B < C < A into a valid order |
| `@DependsOn` | Instance initialization constraints for already-registered beans | Does not turn a previously false `@ConditionalOnBean` into true |
| `@Order`/`Ordered` on eligible Spring objects | Order when sorting collections, interceptors, strategies, etc., by context | Does not define before–after edges between auto-configurations |
| Line order in `AutoConfiguration.imports` | Declaring auto-configuration candidate classes | Should not be used as a dependency ordering contract |

Suppose `RepositoryAutoConfiguration` registers a repository only if `DataSource` has been processed via `@ConditionalOnBean(DataSource.class)`. If the repository is evaluated before the configuration creating the data source, the condition may not match. Merely adding `@DependsOn("dataSource")` to an unregistered bean **does not retroactively create the bean definition**. The bean definition order itself must be fixed via proper auto-configuration relationships.

According to Spring Boot 3.3 documentation, ordering metadata only controls **the order in which bean definitions are registered**. Bean instances are created later based on dependencies and `@DependsOn`; do not use constructor logs to directly conclude how auto-configurations were ordered.

## 7. Spring Boot 3.3 test: A → B → C and transitivity

The following Java 17+ example can be verified in a Spring Boot 3.3 project declaring `spring-boot-starter-test` (JUnit 5, AssertJ, `ApplicationContextRunner`). `RootService`, `MiddleService`, and `FinalService` are defined completely to focus on bean registration conditions.

Path `src/test/java/com/example/demo/AutoConfigurationOrderingGraphTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationOrderingGraphTest {

    static final class RootService {
        String name() {
            return "root";
        }
    }

    static final class MiddleService {
        private final RootService root;

        MiddleService(RootService root) {
            this.root = root;
        }

        String name() {
            return root.name() + "->middle";
        }
    }

    static final class FinalService {
        private final MiddleService middle;

        FinalService(MiddleService middle) {
            this.middle = middle;
        }

        String name() {
            return middle.name() + "->final";
        }
    }

    @AutoConfiguration
    static class RootAutoConfiguration {

        @Bean
        RootService rootService() {
            return new RootService();
        }
    }

    @AutoConfiguration(after = RootAutoConfiguration.class)
    static class MiddleAutoConfiguration {

        @Bean
        @ConditionalOnBean(RootService.class)
        MiddleService middleService(RootService root) {
            return new MiddleService(root);
        }
    }

    @AutoConfiguration(after = MiddleAutoConfiguration.class)
    static class FinalAutoConfiguration {

        @Bean
        @ConditionalOnBean(MiddleService.class)
        FinalService finalService(MiddleService middle) {
            return new FinalService(middle);
        }
    }

    @Test
    void transitiveOrderHoldsEvenWhenInputIsReversed() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        FinalAutoConfiguration.class,
                        MiddleAutoConfiguration.class,
                        RootAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(RootService.class);
                    assertThat(context).hasSingleBean(MiddleService.class);
                    assertThat(context).hasSingleBean(FinalService.class);
                    assertThat(context.getBean(FinalService.class).name())
                            .isEqualTo("root->middle->final");
                });
    }

    @Test
    void missingRootDoesNotCreateDownstreamBeans() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        FinalAutoConfiguration.class,
                        MiddleAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(RootService.class);
                    assertThat(context).doesNotHaveBean(MiddleService.class);
                    assertThat(context).doesNotHaveBean(FinalService.class);
                });
    }
}
~~~

Explanation:
- Edge **Root → Middle** comes from `MiddleAutoConfiguration(after = RootAutoConfiguration.class)`.
- Edge **Middle → Final** comes from `FinalAutoConfiguration(after = MiddleAutoConfiguration.class)`.
- Because of those two constraints, **Root → Final** holds transitively.
- When all candidates are present, root is registered before middle's condition is evaluated; middle is registered before final's condition is evaluated.
- When root does not participate, `after = RootAutoConfiguration.class` does not import root automatically. `@ConditionalOnBean(RootService.class)` on middle does not match, so final also receives no `MiddleService`.

Run command in a project with Gradle wrapper and test dependencies:

~~~bash
./gradlew test --tests "com.example.demo.AutoConfigurationOrderingGraphTest"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.AutoConfigurationOrderingGraphTest"
~~~

**Expected result:** both tests PASS. The tests assert on actual registered beans and the string `root->middle->final`, without requiring any specific Gradle stdout line. That string comes from the `name()` methods in the example, **not a trace of constructor call order**.

`AutoConfigurations.of(...)` passes auto-configurations directly into the test fixture; a real packaged starter must list classes in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` for Spring Boot to discover them.

## 8. Standalone Java 17 program: checking DAG and detecting cycles

To see the graph principle clearly, Kahn's algorithm can check whether a topological order exists:

1. Count the **in-degree** (number of incoming edges) of each vertex.
2. Put vertices with in-degree 0 into a queue.
3. Pop a vertex, append it to the result, and remove the effect of its outgoing edges by decrementing in-degrees.
4. If not all vertices can be processed, a cycle exists and no complete topological ordering can be produced.

Create `AutoConfigurationGraphDemo.java` (requires JDK 17+ only, **no Spring needed**):

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;

public class AutoConfigurationGraphDemo {

    record Edge(String from, String to) {
    }

    static List<String> order(List<String> nodes, List<Edge> edges) {
        Map<String, Integer> incoming = new HashMap<>();
        Map<String, List<String>> outgoing = new HashMap<>();

        for (String node : nodes) {
            if (incoming.putIfAbsent(node, 0) != null) {
                throw new IllegalArgumentException("Duplicate node");
            }
            outgoing.put(node, new ArrayList<>());
        }

        for (Edge edge : edges) {
            if (!incoming.containsKey(edge.from())
                    || !incoming.containsKey(edge.to())) {
                throw new IllegalArgumentException("Unknown node");
            }
            outgoing.get(edge.from()).add(edge.to());
            incoming.merge(edge.to(), 1, Integer::sum);
        }

        PriorityQueue<String> ready = new PriorityQueue<>();
        for (String node : nodes) {
            if (incoming.get(node) == 0) {
                ready.add(node);
            }
        }

        List<String> sorted = new ArrayList<>();
        while (!ready.isEmpty()) {
            String current = ready.remove();
            sorted.add(current);
            for (String next : outgoing.get(current)) {
                int count = incoming.merge(next, -1, Integer::sum);
                if (count == 0) {
                    ready.add(next);
                }
            }
        }

        if (sorted.size() != nodes.size()) {
            throw new IllegalArgumentException("Graph has a cycle");
        }
        return sorted;
    }

    public static void main(String[] args) {
        List<Edge> acyclic = List.of(
                new Edge("A", "B"),
                new Edge("B", "C"),
                new Edge("A", "D")
        );
        System.out.println("DAG: "
                + order(List.of("A", "B", "C", "D"), acyclic));

        List<Edge> cyclic = List.of(
                new Edge("A", "B"),
                new Edge("B", "C"),
                new Edge("C", "A")
        );
        try {
            order(List.of("A", "B", "C"), cyclic);
        } catch (IllegalArgumentException ex) {
            System.out.println("CYCLE: " + ex.getMessage());
        }
    }
}
~~~

Commands:

~~~bash
javac AutoConfigurationGraphDemo.java
java AutoConfigurationGraphDemo
~~~

Exact stdout:

~~~text
DAG: [A, B, C, D]
CYCLE: Graph has a cycle
~~~

For the DAG, the priority queue selects names alphabetically; that is how **the illustrative program** picks among valid topological orderings. Do not infer that Spring Boot uses Kahn's algorithm specifically or this exact tie-breaking rule. The Java snippet simply demonstrates that an acyclic graph lets all vertices be processed, whereas a cycle does not.

## 9. Breaking cycles and keeping configuration sources maintainable

When encountering A → B → C → A:

1. **Convert all annotations into directed edges** and record their source: which class, which file, and whether `before` or `after` points to which class.
2. **Identify the reason for each edge.** For example, if B has `@ConditionalOnBean` needing a bean from A, the true constraint is A → B; do not flip it to B → A.
3. **Check which vertices are actually candidates.** A class may not be selected because it is missing from imports, excluded, or filtered out by conditions. Merely being on the classpath is not enough.
4. **Remove unnecessary or misdeclared relationships.** If C does not actually need to wait for B, edge B → C may be redundant metadata. Remove it only after verifying real requirements.
5. **Extract shared infrastructure into a foundational configuration.** For example, if A and C need each other, consider a configuration D creating the shared part first, with both A and C depending one-way on D; avoid cycles.
6. **Test both full and missing-vertex cases.** Conditions must match when prerequisites exist and back off properly when absent.

An example fix direction:

~~~text
Before: A -> B -> C -> A     (conflicting)
After:  A -> B -> C          (orderable)
~~~

This is only an **illustrative graph**; which edge may legitimately be removed depends on each class's bean registration needs. Never break a cycle arbitrarily by deleting an edge if doing so violates business logic.

If global priority levels are needed among auto-configurations that do not know each other, consider `@AutoConfigureOrder`, though it does not replace modeling and resolving a cyclic dependency. Never treat a successful startup on one version as proof that every conflicting edge was honored.

## 10. Diagnosing cases where a bean is not registered

Typical symptom: auto-configuration B has `@ConditionalOnBean(RootService.class)`, yet B's bean does not appear even though the source code has auto-configuration A defining `RootService`.

How to investigate:
- Confirm A is actually a **candidate auto-configuration**, and the `RootService` bean was not excluded by another condition.
- Read `before/after` metadata on A and B, confirming edge **A → B**. Bean conditions generally inspect only bean definitions already processed up to evaluation time.
- Confirm the `@Bean` method's return type is specific enough for Spring to know the bean type without instantiating it.
- Use `ApplicationContextRunner` to build a context with A and B, testing both with and without prerequisites. Try passing configurations in reverse order to verify metadata works.
- Enable `debug=true` or `--debug` to view Spring Boot's **Condition Evaluation Report** and match/no-match reasons. If the application exposes the `/actuator/conditions` Actuator endpoint appropriately, you can inspect the condition report there as well.
- If a bean is missing, do not automatically conclude an ordering-cycle error: the class may not be imported, a property may be wrong, type metadata may be hidden, or the bean may be absent due to another condition.

Avoid "fixing" solely by moving lines in imports or only adding `@DependsOn` on the consumer. Those two actions do not accurately express before–after auto-configuration processing needs.

## 11. Common reasoning errors

| Misconception | Correct understanding |
| --- | --- |
| "A before B means bean instance A always creates before bean instance B." | Guarantees only **bean definition registration** order when metadata is satisfied; instance creation follows dependencies/lifecycle. |
| "A → B and B → C require declaring A → C too for transitivity to work." | No; A before C is implied when the path applies. |
| "A → B, A → C implies B → C." | No; B and C have no ordering relationship with each other. |
| "A → B → C → A can still find a valid order if configs run fast enough." | No linear order exists that satisfies an entire cycle. |
| "Every ordering cycle always throws the exact same Spring Boot exception." | Do not rely on one specific implementation reaction; fix the conflicting metadata. |
| "`@DependsOn` and `@AutoConfigureAfter` are the same." | One controls instance creation; the other controls auto-configuration application order. |
| "`afterName` automatically imports the named class." | It is relational metadata if the target participates; it does not select that class itself. |
| "Once class `RootService` is on the classpath, `@ConditionalOnBean` always matches." | A matching **bean definition** must be visible when the condition is evaluated. |
| "The order seen in imports is an application contract." | Use before/after metadata for relationships that must remain stable. |

## 12. Self-assessment exercises

1. B has `@AutoConfiguration(after = A.class)`. Which edge appears? **A → B**.
2. A has `@AutoConfiguration(before = B.class)`. Does it conflict with question 1? **No**; it is also A → B.
3. Does A → B → C → D force A before D? **Yes**, by transitivity when all vertices participate.
4. Does the diamond A → B, A → C, B → D, C → D allow the order A,C,B,D? **Yes**.
5. Can A → B, B → C, C → A be topologically sorted? **No**.
6. Does adding `@AutoConfigureOrder(0)` make every edge of a cycle valid? **No**.
7. Why doesn't `@DependsOn` cause a failed `@ConditionalOnBean` condition to be re-evaluated? Because it affects **creation order of already-registered beans**, not retroactively re-running condition evaluation.
8. C depends on B, B depends on A, yet B may be excluded. C always needs A. What should you do? **Account for active candidate sets and declare A → C directly if that requirement must hold independently.**
9. Why isn't seeing classes A and B in source code enough to conclude they run along edge A → B? Because you must confirm both **are applied candidates** at runtime and the constraint lives in auto-configuration metadata.
10. How do you verify the effect of ordering? **Use `ApplicationContextRunner` to test conditions, bean definitions, and present/missing-prerequisite cases**, combined with the condition report when needed.

## References

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `before`/`after` relationships, imports, `@AutoConfigureOrder`, and testing auto-configurations.
- [Spring Boot 3.3 — `@AutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): `before`, `after`, `beforeName`, `afterName` attributes.
- [Spring Boot 3.3 — `@AutoConfigureBefore` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html): definition of applying a configuration before another class.
- [Spring Boot 3.3 — `@AutoConfigureAfter` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html): definition of applying a configuration after another class; distinction from bean instantiation timing.
