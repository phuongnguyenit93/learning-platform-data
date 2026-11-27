# User-Defined Types, Object Types, and Collection Types in Oracle Database

## 1. Why Does Oracle Support User-Defined Types?

In the relational model, a table row is typically described using columns of type `NUMBER`, `VARCHAR2`, `DATE`, `TIMESTAMP`, `CLOB`, and so on. However, some business values carry an **intrinsic structure**: an address with street and city; a product with SKU and unit price; an order with multiple line items; a user with a list of phone numbers. Oracle supports **user-defined types (UDTs)** to model these structures as named, reusable types in SQL or PL/SQL depending on the kind.

For example, instead of treating an address merely as an unstructured string:

```text
'42 Nguyen Hue, Ho Chi Minh City'
```

we can represent it as an object with two attributes:

```text
ADDRESS_T
  ├── STREET = '42 Nguyen Hue'
  └── CITY   = 'Ho Chi Minh City'
```

A **collection type** can represent multiple values of the same type, such as a list of promo codes or a list of objects containing `SKU` and `QUANTITY`. Oracle also supports **associative arrays** in PL/SQL, mapping keys to values, which is very useful for in-memory processing inside programs.

The goals of this lesson are to understand:

- The differences among **object types**, **SQL collection types**, and **PL/SQL collection types**.
- How to declare, instantiate, store, query, and manipulate objects and collections.
- The differences among **nested tables**, **VARRAYs**, and **associative arrays**.
- Error-prone cases involving `NULL`, sparse collections, ordering, schema type dependencies, and privileges.
- When the object-relational model helps, and when standard relational tables are the better choice.

> Examples use standard Oracle Database 19c syntax. Certain SQL/PLSQL integration features, size limits, JSON capabilities, and driver behaviors vary by release. Run `CREATE TYPE`, `CREATE TABLE`, `INSERT`, and `DROP` statements only in a lab schema you are authorized to modify.

## 2. Map of Composite Data Types

```text
                     Oracle composite / user-defined types
                                       │
              ┌────────────────────────┴────────────────────────┐
              │                                                 │
              ▼                                                 ▼
       SQL schema types                                    PL/SQL types
       (CREATE TYPE)                                       (TYPE / RECORD)
              │                                                 │
    ┌─────────┴──────────┐                         ┌─────────────┴──────────┐
    ▼                    ▼                         ▼                        ▼
Object type         Collection type          RECORD / %ROWTYPE       Associative array
attributes          ├─ Nested table          temporary structures    INDEX BY key
methods             └─ VARRAY                in PL/SQL               in PL/SQL
    │                    │                         │                        │
    └────────────┬───────┘                         └────────────┬───────────┘
                 ▼                                              ▼
      Usable as SQL column types,                  Used primarily in PL/SQL;
      PL/SQL variables, SQL values                 not equivalent to SQL column types
```

Oracle distinguishes **types created at the schema level** via `CREATE TYPE` from **types declared only inside PL/SQL** via `TYPE` or `RECORD`. A nested table or VARRAY can be declared in either scope; however, if you intend to store it as **a table column type**, you need a **SQL schema-level type**.

| Type | Creation Syntax | Valid as SQL Column Type? | Key Characteristics |
| --- | --- | --- | --- |
| Object type | `CREATE TYPE ... AS OBJECT` | Yes | Multiple attributes; can have methods, constructors, inheritance |
| SQL nested table type | `CREATE TYPE ... AS TABLE OF ...` | Yes | Variable-length collection; stored in a separate storage table when persisted in a table |
| SQL VARRAY type | `CREATE TYPE ... AS VARRAY(n) OF ...` | Yes | Collection with a **maximum element limit**; preserves logical element ordering in the value |
| PL/SQL nested table | `TYPE ... IS TABLE OF ...` in PL/SQL | Not directly usable as a SQL column definition | Transient program data; can become sparse after `DELETE` |
| PL/SQL VARRAY | `TYPE ... IS VARRAY(n) OF ...` in PL/SQL | Not directly usable as a SQL column definition | Small ordered list with a fixed upper limit |
| Associative array | `TYPE ... IS TABLE OF ... INDEX BY ...` | Cannot be declared as a persistent SQL column | Maps integer or string keys to values; no declared upper bound |
| PL/SQL record | `TYPE ... IS RECORD (...)` or `%ROWTYPE` | Not usable as a SQL object column | Groups fields in PL/SQL, distinct from schema object types |

Certain **package-level PL/SQL collection types** can participate in SQL queries via dedicated mechanisms and limits in modern Oracle releases; that does **not** turn an associative array into a schema SQL collection type or allow it directly in `CREATE TABLE`.

## 3. What Is an Object Type?

An **object type** is a named SQL type defined in a schema. It describes a value with **attributes** and optionally **member methods**, **static methods**, **constructors**, or comparison logic. The concept resembles a class in object-oriented languages, though a SQL object type should not be treated as strictly identical to a Java class.

Example `ADDRESS_T` type:

```sql
-- Run in a lab schema with CREATE TYPE privilege.
CREATE TYPE address_t AS OBJECT (
    street VARCHAR2(120 CHAR),
    city   VARCHAR2(80 CHAR)
);
/
```

A value of this type can be instantiated using the default **constructor**:

```sql
SELECT address_t('42 Nguyen Hue', 'Ho Chi Minh City') AS addr
FROM   dual;
```

For an object type with two attributes, the default constructor takes two matching arguments. If the type definition changes or defines custom constructors, check the actual constructor signatures.

### 3.1. Object Columns in a Relational Table

Once a SQL object type exists, a relational table column can hold object values:

```sql
CREATE TABLE customer_contacts (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(100 CHAR) NOT NULL,
    address     address_t
);

INSERT INTO customer_contacts (customer_id, full_name, address)
VALUES (
    1,
    'Nguyen An',
    address_t('42 Nguyen Hue', 'Ho Chi Minh City')
);
```

Reading attributes from an object column:

```sql
SELECT c.customer_id,
       c.full_name,
       c.address.street AS street,
       c.address.city   AS city
FROM   customer_contacts c
WHERE  c.customer_id = 1;
```

**Syntax tip:** When accessing attributes/methods of an object column in SQL, use a **table alias** such as `c.address.city`. This helps Oracle disambiguate schema, table, column, and attribute names across chained dots.

### 3.2. One Object Value, Multiple Attributes

```text
CUSTOMER_CONTACTS row
  CUSTOMER_ID = 1                  -- NUMBER
  FULL_NAME   = 'Nguyen An'       -- VARCHAR2
  ADDRESS     = ADDRESS_T(...)    -- object column
                ├── STREET = '42 Nguyen Hue'
                └── CITY   = 'Ho Chi Minh City'
```

