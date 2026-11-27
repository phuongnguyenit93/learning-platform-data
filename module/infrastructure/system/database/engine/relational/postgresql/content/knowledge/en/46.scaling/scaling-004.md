# hstore, ltree, and Specialized Data Models in PostgreSQL

PostgreSQL supports a wide range of specialized data types and extensions to represent data according to its actual domain structure. Not all data fits into a fixed set of relational columns. A product may have a flexible set of attributes; a catalog may have a multi-level tree hierarchy; a scheduling system needs to represent time intervals; a network application needs to store IP/CIDR addresses; a geographic system needs geometry/geography types.

Two representative extensions are **hstore** and **ltree**. `hstore` represents a flat set of key/value pairs, useful when each row has extensible text attributes. `ltree` represents a hierarchical path composed of labels, useful for category trees, organizations, taxonomies, or directory structures. Both provide operators and index support for efficient querying.

Choosing a specialized data type is not merely a syntactic decision. You must consider data structure, integrity, query patterns, indexing, updatability, migrations, extension availability, and portability. This lesson explains `hstore`, `ltree`, tree/graph data models, and other specialized options in PostgreSQL.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain when to use `hstore` for key/value attributes.
2. Install and verify the `hstore` extension.
3. Create, query, update, delete, and convert `hstore` values.
4. Use `hstore` operators, functions, and GIN indexes.
5. Distinguish `hstore` from JSONB.
6. Explain `ltree` and how to represent hierarchies using path labels.
7. Install the `ltree` extension and use its path operators/functions.
8. Create GiST indexes for ancestor/descendant queries.
9. Compare adjacency list, materialized path, closure table, and nested sets.
10. Determine when `ltree` is unsuitable, especially for DAGs or multi-parent graphs.
11. Choose arrays, ranges, multiranges, network, full-text, and spatial types when appropriate.
12. Design constraints, indexes, and migrations for specialized data.
13. Evaluate trade-offs in storage, update cost, query complexity, and portability.
14. Work through 80 practical exercises on PostgreSQL data models.

## 2. Why Do We Need Specialized Data Models?

The relational model with explicitly typed columns is a strong default for most business data. However, certain data domains have distinct structures:
- Attributes that vary by product category.
- Multi-level hierarchies.
- Time or numeric intervals.
- Network addresses and subnets.
- Documents requiring full-text search.
- Spatial data.
- Collections of values sharing a type.

PostgreSQL provides built-in types, operators, index operator classes, and extensions for these scenarios.

### 2.1. Using the Right Type Makes Queries Clearer

A `tstzrange` represents a time interval with inclusive/exclusive bound semantics. An `inet` represents a network address with subnet operators. An `ltree` represents a hierarchical path with ancestor/descendant operators. Storing everything as plain `text` forces the application to parse and enforce many rules manually.

### 2.2. Specialized Types Do Not Replace Data Modeling

A good data type does not by itself decide:
- Who is permitted to create/modify data.
- How uniqueness is enforced.
- How foreign keys are maintained.
- How schemas are versioned.
- How access permissions are granted.
- How replication/backup/restore works.

Those requirements must still be designed into the schema and application.

### 2.3. Extensions Are Operational Dependencies

`hstore` and `ltree` are shipped via PostgreSQL contrib/extension packaging in many distributions. The server needs the compatible package, and then the extension is created in each database. Backup/restore targets and HA nodes also require compatible files.

## 3. What Is hstore?

`hstore` is an extension providing a data type that stores a set of key/value pairs where keys and values are `text`. A key may have an SQL `NULL` value. `hstore` is a flat structure, not a nested document tree.

For example, a product with optional attributes:

~~~text
color => blue
size  => medium
material => cotton
~~~

Each row can store different keys without adding a column for every attribute.

### 3.1. When Is hstore Appropriate?

- Extensible attributes in simple key/value form.
- Keys and values are primarily text.
- Flat structure with no nested arrays/objects needed.
- Queries mainly check key existence or containment.
- An existing system already uses `hstore` and requires schema compatibility.

### 3.2. When Is It Unsuitable?

- Nested documents or arrays are needed.
- Numbers/booleans/timestamps need explicit JSON types.
- Complex schema validation is required.
- Attributes have business relationships or require foreign keys.
- Certain keys are frequently filtered/joined/sorted and should be typed columns.
- Portability to databases that do not support `hstore` is required.

### 3.3. Install the Extension

~~~sql
CREATE EXTENSION hstore;
~~~

Verify:

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema
FROM pg_extension
WHERE extname = 'hstore';
~~~

The extension is installed in the current database. If multiple databases need `hstore`, create the extension in each database.

### 3.4. Check the Package

~~~sql
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name = 'hstore';
~~~

If no row is returned, the server may lack the extension package or the provider may not support it. `CREATE EXTENSION` does not download packages from the Internet.

## 4. Creating a Table with an hstore Column

~~~sql
CREATE TABLE app.products (
    product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    name text NOT NULL,
    attributes hstore NOT NULL DEFAULT ''::hstore
);
~~~

`''::hstore` is an empty `hstore`, distinct from SQL `NULL`.

### 4.1. Inserting Data

~~~sql
INSERT INTO app.products (sku, name, attributes)
VALUES
(
    'TSHIRT-001',
    'Basic T-shirt',
    '"color"=>"blue", "size"=>"M", "material"=>"cotton"'::hstore
),
(
    'MUG-001',
    'Ceramic mug',
    '"color"=>"white", "capacity"=>"350ml"'::hstore
);
~~~

### 4.2. Literal Syntax

The `hstore` text representation uses `key => value` pairs separated by commas. Keys/values may need quoting/escaping if they contain punctuation, quotes, or special whitespace.

In applications, prefer bind parameters and drivers with `hstore` support rather than concatenating SQL strings manually.

### 4.3. Creating with the Constructor

~~~sql
SELECT hstore(
    ARRAY['color', 'size', 'material'],
    ARRAY['blue', 'M', 'cotton']
);
~~~

The arrays must have matching structure; keys/values are converted to `text` per the function signature.

### 4.4. Empty hstore vs. NULL

~~~sql
SELECT
    ''::hstore AS empty_attributes,
    NULL::hstore AS missing_attributes;
~~~

An empty `hstore` is a set with zero pairs. SQL `NULL` means the entire attributes value is unknown/absent. Choose semantics fitting the domain and apply `NOT NULL`/defaults where appropriate.

## 5. Reading Values from hstore

The `->` operator retrieves the value for a key and returns `text`.

~~~sql
SELECT
    sku,
    attributes -> 'color' AS color,
    attributes -> 'size' AS size
FROM app.products;
~~~

### 5.1. Non-Existent Key

If the key does not exist, `->` returns SQL `NULL`. If the key exists with an SQL `NULL` value, the result is also SQL `NULL`. Use `?` or `defined()` when you need to distinguish between the two.

### 5.2. Using in Filters

~~~sql
SELECT product_id, sku, name
FROM app.products
WHERE attributes -> 'color' = 'blue';
~~~

### 5.3. Casting Values to Target Types

`hstore` stores values as `text`, so cast explicitly when numeric/date/boolean types are needed:

~~~sql
SELECT
    sku,
    (attributes -> 'weight_grams')::integer AS weight_grams
FROM app.products
WHERE attributes ? 'weight_grams';
~~~

Casting can fail if data is malformed. Validate on write or run a cleanup migration before casting in critical queries.

### 5.4. NULL Semantics

`attributes ? 'key'` checks whether the key exists. `defined(attributes, 'key')` checks whether the key exists and its value is not `NULL`. These two conditions differ.

## 6. Checking Key Existence

The `?` operator checks whether a key exists in an `hstore`.

~~~sql
SELECT sku
FROM app.products
WHERE attributes ? 'material';
~~~

### 6.1. Check All Keys

`?&` checks whether all keys in an array exist:

~~~sql
SELECT sku
FROM app.products
WHERE attributes ?& ARRAY['color', 'size'];
~~~

### 6.2. Check Any Key

`?|` checks whether at least one key in an array exists:

~~~sql
SELECT sku
FROM app.products
WHERE attributes ?| ARRAY['capacity', 'volume', 'size'];
~~~

### 6.3. Key Exists with Non-NULL Value

~~~sql
SELECT sku
FROM app.products
WHERE defined(attributes, 'color');
~~~

### 6.4. Key Existence Is Not Validation

A row having the key `weight_grams` does not guarantee its value is a valid integer. Use constraints, application validation, or typed attribute tables when data guarantees are required.

## 7. Containment and Equality

The `@>` operator checks whether the left-hand `hstore` contains all pairs of the right-hand `hstore`.

~~~sql
SELECT sku
FROM app.products
WHERE attributes @> '"color"=>"blue"'::hstore;
~~~

### 7.1. Multiple Pairs

~~~sql
SELECT sku
FROM app.products
WHERE attributes @> '"color"=>"blue", "size"=>"M"'::hstore;
~~~

The row must contain the requested key/value pairs.

### 7.2. Contained By

`<@` checks whether the left-hand `hstore` is a subset of the right-hand `hstore`.

~~~sql
SELECT *
FROM app.products
WHERE attributes <@ '"color"=>"blue", "size"=>"M", "material"=>"cotton"'::hstore;
~~~

### 7.3. Equality

Two `hstore` values can be compared with `=`. Equality checks key/value contents regardless of the display order of pairs.

~~~sql
SELECT *
FROM app.products
WHERE attributes = '"color"=>"white", "capacity"=>"350ml"'::hstore;
~~~

### 7.4. Choosing the Operator for the Question

- Does a key exist? Use `?`.
- Do all keys exist? Use `?&`.
- Does at least one key exist? Use `?|`.
- Does it contain specific pairs? Use `@>`.
- What is the value of a key? Use `->`.
- Is it a subset? Use `<@`.

## 8. Adding and Updating hstore Pairs

The `||` operator concatenates two `hstore` values.

~~~sql
UPDATE app.products
SET attributes = attributes || '"season"=>"summer"'::hstore
WHERE sku = 'TSHIRT-001';
~~~

### 8.1. Updating an Existing Key

When two `hstore` values share a key, the pair on the right overwrites the pair with the same key on the left:

~~~sql
UPDATE app.products
SET attributes = attributes || '"color"=>"navy"'::hstore
WHERE sku = 'TSHIRT-001';
~~~

### 8.2. Adding Multiple Keys

~~~sql
UPDATE app.products
SET attributes = attributes ||
    '"color"=>"black", "size"=>"L"'::hstore
WHERE sku = 'TSHIRT-001';
~~~

### 8.3. Constructor in Updates

~~~sql
UPDATE app.products
SET attributes = attributes ||
    hstore(ARRAY['material', 'care'], ARRAY['linen', 'hand wash'])
WHERE sku = 'TSHIRT-001';
~~~

### 8.4. Lost Updates

If multiple sessions read-modify-write the entire `hstore` in the application, one update can overwrite another session's changes without concurrency control. Use atomic SQL updates, row locks, or optimistic concurrency/version columns as needed.

### 8.5. Validate Values Before Writing

If a key is part of business logic, validate allowed values. `hstore` does not enforce per-key data types automatically.

## 9. Deleting Keys and Pairs

The `-` operator deletes a key or pairs.

~~~sql
UPDATE app.products
SET attributes = attributes - 'season'
WHERE sku = 'TSHIRT-001';
~~~

Deleting multiple keys:

~~~sql
UPDATE app.products
SET attributes = attributes - ARRAY['color', 'size']
WHERE sku = 'TSHIRT-001';
~~~

Deleting pairs matching another `hstore`:

~~~sql
SELECT
    attributes - '"color"=>"blue"'::hstore
FROM app.products;
~~~

### 9.1. Policy-Based Deletion

Before removing attributes, check whether any application version still uses the key. During rolling deployments, schema/attribute changes must remain backward-compatible during the transition period.

### 9.2. Do Not Arbitrarily Replace NULL with Deletion

An absent key and a key present with `NULL` may carry different semantics. Choose a clear representation.

## 10. Useful hstore Functions

### 10.1. akeys and avals

~~~sql
SELECT
    akeys(attributes) AS keys,
    avals(attributes) AS values
FROM app.products;
~~~

`akeys` returns an array of keys; `avals` returns an array of values.

### 10.2. each

~~~sql
SELECT
    p.sku,
    kv.key,
    kv.value
FROM app.products AS p
CROSS JOIN LATERAL each(p.attributes) AS kv(key, value);
~~~

`each` expands each pair into rows. This is useful for auditing attributes and spotting inconsistent keys.

### 10.3. slice

~~~sql
SELECT
    slice(attributes, ARRAY['color', 'size']) AS selected_attributes
FROM app.products;
~~~

`slice` returns an `hstore` containing only the requested keys.

### 10.4. exist and defined

~~~sql
SELECT
    exist(attributes, 'color') AS color_key_exists,
    defined(attributes, 'color') AS color_value_is_defined
FROM app.products;
~~~

`exist` checks whether the key exists; `defined` checks whether the value exists and is non-`NULL`.

### 10.5. delete

You can use `delete(hstore, key)` or the corresponding operators to remove keys. Choose function or operator form for readability.

### 10.6. Converting to Arrays

~~~sql
SELECT
    hstore_to_array(attributes) AS flat_array,
    hstore_to_matrix(attributes) AS key_value_matrix
FROM app.products;
~~~

The results are array representations suitable for export or SQL processing. Do not assume key order represents business order.

### 10.7. Converting to JSON

~~~sql
SELECT hstore_to_jsonb(attributes)
FROM app.products;
~~~

`hstore` values are converted to JSON representation; because `hstore` stores text, normal values become JSON strings and `hstore` `NULL` becomes JSON `null`. If JSON numbers/booleans are needed, normalize/cast intentionally.

## 11. GIN and GiST Indexes for hstore

When querying key existence or containment on large tables, sequential scans can be expensive. `hstore` provides operator classes for GIN and GiST.

### 11.1. GIN Index

~~~sql
CREATE INDEX products_attributes_gin_idx
    ON app.products
    USING GIN (attributes);
~~~

GIN fits queries searching for keys and containment on `hstore`.

### 11.2. Key Existence

~~~sql
SELECT *
FROM app.products
WHERE attributes ? 'material';
~~~

### 11.3. Containment

~~~sql
SELECT *
FROM app.products
WHERE attributes @> '"color"=>"blue"'::hstore;
~~~

### 11.4. GiST Index

~~~sql
CREATE INDEX products_attributes_gist_idx
    ON app.products
    USING GIST (attributes);
~~~

GiST is an alternative supporting `hstore` operators. GIN and GiST have trade-offs in index size, build time, update cost, and query patterns. Benchmark on realistic workloads.

### 11.5. Expression B-Tree Index

If a specific key is filtered/sorted frequently, an expression index may be suitable:

~~~sql
CREATE INDEX products_color_idx
    ON app.products ((attributes -> 'color'));
~~~

The query must use a compatible expression:

~~~sql
SELECT *
FROM app.products
WHERE attributes -> 'color' = 'blue';
~~~

### 11.6. Index Maintenance Cost

Every update to `hstore` may require updating GIN/GiST indexes. If attributes churn constantly and queries rarely use them, index write amplification may outweigh benefits.

### 11.7. Partial Expression Index

~~~sql
CREATE INDEX products_weight_idx
    ON app.products (((attributes -> 'weight_grams')::integer))
    WHERE attributes ? 'weight_grams';
~~~

Ensure every value of the key can cast safely. Malformed data can cause index builds to fail.

## 12. hstore vs. JSONB

JSONB is a popular choice for flexible documents. `hstore` is simpler and may fit legacy schemas or flat attributes.

