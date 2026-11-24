# Keep business logic in dedicated components instead of configuration classes

**Topic:** Spring Boot Auto Configuration  
**Knowledge area:** Design and maintenance  
**Goal:** Design auto-configuration to be solely responsible for registering and wiring beans; place business rules in dedicated services/policies. This article builds an invoice pricing example with tax, explaining constructor injection, `@ConditionalOnMissingBean`, module organization, and how to test logic independently of Spring as well as ApplicationContext wiring behavior.

## 1. Responsibility boundary: configuration builds objects, services execute business logic

An auto-configuration class answers questions about **how the application is assembled**:

- Which beans are registered?
- When are beans registered?
- Which beans does a bean depend on?
- How can the application replace the default implementation?
- Which properties must be bound to configure the bean?

A business service answers questions about **product behavior**:

- What conditions must a valid invoice satisfy?
- How are subtotal, tax, and total calculated?
- How are invalid quantities or unit prices handled?
- What are the rounding policies and pricing rules?

Do not place calculations, business validations, API calls, data queries, or workflow orchestration inside `@Bean` methods or the body of `@Configuration` classes.

Configuration example to avoid:

```java
@Configuration
class InvoiceConfiguration {

    @Bean
    InvoicePricingService invoicePricingService(InvoiceRepository repository) {
        // Avoid: querying data, calculating tax, applying discounts,
        // and executing all business logic inside the factory method.
        List<Invoice> invoices = repository.findPending();
        BigDecimal total = invoices.stream()
                .map(Invoice::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new InvoicePricingService(total);
    }
}
```

This factory method registers a bean, accesses a repository, and executes business logic all at once. It is hard to test in isolation, can cause side effects during context startup, and bloats the configuration class with every new requirement.

Better design:

```java
@AutoConfiguration
class InvoiceAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(InvoicePricingService.class)
    InvoicePricingService invoicePricingService(TaxPolicy taxPolicy) {
        return new DefaultInvoicePricingService(taxPolicy);
    }
}
```

The `@Bean` method only wires dependencies and creates the implementation. `DefaultInvoicePricingService` is responsible for calculations, data validation, and enforcing business rules.

**Principle:** configuration is Spring's composition root; services/policies are where behavior lives. A business service can be a Spring bean, without placing its logic inside the configuration class.

## 2. Why separate business logic from configuration?

### 2.1. Isolated testing

A plain Java class can be tested with JUnit without starting Spring, creating an ApplicationContext, or mocking a container. Tests focus on inputs, outputs, and business edge cases.

If logic lives inside a `@Bean` method, tests often have to spin up configuration just to invoke a simple calculation. That slows tests down and couples business rules tightly to the framework.

### 2.2. Reusability

A dedicated service can be called from:

- REST controllers.
- Message listeners.
- Scheduled jobs.
- Command-line runners.
- Batch processors.
- Other business services.
- Tests or non-Spring Java programs.

If logic exists only inside a configuration class, callers easily end up invoking factory methods, instantiating objects manually, or duplicating logic.

### 2.3. Implementation replacement

An interface lets the application swap the default service for a custom implementation. For example, the library provides `DefaultInvoicePricingService`, while the application can supply a country-specific tax policy.

Spring Boot supports this pattern with `@ConditionalOnMissingBean`: auto-configuration creates the default bean only when the application has not provided one.

### 2.4. Safe and predictable startup

Configuration classes are processed during ApplicationContext initialization. If a factory method performs network calls, reads large files, queries databases, or runs batch work, startup time grows and infrastructure errors can prevent the context from starting.

Bean creation should primarily construct objects and wire dependencies. Business work should happen when a corresponding request or trigger arrives, following a clearly designed lifecycle.

### 2.5. Maintainability

When rules change, developers look in business services rather than tracing through configuration methods. When bean registration changes, configuration can be updated without rewriting calculations or business rules.

## 3. Running example: invoice pricing service

We build a Spring Boot auto-configuration module for invoice pricing.

Example rules:

1. An invoice must contain at least one line item.
2. Unit price must not be negative.
3. Quantity must be greater than 0.
4. Subtotal is the sum of `unitPrice × quantity`.
5. Tax equals `subtotal × taxRate`.
6. Money is rounded to two decimal places using `HALF_UP`.
7. Total equals subtotal plus tax.