This differs from placing `ADDRESS_STREET` and `ADDRESS_CITY` directly as two columns in the table, because `ADDRESS` carries its own **type identity**. Two distinct object types with identical attribute names remain **two separate SQL types** and cannot automatically be treated as interchangeable structural records.

## 4. A Null Object Differs from an Object with `NULL` Attributes

This is the most common pitfall when starting out with object types.

| Expression | Meaning |
| --- | --- |
| `CAST(NULL AS address_t)` or uninitialized object variable | **Atomically null object**: the entire object has no value |
| `address_t(NULL, NULL)` | An **existing object**, where both attributes are `NULL` |
| `address_t('42 Nguyen Hue', NULL)` | An existing object whose `CITY` attribute is `NULL` |

Example in PL/SQL:

```sql
SET SERVEROUTPUT ON

DECLARE
  l_not_initialized address_t;
  l_empty_address   address_t := address_t(NULL, NULL);
BEGIN
  IF l_not_initialized IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('Object 1 is atomically NULL');
  END IF;

  IF l_empty_address IS NOT NULL THEN
    DBMS_OUTPUT.PUT_LINE('Object 2 exists, attributes can be NULL');
  END IF;
END;
/
```

For an atomically null object, do not assign directly to `l_not_initialized.street` as if the object already exists. Initialize the object via a constructor first. Distinguishing a **null object** from **null attributes** is especially important when designing nullable columns and handling data in Java/JDBC.

## 5. Member Methods and Type Bodies

Object types do not only store data; they can encapsulate operations over their attributes. In Oracle, the **type specification** declares methods, while the **type body** holds PL/SQL implementations for methods requiring a body.

Example of an item with a net price and a method computing gross price after tax:

```sql
CREATE TYPE price_item_t AS OBJECT (
    sku        VARCHAR2(30 CHAR),
    net_amount NUMBER(12, 2),

    MEMBER FUNCTION gross_amount(p_tax_percent NUMBER)
      RETURN NUMBER
);
/

CREATE TYPE BODY price_item_t AS
  MEMBER FUNCTION gross_amount(p_tax_percent NUMBER)
    RETURN NUMBER
  IS
  BEGIN
    RETURN ROUND(SELF.net_amount * (1 + p_tax_percent / 100), 2);
  END gross_amount;
END;
/
```

`SELF` refers to the object instance on which the member method is called. Inside this method, `SELF.net_amount` is the attribute of the current instance. All calculations still follow SQL/PLSQL `NULL` rules: `net_amount = NULL` causes the multiplication to yield `NULL`.

Using it in PL/SQL:

```sql
SET SERVEROUTPUT ON

DECLARE
  l_item price_item_t := price_item_t('BK-001', 100);
BEGIN
  DBMS_OUTPUT.PUT_LINE('Net amount  : ' || l_item.net_amount);
  DBMS_OUTPUT.PUT_LINE('Gross amount: ' || l_item.gross_amount(10));
  -- Gross amount: 110
END;
/
```

Or storing it in an object column and calling the method from SQL:

```sql
CREATE TABLE price_quotes (
    quote_id NUMBER PRIMARY KEY,
    item     price_item_t
);

INSERT INTO price_quotes (quote_id, item)
VALUES (1, price_item_t('BK-001', 100));

SELECT q.quote_id,
       q.item.sku AS sku,
       q.item.net_amount AS net_amount,
       q.item.gross_amount(10) AS gross_amount
FROM   price_quotes q;
```

### 5.1. Member, Static, Constructor, and Comparison Methods

| Component | Meaning | Use Case |
| --- | --- | --- |
| **Attribute** | Data field of the object | `sku`, `net_amount` |
| **Member method** | Function/procedure invoked on an instance, with `SELF` | `item.gross_amount(10)` |
| **Static method** | Type-level method, requiring no `SELF` instance | Factory/helper logic defined on the type |
| **Constructor method** | Creates an object instance; system-defined or user-defined | `price_item_t('BK-001',100)` |
| **MAP method** | Maps the object to a scalar value for comparison/sorting | Sorting versions/priorities by an attribute |
| **ORDER method** | Compares two objects of the same type using custom logic | Complex business ordering |

Oracle enforces specific rules when defining `MAP` or `ORDER` methods; never declare both on the same object type. Never assume `ORDER BY object_column` works automatically like sorting JSON strings unless an appropriate comparison method is defined.

### 5.2. How Does an Object Method Differ from a Regular Package Function?

With a package function, data is passed in as parameters or queried inside. With a member method, attribute data lives in the current object and is accessed via `SELF`. Even so, member methods execute inside the Oracle engine and are subject to execution privileges, dependencies, and PL/SQL/SQL rules just like stored program units. Methods with side effects, embedded SQL, or exceptions affect predictability and performance when invoked across many rows.

## 6. Object Tables: Each Table Row Is an Object

In addition to **object columns** inside regular relational tables, Oracle supports **object tables** declared with `OF <object_type>`; each row in the table represents an object of that type.

```sql
-- This is a different table type than customer_contacts(address address_t).
CREATE TABLE address_objects OF address_t;

INSERT INTO address_objects
VALUES (address_t('10 Le Loi', 'Ho Chi Minh City'));

SELECT a.street, a.city
FROM   address_objects a;
```

An object table has object identity and supports **object identifiers (OIDs)** / `REF` for cross-table object references in object-relational designs. A relational table containing an object column has different semantics. Do not pick an object table just for concise syntax: evaluate `REF`, constraints, business keys, ORM tooling, and actual query patterns.

### 6.1. `REF`, `DEREF`, and Trade-Offs

In the object-relational model, `REF` represents a reference to an object row in an object table; `DEREF` reads the referenced object. Oracle defines scoping rules (`SCOPE`), privileges, and **dangling REF** conditions when the target object is no longer valid.

```text
Object table: CUSTOMERS_OBJECTS
  row customer #10  ◄───────────── REF in another object
            │
            └── DEREF → read customer object
```

For simple order → customer relationships, **foreign keys on NUMBER/VARCHAR2 columns** are usually far easier to use across SQL, ORMs, and BI tools. `REF` fits when an application genuinely leverages the object-relational model and has an explicit strategy for object identity and lifecycles.

## 7. Inheritance and Polymorphism of Object Types

Oracle supports **type hierarchies**. A supertype declared `NOT FINAL` can have subtypes inheriting attributes/methods; subtypes can add attributes/methods and override methods where allowed.

Simple example:

```sql
CREATE TYPE party_t AS OBJECT (
    party_id NUMBER
) NOT FINAL;
/

CREATE TYPE person_t UNDER party_t (
    full_name VARCHAR2(100 CHAR)
);
/
```

