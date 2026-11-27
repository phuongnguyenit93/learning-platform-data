# PL/SQL JSON Object Types and JSON Tree Manipulation

Oracle provides PL/SQL object types to read, construct, traverse, and modify JSON documents as an in-memory data tree. This family of types is commonly referred to as PL/SQL JSON DOM types. The main types include:

- **JSON_ELEMENT_T**: base type representing any JSON element.
- **JSON_OBJECT_T**: represents a JSON object consisting of key/value pairs.
- **JSON_ARRAY_T**: represents an ordered JSON array.
- **JSON_SCALAR_T**: represents scalar values such as string, number, or boolean.
- **JSON_KEY_LIST**: list type of key names returned when retrieving an object's keys.

These types allow PL/SQL to parse JSON text into a manipulable structure, read values by key or index, add/remove/update properties, modify nested objects/arrays, and serialize the JSON tree back into VARCHAR2, CLOB, or BLOB.

For example, parsing an object and updating a property:

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
BEGIN
    l_doc := JSON_OBJECT_T.parse(
        '{"orderId":1001,"status":"NEW","amount":250000}'
    );

    l_doc.put('status', 'APPROVED');

    DBMS_OUTPUT.PUT_LINE(l_doc.to_string());
END;
/
~~~

PL/SQL JSON object types are well suited when logic requires branching over JSON structures or modifying multiple parts of a document. When the goal is simply filtering, projecting, or updating JSON data across many rows, SQL/JSON functions such as JSON_VALUE, JSON_QUERY, JSON_EXISTS, JSON_TABLE, and JSON_TRANSFORM (depending on version) are usually a more natural fit.

## 1. JSON as a Data Tree

JSON has six basic value types:

- Object: a collection of key/value pairs.
- Array: an ordered list of values.
- String: a character sequence.
- Number: a numeric value.
- Boolean: TRUE or FALSE.
- Null: the JSON null value.

Example:

~~~json
{
  "orderId": 1001,
  "customer": {
    "id": 25,
    "name": "An"
  },
  "items": [
    {
      "sku": "KB-01",
      "quantity": 2,
      "price": 150000
    },
    {
      "sku": "MS-02",
      "quantity": 1,
      "price": 250000
    }
  ],
  "paid": false,
  "note": null
}
~~~

The tree above has a root object. The customer property holds a nested object; items holds an array of two objects; paid is a boolean; note is JSON null.

~~~text
root object
  orderId: number
  customer: object
    id: number
    name: string
  items: array
    [0]: object
      sku: string
      quantity: number
      price: number
    [1]: object
      sku: string
      quantity: number
      price: number
  paid: boolean
  note: null
~~~

### 1.1. Objects and Arrays Differ

Objects access elements by key name:

~~~json
{"name":"An","age":30}
~~~

Arrays access elements by position:

~~~json
["An",30,true]
~~~

JSON arrays preserve order. JSON objects are collections of key/value pairs; you should not rely on key order when serializing or iterating over an object.

### 1.2. PL/SQL JSON Types Are In-Memory Trees

When parsing JSON text, Oracle creates PL/SQL objects representing the JSON tree. Operations such as PUT, APPEND, or REMOVE modify the in-memory structure. Those changes are not automatically written to a table; to persist them, you must serialize and execute DML or return the result to the caller.

## 2. The JSON Object Types

### 2.1. JSON_ELEMENT_T

JSON_ELEMENT_T is the base type for any JSON element. It can represent an object, an array, or a scalar. Common type-checking methods include:

- IS_OBJECT
- IS_ARRAY
- IS_SCALAR
- IS_NULL
- IS_STRING
- IS_NUMBER
- IS_BOOLEAN
- GET_TYPE on JSON_OBJECT_T/JSON_ARRAY_T: returns node type by key/index
- TO_STRING
- TO_CLOB
- TO_BLOB

Example:

~~~sql
DECLARE
    l_element JSON_ELEMENT_T;
BEGIN
    l_element := JSON_OBJECT_T.parse('{"active":true}');

    IF l_element.is_object() THEN
        DBMS_OUTPUT.PUT_LINE('Root is an object');
    END IF;

    DBMS_OUTPUT.PUT_LINE('Root type is OBJECT');
END;
/
~~~

JSON_ELEMENT_T is useful when you do not know upfront whether a node is an object, array, or scalar.

### 2.2. JSON_OBJECT_T

JSON_OBJECT_T represents an object. Common operations:

- PARSE: parses JSON text into an object.
- GET: retrieves an element by key as a JSON_ELEMENT_T.
- GET_STRING, GET_NUMBER, GET_BOOLEAN: retrieves a scalar as the desired type.
- GET_OBJECT, GET_ARRAY: retrieves a child node by type.
- HAS: checks whether a key exists.
- GET_KEYS: retrieves the list of keys.
- GET_SIZE: number of properties.
- PUT: adds or replaces a key/value pair.
- PUT_NULL: assigns JSON null.
- REMOVE: deletes a key.
- RENAME_KEY: renames a key.
- TO_STRING, TO_CLOB, TO_BLOB: serializes the object.

### 2.3. JSON_ARRAY_T

JSON_ARRAY_T represents an array. Common operations:

- PARSE: parses a JSON array.
- GET and GET_STRING/GET_NUMBER/GET_BOOLEAN: retrieves an element by index.
- GET_OBJECT, GET_ARRAY: retrieves a child object/array.
- GET_SIZE: number of elements.
- APPEND: appends an element to the end.
- APPEND_NULL: appends JSON null.
- PUT: inserts an element at an index; pass OVERWRITE TRUE to replace an existing element.
- PUT_NULL: sets JSON null at an index.
- REMOVE: removes an element by index.
- TO_STRING, TO_CLOB, TO_BLOB: serializes the array.

### 2.4. JSON_SCALAR_T

JSON_SCALAR_T represents a scalar value. In most application code, you can directly use the GET_STRING, GET_NUMBER, GET_BOOLEAN, and PUT overloads on objects/arrays instead of manually constructing JSON_SCALAR_T.

### 2.5. JSON_KEY_LIST

GET_KEYS returns a list of key names in an object. The return type is JSON_KEY_LIST, which can be iterated like a PL/SQL collection:

~~~sql
DECLARE
    l_obj  JSON_OBJECT_T;
    l_keys JSON_KEY_LIST;
BEGIN
    l_obj := JSON_OBJECT_T.parse(
        '{"id":10,"name":"An","active":true}'
    );

    l_keys := l_obj.get_keys();

    FOR i IN 1 .. l_keys.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(l_keys(i));
    END LOOP;
END;
/
~~~

