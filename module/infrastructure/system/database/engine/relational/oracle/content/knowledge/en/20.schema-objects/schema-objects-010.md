# Object Types, Nested Tables, VARRAYs, and Relationships to Standard Tables in Oracle

## 1. Extending the Relational Model with Object Types

In the standard relational model, tables are built from scalar columns such as `NUMBER`, `VARCHAR2`, `DATE`, and rows. When data has nested structure—such as a multi-attribute address, a list of phone numbers, or an order's line items—Oracle also provides object-relational features:

- **Object type:** defines a data type with multiple attributes, which can hold scalar types, other object types, or collections.
- **Object table:** a table where each row is an instance of an object type.
- **Object column:** a column in a standard table whose data type is an object type.
- **Nested table:** a collection with no declared fixed upper bound; Oracle stores elements in a separate storage table linked to the parent row.
- **VARRAY:** a collection with a fixed maximum element limit that preserves element order and is stored as a collection value of the row.

For example, a customer has a name, address, and list of phone numbers. You can model the address as an object type, the phone list as a VARRAY, and wrap both in a customer profile object type:

```sql
CREATE TYPE address_t AS OBJECT (
    street       VARCHAR2(100),
    city         VARCHAR2(50),
    postal_code  VARCHAR2(20)
);
/

CREATE TYPE phone_list_t AS VARRAY(5) OF VARCHAR2(20);
/

CREATE TYPE customer_profile_t AS OBJECT (
    full_name  VARCHAR2(100),
    address    address_t,
    phones     phone_list_t
);
/
```

Then `CUSTOMER_PROFILE_T` can serve as the type of a column in a relational table:

```sql
CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    profile     customer_profile_t
);
```

This lesson belongs to the **Schema Objects** chapter, focusing on defining and using object types, nested tables, and VARRAYs, querying collections with `TABLE()`, and how the object-relational model relates to standard relational tables. The goal is understanding what structures Oracle supports, how data is stored and accessed, and how to choose the right model for business and application needs.

## 2. What Is an Object Type?

An object type is a user-defined schema-level data type. It groups multiple attributes into a structured value. Attributes can be:

- Scalar types such as `NUMBER`, `VARCHAR2`, `DATE`, `TIMESTAMP`.
- Another object type.
- A collection type such as a nested table or VARRAY.
- Other data types permitted by Oracle as attributes.

Object types can be used in table columns, object tables, collections, and compatible PL/SQL variables.

### 2.1. Defining a Simple Object Type

```sql
CREATE TYPE person_t AS OBJECT (
    person_id  NUMBER,
    full_name  VARCHAR2(100),
    birth_date DATE
);
/
```

`PERSON_T` describes a value with three attributes. `CREATE TYPE` creates the type at schema scope; the `/` on its own line submits the PL/SQL/DDL buffer in SQL*Plus or SQLcl and is not part of the SQL statement itself.

### 2.2. Creating Nested Object Types

One object type can be used as an attribute of another object type:

```sql
CREATE TYPE address_t AS OBJECT (
    street       VARCHAR2(100),
    city         VARCHAR2(50),
    postal_code  VARCHAR2(20)
);
/

CREATE TYPE customer_t AS OBJECT (
    customer_id NUMBER,
    full_name   VARCHAR2(100),
    address     address_t
);
/
```

A `CUSTOMER_T` value contains an `ADDRESS_T` value. This structure fits when an address is part of a customer profile and is typically read or updated together with the profile.

### 2.3. Object Type Constructors

Oracle automatically provides a default constructor for an object type, with parameters matching the order of its attributes:

```sql
SELECT customer_t(
           501,
           'An Nguyen',
           address_t('12 Nguyen Hue', 'Ho Chi Minh City', '700000')
       ) AS customer_value
FROM dual;
```

`CUSTOMER_T(...)` constructs an instance of the customer type; `ADDRESS_T(...)` constructs the address instance passed as the third attribute.

The default constructor is tied to the type and attribute ordering. When a type has many attributes, write the argument list clearly and verify attribute order. Custom constructor methods can be defined when complex initialization rules are required.

### 2.4. Accessing Attributes

On an object column:

```sql
SELECT c.customer_id,
       c.profile.full_name,
       c.profile.address.city
FROM customers c;
```

Dot notation traverses from the object column to an attribute, and onward into nested objects inside.

If an object or nested attribute is NULL, the corresponding attribute access expression evaluates to NULL. Applications must define how a NULL object differs from an instantiated object with a NULL attribute.

## 3. Object Types Can Contain Methods

An object type does not hold only data; it can also define member methods to operate on instances. Example:

```sql
CREATE TYPE person_t AS OBJECT (
    person_id NUMBER,
    full_name VARCHAR2(100),
    MEMBER FUNCTION display_name RETURN VARCHAR2
);
/
```

The type body defines how the method behaves:

```sql
CREATE TYPE BODY person_t AS
    MEMBER FUNCTION display_name RETURN VARCHAR2 IS
    BEGIN
        RETURN full_name;
    END;
END;
/
```

Given an object `p`, the method can be invoked:

```sql
SELECT p.display_name()
FROM person_obj_table p;
```

Methods are invoked per instance. Inside a member method, `SELF` represents the current instance; member methods that do not modify the instance can use `MEMBER`, whereas methods that mutate the instance follow specific declaration rules.

In application design, avoid stuffing all business logic into object types merely because Oracle supports methods. Weigh maintainability, testability, type execute privileges, and Oracle lock-in.

## 4. Object Tables: Each Row Is an Object Instance

An object table is a table built directly on an object type. Instead of listing individual columns in `CREATE TABLE`, you specify the object type:

```sql
CREATE TYPE person_t AS OBJECT (
    person_id NUMBER,
    full_name VARCHAR2(100),
    birth_date DATE
);
/

CREATE TABLE person_obj_table OF person_t (
    CONSTRAINT pk_person_obj PRIMARY KEY (person_id)
);
```

