# Adding Optional Fields

## 1. Objectives

When a gRPC API needs new capabilities, a generally safe way to extend it is to add fields to the Protobuf request and let old callers continue sending messages as before. The new server must handle both the case where a new caller sends the field and the case where an old caller does not know about it.

In proto3, the `optional` keyword solves another problem as well: distinguishing **a field not being sent** from **a field explicitly sent with a default value**. This is especially important for update APIs, where `false`, `0`, or an empty string can be a valid update request.

After this lesson, you will be able to:

- Add optional scalar fields to proto3 request messages.
- Distinguish between implicit presence and explicit presence.
- Use `hasX()`, getters, and `clearX()` in generated Java code.
- Choose appropriate defaults when old callers do not send a field.
- Design update semantics to distinguish skipping from clearing/setting default values.
- Properly handle message, repeated, map, enum, and oneof fields.
- Test requests from old and new clients during rollout.

## 2. Adding Fields While Preserving Old Callers

Suppose the Catalog API initially only searches by query:

```proto
syntax = "proto3";

package catalog.v1;
option java_package = "dev.example.catalog.v1";
option java_multiple_files = true;

service CatalogService {
  rpc Search(SearchRequest) returns (SearchResponse);
}

message SearchRequest {
  string query = 1;
}

message SearchResponse {
  repeated string product_ids = 1;
}
```

We want to add a result count limit. Add a field with an unused tag number:

```proto
message SearchRequest {
  string query = 1;
  optional int32 page_size = 2;
}
```

When the new server receives a request:

- Old clients only know `query = 1`, so they do not send `page_size`. The new server must have compatible default behavior.
- New clients can send `page_size = 20`. The new server uses that value.
- Old servers do not recognize tag `2`; they can ignore the new field when parsing. The request can still be processed with the old behavior, though the old server will not enforce the new page limit.

Adding a field is a relatively safe schema change at the wire layer when the new tag has never been used and the data type is chosen appropriately. That does not automatically guarantee the new feature works on old servers.

## 3. Implicit Presence vs. Explicit Presence

### Scalars Without optional

Regular proto3 scalars use *implicit presence*:

```proto
message UpdatePreferencesRequest {
  bool email_enabled = 1;
  int32 daily_limit = 2;
  string display_name = 3;
}
```

In generated Java:

```java
boolean enabled = request.getEmailEnabled();
int limit = request.getDailyLimit();
String name = request.getDisplayName();
```

If the field is not sent, the getter returns the type's default value:

| Type | Default Value |
|---|---|
| `bool` | `false` |
| Integer | `0` |
| Floating-point | `0.0` |
| `string` | `""` |
| `bytes` | `ByteString.EMPTY` |
| Enum | The enum value with number `0` |

The problem is that the server cannot distinguish an absent field from a field explicitly set by the caller to its exact default value. For example, `false` could mean “the user wants to disable email”, or merely “the old client did not send this field”.

### Scalars With optional

Declare explicit presence:

```proto
message UpdatePreferencesRequest {
  optional bool email_enabled = 1;
  optional int32 daily_limit = 2;
  optional string display_name = 3;
}
```

Generated Java provides presence-checking methods:

```java
if (request.hasEmailEnabled()) {
    boolean enabled = request.getEmailEnabled();
}

if (request.hasDailyLimit()) {
    int limit = request.getDailyLimit();
}
```

`hasEmailEnabled()` returns `false` when the field is absent and `true` when the field has been set, even if the value is `false`. Likewise, `hasDailyLimit()` still returns `true` if the caller explicitly sets `0`.

| What the Caller Sends | `hasEmailEnabled()` | `getEmailEnabled()` |
|---|---:|---:|
| Field not sent | `false` | `false` |
| Sends `false` | `true` | `false` |
| Sends `true` | `true` | `true` |

The getter still returns the default when the field is absent. Therefore, if logic needs to know whether the caller sent the field, check `hasX()` before reading the value.

## 4. How Is Presence Represented in Java?

With proto3 optional, the generated Java builder provides setters, getters, presence checks, and clear methods:

```java
UpdatePreferencesRequest request =
        UpdatePreferencesRequest.newBuilder()
                .setEmailEnabled(false)
                .setDailyLimit(0)
                .build();

assertTrue(request.hasEmailEnabled());
assertFalse(request.getEmailEnabled());

assertTrue(request.hasDailyLimit());
assertEquals(0, request.getDailyLimit());
```

If you omit the field from the builder or call `clearX()`, presence reverts to absent:

```java
UpdatePreferencesRequest request =
        UpdatePreferencesRequest.newBuilder()
                .setEmailEnabled(true)
                .clearEmailEnabled()
                .build();

assertFalse(request.hasEmailEnabled());
```

On the wire format, an explicitly set optional field can be serialized even when it carries its default value. An absent field is not sent. This difference allows the server-side parser to recover presence.

Java method names are generated according to Protobuf rules; inspect the generated source when the schema has special names or naming conflicts.

## 5. Choosing Defaults When a Field Is Absent

`optional` tells you whether a field was set; it does not define the business behavior when the field is absent. The server must decide the default explicitly.

For `SearchRequest.page_size`, you can use:

```java
private static final int DEFAULT_PAGE_SIZE = 25;
private static final int MAX_PAGE_SIZE = 100;

int pageSize = request.hasPageSize()
        ? request.getPageSize()
        : DEFAULT_PAGE_SIZE;

if (pageSize < 1 || pageSize > MAX_PAGE_SIZE) {
    throw Status.INVALID_ARGUMENT
            .withDescription("page_size must be between 1 and 100")
            .asRuntimeException();
}
```

When an old client does not send `page_size`, the server uses `25`. When a new client sends `0`, the server sees presence and rejects the invalid value. Without `optional`, both cases could have the getter return `0`, making it impossible for the server to distinguish them.

New defaults must preserve old semantics. For instance, if Search previously returned at most 25 results, adding `page_size` should not suddenly make old requests return all data. Choose a default that matches the previous limit and publish a maximum limit.

### Distinguishing Protobuf Defaults from Business Defaults

- **Protobuf default:** the value returned by a getter when an implicit/optional scalar is absent, such as `0`, `false`, `""`.
- **Business default:** the behavior the server chooses when the caller does not provide the field, such as a page size of 25 or a default locale.

Do not rely on Protobuf defaults to implicitly define business defaults. Writing the absent branch explicitly helps readers see what behavior the server maintains for old callers.

## 6. optional Is Especially Useful for Update Requests

For creation APIs, absent can use a default. For update APIs, absent usually means **do not change the field**. An explicitly sent default value can be a valid update instruction.

Example:

```proto
message UpdateAccountRequest {
  string account_id = 1;
  optional bool notifications_enabled = 2;
  optional string display_name = 3;
  optional int32 daily_limit = 4;
}
```

The server only updates fields the caller actually sent:

```java
Account account = repository.findById(request.getAccountId())
        .orElseThrow(() -> new AccountNotFoundException());

if (request.hasNotificationsEnabled()) {
    account.setNotificationsEnabled(
            request.getNotificationsEnabled());
}

if (request.hasDisplayName()) {
    account.setDisplayName(request.getDisplayName());
}

if (request.hasDailyLimit()) {
    int value = request.getDailyLimit();
    if (value < 0 || value > MAX_DAILY_LIMIT) {
        throw Status.INVALID_ARGUMENT
                .withDescription("daily_limit is out of range")
                .asRuntimeException();
    }
    account.setDailyLimit(value);
}

repository.save(account);
```

Meaning:

| Request | Update Result |
|---|---|
| `notifications_enabled` absent | Keep current state |
| `notifications_enabled = false` | Turn off notifications |
| `display_name` absent | Keep current name |
| `display_name = ""` | Set empty name if business rules allow; otherwise return a validation error |
| `daily_limit = 0` | Set limit to 0 if business rules allow |

This is why you should not use scalar implicit presence for update APIs when you need to distinguish “not sent” from “reset to default value”.