| Criterion | hstore | JSONB |
| --- | --- | --- |
| Structure | Flat key/value | Nested objects/arrays/scalars |
| Value model | Text or SQL NULL | JSON strings, numbers, booleans, null, arrays, objects |
| Nested data | No | Yes |
| Operators | Key existence, containment, concatenation, deletion | Rich path, containment, existence, mutation operators |
| Indexing | GIN/GiST operator classes | GIN and expression indexes, multiple operator classes |
| Schema validation | Mostly custom-designed | Can use constraints/functions; validation still required |
| Portability | Extension-specific | JSONB is a built-in PostgreSQL type |
| Best fit | Simple text attributes | Flexible documents |

### 12.1. When to Keep hstore?

- Existing application uses `hstore` reliably.
- Flat, text-only attributes.
- Query patterns use `hstore` operators efficiently.
- No nested JSON needed.
- Migration cost exceeds conversion benefits.

### 12.2. When to Choose JSONB?

- Attributes need nested objects/arrays.
- Values require JSON types.
- JSON path/query features are needed.
- Data originates from API documents.
- Preferring a built-in type without installing the `hstore` extension.

### 12.3. Do Not Put Everything into JSONB/hstore

Attributes with stable business semantics such as `price`, `status`, `tenant_id`, and `created_at` should normally be typed columns with clear constraints/indexes. Reserve flexible fields for genuinely dynamic parts.

## 13. Migrating from hstore to JSONB

A migration can use the `hstore_to_jsonb` function:

~~~sql
ALTER TABLE app.products
ADD COLUMN attributes_jsonb jsonb;
~~~

Backfill:

~~~sql
UPDATE app.products
SET attributes_jsonb = hstore_to_jsonb(attributes)
WHERE attributes_jsonb IS NULL;
~~~

### 13.1. Verify Conversion

Compare row counts, keys, and values on samples. Because `hstore` values are text, conversion does not automatically infer numeric/boolean types for keys.

### 13.2. Typed Conversion

If `weight_grams` must be a number, cast explicitly while constructing JSONB or normalize in the application:

~~~sql
UPDATE app.products
SET attributes_jsonb =
    jsonb_set(
        hstore_to_jsonb(attributes),
        '{weight_grams}',
        to_jsonb((attributes -> 'weight_grams')::integer),
        true
    )
WHERE attributes ? 'weight_grams';
~~~

Only run this once values are validated as valid integers.

### 13.3. Dual Write

During application transition, a dual write or compatibility layer may be needed. Prevent the two representations from drifting. Define a source of truth and a reconciliation process.

### 13.4. Index Migration

Create JSONB GIN/expression indexes matching the new query patterns. Do not assume an `hstore` index serves a JSONB column.

### 13.5. Cutover

Compare query results, constraints, performance, and application behavior. Only drop the `hstore` column/extension dependency once all consumers have migrated.

## 14. What Is ltree?

`ltree` is an extension providing a data type to represent a hierarchical path as a dot-separated sequence of labels. Each path describes a node's position in a hierarchy.

Example:

~~~text
Top
Top.Science
Top.Science.Astronomy
Top.Science.Physics
Top.Arts
Top.Arts.Music
~~~

`Top.Science.Astronomy` has ancestors `Top` and `Top.Science`; it is a descendant of `Top.Science`.

### 14.1. Install the Extension

~~~sql
CREATE EXTENSION ltree;
~~~

Verify:

~~~sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'ltree';
~~~

### 14.2. Data Types

- `ltree`: path composed of labels.
- `lquery`: pattern for matching labels/paths.
- `ltxtquery`: text-search-like query over labels.

### 14.3. Label Design

Use stable labels independent of user display names. Labels should have a clear canonical form; normalize spaces/special characters into safe IDs or slugs. Store display names in a separate column.

### 14.4. Not Every String Is a Valid ltree

Paths follow a specific grammar. Use `text2ltree` or cast after normalizing/validating. Never concatenate raw user input directly into SQL literals.

## 15. Creating a Hierarchy Table with ltree

~~~sql
CREATE TABLE app.categories (
    category_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    path ltree NOT NULL UNIQUE,
    label text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

Insert a hierarchy:

~~~sql
INSERT INTO app.categories (path, label)
VALUES
    ('Top'::ltree, 'Top'),
    ('Top.Science'::ltree, 'Science'),
    ('Top.Science.Astronomy'::ltree, 'Astronomy'),
    ('Top.Science.Physics'::ltree, 'Physics'),
    ('Top.Arts'::ltree, 'Arts'),
    ('Top.Arts.Music'::ltree, 'Music');
~~~

### 15.1. Unique Path

`UNIQUE(path)` ensures each path appears only once. It does not automatically guarantee all ancestor rows exist. If parent referential integrity is needed, add a parent relation/trigger or manage the hierarchy through controlled procedures.

### 15.2. Node Identity vs. Path

`category_id` is the stable identity for foreign keys. `path` represents position in the hierarchy. If a node moves to a new parent, its path and its descendants' paths must change.

### 15.3. Display Labels

Never use display names directly as paths if users can rename items, enter dots, or input invalid characters. Use slugs, immutable codes, or encoded IDs.

### 15.4. Root Path

Choose a clear root convention, such as `Top`, `Company`, or a domain-specific root token. Avoid unrelated roots if the business model requires a single tree.

## 16. Querying Ancestors and Descendants

The `@>` operator checks whether the left-hand path is an ancestor of (or equal to) the right-hand path.

~~~sql
SELECT path, label
FROM app.categories
WHERE path @> 'Top.Science.Astronomy'::ltree
ORDER BY nlevel(path);
~~~

The result returns the node and its ancestors.

### 16.1. Finding Descendants

The `<@` operator checks whether the left-hand path is a descendant of (or equal to) the right-hand path.

~~~sql
SELECT path, label
FROM app.categories
WHERE path <@ 'Top.Science'::ltree
ORDER BY path;
~~~

The result includes `Top.Science` and its descendants.

### 16.2. Finding Descendants Excluding the Current Node

~~~sql
SELECT path, label
FROM app.categories
WHERE path <@ 'Top.Science'::ltree
  AND path <> 'Top.Science'::ltree;
~~~

### 16.3. Depth

~~~sql
SELECT
    path,
    nlevel(path) AS depth
FROM app.categories
ORDER BY depth, path;
~~~

`nlevel` returns the number of labels in the path.

### 16.4. Extracting a Prefix

~~~sql
SELECT subpath(
    'Top.Science.Astronomy'::ltree,
    0,
    2
);
~~~

`subpath` extracts a portion of a path by offset/length. Offsets count from the start of the path; check function documentation for negative offsets and boundaries.

### 16.5. Finding Subpath Position

~~~sql
SELECT index(
    'Top.Science.Astronomy'::ltree,
    'Science'::ltree
);
~~~

The `index` function finds the position of a subpath within a path; if not found, the result indicates no match per function semantics.

### 16.6. Lowest Common Ancestor

~~~sql
SELECT lca(
    'Top.Science.Astronomy'::ltree,
    'Top.Science.Physics'::ltree
);
~~~

The result is the lowest common ancestor path—in this example, `Top.Science`.

## 17. lquery Patterns

`lquery` allows matching paths against labels and wildcard patterns.

~~~sql
SELECT path, label
FROM app.categories
WHERE path ~ 'Top.*.Astronomy'::lquery;
~~~

### 17.1. Wildcards

`*` can match labels per `lquery` semantics. Use patterns suited to your hierarchy depth.

### 17.2. Matching Multiple Levels

~~~sql
SELECT path
FROM app.categories
WHERE path ~ 'Top.*{1,2}.Music'::lquery;
~~~

Quantifiers control how many labels are matched by a pattern component according to `lquery` grammar.

### 17.3. Exact Path vs. Pattern

`path = 'Top.Arts.Music'::ltree` is equality. `path ~ 'Top.*.Music'::lquery` is pattern matching. Pick the simplest operator satisfying the query.

### 17.4. User-Generated Patterns

Never concatenate patterns from unvalidated input. `lquery` has its own grammar and wildcard/quantifier semantics; parameterize queries and validate business input.

## 18. Common ltree Functions

### 18.1. text2ltree and ltree2text

~~~sql
SELECT text2ltree('Top.Science.Astronomy');
SELECT ltree2text('Top.Science.Astronomy'::ltree);
~~~

### 18.2. nlevel

~~~sql
SELECT nlevel('Top.Science.Astronomy'::ltree);
~~~

### 18.3. subpath

~~~sql
SELECT subpath('Top.Science.Astronomy'::ltree, 1, 2);
~~~

### 18.4. lca

~~~sql
SELECT lca(
    'Top.Arts.Music'::ltree,
    'Top.Arts.Painting'::ltree
);
~~~

### 18.5. Concatenation

The `||` operator concatenates two `ltree` paths:

~~~sql
SELECT
    'Top.Science'::ltree || 'Astronomy.Stars'::ltree;
~~~

### 18.6. Normalizing Input

Convert application slugs to `ltree` paths through a validation layer. Do not treat casting `text` to `ltree` as sufficient validation for a business hierarchy.

## 19. Indexing ltree

GiST is the standard index for `ltree` hierarchy and pattern-matching queries.

~~~sql
CREATE INDEX categories_path_gist_idx
    ON app.categories
    USING GIST (path);
~~~

### 19.1. Ancestor/Descendant Queries

~~~sql
SELECT *
FROM app.categories
WHERE path <@ 'Top.Science'::ltree;
~~~

A GiST index can accelerate supported `ltree` operators.

### 19.2. Pattern Queries

~~~sql
SELECT *
FROM app.categories
WHERE path ~ 'Top.*.Astronomy'::lquery;
~~~

Check the operator class and query plan on your running version.

### 19.3. B-Tree Index

If the workload is primarily equality/ordering by path, a B-tree index may fit:

~~~sql
CREATE INDEX categories_path_btree_idx
    ON app.categories USING BTREE (path);
~~~

B-tree and GiST serve different operator families and query patterns. Do not create both without a measured need.

### 19.4. EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM app.categories
WHERE path <@ 'Top.Science'::ltree;
~~~

Small tables may cause the planner to choose a sequential scan even when an index exists. Check estimated/actual rows and table size before concluding an index does not work.

### 19.5. Index Write Cost

Every path change must update the index. When moving a large subtree, many rows and index entries can change. Account for WAL volume, lock duration, and replication impact.

## 20. Updating and Moving Subtrees

A materialized path stores the entire ancestor path in each row. When a node moves to a different parent, the path of the node and all its descendants must be updated.

Suppose we move subtree `Top.Science` under `Top.Knowledge`.

### 20.1. Update the Root Node

~~~sql
UPDATE app.categories
SET path = 'Top.Knowledge'::ltree
WHERE path = 'Top.Science'::ltree;
~~~

### 20.2. Update Descendants

For descendants beneath the old parent, take the suffix after the old prefix and prepend the new prefix:

~~~sql
UPDATE app.categories
SET path =
    'Top.Knowledge'::ltree
    || subpath(path, nlevel('Top.Science'::ltree))
WHERE path <@ 'Top.Science'::ltree
  AND path <> 'Top.Science'::ltree;
~~~

Both updates must be coordinated so readers never see an inconsistent hierarchy state. In production, run within an appropriate transaction, lock affected rows as needed, and ensure `UNIQUE(path)` does not conflict.

### 20.3. Unique Conflicts

If a destination path already exists, the update can violate `UNIQUE(path)`. Run preflight checks on the destination subtree and design conflict handling.

### 20.4. Atomic Moves

If applications must never observe a half-moved hierarchy, update the root and descendants together in a single transaction with an appropriate locking strategy.

### 20.5. Large Subtrees

A large subtree can generate substantial WAL and row/index updates. Consider batched/chunked migrations, a maintenance window, or an alternative model if moves happen frequently.

## 21. ltree and Adjacency Lists

An adjacency list stores each node alongside `parent_id`. This is a simple and very common tree model.

~~~sql
CREATE TABLE app.category_nodes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id bigint REFERENCES app.category_nodes(id),
    name text NOT NULL
);
~~~

