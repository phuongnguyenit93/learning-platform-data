# Expressions, Operators, Precedence, and Writing Clear Conditions in Cypher

> **Chapter:** Cypher Basics  
> **Context:** Neo4j stores data as a *property graph* consisting of nodes, relationships, and properties. When querying with Cypher, small expressions such as `p.age >= 25`, `pr.status = 'active'`, or `w.role IN $roles` decide which graph patterns are retained. This lesson focuses on expression semantics, operator groups, precedence order, and writing accurate, easy-to-verify conditions.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Recognize **literals, variables, parameters, property accesses, function calls, and aggregate expressions** in Cypher.
2. Correctly use arithmetic, comparison, logical, string, list, and missing-value operators.
3. Understand **three-valued logic** (`true`, `false`, and `null`) and predict which rows `WHERE` retains.
4. Read and write conditions with multiple `AND`, `OR`, `NOT`, and `XOR` operators without mistaking precedence.
5. Use parentheses `(...)` to express condition groups according to exact business requirements.
6. Combine `CASE`, `coalesce`, `IN`, list predicates, and `EXISTS { ... }` in graph problems.
7. Distinguish conditions belonging to `MATCH`, `OPTIONAL MATCH`, or filtering after `WITH`.
8. Know when to pass parameters, standardize data types, and inspect execution plans when query conditions become complex.

## 2. What Is an Expression in Cypher?

An **expression** is a query component that evaluates to a **value**. That value can be a number, string, boolean, `null`, list, map, node, relationship, path, or temporal value.

Examples:

| Expression | Value Type or Role |
|---|---|
| `25` | Integer literal. |
| `'Hà Nội'` | String literal. |
| `true` | Boolean literal. |
| `null` | Missing / unknown value. |
| `p.age` | Accesses property `age` of the node bound to variable `p`. |
| `$minAge` | Parameter supplied by the application. |
| `p.age + 1` | Arithmetic expression. |
| `p.age >= $minAge` | Boolean condition expression, typically yielding `true`, `false`, or `null`. |
| `coalesce(p.city, 'Not updated')` | Function call to replace a `null` value. |
| `[p.name, p.city]` | A list of two elements. |
| `{name: p.name, age: p.age}` | A map containing values computed from variables. |
| `CASE WHEN p.age >= 18 THEN 'adult' ELSE 'minor' END` | Conditional branching expression. |

An expression can appear in many places:

```cypher
MATCH (p:Person)
WHERE p.age >= $minAge
RETURN p.name AS ten, p.age + 1 AS tuoiNamSau
ORDER BY tuoiNamSau DESC;
```

- `MATCH` binds variable `p` through a node pattern.
- `WHERE` uses a conditional expression to filter patterns.
- `RETURN` evaluates expressions into result columns.
- `ORDER BY` sorts by the named expression/column.

**Key rule:** Inside `WHERE`, only rows whose condition evaluates to **`true`** are kept. Both `false` and `null` fail to pass the filter.

## 3. Sample Dataset for Testing Each Condition

The examples use a fixed set of nodes and relationships. Run the following snippet in a **practice database**; IDs carry the `c006-` prefix to avoid colliding with other lessons. `MERGE` searches before creating sample elements, though a production database still needs a uniqueness constraint if business IDs must remain unique across concurrent transactions.

```cypher
MERGE (an:Person {id: 'c006-an'})
SET an.name = 'An', an.age = 30,
    an.city = 'Hà Nội', an.active = true,
    an.score = 92, an.tags = ['graph', 'java']

MERGE (binh:Person {id: 'c006-binh'})
SET binh.name = 'Bình', binh.age = 27,
    binh.city = 'TP. Hồ Chí Minh', binh.active = true,
    binh.score = 77, binh.tags = ['java', 'api']

MERGE (chi:Person {id: 'c006-chi'})
SET chi.name = 'Chi', chi.age = 35,
    chi.city = 'Hà Nội', chi.active = false,
    chi.score = 88, chi.tags = ['graph', 'data']

MERGE (dung:Person {id: 'c006-dung'})
SET dung.name = 'Dũng', dung.age = 24, dung.active = true
REMOVE dung.city, dung.score, dung.tags

MERGE (api:Project {id: 'c006-api'})
SET api.name = 'Graph API', api.status = 'active',
    api.budget = 100

MERGE (reco:Project {id: 'c006-reco'})
SET reco.name = 'Recommendation', reco.status = 'planned',
    reco.budget = 40

MERGE (an)-[wa:WORKS_ON]->(api)
SET wa.role = 'lead', wa.since = 2021
MERGE (an)-[wb:WORKS_ON]->(reco)
SET wb.role = 'reviewer', wb.since = 2024
MERGE (binh)-[wc:WORKS_ON]->(api)
SET wc.role = 'developer', wc.since = 2023
MERGE (chi)-[wd:WORKS_ON]->(reco)
SET wd.role = 'advisor', wd.since = 2022

MERGE (an)-[:KNOWS]->(binh)
MERGE (binh)-[:KNOWS]->(chi);
```

Data summary:

| Person | age | active | city | score | tags |
|---|---:|---|---|---:|---|
| An | 30 | `true` | Hà Nội | 92 | `['graph', 'java']` |
| Bình | 27 | `true` | TP. Hồ Chí Minh | 77 | `['java', 'api']` |
| Chi | 35 | `false` | Hà Nội | 88 | `['graph', 'data']` |
| Dũng | 24 | `true` | No property | No property | No property |

```text
An   ──WORKS_ON {role: lead}─────> Graph API (active, budget:100)
  └──WORKS_ON {role: reviewer}───> Recommendation (planned, budget:40)
Bình ──WORKS_ON {role: developer}─> Graph API
Chi  ──WORKS_ON {role: advisor}───> Recommendation
Dũng   (no WORKS_ON)

An ──KNOWS──> Bình ──KNOWS──> Chi
```

