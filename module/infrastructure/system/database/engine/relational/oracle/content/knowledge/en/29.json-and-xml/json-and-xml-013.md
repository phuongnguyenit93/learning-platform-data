# Choosing Relational, Document, or Hybrid Storage Models

When designing data in Oracle Database, a key decision is whether to organize data using a **relational model**, a **document model**, or a **hybrid model**. The relational model stores data in tables with explicit columns, keys, and constraints. The document model stores a business entity as JSON or XML, usually keeping related attributes together in a single document. The hybrid model uses relational tables for core structured data and JSON/XML for extensible or highly flexible structures.

No single model is optimal for every system. Your choice should depend on data structure, relationships between entities, integrity rules, query patterns, update frequency, integration requirements, and capabilities supported by your Oracle Database version.

## 1. Three Ways to Organize Data

### Relational Model

The relational model divides data into tables. Each table models an entity type or relationship; rows are identified by primary keys and linked by foreign keys. Data rules can be expressed with NOT NULL, UNIQUE, CHECK, PRIMARY KEY, and FOREIGN KEY constraints.

For example, a sales system might have these tables:

- CUSTOMERS: customer information.
- ORDERS: order header information.
- ORDER_ITEMS: line items within an order.
- PRODUCTS: product catalog.

An order can have multiple line items. The one-to-many relationship is expressed by the foreign key ORDER_ITEMS.order_id referencing ORDERS.order_id.

~~~sql
CREATE TABLE customers (
  customer_id   NUMBER PRIMARY KEY,
  customer_name VARCHAR2(200) NOT NULL,
  email         VARCHAR2(320) UNIQUE
);

