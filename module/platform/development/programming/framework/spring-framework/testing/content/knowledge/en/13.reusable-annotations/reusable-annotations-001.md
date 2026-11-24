# Meta-annotations and Composed Annotations for Testing

A Spring project often has many test classes repeating the same group of annotations: `@SpringBootTest`, `@ActiveProfiles`, `@Transactional`, `@AutoConfigureMockMvc`, `@Import`, or a test slice. When each class declares that group of annotations on its own, configurations easily drift between tests, and changing a shared convention requires editing many places.

Java allows an annotation to be placed on another annotation. This way of combining them is called a **meta-annotation**. From that, you can define a composed annotation that carries multiple existing annotations, and then use a short name that expresses the meaning of the test group. Spring Test, Spring Boot, and JUnit Jupiter all support multiple forms of annotation composition, helping reuse test configuration while preserving customizability.

## 1. What Is a Meta-annotation in Java?

An annotation in Java is also a declaration type. Therefore, an annotation can be annotated with other annotations to describe where it is allowed to be used, how long it is retained, or how tools process it.

For example, a custom annotation typically has the following meta-annotations:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface FastTest {
}
```

The annotations here have the following meanings:

- `@Target` specifies where the annotation is allowed to be placed, such as on a class, method, field, or annotation declaration.
- `@Retention` specifies until which stage the annotation is retained: source, class file, or runtime.
- `@Documented` requests that the annotation appear in the Javadoc documentation of the element that uses it.
- `@Inherited` can make a class-level annotation inherited from a superclass according to Java rules.

For an annotation to be read by JUnit or Spring at runtime, `RetentionPolicy.RUNTIME` is normally required. If the annotation is only retained until compile time, the framework cannot rely on runtime reflection to detect it.

### 1.1. Annotations Can Also Carry Other Annotations

An annotation can be marked with existing annotations:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Test
@Tag("fast")
public @interface FastTest {
}
```

`FastTest` is a JUnit meta-annotation because it carries `@Test` and `@Tag`. When JUnit detects a method with `@FastTest`, that method is treated as a test and has the `fast` tag.

Such an annotation is commonly called a *composed annotation*. It does not create a new test execution mechanism; it packages annotations that the framework already understands into a named configuration that is easy to use.

## 2. Composed Annotations in JUnit Jupiter

JUnit Jupiter supports annotation composition. Annotations such as `@Test`, `@Tag`, and `@ExtendWith` can be used directly or through an annotation defined by the project.

For example, a project has many tests that need to carry the same tag and the same extension:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Test
@Tag("integration")
@ExtendWith(DatabaseCleanupExtension.class)
public @interface DatabaseIntegrationTest {
}
```

A test using this annotation:

```java
class CustomerRepositoryTest {
    @DatabaseIntegrationTest
    void savesCustomerAndCleansDatabase() {
        // JUnit executes this as a test method.
    }
}
```

JUnit recognizes `@Test` via meta-annotation, attaches the `integration` tag, and registers the declared extension. When you need to run a group of tests separately, you can filter by tag via build configuration or the JUnit Platform.

### 2.1. Combining Extensions Under a Shared Convention

If many tests all need an extension to provide a fake clock, configure a security context, or clean up resources, you can package the extension into an annotation:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Test
@ExtendWith(FixedClockExtension.class)
public @interface FixedTimeTest {
}
```

Then the test only needs:

```java
class ExpirationPolicyTest {
    @FixedTimeTest
    void expiresAtTheConfiguredInstant() {
        // FixedClockExtension provides the clock according to the project convention.
    }
}
```

The extension still must comply with the JUnit Extension API. A composed annotation is only a unified way to register the extension; it does not automatically create dependencies or state if the extension has not implemented that.

### 2.2. Do Not Mix Incompatible Test Method Annotations

You should not combine multiple different test execution annotations into the same composed annotation, for example both `@Test` and `@ParameterizedTest` or both `@TestFactory`. They represent different execution models and can create confusing test discovery behavior.

Create a separate annotation for each type of test method, or create an annotation that only attaches tags/extensions to use alongside the appropriate execution annotation. A composed annotation should have one clear meaning.

## 3. Composed Annotations in Spring Test

Spring Test uses meta-annotations to provide convenience annotations. For example, `@SpringJUnitConfig` combines Spring's extension mechanism with `@ContextConfiguration`, making test context declarations more concise.

