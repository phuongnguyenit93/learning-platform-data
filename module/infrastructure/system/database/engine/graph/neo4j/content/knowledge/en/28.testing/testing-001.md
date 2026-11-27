# A Small Sample Dataset Covering All Relationships and Edge Cases in Neo4j

Testing a graph database cannot stop at creating two nodes and checking a single relationship. A Cypher query may work on a simple path yet fail when there are **two paths to the same destination**, **parallel relationships**, **cycles**, **self-loops**, **isolated nodes**, **missing properties**, or two tenants using the **same business key**. These cases affect the row count of `MATCH`, `OPTIONAL MATCH` semantics, `DISTINCT`, counting, traversal, Java mapping, and update logic.

This lesson belongs to the **Testing** chapter in the `DATABASE_ENGINE_GRAPH_NEO4J` module. We design a **fixture** (a small, deterministic test dataset) for a Neo4j property graph, specify exact expectations, and then use Cypher, the Neo4j Java Driver, and Spring Data Neo4j to verify the results. The fixture can be recreated in a test database, helping catch query bugs before optimizing indexes, constraints, or deploying the system.

**Goal:** a dataset small enough for a human to count by hand, yet diverse enough to test **nodes, relationships, directions, multiple combined patterns, paths, null/missing values, multi-tenancy, and boundary conditions**.

## 1. What must a good fixture prove?

An effective test dataset has three properties:

1. **Determinism:** the node count, relationship count, every key, and every expected result are known in advance. It does not depend on stale data or random traversal order.
2. **Intentional coverage:** every edge case exists because there is a specific query or rule to test, rather than adding arbitrary data.
3. **Isolation and reproducibility:** it does not mutate production data, does not let one test pollute another, and does not require Neo4j's internal IDs to remain constant.

Coverage matrix for this lesson:

| Case | Testing purpose | Illustrative data |
| --- | --- | --- |
| Normal nodes and multi-label nodes | Label filtering, entity mapping | Bình has `Test001Person` and `Test001Mentor` |
| Directed relationships | Avoiding outgoing/incoming direction confusion | An → Bình |
| Multiple relationships between the same node pair | `count(*)` differs from `count(DISTINCT ...)` | Two edges An → Bình |
| Two paths to one destination | Avoiding node duplication when counting paths | An → Bình → Dũng and An → Chi → Dũng |
| Cycle | Traversal can return to the starting node | An → Chi → An |
| Self-loop | System does not assume two distinct endpoints | Dũng → Dũng |
| Isolated node | Catching `MATCH` queries that drop nodes with no edges | Hạnh has no relationships |
| Two relationship types between Person nodes | Filtering by type instead of treating all edges identically | `FOLLOWS` and `MENTORS` |
| Relationships with properties | Filtering, counting, boundary-value testing | `score = 0`; missing `score` |
| Missing, empty, and zero node properties | Distinguishing `IS NULL`, empty string, and zero | Chi missing `email`, Hạnh `email = ''`, Dũng `age = 0` |
| Two tenants with the same ID | Testing composite keys and data isolation | T1/P01 and T2/P01 |
| Disconnected components | Avoiding false reachability assumptions | T2 has no `FOLLOWS` edges to T1 |

You do not need to simulate millions of records to verify semantics. Large datasets are for **performance testing**; small fixtures serve **correctness testing**.

## 2. Problem domain and target graph

Suppose the system has learners (`Person`), courses (`Course`), follow relationships (`FOLLOWS`), mentorship (`MENTORS`), and enrollments (`ENROLLED`). Each entity belongs to a tenant.

Business key conventions:

- Person: `(tenantId, personId)`.
- Course: `(tenantId, courseId)`.
- The `FOLLOWS` relationship has an additional `edgeId` to distinguish parallel edges in the fixture.
- The `ENROLLED` relationship has `status` and optionally `score`; **having no score** is different from **having score equal to 0**.

Core diagram in tenant T1:

```text
          ┌──────── FOLLOWS ─────────┐
          │                          ▼
An (P01) ──FOLLOWS×2──► Bình (P02) ──FOLLOWS──► Dũng (P04)
   │                         │                       ▲ │
   │                         └──FOLLOWS──► Chi (P03)│ │ SELF-LOOP
   └────FOLLOWS─────────────────────────► Chi ───────┘ │
                  ▲                      │              │
                  └──────── FOLLOWS ─────┘              └──► Dũng

Bình (P02) ──MENTORS──► An (P01) [different type]

Hạnh (P05) [no relationships]
```

The diagram is only illustrative; **the edge list with `edgeId` in Section 3 is the authoritative source**. The course enrollment part:

```text
T1/An     ──ENROLLED──► T1/C101 (Neo4j)
          └─ENROLLED──► T1/C102 (Java Driver)
T1/Bình   ──ENROLLED──► T1/C101
T1/Chi    ──ENROLLED──► T1/C102 [WITHDRAWN, score = 0]
T1/Dũng   [not enrolled]
T1/Hạnh   [isolated]

T2/Eva (personId = P01) ──ENROLLED──► T2/C101
```

Notably, **both T1/P01 and T2/P01 are valid** because `personId` is only unique **within a tenant**. Similarly, T1/C101 and T2/C101 are two different courses.

## 3. Creating the fixture with Cypher

**Run this only on a dedicated test database, ideally a disposable database/container that can be destroyed after testing.** This lesson uses the labels `Test001Person`, `Test001Course`, and relationship types prefixed with `TEST001_` to make sample data easy to identify. The `CREATE` statements below are **not idempotent**: if run twice without cleaning the database, counts will increase or hit constraint errors. This is intentional so tests do not mask duplicate data seeding.

### 3.1. Constraints to enforce composite keys

Create constraints on an empty database:

```cypher
CREATE CONSTRAINT test001_person_key IF NOT EXISTS
FOR (p:Test001Person)
REQUIRE (p.tenantId, p.personId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT test001_course_key IF NOT EXISTS
FOR (c:Test001Course)
REQUIRE (c.tenantId, c.courseId) IS UNIQUE;
```

Composite uniqueness does not require every node to possess all key properties. For real business data, validate missing keys in the pipeline or use existence-enforcing constraints when supported by your Neo4j version/edition. This fixture supplies complete keys for every node.

### 3.2. Creating 6 Person nodes, 3 Course nodes, and 14 relationships

Run the **entire `CREATE` statement below once**:

```cypher
CREATE
  // 5 Person nodes in T1, where Bình carries an additional Mentor label.
  (an:Test001Person {
    tenantId: 'T1', personId: 'P01',
    name: 'An', email: 'an@example.test',
    active: true, age: 30
  }),
  (binh:Test001Person:Test001Mentor {
    tenantId: 'T1', personId: 'P02',
    name: 'Bình', email: 'binh@example.test',
    active: true, age: 22,
    skills: ['Cypher', 'Java']
  }),
  (chi:Test001Person {
    tenantId: 'T1', personId: 'P03',
    name: 'Chi', active: false, age: 23
    // Intentionally omits the email property.
  }),
  (dung:Test001Person {
    tenantId: 'T1', personId: 'P04',
    name: 'Dũng', email: 'dung@example.test',
    active: true, age: 0
  }),
  (hanh:Test001Person {
    tenantId: 'T1', personId: 'P05',
    name: 'Hạnh', email: '', active: true
    // Empty email; no age; no relationships.
  }),
  // T2 Person sharing the same personId as An, but in a different tenantId.
  (eva:Test001Person {
    tenantId: 'T2', personId: 'P01',
    name: 'Eva', email: 'eva@example.test',
    active: true, age: 28
  }),

  (neo:Test001Course {
    tenantId: 'T1', courseId: 'C101', title: 'Neo4j', published: true
  }),
  (java:Test001Course {
    tenantId: 'T1', courseId: 'C102', title: 'Java Driver', published: false
  }),
  (neoT2:Test001Course {
    tenantId: 'T2', courseId: 'C101', title: 'Graph for T2',
    published: true
  }),

  // 8 FOLLOWS edges (R01 and R08 are parallel edges).
  (an)-[:TEST001_FOLLOWS {
    edgeId: 'R01', since: date('2026-01-01')
  }]->(binh),
  (an)-[:TEST001_FOLLOWS {
    edgeId: 'R02', since: date('2026-01-02')
  }]->(chi),
  (binh)-[:TEST001_FOLLOWS {edgeId: 'R03'}]->(chi),
  (chi)-[:TEST001_FOLLOWS {edgeId: 'R04'}]->(an),
  (binh)-[:TEST001_FOLLOWS {edgeId: 'R05'}]->(dung),
  (chi)-[:TEST001_FOLLOWS {edgeId: 'R06'}]->(dung),
  (dung)-[:TEST001_FOLLOWS {edgeId: 'R07'}]->(dung),
  (an)-[:TEST001_FOLLOWS {
    edgeId: 'R08', since: date('2026-02-01')
  }]->(binh),

  // Different type: Mentor relationship in the opposite direction of FOLLOWS An→Bình.
  (binh)-[:TEST001_MENTORS {edgeId: 'M01'}]->(an),

  // 5 ENROLLED edges.
  (an)-[:TEST001_ENROLLED {
    enrollmentId: 'E01', status: 'ACTIVE', score: 94
  }]->(neo),
  (binh)-[:TEST001_ENROLLED {
    enrollmentId: 'E02', status: 'ACTIVE'
    // Intentionally omits the score property.
  }]->(neo),
  (chi)-[:TEST001_ENROLLED {
    enrollmentId: 'E03', status: 'WITHDRAWN', score: 0
  }]->(java),
  (eva)-[:TEST001_ENROLLED {
    enrollmentId: 'E04', status: 'ACTIVE', score: 88
  }]->(neoT2),
  (an)-[:TEST001_ENROLLED {
    enrollmentId: 'E05', status: 'ACTIVE', score: 77
  }]->(java);
```