## 7. How Do Other Field Types Handle Presence?

Not every field uses the `optional` keyword.

| Field Type | Presence in proto3 | How to Handle |
|---|---|---|
| Scalar without `optional` | Implicit; cannot distinguish absent from default | Use when the default is sufficient to express semantics |
| Scalar with `optional` | Explicit | Use `hasX()` to distinguish absent/default |
| Message field | Inherent presence | Use `hasX()`; no need to add `optional` |
| `oneof` member | Presence via case/member check | Use `getChoiceCase()` or corresponding API |
| `repeated` | No presence | Empty and absent are both an empty collection |
| `map` | No presence | Empty and absent are both an empty map |

### Message Fields

Message fields in proto3 already have explicit presence:

```proto
message SearchRequest {
  SearchOptions options = 1;
}

message SearchOptions {
  bool include_archived = 1;
}
```

Java can check:

```java
if (request.hasOptions()) {
    boolean includeArchived =
            request.getOptions().getIncludeArchived();
}
```

`hasOptions()` distinguishes an absent message from a present `SearchOptions` message containing default values.

### Repeated and Map

Repeated/map fields do not have `hasX()`:

```proto
message UpdateLabelsRequest {
  repeated string labels = 1;
  map<string, string> attributes = 2;
}
```

Getters return an empty collection when there are no elements. If an update API needs to distinguish “not sent to keep unchanged” from “sent an empty collection to clear all”, use `FieldMask` or wrap the collection in a message with presence:

```proto
message StringList {
  repeated string values = 1;
}

message UpdateLabelsRequest {
  StringList labels = 1;
}
```

Because `labels` is a message field, `hasLabels()` distinguishes absent from a present message with empty `values`. Semantics must be clearly defined: absent means keep unchanged, present-empty means clear all.

### Oneof

Members of a `oneof` have presence and are mutually exclusive:

```proto
message SearchFilter {
  oneof filter {
    string category = 1;
    int64 seller_id = 2;
  }
}
```

Generated Java code provides a case enum, such as `getFilterCase()`. If no member is set, the case is `FILTER_NOT_SET`. Both category and seller ID cannot be set simultaneously in the same oneof.

## 8. Optional Enums and the UNSPECIFIED Value

Enums typically declare value `0` as the default value:

```proto
enum SortOrder {
  SORT_ORDER_UNSPECIFIED = 0;
  SORT_ORDER_RELEVANCE = 1;
  SORT_ORDER_NEWEST = 2;
}

message SearchRequest {
  optional SortOrder sort_order = 4;
}
```

With `optional`, the server distinguishes:

- Absent: caller did not provide a sort option; server applies the business default.
- Present with `SORT_ORDER_UNSPECIFIED`: caller explicitly sent enum value `0`; server can apply a specific rule or return a validation error.
- Present with `SORT_ORDER_NEWEST`: caller chose newest sorting.

If you do not need to distinguish absent from `UNSPECIFIED`, you can use a non-optional enum scalar and treat `UNSPECIFIED` as a request to use the default. What matters is that the contract states this clearly.

## 9. Adding Optional Fields During Rollout

When clients and servers are deployed independently, roll out in order:

1. **Add the field to the schema:** choose a new never-used tag; keep existing fields unchanged.
2. **Deploy the server supporting the field:** the new server reads the field when present and applies a compatible default when absent.
3. **Test old clients:** confirm requests missing the field are still accepted and results remain unchanged.
4. **Confirm all server instances are upgraded:** avoid sending new clients to servers that do not yet support the new semantics.
5. **Deploy new clients:** only send the field when the target server supports it.
6. **Observe:** measure the percentage of requests with the field, invalid values, and callers still on old versions.

A new client sending a field to an old server may parse successfully because the old server ignores unknown fields. However, features relying on the new field will not be executed. Wire compatibility does not replace capability negotiation or ordered rollout.

When a field is no longer needed, remove it following the migration process and reserve both its tag number and name. Never reuse a published field number.

## 10. Testing Presence and Compatibility

### Unit Testing Generated Messages