CREATE TABLE orders (
  order_id    NUMBER PRIMARY KEY,
  customer_id NUMBER NOT NULL,
  order_date  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  status      VARCHAR2(20) NOT NULL,
  CONSTRAINT orders_customer_fk
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  CONSTRAINT orders_status_ck
    CHECK (status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED'))
);

CREATE TABLE order_items (
  order_id   NUMBER NOT NULL,
  line_no    NUMBER NOT NULL,
  product_id NUMBER NOT NULL,
  quantity   NUMBER(10, 2) NOT NULL,
  unit_price NUMBER(12, 2) NOT NULL,
  CONSTRAINT order_items_pk PRIMARY KEY (order_id, line_no),
  CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
  CONSTRAINT order_items_quantity_ck CHECK (quantity > 0),
  CONSTRAINT order_items_price_ck CHECK (unit_price >= 0)
);
~~~

Line items can be queried, filtered, aggregated, and joined with products or orders without parsing a large document. The database directly enforces key relationships and integrity rules.

### Document Model

The document model represents a business entity as a JSON or XML document. Rather than splitting every attribute across tables and columns, a document groups data along the boundary the application reads or writes together.

Example purchase order in JSON:

~~~json
{
  "orderId": 1001,
  "customer": {
    "customerId": 501,
    "name": "Nguyen An"
  },
  "status": "NEW",
  "items": [
    {
      "lineNo": 1,
      "productId": 10,
      "description": "Keyboard",
      "quantity": 2,
      "unitPrice": 45.5
    },
    {
      "lineNo": 2,
      "productId": 20,
      "description": "Mouse",
      "quantity": 3,
      "unitPrice": 18
    }
  ]
}
~~~

The document can be stored in CLOB, BLOB, or the native JSON type depending on the Oracle release. For XML, Oracle provides XMLTYPE and SQL/XML functions to query or transform documents.

One way to store textual JSON on Oracle 19c:

~~~sql
CREATE TABLE order_documents (
  order_id NUMBER PRIMARY KEY,
  payload  CLOB NOT NULL,
  CONSTRAINT order_documents_json_ck CHECK (payload IS JSON)
);
~~~

On Oracle Database 21c and later, you can use the native SQL JSON data type:

~~~sql
CREATE TABLE order_documents_native (
  order_id NUMBER PRIMARY KEY,
  payload  JSON NOT NULL
);
~~~

The native JSON type uses binary OSON representation. On a CLOB column, CHECK IS JSON verifies that the content is valid JSON; it does not automatically enforce business rules such as verifying that customerId exists in CUSTOMERS or that quantity is greater than 0.

### Hybrid Model

The hybrid model keeps stably structured data in relational tables while storing flexible attributes in JSON/XML. For example, an order still has order_id, customer_id, status, and order_date in ORDERS, while extensible attributes specific to order types are stored in a JSON column.

~~~sql
CREATE TABLE orders_hybrid (
  order_id    NUMBER PRIMARY KEY,
  customer_id NUMBER NOT NULL,
  order_date  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  status      VARCHAR2(20) NOT NULL,
  attributes  CLOB,
  CONSTRAINT orders_hybrid_customer_fk
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  CONSTRAINT orders_hybrid_status_ck
    CHECK (status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED')),
  CONSTRAINT orders_hybrid_attributes_json_ck
    CHECK (attributes IS JSON)
);
~~~

For instance, attributes can hold delivery details, gift options, or extra sales-channel fields. The order key, customer, and status remain relational columns for straightforward enforcement and querying.

## 2. Comparing the Models

| Criterion | Relational | JSON/XML Document | Hybrid |
|---|---|---|---|
| Data structure | Explicitly defined tables and columns | Structure lives inside each document | Stable columns combined with extensible documents |
| Entity relationships | Primary keys, foreign keys, JOINs | Usually referenced by ID or nested in documents | Core relationships via keys; flexible parts inside documents |
| Integrity checks | Relational constraints and transactions | Requires syntax and rule checks across layers | Constraints for core parts, validation for document parts |
| Schema changes | Schema changes when adding columns or tables | Can add fields inside documents | Add flexible fields without altering every column |
| Analytical queries | SQL JOIN, GROUP BY, and indexes | SQL/JSON, XQuery, JSON_TABLE, XMLTABLE | Combines relational SQL and document queries |
| Repeating / many-to-many data | Modeled with junction tables | Can nest arrays or store references | Relational for controlled links, documents for auxiliary data |
| API integration | Requires mapping tables to DTOs or documents | Natural fit for JSON/XML APIs | Uses views or application layer to assemble documents |
| Best fit | Core data with strict relationships and rules | Well-bounded aggregates/documents with flexible structure | Systems needing both relational integrity and document flexibility |

Do not pick a model solely because JSON/XML is popular or because one design appears to have fewer tables. Determine how data will be queried and updated over the system's lifecycle.

## 3. When to Choose the Relational Model?

The relational model is typically suitable when:

- Data has a stable structure and key attributes are known upfront.
- Multiple entities have one-to-many or many-to-many relationships.
- Foreign keys are required to prevent references to non-existent entities.
- UNIQUE, CHECK, NOT NULL, or other database-enforced constraints are needed.
- Applications require flexible cross-table queries, aggregations, and reporting.
- Data is shared across multiple applications or business teams.
- Transactions must update multiple related entities as one unit of work.

For example, accounting, inventory, order management, HR, and billing systems usually have many relationships to protect. Balances, stock levels, account codes, and business states require strict rules. Putting all data into one JSON document makes enforcing foreign keys and cross-table rules difficult.

### Advantages of Normalization

Normalization reduces duplication and prevents inconsistent updates. For example, if customer names were duplicated in every order, updating a customer's name would require updating many documents. When customer details live in CUSTOMERS and orders store only customer_id, there is a single source of truth.

Normalization does not mean every query must join dozens of tables or every attribute needs its own table. The normalization level should fit data characteristics, performance, and business rules. You can use views, materialized views, or summary tables when optimizing reads.

## 4. When to Choose the Document Model?

The document model fits well when:

- Data is read and written along a clearly bounded aggregate.
- Attributes vary by entity subtype or API version.
- Many fields are optional and do not need JOINs with other entities.
- The application typically retrieves the whole document or most of it at once.
- Payloads from external systems must be stored for processing, inspection, or auditing.
- Documents have a naturally nested structure, such as configurations, events, profiles, or forms.

For example, a configuration management system may have different device types. Network switches have VLAN attributes, routers have routingProtocol, and storage arrays have capacity and RAID. If these fields change frequently and do not need deep relational joins, a JSON document for configuration can be simpler than adding many nullable columns to a single generic table.

~~~sql
CREATE TABLE device_profiles (
  device_id NUMBER PRIMARY KEY,
  device_type VARCHAR2(30) NOT NULL,
  profile JSON
);
~~~

Example profile data for a network device:

~~~json
{
  "hostname": "edge-01",
  "managementIp": "10.10.0.10",
  "vlans": [10, 20, 30],
  "snmp": {
    "enabled": true,
    "version": "v3"
  }
}
~~~

Example profile for a storage device:

~~~json
{
  "hostname": "storage-01",
  "capacityTb": 120,
  "raidLevel": "RAID6",
  "replication": {
    "enabled": true,
    "target": "dc-2"
  }
}
~~~

Each profile can have its own structure. Shared fields like device_id and device_type remain in relational columns.

### Limitations to Understand

Storing documents does not automatically solve business validation. `CHECK (profile IS JSON)` only confirms valid JSON syntax. It does not guarantee:

- That hostname is unique across the system.
- That managementIp belongs to an allowed subnet.
- That device_type matches the profile structure.
- That replication.target references an existing data center.
- That capacityTb stays within contract limits.

These rules may require validation in the application, triggers, procedures, or a complementary relational design. If an attribute becomes a search key, link key, or critical business rule, consider promoting that attribute to a relational column.

## 5. When to Choose the Hybrid Model?

The hybrid model typically suits business systems with a stable core but extensions that vary by product, partner, or integration channel.

For example, an order has core attributes:

- order_id
- customer_id
- order_date
- status
- total_amount

Extended attributes may vary:

- Delivery orders: deliveryWindow, deliveryInstructions.
- Gift orders: giftMessage, giftWrap.
- Enterprise orders: purchaseOrderReference, costCenter.
- International orders: customsCode, importNotes.

You do not need to add every optional field as a column on ORDERS. Keep frequently queried fields in relational columns and specialized data in JSON.

~~~sql
CREATE TABLE orders (
  order_id      NUMBER PRIMARY KEY,
  customer_id   NUMBER NOT NULL,
  order_date    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  status        VARCHAR2(20) NOT NULL,
  total_amount  NUMBER(14, 2) NOT NULL,
  extra_data    CLOB,
  CONSTRAINT orders_customer_fk
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  CONSTRAINT orders_total_ck CHECK (total_amount >= 0),
  CONSTRAINT orders_extra_json_ck CHECK (extra_data IS JSON)
);
~~~

A row may contain:

~~~json
{
  "giftWrap": true,
  "giftMessage": "Happy birthday!",
  "deliveryWindow": {
    "from": "2026-11-20T09:00:00+07:00",
    "to": "2026-11-20T12:00:00+07:00"
  }
}
~~~

Querying relational and JSON fields together:

~~~sql
SELECT order_id,
       customer_id,
       status,
       JSON_VALUE(
         extra_data,
         '$.deliveryWindow.from'
         RETURNING VARCHAR2(40)
       ) AS delivery_from
  FROM orders
 WHERE status = 'NEW'
   AND JSON_VALUE(extra_data, '$.giftWrap' RETURNING VARCHAR2(5)) = 'true';
~~~

In practice, standardize boolean representations and return types for your Oracle version. For frequently queried attributes, evaluate function-based indexes or JSON search indexes suited to the workload.

## 6. Distinguishing Core Data, Extended Data, and Derived Data

A practical way to partition the model is classifying attributes by role:

| Attribute Role | Examples | Usually Best Placed In |
|---|---|---|
| Identifiers and relationships | order_id, customer_id, product_id | Relational columns and keys |
| Business state | status, approved_at, total_amount | Relational columns with constraints/indexes |
| Stable, frequently queried attributes | order_date, region_code | Relational columns |
| Extensible, optional attributes | giftMessage, partnerMetadata | JSON/XML where appropriate |
| Raw document content | Partner-received payloads | CLOB/BLOB/XMLTYPE or native JSON |
| Aggregated/derived data | daily order counts, total revenue | Views, materialized views, or summary tables |

Do not move a field into JSON merely because it is sparse. If that field drives keys, access control, state transitions, constraints, or critical reports, a relational column may fit better.

Conversely, do not add dozens of nullable columns for specialized attributes that apply to only a few record types if they are rarely queried relationally. JSON can represent such extensions more naturally.

## 7. Reference Data and Relationships Across Documents

In a document model, you can embed related data or store only reference IDs. This choice should be based on data ownership and update patterns.

### Embed Data When It Belongs to the Same Aggregate

For instance, order line items are usually created and read together with the order. They can be embedded in one JSON document:

~~~json
{
  "orderId": 1001,
  "items": [
    {"lineNo": 1, "productId": 10, "quantity": 2},
    {"lineNo": 2, "productId": 20, "quantity": 3}
  ]
}
~~~

Embedding lets you fetch a document in one read. However, if product is an independent entity whose price, description, and stock are shared across many orders, do not duplicate the full product record inside every order as authoritative master data.

### Use References When Entities Are Managed Independently

For example, the JSON stores only productId. To get current product details, query PRODUCTS. If you need to record the description and price at order time, store a snapshot of those values in ORDER_ITEMS because they represent historical transaction data.

The key distinction is:

- **Reference:** points to an entity managed elsewhere.
- **Snapshot:** point-in-time copy preserving historical values.
- **Embedded data:** components sharing a lifecycle and typically read/written with the aggregate.

If referential existence must be guaranteed, a relational foreign key is direct and strong. An ID inside JSON does not automatically enforce a FOREIGN KEY constraint against another table.

## 8. JSON or XML for the Document Model?

When choosing document storage, the format must also match the ecosystem:

| Criterion | JSON | XML |
|---|---|---|
| Structure | Objects, arrays, scalars | Elements, attributes, text nodes |
| Web API integration | Dominant in REST and modern apps | Common in SOAP and enterprise integrations |
| Namespaces | No XML-style namespaces | Supports namespace URIs and prefixes |
| Schema | Validated via JSON Schema at app layer or compatible mechanism | XML Schema (XSD) and validation tools |
| Oracle querying | SQL/JSON, JSON_VALUE, JSON_QUERY, JSON_TABLE | XMLTYPE, XQuery, XMLTABLE, XMLQUERY |
| Storage types | VARCHAR2/CLOB/BLOB; native JSON type from 21c | XMLTYPE or text/LOB depending on design |

JSON typically fits API payloads, configurations, and object/array data. XML fits when integration contracts mandate XSD, namespaces, complex document structures, or existing SOAP systems.

Do not convert XML to JSON just because JSON is more compact if the receiving system requires XML with specific schemas and namespaces. Likewise, do not introduce XML if all integrating parties already agree on JSON and have no XML requirements.

## 9. How Does Oracle Support Storage and Querying?

### Textual JSON

In releases prior to 21c, JSON can be stored in VARCHAR2, CLOB, or BLOB. Use a CHECK constraint `IS JSON` to validate syntax:

~~~sql
CREATE TABLE api_messages (
  message_id NUMBER PRIMARY KEY,
  payload    CLOB NOT NULL,
  CONSTRAINT api_messages_json_ck CHECK (payload IS JSON)
);
~~~

SQL/JSON functions extract data:

~~~sql
SELECT message_id,
       JSON_VALUE(payload, '$.eventType' RETURNING VARCHAR2(50)) AS event_type,
       JSON_VALUE(payload, '$.createdAt' RETURNING VARCHAR2(40)) AS created_at
  FROM api_messages;
~~~

### Native JSON

Starting in Oracle Database 21c, you can declare the SQL JSON data type:

~~~sql
CREATE TABLE api_messages_native (
  message_id NUMBER PRIMARY KEY,
  payload    JSON NOT NULL
);
~~~

The native JSON type uses OSON and can be queried with SQL/JSON functions. When exchanging with external systems, serialize to textual JSON; do not send raw OSON bytes as ordinary JSON payloads.

### XMLTYPE

For XML, store data in an XMLTYPE column:

~~~sql
CREATE TABLE partner_xml_messages (
  message_id NUMBER PRIMARY KEY,
  payload    XMLTYPE
);
~~~

XMLTABLE maps XML nodes into SQL rows and columns. XMLSERIALIZE exports XMLTYPE as CLOB or BLOB when transmitting externally.

Choosing among XMLTYPE, CLOB/BLOB, or native JSON also depends on Oracle version, storage configuration, integration tools, and whether raw input bytes must be preserved intact.

## 10. Querying and Indexing in the Hybrid Model

One advantage of the hybrid model is that relational fields continue using traditional B-tree indexes and constraints, while JSON attributes are queried via SQL/JSON.

Example creating an index on relational status:

~~~sql
CREATE INDEX orders_status_ix ON orders(status);
~~~

If filtering frequently on `deliveryWindow.from` inside JSON, consider a function-based index:

~~~sql
CREATE INDEX orders_delivery_from_ix
ON orders (
  JSON_VALUE(
    extra_data,
    '$.deliveryWindow.from'
    RETURNING VARCHAR2(40)
  )
);
~~~

Queries should use an expression matching the index:

~~~sql
SELECT order_id, customer_id
  FROM orders
 WHERE JSON_VALUE(
         extra_data,
         '$.deliveryWindow.from'
         RETURNING VARCHAR2(40)
       ) >= '2026-11-20T00:00:00+07:00';
~~~

This example illustrates timestamps stored as ISO 8601 strings. String comparisons are only safe when formats and timezones are standardized. For temporal calculations, consider extracting into DATE/TIMESTAMP or storing critical timestamps as relational columns.

When JSON has many searched paths, a JSON search index may fit. For XML, XMLIndex can accelerate XQuery/XMLTABLE queries. Indexes increase write cost and storage, so create them based on actual query patterns and verify via execution plans.

## 11. Transactions, Consistency, and Concurrent Updates

The data model shapes how consistency is protected:

**In the relational model**, a single transaction can INSERT/UPDATE multiple tables, with foreign keys and constraints checked by Oracle. If one step fails, the entire transaction can roll back.

**In the document model**, a document is typically updated as a single row value. Updating a document does not automatically protect references to other tables or rules spanning multiple documents. The application must enforce those rules or move them to relational structures.

**In the hybrid model**, a transaction can update relational columns and JSON columns in the same row. When multiple related tables must be updated, perform them in the same transaction with proper locks and constraints.

For example, when confirming an order, order status and inventory deduction must be protected as a single business unit. Do not update only a status field inside JSON while inventory and payments reside in relational tables. Define the authoritative data source and transaction scope clearly.

If multiple processes concurrently update a single large document, contention occurs on that row. Splitting documents into smaller aggregates or moving independently updated parts into separate tables reduces contention and rewrite volume.

## 12. Schema Evolution and Document Versioning

An advantage of JSON is adding optional fields without altering table structure. However, flexibility does not eliminate the need for schema management.

Example version 1 document:

~~~json
{
  "schemaVersion": 1,
  "customerId": 501,
  "preferences": {
    "language": "vi"
  }
}
~~~

Version 2 document adding time zone:

~~~json
{
  "schemaVersion": 2,
  "customerId": 501,
  "preferences": {
    "language": "vi",
    "timeZone": "Asia/Ho_Chi_Minh"
  }
}
~~~

Applications can read both versions and supply defaults when new fields are absent. Include `schemaVersion` whenever documents may evolve over time.

A schema evolution plan should define:

- Which fields are mandatory versus optional.
- Data types and field naming conventions.
- Default values when new fields are absent.
- Backward and forward compatibility rules.
- How legacy documents are migrated.
- When older versions are retired.
- How data is verified before and after migration.

With relational data, schema evolution usually involves ALTER TABLE, new tables, or constraint updates. With JSON/XML, structures can vary per document, yet applications still need version contracts so clients do not interpret payloads differently.

## 13. JSON Relational Duality Views in Oracle Database 23ai

Oracle Database 23c, released as 23ai, introduced JSON Relational Duality Views. This mechanism exposes data stored in relational tables as JSON documents. Applications can interact through a document interface while underlying data remains organized in relational tables and relationships.

Duality Views are useful when:

- The database needs to keep core data in the relational model.
- Applications want to read or update using JSON document structures.
- Multiple applications need different views over the same underlying data.
- You want to avoid duplicating the same data into a separate JSON store just to serve APIs.

This is a hybrid model at the data-access layer. Duality Views do not eliminate the underlying relational tables; keys, relationships, and data rules still must be designed. Updatability through a view depends on the view structure and Oracle-supported rules. Check release-specific documentation and test insert/update/delete operations before adopting them in applications.

Duality Views also do not imply that every JSON document in a system should become a duality view. If a document is a raw partner payload with an independent lifecycle or must preserve exact contents, a dedicated JSON/XML column can still be appropriate.

## 14. Anti-Patterns to Avoid

**Storing everything in one giant JSON document:** oversized documents with independently updated parts and many cross-references make querying, updating, and consistency control difficult.

**Duplicating shared master data across many documents:** copying customer names, product details, or shared statuses into numerous documents causes inconsistency. Only snapshot when preserving point-in-time historical values.

**Burying business keys inside JSON:** if a field is a primary key, foreign key, frequent search key, or must be UNIQUE, consider a relational column.

**Using relational columns for every sparse optional attribute:** dozens of columns relevant to only one record subtype create confusing schemas full of NULLs. Extensions may fit better in JSON.

**Treating IS JSON as business validation:** this constraint verifies JSON syntax; it does not replace type checks, value ranges, relationships, or business rules.

**Omitting schema versions on documents:** adding or renaming fields without a compatibility plan breaks older clients.

**Querying JSON without an indexing strategy:** repeated filtering on JSON paths can be expensive. Measure workloads and evaluate function-based indexes or JSON search indexes.

**Using XML/JSON just to avoid table design:** if business logic needs foreign keys, joins, and frequent aggregations, stuffing everything into a document pushes complexity into application code and weakens control.

## 15. Workflow for Selecting a Model for a Business Domain

When designing an entity, answer these questions in order:

1. **Data boundaries:** which data is always created, read, and updated together?
2. **Relationships:** does the data reference independent entities or involve many-to-many relationships?
3. **Integrity:** which rules must the database enforce via keys, constraints, or transactions?
4. **Queries:** which fields do users filter, join, group, and report on?
5. **Change frequency:** which fields are stable versus varying by product or partner?
6. **Size:** how large can documents grow, and is streaming needed?
7. **Integration:** do systems send/receive JSON, XML, or relational data?
8. **Oracle version:** does the database support native JSON, SQL/JSON, or XML features you plan to use?
9. **Operations:** do backup, restore, replication, export/import, and client drivers support the chosen storage?
10. **Measurement:** test queries and updates on representative data, inspecting execution plans, storage footprint, and contention.

After answering, classify fields into core, extended, snapshot, and derived data. Choose the relational model for core data needing integrity and cross-table queries; choose JSON/XML for flexible aggregates or payloads; combine both when the system has both requirements.

## 16. Complete Hybrid Design Example

Suppose an order management system requires:

- Independently managed customers.
- Orders with status, timestamp, and total amount.
- Multiple line items per order.
- Channel-specific metadata on certain sales channels.
- Exporting orders as JSON for APIs.

Relational design:

~~~sql
CREATE TABLE customers (
  customer_id NUMBER PRIMARY KEY,
  full_name   VARCHAR2(200) NOT NULL,
  email       VARCHAR2(320) UNIQUE
);

CREATE TABLE products (
  product_id   NUMBER PRIMARY KEY,
  product_name VARCHAR2(200) NOT NULL
);

CREATE TABLE orders (
  order_id     NUMBER PRIMARY KEY,
  customer_id  NUMBER NOT NULL,
  order_date   TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  status       VARCHAR2(20) NOT NULL,
  total_amount NUMBER(14, 2) NOT NULL,
  metadata     CLOB,
  CONSTRAINT orders_customer_fk
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  CONSTRAINT orders_status_ck
    CHECK (status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED')),
  CONSTRAINT orders_total_ck CHECK (total_amount >= 0),
  CONSTRAINT orders_metadata_json_ck CHECK (metadata IS JSON)
);

CREATE TABLE order_items (
  order_id   NUMBER NOT NULL,
  line_no    NUMBER NOT NULL,
  product_id NUMBER NOT NULL,
  quantity   NUMBER(10, 2) NOT NULL,
  unit_price NUMBER(14, 2) NOT NULL,
  CONSTRAINT order_items_pk PRIMARY KEY (order_id, line_no),
  CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
  CONSTRAINT order_items_product_fk
    FOREIGN KEY (product_id) REFERENCES products(product_id),
  CONSTRAINT order_items_quantity_ck CHECK (quantity > 0),
  CONSTRAINT order_items_price_ck CHECK (unit_price >= 0)
);
~~~

In this design:

- CUSTOMERS and PRODUCTS are independent entities.
- ORDERS holds core attributes and the relationship to customers.
- ORDER_ITEMS models the one-to-many relationship with a foreign key to products.
- METADATA holds sales-channel-specific attributes validated for JSON syntax.

Querying an order and its line items with SQL:

~~~sql
SELECT o.order_id,
       o.order_date,
       o.status,
       c.full_name,
       i.line_no,
       p.product_name,
       i.quantity,
       i.unit_price
  FROM orders o
  JOIN customers c
    ON c.customer_id = o.customer_id
  JOIN order_items i
    ON i.order_id = o.order_id
  JOIN products p
    ON p.product_id = i.product_id
 WHERE o.order_id = 1001
 ORDER BY i.line_no;
~~~

Extracting an extended attribute from JSON:

~~~sql
SELECT order_id,
       JSON_VALUE(
         metadata,
         '$.salesChannel'
         RETURNING VARCHAR2(30)
       ) AS sales_channel
  FROM orders
 WHERE order_id = 1001;
~~~

Exporting an order as JSON with SQL:

~~~sql
SELECT JSON_OBJECT(
         'orderId' VALUE o.order_id,
         'orderDate' VALUE o.order_date,
         'status' VALUE o.status,
         'customer' VALUE JSON_OBJECT(
           'customerId' VALUE c.customer_id,
           'name' VALUE c.full_name
         ),
         'items' VALUE (
           SELECT JSON_ARRAYAGG(
                    JSON_OBJECT(
                      'lineNo' VALUE i.line_no,
                      'productId' VALUE i.product_id,
                      'productName' VALUE p.product_name,
                      'quantity' VALUE i.quantity,
                      'unitPrice' VALUE i.unit_price
                    )
                    ORDER BY i.line_no
                    RETURNING CLOB
                  )
             FROM order_items i
             JOIN products p
               ON p.product_id = i.product_id
            WHERE i.order_id = o.order_id
         ) FORMAT JSON
         RETURNING CLOB
       ) AS order_json
  FROM orders o
  JOIN customers c
    ON c.customer_id = o.customer_id
 WHERE o.order_id = 1001;
~~~

This SQL builds JSON from relational tables for an API response. Exact syntax and RETURNING options depend on the Oracle release; verify against your target release when deploying. If the application serves multiple output document shapes, create dedicated views or query APIs to decouple the JSON contract from table structures.

## 17. Testing Before Finalizing the Decision

Before locking in a model, test realistic scenarios:

- Adding a new attribute to a document and verifying older clients.
- Querying by relational fields and JSON/XML fields.
- Joining document data with independent entities.
- Concurrently updating the same aggregate.
- Updating multiple tables in one transaction and rolling back on failure.
- Ingesting malformed documents or documents missing required fields.
- Testing duplicate data and non-existent references.
- Measuring query latency, update cost, storage footprint, and index overhead.
- Exporting/importing data across target Oracle versions and client drivers.

Test results help determine which parts belong in relational structures, which belong in documents, and which should be exposed in both forms via views or derived data.

## 18. Conclusion

The relational model fits core data with stable structures, explicit entity relationships, and database-enforced integrity rules. The document model fits aggregates read and written together, integration payloads, and flexible structures. The hybrid model keeps keys, states, and frequently queried data in relational tables while using JSON/XML for extensions with an appropriate lifecycle.

In Oracle Database, SQL/JSON, the native JSON type from 21c, XMLTYPE, and SQL/XML functions combine document data with relational SQL. On 23ai, JSON Relational Duality Views also let applications work with relational data through a JSON interface. Whichever approach you choose, define aggregate boundaries, authoritative data sources, integrity rules, query patterns, and version compatibility before deployment. A good model keeps data consistent, queries clear, and changes controlled throughout the system lifecycle.