`PERSON_T` inherits `PARTY_ID` from `PARTY_T` and adds `FULL_NAME`. Type hierarchies affect **substitutability** of object columns/tables, type checking, and method dispatch. Oracle provides syntax such as `IS OF (type)` and `TREAT` to test or narrow subtypes in SQL.

Use this feature intentionally. If business requirements simply call for two tables linked by a foreign key, UDT inheritance will not necessarily simplify queries or migrations. Furthermore, altering a supertype can impact all dependent subtypes and tables.

## 8. Collection Types: One Value Holding Multiple Elements

A **collection** is a value containing multiple elements. All elements share the same type, either scalar like `NUMBER`/`VARCHAR2` or a user-defined object type. Oracle supports three common collection families:

```text
Nested table                        VARRAY                             Associative array
────────────                        ──────                             ─────────────────
value = ['A','B','C']               value = ['A','B','C']              map['A'] = 5
no declared element cap             max cap at CREATE TYPE             map['B'] = 8
can become sparse in PL/SQL         ordered and typically dense        INTEGER/VARCHAR2 key
SQL schema type storable in column  SQL schema type storable in column PL/SQL runtime collection
```

**"Array" is not precise enough:** choosing nested table, VARRAY, or associative array determines storage layout, element bounds, ordering, available methods, and whether SQL supports it.

| Property | Nested Table | VARRAY | Associative Array |
| --- | --- | --- | --- |
| Key/index type in PL/SQL | Integer subscript | Integer subscript from 1 to `COUNT` | `PLS_INTEGER` or `VARCHAR2` |
| Fixed upper bound at declaration | No | **Yes**, `VARRAY(n)` | No |
| Logical position/order preserved in value | Has PL/SQL index; when stored/queried from storage table **do not rely on order** | Preserves logical element order | Traversed in key order, not insertion order |
| Can become sparse after deleting elements? | Yes via `DELETE` | Not via `DELETE(i)` | Yes: arbitrary keys can be absent |
| `EXTEND`, `TRIM` | Yes | Yes, within `LIMIT` | No |
| `DELETE(i)` | Yes | No | Yes |
| Persistent SQL column type? | Yes if schema type | Yes if schema type | **No** |
| `TABLE()` in SQL | Yes for SQL collection types | Yes for SQL collection types | Supports certain PL/SQL→SQL operations with limits; not a schema column type |

## 9. Nested Tables: Variable-Length Element Sets

### 9.1. Creating a SQL Nested Table Type

Example of a customer having multiple phone numbers:

```sql
CREATE TYPE phone_numbers_t AS TABLE OF VARCHAR2(30 CHAR);
/
```

`PHONE_NUMBERS_T` is a **SQL schema type**, not a standalone table with rows. To store the collection in a column, declare a table with that column and specify a **storage table** using `NESTED TABLE ... STORE AS`:

```sql
CREATE TABLE customer_phones (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(100 CHAR),
    phones      phone_numbers_t
)
NESTED TABLE phones STORE AS customer_phones_nt;
```

Inserting data:

```sql
INSERT INTO customer_phones (customer_id, full_name, phones)
VALUES (
    1,
    'Nguyen An',
    phone_numbers_t('0901000001', '02830000001')
);

INSERT INTO customer_phones (customer_id, full_name, phones)
VALUES (
    2,
    'Tran Binh',
    phone_numbers_t()
);
```

`phone_numbers_t('0901000001', ...)` calls the constructor to create a two-element collection. `phone_numbers_t()` creates an initialized but **empty** collection. `CUSTOMER_PHONES_NT` is the Oracle-managed **nested table storage** holding elements; it is not an independent business table whose structure you alter directly.

### 9.2. Querying Elements with the `TABLE()` Operator

```sql
SELECT c.customer_id,
       c.full_name,
       p.COLUMN_VALUE AS phone_number
FROM   customer_phones c,
       TABLE(c.phones) p
ORDER BY c.customer_id, p.COLUMN_VALUE;
```

Illustrative output:

```text
CUSTOMER_ID  FULL_NAME   PHONE_NUMBER
-----------  ----------  ------------
1            Nguyen An   02830000001
1            Nguyen An   0901000001
```

For collections of scalars (`VARCHAR2`, `NUMBER`, ...), elements appear under the column name **`COLUMN_VALUE`**. The second customer produces no rows in the `TABLE()` expansion because their collection is empty. If you want to retain customers with no phone numbers, use an outer join or aggregation per query requirements.

**Do not rely on element order when `TABLE()` reads a persisted nested table.** Oracle treats persisted nested tables as unordered sets, and storage does not guarantee preserving insertion order. When business order matters, store an explicit **ordinal/position** attribute in an element object or use a child table with an explicit ordering column.

### 9.3. Null Collections vs. Empty Collections in a Column

Consider three values:

```sql
-- NULL collection: not initialized to a collection value.
INSERT INTO customer_phones (customer_id, full_name, phones)
VALUES (3, 'Le Chi', NULL);

-- Empty collection: initialized, element COUNT = 0.
INSERT INTO customer_phones (customer_id, full_name, phones)
VALUES (4, 'Vo Dung', phone_numbers_t());

-- Collection containing one NULL element.
INSERT INTO customer_phones (customer_id, full_name, phones)
VALUES (5, 'Pham Em', phone_numbers_t(NULL));
```

These cases **have distinct meanings**: `NULL collection`, `empty collection`, and `collection containing a NULL element`.

```sql
SELECT c.customer_id,
       CASE WHEN c.phones IS NULL THEN 'NULL_COLLECTION'
            ELSE 'INITIALIZED' END AS collection_state,
       CARDINALITY(c.phones) AS element_count
FROM   customer_phones c
ORDER BY c.customer_id;
```

`CARDINALITY` returns the number of elements in a collection when supported in SQL. For a null collection, it returns `NULL`; for an empty collection, `0`; a collection containing one `NULL` still has **one element**. When application logic distinguishes "not provided" from "none", define both states explicitly in the data contract.

### 9.4. Collections Containing Objects Instead of Scalars

Nested tables can also hold **object types**:

```sql
CREATE TYPE order_line_t AS OBJECT (
    sku      VARCHAR2(30 CHAR),
    quantity NUMBER
);
/

CREATE TYPE order_lines_t AS TABLE OF order_line_t;
/

CREATE TABLE orders_with_lines (
    order_id NUMBER PRIMARY KEY,
    lines    order_lines_t
)
NESTED TABLE lines STORE AS orders_lines_nt;

INSERT INTO orders_with_lines (order_id, lines)
VALUES (
    100,
    order_lines_t(
      order_line_t('SKU-A', 2),
      order_line_t('SKU-B', 1)
    )
);
```