### 21.1. Fetching Direct Children

~~~sql
SELECT *
FROM app.category_nodes
WHERE parent_id = $1;
~~~

Index `parent_id`:

~~~sql
CREATE INDEX category_nodes_parent_idx
    ON app.category_nodes (parent_id);
~~~

### 21.2. Recursive CTE for Descendants

~~~sql
WITH RECURSIVE descendants AS (
    SELECT
        id,
        parent_id,
        name,
        0 AS depth
    FROM app.category_nodes
    WHERE id = $1

    UNION ALL

    SELECT
        child.id,
        child.parent_id,
        child.name,
        parent.depth + 1
    FROM app.category_nodes AS child
    JOIN descendants AS parent
      ON child.parent_id = parent.id
)
SELECT *
FROM descendants
ORDER BY depth, id;
~~~

### 21.3. Advantages

- One row represents one node.
- `parent_id` has a foreign key.
- Moving a node usually only updates `parent_id`.
- No need to rewrite paths for all descendants.
- Suits hierarchies that change frequently.

### 21.4. Disadvantages

- Querying an entire subtree requires a recursive CTE.
- Large depths can complicate queries.
- Cycles must be prevented via business logic/triggers or controlled procedures; a foreign key alone does not forbid a node from becoming its own ancestor.

### 21.5. When to Choose Adjacency Lists

Choose this when the tree sees frequent updates/moves, simple parent relationships are required, and recursive queries meet performance targets.

## 22. ltree / Materialized Path vs. Adjacency List

| Criterion | Adjacency List | ltree / Materialized Path |
| --- | --- | --- |
| Parent lookup | Direct via `parent_id` | Extract prefix or store extra `parent_id` |
| Subtree lookup | Recursive CTE | Path containment |
| Move subtree | Usually changes node's `parent_id` | Updates paths of descendants |
| Referential integrity | FK to parent row | Path uniqueness does not guarantee parent exists |
| Index | B-tree on `parent_id` | GiST/B-tree on `path` |
| Write cost on move | Usually low | Can be high for large subtrees |
| Reading hierarchy | Recursive query | Path operators |
| DAG / multiple parents | Can use edge table | Single path cannot represent it fully |

### 22.1. Hybrid Model

You can store both `parent_id` and `path`:
- `parent_id` serves as the canonical relation for referential integrity.
- `path` accelerates subtree queries.
- A transaction/procedure keeps both representations synchronized.

A hybrid model increases write complexity. It requires invariants and a reconciliation job.

### 22.2. Avoid Arbitrary Redundant Data

If `path` can be derived from parent relationships yet is persisted for speed, define the source of truth and how it updates when the hierarchy changes.

## 23. Closure Table

A closure table stores every ancestor-descendant pair along with depth.

~~~sql
CREATE TABLE app.category_closure (
    ancestor_id bigint NOT NULL REFERENCES app.category_nodes(id),
    descendant_id bigint NOT NULL REFERENCES app.category_nodes(id),
    depth integer NOT NULL CHECK (depth >= 0),
    PRIMARY KEY (ancestor_id, descendant_id)
);

CREATE INDEX category_closure_descendant_idx
    ON app.category_closure (descendant_id, ancestor_id);
~~~

Each node typically has a self-row with depth `0`; child nodes have pairs with their parent at depth `1` and higher ancestors at corresponding depths.

### 23.1. Subtree Query

~~~sql
SELECT n.*, c.depth
FROM app.category_closure AS c
JOIN app.category_nodes AS n
  ON n.id = c.descendant_id
WHERE c.ancestor_id = $1
ORDER BY c.depth, n.id;
~~~

### 23.2. Ancestor Query

~~~sql
SELECT n.*, c.depth
FROM app.category_closure AS c
JOIN app.category_nodes AS n
  ON n.id = c.ancestor_id
WHERE c.descendant_id = $1
ORDER BY c.depth DESC;
~~~

### 23.3. Advantages

- Simple ancestor/descendant lookups.
- Foreign keys can be enforced on both ends.
- Fast B-tree hierarchy queries.
- Can be extended to graph edges if multiple parents are permitted, though semantics must be defined separately.

### 23.4. Disadvantages

