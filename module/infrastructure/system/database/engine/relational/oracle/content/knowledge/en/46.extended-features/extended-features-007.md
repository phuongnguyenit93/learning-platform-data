# SQL Property Graph, Graph Modeling, and Queries by Supported Version

SQL Property Graph lets you model relational data as a graph consisting of **vertices**, **edges**, **labels**, and **properties**, and then query relationships using graph patterns directly in SQL. Starting in Oracle Database 23ai, Oracle provides SQL Property Graph syntax following SQL/PGQ with two core components: `CREATE PROPERTY GRAPH` to define a graph over relational tables and `GRAPH_TABLE` to match graph patterns inside a SELECT statement.

This model is useful when business questions focus on relationships and paths: which accounts a customer is linked to, through which intermediary accounts funds were transferred, who an employee reports to, which devices share an identifier, or which products are connected to other products.

SQL Property Graph does not replace the relational model. Tables remain the data source; the graph definition maps tables and columns into vertices/edges/properties to query relationships more naturally. For systems whose data already lives in Oracle Database, this adds a graph perspective without necessarily migrating all data into a separate graph database.

## 1. What Is a Graph?

A graph is a structure of vertices and edges describing relationships between entities.

- **Vertex:** represents an entity, such as a user, account, product, or city.
- **Edge:** represents a relationship between two vertices, such as a transfer, friendship, purchase, or route.
- **Label:** classifies vertices/edges, such as person, account, transfer, knows.
- **Property:** data describing a vertex/edge, such as name, balance, transaction timestamp, or weight.
- **Key:** uniquely identifies a vertex or edge within the graph.

Social network example:

~~~text
       (An) --------knows--------> (Bình)
        |                            |
        | follows                    | knows
        v                            v
      (Chi) <---------knows--------- (Dũng)
~~~

Vertices are users. Edges describe who knows whom or who follows whom. Vertex properties might be name, age, city; edge properties might be connection timestamp or relationship type.

### 1.1 Directed Graphs

A directed edge specifies a source and a destination. For example:

~~~text
(Account A) --transfers--> (Account B)
~~~

Transferring money from A to B is not the same as transferring from B to A. Therefore, the edge must preserve direction.

### 1.2 Undirected Graphs

A relationship like two people being friends can be viewed as undirected at the business layer. When stored in relational tables, you can represent one relationship with one edge and query using appropriate syntax, or store both directions if the application needs to distinguish direction. Agree on a convention so relationships are not double-counted.

### 1.3 Multigraphs and Self-Loops

Two vertices can have multiple distinct edges. For example, two accounts can transfer funds many times. Each transfer must have its own edge key; otherwise distinct transactions would be wrongly collapsed into a single relationship.

An edge can also connect a vertex to itself if the business model permits—for example, a self-referencing node. Do not automatically discard self-loops if the source data carries that meaning.

## 2. Property Graphs and Relational Data

A property graph is built from relational tables:

| Relational Table | Graph Component |
|---|---|
| PERSON table | Vertex table |
| PERSON_ID | Vertex key |
| NAME, CITY, AGE | Vertex properties |
| KNOWS table | Edge table |
| FRIENDSHIP_ID | Edge key |
| PERSON_A_ID | Source key |
| PERSON_B_ID | Destination key |
| SINCE_DATE, RELATION_TYPE | Edge properties |

The graph definition tells Oracle how to map data. Rows in the vertex table become vertices; rows in the edge table become relationships between the corresponding vertices.

~~~text
PERSON table                       KNOWS table
+-----------+------+               +---------------+------------+------------+
| PERSON_ID | NAME |               | FRIENDSHIP_ID | PERSON_A_ID| PERSON_B_ID|
+-----------+------+               +---------------+------------+------------+
| 1         | An   |               | 101           | 1          | 2          |
| 2         | Binh |               | 102           | 2          | 3          |
| 3         | Chi  |               | 103           | 1          | 3          |
+-----------+------+               +---------------+------------+------------+
        |                                    |
        +---------------+--------------------+
                        v
                Property graph

                 (An) ----101----> (Binh)
                   \                |
                    \               | 102
                     \              v
                      +----------> (Chi)
~~~

### 2.1 Property Graphs Differ from RDF Graphs

Both property graphs and RDF graphs represent graph-structured data, yet their models differ.

| Criterion | Property Graph | RDF Graph |
|---|---|---|
| Components | Vertex, edge, label, property | Subject, predicate, object |
| Attributes | Can attach directly to vertices and edges | Typically represented as triples |
| Relationships | Edges are objects that can have keys/properties | Predicates are relationships between subject/object |
| Querying | SQL/PGQ, graph patterns | SPARQL |
| Best suited for | Business relationships, networks, paths | Knowledge graphs, ontologies, linked data |

Do not use the terms property graph and RDF interchangeably. Oracle offers different graph technologies; select the model and query language based on data sources, applications, and release.

### 2.2 Property Graphs Differ from Plain Adjacency Tables

A table with FROM_ID and TO_ID already stores edge-like relationships, yet is not by itself a SQL Property Graph. A graph object also defines vertex/edge tables, keys, source/destination mappings, labels, and properties. This definition lets graph queries be expressed in terms of vertices/edges instead of manually writing multiple self-joins.

## 3. Example Model: Accounts and Transactions

Consider a small banking system:

- ACCOUNTS stores accounts.
- TRANSFERS stores money transfer transactions.

An account is a vertex. A transaction is a directed edge from sender account to receiver account.

### 3.1 Creating the Vertex Table

~~~sql
CREATE TABLE accounts (
    account_id NUMBER
        CONSTRAINT accounts_pk PRIMARY KEY,
    account_name VARCHAR2(100) NOT NULL,
    account_type VARCHAR2(30),
    city VARCHAR2(80),
    opened_at TIMESTAMP
);
~~~

### 3.2 Creating the Edge Table

