# OUT_OF_RANGE

In gRPC, **OUT_OF_RANGE is status code 11**, used when an operation requests a position, index, or data range outside the currently valid domain. The request may be structurally valid and the arguments may have the right types, yet the requested value exceeds the range currently supported by the resource or API. For example, a client requests to read a file segment starting past the current end of the file.

In **SPRING_GRPC**, you must clearly define the valid domain for each operation, range boundary conventions, and behavior when data changes. OUT_OF_RANGE differs from INVALID_ARGUMENT: the former can often be resolved if the resource state changes, whereas the latter lies in the input value itself. Also distinguish a read request past EOF from a stream reading sequentially and ending naturally at EOF; the second case normally completes with success.

## 1. Meaning of OUT_OF_RANGE

OUT_OF_RANGE has the numeric value **11**. This status applies when the requested operation falls outside the valid range of the resource or data domain at processing time.

| Perspective | Meaning |
| --- | --- |
| Client | The requested position, index, or range is outside the currently available scope |
| Server | The operation cannot be satisfied because the range exceeds resource/domain bounds |
| gRPC runtime | Terminates the RPC with status OUT_OF_RANGE |
| Business | The client may need to re-read bounds, choose another range, or wait for data to appear |

For example:

- Reading a file at an offset beyond the file size.
- Requesting a record sequence greater than the latest generated sequence.
- Querying history earlier than the oldest retention point still stored by the service.
- Accessing an element by index beyond the count of a structure with a defined index domain.
- Requesting a chunk beyond the published total chunk count.
- Reading a time range outside the data window supported by the API.

This status does not by itself state the exact limit or whether data will appear later. If the client needs to adjust its request, the server should provide bounds or a safe way to query metadata.

## 2. OUT_OF_RANGE differs from INVALID_ARGUMENT

This is the core rule when choosing a status:

- INVALID_ARGUMENT is used when the input value is invalid under the contract regardless of system state.
- OUT_OF_RANGE is used when the value is semantically valid in general, but falls outside the current bounds of the resource or data.

Example with a file-reading RPC:

| Request | Usually appropriate status/outcome | Reason |
| --- | --- | --- |
| Negative offset | INVALID_ARGUMENT | Offset is invalid under the contract |
| Negative length | INVALID_ARGUMENT | Length cannot be negative |
| Valid offset exceeding file size | OUT_OF_RANGE | Position is outside currently available data |
| Offset inside file, length past EOF | OUT_OF_RANGE if the API requires the full range | Requested interval crosses the boundary |
| Offset at EOF and length equal to 0 | Empty response or OK per contract | An empty range can be valid |
| Offset inside file, no matching records | OK with empty result if semantics is a query | Having no results is not necessarily a range error |

A request can change from OUT_OF_RANGE to valid if a file grows or new sequences are written. Conversely, a formatting error such as a negative offset cannot be fixed simply by waiting for the resource to change.

## 3. Defining exact range boundaries

The API must publish whether ranges use inclusive or exclusive bounds. A common convention is a half-open interval:

```text
[start, end)

start is inclusive
end is exclusive
length = end - start
```

With this convention, the range [10, 20) contains positions 10 through 19 and has length 10. Two ranges [10, 20) and [20, 30) are adjacent, non-overlapping, and miss no element at the boundary.

For APIs accepting offset and length, specify:

- Whether offsets are 0-based or 1-based.
- Whether length 0 is accepted.
- Whether a range extending past EOF is rejected outright or returns the remaining data.
- What an offset equal to EOF means.
- Whether there is a maximum length per RPC.
- When file/dataset size is evaluated: at call start or within a consistent snapshot.

Do not leave client and server to guess these conventions. Boundary mismatches often cause duplicate reads, skipped records, or repeated chunks during pagination.

## 4. Protobuf contract example for range reads

A chunk-reading RPC can be defined as:

```protobuf
syntax = "proto3";

package storage.v1;

service FileService {
  rpc ReadChunk(ReadChunkRequest) returns (ReadChunkReply);
}

message ReadChunkRequest {
  string file_id = 1;
  int64 offset = 2;
  int32 length = 3;
}

message ReadChunkReply {
  bytes data = 1;
  int64 next_offset = 2;
  bool end_of_file = 3;
}
```

The contract should state clearly:

- Whether offset and length are measured in bytes or another unit.
- Negative offset and negative length are INVALID_ARGUMENT.
- An offset beyond file size is OUT_OF_RANGE.
- Whether a range crossing EOF is rejected or allows a partial read.
- next_offset is the next position under the same range convention.
- Whether the file can change while reading or the request is bound to a snapshot/version.

