# Annotation Inheritance and the Effect of Nested Classes

In Spring Framework Testing, annotations on a test class can influence how Spring creates the `ApplicationContext`, selects profiles, loads properties, and executes testing utilities. When a test class is subclassed or placed inside another class using JUnit Jupiter `@Nested`, you need to understand which rules govern annotation discovery and which configurations are passed down to the child test class.

There are three related but distinct mechanisms:

- **Java inheritance:** an annotation can be inherited from a superclass if the annotation itself is marked `@Inherited`.
- **Spring's merged annotation mechanism:** Spring can discover meta-annotations, composed annotations, and their aliases according to its own rules.
- **Configuration for nested tests:** the Spring TestContext Framework has `@NestedTestConfiguration` to decide whether test configuration annotations on an enclosing class are applied to nested test classes.

Distinguishing these three mechanisms helps avoid bugs such as a nested test unexpectedly sharing profiles or properties with the outer class, a subclass failing to receive expected configuration, or a custom annotation working on a superclass but not working as anticipated in a nested class.

## 1. Annotation Inheritance in Java

Java does not inherit all annotations from a superclass by default. For a class-level annotation to be inherited through an `extends` relationship, that annotation type must be declared with `@Inherited`.

Example:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Inherited
public @interface TestEnvironment {
    String value();
}
~~~

When the annotation is placed on a superclass:

~~~java
@TestEnvironment("integration")
class BaseIntegrationTest {
}

class OrderServiceTest extends BaseIntegrationTest {
}
~~~

`OrderServiceTest` can be seen as carrying `TestEnvironment("integration")` when queried with reflection APIs that support inheritance, such as `getAnnotation`.

If the subclass declares an annotation of the same type, the value on the subclass is used for that class:

~~~java
@TestEnvironment("integration")
class BaseIntegrationTest {
}

@TestEnvironment("staging")
class OrderServiceTest extends BaseIntegrationTest {
}
~~~

`OrderServiceTest` receives the value `staging`. The annotation on the superclass remains effective for other subclasses that do not override it.

### What Are the Limitations of `@Inherited`?

`@Inherited` only affects class-level annotations along a superclass inheritance relationship. It does not automatically apply in the following cases:

- Annotations placed on an interface are not inherited through the interface.
- Annotations placed on a method are not inherited by an overriding method via `@Inherited`.
- Annotations placed on a field, constructor, or package are not inherited.
- A nested class does not automatically inherit annotations from its enclosing class merely because it is declared inside that class.

The last point is very easy to confuse. In Java, syntactic enclosure is not inheritance. For example:

~~~java
@TestEnvironment("integration")
class PaymentTests {

    class CardPaymentTests {
    }
}
~~~

`CardPaymentTests` is not a subclass of `PaymentTests`. `@Inherited` does not make annotations on `PaymentTests` automatically become inherited annotations of `CardPaymentTests`.

JUnit `@Nested` does not change this Java language rule either. Spring has a separate mechanism to handle test configuration from enclosing classes, covered later in this lesson.

## 2. Spring Searches Annotations More Broadly Than Java Reflection

Spring provides a merged annotation mechanism to support composed annotations, meta-annotations, aliases, and hierarchy searching. Therefore, annotation lookup results with Spring can differ from simply calling Java reflection.

For example, an annotation can be placed on another annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ActiveProfiles("integration")
public @interface IntegrationTest {
}
~~~

When a test class uses `@IntegrationTest`, Spring TestContext can recognize `@ActiveProfiles` through the meta-annotation:

~~~java
@IntegrationTest
@SpringJUnitConfig(IntegrationTestConfiguration.class)
class PaymentIntegrationTest {
}
~~~

This lets you group repeated configuration into one meaningful annotation. The test class only needs to express its integration test intent; Spring reads the underlying configuration annotations.

### Meta-annotations and `@Inherited` Are Two Separate Concepts

