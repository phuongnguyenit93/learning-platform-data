# GiST, SP-GiST, and Appropriate Data Types in PostgreSQL

## 1. When B-tree Is No Longer Enough to Answer the Question

In most applications, B-tree indexes excel at equality lookups, ordered comparisons, and sorting scalar values. Yet many problems do not ask “what does the value equal?”:

- Which points lie inside a **rectangle** on a map?
- Which objects are **closest to a given coordinate**?
- Which booking time intervals **overlap** with a requested interval?
- Which IP address ranges **contain or belong to** a subnet?
- Which strings are **similar** to a misspelled search term?
- Which documents satisfy a **full-text search query**?

PostgreSQL provides extensible **index access methods**; among them, **GiST** and **SP-GiST** are essential tools when data types or query operators involve spatial, partitioned, containment, or overlap relationships.

The crucial point: **not the data type alone, but the combination of _data type + operator + operator class + query pattern_ determines whether an index can help**.

### Learning Objectives

After this lesson, you will be able to:

1. Explain GiST (*Generalized Search Tree*) and SP-GiST (*Space-Partitioned GiST*) conceptually.
2. Distinguish tree structures using bounding regions/summary keys from space-partitioned trees such as quadtrees, k-d trees, and radix trees.
3. Select suitable index methods for `point`, `box`, `polygon`, `circle`, `range`, `inet/cidr`, and `text` according to operator class.
4. Write queries for **point containment**, **overlap**, **range containment**, **subnet membership**, and **KNN (k-nearest neighbors)**.
5. Know when you need `pg_trgm`, `btree_gist`, or `PostGIS`.
6. Understand **lossy indexes**, `Recheck Cond`, `Rows Removed by Index Recheck`, and index-only scan limitations.
7. Read `EXPLAIN (ANALYZE, BUFFERS)`, compare index sizes, and evaluate write overhead.
8. Recognize counterexamples: B-tree is usually better for equality, GIN often wins for JSONB/arrays/full-text, and SP-GiST is not a default upgrade over GiST.
9. Run reproducible SQL experiments and solve hands-on exercises.

> **Scope:** core syntax targets modern PostgreSQL; some operator classes and extensions vary by version and configuration. Only create data and indexes in a practice database where you have permissions. In production, building large indexes must account for locks, I/O, WAL, disk space, and replication.

---

## 2. Distinguishing Access Method, Operator Class, and Operator

An index creation statement:

~~~sql
CREATE INDEX idx_places_location_gist
ON index_lab.places
USING gist (location);
~~~

encodes several decisions:

| Component | In the Example | Role |
|---|---|---|
| Relation | `index_lab.places` | Where the table data lives |
| Column | `location` | Value being indexed |
| Access method | `USING gist` | Index tree structure and search mechanism |
| Operator class | Default for `point` when available | Defines which operators/strategies are supported |
| Query | `location <@ box ...`, `ORDER BY location <-> point ...` | Must use an operator supported by the opclass for the index to apply |

Switching `USING gist` to `USING spgist` **does not guarantee all the same operators remain supported**. A single `point` type can have multiple SP-GiST operator classes; `text` with SP-GiST does not automatically enable trigram fuzzy search.

### 2.1. An Access Method Does Not Accelerate Every WHERE Clause

For example, PostgreSQL chooses `btree` by default when `USING` is omitted:

~~~sql
CREATE INDEX idx_customer_id
ON some_schema.orders (customer_id);
~~~

B-tree fits `customer_id = 123`, `customer_id BETWEEN 100 AND 200`, and ordered sorting. Switching this integer column to GiST or SP-GiST makes no sense when queries only run ordinary equality/range predicates.

### 2.2. The Operator Class Acts as a Contract Between Operator and Index

Suppose a query filters with:

~~~sql
WHERE active_period && daterange(
    DATE '2026-04-10', DATE '2026-04-12', '[)'
)
~~~

The `&&` operator expresses **whether two ranges overlap**. A GiST or SP-GiST range operator class can index this operator. By contrast, a B-tree on `active_period` does not provide a native strategy to locate all overlapping intervals the way a range index does.

### 2.3. Inspecting Support in the Current Database

~~~sql
SELECT
    am.amname AS index_method,
    opc.opcname AS operator_class,
    opc.opcintype::regtype AS indexed_type,
    opc.opcdefault AS is_default
FROM pg_opclass AS opc
JOIN pg_am AS am ON am.oid = opc.opcmethod
WHERE am.amname IN ('gist', 'spgist')
ORDER BY am.amname, opc.opcname, indexed_type::text;
~~~

Results depend on your PostgreSQL version and installed extensions. Never “guess” an opclass named `xyz_ops` exists purely from a type name.

To inspect operators published by each operator family:

~~~sql
SELECT
    am.amname AS access_method,
    opc.opcname AS operator_class,
    a.amopstrategy AS strategy_number,
    a.amopopr::regoperator AS indexable_operator
FROM pg_opclass AS opc
JOIN pg_am AS am
  ON am.oid = opc.opcmethod
JOIN pg_amop AS a
  ON a.amopfamily = opc.opcfamily
WHERE am.amname IN ('gist', 'spgist')
  AND opc.opcname IN ('point_ops', 'quad_point_ops',
                      'kd_point_ops', 'range_ops')
ORDER BY access_method, operator_class, strategy_number;
~~~

`pg_amop` catalogs **operator families**, so results may include operators across related input types in the same family. Verify exact syntax and semantics for your argument types in the documentation and `pg_operator`.

---

## 3. GiST: Generalized Search Tree

### 3.1. The Idea Behind GiST

GiST is an **extensible, balanced search tree framework**. It is neither a point-only algorithm nor a fixed B-tree variant; the tree framework pairs with an operator class to express search strategies tailored to the data type.

For geometric objects, a helpful mental model is that **internal nodes store bounding regions** enclosing all child objects:

~~~text
                   [Overall Bounding Box]
                       /            \
              [Bounding Box A]  [Bounding Box B]
                 /     \            /     \
             objects ...        objects ...
~~~

When asking “which objects intersect shape H?”, any bounding box guaranteed not to intersect H allows **pruning that entire subtree**.

However, GiST is not limited to bounding rectangles for every type. Operator classes can implement arbitrary summary models, including intervals, text signatures, and extension-defined structures.

### 3.2. Role of Support Functions

At the operator-class implementation level, GiST relies on support functions such as:

| Function Group | General Role |
|---|---|
| `consistent` | Determines whether an index entry may contain results matching the query operator |
| `union` | Computes a summary key covering a set of entries |
| `penalty` | Estimates the cost of expanding a subtree when inserting a new entry |
| `picksplit` | Splits entries when an index page overflows |
| `same` | Tests whether two summary keys are equal |
| `compress` / `decompress` | Optionally converts stored representations per opclass |
| `distance` | Supports distance ordering / KNN when provided by the opclass |

SQL users **do not write support functions themselves** to use built-in operator classes. These hooks explain why a single GiST access method supports such diverse data types.

### 3.3. What Kinds of Questions Fit GiST Especially Well?

- 2D geometry: points, boxes, polygons, circles, overlap/containment predicates.
- Time and numeric ranges: overlap, containment, adjacency.
- k-nearest-neighbor (KNN) searches via opclass-supported distance operators.
- Text similarity/trigrams when `pg_trgm` is installed.
- Full-text search with `tsvector_ops` for certain strategies.
- Multi-column indexes backing **exclusion constraints**, including scalar columns via `btree_gist`.

### 3.4. GiST Indexes Can Be Lossy

Suppose an index stores a bounding box larger than an irregular polygon. A bounding box intersecting the query region means the underlying shape **might** intersect; the actual polygon might miss.

PostgreSQL performs a **heap recheck** when the opclass reports that index keys are approximate. Never think of this as GiST returning “wrong rows”; the index yields **candidates**, and the executor verifies the exact predicate before returning SQL results.

~~~text
GiST: filter candidates via summary keys
                  |
                  v
             Heap recheck
                  |
                  v
       Exact predicate results
~~~

Whether a scan is lossy depends on the operator class, operator, and data; **not every GiST scan requires the same amount of rechecking**.

---

## 4. SP-GiST: Space-Partitioned GiST

### 4.1. Space-Partitioning Concept

SP-GiST provides an on-disk framework for **space-partitioned trees**, typically taking forms like:

- **Quadtree**: divides 2D space into quadrants.
- **k-d tree**: splits space along alternating dimensions.
- **Radix tree / trie**: branches by character or bit prefixes.
- Other partitioning structures defined by specific operator classes.

~~~text
                      [2D Space]
                      /  |  |  \
                    NW  NE  SW  SE
                    |          /  \
                [point]      ... [point]
~~~

Space is partitioned recursively by opclass rules; a query can **descend only into matching branches** rather than scanning all points.

### 4.2. “SP-GiST” Does Not Mean “Faster GiST”

GiST generally relies on **overlapping bounding summaries** and balanced trees. SP-GiST relies on **non-overlapping space partitions**, does not enforce GiST-style tree balance, and uses its own on-disk page layout.

SP-GiST can excel on certain data distributions, especially where partitioning cleanly prunes branches. Yet it can also:

- Lack an operator class for your desired data type.
- Support a different operator set from GiST.
- Have different storage footprint or insert costs.
- Perform worse than GiST when objects overlap heavily or clash with the split strategy.
- Perform worse than B-tree for plain equality or sorting.

**Decide with `EXPLAIN` and real-workload benchmarks**, never from the algorithm name.

### 4.3. Default and Optional Point Operator Classes

For the `point` type, PostgreSQL provides:

- `quad_point_ops` — default SP-GiST operator class for `point`.
- `kd_point_ops` — k-d tree partitioning strategy.

Both opclasses support the same core `point` operators in modern PostgreSQL, including `<@ (point, box)` and `<-> (point, point)` for nearest-neighbor search.

Example:

~~~sql
CREATE INDEX idx_points_quad
ON index_lab.places USING spgist (location quad_point_ops);

CREATE INDEX idx_points_kd
ON index_lab.places USING spgist (location kd_point_ops);
~~~

These are **two alternative test indexes** for comparison; production rarely needs both for the same workload without clear measured benefit.

### 4.4. SP-GiST Can Also Require Rechecks

SP-GiST does not guarantee every operator class is exact with zero rechecks. Leaf entries can hold exact or summarized representations; the executor rechecks whenever required. Therefore **never claim “SP-GiST is never lossy.”**

---

## 5. Practical Comparison: GiST vs. SP-GiST

| Criterion | GiST | SP-GiST |
|---|---|---|
| Framework | Generalized Search Tree | Space-Partitioned GiST |
| Intuition | Balanced tree of summary/bounding keys; branches may overlap | Tree partitioning space/prefixes into disjoint branches |
| Structure | Balanced tree framework | Non-balanced partitioned tree framework |
| Geometry | `point`, `box`, `polygon`, `circle` via opclasses | `point`, `box`, `polygon` via built-in opclasses |
| Ranges | `range_ops` | `range_ops` |
| Multiranges | `multirange_ops` in modern PostgreSQL | Do not assume an equivalent multirange opclass by default |
| Network addresses | `inet_ops` via explicit opclass | `inet_ops` |
| Text | Opclasses for full-text `tsvector` and `pg_trgm` | `text_ops` for compatible text/prefix operators |
| KNN | Supported on opclasses providing distance ordering | Supported on some opclasses, such as `point` |
| Exclusion constraints | Common; supports scalar combinations via `btree_gist` | Depends on opclass operator support; GiST is standard in examples |
| Extensibility | GiST support functions | SP-GiST partitioning support functions |
| “Fastest” | Cannot be assumed upfront | Cannot be assumed upfront |

