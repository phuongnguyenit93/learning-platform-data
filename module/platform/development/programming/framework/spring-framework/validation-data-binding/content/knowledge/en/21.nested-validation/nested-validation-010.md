# Constraint Inheritance from Superclasses and Interfaces in Bean Validation

## 1. The Problem: Is a Subclass Still Constrained by Its Superclass?

In Spring Framework applications, DTOs, entities, and services are often organized using Java inheritance hierarchies. A subclass may inherit properties from a superclass, implement interfaces, override getters, or override service methods. The question is: **do validation annotations placed on a superclass or interface still apply when validating an instance of the subclass?**

**Yes** for applicable bean constraints: Jakarta Bean Validation considers constraints declared on fields, getters, and classes of **superclasses** and **interfaces** in the type hierarchy when calling `Validator.validate(subclassInstance)`. Constraints on the subclass are additive; they do not by default erase inherited constraints. `@Valid` annotations in the object hierarchy can also be inherited and used for cascading.

However, **method validation** has stricter rules. When overriding or implementing a method:

- You must **not strengthen parameter preconditions** (`precondition`) in a subtype: per the specification, a subtype must not add or redeclare constraints on parameters of an overridden/implemented method, including `@Valid` on parameters.
- You may **add constraints on the return value** (`postcondition`) in a subtype, while still obeying rules on `@Valid` for return values and parallel inheritance across multiple interfaces.
- Placing annotations on methods **does not mean validation automatically runs on every method call**. You need `ExecutableValidator`, Spring method validation integration, or an equivalent invocation mechanism.

This document focuses on **"Constraint Inheritance from Superclasses and Interfaces"** within the **"Nested Validation"** group, and therefore also clarifies the combination of type inheritance and `@Valid` when a bean contains child objects.

### Learning Outcomes

After this lesson, you will be able to:

1. Identify which constraints are inherited from superclasses/interfaces when validating a subclass instance.
2. Distinguish constraints on fields, getters, classes, parameters, and return values.
3. Write getter overrides without accidentally losing interface/superclass constraints.
4. Explain inherited `@Valid` and why null is not cascaded.
5. Design method interfaces in accordance with the Liskov Substitution Principle (LSP).
6. Avoid `ConstraintDeclarationException` when extending interfaces or overriding methods.
7. Write tests checking bean validation and executable validation with Jakarta Validator, while understanding the corresponding Spring activation points.

## 2. Inheritance Rules for Bean Constraints

Suppose:

~~~text
                  Identifiable (interface)
                      getCode()
                          |
                          v
                  BaseAccount (class)
                    id, address
                          |
                       extends
                          |
                          v
                   CustomerAccount
                      email, age
~~~

When the runtime object is a `CustomerAccount`, calling:

~~~java
Set<ConstraintViolation<CustomerAccount>> errors =
    validator.validate(customerAccount);
~~~

uses applicable constraint metadata from the entire type hierarchy, not just annotations written directly on `CustomerAccount`.

| Constraint Location | Inherited When Validating Subclass? | Example |
| --- | --- | --- |
| Field in superclass | **Yes** | `@NotBlank private String id;` in `BaseAccount`. |
| Getter of superclass | **Yes** | `@Size(min=3) public String getCode()`. |
| Getter declared in interface | **Yes** | `@Email String getEmail();`. |
| Class-level constraint on superclass/interface | **Yes** | `@ValidBaseRecord` placed on type supporting `TYPE` target. |
| `@Valid` placed on superclass property | **Yes** | `@Valid private Address address;`. |
| Subclass's own field constraint | **Yes, additive** | `@Min(18) private int age;`. |
| Constraint on method parameter | **Special override rules** | Interface defines `void save(@NotNull Input input)`. |
| Constraint on method return value | **Special override rules** | Interface `@NotNull Result load()`. |
| Constructor constraints | No "constructor inheritance" in Java | Only checks constraints declared on that specific constructor. |

Standard Bean Validation **does not depend on whether Java annotations carry `@Inherited` to apply the rules above**. Java's `@Inherited` has limited semantics for class annotations and does not handle inheritance on interfaces, getters, or methods. Bean Validation providers must apply the specification's own metadata and validation rules.

**Conclusion:** The absence of an annotation in a subclass's source code **does not prove the constraint is gone**. Inspect interfaces and superclasses or query metadata via `Validator.getConstraintsForClass(...)`.

## 3. Field Constraints from Superclasses

A field constrained in a superclass is still evaluated when validating a subclass instance.

~~~java
import jakarta.validation.constraints.NotBlank;

class BaseEntity {
    @NotBlank(message = "id is required")
    private String id;

    BaseEntity(String id) {
        this.id = id;
    }
}

class UserEntity extends BaseEntity {
    private int level;

    UserEntity(String id, int level) {
        super(id);
        this.level = level;
    }
}
~~~

This is an **illustrative declaration**: when `Validator.validate(new UserEntity("", 1))` runs in an application with a provider, the `@NotBlank` constraint declared in `BaseEntity` still applies to the `UserEntity` instance's data.

You **do not need to repeat `@NotBlank` on the subclass**. Repeating annotations out of fear that the superclass won't be checked increases maintenance cost and can produce duplicate violations if placed at multiple locations for the same property.

### Constraints from Multiple Superclass Levels

~~~text
AuditedEntity
    @NotNull createdAt
       |
       v
CatalogEntity
    @NotBlank code
       |
       v
ProductEntity
    @Positive price
~~~

`Validator.validate(productEntity)` can check all three constraints as long as they belong to the active validation group and the values/properties are accessible per the Bean Validation model. It is not limited to the immediate superclass.

