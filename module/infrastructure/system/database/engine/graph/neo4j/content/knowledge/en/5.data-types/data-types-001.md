# Cypher Value Types and Storable Property Types

In Neo4j, data is organized as a **property graph**: nodes and relationships can carry properties as `key: value` pairs. Cypher is the language used to create, read, and transform that graph. When writing Cypher, it is necessary to distinguish between two scopes:

- **Values used in expressions and query results**: can be numbers, strings, dates and times, lists, maps, nodes, relationships, paths, or `null`.
- **Values persisted as properties** on a node/relationship: only belong to the set of types supported by Neo4j for properties, which does not include every value that Cypher can compute.

This distinction is important when modeling connected data, designing APIs, importing data, and converting types from a Java application to Neo4j.

## 1. Overview of Value Types

| Category | Cypher Type/Value | Example | Stored Directly as a Property? |
| --- | --- | --- | --- |
| Boolean | `BOOLEAN` | `true`, `false` | Yes |
| Integer | `INTEGER` | `42`, `-7` | Yes |
| Float | `FLOAT` | `3.14`, `1.0` | Yes |
| Text | `STRING` | `'Neo4j'`, `'Hanoi'` | Yes |
| Date | `DATE` | `date('2026-11-25')` | Yes |
| Zoned Time | `ZONED TIME` | `time('09:30:00+07:00')` | Yes |
| Local Time | `LOCAL TIME` | `localtime('09:30:00')` | Yes |
| Zoned Datetime | `ZONED DATETIME` | `datetime('2026-11-25T09:30:00+07:00')` | Yes |
| Local Datetime | `LOCAL DATETIME` | `localdatetime('2026-11-25T09:30:00')` | Yes |
| Duration | `DURATION` | `duration('P2DT3H')` | Yes |
| Spatial Point | `POINT` | `point({latitude: 10.77, longitude: 106.70})` | Yes |
| List | `LIST` | `['java', 'neo4j']` | Yes, when elements satisfy property list rules |
| Key–Value Map | `MAP` | `{city: 'Da Nang', level: 2}` | Cannot store an entire map in one property |
| Graph Entity | `NODE`, `RELATIONSHIP`, `PATH` | `p`, `r`, `path` in `MATCH` | No |
| Missing Value | `null` | `null` or accessing an absent property | No: assigning `null` deletes the property |

> **Fundamental rule:** a value that *can appear in a Cypher query* is not necessarily *storable as a property*. Both nodes and relationships are subject to the same rules regarding property value types.

## 2. Scalar Types: Boolean, Numeric, and String

### BOOLEAN

`BOOLEAN` has only two non-`null` values: `true` and `false`. It is suitable for status flags such as `isActive`, `verified`, and `isPublic`:

```cypher
CREATE (u:User {
  username: 'lan',
  isActive: true,
  verified: false
})
RETURN u.username, u.isActive, u.verified;
```

`false` is an actual stored value. It differs from `null`, which indicates the absence of a value at expression evaluation time.

### INTEGER and FLOAT

- `INTEGER` represents a 64-bit signed integer, used for ages, quantities, sequence numbers, or counters within the supported range.
- `FLOAT` represents an IEEE 754 64-bit floating-point number; suitable for measurements and decimal data where representation error is acceptable.
- `42` and `42.0` are two literals of different types; type consistency should be maintained during ingestion and updates.

```cypher
RETURN
  42 AS soNguyen,
  42.0 AS soThuc,
  toInteger('42') AS epSangSoNguyen,
  toFloat('3.14') AS epSangSoThuc;
```

Do not assume `FLOAT` represents every decimal number exactly. For currency requiring exact precision, integers in the smallest unit (e.g., cents or dong) or a representation model matching business requirements are commonly used.

### STRING

`STRING` is a Unicode string, used for names, business codes, emails, descriptions, and display labels. The empty string `''` is still a value; it is not synonymous with `null` or the absence of a property.