**Note:** Core PostgreSQL GiST supports `circle_ops` and `tsvector_ops`, so do not assume you can blindly migrate all of those to SP-GiST. Actual support depends on operator classes and PostgreSQL version.

---

## 6. Data Types and Operators: Orientation Table

| Data Type / Problem | Example Predicate | Candidate Index | Notes |
|---|---|---|---|
| `point` inside `box` | `location <@ box ...` | GiST, SP-GiST point opclasses | Planar 2D region search |
| `point` nearest neighbors | `ORDER BY location <-> point ... LIMIT 10` | GiST, SP-GiST `point` | Requires distance-ordering opclass |
| `box`, `polygon` intersection | `area && query_area` | GiST, SP-GiST by type | May involve lossy rechecks |
| `circle` | Overlap/containment with supported operators | Core GiST | Do not assume SP-GiST circle support |
| `daterange` / `tsrange` / `tstzrange` | `period && requested_period` | GiST, SP-GiST `range` | Watch `[)` bounds, empty, infinity |
| `int4range` / `numrange` | `range_col @> element` | GiST, SP-GiST `range` | B-tree sort order does not replace overlap |
| `multirange` | `periods && query_range` | GiST `multirange_ops` | Verify version support |
| `inet` / `cidr` | `address <<= network` | SP-GiST `inet_ops` or GiST `inet_ops` | GiST `inet_ops` must be specified explicitly |
| `text` prefix | `name ^@ 'pre'` | SP-GiST `text_ops` | Not equivalent to `ILIKE` or fuzzy search |
| `text` fuzzy / trigram | `name % 'search'` or `LIKE '%term%'` | GiST `gist_trgm_ops`, GIN `gin_trgm_ops` | Requires `pg_trgm` extension |
| `tsvector` full-text | `search_vector @@ tsquery` | GiST `tsvector_ops` or GIN | GIN is often benchmarked first for FTS |
| PostGIS `geometry` | `ST_Intersects` / `ST_DWithin` | PostGIS GiST opclasses (and SP-GiST where supported) | Extension type, distinct from built-in `point` |

An index supports **specific operators**, not arbitrary function calls. Mismatched syntax, incompatible casts/collations, or predicates not using the opclass's operators can prevent index usage.

---

## 7. Lab Setup: Building the Places Dataset

Create an isolated schema. Point values here represent **2D planar coordinates**, not real-world latitude/longitude:

~~~sql
CREATE SCHEMA IF NOT EXISTS index_lab;

CREATE TABLE index_lab.places (
    place_id BIGINT PRIMARY KEY,
    place_name TEXT NOT NULL,
    location POINT NOT NULL,
    category TEXT NOT NULL
);

INSERT INTO index_lab.places
    (place_id, place_name, location, category)
VALUES
    (1, 'Cafe A',  point '(1,1)',  'cafe'),
    (2, 'Cafe B',  point '(2,3)',  'cafe'),
    (3, 'Park C',  point '(4,4)',  'park'),
    (4, 'Shop D',  point '(8,2)',  'shop'),
    (5, 'Office E',point '(11,8)', 'office'),
    (6, 'Park F',  point '(3,7)',  'park'),
    (7, 'Cafe G',  point '(6,6)',  'cafe'),
    (8, 'Shop H',  point '(-2,3)', 'shop'),
    (9, 'Office I',point '(0,-1)', 'office'),
    (10,'Park J',  point '(9,9)',  'park');

SELECT
    place_id, place_name, location, category
FROM index_lab.places
ORDER BY place_id;
~~~

> Only `INSERT` once into an empty lab table. If the table already exists with data, use a new lab schema/database or clean up intentionally; never run `DROP TABLE CASCADE` on tables you do not own.

### 7.1. Basic Distance Math

Euclidean distance between points A and B:

\[
d(A,B)=\sqrt{(x_A-x_B)^2+(y_A-y_B)^2}
\]

In PostgreSQL, `<->` on `point` computes planar Euclidean distance:

~~~sql
SELECT
    place_id,
    place_name,
    location,
    location <-> point '(2,2)' AS distance_to_target
FROM index_lab.places
ORDER BY distance_to_target, place_id;
~~~

For real Earth latitude/longitude coordinates, **never** rely on Euclidean distance over raw degrees; use an appropriate coordinate reference system and usually PostGIS `geography`/`geometry` in a suitable CRS.

### 7.2. Querying Points Inside a Box

~~~sql
SELECT
    place_id, place_name, location
FROM index_lab.places
WHERE location <@ box '((0,0),(5,5))'
ORDER BY place_id;
~~~

The `<@` operator in a `(point, box)` context means **point contained in box**. This query returns points with x in `[0, 5]` and y in `[0, 5]`.

Check operand type order carefully: `point <@ box` differs from “box contains polygon” or “range contains timestamp.” **One operator symbol can be overloaded across types.**

---

## 8. GiST on point

### 8.1. Creating the Index

~~~sql
CREATE INDEX idx_places_location_gist
ON index_lab.places
USING gist (location);
~~~

For `point`, GiST includes built-in `point_ops` supporting spatial and containment operators in that operator class.

### 8.2. Using with a Region Predicate

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT place_id, place_name, location
FROM index_lab.places
WHERE location <@ box '((0,0),(5,5))';
~~~

On a sufficiently large table with selective predicates, the planner can use an index or bitmap scan. On a 10-row table, `Seq Scan` is cheaper—that does not mean GiST is broken.

### 8.3. KNN with Direct ORDER BY

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    place_id, place_name, location,
    location <-> point '(2,2)' AS distance
FROM index_lab.places
ORDER BY location <-> point '(2,2)'
LIMIT 5;
~~~

When the optimizer selects a GiST nearest-neighbor plan, it can look like:

~~~text
Index Scan using idx_places_location_gist ...
  Order By: (location <-> '(2,2)'::point)
~~~

This snippet is **illustrative only**, not guaranteed output. To make tie ordering deterministic when two points are equidistant, you can add `place_id` as a secondary sort key, though inspect the plan because that may add an extra sort node.

### 8.4. Why Isn't ORDER BY Distance Always a KNN Index Scan?

~~~sql
SELECT ...
FROM index_lab.places
ORDER BY location <-> point '(2,2)'
LIMIT 5;
~~~

This can exploit a distance-ordering operator class. However:

- `ORDER BY sqrt(pow(...))` is not the opclass operator expression required for planner KNN recognition.
- Parameters inside expressions not treated as pseudoconstants can block index ordering.
- Tiny datasets or large `LIMIT`s make full scan + sort cheaper.
- The index's operator class must support `<->` for the exact types.
- Additional filters and joins can shift the optimal access path.

Good practice is to **read `EXPLAIN`**, rather than seeing `<->` in SQL and assuming an index scan will run.

---

## 9. SP-GiST on point: Quadtree and k-d Tree

### 9.1. Default SP-GiST for point

~~~sql
CREATE INDEX idx_places_location_spgist_quad
ON index_lab.places
USING spgist (location);
~~~

In modern PostgreSQL, `quad_point_ops` is the default SP-GiST operator class for `point`.

Explicit equivalent:

~~~sql
CREATE INDEX idx_places_location_spgist_quad_explicit
ON index_lab.places
USING spgist (location quad_point_ops);
~~~

**Do not keep two identical quad indexes** on the same column; both statements are shown to illustrate syntax. If you already created one quad index, treat the other as a syntax example only.

### 9.2. A k-d Tree Variant

~~~sql
CREATE INDEX idx_places_location_spgist_kd
ON index_lab.places
USING spgist (location kd_point_ops);
~~~

These two SP-GiST `point` opclasses are candidates to compare based on:

- Coordinate distribution.
- Clustering and duplicate coordinate rate.
- Region selectivity.
- Insert and update frequency.
- KNN and bounding-box query latency.
- Index size and buffer reads.

Never claim `kd_point_ops` always beats `quad_point_ops` or vice versa.

### 9.3. Region Queries and KNN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT place_id, place_name
FROM index_lab.places
WHERE location <@ box '((0,0),(5,5))';
~~~

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT place_id, place_name
FROM index_lab.places
ORDER BY location <-> point '(2,2)'
LIMIT 3;
~~~

Both GiST `point` and SP-GiST `quad_point_ops`/`kd_point_ops` support these queries, yet **the planner selects one index or `Seq Scan` by cost**. When multiple indexes can serve the same query, creating SP-GiST does not mean you are benchmarking SP-GiST—read `Index Scan using ...` in the plan.

### 9.4. Test Without Forcing Production

In a lab, populate a large enough dataset, run `ANALYZE`, and compare index setups **in an isolated environment**. Never set `enable_seqscan = off` in production to force GiST/SP-GiST; that distorts planner decisions. If used briefly in a lab transaction to inspect plan structure, roll back or reset immediately.

---

## 10. Box, Polygon, Circle: “Geometry” Is Not One Single Type

Core PostgreSQL provides built-in geometric types such as `point`, `box`, `polygon`, and `circle`. They are distinct from PostGIS `geometry`/`geography`.

### 10.1. GiST for box

~~~sql
CREATE TABLE index_lab.regions (
    region_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    bounds BOX NOT NULL
);

INSERT INTO index_lab.regions(region_id, name, bounds)
VALUES
    (1, 'Center', box '((0,0),(5,5))'),
    (2, 'East',   box '((4,1),(9,7))'),
    (3, 'North',  box '((1,6),(6,10))'),
    (4, 'Remote', box '((20,20),(25,25))');

CREATE INDEX idx_regions_bounds_gist
ON index_lab.regions USING gist(bounds);
~~~

Find regions overlapping a query box:

~~~sql
SELECT region_id, name, bounds
FROM index_lab.regions
WHERE bounds && box '((3,3),(7,8))'
ORDER BY region_id;
~~~

`&&` is the **overlap** operator for `(box, box)`. To understand exact boundary-touching semantics, consult the geometric type and operator documentation; do not blindly apply `[)` time-interval conventions to 2D boxes.

### 10.2. SP-GiST for box and polygon

~~~sql
CREATE INDEX idx_regions_bounds_spgist
ON index_lab.regions USING spgist(bounds);
~~~

In modern PostgreSQL, SP-GiST provides built-in `box_ops` and `poly_ops` supporting spatial operators such as `&&`, `@>`, `<@`, and distance ordering for certain type pairs.

### 10.3. Native circle

GiST provides built-in `circle_ops`. Example:

~~~sql
CREATE TABLE index_lab.coverage_areas (
    area_id INTEGER PRIMARY KEY,
    coverage CIRCLE NOT NULL
);

