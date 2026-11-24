# Composed Annotations, Aliases, and Custom Composed Annotations

In Spring and Spring Boot, many familiar annotations are actually built from other annotations. For example, `@RestController` combines the controller role with returning a response body; `@GetMapping` is a specialized form of `@RequestMapping` for HTTP GET; `@SpringBootApplication` groups commonly used application configuration annotations.

This organization is called a **composed annotation**. An annotation can carry other annotations as **meta-annotations**, inheriting their configuration meaning and exposing a more concise interface to the application.

When users of a custom annotation need to override attributes of a meta-annotation, Spring provides **`@AliasFor`**. An alias allows an attribute in a custom annotation to forward its value to an attribute on an underlying annotation, or create multiple equivalent names for the same attribute.

This lesson focuses on three capabilities:

1. Reading and understanding built-in composed annotations in Spring Boot.
2. Designing custom composed annotations to encapsulate an application convention.
3. Using `@AliasFor` properly to forward or synchronize attributes while verifying results using Spring's merged-annotation APIs.

## 1. Annotations and meta-annotations

A Java annotation is metadata attached to a class, method, field, parameter, or other element permitted by `@Target`. Frameworks read this metadata via reflection or annotation processing to alter bean registration, request mapping, validation, transactions, and many other behaviors.

Example:

~~~java
@Service
public class OrderService {
}
~~~

`@Service` is an annotation on the class. However, `@Service` itself is declared with another annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface Service {
    @AliasFor(annotation = Component.class)
    String value() default "";
}
~~~

Here:

- `@Component` is a **meta-annotation** on `@Service`.
- `@Service` is a composed annotation carrying a more specialized meaning.
- Spring component scanning recognizes `@Service` as a stereotype to register a bean.
- The `value` attribute of `@Service` is aliased to `value` of `@Component`, allowing bean naming via `@Service("orderService")`.

A meta-annotation is an annotation placed on another annotation. When Spring reads an annotation on a class, the framework can look through meta-annotations to discover inherited metadata.

### 1.1. Structure reading example

~~~text
OrderService
    |
    v
@Service
    |
    v
@Component
    |
    v
Spring component scanning registers bean
~~~

If you only use direct Java reflection via `OrderService.class.getAnnotation(Component.class)`, the result may not reflect how Spring locates meta-annotations. Standard Java reflection does not synthesize every meta-annotation as if it were directly on the class. Spring provides dedicated APIs to perform that lookup and metadata merging.

## 2. What problem do composed annotations solve?

Suppose every controller in a module must:

- Be registered as a Spring MVC controller.
- Return data via the response body.
- Share the same URL prefix.
- Follow an internal API convention.

If every class has to repeat multiple annotations:

~~~java
@RestController
@RequestMapping("/api/v1")
public class OrderController {
}
~~~

~~~java
@RestController
@RequestMapping("/api/v1")
public class CustomerController {
}
~~~

~~~java
@RestController
@RequestMapping("/api/v1")
public class ProductController {
}
~~~

That shared convention can be encapsulated into one annotation:

~~~java
@ApiV1Controller
public class OrderController {
}
~~~

~~~java
@ApiV1Controller
public class CustomerController {
}
~~~

A well-designed composed annotation helps:

- Reduce repeated metadata.
- Name conventions in the application's domain language.
- Enforce consistent conventions across modules.
- Limit the choices annotation users must know.
- Expose only customizable attributes while keeping shared defaults fixed.

A composed annotation is a **metadata abstraction**. It does not automatically create a wrapper object, generate a subclass, or act as an AOP proxy. Actual behavior depends on which framework reads the annotation.

## 3. Familiar composed annotations in Spring

### 3.1. @RestController

`@RestController` is built from `@Controller` and `@ResponseBody`.

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Controller
@ResponseBody
public @interface RestController {

    @AliasFor(annotation = Controller.class)
    String value() default "";
}
~~~

Meaning:

- `@Controller` marks a Spring MVC controller.
- `@ResponseBody` directs handler return values to be written to the HTTP response body via message conversion.
- `@AliasFor` forwards the bean name from `RestController.value` to `Controller.value`.

Example:

~~~java
@RestController
public class HealthController {

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "UP");
    }
}
~~~

With plain `@Controller`, a method returning an object might be interpreted via view resolution depending on return type and annotations. `@RestController` packages the response-body convention for the entire controller.

### 3.2. @GetMapping

`@GetMapping` is a composed annotation based on `@RequestMapping` with HTTP method set to `GET`.

~~~java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@RequestMapping(method = RequestMethod.GET)
public @interface GetMapping {

    @AliasFor(annotation = RequestMapping.class)
    String name() default "";

    @AliasFor(annotation = RequestMapping.class)
    String[] value() default {};

    @AliasFor(annotation = RequestMapping.class)
    String[] path() default {};

