# Query Parameters and Distinguishing Input Data from Statement Structure in Cypher

> **Chapter:** Cypher Basics  
> **Scope:** Neo4j uses the *property graph* model to store nodes, relationships, and properties. This lesson explains how to pass input data into a Cypher query using **query parameters**, distinguish parameters from pattern variables, and draw the boundary between **data values** and **statement structure**. This knowledge applies directly when using Neo4j Browser, the Java Driver, and Spring Data Neo4j.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the meaning of the `$tenThamSo` syntax and how values are supplied from outside the query.
2. Distinguish **Cypher variables**, **parameters**, **labels**, **relationship types**, **property keys**, and **literal values**.
3. Pass string, numeric, boolean, `null`, list, map, and temporal parameters into query conditions.
4. Write reusable queries instead of concatenating strings containing user values.
5. Understand why parameterization reduces *Cypher injection* risk and typically aids query plan reuse.
6. Identify which parts of Cypher structure cannot be replaced by an ordinary parameter, and recognize version-dependent dynamic syntax.
7. Use parameters in reads, updates, multi-record imports, pagination, and Java application integration.
8. Diagnose errors from missing parameters, mismatched names, type mismatches, passing `null`, and conditions returning no results.

## 2. The Problem: Fixed Query Structure, Changing Input Data

Suppose an application needs to look up a person's information by ID. First it looks up An, next it looks up Bình. The two requests differ only in the **ID value**, while the business logic and graph structure remain unchanged.

Written with a literal:

```cypher
MATCH (p:Person {id: 'p1'})
RETURN p.name AS ten;
```

Next time, `'p1'` must be changed to `'p2'`. When an application concatenates strings from user input to construct queries, controlling data types, special characters, and security becomes much harder.

Written with a parameter:

```cypher
MATCH (p:Person {id: $personId})
RETURN p.name AS ten;
```

The query **stays the same**, while the caller sends the value separately:

```json
{
  "personId": "p1"
}
```

or:

```json
{
  "personId": "p2"
}
```

Here `$personId` is a **placeholder referencing bound input data**. The `$` sign precedes the parameter name; the name `personId` must match the key passed by the caller.

In an application model, you can picture it as:

```text
Fixed Cypher code:
MATCH (p:Person {id: $personId}) RETURN p.name
                │
                ▼
Parameters sent by application:
{ personId: "p1" }
                │
                ▼
Neo4j evaluates the id condition with value "p1"
                │
                ▼
Result record: { name: "An" }
```

**Core point:** a parameter holds a **data value**. It is not a snippet of Cypher text that Neo4j pastes into the statement and re-parses as syntax.

## 3. Six Concepts Commonly Confused with One Another

Consider the pattern:

```cypher
MATCH (p:Person)-[r:WORKS_ON]->(pr:Project)
WHERE p.id = $personId AND r.role = $role
RETURN p.name AS ten, pr.name AS duAn;
```

| Component | Kind | Meaning |
|---|---|---|
| `p`, `r`, `pr` | **Cypher variable** | Bound to nodes/relationships for each row of the query. |
| `$personId`, `$role` | **Parameter** | Values passed by the caller, such as `'p1'` and `'lead'`. |
| `Person`, `Project` | **Node label** | Node label filter condition, appearing after `:` inside `(...)`. |
| `WORKS_ON` | **Relationship type** | Edge type to match inside `[...]`. |
| `id`, `role`, `name` | **Property key** | Name of the accessed property, e.g., `p.id`, `r.role`. |
| `'lead'`, `25`, `true` | **Literal** | A value written directly in the query text. |

Important distinctions:

- `p` is a **variable**, not a parameter; `$p` is a **parameter named p**, not a pointer to the node bound to variable `p`.
- `Person` in `(p:Person)` is a label; `Person` in `(Person)` is a **variable name**, because `:` is missing.
- `$personId` is input data; `personId` without `$` is interpreted according to in-query identifier rules and does not automatically read the parameter.
- `p.name` reads the `name` property of the node referenced by `p`; `$name` reads the **parameter** named `name`.
- `AS ten` creates an intermediate result column/variable name, not a parameter `$ten`.

### 3.1. Variables Exist by Scope; Parameters Are Available for the Entire Execution

```cypher
MATCH (p:Person {id: $personId})
WITH p.name AS ten
RETURN ten;
```

Variable `p` is introduced via `MATCH` and then **disappears after `WITH`** because only `ten` is forwarded. By contrast, parameter `$personId` is part of the input set for the query execution; it is not an intermediate table column and does not need to be passed through `WITH` to remain usable in valid expressions downstream.

Example:

