# Traversing Relationships with $graphLookup and Controlling Depth

Real-world applications do not only store independent documents. An employee may report to a manager, a department may have sub-departments, a category may span multiple tiers, or an airport may connect to other airports. Such data forms a **graph** consisting of **vertices** and **edges**. When you want to find "all subordinates of the director," "the management chain from an employee up to executive leadership," or "destinations reachable within at most two transfers," a standard single-level join is not enough.

In the **MongoDB Aggregation Framework**, the **`$graphLookup`** stage performs a **recursive search** across relationships stored in fields, returning documents reachable from one or more starting values. This stage provides a depth limit parameter **`maxDepth`**, reports depth via **`depthField`**, and allows pruning traversed nodes using **`restrictSearchWithMatch`**.

This lesson belongs to the **Advanced Aggregation** chapter of the *Database Engine Document MongoDB* module, focusing on determining **traversal direction**, **depth**, **stopping conditions**, **indexes**, **cycles**, as well as memory and sharding limits when applying `$graphLookup` in production systems.

After this lesson, you will be able to:

- Distinguish a single-level `$lookup` from a multi-level `$graphLookup`.
- Correctly configure `startWith`, `connectFromField`, `connectToField`, `from`, and `as`.
- Query both **descendants** and **ancestors** over the same organizational structure.
- Accurately interpret **`maxDepth: 0`, `maxDepth: 1`** and **`depthField`** values starting at **0**.
- Understand how `restrictSearchWithMatch` can **prune entire traversal branches**, unlike `$filter` applied after traversal completes.
- Sort results given that `$graphLookup` does not guarantee array order, and count nodes per level.
- Handle cyclic relationships, multi-edge arrays, missing/duplicate keys, and tenant boundaries.
- Design indexes on joined fields, limit input roots, read `explain` output, and account for memory/version limits.
- Write corresponding pipelines in `mongosh` and the MongoDB Java Sync Driver.

> **Version note:** Syntax and depth examples use the `$graphLookup` mechanism available in MongoDB 7.0, 8.0, and compatible versions. Certain **memory / spill-to-disk** behaviors differ across server releases: MongoDB 7.0/8.0 documentation specifies a dedicated 100 MB limit for `$graphLookup` where `allowDiskUse` does not allow exceeding that limit, whereas current Database Manual documentation describes spilling when exceeding 100 MB if permitted. Always check documentation for **your exact server version** before designing high-volume workloads; do not infer spill behavior from a generic example.

## 1. Why Are Recursive Queries Needed?

Consider an HR hierarchy:

~~~text
CEO
├── A (Engineering Lead)
│   ├── C (Platform Team)
│   │   └── E (Engineer)
│   └── D (QA Team)
│       └── I (QA Engineer)
└── B (Operations Lead)
    ├── F (Infrastructure Team)
    │   └── G (Infrastructure Engineer)
    └── H (Operations Staff)
~~~

Each employee stores only their **direct manager ID**:

~~~javascript
{
  employeeId: "E",
  managerId: "C"
}
~~~

To find E's direct manager, a single lookup by `managerId` suffices. However, to walk from E up through C → A → CEO, or from CEO down to all of A/B/C/D/E/F/G/H/I, the application must repeatedly follow related nodes over an **arbitrary number of hops not fixed in advance**.

Three common implementation strategies:

1. **Multiple application queries:** fetch level-1 managers, then level-2, and continue; easily causes many round-trips and forces the app to manage loops and limits manually.
2. **Pre-storing all ancestors/descendants:** fast to read, complex to update when the hierarchy changes; requires maintaining derived data.
3. **Using `$graphLookup`:** lets MongoDB perform recursive traversal inside aggregation, with parameters to bound hop depth and filter traversed documents.

`$graphLookup` does not require a separate "graph database." Vertices remain documents in a collection, and edges can be scalar reference fields or arrays of reference values.

### 1.1. How Do `$lookup` and `$graphLookup` Differ?

| Aspect | `$lookup` | `$graphLookup` |
|---|---|---|
| Typical goal | Join documents to another collection. | Follow relationships **recursively across multiple levels**. |
| Levels of relation | One join per stage; stages can be nested by design. | Automatically expands via `connectFromField`/`connectToField` until stopping. |
| Depth limit | No `maxDepth` for recursive traversal. | Supports `maxDepth`. |
| Depth metadata | Does not automatically attach node depth. | Supports `depthField` (starting from 0). |
| Filtering | Query/pipeline filter inside lookup. | `restrictSearchWithMatch` applied during traversal. |
| Output | Array of joined documents. | Array of documents reachable along the relationship. |

Do not use `$graphLookup` merely to replace a simple `$lookup` when recursion is unnecessary: a recursive stage carries its own costs and semantics.

## 2. Algorithmic Model of `$graphLookup`

Basic structure:

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    as: "descendants",
    maxDepth: 2,
    depthField: "depth",
    restrictSearchWithMatch: { active: true }
  }
}
~~~

Where:

| Parameter | Required? | Meaning |
|---|---|---|
| **`from`** | Yes | Target collection name **in the same database** containing documents to traverse. |
| **`startWith`** | Yes | Aggregation **expression** producing initial search values from the input document; can be a literal, field path, or expression/array. |
| **`connectFromField`** | Yes | Field name on each matched node whose value is used to keep expanding edges. |
| **`connectToField`** | Yes | Field name in the `from` collection matched against initial and expanded search values. |
| **`as`** | Yes | Array field name attached to the input document holding all discovered nodes. |
| **`maxDepth`** | No | Non-negative integer capping maximum recursion depth; **0** still performs one initial lookup. |
| **`depthField`** | No | Field name added to each matched document recording traversal depth as `NumberLong`; **starts at 0**. |
| **`restrictSearchWithMatch`** | No | Query filter restricting which `from` documents are accepted and further expanded during traversal. |

### 2.1. Reading Traversal Step by Step

Suppose the input document has `employeeId = "CEO"` and `startWith: "$employeeId"`:

~~~text
Input document (CEO)
     |
     | startWith = "CEO"
     v
Find from.employees with managerId = "CEO"  --> A, B (depth 0)
     |
     | Take employeeId from A and B
     v
Find managerId = "A" or "B"                 --> C, D, F, H (depth 1)
     |
     | Take employeeId from C, D, F, H
     v
Find managerId = "C", "D", "F", "H"         --> E, I, G (depth 2)
     |
     v
Reached maxDepth = 2 -> stop expanding deeper
     |
     v
Attach discovered nodes to array CEO.descendants
~~~

The key mechanism is **matching `connectToField`**, then **taking `connectFromField` from the newly matched nodes** to expand the next round. Swapping those two fields typically makes the query traverse **in the opposite direction** or start from the wrong node.

### 2.2. Do Not Confuse `startWith` with the First Returned Document

`startWith` produces the **initial search value**, not automatically including the input document in the output. In the descendants query, startWith is the CEO's ID, yet the first round looks for people with `managerId = "CEO"`, namely **A and B**—not the CEO itself.

Conversely, if `startWith: "$employeeId"` and `connectToField: "employeeId"`, then the first matched node may indeed be the input employee itself. Write out the first comparison explicitly as:

~~~text
from.<connectToField> == evaluated(startWith)
~~~

Checking this line before running a pipeline catches most reversed-direction mistakes.

### 2.3. `startWith` and `connectFromField` as Arrays

`startWith` can evaluate to an **array of values**; MongoDB starts traversal simultaneously from all of those elements. If `connectFromField` on a visited node is an array, MongoDB follows **every edge value** in that array.

This fits many-to-many graphs such as airports connected to multiple airports or users with multiple friends. You do not need a separate `$graphLookup` call per array edge.

### 2.4. `$graphLookup` Output Has No Guaranteed Order

Documents inside the `as` array **have no guaranteed order**. Never assume index 0 is the closest manager, or that all depth-0 nodes always precede depth-1 nodes in the array. If ordered display is needed, add a sort step after traversal; `$sortArray` and `$unwind` are shown later.

## 3. Reproducible Practice Dataset

All examples use the `graph_lookup_lab` database. Employee documents contain:

- `employeeId`: stable business key in the demo model.
- `managerId`: direct manager code; CEO has `managerId: null`.
- `name` and `department`: display metadata.
- `active`: status flag to demonstrate branch pruning.

Run `insertMany` only on an **empty lab collection**. Re-running with the same `_id` triggers a duplicate key error; do not drop production or shared databases to reset examples.

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

lab.employees.insertMany([
  {
    _id: "E-CEO",
    employeeId: "CEO",
    managerId: null,
    name: "CEO",
    department: "EXEC",
    active: true
  },
  {
    _id: "E-A",
    employeeId: "A",
    managerId: "CEO",
    name: "Engineering Lead",
    department: "ENG",
    active: true
  },
  {
    _id: "E-B",
    employeeId: "B",
    managerId: "CEO",
    name: "Operations Lead",
    department: "OPS",
    active: true
  },
  {
    _id: "E-C",
    employeeId: "C",
    managerId: "A",
    name: "Platform Team",
    department: "ENG",
    active: true
  },
  {
    _id: "E-D",
    employeeId: "D",
    managerId: "A",
    name: "QA Team",
    department: "ENG",
    active: false
  },
  {
    _id: "E-E",
    employeeId: "E",
    managerId: "C",
    name: "Engineer",
    department: "ENG",
    active: true
  },
  {
    _id: "E-F",
    employeeId: "F",
    managerId: "B",
    name: "Infrastructure Team",
    department: "OPS",
    active: true
  },
  {
    _id: "E-G",
    employeeId: "G",
    managerId: "F",
    name: "Infrastructure Engineer",
    department: "OPS",
    active: true
  },
  {
    _id: "E-H",
    employeeId: "H",
    managerId: "B",
    name: "Operations Staff",
    department: "OPS",
    active: true
  },
  {
    _id: "E-I",
    employeeId: "I",
    managerId: "D",
    name: "QA Engineer",
    department: "ENG",
    active: true
  }
])

