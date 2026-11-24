# Precondition and Postcondition Inheritance Rules in Jakarta Validation and Spring

## 1. Context: Method Contracts Are Also Inherited

An interface publishes a contract for callers: **which input values are accepted** and **which results are guaranteed**. When a class implements an interface, or a subclass overrides a superclass method, method constraints in Jakarta Bean Validation must respect the *Liskov Substitution Principle (LSP)*.

For example, an interface permits any string, including an empty string:

~~~java
public interface LookupService {
    String lookup(String code);
}
~~~

If an implementation only accepts non-empty strings:

~~~java
public class StrictLookupService implements LookupService {
    @Override
    public String lookup(@NotBlank String code) {
        return code;
    }
}
~~~

A caller working through the `LookupService` type does not know about `StrictLookupService`'s new requirement. Jakarta Validation therefore **forbids declaring parameter constraints on overridden/implemented methods**, even when the base interface has no constraints. This is a rule about **constraint declarations**, independent of runtime input values.

Conversely, an interface promises a non-`null` result; an implementation can additionally promise the result contains at least two elements:

~~~java
public interface Catalog {
    @NotNull
    List<String> available();
}

public class DefaultCatalog implements Catalog {
    @Override
    @Size(min = 2)
    public List<String> available() {
        return List.of("A", "B");
    }
}
~~~

This implementation is valid: callers are always guaranteed the interface's `@NotNull` condition, while the implementation satisfies the stricter `@Size(min = 2)`. The validation engine **aggregates** return constraints from both the interface and the implementation.

Two core principles of Jakarta Validation:

1. **Preconditions must not be strengthened in a subtype.** Parameter constraints on overridden/implemented methods must not be newly declared, whether "identical," "stronger," or "seemingly weaker" than the supertype's constraints.
2. **Postconditions must not be weakened in a subtype.** Subtypes may **add** return constraints, while return constraints from supertypes continue to apply during validation.

These are specific rules for **method/constructor validation** in Jakarta Validation, distinct from Java reflection's `@Inherited` annotation inheritance. Providers combine metadata from interfaces and superclasses per the Bean Validation specification.

## 2. Quick Decision Table

| Hierarchy scenario | Jakarta Validation verdict | Reason |
| --- | --- | --- |
| Supertype declares `@NotBlank` on parameter; override **declares no** constraint | **Valid** | Precondition from supertype remains in effect |
| Supertype has no parameter constraint; override adds `@NotBlank` | **Invalid** | Strengthens precondition |
| Supertype has `@Max(100)`; override adds `@Max(50)` | **Invalid** | Cannot redeclare parameter constraints in an override |
| Supertype has `@NotBlank`; override also writes `@NotBlank` | **Invalid** | Even repeating an identical declaration is forbidden |
| Supertype has `@Valid` on parameter; override adds `@Valid` again | **Invalid** | Cannot add new cascade marker on an overridden parameter |
| Supertype has return `@NotNull`; override does not repeat annotation | **Valid** | Supertype return constraint continues to be evaluated |
| Supertype has return `@NotNull`; override adds `@Size(min=2)` | **Valid** | Strengthens/augments postcondition |
| Return `@Valid` on supertype; override repeats `@Valid` | **Invalid** | Cannot mark cascading for the same return value multiple times on one inheritance branch |
| Two **parallel** interfaces declare the same method, one has a parameter constraint | **Invalid** for a class implementing both | Prevents inconsistent input contracts between two supertypes |
| Subclass constructor has different constraints from parent constructor | **Exempt from this override rule** | Constructors do not override each other |

An invalid constraint declaration is typically reported by the provider via `jakarta.validation.ConstraintDeclarationException` when analyzing metadata or executing validation. **It does not necessarily happen at Java compile time or Spring bean creation.** Code may compile cleanly and only fail on the first validation call.

## 3. Why May Preconditions Not Be Strengthened?

### 3.1. Caller Perspective and Static Types

Suppose a published API says:

~~~java
public interface MessagePort {
    void send(String message);
}
~~~

A caller can write:

~~~java
void dispatch(MessagePort port) {
    port.send(""); // Interface declares no constraint.
}
~~~

