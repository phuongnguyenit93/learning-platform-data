# If-Match, Preconditions, and Optimistic Concurrency Control in Spring MVC

> **Scope:** HTTP conditional requests per RFC 9110, Spring Web MVC on the Servlet stack, Java 17+, and Spring Boot 3.x / Spring Framework 6.x. This topic explains how to use **`ETag` + `If-Match`** to prevent **lost updates**, distinguish `412 Precondition Failed` from `428 Precondition Required`, understand strong/weak comparison, other conditional headers, and **atomicity of check-and-write**. It includes a runnable Java REST example, `curl` commands reproducing two users editing the same resource, MockMvc tests, DB optimistic locking strategies, and security notes.

## 1. The Problem: Two Users Overwriting Each Other's Changes

Suppose an API stores a shared document. Initially the document contains:

```json
{
  "id": "1",
  "content": "Initial version",
  "revision": 1
}
```

Alice and Bob open the document concurrently. Alice edits it to `"Alice's content"` and saves successfully. Bob is still viewing revision 1 and clicks Save with `"Bob's content"`.

If the API uses a plain PUT and overwrites without checking version:

```text
T0: server revision 1: "Initial version"
T1: Alice GET -> revision 1
T2: Bob   GET -> revision 1
T3: Alice PUT "Alice's content" -> revision 2
T4: Bob   PUT "Bob's content"   -> revision 3
                                       |
                                Alice's change is lost
```

This is a **lost update**: the later update overwrites the earlier one even though the second user never saw the newer change.

To prevent this, the server emits a **validator** for the current representation version, such as:

```http
HTTP/1.1 200 OK
ETag: "rev-1"
Content-Type: application/json

{"id":"1","content":"Initial version","revision":1}
```

On PUT, the client sends the ETag it observed:

```http
PUT /api/docs/1 HTTP/1.1
Content-Type: application/json
If-Match: "rev-1"

{"content":"Alice's content"}
```

The server updates only if the current representation still has the matching ETag. Once Alice's update succeeds, the server issues a new ETag `"rev-2"`. When Bob sends the stale `If-Match: "rev-1"`, the server **does not overwrite** and returns `412 Precondition Failed`.

**Remember:** `If-Match` is not a command locking the document while a user has the form open. It is a **precondition checked when the server processes the request**. To truly prevent lost updates, comparing the precondition and writing the data must execute **atomically** relative to other writers.

## 2. Concepts: Representation, Validator, and ETag

### 2.1. What Is an ETag?

An `ETag` (entity tag) is HTTP response metadata indicating the version of the **selected representation**. For example:

```http
ETag: "rev-42"
```

Syntactically, an entity tag is a double-quoted value; it **need not be a hash**, and clients should treat its contents as an **opaque identifier**. The server decides how to issue, compare, and advance tags.

Common strategies:
- A record revision number, e.g., `"rev-42"`.
- A hash of representation bytes, when hashing cost and encoding align.
- An opaque random token rotated whenever the representation changes.
- A composite token derived from version and variant metadata.

**Never conclude that two matching ETags prove a user is authorized to access a resource.** ETags serve only validation/conditional requests and never replace authentication or authorization.

### 2.2. Strong and Weak ETags

Examples:

```http
ETag: "abc123"
ETag: W/"abc123"
```

- `"abc123"`: **strong validator**.
- `W/"abc123"`: **weak validator** (`W/` prefix), indicating two representations are weakly equivalent even if bytes differ.
- `If-Match` **requires strong comparison**. A weak tag **never matches** a strong tag with the same text, nor do two weak tags strong-match each other.

Table:

| Current ETag | Client `If-Match` | Condition result |
| --- | --- | --- |
| `"rev-7"` | `"rev-7"` | Strong match |
| `"rev-7"` | `"rev-6"` | No match |
| `"rev-7"` | `W/"rev-7"` | No strong match |
| `W/"rev-7"` | `W/"rev-7"` | No strong match |
| `"rev-7"` | `"rev-5", "rev-7"` | One tag matches; condition holds |
| Resource currently exists | `*` | Existence condition holds |
| Resource does not exist | `*` | Existence condition fails |

Converters, content encodings like gzip, and representation variants can alter transmitted bytes. A strong validator must satisfy the requirements of the **selected representation**; do not reuse the exact same strong ETag across two differently encoded representations if doing so violates strong validation. A database version can back a strong ETag when policy guarantees it advances on every representation-relevant change.

### 2.3. Does Hashing in an ETag Make It Safer?

Hashing does not automatically mean security:
- A hash does not check permissions.
- A hash of confidential content exposed in an ETag may reveal state or structure information in some threat models.
- A hash over JSON depends on serialization rules: field ordering, null omission, character encoding, content coding, locale, or projection.
- Weak hashes or unmanaged variants can collide or conflate distinct representations.

For standard CRUD REST APIs, a monotonically increasing database-protected revision is usually simpler than hashing full bodies on every PUT.

## 3. What Does the If-Match Header Actually Require?

Per RFC 9110 §13.1.1, `If-Match` conditions the request on one of two requirements:
1. If the value is `*`, the target resource has **at least one current representation**.
2. If it is a list of ETags, there is **a strong ETag match** between a client-supplied validator and the current selected representation.

Examples:

```http
If-Match: "rev-7"
```

```http
If-Match: "rev-6", "rev-7"
```

```http
If-Match: *
```

A server proceeds to the write only when the condition holds; when it fails, the server normally returns **412 Precondition Failed** without applying the mutating PUT/DELETE. The RFC permits a narrow exception if the server can prove the state-changing operation **already occurred previously** (e.g., a retry after a dropped response), yet you should never casually return 2xx on a mismatch.