Each row of `PERSON_OBJ_TABLE` is an instance of `PERSON_T`. Object attributes appear as columns of the object table when queried.

### 4.1. Inserting into an Object Table

```sql
INSERT INTO person_obj_table
VALUES (
    person_t(1, 'An Nguyen', DATE '1995-04-12')
);

INSERT INTO person_obj_table
VALUES (
    person_t(2, 'Binh Tran', DATE '1992-09-30')
);
```

The `PERSON_T(...)` constructor creates the object inserted into the table.

### 4.2. Selecting Attributes from an Object Table

```sql
SELECT p.person_id,
       p.full_name,
       p.birth_date
FROM person_obj_table p
ORDER BY p.person_id;
```

Attributes can be used in `WHERE`, `ORDER BY`, JOINs, and other SQL expressions per data type rules.

### 4.3. Retrieving the Whole Object with VALUE

```sql
SELECT VALUE(p)
FROM person_obj_table p;
```

`VALUE(alias)` returns the full object instance of a row in an object table. This differs from projecting individual attributes separately.

### 4.4. Updating Object Table Attributes

```sql
UPDATE person_obj_table p
SET p.full_name = 'An Nguyen Updated'
WHERE p.person_id = 1;
```

Object tables support standard DML. Constraints declared on the object table or its attributes are enforced per Oracle rules.

## 5. Object Columns: Relational Tables Holding an Object Value

You do not need an object table to use an object type. A standard relational table can contain an object column:

```sql
CREATE TYPE address_t AS OBJECT (
    street      VARCHAR2(100),
    city        VARCHAR2(50),
    postal_code VARCHAR2(20)
);
/

CREATE TYPE customer_profile_t AS OBJECT (
    full_name VARCHAR2(100),
    address   address_t
);
/

CREATE TABLE customers_rel (
    customer_id NUMBER PRIMARY KEY,
    profile     customer_profile_t,
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP
);
```

`CUSTOMERS_REL` remains a relational table: `CUSTOMER_ID` and `CREATED_AT` are ordinary columns; `PROFILE` is an object-typed column.

### 5.1. Inserting an Object Column

```sql
INSERT INTO customers_rel (customer_id, profile)
VALUES (
    501,
    customer_profile_t(
        'An Nguyen',
        address_t('12 Nguyen Hue', 'Ho Chi Minh City', '700000')
    )
);
```

### 5.2. Querying Attributes

```sql
SELECT c.customer_id,
       c.profile.full_name AS customer_name,
       c.profile.address.street AS street,
       c.profile.address.city AS city
FROM customers_rel c;
```

### 5.3. Updating Object Attributes

You can update an individual attribute of an object column:

```sql
UPDATE customers_rel c
SET c.profile.address.city = 'Thu Duc'
WHERE c.customer_id = 501;
```

To replace the entire object, assign a new instance:

```sql
UPDATE customers_rel c
SET c.profile = customer_profile_t(
                    'An Nguyen',
                    address_t('12 Nguyen Hue', 'Thu Duc', '700000')
                )
WHERE c.customer_id = 501;
```

Object columns are helpful when a substructure is treated as a structured attribute of the parent row. However, if you frequently filter, update, constrain, and report on individual sub-attributes independently, standard relational columns are often easier to manage.

## 6. Collection Types in Oracle

A collection is a value holding multiple elements of the same type. Oracle provides two common SQL collection types:

- Nested table.
- VARRAY (variable-size array).

A collection can hold scalars or object types. Example:

```sql
CREATE TYPE phone_list_t AS VARRAY(5) OF VARCHAR2(20);
/

CREATE TYPE order_line_t AS OBJECT (
    product_id NUMBER,
    quantity   NUMBER,
    unit_price NUMBER(12, 2)
);
/

CREATE TYPE order_line_nt AS TABLE OF order_line_t;
/
```

`PHONE_LIST_T` is a VARRAY of up to five phone strings. `ORDER_LINE_NT` is a nested table holding `ORDER_LINE_T` objects.

### 6.1. Collection Constructors

Collection constructors use the type name and an element list:

```sql
phone_list_t('0901000001', '0902000002')
```

Nested table:

```sql
order_line_nt(
    order_line_t(1001, 2, 15000),
    order_line_t(1002, 1, 25000)
)
```

Argument order in object constructors must match the attribute order in the type definition.

### 6.2. Empty Collections vs. NULL Collections

These two states differ:

- **NULL collection (atomically null):** uninitialized, with no collection instance.
- **Empty collection:** initialized collection containing 0 elements.

Example:

```sql
phone_list_t()  -- Initialized VARRAY, currently holding 0 elements
```

A collection column can accept NULL if the schema allows it:

```sql
INSERT INTO customer_contacts (customer_id, phones)
VALUES (501, NULL);
```

Or accept an empty collection:

```sql
INSERT INTO customer_contacts (customer_id, phones)
VALUES (502, phone_list_t());
```

Applications must define whether NULL means "unknown/uninitialized" while an empty collection means "known list currently has zero elements." Do not treat the two states as identical automatically.

## 7. Nested Tables: Collections Without a Fixed Declared Bound

A nested table is a collection type declared with `TABLE OF`:

```sql
CREATE TYPE order_line_t AS OBJECT (
    product_id NUMBER,
    quantity   NUMBER,
    unit_price NUMBER(12, 2)
);
/

CREATE TYPE order_line_nt AS TABLE OF order_line_t;
/
```

Nested tables do not declare a maximum element limit like VARRAYs. Oracle stores nested table elements in a separate storage table linked to the parent row via internal metadata.

### 7.1. Using a Nested Table as a Column

