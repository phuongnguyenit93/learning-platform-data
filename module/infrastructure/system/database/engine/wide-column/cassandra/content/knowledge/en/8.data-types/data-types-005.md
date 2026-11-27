# blob, boolean, inet, and Mapping Binary and Address Data in Apache Cassandra

In Apache Cassandra, `blob`, `boolean`, and `inet` address three distinct problems: **storing raw bytes**, **representing true/false values**, and **storing structured IP addresses**. They frequently appear in API event tables, telemetry, audit logs, session tracking, checksums, and file metadata.

This lesson belongs to the **Data Types** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. The module covers distributed wide-column architecture, partition keys, query-driven table design, read/write consistency levels, replication, compaction, repair, error handling, and Java integration. When choosing these three types, answer simultaneously: **what does the value mean, how does the Java application represent it, which partition/clustering keys will queries use, and how do retries or updates affect correctness?**

## 1. Quick Overview

| CQL Type | Represented Value | Typical Java Driver 4.x Type | Suitable Use Cases | Does Not Replace |
|---|---|---|---|---|
| `blob` | Sequence of binary bytes, without automatic encoding interpretation | `ByteBuffer` | SHA-256 digests, small binary encodings, bounded tiny thumbnails, header/protocol bytes | Object storage, JSON/UTF-8 decoders, large file schemas |
| `boolean` | Two values `true`/`false` when the column is present | `boolean`/`Boolean` depending on null handling | Status flags, verification results, feature toggles | Multi-step states or unknown states |
| `inet` | An IPv4 or IPv6 address | `InetAddress` | Source IP, destination IP, node/service address recorded as an IP value | Hostnames, URLs, subnets/CIDRs, address ranges |

Commonly confused values:

- `0x4f4b` is a **binary literal** in CQL consisting of two hex bytes, `4f` and `4b`. Those bytes happen to be ASCII for `"OK"`, yet `blob` does not treat this as a text string.
- `true` is a **boolean** value. The string `'true'`, the number `1`, and `null` are not equivalent to `true`.
- `'203.0.113.24'` is an **IPv4** example, and `'2001:db8::24'` is an **IPv6** example using documentation address ranges. They illustrate an `inet` column well, whereas `'api.example.com'` is a hostname, not an IP address literal.
- `inet` supports both IPv4 and IPv6; you do not need two separate columns just because there are two address families.

Data types govern **value semantics**, whereas search capabilities like "fetch the 100 latest requests for a tenant" or "find requests by IP for a day" depend first on **the primary key and query-driven table design**.

## 2. The blob Type: Store Exact Bytes Without Assuming Content

### 2.1. What Is blob?

`blob` (*binary large object*) represents a byte sequence. Unlike `text`/`varchar`, which are UTF-8 Unicode strings, a `blob` value carries no built-in metadata about **charset**, MIME type, data format, or decoding rules.

Example:

~~~cql
CREATE TABLE tiny_binary_samples_by_id (
    sample_id uuid PRIMARY KEY,
    format_code text,
    payload blob
);

INSERT INTO tiny_binary_samples_by_id
    (sample_id, format_code, payload)
VALUES
    (11111111-1111-4111-8111-111111111111, 'RAW', 0x004f4bff);

SELECT format_code, payload
FROM tiny_binary_samples_by_id
WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

The value `0x004f4bff` contains four bytes: `00`, `4f`, `4b`, `ff`. Never blindly decode all four bytes as UTF-8: a standalone `ff` is not a valid UTF-8 byte.

CQL uses the `0x` prefix for `blob` hex literals. One byte equals **two hex digits**, so `0x004f4bff` is **4 bytes**, not eight bytes. When accessing via the Java Driver, the application works with `ByteBuffer` and must explicitly decide whether to decode into text.

### 2.2. Raw Bytes, UTF-8 Text, Base64, and Hex Differ

The same binary data can have several representations:

| Representation | Example for Two Bytes `4f 4b` | Role |
|---|---|---|
| Binary bytes | `4f 4b` | Actual data, stored in `blob` |
| CQL hex literal | `0x4f4b` | Syntax for writing binary data in CQL statements |
| Base64 | `T0s=` | Text encoding for transmitting bytes over text-only protocols |
| ASCII/UTF-8 text | `OK` | Interpreting those bytes as text under a chosen charset |

**Base64 is a transport encoding, not security encryption.** If an API sends `"T0s="` (Base64), Java must decode it into two bytes before binding to `blob`. If you store `"T0s="` as-is into `text`, the stored value is four characters, not the two original bytes.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

byte[] raw = new byte[] { 0x4f, 0x4b };

String asText = new String(raw, StandardCharsets.UTF_8); // "OK"
String asBase64 = Base64.getEncoder().encodeToString(raw); // "T0s="

byte[] decoded = Base64.getDecoder().decode(asBase64);
ByteBuffer payload = ByteBuffer.wrap(decoded);
~~~

For JSON, XML, logs, or usernames meant to be human-readable, `text`/`varchar` is usually more meaningful than `blob`; use `blob` when **the exact raw bytes** matter. If byte-exact preservation is required for text data, document the charset, normalization, and handling of invalid byte sequences.

### 2.3. What Should Be Stored in blob?

Relatively small, size-bounded values, such as:

- Content **digests/hashes** (`SHA-256` is 32 bytes), used for integrity checks or digest-based lookups.
- **Signature bytes**, binary protocol fields, or versioned serialized sensor frames.
- **Small sample payloads** for diagnostics when operational policy permits and size limits are enforced.
- **Binary identifiers** issued by external systems when no dedicated CQL type (like `uuid`) fits better.

A digest stores only the **hash output** and does not allow recovering the source data. Hashes carry a theoretical collision risk, though SHA-256 is strong enough for most engineering purposes; if the application treats a digest as a legally or financially significant unique identifier, enforce appropriate verification and collision-avoidance policies.

Conversely, **do not default to putting videos, high-resolution images, backup archives, or multi-MB/GB documents into a `blob` cell**. Cassandra serves row/column queries by partition key; object storage is usually a better fit for large files. A common pattern is storing `object_uri text`, `content_type text`, `size_bytes bigint`, and `sha256 blob` along with status and query metadata in Cassandra, while keeping the raw file in object storage.

Benefits of offloading large files include reduced client memory/GC pressure, lower coordinator/replica network traffic, avoiding oversized rows/partitions, and simpler streaming or range downloads. The final decision should still be guided by SLAs and measured workload behavior.

## 3. Java ByteBuffer: Buffer Bounds Must Be Handled Properly

### 3.1. Mapping blob ↔ ByteBuffer

With Apache Cassandra Java Driver 4.x, common methods are:

- Write: `BoundStatementBuilder.setByteBuffer(index, ByteBuffer)`.
- Read: `Row.getByteBuffer("payload")`.
- Missing-data check: `row == null` or `row.isNull("payload")`.

A `ByteBuffer` tracks **position, limit, and capacity**. The active byte slice to read spans from `position` (inclusive) to `limit` (exclusive), with length `remaining()`.

~~~java
import java.nio.ByteBuffer;
import java.util.Arrays;

byte[] source = new byte[] { 0x00, 0x4f, 0x4b, (byte) 0xff };
ByteBuffer buffer = ByteBuffer.wrap(source);
buffer.position(1); // Skip the first byte.

System.out.println(buffer.remaining()); // 3
// Remaining bytes are: 4f 4b ff

ByteBuffer view = buffer.duplicate();
byte[] remaining = new byte[view.remaining()];
view.get(remaining);

System.out.println(Arrays.toString(remaining));
// [79, 75, -1] because Java bytes are signed.
~~~

Important consequences:

1. **Never assume `buffer.array()` is always safe or available.** Direct buffers, read-only buffers, or slices may not expose a backing array, and the backing array may include bytes outside `position..limit`.
2. **Do not mutate the `position` of a buffer the caller still uses.** Use `duplicate()` or `asReadOnlyBuffer()` to read through an independent position view.
3. **Never mutate a bound array/buffer while an asynchronous write is still using it.** `ByteBuffer.wrap(byte[])` shares backing memory with the input array. If a snapshot is needed, copy the bytes before binding.
4. If the data represents UTF-8 text, decode it with an explicit charset and define behavior for malformed bytes.

### 3.2. Copying Bytes to Prevent Mutation

~~~java
import java.nio.ByteBuffer;
import java.util.Arrays;

static ByteBuffer snapshot(byte[] original) {
    byte[] copy = Arrays.copyOf(original, original.length);
    return ByteBuffer.wrap(copy).asReadOnlyBuffer();
}

static byte[] copyRemaining(ByteBuffer input) {
    ByteBuffer view = input.duplicate();
    byte[] bytes = new byte[view.remaining()];
    view.get(bytes);
    return bytes;
}
~~~

This pattern is for payloads **already bounded in size**. Do not load an entire huge file into a `byte[]` just to create a `ByteBuffer`; use object storage or a dedicated streaming mechanism as needed.

### 3.3. Hashing Content Before Storage

~~~java
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

static ByteBuffer sha256(byte[] bytes) throws NoSuchAlgorithmException {
    byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
    // SHA-256 is 32 bytes.
    return ByteBuffer.wrap(digest);
}
~~~

When storing `sha256 blob`, every application must hash the **exact same canonical byte sequence**. Equivalent JSON content with different whitespace or key order will produce different digests when hashed as raw bytes. Hashing cannot replace format canonicalization rules.

## 4. boolean: True/False and Unknown Cases

CQL `boolean` represents **`true`** and **`false`**. An unset column reads as **`null`**, which carries a different meaning from false when business logic must distinguish "not yet processed" from "processed and failed."

Example:

~~~cql
CREATE TABLE verification_by_request (
    request_id uuid PRIMARY KEY,
    passed boolean,
    verifier text,
    checked_at timestamp
);

INSERT INTO verification_by_request (request_id, passed, verifier, checked_at)
VALUES (22222222-2222-4222-8222-222222222222, true,
        'risk-service', '2026-11-21T02:00:00Z');

INSERT INTO verification_by_request (request_id, passed, verifier, checked_at)
VALUES (33333333-3333-4333-8333-333333333333, false,
        'risk-service', '2026-11-21T02:01:00Z');
~~~

Distinctions:

| Business State | `passed` Value | Meaning |
|---|---|---|
| Checked and passed | `true` | Verification succeeded |
| Checked and failed | `false` | Verification failed |
| Not yet checked / no result yet | Column absent or `null` | No boolean result to conclude yet |

Cassandra has no "nullable boolean defaulting to false" just from declaring `boolean`. If you need a **multi-step workflow state** such as `QUEUED`, `RUNNING`, `APPROVED`, `REJECTED`, `EXPIRED`, a `state text` column with an allowlist or a dedicated state model expresses it far better.

**Caution on updates:** in Cassandra, explicitly writing `null` to a column is interpreted as **deleting the value**, creating a tombstone. Omitting the column or using the driver's **UNSET** mechanism differs from writing `null`. If the application wants to keep the existing value when a field is omitted from a patch request, never bind `null` to mean "unchanged."

### 4.1. boolean in Java

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

Row row = session.execute(
    "SELECT passed FROM verification_by_request "
  + "WHERE request_id = 22222222-2222-4222-8222-222222222222"
).one();

if (row == null || row.isNull("passed")) {
    // Row missing or column has no value yet.
} else {
    boolean passed = row.getBoolean("passed");
    // passed can be true or false.
}
~~~

`Row.getBoolean()` returns a primitive `boolean`, which cannot represent `null`; check `isNull` before reading whenever three-state logic is needed.

In prepared statements, use `setBoolean(index, value)`. If the application receives a nullable `Boolean`, decide the business intent before binding: write true, write false, delete the field, or leave the existing value untouched. Never accidentally turn `null` into false via Java default values.