INSERT INTO index_lab.coverage_areas(area_id, coverage)
VALUES
    (1, circle '<(2,2),3>'),
    (2, circle '<(10,10),2>');

CREATE INDEX idx_coverage_circle_gist
ON index_lab.coverage_areas USING gist (coverage);
~~~

Here queries inspect circle relationships using operators supported by `circle_ops`. **Never assume `USING spgist(coverage)` works**, because not every GiST operator class has an SP-GiST counterpart.

### 10.4. Complex Polygons and False Positives

For non-convex shapes or complex polygons, bounding-box approximations match more candidates than truly satisfy the predicate. The executor rechecks exact geometry. When interpreting spatial queries:

- Distinguish bounding-box overlap from exact geometric intersection.
- Check the exact operator in `WHERE`.
- Inspect `Recheck Cond` and `Rows Removed by Index Recheck` in `EXPLAIN` when present.
- Never assume `&&` has identical boundary semantics across different extensions.

---

## 11. Range Types: Data Types Built for Overlap and Containment

Scheduling and booking problems should usually use **range types** rather than storing two raw timestamps without explicit interval semantics.

PostgreSQL includes built-in range types:

- `int4range`, `int8range`.
- `numrange`.
- `daterange`.
- `tsrange` for timestamps without time zone.
- `tstzrange` for `timestamptz`.

### 11.1. Common Range Operators

| Operator | Example Meaning |
|---|---|
| `a && b` | Ranges `a` and `b` **overlap** |
| `a @> b` | Range `a` **contains** element or range `b` |
| `a <@ b` | Range `a` **is contained by** range `b` |
| `a -|- b` | Ranges `a` and `b` are **adjacent** without overlapping |
| `a = b` | Ranges are equal per range semantics |
| `lower(a)` / `upper(a)` | Extracts lower/upper bound when finite |
| `isempty(a)` | Tests whether a range is empty |

### 11.2. [) Bounds and Booking Correctness

Range:

~~~sql
SELECT daterange(
    DATE '2026-04-10',
    DATE '2026-04-13',
    '[)'
) AS booking_days;
~~~

`[)` means **inclusive lower bound, exclusive upper bound**—a natural convention for hotel stays where checking out on April 13 does not occupy the night of April 13.

Example:

~~~sql
SELECT
    daterange(DATE '2026-04-10', DATE '2026-04-13', '[)')
    &&
    daterange(DATE '2026-04-13', DATE '2026-04-15', '[)')
    AS overlaps;
~~~

The result is **`false`** for these two adjacent intervals. Different bound flags or timestamp conventions yield different results; always define boundary semantics explicitly in booking rules.

### 11.3. Creating a Reservations Table

~~~sql
CREATE TABLE index_lab.reservations (
    reservation_id BIGINT PRIMARY KEY,
    room_id INTEGER NOT NULL,
    guest_name TEXT NOT NULL,
    stay DATERANGE NOT NULL,
    CHECK (NOT isempty(stay))
);

INSERT INTO index_lab.reservations
    (reservation_id, room_id, guest_name, stay)
VALUES
    (1, 101, 'Guest A',
        daterange(DATE '2026-04-01', DATE '2026-04-04', '[)')),
    (2, 101, 'Guest B',
        daterange(DATE '2026-04-05', DATE '2026-04-08', '[)')),
    (3, 102, 'Guest C',
        daterange(DATE '2026-04-02', DATE '2026-04-07', '[)')),
    (4, 102, 'Guest D',
        daterange(DATE '2026-04-09', DATE '2026-04-11', '[)'));
~~~

### 11.4. GiST Index for Ranges

~~~sql
CREATE INDEX idx_reservations_stay_gist
ON index_lab.reservations USING gist (stay);
~~~

Overlap query:

~~~sql
SELECT
    reservation_id, room_id, guest_name, stay
FROM index_lab.reservations
WHERE stay && daterange(
    DATE '2026-04-03',
    DATE '2026-04-06',
    '[)'
)
ORDER BY room_id, reservation_id;
~~~

GiST `range_ops` accelerates `&&`, `@>`, and related range operators. This query checks across all rooms; to filter **one room**, add `WHERE room_id = ...`. On large tables filtering both `room_id` and `stay`, evaluate a composite index/constraint design.

### 11.5. SP-GiST Index for Ranges

~~~sql
CREATE INDEX idx_reservations_stay_spgist
ON index_lab.reservations USING spgist (stay);
~~~

SP-GiST also includes `range_ops` for **range types** in modern PostgreSQL. Predicates like `stay && requested_range` can be backed by either method.

An SP-GiST range index does not enforce uniqueness or prevent overlapping bookings by itself; **it only accelerates queries** when the planner selects it.

### 11.6. Containment

~~~sql
SELECT reservation_id, room_id, stay
FROM index_lab.reservations
WHERE stay @> DATE '2026-04-03'
ORDER BY room_id, reservation_id;
~~~

`stay @> DATE` asks “does this reservation cover April 3?”. Both GiST and SP-GiST `range_ops` support element containment for compatible argument types.

---

## 12. Multirange: Do Not Assume SP-GiST Mirrors Range Support

A multirange represents a set of disjoint ranges over the same domain—useful for non-contiguous work schedules, tiered pricing windows, or availability slots.

In modern PostgreSQL:

~~~sql
SELECT datemultirange(
    daterange(DATE '2026-04-01', DATE '2026-04-03', '[)'),
    daterange(DATE '2026-04-07', DATE '2026-04-09', '[)')
) AS available_periods;
~~~

GiST provides built-in `multirange_ops` for compatible multirange operators. Example:

~~~sql
CREATE TABLE index_lab.availability (
    employee_id INTEGER PRIMARY KEY,
    available_days DATEMULTIRANGE NOT NULL
);

INSERT INTO index_lab.availability(employee_id, available_days)
VALUES (
    1,
    datemultirange(
        daterange(DATE '2026-04-01', DATE '2026-04-03', '[)'),
        daterange(DATE '2026-04-07', DATE '2026-04-09', '[)')
    )
);

CREATE INDEX idx_availability_gist
ON index_lab.availability USING gist (available_days);
~~~

Find schedules overlapping a requested range:

~~~sql
SELECT employee_id, available_days
FROM index_lab.availability
WHERE available_days &&
      daterange(DATE '2026-04-08', DATE '2026-04-10', '[)');
~~~

**Do not infer from SP-GiST having `range_ops` that it natively indexes `datemultirange` the same way.** Check `pg_opclass` and the built-in operator class documentation for your version; without a matching opclass, `CREATE INDEX ... USING spgist (available_days)` fails.

---

## 13. IP Networks: inet, cidr, and Subnet Containment

### 13.1. Do Not Treat IP Addresses as Arbitrary Text

PostgreSQL provides `inet` and `cidr` for network hosts and prefixes. Operations like “is network A inside network B?” have specialized CIDR semantics; storing IPs as `text` and running `LIKE '10.%'` misrepresents subnet logic and breaks easily.

Common network operators:

| Operator | Network Meaning |
|---|---|
| `a << b` | `a` is **strictly contained** within subnet `b` |
| `a <<= b` | `a` is contained within or equal to subnet `b` |
| `a >> b` | `a` strictly contains `b` |
| `a >>= b` | `a` contains or equals `b` |
| `a && b` | Subnets overlap |

### 13.2. Creating an IP Lab Table

~~~sql
CREATE TABLE index_lab.network_rules (
    rule_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    network INET NOT NULL
);

INSERT INTO index_lab.network_rules(rule_id, label, network)
VALUES
    (1, 'Office subnet',  inet '10.10.0.0/16'),
    (2, 'VPN subnet',     inet '10.20.0.0/16'),
    (3, 'Office host A',  inet '10.10.2.15'),
    (4, 'Office host B',  inet '10.10.8.99'),
    (5, 'Public host',    inet '203.0.113.8'),
    (6, 'Private range',  inet '192.168.0.0/16');

SELECT rule_id, label, network
FROM index_lab.network_rules
ORDER BY rule_id;
~~~

### 13.3. SP-GiST inet_ops

~~~sql
CREATE INDEX idx_network_rules_spgist
ON index_lab.network_rules USING spgist (network inet_ops);
~~~

Find networks or hosts contained in a subnet:

~~~sql
SELECT rule_id, label, network
FROM index_lab.network_rules
WHERE network <<= inet '10.10.0.0/16'
ORDER BY rule_id;
~~~

Expected matches include the office subnet and both office hosts. `<<=` is supported by SP-GiST `inet_ops`, though a tiny table may still run `Seq Scan`.

### 13.4. GiST inet_ops Must Be Specified Explicitly

In PostgreSQL's core operator classes, GiST `inet_ops` is **not the default opclass for `inet`/`cidr`**. Specify it explicitly:

~~~sql
CREATE INDEX idx_network_rules_gist
ON index_lab.network_rules USING gist (network inet_ops);
~~~

This illustrates a key lesson: **specifying an access method is not enough if the type has no default opclass for it**.

### 13.5. Same Data Type, Multiple Index Choices

For exact IP equality lookups, B-tree may already suffice. Consider GiST/SP-GiST when queries frequently test **subnet containment or overlap**; weigh selectivity, table size, and update rate.

Never store unvalidated address strings or build SQL via string concatenation; use prepared statements or explicit `inet` casts with proper format error handling.

---

## 14. SP-GiST on text: Prefixes and Supported Operators

### 14.1. SP-GiST text_ops Is Not a Trigram Index

SP-GiST `text_ops` supports text comparison operators in its opclass as well as the `^@` prefix operator:

~~~sql
CREATE TABLE index_lab.keywords (
    keyword_id BIGINT PRIMARY KEY,
    term TEXT NOT NULL
);

INSERT INTO index_lab.keywords(keyword_id, term)
VALUES
    (1, 'postgres'),
    (2, 'postgresql'),
    (3, 'postgis'),
    (4, 'postcard'),
    (5, 'index'),
    (6, 'instant'),
    (7, 'spgist'),
    (8, 'spatial');

CREATE INDEX idx_keywords_spgist_text
ON index_lab.keywords USING spgist (term text_ops);
~~~

Find strings starting with a prefix:

~~~sql
SELECT keyword_id, term
FROM index_lab.keywords
WHERE term ^@ 'post'
ORDER BY term;
~~~

`^@` tests “starts with” (case-sensitive per operator semantics). It is a **prefix** check, not fuzzy similarity.

### 14.2. Prefix vs. ILIKE and Substring Matching

| Predicate | Meaning | Common Candidate Opclass |
|---|---|---|
| `term ^@ 'post'` | Starts with `'post'` | SP-GiST `text_ops` |
| `term LIKE 'post%'` | Prefix pattern | B-tree with compatible pattern opclass/collation; `pg_trgm` when needed |
| `term ILIKE '%post%'` | Case-insensitive substring | `pg_trgm` GiST/GIN |
| `term % 'postgre'` | Trigram similarity (requires `pg_trgm`) | `gist_trgm_ops` or `gin_trgm_ops` |
| `term = 'postgres'` | Equality | Standard B-tree |