If `MessagePortImpl` adds `@NotBlank` on its override, a call that is valid under the interface contract would be rejected by validation merely because the implementation changed. That is exactly what LSP forbids: a subtype instance must be substitutable for its supertype without introducing unexpected preconditions.

### 3.2. How to Place Constraints Properly

Put the condition on the contract **from the start**:

~~~java
import jakarta.validation.constraints.NotBlank;

public interface MessagePort {
    void send(@NotBlank String message);
}
~~~

The implementation **does not need to—and must not—** repeat `@NotBlank` on the overridden method's parameter:

~~~java
public class MessagePortImpl implements MessagePort {
    @Override
    public void send(String message) {
        System.out.println(message);
    }
}
~~~

When the validation engine validates `MessagePortImpl.send(...)`, it sees the parameter constraint declared on `MessagePort.send(...)`. Omitting the annotation on the implementation's parameter **does not erase** that constraint.

**Note:** Jakarta Validation does not automatically validate Java methods on every call. `ExecutableValidator`, Spring AOP method validation, or a framework integration must actually trigger it. Thus a method with an invalid declaration can appear to run "normally" when validation is never triggered; that does not make the declaration valid.

### 3.3. It Is Not Only `@NotNull` and `@Size`

Precondition rules apply to:

- Single-parameter constraints such as `@NotBlank`, `@Min`, `@Pattern`, and custom constraints.
- Constraints on a **parameter's type argument**, such as `List<@NotNull Item>`.
- **Cascaded validation** placed via `@Valid` on a parameter or parameter element.
- **Cross-parameter constraints** checking relationships across multiple arguments.

Misleading example:

~~~java
interface Importer {
    void importItems(List<String> items);
}

class StrictImporter implements Importer {
    @Override
    public void importItems(List<@NotBlank String> items) {
        // ...
    }
}
~~~

The snippet above adds a parameter element constraint in the override; in keeping with the spirit and rules of method parameter constraints, declare that requirement on the `Importer` interface instead of the implementation. Furthermore, depending on how type-use annotations are applied, the Java compiler has its own rules for overriding signatures; when debugging errors, distinguish Java compilation errors from provider `ConstraintDeclarationException`.

**There is no need to compare whether the new constraint is "stronger" or "weaker."** Under the specification's default rules, declaring any new parameter constraint on an overridden method is invalid. Even repeating `@NotBlank` identically to the interface annotation is not treated as a "harmless override."

### 3.4. Changing Business Rules Without Violating the Contract

If a use case genuinely needs stricter input requirements:

1. **Update the interface contract** if all implementations and callers must obey it.
2. **Define a new method** with a different name or signature expressing a different operation. A new overload does not override the old contract.
3. **Define a narrower interface** and use it for callers that fit that requirement, instead of sneaking stricter preconditions onto an inherited method.
4. For rules belonging only to one business layer, check them explicitly in the method body and design appropriate API error handling; still, if callers using the parent contract must remain substitutable, explicit validation should not break the promised contract semantics either.

Do not use validation groups or a custom annotation as a trick to disguise adding preconditions on an override. Activating a different group can alter runtime violation sets, yet it does not make a hierarchy-violating declaration portable.

## 4. Postconditions: May Be Augmented, Never Weakened

### 4.1. Return Constraints Are Aggregated Across the Hierarchy

This case is **valid**:

~~~java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

public interface TicketDirectory {
    @NotNull
    List<String> listTickets();
}

public class TicketDirectoryImpl implements TicketDirectory {
    @Override
    @Size(min = 2)
    public List<String> listTickets() {
        return List.of("T-1", "T-2");
    }
}
~~~

When `ExecutableValidator.validateReturnValue(...)` checks the return of `TicketDirectoryImpl.listTickets()`, both `@NotNull` from the interface and `@Size(min=2)` from the implementation are evaluated. If the return is `null`, `@NotNull` fails (while `@Size` normally considers null valid). If a single-element list is returned, `@Size` fails. Both conditions complement each other.