To filter only the people belonging to the sample set when the database contains other data, use:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
RETURN p.name AS ten;
```

The result tables below assume each sample ID corresponds to a single node and no external relationships connect to those nodes.

## 4. Variables, Literals, Parameters, and Data Types

These are the basic building blocks of expressions:

```cypher
MATCH (p:Person)-[w:WORKS_ON]->(pr:Project)
WHERE p.id = $personId
  AND pr.status = 'active'
  AND w.since >= 2020
RETURN p.name, w.role, pr.name;
```

| Component | Explanation |
|---|---|
| `p`, `w`, `pr` | Node/relationship variables bound per row. |
| `Person`, `Project` | Labels; part of the graph pattern structure. |
| `WORKS_ON` | Relationship type; part of the graph pattern structure. |
| `p.id`, `w.since`, `pr.status` | Property access via dot notation. |
| `$personId` | Data parameter, e.g., `'c006-an'`. |
| `'active'`, `2020` | Literals in the query. |
| `=`, `>=`, `AND` | Operators constructing conditions. |

### 4.1. Strings, Numbers, and Booleans Must Have the Right Type

```cypher
RETURN 25 AS so,
       '25' AS chuoi,
       true AS dangHoatDong,
       null AS khongCoGiaTri;
```

`25` is a number, `'25'` is a string. `true` is a boolean, `'true'` is a string. Do not write comparisons across mismatched types expecting Neo4j to coerce them to match application intent.

This example uses a numeric parameter:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.age >= $minAge
RETURN p.name AS ten, p.age AS tuoi;
```

A caller passing `{"minAge": 30}` selects An and Chi. Passing `{"minAge": "30"}` passes a **string** and can result in a type mismatch when comparing against numeric age.

### 4.2. Property Access Can Yield `null`

```cypher
MATCH (p:Person {id: 'c006-dung'})
RETURN p.name AS ten,
       p.city AS thanhPho,
       p.score AS diem;
```

Because Dũng lacks the `city` and `score` properties, those two expressions evaluate to `null`. Neo4j does not store a property with value `null` like an ordinary value; setting a property to `null` is equivalent to removing that property.

## 5. Arithmetic Operators

Common arithmetic operators:

| Operator | Meaning | Example |
|---|---|---|
| `+` | Adds two numbers; has other semantics for strings/lists depending on operand types. | `7 + 3` → `10` |
| `-` | Subtracts two numbers; unary minus can precede numeric expressions. | `7 - 3` → `4` |
| `*` | Multiplication. | `7 * 3` → `21` |
| `/` | Division. | `8 / 2` → `4` |
| `%` | Modulo (remainder). | `10 % 3` → `1` |
| `^` | Exponentiation. | `2 ^ 3` → `8` |

An arithmetic expression on properties:

```cypher
MATCH (p:Person {id: 'c006-an'})
RETURN p.name AS ten,
       p.age AS tuoiHienTai,
       p.age + 1 AS tuoiNamSau,
       p.score * 2 AS diemNhanDoi;
```

For An, `tuoiNamSau = 31` and `diemNhanDoi = 184`.

### 5.1. Arithmetic Precedence

In standard arithmetic operations, multiplication/division/modulo have higher precedence than addition/subtraction:

```cypher
RETURN 2 + 3 * 4 AS ketQuaKhongNgoac,
       (2 + 3) * 4 AS ketQuaCoNgoac;
```

The results are `14` and `20`.

Exponentiation `^` is evaluated with higher precedence than ordinary addition/subtraction; if an expression also includes unary minus, group explicitly with parentheses to avoid misreading:

```cypher
RETURN (2 ^ 3) + 1 AS giaTri,   // 9
       -(2 ^ 2) AS amBon,       // -4
       (-2) ^ 2 AS duongBon;    // 4
```

**Writing tip:** Grouping parentheses carry business meaning, not just operator precedence. For instance, if a calculation depends on `p.score` and a multiplier, add parentheses even when precedence could be deduced from memory.

### 5.2. Division by Zero and Missing Values

Do not assume an expression dividing by 0 will always return a useful result. When the denominator comes from data and may equal 0, state the handling explicitly:

```cypher
WITH 100.0 AS total, 0.0 AS divisor
RETURN CASE
         WHEN divisor = 0 THEN null
         ELSE total / divisor
       END AS tyLe;
```

Here `tyLe = null` according to the **business rule we defined**, without relying on division-by-zero error behavior. When the denominator can be `null`, also check `divisor IS NULL` if you need to distinguish the cause.

## 6. Comparison Operators and Range Conditions

| Operator | Meaning |
|---|---|
| `=` | Equality comparison. |
| `<>` | Inequality comparison. |
| `<`, `<=` | Less than, less than or equal to. |
| `>`, `>=` | Greater than, greater than or equal to. |
| `IS NULL` | Checks whether an expression is `null`. |
| `IS NOT NULL` | Checks whether an expression is not `null`. |

Example: retrieve people aged 25 to 32, inclusive:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.age >= 25
  AND p.age <= 32
