# Integer, Floating-Point, `scaled_float`, and Precision

Elasticsearch provides multiple numeric data types to store, filter, sort, and aggregate values such as quantities, prices, rating scores, weights, or coordinates. Choosing a numeric type should be based on the value range, the precision that must be preserved, and the operations the application performs. A field holding inventory quantity has different requirements from a field holding monetary amounts or scientific measurements.

In Spring Data Elasticsearch, numeric types are declared in the document mapping using `@Field`. The Java type of the property and the Elasticsearch type must be chosen consistently. If you rely solely on dynamic mapping, Elasticsearch may infer the type from the first document; that choice may not fit the data domain or precision required by the business logic.

## 1. Numeric Types in Elasticsearch

Elasticsearch has integer, floating-point, and `scaled_float` types.

| Elasticsearch type | Data | Typical range or precision | Use case |
|---|---|---|---|
| `byte` | Signed 8-bit integer | -128 to 127 | Small numeric flags, bounded levels |
| `short` | Signed 16-bit integer | -32,768 to 32,767 | Small integers with a known range |
| `integer` | Signed 32-bit integer | -2,147,483,648 to 2,147,483,647 | Quantities or ordinals in a medium range |
| `long` | Signed 64-bit integer | -2^63 to 2^63 - 1 | Large counters, epoch timestamps, monetary amounts in minor units |
| `unsigned_long` | Unsigned 64-bit integer | 0 to 2^64 - 1 | Non-negative values needing a larger range than `long` |
| `half_float` | IEEE 754 16-bit floating-point | About 3 significant digits of precision | Approximate data when saving space |
| `float` | IEEE 754 32-bit floating-point | About 7 significant digits | Approximate measurements, values not requiring high precision |
| `double` | IEEE 754 64-bit floating-point | About 15–16 significant digits | Measurements, coordinates, or approximate calculations needing higher precision than `float` |
| `scaled_float` | Floating-point quantized by a factor | Resolution determined by `scaling_factor`; stored internally as a scaled 64-bit integer | Scores, ratios, or decimal values with a fixed number of fractional digits |

The precision figures for floating-point types are approximations, not a guarantee that every decimal value within that range can be represented exactly. `float` and `double` use IEEE 754 binary representation, so many decimal fractions such as 0.1 do not have a finite binary representation.

### Integers and Floating-Point Numbers Solve Different Needs

Integers fit when the data domain consists of discrete units without fractional parts, such as product stock counts, view counts, or attempt counts. Floating-point numbers fit when data has fractional parts and the application tolerates floating-point representation error, such as temperatures, measured weights, or coordinates.

Do not pick `double` merely because it has a large range. If the data represents product quantity, using a floating-point type allows values like `3.5` to appear even though business rules only permit integers. Similarly, do not use `integer` for a value that might exceed the 32-bit limit.

## 2. Value Ranges and Choosing an Integer Type

When choosing `byte`, `short`, `integer`, or `long`, determine the minimum value, maximum value, and growth rate over the data lifecycle.

For example:

- Warehouse inventory count can use `integer` if business limits always stay within the 32-bit range.
- Cumulative view counts for content can grow very large, so `long` is usually a better fit.
- External identifiers, phone numbers, postal codes, or SKUs should usually be `keyword`, even if they contain only digits. They are identifiers for matching, not quantities for arithmetic.
- Monetary values stored in minor units, such as VND or cents, can use `long` if totals stay within the 64-bit range.

### Choose the Smallest Type or a Sufficiently Wide Type?

Smaller types can save space in some scenarios, but avoid premature optimization. `byte` and `short` have narrow bounds; an out-of-range value will cause an indexing error unless the system has a coercion or error-ignoring policy. If the domain is likely to grow, using `integer` or `long` is usually easier to maintain.

Elasticsearch does not automatically turn `integer` into `long` just because a single value exceeds the limit. The declared mapping governs the valid range. Validate bounds at the application layer before sending documents so errors are caught with clear messages.

