# Tenant ID and Locale

In a **Spring gRPC** system serving multiple organizations or multiple languages, the same RPC method may process data belonging to different **tenants** and return content tailored to the caller's **locale**. Both pieces of information are commonly passed via gRPC **metadata**, yet they carry very different meanings:

- **Tenant ID** identifies the organizational scope or data space being requested. It directly relates to data isolation and access control.
- **Locale** expresses language selection and regional conventions for translating messages and formatting numbers, dates, or units. It relates to user experience and presentation.

For example, a client calls `OrderService.GetOrder` with `x-tenant-id: shop-a` and `x-locale: vi-VN`. The server must verify that the caller has permission to access `shop-a` before querying the order; only then does it use `vi-VN` to choose display messages. **A metadata header sent by the client is not proof of permission to access a tenant.**

This lesson focuses on how to use gRPC metadata and Java interceptors in the Spring ecosystem, connecting them to authentication, deadlines, status codes, TLS, and integration testing.

**Learning objectives:**

1. Distinguish tenant identity, tenant selection, and locale preference.
2. Choose key names, ASCII values, and validation rules for `x-tenant-id`, `x-locale`, or `accept-language`.
3. Propagate per-RPC information via `Metadata` and `ClientInterceptor`.
4. Build a `ServerInterceptor` that validates the tenant against an authenticated identity, then passes context via `io.grpc.Context`.
5. Resolve locales using Java's `Locale`, apply fallback languages, and avoid confusing locale with time zone or currency.
6. Ensure data isolation across RPCs, streaming, and asynchronous processing; design safe testing and observability.

## 1. Tenant and Locale Solve Two Different Problems

Consider a multi-store e-commerce platform where each store is a tenant:

| Data | Example | Purpose | Can it be trusted directly from the client? |
| --- | --- | --- | --- |
| Tenant ID | `shop-a` | Identifies the organization's data space, configuration, or policy | **No**; must cross-check identity and permissions |
| User identity | `user-17` | Identifies the calling user or service | Trust only after authentication |
| Locale | `vi-VN` | Selects translations and formatting conventions | Can be treated as a *preference*, after format validation |
| Time zone | `Asia/Ho_Chi_Minh` | Converts timestamps for display | Separate from locale |
| Currency | `VND` | Specifies currency type or pricing rules | Separate from locale and requires business policy |

A user may belong to multiple tenants. For instance, `user-17` is a member of both `shop-a` and `shop-b`. When sending `x-tenant-id: shop-b`, the user is **proposing the active tenant to operate on**, while the server must verify they have access to `shop-b` and permissions for the requested resource.

Conversely, `x-locale: en-US` only indicates a preference for English using United States conventions. A user in Vietnam can still choose `en-US`; locale **does not determine nationality, physical location, or tenant**.

### Tenant Isolation Is Not Just UI Filtering

The server must constrain every data read/write to the verified tenant. For example, when fetching an order:

```sql
SELECT id, status, total_amount
FROM orders
WHERE tenant_id = :verifiedTenantId
  AND id = :requestedOrderId;
```

This illustrates the query filter; a real system must also check order-level permissions, roles, and related policies. Simply attaching `x-tenant-id` to logs, or hiding another tenant's orders in the client UI, **does not provide data isolation**.

## 2. Designing the Metadata Keys

The names `x-tenant-id` and `x-locale` are **application-defined conventions**, not mandatory headers in the gRPC specification. Different names can be chosen, provided client, server, gateway, and observability systems agree on them.

| Key | Value type | Example | Suggested usage |
| --- | --- | --- | --- |
| `x-tenant-id` | ASCII string | `shop-a` | Specifies the desired tenant in a multi-tenant application |
| `x-locale` | ASCII string | `vi-VN` | Specifies **a single** BCP 47 locale |
| `accept-language` | ASCII string | `vi-VN,vi;q=0.9,en-US;q=0.7` | Expresses a weighted list of preferred languages |
| `authorization` | ASCII string | `Bearer <token>` | Carries credentials for the server to authenticate the caller |
| `x-correlation-id` | ASCII string | `corr-42` | Correlates logs across RPCs of the same task |

These keys are **ASCII** metadata, so use `Metadata.ASCII_STRING_MARSHALLER`. The `-bin` suffix is only for values that are genuinely raw binary bytes; do not encode a short tenant ID or locale as binary metadata.