~~~sql
CREATE TABLE transfers (
    transfer_id NUMBER
        CONSTRAINT transfers_pk PRIMARY KEY,
    from_account_id NUMBER NOT NULL,
    to_account_id NUMBER NOT NULL,
    amount NUMBER(18,2) NOT NULL,
    transfer_time TIMESTAMP NOT NULL,
    transfer_status VARCHAR2(20),
    CONSTRAINT transfers_from_fk
        FOREIGN KEY (from_account_id)
        REFERENCES accounts(account_id),
    CONSTRAINT transfers_to_fk
        FOREIGN KEY (to_account_id)
        REFERENCES accounts(account_id),
    CONSTRAINT transfers_amount_ck
        CHECK (amount > 0)
);
~~~

Foreign keys in the relational model ensure source/destination point to existing accounts. The graph definition must also declare corresponding source and destination mappings.

### 3.3 Loading Illustrative Data

~~~sql
INSERT INTO accounts VALUES
    (1, 'An', 'PERSONAL', 'Ha Noi', SYSTIMESTAMP - INTERVAL '3' YEAR);
INSERT INTO accounts VALUES
    (2, 'Binh', 'BUSINESS', 'Da Nang', SYSTIMESTAMP - INTERVAL '2' YEAR);
INSERT INTO accounts VALUES
    (3, 'Chi', 'PERSONAL', 'Ho Chi Minh City', SYSTIMESTAMP - INTERVAL '1' YEAR);
INSERT INTO accounts VALUES
    (4, 'Dung', 'BUSINESS', 'Ha Noi', SYSTIMESTAMP - INTERVAL '6' MONTH);

INSERT INTO transfers VALUES
    (1001, 1, 2, 1500000, SYSTIMESTAMP - INTERVAL '20' DAY, 'POSTED');
INSERT INTO transfers VALUES
    (1002, 2, 3, 500000, SYSTIMESTAMP - INTERVAL '18' DAY, 'POSTED');
INSERT INTO transfers VALUES
    (1003, 1, 3, 250000, SYSTIMESTAMP - INTERVAL '10' DAY, 'POSTED');
INSERT INTO transfers VALUES
    (1004, 3, 4, 700000, SYSTIMESTAMP - INTERVAL '5' DAY, 'POSTED');

COMMIT;
~~~

These values are for lab purposes only and do not represent real banking data.

## 4. Defining a SQL Property Graph

In Oracle Database versions supporting SQL Property Graph, you can create a graph schema object using `CREATE PROPERTY GRAPH`.

Example:

~~~sql
CREATE PROPERTY GRAPH accounts_graph
    VERTEX TABLES (
        accounts
            KEY (account_id)
            LABEL account
            PROPERTIES (
                account_id,
                account_name,
                account_type,
                city,
                opened_at
            )
    )
    EDGE TABLES (
        transfers
            KEY (transfer_id)
            SOURCE KEY (from_account_id)
                REFERENCES accounts (account_id)
            DESTINATION KEY (to_account_id)
                REFERENCES accounts (account_id)
            LABEL transfer
            PROPERTIES (
                transfer_id,
                amount,
                transfer_time,
                transfer_status
            )
    );
~~~

The graph name is ACCOUNTS_GRAPH. The ACCOUNTS table maps to vertices labeled account. The TRANSFERS table maps to edges labeled transfer.

### 4.1 VERTEX TABLES

The VERTEX TABLES clause defines vertex sources:

~~~sql
VERTEX TABLES (
    accounts
        KEY (account_id)
        LABEL account
        PROPERTIES (account_id, account_name, city)
)
~~~

- ACCOUNTS: source table.
- KEY (account_id): column uniquely identifying a vertex.
- LABEL account: label of the vertex.
- PROPERTIES: columns exposed as properties accessible in graph queries.

### 4.2 EDGE TABLES

The EDGE TABLES clause defines edge sources:

~~~sql
EDGE TABLES (
    transfers
        KEY (transfer_id)
        SOURCE KEY (from_account_id)
            REFERENCES accounts (account_id)
        DESTINATION KEY (to_account_id)
            REFERENCES accounts (account_id)
        LABEL transfer
        PROPERTIES (transfer_id, amount, transfer_time)
)
~~~

- KEY (transfer_id): identifies an edge.
- SOURCE KEY: column or group of columns identifying the source vertex.
- DESTINATION KEY: column or group of columns identifying the destination vertex.
- REFERENCES: referenced vertex table and key.
- LABEL transfer: classifies the edge.
- PROPERTIES: properties of the edge.

### 4.3 Keys Must Identify Uniquely

A vertex key must uniquely identify one vertex row. An edge key must uniquely identify one edge row. If keys are not unique, the graph may fail to map entities or relationships properly.

Use primary keys/unique constraints in the relational tables and declare graph keys matching those columns. Never pick a column just because it happens to look unique in current data.

### 4.4 Source and Destination Must Match the Key

If the vertex key is ACCOUNT_ID, the source/destination columns in TRANSFERS must reference the exact type and values of ACCOUNT_ID. With composite keys, column order in the source/destination mapping must match the referenced key order.

### 4.5 Properties Are What Graph Queries See

Declare only columns needed for graph patterns and results. Avoid exposing sensitive columns in a property graph if graph queriers do not need access to them.

## 5. Querying with GRAPH_TABLE

GRAPH_TABLE is a table operator that embeds a graph pattern into a SQL statement. Graph pattern results are returned as relational rows via the COLUMNS clause.

Example finding direct transfers from account An:

~~~sql
SELECT *
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    WHERE a.account_name = 'An'
    COLUMNS (
        a.account_name AS sender,
        b.account_name AS receiver,
        t.amount AS amount,
        t.transfer_time AS transfer_time,
        t.transfer_status AS status
    )
);
~~~

Explanation:

- ACCOUNTS_GRAPH: the created property graph.
- (a IS account): vertex with label account, bound to variable a.
- [t IS transfer]: edge with label transfer, bound to variable t.
- ->: direction from source to destination.
- (b IS account): destination vertex.
- WHERE: filters the graph pattern by properties.
- COLUMNS: values returned as SQL columns.

GRAPH_TABLE can be used in FROM as a row source; it can be combined with other relational tables, CTEs, GROUP BY, ORDER BY, and standard SQL constructs per supported release syntax.

### 5.1 Finding Outgoing Transfers from Accounts

~~~sql
SELECT sender,
       receiver,
       amount
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    COLUMNS (
        a.account_name AS sender,
        b.account_name AS receiver,
        t.amount AS amount
    )
)
ORDER BY sender, receiver;
~~~

### 5.2 Filtering by Edge Properties

~~~sql
SELECT *
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    WHERE t.amount >= 500000
      AND t.transfer_status = 'POSTED'
    COLUMNS (
        a.account_name AS sender,
        b.account_name AS receiver,
        t.amount AS amount
    )
);
~~~

Conditions inside the graph pattern limit results by vertex/edge properties. You can further filter results in outer SQL if needed.

### 5.3 Combining with SQL Aggregation

~~~sql
SELECT receiver,
       COUNT(*) AS incoming_transfer_count,
       SUM(amount) AS total_received
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    COLUMNS (
        b.account_name AS receiver,
        t.amount AS amount
    )
)
GROUP BY receiver
ORDER BY total_received DESC;
~~~

This is a major strength of SQL Property Graph: graph pattern results still participate in SQL aggregations.

## 6. Reading a Path Across Multiple Edges

A graph pattern can describe multiple relationship hops within one pattern.

Example finding a transfer path of two transactions:

~~~sql
SELECT *
FROM GRAPH_TABLE (
    accounts_graph
    MATCH
        (a IS account)
        -[t1 IS transfer]->
        (b IS account)
        -[t2 IS transfer]->
        (c IS account)
    COLUMNS (
        a.account_name AS start_account,
        b.account_name AS intermediate_account,
        c.account_name AS end_account,
        t1.amount AS first_amount,
        t2.amount AS second_amount
    )
);
~~~

This pattern finds three vertices connected by two directed edges. Each occurrence of t1 and t2 is a transaction in the TRANSFERS table.

### 6.1 Finding Intermediary Relationships

A multi-step query can answer:

- Can account A reach C through B?
- Through which management levels does employee A report?
- Is product A related to product C via an intermediate category?
- Which devices share a network node?

### 6.2 Controlling Path Length

Long paths can cause result counts to explode rapidly. Before using variable-length paths or multi-hop patterns:

- Set the required hop limit.
- Filter vertices/edges by time or status.
- Restrict labels and properties.
- Avoid returning entire paths when only endpoints are needed.
- Measure execution plans on production-like data.

Path operators, quantifiers, path variables, and match options can differ across Oracle releases. Use SQL/PGQ syntax documented for your exact version; do not copy PGQL or Cypher syntax into GRAPH_TABLE.

## 7. Labels and Multiple Entity Types

One graph can represent multiple vertex/edge types.

E-commerce network example:

- Vertex labels: customer, product, store.
- Edge labels: purchased, viewed, sold_by, located_in.

Each label identifies the entity/relationship type. Queries can match a single type or combine multiple types per the declared model.

### 7.1 Multiple Vertex Tables

A graph can declare multiple vertex tables:

~~~sql
VERTEX TABLES (
    customers
        KEY (customer_id)
        LABEL customer
        PROPERTIES (customer_id, customer_name, city),
    products
        KEY (product_id)
        LABEL product
        PROPERTIES (product_id, product_name, category)
)
~~~

### 7.2 Multiple Edge Tables

Different relationships can be declared:

~~~sql
EDGE TABLES (
    purchases
        KEY (purchase_id)
        SOURCE KEY (customer_id)
            REFERENCES customers (customer_id)
        DESTINATION KEY (product_id)
            REFERENCES products (product_id)
        LABEL purchased
        PROPERTIES (purchase_id, purchased_at, quantity),
    recommendations
        KEY (recommendation_id)
        SOURCE KEY (source_product_id)
            REFERENCES products (product_id)
        DESTINATION KEY (target_product_id)
            REFERENCES products (product_id)
        LABEL recommends
        PROPERTIES (recommendation_id, score)
)
~~~

This example illustrates structure; before running, ensure the corresponding tables, keys, and column names exist and multi-table graph DDL syntax matches your release.

### 7.3 Labels Are Semantic, Not Indexes

Labels aid classification and pattern selection. They do not automatically guarantee fast queries. Performance still depends on keys, relational indexes, statistics, cardinality, and how the optimizer executes the graph pattern.

## 8. Properties and Data Types

A property is a value exposed from a column of a vertex or edge table.

| Graph Property | Relational Column | Component |
|---|---|---|
| account_id | ACCOUNTS.ACCOUNT_ID | Vertex |
| account_name | ACCOUNTS.ACCOUNT_NAME | Vertex |
| city | ACCOUNTS.CITY | Vertex |
| amount | TRANSFERS.AMOUNT | Edge |
| transfer_time | TRANSFERS.TRANSFER_TIME | Edge |
| transfer_status | TRANSFERS.TRANSFER_STATUS | Edge |

Use clear property names consistent across the schema, graph definition, and queries.

### 8.1 Select Minimal Properties

Do not put unnecessary data into the graph. For example, if a graph is used to analyze paths between accounts, you may only need account ID, account type, and city; there is no need to expose personal identification numbers or sensitive data.

### 8.2 Data Types

Choose SQL types matching semantics:

- NUMBER for IDs, quantities, and monetary amounts.
- VARCHAR2 for names, codes, and statuses.
- DATE/TIMESTAMP for timestamps.
- RAW/UUID representation per convention if identifiers require it.

Verify which data types are supported as properties in your version. Do not assume all Oracle types such as LOBs, object types, or specialized datatypes can be used as properties in every release.

