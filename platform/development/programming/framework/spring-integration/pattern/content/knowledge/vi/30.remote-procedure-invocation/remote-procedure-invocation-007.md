# Contract của request và reply

## 1. Bối cảnh: một lời gọi Java đi qua ranh giới thông điệp

Trong module **SPRING_INTEGRATION_PATTERN**, chúng ta học triển khai **Enterprise Integration Patterns** bằng **Spring Integration** để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng và có thể quan sát. Khi kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, một yêu cầu có thể đi qua nhiều endpoint trước khi có câu trả lời. Riêng **Remote Procedure Invocation (RPI/RPC)** làm vấn đề này rõ rệt: code gọi trông giống một phương thức Java bình thường nhưng phía thực thi có thể là service khác, thread khác hoặc broker/network khác.

Giả sử dịch vụ đơn hàng muốn lấy giá vận chuyển:

~~~java
ShippingQuoteReply reply = quoteGateway.quote(
        request,
        verifiedTenantId,
        trustedBusinessRequestId);
~~~

Caller có thể kỳ vọng một lời gọi đơn giản, nhưng hệ thống cần trả lời nhiều câu hỏi:

- Request phải có trường nào, kiểu gì, version nào?
- Reply thành công có chứng minh giá đã được tính, hay chỉ chứng minh yêu cầu được tiếp nhận?
- Một sản phẩm không hỗ trợ là **business rejection** hay lỗi hạ tầng?
- Khi không nhận được reply, yêu cầu có thể **đã được xử lý** hay chưa?
- Hai replies đến sai thứ tự được nối với hai requests đang chờ bằng khóa nào?
- Nếu broker redeliver một request, phép xử lý có tạo **side effect trùng** hay không?
- Một phiên bản mới của request có tương thích với consumer chưa nâng cấp không?
- Tenant, authorization và trace context đi qua transport boundary như thế nào?

Một contract tốt cần định nghĩa **cả request lẫn reply**, bao gồm schema, validation, identity, business outcome, error semantics, deadline, correlation và compatibility. Chỉ viết method signature Java hoặc một JSON mẫu là chưa đủ.

~~~mermaid
sequenceDiagram
    participant C as Java caller
    participant G as Spring Messaging Gateway
    participant R as Request channel
    participant S as Remote service / adapter
    participant P as Reply channel
    C->>G: quote(request, tenant, requestId)
    G->>R: Message(payload=request, headers=context)
    R->>S: Request over flow or transport
    S-->>P: Reply with correlation
    P-->>G: Matching response
    G-->>C: typed result or failure
~~~

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **RPC integration style** với **request-reply messaging** và lời gọi Java local.
2. Xây dựng **typed request/reply contract** có version, identity, validation, currency và thời gian rõ.
3. Phân biệt **success**, **business rejection**, **accepted/pending**, **technical failure** và **timeout/unknown**.
4. Ánh xạ request/reply bằng **Spring Integration Messaging Gateway** và **Service Activator** mà không làm mất business correlation.
5. Hiểu đúng các timeout, reply channel, network correlation và idempotency khi retry.
6. Thiết kế compatibility và schema evolution qua nhiều phiên bản producer/consumer.
7. Thử nghiệm hợp đồng bằng JUnit, Spring Integration tests và contract tests qua HTTP/JMS/AMQP.
8. Viết runbook giúp xác định request bị mất, reply muộn, response sai schema hoặc hiệu ứng bị thực thi trùng.

## 2. Remote Procedure Invocation là phong cách tích hợp, không phải lời gọi local được bảo đảm

Trong Enterprise Integration Patterns, **Remote Procedure Invocation** là một trong các phong cách tích hợp: một chương trình gọi thao tác mà chương trình khác cung cấp, với giao diện nhìn gần giống một method. Spring Integration có các **Messaging Gateway** và request-reply adapters có thể tạo ra trải nghiệm RPC-like, nhưng cách triển khai vẫn dựa trên **messages, channels, endpoint và transport**.

| Khía cạnh | Lời gọi Java local | RPC qua network/messaging |
| --- | --- | --- |
| Địa chỉ thực thi | Trong cùng tiến trình | Có thể ở tiến trình/host khác |
| Độ trễ | Thường ngắn và ít dao động | Phụ thuộc queue, network, remote load |
| Dữ liệu | Object references | Bytes/serialized DTO hoặc messages |
| Lỗi | Exception thường trực tiếp | Timeout, connection loss, partial failure, remote error |
| Lifecycle | Thread/call stack | Request state, reply correlation, deadline, retries |
| Exactly-once effect | Có thể điều khiển trong một transaction nội bộ | Không tự bảo đảm xuyên service/broker |
| Version | Các classes cùng deployment | Producer và consumer có thể chạy các versions khác nhau |

**Sai lầm phổ biến:** coi một RPC timeout giống một exception Java xảy ra trước khi method chạy. Thực tế remote có thể đã ghi database nhưng reply thất lạc; caller không biết kết quả. Vì vậy request/reply contract phải có cách **tra cứu trạng thái, idempotency hoặc reconciliation** cho thao tác tạo side effect.

### 2.1. Khi nào RPI là lựa chọn hợp lý?

- Caller cần một kết quả nhanh để tiếp tục xử lý, ví dụ lấy báo giá hoặc kiểm tra thông tin.
- Operation có thời gian xử lý dự kiến ngắn và có giới hạn.
- Có cách xử lý khi remote không sẵn sàng.
- Request/reply schema đủ ổn định, có ownership và version rõ.
- Timeout/retry và fallback được thiết kế theo ý nghĩa nghiệp vụ.

### 2.2. Khi nào nên chọn bất đồng bộ?

- Operation mất nhiều phút hoặc phụ thuộc con người/đối tác.
- Có nhiều receivers cần phản hồi độc lập.
- Caller không cần đợi kết quả cuối ngay tại request ban đầu.
- Phải chống lỗi giữa các dịch vụ bằng trạng thái workflow bền.
- Traffic cao cần buffer/backpressure và làm lại sau restart.

Khi đó có thể dùng **command + accepted receipt + completion event**, hoặc **Scatter-Gather/Aggregator** với timeout và release strategy được định nghĩa. Một Gateway đồng bộ không phải một workflow engine bền.

## 3. Contract gồm nhiều lớp hơn JSON payload

Một request/reply contract thường có ít nhất năm lớp:

~~~mermaid
flowchart TB
    C["Business operation semantics"] --> D["Payload schema / validation"]
    D --> I["Identity + correlation"]
    I --> T["Transport + timeout"]
    T --> F["Failure + retry + versioning"]
~~~

| Lớp | Request phải nói rõ | Reply phải nói rõ |
| --- | --- | --- |
| **Operation** | Cần làm gì, side effect hay read-only | Đã hoàn thành, bị từ chối hay chỉ accepted |
| **Schema** | Field bắt buộc, type, unit, version | Result type, money, error code, nullable fields |
| **Identity** | requestId, operationId, tenant, business key | Echo requestId, correlation/causation |
| **Transport** | Channel/endpoint, deadline, auth | Đường reply, protocol correlation, TTL |
| **Failure policy** | Retryability, idempotency, dedup scope | Business rejection khác technical/unknown |

Một API chỉ công bố:

~~~java
String call(Map<String, Object> request);
~~~

là khó sử dụng đúng: caller không biết tên field, dữ liệu có thể thiếu, không biết String là giá hay error, cũng không biết xử lý thế nào khi timeout.

Một API có kiểu:

~~~java
ShippingQuoteReply quote(
        ShippingQuoteRequest request,
        String verifiedTenantId,
        String businessRequestId);
~~~

rõ hơn, nhưng vẫn cần **documentation + schema validation + error policy + integration tests**. Method signature không tự giải quyết chuyện tương thích khi remote deployment thay đổi.

### 3.1. Request contract và reply contract phải được duyệt cùng nhau

Nếu request hỗ trợ `currencyCode="USD"` nhưng reply chỉ có `long amountVnd`, consumer không thể diễn giải chính xác. Nếu request có `businessRequestId` để dedup nhưng reply không echo identity, một async caller có thể nối reply sai invocation.

**Quy tắc:** không thêm field request có ý nghĩa đến business outcome mà không xem lại các invariant và fields của reply.

### 3.2. Chia các trường theo chủ sở hữu

| Trường | Nguồn đúng | Có thể tin raw client tự khai không? |
| --- | --- | --- |
| `sku`, `quantity` | Payload đã parse/validate | Có thể là input nhưng phải kiểm tra |
| `tenantId` | Authentication/authorization context | **Không** |
| `businessRequestId` | Registry/client operation ID được kiểm chứng | Không hoàn toàn |
| `businessCorrelationKey` | Workflow registry/trusted adapter | **Không** |
| `traceRef` | Observability context | Có thể sử dụng sau validation, không làm authority |
| `replyChannel` | Spring runtime | Không đưa trực tiếp từ untrusted request |
| `JMSCorrelationID` | Transport request-reply protocol | Không tự đồng nghĩa business key |

## 4. Ví dụ xuyên suốt: yêu cầu báo giá vận chuyển

Chúng ta thiết kế RPC-like flow **Shipping Rate Quote** nhằm minh họa **request và reply contract**. Để tập trung vào messaging, ví dụ dùng bảng giá cố định nội bộ, không gọi dịch vụ vận chuyển thực và **không thực hiện charge/reservation**.

### 4.1. Wire request minh họa

~~~json
{
  "contractVersion": 1,
  "requestId": "req-quote-00091",
  "operation": "QUOTE_SHIPPING",
  "payload": {
    "shipmentId": "SHIP-901",
    "serviceLevel": "EXPRESS",
    "parcelCount": 2,
    "currencyCode": "VND"
  }
}
~~~

Thông tin tenant và quyền được xác minh ở ingress. Nếu cần truyền qua remote wire envelope, có thể có `tenantRef` hoặc signature/identity claims tùy hợp đồng, nhưng **không coi field `tenantId` trong JSON tự là bằng chứng quyền**.

### 4.2. Wire reply thành công

~~~json
{
  "contractVersion": 1,
  "requestId": "req-quote-00091",
  "outcome": "QUOTED",
  "result": {
    "shipmentId": "SHIP-901",
    "amount": "160000",
    "currencyCode": "VND",
    "rateVersion": "rate-demo-v1",
    "validUntil": "2026-11-21T03:10:00Z"
  }
}
~~~

Tiền tệ là **decimal string** trên wire để tránh mất chính xác do floating point của JSON consumers. `validUntil` là một **Instant UTC** rõ timezone. Thời gian trong ví dụ chỉ minh họa schema; production phải tính thời hạn từ policy/rate version thực tế.

### 4.3. Wire reply bị từ chối theo nghiệp vụ

~~~json
{
  "contractVersion": 1,
  "requestId": "req-quote-00091",
  "outcome": "REJECTED",
  "error": {
    "code": "SERVICE_LEVEL_UNAVAILABLE",
    "retryable": false,
    "message": "Service level not offered for this shipment"
  }
}
~~~

Đây là **business rejection hợp lệ của operation**, không phải HTTP/JMS connection exception. Caller có thể hiển thị lý do hoặc yêu cầu thay service level. Một lỗi DB/network không được giả thành `REJECTED` chỉ để giữ flow có reply.

### 4.4. Trường hợp không có reply

~~~text
Request sent at T0
Caller waits until T0 + 5s
No reply received
Caller observes: TIMEOUT / UNKNOWN
~~~

**Không được suy ra `REJECTED` hoặc `NOT_EXECUTED`.** Remote service có thể chưa nhận, đang xử lý, đã hoàn tất nhưng reply trễ hoặc đã commit rồi connection mất. Với operation tạo side effect, cần lookup/reconciliation theo requestId/operationId.

## 5. Schema và các bất biến cần kiểm thử

| Thuộc tính | Quy định trong ví dụ |
| --- | --- |
| `contractVersion` | Request/Reply version **1** |
| `requestId` | Ổn định cho cùng logical request, không sinh lại mỗi retry |
| `operation` | `QUOTE_SHIPPING`; phiên bản khác phải định nghĩa rõ |
| `shipmentId` | String hợp lệ, không rỗng |
| `serviceLevel` | Enum `STANDARD` hoặc `EXPRESS` |
| `parcelCount` | Integer từ 1 đến 1000 |
| `currencyCode` | Trong ví dụ chỉ hỗ trợ `VND` |
| Reply `requestId` | Bằng requestId của request tương ứng |
| Reply `outcome` | `QUOTED` hoặc `REJECTED` |
| Reply QUOTED | Có price/currency/rateVersion/validUntil, không có error |
| Reply REJECTED | Có stable error code, không có quote thành công |
| Clock | Thời điểm tuyệt đối ISO-8601 có timezone, không dựa máy client |
| Authorization | Tenant/shipment ownership xác minh trước khi xử lý |

### 5.1. Đơn vị và kiểu tiền

Đừng dùng `float`/`double` để truyền số tiền rồi round ở đầu bên kia:

~~~java
// Không phù hợp cho money contract:
double amount = 0.1 + 0.2;
~~~

Với Java, dùng **BigDecimal** cùng Currency/policy scale rõ. Với wire JSON, có thể dùng một String decimal để tránh khác biệt parse của JavaScript, Python và Java.

### 5.2. Null và optional fields

Tránh một reply “một DTO cho tất cả” gồm `price=null`, `error=null`, `status=null` và để client đoán combination hợp lệ. Có thể dùng **discriminated union**: `outcome=QUOTED` thì có result; `outcome=REJECTED` thì có error. Nếu một operation chỉ accepted để xử lý bất đồng bộ, thêm `ACCEPTED` với schema riêng, không gán thành QUOTED.

### 5.3. Không version hóa bằng tên class Java

Một wire payload không nên phụ thuộc vào `com.example.dto.QuoteCommand` được serialize bằng arbitrary Java object serialization. Sử dụng schema/operation ID/version được công bố, và parser chọn DTO theo allowlist/registry.

## 6. Java 17: typed request có validation ở construction