Querying:

```sql
SELECT o.order_id, l.sku, l.quantity
FROM   orders_with_lines o,
       TABLE(o.lines) l
ORDER BY o.order_id, l.sku;
```

For **collections of object types**, Oracle exposes object attributes directly (`l.sku`, `l.quantity`); for collections of **scalars**, use `COLUMN_VALUE`. Knowing this distinction avoids common syntax errors with `TABLE()`.

## 10. VARRAY: Bounded, Logically Ordered Lists

### 10.1. Creating a SQL VARRAY Type

Example where each service plan stores at most four discount levels:

```sql
CREATE TYPE discount_levels_t AS VARRAY(4) OF NUMBER(5, 2);
/

CREATE TABLE service_plans (
    plan_id         NUMBER PRIMARY KEY,
    discount_levels discount_levels_t
);

INSERT INTO service_plans (plan_id, discount_levels)
VALUES (1, discount_levels_t(5, 10, 15));
```

This is a VARRAY with a limit of **4 elements**. Values can hold 0–4 elements, yet `EXTEND` cannot exceed that limit in PL/SQL. VARRAY is a **logically ordered** collection, so positions 1, 2, 3 carry meaning for the application.

### 10.2. Iterating a VARRAY in PL/SQL

```sql
SET SERVEROUTPUT ON

DECLARE
  l_levels discount_levels_t := discount_levels_t(5, 10, 15);
BEGIN
  DBMS_OUTPUT.PUT_LINE('COUNT=' || l_levels.COUNT);
  DBMS_OUTPUT.PUT_LINE('LIMIT=' || l_levels.LIMIT);

  FOR i IN 1 .. l_levels.COUNT LOOP
    DBMS_OUTPUT.PUT_LINE('Position ' || i || ': ' || l_levels(i));
  END LOOP;

  l_levels.EXTEND;
  l_levels(4) := 20;
  DBMS_OUTPUT.PUT_LINE('New COUNT=' || l_levels.COUNT);
END;
/
```

A VARRAY's `LIMIT` is its declared bound (here `4`). For nested tables and associative arrays, `LIMIT` does not return a finite upper bound.

### 10.3. Querying a VARRAY in SQL

```sql
SELECT p.plan_id,
       d.COLUMN_VALUE AS discount_percent
FROM   service_plans p,
       TABLE(p.discount_levels) d
ORDER BY p.plan_id, d.COLUMN_VALUE;
```

This **unnests** elements into relational rows. Even though a VARRAY has logical element order, **a SQL result set has no guaranteed output order without `ORDER BY`**. If element positions must be returned reliably and queried in SQL, model position explicitly rather than inferring it from `ROWNUM` over `TABLE()`.

### 10.4. How Are VARRAYs Stored in the Database?

A VARRAY is generally treated as a single collection value attached to the parent row. Oracle stores VARRAYs **inline** or via **LOB** depending on size/properties, element type, and release. It **does not automatically create a separate nested storage table** like `NESTED TABLE ... STORE AS`.

VARRAY works well for **relatively small, strictly bounded lists that need logical order**. If you frequently search/join individual elements, update single elements often, or allow lists to grow unboundedly, a relational child table is usually far easier to manage.

## 11. Associative Arrays: Key → Value Maps in PL/SQL

An **associative array** (historically called an *index-by table*) is a collection type declared in PL/SQL using `INDEX BY`. It excels as a temporary lookup table, frequency counter, in-program cache, or bulk-processing buffer in PL/SQL.

### 11.1. Example Mapping SKU Codes to Quantities

```sql
SET SERVEROUTPUT ON

DECLARE
  TYPE quantity_by_sku_t IS TABLE OF PLS_INTEGER
    INDEX BY VARCHAR2(30);

  l_quantities quantity_by_sku_t;
  l_key        VARCHAR2(30);
BEGIN
  l_quantities('SKU-A') := 5;
  l_quantities('SKU-B') := 8;
  l_quantities('SKU-C') := 2;

  DBMS_OUTPUT.PUT_LINE('SKU-B=' || l_quantities('SKU-B'));

  l_key := l_quantities.FIRST;
  WHILE l_key IS NOT NULL LOOP
    DBMS_OUTPUT.PUT_LINE(l_key || ' => ' || l_quantities(l_key));
    l_key := l_quantities.NEXT(l_key);
  END LOOP;
END;
/
```

Keys can be `PLS_INTEGER` or a supported string type; they do not have to start at `1`, do not have to be contiguous, and **have no `VARRAY(n)` upper limit**. Traversal via `FIRST`/`NEXT` follows **key** order—which for string keys obeys NLS/comparison rules; never rely on insertion order.

### 11.2. When Is an Associative Array Unsuitable?

- When creating a SQL table column `sku_quantities quantity_by_sku_t`, because associative arrays are **not SQL schema collection types**.
- When persistent data needs SQL queries/joins with indexes, foreign keys, constraints, and table statistics.
- When sharing a type contract across multiple external applications outside PL/SQL without explicit supported mapping/binding.

To persist a key–value dataset in tables, the standard relational model is `SKU_QUANTITY(parent_id, sku, quantity)` with an explicit primary/unique key. At PL/SQL runtime, associative arrays remain a very efficient transient structure.

## 12. Essential Collection Methods

Oracle PL/SQL provides common collection methods. They do not behave identically across all three collection kinds.

| Method | Meaning | Notes |
| --- | --- | --- |
| `COUNT` | Number of currently existing elements | Differs from `LAST` if a nested table/associative array is sparse |
| `FIRST`, `LAST` | First and last existing index/key | Empty collections normally return `NULL` |
| `PRIOR(i)`, `NEXT(i)` | Existing key/index before or after `i` | Essential when collections have gaps |
| `EXISTS(i)` | `TRUE` if an element at index/key `i` exists | Safe check before accessing potentially missing subscripts |
| `LIMIT` | Max element bound of a VARRAY | Returns `NULL` for nested tables/associative arrays |
| `EXTEND` | Increases allocated element slots | For nested table/VARRAY; not associative array |
| `TRIM` | Removes one or more elements from the end | For nested table/VARRAY; not associative array |
| `DELETE`, `DELETE(i)` | Deletes elements or the entire collection | For nested table/associative array; VARRAY does not support `DELETE` |

### 12.1. `COUNT` Differs from `LAST` on Sparse Nested Tables

