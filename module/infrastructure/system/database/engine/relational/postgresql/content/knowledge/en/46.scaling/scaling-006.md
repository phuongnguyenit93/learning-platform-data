# Data Types, Operators, Operator Classes, and Extensible Access Methods

PostgreSQL allows extending its type system, operators, and indexing mechanisms. A new data type can define how values are stored, input/output, and compared. Operators provide syntax for applications and the planner to express comparisons or operations on that type. An operator class describes how an index access method understands those operators and invokes corresponding support functions. An access method provides the actual indexing or table storage algorithm and structure.

These four components are closely connected yet play distinct roles:

```text
       Data type
       Representation, input/output, semantics
             |
             v
       Operators
       =, <, @>, &&, <->, ...
             |
             v
       Operator class / operator family
       Strategies + support functions
             |
             v
       Access method
       B-tree / Hash / GiST / SP-GiST / GIN / BRIN
             |
             v
       Index structure and query execution
```

This lesson belongs to the **Scaling** chapter of the *Database Engine Relational PostgreSQL* module. It progresses from built-in data types, creating types and operators, to operator class/family contracts, index access methods, and the APIs extensions use to add new access methods.

After this lesson, you will be able to:

1. Distinguish type, operator, operator class, operator family, and access method.
2. Choose among domain, enum, composite, range, and custom base type.
3. Declare operators with commutator, negator, selectivity estimators, and join estimators.
4. Understand strategy numbers and support functions in operator classes.
5. Use operator families for multiple input types and cross-type operators.
6. Choose B-tree, Hash, GiST, SP-GiST, GIN, or BRIN based on access pattern.
7. Understand the role of GiST/GIN/SP-GiST/BRIN support functions.
8. Inspect and create indexes with explicit operator classes.
9. Identify extensions that provide new operator classes or access methods.
10. Understand the boundary between SQL DDL and the C-level access method API.

---

## 1. Big Picture of Extensibility

### 1.1. What Question Does a Data Type Answer?

A type defines the set of valid values and how PostgreSQL represents a value. For example:

- **integer, numeric, text, timestamp** are built-in types.
- **enum** represents a finite set of labels.
- **composite** groups multiple fields into a structured value.
- **range** represents an interval with lower/upper bounds.
- **domain** applies constraints and a business domain name over an existing type.
- A custom base type can define its own storage representation and I/O functions.

The type governs type checking, casting, storage layout, input/output, equality semantics, and permissible operations.

### 1.2. What Question Does an Operator Answer?

An operator provides syntax such as **=**, **<**, **@>**, **&&**, **||**, or **<->**. An operator is associated with:

- An operator name.
- Left and right argument data types.
- An underlying function implementing the operation.
- Attributes such as commutator, negator, restriction/join selectivity estimators, and hash/merge capabilities.

An operator does not build an index by itself. It only defines expression semantics; an index can support that operator if the access method has a matching operator class.

### 1.3. What Question Does an Operator Class Answer?

An operator class (opclass) is the contract between an index access method and a data type. It tells the access method:

- Which operator strategies can be supported by the index.
- Which support functions perform comparisons, consistency checks, distance calculations, key extraction, or structural operations.
- How to handle values of that type when building and querying the index.

A single type can have multiple operator classes for the same access method, depending on semantics and workload.

### 1.4. What Question Does an Operator Family Answer?

An operator family (opfamily) groups related operator classes along with associated operators and support functions. It allows an access method to understand operations across multiple types—for instance, comparing `integer` with `bigint`—when semantics are consistently defined.

An opclass is the interface chosen when creating an index; an opfamily is the broader group the planner/access method uses to reason about cross-type relationships.

### 1.5. What Question Does an Access Method Answer?

An access method (AM) is the algorithm and physical mechanism used to build, store, search, and update an index or table. PostgreSQL includes several index access methods:

| Access method | Structure/concept | Typical workload |
|---|---|---|
| B-tree | Balanced tree, ordered keys | Equality, range, sort, min/max |
| Hash | Hash buckets | Equality |
| GiST | Balanced search tree with generalized predicates | Spatial, ranges, nearest-neighbor depending on opclass |
| SP-GiST | Space-partitioned search tree | Trie, radix tree, partitioned spatial data |
| GIN | Inverted index over item components | Arrays, JSONB, full-text, trigrams |
| BRIN | Summaries over block ranges | Large tables correlated with physical order |

An access method does not inherently define semantics for every type. The operator class bridges a type's semantics to the access method's algorithm.

### 1.6. Two Classes of Access Methods

PostgreSQL has **index access methods** and **table access methods**. Index AMs serve `CREATE INDEX ... USING`; table AMs govern how heap/tables store and access rows. The two APIs are distinct and registered with `CREATE ACCESS METHOD` using the corresponding type.

In most SQL applications, you use built-in index AMs or ones provided by extensions. Writing a new AM is C-level work requiring deep understanding of storage, concurrency, WAL, vacuum, and recovery.

---

## 2. Extensible Data Types in PostgreSQL

### 2.1. Pick the Right Type Kind Before Writing C

Not every requirement calls for a custom base type. Prefer built-in types and SQL-level types whenever they accurately model the domain:

| Need | Appropriate type |
|---|---|
| Numeric values with fixed precision | `numeric(p,s)` or integer minor units |
| Small, stable set of labels | `enum` |
| Additional constraints on an existing type | `domain` |
| A record combining multiple fields | `composite` |
| Continuous interval | `range` |
| Discontinuous multi-segment intervals | `multirange` |
| Flexible key/value structure | `jsonb` or a suitable extension |
| Completely custom representation and semantics | Custom base type |

A custom base type typically requires C functions to control representation, I/O, and efficient support functions.

### 2.2. Domain

A domain creates a business type over another type, optionally adding `NOT NULL` and `CHECK` constraints:

```sql
CREATE DOMAIN app.email_address AS text
    CHECK (VALUE = lower(VALUE))
    CHECK (position('@' IN VALUE) > 1);

CREATE TABLE app.users (
    user_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email app.email_address NOT NULL
);
```

Domains help reuse validation and clarify column semantics. A domain does not create a brand-new physical representation; it builds on its base type.

### 2.3. Enum

Enums fit small, rarely changing sets of labels:

```sql
CREATE TYPE app.order_state AS ENUM (
    'pending',
    'paid',
    'shipped',
    'cancelled'
);

CREATE TABLE app.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state app.order_state NOT NULL DEFAULT 'pending'
);
```

An enum is ordered by the declaration order of its labels. You can add labels via `ALTER TYPE ... ADD VALUE`; removing or reordering labels is not as simple as updating a row. If the state set changes frequently or carries metadata, a lookup table with a foreign key may fit better.

### 2.4. Composite Type

A composite type groups multiple fields:

```sql
CREATE TYPE app.address AS (
    street text,
    city text,
    postal_code text,
    country_code char(2)
);

CREATE TABLE app.customer_contacts (
    customer_id bigint PRIMARY KEY,
    billing_address app.address
);
```

Access fields using `(billing_address).city`. Composite types are useful for APIs and function return values; they do not replace normalized relational tables when per-field constraints, joins, and independent lifecycles are required.

### 2.5. Range and Multirange

A range type represents an interval with lower/upper bounds and inclusive/exclusive flags:

```sql
CREATE TABLE app.reservations (
    room_id bigint NOT NULL,
    during tstzrange NOT NULL,
    EXCLUDE USING gist (
        room_id WITH =,
        during WITH &&
    )
);
```

The `&&` operator checks overlap. The `@>` operator checks range/element containment. PostgreSQL provides range types such as `int4range`, `int8range`, `numrange`, `daterange`, `tsrange`, and `tstzrange`; range types are supported by appropriate GiST/SP-GiST operator classes.

Multiranges represent sets of non-contiguous intervals, useful when schedules or availability have multiple segments.