Ví dụ dùng Java 17 records để tạo một request rõ kiểu. Contract version được giữ trong DTO, không chỉ lưu ở comment.

~~~java
import java.util.Objects;

enum ShippingServiceLevel {
    STANDARD,
    EXPRESS
}

record ShippingQuoteRequest(
        int contractVersion,
        String requestId,
        String shipmentId,
        ShippingServiceLevel serviceLevel,
        int parcelCount,
        String currencyCode) {

    ShippingQuoteRequest {
        if (contractVersion != 1) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_REQUEST_VERSION");
        }
        if (requestId == null
                || !requestId.matches("[A-Za-z0-9_:-]{1,96}")) {
            throw new IllegalArgumentException("INVALID_REQUEST_ID");
        }
        if (shipmentId == null
                || !shipmentId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_SHIPMENT_ID");
        }
        Objects.requireNonNull(serviceLevel, "serviceLevel");
        if (parcelCount < 1 || parcelCount > 1000) {
            throw new IllegalArgumentException("INVALID_PARCEL_COUNT");
        }
        if (!"VND".equals(currencyCode)) {
            throw new IllegalArgumentException("UNSUPPORTED_CURRENCY");
        }
    }
}
~~~

Constructor bảo vệ **cú pháp và invariant của request**. Nó không chứng minh shipment thuộc tenant đã xác thực. Security phải được kiểm tra ở ingress/facade hoặc service có quyền truy registry.

### 6.1. Field nào là request identity?

Ở ví dụ này, `requestId` đại diện **logical request identity**. Cùng một request gửi lại do timeout phải giữ cùng requestId. Nhưng một lần báo giá mới với một lựa chọn serviceLevel khác có thể là một logical request mới và cần requestId mới.

Nếu ứng dụng cho phép cùng requestId nhưng payload khác, downstream phải xem đó là **identity conflict** hoặc correction có revision contract, không âm thầm ghi đè kết quả cũ.

### 6.2. Validate theo thứ tự thích hợp

1. Raw bytes/JSON/XML được parse theo version hỗ trợ.
2. Kiểm tra kích thước, kiểu trường, null, enum, timestamp.
3. Tạo `ShippingQuoteRequest` và chạy schema validation.
4. Xác thực producer/principal và authorization shipment/tenant.
5. Gắn trusted metadata rồi gửi vào IntegrationFlow.
6. Kiểm tra domain-specific invariant trước khi tạo reply.

Đừng đưa DTO từ `ObjectMapper` vào handler chưa bảo vệ nếu schema có **polymorphic class names do client tự chỉ định**. Dùng explicit discriminators/allowlist.

## 7. Java 17: reply có kiểu và phân biệt outcome

Một reply nên **buộc consumer phân biệt kết quả thành công với từ chối**, thay vì bắt consumer đoán null fields:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.Currency;
import java.util.Objects;

record QuoteMoney(BigDecimal amount, Currency currency) {
    QuoteMoney {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        if (!Currency.getInstance("VND").equals(currency)) {
            throw new IllegalArgumentException("UNSUPPORTED_CURRENCY");
        }
        amount = amount.setScale(0, RoundingMode.UNNECESSARY);
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("NEGATIVE_AMOUNT");
        }
    }
}

sealed interface ShippingQuoteReply
        permits ShippingQuoteSuccess, ShippingQuoteRejected {
    int contractVersion();
    String requestId();
}

record ShippingQuoteSuccess(
        int contractVersion,
        String requestId,
        String shipmentId,
        QuoteMoney price,
        String rateVersion,
        Instant validUntil) implements ShippingQuoteReply {

    ShippingQuoteSuccess {
        if (contractVersion != 1) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_REPLY_VERSION");
        }
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(shipmentId, "shipmentId");
        Objects.requireNonNull(price, "price");
        if (rateVersion == null || rateVersion.isBlank()) {
            throw new IllegalArgumentException("MISSING_RATE_VERSION");
        }
        Objects.requireNonNull(validUntil, "validUntil");
    }
}

record ShippingQuoteRejected(
        int contractVersion,
        String requestId,
        String code,
        boolean retryable,
        String safeMessage) implements ShippingQuoteReply {

    ShippingQuoteRejected {
        if (contractVersion != 1) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_REPLY_VERSION");
        }
        Objects.requireNonNull(requestId, "requestId");
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("MISSING_ERROR_CODE");
        }
        Objects.requireNonNull(safeMessage, "safeMessage");
    }
}
~~~

**Lưu ý Java records:** constructor compact có thể thay đổi tham số đầu vào như `amount = amount.setScale(...)`; field của record sẽ nhận giá trị đã chuẩn hóa. `RoundingMode.UNNECESSARY` cố ý từ chối giá trị có phần lẻ không hợp với VND. Không âm thầm làm tròn phí vận chuyển.

### 7.1. Business rejection không phải Throwable

`ShippingQuoteRejected` dùng cho một **kết quả nghiệp vụ đã biết** (ví dụ serviceLevel EXPRESS không phục vụ một số loại shipment). Một lỗi thiếu quyền, lỗi JSON hỏng, database timeout hoặc JVM exception không nên tự biến thành một ShippingQuoteRejected có code `UNKNOWN`.

### 7.2. Mã lỗi phải ổn định

Nếu error code là `SERVICE_LEVEL_UNAVAILABLE`, consumer có thể tạo thông báo phù hợp. Trường `safeMessage` chỉ phục vụ hiển thị hoặc debugging đã sanitize; **không parse logic theo nội dung câu tiếng Anh** vì câu chữ có thể đổi khi dịch hoặc deploy.

### 7.3. Reply cần echo requestId

`requestId` nằm trong cả hai variants. Một consumer có thể verify reply.requestId bằng request đang chờ; nếu mismatch, không trả nó về một caller khác. Với request/reply qua transport, còn cần **protocol correlation** và phương án xử lý khi reply đến muộn.

## 8. QuoteDecisionService: kết quả deterministic và có giới hạn

Ta xây service minh họa, không I/O, không tạo side effect. Giá tính theo số package với dữ liệu cố định trong bài, sử dụng Clock để kiểm thử `validUntil` rõ ràng.

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Currency;
import java.util.Objects;

final class QuoteDecisionService {
    private final Clock clock;

    QuoteDecisionService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    ShippingQuoteReply decide(ShippingQuoteRequest request) {
        // Quy tắc nghiệp vụ minh họa:
        // EXPRESS chỉ hỗ trợ tối đa 20 parcels trong demo.
        if (request.serviceLevel() == ShippingServiceLevel.EXPRESS
                && request.parcelCount() > 20) {
            return new ShippingQuoteRejected(
                    1, request.requestId(),
                    "SERVICE_LEVEL_UNAVAILABLE",
                    false,
                    "Express service unavailable for this package count");
        }

        long unitPriceVnd = request.serviceLevel()
                == ShippingServiceLevel.EXPRESS ? 80_000L : 30_000L;
        BigDecimal total = BigDecimal.valueOf(unitPriceVnd)
                .multiply(BigDecimal.valueOf(request.parcelCount()));

        return new ShippingQuoteSuccess(
                1,
                request.requestId(),
                request.shipmentId(),
                new QuoteMoney(total, Currency.getInstance("VND")),
                "rate-demo-v1",
                Instant.now(clock).plus(Duration.ofMinutes(10)));
    }
}
~~~

Hai lời gọi cùng một request có thể cho cùng **amount/rateVersion** nhưng **validUntil khác nhau** nếu dùng Clock thời gian thực. Nếu business yêu cầu replay cùng requestId trả **chính xác cùng một reply**, production cần **persist quote snapshot/rateVersion/expiry** hoặc cache kết quả theo idempotency key; không chỉ phụ thuộc phép tính deterministic trên giá.

### 8.1. Không dùng Clock.now để tạo request identity

Thời điểm xử lý có thể thay đổi giữa retry. Không lấy `Instant.now()` làm requestId, correlationKey hoặc operationId. Những identity cần được cấp bởi registry/ingress, giữ ổn định cho cùng logical operation.

### 8.2. Khi nào Service được phép trả REJECTED?

Ví dụ `EXPRESS` với 21 parcels vi phạm **business offering policy** nhưng request vẫn có schema hợp lệ, service có đủ thông tin để trả từ chối dứt khoát. Ngược lại, network timeout khi tra catalog không cung cấp bằng chứng khách hàng bị từ chối; operation vẫn có thể đang pending/unknown.

## 9. Gateway interface: Java request thành Spring Message

Spring Integration cung cấp **Messaging Gateway** để che giấu MessageChannel và MessageHeaders với caller:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway(defaultRequestChannel = "rpcQuoteRequests")
interface ShippingQuoteGateway {

    @Gateway(requestTimeout = 2_000, replyTimeout = 5_000)
    ShippingQuoteReply quote(
            @Payload ShippingQuoteRequest request,
            @Header("trustedTenantId") String tenantId,
            @Header("businessRequestId") String businessRequestId);
}
~~~

**Mapping của method:**

~~~text
Java Gateway call
  request argument -> Spring Message.payload
  tenantId argument -> header trustedTenantId
  businessRequestId -> header businessRequestId

Framework:
  adds MessageHeaders.ID / timestamp
  manages reply channel if a reply is expected

Downstream:
  Service Activator handles payload and selected headers
  returns ShippingQuoteReply
~~~

Gateway method nhận **ShippingQuoteReply**, nhưng ở Spring runtime nó có thể được triển khai bằng message dispatch, Service Activator, HTTP/JMS/AMQP outbound gateway hoặc một tuyến Router nhiều hops.

### 9.1. Không để client tự quyết định trustedTenantId

Một HTTP request có `X-Tenant-Id: tenant-admin` không được truyền thẳng làm `trustedTenantId`. Gateway proxy chỉ map giá trị, **không xác minh quyền**. Cần application service kiểm tra principal và quyền shipment trước khi gọi interface.

### 9.2. businessRequestId gắn với requestId

Ở ví dụ, `@Header("businessRequestId")` mirror `request.requestId()` để downstream kiểm tra hai nguồn thông tin khớp. Điều này giúp phát hiện một mapping lỗi hoặc header giả, nhưng không thay thế verification tại ingress.

Nếu dùng duy nhất requestId trong payload và không cần mirror header, có thể bỏ argument/header tương ứng. Đừng duy trì nhiều bản sao identity mà không có consistency rule.

### 9.3. Không đẩy timeout policy vào payload bừa bãi

`requestTimeout` và `replyTimeout` là runtime settings của Gateway invocation, không tự là domain deadline. Nếu contract cần một **business deadline** có ý nghĩa qua transport/restarts, biểu diễn rõ bằng một field/metadata versioned với UTC instant và quy tắc hết hạn riêng.

## 10. Service Activator: nhận đúng hợp đồng và tạo reply

Handler nhận `@Payload` và `@Header` để kiểm tra identity. Nó **không tự xây một MessageChannel reply mới**.

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

final class QuoteRpcHandler {
    private final QuoteDecisionService service;

    QuoteRpcHandler(QuoteDecisionService service) {
        this.service = service;
    }

    @ServiceActivator(inputChannel = "rpcQuoteRequests")
    public ShippingQuoteReply handle(
            @Payload ShippingQuoteRequest request,
            @Header("trustedTenantId") String tenantId,
            @Header("businessRequestId") String businessRequestId) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new SecurityException("MISSING_VERIFIED_TENANT");
        }
        if (!request.requestId().equals(businessRequestId)) {
            throw new SecurityException("REQUEST_ID_HEADER_MISMATCH");
        }
        return service.decide(request);
    }
}
~~~

**Hai điểm bảo vệ:** required `@Header` giúp framework phát hiện missing header khi bind parameter; body method đối chiếu requestId để chặn mismatch. Tuy nhiên `tenantId` là String hợp lệ về cú pháp không chứng minh tenant có quyền với shipment; authorization vẫn thuộc lớp có verified principal/registry.

### 10.1. Không tự tạo Reply Message rồi bỏ mất temporary replyChannel

Khi Service Activator trả `ShippingQuoteReply` như payload, Spring Integration có thể tạo reply Message và quản lý đường reply theo framework semantics. Nếu handler tự dựng Message mới mà bỏ replyChannel cần thiết, Gateway đang chờ có thể không nhận kết quả.

### 10.2. Một chiều và hai chiều phải có contract riêng

Nếu thay method bằng `void handle(...)` và chỉ ghi vào database, Gateway method `quote()` vẫn kỳ vọng typed reply. Flow có thể kết thúc không có reply hoặc timeout. Với command one-way, dùng method Gateway trả `void` hoặc trả một **ack/accepted result** có ý nghĩa đã định nghĩa, không giả tạo QUOTED.

## 11. Cấu hình Spring Integration cho RPC-like flow

Ví dụ sử dụng **DirectChannel** để tập trung vào contract và request/reply. Không cần HTTP server, broker hay remote service thật.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan
class QuoteRpcConfig {

    @Bean
    MessageChannel rpcQuoteRequests() {
        return new DirectChannel();
    }

    @Bean
    Clock quoteClock() {
        // Fixed Clock chỉ để ví dụ/test tái lập kết quả.
        // Production dùng Clock.systemUTC().
        return Clock.fixed(
                Instant.parse("2026-11-21T03:00:00Z"),
                ZoneOffset.UTC);
    }

    @Bean
    QuoteDecisionService quoteDecisionService(Clock quoteClock) {
        return new QuoteDecisionService(quoteClock);
    }

    @Bean
    QuoteRpcHandler quoteRpcHandler(QuoteDecisionService service) {
        return new QuoteRpcHandler(service);
    }
}
~~~

Đặt `ShippingQuoteGateway` interface cùng package (hoặc package thuộc phạm vi `@IntegrationComponentScan`). Spring Integration tạo Gateway proxy cho interface được đăng ký, và endpoint của `QuoteRpcHandler` được tạo từ `@ServiceActivator`.

