# Collection Methods, Sparse Indices, and Uninitialized Elements in PL/SQL

A PL/SQL collection is a data structure used to store multiple elements of the same type in a single variable. Collections appear in batch processing, BULK COLLECT, FORALL, data exchange between procedures, and in-database algorithms. When working with collections, element indices are not always contiguous from 1 to COUNT.

A collection can have elements removed with DELETE, missing indices, or elements that have been created but still hold NULL values. Additionally, for nested tables and varrays, a collection variable can be in an **atomically null** (uninitialized) state. These states are distinct and lead to different behaviors when reading elements or calling collection methods.

This lesson covers:

- The three collection types: associative array, nested table, and varray.
- The methods COUNT, FIRST, LAST, PRIOR, NEXT, EXISTS, and LIMIT.
- The methods DELETE, EXTEND, and TRIM.
- Differences among a null collection, an empty collection, a NULL element, and a non-existent index.
- How to traverse sparse collections safely.
- Common exceptions when accessing elements.
- Applications in BULK COLLECT, FORALL, and batch data processing.

## 1. Collections in PL/SQL

A collection is a group of elements of the same type. Each element is accessed via a subscript (index or key). Oracle PL/SQL has three main collection types:

| Type | Declaration | Characteristics |
|---|---|---|
| Associative array | TABLE OF ... INDEX BY | Key-based lookup array; can use integer or string keys; no constructor needed |
| Nested table | TABLE OF ... | Resizable collection; can become sparse after DELETE |
| VARRAY | VARRAY(n) OF ... | Maximum limit of n elements; elements are always contiguous from 1 to COUNT |

Each type supports a different set of methods. You cannot call EXTEND on an associative array, nor can you use DELETE to remove an individual element from a varray.

## 2. Declaring the Three Collection Types

### 2.1 Associative Array

An associative array (also called an index-by table) uses keys to look up elements. Example with PLS_INTEGER keys:

~~~sql
DECLARE
    TYPE t_score_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_scores t_score_map;
BEGIN
    l_scores(10) := 85;
    l_scores(20) := 92;
    l_scores(100) := 77;

    DBMS_OUTPUT.PUT_LINE(l_scores(20));
END;
/
~~~

An associative array starts out empty upon declaration. No constructor call is needed to initialize it, and there is no collection constructor as with nested tables or varrays. Keys can be sparse from the outset: 10, 20, and 100 do not need to be consecutive.

Associative arrays can also use string keys:

~~~sql
DECLARE
    TYPE t_price_map IS TABLE OF NUMBER INDEX BY VARCHAR2(30);
    l_prices t_price_map;
BEGIN
    l_prices('BOOK') := 120000;
    l_prices('PEN')  := 5000;

    DBMS_OUTPUT.PUT_LINE(l_prices('BOOK'));
END;
/
~~~

With string keys, the order of FIRST, LAST, PRIOR, and NEXT depends on the session's string sorting rules (NLS_SORT/NLS_COMP). Associative arrays are not insertion-ordered structures; if business logic requires a specific order, store an explicit ordering column or use another collection.

### 2.2 Nested Table

A nested table is declared using TABLE OF:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30);
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_numbers(1));
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT);
END;
/
~~~

The constructor t_numbers(10, 20, 30) creates three elements at indices 1, 2, 3. A nested table can grow and can become sparse if one or more elements are removed with DELETE.

An uninitialized nested table:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers;
BEGIN
    -- l_numbers is atomically null.
    l_numbers := t_numbers();
    -- Now the collection is initialized and empty.
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT);
END;
/
~~~

The empty constructor t_numbers() creates an initialized collection with no elements yet.

### 2.3 VARRAY

VARRAY declares a maximum element limit:

~~~sql
DECLARE
    TYPE t_tags IS VARRAY(5) OF VARCHAR2(30);
    l_tags t_tags := t_tags('NEW', 'PAID');
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_tags.COUNT);
    DBMS_OUTPUT.PUT_LINE(l_tags.LIMIT);
END;
/
~~~

The VARRAY in this example holds at most 5 elements and currently has 2 elements. VARRAY is always dense (contiguous): if COUNT = 2, the existing indices are 1 and 2. You cannot DELETE an individual element in the middle to leave a gap.

### 2.4 Initialization and Empty State

| State | Nested Table / VARRAY | Associative Array |
|---|---|---|
| Newly declared variable | Atomically null | Empty, immediately usable |
| Calling empty constructor | Allowed: type_name() | No constructor |
| COUNT when initialized but empty | 0 | 0 |
| FIRST and LAST when empty | NULL | NULL |
| Can use EXISTS to check | Yes | Yes |

For nested tables and varrays, declaring a variable without assigning a constructor or another value leaves the collection atomically null. Calling methods such as COUNT, FIRST, LAST, LIMIT, PRIOR, NEXT, DELETE, EXTEND, and TRIM on a null collection raises COLLECTION_IS_NULL. EXISTS is the exception: it can be called on an atomically null collection and returns FALSE.

