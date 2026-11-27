# Null, Missing Data, Empty Values, and Default Values

## 1. Why must these four states be distinguished?

When designing a data model, a field with no content can carry several different meanings. An unknown value, an omitted field, an empty string, an empty list, and a default value may all look like “no data”, yet they express distinct states.

For example, a customer profile has a `middle_name` field:

- `NULL`: the system has no middle name value or the middle name is currently unknown.
- Field absent from a JSON document: the data sender did not supply this field, or the field does not belong to that data version.
- `""`: a string value exists and has length zero; the business may interpret this as the user intentionally leaving it blank.
- Default value, such as `"Not provided"`: the system automatically populates a value on profile creation according to a defined rule.

Collapsing these states into one can cause the system to accidentally delete data during updates, display wrong information, bypass input requirements, or generate inaccurate reports.

This lesson distinguishes four concepts:

1. **NULL:** a marker indicating that an attribute's value is absent or unknown per DBMS semantics.
2. **Missing/absent data:** the attribute is not supplied or does not exist in the record structure.
3. **Empty value:** a value exists yet contains no elements or characters, such as string `""`, array `[]`, or object `{}`.
4. **Default value:** a value chosen by the system when a write operation does not provide a value, according to a defined rule.

To model correctly, first define the business meaning of each state; only then choose data types, nullability, defaults, constraints, and API handling.

## 2. NULL in the relational data model

### 2.1. NULL indicates an absent or unknown value

In SQL, `NULL` is a special marker indicating missing data as interpreted by the DBMS. It is not the number 0, an empty string, the text string `"NULL"`, or an ordinary value comparable with the equality operator.

For example, an employee table may allow an undetermined termination date:

```sql
CREATE TABLE employee (
    employee_id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    terminated_at TIMESTAMP NULL
);
```

If an employee is still active or has no termination date yet, `terminated_at` can be `NULL` by model convention.

However, NULL does not by itself state why no value is present. It may be used for different situations:

- Value unknown.
- Value not yet collected.
- Not applicable to this object.
- Value hidden or not permitted to be provided.
- Value not yet determined at recording time.

If these reasons have different business meanings, a single nullable column is not enough to express them. Add a status or explanatory attribute.

### 2.2. NULL does not equal NULL

In SQL, ordinary comparisons with NULL usually yield UNKNOWN, even when comparing NULL to NULL:

```sql
SELECT NULL = NULL;       -- UNKNOWN
SELECT NULL <> 10;        -- UNKNOWN
SELECT NULL = 10;         -- UNKNOWN
```

Therefore, never use `column = NULL` to find records lacking a value. Instead use:

```sql
SELECT *
FROM employee
WHERE terminated_at IS NULL;
```

And to find populated values:

```sql
SELECT *
FROM employee
WHERE terminated_at IS NOT NULL;
```

Some DBMSs provide NULL-safe comparison operators such as `IS DISTINCT FROM` or `IS NOT DISTINCT FROM`. Syntax and support vary by engine. In PostgreSQL, for example:

```sql
SELECT NULL IS NOT DISTINCT FROM NULL; -- TRUE
SELECT 10 IS DISTINCT FROM NULL;       -- TRUE
```

This operator is useful when comparing two values while treating two NULLs as equivalent under a chosen rule.

### 2.3. Three-valued logic: TRUE, FALSE, and UNKNOWN

SQL conditions can evaluate to three states:

- **TRUE:** condition confirmed true.
- **FALSE:** condition confirmed false.
- **UNKNOWN:** insufficient information to conclude due to NULL.

Example:

```sql
SELECT *
FROM employee
WHERE terminated_at > CURRENT_TIMESTAMP;
```

If `terminated_at` is NULL, the comparison expression returns neither TRUE nor FALSE, but UNKNOWN. The WHERE clause retains only rows where the condition is TRUE, so that row is not returned.

Common rules:

| Expression | Result with NULL |
|---|---|
| `NULL = 5` | UNKNOWN |
| `NULL <> 5` | UNKNOWN |
| `NOT UNKNOWN` | UNKNOWN |
| `TRUE AND UNKNOWN` | UNKNOWN |
| `FALSE AND UNKNOWN` | FALSE |
| `TRUE OR UNKNOWN` | TRUE |
| `FALSE OR UNKNOWN` | UNKNOWN |

This is why a filter condition can drop rows that a query author did not expect. When designing queries, define explicitly how unknown values are handled rather than assuming NULL behaves like an ordinary value.

### 2.4. Aggregate functions and NULL

Many aggregate functions ignore NULL:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(discount_amount) AS known_discount_count,
    AVG(discount_amount) AS average_discount
FROM order_line;
```

- `COUNT(*)` counts all rows.
- `COUNT(discount_amount)` counts only rows where `discount_amount` is not NULL.
- `AVG(discount_amount)` averages only non-NULL values.

This can create substantial differences in reports. If NULL means “not yet calculated”, ignoring NULL may be appropriate. If NULL means “no discount”, ignoring it can skew the average relative to business intent; in that case, store 0 or convert intentionally.

Do not use `COALESCE(discount_amount, 0)` merely to avoid NULL without confirming its meaning. `COALESCE` returns the first non-NULL value, yet replacing NULL with 0 can turn “unknown” into “confirmed none”.

## 3. Missing/absent data

### 3.1. Attribute does not appear in a record

In some document models or JSON data, an attribute may not appear at all. For example:

```json
{
  "customerId": 1001,
  "fullName": "Mai Nguyen"
}
```

Here, `middleName` does not exist in the document. That differs from:

```json
{
  "customerId": 1001,
  "fullName": "Mai Nguyen",
  "middleName": null
}
```

In the second document, the field is present and carries a null value under JSON semantics.

The difference can matter:

- Missing: sender omitted the field, field not yet collected, or the schema version lacks this attribute.
- Null: sender intentionally expressed that the value is absent or undetermined.
- Populated value: sender supplied concrete information.

Not every document database handles missing and null identically in queries, indexes, or constraints. Understand the semantics of your chosen technology.

### 3.2. Missing in partial updates

Missing is especially critical in update APIs. Suppose the current profile has:

```json
{
  "customerId": 1001,
  "email": "mai@example.test",
  "phone": "+84912345678"
}
```

An update request sends only:

```json
{
  "email": "mai.new@example.test"
}
```

If the API is defined as a partial update (PATCH), omitting `phone` usually means keeping the existing phone number unchanged.

If the request sends:

```json
{
  "email": "mai.new@example.test",
  "phone": null
}
```

then `phone: null` may mean clearing the phone number or setting it to unknown, depending on the API contract.

If the request sends:

```json
{
  "email": "mai.new@example.test",
  "phone": ""
}
```

then this is an empty string value; the API must decide whether it is valid, converted to NULL, or rejected.

Do not treat these three cases identically. An update handler must inspect both whether an attribute is present in the payload and what its value is.

### 3.3. Missing is not necessarily an error

An attribute can validly be absent if:

- The attribute is optional.
- Data has not yet been collected.
- The attribute does not apply to that entity subtype.
- The record was created under an older schema version.
- The sender lacks permission or a data source for the attribute.

Conversely, missing is an error if the field is required by business rules or an interface contract. Thus, distinguish “optional” from “required yet omitted”.

## 4. Empty values

### 4.1. Empty string differs from NULL

An empty string `''` is a string of length 0. It is still a string value:

```sql
SELECT
    LENGTH('') AS empty_length,
    LENGTH('abc') AS text_length;