### 3.1. Wildcard `*` Does Not Detect Stale Edits

`If-Match: *` only requires that the resource **exists**. If Alice just updated revision 1 to 2, Bob sending `If-Match: *` can still be accepted, overwriting Alice.

Therefore:
- In an API implementing full HTTP semantics, `*` is valid when the target exists.
- If a product **must prevent lost updates on all edits**, enforce a **stricter application contract**, such as accepting only **concrete strong version tags** on update routes; document the policy and failure status clearly.
- In the runnable example below, to illustrate the RFC, `*` is accepted when the resource exists, while the lesson **explicitly notes it does not prevent stale overwrites**.

### 3.2. When Are Preconditions Evaluated?

HTTP preconditions are **not** a way to bypass access control. The server must enforce authentication/authorization, target existence, and request validity before performing writes. RFC 9110 only requires evaluating preconditions when an unconditional request (ignoring preconditions) would otherwise succeed or in specific applicable cases.

Never leak ETags or sensitive existence info to unauthorized callers just because they sent `If-Match`. An API where the caller lacks permission should still return `401`/`403`/`404` per security contract, never letting `412` accidentally disclose resource existence or version.

### 3.3. Precedence Among Conditional Headers

RFC 9110 specifies the evaluation order when multiple conditional headers appear:

1. `If-Match`, if present, is evaluated first.
2. `If-Unmodified-Since` is evaluated only if `If-Match` is absent.
3. `If-None-Match` is evaluated next; for GET/HEAD, failure can return `304`, whereas for state-changing methods it yields `412`.
4. `If-Modified-Since` applies to GET/HEAD only when `If-None-Match` is absent; `If-Range` has its own rules for Range requests.

**Never write code that reads `If-Unmodified-Since` despite `If-Match` being present and combines them with an arbitrary AND.** When implementing general HTTP conditional requests, follow the RFC and use your framework/container APIs properly.

## 4. Distinguishing 200, 204, 304, 409, 412, and 428

| HTTP status | When typically appropriate? | Did an update occur? |
| --- | --- | --- |
| `200 OK` | PUT succeeded and returns the new representation | Yes |
| `204 No Content` | PUT/DELETE succeeded without a response body | Yes, or deletion succeeded |
| `304 Not Modified` | GET/HEAD with matching `If-None-Match` or compatible cache validator | **Not an update** |
| `409 Conflict` | Domain/state conflict not purely caused by a stale precondition header | Usually no |
| `412 Precondition Failed` | `If-Match` fails to match current representation, or another precondition fails | Write **must not be applied** |
| `428 Precondition Required` | API requires a precondition and client **omitted** it | No |
| `400 Bad Request` | Malformed `If-Match` syntax or invalid request body per contract | No |
| `404 Not Found` | Target resource does not exist or is hidden by ACL | No |
| `401/403` | Unauthenticated / insufficient permissions | No |

**Do not confuse 304 and 412:**
- `If-None-Match` on GET serves **cache revalidation**: unchanged data returns `304` to skip resending the body.
- `If-Match` on PUT/PATCH/DELETE serves **write control**: changed version returns `412`.

**Do not confuse 409 and 412:** If the entity is at the right revision yet domain state forbids the operation (e.g., an already-shipped order cannot change address), `409` may fit. If the client's validator no longer matches the current revision, `412` expresses the reason more accurately.

### 4.1. Complete Sequential Example

```http
GET /api/docs/1
→ 200 OK
ETag: "rev-1"

{"id":"1","content":"Initial version","revision":1}
```

Alice sends:

```http
PUT /api/docs/1
If-Match: "rev-1"
Content-Type: application/json

{"content":"Alice edited"}
```

Server responds:

```http
HTTP/1.1 200 OK
ETag: "rev-2"

{"id":"1","content":"Alice edited","revision":2}
```

Bob sends the old tag:

```http
PUT /api/docs/1
If-Match: "rev-1"
Content-Type: application/json

{"content":"Bob edited on old version"}
```

Server responds:

```http
HTTP/1.1 412 Precondition Failed
```

**Alice's saved value remains untouched.** Bob must GET the newer version, display diffs or merge content per UX, and retry using the current tag. Never auto-retry PUT with the new ETag using Bob's stale content, as that defeats optimistic concurrency.

## 5. How Does If-Match Differ from If-None-Match?

| Header | Core semantics | Usage pattern |
| --- | --- | --- |
| `If-Match: "tag"` | Execute only if there is a **strong match** with the current selected representation | PUT/PATCH/DELETE preventing lost updates |
| `If-Match: *` | Execute only if the resource currently exists | Avoid writing to non-existent resource; **no revision check** |
| `If-None-Match: "tag"` | Execute only if there is **no weak match** per RFC; GET/HEAD can return `304` | Cache revalidation |
| `If-None-Match: *` | Execute only if the target **does not exist yet** | Conditional create (suitable PUT/POST) |
| `If-Unmodified-Since: <date>` | Do not update if resource changed after that timestamp | Fallback when ETag is unavailable |
| `If-Modified-Since: <date>` | GET/HEAD only if resource changed after that timestamp | `Last-Modified`-based cache revalidation |

HTTP timestamps normally have one-second resolution; rapid sequential updates within a single second cannot be distinguished reliably. For rapidly changing resources, concrete strong ETags backed by atomic versions are usually safer than `If-Unmodified-Since`.

### 5.1. Conditional Create

Suppose a client wants to create a resource at a client-chosen URI without overwriting an existing one:

```http
PUT /api/configs/app-A
If-None-Match: *
Content-Type: application/json

{"mode":"safe"}
```

If the resource **already exists**, the condition fails: return `412`. If absent and the caller is authorized, the server creates it. Checking absence and inserting must be atomic, such as via a `UNIQUE` constraint or transaction; if two create requests arrive concurrently, only one may succeed per policy.

This is **a different use case** from `If-Match` for updates.

## 6. Spring MVC: ResponseEntity, ETag, and WebRequest

### 6.1. Returning ETag via ResponseEntity

```java
@GetMapping("/{id}")
public ResponseEntity<DocumentDto> get(@PathVariable String id) {
    DocumentDto dto = service.find(id);
    return ResponseEntity.ok()
            .eTag("\"rev-" + dto.revision() + "\"")
            .body(dto);
}
```

This is an **illustrative snippet**, requiring `DocumentDto` and `service`. `ResponseEntity.BodyBuilder#eTag(String)` sets the `ETag` header. Ensure the string properly represents a strong tag; many Spring versions add quotes automatically when needed, though supplying an already-quoted string keeps the contract explicit.

Never emit `"rev-7"` for a representation whose content changed without bumping the revision. Never expose raw-secret-based ETags if they create disclosure risks.

### 6.2. Reading If-Match in a Controller

```java
@PutMapping("/{id}")
public ResponseEntity<?> put(
        @PathVariable String id,
        @RequestHeader HttpHeaders headers,
        @RequestBody UpdateDocument request) {

    List<String> validators = headers.getIfMatch();
    // Must check for missing header, compare STRONGLY, and perform an atomic update.
    return ResponseEntity.noContent().build();
}
```

This is a **snippet, not a safe implementation**. `HttpHeaders#getIfMatch()` is Spring's API for parsing the validator list, and may throw `IllegalArgumentException` on parse failure. Successfully reading it does not satisfy the precondition; the update service must compare the current ETag against those validators.

Alternatively, you can use `@RequestHeader(value="If-Match", required=false) String header`, but production code must properly parse HTTP entity-tag lists, quoted strings/commas, weak tags, and wildcards. Never use `String.contains(currentTag)` or naive `split(",")` ignoring quotes; that is not RFC-compliant strong ETag comparison.

### 6.3. WebRequest#checkNotModified

Spring provides:

```java
@GetMapping("/{id}")
public ResponseEntity<DocumentDto> get(
        @PathVariable String id, WebRequest webRequest) {

    DocumentDto dto = service.find(id);
    String currentETag = "\"rev-" + dto.revision() + "\"";

    if (webRequest.checkNotModified(currentETag)) {
        return null; // Handler return type needs proper design.
    }

    return ResponseEntity.ok().eTag(currentETag).body(dto);
}
```

This **illustrates the idea**, though returning `null` from a method declared to return `ResponseEntity<DocumentDto>` is awkward in many designs; Spring MVC handles `null` specially on certain signatures, so verify carefully. The common pattern in Spring docs is a method returning a view `String`, `void`, or suitable type where returning after `checkNotModified(...)` returns `true` stops further processing.

`WebRequest#checkNotModified(etag)` / `ServletWebRequest` supports conditional GET/HEAD caching and also recognizes conditional POST/PUT/DELETE in certain flows. **However:** it does not replace **atomic compare-and-set at the storage layer**. If you check the ETag in the controller and someone else writes before the service updates, lost updates can still happen.

Documented view-GET example:

```java
@GetMapping("/pages/{id}")
public String page(@PathVariable String id,
                   WebRequest webRequest,
                   Model model) {
    Article article = articleService.find(id);
    if (webRequest.checkNotModified(article.etag())) {
        return null;
    }
    model.addAttribute("article", article);
    return "article";
}
```

This snippet requires `Article`, `articleService`, and a view resolver, illustrating conditional GET only. When using `ResponseEntity.eTag(...)`, verify how Spring MVC's return-value handlers interact with `If-None-Match` and avoid calling `checkNotModified` redundantly.

### 6.4. Why Not Check Only in the Controller?

**Racy code:**

```java
// ANTI-PATTERN: check and write are two actions not locked together.
if (ifMatch.equals(repo.findById(id).etag())) {
    repo.save(newContent);
}
```

Two requests can both read revision 1, both pass the check, and overwrite each other sequentially. The HTTP header is the communication step; **a backend transaction/lock/CAS is what enforces the final guarantee**.

## 7. Runnable Example: Spring Boot 3.x + Java 17, Synchronized CAS

This example uses only the **Spring Web** dependency, in-memory data, and a `synchronized` lock. Its goal is to prove that **stale PUT requests are rejected** and compare-and-write executes **atomically within one JVM**.

**Important:** `synchronized` in this demo protects only one `DocumentStore` instance inside **a single JVM**. With 2+ pods/instances or a database, you need **database optimistic locking / atomic UPDATE** as in section 10. In-memory state is lost on restart, and the demo omits authentication, authorization, persistence, and CSRF.

### 7.1. Project Setup