**Không đăng ký thêm một IntegrationFlow bean khác cùng tiêu thụ `rpcQuoteRequests` trong context này nếu chỉ muốn một handler.** DirectChannel có thể dispatch cho một subscriber được chọn; hai competing handlers làm kết quả khó dự đoán.

### 11.1. Diagram của cấu hình mẫu

~~~mermaid
flowchart LR
    C["Application service"] --> G["ShippingQuoteGateway"]
    G -->|"QuoteRequest + trusted headers"| D["rpcQuoteRequests DirectChannel"]
    D --> A["QuoteRpcHandler @ServiceActivator"]
    A --> S["QuoteDecisionService"]
    S -->|"ShippingQuoteReply"| A
    A -->|"Gateway-managed reply path"| G
    G -->|"Typed result"| C
~~~

Trong topology này request dispatch và handler chủ yếu chạy **đồng bộ** trên caller thread. `replyTimeout=5_000` không phải một hard execution deadline cho code Java chạy trực tiếp trong DirectChannel; nếu handler bị treo, timeout của `receive` không nhất thiết ngắt được handler đang thực thi.

### 11.2. Một request gọi Gateway

~~~java
ShippingQuoteRequest request = new ShippingQuoteRequest(
        1,
        "req-quote-00091",
        "SHIP-901",
        ShippingServiceLevel.EXPRESS,
        2,
        "VND");

ShippingQuoteReply reply = gateway.quote(
        request,
        "tenant-a",               // chỉ sau authorization
        request.requestId());
~~~

Ở thực tế, mã gọi này nên nằm trong một facade đã xác minh actor/tenant/shipment. `gateway` là bean Spring được inject; không tự `new ShippingQuoteGateway()` vì đây là interface/proxy.

### 11.3. Tách business logic khỏi messaging

`QuoteDecisionService.decide(request)` là một Java method thuần, không import MessageChannel, ErrorMessage hay Gateway. `QuoteRpcHandler` đóng vai trò adapter từ Spring Message sang domain service; `ShippingQuoteGateway` đóng vai trò adapter ngược từ Java API sang messaging.

~~~text
Caller -> Gateway -> Message -> Service Activator
                               -> Domain service
Caller <- Gateway <- Reply Message <- result
~~~

Đây là cách code Java còn dễ kiểm thử, trong khi topology Router, Transformer hoặc remote adapters có thể thay đổi mà không buộc domain service nhận Spring Message trực tiếp.

## 12. Hợp đồng correlation: có ít nhất ba loại identity

Một RPC-like invocation thường có **nhiều identity với phạm vi khác nhau**:

| Identity | Scope | Nguồn | Khi retry? |
| --- | --- | --- | --- |
| **requestId / businessRequestId** | Logical business request | Ingress/operation registry | Giữ nguyên nếu là cùng request |
| **businessCorrelationKey** | Một workflow hoặc group | Verified tenant + entity + epoch | Giữ nguyên trong workflow |
| **Spring MessageHeaders.ID** | Một Message instance | Framework | Có thể đổi |
| **temporary replyChannel** | Một Gateway invocation | Spring Gateway runtime | Thường khác mỗi invocation |
| **JMSCorrelationID / AMQP correlationId** | Transport request/reply exchange | Adapter/broker protocol | Có thể đổi mỗi attempt |
| **traceId/spanId** | Truy vết thực thi | Tracing infrastructure | Trace/span tùy retry topology |

Không gọi tất cả những trường này chung là “correlationId” trong code business nếu chúng phục vụ các bài toán khác nhau.

### 12.1. businessRequestId dùng để xác minh reply

Trong flow đồng bộ, Gateway thường đã giữ riêng temporary reply channel. Nhưng reply vẫn echo `requestId` vì:

- Khi serialize qua network, remote response phải tự mô tả nó trả lời request nào.
- Khi persisted/replayed, không thể dựa vào Java channel object.
- Khi remote trả sai requestId, consumer có thể phát hiện response mismatched.
- Khi log/audit, requestId giúp truy một logical invocation xuyên nhiều hops.

### 12.2. Một workflow có nhiều requestIds

Giả sử workflow SHIP-901 gồm:

~~~text
workflow key = shipping:tenant-a:SHIP-901:epoch-7

quote request:
  requestId = req-quote-00091

reserve stock request:
  requestId = req-stock-00501

book carrier request:
  requestId = req-carrier-00888
~~~

Ba operations có **requestIds riêng** nhưng có thể dùng chung businessCorrelationKey của workflow cha. Nếu dùng workflow key làm idempotency key cho cả ba operations, một ledger có thể chặn các operations khác nhau như duplicates.

### 12.3. Correlation không phải authorization

Một attacker biết requestId hoặc business group key không có nghĩa được phép nhận reply. Transport adapter phải xác thực producer/caller, xác minh tenant ownership và hạn chế destination; không dùng requestId như bearer token.

### 12.4. Splitter/Aggregator có correlation scope riêng

Nếu request được Splitter chia thành nhiều parcel requests, `CORRELATION_ID`, `SEQUENCE_NUMBER`, `SEQUENCE_SIZE` có thể mô tả một nhóm child. Nó không nhất thiết trùng với businessCorrelationKey của shipment. Aggregator cần correlation/release strategy theo **đúng scope**, không chỉ group.size() khi message có thể bị redeliver.

## 13. Reply path trong Spring Messaging Gateway

Với một method có return type, Gateway thường sử dụng **reply destination tạm thời**:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Messaging Gateway
    participant H as RPC handler
    C->>G: quote(request)
    G->>H: Message + temporary replyChannel
    H-->>G: ShippingQuoteSuccess
    G-->>C: typed ShippingQuoteReply
~~~

Trong ví dụ, Service Activator trả một `ShippingQuoteSuccess` hoặc `ShippingQuoteRejected` như payload, để framework gửi lại theo reply path mà Gateway đã thiết lập.

### 13.1. Đường reply bị tách sang QueueChannel

Phản ví dụ:

~~~text
Gateway replyChannel = temporary-A

Handler:
  sends ShippingQuoteSuccess to standalone "quoteOutputQueue"

No bridge / reply wiring back to temporary-A

Gateway:
  waits on temporary-A
  eventually has no reply
~~~

Một `outputChannel` cố định không tự là replyChannel mà caller đang đợi. Nếu flow thiết kế dùng reply queue riêng, cần một **bridge/correlator** hoặc gateway adapter cấu hình chính xác để reply quay về đúng invocation.

### 13.2. Reply đến hai lần

Một request/reply Gateway method kỳ vọng một kết quả tương ứng. Nếu downstream Scatter-Gather làm phát sinh ba replies, Gateway không tự biết reply nào là “kết quả cuối”. Cần Aggregator để tạo **một business result** theo release strategy, có timeout và dedup.

### 13.3. Reply trễ

Nếu caller timeout sau 5 giây, một reply đến giây thứ 8 có thể không còn receiver tương ứng ở temporary reply channel. Nếu business result vẫn cần được xử lý, lưu vào workflow state và liên kết bằng requestId/business key, thay vì chuyển sang một invocation đang chờ khác.

### 13.4. Trả null hoặc không có reply

Một handler một chiều trả void, Filter discard hoặc flow không có responder có thể khiến Gateway không nhận reply đúng hạn. **Không mặc định `null` nghĩa là business rejection**. Hợp đồng client phải phân biệt không có reply (technical outcome) với reply `ShippingQuoteRejected` có ý nghĩa nghiệp vụ.

## 14. Trạng thái outcome: business và technical là hai trục khác nhau

Một hệ thống ổn định cần tránh ghép mọi exception vào một enum `FAILED` không đủ ngữ nghĩa.

| Quan sát của caller | Ý nghĩa có thể kết luận | Caller nên làm |
| --- | --- | --- |
| **ShippingQuoteSuccess** | Quote được tính theo contract và rate version | Dùng trong thời hạn hợp lệ |
| **ShippingQuoteRejected** | Business rule từ chối rõ ràng | Đổi yêu cầu/hiển thị lý do |
| **Accepted/Pending** (nếu contract có) | Yêu cầu được nhận nhưng chưa có kết quả cuối | Poll/subscribe workflow |
| **Validation exception** | Request schema/headers không hợp lệ | Sửa input, thường không retry nguyên request |
| **Authorization exception** | Caller không có quyền | Không tiếp tục, audit |
| **Network/send failure** | Không chắc remote đã nhận | Lookup/retry theo idempotency policy |
| **Reply timeout** | Chưa có reply kịp thời | UNKNOWN; không tự kết luận failed |
| **Remote technical error** | Có sự cố ở hệ thống xử lý | Bounded retry/recovery nếu retryable |

### 14.1. Error reply hay exception?

Một contract có thể chọn trả structured **technical error envelope** (ví dụ `UPSTREAM_UNAVAILABLE`) khi remote biết lỗi và có thể phản hồi một cách an toàn. Nhưng lỗi **không nhận được reply** không thể hiện bằng một remote envelope do server gửi, vì server có thể chưa gửi gì. Client phải có nhánh timeout/exception riêng.

### 14.2. Business rejection không phải luôn retryable=false

Ví dụ bài dùng `SERVICE_LEVEL_UNAVAILABLE, retryable=false`. Một số business refusals có thể là `TEMPORARILY_UNAVAILABLE`, nhưng cần contract nêu rõ **sau điều kiện nào** được thử lại. Không dùng một boolean retryable làm quyết định duy nhất cho side-effecting operations; còn cần deadline, backoff, idempotency và trạng thái đã commit.

### 14.3. Không leak stack trace qua reply

`safeMessage` chỉ nên chứa câu có thể công bố cho consumer, không chứa SQL, token, địa chỉ nội bộ, hostname hoặc stack trace. Các thông tin điều tra nên nằm trong logs/traces và audit có quyền truy cập.

## 15. Request deadline, Gateway timeout và transport TTL

Có ít nhất ba loại hạn thời gian:

| Loại | Được dùng ở đâu? | Điều nó bảo đảm |
| --- | --- | --- |
| **Gateway requestTimeout** | Gửi Message vào request channel | Giới hạn chờ khi send có thể block |
| **Gateway replyTimeout** | Đợi reply sau dispatch | Caller không chờ vô hạn |
| **Business deadline** | Schema/workflow state | Hết thời gian mà operation còn hữu ích |
| **Transport TTL / expiration** | Broker/network | Message quá hạn có thể bị bỏ/không giao |
| **Provider operation timeout** | Remote client/library | Giới hạn một HTTP/gRPC/JMS attempt |

Những thời hạn này không thể thay thế lẫn nhau. Thông số `replyTimeout=5000` không bảo đảm remote dừng xử lý sau 5 giây hoặc rollback những side effects đã commit.

### 15.1. Deadline cần là thời điểm tuyệt đối nếu truyền qua nhiều hops

~~~json
{
  "requestId": "req-quote-00091",
  "businessDeadline": "2026-11-21T03:02:00Z"
}
~~~

Nếu deadline là một field của contract v2, cần quy định timezone UTC, nguồn đồng hồ, skew và behavior khi message đến muộn. Mỗi hop có thể tính **remaining budget** từ deadline thay vì cộng thêm 5 giây cho mỗi service và kéo dài vô hạn end-to-end latency.

### 15.2. Timeout và cancellation không đồng nghĩa

Caller có thể bị timeout trong khi remote vẫn đang chạy. Nếu cần hỗ trợ cancellation, cần một **hợp đồng cancel operation riêng** với operationId, authorization và kết quả CANCELLATION_ACCEPTED/CANNOT_CANCEL/ALREADY_COMMITTED; không giả định Java thread interruption qua network sẽ rollback remote DB.

### 15.3. Không retry sau deadline theo quán tính

Retry policy phải tính tổng thời gian: attempts, backoff, jitter, provider timeout và deadline. Khi deadline hết, chuyển trạng thái timeout/unknown và tra/reconcile nếu có side effect thay vì tiếp tục làm việc vô nghĩa.

## 16. Contract qua HTTP, JMS, AMQP và các remote adapters

Ví dụ DirectChannel ở trên chạy trong cùng JVM để minh họa request/reply. Khi đưa service ra ngoài tiến trình, contract phải đi qua **serialization + protocol-specific request/reply correlation + security**.

~~~mermaid
flowchart LR
    G["Java Messaging Gateway"] --> F["IntegrationFlow"]
    F --> A["HTTP / JMS / AMQP outbound gateway"]
    A --> W["Wire contract v1"]
    W --> B["Remote inbound adapter"]
    B --> S["Remote handler"]
    S --> R["Wire reply v1"]
    R --> A
    A --> F
    F --> G
~~~

| Transport | Request/reply mechanism | Contract concerns |
| --- | --- | --- |
| **HTTP** | Request + HTTP response trên connection/request lifecycle | Status codes, content type, JSON schema, timeout, retry safety |
| **JMS** | JMSReplyTo/JMSCorrelationID và request/reply destinations | Message converter, correlation strategy, reply listener, DLQ |
| **AMQP** | replyTo, correlation properties, broker routing | Message converter, publisher confirms vs business replies, reply queues |
| **TCP** | Framing, connection/request correlator tùy adapter | Message boundaries, connection lifetime, serializer |
| **gRPC/other RPC** | Protocol-defined status, metadata and message schema | Deadlines, status mappings, auth, compatibility |

Không áp dụng cùng một quy tắc request/reply cho tất cả adapters. Một HTTP 202 Accepted có ý nghĩa khác HTTP 200 chứa final quote. Một broker ACK có thể chỉ xác nhận **đã nhận message ở transport**, không chứng minh business operation đã commit.

### 16.1. HTTP: tách status code và business outcome

Một hợp đồng có thể công bố:

| HTTP response | Ý nghĩa | Body |
| --- | --- | --- |
| 200 | Quote đã tính thành công | ShippingQuoteSuccess |
| 422 | Input hợp schema nhưng vi phạm offering policy | ShippingQuoteRejected |
| 202 | Command được nhận, xử lý async | AcceptedReceipt với operationId/statusUrl |
| 400 | JSON/shape không hợp lệ | Standardized validation error |
| 401/403 | Authentication/authorization failed | Error an toàn, không tiết lộ nội bộ |
| 429/503 | Rate limit/upstream unavailable | Technical error với retry guidance nếu phù hợp |
| Timeout/no response | Caller không biết outcome | UNKNOWN, tra trạng thái nếu cần |

