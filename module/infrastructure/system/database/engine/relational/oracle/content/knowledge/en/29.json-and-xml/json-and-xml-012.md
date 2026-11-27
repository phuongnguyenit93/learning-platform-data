# Designing JSON/XML Contracts, Size Limits, and Invalid Data Handling

JSON and XML are two widely used formats for exchanging data between applications, services, and Oracle Database. A payload can be syntactically valid yet violate the business contract: missing required fields, wrong types, out-of-range values, excessively deep nesting, too many elements, or sizes beyond processing capacity. Therefore, designing JSON/XML is not just about choosing field and tag names; you must define schemas, versioning, null/missing rules, encoding, resource limits, validation, and error handling for invalid data.

A solid data contract clarifies what is sent, what is received, the types and value ranges of each field, compatible evolution rules, maximum sizes, and responses when a payload is invalid. Oracle provides data types and SQL operators to store, query, generate, and validate JSON/XML; applications still need validation workflows and resource limits before admitting payloads into the main processing pipeline.

After this lesson, you will be able to:

- Design JSON/XML contracts with schemas, versions, and compatibility rules.
- Distinguish missing fields, JSON null, empty strings, and default values.
- Validate JSON/XML syntax and validate data against schemas and business rules.
- Understand the JSON datatype, IS JSON, JSON_VALUE, JSON_EXISTS, JSON_TABLE, and XMLType.
- Handle XML namespaces, XML Schema, and XMLTABLE.
- Enforce limits on payload size, nesting depth, element count, string length, and byte count.
- Choose appropriately among VARCHAR2, CLOB, BLOB, JSON, or XMLType.
- Detect duplicate JSON keys, invalid encodings, invalid numbers/dates, and malformed data.
- Classify syntax errors, schema errors, business errors, and resource errors.
- Design reject/quarantine flows, logging, retries, and idempotency.
- Mitigate parser abuse, XML external entity (XXE) risks, and malicious payloads.
- Build a lab to test contracts and invalid payload handling in Oracle.

> The JSON datatype and certain SQL/JSON syntax depend on the Oracle release. Oracle Database 21c introduced the native JSON data type in binary JSON form; earlier releases typically store JSON in VARCHAR2/CLOB/BLOB with an IS JSON constraint. Always verify the Oracle SQL Language Reference for your exact release, compatibility setting, and client driver.

## 1. What Is a Data Contract?

### 1.1. Contracts Describe Structure and Semantics

A data contract defines how two systems exchange data. A contract does more than list field names; at a minimum it specifies:

- Names and meanings of each field.
- Data types and valid value domains.
- Required, optional, or nullable fields.
- Format rules for dates/times, numbers, currency, identifiers, and enums.
- Object/array nesting rules and cardinality.
- Contract version and compatibility policy.
- Size and resource limits.
- Handling of unknown fields, duplicate fields, or invalid data.
- Error codes, correlation IDs, and retry behavior.

Example order contract:

```json
{
  "schemaVersion": "1.0",
  "orderId": "ORD-2026-000123",
  "createdAt": "2026-11-14T08:30:00Z",
  "currency": "VND",
  "items": [
    {
      "sku": "KB-001",
      "quantity": 2,
      "unitPrice": 450000
    }
  ]
}
```

The contract must state that orderId is required and specify its uniqueness scope; whether createdAt must be a UTC timestamp or accepts offsets; that quantity is a positive integer; what precision/scale unitPrice uses; and whether items may be empty or must contain at least one element.

### 1.2. Valid Syntax Is Not Enough

The following payload is syntactically valid JSON:

```json
{
  "orderId": 123,
  "createdAt": "yesterday",
  "items": "keyboard"
}
```

However, if the contract requires orderId to be a string, createdAt to be an ISO-8601 timestamp, and items to be an array, this payload violates the contract.

Distinguish four validation layers:

| Layer | Question | Example |
| --- | --- | --- |
| Syntax | Can it be parsed? | JSON missing a comma |
| Structure/schema | Does it match the expected shape and types? | items must be an array |
| Domain/business | Are values valid under business rules? | quantity must be greater than 0 |
| Operational/resource | Is it within system limits? | 200 MB payload when the limit is 10 MB |

A payload must pass all required layers before being accepted.

### 1.3. The Contract Is the Boundary Between Producer and Consumer

The producer creates data; the consumer reads and processes it. Both sides may release versions independently. The contract clarifies:

- Which fields is the producer allowed to add?
- Does the consumer ignore unknown fields?
- Is the consumer required to understand schemaVersion?
- When changing a field's type or meaning, is a new version required?
- How long must older data versions remain readable?
- Who is responsible for validating and returning errors?

Never let a contract exist only inside one service's code. Store schemas/specifications in source control, review changes, and maintain compatibility tests.

## 2. Choosing JSON or XML

### 2.1. JSON

JSON usually fits web APIs, event messages, and object/array data. Its structure is concise, native to JavaScript, and supported in Oracle via SQL/JSON operators.

Advantages:

- Lightweight, readable syntax for objects/arrays.
- Supports string, number, boolean, null, object, and array.
- Well suited for REST APIs and event payloads.
- Oracle offers a native JSON datatype in modern releases and SQL/JSON functions.

Limitations:

- No comments in standard JSON.
- No dedicated date type; dates/times are typically expressed as strings per contract.
- Numbers do not carry business precision/scale metadata inherently.
- Rules for duplicate object keys must be specified and strictly enforced.

### 2.2. XML

XML fits structured documents, namespaces, schema validation, enterprise/SOAP systems, and certain industry exchange standards.

Advantages:

- XML Schema (XSD) describes elements, attributes, types, and cardinality.
- Namespaces separate vocabularies cleanly.
- Can represent document-centric and mixed content.
- Oracle XML DB supports XMLType, XMLQuery, XMLExists, and XMLTable.

Limitations:

- More verbose than JSON.
- Namespaces and schemas can complicate queries.
- Requires controlling DTDs/external entities and parser resources.
- Encoding/character sets and whitespace handling must be explicitly defined.

### 2.3. Choosing Based on Contract and Ecosystem

| Criterion | JSON | XML |
| --- | --- | --- |
| Modern web APIs | Usually convenient | Used when APIs/standards mandate it |
| Schema | JSON Schema commonly used at the app tier; Oracle supports SQL/JSON checks and dedicated mechanisms | Standardized XSD with XML DB integration |
| Namespaces | No standard namespaces | Built-in namespaces |
| Document/mixed content | More limited | Strong |
| SQL in Oracle | JSON datatype, SQL/JSON | XMLType, XQuery/XMLTABLE |
| Size | Typically compact | Typically verbose |
| Parser security | Control parser, depth, and size | Additionally guard against XXE/entity expansion |

The format alone does not determine contract quality. JSON can be tightly specified; XML can be loose if schemas and validation are absent.

## 3. Designing Versioning and Compatibility

### 3.1. Including Version in the Contract

You can use an explicit field:

```json
{
  "schemaVersion": "2.1",
  "eventType": "OrderCreated",
  "eventId": "evt-8f1c",
  "payload": {}
}
```

Or use a media type/version in HTTP headers or topic/event metadata. What matters is that the consumer can determine the version before interpreting the payload.

### 3.2. Typically Compatible Changes

