# Mapping Monetary Values, Business Codes, and Rule-Based Time Types in Spring Data JPA

Many business attributes are not just plain Strings, BigDecimals, or LocalDates. A monetary amount has both an amount and a currency; an order number must follow a specific format; a billing period may be a YearMonth; operating hours have opening and closing rules. Storing these values as primitives everywhere leads to duplicated rules and invalid data.

Spring Data JPA relies on JPA to map Java models to databases. You can use basic types, @Embeddable to store a value object across multiple columns, or AttributeConverter to convert a custom Java type into a basic database type. This lesson explains how to choose a strategy and builds examples for money, business codes, and rule-based time types.

## 1. Value Objects and Business Values

A value object describes a value with business meaning. It is normally compared by value rather than its own identifier, encapsulates validation rules, and should be immutable or restrict mutation after creation.

| Value | Java type | Common rules |
|---|---|---|
| Price | Money with BigDecimal and Currency | Do not mix currencies, scale and rounding |
| Order number | OrderNumber | Correct prefix, length, characters, and uniqueness |
| ISBN code | Isbn | Normalization, format/check-digit validation |
| Billing period | YearMonth | A calendar month, without day or time |
| Opening hours | BusinessHours | Valid open/close times, possibly crossing midnight |
| Date range | DateRange | Start date before end date |

Not every value object needs its own table or entity. If it has no independent lifecycle and identity, it can be mapped as an attribute of the owning entity.

## 2. Main Mapping Strategies

**Basic types supported by JPA:** directly use String, BigDecimal, LocalDate, LocalDateTime, Instant, Boolean, or enum. This is the simplest approach when one attribute corresponds to one column.

~~~java
@Column(name = "unit_price", precision = 19, scale = 4, nullable = false)
private BigDecimal unitPrice;
~~~

**@Embeddable and @Embedded:** use when a value object consists of multiple attributes stored across multiple columns of the same table.

~~~java
@Embeddable
public class Money {
    private BigDecimal amount;
    private String currencyCode;
}

@Entity
public class Product {
    @Embedded
    private Money price;
}
~~~

**AttributeConverter:** use when a custom Java type can be represented by a single basic database type, such as OrderNumber as VARCHAR or YearMonth as CHAR(7).

~~~java
@Converter
public class OrderNumberConverter
        implements AttributeConverter<OrderNumber, String> {
    // Bidirectional conversion.
}
~~~

| Strategy | Column count | When appropriate | Example |
|---|---:|---|---|
| Basic mapping | One column | Directly supported by JPA | BigDecimal, LocalDate |
| @Embeddable | One or more columns | Multi-component value object | Money, BusinessHours |
| AttributeConverter | One basic database type | Custom type with simple representation | OrderNumber, YearMonth |
| Custom Hibernate type | Depends | Specific JDBC/provider type | DB-specific types |

Prefer standard JPA mappings so the application is less coupled to Hibernate and easier to port across databases. Only use custom Hibernate types when basic mappings, embeddables, and converters cannot satisfy the requirements.

## 3. Mapping Money: BigDecimal Alone Is Not Enough

BigDecimal is suitable for storing exact decimal numbers compared to float or double. However, BigDecimal only represents a number; it does not indicate whether it is USD, VND, or EUR. Never use double or float for prices, balances, or taxes because binary floating-point arithmetic can introduce rounding errors.

A monetary value typically needs an amount (BigDecimal), a currency (ISO 4217 code like USD, EUR, VND), and business-appropriate scale/rounding rules. There is no single fixed scale valid for all currencies and all business domains. VND is often represented with 0 decimal places in ordinary transactions, USD usually 2, and some currencies have 3. Taxes, exchange rates, or accounting may require specific precision. Currency.getDefaultFractionDigits() is only a reference, not a substitute for business rounding policies.

## 4. Creating a Money Value Object with @Embeddable

Use this approach when you want to store amount and currency in two separate columns while keeping them as a unified value in Java.

File Money.java:

~~~java
package com.example.shop.domain;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Embeddable;

@Embeddable
public class Money {

