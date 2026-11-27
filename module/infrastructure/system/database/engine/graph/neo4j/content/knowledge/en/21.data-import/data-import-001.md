# Mapping from CSV, JSON, and Relational Sources to the Graph Model

## 1. From source data to a property graph

When importing data into Neo4j, the main challenge is usually not reading a CSV file or a JSON array. The harder problem is **deciding which entities become nodes, which associations become relationships, which fields are properties, and which keys identify objects across multiple imports**.

Neo4j uses the **property graph** model: nodes have labels and properties; relationships have a type, a direction, and optional properties. Source data can come from:

- **CSV**: flat tables with rows, columns, and headers; often exported by another system.
- **JSON**: nested objects, arrays, optional fields, and data sent from APIs or message brokers.
- **Relational databases**: tables with primary keys, foreign keys, join tables, and data constraints.

A data row does not necessarily correspond to a single node. A JSON array does not necessarily produce a node for every element either. **Mapping** must be based on the business questions you want to query, identifier stability, and data lifecycle.

For example, an e-commerce application needs to answer:

1. Which customer placed order O100?
2. Which order lines does order O100 have, with what quantities and unit prices at the time of purchase?
3. Which orders does product P7 appear in?
4. Which customers have ever purchased a product in the "Devices" category?

If you import everything into one giant node containing a JSON string, relationship and path queries can hardly leverage the graph's capabilities. Conversely, if you turn every scalar value into a node, the graph will bloat and queries will have to traverse many unnecessary relationships.

## 2. End-to-end source data example

Suppose the source system has four relational tables:

~~~text
customers(customer_id PK, name, tier)
orders(order_id PK, customer_id FK, status, created_at)
products(product_id PK, name, list_price_in_cents)
order_lines(line_id PK, order_id FK, product_id FK,
            quantity, unit_price_in_cents)
~~~

A minimal dataset:

**customers.csv**

~~~csv
customer_id,name,tier
C01,An,GOLD
C02,Binh,STANDARD
~~~

**orders.csv**

~~~csv
order_id,customer_id,status,created_at
O100,C01,PAID,2026-11-20T09:15:00Z
O101,C02,NEW,2026-11-21T08:00:00Z
~~~

**products.csv**

~~~csv
product_id,name,list_price_in_cents
P7,Keyboard,250000
P9,Mouse,120000
~~~

**order_lines.csv**

~~~csv
line_id,order_id,product_id,quantity,unit_price_in_cents
L1,O100,P7,2,240000
L2,O100,P9,1,120000
L3,O101,P7,1,250000
~~~

In this example, **unit_price_in_cents** on the order line is the actual price at the time of ordering; **list_price_in_cents** on Product is the current list price. You should not drop the price on OrderLine and always recompute it from Product, because later price list changes would corrupt transaction history.

Target graph model:

~~~mermaid
flowchart LR
    C["Customer<br/>customerId, name, tier"]
    O["Order<br/>orderId, status, createdAt"]
    L["OrderLine<br/>lineId, quantity, unitPriceInCents"]
    P["Product<br/>productId, name, listPriceInCents"]
    C -->|PLACED| O
    O -->|HAS_LINE| L
    L -->|FOR_PRODUCT| P
~~~

The **OrderLine** node is kept as a separate entity because each line has its own **lineId** key, quantity, and historical unit price. As a result, a single order can have two different lines referencing the same Product without being merged by mistake.

## 3. Mapping design workflow before running import commands

A safe data import workflow should follow this order:

1. **Inventory the sources**: which files/tables/APIs hold the data, field types, volume, update pattern, and access permissions.
2. **Identify keys**: which source keys are stable, whether keys are globally unique, and whether tenants or source systems must be distinguished.
3. **Sketch the graph**: nodes, labels, relationships, directions, cardinality, and properties.
4. **Define transformation rules**: parsing numbers, timestamps, booleans, string normalization, null handling, and value catalogs.
5. **Define integrity rules**: uniqueness constraints, foreign keys to reconcile, and policies for orphan records.
6. **Choose load order**: create endpoint nodes first; connect relationships after the keys exist.
7. **Dry-run on a small sample**: reconcile counts, test repeated imports, test error cases, and verify business queries.
8. **Operate batch imports**: bound transactions, log results, and manage reruns.

This is a **model-driven ETL/ELT process**, not just file format conversion.

### 3.1. Build an auditable mapping table

