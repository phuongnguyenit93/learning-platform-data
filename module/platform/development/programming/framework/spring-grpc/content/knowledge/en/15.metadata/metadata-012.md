# Testing Required and Optional Metadata

In a Spring gRPC API, metadata can carry information the server needs to process a call, such as a request ID, tenant selection, or locale. Some keys are **required by the application contract**; other keys are **optional** and have default rules when absent. Tests must verify both cases while distinguishing missing metadata from metadata that is present but malformed.

gRPC does not automatically define any custom key as required or optional. That is an API decision. This lesson builds a sample contract for the `GetOrder` RPC: `x-request-id` required for tracing, `x-locale` optional defaulting to `vi-VN`. It then verifies validation, status codes, interceptors, and the actual path over in-process gRPC.

## 1. Write the Contract Clearly Before Writing Tests

A metadata contract must state which keys are accepted, who provides them, data type, value count, format, limits, and how absence is handled.

| Key | Classification | Sample rule | When invalid |
| --- | --- | --- | --- |
| `x-request-id` | Required | One ASCII value, 1–64 chars `[A-Za-z0-9._-]` | `INVALID_ARGUMENT` |
| `x-locale` | Optional | One ASCII value in `vi-VN` or `en-US` | `INVALID_ARGUMENT` |
| `authorization` | Required for security | Credentials verified by the authentication layer | `UNAUTHENTICATED` if missing/invalid |
| Unknown key | Unused by API | Ignore if it does not affect policy; never feed into business logic | Per API/gateway policy |

In this example, if `x-locale` is **absent**, the server selects `vi-VN`. If the key is present yet empty or unsupported, the server returns `INVALID_ARGUMENT`. This rule prevents a client from sending bad data that the server silently treats as absent.

### Required and Optional Do Not Mean Present/Absent in Every Request

- **Required:** client must send the key on every call within the API's scope; server rejects if missing or invalid.
- **Optional:** client may omit the key; server applies the documented default.
- **Optional yet present:** if sent, the value must still be valid. Optional does not mean accepting empty strings or invalid data.
- **Unknown:** new keys or keys unused by the service should not automatically break older clients, unless security policy requires blocking them.

Never use request ID as a credential. If `authorization` is required, validate it via a separate authentication mechanism and preserve the `UNAUTHENTICATED` status; do not lump credential errors together with business metadata format errors.

## 2. Essential Test Matrix

Testing a single successful request does not prove the contract. For each key, test presence, value count, and content.

| Scenario | `x-request-id` | `x-locale` | Expected result |
| --- | --- | --- | --- |
| Minimal sufficient metadata | Valid | Absent | Success; default locale `vi-VN` |
| Explicit metadata | Valid | `en-US` | Success; locale `en-US` |
| Missing required key | Absent | Absent | `INVALID_ARGUMENT` |
| Empty required value | Empty string | Absent | `INVALID_ARGUMENT` |
| Malformed required value | Contains space/newline or too long | Absent | `INVALID_ARGUMENT` |
| Empty optional value | Valid | Empty string | `INVALID_ARGUMENT` per sample contract |
| Unsupported optional value | Valid | `fr-FR` | `INVALID_ARGUMENT` per sample contract |
| Repeated required key | Two values | Absent | `INVALID_ARGUMENT` |
| Repeated optional key | Valid | Two values | `INVALID_ARGUMENT` |
| Missing/invalid credentials | Valid | Any | `UNAUTHENTICATED` at authentication layer |

Beyond the value matrix, tests must verify:

- The service is not invoked when validation fails.
- Validated metadata is placed into the proper `io.grpc.Context`.
- Two concurrent RPCs do not mix up each other's context.
- Clients sending through a real proxy/transport preserve keys per contract.
- Errors do not leak tokens or entire metadata into logs.

## 3. Writing a Separate Validator for Easier Testing

Separating metadata rules from the interceptor allows unit testing without starting a server. `Metadata.getAll(...)` is used to detect duplicate keys; `get(...)` alone only returns the last value and can mask duplicates.