If the implementation omits `@NotNull` in its source code, the interface's condition **does not vanish**. This differs from what you might guess by inspecting only the implementation method's annotations via plain reflection: standard Bean Validation metadata merges constraints from supertypes.

### 4.2. Multiple Return Constraints May Be Added

~~~java
interface NameLookup {
    @NotNull
    String name();
}

class NameLookupImpl implements NameLookup {
    @Override
    @NotBlank
    @Size(min = 3)
    public String name() {
        return "Alice";
    }
}
~~~

`@NotNull` from the interface stays in effect. `@NotBlank` and `@Size(min=3)` on the implementation strengthen the guarantee to callers. This code **is permitted by inheritance rules**; the constraints must simply be satisfiable in business logic.

Be careful not to add contradictory constraints, such as `@NotNull` on the supertype and `@Null` on the subtype. Under inheritance rules, adding return constraints is not forbidden the way parameter constraints are; however, the combined postcondition may have **no valid value that satisfies all constraints at once**, causing the method to fail every time. Validation providers do not necessarily catch such logical contradictions at startup. Verify with tests for valid return values.

### 4.3. Covariant Return Types

Java allows a subtype to return a narrower subtype when overriding, for example:

~~~java
class Document {}
class PdfDocument extends Document {}

interface DocumentStore {
    @NotNull
    Document fetch();
}

class PdfStore implements DocumentStore {
    @Override
    @NotNull
    public PdfDocument fetch() {
        return new PdfDocument();
    }
}
~~~

Repeating `@NotNull` on the **return value** here is permitted in principle; it is a return constraint, unlike repeating annotations on parameters. Still, repeating it is unnecessary to preserve the interface's constraint; if you keep it to express intent, write tests to confirm the expected violation count. With differing return types, providers must still aggregate constraint metadata across the hierarchy accurately.

### 4.4. Return `@Valid`: Special Restriction

`@Valid` requests cascading into the returned object. You can **initiate** cascading in a subtype if the supertype has not marked it:

~~~java
interface CustomerSource {
    Customer load();
}

class ValidatingCustomerSource implements CustomerSource {
    @Override
    @Valid
    public Customer load() {
        return new Customer("An");
    }
}
~~~

However, if the supertype **already has `@Valid` on the return**, the subtype **must not mark `@Valid` again** on the same inheritance branch:

~~~java
interface CustomerSource {
    @Valid
    Customer load();
}

class DuplicateCascadeSource implements CustomerSource {
    @Override
    @Valid // Invalid: duplicate cascaded return on the same branch.
    public Customer load() {
        return new Customer("An");
    }
}
~~~

The two examples above are **two separate alternatives**; do not copy both `CustomerSource` definitions into a single Java file. Once the interface declares cascading, the implementation simply overrides the method and returns the object; the provider still validates properties inside that object.

Why does this restriction exist? A return validation pass must have a consistent cascade configuration; redeclaring `@Valid` and group conversions on overrides could mislead readers or produce conflicting cascade configurations.

**Group conversion:** `@ConvertGroup` is valid only alongside `@Valid`; adding or modifying group conversions on an override when return cascading is already configured on an ancestor has restrictions to ensure inherited supertype postconditions are not altered. For methods inherited from multiple parallel interfaces where return cascading exists on one branch, do not arbitrarily declare new group conversions on returns of parallel branches. If group switching is needed, design the contract where cascading is originally declared and test metadata/violations.

## 5. Two Parallel Interfaces: A Stricter Trap Than Normal Overriding

### 5.1. Invalid Example

~~~java
interface FastSender {
    void send(@NotBlank String text);
}

interface GeneralSender {
    void send(String text);
}

class CombinedSender implements FastSender, GeneralSender {
    @Override
    public void send(String text) {
        // ...
    }
}
~~~

The two interfaces **do not extend each other**, yet both declare `send(String)`. The implementation method overrides/implements both contracts. Because `FastSender` has a parameter constraint while `GeneralSender` does not, callers using `GeneralSender` could face unexpected preconditions.

Specification rule: if a method is inherited/implemented from **multiple parallel supertypes**, **none of the supertypes in those parallel branches may declare parameter constraints/cascades on that method**, even if two branches happen to declare the exact same constraint. Removing the annotation from `CombinedSender.send` alone is not enough to fix the example; the contracts on the supertypes themselves must change.

