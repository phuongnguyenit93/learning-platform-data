# Adding New Fields Without Breaking Old Clients in Spring gRPC

A gRPC service often has multiple client versions running concurrently: web apps update quickly, mobile apps can remain on user devices for months, and partner integrations follow their own release schedules. Consequently, adding a field to a Protocol Buffers file is more than editing a schema and regenerating Java code. You must ensure new servers still understand old requests and old clients can still process new responses.

The core principle: **assign a new field number, preserve the semantics of published fields, and define behavior when the new field is absent**. Compatibility at the wire layer is a necessary condition; business validation and deployment order must also be compatible.

This lesson focuses on extending an in-use Spring gRPC contract. The running example is the **GetProduct** RPC: we add a locale option to the request and a short description to the response, then examine how old and new clients and servers interpret the data.

## 1. The Problem: Multiple Versions Calling One RPC

The first version of the catalog service has this contract:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_package = "com.myshop.grpc.catalog.v1";
option java_multiple_files = true;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
}

message Product {
  string product_id = 1;
  string display_name = 2;
}

message GetProductResponse {
  Product product = 1;
}
```

After v1 clients are released, the team wants to support display locales and short descriptions. The extended contract can add:

```proto
message GetProductRequest {
  string product_id = 1;
  optional string locale = 2;
}