An annotation can carry Spring meta-annotations without necessarily being inherited from a superclass under Java rules. If you want a custom annotation to be inherited through a class hierarchy under Java rules, you can add `@Inherited` onto the custom annotation itself:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Inherited
@ActiveProfiles("integration")
public @interface IntegrationTest {
}
~~~

Then, a subclass that does not declare `@IntegrationTest` can receive this annotation via its superclass. However, `@Inherited` still does not propagate the annotation from an enclosing class to a nested class.

### Aliases in Composed Annotations

Spring supports `@AliasFor` so a custom annotation can expose an attribute of a meta-annotation. For example, a shared test annotation can let the using class choose the web environment:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@SpringBootTest
@ActiveProfiles("integration")
public @interface IntegrationTest {

    @AliasFor(
            annotation = SpringBootTest.class,
            attribute = "webEnvironment"
    )
    SpringBootTest.WebEnvironment webEnvironment()
            default SpringBootTest.WebEnvironment.MOCK;
}
~~~

Usage:

~~~java
@IntegrationTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class PaymentApiIntegrationTest {
}
~~~

Spring merged annotations resolve the alias so the attribute on the composed annotation maps to the attribute of `@SpringBootTest`.

When creating a composed annotation, declare appropriate retention and target, and ensure the alias has a compatible type and default value with the target attribute. If the annotation needs to be inherited via superclasses, add `@Inherited` separately.

Do not assume every annotation lookup API uses the same search strategy. Java reflection, Spring `AnnotationUtils`, `MergedAnnotations`, and TestContext bootstrap have different purposes. When behavior depends on a specific annotation, understand the rules that the framework applies.

## 3. Test Configuration Annotations Can Be Inherited via Superclass

The Spring TestContext Framework supports inheriting many test configuration annotations from a superclass. This is useful when multiple test classes share a basic configuration set.

Example:

~~~java
@SpringJUnitConfig(BaseTestConfiguration.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "service.mode=stub")
abstract class BaseServiceTest {
}

class OrderServiceTest extends BaseServiceTest {

    @Test
    void createsOrder() {
        // Test uses configuration inherited from the superclass.
    }
}
~~~

`OrderServiceTest` can receive the context configuration, active profiles, and property sources from `BaseServiceTest` according to the inheritance rules of the respective annotations.

When a subclass adds configuration, some annotations merge the superclass and subclass values by default. Some annotations have attributes allowing inherited configuration to be replaced.

### `@ContextConfiguration`: Merging `classes` and `locations`

`@ContextConfiguration` has `inheritLocations` and `inheritInitializers` attributes. By default, configuration from the superclass is inherited and merged.

~~~java
@SpringJUnitConfig(classes = SharedTestConfiguration.class)
abstract class BaseRepositoryTest {
}

@ContextConfiguration(classes = OrderTestConfiguration.class)
class OrderRepositoryTest extends BaseRepositoryTest {
}
~~~

In this case, the subclass configuration can be merged with the parent class configuration. The context loader will use the merged configuration set according to `@ContextConfiguration` rules.

If you want the subclass configuration to replace inherited `locations` or `classes`, set `inheritLocations = false`:

~~~java
@ContextConfiguration(
        classes = OrderTestConfiguration.class,
        inheritLocations = false
)
class OrderRepositoryIsolatedTest extends BaseRepositoryTest {
}
~~~

Similarly, `inheritInitializers` controls inheriting `ApplicationContextInitializer` instances. The default is `true`; set it to `false` if the subclass needs to use only its own list of initializers.

### `@ActiveProfiles`: Inheriting Profiles

`@ActiveProfiles` inherits profiles from the superclass by default. Example:

~~~java
@ActiveProfiles("test")
abstract class BaseServiceTest {
}

@ActiveProfiles("database")
class DatabaseServiceTest extends BaseServiceTest {
}
~~~

With the default configuration, the subclass profiles are merged with the inherited profiles. If you want the subclass to use only the `database` profile, set `inheritProfiles = false`:

~~~java
@ActiveProfiles(
        profiles = "database",
        inheritProfiles = false
)
class DatabaseServiceIsolatedTest extends BaseServiceTest {
}
~~~