**Never claim** `SP-GiST text_ops` speeds up arbitrary `LIKE`, `ILIKE`, or regex queries. Only operators registered in the operator class are indexable.

### 14.3. Radix / Prefix Partitioning

For `text`, SP-GiST uses a prefix-partitioning strategy resembling a trie:

~~~text
root
 ├── "pos"
 │     ├── "tgres"
 │     ├── "tgresql"
 │     ├── "tcard"
 │     └── "tgis"
 ├── "in"
 │     ├── "dex"
 │     └── "stant"
 └── "sp"
       ├── "gist"
       └── "atial"
~~~

This diagram illustrates branching conceptually, **not exact SP-GiST on-disk page layouts**. String distribution and shared prefix lengths affect performance.

---

## 15. pg_trgm: GiST for Fuzzy String Search

### 15.1. Why Is an Extension Needed?

Core PostgreSQL GiST does not include fuzzy-string `gist_trgm_ops` automatically for `text` columns. The `pg_trgm` extension supplies trigram operators, functions, and operator classes.

In an environment where you have privileges:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
~~~

Creating extensions requires database privileges and adherence to governance policies; `pg_trgm` ships with standard PostgreSQL contrib modules, yet **not every database has it enabled**.

### 15.2. Creating a GiST Trigram Index

~~~sql
CREATE INDEX idx_keywords_gist_trgm
ON index_lab.keywords
USING gist (term gist_trgm_ops);
~~~

You can tune signature length for this opclass, for instance:

~~~sql
CREATE INDEX idx_keywords_gist_trgm_sig32
ON index_lab.keywords
USING gist (term gist_trgm_ops(siglen=32));
~~~

**These two statements are competing test variants.** Never keep both indexes in production serving the exact same workload. Longer signatures generally enlarge the index while reducing false positives and rechecks.

### 15.3. Similarity with the % Operator

~~~sql
SELECT
    keyword_id,
    term,
    similarity(term, 'postgress') AS score
FROM index_lab.keywords
WHERE term % 'postgress'
ORDER BY score DESC, term;
~~~

In `pg_trgm`, `%` checks whether similarity exceeds `pg_trgm.similarity_threshold`. Results depend on the threshold and data/language, with no fixed row count guaranteed across environments.

You can adjust the threshold **for your lab session** while testing:

~~~sql
SET pg_trgm.similarity_threshold = 0.3;
~~~

Never change the database-wide threshold in production just to “fix one query” without assessing side effects on all other trigram queries.

### 15.4. KNN by Trigram Distance: Where GiST Stands Out

`pg_trgm` defines `<->` for `(text, text)` as similarity-based distance; it is **not** Euclidean `point` distance even though it shares the same symbol.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    keyword_id,
    term,
    term <-> 'postgress' AS trigram_distance
FROM index_lab.keywords
ORDER BY term <-> 'postgress'
LIMIT 5;
~~~

GiST trigram supports **KNN distance-ordered scans** when cost-effective. Key contrast: `GIN gin_trgm_ops` handles similarity/pattern filtering very well, yet **does not support direct KNN order-by-distance scans** the way GiST trigram does.

### 15.5. LIKE '%...%' and Trigrams

~~~sql
SELECT keyword_id, term
FROM index_lab.keywords
WHERE term ILIKE '%post%';
~~~

GiST/GIN trigram indexes can accelerate substring patterns, yet if a pattern is too short or yields no useful trigrams, the scan can degrade into reading large portions of the index. Never assume `%` automatically guarantees speed.

### 15.6. GiST vs. GIN for Text

| Need | GiST Trigram | GIN Trigram |
|---|---|---|
| `LIKE`/`ILIKE`/regex with useful trigrams | Can be good | Can be good |
| Similarity filter `%` | Supported | Supported |
| Approximate top-k via `ORDER BY term <-> q LIMIT k` | **KNN advantage** | Does not use the same KNN distance scan |
| Size and update cost | Depends on `siglen` and data | Depends on inverted postings and `fastupdate` |
| “Always faster” | No | No |

GiST trigram stores approximate signatures, making **index rechecks** an important factor. GIN behaves as an inverted index and is not universally best for every pattern or write rate.

---

## 16. Full-Text Search: GiST tsvector vs. When GIN Fits Better

PostgreSQL full-text search uses `tsvector` and `tsquery`. Example setup:

~~~sql
CREATE TABLE index_lab.articles (
    article_id BIGINT PRIMARY KEY,
    body TEXT NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple', body)
    ) STORED
);

INSERT INTO index_lab.articles(article_id, body)
VALUES
    (1, 'PostgreSQL GiST indexing'),
    (2, 'SP-GiST spatial partitioning'),
    (3, 'Generalized search trees and query plans'),
    (4, 'Database transactions and isolation');

CREATE INDEX idx_articles_gist_fts
ON index_lab.articles USING gist (search_vector);
~~~

Query:

~~~sql
SELECT article_id, body
FROM index_lab.articles
WHERE search_vector @@ to_tsquery('simple', 'indexing');
~~~

Core GiST includes `tsvector_ops` for `@@`, using a signature representation that can be lossy. For many full-text search workloads, **GIN** is the common baseline to benchmark:

~~~sql
CREATE INDEX idx_articles_gin_fts
ON index_lab.articles USING gin (search_vector);
~~~

Do not treat GiST or SP-GiST as the single approach for “text search.” SP-GiST `text_ops` targets prefixes, while GiST `tsvector_ops` and GIN `tsvector_ops` target full-text lexemes—entirely different predicate models.

### 16.1. Do Not Confuse “Text Search” with “tsvector Search”

- `body ILIKE '%term%'`: raw string substring matching.
- `body % 'term'`: trigram similarity (requires `pg_trgm`).
- `search_vector @@ query`: full-text lexeme/linguistic matching.
- `body ^@ 'prefix'`: starts-with text operator.

Pick an index based on the semantics your product requires, not because all four are loosely called “search.”

---

## 17. PostGIS: geometry and geography Are Extension-Provided Types

### 17.1. Native point Is Not PostGIS geometry

Core PostgreSQL `point`/`box` implement simple planar geometry. PostGIS extends PostgreSQL with:

- `geometry`: spatial objects with SRIDs, rich shape types, and spatial operators.
- `geography`: spherical/geodetic calculations on Earth with appropriate units and semantics (per function/operator).
- PostGIS GiST (and selective SP-GiST) operator classes and strategies depending on PostGIS/PostgreSQL version.

Where authorized and installed on the server:

~~~sql
CREATE EXTENSION IF NOT EXISTS postgis;
~~~

**PostGIS is not required** for the native `point`/`range`/`inet` exercises above. If you lack permissions or PostGIS is unavailable, continue with the core lab.

### 17.2. Illustrative PostGIS Example

~~~sql
-- Run only when the postgis extension is enabled.
CREATE TABLE index_lab.geo_places (
    place_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    geom geometry(Point, 4326) NOT NULL
);

CREATE INDEX idx_geo_places_gist
ON index_lab.geo_places USING gist (geom);
~~~

Radius query example:

~~~sql
SELECT place_id, name
FROM index_lab.geo_places
WHERE ST_DWithin(
    geom,
    ST_SetSRID(ST_MakePoint(106.7, 10.8), 4326),
    0.01
);
~~~

**Critically important:** `geometry(Point, 4326)` stores longitude/latitude coordinates in **degrees**. The threshold `0.01` above is also in **degrees**, **not 10 meters or 1 km**. If you need distances in meters, use `geography` or project into an appropriate metric CRS and verify distance semantics.

### 17.3. Which Conditions Do Spatial Indexes Support?

PostGIS provides functions like `ST_Intersects`, `ST_Contains`, `ST_DWithin`, and bounding-box operators. Index eligibility depends on:

- The `geometry`/`geography` operator class.
- Whether the function implementation is index-aware.
- Matching SRIDs and coordinate transforms.
- Predicates, constant expressions, and casts.
- Data size, selectivity, and statistics.

Never write `ST_Distance(geom, query) < radius` assuming the plan matches index-assisted `ST_DWithin`. For distance filtering, prefer index-aware functions and verify via `EXPLAIN` in your environment.

### 17.4. GiST vs. SP-GiST in PostGIS

Recent PostGIS versions add SP-GiST support for certain geometric types/strategies. Still, **never assume** all PostGIS operators are identically supported by both GiST and SP-GiST.

Check installed operator classes in your database:

~~~sql
SELECT
    am.amname,
    opc.opcname,
    opc.opcintype::regtype AS data_type
FROM pg_opclass AS opc
JOIN pg_am AS am
  ON am.oid = opc.opcmethod
WHERE am.amname IN ('gist', 'spgist')
  AND opc.opcname LIKE '%geometry%'
ORDER BY am.amname, opc.opcname;
~~~

Compare real queries (spatial predicates, distance ordering, selectivity, complex geometries) before deciding.

---

## 18. btree_gist and Exclusion Constraints Against Double Booking

### 18.1. A Query Index Does Not Enforce Interval Non-Overlap

If two concurrent sessions book the same room for overlapping dates, merely having:

~~~sql
CREATE INDEX idx_reservations_stay_gist
ON index_lab.reservations USING gist (stay);
~~~

does not stop overlapping inserts. That is a **lookup index**, not an exclusion constraint.

### 18.2. EXCLUDE Using GiST

PostgreSQL provides exclusion constraints to express:

> No two rows may exist where **`room_id` is equal** and **`stay` overlaps**.

GiST fits this role well. However, integer `room_id` lacks a built-in GiST equality opclass out of the box. The `btree_gist` extension supplies B-tree-equivalent GiST operator classes for scalar types.

~~~sql
-- Requires permissions and btree_gist available on the server.
CREATE EXTENSION IF NOT EXISTS btree_gist;
~~~

Then:

~~~sql
ALTER TABLE index_lab.reservations
ADD CONSTRAINT no_overlapping_stays_for_room
EXCLUDE USING gist (
    room_id WITH =,
    stay WITH &&
);
~~~

The constraint guarantees that for **any two distinct rows**, `room_id = room_id` and `stay && stay` cannot both hold simultaneously. PostgreSQL builds a backing GiST index and coordinates concurrent transactions safely; a pre-insert `SELECT` check offers **no equivalent concurrency guarantee**.

### 18.3. Example Violation

If `reservation_id = 1` holds room 101 for `[2026-04-01, 2026-04-04)`, the statement:

~~~sql
INSERT INTO index_lab.reservations
    (reservation_id, room_id, guest_name, stay)
VALUES (
    100, 101, 'Conflicting booking',
    daterange(DATE '2026-04-02', DATE '2026-04-03', '[)')
);
~~~

is rejected while the constraint is active, because the room matches and the dates overlap. The error is an **exclusion violation** (SQLSTATE `23P01`).

### 18.4. Two Adjacent Bookings

~~~sql
INSERT INTO index_lab.reservations
    (reservation_id, room_id, guest_name, stay)
VALUES (
    101, 101, 'Adjacent booking',
    daterange(DATE '2026-04-04', DATE '2026-04-05', '[)')
);
~~~

With `[)` bounds, the new interval is adjacent to (not overlapping) reservation 1 and does not overlap any other room 101 bookings in the lab, so it succeeds **assuming all other constraints hold**.

