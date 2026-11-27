# JSON-Relational Duality and Boundaries with JSON_TABLE or ORM in Oracle

Oracle JSON-Relational Duality Views provide a JSON document interface over data stored in a relational model. Applications can read a nested JSON document representing a business entity while performing changes through that document interface. Relational tables remain where data is stored; Oracle primary keys, foreign keys, constraints, and transactions continue to protect data integrity.

The "duality" concept expresses two views over the same data: document-oriented applications see JSON documents; relational applications see tables and relationships. There is no need to maintain two independent copies of data and manually synchronize them. A change made through a duality view is translated into changes on the underlying tables according to the declared mapping and DML permissions.

JSON_TABLE solves a different problem: taking input JSON and projecting JSON attributes/arrays into relational rows and columns within a SQL query. JSON_TABLE does not by itself create a bidirectional updatable document interface for the entire data model. An ORM operates at the application layer: mapping objects/classes to tables, managing relationships, change tracking, and persistence. An ORM is not a database view and typically requires the application to orchestrate SQL or a unit of work.

All three technologies can coexist in one system:

- Duality View: provides a JSON document interface over relational data and supports reading/writing per view capabilities.
- JSON_TABLE: turns JSON payloads into relational row sources for joining, filtering, aggregating, or loading data.
- ORM: maps the application's domain/object model to the database and manages persistence at the application layer.

This lesson belongs to the **Extended Features** topic of *Database Engine Relational Oracle*. The content focuses on:

- The model and goals of JSON-Relational Duality Views.
- How JSON documents map to tables, primary keys, and foreign keys.
- Reading, inserting, updating, and deleting via duality views.
- Per-table DML permissions in a view and optimistic concurrency.
- Distinguishing duality views from JSON_TABLE, JSON_VALUE, and JSON_QUERY.
- Distinguishing database-native duality from an ORM.
- REST/GraphQL integration and application APIs at an architectural level.
- Schema design, validation, transactions, and performance.
- Version limits, security, migrations, and hands-on exercises.

## 1. JSON Documents and the Relational Model

### Relational Model

In the relational model, data is divided into tables and linked via keys. For example, an order and its line items:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(200) NOT NULL,
    email VARCHAR2(320)
);

CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date TIMESTAMP NOT NULL,
    status VARCHAR2(30) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_item_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    product_code VARCHAR2(50) NOT NULL,
    quantity NUMBER NOT NULL,
    unit_price NUMBER(12,2) NOT NULL,
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
);
~~~

An order has one customer and multiple order items. The relational model represents relationships with foreign keys; applications typically join the tables to retrieve a complete order.

### Document Model

A document-oriented API might want to return:

~~~json
{
  "_id": 9001,
  "orderDate": "2026-11-14T09:30:00Z",
  "status": "CONFIRMED",
  "customer": {
    "customerId": 42,
    "name": "An Nguyen",
    "email": "an@example.test"
  },
  "items": [
    {
      "itemId": 1,
      "productCode": "KB-01",
      "quantity": 2,
      "unitPrice": 25.50
    },
    {
      "itemId": 2,
      "productCode": "MS-03",
      "quantity": 1,
      "unitPrice": 18.00
    }
  ]
}
~~~

A document groups related attributes and collections into a nested structure. If the application assembles documents itself using multiple SELECTs, it must manually handle joins, nested arrays, inserts/updates/deletes, and transactional consistency.

### Duality Bridges Both Perspectives

A JSON-Relational Duality View defines the mapping between relational tables and a JSON document. When reading the view, Oracle returns documents according to the defined structure. When writing through the view, Oracle maps changes back to the underlying tables within the scope of permitted operations.

~~~text
         Application / JSON API
                  |
             JSON document
                  |
       JSON-Relational Duality View
                  |
        Relational tables and keys
          /         |          \
      customers   orders    order_items
~~~

A duality view does not mean storing an extra independent JSON copy for each order. Relational data remains the managed source of truth; the document is a logical interface.

## 2. What Is a JSON-Relational Duality View?

A JSON-Relational Duality View is a specialized database view type that defines how one or more relational tables are represented as JSON documents. Unlike a regular SQL view that returns flat columns, a duality view returns JSON documents following the declared structure and relationships.

### Design Goals

- Provide a document-oriented API over relational data.
- Preserve constraints, transactions, and consistency of the relational database.
- Avoid duplicating data merely to serve a JSON API.
- Allow applications to use JSON without manually joining multiple tables.
- Support reads and document DML within the limits of mapping/view capabilities.
- Allow relational applications and document applications to work together on the same underlying data.

### Two Access Paths

| Path | Perspective |
| --- | --- |
| Relational | SELECT/INSERT/UPDATE/DELETE on tables and relationships |
| Document | Read or modify JSON documents through the duality view |

Both paths operate on the same underlying data. If an application updates the ORDERS table directly, documents read through the duality view reflect that change according to transaction visibility. If an application updates a document through the duality view, the corresponding tables receive the changes.

### A Duality View Is Not an Independent JSON Collection

A JSON collection stores documents in a document-store model. A duality view creates a document view over relational tables. Both models can use JSON APIs, yet differ in where data is stored, how relational constraints are enforced, how DML is mapped, and compatibility with existing SQL applications.

### Versions and Supportability

JSON-Relational Duality Views were introduced in the Oracle Database 23c line, later marketed/renamed under the Oracle Database 23ai line. Exact capabilities, syntax, object/type limits, REST/GraphQL integration, and cloud service availability depend on the release update, deployment model, and service. Before deploying, check the SQL Language Reference and JSON Developer's Guide for the exact version.

Do not assume every Oracle version that has a JSON datatype or JSON_TABLE supports duality views. JSON support has existed since older releases; duality views are a separate feature.

## 3. Mapping Documents to Relational Tables

A duality view describes a document root and child components based on table relationships.

### Root Table

The root table represents the main entity of the document, such as ORDERS. Each root row produces one document with a stable identifier. The primary key is typically used to form the document identifier field.

### Nested Tables

Child tables such as ORDER_ITEMS are represented as nested objects or arrays depending on relationships and mappings. One order has many items, so the document usually contains an items array.

### Parent-Child Relationships

The foreign key from ORDER_ITEMS.ORDER_ID to ORDERS.ORDER_ID enables Oracle to understand the relationship between root and child. Mappings must clearly define keys and cardinality so documents do not duplicate or mismatch rows.

