# MATCH to Find Nodes by Label and Property

In Neo4j's **property graph** model, data is stored as nodes, relationships, and properties. A node can carry one or more labels, such as `:Person` or `:Employee`; properties store values like `name`, `age`, and `city`. The Cypher query language uses the **`MATCH`** clause to find matching graph patterns, then `WHERE` to filter and `RETURN` to retrieve results.

This lesson belongs to the **Read Queries** chapter and focuses on using `MATCH` to find **nodes by label and property**. This is the foundation before querying relationships, paths, optimizing with indexes, or calling Neo4j from the Java Driver and Spring Data Neo4j.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Write `MATCH (n:Label)` to find nodes carrying a label and distinguish labels from properties.
2. Find nodes by one or more properties using the `{key: value}` pattern and the `WHERE` clause.
3. Combine numeric, string, boolean, and list conditions, and check for missing properties.
4. Use `$parameter` parameters, sort and limit results, and count nodes.
5. Read query plans with `EXPLAIN`/`PROFILE` and identify when an index is useful.

## 2. Basic Structure of MATCH

```cypher
MATCH (p:Person)
WHERE p.age >= 18
RETURN p.name AS name, p.age AS age;
```

| Component | Meaning |
| --- | --- |
| `MATCH` | Finds graph patterns that satisfy the described conditions. |
| `(p:Person)` | Finds nodes with the `Person` label, binding variable `p` to each matching node. |
| `p.age` | Accesses the `age` property of node `p`. |
| `WHERE p.age >= 18` | Keeps only nodes where `age` is 18 or older. |
| `RETURN ... AS ...` | Selects the values to return and assigns column aliases. |

A node can carry **multiple labels**; labels categorize nodes, while properties describe a node's data. Naming the variable `p` is valid only within the scope of the query and does not create or modify data.

> **Note:** Cypher is case-sensitive for label names, property names, and standard string comparisons. `:Person` is different from `:person`; `p.name` is different from `p.Name`. Property values must also match the data type—for example, the number `25` is different from the string `'25'`.

## 3. Practice Dataset

Execute the following data setup in Neo4j's **practice database**. Using `MERGE` on `id` avoids creating duplicate nodes in the sample dataset when re-run, assuming the initial data has no duplicate `id` values.

```cypher
UNWIND [
  {id: 'p01', name: 'An',   age: 25, city: 'Hà Nội',           active: true},
  {id: 'p02', name: 'Bình', age: 31, city: 'Đà Nẵng',          active: true},
  {id: 'p03', name: 'Chi',  age: 28, city: 'Hà Nội',           active: false},
  {id: 'p04', name: 'Dũng', age: 35, city: 'TP. Hồ Chí Minh', active: true},
  {id: 'p05', name: 'An',   age: 30, city: 'Hà Nội',           active: true}
] AS row
MERGE (p:Person {id: row.id})
SET p.name = row.name,
    p.age = row.age,
    p.city = row.city,
    p.active = row.active;
```

To illustrate that a node can carry multiple labels, add the `Employee` label to two nodes:

```cypher
MATCH (p:Person)
WHERE p.id IN ['p01', 'p03']
SET p:Employee;
```

From here on, the sample dataset has five `Person` nodes. Two nodes, `p01` and `p03`, simultaneously carry the `Employee` label.

## 4. Finding Nodes by Label

### 4.1. Single Label

```cypher
MATCH (p:Person)
RETURN p.id AS id, p.name AS name, p.city AS city
ORDER BY id;
```

With the sample data, the query returns five rows from `p01` to `p05`. `MATCH` only determines the set of matching nodes; `RETURN` decides which columns are displayed.

### 4.2. Multiple Labels on the Same Node

```cypher
MATCH (p:Person:Employee)
RETURN p.id AS id, p.name AS name
ORDER BY id;
```

The result is `p01` (An) and `p03` (Chi). The syntax `:Person:Employee` requires the node to have **both labels**, not just one of them. To find nodes that only need to have the `Employee` label, use `MATCH (p:Employee)`.

### 4.3. Without Specifying a Label

```cypher
MATCH (n)
RETURN count(n) AS totalNodes;
```

