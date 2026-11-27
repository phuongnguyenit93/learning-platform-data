# Updating JSON and Checking JSON_TRANSFORM/JSON_MERGEPATCH Syntax by Database Version

JSON is often stored as a document in a VARCHAR2, CLOB, or BLOB column. When part of the information changes, the application does not necessarily have to fetch the entire document, modify it on the client side, and overwrite the whole content. Oracle provides two SQL functions to update JSON declaratively: **JSON_TRANSFORM** and **JSON_MERGEPATCH**.

The two functions serve similar goals, but they express changes differently. JSON_TRANSFORM accepts explicit operations such as SET, REPLACE, INSERT, REMOVE, APPEND, RENAME, and KEEP, each targeting a SQL/JSON path. JSON_MERGEPATCH accepts a patch document conforming to RFC 7396 and merges that patch with the target document. Merge Patch is convenient for updating objects, but has a special rule: a member in the patch with a value of null is interpreted as a request to remove that member. It cannot be used to set a property to JSON null and cannot update an individual array element.

A critical point to verify before deployment is the database version. JSON_MERGEPATCH was introduced in Oracle Database 19c, Release 19.1. JSON_TRANSFORM was introduced in Oracle Database 21c and backported to Oracle Database 19c starting with Release Update 19.10; the initial 19.3 release does not include this function. Therefore, merely seeing a JSON_TRANSFORM page in the 19c documentation is not enough to conclude that every 19c installation supports it. Verify the actual RU/patch level and run a minimal test statement to confirm compilation and execution.

This lesson belongs to the **JSON and XML** group under Database Engine Relational Oracle. It focuses on updating JSON documents, the syntax and semantics of JSON_TRANSFORM/JSON_MERGEPATCH, usage in SELECT and UPDATE, differences between null and remove, array handling, return types, version checking, alternatives on older releases, concurrency, and hands-on practice.

After this lesson, you will be able to:

- Distinguish JSON_TRANSFORM from JSON_MERGEPATCH.
- Identify which database versions/RUs support each function.
- Use JSON_TRANSFORM to add, replace, remove, rename, and keep required paths.
- Use SET, REPLACE, INSERT, REMOVE, APPEND, RENAME, and KEEP with accurate semantics.
- Control ON EXISTING, ON MISSING, and ON NULL.
- Use FORMAT JSON to insert an object, array, or boolean rather than a JSON string.
- Update JSON objects and arrays using SQL/JSON paths.
- Use JSON_MERGEPATCH according to RFC 7396 and understand null/array rules.
- Choose RETURNING CLOB/BLOB when output may exceed VARCHAR2(4000).
- Distinguish functions that return a new JSON document from UPDATE statements that persist changes back to the table.
- Verify feature availability on the actual database rather than inferring from 19c/21c labels.
- Use PL/SQL JSON object types as an alternative when JSON_TRANSFORM is not yet available.
- Protect updates against lost updates and verify updated row counts.

> **Scope of Examples:** Basic examples use VARCHAR2/CLOB JSON and syntax compatible with Oracle Database 19c when the corresponding function is available. JSON_MERGEPATCH is available from 19.1. JSON_TRANSFORM is available from 21c and backported to 19c RU 19.10; it is not present in baseline Oracle 19.3. The native JSON datatype is a separate feature introduced in 21c and is not a prerequisite for using these functions with VARCHAR2/CLOB/BLOB.

## 1. JSON Document Update Model

Suppose an order storage table is defined as:

~~~sql
CREATE TABLE order_document_lab (
    order_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    version_no NUMBER DEFAULT 0 NOT NULL,
    CONSTRAINT ck_order_document_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
~~~

A row may store the document:

~~~json
{
  "orderId": 9001,
  "status": "NEW",
  "customer": {
    "customerId": 501,
    "name": "Nguyen An"
  },
  "total": 125.50,
  "note": null,
  "items": [
    {"productId": 101, "quantity": 2},
    {"productId": 205, "quantity": 1}
  ]
}
~~~

Business requirements might include:

- Changing status from NEW to PAID.
- Updating customer.name.
- Adding a paidAt attribute.
- Removing a legacyCode attribute.
- Setting note to JSON null.
- Appending a product to the end of items.
- Removing an array element or replacing an element at a specific position.

With a client-side read-modify-write approach, the application typically must:

1. SELECT the entire payload.
2. Parse the JSON in the application.
3. Modify the object/array.
4. Serialize the entire document.
5. UPDATE the payload column.

That workflow transfers more data over the network and risks overwriting changes from another session unless concurrency control is enforced. JSON_TRANSFORM and JSON_MERGEPATCH allow describing changes directly in SQL so the database produces the modified document and writes it in a single UPDATE statement.

## 2. Functions Only Return a New Document; UPDATE Persists Changes

This is the most important point when learning these two functions.

### 2.1. Used in SELECT: Produces a Modified Copy in the Result Only

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.status' = 'PAID'
       ) AS updated_payload
FROM order_document_lab
WHERE order_id = 9001;
~~~

SELECT returns the modified document in the query result. The PAYLOAD column in the table remains unchanged.

### 2.2. Used in UPDATE: Writes the New Document to the Table

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.status' = 'PAID'
              )
WHERE order_id = 9001;
~~~

Here, the result of JSON_TRANSFORM is assigned back to the PAYLOAD column. Only this operation updates the stored data.

### 2.3. Same Principle Applies to JSON_MERGEPATCH

Viewing the result only:

~~~sql
SELECT JSON_MERGEPATCH(
           payload,
           '{"status":"PAID"}'
       ) AS patched_payload
FROM order_document_lab
WHERE order_id = 9001;
~~~

Persisting the result:

~~~sql
UPDATE order_document_lab
SET payload = JSON_MERGEPATCH(
                  payload,
                  '{"status":"PAID"}'
              )
WHERE order_id = 9001;
~~~

### 2.4. Functions Do Not Auto-COMMIT

JSON_TRANSFORM and JSON_MERGEPATCH are SQL functions that return values. They do not commit transactions automatically. UPDATE still follows standard transaction semantics:

- A successful UPDATE produces uncommitted changes.
- COMMIT confirms the changes.
- ROLLBACK discards uncommitted changes.
- Row locks are held for the transaction until the transaction ends.