The returned key order should not be treated as business order. If the application requires a display order, represent that order using an array or an ordinal property.

## 3. Parsing JSON Text

JSON_OBJECT_T and JSON_ARRAY_T provide the static method PARSE to convert JSON text into an object or array respectively.

### 3.1. Parsing a Root Object

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
BEGIN
    l_doc := JSON_OBJECT_T.parse(
        '{"id":100,"name":"Oracle","enabled":true}'
    );

    DBMS_OUTPUT.PUT_LINE(l_doc.get_number('id'));
    DBMS_OUTPUT.PUT_LINE(l_doc.get_string('name'));
END;
/
~~~

The JSON root must be an object when using JSON_OBJECT_T.PARSE.

### 3.2. Parsing a Root Array

~~~sql
DECLARE
    l_values JSON_ARRAY_T;
BEGIN
    l_values := JSON_ARRAY_T.parse('[10,20,30]');

    DBMS_OUTPUT.PUT_LINE('Count=' || l_values.get_size());
    DBMS_OUTPUT.PUT_LINE('First=' || l_values.get_number(0));
END;
/
~~~

The JSON root must be an array when using JSON_ARRAY_T.PARSE.

### 3.3. Parsing from CLOB

When a JSON document exceeds the VARCHAR2 limit, store the text in a CLOB and parse from the locator:

~~~sql
DECLARE
    l_json CLOB;
    l_doc  JSON_OBJECT_T;
BEGIN
    l_json := TO_CLOB(
        '{"documentId":10,"description":"A large document payload"}'
    );

    l_doc := JSON_OBJECT_T.parse(l_json);

    DBMS_OUTPUT.PUT_LINE(l_doc.get_number('documentId'));
END;
/
~~~

In real applications, the CLOB may come from a table column, request payload, or API. Parsing constructs an object tree in memory, so very large documents still consume session/PGA memory even when the source is stored in a CLOB.

### 3.4. Invalid JSON or Wrong Root Type

If the string is not valid JSON, PARSE raises an error. If you call JSON_OBJECT_T.PARSE on a root array or scalar, the root type mismatches. Catch parse errors at the data ingestion boundary:

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{invalid json}');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Cannot parse JSON');
        DBMS_OUTPUT.PUT_LINE(SQLCODE);
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        RAISE;
END;
/
~~~

Do not catch a parse error and silently replace the payload with an empty object if doing so causes malformed data to be treated as valid.

## 4. Creating a New JSON Object

You do not need to parse text when building a JSON tree from scratch. You can invoke the JSON_OBJECT_T() constructor.

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
BEGIN
    l_doc := JSON_OBJECT_T();

    l_doc.put('orderId', 1001);
    l_doc.put('status', 'NEW');
    l_doc.put('amount', 250000);
    l_doc.put('paid', FALSE);

    DBMS_OUTPUT.PUT_LINE(l_doc.to_string());
END;
/
~~~

PUT adds a new key or replaces the value of an existing key.

### 4.1. PUT with Scalars

~~~sql
l_doc.put('name', 'An');
l_doc.put('age', 30);
l_doc.put('active', TRUE);
l_doc.put('balance', 1250.75);
~~~

The PL/SQL datatype of the actual argument determines the JSON scalar type created. Use BOOLEAN for JSON boolean, NUMBER for JSON number, and VARCHAR2 for JSON string.

### 4.2. Assigning JSON null

Use PUT_NULL to represent JSON null:

~~~sql
l_doc.put_null('middleName');
~~~

Do not confuse JSON null with a non-existent key or a PL/SQL variable that is NULL. If you need to express that a key is present with no value, PUT_NULL is explicit.

### 4.3. Replacing a Key's Value

~~~sql
l_doc.put('status', 'APPROVED');
~~~

If status already exists, its value is replaced. If it does not exist yet, the key is added to the object.

### 4.4. Checking Before Reading

~~~sql
IF l_doc.has('status') THEN
    DBMS_OUTPUT.PUT_LINE(l_doc.get_string('status'));
ELSE
    DBMS_OUTPUT.PUT_LINE('status is missing');
END IF;
~~~

HAS checks key existence. JSON keys are case-sensitive, so status and Status are two distinct names.

## 5. Reading Values from a JSON Object

JSON_OBJECT_T provides typed getters. Choose the getter matching the actual JSON type.

### 5.1. GET_STRING

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
    l_name VARCHAR2(100);
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"name":"An"}');

    l_name := l_doc.get_string('name');

    DBMS_OUTPUT.PUT_LINE(l_name);
END;
/
~~~

GET_STRING is appropriate when the value is a JSON string. Do not use it to read an object or array.

### 5.2. GET_NUMBER

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
    l_amount NUMBER;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"amount":1250.50}');

    l_amount := l_doc.get_number('amount');

    DBMS_OUTPUT.PUT_LINE(l_amount);
END;
/
~~~

JSON numbers map to NUMBER. If the application requires specific precision/scale, validate business bounds before writing to the target column.

### 5.3. GET_BOOLEAN

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
    l_active BOOLEAN;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"active":true}');

    l_active := l_doc.get_boolean('active');

    IF l_active THEN
        DBMS_OUTPUT.PUT_LINE('Active');
    END IF;
END;
/
~~~

A JSON boolean is not the string 'true' or 'false'. Use GET_BOOLEAN to retrieve a PL/SQL BOOLEAN value.

### 5.4. GET_OBJECT and GET_ARRAY

~~~sql
DECLARE
    l_doc      JSON_OBJECT_T;
    l_customer JSON_OBJECT_T;
    l_items    JSON_ARRAY_T;
BEGIN
    l_doc := JSON_OBJECT_T.parse(
        '{"customer":{"id":25,"name":"An"},"items":[1,2,3]}'
    );

    l_customer := l_doc.get_object('customer');
    l_items := l_doc.get_array('items');

    DBMS_OUTPUT.PUT_LINE(l_customer.get_string('name'));
    DBMS_OUTPUT.PUT_LINE(l_items.get_size());
END;
/
~~~

Use the getter matching the child node type. If the key does not exist or the value is not an object/array, code must handle that case before accessing deeper levels.

### 5.5. GET Returns JSON_ELEMENT_T

When a node's type is unknown:

~~~sql
DECLARE
    l_doc     JSON_OBJECT_T;
    l_element JSON_ELEMENT_T;
BEGIN
    l_doc := JSON_OBJECT_T.parse(
        '{"value":[1,2,3]}'
    );

    l_element := l_doc.get('value');

    IF l_element IS NOT NULL THEN
        DBMS_OUTPUT.PUT_LINE('Node type=' || l_doc.get_type('value'));

        IF l_element.is_array() THEN
            DBMS_OUTPUT.PUT_LINE('Value is an array');
        END IF;
    END IF;