| Source | Target mapping | Identifying key | Main transformation | Validation |
|---|---|---|---|---|
| customers.customer_id | `(:Customer {customerId})` | customer_id | trim, keep as string | Non-null, unique within identifying scope |
| customers.name, tier | Customer properties | Same as Customer | Normalize name/tier per business rules | Tier in allowed set |
| orders.order_id | `(:Order {orderId})` | order_id | trim | Unique |
| orders.customer_id | `(:Customer)-[:PLACED]->(:Order)` | customer_id, order_id | Look up node by FK | Endpoint Customer exists |
| orders.created_at | Order.createdAt | Same as Order | ISO 8601 string → datetime | Parsed successfully |
| products.product_id | `(:Product {productId})` | product_id | Keep as string, including leading zeros | Unique |
| products.list_price_in_cents | Product.listPriceInCents | Same as Product | String → integer | Non-negative |
| order_lines.line_id | `(:OrderLine {lineId})` | line_id | Keep source key | Unique |
| order_lines.order_id | `(:Order)-[:HAS_LINE]->(:OrderLine)` | order_id, line_id | Look up both nodes | Order exists |
| order_lines.product_id | `(:OrderLine)-[:FOR_PRODUCT]->(:Product)` | line_id, product_id | Look up both nodes | Product exists |
| order_lines.quantity | OrderLine.quantity | Same as OrderLine | String → integer | Greater than 0 |
| order_lines.unit_price_in_cents | OrderLine.unitPriceInCents | Same as OrderLine | String → integer | Non-negative |

The mapping table helps engineering, data, and business teams verify where each source field goes. When the source schema changes, affected transformations and constraints can be identified immediately.

## 4. Choosing a node, relationship, or property

### 4.1. Data with its own identity and lifecycle is usually a node

**Customer**, **Order**, **Product**, and **OrderLine** each have their own key. They can be looked up, updated, or connected to other entities independently. Therefore, each type is a node candidate.

A field such as **Customer.name** is usually just a property, because users rarely need to "traverse through a name node" to query.

### 4.2. Foreign keys often become relationships, but not by a rigid one-to-one formula

In a relational database:

~~~sql
SELECT o.order_id, c.customer_id
FROM orders AS o
JOIN customers AS c ON c.customer_id = o.customer_id;
~~~

The foreign key **orders.customer_id** represents order ownership. In the graph, a sensible mapping is:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
MATCH (o:Order {orderId: $orderId})
MERGE (c)-[:PLACED]->(o);
~~~

However, relational sources may also contain foreign keys that serve purely technical purposes, audit tables, configuration tables, or associations with no value for graph queries. Only create a relationship when it expresses a genuinely useful business connection.

### 4.3. Many-to-many join tables: relationship or node?

Suppose a table **user_groups(user_id, group_id, joined_at)** has at most one row per user–group pair and the membership itself has no independent lifecycle. You can map it as:

~~~text
(:User)-[:MEMBER_OF {joinedAt}]->(:Group)
~~~

By contrast, the **order_lines** table has its own **line_id**, quantity, and historical unit price, and can contain multiple lines for the same product within one order. Modeling an **OrderLine node** preserves each record and simplifies referencing or updating individual lines.

| Criterion | Use a relationship with properties | Use an intermediate node |
|---|---|---|
| Only represents a link between two entities | Suitable | May introduce unnecessary structure |
| Multiple independent records for one endpoint pair | Requires special identity/linking design | Usually more natural |
| Join record has its own ID and lifecycle | Possible with additional modeling | Usually suitable |
| Join entity needs to link to a third party | Can become awkward to represent | Convenient |
| Queries only check relationship existence | Usually shorter | Requires an extra traversal hop |

The goal is not to convert every join table into a relationship at all costs, but to **preserve identity and semantics accurately**.

## 5. Designing stable keys and constraints

### 5.1. Keep source keys as properties

Neo4j has internal identifiers for nodes and relationships, but repeated imports and synchronization with external systems should rely on **stable business keys** such as **customerId**, **orderId**, **productId**, and **lineId**.

Do not use CSV row numbers as identifiers if row ordering can change. For codes like **"000123"**, keep them as **strings** if leading zeros are part of the identifier. Only convert to integer when the field is genuinely a numeric quantity.

### 5.2. Create constraints before importing

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT product_id_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.productId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT line_id_unique IF NOT EXISTS
FOR (l:OrderLine)
REQUIRE l.lineId IS UNIQUE;
~~~

Uniqueness constraints prevent two nodes **with the same label** from carrying the same key value when that property exists. They do not automatically require every node to have the key property. You should validate inputs and consider existence or node key constraints if your version, edition, and business rules allow.

You can inspect the schema with:

~~~cypher
SHOW CONSTRAINTS;
~~~

**Note:** If nodes with duplicate keys already exist in the database, creating a uniqueness constraint may fail. Detect and resolve duplicates according to business rules before creating the schema.