**Naming rules:** use lowercase with valid gRPC metadata characters; do not define custom keys starting with `grpc-` because that prefix is reserved for the protocol. Avoid stuffing emails, user names, or long JSON strings into metadata.

### Choosing `x-locale` or `accept-language`?

- Use `x-locale` if the internal contract expects the client to have selected **one specific locale**, such as `vi-VN`.
- Use `accept-language` if the client describes a **list of acceptable languages**, possibly with `q` weights. The server must perform language negotiation.
- If accepting both keys, define a clear **precedence order**, e.g., `x-locale` from an internal client takes priority over `accept-language`; do not let conflicting values result in unpredictable behavior.

`accept-language` is not a single BCP 47 language tag. **Do not pass the entire string** `"vi-VN,vi;q=0.9,en-US;q=0.7"` into `Locale.forLanguageTag(...)` and treat it as a single locale.

## 3. Tenant ID Format and Trust Rules

There is no single mandatory tenant ID format across all Spring gRPC applications. Some systems use UUIDs, organization codes, or opaque internal identifiers. An illustrative convention uses 1 to 64 ASCII characters consisting of letters, digits, `-`, and `_`:

```text
Valid per illustrative policy: shop-a, tenant_07, 9d5b7e2c
Invalid:                       shop a, shop-a\nadmin, abnormally long string
```

This rule only checks **format**. A well-formed `x-tenant-id: shop-a` is still caller-supplied data; you cannot assume the caller has access to `shop-a`.

Separate this into three steps:

1. **Authenticate the caller:** the server verifies the bearer token, mTLS service identity, or configured identification mechanism.
2. **Select and verify the tenant:** if the caller can belong to multiple tenants, read the requested tenant ID and cross-check tenant membership, scopes, roles, and policies.
3. **Resource authorization:** when executing `GetOrder(orderId)`, verify that the `orderId` record belongs to the accepted tenant and that the caller is allowed to read it.

Another model does not allow the client to pick a tenant, instead **deriving the tenant from a verified claim** in the token or a server-side service account mapping. In that case, prefer that trusted tenant identity; never let a custom header override it.

| Scenario | Reasonable decision |
| --- | --- |
| Token only permits `shop-a`, client sends `shop-a` | Proceed to per-operation permission checks |
| Token only permits `shop-a`, client sends `shop-b` | Deny access, typically `PERMISSION_DENIED` |
| Caller is unauthenticated | `UNAUTHENTICATED` |
| Tenant header missing on an RPC requiring tenant selection | `INVALID_ARGUMENT` or documented default rule |
| Tenant ID has invalid characters or multiple values | `INVALID_ARGUMENT` |
| Client only knows one tenant, tenant derivable from trusted principal | `x-tenant-id` may not be needed |

Do not return messages distinguishing "this tenant exists but you lack access" from "tenant does not exist" if doing so leaks organizational information. Error codes and descriptions must align with your data disclosure policy.

## 4. Locale and BCP 47 Language Tags

In Java, `java.util.Locale` represents information such as language, region, and script. In metadata, **BCP 47 language tags** can be used, for example:

| Tag | Meaning |
| --- | --- |
| `vi` | Vietnamese, no country specified |
| `vi-VN` | Vietnamese, Vietnam region |
| `en-US` | English, United States region |
| `en-GB` | English, United Kingdom region |
| `zh-Hant-TW` | Chinese using Traditional script, Taiwan region |

Trying conversion:

```java
import java.util.Locale;

Locale vi = Locale.forLanguageTag("vi-VN");
Locale en = Locale.forLanguageTag("en-US");

System.out.println(vi.getLanguage()); // vi
System.out.println(vi.getCountry());  // VN
System.out.println(en.toLanguageTag()); // en-US
```

**Note:** `Locale.forLanguageTag(...)` may normalize or ignore invalid segments instead of always throwing an exception. If input comes from a client and requires strict validation, check format, length, and match against the **set of locales supported by the application**.

### Locale Is Not Time Zone

`vi-VN` does not uniquely specify a time zone for all users. A locale can select date display formatting, but interpreting a timestamp requires separate time zone information, such as `Asia/Ho_Chi_Minh`. For monetary data, `VND`, `USD`, and pricing rules are independent business choices.

