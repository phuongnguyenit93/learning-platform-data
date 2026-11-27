# Transforming Objects with $objectToArray, $arrayToObject, and $mergeObjects in MongoDB

## 1. Why Transform Objects in Aggregation?

MongoDB stores data as **BSON documents**. Within a document, an object is commonly used to represent a set of named attributes. Example:

~~~javascript
{
  _id: "SKU-001",
  name: "Wireless Mouse",
  stockByWarehouse: {
    HN: 7,
    HCM: 12,
    DN: 3
  }
}
~~~

To the application, **stockByWarehouse** is a map from warehouse code to stock quantity:

~~~text
HN  -> 7
HCM -> 12
DN  -> 3
~~~

When the number of warehouses or attribute names varies from document to document, the application cannot pre-write an expression for every key that might appear. Common requirements include:

1. **Iterating over all key/value pairs** to sum or filter dynamic attributes.
2. **Converting an array of key/value pairs into an object** to produce an easily accessible document.
3. **Merging configuration objects** in priority order: defaults → tenant → request.
4. **Transforming or renaming keys** without knowing the key list in advance.
5. **Normalizing data** before generating reports, mapping to DTOs, or updating under new rules.

MongoDB provides three especially useful aggregation expressions:

| Expression | Primary Input | Output | Purpose |
|---|---|---|---|
| **$objectToArray** | Object/document | Array of **{k, v}** objects | Converts object fields into array elements so they can be processed with array operators. |
| **$arrayToObject** | Array of **[k, v]** pairs or **{k, v}** objects | Object/document | Reconstructs an object from a key/value list. |
| **$mergeObjects** | One or more objects | Merged object/document | Combines fields, resolving duplicate keys by priority order. |

Mental model:

~~~text
Object:
  {HN:7, HCM:12}
       |
       | $objectToArray
       v
Array:
  [{k:"HN",v:7}, {k:"HCM",v:12}]
       |
       | $filter / $map / $concatArrays ...
       v
Array:
  [{k:"HN",v:7}, {k:"HCM",v:12}, {k:"total",v:19}]
       |
       | $arrayToObject
       v
Object:
  {HN:7, HCM:12, total:19}

Object A + Object B
       |
       | $mergeObjects
       v
Combined object
~~~

**Key distinction:** these are **aggregation expressions**, not three standalone pipeline stages. They are placed inside stages such as **$project**, **$set/$addFields**, **$replaceRoot/$replaceWith**, or other expression-supporting contexts. **$mergeObjects** in particular also has an **accumulator** form in certain grouping stages.

## 2. Preparing Practice Data

In **mongosh**, use a dedicated test database:

~~~javascript
use aggregation_object_lab
~~~

Insert products with varying sets of warehouse codes:

~~~javascript
db.products.insertMany([
  {
    _id: "SKU-001",
    tenantId: "T1",
    name: "Wireless Mouse",
    status: "ACTIVE",
    stockByWarehouse: {
      HN: NumberInt(7),
      HCM: NumberInt(12),
      DN: NumberInt(3)
    },
    attributes: {
      color: "black",
      warrantyMonths: NumberInt(12),
      wireless: true
    }
  },
  {
    _id: "SKU-002",
    tenantId: "T1",
    name: "Mechanical Keyboard",
    status: "ACTIVE",
    stockByWarehouse: {
      HCM: NumberInt(4),
      CT: NumberInt(6)
    },
    attributes: {
      color: "white",
      switchType: "linear"
    }
  },
  {
    _id: "SKU-003",
    tenantId: "T1",
    name: "27-inch Monitor",
    status: "DRAFT",
    stockByWarehouse: {},
    attributes: {
      resolution: {
        width: NumberInt(2560),
        height: NumberInt(1440)
      },
      refreshRate: NumberInt(144)
    }
  },
  {
    _id: "SKU-004",
    tenantId: "T1",
    name: "USB Hub",
    status: "ACTIVE",
    attributes: null
  },
  {
    _id: "SKU-005",
    tenantId: "T2",
    name: "Laptop Stand",
    status: "ACTIVE",
    stockByWarehouse: {
      HN: NumberInt(10)
    },
    attributes: {
      color: "silver"
    }
  }
]);
~~~

**Note:** `insertMany` should only be run once on a fresh collection. Re-running with the same `_id` values causes MongoDB to return a duplicate key error. The examples below mostly use read aggregations without deleting source data.

We have five documents:

| _id | tenant | Warehouses | Points to note |
|---|---|---|---|
| SKU-001 | T1 | HN, HCM, DN | Has three key/value pairs. |
| SKU-002 | T1 | HCM, CT | Keys do not completely overlap with SKU-001. |
| SKU-003 | T1 | Empty object **{}** | Tests empty object and nested objects. |
| SKU-004 | T1 | `stockByWarehouse` field **missing** | Tests missing fields and null `attributes`. |
| SKU-005 | T2 | HN | Tests tenant filtering. |

Two concepts must be kept distinct:

- **Object** such as **{HN: 7, HCM: 12}**: keys live in **field names**.
- **Array of pairs** such as **[{k:"HN",v:7},{k:"HCM",v:12}]**: keys live in the **value of field `k`** of each element.

Converting between these two forms unlocks **$map**, **$filter**, **$sum**, **$reduce**, and other aggregation expressions.

## 3. $objectToArray: From Object to Array of {k, v}

### 3.1. Syntax

~~~javascript
{
  $objectToArray: <objectExpression>
}
~~~

**objectExpression** must evaluate to a valid BSON document/object. The result is an array of elements with two fields:

- **k:** source field name, as a string.
- **v:** value of the source field, preserving its BSON type.

Example:

~~~javascript
{
  HN: 7,
  HCM: 12,
  DN: 3
}
~~~

becomes:

~~~javascript
[
  { k: "HN", v: 7 },
  { k: "HCM", v: 12 },
  { k: "DN", v: 3 }
]
~~~

### 3.2. Placing the Expression Inside $project

~~~javascript
db.products.aggregate([
  {
    $match: {
      _id: "SKU-001"
    }
  },
  {
    $project: {
      _id: 1,
      warehouses: {
        $objectToArray: "$stockByWarehouse"
      }
    }
  }
]);
~~~

Illustrative output:

~~~javascript
{
  _id: "SKU-001",
  warehouses: [
    { k: "HN", v: 7 },
    { k: "HCM", v: 12 },
    { k: "DN", v: 3 }
  ]
}
~~~

**$project** is the pipeline stage, while **$objectToArray** is the expression inside that stage. This expression **does not multiply document count**: one product entering `$project` still produces one product leaving, only changing the structure of the `warehouses` field.

### 3.3. Using $set to Preserve Original Fields

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $set: {
      warehousePairs: {
        $objectToArray: "$stockByWarehouse"
      }
    }
  }
]);
~~~

Unlike the projection-only example, the **$set** stage keeps the other source fields and adds **warehousePairs**. After this stage, the resulting document contains **both `stockByWarehouse` as an object** and **`warehousePairs` as an array**.

**$set** in **aggregate()** is a stage processing intermediate results; it does not automatically write documents back to the collection. Distinguish it from **$set** in `updateOne` or update pipelines, which perform writes.

### 3.4. $objectToArray Only Processes One Field Level

Consider document SKU-003:

~~~javascript
{
  attributes: {
    resolution: {
      width: 2560,
      height: 1440
    },
    refreshRate: 144
  }
}
~~~

Query:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-003" } },
  {
    $project: {
      _id: 0,
      attributePairs: {
        $objectToArray: "$attributes"
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  attributePairs: [
    {
      k: "resolution",
      v: {
        width: 2560,
        height: 1440
      }
    },
    {
      k: "refreshRate",
      v: 144
    }
  ]
}
~~~

**$objectToArray does not recursively convert nested objects**. It only turns **the immediate top-level fields of the input object** into `{k, v}` elements; the `resolution` entry still has **v as an embedded document**.

If you need to process the subfields of `resolution`, access that object and invoke the conversion expression at that level, or design explicit traversal for nested structures.

### 3.5. Empty Object Case

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-003" } },
  {
    $project: {
      warehouses: {
        $objectToArray: "$stockByWarehouse"
      }
    }
  }
]);
~~~

Because **stockByWarehouse: {}**, the expression returns:

~~~javascript
{
  _id: "SKU-003",
  warehouses: []
}
~~~

An object with no fields is converted into an array with zero elements. **Do not confuse an empty object `{}` with `null` or missing**, because downstream handling can differ.

### 3.6. Missing or null Fields

For a **null** or **missing** input field, **$objectToArray** returns **null**. For instance, SKU-004 has no `stockByWarehouse`:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-004" } },
  {
    $project: {
      warehousePairs: {
        $objectToArray: "$stockByWarehouse"
      }
    }
  }
]);
~~~

The resulting `warehousePairs` is **null**, not an empty array. If downstream stages require an array so **$map/$filter/$size** run reliably, supply a default object using **$ifNull**:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-004" } },
  {
    $project: {
      warehousePairs: {
        $objectToArray: {
          $ifNull: [
            "$stockByWarehouse",
            {}
          ]
        }
      }
    }
  }
]);
~~~

Now **warehousePairs = []**. This rule only handles **null/missing**; if `stockByWarehouse` is a string or number, **$objectToArray** will still error because the input is not an object.

## 4. Working with Key/Value Pairs Using $filter, $map, and $sum

Converting to an array is rarely the final goal. The real benefit is using **array expressions** to process a dynamic set of fields.