```sql
SET SERVEROUTPUT ON

DECLARE
  TYPE tags_t IS TABLE OF VARCHAR2(30);
  l_tags tags_t := tags_t('db', 'sql', 'plsql');
  l_idx PLS_INTEGER;
BEGIN
  l_tags.DELETE(2); -- Removes element 2 while keeping indexes 1 and 3.

  DBMS_OUTPUT.PUT_LINE('COUNT=' || l_tags.COUNT); -- 2
  DBMS_OUTPUT.PUT_LINE('LAST='  || l_tags.LAST);  -- 3

  l_idx := l_tags.FIRST;
  WHILE l_idx IS NOT NULL LOOP
    DBMS_OUTPUT.PUT_LINE(l_idx || ': ' || l_tags(l_idx));
    l_idx := l_tags.NEXT(l_idx);
  END LOOP;
END;
/
```

After `DELETE(2)`, `COUNT=2` while `LAST=3`. A `FOR i IN 1 .. l_tags.COUNT` loop is **unsafe on sparse nested tables**, because index `2` no longer exists. `FIRST` + `NEXT` handles gaps cleanly.

### 12.2. `EXTEND` and `TRIM` Differ from `DELETE`

`EXTEND` appends elements at the end of a nested table/VARRAY. `TRIM` removes elements from the end. In a nested table where elements were previously removed with `DELETE`, mixing `DELETE`, `EXTEND`, and `TRIM` requires care because Oracle tracks an **internal size** distinct from the count of remaining elements; never assume `TRIM` deletes relative to `LAST` of existing elements.

Predictable VARRAY example:

```sql
DECLARE
  TYPE codes_t IS VARRAY(3) OF VARCHAR2(20);
  l_codes codes_t := codes_t('A');
BEGIN
  l_codes.EXTEND;
  l_codes(2) := 'B';
  l_codes.TRIM;
  -- 'A' remains.
END;
/
```

A VARRAY with bound 3 raises an error if code attempts to extend past the limit. Never assume Oracle grows type bounds automatically like `ArrayList` in Java.

## 13. `NULL`, Empty, and Uninitialized Collections

For nested tables and VARRAYs, a variable declared by type **without assigning a constructor** is an **atomically NULL** collection. Calling `COUNT`, `EXTEND`, or indexing elements before initialization typically raises `COLLECTION_IS_NULL` (`ORA-06531`).

```sql
SET SERVEROUTPUT ON

DECLARE
  TYPE code_list_t IS TABLE OF VARCHAR2(20);

  l_null  code_list_t;                 -- atomically NULL
  l_empty code_list_t := code_list_t(); -- initialized, 0 elements
BEGIN
  IF l_null IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('l_null is NULL');
  END IF;

  DBMS_OUTPUT.PUT_LINE('l_empty.COUNT=' || l_empty.COUNT);
  l_empty.EXTEND;
  l_empty(1) := 'A';
  DBMS_OUTPUT.PUT_LINE('l_empty.COUNT=' || l_empty.COUNT);
END;
/
```

By contrast, an **associative array** starts as an **empty collection** upon declaration and needs no constructor like nested tables/VARRAYs. However, reading a nonexistent key raises an exception, so use `EXISTS(key)` or traversal methods.

| Case | `COUNT` | Element Access |
| --- | --- | --- |
| Uninitialized nested table / VARRAY | Raises `COLLECTION_IS_NULL` | Cannot access |
| Nested table / VARRAY after empty constructor | `0` | No elements yet; must `EXTEND` or assign appropriately |
| Sparse nested table after `DELETE(i)` | Remaining element count | Deleted index is no longer valid to read |
| Newly declared associative array | `0` | Only assigned keys are readable |

Other errors include `SUBSCRIPT_BEYOND_COUNT`, `SUBSCRIPT_OUTSIDE_LIMIT`, or `NO_DATA_FOUND` depending on the operation. Always match **collection kind, initialization state, and index** before handling exceptions.

## 14. SQL Collections and PL/SQL Collections Are Not Always Interchangeable

Compare these two blocks:

```sql
-- SQL schema type, usable as a SQL column type.
CREATE TYPE number_list_sql_t AS TABLE OF NUMBER;
/
```

```sql
-- PL/SQL local type, exists only within the block scope.
DECLARE
  TYPE number_list_local_t IS TABLE OF NUMBER;
  l_values number_list_local_t := number_list_local_t(10, 20);
BEGIN
  DBMS_OUTPUT.PUT_LINE(l_values.COUNT);
END;
/
```

Even though both types hold `NUMBER`, their **type identities and declaration scopes differ**. You cannot use `NUMBER_LIST_LOCAL_T` from an anonymous block in `CREATE TABLE`, nor treat it automatically as `NUMBER_LIST_SQL_T` when calling a procedure expecting the schema type.

### 14.1. `TABLE()` Bridges SQL Collections → Rows

With a SQL nested table or VARRAY type:

```sql
SELECT v.COLUMN_VALUE AS n
FROM   TABLE(number_list_sql_t(10, 20, 30)) v
ORDER BY v.COLUMN_VALUE;
```

This produces three rows with values `10`, `20`, `30`. No physical table `NUMBER_LIST_SQL_T` is created just from calling `TABLE()`: it constructs a collection value and unnests it inside the query.

### 14.2. `BULK COLLECT` and `FORALL`

Collections are especially useful in PL/SQL when processing many rows:

```sql
DECLARE
  TYPE id_list_t IS TABLE OF NUMBER;
  l_ids id_list_t;
BEGIN
  SELECT customer_id
  BULK COLLECT INTO l_ids
  FROM   customer_contacts
  WHERE  customer_id <= 100;

  DBMS_OUTPUT.PUT_LINE('Collected rows: ' || l_ids.COUNT);
END;
/
```

`BULK COLLECT` fetches multiple rows into a collection to reduce SQL–PL/SQL context switches. `FORALL` executes bulk DML across collection subscripts when properly designed. For sparse collections, `INDICES OF` or `VALUES OF` avoids assuming contiguous indexes.

**Never make unbounded `BULK COLLECT` your default** across millions of rows: elements reside in the session's PGA memory and can exhaust memory. For large datasets, use `FETCH ... BULK COLLECT ... LIMIT n` or paginated processing aligned with transaction design.

## 15. Limits of `TABLE()` and SQL Semantics

When writing `FROM table_name t, TABLE(t.collection_column) x`, Oracle expands collection elements into a rowset. Key behaviors to remember:

1. **Null/empty collections** emit no element rows; an ordinary join can drop the parent row.
2. **Scalar elements** appear under `COLUMN_VALUE`; object elements expose attributes through an alias.
3. **SQL returns relational sets**: never assume element order is preserved in results without `ORDER BY`.
4. **Collection/element types** need proper privileges and scope; calling `TABLE()` from clients may require a SQL schema type or an Oracle-supported PL/SQL integration feature.
5. **Predicates/aggregations on elements** must evaluate indexes, element counts, pushdown behavior, and actual execution plans.