```cypher
RETURN
  'Neo4j' AS sanPham,
  'Knowledge Graph' AS tieuDe,
  toString(2026) AS namDangChuoi;
```

Identifiers with leading zeros, such as `'00125'`, should be kept as `STRING` if those leading zeros are meaningful. Do not convert them to `INTEGER` merely because all characters are digits.

## 3. Date, Time, and Duration Types

Cypher distinguishes between *date*, *time of day*, *datetime*, and *duration*:

| Type | Meaning | Use Case |
| --- | --- | --- |
| `DATE` | Calendar date, without time | Date of birth, release date |
| `LOCAL TIME` | Time of day, without timezone/UTC offset | Store opening hours in local schedule |
| `ZONED TIME` | Time of day with timezone offset information | Appointment time with offset |
| `LOCAL DATETIME` | Date and time without timezone information | Local schedule when the zone is managed by the application |
| `ZONED DATETIME` | Date and time with timezone/offset information | Timestamp when an event occurred |
| `DURATION` | Length or span of time | Processing duration, time limit |

Example of storing temporal types:

```cypher
CREATE (e:Event {
  eventId: 'EV-001',
  eventDate: date('2026-11-25'),
  localStart: localtime('09:00:00'),
  occurredAt: datetime('2026-11-25T09:00:00+07:00'),
  plannedLength: duration('PT1H30M')
})
RETURN
  e.eventDate,
  e.localStart,
  e.occurredAt,
  e.plannedLength;
```

**Semantic notes:**

- `date('2026-11-25')` does not represent an exact point in time within the day.
- `localdatetime('2026-11-25T09:00:00')` does not by itself indicate which timezone 09:00 belongs to; it should not be used as a global timestamp if data crosses multiple timezones.
- `datetime('2026-11-25T09:00:00+07:00')` carries offset information, making it more suitable for transaction timestamps or logs.
- `duration('P1M')` means one calendar month; it must not be assumed to always equal a fixed number of days or seconds.

Date and time formats in the UI may vary, but data should be normalized before entering Neo4j and stored using actual temporal types rather than storing all dates and times as strings.

## 4. Spatial POINT Type

`POINT` represents a point in a coordinate reference system. For latitude/longitude coordinates on Earth, use the `longitude` and `latitude` fields; for planar coordinates, `x` and `y` can be used according to the corresponding coordinate system.

```cypher
CREATE (s:Store {
  storeId: 'S-001',
  name: 'Central Store',
  location: point({
    latitude: 10.7769,
    longitude: 106.7009
  })
})
RETURN s.name, s.location;
```

From a `POINT` property, spatial distance can be calculated:

```cypher
WITH point({latitude: 10.7769, longitude: 106.7009}) AS center
MATCH (s:Store)
WHERE s.location IS NOT NULL
RETURN
  s.name,
  point.distance(s.location, center) AS distanceMeters
ORDER BY distanceMeters;
```

This example assumes that `s.location` values are all `POINT` and have a coordinate system compatible with `center`. Consistent coordinate storage must be enforced when integrating map data.

## 5. LIST: Query Usage and Property Usage

`LIST` is an ordered sequence of elements. In **Cypher expressions**, a list can contain multiple types, `null`, maps, or nested lists. However, when stored as **a property**, Neo4j only accepts lists whose elements belong to supported property value types and are type-compatible; do not store lists containing `null`, maps, nodes, or nested lists as properties.

```cypher
// Lists used in query expressions:
RETURN
  [1, 'A', true] AS mixedValues,
  [1, null, 3] AS valuesWithNull,
  [{code: 'A'}, {code: 'B'}] AS mapsInQuery;
```

The values above work in query results but **must not be assigned as-is to a property**.

Examples of valid property lists:

```cypher
CREATE (p:Person {
  personId: 'P-001',
  name: 'Lan',
  skills: ['Cypher', 'Java', 'Spring'],
  scores: [8, 9, 10],
  activeDays: [date('2026-11-23'), date('2026-11-25')]
})
RETURN p.name, p.skills, p.scores, p.activeDays;
```