```sql
CREATE TABLE orders_nested (
    order_id    NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_lines order_line_nt
)
NESTED TABLE order_lines STORE AS order_lines_store;
```

`ORDER_LINES` is a collection column. `ORDER_LINES_STORE` is the storage table Oracle uses to store nested table elements. The storage table name is specified explicitly for easier inspection and administration.

### 7.2. Inserting a Nested Table

```sql
INSERT INTO orders_nested (
    order_id,
    customer_id,
    order_lines
)
VALUES (
    100,
    501,
    order_line_nt(
        order_line_t(2001, 2, 15000),
        order_line_t(2002, 1, 25000)
    )
);
```

The parent row contains a collection of two line-item objects.

### 7.3. Querying a Nested Table with TABLE()

To turn a collection into queryable rows, use a collection expression with the `TABLE()` operator:

```sql
SELECT o.order_id,
       line.product_id,
       line.quantity,
       line.unit_price
FROM orders_nested o,
     TABLE(o.order_lines) line
ORDER BY o.order_id, line.product_id;
```

`TABLE(o.order_lines)` unnests the collection into a row source. Each `ORDER_LINE_T` element appears as a row with attributes `PRODUCT_ID`, `QUANTITY`, and `UNIT_PRICE`.

If the collection is NULL or empty, unnesting produces no element rows. A cross join like the query above will not return parent rows without elements; to preserve parent rows, use an outer expansion appropriate for your Oracle version, such as `OUTER APPLY` on supported versions.

### 7.4. Querying Elements and Filtering

```sql
SELECT o.order_id,
       line.product_id,
       line.quantity
FROM orders_nested o,
     TABLE(o.order_lines) line
WHERE line.quantity >= 2;
```

You can filter on object element attributes just like filtering columns of a relational table.

### 7.5. DML on a Nested Table

Collections can be manipulated using collection table expressions:

```sql
INSERT INTO TABLE (
    SELECT o.order_lines
    FROM orders_nested o
    WHERE o.order_id = 100
)
VALUES (
    order_line_t(2003, 3, 12000)
);
```

This appends an element to order 100's collection.

Delete an element:

```sql
DELETE FROM TABLE (
    SELECT o.order_lines
    FROM orders_nested o
    WHERE o.order_id = 100
) line
WHERE line.product_id = 2002;
```

Update an element attribute:

```sql
UPDATE TABLE (
    SELECT o.order_lines
    FROM orders_nested o
    WHERE o.order_id = 100
) line
SET line.quantity = line.quantity + 1
WHERE line.product_id = 2001;
```

These DML statements modify the collection belonging to the parent row selected in the subquery. Ensure the subquery selects exactly one parent row and verify affected element counts.

### 7.6. Nested Tables Have No Inherent Ordering

A nested table is a collection without guaranteed element ordering. When querying via `TABLE()`, never rely on physical order or insertion order to infer element positions.

When sorted output is needed:

```sql
SELECT o.order_id,
       line.product_id,
       line.quantity
FROM orders_nested o,
     TABLE(o.order_lines) line
ORDER BY o.order_id, line.product_id;
```

If order is business data, store an attribute like `LINE_NO` inside the object or use a relational child table with a `LINE_NO` column.

## 8. VARRAY: Bounded, Ordered Collections

A VARRAY is declared with `VARRAY(max_size) OF element_type`:

```sql
CREATE TYPE phone_list_t AS VARRAY(5) OF VARCHAR2(20);
/
```

VARRAY characteristics:

- Has a maximum bound declared in the type (5 elements in this example).
- Preserves element order within the collection.
- Elements are indexed in PL/SQL collection semantics.
- Can hold scalar or object types.

### 8.1. Using a VARRAY as a Column

```sql
CREATE TABLE customer_contacts (
    customer_id NUMBER PRIMARY KEY,
    phones      phone_list_t
);
```

### 8.2. Inserting a VARRAY

```sql
INSERT INTO customer_contacts (customer_id, phones)
VALUES (
    501,
    phone_list_t('0901000001', '0902000002', '0903000003')
);
```

The phone list holds three elements in the supplied order.

### 8.3. Querying VARRAY Elements with TABLE()

```sql
SELECT c.customer_id,
       p.column_value AS phone_number
FROM customer_contacts c,
     TABLE(c.phones) p
ORDER BY c.customer_id, p.column_value;
```

For scalar-element collections, `COLUMN_VALUE` is the pseudocolumn used to access the unnested element value. If positional order must be displayed, access the collection by index in PL/SQL or store position as an explicit attribute; never rely on SQL result order without `ORDER BY`.

### 8.4. Exceeding VARRAY Bounds

With `VARRAY(5)`, the collection cannot hold more than five elements. Attempting to construct or extend beyond the bound raises a collection/limit error. Choose the size based on real business requirements—do not set it too small if lists can grow.

### 8.5. VARRAY Storage

A VARRAY is stored as a collection value of the parent row. Depending on size and declaration, Oracle can store it using default inline/out-of-line mechanics or explicitly as a LOB:

```sql
CREATE TABLE customer_contacts_lob (
    customer_id NUMBER PRIMARY KEY,
    phones      phone_list_t
)
VARRAY phones STORE AS LOB;
```

`STORE AS LOB` can fit large collections; for small collections, evaluate overhead and access patterns. Consult Oracle documentation for your release and application storage profile before choosing.

## 9. Comparing Nested Tables and VARRAYs

| Criterion | Nested Table | VARRAY |
|---|---|---|
| Element limit declared in type | No fixed limit like VARRAY | Has maximum upper bound |
| Element ordering | Not guaranteed | Preserved within the collection |
| Storage | Elements stored in a separate storage table | Collection value stored with parent row; can use LOB storage |
| Duplicate elements | Allowed | Allowed |
| Querying elements | `TABLE(collection_column)` | `TABLE(collection_column)` |
| Positional access | Do not rely on stable positions | Has indexed element semantics |
| Best suited for | Child lists that can grow large and need per-element unnesting/DML | Small, bounded, meaningfully ordered lists |
| Modeling feel | Close to a child row set nested under a parent row | Close to an ordered array attached to a parent row |