Example counting phone numbers:

```sql
SELECT c.customer_id,
       CARDINALITY(c.phones) AS phone_count
FROM   customer_phones c
ORDER BY c.customer_id;
```

When you frequently join and filter by `phone_number`, a relational table:

```text
CUSTOMER_PHONE_ROWS(
  CUSTOMER_ID   FK → CUSTOMERS,
  PHONE_NUMBER  VARCHAR2(...),
  POSITION_NO   NUMBER,
  PRIMARY KEY (CUSTOMER_ID, PHONE_NUMBER)
)
```

is often much easier to constrain, index, and query directly. **Being able to store a collection in a column** does not mean you should use it for every one-to-many relationship.

## 16. When to Choose Object Type, Nested Table, VARRAY, or Relational Tables

| Need | Option to Consider | Reason |
| --- | --- | --- |
| Business value with multiple fields, shared logic, used across SQL/PLSQL | **Object type** | Has type identity, attributes, and methods |
| Column holding a small structure like address, measurement point, coordinates | **Object column** | Models named nested values cleanly |
| Small list with a strict upper bound and logical order | **VARRAY** | Has `LIMIT`, preserves order in collection value |
| Variable-length element list stored as a collection column | **Nested table** | Persists via storage table and expands with `TABLE()` |
| Temporary dictionary/cache inside a PL/SQL procedure | **Associative array** | Key-based lookup without schema storage objects |
| Set of rows needing FKs, unique indexes, joins, and independent updates | **Relational child table** | Easy to query, constrain, and optimize in SQL |
| Flexibly structured fields integrating with JSON services | **JSON** (if supported by release) | Dedicated operators/functions and document model; differs from UDT objects |
| Simply grouping a few local variables in PL/SQL | **RECORD** | Simple, introduces no schema type dependencies |

### 16.1. Order Design Choice Example

Suppose a system stores `ORDERS` and `ORDER_ITEMS`:

**Option A — Nested table of objects:**

```text
ORDERS(order_id, lines ORDER_LINES_T)
  lines = [ORDER_LINE_T('A',2), ORDER_LINE_T('B',1)]
```

Fits when the application treats an order mostly as a single aggregate, line counts stay moderate, independent indexing on lines is minimal, and SQL UDT coupling is acceptable.

**Option B — Two relational tables:**

```text
ORDERS(order_id PK, customer_id, created_at, ...)
ORDER_ITEMS(order_id FK, line_no, sku, quantity,
            PRIMARY KEY(order_id, line_no))
```

Fits when querying by `SKU`, paginating line items, joining with inventory, indexing per-line status, performing batch updates, and integrating with standard ORMs. Most traditional relational OLTP systems fit Option B better unless there is a clear object-relational requirement.

### 16.2. Do Not Equate UDTs with JSON

An object type is a **schema-defined strong type**: attribute structure is declared at `CREATE TYPE`, and changes require dependency management. JSON is document-oriented, with schema enforced by different mechanisms; Oracle 19c mainly stores JSON in `VARCHAR2`, `CLOB`, or `BLOB` with JSON constraints, while newer Oracle releases add native JSON support. A JSON column does not become an object type just because it holds `{ "sku": "A" }`.

## 17. Impact of UDTs on Schemas, Dependencies, and Deployment

### 17.1. Types Are Named Schema Objects with Owners

When creating `APP.PRICE_ITEM_T`, Oracle stores the type definition in the data dictionary. Packages, tables, views, PL/SQL code, or other types can **depend** on it. If another user needs to use the type under their own privileges, a DBA grants privileges such as:

```sql
-- Illustrative privilege change in an admin environment.
GRANT EXECUTE ON price_item_t TO reporting_user;
```

`EXECUTE` on a type grants usage within the privilege scope, but **does not grant SELECT/INSERT/UPDATE** on tables using that type. In CDB/PDB setups, check the exact container and common/local grants where relevant.

### 17.2. Changing a Type Is a Contract Change

Suppose a type is used in a column across one million rows:

```text
PRICE_ITEM_T(sku, net_amount)
        │
        ├── PRICE_QUOTES.ITEM column
        ├── PACKAGE_ORDER_API parameter
        └── VIEW_ORDER_REPORT logic
```

Adding attributes, changing attribute types, or dropping methods can impact **stored object data, dependent objects, PL/SQL interfaces, JDBC apps, and upgrade plans**. Oracle supports **type evolution** via `ALTER TYPE` with rules around `CASCADE`, invalidation, dependent table upgrades, and other restrictions. Never run `CREATE OR REPLACE TYPE` casually as if editing an isolated source file.

Example command requiring DBA review—**never run casually as a lab**:

```sql
-- Illustrates type evolution concept, not an approved migration.
ALTER TYPE price_item_t
  ADD ATTRIBUTE (currency_code VARCHAR2(3 CHAR)) CASCADE;
```

In practice, expanding a constructor from two attributes to three can break existing code calling `price_item_t('A',100)` unless a compatible constructor exists. DBAs must inventory dependencies, write migration/rollback scripts, test against existing data, and coordinate client code updates prior to deployment.

### 17.3. Using Metadata to Inventory UDTs

These read-only queries can run in a lab schema or with appropriate dictionary privileges:

```sql
SELECT type_name, typecode
FROM   user_types
ORDER BY type_name;

SELECT type_name, attr_no, attr_name, attr_type_name
FROM   user_type_attrs
ORDER BY type_name, attr_no;

SELECT type_name, coll_type, upper_bound, elem_type_name
FROM   user_coll_types
ORDER BY type_name;

SELECT object_name, object_type, status
FROM   user_objects
WHERE  object_type IN ('TYPE', 'TYPE BODY')
ORDER BY object_name, object_type;
```

`UPPER_BOUND` in `user_coll_types` applies only to VARRAYs; nested tables have no finite VARRAY-style bound. For types in other schemas when authorized, query the corresponding `ALL_*`/`DBA_*` views. In a CDB, always verify the current PDB before interpreting results.

### 17.4. Exporting DDL and Checking Dependencies

```sql
-- Requires appropriate metadata privilege and an existing type.
SELECT DBMS_METADATA.GET_DDL('TYPE', 'PRICE_ITEM_T')
FROM   dual;

SELECT name, type, referenced_name, referenced_type
FROM   user_dependencies
WHERE  referenced_name = 'PRICE_ITEM_T'
ORDER BY name, type;
```

`DBMS_METADATA` exports type definitions, yet a full schema deployment script also requires **type bodies, dependent types, tables, indexes, constraints, grants, and creation order**. Never treat a standalone type-specification DDL export as a full application backup.