END;
/
~~~

GET returns a JSON_ELEMENT_T. Then use IS_OBJECT, IS_ARRAY, IS_STRING, IS_NUMBER, IS_BOOLEAN, or IS_NULL to determine the right way to read it.

### 5.6. Distinguishing Missing Keys from JSON null

JSON can contain:

~~~json
{"middleName":null}
~~~

Whereas another object might omit the middleName key:

~~~json
{"firstName":"An"}
~~~

The two cases carry different meanings:
- HAS('middleName') = FALSE: the key does not exist.
- HAS('middleName') = TRUE and the element has IS_NULL = TRUE: the key exists with JSON null.

Example check:

~~~sql
DECLARE
    l_doc     JSON_OBJECT_T;
    l_element JSON_ELEMENT_T;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"middleName":null}');

    IF l_doc.has('middleName') THEN
        l_element := l_doc.get('middleName');

        IF l_element.is_null() THEN
            DBMS_OUTPUT.PUT_LINE('Key exists with JSON null');
        END IF;
    ELSE
        DBMS_OUTPUT.PUT_LINE('Key is missing');
    END IF;
END;
/
~~~

This distinction is critical for PATCH APIs: an omitted key may mean "do not change," whereas a key with JSON null may mean "clear the value."

## 6. Reference Semantics, Value Semantics, and CLONE

When retrieving a child node, understand whether the returned variable is a copy or a reference to the node inside the original tree. This matters when editing nested JSON.

### 6.1. GET Returns a Reference to Composite Nodes

The GET methods return a JSON_ELEMENT_T referencing the node in the source object/array. If the node is an object or array and you modify it, the change is reflected in the parent tree.

~~~sql
DECLARE
    l_root    JSON_OBJECT_T;
    l_address JSON_OBJECT_T;
BEGIN
    l_root := JSON_OBJECT_T.parse(
        '{"name":"An","address":{"city":"Hanoi"}}'
    );

    l_address := l_root.get_object('address');
    l_address.put('city', 'Ho Chi Minh City');
    l_address.put('district', 'District 1');

    -- Changes on l_address are already reflected in l_root.
    DBMS_OUTPUT.PUT_LINE(l_root.to_string());
END;
/
~~~

You do not need to call PUT for address again just to propagate changes made through the referenced node back to the parent object. Calling PUT again with the same node can make code harder to read unnecessarily.

### 6.2. Scalar Getters Return Independent Values

GET_STRING, GET_NUMBER, and GET_BOOLEAN return scalar values with value semantics. Modifying the receiving PL/SQL variable does not modify the JSON node:

~~~sql
DECLARE
    l_doc   JSON_OBJECT_T;
    l_value NUMBER;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"amount":100}');

    l_value := l_doc.get_number('amount');
    l_value := 500;

    -- amount in l_doc remains 100.
    DBMS_OUTPUT.PUT_LINE(l_doc.to_string());
END;
/
~~~

To update a scalar in the tree, call PUT on the object or PUT on the array.

### 6.3. CLONE Creates a Deep Copy

CLONE creates an independent copy of an object or array. Changes on the clone do not affect the original tree:

~~~sql
DECLARE
    l_root       JSON_OBJECT_T;
    l_address    JSON_OBJECT_T;
    l_copy       JSON_OBJECT_T;
BEGIN
    l_root := JSON_OBJECT_T.parse(
        '{"address":{"city":"Hanoi"}}'
    );

    l_address := l_root.get_object('address');
    l_copy := l_address.clone();

    l_copy.put('city', 'Da Nang');

    DBMS_OUTPUT.PUT_LINE('Original=' || l_root.to_string());
    DBMS_OUTPUT.PUT_LINE('Copy=' || l_copy.to_string());
END;
/
~~~

Use CLONE when you need an independent processing branch, want to keep a snapshot before editing, or pass an object to a routine that must not mutate the original tree.

### 6.4. TREAT Casts JSON_ELEMENT_T to a Subtype

GET returns JSON_ELEMENT_T. Once you have checked that a node is an object or array, use TREAT to cast it to the specific subtype:

~~~sql
DECLARE
    l_root    JSON_ELEMENT_T;
    l_object  JSON_OBJECT_T;
    l_element JSON_ELEMENT_T;
BEGIN
    l_root := JSON_ELEMENT_T.parse('{"items":[1,2]}');

    IF l_root.is_object() THEN
        l_object := TREAT(l_root AS JSON_OBJECT_T);
        l_element := l_object.get('items');

        IF l_element.is_array() THEN
            DBMS_OUTPUT.PUT_LINE('items is an array');
        END IF;
    END IF;
END;
/
~~~

Only call TREAT after checking the type. Casting a scalar to JSON_OBJECT_T does not turn the scalar into a valid object.

## 7. JSON_ARRAY_T: Index, PUT, and REMOVE

JSON_ARRAY_T is ordered and 0-indexed. Beyond APPEND, you need to understand the exact semantics of PUT.

### 7.1. PUT Inserts Elements by Default

When an index already exists, PUT inserts the new element at that position by default and shifts elements from that position onward to the right:

~~~sql
DECLARE
    l_array JSON_ARRAY_T;
BEGIN
    l_array := JSON_ARRAY_T.parse('["A","B","C"]');

    l_array.put(1, 'X');

    DBMS_OUTPUT.PUT_LINE(l_array.to_string());
END;
/
~~~

The result has order A, X, B, C. Therefore, PUT does not overwrite by default.

### 7.2. PUT with OVERWRITE TRUE to Replace an Element

To replace the value at an index without shifting other elements, pass TRUE for the OVERWRITE parameter:

~~~sql
l_array.put(1, 'X', TRUE);
~~~

Starting from ["A","B","C"], the result is ["A","X","C"].

Use APPEND to add at the end; use PUT(index, value, TRUE) to replace an existing element at a position; use default PUT when you genuinely want to insert.

### 7.3. PUT_NULL Also Has an OVERWRITE Parameter

~~~sql
l_array.put_null(1, TRUE);
~~~

This statement replaces the element at index 1 with JSON null. If TRUE is omitted and the index exists, PUT_NULL may insert a null element and shift subsequent elements.

### 7.4. REMOVE Shifts the Indices of Subsequent Elements

~~~sql
DECLARE
    l_array JSON_ARRAY_T;
BEGIN
    l_array := JSON_ARRAY_T.parse('["A","B","C","D"]');
    l_array.remove(1);

    DBMS_OUTPUT.PUT_LINE(l_array.to_string());