lab.employees.find(
  {},
  { _id: 0, employeeId: 1, managerId: 1, active: 1 }
).sort({ employeeId: 1 })
~~~

### 3.1. Exact Fixture Structure

~~~text
CEO [EXEC, active]
|
|-- A [ENG, active]                         Direct report
|   |-- C [ENG, active]                     Grandchild level
|   |   +-- E [ENG, active]                 Deeper level
|   +-- D [ENG, INACTIVE]
|       +-- I [ENG, active]
|
+-- B [OPS, active]
    |-- F [OPS, active]
    |   +-- G [OPS, active]
    +-- H [OPS, active]
~~~

CEO's descendants **without an active filter** are A, B, C, D, E, F, G, H, I — **9** employees total. When traversing only **active nodes**, D is excluded and the branch under D (I) is not reached through D either; the result set is A, B, C, E, F, G, H — **7** employees total.

### 3.2. Creating Lab Indexes

~~~javascript
// Business ID key; must be unique in the demo model.
lab.employees.createIndex(
  { employeeId: 1 },
  { unique: true, name: "ux_employeeId" }
)

// Enables looking up employees by direct manager.
lab.employees.createIndex(
  { managerId: 1 },
  { name: "ix_managerId" }
)

// Useful when traversal also filters active,
// though verify against explain and real workload.
lab.employees.createIndex(
  { managerId: 1, active: 1 },
  { name: "ix_managerId_active" }
)
~~~

For descendant queries, the engine typically looks up `managerId` in `from`. For ancestor queries, the engine looks up `employeeId`. Therefore an index on the **`connectToField` of the traversal direction** is a primary candidate; do not assume indexing only `managerId` optimizes both directions equally.

## 4. Finding All Subordinates: Top-Down Traversal

To find CEO's descendants, start with the **CEO's ID** and find documents whose **`managerId` equals that ID**. For each matched employee, take their `employeeId` to find the next tier of subordinates:

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      depthField: "level"
    }
  },
  {
    $project: {
      _id: 0,
      employeeId: 1,
      descendantIds: "$descendants.employeeId",
      descendantCount: { $size: "$descendants" }
    }
  }
])
~~~

On this fixture, `descendantCount` is **9**. The `descendantIds` array contains A, B, C, D, E, F, G, H, I, though **order is not guaranteed**. Distinguish carefully:

~~~text
Input: employeeId = "CEO"
        |
        v
Lookup from.employee.managerId = "CEO" -> A, B
        |
        +-> take A.employeeId = "A" to find managerId = "A" -> C, D
        +-> take B.employeeId = "B" to find managerId = "B" -> F, H
        ...
~~~

**Why not start from `managerId`?** The CEO document has `managerId: null`; using `startWith: "$managerId"` with `connectToField: "managerId"` would ask "who has managerId null?" instead of walking CEO's reporting tree. Starting value and edge direction must be chosen together.

### 4.1. Returning Sorted Names and Depths

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      depthField: "level",
      maxDepth: 2
    }
  },
  {
    $set: {
      descendants: {
        $sortArray: {
          input: "$descendants",
          sortBy: { level: 1, employeeId: 1 }
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      employeeId: 1,
      "descendants.employeeId": 1,
      "descendants.name": 1,
      "descendants.level": 1
    }
  }
])
~~~

`$sortArray` is supported starting in MongoDB **5.2**. The example has `level` and `employeeId`, which suffices to sort by level and then by employee ID. Never rely on the raw `$graphLookup` element order for tree rendering or assume index 0 has any special meaning.

### 4.2. Returning a "Flat" Result Instead of One Large Array

If an API needs one row per descendant, use `$unwind`:

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      depthField: "level",
      maxDepth: 2
    }
  },
  { $unwind: "$descendants" },
  {
    $project: {
      _id: 0,
      employeeId: "$descendants.employeeId",
      name: "$descendants.name",
      managerId: "$descendants.managerId",
      level: "$descendants.level"
    }
  },
  { $sort: { level: 1, employeeId: 1 } }
])
~~~

In the fixture, the pipeline returns **9 pipeline documents**, each representing one descendant with `level`. This is convenient for counting/grouping by level, though `$graphLookup` **still traverses and builds the full array** before `$unwind`; do not assume unwinding eliminates traversal resource limits.

### 4.3. Counting Employees at Each Level

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      maxDepth: 2,
      depthField: "level"
    }
  },
  { $unwind: "$descendants" },
  {
    $group: {
      _id: "$descendants.level",
      employees: { $sum: 1 },
      employeeIds: { $addToSet: "$descendants.employeeId" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Expected output:

| `_id` = level | Employee Count | Employee ID Set |
|---:|---:|---|
| 0 | 2 | A, B |
| 1 | 4 | C, D, F, H |
| 2 | 3 | E, G, I |

`$addToSet` produces a **set** of IDs, but element order inside the resulting array is not guaranteed. For level counts, `$sum: 1` alone is enough; include IDs only when actually needed and watch output size.

## 5. Finding the Management Chain: Bottom-Up Traversal

Over the same `employees` collection, we can find **ancestors** by reversing the join direction.

Employee G has `managerId: "F"`. To walk up the chain:

1. Read G's `managerId` (`"F"`).
2. Find the person with `employeeId: "F"`.
3. Read F's `managerId` (`"B"`), find `employeeId: "B"`.
4. Continue up to CEO.

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "G" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$managerId",
      connectFromField: "managerId",
      connectToField: "employeeId",
      as: "ancestors",
      depthField: "level"
    }
  },
  {
    $project: {
      _id: 0,
      employeeId: 1,
      name: 1,
      "ancestors.employeeId": 1,
      "ancestors.name": 1,
      "ancestors.level": 1
    }
  }
])
~~~

For G, ancestors are **F (level 0), B (level 1), CEO (level 2)**. The `ancestors` array can appear in any order.

### 5.1. Comparing Traversal Directions

| Goal | `startWith` | `connectFromField` | `connectToField` | Reading the Relationship |
|---|---|---|---|---|
| Find **descendants** | `"$employeeId"` | `"employeeId"` | `"managerId"` | Find who has `managerId` equal to the current node's ID. |
| Find **ancestors** | `"$managerId"` | `"managerId"` | `"employeeId"` | Find who has `employeeId` equal to the current manager ID. |

Use this verification formula:

~~~text
First lookup searches for:
  from.connectToField = evaluated(startWith)

Each expansion searches for:
  from.connectToField = connectFromField value of newly matched node
~~~

There is no automatic "walk backward" switch in `$graphLookup`; swapping the fields on both sides is how you reverse direction.

### 5.2. Sorting the Management Chain Nearest to Farthest

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "G" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$managerId",
      connectFromField: "managerId",
      connectToField: "employeeId",
      as: "ancestors",
      depthField: "level"
    }
  },
  {
    $set: {
      ancestors: {
        $sortArray: {
          input: "$ancestors",
          sortBy: { level: 1, employeeId: 1 }
        }
      }
    }
  },
  { $project: { _id: 0, employeeId: 1, ancestors: 1 } }
])
~~~

After sorting, the chain runs **F → B → CEO**. To display top-down instead, change `level: 1` to `level: -1`. **Depth 0 is the direct manager**, not employee G themselves.

### 5.3. Ancestors with Limited Depth

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "G" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$managerId",
      connectFromField: "managerId",
      connectToField: "employeeId",
      as: "managers",
      maxDepth: 1,
      depthField: "level"
    }
  }
])
~~~

With `maxDepth: 1`, only **F (level 0)** and **B (level 1)** are returned; CEO at level 2 is omitted. This expresses "at most **two management levels** starting from the direct manager" in the fixture.

## 6. Properly Understanding `maxDepth` and `depthField`

These are the two primary parameters for **controlling traversal depth**. They are related but serve distinct roles:

- **`maxDepth`** controls **how deep the traversal is allowed to expand**.
- **`depthField`** writes the reached depth onto each output document so you can inspect, display, filter, or group by it.

### 6.1. Depth Starts at 0, Not 1

When finding CEO's descendants:

~~~text
CEO          -> input document, not counted inside descendants
├─ A, B      -> depth 0  (first lookup pass)
├─ C,D,F,H   -> depth 1  (second expansion pass)
└─ E,I,G     -> depth 2  (third expansion pass)
~~~

Hence "direct reports" corresponds to **`maxDepth: 0`**, not `maxDepth: 1`. Saying "up to three subordinate tiers" corresponds to `maxDepth: 2`.

### 6.2. `maxDepth` Table on the Fixture

| `maxDepth` | Returned Nodes | Node Count | Meaning |
|---:|---|---:|---|
| 0 | A, B | 2 | Direct reports only. |
| 1 | A, B, C, D, F, H | 6 | Direct reports plus one tier below them. |
| 2 | A, B, C, D, E, F, G, H, I | 9 | Three tiers of descendants. |
| 3 | Same as level 2 on fixture | 9 | No deeper nodes exist. |
| Omitted | All reachable nodes | 9 | Traverses until no new matches exist in the fixture. |

`maxDepth` must be a **non-negative integer**. Negative numbers or invalid types do not mean "unlimited"; to run unbounded depth, **omit the parameter**, though doing so can be very expensive on real graphs.

### 6.3. Example: Up to Two Tiers of Descendants

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      maxDepth: 1,
      depthField: "level"
    }
  },
  {
    $project: {
      _id: 0,
      employeeId: 1,
      count: { $size: "$descendants" },
      descendantIds: "$descendants.employeeId"
    }
  }
])
// CEO has 6 descendants across levels 0 and 1.
~~~

### 6.4. `maxDepth: 0` Equals a Single-Level Lookup

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "directReports",
      maxDepth: 0
    }
  }
])
~~~