### 9.1. When to Use a Nested Table

Choose a nested table when:

- Element counts can vary widely without a known small upper bound.
- Elements may be queried or manipulated individually via `TABLE()`.
- The collection belongs to the parent row value while requiring per-element operations.
- Element ordering does not need to be guaranteed natively.

### 9.2. When to Use a VARRAY

Choose a VARRAY when:

- Element counts have a natural small upper limit, such as at most five priority contact numbers.
- Element order is meaningful.
- The application typically reads and writes the whole collection as a single value.
- Individual elements do not need to be modeled as independent relational entities.

If lists can grow unboundedly or each element needs its own status, constraints, privileges, and lifecycle, a relational child table is usually clearer.

## 10. Object Tables vs. Standard Relational Tables

An object table is still a table in the database, but each row is an instance of an object type. A standard relational table defines each column directly in DDL.

### 10.1. Relational Table

```sql
CREATE TABLE customers_rel (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(100) NOT NULL,
    street      VARCHAR2(100),
    city        VARCHAR2(50),
    postal_code VARCHAR2(20)
);
```

### 10.2. Object Table

```sql
CREATE TYPE address_t AS OBJECT (
    street      VARCHAR2(100),
    city        VARCHAR2(50),
    postal_code VARCHAR2(20)
);
/

CREATE TYPE customer_t AS OBJECT (
    customer_id NUMBER,
    full_name   VARCHAR2(100),
    address     address_t
);
/

CREATE TABLE customers_obj OF customer_t (
    CONSTRAINT pk_customers_obj PRIMARY KEY (customer_id)
);
```

Both approaches can represent similar information, but querying, type management, and application integration differ.

| Criterion | Relational Table | Object Table |
|---|---|---|
| Row definition | Scalar/SQL-typed columns | Instance of an object type |
| Attribute access | `c.full_name`, `c.city` | `c.full_name`, `c.address.city` |
| Type reuse | Domain/type reuse handled differently | Object type reused directly across tables/columns |
| Object identity/REF | Typically uses PK/FK | Can use OID and REF |
| ORM/JDBC integration | Usually more direct | Requires handling object/collection types via driver |
| Cross-DBMS portability | Typically higher with standard relational SQL | Depends on Oracle object-relational features |
| Best suited for | Row/column business data with clear relationships | Reusable structured object data requiring object semantics |

Do not conclude that object tables replace all relational tables. Object tables are one modeling option in Oracle, while the relational model remains best suited for most business data.

## 11. Object Columns vs. Standard Relational Columns

A relational table can combine both scalar columns and object columns:

```sql
CREATE TABLE customer_records (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(100) NOT NULL,
    address     address_t,
    created_at  TIMESTAMP
);
```

Here:

- `CUSTOMER_ID`, `FULL_NAME`, and `CREATED_AT` are ordinary scalar columns.
- `ADDRESS` is an object column.

An object column can be chosen when an address is treated as a reusable structure, such as sharing `ADDRESS_T` for both shipping address and billing address.

However, if reports frequently filter by `CITY` or `POSTAL_CODE`, or need independent indexes and constraints per attribute, consider a standard relational column layout or adding appropriate index/constraint structures. Do not assume nesting objects automatically gives sub-attributes the exact same manageability as directly declared scalar columns in all contexts.

## 12. Nested Tables vs. Relational Child Tables

A list of order lines can be modeled using a nested table:

```sql
CREATE TABLE orders_nested (
    order_id NUMBER PRIMARY KEY,
    order_lines order_line_nt
)
NESTED TABLE order_lines STORE AS order_lines_store;
```

Or using two relational tables:

```sql
CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL
);

CREATE TABLE order_lines (
    order_id NUMBER NOT NULL,
    line_no NUMBER NOT NULL,
    product_id NUMBER NOT NULL,
    quantity NUMBER NOT NULL,
    unit_price NUMBER(12, 2) NOT NULL,
    CONSTRAINT pk_order_lines PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
);
```

### 12.1. Modeling Differences

With a relational child table:

- Each order line is an independent row.
- Foreign key `ORDER_ID` links lines to orders.
- `LINE_NO` expresses business sequence order.
- PK, FK, UNIQUE, and CHECK constraints can be declared directly on lines.
- Easy to JOIN with products, inventory, taxes, and other business tables.

With a nested table:

- The collection is attached as an attribute of the parent row.
- Oracle stores elements in a separate storage table.
- Elements are queried via `TABLE(order_lines)`.
- The collection is managed as a nested value of the parent row.
- Element order is not guaranteed; if order matters, store a position attribute.

### 12.2. Operational Comparison

Fetching order lines via a child table:

```sql
SELECT o.order_id,
       l.line_no,
       l.product_id,
       l.quantity
FROM orders o
JOIN order_lines l
  ON l.order_id = o.order_id;
```

Fetching order lines via a nested table:

```sql
SELECT o.order_id,
       l.product_id,
       l.quantity
FROM orders_nested o,
     TABLE(o.order_lines) l;
```

Both can return relational-style rows to queries. However, the child-table model is typically easier to integrate with complex JOINs, constraints, and BI tools.

### 12.3. Choose a Relational Child Table When

- Child items are business entities with their own lifecycle.
- Foreign keys to multiple other tables are needed.
- Uniqueness or check constraints are needed on individual child rows.
- Independent updates, privileges, auditing, or reporting per line are required.
- Broad compatibility with ORMs, ETL, BI, and external systems is desired.

Choose a nested table when the collection is genuinely part of the parent row's value and storing/accessing it as a collection makes the model cleaner.