    @AliasFor(annotation = RequestMapping.class)
    String[] params() default {};

    @AliasFor(annotation = RequestMapping.class)
    String[] headers() default {};

    @AliasFor(annotation = RequestMapping.class)
    String[] consumes() default {};

    @AliasFor(annotation = RequestMapping.class)
    String[] produces() default {};
}
~~~

Example:

~~~java
@GetMapping(path = "/orders", produces = "application/json")
public List<OrderDto> listOrders() {
    return orderService.findAll();
}
~~~

When Spring reads `@GetMapping`, the framework recognizes the mapping attributes forwarded to `@RequestMapping`. The HTTP method remains GET as fixed on the meta-annotation.

Other specialized annotations follow the same idea:

- `@PostMapping`: `@RequestMapping(method = POST)`.
- `@PutMapping`: `@RequestMapping(method = PUT)`.
- `@PatchMapping`: `@RequestMapping(method = PATCH)`.
- `@DeleteMapping`: `@RequestMapping(method = DELETE)`.

Instead of writing `@RequestMapping(method = RequestMethod.GET)` on every method, you use an annotation expressing the exact HTTP intent.

### 3.3. @SpringBootApplication

`@SpringBootApplication` is an important application-level example:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
public @interface SpringBootApplication {

    @AliasFor(annotation = ComponentScan.class, attribute = "basePackages")
    String[] scanBasePackages() default {};

    @AliasFor(annotation = ComponentScan.class, attribute = "basePackageClasses")
    Class<?>[] scanBasePackageClasses() default {};

    @AliasFor(annotation = EnableAutoConfiguration.class, attribute = "exclude")
    Class<?>[] exclude() default {};

    @AliasFor(annotation = EnableAutoConfiguration.class, attribute = "excludeName")
    String[] excludeName() default {};
}
~~~

The snippet above omits some attributes to focus on the alias mechanism; actual source may contain additional attributes and vary by Spring Boot version.

`@SpringBootApplication` combines:

- `@SpringBootConfiguration`: marks the main Boot application configuration class.
- `@EnableAutoConfiguration`: enables auto-configuration.
- `@ComponentScan`: scans for components in appropriate packages.

Thanks to aliases, users can write:

~~~java
@SpringBootApplication(
        scanBasePackages = {
                "com.example.orders",
                "com.example.shared"
        },
        exclude = {
                SomeAutoConfiguration.class
        }
)
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Attributes on the high-level annotation are forwarded to the corresponding underlying annotations. Users do not have to declare separate `@ComponentScan` and `@EnableAutoConfiguration` annotations just to configure common properties.

**Note:** `scanBasePackages` adjusts only component scanning. It does not automatically alter other scanning mechanisms such as JPA entity scanning or repository scanning; those have their own annotations/configurations.

## 4. What is @AliasFor used for?

`@AliasFor` lives in package:

~~~java
import org.springframework.core.annotation.AliasFor;
~~~

This annotation declares that an attribute is an alias for another attribute. Spring uses that metadata when parsing and synthesizing annotations.

There are three common cases:

1. **Explicit aliases within the same annotation:** two differently named attributes representing the same value.
2. **Implicit aliases within the same annotation:** multiple attributes overriding the same meta-annotation attribute.
3. **Explicit aliases to a meta-annotation:** an attribute on a composed annotation forwarded to a specific attribute on an underlying annotation.

Aliases must satisfy rules for type compatibility, default values, and annotation relationships. Simply placing `@AliasFor` on any annotation method does not make Spring understand your intent automatically.

## 5. Explicit aliases within the same annotation

Suppose you want an annotation with two attribute names `value` and `name`, both representing the same value.

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ClientTag {

    @AliasFor("name")
    String value() default "";

    @AliasFor("value")
    String name() default "";
}
~~~

Usage:

~~~java
@ClientTag("billing")
public class BillingClient {
}
~~~

or:

~~~java
@ClientTag(name = "billing")
public class BillingClient {
}
~~~

Both attributes are bidirectional aliases for each other. Spring treats them as the same metadata value when using merged annotation support.

### 5.1. Rules for bidirectional aliases

For explicit aliases within the same annotation:

- Both attributes must declare `@AliasFor` pointing to each other.
- Both attributes must have the same return type.
- Both attributes must have the same default value.
- They must belong to the same annotation.
- Alias declarations must not form an inconsistent alias graph.

Invalid example:

~~~java
public @interface InvalidTag {

    @AliasFor("name")
    String value() default "";

    @AliasFor("value")
    String name() default "default-name";
}
~~~

Two different defaults prevent Spring from consistently treating them as two ways of writing the same attribute. When Spring validates or synthesizes the annotation, this configuration can raise an alias configuration exception.

### 5.2. When are in-annotation aliases needed?

Use them when you want to support two equivalent names because:

- A short name is convenient when used alone.
- A descriptive name is clearer for readers.
- Compatibility with an existing convention or annotation API is needed.
- Keeping a custom annotation API aligned with an underlying Spring annotation.

Avoid creating many aliases just to offer multiple spellings. Every alias increases metadata API complexity and testing responsibility.

## 6. Explicit aliases to a meta-annotation

This is the most common case when creating composed annotations.

For example, you want every service in the billing module to default to `@Service`, while still allowing users to set a bean name.

~~~java
package com.example.billing;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Service;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Service
public @interface BillingService {

    @AliasFor(annotation = Service.class, attribute = "value")
    String value() default "";
}
~~~

Usage:

~~~java
@BillingService("invoiceProcessor")
public class InvoiceProcessor {
}
~~~

Spring recognizes `@BillingService` as a stereotype based on `@Service`. The value `"invoiceProcessor"` is forwarded to `Service.value` and participates in stereotype component bean naming.

### 6.1. Important rules

For explicit aliases to a meta-annotation:

- The referenced annotation must actually be a meta-annotation on the custom annotation (directly or via a Spring-supported hierarchy).
- The target attribute must exist on the meta-annotation.
- The return types of the alias attribute and target attribute must be compatible, usually identical.
- The default value of the alias attribute must be compatible with the meta-annotation attribute's default.
- Specifying both `annotation` and `attribute` explicitly makes the alias target clear to readers.

The following example has an invalid type:

~~~java
public @interface InvalidBillingService {

    @AliasFor(annotation = Service.class, attribute = "value")
    Class<?> value() default Void.class;
}
~~~

`Service.value` is `String`, whereas the custom attribute is `Class<?>`. The two attributes cannot alias each other.

### 6.2. Fixing underlying metadata when no attribute needs exposure

If every bean in a module must carry fixed metadata, place that value directly on the meta-annotation without creating an alias.

Example:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Service
@Validated
public @interface ValidatedBillingService {
}
~~~

The custom annotation always combines the service stereotype with the validation marker. There is no need to expose a `validated` attribute if users are not allowed to change it.

**Rule:** only alias attributes that users of the composed annotation genuinely need to customize.

## 7. Implicit aliases: multiple attributes overriding the same meta-attribute

An annotation can have multiple attributes marked as aliases to **the same attribute of the same meta-annotation**. Those attributes then act as implicit aliases for one another.

Conceptual example:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@RequestMapping
public @interface ApiRoute {

    @AliasFor(annotation = RequestMapping.class, attribute = "path")
    String[] path() default {};

    @AliasFor(annotation = RequestMapping.class, attribute = "path")
    String[] route() default {};
}
~~~

Here `path` and `route` both override `RequestMapping.path`. When using the annotation, do not supply two different values for both aliases at once:

~~~java
@ApiRoute(path = "/orders")
public class OrderController {
}
~~~

or:

~~~java
@ApiRoute(route = "/orders")
public class OrderController {
}
~~~

Both names express the same metadata.

If both are declared simultaneously:

~~~java
@ApiRoute(path = "/orders", route = "/invoices")
public class InvalidController {
}
~~~

Spring cannot merge two distinct values for the same alias group; annotation synthesis will fail with an alias configuration/conflicting values error.

### 7.1. Defaults for implicit aliases

Implicit alias attributes must have compatible return types and the same default value. In the example, both return `String[]` and default to an empty array.

Do not use implicit aliases merely to create arbitrary synonyms. One canonical name is usually enough; implicit aliases are useful when API or compatibility requires supporting equivalent attribute names.

## 8. Custom composed annotation for transactions

A practical example is encapsulating a read-only transaction convention for query classes/methods.

~~~java
package com.example.orders.persistence;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.transaction.annotation.Transactional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Transactional(readOnly = true)
public @interface ReadOnlyTransaction {

    @AliasFor(annotation = Transactional.class, attribute = "transactionManager")
    String transactionManager() default "";
}
~~~

Usage:

~~~java
@Service
public class OrderQueryService {

    @ReadOnlyTransaction
    public OrderDto findOrder(UUID id) {
        // Read data.
        return ...;
    }
}
~~~

`@ReadOnlyTransaction` always applies the `@Transactional(readOnly = true)` meta-annotation. Callers can still specify a transaction manager if the application defines multiple transaction managers.

### 8.1. Why not alias readOnly with default true?

`Transactional.readOnly` has a default of `false`. With explicit aliases to meta-annotation attributes, default values must be compatible. Therefore, if a custom annotation wants to fix `readOnly = true`, set the value on the meta-annotation and do not expose a `readOnly` attribute as an alias with a different default.

If callers need to toggle read-only per usage site, design the alias API under compatible default rules and verify against your Spring version's semantics. Never simply change an alias default to `true` while ignoring merge rules.

### 8.2. Transaction advice still needs an active proxy

