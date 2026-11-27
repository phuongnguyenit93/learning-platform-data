# Null Values, Non-Existent Properties, and Three-Valued Logic in Cypher

In Neo4j's **property graph** model, nodes and relationships can carry properties such as `name`, `email`, `active`, or `registeredAt`. When reading a property that has not been stored, Cypher generally returns `null`. This value directly affects comparisons, `WHERE` conditions, logical operations, optional relationship queries, and data updates.

This lesson belongs to the **Data Types** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. Mastering the semantics of `null` helps you model connected data consistently, avoid missing results when querying with Cypher, and handle missing fields accurately in Java Driver or Spring Data Neo4j applications.

## 1. What Does null Represent?

`null` represents **no defined value** at the time an expression is evaluated. It is not synonymous with 0, an empty string, or the boolean value `false`.

| Expression | Meaning | Is It `null`? |
| --- | --- | --- |
| `0` | Numeric value of zero | No |
| `''` | String of length zero | No |
| `false` | Boolean false state | No |
| `[]` | Empty list in an expression | No |
| `null` | Missing/undefined value | Yes |
| `n.nickname` when the node lacks the `nickname` property | Accessing an absent property | Result is `null` |

Example without creating any data:

```cypher
RETURN
  0 IS NULL AS zeroIsNull,
  '' IS NULL AS emptyStringIsNull,
  false IS NULL AS falseIsNull,
  [] IS NULL AS emptyListIsNull,
  null IS NULL AS nullIsNull;
```

The results are `false`, `false`, `false`, `false`, and `true`, respectively.

**Key point:** Cypher uses `null` to represent the absence of a value in expressions; Neo4j **does not store a property with a null value** as an independent key–value pair on a node or relationship. This ties the concept of `null` closely to *non-existent properties* when working with properties.

## 2. Non-Existent Properties on Nodes and Relationships

### 2.1. Creating Sample Data

Run the following snippet once in a practice environment to create three nodes with different fields:

```cypher
CREATE
  (:LearnerNullDemo {
    learnerId: 'N-001',
    name: 'An',
    active: true,
    nickname: 'Annie'
  }),
  (:LearnerNullDemo {
    learnerId: 'N-002',
    name: 'Binh',
    active: false,
    nickname: ''
  }),
  (:LearnerNullDemo {
    learnerId: 'N-003',
    name: 'Chi'
  });
```

These are dedicated practice nodes; running `CREATE` again will create additional duplicate sample nodes.

For these nodes:

- An has `active = true` and `nickname = 'Annie'`.
- Binh has `active = false` and `nickname = ''`; both properties **exist**.
- Chi has neither `active` nor `nickname`; when reading these two properties, Cypher returns `null`.

Verification query:

```cypher
MATCH (p:LearnerNullDemo)
RETURN
  p.learnerId AS id,
  p.name AS name,
  p.active AS active,
  p.nickname AS nickname,
  p.nickname IS NULL AS nicknameIsMissing,
  'nickname' IN keys(p) AS hasNicknameKey
ORDER BY id;
```

| `id` | `active` | `nickname` | `nicknameIsMissing` | `hasNicknameKey` |
| --- | --- | --- | --- | --- |
| N-001 | `true` | `'Annie'` | `false` | `true` |
| N-002 | `false` | `''` | `false` | `true` |
| N-003 | `null` | `null` | `true` | `false` |

The `keys(p)` function returns the property keys currently stored on node `p`. The `properties(p)` function lets you inspect a map of those properties:

```cypher
MATCH (p:LearnerNullDemo {learnerId: 'N-003'})
RETURN keys(p) AS storedKeys, properties(p) AS storedProperties;
```

Here, `storedKeys` only contains properties actually stored; it does not populate `active` or `nickname` with `null` values.

### 2.2. Nodes/Relationships Differ from Intermediate Maps

In Cypher expressions, an **intermediate map** can contain a key mapped to `null`:

```cypher
WITH {nickname: null, active: false} AS payload
RETURN
  payload.nickname IS NULL AS declaredNull,
  payload.unknown IS NULL AS absentKey,
  keys(payload) AS mapKeys;
```

Both `payload.nickname` and `payload.unknown` return `null` when read. However, `keys(payload)` contains `nickname` and `active`, and does not contain `unknown`.

This is an important distinction:

- For an **in-memory map inside a query**, you can distinguish *a present key whose value is null* from *an absent key* by checking the list of keys.
- For **node/relationship properties**, a key with a `null` value is not stored; that property becomes absent.