In Protobuf APIs, timestamps should have unambiguous temporal semantics, such as `google.protobuf.Timestamp` representing an absolute instant. The server can return structured timestamps and currency codes, while locale-based presentation can happen on the client. Only localize returned text directly on the server when the API contract requires it.

## 5. Resolving Locale and Fallback Languages

Suppose a service only supports `vi-VN` and `en-US`. An illustrative policy:

1. If the client sends `x-locale` matching the supported set, use it.
2. If `x-locale` is missing but `accept-language` is present, choose the best matching locale.
3. If no suitable match exists, use the **service's** default locale, e.g., `vi-VN`.
4. If the organization has its own default locale setting, apply a precedence rule after verifying the tenant, e.g., user choice → tenant setting → service default.

Example selector from a validated `x-locale`:

```java
import java.util.Locale;

public final class SupportedLocales {
    public static final Locale VI_VN = Locale.forLanguageTag("vi-VN");
    public static final Locale EN_US = Locale.forLanguageTag("en-US");

    private SupportedLocales() {}

    public static Locale resolve(String localeTag) {
        if (localeTag == null || localeTag.isBlank()) {
            return VI_VN;
        }
        String normalized = Locale.forLanguageTag(localeTag).toLanguageTag();
        if ("vi-VN".equalsIgnoreCase(normalized) || "vi".equalsIgnoreCase(normalized)) {
            return VI_VN;
        }
        if ("en-US".equalsIgnoreCase(normalized) || "en".equalsIgnoreCase(normalized)) {
            return EN_US;
        }
        return VI_VN; // Service fallback; can be overridden per tenant policy.
    }
}
```

For `accept-language`, Java provides an API to parse weighted language ranges:

```java
import java.util.List;
import java.util.Locale;

String acceptLanguage = "en-GB,en;q=0.9,vi-VN;q=0.8";
List<Locale.LanguageRange> preferences =
    Locale.LanguageRange.parse(acceptLanguage);

List<Locale> supported = List.of(
    Locale.forLanguageTag("vi-VN"),
    Locale.forLanguageTag("en-US")
);

Locale selected = Locale.lookup(preferences, supported);
if (selected == null) {
    selected = Locale.forLanguageTag("vi-VN");
}
```

Remember to validate input strings and catch `IllegalArgumentException` from the parser per policy. `Locale.lookup` runs a matching algorithm and does not guarantee every request yields a result. The example above only illustrates handling acceptable languages; it does not imply `en-GB` has full translations or automatically becomes `en-US` in every case.

Never call `Locale.setDefault(...)` per RPC: that mutates JVM-wide default state and can cause one tenant's request to affect others. Pass `Locale` scoped to the call.

## 6. Client Interceptor: Sending Tenant and Locale per RPC

A Java/Spring gRPC application can attach both values to a stub via `CallOptions`. The interceptor reads the options when an RPC starts and writes headers using `io.grpc.Metadata`. This avoids placing User A's tenant/locale onto a singleton stub reused for User B.

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.Locale;

public final class TenantLocaleClientInterceptor implements ClientInterceptor {

    public static final CallOptions.Key<String> TENANT_OPTION =
        CallOptions.Key.create("active-tenant-id");
    public static final CallOptions.Key<Locale> LOCALE_OPTION =
        CallOptions.Key.create("active-locale");

    private static final Metadata.Key<String> TENANT_HEADER =
        Metadata.Key.of("x-tenant-id", Metadata.ASCII_STRING_MARSHALLER);
    private static final Metadata.Key<String> LOCALE_HEADER =
        Metadata.Key.of("x-locale", Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate = next.newCall(method, callOptions);
        return new ForwardingClientCall.SimpleForwardingClientCall<ReqT, RespT>(
                delegate) {
            @Override
            public void start(
                    ClientCall.Listener<RespT> listener,
                    Metadata headers) {

                String tenantId = callOptions.getOption(TENANT_OPTION);
                Locale locale = callOptions.getOption(LOCALE_OPTION);

                if (tenantId != null) {
                    headers.put(TENANT_HEADER, tenantId);
                }
                if (locale != null) {
                    headers.put(LOCALE_HEADER, locale.toLanguageTag());
                }
                super.start(listener, headers);
            }
        };
    }
}
```

Applying this to a stub generated from `.proto`:

```java
import java.util.Locale;