The result is A and B; the MongoDB Manual describes `maxDepth: 0` as equivalent to a **non-recursive `$graphLookup` search**. When only a single-level join is needed, `$lookup` can still be the simpler choice. Never use `maxDepth: 0` thinking it "disables the stage": it **still executes the first lookup pass**.

### 6.5. Depth Is Useful for Business Logic, Not a Full Exported Path

`depthField` reports only the **traversal depth of each matched document**, not the full sequence of IDs from root to that node. On a **single-parent tree**, you can reconstruct paths by following `managerId`. On a graph with **multiple paths to the same node**, depth alone does not tell you which path reached that node.

Do not assume `$graphLookup` automatically returns **shortest paths**, **all paths**, **path counts**, or **edge weights**. It returns the set of reachable documents within the traversal scope; weighted shortest paths or multi-criteria path optimization require a different algorithm/model or post-processing.

### 6.6. Depth Limit Bounds Expansion, Not Total Node Count

A graph with a **high branching factor** can still return huge document counts at depth 1 or 2. For example, if each node has 1,000 children:

~~~text
depth 0:             1,000 nodes
depth 1:         1,000,000 nodes (without duplicates or branch pruning)
depth 2:     1,000,000,000 nodes (theoretical scale)
~~~

Therefore `maxDepth: 2` **is not a cap of 2 documents, 2 queries, or 2 MB**. You must also control **fan-out**, input document count, node size, and memory/output limits.

## 7. `restrictSearchWithMatch`: Filtering **During Traversal** and Pruning Branches

Suppose the HR system must traverse only **active employees**, never continuing down branches beneath an inactive node. In the fixture, D is inactive while I (reporting to D) is active.

Here we use `restrictSearchWithMatch`:

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "activeDescendants",
      depthField: "level",
      maxDepth: 3,
      restrictSearchWithMatch: {
        active: true
      }
    }
  },
  {
    $project: {
      _id: 0,
      activeIds: "$activeDescendants.employeeId",
      count: { $size: "$activeDescendants" }
    }
  }
])
~~~

The expected result has **7 people**: A, B, C, E, F, G, H; **no D**, and **no I** even though I is active. Reason: traversal encounters D failing `active: true`, so **D is not accepted as a node to expand further**. The edge D → I is never followed.

~~~text
CEO
├── A (active)
│   ├── C (active) --> E (active)
│   └── D (INACTIVE) -X-> I (active but unreachable through D)
└── B (active)
    ├── F (active) --> G (active)
    └── H (active)
~~~

This is the fundamental difference between **filtering during traversal** and **filtering the final result**.

### 7.1. Filtering After `$graphLookup` Does Not Prune Branches

Compare:

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "everyone",
      depthField: "level",
      maxDepth: 3
    }
  },
  {
    $set: {
      activeOnly: {
        $filter: {
          input: "$everyone",
          as: "person",
          cond: { $eq: ["$$person.active", true] }
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      count: { $size: "$activeOnly" },
      activeIds: "$activeOnly.employeeId"
    }
  }
])
~~~

In this pipeline, `$graphLookup` already traversed both D and I; only afterward does `$filter` drop D. The result has **8 people**: A, B, C, E, F, G, H, **I**.

| Goal | Use | Why |
|---|---|---|
| "Traverse only active people; stop at inactive people." | `restrictSearchWithMatch:{active:true}` | **Prunes the branch** when encountering a non-matching node. |
| "Traverse everyone, but display only active people." | `$filter` on array after traversal | Still shows **I** even though the path goes through inactive D. |
| "Select root CEO only if CEO is active." | `$match` before `$graphLookup` | Filters only the input document, not every node in `from`. |

**Never replace `restrictSearchWithMatch` with a post-graph `$match` when business rules depend on branch pruning.**

### 7.2. `restrictSearchWithMatch` Syntax Is a **Query Filter**, Not an Aggregation Expression

Valid:

~~~javascript
restrictSearchWithMatch: {
  active: true,
  department: { $in: ["ENG", "OPS"] }
}
~~~

Do not write a field-to-field condition like the following expecting `"$department"` to be resolved as a field path:

~~~javascript
// Does NOT compare against the input document's department.
restrictSearchWithMatch: {
  department: { $ne: "$department" }
}
~~~

Per the MongoDB Manual, **do not use aggregation expressions** inside `restrictSearchWithMatch` as you would inside `$expr` in a standard `$match`. The string `"$department"` in this context is treated as a **literal string**, not a dynamic field reference to the root document.

### 7.3. Can the Condition Be Dynamic per Input Document?

`startWith` is an aggregation expression, so it can pull **dynamic** values from each input document. By contrast, `restrictSearchWithMatch` offers no `let` syntax to inject fields from each input document into an arbitrary `$expr`.

For example, a multi-tenant app may need to traverse only employees in the current tenant. If the request is authenticated for tenant T1, you can pass a **verified literal value** in the filter:

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    as: "descendants",
    maxDepth: 3,
    restrictSearchWithMatch: {
      tenantId: "T1"
    }
  }
}
~~~

This is a **structural illustration** for a collection carrying `tenantId`; the employee fixture in Section 3 does not have that field yet, so running it requires adding `tenantId` to the documents or using a separate multi-tenant collection. The tenant value must come from **server-side authorization context**, never blindly trusted from client input.

If a single query must traverse **multiple different tenants** scoped to each root's tenant, do not assume `restrictSearchWithMatch:{tenantId:"$tenantId"}` references the root. A safer model is using **composite node keys that embed the tenant** (for example normalized `nodeKey` and `parentKey` with uniqueness enforced), or executing tenant-scoped queries separately on the backend. Always test against cross-tenant edge traversal before deploying.

### 7.4. Do Not Use `restrictSearchWithMatch` as a Result Count Limit

`restrictSearchWithMatch` chooses **which node types** may be expanded; it has no option for "return only the first 20 nodes." `maxDepth` bounds **levels**, not **node count**. If a graph has huge fan-out, even depth 1 with an active filter can return too many documents.

If you only want to show the first 20 results:

~~~javascript
{
  $set: {
    top20: {
      $slice: [
        { $sortArray: {
            input: "$descendants",
            sortBy: { level: 1, employeeId: 1 }
        } },
        20
      ]
    }
  }
}
~~~

This snippet **only truncates the output after traversal finishes**. It **does not** tell `$graphLookup` to stop after visiting 20 nodes. `$graphLookup` does not provide a general `maxNodes` stop-early parameter; you must bound size via the data model, application limits, or an alternative query strategy.

## 8. Expanding from Multiple Starting Points and Multiple Edges

`$graphLookup` is not limited to trees where "one person has one manager." When each node holds an **array of links**, you can model many-to-many graphs.

### 8.1. Airport Route Graph

~~~text
HAN --> DAD --> CXR
 |       |
 |       +--> HAN (cycle)
 v
SGN --> CXR
 | 
 +----> PQC
~~~

Create a second collection, independent from `employees`:

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

lab.airports.insertMany([
  {
    _id: "AP-HAN",
    airport: "HAN",
    connects: ["DAD", "SGN"]
  },
  {
    _id: "AP-DAD",
    airport: "DAD",
    connects: ["CXR", "HAN"]
  },
  {
    _id: "AP-SGN",
    airport: "SGN",
    connects: ["CXR", "PQC"]
  },
  {
    _id: "AP-CXR",
    airport: "CXR",
    connects: ["HAN"]
  },
  {
    _id: "AP-PQC",
    airport: "PQC",
    connects: []
  }
])

lab.airports.createIndex(
  { airport: 1 },
  { unique: true, name: "ux_airport" }
)

lab.travelers.insertOne({
  _id: "TR-1",
  displayName: "Traveler A",
  nearestAirport: "HAN"
})
~~~

### 8.2. A Traveler Traversing Routes from Their Nearest Airport