### 5.2. Valid Example

One design approach is moving the shared requirement up to **a common ancestor**, so the branches are no longer two independent sources of parameter contracts:

~~~java
interface BaseSender {
    void send(@NotBlank String text);
}

interface AuditedSender extends BaseSender {
    // Do not redeclare send(String).
}

interface RetryingSender extends BaseSender {
    // Do not redeclare send(String).
}

class CombinedSender implements AuditedSender, RetryingSender {
    @Override
    public void send(String text) {
        // ...
    }
}
~~~

In this diagram, there is **one place** declaring the parameter constraint (`BaseSender`); the remaining interfaces inherit that same contract and the implementation does not redeclare the constraint. This reduces conflict risk in multi-interface designs. When frameworks inspect metadata across parallel types, an integration test on the concrete implementation class confirms the specific hierarchy works.

Another option is renaming or changing signatures of methods that truly have different preconditions, avoiding forcing one implementation to satisfy two incompatible contracts.

### 5.3. When Does the Parallel Rule Not Apply?

If `ChildContract extends ParentContract`, those two interfaces have a **direct inheritance relationship**, forming a single hierarchy branch rather than two independent parallel interfaces. Parameter constraints declared on `ParentContract` apply to the implementing class method; `ChildContract` must not add constraints to the overridden method.

This distinction prevents the false conclusion that "any Java class implementing two interfaces forbids parameter constraints": only methods with **overlapping signatures and hierarchy** carrying constraints across parallel branches run into this issue.

## 6. Runnable Example: Java 17 + Spring Boot 3.5 + JUnit

This section contains a minimal Maven project testing **properly inherited** constraints in a Spring service and demonstrating **invalid** declarations via Jakarta `ExecutableValidator`. It uses Java 17, Spring Boot 3.5.7 (Spring Framework 6.2), and the `jakarta.validation.*` namespace.

Files:

~~~text
pom.xml
src/main/java/com/example/demo/
  DemoApplication.java
  CodePolicy.java
  DefaultCodePolicy.java
src/test/java/com/example/demo/
  CodePolicyIntegrationTest.java
  HierarchyRulesTest.java
~~~

### 6.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>validation-hierarchy-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-validation` brings in the Bean Validation provider to execute constraints; `spring-boot-starter-aop` ensures AOP infrastructure needed for service method validation; `spring-boot-starter-test` provides JUnit 5, AssertJ, and other test utilities. No web server or database is needed.

### 6.2. Spring Boot Application

~~~java
// src/main/java/com/example/demo/DemoApplication.java
package com.example.demo;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    // @SpringBootTest only needs one @SpringBootApplication on the classpath.
}
~~~

### 6.3. Interface as Contract Source

~~~java
// src/main/java/com/example/demo/CodePolicy.java
package com.example.demo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public interface CodePolicy {

    // Parameter constraint is properly declared on the interface.
    String generate(@NotBlank String prefix);

    // Interface guarantees a non-null return value.
    @NotNull
    List<String> availableCodes();
}
~~~

Annotations on **parameters** and **return values** are aggregated by the Jakarta Bean Validation provider for the corresponding implementation methods.

### 6.4. Implementation Only Adds Postconditions

~~~java
// src/main/java/com/example/demo/DefaultCodePolicy.java
package com.example.demo;

import jakarta.validation.constraints.Size;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;
import java.util.List;

@Service
@Validated
public class DefaultCodePolicy implements CodePolicy {

    @Override
    public String generate(String prefix) {
        return prefix + "-1";
    }

    @Override
    @Size(min = 2, message = "List must contain at least two codes")
    public List<String> availableCodes() {
        return List.of("A"); // Intentionally violates @Size to test return validation.
    }
}
~~~

Two key points:

1. `DefaultCodePolicy.generate` **does not repeat `@NotBlank`**, yet callers invoking through Spring validation are still checked when passing a blank string.
2. `DefaultCodePolicy.availableCodes` validly adds `@Size(min=2)`. The `@NotNull` constraint on `CodePolicy.availableCodes` still exists and participates in validation.

