# Handling Wrong-Type Data or Missing Properties While Preserving Semantics

In Neo4j, data is represented using **nodes**, **relationships**, and properties in a property graph. Within the same `:Person` label, one node may store `age` as an integer, another node may store `age` as a string, and another node may not have `age` at all. When querying with Cypher, coercing types or assigning default values indiscriminately can turn “unknown” or “invalid” into a value that looks real.

The goal of this lesson in the **Expressions and Functions** chapter is to read, classify, convert, and update heterogeneous data in a controlled manner while preserving the business semantics of missing values, wrong-type values, and valid values.

## 1. Distinguishing States Before Processing

Suppose a user management system has the properties `externalId`, `ageRaw`, and `active`. The following situations carry different meanings:

| Initial Data | Possible Meaning | Appropriate Handling |
| --- | --- | --- |
| Property `ageRaw` does not exist | Age has not been provided | Keep missing status; do not infer age as 0 |
| `ageRaw = 'abc'` | Provided, but cannot be converted to an age | Flag as invalid data for inspection |
| `ageRaw = '0'` | Age is 0 (valid if domain allows) | Convert to the number 0, do not treat as missing |
| `ageRaw = 27.5` | Floating-point number, unsuitable if age must be an integer | Reject or handle according to confirmed business rules |
| `active = false` | Inactive user | Preserve `false`; do not replace with a default value |
| `nickname = ''` | An empty string was stored | Decide per business rules whether an empty string is valid |

Foundational rule: **check presence, type/format validity, and value range before choosing a replacement value**. A technically successful conversion is not necessarily correct from a business perspective.

### `null` in Cypher

When accessing a non-existent property, such as `p.ageRaw`, Cypher returns `null`. Node and relationship properties do not store `null` values: running `SET p.ageRaw = null` removes that property. Therefore, for a stored node, querying `p.ageRaw IS NULL` covers the case where the property is absent.

~~~cypher
MATCH (p:Person)
RETURN p.externalId AS id,
       p.ageRaw IS NULL AS missingAge,
       p.ageRaw IS NOT NULL AS hasAge;
~~~

Standard comparisons with `null` do not behave like comparisons with a concrete value:

~~~cypher
RETURN null = null AS undefinedComparison,
       null IS NULL AS isNullCheck,
       coalesce(null, 0) AS defaultZero;
~~~

The result of `null = null` is still `null`, whereas `null IS NULL` is `true`. In a `WHERE` clause, only expressions that evaluate to `true` are kept; both `false` and `null` filter out the row. Therefore, use `IS NULL` or `IS NOT NULL` to check for missing data, and avoid `= null` and `<> null`.

## 2. Choosing the Right Cypher Tool

| Tool | Purpose | Key Consideration |
| --- | --- | --- |
| `IS NULL` / `IS NOT NULL` | Identify a missing value at the accessed location | Does not prove that a present value has the right type |
| `coalesce(a, b, ...)` | Return the first non-`null` value | Only meaningful when a default value is genuinely appropriate |
| `CASE WHEN ... THEN ... ELSE ... END` | Branch on business conditions | Can produce status labels such as `MISSING`, `INVALID`, `VALID` |
| `toIntegerOrNull(x)` | Attempt to convert a value to an integer, returning `null` on failure | Does not validate value range on its own; floats may have their fractional part truncated |
| `toFloatOrNull(x)` | Attempt to convert to a floating-point number | Does not replace unit or precision checks |
| `toBooleanOrNull(x)` | Attempt to convert to a boolean | Strings outside supported representations may return `null` |
| `toStringOrNull(x)` | Attempt to convert to a string | Stringification does not guarantee semantic correctness, especially for identifiers |
| `trim(x)`, `toLower(x)` | Normalize text | Should be applied after ensuring the input is suitable |
| `=~` | Match a string against a regular expression | Suitable for checking format before numeric casting |