    @Column(name = "amount", precision = 19, scale = 4, nullable = false)
    private BigDecimal amount;

    @Convert(converter = CurrencyConverter.class)
    @Column(name = "currency_code", length = 3, nullable = false)
    private Currency currency;

    protected Money() {
    }

    public Money(BigDecimal amount, Currency currency) {
        this.amount = Objects.requireNonNull(amount);
        this.currency = Objects.requireNonNull(currency);
        if (amount.scale() > 4) {
            throw new IllegalArgumentException(
                    "Amount supports at most 4 decimal places");
        }
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public Currency getCurrency() {
        return currency;
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money subtract(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other);
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                    "Cannot combine different currencies");
        }
    }

    @Override
    public boolean equals(Object object) {
        if (this == object) return true;
        if (!(object instanceof Money other)) return false;
        return amount.compareTo(other.amount) == 0
                && currency.equals(other.currency);
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount.stripTrailingZeros(), currency);
    }
}
~~~

Money enforces basic rules: amount and currency must not be null, amount must not exceed the scale supported by the example schema, and addition/subtraction only happen between matching currencies. Rounding is not performed automatically; the business logic must explicitly choose scale and RoundingMode.

### Converting Currency to an ISO code in the database

Currency is converted to a three-character string code using AttributeConverter.

~~~java
package com.example.shop.domain;

import java.util.Currency;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class CurrencyConverter
        implements AttributeConverter<Currency, String> {

    @Override
    public String convertToDatabaseColumn(Currency currency) {
        return currency == null ? null : currency.getCurrencyCode();
    }

    @Override
    public Currency convertToEntityAttribute(String code) {
        return code == null ? null : Currency.getInstance(code);
    }
}
~~~

Currency.getInstance("USD") is stored as "USD"; on read, the converter reconstructs Currency. If the database contains an invalid code, Currency.getInstance throws an error. Validate or migrate legacy data before enabling the converter.

### Embedding Money into an entity

~~~java
@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(name = "amount",
            column = @Column(name = "price_amount",
                precision = 19, scale = 4, nullable = false)),
        @AttributeOverride(name = "currency",
            column = @Column(name = "price_currency",
                length = 3, nullable = false))
    })
    private Money price;

    protected Product() {
    }

    public Product(String name, Money price) {
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Money getPrice() {
        return price;
    }
}
~~~

The products table has price_amount and price_currency columns. Both columns belong to one Money in the entity. @AttributeOverrides allows renaming/configuring columns when reusing the same embeddable in multiple places. No @OneToOne or separate table is needed because Money has no independent identity.

## 5. Monetary Calculation and Rounding Rules

BigDecimal supports exact decimal arithmetic, yet division may not yield a terminating decimal result. An explicit scale and RoundingMode must be chosen.

~~~java
BigDecimal subtotal = new BigDecimal("19.99");
BigDecimal taxRate = new BigDecimal("0.10");

BigDecimal tax = subtotal
        .multiply(taxRate)
        .setScale(2, RoundingMode.HALF_UP);

BigDecimal total = subtotal.add(tax);

System.out.println(tax);
System.out.println(total);
~~~

Output:

~~~text
2.00
21.99
~~~

Guidelines:

- Construct BigDecimal from strings such as new BigDecimal("19.99"), avoiding new BigDecimal(19.99).
- Determine scale by business domain: list price, tax, exchange rate, or settlement.
- Choose RoundingMode intentionally: HALF_UP, HALF_EVEN, DOWN, UP, or another suitable mode.
- Do not round automatically inside a converter if doing so loses data.
- When adding/subtracting Money, verify matching currencies.
- When converting currencies, require explicit exchange rate, effective timestamp, rate source, and rounding rules.

Database precision/scale is a storage limit; rounding rules are business rules.

## 6. Mapping Business Codes with AttributeConverter

An order number is a single-column value object. The application wants to avoid passing arbitrary Strings and ensure format validity upon object creation.

File OrderNumber.java:

~~~java
package com.example.shop.domain;