## 3. Distinguishing the Four States of a Collection and Its Elements

This is the most important part for avoiding runtime errors.

### 3.1 Atomically Null Collection

An uninitialized collection variable:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers;
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT);
END;
/
~~~

The snippet above raises COLLECTION_IS_NULL because COUNT is called on an atomically null collection.

You can check EXISTS:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers;
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        CASE WHEN l_numbers.EXISTS(1) THEN 'YES' ELSE 'NO' END
    );
END;
/
~~~

EXISTS(1) returns FALSE; calling this method does not initialize the collection.

### 3.2 Initialized but Empty Collection

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers();
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 0
    DBMS_OUTPUT.PUT_LINE(l_numbers.FIRST); -- NULL
    DBMS_OUTPUT.PUT_LINE(l_numbers.LAST);  -- NULL
END;
/
~~~

The collection exists but has no elements yet. COUNT is valid and equals 0.

### 3.3 Element Exists with a NULL Value

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, NULL, 30);
BEGIN
    IF l_numbers.EXISTS(2) THEN
        DBMS_OUTPUT.PUT_LINE('Element 2 exists');
    END IF;

    IF l_numbers(2) IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Element 2 has NULL value');
    END IF;
END;
/
~~~

EXISTS(2) returns TRUE because element 2 exists. The value of that element is NULL. This is not a missing element.

### 3.4 Non-Existent Index or Deleted Element

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30);
BEGIN
    l_numbers.DELETE(2);

    DBMS_OUTPUT.PUT_LINE(l_numbers.EXISTS(2)); -- FALSE
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT);     -- 2
END;
/
~~~

After DELETE(2), the element at index 2 no longer exists. COUNT decreases, but the collection does not shift element 3 down to index 2. The nested table becomes sparse.

### 3.5 Comparison Table

| State | EXISTS(i) | Reading collection(i) | Meaning |
|---|---|---|---|
| Atomically null collection | FALSE | Calling methods/reading elements raises COLLECTION_IS_NULL | Collection not yet initialized |
| Initialized empty collection | FALSE for all i | No elements to read | Valid collection, COUNT = 0 |
| Element exists, value is NULL | TRUE | Returns NULL | Slot exists, no business value yet |
| Element deleted / key absent | FALSE | Can raise NO_DATA_FOUND or subscript error depending on type and bounds | Slot/key does not exist |

Do not check for a NULL value to infer whether an element exists. Use EXISTS to verify existence first, then read the value.

## 4. Core Collection Methods

Methods provide ways to inspect element counts, bounds, and existing indices.

| Method | Meaning |
|---|---|
| COUNT | Number of currently existing elements |
| FIRST | Lowest existing index; NULL if collection is empty |
| LAST | Highest existing index; NULL if collection is empty |
| PRIOR(n) | Existing index immediately preceding n |
| NEXT(n) | Existing index immediately following n |
| EXISTS(n) | TRUE if element at n exists |
| LIMIT | Maximum limit; populated for VARRAY, NULL for nested table and associative array |

### 4.1 COUNT

COUNT returns the number of currently existing elements, not the highest index.

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30, 40);
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 4

    l_numbers.DELETE(2);

    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 3
    DBMS_OUTPUT.PUT_LINE(l_numbers.LAST);  -- 4
END;
/
~~~

After deleting element 2, COUNT = 3 while LAST = 4. Do not use COUNT as the upper index in a sparse collection.

### 4.2 FIRST and LAST

FIRST returns the lowest existing index; LAST returns the highest existing index. If the collection is initialized and empty, both return NULL.

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30, 40, 50);
BEGIN
    l_numbers.DELETE(1);
    l_numbers.DELETE(4);

    DBMS_OUTPUT.PUT_LINE(l_numbers.FIRST); -- 2
    DBMS_OUTPUT.PUT_LINE(l_numbers.LAST);  -- 5
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 3
END;
/
~~~

The remaining indices are 2, 3, and 5. FIRST and LAST do not guarantee that every index between them has an element.

### 4.3 PRIOR and NEXT

PRIOR(n) returns the existing index before n; NEXT(n) returns the existing index after n. They skip deleted indices:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30, 40, 50);
BEGIN
    l_numbers.DELETE(2);
    l_numbers.DELETE(4);

    DBMS_OUTPUT.PUT_LINE(l_numbers.PRIOR(5)); -- 3
    DBMS_OUTPUT.PUT_LINE(l_numbers.NEXT(1));  -- 3
    DBMS_OUTPUT.PUT_LINE(l_numbers.NEXT(3));  -- 5
END;
/
~~~

If there is no preceding or following index, PRIOR/NEXT returns NULL. This is the safe way to step through a sparse collection.

### 4.4 EXISTS

EXISTS(n) checks whether an element exists:

~~~sql
IF l_numbers.EXISTS(3) THEN
    DBMS_OUTPUT.PUT_LINE(l_numbers(3));