END;
/
~~~

After removing index 1, the array becomes ["A","C","D"]. Element C moves from index 2 to index 1; D moves from index 3 to index 2.

Do not persist array indices long-term if elements can be inserted or removed. If stable identification is needed, each object in the array should carry its own ID property.

### 7.5. Updating an Object Element via Reference Semantics

If you retrieve a child object via GET_OBJECT and modify it directly, the change is reflected in the array:

~~~sql
DECLARE
    l_items JSON_ARRAY_T;
    l_item  JSON_OBJECT_T;
BEGIN
    l_items := JSON_ARRAY_T.parse(
        '[{"sku":"KB-01","quantity":2},{"sku":"MS-02","quantity":1}]'
    );

    l_item := l_items.get_object(0);
    l_item.put('quantity', 3);

    DBMS_OUTPUT.PUT_LINE(l_items.to_string());
END;
/
~~~

If you explicitly CLONE the object before modifying it, use PUT with OVERWRITE TRUE to replace the old element:

~~~sql
l_item := l_items.get_object(0).clone();
l_item.put('quantity', 3);
l_items.put(0, l_item, TRUE);
~~~

If TRUE is omitted in the last example, Oracle inserts the new object at index 0 and shifts the old object to index 1.

## 8. Working with Nested Objects and Arrays

Real-world documents often have multiple levels. A manageable approach is to step through each node, check its type, and apply changes on the target container.

### 8.1. Adding Nested Objects

~~~sql
DECLARE
    l_root    JSON_OBJECT_T;
    l_profile JSON_OBJECT_T;
    l_contact JSON_OBJECT_T;
BEGIN
    l_root := JSON_OBJECT_T();

    l_profile := JSON_OBJECT_T();
    l_profile.put('displayName', 'An');

    l_contact := JSON_OBJECT_T();
    l_contact.put('email', 'an@example.com');
    l_contact.put('phone', '0900000000');

    l_profile.put('contact', l_contact);
    l_root.put('profile', l_profile);

    DBMS_OUTPUT.PUT_LINE(l_root.to_string());
END;
/
~~~

PUT accepts JSON_ELEMENT_T or its subtypes, so child objects/arrays can be attached to parent containers.

### 8.2. Adding an Array to an Object

~~~sql
DECLARE
    l_root  JSON_OBJECT_T;
    l_roles JSON_ARRAY_T;
BEGIN
    l_root := JSON_OBJECT_T();
    l_roles := JSON_ARRAY_T();

    l_roles.append('READER');
    l_roles.append('EDITOR');

    l_root.put('roles', l_roles);

    DBMS_OUTPUT.PUT_LINE(l_root.to_string());
END;
/
~~~

### 8.3. Finding an Element in an Array by Property

JSON_ARRAY_T does not provide automatic business-key lookup. To find an item by SKU, iterate through the objects:

~~~sql
DECLARE
    l_items JSON_ARRAY_T;
    l_item  JSON_OBJECT_T;
    l_found PLS_INTEGER := NULL;
BEGIN
    l_items := JSON_ARRAY_T.parse(
        '[{"sku":"KB-01"},{"sku":"MS-02"},{"sku":"HD-03"}]'
    );

    IF l_items.get_size() > 0 THEN
        FOR i IN 0 .. l_items.get_size() - 1 LOOP
            l_item := l_items.get_object(i);

            IF l_item.has('sku')
               AND l_item.get_string('sku') = 'MS-02'
            THEN
                l_found := i;
                EXIT;
            END IF;
        END LOOP;
    END IF;

    IF l_found IS NOT NULL THEN
        DBMS_OUTPUT.PUT_LINE('Found at index ' || l_found);
    END IF;
END;
/
~~~

For very large arrays frequently queried by key, consider normalizing the data into a relational table or using JSON_TABLE instead of scanning the tree repeatedly.

### 8.4. Deleting an Item by SKU

~~~sql
IF l_found IS NOT NULL THEN
    l_items.remove(l_found);
END IF;
~~~

After REMOVE, subsequent indices shift. If removing multiple elements while iterating, iterate backward from the end or recalculate indices after each removal to avoid skipping elements.

## 9. ON_ERROR: Controlling How JSON DOM Reports Errors

JSON object types have an ON_ERROR method to configure behavior when JSON operations encounter errors such as missing keys, type mismatches, or invalid array indices.

By default, JSON DOM may return PL/SQL NULL instead of raising an exception for certain operation errors. This can cause data errors to be mistaken for null values. You can set an explicit policy:

~~~sql
l_doc.on_error(1);
~~~

Common values:

| Value | Behavior |
| ---: | --- |
| 0 | Default behavior: returns NULL for errors per default policy |
| 1 | Raises an exception for all errors |
| 2 | Raises an exception when a value is not found |
| 3 | Raises an exception on datatype mismatch |
| 4 | Raises an exception on invalid input, such as an out-of-range array index |
| 7 | Combines 3 and 4 |

ON_ERROR is set on a JSON_ELEMENT_T instance and applies to subsequent operations on that instance. You can call ON_ERROR(0) to revert to the default behavior.

### 9.1. Enabling Strict Error Handling

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
    l_amount NUMBER;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"amount":"not-a-number"}');
    l_doc.on_error(1);

    l_amount := l_doc.get_number('amount');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLCODE);
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        RAISE;
END;
/
~~~

With strict handling, conversion errors are raised for the caller to handle. This is usually easier to diagnose when receiving JSON from untrusted clients.

### 9.2. Checking for Missing Keys Before Getters

~~~sql
IF NOT l_doc.has('customerId') THEN
    RAISE_APPLICATION_ERROR(-20001, 'Missing customerId');
END IF;

l_customer_id := l_doc.get_number('customerId');
~~~

HAS distinguishes missing keys. ON_ERROR governs how remaining errors such as type mismatches or invalid indices are handled.

### 9.3. GET_STRING May Perform Type Conversion

Some getters perform implicit conversion when possible. For example, GET_STRING may return the string representation of a non-string JSON value. Therefore, if the contract strictly requires a JSON string, check IS_STRING or GET_TYPE before calling GET_STRING.

~~~sql
l_element := l_doc.get('status');

IF l_element IS NULL OR NOT l_element.is_string() THEN
    RAISE_APPLICATION_ERROR(-20002, 'status must be a JSON string');
END IF;

l_status := l_doc.get_string('status');
~~~

Do not rely on getter conversions to skip schema validation.

## 10. JSON null, SQL NULL, and Missing Keys

Three states are frequently confused:

| State | Example | How to Identify |
| --- | --- | --- |
| Key does not exist | {} | HAS(key) = FALSE |
| Key has JSON null | {"note":null} | HAS(key) = TRUE and node IS_NULL |
| PL/SQL NULL | Uninitialized variable/locator | PL/SQL variable IS NULL |

JSON null is a valid node in the JSON tree. It is neither PL/SQL NULL nor an absent key.

### 10.1. Rules for PATCH APIs

A PATCH API often needs to distinguish:
- Key omitted: leave the current property unchanged.
- Key sent with null value: delete or set to null per the API contract.
- Key sent with a new value: update the property.

Example:

~~~sql
IF l_patch.has('middleName') THEN
    l_value := l_patch.get('middleName');

    IF l_value.is_null() THEN
        l_target.remove('middleName');
    ELSE
        l_target.put('middleName', l_value);
    END IF;
END IF;
~~~

This snippet implements a specific policy: JSON null is interpreted as deleting the key. If business rules want to keep the key with JSON null, use PUT_NULL instead of REMOVE.

### 10.2. SQL NULL for the Entire Document

If the CLOB payload column is SQL NULL, there is no JSON text to parse. Check for NULL before calling PARSE:

~~~sql
IF l_payload IS NULL THEN
    RAISE_APPLICATION_ERROR(-20003, 'JSON payload is NULL');
END IF;
~~~

Do not automatically replace SQL NULL with an empty object unless that is an agreed-upon data rule.

## 11. Serializing JSON: VARCHAR2, CLOB, and BLOB

After editing the tree, serialize it to obtain JSON text.

### 11.1. TO_STRING for Small Documents

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
    l_text VARCHAR2(32767);
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"id":10,"status":"NEW"}');
    l_doc.put('status', 'DONE');

    l_text := l_doc.to_string();
    DBMS_OUTPUT.PUT_LINE(l_text);
END;
/
~~~

TO_STRING returns VARCHAR2. Use it for small payloads; do not use it if the document may exceed the PL/SQL VARCHAR2 limit.

### 11.2. TO_CLOB for Large Documents

~~~sql
DECLARE
    l_doc  JSON_OBJECT_T;
    l_json CLOB;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"id":10,"status":"NEW"}');
    l_doc.put('status', 'DONE');

    l_json := l_doc.to_clob();

    DBMS_OUTPUT.PUT_LINE(
        'Length=' || DBMS_LOB.GETLENGTH(l_json)
    );

    IF DBMS_LOB.ISTEMPORARY(l_json) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_json);
    END IF;
END;
/
~~~

The parameterless TO_CLOB function form creates a temporary CLOB as the serialization target. Check ISTEMPORARY and free it when no longer needed.

### 11.3. TO_CLOB with Caller-Provided Target Locator

There is a member procedure form accepting a CLOB IN OUT parameter so the caller supplies the target LOB. The target locator must be validly initialized, not PL/SQL NULL:

~~~sql
DECLARE
    l_doc    JSON_OBJECT_T;
    l_output CLOB;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"id":10,"status":"DONE"}');

    DBMS_LOB.CREATETEMPORARY(l_output, TRUE, DBMS_LOB.CALL);
    l_doc.to_clob(l_output);

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_output));

    DBMS_LOB.FREETEMPORARY(l_output);
END;
/
~~~

This form is useful when the caller wants control over the target locator or wants to reuse an already allocated LOB.

### 11.4. TO_BLOB and UTF-8

TO_BLOB serializes JSON text as a BLOB in UTF-8. This is appropriate when the integration layer requires a byte payload. When exchanging with other systems, align on encoding to prevent corruption of Vietnamese or non-ASCII characters.

### 11.5. Pretty Output and Compact Output

Pretty output adds whitespace and line breaks for readability. Compact output is smaller and suited for transmission. Do not rely on key order or line-break formatting when comparing two JSON objects; if equivalence checks are needed, compare structurally or normalize per application rules.

## 12. Persisting JSON to the Database

JSON_OBJECT_T/JSON_ARRAY_T instances are in-memory PL/SQL objects. They do not automatically become persistent table rows. You must serialize or convert them to a supported SQL JSON type and run DML.

### 12.1. Table Using CLOB and IS JSON

~~~sql
CREATE TABLE json_document_store (
    document_id NUMBER PRIMARY KEY,
    payload     CLOB,
    CONSTRAINT json_document_store_ck
        CHECK (payload IS JSON)
);
~~~

The IS JSON constraint ensures CLOB contents conform to JSON syntax across inserts/updates from different clients.

### 12.2. Parse, Modify, and UPDATE

~~~sql
DECLARE
    l_payload CLOB;
    l_doc     JSON_OBJECT_T;
    l_output  CLOB;
BEGIN
    SELECT payload
    INTO l_payload
    FROM json_document_store
    WHERE document_id = 1
    FOR UPDATE;

    l_doc := JSON_OBJECT_T.parse(l_payload);
    l_doc.on_error(1);

    l_doc.put('status', 'APPROVED');
    l_doc.put('approvedBy', 'APP_USER');

    l_output := l_doc.to_clob();

    UPDATE json_document_store
    SET payload = l_output
    WHERE document_id = 1;

    COMMIT;

    IF l_output IS NOT NULL
       AND DBMS_LOB.ISTEMPORARY(l_output) = 1
    THEN
        DBMS_LOB.FREETEMPORARY(l_output);
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        IF l_output IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_output) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_output);
        END IF;

        ROLLBACK;
        RAISE;
END;
/
~~~

SELECT FOR UPDATE locks the row in the transaction so two sessions do not concurrently read the same document and overwrite each other's changes. In real applications, transaction boundaries usually belong to the caller or service layer; the COMMIT inside this block is illustrative.

### 12.3. Native JSON Data Type

Modern Oracle releases provide the native SQL JSON data type. Specific capabilities depend on the database version and compatibility settings. When using native JSON, you can convert between JSON DOM object types and SQL JSON data using supported APIs such as TO_JSON or corresponding constructors in releases that provide them.

When using textual CLOB/BLOB storage, serialize JSON to text before writing to the column. Do not assume a JSON_OBJECT_T instance can be persisted directly as a PL/SQL variable.

### 12.4. Verifying After Saving

~~~sql
SELECT document_id,
       JSON_VALUE(payload, '$.status') AS status,
       JSON_VALUE(payload, '$.approvedBy') AS approved_by
FROM json_document_store
WHERE document_id = 1;
~~~

Use SQL/JSON to verify that the attributes were saved. This also allows other SQL consumers to read the JSON data without invoking PL/SQL DOM.

## 13. Combining with SQL/JSON

PL/SQL JSON DOM and SQL/JSON solve different needs.