### 2.6. Custom Base Type

When a custom storage representation is needed, you can create a base type via `CREATE TYPE` with I/O functions:

- Input function converts `cstring` to an internal `Datum`.
- Output function converts `Datum` to text.
- Receive/send functions handle the binary wire protocol.
- Typmod input/output functions handle modifiers if the type supports syntax like precision.
- An analyze function can supply custom statistics to the planner.

Base type declarations can specify `INTERNALLENGTH`, `PASSEDBYVALUE`, `ALIGNMENT`, `STORAGE`, `CATEGORY`, `PREFERRED`, `COLLATABLE`, `INPUT`, `OUTPUT`, `RECEIVE`, `SEND`, and other attributes. These declarations must match the C representation exactly.

### 2.7. Shell Types and Bootstrapping

When a C I/O function must declare a return type before the type is fully defined, extensions typically create a shell type first, declare the functions, and then complete the type definition:

```sql
CREATE TYPE app.temperature;

CREATE FUNCTION app.temperature_in(cstring)
RETURNS app.temperature
AS 'MODULE_PATHNAME', 'temperature_in'
LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

CREATE FUNCTION app.temperature_out(app.temperature)
RETURNS cstring
AS 'MODULE_PATHNAME', 'temperature_out'
LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

CREATE TYPE app.temperature (
    INPUT = app.temperature_in,
    OUTPUT = app.temperature_out,
    INTERNALLENGTH = 8,
    PASSEDBYVALUE,
    ALIGNMENT = double,
    STORAGE = plain
);
```

This is an illustrative skeleton for an 8-byte representation matching how C code handles `Datum`. Never guess `INTERNALLENGTH`, `PASSEDBYVALUE`, or `ALIGNMENT`: mismatched declarations can corrupt memory accesses or on-disk data. In practice, you must implement the C functions, header declarations, and verify binary compatibility across every supported platform.

### 2.8. Input/Output and Binary Protocol

Text input/output forms the SQL/client-facing representation. Binary send/receive forms the wire protocol interface; they must use a stable format and proper network byte order per PostgreSQL conventions.

Without `receive`/`send` defined, PostgreSQL may not support binary I/O for the type in the way an application expects. Drivers may fall back to text, though you should not assume all drivers behave identically.

### 2.9. Typmod and Collation

Typmod enables modifiers such as `numeric(12,2)` or `varchar(80)`. A type whose semantics depend on collation must declare `COLLATABLE` and honor the passed collation inside comparison and index support functions.

Do not mark a type `COLLATABLE` merely because it contains text. Enable it only when ordering/equality truly depends on collation and support functions properly handle the provided collation.

### 2.10. Type Statistics

The planner needs statistics to estimate selectivity and cardinality. For custom types with unusual distributions, a custom analyze function or dedicated operator restriction/join estimators may be necessary. If the planner misestimates selectivity, even the right index may not be chosen.

---

## 3. Defining Operators

### 3.1. Operators Bind to Functions

An operator is SQL metadata invoking a function with a matching signature. The function does the actual work; the operator allows expressions to use infix/prefix operator syntax:

```sql
CREATE FUNCTION app.temperature_equal(
    app.temperature,
    app.temperature
)
RETURNS boolean
AS 'MODULE_PATHNAME', 'temperature_equal'
LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

CREATE OPERATOR app.=== (
    LEFTARG = app.temperature,
    RIGHTARG = app.temperature,
    FUNCTION = app.temperature_equal
);
```

The name `===` is purely illustrative. Choose an operator name that does not conflict with the parser or existing operators. User-defined operators cannot define arbitrary precedence; the parser applies PostgreSQL's built-in precedence rules.

### 3.2. Schema-Qualified Operators

If an operator lives in a schema outside `search_path`, invoke it with explicit schema qualification:

```sql
SELECT *
FROM app.readings
WHERE value OPERATOR(app.===) '21.5'::app.temperature;
```

In a real example, `temperature_in` is the illustrative input function, or use a literal cast matching the type.

### 3.3. Commutator

A commutator is the operator produced by swapping the two operands while preserving an equivalent result—for example, `a < b` is equivalent to `b > a`. Declaring a commutator lets the planner rewrite expressions and utilize indexes on the opposite operand when semantics permit.

### 3.4. Negator

A negator is the operator representing logical negation—for example, `=` and `<>`, `<` and `>=`. Declaring an incorrect commutator or negator causes wrong planner inferences, so declare them only when the equivalence holds across all valid values, including edge cases.

### 3.5. Restriction and Join Selectivity

An operator can specify:

- `RESTRICT`: function estimating selectivity when comparing a column to a constant/expression.
- `JOIN`: function estimating selectivity when comparing two relations.

PostgreSQL includes built-in estimators such as `eqsel`, `neqsel`, `scalarltsel`, `scalargtsel`, `eqjoinsel`, `neqjoinsel`, `scalarltjoinsel`, and `scalargtjoinsel`. Only choose an estimator matching your operator's semantics. Custom types/distributions may require custom estimators.

### 3.6. HASHES and MERGES

`HASHES` tells the planner the operator is eligible for hash joins and hash-based operations when a consistent hash function and equality semantics exist.

`MERGES` tells the planner the operator is eligible for merge joins when ordering semantics and an operator family support that requirement.

Do not set these flags just to coerce the planner into trying a plan. The hash function must return identical hashes for equal values; the comparator/operator must follow exact ordering and equality rules.

### 3.7. Strictness, Volatility, and Parallel Safety

Function attributes affect execution:

- `STRICT`: if any argument is `NULL`, the function returns `NULL` without executing its body; use only when semantically valid.
- `IMMUTABLE`: output depends solely on inputs and does not vary with time/config/session.
- `STABLE`: consistent within a single statement, though it may depend on snapshot/session.
- `VOLATILE`: may change on every call or have side effects.
- `PARALLEL SAFE`/`RESTRICTED`/`UNSAFE`: determines whether execution inside parallel workers is allowed.

Over-declaring stability/purity can allow the planner to perform unsafe transformations. Operator functions used in index expressions/opclasses require appropriate immutable semantics.

### 3.8. More Complete Operator Declaration Example

When declaring an operator up front, planner attributes can be included directly instead of the minimal version in section 3.1:

```sql
CREATE OPERATOR app.=== (
    LEFTARG = app.temperature,
    RIGHTARG = app.temperature,
    FUNCTION = app.temperature_equal,
    COMMUTATOR = OPERATOR(app.===),
    RESTRICT = eqsel,
    JOIN = eqjoinsel
);
```

This example illustrates attribute syntax; a self-commuting operator is valid only if the operation is genuinely symmetric. Operators like `<` or `>` require a distinct commutator. Never copy examples without verifying function and operator semantics.

### 3.9. NULL Semantics

SQL uses three-valued logic: comparing with `NULL` usually yields `NULL`/unknown rather than `true` or `false`. A `STRICT` function typically matches standard operators, whereas operators like `IS DISTINCT FROM` have special NULL-aware semantics and are not ordinary user-defined operators.

Test `NULL` handling alongside empty values, boundary values, NaN/infinity if the type has them, and invalid representations.

### 3.10. Operator Families and Planner Transformations

The planner can use commutators, negators, selectivity estimators, and opfamily relationships to deduce predicates, choose join strategies, or select index paths. Declaring metadata inconsistent with actual execution causes wrong query results or broken query plans.

---

## 4. Operator Classes and Operator Families

### 4.1. Why Do Indexes Need Operator Classes?

An index access method cannot inherently understand every data type and every operator. For instance, B-tree requires a total ordering; GIN requires extracting keys from values and queries; GiST requires consistency, penalty, and picksplit behavior.

An operator class supplies those rules for a specific data type.

### 4.2. Default Operator Class

Each access method can define a default opclass for a data type. When you run:

```sql
CREATE INDEX readings_value_idx
ON app.readings USING btree (value);
```