```cypher
MATCH (p:Person {id: $personId})
WITH p.name AS ten
RETURN ten, $personId AS idDaTim;
```

This query is valid even though variable `p` has left scope. The value of `$personId` comes from the parameter map, not from variable `p`.

## 4. Preparing the Practice Neo4j Dataset

Run the following block in a **separate practice database**. The sample uses IDs prefixed with `c005-` to avoid mixing with other examples. `MERGE` searches for a pattern before creating it, though in a real system an appropriate uniqueness constraint should still be designed if IDs must remain unique under concurrent load.

```cypher
MERGE (an:Person {id: 'c005-an'})
SET an.name = 'An', an.age = 30,
    an.city = 'Hà Nội', an.active = true

MERGE (binh:Person {id: 'c005-binh'})
SET binh.name = 'Bình', binh.age = 27,
    binh.city = 'TP. Hồ Chí Minh', binh.active = true

MERGE (chi:Person {id: 'c005-chi'})
SET chi.name = 'Chi', chi.age = 35,
    chi.city = 'Hà Nội', chi.active = false

MERGE (dung:Person {id: 'c005-dung'})
SET dung.name = 'Dũng', dung.age = 24,
    dung.city = 'Đà Nẵng', dung.active = true

MERGE (api:Project {id: 'c005-api'})
SET api.name = 'Graph API', api.status = 'active'

MERGE (pipeline:Project {id: 'c005-pipeline'})
SET pipeline.name = 'Data Pipeline', pipeline.status = 'planned'

MERGE (an)-[lead:WORKS_ON]->(api)
SET lead.role = 'lead'
MERGE (binh)-[dev:WORKS_ON]->(api)
SET dev.role = 'developer'
MERGE (chi)-[advisor:WORKS_ON]->(pipeline)
SET advisor.role = 'advisor';
```

Diagram:

```text
(An:Person, 30, Hà Nội) ─[WORKS_ON {role:lead}]───────> (Graph API:Project)
(Bình:Person, 27, TP.HCM) ─[WORKS_ON {role:developer}]─> (Graph API:Project)
(Chi:Person, 35, Hà Nội) ─[WORKS_ON {role:advisor}]────> (Data Pipeline:Project)
(Dũng:Person, 24, Đà Nẵng)      (not yet on a project)
```

The expected row counts in this lesson are accurate only when the sample nodes have unique IDs and no extra relationships have been added. If the database already holds other data, keep the ID filters rather than running an unfiltered `MATCH (p:Person)`.

## 5. Syntax and How Parameters Are Supplied

Basic reference syntax:

```cypher
WHERE p.id = $personId
```

The query author chooses the parameter name, such as `personId`; the caller supplies a **parameter map** with matching keys and appropriately typed values:

```json
{
  "personId": "c005-an"
}
```

Example query with **two** parameters:

```cypher
MATCH (p:Person)
WHERE p.age >= $minAge AND p.city = $city
RETURN p.name AS ten, p.age AS tuoi
ORDER BY ten;
```

Input values:

```json
{
  "minAge": 25,
  "city": "Hà Nội"
}
```

On the sample data, the result is **An (30)** and **Chi (35)**. The query does not need editing when changing `city` to another city.

### 5.1. Where Are Parameters Configured?

Depending on the tool, values are provided in different ways:

- **Neo4j Browser / cypher-shell:** set parameters using a tool command, then run the Cypher statement.
- **Java Driver:** pass a parameter map into the query execution API.
- **Spring Data Neo4j:** declare parameters on the repository method or query invocation method.

For example, a Neo4j Browser command may use the form:

```text
:param personId => 'c005-an'
```

Then run:

```cypher
MATCH (p:Person {id: $personId})
RETURN p.name AS ten;
```

Note: the `:param` command belongs to the **client tool interface**, not to Cypher clauses placed in a Java Driver query string. Parameter-setting commands vary across client tools and versions; what stays invariant is that the caller must supply a value for `$personId`.

### 5.2. Parameter Names Must Match Exactly

`$personId` differs from `$personID` because names are case-sensitive. If a query expects `$personId` and the caller sends only the key `id`, the query fails with a **missing parameter** error; Neo4j does not guess parameter names from context.

A `null` value and an **omitted parameter** are two different cases:

- `{personId: null}`: the parameter **is present**, carrying the value `null`.
- `{}`: the key `personId` is completely absent; the query still requires that key.

Therefore, for optional parameters, the caller must pass **the key with value `null`** or select a different query that does not reference that parameter.

## 6. Parameters for Common Data Types

### 6.1. Strings, Numbers, and Booleans