- Row count can grow with the number of ancestor-descendant pairs.
- Inserts/moves require updating many closure rows.
- Easy to corrupt if closure and node tables are not updated in the same transaction.

### 23.5. When to Choose a Closure Table

Choose this when subtree/ancestor queries are very frequent, hierarchy updates are rarer than reads, and strong relational integrity is needed.

## 24. Nested Sets

Nested sets assign each node two values, `left`/`right` (or `lft`/`rgt`), representing its traversal positions.

~~~sql
CREATE TABLE app.category_nested (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    lft bigint NOT NULL,
    rgt bigint NOT NULL,
    CHECK (lft < rgt),
    UNIQUE (lft),
    UNIQUE (rgt)
);
~~~

### 24.1. Subtree Query

~~~sql
SELECT child.*
FROM app.category_nested AS parent
JOIN app.category_nested AS child
  ON child.lft >= parent.lft
 AND child.rgt <= parent.rgt
WHERE parent.id = $1
ORDER BY child.lft;
~~~

### 24.2. Ancestor Query

~~~sql
SELECT parent.*
FROM app.category_nested AS node
JOIN app.category_nested AS parent
  ON parent.lft <= node.lft
 AND parent.rgt >= node.rgt
WHERE node.id = $1
ORDER BY parent.lft;
~~~

### 24.3. Advantages

Subtree reads can be simple and efficient.

### 24.4. Disadvantages

Inserts/moves may require renumbering many `left`/`right` values. For frequently changing hierarchies, write amplification and locking can be high.

### 24.5. When to Choose Nested Sets

Suited for nearly static taxonomies with heavy subtree reads and rare updates. Requires a transaction/procedure to maintain consistent numbering.

## 25. Graphs and DAGs: When Hierarchies Have Multiple Parents

`ltree` represents a single path. A node in a tree has one ancestor chain. If a node has multiple parents or relationships form cycles, a single path cannot represent the whole graph.

### 25.1. Edge Table

~~~sql
CREATE TABLE app.graph_nodes (
    node_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label text NOT NULL
);

CREATE TABLE app.graph_edges (
    source_id bigint NOT NULL REFERENCES app.graph_nodes(node_id),
    target_id bigint NOT NULL REFERENCES app.graph_nodes(node_id),
    edge_type text NOT NULL,
    PRIMARY KEY (source_id, target_id, edge_type)
);

CREATE INDEX graph_edges_target_idx
    ON app.graph_edges (target_id, source_id);
~~~

### 25.2. Recursive Traversal

Use a recursive CTE to traverse edges. For graphs with cycles, include cycle detection/path tracking or PostgreSQL's `CYCLE` clause on supported versions.

### 25.3. Do Not Force ltree onto Every Graph

If an entity has multiple parents, typed relationships, or allowed cycles, an edge table is a better representation. `ltree` can still represent a specific materialized traversal/path if you define which path is canonical.

## 26. Specialized Data Model: JSONB

JSONB is a built-in type for JSON documents in a binary representation.

~~~sql
CREATE TABLE app.api_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now()
);
~~~

### 26.1. Accessing Fields

~~~sql
SELECT
    payload ->> 'event_type' AS event_type,
    payload #>> '{customer,address,city}' AS city
FROM app.api_events;
~~~

`->` returns JSON/JSONB; `->>` returns `text`. `#>`/`#>>` traverse via path arrays.

### 26.2. Containment

~~~sql
SELECT *
FROM app.api_events
WHERE payload @> '{"event_type":"order.created"}'::jsonb;
~~~

### 26.3. GIN Index

~~~sql
CREATE INDEX api_events_payload_gin_idx
    ON app.api_events USING GIN (payload);
~~~

Different JSONB operator classes have different trade-offs. Choose `jsonb_ops` or `jsonb_path_ops` based on the operators and query patterns you need to support.

### 26.4. Typed Columns Remain Important

Keys that are frequently filtered/sorted/joined or carry strong constraints should be considered for extraction into typed columns. JSONB does not replace foreign keys or domain constraints.

## 27. Specialized Data Model: Arrays

Arrays store collections of values sharing an element type.

~~~sql
CREATE TABLE app.articles (
    article_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    tags text[] NOT NULL DEFAULT '{}'
);
~~~

### 27.1. Containment and Overlap

~~~sql
SELECT *
FROM app.articles
WHERE tags @> ARRAY['postgresql'];

SELECT *
FROM app.articles
WHERE tags && ARRAY['database', 'sql'];
~~~

### 27.2. GIN Index

~~~sql
CREATE INDEX articles_tags_gin_idx
    ON app.articles USING GIN (tags);
~~~

### 27.3. Arrays vs. Child Tables

Arrays are convenient for small collections not requiring per-element foreign keys/metadata. If each tag needs an owner, status, description, join behavior, uniqueness, or an independent lifecycle, use a normalized child table.

### 27.4. Array Updates

Array operations can rewrite the value and update the GIN index. For large arrays or frequent per-element mutations, consider a relational model.

## 28. Specialized Data Model: Range and Multirange

Range types represent a continuous interval, such as a date or timestamp range.

Common built-in range types:
- `int4range`.
- `int8range`.
- `numrange`.
- `tsrange`.
- `tstzrange`.
- `daterange`.

### 28.1. Creating a Range

~~~sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)') AS billing_period;
~~~

`[)` means include lower bound, exclude upper bound. This is a useful convention to prevent overlap between adjacent periods.

### 28.2. Overlap

The `&&` operator checks whether two ranges overlap.

~~~sql
SELECT *
FROM app.bookings
WHERE during && tstzrange($1, $2, '[)');
~~~

### 28.3. Contains

~~~sql
SELECT *
FROM app.bookings
WHERE during @> now();
~~~

### 28.4. Exclusion Constraints

~~~sql
CREATE EXTENSION btree_gist;

CREATE TABLE app.room_reservations (
    reservation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id bigint NOT NULL,
    during tstzrange NOT NULL,
    EXCLUDE USING GIST (
        room_id WITH =,
        during WITH &&
    )
);
~~~

This constraint prevents the same room from having two overlapping reservations. `btree_gist` provides GiST operator classes for many scalar types so equality can be combined with range overlap.

### 28.5. Multirange

Multirange represents sets of non-contiguous ranges and is supported from PostgreSQL 14 onward. Use it when an entity has multiple disjoint time windows.

### 28.6. Boundary Semantics

Distinguish inclusive/exclusive bounds, unbounded bounds, and empty ranges. Standardize conventions before building queries/constraints.

## 29. Specialized Data Model: Network Types

PostgreSQL includes these types:
- `inet`: IPv4 or IPv6 host/address, optionally with netmask.
- `cidr`: IPv4/IPv6 network.
- `macaddr` and `macaddr8`: hardware addresses.

### 29.1. Creating Columns

~~~sql
CREATE TABLE app.network_assets (
    asset_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    host_ip inet NOT NULL,
    subnet cidr
);
~~~

### 29.2. Subnet Containment

~~~sql
SELECT *
FROM app.network_assets
WHERE host_ip <<= '10.20.0.0/16'::inet;
~~~

Network operators allow checking subnet relationships instead of parsing strings manually.

### 29.3. Host/Network Distinction

Use `inet` for host addresses that may carry a mask; use `cidr` for canonical networks. Validate domain semantics before writing.

### 29.4. Indexing

B-tree can help for equality/ordering; GiST/SP-GiST operator classes are supported depending on type/version for certain network operations. Check documentation and `EXPLAIN` for your specific operators.

## 30. Specialized Data Model: Full-Text Search

PostgreSQL full-text search uses `tsvector` and `tsquery`.

~~~sql
ALTER TABLE app.documents
ADD COLUMN search_vector tsvector;
~~~

Generating vectors:

~~~sql
UPDATE app.documents
SET search_vector =
    to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body, ''));
~~~

### 30.1. GIN Index

~~~sql
CREATE INDEX documents_search_gin_idx
    ON app.documents USING GIN (search_vector);
~~~

### 30.2. Querying

~~~sql
SELECT *
FROM app.documents
WHERE search_vector @@ plainto_tsquery('english', 'postgres database');
~~~