Some practical guidelines:

- `['Cypher', 'Java']` is a storable list of strings; `[8, 9, 10]` is a storable list of integers.
- `[]` can represent an empty list, which is still distinct from a missing property.
- `[1, 'A']`, `[1, null, 3]`, `[[1, 2], [3, 4]]`, and `[{key: 'value'}]` are not suitable for storing directly as property lists.
- A simple list of tags can be kept in a property. If each tag has its own attributes, requires deep querying, or connects to other nodes, consider modeling them as nodes and relationships.

Lists can be accessed and processed using indexes, the `IN` operator, and `UNWIND`:

```cypher
MATCH (p:Person {personId: 'P-001'})
RETURN
  p.skills[0] AS firstSkill,
  'Cypher' IN p.skills AS knowsCypher,
  size(p.skills) AS skillCount;
```

```cypher
MATCH (p:Person {personId: 'P-001'})
UNWIND p.skills AS skill
RETURN p.name, skill
ORDER BY skill;
```

`UNWIND` turns list elements into result rows for further processing; it does not automatically create nodes or relationships.

## 6. MAP, NODE, RELATIONSHIP, and PATH: Query Values, Not Properties

### MAP

`MAP` is a collection of named key–value pairs, useful for packaging results, passing parameters, or structuring data before writing.

```cypher
WITH {
  name: 'Minh',
  address: {city: 'Hanoi', district: 'Cau Giay'},
  skills: ['Neo4j', 'Java']
} AS profile
RETURN profile.name AS name, profile.address.city AS city;
```

In the example above, `profile` is a valid map **within a query**. However, an operation like the following is invalid because a single property cannot hold an entire map:

```cypher
// Example of an INVALID operation: Neo4j does not accept MAP as a property.
CREATE (:Person {
  name: 'Minh',
  address: {city: 'Hanoi'}
});
```

There are two alternative designs, depending on requirements:

1. **Flatten the data** when subfields are few and fixed: `addressCity: 'Hanoi'`, `addressDistrict: 'Cau Giay'`.
2. **Extract into a connected node** when an address has many fields, has history, is shared, or needs to be queried as an entity:

```cypher
CREATE
  (p:Person {personId: 'P-002', name: 'Minh'}),
  (a:Address {city: 'Hanoi', district: 'Cau Giay'})
CREATE (p)-[:HAS_ADDRESS]->(a)
RETURN p.name, a.city;
```

A map containing only valid property values can be used to **set individual properties** using `SET +=`:

```cypher
MATCH (p:Person {personId: 'P-002'})
SET p += {active: true, yearJoined: 2024}
RETURN properties(p) AS storedProperties;
```

This command adds/updates `active` and `yearJoined` individually; it does not store the map under a single key. If a map contains disallowed nested values, it must be transformed before writing.

### NODE, RELATIONSHIP, and PATH

Cypher can return node, relationship, and path objects for application processing or graph traversals:

```cypher
MATCH path = (p:Person)-[r:HAS_ADDRESS]->(a:Address)
RETURN
  p AS personNode,
  r AS addressRelationship,
  a AS addressNode,
  path AS matchedPath,
  nodes(path) AS nodeList,
  relationships(path) AS relationshipList;
```

Here, `p` is a `NODE`; `r` is a `RELATIONSHIP`; `path` is a `PATH`. These values **cannot be assigned directly to properties** such as `p.addressNode = a` or `p.savedPath = path`. To store links between entities, use actual relationships; to store descriptive information, extract the necessary primitive values.

Lists such as `nodes(path)` or `collect(p)` are lists containing graph entities; they can be returned in results but do not become valid property lists.

## 7. NULL and Non-Existent Properties

`null` means there is no defined value in an expression. When reading a non-existent property, Cypher generally returns `null`. Neo4j does not store a property with a `null` value as a separate data cell: **assigning `null` to a property is equivalent to deleting that property**.

