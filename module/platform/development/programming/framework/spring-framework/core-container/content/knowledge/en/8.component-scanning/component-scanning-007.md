# Creating Composed Stereotypes with Meta-Annotations and @AliasFor in Spring Core Container

## Learning Objectives

In Spring, a class annotated with `@Component`, `@Service`, or `@Repository` can be discovered via **component scanning** and registered as a bean. In large projects, however, we often want to express a class's role using a custom annotation such as `@DomainService`, `@PaymentHandler`, or `@ApplicationUseCase`. A custom annotation is only useful to the container if Spring recognizes it as a **stereotype** and reads the relevant metadata properly.

Two mechanisms solve this problem:

1. **Meta-annotation:** placing one annotation on the definition of another annotation. For example, placing `@Component` on `@DomainService` so classes marked with `@DomainService` are also treated as component scan candidates.
2. **`@AliasFor`:** declaring an attribute of an annotation as an alias for another attribute, either within the **same annotation** or on a **meta-annotation**. For example, allowing `@DomainService(beanName = "invoiceProcessor")` to specify the bean name via `@Component.value`.

After this lesson, you will:

- Create a custom stereotype discovered by Spring without needing to add `@Component` to each class.
- Use `@Target`, `@Retention`, and `@Documented` for their proper purposes.
- Map bean names via `@AliasFor(annotation = Component.class, attribute = "value")`.
- Distinguish explicit aliases, aliases to meta-annotation attributes, and implicit aliases.
- Understand requirements on return types, default values, and meta-annotation scope.
- Know how to inspect bean names and merged annotations using Spring APIs.
- Spot common mistakes where an annotation appears on a class yet component scanning does not register the bean.

**Scope limit:** This lesson focuses on custom stereotypes in the **Spring Core Container**, rather than building an entirely new annotation processing mechanism or focusing on AOP. `@Transactional`, `@Qualifier`, and custom filters are mentioned only when needed to separate responsibilities.

## 1. What Is a Stereotype?

Spring refers to annotations that classify a class's role as **stereotype annotations**. `@Component` is the general-purpose stereotype. `@Service`, `@Repository`, and `@Controller` are more specialized, yet all are built on the `@Component` mechanism.

A simplified version of `@Service` looks like:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface Service {
    // Custom attributes may be declared.
}
```

This is a **structural illustration**, not code to redefine `org.springframework.stereotype.Service` in your project. Spring discovers classes annotated with `@Service` because `@Service`'s definition already carries the `@Component` meta-annotation.

The relationship:

```text
@Component
    ↑ meta-annotation
@DomainService
    ↑ annotation applied to class
InvoiceProcessor
    ↓ component scan
BeanDefinition for InvoiceProcessor
    ↓
Spring container manages bean
```

Being treated as a **candidate** does not by itself guarantee `ApplicationContext` startup succeeds: a class may be excluded by filters, lack dependencies, fail during bean creation, or lie outside scanned packages.

A custom stereotype is useful when the same role recurs across the codebase:

```java
@DomainService
public class InvoiceProcessor {
    // ...
}
```

Readers recognize this as a domain service, while Spring treats it like a regular component. Other meaningful metadata can be added to the annotation as needed, provided you clearly distinguish whether it affects **bean registration**, **naming**, **scope**, or **runtime behavior**.

## 2. Three Annotation Concepts to Understand

### 2.1. Regular Annotation

Java allows marking a class:

```java
@SomeMarker
public class Example {
}
```

If `@SomeMarker` is simply a custom annotation without the `@Component` meta-annotation, Spring by default does **not** treat this class as a component candidate merely because it carries the marker. A custom include filter can be written to scan any annotation, but that is a separate configuration.

### 2.2. Meta-Annotation

An annotation placed on **the definition of another annotation** is called a meta-annotation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Component
public @interface DomainService {
}
```

Once the custom stereotype carries the `@Component` meta-annotation, classes annotated with `@DomainService` within the default component scan region can be discovered by Spring.