## 18. Java/JDBC and ORM Applications: Intentional Integration Choices

When using Oracle SQL object types and collection types, data maps to **STRUCT** and **ARRAY** representations in JDBC/Oracle drivers. A Java application may require custom object mapping code, Oracle type names, exact attribute ordering, JDBC connection unwrapping, and null handling.

```text
Oracle schema type                Java/JDBC layer
──────────────────                ───────────────
APP.ADDRESS_T                     STRUCT-like value / custom mapping
APP.PHONE_NUMBERS_T               ARRAY-like value / driver support
NUMBER/VARCHAR2 columns           JDBC scalar types / ORM mapping usually simpler
```

Do not assume JPA/Hibernate automatically maps Oracle nested tables, VARRAYs, or object tables like `@OneToMany` via a standard annotation alone. Some frameworks support custom user types/converters, yet exact behavior depends on **driver version, Hibernate version, DB release, and dialect**. Test round-trip insert/read, SQL null vs. empty collection, schema-qualified type names, and migrations in a production-like environment before adopting UDTs in application APIs.

### 18.1. API Contracts Can Break When Types Change

When `currency_code` is added to `PRICE_ITEM_T`, constructor attribute order and JDBC representations can shift. If an app still constructs objects with the old two attributes, runtime errors can occur. Always review type changes jointly with Java/backend teams, not only DBAs.

### 18.2. Questions to Answer Before Using UDTs in a Java Service

1. Is the UDT used in a **persistent column**, a stored procedure parameter, or only **transient batch passing**?
2. Does your driver/JPA stack support tested type mappings?
3. Do you frequently need to query/index individual collection elements?
4. How will type evolution be managed by Flyway/Liquibase/DDL migrations?
5. Are `NULL object`, `empty collection`, `NULL element`, and schema-qualified type names handled properly?

If most of the codebase uses relational ORMs and a collection merely models a one-to-many relationship, a child table with a foreign key is usually much simpler to maintain.

## 19. Optimization and Operational Limits

### 19.1. Indexing and Query Considerations

- Attributes in object columns can appear in SQL predicates, yet index creation and statistics must be evaluated against actual query workloads.
- Nested table storage may require explicit storage/index/constraint tuning; there is no guarantee element filters perform identically to an indexed foreign-key column.
- VARRAY fits small collections; searching/updating individual elements in large values can cost more than a relational child table.
- Type methods invoked over many rows can add **CPU/SQL context-switch overhead** or trigger extra SQL; avoid expensive methods in large scans without benchmarking.

### 19.2. Maintenance, Backup, and Migration

Object values and collection columns are covered by Oracle Database backups/restores and the data dictionary. However, migrating to another DBMS or ETL pipeline may require flattening UDTs into relational tables/columns, JSON, or intermediate structures.

When exporting schemas with Data Pump/`DBMS_METADATA`, verify **type creation order**, `EXECUTE` grants, type bodies, nested storage metadata, dependent tables, and target DB version. Never start by running `CREATE TABLE` statements that depend on types not yet created.

### 19.3. Data Design Decision Guide

```text
If you need:
  Strongly typed structured value + methods in DB
      └─ Consider OBJECT TYPE.

  Small bounded, ordered list
      └─ Consider VARRAY.

  Variable-length collection in a column, SQL unnest needed
      └─ Consider SQL NESTED TABLE.

  Temporary map/cache inside a procedure
      └─ Consider PL/SQL ASSOCIATIVE ARRAY.

  1:N relationship with FK/index/join and independent lifecycle
      └─ Prefer RELATIONAL CHILD TABLE.
```

## 20. Comprehensive Practice Lab in Your Lab Schema

> The steps below create and drop real objects; use only a lab schema you own. Statements carry implicit commits; never run in a production application schema. If you already ran earlier section examples, you may reuse matching types/tables and skip duplicate creates.

### Step 1 — Create Object Type, Nested Table, and VARRAY

```sql
CREATE TYPE lab_line_t AS OBJECT (
    sku VARCHAR2(30 CHAR),
    qty NUMBER
);
/

CREATE TYPE lab_lines_t AS TABLE OF lab_line_t;
/

CREATE TYPE lab_scores_t AS VARRAY(3) OF NUMBER;
/
```

### Step 2 — Create a Table with Both Nested Table and VARRAY Columns

```sql
CREATE TABLE lab_orders_udt (
    order_id NUMBER PRIMARY KEY,
    lines    lab_lines_t,
    scores   lab_scores_t
)
NESTED TABLE lines STORE AS lab_orders_lines_nt;
```

### Step 3 — Populate Data Using Constructors

```sql
INSERT INTO lab_orders_udt (order_id, lines, scores)
VALUES (
    1,
    lab_lines_t(lab_line_t('SKU-A', 2), lab_line_t('SKU-B', 1)),
    lab_scores_t(10, 20, 30)
);

INSERT INTO lab_orders_udt (order_id, lines, scores)
VALUES (2, lab_lines_t(), lab_scores_t());

COMMIT;
```

### Step 4 — Query Elements and Inspect Collections

```sql
SELECT o.order_id, l.sku, l.qty
FROM   lab_orders_udt o,
       TABLE(o.lines) l
ORDER BY o.order_id, l.sku;

SELECT o.order_id,
       CARDINALITY(o.lines) AS line_count,
       CARDINALITY(o.scores) AS score_count
FROM   lab_orders_udt o
ORDER BY o.order_id;
```

Observe that `order_id=2` has empty collections, so `TABLE(o.lines)` emits no row for that order while `CARDINALITY` returns `0`.

### Step 5 — Inspect Real Metadata and DDL

```sql
SELECT type_name, typecode
FROM   user_types
WHERE  type_name LIKE 'LAB_%'
ORDER BY type_name;

SELECT type_name, coll_type, upper_bound
FROM   user_coll_types
WHERE  type_name LIKE 'LAB_%'
ORDER BY type_name;

SELECT DBMS_METADATA.GET_DDL('TABLE', 'LAB_ORDERS_UDT')
FROM   dual;
```

In SQL*Plus/SQLcl, set `SET LONG` large enough to view the full DDL. Check how `NESTED TABLE ... STORE AS` appears in the table DDL under your transform profile. If your client truncates CLOB output, do not assume the DDL is missing the storage clause.

### Step 6 — Clean Up the Lab When Done

`DROP` statements delete objects permanently and cannot be undone with `ROLLBACK`, so run them only after confirming all objects were created for this lab:

```sql
DROP TABLE lab_orders_udt PURGE;
DROP TYPE lab_scores_t;
DROP TYPE lab_lines_t;
DROP TYPE lab_line_t;
```