Suppose an invoice has:

| Line item | Unit price | Quantity | Line total |
| --- | ---: | ---: | ---: |
| Book | 10.00 | 2 | 20.00 |
| Pen | 5.00 | 1 | 5.00 |
| **Subtotal** | | | **25.00** |
| Tax 10% | | | **2.50** |
| **Total** | | | **27.50** |

Calculations and validation belong to the business service. The tax rate is provided through a policy. Auto-configuration only registers the default policy and default service when the feature is enabled and the application has not supplied a replacement implementation.

## 4. Organize packages by responsibility

A clean structure for an auto-configuration module:

```text
invoice-pricing-autoconfigure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/invoice/
    │   │   ├── api/
    │   │   │   ├── Invoice.java
    │   │   │   ├── InvoiceLine.java
    │   │   │   ├── InvoiceTotal.java
    │   │   │   └── InvoicePricingService.java
    │   │   ├── domain/
    │   │   │   ├── TaxPolicy.java
    │   │   │   ├── ConfiguredTaxPolicy.java
    │   │   │   └── DefaultInvoicePricingService.java
    │   │   ├── config/
    │   │   │   └── InvoicePricingProperties.java
    │   │   └── autoconfigure/
    │   │       └── InvoicePricingAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/acme/invoice/
        └── InvoicePricingTests.java
```

Meaning:

| Package | Responsibility |
| --- | --- |
| `api` | Input/output models and interfaces used by consumers |
| `domain` | Pricing rules and business policies |
| `config` | Bind properties into structured data types |
| `autoconfigure` | Conditions and bean wiring for Spring Boot |

Not every project requires four packages. What matters is splitting by reason to change: business rules change in services; deployment configuration changes in properties; how Spring registers beans changes in auto-configuration.

## 5. Build Spring-independent API and models

Business models do not need to import Spring annotations.

### 5.1. `InvoiceLine.java`

```java
package com.acme.invoice.api;

import java.math.BigDecimal;

public record InvoiceLine(
        String description,
        BigDecimal unitPrice,
        int quantity
) {
}
```

`InvoiceLine` describes one line item. Value validation is placed in the service to clearly illustrate business rules and make testing straightforward.

### 5.2. `Invoice.java`

```java
package com.acme.invoice.api;

import java.util.List;

public record Invoice(List<InvoiceLine> lines) {

    public Invoice {
        lines = lines == null ? List.of() : List.copyOf(lines);
    }
}
```

The record creates an immutable snapshot of the list. `List.copyOf` also rejects `null` elements; the service remains responsible for validating empty invoices and line-item fields.

### 5.3. `InvoiceTotal.java`

```java
package com.acme.invoice.api;

import java.math.BigDecimal;

public record InvoiceTotal(
        BigDecimal subtotal,
        BigDecimal tax,
        BigDecimal total
) {
}
```

The result separates subtotal, tax, and total so callers can display invoices, persist values, or assert each part in tests.

### 5.4. `InvoicePricingService.java`

```java
package com.acme.invoice.api;

public interface InvoicePricingService {

    InvoiceTotal calculate(Invoice invoice);
}
```

Consumers depend on the interface. They do not need to know which class is the default implementation, where the tax policy is created, or how Spring registers beans.

## 6. Put tax policy in a dedicated component

### 6.1. `TaxPolicy.java`

```java
package com.acme.invoice.domain;

import java.math.BigDecimal;

public interface TaxPolicy {

    BigDecimal rate();
}
```

`TaxPolicy` represents the source providing the tax rate. It can be replaced by a policy per region, customer, or item type without modifying the pricing service.

### 6.2. `ConfiguredTaxPolicy.java`

```java
package com.acme.invoice.domain;

import java.math.BigDecimal;
import java.util.Objects;

public final class ConfiguredTaxPolicy implements TaxPolicy {

    private final BigDecimal rate;

    public ConfiguredTaxPolicy(BigDecimal rate) {
        this.rate = Objects.requireNonNull(rate, "rate must not be null");

        if (rate.compareTo(BigDecimal.ZERO) < 0
                || rate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    "tax rate must be between 0 and 1"
            );
        }
    }

    @Override
    public BigDecimal rate() {
        return this.rate;
    }
}
```