```cypher
MATCH (p:Person)
WHERE p.id IN $personIds
  AND p.age >= $minAge
  AND p.active = $isActive
RETURN p.name AS ten, p.age AS tuoi
ORDER BY tuoi DESC;
```

Parameter set:

```json
{
  "personIds": ["c005-an", "c005-binh", "c005-chi", "c005-dung"],
  "minAge": 25,
  "isActive": true
}
```

Result: An (30), Bình (27). Chi is old enough but has `active = false`; Dũng has `age = 24`.

**Watch data types:** the number `25` is not the same as the string `"25"`; the boolean `true` is not the same as the string `"true"`. Pass the proper type from your API rather than expecting Neo4j to coerce types automatically. When explicit conversion is needed, use Cypher functions such as `toInteger(...)` after validating the input.

### 6.2. Lists and the `IN` Operator

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
RETURN p.name AS ten
ORDER BY ten;
```

Parameter:

```json
{
  "ids": ["c005-an", "c005-chi"]
}
```

Result: An and Chi.

If `ids = []`, the expression `p.id IN $ids` matches no nodes. Do not write `IN [$ids]` when `$ids` is already a list: the outer brackets create **a list containing a list**, rather than the intended list of values.

### 6.3. Maps for Filters or Update Payloads

A parameter can contain a map:

```json
{
  "filter": {
    "city": "Hà Nội",
    "minAge": 25
  }
}
```

Query:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c005-an', 'c005-binh', 'c005-chi', 'c005-dung']
  AND p.city = $filter.city
  AND p.age >= $filter.minAge
RETURN p.name AS ten
ORDER BY ten;
```

`$filter` is **a map parameter**; `$filter.city` reads the value of the `city` key inside that map. It differs from `p.city`: the left-hand side reads a node property, while the right-hand side reads an input value.

Example of updating properties on a node:

```cypher
MATCH (p:Person {id: $personId})
SET p += $changes
RETURN p.id AS id, properties(p) AS thuocTinh;
```

Parameter map:

```json
{
  "personId": "c005-an",
  "changes": {
    "city": "Đà Nẵng",
    "active": true
  }
}
```

`SET p += $changes` updates or adds the specified properties while keeping all other properties intact. If a value inside the map is `null`, the update can remove the corresponding property. **Allow only keys permitted by the application**: parameterization protects query syntax, but it does not stop users from requesting changes to sensitive or unauthorized properties. This example mutates data, so run it only on a practice database.

### 6.4. Temporal Types

If the caller sends a date as an ISO string, you can convert it to Cypher's `Date` type:

```cypher
WITH date($startDate) AS batDau
RETURN batDau, batDau + duration({days: 7}) AS sauMotTuan;
```

Parameter:

```json
{
  "startDate": "2026-11-25"
}
```

The `$startDate` value is supplied externally. The `date(...)` function defines the data type semantics, while `duration({days: 7})` is a fixed structural part of the expression. The Java Driver can also send certain temporal types directly; choose the type that matches how properties are modeled in Neo4j.

## 7. `null` and Optional Filters

`null` is a special value, not equivalent to the string `"null"` or an empty list `[]`.

### 7.1. Comparing with `null` Is Not the Same as Checking `IS NULL`

```cypher
MATCH (p:Person {id: 'c005-an'})
WHERE p.city = $city
RETURN p.name AS ten;
```

If `{city: null}` is passed, `p.city = null` does not evaluate to `true`, so no rows match. To check for missing values, use `IS NULL` or `IS NOT NULL` as appropriate.

### 7.2. Optional City Filter Pattern

Requirement: if `$city` has a value, filter by city; if `$city = null`, skip the city condition.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c005-an', 'c005-binh', 'c005-chi', 'c005-dung']
  AND ($city IS NULL OR p.city = $city)
RETURN p.name AS ten, p.city AS thanhPho
ORDER BY ten;
```

- When `city = "Hà Nội"`: An, Chi.
- When `city = null`: all four people.
- When **the `city` key is not sent**: it does not default to `null`; the key must be provided or a different query used.

`OR` expressions can affect how the optimizer exploits indexes in some situations. For large datasets or many optional filters, it may be necessary to design separate fixed query variants and measure them with `EXPLAIN`/`PROFILE`.

### 7.3. Default Values vs. "Parameter Not Sent"

```cypher
WITH coalesce($minAge, 0) AS tuoiToiThieu
MATCH (p:Person)
WHERE p.id IN ['c005-an', 'c005-binh', 'c005-chi', 'c005-dung']
  AND p.age >= tuoiToiThieu
