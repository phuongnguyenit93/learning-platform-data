# TraversableResolver and Property Traversal Limits

## 1. The problem: how far may validation read and traverse?

In Jakarta Bean Validation, when calling `Validator#validate(bean)` or when Spring triggers Bean Validation via `@Valid`/`@Validated`, the provider checks constraints on each property of the object. If a property is marked with `@Valid`, the provider can also continue validating the child object (cascaded validation).

Reading a property or traversing deeply into child objects is not always appropriate. For example: a JPA entity has a `LAZY` association; reading an unloaded association could cause the application to execute unintended SQL queries. Or a validation flow may only want to evaluate direct constraints on a property without continuing into linked objects.

`jakarta.validation.TraversableResolver` is the infrastructure contract that lets the provider decide **whether a property's state may be accessed** and **whether validation may cascade through that property**.

Distinguish clearly:

- `ConstraintValidator` checks a *value* and normally returns valid/invalid.
- `@Valid` marks a site that should cascade into the inner value.
- `TraversableResolver` decides whether the provider *is allowed to inspect/traverse* that site.
- Spring `DataBinder`/Jackson converts input data into an object; `TraversableResolver` does not control the binding process.
- JPA `CascadeType.PERSIST/REMOVE` manages persistence operations; it is not synonymous with Bean Validation `@Valid`.

## 2. Two independent decisions in the same interface

API signature in Jakarta Validation 3.x:

```java
package jakarta.validation;

import java.lang.annotation.ElementType;

public interface TraversableResolver {
    boolean isReachable(
        Object traversableObject,
        Path.Node traversableProperty,
        Class<?> rootBeanType,
        Path pathToTraversableObject,
        ElementType elementType
    );

    boolean isCascadable(
        Object traversableObject,
        Path.Node traversableProperty,
        Class<?> rootBeanType,
        Path pathToTraversableObject,
        ElementType elementType
    );
}
```

This is an **API signature for reading and understanding**, not a Java file to create; the interface is already provided by the Jakarta Validation library.

### `isReachable(...)`: may the property be accessed?

The provider calls `isReachable` before needing to access a property to evaluate constraints or cascade.

- Returns `true`: the property may be read and evaluated according to its constraints/`@Valid`.
- Returns `false`: the property **is not accessed for validation**, constraints placed directly on that property are skipped, and no cascade occurs through that property.

For example, if `@NotNull` is placed on a property but `isReachable` returns `false`, the provider does not produce an `@NotNull` violation for that property. This only means it was *not checked*, not that the data is valid.

### `isCascadable(...)`: may validation proceed through `@Valid`?

The provider only asks `isCascadable` when the property is **already reachable** and is a site requiring cascade via `@Valid`. Thus, for the same arguments, `isReachable` is evaluated before `isCascadable`.

- Returns `true`: allows traversing into the child object according to Bean Validation rules.
- Returns `false`: stops cascading at that property, **but direct constraints on the property are still evaluated** because the property is reachable.

For example, with `@NotNull @Valid Address deliveryAddress`: when `isReachable=true` and `isCascadable=false`, `deliveryAddress=null` still violates `@NotNull`; if `deliveryAddress` is a non-null object, constraints inside `Address` are not checked through this cascade path.

| Resolver result | Direct constraints on property | Cascade via `@Valid` |
| --- | --- | --- |
| `isReachable=false` | Skipped | Skipped, no need to call `isCascadable` |
| `isReachable=true`, without `@Valid` | Can be checked | No cascade |
| `isReachable=true`, `isCascadable=false` | Can be checked | No |
| `isReachable=true`, `isCascadable=true` | Can be checked | Yes, when value/metadata allow |

The table describes **access permissions granted to the validation provider**; it does not assert that the provider necessarily calls the resolver exactly once per field. The engine may cache or optimize the number of calls.

## 3. Reading the five parameters accurately

Both methods take the same five parameters:

| Parameter | Explanation |
| --- | --- |
| `traversableObject` | The object that *owns* the property. Can be `null` when validating via `validateValue(...)`. |
| `traversableProperty` | `Path.Node` representing the property being considered; `getName()` typically returns a name like `"deliveryAddress"`. |
| `rootBeanType` | The root class being validated; for executable validation, the class declaring the validated method/constructor. |
| `pathToTraversableObject` | Path from the root to the object owning the property, **not including the property** currently being considered. |
| `elementType` | `ElementType.FIELD` or `ElementType.METHOD` for where the constraint is declared. |

When the owner is the root object itself, the path to the owner is the root path (whose first node has name `null` per the specification). With deeply nested objects, the path helps distinguish two properties with the same name appearing on different branches. If you use `traversableProperty.getName()` to define a policy, check the owner type or context as well, rather than blocking all properties with that name across every class.