Do not confuse the atomicity of a single JSON_TRANSFORM call with committing the transaction containing the UPDATE statement.

## 3. What Is JSON_TRANSFORM?

JSON_TRANSFORM is a SQL function that accepts a JSON document and one or more modification operations. Each operation specifies a path identifying the target data and describes how to modify it.

### 3.1. Key Characteristics

- Multiple locations can be modified in a single call.
- Operations execute sequentially in the order written.
- Later operations see the results of earlier operations.
- The function builds the modified JSON copy and returns it to SQL.
- If any operation raises an error, the entire JSON_TRANSFORM call fails; no partially modified result is returned.
- Can be used in SELECT for transient transformations or in UPDATE to save changes.

### 3.2. General Syntax

~~~sql
JSON_TRANSFORM(
    json_document,
    operation_1,
    operation_2,
    ...
    RETURNING return_type
    PASSING bind_value AS "variable_name"
)
~~~

RETURNING and PASSING are optional clauses depending on supported syntax. RETURNING specifies the SQL data type of the output. PASSING passes SQL values to be referenced in SQL/JSON path expressions.

### 3.3. Primary Operations

| Operation | Purpose | Notable Default Behavior |
| --- | --- | --- |
| SET | Assign a value to a path | Replaces value if present; creates path if missing |
| REPLACE | Replace an existing value | Ignores if path does not exist |
| INSERT | Insert a field/array element | Errors if object field already exists |
| REMOVE | Delete a field/array element | Ignores if path does not exist |
| APPEND | Add an element to the end of an array | Errors if path does not point to an array |
| RENAME | Rename an object field | Ignores if field does not exist |
| KEEP | Retain only the specified paths | Deletes the rest of the document |

Do not rely solely on operation names instead of checking default handlers. SET and REPLACE are similar but differ in how they handle non-existent paths.

## 4. SET: Create or Replace a Value

SET behaves like an UPSERT on a path:

- If the path already exists, replace the current value.
- If the path does not yet exist, create the data at the specified location where possible.

### 4.1. Replacing status

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.status' = 'PAID'
              )
WHERE order_id = 9001;
~~~

If status was NEW, the result becomes PAID. The SQL string PAID is serialized as the JSON string "PAID".

### 4.2. Adding a New Field

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.paidAt' = SYSTIMESTAMP
              )
WHERE order_id = 9001;
~~~

If paidAt does not exist yet, SET creates the field. If it already exists, SET replaces the old value.

### 4.3. SET with ERROR ON EXISTING

If you only want to create a new field and treat an existing field as an error:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.externalReference' = 'EXT-9001'
               ERROR ON EXISTING
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

If externalReference already exists, the operation raises an error. This expresses intent more clearly than reading first to decide whether to insert.

### 4.4. SET with IGNORE ON MISSING

If you only want to update the field when it already exists:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.customer.name' = 'An Nguyen'
               IGNORE ON MISSING
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

If the path does not match, the document remains unchanged for this operation.

### 4.5. SET Does Not Automatically Create All Parent Objects

If a parent path such as customer does not exist, whether a nested path is created depends on handler/path semantics and the input data. Test the missing-parent-object case. If you need to create the parent object as well, SET the parent object using FORMAT JSON first, then modify child fields in subsequent operations.

## 5. REPLACE: Replace Only When the Path Exists

REPLACE updates the value at an existing path. If the path does not exist, it ignores the operation by default instead of creating a new field.

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  REPLACE '$.status' = 'SHIPPED'
              )
WHERE order_id = 9001;
~~~

If status exists, its value becomes SHIPPED. If status does not exist, the operation adds no field.

### 5.1. REPLACE with ERROR ON MISSING

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           REPLACE '$.status' = 'SHIPPED'
               ERROR ON MISSING
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

Use this when path existence is mandatory. If the field is missing, the error flags that the document is not in the expected state.

### 5.2. SET or REPLACE?

| Requirement | Operation |
| --- | --- |
| Replace if present, create if absent | SET |
| Replace only if already present | REPLACE |
| Raise error if path does not exist | REPLACE ... ERROR ON MISSING |
| Raise error if field already exists when creating | SET ... ERROR ON EXISTING or INSERT |

## 6. INSERT: Inserting a Field or Array Element

INSERT requires a valid target location. For an object field, it errors by default if the field already exists. For an array, the path specifies the insertion index.

### 6.1. Adding a New Field

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           INSERT '$.sourceSystem' = 'ERP'
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

If sourceSystem already exists, the operation errors by default. When your goal is creation and you want to detect duplicates, this default behavior is helpful.

### 6.2. INSERT Array Element

JSON arrays use 0-based indexing in SQL/JSON paths.

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           INSERT '$.items[0]' =
               '{"productId":999,"quantity":1}'
               FORMAT JSON
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

The new element is inserted at the first position and existing elements shift right. FORMAT JSON causes the SQL string value to be parsed as a JSON object. Without FORMAT JSON, that content is stored as a JSON string.

### 6.3. Inserting After the End of an Array

You can specify an array position path past the last element according to supported SQL/JSON path syntax, or use APPEND to clearly express appending to the end of the array.

### 6.4. Inserting Beyond the End of an Array

Per JSON_TRANSFORM semantics, INSERT at an array index beyond the last element can extend the array, filling intermediate positions with JSON null. Be careful, as the result may contain nulls in positions business logic does not expect.

## 7. APPEND: Adding an Element to the End of an Array

APPEND is suitable when you want to add an element to the end of an array.

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  APPEND '$.items' =
                      '{"productId":310,"quantity":3}'
                      FORMAT JSON
              )
WHERE order_id = 9001;
~~~

If items is an array, the new object is appended to the end. If the path does not point to an array, it raises an error by default.

### 7.1. Creating an Array If the Path Does Not Exist

You can specify CREATE ON MISSING for APPEND where syntax allows:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           APPEND '$.tags' = 'priority'
               CREATE ON MISSING
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

CREATE ON MISSING creates a singleton array at the path if the path does not exist. Distinguish between a missing path and a path that already exists as a non-array value.

### 7.2. How APPEND Differs from INSERT