### 5.3. Keys unique only within a tenant or source scope

If Customer C01 appears in two different CRM systems, the key `customerId = 'C01'` may **not be globally unique**. You must define a namespace, for example:

~~~cypher
CREATE CONSTRAINT customer_source_id_unique IF NOT EXISTS
FOR (c:ExternalCustomer)
REQUIRE (c.sourceSystem, c.externalId) IS UNIQUE;
~~~

~~~cypher
MERGE (c:ExternalCustomer {
    sourceSystem: $sourceSystem,
    externalId: $externalId
})
SET c.name = $name;
~~~

Composite identifiers prevent two customers from two systems from being merged together by mistake. Fields must be normalized consistently before import.

## 6. Importing CSV: from flat rows to nodes

Neo4j supports **LOAD CSV** to read CSV data from configured allowed sources. For local file imports, the syntax is typically **file:///customers.csv**; the path is resolved on the **Neo4j server** side, not on the machine running Neo4j Browser or a Java application.

Depending on the Neo4j deployment (self-managed, Docker, cloud) and security configuration, file/URL access permissions may vary. In this example, assume the four files reside in the import directory that the server is allowed to read.

### 6.1. Creating Customer

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row
WHERE row.customer_id IS NOT NULL
  AND trim(row.customer_id) <> ''
MERGE (c:Customer {customerId: trim(row.customer_id)})
SET c.name = row.name,
    c.tier = row.tier;
~~~

Meaning:

- **WITH HEADERS** maps column names to keys of `row`.
- CSV values are read as **strings**; `row.customer_id` is an identifier string.
- **WHERE** filters out rows without a valid ID. In a real system, rejected rows must be **recorded during data validation**, not silently dropped.
- **MERGE** finds or creates a Customer by the constrained key.
- **SET** updates descriptive properties on re-import.

If data contains duplicate rows with the same ID but different names, SET overwrites with the value processed later. If business logic requires choosing the newest record, you must include a timestamp/version and conflict resolution logic.

### 6.2. Creating Product and converting numeric types

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///products.csv' AS row
WITH row
WHERE row.product_id IS NOT NULL
  AND trim(row.product_id) <> ''
MERGE (p:Product {productId: trim(row.product_id)})
SET p.name = row.name,
    p.listPriceInCents = toInteger(row.list_price_in_cents);
~~~

**toInteger** converts a string to an integer. Invalid input values can result in errors or null depending on the expression; do not expect the import query to fix all dirty data automatically. Validate source data before importing, such as verifying prices are non-negative integers.

### 6.3. Creating Order and the PLACED relationship

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///orders.csv' AS row
WITH row
WHERE row.order_id IS NOT NULL
  AND trim(row.order_id) <> ''
MATCH (c:Customer {customerId: trim(row.customer_id)})
MERGE (o:Order {orderId: trim(row.order_id)})
SET o.status = row.status,
    o.createdAt = datetime(row.created_at)
MERGE (c)-[:PLACED]->(o);
~~~

Customer nodes are created **before** Orders. MATCH finds the existing Customer, and only then merges Order and PLACED. If the **customer_id** FK does not match, that row does not proceed in the query; this is why you must **reconcile orphan records** before and after import.

**datetime(row.created_at)** requires a timestamp string in a format supported by Neo4j, for example **2026-11-20T09:15:00Z**. If the source has ambiguous timezones or inconsistent formats, normalize them before import.

### 6.4. Creating OrderLine with two relationships

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///order_lines.csv' AS row
WITH row
WHERE row.line_id IS NOT NULL
  AND trim(row.line_id) <> ''
MATCH (o:Order {orderId: trim(row.order_id)})
MATCH (p:Product {productId: trim(row.product_id)})
MERGE (l:OrderLine {lineId: trim(row.line_id)})
SET l.quantity = toInteger(row.quantity),
    l.unitPriceInCents = toInteger(row.unit_price_in_cents)
MERGE (o)-[:HAS_LINE]->(l)
MERGE (l)-[:FOR_PRODUCT]->(p);
~~~

On the sample dataset, the query creates **3 OrderLines**, **3 HAS_LINE**, and **3 FOR_PRODUCT** relationships if all foreign keys are valid. Relationships are created after both endpoint nodes already have identifiers.

**Note on MERGE and relationships:** The example assumes each lineId belongs to exactly one Order and one Product, and that a re-import does not reassign it to different endpoints. If source data changes the owner of the same lineId, using MERGE on the relationship as shown above can create an unintended additional link. That is a data change that must be handled with explicit migration/sync rules: reject the conflict, replace the old link, or create historical versions.