If the API allows partial reads, the response must clearly show the number of bytes read and the next position. If the API promises to return the entire requested range, never silently return less data while letting the client assume the full request succeeded.

## 5. Safe range validation in Java

When checking offset and length, avoid addition that can overflow. The expression offset + length can overflow long and make a very large range appear small or negative.

Validation example:

```java
public void validateReadRange(long offset, int length, long fileSize) {
    if (offset < 0 || length < 0) {
        throw Status.INVALID_ARGUMENT
            .withDescription("Offset and length must be non-negative")
            .asRuntimeException();
    }

    if (offset > fileSize || length > fileSize - offset) {
        throw Status.OUT_OF_RANGE
            .withDescription("Range is outside the current file size")
            .asRuntimeException();
    }
}
```

The condition offset > fileSize is checked before subtraction, so fileSize - offset cannot be negative in the subsequent branch provided fileSize has been verified non-negative. If the API does not accept an empty range at EOF, define and check the offset == fileSize with length == 0 case explicitly.

Do not use one generic check for every kind of range. For timestamps, sequence numbers, page indexes, or byte offsets, units and boundary rules can differ.

## 6. Mapping domain exceptions to OUT_OF_RANGE in Spring gRPC

The application service should express domain errors explicitly instead of leaving the handler to guess from generic Java exceptions:

```java
public byte[] readChunk(String fileId, long offset, int length) {
    FileMetadata file = fileRepository.findById(fileId)
        .orElseThrow(FileNotFoundException::new);

    rangeValidator.validateReadRange(offset, length, file.size());
    return storage.read(fileId, offset, length);
}
```

If the validator throws a domain exception, the gRPC boundary maps it:

```java
try {
    byte[] data = fileService.readChunk(
        request.getFileId(),
        request.getOffset(),
        request.getLength());

    ReadChunkReply reply = ReadChunkReply.newBuilder()
        .setData(ByteString.copyFrom(data))
        .setNextOffset(request.getOffset() + data.length)
        .setEndOfFile(data.length == 0)
        .build();

    observer.onNext(reply);
    observer.onCompleted();
} catch (RangeOutOfBoundsException ex) {
    observer.onError(Status.OUT_OF_RANGE
        .withDescription("Range is outside available data")
        .asRuntimeException());
}
```

This is an illustrative example; RangeOutOfBoundsException, repository, storage, and response mapping belong to the application. In production code, also guard against overflow when computing nextOffset, and define the exact semantics of end_of_file. In a large application, centralize domain exception mapping in an exception mapper/interceptor to keep behavior consistent across methods.

Do not catch every IndexOutOfBoundsException or IllegalArgumentException and return OUT_OF_RANGE. Those exceptions can also be programming bugs or validation errors. Map only when you have confirmed the error is genuinely a request exceeding the data domain published by the contract.

## 7. Changing data and bounds consistency

A range may be valid when the client reads metadata, yet become out of bounds before the server executes the RPC. For example:

1. Client calls GetFileMetadata and receives file size 1,000 bytes.
2. Client prepares to read [900, 1,100).
3. The file is truncated down to 800 bytes.
4. Client calls ReadChunk with the range computed from stale metadata.
5. Server detects the range is no longer valid and returns OUT_OF_RANGE.

If a file can mutate, the API should define snapshot semantics:

- Read against a version/etag received from metadata.
- Accept the latest data as of each call.
- Lock or snapshot the file for the duration of a read session.
- Return the current version so the client can reload metadata and decide again.

For append-only data such as event logs, a sequence that does not exist yet may appear later. The API can return OUT_OF_RANGE for queries past the current sequence, or provide separate long-poll/wait semantics. Do not force clients into tight polling loops if the API can model waiting for new data.

## 8. OUT_OF_RANGE in pagination and cursors

Pagination can have several different semantics:

- Negative page_size or exceeding the published limit: usually INVALID_ARGUMENT or normalized per contract.
- Malformed or undecodable page token: INVALID_ARGUMENT.
- Cursor requesting a sequence outside the retained data window: can be OUT_OF_RANGE.
- Valid page with no items: usually returns OK with an empty list.
- Expired cursor because a snapshot/retention window was purged: status must be documented clearly; OUT_OF_RANGE can fit if the cursor points outside the currently supported data range.

Do not return OUT_OF_RANGE for every empty page. For mutable collections, a page number past the current page count may simply be an empty result under the contract. The status should signal a range error only when the API defines that the caller requested a position required to lie within valid bounds.

Stable cursors are usually better than offset pagination for continuously changing data. If cursors rely on sequences or timestamps, define retention, monotonicity, and behavior when old data is deleted.

