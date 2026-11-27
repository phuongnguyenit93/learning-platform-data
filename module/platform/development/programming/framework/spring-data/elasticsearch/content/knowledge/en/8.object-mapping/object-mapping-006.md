# Handling Enums, Currencies, and Business Value Types

Application entities often contain data types beyond basic strings and numbers: enum statuses, currencies, product codes, emails, durations, or business-defined value objects. When storing these values in Elasticsearch, you must clearly decide what data is persisted, which mapping fits, and how conversion works between Java types and documents.

Spring Data Elasticsearch uses mapping metadata and the conversion service to convert entities into documents and read documents back into entities. For simple types, the framework already provides many default conversion rules. For custom business types, the application can use converters or a separate document model to control the data structure.

## 1. Conversion Model Between Java and Elasticsearch

When calling `repository.save(entity)`, Spring Data Elasticsearch converts Java properties into document data according to the mapping. When reading a document, conversion runs in the opposite direction.

~~~mermaid
flowchart TD
    A["Domain object / Java Entity"] --> B["MappingElasticsearchConverter"]
    B --> C["CustomConversions and mapping metadata"]
    C --> D["Elasticsearch document"]
    D --> E["Elasticsearch index"]
    E --> F["Document read back"]
    F --> G["MappingElasticsearchConverter"]
    G --> H["Domain object / Java Entity"]
~~~

Three groups of data types commonly appear:

| Group | Example | Typical Handling |
|---|---|---|
| Basic types | String, Integer, Boolean, BigDecimal | Appropriate field mapping |
| Types with built-in conventions | Enum, UUID, date/time | Use default conversions and verify mapping |
| Custom business types | ProductCode, EmailAddress, Money, Quantity | Custom converters or document projection |

It is important to separate **data types in the domain model** from **representation in Elasticsearch**. The domain model serves business rules; the document model serves querying, filtering, sorting, and aggregations.

## 2. Storing Enums in Elasticsearch

An enum represents a finite set of values, such as an order status:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED,
    REFUNDED
}
~~~

In Elasticsearch, statuses are typically stored as strings with a `keyword` mapping, because the application needs to filter on an exact status:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class OrderDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private OrderStatus status;

    // Constructors, getters and setters
}
~~~

Spring Data Elasticsearch supports converting enums to string values under default conversion rules. For a standard Java enum, the value is represented by its constant name. For instance, `OrderStatus.PAID` is stored as `"PAID"`.

You can query the status with `term`:

~~~json
{
  "query": {
    "term": {
      "status": "PAID"
    }
  }
}
~~~

Using `keyword` makes Elasticsearch treat the status as a whole, exact value. Using `text` would cause the analyzer to process the string unnecessarily for an enum.

### Why should you avoid storing enums by ordinal?

Avoid storing the numeric position of an enum such as `0`, `1`, `2`:

~~~java
public enum OrderStatus {
    PENDING,   // 0
    PAID,      // 1
    CANCELLED  // 2
}
~~~

If constants are later added or reordered, the same number can take on a different meaning. Old documents read by newer code could be misinterpreted.

Storing names or stable codes keeps data readable and independent of enum declaration order. However, renaming a constant is still a schema change if that name is already stored in the index.

## 3. Enums with Custom Business Codes

In some systems, the Java enum name is not the value you want to store. For example, an API or legacy system uses code `"P"` for paid instead of `"PAID"`.

You can define an enum with a dedicated code:

~~~java
public enum OrderStatus {

    PENDING("P"),
    PAID("S"),
    CANCELLED("C"),
    REFUNDED("R");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException(
                "Unknown order status code: " + code
        );
    }
}
~~~

If you need to store a custom code, register bidirectional converters instead of relying on constant names.

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class OrderStatusWriteConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.getCode();
    }
}
~~~

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class OrderStatusReadConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

`@WritingConverter` marks the converter used when writing an entity to a document. `@ReadingConverter` marks the converter used when reading a value from a document to a Java type.

