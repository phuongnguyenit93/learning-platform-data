# Configuring META-INF/validation.xml and XML Constraint Mapping

## 1. Goal and context

Jakarta Bean Validation typically declares constraints such as `@NotBlank`, `@Size`, and `@Min` directly in Java code. However, there are cases where you need to **declare or adjust rules without modifying the model**: domain classes coming from a library, DTOs reused across multiple applications, differing deployment policies, or validation rules configured separately by a module.

Jakarta Validation supports **two different kinds of XML**:

1. `META-INF/validation.xml`: configures how `ValidatorFactory` is initialized (provider, message interpolator, method validation choices, list of mapping files, provider properties, etc.).
2. **Constraint mapping XML**: describes exactly which constraints apply to classes, fields, getters, parameters, return values, or container elements; can replace or combine with Java annotations.

In a Spring Framework application, this XML configuration affects Jakarta Validation **when the application uses a `ValidatorFactory`/`Validator` initialized with the corresponding resources**; it is neither Spring bean XML configuration nor Jackson JSON data-binding configuration.

The content below focuses on **Jakarta Validation 3.0** and **Spring Framework 6 / Spring Boot 3**, using the `jakarta.validation.*` namespace, Java 17, and Hibernate Validator 8. For Spring 5/Boot 2, use the `javax.validation.*` namespace and older XML schemas; do not mix configurations from the two generations.

## 2. Loading lifecycle and relationship between the two files

Typical configuration flow:

```text
src/main/resources/META-INF/validation.xml
                  |
                  | <constraint-mapping>...
                  v
src/main/resources/META-INF/validation/customer-constraints.xml
                  |
                  | declares constraints for demo.Customer
                  v
Validation.buildDefaultValidatorFactory()
                  |
                  v
Validator.validate(customer) -> Set<ConstraintViolation<Customer>>
```

When the application runs, Maven/Gradle packages the contents of `src/main/resources` onto the **runtime classpath**. Jakarta Validation looks up `META-INF/validation.xml` when building `ValidatorFactory` (unless told to ignore it). Each `constraint-mapping` entry in the config file references a mapping file on the **classpath**; the mapping filename does not have to be `constraints.xml`, as long as the path points to a valid resource.

**Key distinctions:**

- `validation.xml` is the **mandatory conventional name and location** for automatic default configuration discovery.
- `customer-constraints.xml` is a **custom name**, declared inside `validation.xml` (or registered via API).
- One mapping file can describe multiple beans; one `validation.xml` can register multiple mapping files.
- Simply creating a mapping file **does not make the provider auto-scan all XMLs**. You must register it via `constraint-mapping`, `Configuration.addMapping(InputStream)`, or an equivalent integration mechanism.
- If **more than one** `META-INF/validation.xml` resource exists on the runtime classpath, Jakarta Validation requires throwing `ValidationException` when building the factory.

## 3. Sample Maven project structure

The complete example will use the following files:

```text
validation-xml-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── Customer.java
        │       └── ValidationXmlDemo.java
        └── resources/
            └── META-INF/
                ├── validation.xml
                └── validation/
                    └── customer-constraints.xml
```

When packaging, verify that the resources are actually on the classpath, for example that `target/classes/META-INF/validation.xml` and `target/classes/META-INF/validation/customer-constraints.xml` appear after `mvn compile`.

Do not place `validation.xml` under `src/main/java` expecting the provider to discover it automatically. Likewise, do not write an OS filesystem path like `C:\project\...` inside `constraint-mapping`: it is a **classpath resource name**.

## 4. Global configuration: `META-INF/validation.xml`

Create `src/main/resources/META-INF/validation.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<validation-config
    xmlns="https://jakarta.ee/xml/ns/validation/configuration"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/validation/configuration
        https://jakarta.ee/xml/ns/validation/validation-configuration-3.0.xsd"
    version="3.0">

    <constraint-mapping>
        META-INF/validation/customer-constraints.xml
    </constraint-mapping>

</validation-config>
```

**Key meanings:**