Under a contract convention where consumers ignore unknown fields:

- Adding an optional field is usually backward compatible.
- Adding an enum value can break old consumers if their code only accepts a closed list.
- Adding a required field usually breaks old consumers.
- Renaming a field, deleting a field, or changing its type is typically a breaking change.
- Changing units or field semantics—even while keeping the same type—is also a breaking change.

For example, changing amount from VND to USD is a semantic breaking change even though the JSON remains valid.

### 3.3. Forward and Backward Compatibility

- Backward compatible: a new consumer can read payloads produced by an old producer.
- Forward compatible: an old consumer can still process payloads produced by a new producer.

Both properties depend on conventions for unknown fields, required/optional fields, and enums. Never declare a change compatible solely because the schema parser still parses it.

### 3.4. Release Rules

Define clearly:

1. When to bump a minor version versus a major version.
2. Support window for older versions.
3. Deprecation policy and sunset date.
4. Consumer contract testing before producer release.
5. How to handle payloads missing a schema version or carrying an unsupported version.
6. How to retain raw payloads for investigation within allowed retention windows.

### 3.5. Do Not Use Field Order as Versioning

JSON objects should not depend on key ordering. XML elements may have XSD ordering, but never use field arrangement as a versioning mechanism. Use an explicit version.

## 4. Required, Optional, Missing, Null, and Empty

### 4.1. Distinct States

In JSON, the following states are not identical:

```json
{}
```

```json
{"middleName": null}
```

```json
{"middleName": ""}
```

```json
{"middleName": " "}
```

- Missing: field does not appear.
- Null: field appears with value JSON null.
- Empty string: field is a zero-length string.
- Whitespace string: field contains whitespace characters.

The contract must specify how each state is interpreted. For example, missing may mean leave the current value unchanged in PATCH; null means clear the value; empty string may be accepted as an empty value or rejected.

### 4.2. SQL NULL and JSON null

SQL NULL is the null state of a SQL column/expression. JSON null is the null value inside a JSON document. When using SQL/JSON functions, how JSON null, missing paths, and SQL NULL map to one another depends on the function and its ON EMPTY/ON ERROR clauses.

Do not assume a missing field and a field with JSON null share the same meaning. Use JSON_EXISTS to test whether a field exists; use JSON_VALUE with explicit null/error rules to extract scalar values.

### 4.3. Empty Strings in Oracle SQL

In Oracle SQL, an empty character string is treated as NULL for standard character types. This can erase the distinction between an empty string and SQL NULL when projecting JSON/XML data into VARCHAR2. If preserving that distinction is critical, keep the raw JSON/XML or use an explicit representation rule and test round-trips.

### 4.4. PATCH Semantics

A PATCH contract may define:

| Input | Update Meaning |
| --- | --- |
| Field missing | Keep the current value unchanged |
| Field has value | Replace with the submitted value |
| Field is null | Clear the value if the field is nullable |
| Field is empty string | Reject or store empty value per rules |

If left unspecified, producer and consumer may interpret these differently, causing unintended data deletion.

### 4.5. Default Values

Defaults should be defined in one authoritative place. Do not have the producer default to 0 while the consumer defaults to NULL. If a missing field is replaced by a default, clarify whether it is resolved at ingestion time or dynamically from current configuration.

## 5. Defining Types and Value Domains

### 5.1. Numbers

JSON numbers do not distinguish integer from decimal as separate SQL types. The contract must state:

- Integer or decimal.
- Precision and scale.
- Min/max bounds.
- Whether negative numbers are allowed.
- Whether exponent notation is allowed.
- Rounding rules.
- Currency/measurement units.

Currency example:

```json
{
  "currency": "VND",
  "amount": 1250000.00
}
```

Do not transmit money using floating-point types if binary rounding errors can occur; use decimal types in the application tier and NUMBER with appropriate precision/scale in Oracle. Avoid passing large numbers through JavaScript `Number` if they exceed binary64 exact integer limits; consider decimal strings per contract.

### 5.2. Dates and Timestamps

JSON has no date/time primitive. Specify an explicit format such as RFC 3339/ISO-8601:

```json
{
  "createdAt": "2026-11-14T08:30:00Z",
  "localDate": "2026-11-14"
}
```

Distinguish:

- DATE: calendar date, no time component.
- Local date-time: local clock time without offset.
- Timestamp with offset: instant with explicit offset.
- UTC instant: standardized UTC instant.

Never omit timezones when the meaning is a point in time. In Oracle, choose DATE, TIMESTAMP, or TIMESTAMP WITH TIME ZONE per contract; parse with an explicit format mask rather than relying on NLS_DATE_FORMAT.

### 5.3. Booleans and Enums

The contract must state that booleans accept only true/false—not "true", 1, or "Y"—unless a mapping rule exists. Enums should have an unknown-value policy: reject, map to UNKNOWN, or preserve the string for forward compatibility.

### 5.4. Identifiers

Business code IDs should usually be strings to preserve leading zeros, hyphens, and avoid numeric precision limits. Do not use JSON numbers for account numbers or order IDs when they carry no arithmetic meaning.

### 5.5. Array Cardinality

For every array, specify:

- Min items and max items.
- Whether duplicate items are allowed.
- Whether element order is meaningful.
- Whether an empty array is permitted.
- Which unique key identifies each element.

For example, items has at most 500 elements and sku cannot repeat within an order. This is a schema/business rule that must be explicitly checked.

## 6. Designing JSON Contracts

### 6.1. Objects and Arrays

Objects represent entities with named fields; arrays represent ordered lists. Do not use dynamic object keys to represent lists when consumers need to iterate elements and validate cardinality.

Example:

```json
{
  "customer": {
    "customerId": "C-100",
    "name": "Nguyen An"
  },
  "addresses": [
    {
      "type": "BILLING",
      "countryCode": "VN"
    },
    {
      "type": "SHIPPING",
      "countryCode": "VN"
    }
  ]
}
```

### 6.2. Field Naming Conventions

Pick one consistent convention such as camelCase or snake_case. Do not change conventions across endpoints. Field names should be descriptive, avoid cryptic abbreviations, and avoid SQL reserved words if mapped directly to SQL columns.

### 6.3. Do Not Mix Multiple Types in One Field

Avoid contracts where customerId is sometimes a number and sometimes a string. Consumers end up guessing types. If an identifier format changes, release a new version or a new field with a clear migration path.

### 6.4. Separating Metadata from Business Payload

An envelope may contain:

```json
{
  "schemaVersion": "1.0",
  "eventId": "evt-123",
  "eventType": "DocumentUploaded",
  "occurredAt": "2026-11-14T08:30:00Z",
  "correlationId": "corr-456",
  "payload": {
    "documentId": "DOC-100",
    "fileName": "manual.pdf"
  }
}
```

Metadata supports routing, deduplication, tracing, and versioning. Never place credentials, secrets, or authentication tokens inside payloads or logs.

### 6.5. JSON Schema at the Contract Layer