Create a Maven project on [Spring Initializr](https://start.spring.io/), Java 17+, Spring Boot 3.x, with dependency **Spring Web**:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

That is the POM dependency generated by Initializr. Create one standalone Java file under `src/main/java/com/example/demo/DemoApplication.java`.

### 7.2. Complete Java Code

```java
package com.example.demo;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

// Immutable value objects, safe when leaving the synchronized block.
record DocumentView(String id, String content, long revision) {
    String strongETag() {
        return "\"rev-" + revision + "\"";
    }
}

record ReplaceDocument(String content) {
}

@Service
class DocumentStore {

    private String content = "Ban dau";
    private long revision = 1L;

    private static void requireExistingId(String id) {
        if (!"1".equals(id)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found");
        }
    }

    // Snapshot read does not interleave with an unfinished update.
    public synchronized DocumentView get(String id) {
        requireExistingId(id);
        return new DocumentView(id, content, revision);
    }

    // Compare If-Match and update inside the SAME lock.
    public synchronized DocumentView replace(
            String id,
            List<String> requestedValidators,
            ReplaceDocument command) {

        requireExistingId(id);

        if (command == null
                || command.content() == null
                || command.content().isBlank()
                || command.content().length() > 200) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid content");
        }

        String currentETag = "\"rev-" + revision + "\"";

        // RFC: * matches when target already exists.
        // * does NOT protect against stale overwrites.
        boolean matches = requestedValidators.contains("*");

        if (!matches) {
            for (String requested : requestedValidators) {
                // Compare by equality against STRONG tag.
                // W/"rev-N" differs from "rev-N" and will not match.
                if (currentETag.equals(requested)) {
                    matches = true;
                    break;
                }
            }
        }

        if (!matches) {
            throw new ResponseStatusException(
                    HttpStatus.PRECONDITION_FAILED,
                    "If-Match does not match current revision");
        }

        // While holding the lock, no writer can interleave between check and write.
        content = command.content();
        revision++;
        return new DocumentView(id, content, revision);
    }
}

@RestController
@RequestMapping("/api/docs")
class DocumentController {

    private final DocumentStore store;

    DocumentController(DocumentStore store) {
        this.store = store;
    }

    @GetMapping("/{id}")
    public ResponseEntity<DocumentView> get(
            @PathVariable("id") String id) {

        DocumentView current = store.get(id);

        return ResponseEntity.ok()
                .eTag(current.strongETag())
                .cacheControl(CacheControl.noStore())
                .body(current);
    }

    @PutMapping(
            path = "/{id}",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<DocumentView> replace(
            @PathVariable("id") String id,
            @RequestHeader HttpHeaders headers,
            @RequestBody ReplaceDocument command) {

        if (!headers.containsKey(HttpHeaders.IF_MATCH)) {
            throw new ResponseStatusException(
                    HttpStatus.PRECONDITION_REQUIRED,
                    "Send If-Match from a prior GET");
        }

        List<String> validators;
        try {
            validators = headers.getIfMatch();
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Malformed If-Match");
        }

        if (validators.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Empty If-Match");
        }

        // Atomic compare and write happens inside store.
        DocumentView updated =
                store.replace(id, validators, command);

        return ResponseEntity.ok()
                .eTag(updated.strongETag())
                .cacheControl(CacheControl.noStore())
                .body(updated);
    }
}
```

### 7.3. Guarantees and Limitations of the Code

- `DocumentView` is an immutable record; GET reads a snapshot and attaches the ETag of **that exact snapshot revision**.
- `@RequestHeader HttpHeaders` uses the official `getIfMatch()` parser rather than checking a raw string with `contains()`.
- Missing `If-Match` returns `428`; mismatching validator returns `412`.
- If the client sends `W/"rev-1"`, the weak string differs from `"rev-1"`, so the precondition fails.
- If the client sends multiple strong tags and at least one matches the current tag, the condition passes.
- `If-Match: *` is accepted when document ID `1` exists, **matching existence semantics**, yet does not guard against stale overwrites. APIs requiring version checks on every update must explicitly reject wildcards.
- `synchronized` ensures two threads cannot check and mutate the same `DocumentStore` instance simultaneously. When two requests arrive almost concurrently with `If-Match: "rev-1"`, one advances revision to `2` and the other receives `412`.
- `CacheControl.noStore()` here avoids caching the document while still emitting `ETag` as a version validator. In environments where caching is desired, pick policies matching permissions, `Vary`, and visibility.
- The code does not handle HTTP authentication/authorization. Real apps must check user/tenant/ACL **before disclosing the current ETag or writing the resource**.
- The code does not support create, delete, patch, variants, persistence, or automatic merging; do not treat it as a complete HTTP resource server.
- The GET method uses `ResponseEntity.eTag(...)`; Spring MVC handles conditional GET/HEAD with ETag via its return-value mechanism. The tests below focus on PUT and versioning.

### 7.4. Running the Server

```bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell / CMD
mvnw.cmd spring-boot:run
```

By default the app listens on `http://localhost:8080` unless `server.port` or context path is changed.

### 7.5. Step 1: GET and Record the ETag

```bash
curl -i http://localhost:8080/api/docs/1
```

Key parts:

```http
HTTP/1.1 200
ETag: "rev-1"
Cache-Control: no-store
Content-Type: application/json

{"id":"1","content":"Ban dau","revision":1}
```

Other headers (`Date`, `Connection`, `Transfer-Encoding`/`Content-Length`) and JSON field ordering depend on container/converter, so do not compare the entire raw response verbatim.

### 7.6. Step 2: Alice PUTs with Current Revision

```bash
curl -i -X PUT http://localhost:8080/api/docs/1 \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "rev-1"' \
  -d '{"content":"Alice edit"}'
```

Expected status **200 OK**, new ETag `"rev-2"`, body:

```json
{"id":"1","content":"Alice edit","revision":2}
```

### 7.7. Step 3: Bob Sends the Old Tag

```bash
curl -i -X PUT http://localhost:8080/api/docs/1 \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "rev-1"' \
  -d '{"content":"Bob stale edit"}'
```

Expected status **412 Precondition Failed**; no update occurs. Re-GET:

```bash
curl -sS http://localhost:8080/api/docs/1
```

The body remains:

```json
{"id":"1","content":"Alice edit","revision":2}
```

This demonstrates lost-update protection. An API may attach the current ETag or an error DTO on `412` depending on contract and permissions; never automatically return full document contents if the caller lacks read access.

### 7.8. Step 4: Bob Resends with the New ETag

```bash
curl -i -X PUT http://localhost:8080/api/docs/1 \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "rev-2"' \
  -d '{"content":"Bob accepted after review"}'
```

Expect **200**, ETag `"rev-3"`, and revision 3. This assumes Bob **reviewed and accepted** the newer content; if a client auto-retries without letting the user inspect the conflict, it can overwrite earlier changes.

### 7.9. Step 5: Omitting If-Match

```bash
curl -i -X PUT http://localhost:8080/api/docs/1 \
  -H 'Content-Type: application/json' \
  -d '{"content":"Unsafe update without validator"}'
```

Expect **428 Precondition Required**. On `428`, the response should guide the client to GET and supply the ETag. RFC 6585 mandates that `428` responses **must not be cached**.

### 7.10. Step 6: Weak ETag Invalid for If-Match

```bash
curl -i -X PUT http://localhost:8080/api/docs/1 \
  -H 'Content-Type: application/json' \
  -H 'If-Match: W/"rev-3"' \
  -d '{"content":"Weak validator"}'
```

Expect **412**, because `If-Match` requires strong comparison and current `"rev-3"` does not match `W/"rev-3"`.

### 7.11. Step 7: Wildcard and Overwrite Risk

```bash
curl -i -X PUT http://localhost:8080/api/docs/1 \
  -H 'Content-Type: application/json' \
  -H 'If-Match: *' \
  -d '{"content":"Wildcard overwrites current value"}'
```

The document exists, so the demo returns **200** and increments revision to 4. **Do not use this** when UX demands preventing stale edits: `*` carries no revision info. App policy can require a concrete tag like `"rev-3"`.

### 7.12. Windows PowerShell

PowerShell often aliases `curl`; use `curl.exe` on a single line:

```powershell
curl.exe -i -X PUT "http://localhost:8080/api/docs/1" -H "Content-Type: application/json" -H 'If-Match: "rev-1"' --data-raw '{"content":"Alice edit"}'
```

**Note:** passing JSON quotes to `curl.exe` on Windows differs from Bash depending on PowerShell version and native-argument quoting. If a request gets `400` from malformed JSON, use a `payload.json` file with `--data-binary "@payload.json"`, or use `Invoke-RestMethod` with `ConvertTo-Json`. Never mistake a shell quoting error for an `If-Match` bug.

## 8. Testing Spring MVC with MockMvc

Add test dependency `spring-boot-starter-test` (`test` scope) and create `src/test/java/com/example/demo/ConditionalUpdateTest.java`.

### 8.1. Integration Test

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ConditionalUpdateTest {

    @Autowired
    MockMvc mvc;

    @Test
    void staleIfMatchMustNotOverwriteSuccessfulUpdate()
            throws Exception {

        String initial = mvc.perform(get("/api/docs/1"))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"rev-1\""))
                .andReturn()
                .getResponse()
                .getHeader("ETag");

        mvc.perform(put("/api/docs/1")
                        .contentType("application/json")
                        .header("If-Match", initial)
                        .content("{\"content\":\"Alice edit\"}"))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"rev-2\""))
                .andExpect(jsonPath("$.revision").value(2));

        mvc.perform(put("/api/docs/1")
                        .contentType("application/json")
                        .header("If-Match", initial)
                        .content("{\"content\":\"Bob stale edit\"}"))
                .andExpect(status().isPreconditionFailed());

        mvc.perform(get("/api/docs/1"))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"rev-2\""))
                .andExpect(jsonPath("$.content").value("Alice edit"));
    }
}
```

Each test run in a **fresh context** starts with `revision=1`. If a test suite reuses the application context and other tests mutate the shared `DocumentStore`, tests hardcoding revisions can become flaky. Better practice is resetting state via fixtures/test-specific config, or reading the current tag and asserting relative revision increments. The test above shows a readable approach meant to run isolated from other state-mutating tests.

### 8.2. Additional Tests for Missing/Weak/Wildcard

Cases to assert:
- PUT without header => `428`.
- PUT with weak ETag => `412`.
- PUT with a list containing the strong current tag => succeeds.
- PUT with `*` on an existing resource => succeeds, yet **does not prevent lost updates**.
- PUT to a non-existent ID => `404` per contract.
- PUT with invalid payload => `400`, revision unchanged.
- Two concurrent PUTs with the same revision => **only one wins** and the other receives `412` in the synchronized demo.

### 8.3. Testing Service Concurrency Without HTTP

Here is a standalone test class illustrating two threads using the same ETag:

```java
package com.example.demo;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DocumentStoreConcurrencyTest {

    @Test
    void onlyOneUpdateForSameVersionWins() throws Exception {
        DocumentStore store = new DocumentStore();
        String initial = store.get("1").strongETag();

        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger success = new AtomicInteger();
        AtomicInteger failed = new AtomicInteger();

        Runnable action = () -> {
            try {
                start.await();
                store.replace(
                        "1", List.of(initial),
                        new ReplaceDocument(Thread.currentThread().getName()));
                success.incrementAndGet();
            } catch (ResponseStatusException ex) {
                failed.incrementAndGet();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(action, "Alice");
        Thread b = new Thread(action, "Bob");
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        assertEquals(1, success.get());
        assertEquals(1, failed.get());
        assertEquals(2, store.get("1").revision());
    }
}
```

This test proves atomic compare-and-update inside **one `DocumentStore`/JVM**. It does not prove safety across multiple application replicas, database transactions, or distributed caches.

## 9. Common Pitfalls When Implementing If-Match

### 9.1. Checking ETag in the Controller Then Calling repository.save

```java
// ANTI-PATTERN
Document d = repository.findById(id).orElseThrow();
if (d.etag().equals(ifMatch)) {
    d.setContent(newContent);
    repository.save(d);
}
```

Between `findById` and `save` lies a race window. Ordinary transactions do not prevent lost updates by default if isolation/locking allows concurrent reads before writes; you need **version CAS** or DB-backed optimistic locking.

### 9.2. Using If-None-Match on PUT to Prevent Lost Updates

`If-None-Match` checks for **non-matching** tags; it does not mean "write only if I hold the exact current revision." For updates against a known state, `If-Match` is the proper tool.

### 9.3. Comparing Tags with contains or Inconsistent Quote Stripping

```java
// ANTI-PATTERN: does not handle list/weak/wildcard syntax.
if (header.contains(currentETag)) {
    update();
}
```

For example, `W/"rev-5"` contains the substring `"rev-5"` yet is **not** a strong match. Parse according to HTTP syntax and compare with exact semantics; use `HttpHeaders#getIfMatch()` or framework utilities where appropriate.

### 9.4. Accepting Wildcards While Assuming Lost Updates Are Solved

`If-Match: *` only guarantees existence. If an API allows wildcard updates, clients without a revision can still overwrite changes. Require a concrete strong tag whenever optimistic concurrency is mandatory.

### 9.5. Using Low-Resolution Timestamps

`Last-Modified` usually has one-second granularity; rapid back-to-back updates can share a timestamp. When combining `ETag` and `Last-Modified`, the precedence rules are `If-Match` before `If-Unmodified-Since`, and `If-None-Match` before `If-Modified-Since`. Never assume a record is unchanged solely because rounded timestamps match.

### 9.6. Tags Resetting After Restart or Deploy

If a backend restart resets revisions back to 1 while persistent data differs, a strong ETag `"rev-1"` can be improperly reused. Use durable database versions or fresh opaque tokens on representation changes; across multiple nodes, tag generation must be consistent. The in-memory demo in section 7 does **not** satisfy production persistence requirements.

### 9.7. Partial Updates Bumping Versions Incorrectly

With `PATCH`, if modifying a field alters the representation, the revision must increment. If JPA bulk updates bypass optimistic versioning by default or background jobs mutate data without bumping the version, stale tags can still be accepted. Every writer must participate in the same versioning contract.

### 9.8. Disclosing the New Body to Unauthorized Callers

When returning `412`, the server is not required to send the full current representation. Only disclose the current version/body if the caller has read permission. Return `404`/`403` for sensitive resources per policy instead of letting ETags reveal existence.

## 10. Database: Atomic Compare-and-Swap and Optimistic Locking

Across multiple instances, a **shared atomic data source** must arbitrate writes.

### 10.1. Direct SQL CAS

Suppose we have a table:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    version BIGINT NOT NULL
);
```

Once the client is authenticated and the server verifies permissions and `If-Match: "rev-12"`, execute a conditional update:

```sql
UPDATE documents
SET content = :new_content,
    version = version + 1
WHERE id = :id
  AND owner_id = :authenticated_owner_id
  AND version = :expected_version;
```

Outcome:
- **1 row affected:** the operation won CAS; version incremented.
- **0 rows affected:** no matching row—due to a stale version, missing resource, or lack of permission. Distinguish `404`/`403`/`412` per policy **without leaking permissions**.
- **More than 1 row affected:** impossible if `id` is primary key and criteria are right; indicates data/schema corruption.

A version-conditioned `UPDATE` is executed atomically by the DB under its transaction semantics. Two writers both expecting version 12 cannot both update the row to version 13. To return the updated representation, re-read the row or use `RETURNING` where supported, keeping transaction and response contracts consistent.

**Never take `expected_version` straight from a body `{"version":...}` while ignoring `If-Match` if the API contract mandates HTTP preconditions.** If an API uses an alternative body-version field, document that contract explicitly. Here the client sends a strong ETag, and the server parses/validates it to derive the expected version.

### 10.2. Spring Data JPA @Version

JPA supports optimistic locking:

```java
@Entity
class DocumentEntity {

    @Id
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false)
    private String content;

    // constructors/getters/setters...
}
```

This is an entity snippet lacking imports/constructors, not a standalone runnable file. `@Version` lets the persistence provider detect concurrent writes on managed entities. If a stale transaction attempts to flush/commit, it throws `OptimisticLockException` or Spring's translated `ObjectOptimisticLockingFailureException` (or equivalent).

Notes:
- Use clear transaction boundaries; never return **200 before flush/commit succeeds**.
- Even if you checked `If-Match` in the service before modifying the entity, still handle **version conflicts occurring after the check**.
- Bulk JPQL/SQL updates can bypass automatic version checks/increments unless written carefully; audit all write paths.
- When operations span multiple tables/aggregates, transactions and concurrency models must protect all business invariants.
- Optimistic lock exceptions thrown at flush/commit may need mapping to `412` when tied to HTTP preconditions, though do not blindly map every `DataAccessException` to `412`. Other data errors might be `409`/`500` depending on cause.
- A transaction rolled back due to an optimistic conflict must not reuse the same `EntityManager` to retry updates inside that failed transaction.

### 10.3. Does Pessimistic Locking Replace If-Match?

A pessimistic lock (such as `SELECT FOR UPDATE`) serializes DB writers, yet **has no knowledge of which revision the client originally read**. If Bob viewed revision 1, locking only at save time blocks simultaneous writes, yet still lets Bob overwrite revision 2 after Alice commits.

You must verify the **client's expected revision** inside the critical section/transaction or via optimistic versioning, not merely lock.

### 10.4. Multi-Resource Updates and Transactions

If a PUT updates a document while also updating a balance/quota or audit log, a single CAS on the document row alone cannot protect all invariants. Use database transactions, the outbox pattern when event publishing must stay consistent, idempotency keys for retries if needed, and clear conflict handling.

`ETag`/`If-Match` primarily protects the **representation/version of the target resource**; it does not provide distributed transactions across multiple services by itself.

## 11. HTTP Preconditions and Caching

### 11.1. GET with If-None-Match

The client has cached representation `"rev-5"`:

```http
GET /api/docs/1
If-None-Match: "rev-5"
```

If the server still considers the representation equivalent under `If-None-Match` weak comparison rules, it can return:

```http
HTTP/1.1 304 Not Modified
ETag: "rev-5"
```

A `304` response carries no body per semantics. This saves bandwidth for cache revalidation, yet **is not a PUT** and provides no write concurrency control.

### 11.2. PUT with If-Match

```http
PUT /api/docs/1
If-Match: "rev-5"
```

The server requires the current selected representation to strong-match the tag. If version is already 6, return `412` without writing. `If-Match` is commonly used on PUT/PATCH/DELETE; it also carries semantics on other HTTP methods where RFC allows.

### 11.3. Cache-Control and Privacy

Having an `ETag` **does not mean** browsers/proxies are allowed to cache everything. For user/tenant-scoped resources, configure:
- `Cache-Control: private` or `no-store` per policy.
- `Vary` for variants depending on request headers if HTTP caching is used.
- Authorization and cache-key isolation to avoid cross-user representation sharing.

When using `no-store` as in the demo, clients can still keep the ETag in application state for optimistic concurrency, while shared HTTP caches are barred from storing responses normally.

### 11.4. Strong vs. Weak ETags with gzip and Variants

If one URL returns different bytes by encoding, language, negotiated media type, or permission projection:
- Strong tags must not equate genuinely distinct representation bytes in violation of the RFC.
- Weak tags often fit cache equivalence, yet cannot match `If-Match`.
- Domain entity update versions and HTTP representation ETags are related concepts, though not always identical. If you need one stable revision token across client representation variants, design an explicit API contract or issue controlled per-representation strong tags that map consistently back to an expected domain version.

## 12. Security and Operations

### 12.1. Authorization Always Precedes Updates

Never write:

```java
// ANTI-PATTERN: matching tag does not prove ownership.
if (ifMatch.equals(doc.etag())) {
    save(doc);
}
```

Always check principal/tenant/ACL and capabilities on the target resource. ETags can be guessable (especially `rev-1`), so never treat validators as secrets or bearer tokens.

### 12.2. CSRF Is Not Solved by If-Match

If the app uses session cookies and accepts PUT/PATCH/DELETE from browsers, implement CSRF protection alongside appropriate `SameSite`/session policies. `If-Match` does not prove a request was intentionally initiated by the user; it only shows the caller supplied a validator, which can be leaked or guessed.

### 12.3. DoS and Header Sizes

A client can send a huge `If-Match` list. Servlet containers and reverse proxies must bound request header sizes, header counts, total request body sizes, and rate limits. Never write catastrophically backtracking regex parsers or buffer unbounded millions of ETags.

### 12.4. CORS and Conditional Requests

When a browser calls a cross-origin API, `If-Match` is not a CORS-safelisted request header. The app/gateway must allow it when valid (e.g., via allowed headers) and expose the `ETag` response header to JavaScript via `Access-Control-Expose-Headers: ETag` if needed. This is **CORS policy**, not a substitute for authentication or CSRF protection.

### 12.5. Retries and Idempotency

PUT is theoretically **idempotent** in intended effect when repeated under matching context, yet with `If-Match`:
- The first PUT with `"rev-1"` succeeds, advancing the tag to `"rev-2"`.
- An identical retry with `"rev-1"` may receive `412` because the precondition now fails.
- That does not mean PUT ran twice; the first request may have succeeded while the client lost the response.

RFC 9110 includes an exception allowing servers to return success when they can prove the prior state-changing request already took effect. In real APIs, use a request ID / idempotency key with stored outcomes to distinguish timeout retries from another user's stale edit. Never "fix" `412` by removing the ETag check.

### 12.6. Monitoring

Log safely:
- request method, path template, and resource ID (sanitized of sensitive data);
- controlled principal/tenant identifier;
- expected revision/token as safe metadata;
- current revision, `412`/`428` status, and concurrency conflict rates;
- DB transaction/CAS latency and affected row counts.

Never log raw `Authorization`, cookies, sensitive document contents, or full request/response bodies by default. Sudden spikes in `412`s may point to high-contention UX issues or broken client retries.

## 13. Troubleshooting: Common Errors

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Bob overwrites Alice despite `If-Match` | Check and write are not atomic | Use DB version CAS / `@Version` in a transaction |
| Every PUT returns `412` | Client ETag lacks quotes or representation tag differs | Inspect actual GET `ETag`; send exact strong tag |
| Weak tag `W/"x"` fails to match `"x"` | Expected strong `If-Match` semantics | Use a strong ETag for concurrency |
| PUT without `If-Match` still succeeds | API does not require preconditions | Enforce `428` or matching contract |
| `If-Match: *` still overwrites | Wildcard only checks existence | Require concrete strong ETag for lost-update protection |
| Client treats `412` as data corruption | Normal stale version | Re-GET latest and show diff/conflict/merge workflow |
| `304` appears on GET | Conditional cache revalidation | Distinguish GET `If-None-Match` from PUT `If-Match` |
| `428` gets cached | Cache/proxy violates spec | Emit `Cache-Control: no-store` on `428` responses |
| Conflicts when scaling to multiple pods | Lock lives only inside one JVM | Move CAS/optimistic locking to shared DB |
| JPA optimistic conflict turns into `500` | Exception not mapped | Map concurrency conflicts properly at transaction boundary |
| Record changes while ETag stays the same | Another writer didn't bump version | Require every writer to update revision |
| ETag changes even though JSON format didn't | Pointless timestamp or unstable variant | Choose validator aligned with representation semantics |
| Cross-origin client cannot read `ETag` | Header not exposed in CORS | Expose `ETag` on responses for allowed origins |
| Version token treated as authorization | Missing authorization check | Enforce ACLs on every request |
| Client auto-retried after `412` loses data | Resent old body with new tag unreviewed | Prompt user to merge or confirm |
| HTTP `412` and `409` used inconsistently | Mixing precondition vs. domain conflicts | Use `412` for failed preconditions, `409` for domain conflicts |

### 13.1. Debugging Checklist

1. Which strong ETag does GET currently return for that authenticated user and representation variant?
2. Which **exact header** did PUT/PATCH/DELETE send? Were `"` quotes preserved?
3. Does the header contain weak `W/`, multiple tags, or `*`?
4. Does a missing header return `428` per contract?
5. Does the ETag comparison happen atomically with the DB write?
6. Are background jobs, bulk updates, import scripts, or other nodes mutating data without bumping the version?
7. Are transaction rollback/flush exceptions mapped distinctly to `412` when appropriate?
8. After a conflict, does the client re-GET and display newer changes?
9. Does CORS allow `If-Match` and expose `ETag`?
10. Have concurrent requests, stale tokens, wildcards, `404`, `401`/`403`, timeouts/retries, and multi-instance deployments been tested?