- `validation-config`: root of the configuration document, with its own namespace for **configuration** (distinct from mapping).
- `version="3.0"`: schema of Jakarta Validation 3.0.
- `xsi:schemaLocation`: binds the namespace to the matching XSD schema; the file must follow the exact XSD structure and element ordering.
- `constraint-mapping`: path to the XML declaring constraints to load. Leading/trailing whitespace in element text is normally trimmed when reading the resource name; to make path inspection straightforward, you can write it on **one line**: `<constraint-mapping>META-INF/validation/customer-constraints.xml</constraint-mapping>`.

To eliminate any differences in whitespace handling across implementations, production configuration should prefer the **single-line** form. The examples below use this standard path.

### Notable configuration elements

| Element in `validation.xml` | Purpose |
| --- | --- |
| `<default-provider>` | Selects a specific `ValidationProvider` class, e.g. `org.hibernate.validator.HibernateValidator`; usually unnecessary if only one compatible provider is on the classpath |
| `<message-interpolator>` | `MessageInterpolator` class to turn message templates into error messages |
| `<traversable-resolver>` | Decides whether a property is reachable/cascadable for validation |
| `<constraint-validator-factory>` | Mechanism for instantiating `ConstraintValidator`s |
| `<parameter-name-provider>` | Resolves method/constructor parameter names |
| `<clock-provider>` | Supplies `java.time.Clock` for `@Past`/`@Future` |
| `<value-extractor>` | Registers `ValueExtractor`s for containers |
| `<executable-validation>` | Configures executable validation types per standard configuration |
| `<constraint-mapping>` | Registers an XML mapping file |
| `<property name="...">` | Additional property, typically provider-specific |

Elements are **optional** but **their order must match the schema**. For example, Hibernate Validator allows:

```xml
<property name="hibernate.validator.fail_fast">true</property>
```

When fail-fast mode is enabled, the provider may stop after the first violation, making the returned error count differ from the demo below. Thus, the demo uses the default configuration (fail-fast disabled). `hibernate.validator.*` properties are **Hibernate Validator-specific extensions**, not supported by all providers.

### Configuration precedence

If an element in `validation.xml` and the `Configuration` API configure the same behavior, **the value set explicitly via the programmatic API takes precedence** per Jakarta Validation (for example, `configuration.messageInterpolator(...)` overrides the XML setting). This differs from the rules combining annotations and XML mappings, explained in the next section.

## 5. Constraint mapping XML: declaring rules on a model

Create `src/main/resources/META-INF/validation/customer-constraints.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<constraint-mappings
    xmlns="https://jakarta.ee/xml/ns/validation/mapping"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/validation/mapping
        https://jakarta.ee/xml/ns/validation/validation-mapping-3.0.xsd"
    version="3.0">

    <bean class="demo.Customer" ignore-annotations="false">

        <field name="code">
            <constraint annotation="jakarta.validation.constraints.NotBlank">
                <message>Code is required</message>
            </constraint>
            <constraint annotation="jakarta.validation.constraints.Size">
                <message>Code must be 3-8 chars</message>
                <element name="min">3</element>
                <element name="max">8</element>
            </constraint>
        </field>

        <field name="age">
            <constraint annotation="jakarta.validation.constraints.Min">
                <message>Age must be at least 18</message>
                <element name="value">18</element>
            </constraint>
        </field>

    </bean>
</constraint-mappings>
```

**Explanation:**

- `constraint-mappings`: root in the Jakarta Validation 3.0 **mapping** namespace.
- `bean class="demo.Customer"`: maps to the fully qualified Java class `demo.Customer`; if omitting the package, you can place `<default-package>demo</default-package>` right before the `bean` list.
- `ignore-annotations="false"`: **preserves** Java constraint annotations on the bean while adding the constraints declared in XML.
- `field name="code"`, `field name="age"`: targets **fields** directly on the class, not DB column names; names must exist accurately in the model.
- `constraint annotation="..."`: fully qualified name of an existing **constraint annotation** on the classpath, such as `@NotBlank`, `@Size`, and `@Min`.
- `message`: overrides the constraint's default message.
- `element name="min"`/`element name="max"`/`element name="value"`: sets values for annotation attributes of the same names. Types and content must match the annotation declaration.

