# Designing PUT/PATCH Updates and Handling Repeated Requests in Spring MVC

## 1. Objective and Opening Scenario

A client opens a document at `GET /api/documents/1`, edits the title, and clicks Save. The server processes the change successfully, but the connection drops before the response returns. The client **does not know** whether the update was applied. If it resends the request, will the content stay the same, be applied twice, or overwrite someone else's update?

To answer this, you must design **update semantics**, **repeated-request handling rules**, and **protection when multiple clients edit concurrently**. This lesson helps you:

- Distinguish `PUT` from `PATCH` per HTTP semantics, especially **full replacement** vs. **partial update**.
- Understand **idempotency**: sending the same request multiple times has the same intended effect on the resource as sending it once; distinguish final effect from responses, logs, and request IDs.
- Recognize that `PATCH` may or may not be idempotent depending on the operation and server implementation; understand JSON Merge Patch and JSON Patch.
- Use **ETag + If-Match** to prevent **lost updates**; distinguish `412 Precondition Failed`, `428 Precondition Required`, and `409 Conflict`.
- Choose 200/204/201 responses, distinguish absent vs. null, determine safe retries, and avoid duplicate side effects.
- Build a Spring Boot 3.x / Java 17+ demo with `GET`, `PUT`, `PATCH` endpoints, conditional update checks, and `MockMvc` tests.

**Scope:** REST API design and basic implementation in **Spring MVC (Servlet stack)**. Examples follow the spirit of RFC 9110 (HTTP Semantics), RFC 5789 (PATCH), RFC 7396 (JSON Merge Patch), and RFC 6902 (JSON Patch). Idempotency rules are a property of the **defined HTTP request effect**, not a claim that the server physically processes the request only once.

## 2. PUT and PATCH: Differing Update Contracts

Example current document:

```json
{
  "title": "Hướng dẫn Spring",
  "description": "Bản nháp"
}
```

### 2.1. PUT: Sending a New Representation for the Target Resource

A client wanting to replace the entire representation can send:

```http
PUT /api/documents/1 HTTP/1.1
Content-Type: application/json

{"title":"Hướng dẫn Spring MVC","description":"Bản hoàn chỉnh"}
```

HTTP semantics of `PUT`: requests the server to **create or replace the state of the target resource with the enclosed representation**. If the resource already exists and updates successfully, the response is typically **200 OK** (with body) or **204 No Content** (no body). If the resource **did not exist and PUT creates it successfully**, per HTTP semantics the server **must return 201 Created**.

**Do not apply "update only present fields" to PUT** if the API is specified as full replacement. For example:

```http
PUT /api/documents/1 HTTP/1.1
Content-Type: application/json

{"title":"Hướng dẫn Spring MVC"}
```

For a two-field resource like above, omitting `description` **does not imply keeping `"Bản nháp"`**. The PUT contract must explicitly define this: treat the absent field as default/null, drop it from the representation, or reject requests missing required fields. Clients must send the complete representation per schema. Some real APIs label an endpoint PUT while implementing partial updates; that is a custom contract that easily causes confusion and should be fixed or clearly documented.

**Subtle point:** HTTP PUT is about the **resource representation**; it does not force the server to store the request body byte-for-byte in a single DB row. Still, the server must preserve resource semantics. Server-owned properties such as `id` and `createdAt` are usually not editable by clients; the contract must clarify whether they belong to the PUT-able representation.

### 2.2. PATCH: Sending a Document Describing Changes

To change only the title and keep `description`, use `PATCH` with an agreed patch document format:

```http
PATCH /api/documents/1 HTTP/1.1
Content-Type: application/merge-patch+json

{"title":"Hướng dẫn Spring MVC"}
```

With **JSON Merge Patch** (RFC 7396), omitted fields stay unchanged; present fields are replaced/updated per Merge Patch rules. Old data:

```json
{"title":"Hướng dẫn Spring","description":"Bản nháp"}
```

Resulting data:

```json
{"title":"Hướng dẫn Spring MVC","description":"Bản nháp"}
```

Not every `PATCH` uses the same syntax. The server must pick and advertise a **patch media type**, such as `application/merge-patch+json` or `application/json-patch+json`; an endpoint defining `PATCH` with `application/json` must define its own semantics. Never assume any JSON object sent with PATCH automatically means "update only the sent fields."

### 2.3. Comparison Table

| Question | PUT | PATCH |
| --- | --- | --- |
| What does the request body represent? | New representation for the entire resource | Set of changes / patch document |
| Omitted fields | Follows replacement representation schema; does not assume keeping old values | Follows patch format; Merge Patch keeps them unchanged |
| Can it create a resource? | Yes, if the server supports PUT at that URI | Possible in some PATCH contracts/formats, not a default assumption |
| Is it idempotent per HTTP definition? | **Yes** | **Not by default**, can be designed to be idempotent |
| Needs concurrency control? | Yes | Yes; some patches are especially sensitive to concurrent changes |
| Common success statuses | 200/204; 201 if newly created | 200/204 (or others if contract requires) |
| Suitable body | Resource representation | `application/merge-patch+json` or `application/json-patch+json` |
| Common pitfalls | Missing fields accidentally clearing values, overwriting newer changes | Failing to distinguish absent/null, patching stale state, repeating add/move ops |

## 3. What Is Idempotency?

In HTTP, a method is **idempotent** if the intended effect on server state of **multiple identical requests** is the same as the effect of **a single request**. `GET`, `HEAD`, `OPTIONS`, and `TRACE` are safe (and idempotent); `PUT` and `DELETE` are idempotent yet **not safe** because they can alter state. `POST` and `PATCH` are not defined as idempotent by default.

An easy way to think about it:

```text
SET title = "Hoàn chỉnh"         → can be idempotent
INCREMENT views BY 1            → not idempotent
APPEND "A" to list              → not idempotent (without deduplication)
DELETE resource ID=1            → idempotent in target effect
POST create a new transaction   → may create extra records on retry
```