```

In many DBMSs, an empty string differs from NULL. For example, in PostgreSQL:

```sql
SELECT '' IS NULL;  -- FALSE
SELECT NULL IS NULL; -- TRUE
```

This means a `VARCHAR NOT NULL` column can still contain an empty string unless an additional constraint checks length or content.

For example, if an SKU code must not be empty:

```sql
CREATE TABLE product (
    product_id BIGINT PRIMARY KEY,
    sku VARCHAR(50) NOT NULL CHECK (LENGTH(TRIM(sku)) > 0)
);
```

`NOT NULL` only prevents NULL; it does not by itself prevent empty strings or whitespace-only strings.

**DBMS note:** Oracle Database treats zero-length character strings in character types as NULL in many SQL contexts. Therefore, do not assume every engine distinguishes `''` and NULL the same way. Check your target DBMS semantics.

### 4.2. Empty arrays and NULL

For list-valued fields, an empty array `[]` means the list is known and currently has no elements. NULL can mean the list is unknown, not yet loaded, or not applicable.

Document example:

```json
{
  "customerId": 1001,
  "tags": []
}
```

Differs from:

```json
{
  "customerId": 1001,
  "tags": null
}
```

And differs from omitting `tags`:

```json
{
  "customerId": 1001
}
```

The three states can be interpreted as follows:

| State | Possible meaning |
|---|---|
| `tags: []` | List is known and currently has no tags |
| `tags: null` | List is unknown or not applicable |
| `tags` absent | Not provided or field does not exist in this document version |

If the business does not need to distinguish these cases, they can be normalized to a single representation. However, if “confirmed no tags” must differ from “tags not yet loaded”, preserve that distinction.

### 4.3. Empty objects and absent objects

An empty JSON object `{}` is an object that exists yet has no child properties:

```json
{
  "address": {}
}
```

This differs from `"address": null` or omitting the `address` field. An empty object might mean an address profile was initialized with no components yet; null might mean no address; missing might mean information not provided yet.

If a document model allows nested structures, specify the meaning of empty objects, null objects, and omitted objects.

## 5. Default values

### 5.1. Default is a rule supplying a value on write

A default value is a value used by the system when a write operation omits a value, as defined by the schema or application.

SQL example:

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

If an INSERT omits `status` and `created_at`, the DBMS applies the defaults:

```sql
INSERT INTO orders (order_id)
VALUES (7001);
```

The result will have `status = 'PENDING'` and `created_at` assigned the current timestamp per engine semantics.

### 5.2. Default does not automatically replace an explicitly sent NULL

A common misunderstanding: SQL DEFAULT is usually applied when a column is omitted in an INSERT or when using the `DEFAULT` keyword, not when NULL is explicitly supplied.

Example:

```sql
INSERT INTO orders (order_id, status)
VALUES (7002, NULL);
```

Because `status` is declared `NOT NULL`, the statement above violates the constraint. The `'PENDING'` default does not automatically replace NULL.

To ask the DBMS to use the default, write:

```sql
INSERT INTO orders (order_id, status)
VALUES (7003, DEFAULT);
```

Exact rules can differ by DBMS, yet never assume NULL and DEFAULT are the same.

### 5.3. Default differs from a user-chosen value

Suppose `status` defaults to `'PENDING'`. When a record is created without the user specifying a status, the system can apply the default. However, if the user explicitly chooses `'CANCELLED'`, the system must save that choice.

If the application automatically replaces every empty or NULL value with `'PENDING'`, it can overwrite user intent. Explicitly define each case:

- Field omitted: use default or report missing?
- NULL sent: allow, reject, or convert to default?
- Empty string sent: save empty or reject?
- Concrete value sent: save that value if valid?

### 5.4. Defaults on UPDATE

A default does not re-run automatically whenever a row is updated. For example, if `status` is already `'SHIPPED'`, an UPDATE statement that does not mention `status` leaves that value unchanged.

To reset to default, use `SET status = DEFAULT` if the DBMS supports it:

```sql
UPDATE orders
SET status = DEFAULT
WHERE order_id = 7001;
```

Some applications apply defaults when instantiating objects or deserializing payloads. That is application-layer behavior and should be distinguished from database-enforced defaults.

### 5.5. Defaults are not always appropriate

Defaults are useful when there is a clear, safe initial value, for example:

- New order status is `PENDING`.
- Creation timestamp is recording time.
- Initial retry count is 0.
- Toggle flag has a business-agreed initial value.

Do not use defaults to hide missing required data. For example, auto-filling `'Unknown'` for customer name creates fake data, corrupts reports, and misleads the system into thinking a name was collected.

## 6. Comparing the four states

| State | Relational SQL | JSON/document | Typical meaning |
|---|---|---|---|
| NULL | `NULL` | `"field": null` | Explicit marker indicating absent/unknown |
| Missing | No concept of a missing column in a standard relational row; the column still exists and may be NULL | Property absent | Not provided or does not exist in document structure |
| Empty | `''`, empty array if type supports it | `""`, `[]`, `{}` | Value exists yet contains zero characters/elements/properties |
| Default | `DEFAULT` or omit column in INSERT | Applied by schema, ODM, or application | Initial value assigned by rule |

Note: in a relational table, every row has the same set of columns defined by the schema. Therefore, a “missing column” is not the same as a missing property in a document. A relational row normally represents an unpopulated value with NULL, whereas a column not existing is a schema change rather than a per-row state.

## 7. Designing optional and required attributes

### 7.1. Determining whether an attribute is required

Before declaring NULL or NOT NULL, ask:

- Is the value required to complete the business operation?
- Can the entity be created before this value is known?
- Might the value not apply to some entity subtypes?
- Can the value be added later?
- Does a missing value affect reports, access control, or downstream workflows?

Example:

```sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(320),
    middle_name VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