### 30.3. Configuration

Language configuration affects stemming, stop words, and tokenization. Pick a configuration suited to the content, or use `simple` for tokenization without language-specific stemming.

### 30.4. Maintenance

If using generated columns, triggers, or application-managed vectors, ensure `search_vector` stays updated when source text changes. GIN indexes add write overhead.

## 31. Specialized Data Model: Trigram Similarity

The `pg_trgm` extension provides trigram-based similarity and operators for fuzzy text search.

~~~sql
CREATE EXTENSION pg_trgm;

CREATE INDEX customers_name_trgm_idx
    ON app.customers USING GIN (name gin_trgm_ops);
~~~

### 31.1. Similarity

~~~sql
SELECT
    name,
    similarity(name, 'Postgres') AS score
FROM app.customers
ORDER BY score DESC
LIMIT 20;
~~~

### 31.2. LIKE/ILIKE

`pg_trgm` can accelerate `LIKE`/`ILIKE` patterns that contain enough trigrams. Very short patterns may not benefit.

### 31.3. Thresholds

Similarity thresholds affect operator results. Manage thresholds per session/application if using similarity-based operators.

### 31.4. Not a Replacement for Full-Text Search

Trigrams excel at typos/fuzzy matching and substring-like search; full-text search is better suited to tokenization, stemming, and document search semantics.

## 32. Specialized Data Model: Spatial Types

PostGIS adds `geometry`/`geography` types, spatial functions, and spatial indexes.

### 32.1. Geometry vs. Geography

- `geometry` uses a planar coordinate system; units/measurements depend on the SRID.
- `geography` supports operations on the Earth's surface with global-coordinate semantics, with performance and function-support trade-offs.

### 32.2. Extension

~~~sql
CREATE EXTENSION postgis;
~~~

The package must exist on the server and be supported by the provider.

### 32.3. Spatial Index

~~~sql
CREATE INDEX places_geom_gist_idx
    ON app.places USING GIST (geom);
~~~

### 32.4. Spatial Query

~~~sql
SELECT *
FROM app.places
WHERE ST_DWithin(
    geom,
    ST_SetSRID(ST_MakePoint($1, $2), 4326),
    $3
);
~~~

Ensure SRID, `geometry`/`geography` type, and distance units match. With `geometry`, distance units depend on the coordinate system; do not treat degrees as meters.

### 32.5. Spatial Modeling

Store SRID explicitly, validate geometry types/dimensions, and select GiST/SP-GiST/operator support for real queries.

## 33. Specialized Data Model: UUIDs and Identifiers

`uuid` is a built-in type for distributed identifiers or avoiding sequence coordination across systems.

~~~sql
CREATE TABLE app.external_events (
    event_id uuid PRIMARY KEY,
    payload jsonb NOT NULL
);
~~~

### 33.1. Trade-Offs

Random UUID values can have worse B-tree insertion locality than sequential integer keys. UUID variants differ in locality/time ordering; choose based on generator/version and privacy requirements.

### 33.2. Do Not Use UUIDs Only Because Everything Sounds Distributed

`bigint` identity columns are usually smaller and more index-friendly for single-writer systems. Choose according to integration, generation, and data lifecycle needs.

## 34. Specialized Data Model: XML and Composite Types

### 34.1. XML

PostgreSQL has an `xml` type and functions to parse/query XML. Use it when integration mandates XML or storing/validating XML documents. For new document APIs, JSONB is usually more common.

### 34.2. Composite Types

Composite types represent records consisting of multiple typed fields. They can be useful for function arguments/results or domain-specific structured values.

~~~sql
CREATE TYPE app.address_type AS (
    street text,
    city text,
    postal_code text
);
~~~

### 34.3. Domain Types

`DOMAIN` creates a type over a base type with reusable constraints:

~~~sql
CREATE DOMAIN app.nonnegative_amount AS numeric(14,2)
CHECK (VALUE >= 0);
~~~

### 34.4. When to Normalize into a Separate Table?

If a structured value requires foreign keys, independent updates, per-child indexing, or multiple rows, normalized tables usually fit better than composite/JSON-like storage.

## 35. Choosing a Hierarchy Model

| Model | Subtree Read | Node Move | Integrity | Best Fit |
| --- | --- | --- | --- | --- |
| Adjacency list | Recursive CTE | Cheaper | Direct parent FK | Frequently changing trees |
| `ltree` / materialized path | Path containment | Updates descendants | Requires parent/path consistency management | Frequent subtree reads |
| Closure table | Ancestor-descendant join | Updates multiple pairs | FKs on endpoints | Frequent ancestor queries |
| Nested sets | Range predicate | Can require many updates | Requires `left`/`right` management | Nearly static hierarchies |
| Edge table | Recursive graph traversal | Add/remove edges | FKs on endpoints | DAGs / multi-parent graphs |

### 35.1. Choose by Read/Write Ratio

If subtree reads dominate and the hierarchy rarely changes, `ltree`/closure tables may pay off. If moves happen frequently, adjacency lists may be simpler.

### 35.2. Choose by Relationship Cardinality

If each node has at most one parent, tree models apply. If a node has multiple parents, a DAG/graph representation or edge relation is required.

### 35.3. Choose by Integrity Needs

Foreign keys and constraints should enforce critical invariants. A materialized path may need triggers/procedures to ensure parent paths exist and descendants stay synchronized.

### 35.4. Choose by Query Patterns

List essential queries before choosing a type:
- Get direct children.
- Get all descendants.
- Get ancestors.
- Find lowest common ancestor.
- Move subtree.
- Search by label.
- Traverse multiple relationship types.
- Detect cycles/reachability.

## 36. Constraints for Flexible Attributes

`hstore`/JSONB allow flexible fields but do not automatically enforce domain validity.

### 36.1. Required Keys

`CHECK` constraints can be used:

~~~sql
ALTER TABLE app.products
ADD CONSTRAINT products_color_required
CHECK (attributes ? 'color');
~~~

### 36.2. Allowed Values

~~~sql
ALTER TABLE app.products
ADD CONSTRAINT products_color_allowed
CHECK (
    NOT (attributes ? 'color')
    OR attributes -> 'color' IN ('black', 'white', 'blue')
);
~~~

If a key can hold SQL `NULL`, verify how `CHECK` behaves with `NULL`. PostgreSQL `CHECK` rejects a row only when the expression evaluates to `FALSE`; `UNKNOWN`/`NULL` is not treated as `FALSE`. Use `IS TRUE`/`IS NOT FALSE` per desired logic.

### 36.3. Typed Attributes

If `weight_grams` is numeric, a `CHECK` can validate format, though malformed casts can raise errors. With many typed attributes, a normalized table or JSONB schema validation function may be easier to manage.

### 36.4. Flexible Schema Does Not Mean Schema-Less

Document allowed keys, value formats, defaults, owners, deprecation processes, and data retention. Versioning of attribute definitions still requires management.

## 37. Indexing Specialized Types

Indexes must support the exact operators used by queries.

| Data Model | Common Indexes | Query Pattern |
| --- | --- | --- |
| `hstore` | GIN/GiST; expression B-tree | Key existence, containment, selected key |
| `ltree` | GiST; B-tree equality/ordering | Ancestor/descendant, `lquery`, equality |
| JSONB | GIN/expression B-tree | Containment, path/key filters |
| Arrays | GIN | Contains/overlap |
| Ranges | GiST/SP-GiST per type/operator | Overlap/contains |
| `inet`/`cidr` | B-tree and supported GiST/SP-GiST ops | Equality/subnet |
| `tsvector` | GIN/GiST | Full-text match |
| PostGIS | GiST/SP-GiST per geometry/operator | Spatial predicates |
| `pg_trgm` text | GIN/GiST trigram opclass | Similarity/`LIKE`/`ILIKE` |

### 37.1. Operator Classes

An index only supports the operators provided by its operator class. Do not assume all operators on a type work with every index method.

### 37.2. Query Expressions

An expression index requires a matching query expression. For instance, an index on `attributes -> 'color'` serves that expression, not arbitrary JSON conversions.