Here `PUT` behaves like **setting a desired state**. Sending the same body repeatedly to the same resource—without competing operations or version constraints changing the outcome—leaves the resource in the same state after each application.

### 3.1. Idempotent Does Not Mean Identical Responses

Example:

1. First `DELETE /api/documents/1`: 204; resource is deleted.
2. Second `DELETE /api/documents/1`: 404 because the resource no longer exists.
3. **Final effect:** the resource still does not exist; `DELETE` remains idempotent.

Similarly, a conditional `PUT` with `If-Match: "v1"` may succeed the first time, then return 412 on retry because the version advanced to `"v2"`. **This does not make PUT non-idempotent**: the repeated request does not overwrite or duplicate the change. Responses do not have to keep the exact same status/body/headers.

The server may write new access logs, new metrics, or perform administrative side effects on each request without altering the method's idempotency definition. However, **business side effects** such as sending two invoices, charging twice, or emitting two shipping events **require explicit deduplication**. Do not rely on the PUT label alone to infer exactly-once execution across an entire workflow.

### 3.2. Repeated-Request Reasoning Table

| Request | First call | Exact repeated request | Idempotent in effect? |
| --- | --- | --- | --- |
| `PUT /docs/1` fixed body | Sets document to X | Still X | Yes |
| `PATCH` set `title="X"` | Sets title to X | Still X | Can be |
| `PATCH` `increment count by 1` | count 5 → 6 | 6 → 7 | No |
| `PATCH` JSON Patch `replace /title "X"` | title becomes X | Still X, if path exists | Can be |
| `PATCH` JSON Patch `add /items/- "A"` | Appends element | Appends again | No |
| `DELETE /docs/1` | Deletes document | No additional document deleted | Yes |
| `POST /payments` fixed body | Creates transaction | May create an extra transaction | Not by default |

**Caveat:** preconditions, side effects, related resources, and the API contract determine true idempotency. Do not say "PATCH is always non-idempotent": RFC 5789 allows clients to design idempotent PATCH operations, and conditional updates should be used to reduce conflicts.

### 3.3. Why Does Idempotency Matter for Retries?

Failures can occur after a request leaves the client:

- Connection drops before the server receives the body.
- Server commits the transaction, but the response is lost in transit.
- Gateway times out and the client or proxy retries.
- Mobile app resends due to uncertain network state.

Clients struggle to distinguish **"never executed"** from **"executed but response lost"**. Thus, PUT/PATCH design needs clear outcome verification rules; any non-idempotent operation needs duplicate detection and post-state checking before re-running.

**Retries are safe only when they satisfy the contract.** For cumulative PATCH operations, the server must enforce conditions/deduplication, or the client must not blindly auto-resend.

## 4. Two Common Standards for JSON PATCH Documents

### 4.1. JSON Merge Patch (RFC 7396)

Media type: `application/merge-patch+json`.

Given resource:

```json
{
  "title": "Draft",
  "description": "Need review",
  "labels": ["java", "rest"],
  "settings": {"visible": false, "theme": "light"}
}
```

Send:

```http
PATCH /api/documents/1 HTTP/1.1
Content-Type: application/merge-patch+json

{
  "title": "Final",
  "description": null,
  "settings": {"visible": true}
}
```

Result:

```json
{
  "title": "Final",
  "labels": ["java", "rest"],
  "settings": {"visible": true, "theme": "light"}
}
```

Rules:

- **Absent:** preserves the existing value.
- **Present with non-null value:** adds/replaces; for nested objects, Merge Patch recurses.
- **Present with null value:** **deletes the field** from the target object, rather than "setting the field to JSON null" in the usual data sense.
- **Arrays:** normally replaces the whole array; Merge Patch does not support replacing a single element by index.
- **Non-object patch:** replaces the entire target with the patch value. An API may reject this per resource schema, but must state so clearly.
- **Re-applying the same pure Merge Patch** to the resulting state typically leaves data unchanged; however, version bumps/side effects in the implementation must be designed properly, and conflicts with interleaved updates can still occur.

Merge Patch fits object-structured resources when null does not need to be stored distinctly from **removing the key**. If the domain allows storing valid JSON null in a field, Merge Patch becomes ambiguous; choose JSON Patch or a dedicated contract.

### 4.2. JSON Patch (RFC 6902)

Media type: `application/json-patch+json`. Body is **an ordered array of operations**:

```http
PATCH /api/documents/1 HTTP/1.1
Content-Type: application/json-patch+json

[
  {"op":"test","path":"/title","value":"Draft"},
  {"op":"replace","path":"/title","value":"Final"},
  {"op":"remove","path":"/description"}
]
```

Operations in RFC 6902:

| Operation | Typical effect | When repeated |
| --- | --- | --- |
| `add` | Adds/sets an object key or inserts an array element | Adding an object key is usually safe; array insertion can duplicate |
| `remove` | Removes an existing target location | Repeat may error because the path no longer exists |
| `replace` | Replaces the value at an existing path | Usually keeps the same value on repeat |
| `move` | Moves a value from `from` to `path` | Depends on structure after the first call |
| `copy` | Copies from `from` to `path` | Depends on target structure |
| `test` | Checks value at path; failure aborts the entire patch | Useful as a precondition inside a patch |

Paths use **JSON Pointer** (RFC 6901); `~` and `/` in property names must be escaped as `~0` and `~1`. Array indices and `-` (append position) have specific semantics. For example:

```json
[
  {"op":"add","path":"/labels/-","value":"spring"}
]
```

Without deduplication, resending this request appends `"spring"` a second time. JSON Patch is **not inherently idempotent** simply because the HTTP method is PATCH.

RFC 5789 requires **applying patches atomically**: if an operation fails mid-list, the server must never expose a partially updated representation or persist partial changes. Production implementations need transactions/rollbacks or equivalent atomicity across all affected updates.