### 4.2. boolean and Partition Key Design

Never choose **a single boolean column** as the partition key for a large table: the entire dataset has only two common key values, creating very few partitions and causing massive partitions and hotspots.

If the query is "fetch failed transactions for a tenant on a given day," design the table around `tenant_id`, time buckets, and status (if needed), rather than assuming any `WHERE passed = false` clause is efficient just because `passed` is a boolean.

**Do not rely on `ALLOW FILTERING` as a default strategy** to find all false rows across a large cluster. Filtering on a column outside the key or a suitable index can force scanning huge amounts of data.

## 5. inet: Structured IPv4 and IPv6 Addresses

### 5.1. When to Use inet Instead of text?

The `inet` type stores an IP address, either IPv4 (32-bit) or IPv6 (128-bit). Unlike `text`, it carries **IP address** semantics, enabling applications and drivers to read/write via `InetAddress`.

~~~cql
CREATE TABLE endpoints_by_service (
    service_id uuid,
    endpoint_id uuid,
    ip_address inet,
    port int,
    protocol ascii,
    PRIMARY KEY ((service_id), endpoint_id)
);

INSERT INTO endpoints_by_service
    (service_id, endpoint_id, ip_address, port, protocol)
VALUES
    (44444444-4444-4444-8444-444444444444,
     55555555-5555-4555-8555-555555555555,
     '2001:db8::24', 443, 'TCP');

INSERT INTO endpoints_by_service
    (service_id, endpoint_id, ip_address, port, protocol)
VALUES
    (44444444-4444-4444-8444-444444444444,
     66666666-6666-4666-8666-666666666666,
     '203.0.113.24', 8443, 'TCP');
~~~

Note: `inet` holds only an IP address. Modeling a real endpoint also requires **port** (0–65535 per application rules), **protocol**, and potentially **hostname**, **environment**, or certificate details. `inet` does not replace an entire URL or socket address.

If the source value is `https://api.example.com:443`, you cannot cram the full URL into `inet`. If you need to store hostnames for dynamic DNS resolution, add a separate `host_name text` column, since one hostname can resolve to multiple IPs and DNS results change over time.

### 5.2. inet Does Not Represent Subnets, CIDRs, or IP Ranges

| Input | Use `inet` Directly? | Appropriate Representation |
|---|---|---|
| `203.0.113.24` | Yes | A single IPv4 address |
| `2001:db8::24` | Yes | A single IPv6 address |
| `203.0.113.0/24` | No | A CIDR network: store `network_address` + `prefix_length` or a separately validated string/structure |
| `api.example.com` | No | Hostname in `text` |
| `203.0.113.24:443` | No | Separate `inet` IP and `int` port |
| A range from IP A to IP B | Not as a single `inet` value | Start/end IP or prefix model with range matching in the application |

Queries like "which /24 network does this IP belong to?" typically require subnet logic in the application or a table/key designed around normalized prefixes. `inet` does not provide CIDR containment operators like a specialized routing engine.

### 5.3. IP Normalization and IPv4/IPv6 Differences

IPv6 addresses can have multiple **equivalent text representations** due to zero compression and hex group shortening. When data is a genuine IP, `inet` lets you work with parsed IP values rather than depending on sender formatting.

However, plain IPv4 and **IPv4-mapped IPv6** addresses should not automatically be treated as identical business entities without explicit normalization rules. Systems must decide whether to accept IPv4-mapped IPv6, preserve address families, and model proxies/NATs.

**Important for network logs:** the IP seen at a web server may belong to a **reverse proxy, load balancer, or NAT**, not the end client device. Headers like `X-Forwarded-For` are only trustworthy when traversing a trusted proxy chain with explicit parsing and recording rules. `inet` validates address format, **not address provenance**.

## 6. Java InetAddress: Binding and Reading Addresses Safely

Apache Cassandra Java Driver 4.x maps `inet` to Java `InetAddress`:

- Write: `BoundStatementBuilder.setInetAddress(index, value)`.
- Read: `Row.getInetAddress("ip_address")`.
- Missing check: `row.isNull("ip_address")`.