RETURN p.name AS ten;
```

`coalesce` picks the first non-`null` value. However, for this expression to work when no minimum age is supplied, the caller still needs to **pass the `minAge` key with value `null`**. Omitting the key altogether is not automatically handled by `coalesce`.

## 8. Distinguishing Input Data from Statement Structure

This is the central focus of the lesson. A Cypher statement has **query structure**, including clauses, node–relationship patterns, label/type names, property keys, and sort ordering. Ordinary parameters only carry values in **data expression positions** allowed by the syntax.

Consider these examples:

| Intent | How Written | Validity / Meaning |
|---|---|---|
| Dynamic ID filter | `WHERE p.id = $id` | Valid: `$id` is a value. |
| Dynamic age filter | `WHERE p.age >= $minAge` | Valid: `$minAge` is a number. |
| Filter multiple IDs | `WHERE p.id IN $ids` | Valid if `$ids` is an appropriate list. |
| Read dynamically selected property | `RETURN p[$propertyKey]` | Dynamic property access expression can be used in versions supporting this syntax. |
| Replace entire `MATCH` clause | `$clause (p:Person)` | Invalid: parameters are not Cypher keywords. |
| Replace pattern with a string | `MATCH $pattern` | Invalid: an input string is not re-parsed into a graph pattern. |
| Use value as static label | `MATCH (p:$label)` | Not valid static label parameterization syntax. |
| Use string as sort column list | `ORDER BY $sortBy` | Does not turn the string `"p.name"` into property expression `p.name`. |

### 8.1. Passing a String Does Not Mean Passing Cypher Code

Suppose `$pattern` has the value:

```json
{
  "pattern": "(p:Person)-[:WORKS_ON]->(pr:Project)"
}
```

Neo4j treats it as a **text string**, and does not automatically use that string as the right-hand side of `MATCH`. To check a relationship, you must write a **syntactically valid graph pattern directly in the query**:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id = $personId
RETURN pr.name AS duAn;
```

### 8.2. Dynamic Property Keys and Control Boundaries

In read queries, you can select a property by key name:

```cypher
MATCH (p:Person {id: $personId})
RETURN p[$propertyKey] AS giaTri;
```

Parameters:

```json
{
  "personId": "c005-an",
  "propertyKey": "city"
}
```

`p[$propertyKey]` is a **dynamic property access expression**; the result is the city name string. It differs from placing `$propertyKey` in the middle of a statement where only a static identifier is accepted. The application still needs an **allowlist** of readable keys—such as `name`, `city`, `age`—because a syntactically valid query does not mean every property should be exposed.

### 8.3. Dynamic Labels and Relationship Types Depend on Cypher Version

In basic usage:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
RETURN p, pr;
```

`Person`, `WORKS_ON`, and `Project` are **structural tokens**, not positions that accept parameters via text substitution. Therefore, writing `(p:$label)` or `-[:$type]->` is not standard parameterization.

**Version note:** Neo4j starting from **5.26** provides dedicated syntax for *dynamic labels* and *dynamic relationship types* in supported contexts. For example, on a supporting version:

```cypher
MATCH (n:$($label))
RETURN n
LIMIT 10;
```

With parameter `{label: "Person"}`, the dynamic expression `$($label)` is evaluated according to the corresponding Cypher syntax rules. This is **not** a "query string concatenation" feature; it is **an explicit Cypher language construct**. Support, index optimization, and allowed contexts for dynamic syntax vary by Neo4j/Cypher version. When writing queries meant to run across multiple versions, check the relevant documentation and use static labels/types when appropriate.

When business logic allows only specific labels/types, enforce an explicit allowlist—for example accepting only `Person` or `Project`—and validate access rights. Dynamic syntax does not replace input validation or authorization.

### 8.4. Sorting Requested by the UI

Value parameter:

```cypher
MATCH (p:Person)
WHERE p.id IN $ids AND p.age >= $minAge
RETURN p.name AS ten, p.age AS tuoi
ORDER BY tuoi DESC;
```

Here `$minAge` is data, whereas `tuoi DESC` is a **predefined** sort order. If the UI lets users choose between sorting by name or age, two clear options are:

1. Choose one of **several fixed query templates** pre-approved by the application.
2. Use a **`CASE` expression** inside `ORDER BY` when there is a finite set of options, ensuring all branches have compatible comparison types.

Do not take `"p.name DESC"` from a request and interpolate it verbatim into Cypher. Passing such a string as a parameter does not sort by the described expression either.

## 9. Why Does Parameterization Reduce Cypher Injection?

Suppose a Java application constructs a statement manually:

```java
// UNSAFE: name comes from user
String query =
    "MATCH (p:Person) WHERE p.name = '" + userName + "' RETURN p";