`@Validated` on the service bean enables proxy-based Spring method validation. Adding `@Validated` does not alter Jakarta Validation's inheritance rules; it only determines **when** constraints are enforced in Spring.

### 6.5. Spring Integration Test

~~~java
// src/test/java/com/example/demo/CodePolicyIntegrationTest.java
package com.example.demo;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class CodePolicyIntegrationTest {

    @Autowired
    CodePolicy service; // Bean obtained from Spring, with method validation proxy.

    @Test
    void acceptsValidInheritedPrecondition() {
        assertEquals("ORD-1", service.generate("ORD"));
    }

    @Test
    void inheritedParameterConstraintIsEnforced() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                () -> service.generate(" "));
        assertEquals(1, ex.getConstraintViolations().size());
    }

    @Test
    void additionalReturnConstraintIsEnforced() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                service::availableCodes);
        assertEquals(1, ex.getConstraintViolations().size());
    }

    @Test
    void parentNotNullStillAppliesWithoutRepeatAnnotation()
            throws Exception {
        DefaultCodePolicy target = new DefaultCodePolicy();
        Method method = DefaultCodePolicy.class
                .getMethod("availableCodes");

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            var errors = factory.getValidator()
                    .forExecutables()
                    .validateReturnValue(target, method, null);

            // @NotNull on interface reports an error; @Size allows null.
            assertEquals(1, errors.size());
        }
    }
}
~~~

In the `service.generate(" ")` test, there is no annotation on the implementation's parameter, yet a violation still occurs because the constraint is **inherited from the interface**. In the return test, the list has one element so `@Size(min=2)` is violated; `@NotNull` from the interface passes for that list. The final test explicitly passes `null` to `ExecutableValidator.validateReturnValue(...)` to prove `@NotNull` from the interface still applies even though the implementation did not repeat the annotation.

### 6.6. Testing Invalid Rules with `ConstraintDeclarationException`

Create this additional test file. The classes/interfaces inside the test intentionally model invalid situations and are **not registered as Spring beans**; the test uses `ExecutableValidator` directly.

~~~java
// src/test/java/com/example/demo/HierarchyRulesTest.java
package com.example.demo;

import jakarta.validation.ConstraintDeclarationException;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class HierarchyRulesTest {

    public interface PlainApi {
        String normalize(String value);
    }

    public static class IllegalOverride implements PlainApi {
        @Override
        public String normalize(@NotBlank String value) {
            return value;
        }
    }

    public interface StrictSender {
        void send(@NotBlank String text);
    }

    public interface PlainSender {
        void send(String text);
    }

    public static class IllegalParallel
            implements StrictSender, PlainSender {
        @Override
        public void send(String text) {
        }
    }

    public static class Customer {
        @NotBlank
        private final String name;

        public Customer(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    public interface CustomerSource {
        @Valid
        Customer load();
    }

    public static class InheritedCascade implements CustomerSource {
        @Override
        public Customer load() {
            return new Customer("");
        }
    }

    public static class DuplicateCascade implements CustomerSource {
        @Override
        @Valid // Invalid: supertype already has @Valid on the return value.
        public Customer load() {
            return new Customer("");
        }
    }

    @Test
    void addingParameterConstraintInOverrideIsIllegal()
            throws Exception {
        IllegalOverride target = new IllegalOverride();
        Method method = IllegalOverride.class
                .getMethod("normalize", String.class);

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            assertThrows(
                    ConstraintDeclarationException.class,
                    () -> factory.getValidator().forExecutables()
                            .validateParameters(
                                    target, method, new Object[]{"ABC"}));
        }
    }

    @Test
    void parameterConstraintAcrossParallelInterfacesIsIllegal()
            throws Exception {
        IllegalParallel target = new IllegalParallel();
        Method method = IllegalParallel.class
                .getMethod("send", String.class);

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            assertThrows(
                    ConstraintDeclarationException.class,
                    () -> factory.getValidator().forExecutables()
                            .validateParameters(
                                    target, method, new Object[]{"ABC"}));
        }
    }

    @Test
    void inheritedReturnCascadeStillWorks() throws Exception {
        InheritedCascade target = new InheritedCascade();
        Method method = InheritedCascade.class.getMethod("load");

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            var violations = factory.getValidator()
                    .forExecutables()
                    .validateReturnValue(target, method, target.load());

            assertEquals(1, violations.size());
        }
    }

    @Test
    void repeatingReturnCascadeInOverrideIsIllegal()
            throws Exception {
        DuplicateCascade target = new DuplicateCascade();
        Method method = DuplicateCascade.class.getMethod("load");

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            assertThrows(
                    ConstraintDeclarationException.class,
                    () -> factory.getValidator().forExecutables()
                            .validateReturnValue(
                                    target, method, target.load()));
        }
    }
}
~~~

