# @NestedTestConfiguration to Control Configuration Inheritance

JUnit Jupiter allows placing test classes inside another test class using the **@Nested** annotation. This organization helps group test scenarios around a common behavior or shared state. Meanwhile, the Spring TestContext Framework can inherit test configuration from the enclosing class so that nested tests share the same Spring configuration and environment.

Inheriting configuration reduces duplication, but sometimes a nested class needs its own `ApplicationContext`, profile, property, or test configuration. If every annotation on the outer class continues to affect the nested class, creating an isolated test inside the same nested tree can become difficult.

**@NestedTestConfiguration** allows controlling how Spring TestContext handles test annotations from enclosing classes. The two main modes are:

- **INHERIT:** the nested test class inherits test annotations from the enclosing class. This is the default mode.
- **OVERRIDE:** the nested test class does not inherit test annotations from the enclosing class; it uses the configuration declared within its own test branch.

This annotation is especially useful when combining JUnit Jupiter `@Nested` with Spring configurations such as `@SpringJUnitConfig`, `@SpringJUnitWebConfig`, `@ContextConfiguration`, `@ActiveProfiles`, `@TestPropertySource`, and other TestContext annotations.

## 1. The Configuration Inheritance Problem in Nested Tests

Suppose a group of tests verifies product management features:

~~~java
@SpringJUnitConfig(ProductTestConfig.class)
class ProductServiceTests {

    @Autowired
    ProductService productService;

    @Nested
    class SearchTests {
        @Test
        void finds_products_by_name() {
            // ...
        }
    }

    @Nested
    class UpdateTests {
        @Test
        void updates_product_price() {
            // ...
        }
    }
}
~~~

Both nested classes belong to the same test tree as `ProductServiceTests`. By default, Spring TestContext inherits test configuration from the enclosing class. Thus, the nested tests can use `ProductTestConfig` without repeating `@SpringJUnitConfig`.

This is useful when test groups share the need for:

- An `ApplicationContext` configured with shared beans.
- The same active profiles.
- The same test property sources.
- The same `TestExecutionListener`s or `TestContext` setup.
- The same web or database configuration.

However, suppose `UpdateTests` needs a separate context with a fake repository or a different profile. If configuration from the outer class continues to be inherited, the nested test might receive configuration it does not want. In that case, `@NestedTestConfiguration` specifies how to handle configuration coming from the enclosing class.

## 2. What Is `@NestedTestConfiguration`?

`@NestedTestConfiguration` belongs to the Spring TestContext Framework:

~~~java
import org.springframework.test.context.NestedTestConfiguration;
import org.springframework.test.context.NestedTestConfiguration.EnclosingConfiguration;
~~~

This annotation declares the mode for inheriting test annotations from the enclosing test class. It can be placed on a test class or used as a meta-annotation in a composed annotation.

Basic declaration:

~~~java
@NestedTestConfiguration(EnclosingConfiguration.INHERIT)
class ProductServiceTests {
}
~~~

Or:

~~~java
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
class IsolatedNestedTests {
}
~~~

The annotation does not create an `ApplicationContext` by itself, does not change the JUnit lifecycle, and does not decide whether a test class is executed. It instructs Spring TestContext whether to accept test annotations from the enclosing class.

### 2.1. Two Modes

| Mode | Behavior | When Appropriate |
| --- | --- | --- |
| INHERIT | Inherits test annotations from the enclosing class | Nested tests share a common configuration |
| OVERRIDE | Does not inherit test annotations from the enclosing class | Nested test needs its own configuration or isolation from outer configuration |

`INHERIT` is the default if no other configuration is present. Therefore, many existing test classes using `@Nested` continue to work without adding `@NestedTestConfiguration`.

### 2.2. The Annotation Can Be Inherited Through Class Hierarchy

`@NestedTestConfiguration` can be declared on a test class or superclass. The declared mode can apply to nested test classes within the corresponding class hierarchy. This helps a large test group standardize how enclosing configuration is handled.