There are two scopes to note:

1. Root objects passed directly into `validate(...)` are not excluded from validation by this property filter.
2. Method/constructor parameter values and return values at the direct level also do not pass through the resolver; **properties inside objects cascaded from those values** are still subject to reachability/cascadability checks.

Do not dereference `traversableObject` when it may be `null`. Do not confuse `pathToTraversableObject` with `ConstraintViolation#getPropertyPath()`: one is the callback's context, the other is the path to a recorded error.

## 4. Property evaluation flow

Suppose an object has the structure:

```text
Checkout
├── customerName: @NotBlank
├── internalCode: @NotBlank            ← reachability can be blocked
└── deliveryAddress: @NotNull @Valid  ← cascade can be blocked
    └── street: @NotBlank
```

For each property to process, the provider may follow this logical order:

1. Ask `isReachable`. If `false`, stop validation for the property and any cascade branch starting from it.
2. If reachable, process direct constraints in the active validation group.
3. If the property has `@Valid` and can cascade, ask `isCascadable`.
4. If `isCascadable=true`, validate the child object/branch according to the Bean Validation contract.

The provider may optimize or change processing order across properties; the order above describes the dependency relationship between reachability, direct constraints, and cascaded validation, not a callback event order to rely on in business logic.

## 5. Standalone Java 17 example

The example below uses Jakarta Validation with Hibernate Validator to demonstrate:

- An *unreachable* property will not produce errors from constraints attached to itself.
- A *non-cascadable* property is still checked for direct constraints, but its child object is not validated.

Create two files:

```text
traversal-example/
├── pom.xml
└── src/main/java/demo/validation/TraversalExample.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>traversal-example</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.hibernate.validator</groupId>
      <artifactId>hibernate-validator</artifactId>
      <version>8.0.2.Final</version>
    </dependency>
    <dependency>
      <groupId>org.glassfish</groupId>
      <artifactId>jakarta.el</artifactId>
      <version>4.0.2</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

**`TraversalExample.java`**

```java
package demo.validation;

import jakarta.validation.Configuration;
import jakarta.validation.Path;
import jakarta.validation.TraversableResolver;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.lang.annotation.ElementType;
import java.util.List;

public final class TraversalExample {

    static final class Address {
        @NotBlank
        private final String street;

        Address(String street) {
            this.street = street;
        }
    }

    static final class Checkout {
        @NotBlank
        private final String customerName;

        @NotBlank
        private final String internalCode;

        @NotNull
        @Valid
        private final Address deliveryAddress;

        Checkout(String customerName, String internalCode, Address address) {
            this.customerName = customerName;
            this.internalCode = internalCode;
            this.deliveryAddress = address;
        }
    }

    // Immutable policy; delegate remaining properties to the default resolver.
    static final class LimitedResolver implements TraversableResolver {
        private final TraversableResolver delegate;

        LimitedResolver(TraversableResolver delegate) {
            this.delegate = delegate;
        }

        @Override
        public boolean isReachable(
                Object traversableObject, Path.Node traversableProperty,
                Class<?> rootBeanType, Path pathToTraversableObject,
                ElementType elementType) {

            if (traversableObject instanceof Checkout
                    && "internalCode".equals(traversableProperty.getName())) {
                return false;
            }
            return delegate.isReachable(
                traversableObject, traversableProperty, rootBeanType,
                pathToTraversableObject, elementType);
        }

        @Override
        public boolean isCascadable(
                Object traversableObject, Path.Node traversableProperty,
                Class<?> rootBeanType, Path pathToTraversableObject,
                ElementType elementType) {

            if (traversableObject instanceof Checkout
                    && "deliveryAddress".equals(traversableProperty.getName())) {
                return false;
            }
            return delegate.isCascadable(
                traversableObject, traversableProperty, rootBeanType,
                pathToTraversableObject, elementType);
        }
    }

    private static void show(String label, Validator validator, Checkout item) {
        List<String> errors = validator.validate(item).stream()
            .map(v -> v.getPropertyPath() + ":" +
                v.getConstraintDescriptor().getAnnotation()
                    .annotationType().getSimpleName())
            .sorted()
            .toList();

        System.out.println(label + " => " +
            (errors.isEmpty() ? "OK" : String.join(", ", errors)));
    }