message Product {
  string product_id = 1;
  string display_name = 2;
  string short_description = 3;
}
```

In this example, **locale** is optional; if an old client omits it, the server uses the published default locale. **short_description** is an additional field in the response; old clients do not need to access it to keep displaying product IDs and names.

This is usually a compatible extension at the binary protobuf layer. However, if the new server immediately requires a non-empty locale upon rollout, v1 clients will be rejected. Conversely, if a new client depends on short_description yet its request is routed to an old server, the client may receive incomplete data. **Safely adding fields requires both absent-field handling and a versioned rollout strategy.**

## 2. Compatibility Has Multiple Directions

When calling a schema change compatible, specify which client/server pairs must keep working:

| Scenario | Typical binary protobuf behavior | What must be guaranteed |
| --- | --- | --- |
| **Old client → new server** | Client omits the new field; server reads the default value or absent state if presence is tracked | New server has a safe fallback for old requests |
| **New client → old server** | Old server does not know the new field and usually ignores unknown fields | New client must not assume the old server applied that field |
| **New server → old client** | Old client reads known fields and ignores unknown response fields | Old client keeps working without using the additional field |
| **Old server → new client** | New client sees the new field as absent | New client has a fallback or avoids invoking features the server does not yet support |

In this lesson:

- **Backward compatibility:** new servers continue accepting requests from old clients.
- **Forward compatibility:** old clients continue processing responses from new servers.

These two properties do not arise automatically just because a proto file compiles cleanly. Validation, business logic, ProtoJSON, and rollout order also shape the outcome.

### An Unknown Field Does Not Mean It Was Processed

A new client may send:

```text
GetProductRequest {
  product_id: "P-100"
  locale: "vi-VN"
}
```

If this request reaches an old server that lacks the locale field, the binary protobuf parser typically skips field number 2 because the server's schema does not recognize it. The RPC may still return **OK**, yet the server **never used** vi-VN. The client cannot infer from an OK status that the locale was applied.

In particular, if a new field affects pricing, access control, taxes, or transaction state, having an old server ignore it can produce wrong results. Deploy server support before clients depend on that field.

## 3. Field Numbers Are Wire Identifiers

Protocol Buffers encodes each field with a key composed of **field number** and **wire type**. The name product_id helps schema readers and generated code, but is not sent as a property name in binary protobuf. When decoding, the runtime uses the field number to identify the field.

When adding a field:

1. Assign a new field number never previously used in that message.
2. Keep the field number and type of every published field unchanged.
3. Never renumber existing fields to tidy up the schema.
4. Never reuse removed numbers or names; mark them with reserved.
5. Never assume two types with the same wire type are semantically compatible.

Example:

```proto
message Product {
  string product_id = 1;
  string display_name = 2;
  string short_description = 3; // New field, previously unused number.
}
```

A v1 client knows only fields 1 and 2. When receiving field 3 in a binary response, the old runtime can skip the unknown field; the old app still reads product ID and name. A new client talking to an old server will see field 3 as absent and must handle the default value.

Field numbers 1 through 15 have smaller key encodings, typically saving bytes for frequently populated fields. You can favor this range when designing new schemas, but **never renumber an already-published field merely to save bytes**.

### Reserve Deleted Fields

If field 3 used to be short_description and was removed, protect both its number and name:

```proto
message Product {
  reserved 3;
  reserved "short_description";

  string product_id = 1;
  string display_name = 2;
}
```

Do not delete the old declaration and assign number 3 to manufacturer_id. Payloads persisted from an earlier version may contain tag 3; reusing it can cause old data to be decoded with a brand-new meaning.

## 4. Choosing Presence and Fallbacks for New Fields

For locale, a regular scalar works if an empty string and absence mean the same thing:

```proto
message GetProductRequest {
  string product_id = 1;
  string locale = 2;
}
```

In proto3, regular string scalars have no separate presence tracking; when omitted, the getter returns an empty string. The server treats an empty string as using the default locale.

If you need to distinguish "not sent" from "intentionally sent an empty string", use optional:

```proto
message GetProductRequest {
  string product_id = 1;
  optional string locale = 2;
}
```

Generated Java code can check:

```java
String locale;
if (!request.hasLocale()) {
    // Old client, or new client not requesting a specific locale.
    locale = resolveDefaultLocale(request.getProductId());
} else {
    // When supplied, validate both blank strings and format.
    locale = normalizeAndValidateLocale(request.getLocale());
}
```

If a client sends an empty string, hasLocale() is true; the server can reject it with INVALID_ARGUMENT or assign a specific meaning. That rule must be documented in the contract.

There is no need to add optional to every field just to make it look "stricter". For instance, product_id is a plain scalar yet the server can still reject blank strings:

```java
if (request.getProductId().isBlank()) {
    throw Status.INVALID_ARGUMENT
            .withDescription("product_id must not be blank")
            .asRuntimeException();
}
```

This rejects both an old request missing product_id and a request explicitly sending a blank string, provided both cases share the same business meaning.

### New Fields in Responses

Adding short_description = 3 to Product does not force old clients to change:

```proto
message Product {
  string product_id = 1;
  string display_name = 2;
  string short_description = 3;
}
```

A v1 client lacks getShortDescription(), yet still reads ID and name. A new client calling an old server sees field 3 as absent; the getter returns an empty string. If the description is merely a UI enhancement, the client can hide the description section. If a feature cannot function when the field is absent, the client must verify server support before relying on it.

## 5. Changes Often Mistaken for Compatible

| Change | Assessment | Reason |
| --- | --- | --- |
| Adding a new field with a new number and safe fallback | Usually compatible with binary protobuf | Old clients neither send nor read the new field |
| Renaming a field while keeping number and type | May be binary-compatible, yet affects source code and JSON | Java accessors, default JSON keys, and descriptors change |
| Changing a published field number | Incompatible | Old data may be decoded as a different field |
| Changing an existing field's type | High risk, usually semantically incompatible | Wire type may change; even when unchanged, interpretation may differ |
| Reusing a deleted field's number or name | Unsafe | Clients holding persisted old data can misinterpret it |
| Adding a branch to a published oneof | Requires careful evaluation | Old clients may see the oneof as unset when the server sends the new branch |
| Adding an enum value | Must check old consumers | Old clients may receive an unknown enum value |

**Do not change int32 to int64 just because both commonly use varint.** Value ranges and application behavior differ. Do not change string to bytes merely because both share the length-delimited wire type. When a type or semantics change, adding a new field or creating a new API version is usually safer.

### New Enum Values

Suppose PRODUCT_STATUS_ARCHIVED = 4 is added to a response enum. Old clients can receive the number 4 without having a matching enum constant. In proto3 Java, the enum getter can return UNRECOGNIZED while the integer getter preserves the raw value:

```java
ProductStatus status = response.getStatus();
int rawValue = response.getStatusValue();