```java
@SpringJUnitConfig(CustomerTestConfiguration.class)
class CustomerServiceTest {
    @Autowired
    private CustomerService customerService;
}
```

This annotation is equivalent to declaring `@ExtendWith(SpringExtension.class)` together with `@ContextConfiguration(classes = ...)`. Test authors do not need to repeat both annotations on every class.

Spring Boot also provides many specialized composed annotations:

- `@SpringBootTest` connects the test with Spring Boot's application bootstrap mechanism and Spring Test.
- `@WebMvcTest` sets up the web MVC slice and related configurations.
- `@DataJpaTest` sets up the persistence slice and test transactions.
- `@JsonTest` sets up the slice for JSON serialization/deserialization.
- `@RestClientTest` sets up the test environment for REST clients.

These slice annotations package many configurations, filters, and bootstrap metadata. When creating a custom annotation, you should start from the most suitable existing annotation rather than manually copying every meta-annotation inside it.

## 4. Creating a Composed Annotation for Spring Boot Integration Tests

Suppose many test classes in a project need the same environment:

- Start the Spring Boot application context.
- Use the `integration` profile.
- Auto-configure `MockMvc`.
- Allow each class to specify the application configuration and inline properties.

You can define a reusable annotation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("integration")
public @interface WebIntegrationTest {

    @AliasFor(annotation = SpringBootTest.class, attribute = "classes")
    Class<?>[] classes() default {};

    @AliasFor(annotation = SpringBootTest.class, attribute = "properties")
    String[] properties() default {};
}
```

Usage:

```java
@WebIntegrationTest(
        classes = ShopApplication.class,
        properties = "feature.checkout.enabled=true")
class CheckoutControllerIntegrationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsCheckoutPage() throws Exception {
        mockMvc.perform(get("/checkout"))
                .andExpect(status().isOk());
    }
}
```

The test class only expresses its own differences. Shared conventions for the web environment, profile, and MockMvc are placed in the `WebIntegrationTest` annotation.

In the example, `classes` and `properties` are attributes of the composed annotation. `@AliasFor` maps them to the identically named attributes on `@SpringBootTest`, so Spring uses the values passed by the user when merging metadata.

If all tests always use the same application class and properties, there is no need to expose those attributes. A fixed annotation is less likely to be misused. Only expose attributes that test classes actually need to customize.

## 5. What Is `@AliasFor` Used For?

When creating a composed annotation, you often want to let users configure an attribute of a meta-annotation without having to place the meta-annotation directly on the test class. Spring provides `@AliasFor` to declare that relationship.

`@AliasFor` is commonly used in two ways:

1. Creating an alias between two attributes within the same annotation.
2. Overriding an attribute of a meta-annotation.

### 5.1. Alias Between Two Attributes in the Same Annotation

An annotation can provide two different names for the same value:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ContextFilesTest {
    @AliasFor("locations")
    String[] value() default {};

    @AliasFor("value")
    String[] locations() default {};
}
```

The two attributes `value` and `locations` are reciprocal aliases. Users can write:

```java
@ContextFilesTest("classpath:/test-context.xml")
class LegacyRepositoryTest {
}
```

Or:

```java
@ContextFilesTest(locations = "classpath:/test-context.xml")
class LegacyRepositoryTest {
}
```

This is an alias within the same annotation. The attributes must have compatible return types and the same default value so Spring can merge them consistently.

### 5.2. Overriding an Attribute of a Meta-annotation

Suppose a reusable annotation needs to allow tests to change the web environment of `@SpringBootTest`:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@SpringBootTest
public @interface ApplicationTest {
    @AliasFor(annotation = SpringBootTest.class, attribute = "webEnvironment")
    SpringBootTest.WebEnvironment webEnvironment()
            default SpringBootTest.WebEnvironment.MOCK;
}
```

Users can choose the environment:

```java
@ApplicationTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpServerTest {
}
```

The `RANDOM_PORT` value is mapped to the `webEnvironment` attribute of `@SpringBootTest`. If no value is passed, the composed annotation's default `MOCK` is used.

When overriding a meta-annotation attribute, the return type must be compatible with the target attribute. The default value of the alias must be compatible with the default value of the overridden attribute. If the two attributes do not have the same type or have an invalid default, Spring may report an error when analyzing merged annotations.

### 5.3. Aliasing the `classes` and `properties` Attributes

The `WebIntegrationTest` example in the previous section uses:

```java
@AliasFor(annotation = SpringBootTest.class, attribute = "classes")
Class<?>[] classes() default {};