import java.util.Objects;
import java.util.regex.Pattern;

public final class OrderNumber {

    private static final Pattern FORMAT =
            Pattern.compile("ORD-[0-9]{8}");

    private final String value;

    public OrderNumber(String value) {
        Objects.requireNonNull(value);
        if (!FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "Order number must match ORD- followed by 8 digits");
        }
        this.value = value;
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object object) {
        return object instanceof OrderNumber other
                && value.equals(other.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }

    @Override
    public String toString() {
        return value;
    }
}
~~~

OrderNumber is an immutable class: the value is validated in the constructor and there are no setters. If codes require case, whitespace, or delimiter normalization, perform it consistently before validating and storing.

Converter:

~~~java
package com.example.shop.domain;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class OrderNumberConverter
        implements AttributeConverter<OrderNumber, String> {

    @Override
    public String convertToDatabaseColumn(OrderNumber attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public OrderNumber convertToEntityAttribute(String dbData) {
        return dbData == null ? null : new OrderNumber(dbData);
    }
}
~~~

Entity using the converter:

~~~java
@Entity
@Table(name = "orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = OrderNumberConverter.class)
    @Column(name = "order_number", nullable = false, unique = true, length = 12)
    private OrderNumber orderNumber;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(OrderNumber orderNumber) {
        this.orderNumber = orderNumber;
    }

    public Long getId() {
        return id;
    }

    public OrderNumber getOrderNumber() {
        return orderNumber;
    }
}
~~~

When saving PurchaseOrder, JPA calls the converter to write OrderNumber as VARCHAR. When loading the entity, JPA calls the converter to recreate OrderNumber. The constructor protects format validity even when data comes from the database.

Add a unique constraint in the database for codes that must be unique. Checking for duplicates in Java before inserting is not enough to prevent two concurrent requests from generating the same code; database constraints are the final safeguard.

## 7. Use autoApply or Explicit @Convert?

Automatic conversion can be enabled:

~~~java
@Converter(autoApply = true)
public class OrderNumberConverter
        implements AttributeConverter<OrderNumber, String> {
    // Conversion methods as in the example above.
}
~~~

When autoApply=true, the converter is applied to attributes with the matching Java type in the persistence unit per JPA rules. This is convenient when all OrderNumber attributes always share the same database representation.

Prefer explicit @Convert if only certain fields need the converter, the same Java type has multiple representations, or you want the mapping visible right at the attribute:

~~~java
@Convert(converter = OrderNumberConverter.class)
@Column(name = "order_number", length = 12)
private OrderNumber orderNumber;
~~~

Avoid enabling autoApply for broad types that require varying storage formats. Converters have applicability limits per the JPA specification; for example, they do not automatically convert identifier, version, relationship attributes, or attributes already handled by @Enumerated/@Temporal per their respective rules. For complex mappings, consult the specification and verify provider behavior.

## 8. Mapping Rule-Based Time Types with YearMonth

YearMonth represents a calendar month, such as 2026-11. It has no specific day or time of day, making it suitable for billing periods, payroll periods, and monthly reports.

Converting YearMonth to an ISO yyyy-MM string:

~~~java
package com.example.shop.persistence;

import java.time.YearMonth;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class YearMonthConverter
        implements AttributeConverter<YearMonth, String> {

    @Override
    public String convertToDatabaseColumn(YearMonth attribute) {
        return attribute == null ? null : attribute.toString();
    }

    @Override
    public YearMonth convertToEntityAttribute(String dbData) {
        return dbData == null ? null : YearMonth.parse(dbData);
    }
}
~~~

Applying in an entity:

~~~java
@Entity
@Table(name = "invoices")
public class Invoice {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = YearMonthConverter.class)
    @Column(name = "billing_month", length = 7, nullable = false)
    private YearMonth billingMonth;

    protected Invoice() {
    }

    public Invoice(YearMonth billingMonth) {
        this.billingMonth = billingMonth;
    }

    public Long getId() {
        return id;
    }

    public YearMonth getBillingMonth() {
        return billingMonth;
    }
}
~~~

