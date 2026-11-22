# Cache-Control, ETag, Last-Modified, and Conditional HTTP Requests

## 1. Problem and Objectives

Suppose a browser fetches a document over HTTP:

~~~http
GET /articles/42 HTTP/1.1
Host: example.test
~~~

The server returns `200 OK` with a 50 KiB body. The user reopens the URL after a few seconds. Is it necessary to download the entire 50 KiB again? No. An **HTTP cache** can store the previous response, decide whether **it is still fresh** or **has become stale**, and if stale, **revalidate** it with the origin using a **conditional** request. If the content has not changed, the origin can return **`304 Not Modified` without a representation body**, allowing the client to reuse the stored copy.

Three groups of headers play different roles:

- **`Cache-Control`:** describes the **caching policy** — where a response can be stored, how long it can be reused, and when revalidation is required.
- **`ETag`:** an opaque-token **validator** issued by the server to identify a version of the **selected representation**; the client sends it back via `If-None-Match` or `If-Match`.
- **`Last-Modified`:** the timestamp when the server believes the representation was last modified; the client can send it back via `If-Modified-Since` or use it for certain other conditions.

**Conditional requests** are not only for saving bandwidth: `If-Match` and `If-Unmodified-Since` can protect update operations against **lost updates**. However, cache freshness, validation, and write preconditions are **three related yet distinct concerns**.

After this lesson, you should be able to explain the `200 → cache → 304` flow, distinguish `no-cache` from `no-store`, strong vs. weak ETags, `Last-Modified` precision, conditional header precedence, `Vary` usage, `200/304/412` status codes, and write a Java 17+ HTTP server/client example reproducing those cases.

## 2. Terminology: Cache, Representation, Freshness, and Validation

### 2.1. A Resource Is Not Synonymous with a Single Byte Sequence

A **resource** is a concept identified by a URI, for example `/articles/42`. A **representation** is the content selected to be returned at a specific time, consisting of metadata and representation data. The same resource can have multiple representations:

- `Accept-Encoding: gzip` versus `identity`.
- `Accept-Language: vi` versus `en`.
- Content for different devices/formats, if the server actually performs content negotiation.

Therefore, an ETag is usually tied to the **selected representation**, not an immutable business ID across all variants. If content-coding bytes change, the **strong ETag** of two representations should not be used as if they were the same byte sequence.

### 2.2. Three Typical Caching Locations

~~~text
Client / browser
       |
       | (1) local/browser/private cache?
       v
Shared cache / reverse proxy / CDN
       |
       | (2) fresh copy available? revalidation needed?
       v
Origin server
       |
       v
Selected representation + caching metadata
~~~

- **Private cache:** typically tied to a single user, such as a browser cache.
- **Shared cache:** can serve multiple users, such as a CDN or reverse proxy. Because it is shared, it has stricter restrictions regarding personal data and responses with `Authorization`.
- **Origin:** the source that provides the representation or determines the validator for the resource.

A cache can store **metadata** and the representation body. A “cache hit” can be a **fresh hit** (without calling the origin) or a **revalidated hit** (sending a conditional request, receiving 304, and reusing the old body). They are not the same in terms of latency or bandwidth.

### 2.3. Fresh Is Different from Valid

- **Freshness:** whether a cache is allowed to **reuse a response without contacting the origin**, based on metadata and the current time.
- **Validation:** the cache/client asks the origin whether the **stored version is still suitable**, using a validator.
- **Invalidation:** prevents a cache from arbitrarily continuing to serve an old entry, for example due to an unsafe method or a purge; it does not mean the origin immediately changed its content.

A response with an `ETag` but **no `Cache-Control`** still has a validator; however, `ETag` **does not set a TTL by itself**. Conversely, a response with `Cache-Control: max-age=600` can be fresh for 10 minutes **without an ETag**, but when it becomes stale, it will be hard to verify cheaply without a validator.

## 3. Lifecycle of a Cached Entry

Suppose the origin returns:

~~~http
HTTP/1.1 200 OK
Date: Wed, 10 Jan 2024 00:00:00 GMT
Cache-Control: public, max-age=600
ETag: "article-42-v7"
Last-Modified: Wed, 10 Jan 2024 00:00:00 GMT
Content-Type: text/plain; charset=utf-8
Content-Length: 12

Hello world!
~~~

`Content-Length` and the body are just an independent example. The cache is allowed to store the response if other HTTP caching conditions are met. While within the **freshness lifetime** of 600 seconds, the cache can serve the stored body without calling the origin. Once stale, the cache can send:

~~~http
GET /articles/42 HTTP/1.1
Host: example.test
If-None-Match: "article-42-v7"
~~~

If the selected representation is still suitable:

~~~http
HTTP/1.1 304 Not Modified
Date: Wed, 10 Jan 2024 00:10:02 GMT
Cache-Control: public, max-age=600
ETag: "article-42-v7"
Last-Modified: Wed, 10 Jan 2024 00:00:00 GMT
~~~

The server **does not resend the representation body**. The cache receives 304 and **updates the metadata of the matching stored response**, and can then return the cached 200/body for the client to use. `304` must never be treated as “an empty article”.

If the origin has changed the representation, it returns `200 OK` with the **new body**, a new ETag, and new metadata. Only the server/application knows the content has changed; the client must not treat `304` as a new complete 200 response on its own.

### 3.1. Freshness Expiration Does Not Mean the Data Definitely Changed

`max-age=600` specifies **how long it can be served without verification**, not “the server changes content every 600 seconds”. A stale entry may still be byte-for-byte identical; having the cache revalidate and receive 304 is completely normal. Conversely, a **fresh** entry may already be outdated relative to an immediate update at the origin: freshness is a policy accepting a bounded staleness window, not instant synchronization.

## 4. Cache-Control: One Header, Many Different Policies

`Cache-Control` can appear in both **responses** and **requests**, with related but distinct meanings. Directives are comma-separated, for example `Cache-Control: private, max-age=0, must-revalidate`.