### 4.1. Summing Inventory Across Unknown Keys

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "T1"
    }
  },
  {
    $set: {
      warehousePairs: {
        $objectToArray: {
          $ifNull: [
            "$stockByWarehouse",
            {}
          ]
        }
      }
    }
  },
  {
    $set: {
      totalStock: {
        $sum: "$warehousePairs.v"
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      totalStock: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Expected results:

~~~javascript
[
  { _id: "SKU-001", name: "Wireless Mouse", totalStock: 22 },
  { _id: "SKU-002", name: "Mechanical Keyboard", totalStock: 10 },
  { _id: "SKU-003", name: "27-inch Monitor", totalStock: 0 },
  { _id: "SKU-004", name: "USB Hub", totalStock: 0 }
]
~~~

Explanation:

1. **$objectToArray** converts `stockByWarehouse` into `{k,v}` elements.
2. **"$warehousePairs.v"** extracts the `v` values from the object array.
3. **$sum** in an expression position inside **$set** sums the numeric values.
4. **$project** returns only the fields needed for the report.

This is the **expression `$sum` over an array within each document**, not the **$sum accumulator in `$group`** summing across multiple documents.

If `warehousePairs` contains non-numeric values, check summation semantics carefully; never silently treat wrong-type data as valid stock. Use schema validation or input type checks.

### 4.2. Filtering Only Warehouses with Stock

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      _id: 1,
      availableWarehouses: {
        $filter: {
          input: {
            $objectToArray: "$stockByWarehouse"
          },
          as: "warehouse",
          cond: {
            $gt: [
              "$$warehouse.v",
              0
            ]
          }
        }
      }
    }
  }
]);
~~~

The output is an array of pairs where **v > 0**. In SKU-001's data, all three warehouses have stock.

**$$warehouse** is the **$filter** variable representing one array element. **$$warehouse.v** is the quantity of that element. It differs from **"$stockByWarehouse"**, which is a field path on the root document.

### 4.3. Extracting Only the List of Warehouse Codes

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-002" } },
  {
    $project: {
      _id: 0,
      warehouseCodes: {
        $map: {
          input: {
            $objectToArray: "$stockByWarehouse"
          },
          as: "pair",
          in: "$$pair.k"
        }
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  warehouseCodes: ["HCM", "CT"]
}
~~~

Each source element has **k** and **v**, yet **$map** extracts only **k**. This is useful for reporting or inspecting which dynamic attributes are stored.

### 4.4. Counting Warehouses with Positive Stock

~~~javascript
db.products.aggregate([
  {
    $set: {
      activeWarehouseCount: {
        $size: {
          $filter: {
            input: {
              $objectToArray: {
                $ifNull: ["$stockByWarehouse", {}]
              }
            },
            as: "pair",
            cond: {
              $gt: ["$$pair.v", 0]
            }
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      activeWarehouseCount: 1
    }
  }
]);
~~~

Expected results:

| _id | Warehouses with positive stock |
|---|---:|
| SKU-001 | 3 |
| SKU-002 | 2 |
| SKU-003 | 0 |
| SKU-004 | 0 |
| SKU-005 | 1 |

One document entering the pipeline still produces one document leaving. **$objectToArray**, **$filter**, and **$size** are all expressions and do not multiply documents like an **$unwind stage**.

### 4.5. When Is $unwind Needed After $objectToArray?

If you want one report row **per warehouse**, use **$unwind**:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "T1"
    }
  },
  {
    $set: {
      warehousePairs: {
        $objectToArray: {
          $ifNull: ["$stockByWarehouse", {}]
        }
      }
    }
  },
  { $unwind: "$warehousePairs" },
  {
    $project: {
      _id: 0,
      sku: "$_id",
      warehouse: "$warehousePairs.k",
      stock: "$warehousePairs.v"
    }
  },
  {
    $sort: {
      sku: 1,
      warehouse: 1
    }
  }
]);
~~~

Results on T1 data:

~~~javascript
[
  { sku: "SKU-001", warehouse: "DN", stock: 3 },
  { sku: "SKU-001", warehouse: "HCM", stock: 12 },
  { sku: "SKU-001", warehouse: "HN", stock: 7 },
  { sku: "SKU-002", warehouse: "CT", stock: 6 },
  { sku: "SKU-002", warehouse: "HCM", stock: 4 }
]
~~~

**$unwind** changes cardinality: SKU-001 produces three output documents, SKU-002 produces two, and SKU-003 and SKU-004 have empty arrays after conversion so they produce no rows. To retain products with no warehouses, inspect **preserveNullAndEmptyArrays** and handle output accordingly.

## 5. $arrayToObject: From Array of Pairs to Object

### 5.1. Syntax

~~~javascript
{
  $arrayToObject: <arrayExpression>
}
~~~

**arrayExpression** must return an array in **one of two formats**:

1. **Array of two-element arrays:** first element is the field name, second element is the value.
2. **Array of objects with fields `k` and `v`:** `k` is the field name, `v` is the value.

### 5.2. Two-Element Array Format [key, value]

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      _id: 0,
      labels: {
        $arrayToObject: {
          $literal: [
            ["zoneA", "HN"],
            ["zoneB", "HCM"],
            ["zoneC", "DN"]
          ]
        }
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  labels: {
    zoneA: "HN",
    zoneB: "HCM",
    zoneC: "DN"
  }
}
~~~

**$literal** marks the entire source array explicitly as constant data. In many contexts, a valid array literal can also be written directly, yet `$literal` is helpful to avoid interpreting values starting with **`$`**.

### 5.3. Array of {k, v} Objects Format

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      _id: 0,
      flags: {
        $arrayToObject: {
          $literal: [
            { k: "ready", v: true },
            { k: "mode", v: "ONLINE" },
            { k: "attempts", v: 3 }
          ]
        }
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  flags: {
    ready: true,
    mode: "ONLINE",
    attempts: 3
  }
}
~~~

Both array representations produce the same kind of BSON document. For data coming from **$objectToArray**, the **{k, v}** format is most convenient because no structural conversion is needed.

### 5.4. Empty Arrays and null

**$arrayToObject: []** returns an empty object **{}**.

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-003" } },
  {
    $project: {
      _id: 1,
      objectAgain: {
        $arrayToObject: {
          $objectToArray: "$stockByWarehouse"
        }
      }
    }
  }
]);
~~~

Because `stockByWarehouse` is **{}**, `objectAgain` is also **{}**.

If the input to **$arrayToObject** is **null** or **missing**, the expression returns **null**. So when an object is required in the output, provide a default array:

~~~javascript
{
  $arrayToObject: {
    $ifNull: [
      "$pairs",
      []
    ]
  }
}
~~~

**$ifNull** only replaces `null`/missing; it does not turn a malformed array into a valid one.

### 5.5. Errors When Elements Have the Wrong Format

The example below contains an element that is neither a two-element array nor a `{k, v}` object:

~~~javascript
// Malformed example:
{
  $arrayToObject: {
    $literal: [
      ["color", "red", "unexpected"],
      ["size", "M"]
    ]
  }
}
~~~

MongoDB throws an error because a three-element array violates the contract.

Validation guidelines:

- **k must be a string field name** in MongoDB-supported contexts.
- Two-element arrays must have **exactly two elements**.
- The object form must have **k** and **v** as required.
- Do not pass raw numbers/strings expecting MongoDB to infer keys.
- Do not pass unboundedly large arrays; the resulting object is still subject to the BSON document size limit.

## 6. Duplicate Keys in $arrayToObject: Last Value Wins

Suppose source data contains two pairs with the same name **color**:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      _id: 0,
      result: {
        $arrayToObject: {
          $literal: [
            { k: "color", v: "black" },
            { k: "size", v: "M" },
            { k: "color", v: "white" }
          ]
        }
      }
    }
  }
]);
~~~

In modern MongoDB versions, the result is:

~~~javascript
{
  result: {
    color: "white",
    size: "M"
  }
}
~~~

**The value of the last occurrence of a duplicate key is used.** There are no two independent `color` fields in the resulting object as an application might mistakenly expect.

This is useful for applying **ordered precedence**, yet risky if inputs contain unintended duplicate keys. For systems that must reject duplicates instead of overwriting, validate before calling **$arrayToObject**.

### 6.1. Why Distinguish Duplicate Keys from Duplicate Values?

~~~javascript
[
  { k: "color", v: "red" },
  { k: "size", v: "red" }
]
~~~

Both **v** values are `"red"`, yet **k differs**, so the output object keeps both `color` and `size`.

~~~javascript
[
  { k: "color", v: "red" },
  { k: "color", v: "blue" }
]
~~~

Both **k** keys match, so the later occurrence overwrites the earlier value. **$arrayToObject** does not behave like a multimap holding multiple values per field name.

### 6.2. Array Order Implies Precedence

~~~text
[{k:"theme",v:"light"}, {k:"theme",v:"dark"}]
                  |
                  v
         {theme:"dark"}
~~~

Reverse the order:

~~~text
[{k:"theme",v:"dark"}, {k:"theme",v:"light"}]
                  |
                  v
         {theme:"light"}
~~~

If the data source does not guarantee order, do not rely on **last-wins** as an undefined business rule. Sort explicitly or pick a value by deterministic criteria beforehand.

## 7. Combining $objectToArray and $arrayToObject to Transform Field Names

This is a very common pattern:

~~~text
object
  -> $objectToArray
  -> $map or $filter
  -> $arrayToObject
  -> new object
~~~

### 7.1. Adding a Prefix to Every Field Name

Suppose you want to turn:

~~~javascript
{
  color: "black",
  warrantyMonths: 12,
  wireless: true
}
~~~

into:

~~~javascript
{
  attr_color: "black",
  attr_warrantyMonths: 12,
  attr_wireless: true
}
~~~

Pipeline:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      _id: 1,
      renamedAttributes: {
        $arrayToObject: {
          $map: {
            input: {
              $objectToArray: "$attributes"
            },
            as: "pair",
            in: {
              k: {
                $concat: [
                  "attr_",
                  "$$pair.k"
                ]
              },
              v: "$$pair.v"
            }
          }
        }
      }
    }
  }
]);
~~~

Breakdown:

1. **$objectToArray** turns `attributes` into an array of `{k,v}`.
2. **$map** iterates over each element, computing the new key name with **$concat**.
3. Keeps **v** unchanged and replaces **k**.
4. **$arrayToObject** builds the object with the new field names.

For **attributes: null** on SKU-004, add **$ifNull** so `$objectToArray` receives a default object. This example runs only on SKU-001 so it avoids that case.

### 7.2. Removing Specific Fields from a Dynamic Object