The billing_month column can use CHAR(7) or VARCHAR(7), depending on migrations. ISO yyyy-MM strings sort lexicographically in chronological ascending order if consistent formatting and width are always maintained.

## 9. Mapping Rule-Based Time Ranges with @Embeddable

A store has opening and closing hours. Storing just two LocalTime values is insufficient; rules are needed to indicate whether the hours can cross midnight and how open/closed intervals are evaluated.

~~~java
package com.example.shop.domain;

import java.time.LocalTime;
import java.util.Objects;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class BusinessHours {

    @Column(name = "opens_at", nullable = false)
    private LocalTime opensAt;

    @Column(name = "closes_at", nullable = false)
    private LocalTime closesAt;

    @Column(name = "crosses_midnight", nullable = false)
    private boolean crossesMidnight;

    protected BusinessHours() {
    }

    public BusinessHours(
            LocalTime opensAt,
            LocalTime closesAt,
            boolean crossesMidnight) {
        this.opensAt = Objects.requireNonNull(opensAt);
        this.closesAt = Objects.requireNonNull(closesAt);
        this.crossesMidnight = crossesMidnight;

        if (opensAt.equals(closesAt)) {
            throw new IllegalArgumentException(
                    "Opening and closing times must differ");
        }

        boolean actuallyCrosses = closesAt.isBefore(opensAt);
        if (actuallyCrosses != crossesMidnight) {
            throw new IllegalArgumentException(
                    "crossesMidnight does not match the time range");
        }
    }

    public boolean contains(LocalTime time) {
        Objects.requireNonNull(time);
        if (crossesMidnight) {
            return !time.isBefore(opensAt) || time.isBefore(closesAt);
        }
        return !time.isBefore(opensAt) && time.isBefore(closesAt);
    }

    public LocalTime getOpensAt() {
        return opensAt;
    }

    public LocalTime getClosesAt() {
        return closesAt;
    }

    public boolean isCrossesMidnight() {
        return crossesMidnight;
    }
}
~~~

Using entity:

~~~java
@Entity
@Table(name = "stores")
public class Store {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Embedded
    private BusinessHours businessHours;

    protected Store() {
    }

    public Store(String name, BusinessHours businessHours) {
        this.name = name;
        this.businessHours = businessHours;
    }

    public boolean isOpenAt(LocalTime time) {
        return businessHours.contains(time);
    }
}
~~~

Example:

~~~java
BusinessHours daytime = new BusinessHours(
        LocalTime.of(8, 0), LocalTime.of(17, 0), false);
BusinessHours overnight = new BusinessHours(
        LocalTime.of(22, 0), LocalTime.of(6, 0), true);

System.out.println(daytime.contains(LocalTime.of(12, 0)));
System.out.println(overnight.contains(LocalTime.of(2, 0)));
~~~

Output:

~~~text
true
true
~~~

The example uses the convention that the open interval includes the opening time and excludes the closing time. BusinessHours only describes wall-clock time; if a store operates in regions with DST or across timezones, combine it with a date and ZoneId to determine actual instants.

## 10. Querying Repositories with Value Objects

With OrderNumber mapped onto an entity attribute by a converter, query methods can be declared:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(OrderNumber orderNumber);

    boolean existsByOrderNumber(OrderNumber orderNumber);
}
~~~

Spring Data parses method names against entity attributes. When querying an attribute mapped by a converter, the JPA provider applies the corresponding conversion when binding parameters for JPQL/criteria queries according to the mapping.

With Money as an embeddable, sub-attributes can be queried:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {

    List<Product> findByPrice_CurrencyAndPrice_AmountGreaterThan(
            Currency currency,
            BigDecimal minimumAmount);
}
~~~

Underscores clarify nested attribute paths: price.currency and price.amount. Always filter by currency when comparing amounts; 100 USD and 100 VND are not the same economic value.

JPQL can also access embeddable attributes:

~~~java
@Query("""
       select p
       from Product p
       where p.price.currency = :currency
         and p.price.amount >= :minimum
       """)