### 4.1. Common Response Directives

| Directive | Primary Meaning | Notes |
| --- | --- | --- |
| `max-age=600` | Response can be fresh for up to 600 seconds according to cache age calculation | Not a guarantee that the resource has not changed |
| `s-maxage=60` | Sets the freshness lifetime for **shared caches** | Can override `max-age` for shared caches |
| `public` | Marks the response as eligible to be stored in a **shared cache** under the corresponding conditions | Does not solve data exposure on its own; content must be controlled |
| `private` | **Shared caches must not store** responses marked private | Private/browser caches may store it unless otherwise prohibited |
| `no-cache` | Cache may store it, but **must validate** before reuse (subject to field-name semantics exceptions) | **Not synonymous with forbidding storage** |
| `no-store` | Cache must not intentionally store the request/response under this policy | Does not guarantee deleting previously stored entries or all OS/log copies |
| `must-revalidate` | Once stale, the cache **must not serve it** without successful revalidation per HTTP rules | Useful alongside a TTL for data requiring strict freshness |
| `proxy-revalidate` | Similar requirement to `must-revalidate` for shared caches | Less common than `must-revalidate` |
| `immutable` | During the freshness lifetime, the representation is declared unchanging; compliant clients may skip routine revalidation | Works well for versioned/hashed asset URLs |
| `stale-while-revalidate=30` | May allow serving stale for a limited time while revalidating in the background, if supported by the cache | Depends on the cache and other policies |
| `stale-if-error=120` | Allows serving stale for a limited window when encountering an error, if policy permits | Does not replace proper error recovery |
| `no-transform` | Instructs intermediaries not to alter representation data unlawfully per the corresponding rules | Not a freshness policy |

`Expires` is an HTTP-date header setting an absolute freshness timestamp in certain cases. When an appropriate `Cache-Control: max-age` is present, it takes precedence over `Expires` under HTTP caching rules. For shared caches, `s-maxage` can take precedence over `max-age`.

Some caches may infer **heuristic freshness** when a response is cacheable without an explicit freshness lifetime. Therefore, **never assume omitting Cache-Control guarantees no caching**. If you need to prevent caching of sensitive data, declare the policy explicitly.

### 4.2. `no-cache` IS DIFFERENT FROM `no-store`

Two responses:

~~~http
Cache-Control: no-cache
ETag: "v12"
~~~

and:

~~~http
Cache-Control: no-store
~~~

differ significantly:

- With **`no-cache`**, the cache **can keep the body**. Before reusing it, it must verify with the origin; if it receives `304`, it can still serve the old body with updated metadata.
- With **`no-store`**, the cache **must not intentionally store** the response per policy. Since there is no stored copy to reuse, there is typically no “304 + reuse cached body” benefit from this response.

“`Cache-Control: no-cache`” sounds like “do not cache”, but in the protocol it means **do not reuse without validation**. This misconception easily causes wasted bandwidth and confusion when debugging browsers.

### 4.3. `max-age=0` Differs Technically from `no-cache`

`Cache-Control: max-age=0` defines a **freshness lifetime of 0**, making the response immediately stale under normal age calculation. It **does not forbid storage**. When needed again, the cache may have to validate or apply stale-reuse rules if permitted. `no-cache` explicitly requires validation before reuse, independent of freshness time alone.

When you want “store it, but verify on every use”, a policy like:

~~~http
Cache-Control: private, no-cache
ETag: "profile-42-v8"
~~~

is a reasonable example for content intended only for a private cache. For a document requiring strict stale behavior, you can also use:

~~~http
Cache-Control: private, max-age=0, must-revalidate
ETag: "doc-v7"
~~~

The two policies may produce similar behavior on typical caches, but **that does not mean every directive edge case is identical**.

### 4.4. `public`, `private`, and Personal Data

For example:

~~~http
Cache-Control: public, max-age=86400
~~~

is appropriate for public resources **only when** the server genuinely wants shared caches to store and serve them to multiple users. For a JSON response containing user-specific data, you can use:

~~~http
Cache-Control: private, no-store
~~~

to reduce the risk of caches storing/replaying it; system policies and risks must be evaluated. **Do not rely on `Vary: Cookie` or per-user ETags as a primary security layer** for private data. Authorization, cache keys, headers, and returned data must still be properly controlled; `Set-Cookie`/`Authorization` is not a guaranteed mechanism for “safety from all shared caches” in every configuration.

### 4.5. `immutable` Fits Content-Hashed URLs

Example of a JS asset named by content hash:

~~~http
GET /assets/app.4a81d1.js HTTP/1.1
Host: example.test

HTTP/1.1 200 OK
Cache-Control: public, max-age=31536000, immutable
ETag: "hash-4a81d1"
~~~

When the content changes, publish a **new URL** (new hash); do not overwrite bytes at an old URL already published as immutable. If you reuse an old URL for new content, clients may continue seeing the old version for the entire freshness lifetime, even after the server has updated.

## 5. Request Cache-Control: Clients Can Request Different Serving Behavior

Request directives are signals **from the client to caches/intermediaries**, not all of which are commands to the origin to “bypass all caches”. For example:

~~~http
GET /articles/42 HTTP/1.1
Host: example.test
Cache-Control: no-cache
~~~

asks the cache **not to use** a stored response to satisfy the request without first verifying with the origin. The client/cache may send a corresponding `If-None-Match` if it has a stored copy and validator.

Some request directives:

| Request Directive | Meaning |
| --- | --- |
| `no-cache` | Asks the cache not to use a stored response to satisfy the request without successful validation |
| `no-store` | Asks the cache not to intentionally store the associated request/response; does not automatically delete existing entries |
| `max-age=0` | Client accepts at most 0 seconds of age under the request freshness constraint |
| `max-stale[=N]` | Client can accept a stale entry within the corresponding limit when policy permits |
| `min-fresh=N` | Client wants a response that remains fresh for at least N seconds |
| `only-if-cached` | Asks the cache not to contact the origin to satisfy the request; may result in `504 Gateway Timeout` if no suitable stored response exists |