For example, `@Size(min = 3, max = 8)` in Java corresponds to the XML fragment:

```xml
<constraint annotation="jakarta.validation.constraints.Size">
    <element name="min">3</element>
    <element name="max">8</element>
</constraint>
```

This snippet is only a **fragment** that must sit inside `<field>`/`<getter>`/an appropriate mapping element; it is not a standalone XML file.

**Important warning:** if you omit `ignore-annotations="false"` in the sample above, the default value of `ignore-annotations` on `bean` is **`true`**. In that case, Java annotations on `demo.Customer` can be ignored. This is a major difference from expecting “XML automatically only appends to annotations”.

## 6. Java 17 experiment: how do XML and annotations combine?

### 6.1. Maven dependencies

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
             http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>validation-xml-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.5.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
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
                    <mainClass>demo.ValidationXmlDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

The `hibernate-validator` dependency provides the Jakarta Validation provider; `expressly` provides the Jakarta Expression Language (EL) implementation for default message interpolation.

### 6.2. Model with an annotation on one field

Create `src/main/java/demo/Customer.java`:

```java
package demo;

import jakarta.validation.constraints.NotBlank;

public final class Customer {
    @NotBlank(message = "Name is required")
    private final String name;

    // These two fields have no Java constraints;
    // they will be constrained via XML mapping.
    private final String code;
    private final int age;

    public Customer(String name, String code, int age) {
        this.name = name;
        this.code = code;
        this.age = age;
    }
}
```

`name` is constrained by **annotation**; `code` and `age` are constrained by **XML mapping**. Hibernate Validator can read private fields via reflection under field-level validation, so the example needs no getters.

### 6.3. Building the factory and comparing when XML is ignored

Create `src/main/java/demo/ValidationXmlDemo.java`:

```java
package demo;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import java.util.List;

public final class ValidationXmlDemo {
    private static List<String> errors(Validator validator, Customer bean) {
        return validator.validate(bean).stream()
                .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                .sorted()
                .toList();
    }

    public static void main(String[] args) {
        Customer invalid = new Customer("", "ab", 17);
        Customer valid = new Customer("Lan", "code123", 25);

        // Automatically reads META-INF/validation.xml from the runtime classpath.
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            System.out.println("XML + Java invalid: "
                    + errors(validator, invalid));
            System.out.println("XML + Java valid: "
                    + errors(validator, valid));
        }

        // Create a second factory, intentionally ignoring validation.xml
        // and the mappings registered through this file.
        try (ValidatorFactory factory =
                     Validation.byDefaultProvider()
                             .configure()
                             .ignoreXmlConfiguration()
                             .buildValidatorFactory()) {
            System.out.println("Ignore XML invalid: "
                    + errors(factory.getValidator(), invalid));
        }
    }
}
```

Run with **JDK 17+** and Maven in the directory containing `pom.xml`:

```bash
mvn -q clean compile exec:java
```

**Stdout lines printed by the program** (excluding Maven or provider logs):

```text
XML + Java invalid: [age: Age must be at least 18, code: Code must be 3-8 chars, name: Name is required]
XML + Java valid: []
Ignore XML invalid: [name: Name is required]
```

Because the Java code calls `sorted()`, field ordering in the output is stable. Element order in `Set<ConstraintViolation<?>>` is **not guaranteed**, so do not write tests relying on unsorted order.

Comparison:

| Mode | `name` | `code` | `age` |
| --- | --- | --- | --- |
| XML + annotations, `ignore-annotations="false"` | `@NotBlank` from Java | `@NotBlank` and `@Size` from XML | `@Min` from XML |
| Skipping `validation.xml` via `ignoreXmlConfiguration()` | `@NotBlank` from Java | No constraints in demo | No constraints in demo |

When `invalid = ("", "ab", 17)`, `name` fails because it is blank, `code` fails because length 2 is less than 3, and `age` fails because 17 is less than 18. For `valid = ("Lan", "code123", 25)`, all three fields pass. When XML configuration is ignored, only the `@NotBlank` placed directly in Java remains, so only the `name` error appears.