### 18.5. Two Additional Caveats

- If `room_id` or `stay` is **`NULL`**, `NULL` comparison logic producing `UNKNOWN` can allow rows through that you expected to block. Enforce `NOT NULL` on mandatory booking attributes.
- `btree_gist` **does not build standard unique B-tree indexes**; it adapts scalar comparisons to GiST for exclusion constraints. Never replace a simple `UNIQUE` constraint with `EXCLUDE` just because `btree_gist` is installed.

---

## 19. GiST Is Not GIN, and SP-GiST Is Not BRIN

### 19.1. B-tree

Ideal for equality, ordered ranges, standard `ORDER BY`, and `UNIQUE`/`PRIMARY KEY` in most applications.

### 19.2. GIN (Generalized Inverted Index)

Typically suited for **multi-component values**:

- Arrays with overlap/containment.
- JSONB with compatible operator classes and predicates.
- Full-text search lexemes.
- Trigram inverted postings.

GiST also has useful text and spatial opclasses, yet it is not a default replacement for GIN on JSONB or arrays.

### 19.3. BRIN (Block Range Index)

Stores per-block-range summaries; effective on huge tables when physical row order **correlates** with column values (such as append-only timestamps). BRIN is tiny, though it requires more rechecks. Do not pick GiST/SP-GiST simply because a column is a timestamp; for `created_at >= ...` on append-only tables, B-tree or BRIN fits better.

### 19.4. Quick Selection Table

| Dominant Workload | First Candidate to Evaluate |
|---|---|
| `customer_id = ?` | B-tree |
| `created_at BETWEEN ...` | B-tree, or BRIN on huge physically correlated tables |
| `jsonb_col @> '{"k":...}'` | GIN JSONB opclass |
| `tags && ARRAY[...]` | GIN array opclass |
| `geometry ST_Intersects` | PostGIS GiST with appropriate opclass |
| `point <@ box` | GiST or SP-GiST `point` |
| `point ORDER BY point <-> q LIMIT 10` | GiST/SP-GiST `point` KNN |
| `daterange && daterange` | GiST/SP-GiST `range` |
| `inet <<= subnet` | SP-GiST/GiST `inet_ops` |
| `text ^@ prefix` | SP-GiST `text_ops`; compare against B-tree prefix strategies |
| `text ILIKE '%keyword%'` | `pg_trgm` GiST/GIN |
| `text ORDER BY text <-> q LIMIT 10` | GiST `pg_trgm` KNN |
| `tsvector @@ tsquery` | GIN usually evaluated first; GiST also supports |

A table serving diverse workloads may need **multiple indexes for distinct predicates**, yet each index adds write, `VACUUM`, and storage overhead. Remove overlapping indexes lacking clear measured value.

---

## 20. KNN: Why ORDER BY <-> Is a Special Case

### 20.1. Top-k Instead of Filtering Everything and Sorting

A classic KNN query:

~~~sql
SELECT place_id, place_name, location
FROM index_lab.places
ORDER BY location <-> point '(2,2)'
LIMIT 5;
~~~

In a compatible plan, the index **yields candidates incrementally in distance order**, finding the top-k without computing distances and sorting the entire table.

Both GiST and SP-GiST can support KNN, yet **not every operator class** for either access method supports distance ordering.

### 20.2. Do Not Equate <-> Across Different Types

| Operator | Context | Meaning |
|---|---|---|
| `point <-> point` | Core geometry | Planar distance |
| `text <-> text` with `pg_trgm` | Trigram | Similarity distance |
| Extension distance operator | Extension/opclass dependent | Check that opclass's documentation |

Sharing the same operator symbol does not mean identical units, precision, or sort behavior.

### 20.3. KNN Across a JOIN

For multiple target points, `LATERAL` can retrieve the nearest neighbors per target:

~~~sql
WITH targets(target_id, q) AS (
    VALUES
        (1, point '(2,2)'),
        (2, point '(9,9)')
)
SELECT
    t.target_id,
    p.place_id,
    p.place_name,
    p.location <-> t.q AS distance
FROM targets AS t
CROSS JOIN LATERAL (
    SELECT place_id, place_name, location
    FROM index_lab.places AS p
    ORDER BY p.location <-> t.q
    LIMIT 3
) AS p
ORDER BY t.target_id, distance, p.place_id;
~~~

This demonstrates a correlated-parameter query. Whether the planner chooses a KNN index scan depends on plan costs and types, and on a 10-row lab table a scan + sort is usually cheaper.

### 20.4. Fetching Nearest First vs. Filtering First Changes Semantics

Compare:

~~~sql
-- Get the 3 nearest cafes to point q:
SELECT place_id, place_name, location
FROM index_lab.places
WHERE category = 'cafe'
ORDER BY location <-> point '(2,2)'
LIMIT 3;
~~~

against:

~~~sql
-- Get the 3 nearest places regardless of category,
-- then keep only cafes among those three:
SELECT *
FROM (
    SELECT place_id, place_name, category, location
    FROM index_lab.places
    ORDER BY location <-> point '(2,2)'
    LIMIT 3
) AS nearest_any
WHERE category = 'cafe';
~~~

These express **two different business questions**. The second query can return fewer than three cafes even when a fourth-nearest place is a cafe. Place `WHERE` **before** `LIMIT` when you want the top-k matching a filter.

---

## 21. Lossy, Exact, and Recheck Cond in EXPLAIN

### 21.1. When Is a Recheck Required?

Some indexes store summary keys, such as:

- Bounding boxes around polygons.
- Trigram signatures in GiST `pg_trgm`.
- Compressed or aggregated opclass keys.

The index identifies rows that **might** match. When required by the opclass, the executor re-evaluates the exact predicate against the heap tuple to discard false positives.

### 21.2. Reading the Plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT region_id, name
FROM index_lab.regions
WHERE bounds && box '((3,3),(7,8))';
~~~

A plan might show:

~~~text
Bitmap Heap Scan on regions
  Recheck Cond: (bounds && ...)
  Rows Removed by Index Recheck: ...
  -> Bitmap Index Scan on idx_regions_bounds_gist
       Index Cond: (bounds && ...)
~~~

**This is an illustrative structure**, not guaranteed output, because:

- The planner may pick `Seq Scan` or `Index Scan`.
- `Recheck Cond` on a `Bitmap Heap Scan` does not automatically prove the opclass is always lossy; bitmap heap scans also trigger rechecks when bitmaps degrade to lossy page mode due to memory limits.
- `Rows Removed by Index Recheck` is non-zero only when candidates are actually rejected during recheck.
- Exact opclasses can yield zero false positives.

### 21.3. Index-Only Scans Have Limits

Not every GiST or SP-GiST index can **reconstruct the original indexed value** to support index-only scans. Eligibility depends on the opclass, key storage, PostgreSQL version, and visibility map. Adding `INCLUDE` does not make every GiST/SP-GiST query an index-only scan.

### 21.4. False Positives Do Not Mean Wrong Query Results

PostgreSQL never returns an unverified candidate simply because a summary key matched. Rechecking is part of the **mechanism guaranteeing exact SQL correctness**.

---

## 22. Why Didn't PostgreSQL Use the Index I Created?

### 22.1. Table Is Too Small

With 10 rows, reading the heap directly beats traversing an index and fetching heap rows.

### 22.2. Predicate Does Not Match the Opclass

For instance, SP-GiST `text_ops` supports prefix `^@` but not arbitrary trigram operators. Wrapping a column in an arbitrary function can prevent index matching.

### 22.3. Casts, Expressions, or Collations

~~~sql
WHERE lower(term) = 'postgres'
~~~

does not automatically use an index on raw `term`. If queries rely on an expression, use an expression index with an appropriate opclass—for example, B-tree on `lower(term)` for normalized equality. Never assume GiST is needed just because `WHERE` calls a function.

### 22.4. Low Selectivity

A bounding box covering most points or a date range overlapping almost all reservations favors `Seq Scan`.

### 22.5. ORDER BY Restrictions

A KNN index scan requires an `ORDER BY` distance operator supported by the opclass, typically against an expression treated as constant during the index scan. Custom math expressions force a `Sort`.

### 22.6. Stale Statistics

After a bulk load, run:

~~~sql
ANALYZE index_lab.places;
ANALYZE index_lab.reservations;
ANALYZE index_lab.keywords;
~~~

Check `EXPLAIN`; `ANALYZE` updates statistics, without forcing index usage.

### 22.7. Read/Write Costs and Configuration

The planner weighs heap fetches, random I/O, selectivity, row counts, `LIMIT`, and cost settings. When multiple indexes apply, it picks the cheapest one. To compare fairly, check **which index was actually used** in the plan.

---

## 23. Hands-On EXPLAIN, Statistics, and Index Sizes

### 23.1. Inspecting a Plan Without Executing

~~~sql
EXPLAIN
SELECT place_id, place_name
FROM index_lab.places
WHERE location <@ box '((0,0),(5,5))';
~~~

`EXPLAIN` without `ANALYZE` plans without executing the `SELECT` to measure runtime.

### 23.2. EXPLAIN ANALYZE Actually Executes

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT place_id, place_name
FROM index_lab.places
ORDER BY location <-> point '(2,2)'
LIMIT 5;
~~~

On lab `SELECT` queries, this is safe and informative. When paired with DML (`INSERT`/`UPDATE`/`DELETE`), `EXPLAIN ANALYZE` **actually modifies data** unless rolled back in a lab transaction. Never run DML `EXPLAIN ANALYZE` casually in production.

### 23.3. Listing Existing Indexes

~~~sql
SELECT
    schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'index_lab'
ORDER BY tablename, indexname;
~~~

### 23.4. Inspecting Index Access Methods via Catalogs

~~~sql
SELECT
    i.relname AS index_name,
    am.amname AS access_method,
    t.relname AS table_name,
    pg_get_indexdef(i.oid) AS index_definition
FROM pg_class AS i
JOIN pg_index AS ix ON ix.indexrelid = i.oid
JOIN pg_class AS t ON t.oid = ix.indrelid
JOIN pg_am AS am ON am.oid = i.relam
JOIN pg_namespace AS n ON n.oid = t.relnamespace
WHERE n.nspname = 'index_lab'
ORDER BY table_name, index_name;
~~~

### 23.5. Index Sizes

~~~sql
SELECT
    c.relname AS index_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS index_size,
    pg_relation_size(c.oid) AS bytes
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'index_lab'
  AND c.relkind IN ('i', 'I')
ORDER BY bytes DESC, index_name;
~~~

A larger index can sometimes touch fewer heap pages or eliminate sorts, or vice versa. Judge by total cost—not storage size alone—factoring in build time, write overhead, and query latency.

### 23.6. Index Usage Statistics

~~~sql
SELECT
    schemaname, relname, indexrelname,
    idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'index_lab'
ORDER BY relname, indexrelname;
~~~

These are **statistical counters** dependent on reset timestamps and workload exposure. Seeing `idx_scan = 0` right after creating an index in a small lab does not prove long-term uselessness; the table may simply be too small or untested.

---