If only one nested branch needs different behavior, you can declare the appropriate mode on that branch. Place the annotation close to where the impact needs to be clear so readers understand why outer configuration is inherited or ignored.

## 3. INHERIT: Inheriting Configuration from the Enclosing Class

With `INHERIT`, Spring TestContext looks up test annotations on the enclosing class and includes them when building configuration for the nested test.

Example:

~~~java
@SpringJUnitConfig(ProductTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "catalog.page-size=20")
class ProductServiceTests {

    @Autowired
    ProductService productService;

    @Nested
    class SearchTests {

        @Test
        void uses_shared_product_configuration() {
            // Can use ProductService and configuration from the outer class.
        }
    }

    @Nested
    class DetailTests {

        @Test
        void loads_product_details() {
            // Also uses shared configuration if no other configuration exists.
        }
    }
}
~~~

In the example, the nested tests inherit Spring configuration and profiles from `ProductServiceTests`. The `catalog.page-size` property is also part of their test configuration.

Not all annotations merge in the same way. `@NestedTestConfiguration` decides whether to inherit annotations from the enclosing class; then each Spring annotation applies its own merge rules.

For example:

- `@ContextConfiguration` has attributes such as `inheritLocations` and `inheritInitializers` to control inheriting configuration from superclasses.
- `@ActiveProfiles` has `inheritProfiles` to control inheriting profiles along the class hierarchy.
- `@TestPropertySource` has rules for combining resource locations and inline properties.

Those rules still matter. `@NestedTestConfiguration` does not replace the individual inheritance attributes of each annotation.

### 3.1. Nested Class Supplementing Configuration

A nested test can inherit shared configuration and add its own configuration:

~~~java
@SpringJUnitConfig(ProductTestConfig.class)
@ActiveProfiles("test")
class ProductServiceTests {

    @Nested
    @TestPropertySource(properties = "catalog.search-mode=exact")
    class ExactSearchTests {
        @Test
        void searches_using_exact_mode() {
            // ...
        }
    }
}
~~~

In `INHERIT` mode, the nested test receives annotations from the enclosing class along with annotations declared on itself. Property sources are merged according to `@TestPropertySource` rules.

This is useful when test groups share a base context while needing some additional configuration to represent a specific scenario.

## 4. OVERRIDE: Ignoring Inherited Annotations from the Enclosing Class

With `OVERRIDE`, Spring TestContext does not inherit test annotations from the enclosing class. The nested test must declare the configuration it actually uses.

Example:

~~~java
@SpringJUnitConfig(ProductTestConfig.class)
class ProductServiceTests {

    @Nested
    class StandardSearchTests {
        @Test
        void searches_with_default_configuration() {
            // Inherits ProductTestConfig configuration.
        }
    }

    @Nested
    @NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
    @SpringJUnitConfig(AlternativeProductTestConfig.class)
    class IsolatedSearchTests {

        @Test
        void searches_with_alternative_configuration() {
            // Uses configuration declared in this branch.
        }
    }
}
~~~

`IsolatedSearchTests` does not inherit test configuration from `ProductServiceTests`. It declares its own `AlternativeProductTestConfig`. This lets the test branch express an independent environment.

If the nested class fails to declare the needed configuration after choosing `OVERRIDE`, Spring may fail to find context configuration or fail to create the context. `OVERRIDE` does not automatically create a complete default context; it only changes the inheritance rule from the enclosing class.

### 4.1. When Should `OVERRIDE` Be Used?

`OVERRIDE` is appropriate when a nested test:

- Needs a different `ApplicationContext` from the outer class.
- Needs its own profiles or property sources without inheriting outer configuration.
- Needs to test an error configuration or a minimal standalone configuration.
- Uses a different set of beans, such as swapping an adapter or toggling a feature.
- Needs to prevent outer annotations from affecting the test branch.

Use `OVERRIDE` when independence is an intentional part of the test design. If the nested class only needs to add a property or a profile in a supported mergeable way, `INHERIT` can be simpler.

### 4.2. `OVERRIDE` Does Not Erase Every Inheritance Relationship