This implementation reads the tax rate from configuration. It is a dedicated Java object for the policy; it knows nothing about `Environment`, `@Value`, or ApplicationContext.

If business requirements later need country-based tax, a `RegionalTaxPolicy` or separate policy resolver can be introduced. `DefaultInvoicePricingService` still depends on the `TaxPolicy` abstraction.

## 7. Put all pricing rules in `DefaultInvoicePricingService`

File `DefaultInvoicePricingService.java`:

```java
package com.acme.invoice.domain;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

import com.acme.invoice.api.Invoice;
import com.acme.invoice.api.InvoiceLine;
import com.acme.invoice.api.InvoicePricingService;
import com.acme.invoice.api.InvoiceTotal;

public final class DefaultInvoicePricingService
        implements InvoicePricingService {

    private static final BigDecimal ZERO = BigDecimal.ZERO;
    private static final BigDecimal ONE = BigDecimal.ONE;
    private static final int MONEY_SCALE = 2;

    private final TaxPolicy taxPolicy;

    public DefaultInvoicePricingService(TaxPolicy taxPolicy) {
        this.taxPolicy = Objects.requireNonNull(
                taxPolicy,
                "taxPolicy must not be null"
        );
    }

    @Override
    public InvoiceTotal calculate(Invoice invoice) {
        if (invoice == null) {
            throw new IllegalArgumentException("invoice must not be null");
        }

        if (invoice.lines().isEmpty()) {
            throw new IllegalArgumentException(
                    "invoice must contain at least one line"
            );
        }

        BigDecimal subtotal = ZERO;

        for (InvoiceLine line : invoice.lines()) {
            if (line.unitPrice() == null
                    || line.unitPrice().compareTo(ZERO) < 0) {
                throw new IllegalArgumentException(
                        "unit price must not be null or negative"
                );
            }

            if (line.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be greater than zero"
                );
            }

            BigDecimal lineTotal = line.unitPrice()
                    .multiply(BigDecimal.valueOf(line.quantity()));

            subtotal = subtotal.add(lineTotal);
        }

        BigDecimal rate = this.taxPolicy.rate();

        if (rate == null
                || rate.compareTo(ZERO) < 0
                || rate.compareTo(ONE) > 0) {
            throw new IllegalStateException(
                    "tax policy must return a rate between 0 and 1"
            );
        }

        subtotal = subtotal.setScale(
                MONEY_SCALE,
                RoundingMode.HALF_UP
        );

        BigDecimal tax = subtotal.multiply(rate).setScale(
                MONEY_SCALE,
                RoundingMode.HALF_UP
        );

        BigDecimal total = subtotal.add(tax).setScale(
                MONEY_SCALE,
                RoundingMode.HALF_UP
        );

        return new InvoiceTotal(subtotal, tax, total);
    }
}
```

This class contains the business decisions:

- Which invoices are accepted.
- What constitutes valid unit prices and quantities.
- How line totals and subtotals are computed.
- What constraints the tax rate must satisfy.
- When and how monetary amounts are rounded.

There are no Spring annotations in this class. The service can be instantiated with `new DefaultInvoicePricingService(...)` in unit tests or managed by Spring as a bean.

Having no Spring dependency makes business logic easy to reuse and free from container lifecycle coupling.

### 7.1. Why use `BigDecimal` instead of `double`?

Monetary values require exact decimal representation. `double` uses binary floating-point, so calculations like `0.1 + 0.2` are not guaranteed to represent the exact expected decimal value.

Use `BigDecimal` with a String constructor:

```java
new BigDecimal("10.00")
```

Avoid constructing monetary amounts with:

```java
new BigDecimal(10.00)
```

because the binary representation of `double` may already carry precision errors before conversion to `BigDecimal`.

The example rounds subtotal and tax to two decimal places with `HALF_UP`. Real financial systems must explicitly specify currency scale, per-line vs. total rounding rules, tax-inclusive vs. tax-exclusive pricing, and discount handling. Those rules belong in domain services/policies, not auto-configuration.

## 8. Bind configuration into a typed object