JSON Schema is commonly used at the API gateway or application layer to specify types, required properties, enums, patterns, min/max, array cardinality, and nested structures. Example:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["schemaVersion", "orderId", "items"],
  "additionalProperties": false,
  "properties": {
    "schemaVersion": {"type": "string", "const": "1.0"},
    "orderId": {"type": "string", "minLength": 1, "maxLength": 40},
    "items": {
      "type": "array",
      "minItems": 1,
      "maxItems": 500,
      "items": {
        "type": "object",
        "required": ["sku", "quantity"],
        "properties": {
          "sku": {"type": "string", "maxLength": 40},
          "quantity": {"type": "integer", "minimum": 1}
        },
        "additionalProperties": false
      }
    }
  }
}
```

This is a contract-layer JSON Schema example; do not assume every Oracle release provides built-in SQL functions enforcing this exact JSON Schema draft directly. Oracle SQL/JSON validates syntax and extracts/checks specific types; full schema validation may live in the application/gateway or a dedicated supported mechanism.

## 7. Enforcing JSON Controls in Oracle Database

### 7.1. Storing JSON in VARCHAR2/CLOB/BLOB

In releases without the native JSON datatype, store JSON in VARCHAR2, CLOB, or BLOB with an IS JSON constraint:

```sql
CREATE TABLE lab_json_events (
    event_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_lab_json_events_payload
        CHECK (payload IS JSON)
);
```

The constraint makes the database reject documents that fail to parse under IS JSON rules. It does not replace business validation such as required fields, min/max, enums, or cross-field rules.

### 7.2. STRICT and UNIQUE KEYS

Oracle IS JSON supports options for strict syntax checking and unique object keys:

```sql
CREATE TABLE lab_json_strict (
    id NUMBER PRIMARY KEY,
    payload CLOB,
    CONSTRAINT ck_lab_json_strict
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
```

STRICT enforces stricter JSON syntax than Oracle's default lax mode in certain contexts. WITH UNIQUE KEYS requires objects to have no duplicate keys. This matters because different parsers handle duplicate keys differently (keeping first, keeping last, or erroring); contracts should reject duplicate keys to avoid divergent interpretations across producer, gateway, and database.

Check query:

```sql
SELECT id
FROM lab_json_strict
WHERE payload IS JSON STRICT WITH UNIQUE KEYS;
```

### 7.3. Native JSON Datatype

Oracle Database 21c introduced the native JSON type, storing an optimized binary JSON representation (OSON) inside the database:

```sql
CREATE TABLE lab_json_native (
    event_id NUMBER PRIMARY KEY,
    payload JSON
);
```

The native JSON datatype inherently ensures stored data is valid JSON per the type's rules; an IS JSON constraint is not needed as with raw text storage. Exact syntax, storage behavior, and client binding capabilities depend on version and driver.

When multi-release compatibility or raw text exchange is needed, CLOB/BLOB with IS JSON remains a common pattern.

### 7.4. JSON in BLOB and Encoding

When storing JSON in BLOB, the contract must specify the encoding. Oracle SQL/JSON processes JSON in BLOB according to supported encodings (typically UTF-8). Never dump bytes from an arbitrary encoding into a BLOB assuming the parser will guess correctly.

If the application receives an HTTP body as bytes, keep the raw bytes until the encoding is verified; decode once properly and reject invalid byte sequences. Avoid decoding with replacement characters and continuing, as that silently alters the payload.

### 7.5. Do Not Treat IS JSON as Schema Validation

IS JSON verifies JSON validity under the chosen options. It does not prove:

- That orderId exists.
- That orderId is a non-empty string.
- That items is an array with at least one element.
- That quantity is a positive integer.
- That currency belongs to a supported list.
- That cross-field logic holds.

Combine application-tier JSON Schema or deliberate SQL/PLSQL checks.

## 8. SQL/JSON Functions: Extracting and Checking

### 8.1. JSON_VALUE

JSON_VALUE extracts a scalar from a JSON path:

```sql
SELECT JSON_VALUE(
           payload,
           '$.orderId'
           RETURNING VARCHAR2(40)
           ERROR ON ERROR
           NULL ON EMPTY
       ) AS order_id
FROM lab_json_events;
```

RETURNING defines the SQL result type. ERROR ON ERROR prevents silently turning invalid data into NULL; NULL ON EMPTY specifies returning NULL when the path does not exist. Choose ON ERROR/ON EMPTY explicitly per contract rather than relying on implicit defaults.

### 8.2. JSON_EXISTS

JSON_EXISTS checks whether a path exists and matches:

```sql
SELECT event_id
FROM lab_json_events
WHERE JSON_EXISTS(payload, '$.orderId');
```

Use JSON_EXISTS to distinguish missing fields from certain JSON null cases. When deeper distinction is required, combine JSON_VALUE/JSON_QUERY with ON EMPTY/ON ERROR rules and test on your target release.

### 8.3. JSON_QUERY

JSON_QUERY retrieves an object or array:

```sql
SELECT JSON_QUERY(
           payload,
           '$.items'
           RETURNING CLOB
           ERROR ON ERROR
       ) AS items_json
FROM lab_json_events;
```

JSON_QUERY is useful when you need to preserve a JSON substructure rather than forcing it into a scalar.

### 8.4. JSON_TABLE

JSON_TABLE turns a JSON document into relational rows and columns:

```sql
SELECT
    e.event_id,
    jt.order_id,
    jt.item_sku,
    jt.quantity
FROM lab_json_events e,
     JSON_TABLE(
         e.payload,
         '$'
         COLUMNS (
             order_id VARCHAR2(40)
                 PATH '$.orderId'
                 ERROR ON ERROR,
             NESTED PATH '$.items[*]'
             COLUMNS (
                 item_sku VARCHAR2(40) PATH '$.sku',
                 quantity NUMBER PATH '$.quantity'
                     ERROR ON ERROR
             )
         )
     ) jt;
```

JSON_TABLE projects nested structures into SQL relations, making joins, filtering, and inserts straightforward. Specify RETURNING/column datatypes and error handling explicitly to prevent unwanted implicit casts.

### 8.5. JSON_VALUE and Numeric Types

If the quantity field must be a NUMBER:

```sql
SELECT JSON_VALUE(
           payload,
           '$.quantity'
           RETURNING NUMBER
           ERROR ON ERROR
       )
FROM lab_json_events;
```

After parsing a NUMBER, you must still validate business domains—for example quantity > 0 and within bounds. JSON_VALUE does not replace CHECK constraints or business validation.

### 8.6. ON ERROR and ON EMPTY

Common behaviors include:

| Clause | Meaning |
| --- | --- |
| ERROR ON ERROR | Raises an error if JSON/path/type conversion fails under covered conditions |
| NULL ON ERROR | Returns SQL NULL for errors covered by the clause |
| DEFAULT ... ON ERROR | Returns default on error, where syntax/release supports it |
| ERROR ON EMPTY | Raises an error if the path finds no value |
| NULL ON EMPTY | Returns NULL if the path does not exist |
| DEFAULT ... ON EMPTY | Returns default if the path does not exist |

Using NULL ON ERROR on every field can turn invalid data into NULL and let it slip into the system. For required fields or financial data, prefer ERROR ON ERROR and ERROR ON EMPTY or validate separately before saving.

### 8.7. JSON_OBJECT and JSON_ARRAY

Oracle provides functions to generate JSON from SQL:

```sql
SELECT JSON_OBJECT(
           'orderId' VALUE order_id,
           'status' VALUE status,
           'amount' VALUE total_amount
           RETURNING CLOB
       ) AS order_json
FROM lab_orders;
```

RETURNING CLOB suits outputs that may exceed the VARCHAR2 limit. Use FORMAT JSON when an input value is already JSON and must be embedded as a JSON object/array rather than quoted as a string; only use it on validated sources.

## 9. Validating JSON Structure and Business Rules

### 9.1. Checking Required Fields

You can combine JSON_EXISTS:

```sql
SELECT event_id
FROM lab_json_events
WHERE NOT JSON_EXISTS(payload, '$.orderId')
   OR NOT JSON_EXISTS(payload, '$.items');
```

This checks presence. Next, check types, nulls, lengths, and domains.

### 9.2. Checking Arrays

You can use JSON_TABLE to count elements:

```sql
SELECT e.event_id, COUNT(jt.sku) AS item_count
FROM lab_json_events e,
     JSON_TABLE(
         e.payload,
         '$.items[*]'
         COLUMNS (
             sku VARCHAR2(40) PATH '$.sku'
         )
     ) jt
GROUP BY e.event_id
HAVING COUNT(jt.sku) > 500;
```

If empty arrays must be rejected, check for count 0 or use an appropriate JSON_EXISTS path. Be mindful of outer/inner semantics in JSON_TABLE: documents lacking the array may produce 0 rows or a NULL row depending on how NESTED PATH is written.

### 9.3. Checking Domain Constraints

For example, quantity must be positive:

```sql
SELECT e.event_id, jt.quantity
FROM lab_json_events e,
     JSON_TABLE(
         e.payload,
         '$.items[*]'
         COLUMNS (
             quantity NUMBER PATH '$.quantity'
                 ERROR ON ERROR
         )
     ) jt
WHERE jt.quantity <= 0;
```

In production, avoid letting a single query fail an entire batch on conversion without identifying which document failed. Validate payloads individually at ingress, or use a staging pipeline that classifies errors by event_id.

### 9.4. Duplicate Keys

JSON objects should not have duplicate keys. Example:

```json
{"role": "user", "role": "admin"}
```

Different parsers handle this differently: one layer may take the first value, another the last. Use STRICT WITH UNIQUE KEYS when storing raw text in Oracle and configure parsers/gateways to reject duplicate keys upon receipt.

### 9.5. Unknown Fields

The contract must define unknown-field handling:

- Reject if you want a closed contract and typo protection.
- Ignore if you want forward compatibility.
- Preserve if round-tripping or proxying payloads.

Do not assume the Oracle JSON parser enforces `additionalProperties` like JSON Schema. That is a validator/application contract decision.

### 9.6. Cross-Field Validation

For example, totalAmount must equal the sum of quantity × unitPrice:

```sql
SELECT e.event_id
FROM lab_json_events e
WHERE JSON_VALUE(e.payload, '$.totalAmount' RETURNING NUMBER)
      <>
      (
          SELECT SUM(jt.quantity * jt.unit_price)
          FROM JSON_TABLE(
              e.payload,
              '$.items[*]'
              COLUMNS (
                  quantity NUMBER PATH '$.quantity',
                  unit_price NUMBER PATH '$.unitPrice'
              )
          ) jt
      );
```

This illustrates the logic; you must specify rounding, currency scale, empty-array, and null behavior. For monetary values, use NUMBER and explicit rounding rules.

## 10. Designing XML Contracts

### 10.1. Elements and Attributes

XML can represent data as elements or attributes:

```xml
<Order orderId="ORD-100">
  <CreatedAt>2026-11-14T08:30:00Z</CreatedAt>
  <Items>
    <Item>
      <Sku>KB-001</Sku>
      <Quantity>2</Quantity>
    </Item>
  </Items>
</Order>
```

Define consistently which fields are elements and which are attributes. Repeating data is usually represented as multiple elements with the same name; avoid encoding lists as comma-separated strings if you need type and cardinality validation.

### 10.2. XML Declaration and Encoding

XML can declare its version and encoding:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Order>
  <OrderId>ORD-100</OrderId>
</Order>
```

The encoding in the declaration must match the actual byte stream. If HTTP headers, BOM, and XML declaration conflict, parsers may reject or misinterpret the content. Standardize on one supported encoding, usually UTF-8, and validate byte sequences before processing.

### 10.3. Namespaces

Namespaces distinguish XML vocabularies sharing local names:

```xml
<Order xmlns="urn:example:orders:v1">
  <OrderId>ORD-100</OrderId>
</Order>
```

When querying XML with XPath/XQuery, namespaces must be declared and bound to prefixes. The prefix in the document does not have to match the prefix in the query; the namespace URI is the true identifier.

### 10.4. XSD

XML Schema (XSD) specifies:

- Elements/attributes and data types.
- MinOccurs/MaxOccurs.
- Required/optional status.
- Simple type restrictions, patterns, min/max.
- Sequence/choice and element ordering.
- Namespaces/targetNamespace.
- Nillable settings and xsi:nil rules.

Simple XSD example:

```xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:orders:v1"
           xmlns="urn:example:orders:v1"
           elementFormDefault="qualified">
  <xs:element name="Order">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="OrderId" type="xs:string"/>
        <xs:element name="Quantity" type="xs:positiveInteger"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

XSD validates structure and types; business rules such as which customer owns the order or whether totals match still require separate validation.

### 10.5. Missing, Empty Elements, and xsi:nil

These forms have different meanings:

```xml
<Order/>
```

```xml
<Order><Note/></Order>
```

```xml
<Order xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Note xsi:nil="true"/>
</Order>
```

- Element missing: no Note node.
- Empty element: Note node exists with empty content.
- xsi:nil="true": element is present and explicitly marked nil where the XSD allows nillable.

The contract must define the meaning of each case. Do not automatically treat an empty element as NULL.

### 10.6. XML Whitespace and Canonicalization

Whitespace can be significant in text nodes, mixed content, signatures, or canonicalization. Do not blindly strip whitespace across an entire document. When XML signatures or hashes depend on canonical form, use standard canonicalization and preserve namespace/attribute semantics.

## 11. Oracle XMLType and XML DB

### 11.1. Storing XML with XMLType

Oracle provides XMLType to store and process XML:

```sql
CREATE TABLE lab_xml_messages (
    message_id NUMBER PRIMARY KEY,
    payload XMLTYPE,
    received_at TIMESTAMP
);
```

XMLType can use different storage models depending on release and DDL. When designing large tables, consider binary XML, SecureFiles LOB, or a supported storage model; do not assume every XMLType is stored identically to CLOB.

### 11.2. Creating XMLType from Strings

```sql
INSERT INTO lab_xml_messages (
    message_id,
    payload,
    received_at
)
VALUES (
    1,
    XMLTYPE(
        '<Order><OrderId>ORD-100</OrderId></Order>'
    ),
    SYSTIMESTAMP
);
```

In production systems, bind payloads through the driver rather than concatenating strings into SQL text. If input is untrusted, validate XML and parser policies before storing.

### 11.3. Checking XML Well-Formedness

The XMLType constructor/parser checks well-formedness when creating an XMLType from XML content. Documents with mismatched tag nesting, illegal characters, or invalid XML structure raise parse errors.

Well-formed does not mean XSD-valid or business-valid.

### 11.4. XMLIsValid and Schema Validation

Oracle XML DB supports XML Schema-based XMLType and schema validation APIs. The workflow typically involves registering the XML Schema in XML DB, creating a schema-based XMLType, or validating documents against the registered schema. Specific APIs (XMLIsValid, schemaValidate, or XMLType methods) vary by release; consult your version's SQL Reference and XML DB Developer's Guide.

Do not write a custom function that only checks whether tags exist and call it XSD validation. If the contract requires XSD, use a real XML Schema validator.

### 11.5. Extracting with XMLQuery/XMLCast

XMLQuery executes XQuery over XMLType; XMLCast converts the XML result to a SQL type:

```sql
SELECT XMLCAST(
           XMLQUERY(
               'declare default element namespace "urn:example:orders:v1";
                /Order/OrderId/text()'
               PASSING payload
               RETURNING CONTENT
           )
           AS VARCHAR2(40)
       ) AS order_id
FROM lab_xml_messages;
```

This example assumes the document has the matching default namespace URI. Without proper namespace declaration, XPath may fail to match even when local names look identical.

### 11.6. XMLExists

XMLExists checks whether an XQuery returns any items:

```sql
SELECT message_id
FROM lab_xml_messages
WHERE XMLEXISTS(
    'declare default element namespace "urn:example:orders:v1";
     /Order/OrderId'
    PASSING payload
);
```

XMLExists is useful in WHERE; it does not replace schema validation.

### 11.7. XMLTable

XMLTable maps XML nodes to rows and columns:

```sql
SELECT
    m.message_id,
    x.order_id,
    x.quantity
FROM lab_xml_messages m,
     XMLTABLE(
         XMLNAMESPACES(
             DEFAULT 'urn:example:orders:v1'
         ),
         '/Order'
         PASSING m.payload
         COLUMNS
             order_id VARCHAR2(40) PATH 'OrderId',
             quantity NUMBER PATH 'Quantity'
     ) x;
```

XMLTable is suited for converting XML into SQL relations, joining with other tables, and loading data. Define column datatypes and conversion/error handling explicitly.

## 12. Controlling Size and Resources

### 12.1. Multi-Layer Limits

Safe payload limits must be enforced across multiple layers:

1. HTTP/API gateway: limit Content-Length and streaming bytes.
2. Application ingress: limit bytes, timeouts, rates, and concurrent uploads.
3. Parser: limit nesting depth, token count, element count, and string length.
4. Contract validator: limit array cardinality, field lengths, and domains.
5. Database: choose appropriate datatypes/storage, constraints, quotas, and transaction policies.
6. Downstream: limit rows generated by JSON_TABLE/XMLTABLE and output size.

Checking limits only after reading the entire payload into RAM is too late for huge payloads. Enforce byte limits while streaming.

### 12.2. Byte Size and Character Length Differ

A 1,000-character Unicode string can require more than 1,000 bytes in UTF-8. Therefore distinguish:

- Wire size: bytes received over the network.
- Character length: number of characters per contract semantics.
- Database byte length: bytes after character set conversion.
- Serialized size: JSON/XML size after serialization/escaping.

API limits usually need byte limits to protect network/memory and character limits to protect field semantics.

### 12.3. VARCHAR2 and CLOB

In SQL, the VARCHAR2 limit depends on MAX_STRING_SIZE:

- STANDARD: maximum 4000 bytes for SQL VARCHAR2.
- EXTENDED: up to 32767 bytes for SQL VARCHAR2, depending on configuration.

PL/SQL VARCHAR2 has a maximum of 32767 bytes. Do not use VARCHAR2 to hold payloads larger than its limit. CLOB suits large text; BLOB suits raw bytes.

For JSON/XML outputs, choose RETURNING CLOB or an appropriate datatype when output may exceed VARCHAR2. Avoid implicit conversions that truncate or raise ORA-06502/ORA-01489.

### 12.4. Native JSON Datatype

The native JSON datatype in Oracle 21c+ uses binary JSON representation and is not capped like a VARCHAR2 scalar. Still, you must enforce application-level payload sizes, document complexity, field counts, and resource budgets. A large datatype does not mean unbounded payloads are safe.

### 12.5. Nesting Depth Limits

JSON/XML can be nested many levels deep. Excessive depth increases parser cost, recursive traversal, stack, and memory usage. Set a contract max depth—such as 32 or 64 levels depending on the application—and reject before executing heavy recursive logic.

Do not set max depth purely by the parser's maximum; base it on realistic business structures and testing.

### 12.6. Element and Token Limits

A small payload in bytes can still contain hundreds of thousands of tiny objects. Limit:

- Total JSON nodes/tokens.
- Elements per array.
- Total XML elements/attributes.
- Child object counts.
- Rows generated by JSON_TABLE/XMLTABLE.

This protects the database from excessive fan-out when one document expands into many relational rows.

### 12.7. String and Attribute Limits

Set max lengths for:

- IDs, codes, names, and descriptions.
- URLs, emails, and external references.
- XML attributes and text nodes.
- Error messages and metadata.

Do not allow a description field to accept megabytes when business rules only need a few hundred characters. Large content belongs in dedicated LOB/document storage.

### 12.8. Timeouts and Concurrency

Payload limits must pair with parse/validation timeouts, request timeouts, maximum concurrent requests, and per-caller rate limits. Byte limits without timeouts still allow slow uploads to tie up connections and resources.

### 12.9. Output Size

Queries generating JSON/XML can also produce output larger than the input, especially when joins duplicate rows or aggregate JSON/XML. Enforce result size limits, pagination, streaming, and max rows. Do not serialize an entire table into one CLOB just because the database can.

## 13. Storing Large Payloads and Streaming

### 13.1. Choosing Datatypes by Content

| Content | Suitable Storage Type |
| --- | --- |
| Small JSON queried frequently | Native JSON or VARCHAR2/CLOB with IS JSON |
| Large textual JSON | CLOB or UTF-8 BLOB per contract |
| Large XML | XMLType or CLOB depending on XML DB/query needs |
| Binary files | BLOB |
| External files needing reference only | BFILE |
| Intermediate assembly/transform data | Temporary CLOB/BLOB |

Evaluate indexing, query patterns, retention, backup, compression, SecureFiles, and driver support.

### 13.2. Streaming Instead of Materializing Entirely

Applications should stream payloads from the HTTP body to the parser/LOB API using bounded buffers. Avoid:

1. Reading the entire file into a byte array.
2. Decoding the entire array into a string.
3. Creating another copy during serialization.
4. Binding yet another copy to the database.

Chains of copies can multiply memory usage several times over the payload size.

### 13.3. Temporary LOBs

Temporary LOBs can be used to assemble intermediate content:

```sql
DECLARE
    l_json CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_json,
        cache => TRUE,
        dur => DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        l_json,
        LENGTH('{"status":"ready"}'),
        '{"status":"ready"}'
    );

    -- Use l_json for the next step.
    DBMS_LOB.FREETEMPORARY(l_json);