~~~javascript
lab.travelers.aggregate([
  { $match: { _id: "TR-1" } },
  {
    $graphLookup: {
      from: "airports",
      startWith: "$nearestAirport",
      connectFromField: "connects",
      connectToField: "airport",
      as: "reachable",
      maxDepth: 2,
      depthField: "hops"
    }
  },
  {
    $set: {
      reachable: {
        $sortArray: {
          input: "$reachable",
          sortBy: { hops: 1, airport: 1 }
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      nearestAirport: 1,
      "reachable.airport": 1,
      "reachable.hops": 1
    }
  }
])
~~~

Reachable nodes in the fixture:

| `hops` | Airport |
|---:|---|
| 0 | HAN (first lookup matches `nearestAirport`) |
| 1 | DAD, SGN |
| 2 | CXR, PQC |

**Special note:** In this model, `startWith` evaluates to `"HAN"` and `connectToField: "airport"`, so **HAN appears inside `reachable` with hops 0**. If the UI wants only *other* airports the traveler can reach, filter HAN out after traversal or adjust `startWith`/edges to match the intended semantics.

### 8.3. Array Semantics in `connectFromField`

At node HAN, `connects: ["DAD", "SGN"]` has two elements. MongoDB uses **both DAD and SGN** to find documents matching `airport` in the next step. Then it takes `connects` from both DAD and SGN to continue. You do not need to `$unwind` `connects` manually before each step.

### 8.4. Starting from Multiple Airports

Add an input document:

~~~javascript
lab.travelers.insertOne({
  _id: "TR-2",
  displayName: "Traveler B",
  nearestAirports: ["HAN", "SGN"]
})
~~~

Query:

~~~javascript
lab.travelers.aggregate([
  { $match: { _id: "TR-2" } },
  {
    $graphLookup: {
      from: "airports",
      startWith: "$nearestAirports",
      connectFromField: "connects",
      connectToField: "airport",
      as: "reachable",
      depthField: "hops",
      maxDepth: 1
    }
  }
])
~~~

Because `startWith` is an array, the first lookup evaluates **both HAN and SGN**. Do not assume "it finishes traversing from one element before moving to the next" or that output will be ordered by the input array. In graphs with multiple starting points or multiple paths to the same node, `depthField` records traversal depth, **not a log of each traversed route**.

## 9. Cycles, Repeated Nodes, and Non-Tree Graphs

A graph can contain **cycles**: A → B → C → A. If an application traverses manually with a while-loop without tracking visited nodes, it can run forever. `$graphLookup` follows graph traversal tracking so it avoids looping endlessly over already-visited nodes. Even so, always set **sensible depth and size bounds** to prevent excessive resource consumption on heavily branched graphs.

### 9.1. A Dedicated Cycle Fixture

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

lab.cycleNodes.insertMany([
  { _id: "A", nodeId: "A", links: ["B"] },
  { _id: "B", nodeId: "B", links: ["C"] },
  { _id: "C", nodeId: "C", links: ["A", "D"] },
  { _id: "D", nodeId: "D", links: [] }
])

lab.cycleRoots.insertOne({
  _id: "ROOT-A",
  initialNode: "A"
})

lab.cycleNodes.createIndex(
  { nodeId: 1 },
  { unique: true }
)

lab.cycleRoots.aggregate([
  { $match: { _id: "ROOT-A" } },
  {
    $graphLookup: {
      from: "cycleNodes",
      startWith: "$initialNode",
      connectFromField: "links",
      connectToField: "nodeId",
      as: "reachable",
      depthField: "hops",
      maxDepth: 4
    }
  },
  {
    $project: {
      _id: 1,
      "reachable.nodeId": 1,
      "reachable.hops": 1
    }
  }
])
~~~

Reachable nodes are **A, B, C, D**; the C → A edge does not put infinite copies of A into the array. On clean data with one document per `nodeId`, visited nodes are not duplicated on each cycle revisit.

### 9.2. Cycle Prevention at the Data Layer Is Still Necessary

The fact that `$graphLookup` terminates **does not mean cyclic relationship data is valid**. In an HR org chart, A managing B while B manages A is a business integrity bug even though the query finishes.

When updating `managerId`, the application may need to:

1. Ensure the manager exists and belongs to the same tenant/organization.
2. Disallow an employee from managing themselves.
3. Disallow changing a manager to a **descendant** of the employee, which would create a cycle.
4. Guard against races when two clients update edges concurrently; transactions or versioning may be needed if cross-document invariants matter.
5. Run validation/repair jobs for malformed graphs from imports or migrations.

`$graphLookup` can help **detect potential cycles** when checking descendants, yet a read check followed by a separate update is not automatically atomic with concurrent writers. MongoDB does not enforce a "cycle-free tree" constraint via `$graphLookup` alone.

### 9.3. When Two Paths Converge

In a many-to-many graph, a node D may be reachable via A → B → D and A → C → D. `$graphLookup` returns **reachable documents**, not a separate copy of D for every path. Therefore:

- Do not use `$size: "$reachable"` to count **paths**.
- Do not treat `depthField` as a **list of edges**.
- Do not assume the output contains enough data to reconstruct **all** paths, especially when multiple routes reach the same vertex.
- If you need weighted optimization, cheapest paths, or path counts, consider specialized graph algorithms or derived data structures outside `$graphLookup`.

### 9.4. Missing References, Duplicate Codes, and Nulls

`connectToField` should hold a **stable key value** matching the relationship model. In the employee fixture, `employeeId` is unique and CEO's `managerId` is null; a node referencing `managerId: "UNKNOWN"` simply stops expanding if no employee matches.

If multiple documents share the same `connectToField` value, a single edge can match **multiple nodes**, increasing fan-out and producing unintended results. Put a unique index on the node ID key when the domain requires it. With missing/null fields, spurious matches can happen due to BSON equality rules; enforce **required, consistently typed keys** and avoid letting `startWith` or `connectFromField` accidentally emit null.

## 10. Indexes for `$graphLookup`: Optimizing Each Edge Lookup

`$graphLookup` executes repeated matching steps against the `from` collection. To avoid scanning the collection on every expansion hop, **an index on `connectToField` for the traversed direction** is one of the most important optimizations.

### 10.1. Which Index Does Descendant Traversal Need?

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    as: "descendants",
    maxDepth: 3
  }
}
~~~

Each step searches for documents with:

~~~javascript
{ managerId: "ID-of-current-node" }
~~~

So the candidate index is:

~~~javascript
lab.employees.createIndex(
  { managerId: 1 },
  { name: "ix_managerId" }
)
~~~

This index supports looking up direct children at **every level**. That makes a major difference if the graph has millions of nodes and each node has only a few children. MongoDB does not issue separate client network `find` calls per node; traversal runs inside the server stage, yet index lookups on `from` remain central.

### 10.2. Ancestor Traversal Needs a Different Index

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$managerId",
    connectFromField: "managerId",
    connectToField: "employeeId",
    as: "ancestors"
  }
}
~~~

Each step searches for the manager by:

~~~javascript
{ employeeId: "ID-of-manager-being-sought" }
~~~

So index `employeeId`, preferably **unique** if the model guarantees one document per `employeeId`:

~~~javascript
lab.employees.createIndex(
  { employeeId: 1 },
  { unique: true, name: "ux_employeeId" }
)
~~~

Reversing traversal direction while keeping only the `managerId` index leaves each manager lookup without its primary index. Always read the exact **`connectToField`** in the pipeline before choosing indexes.

### 10.3. Combining Indexes with `restrictSearchWithMatch`

When traversing only active nodes:

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    restrictSearchWithMatch: { active: true },
    as: "activeDescendants",
    maxDepth: 3
  }
}
~~~

A compound index can be a candidate:

~~~javascript
lab.employees.createIndex(
  { managerId: 1, active: 1 },
  { name: "ix_managerId_active" }
)
~~~

For each lookup by `managerId` and `active: true`, the compound index can narrow both relationship and status. However:

- If nearly all employees are active, the `active` key adds little selectivity.
- If other queries only filter by `managerId`, `{managerId: 1}` alone may suffice.
- Compound indexes increase write overhead and storage size.
- The planner/engine may select another index depending on statistics and version.

Do not create two overlapping indexes just because an example showed both; measure your actual traversal workload and weigh the write cost.

### 10.4. Filter Roots Before Traversal

The following query can execute traversal for **every document in employees**:

~~~javascript
lab.employees.aggregate([
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      maxDepth: 2
    }
  }
])
~~~

If the collection has millions of employees, the stage generates **a traversal result for every single employee**. That is drastically different from computing the tree under CEO alone. When an API needs one root, put `$match` **before `$graphLookup`**:

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      maxDepth: 2
    }
  }
])
~~~

The root `$match` can use `ux_employeeId`, and only **one input document** enters `$graphLookup`. The index for **root filtering** and the index on **`connectToField` of `from`** serve **two distinct phases**.

### 10.5. `$limit` Before vs. After Traversal

~~~javascript
// Select at most 10 roots before traversal:
[
  { $match: { department: "ENG" } },
  { $sort: { employeeId: 1 } },
  { $limit: 10 },
  { $graphLookup: { /* ... */ } }
]
~~~

This limits **how many roots are traversed**. Conversely:

~~~javascript
[
  { $match: { department: "ENG" } },
  { $graphLookup: { /* ... */ } },
  { $limit: 10 }
]
~~~

does not imply only 10 roots had traversal computed; a trailing `$limit` **is not a depth or node limit** on `$graphLookup`. When paginating, clarify whether you are **paginating roots or paginating child nodes**, as they are two different problems.

### 10.6. Index Choices for Multi-Tenant Graphs

In multi-tenant models, queries often pair `tenantId` with the relationship key. If one tenant has many nodes:

~~~javascript
// Illustrative index for a collection containing tenantId:
lab.employees.createIndex(
  { tenantId: 1, managerId: 1 },
  { name: "ix_tenant_manager" }
)
~~~

This index does not automatically replace `{managerId: 1}` in every `$graphLookup` if the traversal predicate only uses `managerId`. If `restrictSearchWithMatch` includes a verified literal `tenantId`, the compound index has a chance to be used. Check the **exact query shape** and `explain` instead of assuming "the index contains both fields."

Where security forbids cross-tenant access, **an index is not an authorization boundary**. Encode tenant identity into edges or apply verified filters and data checks; see the multi-tenant design notes.

## 11. Reading `explain` and Monitoring Traversal

For aggregations, you can run:

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

const pipeline = [
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      maxDepth: 2,
      depthField: "level"
    }
  },
  {
    $project: {
      _id: 0,
      employeeId: 1,
      count: { $size: "$descendants" }
    }
  }
]

printjson(
  lab.employees.explain("executionStats").aggregate(pipeline)
)
~~~

Inspect the execution plan for **root selection** and `$graphLookup`-related statistics. Depending on MongoDB version, stage metrics may appear at different locations in the explain structure.

### 11.1. Useful Metrics to Inspect

| Metric | Question to Answer |
|---|---|
| Leading `IXSCAN` or `COLLSCAN` | Was root `employeeId: "CEO"` selected via index or scan? |
| `indexesUsed` (if reported by the stage) | Which index did traversal use on the `from` collection? |
| `totalDocsExamined`, `totalKeysExamined` | Is the reported scan work proportional to the number of returned nodes? |
| Stage `collectionScans` (if present) | Is traversal performing repeated collection scans? |
| `executionTimeMillisEstimate` / timing (if present) | How long did the recursive stage take per engine stats? |
| `usedDisk` / `spills` (when supported) | Is there spilling or memory pressure? |
| Root count / output size | Is traversal running on more roots than necessary? |

Explain layout varies across the classic engine, SBE, MongoDB versions, and pipeline shapes. Never rely on a single hardcoded JSON path to parse metrics across all versions.

### 11.2. One `IXSCAN` Does Not Prove Traversal Is Optimal