In terms of classification, `@Service` is also a stereotype meta-annotated with `@Component`. If a custom annotation is meta-annotated with `@Service`, `@Component` is **indirectly** present one level further up. Spring can read valid meta-annotation chains, though for basic bean-naming examples, meta-annotating directly with `@Component` keeps the structure easier to verify.

### 2.3. Composed Annotation

A **composed annotation** integrates meta-annotations and can **re-expose certain attributes** to callers. For example, a feature-specific annotation might combine the meaning "this is a component" with a bean name, scope, or qualifier rule.

Composition does not mean Java automatically copies attributes between annotations. Spring must read its **merged annotation model** to apply overrides and aliases.

Example:

```java
@DomainService(beanName = "invoiceProcessor")
public class InvoiceProcessor {
}
```

Here `beanName` is a custom-named attribute of `@DomainService`. For Spring to use it as the bean name, an explicit alias to `@Component.value` must be declared.

## 3. Standard Custom Stereotype Definition

A typical custom annotation:

```java
package demo.stereotype;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface DomainService {

    @AliasFor(annotation = Component.class, attribute = "value")
    String beanName() default "";
}
```

Role of each element:

| Element | Role |
| --- | --- |
| `@Target(ElementType.TYPE)` | Annotation applies to classes/interfaces or `TYPE` declarations. In component scan, the registration target is a candidate class. |
| `@Retention(RetentionPolicy.RUNTIME)` | Annotation remains in the class file and can be read at runtime. |
| `@Documented` | Includes the annotation in Javadoc of annotated elements; does not make Spring register a bean. |
| `@Component` | Tells the component scanner this annotation is a stereotype when present in the meta-annotation chain. |
| `@AliasFor(...)` | Tells Spring that `DomainService.beanName` overrides/maps to `Component.value`. |
| `String beanName() default ""` | Callers can provide a bean name or leave it empty to use the default naming mechanism. |

**Important:** `@AliasFor` must be placed **on the attribute method of the annotation** (`beanName()`). Never put `@AliasFor` on the target class `InvoiceProcessor` or on a regular Java field.

`@Target` and `@Retention` come from `java.lang.annotation`; `@Component` comes from `org.springframework.stereotype`; `@AliasFor` comes from `org.springframework.core.annotation`. Mixing up package imports will prevent compilation or break intended behavior.

## 4. Why Is @AliasFor Needed for Bean Naming?

`@Component` defines the attribute `String value() default ""`. When writing:

```java
@Component("invoiceProcessor")
public class InvoiceProcessor {
}
```

Spring can use `invoiceProcessor` as the bean name.

Suppose you create:

```java
@Component
public @interface DomainService {
    String beanName() default "";
}
```

and write:

```java
@DomainService(beanName = "invoiceProcessor")
public class InvoiceProcessor {
}
```

**Without `@AliasFor`**, you cannot assume Spring will automatically interpret an arbitrary attribute named `beanName` as `Component.value`. Thus, even though the class may still be scanned via `@Component`, the custom bean name may **not be applied**.

Add:

```java
@AliasFor(annotation = Component.class, attribute = "value")
String beanName() default "";
```

to explicitly declare the relationship "`DomainService.beanName` is an override for `Component.value`." Since Spring Framework 6.1, supporting stereotype names via attributes not named `value` relies on this explicit alias. Also starting in 6.1, relying on the convention of **matching the name `value` without `@AliasFor`** has been deprecated; when creating new annotations, declare the alias explicitly.

### When Leaving the Name Empty

If using:

```java
@DomainService
public class ReportService {
}
```

`beanName()` defaults to `""`. When no other explicit name is provided, the default `AnnotationBeanNameGenerator` can generate the bean name `reportService` from class name `ReportService` under Spring's decapitalization rules.

If the scanner is configured with a custom `BeanNameGenerator`, the actual name may differ. Do not build critical logic around a default bean name when the application might switch naming strategies.

## 5. Runnable Java 17 and Spring Framework 6.2 Example

The example below has two classes annotated with the same custom stereotype:

- `InvoiceProcessor` uses the explicit bean name `invoiceProcessor` via `beanName`.
- `ReportService` specifies no name, using the default bean name `reportService`.

Spring uses `@ComponentScan` to find both classes in package `demo.app`. We will verify that beans can be retrieved by name and by type.