### Shared/Reference Data

CUSTOMERS can be embedded into the order document or represented via an appropriate reference mapping. When a customer appears in multiple orders, applications must understand that updating a customer through one document can affect customer data shared by other documents.

### One Row or Multiple Rows?

- A root row typically identifies a single document.
- Child rows can be grouped into an array.
- A one-to-one relationship can become a nested object.
- Many-to-many relationships usually require mapping via a junction table and explicitly defined semantics.
- A table can participate in multiple duality views; understand the update scope and permissions of each view.

### Primary Key as the Foundation of Identity

A stable primary key helps Oracle identify rows when a document is updated. Do not use mutable attributes such as name, email, or description as document identity without special reason. Changing a key can affect document identity, foreign keys, and client caching.

## 4. Syntax for Creating a Duality View

Creating a duality view uses `CREATE JSON RELATIONAL DUALITY VIEW` together with a `SELECT JSON` expression. The `SELECT` describes JSON fields and nested relationships; table references can declare INSERT, UPDATE, and DELETE permissions allowed through the view.

Illustrative example following Oracle 23ai duality view syntax:

~~~sql
CREATE JSON RELATIONAL DUALITY VIEW order_dv AS
SELECT JSON {
    '_id' : o.order_id,
    'orderDate' : o.order_date,
    'status' : o.status,
    'customerId' : o.customer_id,
    'items' :
        [
            SELECT JSON {
                'itemId' : i.order_item_id,
                'productCode' : i.product_code,
                'quantity' : i.quantity,
                'unitPrice' : i.unit_price
            }
            FROM order_items i WITH INSERT UPDATE DELETE
            WHERE i.order_id = o.order_id
        ]
}
FROM orders o WITH INSERT UPDATE DELETE;
~~~

This is a simplified example to illustrate structure. Verify exact syntax, annotations, datatype mappings, nested query restrictions, and privilege requirements in the SQL Language Reference for your running release before executing. If adding a customer object, define the nested relationship and appropriate DML permissions on CUSTOMERS.

### JSON Object Constructor

`JSON { ... }` constructs an object with the defined fields. JSON field names can differ from relational column names. For example:

- order_id -> _id
- order_date -> orderDate
- product_code -> productCode

This is an API mapping; renaming a JSON field does not rename the column in the table.

### Nested Arrays

A subquery inside an array expression builds a child collection, such as items. Join conditions must use appropriate foreign/primary keys. If the join is wrong, documents may miss children or duplicate children.

### DML Annotations

INSERT, UPDATE, and DELETE annotations on table references specify which change types are allowed through the duality view. Actual permissions also depend on mapping updatability, table constraints, and database user privileges.

Do not grant broader DML permissions than the API needs. A read-only view can be designed by omitting the corresponding write operations.

### Verifying the View After Creation

Check the object in USER_OBJECTS/USER_VIEWS and use DESC or dictionary views per release. Test SELECTing a document, verifying JSON shape, key identity, and nested arrays. Do not mark a view production-ready simply because the CREATE statement succeeded.

## 5. Reading Documents via a Duality View

Applications can query duality views using SQL. How documents are retrieved and the returned column name depend on the view definition and release.

Conceptual example:

~~~sql
SELECT data
FROM order_dv
WHERE JSON_VALUE(data, '$._id') = '9001';
~~~

Some duality views expose a JSON document column named DATA; confirm actual metadata with `DESC ORDER_DV` or the data dictionary. Predicates can be written appropriately for the datatype and JSON view definition.

### Filtering by Key

The document identifier should be used to retrieve a specific document. For APIs, define endpoints by stable keys and avoid parsing the entire document just to locate a root row when the view provides suitable relational keys/filters.

### Filtering Nested Fields

JSON_VALUE, JSON_EXISTS, or JSON SQL operators can be used to filter on document fields. The optimizer may push predicates or rewrite queries depending on the view definition and release; inspect execution plans for critical workloads.

### Querying Nested Arrays

When analyzing child items as relational rows, you can use JSON_TABLE on the returned document. However, if suitable relational tables already exist, querying the tables directly can be simpler and avoid unnecessary JSON serialization/parsing.

### Document Size

Large documents can include many child rows. APIs should consider pagination, projection, and payload limits. Not every endpoint needs to return the entire nested collection for an order.

## 6. Inserting, Updating, and Deleting via a Duality View

A standout feature of duality views is performing DML through a document interface. Oracle maps document changes back to the underlying tables according to the view structure, DML annotations, key relationships, and constraints.

### Inserting a Document

An INSERT creating a new document can create both the root row and child rows based on the nested document:

~~~sql
INSERT INTO order_dv (data)
VALUES (
    JSON('{
      "_id": 9002,
      "orderDate": "2026-11-14T10:00:00",
      "status": "NEW",
      "customerId": 42,
      "items": [
        {
          "itemId": 21,
          "productCode": "KB-01",
          "quantity": 1,
          "unitPrice": 25.50
        }
      ]
    }')
);
~~~

This example illustrates the document column type and how JSON is passed; confirm column names, JSON constructors, and view datatype binding in your release. All required fields, primary keys, foreign keys, defaults, and DML permissions must be valid. If a document omits a NOT NULL field without a default, the insert can fail.

### Updating a Document

An update can modify a field inside the document:

~~~sql
UPDATE order_dv
SET data = JSON_TRANSFORM(
    data,
    SET '$.status' = 'CONFIRMED'
)
WHERE JSON_VALUE(data, '$._id') = '9002';
~~~

This illustrates updating a document with JSON_TRANSFORM. Verify DML syntax and JSON_TRANSFORM support on the exact release. With a duality view, the mapping must permit UPDATE on the modified table/field.

### Deleting a Document

~~~sql
DELETE FROM order_dv
WHERE JSON_VALUE(data, '$._id') = '9002';
~~~

Deleting a document can delete the root row and child rows according to defined mapping/cascade semantics and constraints. Do not assume every nested table automatically cascades; check foreign key ON DELETE behavior, delete permissions, and the view definition.

### Transactions

DML through a duality view still participates in Oracle transactions:

~~~sql
UPDATE order_dv
SET data = JSON_TRANSFORM(
    data,
    SET '$.status' = 'SHIPPED'
)
WHERE JSON_VALUE(data, '$._id') = '9002';

-- Other DML operations can be performed within the same transaction.
COMMIT;
~~~