- APPEND explicitly expresses adding to the end of an array.
- INSERT allows choosing a specific index and can shift existing elements.
- SET at an array index replaces or creates an element depending on the handler.

## 8. REMOVE: Deleting a Field or Array Element

REMOVE deletes data matching the path.

### 8.1. Deleting a Field

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  REMOVE '$.legacyCode'
              )
WHERE order_id = 9001;
~~~

If legacyCode does not exist, no error is raised by default.

### 8.2. Deleting an Array Element

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           REMOVE '$.items[1]'
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

The element at index 1 is removed and subsequent elements shift down. Array indices start at 0.

### 8.3. Raising an Error When the Path Does Not Exist

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           REMOVE '$.legacyCode' ERROR ON MISSING
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

Use ERROR ON MISSING when failing to find the field indicates the document violates its contract.

### 8.4. Cannot REMOVE Root

You cannot use REMOVE '$' to delete the entire document root. If you need to replace the document completely, assign a new document via UPDATE or use an appropriate operation.

## 9. RENAME: Renaming an Object Field

RENAME renames the field specified by the path. The field's value is preserved.

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           RENAME '$.customer.fullName' = 'name'
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

The expression after the equals sign must be a SQL string providing the new name. If the path does not exist, it is ignored by default; you can use ERROR ON MISSING when required.

RENAME applies to object fields, not to renaming array elements. To alter array structures, use SET/INSERT/REMOVE as appropriate.

## 10. KEEP: Retaining Only Selected Paths

KEEP removes all data except what is retained by the specified paths. The root object/array is not deleted; it becomes an empty object/array if no matching components remain.

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           KEEP '$.orderId',
                '$.status',
                '$.total'
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

The result keeps only orderId, status, and total along with the required parent structure. KEEP is useful for producing a field-filtered JSON payload before sending it to a client.

### 10.1. Use KEEP Carefully

KEEP is an operation that discards most data outside the listed paths. If you omit a required field, that field disappears from the output. Before using it for data export, validate the output schema with test cases.

## 11. ON EXISTING, ON MISSING, and ON NULL

Handlers allow defining behavior when a path exists, does not exist, or when the SQL expression evaluates to NULL.

### 11.1. ON EXISTING

Applies when the path matches existing data:

| Handler | Behavior |
| --- | --- |
| ERROR ON EXISTING | Raises an error |
| IGNORE ON EXISTING | Leaves existing data unchanged |
| REPLACE ON EXISTING | Replaces existing data with the new value |
| REMOVE ON EXISTING | Deletes the existing data |

Not every operation supports every handler. For example, INSERT defaults to ERROR ON EXISTING; SET defaults to REPLACE ON EXISTING.

### 11.2. ON MISSING

Applies when the path does not match:

| Handler | Behavior |
| --- | --- |
| ERROR ON MISSING | Raises an error |
| IGNORE ON MISSING | Leaves data unchanged |
| CREATE ON MISSING | Creates data at the path if supported by the operation |

Example:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           REPLACE '$.status' = 'PAID'
               ERROR ON MISSING
       )
FROM order_document_lab;
~~~

### 11.3. ON NULL

Applies when the SQL result expression after the equals sign returns SQL NULL:

| Handler | Behavior |
| --- | --- |
| NULL ON NULL | Writes JSON null at the target location |
| ERROR ON NULL | Raises an error |
| IGNORE ON NULL | Leaves data unchanged |
| REMOVE ON NULL | Deletes data at the target location |

For operations supporting ON NULL, the default is typically NULL ON NULL.

### 11.4. SQL NULL vs. JSON null

When using SET:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.note' = NULL
               NULL ON NULL
       )
FROM order_document_lab;
~~~

The result sets the note property to JSON null.

If you use:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.note' = NULL
               REMOVE ON NULL
       )
FROM order_document_lab;
~~~

then the note property is deleted.

If you use IGNORE ON NULL, the current value is kept unchanged. These three behaviors carry different business meanings.

## 12. FORMAT JSON: Inserting a JSON Value Instead of a String

A SQL string is converted into a JSON string unless FORMAT JSON is specified.

### 12.1. Without FORMAT JSON

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.customer' =
               '{"customerId":501,"name":"An"}'
       )
FROM order_document_lab;
~~~

The customer value becomes a JSON string containing text with curly braces, not a nested JSON object.

### 12.2. With FORMAT JSON

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.customer' =
               '{"customerId":501,"name":"An"}'
               FORMAT JSON
       )
FROM order_document_lab;
~~~

Now customer is a JSON object.

### 12.3. Assigning a JSON Boolean

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.allowPartialShipment' = 'true'
               FORMAT JSON
       )
FROM order_document_lab;
~~~

FORMAT JSON causes the string true to be interpreted as the JSON boolean true. Without FORMAT JSON, the result is the JSON string "true".

### 12.4. Assigning an Array

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.tags' = '["priority","online"]'
               FORMAT JSON
       )
FROM order_document_lab;
~~~

Do not use FORMAT JSON on uncontrolled data or non-well-formed JSON. FORMAT JSON is an assertion by the SQL author that the expression contains valid JSON.

## 13. Multiple Operations in One JSON_TRANSFORM Call

Operations execute sequentially. Each operation sees the result of the preceding one.

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.status' = 'PAID',
                  SET '$.paidAt' = SYSTIMESTAMP,
                  REMOVE '$.temporaryFlag',
                  APPEND '$.history' = 'PAID'
              )
WHERE order_id = 9001;
~~~

This example:

1. Sets status to PAID.
2. Adds or replaces paidAt.
3. Removes temporaryFlag if it exists.
4. Appends PAID to the end of the history array.

If the fourth operation fails because history is not an array, the entire JSON_TRANSFORM call errors. Prior operations do not produce a partially updated result.

### 13.1. Operation Order Matters

Example:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.status' = 'PAID',
           RENAME '$.status' = 'paymentStatus'
       )
FROM order_document_lab;
~~~

The RENAME operation runs after SET, so it sees the newly updated status field. The final result has paymentStatus with value PAID.

### 13.2. Paths Must Match the Structure at Execution Time

If an earlier operation deletes a parent object, a later operation modifying a child field of that object will no longer match. Order operations so that data creations/updates occur before deletions.