**Note on comment syntax:** some Cypher clients/versions may be sensitive to trailing comments inside map literals. If you encounter a parse error caused by inline comments, move the comments outside the map without changing any data. The `CREATE` statement above intentionally creates **9 nodes and 14 relationships**.

### 3.3. Expected data inventory

| Data type | Count |
| --- | ---: |
| `Test001Person` | 6 |
| `Test001Course` | 3 |
| Total nodes | **9** |
| `TEST001_FOLLOWS` | 8 |
| `TEST001_MENTORS` | 1 |
| `TEST001_ENROLLED` | 5 |
| Total relationships | **14** |

Edges of type `FOLLOWS` have IDs R01–R08; the mentorship edge is M01; enrollment edges are E01–E05. Relying on edge IDs allows exact verification when two relationships share the same start and end nodes, rather than visually inspecting a diagram.

## 4. Asserting counts instead of visually inspecting the graph

Neo4j Browser's graph visualization is helpful, but it is **not a test oracle**: nodes can overlap and parallel relationships are hard to distinguish. Return results as tables and compare them against expected values.

```cypher
MATCH (p:Test001Person)
RETURN count(p) AS actual,
       count(p) = 6 AS passed;
```

```cypher
MATCH (c:Test001Course)
RETURN count(c) AS actual,
       count(c) = 3 AS passed;
```

```cypher
MATCH ()-[r:TEST001_FOLLOWS]->()
RETURN count(r) AS actual,
       count(r) = 8 AS passed;
```

```cypher
MATCH ()-[r:TEST001_ENROLLED]->()
RETURN count(r) AS actual,
       count(r) = 5 AS passed;
```

In a test environment with this dedicated fixture, every `passed` field must be `true`. In an automated framework, you **must assert** that `passed == true` or `actual == expected`; merely executing a query without checking its result does **not** count as a test.

To verify that additional labels do not inflate the node count, check separately:

```cypher
MATCH (p:Test001Person:Test001Mentor)
RETURN collect(p.personId) AS mentorIds;
```

Returns `['P02']`. Bình is **one node with two labels**, not two separate nodes.

## 5. Directed relationships, multiple types, and parallel edges

### 5.1. Do not confuse edge count with target node count

```cypher
MATCH (an:Test001Person {
  tenantId: 'T1', personId: 'P01'
})-[r:TEST001_FOLLOWS]->(target:Test001Person)
RETURN count(r) AS relationships,
       count(DISTINCT target) AS uniqueTargets;
```

Expected result:

| relationships | uniqueTargets |
| ---: | ---: |
| **3** | **2** |

Both edges R01 and R08 go from An to Bình. If the application asks "How many people does An follow?", the answer is **2**; if it asks "How many outgoing follow relationship records exist?", the answer is **3**.

List the edges to inspect them clearly:

```cypher
MATCH (an:Test001Person {
  tenantId: 'T1', personId: 'P01'
})-[r:TEST001_FOLLOWS]->(target:Test001Person)
RETURN r.edgeId AS edgeId,
       target.personId AS targetId,
       r.since AS since
ORDER BY edgeId;
```

Expected: R01→P02, R02→P03, R08→P02. `r.since` also verifies the date property on the relationship.

### 5.2. Testing outgoing vs. incoming direction

```cypher
MATCH (binh:Test001Person {
  tenantId: 'T1', personId: 'P02'
})
OPTIONAL MATCH (follower:Test001Person)
  -[r:TEST001_FOLLOWS]->(binh)
RETURN count(r) AS incomingRelationships,
       count(DISTINCT follower) AS incomingPeople;
```

Returns **2 relationships** but only **1 follower** (An). If mistakenly written as `(binh)-[:TEST001_FOLLOWS]->(...)`, both the dataset and counts will differ. Avoid using an undirected pattern `-[:TYPE]-` when business logic distinguishes between "following" and "followed by".