RETURN p.name AS ten, p.age AS tuoi
ORDER BY tuoi DESC;
```

Result: An (30), Bình (27). A range condition is expressed using **two comparisons** joined with `AND`.

### 6.1. Conditions Must Be Explicit About Boundaries

Suppose the requirement is "people over 30 years old":

```cypher
WHERE p.age > 30
```

That is not the same as "people aged 30 or older":

```cypher
WHERE p.age >= 30
```

In the sample data, `p.age > 30` selects only Chi, while `p.age >= 30` selects An and Chi.

### 6.2. Avoid Mixed-Type Comparisons

Compare numbers with numbers, strings with strings, and dates with dates when meaningful. Example:

```cypher
RETURN date('2026-11-25') >= date('2026-11-01') AS trongThang;
```

The result is `true`. If the database property has type `Date`, the application should pass an appropriate date value or intentionally convert the input string. Comparing dates as plain strings is not a general substitute for temporal comparisons.

## 7. Logical Operators: `AND`, `OR`, `NOT`, `XOR`

Cypher conditions can combine boolean expressions:

- `A AND B`: both A and B must be true.
- `A OR B`: at least one condition is true.
- `NOT A`: negates the logical value of A.
- `A XOR B`: true when **exactly one** of the two conditions is true.

For non-missing values:

| A | B | `A AND B` | `A OR B` | `A XOR B` |
|---|---|---|---|---|
| `true` | `true` | `true` | `true` | `false` |
| `true` | `false` | `false` | `true` | `true` |
| `false` | `true` | `false` | `true` | `true` |
| `false` | `false` | `false` | `false` | `false` |

### 7.1. Combined Condition Example

Requirement: "Active people **and** aged 28 or older."

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND (p.active = true AND p.age >= 28)
RETURN p.name AS ten;
```

Only **An** satisfies this. Chi is 35 but `active = false`; Bình is 27; Dũng is 24.

### 7.2. Negating a Group of Conditions

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND NOT (p.active = true AND p.age >= 28)
RETURN p.name AS ten
ORDER BY ten;
```

Result: Bình, Chi, Dũng. Parentheses after `NOT` make clear that we are negating **the entire** compound condition.

Do not rewrite `NOT (A AND B)` as `(NOT A) AND (NOT B)`. By De Morgan's law, the equivalent expression is `(NOT A) OR (NOT B)` (preserving `null` semantics under Cypher's three-valued logic as well).

## 8. Operator Precedence

When an expression lacks parentheses, the engine relies on rules to decide which part evaluates first. Below is the precedence order **grouped from highest to lowest**, commonly needed when reading Cypher conditions:

| Group | Representative Operators / Expressions | Notes |
|---|---|---|
| Value access | `p.age`, `list[0]`, `map['key']` | Resolves values/properties before they are used in larger expressions. |
| Exponentiation and unary signs | `^`, unary `+`/`-` | Use parentheses when combining unary minus with exponentiation. |
| Multiplication, division, modulo | `*`, `/`, `%` | Higher than addition/subtraction. |
| Addition, subtraction | `+`, `-` | Evaluated after multiplication/division in ordinary expressions. |
| Comparisons and checks | `=`, `<>`, `<`, `>=`, `IN`, `IS NULL`, ... | Produce logical values used by subsequent groups. |
| Logical negation | `NOT` | Higher than `AND`, `XOR`, `OR`. |
| Logical conjunction | `AND` | Higher than `XOR` and `OR`. |
| Exclusive disjunction | `XOR` | Higher than `OR`. |
| Logical disjunction | `OR` | Lowest precedence among these four logical operators. |

These entries represent **conceptual precedence groups**. When encountering less common syntax, unary arithmetic signs, version-specific operators, or deeply nested expressions, add parentheses to communicate intent clearly instead of relying on memorization.

### 8.1. `AND` Has Higher Precedence Than `OR`

```cypher
RETURN true OR false AND false AS khongNgoac,
       (true OR false) AND false AS coNgoac;
```

`khongNgoac = true` because `false AND false` is grouped first. `coNgoac = false` because `true OR false` is grouped first.

### 8.2. A Subtle Business Difference Easily Overlooked

Consider requirement A: **"Get people who are active, or people aged 30 or older and in Hà Nội."**

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND (p.active = true OR (p.age >= 30 AND p.city = 'Hà Nội'))
RETURN p.name AS ten
ORDER BY ten;
```

The result is **An, Bình, Chi, Dũng**: the three people with `active = true` pass; Chi is inactive, yet over 30 and in Hà Nội.

Requirement B: **"Get people in Hà Nội who are also either active or aged 30 or older."**

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND ((p.active = true OR p.age >= 30) AND p.city = 'Hà Nội')
RETURN p.name AS ten
ORDER BY ten;
```

Only **An and Chi**. The two requirements sound very similar in wording, yet the scope of "in Hà Nội" differs. **Parentheses are part of the business specification.**

### 8.3. Combining an ID Filter with an `OR` Group

A common bug:

```cypher
// ERROR-PRONE: the trailing OR branch can bypass the ID filter
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh']
  AND p.active = true
  OR p.age >= 30
RETURN p.name;
```

Because `AND` binds tighter than `OR`, this statement means:

```text
(id in list AND active)
OR (age >= 30)
```

As a result, the age branch can return nodes **outside the ID list**, such as Chi or any other person aged 30 or older. If the requirement is "within those two IDs only, select people who are active or aged 30+", write:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh']
  AND (p.active = true OR p.age >= 30)
RETURN p.name AS ten;
```

The second pair of parentheses draws a clear boundary between **the allowed candidate set** and **the selection condition within that set**.

## 9. `null` and Three-Valued Logic

In Cypher, a missing property or an unmatched variable in `OPTIONAL MATCH` produces `null`. In logical conditions, `null` represents **unknown/undefined**; it is not synonymous with `false`.

### 9.1. Logical Operations with `null`

| A | B | `A AND B` | `A OR B` |
|---|---|---|---|
| `true` | `null` | `null` | `true` |
| `false` | `null` | `false` | `null` |
| `null` | `true` | `null` | `true` |
| `null` | `false` | `false` | `null` |
| `null` | `null` | `null` | `null` |

