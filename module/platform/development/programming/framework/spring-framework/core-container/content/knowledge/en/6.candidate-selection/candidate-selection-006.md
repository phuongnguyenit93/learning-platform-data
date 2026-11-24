# Using Generic Type Parameters for Bean Selection in Spring

## 1. The Problem: Same Interface, Different Data Types

A generic interface can represent multiple distinct capabilities:

~~~java
interface Store<T> {
    T read();
}
~~~

A `Store<String>` implementation supplies strings, whereas `Store<Integer>` supplies integers. At the **raw type** level, both are `Store`, yet they do not share the same **parameterized type**.

If Spring registers beans carrying type metadata:

~~~java
@Bean
Store<String> messageStore() {
    return new StringStore();
}

@Bean
Store<Integer> counterStore() {
    return new IntegerStore();
}
~~~

then an injection point declared as `Store<String>` can select `messageStore` without writing `@Qualifier("messageStore")`; likewise `Store<Integer>` can select `counterStore`. Spring refers to this mechanism as **generics as autowiring qualifiers**: **generic type parameters act as a form of implicit qualifier**. <https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html>

The two `@Bean` methods above are **illustrative snippets**, missing the class definitions; runnable standalone code with complete definitions is in section 5.

**Key point:** Spring does not look only at the `Store` interface name; it can also inspect type `T` in type metadata preserved on the bean definition and injection point. This differs from Java generating a separate runtime class per `Store<T>`: Java still uses **type erasure**, yet declared signatures, generic interfaces, and appropriate metadata sources preserve generic information for the container to resolve.

~~~text
Bean declarations                 Injection point
--------------------------------------------------------------
Store<String> messageStore    --> Store<String>       selects messageStore
Store<Integer> counterStore   --> Store<Integer>      selects counterStore
Store<Double> priceStore      --> Store<Double>       selects priceStore

Store<Integer> counterStore   --+
Store<Integer> auditStore     --+--> List<Store<Integer>> receives both
Store<String> messageStore    --+--> excluded from Integer group
~~~

**Benefit:** when generic types genuinely denote roles, they eliminate the need to invent String qualifiers solely to separate distinct typed groups.

## 2. At Which Step Is Generic Qualification Applied?

A practical mental model:

1. Spring determines the dependency type from constructor/field/method/factory method; for example `Store<String>`.
2. The container finds beans whose metadata is **assignable and generically compatible** with the requested type.
3. Additional filters such as `@Qualifier`, bean name, `@Primary`, and other resolution rules are evaluated where applicable.
4. If injection expects **a single bean**, the container must choose one final candidate; if it expects **a collection**, Spring can gather multiple compatible candidates.

Spring documentation confirms that using generic types as qualifiers applies not only to fields but also to **typed collections** such as `List`, `Map`, and arrays. It works for constructor arguments and `@Bean` factory method parameters as appropriate. <https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html>

### Example Table

| Declared bean | Metadata type | Injection point | Generic match? |
| --- | --- | --- | --- |
| `words` | `Store<String>` | `Store<String>` | Yes |
| `counter` | `Store<Integer>` | `Store<String>` | No |
| `counter` | `Store<Integer>` | `Store<Integer>` | Yes |
| `price` | `Store<Double>` | `List<Store<Integer>>` | No |
| `auditCounter` | `Store<Integer>` | `List<Store<Integer>>` | Yes |

The table assumes Spring has **complete generic metadata** for each bean; for raw types, factory metadata lacking type parameters, or special proxies, verify actual runtime behavior.

### Generics Are Not a `@Qualifier` Annotation

This code:

~~~java
@Autowired
private Store<String> messages;
~~~

can inject the matching bean solely via type `Store<String>`, even **without `@Qualifier`** on the field. Spring understands the requirement from the generic signature.

Using `@Qualifier` remains helpful when **two beans share the exact same `Store<String>` type**. Generics separate groups by type argument, without distinguishing semantic roles between two objects in the same typed group.

## 3. Java Generics, Type Erasure, and Why Spring Still Makes It Work

### 3.1. `Store<String>` and `Store<Integer>` Share the Same Raw Class

Java generics are checked primarily at compile time; many type parameters are **erased** in the bytecode representation of references. That means Java does not create two independent runtime classes named `Store<String>` and `Store<Integer>`.

Example (not standalone runnable because `Store` is omitted):

~~~java
Store<String> text = ...;
Store<Integer> number = ...;