`MATCH (n)` considers nodes of **all labels** in the database. Therefore, `totalNodes` is only 5 if the database contains solely the five nodes from this example. In real-world workloads, specify the label when you already know the type of data you need so the query is clearer and gives the optimizer more information.

## 5. Finding Nodes by Exact Property

You can declare a property map directly inside the node pattern:

```cypher
MATCH (p:Person {name: 'An'})
RETURN p.id AS id, p.name AS name
ORDER BY id;
```

**Expected result:** `p01` and `p05`, because both nodes have `name = 'An'`. Names are not necessarily unique keys; to find one specific person, prefer an identifier such as `id` backed by a uniqueness constraint.

When there are multiple properties in the pattern, **all** of them must match:

```cypher
MATCH (p:Person {name: 'An', city: 'Hà Nội'})
RETURN p.id AS id, p.age AS age
ORDER BY id;
```

The query above is equivalent in filtering logic to:

```cypher
MATCH (p:Person)
WHERE p.name = 'An' AND p.city = 'Hà Nội'
RETURN p.id AS id, p.age AS age
ORDER BY id;
```

In both cases, the result is `p01` (age 25) and `p05` (age 30). The `{key: value}` pattern is convenient for **equality comparisons**; use `WHERE` when you need other operators or complex expressions.

## 6. Advanced Filtering with WHERE

### 6.1. Common Operators

| Category | Example | Purpose |
| --- | --- | --- |
| Comparison | `p.age = 30`, `p.age <> 30` | Equal, not equal. |
| Range | `p.age >= 25 AND p.age < 35` | Compares numbers or appropriately orderable values. |
| Logical | `AND`, `OR`, `NOT` | Combines or negates conditions. |
| List | `p.city IN ['Hà Nội', 'Đà Nẵng']` | Matches one of the values. |
| String prefix | `p.name STARTS WITH 'A'` | String begins with prefix. |
| String suffix | `p.name ENDS WITH 'ng'` | String ends with suffix. |
| Substring | `p.name CONTAINS 'nh'` | String contains substring. |
| Null check | `p.email IS NULL` | Property has no value (including non-existent properties). |

Example finding people aged 28 or older, living in Hà Nội, and currently active:

```cypher
MATCH (p:Person)
WHERE p.city = 'Hà Nội'
  AND p.age >= 28
  AND p.active = true
RETURN p.id AS id, p.name AS name, p.age AS age;
```

**Result:** `p05` (An, age 30). `p03` also matches city and age but is excluded because `active = false`.

`OR` and `IN` conditions:

```cypher
MATCH (p:Person)
WHERE p.city IN ['Hà Nội', 'Đà Nẵng']
  AND p.age >= 30
RETURN p.id AS id, p.name AS name, p.city AS city
ORDER BY id;
```

**Result:** `p02` (Bình, Đà Nẵng) and `p05` (An, Hà Nội). For longer conditions, use parentheses to clarify intent:

```cypher
MATCH (p:Person)
WHERE (p.city = 'Hà Nội' OR p.city = 'Đà Nẵng')
  AND p.active = true
RETURN p.id AS id
ORDER BY id;
```

The result here is `p01`, `p02`, `p05`.

### 6.2. String Filtering

```cypher
MATCH (p:Person)
WHERE p.name STARTS WITH 'A'
RETURN p.id AS id, p.name AS name
ORDER BY id;
```

The result is `p01` and `p05`. Standard string comparisons are case-sensitive: `STARTS WITH 'a'` is not the same as `STARTS WITH 'A'`.

When business logic requires case-insensitive lookup, you can normalize both sides:

```cypher
MATCH (p:Person)
WHERE toLower(p.name) = toLower($name)
RETURN p.id AS id, p.name AS name;
```

However, calling a function on a property may limit the use of a standard **range index**. For large systems, consider storing an additional normalized property (such as `nameNormalized`) and indexing that property. Case normalization also does not resolve all differences in Vietnamese diacritics or natural-language search rules.

### 6.3. Non-Existent Properties and null

In Neo4j, a node may not contain an `email` property. Reading `p.email` on that node yields `null`; Neo4j does not store a property with a `null` value as an independent property entry.