**Do not confuse this with Java field hiding.** If a subclass declares a new field with the same name as a superclass field, those are **two separate fields**, not a field override. Bean Validation can observe different metadata on each field. Using field hiding in DTOs/entities easily causes ambiguity between bound, serialized, and validated data; avoid this design. Use clear property names and consistent constraint placement.

### Constraints Declared on Both Field and Getter

Example:

~~~java
class Product {
    @NotBlank
    private String code;

    @NotBlank
    public String getCode() {
        return code;
    }
}
~~~

The constraint is declared **twice** at two access points. When `code` is blank, multiple constraint violations can appear for the same property. Usually standardize on **field-level** or **getter-level** for a given rule unless there is a genuinely different purpose. This is even more important in hierarchies where a superclass uses getter constraints while a subclass adds a field constraint with the same intent.

## 4. Getter Constraints from Superclasses Survive Overrides

Suppose a superclass publishes a contract on the return value of a JavaBean getter:

~~~java
import jakarta.validation.constraints.Size;

class Document {
    private final String code;

    Document(String code) {
        this.code = code;
    }

    @Size(min = 3, max = 8)
    public String getCode() {
        return code;
    }
}

class SpecialDocument extends Document {
    SpecialDocument(String code) {
        super(code);
    }

    @Override
    public String getCode() {
        return super.getCode();
    }
}
~~~

`@Size` on `Document.getCode()` is a **property constraint**. It still applies when validating `SpecialDocument` even when the overridden method in the subclass **does not repeat the annotation**. For example, `"X"` (length 1) fails `@Size(min=3)`.

**Two conditions must be distinguished:**

- When calling `validator.validate(specialDocument)`, the getter constraint participates in **bean/property validation**.
- Do not infer that merely calling `specialDocument.getCode()` causes `@Size` to run and throw an error. That is still a plain Java method call.

### What If the Subclass Adds a Getter Constraint?

For example, the superclass has `@Size(min=3)`, and the subclass adds its own constraint on the getter:

~~~java
class StrictDocument extends Document {
    StrictDocument(String code) {
        super(code);
    }

    @Override
    @Pattern(regexp = "[A-Z0-9]+")
    public String getCode() {
        return super.getCode();
    }
}
~~~

This snippet requires importing `jakarta.validation.constraints.Pattern`. A `StrictDocument` instance can be validated against **both the inherited `@Size` and the added `@Pattern`**. `@Pattern` does not "override" `@Size`. Adding a constraint to a method's **return value** is a valid change under method inheritance rules; here, the getter is also a bean property. Do not conclude from this that you can freely add constraints to **parameters** of overridden methods (the rule for parameters is completely different).

### Getter Access vs. Field Access

A getter constraint validates **the value returned by the getter**; a field constraint validates the constrained field. If a getter transforms or computes data (e.g., returning a normalized `String`), the result may differ from the raw field. Therefore:

- Ensure getters have no side effects and do not invoke expensive infrastructure when the provider reads properties.
- Choose annotation placement consistent with the data you want validated.
- Do not add constraints on an overridden getter solely to "preserve" the superclass constraint.

## 5. Constraints from Interfaces: Implementing Classes Must Still Satisfy Them

Java interfaces do not carry instance fields, but an interface can declare **getter constraints**, method parameter constraints, and return-value constraints. Bean Validation collects applicable constraints from interfaces.

Example:

~~~java
import jakarta.validation.constraints.Email;

interface ContactView {
    @Email(message = "email is invalid")
    String getEmail();
}

class Customer implements ContactView {
    private final String email;

    Customer(String email) {
        this.email = email;
    }

    @Override
    public String getEmail() {
        return email;
    }
}
~~~

When a `Customer` is validated with `Validator.validate(...)`, `@Email` declared on `ContactView.getEmail()` still applies. `Customer.getEmail()` does not need to repeat `@Email`.

This is useful when multiple implementations must uphold a shared data contract:

~~~text
                ContactView
              @Email getEmail()
                 /       \
                /         \
          Customer       Partner
             |              |
        getEmail()      getEmail()
~~~

Both implementations can be validated against the constraint on the interface. If a subclass also inherits constraints from a superclass, Bean Validation combines metadata across the applicable type paths rather than picking only a single source.

### Interface Getter Constraints Are Not Spring AOP Activation

With `Validator.validate(customer)`, you do not need `@Validated` on the interface just for Bean Validation to recognize `@Email`. Spring's `@Validated` generally serves to **select groups/activate method validation** in Spring's infrastructure; it does not replace constraint annotations. Likewise, Bean Validation annotations on an interface do not by themselves cause Java or Spring to run validation on every getter or service method call.

### Class-Level Constraints from Interfaces

A project-defined constraint with `@Target(TYPE)` can be placed on an interface:

~~~java
@ValidCustomerContract
interface CustomerContract {
    String getCustomerCode();
}

class CustomerRecord implements CustomerContract {
    @Override
    public String getCustomerCode() {
        return "C123";
    }
}
~~~

This is an **illustrative snippet** only; `@ValidCustomerContract` must be a valid constraint annotation with a `ConstraintValidator` and appropriate groups. When validating a `CustomerRecord` instance, the type-level constraint declared on the interface can be evaluated per specification. In practice, use class-level constraints when conditions span multiple properties rather than stuffing cross-field rules into a single getter.

## 6. Connection to Nested Validation: `@Valid` Is Also Inherited

`@Valid` does not enforce requiredness by itself; it marks a site for **cascaded validation** into a non-null child object. This marker can reside in a superclass or interface and still take effect when validating an inheriting child bean.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