### 5.3. Testing filtering by relationship type

```cypher
MATCH (binh:Test001Person {
  tenantId: 'T1', personId: 'P02'
})-[r]->(target:Test001Person)
RETURN type(r) AS relationshipType,
       target.personId AS targetId,
       count(*) AS n
ORDER BY relationshipType, targetId;
```

The results include FOLLOWS→P03, FOLLOWS→P04, and MENTORS→P01. A query that does not constrain the relationship type will include mentorship edges as well, breaking logic when the application only wants follow connections.

## 6. Cycles, self-loops, and two-hop paths

### 6.1. A self-loop is not a Cypher error

```cypher
MATCH (p:Test001Person)-[r:TEST001_FOLLOWS]->(p)
RETURN p.personId AS personId,
       r.edgeId AS edgeId;
```

Only **P04/R07** matches. If the business domain forbids a person from following themselves, this fixture case acts as a **negative case** for the service layer to reject creation. Yet it remains valuable for general queries: verifying that algorithms do not hang, do not assume the start and end nodes differ, and do not silently drop an existing edge.

### 6.2. Cycle returning to the starting node

```cypher
MATCH path =
  (an:Test001Person {tenantId: 'T1', personId: 'P01'})
  -[:TEST001_FOLLOWS]->
  (:Test001Person)
  -[:TEST001_FOLLOWS]->
  (an)
RETURN [n IN nodes(path) | n.personId] AS route;
```

Returns the path `P01 → P03 → P01`. A path can start and end at the **same node**. When test code inspects `nodes(path)`, the list length is **3** (with P01 at both start and end), even though there are only **2 distinct nodes**.

### 6.3. Counting paths vs. counting destinations

Pattern matching exactly two `FOLLOWS` edges in the outgoing direction:

```cypher
MATCH path =
  (an:Test001Person {tenantId: 'T1', personId: 'P01'})
  -[:TEST001_FOLLOWS]->
  (:Test001Person)
  -[:TEST001_FOLLOWS]->
  (dest:Test001Person)
RETURN count(path) AS paths,
       count(DISTINCT dest) AS uniqueDestinations;
```

Expected result on the sample data:

| paths | uniqueDestinations |
| ---: | ---: |
| **6** | **3** |

Manual breakdown:

- Two An→Bình edges, each with two next hops (Bình→Chi or Bình→Dũng): **4 paths**.
- One An→Chi edge, followed by Chi→An or Chi→Dũng: **2 paths**.
- Total **6 paths**; distinct destinations are `P01`, `P03`, and `P04`.

If searching only for paths reaching Dũng in exactly two hops:

```cypher
MATCH path =
  (an:Test001Person {tenantId: 'T1', personId: 'P01'})
  -[:TEST001_FOLLOWS]->
  (:Test001Person)
  -[:TEST001_FOLLOWS]->
  (dung:Test001Person {tenantId: 'T1', personId: 'P04'})
RETURN count(path) AS waysToDung;
```

The answer is **3**: An→Bình→Dũng via R01, via R08, and An→Chi→Dũng.

**Note:** these examples use **two explicit edge patterns**, independent of older or newer Cypher variable-length path syntax. For variable-length paths, you must also confirm uniqueness semantics and which relationships are allowed to repeat in your Cypher version.

## 7. Isolated nodes, OPTIONAL MATCH, and null values

### 7.1. Isolated nodes must appear when queries ask for "all"

Check for nodes with no relationships at all using a pattern existence subquery:

```cypher
MATCH (p:Test001Person {tenantId: 'T1'})
WHERE NOT EXISTS {
  MATCH (p)--()
}
RETURN p.personId AS personId, p.name AS name;
```

Expected: only **P05/Hạnh**, since Hạnh participates in no relationships. Here `EXISTS` checks all relationships regardless of direction or type; therefore Dũng is not isolated despite only having a self-loop. A query like `MATCH (p)-[:TEST001_ENROLLED]->(...)` will **omit** both Dũng and Hạnh. If an API needs every Person alongside their course count, use `OPTIONAL MATCH`:

```cypher
MATCH (p:Test001Person)
OPTIONAL MATCH (p)-[e:TEST001_ENROLLED]->(c:Test001Course)
RETURN p.tenantId AS tenantId,
       p.personId AS personId,
       count(e) AS enrollments
ORDER BY tenantId, personId;
```

Expected:

| tenantId | personId | enrollments |
| --- | --- | ---: |
| T1 | P01 | 2 |
| T1 | P02 | 1 |
| T1 | P03 | 1 |
| T1 | P04 | 0 |
| T1 | P05 | 0 |
| T2 | P01 | 1 |