### 4.3. PATCH with a Custom JSON Body

Many APIs choose:

```http
PATCH /api/orders/42 HTTP/1.1
Content-Type: application/json

{"status":"SHIPPED"}
```

This can be valid if the API **explicitly defines** the body as "editable fields, absent fields unchanged, null means X". However, do not label it RFC 7396 if it does not fully obey Merge Patch (e.g., if null is stored as null or arrays merge by index). Consider vendor media types and OpenAPI/contract documentation.

When changing business relationships such as "capture payment", "confirm", or "add inventory units", a **POST command endpoint** with an idempotency key sometimes expresses behavior more clearly than an ambiguous PATCH. Choose the method by resource semantics, not controller annotation convenience.

## 5. The Hard Problem: Concurrent Updates and Lost Updates

Suppose the initial state is:

```json
{"title":"Draft","description":"Original"}
```

Two clients both GET at 10:00:

1. Client A changes `title` to `"Published"` and PUTs the full object.
2. Client B still holds the old copy, changes `description` to `"Revised"`, and PUTs the full object.
3. If the server accepts B after A **without checking version**, B's body may still contain `title="Draft"`, accidentally overwriting A's `"Published"`.

This is a **lost update**, which can happen even when PUT is completely idempotent. Idempotency solves the risk of **repeating the same request**, not **two different valid requests racing**.

PATCH lowers the chance of overwriting unrelated fields when it sends only changed fields, yet logical conflicts remain; two clients editing `description`, one acting on an old version, or a JSON Patch targeting shifted array indices will still break. Therefore, both PUT and PATCH need concurrency control.

### 5.1. ETag + If-Match (Optimistic Concurrency)

A standard HTTP approach is returning a **strong ETag** on resource GET:

```http
GET /api/documents/1 HTTP/1.1

HTTP/1.1 200 OK
ETag: "v7"
Content-Type: application/json

{"title":"Draft","description":"Original"}
```

The client sends the version it read:

```http
PUT /api/documents/1 HTTP/1.1
If-Match: "v7"
Content-Type: application/json

{"title":"Published","description":"Original"}
```

The server performs an **atomic check-and-update**:

```text
Does resource have current ETag "v7"?
  ├── Yes → validate input, write update, advance to new version
  └── No  → DO NOT overwrite, return 412 Precondition Failed
```

If A already updated to `"v8"`, B's stale PUT with `If-Match: "v7"` is rejected with **412** instead of silently overwriting A. B must GET the latest state and decide how to merge/re-edit.

**Crucial points:**

- `If-Match` uses **strong comparison**. A weak ETag like `W/"v7"` does not satisfy a strong match against `"v7"`.
- `If-Match: *` requires the resource to have a current representation; it **does not** check a specific version and does not prevent lost updates from stale reads.
- `If-Match` can contain a list of valid entity tags. The runnable example in section 8 **intentionally supports only a single exact strong tag** to keep the code focused; production must follow the full HTTP precondition syntax/rules.
- If the client omits the condition and API policy requires optimistic concurrency, return **428 Precondition Required**. If sent with a mismatched tag, return **412 Precondition Failed**.
- Do not use `If-None-Match` instead of `If-Match` to guard updates to an existing resource; `If-None-Match: *` is primarily useful for **creating only if absent**.
- An entity tag does not have to be a visible version number; it can be a representation hash or opaque token, as long as strong-validator rules hold. Never compare ETags numerically with greater-than/less-than.

### 5.2. How Does ETag Differ from `@Version` in JPA?

Jakarta Persistence `@Version` is optimistic locking at the **storage layer**; ETag/If-Match is the **HTTP** contract. They work together:

```text
HTTP GET  → read row (id=1, version=7) → build ETag "v7"
HTTP PUT  → receive If-Match "v7"
          → transaction checks DB version=7
          → UPDATE ... WHERE id=1 AND version=7
          → update version=8
          → commit
HTTP GET  → ETag "v8"
```

Do not just do:

```java
if (incomingTag.equals(currentTag)) {
    // after reading, another transaction can interleave here
    repository.save(entity);
}
```

Check-then-write without a transaction/locking/CAS is a **race condition**. With multiple application instances, `synchronized` inside one JVM is not enough either because each instance has its own lock. Use DB transactions, optimistic locking/versioning, compare-and-swap, or atomic storage operations.

### 5.3. Retrying After a Request Succeeded but the Response Was Lost

Example:

```text
Before state: ETag "v7"
Client sends: PUT body X + If-Match "v7"
Server: commit X, bump tag to "v8"; response is lost
Client retries IDENTICAL request: PUT body X + If-Match "v7"
Server: sees tag "v8" → 412, DOES NOT write a second time
Client: GET latest, compare content, and decide outcome
```

This is a safe response. Never treat HTTP 412 as "guaranteed the entire operation never succeeded"; the earlier request **may already have succeeded**. Clients should GET/compare state or use idempotency result tracking when they must know the exact outcome of a business action.

HTTP allows servers in certain cases to return 2xx if they determine the state already matches the previous request, though **they must never arbitrarily overwrite newer state** or return a semantically wrong new ETag. For clarity, the demo strictly returns 412 when the tag no longer matches.

## 6. Response/Status Design Rules for Updates

| HTTP status | When to use | Response guidance |
| --- | --- | --- |
| **200 OK** | PUT/PATCH succeeded and returns representation or metadata | JSON body reflecting new state |
| **204 No Content** | PUT/PATCH succeeded, client needs no body | **No body**; may include relevant metadata headers |
| **201 Created** | PUT created a new resource at the URI | `Location` if helpful; return representation if needed |
| **400 Bad Request** | Malformed body, missing required field, invalid input contract | Safe error code/details |
| **404 Not Found** | Target resource absent, API forbids PUT-create | Report resource does not exist |
| **409 Conflict** | Business state conflict or patch conflict not expressed via HTTP preconditions | Error code and fetch/reconcile guidance |
| **412 Precondition Failed** | `If-Match`/HTTP precondition sent and failed | Prompt client to re-read state |
| **415 Unsupported Media Type** | Unsupported patch content type | May advertise patch formats to client |
| **422 Unprocessable Content** | Content type/syntax understood, but instructions cannot be processed semantically, if contract uses this code | Appropriate semantic error description |
| **428 Precondition Required** | API requires update condition to prevent lost updates | Guide client to send If-Match |