## 14. Knowledge Self-Check

**Q1.** Two users GET revision 3. Alice PUTs with `If-Match: "rev-3"`, succeeding and creating revision 4. What should Bob receive when PUTting with `"rev-3"`?

**Answer:** `412 Precondition Failed`, and no overwrite occurs.

**Q2.** What should a PUT without `If-Match` return in an API that mandates preconditions?

**Answer:** `428 Precondition Required` is the dedicated status, with a response guiding the client to GET the ETag first.

**Q3.** Does `If-Match: W/"rev-3"` match `ETag: "rev-3"`?

**Answer:** No. `If-Match` uses **strong comparison**; a weak tag cannot strong-match.

**Q4.** Does `If-Match: *` prevent lost updates?

**Answer:** No. It only requires that the target resource exists, carrying no specific revision.

**Q5.** Is `@Synchronized` or `synchronized` on a JVM controller/service enough across multiple replicas?

**Answer:** No. A JVM lock protects only one instance; multiple replicas require shared database atomic CAS / optimistic locking.

**Q6.** What status does GET with a matching `If-None-Match` tag typically return?

**Answer:** `304 Not Modified` for eligible conditional GET/HEAD, not the `412` of a stale PUT.

**Q7.** A JPA entity has `@Version`, yet a bulk SQL job updates content without bumping the version. What is the risk?