COMMIT makes changes durable; ROLLBACK before COMMIT cancels uncommitted DML per transaction semantics. An important difference from DDL migrations is that DML via a duality view does not issue an implicit commit.

### Not Every JSON Patch Is Updatable

A document may contain computed, derived, or read-only fields. If a field does not map to an updatable column, Oracle may reject the change. Nested structures, key mappings, table annotations, and constraints govern valid operations.

### Checking Row Counts

After DML, check SQL%ROWCOUNT in PL/SQL or the affected row count from the driver. For APIs, return appropriate statuses when a document does not exist, an update matches nothing, or a conflict occurs. Do not return HTTP success simply because the request JSON parsed cleanly.

## 7. Per-Table Write Permissions and View Boundaries

A duality view can allow or restrict DML operations on individual table references. This enables a document API to allow updates only on intended parts of the data.

### Root and Child Permissions

For example, an order API might allow:

- INSERT/UPDATE on the root order.
- INSERT/UPDATE/DELETE on order items.
- Read-only access to customer details.

In that case, CUSTOMER data must not be modifiable just because a customer object appears in the document. Permissions for each table in the view should be explicitly declared.

### View Capabilities Do Not Replace Database Privileges

Users need appropriate privileges on the duality view and underlying privileges per Oracle rules. Table DML annotations define the view's capabilities; GRANT/REVOKE govern which users may access the view. Least privilege still applies.

### Read-Only Duality Views

If an API is read-only, omit write annotations or design the view as non-updatable. Use a dedicated account for read-only workloads and never grant UPDATE/INSERT/DELETE merely to avoid integration errors.

### Constraints Are Not Bypassed

DML through a duality view must still obey relational constraints on the underlying tables. Foreign keys, unique keys, check constraints, and NOT NULL continue to protect data. A syntactically valid JSON document does not mean business-valid data.

### Shared Child/Reference Data

If a document embeds customer, product, or account information shared by multiple root documents, updating that object can affect other documents. API design must distinguish embedded representation from true ownership. Do not allow updating shared entities through a root document if the business does not want write permissions propagating to shared entities.

## 8. Optimistic Concurrency and ETag

Multiple clients may read the same document and then update it nearly simultaneously. If client B writes after client A without detecting that the data changed, A's update may be overwritten or client B may lose recent changes.

### Optimistic Concurrency

Optimistic concurrency allows multiple clients to read concurrently, then checks on write that the document is still at the version the client read. If the document has changed, the stale update is rejected so the client can re-read and merge changes.

### ETag in Duality Documents

Duality views can provide ETag metadata computed by Oracle from document data per the feature's mechanism. An ETag represents document state and helps detect changes between read and write. The REST layer can use ETag/If-Match for conditional updates depending on API integration/version.

General flow:

~~~text
Client A                  Database
   |                         |
   |---- GET document ------>|
   |<--- JSON + ETag --------|
   |                         |
Client B updates document    |
   |                         |
   |---- PUT with old ETag ->|
   |<--- conflict/stale -----|
   |                         |
Client A rereads latest      |
and merges intended change   |
   |                         |
   |---- conditional PUT --->|
   |<--- success + new ETag -|
~~~

### ETag Is Not a Business Version

ETag is a concurrency/representation token; it should not replace business order versions, audit sequences, or event numbers if the application needs those semantics. Maintain a separate version column for business logic.

### Handling Conflicts

When an ETag no longer matches:

1. Do not blindly retry the same old payload.
2. Read the latest document.
3. Identify which fields were changed by someone else.
4. Merge according to business rules or ask the user to resolve.
5. Send a conditional update with the new ETag.

### Atomicity of Document Updates

A document can span multiple tables. DML through a duality view executes within an Oracle transaction; if a constraint or child operation fails, the transaction must roll back so partial changes are not left behind unintentionally. Applications must handle exceptions and commit boundaries properly.

## 9. JSON_TABLE: Projecting JSON into Rows and Columns

JSON_TABLE is a SQL row source function. It takes a JSON expression (a JSON column, CLOB/BLOB/VARCHAR2 containing JSON, or suitable JSON value) along with a JSON path and returns a relational set of rows/columns for SQL to join, filter, aggregate, or insert into tables.

### Data Direction

~~~text
JSON payload / JSON column
          |
       JSON_TABLE
          |
   Relational rows/columns
          |
 SELECT / JOIN / GROUP BY / INSERT
~~~

JSON_TABLE answers the question: "I have JSON and want to process its attributes as relational data in SQL." A duality view answers the question: "I have relational data and want to expose it as a structured JSON document, updatable per mapping."

### Basic JSON_TABLE Example

~~~sql
SELECT jt.order_id,
       jt.status,
       jt.order_date
FROM inbound_orders src,
     JSON_TABLE(
         src.payload,
         '$'
         COLUMNS (
             order_id   NUMBER        PATH '$.orderId',
             status     VARCHAR2(30)  PATH '$.status',
             order_date TIMESTAMP     PATH '$.orderDate'
         )
     ) jt;
~~~

JSON_TABLE reads each row's payload in INBOUND_ORDERS and returns relational columns. The result can be joined with CUSTOMERS, filtered by STATUS, or inserted into target tables.

### NESTED PATH for Arrays

~~~sql
SELECT jt.order_id,
       jt.status,
       item.item_id,
       item.product_code,
       item.quantity
FROM inbound_orders src,
     JSON_TABLE(
         src.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             status VARCHAR2(30) PATH '$.status',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 item_id NUMBER PATH '$.itemId',
                 product_code VARCHAR2(50) PATH '$.productCode',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt
CROSS APPLY JSON_TABLE(
    src.payload,
    '$.items[*]'
    COLUMNS (
        item_id NUMBER PATH '$.itemId',
        product_code VARCHAR2(50) PATH '$.productCode',
        quantity NUMBER PATH '$.quantity'
    )
) item;
~~~

This snippet only illustrates nested projection capabilities; in practice there is no need to declare the same array twice simultaneously as in the combined example above. Use a single JSON_TABLE with NESTED PATH when keeping parent/child columns in the same row source, or use a separate CROSS APPLY when independent processing is needed. Choose one form matching the output shape.

### Common Nested Projection Form

~~~sql
SELECT jt.order_id,
       jt.status,
       jt.item_id,
       jt.product_code,
       jt.quantity
FROM inbound_orders src,
     JSON_TABLE(
         src.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             status VARCHAR2(30) PATH '$.status',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 item_id NUMBER PATH '$.itemId',
                 product_code VARCHAR2(50) PATH '$.productCode',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt;
~~~

The result typically yields one row per array element. When an array is empty or missing, semantics of nested columns and the parent row depend on JSON path/error handling; test NULL/empty behavior per requirements.

### FOR ORDINALITY

JSON_TABLE can generate an ordinal column for array elements:

~~~sql
SELECT jt.order_id,
       jt.item_position,
       jt.product_code
FROM inbound_orders src,
     JSON_TABLE(
         src.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 item_position FOR ORDINALITY,
                 product_code VARCHAR2(50) PATH '$.productCode'
             )
         )
     ) jt;