### 5.1. Directory Structure

```text
composed-stereotype-demo/
├── pom.xml
└── src/main/java/
    └── demo/
        ├── Main.java
        ├── config/
        │   └── AppConfig.java
        ├── stereotype/
        │   └── DomainService.java
        └── app/
            ├── billing/
            │   └── InvoiceProcessor.java
            └── report/
                └── ReportService.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>composed-stereotype-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. Creating the @DomainService Annotation

File `src/main/java/demo/stereotype/DomainService.java`:

```java
package demo.stereotype;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface DomainService {

    @AliasFor(annotation = Component.class, attribute = "value")
    String beanName() default "";
}
```

This annotation contains no manual bean instantiation code. When the component scanner encounters a class carrying `@DomainService` in a scanned package, Spring recognizes `@Component` as a meta-annotation and registers that class as a component candidate. The alias affects **bean name metadata**.

### 5.4. Service with an Explicit Bean Name

File `src/main/java/demo/app/billing/InvoiceProcessor.java`:

```java
package demo.app.billing;

import demo.stereotype.DomainService;

@DomainService(beanName = "invoiceProcessor")
public class InvoiceProcessor {

    public String execute() {
        return "invoice-created";
    }
}
```

The class does not directly carry `@Component` or `@Service`. The custom annotation is enough for the component scanner to recognize it, provided `demo.app.billing` is within the scan region and no filter excludes it.

### 5.5. Service Using the Default Name

File `src/main/java/demo/app/report/ReportService.java`:

```java
package demo.app.report;

import demo.stereotype.DomainService;

@DomainService
public class ReportService {

    public String render() {
        return "report-ready";
    }
}
```

Because `beanName` is not passed, it defaults to an empty string. The corresponding default bean name for `ReportService` is normally `reportService`.

### 5.6. Enabling Component Scan

File `src/main/java/demo/config/AppConfig.java`:

```java
package demo.config;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "demo.app")
public class AppConfig {
}
```

Having the configuration class `AppConfig` in `demo.config` does not prevent scanning `demo.app`, because `basePackages` specifies the root explicitly. The configuration class is passed explicitly into the context in `Main`.

### 5.7. Querying the Container and Checking Results

File `src/main/java/demo/Main.java`:

```java
package demo;

import demo.app.billing.InvoiceProcessor;
import demo.app.report.ReportService;
import demo.config.AppConfig;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            System.out.println("named=" +
                    context.containsBean("invoiceProcessor"));
            System.out.println("default=" +
                    context.containsBean("reportService"));

            InvoiceProcessor invoice =
                    context.getBean("invoiceProcessor", InvoiceProcessor.class);
            ReportService report =
                    context.getBean(ReportService.class);

            System.out.println("invoice=" + invoice.execute());
            System.out.println("report=" + report.render());
        }
    }
}
```

### 5.8. Running the Program

From the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.Main
```

Lines printed by the program (excluding Maven or environment logging):

```text
named=true
default=true
invoice=invoice-created
report=report-ready
```

**Explanation of output:**

1. `AppConfig` instructs the scanner to scan `demo.app` and its subpackages, so both `demo.app.billing` and `demo.app.report` are inspected.
2. Both classes carry `@DomainService`. Since this annotation is meta-annotated with `@Component`, Spring treats them as component candidates.
3. `InvoiceProcessor` has `beanName = "invoiceProcessor"`. The explicit alias lets Spring interpret this as the value for `Component.value` and register the bean under `invoiceProcessor`.
4. `ReportService` leaves `beanName` empty, so it receives the default name `reportService`.
5. `getBean("invoiceProcessor", InvoiceProcessor.class)` and `getBean(ReportService.class)` both retrieve their beans. Both application methods return fixed strings, so output is predictable.

**Note:** This example presents a complete standalone program with 5 Java files and 1 POM. Small annotation snippets in other sections may just be **illustrative fragments that need to be placed in an appropriate project**.

## 6. @AliasFor Works in Three Relationship Modes

`@AliasFor` is declared on an **attribute method** inside an annotation. In the Spring annotation programming model, three relationship types are worth distinguishing.