END IF;
~~~

EXISTS returns FALSE if the element was never created, was deleted, or the index is outside the collection. It still returns TRUE if the element exists with a NULL value.

EXISTS is the only method that can be called on an atomically null collection. That is useful when a procedure receives a collection that the caller may not have initialized.

### 4.5 LIMIT

LIMIT returns the maximum number of elements for a VARRAY:

~~~sql
DECLARE
    TYPE t_tags IS VARRAY(10) OF VARCHAR2(20);
    l_tags t_tags := t_tags('A', 'B');
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_tags.COUNT); -- 2
    DBMS_OUTPUT.PUT_LINE(l_tags.LIMIT); -- 10
END;
/
~~~

For nested tables and associative arrays, LIMIT returns NULL because neither type has a maximum limit declared in its collection type syntax.

## 5. Methods That Modify Collections

DELETE, EXTEND, and TRIM are not uniformly supported across all three collection types.

| Method | Associative Array | Nested Table | VARRAY |
|---|---:|---:|---:|
| DELETE | Yes | Yes | No |
| EXTEND | No | Yes | Yes |
| TRIM | No | Yes | Yes |

### 5.1 DELETE

DELETE removes elements:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30, 40, 50);
BEGIN
    l_numbers.DELETE(3);

    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 4
    DBMS_OUTPUT.PUT_LINE(l_numbers.EXISTS(3)); -- FALSE
END;
/
~~~

Common forms:

- DELETE: deletes all elements.
- DELETE(n): deletes the element at index n.
- DELETE(m, n): deletes elements in the index range m through n.

DELETE on a nested table can leave gaps. DELETE on an associative array removes keys from the map. VARRAY does not support DELETE; if you need to remove elements in a varray, rebuild the collection (e.g., create a new varray with only the kept elements) or choose a nested table if business logic requires sparse deletions.

### 5.2 EXTEND

EXTEND appends elements to the end of a nested table or varray:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20);
BEGIN
    l_numbers.EXTEND;
    l_numbers(3) := 30;

    l_numbers.EXTEND(2);
    l_numbers(4) := 40;
    l_numbers(5) := 50;

    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 5
END;
/
~~~

Forms:

- EXTEND: appends one new element with value NULL.
- EXTEND(n): appends n new elements with value NULL.
- EXTEND(n, i): appends n copies of the element at index i.

EXTEND(n, i) example:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20);
BEGIN
    l_numbers.EXTEND(2, 1);

    DBMS_OUTPUT.PUT_LINE(l_numbers(3)); -- 10
    DBMS_OUTPUT.PUT_LINE(l_numbers(4)); -- 10
END;
/
~~~

EXTEND cannot be used on associative arrays. You cannot EXTEND an atomically null nested table or varray; initialize it first with a constructor or valid assignment. A VARRAY cannot exceed LIMIT.

A newly EXTENDed element exists with an initial value of NULL. Therefore EXISTS on the new index returns TRUE, while checking its value with IS NULL also returns TRUE.

### 5.3 TRIM

TRIM removes one or more elements from the end of a nested table or varray:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30, 40);
BEGIN
    l_numbers.TRIM;
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 3
    DBMS_OUTPUT.PUT_LINE(l_numbers.LAST);  -- 3

    l_numbers.TRIM(2);
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 1
END;
/
~~~

TRIM cannot be used on associative arrays. TRIM(2) removes the last two elements from the internal end of the collection.

### 5.4 Caution When Mixing DELETE and TRIM

DELETE and TRIM view deleted elements differently:

- DELETE marks an element as non-existent, potentially leaving a gap in a nested table.
- TRIM operates on the end of the collection by internal size; it can remove trailing positions that were already deleted via DELETE.

Consequently, mixing DELETE and TRIM on the same nested table can make remaining indices hard to predict. If your algorithm needs sparse indices, prefer DELETE and FIRST/NEXT. If your algorithm manages a contiguous sequence like a stack, use EXTEND/TRIM by clear convention. Do not assume TRIM is equivalent to DELETE(LAST).

## 6. Sparse Collections

A sparse collection is one whose existing element indices are non-contiguous. Nested tables can become sparse after DELETE; associative arrays are naturally sparse because keys can be assigned arbitrarily. VARRAYs are always dense.

### 6.1 Sparse Nested Table Example

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(30);
    l_names t_names := t_names(
        'An', 'Binh', 'Chi', 'Dung', 'Hoa'
    );
BEGIN
    l_names.DELETE(2);
    l_names.DELETE(4);

    DBMS_OUTPUT.PUT_LINE('COUNT = ' || l_names.COUNT);
    DBMS_OUTPUT.PUT_LINE('FIRST = ' || l_names.FIRST);
    DBMS_OUTPUT.PUT_LINE('LAST  = ' || l_names.LAST);
END;
/
~~~

Index state:

| Index | Element | Status |
|---:|---|---|
| 1 | An | Exists |
| 2 | Binh | Deleted |
| 3 | Chi | Exists |
| 4 | Dung | Deleted |
| 5 | Hoa | Exists |

COUNT = 3, FIRST = 1, LAST = 5. Existing indices cannot be inferred from the range 1 to COUNT.

### 6.2 Why FOR i IN 1..COUNT Is Unsafe

The following works only for dense collections with contiguous indices starting at 1:

~~~sql
FOR i IN 1 .. l_names.COUNT LOOP
    DBMS_OUTPUT.PUT_LINE(l_names(i));
END LOOP;
~~~

For the collection in the example above, COUNT = 3, so the loop reads indices 1, 2, 3. Index 2 was deleted and raises an error on access; index 5 is skipped even though the element still exists.

Similarly, FIRST..LAST is also unsafe if there are gaps in the middle:

~~~sql
FOR i IN l_names.FIRST .. l_names.LAST LOOP
    DBMS_OUTPUT.PUT_LINE(l_names(i));
END LOOP;
~~~

This loop still steps over deleted indices.

### 6.3 Traversing with FIRST and NEXT

This is the general pattern for traversing sparse collections:

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(30);
    l_names t_names := t_names(
        'An', 'Binh', 'Chi', 'Dung', 'Hoa'
    );
    l_idx PLS_INTEGER;
BEGIN
    l_names.DELETE(2);
    l_names.DELETE(4);

    l_idx := l_names.FIRST;

    WHILE l_idx IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Index=' || l_idx || ', value=' || l_names(l_idx)
        );

        l_idx := l_names.NEXT(l_idx);
    END LOOP;
END;
/
~~~

NEXT automatically skips deleted indices and returns NULL after the last element. This pattern also works for associative arrays; if the keys are strings, the key variable must have a type compatible with the key type.

### 6.4 Traversing an Associative Array with Sparse Keys

~~~sql
DECLARE
    TYPE t_score_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_scores t_score_map;
    l_key PLS_INTEGER;
BEGIN
    l_scores(10) := 85;
    l_scores(30) := 92;
    l_scores(100) := 77;

    l_key := l_scores.FIRST;
    WHILE l_key IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Key=' || l_key || ', score=' || l_scores(l_key)
        );
        l_key := l_scores.NEXT(l_key);
    END LOOP;
END;
/
~~~

There is no need to assume keys start at 1 or are contiguous. FIRST/NEXT is the natural traversal pattern for associative arrays.

## 7. EXISTS Before Reading an Element

If an index might not exist, check with EXISTS first:

~~~sql
IF l_values.EXISTS(p_index) THEN
    IF l_values(p_index) IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Element exists but value is NULL');
    ELSE
        DBMS_OUTPUT.PUT_LINE(l_values(p_index));
    END IF;
ELSE
    DBMS_OUTPUT.PUT_LINE('Element does not exist');
END IF;
~~~

Order matters: only read l_values(p_index) after EXISTS returns TRUE.

Do not write:

~~~sql
IF l_values(p_index) IS NOT NULL
   AND l_values.EXISTS(p_index) THEN
    ...
END IF;
~~~

Because the expression attempts to access the element before checking EXISTS; do not rely on boolean evaluation order to guard collection access.

### 7.1 Checking Whether a Collection Is Initialized

For a nested table or varray that might be atomically null:

~~~sql
IF l_values.EXISTS(1) THEN
    -- Element 1 exists.
ELSE
    -- Element 1 does not exist; the collection may be empty or atomically null.
END IF;
~~~

EXISTS does not distinguish an empty collection from an atomically null collection because both return FALSE for a missing index. If you need to distinguish those two states to apply different logic, pass a separate status flag in your API or require callers to initialize collections with a constructor before calling.

## 8. Common Exceptions

Accessing a collection in the wrong state or with an invalid index can raise exceptions. Common errors:

| Exception | Typical Error Code | Cause |
|---|---:|---|
| COLLECTION_IS_NULL | ORA-06531 | Calling methods other than EXISTS or reading/assigning elements on an atomically null collection |
| SUBSCRIPT_OUTSIDE_LIMIT | ORA-06532 | Subscript is outside valid collection bounds, e.g., exceeding VARRAY limit |
| SUBSCRIPT_BEYOND_COUNT | ORA-06533 | Accessing an element beyond current element count, commonly with VARRAY |
| NO_DATA_FOUND | ORA-01403 | Accessing a non-existent element, such as a deleted nested table slot or unassigned associative array key |

The specific exception depends on the collection type and operation. For example, with a varray, an index greater than LIMIT is outside the limit; an index greater than COUNT but within LIMIT has no element yet to read. With a sparse nested table, a deleted index can raise NO_DATA_FOUND.

### 8.1 COLLECTION_IS_NULL

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers;
BEGIN
    l_numbers.EXTEND;
END;
/
~~~

EXTEND cannot initialize an atomically null collection; assign a constructor first:

~~~sql
l_numbers := t_numbers();
l_numbers.EXTEND;
~~~

### 8.2 NO_DATA_FOUND from a Deleted Element

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30);
BEGIN
    l_numbers.DELETE(2);
    DBMS_OUTPUT.PUT_LINE(l_numbers(2));
END;
/
~~~

Index 2 no longer has an element. Check EXISTS before reading.

### 8.3 SUBSCRIPT_BEYOND_COUNT and SUBSCRIPT_OUTSIDE_LIMIT

For VARRAY:

~~~sql
DECLARE
    TYPE t_small_array IS VARRAY(3) OF NUMBER;
    l_values t_small_array := t_small_array(10, 20);
BEGIN
    -- Index 3 has no element yet because COUNT = 2.
    DBMS_OUTPUT.PUT_LINE(l_values(3));
END;
/
~~~

Reading an unpopulated index past COUNT can raise SUBSCRIPT_BEYOND_COUNT. Accessing an index past LIMIT or outside valid subscript bounds can raise SUBSCRIPT_OUTSIDE_LIMIT. Use EXISTS and COUNT/LIMIT to avoid invalid accesses.

## 9. Dense VARRAYs and the LIMIT Bound

VARRAY suits lists with a known maximum size that must preserve sequential order. VARRAY does not create gaps via single-element DELETE.

### 9.1 COUNT, LAST, and LIMIT

~~~sql
DECLARE
    TYPE t_codes IS VARRAY(4) OF VARCHAR2(10);
    l_codes t_codes := t_codes('A', 'B');
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_codes.COUNT); -- 2
    DBMS_OUTPUT.PUT_LINE(l_codes.LAST);  -- 2
    DBMS_OUTPUT.PUT_LINE(l_codes.LIMIT); -- 4

    l_codes.EXTEND;
    l_codes(3) := 'C';

    DBMS_OUTPUT.PUT_LINE(l_codes.COUNT); -- 3
END;
/
~~~

For a non-empty VARRAY, COUNT and LAST are equal because indices are always contiguous from 1. LIMIT is the declared upper bound.

### 9.2 Cannot Exceed LIMIT

~~~sql
DECLARE
    TYPE t_codes IS VARRAY(2) OF VARCHAR2(10);
    l_codes t_codes := t_codes('A', 'B');
BEGIN
    l_codes.EXTEND;
END;
/
~~~

EXTEND fails because the collection has reached its limit of 2. You can check COUNT < LIMIT before appending:

~~~sql
IF l_codes.COUNT < l_codes.LIMIT THEN
    l_codes.EXTEND;
    l_codes(l_codes.COUNT) := 'C';
END IF;
~~~

### 9.3 Wanting to Delete an Element in the Middle

VARRAY does not support DELETE( n ). If business logic needs arbitrary deletions leaving sparse indices, a nested table or associative array is usually more appropriate. If you still need a VARRAY, build a new VARRAY and copy the kept elements in order.

## 10. Nested Tables: DELETE, EXTEND, and TRIM

A nested table can both change size and become sparse. Design algorithms based on whether subscripts must stay fixed or you just need a dense list.

### 10.1 Deleting a Middle Element and Traversing the Rest

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_values t_numbers := t_numbers(100, 200, 300, 400, 500);
    l_idx PLS_INTEGER;
BEGIN
    l_values.DELETE(2);

    l_idx := l_values.FIRST;
    WHILE l_idx IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(l_idx || ': ' || l_values(l_idx));
        l_idx := l_values.NEXT(l_idx);
    END LOOP;
END;
/
~~~

The element at index 2 is removed; indices 3, 4, and 5 remain intact. Oracle does not automatically compact data to fill the gap.

### 10.2 Deleting Everything

~~~sql
l_values.DELETE;
~~~

DELETE with no arguments removes all elements. For an initialized collection, the collection remains valid and empty; COUNT = 0 and FIRST/LAST return NULL. It is not the same as resetting the variable to atomically null.

### 10.3 Using EXTEND to Append Elements

~~~sql
l_values.EXTEND;
l_values(l_values.LAST) := 600;
~~~

EXTEND creates an extra slot at the end with an initial value of NULL. For clarity, store the new index after EXTEND or use LAST to identify the new end position. With sparse collections, do not use COUNT as the new index unless you are certain the collection is dense.

### 10.4 When a Fresh Dense List Is Needed

If you want to eliminate gaps and produce a contiguous collection starting at 1, copy existing elements into a new collection:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_source t_numbers := t_numbers(10, 20, 30, 40, 50);
    l_dense  t_numbers := t_numbers();
    l_idx    PLS_INTEGER;
BEGIN
    l_source.DELETE(2);
    l_source.DELETE(4);

    l_idx := l_source.FIRST;
    WHILE l_idx IS NOT NULL LOOP
        l_dense.EXTEND;
        l_dense(l_dense.LAST) := l_source(l_idx);
        l_idx := l_source.NEXT(l_idx);
    END LOOP;

    -- l_dense has contiguous indices 1..3.
    DBMS_OUTPUT.PUT_LINE(l_dense.COUNT);