### 6.5. Verifying the graph after import

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[:HAS_LINE]->(l:OrderLine)-[:FOR_PRODUCT]->(p:Product)
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       l.lineId AS lineId,
       p.productId AS productId,
       l.quantity AS quantity,
       l.unitPriceInCents AS unitPriceInCents
ORDER BY orderId, lineId;
~~~

For the sample dataset, the query returns **3 rows corresponding to 3 order lines**, not 3 orders or 3 products. Reconcile each **lineId** against the source to verify relationships are connected accurately.

## 7. Importing JSON: splitting nested data into entities and links

JSON often contains nested objects:

~~~json
{
  "orderId": "O100",
  "customerId": "C01",
  "status": "PAID",
  "createdAt": "2026-11-20T09:15:00Z",
  "items": [
    {"lineId": "L1", "productId": "P7", "quantity": 2, "unitPriceInCents": 240000},
    {"lineId": "L2", "productId": "P9", "quantity": 1, "unitPriceInCents": 120000}
  ]
}
~~~

This JSON shape is **an order document containing a list of line items**, but when represented in a graph it should preserve separate objects with IDs. You should not store the entire **items** array as a JSON property by default if the business needs to search products across orders.

### 7.1. Passing parsed JSON as a Cypher parameter

Neo4j does not have a core Cypher command named **LOAD JSON** analogous to LOAD CSV. A plugin-free approach is to have the application read/parse JSON into a **list/map**, pass it through the Java Driver as the **$orders** parameter, and then use **UNWIND** to construct the graph.

For example, **$orders** is an array containing one or more objects structured like the JSON above. Assuming Customer and Product are already imported, you can run:

~~~cypher
UNWIND $orders AS row
MATCH (c:Customer {customerId: row.customerId})
MERGE (o:Order {orderId: row.orderId})
SET o.status = row.status,
    o.createdAt = datetime(row.createdAt)
MERGE (c)-[:PLACED]->(o)
WITH o, row
UNWIND coalesce(row.items, []) AS item
MATCH (p:Product {productId: item.productId})
MERGE (l:OrderLine {lineId: item.lineId})
SET l.quantity = toInteger(item.quantity),
    l.unitPriceInCents = toInteger(item.unitPriceInCents)
MERGE (o)-[:HAS_LINE]->(l)
MERGE (l)-[:FOR_PRODUCT]->(p)
RETURN count(l) AS importedItemRows;
~~~

Explanation:

- **UNWIND $orders AS row** turns each Order object into a row.
- MERGE Order by **orderId** and connect it to Customer.
- **UNWIND row.items AS item** creates a row for each order line, then connects it to Product.
- **coalesce(row.items, [])** treats a missing/null items list as an empty list during expansion.
- **count(l)** at the end counts the number of **processed item rows**, not the number of newly created Orders or actually newly created nodes.

If an Order has **items = []**, the earlier Order import portion can still execute, but that row does not pass through the part after UNWIND, so it will not appear in the **importedItemRows** count. If you need to report both the Order count and the item count, separate the statistics or use a different query structure.

**Important:** When a Customer/Product endpoint does not exist, MATCH drops the corresponding row. To avoid silent omissions, the application must validate foreign keys and row totals before running the actual import.

### 7.2. Reading JSON from a file or URL via APOC (optional)

Some deployments install **APOC** and allow loading JSON from properly configured sources:

~~~cypher
CALL apoc.load.json($jsonUrl) YIELD value
RETURN value;
~~~

This is an **APOC** procedure, not core Cypher LOAD CSV syntax. Support for local files, URLs, security configuration, and execution permissions depends on the Neo4j/APOC version and deployment environment. Do not assume every Neo4j server enables APOC or allows it to read arbitrary paths.

When APOC is unavailable, the application can fetch JSON from the source system, parse/validate it, and send a **list/map** parameter via the Driver as in Section 7.1. This approach is also convenient for controlling authentication, retries, error handling, and batch size.

### 7.3. Mismatches between JSON types and Neo4j properties

JSON can contain:

- **string, number, boolean, null**;
- **arrays** of objects or values;
- **nested objects**;
- dates and times represented as strings.

Neo4j supports property types suitable for primitive values, temporal types, and certain lists; **nested maps/objects cannot by default be stored directly as a node property the way JSON document stores do**. You need to decide:

- Turn an object into a **node** if it has identity and needs connections.
- Flatten child fields into **properties** if the field group is stable, useful, and valid.
- Store the raw JSON outside the graph or as a separate string if you genuinely need the payload for auditing; avoid using it in place of the primary query structure.

## 8. Importing from relational sources: handling PKs, FKs, and join tables