@AliasFor(annotation = SpringBootTest.class, attribute = "properties")
String[] properties() default {};
```

This means users can configure the composed annotation without having to write `@SpringBootTest` directly. Spring merges the attributes of the composed annotation and meta-annotations to produce the final configuration.

If a meta-annotation attribute is not exposed, the value declared directly on the meta-annotation is kept. For example, `@ActiveProfiles("integration")` fixes the profile for all tests using `@WebIntegrationTest`; a test class cannot change the profile through this annotation if the composed annotation does not define a corresponding alias.

## 6. Aliases Across Multiple Meta-annotation Levels

A composed annotation can be built from another composed annotation. For example, a general annotation for integration tests can be used by a specialized annotation for MVC or persistence.

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest
@ActiveProfiles("integration")
public @interface IntegrationTest {
    @AliasFor(annotation = SpringBootTest.class, attribute = "properties")
    String[] properties() default {};
}
```

A specialized annotation for web:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@IntegrationTest
@AutoConfigureMockMvc
public @interface WebLayerIntegrationTest {
}
```

A test uses it:

```java
@WebLayerIntegrationTest
class AccountControllerIntegrationTest {
    @Autowired
    private MockMvc mockMvc;
}
```

Spring supports searching for metadata across meta-annotation levels. However, the more levels there are, the harder it becomes to know where the final value comes from. Limit composition depth and choose names that clearly express each annotation's role.

When an attribute needs to be exposed across multiple levels, corresponding aliases must be declared at the necessary levels and you must ensure alias paths do not conflict. If tests frequently need to override profiles, properties, or context classes, a single annotation with explicit attributes may be easier to understand than multiple layers of annotations.

## 7. Combining Spring Test and Spring Boot Annotations

A composed annotation can combine multiple class-level annotations, provided they are compatible in bootstrap target and configuration.

For example, an annotation for repository integration tests:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@DataJpaTest
@ActiveProfiles("repository-test")
public @interface RepositoryIntegrationTest {
}
```

Usage:

```java
@RepositoryIntegrationTest
class CustomerRepositoryTest {
    @Autowired
    private CustomerRepository customers;
}
```

This annotation unifies the persistence slice and profile for repository tests. `@DataJpaTest` already provides the appropriate bootstrap and transaction semantics; there is no need to add `@SpringBootTest` to the same composed annotation.

### 7.1. Avoiding Conflicting Bootstrap Annotations

A test class should not accidentally receive multiple incompatible bootstrap strategies. For example, `@SpringBootTest` and `@WebMvcTest` both describe how to create a test context for different goals. Combining both in a composed annotation can lead to a `@BootstrapWith` conflict or unpredictable context configuration.

Choose one bootstrap annotation as the base:

- Full application context: `@SpringBootTest`.
- MVC slice: `@WebMvcTest`.
- JPA slice: `@DataJpaTest`.
- Plain Spring context: `@ContextConfiguration` or `@SpringJUnitConfig`.

Then add compatible supporting annotations such as `@ActiveProfiles`, `@TestPropertySource`, `@Import`, `@AutoConfigureMockMvc`, `@Transactional`, or `@DirtiesContext` when genuinely needed.

## 8. Applicability Scope of Composed Annotations

The `@Target` of a composed annotation must include where users will place it. For example, an annotation used at the class level:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ServiceIntegrationTest {
}
```

An annotation used at the method level:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Test
public @interface ServiceTest {
}
```

If an annotation can be used on both classes and methods, declare both explicitly:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface TestCategory {
    String value();
}
```

When creating a meta-annotation, the annotation needs to be allowed to appear on an annotation declaration. That means the `@Target` of the original annotation must support `ElementType.ANNOTATION_TYPE` if that annotation is used as a meta-annotation. JUnit and Spring annotations designed for composition usually already allow this position.

Do not declare a broader `@Target` than needed just to avoid compile errors. An annotation that only makes sense at the test class level should keep `TYPE`, helping the IDE and compiler prevent misuse on methods or fields.

## 9. `@Inherited` and Annotation Inheritance

`@Inherited` is a Java meta-annotation that allows a class-level annotation to be inherited from a superclass when reading annotations via Java reflection. It does not make annotations inherited from interfaces and does not apply to annotations on methods or fields.

For example:

```java
@Inherited
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ActiveProfiles("integration")
public @interface IntegrationProfile {
}
```

A subclass can receive the annotation from the superclass:

```java
@IntegrationProfile
abstract class BaseIntegrationTest {
}