END;
/
~~~

This constructs a new collection; DELETE does not auto-compact. It is helpful when downstream code requires a contiguous index sequence.

## 11. Associative Arrays: Non-Contiguous Keys

Associative arrays are commonly used for lookups in PL/SQL:

~~~sql
DECLARE
    TYPE t_employee_map IS TABLE OF VARCHAR2(100)
        INDEX BY PLS_INTEGER;
    l_names t_employee_map;
BEGIN
    l_names(100) := 'An';
    l_names(500) := 'Binh';
    l_names(900) := 'Chi';

    l_names.DELETE(500);

    IF l_names.EXISTS(500) THEN
        DBMS_OUTPUT.PUT_LINE(l_names(500));
    ELSE
        DBMS_OUTPUT.PUT_LINE('Key 500 was removed');
    END IF;
END;
/
~~~

Associative arrays have sparse keys, and DELETE removes a key. There is no EXTEND/TRIM because elements are not managed as a contiguous-sized sequence. Use FIRST/NEXT to traverse existing keys.

### 11.1 String-Keyed Associative Arrays

~~~sql
DECLARE
    TYPE t_config_map IS TABLE OF VARCHAR2(200)
        INDEX BY VARCHAR2(30);
    l_config t_config_map;
    l_key VARCHAR2(30);
BEGIN
    l_config('LANGUAGE') := 'vi';
    l_config('TIMEZONE') := 'Asia/Ho_Chi_Minh';
    l_config('THEME') := 'dark';

    l_key := l_config.FIRST;
    WHILE l_key IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(l_key || '=' || l_config(l_key));
        l_key := l_config.NEXT(l_key);
    END LOOP;
END;
/
~~~

With string keys, FIRST/NEXT follows the associative array's index order, not insertion order. Order can be affected by NLS_SORT and NLS_COMP. If you need stable business ordering independent of session settings, track order explicitly.

## 12. Collection Methods in Loops and Batch Processing

### 12.1 Simple Dense Loop

For a VARRAY or a nested table guaranteed to be dense:

~~~sql
FOR i IN 1 .. l_values.COUNT LOOP
    process_value(l_values(i));
END LOOP;
~~~

This is concise when the collection is initialized, COUNT > 0, and indices are contiguous from 1. If COUNT = 0, the loop 1..0 executes zero times; however, make sure the collection is not atomically null before reading COUNT.

### 12.2 General Sparse Loop

~~~sql
DECLARE
    l_idx PLS_INTEGER;
BEGIN
    l_idx := l_values.FIRST;
    WHILE l_idx IS NOT NULL LOOP
        process_value(l_values(l_idx));
        l_idx := l_values.NEXT(l_idx);
    END LOOP;
END;
/
~~~

Use this pattern whenever a collection may have elements deleted or uses sparse keys.

### 12.3 BULK COLLECT Usually Produces a Dense Collection

Example:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_employee_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_employee_ids
    FROM employees
    WHERE department_id = 10
    ORDER BY employee_id;

    FOR i IN 1 .. l_employee_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(l_employee_ids(i));
    END LOOP;
END;
/
~~~

BULK COLLECT loads returned rows into a contiguous collection starting at index 1 in this standard case. If elements are later removed with DELETE, do not continue assuming it is dense.

### 12.4 BULK COLLECT with LIMIT

LIMIT in FETCH BULK COLLECT caps how many rows are fetched per batch; it is not the LIMIT method of a nested table or associative array. Example:

~~~sql
DECLARE
    CURSOR c_emp IS
        SELECT employee_id
        FROM employees
        ORDER BY employee_id;

    TYPE t_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_ids;
BEGIN
    OPEN c_emp;
    LOOP
        FETCH c_emp BULK COLLECT INTO l_ids LIMIT 500;
        EXIT WHEN l_ids.COUNT = 0;

        FOR i IN 1 .. l_ids.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(l_ids(i));
        END LOOP;
    END LOOP;
    CLOSE c_emp;
END;
/
~~~

Each FETCH replaces the collection with the new result batch. Therefore you can safely iterate 1..COUNT unless you delete elements inside the batch.

### 12.5 FORALL and Sparse Indices

FORALL can work with sparse collections using appropriate index clauses such as INDICES OF or VALUES OF. Example:

~~~sql
FORALL i IN INDICES OF l_ids
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = l_ids(i);
~~~

INDICES OF lets FORALL iterate over existing indices rather than assuming 1..COUNT. When using SAVE EXCEPTIONS, inspect SQL%BULK_EXCEPTIONS to handle individual DML errors; FORALL details are their own topic, but both rely on understanding collection indices correctly.

## 13. Writing Procedures That Accept Collections from Callers

A procedure should define its contract: must callers pass an initialized collection, or does the procedure accept null collections?