```java
import io.grpc.Metadata;

final class OrderRequestMetadata {
    static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of(
            "x-request-id", Metadata.ASCII_STRING_MARSHALLER);
    static final Metadata.Key<String> LOCALE =
        Metadata.Key.of(
            "x-locale", Metadata.ASCII_STRING_MARSHALLER);

    final String requestId;
    final String locale;

    private OrderRequestMetadata(String requestId, String locale) {
        this.requestId = requestId;
        this.locale = locale;
    }

    static OrderRequestMetadata parse(Metadata headers) {
        String requestId = single(headers, REQUEST_ID);
        String locale = single(headers, LOCALE);

        if (requestId == null
                || !requestId.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid x-request-id");
        }

        if (locale == null) {
            locale = "vi-VN";
        } else if (!locale.equals("vi-VN") && !locale.equals("en-US")) {
            throw new IllegalArgumentException("Unsupported x-locale");
        }

        return new OrderRequestMetadata(requestId, locale);
    }

    private static String single(
            Metadata headers, Metadata.Key<String> key) {
        Iterable<String> values = headers.getAll(key);
        if (values == null) {
            return null;
        }
        java.util.Iterator<String> iterator = values.iterator();
        if (!iterator.hasNext()) {
            return null;
        }
        String value = iterator.next();
        if (iterator.hasNext()) {
            throw new IllegalArgumentException("Repeated metadata key");
        }
        return value;
    }
}
```

`parse(...)` expresses the example's policy: request ID is required, locale is optional, empty values are rejected, and keys may appear only once. In a real API, a BCP 47 parser and a broader list of supported locales may be used; the key point is that contract and tests agree.

## 4. Attaching the Validator to a `ServerInterceptor`

The interceptor turns validation failures into a gRPC status before calling the service. Only validated metadata is placed into context:

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