Do not map every PATCH error to 409. When `If-Match` is evaluated and mismatches, **412** expresses it more clearly. When the API actively requires the header and it is missing, **428** is the right choice. For normal validation, Spring MVC typically returns **400**, whereas using **422** is a contract choice rather than Spring's automatic default.

**ETag in PUT responses:** HTTP places strict rules on sending a validator after a successful PUT: do not return `ETag`/`Last-Modified` if the server transforms the request representation on save such that the validator would not match the stored representation. The demo below **omits ETag on PUT responses**; clients call GET for the new validator. On GET, ETag is returned for the current representation. For PATCH, the server can likewise return post-update version info if computed accurately.

### 6.1. Advertising Patch Formats

RFC 5789 defines the `Accept-Patch` header, often advertised in `OPTIONS` responses:

```http
OPTIONS /api/documents/1 HTTP/1.1

HTTP/1.1 204 No Content
Allow: GET, PUT, PATCH, OPTIONS
Accept-Patch: application/merge-patch+json, application/json-patch+json
```

This is an **HTTP example assuming the server supports both standards**; never advertise unimplemented formats. In Spring MVC, declaring `@PatchMapping(consumes = ...)` alone does not automatically emit an `Accept-Patch` header like the example. If you want to advertise it, configure the endpoint/response accordingly and test it.

## 7. Designing DTOs, Absent/Null, and Security for Updates

For resource-replacing PUTs, a qualifying DTO usually has explicit fields. For partial PATCHes, distinguish at least **three states**:

1. Field **absent** → leave untouched.
2. Field **present with a value** → replace with that value.
3. Field **present with null** → depends on format: JSON Merge Patch **deletes the key**, while a custom partial DTO might treat it as "set null", "clear data", or "disallowed".

If you bind PATCH directly to:

```java
record PatchProfile(String nickname, String phone) {}
```

then both `{}` and `{"phone":null}` produce `phone == null`, losing the distinction between "client did not send" and "client requested removal". To distinguish them, use `JsonNode`/`Map` with key-presence checks, or a dedicated three-state wrapper mapped explicitly.

**PUT vs. PATCH validation:** PUT typically applies constraints to the entire new representation. PATCH typically validates the **patch document**, applies the patch to a temporary candidate, and then validates the **resulting state of the whole resource** before commit. Do not validate only individual fields in isolation, because changing one field can break cross-field invariants.

**Security:**

- Allow modifying only published fields; reject `role`, `isAdmin`, `balance`, `createdAt` if the client lacks permission. Never bind requests directly to persistence entities with broad setters.
- Check authorization against the **resource ID** and each field/action; ETag does not replace authentication/authorization.
- Bound patch document size, operation count, JSON depth, JSON Pointer paths, and array indices.
- Apply patches atomically within a transaction; check business rules and concurrency before commit.
- Avoid echoing sensitive data or Jackson/JPA stack traces in error responses.

## 8. Spring Boot 3 + Java 17 Demo: PUT/PATCH + ETag/If-Match

This app manages exactly **one document** at `/api/documents/1`, stored **in-memory within one JVM** to illustrate semantics and request flow. There is no database, authentication, or multi-node synchronization. The code uses `synchronized` for atomic version checking and updates on **a single controller instance**; section 10 explains moving to real storage.

The demo supports:

- `GET /api/documents/1` returning the representation and strong ETag `"v1"`, `"v2"`...
- `PUT /api/documents/1` with the full representation and `If-Match`, leaving version unchanged if state is identical.
- `PATCH /api/documents/1` accepting only `application/merge-patch+json` for two flat fields `title` and `description`. Omitting a field preserves it; `description:null` removes it from the representation. `title` must be a non-blank string and cannot be removed.
- Rejecting unknown fields/wrong JSON types, ensuring **no partial update on invalid requests**.
- Returning 404 when ID != 1, 428 if `If-Match` is missing, 412 on stale tag, and 400 on invalid input.

This is a **fixed-schema subset** of JSON Merge Patch: the body must be an object containing only the two allowed fields. It is not a general-purpose JSON Merge Patch implementation for arbitrary JSON structures/arrays or arbitrary resources.

### 8.1. Project Structure

```text
document-update-demo/
├── pom.xml
└── src/
    ├── main/java/example/DocumentUpdateApplication.java
    └── test/java/example/DocumentControllerTest.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>document-update-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. DocumentUpdateApplication.java (Runnable Program)

All classes/records live in `src/main/java/example/DocumentUpdateApplication.java`. Java permits one `public` top-level class matching the filename alongside package-private classes.

```java
package example;

import java.util.Iterator;
import java.util.Map;
import java.util.Objects;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DocumentUpdateApplication {
    public static void main(String[] args) {
        SpringApplication.run(DocumentUpdateApplication.class, args);
    }
}

// Null description is omitted when serializing response JSON.
// For PUT, this is a full new representation; omitting description sets it to null.
@JsonInclude(JsonInclude.Include.NON_NULL)
record Document(@NotBlank String title, String description) {}

// Simple error body containing only a demo-defined code.
record ApiProblem(String code) {}

@RestController
@RequestMapping("/api/documents")
class DocumentController {

    private Document current = new Document("Draft", "Initial description");
    private long version = 1L;

    private String currentTag() {
        return "\"v" + version + "\"";
    }