### `unsigned_long`

`unsigned_long` represents non-negative integers in the unsigned 64-bit range, from 0 to 2^64 - 1. This range exceeds Java's signed `long` in the upper half. Java has no equivalent `unsigned long` primitive capable of holding that entire range; if the application needs the full range, choose a representation such as `BigInteger` and verify that converters/serializers and the client support it properly.

Do not use `unsigned_long` solely because values are always positive. If the business range fits within `Long.MAX_VALUE`, Java `Long` and Elasticsearch `long` are usually simpler. For identifiers used solely for recognition, `keyword` is typically better than either numeric type.

## 3. Precision of `float` and `double`

`float` and `double` store numbers according to binary floating-point standards. Actual values are rounded to a binary number with finite precision. This can produce results that differ from how humans write decimal numbers.

Example in Java:

```java
double a = 0.1;
double b = 0.2;

System.out.println(a + b); // typically prints 0.30000000000000004
```

This is not an Elasticsearch-specific bug. It is a property of floating-point representation. When a `double` value is sent to Elasticsearch and indexed in a `double` field, representation errors can continue to surface in comparisons, sorting, or aggregations.

### `float` or `double`?

Choose `float` when roughly 7 significant digits of precision suffice for the application and you want a smaller representation. Choose `double` when higher precision—around 15–16 significant digits—is needed, or when computation libraries and Java models already use `double`.

For instance, sensor temperature might not need absolute precision to many decimal places. Conversely, a scientific measurement may require more significant digits. Base the choice on the domain's acceptable error margin, not solely on the number of decimal digits.

### Do Not Use Floating-Point for Exact Monetary Calculations

Currency generally requires explicit rounding rules and reconcilable results. `float` or `double` can introduce binary rounding errors and make cumulative additions and subtractions unpredictable. Use `BigDecimal` in business logic and choose an appropriate representation when sending values to Elasticsearch.