If an API needs to distinguish "user did not send the field" from "user sent the field to clear it", that information must be preserved at the application layer or in the input payload before translating it into Neo4j properties.

## 3. Creating, Updating, and Deleting Properties with null

### 3.1. Assigning null Deletes a Property

In Cypher, assigning `null` to a property **deletes the property** from the node or relationship:

```cypher
MATCH (p:LearnerNullDemo {learnerId: 'N-001'})
SET p.nickname = null
RETURN
  p.nickname AS nicknameAfterUpdate,
  'nickname' IN keys(p) AS hasNicknameKey;
```

Result: `nicknameAfterUpdate` is `null` and `hasNicknameKey` is `false`. The statement removed the `nickname` property rather than creating a property with a null value.

You can delete a property directly using `REMOVE`:

```cypher
MATCH (p:LearnerNullDemo {learnerId: 'N-002'})
REMOVE p.nickname
RETURN keys(p) AS remainingKeys;
```

`REMOVE p.nickname` clearly expresses the intent to delete the field; `SET p.nickname = null` produces the equivalent storage result. Both sample statements above **modify the practice data**, so run them only when you want to test the update behavior.

### 3.2. When Creating Properties with a null Value

Neo4j ignores properties with a `null` value in the data to be written. In the following example, `middleName` does not become a stored property:

```cypher
CREATE (p:PersonNullExample {
  personId: 'P-NULL-001',
  name: 'Minh',
  middleName: null
})
RETURN keys(p) AS keysAfterCreate, p.middleName AS middleName;
```

Therefore, "storing a null property" cannot be used as a marker to indicate that a column was submitted but left blank.

### 3.3. SET with a Map Containing null

The `SET n += map` syntax adds and updates properties key by key. If the map contains a key whose value is `null`, the corresponding property is deleted:

```cypher
MATCH (p:PersonNullExample {personId: 'P-NULL-001'})
SET p += {
  city: 'Hanoi',
  name: 'Minh Anh',
  middleName: null
}
RETURN properties(p) AS propertiesAfterUpdate;
```

The `city` field is added, `name` is updated, and `middleName` does not exist. Check for `null` values in input maps before using `SET +=` if an update is not allowed to delete existing data.

### 3.4. Key Fields Must Not Be null in MERGE

`MERGE` is used to match or create patterns by key properties. A key property with a `null` value can cause `MERGE` to fail:

```cypher
// Example DO NOT RUN when $email = null:
// MERGE (u:User {email: $email})
```

Validate the key before executing:

```cypher
WITH $email AS email
WHERE email IS NOT NULL
MERGE (u:User {email: email})
RETURN u;
```

If `$email` is `null`, the validated query passes no rows to `MERGE`. In a real application, report an input error or intentionally skip the record, and consider adding a unique constraint for business keys when designing the model.

## 4. Three-Valued Logic: true, false, and null

For logical operations, Cypher uses three outcomes: **`true`, `false`, and `null`** (unknown). `null` is not implicitly coerced to `false`.

### 4.1. AND and OR Truth Table

| `a` | `b` | `a AND b` | `a OR b` |
| --- | --- | --- | --- |
| `true` | `true` | `true` | `true` |
| `true` | `false` | `false` | `true` |
| `true` | `null` | `null` | `true` |
| `false` | `true` | `false` | `true` |
| `false` | `false` | `false` | `false` |
| `false` | `null` | `false` | `null` |
| `null` | `true` | `null` | `true` |
| `null` | `false` | `false` | `null` |
| `null` | `null` | `null` | `null` |

Explanation:

- `false AND null` is `false` because one side is already known to be false, regardless of the other side.
- `true OR null` is `true` because one side is already known to be true.
- `true AND null` is `null` because the result depends on unknown data.
- `false OR null` is `null`, also because it still depends on an unknown value.

You can generate the truth table directly using Cypher:

```cypher
WITH [true, false, null] AS values
UNWIND values AS a
UNWIND values AS b
RETURN a, b, a AND b AS andResult, a OR b AS orResult;
```

### 4.2. NOT and XOR

| Expression | Result |
| --- | --- |
| `NOT true` | `false` |
| `NOT false` | `true` |
| `NOT null` | `null` |
| `true XOR false` | `true` |
| `true XOR true` | `false` |
| `false XOR false` | `false` |
| `true XOR null` | `null` |

`NOT null` remains `null`: negating something unknown does not turn it into `true`.

### 4.3. Comparing with null