A composed annotation does not start a transaction simply by being read in a constructor. `@ReadOnlyTransaction` works because Spring's transaction infrastructure detects `@Transactional` via meta-annotations and applies the corresponding advisor/proxy.

Proxy limitations still apply:

- Calls must pass through the proxy in proxy mode.
- Self-invocation does not trigger separate advice.
- `final`/`private`/`static` methods cannot automatically become interceptable join points under regular proxies.
- A transaction manager and transaction configuration must be active.

Composed annotations only package metadata; they do not change how transactions execute.

## 9. Custom composed annotation for controllers

An API module can define its own annotation to express a controller role.

~~~java
package com.example.api;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@RestController
@RequestMapping(path = "/api/v1")
public @interface ApiV1Controller {

    @AliasFor(annotation = RequestMapping.class, attribute = "path")
    String[] path() default {};
}
~~~

Default usage:

~~~java
@ApiV1Controller
public class OrderController {

    @GetMapping("/orders")
    public List<OrderDto> list() {
        return ...;
    }
}
~~~

The meta-annotation supplies `RequestMapping(path = "/api/v1")`. The `path` attribute on the composed annotation allows overriding the meta-annotation's `path` attribute.

Example:

~~~java
@ApiV1Controller(path = "/internal")
public class InternalOrderController {
}
~~~

In this example, the alias forwards the value to the underlying mapping attribute; it does not concatenate `"/api/v1" + "/internal"`. Aliasing is a metadata override mechanism, not a prefix/suffix concatenation mechanism. If complex path composition rules are needed, use an explicit mapping structure or tested custom infrastructure.

### 9.1. Do not declare two independent mappings expecting Spring to concatenate them

If a custom annotation already carries `@RequestMapping` and the class/method adds another mapping annotation, check Spring MVC's handler mapping rules. Do not assume two mappings merge additively the way the application intends.

Keep one clear source of ownership for class-level paths and method-level routes. Use the composed annotation to package class-level metadata; use `@GetMapping`/`@PostMapping` for handler methods.

## 10. @AliasFor with multi-attribute underlying annotations

`@RequestMapping` has many attributes, including:

- `name`
- `value`
- `path`
- `method`
- `params`
- `headers`
- `consumes`
- `produces`

A composed annotation should expose only the attributes needed for its use case. For instance, if an API module always serves JSON, fix `produces` on the meta-annotation and expose only `path`.

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@RequestMapping(
        path = "/api/v1",
        produces = "application/json"
)
public @interface JsonApiController {

    @AliasFor(annotation = RequestMapping.class, attribute = "path")
    String[] path() default {};
}
~~~

This narrows the configuration surface. Annotation users cannot accidentally change `produces` to a format violating module conventions.

If you want to expose `produces`, add an alias whose type and default match `RequestMapping.produces`. Add attributes only when they serve a real purpose.

## 11. Naming value and path: aliases of underlying annotations

Some Spring annotations provide two equivalent attribute names for shorthand syntax convenience.

For example, `@RequestMapping` declares `value` and `path` as aliases within the same annotation. Consequently, these forms mean the same thing:

~~~java
@RequestMapping("/orders")
~~~

~~~java
@RequestMapping(path = "/orders")
~~~

Similarly with `@GetMapping`:

~~~java
@GetMapping("/orders")
~~~

~~~java
@GetMapping(path = "/orders")
~~~

If creating a custom annotation that exposes both `value` and `path`, design the alias group according to the rules. A simple design can alias both to the same underlying attribute, ensuring compatible types/defaults and checking for conflicts if users specify both.

In many cases, exposing `path` alone is sufficient and clearer.

## 12. Meta-annotations can be nested across multiple levels

A composed annotation does not have to stop at a single level.

Example:

~~~text
@InternalApiController
       |
       v
@ApiV1Controller
       |
       +------> @RestController
       |
       +------> @RequestMapping
                    |
                    v
               @Controller / mapping metadata
~~~

Spring can traverse multiple meta-annotation levels via its merged annotations mechanism. Spring's stereotype, mapping, and configuration annotations are built on this model.

However, the deeper the nesting, the harder it becomes to trace final values. Limit nesting depth and choose names reflecting the annotation's real role.

### 12.1. An alias must point to a valid meta-annotation in the hierarchy

If a custom annotation tries to alias `RequestMapping.path` without having `@RequestMapping` in its meta-annotation hierarchy, that declaration is structurally invalid.

Invalid example:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Service
public @interface InvalidRoute {

    @AliasFor(annotation = RequestMapping.class, attribute = "path")
    String[] path() default {};
}
~~~

`InvalidRoute` does not have `RequestMapping` as a meta-annotation. The alias target is outside the hierarchy, so Spring cannot merge the value as intended.

## 13. Configuration annotations can also be composed

Composed annotations are not limited to stereotypes or MVC. You can package a commonly used group of configurations.