if (status == ProductStatus.UNRECOGNIZED) {
    // Do not infer an unknown status as ACTIVE or DELETED.
    handleUnknownStatus(rawValue);
}
```

Do not add a new enum value if old clients will make dangerous decisions upon encountering an unrecognized state. Design a safe default branch and test against older generated code.

### Extending `oneof`

Suppose the published schema has:

```proto
message PaymentMethod {
  oneof method {
    CardPayment card = 1;
    BankTransfer bank_transfer = 2;
  }
}
```

A new server adds branch wallet = 3. When the server sends this branch, an old client knows only card and bank_transfer; it may observe getMethodCase() as having no branch set. If old logic treats NOT_SET as card payment or triggers an unsafe fallback, behavior breaks.

Before extending a oneof, verify whether old clients can safely ignore the new choice, whether an unknown branch could be mistaken for a valid state, and whether a new RPC or response version is needed instead. oneof guarantees at most one branch within the schema in use; it does not ensure every client version knows about future branches.

## 6. Binary Protobuf and ProtoJSON Have Different Rules

The unknown-field behavior above applies to **binary protobuf**. If the API is also accessed via a JSON gateway, ProtoJSON, or custom clients, evaluate them separately:

- New fields in JSON typically use lowerCamelCase names, such as shortDescription.
- An old client's JSON parser may reject unknown keys depending on library and configuration. Never assume every JSON parser ignores unknown keys.
- Renaming a field or changing json_name can break JSON clients even when the binary field number stays unchanged.
- For 64-bit numeric types like int64, ProtoJSON maps them to decimal strings per standard rules; do not convert them to JSON numbers and assume every client parses them identically.
- If using HTTP transcoding, verify routes, body mappings, and gateway behavior when the new field is absent.

Therefore, when calling a field addition "compatible", specify which client types must remain supported: binary gRPC stubs, dynamic protobuf, JSON gateways, or applications reading schemas via reflection.

## 7. Deploy Servers First, Clients Second

Suppose multiple server instances sit behind a load balancer. If new clients begin sending locale while some instances still run the old server, requests may be handled inconsistently depending on which instance serves them. One request hits a new server and gets localized; the next hits an old server and falls back to the default locale.

Recommended rollout sequence:

1. **Design the field and fallback.** Assign a new number, define absent behavior, and keep old field semantics intact.
2. **Deploy compatible servers.** Every instance recognizes the new field; requests missing the field still follow legacy rules.
3. **Verify the fleet.** Confirm no old server instances still receive traffic for the new feature; monitor errors and fallback rates.
4. **Deploy new clients.** Clients begin sending the new field; enable behaviors dependent on the field only once server support is confirmed.
5. **Review API lifecycle.** If the field must later become mandatory, publish v2 or a new endpoint when v1 cannot preserve compatible behavior.

Server-first rollout works only if every server instance is upgraded before clients rely on the field. In multi-region or partner environments, you may need capability negotiation, version-based routing, or feature flags.

### Do Not Use Fake Defaults to Mask Missing Data

If locale is absent, defaulting to en-US may be reasonable if that is already the established convention. Yet if the new field is tax_region and affects tax amounts, picking an arbitrary default can produce incorrect invoices. When no safe derivation exists, preserve v1 behavior using legacy data, require clients to migrate to v2, or reject the new feature on the legacy endpoint. Compatibility never means accepting wrong results.

## 8. Java Example in a Spring gRPC Server

After generating Java code from the extended schema, GetProductRequest exposes hasLocale() and getLocale(). The handler can preserve legacy behavior when the client omits the field:

```java
package com.myshop.server.catalog;

import com.myshop.grpc.catalog.v1.CatalogServiceGrpc;
import com.myshop.grpc.catalog.v1.GetProductRequest;
import com.myshop.grpc.catalog.v1.GetProductResponse;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class CatalogGrpcEndpoint
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    private final CatalogApplicationService catalog;

    public CatalogGrpcEndpoint(CatalogApplicationService catalog) {
        this.catalog = catalog;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<GetProductResponse> observer) {
        if (request.getProductId().isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("product_id is required")
                    .asRuntimeException());
            return;
        }

        final String locale;
        if (!request.hasLocale()) {
            locale = catalog.defaultLocaleFor(request.getProductId());
        } else if (request.getLocale().isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("locale must not be blank when supplied")
                    .asRuntimeException());
            return;
        } else {
            locale = catalog.validateLocale(request.getLocale());
        }

        GetProductResponse response =
                catalog.getProduct(request.getProductId(), locale);
        observer.onNext(response);
        observer.onCompleted();
    }
}
```

CatalogApplicationService represents application logic supplied by the project. The example assumes it raises appropriate domain errors when a product does not exist or a locale is unsupported; exception-to-gRPC-status mapping must be implemented consistently. The @GrpcService annotation and server configuration must match the Spring gRPC version in use.

Compatibility rests on the !request.hasLocale() branch: old clients that omit the field still receive the default behavior. Do not rely on getLocale().isBlank() as the sole check when presence carries distinct semantics.

## 9. Testing Client/Server Combinations

A test that merely generates code from the new schema and calls the new server does not prove compatibility. Test all combinations:

| Client | Server | Case | Expected outcome |
| --- | --- | --- | --- |
| v1 | v1 | Baseline behavior | Same result preserved |
| v1 | new | Request lacks new field | New server applies fallback without rejecting merely for the missing field |
| new | new | Valid new field | Server applies field properly |
| new | new | Malformed new field | Server returns appropriate validation status |
| new | old | Request includes new field | Confirm old server can ignore it; client does not assume field took effect |
| old | new | Response includes new field | Old client reads old fields and keeps working |
| old | new | New enum/oneof branch | Unknown value does not trigger unsafe behavior |
| Old JSON | new gateway | Response includes new JSON key | Verify old parser and ignore-unknown-fields config |

### Wire Testing With a v1 Fixture

You can persist a binary request produced by v1-generated classes and parse it using v2 classes:

```java
// oldRequest was built using the generated class from the v1 schema.
byte[] bytesV1 = oldRequest.toByteArray();