### 8.3 NULL Properties

Properties can be NULL if the source column allows it. Queries must explicitly handle NULLs, especially in filters, equality checks, and aggregations. If an attribute is mandatory for graph logic, place NOT NULL on the source table or validate data before creating the graph.

## 9. Vertex Keys, Edge Keys, and Integrity

### 9.1 Vertex Key

A vertex key identifies a vertex. For example, ACCOUNT_ID:

~~~sql
KEY (account_id)
~~~

Keys should be protected by a PRIMARY KEY or UNIQUE constraint on the relational table.

### 9.2 Edge Key

An edge key identifies each edge. For example, TRANSFER_ID:

~~~sql
KEY (transfer_id)
~~~

Do not use the source/destination pair as the edge key if the same two accounts can transact multiple times.

### 9.3 Source/Destination Mapping

Source and destination must reference the vertex table's key:

~~~sql
SOURCE KEY (from_account_id)
    REFERENCES accounts (account_id)
DESTINATION KEY (to_account_id)
    REFERENCES accounts (account_id)
~~~

If the edge table contains an ID with no matching vertex, the graph mapping may violate constraints or queries may fail to map endpoints properly. Use foreign key constraints in the relational schema to protect integrity from the start.

### 9.4 Composite Keys

If a vertex is identified by multiple columns, declare the composite key and composite source/destination keys in the exact same order. Check the SQL Property Graph documentation for your release for composite key syntax and limits.

## 10. Property Graphs vs. Traditional SQL Queries

Not every relational query needs a graph.

Join queries fit well when the number of relationship hops is fixed and small:

~~~sql
SELECT a.account_name AS sender,
       b.account_name AS receiver,
       t.amount
FROM transfers t
JOIN accounts a
  ON a.account_id = t.from_account_id
JOIN accounts b
  ON b.account_id = t.to_account_id;
~~~

Graph patterns are useful when expressing multi-step or path structures:

~~~sql
SELECT *
FROM GRAPH_TABLE (
    accounts_graph
    MATCH
        (a IS account)
        -[t1 IS transfer]->
        (b IS account)
        -[t2 IS transfer]->
        (c IS account)
    COLUMNS (
        a.account_name AS source_account,
        c.account_name AS destination_account
    )
);
~~~

| Scenario | Suitable Approach |
|---|---|
| Joining 2–3 fixed tables | SQL JOIN |
| Finding relationships across multiple hops | Graph pattern |
| Grouping aggregations | SQL GROUP BY |
| Advanced centrality/community/shortest path analytics | Appropriate graph analytics engine/API |
| Standard tabular reporting | Traditional SQL |
| Pattern-based relationship queries | SQL Property Graph can be clearer |

SQL Property Graph still runs inside Oracle Database and its optimizer. Do not assume every graph query is faster than a join. Compare execution plans, timing, and resources on real workloads.

## 11. Property Graphs vs. PGQL/Cypher/SPARQL

Graph languages have their own syntax and execution environments:

- SQL/PGQ: graph patterns embedded in SQL; in Oracle, using GRAPH_TABLE and MATCH.
- PGQL: dedicated graph query language supported by the Oracle Graph ecosystem in corresponding configurations.
- Cypher: graph language popular in the Neo4j ecosystem and certain other platforms.
- SPARQL: query language for RDF.

Never copy queries verbatim from PGQL or Cypher into GRAPH_TABLE. Vertex/edge concepts may be similar, yet grammar, path syntax, functions, and execution environments differ.

### 11.1 SQL/PGQ Fits When

- Source data already resides in Oracle Database.
- Applications need to combine graph patterns with SQL.
- You want graph query results returned as a relational table.
- You want to share the database's existing transactions/security/data governance.

### 11.2 Graph Server/Analytics Fits When

- Deep graph analytics algorithms are needed.
- In-memory graph processing or large-scale API-driven analytics are needed.
- A dedicated graph environment is needed for analytical workloads.
- Algorithms/engines not directly provided by SQL queries are required.

SQL Property Graph and Oracle Graph Server/PGX can complement each other. Check documentation, licensing, and versions of each component before deploying.

## 12. Graph Example for a Social Network

### 12.1 Source Tables

~~~sql
CREATE TABLE people (
    person_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(100) NOT NULL,
    city VARCHAR2(80)
);

CREATE TABLE friendships (
    friendship_id NUMBER PRIMARY KEY,
    person_a_id NUMBER NOT NULL,
    person_b_id NUMBER NOT NULL,
    since_date DATE,
    CONSTRAINT friendships_a_fk
        FOREIGN KEY (person_a_id) REFERENCES people(person_id),
    CONSTRAINT friendships_b_fk
        FOREIGN KEY (person_b_id) REFERENCES people(person_id)
);
~~~

### 12.2 Graph Definition

~~~sql
CREATE PROPERTY GRAPH social_graph
    VERTEX TABLES (
        people
            KEY (person_id)
            LABEL person
            PROPERTIES (person_id, full_name, city)
    )
    EDGE TABLES (
        friendships
            KEY (friendship_id)
            SOURCE KEY (person_a_id)
                REFERENCES people (person_id)
            DESTINATION KEY (person_b_id)
                REFERENCES people (person_id)
            LABEL knows
            PROPERTIES (friendship_id, since_date)
    );
~~~

### 12.3 Finding Direct Friends

~~~sql
SELECT *
FROM GRAPH_TABLE (
    social_graph
    MATCH (p IS person) -[e IS knows]-> (friend IS person)
    WHERE p.full_name = 'An'
    COLUMNS (
        p.full_name AS person_name,
        friend.full_name AS friend_name,
        e.since_date AS since_date
    )
);
~~~

### 12.4 Finding Friends of Friends