Profiles can affect which beans are registered, so merging or replacing profiles can produce a different `ApplicationContext`.

### `@TestPropertySource`: Inheriting Files and Inline Properties

`@TestPropertySource` supports two separate inheritance attributes:

- `inheritLocations` controls inheriting property file locations.
- `inheritProperties` controls inheriting inline properties.

By default, both are `true`. Subclasses can add properties:

~~~java
@TestPropertySource(properties = "service.mode=stub")
abstract class BaseServiceTest {
}

@TestPropertySource(properties = "service.region=test")
class RegionalServiceTest extends BaseServiceTest {
}
~~~

If you want to drop inline properties from the parent class, use `inheritProperties = false`. If you want to replace the inherited configuration file list, use `inheritLocations = false`.

When the same key appears in multiple sources, property source precedence still determines the final value. Annotation inheritance and property precedence are two related but distinct steps: the first decides which sources are included in the configuration, while the second decides which source wins on lookup.

### `@TestExecutionListeners`: Inheriting Listeners

`@TestExecutionListeners` has an `inheritListeners` attribute. By default, listeners declared on a superclass can be inherited and merged with listeners on the subclass according to the corresponding merge mode.

If a subclass needs to replace the inherited listener set, you can set `inheritListeners = false`. When changing listeners, consider Spring's default listeners such as those for dependency injection and transactions. Missing required listeners can prevent `@Autowired` on the test instance or test-managed transactions from working as expected.

## 4. JUnit Jupiter `@Nested` Is a Nested Class, Not a Subclass

JUnit Jupiter uses `@Nested` to group test classes inside another test class. A nested test class must be a non-static inner class.

Example:

~~~java
@SpringJUnitConfig(OrderTestConfiguration.class)
class OrderServiceTests {

    @Autowired
    OrderService orderService;

    @Nested
    class WhenOrderIsValid {

        @Test
        void confirmsOrder() {
            // Test for the valid order case.
        }
    }

    @Nested
    class WhenStockIsInsufficient {

        @Test
        void rejectsOrder() {
            // Test for the insufficient stock case.
        }
    }
}
~~~

Nested classes help group tests by business context or state. JUnit runs test methods in nested classes according to Jupiter's lifecycle and maintains the relationship with the enclosing test instance.

However, a nested class is still not a subclass of the enclosing class. Therefore, Java `@Inherited` rules are not sufficient to explain whether Spring passes configuration from the outer class into the nested class.

The Spring TestContext Framework provides `@NestedTestConfiguration` for this scenario.

## 5. `@NestedTestConfiguration` Controls Inheriting Configuration from the Enclosing Class

`@NestedTestConfiguration` lets you decide whether test configuration annotations on an enclosing class are inherited by nested test classes.

The annotation resides in the package:

~~~java
import org.springframework.test.context.NestedTestConfiguration;
~~~

There are two modes:

| Mode | Behavior |
|---|---|
| INHERIT | The nested test class inherits test configuration annotations from the enclosing class |
| OVERRIDE | Test configuration annotations on the enclosing class are not inherited into the nested test class |

The default in the Spring TestContext Framework is `INHERIT`. This feature has been available since Spring Framework 5.3.

### INHERIT: Using the Outer Class's Configuration

Example:

~~~java
@SpringJUnitConfig(OrderTestConfiguration.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "service.mode=stub")
class OrderServiceTests {

    @Nested
    class WhenOrderIsValid {

        @Test
        void usesSharedTestConfiguration() {
            // Nested test uses the enclosing class's configuration.
        }
    }
}
~~~

When using `INHERIT` mode, the nested class can receive test configuration annotations from `OrderServiceTests`. Thus, the nested test uses the same context configuration, profiles, and property sources declared on the outer class, unless it adds or overrides them according to the rules of the corresponding annotation.

This mode is suitable when nested classes simply group tests by business scenario and need the same Spring environment.

### OVERRIDE: Nested Class Uses Its Own Configuration