Standard comparisons against `null` do not yield a definite `true` or `false`; for example:

```cypher
RETURN
  null = null AS equalityOfNulls,
  5 = null AS equalityWithNull,
  5 <> null AS inequalityWithNull,
  5 > null AS greaterThanNull,
  null IS NULL AS explicitNullCheck,
  null IS NOT NULL AS explicitNotNullCheck;
```

The first four comparison expressions return `null`; the two checks `IS NULL` and `IS NOT NULL` evaluate to `true` and `false`, respectively.

**Do not use `n.property = null` or `n.property <> null` to check for missing values.** Use `IS NULL` and `IS NOT NULL`.

## 5. How Does WHERE Handle null Conditions?

The `WHERE` clause only keeps rows where the condition evaluates to **`true`**. Rows evaluating to `false` or `null` are both discarded.

The following example returns nodes with `active = true`:

```cypher
MATCH (p:LearnerNullDemo)
WHERE p.active = true
RETURN p.learnerId, p.name;
```

With the initial sample dataset, An is returned. Binh has `active = false` and is filtered out; Chi lacks `active`, so the condition `null = true` evaluates to `null` and is also filtered out.

Similarly, negation does not automatically include nodes missing the property:

```cypher
MATCH (p:LearnerNullDemo)
WHERE NOT p.active
RETURN p.learnerId, p.name;
```

The query above returns Binh since `active = false`, but does not return Chi because `NOT null` is `null`.

If the goal is to find both inactive users **or** users without a status yet, write both cases explicitly:

```cypher
MATCH (p:LearnerNullDemo)
WHERE p.active = false OR p.active IS NULL
RETURN p.learnerId, p.name, p.active;
```

If searching only for missing fields:

```cypher
MATCH (p:LearnerNullDemo)
WHERE p.active IS NULL
RETURN p.learnerId, p.name;
```

If searching only for fields that have a value:

```cypher
MATCH (p:LearnerNullDemo)
WHERE p.active IS NOT NULL
RETURN p.learnerId, p.name;
```

**Note:** for actual node/relationship properties, `IS NULL` effectively checks the non-existent property case. However, if the expression is a computation or a variable from `OPTIONAL MATCH`, `IS NULL` can also arise from other causes.

## 6. Computations and Functions with null

Many arithmetic expressions or string operations yield `null` when a required operand is missing:

```cypher
RETURN
  10 + null AS missingAddition,
  100 * null AS missingMultiplication,
  'Cypher' + null AS missingConcatenation,
  size(null) AS missingSize;
```

Having a calculation return `null` can be helpful: the result is not mistaken for 0 when inputs are missing. When a default value is needed, use `coalesce()`.

### 6.1. coalesce Picks the First Non-null Value

```cypher
RETURN
  coalesce(null, 'Anonymous') AS defaultName,
  coalesce(0, 10) AS zeroIsRetained,
  coalesce(false, true) AS falseIsRetained,
  coalesce('', 'Default') AS emptyStringIsRetained;
```

`coalesce()` **does not replace** 0, `false`, or an empty string, because all three are non-`null` values.

Example for outputting display text:

```cypher
MATCH (p:LearnerNullDemo)
RETURN
  p.name,
  coalesce(p.nickname, '(no nickname)') AS displayNickname;
```

In Binh's case, since `nickname = ''`, the result remains an empty string. If the application wants to show a default for empty strings as well, handle it explicitly according to business rules.

### 6.2. CASE Explicitly Classifies Missing States

`CASE` lets you represent multiple states while preserving the distinction between `false` and `null`:

```cypher
MATCH (p:LearnerNullDemo)
RETURN
  p.name,
  CASE
    WHEN p.active = true THEN 'Active'
    WHEN p.active = false THEN 'Suspended'
    ELSE 'No status'
  END AS accountStatus;
```

With the initial sample data, the results are "Active", "Suspended", and "No status", respectively. The `ELSE` branch covers cases without an `active` value.

Another example handling a missing number in a calculation:

```cypher
WITH 150000 AS price, null AS discountPercent
RETURN
  CASE
    WHEN discountPercent IS NULL THEN null
    ELSE price * (1.0 - discountPercent / 100.0)
  END AS finalPrice;
```

Returning `null` here expresses "unable to compute final price because discount rate is missing". Defaulting to a 0% discount is only valid if permitted by the business domain.

## 7. OPTIONAL MATCH Produces null When No Matching Relationship Exists