Example module annotation importing configuration:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(OrdersModuleConfiguration.class)
public @interface EnableOrdersModule {
}
~~~

Usage:

~~~java
@SpringBootApplication
@EnableOrdersModule
public class Application {
}
~~~

`@EnableOrdersModule` expresses the intent to enable the orders module; Spring processes the `@Import` meta-annotation and registers the corresponding configuration.

If the annotation needs to expose configuration attributes for the imported component, use `@AliasFor` to an appropriate meta-annotation or create a separate configuration properties type. Do not turn an annotation into a giant configuration file with dozens of unrelated attributes.

### 13.1. Composed annotations do not replace configuration properties

Annotations fit declarative metadata and small, stable choices. For multi-valued settings, nested objects, durations, endpoints, or secrets, `@ConfigurationProperties` is usually a better fit.

For example, do not create an annotation with dozens of attributes for every timeout, retry count, URL, and key. Use a typed properties class with validation and externalized configuration sources.

## 14. @Inherited and annotation inheritance scope

Java provides the `@Inherited` meta-annotation so an annotation on a superclass can be inherited when reading annotations on a subclass via certain reflection APIs.

Example:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Inherited
public @interface AuditedType {
}
~~~

~~~java
@AuditedType
class BaseHandler {
}

class OrderHandler extends BaseHandler {
}
~~~

With `@Inherited`, reflection queries supporting inheritance can find the annotation on the superclass when inspecting the subclass.

Keep in mind:

- `@Inherited` applies only to annotations on class declarations.
- It does not cause annotations on interfaces to be inherited by implementing classes.
- It does not cause annotations on methods to be inherited onto overridden methods under the same rules.
- Spring's merged-annotation search has its own semantics and can search meta-annotations/hierarchies depending on the API called.

Do not add `@Inherited` to every custom annotation by default. Use it only if the annotation truly must propagate from superclass to subclass and framework consumers require that behavior.

## 15. Java meta-annotations that must be declared properly

When creating custom annotations, the following annotations are usually essential:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface ModuleService {
}
~~~

### @Target

Defines where the annotation may be placed.

Common element types:

| ElementType | Location |
|---|---|
| `TYPE` | Class, interface, enum, annotation type, record |
| `METHOD` | Method |
| `FIELD` | Field |
| `PARAMETER` | Parameter |
| `CONSTRUCTOR` | Constructor |
| `ANNOTATION_TYPE` | Annotation type |
| `TYPE_USE` | Type use |
| `TYPE_PARAMETER` | Type parameter declaration |

Choose the target according to the underlying annotations. If a custom annotation is meta-annotated with `@Transactional` and intended for both classes and methods, target should allow both locations.

### @Retention

`RetentionPolicy.RUNTIME` lets the framework read the annotation while the application runs.

If `RetentionPolicy.CLASS` or `SOURCE` is used, metadata will not be available for Spring's reflection-based annotation processing. Composed annotations read by Spring at runtime normally require `RUNTIME`.

### @Documented

Causes the annotation to appear in Javadoc of annotated elements, making the annotation API easier to discover.

### @Inherited

Add only when class inheritance semantics as described earlier are needed. Not required for every composed annotation.

### @Repeatable

Use only when it makes sense for the annotation to appear multiple times on the same element with a suitable container annotation. Do not use `@Repeatable` just to supply multiple alias values; aliasing and repeatability are unrelated concepts.

## 16. Spring merged annotations: reading composed annotations properly

When reading meta-annotation values that have been aliased/overridden, use Spring's APIs rather than plain Java reflection alone.

Example custom annotation:

~~~java
@ApiV1Controller(path = "/internal")
public class InternalOrderController {
}
~~~

You can retrieve the merged `RequestMapping`:

~~~java
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.web.bind.annotation.RequestMapping;

RequestMapping mapping =
        AnnotatedElementUtils.findMergedAnnotation(
                InternalOrderController.class,
                RequestMapping.class
        );

System.out.println(Arrays.toString(mapping.path()));
~~~

Spring traverses the meta-annotation hierarchy, applies alias mappings, and returns the synthesized annotation according to framework semantics.

### 16.1. MergedAnnotations API

Spring Core also provides `MergedAnnotations`:

~~~java
import org.springframework.core.annotation.MergedAnnotations;
import org.springframework.web.bind.annotation.RequestMapping;

MergedAnnotations annotations =
        MergedAnnotations.from(InternalOrderController.class);

RequestMapping mapping =
        annotations.get(RequestMapping.class).synthesize();
~~~

The full API offers multiple options for search strategies and lookup behavior. The example above illustrates retrieving a synthesized meta-annotation; in production code, handle the case where the annotation is absent before calling `synthesize()`.

Presence check example:

~~~java
boolean hasMapping =
        annotations.isPresent(RequestMapping.class);
~~~

### 16.2. Why is getAnnotation() insufficient?