~~~

Ordinality is useful for preserving order in an input array. It does not replace a stable primary key for items; positions can shift when clients reorder or remove elements.

### JSON_TABLE with DML

A payload can be converted into rows and inserted into a relational table:

~~~sql
INSERT INTO order_stage (
    order_id,
    status,
    product_code,
    quantity
)
SELECT jt.order_id,
       jt.status,
       jt.product_code,
       jt.quantity
FROM inbound_orders src,
     JSON_TABLE(
         src.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             status VARCHAR2(30) PATH '$.status',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 product_code VARCHAR2(50) PATH '$.productCode',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt;
~~~

JSON_TABLE here serves as a row source for INSERT SELECT. It does not update the source document itself and does not provide duality semantics.

### Error Handling and Datatype Conversion

JSON_TABLE supports options such as ERROR ON ERROR, NULL ON ERROR, DEFAULT ... ON ERROR, and related clauses per JSON SQL syntax. Choose explicit behavior for:

- Missing JSON path.
- JSON value of a type not convertible to NUMBER/DATE/TIMESTAMP.
- Array element missing a required field.
- Malformed JSON or format violations.
- Value exceeding target column precision/length.

Do not use NULL ON ERROR for every field if NULL could hide malformed data. For critical business data, prefer rejecting or logging error details into a quarantine table.

### JSON_VALUE and JSON_QUERY

- JSON_VALUE extracts a scalar (string, number, date-like scalar per conversion rules) from a JSON path.
- JSON_QUERY extracts a JSON object/array by path.
- JSON_TABLE extracts multiple values and nested arrays into a relational rowset.

They can be combined in the same query; choice depends on field count, cardinality, and desired output.

## 10. ORM: Application-Layer Object Mapping

An object-relational mapper (ORM) maps classes/objects in a programming language to relational tables and relationships. An ORM typically manages entity identity, change tracking, lazy/eager loading, SQL generation, transaction scope, and datatype mapping.

For example, a Java application might have:

~~~java
class Order {
    Long id;
    Customer customer;
    List<OrderItem> items;
    OrderStatus status;
}
~~~

The ORM maps Order to ORDERS, Customer to CUSTOMERS, and OrderItem to ORDER_ITEMS. When the application loads Order, the ORM may issue one or more SQL queries to fetch the root and related entities.

### What Does an ORM Do?

- Maps classes/properties to tables/columns.
- Maps one-to-one, one-to-many, and many-to-many relationships.
- Manages primary keys and identity maps.
- Tracks object changes and generates INSERT/UPDATE/DELETE.
- Manages units of work and transaction boundaries.
- Supports lazy/eager loading.
- May provide schema migration tooling.
- Converts datatypes between the database and language runtime.

### An ORM Is Not a Database-Native JSON View

An ORM runs inside the application process. It requires mapping metadata and a runtime library. If another application does not use the same ORM, it does not automatically share the same object model or change tracking. ORM-generated SQL is still SQL over tables; the database does not necessarily know the application's object graph.

### ORMs and Document APIs

Applications can serialize ORM entities to JSON to return from REST APIs. However, serialization does not automatically create a database-native duality view. The application must manage:

- Mapping JSON field names.
- Nested collection loading.
- Circular references.
- Lazy loading outside transactions.
- The N+1 query problem.
- Optimistic locking/version fields.
- Validation and authorization.
- Partial updates and merge semantics.

### Can an ORM Use a Duality View?

Yes, depending on whether the ORM and driver support mapping a JSON document column/value as an entity or custom type. ORMs are generally optimized for row/entity mapping, whereas duality views provide a document interface. An architecture can use an ORM for relational workflows and call duality views via native SQL/JSON APIs for document endpoints.

## 11. Comparing Duality View, JSON_TABLE, and ORM

| Criterion | JSON-Relational Duality View | JSON_TABLE | ORM |
| --- | --- | --- | --- |
| Operating layer | Database | SQL query engine | Application runtime |
| Primary data direction | Relational tables to JSON documents; document DML to relational rows | JSON to relational rows/columns | Objects/classes to relational SQL |
| Goal | Document API over a relational source of truth | Parse/ingest/project JSON in SQL | Persistence for domain objects |
| Mapping | Defined in database view | JSON paths/columns in query | Mapping metadata/config/code |
| Nested structures | Represents nested objects/arrays | NESTED PATH projects nested JSON into rows | Object graphs/collections |
| Writing data | Supports DML via view per annotations/capabilities | Primarily row projection; DML done via separate INSERT/UPDATE/MERGE | ORM generates DML per unit of work |
| Transactions | Oracle transactions on underlying tables | SQL statement/session transaction | Depends on application transaction and ORM |
| Concurrency | Can use metadata/ETag and database transactions | Managed by query/DML design | Usually uses version columns/optimistic locking or locks |
| JSON input | Document interface of the view | Input JSON parsed/projected | Serialized/deserialized in application |
| Relational links | Uses PK/FK and duality view mapping | SQL joins after projection | ORM relationship mapping |
| Use when | API/document access needs relational consistency | Loading, transforming, querying JSON payloads | Complex domain models and persistence inside the app |

### Choose Duality View When

- Applications need a JSON document API over relational data.
- Multiple clients/languages want to share one document contract.
- You want to avoid manually assembling nested JSON with multiple queries.
- You want the database to manage mappings and transactions across underlying tables.
- You want relational apps and document apps working on one source of truth.

### Choose JSON_TABLE When

- You receive JSON payloads from REST, files, queues, or JSON columns.
- You need to turn JSON into rows to join with relational tables.
- You need to load JSON into staging/target tables.
- You need to inspect/aggregate JSON data with SQL.
- You need to extract nested arrays into multiple rows.

### Choose ORM When

- The domain model lives in the application layer.
- The application needs identity maps, units of work, and relationship navigation.
- Persistence logic is tied to language classes and application transactions.
- The team wants to manage SQL mappings via ORM conventions/configuration.
- There are many database tables, and APIs do not need a database-native document interface.

### All Three Can Be Used Together

Example:

1. A REST endpoint receives a JSON payload.
2. JSON_TABLE validates/projects the payload into staging rows.
3. A business service uses an ORM to process domain entities.
4. Another endpoint reads order documents via a duality view.
5. Batch SQL uses relational tables directly for aggregations.

Do not force a single technology to handle every kind of workload.

## 20. Hands-On Exercise: Creating a Document View over Relational Tables

This lab requires an Oracle Database release supporting JSON-Relational Duality Views and a lab schema with privileges to create tables/views. Duality view syntax varies by release update; consult the SQL Language Reference for your exact environment before running.

### Step 1: Create Relational Tables

~~~sql
CREATE TABLE lab_customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL
);

CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    CONSTRAINT fk_lab_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers(customer_id)
);

CREATE TABLE lab_order_items (
    item_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    product_code VARCHAR2(30) NOT NULL,
    quantity NUMBER NOT NULL,
    CONSTRAINT fk_lab_items_order
        FOREIGN KEY (order_id)
        REFERENCES lab_orders(order_id)
);
~~~

### Step 2: Load Sample Data

~~~sql
INSERT INTO lab_customers VALUES (10, 'Customer A');
INSERT INTO lab_orders VALUES (1001, 10, 'NEW');
INSERT INTO lab_order_items VALUES (1, 1001, 'P-01', 2);
INSERT INTO lab_order_items VALUES (2, 1001, 'P-02', 1);
COMMIT;
~~~

### Step 3: Create the Duality View

Conceptual example:

~~~sql
CREATE JSON RELATIONAL DUALITY VIEW lab_order_dv AS
SELECT JSON {
    '_id' : o.order_id,
    'status' : o.status,
    'customerId' : o.customer_id,
    'items' : [
        SELECT JSON {
            'itemId' : i.item_id,
            'productCode' : i.product_code,
            'quantity' : i.quantity
        }
        FROM lab_order_items i WITH INSERT UPDATE DELETE
        WHERE i.order_id = o.order_id
    ]
}
FROM lab_orders o WITH INSERT UPDATE DELETE;
~~~

This is a minimal mapping pattern, omitting nested customer objects to focus on the root-child relationship. Verify exact syntax and any annotations/requirements for your installed release.

### Step 4: Read Documents

~~~sql
DESC lab_order_dv;

SELECT data
FROM lab_order_dv;
~~~

Verify the JSON contains _id, status, customerId, and the items array. If the document column name differs from DATA, use the actual name shown by DESC.

### Step 5: Update the Relational Table

~~~sql
UPDATE lab_orders
SET status = 'CONFIRMED'
WHERE order_id = 1001;

COMMIT;
~~~

Re-read the duality view and verify the document reflects the new status. This demonstrates relational DML and the document view seeing the same underlying data.

### Step 6: Update via the Duality View

If the view and document column support DML in your release:

~~~sql
UPDATE lab_order_dv
SET data = JSON_TRANSFORM(
    data,
    SET '$.status' = 'SHIPPED'
)
WHERE JSON_VALUE(data, '$._id') = '1001';

COMMIT;
~~~

Query LAB_ORDERS directly to verify the status changed. If syntax or column names differ, follow your release documentation.

### Step 7: Use JSON_TABLE to Project Items

~~~sql
SELECT jt.order_id,
       jt.item_id,
       jt.product_code,
       jt.quantity