A common approach is converting currency to minor units and storing it as `long`. For example, 125,990 VND is represented as the integer 125990 when the unit is VND; 12.34 USD is represented as 1234 when the unit is cents. For display, convert back using the corresponding scale and always store the currency code.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class MoneyIndexValue {

    private MoneyIndexValue() {}

    public static long toMinorUnits(BigDecimal amount, int scale) {
        return amount
            .movePointRight(scale)
            .setScale(0, RoundingMode.UNNECESSARY)
            .longValueExact();
    }

    public static BigDecimal fromMinorUnits(long minorUnits, int scale) {
        return BigDecimal.valueOf(minorUnits, scale);
    }
}
```

`RoundingMode.UNNECESSARY` makes the operation fail if the value has more fractional digits than the allowed scale. If business rules allow rounding, explicitly choose a rule such as `HALF_UP` or `HALF_EVEN` at the business layer and unit test that rule. Do not let Elasticsearch type coercion dictate monetary rules.

When storing monetary values in minor units, also store `currency` as a `keyword`. Never sum or compare monetary amounts across different currencies as if they shared the same unit.

## 4. How Does `scaled_float` Work?

`scaled_float` is a floating-point type with a scaling factor chosen by the mapping designer. Elasticsearch multiplies the value by `scaling_factor`, rounds to an integer, and stores the scaled value using a 64-bit integer representation. When reading or computing, the value is converted back using that factor.

You can visualize the conversion as follows:

\[
\text{stored} \approx \operatorname{round}(\text{value} \times \text{scaling\_factor})
\]

\[
\text{represented value} = \frac{\text{stored}}{\text{scaling\_factor}}
\]

Example with `scaling_factor = 100`:

| Input value | Value after scaling/rounding | Reconstructed value |
|---:|---:|---:|
| 12.34 | 1234 | 12.34 |
| 12.345 | approx. 1235 | approx. 12.35 |
| 8.90 | 890 | 8.90 |
| 4.567 | approx. 457 | approx. 4.57 |

With a factor of 100, the resolution is 0.01. Values with more than two decimal places can be rounded to the nearest 0.01. Therefore, `scaled_float` does not store arbitrary decimal numbers with infinite precision; it quantizes data to the chosen resolution.

### Choosing `scaling_factor`

Choose the factor according to the resolution to preserve:

| `scaling_factor` | Approximate step size | Example |
|---:|---:|---|
| 1 | 1 | Integer scores |
| 10 | 0.1 | Rating scores with one decimal digit |
| 100 | 0.01 | Ratios or values with two decimal digits |
| 1000 | 0.001 | Measurements requiring three decimal digits |

The larger the factor, the finer the resolution, but the larger the value after multiplication. Because `scaled_float` uses a scaled 64-bit integer range, an overly large factor can push values past the storage bounds. Approximately, the maximum absolute magnitude depends on `Long.MAX_VALUE / scaling_factor`.

### Is `scaled_float` Absolutely Exact?

No. It provides predictable decimal resolution, but it is still a quantization operation with rounding. If the factor is 100, data is represented in multiples of 0.01. For business data requiring exactness down to the minor unit with no rounding allowed, use an integer storing minor units or design a different exact storage model.

`scaled_float` is useful when numeric queries, range filtering, sorting, and aggregations are needed on data with fixed resolution while accepting rounding according to the scale. It is often a good fit for ratings, percentages, or measurements with standardized precision.

## 5. Declaring Numeric Types in Spring Data Elasticsearch

Spring Data Elasticsearch lets you declare field types via `@Field`. Explicitly declare types for important numeric properties rather than relying completely on dynamic mapping.

Example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-v1")
public class ProductSearchDocument {

    @Id
    private String id;

    @Field(type = FieldType.Integer)
    private Integer stockQuantity;

    @Field(type = FieldType.Long)
    private Long viewCount;

    @Field(type = FieldType.Float)
    private Float packageWeight;

    @Field(type = FieldType.Double)
    private Double latitude;

    @Field(type = FieldType.Scaled_Float, scalingFactor = 100)
    private Double averageRating;

    @Field(type = FieldType.Long)
    private Long priceMinorUnits;

    @Field(type = FieldType.Keyword)
    private String currency;

    // Constructors, getters and setters
}
```

The enum names in annotations belong to the Spring Data Elasticsearch API; the JSON mapping sent to Elasticsearch uses lowercase type names such as `integer`, `long`, `float`, `double`, and `scaled_float`. Check the enum values and annotation attributes for your project's exact Spring Data version when upgrading.

`averageRating` uses `Double` in the example to illustrate a Java property mapped to `scaled_float`. If using `BigDecimal` in the entity, confirm that the application's converter/serializer writes it as a JSON number and reads it back according to the desired rules. For money requiring exactness, the example uses `Long` storing minor units to avoid confusion between Java precision and mapping resolution.

### Corresponding JSON Mapping

A corresponding mapping may look like:

```json
{
  "mappings": {
    "properties": {
      "stockQuantity": { "type": "integer" },
      "viewCount": { "type": "long" },
      "packageWeight": { "type": "float" },
      "latitude": { "type": "double" },
      "averageRating": {
        "type": "scaled_float",
        "scaling_factor": 100
      },
      "priceMinorUnits": { "type": "long" },
      "currency": { "type": "keyword" }
    }
  }
}
```

This mapping must be created before indexing the first document if the application wants control over field types. You can use annotations, index operations, or a dedicated index management process to create the mapping; avoid letting a random first document dictate data types.

## 6. Dynamic Mapping and the Risk of Choosing the Wrong Type

If a field has no mapping yet, Elasticsearch can infer a type from the first value received. For example, a numeric field may be created as an integer or floating-point type based on the JSON sent. The created type will then apply to subsequent documents.