`NOT null` yields `null`; an `XOR` expression with a `null` operand also yields `null`. `false AND null` always yields `false` because regardless of what the unknown value is, both conditions cannot simultaneously be true.

### 9.2. Comparing with `null`

```cypher
RETURN null = null AS soSanhBang,
       null <> 1 AS soSanhKhac,
       NOT null AS phuDinh;
```

All three columns evaluate to `null`. Never use `p.city = null` to find people missing the `city` property; use:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.city IS NULL
RETURN p.name AS ten;
```

Result: **Dũng**.

### 9.3. `<>` Does Not Automatically Include Missing Values

Requirement: "Find people not in Hà Nội."

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.city <> 'Hà Nội'
RETURN p.name AS ten;
```

Only **Bình** is returned. Dũng does not appear, because `null <> 'Hà Nội'` evaluates to `null`, not `true`.

If the requirement is "not in Hà Nội **or city not yet updated**", write it explicitly:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND (p.city <> 'Hà Nội' OR p.city IS NULL)
RETURN p.name AS ten
ORDER BY ten;
```

The result is **Bình, Dũng**.

### 9.4. `coalesce` Replaces `null` Intentionally

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
RETURN p.name AS ten,
       coalesce(p.city, 'Not updated') AS thanhPho
ORDER BY ten;
```

`coalesce` returns the **first non-`null` expression**; Dũng displays `'Not updated'`. This is a display rule we choose, without turning the missing property in the database into a stored value.

For numeric properties, `coalesce(p.score, 0)` can be useful when business rules treat "no score yet" as 0. If a missing score and a score of 0 carry different meanings, keep them **separate** and check with `IS NULL`.

## 10. String Operators

Cypher supports common string conditions:

| Expression | Meaning | Example |
|---|---|---|
| `name STARTS WITH 'B'` | Starts with substring. | `'Bình'` matches. |
| `name ENDS WITH 'nh'` | Ends with substring. | `'Bình'` matches. |
| `city CONTAINS 'Hà'` | Contains substring. | `'Hà Nội'` matches. |
| `name =~ 'B.*'` | Matches a regular expression. | `'Bình'` matches. |
| `toLower(name)` | Converts string to lowercase. | Useful when designing case-insensitive filtering. |
| `trim(name)` | Strips leading/trailing whitespace. | Useful when handling inputs with extra spaces. |

Example:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.name STARTS WITH 'B'
RETURN p.name AS ten;
```

Result: **Bình**.

### 10.1. Case Sensitivity

`STARTS WITH`, `ENDS WITH`, and `CONTAINS` perform literal character matching and do not automatically apply language-specific or Vietnamese diacritic normalization rules. When business logic requires case-insensitive filtering:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND toLower(p.name) STARTS WITH toLower($prefix)
RETURN p.name AS ten;
```

With parameter `{"prefix": "b"}`, **Bình** is found. Accented characters, Unicode normalization, and locale collations require dedicated design if the application needs diacritic-insensitive search.

### 10.2. Regular Expressions `=~`

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.name =~ '(?i)b.*'
RETURN p.name AS ten;
```

The pattern uses `(?i)` to enable case-insensitive regex matching, and `b.*` to require the string to start with "b" followed by any characters. Result: **Bình**.

**Pick the right tool:** if you only need prefix matching, `STARTS WITH` is usually clearer in intent than regex. For user-supplied regular expressions, the application must constrain complexity and input to avoid expensive queries.

### 10.3. String Concatenation vs. Arithmetic Addition

```cypher
MATCH (p:Person {id: 'c006-an'})
RETURN 'Staff: ' + p.name AS nhan;
```

Result: `'Staff: An'`. The `+` operator's behavior depends on data types; avoid mixing numbers and strings arbitrarily. When you need to display a number in text, convert explicitly, e.g., `toString(p.age)`.

## 11. `IN`, Lists, and Collection Conditions

The `IN` operator checks whether a value belongs to a list:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.city IN ['Hà Nội', 'Đà Nẵng']
RETURN p.name AS ten
ORDER BY ten;
```

Result: **An, Chi**. Dũng lacks the `city` property, so the condition does not evaluate to `true` even though the list includes `'Đà Nẵng'`.

### 11.1. Lists Are Data, Not String-Concatenated Syntax

In applications, pass lists via parameters:

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
RETURN p.name AS ten;
```

With:

```json
{
  "ids": ["c006-an", "c006-chi"]
}
```

The query selects An and Chi. Do not write `p.id IN [$ids]` if `$ids` is already a list: that creates **a list wrapping the input list**, contrary to your intent.

### 11.2. Empty Lists and `null` Elements

```cypher
RETURN 1 IN [] AS trongDanhSachRong,
       1 IN [1, 2] AS coTrongDanhSach,
       1 IN [2, null] AS khongChacChan;
```

Respectively:

- `1 IN []` → `false`.
- `1 IN [1, 2]` → `true`.
- `1 IN [2, null]` → `null`: no `1` explicitly matched, yet the list contains an unknown value.

Thus, missing data inside a list can affect condition outcomes. Applications should decide whether `null` elements are valid inside filter lists.

### 11.3. Checking Elements of a List Property

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND 'graph' IN coalesce(p.tags, [])
RETURN p.name AS ten
ORDER BY ten;
```

Result: **An, Chi**. `coalesce(p.tags, [])` lets Dũng—who has no `tags`—be treated as having an empty list **for the purpose of this expression**.