PostgreSQL chooses the default B-tree opclass for `value`'s type. If different semantics are needed or a type has multiple opclasses, specify one explicitly:

```sql
CREATE INDEX readings_value_idx
ON app.readings USING btree (value app.temperature_btree_ops);
```

### 4.3. Strategy Numbers

In B-tree, standard strategy numbers are:

| Strategy | Operator | Meaning |
|---:|---|---|
| 1 | `<` | Less than |
| 2 | `<=` | Less than or equal |
| 3 | `=` | Equal |
| 4 | `>=` | Greater than or equal |
| 5 | `>` | Greater than |

Strategy numbers differ across access methods. Never apply B-tree strategy numbers to GIN, GiST, or BRIN.

### 4.4. Support Functions

Support functions are callbacks invoked by the access method to manipulate the type and index. Their meanings and numbers depend on the AM.

For example, B-tree support function 1 is a comparator returning a negative integer, `0`, or a positive integer indicating the order of two values. B-tree also supports additional support functions for sort support, `in_range`, equal image, and further optimizations depending on version.

### 4.5. Declaring a B-Tree Operator Class

A conceptual custom B-tree opclass looks like:

```sql
CREATE OPERATOR CLASS app.temperature_btree_ops
DEFAULT FOR TYPE app.temperature USING btree AS
    OPERATOR 1 app.<  (app.temperature, app.temperature),
    OPERATOR 2 app.<= (app.temperature, app.temperature),
    OPERATOR 3 app.=== (app.temperature, app.temperature),
    OPERATOR 4 app.>= (app.temperature, app.temperature),
    OPERATOR 5 app.>  (app.temperature, app.temperature),
    FUNCTION 1 app.temperature_cmp(
        app.temperature, app.temperature
    );
```

This is an illustrative skeleton: before creating the opclass, all corresponding operators and comparator functions must be defined. The equality operator must agree with the comparator returning `0`. Operator names/schema syntax may need adjustment to match the operators declared in the extension. Never register an opclass if `<`, `=`, `>`, and the comparator do not define the same total ordering.

### 4.6. Comparator Contract

A B-tree comparator must satisfy:

- Reflexive equality: `compare(a, a) = 0`.
- Antisymmetry: `sign(compare(a, b)) = -sign(compare(b, a))`.
- Transitivity: if `a < b` and `b < c`, then `a < c`.
- Consistency: `compare(a, b) = 0` if and only if the equality operator returns `true`.
- Determinism: results never depend on session state or mutable external data.

Violating this contract can break index scans, uniqueness checks, and sort order.

### 4.7. Unique Indexes and Equality Semantics

A unique B-tree index uses opclass/equality semantics to decide whether two keys collide. If the comparator treats two values as equal while `=` returns `false` (or vice versa), behavior becomes inconsistent.

For collation-sensitive types, a collation version change can also invalidate existing index ordering; monitor collation version mismatches and reindex when required.

### 4.8. Operator Family

Create a family:

```sql
CREATE OPERATOR FAMILY app.temperature_ops USING btree;
```

An opclass can belong to this family:

```sql
CREATE OPERATOR CLASS app.temperature_btree_ops
DEFAULT FOR TYPE app.temperature USING btree
FAMILY app.temperature_ops AS
    OPERATOR 1 app.<  (app.temperature, app.temperature),
    OPERATOR 2 app.<= (app.temperature, app.temperature),
    OPERATOR 3 app.=== (app.temperature, app.temperature),
    OPERATOR 4 app.>= (app.temperature, app.temperature),
    OPERATOR 5 app.>  (app.temperature, app.temperature),
    FUNCTION 1 app.temperature_cmp(
        app.temperature, app.temperature
    );
```

A family can contain multiple opclasses across multiple types. A family is only meaningful when operators and support functions across types share compatible semantics.

### 4.9. Cross-Type Operators

A family can include operators comparing two different input types. For example, the B-tree integer family includes comparisons between `integer` and `bigint` so the planner can use an index without forcing a cast that disables index usage.

Cross-type comparators and operators must agree on a single shared ordering. Never add an operator to a family merely because two types can cast between each other.

### 4.10. ALTER OPERATOR FAMILY

You can add operators/support functions to a family after creation:

```sql
ALTER OPERATOR FAMILY app.temperature_ops USING btree
    ADD OPERATOR 3 app.=== (
        app.temperature, app.temperature
    );
```

Use this only after the opclass/family design and support functions have been validated. Modifying a family affects planner and index behavior; govern it as a schema-level change.

### 4.11. Inspecting Catalogs

Useful system catalogs:

- `pg_opclass`: opclasses, access method, input type, default flag.
- `pg_opfamily`: operator families.
- `pg_am`: access methods.
- `pg_amop`: operators belonging to an opfamily and their strategy.
- `pg_amproc`: support procedures belonging to an opfamily.
- `pg_operator`: operator definitions.

Example:

```sql
SELECT
    am.amname,
    ns.nspname AS opclass_schema,
    opc.opcname,
    opc.opcintype::regtype AS input_type,
    opc.opcdefault,
    opf.opfname
FROM pg_opclass AS opc
JOIN pg_am AS am ON am.oid = opc.opcmethod
JOIN pg_namespace AS ns ON ns.oid = opc.opcnamespace
JOIN pg_opfamily AS opf ON opf.oid = opc.opcfamily
ORDER BY am.amname, ns.nspname, opc.opcname;
```

Catalog columns can evolve across major versions; this query illustrates the core relationships.

---

## 5. B-Tree and Hash Access Methods

### 5.1. B-Tree

B-tree is the default choice for most scalar types. It supports equality, range predicates, ordering, and sorting. A B-tree opclass requires consistent ordering; PostgreSQL provides default opclasses for built-in types.

Example:

```sql
CREATE INDEX events_created_at_idx
ON app.events USING btree (created_at);

SELECT *
FROM app.events
WHERE created_at >= timestamptz '2026-01-01 00:00:00+00'
  AND created_at <  timestamptz '2026-02-01 00:00:00+00'
ORDER BY created_at;
```

B-tree can satisfy `ORDER BY` when query ordering matches the opclass, collation, and direction. An index scan is not guaranteed: the planner weighs cost against sequential scans and other plans.

### 5.2. Multicolumn B-Tree

In multi-column indexes, column order is critical. A B-tree is generally most effective when equality conditions apply to leading left columns followed by a range condition on the next column:

```sql
CREATE INDEX orders_customer_created_idx
ON app.orders (customer_id, created_at DESC);

SELECT *
FROM app.orders
WHERE customer_id = 42
  AND created_at >= now() - interval '7 days'
ORDER BY created_at DESC
LIMIT 20;
```

Do not reverse column order blindly or create indexes for every permutation. Base decisions on query workload, selectivity, write overhead, and index size.

### 5.3. Sort Support and Collation

B-tree can use additional support functions to sort faster than pairwise comparisons. Text ordering also depends on collation; an index is built with a specific collation. A query using a different collation may not be able to use that index for ordering.

When a collation provider or version changes, check for collation version mismatches and run `REINDEX` as guided. Otherwise, index ordering may no longer match the active comparator.

### 5.4. Hash

Hash indexes support equality operations. The Hash access method requires a consistent hash function: two equal values must produce the same hash code. Hash collisions are normal and resolved via equality rechecks.

Example:

```sql
CREATE INDEX sessions_token_hash_idx
ON app.sessions USING hash (token);

SELECT *
FROM app.sessions
WHERE token = 'opaque-token';
```

Hash indexes do not support range scans or `ORDER BY`. B-tree is usually the more versatile option unless the workload is strictly equality-only with a specific reason to use Hash.

### 5.5. Hash Opclass Contract

A custom hash opclass requires a support function generating a hash code from a value. The function must:

- Be deterministic for the same input.
- Return the same hash for equal values.
- Never depend on mutable session state.
- Have good distribution to avoid excessive collisions.

Hash codes need not be unique. The hash index retains enough information to recheck equality when required.

### 5.6. Choosing Between B-Tree and Hash

| Question | B-tree | Hash |
|---|---|---|
| Equality | Yes | Yes |
| Range | Yes | No |
| `ORDER BY` | Yes | No |
| Prefix/range traversal | Yes | No |
| Default choice for scalars | Usually yes | Usually no |
| Custom ordering semantics | Via opclass | No ordering needed |

---

## 6. GiST — Generalized Search Tree

### 6.1. GiST Is a Framework, Not a Single Data Type

GiST is a balanced tree framework for generalized predicates. Unlike B-tree, it does not impose a total ordering. The operator class defines how keys are represented, how to test whether a subtree can hold matches, how to split pages, and how to estimate insertion penalties.

GiST fits spatial data, ranges, geometric predicates, nearest-neighbor searches, and many other types when paired with an appropriate opclass.

### 6.2. Key Support Functions

A GiST opclass may require support functions such as:

- **consistent:** checks whether an index key/subtree might satisfy a query predicate.
- **union:** computes a bounding key representing entries on a page.
- **compress/decompress:** converts between indexed and stored representations.
- **penalty:** estimates how much a bounding key expands if an entry is added.
- **picksplit:** splits entries when a page overflows.
- **same:** tests whether two keys are equivalent.
- **distance:** computes a lower-bound distance for nearest-neighbor search.
- **fetch:** reconstructs the original datum when an opclass supports index-only scans per contract.

Not every opclass requires all functions; requirements depend on capabilities and PostgreSQL version.

### 6.3. Consistent Function and False Positives

GiST commonly uses bounding keys. A bounding key can cover a larger area than the underlying object; `consistent` can report that a subtree *might* contain a match. Whenever the index cannot prove exact satisfaction, PostgreSQL rechecks the condition against the heap tuple.

Consequently, a GiST scan can yield false positives during index filtering, though it must never return incorrect final rows after recheck. `EXPLAIN` may show `Rows Removed by Index Recheck`.

### 6.4. Range and Exclusion Constraint Example

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE app.room_booking (
    booking_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id bigint NOT NULL,
    during tstzrange NOT NULL,
    EXCLUDE USING gist (
        room_id WITH =,
        during WITH &&
    )
);
```

The GiST index guarantees no two rows share the same `room_id` with overlapping time ranges. The `btree_gist` extension supplies GiST operator classes for many scalar types so equality can be combined with range overlap inside a single exclusion constraint.

### 6.5. Nearest-Neighbor

Some GiST opclasses support distance operators and `ORDER BY` distance:

```sql
SELECT place_id, location
FROM app.places
ORDER BY location <-> point(106.7, 10.8)
LIMIT 10;
```

This illustrates a type/opclass with distance support. The GiST distance function must return a valid lower bound for subtrees; if the lower bound is invalid, nearest-neighbor results can be wrong.

### 6.6. Penalty and Picksplit

`penalty` governs where a new key is inserted in the tree. `picksplit` divides entries on page overflow. Together they shape tree structure, bounding-key overlap, index size, and query cost.

A good split strategy minimizes overlap while avoiding unbalanced pages or excessive wasted space. This is one of the hardest parts of designing a new GiST opclass.

---

## 7. SP-GiST — Space-Partitioned GiST

### 7.1. Differences from GiST

SP-GiST supports space-partitioned trees such as tries, radix trees, quadtrees, and k-d trees. While GiST organizes around potentially overlapping bounding predicates, SP-GiST partitions space into disjoint regions/nodes following opclass rules.

SP-GiST excels when data has natural hierarchical or partitioned structure—such as prefix strings, IP ranges, and certain spatial datasets.

### 7.2. Support Functions

An SP-GiST opclass can define:

- **config:** describes type/storage options and leaf representations.
- **choose:** decides which node/partition receives an inserted tuple.
- **picksplit:** partitions leaf tuples into inner nodes and partitions.
- **inner_consistent:** determines which child nodes may satisfy a query.
- **leaf_consistent:** checks a leaf value against the query predicate.
- **compress:** converts input into an indexable representation.

Functions must be consistent with the partitioning rules; `inner_consistent` must never prune a branch that could contain a match.

### 7.3. Built-In Examples

PostgreSQL includes SP-GiST opclasses for several types such as `point`, `box`, `range`, and text prefix depending on version. You can create an index with:

```sql
CREATE INDEX points_location_spgist_idx
ON app.points USING spgist (location);
```

Check available opclasses on your active major version before choosing. Not every type has a default SP-GiST opclass.

### 7.4. When to Choose SP-GiST?

Choose it when access patterns match the opclass's partitioning semantics. Compare against GiST/B-tree on the same dataset and query workload. A theoretically attractive structure is not always faster on real data distributions.

---

## 8. GIN — Generalized Inverted Index

### 8.1. Inverted Index

GIN stores a mapping from key components to the heap rows containing each component. One row can contribute many keys. This fits arrays, JSONB, full-text lexemes, and trigrams.

For example, a JSONB document has many keys/values; GIN indexes those components to find documents containing a matching key or path/value.

### 8.2. GIN Support Functions

A GIN opclass defines how keys are extracted from indexed values and queries:

- **compare:** compares extracted keys within the index.
- **extractValue:** extracts keys from an indexed datum.
- **extractQuery:** extracts keys from a query operand and supplies search modes/flags.
- **consistent:** determines whether a candidate tuple may satisfy the query.
- **triConsistent:** returns `TRUE`/`FALSE`/`MAYBE` to evaluate multi-key queries efficiently.
- **comparePartial:** supports partial-match searches in opclasses that require them.

GIN may recheck because individual keys are not always sufficient to prove the entire predicate.

### 8.3. Array Operators

GIN has an opclass for arrays supporting operations such as contains, contained-by, and overlap:

```sql
CREATE INDEX products_tags_gin_idx
ON app.products USING gin (tags);

SELECT *
FROM app.products
WHERE tags @> ARRAY['database', 'postgresql'];

SELECT *
FROM app.products
WHERE tags && ARRAY['cloud', 'database'];
```

GIN helps locate rows containing matching elements. For very large arrays or frequent writes, index maintenance can become costly.

### 8.4. JSONB Opclasses

PostgreSQL offers two popular GIN opclasses for JSONB:

- **jsonb_ops:** supports wide key-existence and containment operations; indexes keys and values in a general form.
- **jsonb_path_ops:** focuses on containment and matching `jsonpath` operations; typically yields smaller indexes while supporting fewer operators.

Example:

```sql
CREATE INDEX events_payload_ops_idx
ON app.events USING gin (payload jsonb_ops);

CREATE INDEX events_payload_path_idx
ON app.events USING gin (payload jsonb_path_ops);

SELECT *
FROM app.events
WHERE payload @> '{"kind":"payment","status":"ok"}';
```

Choose the opclass matching your actual query operators. If queries use key-existence operators such as `?`, `?|`, or `?&`, verify opclass support; `jsonb_path_ops` does not replace `jsonb_ops` for all predicates.

### 8.5. Full-Text Search

GIN is commonly used for `tsvector`:

```sql
CREATE INDEX documents_search_idx
ON app.documents USING gin (search_vector);