`OVERRIDE` concerns test annotations from the enclosing class. It does not change all inheritance rules of Java, JUnit, or Spring.

Distinguish between:

- Inheriting annotations from an enclosing class: controlled by `@NestedTestConfiguration`.
- Inheriting annotations from a superclass: governed by each annotation's inheritance mechanism and its own attributes.
- Inheriting test methods or lifecycle under JUnit: managed by JUnit Jupiter.
- Inheriting bean configuration between parent/child contexts: managed by context hierarchy configuration.

For example, `@ContextConfiguration(inheritLocations = false)` controls inheriting locations from a superclass according to that annotation's rules. It is not a direct substitute for `@NestedTestConfiguration(OVERRIDE)`, which controls annotations from the enclosing class.

## 5. Global Default Configuration

The default of Spring TestContext is `INHERIT`. You can change the default for the entire test JVM using a system property:

~~~text
-Dspring.test.enclosing.configuration=override
~~~

Valid values are:

- `inherit`
- `override`

Gradle configuration example:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty(
        "spring.test.enclosing.configuration",
        "override"
    )
}
~~~

With Maven Surefire, you can pass the system property via plugin configuration or the corresponding JVM arguments:

~~~xml
<systemPropertyVariables>
    <spring.test.enclosing.configuration>override</spring.test.enclosing.configuration>
</systemPropertyVariables>
~~~

The system property must be effective in the test JVM before Spring TestContext processes test classes. Putting it inside an application context property source does not have the same meaning, because this setting controls how the framework discovers test annotations.

### 5.1. Choosing a Global Default vs. Per-Class Selection

If most tests in the project need to inherit configuration from the enclosing class, keeping the `INHERIT` default is usually easy to understand.

If the project wants every nested test to declare its own configuration, you can set the global default to `OVERRIDE`. Then, test classes that need to share configuration can declare `INHERIT` explicitly.

Example:

~~~java
@NestedTestConfiguration(EnclosingConfiguration.INHERIT)
@SpringJUnitConfig(SharedTestConfig.class)
class SharedContextTests {
    @Nested
    class NestedFeatureTests {
        // Inherits shared configuration.
    }
}
~~~

When changing the global default, consider the impact on the entire test suite. Some nested classes may be relying on outer configuration without redeclaring it. Changing the property can stop them from loading the context as before.

### 5.2. Explicit Annotations Help Readers Understand Tests

When a project has many test groups with different purposes, declaring `@NestedTestConfiguration` directly on the class makes intent clearer. This is especially helpful when a test class is shared across modules or extended by other test classes.

There is no need to add the annotation everywhere if the project default is clear and consistent. Use it when documenting a decision different from the default or when the inheritance scope is not obvious.

## 6. Which Annotations Are Affected?

`@NestedTestConfiguration` affects how Spring TestContext processes test annotations on the enclosing class. Common annotation groups include:

| Group | Examples | Content That Can Be Inherited |
| --- | --- | --- |
| Context bootstrap | @BootstrapWith, @ContextConfiguration | Bootstrapper and context configuration sources |
| Web context | @WebAppConfiguration | Web application context configuration |
| Profile | @ActiveProfiles | Active profiles |
| Property | @TestPropertySource | Resources and inline properties |
| Test execution | @TestExecutionListeners | TestContext listeners |
| Lifecycle/context state | @DirtiesContext | Rules for marking context dirty |
| Transaction | @Transactional, @Commit, @Rollback | Transaction configuration for tests |
| SQL test support | @Sql, @SqlConfig, @SqlMergeMode | SQL scripts and execution behavior |
| Event/application test support | Related TestContext annotations | Configuration supported for inheritance by the framework |
| Bean override | @MockitoBean, @MockitoSpyBean, and corresponding override declarations | Bean override metadata in test configuration |

The exact scope of annotations supported by Spring can depend on the version and integration modules. Consult the Javadoc of the Spring version in use when a test relies on a specific annotation. Do not assume every JUnit annotation or every Java annotation is controlled by `@NestedTestConfiguration`.

### 6.1. JUnit Annotations Are Not TestContext Annotations