Do not rely on a browser’s “refresh” button behavior to make sweeping claims about the entire cache flow; different browsers and CDNs have different policies. To debug, inspect the **actual request/response headers**, status codes, `Age`, and hit/miss information of the specific cache.

## 6. Cache Age: Date, Age, and Freshness Lifetime

Cache freshness is not simply “download date + max-age”. A cache calculates the **current age** of a response from metadata and path timing, including `Date`, `Age`, response transit time, and time stored in the cache according to HTTP rules.

For example:

~~~http
HTTP/1.1 200 OK
Date: Wed, 10 Jan 2024 00:00:00 GMT
Cache-Control: public, max-age=600
Age: 90
~~~

If a response arrives already carrying `Age: 90`, a shared cache/client must not treat **the full 600 seconds** as having just started at the moment of receipt. The response already has age. After additional storage time, age increases; once current age exceeds freshness lifetime, it becomes stale and requires revalidation or applying an appropriate stale-reuse policy.

`Date` is typically when the origin generated the response, **not `Last-Modified`**. A document unchanged for a week can be sent right now with the current `Date`, while `Last-Modified` remains last week. Confusing the two headers breaks conditional GET logic.

`Last-Modified` **is not a TTL**. `ETag` **is not a TTL**. `Cache-Control` determines most of the freshness policy; `Age/Date` participate in age calculation when caches process responses.

## 7. ETag: Opaque, Strong, and Weak Validators

### 7.1. What Is an ETag?

`ETag` is an **entity tag** generated by the server for the selected representation. Examples:

~~~http
ETag: "v7"
ETag: "sha256-1b2c3d..."
ETag: W/"v7"
~~~

The syntax has **double quotes** around the opaque-tag. `W/` is the **weak validator prefix**, located **outside** the quotes. The server can generate tags from data versions, hashes, build IDs, or other reliable mechanisms; an **ETag does not have to be a hash**, and clients should not parse its internal meaning as a stable API.

The server must generate ETags with **semantics matching representation changes**. If bytes change while issuing the same **strong ETag**, conditional requests may produce wrong results or lost updates.

### 7.2. Strong ETag vs. Weak ETag

| Characteristic | Strong ETag | Weak ETag |
| --- | --- | --- |
| Example | `"abc"` | `W/"abc"` |
| Implication | Identifies a representation under strong comparison for the exact same representation data | Representations may be considered semantically equivalent, even if bytes differ |
| Comparison in `If-None-Match` | Uses **weak comparison** | Uses **weak comparison** |
| Comparison in `If-Match` | Uses **strong comparison** | Cannot satisfy a strong condition with a weak tag alone |
| Lost-update control | Can be used with `If-Match` | Not suitable as a replacement for a strong validator in `If-Match` |
| Range / If-Range | Can use a suitable strong validator | Weak entity-tags are not used for `If-Range` |

Example for If-None-Match (weak comparison):

~~~text
Current ETag:       "v7"
If-None-Match:      W/"v7"
Weak comparison:    MATCH
GET result:         304 if other preconditions match

Current ETag:       W/"v7"
If-Match:           "v7"
Strong comparison:  NO MATCH
On update:          412 Precondition Failed
~~~

**Subtlety:** “weak” does not mean “cryptographically weak hash”; it describes the **kind of equivalence allowed between representations**. Auth/trust and ETag are two separate issues. A predictable ETag can still be valid as a validator; never use an ETag as a secret token to prove access rights.

### 7.3. If-None-Match Conditions Can Contain Multiple Tags or `*`

~~~http
If-None-Match: "v5", "v6", W/"v7"
~~~

A client can send a **list** of validators. There is also the syntax:

~~~http
If-None-Match: *
~~~

The `*` represents the condition that the resource currently **has a representation** under HTTP semantics, rather than a normal opaque tag string. For GET/HEAD, if the `If-None-Match` condition **fails** (the selected representation matches a validator), the origin typically returns **`304`**. For other methods, failing the condition may return **`412 Precondition Failed`**, such as using `If-None-Match: *` to **create a resource only if it does not yet exist**.

**Be careful when writing a parser:** an opaque ETag can contain certain allowed characters inside quotes. Do not naively split `If-None-Match` with `String.split(",")` and claim RFC-compliant parsing. In production applications, use a standard HTTP parser or code that properly handles entity-tag formats, weak comparison, wildcards, and list syntax. The Java example in Section 12 intentionally supports only **a single exact strong tag** to teach the core flow.

### 7.4. ETag and Content Encoding

If a server returns similar content under two encodings:

~~~text
GET /data, Accept-Encoding: identity -> bytes A
GET /data, Accept-Encoding: gzip     -> bytes B
~~~

then if the bytes differ, do not use the **same strong ETag** as if they were the same representation byte sequence. A common approach is to generate distinct strong ETags per variant, or weak tags if semantics and policy permit. You must send `Vary: Accept-Encoding` so caches do not pick the wrong stored variant (see Section 10).

## 8. Last-Modified: Time-Based Validator

`Last-Modified` typically contains the timestamp when the resource/representation was last modified, formatted as an **HTTP-date**:

~~~http
Last-Modified: Wed, 10 Jan 2024 00:00:00 GMT
~~~

A client can send:

~~~http
GET /articles/42 HTTP/1.1
Host: example.test
If-Modified-Since: Wed, 10 Jan 2024 00:00:00 GMT
~~~

If the selected representation is **not newer** than the timestamp provided by the client and the request is eligible, the server can return `304 Not Modified`. If it changed after that timestamp, return `200 OK` with the new body.

### 8.1. Why Is Last-Modified Less Precise Than ETag?

HTTP-dates typically have **one-second resolution**. A resource updated **twice within the same second** may still carry the same `Last-Modified` if the server rounds timestamps, preventing a date-based validator from distinguishing the two versions. Clock skew or clock adjustments across multiple nodes also complicate results.

Example:

~~~text
10:00:00.100 -> content A
10:00:00.700 -> content B

Last-Modified for both could be:
Wed, 10 Jan 2024 10:00:00 GMT

=> If-Modified-Since may lack the precision to detect B.
=> ETag "v1" -> "v2" is clearer if the server updates the tag properly.
~~~

Therefore, use **ETag** whenever possible. `Last-Modified` remains useful as a fallback validator or for resources with stable modification metadata, but do not use it in place of proper concurrency control strategies.

### 8.2. Last-Modified May Be Absent or Inaccurate

A dynamically generated asset without a reliable modification timestamp **should probably not emit a fake Last-Modified**. If a server sets `Last-Modified = current time` on every response, clients will continuously see a new timestamp and struggle to revalidate effectively. Conversely, if the source changes without updating the timestamp, `304` may be returned erroneously.

With multiple cached variants by encoding/language, timestamps may change together, whereas ETag must consider the specific selected representation. Do not automatically use the response `Date` as `Last-Modified`.

### 8.3. Handling If-Modified-Since Properly

For GET/HEAD, the origin should evaluate `If-Modified-Since` **when no applicable If-None-Match is present**. A request with a malformed or invalid date must be handled per HTTP semantics—typically **ignoring the invalid condition** rather than crashing the parser. Future dates, time precision, and proxy caches are edge cases that should follow the RFC and real-world testing.

A server may still return `200` in situations where the condition does not apply; clients must handle both `200` and `304`, and must not treat `If-Modified-Since` as a guarantee of receiving 304.

## 9. Conditional Requests: If-None-Match, If-Modified-Since, If-Match

### 9.1. Revalidation for GET / HEAD

When the cache has an ETag:

~~~http
GET /articles/42 HTTP/1.1
If-None-Match: "article-42-v7"
~~~

The origin evaluates the current selected representation. If it matches under **weak comparison**, the appropriate response for GET/HEAD is **`304 Not Modified`**; if it does not match, the normal response is **`200 OK`** with the new body.

When the cache only has Last-Modified:

~~~http
GET /articles/42 HTTP/1.1
If-Modified-Since: Wed, 10 Jan 2024 00:00:00 GMT
~~~

If the representation has not changed relative to the accepted timestamp, the origin can return 304; if it has changed, 200.

### 9.2. Both ETag and Last-Modified Present: If-None-Match Takes Precedence

Clients/caches can send both:

~~~http
GET /articles/42 HTTP/1.1
If-None-Match: "old-etag"
If-Modified-Since: Wed, 10 Jan 2024 00:00:00 GMT
~~~

**According to HTTP precondition evaluation order, If-None-Match takes precedence over If-Modified-Since.** The origin must not see an “unchanged” date and return 304 when the new ETag **does not match** the ETag sent by the client. If `If-None-Match` does not match, the server processes the request and returns the new version subject to any other relevant conditions; `If-Modified-Since` must not override the ETag result.

Example:

~~~text
Origin ETag:              "v2"
Client If-None-Match:     "v1"       -> no match
Client If-Modified-Since: unchanged/coinciding timestamp due to resolution
GET result:               200 + new representation
                          not 304 just because the timestamp matches.
~~~

This is why using both validators **does not conflict**: ETag provides finer version precision, while the date serves as a secondary validator when a client lacks an ETag.

### 9.3. Preconditions for Data Modification: If-Match

A client reads a resource with ETag `"v7"`, then wants to update it while fearing another client may have modified it. It sends:

~~~http
PUT /articles/42 HTTP/1.1
Content-Type: application/json
If-Match: "v7"

{"title":"Updated"}
~~~

The server only allows the update when a **strong comparison** of the current representation’s ETag matches `If-Match`. If the resource has already changed to `"v8"`, it returns **`412 Precondition Failed`**, preventing overwriting someone else’s version.

This is **optimistic concurrency control**. You must perform the validator check and state update **atomically** at the storage layer; if checking the ETag and updating are separate and a race occurs, you can still suffer a lost update.

### 9.4. If-Unmodified-Since and If-None-Match: `*`

When no ETag is available, some systems support:

~~~http
PUT /articles/42 HTTP/1.1
If-Unmodified-Since: Wed, 10 Jan 2024 00:00:00 GMT
~~~

If the representation has been modified after that date, the condition fails and `412` can be returned. However, date validators are limited to **one-second precision**, so for heavily contended updates, **If-Match + strong ETag** is generally preferable.

A **create-if-absent** design pattern:

~~~http
PUT /objects/new-key HTTP/1.1
If-None-Match: *
~~~

This means creating the content **only if no current representation exists** under conditional semantics. If the resource already exists, write methods can return `412` instead of overwriting; the backend must enforce this condition atomically.

### 9.5. What If Multiple Preconditions Are Present?

HTTP defines an **evaluation order** for preconditions (such as `If-Match`, `If-Unmodified-Since`, `If-None-Match`, `If-Modified-Since`, and `If-Range` depending on the case). Do not combine all of them with a custom OR/AND check, as that will produce incorrect 200/304/412 results. In production, implement RFC 9110 **Section 13: Conditional Requests** in full, or use an HTTP framework that already implements the semantics correctly.

For a server handling only simple GETs, at minimum you must enforce **If-None-Match taking precedence over If-Modified-Since** and distinguish `304` from `200`.

## 10. Three Important Status Codes: 200, 304, and 412

| Status | When Used | Has Representation Body? |
| --- | --- | --- |
| `200 OK` | Unconditional GET, condition does not match validator, or a new copy must be sent | **Yes**, except in special cases like equivalent HEAD |
| `304 Not Modified` | Conditional GET/HEAD selected a representation and the condition permits omitting the content | **No message content** |
| `412 Precondition Failed` | Request precondition (e.g., `If-Match` on PUT) is not met | May have an error representation, but **the update is not applied** |

`304` **is not** `204 No Content`. `204` describes a successful response with no body in a different interaction pattern. `304` indicates that **clients/caches can refer to the stored representation** according to the validator and metadata; a client without a previously stored body cannot reconstruct the document from 304 alone.