| Need | Suitable Tool |
| --- | --- |
| Editing multiple nodes with procedural logic | JSON_OBJECT_T / JSON_ARRAY_T |
| Recursively traversing a JSON tree | JSON_ELEMENT_T and subtypes |
| Extracting a scalar across many rows | JSON_VALUE |
| Extracting a JSON fragment | JSON_QUERY |
| Checking path existence | JSON_EXISTS |
| Turning arrays/objects into relational rows | JSON_TABLE |
| Generating JSON from SQL columns | JSON_OBJECT / JSON_ARRAY |
| Updating JSON by path in SQL | JSON_TRANSFORM when supported by version |

### 13.1. JSON_VALUE

~~~sql
SELECT document_id,
       JSON_VALUE(payload, '$.customer.name') AS customer_name
FROM json_document_store;
~~~

JSON_VALUE extracts a scalar by path. If you only need a few attributes across many rows, you usually do not need to parse the entire document into a DOM inside a PL/SQL loop.

### 13.2. JSON_QUERY

~~~sql
SELECT JSON_QUERY(payload, '$.customer')
FROM json_document_store;
~~~

JSON_QUERY returns an object/array fragment by path.

### 13.3. JSON_EXISTS

~~~sql
SELECT document_id
FROM json_document_store
WHERE JSON_EXISTS(payload, '$.items[*]?(@.quantity > 1)');
~~~

JSON_EXISTS checks whether a path matches data. Filter path syntax must be compatible with your Oracle version.

### 13.4. JSON_TABLE

~~~sql
SELECT d.document_id,
       jt.sku,
       jt.quantity
FROM json_document_store d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             sku      VARCHAR2(30) PATH '$.sku',
             quantity NUMBER       PATH '$.quantity'
         )
     ) jt;
~~~

JSON_TABLE turns each item into a relational row. For set-based queries across many documents, this is usually clearer and more efficient than a PL/SQL loop parsing each document.

## 14. Validation and Protecting Input Data

PARSE checks JSON syntax, not the entire schema or business rules.

### 14.1. Checking Required Keys

~~~sql
IF NOT l_doc.has('orderId') THEN
    RAISE_APPLICATION_ERROR(-20010, 'Missing orderId');
END IF;
~~~

### 14.2. Checking JSON Types

~~~sql
l_element := l_doc.get('amount');

IF l_element IS NULL OR NOT l_element.is_number() THEN
    RAISE_APPLICATION_ERROR(-20011, 'amount must be a number');
END IF;

l_amount := l_doc.get_number('amount');
~~~

Checking types before calling getters prevents unwanted implicit conversions.

### 14.3. Checking Business Ranges

~~~sql
IF l_amount <= 0 OR l_amount > 1000000000 THEN
    RAISE_APPLICATION_ERROR(-20012, 'amount is outside allowed range');
END IF;
~~~

A value of type NUMBER can still violate business constraints.

### 14.4. Checking Arrays and Individual Elements

~~~sql
IF NOT l_doc.has('items') THEN
    RAISE_APPLICATION_ERROR(-20013, 'Missing items');
END IF;

l_element := l_doc.get('items');

IF NOT l_element.is_array() THEN
    RAISE_APPLICATION_ERROR(-20014, 'items must be an array');
END IF;

l_items := l_doc.get_array('items');

IF l_items.get_size() = 0 THEN
    RAISE_APPLICATION_ERROR(-20015, 'items cannot be empty');
END IF;
~~~

Then iterate over each item, verify it is an object, and confirm required keys such as sku, quantity, and price exist.

### 14.5. Payload Limits

For JSON received from clients:
- Enforce payload size limits.
- Enforce maximum nesting depth.
- Limit the number of array elements.
- Validate datatypes and ranges.
- Avoid logging full payloads if they contain personal data or secrets.
- Never use JSON keys/values directly as dynamic SQL identifiers without strict control.

## 15. Dates and Times in JSON

Standard JSON has no dedicated DATE or TIMESTAMP datatype. Date-time values are usually represented as ISO 8601 strings, for example:

~~~json
{"createdAt":"2026-11-14T10:30:00+00:00"}
~~~

When parsing JSON text like the above, createdAt is a JSON string. Use GET_STRING and convert with TO_TIMESTAMP_TZ using an explicit format model:

~~~sql
l_text := l_doc.get_string('createdAt');

l_created_at := TO_TIMESTAMP_TZ(
    l_text,
    'YYYY-MM-DD"T"HH24:MI:SSTZH:TZM'
);
~~~

PL/SQL JSON types also have overloads accepting DATE/TIMESTAMP when constructing scalars in memory; when serialized, the value is formatted as an ISO 8601 string. However, after parsing ordinary JSON text, a date string remains a string and does not automatically become a SQL DATE.

Align time zones and formats between producer and consumer. Do not rely on the session's default NLS_DATE_FORMAT.

## 16. Recursive JSON Tree Traversal and Depth Limits

When the structure is dynamic, you can write a recursive procedure accepting JSON_ELEMENT_T. Check the type before TREAT and enforce a depth limit.

~~~sql
CREATE OR REPLACE PROCEDURE inspect_json_tree (
    p_element IN JSON_ELEMENT_T,
    p_depth   IN PLS_INTEGER DEFAULT 0
) IS
    l_object JSON_OBJECT_T;
    l_array  JSON_ARRAY_T;
    l_keys   JSON_KEY_LIST;
    l_child  JSON_ELEMENT_T;
    l_type   VARCHAR2(20);
BEGIN
    IF p_element IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('PL/SQL NULL');
        RETURN;
    END IF;

    IF p_depth > 50 THEN
        RAISE_APPLICATION_ERROR(-20020, 'JSON nesting is too deep');
    END IF;

    IF p_element.is_object() THEN
        l_object := TREAT(p_element AS JSON_OBJECT_T);
        l_keys := l_object.get_keys();

        FOR i IN 1 .. l_keys.COUNT LOOP
            l_child := l_object.get(l_keys(i));
            inspect_json_tree(l_child, p_depth + 1);
        END LOOP;

    ELSIF p_element.is_array() THEN
        l_array := TREAT(p_element AS JSON_ARRAY_T);

        IF l_array.get_size() > 0 THEN
            FOR i IN 0 .. l_array.get_size() - 1 LOOP
                l_child := l_array.get(i);
                inspect_json_tree(l_child, p_depth + 1);
            END LOOP;
        END IF;

    ELSE
        IF p_element.is_string() THEN
            l_type := 'STRING';
        ELSIF p_element.is_number() THEN
            l_type := 'NUMBER';
        ELSIF p_element.is_boolean() THEN
            l_type := 'BOOLEAN';
        ELSIF p_element.is_null() THEN
            l_type := 'NULL';
        ELSE
            l_type := 'SCALAR';
        END IF;

        DBMS_OUTPUT.PUT_LINE(
            l_type || ': ' || p_element.to_string()
        );
    END IF;