- `full_name` is required.
- `email` and `middle_name` can be NULL in this illustrative model.
- `created_at` is required and defaulted upon creation.

If email is mandatory for registration, change it to NOT NULL and optionally enforce verification in the business layer. Do not leave it nullable simply because some legacy imported records are missing values without defining a migration policy.

### 7.2. Distinguishing unknown, not applicable, and not yet collected

If the business must distinguish multiple reasons for absence, add a status field:

```sql
CREATE TABLE customer_profile (
    customer_id BIGINT PRIMARY KEY,
    middle_name VARCHAR(100),
    middle_name_status VARCHAR(20) NOT NULL,
    CHECK (
        middle_name_status IN (
            'KNOWN',
            'NOT_PROVIDED',
            'NOT_APPLICABLE',
            'NOT_COLLECTED'
        )
    )
);
```

This model shows why a middle name is absent. However, add constraints or application rules to keep status and value consistent. For example, `KNOWN` must accompany a valid value; `NOT_APPLICABLE` may require a NULL value.

Do not create excessive status columns if the business does not use them. Model only distinctions meaningful for decisions or reporting.

### 7.3. Avoiding sentinel values

A sentinel value is a special value used in place of a missing state, such as:

- `0` to indicate unknown quantity.
- `-1` to indicate no ID.
- `1900-01-01` to indicate unknown date.
- `'N/A'` or `'UNKNOWN'` to indicate a missing string.

This approach causes bugs because sentinel values remain ordinary data values of that type. They can participate in calculations, sorting, filtering, or reports as if they were real values.

Use NULL, a dedicated status, or a structure matching the semantics. Use a sentinel only when it is genuinely a valid, well-defined business value.

## 8. NULL, missing, and defaults in APIs

### 8.1. Distinguishing POST, PUT, and PATCH

APIs must explicitly specify the meaning of omitted fields and sent NULLs.

A common contract:

| Payload | Possible defined meaning |
|---|---|
| POST omits a field with a default | Create record and apply default |
| POST omits a required field | Reject due to missing data |
| PATCH omits a field | Keep current value unchanged |
| PATCH sends `null` | Clear value or set to unknown |
| PATCH sends `""` | Set empty string if allowed |
| PUT omits a field | May represent full replacement; explicitly define whether omitted values are cleared or defaulted |

No single semantics governs all APIs. Contracts must state behavior explicitly, especially when old and new clients coexist.

### 8.2. Example of PATCH handling

