# Distinguishing Omitted Fields, Null Values, and Array Replacement When Updating

When updating a resource through Spring Data REST, three cases are easily confused: not sending a property, sending a property with JSON value `null`, and sending a new array. They have different meanings. If misunderstood, a PATCH request intended to edit just one field can accidentally delete data or replace an entire existing list.

You need to determine the **PATCH type and Content-Type** before inferring the outcome. The sections below focus on two patch formats with explicit rules: JSON Merge Patch and JSON Patch.

## 1. Choosing the right update style

| Submission style | Primary meaning | When to use |
|---|---|---|
| PUT | Send the full representation to replace the resource | When the client has the entire state to save |
| PATCH with application/merge-patch+json | Describe changes structured as JSON; unmentioned properties are preserved | When wanting to update a subset of properties |
| PATCH with application/json-patch+json | Send a list of path-specific operations such as add, remove, replace | When needing precise control over a property or array element |

Do not assume every PATCH request follows the same rules. Send the Content-Type corresponding to the patch format supported by the Spring Data REST endpoint and used by the client.

## 2. Omitted properties: keep the current value

With JSON Merge Patch, a property that does not appear in the patch document is not modified.

Example current resource:

~~~json
{
  "id": 42,
  "name": "Laptop",
  "description": "Office equipment",
  "price": 1000,
  "tags": ["work", "portable"]
}
~~~

Request sending only the new name:

~~~http
PATCH /products/42
Content-Type: application/merge-patch+json
Accept: application/hal+json
~~~

~~~json
{
  "name": "Laptop Pro"
}
~~~

Expected result:

- name is updated to Laptop Pro.
- description remains Office equipment.
- price remains 1000.
- tags still contains work and portable.

In other words, in Merge Patch, **omitting a property means not requesting any change to that property**. This is appropriate for keeping fields that a form or client did not edit.

With JSON Patch, properties without a corresponding operation in the operation array are also preserved.

## 3. Sending null: request to remove or clear a property

In JSON Merge Patch, a null value means removing the property from the target representation. When the patch is mapped onto an entity, this operation typically corresponds to clearing the property, such as assigning null to a nullable field. The final outcome still depends on data type, mapping, validation, and the application's business rules.

Example:

~~~json
{
  "description": null
}
~~~

After the patch, description is requested to be removed/cleared; unmentioned properties such as name, price, and tags are preserved.

Check the following conditions before allowing a value to be cleared:

- Does the field allow null? Constraints such as @NotNull or nullable = false can cause the operation to be rejected.
- Is the field a Java primitive type such as int or long? Primitives cannot represent null; if clearing the value is needed, consider wrapper types such as Integer or Long.
- Is the field a relationship to another entity? Setting a relationship to null may be prevented by validation or domain rules.
- Is it necessary to distinguish removing a property from JSON versus storing null in the database? Those two states can differ depending on serialization and the data model.

### null in JSON Patch differs from remove

JSON Patch uses explicit operations so it can distinguish the two intents:

~~~json
[
  { "op": "remove", "path": "/description" },
  { "op": "replace", "path": "/name", "value": null }
]
~~~

- remove requests dropping the property at that path.
- replace with value null requests replacing the value at that path with JSON null. The path must exist for replace to be valid.

Therefore, when you need to distinguish removing a property from assigning a null value, choose the corresponding JSON Patch operation instead of relying on an ambiguous payload.

## 4. Arrays in JSON Merge Patch are replaced completely

Arrays are the easiest case to cause data loss. Under JSON Merge Patch rules, an array is treated as an atomic value. The new array replaces the entire old array; elements not resent disappear.

Suppose the resource currently has:

~~~json
{
  "tags": ["work", "portable", "office"]
}
~~~

The client sends:

~~~json
{
  "tags": ["work", "premium"]
}
~~~

The result is:

~~~json
{
  "tags": ["work", "premium"]
}
~~~

The elements portable and office were dropped because the client sent a replacement array.

Distinguish the following payloads:

| Payload | Result with Merge Patch |
|---|---|
| Without the tags property | Keeps the current array |
| "tags": [] | Replaces with an empty array |
| "tags": ["work", "premium"] | Replaces completely with the new array |
| "tags": null | Removes the tags property from the target representation |