```cypher
CREATE (p:Person {
  personId: 'P-003',
  name: 'Hoa',
  nickname: 'H'
})
SET p.nickname = null
RETURN
  p.nickname AS nickname,
  p.nickname IS NULL AS isMissing;
```

The result for `nickname` is `null` and `isMissing` is `true`. The `nickname` property has been removed from the node.

When checking for missing data, use `IS NULL` or `IS NOT NULL`, not `= null`:

```cypher
MATCH (p:Person)
WHERE p.nickname IS NULL
RETURN p.personId, p.name;
```

In Cypher's three-valued logic, a comparison involving `null` can yield `null` (neither `true` nor `false`). For example, `null = null` does not assert that two values are equal. The `coalesce` function helps select the first non-`null` value:

```cypher
MATCH (p:Person)
RETURN
  p.name,
  coalesce(p.nickname, '(no nickname)') AS displayedNickname;
```

Distinguish between the following three cases in business modeling:

| Case | Meaning |
| --- | --- |
| `isActive: false` | Explicitly known that the status is inactive |
| `nickname: ''` | Property exists but holds an empty string |
| No `nickname` | No value yet; reading will return `null` |

If the system needs to distinguish between "not provided", "not applicable", and "deleted", design appropriate business status fields; `null` alone cannot express all of those meanings.

## 8. Complete Example: Choosing Types When Modeling a Graph

Suppose we build a course graph consisting of `Learner`, `Course`, and the `ENROLLED_IN` relationship.

```cypher
CREATE
  (l:Learner {
    learnerId: 'L-001',
    fullName: 'Nguyen An',
    age: 24,
    active: true,
    interests: ['graph', 'backend'],
    joinedAt: datetime('2026-11-01T08:30:00+07:00')
  }),
  (c:Course {
    courseId: 'C-NEO4J',
    title: 'Cypher Fundamentals',
    hours: 12.5,
    publishedOn: date('2026-10-20')
  })
CREATE (l)-[:ENROLLED_IN {
  enrolledOn: date('2026-11-10'),
  progressPercent: 45.0
}]->(c)
RETURN l, c;
```

In this model:

- `learnerId` and `courseId` are `STRING` because they serve as business codes, not for arithmetic calculations.
- `age` is `INTEGER`, `active` is `BOOLEAN`.
- `interests` is a homogeneous string property list.
- `joinedAt` is `ZONED DATETIME` to preserve the timestamp along with its offset.
- `publishedOn` and `enrolledOn` are `DATE` because the business domain only needs the date.
- `hours` and `progressPercent` are `FLOAT` because they contain decimal parts.
- The `ENROLLED_IN` relationship has its own properties while accurately representing the semantics "a learner enrolls in a course".

Query to read data and output results as a map for an API:

```cypher
MATCH (l:Learner)-[enrollment:ENROLLED_IN]->(c:Course)
WHERE l.active = true
RETURN {
  learnerId: l.learnerId,
  learnerName: l.fullName,
  courseTitle: c.title,
  progressPercent: enrollment.progressPercent,
  enrolledOn: enrollment.enrolledOn
} AS enrollmentView;
```

`enrollmentView` is a query result map, **not a property stored on the graph**. The nodes and relationships are still stored according to the graph model.

## 9. Type Conversion and Input Validation

In CSV, JSON, or parameters from a Java application, a value may be passed as a string even when the domain requires a numeric, date, or boolean type. It must be validated and converted to the target type before writing.

```cypher
WITH {
  ageText: '29',
  scoreText: '8.5',
  activeText: 'true',
  joinedDateText: '2026-11-01'
} AS raw
RETURN
  toInteger(raw.ageText) AS age,
  toFloat(raw.scoreText) AS score,
  toBoolean(raw.activeText) AS isActive,
  date(raw.joinedDateText) AS joinedDate;
```

Principles to maintain:

1. **Determine the meaning before casting**: order code `'00042'` should be a string; quantity `42` is an integer.
2. **Do not store dates as strings if temporal operations are needed**: use `DATE` or the appropriate `DATETIME` type.
3. **Do not expect every conversion to succeed**: invalid input can lead to `null` or errors depending on the function and context. Validate data before writing and handle missing fields.
4. **Standardize types for the same property**: avoid having some nodes store `age` as `INTEGER` and other nodes store `age` as `STRING`; inconsistency makes filtering, aggregation, and API integration unpredictable.
5. **Use Cypher parameters for application data**: parameters can pass numbers, strings, dates/times, lists, or maps to update valid properties. Never concatenate input data directly into query strings.

Example of a parameterized query:

```cypher
CREATE (p:Person {
  personId: $personId,
  name: $name,
  age: $age,
  skills: $skills
})
RETURN p;
```

On the Java Driver side, `$age` must be passed as an integer and `$skills` as a list of strings if those are the defined business types. If `$skills` is replaced by a list containing maps, the property write operation will be invalid. Neo4j allows schema flexibility, yet applications still need a consistent data contract; on supported setups, property type constraints and other constraints supported by the edition/version in use can be added.

You can inspect the current value type using the `valueType()` function on Neo4j/Cypher versions that support it:

```cypher
MATCH (p:Person)
RETURN
  p.personId,
  valueType(p.age) AS ageType,
  valueType(p.skills) AS skillsType;
```

This function is useful when investigating inhomogeneous ingested data; check the documentation for your running Neo4j version to verify type names and support.

## 10. Common Errors and Fixes

| Scenario | Cause | Resolution |
| --- | --- | --- |
| Assigning `p.address = {city: 'Hue'}` | `MAP` is not a valid property value | Flatten into `p.addressCity` or create an `Address` node |
| Assigning `p.tags = ['graph', null]` | Property lists cannot store `null` elements | Filter out missing elements before writing |
| Assigning `p.items = [[1, 2], [3, 4]]` | Property lists do not support nested lists | Change the model or split into separate entities |
| Assigning `p.friend = otherNode` | `NODE` cannot be stored in a property | Create a relationship between the nodes |
| `WHERE p.field = null` | Comparing with `null` does not yield the intended condition | Use `p.field IS NULL` |
| Storing `price = 0.1 + 0.2` and doing exact comparison | Floating-point numbers have precision error | Use integers in the smallest unit when exactness is required |
| Storing `createdAt: '25/11/2026'` | Strings do not inherently carry date/time semantics | Convert and write using `DATE`/`DATETIME` types |
| Storing `age` properties in multiple types | Inconsistency caused by data ingestion | Normalize and validate input; consider type constraints |

## 11. Self-Check

**Question 1.** `RETURN {name: 'Lan', age: 29} AS profile` is valid. Can the entire `profile` value be assigned to `p.profile`?

*Answer:* No. `MAP` is valid in expressions/results, but it is not a property type; assign individual fields or convert into appropriate nodes/relationships.

**Question 2.** How do `['Cypher', 'Java']` and `['Cypher', null]` differ when used as a property?

*Answer:* The first list is a storable list of strings; the second list contains `null` and therefore cannot be used directly as a property list.

**Question 3.** What happens when running `SET p.nickname = null`?

*Answer:* The `nickname` property is removed from the node; subsequent access to `p.nickname` returns `null`.

**Question 4.** For `startAt` representing a transaction timestamp across multiple timezones, should `LOCAL DATETIME` or `ZONED DATETIME` be preferred?

*Answer:* Prefer `ZONED DATETIME` with an explicit offset/zone to avoid losing point-in-time information.

**Question 5.** Why is `MATCH (a)-[r]->(b) RETURN r` valid, whereas `SET a.savedRelationship = r` is invalid?

*Answer:* `r` is a `RELATIONSHIP` value usable in queries; to store links between entities, use relationships in the graph rather than storing relationship objects in properties.

---

**Remember:** Cypher operates on a richer type system than the set of storable property types. Choose valid scalar values or property lists for properties; use maps, nodes, relationships, and paths to construct results and model connections; handle `null` properly and normalize input types before writing data.