`OPTIONAL MATCH` is very important in Neo4j because applications often need to retrieve a node even when a related relationship or node does not yet exist.

Create a sample course and link it only to An:

```cypher
CREATE (:CourseNullDemo {courseId: 'C-001', title: 'Cypher Basics'});
```

```cypher
MATCH (p:LearnerNullDemo {learnerId: 'N-001'})
MATCH (c:CourseNullDemo {courseId: 'C-001'})
CREATE (p)-[:ENROLLED_IN]->(c);
```

Then query:

```cypher
MATCH (p:LearnerNullDemo)
OPTIONAL MATCH (p)-[r:ENROLLED_IN]->(c:CourseNullDemo)
RETURN
  p.learnerId AS learnerId,
  p.name AS learnerName,
  c.title AS courseTitle,
  r IS NULL AS enrollmentMissing
ORDER BY learnerId;
```

Assuming each node in the example has at most one `ENROLLED_IN` relationship, illustrative results:

| `learnerId` | `courseTitle` | `enrollmentMissing` |
| --- | --- | --- |
| N-001 | `'Cypher Basics'` | `false` |
| N-002 | `null` | `true` |
| N-003 | `null` | `true` |

`MATCH` normally requires a matching pattern to keep a row; `OPTIONAL MATCH` keeps the row from `p` and assigns `null` for the unmatched part of the pattern. `c.title IS NULL` in this case can occur because variable `c` is unbound, even if unrelated to the `title` property of an existing node.

### 7.1. WHERE Placement Changes the Meaning

In this example, `WHERE` belongs to `OPTIONAL MATCH` itself:

```cypher
MATCH (p:LearnerNullDemo)
OPTIONAL MATCH (p)-[:ENROLLED_IN]->(c:CourseNullDemo)
WHERE c.title = 'Cypher Basics'
RETURN p.name, c.title;
```

When no matching course relationship is found, row `p` is still kept and `c` is `null`.

By contrast:

```cypher
MATCH (p:LearnerNullDemo)
OPTIONAL MATCH (p)-[:ENROLLED_IN]->(c:CourseNullDemo)
WITH p, c
WHERE c.title = 'Cypher Basics'
RETURN p.name, c.title;
```

Here, `WHERE` filters results **after** the optional match step. For nodes without a course, `c.title` is `null`; the condition is not `true`, so those nodes are dropped.

This is a common reason why a query appears to use `OPTIONAL MATCH` yet still loses nodes without relationships.

### 7.2. Checking Relationship Existence with EXISTS

If you need to check *whether or not* a relationship exists, you can use an `EXISTS { ... }` expression instead of fetching data and comparing against `null`:

```cypher
MATCH (p:LearnerNullDemo)
RETURN
  p.name,
  EXISTS {
    MATCH (p)-[:ENROLLED_IN]->(:CourseNullDemo)
  } AS hasEnrollment;
```

This query returns a boolean for the existence of the pattern. When you only need to know whether a connection exists, this representation usually expresses intent more clearly than an `OPTIONAL MATCH` used solely to build a flag.

## 8. null in Lists, IN, and Aggregations

### 8.1. Lists in Expressions Can Contain null

```cypher
RETURN
  [1, null, 3] AS valuesInQuery,
  size([1, null, 3]) AS numberOfElements;
```

The list above has three elements in a **Cypher expression**. However, a list property on a node/relationship cannot directly store `null` elements. If you need to store a list as a property, strip missing elements or change the data model before `SET`.

Example of filtering `null` out of a list:

```cypher
WITH [1, null, 3, null, 5] AS rawNumbers
RETURN [x IN rawNumbers WHERE x IS NOT NULL] AS cleanNumbers;
```

The result `cleanNumbers` is `[1, 3, 5]`.

`UNWIND` can produce rows with `null` values; filter with `WHERE` if those rows are not wanted:

```cypher
UNWIND [1, null, 3] AS number
WITH number
WHERE number IS NOT NULL
RETURN number
ORDER BY number;
```

### 8.2. The IN Operator When a List Contains null

With a list containing `null`, the result of `IN` is sometimes unknown:

```cypher
RETURN
  5 IN [5, null] AS definitelyPresent,
  5 IN [3, null] AS cannotConfirmAbsent,
  5 IN [3, 4] AS definitelyAbsent;
```

The results are `true`, `null`, and `false`. In the second case, no known element equals 5, yet an unknown element exists, so `false` cannot be confirmed.

If a list is used to check a set of identifiers, proactively handle null elements before checking membership.