class CustomerServiceTest extends BaseIntegrationTest {
}
```

However, Spring Test has its own merged annotation mechanism and inheritance rules for certain configuration annotations. For example, `@ContextConfiguration`, `@ActiveProfiles`, and `@TestPropertySource` have attributes that control inheritance. You should not rely solely on `@Inherited` to infer the entirety of how Spring merges metadata.

### 9.1. Superclass Inheritance vs. Meta-annotations

These two concepts are independent:

- Meta-annotation: annotation A is placed on the definition of annotation B; the framework finds A when a test uses B.
- Annotation inheritance: a subclass receives an annotation from a superclass according to Java or Spring Test rules.

A composed annotation may not use `@Inherited`, yet Spring Test can still find the configuration through its merged annotation rules. Conversely, `@Inherited` does not turn an arbitrary annotation into a meta-annotation of another annotation.

### 9.2. Be Careful with Method Overrides

Java's `@Inherited` does not make annotations on a superclass method automatically appear on an overridden method of a subclass. If a test method is overridden, check the rules of the framework being used instead of inferring from class-level inheritance.

## 10. Composed Annotations and the Spring TestContext Framework

The Spring TestContext Framework uses the merged annotations mechanism to find and merge configuration from the test class, superclasses, enclosing classes, and meta-annotations. Therefore, a composed annotation can supply information to the context bootstrap process such as:

- `@ContextConfiguration` or `@SpringBootTest`.
- `@ActiveProfiles`.
- `@TestPropertySource`.
- `@ContextHierarchy`.
- `@Transactional`.
- `@DirtiesContext`.
- Spring Test's bean override annotations.

Spring does not only inspect annotations placed directly on the class. It can traverse meta-annotations to find configuration. `@AliasFor` ensures attributes of the composed annotation are properly merged with the corresponding meta-annotation attributes.

### 10.1. Where Does the Final Value Come From?

When a test class has multiple configuration sources, the final value depends on:

- Values declared directly on the composed annotation.
- Fixed values in meta-annotations.
- Attributes exposed via `@AliasFor`.
- Override and inheritance rules of the corresponding Spring annotation.

You should not place the same attribute at multiple levels without a convention. For example, if a composed annotation fixes the `integration` profile while the superclass also declares `@ActiveProfiles("repository")`, the merged result may not be what the reader expects. Standardize a single owner for profiles or declare inheritance rules explicitly.

### 10.2. Impact on the Context Cache

The Spring TestContext Framework caches `ApplicationContext` instances based on the merged configuration. Values coming from a composed annotation can affect the cache key, such as classes, properties, profiles, context customizers, or bean overrides.

If multiple tests use the same composed annotation with the same values, they have the opportunity to reuse the context. If each class passes different properties or classes via `@AliasFor`, the context key may differ and Spring must create a separate context.

This is the right behavior: two tests that need different configurations should not share a single context if that configuration changes the bean graph or application behavior. However, if the difference is only test method data, consider moving the data into a fixture rather than creating a different annotation attribute for each class.

## 11. Examples of Composed Annotations for Common Test Groups

### 11.1. Web Integration Test

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("integration")
public @interface WebIntegrationTest {
    @AliasFor(annotation = SpringBootTest.class, attribute = "properties")
    String[] properties() default {};
}
```

Test:

```java
@WebIntegrationTest(properties = "feature.catalog.enabled=true")
class CatalogControllerIntegrationTest {
    @Autowired
    MockMvc mockMvc;
}
```

### 11.2. Repository Slice Test

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@DataJpaTest
@ActiveProfiles("repository-test")
public @interface JpaSliceTest {
}
```

Test:

```java
@JpaSliceTest
class ProductRepositoryTest {
    @Autowired
    ProductRepository products;
}
```

### 11.3. Unit Test with Tag and Extension

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Test
@Tag("fast")
@ExtendWith(FixedClockExtension.class)
public @interface FastFixedTimeTest {
}
```

Test:

```java
class SubscriptionPolicyTest {
    @FastFixedTimeTest
    void evaluatesSubscriptionAtTheFixedInstant() {
        // Test uses the clock provided by the extension.
    }
}
```

The three composed annotations above serve three different purposes. You should not create a single annotation that represents unit tests, web slices, and JPA slices because their bootstrap scopes and costs differ.