Beyond `IN`, you can use **list predicates** for more complex requirements:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND any(tag IN coalesce(p.tags, []) WHERE tag = 'graph')
RETURN p.name AS ten
ORDER BY ten;
```

`any(...)` checks whether at least one element satisfies the condition; the result is still An and Chi.

| List Predicate | Meaning for Definite `true`/`false` Conditions |
|---|---|
| `any(x IN list WHERE condition)` | At least one element satisfies the condition. |
| `all(x IN list WHERE condition)` | Every element satisfies the condition. |
| `none(x IN list WHERE condition)` | No element satisfies the condition. |
| `single(x IN list WHERE condition)` | Exactly one element satisfies the condition. |

On an empty list, `any` and `single` evaluate to `false`, whereas `all` and `none` evaluate to `true`; keep this behavior in mind when writing conditions like "all tags are valid". When elements or conditions involve `null`, list predicates also follow three-valued logic in indeterminate cases.

## 12. Map Expressions and Dynamic Property Access

Maps group named values together:

```cypher
WITH {minAge: 25, requiredCity: 'Hà Nội'} AS f
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.age >= f.minAge
  AND p.city = f.requiredCity
RETURN p.name AS ten;
```

Map `f` holds two keys, `minAge` and `requiredCity`. The result is An and Chi.

You can also access a property by a dynamic key using the expression:

```cypher
MATCH (p:Person {id: 'c006-an'})
RETURN p[$propertyName] AS giaTri;
```

If parameter `{"propertyName": "city"}` is passed, `giaTri = 'Hà Nội'`. `p[$propertyName]` is **dynamic-key property access**, different from passing a string to replace an entire query clause.

When an application lets callers choose properties dynamically, **restrict the set of readable keys** according to business rules, especially for sensitive data. Parameterization separates data from query syntax, but does not replace authorization.

## 13. `CASE`: Expressing Conditional Branching

Sometimes you need to return a value computed across multiple cases. `CASE` is the right expression:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
RETURN p.name AS ten,
       CASE
         WHEN p.score IS NULL THEN 'Unscored'
         WHEN p.score >= 90 THEN 'Excellent'
         WHEN p.score >= 80 THEN 'Pass'
         ELSE 'Needs improvement'
       END AS xepLoai
ORDER BY ten;
```

| ten | xepLoai |
|---|---|
| An | Excellent |
| Bình | Needs improvement |
| Chi | Pass |
| Dũng | Unscored |

`CASE` evaluates `WHEN` branches in order; the first branch whose condition evaluates to `true` determines the returned value. If no branch matches and there is no `ELSE`, the result is `null`.

### 13.1. `CASE` Makes Edge Cases Explicit

If Dũng has no score, do not implicitly classify Dũng as "below 80" without checking `null`. Placing `WHEN p.score IS NULL` first makes clear that "not yet scored" is **different from** "low score".

### 13.2. Simple Form for Equality-Only Checks

```cypher
MATCH (pr:Project)
WHERE pr.id IN ['c006-api', 'c006-reco']
RETURN pr.name AS ten,
       CASE pr.status
         WHEN 'active' THEN 'Running'
         WHEN 'planned' THEN 'Planned'
         ELSE 'Other'
       END AS trangThaiHienThi;
```

`CASE pr.status WHEN ...` fits equality comparisons. When requirements involve numeric ranges, multiple conditions, or `null` checks, the searched form `CASE WHEN condition THEN ...` usually expresses intent more clearly.

## 14. `EXISTS { ... }`: Conditions on Graph Pattern Existence

In a property graph, a common requirement is "which people **have** a relationship to an active project", without needing to enumerate each individual relationship.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND EXISTS {
    MATCH (p)-[:WORKS_ON]->(pr:Project)
    WHERE pr.status = 'active'
  }
RETURN p.name AS ten
ORDER BY ten;
```

Result: **An, Bình**. Variable `p` inside the existential expression refers to `p` from the outer row. The condition checks whether **at least one matching pattern exists**; it does not create two rows for An simply because An might have multiple relationships.

### 14.1. Comparison with Expanding `MATCH` + `DISTINCT`

An alternative:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND pr.status = 'active'
RETURN DISTINCT p.name AS ten
ORDER BY ten;
```

Here the result is also An, Bình. Semantically, however:

- `EXISTS { ... }` expresses an **existence predicate** directly per person.
- `MATCH` expands rows per relationship, and then `DISTINCT` deduplicates repeated names.

When relationship details are not needed, an existence expression usually states intent more cleanly; actual runtime performance still depends on data distribution and the plan Neo4j chooses.

### 14.2. Negating an Existence Condition

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND NOT EXISTS {
    MATCH (p)-[:WORKS_ON]->(:Project {status: 'active'})
  }
RETURN p.name AS ten
ORDER BY ten;
```

Result: **Chi, Dũng**. Chi has a project, but only a `planned` one; Dũng has no project. `NOT EXISTS` here means "no active project connected by this pattern exists", not "has no projects at all".

## 15. Conditions Attached to `MATCH`, `OPTIONAL MATCH`, and `WITH`

Where `WHERE` is placed determines **which entities get filtered out**. This matters especially when optional relationships are involved.

### 15.1. `WHERE` on `MATCH`

```cypher
MATCH (p:Person)-[w:WORKS_ON]->(pr:Project)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND pr.status = 'active'
  AND w.role IN ['lead', 'developer']
RETURN p.name AS ten, pr.name AS duAn, w.role AS vaiTro
ORDER BY ten;
```

Result: An – Graph API – lead; Bình – Graph API – developer. Only **complete** patterns satisfying the conditions are kept.

### 15.2. `WHERE` on `OPTIONAL MATCH`

Requirement: keep all four people, and if they participate in an active project in the lead role, return that project.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
OPTIONAL MATCH (p)-[w:WORKS_ON]->(pr:Project)
WHERE pr.status = 'active' AND w.role = 'lead'
RETURN p.name AS ten, pr.name AS duAnLead
ORDER BY ten;
```