### 8.3. count(*) Differs from count(expression)

Aggregation functions distinguish between row counts and non-null value counts:

```cypher
MATCH (p:LearnerNullDemo)
RETURN
  count(*) AS learnerRows,
  count(p.active) AS learnersWithActive,
  count(p.nickname) AS learnersWithNickname;
```

With the initial three nodes, `learnerRows` equals 3; `learnersWithActive` equals 2; `learnersWithNickname` equals 2. If you ran the `SET ... = null` or `REMOVE` snippets earlier, the property counts will change accordingly.

- `count(*)` counts **result rows**, even when some columns in a row are null.
- `count(p.active)` counts only rows where `p.active` is not `null`. A `false` value is still counted.
- `count(p.nickname)` counts the empty string `''` as well, because an empty string is not `null`.

The `collect(expression)` function skips `null` values, so the aggregated list may have fewer elements than the number of rows:

```cypher
MATCH (p:LearnerNullDemo)
RETURN
  count(*) AS totalRows,
  collect(p.nickname) AS availableNicknames;
```

When computing averages or sums on potentially missing properties, consider how many values participate in the calculation and the business intent: "no score yet" differs from "score of 0".

### 8.4. Counting Relationships with OPTIONAL MATCH

```cypher
MATCH (p:LearnerNullDemo)
OPTIONAL MATCH (p)-[r:ENROLLED_IN]->(:CourseNullDemo)
RETURN
  p.learnerId AS id,
  count(r) AS enrollmentCount
ORDER BY id;
```

`count(r)` counts actual matched relationships, so unenrolled nodes yield `0`. Replacing it with `count(*)` would also count rows preserved by `OPTIONAL MATCH`; when no relationship exists, each learner still contributes one row. Choose the counting expression that matches the business question.

## 9. null in Java Driver Parameters and Spring Data Neo4j

A user-update API might receive a request containing `nickname` or omitting that field. At the application layer, three meanings often need to be distinguished:

| Input State | Example Business Meaning | Recommended Behavior |
| --- | --- | --- |
| Field `nickname` omitted | Keep existing information | Do not update the property |
| Sent `nickname: null` | Delete nickname | Intentionally delete the property |
| Sent `nickname: ''` | Set nickname to empty string | Store empty string if valid |

Neo4j only sees the parameter value passed into the query; if the application has already collapsed the first two cases into `null`, Cypher cannot know on its own whether the user meant "keep" or "delete".

Example query:

```cypher
MATCH (p:User {userId: $userId})
SET p.nickname = $nickname
RETURN p.userId, p.nickname;
```

When the Java Driver passes `$nickname = null`, the `SET` clause deletes the nickname property. If parameter `$nickname` **is not passed** even though the query references it, Neo4j raises a missing-parameter error; that is not how to express "do not update".

If the business rule states that `null` means "keep unchanged", you can use:

```cypher
MATCH (p:User {userId: $userId})
SET p.nickname = coalesce($nickname, p.nickname)
RETURN p.userId, p.nickname;
```

This keeps the old property when `$nickname` is `null` but **does not allow callers to use null to delete it**. If the API needs to distinguish keeping from deleting, translate the update state into explicit actions in the Java layer—for example, only including `SET` when changed and using `REMOVE` when deletion is needed.

With the Java Driver, when reading returned values, you can check `Value.isNull()` before extracting a Java value. In Spring Data Neo4j, define conventions for mapping missing fields to entity properties and design update DTOs so that "omitted" is distinguishable from "intentionally sent null" when required by the business domain.

**Especially with MERGE:** validate identifier/matching keys before running Cypher. A map containing `null` in a key can cause errors or disrupt a data ingestion pipeline.

## 10. Common Errors and Fixes

| Scenario | Why Is It Wrong or Unexpected? | Resolution |
| --- | --- | --- |
| `WHERE n.email = null` | `= null` yields `null` | Use `n.email IS NULL` |
| `WHERE n.email <> null` | Fails to check "has email" | Use `n.email IS NOT NULL` |
| `WHERE NOT n.active` to include users without a status | `NOT null` is still `null` | Add `OR n.active IS NULL` if required by business logic |
| `SET n.email = $email` with `$email = null` | Deletes the existing property | Check update intent before `SET` |
| `SET n += $patch` with a key holding null | That key deletes the property | Filter/interpret patch data in the application layer |
| `MERGE (n:User {email: $email})` with null email | Cannot use null as a `MERGE` key property value | Validate the key before merging |
| `OPTIONAL MATCH` followed by `WHERE matched.value = ...` in a later step | Drops rows where the matched variable is null | Place the condition properly or handle `IS NULL` |
| `count(*)` interpreted as number of existing relationships | Also counts empty rows from `OPTIONAL MATCH` | Use `count(r)` when counting relationships |
| `coalesce(n.score, 0)` used without checking business rules | Turns "no score yet" into "score 0" | Only default to 0 if explicitly specified |
| Storing `[1, null, 3]` as a property list | Property lists cannot contain null elements | Clean the data or change the model |