class Address {
    @NotBlank
    String city;
}

class BaseProfile {
    @Valid
    @NotNull
    Address address;
}

class PremiumProfile extends BaseProfile {
    @NotBlank
    String membershipCode;
}
~~~

For `PremiumProfile`:

- If `address` is non-null and `address.city` is blank, Bean Validation follows the inherited `@Valid` on `BaseProfile.address` and produces a violation with a property path like `address.city`.
- If `address == null`, `@Valid` **skips null**; `@NotNull` on the base property is what rejects null.
- If `membershipCode` is blank, the subclass's own constraint is also checked.
- If multiple violations occur, `Set<ConstraintViolation<PremiumProfile>>` guarantees no iteration order.

**Constraint inheritance** and **cascading** are two independent yet complementary mechanisms:

~~~text
PremiumProfile instance
    |
    +-- @NotNull / @Valid address   (declared on BaseProfile)
    |       |
    |       +-- Address.city @NotBlank
    |
    +-- membershipCode @NotBlank   (declared on PremiumProfile)
~~~

If `@Valid` is omitted on the base class, the `Address` child bean is not traversed automatically just because the `address` field exists. If `@NotNull` is omitted, a null address remains valid from the cascade perspective. These are two common design mistakes in multi-level object models.

### Cascading Through an Interface Getter

~~~java
interface HasAddress {
    @Valid
    Address getAddress();
}

class Employee implements HasAddress {
    private Address address;

    @Override
    public Address getAddress() {
        return address;
    }
}
~~~

This illustrative snippet uses `Address` and imports `@Valid`. When validating an `Employee` bean, the provider can cascade through the property getter marked `@Valid` on the interface. To require an address to be present, also declare `@NotNull` where the contract belongs. Do not repeat `@Valid` on the overridden getter just for inheritance; on executable method return values, repeating `@Valid` along the same inheritance line can even **violate the specification** (see Section 11).

## 7. Distinguishing Bean Property Validation from Executable Method Validation

This is an important technical boundary when working with interfaces/superclasses.

| Action | API/Trigger Point | Which Constraints Apply? |
| --- | --- | --- |
| Validate an object's state | `Validator.validate(bean)` | Field, getter, class-level, and `@Valid` cascades per active groups and hierarchy. |
| Validate one bean property | `Validator.validateProperty(bean, "name")` | Constraints on the property; does not cascade `@Valid` per specification. |
| Validate a hypothetical value | `Validator.validateValue(Type.class, "name", value)` | Constraints on the target property; needs no bean instance and does not cascade. |
| Validate parameters of a method call | `validator.forExecutables().validateParameters(...)` | Parameter/cross-parameter constraints on the executable, including valid inheritance. |
| Validate a method's return value | `validator.forExecutables().validateReturnValue(...)` | Return-value constraints and corresponding cascades from the hierarchy. |
| Spring service method validation | Proxy/AOP and/or `MethodValidationPostProcessor` | Uses executable metadata; must actually be enabled and invoked through the proper mechanism. |
| Spring MVC request DTO | `@Valid @RequestBody` or `@ModelAttribute` ... | Typically uses bean validation and Spring `BindingResult`/`Errors`. |

**Do not conflate:** `@NotBlank` on `User.getName()` serves bean property validation; `@NotBlank` on parameter `Service.register(String name)` serves method-parameter validation. The specification states that getters are not by default treated as constrained methods for executable validation; validating getters as properties remains completely valid.

A service interface with an annotation:

~~~java
interface OrderService {
    void submit(@NotNull Order input);
}
~~~

does not by itself make `new OrderServiceImpl().submit(null)` throw an error. For method constraints to run, `ExecutableValidator` or properly configured Spring method-validation integration must be active.

## 8. Liskov Principle and Method Parameter Override Rules

In an inheritance hierarchy, a subtype must be substitutable for its supertype without unexpectedly rejecting calls that were previously valid. Jakarta Bean Validation applies this principle to method constraints:

- **Parameters = preconditions** on the caller.
- **Return value = postconditions** guaranteed by the implementation.

### 8.1. Valid: Declare Parameter Constraints on the Interface, Do Not Repeat in Implementation

~~~java
import jakarta.validation.constraints.NotBlank;

interface SearchService {
    String search(@NotBlank String query);
}

class SearchServiceImpl implements SearchService {
    @Override
    public String search(String query) {
        return "result";
    }
}
~~~

The parameter contract lives on the interface; the implementation **does not need to and must not redeclare** constraints on the overridden method's parameters under portable rules. Method validation of `SearchServiceImpl.search(...)` still sees `@NotBlank` from the interface.

### 8.2. Invalid: Subtype Adds Its Own Parameter Constraint

~~~java
interface LegacySearch {
    String search(String query);
}

class StrictSearch implements LegacySearch {
    @Override
    public String search(@NotBlank String query) { // INVALID
        return "result";
    }
}
~~~

This annotation alters the input preconditions in a way callers of `LegacySearch` do not expect. A compliant Bean Validation provider must throw `ConstraintDeclarationException` when detecting invalid method constraint declarations. This is an **intentionally invalid example**; do not include it in the runnable project later.

### 8.3. Repeating `@NotBlank` on an Override Is Still a Violation

~~~java
interface CheckedSearch {
    String search(@NotBlank String query);
}

class CheckedSearchImpl implements CheckedSearch {
    @Override
    public String search(@NotBlank String query) { // INVALID
        return "result";
    }
}
~~~