| ten | duAnLead |
|---|---|
| An | Graph API |
| Bình | `null` |
| Chi | `null` |
| Dũng | `null` |

`WHERE` immediately following `OPTIONAL MATCH` is a condition **on the optional pattern**. People without a matching edge still keep their input row, while new variables such as `pr` take `null`.

### 15.3. `WHERE` After `WITH` Filters Existing Rows

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
OPTIONAL MATCH (p)-[w:WORKS_ON]->(pr:Project)
WITH p, w, pr
WHERE pr.status = 'active' AND w.role = 'lead'
RETURN p.name AS ten, pr.name AS duAnLead;
```

Only **An** remains. Bình – Graph API has role developer so it is filtered out; Chi – Recommendation is planned; Dũng has `pr = null`. The condition placed after `WITH` filters **the entire row**, no longer preserving optional rows on a miss.

To express requirements accurately, ask: "Do I want to **return only people** meeting the condition, or **keep everyone and optionally attach matching details**?" The answer determines where the condition goes.

## 16. Expressions After `WITH` and Variable Scope

`WITH` lets you bind a variable to a computed value and use it downstream in `WHERE` or `RETURN`.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
WITH p, p.score >= 80 AS diemDat
WHERE diemDat = true
RETURN p.name AS ten, p.score AS diem;
```

Result: An (92), Chi (88). Dũng has `p.score = null`, so `diemDat` is `null` and fails `WHERE diemDat = true`.

A variable remains in scope after `WITH` only if it is **forwarded**:

```cypher
// Intentionally invalid: p was not forwarded across WITH
MATCH (p:Person {id: 'c006-an'})
WITH p.score >= 80 AS diemDat
RETURN p.name AS ten, diemDat;
```

Valid version:

```cypher
MATCH (p:Person {id: 'c006-an'})
WITH p, p.score >= 80 AS diemDat
RETURN p.name AS ten, diemDat;
```

`WITH` is also where aggregations are computed so you can filter on counted results:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WITH p, count(pr) AS soDuAn
WHERE soDuAn >= 2
RETURN p.name AS ten, soDuAn;
```

Only An has two projects. `WHERE soDuAn >= 2` executes after the aggregate expression creates alias `soDuAn`.

## 17. Parameterizing Conditions for Safety and Reusability

In Java applications, values often vary per request: minimum age, city, list of roles, score threshold. Keep the Cypher structure fixed and move values into parameters:

```cypher
MATCH (p:Person)-[w:WORKS_ON]->(pr:Project)
WHERE p.id IN $personIds
  AND p.age >= $minAge
  AND w.role IN $roles
  AND pr.status = $status
RETURN p.name AS ten, pr.name AS duAn, w.role AS vaiTro
ORDER BY ten;
```

Sample parameters:

```json
{
  "personIds": ["c006-an", "c006-binh", "c006-chi", "c006-dung"],
  "minAge": 25,
  "roles": ["lead", "developer"],
  "status": "active"
}
```

Result: An – Graph API – lead; Bình – Graph API – developer. `Person`, `WORKS_ON`, and `Project` are part of the pattern structure, while parameters carry **data values**.

### 17.1. Example Passing Parameters from the Java Driver

```java
import java.util.List;
import java.util.Map;

String cypher = """
    MATCH (p:Person)
    WHERE p.id IN $ids
      AND p.age >= $minAge
      AND (p.active = true OR p.score >= $minScore)
    RETURN p.name AS ten, p.age AS tuoi
    ORDER BY ten
    """;

Map<String, Object> params = Map.of(
    "ids", List.of("c006-an", "c006-binh", "c006-chi", "c006-dung"),
    "minAge", 25,
    "minScore", 85
);

// Assume session is an open org.neo4j.driver.Session.
var records = session.run(cypher, params)
                     .list(row -> row.get("ten").asString());
```

Result is **An, Bình, Chi**:

- An: active, old enough, high score.
- Bình: active and old enough; score below 85 still satisfies the `OR` branch.
- Chi: inactive, yet old enough and score 88 exceeds threshold.
- Dũng: under 25, so filtered out despite being active.

Never concatenate user values into Cypher strings like `"... p.age >= " + userInput`. Passing values via a parameter map keeps inputs strictly in data positions, reducing Cypher injection risk. Applications still must validate types, value ranges, and access rights.

### 17.2. Missing Parameter vs. `null` Parameter

If a query references `$city`:

- Map `{"city": null}` contains key `city` with value `null`.
- Map `{}` omits the key altogether; a query expecting `$city` will not default it to `null`.

With an optional city filter:

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
  AND ($city IS NULL OR p.city = $city)
RETURN p.name AS ten;
```

Pass `city = null` to disable the city filter, or a city name to apply it. The condition uses parentheses to group the optional branch without affecting the `id` constraint.

## 18. Optimizing Conditions While Preserving Semantics

A **correct** condition must produce right results before optimization. When evaluating a query:

1. **Place meaningful filters.** Target labels/types and business properties rather than scanning the entire graph and checking arbitrary expressions.
2. **Use properly typed parameters.** Compare dates with dates and numbers with numbers; avoid implicit conversions.
3. **Ensure missing properties do not distort intent.** Pay special attention to `null`, `IS NULL`, and `OPTIONAL MATCH`.
4. **Watch out for functions on indexed properties.** For instance, `toLower(p.name)` can alter index usage compared to filtering on raw `p.name`. Choose normalization and indexing strategies based on real search requirements.
5. **Monitor intermediate row counts.** A person matching many relationships can generate many rows; use `EXISTS` when only checking existence.
6. **Inspect execution plans.** `EXPLAIN` shows the estimated plan; `PROFILE` executes the query and reports runtime metrics.