SELECT document_id
FROM app.documents
WHERE search_vector @@ plainto_tsquery('english', 'query planning');
```

GIN speeds up lexeme lookup; ranking still runs over matching candidates. Updating a document may update many index entries.

### 8.6. Pending List and Fast Update

GIN features a fast-update mechanism using a pending list to buffer index entries before merging into the main index. This can speed up inserts in some workloads, though the pending list requires cleanup; vacuum/autovacuum and `gin_clean_pending_list` can affect latency.

Monitor GIN index size, pending-list behavior, and write latency. Never disable `fastupdate` or adjust `gin_pending_list_limit` based solely on a brief microbenchmark.

---

## 9. BRIN — Block Range Index

### 9.1. Summary by Block Ranges

BRIN stores summaries for groups of physical blocks instead of one entry per row. When a column correlates strongly with physical row order, min/max or inclusion summaries can skip most irrelevant block ranges.

BRIN is far smaller and cheaper to maintain than B-tree on some massive, append-oriented tables. It usually requires heap rechecks and may scan more candidate pages than a B-tree.

### 9.2. Append-Only Time-Series Example

```sql
CREATE INDEX measurements_time_brin_idx
ON app.measurements USING brin (measured_at);

SELECT *
FROM app.measurements
WHERE measured_at >= timestamptz '2026-03-01 00:00:00+00'
  AND measured_at <  timestamptz '2026-03-02 00:00:00+00';
```

If rows are inserted roughly in `measured_at` order, `minmax` summaries can skip many block ranges.

### 9.3. Pages Per Range

The BRIN index option `pages_per_range` controls how many heap pages are summarized per range. Smaller values create more summaries and a larger index, potentially filtering more tightly. Larger values shrink the index but can increase false positives and rechecks.

Benchmark on actual data distributions rather than relying on one default across all tables.

### 9.4. Summarization and Unsummarized Ranges

Newly appended block ranges may remain unsummarized initially. `autosummarize` or `brin_summarize_new_values` can update summaries. Check summarization status and ensure maintenance keeps pace with ingestion rates.

### 9.5. BRIN Opclass Families

PostgreSQL provides BRIN opclasses such as `minmax`, `minmax-multi`, `inclusion`, and `bloom` for supported data types. Each summary style offers different filtering power and storage trade-offs. Choose a specific opclass when the workload requires semantics beyond the default.

### 9.6. When BRIN Is Unsuitable

If data is inserted or updated randomly with low physical-order correlation, `minmax` summaries span overly wide ranges and prune very few pages. In such cases, B-tree, GIN/GiST, or partition pruning may fit better.

---

## 10. Comparing Index Access Methods

### 10.1. Quick Selection Table

| Predicate/workload | Access method to consider | What to verify |
|---|---|---|
| Equality, range, `BETWEEN`, `ORDER BY` | B-tree | Ordering and leading columns |
| Equality-only on hashable type | Hash or B-tree | Hash distribution and query mix |
| Overlap/containment/spatial | GiST or SP-GiST | Opclass and recheck behavior |
| Array/JSONB/full-text/trigram components | GIN | Supported operators, write cost |
| Range filter on physically correlated data | BRIN | Physical correlation, `pages_per_range` |
| Nearest-neighbor | GiST or extension-specific AM | Distance operator and ordering semantics |
| Approximate vector search | Extension AM such as HNSW/IVFFlat | Recall, latency, memory, build/update cost |

This is a starting guide, not a rigid rule. A type can have multiple opclasses, and an AM can support multiple operator families.

### 10.2. One Column Can Have Multiple Indexes

The same column may need different indexes for different workloads:

```sql
CREATE INDEX documents_title_btree_idx
ON app.documents USING btree (title);

CREATE INDEX documents_title_trgm_idx
ON app.documents USING gin (title gin_trgm_ops);
```

B-tree can serve equality/prefix/order; trigram GIN can serve substring/similarity. In return, each index adds disk usage, WAL volume, write latency, and vacuum overhead. Keep only indexes justified by real workloads.

### 10.3. Index Conditions and Recheck

An index AM can filter candidate rows and rely on the executor to recheck predicates on the heap. `EXPLAIN` can show `Index Cond`, `Recheck Cond`, and `Rows Removed by Index Recheck`.

Recheck is not automatically an error; it is part of the design of generalized and inverted indexes. Still, excessive rechecks can degrade efficiency.

### 10.4. How the Planner Chooses an Index

PostgreSQL uses its cost model, statistics, selectivity, correlation, table size, `random_page_cost`, `effective_cache_size`, and other factors. An opclass supporting an operator does not guarantee the planner will choose the index.

When an index is not used, check:

- Whether the query operator belongs to the opclass strategies.
- Whether operand types match or have cross-type family support.
- Whether a cast/function wraps the indexed column and blocks indexability.
- Whether collations match.
- Whether statistics are fresh.
- Whether selectivity and estimated rows look reasonable.
- Whether a sequential scan is genuinely cheaper.

---

## 11. Operator Classes from Common Extensions

### 11.1. pg_trgm

The `pg_trgm` extension provides text trigram functions/operators and GIN/GiST opclasses:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX customers_name_trgm_gin_idx
ON app.customers USING gin (name gin_trgm_ops);

SELECT customer_id, name
FROM app.customers
WHERE name ILIKE '%nguyen%';
```

A GIN trigram index fits `LIKE`/`ILIKE` substring searches and extension-supported similarity operations.

A GiST trigram opclass can support distance ordering:

```sql
CREATE INDEX customers_name_trgm_gist_idx
ON app.customers USING gist (name gist_trgm_ops);

SELECT customer_id, name, name <-> 'postgress' AS distance
FROM app.customers
ORDER BY name <-> 'postgress'
LIMIT 10;
```

GIN and GiST have distinct trade-offs: GIN typically excels at candidate filtering; GiST can support nearest-neighbor ordering by distance. Choose by query workload and benchmark on real data.

### 11.2. btree_gist

`btree_gist` provides GiST operator classes for many scalar types, letting you combine equality/order-like predicates with range/spatial conditions in a single GiST index or exclusion constraint:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE app.resource_schedule (
    resource_id bigint NOT NULL,
    reserved_at tstzrange NOT NULL,
    EXCLUDE USING gist (
        resource_id WITH =,
        reserved_at WITH &&
    )
);
```

`btree_gist` does not turn GiST into a full replacement for B-tree. Certain B-tree capabilities and performance characteristics differ; for ordinary scalar equality/range/sort, B-tree remains the natural choice.

### 11.3. Vector Extensions

Extensions such as `pgvector` provide a vector data type, distance operators, and dedicated index access methods—typically including HNSW and IVFFlat depending on extension version:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE app.items (
    item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    embedding vector(3)
);

CREATE INDEX items_embedding_hnsw_idx
ON app.items USING hnsw (embedding vector_l2_ops);

SELECT item_id
FROM app.items
ORDER BY embedding <-> '[1,2,3]'
LIMIT 10;
```

HNSW/IVFFlat are approximate nearest-neighbor indexes; recall and latency depend on index parameters, query settings, dataset size, and build strategy. The opclass defines metric semantics such as L2, inner product, or cosine distance. Ensure the query operator matches the opclass; switching metrics may require a different index.

### 11.4. jsonb_ops and jsonb_path_ops

JSONB GIN example:

```sql
CREATE INDEX api_payload_gin_idx
ON app.api_events USING gin (payload jsonb_ops);

CREATE INDEX api_payload_path_idx
ON app.api_events USING gin (payload jsonb_path_ops);
```

Before creating both, determine which query operators are actually used. Having two GIN indexes on the same column incurs heavy storage and write overhead without proportional benefit.

### 11.5. Extensions Can Add Operators Without Adding Access Methods

Not every extension installs a new AM. An extension may add only:

- New data types.
- Operators and functions.
- Operator classes for existing AMs.
- Casts, aggregates, or statistics functions.

For instance, `pg_trgm` adds type-independent functions/operators and GIN/GiST opclasses using existing AMs. `btree_gist` adds GiST opclasses for scalar types. By contrast, `pgvector` provides its own AMs alongside its opclasses.

---

## 12. Adding New Access Methods via Extensions

### 12.1. SQL DDL to Register an Access Method

PostgreSQL allows registering an access method via `CREATE ACCESS METHOD`:

```sql
CREATE FUNCTION app.my_index_handler(internal)
RETURNS index_am_handler
AS 'MODULE_PATHNAME', 'my_index_handler'
LANGUAGE C STRICT;

CREATE ACCESS METHOD app_my_index
TYPE INDEX
HANDLER app.my_index_handler;
```

The handler function is a C function returning an `IndexAmRoutine` used by the PostgreSQL backend. This is only a registration skeleton; unless the routine supplies the required callbacks and consistent semantics, the AM cannot function safely.

### 12.2. IndexAmRoutine

The handler allocates an `IndexAmRoutine` and populates the flags and callbacks supported by the AM. Depending on capabilities, the routine may need to implement:

- Build and build-empty.
- Insert and bulk delete.
- Vacuum cleanup.
- Index scan or bitmap scan.
- Cost estimation.
- Options and property validation.
- Parallel build/scan if supported.
- Backward scan, ordering, uniqueness, or included columns if corresponding capabilities are declared.

Field names and callback signatures are C APIs tied to a major version. Extensions must be built and tested against the target major version's PostgreSQL headers; never copy a routine struct from another major version without checking current source/headers.

### 12.3. An Index AM Is More Than a Search Algorithm

A production index AM must integrate cleanly with:

- MVCC and snapshot visibility.
- Concurrent inserts/deletes.
- WAL logging and crash recovery.
- Vacuum and dead index entries.
- Locking/latches and concurrent scans.
- HOT updates and heap TIDs.
- Parallel workers and maintenance memory.
- Backup/restore and replication.

Missing any piece can cause index corruption or inconsistent results after crashes or concurrency.

### 12.4. Table Access Methods

Table AMs use a separate API:

```sql
CREATE FUNCTION app.my_table_handler(internal)
RETURNS table_am_handler
AS 'MODULE_PATHNAME', 'my_table_handler'
LANGUAGE C STRICT;

CREATE ACCESS METHOD app_my_table
TYPE TABLE
HANDLER app.my_table_handler;
```

`TableAmRoutine` defines how rows are inserted, fetched, updated, deleted, scanned, vacuumed, analyzed, sized, locked, TOASTed, and more. Table AMs are not index AMs and do not use operator classes.

### 12.5. Who Should Write a Custom Access Method?

Only write a custom AM when you have a genuinely distinct storage or search structure and have already evaluated existing extensions. For many needs, creating a type/operator/opclass for existing B-tree/GiST/GIN/BRIN AMs is simpler, safer, and far easier to maintain.

### 12.6. Privileges and Security

Registering an access method and installing C shared libraries are privileged operations. C code runs inside backend processes; memory safety bugs can crash the server or corrupt data. Only install reviewed extensions built from trusted sources with verified packages/signatures per system policy.

### 12.7. SQL Operator Classes Are Still Needed for Custom AMs

Once an AM is registered, a type still needs an opclass/opfamily describing operators and support procedures for that AM. The AM handler and the opclass are two separate layers:

- The handler registers the physical algorithm and callbacks.
- The opclass defines how a type and its operators use that algorithm.

### 12.8. Version Compatibility

The Index AM API is an internal C API that can change across major versions. Build extensions for each supported PostgreSQL major version, check compiler warnings, run regression tests, and verify upgrade scripts and recovery behavior. Never declare an extension compatible merely because its SQL DDL installs.

---

## 13. Extension Packaging and Lifecycle

### 13.1. Typical Components

A C/SQL extension typically includes:

- Control file: metadata such as `default_version`, `module_pathname`, `relocatable`, `requires`, and `comment`.
- Install SQL script: creates types, functions, operators, opclasses, opfamilies, or access methods.
- Shared library: C functions/handlers/support functions.
- Upgrade scripts: alter catalog objects between extension versions.
- Regression tests: verify semantics, index results, and upgrade behavior.

### 13.2. MODULE_PATHNAME

In extension SQL scripts, `MODULE_PATHNAME` is normally substituted with the library path configured in the control file. Use stable symbol names and declare C functions with exact signatures.

### 13.3. CREATE EXTENSION

Users install the extension:

```sql
CREATE EXTENSION my_extension;
```

If an extension depends on another extension, declare `requires` in the control file so dependencies install in the right order.

### 13.4. Extension Version Upgrades

Extension changes should be packaged as versioned SQL upgrade scripts executed via `ALTER EXTENSION ... UPDATE`. Upgrades must account for catalog dependencies, function signatures, operator/opclass/family objects, and existing indexes.

If the semantics of an operator class or support function change, already-built indexes may become invalid. Extension upgrades must document when `REINDEX` is required and provide a safe migration procedure.

### 13.5. Never Change Semantics Silently

A comparator, hash, or consistent function used by an index must maintain stable semantics. If a new version alters ordering or equality, old indexes may still hold entries arranged under old semantics. Reindex before relying on new semantics.

### 13.6. Relocatable and Schemas

Extensions can be designed as relocatable or bound to a specific schema. Operators, types, and opclasses are namespaced; ensure object names and `search_path` do not introduce ambiguity. For security-sensitive extensions, restrict schema ownership and `CREATE` privileges.

---

## 14. Diagnosing Indexes and the Planner

### 14.1. Verify an Index's Access Method and Opclass

```sql
SELECT
    idx.relname AS index_name,
    am.amname AS access_method,
    opc_ns.nspname AS opclass_schema,
    opc.opcname AS operator_class,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_am AS am ON am.oid = idx.relam
JOIN LATERAL unnest(i.indclass) WITH ORDINALITY AS c(opclass_oid, ord) ON true
JOIN pg_opclass AS opc ON opc.oid = c.opclass_oid
JOIN pg_namespace AS opc_ns ON opc_ns.oid = opc.opcnamespace
ORDER BY idx.relname, c.ord;
```

This query illustrates how to inspect the AM and opclass for each indexed column; adjust for catalog changes if needed across versions.

### 14.2. EXPLAIN

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT *
FROM app.documents
WHERE title ILIKE '%postgres%';
```

Inspect:

- Scan node and index name.
- `Index Cond`/`Filter`/`Recheck Cond`.
- Estimated rows vs. actual rows.
- Shared hit/read blocks.
- `Rows Removed by Index Recheck`.
- Planning/execution time.

If a query chooses `Seq Scan`, the planner may estimate a sequential scan is cheaper; that is not necessarily an opclass bug.

### 14.3. Check Whether an Operator Belongs to an Opfamily

`pg_amop` links operator families to operators and strategies. Example:

```sql
SELECT
    am.amname,
    ns.nspname AS family_schema,
    opf.opfname,
    amop.amopstrategy,
    amop.amoppurpose,
    amop.amoplefttype::regtype AS left_type,
    amop.amoprighttype::regtype AS right_type,
    amop.amopopr::regoperator AS operator
FROM pg_amop AS amop
JOIN pg_opfamily AS opf ON opf.oid = amop.amopfamily
JOIN pg_namespace AS ns ON ns.oid = opf.opfnamespace
JOIN pg_am AS am ON am.oid = opf.opfmethod
ORDER BY am.amname, opf.opfname, amop.amopstrategy;
```

Check strategy numbers and operand types whenever a query operator fails to use an index as expected.

### 14.4. Check Support Procedures

```sql
SELECT
    am.amname,
    ns.nspname AS family_schema,
    opf.opfname,
    amproc.amprocnum,
    amproc.amproclefttype::regtype AS left_type,
    amproc.amprocrighttype::regtype AS right_type,
    amproc.amproc::regprocedure AS support_function