    public static void main(String[] args) {
        Checkout nestedInvalid = new Checkout("", "", new Address(""));
        Checkout missingAddress = new Checkout("", "", null);

        try (ValidatorFactory normal = Validation.buildDefaultValidatorFactory()) {
            Configuration<?> config = Validation.byDefaultProvider().configure();

            TraversableResolver defaultResolver =
                config.getDefaultTraversableResolver();

            try (ValidatorFactory limited = config
                    .traversableResolver(new LimitedResolver(defaultResolver))
                    .buildValidatorFactory()) {

                show("normal(nested)", normal.getValidator(), nestedInvalid);
                show("limited(nested)", limited.getValidator(), nestedInvalid);
                show("limited(null)", limited.getValidator(), missingAddress);
            }
        }
    }
}
```

Run in the directory containing `pom.xml` with Java 17+ and Maven:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.validation.TraversalExample
```

Lines printed by the program, excluding extra Maven/provider logs if logging is enabled in the environment:

```text
normal(nested) => customerName:NotBlank, deliveryAddress.street:NotBlank, internalCode:NotBlank
limited(nested) => customerName:NotBlank
limited(null) => customerName:NotBlank, deliveryAddress:NotNull
```

**Explanation:**

- `normal(nested)`: in the example without JPA, the default resolver allows reading every property and cascading; `customerName`, `internalCode`, and `Address.street` are all empty and violate `@NotBlank`.
- `limited(nested)`: `internalCode` is blocked in `isReachable`, so its `@NotBlank` does not run. `deliveryAddress` is reachable and non-`null`, so it satisfies `@NotNull`, but it does not cascade, so `street` is not checked. Only `customerName` fails.
- `limited(null)`: `deliveryAddress` is reachable, so `@NotNull` still reports an error even though cascading is blocked. This is the core difference between the two methods.

The program uses annotation names and sorts results to avoid depending on `Set<ConstraintViolation<?>>` order and error message language. `ValidatorFactory` is closed with try-with-resources after use.

**Why include `defaultResolver`?** The default resolver may contain JPA policy to avoid reading unloaded properties. If you write a custom resolver that simply returns `true` for remaining properties, you could accidentally discard that policy. Delegating to `Configuration#getDefaultTraversableResolver()` preserves provider behavior for non-customized parts.

## 6. Relationship with JPA and lazy associations

A JPA integration example (illustrative snippet; requires entity mapping/application configuration to run):

```java
@Entity
public class Invoice {
    @Id
    private Long id;

    @NotNull
    @Valid
    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}
```

When `customer` has not been loaded, reading the association directly could cause the ORM to query the DB. By default under the Jakarta Validation specification when Jakarta Persistence is present, a property is considered reachable if the persistence provider confirms it is loaded. A common mechanism is:

```java
// Illustrates JPA-aware reachability, not a complete class:
return traversableObject == null
    || jakarta.persistence.Persistence.getPersistenceUtil()
        .isLoaded(traversableObject, traversableProperty.getName());
```

Many providers already integrate this behavior out of the box when JPA is present. Therefore, **you do not need to write your own resolver just to prevent lazy loading when the default already meets your needs**. If you must write a custom resolver to add policy, delegate to the default resolver as in the example.

Consequences to know:

- A property marked unreachable does not have its direct constraints evaluated; even `@NotNull` on that property will not produce a violation in that validation pass.
- If the property is already loaded, the provider can evaluate it and cascade normally depending on annotations/groups.
- “Not yet loaded” is different from “value is `null`”. Avoid calling getters or reading lazy collections inside `isReachable` itself.
- The resolver only controls **the Bean Validation process**. Mappers, serializers, debuggers, loggers, or business code can still read the property and trigger queries.
- `@Valid` is not `CascadeType.PERSIST` or `CascadeType.REMOVE`. One controls validation; the other controls ORM operations.

If business logic needs to guarantee the entire graph is valid, load the required data inside an appropriate transaction or validate explicit DTOs. Do not treat “no violations” on an entity with many unloaded associations as proof that all associations are valid.

## 7. Limiting traversal by name, path, and depth

A resolver can make decisions based on:

- **Owner type:** `traversableObject instanceof Checkout` to avoid affecting other classes.
- **Property name:** `traversableProperty.getName()`.
- **Root type:** `rootBeanType` helps distinguish the validation entry point.
- **Path:** `pathToTraversableObject` helps identify nested branches.
- **Declaration site:** `elementType` distinguishes field constraints from getter constraints.

When you want to restrict going too deep while keeping constraints on the current property, control **`isCascadable`**. Illustrative example inside that method, where `delegate` is the default resolver:

```java
long propertyNodes = 0;
for (Path.Node node : pathToTraversableObject) {
    if (node.getKind() == jakarta.validation.ElementKind.PROPERTY) {
        propertyNodes++;
    }
}

boolean mayGoDeeper = propertyNodes < 2;
return mayGoDeeper && delegate.isCascadable(
    traversableObject, traversableProperty, rootBeanType,
    pathToTraversableObject, elementType);
```