A SQL-to-graph migration usually requires an **extract** step before LOAD CSV or passing parameters via the Driver. The four source tables can be exported while preserving key names and business fields.

### 8.1. Classifying source tables

| Relational table characteristic | Suggested mapping direction | What to verify |
|---|---|---|
| Entity table with PK | Node with a business label | Key uniqueness, data types, lifecycle |
| 1–n FK column | Relationship between two nodes | Direction, mandatory/optional, endpoint nodes |
| n–n join table with only two FKs | Relationship between two nodes | Are multiple links allowed for the same pair? |
| Join table with payload and own PK | Relationship with properties or intermediate node | Does each record have identity, audit, lifecycle? |
| Small lookup/catalog table | Node, property, or enum based on query needs | Is traversing relationships to the catalog needed? |
| History/event table | Event node, temporal property, or separate history store | Volume, TTL, temporal queries |
| JSON column in SQL | Parse into properties/relationships or keep controlled payload | Data types and schema volatility |

Do not treat omitting a node for a SQL table as losing data. The goal is to **preserve business information and queryability** with an appropriate graph design.

### 8.2. A single FK target can have multiple meanings

For example, the **orders** table has **customer_id** representing the person who placed the order and **approved_by_user_id** representing the approver. Both FKs point to user records, yet they need relationships with distinct meanings:

~~~text
(:Customer)-[:PLACED]->(:Order)
(:User)-[:APPROVED]->(:Order)
~~~

Do not collapse all foreign keys into a generic **RELATED_TO** relationship type, because that loses semantics and makes Cypher queries harder.

### 8.3. Choosing relationship direction from query patterns

For **PLACED**, choosing the **Customer → Order** direction reads naturally as "Customer placed Order". Neo4j still supports matching relationships in both directions:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order {orderId: $orderId})
RETURN c.customerId AS customerId;
~~~

Choose one consistent directional convention in the model; there is no need to create an extra reverse relationship just for reverse lookups.

### 8.4. Foreign key constraints are not automatically recreated

In SQL, a foreign key can prevent inserting a record pointing to a non-existent PK. When importing into Neo4j with MATCH, a row pointing to a non-existent node typically **does not create a relationship**. If you only run the import command without comparing row counts, links can be missed without an obvious error.

You must build a referential integrity check step:

- List Orders whose **customer_id** is not found in the Customer list.
- List OrderLines whose **order_id** or **product_id** does not match.
- Choose a policy: **halt the batch**, **quarantine bad rows**, or **create controlled placeholders** if business rules allow.
- Reconcile actual node and relationship counts after import.

Do not create placeholder nodes for every missing FK just to make row counts match, because that can mask corrupted input data.

## 9. Normalizing data types before writing

CSV reads strings, whereas JSON/SQL may carry numeric or boolean types. A source field may need different conversions depending on the ingestion channel.

| Source data type | Target property | Rule |
|---|---|---|
| `"00128"` as an identifier code | `productId: "00128"` | Keep as string, do not drop leading zeros |
| `"2"` as quantity | `quantity: 2` | Parse integer, check > 0 |
| `"240000"` as money in cents | `unitPriceInCents: 240000` | Use integer to avoid currency precision errors |
| `"2026-11-20T09:15:00Z"` | `createdAt` of type datetime | Normalize timezone and ISO format |
| `"true"` or boolean | `active` of type boolean | Define explicit parsing rules |
| Empty string, null, or missing key | Null/absent property or error | Follow required-field rules |

Conversion example in Cypher:

~~~cypher
WITH {
    quantityText: '2',
    amountText: '240000',
    timeText: '2026-11-20T09:15:00Z'
} AS raw
RETURN toInteger(raw.quantityText) AS quantity,
       toInteger(raw.amountText) AS amountInCents,
       datetime(raw.timeText) AS createdAt;
~~~

This snippet illustrates type conversion functions, not a comprehensive input validation pipeline.

### 9.1. Nulls, empty strings, and missing fields

Across data sources:

- A **blank CSV cell** may be an **empty string**.
- **JSON null** has a different meaning from a **missing key**.
- **SQL NULL** reflects a missing value per the SQL schema.
- In Neo4j, **null is not stored as a normal property value**; setting a property to null removes that property.

Before updating with **SET c.name = row.name**, determine whether empty source data means **clear the old name**, **keep the old name**, or **raise an error**. In incremental sync, this distinction is critical.

One way to avoid overwriting with null when an API omits a field:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
SET c.name = coalesce($name, c.name)
RETURN c.customerId AS customerId, c.name AS name;
~~~

The expression above keeps the existing name if **$name = null**. It is only appropriate when null is defined as **do not update**, not when null must clear the field. Empty strings require a separate rule.