**Counting trap:** for rows preserved by `OPTIONAL MATCH` when no relationship matches, `count(*)` still counts **1 row**. `count(e)` counts only non-`null` `e` values, which is correct for counting enrollments.

### 7.2. Missing property vs. empty string

Chi (T1/P03) **does not have an `email` property**; Hạnh (T1/P05) has `email = ''`. Both cases may trigger validation errors, yet they are **not equivalent in Cypher**:

```cypher
MATCH (p:Test001Person {tenantId: 'T1'})
WHERE p.email IS NULL
RETURN p.personId AS id;
```

Expected: **P03**.

```cypher
MATCH (p:Test001Person {tenantId: 'T1'})
WHERE p.email = ''
RETURN p.personId AS id;
```

Expected: **P05**.

Expressions like `p.email = null` must never be used to check for a missing property: use `IS NULL` or `IS NOT NULL`. Neo4j does not store a property with a `null` value as an ordinary node property; `SET p.email = null` removes that property.

### 7.3. Value 0 vs. nonexistent property

Dũng (T1/P04) has `age = 0`, while Hạnh has no `age`:

```cypher
MATCH (p:Test001Person {tenantId: 'T1'})
WHERE p.age = 0
RETURN p.personId AS id;
```

Returns **P04**.

```cypher
MATCH (p:Test001Person {tenantId: 'T1'})
WHERE p.age IS NULL
RETURN p.personId AS id;
```

Returns **P05**. In a Java mapper, avoid using primitive `int` for a numeric field that may be missing without an explicit default rule: use `Integer` or a DTO as appropriate.

### 7.4. Relationships with score equal to 0 vs. missing score

```cypher
MATCH (:Test001Person)-[e:TEST001_ENROLLED]->(:Test001Course)
RETURN e.enrollmentId AS id, e.status AS status, e.score AS score
ORDER BY id;
```

Expected:

| id | status | score |
| --- | --- | ---: |
| E01 | ACTIVE | 94 |
| E02 | ACTIVE | `null` |
| E03 | WITHDRAWN | 0 |
| E04 | ACTIVE | 88 |
| E05 | ACTIVE | 77 |

Tests must distinguish: `e.score IS NULL` returns **E02**; `e.score = 0` returns **E03**. When aggregating graded enrollments, `count(e.score)` returns **4**, whereas `count(*)` returns **5**. A `null` field may be interpreted by the application as "not yet graded"; `0` may be an actual score or a valid boundary value depending on business rules.

## 8. Tenant isolation and duplicate keys across tenants

The fixture intentionally uses `personId = 'P01'` for both **An (T1)** and **Eva (T2)**; course `C101` also appears in both tenants. This forces tests to target the **composite key**.

Query missing the tenant filter:

```cypher
MATCH (p:Test001Person {personId: 'P01'})
RETURN p.tenantId AS tenantId, p.name AS name
ORDER BY tenantId;
```

Returns two rows: **T1/An** and **T2/Eva**. That is not a data bug; it demonstrates that `personId` is not a global key.

Query with tenant filter:

```cypher
MATCH (p:Test001Person {
  tenantId: 'T1', personId: 'P01'
})-[e:TEST001_ENROLLED]->(c:Test001Course)
RETURN p.name AS name,
       c.tenantId AS courseTenant,
       c.courseId AS courseId
ORDER BY courseId;
```

Expected: **C101 and C102 from T1**, without mixing in T2's C101. You should also verify that enrollment relationships do not connect two different tenants:

```cypher
MATCH (p:Test001Person)-[e:TEST001_ENROLLED]->(c:Test001Course)
WHERE p.tenantId <> c.tenantId
RETURN count(e) AS crossTenantEnrollments;
```

Returns **0**. A uniqueness constraint on each label **does not automatically guarantee** that both endpoints of a relationship belong to the same tenant; this must be checked by business rules in the service/pipeline or via an audit query.

## 9. Negative testing: invalid data must be detected

A small fixture does not need to pre-populate every invalid record: some edge cases must **attempt to insert invalid data in a separate transaction** and verify that it is rejected/rolled back. This is especially important for constraints and transactions.

### 9.1. Violating Person key uniqueness

After creating the constraints in Section 3, the following statement intentionally attempts to create a second T1/P01 Person:

```cypher
// NEGATIVE TEST: expected to violate uniqueness constraint
CREATE (:Test001Person {
  tenantId: 'T1', personId: 'P01', name: 'Duplicate key'
});
```

