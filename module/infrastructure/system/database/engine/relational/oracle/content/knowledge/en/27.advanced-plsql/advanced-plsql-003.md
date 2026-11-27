# FORALL, INDICES OF, and VALUES OF with Sparse Collections

In PL/SQL, when you need to execute the same DML statement for many elements of a collection, a regular FOR loop can generate many context switches between the PL/SQL engine and the SQL engine. FORALL solves this with bulk binding: PL/SQL bundles values from collections and sends the DML executions in bulk.

A challenge arises when a collection no longer has contiguous indices. A nested table can become sparse after DELETE; an associative array can have arbitrary keys from the start. In such cases, FORALL with a fixed range from 1 to COUNT can access a non-existent index. Oracle provides two ways to specify the exact set of indices to run:

- **INDICES OF**: iterates over the existing indices in a collection.
- **VALUES OF**: iterates over the index values stored in another collection, often called an index collection or pointer collection.

This lesson explains FORALL, dense and sparse collections, how to choose INDICES OF or VALUES OF, BETWEEN bounds, error handling with SAVE EXCEPTIONS, reading SQL%BULK_EXCEPTIONS and SQL%BULK_ROWCOUNT, along with a runnable lab to observe the results.

Examples use Oracle Database 19c. The goal is to understand how collection indices map to each DML execution and how to keep data synchronized across collections.

## 1. Why Is FORALL Needed?

Suppose you need to increase stock quantities for multiple products. The straightforward approach is looping over each element and running UPDATE:

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF NUMBER;
    TYPE t_qty_list IS TABLE OF NUMBER;

    l_product_ids t_id_list := t_id_list(101, 102, 103);
    l_increments  t_qty_list := t_qty_list(5, 3, 8);
BEGIN
    FOR i IN 1 .. l_product_ids.COUNT LOOP
        UPDATE inventory
        SET quantity = quantity + l_increments(i)
        WHERE product_id = l_product_ids(i);
    END LOOP;
END;
/
~~~

The loop above makes multiple SQL calls from PL/SQL. With large data volumes, context switch overhead can become significant.

FORALL lets you bulk-bind collection values to a single DML statement:

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF NUMBER;
    TYPE t_qty_list IS TABLE OF NUMBER;

    l_product_ids t_id_list := t_id_list(101, 102, 103);
    l_increments  t_qty_list := t_qty_list(5, 3, 8);
BEGIN
    FORALL i IN 1 .. l_product_ids.COUNT
        UPDATE inventory
        SET quantity = quantity + l_increments(i)
        WHERE product_id = l_product_ids(i);
END;
/
~~~

FORALL still executes multiple logical DML operations, each using one collection element. The difference is that Oracle handles the bindings in bulk, reducing switches between the PL/SQL and SQL engines.

### 1.1. FORALL Is Not a General-Purpose PL/SQL Loop

FORALL applies only to a single DML statement or a single dynamic SQL statement per FORALL. It is not a replacement for a FOR LOOP containing multiple PL/SQL statements, complex IF blocks, or arbitrary procedure calls.

Do not write:

~~~sql
FORALL i IN 1 .. l_ids.COUNT
BEGIN
    validate_item(l_ids(i));
    UPDATE inventory SET quantity = quantity + 1
    WHERE product_id = l_ids(i);
END;
~~~

Validate and prepare data first, then use FORALL for the DML statement. If each element requires different procedural business logic, a regular loop may be more appropriate.

### 1.2. General Syntax

FORALL supports three ways to specify indices:

~~~sql
FORALL index_name IN lower_bound .. upper_bound
    dml_statement;

FORALL index_name IN INDICES OF collection_name
    dml_statement;

FORALL index_name IN VALUES OF index_collection
    dml_statement;
~~~

INDICES OF and VALUES OF can include BETWEEN to restrict the range of indices considered:

~~~sql
FORALL i IN INDICES OF l_values BETWEEN 2 AND 10
    UPDATE ...;

FORALL i IN VALUES OF l_indexes BETWEEN 1 AND 5
    UPDATE ...;
~~~

FORALL does not automatically COMMIT. The DML remains part of the session's current transaction; the caller decides whether to COMMIT or ROLLBACK.

## 2. Dense and Sparse Collections

A dense collection has contiguous elements across its index range. A sparse collection has at least one missing index between existing indices, or has indices that do not start at 1.