Đây là **gợi ý thiết kế**, không phải Spring Integration tự mặc định mapping đúng những status code này. HTTP inbound/outbound gateways cần được cấu hình converter, status mapping và exception handling theo hợp đồng cụ thể.

### 16.2. JMSCorrelationID không nhất thiết bằng requestId nghiệp vụ

Một JMS outbound gateway có thể tự quản lý correlation token cho **một request attempt**. `businessRequestId` là identity xuyên retries và qua persisted workflow. Không nên ép token transport và business request ID luôn trùng nhau trừ khi **adapter configuration, collision rules và version contract** được kiểm chứng.

### 16.3. AMQP broker ACK khác business reply

Publisher confirm/broker ack chỉ chứng minh broker đã nhận hoặc xử lý tới một mức nhất định. Một reply `ShippingQuoteSuccess` phải đến từ handler đã tính quote, theo schema v1. Nếu consumer crash trước khi trả reply, broker redelivery/retry logic phải xử lý đúng, không coi broker confirm là giá trị business.

### 16.4. Header mapper và envelope

Một Spring Message có thể có:

~~~text
payload: ShippingQuoteRequest
headers:
  trustedTenantId: tenant-a
  businessRequestId: req-quote-00091
  replyChannel: temporary Java object
~~~

Sau serialize sang HTTP/JMS, **không phải mọi header được giữ**. Business identity cần có wire schema hoặc selected broker properties rõ, và remote ingress phải **xác minh lại** quyền tenant. Không serialize một live `replyChannel` object vào JSON rồi mong JVM khác có thể dùng nó.

### 16.5. Test round-trip qua adapter thực

1. Dựng request với version và requestId xác định.
2. Gateway tạo Spring Message.
3. Converter/adapter biến nó thành bytes + allowed protocol headers.
4. Remote parser/validator dựng typed request.
5. Remote handler trả một reply có requestId khớp.
6. Reply qua transport adapter được map về Spring Message.
7. Gateway caller nhận đúng reply hoặc một lỗi được phân loại.

Unit test với `ObjectMapper` không thay thế một **JMS HeaderMapper/HTTP integration test** nếu mục tiêu là kiểm chứng network metadata.

## 17. Versioning và compatibility của request/reply

Request và reply có thể tiến hóa theo nhịp khác nhau. Một thay đổi cần xét **cả producer, consumer, persisted message, DLQ và replay**.

### 17.1. Ba loại thay đổi

| Thay đổi | Ví dụ | Đánh giá |
| --- | --- | --- |
| **Additive/optional** | Reply thêm `estimatedDeliveryDate` nullable | Có thể backward compatible nếu consumer bỏ qua unknown field |
| **Semantics change** | `amount` từ gross thành net | **Breaking về ý nghĩa** dù tên và kiểu không đổi |
| **Structural breaking** | `requestId` đổi sang integer, đổi `currencyCode` sang enum khác | Cần version/migration |

**Tương thích cấu trúc chưa đủ tương thích nghiệp vụ.** Một v1 consumer đọc được field `amount` của v2 nhưng hiểu sai gross/net còn nguy hiểm hơn lỗi parse rõ ràng.

### 17.2. Quy tắc consumer tolerant nhưng không mơ hồ

Consumer có thể bỏ qua **unknown optional fields** nếu schema policy cho phép. Nhưng không được:

- Đoán currency khi currencyCode thiếu.
- Tự map enum lạ thành QUOTED hoặc REJECTED.
- Tự chuyển amount float sang decimal mà không biết precision.
- Dùng businessRequestId khác nhau cho cùng logical retry.
- Đổi timezone của `validUntil` sang system default.

### 17.3. Không lấy version reply từ request rồi gán bừa

Một server nhận request v1 có thể trả reply v1 theo negotiated contract. Nếu server trả reply v2, caller phải biết decode và kiểm tra compatibility. Không gắn `contractVersion=1` lên một payload thực chất có semantics v2 chỉ để parser cũ không báo lỗi.

### 17.4. Versioned upcaster

~~~text
Wire Request v1 ----> Parser V1 ---+
                                   +-> CanonicalRequest -> Domain service
Wire Request v2 ----> Parser V2 ---+

Domain result -> Reply projection v1 / v2
              -> Wire serializer by negotiated contract
~~~

Upcaster chỉ được điền default cho các field mới **nếu có nghĩa nghiệp vụ hợp lệ**. Ví dụ v1 chưa có insuranceFlag mà v2 mặc định `false` có thể sai nếu v1 mặc định bảo hiểm theo một chính sách khác.

### 17.5. Version trong URL, header hay body?

Có thể dùng `/v1/quote`, media type versioned, schema registry, `contractVersion` trong envelope hoặc broker topic versioned. Chọn **một strategy nhất quán**, document cách nhận diện parser, và tránh để nhiều version markers mâu thuẫn mà không có validation.

### 17.6. Error code cũng là contract

Nếu một consumer xử lý `SERVICE_LEVEL_UNAVAILABLE`, đổi tên code thành `UNSUPPORTED_LEVEL` có thể phá backward compatibility. Nên version code taxonomy, có mapping/deprecation plan và contract tests cho error replies.

## 18. Trusted facade: ai được phép gọi remote operation?

Không nên để một HTTP controller truyền trực tiếp `X-Tenant-Id` vào Gateway. Một facade kiểm tra identity và quyền shipment trước, rồi tạo/gắn `requestId` theo hợp đồng.

### 18.1. Application contracts

~~~java
record AuthenticatedQuoteActor(
        String principalId,
        String tenantId) {
}

interface QuoteAuthorization {
    void requireAllowed(
            AuthenticatedQuoteActor actor,
            ShippingQuoteRequest request);
}

interface QuoteRequestRegistry {
    void verifyLogicalIdentity(
            AuthenticatedQuoteActor actor,
            ShippingQuoteRequest request);
}
~~~

`AuthenticatedQuoteActor` phải đến từ authentication/session/mTLS/JWT/broker identity đã xác minh, **không** dựng từ raw tenant claim. `QuoteRequestRegistry` có thể kiểm tra requestId là identity hợp lệ cho request này, trùng payload hay một revision mới.

### 18.2. Facade tách quyền khỏi Gateway

~~~java
final class QuoteApplicationFacade {
    private final ShippingQuoteGateway gateway;
    private final QuoteAuthorization authorization;
    private final QuoteRequestRegistry registry;

    QuoteApplicationFacade(
            ShippingQuoteGateway gateway,
            QuoteAuthorization authorization,
            QuoteRequestRegistry registry) {
        this.gateway = gateway;
        this.authorization = authorization;
        this.registry = registry;
    }

    ShippingQuoteReply getQuote(
            ShippingQuoteRequest request,
            AuthenticatedQuoteActor actor) {

        authorization.requireAllowed(actor, request);
        registry.verifyLogicalIdentity(actor, request);

        ShippingQuoteReply reply = gateway.quote(
                request,
                actor.tenantId(),
                request.requestId());

        if (reply == null) {
            throw new IllegalStateException("NO_REPLY_RECEIVED");
        }
        if (!request.requestId().equals(reply.requestId())) {
            throw new IllegalStateException("WRONG_REQUEST_REPLY");
        }
        if (reply.contractVersion() != 1) {
            throw new IllegalStateException(
                    "UNSUPPORTED_REPLY_VERSION");
        }
        return reply;
    }
}
~~~

Nếu Gateway không trả reply đúng hạn, `getQuote` có thể ném exception hoặc nhận kết quả theo timeout configuration; ví dụ này chỉ kiểm tra **một reply thực sự được nhận**. `reply` có thể cần null check theo Gateway version/return contract để không báo NullPointerException thiếu thông tin.

### 18.3. Remote service cũng phải authorize

Không dựa duy nhất vào việc caller nội bộ đã xác minh. Khi message đi qua broker/network, remote có thể được gọi từ một producer khác. Remote ingress cần authentication, tenant binding và authorization thích hợp; application header do một producer gửi không tự là quyền.

### 18.4. Không đẩy secret vào reply

Reply có thể đi vào logs, caches hoặc UI. Chỉ trả dữ liệu cần thiết cho consumer: requestId, quote, validity, safe error code. Không echo JWT token, cookie, mTLS private material hoặc raw stack trace.

## 19. Retry và idempotency cho RPC có side effect

Trong ví dụ tính giá thuần, gọi lại có thể không tạo side effect. Nhưng khi áp dụng RPI cho **reserveInventory**, **chargePayment**, **bookShipment** hoặc **createOrder**, một timeout gây nguy cơ gửi lại operation đã được thực hiện.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant S as Remote service
    participant D as Database
    C->>S: Reserve(operationId=op-91)
    S->>D: Commit reservation
    D-->>S: Committed
    Note over S,C: Reply lost / connection reset
    C->>C: Timeout / UNKNOWN
    C->>S: Retry same operationId=op-91
    S->>D: Find committed result by operationId
    D-->>S: Existing reservation receipt
    S-->>C: Same logical result
~~~

### 19.1. Phân biệt requestId và operationId

Với một read-only quote, requestId đủ nhận diện query. Với lệnh có side effect, cần **operationId/idempotencyKey** theo scope tenant+producer+operationType. Có thể chọn operationId=requestId **nếu contract quy định và bảo đảm duy nhất phù hợp**; không tự mặc định mọi RPC request cùng business correlation key đều là một operation.

### 19.2. Một ledger bền

~~~sql
CREATE TABLE rpc_operation_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    producer_id VARCHAR(64) NOT NULL,
    operation_type VARCHAR(48) NOT NULL,
    operation_id VARCHAR(96) NOT NULL,
    request_digest VARCHAR(128) NOT NULL,
    contract_version INTEGER NOT NULL,
    state VARCHAR(24) NOT NULL,
    result_reference VARCHAR(160),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (
        tenant_id, producer_id, operation_type, operation_id)
);

CREATE INDEX rpc_operation_inbox_state_idx
    ON rpc_operation_inbox (state);
~~~

**Identity scope phải theo nguồn contract.** Nếu operationId duy nhất toàn hệ thống, có thể giản lược; nếu chỉ duy nhất theo producer, không bỏ producer_id.

### 19.3. Same key, different payload = conflict

Một idempotency key bị dùng lại với request digest khác không phải redelivery vô hại. Trả conflict/quarantine, yêu cầu producer cấp operationId mới hoặc revision contract có điều kiện. Không overwrite operation cũ rồi gửi reply QUOTED/ACCEPTED như chưa có chuyện gì.

### 19.4. Trạng thái xử lý

~~~text
RECEIVED
   |
   v
DISPATCH_PENDING
   |
   v
EXECUTING
   |
   +--> EFFECT_COMMITTED --> COMPLETED
   |
   +--> FAILED_TERMINAL
   |
   +--> NEEDS_RECONCILIATION
~~~

Khi retry, chỉ skip khi state cho phép kết luận outcome; `RECEIVED` không có nghĩa đã thực hiện effect.

### 19.5. Bounded retry và policy phân loại

| Lỗi | Retry? | Điều kiện |
| --- | --- | --- |
| Schema/version unsupported | Không retry nguyên payload vô hạn | Fix contract/producers |
| Authorization denied | Không tự retry | Audit/khắc phục quyền |
| Business rejection dứt khoát | Không retry như lỗi network | Chờ request mới |
| Transient connection reset | Có thể | Stable operationId, bounded backoff |
| Rate limited | Theo Retry-After/deadline nếu có | Bounded attempts |
| Timeout sau gửi lệnh có effect | Cần reconcile/idempotent retry | Không tạo effect trùng |
| Reply requestId mismatch | Không accept reply | Quarantine/security alert |

Không dùng một retry advice chung cho tất cả exceptions nếu có cả lỗi dữ liệu vĩnh viễn lẫn lỗi hạ tầng tạm thời.

## 20. Outbox, inbox và khoảng hở crash

Idempotency không chỉ là unique index. Nếu ghi trạng thái SEEN rồi crash trước khi dispatch, một message có thể **không bao giờ được xử lý**:

~~~text
1. INSERT inbox(op-91, state=SEEN)
2. COMMIT
3. Crash before remote side effect
4. Request is redelivered
5. "op-91 exists" -> drop
6. Effect never happens
~~~

Các lựa chọn:

- **Transactional outbox:** trong cùng DB transaction ghi state nhận và task cần dispatch; worker phát task và cập nhật trạng thái có recovery.
- **Inbox state machine:** claim operation, chuyển trạng thái, có lease/reaper để xử lý in-flight sau crash.
- **Idempotent external provider API:** gửi stable provider idempotency key; tra trạng thái trước khi retry nếu outcome unknown.
- **Compensation/Saga:** khi nhiều remote effects không có transaction chung, định nghĩa thao tác bù, điều kiện kích hoạt và giới hạn.

Đừng gọi một RPC method rồi mặc định có **exactly-once distributed transaction**. Spring Integration có thể hỗ trợ message delivery, retry, persistence và advice, nhưng application vẫn phải quyết định **business effect semantics**.

### 20.1. Retry một request không được sửa nghĩa

Nếu quote rateVersion thay đổi sau khi caller timeout, cùng requestId có thể cho giá khác trong lần xử lý lại. Nếu contract yêu cầu cùng operationId cho cùng result, lưu **reply snapshot/rate version** khi lần đầu hoàn thành; không recompute với rule mới rồi gọi đó là replay bình thường.

### 20.2. Rebuild projection khác replay side effect

Replay historical request để tạo reporting/read model không được tự gửi lại charge/reserve/booking. Phân tách processing mode hoặc dùng immutable event log + idempotency ledger; mọi re-execution có effect cần authorization và policy rõ.

## 21. Chuyển contract từ đồng bộ sang bất đồng bộ