END;
/
```

Free temporary LOBs on both success and exception paths. For large payloads, monitor TEMP usage and avoid holding SESSION-duration LOBs unnecessarily.

### 13.4. Staging Tables

For large payloads or multi-step validation, use a staging table:

```sql
CREATE TABLE lab_payload_stage (
    payload_id NUMBER PRIMARY KEY,
    payload_type VARCHAR2(10) NOT NULL,
    payload_body CLOB,
    validation_status VARCHAR2(20) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    error_code VARCHAR2(50),
    error_detail VARCHAR2(1000)
);
```

Load raw payloads into staging, validate syntax/schema/domain/resource limits, and move valid data into business tables. Keep failed data in REJECTED/QUARANTINED state per retention policy.

## 14. Handling Invalid Data

### 14.1. Error Classification

Do not lump every failure into a single INVALID_DATA code. Classification helps callers fix payloads properly:

| Error Category | Example | Should Raw Payload Be Retried? |
| --- | --- | --- |
| Syntax | JSON missing bracket, malformed XML nesting | No; producer must fix |
| Encoding | Invalid UTF-8 byte sequence | No; resend with valid encoding |
| Schema/structure | Missing orderId, wrong type for items | No; fix contract payload |
| Domain | Negative quantity, unsupported currency | No unless business data changes |
| Reference | customerId does not exist | Possibly retry if dependency arrives later, per policy |
| Conflict | Version changed, duplicate event | Handle via idempotency/concurrency |
| Resource | Payload exceeds size/depth/timeout | Retry only after shrinking payload or controlled limit change |
| Infrastructure | Database unavailable, network timeout | Can retry with backoff and idempotency |

### 14.2. Fail Fast / Reject Early

Validate at ingress before:

- Loading the full payload into memory.
- Parsing huge nested structures.
- Calling SQL/JSON or XMLTable to generate rows.
- Acquiring row locks or opening long transactions.
- Calling downstream services.

Early rejection saves CPU, memory, TEMP, undo, and connections.

### 14.3. Validate in Order

A sound pipeline:

1. Check HTTP content type, encoding, and byte limit.
2. Safely parse JSON/XML syntax.
3. Check document depth, token/element count, and string lengths.
4. Validate schema/version.
5. Validate types, required/null rules, formats, and cardinality.
6. Validate domain and cross-field rules.
7. Check references, uniqueness, and authorization.
8. Move data into staging or business tables inside a controlled transaction.

Do not run expensive steps before checking whether the payload exceeds basic limits.

### 14.4. Structured Error Responses

Example error response:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Payload does not match the order contract.",
    "correlationId": "corr-456",
    "details": [
      {
        "path": "$.items[0].quantity",
        "rule": "minimum",
        "expected": ">= 1"
      }
    ]
  }
}
```