### 2.1. Dense Collection

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_values t_numbers := t_numbers(10, 20, 30, 40);
BEGIN
    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_values.COUNT);
    DBMS_OUTPUT.PUT_LINE('FIRST=' || l_values.FIRST);
    DBMS_OUTPUT.PUT_LINE('LAST=' || l_values.LAST);
END;
/
~~~

The collection has four elements at indices 1, 2, 3, and 4. COUNT is 4, FIRST is 1, and LAST is 4.

### 2.2. Creating a Sparse Nested Table with DELETE

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_values t_numbers := t_numbers(10, 20, 30, 40, 50);
BEGIN
    l_values.DELETE(2);
    l_values.DELETE(4);

    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_values.COUNT);
    DBMS_OUTPUT.PUT_LINE('FIRST=' || l_values.FIRST);
    DBMS_OUTPUT.PUT_LINE('LAST=' || l_values.LAST);
    DBMS_OUTPUT.PUT_LINE('EXISTS(2)=' || CASE
        WHEN l_values.EXISTS(2) THEN 'Y' ELSE 'N' END);
END;
/
~~~

After DELETE, the remaining indices are 1, 3, and 5. COUNT is 3 while LAST is 5. COUNT is the number of existing elements, not the highest index.

### 2.3. Associative Arrays Can Also Be Sparse

Associative arrays do not require contiguous indices:

~~~sql
DECLARE
    TYPE t_map IS TABLE OF VARCHAR2(30)
        INDEX BY PLS_INTEGER;
    l_values t_map;
BEGIN
    l_values(2) := 'Two';
    l_values(10) := 'Ten';
    l_values(50) := 'Fifty';

    DBMS_OUTPUT.PUT_LINE(l_values.COUNT);
    DBMS_OUTPUT.PUT_LINE(l_values.FIRST);
    DBMS_OUTPUT.PUT_LINE(l_values.LAST);
END;
/
~~~

Indices 2, 10, and 50 are all valid. The range 1 .. COUNT would be 1 .. 3, which does not match the actual indices.

### 2.4. Why Can 1 .. COUNT Fail?

Suppose a nested table has indices 1, 3, and 5. COUNT is 3, so:

~~~sql
FORALL i IN 1 .. l_values.COUNT
    UPDATE target_table
    SET value = l_values(i)
    WHERE id = i;
~~~

FORALL will reference l_values(1), l_values(2), and l_values(3). Index 2 was deleted, so the operation can raise a non-existent collection subscript error. Meanwhile, index 5 is skipped.

Similarly, using FIRST .. LAST does not solve gaps in the middle. You must select either the exact existing indices using INDICES OF or a specific list of indices using VALUES OF.

## 3. FORALL with a Fixed Index Range

Simple syntax:

~~~sql
FORALL i IN 1 .. l_ids.COUNT
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

This works when:

- The collection is initialized densely.
- Indices start at 1 and run contiguously up to COUNT.
- All collections referenced in the DML share the same index set.

If a collection has indices starting at another number or has gaps, do not use 1 .. COUNT. Also do not use FIRST .. LAST if indices are missing in between.

### 3.1. Collections Must Have Synchronized Indices

A single DML statement can reference multiple collections:

~~~sql
FORALL i IN 1 .. l_ids.COUNT
    INSERT INTO order_lines (order_id, product_id, quantity)
    VALUES (l_order_ids(i), l_ids(i), l_quantities(i));
~~~

The collections l_order_ids, l_ids, and l_quantities must all have elements at every index used by FORALL. If one collection is missing an index, that reference can fail even if the driving collection is complete.

## 4. INDICES OF: Iterating Over Existing Indices

INDICES OF tells Oracle to iterate over the existing indices of a collection. This is the natural choice when data is already in a sparse collection and other referenced collections use the same indices.

### 4.1. Syntax

~~~sql
FORALL i IN INDICES OF l_ids
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

Oracle only uses indices that exist in l_ids. If l_ids has indices 1, 3, and 5, the DML executions run with i equal to 1, 3, and 5.

### 4.2. Sparse Nested Table Example

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF NUMBER;
    TYPE t_delta_list IS TABLE OF NUMBER;

    l_ids   t_id_list := t_id_list(101, 102, 103, 104, 105);
    l_delta t_delta_list := t_delta_list(5, 10, 15, 20, 25);