Ensure every code existing in the index is recognized by `fromCode`. If an obsolete code exists, handle it under an explicit data compatibility policy rather than silently falling back to a default status.

## 4. Registering Custom Conversions

Spring Data Elasticsearch provides `ElasticsearchCustomConversions` to register converters used during mapping.

Configuration example:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.core.convert.ElasticsearchCustomConversions;

@Configuration
public class ElasticsearchConversionConfig {

    @Bean
    ElasticsearchCustomConversions elasticsearchCustomConversions() {
        return new ElasticsearchCustomConversions(List.of(
                new OrderStatusWriteConverter(),
                new OrderStatusReadConverter(),
                new ProductCodeWriteConverter(),
                new ProductCodeReadConverter()
        ));
    }
}
~~~

Spring Data uses the converters registered in `ElasticsearchCustomConversions` when converting values. Place this configuration in the application context so Elasticsearch's mapping converter receives the required conversions.

When a converter could be interpreted in either direction, `@WritingConverter` and `@ReadingConverter` clarify intent. Also avoid registering multiple competing converters for the same source and target type pair.

Specific package names and configuration mechanisms should be verified against your Spring Data Elasticsearch version; do not mix converters from MongoDB, JPA, or other persistence modules into Elasticsearch's conversion registry.

## 5. Business Value Objects

A value object is a data type that describes a business concept through its value and invariants. Examples:

- `ProductCode`: a valid product code.
- `EmailAddress`: a normalized email address.
- `Money`: an amount paired with a currency unit.
- `Quantity`: an amount paired with a unit of measure.

A value object typically encapsulates validation and behavior to prevent raw strings or numbers from being handled inconsistently across the codebase.

Product code example:

~~~java
import java.util.Objects;

public record ProductCode(String value) {

    public ProductCode {
        Objects.requireNonNull(value, "value must not be null");

        if (!value.matches("[A-Z0-9-]{3,30}")) {
            throw new IllegalArgumentException(
                    "Invalid product code: " + value
            );
        }
    }
}
~~~

In the domain model, using `ProductCode` makes it clear this is a validated product code rather than an arbitrary `String`.

However, Elasticsearch needs to represent this value as indexable data. If the product code is used for exact filtering, it is typically stored as a `keyword` string.

## 6. Custom Converters for Simple Value Objects

For a value object representable as a single scalar, such as `ProductCode`, you can convert between the object and `String`.

Writing converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class ProductCodeWriteConverter
        implements Converter<ProductCode, String> {

    @Override
    public String convert(ProductCode source) {
        return source.value();
    }
}
~~~

Reading converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class ProductCodeReadConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        return new ProductCode(source);
    }
}
~~~

The entity can declare:

~~~java
@Field(type = FieldType.Keyword)
private ProductCode productCode;
~~~

When writing, `ProductCode("KB-1001")` is converted to the string `"KB-1001"`. When reading, the string is converted back to `ProductCode`, and the constructor runs validation.

This approach works well for value objects with one clear scalar representation. If a value object has multiple components that need to be queried separately, do not pack all of them into a single string.

## 7. Storing Currencies and Monetary Amounts

Money is never just a number. A monetary value needs to be accompanied by a currency code, for example:

- `19.99 USD`
- `500000 VND`
- `2500 JPY`

Two amounts with the same numeric value but different currencies cannot be treated as equal. For example, `100 USD` and `100 JPY` do not have the same value.

Do not store only the amount in a numeric field while discarding the currency code. Likewise, do not store a combined string like `"19.99 USD"` in a text field if you need range queries, sorting, or aggregations on the amount.

A query-friendly document representation splits the amount and currency code into two fields:

~~~json
{
  "priceAmount": 1999,
  "priceCurrency": "USD"
}
~~~

In this example, `priceAmount` represents the amount in the currency's minor units, and `priceCurrency` stores the ISO 4217 code.