`@Nested` is a JUnit Jupiter annotation that identifies a nested test class. `@Test`, `@BeforeEach`, `@AfterEach`, and extension annotations belong to the JUnit mechanism.

`@NestedTestConfiguration` controls whether Spring TestContext inherits test annotations from the enclosing class. It does not change JUnit's test method discovery rules or turn an ordinary class into a nested test.

`SpringExtension` must still be registered appropriately, such as via `@SpringJUnitConfig` or `@ExtendWith(SpringExtension.class)`. If the test class configuration is altered by `OVERRIDE`, ensure the nested class still has a way to activate Spring TestContext as needed.

## 7. Combining with `@SpringJUnitConfig`

`@SpringJUnitConfig` is a composed annotation combining `SpringExtension` and `ContextConfiguration`. When placed on the outer test class, nested tests can inherit that configuration by default.

Example:

~~~java
@SpringJUnitConfig(classes = CatalogTestConfig.class)
class CatalogTests {

    @Autowired
    CatalogService catalogService;

    @Nested
    class FindTests {

        @Test
        void finds_existing_item() {
            assertThat(catalogService.findById("SKU-1"))
                .isPresent();
        }
    }
}
~~~

If `FindTests` needs its own configuration:

~~~java
@Nested
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
@SpringJUnitConfig(classes = CatalogIsolatedTestConfig.class)
class FindTests {

    @Autowired
    CatalogService catalogService;
}
~~~

The important point is that the nested test must have the configuration and extension required for its goal. When using composed annotations, remember that a composed annotation can carry multiple pieces of Spring metadata at once.

### 7.1. Context Configuration and Test Configuration Are Not the Same Thing

`@NestedTestConfiguration` does not decide on its own which beans exist in the context. It decides whether annotations from the enclosing class participate in the test configuration. After that, `@ContextConfiguration` or `@SpringJUnitConfig` determines where the context is loaded from.

For example:

- `INHERIT` lets the nested class receive `@SpringJUnitConfig` from the outer class.
- `OVERRIDE` excludes those annotations from inheritance from the enclosing class.
- If the nested class declares a different `@SpringJUnitConfig`, Spring uses the configuration declared in that branch.

## 8. Combining with `@SpringJUnitWebConfig`

`@SpringJUnitWebConfig` combines `SpringExtension`, `ContextConfiguration`, and `WebAppConfiguration`. Therefore, nested web tests are also affected by `@NestedTestConfiguration`.

Example:

~~~java
@SpringJUnitWebConfig(classes = WebTestConfig.class)
class WebControllerTests {

    @Autowired
    WebApplicationContext context;

    @Nested
    class PublicEndpointTests {
        // Inherits web context from the outer class.
    }

    @Nested
    @NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
    @SpringJUnitWebConfig(classes = AdminWebTestConfig.class)
    class AdminEndpointTests {
        // Uses separate web configuration.
    }
}
~~~

`PublicEndpointTests` can share the `WebApplicationContext` configured on the outer class. `AdminEndpointTests` selects `OVERRIDE` and declares its own web configuration.

If the two branches produce different contexts, Spring may create different cache entries. If they have the same merged configuration, `TestContext` can reuse the context through the usual caching mechanism.

## 9. Combining with `@ActiveProfiles` and `@TestPropertySource`

A common case is when the outer class sets shared profiles and properties, while the nested class changes the environment.

### 9.1. `INHERIT` with Merged Profiles

~~~java
@SpringJUnitConfig(classes = FeatureTestConfig.class)
@ActiveProfiles("test")
class FeatureTests {

    @Nested
    @ActiveProfiles("search")
    class SearchTests {
        @Test
        void uses_search_profile() {
            // ...
        }
    }
}
~~~

In `INHERIT` mode, profiles from the enclosing class can be inherited and combined according to `@ActiveProfiles` rules. By default, `@ActiveProfiles` has a mechanism to inherit profiles from superclasses; when a nested class declares its own profiles, verify the merge rules and the `inheritProfiles` attribute of the Spring version in use.

