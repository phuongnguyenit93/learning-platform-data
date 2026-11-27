# Associative Arrays, Nested Tables, and VARRAYs in PL/SQL

In PL/SQL, a **collection** is a data structure that holds multiple elements of the same type. Collections enable programs to process groups of values in memory, pass multiple values between subprograms, assemble data before writing to the database, and reduce context switches between the PL/SQL engine and the SQL engine.

Oracle provides three main collection types:

- **Associative array**: a set of elements accessed by an index key, typically an integer or a string. This collection is suited for in-memory lookups and key-value mappings.
- **Nested table**: a collection whose size can grow dynamically and which can become sparse after deleting elements. Nested tables can be used in SQL when the type is declared at schema level and can also be stored as a collection column in a table.
- **VARRAY** (*variable-size array*): an array with a fixed maximum element limit that preserves element order and is always dense from index 1 to COUNT. VARRAYs are suitable for small lists with a clear upper bound.

All three are collections, yet they differ in indexing, ability to be stored in SQL tables, size limits, element deletion behavior, and supported collection methods. Choosing the right type makes code easier to understand, avoids subscript errors, and lets you leverage BULK COLLECT/FORALL when processing large datasets.

## 1. Collections in PL/SQL

A collection holds multiple elements of the same data type. For example, a list of employee IDs:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF PLS_INTEGER;
    l_employee_ids t_employee_ids := t_employee_ids(101, 102, 103);
BEGIN
    DBMS_OUTPUT.PUT_LINE('Element count: ' || l_employee_ids.COUNT);
    DBMS_OUTPUT.PUT_LINE('First element: ' || l_employee_ids(1));
END;
/
~~~

Output:

~~~text
Element count: 3
First element: 101
~~~

T_EMPLOYEE_IDS is the collection type declared by the program; L_EMPLOYEE_IDS is the collection variable; T_EMPLOYEE_IDS(101, 102, 103) is the constructor creating a nested table with three elements.

### 1.1. How Collections Differ from Arrays in Conventional Languages

PL/SQL collections can:
- Grow or shrink in element count.
- Have sparse indices, depending on type.
- Use methods such as COUNT, FIRST, LAST, NEXT, PRIOR, and EXISTS.
- Be populated from SQL via BULK COLLECT.
- Be used to execute multiple DML statements via FORALL.

Not every collection shares the same capabilities. For instance, associative arrays have no EXTEND; VARRAYs cannot delete individual elements; nested tables can become sparse after DELETE.

### 1.2. Declaring Types and Variables

A collection type can be declared in:
- The DECLARE section of an anonymous PL/SQL block.
- The declarative section of a package.
- The specification/body of a procedure or function.
- The schema using CREATE TYPE for SQL-supported collection types.

Local type example:

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(100);
    l_names t_names;
BEGIN
    NULL;
END;
/
~~~

A type declared inside a block is scoped only to that block. If multiple procedures need to share the type, declare it in a package specification. If you need to use the collection as a SQL type outside PL/SQL, declare the type at schema level with CREATE TYPE.

### 1.3. The Three Collection Types Conceptually

~~~text
Associative array
  key -> value
  10  -> 'An'
  20  -> 'Binh'
  50  -> 'Chi'

Nested table
  1 -> 'An'
  2 -> 'Binh'
  3 -> 'Chi'
  DELETE(2) can create a gap at index 2

VARRAY(5)
  1 -> 'An'
  2 -> 'Binh'
  3 -> 'Chi'
  maximum 5 elements, contiguous indices
~~~

## 2. Associative Arrays

An **associative array** (formerly called an index-by table) is a collection storing elements by index key. The key can be PLS_INTEGER/BINARY_INTEGER or an Oracle-supported character type.

Associative arrays are commonly used like in-memory maps/dictionaries in PL/SQL.

### 2.1. Associative Array with PLS_INTEGER Keys

~~~sql
DECLARE
    TYPE t_salary_map IS TABLE OF NUMBER
        INDEX BY PLS_INTEGER;

    l_salary_by_employee t_salary_map;
BEGIN
    l_salary_by_employee(101) := 20000000;
    l_salary_by_employee(102) := 25000000;
    l_salary_by_employee(205) := 18000000;

    DBMS_OUTPUT.PUT_LINE(
        'Salary of Emp 102: ' || l_salary_by_employee(102)
    );

    DBMS_OUTPUT.PUT_LINE(
        'Element count: ' || l_salary_by_employee.COUNT
    );
END;
/
~~~

Here the indices 101, 102, and 205 are keys chosen by the program. They do not need to be contiguous and do not have to start at 1.

Associative arrays are ideal when you need fast lookup by a business key, such as EMPLOYEE_ID -> SALARY or PRODUCT_CODE -> STOCK.

### 2.2. Associative Array with String Keys

~~~sql
DECLARE
    TYPE t_country_map IS TABLE OF VARCHAR2(100)
        INDEX BY VARCHAR2(10);

    l_country_name t_country_map;
BEGIN
    l_country_name('VN') := 'Viet Nam';
    l_country_name('JP') := 'Japan';
    l_country_name('SG') := 'Singapore';

    DBMS_OUTPUT.PUT_LINE(l_country_name('VN'));
END;
/
~~~

String keys represent mappings such as country code to country name. When iterating an associative array with string keys, FIRST/NEXT order is governed by the session's character comparison/NLS rules; do not treat it as insertion order.

### 2.3. Associative Arrays Do Not Need a Constructor

A newly declared associative array variable is an empty collection ready for immediate use:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_numbers t_numbers;
BEGIN
    l_numbers(1) := 10;
    l_numbers(5) := 50;
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT);
END;
/
~~~

No constructor call is needed. Constructor syntax like T_NUMBERS(10, 20) does not apply to associative arrays the way it does for nested tables or VARRAYs.