List<Product> findAtLeast(
        @Param("currency") Currency currency,
        @Param("minimum") BigDecimal minimum);
~~~

With native queries, SQL uses physical column names such as price_amount and price_currency. Parameter conversion for native queries can depend on the provider and result types; test with the deployed Hibernate/database version and do not assume all native queries handle converters identically to JPQL.

## 11. Choosing @Embeddable, AttributeConverter, or Entity

- Use @Embeddable when a value object has multiple attributes stored across multiple columns, needs per-component querying, or needs @AttributeOverride.
- Use AttributeConverter when a Java type maps to a single basic value, such as OrderNumber to VARCHAR, YearMonth to CHAR(7), or Currency to an ISO code.
- Use basic types when JPA already supports them and no additional domain rules are needed.
- Use @ElementCollection when storing a collection of value objects without separate identities; collections are typically stored in an auxiliary table.
- Use a separate entity when an object has its own identity, lifecycle, relationships, or independent management.
- Use custom Hibernate types when integrating specific JDBC/provider types and accepting Hibernate coupling.

Do not use a converter for a multi-component object if you have to cram data into an ad-hoc string that is hard to query. Nor should you create an entity for every value object, as that adds unnecessary persistence complexity.

## 12. Nulls, Validation, and Legacy Data

AttributeConverter should handle null in both directions. If the entity attribute is null, the converter returns null; if the database returns null, the converter returns null. Place nullable constraints on entity mappings and schemas according to business rules.

Checks to perform:

- Value objects reject invalid values upon creation, without waiting until save time.
- Converters do not contain business logic that silently alters data.
- When reading invalid legacy data, converters may throw exceptions; have a migration plan ready.
- Place unique constraints on business codes that must be unique.
- Use CHECK constraints when the database supports them and rules can be expressed in SQL.
- Keep normalization rules consistent across API, domain, and database.
- For embedded values, clarify whether the entire value object can be null or all components are required.

Avoid using converters to mask invalid data by returning default values. That can allow corrupted data to propagate silently through the system undetected.

## 13. Migrations and Database Schemas

Entity mappings describe how JPA views data. In real applications, schemas should be managed with Flyway or Liquibase rather than relying entirely on Hibernate ddl-auto=update.

Illustrative SQL migration example:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price_amount DECIMAL(19, 4) NOT NULL,
    price_currency CHAR(3) NOT NULL,
    CONSTRAINT chk_price_amount_nonnegative
        CHECK (price_amount >= 0)
);

CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(12) NOT NULL UNIQUE
);

CREATE TABLE invoices (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    billing_month CHAR(7) NOT NULL
);
~~~

Identity syntax may need adjustments per database. This example illustrates the schema; write migrations in the actual dialect of PostgreSQL, MySQL, or H2 used by the project.

Verify DECIMAL precision/scale, currency_code length, order_number unique constraint, billing_month yyyy-MM format, and embedded column names. In production, configure Hibernate ddl-auto=validate or none depending on the migration process; avoid letting the application alter schemas unexpectedly.

## 14. Testing Value Objects and Converters

Testing domain objects independently of the database:

~~~java
@Test
void moneyRejectsDifferentCurrencies() {
    Money usd = new Money(
            new BigDecimal("10.00"), Currency.getInstance("USD"));
    Money eur = new Money(
            new BigDecimal("10.00"), Currency.getInstance("EUR"));

    assertThatThrownBy(() -> usd.add(eur))
            .isInstanceOf(IllegalArgumentException.class);
}

@Test
void orderNumberRejectsInvalidFormat() {
    assertThatThrownBy(() -> new OrderNumber("wrong"))
            .isInstanceOf(IllegalArgumentException.class);
}
~~~

Testing converters:

~~~java
@Test
void orderNumberConverterRoundTrips() {
    OrderNumberConverter converter = new OrderNumberConverter();
    OrderNumber original = new OrderNumber("ORD-12345678");

    String stored = converter.convertToDatabaseColumn(original);
    OrderNumber restored = converter.convertToEntityAttribute(stored);

    assertThat(stored).isEqualTo("ORD-12345678");
    assertThat(restored).isEqualTo(original);
}
~~~

