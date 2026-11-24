# @AliasFor When Configuration Attributes Need to Be Exposed

In Spring, a composed annotation bundles multiple configuration annotations into a single interface with a clear meaning. A group of integration tests might always need `SpringExtension`, an `ApplicationContext` configuration, an `integration` profile, and test-specific properties.

When creating a new annotation that only carries meta-annotations, users of that annotation cannot yet pass values into the meta-annotation attributes. `@AliasFor` solves this problem by declaring an attribute of the composed annotation as an alias for another attribute in the same annotation or an attribute belonging to a meta-annotation.

As a result, the composed annotation preserves the shared policy while still exposing the choices that each test class needs to change. The Spring TestContext Framework understands aliases when merging metadata to build the test configuration.

## Composed Annotations and the Need to Expose Attributes

Suppose many test classes repeat the following configuration:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = PersistenceTestConfig.class)
@ActiveProfiles("integration")
@TestPropertySource(properties = "feature.audit.enabled=false")
class CustomerRepositoryTest {
    // ...
}
~~~

You can group the common annotations into one annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@ExtendWith(SpringExtension.class)
@ContextConfiguration
@ActiveProfiles("integration")
@TestPropertySource
public @interface PersistenceIntegrationTest {
}
~~~

Then the test class only needs to write:

~~~java
@PersistenceIntegrationTest
class CustomerRepositoryTest {
    // ...
}
~~~

This approach reduces repetition, but the test class cannot yet pass its own configuration classes or properties through the new annotation. Simply adding an attribute named `classes` to the new annotation does not make Spring guess that it should map to `@ContextConfiguration.classes`. `@AliasFor` establishes that relationship explicitly.

## Two Main Types of Aliases

`@AliasFor` belongs to the `org.springframework.core.annotation` package:

~~~java
import org.springframework.core.annotation.AliasFor;
~~~

There are two common ways to use it:

1. **Alias within the same annotation:** two attributes of one annotation represent the same value, such as `value` and `locations`.
2. **Alias to a meta-annotation:** an attribute of the composed annotation exposes an attribute of a meta-annotation, such as `classes` on the new annotation mapping to `classes` of `@ContextConfiguration`.

`@AliasFor` is not an arbitrary mapping mechanism between any two annotations. For an alias to a meta-annotation, the target annotation must be in the meta-annotation hierarchy of the composed annotation so Spring can merge the metadata.

## Alias Between Two Attributes in the Same Annotation

An annotation can provide two names for the same attribute. A familiar case is `value` for concise writing and a more descriptive name for readable source code.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface TestResources {

    @AliasFor("locations")
    String[] value() default {};

    @AliasFor("value")
    String[] locations() default {};
}
~~~

The two attributes `value` and `locations` are explicit aliases for each other. Users can choose either way of writing:

~~~java
@TestResources("/test-context.xml")
class XmlContextTest {
}

@TestResources(locations = "/test-context.xml")
class AnotherXmlContextTest {
}
~~~

For an internal alias, a bidirectional relationship must be declared: each attribute points to the other. Both attributes must have the same return type and the same default value. For example, an attribute of type `String[]` cannot be aliased with an attribute of type `String`.

## Alias to a Meta-Annotation Attribute

An important case when building reusable annotations is surfacing an attribute of a meta-annotation onto the outer annotation.

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.core.annotation.AliasFor;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.TestPropertySource;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@ExtendWith(SpringExtension.class)
@ContextConfiguration
@ActiveProfiles("integration")
@TestPropertySource
public @interface PersistenceIntegrationTest {

    @AliasFor(
        annotation = ContextConfiguration.class,
        attribute = "classes"
    )
    Class<?>[] classes() default {};

    @AliasFor(
        annotation = ContextConfiguration.class,
        attribute = "locations"
    )
    String[] locations() default {};

    @AliasFor(
        annotation = TestPropertySource.class,
        attribute = "properties"
    )
    String[] properties() default {};

    @AliasFor(
        annotation = TestPropertySource.class,
        attribute = "locations"
    )
    String[] propertyLocations() default {};
}
~~~

The attributes of the composed annotation are mapped as follows:

| Exposed Attribute | Mapped Meta Attribute | Purpose |
|---|---|---|
| classes | ContextConfiguration.classes | Declare Java configuration classes |
| locations | ContextConfiguration.locations | Declare configuration resources, such as XML |
| properties | TestPropertySource.properties | Pass inline properties for the test |
| propertyLocations | TestPropertySource.locations | Specify property files for the test |

A test class can use the new annotation and pass its own configuration:

~~~java
@PersistenceIntegrationTest(
    classes = CustomerPersistenceConfig.class,
    properties = {
        "feature.audit.enabled=true",
        "customer.search.page-size=20"
    }
)
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void loadsCustomerRepository() {
        assertThat(customerRepository).isNotNull();
    }
}
~~~

When the Spring TestContext Framework merges annotations, the `classes` value is forwarded to `@ContextConfiguration.classes`, and the properties are forwarded to `@TestPropertySource.properties`. The `integration` profile still comes from the `@ActiveProfiles("integration")` meta-annotation.

Thus, the composed annotation keeps shared configuration in one place while still letting each test class supply its own configuration. Users do not need to repeat all the meta-annotations.

## Fixed Configuration vs. Customizable Configuration

Not every attribute of a meta-annotation needs to be exposed externally. A composed annotation usually has two groups:

- **Fixed attributes:** policies that the test group must follow, such as always enabling the `integration` profile or always registering `SpringExtension`.
- **Exposed attributes:** choices that vary between test classes, such as configuration classes, properties, or resource locations.

In the example above, `@ActiveProfiles("integration")` is a fixed configuration. The annotation does not declare an alias for `profiles`, so a test class cannot change the profile through `@PersistenceIntegrationTest`.

If you want profiles to be customizable as well, leave the meta-annotation without a fixed value and expose an alias attribute:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.test.context.ActiveProfiles;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ActiveProfiles
public @interface ProfiledIntegrationTest {

    @AliasFor(
        annotation = ActiveProfiles.class,
        attribute = "profiles"
    )
    String[] profiles() default {};
}
~~~

Usage:

~~~java
@ProfiledIntegrationTest(profiles = {"integration", "customer"})
class CustomerIntegrationTest {
}
~~~

The `profiles` attribute of the composed annotation maps to `@ActiveProfiles.profiles`. The default of the alias is an empty array, matching the default of the meta attribute. When the test class passes profiles, Spring uses those values to build the list of active profiles.

Only expose attributes that users genuinely need to change. Exposing every attribute of every meta-annotation makes the composed annotation complex and hard to maintain.

## Rules When Declaring Aliases

Spring validates alias rules when merging annotations. If declarations are inconsistent, reading the annotation or creating the `TestContext` can fail.

### 1. Internal Aliases Must Be Declared Bidirectionally

Valid example:

~~~java
public @interface ResourceConfig {

    @AliasFor("locations")
    String[] value() default {};

    @AliasFor("value")
    String[] locations() default {};
}
~~~

Both attributes have the same `String[]` type, the same default value, and point to each other.

### 2. Return Types Must Be Strictly Compatible

If the target attribute is `Class<?>[]`, the alias attribute must also be `Class<?>[]`. If the target is `String[]`, the alias must be `String[]`.

Invalid example:

~~~java
public @interface InvalidTestConfig {

    @AliasFor(
        annotation = ContextConfiguration.class,
        attribute = "classes"
    )
    String[] classes() default {};
}
~~~

The alias attribute has type `String[]`, whereas `ContextConfiguration.classes` has type `Class<?>[]`. Spring cannot merge two values of different types.

### 3. Default Values Must Match

When aliasing to a meta-annotation, the default value of the alias attribute must equal the default value declared on the target attribute.

For example, `ContextConfiguration.classes()` defaults to an empty class array, so the alias must also default to an empty array:

~~~java
@AliasFor(
    annotation = ContextConfiguration.class,
    attribute = "classes"
)
Class<?>[] classes() default {};
~~~

If aliasing to a boolean attribute whose default is `true`, the alias must also declare a default of `true`. This rule compares against the default value in the target annotation's definition, not a specific value set on a meta-annotation instance.

### 4. Target Annotation Must Be in the Meta-Annotation Hierarchy

The following declaration makes sense because `@ContextConfiguration` is placed on the composed annotation:

~~~java
@ContextConfiguration
public @interface ConfiguredTest {