### 2.4. Associative Arrays Can Be Sparse

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_numbers t_numbers;
BEGIN
    l_numbers(2) := 20;
    l_numbers(10) := 100;
    l_numbers(100) := 1000;

    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_numbers.COUNT);
    DBMS_OUTPUT.PUT_LINE('FIRST=' || l_numbers.FIRST);
    DBMS_OUTPUT.PUT_LINE('LAST=' || l_numbers.LAST);
END;
/
~~~

COUNT = 3, FIRST = 2, and LAST = 100. COUNT is the number of existing elements; LAST is the highest index, not the element count.

Do not write a 1..COUNT loop unless indices are guaranteed contiguous. Use FIRST/NEXT to iterate safely.

### 2.5. Traversing an Associative Array with FIRST and NEXT

~~~sql
DECLARE
    TYPE t_salary_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_salary t_salary_map;
    l_key PLS_INTEGER;
BEGIN
    l_salary(101) := 20000000;
    l_salary(105) := 25000000;
    l_salary(205) := 18000000;

    l_key := l_salary.FIRST;

    WHILE l_key IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Employee ' || l_key || ': ' || l_salary(l_key)
        );

        l_key := l_salary.NEXT(l_key);
    END LOOP;
END;
/
~~~

FIRST returns the first existing index; NEXT(key) returns the next existing index. When no elements remain, NEXT returns NULL.

### 2.6. Checking Elements with EXISTS

~~~sql
IF l_salary.EXISTS(105) THEN
    DBMS_OUTPUT.PUT_LINE('Data exists');
END IF;
~~~

EXISTS checks whether a key exists. Use EXISTS before reading an index that might not have been assigned to avoid non-existent element errors.

### 2.7. Deleting Associative Array Elements

~~~sql
l_salary.DELETE(105); -- Delete key 105
l_salary.DELETE;      -- Delete all elements
~~~

DELETE does not renumber remaining keys. If keys 101 and 205 remain after deleting 105, they retain their original keys.

Associative arrays do not support EXTEND, TRIM, or LIMIT.

## 3. Nested Tables

A **nested table** is a variable-size collection declared with TABLE OF. It can be used in PL/SQL and, when its type is declared at schema level, can be used as a SQL type and stored in a table's collection column.

### 3.1. Declaring and Initializing a Nested Table

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(100);
    l_names t_names := t_names('An', 'Binh', 'Chi');
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_names.COUNT);
    DBMS_OUTPUT.PUT_LINE(l_names(2));
END;
/
~~~

A nested table uses integer indices starting at 1 when created via constructor. It can grow using EXTEND and can develop gaps after calling DELETE on an element.

### 3.2. Uninitialized Nested Table vs. Empty Nested Table

A nested table variable declared without a constructor assignment is an **atomically null collection**:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers;
BEGIN
    -- l_numbers is atomically null.
    l_numbers := t_numbers(); -- Initialize empty collection.
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT);
END;
/
~~~

Calling COUNT on an atomically null collection raises ORA-06531 (Reference to uninitialized collection). Assign the empty constructor T_NUMBERS() to create an initialized collection with zero elements.

Distinction:
- Atomically null: not yet initialized.
- Empty collection: initialized, COUNT = 0.

Associative arrays differ: declaring the variable makes it immediately usable without a constructor.

### 3.3. Adding Elements with EXTEND

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(100);
    l_names t_names := t_names();
BEGIN
    l_names.EXTEND;
    l_names(1) := 'An';

    l_names.EXTEND;
    l_names(2) := 'Binh';

    DBMS_OUTPUT.PUT_LINE(l_names.COUNT);
END;
/
~~~

EXTEND appends elements at the end of the collection. For nested tables and VARRAYs, you can use EXTEND(n) to append n unpopulated null elements.

### 3.4. Deleting an Element and Creating Gaps

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(100);
    l_names t_names := t_names('An', 'Binh', 'Chi');
BEGIN
    l_names.DELETE(2);

    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_names.COUNT);
    DBMS_OUTPUT.PUT_LINE('FIRST=' || l_names.FIRST);
    DBMS_OUTPUT.PUT_LINE('LAST=' || l_names.LAST);

    IF l_names.EXISTS(2) THEN
        DBMS_OUTPUT.PUT_LINE('Index 2 exists');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Index 2 was deleted');
    END IF;
END;
/
~~~

After DELETE(2):
- Element 1 is still An.
- Index 2 does not exist.
- Element 3 is still Chi.
- COUNT = 2, LAST = 3.

The nested table becomes sparse. Indices do not automatically compact.

### 3.5. Deleting the Entire Nested Table

~~~sql
l_names.DELETE;
~~~

DELETE with no arguments removes all elements while keeping the collection initialized. Elements can be added again with EXTEND.

### 3.6. EXTEND and TRIM

- EXTEND: appends one element at the end.
- EXTEND(n): appends n elements.
- EXTEND(n, i): appends n copies of the element at index i.
- TRIM: removes the last element.
- TRIM(n): removes the last n elements.

Example:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30);
BEGIN
    l_numbers.EXTEND;
    l_numbers(4) := 40;

    l_numbers.TRIM(2);

    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_numbers.COUNT);
    DBMS_OUTPUT.PUT_LINE('LAST=' || l_numbers.LAST);
END;
/
~~~

TRIM removes elements from the end of the collection. Be cautious when mixing DELETE and TRIM on nested tables: DELETE leaves gaps without shrinking internal slot count the same way TRIM does. If you delete elements and then TRIM, elements are removed from the internal end position, which may not be the element the author expects. Combine them only when you understand the exact collection state.

### 3.7. Nested Tables Do Not Guarantee Order When Stored in the Database