### 9.2. Normalization and data provenance

In addition to business fields, you can store metadata such as **sourceSystem**, **externalId**, **lastImportedAt**, and **sourceUpdatedAt** when lineage tracking is needed. Only store metadata that genuinely serves governance or synchronization; there is no need to copy every technical column from the source.

If the source emits multiple versions of the same record, **repeated imports with MERGE do not automatically decide which record is newer or older**. You must adopt a version/timestamp rule to prevent a late-arriving record from overwriting newer data.

## 10. Designing safe repeated imports and incremental sync

### 10.1. MERGE by key, SET by changes

~~~cypher
MERGE (c:Customer {customerId: $customerId})
ON CREATE SET c.createdAt = datetime()
SET c.name = $name,
    c.tier = $tier
RETURN c.customerId AS customerId;
~~~

When re-importing the same Customer, MERGE attempts to reuse the node by key rather than always creating a new node like CREATE. Under concurrent writes or retries, uniqueness constraints protect against duplicate nodes for the same key.

Do not put mutable fields like **name**, **tier**, or timestamps into the MERGE map:

~~~cypher
// Do not use when name can change.
MERGE (c:Customer {customerId: $customerId, name: $name});
~~~

If the name changes, the old pattern does not fully match; Neo4j may try to create an additional node or report a uniqueness violation. Put **only stable identifying keys** in MERGE.

### 10.2. Full snapshot import vs. change event import

| Data pattern | Meaning | Required handling |
|---|---|---|
| Full snapshot | File representing state at a point in time | Policy for handling nodes missing from the snapshot |
| Incremental upsert | Only new or changed records | MERGE by key, SET properties with versioning policy |
| Change data capture (CDC) | Insert/update/delete events from SQL | Map each change type and preserve event ordering |
| At-least-once event stream | An event may be redelivered | Idempotency key, duplicate control, and retries |
| Historical backfill | Large volume of older records to build initial graph | Batching, checkpoints, staged execution, verification |

**Do not infer that a record absent from an incremental batch should be deleted.** Only with a well-defined full snapshot can the application consider diffing and deleting records that no longer exist, while also evaluating the impact on relationships.

### 10.3. Deletions also need mapping rules

If the source SQL deletes an Order, the graph must decide:

- Delete the Order and its related OrderLines?
- Keep the Order as archived/soft-deleted?
- Retain transaction history for reporting?
- Which relationships to delete, and which shared nodes must be preserved?

Do not run bulk **DETACH DELETE** just because a record is no longer in the source; links may hold information that must be retained. Choose behavior based on the business lifecycle and data retention policy.

## 11. Batching, transactions, and performance

For small datasets, a single LOAD CSV statement may suffice for illustration. For millions of rows, you must control transaction size, concurrency, and error logging.

You can split data into batches and invoke multiple transactions via the Java Driver, or use **CALL ... IN TRANSACTIONS** if your Neo4j version and invocation context support that syntax. Conceptual example for Neo4j supporting variables in a subquery:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///products.csv' AS row
CALL (row) {
    WITH row
    WHERE row.product_id IS NOT NULL
      AND trim(row.product_id) <> ''
    MERGE (p:Product {productId: trim(row.product_id)})
    SET p.name = row.name,
        p.listPriceInCents = toInteger(row.list_price_in_cents)
} IN TRANSACTIONS OF 1000 ROWS;
~~~

**Version note:** Variable-import syntax in CALL subqueries and support for **IN TRANSACTIONS** vary across Neo4j versions. Check the documentation for the version you run; some client explicit transactions do not allow this batched transaction control statement. Alternatively, use your ETL/Driver batching mechanism to execute each batch in its own transaction.

Factors determining import speed:

1. **Constraints/indexes on MERGE keys** enable fast node lookup by identifier.
2. **Loading nodes before relationships** avoids searching for missing endpoints.
3. **Batch size** must fit memory, transaction duration, and write load.
4. **Concurrent worker count** must be bounded when many records touch a high-degree node.
5. **Relationship-linking queries** should MATCH explicitly by key, avoiding full label scans.
6. **Checkpoints and retries** allow resuming after failure without duplicating data.
7. **Observe DB Hits and transaction latency** to find bottlenecks instead of guessing speed from CSV line counts.

MERGE improves safe re-importability, but it does not guarantee that every operation on relationships or mutable payloads automatically resolves business conflicts. Protect each invariant according to the data model and actual concurrency level.

## 12. Java Driver application example passing normalized records