OrderServiceGrpc.OrderServiceBlockingStub baseStub =
    OrderServiceGrpc.newBlockingStub(channel)
        .withInterceptors(new TenantLocaleClientInterceptor());

OrderServiceGrpc.OrderServiceBlockingStub requestStub =
    baseStub
        .withOption(TenantLocaleClientInterceptor.TENANT_OPTION, "shop-a")
        .withOption(
            TenantLocaleClientInterceptor.LOCALE_OPTION,
            Locale.forLanguageTag("vi-VN"));

// requestStub.getOrder(...) sends x-tenant-id and x-locale.
```

`OrderServiceGrpc`, `channel`, and `getOrder(...)` are illustrative names; in real projects, use the stub and methods generated by Protobuf.

**Key point:** the client sends a *tenant selection*, not proof of that selection. Credentials must be supplied via an appropriate authentication mechanism, such as `CallCredentials`, and the server is responsible for verification. The interceptor above does not attach tokens or trace context on its own.

If you need to pass an inbound call's tenant ID to a downstream call, use only the **server-verified tenant ID**, never forward a raw `x-tenant-id` from a public client.

## 7. Server Interceptor: Authenticating Caller and Controlling Tenant Access

A server receives two types of data with different trust levels: tenant must be tied to an **authenticated principal**, whereas locale is a negotiable preference. The example below illustrates an interceptor using an application-provided `IdentityVerifier` to avoid assuming the tenant header alone suffices for authorization.

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Iterator;
import java.util.Locale;

public final class TenantLocaleServerInterceptor implements ServerInterceptor {

    private static final Metadata.Key<String> TENANT_HEADER =
        Metadata.Key.of("x-tenant-id", Metadata.ASCII_STRING_MARSHALLER);
    private static final Metadata.Key<String> LOCALE_HEADER =
        Metadata.Key.of("x-locale", Metadata.ASCII_STRING_MARSHALLER);

    public static final Context.Key<String> VERIFIED_TENANT =
        Context.key("verified-tenant-id");
    public static final Context.Key<Locale> REQUEST_LOCALE =
        Context.key("request-locale");

    private final IdentityVerifier identityVerifier;

    public TenantLocaleServerInterceptor(IdentityVerifier identityVerifier) {
        this.identityVerifier = identityVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        final String requestedTenant;
        final String requestedLocale;
        try {
            requestedTenant = getSingleValue(headers, TENANT_HEADER);
            requestedLocale = getSingleValue(headers, LOCALE_HEADER);
        } catch (IllegalArgumentException ex) {
            return reject(call, Status.INVALID_ARGUMENT, "Duplicate metadata");
        }

        if (requestedTenant == null
                || !requestedTenant.matches("[A-Za-z0-9_-]{1,64}")) {
            return reject(call, Status.INVALID_ARGUMENT, "Invalid tenant selection");
        }
        if (requestedLocale != null && requestedLocale.length() > 64) {
            return reject(call, Status.INVALID_ARGUMENT, "Locale too long");
        }

        final VerifiedPrincipal principal;
        try {
            // Verifier must validate credentials, never trust x-tenant-id.
            principal = identityVerifier.verify(headers);
        } catch (InvalidCredentialsException ex) {
            return reject(call, Status.UNAUTHENTICATED, "Authentication required");
        }

        if (principal == null || !principal.canAccessTenant(requestedTenant)) {
            return reject(call, Status.PERMISSION_DENIED, "Access denied");
        }

        Locale locale = SupportedLocales.resolve(requestedLocale);
        Context context = Context.current()
            .withValue(VERIFIED_TENANT, requestedTenant)
            .withValue(REQUEST_LOCALE, locale);

        return Contexts.interceptCall(context, call, headers, next);
    }

    private static String getSingleValue(
            Metadata headers, Metadata.Key<String> key) {
        Iterable<String> all = headers.getAll(key);
        if (all == null) {
            return null;
        }
        Iterator<String> it = all.iterator();
        if (!it.hasNext()) {
            return null;
        }
        String value = it.next();
        if (it.hasNext()) {
            throw new IllegalArgumentException("Duplicate metadata key");
        }
        return value;
    }

    private static <ReqT, RespT> ServerCall.Listener<ReqT> reject(
            ServerCall<ReqT, RespT> call,
            Status status,
            String description) {
        call.close(status.withDescription(description), new Metadata());
        return new ServerCall.Listener<ReqT>() {};
    }

    public interface IdentityVerifier {
        VerifiedPrincipal verify(Metadata headers)
            throws InvalidCredentialsException;
    }

    public interface VerifiedPrincipal {
        boolean canAccessTenant(String tenantId);
    }

    public static final class InvalidCredentialsException extends Exception {
        public InvalidCredentialsException(String message) {
            super(message);
        }
    }
}
```