### 13.3. Function Atomicity and UPDATE Transactions

JSON_TRANSFORM is atomic at the scope of a single function call: either all operations succeed, or the function returns no partial edit. The UPDATE statement containing the function is still a statement within a transaction; if the statement fails, the statement rolls back per SQL semantics. COMMIT/ROLLBACK remains controlled by the caller.

## 14. RETURNING and Output Size

The default return data type depends on the input type and database release. For VARCHAR2 input, Oracle 19c documentation states the default result is VARCHAR2(4000), even if the input column is declared larger. For CLOB/BLOB, the default preserves the input type per 19c documentation. You can specify RETURNING explicitly.

### 14.1. Returning CLOB

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.status' = 'PAID'
           RETURNING CLOB
       )
FROM order_document_lab;
~~~

RETURNING CLOB is appropriate when results may exceed the VARCHAR2 limit.

### 14.2. Returning BLOB

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           REMOVE '$.internalNotes'
           RETURNING BLOB
       )
FROM order_document_lab;
~~~

BLOB JSON text must follow UTF-8 encoding per Oracle JSON rules.

### 14.3. Pretty Output

Some JSON SQL functions support PRETTY for human-readable formatting. Pretty-printing increases string size; do not enable it if the output is for storage or compact transmission without formatting needs.

### 14.4. Native JSON Type

Starting in Oracle Database 21c, the native JSON SQL datatype is available. When the input is of JSON type, the output can preserve native JSON type according to release rules. However, JSON_TRANSFORM can still accept VARCHAR2/CLOB/BLOB on releases supporting the function. You do not have to convert columns to native JSON just to use JSON_TRANSFORM.

## 15. What Is JSON_MERGEPATCH?

JSON_MERGEPATCH applies a patch document to a target JSON document according to IETF RFC 7396.

- Target document: the current document.
- Patch document: an object describing members to add, replace, or remove.
- Result: the new document after merging the patch.

### 15.1. Basic Syntax

~~~sql
JSON_MERGEPATCH(target_document, patch_document)
~~~

Example:

~~~sql
SELECT JSON_MERGEPATCH(
           payload,
           '{"status":"PAID","source":"WEB"}'
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

Status is replaced with PAID and source is newly added.

### 15.2. Used in UPDATE

~~~sql
UPDATE order_document_lab
SET payload = JSON_MERGEPATCH(
                  payload,
                  '{"status":"PAID","source":"WEB"}'
              )
WHERE order_id = 9001;
~~~

The patch document is a JSON object. Patch members are applied recursively against the target object according to RFC 7396.

## 16. Special Null Rule in JSON_MERGEPATCH

This is the most common source of business-logic bugs.

### 16.1. Patch Member Equal to null Means Delete

Target:

~~~json
{
  "status": "NEW",
  "note": "Call customer",
  "priority": "HIGH"
}
~~~

Patch:

~~~json
{
  "note": null
}
~~~

Result:

~~~json
{
  "status": "NEW",
  "priority": "HIGH"
}
~~~

The note property is deleted.

### 16.2. Merge Patch Cannot Set a Property to JSON null

If the requirement is to keep the note property with its value set to JSON null, the patch:

~~~json
{
  "note": null
}
~~~

does not do that; it deletes note per RFC 7396.

Use JSON_TRANSFORM:

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.note' = NULL NULL ON NULL
              )
WHERE order_id = 9001;
~~~

### 16.3. Null in Patch vs. SQL NULL Parameter

JSON null is the null token inside the patch document. SQL NULL passed into the target or patch expression is a SQL NULL value; per Oracle documentation, if either the target or patch document is SQL NULL, JSON_MERGEPATCH returns SQL NULL.

Test these three scenarios separately:

- The SQL column is NULL.
- The JSON document is the literal null.
- The patch object has a member holding JSON null.

They do not share the same semantics.

## 17. How Does JSON_MERGEPATCH Handle Arrays?

JSON Merge Patch works best with JSON objects. For arrays, the patch replaces the entire array at that member; there is no standard operation to edit a single array element.

Target:

~~~json
{
  "items": [
    {"productId": 101, "quantity": 2},
    {"productId": 205, "quantity": 1}
  ]
}
~~~

Patch:

~~~json
{
  "items": [
    {"productId": 101, "quantity": 3}
  ]
}
~~~

Result:

~~~json
{
  "items": [
    {"productId": 101, "quantity": 3}
  ]
}
~~~

The productId 205 element disappears because the entire array was replaced.

### 17.1. When You Need to Modify a Single Array Element

Use JSON_TRANSFORM:

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.items[0].quantity' = 3
              )
WHERE order_id = 9001;
~~~

### 17.2. When You Need to Append to an Array

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  APPEND '$.items' =
                      '{"productId":310,"quantity":1}'
                      FORMAT JSON
              )
WHERE order_id = 9001;
~~~

### 17.3. Choosing Merge Patch or Transform?

| Scenario | JSON_MERGEPATCH | JSON_TRANSFORM |
| --- | --- | --- |
| Replacing multiple object fields | Very suitable | Suitable |
| Adding members to an object | Suitable | Suitable |
| Deleting members via patch null | Yes | Yes, REMOVE |
| Setting a field to JSON null | Not directly | Yes, SET ... NULL ON NULL |
| Editing an individual array element | No | Yes |
| Appending an array element | No | Yes, APPEND |
| Inserting an array element at an index | No | Yes, INSERT |
| Receiving a client-generated patch document | Very suitable | Different model |
| Multiple path-specific operations in one call | Patch described as an object | Very suitable |

## 18. RETURNING and Errors in JSON_MERGEPATCH

JSON_MERGEPATCH has a RETURNING clause to specify the SQL datatype of the output. Oracle 19c documentation states the default RETURNING is VARCHAR2(4000). For large documents, specify an appropriate LOB type.

### 18.1. Returning CLOB

~~~sql
SELECT JSON_MERGEPATCH(
           payload,
           '{"status":"PAID"}'
           RETURNING CLOB
       )
FROM order_document_lab;
~~~

### 18.2. Controlling Errors

JSON_MERGEPATCH supports error clauses:

- NULL ON ERROR: returns SQL NULL when an error occurs; this is the default in Oracle 19c documentation.
- ERROR ON ERROR: raises the corresponding Oracle error.

For critical business data, ERROR ON ERROR ensures data errors are not silently turned into NULL. If choosing NULL ON ERROR, the application must have a way to distinguish processing errors from valid SQL NULL documents.

### 18.3. Target or Patch Is SQL NULL

If the target expression or patch expression is SQL NULL, JSON_MERGEPATCH returns SQL NULL. Handle this explicitly before calling the function if business logic requires keeping the current document, creating an empty object, or skipping the row.

## 19. Comparing JSON_TRANSFORM and JSON_MERGEPATCH

| Criterion | JSON_TRANSFORM | JSON_MERGEPATCH |
| --- | --- | --- |
| How changes are expressed | Operations and SQL/JSON paths | JSON patch document |
| Standard | Oracle SQL function | RFC 7396 |
| Modifying multiple fields | Yes, sequentially | Yes, via object merge |
| Array elements | Edit/insert/delete/append | Replaces entire array only |
| Setting explicit JSON null | Yes | Null member means delete |
| Deleting fields | REMOVE | Patch member set to null |
| Conditional missing/existing | Per-operation handlers | Merge patch semantics |
| Fit for client-sent patches | Possible, but client must build operations | Very suitable |
| Fit for targeted path edits | Very suitable | Less flexible |
| Atomicity | All operations in one call | Applies patch as one merge |
| Version | 21c; backported to 19c RU 19.10 | 19c Release 19.1 |

### 19.1. Quick Selection Rules

- Use JSON_MERGEPATCH if the client already sends a merge-patch document and the structure is primarily objects.
- Use JSON_TRANSFORM if you need precise path edits, array manipulation, or distinguishing set-null from remove.
- Use plain SQL if the change is just a relational field stored in a dedicated column.
- Use PL/SQL JSON object types if the database lacks JSON_TRANSFORM or the document-editing logic is complex.

## 20. Oracle Versions: Support Milestones to Remember

### 20.1. JSON_MERGEPATCH

Oracle Database 19c Release 19.1 lists JSON_MERGEPATCH as a new SQL function for declaratively updating JSON documents.

| Version | JSON_MERGEPATCH |
| --- | --- |
| Oracle 12.2/18c | No SQL function JSON_MERGEPATCH |
| Oracle 19c 19.1 and later | Available |
| Oracle 21c | Available |
| Oracle 23c/23ai | Available |

### 20.2. JSON_TRANSFORM

JSON_TRANSFORM is part of the JSON feature set in Oracle 21c. Oracle backported this function to Oracle Database 19c RU 19.10. Therefore:

| Version | JSON_TRANSFORM |
| --- | --- |
| Initial Oracle 19c 19.3 | Not available |
| Oracle 19c RU 19.10 and later | Available via backport; verify actual patch/RU |
| Oracle 21c | Available |
| Oracle 23c/23ai | Available |

Oracle 19c documentation now includes a JSON_TRANSFORM page and usage guide, but the general reference page does not clearly call out the RU backport. Therefore, do not rely solely on a 19c documentation URL to assume an older 19c database has this function.

### 20.3. Native JSON Datatype Is a Separate Milestone

The native SQL JSON datatype was introduced in Oracle Database 21c. That does not mean JSON_TRANSFORM only runs on 21c+: the function was backported to 19c RU 19.10 to work on VARCHAR2/CLOB/BLOB JSON.

### 20.4. Release Update and Patch Level

When referring to a 19c database, know the exact RU:

- 19.3 is the initial 19c release commonly found in older environments.
- 19.10 and later include the JSON_TRANSFORM backport per Oracle SQL Developer Advocate announcements and observed behavior in newer 19c RU environments.
- One-off patches or bundle patches can also affect actual availability.

Do not upgrade a database just to use one function without evaluating patch policies, support matrices, and compatibility. Check with your DBA and the deployed RU documentation.

## 21. Checking Feature Support on an Actual Database

### 21.1. Check Version

~~~sql
SELECT banner
FROM v$version;
~~~

Or:

~~~sql
SELECT version
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
~~~

### 21.2. Check RU/Patch Level

The DBA can inspect inventory/patch level using the OPatch utility on the Oracle Home host:

~~~text
opatch lsinventory
~~~

Inside the database, the DBA can also query the SQL patch registry:

~~~sql
SELECT patch_id, patch_type, action, status, action_time, description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
~~~

DBA_REGISTRY_SQLPATCH requires appropriate dictionary privileges. The version banner shows the release, not always every applied one-off patch.

### 21.3. Test JSON_MERGEPATCH

~~~sql
SELECT JSON_MERGEPATCH(
           '{"a":1,"b":2}',
           '{"b":3}'
       ) AS result
FROM dual;
~~~

Expected result:

~~~json
{"a":1,"b":3}
~~~

### 21.4. Test JSON_TRANSFORM

~~~sql
SELECT JSON_TRANSFORM(
           '{"a":1}',
           SET '$.b' = 2
       ) AS result
FROM dual;
~~~

Expected result:

~~~json
{"a":1,"b":2}
~~~

If the database reports that the function does not exist or throws a parse error, check the version/RU and patch inventory. Do not conclude the function is missing merely because a test query had a syntax typo.

### 21.5. Test Each Operation

A database having JSON_TRANSFORM does not mean every path/operation you plan to use has been verified. Run tests for:

- SET on existing and missing paths.
- REMOVE on existing and missing paths.
- SET SQL NULL with NULL ON NULL and REMOVE ON NULL.
- FORMAT JSON with object/array/boolean.
- APPEND to an array.
- INSERT at a specific index.
- RETURNING CLOB with large documents.

## 22. Alternatives When JSON_TRANSFORM Is Unavailable

On Oracle 19c below RU 19.10, JSON_MERGEPATCH is still available for updating objects per RFC 7396. If you need to edit arrays or set fields to JSON null, you can use PL/SQL JSON object types or update the full document from the application.

### 22.1. PL/SQL JSON_OBJECT_T

Oracle supports PL/SQL JSON object types such as:

- JSON_ELEMENT_T: base type for JSON values.
- JSON_OBJECT_T: JSON object.
- JSON_ARRAY_T: JSON array.
- JSON_SCALAR_T: JSON scalar.

You can parse a CLOB into an object, edit fields, and serialize it back.

~~~sql
DECLARE
    l_doc CLOB;
    l_json JSON_OBJECT_T;
BEGIN
    SELECT payload
    INTO l_doc
    FROM order_document_lab
    WHERE order_id = 9001
    FOR UPDATE;

    l_json := JSON_OBJECT_T.parse(l_doc);
    l_json.put('status', 'PAID');
    l_json.remove('legacyCode');

    UPDATE order_document_lab
    SET payload = l_json.to_clob()
    WHERE order_id = 9001;

    COMMIT;
END;
/
~~~

This example illustrates the object types API. In production code, handle SQL NULL, parse errors, root object types, and transaction exceptions explicitly. FOR UPDATE holds a row lock while the document is parsed and updated; keep transactions short.

### 22.2. Modifying Arrays with JSON_ARRAY_T

You can extract an array from an object using GET_ARRAY, then use JSON_ARRAY_T methods such as APPEND, PUT, or REMOVE per your release's API:

~~~sql
DECLARE
    l_doc CLOB;
    l_json JSON_OBJECT_T;
    l_items JSON_ARRAY_T;
BEGIN
    SELECT payload
    INTO l_doc
    FROM order_document_lab
    WHERE order_id = 9001
    FOR UPDATE;

    l_json := JSON_OBJECT_T.parse(l_doc);
    l_items := l_json.get_array('items');

    l_items.append(JSON_OBJECT_T.parse(
        '{"productId":310,"quantity":1}'
    ));

    l_json.put('items', l_items);

    UPDATE order_document_lab
    SET payload = l_json.to_clob()
    WHERE order_id = 9001;

    COMMIT;
END;
/
~~~

If the items property does not exist or is not an array, GET_ARRAY may return NULL or behave in ways that must be handled per API docs. Production code must check before calling APPEND.

### 22.3. Pros and Cons of PL/SQL Object Types

Pros:

- Can procedurally edit both objects and arrays.
- Can be used on releases older than JSON_TRANSFORM if PL/SQL JSON types are present.
- Supports complex conditional logic.

Cons:

- More verbose than a SQL expression.
- Requires parsing/serializing the document.
- May hold a row lock throughout processing.
- Must handle object/array/scalar roots and parse errors.

### 22.4. Do Not Substitute Two UPDATEs If One Atomic Statement Is Required

If using JSON_MERGEPATCH twice to delete a field and then add a new value, two UPDATEs are two separate statements within the transaction. They can belong to the same transaction if no COMMIT happens in between, though you must account for round-trips and error handling. When a single statement is required and the function is available, JSON_TRANSFORM or PL/SQL object manipulation can be cleaner.

## 23. Concurrency and Lost Updates

JSON_TRANSFORM and JSON_MERGEPATCH perform updates inside the database, but row locks still operate at the table-row level. They do not create separate locks for individual JSON properties.

### 23.1. Updating the Same Row

Session A:

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.status' = 'PAID'
              )
WHERE order_id = 9001;
~~~

Session B attempting to UPDATE the same order_id will wait until Session A's row lock is released per transaction semantics.

### 23.2. Updating Against the Current Column Value in the Database

The strength of the expression:

~~~sql
SET payload = JSON_TRANSFORM(payload, ...)
~~~

is that the function reads the current column value within the executing statement. The client does not have to send back an entire old document read earlier. This helps avoid a common form of lost update caused by clients overwriting stale snapshots.

### 23.3. Optimistic Locking with a Version Column

If the application read the document earlier and needs to detect any change since that read:

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.status' = 'PAID'
              ),
    version_no = version_no + 1
WHERE order_id = 9001
  AND version_no = :old_version;
~~~

After UPDATE, check SQL%ROWCOUNT:

- 1: update succeeded.
- 0: row does not exist or version has changed; caller must re-read and handle the conflict.

### 23.4. Two Clients Editing Two Different Fields

If both clients submit the full document they read earlier, the second client can overwrite the first client's changes. If each client sends path operations and the database runs JSON_TRANSFORM against the current column value, independent changes are much more likely to be preserved, though row-level transaction serialization still applies.

### 23.5. Never Omit the WHERE Clause

Always filter for the exact rows to update:

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(payload, SET '$.status' = 'PAID')
WHERE order_id = :order_id
  AND JSON_VALUE(payload, '$.status') = 'NEW';
~~~

The status condition can enforce optimistic state transitions per business rules. Check SQL%ROWCOUNT to verify whether any row actually transitioned.

## 24. Indexes, Constraints, and Post-Update Data

### 24.1. CHECK IS JSON Still Applies

If the column has a CHECK constraint:

~~~sql
CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
~~~

then the value returned by JSON_TRANSFORM/JSON_MERGEPATCH must still satisfy the constraint during UPDATE. The functions do not bypass column validation.

### 24.2. JSON_TRANSFORM Does Not Guarantee Business Schema

The function can produce syntactically valid JSON that violates business rules. For example, SET status = 'UNKNOWN' still produces valid JSON. Add business validation at the SQL or application layer.

### 24.3. Function-Based Indexes

If there is an index on JSON_VALUE(payload, '$.status'), updating payload causes related index entries to be maintained per Oracle indexing mechanics. JSON DML updates still incur index maintenance overhead.

### 24.4. JSON Search Indexes

JSON search indexes must also be updated when documents change. If the workload updates JSON frequently and the search index is large, measure DML cost alongside query cost rather than benchmarking the function in isolation.

### 24.5. LOB Storage

With CLOB/BLOB, document size and storage attributes can affect I/O, redo, undo, and update duration. Although JSON_TRANSFORM expresses changes by path, do not assume every storage type/release performs physical updates identically. Benchmark on realistic data.

## 25. Common Errors and Diagnostics