**Expected:** Neo4j raises a constraint error; no new node is committed. Run this only in an isolated transaction/test when testing failure behavior—do not include this statement in the seed batch. If the statement succeeds, either the constraint does not exist / was not created properly, or the test label/key differs from expectations.

### 9.2. Same personId in a different tenant is valid

Conversely, An and Eva sharing `personId='P01'` is **valid** under composite uniqueness. An automated test must not assert that "`personId` appears only once across the entire graph".

### 9.3. Application validation and constraints are two separate layers

The following rules are **not enforced by uniqueness constraints alone**:

- `Person.email` must have a non-empty value.
- `ENROLLED.score` must be in the range `0..100` if non-null.
- `FOLLOWS` must not self-connect `p→p` if the business rules forbid self-following.
- A Person–Person pair may have at most one `FOLLOWS` edge if the business rules forbid parallel edges.
- `ENROLLED` must not connect two different tenants.

The fixture **intentionally includes several cases that violate optional business rules** (such as a self-loop, parallel edges, and an empty email) to see how queries handle them. If the real system **forbids** those situations, write-command tests must **reject** them, while dirty-data query tests can use a separate fixture/transaction to verify detection.

Do not enable an automatic "cleanup" rule during seeding that strips away edge cases; otherwise the test suite may turn green without verifying the intended behavior.

## 10. Summary assertions: a stable oracle table

A good test suite has an **oracle**: expected results calculated by hand rather than derived from the query under test.

| Assertion | Expected result |
| --- | --- |
| Number of Person nodes | **6** |
| Number of Course nodes | **3** |
| Number of FOLLOWS edges | **8** |
| Number of MENTORS edges | **1** |
| Number of ENROLLED edges | **5** |
| Total relationships | **14** |
| Person nodes with Mentor label | **1** (T1/P02) |
| Outgoing FOLLOWS from T1/P01 | **3 edges**, **2 targets** |
| Incoming FOLLOWS to T1/P02 | **2 edges**, **1 person** |
| FOLLOWS self-loops | **1** (R07) |
| Paths of exactly 2 FOLLOWS from T1/P01 | **6** |
| Distinct destinations after exactly 2 FOLLOWS from T1/P01 | **3** |
| Paths of exactly 2 FOLLOWS from T1/P01 to T1/P04 | **3** |
| Person nodes with no relationships at all | **1** (T1/P05) |
| Person in T1 missing email | **1** (P03) |
| Person in T1 with empty email | **1** (P05) |
| ENROLLED relationships missing score | **1** (E02) |
| ENROLLED relationships with score = 0 | **1** (E03) |
| ACTIVE enrollments | **4** |
| Cross-tenant ENROLLED relationships | **0** |

Every corresponding test should assert on **stable values or result sets**. Do not assert on node/path ordering if the Cypher query omits `ORDER BY`.

## 11. Turning verification queries into automated tests

### 11.1. Cypher returning a pass/fail flag

Example checking the Person count:

```cypher
MATCH (p:Test001Person)
WITH count(p) AS actual
RETURN actual,
       6 AS expected,
       actual = 6 AS passed;
```

Checking An's follow set **independently of ordering** by counting target nodes:

```cypher
MATCH (an:Test001Person {
  tenantId: 'T1', personId: 'P01'
})-[:TEST001_FOLLOWS]->(p:Test001Person)
RETURN count(DISTINCT p) AS uniqueTargetCount;
```

Expected = **2**. If you need to match the exact set `P02, P03`, use `RETURN DISTINCT p.personId ORDER BY p.personId`, and then assert against a sorted list or compare ID sets in Java.

### 11.2. JUnit 5 + Neo4j Java Driver

Example test snippet **after the fixture from Section 3 has been seeded into the test database**:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

class FixtureQueryTest {

    private final Driver driver;

    FixtureQueryTest(Driver driver) {
        this.driver = driver; // Provided by test configuration.
    }

    @Test
    void followsFromAnHasThreeEdgesButTwoDestinations() {
        try (Session session = driver.session()) {
            var record = session.run("""
                MATCH (:Test001Person {
                    tenantId: 'T1', personId: 'P01'
                })-[r:TEST001_FOLLOWS]->(p:Test001Person)
                RETURN count(r) AS edges,
                       count(DISTINCT p) AS destinations
                """).single();

            assertEquals(3L, record.get("edges").asLong());
            assertEquals(2L, record.get("destinations").asLong());
        }
    }