In this example:

- `getSingleValue(...)` rejects duplicate headers to prevent two conflicting interpretations of tenant/locale.
- `IdentityVerifier` is an **integration point** with real authentication, not a complete verifier itself. It must verify JWT signatures, validity, audience/issuer, or use an appropriate authentication mechanism; never merely read an unverified claim.
- `principal.canAccessTenant(...)` must rely on attested permissions or a trusted authorization source. If permissions change over time, proper synchronization and revocation policies are needed.
- `SupportedLocales.resolve(...)` was defined in the previous section; locale does not determine whether tenant access is permitted.
- `Contexts.interceptCall(...)` passes the verified tenant and resolved locale into the call's gRPC context.

**Limitations of the example:** the interceptor only checks basic membership. Whether the user is allowed to read/write **a specific resource** must still be enforced at the service or policy layer. For verifiers that make network calls, avoid long blocking operations on gRPC processing threads; use async authentication or appropriate infrastructure components.

## 8. Using Tenant and Locale in the Service

RPC handler code reads the **verified tenant** and locale from `io.grpc.Context`:

```java
import java.util.Locale;

String tenantId = TenantLocaleServerInterceptor.VERIFIED_TENANT.get();
Locale locale = TenantLocaleServerInterceptor.REQUEST_LOCALE.get();

if (tenantId == null) {
    responseObserver.onError(
        Status.UNAUTHENTICATED
            .withDescription("Authentication required")
            .asRuntimeException());
    return;
}

// Query must be scoped to the verified tenant.
Order order = orderRepository.findByTenantIdAndId(
    tenantId, request.getOrderId());

if (order == null || !orderAccessPolicy.canRead(tenantId, request.getOrderId())) {
    responseObserver.onError(
        Status.NOT_FOUND.withDescription("Order not found")
            .asRuntimeException());
    return;
}

// locale is used in the translation/presentation layer per API contract.
```

This is an illustrative snippet inside an RPC method: `orderRepository` and `orderAccessPolicy` are application components to implement. Returning `NOT_FOUND` for an unauthorized resource is an **existence-hiding policy**; other APIs may use `PERMISSION_DENIED`. Never accidentally return cross-tenant data just because the caller knows an `orderId`.

### How Can Locale Affect the Response?

Example of a business message:

| Locale | Message |
| --- | --- |
| `vi-VN` | "Đơn hàng đã được xác nhận" |
| `en-US` | "Order confirmed" |

In Java/Spring, `MessageSource` can be used to retrieve localized messages:

```java
import java.util.Locale;
import org.springframework.context.MessageSource;

Locale locale = TenantLocaleServerInterceptor.REQUEST_LOCALE.get();
if (locale == null) {
    locale = Locale.forLanguageTag("vi-VN");
}

String message = messageSource.getMessage(
    "order.confirmed",
    null,
    locale);
```

`messageSource` is assumed to be configured with the corresponding translations. This is one option for **content requiring localization**; many gRPC APIs should return stable status codes and Protobuf fields so clients can render translations themselves. Do not use localized text as machine-readable error codes.

### Locale in Java, Spring, and Threads

`io.grpc.Context`, `org.springframework.context.i18n.LocaleContextHolder`, and `org.slf4j.MDC` are not the same mechanism. Setting `REQUEST_LOCALE` in gRPC Context does not automatically update `LocaleContextHolder` across all threads.

When using Spring APIs that rely on `LocaleContextHolder`, set and restore the locale within the callback/transaction scope as appropriate for your application. Never forget to restore state on thread pools. For async processing, propagate gRPC context (`Context.current().wrap(...)` or the corresponding executor) and, when applicable, Spring locale/trace context deliberately.

## 9. Passing Tenant and Locale Between Services