In a PL/SQL variable, you can access a nested table by index. However, when a nested table is stored in a SQL table and queried with TABLE(collection_column), do not rely on physical storage order to infer element ordering. If SQL output order matters, use ORDER BY on an explicit ordinal column or stored attribute.

## 4. VARRAY

A **VARRAY** is a collection whose maximum size is fixed at type declaration. A VARRAY preserves element order and is always dense: valid indices are contiguous from 1 to COUNT.

Syntax:

~~~sql
TYPE type_name IS VARRAY(maximum_size) OF element_type;
~~~

### 4.1. Declaring and Initializing a VARRAY

~~~sql
DECLARE
    TYPE t_phone_numbers IS VARRAY(5) OF VARCHAR2(20);
    l_phones t_phone_numbers :=
        t_phone_numbers('0900000001', '0900000002');
BEGIN
    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_phones.COUNT);
    DBMS_OUTPUT.PUT_LINE('LIMIT=' || l_phones.LIMIT);
    DBMS_OUTPUT.PUT_LINE('FIRST=' || l_phones.FIRST);
    DBMS_OUTPUT.PUT_LINE('LAST=' || l_phones.LAST);
END;
/
~~~

The VARRAY holds at most 5 elements. In this example, COUNT=2 and LIMIT=5.

### 4.2. Adding Elements to a VARRAY

~~~sql
DECLARE
    TYPE t_tags IS VARRAY(3) OF VARCHAR2(20);
    l_tags t_tags := t_tags('NEW');
BEGIN
    l_tags.EXTEND;
    l_tags(2) := 'PAID';

    l_tags.EXTEND;
    l_tags(3) := 'SHIPPED';

    DBMS_OUTPUT.PUT_LINE(l_tags.COUNT);
END;
/
~~~

Calling EXTEND beyond LIMIT raises a VARRAY limit error, typically ORA-06532 (Subscript outside of limit).

### 4.3. VARRAYs Are Always Dense

You cannot delete an individual element in the middle of a VARRAY using DELETE(index). VARRAYs do not support the DELETE method; you can remove trailing elements with TRIM or overwrite element values.

Example:

~~~sql
l_tags.TRIM; -- Remove last element
~~~

After TRIM, COUNT decreases by one and remaining indices stay contiguous from 1.

### 4.4. VARRAYs Preserve Order

If a small list has a clear business order, such as workflow steps or prioritized phone numbers, VARRAY can be a good fit. When a VARRAY is stored in the database, element order is part of the collection's semantics; however, when querying via TABLE(varray_column), use an appropriate ordering/ordinal mechanism if the application requires a strict output order contract.

### 4.5. LIMIT Is Only Meaningful for VARRAYs

LIMIT returns the maximum number of elements of a VARRAY. For nested tables and associative arrays, LIMIT returns NULL.

~~~sql
DECLARE
    TYPE t_small_list IS VARRAY(10) OF NUMBER;
    l_values t_small_list := t_small_list(1, 2, 3);
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_values.LIMIT); -- 10
END;
/
~~~

## 5. Comparing the Three Collection Types

| Feature | Associative Array | Nested Table | VARRAY |
| --- | --- | --- | --- |
| Indices | PLS_INTEGER or string keys | Integers | Integers |
| Constructor | No | Yes | Yes |
| Declared max size | No fixed type limit | No declared max limit | Has LIMIT |
| Sparse | Yes | Can be sparse after DELETE | No, always dense |
| Preserves element order | Traversed in key order, not insertion order | Do not rely on order when stored/queried in SQL | Preserves element order |
| EXTEND | No | Yes | Yes |
| TRIM | No | Yes | Yes |
| DELETE(index) | Yes | Yes | No |
| DELETE all | Yes | Yes | No DELETE method |
| LIMIT | NULL | NULL | Maximum size |
| Used in PL/SQL | Yes | Yes | Yes |
| Stored directly as SQL column | No | Yes, with SQL type | Yes, with SQL type |
| Typical usage pattern | In-memory map/cache/lookup | Variable lists, nested collections in SQL | Small bounded lists |

### 5.1. Choosing the Type by Requirement

- Use an associative array when you need key-value mapping, lookup by code, and do not need to store the collection as a SQL column.
- Use a nested table when the element count varies, you need to use the collection in SQL, or you need to store an expandable set of elements.
- Use a VARRAY when the element count has a clear upper bound and element order matters.

Do not pick a collection by name alone. Determine:
- Do you need arbitrary keys or 1..N indices?
- Do you need to delete elements from the middle?
- Must element order be preserved?
- Does the collection need to be stored in a SQL table?
- Is the maximum size known in advance?
- Will you use BULK COLLECT/FORALL, and are indices contiguous?

## 6. Collection Methods

Oracle provides collection methods to query state and manipulate elements. Methods do not apply uniformly to all collection types.

| Method | Meaning | Associative Array | Nested Table | VARRAY |
| --- | --- | --- | --- | --- |
| COUNT | Current number of elements | Yes | Yes | Yes |
| FIRST | First index | Yes | Yes | Yes |
| LAST | Last index | Yes | Yes | Yes |
| PRIOR(n) | Index preceding n | Yes | Yes | Yes |
| NEXT(n) | Index following n | Yes | Yes | Yes |
| EXISTS(n) | Checks element existence | Yes | Yes | Yes |
| DELETE | Deletes element(s)/range | Yes | Yes | No |
| EXTEND | Appends elements at end | No | Yes | Yes |
| TRIM | Removes elements from end | No | Yes | Yes |
| LIMIT | Maximum limit | NULL | NULL | Yes |

### 6.1. COUNT

COUNT returns the current number of elements. For sparse collections, COUNT does not necessarily equal LAST.

### 6.2. FIRST and LAST

FIRST and LAST return the first/last existing index; for an empty collection, they return NULL.