Never return raw stack traces, SQL text, filesystem paths, schema internals, or sensitive data to callers. You may return multiple validation errors if safe and helpful, but cap error count so responses do not bloat.

### 14.5. Do Not Silently Turn Errors into Defaults

For example, JSON_VALUE NULL ON ERROR can turn an invalid quantity type into NULL. If subsequent code uses NVL(quantity, 1), a malformed payload may be accepted as quantity = 1.

Only use defaults when explicitly defined by the contract; never use defaults to hide parse, conversion, or missing-mandatory-field errors.

### 14.6. Reject or Quarantine?

- Reject: refuse immediately and return an error to the producer.
- Quarantine: hold the raw payload in isolation for investigation or controlled replay.
- Accept with warning: use only when permitted by the contract and warnings are logged clearly.

Quarantine requires retention, access control, encryption, masking, and deletion workflows. Never store payloads containing personal data or secrets indefinitely.

## 15. Duplicates, Idempotency, and Repeated Data

### 15.1. Duplicate Events

Producers may retry on timeout even after the consumer committed. Without idempotency, the same event can create duplicate orders or payments.

Event contracts should include an eventId unique within a defined scope. The database can enforce this with a unique constraint:

```sql
CREATE TABLE lab_processed_events (
    event_id VARCHAR2(100) PRIMARY KEY,
    payload_hash VARCHAR2(128),
    processed_at TIMESTAMP NOT NULL
);
```