## 12. Common Mistakes When Creating Composed Annotations

### Missing Runtime Retention

If an annotation uses `RetentionPolicy.CLASS` or `SOURCE`, the framework may not be able to read it at runtime. For annotations intended for JUnit and Spring Test, use `RetentionPolicy.RUNTIME`.

### `@Target` Does Not Allow the Usage Location

An annotation may fail to compile when placed on an annotation declaration if its `@Target` does not include `ANNOTATION_TYPE`. Check both where the composed annotation is declared and where users apply it.

### Wrong Type or Wrong Default in `@AliasFor`

The alias attribute must be compatible with the target attribute. Aliases within the same annotation need reciprocal declarations; default values must match. When Spring reports a merged annotation error, check the attribute name, type, and default value first.

### Placing Multiple Conflicting Bootstrap Annotations

Combining `@SpringBootTest` with `@WebMvcTest` or `@DataJpaTest` in the same composed annotation can create multiple incompatible bootstrap strategies. Choose a single base annotation and add supporting annotations.

### Composed Annotation Containing Too Much Configuration

An annotation bundling profiles, properties, transactions, mocks, web environment, and cleanup for every kind of test will be hard to understand. Split into annotations by goal: web integration, repository slice, service integration, or unit test.

### Unclear Which Attributes Are Exposed

If a test needs to change an attribute but the composed annotation has no alias, users may add the original annotation alongside it and create overlapping configurations. Expose the exact attributes that need customization, or keep the annotation fixed if there is no need to change them.

### Using `@Inherited` with Wrong Expectations

`@Inherited` only applies to class-level annotations via superclasses under Java rules. It does not apply to interfaces, method overrides, or all Spring merged annotation rules.

### Placing the Annotation at the Wrong Level

An annotation combining `@SpringBootTest` is typically used at the class level; an annotation combining `@Test` is used at the method level. Set the right `@Target` so the compiler helps prevent misuse.

## 13. Process for Designing Composed Annotations

When you want to standardize a group of test annotations, follow this sequence:

1. Identify the test type: unit test, Spring context test, full Boot integration test, or slice test.
2. Choose a suitable base annotation such as `@Test`, `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, or `@ContextConfiguration`.
3. Add supporting annotations that are genuinely shared, such as `@Tag`, `@ExtendWith`, `@ActiveProfiles`, `@Transactional`, or `@AutoConfigureMockMvc`.
4. Declare `@Target`, `@Retention(RUNTIME)`, and `@Documented` for the new annotation.
5. Use `@AliasFor` to expose the meta-annotation attributes that test classes need to customize.
6. Keep default values compatible and avoid multiple sources overriding the same attribute.
7. Apply the annotation to a representative test and verify the framework loads the right context, profiles, extensions, or tags.
8. Use the same annotation across the group of tests with the same configuration to improve consistency and context reuse.

A composed annotation should reflect a meaningful convention in the project. If two test groups have different lifecycles or bootstraps, create two annotations instead of adding many boolean flags so that one annotation tries to serve every case.

## 14. Key Principles to Remember

- A meta-annotation is an annotation placed on another annotation's definition; a composed annotation packages multiple configurations for reuse.
- Use `RetentionPolicy.RUNTIME` so JUnit and Spring can read the annotation at runtime.
- `@Target` must allow the location where the annotation is used, including `ANNOTATION_TYPE` when that annotation will serve as a meta-annotation.
- JUnit Jupiter allows combining `@Test`, `@Tag`, and `@ExtendWith` in a reusable annotation.
- Spring provides composed annotations such as `@SpringJUnitConfig`, `@SpringBootTest`, `@WebMvcTest`, and `@DataJpaTest` for different test scopes.
- `@AliasFor` creates aliases within the same annotation or maps a composed annotation's attribute to a meta-annotation.
- Choose one base bootstrap annotation; avoid combining context annotations with conflicting initialization strategies.
- `@Inherited` controls class-level inheritance via superclasses and does not replace Spring's merged annotation mechanism.
- Values from composed annotations can affect the configuration and the context cache key.
- Keep annotations short, clear in purpose, and expose only attributes that genuinely need customization.

Meta-annotations and composed annotations help projects package testing conventions into meaningful names. When you choose the right base annotation, declare aliases accurately, and keep the applicability scope clear, test classes become more consistent, repeat less configuration, and can still customize the attributes needed for each scenario.