If a nested test needs a different context or configuration, you can place `@NestedTestConfiguration` on the nested class:

~~~java
@SpringJUnitConfig(OrderTestConfiguration.class)
class OrderServiceTests {

    @Nested
    @NestedTestConfiguration(
            NestedTestConfiguration.EnclosingConfiguration.OVERRIDE
    )
    @SpringJUnitConfig(AlternativeOrderTestConfiguration.class)
    class WhenUsingAlternativeConfiguration {

        @Test
        void usesAlternativeContext() {
            // Test uses the configuration declared on the nested class.
        }
    }
}
~~~

`OVERRIDE` prevents test configuration from the enclosing class from being applied to that nested class. The nested class can declare its own configuration using `@SpringJUnitConfig` or an appropriate annotation.

If the nested class does not declare a replacement configuration, Spring processes it according to the remaining metadata and bootstrapper on the test class; you should not expect the enclosing class's configuration to still be applied automatically once `OVERRIDE` is chosen.

### Setting the Mode on the Enclosing Class

You can place `@NestedTestConfiguration` on the enclosing class to apply a policy to nested classes inside it:

~~~java
@SpringJUnitConfig(OrderTestConfiguration.class)
@NestedTestConfiguration(
        NestedTestConfiguration.EnclosingConfiguration.OVERRIDE
)
class OrderServiceTests {

    @Nested
    class UsesOwnConfiguration {
        // Nested classes inherit the OVERRIDE policy.
    }
}
~~~

When a nested class needs to switch back to another mode, you can declare `@NestedTestConfiguration` explicitly on that class. Putting the policy in one shared place helps nested tests follow the same convention.

### Changing the Global Default

You can configure the default mode for the entire test suite via a system property:

~~~text
-Dspring.test.context.defaultEnclosingConfiguration=OVERRIDE
~~~

The value can be `INHERIT` or `OVERRIDE`. The property must be passed to the JVM executing the tests.

Gradle example:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty(
        'spring.test.context.defaultEnclosingConfiguration',
        'OVERRIDE'
    )
}
~~~

Maven Surefire example:

~~~xml
<systemPropertyVariables>
    <spring.test.context.defaultEnclosingConfiguration>
        OVERRIDE
    </spring.test.context.defaultEnclosingConfiguration>
</systemPropertyVariables>
~~~

Only change the global default when the project has a clear convention for nested tests. If only a few tests need separate configurations, placing `@NestedTestConfiguration` directly on the relevant class makes the intent easier to see.

## 6. How Is Inherited Configuration Merged in Nested Tests?

When the mode is `INHERIT`, Spring finds test configuration annotations on the enclosing class and combines them with annotations on the nested class according to each annotation's rules.

Example:

~~~java
@SpringJUnitConfig(SharedConfiguration.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "service.mode=stub")
class BaseOrderTests {

    @Nested
    @ActiveProfiles("database")
    @TestPropertySource(properties = "service.region=local")
    class DatabaseScenario {
    }
}
~~~

Here, context configuration from the enclosing class is inherited. Profiles and properties are also processed according to the inheritance policies of the corresponding annotations. The nested class's profile can be merged with the profile from the outer class because `@ActiveProfiles` defaults to `inheritProfiles = true`.

If the nested class needs a completely separate profile:

~~~java
@Nested
@ActiveProfiles(
        profiles = "database",
        inheritProfiles = false
)
class DatabaseScenario {
}
~~~

Similarly, `@TestPropertySource` can set `inheritProperties` or `inheritLocations` to `false` to replace the corresponding part.

Two levels of control must be distinguished:

1. `@NestedTestConfiguration` decides whether to look up and inherit test configuration from the enclosing class.
2. Attributes such as `inheritProfiles`, `inheritLocations`, and `inheritProperties` decide how values are merged between classes within the permitted inheritance scope.

`OVERRIDE` at the enclosing configuration level does not mean all annotations on a superclass are removed. Inheritance via superclass and inheritance from an enclosing class are two different relationships. Configure the right annotation attributes when you need to control each source.