Even with the exact same annotation, declaring a parameter constraint in a subtype **still violates the override rule**. "Repeating for clarity" does not make the declaration valid. Keep method parameter constraints at the highest appropriate contract source, typically the interface/superclass where the method is defined.

### 8.4. `@Valid` on Parameter Overrides Is Also Restricted

~~~java
interface PaymentProcessor {
    void process(Payment payment);
}

class PaymentProcessorImpl implements PaymentProcessor {
    @Override
    public void process(@Valid Payment payment) { // INVALID
    }
}
~~~

This is an intentionally invalid illustrative snippet requiring a `Payment` class. Adding `@Valid` on an overridden method parameter also strengthens preconditions/cascading compared to the original contract. To deeply validate `Payment`, put `@Valid` on the interface/superclass parameter from the start, or introduce a separate method with a new contract.

**Note:** Method parameter override rules do not prevent a subclass from **adding its own field/getter constraints** for bean validation. Those are two separate validation layers and must be distinguished.

## 9. Return Value Rules: You Can Strengthen Guarantees, Not Remove Existing Constraints

Opposite to preconditions, a subtype may make **postconditions stricter** while remaining safe for interface callers.

~~~java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

interface TokenProvider {
    @NotNull(message = "token is required")
    String create();
}

class SecureTokenProvider implements TokenProvider {
    @Override
    @Size(min = 8, message = "token is too short")
    public String create() {
        return "123"; // Example intentionally returning a value failing @Size.
    }
}
~~~

This is a **structurally valid illustrative snippet**, though the implementation returns an invalid value to explain the outcome:

- The interface's `@NotNull` constraint still applies.
- `@Size(min=8)` on the implementation is **added**, not replacing `@NotNull`.
- When calling `ExecutableValidator.validateReturnValue(...)` with `"123"`, `@Size` fails while `@NotNull` passes.
- When calling Java `create()` normally without triggering method validation, the provider does not run automatically and throws no exception.

Do not misread "subclasses may add return-value constraints" as "they may remove old annotations": omitting an annotation in the subclass source code **does not remove** the interface/superclass constraint.

If an implementation truly requires a weaker return-value contract, that likely belongs on a different method or different interface; do not rely on overriding to weaken a published contract.

## 10. Multiple Parallel Interfaces: Trap with Parameter Constraints

A class can implement multiple interfaces not on the same inheritance branch:

~~~java
interface SearchA {
    void search(@NotBlank String query);
}

interface SearchB {
    void search(String query);
}

class CombinedSearch implements SearchA, SearchB {
    @Override
    public void search(String query) {
    }
}
~~~

This is an **intentionally invalid example from a method-constraints perspective**, even though the Java code compiles. Jakarta Bean Validation specifies: if a method is inherited from **parallel types with no inheritance relationship** (such as two independent interfaces), **neither parameter constraints nor parameter `@Valid` cascades may be declared for that method on any branch**. Here `SearchA.search` has `@NotBlank`, violating the rule.

What surprises developers: **even if only one of the two interfaces has a constraint**, the structure above is still non-portable. Some providers offer specific flags to relax this rule, but that ceases to be a portable Jakarta Bean Validation contract.

Design guidance:

1. Place the method parameter contract in **a single root interface**, and have other interfaces extend it where appropriate.
2. Split methods into two distinct operations/names to avoid a single method having two conflicting contract sources.
3. Keep parameter constraints in another service layer when integrating external interfaces you cannot modify; do not rely on provider-specific switches if portability matters.
4. Write metadata and `ExecutableValidator` tests for classes implementing multiple interfaces; do not stop at "it compiles in Java."

### What About Inheriting Interfaces Along a Single Branch?

~~~java
interface BaseQuery {
    void search(@NotBlank String query);
}

interface ExtendedQuery extends BaseQuery {
    // No need to redeclare search or @NotBlank parameter.
}

class QueryImpl implements ExtendedQuery {
    @Override
    public void search(String query) {
    }
}
~~~

Along a valid single inheritance line, the method parameter constraint on `BaseQuery` can still be enforced on `QueryImpl` via executable validation. `ExtendedQuery` and the implementation must not add constraints onto that method parameter.

## 11. `@Valid` on Return Values: Do Not Mark Cascading Twice in the Same Hierarchy Line

Per the specification, a subtype may declare return-value `@Valid` cascading when the supertype has not declared it. However, **you must not mark a return value for cascading more than once along the same class/interface hierarchy line**.

Intentionally invalid example:

~~~java
interface AddressGateway {
    @Valid
    Address load();
}

class DefaultAddressGateway implements AddressGateway {
    @Override
    @Valid // INVALID: @Valid is already on interface return value.
    public Address load() {
        return new Address();
    }
}
~~~

This is an illustrative snippet; `Address` must exist in the project and `@Valid` must be imported. In Java, this does not necessarily cause a compile error, but the provider must detect duplicate return-value cascade declarations under inheritance rules and may throw `ConstraintDeclarationException` when metadata or executable validation is accessed.

Correct approach:

~~~java
interface AddressGateway {
    @Valid
    Address load();
}

class DefaultAddressGateway implements AddressGateway {
    @Override
    public Address load() {
        return new Address();
    }
}
~~~

Here `@Valid` from the interface still applies. When validating a non-null return value, `Address`'s constraints are cascaded. If the method returns `null`, `@Valid` itself does not reject null; combine `@NotNull` on the return-value contract if data is required to be present.

You may **add other return-value constraints** in the subtype where valid, but do not arbitrarily repeat `@Valid`. Provider settings that relax this rule are provider-specific and must be explicitly tested.

## 12. Runnable Java 17 Program: Inheritance from Superclasses, Interfaces, and Method Constraints