### 13.1 Checking EXISTS Safely on Potentially Null Collections

~~~sql
CREATE TYPE t_number_table AS TABLE OF NUMBER;
/

CREATE OR REPLACE PROCEDURE print_first_value (
    p_values IN t_number_table
)
AS
BEGIN
    IF p_values.EXISTS(1) THEN
        DBMS_OUTPUT.PUT_LINE(p_values(1));
    ELSE
        DBMS_OUTPUT.PUT_LINE('No element at index 1');
    END IF;
END;
/
~~~

T_NUMBER_TABLE is a schema-level nested table type so standalone procedures can use it as a parameter type. EXISTS can be called even when the collection parameter is atomically null.

### 13.2 Initializing Null Collections If the Procedure Needs to Append Elements

If a procedure must call EXTEND or assign elements on a nested table/varray, ensure the collection is initialized:

If a procedure needs to call EXTEND or read elements via FIRST/NEXT, specify clearly that callers must pass an initialized collection. EXISTS can safely test a subscript on a null collection, but it cannot distinguish an atomically null collection from an empty collection using its FALSE result alone. If the API needs to differentiate those two states, pass a separate status flag or design callers to always initialize collections with a constructor before calling.

### 13.3 Do Not Mutate IN Collection Parameters

An IN parameter must not be used to modify the caller's collection. If you need to add or remove elements, use an IN OUT parameter or return an OUT result collection with a clear contract.

## 14. Performance and Memory

### 14.1 Collections Reside in Session Memory

PL/SQL collections are generally stored in session/engine memory during processing. A very large collection can consume significant PGA or session memory, especially when many sessions run concurrently.

### 14.2 Use LIMIT for Batching

For large queries, FETCH BULK COLLECT ... LIMIT caps the number of rows held in the collection at once. Choose batch size based on row width, available memory, processing time, and system load.

### 14.3 COUNT Does Not Measure Memory Footprint

COUNT is only the number of existing elements. It does not tell you exact bytes used, internal capacity, or total collection overhead.

### 14.4 Avoid Unnecessary Copies of Large Collections

Assigning collections, passing collections across many layers, or building new dense copies can incur copy/memory overhead. If you only need to iterate, use FIRST/NEXT directly; make copies only when business logic truly requires them.

## 15. Common Errors and How to Handle Them

| Error | Cause | Resolution |
|---|---|---|
| COLLECTION_IS_NULL | Calling a method on an uninitialized nested table/varray | Assign a constructor before use |
| NO_DATA_FOUND | Reading a deleted index or unassigned key | Check EXISTS first |
| SUBSCRIPT_BEYOND_COUNT | Reading an index beyond current element count, typically with varray | Check EXISTS/COUNT |
| SUBSCRIPT_OUTSIDE_LIMIT | Index outside valid limits, e.g., exceeding VARRAY LIMIT | Check LIMIT and index |
| 1..COUNT loop skips elements | Collection is sparse, COUNT is not the last index | Use FIRST/NEXT |
| FIRST..LAST loop fails | Deleted indices exist in the middle | Use NEXT to skip gaps |
| Calling EXTEND on associative array | Method unsupported for this type | Assign directly by key |
| Calling DELETE(n) on VARRAY | VARRAY does not support single-element deletion | Rebuild collection or choose nested table |
| VARRAY EXTEND exceeds LIMIT | Maximum element count reached | Check COUNT < LIMIT |
| Confusing NULL with missing element | A NULL value can still belong to an existing element | Check EXISTS first, then IS NULL |
| Using TRIM like DELETE(LAST) | TRIM acts on internal size, including deleted trailing slots | Do not mix DELETE and TRIM carelessly |
| Assuming associative array follows insertion order | Keys are traversed in index order | Store explicit order if needed |

## 16. Lab: Observing Sparse Indices and Collection Methods

The following blocks run in a practice PL/SQL schema. They use local collections and do not create or alter business tables.

### 16.1 Comparing COUNT, FIRST, and LAST Before and After DELETE

~~~sql
SET SERVEROUTPUT ON

DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_values t_numbers := t_numbers(10, 20, 30, 40, 50);
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Before: COUNT=' || l_values.COUNT ||
        ', FIRST=' || l_values.FIRST ||
        ', LAST=' || l_values.LAST
    );

    l_values.DELETE(2);
    l_values.DELETE(4);

    DBMS_OUTPUT.PUT_LINE(
        'After: COUNT=' || l_values.COUNT ||
        ', FIRST=' || l_values.FIRST ||
        ', LAST=' || l_values.LAST
    );

    DBMS_OUTPUT.PUT_LINE('EXISTS(2)=' ||
        CASE WHEN l_values.EXISTS(2) THEN 'TRUE' ELSE 'FALSE' END);
    DBMS_OUTPUT.PUT_LINE('NEXT(1)=' || l_values.NEXT(1));
    DBMS_OUTPUT.PUT_LINE('NEXT(3)=' || l_values.NEXT(3));