### 6.1. Explicit Alias Between Two Attributes of the Same Annotation

Suppose you want `value` and `name` to be two equivalent ways of writing the attribute:

```java
// Illustrative snippet declaring a standalone annotation.
import org.springframework.core.annotation.AliasFor;

public @interface LocalAlias {

    @AliasFor("name")
    String value() default "";

    @AliasFor("value")
    String name() default "";
}
```

When the annotation is processed by Spring via **MergedAnnotations** or equivalent APIs, the two attributes are explicit aliases. Key conditions:

- Both must have the **same return type** — in the example, both are `String`.
- Both must have the **same default value** — in the example, both are `""`.
- Declare `@AliasFor` on **both sides** for clear documentation and compatibility.
- Within the same annotation, do not specify `annotation = ...` because by default it points to the current annotation.
- If two **different** values are supplied on the same annotation usage, Spring can detect an alias conflict when synthesizing metadata.

Usage example:

```java
@LocalAlias("workerA")
class Alpha {
}

@LocalAlias(name = "workerB")
class Beta {
}
```

However, `@LocalAlias` in this example **does not have `@Component`**, so aliases alone do not turn `Alpha` or `Beta` into Spring beans. The purpose is to illustrate internal alias relationships, not a complete component scan example.

### 6.2. Explicit Alias to a Meta-Annotation

This is the main pattern of this lesson:

```java
@Component
public @interface DomainService {

    @AliasFor(annotation = Component.class, attribute = "value")
    String beanName() default "";
}
```

`DomainService.beanName` is an **explicit override** for `Component.value`. The value from the annotation on the class is propagated by Spring down into the merged metadata view of `@Component`.

Conditions to understand:

1. `Component.class` must be a **discoverable meta-annotation** on the definition of `@DomainService` (directly or meta-present through valid layers).
2. The target attribute `value` must exist on `@Component`.
3. The return types of source and target must be compatible/matching: here both are `String`.
4. Specify `annotation = Component.class` and `attribute = "value"` explicitly so Spring knows which attribute is overridden.
5. Ensure the target annotation has suitable retention/target so metadata can be read.

You cannot write:

```java
// COUNTER-EXAMPLE — @Component is not in the meta-annotation chain.
@Deprecated
public @interface BrokenService {
    @AliasFor(annotation = Component.class, attribute = "value")
    String name() default "";
}
```

and expect Spring to automatically treat `BrokenService` as a stereotype. Here `@Component` is not meta-present on `@BrokenService`; the alias references a missing meta-annotation and can cause Spring to detect an invalid annotation configuration when reading metadata. `@Deprecated` is also not a stereotype.

### 6.3. Implicit Aliases When Two Attributes Override the Same Meta-Attribute

You can expose both `value` and `beanName`, each overriding `Component.value`:

```java
// Illustrative snippet of another custom stereotype.
// Requires importing java.lang.annotation.*,
// org.springframework.core.annotation.AliasFor, and
// org.springframework.stereotype.Component.

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface NamedDomainService {

    @AliasFor(annotation = Component.class, attribute = "value")
    String value() default "";

    @AliasFor(annotation = Component.class, attribute = "value")
    String beanName() default "";
}
```

The two attributes become **implicit aliases** of one another because both point to the same meta-attribute `Component.value`. They must have the **same type** and **same default value**; you can use `@NamedDomainService("a")` or `@NamedDomainService(beanName = "a")`. If two different values are declared at the same usage site, Spring can report a conflict when resolving merged attributes.

You do not need to declare both names if the project has no requirement for equivalent syntax. A single explicit `beanName()` attribute as in the full example is usually simpler and less confusing.

### 6.4. Aliases Across Multiple Meta-Annotation Layers

Spring supports synthesizing metadata across multiple layers. For example, `@SpecializedService` is meta-annotated with `@DomainService`, while `@DomainService` is meta-annotated with `@Component`. An alias on `@SpecializedService` can target `@DomainService`'s meta-annotation attribute and be forwarded to `@Component` if the alias chain is declared properly.