If explain shows `IXSCAN` for root `employeeId: "CEO"` while traversal on `managerId` lacks a suitable index, the overall query can still be slow. Conversely, on a tiny ten-employee collection like the fixture, the planner choosing a scan may be cheaper. Evaluate on a graph large enough to exhibit **representative fan-out and depth**, rather than benchmarking a ten-document demo.

### 11.3. Measuring Growth Across Depths

You can run the same pipeline with `maxDepth: 0`, `1`, `2`, `3` to observe growth:

~~~javascript
for (const depth of [0, 1, 2, 3]) {
  const result = lab.employees.aggregate([
    { $match: { employeeId: "CEO" } },
    {
      $graphLookup: {
        from: "employees",
        startWith: "$employeeId",
        connectFromField: "employeeId",
        connectToField: "managerId",
        as: "descendants",
        maxDepth: depth
      }
    },
    {
      $project: {
        _id: 0,
        depthLimit: { $literal: depth },
        count: { $size: "$descendants" }
      }
    }
  ]).toArray()

  printjson(result)
}
~~~

On the fixture, the counts are **2, 6, 9, 9**. In production, node counts can grow exponentially in wide branching trees. Treat this loop as a **controlled experiment**, not something to run concurrently across deep graphs on an overloaded system.

### 11.4. Bounding Query Execution Time

`aggregate()` accepts the `maxTimeMS` option:

~~~javascript
lab.employees.aggregate(
  [
    { $match: { employeeId: "CEO" } },
    {
      $graphLookup: {
        from: "employees",
        startWith: "$employeeId",
        connectFromField: "employeeId",
        connectToField: "managerId",
        as: "descendants",
        maxDepth: 3
      }
    }
  ],
  { maxTimeMS: 5000 }
)
~~~

`maxTimeMS` sets a processing time limit at which the server can abort execution; it is a **safety guardrail**, not a guarantee that the query always finishes within 5 seconds. On timeout, the application must handle the error and decide whether to reduce depth/scope rather than endlessly retrying the same expensive pipeline.

## 12. Memory Limits, Result Size, and Versions

`$graphLookup` can expand a very large set of documents and attach them into **one array per root**. Two distinct limits must be considered:

1. **Traversal execution resources** — memory, version-dependent disk spill, I/O, CPU, lookup count, and time.
2. **Returned document size** — each aggregation output document must fit within the **16 MiB BSON** limit.

### 12.1. What to Check by MongoDB Version

Official documentation varies across release lines:

| Documentation Line | `$graphLookup` and Memory |
|---|---|
| **MongoDB 7.0/8.0** | The `$graphLookup` page states a **100 MB** limit; `allowDiskUse: true` **does not allow this stage to exceed the limit** (the option can still apply to other stages in the pipeline). |
| **Current Database Manual** | The `$graphLookup` page describes that exceeding **100 MB** can spill temporary files to disk when permitted; with `allowDiskUse: false` it errors if exceeded. |

Never apply a blanket claim like "`$graphLookup` always spills" or "`$graphLookup` never spills" without checking **server version**. Consult the documentation page **for the version you run**, inspect `explain("executionStats")`, and monitor `usedDisk`/spills under realistic load testing.

Additionally, starting in MongoDB 9.0 there is a **cluster/operation-wide memory limit** alongside per-stage limits; that is another control layer. Do not rely on disk spilling to justify unbounded traversals.

### 12.2. `allowDiskUse` Is No Substitute for Graph Design

Example setting the option:

~~~javascript
lab.employees.aggregate(
  [
    { $match: { employeeId: "CEO" } },
    {
      $graphLookup: {
        from: "employees",
        startWith: "$employeeId",
        connectFromField: "employeeId",
        connectToField: "managerId",
        as: "descendants",
        maxDepth: 3
      }
    }
  ],
  { allowDiskUse: true }
)
~~~

On MongoDB 7.0/8.0, per the corresponding `$graphLookup` docs, **do not expect this option to bypass the dedicated 100 MB limit of `$graphLookup` itself**. On releases where `$graphLookup` supports spilling, writing to disk still incurs heavy I/O and cannot rescue a result document that is too big to return.

### 12.3. Oversized Result Arrays and the 16 MiB Limit

If a root has 200,000 descendants and each descendant holds many fields, the `as` array can easily produce an oversized output document. A `$project` after traversal trims returned fields, yet **does not reduce how many nodes the initial traversal visits**; intermediate memory pressure still happens.

Design mitigations:

- Bound `maxDepth` to real business requirements.
- Use `restrictSearchWithMatch` to **prune unnecessary branches** where semantically valid.
- Select **fewer roots** with `$match`/`$limit` before traversal.
- Keep the graph collection's **node documents compact**, splitting bulky details into another collection.
- When the API only needs a **page of direct children**, use an indexed `find({managerId: ...})` query instead of walking the full tree.
- Consider **materialized paths**, ancestor/closure tables, caching, or external computation for huge or frequently repeated traversals.

### 12.4. `$project`/`$slice` Is Not a Traversal Limit

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  { $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants"
  } },
  { $project: {
      descendants: { $slice: ["$descendants", 10] }
  } }
])
~~~

The final stage only slices the **output array**. It does not tell MongoDB "stop after visiting 10 nodes." On a huge graph, the heaviest work has already happened beforehand. Moreover, without sorting, "the first 10 nodes" in the array have no guaranteed order.

### 12.5. Designing Limits Around Business Needs

Not every graph query needs deep recursion:

| Need | Reasonable Starting Bound |
|---|---|
| Show direct reports | Single-level query / `maxDepth: 0`. |
| Two-tier chart under a manager | `maxDepth: 1`. |
| Authorization across up to three org tiers | `maxDepth: 2` with tenant/active controls. |
| Report all descendants | Evaluate unbounded graph risks, fan-out, memory, and precomputation. |
| Find friends within two hops | Set `maxDepth` according to seed semantics; watch depth 0. |
| Count all distinct paths between two nodes | `$graphLookup` alone does not solve this directly. |

What matters is **defining hop depth from expected business semantics**, rather than picking an arbitrary shallow depth just to avoid timeouts and silently returning incomplete data.

## 13. `$graphLookup` on Sharded Collections, Views, and Transactions

### 13.1. `from` Must Be a Collection in the **Same Database**

`$graphLookup` uses:

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    as: "descendants"
  }
}
~~~

`from: "employees"` is a **collection name in the same database** as the aggregation; it cannot be an arbitrary URL or cross-database namespace. If the input is `lab.roots` and `from: "employees"`, both `roots` and `employees` must live in database `graph_lookup_lab`.

Two-collection example:

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

lab.roots.insertOne({
  _id: "R-ENG",
  rootEmployeeId: "A",
  title: "Engineering Org Chart"
})

lab.roots.aggregate([
  { $match: { _id: "R-ENG" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$rootEmployeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "members",
      maxDepth: 2,
      depthField: "level"
    }
  },
  {
    $project: {
      title: 1,
      memberIds: "$members.employeeId",
      memberCount: { $size: "$members" }
    }
  }
])
~~~

Root A has four descendants in the fixture: C, D, E, I (C/D at depth 0, E/I at depth 1). With `restrictSearchWithMatch: {active: true}`, only C and E remain because D is inactive and I sits under D.

### 13.2. Sharded Collection Support Since MongoDB 5.1

Starting in MongoDB **5.1**, `$graphLookup` allows the `from` collection to be a **sharded collection**. Earlier versions had different restrictions, so do not apply 5.1+ statements to older servers.

Operational consequences:

- Traversal can touch **multiple shards**, increasing latency and network/merge work.
- An index on `connectToField` and a **shard-key-aware data model** remain essential, yet an index alone does not guarantee every lookup routes to a single shard.
- If edges lack routing-compatible keys, the server may have to query across multiple shards.
- Measure `explain`/profiler on an actual sharded deployment; a single small collection fixture does not reflect distributed fan-out costs.

### 13.3. Transaction Limitation with Sharded `from`

Per the MongoDB Database Manual: **you cannot use `$graphLookup` inside a transaction when the stage targets a sharded collection in `from`**. This is an explicit restriction, even on newer MongoDB versions that support sharded `from`.

Do not assume that because `$lookup` or general aggregations can run in some transactions, every `$graphLookup` works in sharded transactions too. If business logic requires snapshot/atomic consistency across sharded graphs, design an alternative data flow compatible with deployment limits.

### 13.4. Views and Collation

When an aggregation involves multiple **views** via `$graphLookup` (or `$lookup`), the views must share **compatible/identical collations** per MongoDB docs. Collation also affects string matching across relationships.

If node IDs are strings and the app distinguishes `"A"` from `"a"`, define explicit collation/canonical IDs. A graph with inconsistent casing in node keys can yield unexpected results or falsely match distinct IDs.

### 13.5. Data Can Change During Traversal

A `$graphLookup` can run on a collection while the application is actively updating manager links or active flags. If business logic requires a **strongly consistent snapshot** of the entire tree while writers update concurrently, evaluate read concern, transaction semantics, and sharding constraints; do not assume a recursive aggregation automatically locks the entire graph against edge updates.

Some systems maintain a **graphVersion** or publish an org-tree snapshot after changes are approved so UI reads target an immutable version. That architectural pattern fits when global graph consistency outweighs live per-request computation.

## 14. Data Models Suited for Graph Queries

### 14.1. Adjacency List: Simple and Flexible

The fixture uses:

~~~javascript
{ employeeId: "G", managerId: "F" }
~~~

This is an **adjacency list**: each node stores direct links to neighbors/parent. Pros:

- Writing or changing a direct manager is straightforward.
- Moving a branch does not require updating ancestor lists on every descendant.
- Single-level queries using `{managerId: 1}` are fast.
- `$graphLookup` handles multi-level queries when needed.

Cons:

- Querying an entire deep and wide subtree can be resource-heavy.
- Cycle checks and tree-wide authorization must be designed separately.
- Frequent repeated reports may recompute the same traversal over and over.

### 14.2. Materialized Path

Another approach stores the path from root to node:

~~~javascript
{
  employeeId: "G",
  managerId: "F",
  ancestorPath: ["CEO", "B", "F"]
}
~~~

To find nodes under B, you can query `ancestorPath` if the array/path is properly structured and indexed. This simplifies certain descendant/ancestor reads, but reassigning a branch to another manager requires **updating derived paths on all descendants**, increasing write cost and consistency risk.

### 14.3. Ancestor / Closure Collection

Another model stores relationship pairs:

~~~javascript
{
  ancestorId: "CEO",
  descendantId: "G",
  distance: 3
}
~~~

With a MongoDB-style **closure table**, querying descendants becomes `find({ancestorId: "CEO"})`, with distances already stored. However, the app must maintain all affected pairs when adding, removing, or moving edges. This works best when **tree reads are very frequent, structural changes are rare**, and a consistent update pipeline exists.

### 14.4. Embedded Subtree

Small subtrees can be embedded inside a root document when cardinality is bounded and everything is read together. However, if the tree grows unboundedly or multiple writers update independent branches, the root document becomes a **hot document** and risks hitting the 16 MiB limit. Do not embed an entire graph just to avoid `$graphLookup` while ignoring fan-out and growth.

### 14.5. Choosing by Access Pattern

| Primary Need | Suitable Model / Query Approach | Trade-offs |
|---|---|---|
| Direct manager only | Adjacency list + single-level `find`/`$lookup`. | Simple, no recursion needed. |
| Descendants within a few tiers | Adjacency list + `$graphLookup` with `maxDepth`. | Sensitive to fan-out and indexes. |
| Ancestors along a short chain | Adjacency list + upward `$graphLookup`. | Needs accurate keys and root termination. |
| Frequently displaying a massive org chart | Cache / materialized graph / closure collection. | Complicates updates and invalidation. |
| Many-to-many with cycles | Array edges + `$graphLookup` for reachability. | Does not compute weighted shortest paths or all paths. |
| Counting paths, weighted optimization | Dedicated graph algorithm or specialized store. | Requires computation outside `$graphLookup`. |
| Multi-tenant tree authorization | Tenant checks, cycle prevention, constraints, snapshots. | More than a traversal; must block cross-tenant edges. |

## 15. Implementation Examples Using the MongoDB Java Sync Driver

The MongoDB Java Sync Driver builds aggregation pipelines with `List<Bson>`. To represent `$graphLookup` options accurately, you can construct the stage with `org.bson.Document`; the server receives the exact same BSON as `mongosh`.

### 15.1. Traversing Descendants in Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static com.mongodb.client.model.Aggregates.match;
import static com.mongodb.client.model.Filters.eq;

// database is a MongoDatabase pointing to "graph_lookup_lab".
MongoCollection<Document> employees = database.getCollection("employees");

Document graphLookupConfig = new Document("from", "employees")
    .append("startWith", "$employeeId")
    .append("connectFromField", "employeeId")
    .append("connectToField", "managerId")
    .append("as", "descendants")
    .append("maxDepth", 2)
    .append("depthField", "level")
    .append(
        "restrictSearchWithMatch",
        new Document("active", true)
    );

Bson graphLookupStage = new Document("$graphLookup", graphLookupConfig);

List<Bson> pipeline = Arrays.asList(
    match(eq("employeeId", "CEO")),
    graphLookupStage
);

employees.aggregate(pipeline)
    .maxTime(5, TimeUnit.SECONDS)
    .forEach(doc -> System.out.println(doc.toJson()));
~~~

On the fixture, the pipeline follows only active nodes, returning **7 descendants** (inactive D is excluded, and I under D is not reached). `maxTime(5, TimeUnit.SECONDS)` sets a server execution timeout per the driver API; it does not replace depth limits and indexes.

### 15.2. Traversing Ancestors in Java

Simply swap the three direction-defining fields:

~~~java
Document ancestorsConfig = new Document("from", "employees")
    .append("startWith", "$managerId")
    .append("connectFromField", "managerId")
    .append("connectToField", "employeeId")
    .append("as", "ancestors")
    .append("maxDepth", 2)
    .append("depthField", "level");

List<Bson> ancestorsPipeline = Arrays.asList(
    match(eq("employeeId", "G")),
    new Document("$graphLookup", ancestorsConfig)
);

employees.aggregate(ancestorsPipeline)
    .forEach(doc -> System.out.println(doc.toJson()));
~~~

The output contains F, B, CEO at levels 0, 1, 2. Using `Document` for the stage makes it easy to cross-check with the MongoDB Manual; depending on driver version, typed aggregation builders may also be available once you verify their API and generic signatures.

### 15.3. Rejecting Invalid Depth from Requests

Never accept an arbitrarily large `maxDepth` blindly from URL/query parameters. In the Java service:

~~~java
int requestedDepth = 2; // Example value received by service from request.
int allowedMaximum = 4; // Endpoint policy limit.

if (requestedDepth < 0 || requestedDepth > allowedMaximum) {
    throw new IllegalArgumentException(
        "depth must be between 0 and " + allowedMaximum
    );
}

Document config = new Document("from", "employees")
    .append("startWith", "$employeeId")
    .append("connectFromField", "employeeId")
    .append("connectToField", "managerId")
    .append("as", "descendants")
    .append("maxDepth", requestedDepth);
~~~

This is an **application-level limit**, not a MongoDB rule saying "maxDepth cannot exceed 4." Pick a bound suited to your fan-out and SLOs based on business needs and load testing.

### 15.4. Combining Root Filter, Restrict, and Tenant

In multi-tenant applications, never take `tenantId` unverified from a request and pass it into the graph filter. Combine them safely:

~~~java
String authorizedTenantId = "T1"; // Obtained from verified authorization context.
String requestedEmployeeId = "CEO";

List<Bson> scopedPipeline = Arrays.asList(
    match(new Document("employeeId", requestedEmployeeId)
        .append("tenantId", authorizedTenantId)),
    new Document("$graphLookup",
        new Document("from", "employees")
            .append("startWith", "$employeeId")
            .append("connectFromField", "employeeId")
            .append("connectToField", "managerId")
            .append("as", "descendants")
            .append("maxDepth", 3)
            .append("restrictSearchWithMatch",
                new Document("tenantId", authorizedTenantId)
                    .append("active", true)))
);
~~~

This pattern assumes a **collection with `tenantId`** and will not return data on the Section 3 fixture unless `tenantId` is added. Passing the same tenant scope to both **root** and **from nodes** expresses the intent clearly. However, to prevent matching two employees with the same `employeeId` across tenants, **link keys must be unique per tenant** or use composite node IDs; an improperly scoped global unique index can block valid tenants or expose wrong links.

### 15.5. Spring Data MongoDB

Spring Data provides aggregation abstractions; how `$graphLookup` stages and builders are structured varies across framework versions. If your version's builder lacks an option, you can implement an `AggregationOperation` returning a BSON `Document` with `$graphLookup`. Regardless of API, the fields received by the server must match:

~~~javascript
{
  from: "employees",
  startWith: "$employeeId",
  connectFromField: "employeeId",
  connectToField: "managerId",
  as: "descendants",
  maxDepth: 2,
  depthField: "level"
}
~~~

When using entity field mapping, verify whether serialized BSON field names are actually `employeeId`/`managerId` or renamed by annotations/converters. Do not look only at Java property names and assume `connectToField` matches.

## 16. Common Pitfalls When Using `$graphLookup`

| Common Misconception / Mistake | Issue | Correct Approach |
|---|---|---|
| "`$graphLookup` is just like `$lookup`, no different from a join." | `$graphLookup` **runs recursively**, with distinct costs and limits. | Use `$lookup` for single-level joins when recursion is unnecessary. |
| "`startWith` must be a field name." | `startWith` is an **aggregation expression**, which can be a field path, literal, or array expression. | Verify the actual initial value evaluated. |
| "`connectFromField` is the field matched, `connectToField` is read for the next step." | The two fields are swapped. | **Match on connectTo**, then **read connectFrom** to expand. |
| "Going down vs. going up only requires changing `startWith`." | Direction also depends on the connect field pair. | Flip `startWith`, `connectFromField`, and `connectToField` to match the relation. |
| "`depthField: 0` is the input root." | Depth 0 belongs to **documents matched in the first lookup**. | Direct matches are 0; subsequent hops are 1, 2, ... |
| "`maxDepth: 0` executes no lookup." | It still executes **one lookup pass**, just without expanding further. | Use `maxDepth: 0` for a single level. |
| "`maxDepth: 2` returns at most two nodes." | It means **two expansion hops after depth 0**, not a node count cap. | Add controls for fan-out, root count, and output size. |
| "Omitting `maxDepth` is safe because our data is small today." | Fan-out, cycles, or updates can quickly spike cost. | Set explicit depth bounds and endpoint limits. |
| "The `as` array is already sorted nearest to farthest." | `$graphLookup` **does not guarantee order**. | Use `$sortArray` or `$unwind → $sort`. |
| "`depthField` is the full path." | It is only the **depth**, not individual edges or all paths. | Use an appropriate model/algorithm if full paths or shortest paths are needed. |
| "Filtering active after `$graphLookup` equals restricting active." | Post-filtering can still keep nodes under an **inactive ancestor**. | Use `restrictSearchWithMatch` when **branch pruning** is required. |
| "`restrictSearchWithMatch` supports `"$tenantId"` referencing input." | `"$tenantId"` in the filter is a literal string, not a dynamic expression. | Scope with a verified literal or composite keys/model. |
| "A root `$match` guarantees all descendants belong to the tenant." | Edges could point to another tenant. | Enforce tenant scope on relationships/`from` and node identities. |
| "To fetch only 10 nodes, `$slice` the output array." | `$slice` after traversal **does not stop the server from walking the whole graph**. | Choose a bounded data model, pagination, or bounded algorithm. |
| "`$limit: 10` after `$graphLookup` limits to 10 traversals." | A trailing stage does not restrict inputs entering the graph stage. | `$match`/`$limit` roots **before** the graph stage when valid. |
| "An index on `managerId` makes ancestor queries indexed too." | Ancestor traversal matches on `employeeId`. | Index the **`connectToField`** of each traversal direction. |
| "Having an index guarantees `$graphLookup` is fast." | Wide graphs, many roots, fan-out, and memory can still be expensive. | Check explain, measure nodes/level, `maxTimeMS`, and load test. |
| "A cyclic graph makes `$graphLookup` loop forever." | The stage tracks visited nodes and will not emit one node infinitely due to cycles. | Still **prevent cycles at the domain layer** if data must form a tree. |
| "A unique index on `managerId` keeps the tree valid." | That forbids two employees from sharing a manager, breaking org charts. | Unique on **`employeeId`**; non-unique on **`managerId`**. |
| "`allowDiskUse: true` always solves graphLookup memory." | MongoDB 7.0/8.0 specify a dedicated 100 MB limit; current docs describe different spill behavior. | Check your exact server version; reduce fan-out and output size. |
| "Returning huge arrays is fine because MongoDB uses cursors." | Each **output document** still hits the 16 MiB limit; cursors do not lift it. | Bound depth, node size, and output design. |
| "Sharded `from` is supported in all versions." | Supported since **MongoDB 5.1**, with transaction limits. | Verify server version and shard routing. |
| "`$graphLookup` in transactions targeting sharded collections works like `$lookup`." | MongoDB explicitly **forbids** `$graphLookup` inside transactions targeting a sharded `from`. | Choose another consistency design. |
| "`$graphLookup` enforces foreign key integrity." | The stage simply follows references present in existing data. | Validate node keys, refs, tenant, and cycles at design/write time. |