```

When `userName` contains quotes or characters with special meaning in Cypher, the query text can change semantics or fail to parse. If the input is controlled by an attacker, this poses a **Cypher injection** risk.

Replace with a parameterized query:

```java
String query = """
    MATCH (p:Person)
    WHERE p.name = $name
    RETURN p
    """;

Map<String, Object> params = Map.of("name", userName);
```

In this case, `userName` is transmitted as a **string value**. Quote characters in the name do not act as opening/closing quotes in Cypher syntax. The value is processed strictly as data compared against property `p.name`.

**However, parameterization does not make every action safe by itself:** the system must still enforce which nodes a user can view, which properties they can read/modify, which query types they may run, and what result limits apply. In particular, parameterization **does not protect** any part of query structure built by string concatenation outside the parameter mechanism.

## 10. Query Plans and Performance

Neo4j builds an execution plan from the Cypher statement and conditions that can leverage indexes or constraints. When only input values change, parameters **keep the query text identical**, giving the database engine an opportunity to reuse cached plans.

Two runs example:

```cypher
MATCH (p:Person {id: $personId})
RETURN p.name AS ten;
```

Run 1: `personId = "c005-an"`. Run 2: `personId = "c005-binh"`. The structure of the ID-matching expression does not change.

However:

- Parameterization **does not create indexes automatically**. If you frequently look up by `Person.id`, evaluate adding an index or uniqueness constraint on that property.
- Not all runs with the same query text have equal cost: parameter values may match very different numbers of nodes/relationships.
- Plan caching behavior, operator selection, and optimization strategies can vary by Neo4j version.
- Parameterization cannot fix faulty pattern joins that create Cartesian products or inflate row counts when a node matches many relationships.

You can inspect the estimated plan:

```cypher
EXPLAIN
MATCH (p:Person {id: $personId})
RETURN p.name AS ten;
```

When executing in Neo4j Browser or a Driver, you still must **supply the `personId` parameter**. Use `PROFILE` if you need actual row counts and runtime statistics; remember that `PROFILE` executes the query, including write queries.

## 11. Complete Read Example Using Parameters

**Requirement:** find active people at or above a minimum age within a selected list of IDs; return name, age, and city.

```cypher
MATCH (p:Person)
WHERE p.id IN $personIds
  AND p.active = $active
  AND p.age >= $minAge
RETURN p.id AS id,
       p.name AS ten,
       p.age AS tuoi,
       p.city AS thanhPho
ORDER BY tuoi DESC, id ASC;
```

Input:

```json
{
  "personIds": ["c005-an", "c005-binh", "c005-chi", "c005-dung"],
  "active": true,
  "minAge": 26
}
```

Expected result:

| id | ten | tuoi | thanhPho |
|---|---|---:|---|
| c005-an | An | 30 | Hà Nội |
| c005-binh | Bình | 27 | TP. Hồ Chí Minh |

Flow explanation:

1. `MATCH` selects candidate `Person` nodes.
2. `$personIds` is a **list** used with the `IN` operator.
3. `$active` is a **boolean** compared against property `p.active`.
4. `$minAge` is a **number** compared against `p.age`.
5. `RETURN` selects columns; `ORDER BY` specifies deterministic output ordering.

Changing `minAge` to `31` yields **0 rows** without modifying the Cypher query text.

## 12. Writing Data with Parameters: `MERGE`, `SET`, and Record Lists

### 12.1. Finding or Creating a Node by Business ID

```cypher
MERGE (p:Person {id: $personId})
ON CREATE SET p.name = $name, p.age = $age
ON MATCH SET p.name = $name
RETURN p.id AS id, p.name AS ten, p.age AS tuoi;
```

Input:

```json
{
  "personId": "c005-lan",
  "name": "Lan",
  "age": 29
}
```

`MERGE` checks for a node with label `Person` and `id` matching the parameter. `ON CREATE SET` runs only if the node is newly created; `ON MATCH SET` runs if it already matched. Using the business ID as the primary match key separates node identity from mutable properties like name or age.

To guarantee ID uniqueness under concurrent transactions, design an appropriate uniqueness constraint. `MERGE` alone is not a substitute for that constraint.

### 12.2. Creating or Updating a Relationship by Two IDs

```cypher
MATCH (p:Person {id: $personId})
MATCH (pr:Project {id: $projectId})
MERGE (p)-[w:WORKS_ON]->(pr)
SET w.role = $role
RETURN p.name AS nguoi, pr.name AS duAn, w.role AS vaiTro;
```

Input:

```json
{
  "personId": "c005-dung",
  "projectId": "c005-api",
  "role": "tester"
}
```

Here `Person`, `Project`, and `WORKS_ON` are query structure defined by the application; the three parameters supply **values** to locate nodes and set a property. Using `MATCH` to bind both nodes before `MERGE`ing the relationship avoids accidentally creating unwanted extra nodes.

This snippet modifies the practice data: after running it, Dũng will have a `WORKS_ON` relationship, so earlier examples assuming Dũng has no projects will no longer hold. You can use a separate practice database for each group of examples or reset the dataset to its initial state.

### 12.3. Importing a List with `UNWIND`

An application can pass **a single list parameter containing multiple maps** to repeat an operation following the same pattern:

```cypher
UNWIND $rows AS row
MERGE (p:Person {id: row.id})
SET p.name = row.name,
    p.age = row.age