If you want the nested test to use a completely independent profile, you can use `OVERRIDE` and declare the separate profile:

~~~java
@Nested
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
@SpringJUnitConfig(classes = SearchOnlyTestConfig.class)
@ActiveProfiles("search")
class SearchTests {
}
~~~

### 9.2. `INHERIT` with Additional Properties

~~~java
@SpringJUnitConfig(classes = FeatureTestConfig.class)
@TestPropertySource(properties = "feature.enabled=true")
class FeatureTests {

    @Nested
    @TestPropertySource(properties = "feature.mode=fast")
    class FastModeTests {
        @Test
        void uses_fast_mode() {
            // ...
        }
    }
}
~~~

The nested class inherits property sources from the enclosing class and adds its own properties according to `@TestPropertySource` rules. If you need to replace the entire property source of the nested branch, consider `OVERRIDE` and declare the new source clearly.

## 10. Impact on the `ApplicationContext` Cache

The TestContext Framework caches `ApplicationContext` instances by merged configuration. `@NestedTestConfiguration` affects which annotations are fed into the merge process, so it can indirectly affect the context cache.

For example:

- Two nested classes using `INHERIT` and receiving the same configuration from the outer class can share a context.
- A nested class using `OVERRIDE` and loading its own configuration can create a different context.
- Changing active profiles, property sources, or bean overrides can produce a different cache key.

Having nested classes does not automatically make Spring create a new context. A context is reused when the merged configuration is equivalent and the context is still in the cache.

### 10.1. Context Cache Does Not Replace Data Isolation

Nested tests sharing a context may simultaneously access singleton beans. If a bean holds mutable state, tests must reset state or design the bean to be stateless.

Database state, files, messages, and external systems are not automatically cleaned by the context cache. Use transactions, fixtures, cleanup, or dedicated resources.

### 10.2. Using `OVERRIDE` Can Increase the Number of Contexts

If every nested class declares its own configuration, Spring may have to create many contexts. This can slow down the suite.

Use a separate context when the test genuinely needs a different environment. If you only need to change a business input, pass data into the test instead of creating a new Spring configuration.

## 11. Distinguishing the Enclosing Class from a Superclass

This is a common point of confusion when both nested tests and test class inheritance exist.

Suppose:

~~~java
abstract class BaseCatalogTests {
    // Shared configuration or setup via superclass.
}

@SpringJUnitConfig(CatalogTestConfig.class)
class CatalogTests extends BaseCatalogTests {

    @Nested
    class SearchTests {
        // Nested test inside CatalogTests.
    }
}
~~~

There are two different relationships:

1. `CatalogTests` extends `BaseCatalogTests` in the Java class hierarchy.
2. `SearchTests` resides inside `CatalogTests` via an enclosing class relationship.

`@NestedTestConfiguration` controls whether Spring TestContext inherits annotations from the enclosing class relationship. Attributes like `inheritLocations` or `inheritProfiles` control each annotation's own inheritance rules in the class hierarchy. Do not use one mechanism to infer the behavior of the other.

### 11.1. When a Superclass Also Has `@NestedTestConfiguration`

If a superclass or enclosing test class declares `@NestedTestConfiguration`, that mode can be inherited across the class hierarchy due to the annotation's characteristics. Place the mode on a base test class when the entire test group needs the same policy.

If a subclass needs to change the policy, you can declare `@NestedTestConfiguration` directly on the subclass. This keeps local decisions clear and avoids changing the default for unrelated tests.

## 12. Using `@NestedTestConfiguration` as a Meta-Annotation

Test groups may need a uniform inheritance policy. You can create a composed annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
public @interface IsolatedNestedTests {
}
~~~

Then:

~~~java
@IsolatedNestedTests
class PaymentTests {
    @Nested
    class ProviderTests {
        // The nested branch follows the OVERRIDE policy.
    }
}
~~~

Meta-annotations help package a shared convention. Only create one when multiple test classes genuinely need the same policy and the annotation name expresses the meaning. For a single case, declaring `@NestedTestConfiguration` directly is usually easier to read.