To observe everything completely without starting a web server, we run a **Java 17** Maven project using **Jakarta Bean Validation 3.0** and **Hibernate Validator 8.0.6.Final**. Version 8.0.6.Final is a release in the 8.0 line and uses the `jakarta.validation.*` namespace. The intentionally invalid examples from Sections 8, 10, and 11 **are excluded from this project**.

Structure:

~~~text
constraint-inheritance-demo/
├── pom.xml
└── src/
    ├── main/java/demo/InheritanceDemo.java
    └── test/java/demo/InheritanceDemoTest.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>constraint-inheritance-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.6.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The `org.hibernate.validator:hibernate-validator` dependency supplies the provider; the Jakarta API is pulled in transitively. `org.glassfish.expressly:expressly` is a Jakarta Expression Language implementation used for message interpolation when running standalone Java SE. In Spring Boot applications already using the validation starter and BOM, generally let Boot manage versions to avoid incompatibilities.

### 12.1. File src/main/java/demo/InheritanceDemo.java

~~~java
package demo;

import java.lang.reflect.Method;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import jakarta.validation.executable.ExecutableValidator;

public class InheritanceDemo {

    interface EmailView {
        @Email(message = "email invalid")
        String getEmail();
    }

    static final class Address {
        @NotBlank(message = "city required")
        private final String city;

        Address(String city) {
            this.city = city;
        }
    }

    static class BaseMember {
        @NotBlank(message = "id required")
        private final String id;

        @NotNull(message = "address required")
        @Valid
        private final Address address;

        private final String code;

        BaseMember(String id, String code, Address address) {
            this.id = id;
            this.code = code;
            this.address = address;
        }

        @Size(min = 3, max = 8,
              message = "code length must be 3..8")
        public String getCode() {
            return code;
        }
    }

    static final class Member extends BaseMember implements EmailView {
        @Min(value = 18, message = "age must be at least 18")
        private final int age;

        private final String email;

        Member(String id, String code, Address address,
               String email, int age) {
            super(id, code, address);
            this.email = email;
            this.age = age;
        }

        @Override
        public String getEmail() {
            return email;
        }

        // Override getter; superclass @Size still applies.
        @Override
        public String getCode() {
            return super.getCode();
        }
    }

    interface LookupService {
        @NotNull(message = "result required")
        String find(
            @NotBlank(message = "query required") String query);
    }

    static final class LookupServiceImpl implements LookupService {
        @Override
        @Size(min = 3, message = "result too short")
        public String find(String query) {
            return "x";
        }
    }

    static Member invalidMember() {
        return new Member(
            "", "X", new Address(""), "wrong-email", 16);
    }

    static Member validMember() {
        return new Member(
            "ID-7", "C123", new Address("Ha Noi"),
            "member@example.com", 20);
    }

    public static void main(String[] args)
            throws NoSuchMethodException {

        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            Set<ConstraintViolation<Member>> errors =
                validator.validate(invalidMember());

            System.out.println("beanErrors=" + errors.size());
            errors.stream()
                .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                .sorted()
                .forEach(System.out::println);

            System.out.println(
                "validBeanErrors=" +
                validator.validate(validMember()).size());

            LookupServiceImpl service = new LookupServiceImpl();
            Method method = LookupServiceImpl.class
                .getMethod("find", String.class);

            ExecutableValidator executable =
                validator.forExecutables();

            var parameterErrors = executable.validateParameters(
                service, method, new Object[]{""});

            var returnErrors = executable.validateReturnValue(
                service, method, "x");

            System.out.println(
                "parameterErrors=" + parameterErrors.size());
            System.out.println(
                "returnErrors=" + returnErrors.size());
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.InheritanceDemo
~~~

Stdout produced by the program (Maven/provider may emit logs outside these lines):

~~~text
beanErrors=5
address.city: city required
age: age must be at least 18
code: code length must be 3..8
email: email invalid
id: id required
validBeanErrors=0
parameterErrors=1
returnErrors=1
~~~

### 12.2. Explaining the Five Bean Errors

1. `BaseMember.id` has `@NotBlank` in the **superclass**; `Member` instance has `id=""` → 1 error.
2. `BaseMember.getCode()` has `@Size(min=3,max=8)`; `Member` overrides the getter without annotations, yet `code="X"` is still too short → 1 error.
3. `EmailView.getEmail()` has `@Email` from the **interface**; `Member` implements the getter returning `"wrong-email"` → 1 error.
4. `Member.age` has `@Min(18)` in the **subclass**; `age=16` → 1 error.
5. `BaseMember.address` has `@Valid`; the `Address` bean exists, and `city=""` fails `@NotBlank` → 1 error.

Total 5. `validMember()` satisfies those constraints so `validBeanErrors=0`.

For `LookupService`:

- The interface declares the `@NotBlank` parameter on `find(String query)`.
- The implementation **does not repeat** the parameter constraint, yet `ExecutableValidator.validateParameters(...)` still catches the empty query → `parameterErrors=1`.
- The interface declares `@NotNull` on return; the implementation **adds** `@Size(min=3)` on the return value.
- `"x"` is non-null so it passes `@NotNull`, but has length 1 so it fails `@Size(min=3)` → `returnErrors=1`.

The program does not use Spring MVC/AOP; it invokes Jakarta Validator directly to demonstrate metadata inheritance. The two validation mechanisms are kept distinct: `validate(bean)` for bean state; `forExecutables()` for method parameters/return values. Sorting with `sorted()` is only for stable stdout because `Set` does not guarantee order.

## 13. JUnit 5: Verifying Inheritance, Nested `@Valid`, and Executable Constraints

File `src/test/java/demo/InheritanceDemoTest.java`:

~~~java
package demo;

import java.lang.reflect.Method;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class InheritanceDemoTest {

    @Test
    void inheritsSuperclassAndInterfaceConstraints() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var errors = validator.validate(
                InheritanceDemo.invalidMember());

            assertEquals(5, errors.size());

            Set<String> paths = errors.stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());

            assertEquals(
                Set.of("id", "code", "email", "age", "address.city"),
                paths);
        }
    }

    @Test
    void getterConstraintSurvivesOverride() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var member = new InheritanceDemo.Member(
                "ID-7", "X",
                new InheritanceDemo.Address("Ha Noi"),
                "member@example.com", 20);

            var errors = validator.validate(member);

            assertEquals(1, errors.size());
            assertEquals("code",
                errors.iterator().next()
                    .getPropertyPath().toString());
        }
    }

    @Test
    void inheritedCascadeRequiresNonNullChild() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var member = new InheritanceDemo.Member(
                "ID-7", "C123", null,
                "member@example.com", 20);

            var errors = validator.validate(member);

            // @Valid does not create a new Address; base @NotNull reports error.
            assertEquals(1, errors.size());
            assertEquals("address",
                errors.iterator().next()
                    .getPropertyPath().toString());
        }
    }

    @Test
    void executableConstraintsAreInherited()
            throws NoSuchMethodException {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var impl = new InheritanceDemo.LookupServiceImpl();

            Method method = InheritanceDemo.LookupServiceImpl.class
                .getMethod("find", String.class);

            var executable = validator.forExecutables();

            var paramErrors = executable.validateParameters(
                impl, method, new Object[]{""});
            var returnErrors = executable.validateReturnValue(
                impl, method, "x");

            assertEquals(1, paramErrors.size());
            assertEquals(1, returnErrors.size());

            assertEquals("query required",
                paramErrors.iterator().next().getMessage());

            assertEquals("result too short",
                returnErrors.iterator().next().getMessage());
        }
    }

    @Test
    void validSubtypeHasNoBeanViolations() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            assertTrue(validator.validate(
                InheritanceDemo.validMember()).isEmpty());
        }
    }

    @Test
    void metadataExposesInheritedProperties() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var metadata = validator.getConstraintsForClass(
                InheritanceDemo.Member.class);

            assertNotNull(
                metadata.getConstraintsForProperty("id"));
            assertNotNull(
                metadata.getConstraintsForProperty("code"));
            assertNotNull(
                metadata.getConstraintsForProperty("email"));
        }
    }
}
~~~