RETURN count(p) AS soBanGhiXuLy;
```

Example input:

```json
{
  "rows": [
    {"id": "c005-e1", "name": "Hà", "age": 28},
    {"id": "c005-e2", "name": "Minh", "age": 31}
  ]
}
```

`UNWIND` turns the list into intermediate rows `row`. Dot notation `row.id` reads a field from each row's map; it is not a query generated from strings. With this input, `count(p)` in the example returns `2`, reflecting the **number of rows processed**, not necessarily the number of newly created nodes if the IDs already existed.

For large volumes of data, batch appropriately and consider transactions, constraints, and memory limits; avoid sending huge datasets all at once inside a single list parameter by default.

## 13. Passing Parameters from the Neo4j Java Driver

The Java Driver executes query text alongside a parameter structure. The simple example below illustrates passing values via a `Map`:

```java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;

import java.util.List;
import java.util.Map;

public class PersonLookup {
    public static void main(String[] args) {
        // Connection values are supplied from actual environment configuration.
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");

        String cypher = """
                MATCH (p:Person)
                WHERE p.id IN $ids AND p.age >= $minAge
                RETURN p.name AS ten
                ORDER BY ten
                """;

        Map<String, Object> params = Map.of(
                "ids", List.of("c005-an", "c005-binh", "c005-chi"),
                "minAge", 28
        );

        try (Driver driver = GraphDatabase.driver(
                     uri, AuthTokens.basic(username, password));
             Session session = driver.session()) {
            List<String> names = session.run(cypher, params)
                    .list(record -> record.get("ten").asString());
            names.forEach(System.out::println);
        }
    }
}
```

When run on the sample data, the printed list is **An** and **Chi**. Although the input includes three IDs, Bình is 27 and is filtered out by `minAge = 28`.

Points to note:

- `session.run(cypher, params)` accepts **Cypher text** and a **parameter map** separately.
- The map key `"ids"` corresponds to `$ids`; the key `"minAge"` corresponds to `$minAge`.
- `record.get("ten")` retrieves the result column `ten` produced by `RETURN ... AS ten`, **not** a parameter.
- Java's `Map.of(...)` does not allow `null` values. If an optional parameter must be `null`, use a `Map` that allows nulls or an appropriate parameter-building API.
- Never hardcode URIs, passwords, or sensitive credentials in source code; the example reads configuration from environment variables to emphasize this separation.
- In production applications, choose the database, Driver/Session lifecycle management, transactions, and timeouts to fit the application lifecycle; the code snippet above only illustrates **parameter passing**.

### 13.1. Type Mismatches in Java Can Cause No Matches or Errors

Example:

```java
// Wrong intent when age is an integer: passing string "28"
Map<String, Object> wrong = Map.of("minAge", "28");

// Correct: numeric value
Map<String, Object> correct = Map.of("minAge", 28);
```

Do not rely on Neo4j automatically interpreting strings as numbers for comparison. APIs should validate input types before building the parameter map.

## 14. Parameters in Spring Data Neo4j

In Spring Data Neo4j, a repository can use `@Query` with named parameters. The conceptual example below assumes the application already has a `Person` entity properly mapped to the `Person` label and ID field:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;
import java.util.List;

public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    @Query("""
           MATCH (p:Person)
           WHERE p.city = $city AND p.age >= $minAge
           RETURN p
           """)
    List<Person> findInCityFromAge(
            @Param("city") String city,
            @Param("minAge") int minAge);
}
```

Distinctions to keep clear:

- `@Query` defines the **Cypher structure** containing the `Person` node pattern and filter conditions.
- `@Param("city")` and `@Param("minAge")` bind the Java method arguments to `$city` and `$minAge`.
- `RETURN p` returns the **node** for the entity mapping mechanism to process. If returning scalars or projections, design the return type accordingly.
- How IDs, relationships, entities, DTOs, and transactions are mapped depends on your application's Spring Data Neo4j configuration; this example only illustrates parameters and does not replace full repository design.