## 13. Common Mistakes

### Nested Class No Longer Receives Spring Configuration

If `OVERRIDE` is chosen and you forget to declare separate configuration, Spring may fail to find context configuration or fail to create required beans. Check composed annotations, `classes`/`locations` configuration, and `SpringExtension`.

### Thinking `OVERRIDE` Removes All Configuration from Superclasses

`OVERRIDE` controls annotations from the enclosing class. Java inheritance and each annotation's own rules still need to be considered independently.

### Using `inheritLocations` Instead of `@NestedTestConfiguration`

`inheritLocations` controls inheriting resource locations in `@ContextConfiguration` along the class hierarchy. It does not replace the policy for inheriting annotations from an enclosing test class.

### Placing `@NestedTestConfiguration` at the Wrong Scope

If the annotation is placed on a superclass or outer class, the mode may affect more nested tests than intended. Place the annotation close to the branch that needs to change and review the class hierarchy scope.

### Creating Too Many Unnecessary Contexts

Each nested class declaring different profiles or properties can produce a different context cache key. Only create a separate context when the testing environment truly differs.

### Confusing `@NestedTestConfiguration` with JUnit `@Nested`

JUnit's `@Nested` identifies a nested test class. `@NestedTestConfiguration` controls Spring TestContext inheritance. The two annotations complement each other and cannot replace one another.

### Assuming Every Java Annotation Is Controlled

This annotation is meant for test annotations processed by Spring TestContext. It does not alter every JUnit annotation or annotations from other frameworks.

## 14. Process for Choosing `INHERIT` vs. `OVERRIDE`

**Step 1 – Identify the outer class configuration.** Record the context configuration, profiles, property sources, listeners, transactions, and bean overrides declared on the outer class.

**Step 2 – Determine what the nested test needs.** Does the nested test share beans and environment, or does it need its own context?

**Step 3 – Choose `INHERIT` if shared configuration is intentional.** Allow Spring to inherit annotations from the enclosing class and use each annotation's merge rules.

**Step 4 – Choose `OVERRIDE` if independence is needed.** Prevent Spring from inheriting test annotations from the enclosing class and declare full configuration for the nested branch.

**Step 5 – Check superclasses separately.** Check whether `inheritLocations`, `inheritProfiles`, and Java inheritance rules apply.

**Step 6 – Check the extension.** Ensure `SpringExtension` is registered appropriately so the nested test uses Spring TestContext.

**Step 7 – Observe the context cache.** If configurations differ, accept a separate context; if configurations are equivalent, let TestContext reuse the cache.

**Step 8 – Run tests individually and as a suite.** Verify nested tests do not depend on the state or order of other branches.

## 15. Quick Decision Table

| Question | Choice |
| --- | --- |
| Nested tests share the outer class configuration? | INHERIT |
| Nested test needs to add properties or mergeable annotations? | Usually INHERIT |
| Nested test needs an independent context/profile? | OVERRIDE and declare separate configuration |
| Want to change the default for the whole test JVM? | System property spring.test.enclosing.configuration |
| Only want to stop inheriting locations from a superclass? | Look at inheritLocations of @ContextConfiguration |
| Want to change JUnit nested lifecycle? | Use JUnit Jupiter mechanisms, not @NestedTestConfiguration |
| Want multiple nested tests to share one policy? | Place the annotation on a base/outer class or create a meta-annotation |

## Conclusion

`@NestedTestConfiguration` allows Spring TestContext to control inheriting test annotations from the enclosing class of JUnit Jupiter nested tests. `INHERIT` is the default and fits when test branches share configuration. `OVERRIDE` makes a nested branch independent from annotations on the enclosing class so it can declare its own context, profiles, or properties as needed.

Distinguish this mechanism from Java inheritance from superclasses, the specific merge rules of `@ContextConfiguration` or `@ActiveProfiles`, and the lifecycle managed by JUnit. When choosing the right scope, nested tests can reuse shared configuration where appropriate, create separate contexts when needed, and keep the goal of each test branch clear.