BEGIN
    l_ids.DELETE(2);
    l_delta.DELETE(2);
    l_ids.DELETE(4);
    l_delta.DELETE(4);

    FORALL i IN INDICES OF l_ids
        UPDATE inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);
END;
/
~~~

Only indices 1, 3, and 5 are processed. Both l_ids and l_delta must still have elements at those indices.

### 4.3. Driving Collection and Referenced Collections

The collection in INDICES OF determines which indices are iterated. It can be a collection referenced in the DML statement or another collection sharing the same index set. For example:

~~~sql
FORALL i IN INDICES OF l_active_flags
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

Here l_active_flags decides which indices to run. Because the DML accesses l_delta(i) and l_ids(i), those two collections must have corresponding indices for every i provided by l_active_flags.

Do not check COUNT alone. Check EXISTS(i) or build parallel collections in the same routine to keep indices synchronized.

### 4.4. INDICES OF with BETWEEN

BETWEEN restricts the index values of the driving collection:

~~~sql
FORALL i IN INDICES OF l_ids BETWEEN 3 AND 8
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

If l_ids has indices 1, 3, 5, 9, only indices 3 and 5 are evaluated. The numbers 3 and 8 are index bounds, not element ordinals and not product_id values.

BETWEEN is useful for splitting a collection into processing ranges, but the lower/upper bounds must be understood as actual indices. For an associative array with sparse keys, only existing keys within the range are selected.

### 4.5. When to Use INDICES OF?

- Data collection became sparse after DELETE.
- Associative array uses non-contiguous PLS_INTEGER keys.
- You want to process every existing element in a collection.
- You have a control collection holding valid indices for parallel data collections.
- You want to restrict processing to an index range using BETWEEN.

INDICES OF does not sort data by business value. It only picks existing indices; if business ordering matters, design explicit keys/sorting separately.

## 5. VALUES OF: Using a Collection Containing a List of Indices

VALUES OF is useful when you want to pick a subset or a specific processing order without deleting elements from the data collection. A second collection stores the indices to use; the values inside this collection serve as indices to access the data collections.

### 5.1. Syntax

~~~sql
FORALL i IN VALUES OF l_selected_indexes
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

l_selected_indexes is a collection containing index values. For example, if it holds 5, 2, and 9, the DML executions run with i equal to 5, 2, and 9. The collections l_ids and l_delta must have elements at those respective indices.

### 5.2. Example Using a Pointer Collection

~~~sql
DECLARE
    TYPE t_id_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_delta_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_index_list IS TABLE OF PLS_INTEGER;

    l_ids       t_id_map;
    l_delta     t_delta_map;
    l_selected  t_index_list := t_index_list(5, 2);
BEGIN
    l_ids(2) := 102;
    l_delta(2) := 10;

    l_ids(5) := 105;
    l_delta(5) := 25;

    FORALL i IN VALUES OF l_selected
        UPDATE inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);
END;
/
~~~

Only indices 5 and 2 are processed, following the list in l_selected. Other elements in l_ids and l_delta are untouched.

### 5.3. VALUES OF with BETWEEN

~~~sql
FORALL i IN VALUES OF l_selected BETWEEN 2 AND 4
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

With VALUES OF, BETWEEN restricts the indices of the driving collection l_selected itself, not the index values stored inside it. For instance, if l_selected has elements at indices 1, 2, 3, 4, BETWEEN 2 AND 4 selects l_selected(2), l_selected(3), and l_selected(4), then uses the value inside each element as index i for l_ids/l_delta.

Distinguish the two levels of indexing:

1. Index of the pointer collection, e.g., l_selected(2).
2. Value stored inside the pointer collection, e.g., l_selected(2) = 5; the value 5 becomes i in the DML.

This is the easiest point to confuse when combining VALUES OF and BETWEEN.

### 5.4. VALUES OF Can Represent a Subset

Suppose l_ids and l_delta hold 100 elements, yet only 3 elements need updating. You can create a pointer collection containing just those three indices without needing to DELETE the remaining elements from the data collections.

~~~sql
TYPE t_index_list IS TABLE OF PLS_INTEGER;
l_selected t_index_list := t_index_list(7, 22, 81);

FORALL i IN VALUES OF l_selected
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

This separates source data from selection policy. You can build l_selected from validation results or business categorization before running DML.

### 5.5. Duplicate Values in a Pointer Collection

If the pointer collection contains the same index multiple times, FORALL can execute DML multiple times for that index:

~~~sql
TYPE t_index_list IS TABLE OF PLS_INTEGER;
l_selected t_index_list := t_index_list(5, 2, 5);
~~~

Index 5 appears twice. If the DML adds a quantity, that element may be updated twice. Keep duplicates only when business requirements intend it; otherwise deduplicate before FORALL.

### 5.6. Requirements for the Pointer Collection

- The pointer collection must be an integer-indexed collection suitable for FORALL.
- Every stored index value must exist in every collection accessed by the DML at that index.
- Do not confuse the pointer collection's index with the pointer value.
- If the pointer collection has deleted elements, only existing elements are used; design and verify the index set carefully.
- For ordered processing, construct the pointer list in the desired order and verify results by business key.

## 6. Comparing Fixed Range, INDICES OF, and VALUES OF

| Syntax | Set of indices processed | Suitable when |
| --- | --- | --- |
| 1 .. COUNT | Numbers from 1 to COUNT | Dense collection starting at 1 |
| FIRST .. LAST | Every integer from FIRST to LAST | Only when the collection is dense across that range |
| INDICES OF data | Existing indices in collection data | Processing a sparse collection |
| INDICES OF control BETWEEN a AND b | Existing indices of collection control within a..b | Splitting processing by index range |
| VALUES OF pointers | Index values stored in the pointer collection | Choosing a subset or custom index order |
| VALUES OF pointers BETWEEN a AND b | Pointer values at pointer-collection indices within a..b | Selecting a slice of the pointer list |

Selection rules:

- Use a fixed range when you are certain the collection is dense.
- Use INDICES OF when you want to process all existing indices of a sparse collection.
- Use VALUES OF when you want a separate index list, possibly picking a subset or intentionally repeating indices.

## 7. FORALL with Multiple Collections and Parallel Data

A single DML statement often uses multiple collections, such as product ID, quantity, and warehouse ID. The collections must accurately map to the same logical element.

~~~sql
DECLARE
    TYPE t_number_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;

    l_product_ids t_number_map;
    l_quantities  t_number_map;
    l_warehouses  t_number_map;
BEGIN
    l_product_ids(2) := 101;
    l_quantities(2) := 5;
    l_warehouses(2) := 1;

    l_product_ids(7) := 102;
    l_quantities(7) := 3;
    l_warehouses(7) := 2;

    FORALL i IN INDICES OF l_product_ids
        INSERT INTO inventory_movements (
            product_id,
            quantity,
            warehouse_id
        )
        VALUES (
            l_product_ids(i),
            l_quantities(i),
            l_warehouses(i)
        );
END;
/
~~~

Collection l_product_ids drives the index set. The other two collections must contain both indices 2 and 7. If l_quantities lacks index 7, the corresponding DML fails even though l_product_ids is valid.

### 7.1. Checking Synchronization Before DML

You can validate parallel collections before calling FORALL:

~~~sql
DECLARE
    i PLS_INTEGER;
BEGIN
    i := l_product_ids.FIRST;
    WHILE i IS NOT NULL LOOP
        IF NOT l_quantities.EXISTS(i)
           OR NOT l_warehouses.EXISTS(i)
        THEN
            RAISE_APPLICATION_ERROR(
                -20001,
                'Missing data for collection index ' || i
            );
        END IF;

        i := l_product_ids.NEXT(i);
    END LOOP;
END;
~~~

This snippet illustrates the principle; place it in the same block where the collections are declared. Early validation makes data errors easier to diagnose than letting FORALL fail on a hard-to-trace element.

### 7.2. Choosing the Driving Collection

The driving collection should have a clear role:

- INDICES OF l_product_ids if ID is the canonical collection and the others are parallel.
- INDICES OF l_valid_rows if you built a collection marking approved rows.
- VALUES OF l_selected_indexes if you need a separate selection list.

Never choose a driving collection simply because its COUNT matches other collections. Two collections with equal COUNT can still have different indices and be incompatible.

## 8. SAVE EXCEPTIONS and Per-Element Error Handling

By default, if a DML execution inside FORALL fails, Oracle stops processing and raises an exception. Any prior successful DML executions remain part of the current transaction and can be committed or rolled back by the caller.

If you want Oracle to continue the remaining DML executions and report errors afterward, use SAVE EXCEPTIONS.

### 8.1. Syntax

~~~sql
FORALL i IN INDICES OF l_ids SAVE EXCEPTIONS
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