```java
// Illustrative snippet: DomainService is already defined.
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@DomainService
public @interface SpecializedService {

    @AliasFor(annotation = DomainService.class, attribute = "beanName")
    String name() default "";
}
```

Here `SpecializedService.name` points to `DomainService.beanName`; `DomainService.beanName` in turn points to `Component.value`. The example demonstrates **transitive meta-annotation override** capability, though you should not create many annotation layers just because you can. Each layer makes final metadata harder for readers to see; in real systems, integration tests are needed to verify the bean name and applied metadata.

## 7. Java Reflection and the Spring Merged Annotation Model

A common misconception: declaring `@AliasFor` makes **plain Java reflection** automatically treat one alias as the other.

In reality, `@AliasFor` is **metadata for Spring's annotation-reading mechanism**. Java reflection such as `SomeClass.class.getAnnotation(...)` only reflects annotations per Java's model and does not enforce override rules across meta-annotations.

Example with `InvoiceProcessor`:

```java
// Illustrative snippet in the complete example project:
DomainService direct =
        InvoiceProcessor.class.getAnnotation(DomainService.class);

System.out.println(direct.beanName());
```

`direct.beanName()` returns `"invoiceProcessor"` because that value was declared directly on the annotation. However, that **does not prove** Java reflection automatically computes `Component.value`.

When you need to read the synthesized result:

```java
// Additional snippet in the example project.
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.stereotype.Component;

Component merged = AnnotatedElementUtils.findMergedAnnotation(
        InvoiceProcessor.class, Component.class);

System.out.println(merged.value());
```

Expected output of the additional snippet:

```text
invoiceProcessor
```

`findMergedAnnotation` uses Spring's merged annotations model, so it sees the `Component.value` attribute overridden by the custom stereotype. It can also return `null` if the requested annotation is not present; for `InvoiceProcessor` in this example, `@Component` is present at the meta-annotation layer, so a result is returned.

APIs like `MergedAnnotations` and `AnnotatedElementUtils` are the right tools when writing custom infrastructure that needs to query composed metadata. Avoid writing a manual reflection loop that only checks for `@Component` directly on a class and concludes every custom stereotype is invalid: `@Component` can be **meta-present**.

## 8. How Does @ComponentScan Discover Custom Stereotypes?

With:

```java
@Configuration
@ComponentScan(basePackages = "demo.app")
class AppConfig {
}
```

when `useDefaultFilters` keeps its default value `true`, the scanner looks for classes annotated with `@Component` **directly or via meta-annotation**; both `@Service` and custom `@DomainService` belong to this group.

Conceptual flow:

```text
Scan classpath under demo.app
        |
        v
Read class annotation metadata
        |
        v
Class has @Component directly / meta-present?
        | Yes
        v
Check filters and candidate conditions
        |
        v
Determine bean name from stereotype/alias or default generator
        |
        v
Register BeanDefinition
        |
        v
Instantiate bean per lifecycle/scope when needed
```

A class with `@DomainService` **will not be found** if it lies outside the `demo.app` root, even if the annotation is defined accurately. Switching an annotation from `@Component` to `@DomainService` also does not automatically widen the scan scope.

If the scanner uses:

```java
@ComponentScan(
    basePackages = "demo.app",
    useDefaultFilters = false
)
```

default stereotype filters are turned off. Then `@DomainService` is no longer automatically recognized by default; to include it again, configure an appropriate `includeFilters`. Therefore, distinguish between **the annotation being defined correctly** and **the scanner having the filter enabled to accept it**.

Also distinguish a class annotation from a bean definition: an annotation definition only makes the class a **candidate**; issues such as unsatisfied dependencies, bean name conflicts, or configuration conditions can prevent successful registration/instantiation.

## 9. Composed Stereotypes and @Service/@Repository/@Controller

`@Component` is the simplest foundation, yet not every custom stereotype should carry the same generic meaning. To create an annotation for the service layer, you can meta-annotate with `@Service`; since `@Service` itself is meta-annotated with `@Component`, the class remains a component candidate. The metadata structure then has multiple layers.

However, understand clearly:

- `@Service` expresses the service role; the annotation itself does not add transactions or security.
- `@Repository` can participate in persistence-layer exception translation when the corresponding processing infrastructure is enabled. Do not use it on a class solely to trigger component scanning.
- `@Controller` is for controller classes in a web stack; a custom stereotype meta-annotated with `@Controller` does not automatically define request mappings.
- Spring MVC's `@RestController` is a real-world example of an annotation composed from `@Controller` and `@ResponseBody`, though it belongs to the web scope rather than the core example of this lesson.

Choose the meta-stereotype based on the component's **true role**. When the goal is an application-owned annotation with a custom bean name, meta-annotating `@Component` directly establishes minimal clear semantics that can be extended when needed.

## 10. Composing Other Metadata: Do Not Confuse with @AliasFor

A custom stereotype can carry multiple meta-annotations, each with its own contract. For instance, if a group of beans genuinely must use prototype scope:

```java
// Illustrative snippet of another annotation; requires full imports.
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
@Scope("prototype")
public @interface PrototypeComponent {

    @AliasFor(annotation = Component.class, attribute = "value")
    String beanName() default "";
}
```

`@Scope("prototype")` specifies the scope, whereas `@AliasFor` above only specifies the bean name attribute. Do not infer that `@AliasFor` itself activates prototype scope. To also expose scope or proxy mode options, you need matching aliases pointing to `@Scope`'s attributes, with matching return types and valid meta-present metadata.

Similarly:

- `@Qualifier` attaches candidate-selection metadata at injection points; it is not a general bean-naming mechanism.
- `@Primary` prioritizes a candidate during single-bean autowiring; it is neither an alias nor a bean-creation requirement.
- `@Order` affects ordering where sorting is applied; it does not register a bean by itself.
- `@Transactional` requires matching transaction management infrastructure to create transactional behavior. Composing the annotation alone does not guarantee proxies or a transaction manager are enabled.
- `@Lazy` affects lazy initialization or lazy dependency resolution depending on where it is applied; it does not turn a custom stereotype into an optional dependency.

Do not cram all metadata into one "do-everything" annotation. Each meta-annotation adds a configuration decision and can cause hard-to-observe effects when applied broadly.

## 11. @AliasFor Rules to Remember When Designing Annotation APIs

### 11.1. Internal Aliases Must Share Type and Default

For:

```java
@AliasFor("name")
String value() default "";

@AliasFor("value")
String name() default "";
```

both attributes have the same type `String` and the same default `""`. If one attribute defaults to `"main"` while the other defaults to `""`, the alias pair violates Spring's contract. If one is `String` and the other is `String[]`, the types mismatch as well.

### 11.2. Meta-Annotation Aliases Must Point to the Exact Attribute

```java
@AliasFor(annotation = Component.class, attribute = "value")
String beanName() default "";
```

`Component.value` is `String`, so `beanName` must also be `String`. Writing `attribute = "name"` when `@Component` has no `name()` attribute is invalid.

### 11.3. Do Not Overuse Aliases When Attribute Names Are Unnecessary

If a custom annotation is only meant to replace `@Component` with a domain name and does not need custom bean naming, you can write:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface DomainService {
}
```

This annotation is still a valid custom stereotype. **`@AliasFor` is a tool for declaring attribute relationships**, not a mandatory step for every custom stereotype. Only add it when you need to expose a meta-annotation's attribute or create synonymous attribute names.

### 11.4. Do Not Rely on Legacy Implicit Conventions

A custom stereotype with `String value() default ""` without `@AliasFor` used to be handled by some Spring mechanisms via naming convention. Since Spring Framework 6.1, convention-based component naming support like this is deprecated. For new code, declare an explicit alias to `Component.value` so intent and compatibility are clear.

### 11.5. @AliasFor Does Not Alter Java Annotation Semantics

Annotation values are part of Java class metadata, not mutable variables. You cannot mutate an alias at runtime and expect beans to be renamed. Bean names are decided when Spring registers bean definitions; reading annotations via Spring's merged model serves metadata processing.

## 12. Verifying with Integration Tests Instead of Only Reading Annotations

A custom stereotype should be tested at **two levels**:

1. **Metadata level:** Spring reads the meta-present `@Component`, and the `beanName` alias is synthesized into `Component.value`.
2. **Container level:** the component scanner discovers the class in the right package, the bean name is exact, and the bean can be injected/looked up by type.

Example check added to `Main` in the section 5 project:

```java
// Illustrative snippet added to main; requires corresponding imports.
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.stereotype.Component;