END inspect_json_tree;
/
~~~

A deeply nested JSON document can cause recursion to consume stack and CPU. If you only need fixed paths, direct access is simpler. For untrusted payloads, cap both nesting depth and total visited nodes.

## 17. Oracle Versions and Compatibility

PL/SQL JSON object types such as JSON_ELEMENT_T, JSON_OBJECT_T, JSON_ARRAY_T, and JSON_SCALAR_T were introduced in Oracle Database 12c Release 2 (12.2). Later releases expanded the API and interoperability with SQL JSON.

When deploying:
- Check the Oracle version and compatibility setting.
- Verify that JSON packages/types exist and execution privileges are granted.
- Verify PARSE/TO_CLOB/TO_BLOB overloads on the datatypes in use.
- The native SQL JSON data type is only available in supported releases.
- JSON_TRANSFORM and newer path features are release-dependent.
- Do not use newer methods if the production database does not support them yet.

Check the version:

~~~sql
SELECT banner
FROM v$version;
~~~

If you lack privilege to read V$VERSION, ask the DBA or query an authorized version view.

## 18. Performance and Memory Management

JSON DOM builds a tree in memory. For large documents, the cost is not just the source CLOB size, but also object/array nodes, scalar values, copies, and serialized output.

Principles:
1. Parse once and reuse the tree when reading multiple attributes.
2. Do not re-parse the same document for each key.
3. Avoid CLONE on the entire document if you only need to modify one node.
4. Use TO_CLOB instead of TO_STRING for large documents.
5. Free temporary LOBs allocated by TO_CLOB/GET_CLOB when no longer needed.
6. Use set-based SQL/JSON when querying across many rows.
7. Cap input payload size, nesting depth, and element counts.
8. Do not print large payloads to DBMS_OUTPUT in production.
9. Do not retain DOM trees in package globals longer than necessary.
10. Measure PGA, CPU, and TEMP usage with representative data.

### 18.1. When Is DOM Appropriate?

DOM fits well when:
- Multiple nodes in a single document must be modified.
- Branching logic depends on the JSON structure.
- Recursive tree traversal is required.
- Complex payloads are assembled from multiple sources.
- Documents are small enough to hold their trees in memory.

### 18.2. When Should SQL/JSON Be Used?

SQL/JSON fits well when:
- Rows must be filtered by JSON properties.
- A few scalars are projected from many documents.
- Arrays must be unnested into relational rows.
- Set-based operations can run in a single SQL statement.
- Keeping and editing the full tree in PL/SQL is unnecessary.

## 19. Comprehensive Example: Updating an Order JSON Document

Create a sandbox table:

~~~sql
CREATE TABLE json_order_demo (
    order_id NUMBER PRIMARY KEY,
    payload  CLOB,
    CONSTRAINT json_order_demo_ck CHECK (payload IS JSON)
);
~~~

Insert a document:

~~~sql
INSERT INTO json_order_demo(order_id, payload)
VALUES (
    1,
    '{
       "orderId":1,
       "status":"NEW",
       "customer":{"id":25,"name":"An"},
       "items":[
          {"sku":"KB-01","quantity":2,"price":150000},
          {"sku":"MS-02","quantity":1,"price":250000}
       ]
     }'
);

COMMIT;
~~~

Parse, validate, update, and save:

~~~sql
DECLARE
    l_payload  CLOB;
    l_doc      JSON_OBJECT_T;
    l_customer JSON_OBJECT_T;
    l_items    JSON_ARRAY_T;
    l_item     JSON_OBJECT_T;
    l_output   CLOB;
BEGIN
    SELECT payload
    INTO l_payload
    FROM json_order_demo
    WHERE order_id = 1
    FOR UPDATE;

    l_doc := JSON_OBJECT_T.parse(l_payload);
    l_doc.on_error(1);

    IF NOT l_doc.has('status') THEN
        RAISE_APPLICATION_ERROR(-20030, 'Missing status');
    END IF;

    l_doc.put('status', 'PROCESSING');

    l_customer := l_doc.get_object('customer');
    l_customer.put('name', 'An Nguyen');

    l_items := l_doc.get_array('items');

    IF l_items.get_size() > 0 THEN
        -- GET_OBJECT returns a reference to the child object inside the array.
        l_item := l_items.get_object(0);
        l_item.put('quantity', 3);
    END IF;

    l_item := JSON_OBJECT_T();
    l_item.put('sku', 'HD-03');
    l_item.put('quantity', 1);
    l_item.put('price', 500000);
    l_items.append(l_item);

    l_output := l_doc.to_clob();

    UPDATE json_order_demo
    SET payload = l_output
    WHERE order_id = 1;

    COMMIT;

    IF l_output IS NOT NULL
       AND DBMS_LOB.ISTEMPORARY(l_output) = 1
    THEN
        DBMS_LOB.FREETEMPORARY(l_output);
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        IF l_output IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_output) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_output);
        END IF;

        ROLLBACK;
        RAISE;
END;
/
~~~

Verify the data:

~~~sql
SELECT order_id,
       JSON_VALUE(payload, '$.status') AS status,
       JSON_VALUE(payload, '$.customer.name') AS customer_name,
       JSON_VALUE(payload, '$.items[0].quantity') AS first_quantity
FROM json_order_demo
WHERE order_id = 1;
~~~

Expected result: status is PROCESSING, customer_name is An Nguyen, and first_quantity is 3.

Clean up the sandbox:

~~~sql
DROP TABLE json_order_demo PURGE;
~~~

DROP is DDL and triggers an implicit commit; perform cleanup only when you are sure this is the practice sandbox table.

## 20. Common Errors When Manipulating JSON DOM