### 6.3. NEXT and PRIOR

NEXT(index_value) and PRIOR(index_value) return the next or previous existing index. They are especially useful when a collection is sparse or an associative array uses non-contiguous keys.

### 6.4. EXISTS

~~~sql
IF l_collection.EXISTS(i) THEN
    -- Safely read element.
END IF;
~~~

EXISTS returns TRUE if an element exists at that index/key. Use EXISTS before reading an index that may be unassigned to avoid missing-element errors.

### 6.5. DELETE

~~~sql
l_collection.DELETE;
l_collection.DELETE(i);
l_collection.DELETE(m, n);
~~~

DELETE with no arguments removes all elements; DELETE(i) removes one element; DELETE(m,n) removes a range of indices in supported collection types. Associative arrays and nested tables support DELETE; VARRAY does not.

### 6.6. EXTEND

~~~sql
l_collection.EXTEND;
l_collection.EXTEND(n);
l_collection.EXTEND(n, i);
~~~

EXTEND adds elements to nested tables/VARRAYs. EXTEND(n,i) creates copies of the element at index i; if the source element does not exist, the operation fails.

### 6.7. TRIM

~~~sql
l_collection.TRIM;
l_collection.TRIM(n);
~~~

TRIM removes one or more trailing elements from a nested table/VARRAY. It does not apply to associative arrays.

## 7. Safely Traversing Collections

A common mistake is assuming every collection has contiguous indices from 1 to COUNT.

Unsafe example for sparse collections:

~~~sql
FOR i IN 1 .. l_names.COUNT LOOP
    DBMS_OUTPUT.PUT_LINE(l_names(i));
END LOOP;
~~~

If index 2 was deleted via DELETE and the collection only has indices 1 and 3, the loop still accesses 2 and fails.

Traversing with FIRST/NEXT:

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(100);
    l_names t_names := t_names('An', 'Binh', 'Chi');
    i PLS_INTEGER;
BEGIN
    l_names.DELETE(2);

    i := l_names.FIRST;

    WHILE i IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Index=' || i || ', Value=' || l_names(i)
        );
        i := l_names.NEXT(i);
    END LOOP;
END;
/
~~~

This works for associative arrays, sparse nested tables, and VARRAYs.

### 7.1. Reverse Traversal with PRIOR

~~~sql
i := l_names.LAST;

WHILE i IS NOT NULL LOOP
    DBMS_OUTPUT.PUT_LINE(l_names(i));
    i := l_names.PRIOR(i);
END LOOP;
~~~

Reverse traversal is useful when processing from the last element to the first. It does not mean the collection is sorted by business criteria; order follows the index/key.

### 7.2. Traversing a String-Keyed Associative Array

~~~sql
DECLARE
    TYPE t_country_map IS TABLE OF VARCHAR2(100)
        INDEX BY VARCHAR2(10);
    l_countries t_country_map;
    l_code VARCHAR2(10);
BEGIN
    l_countries('VN') := 'Viet Nam';
    l_countries('JP') := 'Japan';
    l_countries('SG') := 'Singapore';

    l_code := l_countries.FIRST;

    WHILE l_code IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(
            l_code || ': ' || l_countries(l_code)
        );
        l_code := l_countries.NEXT(l_code);
    END LOOP;
END;
/
~~~

Traversal order follows key order per the session's comparison rules, not the order of assignment statements.

## 8. Collections of Records

A collection can hold records instead of just scalar values. This is useful when keeping multiple attributes of a row together in each element.

~~~sql
DECLARE
    TYPE t_employee_record IS RECORD (
        employee_id NUMBER,
        full_name   VARCHAR2(100),
        salary      NUMBER
    );

    TYPE t_employee_list IS TABLE OF t_employee_record
        INDEX BY PLS_INTEGER;

    l_employees t_employee_list;
BEGIN
    l_employees(1).employee_id := 101;
    l_employees(1).full_name := 'An';
    l_employees(1).salary := 20000000;

    l_employees(2).employee_id := 102;
    l_employees(2).full_name := 'Binh';
    l_employees(2).salary := 25000000;

    DBMS_OUTPUT.PUT_LINE(l_employees(2).full_name);
END;
/
~~~

Collections of records keep related columns grouped in one element. With BULK COLLECT, you can populate a record collection from a cursor or use multiple parallel collections. Choose the structure that is easier to maintain and avoid parallel collections that could drift out of index sync.

## 9. BULK COLLECT: Loading Multiple Rows into Collections

Normally, PL/SQL can fetch row by row with FETCH or SELECT INTO. When processing many rows, BULK COLLECT loads multiple rows in a single data transfer between the SQL engine and PL/SQL engine.

Example:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    TYPE t_salaries IS TABLE OF employees.salary%TYPE;

    l_employee_ids t_employee_ids;
    l_salaries     t_salaries;
BEGIN
    SELECT employee_id, salary
    BULK COLLECT INTO l_employee_ids, l_salaries
    FROM employees
    WHERE department_id = 10;

    FOR i IN 1 .. l_employee_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            l_employee_ids(i) || ': ' || l_salaries(i)
        );
    END LOOP;
END;
/
~~~

Collections in the INTO clause are populated positionally: the i-th element of L_EMPLOYEE_IDS aligns with the i-th element of L_SALARIES.

### 9.1. BULK COLLECT with a Cursor

For large datasets, do not default to loading all rows into memory. Fetch in batches using LIMIT:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, salary
        FROM employees
        ORDER BY employee_id;

    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    TYPE t_salaries IS TABLE OF employees.salary%TYPE;

    l_ids      t_employee_ids;
    l_salaries t_salaries;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        BULK COLLECT INTO l_ids, l_salaries
        LIMIT 500;

        EXIT WHEN l_ids.COUNT = 0;

        FOR i IN 1 .. l_ids.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                l_ids(i) || ': ' || l_salaries(i)
            );
        END LOOP;
    END LOOP;

    CLOSE c_employees;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employees%ISOPEN THEN
            CLOSE c_employees;
        END IF;
        RAISE;