When one or more DML executions fail, Oracle continues through the rest and then raises ORA-24381. Detailed errors are stored in SQL%BULK_EXCEPTIONS.

### 8.2. Declaring an Exception for ORA-24381

~~~sql
DECLARE
    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    NULL;
EXCEPTION
    WHEN e_bulk_errors THEN
        DBMS_OUTPUT.PUT_LINE('One or more FORALL iterations failed');
END;
/
~~~

### 8.3. Reading SQL%BULK_EXCEPTIONS

Each element in SQL%BULK_EXCEPTIONS contains:

- ERROR_INDEX: the index/iteration reported by Oracle as causing the error in FORALL.
- ERROR_CODE: the Oracle error code of the failed DML execution, without the minus sign.

Example:

~~~sql
EXCEPTION
    WHEN e_bulk_errors THEN
        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Error index=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', code=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE ||
                ', message=' ||
                SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
            );
        END LOOP;
~~~

SQL%BULK_EXCEPTIONS is a pseudo-collection provided by Oracle inside the exception handler. Use index j to iterate through the error list; do not confuse j with the data collection's index.

When using INDICES OF or VALUES OF, maintain a clear mapping from the iteration/error index to the element's business key. Do not assume ERROR_INDEX is always a product ID or always a sequential position in another collection. Verify the mapping behavior for your specific FORALL bounds form and Oracle version; in critical systems, you can store an iteration/index/key lookup table before running.

### 8.4. SQL%BULK_ROWCOUNT

SQL%BULK_ROWCOUNT provides the number of rows affected by each DML execution inside FORALL. SQL%ROWCOUNT is the total number of rows affected by the FORALL statement.

Example:

~~~sql
FORALL i IN INDICES OF l_ids
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);

DBMS_OUTPUT.PUT_LINE('Total affected rows=' || SQL%ROWCOUNT);
~~~

If you need to know whether each ID matched a row, read SQL%BULK_ROWCOUNT using the corresponding FORALL index/iteration and consult the Oracle documentation for the bounds form in use. A DML execution can succeed yet affect 0 rows; that is not a bulk exception.

## 9. Lab: Updating Sparse Collections with INDICES OF and VALUES OF

The lab below creates a small inventory table to observe which indices get selected. Run it in a dedicated practice schema.

### 9.1. Create the Table

~~~sql
CREATE TABLE lab_inventory (
    product_id NUMBER PRIMARY KEY,
    quantity   NUMBER NOT NULL,
    CONSTRAINT lab_inventory_qty_ck CHECK (quantity >= 0)
);

INSERT INTO lab_inventory VALUES (101, 100);
INSERT INTO lab_inventory VALUES (102, 100);
INSERT INTO lab_inventory VALUES (103, 100);
INSERT INTO lab_inventory VALUES (104, 100);
INSERT INTO lab_inventory VALUES (105, 100);
COMMIT;
~~~

### 9.2. Create a Sparse Collection and Run INDICES OF

~~~sql
DECLARE
    TYPE t_number_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_ids   t_number_map;
    l_delta t_number_map;
BEGIN
    l_ids(1) := 101;
    l_delta(1) := 5;

    l_ids(3) := 103;
    l_delta(3) := 15;

    l_ids(5) := 105;
    l_delta(5) := 25;

    FORALL i IN INDICES OF l_ids
        UPDATE lab_inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);

    DBMS_OUTPUT.PUT_LINE('Rows updated=' || SQL%ROWCOUNT);
END;
/

SELECT product_id, quantity
FROM lab_inventory
ORDER BY product_id;
~~~

Expected result: product 101 has 105, 103 has 115, 105 has 125; 102 and 104 remain 100. Indices 1, 3, and 5 are processed even though COUNT is only 3.

### 9.3. Using BETWEEN with INDICES OF

~~~sql
DECLARE
    TYPE t_number_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_ids   t_number_map;
    l_delta t_number_map;
BEGIN
    l_ids(1) := 101; l_delta(1) := 1;
    l_ids(3) := 103; l_delta(3) := 3;
    l_ids(5) := 105; l_delta(5) := 5;
    l_ids(9) := 104; l_delta(9) := 9;

    FORALL i IN INDICES OF l_ids BETWEEN 3 AND 8
        UPDATE lab_inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);
END;
/
~~~