File `InvoicePricingProperties.java`:

```java
package com.acme.invoice.config;

import java.math.BigDecimal;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.invoice")
public record InvoicePricingProperties(BigDecimal taxRate) {

    public InvoicePricingProperties {
        taxRate = taxRate == null
                ? new BigDecimal("0.10")
                : taxRate;

        if (taxRate.compareTo(BigDecimal.ZERO) < 0
                || taxRate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    "acme.invoice.tax-rate must be between 0 and 1"
            );
        }
    }
}
```

Corresponding properties:

```yaml
acme:
  invoice:
    enabled: true
    tax-rate: 0.10
```

`enabled` controls whether the auto-configuration is active. `tax-rate` is bound as a `BigDecimal` in `InvoicePricingProperties`.

The properties class is an adapter between external configuration and internal types. It can perform basic configuration validity checks, but should not contain invoice calculation flows or discount application logic.

Validating the tax rate in both properties and `ConfiguredTaxPolicy` protects different construction paths: properties protect Spring configuration; the policy protects the object itself when instantiated directly or used outside Spring.

## 9. Auto-configuration handles wiring only

File `InvoicePricingAutoConfiguration.java`:

```java
package com.acme.invoice.autoconfigure;

import com.acme.invoice.api.InvoicePricingService;
import com.acme.invoice.config.InvoicePricingProperties;
import com.acme.invoice.domain.ConfiguredTaxPolicy;
import com.acme.invoice.domain.DefaultInvoicePricingService;
import com.acme.invoice.domain.TaxPolicy;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.invoice",
        name = "enabled",
        havingValue = "true"
)
@EnableConfigurationProperties(InvoicePricingProperties.class)
public class InvoicePricingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(TaxPolicy.class)
    TaxPolicy invoiceTaxPolicy(InvoicePricingProperties properties) {
        return new ConfiguredTaxPolicy(properties.taxRate());
    }

    @Bean
    @ConditionalOnMissingBean(InvoicePricingService.class)
    InvoicePricingService invoicePricingService(TaxPolicy taxPolicy) {
        return new DefaultInvoicePricingService(taxPolicy);
    }
}
```

The configuration class performs only four tasks:

1. The `acme.invoice.enabled=true` condition decides whether the feature is enabled.
2. `@EnableConfigurationProperties` registers the typed configuration object.
3. The default `TaxPolicy` bean is created if the application has not supplied a policy.
4. The default `InvoicePricingService` bean is created if the application has not supplied a service.

There are no price calculations, line-item loops, invoice validations, or discount logic in this class.

### 9.1. Why use method parameters instead of calling another `@Bean` directly?

Avoid writing:

```java
@Bean
InvoicePricingService invoicePricingService() {
    return new DefaultInvoicePricingService(invoiceTaxPolicy(null));
}
```

The method above directly calls another factory method and even passes the wrong dependency. With `@Configuration(proxyBeanMethods = false)`, a normal Java call is not intercepted to return the managed bean. It can inadvertently construct a fresh object.

Declare dependencies via parameters instead:

```java
@Bean
InvoicePricingService invoicePricingService(TaxPolicy taxPolicy) {
    return new DefaultInvoicePricingService(taxPolicy);
}
```

Spring finds the matching `TaxPolicy` bean and injects it into the factory method. This expresses the dependency graph clearly and works cleanly with lite configuration/`proxyBeanMethods = false`.

### 9.2. Why is `@ConditionalOnMissingBean` important?

Auto-configuration provides defaults for consumers, but should not lock the application into the default implementation.

If the application defines a bean:

```java
@Bean
TaxPolicy regionalTaxPolicy() {
    return new RegionalTaxPolicy();
}
```

then `@ConditionalOnMissingBean(TaxPolicy.class)` ensures the default policy is not registered.

If the application provides:

```java
@Bean
InvoicePricingService customInvoicePricingService() {
    return new CustomInvoicePricingService();
}
```

then the default service backs off.

Conditions should sit on auto-configuration bean methods, where Spring Boot can inspect user bean definitions processed earlier. Declare sufficiently specific return types so Spring recognizes the bean type each method provides.

### 9.3. Do not use `@Service` and `@Bean` at the same time