In real applications, framework-derived query methods can also be used when suitable. Whether using `@Query` or derived repository methods, keep user data as **parameter values**.

## 15. Pagination: Data Is Parameterized, Ordering Is Structural

A paginated query can take offset and page size from parameters:

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
RETURN p.id AS id, p.name AS ten, p.age AS tuoi
ORDER BY ten ASC, id ASC
SKIP $offset
LIMIT $pageSize;
```

Input:

```json
{
  "ids": ["c005-an", "c005-binh", "c005-chi", "c005-dung"],
  "offset": 0,
  "pageSize": 2
}
```

The result is at most **the first two rows** ordered by `ten, id`. `offset` and `pageSize` must be appropriate integer values; the application should validate that they are **non-negative** and cap the page size.

Why is `ORDER BY` written statically? Because choosing "sort by name or sort by age" is **changing the sort expression**. Strings like `"p.age DESC"` are not re-evaluated by Neo4j as expressions when passed via `$sortBy`. If the UI allows choosing sort order, select from pre-validated fixed options.

When using `SKIP` across multiple pages, remember that data can change between queries. For large datasets and frequent updates, *keyset pagination* may be a better fit.

## 16. Common Pitfalls Table

| Symptom | Cause | Resolution |
|---|---|---|
| Missing `$personId` error | Map sent `id` instead of `personId`, or omitted the key. | Ensure parameter names match and are always supplied. |
| No results when comparing ID | Passed `"p1"` when node stores `"c005-an"`, or wrong type. | Check the parameter value and type against stored data. |
| `WHERE p.name = '$name'` always compares against literal `$name` | Parameter name placed inside string quotes. | Write `WHERE p.name = $name`. |
| `WHERE p.age >= $minAge` type error or mismatch | Application sent string `"25"` instead of number `25`. | Validate/convert input types before sending. |
| `WHERE p.city = $city` fails to match when `city = null` | Standard equality with null does not evaluate to true. | Design `IS NULL` checks or optional filter conditions. |
| `IN [$ids]` fails to match | `$ids` is already a list and was wrapped in another list. | Write `IN $ids`. |
| `MATCH (p:$label)` fails with syntax error | Ordinary parameters cannot be placed as static labels. | Use a static label or version-supported dynamic label syntax. |
| `ORDER BY $sortBy` does not change sort order | A string parameter does not become a Cypher expression. | Choose from pre-approved sort expressions in the application. |
| `RETURN p` errors after `WITH p.name AS ten` | Variable `p` was not forwarded. | Use `WITH p, p.name AS ten` or use `ten` only. |
| Input containing quotes breaks query | Application concatenated values directly into Cypher text. | Pass values through the parameter API. |
| `Map.of("city", null)` throws in Java | `Map.of` rejects null values. | Use a map implementation that permits nulls when passing null. |
| Unexpected properties written via `SET p += $changes` | Map allowed arbitrary keys. | Enforce an allowlist of updatable properties. |
| One node appears on multiple rows | Node matches multiple relationships; not a parameter bug. | Check granularity, and use `DISTINCT`/aggregation where appropriate. |

## 17. Workflow for Designing Parameterized Queries

For a Neo4j query API, you can follow these steps:

1. **Define the fixed structure.** Example: start from a `Person` node, follow `WORKS_ON` to `Project`, return the project name.
2. **Identify varying data.** Example: person ID, minimum age, project status, list of IDs to filter.
3. **Choose clear parameter names.** Example: `$personId`, `$minAge`, `$status`, `$ids`; avoid single-letter names easily confused with variables.
4. **Declare the data type contract.** `personId: String`, `minAge: Integer`, `ids: List<String>`, `status: String`.
5. **Handle optional conditions.** Distinguish missing keys, `null`, empty strings, and empty lists according to business rules.
6. **Constrain structural choices.** Labels, types, sort columns, and readable/writable properties must be validated against an allowlist; use dynamic syntax only if supported by your version.
7. **Test with multiple value sets.** Check normal inputs, non-matching inputs, wrong types, `null`, special characters, and empty lists.
8. **Observe performance when needed.** Use `EXPLAIN`, `PROFILE`, evaluate indexes/constraints, and inspect intermediate row counts.

Example API contract:

```text
Endpoint: GET /people/projects
Input:
  personId: string (required)
  status: string (required, active or planned only)
Output:
  list of matching project names