// Looking at the raw interface:
// text instanceof Store
// number instanceof Store
~~~

`instanceof Store<String>` is not a standard parameterized type check allowed by Java. You cannot resolve every generic simply by calling `someObject.getClass()` and guessing `T` from an instance at runtime.

### 3.2. Generic Signatures Can Be Retained in Metadata

Despite erasure, Java reflection can still read **declared generic signatures** on fields, superclasses, generic interfaces, and method parameter/return types. Spring uses advanced type abstractions such as `ResolvableType` to work with this metadata.

For example, a `@Bean` method declaring return type `Store<Integer>` gives the container far clearer type intent than a method declaring only the raw type `Store`.

**Do not misunderstand:** Spring does not infer that a raw `Store` is `Store<Integer>` merely because the instance happens to hold `123`. Runtime data values are not a safe type contract for autowiring.

### 3.3. Plain Java 17 Checking Erasure Metadata

Create standalone file `GenericSignatureDemo.java`:

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;

public final class GenericSignatureDemo {
    interface Store<T> {}

    Store<String> words;
    Store<Integer> numbers;

    public static void main(String[] args) throws Exception {
        Type a = GenericSignatureDemo.class
                .getDeclaredField("words").getGenericType();
        Type b = GenericSignatureDemo.class
                .getDeclaredField("numbers").getGenericType();

        ParameterizedType text = (ParameterizedType) a;
        ParameterizedType integer = (ParameterizedType) b;

        System.out.println("TEXT_ARG "
                + text.getActualTypeArguments()[0].getTypeName());
        System.out.println("NUMBER_ARG "
                + integer.getActualTypeArguments()[0].getTypeName());
        System.out.println("SAME_RAW "
                + text.getRawType().equals(integer.getRawType()));
    }
}
~~~

Compile and run with **JDK 17+**, without Spring:

~~~bash
javac --release 17 -encoding UTF-8 GenericSignatureDemo.java
java GenericSignatureDemo
~~~

Stdout:

~~~text
TEXT_ARG java.lang.String
NUMBER_ARG java.lang.Integer
SAME_RAW true
~~~

The two fields carry different generic arguments, and `getGenericType()` reflects that. Yet `getRawType()` is identical. Spring relies on the appropriate type metadata, rather than creating a separate JVM class per type parameter.

## 4. Single-Bean Injection and Multi-Bean Injection with Generics

### 4.1. A Fully Parameterized Single Argument

~~~java
public MessageService(Store<String> store) {
    this.store = store;
}
~~~

This is an illustrative snippet requiring service and `Store` declarations. If only **one `Store<String>`** is registered, Spring can resolve the parameter from its generic type.

### 4.2. What If There Are Two `Store<Integer>` Beans?

Suppose:

~~~java
@Bean
Store<Integer> primaryCounter() { ... }

@Bean
Store<Integer> secondaryCounter() { ... }
~~~

When requesting a single `Store<Integer>`, the generic filter still leaves **two candidates**. Without an additional selection rule, `NoUniqueBeanDefinitionException` can occur.

This proves **generic qualifiers distinguish type arguments, not unique bean IDs**. You can add `@Qualifier("primaryCounter")` or a semantic qualifier such as `@Qualifier("reporting")` on both the injection point and the appropriate candidate.

### 4.3. Collections Receive Only Generically Compatible Beans

~~~java
public Aggregator(List<Store<Integer>> integerStores) {
    this.integerStores = integerStores;
}
~~~

This illustrative snippet represents a group. With multiple `Store<Integer>` beans, Spring can inject **all** beans compatible with generic `Integer`, while excluding `Store<String>` from the group.

Spring also supports `Map<String, Store<Integer>>` injection; map keys are typically **bean names**, and values are the matching `Store<Integer>` beans. `List<Store<String>>` forms a separate set.

### 4.4. How Generics Fit with `@Primary` and `@Qualifier`

| Injection | After generic filtering | What else is needed? |
| --- | --- | --- |
| `Store<String>` with one String bean | 1 bean | No name qualifier needed |
| `Store<Integer>` with two Integer beans | 2 beans | Needs a rule to pick one bean for a single dependency |
| `@Qualifier("reporting") Store<Integer>` | Integer beans carrying `reporting` | One final candidate or an extra rule |
| `List<Store<Integer>>` | All matching Integer beans | Can inject the whole group |
| `Map<String, Store<Integer>>` | All matching Integer beans | Keys are bean names |
| `Store<?>` | Broader wildcard type | Can match multiple candidates; does not guarantee uniqueness |