## 7. Example: Splitting Nested Tests by Scenario While Sharing a Spring Context

A service class may have multiple business scenarios:

~~~java
@SpringJUnitConfig(OrderTestConfiguration.class)
@ActiveProfiles("test")
class OrderServiceTests {

    @Autowired
    OrderService orderService;

    @Nested
    class WithAvailableStock {

        @Test
        void acceptsOrder() {
            OrderResult result =
                    orderService.place(new OrderCommand("SKU-01", 2));

            assertEquals(OrderStatus.ACCEPTED, result.status());
        }
    }

    @Nested
    class WithInsufficientStock {

        @Test
        void rejectsOrder() {
            OrderResult result =
                    orderService.place(new OrderCommand("SKU-02", 20));

            assertEquals(OrderStatus.REJECTED, result.status());
        }
    }
}
~~~

Two nested classes split scenarios by business conditions. Both use the test configuration on the enclosing class.

If their effective merged configurations are equivalent, Spring TestContext can reuse the same `ApplicationContext` cache entry. Splitting tests into nested classes does not automatically force Spring to create a new context for each class.

However, if each nested class adds different profiles, property sources, context customizers, or bean configurations, the cache key may differ and Spring needs separate contexts.

### Test Data Still Needs Isolation

Sharing a context does not mean sharing business state without control. If `OrderService` or a repository holds data that mutates between tests, data must be prepared and cleaned up per method.

You can use `@BeforeEach` in the nested class or test transactions depending on the dependency type. For database tests, transaction rollback can help isolate transactional changes. Side effects such as sent messages or completed HTTP requests are not automatically rolled back with the database.

Do not use `OVERRIDE` just to deal with leftover test data if the issue can be solved with fixtures or cleanup. `OVERRIDE` changes how context configuration is resolved and can increase the number of contexts initialized.

## 8. Example: Nested Test Needing a Different Context from the Outer Class

Suppose the default test group uses a fake payment gateway, while one nested test group needs a database configuration or a different implementation.

~~~java
@SpringJUnitConfig(FakePaymentConfiguration.class)
@ActiveProfiles("test")
class PaymentServiceTests {

    @Nested
    class UsesFakeGateway {
        // Inherits FakePaymentConfiguration and the test profile.
    }

    @Nested
    @NestedTestConfiguration(
            NestedTestConfiguration.EnclosingConfiguration.OVERRIDE
    )
    @SpringJUnitConfig(RealAdapterTestConfiguration.class)
    @ActiveProfiles("adapter-test")
    class UsesAdapterConfiguration {

        @Test
        void loadsAdapterContext() {
            // Verifies beans in the context dedicated to the adapter.
        }
    }
}
~~~

The `UsesAdapterConfiguration` nested class chooses `OVERRIDE` and declares its own configuration. Configuration from `PaymentServiceTests` is not inherited into this nested class.

If the separate configuration needs different profiles or properties, declare them directly. When the nested class uses a different context, Spring will create or retrieve the cache entry corresponding to its merged configuration.

This example fits when two test groups genuinely need different environments. If you only need to swap one dependency for a test, a bean override like `@MockitoBean` can be cleaner than creating a completely separate context.

## 9. Composed Annotations in Inherited Test Classes and Nested Tests

Composed annotations help package a group of configurations:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Inherited
@SpringBootTest
@ActiveProfiles("integration")
@TestPropertySource(properties = "service.mode=remote")
public @interface FullIntegrationTest {
}
~~~

Using on a base class:

~~~java
@FullIntegrationTest
abstract class BaseIntegrationTest {
}

class PaymentIntegrationTest extends BaseIntegrationTest {
}
~~~

If `@FullIntegrationTest` is marked `@Inherited`, the subclass can receive the annotation via the superclass under Java rules. Spring merged annotations continue reading meta-annotations such as `@SpringBootTest`, `@ActiveProfiles`, and `@TestPropertySource`.

With nested tests:

~~~java
@FullIntegrationTest
class PaymentIntegrationTests {