An application can read CSV/JSON/SQL into a list of maps, validate them, and send **parameters** to Neo4j. The snippet below illustrates batch-upserting Customers; it does not perform source parsing or validation.

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class CustomerImportService {
    private final Driver driver;

    public CustomerImportService(Driver driver) {
        this.driver = driver;
    }

    public long importCustomers(List<Map<String, Object>> records) {
        String cypher = """
            UNWIND $records AS row
            MERGE (c:Customer {customerId: row.customerId})
            SET c.name = row.name,
                c.tier = row.tier
            RETURN count(c) AS processedRows
            """;

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx ->
                tx.run(cypher, Map.of("records", records))
                  .single()
                  .get("processedRows")
                  .asLong()
            );
        }
    }
}
~~~

Notes:

- **Driver** is typically reused at the application level; **Session** is short-lived.
- **executeWrite** uses a managed transaction; the callback may be retried when transient errors deemed retryable by the driver occur.
- **records** must be normalized, checked for required keys, and split into appropriate batches before calling.
- **processedRows** counts the parameter rows flowing through the query, **not the number of newly created nodes**.
- Do not call external APIs with side effects inside a retryable callback unless idempotency mechanisms are in place.
- If source data contains multiple records with the same customerId but different values, decide the update rule before UNWIND.

With **Spring Data Neo4j**, you can manage transactions via services/repositories or Neo4jClient, but the principles of identity, constraints, batch importing, and correctness verification remain unchanged. A `save` method at the Java layer does not replace a mapping plan and uniqueness constraints in the database.

## 13. Input validation and post-import reconciliation

### 13.1. Validating sources before writing

For the sample files, minimum checks include:

- No Customer, Order, Product, or OrderLine is missing its identifying key.
- No two rows share the same key while carrying unintended conflicting data.
- Every **orders.customer_id** appears in Customer.
- Every **order_lines.order_id** appears in Order.
- Every **order_lines.product_id** appears in Product.
- **quantity** is a positive integer; prices are non-negative integers.
- **created_at** uses a consistent format and timezone.
- CSV headers match expected names; UTF-8 encoding is verified.
- JSON has the expected item structure; never assume a required key is always present.

When source data is invalid, decide whether to **halt the batch**, **skip the row with logging**, or **route it to a data-remediation queue**. Do not silently ignore orphan records just so the import job finishes successfully.

### 13.2. Reconciling node and relationship counts

~~~cypher
MATCH (c:Customer)
RETURN count(c) AS customerNodes;
~~~

~~~cypher
MATCH (o:Order)
RETURN count(o) AS orderNodes;
~~~

~~~cypher
MATCH (l:OrderLine)
RETURN count(l) AS lineNodes;
~~~

~~~cypher
MATCH (:Customer)-[r:PLACED]->(:Order)
RETURN count(r) AS placedRelationships;
~~~

~~~cypher
MATCH (:Order)-[r:HAS_LINE]->(:OrderLine)
RETURN count(r) AS hasLineRelationships;
~~~

~~~cypher
MATCH (:OrderLine)-[r:FOR_PRODUCT]->(:Product)
RETURN count(r) AS forProductRelationships;
~~~

For a graph containing only the sample data, expect **2 Customers**, **2 Orders**, **2 Products**, **3 OrderLines**, **2 PLACED**, **3 HAS_LINE**, and **3 FOR_PRODUCT** relationships. If the database holds other data, filter by the import's namespace/identifier before comparing.

Count reconciliation is only the first step; **having the right node count but wrong relationship wiring** is still a bug. You also need to inspect path patterns and endpoint key pairs.

### 13.3. Detecting nodes missing expected links

For example, finding Orders without a placing Customer:

~~~cypher
MATCH (o:Order)
WHERE NOT EXISTS {
    MATCH (:Customer)-[:PLACED]->(o)
}
RETURN o.orderId AS orderId
LIMIT 50;
~~~

Finding OrderLines not pointing to a Product:

~~~cypher
MATCH (l:OrderLine)
WHERE NOT EXISTS {
    MATCH (l)-[:FOR_PRODUCT]->(:Product)
}
RETURN l.lineId AS lineId
LIMIT 50;
~~~

These queries detect anomalies inside the graph, but they cannot find source rows that were completely dropped before node creation. Therefore, you must reconcile **both the source and the graph**.

### 13.4. Testing re-imports

Re-run the same test data after constraints have been created. If the mapping is designed to be idempotent, node counts by business key **must not increase** merely from re-importing. Also confirm properties and relationships have not changed unexpectedly.

Inject intentional bad data in a test environment—for example, a **lineId** with a different **orderId** than in the previous import—to verify whether the system detects the conflict or silently adds another relationship.

## 14. Common mapping pitfalls