### Why use minor units?

Storing money as an integer in its smallest unit avoids rounding errors introduced when converting between floating-point types.

Example:

| Currency | Standard Decimal Places | Amount | Minor Units |
|---|---:|---:|---:|
| USD | 2 | 19.99 | 1999 |
| VND | 0 | 500000 | 500000 |
| JPY | 0 | 2500 | 2500 |
| KWD | 3 | 12.345 | 12345 |

The number of decimal places depends on the currency. Java's `Currency` provides `getDefaultFractionDigits()` for supported ISO currency codes.

If the domain uses only a single currency with a fixed scale, `scaled_float` with an appropriate `scalingFactor` can be used. But when supporting multiple currencies with different decimal places, minor units paired with a currency code is a clearer representation.

## 8. Domain Money and Document Projection

The domain can use a dedicated value object:

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {

    public Money {
        Objects.requireNonNull(amount, "amount must not be null");
        Objects.requireNonNull(currency, "currency must not be null");

        int fractionDigits = currency.getDefaultFractionDigits();
        if (fractionDigits < 0) {
            throw new IllegalArgumentException(
                    "Unsupported currency fraction digits: " + currency
            );
        }

        amount = amount.setScale(fractionDigits);
    }
}
~~~

In practice, rounding rules must be an explicitly defined business rule. The example above uses `setScale` with the default rounding mode `UNNECESSARY`; if the amount has more decimal places than allowed, conversion fails rather than silently rounding.

A separate document model representing money in minor units:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Long)
    private Long priceMinorUnits;

    @Field(type = FieldType.Keyword)
    private String priceCurrency;

    // Other fields and getters/setters
}
~~~

Converting between domain `Money` and the document:

~~~java
import java.math.BigDecimal;
import java.util.Currency;

public final class MoneyDocumentMapper {

    private MoneyDocumentMapper() {
    }

    public static long toMinorUnits(Money money) {
        int fractionDigits =
                money.currency().getDefaultFractionDigits();

        if (fractionDigits < 0) {
            throw new IllegalArgumentException(
                    "Unsupported currency: " + money.currency()
            );
        }

        return money.amount()
                .movePointRight(fractionDigits)
                .longValueExact();
    }

    public static Money toMoney(
            long minorUnits,
            String currencyCode
    ) {
        Currency currency = Currency.getInstance(currencyCode);
        int fractionDigits = currency.getDefaultFractionDigits();

        if (fractionDigits < 0) {
            throw new IllegalArgumentException(
                    "Unsupported currency: " + currencyCode
            );
        }

        BigDecimal amount =
                BigDecimal.valueOf(minorUnits, fractionDigits);

        return new Money(amount, currency);
    }
}
~~~

`longValueExact()` guarantees fractional parts are not silently dropped and numeric overflow does not occur during conversion. If the amount cannot be represented accurately in the currency's minor units, conversion raises an error.

Document projection decouples the storage structure from the domain model. When an index mapping has multiple fields dedicated to search, this is often easier to control than trying to squeeze a complex object into a single scalar.

### Filtering by currency and price range

When finding products priced between 10 and 100 USD, the query must filter on both currency and the minor units range:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "priceCurrency": "USD"
          }
        },
        {
          "range": {
            "priceMinorUnits": {
              "gte": 1000,
              "lte": 10000
            }
          }
        }
      ]
    }
  }
}
~~~

Do not compare `priceMinorUnits` across different currencies without conversion. `1000` minor units in USD is 10 USD, whereas in JPY it means 1000 JPY. If cross-currency aggregations are needed, store a converted value with an explicit target currency, exchange rate, and conversion timestamp.

Elasticsearch is well suited for searching and filtering over currency projections. An accounting system or transactional source of truth should still own exact financial calculation rules and authoritative records.

## 9. When to Use Custom Converters vs. a Separate Document Model

There are two primary strategies:

| Scenario | Suitable Strategy |
|---|---|
| Value object represented by one string or number | Scalar custom converter |
| Enum needing custom stable codes | Custom read/write converters |
| Value object with multiple parts needing separate queries | Document model or object mapping |
| Money needing filtering by amount and currency | Separate numeric field and currency code |
| Domain model differs significantly from Elasticsearch structure | Document projection and mapper |
| Only storing/reading simple types already supported by Spring | Use default conversions |

Custom converters fit when you want to preserve strong domain types while the stored form can be represented as a simple value.

A separate document model fits when the index structure is optimized for querying and may diverge from domain structure. It also prevents Elasticsearch annotations from spreading into shared domain classes used across multiple application layers.

## 10. Data Compatibility When Changing Enums or Value Objects

Data stored in Elasticsearch exists independently of the current code version. Consequently, changing conversion logic can affect older documents.

### Renaming an enum constant

If `"PAID"` was stored previously and new code renames it to `"SETTLED"`, existing documents still contain `"PAID"`. The new reading converter must support the old value during a transition period, or existing data must be updated/reindexed.

### Changing an enum code

If code `"P"` changes to `"S"`, define how both codes are read during migration and how old documents are updated.

### Changing Money structure

If `price` was previously stored as a string and later split into `priceMinorUnits` and `priceCurrency`, a migration step is needed to transform old documents. Changing Java classes alone does not alter already-indexed data.

### Changing value object validation

If a new constructor rejects a legacy value, reading old documents may fail. Audit existing data, support the legacy format during a transition period, or clean up data before enforcing the stricter rule.

A safe strategy is creating a new versioned index, reindexing data through a transforming mapper, and switching the alias to the new index after verifying results.

## 11. Common Pitfalls

### Storing enums by ordinal

Changing enum order can give old numbers different meanings. Store names or stable codes instead.

### Using text fields for enums

Enums are normally used in filters or terms aggregations. `keyword` mapping is more appropriate.

### Writing an enum by code without a reverse reading converter

Writing `"P"` when the reading converter only recognizes `"PAID"` causes mapping failures on read. Implement both write and read directions.

### Storing money without a currency code

An amount without a currency unit is incomplete data. Store the currency code alongside the amount.

### Using double for exact monetary calculations

Binary floating-point numbers may fail to represent decimal numbers accurately. Use `BigDecimal` in the domain and choose a document representation with clear precision rules.

### Comparing minor units across currencies

Minor units depend on the currency's decimal places. Always filter by the corresponding currency before comparing amounts or perform controlled currency conversion.

### Packing a multi-field value object into a single string

If you need to filter on individual components, store them as separate fields or mapped objects. A concatenated string loses structured query capabilities.

### Failing to test old documents after changing converters

New converters may be unable to read legacy formats. Check real data and plan migrations accordingly.

## 12. Workflow for Designing Entity Conversions

When introducing a business type into Spring Data Elasticsearch, you can follow these steps:

1. Identify the domain type and the invariants its constructor or value object must protect.
2. Decide whether data will be stored as a scalar, an object, or multiple separate fields.
3. Choose mappings suited to queries: `keyword` for enums/codes, numeric for amounts, and a separate field for currency.
4. Use default conversions when they match the required data format.
5. Write bidirectional converters for scalar value objects or enums with custom codes.
6. Register converters in `ElasticsearchCustomConversions`.
7. For multi-component value objects, consider a document projection to control the mapping.
8. Verify data written to documents and read back into domain objects.
9. Define how legacy documents will be handled when enum names, codes, or value object structures change.
10. Test actual queries against the indexed fields.

## Conclusion

Enums are typically stored as `keyword` strings; when stable business codes are required, use custom read/write converters. Scalar value objects like `ProductCode` can convert bidirectionally via strings. Monetary values must store both amount and currency code; use minor units or a numeric representation with well-defined precision to support range queries and sorting. When the domain model differs from the search structure, document projections provide full control over Elasticsearch data without sacrificing business semantics.