Command:

~~~bash
mvn test
~~~

With the full sample project, **6 passing tests** are expected. The tests check path sets instead of relying on "the first error"; only tests expecting a single error use `iterator().next()`. Method validation tests call `ExecutableValidator` **explicitly**, avoiding assumptions about a running Spring proxy.

### Why Inspect Metadata?

`Validator.getConstraintsForClass(Member.class)` returns a `BeanDescriptor` containing constraint information across the inheritance hierarchy. `getConstraintsForProperty("email")` verifies that the constraint from the interface was not lost; similarly `id` from the superclass field and `code` from the superclass getter. This is useful when refactoring type hierarchies, because unit tests look beyond just the subclass's source code.

You can inspect annotation details via `PropertyDescriptor.getConstraintDescriptors()` to catch accidental contract changes. Do not manually scan Java reflection annotations on *every method declared on the subclass* and conclude there are no annotations; Bean Validation metadata draws from a broader source than Java's `getDeclaredAnnotations()` on a single member.

## 14. Combining Validation Groups with Inherited Constraints

Inherited constraints remain subject to **group** rules. By default, `Validator.validate(bean)` checks the `jakarta.validation.groups.Default` group along with applicable group inheritance/group sequences.

Example:

~~~java
interface UpdateChecks {}

class BaseCommand {
    @NotNull
    Long id;
}

class UpdateCommand extends BaseCommand {
    @NotBlank(groups = UpdateChecks.class)
    String changeReason;
}
~~~

This is an illustrative declaration. When calling `validator.validate(updateCommand)`, `@NotNull` in `Default` on the superclass is evaluated, whereas `@NotBlank(groups=UpdateChecks.class)` may not be evaluated since it does not belong to `Default`. When calling:

~~~java
validator.validate(
    updateCommand,
    jakarta.validation.groups.Default.class,
    UpdateChecks.class);
~~~

both groups are requested. Execution order is not guaranteed without `@GroupSequence`. With group-defining interfaces, Java interface inheritance can create **group inheritance**, which should be distinguished from **constraint declarations placed on Java interfaces**; these are related but distinct concepts.

### Group Conversion During Cascading

For a child object inherited via `@Valid`, Bean Validation also supports `@ConvertGroup` to switch groups along the cascade edge. For instance, a base type has `@Valid` on `Address`; the subtype inherits that relationship, so applicable cascade/group conversion rules can affect which constraints run on `Address`. When applying group conversion, place it where the cascade relationship is defined and test with actual groups.

Do not add `@Valid` or `@ConvertGroup` on an overridden getter just to "compensate" for not seeing annotations in the subclass. First inspect metadata and follow return-value cascade declaration rules in the hierarchy.

## 15. Enabling Method Validation in Spring Framework and Spring Boot

Jakarta Bean Validation is the API/specification; Spring provides integration points to invoke it at the right time. The common approach is Spring's `@Validated` combined with method-validation infrastructure.

In a Spring Boot 3 application (exact version aligned with BOM), the typical dependency is:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