Suppose `CheckoutService` calls `InventoryService` to deduct stock. Both services must agree on which tenant owns the data and communicate which language was selected.

```text
Client
  |
  | x-tenant-id: shop-a
  | x-locale: vi-VN
  v
CheckoutService
  | authenticate caller
  | check permissions for shop-a
  | active tenant = shop-a
  | request locale = vi-VN
  |
  | downstream RPC; appropriate credentials/service identity
  | x-tenant-id: shop-a  <- verified tenant
  | x-locale: vi-VN      <- selected preference
  v
InventoryService
  | authenticate caller as CheckoutService/delegated caller
  | independently verify permissions for shop-a
  v
Read/write shop-a data
```

**Important policies:**

1. A downstream service **must not skip permission checks** just because an upstream attached `x-tenant-id`. It must authenticate the caller and verify permissions within its own trust boundary.
2. If a user token is restricted by `audience`, do not blindly forward the raw token to every service. Service identity, token exchange, or an appropriate on-behalf-of mechanism may be required.
3. Locale can be forwarded to produce appropriate messages, but never as a basis for granting permissions.
4. If spawning an independent task or switching tenants during processing, establish the new context explicitly rather than reusing the old tenant by mistake.
5. Deadlines, trace context, and correlation IDs are still designed via their respective APIs; tenant/locale metadata does not replace them.

### Streaming RPCs

Metadata is only sent at the **start of an RPC stream**. Therefore:

- Within a single-tenant stream, all messages are processed under the tenant verified when the stream opened, subject to revocation/permission policies throughout the stream.
- Do not expect to change `x-tenant-id` or `x-locale` between messages sent by the client.
- If business logic allows each message to belong to a different tenant, model the tenant as a field in the Protobuf message **and enforce permissions per message**. This is a contract and security decision requiring careful review.
- For long-lived streams, establish policies for token expiration, revoked permissions, cancellation checks, and deadlines.

## 10. Error Statuses, Logging, and Security

Tenant and locale issues can lead to various outcomes:

| Scenario | Appropriate gRPC status | Notes |
| --- | --- | --- |
| Missing or invalid token | `UNAUTHENTICATED` | Caller could not be authenticated |
| Malformed tenant ID or duplicate header | `INVALID_ARGUMENT` | Invalid input metadata |
| Authenticated caller lacking permission on tenant | `PERMISSION_DENIED` | Insufficient access rights |
| Resource belongs to another tenant | `PERMISSION_DENIED` or `NOT_FOUND` | Per resource-hiding policy |
| Unsupported locale | Fallback locale or `INVALID_ARGUMENT` | Choose one consistent contract policy |
| Authorization depends on downstream service that is unavailable | `UNAVAILABLE` or appropriate infrastructure status | Never grant access when backend checks fail |
| RPC exceeds deadline | `DEADLINE_EXCEEDED` | Deadlines are managed via gRPC APIs |

These outcomes are returned using `io.grpc.Status`. Never manually write `grpc-status` as a custom metadata key.

**Logging:** log verified tenant IDs only when permitted by logging policy, preferring identifiers that do not disclose private data. Locale can be helpful for diagnosing translation issues, but avoid creating metric labels with unbounded cardinality. Never log bearer tokens, a user's full tenant list, or entire metadata objects.

**Transport security:** TLS/mTLS protects connections and helps authenticate services as configured; they do not turn a self-declared tenant ID into authorized data. If a gateway/proxy terminates TLS, define trust boundaries, protect internal headers, and secure connections behind the proxy.

**Size limits:** gRPC metadata travels via HTTP/2 headers/trailers and is subject to library and infrastructure size limits. Tenant IDs and locales should stay short; do not put permission lists or large tenant configurations into metadata.

## 11. Integration Testing in Spring gRPC

You can test `Metadata` and resolver logic with unit tests, then run a gRPC client/server with interceptors registered to verify permissions, context, and responses. `InProcessServerBuilder`/`InProcessChannelBuilder` are useful for testing logic without opening network ports; TLS, proxies, and network failures need testing over real transport.