JPA integration testing with @DataJpaTest:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void persistsMoneyAsAmountAndCurrency() {
        Money price = new Money(
                new BigDecimal("125.50"), Currency.getInstance("USD"));

        Product saved = repository.save(new Product("Keyboard", price));
        Product loaded = repository.findById(saved.getId()).orElseThrow();

        assertThat(loaded.getPrice()).isEqualTo(price);
        assertThat(loaded.getPrice().getCurrency().getCurrencyCode())
                .isEqualTo("USD");
    }
}
~~~

Real tests should cover value object round-trips, unique constraints, null data, currency scale, and derived queries. If using native queries or database-specific SQL types, test against the actual target database; H2 is not guaranteed to reproduce every difference of PostgreSQL or MySQL.

## 15. Common Errors

| Error | Cause | Fix |
|---|---|---|
| Converter is not called | Missing @Convert or converter not scanned | Check annotations, package scan, and persistence unit |
| Malformed business code | Validation exists only at the API layer | Validate inside constructors/factories |
| Money loses precision | Using double/float or SQL scale is too small | Use BigDecimal and an appropriate DECIMAL definition |
| Adding Money of different currencies | Not checking currencies | Enforce matching currency codes or convert with an exchange rate |
| Currency cannot be read | Database contains invalid code | Clean up data and validate ISO codes |
| YearMonth fails to parse | Data does not follow yyyy-MM | Normalize and migrate data |
| Embedded column name collision | Multiple embeddables sharing the same default names | Use @AttributeOverride |
| Derived query fails to build | Wrong nested attribute path | Check attribute names and underscores |
| Native query maps incorrectly | Column names/result types differ from mapping | Check SQL, aliases, and mappings |
| Invalid data enters database | Validating only in Java | Add NOT NULL, UNIQUE, and CHECK constraints |

## 16. Practical Design Principles

- Place validation rules inside value objects so all data creation paths are protected.
- Use @Embeddable for multi-component values that need per-column storage and querying.
- Use AttributeConverter for custom values with a simple database representation.
- Only enable autoApply when the same Java type always requires one consistent storage representation.
- Never use double/float for money; define precision, scale, and rounding per business rules.
- Store currency code alongside amount if data can involve multiple currencies.
- Use validated business codes backed by unique constraints in the database.
- For rule-based time types, represent types and timezones explicitly; do not hide rules inside converters.
- Manage schemas via migrations and test against real databases.
- Keep converters simple, deterministic, testable, and independent of request/session state.

## 17. Self-Assessment Checklist

- [ ] Explain value objects and why not every value object is an entity.
- [ ] Distinguish basic mappings, @Embeddable, and AttributeConverter.
- [ ] Build Money using BigDecimal and Currency.
- [ ] Ensure monetary addition/subtraction apply only to matching currencies.
- [ ] Choose precision, scale, and RoundingMode according to business rules.
- [ ] Map business codes to VARCHAR using a converter.
- [ ] Know when to enable autoApply and when to use explicit @Convert.
- [ ] Map YearMonth as a yyyy-MM string.
- [ ] Model opening hours with @Embeddable and verify midnight-crossing rules.
- [ ] Query embedded attributes using derived queries or JPQL.
- [ ] Design migrations with appropriate NOT NULL, UNIQUE, CHECK, and precision constraints.
- [ ] Test domain objects, converters, and JPA round-trips.

## 18. Conclusion

Business values such as monetary amounts, order numbers, and time periods should be modeled together with their rules. @Embeddable fits multi-component value objects like Money or BusinessHours; AttributeConverter fits single-column types like OrderNumber or YearMonth. Standard JPA basic types remain a solid choice when no separate domain class is needed.

When selecting a mapping strategy, weigh data structure, queryability, cross-database portability, and where validation lives. Value objects enforce rules in Java, converters/embeddables define storage representations, while constraints and migrations protect data in the database. Combining these layers properly yields a clear domain model and consistent data.