~~~java
RequestMapping mapping =
        InternalOrderController.class.getAnnotation(RequestMapping.class);
~~~

Java reflection returns annotations placed directly on the class per Java metadata. In this example, `@RequestMapping` is a meta-annotation on `@ApiV1Controller`, not copied directly onto the class.

Spring's merged annotation APIs understand hierarchies and aliases. When code consumes framework metadata, use the framework's appropriate APIs.

## 17. Testing custom composed annotations

A custom annotation should be tested in at least two aspects:

1. **Merged metadata:** Do aliases forward values to the meta-annotation?
2. **Framework behavior:** Does Spring actually recognize the annotation at the corresponding extension point?

### 17.1. Unit testing alias values

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.web.bind.annotation.RequestMapping;

class ApiV1ControllerAnnotationTest {

    @Test
    void aliasesPathToRequestMapping() {
        RequestMapping mapping =
                AnnotatedElementUtils.findMergedAnnotation(
                        InternalOrderController.class,
                        RequestMapping.class
                );

        assertThat(mapping).isNotNull();
        assertThat(mapping.path()).containsExactly("/internal");
    }
}
~~~

This test confirms the alias on the custom annotation merges into `RequestMapping`.

### 17.2. Testing default meta-annotation values

~~~java
@Test
void usesDefaultApiPathWhenNotOverridden() {
    RequestMapping mapping =
            AnnotatedElementUtils.findMergedAnnotation(
                    OrderController.class,
                    RequestMapping.class
            );

    assertThat(mapping).isNotNull();
    assertThat(mapping.path()).containsExactly("/api/v1");
}
~~~

This test assumes `OrderController` uses `@ApiV1Controller` without passing a path, while the meta-annotation specifies `path = "/api/v1"`.

Important point: the alias default on the composed annotation must follow Spring's rules so it does not accidentally wipe out the value placed on the meta-annotation.

### 17.3. Testing framework registration

For a stereotype annotation like `@BillingService`, use a Spring context test to verify the class is discovered by component scanning and registered as a bean.

~~~java
@SpringBootTest
class BillingServiceComponentScanTest {

    @Autowired
    ApplicationContext context;

    @Test
    void discoversComposedService() {
        assertThat(context.getBean("invoiceProcessor"))
                .isInstanceOf(InvoiceProcessor.class);
    }
}
~~~

This example assumes `InvoiceProcessor` is within component scan scope and annotated with `@BillingService("invoiceProcessor")`.

For custom MVC annotations, use MockMvc or handler mapping inspection to verify endpoints register at the right path. For composed transaction annotations, test transaction behavior through the proxy rather than merely asserting the annotation is present.

## 18. Common errors when using @AliasFor

### 18.1. Alias target not in the meta-annotation hierarchy

Usually caused by declaring `@AliasFor(annotation = X.class, attribute = "...")` when annotation X is not a valid meta-annotation on the custom annotation.

Fix: check whether the underlying annotation is actually placed on the custom annotation; fix the hierarchy or point the alias to the right annotation.

### 18.2. Wrong attribute name

For example, the underlying annotation has `path`, yet code specifies `paths`. Spring cannot locate the target attribute.

Use the exact attribute name and consider specifying `attribute` explicitly to avoid mistakes.

### 18.3. Mismatched return type

Aliasing between `String` and `String[]`, or `Class<?>` and `String`, is invalid. The custom attribute's return type must be compatible with the meta-attribute.

### 18.4. Incompatible default value

For explicit aliases to a meta-annotation, the custom attribute's default must obey compatibility rules with the underlying attribute's default. For aliases within the same annotation, all aliases must share the same default.

When you want a fixed underlying value different from the default, place it directly on the meta-annotation and keep the alias default compatible with the underlying attribute's default declaration.

### 18.5. Forgetting @Retention(RUNTIME)

If an annotation has only the default `CLASS` retention, Spring cannot read it via runtime reflection as intended. Composed annotations used for component scanning, MVC, transactions, and other runtime framework features generally require `RUNTIME`.

### 18.6. Inappropriate @Target

If the meta-annotation supports methods while the custom annotation permits only `TYPE`, users cannot place the custom annotation on methods. Conversely, widening targets arbitrarily may allow placements unsupported by framework consumers.

Choose targets based on where the annotation actually needs to appear.

### 18.7. Calling Java reflection and expecting aliases to be written into the annotation

`@AliasFor` does not rewrite bytecode or alter annotation instances inside class files. It supplies metadata so Spring can synthesize values when reading annotations through merged annotation infrastructure.

Use `AnnotatedElementUtils` or `MergedAnnotations` when reading merged results.

### 18.8. Two aliases receiving conflicting values

If two attributes alias each other and a user supplies different values for both, Spring cannot pick one valid value. Pass only one of the two, or design the API without unnecessary synonyms.

### 18.9. Assuming a composed annotation creates a proxy automatically