| Error/Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| JSON_TRANSFORM function not recognized | Database 19c below RU 19.10 or missing patch | Check RU/SQL patch registry and test a minimal statement |
| JSON_MERGEPATCH not recognized | Database prior to 19c or incompatible environment/compatibility | Check release and SQL reference |
| ORA-40441 / JSON parse error | Input or patch is not valid JSON | Inspect document, escaping, and JSON constraint |
| ORA-40442 / path expression error | Invalid SQL/JSON path syntax | Check path and array indices |
| Operation ERROR ON EXISTING | Path already holds data | Choose SET/REPLACE or adjust handler |
| ERROR ON MISSING | Path does not exist | Check document shape or use IGNORE/CREATE if appropriate |
| APPEND raises error | Path does not point to an array | Verify path and datatype |
| JSON string appears instead of object | Missing FORMAT JSON | Add FORMAT JSON to JSON text expression |
| Field deleted when intending to set null | Used JSON_MERGEPATCH null member | Use JSON_TRANSFORM SET ... NULL ON NULL |
| Entire array replaced | Used JSON_MERGEPATCH on array member | Use JSON_TRANSFORM to edit elements |
| ORA-02290 | Result violates IS JSON/CHECK constraint | Check output and constraint |
| ORA-12899 or length error | Return type too small | Use RETURNING CLOB/BLOB as appropriate |
| UPDATE modifies no rows | WHERE did not match or business predicate failed | Check SQL%ROWCOUNT and predicate |
| Client overwrites recent changes | Lost update from stale snapshot | Use path updates on current column or version predicate |

## 26. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| Calling JSON_TRANSFORM automatically saves the document | The function returns a new document; you must UPDATE the column to save |
| Calling JSON_MERGEPATCH automatically saves the document | Also requires UPDATE to persist the result |
| JSON_MERGEPATCH and JSON_TRANSFORM are identical | Change expression and null/array semantics differ |
| Merge Patch null sets a field to JSON null | Per RFC 7396, a null member in a patch means delete |
| Merge Patch can edit a single array element | It replaces the entire array at that member |
| JSON_TRANSFORM SET and REPLACE are identical | SET creates missing paths; REPLACE ignores missing paths by default |
| INSERT always overwrites existing fields | INSERT errors by default when an object field already exists |
| APPEND works on any path type | APPEND requires the target to be an array, unless using a create-on-missing handler |
| A SQL string containing an object automatically becomes a JSON object | Requires FORMAT JSON |
| SQL NULL and JSON null are the same | SQL NULL is SQL's null state; JSON null is a scalar inside the document |
| JSON_TRANSFORM is only in 21c+ | Introduced in 21c and backported to 19c RU 19.10 |
| Every Oracle 19c has JSON_TRANSFORM | Baseline 19c 19.3 lacks it; must verify RU |
| JSON_MERGEPATCH is only in 21c+ | Available since Oracle 19c Release 19.1 |
| Native JSON type is required to use JSON_TRANSFORM | Function works with VARCHAR2/CLOB/BLOB on supported releases |
| Atomic function means auto-COMMIT | Function atomicity does not replace transaction control |

## 27. Checklist for Function Selection and Deployment

**Version**

- Does the database run a supported release/RU?
- Is JSON_MERGEPATCH available on baseline 19c?
- Does JSON_TRANSFORM have RU 19.10+ or database 21c+?
- Have you run a capability test on the target database?

**Semantics**

- Replace a field, create a field, or replace only if the field exists?
- Should null fields be deleted or preserved as JSON null?
- Do you need to edit a single array element or replace the entire array?
- Does the operation need ERROR ON MISSING/EXISTING?
- Does the SQL string need FORMAT JSON?

**Datatype**

- Is the input VARCHAR2, CLOB, BLOB, or native JSON?
- Can the output exceed VARCHAR2(4000)?
- Is RETURNING CLOB/BLOB needed?
- Are IS JSON constraints and business validations in place?

**Concurrency**

- Does WHERE target the right row?
- Is a version_no or status predicate needed?
- Is SQL%ROWCOUNT checked?
- Are transactions kept short?

**Performance**

- Are there indexes/search indexes requiring maintenance?
- Have you benchmarked with realistic document sizes?
- Could frequently queried fields be promoted to relational columns?
- Would plain SQL be better than modifying JSON?

## 28. Comprehensive Practice Exercises

This lab creates a JSON document, uses both functions, and compares null/array semantics.

### Step 1 — Create the Table

~~~sql
CREATE TABLE json_update_lab (
    id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    version_no NUMBER DEFAULT 0 NOT NULL,
    CONSTRAINT ck_json_update_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
~~~

### Step 2 — Load the Document

~~~sql
INSERT INTO json_update_lab(id, payload)
VALUES (
    1,
    '{
       "status":"NEW",
       "note":"Call customer",
       "customer":{"id":501,"name":"An"},
       "items":[
         {"productId":101,"quantity":2},
         {"productId":205,"quantity":1}
       ]
     }'
);

COMMIT;
~~~

### Step 3 — JSON_TRANSFORM to Update status and Add a Timestamp

~~~sql
UPDATE json_update_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.status' = 'PAID',
                  SET '$.paidAt' = SYSTIMESTAMP
              ),
    version_no = version_no + 1
WHERE id = 1;
~~~

### Step 4 — Set note to JSON null

~~~sql
UPDATE json_update_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.note' = NULL NULL ON NULL
              )
WHERE id = 1;
~~~

### Step 5 — Append an Item

~~~sql
UPDATE json_update_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  APPEND '$.items' =
                      '{"productId":310,"quantity":3}'
                      FORMAT JSON
              )
WHERE id = 1;
~~~

### Step 6 — Update the Quantity of the First Item

~~~sql
UPDATE json_update_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.items[0].quantity' = 5
              )
WHERE id = 1;
~~~

### Step 7 — Use JSON_MERGEPATCH to Remove note and Add source

~~~sql
UPDATE json_update_lab
SET payload = JSON_MERGEPATCH(
                  payload,
                  '{"note":null,"source":"PORTAL"}'
              )
WHERE id = 1;
~~~

At this point note is deleted, no longer JSON null.

### Step 8 — Inspect the Results

~~~sql
SELECT
    id,
    JSON_VALUE(payload, '$.status') AS status,
    JSON_VALUE(payload, '$.source') AS source,
    JSON_VALUE(payload, '$.note') AS note,
    JSON_QUERY(payload, '$.items' RETURNING CLOB) AS items,
    version_no