    private ResponseEntity<?> guard(long id, String ifMatch) {
        if (id != 1L) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ApiProblem("NOT_FOUND"));
        }
        if (ifMatch == null || ifMatch.isBlank()) {
            return ResponseEntity.status(HttpStatus.PRECONDITION_REQUIRED)
                    .body(new ApiProblem("PRECONDITION_REQUIRED"));
        }
        // Demo only accepts a single strong ETag of form "vN".
        // Real products must parse tag lists and full preconditions
        // per RFC 9110.
        if (!ifMatch.equals(currentTag())) {
            return ResponseEntity.status(HttpStatus.PRECONDITION_FAILED)
                    .body(new ApiProblem("STALE_VERSION"));
        }
        return null;
    }

    @GetMapping("/{id}")
    public synchronized ResponseEntity<?> get(@PathVariable long id) {
        if (id != 1L) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ApiProblem("NOT_FOUND"));
        }
        return ResponseEntity.ok()
                .eTag(currentTag())
                .body(current);
    }

    @PutMapping(path = "/{id}",
                consumes = MediaType.APPLICATION_JSON_VALUE)
    public synchronized ResponseEntity<?> put(
            @PathVariable long id,
            @RequestHeader(value = "If-Match", required = false)
            String ifMatch,
            @Valid @RequestBody Document replacement) {

        ResponseEntity<?> precondition = guard(id, ifMatch);
        if (precondition != null) {
            return precondition;
        }

        // PUT sends a replacement representation. If the body equals the current
        // state, do not bump the version just because of a retry.
        if (!Objects.equals(current, replacement)) {
            current = replacement;
            version++;
        }

        // Subsequent GET provides the new ETag. Do not automatically emit
        // a validator on PUT responses when the server might transform data.
        return ResponseEntity.ok(current);
    }

    @PatchMapping(path = "/{id}",
                  consumes = "application/merge-patch+json")
    public synchronized ResponseEntity<?> patch(
            @PathVariable long id,
            @RequestHeader(value = "If-Match", required = false)
            String ifMatch,
            @RequestBody JsonNode patchDocument) {

        ResponseEntity<?> precondition = guard(id, ifMatch);
        if (precondition != null) {
            return precondition;
        }

        if (!patchDocument.isObject()) {
            return ResponseEntity.badRequest()
                    .body(new ApiProblem("INVALID_PATCH_DOCUMENT"));
        }

        // Build candidate first; never mutate current mid-way.
        String newTitle = current.title();
        String newDescription = current.description();

        Iterator<Map.Entry<String, JsonNode>> entries =
                patchDocument.fields();

        while (entries.hasNext()) {
            Map.Entry<String, JsonNode> entry = entries.next();
            String field = entry.getKey();
            JsonNode value = entry.getValue();

            if (field.equals("title")) {
                if (!value.isTextual() || value.asText().isBlank()) {
                    return ResponseEntity.badRequest()
                            .body(new ApiProblem("INVALID_TITLE"));
                }
                newTitle = value.asText();
            } else if (field.equals("description")) {
                if (!value.isNull() && !value.isTextual()) {
                    return ResponseEntity.badRequest()
                            .body(new ApiProblem("INVALID_DESCRIPTION"));
                }
                // Merge Patch: null means remove the property from the representation.
                newDescription = value.isNull() ? null : value.asText();
            } else {
                return ResponseEntity.badRequest()
                        .body(new ApiProblem("UNKNOWN_PATCH_FIELD"));
            }
        }

        Document candidate = new Document(newTitle, newDescription);

        // Single commit only after the entire patch passes validation.
        if (!candidate.equals(current)) {
            current = candidate;
            version++;
        }

        return ResponseEntity.ok(current);
    }
}
```

**Key mechanisms:**

- `currentTag()` is a strong token enclosed in `"..."`. This is an illustrative implementation: version advances when the representation changes; other instances would not share this counter in a multi-node deployment.
- `guard()` uses the tag read during GET, requires the header before PUT/PATCH, and blocks stale requests. `If-Match` in the demo uses **simple string equality**; production requires a full HTTP precondition parser/evaluator.
- PUT accepts `Document` with `@NotBlank title`; a valid body replaces the entire representation. Omitted `description` becomes `null` rather than being implicitly kept. `@JsonInclude(NON_NULL)` makes GET omit `description` when removed.
- PATCH accepts `JsonNode` to distinguish **absent fields** from **null fields**. Title cannot be deleted due to domain rules; null description removes the field from JSON output.
- Both PUT and PATCH advance version only when the final `Document` differs from the current one. Invalid patches return 400 before assigning `current`, satisfying atomicity for this in-memory resource.
- `synchronized` places the check and mutation under the same lock within one JVM. This is not a multi-instance production strategy.
- The API chooses an **update-only** policy for ID=1 and does not support PUT-create; other IDs return 404 per the demo contract.

### 8.4. Running and Testing with curl

Requires JDK 17+ and Maven; in the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

First read the resource and its ETag:

```bash
curl -i http://localhost:8080/api/documents/1
```

Illustrative response (other HTTP server headers may accompany it):

```http
HTTP/1.1 200 OK
ETag: "v1"
Content-Type: application/json

{"title":"Draft","description":"Initial description"}
```

**PUT replacement**:

```bash
curl -i -X PUT http://localhost:8080/api/documents/1 \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "v1"' \
  -d '{"title":"Published","description":"Final description"}'
```

Server returns **200** with body:

```json
{"title":"Published","description":"Final description"}
```

GET again:

```bash
curl -i http://localhost:8080/api/documents/1
```

Expect ETag `"v2"` because the representation changed. If you retry the exact same PUT with `If-Match: "v1"`, the server returns **412**:

```json
{"code":"STALE_VERSION"}
```

The resource remains `{"title":"Published","description":"Final description"}`; no second write occurred.

**PATCH removing only description**:

```bash
curl -i -X PATCH http://localhost:8080/api/documents/1 \
  -H 'Content-Type: application/merge-patch+json' \
  -H 'If-Match: "v2"' \
  -d '{"description":null}'