FROM pg_amproc AS amproc
JOIN pg_opfamily AS opf ON opf.oid = amproc.amprocfamily
JOIN pg_namespace AS ns ON ns.oid = opf.opfnamespace
JOIN pg_am AS am ON am.oid = opf.opfmethod
ORDER BY am.amname, opf.opfname, amproc.amprocnum;
```

### 14.5. Diagnostic Settings

In test environments, you can temporarily set `enable_seqscan = off` to verify whether the planner has a valid index path. This is strictly diagnostic; never use it in benchmarks or production configuration as a substitute for fixing statistics, opclasses, or queries.

### 14.6. Reindex When Semantics Change

If comparator, hash function, collation behavior, or opclass support semantics change, audit dependent indexes. Rebuild indexes via `REINDEX` on a schedule; on large production tables, consider `CONCURRENTLY` and check locks and storage.

### 14.7. Validate Results Against a Sequential Reference

For custom opclasses, compare indexed query results against forced sequential scan results in a test database. Test boundary cases, `NULL`s, duplicates, collisions, ordering, range endpoints, and concurrent modifications. An index must return the exact right rows; being fast with wrong semantics is a critical bug.

---

## 15. Designing a Custom Type and Opclass: Layer-by-Layer Example

### 15.1. Start from Domain Semantics

Suppose we need to store a temperature value and support:

- Parsing from text such as `21.5 C`.
- Equality and ordering comparisons.
- Range predicates such as less than 18 degrees.
- Sorting and unique constraints.

Before writing a custom base type, consider `numeric` plus a domain/check constraint. Build a dedicated base type only when representation, validation, operators, or performance have special requirements.

### 15.2. Define the Representation

Choose a clear representation—for example, `double precision` storing Celsius. Decide:

- Are `NaN`/infinity accepted?
- Are units normalized on input?
- Is equality bitwise or numeric?
- Must original scale/formatting be preserved?
- Is it collatable? For numeric temperatures, no.

If using `double`, define behavior for `NaN`, signed zero, and rounding. If the domain requires exact decimal arithmetic, `numeric` or fixed-point integers may fit better.

### 15.3. I/O and Validation

The input function must parse the entire valid string, reject malformed values, and check overflow/ranges—not merely parse a prefix and ignore a trailing suffix. The output function should produce a stable canonical representation.

Valid input examples:

- `21.5`
- `-10.0`
- `0`

Inputs to reject unless permitted by grammar:

- empty string
- `12abc`
- values outside domain limits
- unsupported units

### 15.4. Equality and Ordering

Implement equality and the comparator from the same semantic rule. If the type stores `double`, decide how `NaN` and signed zero compare. Never let the equality function and comparator handle edge cases under two different rules.

### 15.5. Hash Support

To support Hash indexes or hash joins, the hash function must agree with equality. For all `a, b`:

```text
a = b  =>  hash(a) = hash(b)
```

Two unequal values need not have distinct hashes. Check distribution to minimize collisions and ensure hashes do not change across upgrades without rebuilding affected indexes.

### 15.6. Register Operators

Create equality/ordering operators with appropriate functions, commutators, negators, and estimators. Operators used in a B-tree opclass must have operand types and semantics matching the comparator.

### 15.7. Register the B-Tree Opclass

Declare strategy operators 1–5 and the comparator support function. If cross-type comparisons are needed, add operators/support functions to the operator family with compatible semantics.

### 15.8. Create the Index and Verify

```sql
CREATE TABLE app.readings (
    reading_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    value app.temperature NOT NULL
);

CREATE INDEX readings_temperature_idx
ON app.readings USING btree (value app.temperature_btree_ops);

SELECT *
FROM app.readings
WHERE value OPERATOR(app.<) '18'::app.temperature;