`@Primary` can prioritize one bean when an injection target needs **one object**, yet it does not shrink `List<Store<Integer>>` down to one element. If a candidate marked `@Primary` has an incompatible generic type, primary does not make it match the requested type.

## 5. Complete Example: Spring Framework 6.2 and Java 17

The example uses **one generic interface `Store<T>`**, one `Store<String>` bean, and **two `Store<Integer>` beans**. One Integer bean carries qualifier `reporting`; the other does not. `Dashboard` receives:

- `Store<String>`: one candidate via generic type.
- `@Qualifier("reporting") Store<Integer>`: one candidate out of two beans sharing the same generic type.
- `List<Store<Integer>>`: two Integer candidates.
- `Map<String, Store<Integer>>`: two entries keyed by bean names.
- `List<Store<String>>`: only one String candidate.

### 5.1. Directory and Maven

Requires JDK 17+ and Maven; no Spring Boot, web server, database, or Java preview features needed.

~~~text
generic-qualifier-demo/
├── pom.xml
└── src/main/java/demo/GenericQualifierDemo.java
~~~

`pom.xml` file:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>generic-qualifier-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.GenericQualifierDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. Complete Java File

Create `src/main/java/demo/GenericQualifierDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class GenericQualifierDemo {
    private GenericQualifierDemo() {}

    public interface Store<T> {
        String label();
        T read();
    }

    public record FixedStore<T>(String label, T value) implements Store<T> {
        @Override
        public T read() {
            return value;
        }
    }

    public static final class Dashboard {
        private final Store<String> message;
        private final Store<Integer> selectedCounter;
        private final List<Store<Integer>> counters;
        private final Map<String, Store<Integer>> countersByBeanName;
        private final List<Store<String>> messages;

        public Dashboard(Store<String> message,
                         Store<Integer> selectedCounter,
                         List<Store<Integer>> counters,
                         Map<String, Store<Integer>> countersByBeanName,
                         List<Store<String>> messages) {
            this.message = Objects.requireNonNull(message);
            this.selectedCounter = Objects.requireNonNull(selectedCounter);
            this.counters = List.copyOf(counters);
            this.countersByBeanName = Map.copyOf(countersByBeanName);
            this.messages = List.copyOf(messages);
        }

        public String messageValue() {
            return message.read();
        }

        public String selectedValue() {
            return selectedCounter.label() + "="
                    + selectedCounter.read();
        }

        public String counterValues() {
            return counters.stream()
                    .map(s -> s.label() + "=" + s.read())
                    .sorted()
                    .toList()
                    .toString();
        }

        public String counterNames() {
            return countersByBeanName.keySet().stream()
                    .sorted()
                    .toList()
                    .toString();
        }

        public int counterCount() {
            return counters.size();
        }

        public int messageCount() {
            return messages.size();
        }

        public int reportValue() {
            return countersByBeanName.get("reportCounter").read();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Store<String> welcomeStore() {
            return new FixedStore<>("welcome", "hello");
        }

        @Bean
        @Qualifier("reporting")
        public Store<Integer> reportCounter() {
            return new FixedStore<>("report", 17);
        }

        @Bean
        @Qualifier("archival")
        public Store<Integer> archiveCounter() {
            return new FixedStore<>("archive", 42);
        }

        // Spring resolves generic arguments of each factory parameter.
        @Bean
        public Dashboard dashboard(
                Store<String> stringStore,
                @Qualifier("reporting") Store<Integer> selected,
                List<Store<Integer>> integerStores,
                Map<String, Store<Integer>> integersByName,
                List<Store<String>> stringStores) {
            return new Dashboard(stringStore, selected, integerStores,
                    integersByName, stringStores);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            Dashboard dash = context.getBean(Dashboard.class);

            System.out.println("MESSAGE " + dash.messageValue());
            System.out.println("SELECTED " + dash.selectedValue());
            System.out.println("INT_COUNT " + dash.counterCount());
            System.out.println("INT_VALUES " + dash.counterValues());
            System.out.println("INT_NAMES " + dash.counterNames());
            System.out.println("STRING_COUNT " + dash.messageCount());
            System.out.println("REPORT_VALUE " + dash.reportValue());
            System.out.println("SAME_DASHBOARD "
                    + (dash == context.getBean(Dashboard.class)));
        }
    }
}
~~~

**What makes this example notable:** both `reportCounter` and `archiveCounter` explicitly declare return type `Store<Integer>`, so generic qualification **cannot select a unique bean** by type alone. `@Qualifier("reporting")` placed on one factory method and on parameter `selected` picks the reporting bean; meanwhile `List` and `Map` **still receive both `Store<Integer>` beans**. The `welcomeStore` bean has type `Store<String>`, so it enters only the String group.

### 5.3. Running via Maven

From the `generic-qualifier-demo` directory:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

If running directly with `javac/java`, the classpath must include Spring and its dependencies; Maven manages the classpath for the example. `maven.compiler.release=17` requires Java 17 compatible compilation.

**Stdout printed by the program itself in exact order:**

~~~text
MESSAGE hello
SELECTED report=17
INT_COUNT 2
INT_VALUES [archive=42, report=17]
INT_NAMES [archiveCounter, reportCounter]
STRING_COUNT 1
REPORT_VALUE 17
SAME_DASHBOARD true
~~~

Maven may print additional dependency download info and its own logs. The block above describes the **program's `System.out.println` output**, not claiming the entire terminal has only eight lines.

### 5.4. Explaining Stdout

1. `Store<String> stringStore` in `dashboard(...)` matches `welcomeStore`. `reportCounter` and `archiveCounter` do not match the String parameter type, so `MESSAGE hello`.
2. `@Qualifier("reporting") Store<Integer> selected` selects `reportCounter`, giving `SELECTED report=17`.
3. `List<Store<Integer>>` receives the two integer beans and excludes `Store<String>`. Result: `INT_COUNT 2`.
4. `counterValues()` formats each store as `label=value` and calls `sorted()`, yielding deterministic `[archive=42, report=17]` independent of bean registration order.
5. `Map<String, Store<Integer>>` carries the two bean name keys `archiveCounter` and `reportCounter`. Calling `sorted()` on the keys gives the order shown in `INT_NAMES`.
6. `List<Store<String>>` contains one bean, so `STRING_COUNT 1`.
7. Querying the map for `reportCounter` returns `REPORT_VALUE 17`.
8. `Dashboard` is a default singleton within the same context, so repeated lookups return the same reference: `SAME_DASHBOARD true`.

**There is no stdout inside bean constructors or factory methods**, keeping output deterministic and independent of the order Spring instantiates singletons.

## 6. Limitations and Common Pitfalls

### 6.1. Declaring Raw Generics Loses Bean Selection Information

Compare:

~~~java
@Bean
Store<Integer> integerStore() {
    return new FixedStore<>("int", 5);
}
~~~

with:

~~~java
@Bean
@SuppressWarnings("rawtypes")
Store rawStore() {
    return new FixedStore<Integer>("int", 5);
}
~~~

These are **two separate illustrative snippets**, assuming `Store` and `FixedStore` already exist. The second method **declares a raw return type**, so the bean factory method metadata does not express `<Integer>`. Depending on the class, target type, bean factory inference, and proxies, Spring may fail to determine the exact generic argument or match more broadly than intended.

Do not conclude every raw bean is always excluded or always chosen: behavior must be verified against the actual bean definition. However, best practice is to **keep generic signatures explicit** on both `@Bean` methods and injection points.

### 6.2. Type Erasure Is Not “Disabled”

Spring uses metadata from declared type signatures; it does not inspect values inside a store to guess `T`. If a factory creates `Store<Integer>` yet declares return type `Object` or raw `Store`, the container will not necessarily deduce the type accurately from its contents.

Do not write business code assuming `getClass()` on a `FixedStore<Integer>` instance always tells you `T` is `Integer`. A generic class `FixedStore<T>` can share one runtime class across multiple instantiations.

### 6.3. Wildcards, Raw Types, Type Variables, and Nested Generics

Examples:

~~~java
Store<?> anyStore;
Store<? extends Number> numericStore;
List<Store<Integer>> integerStores;
Store<List<String>> nestedStringLists;
~~~

These are illustrative fields, not injection points from the demo. `Store<?>` is broader than `Store<String>` and may leave multiple candidates. `Store<? extends Number>` and nested generic types involve assignability/variance relationships requiring matching metadata; **do not assume Spring will always pick a single bean**. For type variables like `Store<T>` on a generic class, resolving `T` also depends on whether Spring knows the type binding of the bean class under consideration.

A configuration should avoid wildcard/raw injection whenever precise bean selection depends on a specific `T`.

### 6.4. Java Generics Are Invariant at Compile Time

`Store<Integer>` **is not a subtype** of `Store<Number>` merely because `Integer extends Number`. That is Java generic invariance, not a Spring bug. Therefore, do not use `Store<Number>` expecting it to implicitly match `Store<Integer>` without appropriate typing.

### 6.5. Generic Qualifiers Do Not Solve Every Ambiguity

If two `Store<Integer>` beans exist, injecting a single `Store<Integer>` can still throw `NoUniqueBeanDefinitionException`. You can combine:

- `@Qualifier("reporting")` to choose a role.
- `@Primary` if one bean is genuinely the default preference within the matching set.
- Bean name or custom qualifiers when intentionally selecting by name/metadata.
- `List<Store<Integer>>` when business logic needs **the whole group**, rather than a single bean.
- A runtime data-driven factory/strategy if selection changes per request.

Do not slap `@Primary` on every implementation or switch everything to `ObjectProvider` to dodge making an explicit choice.

### 6.6. Annotations and Component Registration Still Apply

A class implementing `Store<String>` does not appear in a Spring context automatically just because of its Java generic interface. The bean must be registered via `@Bean`, component scanning, or another supported mechanism. And if type metadata is obscured by a proxy or factory, evaluate the actual runtime path rather than inferring solely from the Java interface in your IDE.

## 7. Generics vs. `@Qualifier` vs. Bean Name: Which to Choose?

| Approach | What it expresses | When appropriate |
| --- | --- | --- |
| Generic type | `Store<String>` vs. `Store<Integer>` | Different **data types / type contracts** |
| Spring `@Qualifier("reporting")` | Only candidates carrying the same label | Multiple implementations **of the same generic type** with different roles |
| `@Primary` | Priority when a single bean is needed | There is a default choice among valid candidates |
| Bean name | `reportCounter` | Need a specific name reference, understanding bean-name matching semantics |
| Typed collection | `List<Store<Integer>>` | Need multiple beans of the same generic type |
| Provider/factory | `ObjectProvider<Store<Integer>>` | Need deferred or on-demand lookup |
| Domain strategy | `Map<Key, Handler>` or router | Choose by per-request/runtime policy, not at wiring time |

**Do not conflate responsibilities:** generic parameters describe the **type** of a dependency; qualifier annotations describe additional **traits** of a bean. The two mechanisms complement rather than exclude each other.

### Avoid Unintentional Reliance on Java Parameter Names

In modern Spring, when multiple beans share the same type, a field/parameter name can act as a final fallback match under certain conditions. Yet you should not rely on source-code names like `reportCounter` in place of a meaningful qualifier, especially when a project lacks `-parameters` or must stay stable across refactoring.

If the actual requirement is “the reporting store”, write `@Qualifier("reporting")`. If the requirement is simply “the integer store”, keep generic `Store<Integer>` and ensure the right number of candidates exists.

## 8. Testing and Debugging

### Testing Generic Type Resolution

A container integration test should verify:

1. `Store<String>` picks the string bean.
2. `List<Store<Integer>>` contains only the integer beans.
3. `Map<String, Store<Integer>>` contains the expected bean names.
4. `@Qualifier("reporting") Store<Integer>` picks the reporting bean.
5. Intentionally injecting an unqualified `Store<Integer>` with two candidates fails or requires a selection rule, instead of the app accidentally picking one bean.

The demo program already produces output verifying the first four items. Negative tests should run in a separate test context so they do not break main application startup.

### Debugging in Order

- **Step 1 — verify the bean is registered:** check `@Bean`, component scans, profiles, and conditions.
- **Step 2 — compare full types:** `Store<String>` differs from `Store<Integer>`, not just raw `Store`.
- **Step 3 — inspect declared signatures:** does the bean factory method declare a parameterized return type? Does a generic class implement the interface with a concrete argument?
- **Step 4 — check qualifiers/primary:** how many candidates remain after generic filtering?
- **Step 5 — check the injection target:** is it a single bean or a `List`/`Map`? Target kind changes how results are assembled.
- **Step 6 — read the root cause:** `NoSuchBeanDefinitionException` when a candidate is missing, `NoUniqueBeanDefinitionException` when too many matching candidates exist, and `BeanCreationException` when a candidate's factory/init fails.

**Do not work around it by casting a raw bean to `Store<String>`** just to silence Spring: casting does not provide type safety and can cause a `ClassCastException` when the data is used.

## 9. Exercises with Answers

**Exercise 1.** Beans `Store<String>` and `Store<Integer>` exist. Does injecting `Store<String>` necessarily require `@Qualifier("stringStore")`?

**Answer:** No, if generic metadata is intact and only one candidate matches `Store<String>`. Spring can use the generic argument as an implicit qualifier.

**Exercise 2.** Two beans share type `Store<Integer>`. Can generic qualification pick a single unique bean?

**Answer:** No. Generic filtering still leaves both; an additional selection rule is needed if the injection target expects a single object.

**Exercise 3.** Does injecting `List<Store<Integer>>` include `Store<String>`?

**Answer:** Not under normal generic matching when type metadata is preserved. It collects only stores matching `Integer`.

**Exercise 4.** Why does `Map<String, Store<Integer>>` use bean names as keys?

**Answer:** Spring supports autowiring typed maps with bean names as `String` keys and matching beans as values.

**Exercise 5.** Why is `Store<Integer>` not a subtype of `Store<Number>`?

**Answer:** Generic type parameters are invariant in Java. The subtype relationship between `Integer` and `Number` does not carry over to `Store<T>`.

**Exercise 6.** If `@Bean Store rawStore()` returns an object holding an `Integer`, will Spring definitely know that bean is `Store<Integer>`?

**Answer:** Not necessarily. A raw return type does not preserve `T` on the factory method signature; target metadata may be missing or depend on how Spring determines the actual bean class.

**Exercise 7.** Does `Store<?>` distinguish `String` and `Integer` as clearly as `Store<String>`?

**Answer:** No. The wildcard is broader, so multiple beans can be compatible and an explicit selection rule may be needed.

**Exercise 8.** Given one `Store<String>` and two `Store<Integer>` beans, what should you inject if you want all integer stores?

**Answer:** `List<Store<Integer>>` or a typed `Map<String, Store<Integer>>`. There is no need to mark one bean `@Primary` just to gather the group.

**Exercise 9.** How do you pick only the reporting store out of two Integer beans for one injection point?

**Answer:** Combine `Store<Integer>` with `@Qualifier("reporting")` on both the injection point and the candidate bean.

**Exercise 10.** Why does `new FixedStore<>("x", 17).getClass()` not automatically reveal that it is `FixedStore<Integer>`?

**Answer:** Type erasure causes multiple instantiations to share one runtime class. Metadata on declarations is a more reliable source for Spring to infer generics.

**Exercise 11.** Can a raw `Store` be turned into a type-safe bean simply by adding `@Primary`?

**Answer:** No. `@Primary` is a selection precedence rule; it does not restore missing generic arguments.

## 10. Design Checklist

- [ ] Use generic interfaces when `T` genuinely expresses a meaningful type contract.
- [ ] Declare explicit `@Bean` return types like `Store<String>` instead of raw `Store`.
- [ ] Keep type parameters explicit at constructor, field, method, and collection injection points.
- [ ] Register beans properly; do not assume generic classes are scanned automatically.
- [ ] Check candidate counts **after** generic filtering.
- [ ] If one bean is needed and multiple candidates share the same generic type, add a qualifier or primary intentionally.
- [ ] If all `Store<Integer>` beans are needed, use parameterized `List`/`Map`.
- [ ] Do not rely on `getClass()` to distinguish actual `T` past type erasure.
- [ ] Avoid raw/wildcard signatures when precise bean selection is required.
- [ ] Inspect nested generics, type variables, and proxy metadata in complex setups.
- [ ] Do not abuse bean-name matching via Java source parameter names.
- [ ] Keep request-content selection in domain routers/strategies, not in generic qualifiers.
- [ ] Separate unit tests of generic contracts from Spring bean-wiring integration tests.
- [ ] Test missing beans, two beans with identical generics, and typed collection injection.
- [ ] Distinguish program stdout from Maven logs and compile with the target Java 17 release.

### Official Spring Documentation

- [Using Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html)
- [Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)

**Conclusion:** Java generic parameters such as `Store<String>` and `Store<Integer>` can serve as **implicit qualifiers** when Spring resolves dependencies. This works for single injection, parameterized `List`, and parameterized `Map`; however, generics do not guarantee uniqueness when multiple beans share the full type, and they depend on clear type metadata rather than “reading `T` from an object” in spite of type erasure. Combining generic types, `@Qualifier`, and typed collections appropriately keeps object graphs type-safe, extensible, and easy to test.