There is no automatic merging of elements by position, ID, or value. If the client only knows part of the list, sending a partial array can lose the remaining elements.

### Updating a single array element with JSON Patch

If you only want to edit one element or append an element to the end of the array, JSON Patch lets you specify the exact path:

~~~http
PATCH /products/42
Content-Type: application/json-patch+json
~~~

~~~json
[
  { "op": "replace", "path": "/tags/1", "value": "premium" },
  { "op": "add", "path": "/tags/-", "value": "featured" }
]
~~~

Starting from the array ["work", "portable", "office"], the result will be ["work", "premium", "office", "featured"].

Common operations:

- replace /tags/1: replaces the element at index 1.
- add /tags/-: appends an element to the end of the array.
- remove /tags/0: removes the element at index 0; subsequent indices shift.

Array indices start at 0. If multiple operations modify the array together, operation order affects the indices of subsequent elements. Do not use indices as stable identifiers when data can be modified concurrently.

## 5. Combined example

Initial resource:

~~~json
{
  "id": 42,
  "name": "Laptop",
  "description": "Office equipment",
  "price": 1000,
  "tags": ["work", "portable"],
  "stock": 5
}
~~~

Merge Patch request:

~~~json
{
  "name": "Laptop Pro",
  "description": null,
  "tags": ["work", "premium"]
}
~~~

Read the result property by property:

| Property | Payload | Result |
|---|---|---|
| name | New value provided | Changed to Laptop Pro |
| description | null provided | Requested removal/clearing; depends on nullability and mapping |
| price | Omitted | Kept at 1000 |
| tags | New array provided | Replaced completely with ["work", "premium"] |
| stock | Omitted | Kept at 5 |

This example shows that a single request can simultaneously preserve some fields, clear a field, and replace an entire array.

## 6. Notes when writing a custom Controller or using DTOs

Patch format rules take effect only if the processing layer preserves the payload's meaning. When receiving a request with a plain DTO, the two cases of omitting a property and sending the property with null can both map to Java null. If you then copy the entire DTO onto the entity, the code may accidentally clear data.

When you need to distinguish them clearly, you can read the payload as a JsonNode and check for property presence:

~~~java
if (!patch.has("description")) {
    // Property absent: keep current value.
} else if (patch.get("description").isNull()) {
    // Property present and value is JSON null: handle clearing request.
    product.setDescription(null);
} else {
    // Concrete value present: update with the sent value.
    product.setDescription(patch.get("description").asText());
}
~~~

JsonNode.has("description") returns true when the property is present, even when its value is JSON null. Do not use hasNonNull to check presence if you need to distinguish the two states, because that method returns false when the value is null.

With a dedicated DTO, you can use a data type supporting undefined/present/null states, or build a mechanism to track which properties actually appeared in the request. Simply using Optional<T> does not automatically solve the difference between an omitted property and a property sent as null.

## 7. Case where an array is a relationship between entities

In Spring Data REST, a collection in the model can be a list of simple values or a relationship to other resources. Relationships are typically represented as association links in HAL and have dedicated association endpoints.

Therefore, do not assume every array shown in JSON can be modified like an ordinary List property. Inspect the relationship links returned by Spring Data REST and use the exact association endpoint/method exposed by the API to add, replace, or unlink relationships. For relationships to multiple resources, sending a new list may mean replacing the entire set of links if the endpoint supports that operation.

## 8. Checklist before sending an update request

1. Confirm whether the request is PUT, JSON Merge Patch, or JSON Patch.
2. Send the right Content-Type: application/merge-patch+json or application/json-patch+json.
3. For each property, decide explicitly: preserve, assign value, or remove/clear.
4. If sending an array with Merge Patch, confirm the client intends to replace the entire list.
5. Check validation, nullability, and business rules before allowing null assignment.
6. With a DTO handling PATCH manually, preserve the distinction between an absent property and a property with value null.
7. For entity relationships, operate through the appropriate association resource.
8. After updating, GET the resource again to verify the persisted state, especially omitted fields and array elements.

You can test at least four independent scenarios: omitting a field, sending null, sending an empty array, and sending a new array with fewer elements than the old array. Checking the GET result after each request helps catch unintended updates early.