```cypher
MATCH (p:Person)
WHERE p.email IS NULL
RETURN p.id AS id
ORDER BY id;
```

Because the sample dataset does not declare `email`, the query returns all five `Person` nodes. To find nodes that **have** an `email` value, use `p.email IS NOT NULL`.

Do not write `p.email = null` or `p.email <> null` to check for null. Under Cypher's three-valued logic, those comparisons do not return `true`, so `WHERE` does not keep the corresponding row. Similarly, `WHERE NOT p.active` only selects `false`; a node missing `active` is not automatically treated as `false`.

## 7. Using Parameters Instead of Query String Concatenation

In applications, filter values usually come from users or APIs. Using parameters separates the Cypher statement from input data, making query reuse convenient and avoiding unsafe string concatenation.

```cypher
MATCH (p:Person)
WHERE p.city = $city AND p.age >= $minAge
RETURN p.id AS id, p.name AS name, p.age AS age
ORDER BY age DESC, id ASC;
```

For example, if you pass `city = 'Hà Nội'` and `minAge = 28`, the results in order are `p05` (age 30) and `p03` (age 28).

In the Neo4j Java Driver, values can be passed via a parameter map. The example below assumes `driver` is already configured and uses a Driver API version that supports `executeRead`:

```java
try (var session = driver.session()) {
    var names = session.executeRead(tx ->
        tx.run("""
            MATCH (p:Person)
            WHERE p.city = $city AND p.age >= $minAge
            RETURN p.name AS name
            ORDER BY name
            """, java.util.Map.of("city", "Hà Nội", "minAge", 28))
          .list(record -> record.get("name").asString())
    );
    System.out.println(names); // [An, Chi]
}
```

`$city` and `$minAge` are **value parameters**. Labels and property names belong to the query structure and must be controlled separately when building dynamic queries; whether they can be parameterized depends on the Cypher syntax and version in use. In Spring Data Neo4j, the same principle applies when writing `@Query` methods with parameter binding.

## 8. Selecting and Sorting Results

`RETURN` can return the entire node (`RETURN p`) or only the required properties (`RETURN p.id, p.name`). In APIs, selecting only the needed columns usually reduces transferred data.

```cypher
MATCH (p:Person)
WHERE p.active = true
RETURN p.id AS id, p.name AS name, p.age AS age
ORDER BY age DESC, id ASC
LIMIT 3;
```

Result with the sample dataset:

| id | name | age |
| --- | --- | ---: |
| p04 | Dũng | 35 |
| p02 | Bình | 31 |
| p05 | An | 30 |

Commonly used clauses alongside `RETURN`:

- `ORDER BY` sorts results, ascending by default; `DESC` sorts descending.
- `LIMIT n` takes at most `n` rows. Without `ORDER BY`, **do not assume** which rows will be returned first.
- `SKIP n` skips `n` rows after sorting, suitable for simple pagination; for very large datasets, consider keyset pagination on a stable key.
- `count(p)` counts matching node rows `p`; `count(DISTINCT p)` is useful when relationship patterns can produce multiple rows for the same node.

Example counting people in Hà Nội:

```cypher
MATCH (p:Person {city: 'Hà Nội'})
RETURN count(p) AS total;
```

**Result:** `total = 3`.

## 9. Performance: Labels, Indexes, and Query Plans

In a small database, a query can be fast even without an index. When the number of nodes grows large, lookups on high-selectivity properties (such as `id`) typically benefit from an index.

On a **test database**, you can create an index and a constraint as follows:

```cypher
CREATE RANGE INDEX person_city_idx IF NOT EXISTS
FOR (p:Person) ON (p.city);
```

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.id IS UNIQUE;
```

The uniqueness constraint on `Person.id` both supports identifier-based lookups and prevents `Person` nodes from sharing the same `id` value (for nodes that have `id`). Creating the constraint will fail if existing data already violates uniqueness.

To inspect how Neo4j plans to execute a query:

```cypher
EXPLAIN
MATCH (p:Person {id: 'p05'})
RETURN p.name AS name;
```

`EXPLAIN` generates the plan **without executing** the query; `PROFILE` executes it and adds actual runtime statistics for performance evaluation. Depending on the version, node count, statistics, and existing indexes, the plan may use a label scan or an index seek. Do not assume that every `MATCH` automatically uses an index.

A few guidelines:

1. Specify the target label, such as `(p:Person)`, instead of scanning all nodes with `(p)` when unnecessary.
2. Create indexes or constraints on frequently queried properties, especially unique identifiers.
3. Use parameters and filter early; return only the properties you need.
4. Check the query plan and actual data before concluding which index is effective. Expressions that transform properties (such as `toLower(p.name)`) or substring searches do not have the same optimization capabilities as direct comparisons on a standard index.

## 10. From Finding Nodes to Finding Relationships

Once you master `MATCH` with labels and properties, you can extend the pattern to traverse relationships in the property graph:

```cypher
MATCH (p:Person {id: $personId})-[:WORKS_AT]->(c:Company)
RETURN p.name AS person, c.name AS company;
```

This query only returns results if the database has a matching `WORKS_AT` relationship; the sample dataset above has **not yet created** `Company` nodes or relationships, so it returns no rows. The example shows that `(p:Person {id: $personId})` remains a node lookup by label/property, extended with a relationship pattern.

## 11. Common Mistakes

| Symptom | Cause to Check | How to Fix |
| --- | --- | --- |
| No nodes returned | Wrong case in label, property name, or string value. | Check `:Person`, `p.name`, and actual values. |
| More results than expected | Filter property is not unique, such as two people named An. | Use `id` and a uniqueness constraint if business logic requires it. |
| Cannot find missing properties | Comparing `= null` instead of `IS NULL`. | Use `IS NULL` or `IS NOT NULL`. |
| `LIMIT` returns varying rows | Missing `ORDER BY` to define order. | Sort by a stable property, adding `id` as a tie-breaker. |
| Slow query on large data | Missing appropriate label, index, or low-selectivity filter. | Check `EXPLAIN`/`PROFILE`, then inspect indexes and filter expressions. |
| Application errors when building Cypher | Concatenating input strings, wrong parameter type, or invalid dynamic property name. | Bind parameters for values and validate query structure. |

## 12. Practice Exercises

Use the `Person` dataset from Section 3. Write your own queries before checking the hints.

**Exercise 1.** Find `id` and `name` of people aged 30 or older, sorted by age descending, then `id` ascending.

**Exercise 2.** Find people who have the `Employee` label and live in Hà Nội.

**Exercise 3.** Count active people (`active = true`) in Hà Nội.

**Exercise 4.** Find the exact person with `id = 'p03'` using parameter `$id`. How many rows do you expect if `id` is unique?

<details>
<summary>Suggested Answers and Expected Results</summary>

**Exercise 1**

```cypher
MATCH (p:Person)
WHERE p.age >= 30
RETURN p.id AS id, p.name AS name, p.age AS age
ORDER BY age DESC, id ASC;
```

Result: `p04`, `p02`, `p05`.

**Exercise 2**

```cypher
MATCH (p:Person:Employee {city: 'Hà Nội'})
RETURN p.id AS id, p.name AS name
ORDER BY id;
```

Result: `p01` and `p03`.

**Exercise 3**

```cypher
MATCH (p:Person)
WHERE p.active = true AND p.city = 'Hà Nội'
RETURN count(p) AS total;
```

Result: `total = 2`.

**Exercise 4**

```cypher
MATCH (p:Person {id: $id})
RETURN p.id AS id, p.name AS name;
```

With `id = 'p03'`, the result is one row `p03` (Chi), if the `id` property is unique.

</details>

## 13. Key Takeaways

- `MATCH (n:Label)` finds nodes with a label; `MATCH (n:Label {key: value})` combines equality conditions on properties.
- `WHERE` expresses flexible conditions with numbers, strings, booleans, `IN`, and `IS NULL` checks.
- Common names or properties can yield multiple results; use a unique identifier when you want to pinpoint a single node.
- Always use parameters for application input values, sort before limiting/paginating, and measure performance with query plans.
- These operations are the basic building blocks for querying relationships, paths, and implementing graph data with Neo4j and Cypher.