SELECT *
FROM app.readings
ORDER BY value;
```

This is an illustrative flow; the type input function, operators, and opclass must be installed beforehand. Verify that sort and range scan outputs match a reference sort in the application or test harness.

### 15.9. Verify Uniqueness

Attempt to insert duplicate values according to semantic equality. If the type canonicalizes equivalent inputs, confirm that a unique index rejects duplicates per business rules. Test edge cases such as signed zero, `NaN`, rounding boundaries, or case folding if applicable.

### 15.10. Reindex and Upgrade

If comparator, equality, or hash behavior changes, treat it as an index semantics change. Plan a migration with `REINDEX` and check for unique violations before rolling out the new version. Never silently alter function implementations while leaving old indexes behind.

---

## 16. Practice: Choosing an Opclass for Each Query

### 16.1. Exact Text Match and Sort

Query:

```sql
SELECT customer_id
FROM app.customers
WHERE email = 'user@example.test'
ORDER BY email;
```

B-tree usually fits because both equality and ordering are needed.

### 16.2. Substring Search

Query:

```sql
SELECT customer_id, name
FROM app.customers
WHERE name ILIKE '%nguyen%';
```

Consider `pg_trgm` with GIN/GiST. A standard B-tree is ineffective for patterns with a leading wildcard.

### 16.3. JSONB Containment

Query:

```sql
SELECT event_id
FROM app.events
WHERE payload @> '{"status":"paid"}';
```

Consider GIN and select between `jsonb_ops` and `jsonb_path_ops` based on actual operators used.

### 16.4. Array Overlap

Query:

```sql
SELECT product_id
FROM app.products
WHERE tags && ARRAY['sale', 'featured'];
```

The GIN array opclass is usually the starting point.

### 16.5. Range Overlap

Query:

```sql
SELECT booking_id
FROM app.room_booking
WHERE during && tstzrange(now(), now() + interval '1 hour');
```

A GiST range opclass usually fits well.

### 16.6. Time-Series Range Scan

Query:

```sql
SELECT count(*)
FROM app.measurements
WHERE measured_at >= now() - interval '1 day';
```

If data is appended chronologically with high physical-order correlation, test BRIN; if highly selective point/range lookups and sorting are needed, B-tree is also worth considering.

### 16.7. Nearest-Neighbor Vector Search

Query:

```sql
SELECT item_id
FROM app.items
ORDER BY embedding <=> '[0.1, 0.2, 0.3]'
LIMIT 20;
```

Choose the vector opclass matching cosine distance and an appropriate AM extension. Never use an L2 opclass for a query operator using a different metric.

### 16.8. Exclusion Constraint

If business rules forbid overlapping reservations for the same resource, use a GiST exclusion constraint rather than relying solely on a pre-insert check query. The constraint enforces the invariant even under concurrent transactions.

### 16.9. Measure Write Overhead

For every index, measure:

- Insert/update/delete throughput.
- WAL volume.
- Index size.
- Vacuum work.
- Locks/latency under concurrent writes.

An index that speeds up `SELECT` yet severely degrades write latency may be unsuitable for a write-heavy workload.

---

## 17. Common Design Mistakes

1. **Choosing a custom base type too early:** domain, enum, composite, or range types can often meet requirements with far less code.
2. **Non-transitive comparator:** breaks B-tree ordering validity.
3. **Equality inconsistent with comparator:** breaks unique indexes and scans.
4. **Hash inconsistent with equality:** causes hash joins and hash indexes to miss matches.
5. **Wrong `HASHES`/`MERGES` flags:** causes the planner to pick semantically invalid join algorithms.
6. **Wrong commutator/negator:** planner rewrites can alter query results.
7. **Missing or unsuitable selectivity estimators:** causes bad cardinality estimates.
8. **Wrong strategy number:** query operators fail to map to index support as expected.
9. **Using an opclass from another AM:** opclasses are not interchangeable across B-tree, GIN, GiST, SP-GiST, and BRIN.
10. **GiST `consistent` too loose or too tight:** too loose triggers excessive rechecks; too tight drops valid rows.
11. **Inconsistent GIN extract functions:** query keys fail to match keys stored at index build time.
12. **BRIN on uncorrelated columns:** summaries prune very few pages.
13. **Ignoring collation:** index ordering mismatches comparison semantics.
14. **Changing opclass functions without `REINDEX`:** existing indexes retain entries built under old semantics.
15. **Assuming extensions need only SQL scripts:** C shared libraries and version-specific builds may be mandatory.
16. **Confusing table AMs with index AMs:** they are separate APIs with distinct responsibilities.
17. **Writing a custom AM too early:** WAL, vacuum, MVCC, and recovery make the scope far larger than the search algorithm alone.
18. **Forcing index usage in production:** `enable_seqscan = off` does not fix broken index design or statistics.

---

## 18. Practice Exercises and Answers

### Exercise 1 — Distinguishing Concepts

**Question:** How do type, operator, opclass, and access method differ?

**Answer:** A type defines representation/semantics; an operator expresses an operation; an opclass connects operators/types to an AM; an AM provides the physical algorithm and index/table structure.

### Exercise 2 — Domain vs. Base Type

**Question:** An email field only needs lowercase normalization and simple format validation. Is a C custom base type needed?

**Answer:** Usually no. A domain over `text` with `CHECK` constraints is sufficient.

### Exercise 3 — Enum

**Question:** Why is an enum not ideal for a frequently changing catalog with metadata?

**Answer:** Enum labels have a constrained change lifecycle; a lookup table manages metadata and updates much more flexibly.

### Exercise 4 — Range

**Question:** What does the `&&` operator do on ranges?

**Answer:** Checks whether two ranges overlap.

### Exercise 5 — Operator Function

**Question:** Does an operator contain its implementation directly?

**Answer:** No. An operator binds to a function with a matching signature.

### Exercise 6 — Commutator

**Question:** What is the commutator of `a < b`?

**Answer:** The equivalent operator with operands swapped—normally `b > a`.

### Exercise 7 — Selectivity

**Question:** What is the `RESTRICT` estimator used for?

**Answer:** Estimating the fraction of rows matching a restriction predicate so the planner can compute costs.

### Exercise 8 — HASHES

**Question:** What is the critical requirement of a hash function?

**Answer:** Two equal values must produce the same hash value.

### Exercise 9 — B-Tree Strategies

**Question:** What is B-tree strategy 3?

**Answer:** Equality.

### Exercise 10 — B-Tree Comparator

**Question:** Is it valid if a comparator returns `0` while the equality operator returns `false`?

**Answer:** No. Ordering and equality must be consistent.

### Exercise 11 — Operator Family

**Question:** Why are operator families needed?

**Answer:** To group related opclasses, operators, and support functions, including cross-type comparisons that share consistent semantics.

### Exercise 12 — GiST

**Question:** What does the GiST `consistent` function do?

**Answer:** Checks whether an index key/subtree can potentially contain matches for a query predicate.

### Exercise 13 — GIN

**Question:** What kinds of data fit GIN?

**Answer:** Multi-component values such as arrays, JSONB, `tsvector`, and trigrams.

### Exercise 14 — BRIN

**Question:** What data condition makes BRIN `minmax` effective?

**Answer:** High correlation between the column values and physical row order so min/max summaries prune block ranges.

### Exercise 15 — SP-GiST

**Question:** How does SP-GiST differ conceptually from GiST?

**Answer:** SP-GiST partitions space into disjoint nodes/regions; GiST typically uses generalized bounding predicates that may overlap.

### Exercise 16 — pg_trgm

**Question:** Which AMs does `pg_trgm` provide opclasses for?

**Answer:** GIN and GiST.

### Exercise 17 — btree_gist

**Question:** Does `btree_gist` replace B-tree for all workloads?

**Answer:** No. It provides GiST opclasses for scalar types, useful when combining scalar equality with predicates such as range overlap.

### Exercise 18 — Custom AM

**Question:** What routine does an index access method handler return?

**Answer:** `IndexAmRoutine`.

### Exercise 19 — Table AM

**Question:** Do table AMs use operator classes?

**Answer:** No. Table AM and index AM are two distinct APIs.

### Exercise 20 — Reindex

**Question:** Why is `REINDEX` required if comparator semantics change?

**Answer:** Existing index entries were ordered under the old semantics and may violate the new comparator.

### Exercise 21 — Planner

**Question:** If an opclass supports an operator, is the planner guaranteed to pick the index?

**Answer:** No. The planner still compares costs and statistics.

### Exercise 22 — JSONB

**Question:** Are `jsonb_ops` and `jsonb_path_ops` identical?

**Answer:** No. They support different sets of operators and have different storage/query trade-offs.

### Exercise 23 — Vector

**Question:** Why must the query distance operator match the vector opclass?

**Answer:** The opclass defines the metric/search semantics supported by the index; another metric requires a matching opclass.

### Exercise 24 — Extension Lifecycle

**Question:** What actions may be needed if an extension changes a comparator or opclass support function?

**Answer:** A migration script and `REINDEX` so indexes are rebuilt under the new semantics.

---

## 19. Checklist and Summary

### When Designing a Type/Operator

1. Define semantics and representation before writing code.
2. Prefer built-in/domain/enum/composite/range types if they satisfy requirements.
3. Define text I/O and binary protocol behavior clearly.
4. Handle `NULL`, boundary values, `NaN`, and collation per contract.
5. Keep equality, comparator, and hash semantics consistent.
6. Declare commutators/negators/estimators only when strictly valid.

### When Designing an Opclass/Opfamily

7. Select the right access method for the workload.
8. Specify strategy operators and operand types explicitly.
9. Implement support functions strictly per the AM contract.
10. Ensure comparators are transitive and deterministic.
11. Ensure hash values agree with equality.
12. Use opfamilies for cross-type operations only when shared semantics hold.
13. Mark `HASHES`/`MERGES` only when genuinely supported.
14. Verify catalog entries and planner paths.

### When Deploying Extensions/Access Methods

15. Keep index AMs and table AMs separate.
16. Use version-specific PostgreSQL headers and APIs.
17. Verify MVCC, WAL, vacuum, locking, and crash recovery.
18. Package control/install/upgrade scripts and shared libraries cleanly.
19. Test `CREATE INDEX`, `INSERT`/`UPDATE`/`DELETE`, `REINDEX`, and concurrent workloads.
20. Test upgrades and restores, and document when `REINDEX` is mandatory.

### When Operating

21. Use `EXPLAIN (ANALYZE, BUFFERS)` to inspect index paths and rechecks.
22. Monitor index size, write overhead, vacuum activity, and bloat.
23. Never force index usage in production as a fix.
24. Keep semantics stable or provide explicit migration/reindexing steps on change.

PostgreSQL extensibility works through clean separation of contracts. A type defines the data; an operator defines the operation; an opclass/family tells an index AM how to accelerate the operation; and an access method provides the physical structure and algorithm. When these contracts align, PostgreSQL's planner, indexes, and executor work seamlessly with new types and extensions just as they do with built-in components.

**Self-check question:** You have a custom type with an equality operator and a comparator. To create a B-tree index, is declaring the operator enough? No. You need a B-tree operator class with the proper strategy operators and a consistent support comparator; the planner also needs appropriate statistics/selectivity to choose the index.

### Official PostgreSQL Documentation

- [Extensibility Overview](https://www.postgresql.org/docs/current/extend.html).
- [User-Defined Types](https://www.postgresql.org/docs/current/xtypes.html).
- [User-Defined Operators](https://www.postgresql.org/docs/current/xoper.html).
- [Operator Classes and Operator Families](https://www.postgresql.org/docs/current/xindex.html).
- [Index Access Method Interface](https://www.postgresql.org/docs/current/indexam.html).
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html).
- [CREATE OPERATOR](https://www.postgresql.org/docs/current/sql-createoperator.html).
- [CREATE OPERATOR CLASS](https://www.postgresql.org/docs/current/sql-createopclass.html).
- [CREATE ACCESS METHOD](https://www.postgresql.org/docs/current/sql-createaccessmethod.html).
- [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html).
- [btree_gist](https://www.postgresql.org/docs/current/btree-gist.html).
- [Table Access Method Interface](https://www.postgresql.org/docs/current/tableam.html).