A `@Transactional` meta-annotation can be recognized by transaction infrastructure, yet execution still depends on proxy/weaving mode and proper call paths. A composed annotation does not turn a method into a proxy join point by itself.

## 19. Aliasing is neither Java inheritance nor arbitrary attribute mapping

Distinguish these mechanisms:

| Mechanism | Purpose |
|---|---|
| Java inheritance | Subclass inherits members/behavior from superclass |
| Meta-annotation | One annotation carries another annotation as metadata |
| `@AliasFor` | Spring treats annotation attributes as aliases and merges/forwards values |
| Configuration binding | Maps property sources into configuration objects |
| AOP proxy | Intercepts method invocations according to proxy strategy |

For instance, `@AliasFor` does not make a custom annotation inherit all Java methods of its underlying annotation at the language level. It declares relationships between annotation attributes for Spring annotation processing.

Similarly, an alias does not automatically map a YAML property into an annotation attribute; that is the job of configuration binding.

## 20. Composed annotations and version compatibility

Spring's annotation APIs have expanded across versions. When writing libraries or custom annotations shared across multiple applications, determine your Spring Framework/Spring Boot baseline.

Notable milestones:

- `@AliasFor` was introduced in Spring Framework 4.2.
- Spring provides merged annotation support to find meta-annotations, override, and synthesize attributes.
- Modern Spring Framework versions include the `MergedAnnotations` API and richer annotation hierarchy processing.
- Spring Boot 2.x and 3.x use different Spring Framework generations; the main package/API for `@AliasFor` remains `org.springframework.core.annotation`.
- Spring Boot 3 rests on Spring Framework 6 and a Java 17 baseline, yet legacy custom annotation aliases will still fail if types, defaults, or targets were declared improperly.

### 20.1. If writing a starter/library across multiple Boot versions

- Compile and test against the lowest Spring Framework baseline your library claims to support.
- Avoid newer merged annotation APIs if the baseline lacks them.
- Do not rely on internal implementation details of annotation scanners.
- Use public Spring annotations like `@AliasFor` and matching public APIs.
- Include tests verifying composed annotations across each supported framework line.
- Treat changes to attributes/defaults of a custom annotation as public API changes affecting consumers.

### 20.2. Do not copy framework annotation source as a fixed contract

For instance, the source of `@GetMapping` or `@SpringBootApplication` may add or change attributes across versions. Reading them to learn the pattern is helpful, but base your custom annotations on the public API of your project's version rather than copying whole framework definitions verbatim into application code.

## 21. Designing maintainable custom annotations

A composed annotation should have a clear purpose and a small API.

### 21.1. Name by role

Good names express a module convention:

- `@BillingService`
- `@ReadOnlyTransaction`
- `@InternalApiController`
- `@AuditedOperation`
- `@EnableOrdersModule`

Avoid generic names like `@CustomAnnotation`, `@MyComponent`, or `@SpecialConfig` because they tell readers nothing about what the annotation does.

### 21.2. Keep defaults stable

Annotation users rely on defaults to minimize configuration. Changing an alias default can alter the behavior of every class using that annotation.

Treat defaults as part of your public API and cover them with tests.

### 21.3. Expose few attributes

If a custom annotation exposes 15 aliases across multiple meta-annotations, users must understand nearly the entire underlying framework API. The abstraction stops simplifying anything.

Expose only attributes meaningful for the use case. Convention values should be fixed on the meta-annotations.

### 21.4. Avoid unnecessarily deep composed annotation layers

An overly deep hierarchy:

~~~text
@SpecialController
    -> @ModuleController
        -> @InternalController
            -> @RestController
                -> @Controller
                    -> @Component
~~~

can work if structured validly, yet becomes difficult to trace. When expressing a single convention, compose directly from the needed underlying annotations.

### 21.5. Document framework side effects

A custom annotation should document clearly whether it:

- Registers a bean or only marks metadata.
- Creates specific MVC mappings.
- Enables transactions, read-only mode, or security rules.
- Imports specific configuration classes.
- Requires certain starters/dependencies.
- Depends on profile/classpath conditions.

The annotation name is only part of the contract; behavior must be documented.

## 22. Complete example: a module with custom stereotype and transaction annotations

Suppose the orders module wants to standardize services and query transactions.

### 22.1. Custom stereotype

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Service
public @interface OrderService {

    @AliasFor(annotation = Service.class, attribute = "value")
    String value() default "";
}
~~~

### 22.2. Custom read-only transaction

~~~java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Transactional(readOnly = true)
public @interface OrderReadOnly {

    @AliasFor(annotation = Transactional.class, attribute = "transactionManager")
    String transactionManager() default "";
}
~~~

### 22.3. Using them in a service

~~~java
@OrderService("orderQueryService")
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @OrderReadOnly
    public OrderDto findById(UUID id) {
        return repository.findById(id)
                .map(OrderDto::from)
                .orElseThrow();
    }
}
~~~