    @AliasFor(
        annotation = ContextConfiguration.class,
        attribute = "classes"
    )
    Class<?>[] classes() default {};
}
~~~

If the target annotation is not in the meta-annotation hierarchy of the composed annotation, Spring has no valid mapping path to merge the value.

### 5. Target Attribute Name Must Exist

The `attribute` value must match the name of a real attribute on the target annotation. Using the wrong name or pointing to an annotation without that attribute prevents Spring from merging metadata.

It is good practice to specify the target annotation and attribute clearly:

~~~java
@AliasFor(
    annotation = ContextConfiguration.class,
    attribute = "classes"
)
Class<?>[] configClasses() default {};
~~~

This style tells the reader where the attribute maps to.

## value and attribute in @AliasFor

`@AliasFor` has two attributes `value` and `attribute` that are aliases of each other. Therefore, the following two forms are equivalent when pointing to an attribute in the same annotation:

~~~java
@AliasFor("locations")
String[] value() default {};
~~~

~~~java
@AliasFor(attribute = "locations")
String[] value() default {};
~~~

When pointing to a meta-annotation, explicitly write the target annotation and attribute name:

~~~java
@AliasFor(
    annotation = ContextConfiguration.class,
    attribute = "classes"
)
Class<?>[] classes() default {};
~~~

If `annotation` is omitted, Spring treats the alias as an alias to an attribute in the current annotation itself. If you want to point to a meta-annotation, you must specify the target annotation.

## Aliases Do Not Change the Meaning of the Original Attribute

`@AliasFor` only establishes a relationship between attribute names. It does not change how the meta-annotation processes the value.

An alias to `@ContextConfiguration.locations` still declares resource locations for Spring to load the `ApplicationContext`. An alias to `@TestPropertySource.properties` still supplies inline properties for the test environment. An alias to `@ActiveProfiles.profiles` still follows profile inheritance rules and how Spring builds the context.

`@AliasFor` does not activate profiles on its own, does not create beans, and does not load a context. It only exposes a configuration attribute under another name.

## How Does Spring Merge Aliases When Reading Annotations?

Java reflection can read annotations declared directly on an element, but merging attributes across multiple layers of meta-annotations and applying aliases is the job of Spring's merged annotation model.

Spring provides APIs such as `MergedAnnotations`, `AnnotatedElementUtils`, and `AnnotationUtils` to search and merge annotations. The TestContext Framework also uses this mechanism when reading test configuration annotations.

Example of reading a merged annotation:

~~~java
MergedAnnotation<ContextConfiguration> merged =
    MergedAnnotations.from(
        CustomerRepositoryTest.class,
        MergedAnnotations.SearchStrategy.TYPE_HIERARCHY
    ).get(ContextConfiguration.class);

Class<?>[] classes = merged.getClassArray("classes");
~~~

When a test class is annotated with `@PersistenceIntegrationTest(classes = CustomerPersistenceConfig.class)`, the merged annotation of `ContextConfiguration` can return the configuration class forwarded by the alias.

You should not call only `getDeclaredAnnotation(ContextConfiguration.class)` on a test class and conclude the configuration does not exist if the annotation is placed indirectly through a composed annotation. Use an API capable of finding meta-annotations and merging aliases when reading configuration the way Spring processes it.

## Combining Aliases with Multi-Level Composed Annotations

A composed annotation can be built from other composed annotations. Spring supports searching annotations across the meta-annotation hierarchy and merging attributes according to the declared aliases.

For example, a base annotation for integration tests can be used in a specialized annotation for repositories:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PersistenceIntegrationTest
public @interface JdbcRepositoryTest {

    @AliasFor(
        annotation = PersistenceIntegrationTest.class,
        attribute = "classes"
    )
    Class<?>[] classes() default {};

    @AliasFor(
        annotation = PersistenceIntegrationTest.class,
        attribute = "properties"
    )
    String[] properties() default {};
}
~~~

A test class uses the outer annotation:

~~~java
@JdbcRepositoryTest(
    classes = CustomerPersistenceConfig.class,
    properties = "customer.repository.cache=false"
)
class CustomerRepositoryTest {
}
~~~