### 10.1. Headers on 304

A `304` should carry the metadata needed to update the cached response, especially fields the origin would send in the corresponding `200`, such as:

~~~http
HTTP/1.1 304 Not Modified
Date: Wed, 10 Jan 2024 00:10:00 GMT
ETag: "v7"
Cache-Control: public, max-age=300
Vary: Accept-Encoding
Last-Modified: Wed, 10 Jan 2024 00:00:00 GMT
~~~

**Do not send a representation body for 304**, not even JSON `{}` or the text “Not Modified”. The browser or cache merges the 304 metadata with its stored entry and decides which representation to hand to the application. The Java demo code in Section 12 uses `sendResponseHeaders(304, -1)` so no response body is created.

Do not assume every header of the old `200` stays unchanged forever: a `304` response can update `Cache-Control` or corresponding metadata. Updating a stored response in a cache must follow RFC 9111 rules; do not merely extend TTL while ignoring new headers.

### 10.2. What If the Client Has No Cached Copy?

A client that sends `If-None-Match` on its own after losing the previous body may still receive 304. In that case, it **has no representation to reuse**. It must fetch a fresh copy via an unconditional GET or rebuild its cache state; do not interpret 304 as a valid empty payload.

## 11. Vary and Cache Keys: Same URL, Different Representations

A server can send:

~~~http
Vary: Accept-Encoding, Accept-Language
~~~

This header indicates that representation selection depends on the listed request headers. Shared/private caches must select the right stored response for requests with matching request header dimensions per the rules, rather than serving a Vietnamese copy to an English requester or mixing up gzip and identity.

Example:

| Request | Representation | ETag Note |
| --- | --- | --- |
| `Accept-Language: vi`, `Accept-Encoding: gzip` | Gzipped Vietnamese JSON | Strong ETag tied to this variant’s bytes |
| `Accept-Language: en`, `Accept-Encoding: gzip` | Gzipped English JSON | Should have a different strong ETag if bytes differ |
| `Accept-Language: vi`, `Accept-Encoding: identity` | Uncompressed Vietnamese JSON | Different strong ETag if bytes differ due to content-coding |

**Vary does not replace authorization.** A cache key “including User-ID” does not by itself prevent data leaks if a shared cache is misconfigured. For personalized responses, consider `private`/`no-store` and verify CDN policies.

`Vary: *` means selection depends on factors that cannot be reused from cache via normal matching. Do not use it as a substitute for a well-thought-out caching policy.

## 12. Complete Java 17+ Example: HTTP Server + HttpClient with ETag and Last-Modified

This example runs standalone on **IPv4 loopback 127.0.0.1**, requiring no Internet connection. The server uses the `jdk.httpserver` module (`com.sun.net.httpserver.HttpServer`) in the JDK, and the client uses `java.net.http.HttpClient`. The demo has **one resource** with immutable state holding the body, ETag, and Last-Modified. The client sends an unconditional request and three conditional requests, then the server updates the resource.

**Demo rules:**

- Only **GET** is supported, returning `405` for other methods.
- When `If-None-Match` is present, the demo **only accepts a single exact strong ETag** via string matching; it does not support lists, `W/`, or wildcards. This is an **intentional simplification**, not a full RFC 9110 implementation.
- If `If-None-Match` is absent, evaluate `If-Modified-Since` using IMF-fixdate and the resource’s modification timestamp.
- If the validator indicates the resource has not changed, return `304` **with no body**.
- If changed/not matching, return `200` with the body, `Cache-Control`, `ETag`, and `Last-Modified`.
- `Cache-Control: private, max-age=0, must-revalidate` indicates that caches may store privately but generally need to verify before reuse; the demo client **constructs conditional requests manually**.

Save the following code to **HttpCacheDemo.java**:

~~~java
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.concurrent.atomic.AtomicReference;

public class HttpCacheDemo {
    record Version(String body, String etag, Instant lastModified) {}