**Answer:** Stale ETags can still be accepted even though the representation changed; every writer must honor the same version contract.

**Q8.** Auth is valid, yet the user lacks permission to edit the document; the user sends the exact current ETag. Should the update be allowed?

**Answer:** No. `If-Match` is a validator, **not** permission; authorization is a separate requirement.

**Q9.** Should a client automatically GET the new tag and retry the old body after a `412`?

**Answer:** Not by default. Doing so can wipe out another user's edits; UX should compare, merge, or ask confirmation.

## 15. Official Documentation

- [RFC 9110 — HTTP Semantics, §13.1.1 If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1): `If-Match`, strong comparison, wildcard, and failed precondition handling.
- [RFC 9110 — §13.2 Evaluating Preconditions](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.2): ordering of `If-Match`, `If-Unmodified-Since`, `If-None-Match`, and `If-Modified-Since`.
- [RFC 9110 — §8.8.3 Entity Tags](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.8.3): `ETag`, strong/weak validators, representation semantics.
- [RFC 6585 — §3 428 Precondition Required](https://www.rfc-editor.org/rfc/rfc6585.html#section-3): requiring conditional requests to prevent lost updates.
- [Spring Framework 6.2 — HttpHeaders Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/http/HttpHeaders.html): `getIfMatch()`, `setIfMatch()`, and ETag header methods.
- [Spring Framework 6.2 — ServletWebRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/web/context/request/ServletWebRequest.html): `checkNotModified()` for conditional GET and state-changing requests.
- [Spring Framework — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): HTTP caching and validators in Spring MVC.
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): response status, headers, and body.
- [Jakarta Persistence — Version](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/version): optimistic versioning in entity persistence.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): authentication, authorization, and HTTP API safety.

**Conclusion:** A safe client workflow is **GET → keep strong ETag → PUT/PATCH/DELETE with If-Match**. The server requires preconditions when appropriate (`428`), rejects stale validators (`412`), and executes **atomic compare-and-update** while incrementing the version under an appropriate transaction/lock; without atomicity, lost updates still happen. To protect every edit, never treat `If-Match: *` as a version check. ETags never replace ACLs, validation, CSRF protection, cache policies, or UI conflict-resolution workflows.