This can cause problems if the first document is not representative of later data. For instance, a `rating` field initially receives only `5`, so it is inferred as an integer; later, the application sends `4.5` and encounters a type conflict or unwanted coercion behavior.

For important fields, create explicit mappings:

- `stockQuantity`: `integer` if bounds are well known.
- `viewCount`: `long` if the counter can grow large.
- `rating`: `scaled_float` with an appropriate scale if only a fixed number of decimal places is needed.
- `priceMinorUnits`: `long` if storing money in minor units.
- `sku`, phone numbers, postal codes: `keyword` even though the content looks numeric.

### Type Coercion

Elasticsearch has a `coerce` mechanism for certain numeric fields. When enabled, numeric strings can be converted to numbers and decimal values sent to integer fields can be converted to integers according to coercion rules. This is convenient for inconsistent input data, but it can hide bugs at the application layer.

If business logic needs to reject wrong-type values or disallow fractional parts in integer fields, configure the mapping to disable coercion on the corresponding fields and validate data before writing. Do not rely on Elasticsearch's automatic coercion to enforce business rules.

## 7. Querying, Sorting, and Aggregating on Numeric Fields

Numeric types support range queries, numeric sorting, and aggregations. For example, finding products weighing between 1.5 and 5.0 kg:

```json
{
  "query": {
    "range": {
      "packageWeight": {
        "gte": 1.5,
        "lte": 5.0
      }
    }
  },
  "sort": [
    { "packageWeight": "asc" }
  ]
}
```

Example aggregation calculating average and maximum price:

```json
{
  "size": 0,
  "aggs": {
    "average_price_minor": {
      "avg": { "field": "priceMinorUnits" }
    },
    "maximum_price_minor": {
      "max": { "field": "priceMinorUnits" }
    }
  }
}
```

Aggregations on integers can return floating-point results because metrics like averages can have fractional parts. If displaying money, convert units and round according to business rules. Also filter by `currency` before aggregating so different currencies are not summed together.

With `scaled_float`, range queries and sorting operate on quantized values. If business thresholds fall between two scale steps, clearly define rounding rules and comparison bounds. For example, a scale of 0.01 cannot distinguish 12.341 from 12.344 if both are quantized to the same stored value.

## 8. Numeric Identifiers Are Not Necessarily Numeric Types

A common design mistake is using a numeric type for every string that contains only digits. An SKU `000123`, phone number `0901234567`, or postal code may have leading zeros and no arithmetic meaning.

If `000123` is stored as an integer, the value becomes `123`; the leading-zero information is lost. Range queries on identifiers can also carry unintended numeric semantics. For these fields, use `keyword`:

```java
@Field(type = FieldType.Keyword)
private String sku;

@Field(type = FieldType.Keyword)
private String postalCode;
```

Only use numeric types when the application genuinely needs arithmetic operations or numeric range queries. If you only need exact lookup, filtering, or grouping by code, `keyword` is usually the right choice.

## 9. Integer Limits Across JSON and JavaScript

Elasticsearch `long` can store 64-bit integers, but not every component in the system preserves that entire range accurately. JavaScript uses the `Number` type based on IEEE 754 double; integers are only represented contiguously and accurately up to 2^53 - 1. When an intermediate API, browser, or analytics tool parses a `long` larger than this limit into a `Number`, the value can be rounded.

Example:

```javascript
const value = 9007199254740993;
console.log(value); // may become 9007199254740992
```

If 64-bit values must pass through JavaScript, consider transmitting them as strings at the API boundary, or using a mechanism that supports `BigInt` without directly serializing into an unsafe JSON number. Standard JSON has no dedicated BigInt type; producer and consumer must agree on a convention.

This is also a reason not to use large integers as numeric IDs across all layers if the ID only needs to identify records. A `keyword` string preserves both the exact value and formatting.

## 10. Controlling Overflow, Rounding, and Invalid Data

When receiving data from an API, message queue, or external system, check:

- Is the value within the range of the declared Elasticsearch type?
- Is the value finite and valid?
- Is there a fractional part when the field only permits integers?
- Does the `scaled_float` scale match the business resolution?
- Could multiplying by the scaling factor exceed the 64-bit integer range?
- Does the monetary value match the currency's scale?

Example quantity check in Java:

```java
public static int requireQuantity(long value) {
    if (value < 0 || value > Integer.MAX_VALUE) {
        throw new IllegalArgumentException("Quantity is out of range");
    }
    return Math.toIntExact(value);
}
```

Example decimal check before converting to `double`:

```java
public static double requireFinite(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Value must be finite");
    }
    return value;
}
```

Reject invalid data or route it to an observable error-handling flow. Silently dropping fields or coercing types can cause search and aggregation results to stop reflecting business data.

## 11. Changing Numeric Types After an Index Exists

The mapping of an already-created field cannot be arbitrarily changed from `integer` to `long`, `double`, or `scaled_float` on the same index. Changing `scaling_factor` also changes how stored values are interpreted, so do not treat it as a light property that can be tweaked after data has been indexed.

When a type or resolution change is needed, the standard workflow is:

1. Create a new index with the right mapping.
2. Transform source data to the new type using explicit rules.
3. Reindex or backfill data into the new index.
4. Verify boundary values, document counts, range queries, and aggregations.
5. Switch the alias or application configuration to the new index.
6. Retain the old index as long as needed to support rollback.

For example, if `rating` was previously `float` and you later want `scaled_float` with scale 100, decide how to round historical data, test queries with closely spaced thresholds, and verify that sorting and aggregations still meet requirements.

## 12. Quick Selection Table by Scenario

| Data | Usually appropriate choice | Notes |
|---|---|---|
| Inventory stock count | `integer` | Validate bounds and disallow fractional values |
| Cumulative counter | `long` | May exceed 32-bit limit |
| SKU code, phone number | `keyword` | Preserves leading zeros, no arithmetic meaning |
| Exact monetary amount | `long` in minor units | Also store currency and scale |
| Rating score 0–5 with 1–2 decimal digits | `scaled_float` | Pick factor 10 or 100 according to resolution |
| Approximate measured weight | `float` or `double` | Choose according to acceptable error margin |
| Geographic coordinates | `geo_point` if geo queries are needed | Do not use standalone `double` if geo queries, distance, or bounding boxes are required |
| Non-negative integers exceeding signed 64-bit range | `unsigned_long` | Check representation support in Java and all API layers |

## 13. Workflow for Designing Numeric Fields

When adding a numeric field to a search document, you can follow this sequence:

1. Identify the business meaning: quantity, counter, currency, or identifier.
2. Identify minimum/maximum values and future growth potential.
3. Determine precision: exact integer, approximate floating-point, or decimal with fixed scale.
4. Choose the Elasticsearch type matching the range and resolution.
5. Choose the corresponding Java type; use `BigDecimal` for business decimal calculations and convert deliberately when indexing.
6. Declare explicit mappings before writing the first document.
7. Test boundary values, overflow, rounding, coercion, and null/missing data.
8. Test range queries, sorting, and aggregations with representative data.
9. Verify whether JSON/API layers preserve large values accurately.
10. Plan for reindexing if type or scaling factor changes are needed in the future.

## 14. Conclusion

Numeric types in Elasticsearch must be chosen based on value range and precision requirements. `byte`, `short`, `integer`, and `long` fit bounded integers; `float` and `double` fit approximate IEEE 754 data; `scaled_float` fits decimals with fixed resolution that accept rounding according to the scaling factor.

In Spring Data Elasticsearch, declare mappings explicitly with `@Field`, choose corresponding Java types, and validate data before indexing. For currency or values requiring absolute precision, use `BigDecimal` in business logic and consider storing integers in minor units. For digit-only identifiers, use `keyword`. When changing the type or resolution of an existing field, create a new index and reindex according to plan.