| Test case | Setup | Expectation |
| --- | --- | --- |
| Valid tenant, authorized caller | Principal for `shop-a`, header `shop-a` | RPC processes within `shop-a` scope |
| Missing credentials | `x-tenant-id` present without valid token | `UNAUTHENTICATED` |
| Unauthorized tenant | Caller `shop-a` sends `shop-b` | `PERMISSION_DENIED` |
| Duplicate tenant header | Two `x-tenant-id` values | `INVALID_ARGUMENT` in the example interceptor |
| Malformed tenant | Contains newline or exceeds length limit | Rejected per policy |
| Cross-tenant resource read | Request order ID from another tenant | No data returned; error code per policy |
| Valid locale | `x-locale: en-US` | Context holds `Locale.forLanguageTag("en-US")` |
| Unsupported locale | `x-locale: fr-FR` | Uses fallback `vi-VN` per example |
| Missing locale | No `x-locale` | Uses default locale per policy |
| Weighted `accept-language` | `en-GB,en;q=0.9,vi-VN;q=0.8` | Resolver negotiates against supported list |
| Two concurrent callers | Different tenants and locales on the same channel | No context leakage between the two RPCs |
| Downstream RPC | Tenant verified upstream | Downstream still authenticates and enforces permissions |
| Streaming | Multiple messages in one stream | Tenant/locale bound to RPC, not confused per message |
| Async executor | Offload work to thread pool | Context propagated properly without affecting other requests |
| Log inspection | Enable tracing and logging in tests | No tokens or sensitive metadata leaked |

### Unit Test Example for Locale Resolver

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class SupportedLocalesTest {

    @Test
    void resolvesSupportedLocaleAndFallsBack() {
        assertEquals(
            Locale.forLanguageTag("en-US"),
            SupportedLocales.resolve("en-US"));
        assertEquals(
            Locale.forLanguageTag("vi-VN"),
            SupportedLocales.resolve("vi"));
        assertEquals(
            Locale.forLanguageTag("vi-VN"),
            SupportedLocales.resolve("fr-FR"));
        assertEquals(
            Locale.forLanguageTag("vi-VN"),
            SupportedLocales.resolve(null));
    }
}
```

This test validates the pure Java resolver. To confirm the interceptor populates `VERIFIED_TENANT` accurately, test through a server with a **mock `IdentityVerifier` with deterministic principals and permissions**. Do not merely assert a header was sent to prove isolation; verify that queries from tenant A never return tenant B's records.

## 12. Practice Exercise: Multi-Tenant, Multi-Language gRPC

A SaaS platform has `BillingService.GetInvoice` for three tenants: `shop-a`, `shop-b`, and `shop-c`. The client lets users choose a store and display language. Invoice data is stored separately per tenant.

**Implementation requirements:**

1. Standardize `x-tenant-id` as an ASCII tenant ID and `x-locale` as a BCP 47 tag. Specify format, limits, missing-key policy, and fallback policy.
2. Attach both metadata values to the client stub per RPC, while passing credentials via an appropriate authentication mechanism.
3. On the server, verify the caller is authenticated and authorized for the requested tenant; place the **verified tenant** and locale into context.
4. Query invoices using both the verified tenant ID and invoice ID, then apply the invoice viewing policy.
5. Return monetary amounts and timestamps as structured data. Localize only messages genuinely required by the API contract.
6. Write tests for invalid tenants, cross-tenant access, supported/unsupported locales, concurrent execution, and a streaming call.

**Self-check questions:**

- Why is `x-tenant-id` only a tenant selection request, not proof of permission to access?
- What must a user belonging to two tenants do to access each tenant's resources?
- When should clients not send a tenant ID, instead deriving it directly from the verified principal?
- Does `vi-VN` definitively determine the time zone or currency of a transaction?
- What is the difference between `x-locale: vi-VN` and `accept-language: vi-VN,vi;q=0.9,en-US;q=0.7`?
- Why should `Locale.setDefault(...)` not be called on every incoming RPC?
- If `CheckoutService` already verified tenant A, may `InventoryService` trust every tenant header it receives?
- In bidirectional streaming, can a client switch tenants by "updating metadata" on the second message?

**Key takeaway:** Tenant ID and locale can both appear in gRPC metadata, yet serve two different goals. **Tenant ID defines the data scope requiring access control**, whereas **locale adjusts presentation by language and regional conventions**. With Spring gRPC, propagate them per RPC via metadata and interceptors, validate tenant access against a trusted principal, store context in `io.grpc.Context`, and test both data boundaries and language fallback mechanisms.