```java
SearchRequest absent = SearchRequest.newBuilder()
        .setQuery("keyboard")
        .build();

assertFalse(absent.hasPageSize());
assertEquals(0, absent.getPageSize());

SearchRequest explicitZero = SearchRequest.newBuilder()
        .setQuery("keyboard")
        .setPageSize(0)
        .build();

assertTrue(explicitZero.hasPageSize());
assertEquals(0, explicitZero.getPageSize());
```

This test proves `hasPageSize()` distinguishes absent from explicit zero. The getter returns `0` in both cases, so checking the getter alone is insufficient.

### Testing Serialize/Parse

```java
SearchRequest original = SearchRequest.newBuilder()
        .setQuery("keyboard")
        .setPageSize(0)
        .build();

SearchRequest parsed = SearchRequest.parseFrom(
        original.toByteArray());

assertTrue(parsed.hasPageSize());
assertEquals(0, parsed.getPageSize());
```

Also test an absent request to confirm `hasPageSize()` remains false after a round trip.

### Compatibility Matrix

| Client | Server | What to Verify |
|---|---|---|
| Old | New | Absent field uses old default; not rejected by required validation |
| New | New | Optional value is applied properly |
| New | Old | Old server ignores new field; client has fallback if feature is unavailable |
| Old | Old | Baseline behavior is unchanged |

Business tests should cover absent, explicit default, valid values, out-of-range values, and conflicts with old fields if migrating.

## 11. Common Pitfalls

| Symptom | Cause | How to Fix |
|---|---|---|
| Cannot tell whether caller sent `false` | Scalar implicit presence | Switch to `optional bool` if explicit presence is needed |
| Old requests rejected after deploy | New server requires newly added field | Keep field optional and handle absent |
| Server applies wrong default | Confusing Protobuf default with business default | Write explicit absent branch and business default |
| Cannot distinguish absent vs. empty collection | `repeated`/`map` has no presence | Use FieldMask or wrapper message |
| Update cannot reset field to `false`/`0` | Logic only updates when getter differs from default | Use `hasX()` |
| New client assumes old server applied field | Old server ignores unknown field | Roll out servers first or use capability routing |
| `hasX()` does not exist in Java | Field lacks explicit presence or code generated from old schema | Check `optional`, plugin/protoc, and generated source |
| New field changes results for old requests | Incompatible business default | Preserve old behavior when field is absent |

## 12. Hands-On Exercise

**Scenario:** The Profile API has a request to update `display_name` and `notifications_enabled`. Old clients only send `user_id`; new clients need to change the name or turn off notifications. If the server uses proto3 scalar implicit presence, it could overwrite existing data with `""` or `false` when old clients omit those fields.

Perform the following:

1. Add `optional string display_name` and `optional bool notifications_enabled` with new tags, keeping `user_id` unchanged.
2. Regenerate Java code and verify `hasDisplayName()` and `hasNotificationsEnabled()` exist.
3. Implement the server to update only fields with presence; add validation for empty strings per business rules.
4. Test an old client sending only `user_id`; existing data must remain preserved.
5. Test a new client sending `notifications_enabled = false`; the server must save false instead of ignoring it.
6. Test absent fields and explicit defaults across serialize/parse.
7. For a repeated field that needs to support clearing all items, design a wrapper message or FieldMask and define semantics.
8. Run the old/new client-server matrix before enabling new clients in production.

**Completion criteria:** the server distinguishes absent from explicit defaults, preserves data when old callers omit fields, applies `false`/`0`/empty string when callers explicitly send them, and does not break callers during rollout.

## 13. Key Takeaways

In proto3, adding new fields with unused tags and handling absent cases with compatible defaults allows safe request extension. Use `optional` on scalars when explicit presence is needed: `hasX()` distinguishes an unsent field from a field set to `false`, `0`, or `""`. Message fields inherently have presence; repeated/map fields do not, so FieldMask or a wrapper message is needed if you must distinguish absent from empty. In the Java server, update fields based on `hasX()`, test both wire and semantics, and deploy supporting servers before clients depend on the new fields.