END;
/
~~~

Observe that COUNT decreases while LAST does not necessarily equal COUNT; NEXT skips deleted indices.

### 16.2 Distinguishing a NULL Element from a Deleted Element

~~~sql
DECLARE
    TYPE t_values IS TABLE OF NUMBER;
    l_values t_values := t_values(10, NULL, 30);
BEGIN
    l_values.DELETE(3);

    DBMS_OUTPUT.PUT_LINE(
        'Index 2 exists=' ||
        CASE WHEN l_values.EXISTS(2) THEN 'TRUE' ELSE 'FALSE' END
    );
    DBMS_OUTPUT.PUT_LINE(
        'Index 2 is null=' ||
        CASE WHEN l_values(2) IS NULL THEN 'TRUE' ELSE 'FALSE' END
    );

    DBMS_OUTPUT.PUT_LINE(
        'Index 3 exists=' ||
        CASE WHEN l_values.EXISTS(3) THEN 'TRUE' ELSE 'FALSE' END
    );
END;
/
~~~

Index 2 exists with a NULL value; index 3 was deleted.

### 16.3 Traversing a Sparse Nested Table

~~~sql
DECLARE
    TYPE t_values IS TABLE OF VARCHAR2(20);
    l_values t_values := t_values('A', 'B', 'C', 'D', 'E');
    l_idx PLS_INTEGER;
BEGIN
    l_values.DELETE(2);
    l_values.DELETE(4);

    l_idx := l_values.FIRST;
    WHILE l_idx IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(l_idx || '=' || l_values(l_idx));
        l_idx := l_values.NEXT(l_idx);
    END LOOP;
END;
/
~~~

The output prints only indices 1, 3, and 5.

### 16.4 Comparing the Three Collection Types

~~~sql
DECLARE
    TYPE t_assoc IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_nested IS TABLE OF NUMBER;
    TYPE t_array IS VARRAY(5) OF NUMBER;

    l_assoc  t_assoc;
    l_nested t_nested := t_nested(10, 20, 30);
    l_array  t_array := t_array(10, 20, 30);
BEGIN
    l_assoc(10) := 100;
    l_assoc(30) := 300;

    l_nested.DELETE(2);
    l_array.EXTEND;
    l_array(4) := 40;

    DBMS_OUTPUT.PUT_LINE('Associative count=' || l_assoc.COUNT);
    DBMS_OUTPUT.PUT_LINE('Nested count=' || l_nested.COUNT);
    DBMS_OUTPUT.PUT_LINE('Nested last=' || l_nested.LAST);
    DBMS_OUTPUT.PUT_LINE('Varray count=' || l_array.COUNT);
    DBMS_OUTPUT.PUT_LINE('Varray limit=' || l_array.LIMIT);
END;
/
~~~

Observe that the associative array uses keys 10 and 30; the nested table has a gap at index 2; the varray stays contiguous after EXTEND.

## 17. Practical Guidelines

When writing PL/SQL with collections:

1. Identify the collection type before calling methods.
2. Initialize nested tables/varrays before calling methods other than EXISTS.
3. Use COUNT to get the current element count, not as the last index if the collection can be sparse.
4. Use FIRST/NEXT to traverse collections that may have gaps or sparse keys.
5. Use EXISTS before reading an uncertain index.
6. Separate existence checks from NULL value checks.
7. Use EXTEND/TRIM only with nested tables and varrays.
8. Use DELETE only with associative arrays and nested tables; do not delete individual varray elements.
9. Check LIMIT before calling EXTEND on a varray.
10. Do not mix DELETE and TRIM on the same nested table without understanding the effect on its internal tail.
11. For string-keyed associative arrays, do not rely on insertion order.
12. For large collections, consider BULK COLLECT LIMIT and avoid unnecessary data copies.

## 18. Summary

Collection methods are the interface for inspecting and manipulating elements in PL/SQL. To use them safely, you need to know what state the collection is in and whether an index actually exists.

- COUNT counts existing elements; LAST returns the highest existing index. The two values can differ in sparse collections.
- FIRST/LAST determine index bounds; PRIOR/NEXT step through existing indices and skip deleted elements.
- EXISTS checks existence, even when the element's value is NULL. It is also the only method callable on an atomically null collection.
- LIMIT reports the maximum limit of a VARRAY; nested tables and associative arrays have no fixed LIMIT.
- DELETE creates gaps in nested tables or removes keys from associative arrays. VARRAY does not support single-element DELETE.
- EXTEND adds NULL elements to nested tables/varrays; TRIM removes elements from the end. Neither applies to associative arrays.
- Atomically null collections, empty collections, NULL elements, and deleted indices are distinct states.
- Traverse potentially sparse collections with FIRST/NEXT; use 1..COUNT only when the collection is guaranteed dense.

Once you master these rules, your PL/SQL code will avoid subscript errors, handle sparse collections cleanly, and leverage collections safely in bulk processing.