Nếu remote operation mất vài phút hoặc nhiều downstream systems, không nên kéo dài một Gateway invocation vô hạn. Một lựa chọn là **request → accepted receipt → completion event**:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API / Gateway
    participant W as Durable workflow
    participant P as External provider
    C->>A: POST command, operationId=op-91
    A->>W: Persist command / outbox
    A-->>C: 202 Accepted, operationId
    W->>P: Execute with idempotency key
    P-->>W: Completion callback / result
    W->>W: Verify identity, record terminal outcome
    C->>A: GET /operations/op-91
    A-->>C: COMPLETED / REJECTED / PENDING
~~~

### 21.1. Accepted không có nghĩa completed

~~~json
{
  "contractVersion": 1,
  "operationId": "op-91",
  "outcome": "ACCEPTED",
  "statusRef": "operations/op-91",
  "acceptedAt": "2026-11-21T03:00:00Z"
}
~~~

Contract phải nói rõ **đã persist tới đâu** khi trả ACCEPTED: chỉ nhận trong memory, broker accepted hay đã commit outbox transaction? Nếu system có thể crash mất command ngay sau 202, `ACCEPTED` đang gây hiểu lầm.

### 21.2. Completion event cần chống duplicate và sai nguồn

~~~json
{
  "contractVersion": 1,
  "operationId": "op-91",
  "eventId": "evt-complete-op-91-v1",
  "outcome": "COMPLETED",
  "completedAt": "2026-11-21T03:04:00Z"
}
~~~

Một callback phải có authentication/signature hoặc broker ACL, verify tenant + operation ownership, và dedup theo event/operation identity. Không nhận completion chỉ vì người gửi biết `op-91`.

### 21.3. Poll hay subscribe?

- **Poll status:** đơn giản cho người dùng cần truy trạng thái; cần rate limit, TTL, quyền truy cập.
- **Webhook/callback:** độ trễ thấp nhưng cần auth, retry, dedup, replay protection và webhook delivery policy.
- **Message consumer:** phù hợp hệ thống backend cùng broker/stream; vẫn cần persisted offset/inbox.

Không yêu cầu client tự đi gọi một `statusUrl` do remote producer không tin cậy chỉ định; nếu backend chủ động fetch URL tùy ý, có rủi ro SSRF. Dùng trusted service registry hoặc ID-based route cho status queries.

### 21.4. Khi nào dùng Scatter-Gather?

Nếu một shipment cần báo giá từ ba providers rồi chọn giá tốt nhất, có thể dùng Scatter-Gather và một Aggregator. Contract cần:

- Correlation key gắn đúng tenant+shipment+workflow epoch.
- Expected provider set hoặc manifest.
- One **terminal result** per provider operation, không đếm retries là kết quả mới.
- Release policy khi đủ unique outcomes hoặc deadline tới.
- Chính sách **partial results** và late arrivals.
- Một final reply hoặc một async completion event có schema rõ.

Một Gateway đang chờ một result không tự tổng hợp ba replies cho đúng nghiệp vụ; Aggregator phải đảm nhiệm hợp đồng đó.

## 22. Error handling trên Spring Integration channels

Lỗi của request/reply contract có thể xảy ra ở nhiều điểm:

~~~mermaid
flowchart TD
    A["Gateway invocation"] --> B{"Argument binding + send"}
    B -->|"Invalid / no subscriber"| E1["Invocation / send error"]
    B -->|"Dispatched"| C{"Handler"}
    C -->|"Business reject"| R["Typed ShippingQuoteRejected"]
    C -->|"Validation/security exception"| E2["Fail + audit"]
    C -->|"Transient infrastructure"| E3["Retry / errorChannel / recover"]
    C -->|"Success"| O["ShippingQuoteSuccess"]
    O --> D{"Reply path"}
    R --> D
    D -->|"On time"| G["Gateway return"]
    D -->|"Late / missing"| E4["Timeout / UNKNOWN"]
~~~

### 22.1. Lỗi trên DirectChannel

Trong cấu hình demo, `rpcQuoteRequests` là **DirectChannel**. Handler thường chạy trên thread caller, và exception có thể lan ngược về Gateway, được Spring Integration wrap theo cơ chế MessagingException.

Không phải cứ handler throw exception là framework tự đưa Message sang `errorChannel` rồi trả ShippingQuoteRejected; cách lỗi được chuyển phụ thuộc topology/advice/error configuration.

### 22.2. Lỗi trên ExecutorChannel/poller

Nếu chuyển sang ExecutorChannel, worker thread hoặc poller, exception có thể tạo **ErrorMessage** tới một error channel thích hợp. ErrorMessage mang Throwable (có thể tham chiếu failedMessage), **không phải** payload ShippingQuoteReply thông thường.

Error flow phải tìm lại requestId, tenant và operationId từ **nguồn đáng tin/persisted state**, phân loại lỗi, rồi quyết định reply/retry/recovery. Đừng đọc `errorMessage.getPayload()` như `ShippingQuoteRequest` mà không kiểm tra kiểu.

### 22.3. Khi nào đổi error thành typed reply?

Chỉ khi remote có bằng chứng **kết quả nghiệp vụ dứt khoát** và hợp đồng định nghĩa code tương ứng. Ví dụ `SERVICE_LEVEL_UNAVAILABLE` là business rejection. Nhưng:

~~~text
SQLException
SocketTimeoutException
ConnectionReset
UnknownCommitState
~~~

không tự trở thành QUOTED hoặc REJECTED. Với lỗi kỹ thuật biết chắc có thể trả structured technical fault theo contract; với timeout không nhận reply, caller có thể chỉ nhận exception/UNKNOWN.

### 22.4. errorChannel khác durable dead-letter queue

`errorChannel` là khái niệm routing lỗi trong Spring Integration. Nếu cần xử lý sau restart, phải cấu hình persistent transport/storage, retry metadata, ownership và retention; một PublishSubscribeChannel hoặc QueueChannel in-memory không tự bền.

### 22.5. Phân biệt retryable với safe-to-retry

Một HTTP 503/SocketTimeout có thể là transient, nhưng nếu operation `chargePayment` đã commit rồi reply mất, **gửi lại một operationId mới** không an toàn. “Lỗi có thể hồi phục” và “operation có thể retry an toàn” là hai câu hỏi riêng.

## 23. Security: request/reply contract cần bảo vệ cả hai chiều

Một RPC-like flow có rủi ro request giả mạo, reply giả mạo, correlation collision và lộ thông tin giữa tenants.

### 23.1. Ở đầu request

1. Authenticate caller/producer.
2. Bind tenant và principal từ nguồn tin cậy.
3. Authorize operation + shipmentId + workflow epoch.
4. Validate input schema, kích thước, enum, range và currency.
5. Bind requestId/operationId với payload và tenant đã xác minh.
6. Tạo Spring Message với **header allowlist**.
7. Giới hạn timeout, rate, queue capacity và max message size.

Không dùng JSON field `tenantId` do client tự khai làm bằng chứng đã xác thực.

### 23.2. Ở đầu reply

1. Xác minh nguồn remote reply/certificate/broker ACL.
2. Decode reply theo negotiated schemaVersion.
3. So sánh requestId và, khi cần, tenant/operation binding.
4. Kiểm tra reply outcome fields hợp lệ và đúng kiểu.
5. Chặn replay/conflicting terminal outcomes.
6. Không trả reply của tenant A cho caller tenant B.
7. Sanitize technical fault messages.

### 23.3. Correlation ID không phải bí mật

Một requestId/correlationKey có thể xuất hiện trong logs hoặc bị đoán. Nó **không** được dùng làm secret token hoặc thay authentication. Với status endpoints, kiểm tra actor có quyền với operationId; không chỉ kiểm tra request có biết ID hay không.

### 23.4. Không copy framework control headers từ bên ngoài

Các headers `replyChannel`, `errorChannel`, `routingSlip` có thể ảnh hưởng message route. Một external producer không được tự quyết định các destination nội bộ. Ingress phải xây Message mới hoặc lọc headers theo allowlist; selected business metadata chỉ được tin sau khi verify.

### 23.5. Không deserialize tùy ý class names

Một wire field `"javaClass":"com.example.RemoteCommand"` do client gửi không được đưa vào arbitrary polymorphic deserialization. Chọn DTO theo **operation + contractVersion** trong allowlist/schema registry; giới hạn depth/size và validate nội dung sau parse.

### 23.6. Không log raw sensitive requests/replies

Ngay cả một ShippingQuoteRequest có thể chứa customer address trong ứng dụng thật. Logs nên lưu requestRef, stage, outcome và mã lỗi; raw payload/quarantine cần access control, encryption, retention và audit.

## 24. Observability cho contract request/reply

Một lỗi `RPC_FAILED` tổng quát không đủ để biết request chưa gửi, remote xử lý lỗi hay reply bị mất. Cần phân tách các giai đoạn.

| Metric | Ý nghĩa | Labels hữu hạn |
| --- | --- | --- |
| `rpc_requests_total` | Request bắt đầu | operation, version |
| `rpc_dispatch_failed_total` | Gửi vào channel/transport lỗi | operation, reason |
| `rpc_request_validation_failed_total` | Request schema/identity invalid | reasonCode |
| `rpc_business_rejected_total` | Server trả business rejection | code |
| `rpc_success_total` | Nhận QUOTED hợp lệ | operation, version |
| `rpc_reply_timeout_total` | Caller không nhận reply đúng hạn | operation |
| `rpc_reply_mismatch_total` | Reply requestId/version không khớp | reasonCode |
| `rpc_reply_schema_failed_total` | Reply không decode/validate | version |
| `rpc_inflight_requests` | Số requests đang đợi | operation |
| `rpc_request_duration_seconds` | Latency từ caller đến reply | operation |
| `rpc_pending_operations` | Số operations chưa terminal | state |
| `rpc_idempotency_conflict_total` | Cùng key payload khác | operation |
| `rpc_retry_attempt_total` | Retry tạm thời | reasonClass |
| `rpc_late_reply_total` | Reply đến sau deadline | operation |

Không dùng requestId, shipmentId, tenantId hoặc traceId làm **metric label** vì cardinality cao và có thể lộ dữ liệu. Dùng structured logs/traces có search và retention phù hợp.

### 24.1. Log có cấu trúc khi dispatch

~~~json
{
  "component": "ShippingQuoteGateway",
  "stage": "REQUEST_DISPATCH",
  "operation": "QUOTE_SHIPPING",
  "contractVersion": 1,
  "requestRef": "req-quote-00091",
  "outcome": "SENT"
}
~~~

### 24.2. Log có cấu trúc khi có reply

~~~json
{
  "component": "QuoteRpcHandler",
  "stage": "REPLY",
  "contractVersion": 1,
  "requestRef": "req-quote-00091",
  "replyType": "QUOTED",
  "rateVersion": "rate-demo-v1",
  "outcome": "COMPLETED"
}
~~~

### 24.3. Log khi không có reply

~~~json
{
  "component": "ShippingQuoteGateway",
  "stage": "REPLY_WAIT",
  "requestRef": "req-quote-00091",
  "reason": "TIMEOUT",
  "businessOutcome": "UNKNOWN"
}
~~~

Những ví dụ là **log ứng dụng định nghĩa**, không phải format Spring Integration tự sinh. Nếu Gateway timeout trước khi handler chạy, logging chỉ trong handler sẽ không ghi được request đó; cần instrumentation ở cả caller, adapter và remote.

### 24.4. SLO/alerts cần gắn với outcome

Một SLO “99% HTTP 200” có thể bị che khuất nếu API luôn trả 200 với `outcome=REJECTED` hoặc `outcome=UNKNOWN`. Đo:

- Tỷ lệ QUOTED trên các request hợp lệ.
- Tỷ lệ business rejection theo mã (không tính như availability outage).
- Timeout/reply-lost theo transport.
- Backlog của pending/needs-reconciliation.
- Latency p95/p99 và deadline violations.
- Event ID conflicts, duplicate effect prevention và late replies.

## 25. Unit test: request/reply invariants và business semantics

Unit tests cho `QuoteDecisionService` nên kiểm tra cả **giá trị** và **outcome type**. Không chỉ assert reply khác null.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Currency;

import org.junit.jupiter.api.Test;

class QuoteDecisionServiceTest {

    private final Clock fixedClock = Clock.fixed(
            Instant.parse("2026-11-21T03:00:00Z"),
            ZoneOffset.UTC);
    private final QuoteDecisionService service =
            new QuoteDecisionService(fixedClock);

    private ShippingQuoteRequest request(
            String requestId,
            ShippingServiceLevel level,
            int parcelCount) {
        return new ShippingQuoteRequest(
                1, requestId, "SHIP-901",
                level, parcelCount, "VND");
    }

    @Test
    void expressRequestProducesTypedSuccessfulReply() {
        ShippingQuoteRequest input = request(
                "req-quote-901",
                ShippingServiceLevel.EXPRESS, 2);

        ShippingQuoteReply reply = service.decide(input);
        assertInstanceOf(ShippingQuoteSuccess.class, reply);

        ShippingQuoteSuccess success = (ShippingQuoteSuccess) reply;
        assertEquals(1, success.contractVersion());
        assertEquals(input.requestId(), success.requestId());
        assertEquals(input.shipmentId(), success.shipmentId());
        assertEquals(new BigDecimal("160000"),
                success.price().amount());
        assertEquals(Currency.getInstance("VND"),
                success.price().currency());
        assertEquals("rate-demo-v1", success.rateVersion());
        assertEquals(Instant.parse("2026-11-21T03:10:00Z"),
                success.validUntil());
    }

    @Test
    void standardRequestHasDifferentPriceButSameSchema() {
        ShippingQuoteReply reply = service.decide(
                request("req-standard-901",
                        ShippingServiceLevel.STANDARD, 2));

        ShippingQuoteSuccess success =
                assertInstanceOf(ShippingQuoteSuccess.class, reply);
        assertEquals(new BigDecimal("60000"),
                success.price().amount());
        assertEquals(1, success.contractVersion());
    }