The `*OrNull` functions help handle heterogeneous data sources, but **a `null` result after conversion can have two causes**: the input was missing in the first place, or the input had data that was invalid. You must preserve information about the input prior to conversion if the application needs to distinguish these two cases.

### Why Not Always Use `coalesce`?

~~~cypher
MATCH (p:Person)
RETURN p.externalId AS id,
       coalesce(p.ageRaw, 0) AS displayedAge;
~~~

The query above assigns age 0 even to people who have never declared an age. If `0` means “infant”, the displayed data is already wrong.

`coalesce` remains appropriate in **display** contexts, such as a fallback name when a nickname is absent:

~~~cypher
MATCH (p:Person)
RETURN p.externalId AS id,
       coalesce(p.nickname, p.fullName, '[No name]') AS displayName;
~~~

Distinguish UI display values from canonical data intended for storage, computation, reporting, and business decisions.

## 3. Normalizing Age with Format and Range Validation

Business assumptions:

- Age is an **integer from 0 to 120**.
- Inputs may be an integer or a digit string that may have leading/trailing whitespace.
- Do not silently round or truncate a decimal number.
- A missing property must have a different status from an invalidly entered value.

The following query keeps all nodes while producing two columns: data quality status and the normalized age when valid.

~~~cypher
MATCH (p:Person)
WITH p, trim(toStringOrNull(p.ageRaw)) AS ageText
WITH p, ageText,
     CASE
       WHEN ageText =~ '^[0-9]{1,3}$'
       THEN toIntegerOrNull(ageText)
       ELSE null
     END AS ageCandidate
RETURN p.externalId AS id,
       p.ageRaw AS rawAge,
       CASE
         WHEN p.ageRaw IS NULL THEN 'MISSING'
         WHEN ageCandidate IS NULL OR ageCandidate > 120 THEN 'INVALID'
         ELSE 'VALID'
       END AS status,
       CASE
         WHEN ageCandidate IS NOT NULL AND ageCandidate <= 120
         THEN ageCandidate
         ELSE null
       END AS normalizedAge;
~~~

Step-by-step explanation:

1. `toStringOrNull` creates a string representation when possible; `trim` removes leading and trailing whitespace. If conversion is not possible, `ageText` is `null`.
2. `=~ '^[0-9]{1,3}$'` accepts only one to three digits. The string `'27.5'` and the float `27.5` are not silently turned into `27`.
3. `toIntegerOrNull` runs only in the branch where the input format is valid; the result still needs to be checked against the `120` threshold.
4. The `MISSING` classification checks the original value first, and only then checks `INVALID`. Thus, undeclared users are not conflated with users who entered invalid data.

The format above is an **example convention**. A real system might disallow leading zeros, accept only native integer types, or allow higher ages; adjust the regular expression and value range to match that specification.

### Quick Test Without Creating Nodes

~~~cypher
WITH [
  {id: 'A', age: '27'},
  {id: 'B', age: '0'},
  {id: 'C', age: '27.5'},
  {id: 'D'},
  {id: 'E', age: 25.7},
  {id: 'F', age: 'abc'},
  {id: 'G', age: null}
] AS rows
UNWIND rows AS row
WITH row,
     'age' IN keys(row) AS fieldProvided,
     trim(toStringOrNull(row.age)) AS ageText
WITH row, fieldProvided,
     CASE WHEN ageText =~ '^[0-9]{1,3}$'
          THEN toIntegerOrNull(ageText)
          ELSE null
     END AS ageCandidate
RETURN row.id AS id,
       CASE
         WHEN NOT fieldProvided THEN 'FIELD_OMITTED'
         WHEN row.age IS NULL THEN 'NULL_PROVIDED'
         WHEN ageCandidate IS NULL OR ageCandidate > 120 THEN 'INVALID'
         ELSE 'VALID'
       END AS status,
       CASE WHEN ageCandidate <= 120 THEN ageCandidate END AS normalizedAge
ORDER BY id;
~~~