// After context creation:
Component merged = AnnotatedElementUtils.findMergedAnnotation(
        InvoiceProcessor.class, Component.class);

if (merged == null ||
        !"invoiceProcessor".equals(merged.value())) {
    throw new AssertionError("Incorrect merged component name");
}
if (!context.containsBean("invoiceProcessor")) {
    throw new AssertionError("Custom stereotype bean not registered");
}
if (!context.containsBean("reportService")) {
    throw new AssertionError("Default component name not registered");
}
```

This is an **additional verification snippet**, printing no extra stdout when passing. If bean names change due to a broken alias or wrong package scan, it catches the issue. The goal is to test **real container outcomes**, rather than merely asserting via reflection that the annotation is present.

If you implement a custom annotation with multiple aliases, add tests for using each alias name and for conflicting declarations. If an alias traverses multiple meta-annotation layers, test that information propagates accurately to the target annotation.

In a project with a custom bean naming strategy, write tests against that strategy rather than hardcoding `reportService` when that is not the active default name generator.

## 13. Common Errors

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Class has `@DomainService` but no bean exists | Missing `@Component` meta-annotation, class outside scan region, or scanner filters changed | Check `@Component` on the annotation definition, scan roots, `useDefaultFilters`, and classpath |
| `beanName` is ignored | No explicit alias declared to `Component.value` or alias misconfigured | Add `@AliasFor(annotation = Component.class, attribute = "value")` |
| Spring throws annotation configuration error | Alias points to nonexistent attribute, target meta-annotation absent, invalid type/default | Read root exception and `@AliasFor` Javadoc |
| Default bean name differs from expected | Custom bean name generator used or class name hits special rule | Query actual bean name and check generator configuration |
| Two components share the same bean name | Alias assigns duplicate name or component scan is broader than intended | Choose unique names; design namespaces/scan boundaries cleanly |
| `@AliasFor` placed on consumer class | Misunderstanding where aliases are declared | Place annotation on the `String beanName()` method **inside the @interface definition** |
| Missing `@Retention(RUNTIME)` | Annotation loses required runtime metadata | Declare runtime retention |
| Only `@DomainService` visible via reflection, not `@Component` directly | Java reflection does not surface meta-annotations as direct annotations | Use Spring's `MergedAnnotations`/`AnnotatedElementUtils` |
| Annotation appears yet transactions do not run | Meta-annotated `@Transactional` without matching transaction infrastructure | Configure transaction manager/proxies as needed; distinguish discovery from behavior |
| Two aliases on same annotation have differing values | Violates alias contract during Spring metadata synthesis | Supply only one alias or ensure matching values |
| `@DomainService` works in one module but not another | Classpath, scan roots, or component filters differ | Check `ApplicationContext` configuration and dependencies |
| Marker interface mistaken for component | Confusing `basePackageClasses` marker with stereotype | Markers only anchor package scans unless annotated with `@Component` |

### Compact Debugging Procedure

1. Verify `@DomainService` has `@Target(TYPE)`, `@Retention(RUNTIME)`, and the `@Component` meta-annotation.
2. Check that the bean class resides in a package actually scanned by `@ComponentScan`.
3. Confirm whether the scanner still uses default filters or has custom include/exclude filters.
4. Inspect alias attributes: target annotation, attribute name, return type, and default value.
5. Use `AnnotatedElementUtils.findMergedAnnotation` to verify Spring synthesizes `@Component` and `value` as expected.
6. Create a minimal `ApplicationContext` and verify `containsBean` and `getBean`; on error, read the root exception before changing configuration.

Do not "fix" issues by adding `@Component` to every class using a custom stereotype just to make it run; doing so masks defects in the annotation definition or scan configuration itself.

## 14. Self-Check Exercises

### Exercise 1: Removing @Component

If you remove `@Component` from `@DomainService`'s definition while keeping `@AliasFor(annotation = Component.class, attribute = "value")`, will the default scanner still pick up `InvoiceProcessor`?

**Answer:** No. `@DomainService` is no longer a `@Component`-based stereotype; an alias cannot substitute for the target meta-annotation. Furthermore, the alias to `Component.value` no longer has a valid meta-annotation chain, which is likely to cause an error when Spring processes metadata.

### Exercise 2: Changing beanName

Change `@DomainService(beanName = "invoiceProcessor")` to `@DomainService(beanName = "billingInvoice")`. How must the name-based bean lookup be updated?

**Answer:** `context.getBean("billingInvoice", InvoiceProcessor.class)`. The class type and `execute()` method are unchanged, while the registered bean name changes. For consumers injecting by type when only one candidate exists, changing the bean name may have no impact; for string lookups, it does.

### Exercise 3: Scanning the Wrong Package

If `@ComponentScan(basePackages = "demo.app.report")` while `InvoiceProcessor` resides in `demo.app.billing`, will the custom stereotype cause `InvoiceProcessor` to still be discovered?

**Answer:** No. The meta-annotation determines whether the class is a stereotype candidate; the scan package determines **whether the class is inspected**. You must scan the `billing` root as well or register the bean via another mechanism.

### Exercise 4: Aliases Within the Same Annotation

With:

```java
@AliasFor("name")
String value() default "";