### 16.1. Three Questions Before Code Review

1. **Where does it start, and in which direction?** Write the first lookup: `from.connectToField = startWith`.
2. **When does it stop?** Check `maxDepth`, `restrictSearchWithMatch` rules, and worst-case fan-out.
3. **What is the output?** Reachable node set, sorted tree, manager list, or all paths? `$graphLookup` does not directly provide all of those structures.

### 16.2. Two Questions on System Limits

4. **Which index resolves the edges?** Index `connectToField`, plus restrict fields when genuinely beneficial.
5. **Is it safe regarding tenant isolation, memory, and output size?** Verify root scope, check edges, guard `maxDepth`, and measure under real load.

## 17. Practice Exercises with Answers

Use the `graph_lookup_lab.employees`, `airports`, `travelers`, and `cycleNodes` fixtures from earlier sections. Exercises are read-only unless stated otherwise; never run them on production.

### Exercise 1 — Finding All CEO Subordinates

**Task:** Return CEO's descendants up to three tiers down, including `level`.

**Answer:**

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "reports",
      maxDepth: 2,
      depthField: "level"
    }
  }
])
~~~

Returns **9 people**, excluding CEO. A/B at level 0; C/D/F/H at level 1; E/I/G at level 2.

### Exercise 2 — Direct Reports Only

**Task:** From CEO, return only A and B, not C/D.

**Answer:** Use the same descendant pipeline with `maxDepth: 0`:

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    as: "directReports",
    maxDepth: 0
  }
}
~~~

`maxDepth: 0` runs **a single lookup pass**. If only one level is needed and the model is simple, an indexed `find({managerId: "CEO"})` can also suffice.

### Exercise 3 — Finding G's Management Chain

**Task:** Return all superiors of G up to CEO.

**Answer:**

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "G" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$managerId",
      connectFromField: "managerId",
      connectToField: "employeeId",
      as: "ancestors",
      depthField: "level"
    }
  }
])
~~~

Result set: **F, B, CEO** with levels 0, 1, 2 respectively; array order is not guaranteed.

### Exercise 4 — Short Management Chain

**Task:** For G, return at most two managers starting from G.

**Answer:** Use the ancestor query with `maxDepth: 1`, returning **F and B**, excluding CEO.

### Exercise 5 — Counting by Tier

**Task:** Count CEO's descendants at each level 0, 1, 2.