Expected outcome: `A → 27`, `B → 0`; `C`, `E`, and `F` have no normalized age due to invalid format; `D` is **field omitted**, whereas `G` is **field provided with a null value**. The difference between `D` and `G` is clearly visible on the **input map** thanks to `'age' IN keys(row)`.

Note: for **node properties**, Neo4j does not store `null` as a separate property value; however, for **maps received via parameters** (such as from the Java Driver), having a key with a `null` value can carry a different meaning from omitting the key. This is an important point when designing partial-update APIs.

## 4. Preserving Semantics When Updating Data

Consider an API receiving update maps from a Java application:

- Omitted `age`: keep the existing age.
- Sent `age: null`: delete age only if the API **explicitly specifies** that `null` is a delete request.
- Sent `age` with invalid data: return an error or route to a cleanup queue; do not overwrite.
- Sent valid `age`: store the normalized age.

Do not use expressions such as `coalesce(toIntegerOrNull(row.age), 0)` to write directly. That turns unprovided or wrong-type data into age 0. Similarly, `SET p.age = toIntegerOrNull(row.age)` will **delete the existing property** if the result is `null`.

If the task only requires “updating rows with a valid age”, you can filter **before SET**:

~~~cypher
UNWIND $rows AS row
WITH row, trim(toStringOrNull(row.age)) AS ageText
WITH row,
     CASE WHEN ageText =~ '^[0-9]{1,3}$'
          THEN toIntegerOrNull(ageText)
          ELSE null
     END AS ageCandidate
WHERE ageCandidate IS NOT NULL AND ageCandidate <= 120
MATCH (p:Person {externalId: row.externalId})
SET p.age = ageCandidate
RETURN count(DISTINCT p) AS updatedCount;
~~~

Here `$rows` is a list-of-maps parameter passed by the application. Invalid rows or rows without an age never reach `SET`; the stored ages of those nodes remain untouched. In a real application, collect and report rejected rows separately, because they do not appear in the update count above.

If the API supports intentional deletion, classify rows into `FIELD_OMITTED` / `NULL_PROVIDED` / `VALID` / `INVALID` first, then process each group according to confirmed rules. Never assume every `null` means a delete command.

## 5. Missing Data in Relationships and Aggregations

Missing values do not appear only in properties. `OPTIONAL MATCH` also produces rows where variables are `null` when no matching relationship is found.

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.customerId AS customer,
       count(o) AS orderCount,
       count(*) AS rowsAfterOptional
ORDER BY customer;
~~~

For a customer with no orders, `count(o)` equals **0** because expression counting ignores `null`, whereas `count(*)` equals **1** because `OPTIONAL MATCH` still keeps one row for that customer. Therefore, to count linked entities, use `count(o)` (or `count(DISTINCT o)` if the query pattern can produce duplicates).

Aggregations such as `sum(o.total)` ignore `null` values. However, **having no orders** and **having an order with a missing total amount** are two distinct business states. When building reports, you can track both the order count and the count of orders with a total:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.customerId AS customer,
       count(DISTINCT o) AS totalOrders,
       count(o.total) AS ordersWithTotal,
       sum(o.total) AS totalAmount;
~~~

Assumptions in this example: each `PLACED` relationship corresponds to one order, and `o.total` has a properly normalized numeric type. If an order can appear multiple times across different relationship patterns, review the aggregation so it does not double-count. Do not replace a missing order total with 0 unless the data source confirms it is genuinely a 0-value order.

### Filter Conditions and Three-Valued Logic

~~~cypher
MATCH (p:Person)
WHERE p.active = false
RETURN p.externalId;
~~~

This query returns only people whose `active` is `false`. Nodes missing `active` are not automatically treated as inactive: their comparison evaluates to `null` and does not pass `WHERE`. If you want to report the undetermined group as well, use `CASE` to produce `ACTIVE`, `INACTIVE`, and `UNKNOWN` statuses.

## 6. From Cypher to the Java Driver and Spring Data Neo4j

The same principle must be upheld at the application layer:

- **Java Driver:** queries should return both the normalized value and the quality status; check `Value.isNull()` before reading a potentially missing field, and avoid coercing `null` into a primitive type or defaulting to 0.
- **Spring Data Neo4j:** for nullable properties, represent them with reference types such as `Integer` or `Boolean` (instead of `int` / `boolean`) when the data domain needs to distinguish `null` from `0` / `false`.
- **Data ingestion:** record the raw value, validation status, and rejection reason at the appropriate processing step. Write only canonical data types to properties used for filtering, relationship linking, or calculations.
- **Query performance:** normalizing types at ingestion time lets you write predicates such as `WHERE p.age = 27` on the normalized property. Wrapping properties in conversion functions inside `WHERE` frequently makes it harder for the query to leverage an index optimally.

Example reading a potentially missing age value from the Java Driver:

~~~java
org.neo4j.driver.Value ageValue = record.get("normalizedAge");
Integer age = ageValue.isNull() ? null : ageValue.asInt();
~~~

The snippet above applies when the query already returns `normalizedAge` as an integer or `null`. If you only receive `age` without `status`, the Java layer still cannot tell why the age is missing: whether there was no source data or the source data was rejected due to an invalid format.

## 7. Common Mistakes

| Pattern / Practice | Risk | Alternative |
| --- | --- | --- |
| `p.age = null` | Comparison evaluates to `null`, does not determine whether missing | `p.age IS NULL` |
| Using `coalesce(p.age, 0)` for business data | Conflates “unknown” and “equal to 0” | Keep `null` and a separate status |
| Running `toIntegerOrNull(27.9)` and treating the result as a valid age | Can silently lose the fractional part | Check format/type and range before accepting |
| `SET p.age = toIntegerOrNull(row.age)` | Unconvertible values end up deleting the property | Only `SET` valid rows |
| Treating `false` or `''` as missing data | Discards values explicitly provided by the user | Define rules per property |
| Converting codes like `'00123'` to number 123 | Loses leading zeros, alters the identifier | Keep codes as strings; validate using code rules |
| Using `count(*)` to count optional nodes after `OPTIONAL MATCH` | Also counts rows where the linked variable is `null` | `count(o)` or `count(DISTINCT o)` |
| Conflating “field omitted” with “field sent as null” in payloads | Partial-update APIs may delete or overwrite data unintentionally | Check keys with `keys(map)` before deciding |

## 8. Workflow for Applying to Real-World Graph Data

1. **Define the semantics of each property:** what missing means, whether empty values are allowed, what the canonical type is, and what the valid range is.
2. **Read and classify inputs:** preserve information for “omitted”, “sent as null”, “invalid format”, “out of range”, and “valid” if the workflow needs to distinguish them.
3. **Normalize conditionally:** use `CASE`, `to*OrNull`, and format checks, avoiding conversions that lose business information.
4. **Decide updates:** write only validated values; delete only when an explicit delete request is defined; route invalid data to an inspection flow.
5. **Verify results:** re-query statuses and record counts, and test edge cases such as 0, `false`, empty strings, negative numbers, floats, and non-existent relationships.
6. **Stabilize the schema:** once the data is clean, apply constraints and indexes appropriate for your Neo4j version to reduce the chance of missing or malformed data recurring.

### Self-Check Questions

1. Why might `coalesce(p.age, 0)` be acceptable for a UI display yet wrong for an age report?
2. When processing `$rows` from the Java Driver, how do you distinguish a map without the `age` key from a map with `age: null`?
3. Why do you still need to check format and age range even when `toIntegerOrNull` returns a number?
4. With `OPTIONAL MATCH`, when should you use `count(o)` instead of `count(*)`?
5. If a `SET` clause receives `null`, what happens to an existing property on the node?

**Key takeaway:** in Cypher, a conversion expression or default value is only a technical operation. The accuracy of a property graph model depends on keeping clear semantics for **missing**, **invalid**, **intentionally deleted**, and **valid** values—from data ingestion through relationship queries to Java applications.