Metadata outcome:

- `OrderQueryService` is recognized by component scanning as a service.
- The bean name can be `orderQueryService`.
- Method `findById` carries read-only transaction metadata through the meta-annotation.
- Transaction infrastructure can apply transaction advice when the method is invoked through the proxy with active transaction configuration.

### 22.4. Integration tests should verify both parts

- Context contains a bean named `orderQueryService`.
- The bean receives `OrderRepository` injection.
- The method is invoked through the proxy and read-only transaction semantics apply under the transaction manager.
- If the method is called internally within the same bean, remember self-invocation rules just like any proxy-based transaction.

Do not check only `OrderQueryService.class.isAnnotationPresent(OrderService.class)` because that does not prove component scanning or transaction advice works.

## 23. Checklist for creating custom composed annotations

When creating a new annotation, check:

1. Does the annotation have a clear business/framework purpose?
2. Are the underlying meta-annotations correct?
3. Does `@Target` include the intended usage locations?
4. Is `@Retention(RUNTIME)` declared?
5. Are `@Documented` or `@Inherited` needed?
6. Which attributes must be exposed to users?
7. Do `@AliasFor` declarations point to the right annotation/attribute?
8. Are return types and default values compatible?
9. Are there bidirectional explicit aliases or implicit alias groups requiring alignment?
10. Is there any risk of two aliases receiving conflicting values?
11. Does the framework consumer recognize the meta-annotation?
12. Have both merged annotation values and actual behavior been tested?
13. Is the annotation compatible with the lowest Spring version the project supports?
14. Do docs explain defaults, scope, and required dependencies?

## 24. Quick diagnosis by symptom

| Symptom | Common cause | Resolution |
|---|---|---|
| Custom stereotype creates no bean | Missing stereotype meta-annotation or package outside component scan | Check `@Component`/`@Service` meta-annotation and scan scope |
| Alias does not forward value | Wrong target annotation/attribute or mismatched default/type | Inspect `@AliasFor` and hierarchy |
| Spring throws alias configuration exception | Invalid alias pair/group or conflicting values supplied | Align types/defaults and pass only one alias value |
| Annotation not readable at runtime | Retention is not `RUNTIME` | Use `@Retention(RetentionPolicy.RUNTIME)` |
| Cannot place annotation on method | `@Target` omits `METHOD` | Add the target if semantics support it |
| Java `getAnnotation` misses meta-annotation | Annotation sits in hierarchy only | Use Spring `AnnotatedElementUtils`/`MergedAnnotations` |
| Mapping path differs from expectation | Alias overrides meta-annotation value instead of concatenating | Design explicit path semantics and test merged mapping |
| `@Transactional` meta-annotation does not run | Transaction infrastructure/proxy/call path mismatch | Inspect proxy, self-invocation, visibility, and transaction manager |
| Custom annotation works on newer Boot, fails on older Boot | Different API/version baselines | Compile/test on the supported framework baseline |
| Adding many meta-annotations causes unpredictable behavior | Metadata hierarchy too broad or conflicting | Reduce layers and expose fewer attributes |

## 25. Principles to remember

- A **composed annotation** packages one or more meta-annotations into an annotation with a more specific meaning.
- `@RestController`, `@GetMapping`, `@Service`, and `@SpringBootApplication` are familiar examples.
- A **meta-annotation** is an annotation placed on another annotation.
- `@AliasFor` declares relationships between annotation attributes; it does not alter bytecode and is not Java inheritance.
- Explicit aliases within the same annotation must declare reciprocal alias relationships with compatible types and defaults.
- Implicit aliases overriding the same meta-attribute must also share consistent types and defaults.
- Explicit aliases to a meta-annotation must point to an actual annotation in the hierarchy and a valid attribute.
- To fix a meta-annotation value, place it directly on the underlying annotation; do not expose an alias if callers should not change it.
- Custom annotations consumed by Spring at runtime normally require `@Retention(RetentionPolicy.RUNTIME)` and an appropriate `@Target`.
- Use `AnnotatedElementUtils` or `MergedAnnotations` to read merged metadata; plain Java reflection does not replace merged annotation semantics.
- Composed annotations only package metadata; transactions, MVC mappings, component scanning, and imports still rely on framework infrastructure.
- Test both synthesized alias values and actual framework behavior.
- Keep annotations small, clearly named, with stable defaults and verified version compatibility.

**Conclusion:** Composed annotations turn repeated metadata groups into named conventions across an application. `@AliasFor` lets custom annotation attributes forward to or synchronize with meta-annotation attributes. When designed with the right hierarchy, target, retention, types, and default values, custom annotations cut boilerplate while preserving clear configurability. When troubleshooting, inspect the meta-annotation relationship and merged-annotation behavior before suspecting component scanning or framework runtime.