**Note on test scope:** `IllegalOverride` and `IllegalParallel` intentionally have invalid metadata. Spring Boot does not scan them as `@Component` beans, so initializing the context for valid services stays isolated. In tests, the exception can be thrown when the provider analyzes method metadata to run `validateParameters`/`validateReturnValue`; the `assertThrows` blocks verify that exact contract.

Run everything:

~~~bash
mvn test
~~~

Expected: **8 tests PASS** (4 Spring integration tests, 4 `ExecutableValidator` tests) with no assertion failures when the project has the right dependencies. This outcome is expected from Jakarta Validation and Spring Boot semantics, not a claim that Maven was executed on your machine. Do not hardcode verbatim Maven stdout/logs because they depend on the environment.

## 7. Cases Requiring Careful Consideration

### 7.1. Sub-Interface Extending a Parent Interface

~~~java
interface BaseApi {
    void update(@NotBlank String id);
}

interface ExtendedApi extends BaseApi {
    // Merely inherits update, does not redeclare the constraint.
}

class ExtendedApiImpl implements ExtendedApi {
    @Override
    public void update(String id) {
        // ...
    }
}
~~~

This is a single inheritance chain, unlike two independent parallel interfaces. The constraint from `BaseApi` remains in effect. If `ExtendedApi` redeclared `update(@NotBlank String id)`, that would still be an overridden method with a new parameter constraint, which is not portable under the specification.

### 7.2. Overloading Is Not Overriding

~~~java
class Encoder {
    String encode(String value) {
        return value;
    }

    String encode(@NotBlank String value, int mode) {
        return mode + ":" + value;
    }
}
~~~

The two methods have **different parameter counts**, so they are overloads. Each signature has its own contract. Constraints on the new overload do not strengthen preconditions of the existing `encode(String)` method. However, if a subtype overrides an overload already present in the supertype, method override rules apply to that specific signature.

### 7.3. Covariant Returns and Java Visibility

Java overriding requires compatible/covariant return types and forbids reducing method visibility. Jakarta Validation **does not replace** these Java compilation rules: code must first compile as a valid override before the provider processes constraints.

When a return type is narrowed from `Object` to a subtype, constraints from the supertype method still apply when validating the subtype instance. When evolving an API, specifically test the narrowed return type alongside return constraints from all relevant supertypes.

### 7.4. Constructors Do Not Inherit Contracts via Overriding

~~~java
class BaseJob {
    BaseJob(@NotNull String name) {
    }
}

class DetailedJob extends BaseJob {
    DetailedJob(String name, @Min(1) int priority) {
        super(name);
    }
}
~~~

`DetailedJob` does not override `BaseJob`'s constructor. Under Jakarta Validation, when `validateConstructorParameters(...)` is called on `DetailedJob`'s constructor, **only constraints declared directly on that constructor** are evaluated. `@NotNull` on `BaseJob`'s constructor does not automatically carry over as a parameter constraint on the subclass constructor. Likewise, constructor return validation applies constraints directly on the constructor being inspected.

This concerns validation metadata, not whether `super(name)` executes: Java still calls the parent constructor during object construction.

### 7.5. Cross-Parameter Constraints and Container Elements