### 37.3. Selectivity

An index may not help if the predicate matches most rows. The planner choosing a sequential scan can be correct.

### 37.4. Index Maintenance

Specialized types can create large indexes with high write overhead. Measure index size, build duration, WAL rate, and update cost.

## 38. Data Migration Between Models

Migrations between `hstore`, JSONB, `ltree`, and relational tables should follow a clear plan.

### 38.1. Expand

Add the new representation or columns, create required indexes/constraints, and deploy compatible code.

### 38.2. Backfill

Backfill in batches for large tables. Monitor WAL, locks, replica lag, and disk capacity.

### 38.3. Validate

Compare row counts, values, hierarchy relationships, duplicate keys, orphan nodes, and query results.

### 38.4. Dual Write / Cutover

Establish the source of truth. If dual writing, run reconciliation to catch drift. Cut over via feature flags or release steps.

### 38.5. Contract

After an observation period, stop writes to the old representation, archive if needed, and drop old columns/extension dependencies per change plan.

### 38.6. Rollback

Schema rollback does not necessarily restore transformed data. Retain backups and migration mappings sufficient to recover per business requirements.

## 39. Performance and Storage Trade-Offs

### 39.1. Flexible Columns

`hstore`/JSONB reduce frequent column churn but can complicate querying typed values. Attributes filtered often should be considered for expression indexes or dedicated columns.

### 39.2. Path Denormalization

`ltree` stores ancestor paths in every row. Subtree reads are fast, while moving subtrees updates many rows.

### 39.3. GIN Indexes

GIN excels at inverted lookups but can consume storage and update work. For write-heavy tables, evaluate `fastupdate`/pending-list behavior by operator class and version; do not tune without evidence.

### 39.4. GiST Indexes

GiST supports many specialized operators such as hierarchy/range/spatial. Effectiveness depends on operator class, data distribution, and queries.

### 39.5. TOAST

Large `hstore`/JSONB values may be TOASTed. Monitor `pg_column_size`, `pg_total_relation_size`, and table/index growth. Do not assume flexible values always stay small.

### 39.6. Cache Locality

A JSONB/`hstore` column packing many fields may read more bytes when queries only need one attribute. Extracting hot attributes into columns can improve selectivity and cache behavior.

## 40. Extension Security and Operations

### 40.1. Package Availability

Install extension packages on all nodes eligible to run the database. Physical replication does not synchronize server binaries.

### 40.2. Trusted / Superuser

Check extension control metadata and provider policies. Never grant superuser to the application runtime just for `CREATE EXTENSION`.

### 40.3. Schema / search_path

Place extension objects in a managed schema. Prevent untrusted roles from holding `CREATE` privileges on schemas appearing before schemas with trusted functions.

### 40.4. Upgrade Lifecycle

Check available versions, update paths, release notes, and compatibility with the PostgreSQL major version.

### 40.5. Backup / Restore

`pg_dump` can emit `CREATE EXTENSION` and config data per extension metadata, but it does not bundle shared libraries/control files. Targets need compatible packages.

### 40.6. Managed Services

Providers may restrict the extension allowlist and role privileges. Verify supported versions and required parameters before designing.

## 41. Troubleshooting hstore

### 41.1. Type hstore Does Not Exist

The usual cause is that the extension is not installed in the current database or the package is missing from the server.

~~~sql
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name = 'hstore';

CREATE EXTENSION hstore;
~~~

If the package is missing, install the matching package or check the managed-service allowlist.

### 41.2. Query Not Using GIN Index

Check:
- Does the predicate use an operator supported by the opclass?
- Is the index valid?
- Are statistics up to date?
- Is predicate selectivity high enough?
- Is the table too small?
- Does the query expression match the index expression?

Use `EXPLAIN (ANALYZE, BUFFERS)` in an appropriate environment.

### 41.3. Cast Errors

If casting an `hstore` text value to integer/date fails, identify rows with malformed values. Validate and clean data before creating expression indexes or generated expressions relying on casts.

### 41.4. Attribute Drift

Generate a report of keys/values using `each()` to spot legacy keys, typos, and inconsistent value formats. Standardize definitions and deprecate per rollout plan.

## 42. Troubleshooting ltree

### 42.1. Invalid Path Label

The path violates `ltree` grammar. Normalize input and use `text2ltree`/cast after validation. Store display labels separately.

### 42.2. Subtree Query Returns Wrong Results

Check operator direction:
- `ancestor @> descendant`.
- `descendant <@ ancestor`.

This is a common source of confusion.

### 42.3. GiST Not Used

Check operators, index validity, statistics, selectivity, and `EXPLAIN` plans. Simple equality queries may suit B-tree better.

### 42.4. Path Move Conflict

A destination path may collide with another node. Run preflight checks on path uniqueness and descendants before updating.

### 42.5. Orphan Paths

`UNIQUE(path)` does not guarantee ancestor rows exist. Create a validation procedure/trigger or retain `parent_id` with an FK if that invariant matters.

### 42.6. Unsuitable Graph

If nodes have multiple parents, cycles, or typed edges, switch to an edge table/graph model. Do not try to cram multiple paths into one `ltree` column without clear semantics.

## 43. Common Mistakes

| Mistake | Consequence | Correct Practice |
| --- | --- | --- |
| Using `hstore` for nested documents | Hard to query/validate | Choose JSONB |
| Storing numbers/booleans as unvalidated text | Cast errors and wrong comparisons | Typed columns or validation |
| Dumping all attributes into `hstore` | Business columns hard to enforce | Separate stable attributes |
| Treating empty `hstore` and `NULL` identically | Unclear semantics | Define defaults/nulls explicitly |
| Using `->` to check key existence | Cannot distinguish missing from `NULL` | Use `?`/`defined` |
| Not indexing `hstore` filters | Sequential scans on large tables | GIN/GiST/expression index per query |
| Adding GIN to every `hstore` column | Write/storage overhead | Index per workload |
| Using `ltree` for multi-parent DAGs | Model misrepresents graph | Edge table |
| Using display names as labels | Rename and path grammar issues | Stable IDs/slugs |
| Assuming `UNIQUE(path)` ensures full hierarchy integrity | Missing ancestor rows possible | Parent FK/trigger/procedure |
| Confusing direction of `@>` and `<@` | Wrong ancestors/descendants returned | Remember left `ancestor @> right` |
| Moving a node without updating descendants | Inconsistent paths | Transactional subtree migration |
| Using nested sets for constantly changing hierarchies | Massive row updates | Adjacency list/`ltree`/closure |
| Using adjacency list for every deep subtree query | Complex recursive queries | Benchmark `ltree`/closure |
| Failing to measure GIN/GiST overhead | Increased WAL and write latency | Measure before/after |
| Using JSONB for all typed fields | Harder constraints/indexing | Extract hot typed columns |
| Using ranges without standardized bounds | Overlap/off-by-one bugs | Adopt `[)` convention |
| Using wrong geometry SRID | Wrong distances/areas | Validate SRID/units |
| Assuming installing extensions on primary suffices | Failover node lacks packages | Provision all HA nodes |
| Never testing restores | Target lacks extension binaries | Restore rehearsal |

## 44. Practical PostgreSQL Exercises

Perform on lab/staging. Installing extensions requires appropriate packages/privileges; do not alter production schemas solely for experimentation.