## 11. Practice Exercises with Solutions

### Exercise 1 — Distinguishing null from Concrete Values

Predict the result of the query:

```cypher
RETURN
  false IS NULL AS a,
  0 IS NULL AS b,
  '' IS NULL AS c,
  null IS NULL AS d;
```

**Answer:** `a = false`, `b = false`, `c = false`, `d = true`. Boolean false, zero, and an empty string are all valid values.

### Exercise 2 — Reading the Truth Table

Evaluate `true AND null`, `false AND null`, `true OR null`, and `NOT null`.

**Answer:** `null`, `false`, `true`, `null`, respectively. Even with one operand missing, `AND` and `OR` can sometimes determine the outcome from the other operand.

### Exercise 3 — Finding Users Without a Verification Status

A `User` node has a `verified` property with `true`, `false`, or no property at all. Find exactly the nodes that do not have the `verified` property.

**Answer:**

```cypher
MATCH (u:User)
WHERE u.verified IS NULL
RETURN u.userId;
```

Do not use `u.verified = false` because that condition only applies to statuses known to be false.

### Exercise 4 — Keeping Learners Without Any Course Enrollment

Return the learner's name, the course name if present, and display the string `'(not enrolled)'` if no enrollment relationship exists.

**Answer:**

```cypher
MATCH (p:LearnerNullDemo)
OPTIONAL MATCH (p)-[:ENROLLED_IN]->(c:CourseNullDemo)
RETURN
  p.name AS learnerName,
  coalesce(c.title, '(not enrolled)') AS courseName;
```

Because `OPTIONAL MATCH` preserves the learner row, `coalesce()` can substitute a display message for the absent course title.

### Exercise 5 — Counting Actual Relationships

A learner can have 0, 1, or more `ENROLLED_IN` relationships. Count the number of relationships for each learner, including those not enrolled.

**Answer:**

```cypher
MATCH (p:LearnerNullDemo)
OPTIONAL MATCH (p)-[r:ENROLLED_IN]->(:CourseNullDemo)
RETURN
  p.name,
  count(r) AS numberOfEnrollments
ORDER BY p.name;
```

When no relationship matches, `r` is `null` and is not counted by `count(r)`.

### Exercise 6 — Predicting the Impact of an Update

Initially a node has `nickname = 'Annie'`. What happens after `SET p.nickname = null`? Will `p.nickname IS NULL` return `true`?

**Answer:** the `nickname` property is deleted, reading `p.nickname` afterward returns `null`, and `p.nickname IS NULL` evaluates to `true`.

## 12. Checklist for Applying in a Neo4j Project

Before deploying Cypher queries or updates via the Java Driver/Spring Data Neo4j, check:

1. Is a missing data field truly distinct from `false`, `0`, or an empty string?
2. Do filter conditions use `IS NULL`/`IS NOT NULL` instead of `= null`?
3. Could `AND`, `OR`, or `NOT` produce `null` and cause `WHERE` to drop rows?
4. Is an `OPTIONAL MATCH` accidentally being turned into a mandatory filter by a later `WHERE` condition?
5. Is `count(*)` or `count(expression)` the right one for the quantity being counted?
6. Is there a risk of assigning `null` and losing existing properties when handling parameters or update maps?
7. Are keys used in `MERGE` validated to be non-null?
8. Does the API need to distinguish between "field omitted", "null sent to delete", and "empty value sent"?
9. Should an additional business indicator like `verificationStatus` be stored to distinguish multiple kinds of "unknown"?

---

**Remember:** `null` is the state of having no defined value in an expression; on nodes and relationships, properties with `null` are not stored, and assigning `null` deletes the property. Three-valued logic causes comparisons or negations on missing data to often still produce `null`. Use `IS NULL`, `IS NOT NULL`, `OPTIONAL MATCH`, `CASE`, and `coalesce()` in line with your business goals, while controlling update parameters to avoid accidental data loss.