// This GetProductRequest is generated from the v2 schema.
GetProductRequest parsedByV2 =
        GetProductRequest.parseFrom(bytesV1);

assertEquals("P-100", parsedByV2.getProductId());
assertFalse(parsedByV2.hasLocale());
```

This is a wire-level check at the message boundary. End-to-end tests must also invoke the new server using a real v1 client to verify that handlers, validation, authentication, and gRPC status codes all behave as promised. Conversely, test a v2 client calling an old server to verify the client does not depend on fields the old server does not yet support.

Tests should cover:

- New field absent, new field with a valid value, and new field explicitly set to its default value.
- Old client parsing the new response and continuing to use existing fields.
- New client talking to an old server; ignored fields do not cause wrong application decisions.
- Mixed-version server instances serving traffic simultaneously during rollout.
- ProtoJSON/HTTP gateway if the API supports JSON.
- Enums and oneofs when new values or branches appear.

## 10. When Should You Create `v2`?

Adding fields to v1 is usually appropriate when the new data is optional or has a safe fallback, old clients can ignore new response fields, and old servers ignoring new request fields do not corrupt results.

Consider a v2 RPC or package when:

- The new field must be present for correct execution, yet old clients cannot send it and the server cannot safely infer it.
- An existing field changes meaning, type, or validation in a way that breaks legacy behavior.
- Old clients cannot handle a new enum/oneof branch and lack a safe fallback.
- The new response has a fundamentally different structure that cannot be extended without misleading consumers.

Do not create v2 for every new field. Overly frequent versioning multiplies endpoints and operational overhead. Extend v1 when semantics stay intact; create a new version when the old contract can no longer satisfy requirements accurately.

## 11. Pre-Merge Review Checklist

- [ ] The new field uses a number never previously used in the message.
- [ ] No existing field's number, type, or meaning has changed.
- [ ] If a field was deleted, both its number and name are marked reserved.
- [ ] Choice between plain scalar and optional reflects actual presence requirements.
- [ ] The new server defines clear behavior when the field is absent.
- [ ] The new field is not made mandatory on an existing RPC if old clients cannot send it yet.
- [ ] New clients have a fallback when an old server returns a response missing the field.
- [ ] New enum values and oneof branches have been evaluated against old consumers.
- [ ] ProtoJSON/HTTP gateways have been tested separately from binary protobuf.
- [ ] Server-first rollout has a way to verify all instances support the field before enabling clients.
- [ ] Tests use both old and new fixtures/stubs, covering absent, default, and invalid cases.
- [ ] Metrics avoid logging sensitive data while tracking new-field adoption and compatibility errors.

**Self-Check**

**Question 1.** You add optional string locale = 2 to a request. A v1 client omits it. How should the v2 server handle this?

*Answer:* Check hasLocale(). When absent, use the published fallback or legacy behavior. Validate locale format only when the client actually sent it.

**Question 2.** A new client sends locale to an old server and receives OK. Can you conclude the response was localized?

*Answer:* No. The old server may ignore unknown fields. Deploy supporting servers first and do not enable client behavior that depends on the feature while old servers remain in the fleet.

**Question 3.** You removed field number 3. Can you reuse number 3 for a new field?

*Answer:* No. Mark number 3 and the old name as reserved to prevent old payloads from being decoded with the wrong meaning.

**Question 4.** A new value is added to a response enum. What should an old Java client do upon receiving an unrecognized value?

*Answer:* Handle the UNRECOGNIZED branch or unknown numeric value with a safe policy; never map it to an old state with a different meaning.

**Question 5.** When should you create shop.catalog.v2?

*Answer:* When you cannot preserve correct behavior for v1 clients via optional fields/fallbacks, or when structural/semantic changes would mislead old clients. If you are only adding optional data that old clients can safely ignore, you can keep extending v1.

Adding fields safely is not just about keeping protoc compiling cleanly. You must preserve how old clients interpret data, define behavior when fields are absent, and deploy server support before clients rely on new capabilities.