Only indices 3 and 5 fall within 3..8, so only products 103 and 105 are updated. Indices 1 and 9 are skipped.

### 9.4. Using VALUES OF to Select a Subset

~~~sql
DECLARE
    TYPE t_number_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_index_list IS TABLE OF PLS_INTEGER;

    l_ids      t_number_map;
    l_delta    t_number_map;
    l_selected t_index_list := t_index_list(9, 2);
BEGIN
    l_ids(2) := 102; l_delta(2) := 20;
    l_ids(5) := 105; l_delta(5) := 50;
    l_ids(9) := 104; l_delta(9) := 90;

    FORALL i IN VALUES OF l_selected
        UPDATE lab_inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);
END;
/
~~~

The pointer collection holds values 9 and 2, so the DML uses l_ids(9)/l_delta(9) and then l_ids(2)/l_delta(2). Index 5 is not selected.

### 9.5. Using VALUES OF with BETWEEN

~~~sql
DECLARE
    TYPE t_number_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_index_list IS TABLE OF PLS_INTEGER;

    l_ids      t_number_map;
    l_delta    t_number_map;
    l_selected t_index_list := t_index_list(9, 2, 5, 1);
BEGIN
    l_ids(1) := 101; l_delta(1) := 1;
    l_ids(2) := 102; l_delta(2) := 2;
    l_ids(5) := 105; l_delta(5) := 5;
    l_ids(9) := 104; l_delta(9) := 9;

    FORALL i IN VALUES OF l_selected BETWEEN 2 AND 3
        UPDATE lab_inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);
END;
/
~~~

BETWEEN 2 AND 3 selects l_selected(2) and l_selected(3), which are pointer values 2 and 5. The DML affects products 102 and 105. It does not select pointer values 9 and 2 by comparing pointer values against 2..3.

## 10. Lab: SAVE EXCEPTIONS and Error Handling

Use the CHECK constraint on LAB_INVENTORY to create a controlled failing update. Product 102 has quantity 100; a large negative delta makes the new value negative and violates the constraint.

~~~sql
DECLARE
    TYPE t_number_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;

    l_ids   t_number_map;
    l_delta t_number_map;

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    l_ids(2) := 101;
    l_delta(2) := 10;

    l_ids(5) := 102;
    l_delta(5) := -1000;

    l_ids(9) := 103;
    l_delta(9) := 20;

    FORALL i IN INDICES OF l_ids SAVE EXCEPTIONS
        UPDATE lab_inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);

    DBMS_OUTPUT.PUT_LINE('All iterations succeeded');
EXCEPTION
    WHEN e_bulk_errors THEN
        DBMS_OUTPUT.PUT_LINE(
            'Bulk errors=' || SQL%BULK_EXCEPTIONS.COUNT
        );

        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Error index=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', error code=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE ||
                ', message=' ||
                SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
            );
        END LOOP;
END;
/
~~~

Oracle continues executing subsequent DML statements after an error thanks to SAVE EXCEPTIONS. In this example, updates for 101 and 103 can succeed; the update for 102 fails due to the CHECK constraint. Successful DML changes remain part of the current transaction. Inspect the data and then explicitly COMMIT or ROLLBACK as required by the lab.

~~~sql
SELECT product_id, quantity
FROM lab_inventory
ORDER BY product_id;
~~~

Do not automatically COMMIT just because FORALL continued past errors. SAVE EXCEPTIONS is an error-collection mechanism, not a transaction policy.

## 11. Combining with RETURNING BULK COLLECT INTO

A DML statement inside FORALL can use RETURNING BULK COLLECT INTO to gather values returned from affected rows.

Example:

~~~sql
DECLARE
    TYPE t_id_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_id_list IS TABLE OF NUMBER;

    l_ids t_id_map;
    l_deleted_ids t_id_list;
BEGIN
    l_ids(2) := 101;
    l_ids(5) := 103;

    FORALL i IN INDICES OF l_ids
        DELETE FROM lab_inventory
        WHERE product_id = l_ids(i)
        RETURNING product_id BULK COLLECT INTO l_deleted_ids;

    FOR j IN 1 .. l_deleted_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE('Deleted product=' || l_deleted_ids(j));
    END LOOP;
END;
/
~~~

The collection receiving RETURNING results is populated from the rows actually affected. The number of returned elements does not necessarily equal the FORALL iteration count if an iteration affects 0 rows or multiple rows. Iterate over the returned collection itself rather than inferring its positions from input indices.