Suppose `attributes` contains an internal field **internalNote** that clients must not see. You can filter by key name:

~~~javascript
db.products.aggregate([
  {
    $project: {
      name: 1,
      publicAttributes: {
        $arrayToObject: {
          $filter: {
            input: {
              $objectToArray: {
                $ifNull: ["$attributes", {}]
              }
            },
            as: "pair",
            cond: {
              $ne: [
                "$$pair.k",
                "internalNote"
              ]
            }
          }
        }
      }
    }
  }
]);
~~~

Every pair except key `internalNote` is restored into the object. In the current sample data, `internalNote` is absent, so output matches source `attributes`.

**Security warning:** excluding one field name does not guarantee all sensitive data is hidden. For data with user-supplied dynamic keys, prefer an **allowlist of permitted output fields** when documents contain varied sensitive data, and enforce protection via schema and authorization.

### 7.3. Keeping Only Keys with an Allowed Prefix

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 1,
      filtered: {
        $arrayToObject: {
          $filter: {
            input: {
              $objectToArray: {
                $ifNull: ["$attributes", {}]
              }
            },
            as: "pair",
            cond: {
              $regexMatch: {
                input: "$$pair.k",
                regex: "^public_"
              }
            }
          }
        }
      }
    }
  }
]);
~~~

**$regexMatch** is an aggregation expression returning a boolean. It inspects key names, not `v` values. If no key starts with `public_`, the resulting object is **{}**.

Regexes should be fixed or controlled via trusted configuration; never let users pass arbitrary unbounded regex expressions.

### 7.4. Converting Value Types While Transforming Keys

Suppose all stock quantities must be represented as strings in a JSON report:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      _id: 0,
      stockAsText: {
        $arrayToObject: {
          $map: {
            input: {
              $objectToArray: "$stockByWarehouse"
            },
            as: "pair",
            in: {
              k: "$$pair.k",
              v: {
                $toString: "$$pair.v"
              }
            }
          }
        }
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  stockAsText: {
    HN: "7",
    HCM: "12",
    DN: "3"
  }
}
~~~

This is an **output-only representation**; never overwrite numeric stock in the database with strings if the application still needs accurate addition/subtraction. Type conversion is a schema/contract decision.

## 8. From an Array of Dynamic Attributes to an Object

Not all data starts as an object. Some APIs or ingestion feeds store attributes as an array:

~~~javascript
{
  _id: "IMPORT-001",
  properties: [
    { name: "color", value: "black" },
    { name: "size", value: "M" },
    { name: "weightKg", value: 1.25 }
  ]
}
~~~

### 8.1. Using $map to Build {k, v} and Then $arrayToObject

Create a separate lab collection:

~~~javascript
db.import_rows.insertOne({
  _id: "IMPORT-001",
  properties: [
    { name: "color", value: "black" },
    { name: "size", value: "M" },
    { name: "weightKg", value: 1.25 }
  ]
});
~~~

Pipeline:

~~~javascript
db.import_rows.aggregate([
  {
    $project: {
      _id: 1,
      propertiesAsObject: {
        $arrayToObject: {
          $map: {
            input: "$properties",
            as: "property",
            in: {
              k: "$$property.name",
              v: "$$property.value"
            }
          }
        }
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  _id: "IMPORT-001",
  propertiesAsObject: {
    color: "black",
    size: "M",
    weightKg: 1.25
  }
}
~~~

Here **properties** uses `{name, value}`; thus **$map** is required to reshape each element to `{k, v}` before **$arrayToObject**.

### 8.2. When properties Is Missing or null

~~~javascript
{
  $arrayToObject: {
    $map: {
      input: {
        $ifNull: ["$properties", []]
      },
      as: "property",
      in: {
        k: "$$property.name",
        v: "$$property.value"
      }
    }
  }
}
~~~

If `properties` is absent, **$ifNull** supplies an empty array; **$map** returns `[]`; **$arrayToObject** returns `{}`.

### 8.3. If a Name Appears Twice

~~~javascript
properties: [
  { name: "color", value: "black" },
  { name: "color", value: "white" }
]
~~~

**$arrayToObject** keeps **white** under the last-wins rule. If the domain requires retaining all values for a field name, an object format is unsuitable as the sole source of truth; keep the array form or use a multivalued model.

### 8.4. Controlling Input Quality

Before using client-supplied attribute names as MongoDB field names:

- Verify **name is a valid string**.
- Cap name length and attribute count.
- Allow only characters permitted by business policy.
- Block reserved names such as **_id**, **tenantId**, and **permissions** if output will be merged into a root document.
- Define a clear policy for duplicate names.
- Never accept raw aggregation expressions from clients instead of a key/value list.
- Account for risks of field names containing dots, **`$`**, or null bytes, as well as query/update/index restrictions across MongoDB versions.

**MongoDB supports special field names in certain contexts/versions**, yet permitting them arbitrarily does not mean every driver, index, export format, or dotted path operation handles them smoothly. Standard ingestion APIs should enforce a clear naming policy.

## 9. $mergeObjects: Merging Multiple Objects

### 9.1. Expression Syntax

~~~javascript
{
  $mergeObjects: [
    <objectExpression1>,
    <objectExpression2>,
    ...
  ]
}
~~~

In expression context, **$mergeObjects** combines input objects into **a single new object**. It evaluates left to right.

If a field appears multiple times, the value from the **latest object** overwrites earlier ones.

Example:

~~~javascript
{
  $mergeObjects: [
    { theme: "light", alerts: true },
    { theme: "dark" },
    { locale: "vi-VN" }
  ]
}
~~~

Result:

~~~javascript
{
  theme: "dark",
  alerts: true,
  locale: "vi-VN"
}
~~~

**theme** from the second object overwrites the first object's value, while **alerts** is preserved because later objects do not redefine it.

### 9.2. Practice with Defaults and Overrides

Insert data:

~~~javascript
db.app_settings.insertOne({
  _id: "SETTINGS-001",
  tenantId: "T1",
  defaults: {
    theme: "light",
    locale: "en-US",
    alertsEnabled: true
  },
  overrides: {
    theme: "dark",
    locale: "vi-VN"
  }
});
~~~

Compute effective configuration:

~~~javascript
db.app_settings.aggregate([
  { $match: { _id: "SETTINGS-001" } },
  {
    $project: {
      _id: 0,
      effectiveSettings: {
        $mergeObjects: [
          "$defaults",
          "$overrides"
        ]
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  effectiveSettings: {
    theme: "dark",
    locale: "vi-VN",
    alertsEnabled: true
  }
}
~~~

**$mergeObjects** can read field paths from each document; objects do not have to be written inline in the pipeline.

### 9.3. Three Configuration Layers: system → tenant → request

~~~javascript
db.app_settings.aggregate([
  { $match: { _id: "SETTINGS-001" } },
  {
    $project: {
      effectiveSettings: {
        $mergeObjects: [
          { theme: "light", locale: "en-US", pageSize: 20 },
          "$overrides",
          { pageSize: 50 }
        ]
      }
    }
  }
]);
~~~

This ordering establishes:

~~~text
System defaults    (lowest priority)
      |
      v
Tenant overrides
      |
      v
Request overrides  (highest priority)
~~~

The final **pageSize** is `50`, while `theme`/`locale` come from tenant overrides if present.

In practice, **request overrides** must be validated and allowlisted so clients cannot overwrite fields like `permission`, `securityMode`, or `tenantId` using a free-form object.

### 9.4. $mergeObjects Ignores Null Operands

~~~javascript
{
  $mergeObjects: [
    { a: 1 },
    null,
    { b: 2 }
  ]
}
~~~

Result:

~~~javascript
{ a: 1, b: 2 }
~~~

If **all operands** are null:

~~~javascript
{
  $mergeObjects: [null, null]
}
~~~

the result is **{}**.

Thus merging optional configs works even when some objects are absent:

~~~javascript
{
  $mergeObjects: [
    "$defaults",
    "$overrides"
  ]
}
~~~

If a field is missing or null, MongoDB ignores that null operand. **However**, if an operand is a string or unsupported non-object value in that slot, do not assume it will be ignored like `null`; it can raise a type error.

### 9.5. Null Operand vs. Field Value null

This is an extremely important distinction:

~~~javascript
{
  $mergeObjects: [
    { a: 1, b: 2 },
    { b: null }
  ]
}
~~~

Result:

~~~javascript
{ a: 1, b: null }
~~~

**The object `{b: null}` is not a null operand.** It is a valid object containing field `b`, and **`b: null` overwrites `b: 2`**.

If business logic means "null means do not override," you must **filter out null-valued fields from the override object** before merging, or use another handling policy. You cannot rely on the rule "`$mergeObjects` ignores null operands."

## 10. $mergeObjects Performs a Shallow Merge, Not a Recursive Merge

Consider two configurations:

~~~javascript
const defaults = {
  theme: "light",
  limits: {
    perDay: 100,
    perHour: 10
  }
};

const override = {
  limits: {
    perDay: 20
  }
};
~~~

When merged:

~~~javascript
{
  $mergeObjects: [
    { limits: { perDay: 100, perHour: 10 } },
    { limits: { perDay: 20 } }
  ]
}
~~~

The result is:

~~~javascript
{
  limits: {
    perDay: 20
  }
}
~~~

The **limits** field in the second object overwrites the **entire `limits` object** from the first object. **`perHour: 10` is lost**. **$mergeObjects does not perform a recursive deep merge**.

### 10.1. Intentional Deep Merge at a Known Level

If the structure of **limits** is known in advance, merge the nested sub-object explicitly:

~~~javascript
db.app_settings.insertOne({
  _id: "SETTINGS-NESTED",
  defaults: {
    theme: "light",
    limits: {
      perDay: 100,
      perHour: 10
    }
  },
  overrides: {
    limits: {
      perDay: 20
    }
  }
});
~~~

Pipeline:

~~~javascript
db.app_settings.aggregate([
  { $match: { _id: "SETTINGS-NESTED" } },
  {
    $project: {
      _id: 0,
      effectiveSettings: {
        $mergeObjects: [
          "$defaults",
          "$overrides",
          {
            limits: {
              $mergeObjects: [
                "$defaults.limits",
                "$overrides.limits"
              ]
            }
          }
        ]
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  effectiveSettings: {
    theme: "light",
    limits: {
      perDay: 20,
      perHour: 10
    }
  }
}
~~~

Explanation: the third object in the **outer `$mergeObjects`** overwrites `limits` with the result of the **inner `$mergeObjects`**, where `perDay` is overridden while `perHour` is preserved.

This pattern deep-merges only the explicitly named **limits** field; it is not a general arbitrary-depth deep merge algorithm. If structures have arbitrary deep nesting, use a cleaner schema or explicit application logic.

### 10.2. Do Not Confuse $mergeObjects with the Update $set Operator

An update:

~~~javascript
db.app_settings.updateOne(
  { _id: "SETTINGS-NESTED" },
  {
    $set: {
      "defaults.limits.perDay": 50
    }
  }
);
~~~

targets **one specific nested field**. By contrast, **$mergeObjects** applied to a `limits` object produces a merged object at `limits`'s direct level. The two tools solve different problems.

## 11. Using $mergeObjects with $replaceRoot and $replaceWith

### 11.1. Adding Defaults to a Document Without Deleting Original Fields

Suppose we have an **events** collection:

~~~javascript
db.events.insertMany([
  {
    _id: "EV-001",
    type: "LOGIN",
    severity: "INFO"
  },
  {
    _id: "EV-002",
    type: "PAYMENT",
    severity: "ERROR",
    source: "billing"
  }
]);
~~~

We want every output document to have default **source: "unknown"** and **processed: false**, while keeping real stored values when present:

~~~javascript
db.events.aggregate([
  {
    $replaceRoot: {
      newRoot: {
        $mergeObjects: [
          {
            source: "unknown",
            processed: false
          },
          "$$ROOT"
        ]
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Result:

~~~javascript
[
  {
    _id: "EV-001",
    type: "LOGIN",
    severity: "INFO",
    source: "unknown",
    processed: false
  },
  {
    _id: "EV-002",
    type: "PAYMENT",
    severity: "ERROR",
    source: "billing",
    processed: false
  }
]
~~~

**$$ROOT** is the input document to the current stage. Place **$$ROOT after the defaults object** so actual fields override defaults.

### 11.2. Reversing the Order Changes Override Behavior

~~~javascript
{
  $replaceRoot: {
    newRoot: {
      $mergeObjects: [
        "$$ROOT",
        { source: "unknown" }
      ]
    }
  }
}
~~~

Here every output document gets **source: "unknown"**, even EV-002 which originally had `source: "billing"`. That is because the defaults object was placed **last**, giving it highest precedence.

**Operand order is part of the business rule**, not just syntax style.

### 11.3. How Do $replaceRoot and $replaceWith Differ?

**$replaceRoot**:

~~~javascript
{
  $replaceRoot: {
    newRoot: {
      $mergeObjects: [
        { status: "UNKNOWN" },
        "$$ROOT"
      ]
    }
  }
}
~~~

**$replaceWith**:

~~~javascript
{
  $replaceWith: {
    $mergeObjects: [
      { status: "UNKNOWN" },
      "$$ROOT"
    ]
  }
}
~~~

Both stages replace the current document with a new document, using slightly different syntax. **$mergeObjects** acts as the expression computing the new document; **$replaceRoot/$replaceWith** is the stage performing the root replacement.

### 11.4. Preserving _id When Replacing Root

In a regular read pipeline, output might not need `_id`. However, if using **$replaceRoot** to prepare writes via **$merge/$out**, or to retain a link to the source document, actively preserve `_id`:

~~~javascript
{
  $replaceRoot: {
    newRoot: {
      $mergeObjects: [
        { _id: "$_id", status: "UNKNOWN" },
        "$$ROOT"
      ]
    }
  }
}
~~~

If a user-supplied override object contains **`_id`** and is merged last, it can alter the output's `_id`; when writing back to a collection, this can cause conflicts or identity bugs. Never merge raw user objects into the root of writable documents.

## 12. $mergeObjects Has an Accumulator Form in $group

This is a frequent source of confusion because it shares the **same name** while having context-dependent syntax.

### 12.1. Expression Mode: Merging Multiple Objects Within One Document

~~~javascript
{
  $project: {
    merged: {
      $mergeObjects: [
        "$defaults",
        "$overrides"
      ]
    }
  }
}
~~~

This is an expression taking objects from **a single document** and returning a new object.

### 12.2. Accumulator Mode: Merging Objects Across Multiple Documents in a Group

Suppose each step of a job records a subset of metrics:

~~~javascript
db.job_metrics.insertMany([
  {
    _id: "M1",
    jobId: "JOB-1",
    step: "PARSE",
    metrics: {
      received: NumberInt(120),
      parsed: NumberInt(118)
    }
  },
  {
    _id: "M2",
    jobId: "JOB-1",
    step: "VALIDATE",
    metrics: {
      valid: NumberInt(110),
      rejected: NumberInt(8)
    }
  },
  {
    _id: "M3",
    jobId: "JOB-1",
    step: "WRITE",
    metrics: {
      inserted: NumberInt(110)
    }
  },
  {
    _id: "M4",
    jobId: "JOB-2",
    step: "PARSE",
    metrics: {
      received: NumberInt(30)
    }
  }
]);
~~~

We want one summary document per job:

~~~javascript
db.job_metrics.aggregate([
  {
    $group: {
      _id: "$jobId",
      mergedMetrics: {
        $mergeObjects: "$metrics"
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Expected result values:

~~~javascript
[
  {
    _id: "JOB-1",
    mergedMetrics: {
      received: 120,
      parsed: 118,
      valid: 110,
      rejected: 8,
      inserted: 110
    }
  },
  {
    _id: "JOB-2",
    mergedMetrics: {
      received: 30
    }
  }
]
~~~

**$group** is the stage, and **$mergeObjects: "$metrics"** is the **accumulator** merging `metrics` across multiple documents in each group.

### 12.3. Syntax Differences

| Context | Usage Form |
|---|---|
| **Expression mode** in **$project/$set/$replaceRoot** | **{$mergeObjects: ["$defaults","$overrides"]}** |
| **Accumulator mode** in **$group** | **{$mergeObjects: "$metrics"}** |
| Expression mode with a field holding an array of objects | **{$mergeObjects: "$listOfObjects"}** (when the expression resolves to an array to merge) |

In accumulator mode, the operator merges objects across **documents in the group**. In expression mode, it merges objects returned by expressions on the **current document**.

### 12.4. Watch Out for Duplicate Fields Across Grouped Documents

Suppose a job has two metrics documents:

~~~javascript
{ jobId: "JOB-1", metrics: { count: 10 } }
{ jobId: "JOB-1", metrics: { count: 20 } }
~~~

**The `$mergeObjects` accumulator does not compute `10 + 20`.** It produces an object whose `count` field comes from whichever document is merged last according to execution order.

If business logic needs to **sum counts**, use **$sum** or an aggregation suited to the data unit. If you need the **latest metrics snapshot**, define an explicit sort/timestamp order and handle duplicates under a controlled strategy rather than relying on arbitrary group arrival order.

In the first `job_metrics` example, each step writes **distinct field names**, so the output does not depend on metric-field conflicts.

### 12.5. $mergeObjects Does Not Replace Every Accumulator

~~~javascript
// Does not sum values sharing the same key:
{ $mergeObjects: "$metrics" }
~~~

Compare with:

~~~javascript
// Sums a numeric field across multiple documents:
{ $sum: "$metrics.received" }
~~~

Choose the accumulator by business intent:

- **Combine differently named fields:** `$mergeObjects`.
- **Sum numeric values:** `$sum`.
- **Compute averages:** `$avg`.
- **Collect values into an array:** `$push`.
- **Collect distinct values:** `$addToSet`.
- **Pick first/last value in intentional order:** `$first`/`$last` with an appropriate `$sort`.

## 13. $mergeObjects Can Accept an Array of Objects in Expression Mode

You do not have to hardcode the number of objects to merge. Suppose a document contains:

~~~javascript
{
  _id: "DOC-1",
  patches: [
    { a: 1 },
    { b: 2 },
    { a: 3 }
  ]
}
~~~

When **patches** is an array of BSON documents, you can write:

~~~javascript
db.patch_batches.insertOne({
  _id: "DOC-1",
  patches: [
    { a: 1 },
    { b: 2 },
    { a: 3 }
  ]
});

db.patch_batches.aggregate([
  {
    $project: {
      _id: 1,
      result: {
        $mergeObjects: "$patches"
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  _id: "DOC-1",
  result: {
    a: 3,
    b: 2
  }
}
~~~

In expression mode, **$mergeObjects** can accept an expression returning an **array of documents to merge**, not just a literal operand list. When constructing an array dynamically with **$map/$filter**, ensure the elements are valid objects.

This differs from the `$group` accumulator, where each source document provides one object to merge.

## 14. Combined Problem: Adding a total Field to a Dynamic Stock Object

This pattern combines all three expressions to solve a concrete problem.

### 14.1. Requirement

From the document:

~~~javascript
{
  _id: "SKU-001",
  stockByWarehouse: {
    HN: 7,
    HCM: 12,
    DN: 3
  }
}
~~~

we want to build the object:

~~~javascript
{
  HN: 7,
  HCM: 12,
  DN: 3,
  total: 22
}
~~~

Warehouse codes are not known ahead of time, so we cannot hardcode **$stockByWarehouse.HN + $stockByWarehouse.HCM + ...**.

### 14.2. Step-by-Step Pipeline

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "T1",
      status: "ACTIVE"
    }
  },
  {
    $set: {
      stockPairs: {
        $objectToArray: {
          $ifNull: [
            "$stockByWarehouse",
            {}
          ]
        }
      }
    }
  },
  {
    $set: {
      stockPairs: {
        $concatArrays: [
          "$stockPairs",
          [
            {
              k: "total",
              v: {
                $sum: "$stockPairs.v"
              }
            }
          ]
        ]
      }
    }
  },
  {
    $set: {
      stockWithTotal: {
        $arrayToObject: "$stockPairs"
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      stockWithTotal: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Expected results:

~~~javascript
[
  {
    _id: "SKU-001",
    name: "Wireless Mouse",
    stockWithTotal: {
      HN: 7,
      HCM: 12,
      DN: 3,
      total: 22
    }
  },
  {
    _id: "SKU-002",
    name: "Mechanical Keyboard",
    stockWithTotal: {
      HCM: 4,
      CT: 6,
      total: 10
    }
  },
  {
    _id: "SKU-004",
    name: "USB Hub",
    stockWithTotal: {
      total: 0
    }
  }
]
~~~

SKU-003 is excluded due to `status: "DRAFT"`. SKU-005 is excluded due to `tenantId: "T2"`.

### 14.3. Tracking Document Shape Across Stages

~~~text
stockByWarehouse:
  {HN:7,HCM:12,DN:3}
          |
          | $objectToArray
          v
stockPairs:
  [{k:"HN",v:7},{k:"HCM",v:12},{k:"DN",v:3}]
          |
          | $sum + $concatArrays
          v
stockPairs:
  [..., {k:"total",v:22}]
          |
          | $arrayToObject
          v
stockWithTotal:
  {HN:7,HCM:12,DN:3,total:22}
~~~

In this pipeline **$set is the stage**, while **$objectToArray**, **$concatArrays**, **$sum**, and **$arrayToObject** are expressions.

### 14.4. Warning About the total Key

If a document has an **actual warehouse code named `"total"`**, that key collides with the newly added total field. Because `{k: "total", v: ...}` is appended at the end of the array, **$arrayToObject** uses the computed sum and overwrites the stock of the real warehouse named `total`.

To avoid this, design a safer output structure:

~~~javascript
{
  stockByWarehouse: {
    HN: 7,
    HCM: 12,
    DN: 3
  },
  totalStock: 22
}
~~~

Place **totalStock** in a separate field outside the warehouse map when warehouse codes are open-ended data. Inserting `total` into the map itself should only be used when **"total" is a reserved name** forbidden in input data.

## 15. Combined Problem: Merging Default Configs with Optional Attributes

Suppose a product has attributes:

~~~javascript
{
  attributes: {
    color: "black",
    wireless: true
  }
}
~~~

The application wants to produce a complete output:

~~~javascript
{
  color: "black",
  wireless: true,
  warrantyMonths: 12,
  countryOfOrigin: "UNKNOWN"
}
~~~

### 15.1. Using $mergeObjects to Supply Defaults

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      normalizedAttributes: {
        $mergeObjects: [
          {
            warrantyMonths: 12,
            countryOfOrigin: "UNKNOWN"
          },
          "$attributes"
        ]
      }
    }
  }
]);
~~~

If **attributes** has its own **warrantyMonths**, that value takes precedence. If `attributes` is **null** like SKU-004, the null operand is ignored and the result contains only the defaults.

### 15.2. When null Values Should Mean "Not Provided"

If `attributes` contains:

~~~javascript
{
  warrantyMonths: null
}
~~~

the merge result will have **warrantyMonths: null**, because a field with value `null` overwrites the default `12`.

If the domain wants **null replaced by the default**, add explicit handling:

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 1,
      warrantyMonths: {
        $ifNull: [
          "$attributes.warrantyMonths",
          12
        ]
      }
    }
  }
]);
~~~

For configuration objects with many dynamic keys, to drop all `null` fields before merging, combine **$objectToArray → $filter → $arrayToObject**, and then run **$mergeObjects**.

Example:

~~~javascript
db.products.aggregate([
  {
    $set: {
      nonNullAttributes: {
        $arrayToObject: {
          $filter: {
            input: {
              $objectToArray: {
                $ifNull: ["$attributes", {}]
              }
            },
            as: "pair",
            cond: {
              $ne: ["$$pair.v", null]
            }
          }
        }
      }
    }
  },
  {
    $set: {
      normalizedAttributes: {
        $mergeObjects: [
          {
            warrantyMonths: 12,
            countryOfOrigin: "UNKNOWN"
          },
          "$nonNullAttributes"
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      normalizedAttributes: 1
    }
  }
]);
~~~

**The rule for dropping nulls** must be decided explicitly: in some business domains, `null` represents "user deliberately cleared the value" rather than "not yet supplied," so it cannot always be ignored.

## 16. Combining $objectToArray with $group to Aggregate Dynamic Keys

Suppose we need to know **how many active products are in stock at each warehouse and the total units**, considering only tenant T1.

### 16.1. Pipeline

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "T1",
      status: "ACTIVE"
    }
  },
  {
    $set: {
      warehousePairs: {
        $objectToArray: {
          $ifNull: ["$stockByWarehouse", {}]
        }
      }
    }
  },
  { $unwind: "$warehousePairs" },
  {
    $group: {
      _id: "$warehousePairs.k",
      totalUnits: {
        $sum: "$warehousePairs.v"
      },
      productCount: {
        $sum: 1
      }
    }
  },
  {
    $project: {
      _id: 0,
      warehouse: "$_id",
      totalUnits: 1,
      productCount: 1
    }
  },
  { $sort: { warehouse: 1 } }
]);
~~~

Result:

~~~javascript
[
  { warehouse: "CT", totalUnits: 6, productCount: 1 },
  { warehouse: "DN", totalUnits: 3, productCount: 1 },
  { warehouse: "HCM", totalUnits: 16, productCount: 2 },
  { warehouse: "HN", totalUnits: 7, productCount: 1 }
]
~~~

Notes:

- **$objectToArray** converts each warehouse object into an array of pairs.
- **$unwind** emits one document per pair.
- **$group** groups by **k** (warehouse code) and sums **v** (quantity).
- **$sum: 1** counts **warehouse rows** in the intermediate stream, not automatically distinct products if a product could appear across multiple source records for the same warehouse.

In the warehouse-object model, a single warehouse code cannot appear twice as two independent keys under normal usage, so `productCount` in this example also equals the number of products holding that warehouse field.

### 16.2. When Should Warehouses Be Stored as an Array from the Start?

If each warehouse needs multiple attributes:

~~~javascript
stock: [
  {
    warehouseId: "HN",
    available: 7,
    reserved: 2,
    lastUpdatedAt: ISODate("2026-07-01T10:00:00Z")
  },
  {
    warehouseId: "HCM",
    available: 12,
    reserved: 1,
    lastUpdatedAt: ISODate("2026-07-01T11:00:00Z")
  }
]
~~~

then an array of embedded documents is often a better fit than an object with dynamic keys, especially when:

- you frequently query by `warehouseId`;
- each warehouse needs multiple fields;
- you need clear indexes on subfields;
- you need conditional per-element updates with **arrayFilters**.

**$objectToArray** helps manipulate dynamic objects, but that does not mean a **dynamic object is always the optimal data model**.

## 17. Nested Objects and the Non-Recursive Limitation

### 17.1. Converting a Specific Sub-Object

Consider:

~~~javascript
{
  attributes: {
    resolution: {
      width: 2560,
      height: 1440
    },
    refreshRate: 144
  }
}
~~~

To convert `resolution` specifically:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-003" } },
  {
    $project: {
      _id: 0,
      resolutionPairs: {
        $objectToArray: "$attributes.resolution"
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  resolutionPairs: [
    { k: "width", v: 2560 },
    { k: "height", v: 1440 }
  ]
}
~~~

The query author must **specify the sub-object** to convert. **$objectToArray: "$attributes"** at the parent level does not automatically turn `width` and `height` into separate pairs.

### 17.2. Nested $mergeObjects Must Name Fields Explicitly

~~~javascript
{
  $mergeObjects: [
    "$defaults",
    "$overrides",
    {
      resolution: {
        $mergeObjects: [
          "$defaults.resolution",
          "$overrides.resolution"
        ]
      }
    }
  ]
}
~~~

This pattern performs a deep merge at **one specific level**. If structures contain arbitrary objects at arbitrary depths, a hardcoded expression solution becomes hard to maintain. You may need a normalized data model or well-defined out-of-database processing.

### 17.3. When Objects Have Keys Containing Dots

Modern BSON documents have certain capabilities to store special field names in supported versions, yet a **path like `"a.b"`** in many APIs is interpreted as field `b` nested under `a`, not a literal key `"a.b"`.

When manipulating special field names in the database, MongoDB offers **$getField** and **$setField** in supporting versions. For user-supplied inputs, the simpler and safer approach in most APIs is to **restrict key names**, such as allowing only letters, digits, and underscores with a defined prefix.

Never use raw client keys as unvalidated operators or field paths.

## 18. Wrong-Type Inputs, Missing Fields, and BSON Values

### 18.1. Behavior Comparison Table

| Input | $objectToArray | $arrayToObject | $mergeObjects |
|---|---|---|---|
| Valid object | Returns **{k,v}** array. | Invalid direct input type; requires array. | Merges object. |
| Empty object **{}** | Returns **[]**. | Invalid input type. | Participates in merge, adds no fields. |
| Array **[]** | Invalid input type. | Returns **{}**. | In expression mode, interpreted as an empty array of objects per supported operand form. |
| **null/missing** | Returns **null**. | Returns **null**. | Ignores null operand; all-null returns **{}**. |
| Arbitrary string/number | Not an object, may error. | Not a valid array, may error. | Not a valid document, may error. |

**Note:** `$mergeObjects` accepts different operand forms depending on context (array of objects, array-valued expression, or `$group` accumulator); the table summarizes primary behavior. Do not treat `[]` as though it were universally valid as an object in every syntactic position.

### 18.2. Using $type to Detect Schema Violations

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 1,
      attributesType: {
        $type: "$attributes"
      },
      stockType: {
        $type: "$stockByWarehouse"
      }
    }
  }
]);
~~~

Results can include **"object"**, **"null"**, **"missing"**, **"array"**, or other types. For example, SKU-004 has `attributes: null` and `stockByWarehouse: missing`.

### 18.3. $ifNull Cannot Fix Wrong Non-Null Types

~~~javascript
{
  $objectToArray: {
    $ifNull: ["$attributes", {}]
  }
}
~~~

If `attributes` is the string **"oops"**, `$ifNull` keeps that string, feeding wrong-type input into **$objectToArray**.

When handling legacy data with mixed types, you can guard with:

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 1,
      attributePairs: {
        $cond: [
          {
            $eq: [
              { $type: "$attributes" },
              "object"
            ]
          },
          {
            $objectToArray: "$attributes"
          },
          []
        ]
      }
    }
  }
]);
~~~

In real applications, **silently converting bad input to `[]`** can mask data corruption. Often it is better to raise an error, record a metric, or route the document for remediation instead of silently ignoring it.

### 18.4. Values v Preserve Source Data Types

When `$objectToArray` converts:

~~~javascript
{
  number: NumberInt(12),
  createdAt: ISODate("2026-07-01T10:00:00Z"),
  active: true,
  nested: { a: 1 }
}
~~~

into an array:

~~~javascript
[
  { k: "number", v: NumberInt(12) },
  { k: "createdAt", v: ISODate("2026-07-01T10:00:00Z") },
  { k: "active", v: true },
  { k: "nested", v: { a: 1 } }
]
~~~

**v does not automatically convert to a string**. When `$arrayToObject` reconstructs the object, BSON values keep their native types unless the pipeline explicitly runs conversion expressions like **$toString**, **$toInt**, or **$toDecimal**.

Do not use **JSON.stringify** or JSON string character count to infer BSON size or value types.

## 19. Updating Documents with an Aggregation Pipeline

These three expressions do not serve read pipelines alone. MongoDB supports **updates using an aggregation pipeline** with a permitted set of stages.

### 19.1. Example Persisting totalStock into the Document

~~~javascript
db.products.updateOne(
  { _id: "SKU-001" },
  [
    {
      $set: {
        totalStock: {
          $sum: {
            $map: {
              input: {
                $objectToArray: {
                  $ifNull: ["$stockByWarehouse", {}]
                }
              },
              as: "pair",
              in: "$$pair.v"
            }
          }
        }
      }
    }
  ]
);
~~~

Unlike **aggregate()**, `updateOne` with an array of stages **actually writes the `totalStock` field** on the matching document if the operation succeeds. Since a single document is updated in one operation, MongoDB applies document-level atomicity accordingly.

### 19.2. Merging Configs in an Update Pipeline

~~~javascript
db.app_settings.updateOne(
  { _id: "SETTINGS-001" },
  [
    {
      $set: {
        effectiveSettings: {
          $mergeObjects: [
            "$defaults",
            "$overrides"
          ]
        }
      }
    }
  ]
);
~~~

This command writes `effectiveSettings` into the document. Do not confuse:

- **$set** here is an **allowed stage inside an update pipeline**;
- **$mergeObjects** is the expression computing the new object;
- This is not a **read-only `aggregate()`** command.

### 19.3. Not Every Aggregation Stage Is Allowed in an Update Pipeline

Update pipelines only permit a subset of document-transformation stages, such as **$set/$addFields**, **$project/$unset**, and **$replaceRoot/$replaceWith** per MongoDB documentation. You cannot freely place **$group** or **$lookup** inside an update pipeline and expect MongoDB to accept it.

When business logic needs to aggregate across multiple documents and write to another collection, consider **$merge/$out** in aggregation under appropriate rules and permissions, or a controlled backend workflow.

### 19.4. Do Not Use Expressions to Bypass Authorization

If an application accepts dynamic keys from users and writes them back via **$arrayToObject/$mergeObjects**, protect **_id**, **tenantId**, **ownerId**, **roles**, **permissions**, and system fields. Client-supplied field names must never automatically become permission to overwrite arbitrary document fields.

Build target objects from verified fields or merge only into a **restricted attribute namespace** such as **customAttributes**; never merge raw user input into **$$ROOT** of sensitive documents.

## 20. Java Sync Driver: Using BSON to Build Object Expressions

The MongoDB Java Sync Driver takes **List<Bson>** as a pipeline. You can use **Aggregates** builders or construct **org.bson.Document** for nested expressions.

### 20.1. $objectToArray + $sum in Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;

public final class StockReport {
    public static void run(MongoDatabase database) {
        MongoCollection<Document> products =
                database.getCollection("products");

        Bson match = new Document(
                "$match",
                new Document("tenantId", "T1")
        );

        Bson toPairs = new Document(
                "$set",
                new Document(
                        "warehousePairs",
                        new Document(
                                "$objectToArray",
                                new Document(
                                        "$ifNull",
                                        List.of(
                                                "$stockByWarehouse",
                                                new Document()
                                        )
                                )
                        )
                )
        );

        Bson sumStock = new Document(
                "$set",
                new Document(
                        "totalStock",
                        new Document("$sum", "$warehousePairs.v")
                )
        );

        Bson project = new Document(
                "$project",
                new Document("_id", 1)
                        .append("name", 1)
                        .append("totalStock", 1)
        );

        List<Bson> pipeline = List.of(
                match,
                toPairs,
                sumStock,
                project
        );

        for (Document row : products.aggregate(pipeline)) {
            System.out.println(row.toJson());
        }
    }
}
~~~

Java breakdown:

- **new Document("$match", ...)** is a stage.
- **new Document("$set", ...)** is a stage.
- **new Document("$objectToArray", ...)** is an expression.
- **new Document("$ifNull", ...)** is a helper expression.
- **new Document("$sum", ...)** is an expression summing a value array within one document.

Be careful to distinguish the driver's **org.bson.Document** from other `Document` classes in your application. When mapping report data into DTOs, verify the BSON types of numeric and nested values.

### 20.2. $arrayToObject in Java

~~~java
import org.bson.Document;
import org.bson.conversions.Bson;
import java.util.List;

Bson project = new Document(
        "$project",
        new Document(
                "attributesObject",
                new Document(
                        "$arrayToObject",
                        new Document(
                                "$map",
                                new Document("input", "$properties")
                                        .append("as", "prop")
                                        .append(
                                                "in",
                                                new Document(
                                                        "k",
                                                        "$$prop.name"
                                                ).append(
                                                        "v",
                                                        "$$prop.value"
                                                )
                                        )
                        )
                )
        )
);
~~~

This example corresponds to the **import_rows** collection with an array `properties` field. `"$$prop.name"` must be written literally so MongoDB resolves it as the `$map` variable rather than a Java object path.

### 20.3. $mergeObjects in Java

~~~java
Bson mergeDefaults = new Document(
        "$project",
        new Document(
                "effectiveSettings",
                new Document(
                        "$mergeObjects",
                        List.of(
                                new Document(
                                        "theme",
                                        "light"
                                ).append(
                                        "pageSize",
                                        20
                                ),
                                "$overrides"
                        )
                )
        )
);
~~~

The **defaults `Document`** operand comes before **"$overrides"**, so document overrides take higher priority.

### 20.4. Using a Cursor Instead of Loading All Results into RAM

~~~java
for (Document row : products.aggregate(pipeline)) {
    processResult(row);
}
~~~

For large reports, streaming each document from the cursor avoids materializing the entire result set on the client. However, **$group/$sort** are stages that can still require significant server memory and time; using a cursor does not eliminate server-side computation cost.

## 21. Spring Data MongoDB: AggregationOperation and MongoTemplate

Spring Data MongoDB provides **Aggregation**, **AggregationOperation**, **MongoTemplate**, and entity mapping. You can use builders for simple stages or a **custom AggregationOperation** to write complex MongoDB expressions verbatim.

### 21.1. Custom Stage Example for $objectToArray

~~~java
import java.util.List;

import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

public final class StockReportService {
    private final MongoTemplate mongoTemplate;

    public StockReportService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> stockTotals() {
        AggregationOperation toPairs = context ->
                new Document(
                        "$set",
                        new Document(
                                "pairs",
                                new Document(
                                        "$objectToArray",
                                        new Document(
                                                "$ifNull",
                                                List.of(
                                                        "$stockByWarehouse",
                                                        new Document()
                                                )
                                        )
                                )
                        )
                );

        AggregationOperation sumStock = context ->
                new Document(
                        "$set",
                        new Document(
                                "totalStock",
                                new Document("$sum", "$pairs.v")
                        )
                );

        Aggregation aggregation = Aggregation.newAggregation(
                Aggregation.match(
                        Criteria.where("tenantId").is("T1")
                ),
                toPairs,
                sumStock,
                Aggregation.project(
                        "name",
                        "totalStock"
                )
        );

        AggregationResults<Document> results =
                mongoTemplate.aggregate(
                        aggregation,
                        "products",
                        Document.class
                );

        return results.getMappedResults();
    }
}
~~~

This snippet illustrates pipeline stages; **$objectToArray** and **$sum** are expressions inside the **$set stages**.

### 21.2. Be Careful with Custom BSON and Entity Mapping

A **Custom AggregationOperation** produces raw BSON using **actual MongoDB field names**. If a Java entity uses **@Field("stock_by_warehouse")** while raw stage code references **"$stockByWarehouse"**, the query will not read the expected field.

In systems using custom converters or annotations:

1. Check actual BSON field names.
2. Use appropriate builder/mapping contexts or map field names explicitly.
3. Do not guess output types when `v` holds Decimal128, Date, or embedded documents.
4. Pick a dedicated DTO for aggregation output when the shape no longer matches the input entity.

### 21.3. Building a $mergeObjects Expression in a Custom Stage

~~~java
AggregationOperation mergeSettings = context ->
        new Document(
                "$project",
                new Document(
                        "effectiveSettings",
                        new Document(
                                "$mergeObjects",
                                List.of(
                                        "$defaults",
                                        "$overrides"
                                )
                        )
                )
        );
~~~

This stage can be passed into **Aggregation.newAggregation(...)** and executed via `MongoTemplate`. If `defaults`/`overrides` are raw object fields, the schema/mapper must store them as proper BSON object types.

### 21.4. When to Prefer Builders vs. Raw BSON?

| Approach | Advantage | Caveat |
|---|---|---|
| **Aggregation builders** | Readable, integrates with mapping and Java refactoring. | Not every newer operator has identical APIs across all Spring Data versions. |
| **Custom AggregationOperation / raw Document** | Expresses MongoDB syntax directly; flexible with newer expressions. | Must manage field names, mapping, typos, and version compatibility manually. |
| **Pipeline split into small helper methods** | Controls shape per stage, promotes reuse. | Must keep input/output contracts of each method clear. |

For complex dynamic transformation logic, prefer well-named helper functions constructing **Bson/Document expressions** rather than deeply nested expressions inside controllers.

## 22. Performance, Document Size, and Indexes

### 22.1. The Three Expressions Do Not Create Indexes on Dynamic Keys

Example:

~~~javascript
db.products.aggregate([
  {
    $set: {
      pairs: {
        $objectToArray: "$attributes"
      }
    }
  },
  {
    $match: {
      "pairs.k": "color"
    }
  }
]);
~~~

**pairs** is a computed pipeline field, not a pre-existing stored field in source documents. Standard indexes on source fields do not automatically turn `pairs.k` values into physical index keys over computed output.

If the application frequently queries a specific attribute, consider:

- Querying directly on **attributes.color** with an appropriate index;
- Using a **wildcard index** where dynamic fields fit;
- Designing an array of **{name, value}** with a multikey index when queries match by attribute;
- Restructuring data into a dedicated attributes collection if size/query frequency demands it.

Do not treat `$objectToArray` as a zero-cost substitute for an indexing strategy.

### 22.2. Place $match Early When Possible

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "T1",
      status: "ACTIVE"
    }
  },
  {
    $set: {
      pairs: {
        $objectToArray: {
          $ifNull: ["$attributes", {}]
        }
      }
    }
  }
]);
~~~

If a suitable index exists on `tenantId`/`status`, an early **$match** reduces the number of documents needing transformation.

Conversely, if `$match` depends on the newly computed field, it must run after the stage creating that field (unless the optimizer applies a valid rewrite). Distinguish **source query predicates** from **predicates on computed results**.

### 22.3. Objects with Very Many Keys

Converting an object with tens of thousands of keys via **$objectToArray** creates an array with as many `{k,v}` elements, adding overhead for `k`/`v` field names and array structure.

Consequences:

- Intermediate results can be larger than the original document.
- **$unwind** can explode into huge numbers of intermediate documents.
- **$arrayToObject** constructing large objects can exceed the BSON size limit.
- **$mergeObjects** over large operands consumes CPU and memory.
- Blocking stages like **$group/$sort** experience higher memory pressure.

MongoDB enforces a standard **16 MiB BSON document size limit**, and aggregation stages have memory/spill limits. Do not build pipelines that arbitrarily merge millions of pairs into a single document.

### 22.4. $group Accumulator and Memory

~~~javascript
db.job_metrics.aggregate([
  {
    $group: {
      _id: "$jobId",
      mergedMetrics: {
        $mergeObjects: "$metrics"
      }
    }
  }
]);
~~~

If each job has very many unique metric keys, **mergedMetrics** can grow too large. **allowDiskUse** does not remove the final BSON document size limit.

When key cardinality is too large, return multiple documents, group at finer granularity, or store aggregated statistics using a dedicated schema.

### 22.5. Using explain to Inspect Execution Plans

~~~javascript
db.products.explain("executionStats").aggregate([
  { $match: { tenantId: "T1", status: "ACTIVE" } },
  {
    $set: {
      warehousePairs: {
        $objectToArray: {
          $ifNull: ["$stockByWarehouse", {}]
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      totalStock: {
        $sum: "$warehousePairs.v"
      }
    }
  }
]);
~~~

Inspect `winningPlan`, examined document/key counts, output cardinality, and other metrics depending on server version/engine. On a lab collection with a handful of documents, the planner may pick a collection scan; never draw production performance conclusions from a tiny dataset.

### 22.6. When to Compute on the Server vs. in the Application?

Computing in MongoDB aggregation fits when:

- data must be filtered/summarized close to storage;
- returning only processed fields avoids transferring large objects;
- expressions are reused across reporting pipelines;
- transformations are relatively short with measurable cost.

Computing in Java fits when:

- data is already fetched for another business workflow;
- complex deep-merge algorithms or rich domain rules are needed;
- strict type/key validation is required;
- building nested BSON expressions is harder to maintain than typed Java code.

There is no universal winner; weigh data size, network, indexes, server CPU/memory, and maintainability.

## 23. Protecting the System When Field Names Are Dynamic Data

### 23.1. Field Names Are Not Just Harmless Strings

When a user-submitted array is turned into an object with **$arrayToObject**, the **k** values become real field names. If merged into the root document:

~~~javascript
{
  $mergeObjects: [
    "$$ROOT",
    "$userAttributes"
  ]
}
~~~

then `userAttributes` can overwrite critical fields if unguarded.

Example `userAttributes`:

~~~javascript
{
  tenantId: "OTHER-TENANT",
  role: "ADMIN"
}
~~~

Merging into root without an allowlist can alter `tenantId` or `role` in the output. If the pipeline executes a write, the result can be privilege escalation or data corruption.

### 23.2. Design a Dedicated Namespace for Custom Attributes

Instead of merging into **$$ROOT**, place results inside a **customAttributes** field:

~~~javascript
db.import_rows.aggregate([
  {
    $project: {
      _id: 1,
      customAttributes: {
        $arrayToObject: {
          $map: {
            input: {
              $ifNull: ["$properties", []]
            },
            as: "property",
            in: {
              k: "$$property.name",
              v: "$$property.value"
            }
          }
        }
      }
    }
  }
]);
~~~

In real APIs, validate **name/value** before writing, bounding name format, size, element count, and duplicate keys. A **dedicated namespace** limits blast radius, yet does not replace authorization and schema checks.

### 23.3. Never Let Clients Submit Arbitrary Pipelines

Applications should not take a raw array of aggregation stages sent by a client and execute it directly, because that can:

- trigger expensive resource-exhausting queries;
- leak cross-tenant data;
- alter output shapes and break downstream consumers;
- invoke write stages like **$merge/$out** if permissions allow;
- exceed size and timeout limits.

Instead, accept structured business inputs such as **selectedKeys, filters, sourceMap** in DTOs, validate against an allowlist, and construct the pipeline server-side using permitted operators.

## 24. Quick Comparison of the Three Expressions

| Criterion | $objectToArray | $arrayToObject | $mergeObjects |
|---|---|---|---|
| Input | One object. | One array of key/value pairs. | Multiple objects or array of objects in expression mode; also has accumulator form. |
| Output | Array of **{k,v}**. | One object. | One object. |
| Main use | Traverse dynamic keys. | Rebuild dynamic keys. | Combine configs, defaults, fragments. |
| Recursive merge? | N/A; direct field level only. | No; builds single-level fields. | **No**; shallow merge. |
| Null handling | Returns `null` if input is null/missing. | Returns `null` if input is null/missing. | Ignores null operands; all-null returns `{}`. |
| Empty object/array | **{} → []**. | **[] → {}**. | Empty object adds no fields. |
| Duplicate keys | Does not generate duplicate keys from standard source objects. | Last-wins in modern versions. | Last operand wins. |
| Used in $project/$set? | Yes. | Yes. | Yes. |
| Used as accumulator in $group? | No. | No. | **Yes**. |
| Risks | Large arrays, wrong-type fields. | Invalid keys, duplicate keys, data injection. | Unintended overwrites, null overwrites, whole nested object replacement. |

### 24.1. Choosing an Expression

~~~text
"Need to iterate all keys of an object without knowing key names upfront"
    -> $objectToArray

"Have {k,v} pairs and want to rebuild an object"
    -> $arrayToObject

"Need defaults + overrides in precedence order"
    -> $mergeObjects

"Need to rename or filter dynamic keys"
    -> $objectToArray + $map/$filter + $arrayToObject

"Need to merge objects across multiple records in a group"
    -> $group + $mergeObjects accumulator

"Need arbitrary deep merge at all levels"
    -> Do not assume $mergeObjects does this;
       design explicit per-level merges or custom logic.
~~~

## 25. Common Mistakes

### 25.1. Using $objectToArray as a Standalone Stage

**Wrong:**

~~~javascript
db.products.aggregate([
  { $objectToArray: "$attributes" }
]);
~~~

**$objectToArray** is an expression, not a stage. **Correct:**

~~~javascript
db.products.aggregate([
  {
    $project: {
      attributePairs: {
        $objectToArray: "$attributes"
      }
    }
  }
]);
~~~

### 25.2. Assuming $objectToArray Traverses Nested Objects Automatically

With **{resolution:{width:2560,height:1440}}**, it produces only one pair **{k:"resolution",v:{...}}**. To convert `resolution`, target that sub-object explicitly.

### 25.3. Passing Wrongly Formatted Arrays to $arrayToObject

**Wrong:**

~~~javascript
[
  { name: "color", value: "red" }
]
~~~

This is not an array of **{k,v}**. Use **$map** to transform it into **{k:"color",v:"red"}** before building the object.

### 25.4. Ignoring Duplicate Keys

Two pairs with the same `k` do not create a multimap. **The last value wins**. If overwriting is undesired, validate first or choose a different representation.

### 25.5. Placing Defaults After Overrides

~~~javascript
{
  $mergeObjects: [
    "$overrides",
    "$defaults"
  ]
}
~~~

In this order, **defaults overwrite matching fields from overrides**. For overrides to win, use **[defaults, overrides]**.

### 25.6. Assuming Null Fields Do Not Overwrite

**$mergeObjects ignores null operands**, yet an object **{x:null}** still overwrites field `x`. If null should mean "no override," filter out null fields first.

### 25.7. Expecting $mergeObjects to Deep-Merge Nested Objects

**{limits:{perDay:20}}** overwrites the entire prior `limits` field under the same key. To preserve `perHour`, merge the `limits` sub-object explicitly.

### 25.8. Mixing Accumulator and Expression Syntax

In **$group**:

~~~javascript
{
  $group: {
    _id: "$jobId",
    combined: {
      $mergeObjects: "$metrics"
    }
  }
}
~~~

This is an accumulator across multiple documents. In **$project**, **$mergeObjects** over a list of objects is an expression. Do not conflate execution contexts simply because the operator name is the same.

### 25.9. Using $unwind When You Only Need Per-Document Totals

To sum warehouse stock **per product**, use **$objectToArray + $sum** without unwinding. Unwinding and grouping back forces handling products with no warehouses and preserving grouping keys, adding needless complexity.

### 25.10. Overwriting System Keys During Merge

Never merge raw attributes into **$$ROOT** if they could contain **_id/tenantId/permissions**. Use an allowlist and a dedicated namespace for custom data.

### 25.11. Thinking a Read Pipeline Writes to the Collection

~~~javascript
db.products.aggregate([
  {
    $set: {
      totalStock: 22
    }
  }
]);
~~~

This only transforms the output of **aggregate**. To persist changes, use an update pipeline or controlled write workflow.

### 25.12. Forgetting to Measure Output BSON Size

An oversized intermediate object or array can exceed document output limits or stage memory caps. Never construct a single document containing "every attribute in the entire collection" just because `$mergeObjects` can combine objects.

## 26. Practice Exercises

### Exercise 1 — Reading Warehouse Stock as an Array

From SKU-001, return **warehousePairs**:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      warehousePairs: {
        $objectToArray: "$stockByWarehouse"
      }
    }
  }
]);
~~~

Verify the output contains three pairs: **HN, HCM, DN**.

### Exercise 2 — Summing Stock Without Knowing Warehouse Codes

Use **$objectToArray** and **$sum** to calculate `totalStock` for T1. Expected results: SKU-001 = 22, SKU-002 = 10, SKU-003 = 0, SKU-004 = 0.

### Exercise 3 — Keeping Only Warehouses with Stock

Use **$filter** on the `{k,v}` array to retain only pairs with **v > 0**. If a warehouse has `v = 0`, will it be returned?

### Exercise 4 — Converting an Array of {name,value} into an Object

From document `IMPORT-001` in `import_rows`, produce **propertiesAsObject** containing `color`, `size`, and `weightKg`. Hint: use **$map** and **$arrayToObject**.

### Exercise 5 — Renaming All Keys

Produce **attr_color**, **attr_warrantyMonths**, and **attr_wireless** from SKU-001's `attributes` without hardcoding each field. Hint:

~~~text
$objectToArray -> $map with $concat -> $arrayToObject
~~~

### Exercise 6 — Removing an Internal Key

Create a test document with `attributes`:

~~~javascript
{
  color: "black",
  internalNote: "do-not-publish",
  size: "M"
}
~~~

Use **$filter** to remove `internalNote` and rebuild the public object. Explain why systems with varied sensitive data should prefer an allowlist over denylisting a single key.

### Exercise 7 — Merging Defaults and Overrides

Given:

~~~javascript
defaults: {
  theme: "light",
  locale: "en-US"
}

overrides: {
  theme: "dark"
}
~~~

Use **$mergeObjects** to produce an object with `theme: "dark"` and `locale: "en-US"`. Swap the two operands and explain the change.

### Exercise 8 — Observing Null Operand vs. Null Field Value

Evaluate:

~~~javascript
{ $mergeObjects: [ { x: 1 }, null ] }
{ $mergeObjects: [ { x: 1 }, { x: null } ] }
~~~

Why are the results different?

### Exercise 9 — Merging Nested Objects

Given:

~~~javascript
defaults: {
  limits: { perDay: 100, perHour: 10 }
}

overrides: {
  limits: { perDay: 20 }
}
~~~

Predict the result of **direct `$mergeObjects`**. Then write a **nested `$mergeObjects`** expression that preserves `perHour = 10`.

### Exercise 10 — $mergeObjects Accumulator

On `job_metrics`, group by `jobId` and merge the `metrics` objects. Explain why it does not sum duplicate fields by default.

### Exercise 11 — Totals by Warehouse

Use **$objectToArray + $unwind + $group** to calculate total quantity per warehouse. Verify T1: CT = 6, DN = 3, HCM = 16, HN = 7.

### Exercise 12 — Handling Wrong-Type Fields

Insert a test document with `attributes` set to the string **"invalid"**. Observe the difference between:

~~~javascript
{ $objectToArray: { $ifNull: ["$attributes", {}] } }
~~~

and using **$type + $cond** to convert only when `attributes` is an object. Discuss when to raise an error instead of silently substituting an empty array.

### Exercise 13 — API Accepting Dynamic Keys

An API receives `properties`:

~~~json
[
  {"name": "color", "value": "black"},
  {"name": "tenantId", "value": "ATTACKER"}
]
~~~

Design validation rules so only `customAttributes` is written and a user-supplied `tenantId` key cannot overwrite system fields.

### Exercise 14 — Java and Spring Data

Write a Java pipeline producing **totalStock** from `stockByWarehouse` and print the output. Write one implementation using **org.bson.Document** and one using **MongoTemplate**. Distinguish Java **List<Bson> pipeline stages** from **BSON expression Documents**.

## 27. Review Questions

1. What input type does **$objectToArray** accept and what does it return?
2. In the output of **$objectToArray**, what do **k** and **v** represent?
3. Does **$objectToArray** automatically convert nested objects into `{k,v}` pairs?
4. What is the result of **$objectToArray: {}**?
5. When input is null/missing, how does **$objectToArray** behave?
6. What two array element formats does **$arrayToObject** accept?
7. Why does **[{name:"color",value:"red"}]** require transformation before `$arrayToObject`?
8. What does **$arrayToObject** do when an array has two elements with the same `k`?
9. Does **$arrayToObject: []** return an empty object?
10. How does **$mergeObjects** determine precedence for duplicate fields?
11. How does a null operand differ from an object containing a field with value `null`?
12. Does **$mergeObjects** deep-merge nested objects?
13. When should you use the **$mergeObjects accumulator in `$group`** instead of the expression in `$project`?
14. Why doesn't **$mergeObjects** replace **$sum** for metrics with overlapping numeric field names?
15. Which expressions can be combined to rename all dynamic keys in `attributes`?
16. When should **$unwind** be used after **$objectToArray**?
17. Why is **$ifNull: ["$stockByWarehouse", {}]** useful when a warehouse object field might be absent?
18. Why can using **$mergeObjects** with raw user attributes pose a security risk?
19. What precautions apply if a field name built from `k` contains dots or **`$`** characters?
20. Does an aggregation containing **$set** modify the source collection?
21. How can you inspect whether MongoDB processes too many documents before transforming dynamic objects?
22. When is an **array of `{name,value}`** model better suited than an object with dynamic keys?

## 28. Summary

These three expressions form a powerful toolkit for documents with **dynamic field structures**:

~~~text
$objectToArray
    Object -> [{k, v}, ...]
    Used to iterate, filter, rename, and compute over dynamic keys.

$arrayToObject
    [{k, v}, ...] or [[key, value], ...] -> Object
    Used to rebuild an object after array transformations.
    Duplicate keys: last value wins.

$mergeObjects
    Object A + Object B + ... -> New object
    Used for defaults/overrides and merging object fragments.
    Duplicate fields: later operand wins.
    Null operands are ignored; fields with null values still overwrite.
    Does not perform automatic deep merge.
~~~

To use them properly:

1. **Distinguish stage from expression:** `$project`/`$set`/`$group` are stages; `$objectToArray`/`$arrayToObject`/`$mergeObjects` compute values inside stages. **$mergeObjects** also has an accumulator form when grouping.
2. **Choose an appropriate data model:** dynamic objects suit simple maps; arrays of objects suit rich metadata and attribute-based queries.
3. **Validate input types:** objects, arrays, null, missing, and strings are not arbitrarily interchangeable.
4. **Watch evaluation order:** last-wins behavior in `$arrayToObject` and `$mergeObjects` can dictate business results.
5. **Do not expect deep merge:** to preserve un-overridden nested fields, merge those nested levels explicitly.
6. **Block invalid or sensitive keys:** dynamic field names need validation, dedicated namespaces, and access controls.
7. **Control size:** converting large objects to arrays, unwinding, and grouping can inflate intermediate data volume.
8. **Measure on real workloads:** place indexed filters before transformations when semantics allow; inspect `explain` and metrics.

### Official Documentation

- [MongoDB $objectToArray](https://www.mongodb.com/docs/manual/reference/operator/aggregation/objectToArray/) — **{k,v}** structure, non-recursive limit.
- [MongoDB $arrayToObject](https://www.mongodb.com/docs/manual/reference/operator/aggregation/arrayToObject/) — two input formats, empty arrays, duplicate keys.
- [MongoDB $mergeObjects (expression)](https://www.mongodb.com/docs/manual/reference/expression/mergeobjects/) — merging multiple objects, null operands, and precedence order.
- [MongoDB $mergeObjects (accumulator)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/mergeObjects/) — merging objects across documents in grouping stages.
- [MongoDB $map](https://www.mongodb.com/docs/manual/reference/operator/aggregation/map/) and [$filter](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/) — transforming and filtering array elements.
- [MongoDB $replaceRoot](https://www.mongodb.com/docs/manual/reference/operator/aggregation/replaceRoot/) — replacing the document root with an expression.
- [MongoDB $getField](https://www.mongodb.com/docs/manual/reference/operator/aggregation/getField/) and [$setField](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setField/) — working with special field names in supported versions.
- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) and [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/) — stage flow and resource limits.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — building aggregation pipelines in Java.
- [Spring Data MongoDB Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — aggregation with `MongoTemplate` and Java mapping.

When encountering an object with a variable key set, ask: **"Do I need to iterate keys, construct new keys, or merge objects?"**. Use **$objectToArray** to turn keys into iterable data, **$arrayToObject** to rebuild the structure, and **$mergeObjects** to express precedence across data sources. Combining these three expressions in the right context keeps MongoDB pipelines both flexible and easy to explain, test, and operate safely.