This is **an illustrative policy for counting property nodes**, not a “two objects” depth-limiting algorithm that fits every case. `Path` can contain method nodes, parameter nodes, container-element nodes, or index/key information. With `List<@Valid T>`, `Map<K, @Valid V>`, and nested structures, test the actual paths and define the exact depth you want to limit.

Do not use `isReachable=false` merely to reduce depth if you still need to check constraints on the current property: that would skip direct constraints too. Likewise, *stopping cascade* does not prevent an object from being validated via another reference path in the same graph.

## 8. Integration with Spring Framework

In Spring Framework 6/Spring Boot 3, Bean Validation uses `jakarta.validation`. Spring typically integrates the provider via `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean`, which has `setTraversableResolver(...)`:

```java
// Illustrative configuration snippet, not a standalone @Configuration:
LocalValidatorFactoryBean bean = new LocalValidatorFactoryBean();
bean.setTraversableResolver(customResolver);
```

`customResolver` must be an instance of a class implementing `TraversableResolver`, such as `LimitedResolver` from section 5 if organized as an accessible class in the application. For the policy to actually affect validation from Spring MVC, ensure this bean is used as the validator at the right integration point. Spring Boot may auto-configure a validator, so avoid declaring an unintended new factory if the application already has a suitable customization mechanism.

Controller example (integration snippet; requires the related classes/imports):

```java
@PostMapping("/checkouts")
public ResponseEntity<Void> create(@Valid @RequestBody CheckoutRequest body) {
    return ResponseEntity.noContent().build();
}
```

When Bean Validation is triggered, reachability/cascadability applies to the properties being evaluated. However:

- JSON binding and type conversion happen at a different layer; JSON parsing errors can occur before validation runs.
- `@Validated` can select validation groups; it does not change the meaning of `isReachable`/`isCascadable`.
- Spring's `org.springframework.validation.Validator` with `validate(Object, Errors)` is a separate interface; it does not automatically use the `TraversableResolver` contract for manual checks.
- If the goal is simply to validate a value, writing an appropriate constraint/`ConstraintValidator` is clearer than intervening in property traversal infrastructure.

## 9. Operational constraints and common mistakes

A `TraversableResolver` implementation must be **thread-safe**. Use a stateless object or immutable state like `LimitedResolver`. Do not use a shared counter incremented/decremented across callbacks to measure depth, as one instance can be reused during concurrent validation runs.

Do not rely on how many times a callback is invoked: Hibernate Validator may cache resolver results within a validation pass to reduce overhead, especially with JPA. If the resolver itself is very fast, changing caching is a specialized optimization requiring measurement; normally keep the default configuration.

If the resolver throws an exception, the provider wraps it in a `ValidationException`; that is an infrastructure failure, **not** a constraint violation. For a property that must not be accessed, return `false` instead of throwing an error. Do not invoke lazy getters, run DB queries, or mutate object state inside the callbacks.

Common mistakes:

1. Returning `false` from `isReachable` and assuming `@NotNull` still runs.
2. Returning `false` from `isCascadable` and assuming all constraints on the property are skipped.
3. Dropping the default resolver in a JPA application and accidentally reading lazy properties.
4. Blocking globally by property name without checking owner type/path.
5. Dereferencing `traversableObject` in `validateValue` contexts when this parameter is `null`.
6. Confusing the resolver with security/authorization or query limiting across all software layers.
7. Treating `Path` depth as object count without accounting for container/executable nodes.

## 10. Testing a traversal policy

| Test case | Expected behavior |
| --- | --- |
| Reachable `@NotBlank` property, empty value | Violation is produced |
| Same property marked unreachable | That constraint is not evaluated |
| Reachable, non-cascadable `@NotNull @Valid` property, non-null | Does not enter child object constraints |
| Same property equal to null | Still reports `@NotNull` |
| Reachable and cascadable `@Valid` property | Allows child object validation |
| `validateValue(...)` with null owner | Resolver works without NPE |
| JPA entity with unloaded association | Does not inadvertently trigger lazy queries via validation |
| List/Map and deeply nested objects | `Path`-based policy does not block the wrong level |
| Concurrent validation passes | Results are unaffected by shared state |

**Rule of thumb:** `isReachable` decides *whether to inspect the property at all*; `isCascadable` decides *whether to continue through `@Valid`*. When blocking a branch, understand clearly which violations will no longer be detected and test that decision at the actual call site.

## References

- Jakarta Validation API, `TraversableResolver`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/TraversableResolver.html
- Jakarta Bean Validation 3.0 Specification, *Traversable property* section: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation `Configuration`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Configuration.html
- Hibernate Validator 8 Reference Guide, *TraversableResolver*: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework 6 `LocalValidatorFactoryBean` API: https://docs.spring.io/spring-framework/docs/6.0.23/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html