@AliasFor("value")
String name() default "";
```

can the two attributes have different types or different defaults?

**Answer:** No. Explicit aliases within the same annotation must have the same type and the same default. If you want two independent options, do not declare them as aliases.

### Exercise 5: Which Aliases Affect Bean Names?

An annotation has `@Component` and an attribute `String category() default "core";` without `@AliasFor`. Does `category` automatically become the bean name?

**Answer:** No. It is custom metadata defined by the annotation; to map the bean name, an explicit alias to `Component.value` or a custom bean name generator/scanner policy is required.

### Exercise 6: Designing a Custom Stereotype

You want application-layer classes marked with `@ApplicationUseCase`, allowing `@ApplicationUseCase(name = "orderCreation")` to set the bean name. List the essential parts.

**Answer guide:** Declare an `@interface ApplicationUseCase` with `@Target(TYPE)`, `@Retention(RUNTIME)`, `@Documented`, and meta-annotation `@Component`. Add `@AliasFor(annotation = Component.class, attribute = "value") String name() default "";`. Scan the right package, then verify the container holds bean `orderCreation`. Only add scope/transaction/qualifier metadata if genuinely required by that role.

## Key Takeaways

- **Meta-annotation `@Component`** turns a custom annotation into a stereotype discoverable by the default component scanner.
- **`@AliasFor`** describes relationships between attributes: internal aliases, overrides to a meta-attribute, or implicit aliases sharing a target.
- For custom stereotypes with a dedicated naming attribute, use **`@AliasFor(annotation = Component.class, attribute = "value")`** to set bean names explicitly and stay compatible with Spring 6.1+.
- `@Target(TYPE)`, `@Retention(RUNTIME)`, and scan scope must all be right; a valid annotation definition does not guarantee bean registration if the scanner never reaches the class.
- Plain Java reflection does not replace **Spring's merged annotations** mechanism. When verifying aliases, check both synthesized metadata and the actual bean in `ApplicationContext`.
- Keep custom stereotypes small, semantically meaningful, and covered by integration tests; do not turn one annotation into a catch-all for every Spring policy.

## Official Documentation

- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): stereotypes, meta-annotations, composed annotations, bean names, and component scanner.
- [Spring Framework 6.2 — @AliasFor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/annotation/AliasFor.html): alias types, type and default constraints, explicit/implicit overrides.
- [Spring Framework 6.2 — @Component Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/stereotype/Component.html): stereotypes and naming conventions from Spring 6.1.
- [Spring Framework 6.2 — @ComponentScan Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/ComponentScan.html): scan scope and filters.
- [Spring Framework — Annotation Programming Model](https://github.com/spring-projects/spring-framework/wiki/Spring-Annotation-Programming-Model): deep explanation of merged annotations and aliases.