| Mistake | Consequence | Remedy |
|---|---|---|
| Using CREATE for every row on every import | Duplicate nodes on rerun | MERGE by key with appropriate constraints |
| Treating CSV row numbers as keys | Reordering the file changes identity | Use stable business PK/IDs |
| Converting all numeric codes to integers | Drops leading zeros, merges distinct IDs | Distinguish identifier codes from quantities |
| Turning every JSON field into a node | Graph cluttered with meaningless nodes and complex queries | Keep simple fields as properties |
| Stuffing all JSON into a single string property | Cannot leverage relationship/path queries | Extract entities with identity and queryable links |
| Collapsing every join table into a single relationship | Can lose lineId and multiple lines per endpoint pair | Consider intermediate nodes |
| Importing relationships before nodes | Missing endpoints, lost relationships | Load nodes first, reconcile FKs |
| Not checking for 0-row MATCHes | Source rows silently dropped | Reconcile orphans and record counts |
| Omitting uniqueness constraints | Duplicate nodes under load or re-sync | Create schema before import |
| Relying solely on post-import counts | Fails to catch miswired endpoints | Inspect path patterns and key pairs |
| Writing null as if it meant "do not update" | Unintentionally deletes existing properties | Define explicit null semantics |
| Overwriting values with late-arriving events | Newer data reverts to older state | Use version/timestamp rules |
| Importing everything in one huge transaction | Slow, memory-heavy, hard to roll back | Batch according to system limits |
| Creating bidirectional relationships just to read backward | Redundant and hard to keep in sync | Pick one direction, MATCH in reverse when needed |

## 15. Practice exercises

### Exercise 1. From relational tables to a graph

The source has **students(id, name)**, **courses(id, title)**, **enrollments(student_id, course_id, enrolled_at)**. Each student can enroll only once per course; enrollment records have no separate ID.

**Question:** Should enrollments be mapped as a node or a relationship?

**Hint:** You can use **(Student)-[:ENROLLED_IN {enrolledAt}]->(Course)** if each student–course pair has only one enrollment and the record has no independent lifecycle. Define a policy to ensure duplicate relationships are not created for the same pair under concurrent imports.

### Exercise 2. Preserving order_lines records

The source has two order lines for the same Order and Product, but with different **line_id** values and unit prices.

**Question:** Why can using only **MERGE (Order)-[:HAS_ITEM]->(Product)** break the model?

**Hint:** Two independent records may be collapsed into a single relationship if the pattern only uses the endpoint pair. Using an **OrderLine node with lineId** is one way to preserve each line and its historical price.

### Exercise 3. Nested JSON

An API returns an Order with an **items** array, where each item contains productId, quantity, and unitPriceInCents.

**Question:** To find Orders that have included Product P7, how should the data be mapped?

**Hint:** Extract Product and OrderLine into nodes and create relationships to query across the graph. Use **UNWIND** if the JSON has been parsed into a list/map passed to Neo4j via the Driver.

### Exercise 4. Missing foreign key

An Order row has customer_id = C99, but the Customer table has no C99.

**Question:** If the import query runs MATCH Customer before MERGE Order, what happens?

**Hint:** The row without a matching Customer will not proceed, so the Order may not be created. Detect orphans from the source and handle them by policy before writing.

### Exercise 5. Customer renamed after the first import

Import 1 has C01 = "An", and import 2 has C01 = "An Nguyen".

**Question:** Which MERGE pattern avoids creating an extra Customer just because the name changed?

**Sample answer:**

~~~cypher
MERGE (c:Customer {customerId: 'C01'})
SET c.name = 'An Nguyen';
~~~

Keep **customerId** as the identifier, while **name** is an updatable property.

### Exercise 6. Post-migration verification

After importing the sample dataset, the graph has 3 OrderLines but only 2 FOR_PRODUCT relationships.

**Question:** Can we conclude the import succeeded because the node counts match?

**Hint:** No. An OrderLine may be missing its Product due to an FK error, a failed MATCH, or import logic bugs. Reconcile both relationship counts and run a query for OrderLines missing FOR_PRODUCT.

## 16. Key takeaways

**Mapping from CSV, JSON, and relational sources to Neo4j** starts with **data semantics**: choose nodes for entities with identity, relationships for meaningful connections, and properties for attributes to store. Keep stable business keys, preserve multiplicity and history when mapping join tables, and standardize data types and null handling.

For reliable imports, **create uniqueness constraints first**, load nodes before relationships, use **MERGE by key**, validate foreign keys/missing data, batch appropriately, and reconcile both counts and wiring paths. Whether the source is CSV via **LOAD CSV**, JSON as **UNWIND** parameters, or SQL tables exported through a pipeline, a good graph preserves source meaning and answers the relationship queries the application needs.