    @Nested
    class CardPayments {
        // Spring Test can inherit configuration from the enclosing class
        // by default via @NestedTestConfiguration(INHERIT).
    }
}
~~~

Inheritance into the nested class in this example is controlled by Spring `@NestedTestConfiguration`, not Java's `@Inherited`. If switched to `OVERRIDE`, test configuration from the enclosing class will not be applied by that mechanism.

When creating a composed annotation, test both scenarios: subclasses via `extends` and nested classes via `@Nested`. They use different mechanisms, so an annotation working in one scenario does not guarantee it works automatically in the other.

## 10. Notes on Method-Level Annotations

Class-level annotations and method-level annotations have different lookup scopes. `@Inherited` is only for class annotations and does not automatically pass method annotations to overriding methods.

Spring Test has specific rules for method-level annotations. For example, `@Sql` can be placed on a class or method to specify data-preparation scripts. `@Transactional` can be declared at the class or method level to configure test transactions. Merging class-level and method-level settings depends on the specific annotation.

With JUnit `@Nested`, lifecycle methods of the enclosing class can participate in the nested test lifecycle according to Jupiter rules. But that does not mean every annotation on a method of the enclosing class is treated as an annotation on a method of the nested class.

When a test behaves unexpectedly, locate where each annotation resides:

- On the superclass.
- On the enclosing class.
- On the nested class.
- On a method of the enclosing class.
- On a method of the nested class.
- On a composed annotation.

Then check the rules of that specific annotation rather than assuming all of them share the same inheritance mechanism.

## 11. Impact on the `ApplicationContext` Cache

Inherited configuration directly affects the merged configuration that Spring uses to look up an `ApplicationContext` in the cache.

If two nested classes inherit the same configuration and add no differences that alter the cache key, they can share a context. If a nested class changes profiles, properties, initializers, configuration classes, or context customizers, it may need a different context.

Example:

| Test class | Mode | Effective configuration | Context sharing potential |
|---|---|---|---|
| OrderServiceTests | Enclosing class | Config A, profile test | Has baseline context |
| WhenOrderValid | INHERIT | Inherits Config A, profile test | Can use baseline context |
| WhenStockMissing | INHERIT | Inherits Config A, profile test | Can use baseline context |
| UsesDatabase | INHERIT, adds profile database | Config A, profiles test + database if merged | May need a different context |
| UsesAlternativeConfig | OVERRIDE | Config B and separate config | Needs a context matching Config B |

The cache key is not based solely on the test class name. It is based on the merged configuration and related components. Therefore, two differently named test classes can still share a context, while two nested classes inside the same enclosing class can still need separate contexts.

If you observe many contexts being initialized, inspect profiles, properties, customizers, and inheritance before increasing the cache size. Many unnecessary configuration variants can fragment the cache.

## 12. Common Mistakes and How to Handle Them

### Thinking `@Inherited` Propagates Annotations into Nested Classes

`@Inherited` only handles superclass relationships. A nested class is not a subclass of its enclosing class.

With Spring Test, use `@NestedTestConfiguration` to control inheriting configuration annotations from the enclosing class.

### Confusing `@Nested` with `extends`

JUnit `@Nested` only declares a nested test structure. It does not create a Java inheritance relationship and does not make the nested class a subclass of the outer class.

### Nested Test Unexpectedly Receives Profiles or Properties from the Outer Class

By default, Spring TestContext uses `@NestedTestConfiguration(INHERIT)`. If a nested class needs independent configuration, declare `OVERRIDE` and supply its own configuration.

If you only want to replace part of the profiles or properties in a superclass relationship, use the `inheritProfiles`, `inheritProperties`, or `inheritLocations` attributes respectively.

### Setting `OVERRIDE` but Forgetting Replacement Configuration

`OVERRIDE` prevents test configuration from the enclosing class from being inherited. If the nested class needs a Spring context, declare the appropriate configuration on the nested class or ensure its bootstrapper can find a valid configuration.

### Subclass Does Not Receive Expected Properties