Suppose a profile has `displayName` and `phone`. A PATCH request sends only `displayName`:

```json
{
  "displayName": "Mai Nguyen"
}
```

The system keeps `phone` unchanged.

If it sends:

```json
{
  "displayName": "Mai Nguyen",
  "phone": null
}
```

The system clears `phone` or sets it to unknown per the contract.

If it sends:

```json
{
  "displayName": "Mai Nguyen",
  "phone": ""
}
```

The system must check whether empty strings are permitted.

In code, inspect whether the property is present in the payload before reading its value. If deserialization turns every absent field into null, the system cannot distinguish “do not update field” from “clear value”.

### 8.3. API defaults and database defaults

An application may apply defaults before issuing INSERT while the database also has its own defaults. If the two diverge, results become inconsistent.

For example, the database defaults `status = 'PENDING'`, while the application defaults `status = 'NEW'`. Different write paths can produce different statuses depending on whether the column is included.

Designate a single authoritative source for each default. You can keep database defaults to protect direct write paths while the application follows the exact same rule for consistent responses. Keep schema and API documentation synchronized.

## 9. Impact on queries, constraints, and indexes

### 9.1. NOT NULL and CHECK

`NOT NULL` blocks NULL values yet does not prevent empty strings on its own:

```sql
CREATE TABLE category (
    category_id BIGINT PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL
        CHECK (LENGTH(TRIM(category_name)) > 0)
);
```

Important note: in SQL, CHECK typically rejects a row only when the expression evaluates to FALSE; an UNKNOWN result from NULL may not count as a violation. Therefore, if a field must have a value, combine `NOT NULL` with an appropriate CHECK constraint.

For example, `CHECK (quantity > 0)` does not necessarily prevent NULL if the column remains nullable. Declare:

```sql
quantity INTEGER NOT NULL CHECK (quantity > 0)
```

### 9.2. UNIQUE and NULL

How a unique constraint handles multiple NULLs depends on the DBMS and options. Some engines allow multiple NULL rows in a unique column; other engines or syntax support `NULLS NOT DISTINCT` semantics.

If the business requires every row to have a unique non-missing value, combine both `NOT NULL` and `UNIQUE`. If NULL is allowed, clarify whether multiple records lacking a value are permitted.

### 9.3. Querying for missing data

Use `IS NULL` to find absent values:

```sql
SELECT customer_id
FROM customer
WHERE email IS NULL;
```

To find empty or whitespace-only strings:

```sql
SELECT customer_id
FROM customer
WHERE email = ''
   OR TRIM(email) = '';
```

Length, trim, and string functions vary in syntax across engines. In systems with multiple data sources, profile NULL, empty strings, whitespace-only strings, and absent document fields separately to understand data quality.

## 10. Migrating schemas and data when semantics change

When changing an attribute from nullable to NOT NULL or adding a default, inspect existing data.

A safe workflow typically includes:

1. Count existing rows with NULL, empty strings, and sentinel values.
2. Confirm with the business which replacement value is valid.
3. Determine whether the default truly represents historical data or applies only to new records.
4. Backfill old data according to approved rules.
5. Verify no violating records remain.
6. Add the constraint or change nullability.
7. Update APIs, applications, ETL pipelines, and documentation.
8. Monitor errors from older clients still sending payloads under previous semantics.

Do not blindly replace all NULLs with empty strings or default values. For instance, turning every `email IS NULL` into `'unknown@example.test'` fabricates a fake value that may be treated as a real email and violate unique constraints.

A new default normally applies to new writes after the schema change. It does not automatically backfill existing rows unless an explicit backfill operation or specific migration syntax is executed.

## 11. Comprehensive example: product profile

Suppose a product has attributes `description`, `tags`, `weight`, and `status`.