Example constructing IPv4 without DNS lookups:

~~~java
import java.net.InetAddress;
import java.net.UnknownHostException;

byte[] ipv4Bytes = new byte[] {
    (byte) 203, 0, 113, 24
};

InetAddress ip = InetAddress.getByAddress(ipv4Bytes);
System.out.println(ip.getHostAddress()); // 203.0.113.24
~~~

`InetAddress.getByName(input)` may trigger a **DNS lookup** when `input` is a hostname, so it is not a safe way to enforce "input must be an IP literal" without separate validation. For untrusted inputs or high-throughput ingestion, use a parser that accepts IPv4/IPv6 literals only and construct `InetAddress` from validated bytes; never implicitly trigger DNS resolution per row.

CQL integration example:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.net.InetAddress;
import java.util.UUID;

// session is a CqlSession with keyspace/cluster configured outside this example.
UUID serviceId = UUID.fromString("44444444-4444-4444-8444-444444444444");
UUID endpointId = UUID.fromString("55555555-5555-4555-8555-555555555555");

InetAddress address = InetAddress.getByAddress(
    new byte[] {(byte) 203, 0, 113, 24}
);

PreparedStatement ps = session.prepare(
    "INSERT INTO endpoints_by_service "
  + "(service_id, endpoint_id, ip_address, port, protocol) "
  + "VALUES (?, ?, ?, ?, ?)");

BoundStatement bound = ps.boundStatementBuilder()
    .setUuid(0, serviceId)
    .setUuid(1, endpointId)
    .setInetAddress(2, address)
    .setInt(3, 443)
    .setString(4, "TCP")
    .build();

session.execute(bound);
~~~

When reading:

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

PreparedStatement find = session.prepare(
    "SELECT ip_address, port, protocol "
  + "FROM endpoints_by_service "
  + "WHERE service_id = ? AND endpoint_id = ?");

Row result = session.execute(
    find.bind(serviceId, endpointId)
).one();

if (result != null && !result.isNull("ip_address")) {
    InetAddress stored = result.getInetAddress("ip_address");
    String display = stored.getHostAddress(); // Numeric address for display.
    int port = result.getInt("port");
}
~~~

`getHostAddress()` returns the numeric IP string. Never call `getHostName()` just to format logs if you want to avoid reverse DNS lookups and network stalls. Logging IPs must also comply with your system's data protection policies.

## 7. Combined Case Study: Request Auditing by Tenant and Day

Suppose a Java application must answer the query:

> "Fetch the 100 most recent API requests for a tenant on a given day, showing whether the request succeeded, source IP, and a small byte sample for diagnostics."

CQL table design:

~~~cql
CREATE TABLE api_requests_by_tenant_day (
    tenant_id uuid,
    request_day date,
    occurred_at timestamp,
    request_id uuid,
    succeeded boolean,
    client_ip inet,
    payload_preview blob,
    error_code text,
    PRIMARY KEY ((tenant_id, request_day), occurred_at, request_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, request_id ASC);
~~~

Explanation:

- `(tenant_id, request_day)` is the composite **partition key**, grouping events by tenant and day.
- `occurred_at timestamp` is a clustering column ordered newest to oldest; `request_id uuid` disambiguates requests occurring within the same millisecond.
- `succeeded boolean` indicates a true/false result; if pending states must be distinguished, define an explicit business state column.
- `client_ip inet` stores a parsed IP validated from trusted headers/sources.
- `payload_preview blob` is a **bounded byte excerpt**, not the full file or large request body.
- `error_code text` may be absent for successful requests; check for null when reading.

~~~cql
INSERT INTO api_requests_by_tenant_day (
    tenant_id, request_day, occurred_at, request_id,
    succeeded, client_ip, payload_preview, error_code
) VALUES (
    77777777-7777-4777-8777-777777777777,
    '2026-11-21', '2026-11-21T03:15:00Z',
    88888888-8888-4888-8888-888888888888,
    true, '203.0.113.24', 0x4f4b, null
);

SELECT occurred_at, request_id, succeeded, client_ip,
       payload_preview, error_code
FROM api_requests_by_tenant_day
WHERE tenant_id = 77777777-7777-4777-8777-777777777777
  AND request_day = '2026-11-21'
LIMIT 100;
~~~

In the example, `payload_preview = 0x4f4b` holds two data bytes; `error_code = null` illustrates an absent column. In production, when a field has no value, **omit the column from the INSERT** to avoid writing a tombstone from an explicit null. The same applies when a request has no payload preview.

### 7.1. Writing from Java with Prepared Statements

~~~java
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.net.InetAddress;
import java.nio.ByteBuffer;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

UUID tenantId = UUID.fromString("77777777-7777-4777-8777-777777777777");
UUID requestId = UUID.fromString("88888888-8888-4888-8888-888888888888");
Instant occurredAt = Instant.parse("2026-11-21T03:15:00Z");
LocalDate dayUtc = occurredAt.atZone(ZoneOffset.UTC).toLocalDate();

InetAddress clientIp = InetAddress.getByAddress(
    new byte[] {(byte) 203, 0, 113, 24}
);

byte[] previewBytes = new byte[] { 0x4f, 0x4b }; // Bounded payload.
ByteBuffer preview = ByteBuffer.wrap(previewBytes.clone());

PreparedStatement insert = session.prepare(
    "INSERT INTO api_requests_by_tenant_day "
  + "(tenant_id, request_day, occurred_at, request_id, "
  + " succeeded, client_ip, payload_preview) "
  + "VALUES (?, ?, ?, ?, ?, ?, ?)");

BoundStatement request = insert.boundStatementBuilder()
    .setUuid(0, tenantId)
    .setLocalDate(1, dayUtc)
    .setInstant(2, occurredAt)
    .setUuid(3, requestId)
    .setBoolean(4, true)
    .setInetAddress(5, clientIp)
    .setByteBuffer(6, preview)
    .build();

session.execute(request);
~~~

Two decisions here preserve correctness:

1. **The day bucket** is derived from `occurredAt` in UTC. Every writer and reader must use the exact same rule to avoid placing requests in different daily partitions due to time zones.
2. **`requestId`, `occurredAt`, and the partition key** remain stable on retries. Generating a new UUID and timestamp after a timeout turns one event into multiple rows.

Even with identical keys, updating the same cell with different values is governed by Cassandra's conflict resolution rules. **Consistency levels** like `LOCAL_QUORUM` control replica acknowledgment, not business-level idempotency.

### 7.2. Reading and Interpreting Data

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetAddress;
import java.nio.ByteBuffer;

PreparedStatement select = session.prepare(
    "SELECT request_id, succeeded, client_ip, payload_preview "
  + "FROM api_requests_by_tenant_day "
  + "WHERE tenant_id = ? AND request_day = ? LIMIT 100");

for (Row event : session.execute(select.bind(tenantId, dayUtc))) {
    UUID id = event.getUuid("request_id");

    Boolean succeeded = event.isNull("succeeded")
        ? null : event.getBoolean("succeeded");

    InetAddress ip = event.isNull("client_ip")
        ? null : event.getInetAddress("client_ip");

    byte[] previewCopy = null;
    if (!event.isNull("payload_preview")) {
        ByteBuffer view = event.getByteBuffer("payload_preview").duplicate();
        previewCopy = new byte[view.remaining()];
        view.get(previewCopy);
    }

    // Process event; do not decode preview as text unless encoding is known.
}
~~~

Because `Boolean` can be null, the application clearly distinguishes missing data from failure (`false`). For IP, if the column is absent, check the data source and handling rules. For `blob`, read the buffer using **remaining bytes**, never relying on `array()`.

### 7.3. What If You Need to Query by IP?

`api_requests_by_tenant_day` is built for tenant/day reads. The query "find all requests from IP `203.0.113.24` across the cluster on a given day" **has no direct access path** merely because `client_ip` is `inet`.

A separate query table can be created when the business genuinely requires it:

~~~cql
CREATE TABLE request_refs_by_ip_day (
    client_ip inet,
    request_day date,
    occurred_at timestamp,
    request_id uuid,
    tenant_id uuid,
    PRIMARY KEY ((client_ip, request_day), occurred_at, request_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, request_id ASC);
~~~

However, this design requires checking for **hotspots**: many clients can share a single proxy/NAT IP and build an oversized partition. At high traffic, you may need hourly buckets, sharding, or another search model. Writing to two tables also requires synchronization, retry, and reconciliation rules, because writing across two partitions/tables is not an atomic multi-table transaction by default.

## 8. Operational Limits You Need to Know

### 8.1. Large BLOBs Burden Reads, Writes, and Compaction

Larger blobs increase byte volume across client, coordinator, and replicas. Rows with bulky payloads undermine efficient small-column reads and increase memory, network, and disk I/O pressure. Compaction must process SSTables holding those values; repair must exchange metadata to keep replicas synchronized.

A pragmatic rule:

- Enforce a clear payload cap at the API boundary—e.g., store only **a few-hundred-byte excerpt** for debugging.
- Store `size_bytes bigint`, `sha256 blob`, `content_type text`, and a URI to object storage when full content is large.
- Avoid storing sensitive data in payload previews; redact or strip secrets and PII as required.
- Monitor p95/p99 latency, partition sizes, tombstones, and compaction under realistic workloads.

No `blob` type enforces a size limit for you if the application fails to validate inputs.

### 8.2. Deletions, TTL, and Tombstones

In Cassandra, deleting cells, explicitly writing nulls, or expiring data via TTL generates tombstones, which degrade read performance and compaction when accumulated. For an absent boolean column, setting `passed = null` is not equivalent to setting `passed = false`. For blobs, deleting payloads later to reclaim space also requires accounting for tombstone counts and compaction cleanup timing.

If auditing requires months of retention, derive TTL/retention from business rules instead of setting an arbitrary default TTL and losing audit evidence. If deletion is required for data privacy regulations, design deletion across live tables, replicas, and backups per system policy.

### 8.3. Consistency, Retries, Repair, and Data Types

Cassandra **replicates** written values as bytes/cells, and **repair** helps replicas converge. They do **not**:

- Automatically decode a `blob` into valid UTF-8 if the application wrote the wrong bytes.
- Turn `false` into `null` or vice versa according to business state.
- Automatically distinguish end-user IPs from reverse proxy IPs.
- Add an index to scan all IPs when the table does not match the query pattern.
- Guarantee a retried request produces only one row if every retry generates a new primary key.

Therefore, correctness must be enforced by **the data contract + key design + Java error handling**. Consistency level selection should reflect SLAs and concurrency needs, not serve as a workaround for broken column semantics.

## 9. Common Mistakes and How to Fix Them

| Mistake | Consequence | Solution |
|---|---|---|
| Storing Base64 strings in `blob` as raw text | Stored bytes are not the original binary payload | Decode Base64 to `byte[]`, then bind as `ByteBuffer` |
| Decoding every `blob` as UTF-8 | Arbitrary bytes may be invalid and corrupt data | Decode only when charset/format is known |
| Calling `ByteBuffer.array()` to read payload | Fails on direct/read-only buffers, reads extra bytes | Use `duplicate()`, `remaining()`, and copy the active slice |
| Mutating the backing array after binding an async write | Unintended bytes may be written | Snapshot the data or manage buffer lifecycle |
| Storing hundreds-of-MB files in a `blob` cell | Heavy network/memory/compaction load | Use object storage + URI/metadata in Cassandra |
| Merging "unprocessed" and "failed" into `false` | Loses business state distinction | Handle `null` separately or model explicit states |
| Binding `null` to mean "unchanged" | Deletes the cell and creates a tombstone | Omit column / use UNSET for patch semantics |
| Using `boolean` as the sole partition key | Creates a few massive hotspot partitions | Design composite keys by tenant/bucket |
| Storing CIDR `203.0.113.0/24` in `inet` | Not a single IP address | Use a dedicated network prefix model |
| Calling `InetAddress.getByName` on arbitrary input | Triggers DNS lookups instead of literal parsing | Validate IP literals before constructing `InetAddress` |
| Treating proxy IP as end-user IP | Inaccurate audit trails | Enforce trusted proxy rules and source IP parsing |
| Filtering `WHERE client_ip = ...` without a matching key/index | Expensive scans or invalid queries | Build an IP-keyed query table or suitable search mechanism |

## 10. Applied Exercises

### Exercise 1 — Which Type Should You Use?

A system stores: a 4 MB profile photo, the photo's SHA-256 digest, an "approved" flag, the client's IPv6 address, and a CIDR `2001:db8::/32`.

**Hint:** store the photo in object storage and keep URI/metadata; SHA-256 digest as a 32-byte `blob`; approval flag as `boolean` if strictly true/false; single IP as `inet`; CIDR requires a separate network/prefix model, not a single `inet` value.

### Exercise 2 — Misread ByteBuffer

A buffer has capacity 1024, `position=100`, `limit=108`. The application calls `buffer.array()` and writes the entire array to `blob`.

**Question:** How many bytes of actual payload were expected? How many might the application accidentally write?

**Answer:** the valid view contains **8 bytes**; writing the backing array could write **1024 bytes** (including bytes outside the payload slice). Use `duplicate()`, `remaining()`, and copy the 8 bytes.

### Exercise 3 — Boolean null vs. false

A request has not yet undergone security checks, yet the system defaults `passed=false`. Later, a report counts "how many requests were rejected."

**Question:** Why is the report wrong? How should the model be fixed?

**Answer:** `false` conflates "not checked yet" with "failed." Keep `passed` unset when unverified, add `checked_at`, or use a `state` column with values `PENDING`, `PASSED`, `FAILED`.

### Exercise 4 — Querying by IP Address

An application stores `client_ip inet` in a table partitioned by `tenant_id + request_day`. Users ask to retrieve all requests for an IP over a month.

**Question:** Does simply changing `client_ip` to `text` make the query faster?

**Answer:** no. You need an access path keyed by IP + appropriate bucket, or a benchmarked index/search system; watch out for NAT/proxy IPs creating hot partitions.

## 11. Checklist for Designing blob, boolean, and inet

- [ ] Is the content genuinely **raw binary bytes**, or is it text/JSON better stored as UTF-8?
- [ ] Does `blob` have a **byte cap**, encoding/decoding contract, and object storage consideration for large files?
- [ ] Is Base64/hex API input properly decoded to bytes before binding?
- [ ] Does Java handle `ByteBuffer` using **remaining/duplicate**, avoiding `array()` and unsafe mutation?
- [ ] For `boolean`, are **true / false / no result yet** distinguished without equating null with false?
- [ ] Do PATCH/UPDATE paths distinguish **UNSET/omitted field** from **writing null to delete**?
- [ ] Does `inet` receive IP literals only? Are hostnames, ports, URLs, and CIDRs modeled separately?
- [ ] Is source IP derived under a **trusted proxy** policy with consistent IPv4/IPv6 rules?
- [ ] Do real queries have matching partition/clustering keys, buckets, and safe partition sizes?
- [ ] Do event write retries reuse the **exact same primary key** to prevent duplicate rows?
- [ ] Do Java getters/setters match column types (`getByteBuffer`, `getBoolean`, `getInetAddress`) with proper null checks?
- [ ] Have tombstones, TTL, compaction, repair, and retention requirements been accounted for operationally?

**Key takeaway:** `blob` preserves **raw bytes**, `boolean` captures **true/false outcomes**, and `inet` stores **structured IP addresses**. Choosing the right type prevents loss of meaning, while **partition keys, clustering keys, retry policies, and the Java driver** determine whether that data is read and written accurately and efficiently in a Cassandra cluster.