`ignoreXmlConfiguration()` applies to **the factory being built**. It does not delete `validation.xml` from the JAR, does not disable Jakarta Validation annotations in Java, and does not prevent another application from explicitly registering XML mappings via `addMapping(...)`.

## 7. When does XML supplement vs replace annotations?

Handling depends on the `ignore-annotations` attribute:

| Declaration on bean | Behavior for annotations on the mapped bean |
| --- | --- |
| `<bean class="demo.Customer">` | Defaults to `ignore-annotations="true"`: ignores constraint annotations on that bean |
| `<bean class="demo.Customer" ignore-annotations="true">` | Explicitly requests XML declarations to replace annotations in the corresponding scope |
| `<bean class="demo.Customer" ignore-annotations="false">` | Keeps Java annotations **and** adds XML constraints |

Finer control is available on `class`, `field`, `getter`, `method`, `constructor`, `parameter`, and `return-value`. If a child node does not declare `ignore-annotations`, it inherits the setting from its enclosing node per specification rules.

The following **fragment** illustrates ignoring annotations only on field `name`, while keeping other annotations on the bean active:

```xml
<bean class="demo.Customer" ignore-annotations="false">
    <field name="name" ignore-annotations="true">
        <constraint annotation="jakarta.validation.constraints.NotBlank">
            <message>Name is mandatory by XML policy</message>
        </constraint>
    </field>
</bean>
```

This is an **illustrative alternative configuration**, not to be appended to the complete mapping file in section 5, because `demo.Customer` should not be declared twice in the same XML mapping set.

**Important point:** the `ignore-annotations` flag applies to the corresponding bean/element. It does not change the configuration of other beans in the application and does not automatically suppress constraints inherited from superclasses. If both annotation and XML declare equivalent constraints for the same property when `ignore-annotations="false"`, **duplicate violations** can appear; decide clearly whether to supplement or replace.

## 8. Advanced mapping constructs

Beyond `field`, mappings also support these constructs:

| XML construct | Use case |
| --- | --- |
| `<class>` | Class-level constraints; can describe `group-sequence` |
| `<getter name="property">` | Constraints on getter/property instead of direct field |
| `<valid/>` | Enables cascaded validation equivalent to `@Valid` |
| `<container-element-type>` | Constraints on elements of `List`, `Map`, `Optional`... |
| `<method>` / `<constructor>` | Constraints on parameters, return values, cross-parameter |
| `<groups>` | Assigns constraint to one or more validation groups |
| `<convert-group from="..." to="..."/>` | Converts groups during cascaded validation |
| `<constraint-definition>` | Replaces or supplements `ConstraintValidator` list for an **existing constraint annotation** |

### 8.1. Container element constraints

Another example: suppose class `demo.TagRequest` has field `List<String> tags`. An XML fragment inside `<bean class="demo.TagRequest">` can be written as:

```xml
<field name="tags">
    <container-element-type type-argument-index="0">
        <constraint annotation="jakarta.validation.constraints.NotBlank">
            <message>Tag must not be blank</message>
        </constraint>
    </container-element-type>
</field>
```

For `List<String>`, the type argument only has index 0. For `Map<K,V>`, key is typically index 0 and value is index 1. Do not confuse `<valid/>` (cascading into a child object) with constraints on the collection element value itself; each has a distinct meaning.

### 8.2. Method validation

For a method `void register(String email)`, a fragment inside the `bean` declaring that method can describe:

```xml
<method name="register">
    <parameter type="java.lang.String">
        <constraint annotation="jakarta.validation.constraints.NotBlank">
            <message>Email is required</message>
        </constraint>
    </parameter>
</method>
```

This is only a **metadata declaration**; method calls are not intercepted automatically unless a method-validation trigger mechanism is active. With the Jakarta Validation API, you can call `Validator.forExecutables()`; in Spring, use the method-validation mechanism suited to your Spring version and call site. Overloaded methods must be described with their exact parameter list and types.

### 8.3. `constraint-definition` does not create a new annotation

Example illustrating **replacing validators** for an annotation already defined in code:

```xml
<constraint-definition annotation="demo.ValidCode">
    <validated-by include-existing-validators="false">
        <value>demo.ValidCodeValidator</value>
    </validated-by>
</constraint-definition>
```

Both `demo.ValidCode` and `demo.ValidCodeValidator` must be real classes with valid contracts. `include-existing-validators="false"` replaces the validator list from the annotation; `true` appends XML validators to existing ones. You cannot invent a brand-new annotation type solely in XML. You also cannot redefine the same constraint annotation multiple times within a factory's mapping set.

## 9. Applying in Spring Framework / Spring Boot

In Spring Boot 3 with `spring-boot-starter-validation`, Boot typically creates a `LocalValidatorFactoryBean` as the Jakarta Validation validator. When the provider initializes via default mechanisms and the XML sits on the classpath, `META-INF/validation.xml` and its referenced mappings are picked up. A DTO used in a controller can be a class with no Java constraint annotations yet still receive constraints from XML if the mapping targets the exact class and fields.

Illustrative snippet in an application with Spring Web:

```java
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {
    @PostMapping("/customers")
    String create(@Valid @RequestBody CustomerRequest request) {
        return "accepted";
    }
}
```

Here `CustomerRequest` represents a DTO class in the Spring application and **is not a file in the standalone Maven demo**. To validate its fields via XML, declare `<bean class="...CustomerRequest">` with exact class and property names, and ensure Spring MVC uses the factory that loaded the mapping. With `@Valid @RequestBody`, a failed constraint normally results in HTTP 400 under default validation handling; the response format depends on the application's exception handler.

### Registering mappings via `LocalValidatorFactoryBean`

Spring also lets you load mappings programmatically when you prefer not to declare `<constraint-mapping>` inside `validation.xml`. Example of an **alternative configuration option**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
class ExplicitMappingConfig {
    @Bean
    LocalValidatorFactoryBean validator() {
        LocalValidatorFactoryBean factory =
                new LocalValidatorFactoryBean();
        factory.setMappingLocations(
                new ClassPathResource(
                    "META-INF/validation/customer-constraints.xml"
                )
        );
        return factory;
    }
}
```

**Do not declare the same mapping simultaneously** via `<constraint-mapping>` in `validation.xml` **and** `setMappingLocations(...)` on the same validator factory: it can register a bean/constraint twice and throw `ValidationException`. If you already use `validation.xml` to register mappings as in the demo, you do not need the Spring config above. If you choose `setMappingLocations`, remove the duplicate entry in `validation.xml` or remove the configuration file if no other settings are needed.

When an application has multiple `Validator` / `ValidatorFactory` beans or customizes `WebMvcConfigurer#getValidator()`, verify that the exact instance executing validation has the mapping loaded. The `@Valid` annotation only **triggers validation**; it does not decide which XML sources are loaded.

### How does XML mapping differ from Spring DataBinder?

- `@Valid` and `Validator` apply **Bean Validation rules** to an already populated object.
- `WebDataBinder`, Jackson, and converters handle **data binding/type conversion**; XML constraints do not alter JSON parsing, conversion services, or binding errors.
- `LocalValidatorFactoryBean` is the bridge from Spring Validation to the Jakarta Validation provider. XML takes effect when it is loaded into that factory/provider.

## 10. Testing and troubleshooting

### Verifying resources are packaged

After `mvn compile`, check:

```text
target/classes/META-INF/validation.xml
target/classes/META-INF/validation/customer-constraints.xml
```

You can use Java to check that the classloader finds the resources:

```java
var loader = Thread.currentThread().getContextClassLoader();
System.out.println(loader.getResource("META-INF/validation.xml"));
System.out.println(
    loader.getResource("META-INF/validation/customer-constraints.xml")
);
```

This is an **illustrative debugging snippet** placed inside a Java method, not a standalone program. If the output is `null`, check the actual path in the build output, resource filtering configuration, and runtime classpath.

### Inspecting constraint metadata

Besides `validate()`, you can query:

```java
var codeDescriptor = factory.getValidator()
        .getConstraintsForClass(Customer.class)
        .getConstraintsForProperty("code");

System.out.println(codeDescriptor != null);
```