END;
/
~~~

LIMIT 500 caps the number of rows loaded per batch. The LIMIT value should be chosen based on row width, memory, and workload; there is no single optimal number for every application.

### 9.2. Why Is LIMIT Needed?

If SELECT BULK COLLECT loads millions of rows into a single collection, the session can consume excessive PGA memory and hit memory errors. Fetching in batches caps the volume of data resident in PL/SQL memory.

Each FETCH BULK COLLECT inside the loop replaces the collection's contents with the newly fetched batch; finish processing the current batch before fetching the next.

### 9.3. SELECT BULK COLLECT INTO When No Rows Match

Unlike standard SELECT INTO, SELECT BULK COLLECT INTO does not raise NO_DATA_FOUND simply because no rows matched. The target collection becomes empty with COUNT = 0.

~~~sql
SELECT employee_id
BULK COLLECT INTO l_ids
FROM employees
WHERE department_id = -1;

IF l_ids.COUNT = 0 THEN
    DBMS_OUTPUT.PUT_LINE('No employees found');
END IF;
~~~

## 10. FORALL: Executing Multiple DMLs via Bulk Binding

FORALL is a PL/SQL statement that sends a batch of DML operations to the SQL engine using collections as bind sources. It reduces round-trips between the PL/SQL and SQL engines compared to a regular DML loop.

Regular loop example:

~~~sql
FOR i IN 1 .. l_employee_ids.COUNT LOOP
    UPDATE employees
    SET salary = salary + 100000
    WHERE employee_id = l_employee_ids(i);
END LOOP;
~~~

FORALL:

~~~sql
FORALL i IN 1 .. l_employee_ids.COUNT
    UPDATE employees
    SET salary = salary + 100000
    WHERE employee_id = l_employee_ids(i);
~~~

FORALL is not a conventional PL/SQL loop; it is a bulk SQL statement. DML still executes per bound element, but with reduced engine-switching overhead.

### 10.1. Complete Example

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = l_ids(i);

    DBMS_OUTPUT.PUT_LINE(
        'Rows updated: ' || SQL%ROWCOUNT
    );

    COMMIT;
END;
/
~~~

In this example, SELECT BULK COLLECT retrieves the ID list and FORALL updates rows by ID. SQL%ROWCOUNT after FORALL reflects the total rows affected by the most recent bulk DML.

### 10.2. FORALL Requires Compatible Collection Indexing

The pattern FORALL i IN 1..collection.COUNT assumes indices exist contiguously from 1 to COUNT. If the collection is sparse or uses non-contiguous PLS_INTEGER keys, use INDICES OF or VALUES OF as appropriate.

### 10.3. INDICES OF for Sparse Collections

~~~sql
DECLARE
    TYPE t_id_map IS TABLE OF employees.employee_id%TYPE
        INDEX BY PLS_INTEGER;

    l_ids t_id_map;
BEGIN
    l_ids(2) := 101;
    l_ids(10) := 102;
    l_ids(50) := 103;

    FORALL i IN INDICES OF l_ids
        UPDATE employees
        SET salary = salary + 50000
        WHERE employee_id = l_ids(i);

    COMMIT;
END;
/
~~~

INDICES OF iterates over the indices that actually exist in the collection, avoiding the contiguous-range assumption.

### 10.4. VALUES OF Using an Index Collection

VALUES OF lets one collection specify which indices to use from the source collection:

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF employees.employee_id%TYPE
        INDEX BY PLS_INTEGER;
    TYPE t_index_list IS TABLE OF PLS_INTEGER
        INDEX BY PLS_INTEGER;

    l_ids     t_id_list;
    l_indexes t_index_list;
BEGIN
    l_ids(10) := 101;
    l_ids(20) := 102;
    l_ids(30) := 103;

    l_indexes(1) := 10;
    l_indexes(2) := 30;

    FORALL i IN VALUES OF l_indexes
        UPDATE employees
        SET salary = salary + 100000
        WHERE employee_id = l_ids(i);

    COMMIT;
END;
/
~~~

In this example, only elements of L_IDS at keys 10 and 30 are used. The collection holding index values must have a compatible type and all referenced keys must exist.

## 11. SAVE EXCEPTIONS in FORALL

By default, if an iteration in FORALL hits an error, Oracle stops the bulk operation and raises the error. When you want to continue processing the remaining elements and collect the errors, use SAVE EXCEPTIONS.

~~~sql
DECLARE
    TYPE t_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_ids := t_ids(101, 102, -1, 103);

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        UPDATE employees
        SET salary = salary + 100000
        WHERE employee_id = l_ids(i);

    DBMS_OUTPUT.PUT_LINE('Total rows: ' || SQL%ROWCOUNT);
EXCEPTION
    WHEN e_bulk_errors THEN
        DBMS_OUTPUT.PUT_LINE(
            'Error count: ' || SQL%BULK_EXCEPTIONS.COUNT
        );

        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Iteration=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', Error=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE
            );
        END LOOP;

        RAISE;
END;
/
~~~

When errors occur, Oracle completes all feasible iterations and stores error details in SQL%BULK_EXCEPTIONS. Then exception ORA-24381 is raised for the program to handle.

In the example, RAISE re-raises the error after printing details. If you omit RAISE and continue, you must explicitly decide whether successful changes should be COMMITted or ROLLBACKed. SAVE EXCEPTIONS does not automatically roll back the entire batch.

### 11.1. SQL%BULK_EXCEPTIONS