## 24. Creating Indexes on Large Tables: Locks and Operations

### 24.1. Standard CREATE INDEX

~~~sql
CREATE INDEX idx_large_points_gist
ON index_lab.places USING gist (location);
~~~

Syntax example; do not re-run if an index with that name already exists. Standard `CREATE INDEX` on a large table can **block concurrent DML** while building. A fast build in a small lab hides production lock impact.

### 24.2. CREATE INDEX CONCURRENTLY

On large active tables, consider:

~~~sql
CREATE INDEX CONCURRENTLY idx_places_location_gist_online
ON index_lab.places USING gist (location);
~~~

Properties:

- Avoids blocking normal `INSERT`/`UPDATE`/`DELETE` compared to standard builds.
- Can wait on active transactions/snapshots before and between scan passes.
- Generates CPU, I/O, and WAL load.
- **Cannot run inside an explicit transaction block**.
- Failures or cancellations can leave an `INVALID` index requiring catalog inspection and cleanup.

### 24.3. Diagnosing Invalid Indexes

~~~sql
SELECT
    idx.relname AS index_name,
    ix.indisvalid,
    ix.indisready,
    pg_get_indexdef(ix.indexrelid) AS definition
FROM pg_index AS ix
JOIN pg_class AS idx ON idx.oid = ix.indexrelid
JOIN pg_class AS tbl ON tbl.oid = ix.indrelid
JOIN pg_namespace AS n ON n.oid = tbl.relnamespace
WHERE n.nspname = 'index_lab';
~~~

`indisvalid = false` means the planner will not use the index as valid. Never assume “`CREATE INDEX CONCURRENTLY` timed out, yet the index name exists, so it is ready.”

### 24.4. Maintenance and Write Overhead

Both GiST and SP-GiST incur costs:

- Entry insertion on `INSERT`.
- Maintenance when `UPDATE`/`DELETE` modifies tuple versions.
- WAL and disk footprint.
- `VACUUM`/autovacuum cleanup.
- Occasional rebuild/reindex when operationally warranted.

If you create three `point` indexes on one column just to “try everything,” every insert must maintain all three. In production, keep **only the minimal index set with measured benefit**.

### 24.5. REINDEX and REINDEX CONCURRENTLY

When bloat, corruption, or structural needs require rebuilding, PostgreSQL offers `REINDEX` and (depending on version/object type) `REINDEX CONCURRENTLY` to reduce write blocking. Both carry operational costs and transaction-block rules; never use them as a blind fix for slow queries before inspecting `EXPLAIN` and statistics.

---

## 25. Benchmarking GiST vs. SP-GiST Properly

### 25.1. Metrics to Measure

| Category | Metric | Why It Matters |
|---|---|---|
| Query | p50/p95/p99 latency per predicate | Rare outlier queries can stall severely |
| Planner | `Index Scan`, `Bitmap Heap Scan`, `Seq Scan` | Confirms whether the index is actually chosen |
| I/O | `shared hit/read`, buffers, WAL | Reveals cache and storage cost |
| Data | Row count, selectivity, point/range distribution | Strongly affects partitioning vs. bounding boxes |
| Storage | Index size, dead tuples | Long-term footprint |
| Write | `INSERT`/`UPDATE` throughput | Checks write amplification |
| Build | Index creation time and temp disk | Deployment feasibility |
| Maintenance | `VACUUM`/`REINDEX` overhead | Operational sustainability |

### 25.2. A Simple Benchmarking Workflow

1. Prepare representative data in an **isolated database**.
2. Test **one** index configuration at a time, or compare across identical dataset copies.
3. Run `ANALYZE`.
4. Execute realistic queries and record plans, latencies, and buffer counts.
5. Include varied selectivities: tight regions, wide regions, clustered points, KNN top-5 and top-100.
6. Measure `INSERT` and `UPDATE` throughput.
7. Repeat for the competing index setup under comparable hardware and cache conditions.
8. Draw conclusions for your **specific workload**, not a single cherry-picked query.

### 25.3. Avoid False Conclusions When Multiple Indexes Coexist

If both GiST and SP-GiST exist on the same column, the planner may pick one, the other, or `Seq Scan`. Every benchmark run must confirm `Index Scan using idx...` in the plan; isolate each index configuration cleanly on dedicated copies or controlled lab runs.

### 25.4. Caching and Run Order

The first run may read cold disk pages while the second hits warm memory. Never declare a winner just because it ran **second**. Repeat trials, alternate run orders, and track both cold and warm behavior.

### 25.5. Avoid Forcing the Planner in Production

Setting `enable_seqscan = off` or skewing `random_page_cost` just to force an index scan does not prove that plan has lower total cost. Treat debug GUCs in a lab purely as plan-exploration experiments, never as production defaults.

---

## 26. Common Mistakes and Misconceptions

| Misconception / Mistake | Why It Is Wrong | Better Approach |
|---|---|---|
| “GiST is an index only for geometry” | GiST is an extensible tree framework | Check opclasses for ranges, `inet`, text, and extensions |
| “SP-GiST is definitely faster than GiST” | Different partitioning structure, no universal guarantee | Benchmark actual queries and data distribution |
| “`USING gist` can index any data type” | Requires an opclass for that type | Check `pg_opclass` |
| “GiST and SP-GiST support identical operators” | Opclasses and methods differ | Check operator families/opclasses |
| “For TEXT, use SP-GiST to speed up `ILIKE '%x%'`” | `text_ops` is not trigram | Use `pg_trgm` GiST/GIN when needed |
| “KNN works with `ORDER BY` any distance function” | Planner needs a matching opclass ordering operator | Use `<->` for the right type/opclass and check `EXPLAIN` |
| “All KNN queries return distances in meters” | Units depend on type and operator | Core `point` is planar; use an appropriate CRS |
| “With GiST, you never need GIN for full-text” | Access patterns and structures differ | Benchmark GiST vs. GIN per workload |
| “Range overlap can be replaced by a B-tree on `start_time`” | Filtering only start times misses long overlapping intervals | Use range types and `&&` where suitable |
| “Two intervals touching at an endpoint always overlap” | Bound flags determine overlap | Use `[)` conventions and verify range operators |
| “SP-GiST range implies identical multirange support” | Range and multirange use separate opclasses | Check catalogs; use GiST `multirange_ops` where supported |
| “GiST `inet_ops` is default for `inet`” | GiST `inet_ops` is not the default | Write `USING gist (network inet_ops)` |
| “SP-GiST is never lossy” | Depends on opclass and leaf representation | Check `Recheck Cond` and `EXPLAIN` |
| “Lossy indexes return wrong data to clients” | The executor rechecks exact predicates | Understand candidate generation + recheck |
| “Bitmap `Recheck Cond` means every index query is lossy” | Rechecks also happen on memory-limited lossy bitmap pages | Inspect `Rows Removed by Index Recheck` |
| “Index-only scan only needs `INCLUDE`” | Opclass must reconstruct keys, and visibility map still governs | Verify opclass capabilities and `EXPLAIN` |
| “Once an index exists, every query uses it” | Planner chooses by cost and selectivity | Run `ANALYZE` and inspect `EXPLAIN` |
| “Indexing `point` replaces PostGIS” | Geographic coordinates on Earth require CRS/geodetic math | Use PostGIS with appropriate metrics |
| “GiST on a range column prevents overlapping bookings” | A lookup index is not a write constraint | Use `EXCLUDE USING gist` with matching operators |
| “`btree_gist` equals `UNIQUE` B-tree” | Enables scalar operators in GiST, not B-tree uniqueness | Use `UNIQUE`/`PK` or `EXCLUDE` appropriately |
| “GiST and SP-GiST add no write cost” | Every index is maintained across DML | Account for write amplification |
| “`CREATE INDEX CONCURRENTLY` has zero production impact” | Consumes I/O, WAL, waits, and can fail invalid | Monitor and plan maintenance windows |
| “An index with that name exists, so it is VALID” | Concurrent builds can leave invalid indexes | Verify `pg_index.indisvalid` |
| “Planner choosing `Seq Scan` on small data is a bug” | `Seq Scan` can be cheapest | Measure on representative data sizes |
| “Forcing indexes via `enable_seqscan = off` is tuning” | Changes choice without lowering true cost | Evaluate natural plans |
| “Adding GiST, SP-GiST, and GIN makes every query fast” | Heavy write and maintenance overhead | Retain only indexes with measured net gain |

---

## 27. Process for Choosing Between GiST and SP-GiST

Orientation flowchart:

~~~mermaid
flowchart TD
    A["Specify exact predicate and data type"] --> B{"Primary query pattern?"}
    B -- "Scalar equality/range" --> C["B-tree; BRIN for huge physically correlated tables"]
    B -- "JSONB, arrays, full-text" --> D["GIN with matching operator class"]
    B -- "Geometry/range/inet/prefix/nearest" --> E["Find GiST/SP-GiST opclass supporting the operator"]
    B -- "Fuzzy text" --> F["pg_trgm: GiST vs GIN"]
    E --> G{"Supported by both GiST and SP-GiST?"}
    G -- "Only one" --> H["Use the method with the matching opclass"]
    G -- "Both" --> I["Benchmark on real distribution and queries"]
    I --> J{"Is KNN top-k central?"}
    J -- "Yes" --> K["Check ordering operators and Index Scan Order By"]
    J -- "No" --> L["Compare Index Cond, recheck, buffers"]
    K --> M["Evaluate latency, writes, size, build time"]
    L --> M
    F --> M
    H --> M
    C --> M
    D --> M
    M --> N["Keep only the minimal useful index"]
~~~

### 27.1. Reasoning Example Before Creating an Index

Suppose business requirements ask to “find overlapping bookings on April 20”:

1. Data represents date intervals ⇒ `daterange`.
2. Predicate is overlap ⇒ `&&`.
3. Both GiST and SP-GiST have `range_ops` ⇒ both are candidates.
4. If we must **prevent overlapping bookings on write**, an index alone is insufficient ⇒ use an **exclusion constraint** (GiST is the standard method).
5. If filtering by `room_id`, evaluate a combined index/constraint.
6. Verify `[)` bounds and `NULL` rules.
7. Measure query plans and insert/update impact.

Another example: “top 10 names most similar to `'postgress'`”:

1. Text type with trigram similarity metric.
2. Requires `pg_trgm` extension.
3. Requires KNN `ORDER BY term <-> query LIMIT 10`.
4. GiST `gist_trgm_ops` fits top-k KNN better than GIN in this case.
5. Check thresholds and trigram lengths; benchmark on real data.

---

## 28. Practice Exercises

Exercises use `index_lab.places`, `regions`, `reservations`, `network_rules`, `keywords`, and earlier optional tables. The goal is understanding logic and SQL; **do not run every `CREATE INDEX` simultaneously if you only intend to test one option**.

### Exercise 1 — What Are GiST and SP-GiST?

Explain both access methods and the fundamental difference between a “bounding-region tree” and a “space-partitioned tree.”

### Exercise 2 — Operator Classes

Why might `CREATE INDEX ... USING spgist (col)` fail for a data type even though PostgreSQL supports the SP-GiST access method?