In the library example, `DefaultInvoicePricingService` is a plain Java class registered via `@Bean`.

Do not add `@Service` to this class, because auto-configuration already creates the bean. If both component scanning and `@Bean` register the same implementation, the application can end up with two beans fulfilling the same contract and encounter ambiguity or unexpected behavior.

## 10. Register auto-configuration in the JAR

For Spring Boot 2.7 and later, create file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Content:

```text
com.acme.invoice.autoconfigure.InvoicePricingAutoConfiguration
```

Each line is a fully qualified class name. This file lets Spring Boot discover auto-configuration in dependency JARs.

For Boot 2.6 and earlier, the legacy mechanism uses the `EnableAutoConfiguration` key in `META-INF/spring.factories`. If a library supports multiple Boot lines, choose registration and annotations compatible with the lowest baseline. The current example uses `@AutoConfiguration`, so it targets Boot 2.7+.

The imports file is registration metadata and contains no business logic. Do not list `DefaultInvoicePricingService` in the imports file if it is only an implementation created by auto-configuration; register only top-level configuration classes.

## 11. Maven setup for the example

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>invoice-pricing-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

The example uses Spring Boot 3.3.13 and Java 17. The parent manages versions for Spring Boot dependencies. The autoconfigure module does not need to pull in `spring-boot-starter-web` if it provides no web endpoints.

If publishing this library for consumers, declare API/runtime dependencies according to the module contract and keep annotation processor/test dependencies in their proper scopes. An umbrella starter can depend on the autoconfigure module plus the dependencies end users need.

## 12. Test the business service without starting Spring

File `InvoicePricingServiceUnitTests.java`:

```java
package com.acme.invoice;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

import com.acme.invoice.api.Invoice;
import com.acme.invoice.api.InvoiceLine;
import com.acme.invoice.api.InvoiceTotal;
import com.acme.invoice.domain.DefaultInvoicePricingService;
import com.acme.invoice.domain.TaxPolicy;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class InvoicePricingServiceUnitTests {

    private static Invoice sampleInvoice() {
        return new Invoice(List.of(
                new InvoiceLine("Book", new BigDecimal("10.00"), 2),
                new InvoiceLine("Pen", new BigDecimal("5.00"), 1)
        ));
    }

    @Test
    void calculatesSubtotalTaxAndTotal() {
        TaxPolicy tenPercent = () -> new BigDecimal("0.10");

        DefaultInvoicePricingService service =
                new DefaultInvoicePricingService(tenPercent);

        InvoiceTotal result = service.calculate(sampleInvoice());

        assertThat(result.subtotal()).isEqualByComparingTo("25.00");
        assertThat(result.tax()).isEqualByComparingTo("2.50");
        assertThat(result.total()).isEqualByComparingTo("27.50");
    }

    @Test
    void rejectsNonPositiveQuantity() {
        TaxPolicy tenPercent = () -> new BigDecimal("0.10");

        DefaultInvoicePricingService service =
                new DefaultInvoicePricingService(tenPercent);

        Invoice invalidInvoice = new Invoice(List.of(
                new InvoiceLine("Book", new BigDecimal("10.00"), 0)
        ));

        assertThatThrownBy(() -> service.calculate(invalidInvoice))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("quantity must be greater than zero");
    }
}
```

Run:

```bash
mvn -Dtest=InvoicePricingServiceUnitTests test
```

Expected output:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

These two tests instantiate the service directly via its constructor. No ApplicationContext, Spring runner, mock container, or `@SpringBootTest` is needed.

This is a major benefit of separating business logic: tests verify pricing rules independently of how Spring registers beans.

## 13. Test wiring and back-off with `ApplicationContextRunner`

Unit tests do not verify whether auto-configuration creates the right beans. We need context tests for the wiring layer.

File `InvoicePricingAutoConfigurationTests.java`:

```java
package com.acme.invoice;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

import com.acme.invoice.api.Invoice;
import com.acme.invoice.api.InvoiceLine;
import com.acme.invoice.api.InvoicePricingService;
import com.acme.invoice.api.InvoiceTotal;
import com.acme.invoice.autoconfigure.InvoicePricingAutoConfiguration;
import com.acme.invoice.domain.TaxPolicy;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class InvoicePricingAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    InvoicePricingAutoConfiguration.class
                            )
                    );

    private static Invoice sampleInvoice() {
        return new Invoice(List.of(
                new InvoiceLine("Book", new BigDecimal("10.00"), 2),
                new InvoiceLine("Pen", new BigDecimal("5.00"), 1)
        ));
    }

    @Test
    void doesNotRegisterServiceWhenEnabledPropertyIsMissing() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(InvoicePricingService.class);
        });
    }

    @Test
    void doesNotRegisterServiceWhenFeatureIsDisabled() {
        this.runner
                .withPropertyValues("acme.invoice.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(InvoicePricingService.class);
                });
    }

    @Test
    void registersDefaultServiceWhenFeatureIsEnabled() {
        this.runner
                .withPropertyValues("acme.invoice.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(InvoicePricingService.class);

                    InvoiceTotal result = context
                            .getBean(InvoicePricingService.class)
                            .calculate(sampleInvoice());

                    assertThat(result.total()).isEqualByComparingTo("27.50");
                });
    }

    @Test
    void usesApplicationProvidedServiceInsteadOfDefault() {
        this.runner
                .withPropertyValues("acme.invoice.enabled=true")
                .withUserConfiguration(UserPricingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(InvoicePricingService.class);

                    InvoiceTotal result = context
                            .getBean(InvoicePricingService.class)
                            .calculate(sampleInvoice());

                    assertThat(result.total()).isEqualByComparingTo("99.00");
                });
    }

    @Test
    void injectsApplicationProvidedTaxPolicyIntoDefaultService() {
        this.runner
                .withPropertyValues("acme.invoice.enabled=true")
                .withUserConfiguration(UserTaxPolicyConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(InvoicePricingService.class);

                    InvoiceTotal result = context
                            .getBean(InvoicePricingService.class)
                            .calculate(sampleInvoice());

                    assertThat(result.subtotal()).isEqualByComparingTo("25.00");
                    assertThat(result.tax()).isEqualByComparingTo("5.00");
                    assertThat(result.total()).isEqualByComparingTo("30.00");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserPricingConfiguration {

        @Bean
        InvoicePricingService customInvoicePricingService() {
            return invoice -> new InvoiceTotal(
                    new BigDecimal("0.00"),
                    new BigDecimal("0.00"),
                    new BigDecimal("99.00")
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserTaxPolicyConfiguration {

        @Bean
        TaxPolicy customTaxPolicy() {
            return () -> new BigDecimal("0.20");
        }
    }
}
```

Run:

```bash
mvn -Dtest=InvoicePricingAutoConfigurationTests test
```

Expected output:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

`ApplicationContextRunner` is used here to test how the configuration wires components together:

- Missing property: feature is not registered.
- Property `false`: feature is not registered.
- Property `true`: default service is created and performs calculations.
- User service present: default service backs off.
- User policy present: default service receives the application-provided policy.

The back-off test uses `AutoConfigurations.of(...)` for auto-configuration and `withUserConfiguration(...)` for user config. This simulates processing user beans before auto-configuration, matching the goal of testing `@ConditionalOnMissingBean`.

## 14. Unit tests and context tests protect two different contracts

| Test type | Verifies | Does not need to verify |
| --- | --- | --- |
| Service unit test | Formulas, validation, rounding, edge cases | Bean registration, property binding |
| Context test | Conditions, bean wiring, overrides, policy injection | Exhaustive business rules |
| Integration test | Resource registration, startup, real module wiring | Every business input combination |
| End-to-end test | Behavior from request/message to output | Internal details of individual classes |

Do not put every test into `@SpringBootTest`. For pure business logic, unit tests are faster and more focused. Use Spring test support for what Spring is actually responsible for: conditions, bean creation, property binding, and overrides.

If the module is published, add an integration test using `@EnableAutoConfiguration` without importing the class directly, to confirm `AutoConfiguration.imports` is discovered. `AutoConfigurations.of(...)` passes the class directly, so it verifies auto-configuration logic but not registration resource discovery.

## 15. For applications instead of libraries, `@Service` can be used

In a typical Spring Boot application, services are usually annotated with:

```java
@Service
public class InvoicePricingServiceImpl implements InvoicePricingService {
    // Business logic
}
```

Constructor injection wires policies or repositories:

```java
@Service
public class InvoiceApplicationService {

    private final InvoicePricingService pricingService;

    public InvoiceApplicationService(InvoicePricingService pricingService) {
        this.pricingService = pricingService;
    }
}
```

Component scanning discovers classes inside scanned packages.

For auto-configuration libraries, explicit `@Bean` is usually better than broad `@ComponentScan`:

- Consumers opt into beans via library dependencies.
- Auto-configuration can toggle on/off via property/class conditions.
- `@ConditionalOnMissingBean` allows consumer overrides.
- The library does not accidentally scan application packages and register unrelated components.

`@Service` can be used in a library module if component scanning is designed intentionally, but you must check for duplicate registration risks when auto-configuration also creates the same bean. Choose one clear registration mechanism.

## 16. Anti-patterns to avoid

### 16.1. Business logic inside `@Bean` methods

**Problem:** Factory methods both create beans and execute business workflows.

**Consequence:** Hard to unit test, startup has side effects, and configurations bloat.

**Fix:** Move logic into services/policies; factory methods only call constructors and pass dependencies.

### 16.2. Using a configuration class as a service

**Problem:** Controllers or other services inject `InvoicePricingAutoConfiguration` to invoke pricing methods.

**Consequence:** Consumers depend on a Spring infrastructure class rather than a business contract.

**Fix:** Inject `InvoicePricingService` or a business abstraction.

### 16.3. Injecting `Environment` into every business service

**Problem:** Services read property Strings themselves and convert types manually.

**Consequence:** Business logic depends on configuration structure and is harder to test.

**Fix:** Bind with `@ConfigurationProperties`, then pass typed values or policies into constructors.

### 16.4. Using static mutable state in configurations

**Problem:** Storing dependencies or business results in static fields.

**Consequence:** State is hard to isolate across contexts/tests, hard to run multiple application contexts, and risks race conditions.

**Fix:** Use stateless beans or state with clear lifecycles; inject via constructors.

### 16.5. Directly calling another `@Bean` method

**Problem:** Under `proxyBeanMethods = false`, direct Java calls can create new objects instead of retrieving managed beans.

**Fix:** Declare dependencies via method parameters or constructor injection.

### 16.6. Creating default beans without allowing consumer overrides

**Problem:** Beans are always registered even when the application already has its own implementation.

**Consequence:** Multiple candidates, ambiguity, or consumers forced onto the wrong service.

**Fix:** Use `@ConditionalOnMissingBean` on default beans and test user overrides.

### 16.7. Component scanning across all consumer packages

**Problem:** Auto-configuration scans overly broad packages.

**Consequence:** The library may mistakenly register application beans or create duplicate beans.

**Fix:** Explicitly register supporting configurations via `@Import` or `@Bean`; let applications manage their own component scans.

### 16.8. Service constructors performing I/O

**Problem:** Constructors connect to databases, make HTTP calls, or load large datasets.

**Consequence:** Building the ApplicationContext becomes infrastructure-dependent and hard to test.

**Fix:** Constructors only accept dependencies and establish invariants. Perform I/O through business methods or dedicated lifecycle components.

## 17. Workflow for designing an auto-configuration with a business service

1. Define the business contract as Spring-independent interfaces and models.
2. Implement the service with explicit constructor dependencies.
3. Extract variable policies into separate abstractions.
4. Write unit tests for rules, validation, and edge cases first.
5. Create `@ConfigurationProperties` for typed configuration values.
6. Create auto-configuration containing only conditions, property registration, and bean wiring.
7. Use `@ConditionalOnMissingBean` to support consumer-provided implementations.
8. Use `@Bean` parameters or constructor injection rather than direct factory method calls.
9. Register auto-configuration via the imports file matching your Boot baseline.
10. Write context tests for property on/off, default beans, and user overrides.
11. If publishing a library, write an integration test verifying discovery from the registration resource.
12. Inspect the final JAR and run a consumer smoke test.

Each step protects a distinct boundary: domain rules, configuration, Spring wiring, and artifact publication.

## 18. Code review checklist