## 12. FORALL and Transactions

FORALL optimizes how DML is sent; it does not create an independent transaction per element.

- There is no automatic COMMIT after each iteration.
- Without SAVE EXCEPTIONS, a DML error stops FORALL; preceding successful DML executions remain uncommitted changes in the current transaction.
- With SAVE EXCEPTIONS, Oracle continues the remaining iterations and raises ORA-24381 afterward; successful DML executions remain uncommitted.
- The caller can COMMIT the successful elements or ROLLBACK the entire transaction.
- Do not invoke COMMIT inside a batch-processing loop just to avoid collection errors; doing so alters business atomicity.

If each batch needs its own transaction, split batches explicitly at the orchestration layer and define retry/idempotency policies. Do not confuse bulk binding with transaction batching.

## 13. Performance and Practical Limits

FORALL reduces context switches, but it does not guarantee every workload is faster in every situation. Performance also depends on row count, data size, indexes, constraints, triggers, redo/undo, and execution plans.

### 13.1. Prepare Data First

Be sure to:

- Validate input data before FORALL.
- Normalize collections and indices.
- Use bind collections rather than concatenating values into dynamic SQL.
- Select the exact set of indices to run.
- Fetch only the columns needed.

### 13.2. Keep Collections Synchronized

If a DML statement uses l_ids(i), l_qty(i), and l_wh_id(i), every collection must have an element at each selected index i. If collections can be deleted independently, check EXISTS before executing.

### 13.3. Batch Size

When loading data from a query, BULK COLLECT ... LIMIT helps bound memory:

~~~sql
FETCH c_source BULK COLLECT INTO l_rows LIMIT 500;
~~~

You can then run FORALL on each batch. Choose LIMIT based on record size, PGA memory, and measured performance.

### 13.4. Do Not Use FORALL to Mask Poor DML Design

If a single set-based UPDATE can replace thousands of collection-driven UPDATEs, the set-based SQL statement is usually simpler and more efficient. FORALL is suited when applying DML per input element that cannot be cleanly expressed in a single set-based SQL statement.

## 14. Common Errors

| Symptom | Cause | Solution |
| --- | --- | --- |
| FORALL 1..COUNT accesses missing index | Sparse collection; COUNT is not the highest index | Use INDICES OF or VALUES OF |
| FORALL FIRST..LAST still fails | Gaps exist between FIRST and LAST | Use INDICES OF |
| DML fails even though driving collection is valid | Another collection in DML is missing the same index | Synchronize indices or check EXISTS |
| VALUES OF accesses wrong element | Confusing pointer collection index with pointer value | Track both indexing levels |
| BETWEEN selects wrong elements | Interpreting BETWEEN as filtering pointer values | BETWEEN filters indices of the driving collection |
| One row updated multiple times | Pointer collection has duplicate indices | Deduplicate or confirm repetition is intentional |
| ORA-24381 | One or more iterations failed with SAVE EXCEPTIONS | Inspect SQL%BULK_EXCEPTIONS |
| Missed errors by checking only SQL%ROWCOUNT | Total row count does not list individual failures | Iterate SQL%BULK_EXCEPTIONS and SQL%BULK_ROWCOUNT |
| Confusing ERROR_INDEX with business key | ERROR_INDEX locates the failed FORALL iteration | Maintain mapping to business keys |
| Successful data remains after error | SAVE EXCEPTIONS does not auto-rollback succeeded iterations | Choose COMMIT/ROLLBACK per policy |
| FORALL slower than expected | Set-based DML may fit better, or triggers/indexes are costly | Measure and compare execution paths |

## 15. Workflow for Choosing an Iteration Method

Before writing FORALL, determine:

1. Is the data collection dense?
2. If sparse, what are the actual existing indices?
3. Do all collections referenced in the DML share the same index set?
4. Do you want to process every element or only a subset?
5. Do you need a custom order or intentional duplicate index execution?
6. Should processing stop on the first error or continue with SAVE EXCEPTIONS?
7. After an error, should successful changes be committed or the entire transaction rolled back?

Selection:

- Dense 1..COUNT: use a fixed range.
- Sparse and need all existing elements: use INDICES OF.
- Sparse and only selecting certain indices or needing a custom order: use VALUES OF.
- Need to restrict by index of the driving collection: use BETWEEN.
- Need to collect per-iteration errors: add SAVE EXCEPTIONS and inspect SQL%BULK_EXCEPTIONS.