When creating multi-level annotations, ensure the alias paths are clear and attributes have matching types and defaults at each level. A meta-annotation chain that is too deep or has many identically named attributes makes it hard for readers to tell where the final value comes from. The outer annotation should expose only the options needed.

## Handling Conflicts and Values Declared in Multiple Places

When configuration can come from a composed annotation, superclass, meta-annotation, or an annotation directly on the test class, you need to understand how Spring merges metadata and the annotation search order.

Some practical guidelines:

- An alias specifies two names representing the same attribute; it is not an independent precedence rule.
- Values declared via an alias are processed as values of the corresponding meta attribute.
- Avoid conflicting configuration of the same attribute across multiple paths.
- For inherited configuration like `@ActiveProfiles` or `@TestPropertySource`, the merge/inherit rules of those annotations themselves remain in effect.
- When you need to know the final value, inspect the merged annotation or the `Environment` of the `ApplicationContext`.

For example, if a composed annotation fixes `@ActiveProfiles("integration")` while also exposing an alias for test classes to pass different profiles, you should clarify whether the profile is a fixed policy or a per-class choice. Clear design from the start avoids unpredictable configurations.

## When Should @AliasFor Be Used?

| Need | Should Use? | Reason |
|---|---|---|
| Group multiple Spring annotations into an easy-to-use annotation | Yes | Expose needed attributes from meta-annotations |
| Allow value and locations to be two equivalent names | Yes | Create an explicit internal alias |
| Arbitrarily rename an attribute with no meta-annotation relationship | No | AliasFor is not a general-purpose mapper |
| Fix a profile for all tests in a group | Not needed | Put the value directly on the ActiveProfiles meta-annotation |
| Let each test class pick configuration classes via a composed annotation | Yes | Alias to ContextConfiguration.classes |
| Read meta-annotations via plain Java reflection | Does not solve directly | Use Spring merged annotation APIs |

There is no need to create a composed annotation for a single test class. A reusable annotation adds value when multiple classes genuinely share the same configuration policy and need a simple, stable interface.

## Common Mistakes

**Declaring an alias but forgetting the meta-annotation.** Attributes on the new annotation do not automatically map to Spring. Place the target annotation on the composed annotation and declare `@AliasFor` with the correct class and attribute.

**Alias type differs from the target attribute type.** For example, using `String` to alias `Class<?>[]`. Types must match strictly.

**Default values do not match.** When aliasing to a meta-annotation, the default of the new attribute must equal the default of the target attribute. For internal aliases, both attributes must have the same default.

**Declaring only one side of an internal alias.** An explicit alias pair in the same annotation needs to point to each other.

**Confusing aliases with fixed configuration.** If every test must use the `integration` profile, place the profile on the meta-annotation. Only alias the profile when users of the composed annotation need permission to change it.

**Reading annotations with direct reflection and missing meta-annotations.** Use Spring merged annotation APIs when you need the merged result.

**Exposing too many attributes.** A composed annotation should present meaningful choices to users, not necessarily copy the entire API of every meta-annotation.

**Expecting an alias to change beans or context on its own.** Aliases only forward configuration values. Spring still needs to run the TestContext process to create the `ApplicationContext` from the merged configuration.

## How to Design Reusable Annotations

When building a configuration annotation for a group of tests, start by identifying what is always the same and what each test class needs to decide.

1. Choose the base annotations to bundle, such as `@ExtendWith(SpringExtension.class)`, `@ContextConfiguration`, `@ActiveProfiles`, and `@TestPropertySource`.
2. Put fixed values directly on the meta-annotations if they are a shared policy.
3. Declare attributes in the new annotation for the choices that need to be exposed.
4. Use `@AliasFor(annotation = ..., attribute = "...")` to connect each attribute to the right meta-annotation.
5. Keep return types and default values matching the target attribute.
6. If two names in the new annotation represent the same value, declare a bidirectional internal alias.
7. Use the composed annotation on a test class and let the Spring TestContext Framework merge the configuration.
8. When diagnosing issues, read the merged annotation or inspect the `Environment` of the `ApplicationContext`.

A good composed annotation expresses a test policy with a meaningful name while exposing only the necessary choices. `@AliasFor` is the bridge between that simple interface and Spring's configuration attributes. When relationships, types, and default values are declared properly, Spring can merge metadata consistently and create the `TestContext` according to the configuration the test class requires.