    @Test
    void businessRuleCanRejectWithoutThrowingTransportError() {
        ShippingQuoteRequest input = request(
                "req-too-many-parcels",
                ShippingServiceLevel.EXPRESS, 21);

        ShippingQuoteReply reply = service.decide(input);

        ShippingQuoteRejected rejected =
                assertInstanceOf(ShippingQuoteRejected.class, reply);
        assertEquals(input.requestId(), rejected.requestId());
        assertEquals("SERVICE_LEVEL_UNAVAILABLE",
                rejected.code());
        assertFalse(rejected.retryable());
    }

    @Test
    void invalidRequestVersionIsRejectedBeforeHandler() {
        assertThrows(IllegalArgumentException.class, () ->
                new ShippingQuoteRequest(
                        99, "req-901", "SHIP-901",
                        ShippingServiceLevel.STANDARD, 2, "VND"));
    }

    @Test
    void invalidParcelCountIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                request(
                        "req-invalid",
                        ShippingServiceLevel.STANDARD, 0));
    }

    @Test
    void nonVndQuoteAmountIsNotSilentlyAccepted() {
        assertThrows(IllegalArgumentException.class, () ->
                new QuoteMoney(
                        new BigDecimal("12.35"),
                        Currency.getInstance("USD")));
    }

    @Test
    void vndFractionIsNotSilentlyRounded() {
        assertThrows(ArithmeticException.class, () ->
                new QuoteMoney(
                        new BigDecimal("1200.25"),
                        Currency.getInstance("VND")));
    }

    @Test
    void sameInputAndClockProduceSameBusinessReply() {
        ShippingQuoteRequest input = request(
                "req-repeat",
                ShippingServiceLevel.EXPRESS, 2);
        assertEquals(service.decide(input), service.decide(input));
    }
}
~~~

Test cuối dùng **fixed Clock**. Với system clock thật, `validUntil` có thể khác giữa hai calls; điều này chứng minh business logic chưa tự có **persisted exactly-once reply snapshot**. Nếu contract yêu cầu replay cùng requestId trả cùng `validUntil`, cần lưu result đã commit theo idempotency key.

### 25.1. Test đối chiếu header và requestId không chạy annotation resolver

Có thể gọi trực tiếp handler:

~~~java
@Test
void handlerRejectsMismatchedRequestIdHeader() {
    QuoteRpcHandler handler = new QuoteRpcHandler(
            new QuoteDecisionService(fixedClock));
    ShippingQuoteRequest input = request(
            "req-correct",
            ShippingServiceLevel.STANDARD, 1);

    assertThrows(SecurityException.class, () ->
            handler.handle(
                    input,
                    "tenant-a",
                    "req-different"));
}
~~~

Đây là **unit test Java**; framework chưa resolve `@Header`. Để chứng minh MessageHeaders được ánh xạ vào Java parameters và reply về Gateway, phải chạy integration test có Spring context.

### 25.2. Test requestId cùng với nhiều tenants

Nếu requestId duy nhất trong một producer/tenant scope, cùng chuỗi requestId ở hai tenants có thể đại diện hai logical requests khác nhau. Ledger và authorization phải dùng namespace tương ứng. Đừng dùng String requestId đơn độc làm khóa toàn cục nếu hợp đồng không bảo đảm globally unique.

## 26. Integration test: Gateway proxy và Service Activator thật

Test dưới đây không tự dựng Spring Message; nó gọi **Gateway proxy** và để Spring Integration tạo request headers, gửi vào DirectChannel rồi nhận reply của `QuoteRpcHandler`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(QuoteRpcConfig.class)
class QuoteRpcIntegrationTest {

    @Autowired
    ShippingQuoteGateway gateway;

    private ShippingQuoteRequest request(
            String id,
            ShippingServiceLevel level,
            int parcels) {
        return new ShippingQuoteRequest(
                1, id, "SHIP-901", level, parcels, "VND");
    }

    @Test
    void gatewayMapsPayloadAndRequestIdHeaderToHandler() {
        ShippingQuoteRequest command = request(
                "req-int-1", ShippingServiceLevel.EXPRESS, 2);

        ShippingQuoteReply reply = gateway.quote(
                command, "tenant-a", command.requestId());

        ShippingQuoteSuccess success =
                assertInstanceOf(ShippingQuoteSuccess.class, reply);
        assertEquals(command.requestId(), success.requestId());
        assertEquals("SHIP-901", success.shipmentId());
        assertEquals(new BigDecimal("160000"),
                success.price().amount());
        assertEquals("rate-demo-v1", success.rateVersion());
        assertEquals(Instant.parse("2026-11-21T03:10:00Z"),
                success.validUntil());
    }

    @Test
    void gatewayReturnsTypedBusinessRejection() {
        ShippingQuoteRequest command = request(
                "req-int-2", ShippingServiceLevel.EXPRESS, 21);

        ShippingQuoteReply reply = gateway.quote(
                command, "tenant-a", command.requestId());

        ShippingQuoteRejected rejected =
                assertInstanceOf(ShippingQuoteRejected.class, reply);
        assertEquals("req-int-2", rejected.requestId());
        assertEquals("SERVICE_LEVEL_UNAVAILABLE",
                rejected.code());
        assertFalse(rejected.retryable());
    }

    @Test
    void separateRequestsRetainTheirOwnIdentities() {
        ShippingQuoteRequest first = request(
                "req-int-A", ShippingServiceLevel.STANDARD, 1);
        ShippingQuoteRequest second = request(
                "req-int-B", ShippingServiceLevel.EXPRESS, 3);

        ShippingQuoteReply replyA = gateway.quote(
                first, "tenant-a", first.requestId());
        ShippingQuoteReply replyB = gateway.quote(
                second, "tenant-a", second.requestId());

        assertEquals("req-int-A", replyA.requestId());
        assertEquals("req-int-B", replyB.requestId());
        assertNotEquals(replyA.requestId(), replyB.requestId());
    }

    @Test
    void requestIdHeaderMismatchIsRejected() {
        ShippingQuoteRequest command = request(
                "req-int-3", ShippingServiceLevel.STANDARD, 1);

        // Exception ngoài cùng có thể là MessagingException.
        assertThrows(RuntimeException.class, () ->
                gateway.quote(
                        command,
                        "tenant-a",
                        "req-forged"));
    }

    @Test
    void missingTenantIsNotAccepted() {
        ShippingQuoteRequest command = request(
                "req-int-4", ShippingServiceLevel.STANDARD, 1);

        assertThrows(RuntimeException.class, () ->
                gateway.quote(
                        command,
                        null,
                        command.requestId()));
    }
}
~~~

### 26.1. Điều mà integration test chứng minh

- Spring context đăng ký Gateway proxy qua `@IntegrationComponentScan`.
- `@Payload` và `@Header` trên Gateway map Java arguments thành Message.
- Service Activator nhận được typed request và header tương ứng.
- Reply QUOTED/REJECTED quay về đúng synchronous Gateway invocation.
- RequestId mismatch không được trả lời như một success.

### 26.2. Điều integration test chưa chứng minh

- HTTP/JMS/AMQP network converter/headers hoạt động đúng.
- Reply correlation giữa nhiều instances qua broker.
- Authorization với JWT/mTLS/ACL hoặc shipment ownership thực.
- Durable idempotency/outbox khi crash.
- Timeout/cancellation khi remote treo.
- Business operation có side effect được thực hiện đúng một lần.

**Đây là test contract ở Spring runtime trong cùng JVM**, không thay thế end-to-end tests với transport và database thực.

### 26.3. Lưu ý khi chạy test theo version

Với các dòng Spring Integration mới, `@MessagingGateway`, `@Gateway`, `@ServiceActivator`, `@EnableIntegration` và `@IntegrationComponentScan` là API phổ biến. Khi ghép snippets vào module thật, cần đặt interfaces và config đúng package, dùng dependency Spring Test/JUnit phù hợp và kiểm tra external converter configuration. Bài này thuộc STEP 4, chưa chạy Content QA/Gradle.

## 27. Negative tests: contract phải fail rõ trước khi gây side effect

Một RPC-like system cần nhiều test **không thành công** hơn là chỉ có happy path. Các lỗi nặng nhất thường là response thuộc sai request, tenant bị nhầm, unknown schema được coi là success hoặc retry tạo effect trùng.

### 27.1. Bảng test tối thiểu

| Case | Tình huống | Kết quả cần khẳng định |
| --- | --- | --- |
| **Missing requestId** | Request thiếu logical identity | Reject trước dispatch |
| **Unsupported version** | contractVersion=99 | Reject/unsupported schema |
| **Invalid parcelCount** | 0 hoặc 1001 | Validation error |
| **Unknown currency** | USD trong demo VND-only | Không tự đổi tiền |
| **Unknown service level** | Enum `DRONE` chưa hỗ trợ | Parse/validation reject |
| **Header/request mismatch** | businessRequestId khác requestId | Exception/reject |
| **Tenant spoofing** | Caller tự khai tenant-admin | Facade authorization reject |
| **Wrong reply ID** | Reply requestId khác request | Reject, không trả về caller khác |
| **Wrong reply version** | Reply v2 cho v1-only client | Reject/compatibility path |
| **Invalid money precision** | 12.50 VND theo chính sách no fractional | Reject, không round |
| **No responder** | Handler không có reply | Reply timeout/technical failure |
| **Late reply** | Reply sau deadline | Không gắn vào invocation khác |
| **Duplicate request** | Cùng operationId, payload giống | Không tạo side effect mới |
| **Identity conflict** | Cùng operationId, payload khác | ID_CONFLICT |
| **Broker redelivery** | Consumer xử lý lại sau crash | Recovery/idempotent |
| **Transport header loss** | businessRequestId mất qua JMS mapper | Contract test phát hiện |
| **Invalid error code** | Một error code ngoài allowlist | Unknown error policy, không giả QUOTED |
| **Callback không xác thực** | Người ngoài biết operationId | Reject |
| **Expired quote** | validUntil đã qua | Không dùng giá cũ |
| **Cross-tenant reply** | Tenant B nhận result tenant A | Security failure |

### 27.2. Thử reply sai requestId tại facade

Test riêng cho tầng application, có thể giả Gateway bằng lambda vì interface `ShippingQuoteGateway` chỉ có một abstract method trong ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class QuoteApplicationFacadeTest {

    @Test
    void rejectsReplyForAnotherRequest() {
        ShippingQuoteGateway wrongGateway =
                (request, tenant, businessRequestId) ->
                        new ShippingQuoteRejected(
                                1,
                                "req-other",
                                "SERVICE_LEVEL_UNAVAILABLE",
                                false,
                                "Not available");

        QuoteAuthorization allowDemo =
                (actor, request) -> { /* test-only */ };
        QuoteRequestRegistry allowIdentity =
                (actor, request) -> { /* test-only */ };

        QuoteApplicationFacade facade = new QuoteApplicationFacade(
                wrongGateway, allowDemo, allowIdentity);

        ShippingQuoteRequest request = new ShippingQuoteRequest(
                1, "req-original", "SHIP-901",
                ShippingServiceLevel.STANDARD, 1, "VND");

        assertThrows(IllegalStateException.class, () ->
                facade.getQuote(
                        request,
                        new AuthenticatedQuoteActor(
                                "principal-1", "tenant-a")));
    }

    @Test
    void authorizationRunsBeforeSendingMessage() {
        final int[] invoked = {0};
        ShippingQuoteGateway gateway =
                (request, tenant, id) -> {
                    invoked[0]++;
                    return new ShippingQuoteRejected(
                            1, request.requestId(),
                            "SERVICE_LEVEL_UNAVAILABLE",
                            false, "Not available");
                };
        QuoteAuthorization deny =
                (actor, request) -> {
                    throw new SecurityException("SHIPMENT_ACCESS_DENIED");
                };
        QuoteRequestRegistry registry =
                (actor, request) -> { /* test-only */ };
        QuoteApplicationFacade facade =
                new QuoteApplicationFacade(gateway, deny, registry);

        ShippingQuoteRequest request = new ShippingQuoteRequest(
                1, "req-auth", "SHIP-901",
                ShippingServiceLevel.STANDARD, 1, "VND");

        assertThrows(SecurityException.class, () ->
                facade.getQuote(
                        request,
                        new AuthenticatedQuoteActor(
                                "principal-2", "tenant-b")));
        assertEquals(0, invoked[0]);
    }
}
~~~

**Cảnh báo:** hai lambda `allowDemo` và `allowIdentity` là stub dành riêng test; không sao chép thành authorization thực. Production phải tra quyền từ identity provider/registry, bao gồm tenant ownership và operation scope.

### 27.3. Test timeout đúng với semantics channel

Một test không có handler có thể tạo send failure hoặc reply timeout tùy channel. **Đừng viết test giả định mọi topology đều ném cùng một Gateway timeout exception**. Nên tạo test configuration riêng cho từng trường hợp:

1. **RequestChannel không có subscriber** → kiểm tra lỗi dispatch.
2. **Consumer nhận Message nhưng không reply** → kiểm tra reply wait/timeout.
3. **DirectChannel handler block** → kiểm tra thời gian caller bị giữ, không giả định replyTimeout tự interrupt handler.
4. **ExecutorChannel handler chậm** → kiểm tra receive timeout và xử lý late reply.
5. **Transport reset after effect** → kiểm tra reconciliation thay vì tạo operationId mới.

Giữ timeout ngắn trong tests, dùng `CountDownLatch` hoặc fake Clock/controlled executor khi phù hợp để tránh flaky tests phụ thuộc `Thread.sleep()`.

### 27.4. Test error taxonomy

Tách ít nhất:

- Request không parse được → schema/validation failure.
- Header/requestId không khớp → contract/identity failure.
- Không có quyền tenant → authorization failure.
- Service không phục vụ yêu cầu → typed ShippingQuoteRejected.
- Remote timeout → technical UNKNOWN.
- Reply sai requestId → correlation mismatch.
- Side effect đã commit nhưng reply mất → reconcile/idempotent read.