A cross-parameter constraint placed on a method with `ValidationTarget.PARAMETERS` counts as a **precondition**. Do not add it on an overridden method to impose a new rule on a subtype. Likewise, `@Valid` or `@NotNull` inside a parameter's type argument is part of the input contract.

Example with annotation placed properly on the interface and not repeated in the implementation:

~~~java
interface BatchWriter {
    void write(List<@NotBlank String> names);
}

class BatchWriterImpl implements BatchWriter {
    @Override
    public void write(List<String> names) {
        // ...
    }
}
~~~

Here container element validation is declared on the interface. Providers need a value extractor for the container, though `List` is widely supported out of the box. Note that `@NotBlank` on the element alone does not forbid `names == null`; if the list itself is required, add `@NotNull` **on the parameter in the interface**.

### 7.6. Validation Groups

Constraints in a custom group such as `UpdateGroup` only run when that group is requested. This does not alter hierarchy declaration rules: a subtype **may not add parameter constraints** even if they belong to a group the application "rarely" invokes.

When different groups are needed for different use cases, define separate contracts or structure groups at the original contract source. Do not use `@Validated(SomeGroup.class)` on a subclass as a workaround to add `@NotBlank(groups=SomeGroup.class)` to an overridden parameter; providers may still reject that declaration as invalid.

### 7.7. Getters and Property Validation

`@NotNull` on a getter can be interpreted as a JavaBean property constraint during `Validator#validate(bean)`, while the method can also be validated via `ExecutableValidator#validateReturnValue(...)`. The two validation modes have **different scopes and lifecycles**; do not run both and sum error counts without realizing they can hit the same constraint.

With method overriding, the provider gathers constraints across the hierarchy. If a design places constraints at both field level and getter level for the same data, test carefully to avoid duplicate error reports.

### 7.8. Spring Proxies Do Not Erase or Alter Hierarchy Contracts

In Spring Framework, `@Validated` services are typically checked via a Spring AOP proxy. Input violations can become `ConstraintViolationException`; without a proxy, direct `new` calls or `this.method(...)` self-invocations are normally not intercepted. Spring Boot 3.x with `MethodValidationPostProcessor` has its own adaptation option, so exceptions can differ by configuration.

**Inheritance rules still belong to Jakarta Validation**; Spring does not arbitrarily permit parameter constraints on overrides. Even if a class compiles or a Spring context boots, test with a real validator on the method itself to check metadata.

For Spring MVC 6.1+ controllers specifically, there is built-in handler method validation and `HandlerMethodValidationException`; class-level `@Validated` can switch a controller to AOP method validation. Framework choices affect **trigger points and error reporting**, not Bean Validation's LSP rules.

## 8. Hibernate Validator Options to Relax Rules: Use Very Cautiously

Hibernate Validator provides **provider-specific options** that can relax the default rules:

- `hibernate.validator.allow_parameter_constraint_override`: allows parameter constraints on overrides.
- `hibernate.validator.allow_parallel_method_parameter_constraint`: allows parameter constraints from parallel branches.
- `hibernate.validator.allow_multiple_cascaded_validation_on_result`: allows repeated cascading on returns.

These flags default to **false** for strict compliance with standard rules. They can be configured via `validation.xml` or Hibernate Validator's proprietary bootstrap API. Once enabled, the application is no longer fully portable across Jakarta Validation providers; differences in constraint aggregation, inheritance, and group conversion must be verified against your exact provider version.

If your goal is a widely reusable Java/Spring library, **fix the interface/hierarchy** to comply with Jakarta Validation rather than enabling relaxation flags. Consider these extensions only when maintaining legacy systems, with full awareness of their impact, test coverage across diverse caller types, and explicit acceptance of Hibernate Validator coupling.

## 9. Diagnosing `ConstraintDeclarationException`

A common situation: the application reaches a request or validation test and throws an error mentioning overriding methods, parallel interfaces, or multiple cascaded return values. Work through it step by step:

1. **Identify the method signature** in the exception: method name and parameter list, not just the logged class name.
2. **Inspect all supertypes** declaring or implementing that same signature: interfaces, superclasses, parent interfaces. For parallel hierarchies, inspect every branch.
3. **Separate parameters from return values**: adding annotations on method returns is generally valid; adding annotations on overridden parameters is not.
4. **Look for repeated `@Valid`** on returns along the inheritance branch; look for `@Valid` on overridden parameters; also check related `@ConvertGroup` annotations.
5. **Look for container element or cross-parameter constraints** even if `@NotNull` is not directly on the parameter.
6. **Fix at the contract source**: move parameter constraints up to the appropriate supertype; remove annotations from overrides; unify parallel interfaces where needed.
7. **Test with `ExecutableValidator`** on the concrete class and actual method; call `validateParameters(...)` and `validateReturnValue(...)` to verify metadata.
8. **Test Spring integration** if using `@Validated`: verify calls go through the proxy or MVC handler and check exception mapping at the HTTP layer.

Do not confuse `ConstraintDeclarationException` (invalid constraint declaration/hierarchy) with `ConstraintViolationException` (valid constraints violated by actual runtime data). These two exceptions require opposite responses: declaration errors must be fixed by developers in code/config; data violations can be returned to callers with suitable messages.

## 10. Common Design Mistakes

1. **Repeating `@NotBlank` in the implementation to "document" the interface**: still invalid per spec. Put JavaDoc in the implementation if clarity is needed, and keep constraints on the contract.
2. **Not seeing the annotation in the implementation and assuming the constraint was lost**: providers aggregate across the hierarchy; verify with `ExecutableValidator`.
3. **Placing `@Valid` on an overridden parameter just to cascade deeper**: that alters the precondition; place it on the original declaration.
4. **Two interfaces sharing a method where one branch has a parameter constraint**: parallel structures can be invalid even if the implementation adds nothing.
5. **Repeating return `@Valid` on both base and override**: rules forbid double cascaded returns on a single branch; remove `@Valid` from the override.
6. **Changing return `@NotNull` to `@NotBlank` thinking it replaces the old constraint**: return constraints from the base remain; the new constraint is added alongside them.
7. **Creating two conflicting return constraints**: no return value may ever satisfy both. Additions must align with business logic.
8. **Expecting the compiler to report Jakarta Validation errors**: hierarchy errors are normally thrown by the provider when reading metadata or validating, not by the default Java compiler.
9. **Mixing `javax.validation.*` with Spring Boot 3.x**: Boot 3 uses `jakarta.validation.*` and compatible providers.
10. **Forgetting the method validation trigger in Spring**: proxies, `@Validated`, and bean lifecycle must be wired up. Jakarta annotations do not throw on ordinary Java method calls by themselves.
11. **Enabling Hibernate Validator extensions as a "quick fix"**: breaks portability and substitution principles. Prefer fixing the API contract.
12. **Misunderstanding constructor overrides**: constructors are not inherited via method overriding; only constraints directly on the constructor apply.

## 11. Pull Request Review Checklist

- [ ] Parameter constraints (including `@Valid`, container elements, cross-parameter) are declared at the proper input contract level, **never added on overrides**.
- [ ] No shared method across parallel interfaces carries parameter constraints in an incompatible hierarchy.
- [ ] New return constraints on implementations complement supertype constraints without logical contradictions.
- [ ] Return `@Valid` is declared at most once per branch; group conversions do not invalidly alter inherited cascade contracts.
- [ ] Overloads are distinguished from overrides, and constructors from methods.
- [ ] `ExecutableValidator` tests verify both valid and invalid metadata, not just happy-path data cases.
- [ ] With Spring, tests invoke managed beans through proxies and cover parameter/return cases; do not extrapolate from `new` or self-invocation.
- [ ] No Hibernate Validator-specific relaxation flags are required to run standard contracts.

## References

- Jakarta Validation 3.1 Specification, `5.6.5 “Method constraints in inheritance hierarchies”: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#method-constraints-in-inheritance-hierarchies
- Hibernate Validator Reference Guide, `3.1.4 “Method constraints in inheritance hierarchies”: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#section-method-constraints-inheritance
- Hibernate Validator Reference Guide, “Relaxation of requirements for method validation in class hierarchies”: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#section-method-validation-configuration
- Spring Boot 3.5 Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Framework 6.2 Method Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