**Answer:**

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "reports",
      maxDepth: 2,
      depthField: "level"
    }
  },
  { $unwind: "$reports" },
  {
    $group: {
      _id: "$reports.level",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Counts are **2, 4, 3** for levels 0, 1, 2.

### Exercise 6 — How Do the Two Active-Filtering Approaches Differ?

**Task:** Compare `restrictSearchWithMatch: {active: true}` against a trailing `$filter` without restrict.

**Answer:**

- **Restrict during traversal:** A, B, C, E, F, G, H = **7**; inactive D is pruned and I under D is unreachable.
- **Filter array after traversal:** A, B, C, E, F, G, H, I = **8**; I still appears because traversal walked through D before filtering.

This is a **semantic and cost difference**, not just two syntax styles.

### Exercise 7 — Why Is `startWith: "$managerId"` Wrong When Finding CEO's Subordinates?

**Answer:** CEO has `managerId: null`. Using `startWith: "$managerId"` instead of `"$employeeId"` to walk downward does not search for "who has managerId = CEO." You must seed with CEO's `employeeId` to match against subordinates' `managerId`.

### Exercise 8 — Which Indexes for Both Directions?

**Task:** Propose indexes for descendant queries and ancestor queries.

**Answer:**

~~~javascript
// Find children by managerId:
lab.employees.createIndex({ managerId: 1 })

// Find parent by employeeId:
lab.employees.createIndex(
  { employeeId: 1 },
  { unique: true }
)
~~~

Note: do not create a unique index on `managerId`, since multiple employees can share a manager. Since the fixture already created the indexes in Section 3, these statements **illustrate the key patterns** and do not need to be re-created as duplicates.

### Exercise 9 — Traversing Airports from HAN

**Task:** For traveler TR-1, which airports does `maxDepth: 1` return?

**Answer:** **HAN** at hops 0, **DAD and SGN** at hops 1. CXR/PQC are reached only at hops 2 and are omitted. Here HAN is the first node matched in `from` because `startWith: "HAN"` and `connectToField: "airport"`.

### Exercise 10 — Sorting by Level

**Task:** Sort CEO's descendants by ascending `level` and then ascending `employeeId`.

**Suggested answer:**

~~~javascript
{
  $set: {
    descendants: {
      $sortArray: {
        input: "$descendants",
        sortBy: { level: 1, employeeId: 1 }
      }
    }
  }
}
~~~

Place this stage after `$graphLookup`. `$sortArray` is supported since MongoDB 5.2; do not rely on the natural order of the `as` array.

### Exercise 11 — Root with an Inactive Subordinate

**Task:** Start from A with `restrictSearchWithMatch: {active: true}` and `maxDepth: 2`. Who is returned?

**Answer:** C (level 0) and E (level 1). D is excluded because it is inactive, and I is not traversed since it reports to D. Without restrict, C, D, E, I are returned.

### Exercise 12 — Running from Another Collection

**Task:** From `lab.roots` with `rootEmployeeId: "A"`, retrieve descendants from `lab.employees`.

**Answer:**

~~~javascript
lab.roots.aggregate([
  { $match: { _id: "R-ENG" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$rootEmployeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "members",
      maxDepth: 2
    }
  }
])
~~~

`from` can be a different collection **in the same database**. Source and target collections do not need the same name.

### Exercise 13 — Query Slow Despite Root `$match`

**Prompt:** `$match: {employeeId: "CEO"}` uses `IXSCAN`, yet `$graphLookup` is still slow. What should you inspect next?

**Answer:** Check the index on `connectToField` (`managerId`), traversal fan-out, depth, node count, stage stats, version-specific memory/disk usage, and output size. Root `IXSCAN` only optimizes finding the initial input; it does not prove recursive lookups are indexed.

### Exercise 14 — Does `$slice` Reduce Traversed Nodes?

**Prompt:** After `$graphLookup`, apply `$project: {reports: {$slice: ["$reports", 5]}}`. Does MongoDB stop after five nodes?

**Answer:** No. `$slice` runs **after the array is built**, trimming only the output. To reduce traversal cost, reduce roots/depth/branches, redesign the data model, or use a genuinely bounded algorithm.

### Exercise 15 — Handling Cycles

**Prompt:** Graph A → B → C → A, plus C → D. Does `$graphLookup` from A return A infinitely many times?

**Answer:** No; traversal tracks visited nodes, so the reachable set is just A, B, C, D. However, if the domain requires an **HR tree**, the cycle is still **corrupt data** and must be prevented on the write path.

### Exercise 16 — Dynamic Tenant Filter

**Prompt:** Can you set `restrictSearchWithMatch: {tenantId: "$tenantId"}` expecting it to resolve each input document's `tenantId`?

**Answer:** No. It is not an aggregation expression; `"$tenantId"` is treated as a literal string in the filter. For one authenticated tenant, pass the backend-verified literal `tenantId`; for multi-tenant queries, design **composite keys** or scoped data so cross-tenant traversal cannot occur.

### Exercise 17 — Why Isn't `maxDepth: 2` Enough to Protect Resources?

**Answer:** Each level can contain huge numbers of nodes. With 1,000 children per node, depth 0 has 1,000 nodes and depth 1 can reach 1,000,000 nodes. Account for **fan-out**, root count, doc size, memory, and the 16 MiB limit; `maxDepth` is not a result count cap.

### Exercise 18 — Memory Limits Differ by Version

**Prompt:** A tutorial claims setting `allowDiskUse: true` removes the 100 MB limit on `$graphLookup` in MongoDB 8.0. Is that true?

**Answer:** No, according to **MongoDB 8.0 `$graphLookup` documentation**, where this option does not let the stage exceed its 100 MB limit. Current Manual docs describe different spill behavior; always check your exact **server version** and test rather than copying one rule across all releases.

### Exercise 19 — Weighted Shortest Path Requirement

**Prompt:** In an airport network, find the route with the **lowest total ticket cost**, where each edge has a different price. Can `$graphLookup` return the cheapest route directly?

**Answer:** No. `$graphLookup` performs reachability traversal, not Dijkstra / weighted shortest path, and does not compute optimal routes automatically. You need edge weights paired with an appropriate algorithm or a dedicated graph-processing component.

## 18. Process for Designing a Safe Relationship-Traversal Endpoint

A service exposing an endpoint like:

~~~text
GET /organizations/{tenantId}/employees/{employeeId}/descendants?depth=2
~~~

should not simply drop a `$graphLookup` into a controller and return the whole array. A sound workflow:

### Step 1 — Lock Down Semantics

Define:

- Does `depth=0` mean "direct reports" or "root only"? In MongoDB `maxDepth: 0` executes **one lookup pass**; if the API defines `depth=0` as **root only**, translate that convention in the backend.
- Should the root be included in the output?
- Does each node have one parent or multiple parents?
- Should inactive nodes **halt traversal** or merely be hidden from display?
- Return all descendants or a subset; is deterministic ordering required?
- Are cross-tenant links ever allowed?

Document these rules in the API contract rather than letting consumers infer them from `maxDepth`.

### Step 2 — Enforce Node Identity Constraints

In a single-tenant model:

~~~javascript
{
  employeeId: "E",
  managerId: "C",
  active: true
}
~~~

Verify that `employeeId` is stable/unique and `managerId` shares the same type and references a valid employee; otherwise traversal easily misses branches or multiplies matches. In multi-tenant setups, consider `(tenantId, employeeId)` keys and composite edge keys so identical employee codes in two tenants never link.

### Step 3 — Bound Root and Depth from Authenticated Context

~~~javascript
const requestedEmployeeId = "CEO"
const requestedDepth = 2
const maximumDepth = 4

if (!Number.isInteger(requestedDepth) ||
    requestedDepth < 0 ||
    requestedDepth > maximumDepth) {
  throw new Error("depth exceeds API limit")
}

lab.employees.aggregate([
  { $match: { employeeId: requestedEmployeeId } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      maxDepth: requestedDepth,
      depthField: "level",
      restrictSearchWithMatch: { active: true }
    }
  }
], { maxTimeMS: 5000 })
~~~

In production, `requestedEmployeeId` must be checked against authentication and authorization permissions. Multi-tenant APIs must also enforce tenant scope on both **root and graph edges** as discussed. Never accept an arbitrary path key and expose an entire sensitive hierarchy.

### Step 4 — Create Indexes Matching Traversal Direction

For descendants:

~~~javascript
lab.employees.createIndex({ managerId: 1 })
~~~

For ancestors:

~~~javascript
lab.employees.createIndex(
  { employeeId: 1 },
  { unique: true }
)
~~~

These are candidate indexes. If equivalent indexes already exist on the collection, do not add duplicates. Inspect `explain` and consider compound indexes with common restrict filters.

### Step 5 — Test on Small Graphs Covering Edge Cases

A test suite should cover:

| Test Case | What to Verify |
|---|---|
| Root with no children | `as` is an empty array. |
| Root with one child | `maxDepth: 0` returns one child at level 0. |
| Three-tier tree | `maxDepth: 1` omits depth-2 tier. |
| Inactive branch with active grandchild | Does restrict prune the entire branch per policy? |
| Orphan node (missing managerId target) | No phantom nodes created; traversal scope behaves properly. |
| Cycle A → B → A | Query terminates; domain logic rejects cycles. |
| Multiple paths to one node | Do not assume "one output item = one path." |
| Two tenants sharing employeeId | No cross-tenant edges created. |
| Node with array links | Every valid edge element is expanded. |
| Very wide graph | Resource and output limits are handled gracefully. |

### Step 6 — Load Test with a Representative Graph

Check at least:

- Roots per query and children-per-node distribution.
- Fraction of nodes excluded by restrict filters and **branches pruned**.
- Typical `maxDepth` versus maximum depth in actual data.
- `totalKeysExamined`/`totalDocsExamined` and `indexesUsed` in explain.
- P50/P95/P99 latency, CPU, memory, and I/O/disk spill per version.
- BSON output size as a function of node count and field count.
- Shard targeting/fan-out if `from` is sharded.
- Timeout/cancellation behavior when clients disconnect.

A ten-node tree always runs fast and reveals nothing about a million-node graph with cross-shard edges or unindexed root queries.

### Step 7 — Set Product Boundaries for Oversized Graphs

Instead of returning an entire tree:

- The UI can **lazy-load direct children on expand** via `find({managerId: ...})`.
- Reports can run **offline/precomputed** and store summaries.
- Management chain lookups can be bounded to a sensible number of levels.
- If the business genuinely requires exporting all descendants, paginate or stream over a **suitable data model** rather than expecting `$slice` after `$graphLookup` to cap traversal cost.
- Nodes with bulky/sensitive profile fields should **separate graph topology** from heavy profile details.

### Step 8 — Monitor Graph Mutations

When departments reorganize or managers change:

1. Prevent cycles and cross-tenant references if forbidden by domain rules.
2. Update caches or materialized paths consistently, if used.
3. Handle concurrent edits and audit trails.
4. Re-measure queries after structural changes, as one node's fan-out can spike dramatically.
5. Do not misinterpret missing nodes after restrict as an index bug when the filter is intentionally pruning branches.

## 19. Quick Syntax Reference

### 19.1. Descendant Traversal

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    as: "descendants",
    maxDepth: 2,
    depthField: "level"
  }
}
~~~

**Finds documents whose `managerId` equals the current node ID**, repeating from each matched node's `employeeId`.

### 19.2. Ancestor Traversal

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$managerId",
    connectFromField: "managerId",
    connectToField: "employeeId",
    as: "ancestors",
    maxDepth: 2,
    depthField: "level"
  }
}
~~~

**Finds documents whose `employeeId` equals the current `managerId`**, repeating upward through management tiers.

### 19.3. Conditional Branch Pruning

~~~javascript
restrictSearchWithMatch: {
  active: true
}
~~~

Nodes failing the filter are not accepted for further expansion. **Do not** write `"$field"` inside the restrict filter expecting dynamic comparison against the root.

### 19.4. "Number of Tiers" Conversion Table

| Output Tiers from Starting Node (excluding root) | `maxDepth` |
|---:|---:|
| 1 | 0 |
| 2 | 1 |
| 3 | 2 |
| N | N − 1 |

This mapping holds when the first lookup returns the **first child/manager tier**, as in the employee example. If the seed is a node inside `from` and that node itself is matched at depth 0 (such as airport HAN), revisit how your API defines "tier."

### 19.5. Ordering and Shaping Output

~~~javascript
{
  $set: {
    descendants: {
      $sortArray: {
        input: "$descendants",
        sortBy: { level: 1, employeeId: 1 }
      }
    }
  }
}
~~~

Run after `$graphLookup`; never depend on raw array order. To group by depth, use `$unwind` followed by `$group`/`$sort`.

## 20. Official MongoDB References

The resources below help verify syntax and limits **by server version**, especially regarding `$graphLookup` memory limits:

- [`$graphLookup` — MongoDB Database Manual](https://www.mongodb.com/docs/manual/reference/operator/aggregation/graphLookup/) — `from`/`startWith`/`connectFromField`/`connectToField` parameters, `maxDepth`/`depthField`, restrict filter, sharding, and unsorted output.
- [`$graphLookup` — MongoDB 8.0 Manual](https://www.mongodb.com/docs/v8.0/reference/operator/aggregation/graphLookup/) — exact memory limit and `allowDiskUse` behavior for the 8.0 release line.
- [`$graphLookup` — MongoDB 7.0 Manual](https://www.mongodb.com/docs/v7.0/reference/operator/aggregation/graphLookup/) — reference for the 7.0 release line.
- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — stage semantics, data flow, and aggregation basics.
- [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/) — semantically equivalent stage reordering and optimizations.
- [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/) — memory, disk use, and result size limits.
- [`$lookup` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — comparing single-level joins and pipeline lookups.
- [`$unwind` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/) — turning each element of a result array into a pipeline document.
- [`$sortArray` Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sortArray/) — sorting an output array by fields.
- [`$filter` Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/) — filtering array elements **after creation**, unlike branch pruning during traversal.
- [`$match` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/) — selecting only the roots to traverse.
- [Indexes](https://www.mongodb.com/docs/manual/indexes/) — designing indexes matching the field queried in `connectToField`.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — how to read execution plans and explain statistics.
- [`db.collection.explain()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/) — running `explain("executionStats")` on aggregations.
- [Sharded Collections and Aggregation](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-sharded-collections/) — aggregation mechanics on sharded collections.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — restrictions on `$graphLookup` targeting a sharded `from`.
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/) — building pipelines via `MongoCollection.aggregate` and Java BSON builders.
- [MongoDB 9.0 Release Notes](https://www.mongodb.com/docs/manual/release-notes/9.0/) — operation-wide memory limits starting in 9.0, distinct from per-stage limits.

**Conclusion:** `$graphLookup` is well suited for **recursively traversing relationships modeled with reference fields** in MongoDB. The three decisions that govern correctness most directly are **setting the right direction via `connectFromField`/`connectToField`**, **setting `maxDepth` using 0-based depth counting**, and **choosing `restrictSearchWithMatch` when you need branch pruning rather than post-display filtering**. In production, keep input roots small, index `connectToField`, measure fan-out, never assume output is ordered or holds all paths, and check memory/sharding limits for your exact server version before scaling up graph queries.