The cleanup order—**table before types**, and outer collection type before element type—reflects dependencies. Never drop with `FORCE` while other objects still depend on a type without checking dependencies first.

## 21. Common Errors and How to Reason About Them

| Symptom / Error | Typical Cause | Resolution |
| --- | --- | --- |
| `PLS-00306` on constructor call | Wrong argument count/types, or type attributes changed | Check `USER_TYPE_ATTRS` and constructor signature |
| `ORA-06531: Reference to uninitialized collection` | Nested table/VARRAY never called constructor | Initialize `my_type()` before `COUNT`/`EXTEND` |
| `ORA-06532` / `ORA-06533` on collection access | Subscript out of bounds or element does not exist | Check `COUNT`, `LIMIT`, `FIRST`, `NEXT`, `EXISTS` |
| `NO_DATA_FOUND` reading associative array | Key has no assigned element | `IF l_map.EXISTS(key) THEN ...` |
| `ORA-00902: invalid datatype` | Using a PL/SQL-only type or invalid type kind in SQL DDL | Create a SQL schema type with `CREATE TYPE` for SQL columns |
| `ORA-02303` when altering/dropping a type | Type still has dependent tables/other types | Inventory dependencies and use proper migration/evolution |
| `TABLE()` query omits parent row with empty collection | Collection expansion emits no element rows | Use an outer join or aggregate if parent rows must stay |
| Nested table query order differs from insert order | No guaranteed row order in SQL/nested storage | Store `position_no` and use an explicit `ORDER BY` |
| Java/JDBC fails to map UDT | Missing schema type mapping, driver support, or attribute mismatch | Verify Oracle JDBC STRUCT/ARRAY, type name, and constructor |
| Table builds, yet app cannot call constructor | Missing `EXECUTE` on type or wrong schema/PDB | Check grants and current container |
| `CREATE OR REPLACE TYPE` invalidates packages | Dependent object incompatible with new type | Inventory dependencies, versioned migration, recompile, and test |

Exact errors can vary by code path and release; use this table to **locate the root cause**, not as a replacement for reading full error messages and stack traces.

## 22. Self-Check Questions

**Question 1.** How does `CREATE TYPE address_t AS OBJECT (...)` differ from PL/SQL `TYPE address_rec IS RECORD (...)` in scope and SQL usability?

**Question 2.** When `l_phones phone_numbers_t;` is uninitialized, does `l_phones.COUNT` return `0` or raise an error?

**Question 3.** Are `phone_numbers_t()` and `phone_numbers_t(NULL)` identical?

**Question 4.** Why does a nested table have `COUNT=2` and `LAST=3` after `l_nested.DELETE(2)`? How should you iterate it?

**Question 5.** Can a VARRAY declared as `VARRAY(4)` hold five elements? Is `SELECT ... FROM TABLE(varray_column)` guaranteed to return rows in insertion order?

**Question 6.** Can an associative array `INDEX BY VARCHAR2(30)` be used directly as a table column type? Why or why not?

**Question 7.** How does querying a collection of `VARCHAR2` differ from querying a collection of object types in `TABLE()` syntax?

**Question 8.** A schema has `ORDER_LINES_T` depending on `ORDER_LINE_T`. To drop both types, in what order must dependencies be handled?

**Question 9.** If you want to search individual phone numbers across millions of customers using an index and enforce uniqueness per customer, which model should you consider?

**Question 10.** An attribute is added to `PRICE_ITEM_T`. What else must be verified besides the `ALTER TYPE` statement itself?

<details>
<summary>Suggested Answers</summary>

1. `ADDRESS_T` is a SQL schema object type usable as a SQL column type; a local/package PL/SQL `RECORD` is usable only within supported PL/SQL scopes.
2. It raises `COLLECTION_IS_NULL`/`ORA-06531` when uninitialized; it does not default to `0`.
3. Different: the empty constructor creates a **0-element** collection; the constructor with `NULL` creates a **1-element collection whose element is NULL**.
4. A nested table becomes sparse after `DELETE`. `COUNT` counts existing elements; `LAST` is the highest remaining subscript. Iterate with `FIRST` and `NEXT`.
5. Cannot exceed 4; SQL rowsets have no guaranteed output order without an explicit `ORDER BY`, even though VARRAY has logical order.
6. No. Associative arrays are PL/SQL runtime types, not SQL schema types for persistent columns.
7. Scalar elements use `COLUMN_VALUE`; object elements expose `alias.attribute` such as `l.sku`.
8. Drop the dependent collection type first (`ORDER_LINES_T`), then the element type (`ORDER_LINE_T`), after dropping tables/objects that use them.
9. A relational child table with foreign key and unique key/index is usually much more suitable.
10. Dependent tables/types/packages/views, constructors, data upgrades, grants, app/JDBC mappings, and migration/rollback tests.

</details>

## 23. Official Oracle Documentation

1. [Oracle Database 19c SQL Language Reference — `CREATE TYPE`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TYPE.html): SQL object type, nested table, and VARRAY syntax.
2. [Oracle Database 19c SQL Language Reference — `CREATE TYPE BODY`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TYPE-BODY.html): declaring and implementing member/static methods.
3. [Oracle Database 19c Object-Relational Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/adobj/): object attributes, constructors, object tables, `REF`, inheritance, and storage.
4. [Oracle Database 19c PL/SQL Language Reference — Collections and Records](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-collections-and-records.html): nested tables, VARRAYs, associative arrays, records, and collection methods.
5. [Oracle Database 19c SQL Language Reference — `TABLE` collection expression](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): unnesting collections into relational rowsets and join semantics.
6. [Oracle Database 19c SQL Language Reference — `ALTER TYPE`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TYPE.html): type evolution, dependencies, and upgrade behavior.
7. [Oracle Database 19c PL/SQL Language Reference — Bulk SQL and Bulk Binding](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-optimization-and-tuning.html): `BULK COLLECT`, `FORALL`, `LIMIT`, and array processing.
8. [Oracle Database 19c Database Reference — Data Dictionary](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/about-static-data-dictionary-views.html): `USER_TYPES`, `USER_TYPE_ATTRS`, `USER_COLL_TYPES`, `USER_DEPENDENCIES`.
9. [Oracle Database 19c JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): working with Oracle object/collection types in JDBC and Java applications.

**Key takeaway:** Oracle offers **object types** for multi-attribute values with methods, **nested tables/VARRAYs** for collections usable in SQL when declared as schema types, and **associative arrays** for flexible maps in PL/SQL. Every choice must evaluate **type lifecycle, element ordering, null semantics, privileges/schemas, queryability, dependencies, and application tooling**; adopt composite types in schemas only when their benefits outweigh integration and maintenance costs.