```

Success body:

```json
{"title":"Published"}
```

GET again shows ETag `"v3"` and a body without `description`. An omitted field in PATCH (such as `{"title":"Final"}`) preserves description, while `"description":null` intentionally removes it.

**Missing update precondition**:

```bash
curl -i -X PATCH http://localhost:8080/api/documents/1 \
  -H 'Content-Type: application/merge-patch+json' \
  -d '{"title":"Danger"}'
```

Expect **428** with:

```json
{"code":"PRECONDITION_REQUIRED"}
```

Note: the `curl` snippets above use POSIX shell line continuations; PowerShell users can run `curl.exe` on one line or adapt multiline syntax accordingly.

### 8.5. MockMvc: Proving Replacement, Partial Update, Retries, and Preconditions

File `src/test/java/example/DocumentControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.BEFORE_EACH_TEST_METHOD)
class DocumentControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getExposesInitialStrongEtag() throws Exception {
        mvc.perform(get("/api/documents/1"))
            .andExpect(status().isOk())
            .andExpect(header().string("ETag", "\"v1\""))
            .andExpect(jsonPath("$.title").value("Draft"));
    }

    @Test
    void putReplacesAndRetryWithStaleEtagDoesNotOverwrite() throws Exception {
        String body =
                "{\"title\":\"Published\","
              + "\"description\":\"Final description\"}";

        mvc.perform(put("/api/documents/1")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("If-Match", "\"v1\"")
                    .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Published"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v2\""));

        mvc.perform(put("/api/documents/1")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("If-Match", "\"v1\"")
                    .content(body))
            .andExpect(status().isPreconditionFailed())
            .andExpect(jsonPath("$.code").value("STALE_VERSION"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(status().isOk())
            .andExpect(header().string("ETag", "\"v2\""))
            .andExpect(jsonPath("$.description")
                    .value("Final description"));
    }

    @Test
    void putWithSameRepresentationHasNoAdditionalEffect() throws Exception {
        String same =
                "{\"title\":\"Draft\","
              + "\"description\":\"Initial description\"}";

        for (int n = 0; n < 2; n++) {
            mvc.perform(put("/api/documents/1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("If-Match", "\"v1\"")
                        .content(same))
                .andExpect(status().isOk());
        }

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v1\""));
    }

    @Test
    void patchDistinguishesOmittedFieldAndExplicitNull() throws Exception {
        mvc.perform(patch("/api/documents/1")
                    .contentType("application/merge-patch+json")
                    .header("If-Match", "\"v1\"")
                    .content("{\"title\":\"Published\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Published"))
            .andExpect(jsonPath("$.description")
                    .value("Initial description"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v2\""));

        mvc.perform(patch("/api/documents/1")
                    .contentType("application/merge-patch+json")
                    .header("If-Match", "\"v2\"")
                    .content("{\"description\":null}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.description").doesNotExist());

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v3\""))
            .andExpect(jsonPath("$.description").doesNotExist());
    }

    @Test
    void patchWithNoStateChangeCanRepeatWithSameEtag() throws Exception {
        for (int n = 0; n < 2; n++) {
            mvc.perform(patch("/api/documents/1")
                        .contentType("application/merge-patch+json")
                        .header("If-Match", "\"v1\"")
                        .content("{\"title\":\"Draft\"}"))
                .andExpect(status().isOk());
        }

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v1\""));
    }

    @Test
    void incompletePutReplacesAbsentOptionalField() throws Exception {
        mvc.perform(put("/api/documents/1")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("If-Match", "\"v1\"")
                    .content("{\"title\":\"Only title\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Only title"))
            .andExpect(jsonPath("$.description").doesNotExist());
    }

    @Test
    void missingConditionIs428AndLeavesStateIntact() throws Exception {
        mvc.perform(put("/api/documents/1")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"title\":\"Other\", \"description\":\"Text\"}"))
            .andExpect(status().is(428))
            .andExpect(jsonPath("$.code")
                    .value("PRECONDITION_REQUIRED"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v1\""));
    }

    @Test
    void invalidPatchFailsAtomically() throws Exception {
        mvc.perform(patch("/api/documents/1")
                    .contentType("application/merge-patch+json")
                    .header("If-Match", "\"v1\"")
                    .content(
                        "{\"title\":\"Changed\", \"privileged\":true}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("UNKNOWN_PATCH_FIELD"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v1\""))
            .andExpect(jsonPath("$.title").value("Draft"));
    }

    @Test
    void invalidPutDataCannotReplaceResource() throws Exception {
        mvc.perform(put("/api/documents/1")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("If-Match", "\"v1\"")
                    .content(
                        "{\"title\":\"\", \"description\":\"Ignored\"}"))
            .andExpect(status().isBadRequest());

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v1\""));
    }

    @Test
    void unsupportedPatchMediaTypeIs415() throws Exception {
        mvc.perform(patch("/api/documents/1")
                    .contentType(MediaType.TEXT_PLAIN)
                    .header("If-Match", "\"v1\"")
                    .content("title=Changed"))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

Run `mvn test`. Each test gets a fresh Spring context via `@DirtiesContext(BEFORE_EACH_TEST_METHOD)` to reset initial in-memory state back to `"v1"`; this is simple for a small example, though relatively expensive with many tests. In a real project, replace it with controlled test fixtures and also test transaction/concurrency behavior at the persistence layer.

The tests verify **final state** after updates/retries. Asserting status 200 alone is not enough to prove idempotency or absence of lost updates.

## 9. Designing Retries When Uncertain If the Previous Call Succeeded

### 9.1. Retrying PUT

If PUT is designed with true replacement semantics, repeating a request with the same body normally brings state to the same desired representation. With If-Match:

1. Send PUT with `If-Match: "vN"`.
2. On **200/204**, update local cache or re-GET if a new version token is needed.
3. On timeout and retry, you may receive **412** because the first attempt already committed. Do not treat 412 as proof that "none of the attempts succeeded"; GET and compare.
4. If the latest state matches your target, treat it as "desired state already reached" when the workflow allows. If it differs, surface the conflict/offer a merge.
5. Never automatically drop `If-Match` after getting 412 to "force the write through"; doing so can overwrite someone else's work.

### 9.2. Retrying PATCH

Classify patches:

- **Target-state patches:** `{"title":"Final"}` with Merge Patch can run multiple times without changing content after the first run; still use If-Match to avoid updating a stale version.
- **State-dependent patches:** JSON Patch with `test` or `remove`; retries can fail because the base changed; GET and recompute.
- **Cumulative patches:** `{"increment":1}` is a custom command contract rather than pure RFC Merge Patch; blind retries double-apply it.
- **Append patches:** JSON Patch adding to `/items/-` can duplicate elements; requires deduplication tokens or item identity policies.

If PATCH is non-idempotent, use an **idempotency key** if the server supports it, redesign as "set desired state" / item resources with stable URIs, or combine preconditions with reconciliation logic. Do not assume simply sending `If-Match` makes retries replay the identical response: If-Match only guards the **pre-apply version**, not storing outcomes of past requests.

### 9.3. Idempotency-Key for Non-Idempotent Operations

Business example adding a payment:

```http
POST /api/payments HTTP/1.1
Idempotency-Key: 58f147f6-6b4d-4f8b-9b2e-1a1c4ef9a53a
Content-Type: application/json

{"orderId":42,"amount":150000}
```

This is an **API-implemented contract**. A header does nothing by itself unless the server implements handling. The backend must:

1. Scope the key properly (user/tenant + operation + key) and fingerprint the request; same key with a different payload → appropriate error.
2. Claim the key **atomically** alongside the transaction so two concurrent requests cannot both execute.
3. Persist in-progress/succeeded/failed states and replayable outcomes per policy; never run side effects a second time once the key completed.
4. Set retention TTLs and recovery handling for process crashes, timeouts, and retries.
5. For external events/payments, combine transaction/outbox, provider idempotency keys, or consumer deduplication. Never store keys only in an in-process `HashMap` when multi-instance safety is needed.

The same principle applies to append/increment PATCHes if business rules need an exactly-once effect. This does not automatically make the HTTP PATCH method globally idempotent; it makes **one specific operation** safer to retry.

## 10. From a Single-JVM Demo to Production Spring MVC

The demo uses `synchronized` to illustrate atomic updates; production deployments must coordinate storage, validation, authorization, and events.

### 10.1. Using JPA `@Version`

Illustrative entity:

```java
@Entity
class DocumentEntity {
    @Id
    private Long id;

    @Version
    private long version;

    private String title;
    private String description;

    // Constructors, getters, and setters omitted;
    // this is a non-standalone illustrative snippet.
}
```

On GET, read the version tied to the representation and build the ETag. On PUT/PATCH, verify the client's `If-Match` matches the version and apply the change inside a transaction. Hibernate/JPA optimistic locking checks the version on flush/commit; on `OptimisticLockException` or `ObjectOptimisticLockingFailureException`, respond according to the contract (e.g., 412 if the If-Match precondition is no longer valid, or 409 for other conflicts). Mapping exceptions to statuses must depend on **cause and precondition semantics**, rather than blindly treating every DB exception as 412.

### 10.2. Unifying Version Checks and Side Effects

A production flow should look like:

```text
Authentication/Authorization
   → Identify resource & permissions
   → Parse and validate representation / patch document
   → Begin transaction
       → Read and lock/CAS by version
       → Evaluate If-Match
       → Build candidate state
       → Validate full-resource invariants
       → Save state + new version if changed
       → Write outbox event in the same transaction if needed
   → Commit
   → Return response / ETag (if compliant with HTTP spec)
   → Outbox publisher sends event, consumer performs deduplication
```

With storage supporting compare-and-swap, you can use the pattern:

```sql
UPDATE documents
SET title = :new_title,
    description = :new_description,
    version = version + 1
WHERE id = :id AND version = :expected_version;
```

If affected rows = 0, check whether the resource no longer exists or its version changed, then return 404/412 accordingly. This SQL snippet only illustrates conditional updates; to preserve **"do not create a new version if PUT sends identical data"**, compare the desired state with current state under the same lock/CAS, or pick an appropriate versioning policy and verify retries do not duplicate business side effects.

### 10.3. Validating After Applying a Patch

Never mutate a persistence-context-managed entity, flush early, and only afterward check another patch field. A safe pattern:

1. Parse the patch into a **temporary** structure, checking allowed fields and type/null rules.
2. Create a **candidate copy** of the resource state based on the verified version.
3. Apply the **entire** patch to the candidate.
4. Run Bean Validation + domain invariants on the **final candidate**.
5. If valid, persist all changes in one transaction; if any step fails, roll back everything.
6. Never emit events or alter external state until the transaction commits.

For JSON Patch with multiple operations, atomicity is critical: if the third operation fails, the first two **must not** remain persisted as a partial update.

### 10.4. Which Representation Should an ETag Describe?

An ETag is a validator for a **representation**, not an arbitrary DB column. If the same resource has multiple representations by media type, language, or encoding, handle validators/variants carefully. An ETag should not contain only a DB version number if the representation can change without bumping that version, or if different-byte representations share the same strong tag.

In the demo, the representation is two JSON fields in one JVM and the version increments whenever data changes; thus the ETag simulates a strong validator within that fixed scope. Real products must ensure the validator truly matches the GET response, updates whenever anything affecting the representation changes, and obeys HTTP preconditions.

## 11. Common Design Mistakes

| Mistake | Risk | Fix |
| --- | --- | --- |
| Using PUT to merge body fields without documenting it | Clients think they replace everything while old data persists | Clearly separate full replacement and partial patch |
| Using PATCH without defining media type/semantics | Unclear meaning of null/omitted/arrays | Choose JSON Merge Patch, JSON Patch, or explicit custom contract |
| Assuming all PATCHes are non-idempotent | Misses target-state update patterns | Classify operations and guarantee retry effects |
| Assuming all PATCHes are idempotent | Append/increment gets doubled | Use preconditions/idempotency keys or redesign model |
| Adding `synchronized` only and deploying multiple instances | Two instances still overwrite each other | DB transactions/versioning/CAS |
| Checking If-Match before starting the transaction | Race between check and write | Atomic conditional write |
| Returning 409 when ETag is stale | Clients cannot distinguish HTTP precondition failures | Return 412 when If-Match fails |
| Dropping If-Match when a retry gets 412 | Overwrites another user's changes | GET, reconcile, send new request with new tag |
| Returning 428 when a tag was sent but wrong | Confuses missing condition with failed condition | 428 for missing, 412 for mismatch |
| Using `If-Match: *` to prevent lost updates | Only checks whether the resource exists | Use a specific strong version tag |
| PUT omitting a field silently preserves old value | Not true full replacement | Clear PUT DTO contract and full validation |
| JSON Merge Patch `null` treated as "store null" | Violates RFC 7396, may delete unintentionally | Null deletes the field; if JSON null is needed, use another format |
| Blindly retrying JSON Patch `add /items/-` | Appends duplicate elements | Use deduplication or element identity |
| PATCH applies operations one by one then errors out | Resource left half-updated | Full transaction/rollback |
| Validating only fields present in the patch | Misses cross-field invariants | Validate the post-merge candidate |
| Binding entities containing `role`/`balance` | Mass assignment/privilege escalation | DTOs, allowlists, authorization |
| Returning ETag after PUT when server transformed request data | Violates HTTP validator rules | Emit validator only when compliant, or let client re-GET |
| Retries emit extra emails/events/payments | Duplicate business side effects | Outbox + dedup/idempotency keys |
| Treating 412 after timeout as "definitely never committed" | User repeats action or mis-handles conflict | GET actual state and reconcile |

## 12. Self-Check Exercises

1. **PUT** `{"title":"A","description":"B"}` twice to the same URL with no competing updates. Does the final state differ? **No**; both aim for A/B. If the same old If-Match is reused on the second call it may return 412, without overwriting.
2. **PUT** only `{"title":"A"}` when the endpoint specifies full replacement. Should the server silently keep `description`? **Not by default**. Omitting a field follows the full-representation schema or errors if required.
3. **PATCH Merge Patch** sends `{"description":null}`. Does that set description to JSON null? **No per RFC 7396**; that is a request to delete the member.
4. **PATCH Merge Patch** sends `{}`. What happens? **No field changes requested**; resulting state matches prior state (assuming valid input and no extra server business side effects).
5. **PATCH JSON Patch** `add` to `/items/-` is retried. What is the issue? **May append a second time**, so it cannot be considered idempotent without deduplication.
6. If Client A and B both GET ETag `"v7"`, A updates first to `"v8"`, and B PUTs with `If-Match: "v7"`, what happens? **412**, without overwriting A.
7. If an API requires If-Match and a PUT omits it, what status applies? **428 Precondition Required** per API policy.
8. If a request sends If-Match and it no longer matches, what status applies? **412 Precondition Failed**.
9. Does sending `If-Match: *` prevent lost updates? **Not enough**, because it only checks resource existence.
10. Does HTTP 204 carry a JSON body? **No**; if you want to return a representation, use 200.
11. Which HTTP status should a successful PUT creating a nonexistent resource return? **201 Created**.
12. Why is `PATCH` not automatically concurrency-safe even when sending only one field? **Because it can collide on the same field another client edited or depend on stale base state**, so concurrency control is still needed.
13. A service sends an email on every PUT even when state did not change. Is there a problem? **Yes**, with business side effects on retry; restrict emails to actual state transitions and use dedup/outbox.
14. Can you put `synchronized` on a controller to prevent lost updates across 5 Spring Boot instances? **No**; that lock lives only inside each individual JVM.
15. When a PATCH has 5 operations and the fifth fails, is committing the first 4 compliant with RFC 5789? **No**, patches must be atomic.
16. If a PATCH body is `application/json` while the server only supports `application/merge-patch+json`, what status fits? **415 Unsupported Media Type**.
17. After a timeout, a retried PUT gets 412. Can you conclude the first attempt failed? **No**; GET to inspect current state before deciding the next step.
18. If the database stores `version=8` while the GET representation changes from a secondary source outside the DB, is a strong ETag `"v8"` still accurate? **Not necessarily**; the validator must change whenever the actual representation changes.

## 13. Official Sources and References

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): PUT semantics, idempotency, status codes, ETag, and `If-Match` preconditions.
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789): PATCH semantics, atomicity, design-dependent idempotency, `Accept-Patch`.
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396): JSON Merge Patch structure, absent/null, object and array handling.
- [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902): `add`, `remove`, `replace`, `move`, `copy`, `test`.
- [RFC 6901 — JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901): path syntax in JSON Patch.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): status 428 Precondition Required.
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods.html): `@PutMapping`, `@PatchMapping`, request mapping.
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): selecting converters by `Content-Type`, binding JSON to DTOs.
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html): persistence-layer locking mechanisms; pairing with appropriate versioning/transactions.

**Key takeaway:** `PUT` expresses the **desired resource state after updating** and is idempotent per HTTP; `PATCH` expresses **changes to apply**, where idempotency depends on format and operation. **ETag/If-Match** prevents overwriting based on stale reads; **idempotency keys/deduplication** protect non-repeatable business side effects. Verify behavior by checking state after requests and after retries, not merely a single HTTP status code.