Nếu tất cả đều xuất thành cùng string `"ERROR"`, consumer không thể quyết định khi nào retry an toàn.

## 28. Wire contract tests: không serialize domain records theo cảm tính

Domain Java records có cấu trúc thuận tiện nhưng không nhất thiết trùng schema JSON công bố. Ví dụ `QuoteMoney` là Java record chứa `BigDecimal` và `Currency`; nếu serialize mặc định, cách biểu diễn có thể là number/string tùy converter, trong khi contract ví dụ yêu cầu **decimal string**.

### 28.1. Tạo wire DTO rõ kiểu

~~~java
record QuoteMoneyWire(
        String amount,
        String currencyCode) {
}

record QuoteSuccessBodyWire(
        String shipmentId,
        QuoteMoneyWire money,
        String rateVersion,
        String validUntil) {
}

record QuoteSuccessWire(
        int contractVersion,
        String requestId,
        String outcome,
        QuoteSuccessBodyWire result) {

    static QuoteSuccessWire from(ShippingQuoteSuccess domain) {
        QuoteMoney money = domain.price();
        return new QuoteSuccessWire(
                domain.contractVersion(),
                domain.requestId(),
                "QUOTED",
                new QuoteSuccessBodyWire(
                        domain.shipmentId(),
                        new QuoteMoneyWire(
                                money.amount().toPlainString(),
                                money.currency().getCurrencyCode()),
                        domain.rateVersion(),
                        domain.validUntil().toString()));
    }
}
~~~

Wire schema mới có `result.money.amount` thay vì `result.amount` ở JSON minh họa mục 4. Nếu **đã công bố** JSON mục 4, không được thay đường dẫn field âm thầm. Hai lựa chọn đúng:

- Giữ contract mục 4 bằng cách đổi `QuoteSuccessBodyWire` thành `amount` và `currencyCode` trực tiếp.
- Hoặc công bố schema **v2** với nested money object và migration policy.

Để các ví dụ của bài **nhất quán với v1**, chúng ta chọn dạng **flat result fields** ở bước kế tiếp.

### 28.2. Flat result wire DTO đúng schema v1

~~~java
record QuoteSuccessResultV1(
        String shipmentId,
        String amount,
        String currencyCode,
        String rateVersion,
        String validUntil) {
}

record QuoteSuccessWireV1(
        int contractVersion,
        String requestId,
        String outcome,
        QuoteSuccessResultV1 result) {

    static QuoteSuccessWireV1 from(ShippingQuoteSuccess domain) {
        return new QuoteSuccessWireV1(
                1,
                domain.requestId(),
                "QUOTED",
                new QuoteSuccessResultV1(
                        domain.shipmentId(),
                        domain.price().amount().toPlainString(),
                        domain.price().currency().getCurrencyCode(),
                        domain.rateVersion(),
                        domain.validUntil().toString()));
    }
}
~~~

**Dùng QuoteSuccessWireV1 cho contract của bài**, còn `QuoteSuccessWire` nested ở mục 28.1 là một phương án **khác schema, không tương đương**. Ví dụ so sánh giúp nhận ra breaking change tưởng như chỉ là một quyết định tổ chức DTO.

### 28.3. Test JSON contract bằng Jackson

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;
import org.junit.jupiter.api.Test;

class QuoteWireContractTest {

    @Test
    void successReplyMatchesPublishedVersionOneShape()
            throws Exception {

        ShippingQuoteSuccess domain = new ShippingQuoteSuccess(
                1,
                "req-quote-00091",
                "SHIP-901",
                new QuoteMoney(
                        new BigDecimal("160000"),
                        Currency.getInstance("VND")),
                "rate-demo-v1",
                Instant.parse("2026-11-21T03:10:00Z"));

        ObjectMapper mapper = new ObjectMapper();
        QuoteSuccessWireV1 wire = QuoteSuccessWireV1.from(domain);
        JsonNode root = mapper.readTree(
                mapper.writeValueAsBytes(wire));

        assertEquals(1, root.path("contractVersion").asInt());
        assertEquals("req-quote-00091",
                root.path("requestId").asText());
        assertEquals("QUOTED", root.path("outcome").asText());
        assertEquals("SHIP-901",
                root.path("result").path("shipmentId").asText());
        assertEquals("160000",
                root.path("result").path("amount").asText());
        assertEquals("VND",
                root.path("result").path("currencyCode").asText());
        assertEquals("2026-11-21T03:10:00Z",
                root.path("result").path("validUntil").asText());
        assertTrue(root.path("error").isMissingNode());
    }
}
~~~

Test này dùng **wire DTO với String validUntil**, nên không cần Jackson JavaTimeModule để serialize một `Instant` trực tiếp. Nếu chuyển sang serialize domain records có Instant, phải cấu hình Java Time module phù hợp.

### 28.4. Chọn đúng reply variant khi decode

Khi nhận JSON:

1. Đọc `contractVersion` và `outcome` theo allowlist.
2. Nếu QUOTED, validate `result` có đủ fields; không có error.
3. Nếu REJECTED, validate `error` có code/retryable/safeMessage; không có success result.
4. Nếu outcome chưa hỗ trợ, trả unsupported reply error; **không default thành QUOTED**.
5. Verify `requestId` và sender identity trước khi trả về Gateway caller.

Đừng bật deserialization dựa trên arbitrary `@class` field từ remote; dùng schema discriminator đã được công bố.

### 28.5. Consumer-driven contracts

Khi có nhiều consumers, mỗi client có thể kiểm chứng các fields mà nó dựa vào: requestId, outcome, price precision, error code và timestamp. Producer contract tests phải chạy trong CI khi thay schema, kể cả khi chỉ đổi MessageConverter/HeaderMapper mà DTO Java không đổi.

## 29. Runbook: caller timeout nhưng không biết remote đã xử lý chưa

**Tình huống:** một Java caller gọi `quoteGateway.quote(...)`, chờ rồi nhận timeout. Thống kê phía remote cho thấy có lúc request được xử lý, có lúc không. Nếu đây là lệnh reserve/charge, retry mù quáng có thể gây tác động trùng.

### Bước 1 — Xác minh hợp đồng request tại caller

Thu thập:

~~~text
operation = QUOTE_SHIPPING
contractVersion = 1
requestId = req-quote-00091
tenant = tenant-a (đã xác minh)
shipmentId = SHIP-901
serviceLevel = EXPRESS
deadline = <the actual application deadline>
~~~

Không cần log raw address/payment payload hay credential. Kiểm tra requestId có ổn định qua attempts không, và có bị đổi khi Gateway proxy được gọi lại không.

### Bước 2 — Xác định request đã gửi tới channel chưa

Phân biệt:

- Gateway mapping/validation lỗi trước khi gửi.
- Request channel không có subscriber.
- Queue/executor full hoặc send timeout.
- Outbound adapter đã nhận message và bắt đầu gọi network.

Nếu lỗi xảy ra **trước khi gửi**, remote có thể chưa thấy request. Nhưng nếu lỗi xảy ra sau network send, chưa thể kết luận operation chưa được xử lý.

### Bước 3 — Kiểm tra protocol correlation

Nếu dùng JMS/AMQP, tìm correlation token/ReplyTo tại **transport layer**; nếu dùng HTTP, tìm request/response trace ở connector; nếu dùng Java Gateway, tìm temporary replyChannel invocation. Không nhầm những token đó với businessRequestId.

### Bước 4 — Kiểm tra remote inbox/operation state

~~~text
requestId = req-quote-00091
operationId = op-91 (nếu là command có side effect)

Remote state:
  RECEIVED / DISPATCH_PENDING / EXECUTING /
  COMPLETED / FAILED_TERMINAL / NEEDS_RECONCILIATION
~~~

- Không có record: có thể chưa tới hoặc dữ liệu chưa được persist; đối chiếu broker/transport.
- RECEIVED/IN_PROGRESS: không được coi là failed; kiểm tra worker/lease/recovery.
- COMPLETED: lấy kết quả đã lưu, không thực hiện effect lần hai.
- ID_CONFLICT: so sánh payload digest/tenant/producer; cần điều tra.
- NEEDS_RECONCILIATION: tra provider hoặc chạy recovery policy.

### Bước 5 — Kiểm tra reply có được tạo đúng contract chưa

Một service có thể đã xử lý nhưng trả:

~~~json
{
  "contractVersion": 1,
  "requestId": "req-other",
  "outcome": "QUOTED",
  "result": {}
}
~~~

Reply này **không hợp lệ cho request hiện tại**: requestId sai, result thiếu fields. Không gửi nó tới caller chỉ vì có một temporary replyChannel đang chờ. Ghi lỗi correlation/schema và quarantine khi cần.

### Bước 6 — Kiểm tra reply path

Xem handler trả DTO hay tự gửi vào một QueueChannel không bridge tới Gateway. Kiểm tra Message mới có làm mất replyChannel, HeaderFilter có loại correlation metadata, và transport header mapper có làm mất replyTo/correlation token hay không.

### Bước 7 — Kiểm tra timeout/deadline

Gateway replyTimeout, remote client timeout, broker TTL và business deadline có thể khác nhau. Một reply đến sau Gateway timeout vẫn có thể là kết quả business hợp lệ, nhưng cần xử lý qua **persistent workflow state**, không gắn vào một invocation mới.

### Bước 8 — Kiểm tra nguyên nhân lỗi

| Dấu hiệu | Phân loại |
| --- | --- |
| Invalid contractVersion, parcelCount | Data/schema |
| Tenant không có quyền | Security |
| ServiceLevel không hỗ trợ | Business rejection |
| DB down | Transient infrastructure |
| Connection reset sau gửi request | UNKNOWN |
| Reply.requestId khác request | Correlation/contract violation |
| Operation đã commit, reply lost | Completed but caller uncertain |

### Bước 9 — Khôi phục có kiểm soát

Nếu operation thuần read-only, có thể gọi lại bằng cùng requestId với policy rate version/expiry phù hợp. Nếu operation tạo side effect, tra ledger/provider bằng stable operationId trước khi retry. Nếu cần retry, dùng cùng identity và giới hạn attempts/deadline.

### Bước 10 — Xác minh sau sửa

Chạy contract tests qua Gateway và adapter, assert:

~~~text
requestId in request == requestId in reply
contractVersion supported
reply is exactly one legal outcome
QUOTED has valid money/time fields
REJECTED has stable code
TIMEOUT stays UNKNOWN until reconciliation
no cross-tenant response
no duplicated business effect
~~~

## 30. Bài thực hành: ba RPC operations và một hợp đồng nhất quán

Hãy xây module `OrderRemoteOperations` gồm ba thao tác, mỗi thao tác có contract riêng:

1. **GetShippingQuote:** read-only, trả giá hoặc business rejection.
2. **ReserveInventory:** command có side effect, cần idempotency + recovery.
3. **RequestCarrierBooking:** xử lý lâu, trả ACCEPTED + completion event.

~~~mermaid
flowchart TD
    C["Order Application"] --> G["Messaging Gateway façade"]
    G --> Q["GetShippingQuote"]
    G --> R["ReserveInventory"]
    G --> B["RequestCarrierBooking"]
    Q --> QQ["QUOTED / REJECTED reply"]
    R --> RR["RESERVED / REJECTED reply"]
    B --> BA["ACCEPTED receipt"]
    BA --> W["Durable booking workflow"]
    W --> EV["BOOKED / FAILED completion event"]
~~~

### 30.1. Các contract cần công bố

| Operation | Request identity | Reply/outcomes | Kỹ thuật bắt buộc |
| --- | --- | --- | --- |
| Quote | requestId | QUOTED, REJECTED, technical UNKNOWN | Versioned price, validUntil |
| Reserve | operationId/idempotencyKey | RESERVED, REJECTED, technical UNKNOWN | Unique ledger, stable side-effect identity |
| Book carrier | operationId | ACCEPTED → BOOKED/FAILED event | Outbox, status API, callback auth |

Không dùng cùng một `Reply` với field nullable không kiểm soát cho mọi operation. Có thể dùng một **base envelope** giống nhau về requestId/version/trace, nhưng từng operation cần typed result và error taxonomy rõ.

### 30.2. Mẫu request inventory

~~~json
{
  "contractVersion": 1,
  "operationId": "op-reserve-1001",
  "orderId": "ORD-1001",
  "items": [
    { "sku": "SKU-RED-001", "quantity": 2 },
    { "sku": "SKU-BLUE-002", "quantity": 1 }
  ]
}
~~~

Định nghĩa: cùng `operationId` với cùng items là redelivery; cùng ID nhưng items khác là conflict. Reservation có thể bị từ chối vì hết hàng (business), hoặc pending/UNKNOWN vì DB/provider mất kết nối (technical). Không gán tất cả các trường hợp thành `OUT_OF_STOCK`.

### 30.3. Mẫu reply inventory

~~~json
{
  "contractVersion": 1,
  "operationId": "op-reserve-1001",
  "outcome": "RESERVED",
  "reservationId": "res-1001",
  "expiresAt": "2026-11-21T03:20:00Z"
}
~~~

Nếu request được redeliver, trả cùng reservationId/expiresAt từ persisted snapshot; không reserve thêm stock chỉ để tạo một reply mới. Nếu kết quả không xác định sau timeout, cần query operation state.

### 30.4. Mẫu accepted booking

~~~json
{
  "contractVersion": 1,
  "operationId": "op-book-1001",
  "outcome": "ACCEPTED",
  "statusRef": "operations/op-book-1001",
  "acceptedAt": "2026-11-21T03:00:00Z"
}
~~~

Từ accepted state, có thể phát terminal event `BOOKED` hoặc `FAILED`. Cần định nghĩa late callback, duplicate callback và quyền tenant khi poll trạng thái.

### 30.5. Các bước triển khai