## 13. REF and Relationships Between Object Tables

The object-relational model also includes the `REF` type, a reference to an object row in an object table. REF is not like an ordinary NUMBER/VARCHAR2 foreign key; it references the object identity of a row.

### 13.1. Create an Object Table

```sql
CREATE TYPE customer_t AS OBJECT (
    customer_id NUMBER,
    full_name   VARCHAR2(100)
);
/

CREATE TABLE customers_obj OF customer_t (
    CONSTRAINT pk_customers_obj PRIMARY KEY (customer_id)
)
OBJECT IDENTIFIER IS PRIMARY KEY;
```

`OBJECT IDENTIFIER IS PRIMARY KEY` instructs Oracle to use the primary key as the object identifier. This is helpful when stable REFs based on a chosen business/technical key are desired.

### 13.2. Table Containing a REF

```sql
CREATE TABLE orders_with_ref (
    order_id NUMBER PRIMARY KEY,
    customer_ref REF customer_t SCOPE IS customers_obj
);
```

`SCOPE IS customers_obj` constrains the REF to point into object table `CUSTOMERS_OBJ`.

### 13.3. Inserting a REF

```sql
INSERT INTO customers_obj
VALUES (customer_t(501, 'An Nguyen'));

INSERT INTO orders_with_ref (order_id, customer_ref)
SELECT 1001, REF(c)
FROM customers_obj c
WHERE c.customer_id = 501;
```

`REF(c)` constructs a reference to object row `c`.

### 13.4. Dereferencing a REF

```sql
SELECT o.order_id,
       DEREF(o.customer_ref).customer_id AS customer_id,
       DEREF(o.customer_ref).full_name AS customer_name
FROM orders_with_ref o;
```

`DEREF` retrieves the referenced object so its attributes can be accessed. In most standard relational applications, scalar foreign keys and JOINs are easier to understand and integrate than REF. REF fits when applications genuinely require object identity/reference semantics.

### 13.5. REF Does Not Replace Every Foreign Key

REF is tied to object tables/object identities and follows its own management rules. If data is primarily queried through PK/FK relationships, standard relational tables remain simpler to deploy and more portable.

## 14. Converting Relational Data into a Collection

You can construct a nested table collection from a query using `CAST(MULTISET(...))`.

Suppose we have:

```sql
CREATE TYPE order_line_t AS OBJECT (
    product_id NUMBER,
    quantity   NUMBER,
    unit_price NUMBER(12, 2)
);
/

CREATE TYPE order_line_nt AS TABLE OF order_line_t;
/
```

Relational rows can be gathered into a collection:

```sql
SELECT CAST(
           MULTISET(
               SELECT order_line_t(
                          l.product_id,
                          l.quantity,
                          l.unit_price
                      )
               FROM order_lines l
               WHERE l.order_id = 100
           )
           AS order_line_nt
       ) AS lines
FROM dual;
```

`MULTISET` turns a multi-row query result into a collection; `CAST` specifies the exact collection type returned by the expression. This technique is useful when feeding relational data into an object-relational API or passing a set of elements as a collection.

### 14.1. Updating a Collection from a Relational Table

You can assign a collection built from a child table to a collection column:

```sql
UPDATE orders_nested o
SET order_lines = CAST(
    MULTISET(
        SELECT order_line_t(
                   l.product_id,
                   l.quantity,
                   l.unit_price
               )
        FROM order_lines l
        WHERE l.order_id = o.order_id
    )
    AS order_line_nt
)
WHERE o.order_id = 100;
```

The subquery builds the collection from child rows matching `ORDER_ID`. If no child rows exist, MULTISET yields an empty collection based on the query result, not a dummy line-item row.

When synchronizing between the two models, designate one side as the single source of truth. Never maintain the same line-item list independently in both a child table and a nested table without a well-defined synchronization process.

## 15. Collection Methods in PL/SQL

In PL/SQL, collections provide methods to inspect and manipulate elements. Common methods:

| Method | Meaning |
|---|---|
| `COUNT` | Current number of elements |
| `FIRST` | First index containing an element |
| `LAST` | Last index containing an element |
| `EXISTS(i)` | Checks whether an element exists at index i |
| `PRIOR(i)` | Index preceding i |
| `NEXT(i)` | Index following i |
| `LIMIT` | Maximum capacity; useful for VARRAYs |
| `EXTEND` | Appends space/elements at the end of a collection |
| `TRIM` | Removes trailing elements |
| `DELETE` | Removes elements; applicable to nested tables, not for creating arbitrary gaps in VARRAYs |

PL/SQL example with VARRAY:

```sql
DECLARE
    v_phones phone_list_t :=
        phone_list_t('0901000001', '0902000002');
BEGIN
    DBMS_OUTPUT.PUT_LINE('COUNT=' || v_phones.COUNT);
    DBMS_OUTPUT.PUT_LINE('LIMIT=' || v_phones.LIMIT);
    DBMS_OUTPUT.PUT_LINE('FIRST=' || v_phones.FIRST);

    v_phones.EXTEND;
    v_phones(3) := '0903000003';

    DBMS_OUTPUT.PUT_LINE('NEW COUNT=' || v_phones.COUNT);
END;
/
```

VARRAYs have dense sequential subscripts and a fixed capacity. Nested tables in PL/SQL can become sparse after DELETE; therefore, when iterating over nested tables, use FIRST/NEXT rather than assuming `1 .. COUNT` are always valid subscripts.

### 15.1. NULL Collections vs. Empty Collections in PL/SQL

```sql
DECLARE
    v_empty phone_list_t := phone_list_t();
    v_null  phone_list_t;
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_empty.COUNT); -- 0

    IF v_null IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Collection is atomically null');
    END IF;
END;
/
```