Each element in SQL%BULK_EXCEPTIONS has:
- ERROR_INDEX: the FORALL iteration index that caused the error.
- ERROR_CODE: the Oracle error code stored without a negative sign in the attribute.

You can retrieve the error message using SQLERRM with the negated code:

~~~sql
SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
~~~

Map ERROR_INDEX back to your collection index and FORALL form carefully; with INDICES OF/VALUES OF, do not confuse the iteration ordinal with the original collection key.

### 11.2. SQL%BULK_ROWCOUNT

SQL%BULK_ROWCOUNT(i) reports how many rows were affected by iteration i of FORALL. For instance, an UPDATE by primary key is typically 0 or 1.

~~~sql
FOR i IN 1 .. l_ids.COUNT LOOP
    DBMS_OUTPUT.PUT_LINE(
        'Iteration ' || i ||
        ' affected ' || SQL%BULK_ROWCOUNT(i)
    );
END LOOP;
~~~

This attribute is helpful when you need to know which ID matched no rows or when a DML affected more rows than expected.

## 12. Collections in SQL: PL/SQL Types vs. Schema Types

Not every PL/SQL collection can be used in every SQL context. Distinguish between:
- Collection types declared inside a PL/SQL block/package.
- Collection types declared at schema level with CREATE TYPE.

If you want a collection to be a SQL type usable in DDL, table columns, or TABLE(collection_expression), declare a SQL collection type at schema level.

### 12.1. Creating a Schema-Level Nested Table Type

~~~sql
CREATE TYPE number_list_t AS TABLE OF NUMBER;
/
~~~

Then you can use the type in SQL:

~~~sql
SELECT column_value
FROM TABLE(number_list_t(10, 20, 30));
~~~

COLUMN_VALUE is the default column name when TABLE() unnests a scalar collection.

### 12.2. Using a Collection Type in a Table

~~~sql
CREATE TABLE project_demo (
    project_id NUMBER PRIMARY KEY,
    project_codes number_list_t
)
NESTED TABLE project_codes STORE AS project_codes_nt;
~~~

PROJECT_CODES is a nested table column. Oracle stores the elements in the specified nested table storage table.

Inserting a collection:

~~~sql
INSERT INTO project_demo(project_id, project_codes)
VALUES (1, number_list_t(100, 200, 300));

COMMIT;
~~~

Reading elements:

~~~sql
SELECT p.project_id,
       x.COLUMN_VALUE AS project_code
FROM project_demo p,
     TABLE(p.project_codes) x
ORDER BY p.project_id, x.COLUMN_VALUE;
~~~

ORDER BY here sorts by value; do not assume physical storage order of a nested table.

### 12.3. Using a Schema-Level VARRAY Type

~~~sql
CREATE TYPE phone_list_t AS VARRAY(5) OF VARCHAR2(20);
/
~~~

Creating the table:

~~~sql
CREATE TABLE customer_phone_demo (
    customer_id NUMBER PRIMARY KEY,
    phone_numbers phone_list_t
);
~~~

Inserting:

~~~sql
INSERT INTO customer_phone_demo
VALUES (
    1,
    phone_list_t('0900000001', '0900000002')
);

COMMIT;
~~~

VARRAY fits a list of phone numbers capped at a maximum of 5 in this example.

### 12.4. Associative Arrays Are Not SQL Column Types

An associative array is an in-memory PL/SQL structure; you cannot declare it directly as a SQL table column like a SQL nested table or VARRAY type. If you need to persist a list long-term in the database, consider a nested table, VARRAY, or a conventional relational model with a child table.

If you only need to pass a list of IDs inside PL/SQL or bind to bulk DML, an associative array can be very suitable.

### 12.5. SQL Interoperability Depends on How the Type Is Declared

A collection type local to a block does not have the same scope and SQL interoperability as a schema-level SQL type. Modern Oracle versions support certain PL/SQL types in SQL, yet limitations still apply regarding types, usage positions, and contexts. When you need a type used reliably in DDL, SQL queries, views, or across applications, a schema-level SQL type is the clearer and more compatible choice.

## 13. Collections and Procedure/Function Parameters

Collections can be IN, OUT, or IN OUT parameters of procedures/functions.

Package type example:

~~~sql
CREATE OR REPLACE PACKAGE employee_api AS
    TYPE t_employee_ids IS TABLE OF PLS_INTEGER
        INDEX BY PLS_INTEGER;

    PROCEDURE list_ids(
        p_ids OUT t_employee_ids
    );
END employee_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY employee_api AS
    PROCEDURE list_ids(
        p_ids OUT t_employee_ids
    ) IS
    BEGIN
        p_ids(1) := 101;
        p_ids(2) := 102;
        p_ids(3) := 103;
    END list_ids;
END employee_api;
/
~~~

Calling:

~~~sql
DECLARE
    l_ids employee_api.t_employee_ids;
    i PLS_INTEGER;
BEGIN
    employee_api.list_ids(l_ids);

    i := l_ids.FIRST;
    WHILE i IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(l_ids(i));
        i := l_ids.NEXT(i);
    END LOOP;
END;
/
~~~

Declaring the type in the package specification lets callers see the type and use it to declare variables receiving the output.

### 13.1. Choosing Package Type vs. Schema SQL Type

- Package PL/SQL types fit internal PL/SQL APIs.
- Schema SQL types fit when the type must be used in SQL, table columns, TABLE(), or shared across schemas/applications under granted privileges.
- Associative arrays fit in-memory lookups and bulk processing in PL/SQL.
- Schema nested table/VARRAY types fit collection data processed or stored by SQL.

## 14. Collections and Performance: BULK COLLECT/FORALL

The PL/SQL and SQL engines are two execution environments separated by a context-switch boundary. If code loops row by row and issues a SQL statement per row, switching overhead can become large.

Row-by-row example:

~~~sql
FOR r IN (
    SELECT employee_id
    FROM employees
    WHERE department_id = 10
) LOOP
    UPDATE employees
    SET salary = salary * 1.05
    WHERE employee_id = r.employee_id;
END LOOP;
~~~

Bulk processing:

~~~sql
DECLARE
    TYPE t_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = l_ids(i);

    COMMIT;
END;
/
~~~

BULK COLLECT reduces round-trips fetching data from SQL to PL/SQL; FORALL reduces round-trips sending DML from PL/SQL to SQL. The two mechanisms often work together.

### 14.1. Bulk Is Not Always Faster

For an UPDATE expressible in set-based SQL, prefer a single SQL statement:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
~~~

Set-based SQL is usually simpler and more efficient than selecting IDs and then running FORALL UPDATE on the exact same set of rows.

Use BULK COLLECT/FORALL when processing logic requires PL/SQL or must execute DML driven by individual collection elements. Do not convert every simple SQL statement into bulk PL/SQL code.

### 14.2. Batch Size and PGA

Unbounded BULK COLLECT can load too much data into PGA. Use LIMIT to control batch size. The right value depends on:
- Record width.
- Column count.
- Session memory.
- Processing speed per batch.
- Resource contention levels.

Measure with representative data.

### 14.3. Transaction Boundaries Are Still Controlled by COMMIT/ROLLBACK

FORALL does not auto-COMMIT. BULK COLLECT does not end a transaction either. DML changes remain part of the current transaction; the caller decides COMMIT or ROLLBACK.

## 15. Common Collection Errors

| Error/Situation | Cause | Resolution |
| --- | --- | --- |
| ORA-06531 | Accessing an atomically null collection | Initialize nested table/VARRAY via constructor |
| ORA-06532 | Exceeding VARRAY LIMIT | Check LIMIT before EXTEND |
| ORA-06533 | Accessing beyond valid collection elements | Check COUNT/EXISTS and indices |
| NO_DATA_FOUND when reading an element | Index/key does not exist or was deleted | Use EXISTS, FIRST/NEXT |
| FOR loop accesses deleted element | Assuming collection is dense | Traverse via FIRST/NEXT or FORALL INDICES OF |
| Calling EXTEND on associative array | Associative arrays do not support EXTEND | Assign directly by key |
| Calling DELETE(index) on VARRAY | VARRAY does not support deleting individual elements | Use TRIM for trailing elements or rebuild collection |
| Confusing COUNT with LAST | Sparse collection | Distinguish element count from last index |
| BULK COLLECT consumes excessive PGA | Loading too large a dataset at once | FETCH BULK COLLECT LIMIT |
| FORALL error aborts entire batch | Missing SAVE EXCEPTIONS | Use SAVE EXCEPTIONS if per-iteration errors should be collected |
| SQL rejects local collection type | Type is not in an appropriate SQL scope | Declare a schema-level SQL collection type when needed |
| Nested table query order changes | Relying on physical storage order | ORDER BY an explicit key/ordinal |

## 16. Comprehensive Practice Example

This example creates an employee ID map in an associative array, bulk-loads rows from a table, and updates them with FORALL. Run in a sandbox schema.

### 16.1. Declaring and Using an Associative Array

~~~sql
DECLARE
    TYPE t_salary_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_salary t_salary_map;
    k PLS_INTEGER;
BEGIN
    l_salary(101) := 20000000;
    l_salary(105) := 25000000;
    l_salary(205) := 18000000;

    k := l_salary.FIRST;
    WHILE k IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(k || ' => ' || l_salary(k));
        k := l_salary.NEXT(k);
    END LOOP;
END;
/
~~~

### 16.2. Sparse Nested Table

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(50);
    l_names t_names := t_names('An', 'Binh', 'Chi', 'Dung');
    i PLS_INTEGER;
BEGIN
    l_names.DELETE(2);

    i := l_names.FIRST;
    WHILE i IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(i || ': ' || l_names(i));
        i := l_names.NEXT(i);
    END LOOP;
END;
/
~~~

Output shows indices 1, 3, 4. COUNT=3 while LAST=4.

### 16.3. Bounded VARRAY

~~~sql
DECLARE
    TYPE t_steps IS VARRAY(4) OF VARCHAR2(30);
    l_steps t_steps := t_steps('CREATED', 'PAID');
BEGIN
    l_steps.EXTEND;
    l_steps(3) := 'PACKED';

    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_steps.COUNT);
    DBMS_OUTPUT.PUT_LINE('LIMIT=' || l_steps.LIMIT);

    l_steps.TRIM;
    DBMS_OUTPUT.PUT_LINE('COUNT after TRIM=' || l_steps.COUNT);
END;
/
~~~

VARRAY keeps steps in order and prevents exceeding four elements.

### 16.4. Batched BULK COLLECT and FORALL

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id;

    TYPE t_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_ids;
BEGIN
    OPEN c_employee;

    LOOP
        FETCH c_employee BULK COLLECT INTO l_ids LIMIT 200;
        EXIT WHEN l_ids.COUNT = 0;

        FORALL i IN 1 .. l_ids.COUNT
            UPDATE employees
            SET salary = salary + 100000
            WHERE employee_id = l_ids(i);
    END LOOP;

    CLOSE c_employee;
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employee%ISOPEN THEN
            CLOSE c_employee;
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

This example processes batches of 200 employees. All DML across batches belongs to the current transaction until the final COMMIT. If an error raises an exception out of the block, ROLLBACK undoes all uncommitted updates.

## 17. Process for Choosing a Collection Type

Before declaring a collection, determine:

1. Are elements accessed by ordinal position or by a business key?
2. Does the key need to be a string?
3. Does the collection need to be stored directly in a SQL table?
4. Is there a fixed maximum size limit?
5. Do you need to delete elements from the middle?
6. Must element order be preserved as part of the data?
7. Can there be gaps in indices?
8. Does the collection need to be used in TABLE(), SQL expressions, or schema DDL?
9. Do you need BULK COLLECT/FORALL?
10. Is the dataset large enough to require batched fetching?

Suggestions:

| Requirement | Suitable Collection |
| --- | --- |
| Map employee_id -> salary | Associative array |
| Key is a string code, PL/SQL lookup | Associative array |
| Variable-size list used in SQL | Nested table |
| Collection stored in table column with potentially many items | Nested table or VARRAY depending on semantics |
| Small bounded list preserving order | VARRAY |
| Delete arbitrary items and allow sparse indices | Associative array or nested table |
| Bulk bind using PLS_INTEGER indices | Associative array, nested table, or VARRAY |
| SQL type shared across schemas | Schema-level nested table/VARRAY type |

## 18. Common Misconceptions

**Associative arrays, nested tables, and VARRAYs are the same, just with different names.** False. They differ in indexing, sparse/dense behavior, size limits, SQL storage, and collection methods.

**Associative arrays start at index 1.** False. Keys are chosen by the program and can be non-contiguous integers or strings.

**COUNT always equals LAST.** False for sparse collections. COUNT is the element count, while LAST is the highest existing index/key.

**Nested tables are always dense.** False. DELETE(index) can leave gaps.

**VARRAYs can DELETE elements in the middle.** False. VARRAYs do not support the DELETE method; use TRIM from the end or construct a new collection.

**Associative arrays need a constructor before assignment.** False. Associative array variables can be used immediately after declaration.

**An uninitialized nested table has COUNT=0.** False. It can be atomically null; an empty constructor is needed to initialize it.

**EXTEND works on every collection.** False. EXTEND applies only to nested tables and VARRAYs.

**LIMIT works on every collection.** False. LIMIT returns a maximum size only for VARRAYs; the other types return NULL.

**Insertion order of an associative array equals FIRST/NEXT order.** False. Associative arrays are traversed in key order.

**Nested table queries always return elements in their original order.** False. Use ORDER BY when deterministic output order is required.

**BULK COLLECT automatically bounds memory.** False. LIMIT is needed when fetching large sets.

**FORALL is a regular FOR loop.** False. FORALL is a bulk DML statement that reduces context switching.

**FORALL auto-COMMITs.** False. Transaction boundaries remain managed by the program's COMMIT/ROLLBACK.

**SAVE EXCEPTIONS automatically rolls back every successful iteration.** False. It collects iteration errors; the program decides COMMIT/ROLLBACK.

**Every PL/SQL collection can be a SQL table column.** False. Associative arrays are not SQL column types; use SQL nested table/VARRAY types when storing collections.

**If an UPDATE can be written set-based, you should still use FORALL.** False. A single set-based SQL statement is usually simpler and faster; FORALL is useful when logic truly needs collection processing in PL/SQL.

## 19. Practice Exercises

1. Declare an associative array mapping EMPLOYEE_ID to SALARY and add three elements.
2. Use an associative array with VARCHAR2 keys to map country codes to country names.
3. Why don't associative arrays need a constructor?
4. Write a FIRST/NEXT loop to traverse an associative array with keys 10, 50, 100.
5. Declare a nested table and initialize it empty using a constructor.
6. Explain the difference between an atomically null collection and an empty collection.
7. Add five elements to a nested table using EXTEND.
8. Delete the second element and explain how COUNT differs from LAST.
9. Traverse a sparse nested table without subscript errors.
10. Explain how EXTEND(n,i) works.
11. Why must you be careful when combining DELETE and TRIM?
12. Declare a VARRAY with a maximum of five elements and add three values.
13. Try calling EXTEND past LIMIT and explain the error.
14. Why are VARRAYs always dense?
15. Compare DELETE and TRIM on a nested table.
16. List the collection methods supported by each collection type.
17. Use PRIOR to traverse a collection from the end to the beginning.
18. Declare a collection of records holding EMPLOYEE_ID, FULL_NAME, and SALARY.
19. Use SELECT BULK COLLECT INTO to fetch IDs and salaries for department 10.
20. Write FETCH BULK COLLECT LIMIT 100 and process each batch.
21. Why can unbounded BULK COLLECT put pressure on PGA?
22. Use FORALL to update salaries for a list of employee IDs.
23. When a collection is sparse, why is 1..COUNT unsafe?
24. Rewrite FORALL using INDICES OF.
25. Explain VALUES OF and create a selective index collection.
26. Use SAVE EXCEPTIONS and print ERROR_INDEX/ERROR_CODE.
27. Distinguish SQL%BULK_EXCEPTIONS from SQL%BULK_ROWCOUNT.
28. Create a SQL-level nested table type and query it using TABLE().
29. Create a schema-level VARRAY type and use it as a table column.
30. Why can't an associative array be declared directly as a table column?
31. A report needs to pass a list of IDs from PL/SQL to SQL. Choose an appropriate collection type and type scope.
32. A simple UPDATE can process all rows with one predicate. Why might set-based SQL be better than BULK COLLECT/FORALL?
33. Design a collection for an ordered list of at most three status steps.
34. Design a collection to map product codes to inventory quantities.
35. Write a block with an exception handler to close the cursor and roll back if bulk DML fails.

**Associative arrays suit in-memory key-value mappings; nested tables suit flexible-size lists usable as SQL collections; VARRAYs suit bounded, ordered lists.** Understanding sparse vs. dense behavior, constructors, collection methods, and type scope helps prevent subscript errors. When handling many rows, BULK COLLECT and FORALL reduce context-switching overhead between PL/SQL and SQL engines, while still requiring batch-size control and explicit transaction management via COMMIT/ROLLBACK.