This is a dependency **used inside a Spring Boot project with configured dependency management**, not standalone like the `pom.xml` in Section 12. With plain Spring Framework, configure a provider and `MethodValidationPostProcessor` when AOP method validation is desired.

Example service interface declaring a contract:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public interface CustomerService {
    @NotNull
    String lookup(
        @NotBlank String customerCode);
}
~~~

Implementation:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class CustomerServiceImpl implements CustomerService {

    @Override
    public String lookup(String customerCode) {
        return customerCode;
    }
}
~~~

These are **integration snippets**, not a standalone runnable Spring Boot application. When Spring method validation is active and calls go through the appropriate bean/proxy, parameter and return-value constraints **from the interface** can be enforced. Do not repeat `@NotBlank` on the overridden method parameter.

Notes:

- `@Validated` tells Spring to enable/scope method validation within the corresponding mechanism; it does not replace `@NotBlank` or `@NotNull`.
- With self-invocation `this.lookup(...)` inside the same instance, calls may **bypass the AOP proxy**; do not rely on method validation occurring when using proxy-based interception.
- JDK and class-based proxies have specific nuances regarding interfaces/method visibility. Test calls **through the Spring bean** in your actual configuration.
- Spring MVC 6.1+ has built-in method validation for controllers; errors directly on parameters/return values may appear as `HandlerMethodValidationException`. With `@Valid @RequestBody` validating an object, the error is typically `MethodArgumentNotValidException` when not capturing with `BindingResult`/`Errors` and no method-level validation takes over.
- Service AOP method validation typically throws `ConstraintViolationException`, or a Spring-adapted exception when configured optionally. Do not assume all Spring validation exceptions share the same type.
- If an interface method only puts `@Valid` on a parameter, method validation must still be executed to cascade; having `@Valid` in source code does not validate plain Java calls automatically.

### How to Test in a Spring Application

Write an integration test retrieving `CustomerService` from the Spring context and calling `lookup("")`. Assert the validation failure according to the configured mechanism, without assuming every project uses the same exception class. Also test `lookup("C123")` succeeding. Do not simply instantiate `new CustomerServiceImpl()` and call the method to conclude Spring method validation failed — that object is not a Spring-managed bean, so it usually has no interceptor/proxy.

## 16. Metadata API for Checking Inheritance and Investigating Errors

Beyond `validate(...)`, Bean Validation provides a metadata API to query constraints seen by the provider:

~~~java
BeanDescriptor descriptor =
    validator.getConstraintsForClass(Member.class);

PropertyDescriptor emailDescriptor =
    descriptor.getConstraintsForProperty("email");

boolean constrained =
    emailDescriptor != null
        && emailDescriptor.hasConstraints();
~~~

This is an **illustrative snippet** requiring imports for `jakarta.validation.metadata.BeanDescriptor`, `PropertyDescriptor`, and variables `validator` and `Member`. `Member` can be referenced in the sample project as `InheritanceDemo.Member`.

If a property has only `@Valid` cascading without direct constraints on the property value itself, `PropertyDescriptor.hasConstraints()` does not necessarily reflect the full cascade semantics. Metadata also reports whether the property `isCascaded()` along with `CascadableDescriptor`/container-element metadata. Therefore, do not use `hasConstraints()` alone to conclude "no validation exists" in all cases.

At the method level, use `BeanDescriptor.getConstraintsForMethod(name, parameterTypes...)` and `MethodDescriptor.getParameterDescriptors()`/`getReturnValueDescriptor()` to inspect the contract. Parameter constraints from interfaces and return constraints added in subtypes are aggregated in executable metadata. This is a great tool for catching contract-breaking refactors even before running HTTP requests.

### Visualizing Verification

~~~text
validator.getConstraintsForClass(Subtype.class)
             |
             +-- PropertyDescriptor("id")
             |      from superclass field
             |
             +-- PropertyDescriptor("code")
             |      from superclass getter
             |
             +-- PropertyDescriptor("email")
             |      from interface getter
             |
             +-- PropertyDescriptor("address")
             |      @Valid cascade / @NotNull
             |
             +-- MethodDescriptor("find", String.class)
                    parameter constraints from interface
                    return constraints from interface + implementation
~~~

Separating bean-property metadata from executable metadata is especially helpful to prevent confusion when source code uses multi-interface hierarchies and overrides.

## 17. Common Mistakes When Inheriting Constraints