| Situation | Cause | Resolution |
| --- | --- | --- |
| Parse error | Malformed JSON syntax | Validate input and handle parse errors |
| Wrong root type | Using JSON_OBJECT_T for a root array | Choose the matching PARSE subtype |
| GET_OBJECT returns NULL | Missing key or node is not an object | Use HAS, IS_OBJECT, and ON_ERROR |
| ORA-30625 | Calling a method on a NULL JSON object instance | Check locator/object before calling |
| Getter returns unexpected NULL | Default ON_ERROR behavior or missing key | Set ON_ERROR and check HAS |
| Getter performs unwanted conversion | GET_STRING/GET_NUMBER may convert | Check IS_* or GET_TYPE first |
| JSON array reads wrong element | Using 1-based indexing | Use 0-based indexing |
| PUT on array increases element count | PUT inserts and shifts by default | Pass OVERWRITE TRUE to replace |
| REMOVE shifts indices | Subsequent elements move down | Recalculate indices after deletion |
| Child edit missing in clone | Editing a different reference or clone | Clarify reference/value semantics |
| Editing copy affects original tree | GET_OBJECT returns a reference | Call CLONE before editing |
| JSON null treated as missing | Not using HAS/IS_NULL separately | Distinguish missing keys from JSON null |
| Tree modified but table unchanged | Not serialized and persisted via DML | Call TO_CLOB/TO_STRING then INSERT/UPDATE |
| TO_STRING exceeds limit | Document larger than VARCHAR2 buffer | Use TO_CLOB |
| Temporary CLOB leaked | Serialized result not freed | Check ISTEMPORARY then FREETEMPORARY |
| Traversal too deep | Unbounded recursion | Cap depth and node count |
| Repeated parsing per key | Parsing the same document multiple times | Parse once and reuse the DOM |

## 21. JSON Processing Workflow in PL/SQL

A document processing pipeline typically includes:

1. Receive JSON text from a CLOB/BLOB or integration source.
2. Check for SQL NULL and size limits.
3. Parse with JSON_OBJECT_T or JSON_ARRAY_T matching the root type.
4. Configure ON_ERROR per validation policy.
5. Check required keys using HAS.
6. Distinguish missing keys, JSON null, and PL/SQL NULL.
7. Check datatypes with IS_OBJECT, IS_ARRAY, IS_STRING, IS_NUMBER, or IS_BOOLEAN.
8. Retrieve scalars with GET_STRING/GET_NUMBER/GET_BOOLEAN.
9. Retrieve composite nodes with GET/GET_OBJECT/GET_ARRAY while accounting for reference semantics.
10. Use CLONE when an independent data branch is needed.
11. Mutate the tree with PUT, PUT_NULL, APPEND, REMOVE, or RENAME_KEY.
12. For arrays, distinguish PUT insert from PUT overwrite.
13. Validate business rules and document limits.
14. Serialize with TO_CLOB if the document may be large.
15. Execute INSERT/UPDATE inside an appropriate transaction.
16. Free temporary LOBs created during serialization.
17. Log parse/validation/DML errors without masking original exceptions.

## 22. Common Misconceptions

**JSON_OBJECT_T is a JSON column in a table.** False. It is an in-memory PL/SQL object; it must be serialized or converted to a version-appropriate SQL JSON type before storing.

**GET always returns VARCHAR2.** False. GET returns JSON_ELEMENT_T; typed getters return PL/SQL scalars.

**JSON arrays start at index 1.** False. JSON_ARRAY_T uses 0-based indexing.

**JSON objects preserve the exact key order from the source text.** Do not rely on key order; use an array if ordering is business data.

**A non-existent key is the same as a key with JSON null.** False. HAS distinguishes missing keys; IS_NULL identifies JSON null.

**PUT on an array overwrites elements by default.** False. PUT inserts at the index and shifts later elements; pass OVERWRITE TRUE to replace.

**GET_OBJECT always produces an independent copy.** False. Composite object/array nodes are returned with reference semantics; use CLONE for a deep copy.

**Modifying a child object requires calling PUT back on the parent object.** Not necessary when modifying a referenced node obtained from the parent tree. Calling PUT again may be redundant.

**GET_NUMBER and GET_STRING never convert types.** False. Getters may convert when possible; check IS_* when exact datatypes are required.

**JSON null is PL/SQL NULL.** False. JSON null is a node in the JSON tree; PL/SQL NULL is the state of a variable/locator.

**Successful parsing means business-valid data.** False. You still need to validate keys, types, ranges, permissions, and relational integrity.

**TO_STRING works for every document.** False. VARCHAR2 has size limits; use TO_CLOB for large documents.

**TO_CLOB just returns text and needs no cleanup.** False. The function form can allocate a temporary CLOB; check ISTEMPORARY and free it when done.

**PL/SQL DOM is always better than SQL/JSON.** False. DOM suits procedural tree edits; SQL/JSON suits querying and set-based processing.

**Modifying the DOM automatically updates the table.** False. You must serialize and execute DML.

## 23. Practice Exercises

1. Parse a JSON object with id, name, and active using JSON_OBJECT_T.
2. Parse a root array using JSON_ARRAY_T.
3. Explain the roles of JSON_ELEMENT_T and JSON_SCALAR_T.
4. Create an empty object and add three scalars with PUT.
5. Add JSON null using PUT_NULL.
6. Use HAS to check whether a key exists.
7. Distinguish a missing key from a key containing JSON null.
8. Retrieve a string with GET_STRING and a number with GET_NUMBER.
9. Retrieve a boolean with GET_BOOLEAN.
10. Use GET_OBJECT to read a nested customer object.
11. Use GET_ARRAY to retrieve the items list.
12. Use GET_KEYS to iterate through all keys.
13. Explain why you should not depend on object key order.
14. Create a JSON_ARRAY_T and APPEND a string, number, and boolean.
15. Add JSON null to an array using APPEND_NULL.
16. Iterate over an array starting at index 0.
17. Use default PUT to insert an element into the middle of an array.
18. Use PUT with OVERWRITE TRUE to replace an element.
19. Delete an element with REMOVE and observe the shifting indices.
20. Create a child object and PUT it into a root object.
21. Compare reference semantics and value semantics.
22. Use CLONE to create an independent copy of an object.
23. Write a recursive procedure to traverse a JSON tree with a depth limit.
24. Enable ON_ERROR(1) and try reading a missing key.
25. Enable ON_ERROR(3) and try reading a number from a JSON string.
26. Distinguish TO_STRING, TO_CLOB, and TO_BLOB.
27. Serialize an object and store it in a CLOB column with an IS JSON constraint.
28. Use JSON_TABLE to project an items array into rows.
29. Compare when to use JSON_OBJECT_T versus JSON_VALUE/JSON_TABLE.
30. Build a procedure that updates status, customer, and items of an order JSON document and saves it within a transaction.

**JSON_OBJECT_T and JSON_ARRAY_T allow PL/SQL to manipulate JSON as an in-memory tree: parse documents, check types, read scalars, modify nested objects/arrays, and serialize results.** Remember that arrays are 0-indexed, distinguish missing keys from JSON null, understand the reference semantics of GET, and use CLONE when an independent copy is needed. Enable appropriate ON_ERROR settings, pass OVERWRITE TRUE to PUT when replacing array elements, and serialize plus run DML when changes must be persisted.