Calling methods like `COUNT` on an atomically NULL collection raises `COLLECTION_IS_NULL`; initialize collections with a constructor before invoking methods.

### 15.2. Not All Collection Methods Work in SQL

Methods such as `EXTEND`, `TRIM`, `DELETE`, `FIRST`, and `NEXT` are primarily PL/SQL collection methods. In SQL statements, use supported SQL collection syntax such as `TABLE()`, constructors, `CAST(MULTISET(...))`, and appropriate SQL functions. Do not assume every PL/SQL collection expression can be called directly inside SELECT.

## 16. Constraints and Data Integrity

Object types define attribute structure, but they do not replace relational table constraints.

### 16.1. Constraints on Object Tables

```sql
CREATE TABLE person_obj_table OF person_t (
    CONSTRAINT pk_person_obj PRIMARY KEY (person_id),
    CONSTRAINT ck_person_id CHECK (person_id > 0)
);
```

Constraints can be placed on object table attributes using supported syntax. When foreign-key relationships with other tables are needed, design constraints aligned with the storage structure.

### 16.2. Constraints on Object Columns

On an object column, constraints can reference eligible attributes:

```sql
CREATE TABLE customer_records (
    customer_id NUMBER PRIMARY KEY,
    address     address_t,
    CONSTRAINT ck_customer_postal
        CHECK (address.postal_code IS NULL
               OR LENGTH(address.postal_code) <= 20)
);
```

Verify exact syntax and object attribute constraint support on your Oracle version. When complex constraints are needed, splitting attributes into relational columns is often simpler.

### 16.3. Nested Tables Lack Built-In Business Primary Keys

Nested table elements can contain duplicates. If each child item must be unique by `LINE_NO` or `PRODUCT_ID`, include key attributes in the element object and implement appropriate checks; when explicit PK/FK and per-row constraints are needed, a relational child table is usually preferable.

### 16.4. VARRAY Caps Element Count Without Replacing Business Validation

`VARRAY(5)` prevents a collection from exceeding five elements, but it does not enforce:

- No duplicate phone numbers.
- Valid formatting for every phone number.
- Exactly one primary phone number.
- Business-valid priority order.

Those rules must be enforced in application code, via appropriate constraints, or through a relational table model.

## 17. Evolving Object Types and Schema Dependencies

An object type is a schema object. Tables, columns, collection types, methods, or other types can depend on it. Modifying a type definition requires reviewing dependencies.

Example adding an attribute:

```sql
ALTER TYPE person_t
ADD ATTRIBUTE (email VARCHAR2(150))
CASCADE;
```

This is an example of type evolution; depending on type, dependencies, and Oracle version, options like `CASCADE` or handling dependent objects may be needed. Never run ALTER TYPE on an active schema without assessing impact on tables, data, applications, and dependent types.

To inspect types in a schema:

```sql
SELECT type_name,
       typecode,
       attributes,
       methods
FROM user_types
ORDER BY type_name;
```

Inspect attributes:

```sql
SELECT type_name,
       attr_no,
       attr_name,
       attr_type_name,
       length,
       precision,
       scale
FROM user_type_attrs
WHERE type_name = 'CUSTOMER_T'
ORDER BY attr_no;
```

Inspect collection types:

```sql
SELECT type_name,
       coll_type,
       upper_bound,
       elem_type_name,
       elem_type_mod
FROM user_coll_types
ORDER BY type_name;
```

`USER_*` views show metadata in the current schema. Use `ALL_*` or `DBA_*` with appropriate privileges to inspect other schemas.

## 18. Privileges for Using Object Types

Creating and using object types requires appropriate privileges:

- `CREATE TYPE` to create types in a schema.
- `CREATE TABLE` to create tables using types.
- `EXECUTE` privilege on the type when another schema uses it.
- DML privileges on tables containing objects/collections.

Example granting type usage to an application user:

```sql
GRANT EXECUTE ON customer_profile_t TO app_user;
```

If a type contains other types, the application may require appropriate privileges on dependent types depending on usage and grants. Manage privileges following least-privilege principles.

Never grant broad privileges such as `DBA` just so an application can use an object type.

## 19. JDBC and Java Applications

Scalar columns map directly via `ResultSet.getLong`, `getString`, `getBigDecimal`, etc. Object types and collections require handling more complex types.

### 19.1. Reading Object Columns

JDBC provides abstractions such as `java.sql.Struct` for SQL structured types. Depending on the Oracle JDBC driver version, Oracle-specific APIs may exist to map object types to Java classes.

Conceptually:

```java
Object value = resultSet.getObject("PROFILE");
```

The returned object and decoding behavior depend on the driver, type mapping, and application setup. With `Struct`, applications extract attributes via corresponding APIs; do not assume every driver automatically turns object types into POJOs.

### 19.2. Reading Collections

JDBC provides `java.sql.Array` for SQL collections in many drivers. Oracle JDBC includes additional version-specific APIs/mappings. Check documentation for your driver version and release collection resources properly when required by the driver.

### 19.3. Application Portability

If an application uses ORMs or frameworks that do not map Oracle object types/collections cleanly, standard relational tables are usually simpler:

- Each entity is a table.
- Relationships are expressed via foreign keys.
- Collections are modeled as child tables.
- Queries use standard JOINs and row mapping.

Object-relational types make sense when the benefits of in-database object structures outweigh integration costs and platform coupling.

## 20. When to Use Object-Relational vs. Relational Modeling

| Requirement | Design to Consider |
|---|---|
| Reusable address structure typically read with profile | Object type in an object column |
| Table row directly represents an object with identity | Object table |
| Small, bounded list where order matters | VARRAY |
| Potentially large child list attached to parent row as a collection | Nested table |
| Child items with independent keys, relationships, and lifecycles | Relational child table |
| Standard JOINs, reporting, BI, and ORM integration | Standard relational tables |
| References to object identity | REF between object tables |
| Multi-DBMS portability | Standard relational model |