Within the event-processing transaction, insert eventId before or alongside business DML; a unique violation indicates the event was already processed or is in contention. Define how payload hashes are compared if the same eventId arrives with different contents.

### 15.2. Idempotent Processing

An idempotent operation can be repeated without unintended side effects. Designs usually combine:

- An eventId/requestId stable across retries.
- A database unique constraint.
- Persisted processing status and committed result.
- A payload hash to detect same ID with altered content.
- A transaction spanning both the processed marker and business updates.

Do not rely solely on SELECT-before-INSERT; two sessions can concurrently see no row. A unique constraint is the final concurrency safeguard.

### 15.3. Duplicate Keys in JSON

Duplicate object keys differ from duplicate eventIds—for example, an object containing two orderId keys. Reject duplicate keys before interpretation so every parser agrees.

### 15.4. Duplicate XML Elements

XML can validly contain multiple elements with the same name if the XSD sets maxOccurs greater than 1. Distinguish:

- Repeating elements permitted by the contract (e.g., multiple Item elements).
- Disallowed duplicate elements (e.g., only one OrderId).
- Duplicate attribute names on the same element (not well-formed XML).

XSD cardinality and application validation define what is valid.

## 16. Encoding, Unicode, and Normalization

### 16.1. UTF-8

For JSON/XML APIs, UTF-8 is typically the best choice due to broad compatibility. Contracts should state the encoding and byte-stream rules. Never guess encoding from content when it can be determined via protocol or declaration.

### 16.2. Character Count vs. Byte Count

Unicode characters can take multiple bytes. For instance, accented Vietnamese text can be represented as precomposed characters or base characters plus combining marks; two strings can look identical yet have different byte sequences.

When contracts compare lengths:

- Cap requests in bytes to protect transport/memory.
- Cap fields in characters per clear rules.
- Define whether Unicode NFC/NFD normalization applies.
- Do not alter content if signatures/hashes depend on original bytes.

### 16.3. Unicode Normalization

Two visually identical strings can have different code point sequences. If identifiers, emails, or names require consistent matching, define normalization at the contract/application layer and store canonical values. Keep raw values if auditing or proving original input is required.

### 16.4. Escaping

JSON escapes quotes, backslashes, and control characters. XML escapes special characters in text and attributes; never build documents by raw string concatenation. Use standard serializers for proper escaping and injection prevention.

### 16.5. Do Not Decode/Re-Encode Arbitrarily

If a payload is digitally signed or checksummed, any decoding, newline normalization, property reordering, or reserialization can alter the bytes. Clarify whether signatures are computed over raw bytes, canonical JSON/XML, or semantic objects; use the exact canonicalization scheme rather than inventing custom rules.

## 17. JSON/XML Parser Security

### 17.1. JSON Parser Limits

JSON parsers should cap:

- Total input bytes.
- Maximum nesting depth.
- Total token/node count.
- Array element count.
- String/key lengths.
- Parse duration and concurrent request count.

Prevent payloads with thousands of nested objects or giant arrays from exhausting stack or memory. Check for duplicate keys and reject invalid keys per contract.

### 17.2. XML External Entities (XXE)

XML parsers may support DTDs and external entities. If a parser resolves external entities from URLs/files, untrusted payloads can attempt to read local files, probe internal endpoints, or trigger SSRF.

For external XML:

- Disable DTDs when unnecessary.
- Disable external general entities and external parameter entities.
- Prevent the parser from fetching external schemas/stylesheets from untrusted URLs.
- Use schema URI allowlists and controlled internal resolvers.
- Cap entity expansion and parser resources.
- Keep parser libraries updated and test actual configurations.

### 17.3. Billion Laughs and Entity Expansion

A small XML document can declare nested entities that expand into massive content—a classic resource exhaustion attack. Disable DTDs/external entities and enforce expansion limits; do not check only raw file size.

### 17.4. XInclude and External Schemas

Check whether the parser enables XInclude, schema-location auto-fetch, or XSLT document access. Convenient features can open filesystem or network access paths. Enable them only when strictly needed with controlled resolvers/allowlists.

### 17.5. XML Namespaces and Signatures

XML Signatures can be attacked if an application verifies one node but processes another (signature wrapping). Use standard XML Signature libraries, validate reference URIs, and ensure the signed node and processed node are the exact same element per contract.

### 17.6. Do Not Log Full Payloads by Default

Payloads can carry PII, access tokens, addresses, financial data, or sensitive documents. Log diagnostic metadata such as eventId, correlationId, payload size, schemaVersion, hash, error code, and error path. Mask or omit sensitive fields; store raw payloads only in controlled quarantine.

## 18. JSON/XML Inside Oracle Transactions

### 18.1. Validate Before Writing Core Data

If a payload requires multi-step parsing and validation, perform those steps before updating business tables. Avoid holding transactions or row locks while parsing large files or waiting on network calls.

### 18.2. Staging and Publishing

One pattern:

1. Receive payload into staging with state RECEIVED.
2. Record byte size, encoding, schema version, event ID, and hash.
3. Validate syntax and resource limits.
4. Validate schema/types/domain.
5. Record the validation result.
6. Move valid data into business tables in a short transaction.
7. Mark PUBLISHED/PROCESSED in the same transaction as business DML.
8. Quarantine failed payloads and apply retention.

### 18.3. Atomicity

When business rows are derived from JSON_TABLE/XMLTABLE, you can run INSERT ... SELECT into target tables within the same transaction. If any step fails, roll back per transaction policy to avoid half-applied states.

When processing hundreds of thousands of elements, consider chunking/batching with progress states; when splitting commits, the contract must clearly reflect in-progress data so readers do not observe incomplete states.

### 18.4. Never Run DDL Inside Ingestion Transactions

CREATE TABLE, ALTER TABLE, and other DDL statements usually issue implicit commits. Never dynamically create staging tables per request inside a business transaction. Pre-provision staging tables and partition logically using metadata or request IDs.

### 18.5. Locks and Concurrency

When updating the same business entity from multiple payloads, use unique keys, version columns, or SELECT FOR UPDATE as required. Do not assume a large JSON/XML payload creates an independent unit of atomicity on its own; the database transaction remains the commit boundary.

## 19. Logging, Metrics, and Observability

### 19.1. Recording Metadata

An ingestion log record may capture:

- eventId/requestId.
- correlationId/traceId.
- Producer and schemaVersion.
- Payload format (JSON/XML).
- Byte size and parsed element count.
- Checksum/hash.
- Validation/processing status.
- Error code, error path, and timestamp.
- Duration of parse, validate, persist, and publish phases.

### 19.2. Do Not Log Raw Payloads Unconditionally

Raw payloads should only be stored when justified for business/investigation purposes under protective policies. Apply encryption, access control, masking, retention, and deletion. Never write passwords, tokens, or sensitive payment data into error logs.

### 19.3. Metrics to Monitor

- Payload count by format/version/producer.
- Syntax/schema/business rejection rates.
- Payload size distribution (p50/p95/p99/max).
- Parse/validation latency.
- Quarantined payload count.
- Retry and duplicate event counts.
- TEMP/PGA/LOB usage and database waits.
- Row counts generated by JSON_TABLE/XMLTABLE.

### 19.4. Error Paths

Paths like $.items[3].quantity or XPath /Order/Items/Item[4]/Quantity help producers fix bad payloads. Avoid logging full raw values if they may contain PII or secrets. Log rule names, expected types, and error locations.

## 20. JSON Hands-On Practice in Oracle

Run examples in a lab schema. Verify your Oracle version and table creation privileges before running.

### 20.1. Create a JSON Text Table

```sql
CREATE TABLE lab_contract_json (
    payload_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    received_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT ck_lab_contract_json
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
```

### 20.2. Load a Valid Payload

```sql
INSERT INTO lab_contract_json (payload_id, payload)
VALUES (
    1,
    '{
       "schemaVersion":"1.0",
       "orderId":"ORD-100",
       "items":[
         {"sku":"KB-001","quantity":2,"unitPrice":450000}
       ]
     }'
);
COMMIT;
```

### 20.3. Test a Syntactically Invalid Payload

```sql
INSERT INTO lab_contract_json (payload_id, payload)
VALUES (2, '{"orderId":"ORD-101", "items":[}');
```

The IS JSON constraint must reject unparseable payloads. In client code, capture the specific statement error; never treat a failed insert as a saved row.

### 20.4. Extract a Scalar

```sql
SELECT
    payload_id,
    JSON_VALUE(
        payload,
        '$.orderId'
        RETURNING VARCHAR2(40)
        ERROR ON ERROR
        NULL ON EMPTY
    ) AS order_id
FROM lab_contract_json;
```

### 20.5. Project JSON into Rows

```sql
SELECT
    p.payload_id,
    jt.sku,
    jt.quantity,
    jt.unit_price
FROM lab_contract_json p,
     JSON_TABLE(
         p.payload,
         '$.items[*]'
         COLUMNS (
             sku VARCHAR2(40) PATH '$.sku',
             quantity NUMBER PATH '$.quantity' ERROR ON ERROR,
             unit_price NUMBER PATH '$.unitPrice' ERROR ON ERROR
         )
     ) jt;
```

### 20.6. Check Required Fields and Array Limits

```sql
SELECT payload_id
FROM lab_contract_json
WHERE NOT JSON_EXISTS(payload, '$.orderId')
   OR NOT JSON_EXISTS(payload, '$.items');

SELECT p.payload_id, COUNT(*) AS item_count
FROM lab_contract_json p,
     JSON_TABLE(
         p.payload,
         '$.items[*]'
         COLUMNS (sku VARCHAR2(40) PATH '$.sku')
     ) jt
GROUP BY p.payload_id
HAVING COUNT(*) > 500;
```

These two queries illustrate presence and cardinality checks. In an ingestion pipeline, record validation results per payload rather than running detection queries only after mixing data.

## 21. XML Hands-On Practice in Oracle

### 21.1. Create an XMLType Table

```sql
CREATE TABLE lab_contract_xml (
    message_id NUMBER PRIMARY KEY,
    payload XMLTYPE,
    received_at TIMESTAMP DEFAULT SYSTIMESTAMP
);
```

### 21.2. Insert Well-Formed XML

```sql
INSERT INTO lab_contract_xml (message_id, payload)
VALUES (
    1,
    XMLTYPE(
        '<Order xmlns="urn:example:orders:v1">
           <OrderId>ORD-200</OrderId>
           <Items>
             <Item>
               <Sku>KB-001</Sku>
               <Quantity>2</Quantity>
             </Item>
           </Items>
         </Order>'
    )
);
COMMIT;
```