~~~sql
SELECT *
FROM GRAPH_TABLE (
    social_graph
    MATCH
        (p IS person)
        -[e1 IS knows]->
        (friend IS person)
        -[e2 IS knows]->
        (second_degree IS person)
    WHERE p.full_name = 'An'
    COLUMNS (
        p.full_name AS start_person,
        friend.full_name AS intermediate_person,
        second_degree.full_name AS second_degree_person
    )
);
~~~

If business rules treat friendship as undirected yet the table only stores one direction, the directed pattern above only follows the stored direction. Design the representation or use supported undirected match syntax to reflect the rule accurately.

## 13. Graph Example for HR Management

An EMPLOYEES table can both act as a vertex table and contain a MANAGER_ID column referencing EMPLOYEE_ID. A separate edge table can store reporting relationships:

~~~sql
CREATE TABLE reporting_lines (
    reporting_id NUMBER PRIMARY KEY,
    employee_id NUMBER NOT NULL,
    manager_id NUMBER NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    CONSTRAINT reporting_employee_fk
        FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    CONSTRAINT reporting_manager_fk
        FOREIGN KEY (manager_id) REFERENCES employees(employee_id)
);
~~~

Vertices are employees; edges are reporting relationships. Edge properties can hold effective start/end dates.

A separate edge table is helpful when an employee has manager-change history, relationships carry attributes, multiple reporting types exist, or effective dates must be stored.

If only MANAGER_ID is stored in EMPLOYEES, self-references can be mapped per the graph DDL capabilities of your version. A separate edge table is usually clearer when relationships have multiple attributes or history.

## 14. Graph Example for Fraud Detection

A graph can link:

- Customer.
- Bank account.
- Device.
- Phone number.
- IP address.
- Merchant.

Edges can represent:

- Customer owns account.
- Account uses device.
- Customer shares phone.
- Account transfers to account.
- Device connects from IP.

A graph query can find accounts linked via a shared device or phone number. This is an investigative signal, not automatic proof of fraud.

### 14.1 Data Design

Do not lump all ID types into an undifferentiated column. Use separate labels/vertex tables or a clearly namespaced model to avoid collisions between customer_id, account_id, and device_id.

### 14.2 Time-Aware Graphs

Fraud relationships may only hold within a time window. Include valid_from, valid_to, observed_at, or event timestamps in edge properties and filter by the analysis window.

### 14.3 Avoiding False Positives

Two customers sharing a public IP or a family device are not automatically fraudulent. Graph results must be combined with rules, scores, timing, data sources, and analyst review.

## 15. Graph Queries and SQL Filters

A graph query can filter vertex/edge properties, and outer SQL can further process the results.

Example summing transfer amounts from personal accounts:

~~~sql
SELECT sender_city,
       SUM(amount) AS total_amount
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    WHERE a.account_type = 'PERSONAL'
      AND t.transfer_status = 'POSTED'
    COLUMNS (
        a.city AS sender_city,
        t.amount AS amount
    )
)
GROUP BY sender_city
ORDER BY total_amount DESC;
~~~

### 15.1 Bind Variables

In applications, use bind variables for dynamic conditions:

~~~sql
SELECT *
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    WHERE a.account_id = :source_account_id
    COLUMNS (
        a.account_name AS sender,
        b.account_name AS receiver,
        t.amount AS amount
    )
);
~~~

Bind variables avoid concatenating user input directly into SQL text, reduce SQL injection risk, and support cursor reuse.

### 15.2 Combining with CTEs

~~~sql
WITH transfer_edges AS (
    SELECT *
    FROM GRAPH_TABLE (
        accounts_graph
        MATCH (a IS account) -[t IS transfer]-> (b IS account)
        COLUMNS (
            a.account_id AS source_id,
            b.account_id AS target_id,
            t.amount AS amount
        )
    )
)
SELECT source_id,
       COUNT(*) AS outgoing_count,
       SUM(amount) AS outgoing_amount
FROM transfer_edges
GROUP BY source_id;
~~~

### 15.3 Combining with Relational Tables

~~~sql
SELECT g.sender,
       g.receiver,
       g.amount,
       c.customer_segment
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    COLUMNS (
        a.account_id AS sender_id,
        b.account_id AS receiver_id,
        a.account_name AS sender,
        b.account_name AS receiver,
        t.amount AS amount
    )
) g
JOIN account_customers c
  ON c.account_id = g.sender_id;
~~~

Graph results can be combined with relational tables to retrieve additional details. Choose appropriate cardinality and indexes for the outer join.

## 16. Performance and Optimization

Graph queries still consume CPU, memory, and I/O. Multi-hop paths can expand the number of combinations very rapidly.

### 16.1 Indexes for Keys and Join Columns

Have appropriate indexes on vertex keys, edge keys, source keys, destination keys, and frequently filtered properties.

Primary key/unique constraints typically already create indexes for keys. Source/destination foreign keys do not automatically get indexes in every design; consider indexing the edge table for endpoint access.

Example:

~~~sql
CREATE INDEX transfers_from_ix
ON transfers(from_account_id);

CREATE INDEX transfers_to_ix
ON transfers(to_account_id);

CREATE INDEX transfers_time_ix
ON transfers(transfer_time);
~~~

Do not create every index mechanically. Each index increases storage and INSERT/UPDATE/DELETE overhead.

### 16.2 Statistics

The optimizer needs accurate statistics to estimate cardinality. After loading large amounts of data or shifting distributions, gather statistics per database policy:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'TRANSFERS',
        cascade => TRUE
    );
END;
/
~~~

For production, follow the DBA's existing statistics procedure; do not run statistics gathering on all tables during peak hours.

### 16.3 Limiting Scope

- Filter by time before expanding paths.
- Restrict labels to match.
- Select minimal properties in COLUMNS.
- Bound path length.
- Start from selective endpoints.
- Avoid querying the whole graph when only a small neighborhood is needed.

### 16.4 Reading Execution Plans

Graph queries execute inside the SQL engine. Use appropriate SQL plan tools to inspect plans:

~~~sql
EXPLAIN PLAN FOR
SELECT *
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    WHERE a.account_id = 1
    COLUMNS (
        a.account_name AS sender,
        b.account_name AS receiver,
        t.amount AS amount
    )
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Operator details in the plan depend on release and query. Do not infer performance solely from a single operator or estimated rows; compare actual runtime statistics in an appropriate test environment.

## 17. Managing Source Table Changes

A property graph references source tables and columns. If columns are renamed/dropped, or datatypes, keys, or table structures change, the graph definition may become invalid or queries may stop behaving as expected.

Before running DDL:

- Check which graphs reference the table.
- Check which properties depend on columns about to change.
- Check key/source/destination mappings.
- Test DDL in a test environment.
- Update the graph definition in the migration.
- Run smoke queries after deployment.

Do not drop/rename a column simply because the current relational application does not use it; graph queries or other reports may depend on it.

## 18. Managing Graph Objects

A property graph is a schema object with metadata. Governance needs to track who created the graph, which tables it relies on, which columns are exposed, who is allowed to query it, which migrations created/altered it, and which graphs are no longer used.

Basic DDL commands can include CREATE, ALTER, or DROP depending on release capabilities. Syntax for modifying graph definitions and metadata views must be checked in the SQL Language Reference for the exact version.

### 18.1 Dropping a Graph

When removing a graph object, distinguish dropping the graph definition from dropping the source relational tables. Do not drop ACCOUNTS or TRANSFERS simply because the graph object is no longer needed.

Before dropping:

- Confirm no queries still depend on it.
- Check application code/reports.
- Save the DDL definition in case rollback is needed.
- Execute through a controlled migration.

### 18.2 Version Control

Store graph DDL in the repository alongside schema migrations. Name migrations sequentially, for example:

~~~text
V042__create_accounts_graph.sql
V043__add_transfer_status_property.sql
V044__update_graph_edge_mapping.sql
~~~

Filenames are examples. Conventions depend on Flyway/Liquibase or the project's migration tool.

## 19. Privileges and Security

Graph queries must not broaden data access beyond relational schema policies.

When deploying:

- The user creating the graph needs graph-object creation privileges per release.
- The user defining the graph needs appropriate privileges on source tables.
- Querying users need privileges to access the graph and data per the release's Oracle mechanism.
- Never grant database admin privileges just to query a graph.
- Restrict sensitive properties.
- Use a dedicated schema owner for graph definitions if appropriate.
- Audit graph create/alter/drop operations.

System/object privilege names and GRANT syntax can vary by release. Consult the corresponding Security Guide/SQL Language Reference before applying GRANTs in production; do not guess privileges from feature names.

### 19.1 Row-Level Security

If source tables use Virtual Private Database (VPD), Real Application Security, or other security policies, verify that graph queries enforce policies as expected in your release and execution context. Never assume exposing a table as a graph disables policies, nor assume every policy behaves identically without testing.

### 19.2 Data Masking

Do not include PII or confidential data in graph properties if queries do not need them. For lab environments, use synthetic or masked data.

### 19.3 SQL Injection

Applications calling GRAPH_TABLE via JDBC must still use bind variables. Never concatenate user input into graph patterns, labels, or SQL text.

## 20. Checking Oracle Versions Supporting SQL Property Graph

Version support requirements are critical because not every Oracle Database release understands CREATE PROPERTY GRAPH and GRAPH_TABLE syntax.

### 20.1 Version Milestones

| Database Release | Applicability Guidance |
|---|---|
| Oracle Database 19c and releases older than 23ai | Do not assume native SQL Property Graph DDL/GRAPH_TABLE exists. Check separate graph options/servers or use relational models/alternative solutions. |
| Oracle Database 23ai | Supports SQL Property Graph and core SQL/PGQ such as CREATE PROPERTY GRAPH and GRAPH_TABLE. |
| Oracle Database 26ai and newer releases | Check the SQL Language Reference/Graph documentation for the exact release to confirm core syntax, enhancements, and restrictions. |

Marketing release names, internal version numbers, Release Updates, and compatibility settings do not always surface identically. Verify against the connected database rather than relying on image names or documentation from another environment.

### 20.2 Checking Database Version

~~~sql
SELECT banner
FROM v$version;
~~~

On releases supporting the BANNER_FULL column:

~~~sql
SELECT banner_full
FROM v$version;
~~~

Or:

~~~sql
SELECT product,
       version,
       status
FROM product_component_version;
~~~

Columns can differ by version. Use `DESC V$VERSION` or `DESC PRODUCT_COMPONENT_VERSION` if writing scripts compatible across multiple releases.

### 20.3 Checking Container/PDB

In multitenant, identify the current container:

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

A query succeeding on one PDB does not prove another PDB shares the same version, patches, or privileges.

### 20.4 Checking COMPATIBLE

~~~sql
SHOW PARAMETER compatible;
~~~

COMPATIBLE affects availability of certain features and compatibility formats. However, do not use the COMPATIBLE value alone to conclude SQL Property Graph is definitely supported. Cross-check release, RU, platform/service, and feature prerequisite documentation.

### 20.5 Minimal Syntax Verification

In a lab or test schema on a database confirmed to support it, create a minimal graph from two small tables and run a GRAPH_TABLE query. This is a better technical verification than just looking at a version banner.

Never create test graphs in production without an object cleanup plan and approved privileges.

## 21. Database Service, Cloud, and Platform Restrictions

Do not assume every Oracle Database deployment has the same feature set merely because they share a release name.

Check:

- On-premises vs. cloud service.
- Autonomous Database vs. Base Database Service.
- Exadata vs. other platforms.
- Region and service version.
- Release Update/patch level.
- PDB configuration.
- Feature restrictions by service tier.
- Licensing and rights for related graph/analytics components.

Oracle documentation for the exact cloud service is the authoritative source. A SQL feature inside the database may have different availability by service, while Graph Server/Graph Studio/analytics have their own deployment requirements.