| Field | State | Meaning |
|---|---|---|
| `description = NULL` | NULL | Description unknown or not yet available |
| `description` absent in document | Missing | Sender omitted it or legacy schema lacked the field |
| `description = ""` | Empty string | Description was provided as empty |
| `tags = []` | Empty collection | Confirmed product has no tags |
| `tags = null` | NULL | Tag list unknown or not applicable |
| `tags` absent | Missing | Tag field not supplied |
| `weight = 0` | Numeric value | Weight is 0 in the chosen unit; valid only if business permits |
| `status` omitted on creation | Default | Applies default status, e.g., `DRAFT` |
| `status = null` | Explicit NULL | Rejected if status is NOT NULL |

An illustrative document:

```json
{
  "productId": "P-100",
  "description": "",
  "tags": [],
  "weight": null,
  "status": "DRAFT"
}
```

Here, description was supplied as empty; the tag list is confirmed empty; weight is absent; status was explicitly set. If the document omits `weight`, the system may interpret it as weight not yet sent. Whether those last two cases differ must be defined by the data contract.

## 12. Process for defining semantics per attribute

For every attribute in the model, answer in order:

1. **Is it required?** If required, define the conditions and when it becomes mandatory.
2. **When no value is present, what is the reason?** Unknown, not applicable, not yet collected, hidden, or intentionally cleared by the user?
3. **Does a missing state exist?** Especially in documents, events, and partial-update APIs.
4. **Are empty values valid?** Define rules separately for strings, arrays, objects, and sets.
5. **Is there a default?** Identify whether the database, application, or data source supplies it.
6. **Is NULL permitted?** If so, describe its meaning and how to query it.
7. **Which constraints are needed?** NOT NULL, CHECK, UNIQUE, length, value domain, or cross-field rules.
8. **What happens on update?** Missing preserves, NULL clears, empty sets empty, or other semantics?
9. **What happens on sync and ingestion?** Preserve the distinction among omitted field, NULL, and empty value from the source.
10. **What happens in reporting?** Define how counting, averaging, filtering, and NULL substitution behave if needed.

Record these answers in the data dictionary or schema contract so authors of APIs, ETL jobs, reports, and queries share one understanding.

## 13. Common mistakes

- Treating NULL, empty string, zero, and missing field as the same state.
- Using `= NULL` instead of `IS NULL`.
- Assuming `NOT NULL` automatically prevents empty strings.
- Assuming SQL DEFAULT replaces an explicitly supplied NULL.
- Turning every missing value into 0 or `"N/A"` without confirming meaning.
- Failing to distinguish missing from null in PATCH payloads.
- Overwriting existing data with NULL when a client merely omits a field.
- Letting application defaults and database defaults diverge.
- Assuming all DBMSs treat empty strings and NULL identically.
- Failing to consider how COUNT, AVG, SUM, and CHECK handle NULL.
- Adding NOT NULL to a schema without backfilling and checking historical data.
- Leaving unclear whether an empty array means “confirmed no elements” or “data not yet loaded”.

## 14. Verification checklist

Before finalizing attribute modeling, confirm:

- [ ] Distinguished NULL, missing, empty, and default.
- [ ] Business meaning of NULL explicitly documented.
- [ ] Determined whether each attribute is required or optional.
- [ ] Empty strings, whitespace, empty arrays, and empty objects have clear semantics.
- [ ] Defaults applied at the right layer and time.
- [ ] Behavior defined when INSERT omits a column, sends NULL, or sends DEFAULT.
- [ ] Behavior defined when UPDATE/PATCH omits a field, sends NULL, or sends empty.
- [ ] Queries use IS NULL/IS NOT NULL and account for three-valued logic.
- [ ] CHECK, NOT NULL, and UNIQUE combined properly.
- [ ] DBMS differences, especially around empty strings and NULL, verified.
- [ ] Migrations include a backfill plan and historical data checks.
- [ ] APIs, ETL, reports, and database share unified semantics.

Clearly distinguishing NULL, missing data, empty values, and default values ensures the data model preserves information meaning across creation, updates, synchronization, and analytics. When every state has a consistent definition, the system avoids turning “unknown” into “none”, or turning “omitted” into “delete data”.