### Exercise 3 — Catalogs

Write SQL listing `gist` and `spgist` opclasses along with input types and default flags. Why must you inspect this on the **current database**?

### Exercise 4 — Point GiST

Create a GiST index on `index_lab.places.location` and write a query finding points inside `box '((0,0),(5,5))'`.

### Exercise 5 — Point SP-GiST

Write SQL creating two distinct point indexes using `quad_point_ops` and `kd_point_ops`. Should both normally be kept in production?

### Exercise 6 — KNN

Write a query finding the three places closest to `point '(2,2)'`. Which operator enables the planner to consider a KNN index scan?

### Exercise 7 — Wrong ORDER BY Form

Why doesn't `ORDER BY sqrt(pow(x-2,2)+pow(y-2,2))` on separate coordinate columns translate automatically into a GiST point KNN scan?

### Exercise 8 — Coordinates

Why shouldn't the distance between `point '(106.7,10.8)'` and `point '(106.8,10.9)'` on longitude/latitude coordinates be interpreted as meters?

### Exercise 9 — Box Overlap

Create a GiST index on `regions.bounds` and write a predicate finding boxes overlapping `box '((3,3),(7,8))'`.

### Exercise 10 — Circle

Does core GiST support `circle`? Can you assume SP-GiST also provides a default circle opclass?

### Exercise 11 — Range Overlap

Using `daterange`, write a predicate finding reservations overlapping `[2026-04-03, 2026-04-06)`.

### Exercise 12 — [) Bounds

Do `[2026-04-01, 2026-04-04)` and `[2026-04-04, 2026-04-05)` overlap? Why do bounds matter?

### Exercise 13 — Range Containment

Find reservations covering `2026-04-03` using a range operator rather than manually comparing separate start/end columns.

### Exercise 14 — SP-GiST Range

Write the command creating an SP-GiST index on `reservations.stay`. Does it prevent double bookings automatically?

### Exercise 15 — Multiranges

Distinguish GiST `multirange_ops` from SP-GiST `range_ops`. Can you assume SP-GiST directly indexes `datemultirange`?

### Exercise 16 — Subnets

Write a query finding `network_rules.network` values inside `10.10.0.0/16`, inclusive. Which operator fits?

### Exercise 17 — inet_ops

Explain the syntax for creating a GiST index on `network INET` and why `inet_ops` must be named explicitly.

### Exercise 18 — Text Prefix

Write SQL creating SP-GiST `text_ops` on `keywords.term` and finding keywords starting with `post`.

### Exercise 19 — Prefix vs. Fuzzy

Why isn't `term ^@ 'post'` equivalent to `pg_trgm`'s `term % 'postgre'`?

### Exercise 20 — Trigram Similarity

Write SQL enabling `pg_trgm` and creating a GiST trigram index. Query keywords similar to `postgress` using `%`.

### Exercise 21 — KNN Trigram

Write a query finding the five keywords with the smallest trigram distance to `postgress`. How do GiST and GIN differ for KNN distance ordering?

### Exercise 22 — Overly Short Patterns

Will `ILIKE '%a%'` always use a trigram index efficiently? Why or why not?

### Exercise 23 — Full-Text

Write SQL creating a GiST index on `articles.search_vector` and querying `@@ to_tsquery(...)`. When should you compare against GIN?

### Exercise 24 — PostGIS

Distinguish core `point` from PostGIS `geometry(Point, 4326)`. Is the threshold in `ST_DWithin(geom, q, 0.01)` at SRID 4326 measured in meters by default?

### Exercise 25 — Exclusion Constraint

After enabling `btree_gist`, write a constraint preventing two reservations for the same `room_id` from having overlapping `stay` ranges. Does a plain GiST index on `stay` replace this constraint?

### Exercise 26 — Lossy and Recheck

Explain candidate generation/recheck and how to interpret `Recheck Cond` alongside `Rows Removed by Index Recheck` in `EXPLAIN`.

### Exercise 27 — Planner Picks Seq Scan

The `places` table has only 10 rows; queries use `Seq Scan` even though a GiST index exists. Is this necessarily a bug? Give four reasons the planner may skip an index.

### Exercise 28 — Monitoring Indexes

Write a query inspecting `pg_indexes` and another checking `pg_index.indisvalid` after `CREATE INDEX CONCURRENTLY`.

### Exercise 29 — Size

Write SQL checking index sizes in `index_lab` and explain why the smallest index is not always optimal.

### Exercise 30 — Cost of Writes

Why shouldn't you create GiST, SP-GiST quad, SP-GiST kd, GIN, and B-tree on the same column “just to be safe”?

### Exercise 31 — Top-k by Category

Write a query finding the two closest `cafe` places to `point '(2,2)'`. Why should `WHERE category = 'cafe'` come before `LIMIT`?

### Exercise 32 — Scheduling Race Condition

Two clients simultaneously check “room 101 has no overlap” and then `INSERT`. Why does check-then-insert without locking/constraints fail under concurrency? What is the solution?

### Exercise 33 — Indexing Networks

With millions of CIDR ranges, common queries run `network <<= q` and `network && q`. Which index would you test first, and what metrics would you measure?

### Exercise 34 — Removing Redundant Indexes

A table has both GiST and SP-GiST point indexes serving identical predicates. Outline the process for deciding whether one can be dropped.

### Exercise 35 — Index Selection Synthesis

Pick one or two suitable index candidates for each scenario:

1. Lookup `user_id = 42`.
2. Find overlapping time intervals.
3. Find top-10 stores nearest a planar point.
4. Search text with `ILIKE '%word%'`.
5. Find closest words by trigram distance.
6. Filter JSONB object containment.
7. Find IPs belonging to a subnet.
8. Find text starting with a prefix.
9. Full-text query `tsvector @@ tsquery`.
10. Filter timestamps on a multi-billion-row append-only log table.

---

## 29. Suggested Solutions

### Exercise 1 — Structures

GiST is a balanced search-tree framework using summary keys such as bounding regions depending on the operator class. SP-GiST supports space- or prefix-partitioned trees like quadtrees, k-d trees, and radix trees without GiST-style balancing. Neither method is universally fastest for every dataset.

### Exercise 2 — Opclasses

An access method provides only the framework. Without an operator class for the column's type and semantics, PostgreSQL cannot map values into keys or search strategies. A compatible opclass and registered operators are required.

### Exercise 3 — Catalogs

~~~sql
SELECT
    a.amname,
    o.opcname,
    o.opcintype::regtype AS input_type,
    o.opcdefault AS is_default
FROM pg_opclass AS o
JOIN pg_am AS a ON a.oid = o.opcmethod
WHERE a.amname IN ('gist', 'spgist')
ORDER BY a.amname, o.opcname;
~~~

The list depends on server version and installed extensions; never rely on someone else's environment.

### Exercise 4 — GiST point

~~~sql
CREATE INDEX idx_places_location_gist
ON index_lab.places USING gist(location);

SELECT place_id, place_name, location
FROM index_lab.places
WHERE location <@ box '((0,0),(5,5))'
ORDER BY place_id;
~~~

If the index already exists, do not re-run `CREATE` with the same name; this is a practice template.

### Exercise 5 — SP-GiST point

~~~sql
CREATE INDEX idx_places_quad
ON index_lab.places USING spgist(location quad_point_ops);

CREATE INDEX idx_places_kd
ON index_lab.places USING spgist(location kd_point_ops);
~~~

Do not keep both by default; measure query plans, latency, index size, and write cost. Keep only the index(es) with clear benefit in production.

### Exercise 6 — KNN

~~~sql
SELECT place_id, place_name, location,
       location <-> point '(2,2)' AS distance
FROM index_lab.places
ORDER BY location <-> point '(2,2)'
LIMIT 3;
~~~

`<->` is the KNN distance operator for point opclasses. The planner can use an ordered index scan when cheaper than scan + sort.

### Exercise 7 — Order-by-distance Expression

GiST point indexes recognize specific opclass distance-ordering operators. Custom `sqrt`/`pow` formulas over separate numeric columns are not mapped to that opclass ordering operator. For index-assisted KNN, use `<->` on an indexed `point` column and verify the plan.

### Exercise 8 — Units

Core `point` operates in planar coordinates. If inputs are longitude/latitude degrees, Euclidean distance in degrees is not meters. Use PostGIS `geography` or `geometry` in a metric CRS with the corresponding distance function.

### Exercise 9 — Box Overlap

~~~sql
CREATE INDEX idx_regions_bounds_gist
ON index_lab.regions USING gist(bounds);

SELECT region_id, name
FROM index_lab.regions
WHERE bounds && box '((3,3),(7,8))';
~~~

`&&` on `box` checks geometric overlap.

### Exercise 10 — Circle

Core GiST includes `circle_ops`; SP-GiST does not automatically support every GiST opclass. Inspect `pg_opclass` before assuming cross-method parity.

### Exercise 11 — Range Overlap

~~~sql
SELECT reservation_id, room_id, stay
FROM index_lab.reservations
WHERE stay && daterange(
    DATE '2026-04-03',
    DATE '2026-04-06',
    '[)'
)
ORDER BY reservation_id;
~~~

### Exercise 12 — Half-Open Bounds

No overlap: April 4 is the **exclusive** upper bound of the first interval and the **inclusive** lower bound of the second. `[)` models check-in/check-out nights cleanly without double-counting turnover days.

### Exercise 13 — Element Containment

~~~sql
SELECT reservation_id, room_id, guest_name
FROM index_lab.reservations
WHERE stay @> DATE '2026-04-03';
~~~

### Exercise 14 — SP-GiST Range

~~~sql
CREATE INDEX idx_reservations_stay_spgist
ON index_lab.reservations USING spgist(stay);
~~~

The index accelerates overlap/containment queries when chosen by the planner; it does not prevent concurrent double bookings. You need an exclusion constraint or locking/transaction strategy.

### Exercise 15 — Range vs. Multirange

Modern PostgreSQL GiST has a built-in multirange opclass. SP-GiST provides `range_ops` for **range types**, not multiranges by default. Verify available operator classes before creating indexes.

### Exercise 16 — IP in Subnet

~~~sql
SELECT rule_id, label, network
FROM index_lab.network_rules
WHERE network <<= inet '10.10.0.0/16';
~~~

`<<=` means “contained by or equal to,” including the subnet itself.

### Exercise 17 — inet_ops

~~~sql
CREATE INDEX idx_network_rules_gist
ON index_lab.network_rules USING gist(network inet_ops);
~~~

GiST `inet_ops` is not the default opclass for `inet`/`cidr`, so it must be specified explicitly.

### Exercise 18 — Text Prefix

~~~sql
CREATE INDEX idx_keywords_spgist_text
ON index_lab.keywords USING spgist(term text_ops);

SELECT term
FROM index_lab.keywords
WHERE term ^@ 'post'
ORDER BY term;
~~~

`^@` is a strict prefix starts-with operator, not fuzzy matching.

### Exercise 19 — Prefix vs. Similarity

Prefix matching tests whether a string starts with an exact substring; trigram similarity measures shared three-character sequences against a similarity threshold. Two strings can have high trigram similarity without sharing a prefix.