## 22. JDBC and SQL Property Graph

GRAPH_TABLE is part of a SQL statement. Java applications can send this SQL via JDBC just like other SELECT statements if the database supports the syntax and the driver is compatible with the database release.

Example:

~~~java
String sql =
    "SELECT * " +
    "FROM GRAPH_TABLE (" +
    "  accounts_graph " +
    "  MATCH (a IS account) -[t IS transfer]-> (b IS account) " +
    "  WHERE a.account_id = ? " +
    "  COLUMNS (" +
    "    a.account_name AS sender, " +
    "    b.account_name AS receiver, " +
    "    t.amount AS amount" +
    "  )" +
    ")";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, sourceAccountId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            String sender = rs.getString("sender");
            String receiver = rs.getString("receiver");
            BigDecimal amount = rs.getBigDecimal("amount");
        }
    }
}
~~~

### 22.1 No Graph-Specific JDBC API Needed for Basic SELECTs

Applications can use PreparedStatement and ResultSet. A separate graph driver is not required just to execute SQL GRAPH_TABLE queries.

### 22.2 Driver/Database Compatibility

The driver must still be compatible with the JDK and database release. An older driver may connect to a newer database without supporting all new datatypes, metadata, or protocol features. Consult the JDBC certification matrix.

### 22.3 Bind Variables

Never concatenate input values into SQL. Use bind variables for IDs and filter values. Labels and pattern structure are typically part of the SQL text; never let users control graph names/labels arbitrarily via string concatenation. If graph pattern selection is needed, map from an application-controlled allowlist configuration.

## 23. Optimizing the Graph Model

A graph model should reflect business questions rather than copying every table into vertices/edges.

### 23.1 Choosing the Right Vertices

Vertices are usually entities with stable identities: Person, Account, Product, Device, Location, or Organization. Do not turn every lookup table into a vertex if no relationship query requires it.

### 23.2 Choosing the Right Edges

Edges should express a meaningful relationship: Owns, Transfers, Knows, Reports_to, Purchased, or Connected_to. If a relationship has its own attributes or occurs multiple times, use an edge table with its own key.

### 23.3 Event Edges vs. Relationship Edges

A money transfer is an event edge: each transfer is an event with a timestamp, amount, and status.

A friendship is a relationship edge: it persists over a time span and may change status.

Distinguishing the two types leads to better retention, event history, and temporal query designs.

### 23.4 Temporal Graphs

If relationships are time-bounded, store start/end timestamps or event timestamps in edge properties. At query time, filter by the business time window.

Do not delete edge history if you need to investigate past graph states.

## 24. Limitations to Consider

Specific restrictions depend on the database release and graph DDL, yet during design you should verify:

- Which datatypes can be used as vertex/edge keys.
- Which datatypes can be exposed as properties.
- Composite key support.
- Supported tables, views, or other relational sources.
- Rules for partitioned tables.
- How NULL keys/properties are handled.
- Limits on label/property names and identifiers.
- DDL dependencies when renaming/dropping columns.
- Privileges to create and query graphs.
- Behavior with VPD/row-level security.
- Supported pattern/path syntax.
- Optimizer capabilities and index usage.

Do not infer limitations from a different version. The SQL Language Reference and Graph Developer's Guide for the exact release are the sources to consult.

## 25. Troubleshooting

### CREATE PROPERTY GRAPH Not Recognized

Possible causes:

- Database release does not yet support SQL Property Graph.
- Connected to the wrong PDB/service.
- Release Update or platform does not meet prerequisites.
- User lacks privileges to create graphs.
- Syntax taken from another version's documentation.

Resolution steps:

1. Confirm V$VERSION.
2. Confirm CON_NAME/SERVICE_NAME.
3. Check documentation for the exact release.
4. Check privileges.
5. Test minimal syntax in a lab.

### GRAPH_TABLE Not Recognized

Check whether the database parser/release supports SQL/PGQ. Do not confuse GRAPH_TABLE syntax with PGQL running on a graph server.

### Invalid Vertex/Edge Mapping

Check:

- Is the vertex key unique?
- Is the edge key unique?
- Do source/destination columns match the vertex key's type and values?
- Are composite keys in the right order?
- Are there nonexistent endpoints?
- Was a column renamed/dropped?

### Query Returns Few or No Rows

Check:

- Are labels correct?
- Is edge direction correct?
- Are source/destination mappings reversed?
- Are property filters too restrictive?
- Does edge data have valid endpoints?
- Are you querying the right PDB/schema?

### Slow Queries

Check:

- Path length and intermediate result counts.
- Indexes on keys/source/destination.
- Statistics.
- Filter selectivity.
- Execution plans.
- Number of properties returned.
- Would a simpler SQL JOIN work?

### Privilege Errors

Identify the user executing the query, the graph owner, and privileges on base tables. Grant exact privileges per release documentation rather than defaulting to the DBA role.

## 26. Best Practices

- Start from the business questions to be answered by the graph.
- Keep relational tables as a clean source of truth.
- Choose stable, unique vertex keys and edge keys.
- Name labels/properties meaningfully.
- Declare source/destination mappings in the right direction.
- Expose only necessary properties.
- Use foreign keys to protect endpoint integrity.
- Index keys and endpoint columns based on workload.
- Gather appropriate statistics.
- Bound paths and filter early.
- Combine GRAPH_TABLE with SQL when aggregations/joins are needed.
- Use bind variables via JDBC.
- Manage graph DDL in migrations/version control.
- Verify version, RU, PDB, and cloud service.
- Verify security policies and query privileges.
- Benchmark with representative data.

## 27. Common Mistakes