- [ ] Configuration classes contain no formulas or business rules.
- [ ] Factory methods only construct objects and wire dependencies.
- [ ] Business services expose interfaces/contracts suitable for consumers.
- [ ] Services can be unit-tested without a Spring context.
- [ ] Constructor injection makes required dependencies explicit.
- [ ] Policies can be swapped without modifying the core service.
- [ ] Properties are bound into structured data types.
- [ ] `@ConditionalOnProperty` accurately reflects enabled/disabled state.
- [ ] Default beans use `@ConditionalOnMissingBean` when overrides should be allowed.
- [ ] User-provided services/policies are tested in context.
- [ ] Component scanning and `@Bean` do not duplicate registration of the same implementation.
- [ ] `Environment` or static mutable state is not used in the domain unnecessarily.
- [ ] No I/O or heavy business processing runs during bean creation.
- [ ] Unit tests, context tests, and integration tests match the contract.
- [ ] Auto-configuration registration resource is packaged in the right module JAR.

## 19. Self-check questions

**Question 1.** What should an `@AutoConfiguration` class primarily be responsible for?  
**Answer:** Declaring conditions, registering properties, and wiring beans/dependencies. Business rules belong in dedicated services or policies.

**Question 2.** Why shouldn't invoice totals be calculated inside a `@Bean` method?  
**Answer:** The factory method mixes wiring with business logic, complicates unit testing, and risks running unnecessary work during ApplicationContext startup.

**Question 3.** Must a business service carry `@Service`?  
**Answer:** No. It can be a plain Java class registered via `@Bean`, or discovered by component scanning when designed in an application style.

**Question 4.** How does `@ConditionalOnMissingBean(InvoicePricingService.class)` help?  
**Answer:** Auto-configuration creates the default implementation only when the consumer has not provided a matching service.

**Question 5.** Why use constructor injection?  
**Answer:** Required dependencies are explicit, objects can be created in a valid state, and unit tests can easily pass fake/stub implementations.

**Question 6.** What kind of logic should `@ConfigurationProperties` contain?  
**Answer:** Binding configuration values to types and checking basic configuration invariants; it should not contain invoice business workflows.

**Question 7.** With `proxyBeanMethods = false`, why shouldn't you call another `@Bean` method directly?  
**Answer:** A Java call can create a new object instead of retrieving the Spring-managed bean. Declare dependencies via method parameters.

**Question 8.** How do unit tests differ from `ApplicationContextRunner`?  
**Answer:** Unit tests verify business rules in isolation; `ApplicationContextRunner` verifies conditions, bean registration, wiring, and overrides.

**Question 9.** In auto-configuration libraries, why is broad `@ComponentScan` generally avoided?  
**Answer:** It can accidentally scan consumer packages, register unintended components, or create duplicate beans. Explicit `@Bean`/`@Import` keeps registration controlled.

**Question 10.** If a consumer needs country-based tax calculation, must the auto-configuration class be modified?  
**Answer:** Usually not. Provide another `TaxPolicy` implementation; the service continues calling the abstraction. Auto-configuration simply backs off in favor of the consumer-provided policy.

## 20. Principles to remember

- Auto-configuration is the composition root: it decides when and how beans are registered.
- Business services/policies hold behavior, validation, and business rules.
- `@Bean` methods should be short, declare explicit dependencies, and avoid side effects.
- Business services do not have to import Spring; they can be constructed directly in unit tests.
- Use interfaces and constructor injection to decouple consumers from implementations.
- Use `@ConfigurationProperties` for typed configuration; do not let domain services read raw property strings.
- Use `@ConditionalOnMissingBean` so consumers can replace default implementations.
- With `proxyBeanMethods = false`, inject dependencies via method parameters instead of calling other `@Bean` methods directly.
- Distinguish business unit tests, wiring context tests, and discovery integration tests.
- Never let auto-configuration scan consumer packages or run heavy business logic at startup.

### Official references

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — `@AutoConfiguration`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3 API — `@ConditionalOnMissingBean`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Framework — Using `@Bean` Methods](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring Framework — Constructor-based Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Boot 3.3 — Configuration Metadata and `@ConfigurationProperties`](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Testing Auto-configuration with `ApplicationContextRunner`](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