    @Test
    void isolatedPersonStillExists() {
        try (Session session = driver.session()) {
            var record = session.run("""
                MATCH (p:Test001Person {
                    tenantId: 'T1', personId: 'P05'
                })
                RETURN NOT EXISTS { MATCH (p)--() } AS isolated
                """).single();

            assertTrue(record.get("isolated").asBoolean());
        }
    }
}
```

This is an **illustrative test snippet focusing on assertions**, not a complete test class configured for JUnit to auto-inject `Driver`. In a real project, create `Driver` through a test fixture/configuration, `@BeforeAll`/`@AfterAll`, or Spring Test, and close it according to its lifecycle. The key is that every assertion reads the returned value and checks it against a **predefined expected value**.

### 11.3. Testcontainers and Spring Data Neo4j

For integration tests, Testcontainers can start an **ephemeral Neo4j container**, seed the fixture, and execute repositories or `Neo4jClient`. An illustrative connection skeleton:

```java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.testcontainers.containers.Neo4jContainer;

// Illustrative example; lifecycle can be managed by JUnit @Container.
String testPassword = "test-only-password";
try (Neo4jContainer<?> neo4j =
         new Neo4jContainer<>("neo4j:5")
             .withAdminPassword(testPassword)) {

    neo4j.start();

    try (Driver driver = GraphDatabase.driver(
            neo4j.getBoltUrl(),
            AuthTokens.basic("neo4j", testPassword))) {

        driver.verifyConnectivity();

        // Seed the Cypher statements from Section 3.
        // Run queries and assert the expectations from Section 10.
    }
}
```

**This example only demonstrates connection setup and lifecycle**; real usage requires compatible Testcontainers dependencies, a running Docker daemon, seeding logic, and test assertions. Pin a **verified** image tag instead of a floating `neo4j:5` tag when CI reproducibility is required. When testing SDN, match the image version to your Spring Boot/SDN, Java Driver, and Cypher versions.

For Spring Boot tests, you can use `@DataNeo4jTest` or `@SpringBootTest` combined with a test container/configuration depending on the goal: repository mapping, graph updates, transactions, or the full application context.

**Mapping and persistence must be tested separately:** a Cypher query returning accurate rows does not prove that `@Node`, `@Relationship`, `@RelationshipProperties`, and `repository.save()` behave properly, especially when entities only load a partial subgraph.

## 12. Test isolation, fixture reset, and preventing flaky tests

A good fixture is not just about having the right data: **tests must be repeatable without interfering with one another**.

### 12.1. Isolation strategies

| Strategy | Strengths | Caveats |
| --- | --- | --- |
| Fresh database/Neo4j container per suite | No leftover data; predictable schema and resources | Container startup overhead |
| Dedicated database per test group | Easy separation of permissions and schema | Neo4j edition/privileges may restrict database creation |
| Transaction rollback per test | Fast when supported by the framework | Does not apply to operations committed in other transactions; DDL behavior may differ |
| Namespacing with `testRunId` | Multiple test groups share one DB while staying distinguishable | Every query and cleanup must filter by the exact namespace |
| Deleting data by test label after suite | Reuses the test DB | **Safe only in a dedicated test DB**; must control links outside the test labels |

Prefer a dedicated container/database because absolute counts are easy to assert. A query like `MATCH (p:Test001Person) RETURN count(*)` becomes unreliable if multiple tests concurrently create nodes with that label in a shared database.

### 12.2. Intentional cleanup

**Only in a database dedicated to this fixture**, after confirming no other data shares those nodes, you can clean up with:

```cypher
MATCH (p:Test001Person)
DETACH DELETE p;
```

```cypher
MATCH (c:Test001Course)
DETACH DELETE c;
```

`DETACH DELETE` removes each node **and all of its adjacent relationships**. Do not run these statements against labels that overlap real business data or a shared graph with links outside the test scope. With Testcontainers, tearing down the container after the suite is usually safer and simpler than writing broad cleanup scripts.

The constraints `test001_person_key` and `test001_course_key` remain even after deleting all nodes; if you need a completely fresh database, manage schema lifecycle through the test environment as well.

### 12.3. Common causes of flaky tests

- Relying on `elementId()` or internal IDs across graph rebuilds.
- Relying on the order in which Neo4j returns nodes/relationships without `ORDER BY`.
- Relying on system time (`date()`, `datetime()`) instead of fixed dates in the fixture.
- Using `MERGE` to seed and accidentally masking duplicate seeds; or running `CREATE` multiple times on an unreset DB.
- Sharing one database across parallel tests and asserting global node counts.
- Not waiting for indexes/constraints to come online when tests depend on schema.
- Checking query tuning with `PROFILE` and assuming the plan or DB Hits will never change across server versions.

## 13. Distinguishing correctness tests from performance tests

Use the same small fixture to verify structure and semantics; **do not use it as proof of production performance**.

| Test type | Appropriate dataset | Appropriate assertions |
| --- | --- | --- |
| Service unit test | Mocked objects/DTOs | Input mapping, business conditions |
| Cypher integration test | 9-node / 14-relationship fixture | Row counts, ID sets, direction/type, paths, nulls |
| SDN integration test | Small fixture on real Neo4j | Mapping and avoiding unintended edge additions/deletions |
| Constraint/negative test | Fixture + isolated failing transaction | Duplicates rejected, proper rollback |
| Performance/load test | Large graph with representative distribution and degree | Latency percentiles, DB Hits, CPU/memory, and throughput |

A query planner may choose `NodeByLabelScan` on a 9-node graph, which is completely reasonable. Do not write brittle tests asserting that a query **must** use `NodeIndexSeek` or incur an exact number of DB Hits on a tiny dataset. For query tuning, use `EXPLAIN`/`PROFILE` to understand the plan; derive performance thresholds from a representative environment and workload.

## 14. Workflow for designing a fixture for a new feature

When developing a query such as "two-hop follow recommendations" or "courses a user is currently taking", you can follow this sequence:

1. **List the expected semantics:** return unique nodes or all paths? Are parallel relationships counted? Is tenant filtering applied?
2. **Choose a small size:** small enough to count by hand, such as 5–10 nodes and a set of labeled/numbered edges.
3. **Add control cases:** an unconnected node, a node with missing properties, and a node with the same business ID in another tenant.
4. **Add tricky structures:** at least two paths to the same destination, a cycle, a self-loop, and unrelated edge types.
5. **Add boundary values:** empty string, zero value, missing property, and ACTIVE/WITHDRAWN statuses.
6. **Write the oracle before the code:** count table, key sets, and allowed vs. disallowed paths.
7. **Seed under a clear contract:** constraints first, data second; no random inserts, no current timestamps.
8. **Assert via Cypher or Java:** do not rely solely on opening Browser to look at the graph.
9. **Separate negative tests from shared seeding:** run negative constraint tests in an isolated transaction/DB.
10. **Isolate and clean up:** use Testcontainers or a controlled test scope; never run cleanup on production.

### Self-practice exercises

**Question 1.** Why is the assertion "An follows 3 people" wrong for this fixture, even though An has three outgoing `FOLLOWS` relationships?

**Question 2.** How many paths of length exactly two `FOLLOWS` edges go from T1/P01 to T1/P04? Explain the role of parallel edges.

**Question 3.** How do `count(*)` and `count(e)` differ when using `OPTIONAL MATCH` for Hạnh?

**Question 4.** Why does `p.email IS NULL` find Chi but not Hạnh?

**Question 5.** If you run `MATCH (p:Test001Person {personId:'P01'})` and forget `tenantId`, what results appear and what is the risk?

**Question 6.** Why does testing on 9 nodes fail to prove that an index seek is always faster than a label scan?

**Question 7.** If a query returns 6 paths but only 3 distinct destination nodes, what should the API return when the business question is "which people are reachable"?

**Suggested answers:** (1) An has three edges, but only two targets: Bình and Chi. (2) Three paths: two via Bình using R01/R08, and one via Chi. (3) `count(*)` counts the null row preserved by the optional match, whereas `count(e)` only counts actual edges. (4) Hạnh has an empty email string, whereas Chi has no email property. (5) Both T1's An and T2's Eva appear; risk of cross-tenant data leakage or collision. (6) The dataset is too small, and the planner depends on real statistics and workload. (7) Return distinct destination nodes using `DISTINCT` or an appropriate reachability mechanism.

## References

- [Neo4j Cypher Manual — Patterns](https://neo4j.com/docs/cypher-manual/current/patterns/): nodes, relationships, directions, and pattern matching.
- [Neo4j Cypher Manual — OPTIONAL MATCH](https://neo4j.com/docs/cypher-manual/current/clauses/optional-match/): rows with null values when no relationship is found.
- [Neo4j Cypher Manual — Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/): `count()`, `collect()`, and `DISTINCT`.
- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/): uniqueness and business key enforcement.
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/): executing queries and reading results in Java tests.
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/): integration testing, entity/relationship mapping, and persisting graphs.

**Key takeaway:** a good Neo4j fixture does not need a lot of data; it needs **the exact cases most likely to break queries**. Include clear business keys and counts, parallel edges, cycles, isolated nodes, null/empty/zero values, two tenants, and an expected-results table before writing tests. From there, every change to Cypher, the Java Driver, or Spring Data Neo4j can be verified for **correctness** without relying on visual diagrams or random data.