Check whether `inheritProperties`/`inheritLocations` on `@TestPropertySource` is disabled. Check if a property with the same key appears in multiple sources and which source has higher precedence.

### Profiles Accumulate Unexpectedly

`@ActiveProfiles` inherits profiles from superclasses by default. If you need a separate profile list, set `inheritProfiles = false`. With nested classes, also check the `@NestedTestConfiguration` mode.

### Composed Annotation Does Not Behave as Expected

Check `@Retention(RUNTIME)`, `@Target`, meta-annotations, and `@AliasFor`. If inheritance via superclass is needed, add `@Inherited` onto the composed annotation. If applying from an enclosing class to a nested class is needed, check `@NestedTestConfiguration`.

### Context Cache Grows Rapidly When Using Many Nested Classes

Nested classes can create many context configurations if each class declares different profiles, properties, or customizers. Standardize shared configuration and only create separate contexts when the behavior under test truly requires a different environment.

### Changing an Annotation on a Base Class Breaks Many Tests

A base test class can be the shared configuration source for many subclasses. When modifying profiles, properties, or context configuration, review the impact across the entire hierarchy. If a group of tests needs a separate environment, split the base class or use the appropriate inheritance attributes.

## 13. Diagnostic Process When Annotations Are Not Inherited Correctly

When a test class receives a different configuration than expected, check in this order:

1. Determine whether the relationship between the two classes is `extends` or enclosing/nested.
2. If it is a superclass, check whether the annotation supports inheritance and its corresponding `inherit` attribute.
3. If it is a nested test, check whether `@NestedTestConfiguration` is `INHERIT` or `OVERRIDE`.
4. Check whether a composed annotation has the right meta-annotations and aliases.
5. Check whether `@ActiveProfiles`, `@ContextConfiguration`, and `@TestPropertySource` are merging or replacing inherited values.
6. Check method-level annotations against the specific rules of each annotation.
7. Inspect the effective `ApplicationContext` configuration and cache key.
8. Run the nested class in isolation and run the whole test class to confirm behavior does not depend on execution order.

You can enable Spring TestContext logging to observe the bootstrap and caching process:

~~~properties
logging.level.org.springframework.test.context=DEBUG
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Logs help identify contexts being loaded, reused, or created anew. If the test uses Spring Boot, you can raise the log level for relevant configuration packages when diagnosing property sources or bean conditions.

## 14. Choosing the Right Mechanism for Your Goal

| Goal | Mechanism to Use |
|---|---|
| Subclass receives class-level annotation from superclass | @Inherited if supported by the annotation, or Spring merged annotation rules |
| Bundle Spring configuration into a custom annotation | Meta-annotations and @AliasFor |
| Split tests into nested groups sharing a context | JUnit @Nested with default @NestedTestConfiguration(INHERIT) |
| Nested class needs independent Spring configuration | @NestedTestConfiguration(OVERRIDE) and separate configuration |
| Replace profiles inherited from superclass | @ActiveProfiles(inheritProfiles = false) |
| Replace inherited property locations | @TestPropertySource(inheritLocations = false) |
| Replace inherited inline properties | @TestPropertySource(inheritProperties = false) |
| Replace inherited context classes/locations | @ContextConfiguration(inheritLocations = false) |
| Replace inherited initializers | @ContextConfiguration(inheritInitializers = false) |
| Replace inherited listeners | @TestExecutionListeners(inheritListeners = false) |

When designing a test suite, put shared configuration on a base class or enclosing class if tests truly need the same environment. Use nested classes to group business scenarios. When a nested test group needs a different context, choose `OVERRIDE` and declare dedicated configuration. With composed annotations, clearly distinguish Java inheritance, Spring meta-annotations, and nested test rules.

Spring supports multiple layers of annotation inheritance because tests can be organized by superclass, composed annotations, or nested structures. Each mechanism solves a distinct need. Understanding the relationship between classes and annotation sources keeps Spring TestContext configuration predictable, reduces unnecessary contexts, and keeps the test suite readable as the number of scenarios grows.