| Mistake | Consequence | Right Approach |
|---|---|---|
| Thinking a table with FROM_ID/TO_ID is automatically a property graph | Missing graph metadata and key/label mappings | Create a graph definition |
| Confusing vertices with edges | Mismodeling entities and relationships | Identify entities vs. relationships |
| Reversing source/destination | Path queries return results in the wrong direction | Declare SOURCE KEY/DESTINATION KEY properly |
| Non-unique edge key | Collapses or misidentifies relationships | Use a dedicated key for each edge |
| Using endpoint pair as edge key for repeated events | Loses distinction across multiple transactions | Use a dedicated event/relationship ID |
| Unprotected vertex key | Unstable mapping | Enforce PRIMARY KEY/UNIQUE on source table |
| No foreign keys on endpoints | Edges point to invalid vertices | Protect source/destination with FKs |
| Putting every column into properties | Data exposure and enlarged attack surface | Expose only needed properties |
| Assuming graph queries are always faster than JOINs | High CPU/memory and path explosion | Compare plans/runtime |
| Forgetting edge direction | Missing paths | Define directed/undirected semantics |
| Using Cypher/PGQL syntax in GRAPH_TABLE | Syntax error | Use SQL/PGQ for the exact Oracle release |
| Thinking 19c supports native GRAPH_TABLE | Cannot parse syntax | Verify 23ai+ milestone and service |
| Looking only at V$VERSION | Misses PDB/RU/platform/privileges | Verify the entire deployment context |
| Not updating graph when renaming columns | Broken graph definition/queries | Include graph DDL in migrations |
| Not indexing endpoints | Expensive path traversal | Measure and create appropriate indexes |
| Treating graph results as proof of fraud | False positives | Combine with rules and business investigation |
| Using literal input in SQL | SQL injection | Bind variables and allowlisted patterns |

## 28. Self-Check Practice Exercises

Execute on an Oracle Database release supporting SQL Property Graph, in a lab schema.

### Exercise 1 — Design Vertices and Edges

From the accounts domain, identify vertex tables, edge tables, keys, source keys, destination keys, and properties.

### Exercise 2 — Create Source Tables

Create ACCOUNTS and TRANSFERS with primary keys, foreign keys, and synthetic data.

### Exercise 3 — Create the Property Graph

Create ACCOUNTS_GRAPH using CREATE PROPERTY GRAPH. Verify DDL completion.

### Exercise 4 — Query Direct Edges

Use GRAPH_TABLE to find all transactions from an account.

### Exercise 5 — Two-Hop Query

Find two-transaction paths from a source account to a destination account.

### Exercise 6 — Filter Properties

Filter by amount, status, city, and transfer_time.

### Exercise 7 — Aggregation

Compute total received amount per account using GROUP BY outside GRAPH_TABLE.

### Exercise 8 — Composite Key

Design a graph with a composite vertex key and verify source/destination mappings.

### Exercise 9 — Data Integrity

Attempt to create an edge pointing to a nonexistent vertex. Verify that the foreign key protects data at the relational layer.

### Exercise 10 — Indexes and Execution Plans

Compare a query before and after creating endpoint indexes. Record actual runtime and plans.

### Exercise 11 — JDBC

Invoke GRAPH_TABLE via PreparedStatement and bind the source account ID.

### Exercise 12 — Version Compatibility

Record database version, RU, PDB, service, and review SQL Property Graph documentation for the exact release. Compare behavior on an older environment if available.

## 29. Pre-Deployment Checklist

**Model**

- Vertices/edges identified per business requirements?
- Vertex keys and edge keys unique?
- Source/destination directions accurate?
- Labels and properties clearly named?
- Event edges and relationship edges distinguished?

**Database**

- Release includes SQL Property Graph?
- Release Update and COMPATIBLE verified?
- Connected to the right PDB/service?
- Syntax matches SQL Language Reference?
- Datatypes/keys/properties supported?

**Security**

- Graph creator user has least privileges?
- Querying users have appropriate privileges?
- Sensitive properties excluded?
- Row-level security verified?
- JDBC uses bind variables?

**Performance**

- Endpoint indexes evaluated?
- Statistics up to date?
- Path length bounded?
- Filters applied early?
- Execution plans and actual runtime measured?

**Operations**

- Graph DDL under version control?
- Migration/rollback plan exists?
- Post-deployment smoke queries ready?
- Graph object dependencies tracked?
- Tested when source tables change?

## 30. Key Takeaways

| Concept | Key Point |
|---|---|
| Property graph | Graph consisting of vertices, edges, labels, and properties |
| Vertex | Entity in the graph |
| Edge | Directed relationship between two vertices |
| Label | Classifies vertices/edges |
| Property | Attribute of a vertex/edge |
| Vertex key | Uniquely identifies a vertex |
| Edge key | Uniquely identifies an edge |
| SOURCE KEY | Maps the source endpoint |
| DESTINATION KEY | Maps the destination endpoint |
| CREATE PROPERTY GRAPH | Creates a graph schema object over relational tables |
| GRAPH_TABLE | Queries graph patterns in SQL |
| MATCH | Describes vertex/edge patterns |
| COLUMNS | Selects values to return as SQL columns |
| SQL/PGQ | SQL Property Graph Queries |
| PGQL | Separate graph query language |
| RDF/SPARQL | Different graph model/language |
| Oracle Database 23ai | Milestone supporting core native SQL Property Graph |
| V$VERSION | Checks database version |
| TNS/service/PDB | Identifies the exact connected environment |
| Endpoint index | Supports relationship access by source/destination |

SQL Property Graph adds a graph view over relational data: vertices represent entities, edges represent relationships, labels classify them, and properties describe data. CREATE PROPERTY GRAPH maps tables/keys/columns; GRAPH_TABLE uses MATCH to find relationship patterns and returns results to SQL via COLUMNS. The milestone supporting native SQL Property Graph is Oracle Database 23ai; for older releases, cloud services, or different RUs, verify documentation and the actual environment before use. Design keys and edge directions accurately, protect endpoints with constraints, expose only necessary properties, and measure execution plans on real workloads. SQL/PGQ, PGQL, Cypher, and SPARQL are distinct languages/environments; do not mix syntax across them.