## 16. Practice Exercises

Use LAB_INVENTORY from Section 9.

### Exercise 1 — Dense and Sparse

Create a nested table with 6 elements, DELETE indices 2 and 5. Print COUNT, FIRST, LAST, and EXISTS for each index. Explain why COUNT cannot be used in place of the highest index.

### Exercise 2 — Failure of 1..COUNT

Try FORALL i IN 1..COUNT on the collection created in Exercise 1. Observe the index error. Fix it using INDICES OF.

### Exercise 3 — INDICES OF

Create two associative arrays l_ids and l_delta with the same indices 2, 7, and 20. Use INDICES OF l_ids to update inventory. Then delete index 7 from one collection and observe the error caused by desynchronized collections.

### Exercise 4 — BETWEEN

Create a collection with indices 1, 3, 5, 9, and 12. Use INDICES OF ... BETWEEN 3 AND 9. Record which indices execute.

### Exercise 5 — VALUES OF

Create a pointer collection containing values 12, 3, and 9. Use VALUES OF to select exactly those three elements from the data collection. Add a non-existent pointer value and observe the error.

### Exercise 6 — VALUES OF and BETWEEN

Create a pointer collection with indices 1..5 and values 12, 3, 9, 1, 5 respectively. Use VALUES OF ... BETWEEN 2 AND 4. Record which pointer-collection indices are evaluated and which pointer values are used in the DML.

### Exercise 7 — SAVE EXCEPTIONS

Use the CHECK constraint quantity >= 0. Build a batch with both valid deltas and a delta making quantity negative. Use SAVE EXCEPTIONS, print ERROR_INDEX, ERROR_CODE, and SQLERRM. Identify the corresponding business key.

### Exercise 8 — Set-Based DML vs. FORALL

Write the same update requirement two ways: a single set-based UPDATE and FORALL with collections. Measure execution time on a larger lab data set, comparing complexity and results.

## 17. Clean Up Lab Data

Run only in the lab schema you created, after finishing the exercises:

~~~sql
DROP TABLE lab_inventory PURGE;
~~~

If you created additional tables or objects for the exercises, drop only your own lab objects. Never run cleanup commands against business data.

## Summary

FORALL uses bulk binding to execute a single DML statement across many collection elements, reducing switches between the PL/SQL and SQL engines. The range 1..COUNT is safe only when the collection is dense and indexed 1 through COUNT. For sparse collections, INDICES OF selects existing indices; VALUES OF uses values stored in a pointer collection as indices into the data collections. BETWEEN restricts indices of the driving collection rather than filtering pointer values directly.

When a DML statement references multiple collections, every collection must have elements at each selected index. SAVE EXCEPTIONS lets execution continue past errors and raises ORA-24381; SQL%BULK_EXCEPTIONS provides error positions and error codes, while SQL%BULK_ROWCOUNT reveals affected row counts per iteration. FORALL does not auto-commit: after handling errors, the caller must decide whether to commit successful portions or roll back the transaction. Maintain mappings from indices to business keys, validate parallel collections, and use duplicate VALUES OF entries only when repeated execution is intentional.

## Oracle Reference Documentation

- [Oracle Database PL/SQL Language Reference — FORALL Statement (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/FORALL-statement.html) — bounds syntax, INDICES OF, VALUES OF, and SAVE EXCEPTIONS.
- [Oracle Database PL/SQL Language Reference — Handling FORALL Exceptions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/bulk-sql-and-bulk-binding.html) — bulk exceptions and error handling.
- [Oracle Database PL/SQL Language Reference — Collection Methods (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/collection-methods.html) — COUNT, FIRST, LAST, NEXT, EXISTS, and DELETE.
- [Oracle Database PL/SQL Language Reference — Bulk SQL and Bulk Binding (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/bulk-sql-and-bulk-binding.html) — BULK COLLECT, FORALL, and bulk binding.
- [Oracle Database PL/SQL Language Reference — Implicit Cursor Attribute (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/implicit-cursor-attribute.html) — SQL%ROWCOUNT and SQL%BULK_ROWCOUNT.

When deploying on an Oracle release other than 19c, consult the PL/SQL Language Reference for that exact version, especially for VALUES OF/BETWEEN syntax, ERROR_INDEX interpretation, collection limits, and SAVE EXCEPTIONS behavior.