final class RequiredOptionalMetadataInterceptor
        implements ServerInterceptor {

    static final Context.Key<String> REQUEST_ID =
        Context.key("request-id");
    static final Context.Key<String> LOCALE =
        Context.key("request-locale");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {
        final OrderRequestMetadata parsed;
        try {
            parsed = OrderRequestMetadata.parse(headers);
        } catch (IllegalArgumentException ex) {
            call.close(
                Status.INVALID_ARGUMENT.withDescription(
                    "Invalid request metadata"),
                new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        Context context = Context.current()
            .withValue(REQUEST_ID, parsed.requestId)
            .withValue(LOCALE, parsed.locale);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

The status description returned to the client is kept generic; never include metadata values in errors. Authentication should run in a separate interceptor/security layer so missing or invalid tokens return `UNAUTHENTICATED` instead of `INVALID_ARGUMENT`.

The service can read context once the interceptor allows the call:

```java
String requestId = RequiredOptionalMetadataInterceptor.REQUEST_ID.get();
String locale = RequiredOptionalMetadataInterceptor.LOCALE.get();

// Use requestId for validated log correlation.
// Use locale for localized content per contract.
```

## 5. Unit Tests for Required and Optional Metadata

Unit tests verify the validator case by case. JUnit 5 example:

```java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.Metadata;
import org.junit.jupiter.api.Test;

class OrderRequestMetadataTest {
    @Test
    void requiredKeyMustBePresent() {
        Metadata headers = new Metadata();
        assertThrows(
            IllegalArgumentException.class,
            () -> OrderRequestMetadata.parse(headers));
    }

    @Test
    void optionalLocaleUsesDefaultWhenAbsent() {
        Metadata headers = new Metadata();
        headers.put(OrderRequestMetadata.REQUEST_ID, "req-42");

        OrderRequestMetadata parsed = OrderRequestMetadata.parse(headers);

        assertEquals("req-42", parsed.requestId);
        assertEquals("vi-VN", parsed.locale);
    }

    @Test
    void acceptsSupportedOptionalLocale() {
        Metadata headers = new Metadata();
        headers.put(OrderRequestMetadata.REQUEST_ID, "req-43");
        headers.put(OrderRequestMetadata.LOCALE, "en-US");

        OrderRequestMetadata parsed = OrderRequestMetadata.parse(headers);
        assertEquals("en-US", parsed.locale);
    }

    @Test
    void rejectsEmptyOptionalValueWhenPresent() {
        Metadata headers = new Metadata();
        headers.put(OrderRequestMetadata.REQUEST_ID, "req-44");
        headers.put(OrderRequestMetadata.LOCALE, "");

        assertThrows(
            IllegalArgumentException.class,
            () -> OrderRequestMetadata.parse(headers));
    }

    @Test
    void rejectsRepeatedRequiredKey() {
        Metadata headers = new Metadata();
        headers.put(OrderRequestMetadata.REQUEST_ID, "req-a");
        headers.put(OrderRequestMetadata.REQUEST_ID, "req-b");

        assertThrows(
            IllegalArgumentException.class,
            () -> OrderRequestMetadata.parse(headers));
    }
}
```

Add tests for overly long values, invalid characters, unsupported optional locales, and duplicate optional keys. Validator unit tests do not prove the interceptor is registered or that the service skips execution when rejected; that requires integration tests.

## 6. Integration Testing via In-Process gRPC

To verify the entire path, spin up a test server with the interceptor and a generated stub that can attach metadata. The test service echoes back the context set by the interceptor:

```java
import io.grpc.stub.StreamObserver;

final class MetadataProbeService extends MetadataProbeGrpc.MetadataProbeImplBase {
    @Override
    public void inspect(
            MetadataProbeRequest request,
            StreamObserver<MetadataProbeReply> observer) {
        String id = RequiredOptionalMetadataInterceptor.REQUEST_ID.get();
        String locale = RequiredOptionalMetadataInterceptor.LOCALE.get();
        observer.onNext(MetadataProbeReply.newBuilder()
            .setRequestId(id)
            .setLocale(locale)
            .build());
        observer.onCompleted();
    }
}
```

In the test, register the service via `ServerInterceptors.intercept(...)`, call via `InProcessChannelBuilder`, and create a stub with `MetadataUtils.newAttachHeadersInterceptor(headers)`. Two success cases to verify:

1. Sending only `x-request-id`: response carries the corresponding request ID and default locale `vi-VN`.
2. Sending both `x-request-id` and `x-locale: en-US`: response carries locale `en-US`.

For failure cases, send a request missing request ID or with an invalid locale; assert `StatusRuntimeException` with code `INVALID_ARGUMENT`. Also use a counter in the test service to verify the method is never invoked when the interceptor rejects the call.

`InProcessServerBuilder` and `InProcessChannelBuilder` test gRPC/interceptor logic within the same process. They do not fully emulate TLS, HTTP/2 proxies, gateway header filtering, or production header limits.

## 7. Compatibility Testing When Contracts Change

The metadata contract is also part of client–server compatibility. When adding a new key:

- **Adding an optional key:** generally more compatible if older servers ignore unknown keys and newer servers have clear defaults.
- **Adding a required key:** can immediately reject older clients upon deploying a new server. Requires versioning, phased rollouts, or fallback mechanisms.
- **Renaming a key:** equivalent to a contract change; consider a transition window supporting both old and new names.
- **Changing value format:** must test clients and servers across different versions.
- **Changing defaults:** can alter behavior even without changing sent metadata; treat it as an API change.

Compatibility testing should cover old clients calling new servers, new clients calling old servers, and mixed versions running side by side during rollouts. Never turn an optional metadata key into a required one without a migration plan.

## 8. Practice Exercise

An `OrderService.GetOrder` requires `x-request-id` and accepts an optional `x-locale`. The development team wants to change the default locale from `vi-VN` to `en-US` in the next release.

**Requirements:**

1. Write the contract for both keys, including types, formats, value counts, and behavior when absent.
2. Add unit tests for missing, empty, malformed, duplicate, and supported values.
3. Write an integration test proving the service does not execute when required metadata is invalid.
4. Verify missing optional metadata produces the right default and valid values are preserved.
5. Propose how to roll out the default change without surprising older clients.
6. Add a separate authentication test so missing/invalid credentials return `UNAUTHENTICATED`, never confused with metadata errors.

**Self-check questions:**

- Why can absent optional metadata use a default while an empty value is still rejected?
- Why is `getAll(...)` needed when a key must appear exactly once?
- What do validator unit tests fail to prove about the interceptor and service?
- Why can adding required metadata break older clients?
- When should `INVALID_ARGUMENT` be returned versus `UNAUTHENTICATED`?
- Why should request ID metadata never be used as an authentication mechanism?

**Key takeaway:** Metadata testing must follow each key's contract: required vs. optional, format, value count, and defaults. Test valid cases as well as missing, invalid, and duplicate cases; use unit tests for validators and integration tests to prove interceptors, statuses, and services work properly. When changing contracts—especially turning an optional key into a required one or changing defaults—run compatibility tests across client/server versions.