    static void serve(HttpExchange exchange,
                      AtomicReference<Version> state) throws IOException {
        try (exchange) {
            Version version = state.get();

            Headers headers = exchange.getResponseHeaders();
            String modified = DateTimeFormatter.RFC_1123_DATE_TIME.format(
                    version.lastModified().atZone(ZoneOffset.UTC));

            headers.set("Cache-Control",
                    "private, max-age=0, must-revalidate");
            headers.set("ETag", version.etag());
            headers.set("Last-Modified", modified);

            if (!"GET".equals(exchange.getRequestMethod())) {
                headers.set("Allow", "GET");
                exchange.sendResponseHeaders(405, -1);
                return;
            }

            String ifNoneMatch = exchange.getRequestHeaders()
                    .getFirst("If-None-Match");
            boolean notModified = false;

            if (ifNoneMatch != null) {
                // Demo ONLY: an exact single strong tag.
                // Production needs to parse lists, W/, and *.
                notModified = ifNoneMatch.equals(version.etag());
            } else {
                String ifModifiedSince = exchange.getRequestHeaders()
                        .getFirst("If-Modified-Since");

                if (ifModifiedSince != null) {
                    try {
                        Instant since = ZonedDateTime.parse(
                                ifModifiedSince,
                                DateTimeFormatter.RFC_1123_DATE_TIME)
                                .toInstant();
                        notModified =
                                !version.lastModified().isAfter(since);
                    } catch (DateTimeParseException ignored) {
                        // Demo ignores malformed HTTP-date.
                    }
                }
            }

            if (notModified) {
                // 304 has no representation body.
                exchange.sendResponseHeaders(304, -1);
                return;
            }

            byte[] bytes =
                    version.body().getBytes(StandardCharsets.UTF_8);
            headers.set("Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, bytes.length);

            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    static HttpResponse<String> get(
            HttpClient client, URI uri,
            String etag, String modified)
            throws IOException, InterruptedException {

        HttpRequest.Builder req = HttpRequest.newBuilder(uri).GET();
        if (etag != null) {
            req.header("If-None-Match", etag);
        }
        if (modified != null) {
            req.header("If-Modified-Since", modified);
        }
        return client.send(req.build(),
                HttpResponse.BodyHandlers.ofString());
    }

    public static void main(String[] args) throws Exception {
        AtomicReference<Version> state = new AtomicReference<>(
                new Version("version one", "\"v1\"",
                        Instant.parse("2024-01-10T00:00:00Z")));

        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/resource",
                exchange -> serve(exchange, state));
        server.start();

        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/resource");
            HttpClient client = HttpClient.newHttpClient();

            HttpResponse<String> first =
                    get(client, uri, null, null);
            String etag = first.headers()
                    .firstValue("ETag").orElseThrow();
            String lastModified = first.headers()
                    .firstValue("Last-Modified").orElseThrow();

            System.out.println(
                    "First: " + first.statusCode()
                    + " " + first.body());

            System.out.println(
                    "If-None-Match: "
                    + get(client, uri, etag, null).statusCode());

            System.out.println(
                    "If-Modified-Since: "
                    + get(client, uri, null, lastModified)
                            .statusCode());

            // ETag does not match => DO NOT use timestamp to return 304.
            System.out.println(
                    "Stale ETag overrides date: "
                    + get(client, uri, "\"stale\"", lastModified)
                            .statusCode());

            state.set(new Version("version two", "\"v2\"",
                    Instant.parse("2024-01-10T00:00:10Z")));

            HttpResponse<String> changed =
                    get(client, uri, etag, null);

            System.out.println(
                    "Changed: " + changed.statusCode()
                    + " " + changed.body());

            System.out.println(
                    "New ETag: " + get(client, uri,
                            changed.headers().firstValue("ETag")
                                    .orElseThrow(), null)
                            .statusCode());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 HttpCacheDemo.java
java HttpCacheDemo
~~~

Expected output verified on a JDK with `jdk.httpserver`:

~~~text
First: 200 version one
If-None-Match: 304
If-Modified-Since: 304
Stale ETag overrides date: 200
Changed: 200 version two
New ETag: 304
~~~

### 12.1. Why the Results Are Correct

1. The first request has **no validators**, so the origin returns `200` with body `version one`, ETag `"v1"`, and Last-Modified as an HTTP-date. The Java client stores them in local variables to test conditions.
2. The second request sends `If-None-Match: "v1"`; the tag matches, so the origin returns **304**, without resending the body.
3. The third request sends only `If-Modified-Since` equal to the exact Last-Modified timestamp, so the origin returns **304**.
4. The fourth request sends both `If-None-Match: "stale"` and a still-matching date; because **If-None-Match takes precedence**, the origin returns **200**, not 304 merely due to the timestamp.
5. The server updates the representation to `version two`, ETag `"v2"`, and a new timestamp. A request carrying the old ETag `"v1"` receives **200** and the new body.
6. The final request sends ETag `"v2"` and therefore receives **304**.

### 12.2. Intentional Limitations of the Demo

- The demo does not implement a **full HTTP cache**. Here `HttpClient` only sends requests; it **does not automatically manage stored response bodies, Age, TTL, Vary, or cache metadata**. Conditional headers are attached manually by the programmer.
- Only a single strong ETag is supported. Production needs **weak comparison for If-None-Match**, entity-tag lists, `*`, corresponding status codes, `If-Match`/`If-Range` handling if supported, and RFC 9110 precondition ordering.
- The demo only handles GET; production should implement **HEAD**, range requests if applicable, and write methods according to the full protocol model.
- The simple date parser uses `DateTimeFormatter.RFC_1123_DATE_TIME` and ignores malformed dates. Real HTTP has additional requirements for legacy date formats and clock behavior, which a standard HTTP framework should handle.
- Fixed state/`AtomicReference` only illustrates version changes. A production backend needs version/ETag consistency with transactions, atomic updates, and variant separation by `Vary`/encoding.
- The demo does not handle future `If-Modified-Since` dates, sub-second precision, CDN caching, or structured error responses.
- This is a **non-TLS** HTTP server on loopback strictly for learning semantics. For real deployments, use HTTPS, authentication, input validation, resource limits, and an appropriate framework.

**Key takeaway:** a short example can accurately teach **how to use headers and status codes**, but it cannot replace a full, RFC-tested HTTP conditional request implementation.

## 13. Testing with curl and Reading Response Headers

For a real server endpoint with an ETag:

~~~bash
curl -i https://example.test/articles/42
~~~

Suppose you receive:

~~~http
HTTP/1.1 200 OK
Cache-Control: private, max-age=0, must-revalidate
ETag: "v7"
Last-Modified: Wed, 10 Jan 2024 00:00:00 GMT
Content-Type: application/json

{"id":42}
~~~

Test If-None-Match:

~~~bash
curl -i -H 'If-None-Match: "v7"' https://example.test/articles/42
~~~

If unchanged, expect **304 without a body**. Test with an old ETag:

~~~bash
curl -i -H 'If-None-Match: "old"' https://example.test/articles/42
~~~

Normally expect **200** with the new version (barring other conditions/states).

Test Last-Modified:

~~~bash
curl -i -H 'If-Modified-Since: Wed, 10 Jan 2024 00:00:00 GMT' \
  https://example.test/articles/42
~~~

`example.test` and the responses are **illustrative**, not a running server. Single-quote syntax works well in POSIX-style shells; in Windows PowerShell, quoting rules vary by version and must be adjusted for the shell actually used.

### 13.1. How to Read Network Logs in the Browser

In DevTools Network, observe:

- Status `200` or `304`; some browsers may display responses `from disk cache`/`from memory cache`, meaning they may **not have called the origin** on that turn.
- **Request headers**: are `If-None-Match` or `If-Modified-Since` present?
- **Response headers**: are `Cache-Control`, `ETag`, `Last-Modified`, `Vary`, `Age` present?
- Which cache served the response: browser, service worker, reverse proxy, or CDN?
- DevTools “Disable cache” and reload can alter experiments; do not use a single result to assert all clients behave identically.

Use `curl -i` to inspect response headers; to inspect a CDN chain, you can use verbose/tracing and origin logs to distinguish **fresh hit, revalidation hit, and full miss**. Do not assume a 304 came “from the origin” if an intermediary itself returned the response under permitted conditions.

## 14. Designing Policies for Different Resource Types

| Resource Type | Policy Often Worth Considering | Reason |
| --- | --- | --- |
| JS/CSS with content-hashed filenames | `public, max-age=31536000, immutable` | New URL when bytes change; avoids frequent revalidation |
| Frequently updated HTML entry point | `no-cache` + ETag | May keep the body, but verifies before reuse |
| Infrequently changing public JSON | `public, max-age=60` + ETag | Short freshness and cheap 304 when stale |
| Personal profile allowed in local cache | `private, no-cache` + ETag | Avoids shared-cache storage; private cache revalidates |
| Highly sensitive data | `private, no-store` (alongside other security controls) | Minimizes storing responses in caches |
| Dashboard with strict freshness SLA | Small TTL, `must-revalidate`/appropriate conditions | Avoids serving stale beyond policy |
| Resource used for concurrent PUT | Strong ETag + `If-Match` | Prevents lost updates |
| Large file with Range downloads | Strong validators and `If-Range` per RFC | Avoids mixing bytes from different versions |

These are **guidelines**, not a safe default configuration for every application. You must consider: whether the data is shared, rate of change, security, CDN behavior, deployment changes, purge capability, and acceptable staleness.

## 15. Common Real-World Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `no-cache` as if it meant “do not store” | Misunderstanding why browsers still keep the body | Use `no-store` when storage is truly forbidden |
| `max-age=0` and assuming “no caching” | Body can still be stored/revalidated | Distinguish freshness from storage |
| Setting only `ETag` with no policy | TTL may fall back to heuristics/other metadata | Set an explicit Cache-Control |
| Returning `304` with JSON/body | Violates 304 semantics | Do not send a representation body |
| Returning `304` when ETag changed because the date didn’t | Client wrongly uses the old copy | Prioritize If-None-Match; use accurate validators |
| Comparing If-None-Match using strong comparison | Weak ETag revalidation is handled incorrectly | Use weak comparison per RFC |
| Using weak ETag for If-Match | Strong condition cannot be satisfied as intended | Use strong ETag for lost-update protection |
| Deriving ETag solely from one-second timestamps | Two updates in the same second share the same validator | Use a stable version/hash/transaction ID |
| Content-Encoding changes while keeping the same strong ETag | Range requests and variants can break | Use distinct strong ETags per bytes/variant |
| Missing `Vary: Accept-Encoding` | Cache may serve the wrong encoding | Declare the proper request selection headers |
| Treating `Vary: Cookie` as sufficient for private data | Information may leak from shared caches | Use private/no-store policies + authorization |
| Returning `Last-Modified=Date` on every GET | Time validator constantly changes | Use the actual modification time or omit it |
| Lacking cache duration limits on public content | Unwanted long staleness or excessive revalidation | Set TTL according to goals |
| `immutable` while overwriting the same URL | Clients keep old content for a very long time | Use a new versioned/hashed URL |
| Sending If-None-Match without keeping a cached body | 304 contains no content to display | Keep the body or send an unconditional GET |
| Assuming Java `HttpClient` caches automatically like a browser | Code may re-download every time | Manage caching yourself or use a suitable caching library |
| Not applying `If-Match` atomically | Race condition causes lost update | Check version and update inside a transaction |
| Not testing through CDN/proxy | Headers and Age get modified along the path | Measure at each layer; configure cache keys properly |

## 16. Operational Scenario: Wrong 304 and Users Seeing Stale Pages

A system has multiple origin nodes A and B behind a load balancer. Node A emits `ETag: "v10"`, while Node B has new content but still emits `"v10"` because the tag was hard-coded per deployment or derived from separate cache state.

A client has the stored content from A, then sends a request to B with `If-None-Match: "v10"`. If B returns `304` even though the bytes changed, the client keeps using A’s body. **The bug is in how the validator is generated**, not “HTTP caching failing to update”.

How to fix it:

1. ETags must reflect the **selected representation version** consistently across all nodes (e.g., from a content revision or properly scoped hash).
2. Data and validators must be published/updated atomically; do not change the body first and update the ETag seconds later.
3. If there are multiple variants/encodings, attach the proper Vary and per-variant ETag.
4. Verify 200/304 at the origin and through the CDN, observing `Date`, `Age`, `ETag`, `Cache-Control`, and `Vary`.
5. Have a purge/versioned-URL process when stale objects must be evicted before TTL, but purging does not replace correct validators going forward.

### 16.1. When Does Revalidation Not Help?

If the server provides no validator, caches may have to re-download the body when stale. If caching is disabled with `no-store`, there is no eligible stored copy to use with 304. If the validator does not change when the representation changes, `304` is even more dangerous than re-downloading because it masks new content.

Do not optimize bandwidth with ETags if tag calculation is unreliable. **Validator correctness matters more than bytes saved.**

## 17. Self-Check Exercises

### Exercise A — no-cache and no-store

Resource A returns `Cache-Control: no-cache`, and resource B returns `Cache-Control: no-store`. After downloading, can the browser keep the body of A?

**Answer:** it can keep A per policy, but must validate before reuse. For B, the cache must not intentionally store it per the no-store directive. The two are **not synonymous**.

### Exercise B — 600-Second Freshness, 500-Second Age

A cache receives a `max-age=600` response that already has `Age=500`. Does it immediately get a fresh 600 seconds?

**Answer:** no. Age is how “old” the response already is; the cache must calculate current age per the RFC. At most roughly 100 seconds of freshness remain in this simple example, minus other timing/network and metadata factors.

### Exercise C — Conflicting If-None-Match and If-Modified-Since

A client sends `If-None-Match: "v1"` and `If-Modified-Since` equal to the current representation’s timestamp. The origin is currently serving `ETag: "v2"`. Should it return 304 or 200?

**Answer:** for a normal GET, **200** because If-None-Match takes precedence and does not match the current validator. The server must not look only at the date and return 304.

### Exercise D — Strong vs. Weak

The current ETag is `"v2"`, and the client sends `If-None-Match: W/"v2"`. Does it match? What if it sends `If-Match: W/"v2"` for a PUT?

**Answer:** `If-None-Match` uses weak comparison so it matches on the opaque value; GET can receive **304**. `If-Match` requires strong comparison, so a weak tag is insufficient to allow the update and may return **412**.

### Exercise E — Data Changed Twice in the Same Second

`Last-Modified` is rounded to the same second across two updates; a client sends the old If-Modified-Since. What problem occurs?

**Answer:** the timestamp may fail to distinguish the two versions, leading to incorrect validation. Use properly updated ETags or transaction versions for resources requiring precision.

### Exercise F — Personal Page on a CDN

A user profile endpoint returns `Cache-Control: public, max-age=3600`. Is it safe if other users access the same URL through the CDN?

**Answer:** it cannot be considered safe. If the representation is personalized, shared caching can leak information if cache keys/policies/authorization are wrong. Consider `private`/`no-store`, separating public/private content, and checking authorization.

### Exercise G — 304 Without a Body

A Java application sends `If-None-Match: "v7"` on its own without saving the previous response body. The server returns 304. What data should the app display?

**Answer:** there is no new body. The app needs a **valid cached representation** or must send an unconditional GET to download it again. `304` is a revalidation mechanism, not an empty content response.

### Exercise H — Concurrent PUT

Two clients both read ETag `"v1"`. Client A updates it to `"v2"` using `If-Match: "v1"`; then B sends a PUT also with `If-Match: "v1"`. How does the server handle it?

**Answer:** A can succeed if compare-and-update is atomic. B must receive **`412 Precondition Failed`** since the current version is no longer `"v1"`, preventing overwriting A.

### Exercise I — Content-Hashed Asset with Overwritten Bytes at the Same URL

The server sends `Cache-Control: public, max-age=31536000, immutable` for `/assets/app.4a81d1.js`, but a deployment overwrites new bytes at the **same URL**. Why do clients still receive the old version?

**Answer:** clients can trust that the asset is still fresh and skip revalidation. The right approach is to publish a **new hashed URL** and update the referencing HTML, rather than overwriting the content of an immutable URL.

### Exercise J — Last-Modified and Date

The server returns `Date: Wed, 10 Jan 2024 12:00:00 GMT` and `Last-Modified: Tue, 09 Jan 2024 08:00:00 GMT`. Is there an error?

**Answer:** no. `Date` indicates when the response was generated, while `Last-Modified` indicates when the content was modified. They do not need to be the same. Do not automatically substitute Date for Last-Modified.

## 18. HTTP Caching Design and Testing Checklist

- [ ] Determined whether the representation is public or personalized, and whether shared caches may store it?
- [ ] Does `Cache-Control` accurately reflect TTL, private/public, no-cache/no-store, and revalidation requirements?
- [ ] Understood that `no-cache` still **allows storage**, whereas `no-store` forbids storage?
- [ ] Are `max-age`/`s-maxage` set appropriately; are `Date` and `Age` accounted for when evaluating freshness?
- [ ] Is ETag generated consistently with the representation, changing when bytes/versions change, and distinguishing strong/weak?
- [ ] Is `Vary` set properly for content negotiation, especially `Accept-Encoding`?
- [ ] Is `Last-Modified` the actual modification time, rather than using the current `Date` as the modification time?
- [ ] Do conditional GET/HEAD handlers process `If-None-Match` and `If-Modified-Since` with the **correct precedence**?
- [ ] Does `304` omit the body and return the metadata needed for cache updates?
- [ ] If write preconditions are implemented, does `If-Match` use strong comparison and **atomic** compare-and-write?
- [ ] Is there proper handling for `If-None-Match: *`, entity-tag lists, `W/` tags, and date parsing if implementing in full?
- [ ] When a client receives 304, does it have a matching stored body rather than interpreting it as empty data?
- [ ] Do CDN/reverse proxy/browser layers avoid wrong cache keys or public policies for private data?
- [ ] Retested after real updates, two edits in the same second, multiple origin nodes, gzip/identity variants, clock skew, and malformed validators?
- [ ] Using metrics to observe hit/miss/revalidate, 200/304/412 statuses, Age, network bytes, latency, and stale incidents?

**Conclusion:** `Cache-Control` decides **when and where a response can be stored and reused**; `ETag` and `Last-Modified` provide **validators** to verify stored copies; `If-None-Match`/`If-Modified-Since` enable **304 Not Modified** when appropriate, saving body transfers; `If-Match`/`If-Unmodified-Since` help prevent overwriting older versions. To cache correctly, you must combine **freshness, selected representation, Vary, validators, status codes, and access control**, rather than just adding a header and trusting the browser to do the right thing in every case.

## 19. Standard Reference Documents

- **RFC 9110 — HTTP Semantics:** especially Section 8 on representation metadata, Section 13 on conditional requests, and Section 15 on status codes. https://www.rfc-editor.org/rfc/rfc9110
- **RFC 9111 — HTTP Caching:** cacheability, freshness, Age, Cache-Control, and validation. https://www.rfc-editor.org/rfc/rfc9111
- **RFC 5861 — HTTP Cache-Control Extensions for Stale Content:** `stale-while-revalidate`, `stale-if-error`. https://www.rfc-editor.org/rfc/rfc5861
- **Java 17 HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Java 17 HttpServer:** https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html

HTTP caching is a protocol with many conditions; the examples above teach the fundamentals and key rules. When deploying public CDNs, proxies, or full-featured HTTP servers, use an appropriate framework and verify RFCs/cache behavior directly before relying on optimizations or security changes.