1. Định nghĩa request DTO riêng cho Quote/Reserve/Book, có version và validation.
2. Định nghĩa typed success/business rejection/accepted result.
3. Định nghĩa error codes ổn định, tách technical exceptions.
4. Tạo authenticated caller context và kiểm tra tenant/order ownership.
5. Tạo requestId/operationId ổn định cho logical operation; persist mapping khi cần.
6. Xây Spring Messaging Gateway interfaces và request/reply channels.
7. Dùng Router theo operation được allowlist, không arbitrary channel name.
8. Dùng Service Activator/Transformer riêng cho mỗi operation.
9. Cho Quote trả một reply đồng bộ với `validUntil`/rateVersion.
10. Cho Reserve dùng transactional inbox/idempotent effect; reply có reservation ID bền.
11. Cho Book trả ACCEPTED sau khi persist command/outbox, kết quả sau qua event.
12. Cấu hình deadlines, request/reply timeouts, transport TTL và retry budgets.
13. Dùng correlation/replyChannel đúng scope, không gộp chúng thành business ID.
14. Chặn malformed requests, unauthorized requests và unknown reply variants.
15. Thêm tests unit/Spring proxy/wire contract/adapter integration.
16. Mô phỏng lost reply sau effect commit; bảo đảm retry không tạo reservation thứ hai.
17. Mô phỏng callback đến sau deadline và redelivery cùng eventId.
18. Thêm metrics, tracing, DLQ/quarantine và recovery runbook.

### 30.6. Ma trận nghiệm thu

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| Quote hợp lệ | QUOTED có amount/currency/rateVersion/validUntil |
| Unsupported serviceLevel | REJECTED hoặc schema error đúng contract |
| RequestId response mismatch | Không giao reply sai caller |
| Reply v2 khi caller v1-only | Compatibility error |
| Cùng reserve operationId replay | Một reservation, cùng receipt |
| Cùng reserve ID payload khác | ID_CONFLICT |
| Lost reserve reply after commit | Lookup/reconcile, không reserve lần hai |
| Carrier booking accepted | Command đã được persist theo contract |
| Callback giả mạo | Authorization/signature reject |
| Callback duplicate | Không phát business effect hai lần |
| Gateway reply timeout | UNKNOWN, không tự chuyển sang REJECTED |
| Hai tenants cùng orderId | Không lộ/ghép lẫn operation |
| Async partial results | Release theo manifest/deadline |
| Network converter mất requestId | Contract test thất bại |
| DLQ replay sau deploy v2 | Version-aware parser/handler |

### 30.7. Tiêu chí đạt

Một nhóm client chỉ đọc **contract documents/schema** phải biết:

- Gửi request nào, field nào bắt buộc và version nào được hỗ trợ.
- Khi nào nhận được QUOTED/RESERVED/ACCEPTED/REJECTED.
- Khi nào phải coi trạng thái là UNKNOWN.
- Dùng requestId/operationId ra sao khi retry.
- Correlate reply và kiểm tra identity như thế nào.
- Khi nào deadline hết và cách tra trạng thái bền.
- Những lỗi nào cần sửa input, những lỗi nào được retry.
- Quyền truy cập và tenant scoping được kiểm tra ở đâu.

Nếu muốn dùng API an toàn mà client phải đọc code triển khai của server để suy đoán những điều này, request/reply contract chưa đủ hoàn chỉnh.

## 31. Câu hỏi tự kiểm tra

1. Remote Procedure Invocation khác lời gọi Java trong cùng JVM ở những failure modes nào?
2. Vì sao một method Java có return type `ShippingQuoteReply` vẫn cần request/reply schema khi đi qua network?
3. Một request contract phải có những thông tin gì ngoài fields nghiệp vụ?
4. Tại sao requestId nên ổn định qua retries của cùng logical request?
5. Có phải requestId và businessCorrelationKey luôn là cùng một giá trị không?
6. Spring MessageHeaders.ID khác businessRequestId ở đâu?
7. Temporary replyChannel của Messaging Gateway có thể lưu bền qua restart được không?
8. JMSCorrelationID/AMQP correlationId có bắt buộc trùng businessRequestId không?
9. Reply có requestId không khớp request gốc phải xử lý thế nào?
10. Vì sao reply QUOTED cần currency, rateVersion và validUntil?
11. Một quote amount dạng `double` có rủi ro gì đối với wire consumers?
12. `ShippingQuoteRejected` khác SocketTimeoutException ở điểm nào?
13. Lỗi serviceLevel không phục vụ có nên trả typed business rejection không?
14. Lỗi DB timeout có thể tự chuyển thành REJECTED không? Vì sao?
15. Vì sao ReplyTimeout không chứng minh server chưa tạo side effect?
16. Với DirectChannel, replyTimeout có bảo đảm chấm dứt handler đang chạy không?
17. Khi nào nên chuyển từ RPC sync sang ACCEPTED + completion event?
18. Một HTTP 202 Accepted cần cam kết đã persist command đến đâu?
19. Vì sao business deadline nên là Instant tuyệt đối qua nhiều service?
20. Cần làm gì với late reply sau khi Gateway caller đã timeout?
21. Tại sao `@Header("trustedTenantId")` không tự thực hiện authentication?
22. Có thể dùng requestId như secret token để tra trạng thái operation không?
23. Khi nào một idempotency key phải bao gồm producerId hoặc operationType?
24. Cùng operationId nhưng payload digest khác có phải duplicate bình thường không?
25. Cửa sổ crash giữa ghi SEEN và dispatch gây lỗi gì?
26. Transactional outbox/inbox giải quyết khoảng hở nào của RPC có side effect?
27. Nếu quote price rule thay đổi giữa retries, làm sao giữ cùng reply theo contract?
28. Versioned upcaster có được tự bịa default có khả năng đổi semantics không?
29. Thêm optional field và đổi nghĩa trường `amount` khác nhau thế nào về compatibility?
30. Tại sao cần tách domain DTO và wire DTO khi biểu diễn tiền tệ?
31. Gateway proxy integration test chứng minh gì mà unit test service không chứng minh được?
32. Một contract test chỉ kiểm tra Jackson JSON có chứng minh HeaderMapper qua JMS đúng không?
33. Khi Splitter tạo nhiều child results, Gateway caller có tự chọn final reply không?
34. Correlation và release strategy của Aggregator có trách nhiệm khác nhau thế nào?
35. Những metric nào giúp phân biệt dispatch failure với reply timeout?
36. Nếu callback completion chứa đúng operationId nhưng đến từ producer giả, xử lý thế nào?
37. Nếu broker nhận ACK nhưng business handler chưa commit, caller có thể coi operation completed không?
38. Vì sao không retry một authorization failure vô hạn?
39. Khi errorChannel nhận ErrorMessage, payload có tự là domain ShippingQuoteRequest không?
40. Đâu là dấu hiệu phải chọn workflow state bền thay vì một Gateway sync invocation?

## 32. Checklist thiết kế và vận hành

### 32.1. Request contract

- Operation name và semantics được mô tả rõ: read-only, idempotent hay side effect.
- Request có version/operation discriminator được định nghĩa.
- Fields bắt buộc, type, length, nullable, enum và unit được công bố.
- requestId hoặc operationId có scope duy nhất, quy tắc cấp và vòng đời rõ.
- Retry của cùng logical operation giữ identity phù hợp.
- Không sử dụng một ID chung cho các business operations khác nhau nếu contract không cho phép.
- Có business deadline nếu operation có time budget xuyên nhiều hops.
- Payload validation xảy ra trước business effect.
- Có policy unknown schema/enum; không tự default thành success.

### 32.2. Reply contract

- Reply echo đúng requestId/operationId để correlate.
- Outcome có kiểu rõ: success, business reject, accepted/pending nếu có.
- Success reply chứa đầy đủ fields đã cam kết: currency, amount precision, rateVersion, expiry.
- Business rejection có stable error code và safe message.
- Technical exception/timeout không được giả thành business rejection dứt khoát.
- Không nhận response sai requestId/version hoặc sai tenant.
- Có behavior cho late reply, duplicate reply và conflicting terminal outcomes.
- Có schema evolution/backward compatibility và consumer-driven contract tests.

### 32.3. Spring Integration topology

- @MessagingGateway interface được đăng ký và request channel có owner rõ.
- @Payload/@Header mappings không mơ hồ, tên header nhất quán.
- Service Activator có một consumer rõ trên DirectChannel nếu flow yêu cầu một handler.
- Handler trả typed reply hoặc định nghĩa đúng one-way semantics.
- Reply channel/temporary destination được giữ theo framework/adapter contract.
- Không nhầm businessCorrelationKey với temporary replyChannel hoặc transport correlation.
- Router/Transformer/Subflow không vô tình làm mất identity.
- Nếu có Splitter/Aggregator, scope group và release strategy được xác định.
- requestTimeout/replyTimeout/remote timeout được đo và kiểm thử theo channel semantics.
- ErrorMessage/errorChannel và DLQ persistence được phân biệt rõ.
- Bounded queues, executors, rate limits và backpressure được cấu hình nếu async.

### 32.4. Security và dữ liệu

- Producer/caller được authenticate.
- Tenant và quyền shipment/order được authorize.
- Không tin custom tenant/role/correlation headers từ client chỉ vì đã map thành Spring header.
- Remote request và reply đều được kiểm chứng source/tenant/operation binding.
- Không deserialize arbitrary Java class names từ wire.
- Không copy control headers `replyChannel`/`errorChannel` tùy ý từ external request.
- Logs, traces, payload quarantine được redact và bảo vệ.
- Error messages không làm lộ stack trace/token/SQL nội bộ.
- Status/callback endpoints kiểm tra quyền operation, không chỉ kiểm tra biết ID.

### 32.5. Reliability và vận hành

- Side-effecting commands có idempotency key và durable ledger.
- Ledger phát hiện same-key/different-payload conflict.
- Có recovery cho khoảng hở giữa accepted, dispatch và commit.
- Retry bounded, backoff/jitter và deadline-aware.
- UNKNOWN state được reconcile, không mặc định coi là NOT_EXECUTED.
- Có policy giữ reply snapshot/rateVersion cho replay.
- Late reply và duplicate callback có xử lý bền.
- Schema migrations bao gồm persisted events, DLQ và replay.
- Metrics phân biệt mapping, send, business reject, remote error, reply timeout.
- Có dashboard/SLO cho pending operations và reconciliation backlog.
- Runbook đã được diễn tập với lost reply sau effect commit.

### 32.6. Kiểm thử

- Unit tests cho request constructor và các reply variants.
- Tests cho amount/currency precision, timestamp và validity.
- Tests cho business rejection vs technical exceptions.
- Spring context test gọi Gateway proxy thật rồi nhận typed reply.
- Tests cho missing/mismatched requestId header và unauthorized tenant.
- Tests cho reply requestId/version không khớp.
- Wire JSON Schema/serialization tests cho v1/v2.
- Adapter contract tests cho HTTP/JMS/AMQP correlation/header mapping.
- Tests cho timeout và late replies ở đúng topology async.
- Tests cho retries/dedup, ID_CONFLICT và process restart.
- Tests cho two tenants same entity ID, không trộn replies.
- Tests cho partial/duplicate results nếu có Scatter-Gather.

## 33. Tổng kết

**Contract của request và reply** trong Remote Procedure Invocation không chỉ là chữ ký một Java method:

~~~text
Verified caller
    |
    +-- Typed request
    |     contractVersion
    |     requestId / operationId
    |     typed business fields
    |
    v
Messaging Gateway -> Spring Integration flow -> remote adapter/service
    |                                          |
    |                                          +-- business success/reject
    |                                          +-- technical error/timeout
    v
Typed reply
    contractVersion
    matching requestId
    exactly one legal outcome
    explicit amount/currency/time/error semantics
~~~

Một contract tốt phân biệt **đã tính xong**, **bị từ chối theo nghiệp vụ**, **được tiếp nhận để xử lý tiếp**, và **không biết remote đã thực hiện hay chưa**. Gateway có thể giúp ứng dụng gọi một API Java gọn và Spring Integration có thể route, transform, retry và correlate messages, nhưng hệ thống vẫn cần **identity ổn định, schema versioning, reply matching, authorization, timeout policy, idempotency và recovery**.

Khi những quy tắc này được công bố và kiểm thử ở cả **domain DTO, Messaging Gateway, Service Activator và wire adapter**, RPC-like integration mới thực sự có thể mở rộng an toàn qua nhiều services và nhiều phiên bản triển khai.

## Tài liệu tham khảo

- [Enterprise Integration Patterns — Integration Styles](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IntegrationStylesIntro.html): các phong cách tích hợp bao gồm File Transfer, Shared Database, Remote Procedure Invocation và Messaging.
- [Enterprise Integration Patterns — Request-Reply](https://www.enterpriseintegrationpatterns.com/patterns/messaging/RequestReply.html): request/reply, correlation identifiers và reply addresses.
- [Enterprise Integration Patterns — Messaging Gateway](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html): che giấu messaging API đằng sau giao diện ứng dụng.
- [Enterprise Integration Patterns — Correlation Identifier](https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html): liên kết reply với request liên quan.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): Messaging Gateway, method mappings, request/reply timeouts và error handling.
- [Spring Integration Reference — Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html): biến Message thành lời gọi POJO, reply và output channels.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel và QueueChannel.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): lỗi đồng bộ/bất đồng bộ, ErrorMessage và error channels.
- [Spring Integration Reference — Routers](https://docs.spring.io/spring-integration/reference/router.html): routing theo metadata và routing defaults.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): payload conversion và header propagation.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): child message sequence/correlation metadata.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): grouping, release strategy, timeout và partial results.
- [Spring Integration Reference — HTTP Support](https://docs.spring.io/spring-integration/reference/http.html): request/reply adapters và gateways qua HTTP.
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): JMS inbound/outbound gateways, headers và correlation.
- [Spring Integration Reference — AMQP Support](https://docs.spring.io/spring-integration/reference/amqp.html): AMQP inbound/outbound gateways và reply behavior.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): idempotency advice và duplicate detection.
- [Spring Framework — Integration testing with Spring TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): dựng Spring context và integration tests.