### 20.1. Example: Modeling a Phone Number List

**VARRAY** can make sense if each customer has at most five contact numbers, priority order matters, and the list is usually read/written as a unit:

```sql
CREATE TYPE phone_list_t AS VARRAY(5) OF VARCHAR2(20);
/

CREATE TABLE customer_contacts (
    customer_id NUMBER PRIMARY KEY,
    phones phone_list_t
);
```

**A relational child table** fits if phone numbers need verification status, phone type, verification timestamp, OTP opt-in flag, and history:

```sql
CREATE TABLE customer_phones (
    customer_id NUMBER NOT NULL,
    phone_no VARCHAR2(20) NOT NULL,
    phone_type VARCHAR2(20),
    is_verified CHAR(1) DEFAULT 'N' NOT NULL,
    priority_no NUMBER NOT NULL,
    CONSTRAINT pk_customer_phones
        PRIMARY KEY (customer_id, phone_no),
    CONSTRAINT ck_customer_phone_verified
        CHECK (is_verified IN ('Y', 'N'))
);
```

In the second model, each phone number is an independent row that can be queried and updated by its own attributes.

### 20.2. Example: Modeling Order Lines

Order lines typically have quantity, price, tax, discount, fulfillment status, and foreign keys to products. An `ORDER_LINES` table with PK/FK usually fits better than a nested table because each line has business identity and needs to join with many other tables.

A nested table can still fit when child items are simply an attribute collection of a parent object, processed together without broad independent relationships.

## 21. Comprehensive Lab Exercise

The commands below create dedicated object types, collection types, and tables in a practice schema. Run them only with `CREATE TYPE`/`CREATE TABLE` privileges, and avoid name collisions with existing objects.

### Step 1. Create Address and Profile Object Types

```sql
CREATE TYPE demo_address_t AS OBJECT (
    street VARCHAR2(100),
    city VARCHAR2(50)
);
/

CREATE TYPE demo_profile_t AS OBJECT (
    full_name VARCHAR2(100),
    address demo_address_t
);
/
```

### Step 2. Create a Relational Table with an Object Column

```sql
CREATE TABLE demo_customers (
    customer_id NUMBER PRIMARY KEY,
    profile demo_profile_t
);
```

### Step 3. Insert and Read Attributes

```sql
INSERT INTO demo_customers
VALUES (
    1,
    demo_profile_t(
        'An Nguyen',
        demo_address_t('12 Nguyen Hue', 'Ho Chi Minh City')
    )
);

SELECT customer_id,
       profile.full_name,
       profile.address.city
FROM demo_customers;
```

### Step 4. Create an Element Object Type and Nested Table

```sql
CREATE TYPE demo_line_t AS OBJECT (
    product_id NUMBER,
    quantity NUMBER
);
/

CREATE TYPE demo_line_nt AS TABLE OF demo_line_t;
/

CREATE TABLE demo_orders_nested (
    order_id NUMBER PRIMARY KEY,
    lines demo_line_nt
)
NESTED TABLE lines STORE AS demo_order_lines_store;
```

### Step 5. Insert into Nested Table and Unnest

```sql
INSERT INTO demo_orders_nested
VALUES (
    100,
    demo_line_nt(
        demo_line_t(2001, 2),
        demo_line_t(2002, 1)
    )
);

SELECT o.order_id,
       l.product_id,
       l.quantity
FROM demo_orders_nested o,
     TABLE(o.lines) l
ORDER BY o.order_id, l.product_id;
```

### Step 6. Create a VARRAY and Table Containing the VARRAY

```sql
CREATE TYPE demo_phone_va AS VARRAY(3) OF VARCHAR2(20);
/

CREATE TABLE demo_customer_phones (
    customer_id NUMBER PRIMARY KEY,
    phones demo_phone_va
);
```

### Step 7. Insert and Unnest the VARRAY

```sql
INSERT INTO demo_customer_phones
VALUES (
    1,
    demo_phone_va('0901000001', '0902000002')
);

SELECT c.customer_id,
       p.column_value AS phone_number
FROM demo_customer_phones c,
     TABLE(c.phones) p
ORDER BY c.customer_id, p.column_value;
```

### Step 8. Inspect Metadata

```sql
SELECT type_name, typecode
FROM user_types
WHERE type_name LIKE 'DEMO_%'
ORDER BY type_name;

SELECT type_name, coll_type, upper_bound, elem_type_name
FROM user_coll_types
WHERE type_name LIKE 'DEMO_%'
ORDER BY type_name;

SELECT table_name, column_name, storage_table_name
FROM user_nested_tables
WHERE table_name = 'DEMO_ORDERS_NESTED';
```

### Step 9. Clean Up Practice Objects

Only after verifying these are objects you created and data is no longer needed:

```sql
DROP TABLE demo_customer_phones PURGE;
DROP TABLE demo_orders_nested PURGE;
DROP TABLE demo_customers PURGE;

DROP TYPE demo_line_nt FORCE;
DROP TYPE demo_line_t FORCE;
DROP TYPE demo_phone_va FORCE;
DROP TYPE demo_profile_t FORCE;
DROP TYPE demo_address_t FORCE;
```

`DROP TABLE ... PURGE` drops the table and data, bypassing the recycle bin; DDL commits implicitly. `DROP TYPE ... FORCE` can break or invalidate dependencies; use it only in a lab schema after cleaning up dependent tables in the proper order. Never use it on business schemas.

## 22. Common Errors and Misconceptions