### Exercise 20 — pg_trgm

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_keywords_gist_trgm
ON index_lab.keywords USING gist (term gist_trgm_ops);

SELECT term, similarity(term,'postgress') AS score
FROM index_lab.keywords
WHERE term % 'postgress'
ORDER BY score DESC, term;
~~~

Create only if extensions are permitted; `pg_trgm.similarity_threshold` controls which rows match `%`.

### Exercise 21 — KNN Trigram

~~~sql
SELECT term, term <-> 'postgress' AS distance
FROM index_lab.keywords
ORDER BY term <-> 'postgress'
LIMIT 5;
~~~

GiST `gist_trgm_ops` supports KNN distance ordering. GIN `gin_trgm_ops` works well for filtering yet does not perform the same distance-ordered KNN index scan.

### Exercise 22 — Short Patterns

Efficiency is not guaranteed. Patterns without informative trigrams force scanning large parts of the index. Check `EXPLAIN`; for a single character, a trigram index is rarely effective.

### Exercise 23 — Full-Text

~~~sql
CREATE INDEX idx_articles_gist_fts
ON index_lab.articles USING gist(search_vector);

SELECT article_id, body
FROM index_lab.articles
WHERE search_vector @@ to_tsquery('simple', 'indexing');
~~~

GIN often fits read-heavy full-text workloads better; compare selectivity, update cost, and query latency. Do not conflate FTS with `ILIKE`.

### Exercise 24 — PostGIS

Core `point` is planar geometry; `geometry(Point, 4326)` carries an explicit SRID. For `geometry` in SRID 4326, `ST_DWithin` measures distances in **degrees**, not meters. Switch to `geography` or a metric projection if you need meters.

### Exercise 25 — Exclusion

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE index_lab.reservations
ADD CONSTRAINT no_overlapping_stays_for_room
EXCLUDE USING gist(room_id WITH =, stay WITH &&);
~~~

A standalone GiST index on `stay` only speeds up overlap queries; **it neither prevents race conditions nor enforces write constraints**. Only the exclusion constraint rejects overlapping bookings for the same room.

### Exercise 26 — Recheck

A lossy index stores summary keys and yields rows that **might** match. PostgreSQL re-evaluates the exact predicate on the heap when needed. In `EXPLAIN`:

- `Index Cond` / `Recheck Cond` show the index filter and verification condition.
- `Rows Removed by Index Recheck` counts candidates rejected during recheck.
- Seeing `Recheck Cond` alone does not prove an index is always lossy; it also appears on lossy page-level bitmap heap scans.

### Exercise 27 — Seq Scan

Not necessarily a bug. Causes include: tiny table, unselective predicate, operator unsupported by the index, expression/cast mismatching the indexed column, large `LIMIT`, or stats/I/O estimates making sequential scan + sort cheaper.

### Exercise 28 — Index Metadata

~~~sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'index_lab'
ORDER BY tablename, indexname;
~~~

~~~sql
SELECT
    idx.relname AS index_name,
    ix.indisvalid,
    ix.indisready
FROM pg_index AS ix
JOIN pg_class AS idx ON idx.oid = ix.indexrelid
JOIN pg_class AS tbl ON tbl.oid = ix.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'index_lab';
~~~

An index name appearing in catalogs is not enough: a failed concurrent build leaves `indisvalid = false`.

### Exercise 29 — Index Size

~~~sql
SELECT
    idx.relname AS index_name,
    pg_size_pretty(pg_relation_size(idx.oid)) AS size_pretty,
    pg_relation_size(idx.oid) AS size_bytes
FROM pg_class AS idx
JOIN pg_namespace AS ns ON ns.oid = idx.relnamespace
WHERE ns.nspname = 'index_lab'
  AND idx.relkind IN ('i','I')
ORDER BY size_bytes DESC;
~~~

A larger index might touch fewer heap pages or avoid sorting; choose based on total cost, not size alone.

### Exercise 30 — Redundant Indexes

Every insert, update, and delete must maintain all affected indexes, multiplying I/O, WAL, disk space, and reducing write throughput. Redundant indexes also inflate `VACUUM`, `REINDEX`, and deployment overhead. Pick indexes strictly around real queries.

### Exercise 31 — Top-k Cafes

~~~sql
SELECT place_id, place_name, location
FROM index_lab.places
WHERE category = 'cafe'
ORDER BY location <-> point '(2,2)'
LIMIT 2;
~~~

Filtering `category` before `LIMIT` guarantees the top two results are cafes; taking top-2 overall and filtering afterward changes semantics and can return fewer than two cafes.

### Exercise 32 — Check-Then-Insert Race

Two clients can both see “no conflict” before either commits its `INSERT`, creating double bookings if no constraint or locking exists. A GiST exclusion constraint on `(room_id WITH =, stay WITH &&)` paired with transaction handling of SQLSTATE `23P01` solves this safely.

### Exercise 33 — CIDR Workload

Benchmark SP-GiST `inet_ops` and GiST `inet_ops`, plus B-tree if equality lookups are significant. Measure p95 latency, buffers, index size, write overhead, subnet selectivity, host-vs-network mix, scale, and planner choices.

### Exercise 34 — Removing Redundant Indexes

1. Identify which queries actually use each index via `EXPLAIN`.
2. Audit full workload stats, not just a single query.
3. Benchmark each setup on representative data.
4. Compare insert/update cost, storage, `VACUUM`, and build time.
5. When dropping one, use a reversible migration plan; never drop an active index unmeasured.

### Exercise 35 — Selection Matrix

| Scenario | Candidate |
|---|---|
| 1. `user_id = 42` | B-tree |
| 2. Overlapping time intervals | GiST/SP-GiST `range_ops` |
| 3. Top-10 stores near a point | GiST or SP-GiST point KNN; PostGIS for real geography |
| 4. `ILIKE '%word%'` | `pg_trgm` GiST/GIN |
| 5. Trigram distance top-k | GiST `gist_trgm_ops` |
| 6. JSONB containment | GIN JSONB opclass |
| 7. Addresses within a subnet | SP-GiST/GiST `inet_ops` |
| 8. Text starts-with | SP-GiST `text_ops` with `^@` or B-tree prefix strategy |
| 9. `tsvector @@ tsquery` | GIN usually checked first; GiST also supports |
| 10. Append-only log timestamps | BRIN or B-tree depending on correlation and selectivity |

---

## 30. Checklist for Choosing and Deploying Indexes

### Before Choosing

- [ ] Write down exact data types and **operators** used in queries.
- [ ] Verify business semantics: `[)` intervals, planar vs. Earth coordinates, prefix vs. similarity.
- [ ] Inspect actual operator classes in `pg_opclass` for your version/extensions.
- [ ] Determine whether KNN `<->` and top-k ordering are required.
- [ ] Evaluate B-tree, GIN, and BRIN before defaulting to GiST/SP-GiST.
- [ ] For non-overlapping invariants, use **`EXCLUDE`**, not just a read index.
- [ ] Analyze duplicates, `NULL`s, skew, density, and selectivity.

### When Testing

- [ ] Use a representative dataset, not just a 10-row lab.
- [ ] Run `ANALYZE` before measuring.
- [ ] Inspect `Index Scan`/`Index Cond`/`Order By`/`Recheck Cond`.
- [ ] Compare latency, buffers, size, write cost, and build time.
- [ ] Never trust a single warm-cache run or forced plan.
- [ ] Avoid keeping overlapping indexes without clear justification.

### When Deploying to Production

- [ ] Verify whether the table receives continuous writes during builds.
- [ ] If using `CREATE INDEX CONCURRENTLY`, run outside transaction blocks.
- [ ] Monitor build progress, disk, WAL, replication lag, and waiting backends.
- [ ] Handle invalid indexes before retrying.
- [ ] Confirm opclass, definition, and `VALID` status after deployment.
- [ ] Review critical queries and write throughput impact.

---

## 31. Official Documentation References

Verify operator classes against your exact PostgreSQL major version:

- [PostgreSQL — Index Types](https://www.postgresql.org/docs/current/indexes-types.html): overview of B-tree, GiST, SP-GiST, GIN, and BRIN.
- [PostgreSQL — GiST Indexes](https://www.postgresql.org/docs/current/gist.html): built-in operator classes, support functions, and distance ordering.
- [PostgreSQL — SP-GiST Indexes](https://www.postgresql.org/docs/current/spgist.html): quadtree/k-d tree/radix tree, supported opclasses, and KNN.
- [PostgreSQL — pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html): similarity, operators, GiST/GIN opclasses, and trigram KNN.
- [PostgreSQL — Range Types](https://www.postgresql.org/docs/current/rangetypes.html): bounds, overlap, containment, and exclusion constraints.
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): `USING`, operator classes, concurrent builds, and transaction limits.
- [PostgreSQL — btree_gist](https://www.postgresql.org/docs/current/btree-gist.html): B-tree-like GiST operators for exclusion constraints.
- [PostGIS Documentation](https://postgis.net/documentation/): `geometry`/`geography` semantics, CRS, spatial operators, and indexing.

When `/current/` advances to a newer release, consult `/docs/<major>/...` for your running server version. Never treat an extension's operator class as built-in across every database.

---

## 32. Summary

**GiST and SP-GiST are not merely two ways to write “spatial index.” They are two distinct indexing frameworks with different tree structures and partitioning strategies, paired with operator classes to solve specialized predicates.**

- **GiST — Generalized Search Tree:** supports diverse types and strategies—geometry, ranges/multiranges, networks, trigrams, full-text, and exclusion constraints via opclasses and extensions. It may store summary keys and require rechecks when lossy.
- **SP-GiST — Space-Partitioned GiST:** supports space- or prefix-partitioned structures like quadtrees, k-d trees, and radix trees, with built-in opclasses for `point`, `box`, `polygon`, `range`, `inet`, and `text`.
- **A compatible data type does not mean every operator works.** Verify type, operator, and operator class on your PostgreSQL version.
- **KNN:** `ORDER BY indexed_value <-> query LIMIT k` enables index-assisted nearest-neighbor scans when the opclass supports distance ordering; `<->` for `point` and `pg_trgm` carry **different semantics and units**.
- **Time intervals:** use range types with `&&`/`@>` for overlap and containment. To **prevent double bookings**, use an exclusion constraint and proper transaction logic, not an index alone.
- **Text:** SP-GiST `text_ops` targets prefixes; fuzzy/trigram matching needs `pg_trgm`, while `tsvector @@ tsquery` full-text search typically compares GiST vs. GIN.
- **Real geography:** core `point` is planar; PostGIS `geometry`/`geography` with an appropriate CRS is essential for real-world geographic distances.
- **Performance:** never judge by access method name. Base decisions on `EXPLAIN (ANALYZE, BUFFERS)`, statistics, index size, representative data, and write impact.
- **Deployment:** large indexes require attention to locking, `CONCURRENTLY`, `INVALID` states, WAL, disk space, and replication.

Workflow to remember: **define the business question → pick the accurate data type → check operators and operator classes → build one candidate index → measure `EXPLAIN` on realistic workloads → weigh write/maintenance costs → keep only configurations with verified benefit**.