This runs in a scope that has `factory` and `Customer`; once the mapping is loaded, `codeDescriptor` exists. If the mapping is missing and the field has no annotations, the result can be `null`. Querying metadata verifies that **constraints are actually registered**, without depending solely on error messages.

### Common errors

| Symptom | Possible cause | Check/fix |
| --- | --- | --- |
| XML constraints do not run | `validation.xml` in wrong location or missing `constraint-mapping` | Check resources on runtime classpath and filenames |
| `ValidationException` at startup | Wrong namespace/XSD/version, invalid XML schema | Use `https://jakarta.ee/xml/ns/validation/...` namespaces and matching version |
| Java annotations suddenly stop working | Default `ignore-annotations="true"` on `bean` | Set `false` if combining |
| Same error appears multiple times | Both annotation and XML constrain it, or duplicate field/getter declaration | Inspect metadata, choose one source per rule |
| Provider reports bean mapped twice | Class declared in multiple mapping files or file registered twice | Map each class once within a factory's XML set |
| Class/field not found | Wrong fully qualified class/field/getter name | Match class/package and member names in bytecode |
| `jakarta.validation.*` annotations ignored | Legacy `javax.validation` library mixed onto Jakarta stack | Align Spring, provider, API, and XML schemas to the same generation |
| Missing errors after setting `fail_fast=true` | Provider stops after first violation | Disable fail-fast when collecting all errors |
| Mapping present but controller still accepts invalid data | Controller does not trigger validation or uses another validator | Check `@Valid`/`@Validated`, validator bean, and MVC config |
| Tests only assert message text | Messages can vary by locale/resource bundle | Assert property path, annotation type, groups, violation count where appropriate |

### Specification rules to remember

1. XML descriptors must validate against their XSDs; invalid configuration can raise `ValidationException` when building the factory, before `validate()` is ever called.
2. Each bean class should be described **only once** across a validator factory's constraint mappings; each constraint annotation definition can likewise be redefined only once.
3. When using `<getter>`, property/method names and types must follow JavaBean/provider rules; avoid accidentally applying the same constraint on both field and getter.
4. XML allows setting annotation element values, but elements and value types must exist and match the actual annotation. For example, `@Min.value` is `long`, `@Size.min` is `int`.
5. XML can describe `@Valid` (cascading), groups, group conversions, and method validation, but triggering checks at call sites is still coordinated by the application / framework.
6. Do not rely on default messages for stable snapshot tests; use explicit messages or assert against metadata/violation codes.
7. Programmatic factory configuration can override XML on overlapping settings; if an application builds multiple factories, they may apply different configurations.

## 11. Implementation checklist

- [ ] All dependencies and imports belong to the same Jakarta Validation / Spring generation.
- [ ] Only one `META-INF/validation.xml` is visible on the runtime classpath.
- [ ] `validation.xml` uses the **configuration** namespace and schema version.
- [ ] Constraint mappings use the **mapping** namespace, schema version, and classpath location.
- [ ] Each class is mapped once, with accurate field/getter/method names.
- [ ] Intentional `ignore-annotations` choice: `false` to supplement, `true` to replace annotations in that scope.
- [ ] XML declares valid constraint annotation types/names and `element` attributes.
- [ ] Same mapping is not registered through multiple paths on the same validator factory.
- [ ] Tests cover valid data, invalid data, annotations + XML, and ignoring XML.
- [ ] For Spring MVC/services, verify the actual validator invoked and expected HTTP/error handling.

**Key takeaway:** `META-INF/validation.xml` decides **how configuration and mappings are loaded**; constraint mapping XML decides **which rules apply to a bean**. The `ignore-annotations` flag decides **whether to merge with or replace Java annotations**. Getting those three layers clear makes XML configuration transparent and testable.

## References

- [Jakarta Bean Validation 3.0 specification — XML configuration and XML deployment descriptor](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Hibernate Validator 8 Reference Guide — Configuring via XML](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-xml-configuration)
- [Jakarta Validation Configuration API — ignoreXmlConfiguration()](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Configuration.html)
- [Spring Framework — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