FROM json_update_lab;
~~~

### Step 9 — Verify Documents and Constraints

~~~sql
SELECT id
FROM json_update_lab
WHERE payload IS NOT JSON STRICT WITH UNIQUE KEYS;

SELECT constraint_name, status, validated
FROM user_constraints
WHERE table_name = 'JSON_UPDATE_LAB';
~~~

### Step 10 — Clean Up Lab (Optional)

~~~sql
DROP TABLE json_update_lab PURGE;
~~~

Only run if you are sure the table belongs to the lab and the data is no longer needed. DROP is DDL with an implicit commit.

## 29. Self-Check Questions

1. What inputs does JSON_TRANSFORM take?
2. Which standard is JSON_MERGEPATCH based on?
3. Does calling JSON_TRANSFORM in a SELECT save changes to the table?
4. What must you do to persist the function's output?
5. How does SET differ from REPLACE when a path is missing?
6. How does INSERT behave if an object field already exists?
7. What structure is APPEND used for?
8. How does REMOVE behave if a path does not exist?
9. Does RENAME change the field value or the field name?
10. What does KEEP do to data outside the retained paths?
11. In what order do operations in JSON_TRANSFORM execute?
12. What happens if one operation in a JSON_TRANSFORM call errors?
13. How does NULL ON NULL differ from REMOVE ON NULL?
14. Why is FORMAT JSON needed?
15. At what number do array indices start in SQL/JSON paths?
16. How does JSON_MERGEPATCH handle a null patch member?
17. Why cannot Merge Patch be used to set a property to JSON null?
18. How does Merge Patch update arrays?
19. When is JSON_TRANSFORM more suitable than JSON_MERGEPATCH?
20. What problem does RETURNING CLOB solve?
21. From which release was JSON_MERGEPATCH introduced?
22. From which RU is JSON_TRANSFORM available in Oracle 19c?
23. Why can you not assume every 19c database supports JSON_TRANSFORM?
24. Do the native JSON datatype and JSON_TRANSFORM share the same version milestone?
25. How do you verify feature availability on an actual database?
26. What can be used instead of JSON_TRANSFORM on older 19c RUs?
27. Does JSON_TRANSFORM create per-property row locks?
28. How do you detect lost updates from clients using stale snapshots?
29. Why check SQL%ROWCOUNT after UPDATE?
30. Does CHECK IS JSON enforce business rules?

**Suggested Answers:**

1. JSON input, one or more modification operations, and optional RETURNING/PASSING.
2. RFC 7396.
3. No; SELECT only returns the modified copy.
4. Assign the function's result to the column in an UPDATE.
5. SET creates missing paths; REPLACE ignores missing paths by default.
6. Errors by default.
7. JSON array.
8. Ignores by default.
9. Renames the field while preserving its value.
10. Deletes data outside the specified paths.
11. In the order written; each operation sees the result of the previous one.
12. The entire function call fails with no partial edit returned.
13. NULL ON NULL sets JSON null; REMOVE ON NULL deletes the path.
14. So a SQL string is interpreted as a JSON object/array/boolean rather than a JSON string.
15. 0.
16. Deletes the corresponding member.
17. RFC 7396 defines null in a patch as remove.
18. Replaces the entire array at that member.
19. When targeted path operations, array modifications, or setting JSON null are needed.
20. Avoids the VARCHAR2(4000) output limit for large documents.
21. Oracle Database 19c Release 19.1.
22. Backported to Oracle Database 19c RU 19.10.
23. Initial 19c 19.3 lacks the function; you must verify RU/patches.
24. No; JSON_TRANSFORM was backported to 19c RU 19.10, while native JSON type was introduced in 21c.
25. Check the version/RU and run a minimal test SQL statement.
26. JSON_MERGEPATCH for object-centric patches or PL/SQL JSON_OBJECT_T/JSON_ARRAY_T.
27. No; row locks remain at the row level.
28. Apply path updates against the current column value, or use a version predicate.
29. To confirm whether any rows actually matched the condition and were updated.
30. No; it only validates JSON syntax; business validation is needed separately.

## Oracle Documentation and Reference Standards

- [Oracle Database 19c SQL Language Reference — JSON_MERGEPATCH](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_MERGEPATCH.html): syntax, return types, and error clauses of JSON_MERGEPATCH.
- [Oracle Database 19c JSON Developer's Guide — Updating a JSON Document with JSON Merge Patch](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/updating-a-json-document-with-json-merge-patch.html): examples and RFC 7396 limitations.
- [Oracle Database 19c JSON Developer's Guide — Oracle SQL Function JSON_TRANSFORM](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/oracle-sql-function-json_transform.html): JSON_TRANSFORM operations, handlers, and examples.
- [Oracle Database 19c SQL Language Reference — JSON_TRANSFORM](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/json_transform.html): SQL function syntax and RETURNING clause.
- [Oracle Database 19c JSON Developer's Guide — Overview of Inserting, Updating, and Loading JSON Data](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/overview-of-inserting-updating-loading-JSON-data.html): choosing among JSON_TRANSFORM, JSON_MERGEPATCH, and PL/SQL JSON object types.
- [Oracle Database 19c New Features Guide — JSON_MERGEPATCH](https://docs.oracle.com/en/database/oracle/oracle-database/19/newft/application-development.html): JSON_MERGEPATCH as a new feature in Oracle 19c.
- [Oracle Database 21c SQL Language Reference — JSON_TRANSFORM](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/JSON_TRANSFORM.html): function in the 21c SQL Reference.
- [IETF RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396): specification describing JSON Merge Patch semantics.

**Key Principle:** JSON_TRANSFORM expresses precise path operations and is suitable when modifying arrays, setting JSON null, or combining multiple changes. JSON_MERGEPATCH accepts an RFC 7396 patch document—convenient for objects, but null members mean deletion and arrays are replaced wholesale. Both functions only return the transformed document; to persist changes you must use UPDATE. JSON_MERGEPATCH has been available since Oracle 19c 19.1; JSON_TRANSFORM is from 21c and was backported to 19c RU 19.10. Confirm the RU on the target database, verify null/array semantics, and choose RETURNING to match the document size.