```

Cypher query:

```cypher
MATCH (p:Person {id: $personId})-[:WORKS_ON]->(pr:Project)
WHERE pr.status = $status
RETURN pr.id AS id, pr.name AS ten
ORDER BY ten;
```

Example input `{personId: "c005-an", status: "active"}` returns **Graph API**. If `status = "planned"`, the query returns no projects for An in the sample data. **Query structure and access control remain governed by the application**, while data values vary via parameters.

## 18. Self-Practice Exercises

The following exercises use the dataset from Section 4 and assume the write examples adding people/relationships in Section 12 have not been executed.

### Exercise 1. Replacing a Literal with a Parameter

Convert the following query to accept parameter `$id`:

```cypher
MATCH (p:Person {id: 'c005-an'})
RETURN p.name AS ten;
```

<details>
<summary>Reference Answer</summary>

```cypher
MATCH (p:Person {id: $id})
RETURN p.name AS ten;
```

Input: `{"id": "c005-an"}`. Result: **An**.

</details>

### Exercise 2. Passing Two Value Types

Write a query finding people aged `$minAge` or older with `active = $active`, restricted to the four `c005-` IDs. With `minAge = 28` and `active = true`, which names are returned?

<details>
<summary>Reference Answer</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c005-an', 'c005-binh', 'c005-chi', 'c005-dung']
  AND p.age >= $minAge
  AND p.active = $active
RETURN p.name AS ten;
```

Input: `{"minAge": 28, "active": true}`. Result: only **An** (Chi meets the age requirement but has `active = false`).

</details>

### Exercise 3. Lists and the `IN` Operator

The application sends `{"ids": ["c005-binh", "c005-dung"]}`. Write a Cypher query returning the names of those two people without modifying the query whenever the list changes.

<details>
<summary>Reference Answer</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
RETURN p.name AS ten
ORDER BY ten;
```

Result: **Bình, Dũng**. If `ids = []`, the result is empty.

</details>

### Exercise 4. Parameter or Variable?

In the following query, what kind of token are `p`, `Person`, `id`, `$personId`, and `ten`?

```cypher
MATCH (p:Person {id: $personId})
RETURN p.name AS ten;
```

<details>
<summary>Answer</summary>

`p`: node variable. `Person`: label. `id`: property key. `$personId`: parameter passed by the caller. `ten`: return column alias. `name` in `p.name` is also a property key.

</details>

### Exercise 5. Optional Condition with `null`

Write a query allowing the user to pass `city = null` to return all four people, or `city = "Hà Nội"` to return only An and Chi.

<details>
<summary>Reference Answer</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c005-an', 'c005-binh', 'c005-chi', 'c005-dung']
  AND ($city IS NULL OR p.city = $city)
RETURN p.name AS ten
ORDER BY ten;
```

Always supply the `city` key. Omitting the key from the parameter map causes a missing parameter error.

</details>

### Exercise 6. Identifying Where Ordinary Parameters Cannot Be Used

Why is `MATCH (p:$label) RETURN p` not a way to pass a label dynamically like passing an ID? Suggest an approach when only `Person` or `Project` is allowed.

<details>
<summary>Reference Answer</summary>

Labels belong to the graph pattern structure, not an expression position accepting a parameter like `$id`. The application can choose **one of two fixed queries**, each with a static label and parameterized filter values:

```cypher
MATCH (p:Person {id: $id})
RETURN p;
```

or:

```cypher
MATCH (pr:Project {id: $id})
RETURN pr;
```

If the Neo4j version in use supports dedicated dynamic label syntax, that dedicated syntax can be considered while still enforcing an allowlist, access control, and execution-plan checks.

</details>

### Exercise 7. Writing a Project Lookup Query with Parameters

Find a person's projects using `$personId` and filter projects by status `$status`. With input `{"personId": "c005-chi", "status": "planned"}`, what is the expected result?

<details>
<summary>Reference Answer</summary>

```cypher
MATCH (p:Person {id: $personId})-[:WORKS_ON]->(pr:Project)
WHERE pr.status = $status
RETURN pr.name AS duAn;
```

Result: **Data Pipeline**.

</details>

## 19. Key Takeaways

**Cypher parameters** are written as `$ten` and receive values from the caller; **Cypher variables** such as `p`, `r`, and `pr` are bound via query patterns and exist per row within clause scope. Labels, relationship types, property keys, `MATCH`/`WHERE`/`RETURN` syntax, and `ORDER BY` expressions belong to **statement structure**; they are not substituted by parameter strings the way ID or age values are.

When integrating Neo4j via the Java Driver or Spring Data Neo4j, write **deliberate query structures**, pass user data via properly typed parameters, and validate any choices that can affect labels, types, properties, or access rights. This practice keeps queries reusable, lowers injection risk, and creates a solid foundation for tuning with indexes, constraints, and execution plans.