| Symptom | Cause | Resolution |
|---|---|---|
| `ORA-00902: invalid datatype` | Referencing a nonexistent type, type invalid in context, or wrong declaration type | Create dependent types first; verify type and syntax |
| `ORA-00904` when accessing attribute | Wrong attribute name or object path | Check type definition and table alias |
| `ORA-22905: cannot access rows from a non-nested table item` | Argument to TABLE() is not a valid collection | Check collection expression and data type |
| `ORA-22908: reference to NULL table value` | Collection table DML on a NULL collection | Initialize the collection or handle NULL first |
| `ORA-06531: Reference to uninitialized collection` | PL/SQL calls a method on an atomically NULL collection | Initialize with constructor before use |
| VARRAY exceeds bound | Element count exceeds `VARRAY(n)` | Increase type bound by design or use nested table/child table |
| Nested table returns unexpected order | Assuming collection preserves order | Add an ordering attribute and ORDER BY |
| TABLE(collection) drops empty parent rows | Using cross join expansion | Use appropriate outer expansion or query parent separately |
| Object type is hard to modify | Many tables/types depend on the type | Plan type evolution and dependencies carefully |
| JDBC does not map objects automatically | Driver/framework lacks type mapping config | Use Struct/Array or compatible Oracle driver APIs |
| Collection contains duplicate elements | Collections do not enforce business uniqueness automatically | Validate in application or use constrained child table |
| Object types used to replace all relational tables | Choosing model by syntax rather than query needs | Evaluate JOINs, constraints, ORMs, BI, and portability |

## 23. Quick-Reference Cheat Sheet

| Construct | Meaning and Usage |
|---|---|
| `CREATE TYPE ... AS OBJECT` | Defines an object type with attributes and optional methods |
| `CREATE TABLE ... OF object_type` | Creates an object table; each row is an object instance |
| `object_column object_type` | Creates an object column in a relational table |
| `CREATE TYPE ... AS TABLE OF ...` | Defines a nested table collection type |
| `CREATE TYPE ... AS VARRAY(n) OF ...` | Defines a VARRAY bounded to n elements |
| `NESTED TABLE col STORE AS storage_table` | Declares the storage table for a nested table column |
| `TABLE(collection_expression)` | Unnests a collection into a SQL row source |
| `VALUE(alias)` | Retrieves the complete object instance from an object table |
| `REF(alias)` / `DEREF(ref)` | Creates and dereferences an object reference |
| `CAST(MULTISET(subquery) AS collection_type)` | Converts multi-row query output into a collection type |
| `phone_list_t(...)` | Constructor creating a collection instance |
| Relational child table | Strong choice when items need PK/FK, constraints, and independent lifecycles |

## 24. Self-Check Questions

**Question 1.** What is an object type?

**Answer:** A schema-level user-defined data type grouping multiple attributes into a structured value, optionally with methods.

**Question 2.** How does an object table differ from an object column?

**Answer:** An object table has each row as an object instance; an object column is a column inside a standard relational table whose type is an object.

**Question 3.** How is a nested table stored?

**Answer:** Oracle stores elements in a separate storage table and links them to the parent row using internal metadata.

**Question 4.** What is the main difference between a VARRAY and a nested table?

**Answer:** A VARRAY has a fixed element limit and preserves order; a nested table has no fixed VARRAY-style bound and does not guarantee element order.

**Question 5.** What does `TABLE(collection_column)` do?

**Answer:** Unnests a collection into rows so it can be selected, joined, and filtered by element.

**Question 6.** Why must queries over a nested table not rely on INSERT order?

**Answer:** Nested tables do not guarantee element ordering; if order is needed, store an ordering attribute and use ORDER BY.

**Question 7.** How does an empty collection differ from a NULL collection?

**Answer:** An empty collection is initialized and holds 0 elements; a NULL collection has no collection instance.

**Question 8.** When should a VARRAY be used?

**Answer:** When a list has a natural small upper bound, order matters, and it is typically handled as a single value of the parent row.

**Question 9.** When should a relational child table be used instead of a nested table?

**Answer:** When child items have their own identity, foreign keys, constraints, auditing, privileges, or independent lifecycle.

**Question 10.** Is a REF the same as a NUMBER foreign key?

**Answer:** No. A REF points to the object identity of an object row; a scalar foreign key references a key in a relational table.

**Question 11.** What is `CAST(MULTISET(subquery) AS type)` used for?

**Answer:** Converts multiple rows from a query into a collection of a specific SQL collection type.

**Question 12.** Do object types replace table constraints?

**Answer:** No. Type definitions describe attribute structure; data integrity still requires constraints and appropriate rules on tables/collections or in the application layer.

**Question 13.** How does JDBC map object types and collections?

**Answer:** Using `Struct` for objects and `Array` for collections or Oracle driver APIs; exact capabilities depend on driver and type mapping configuration.

**Question 14.** Are object-relational types always better than standard relational tables?

**Answer:** No. Weigh query requirements, JOINs, constraints, ORM/BI support, portability, and operational complexity.

## 25. Conclusion

Oracle supports the object-relational model through **object types**, **object tables**, **object columns**, **nested tables**, **VARRAYs**, and **REFs**. An object type defines a structured value; an object table stores each row as an object instance, while an object column embeds objects inside a standard relational table. Nested tables represent collections without fixed VARRAY bounds and store elements in a separate storage table. VARRAYs enforce a maximum element bound and preserve collection order.

`TABLE()` unnests collections to query individual elements; `CAST(MULTISET(...))` converts multi-row query results into collections. However, collections do not replace PK/FK relationships or relational constraints. When child elements have independent identities, require multi-table JOINs, auditing, access control, or separate lifecycles, relational child tables are usually easier to manage and integrate.

Choose object-relational modeling when object/collection structures accurately mirror how data is used and type reuse brings clear benefits. Choose standard relational tables when query flexibility, integrity constraints, ORM/BI compatibility, and portability are priorities. A good model expresses business semantics clearly, remains maintainable, and fits how applications actually read, write, and manage data.