## 9. Time ranges and numeric domains

OUT_OF_RANGE can also be used for requests querying time intervals or numeric values outside the supported data domain.

For example:

- An API retains only the last 30 days of telemetry; a client requests a timestamp older than the retention window.
- A computation requests a sample index greater than the number of available samples.
- A report requests a data period not yet generated.
- A client requests a timestamp past the published data boundary in a snapshot.

Distinguish:

| Case | Usually appropriate status/outcome |
| --- | --- |
| start time after end time | INVALID_ARGUMENT |
| Malformed timestamp | INVALID_ARGUMENT |
| Valid time range with no events | OK with an empty list |
| Requested range outside the API's supported retention window | OUT_OF_RANGE |
| Future data not yet created that may appear later | OUT_OF_RANGE or dedicated wait semantics, per contract |

Do not use status codes as a substitute for business rules. For instance, "reporting period not yet opened" can be FAILED_PRECONDITION, whereas "requested sequence exceeds maximum available sequence" can be OUT_OF_RANGE.

## 10. Error details and bounds information

A short description is often not enough for clients to adjust their range on their own. gRPC does not define one specialized standard detail for every kind of OUT_OF_RANGE; an API can use google.rpc.ErrorInfo with a stable reason or a custom Protobuf detail.

Example of logical information:

```text
grpc-status: OUT_OF_RANGE
grpc-message: Range exceeds available data

ErrorInfo:
  reason: "RANGE_OUT_OF_BOUNDS"
  domain: "storage.example"
  metadata:
    requested_offset: "900"
    requested_length: "200"
    available_size: "1000"
```

The metadata above is illustrative only. In gRPC Java, richer details can be packed into com.google.rpc.Status and converted to an exception via io.grpc.protobuf.StatusProto. Do not include internal file paths, other tenants, or sensitive information in details. If bounds change rapidly, state clearly that this is a snapshot at check time rather than a guarantee for subsequent calls.

Clients should rely on stable reasons or detail types rather than parsing grpc-message sentences. If the API must not expose actual sizes or limits, return only a generic status and provide an authorization-protected metadata method.

## 11. Client recovery after OUT_OF_RANGE

When receiving OUT_OF_RANGE, the client must determine the current range and decide whether to adjust the request or wait for data:

1. Read the status and structured details if present.
2. Reload metadata/bounds if the resource can change.
3. Check the version/snapshot to see if metadata still applies.
4. Pick a new valid range, split the request, or wait for data to be created.
5. Re-invoke only when the operation still preserves its business meaning.

Blocking stub example:

```java
try {
    ReadChunkReply reply = fileStub.readChunk(request);
    consume(reply.getData());
} catch (StatusRuntimeException ex) {
    if (ex.getStatus().getCode() == Status.Code.OUT_OF_RANGE) {
        // Reload file metadata, check version, and choose a new range.
    } else {
        // Handle other statuses.
    }
}
```

Do not automatically clamp every range to the current limit. If the client requests [900, 1100) and the server silently returns [900, 1000), the client may mistakenly believe it received all 200 bytes. Return partial results only if the contract explicitly defines how to represent actual bytes received and the next position.

## 12. OUT_OF_RANGE and streaming RPCs

Distinguish two cases:

- Request range is out of bounds from the start: the server can reject the RPC with OUT_OF_RANGE before emitting messages.
- Stream reads sequentially to a natural EOF: this is normally a regular completion; the server calls onCompleted() and the client receives status OK.

For example, ReadFile(offset, length) asks for exactly 500 bytes, but only 200 bytes remain in the file. If the contract requires all 500 bytes, the server can return OUT_OF_RANGE. Conversely, StreamFileFrom(offset) can emit all remaining bytes and finish with OK upon reaching EOF.

With server streaming, if a file is truncated mid-stream, the contract must specify snapshot behavior, partial results, or termination with an error status. The client needs to know whether already-received messages count as valid data or require restarting from a checkpoint.

With bidirectional streaming, each message may request a separate range. If one message goes out of bounds, the API must define whether that error terminates the whole stream or is returned merely as a per-item result.

## 13. Testing OUT_OF_RANGE

Tests should focus on boundaries, state changes, and stream semantics:

| Scenario | What to verify |
| --- | --- |
| Negative offset or negative length | INVALID_ARGUMENT |
| Offset greater than file size | OUT_OF_RANGE |
| Range crosses EOF | Strict/partial behavior matches contract |
| Offset right at EOF, length 0 | Outcome follows empty-range convention |
| Offset right at EOF, positive length | OUT_OF_RANGE if strict read |
| Overflow-prone offset + length | Does not slip past validation |
| File truncated after client reads metadata | Version/bounds checked and right status returned |
| Valid query range with zero records | OK with empty result if semantics is a query |
| Malformed cursor/token | INVALID_ARGUMENT |
| Cursor outside retention window | Status per contract, possibly OUT_OF_RANGE |
| Stream reaches natural EOF | Completes OK, no range error reported |
| Stream truncated mid-transfer | Partial/checkpoint behavior matches contract |

Unit tests verify validators and boundary arithmetic. Integration tests over a gRPC client/server confirm actual statuses and rich details. For file/object storage or databases, tests should simulate size/version changes between reading metadata and calling the range read.

## 14. Observability and operations

Rising OUT_OF_RANGE rates can indicate clients using stale metadata, unstable cursors, changed retention policies, or unclear bounds contracts.

Monitor:

- Count/rate of OUT_OF_RANGE by service/method.
- Range type: byte offset, sequence, page cursor, timestamp, or numeric index.
- Normalized cause categories: negative input, past end, expired retention, stale snapshot.
- Client/SDK versions and resource versions if permitted.
- Success rate after clients reload metadata.
- Partial read, EOF, and stream restart rates.
- Trace/correlation IDs to link the request to the earlier metadata read.

Do not put file IDs, tenant IDs, user IDs, or full cursors into high-cardinality metric labels. Logs can record allowed ranges and bounds, while avoiding leaking internal paths or private data. If bounds could be sensitive, log reason codes and trace IDs instead of specific values.

## 15. Common design mistakes

| Mistake | Consequence | Better practice |
| --- | --- | --- |
| Using INVALID_ARGUMENT for every out-of-bounds range | Clients do not know state changes could make the request valid | Separate invalid values from ranges outside current bounds |
| Returning OUT_OF_RANGE for empty queries | Turns valid results into errors | Return OK with an empty collection when semantically right |
| Not defining inclusive/exclusive bounds | Duplicate reads or skipped elements at boundaries | Publish range conventions and units |
| Computing offset + length without overflow guards | Huge ranges can bypass validation | Use safe comparisons before addition |
| Silently truncating the range | Clients think they received complete data | Strict error or explicitly described partial response |
| Treating natural EOF as OUT_OF_RANGE | Normal streams fail with errors | Complete OK when stream reaches EOF per contract |
| Using stale metadata bounds without version checks | Reads wrong data after truncate/update | Snapshots/versions or server-side bounds validation |
| Retrying the exact same range unchanged | Repeated errors and extra load | Reload bounds, pick a new range, or wait for state change |

## 16. OUT_OF_RANGE design checklist

Before publishing a gRPC method, determine:

1. **What is the valid domain?** Byte offset, index, sequence, timestamp, or page cursor.
2. **What are the boundary conventions?** Inclusive/exclusive, zero-based, length 0.
3. **Which values are INVALID_ARGUMENT?** Negative numbers, wrong formats, or invalid structure.
4. **When is it OUT_OF_RANGE?** Exceeding current bounds or outside retention window.
5. **Can data change?** Snapshots/versions and when bounds are checked.
6. **Strict or partial read?** Responses must express actual amount read and checkpoints.
7. **Is overflow prevented?** Check range arithmetic before accessing the resource.
8. **How do clients recover?** Read fresh metadata, pick another range, or wait for data.
9. **What are the streaming EOF semantics?** Separate natural completion from invalid range requests.
10. **Can telemetry diagnose causes without leaking data?**

## 17. Takeaways

OUT_OF_RANGE is gRPC status code 11, used when a requested position, index, or data range lies outside the currently valid domain. It differs from INVALID_ARGUMENT, which indicates an input value invalid under the contract. A valid query with no results normally still returns OK with an empty collection; a stream reading sequentially to natural EOF also normally completes OK.

In Spring gRPC, publish clear range bounds, units, inclusive/exclusive conventions, and strict/partial semantics. Validate inputs and prevent overflow before accessing data; map domain range exceptions to Status.OUT_OF_RANGE. If bounds can change, use snapshots/versions or let clients reload metadata. Rich error details can describe safe reasons and bounds. Clients should adjust their range rather than retrying the exact request, and streaming must distinguish out-of-bounds range requests from normal EOF. Clear design prevents missing or duplicate reads and helps clients recover properly.

### References

- [gRPC – Status codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC – Error handling](https://grpc.io/docs/guides/error/)
- [Google API – Error model](https://cloud.google.com/apis/design/errors)
- [Google API – Resource-oriented design](https://cloud.google.com/apis/design/resources)
- [Java – Math.addExact](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