FROM lab_order_dv d,
     JSON_TABLE(
         d.data,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$._id',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 item_id NUMBER PATH '$.itemId',
                 product_code VARCHAR2(30) PATH '$.productCode',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt;
~~~

This example shows JSON_TABLE consuming documents produced by a duality view to return child items as relational rows. In real workloads, if only item data is needed and LAB_ORDER_ITEMS is available, querying the table directly can be more efficient.

### Step 8: Check Constraints and Privileges

~~~sql
SELECT constraint_name, constraint_type, status, validated
FROM user_constraints
WHERE table_name IN (
    'LAB_CUSTOMERS',
    'LAB_ORDERS',
    'LAB_ORDER_ITEMS'
)
ORDER BY table_name, constraint_name;

SELECT table_name, privilege, grantee
FROM user_tab_privs
WHERE table_name = 'LAB_ORDER_DV';
~~~

Try inserting a document with a nonexistent customer_id to confirm the foreign key protects data if the view permits inserts. Try updating a disallowed field to observe DML capability enforcement.

### Step 9: Check Concurrency

1. Session A reads the document and ETag/metadata if returned by the view/API.
2. Session B updates the status.
3. Session A attempts an update using the old token/version via the API or supported conditional update mechanism.
4. Confirm the conflict is detected and the application does not overwrite Session B's change.

Do not assume a plain SQL UPDATE automatically checks ETags without using the proper concurrency mechanism of the duality view/API.

### Step 10: Clean Up the Lab

~~~sql
DROP VIEW lab_order_dv;
DROP TABLE lab_order_items PURGE;
DROP TABLE lab_orders PURGE;
DROP TABLE lab_customers PURGE;
~~~

Confirm DROP VIEW syntax/object type according to how duality views are registered in your release. Only drop lab objects created by this exercise.

## 21. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| CREATE JSON RELATIONAL DUALITY VIEW not recognized | Database release/service does not support it or wrong syntax | Confirm version, RU, SQL Language Reference, and feature availability. |
| Table mapping rejected | Missing primary key, unclear relationship, or unsupported table/type | Check PK/FK, cardinality, and supported object restrictions. |
| DML through view rejected | Table annotations/capabilities do not permit the operation | Review view definition, DML privileges, and constraints. |
| Document insert fails | Missing NOT NULL field, key, or invalid foreign key | Validate JSON shape and relational constraints before inserting. |
| Nested array missing or duplicating elements | Wrong join/cardinality mapping or unsuitable child key | Check FKs, join conditions, and child identity. |
| Shared customer updated from order document | Shared entity included in mapping with write permissions | Separate ownership/API boundaries and restrict table DML permissions. |
| JSON_TABLE returns NULL | Nonexistent path, datatype conversion, or error handling | Check JSON payload, path, ON ERROR, and datatypes. |
| JSON_TABLE multiplies row counts | Nested array cardinality or multiple nested paths | Determine desired row pattern and join cardinality. |
| ORM generates too many queries | Lazy loading/N+1 or poor fetch plan | Use fetch joins, batch fetching, projections, and query logging. |
| Document update overwrites recent changes | Optimistic concurrency not checked | Use ETag/version and handle conflicts. |
| REST API returns unclear errors | Exception mapping/authorization not designed | Map database errors to safe API statuses, log request IDs. |
| Document response too large | Unbounded nested arrays | Use pagination, projection, child collection endpoints, or filters. |

### Diagnostic Checklist

1. Does the Oracle Database release and service support duality views?
2. Is the view built from the right root table and relationships?
3. Do root/child tables have suitable keys?
4. Do table DML annotations permit the operation?
5. Does the database user have the required privileges?
6. Does the JSON document have fields/types satisfying constraints?
7. Do nested paths/joins yield the right cardinality?
8. Is ETag/version checked during concurrent updates?
9. Does the execution plan use the right keys/indexes?
10. Are API authorization and tenant filters enforced?

## 22. Production Deployment Checklist

### Data Model

- Root document has a stable primary key.
- Child relationships have clear foreign keys.
- Shared entities have clear ownership and update boundaries.
- Relational constraints protect invariants.
- Document shape exposes only necessary fields.

### Duality View

- View syntax verified for the release.
- Root/nested mappings and cardinality tested.
- INSERT/UPDATE/DELETE capabilities scoped down.
- Read-only fields and derived fields identified.
- ETag/optimistic concurrency understood and tested.

### Application/API

- REST/GraphQL layer enforces authentication/authorization.
- Request validation, payload sizing, and pagination.
- Error mapping for missing documents, constraints, and conflicts.
- Retry/idempotency and transaction boundaries.
- Document contract versioning and backward compatibility.

### Performance

- Appropriate indexes on root/foreign keys.
- Nested arrays do not create oversized documents.
- Query plans and actual runtime measured.
- JSON_TABLE projects only required fields.
- ORM fetch strategy avoids N+1 and over-fetching.
- Load tested with realistic document sizes and concurrency.

### Operations

- Database version/RU and service entitlement verified.
- DDL migrations and rollback/roll-forward plans prepared.
- Audit/log redaction and monitoring.
- Backup/recovery and schema exports.
- Deployment/rollback rehearsed on a clone environment.

## 23. Self-Check Questions

1. **What is a JSON-Relational Duality View?** A database view producing JSON documents over relational tables that can support DML per its mapping.
2. **Is data stored as a duplicate JSON copy?** Not necessarily; relational tables remain the underlying data store.
3. **Why is it called duality?** The same data can be viewed through both a relational model and a JSON document model.
4. **What is the role of the root table?** Identifies the root entity/document.
5. **What are foreign keys used for?** Describing parent-child relationships in the relational model and supporting mappings.
6. **What do DML annotations mean?** Specify which INSERT/UPDATE/DELETE operations are allowed through a table reference in the view.
7. **Does a duality view bypass constraints?** No; relational constraints on underlying tables still apply.
8. **What does ETag help with?** Detecting whether a document has changed since the client last read it.
9. **Is ETag a business version?** No; business versions have their own semantics.
10. **What does JSON_TABLE do?** Projects JSON fields/arrays into relational rows and columns.
11. **Does JSON_TABLE create an updatable document API?** No; it is a row source inside SQL.
12. **What is NESTED PATH used for?** Projecting nested JSON arrays/objects into child columns/rows.
13. **What is FOR ORDINALITY used for?** Generating sequence numbers for array elements.
14. **How does JSON_VALUE differ from JSON_QUERY?** JSON_VALUE extracts scalars; JSON_QUERY extracts JSON objects/arrays.
15. **What does an ORM do?** Maps application objects/classes to tables and manages persistence/units of work.
16. **Is an ORM a database view?** No; an ORM operates in the application runtime.
17. **Can duality views be used alongside an ORM?** Yes, if the ORM/driver supports it or the application calls the view via native SQL/APIs.
18. **When should you use JSON_TABLE?** When you need to ingest, validate, query, or transform JSON into relational rows.
19. **When should you use a duality view?** When you need a document interface over a relational source of truth.
20. **When is an ORM appropriate?** When application domain models and object lifecycles need persistence mapping.
21. **Can all three be used in one system?** Yes; each technology addresses a different access direction/layer.
22. **Does a duality view automatically create a REST API?** No; API integration/configuration is required.
23. **What can happen when a customer is embedded in multiple orders?** Updating via one document can affect shared customer data.
24. **Why is pagination needed for nested arrays?** To avoid large document payloads and excessive resource consumption.
25. **What risk does JSON_TABLE NULL ON ERROR carry?** It can hide malformed payloads or datatype conversion errors.
26. **Does a duality view replace relational schema design?** No; keys, constraints, and data ownership remain essential.
27. **Do V$OPTION or feature availability prove entitlement?** No; contracts/license documents must be checked.
28. **What must be tested before production?** Version support, mappings, DML capabilities, concurrency, security, performance, and recovery.

JSON-Relational Duality Views provide a document interface over relational tables, allowing document-oriented and relational applications to share a single source of truth. JSON_TABLE works in the opposite direction: projecting JSON inputs into rows/columns for SQL; ORMs map application objects and manage persistence at the application layer. Choose a duality view when you need JSON document CRUD over relational data, JSON_TABLE when you need to ingest/query JSON payloads, and an ORM when you need domain object lifecycles. All three technologies can work together. Before production, verify release support, keys/relationships, DML permissions, constraints, ETag concurrency, API authorization, payload sizes, and query performance.

## 12. Duality Views vs. JSON Columns and JSON Collections

Oracle supports storing JSON in relational columns (for example, the native JSON type in supported releases, or VARCHAR2/CLOB/BLOB with an IS JSON constraint). This differs from a duality view.

### JSON Column

A JSON column stores a document as a value inside a row:

~~~sql
CREATE TABLE api_events (
    event_id NUMBER PRIMARY KEY,
    payload JSON
);
~~~

The native JSON datatype and exact syntax depend on the release. In older releases, JSON is typically stored in VARCHAR2/CLOB/BLOB with corresponding constraints/validation.

A JSON column fits when documents are stored directly, schemas are flexible, and relational decomposition per field is unnecessary.

### Duality View

A duality view presents a document assembled from multiple relational rows/tables. Data remains stored in a relational schema and subject to relational constraints.

### JSON Collection/Document Store

Document collections manage JSON documents in a document-store model, with product- and release-specific APIs/indexing/operations. A duality view is not an independent collection; it is a view over relational tables.

### Comparison Table

| Model | Where Is Data Stored? | Strengths | Things to Watch |
| --- | --- | --- | --- |
| Relational tables | Relational columns and rows | Constraints, joins, SQL, normalization | Applications may have to construct JSON themselves |
| JSON column | One JSON value inside a row | Flexible payload storage, schema evolution | Validation/indexing and query paths |
| JSON collection | Document store | Document CRUD and document APIs | Relational constraints/joins differ from table models |
| Duality view | Underlying relational tables | JSON interface over relational source of truth | Mappings, DML capabilities, and feature/version limits |

## 13. REST and GraphQL Integration

Duality views can serve as the foundation for document APIs. The API layer can expose document reads/writes over REST or GraphQL per supported tooling and releases.

### Roles of the Database and API Layer

- Duality view defines the document shape and relational mapping.
- Database enforces constraints, transactions, and DML capabilities.
- API layer handles authentication, authorization, routing, HTTP semantics, and payload limits.
- Client manages ETags/versions and retry/conflict behavior.

### REST Endpoints

Conceptual endpoints:

~~~text
GET    /orders/9002
POST   /orders
PUT    /orders/9002
PATCH  /orders/9002
DELETE /orders/9002
~~~

REST services can map endpoints to a duality view, but URL/method behavior is not automatically generated just because the view exists. Configure REST services/ORDS or appropriate application middleware.

### HTTP Statuses

The API should distinguish:

- 200/201: successful read or creation.
- 204: successful update/delete with no response body needed.
- 400: invalid JSON or malformed request shape.
- 401/403: authentication/authorization failure.
- 404: document does not exist.
- 409: conflict per business rule or concurrency.
- 412: precondition failed, e.g., ETag mismatch if API uses If-Match.
- 500: unexpected server/database error.

Exact status mapping depends on the API framework. Never expose raw SQL errors or database credentials in responses.

### GraphQL

GraphQL lets clients request a specific shape. A duality view can be a document data source for resolvers/services, yet GraphQL schemas, authorization, pagination, and mutation semantics must still be designed. A duality view does not automatically become a GraphQL API without an integration layer.

### Do Not Put Every Child Array into a Single Response

An order can have tens of thousands of items. APIs should support pagination/filtering or separate endpoints for child collections if view/API integration permits. Oversized aggregate documents increase memory, network payloads, and latency.

## 14. Performance and Query Planning

Duality views simplify document access but do not eliminate relational work. Oracle still must read root/child rows, perform joins, construct the JSON representation, and apply predicates.

### Influencing Factors

- Number of tables and nesting depth.
- Number of child rows per root document.
- Primary/foreign key indexes.
- Predicate selectivity and filtering by root ID.
- Returned document size.
- Number of serialized fields.
- Concurrent updates and lock contention.
- Network payload and application JSON parsing.

### Indexes on Relational Keys

A primary key on the root table helps locate documents. Indexes on child foreign keys commonly help joins, child lookups, and DML behavior. Do not blindly index every JSON field; identify real query predicates and inspect plans.

### Avoid Oversized Documents

A document can aggregate many child records. If every order has tens of thousands of items, always returning the entire array consumes CPU/memory and increases network transfer. Consider:

- Aggregate documents containing only the child data needed for the use case.
- Separate endpoints for paginating items.
- Limiting returned element counts.
- Filtering by root key before assembling the document.
- Never querying the entire duality view and filtering in the application.

### Inspecting Execution Plans

~~~sql
EXPLAIN PLAN FOR
SELECT data
FROM order_dv
WHERE JSON_VALUE(data, '$._id') = '9002';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN is an estimated plan. For real workloads, collect actual cursor plans and runtime statistics using appropriate methods. Confirm the optimizer uses key access paths and is not scanning/assembling excessive documents.

### Comparing with Direct Relational Queries

If a report needs to SUM quantities by product across millions of order items, querying ORDER_ITEMS directly is usually more natural and efficient than assembling JSON documents and re-parsing them with JSON_TABLE. Duality views suit document access; not every analytical SQL query should go through a document representation.

### JSON_TABLE Performance

JSON_TABLE incurs parsing/path evaluation and row-source generation costs. Optimize by:

- Projecting only needed fields.
- Choosing specific JSON paths.
- Avoiding parsing the same payload multiple times in one query where possible.
- Using appropriate datatypes to avoid repeated conversions.
- Checking cardinality estimates for nested arrays.
- Storing validated JSON with an appropriate datatype/constraint.

### ORM Performance

ORMs can emit N+1 queries, load too many columns, or generate suboptimal SQL. Use fetch plans, batching, projections, query logging, and execution plan reviews. An ORM is not automatically faster than direct SQL.

## 15. Consistency, Transactions, and Locking

A duality view is a database interface over relational data. DML operations through the view obey Oracle transaction and constraint semantics.

### One Document, Multiple Tables

If a document contains a root row and child rows, a single document DML operation can affect multiple tables. The database must apply changes per the mapping and transaction. The application should commit after all operations succeed; on error, roll back the uncommitted transaction.

### Concurrent Updates

Two clients can update the same document or related child records. Use ETag/optimistic concurrency or appropriate version control to detect stale updates. Do not assume all field-level updates merge automatically.

### Row Locks

DML through a duality view can lock the modified relational rows. A large document with many child rows can increase row lock counts and transaction duration. Keep transactions short and avoid external API calls while holding locks.

### Concurrent Relational Applications

One application might update ORDERS directly while another updates ORDER_DV. Both operate on the same underlying tables. Align business rules, versioning, and transaction boundaries; a duality view does not create an isolated data zone.

### Read Consistency

Document SELECTs obey Oracle read consistency. When querying multiple documents or separate endpoints, they may be read at different statement snapshots. If the business requires a consistent snapshot across multiple requests, design an appropriate transaction/SCN strategy.

### Shared Entities

A customer is referenced by many orders. Updating a customer via an order document can change information displayed in other orders. If the business wants customers managed only through a separate endpoint, design view permissions and API boundaries to prevent shared-entity updates from order documents.

## 16. Security and Authorization

A JSON document interface does not reduce security requirements. Both database objects and API endpoints must be protected.

### Least Privilege

- Create separate database users per service/application role.
- GRANT only necessary privileges on the duality view.
- Never grant SYSDBA/DBA to API accounts.
- Restrict direct DML on underlying tables if applications must go through the view/API contract.
- Use read-only accounts for reporting.

### Row-Level Security

If users should only see orders for their own tenant/customer, enforce authorization in the API and/or database row-level security (VPD/FGAC) per design. Do not assume hard-to-guess document IDs act as a security boundary.

### Tenant Isolation

Document keys should be combined with tenant predicates/authorization. APIs must verify tenant identity on every request; never accept a client-supplied tenant_id and trust it blindly.

### Field-Level Access

Do not expose password hashes, internal flags, PII, or sensitive columns merely because they exist in the relational table. Document mappings should include only fields needed by the API. For sensitive fields, use separate views or control policies.

### SQL Injection and JSON Paths

Never concatenate JSON paths, filters, or SQL fragments from untrusted input. Use bind variables and validation. JSON payloads also need size limits, nesting depth limits, and value validation against the business schema.

### Auditing

Audit the API principal, database user, action, document key, request ID, and timestamp. Do not log full JSON documents if they contain sensitive data. Apply appropriate redaction and retention policies.

## 17. Schema Evolution and Document Versioning

Relational schemas and JSON document contracts can evolve independently across releases. A column change should not automatically break JSON clients.

### Additive Changes

Adding optional JSON fields is usually more backward-compatible than renaming or removing existing fields. Older clients should ignore unknown fields; newer clients must handle potentially absent fields.

### Renaming Fields

If a JSON field name changes, consider maintaining an alias/compatibility layer or versioning the API. Do not change field contracts without coordinating client releases.

### Required Fields

Adding a required field can cause inserts from older clients omitting that field to fail. Provide defaults, server-side derivations, or a new API version.

### Relational Migrations

When altering underlying tables:

1. Expand the schema in a compatible way.
2. Update the duality view mapping.
3. Deploy compatible client/server code.
4. Backfill data if needed.
5. Validate document shapes and relational constraints.
6. Contract old structures only after all consumers have migrated.

### View DDL and Dependent Objects

Changing a duality view can affect REST endpoints, client document schemas, grants, and application code. Store DDL, check dependencies, version document contracts, and test insert/update/delete after every migration.

### Backward Compatibility

Do not remove JSON fields, change types, or switch a nested array to an object in one release while old clients still rely on the old contract. Use versioned endpoints or a migration period.

## 18. Limitations and Items to Verify

Duality view capabilities depend on the Oracle Database release and release update. Before production, verify:

- Whether the feature is supported in the exact database version/service.
- Syntax of CREATE JSON RELATIONAL DUALITY VIEW and table annotations.
- Supported table types, datatypes, constraints, and relationships.
- DML support for nested inserts/updates/deletes and shared tables.
- Key generation and document identity rules.
- ETag/optimistic concurrency semantics.
- REST/GraphQL integration and ORDS version.
- Security policies, privileges, and audit behavior.
- Partitioning, replication, standby, and cloud-service restrictions.

### Do Not Treat a Duality View Like a Regular Updatable View

Duality view DML capabilities are governed by feature-specific rules. Do not assume every updatable SQL view can be converted into a duality view, or that every JSON patch translates into arbitrary table DML.

### Do Not Use Duality Views to Replace Relational Schema Design

Primary keys, foreign keys, unique constraints, normalization, and data ownership still need sound design. Document representations cannot fix a relational schema with weak keys, duplicated data, or unclear business rules.

### Do Not Use JSON_TABLE as a Duality View

JSON_TABLE does not define a persistent document API and does not provide duality DML semantics. It is a row source within a SQL statement.

### Do Not Use an ORM as the Sole Authorization Boundary

Database privileges, row-level security, and API authorization remain necessary. ORM mappings can be bypassed by native SQL, batch jobs, or other applications.

## 19. Choosing Technology by Use Case

### Order Document API on a Relational Database

If orders, customers, and items are already normalized in relational tables yet a REST API needs a readable/writable JSON aggregate, a duality view is worth considering. The database preserves constraints and transactions; the application works with the document shape.

### Importing JSON from Partners

If a system receives files/HTTP payloads containing thousands of orders and needs to validate and load them into staging tables, JSON_TABLE fits well. It turns JSON arrays into rows for joining reference data, detecting errors, and inserting into relational tables.

### Complex Domain Model in Java

If an application has rich domain entities, business methods, relationships, and units of work, an ORM can be appropriate. Use the ORM to manage persistence; document endpoints can call duality views via native SQL if needed.

### Reporting and Analytics

If a workload needs grouping, summing, joining, and window functions over millions of rows, prefer direct relational SQL. Do not serialize documents and then use JSON_TABLE to reconstruct relationships that already exist.

### Event Payloads

If payloads are immutable events with flexible schemas mostly stored/retrieved as whole documents, a JSON column or document collection may fit better than a duality view. If relational constraints must be enforced and joined with master data, consider relational tables + JSON_TABLE or a duality view depending on access patterns.

### Decision Table

| Question | If the Answer Is Yes | Technology to Consider |
| --- | --- | --- |
| Is data already normalized across multiple relational tables? | Yes | Duality view if a document API is needed |
| Is the current input JSON that needs to become rows? | Yes | JSON_TABLE |
| Are object graphs and units of work needed in the application? | Yes | ORM |
| Is document CRUD needed over a relational source of truth? | Yes | Duality view |
| Is SQL aggregation needed on nested JSON payloads? | Yes | JSON_TABLE |
| Is a document API needed without database-side DML? | Yes | JSON view/query or API serialization; duality view may be unnecessary |
| Do event JSON payloads need to be stored as-is? | Yes | JSON column/document store |

### All Three Can Be Used Together

Example:

1. A REST endpoint receives a JSON payload.
2. JSON_TABLE validates/projects the payload into staging rows.
3. A business service uses an ORM to process domain entities.
4. Another endpoint reads order documents via a duality view.
5. Batch SQL uses relational tables directly for aggregations.

Do not force a single technology to handle every kind of workload.