| Design Mistake | Why Is It Wrong | How to Fix |
| --- | --- | --- |
| Repeating `@NotBlank` on getter override thinking interface constraint is lost | Interface constraints are already inherited during validation. | Keep contract source on the interface; verify via `Validator.validate`. |
| Placing constraints on superclass but checking only subclass annotations when debugging | Subclass source does not show all provider metadata. | Inspect the hierarchy and `getConstraintsForClass`. |
| Using Java reflection `getDeclaredAnnotations()` to list all Bean Validation constraints | Misses superclasses/interfaces and provider metadata. | Use the Bean Validation metadata API. |
| Declaring a field with the same name as a superclass field | Java field hiding is not overriding; metadata/binding easily diverges. | Avoid field hiding and standardize access strategy. |
| Putting the same constraint on both field and getter unnecessarily | Can produce duplicate violations or divergent results if getter transforms value. | Choose one clear constraint placement. |
| Adding `@NotBlank` on a method parameter in the implementation | Violates the rule against strengthening preconditions. | Declare on the interface/supertype where the method is defined. |
| Repeating identical parameter annotations in a subtype | Even with identical constraints, still violates portable override rules. | Do not repeat; the provider inherits them. |
| Adding `@Valid` on a parameter override | Also strengthens preconditions via new cascading. | Define parameter cascading on the root contract source. |
| Two independent interfaces declare the same method, one with a parameter constraint | Violates the parallel types rule. | Refactor the contract or split the method. |
| Putting `@Valid` on return value in both interface and overriding method | Forbids duplicate return cascading along one hierarchy line. | Place `@Valid` once in the appropriate place. |
| Thinking omitting annotations on return method override removes interface constraint | Inherited metadata still applies. | Design a new contract if different semantics are needed. |
| Using only `@Valid` expecting a null nested field to be rejected | Cascading skips null. | Add `@NotNull` if presence is required. |
| Using only `@NotNull` on child bean thinking child properties are checked | `@NotNull` does not cascade. | Combine with `@Valid` when deep validation is needed. |
| Calling a plain Java method without enabling executable validation | Method annotations do not run automatically. | Configure Spring AOP/method validation or call `ExecutableValidator`. |
| Testing only bean `validate(...)` and assuming method parameters are checked | Two separate API paths. | Test `forExecutables()` and Spring integration. |
| Relying on `ConstraintViolation` iteration order in a `Set` | `Set` does not guarantee order. | Sort by path/code when displaying or testing. |
| Catching all `ConstraintDeclarationException` and returning 400 as user error | Usually a metadata/server configuration bug, not bad client input. | Fix code/constraint hierarchy and monitor infrastructure errors. |
| Mixing `javax.validation.*` with `jakarta.validation.*` provider | Namespace mismatch between Spring 5/6 and Hibernate Validator. | Align dependencies and imports to the proper version. |
| Expecting `@Validated` on an interface to "create" bean constraints | `@Validated` is a Spring integration annotation, not a data constraint. | Distinguish activation from constraint declarations. |

## 18. Safe Implementation Checklist

1. Identify the validated object's class and all relevant superclasses/interfaces.
2. For **bean state**, audit field, getter, and class-level constraints across the whole hierarchy.
3. Choose a consistent field-level or getter-level strategy; avoid field hiding.
4. Identify where `@Valid` lives and whether `@NotNull` is needed for child objects.
5. For **method parameters**, place constraints on the root interface/supertype and do not repeat them in overrides.
6. Check methods implemented from **multiple parallel interfaces** before adding parameter constraints.
7. For **method return values**, postconditions may be added, but do not repeat `@Valid` cascading along the same hierarchy.
8. Identify groups: Default, custom groups, group sequences, and group conversions (if any).
9. Inspect Bean Validation metadata with `getConstraintsForClass(...)`, `getConstraintsForProperty(...)`, and method descriptors when needed.
10. Write separate tests for `Validator.validate(...)` and `ExecutableValidator` since they are not equivalent.
11. If using Spring, verify the provider/starter is present, `@Validated`/method-validation infrastructure is properly enabled, and calls go through the bean/proxy.
12. Check actual exception types at boundaries: data binding, method validation, and invalid metadata may differ.
13. Verify property paths of nested violations, handle unordered `Set`s, and do not return sensitive raw `invalidValue`s.
14. Review overridden methods after every interface refactor to avoid `ConstraintDeclarationException`.

### Self-Check Questions

1. An `@Email` getter is in an interface; the implementing class does not repeat the annotation. Does `Validator.validate(instance)` apply `@Email`?
2. A subclass overrides a `@Size` getter from its superclass without writing `@Size` on the override. Does the constraint still take effect?
3. Why does `@NotNull` on `BaseProfile.address` differ from `@Valid` on the same field?
4. An interface method has no parameter constraints; can the implementation add `@NotBlank` to the overridden parameter?
5. An interface already has `@NotBlank` on a parameter; is repeating that exact annotation in the implementation valid per the specification?
6. A class implements two independent interfaces declaring the same method; one interface has a parameter constraint. Is this a portable method-constraints structure?
7. Can a subtype add `@Size` on a method return value if the supertype already has `@NotNull`?
8. An interface already has `@Valid` on a return value; can the subclass place `@Valid` again on the overridden method?
9. Does calling `new ServiceImpl().find("")` directly trigger Bean Validation for the method parameter?
10. Why is `Validator.validate(bean)` insufficient to verify parameter constraints on a service method?
11. Which API helps inspect inherited constraints without reading only annotations declared directly on the subclass?

**Answers:** (1) Yes; (2) still takes effect; (3) `@NotNull` forbids a missing object, `@Valid` requests deep validation of a present object; (4) no under portable rules; (5) no; (6) no; (7) yes, that strengthens the postcondition; (8) no, repeating return cascading along the same line is forbidden; (9) no, activation is required; (10) bean validation and executable validation are distinct; (11) `Validator.getConstraintsForClass(...)` and the Bean Validation metadata API.

## 19. Official Documentation

- Jakarta Bean Validation 3.0 Specification — *Constraint declaration and validation process*, *Method constraints in inheritance hierarchies*, *Validation routine*: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Bean Validation 3.0 API — `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html
- Jakarta Bean Validation 3.0 API — `ExecutableValidator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/executable/ExecutableValidator.html
- Jakarta Bean Validation 3.0 API — `ConstraintDeclarationException`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintDeclarationException.html
- Hibernate Validator 8.0 Reference Guide — *Inheritance hierarchies*, *Method constraints*, *Cascaded validation*: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Hibernate Validator 8.0 releases and Maven coordinates: https://hibernate.org/validator/releases/8.0/
- Spring Framework — Java Bean Validation integration: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — MethodValidationPostProcessor Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html