Example:

```cypher
EXPLAIN
MATCH (p:Person)
WHERE p.id = $personId
  AND p.age >= $minAge
RETURN p.name AS ten;
```

The statement must be run with a parameter map providing `personId` and `minAge`. An index or uniqueness constraint on `Person.id` typically helps queries starting from a business ID; this does not replace verifying the correctness of logical conditions.

**Do not rely on `AND`/`OR` being evaluated physically left to right** as a defensive guard. Cypher is declarative and the optimizer can choose any valid execution plan. When handling hazardous cases such as a zero denominator or missing values, express them explicitly via `CASE` or appropriate guards.

## 19. Comprehensive Problem: Filtering Staff by Business Criteria

**Requirement:** Within the selected list of people, consider only those aged 25 or older. Keep people who are **active and have an active project in an allowed role**, or **have a score at or above a high threshold**. Return name, display city, matching project count, list of matching projects, and outcome group.

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
  AND p.age >= $minAge
OPTIONAL MATCH (p)-[w:WORKS_ON]->(pr:Project)
WHERE pr.status = $status
  AND w.role IN $roles
WITH p,
     count(pr) AS soDuAnPhuHop,
     collect(DISTINCT pr.name) AS dsDuAnPhuHop
WHERE (p.active = true AND soDuAnPhuHop >= 1)
   OR (p.score IS NOT NULL AND p.score >= $minScore)
RETURN p.name AS ten,
       coalesce(p.city, 'Not updated') AS thanhPho,
       soDuAnPhuHop,
       dsDuAnPhuHop,
       CASE
         WHEN soDuAnPhuHop >= 1 THEN 'Has matching project'
         ELSE 'Meets score threshold'
       END AS lyDo
ORDER BY soDuAnPhuHop DESC, ten ASC;
```

Parameters:

```json
{
  "ids": ["c006-an", "c006-binh", "c006-chi", "c006-dung"],
  "minAge": 25,
  "status": "active",
  "roles": ["lead", "developer"],
  "minScore": 85
}
```

**Stage-by-stage walkthrough:**

| Stage | Condition and Effect | Result on Sample Data |
|---|---|---|
| Initial `MATCH` and `WHERE` | Selects valid IDs, age >= 25 | An, Bình, Chi; drops Dũng |
| `OPTIONAL MATCH` + `WHERE` | Finds active projects with allowed roles | An – Graph API; Bình – Graph API; Chi – `null` |
| `WITH` | Groups by `p` and counts matching projects | An 1, Bình 1, Chi 0 |
| `WHERE` after `WITH` | Checks active/project group **or** high score | Keeps An, Bình, and Chi |
| `RETURN` | Builds columns, replaces display `null`, sets `lyDo` label | Final 3 rows |

| ten | thanhPho | soDuAnPhuHop | dsDuAnPhuHop | lyDo |
|---|---|---:|---|---|
| An | Hà Nội | 1 | `['Graph API']` | Has matching project |
| Bình | TP. Hồ Chí Minh | 1 | `['Graph API']` | Has matching project |
| Chi | Hà Nội | 0 | `[]` | Meets score threshold |

Because `WITH` grouped by `p`, the final output has **one row per person**, not one row per relationship. `OPTIONAL MATCH` preserves Chi even though she has no active project. The high score threshold keeps Chi via the second `OR` branch. Parentheses make the scope of each branch explicit.

## 20. Common Condition Mistakes

| Mistake | Why It Is Wrong or Confusing | Clearer Form |
|---|---|---|
| `p.age >= 25 OR p.active = true AND p.city = 'Hà Nội'` | `AND` has higher precedence than `OR`; easily misread against requirements. | Write `(p.age >= 25 OR p.active = true) AND p.city = 'Hà Nội'` or group to match business intent. |
| `p.city = null` | Equality with null never yields `true`. | `p.city IS NULL`. |
| `p.city <> 'Hà Nội'` to also include people without a city | Missing property evaluates to `null` and is filtered out. | `p.city <> 'Hà Nội' OR p.city IS NULL`. |
| `p.age >= '25'` | String differs from number. | Use numeric literal `25` or numeric parameter. |
| `p.id IN [$ids]` when `$ids` is already a list | Creates a nested list. | `p.id IN $ids`. |
| `p.name = '$name'` | Compares against literal string `'$name'`. | `p.name = $name`. |
| `WHERE p.tags CONTAINS 'graph'` | `CONTAINS` is substring search, not list membership check. | `'graph' IN coalesce(p.tags, [])`. |
| `NOT p.active = true AND p.age >= 30` | Negation scope is unclear to readers. | `NOT (p.active = true AND p.age >= 30)` if negating the whole group. |
| `OPTIONAL MATCH` followed by filtering optional properties after `WITH` | Drops the preserved `null` rows. | Attach the filter to `OPTIONAL MATCH` when rows must be preserved. |
| Using `MATCH` across many relationships then returning nodes without grouping | A node matching multiple edges produces multiple rows. | Use `EXISTS` when only checking existence; aggregate/`DISTINCT` when appropriate. |
| Putting `"p.age DESC"` into `$sortBy` expecting it to sort | Parameters hold data, not syntax structure. | Select from application-approved queries/expressions. |
| Using `coalesce(p.score, 0)` blindly, ignoring "not yet scored" semantics | Conflates missing value with a real score of 0. | Use `IS NULL` and `CASE` if the two cases differ. |

## 21. Self-Practice Exercises

The exercises below use the dataset from Section 3. Predict the results yourself first, then compare with the answers.

### Exercise 1. Precedence of `AND` and `OR`

How does the following query differ when parentheses are added around the `OR` branch?

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND p.active = true OR p.age >= 30
RETURN p.name AS ten
ORDER BY ten;
```