1. **Install hstore:** install the extension in the lab database.
2. **Inventory:** query `pg_available_extensions` and `pg_extension`.
3. **Create table:** create `products` with `attributes hstore`.
4. **Insert literal:** insert an `hstore` literal with three pairs.
5. **Constructor:** build an `hstore` using `hstore(text[], text[])`.
6. **Read value:** fetch a key using `->`.
7. **Missing key:** compare a non-existent key with SQL `NULL`.
8. **Key exists:** filter with `?`.
9. **All keys:** filter with `?&`.
10. **Any key:** filter with `?|`.
11. **Defined:** distinguish `exist` and `defined`.
12. **Containment:** query using `@>`.
13. **Contained by:** query using `<@`.
14. **Equality:** compare two `hstore` values.
15. **Update:** add a pair using `||`.
16. **Overwrite:** overwrite an existing key.
17. **Delete key:** delete one key using `-`.
18. **Delete array:** delete multiple keys.
19. **Delete pairs:** test deleting pairs matching an `hstore` value.
20. **akeys:** list keys.
21. **avals:** list values.
22. **each:** unnest pairs into rows.
23. **slice:** extract a subset of keys.
24. **Array conversion:** convert `hstore` to array/matrix.
25. **JSON conversion:** use `hstore_to_jsonb`.
26. **Typed cast:** cast `weight_grams` to `integer`.
27. **Invalid value:** insert a malformed numeric value and observe the cast error.
28. **GIN:** create a GIN index on `attributes`.
29. **Containment plan:** `EXPLAIN` a `@>` query.
30. **Key plan:** `EXPLAIN` a `?` query.
31. **GiST:** benchmark a GiST index on `hstore`.
32. **Expression index:** create a B-tree index for `attributes -> 'color'`.
33. **Write overhead:** compare inserts/updates before and after GIN.
34. **JSONB comparison:** store the same sample in JSONB and compare queries.
35. **Migration:** backfill `hstore` into JSONB.
36. **Typed JSON:** convert a text key into a JSON number with validation.
37. **Dual write:** design source-of-truth during migration.
38. **Attribute audit:** summarize keys using `each()`.
39. **Key policy:** build a table defining allowed keys.
40. **Install ltree:** install the `ltree` extension in lab.
41. **Path table:** create `categories` with `path ltree`.
42. **Insert tree:** create a three-level hierarchy.
43. **Ancestors:** query using `@>`.
44. **Descendants:** query using `<@`.
45. **Exclude self:** fetch descendants excluding the root node.
46. **Depth:** compute `nlevel`.
47. **Subpath:** extract prefix/suffix.
48. **Index function:** locate a subpath with `index()`.
49. **LCA:** compute lowest common ancestor.
50. **Concatenate:** join paths with `||`.
51. **lquery:** match paths with wildcards.
52. **Quantifier:** test `lquery` across multiple levels.
53. **GiST:** create a GiST index on `path`.
54. **B-tree:** create a B-tree index for equality and compare.
55. **EXPLAIN:** compare ancestor/descendant query plans.
56. **Move subtree:** move a subtree and update descendants.
57. **Unique conflict:** trigger a duplicate destination path and handle it.
58. **Orphan check:** find paths missing an ancestor row.
59. **Stable labels:** design slugs/IDs instead of display names.
60. **Adjacency list:** create nodes with `parent_id`.
61. **Recursive CTE:** retrieve descendants from a node.
62. **Cycle:** simulate a cycle and design prevention.
63. **Closure table:** create ancestor-descendant pairs.
64. **Closure query:** query ancestors and descendants.
65. **Closure move:** update closure rows when moving a subtree.
66. **Nested sets:** build an `lft`/`rgt` model.
67. **Nested subtree:** query descendants by interval.
68. **Nested move:** analyze the cost of moving a node.
69. **DAG:** create `graph_nodes` and `graph_edges`.
70. **Multi-parent:** model a node with two parents.
71. **JSONB:** create a document table and GIN index.
72. **Arrays:** create a `tags` array and GIN index.
73. **Ranges:** create `tstzrange` for booking periods.
74. **Exclusion:** use `btree_gist` to prevent overlap.
75. **Network:** store `inet`/`cidr` and query subnets.
76. **Full-text:** create `tsvector` and a GIN index.
77. **Trigram:** install `pg_trgm` and run fuzzy search.
78. **Spatial:** explore `geometry`/`geography` and PostGIS GiST.
79. **Model choice:** select data models for a taxonomy, product attributes, and dependency graph.
80. **Comprehensive design:** design a PostgreSQL schema for a catalog with flexible attributes, multi-level hierarchy, search, constraints, indexes, migrations, extension provisioning, and capacity/performance planning.

## 45. Data Model Selection Checklist

### hstore/JSONB

- [ ] Are the attributes genuinely flexible?
- [ ] Are values only text, or are JSON types needed?
- [ ] Are nested arrays/objects needed?
- [ ] Which keys should be typed columns?
- [ ] Is there an allowed-key/value policy?
- [ ] Are there indexes matching query patterns?
- [ ] Are migration/extension dependencies accounted for?

### Hierarchy

- [ ] Is the structure a tree, DAG, or general graph?
- [ ] Does each node have at most one parent?
- [ ] Are subtree reads or moves more frequent?
- [ ] Is an FK required to ensure parent existence?
- [ ] Do paths use stable labels?
- [ ] Is cycle prevention in place?
- [ ] Have index and path-update costs been benchmarked?

### Specialized Types

- [ ] Are range boundaries standardized?
- [ ] Are host/subnet network semantics clear?
- [ ] Does the full-text language configuration match the content?
- [ ] Are spatial SRID/units accurate?
- [ ] Do array elements require foreign keys/metadata?
- [ ] Does the index operator class support the queries?
- [ ] Are extension packages installed on all HA/restore nodes?

### Production Readiness

- [ ] Has backup/restore been tested?
- [ ] Are extension versions/provenance pinned?
- [ ] Are permissions/`search_path` secure?
- [ ] Have query plans and write overhead been benchmarked?
- [ ] Have migration/rollback been rehearsed?
- [ ] Are monitoring and capacity alerts ready?

## 46. Summary

PostgreSQL can represent many data models beyond ordinary scalar columns. `hstore` fits flat key/value attributes; `ltree` fits materialized paths for tree hierarchies; JSONB, arrays, ranges, network, full-text, and spatial types serve other specialized structures.

~~~text
FLEXIBLE ATTRIBUTES
  hstore (flat text key/value)
  JSONB (nested typed document)
             |
             v
HIERARCHY / RELATIONSHIPS
  ltree (materialized tree path)
  adjacency list
  closure table
  nested sets
  edge table (DAG/graph)
             |
             v
DOMAIN-SPECIFIC TYPES
  arrays / ranges / inet / tsvector
  UUID / XML / PostGIS
             |
             v
OPERATORS + INDEXES + CONSTRAINTS
  GIN / GiST / B-tree / SP-GiST
             |
             v
MIGRATION / MONITORING / OPERATIONS
~~~

Key principles:

- **hstore is flat, text-oriented key/value storage.** Use it for simple attributes; choose JSONB when nested structures and typed JSON values are needed.
- **Keep stable business attributes as typed columns.** Flexible storage does not replace constraints, foreign keys, and relational design.
- **Use the right hstore operators.** `?`, `?&`, `?|`, `@>`, `<@`, `->`, and `||` express different query patterns.
- **Index for the operators actually used.** GIN/GiST serve `hstore` containment/key queries; expression B-tree fits filtering on a specific key.
- **ltree represents a path in a hierarchy.** `ancestor @> descendant`; `descendant <@ ancestor`.
- **Paths need stable labels.** Store display names separately and normalize identifiers.
- **ltree makes subtree reads fast, but subtree moves are write-heavy.** Update the node's path and descendants consistently.
- **`UNIQUE(path)` alone does not guarantee hierarchy integrity.** If parent existence must be enforced, use a parent FK or controlled procedures/triggers.
- **DAGs/graphs require an edge model.** A single `ltree` path cannot properly represent multiple parents or cycles.
- **Choose adjacency list, closure table, nested sets, or `ltree` by read/write pattern.** No single hierarchy model is optimal for every workload.
- **Ranges, network, full-text, and spatial types provide specialized operators.** Use their native types and indexes rather than parsing text manually.
- **Extensions are production dependencies.** Install packages on all HA/restore nodes, pin versions, and test backup/restore.
- **Measure both read and write performance.** Specialized indexes accelerate queries but also increase storage, WAL, and update costs.

A sound data model expresses actual business semantics, lets PostgreSQL enforce validity, and leverages appropriate operators and indexes. Choose `hstore`, `ltree`, or specialized types when the data structure genuinely warrants them, then govern constraints, migrations, and operations as part of the production schema.