### 21.3. Extract Using XMLTable

```sql
SELECT
    m.message_id,
    x.order_id,
    x.sku,
    x.quantity
FROM lab_contract_xml m,
     XMLTABLE(
         XMLNAMESPACES(
             DEFAULT 'urn:example:orders:v1'
         ),
         '/Order'
         PASSING m.payload
         COLUMNS
             order_id VARCHAR2(40) PATH 'OrderId',
             sku VARCHAR2(40) PATH 'Items/Item/Sku',
             quantity NUMBER PATH 'Items/Item/Quantity'
     ) x;
```

### 21.4. Test a Namespace Mismatch

Run XMLTable with a different namespace URI to observe the query failing to match. Matching the local name OrderId is not enough; the namespace URI must match.

### 21.5. Well-Formed vs. XSD Valid

Create a document with all tags closed properly but a negative Quantity. The document is well-formed yet XSD-invalid if typed as positiveInteger; if the XSD only declares integer, business validation is still needed to enforce > 0.

## 22. Common Errors and Resolutions

| Symptom/Error | Possible Cause | Resolution |
| --- | --- | --- |
| IS JSON constraint failure | Invalid JSON syntax or violated strict/unique-key rules | Parse/validate at ingress and return error path |
| JSON_VALUE returns NULL | Missing field, JSON null, or NULL ON ERROR/EMPTY | Use JSON_EXISTS and explicit error clauses |
| JSON_VALUE conversion error | Scalar has wrong type or exceeds precision | Validate type/domain and choose appropriate RETURNING |
| Duplicate JSON key | Producer sent the same key multiple times | Reject via unique-key validation |
| ORA-40441 / JSON parse error | Invalid JSON syntax/encoding | Inspect raw bytes and parser error |
| ORA-06502 | Buffer/variable too small or conversion error | Use CLOB/JSON, adequate buffers, and explicit casts |
| ORA-01489 | String concatenation result exceeds limit | Use CLOB/LOB aggregation as appropriate |
| XML parse error | Malformed XML or wrong encoding | Inspect declaration, byte stream, and nesting |
| XMLTable returns no rows | Wrong namespace URI or XPath | Declare XMLNAMESPACES and accurate path |
| XSD validation failure | Wrong type, missing required element, cardinality, or namespace | Return validation path and schema version |
| ORA-31011 / XML parser error | XML parser cannot process document | Check well-formedness, encoding, and parser settings |
| Small payload takes long to parse | Deep nesting, entity expansion, or token explosion | Enforce depth/token/timeout and XML entity limits |
| High memory/TEMP usage | Materializing huge payloads or leaking temporary LOBs | Stream, batch, and free temporary LOBs |
| Consumers interpret differently | Unspecified null/missing/duplicate/unknown field rules | Tighten contract and add contract tests |
| Event processed twice | Retries without an idempotency key | Enforce unique eventId and transaction deduplication |
| Stale data overwrites newer data | Missing version/concurrency check | Use optimistic locking or proper row locks |

## 23. Contract Design Checklist

Before deploying a JSON/XML contract to production, confirm:

- [ ] Defined owner, producer, consumer, and data purpose.
- [ ] Defined schemaVersion and compatibility/deprecation policy.
- [ ] Defined required/optional/nullable rules.
- [ ] Distinguished missing, null, empty, and default.
- [ ] Defined types, formats, precision, scale, enums, and domains.
- [ ] Set max byte size and max character length.
- [ ] Set max nesting depth, token/node count, and array cardinality.
- [ ] Defined rules for unknown fields and duplicate keys.
- [ ] Defined encoding and Unicode normalization policy.
- [ ] Provided JSON Schema/XSD or corresponding validator.
- [ ] Implemented cross-field and reference validation.
- [ ] Configured parser timeouts, concurrency limits, and rate limits.
- [ ] Disabled DTDs/external entities in XML parsers when unneeded.
- [ ] Established reject/quarantine and retention policies.
- [ ] Added eventId/idempotency and payload hashes where needed.
- [ ] Defined error codes, error paths, correlation IDs, and metrics.
- [ ] Added producer/consumer compatibility tests.
- [ ] Tested boundary-sized and malicious payloads.
- [ ] Planned streaming/staging for large payloads.
- [ ] Configured appropriate access control, encryption, and masking.

## 24. Self-Check Questions

1. How does a data contract differ from JSON syntax checking?
2. Why can valid JSON still violate a schema or business rule?
3. When should you choose JSON versus XML?
4. How do backward compatibility and forward compatibility differ?
5. How do a missing field, JSON null, and an empty string differ?
6. Why can Oracle SQL turn an empty string into NULL?
7. What extra contract rules do JSON numbers need for money and identifiers?
8. Why must timezones be specified for timestamps?
9. What does IS JSON check and what does it not check?
10. What issue does STRICT WITH UNIQUE KEYS prevent?
11. How do JSON_VALUE, JSON_EXISTS, JSON_QUERY, and JSON_TABLE differ?
12. What principle guides choosing ON EMPTY and ON ERROR?
13. Why does having JSON Schema at the application layer not mean Oracle automatically enforces it?
14. How does well-formed XML differ from XSD-valid XML?
15. Why is the namespace URI more important than the prefix?
16. How do a missing element, an empty element, and xsi:nil differ?
17. What are the roles of XMLType, XMLQuery, XMLExists, and XMLTable?
18. Why does byte limit differ from character limit?
19. Why limit nesting depth, token counts, and array cardinality?
20. What risks do XXE and entity expansion pose?
21. Why should raw payloads not be logged by default?
22. How does quarantine differ from reject?
23. How do eventId and unique constraints support idempotency?
24. Why are staging and streaming helpful for large payloads?
25. Why do chunked commits require upload state and publish state?

## 25. Memory Model

```text
JSON / XML DATA CONTRACT
        |
        v
  Schema + Version + Semantics
        |
        +-- Required / Optional / Null
        +-- Type / Format / Domain
        +-- Compatibility / Unknown fields
        |
        v
  RESOURCE LIMITS
        |
        +-- Bytes / Characters
        +-- Depth / Tokens / Elements
        +-- Array count / String length
        +-- Timeout / Concurrency / Rate
        |
        v
  VALIDATION PIPELINE
        |
        +-- Encoding and syntax
        +-- Schema and type
        +-- Business and reference
        +-- Duplicate / Idempotency
        |
        v
  ORACLE STORAGE / QUERY
        |
        +-- JSON / CLOB / BLOB
        +-- XMLType
        +-- JSON_VALUE / JSON_TABLE
        +-- XMLQuery / XMLTable
        |
        v
  ACCEPT / REJECT / QUARANTINE
        |
        +-- Error code and path
        +-- Correlation ID and metrics
        +-- Staging and atomic publish
        +-- Retention, masking and access control
```

**Key Takeaway:** A contract must specify structure, semantics, and resource limits. Successful parsing proves only syntax; you must validate schemas, domains, sizes, depth, cardinality, encoding, and concurrency before publishing data. In Oracle, choose appropriate JSON/XML types and SQL operators, handle large payloads with LOBs/streaming, and isolate invalid payloads into controlled reject/quarantine flows.