<details>
<summary>Reference Answer</summary>

Because `AND` has higher precedence than `OR`, the query could return people aged 30+ **outside the ID list** if the database contains other data. On the sample set, all four people satisfy either `active = true` or `age >= 30`. To **restrict strictly to the four IDs** and then apply either criterion, write:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND (p.active = true OR p.age >= 30)
RETURN p.name AS ten
ORDER BY ten;
```

On the sample set the output is still An, Bình, Chi, Dũng, but the ID scope is properly preserved.

</details>

### Exercise 2. `null` and the Inequality Operator

Who does `WHERE p.city <> 'Hà Nội'` select? Rewrite it to also include people missing `city`.

<details>
<summary>Reference Answer</summary>

The original condition selects only **Bình**; Dũng has `p.city = null`, so `<>` yields `null`.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND (p.city <> 'Hà Nội' OR p.city IS NULL)
RETURN p.name AS ten
ORDER BY ten;
```

New result: **Bình, Dũng**.

</details>

### Exercise 3. Checking a List with `IN`

Find people who have the `'graph'` tag, even if a person has no `tags` property.

<details>
<summary>Reference Answer</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND 'graph' IN coalesce(p.tags, [])
RETURN p.name AS ten
ORDER BY ten;
```

Result: **An, Chi**. Dũng is evaluated with an empty list and does not match the condition.

</details>

### Exercise 4. Classifying Scores with `CASE`

Write an expression classifying scores >= 90 as `'Excellent'`, 80 to < 90 as `'Pass'`, < 80 as `'Needs improvement'`, and missing scores as `'Unscored'`.

<details>
<summary>Reference Answer</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
RETURN p.name AS ten,
       CASE
         WHEN p.score IS NULL THEN 'Unscored'
         WHEN p.score >= 90 THEN 'Excellent'
         WHEN p.score >= 80 THEN 'Pass'
         ELSE 'Needs improvement'
       END AS loai
ORDER BY ten;
```

An: Excellent; Bình: Needs improvement; Chi: Pass; Dũng: Unscored.

</details>

### Exercise 5. Relationship Existence Condition

Find people **who have at least one active project**, returning one row per person. Use `EXISTS { ... }`.

<details>
<summary>Reference Answer</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
  AND EXISTS {
    MATCH (p)-[:WORKS_ON]->(pr:Project)
    WHERE pr.status = 'active'
  }
RETURN p.name AS ten
ORDER BY ten;
```

Result: **An, Bình**.

</details>

### Exercise 6. Condition Placement with `OPTIONAL MATCH`

Write a query keeping **all four people**, where the project column shows only an active project in which the person holds the `'lead'` role. For anyone without a match, the project column must be `null`.

<details>
<summary>Reference Answer</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c006-an', 'c006-binh', 'c006-chi', 'c006-dung']
OPTIONAL MATCH (p)-[w:WORKS_ON]->(pr:Project)
WHERE pr.status = 'active' AND w.role = 'lead'
RETURN p.name AS ten, pr.name AS duAnLead
ORDER BY ten;
```

An – Graph API; Bình – `null`; Chi – `null`; Dũng – `null`. Placing `WHERE` directly after `OPTIONAL MATCH` applies the filter to the optional pattern.

</details>

### Exercise 7. Fixing a Semantic Bug with `IN`

The application passes `{"ids": ["c006-an", "c006-chi"]}`. Why does `WHERE p.id IN [$ids]` fail to express the requirement? Rewrite the query.

<details>
<summary>Reference Answer</summary>

`$ids` is already a list; `[$ids]` is a **single-element list whose element is itself a list**. Correct form:

```cypher
MATCH (p:Person)
WHERE p.id IN $ids
RETURN p.name AS ten
ORDER BY ten;
```

Result: An, Chi.

</details>

### Exercise 8. Evaluating a Three-Valued Expression

Predict the results of:

```cypher
RETURN false AND null AS a,
       true OR null AS b,
       null = null AS c,
       NOT null AS d;
```

<details>
<summary>Answer</summary>

`a = false`, `b = true`, `c = null`, `d = null`. Because `false AND ...` is definitely false and `true OR ...` is definitely true; comparing and negating `null` remain unknown.

</details>

### Exercise 9. Reasoning About Two Different Business Requirements

Given two conditions:

```cypher
// A
(p.active = true OR p.age >= 30) AND p.city = 'Hà Nội'

// B
p.active = true OR (p.age >= 30 AND p.city = 'Hà Nội')
```

Explain the result sets over the four sample people.

<details>
<summary>Answer</summary>

- **A:** only **An and Chi**, because Hà Nội is required for both branches.
- **B:** **An, Bình, Chi, Dũng**, because everyone who is active passes, while Chi satisfies the age-and-city branch.

Parentheses clarify the scope of the city constraint; this is a business difference, not merely stylistic formatting.

</details>

## 22. Key Takeaways

In Cypher, every expression evaluates to a value from variables, literals, parameters, properties, function calls, or operators. `WHERE` keeps only rows whose condition evaluates to `true`; when properties are missing, `null` makes many comparisons **unknown**, so use `IS NULL`, `IS NOT NULL`, or `coalesce` according to business semantics.

For complex conditions, favor **parentheses that explicitly reflect intent**: `NOT`, `AND`, `XOR`, and `OR` have different precedences, and a single parenthesis shift can change which people or relationships are selected. Expressions like `CASE`, `IN`, `any`, and `EXISTS { ... }` help express concrete requirements, particularly in Neo4j's property graph model. When integrating queries into the Java Driver or Spring Data Neo4j, continue passing values through parameters, enforce strict data types, track result row counts, and inspect execution plans when optimizing.
