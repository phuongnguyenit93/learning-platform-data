# Mapping header vào tham số

## 1. Tại sao Service Activator cần đọc cả payload lẫn headers?

Trong module **SPRING_INTEGRATION_PATTERN**, chúng ta học triển khai Enterprise Integration Patterns bằng **Spring Integration** để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng. Khi Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation phối hợp, một Service Activator thường là nơi kết nối message với một phương thức Java thực hiện nghiệp vụ.

Giả sử một message yêu cầu ghi nhận thanh toán:

~~~text
Spring Message
├── headers
│   ├── trustedTenantId = tenant-a
│   ├── businessEventId = evt-payment-1042
│   ├── businessCorrelationKey = payment:v1:tenant-a:PAY-1042:3
│   ├── sourceSystem = BILLING
│   ├── traceId = trace-abc
│   ├── id = <Spring-generated Message ID>
│   └── timestamp = <Spring-generated timestamp>
└── payload
    ├── paymentId = PAY-1042
    ├── amountMinor = 125000
    ├── currencyCode = VND
    └── workflowEpoch = 3
~~~

Phương thức nghiệp vụ cần biết **số tiền và mã thanh toán** từ payload. Nhưng nó cũng cần **tenant đã xác minh**, **eventId** để chống xử lý trùng, và **businessCorrelationKey** để liên kết workflow. Nếu mỗi handler phải tự duyệt MessageHeaders và ép kiểu thủ công, code dễ trở nên dài, phụ thuộc framework và bỏ sót validation.

Spring Integration cho phép method của Service Activator khai báo những tham số mà nó cần:

~~~java
@ServiceActivator(inputChannel = "verifiedPayments")
public PaymentReceipt handle(
        @Payload PaymentSubmitted payment,
        @Header("trustedTenantId") String tenantId,
        @Header("businessEventId") String eventId,
        @Header("businessCorrelationKey") String groupKey) {
    // ...
}
~~~

Framework lấy payload và các giá trị header từ **Spring Message đang được xử lý**, rồi truyền vào lời gọi Java. Đây là **method argument mapping**, không phải chuyển toàn bộ HTTP headers từ bên ngoài thành dữ liệu đáng tin.

### Mục tiêu bài học

Sau bài này, bạn sẽ:

1. Phân biệt **payload**, **Spring MessageHeaders**, **application/transport headers** và **method arguments**.
2. Dùng **@Payload**, **@Header** và **@Headers** đúng với method gắn **@ServiceActivator**.
3. Hiểu cách xử lý header bắt buộc, header tùy chọn, header sai kiểu và các quy tắc chuyển đổi kiểu.
4. Chọn giữa handler nhận tham số rời, handler nhận **Message<?>**, và Java DSL **.handle(...)**.
5. Thiết kế ranh giới tin cậy để tenant, role, replyChannel hay routing metadata không bị giả mạo.
6. Giữ business correlation, eventId, sequence metadata khi message đi qua subflows/adapter.
7. Phân biệt **handler trả reply** với **handler một chiều**, lỗi sync/async và retry/idempotency.
8. Viết các unit test và Spring Integration integration test xác minh giá trị header được ánh xạ chính xác.

## 2. Service Activator trong Enterprise Integration Patterns

**Service Activator** nối thế giới messaging với một service hoặc phương thức nghiệp vụ. Một Message được gửi đến endpoint; endpoint lấy dữ liệu, gọi Java method và tùy hợp đồng có thể tạo một reply.

~~~mermaid
flowchart LR
    A["Inbound adapter / Gateway"] --> B["MessageChannel"]
    B --> S["Service Activator"]
    S --> M["Java business method"]
    M -->|"Reply payload hoặc Message"| R["Output / reply channel"]
    M -->|"Error"| E["Caller / errorChannel policy"]
~~~

Một Service Activator thường:

- Nhận message đã qua các bước xác thực, routing hoặc chuyển đổi.
- Chuyển các thông tin cần thiết thành Java arguments.
- Gọi service nghiệp vụ, có thể ghi dữ liệu hay gọi hệ thống ngoài.
- Trả kết quả nếu flow yêu cầu request/reply.
- Để framework/flow xử lý reply, exception, retry và error channel theo cấu hình.

**@ServiceActivator** là một annotation endpoint của Spring Integration; **@Payload**, **@Header** và **@Headers** thuộc nhóm annotation cho Spring Messaging method parameters.

### 2.1. Một message không đồng nghĩa một lời gọi HTTP

Cùng một Service Activator có thể được kích hoạt bởi:

- Một Gateway chuyển lời gọi Java sang Spring Message.
- HTTP/JMS/AMQP/Kafka inbound adapter sau bước chuyển đổi và xác thực.
- Một Router hoặc Transformer trong IntegrationFlow.
- Một nhánh con của Splitter hay Aggregator.
- Một message được redeliver sau retry/restart.

Vì vậy **header của Spring Message** không luôn là **header HTTP**. Nguồn có thể là một Java object do nội bộ tạo, một header đã map từ broker, hoặc một giá trị do Gateway/Transformer gắn.

### 2.2. Mapping ở lớp nào?

~~~mermaid
flowchart TD
    W["Wire: HTTP / broker / file"] --> P["Parse + authenticate"]
    P --> M["Spring Message payload + headers"]
    M --> A["@ServiceActivator method invocation"]
    A --> H["@Payload -> Java payload"]
    A --> X["@Header -> một header"]
    A --> Y["@Headers -> Map header"]
    H --> B["Business operation"]
    X --> B
    Y --> B
~~~

**Mapping header vào tham số** diễn ra tại điểm gọi handler. Nếu ingress đã mang header sai hoặc bị giả mạo, annotation không tự sửa được sự sai lệch đó. Bảo vệ dữ liệu ở trust boundary phải xảy ra **trước** Service Activator.

## 3. Ba annotation dùng thường xuyên

| Annotation / kiểu tham số | Đầu vào lấy từ Message | Khi nào dùng |
| --- | --- | --- |
| **@Payload PaymentSubmitted** | Payload, có thể áp dụng conversion theo cấu hình | Logic chính dựa trên typed payload |
| **@Header("trustedTenantId") String** | Một header có tên chính xác | Handler cần một metadata cụ thể |
| **@Header(value="sourceSystem", required=false) String** | Header tùy chọn | Metadata phụ trợ không bắt buộc |
| **@Headers Map<String, Object>** | Tập header | Cần quan sát, xác minh nhiều header |
| **Message<PaymentSubmitted>** | Toàn bộ Spring Message | Thao tác mức messaging, cần headers/reply context |
| **MessageHeaders** | Tập headers của framework | Cần đọc toàn bộ metadata |

**@Payload** và **@Header** làm rõ ý nghĩa tham số, thay vì hy vọng framework suy ra bằng tên biến Java hoặc thứ tự arguments. Với Service Activator có nhiều tham số, annotation tường minh giúp code ổn định qua refactor.

### 3.1. @Header chọn đúng tên header

~~~java
import org.springframework.messaging.handler.annotation.Header;

void inspect(
        @Header("trustedTenantId") String tenantId,
        @Header("businessEventId") String eventId) {
    // ...
}
~~~

Hai chuỗi tên header phải **khớp chính xác** với giá trị đã gắn vào Spring Message. Đừng giả định Spring tự đổi từ HTTP header **X-Tenant-Id** thành Spring header **trustedTenantId**; việc chuyển đổi đó phải được thực hiện/kiểm chứng tại inbound adapter.

### 3.2. @Payload đưa payload vào tham số

~~~java
import org.springframework.messaging.handler.annotation.Payload;

void inspect(
        @Payload PaymentSubmitted payment,
        @Header("trustedTenantId") String tenantId) {
    // ...
}
~~~

Lớp payload nên có schema/validation của riêng nó. Chỉ gắn @Payload không chứng minh payload đã được xác thực hoặc thuộc tenant được khai báo ở header.

### 3.3. @Headers dùng khi cần nhiều metadata

~~~java
import java.util.Map;
import org.springframework.messaging.handler.annotation.Headers;

void audit(
        @Payload PaymentSubmitted payment,
        @Headers Map<String, Object> headers) {

    Object correlation = headers.get("businessCorrelationKey");
    Object source = headers.get("sourceSystem");
    // Đọc metadata cần thiết, không log toàn bộ headers.
}
~~~

**@Headers** không phải lý do để chuyển toàn bộ headers sang business layer. Nhiều headers có thể là infrastructure metadata (replyChannel, errorChannel, sequence/correlation IDs, broker delivery tags) hoặc có chứa dữ liệu nhạy cảm. Tốt hơn nên chọn các header cụ thể khi business method chỉ cần vài trường.

### 3.4. Không mutate MessageHeaders để thay dữ liệu

Spring MessageHeaders về mặt hợp đồng là một tập metadata bất biến. Nếu cần cập nhật header cho message tiếp theo, hãy dùng **MessageBuilder**, header enricher hoặc transformer tạo Message mới:

~~~java
Message<?> result = MessageBuilder
        .fromMessage(incoming)
        .setHeader("processingStage", "VALIDATED")
        .build();
~~~

Những metadata gốc như tenant, event ID hay business key chỉ được thay đổi khi có **quy tắc nghiệp vụ và quyền sở hữu rõ ràng**. Một handler tính phí không được ngầm đổi trustedTenantId rồi gửi sang channel khác.

## 4. Header bắt buộc và header tùy chọn

Spring Messaging **@Header** có thuộc tính **required**; mặc định là bắt buộc. Nếu một message đến handler mà thiếu header được đánh dấu bắt buộc, việc resolve tham số thường thất bại **trước khi chạy business method**.

~~~java
// Header bắt buộc:
@Header("trustedTenantId") String tenantId

// Header tùy chọn:
@Header(value = "traceId", required = false) String traceId
~~~

Khi traceId không có, tham số kiểu reference có thể là null; code nghiệp vụ phải xử lý hợp đồng đó. Không dùng primitive như **int** cho header có thể thiếu, trừ khi có default/conversion phù hợp và đã được kiểm thử.

### 4.1. Bắt buộc về cú pháp chưa đủ bắt buộc về nghiệp vụ

Header hiện diện nhưng bằng chuỗi rỗng cũng có thể là dữ liệu không hợp lệ:

~~~text
trustedTenantId = ""
businessEventId = "evt-1042"
~~~

@Header chỉ giải quyết việc lấy dữ liệu; một method/domain validator cần kiểm tra:

- Không null hoặc blank.
- Đúng pattern/độ dài.
- Đúng quyền tenant/workflow.
- Đúng loại dữ liệu.
- Đúng quan hệ với payload.

Với metadata có tính bảo mật, **xác minh quyền và đối chiếu registry phải diễn ra trước business side effect**.

### 4.2. Không dùng một header tùy chọn làm khóa idempotency

Nếu eventId không tồn tại mà handler tự tạo UUID:

~~~text
attempt 1: generated-event-id = uuid-A
attempt 2: generated-event-id = uuid-B
~~~

Hai lần nhận của **cùng logical event** sẽ trông như hai sự kiện khác nhau. Với handler ghi database/đặt hàng/thu phí, eventId hoặc operationId phải là một **business identity ổn định**; nếu thiếu, dừng/quarantine thay vì tự phát sinh mỗi retry.

### 4.3. Khi nào dùng defaultValue?

Một số annotation method-argument binding có hỗ trợ default value. Dù dùng cách nào, cần phân biệt **metadata phụ trợ** (ví dụ source label hiển thị trong log) với **metadata quyết định quyền hoặc kết quả nghiệp vụ**. Không đặt default tenantId="public", correlationKey="unknown" hay eventId ngẫu nhiên để vượt qua kiểm tra thiếu header. Nếu nguồn không có identity đáng tin, luồng nên reject trước khi xử lý.

## 5. Tạo payload và trusted context cho ví dụ

Chúng ta xây dựng một flow nhận thông tin thanh toán rồi trả **PaymentReceipt**. Flow này chỉ minh họa mapping arguments và idempotency ở mức mô phỏng; không thực hiện giao dịch ngân hàng hay trừ tiền.

### 5.1. Payload chỉ chứa thông tin nghiệp vụ

~~~java
record PaymentSubmitted(
        String paymentId,
        long amountMinor,
        String currencyCode,
        int workflowEpoch) {

    PaymentSubmitted {
        if (paymentId == null
                || !paymentId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_PAYMENT_ID");
        }
        if (amountMinor <= 0) {
            throw new IllegalArgumentException("INVALID_AMOUNT");
        }
        if (!"VND".equals(currencyCode)
                && !"USD".equals(currencyCode)) {
            throw new IllegalArgumentException("UNSUPPORTED_CURRENCY");
        }
        if (workflowEpoch < 1) {
            throw new IllegalArgumentException("INVALID_WORKFLOW_EPOCH");
        }
    }
}

record PaymentReceipt(
        String tenantId,
        String paymentId,
        String eventId,
        String businessCorrelationKey,
        String decision) {
}
~~~

**PaymentSubmitted không chứa trustedTenantId hay authorization role.** Tenant phải được xác minh bởi ingress hoặc application service. Một client tự ghi tenantId trong JSON không được trở thành Spring header trustedTenantId chỉ vì tên field giống nhau.

### 5.2. Context được tạo bởi trust boundary

~~~java
record VerifiedPaymentContext(
        String tenantId,
        String eventId,
        String sourceSystem) {

    VerifiedPaymentContext {
        if (tenantId == null
                || !tenantId.matches("[a-z0-9_-]{1,48}")
                || eventId == null
                || !eventId.matches("[A-Za-z0-9_-]{1,96}")
                || sourceSystem == null
                || !sourceSystem.matches("[A-Z_]{1,40}")) {
            throw new IllegalArgumentException("INVALID_VERIFIED_CONTEXT");
        }
    }
}

interface PaymentAuthorization {
    void assertAllowed(
            VerifiedPaymentContext context,
            PaymentSubmitted payment);
}
~~~

**Tên VerifiedPaymentContext không tạo ra tính đáng tin một cách thần kỳ.** Trong production, đối tượng đó chỉ được cấp sau khi xác thực client/producer, kiểm tra quyền tenant/paymentId/workflowEpoch và đối chiếu nguồn. Trong unit test, ta dùng context giả định đã được xác minh để kiểm tra mapping độc lập với hệ thống auth.

### 5.3. Correlation key có namespace tenant/epoch

~~~java
final class PaymentCorrelation {
    private PaymentCorrelation() {
    }

    static String key(
            String verifiedTenantId,
            PaymentSubmitted payment) {

        if (verifiedTenantId == null
                || !verifiedTenantId.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT");
        }
        return "payment:v1:"
                + verifiedTenantId + ":"
                + payment.paymentId() + ":"
                + payment.workflowEpoch();
    }
}
~~~

Cùng một logical event bị broker redeliver phải mang **cùng eventId và business key**. Nếu cùng paymentId được xử lý trong epoch mới theo nghiệp vụ, correlation key mới phải phân biệt epoch đó. Không dùng Spring MessageHeaders.ID làm business eventId vì ID có thể khác khi message được tạo lại.

## 6. Dựng Message tại ingress và đặt header có chủ sở hữu rõ

Sau khi authorization PASS, một factory tạo Message để downstream Service Activator không cần biết HTTP/JMS/AMQP nguồn nào đã mang sự kiện đến.

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class TrustedPaymentMessageFactory {
    private final PaymentAuthorization authorization;

    TrustedPaymentMessageFactory(
            PaymentAuthorization authorization) {
        this.authorization = authorization;
    }

    Message<PaymentSubmitted> create(
            PaymentSubmitted payment,
            VerifiedPaymentContext context) {

        authorization.assertAllowed(context, payment);
        String groupKey = PaymentCorrelation.key(
                context.tenantId(), payment);

        return MessageBuilder.withPayload(payment)
                .setHeader("trustedTenantId", context.tenantId())
                .setHeader("businessEventId", context.eventId())
                .setHeader("businessCorrelationKey", groupKey)
                .setHeader("sourceSystem", context.sourceSystem())
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        groupKey)
                .build();
    }
}
~~~

Các header **trustedTenantId**, **businessEventId** và **businessCorrelationKey** do application sở hữu. Chúng chỉ được gắn sau kiểm tra quyền. **CORRELATION_ID** là header kỹ thuật Spring Integration; trong topology này ta mirror business key vào đó vì phù hợp scope, nhưng với Splitter/Aggregator lồng nhau có thể cần correlation scope khác.

### 6.1. Vì sao không dùng copyHeaders từ request thô?

Một external request có thể gửi:

~~~http
POST /payments/events HTTP/1.1
Authorization: Bearer <redacted>
X-Tenant-Id: tenant-admin
X-Business-Event-Id: evt-stolen
X-Correlation-Id: payment:v1:tenant-admin:PAY-999:1
Content-Type: application/json

{"paymentId":"PAY-1042","amountMinor":125000,"currencyCode":"VND","workflowEpoch":3}
~~~

Nếu adapter sao chép nguyên các giá trị ấy vào Spring headers mà không kiểm tra, handler sẽ nhận **tham số @Header không đáng tin**. Tệ hơn, một client có thể cố đưa các header điều khiển như replyChannel hoặc errorChannel vào đường nội bộ.

Quy trình an toàn:

1. Parse và validate wire payload theo schema hỗ trợ.
2. Xác thực producer (JWT/mTLS/broker identity).
3. Tra tenant, quyền sở hữu payment và workflowEpoch từ registry.
4. Tạo **VerifiedPaymentContext** từ nguồn đã xác minh.
5. Dùng **TrustedPaymentMessageFactory** tạo Message mới với header allowlist.
6. Chuyển Message qua channel nội bộ chỉ dành cho trusted messages.

**@Header chỉ đọc metadata, không thực hiện authorization.** Không đặt niềm tin vào annotation khi dữ liệu được gắn trước đó chưa được kiểm tra.

### 6.2. Khi header từ HTTP/JMS không có tên giống nhau

HeaderMapper có thể ánh xạ:

~~~text
HTTP:   X-Request-Id
JMS:    businessRequestId
AMQP:   x-request-id

            |
            v
Inbound adapter / context verifier
            |
            v
Spring header: businessEventId
~~~

Sự chuyển đổi tên và semantics nên nằm tại **adapter hoặc ingress boundary**. Service Activator đọc một hợp đồng Spring Message nhất quán và không phải mang ba annotation với tên khác nhau cho từng connector.

## 7. Service Activator nhận nhiều header vào từng tham số

Đây là ví dụ chính của bài:

~~~java
import java.util.Map;
import java.util.Objects;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

final class PaymentHeaderServiceActivator {
    private final PaymentLedger ledger;

    PaymentHeaderServiceActivator(PaymentLedger ledger) {
        this.ledger = Objects.requireNonNull(ledger);
    }

    @ServiceActivator(
            inputChannel = "verifiedPayments",
            outputChannel = "paymentReceipts")
    public PaymentReceipt accept(
            @Payload PaymentSubmitted payment,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId,
            @Header("businessCorrelationKey") String groupKey,
            @Header(value = "sourceSystem", required = false)
                    String sourceSystem,
            @Headers Map<String, Object> headers) {

        // @Header đưa đúng field từ MessageHeaders vào tham số.
        String expected = PaymentCorrelation.key(tenantId, payment);
        if (!expected.equals(groupKey)) {
            throw new SecurityException("CORRELATION_MISMATCH");
        }

        // Chỉ kiểm tra một metadata phụ trợ, không chuyển
        // nguyên toàn bộ headers vào business operation.
        if (sourceSystem != null
                && !sourceSystem.matches("[A-Z_]{1,40}")) {
            throw new IllegalArgumentException("INVALID_SOURCE_SYSTEM");
        }
        if (!tenantId.equals(headers.get("trustedTenantId"))) {
            throw new SecurityException("TENANT_HEADER_MISMATCH");
        }

        // Phương thức service xử lý business event bằng
        // identity đã có từ trusted ingress.
        return ledger.apply(payment, tenantId, eventId, groupKey);
    }
}
~~~

**Những gì xảy ra khi endpoint nhận Message:**

1. Xác định payload của message → truyền vào **PaymentSubmitted payment**.
2. Tìm header **trustedTenantId** → truyền vào **String tenantId**.
3. Tìm header **businessEventId** → truyền vào **String eventId**.
4. Tìm header **businessCorrelationKey** → truyền vào **String groupKey**.
5. Tìm **sourceSystem** nếu có; nếu thiếu, tham số có thể null.
6. Truyền tập headers vào tham số **Map<String,Object> headers**.
7. Gọi body của method và lấy **PaymentReceipt** làm reply payload.

Lỗi thiếu một header bắt buộc hoặc không chuyển được kiểu có thể xảy ra **trước bước 7**. Lỗi quyền/correlation do body method phát hiện xảy ra ở handler và được xử lý theo flow error policy.

### 7.1. Không trộn @Header vào tên biến mơ hồ

~~~java
// Nên viết:
@Header("businessCorrelationKey") String groupKey

// Tránh phụ thuộc suy diễn:
String groupKey
~~~

Một tham số String không được annotation có thể khiến method resolution khó hiểu, đặc biệt khi method có nhiều chuỗi: paymentId, tenantId, eventId, traceId. Annotation tường minh là hợp đồng tốt hơn tên biến Java.

### 7.2. Vì sao method nhận cả @Headers trong ví dụ?

Để minh họa sự khác nhau giữa **lấy từng header** và **nhận một tập header**. Trong production, nếu không cần Map, bỏ hẳn tham số @Headers để giảm coupling và tránh vô tình log/copy metadata nhạy cảm.

## 8. Business service và ledger: tránh side effect trùng

Để hoàn thiện ví dụ, ta định nghĩa interface lưu kết quả và một implementation in-memory **chỉ dành cho minh họa/test**.

~~~java
interface PaymentLedger {
    PaymentReceipt apply(
            PaymentSubmitted payment,
            String tenantId,
            String eventId,
            String businessCorrelationKey);
}
~~~

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

final class InMemoryPaymentLedger implements PaymentLedger {
    private final ConcurrentMap<String, Recorded> records =
            new ConcurrentHashMap<>();

    private record Recorded(
            PaymentSubmitted original,
            PaymentReceipt receipt) {
    }

    @Override
    public PaymentReceipt apply(
            PaymentSubmitted payment,
            String tenantId,
            String eventId,
            String businessCorrelationKey) {

        String dedupKey = tenantId + ":" + eventId;
        Recorded result = records.compute(dedupKey, (ignored, existing) -> {
            if (existing != null) {
                if (!existing.original().equals(payment)
                        || !existing.receipt()
                                .businessCorrelationKey()
                                .equals(businessCorrelationKey)) {
                    throw new IllegalStateException("EVENT_ID_CONFLICT");
                }
                return existing;
            }

            return new Recorded(
                    payment,
                    new PaymentReceipt(
                            tenantId,
                            payment.paymentId(),
                            eventId,
                            businessCorrelationKey,
                            "RECORDED"));
        });
        return result.receipt();
    }

    int uniqueEventCount() {
        return records.size();
    }
}
~~~

Ví dụ này giúp unit test redelivery: **cùng tenant/eventId và cùng payload** cho cùng receipt; nếu eventId bị dùng lại với payload khác, báo conflict. Nó **không bền qua restart**, không phối hợp multi-instance, không bảo đảm transaction ngoài database, và không phải cài đặt ledger production.

Trong production, dùng unique key/index và transaction/inbox/outbox hoặc provider idempotency key theo phạm vi eventId thật. Đừng suy ra “exactly once” chỉ từ ConcurrentHashMap hoặc từ việc Service Activator nhận đúng tham số.

## 9. Đăng ký Service Activator và các channels

Các lớp ở phần trước có thể được đăng ký thành Spring beans. Endpoint được tạo từ method có annotation **@ServiceActivator**, còn handler nhận những tham số do framework ánh xạ từ Message.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class PaymentHeaderFlowConfig {

    @Bean
    MessageChannel verifiedPayments() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel paymentReceipts() {
        return new QueueChannel();
    }

    @Bean
    InMemoryPaymentLedger paymentLedger() {
        return new InMemoryPaymentLedger();
    }

    @Bean
    PaymentHeaderServiceActivator paymentHeaderServiceActivator(
            InMemoryPaymentLedger ledger) {
        return new PaymentHeaderServiceActivator(ledger);
    }
}
~~~

Trong **cùng Spring context**, @EnableIntegration cung cấp hạ tầng để các annotation endpoint như @ServiceActivator được xử lý. Handler bean ở đây được đăng ký bằng @Bean, không cần thêm @Component trên chính lớp đó.

### 9.1. Luồng xử lý đầy đủ

~~~mermaid
sequenceDiagram
    participant A as Trusted application ingress
    participant F as MessageFactory
    participant C as verifiedPayments
    participant S as Service Activator
    participant L as PaymentLedger
    participant O as paymentReceipts
    A->>F: PaymentSubmitted + VerifiedPaymentContext
    F->>F: Authorization + create trusted headers
    F->>C: Spring Message
    C->>S: Method argument resolution
    Note over S: @Payload, @Header, @Headers
    S->>L: apply(payment,tenant,eventId,key)
    L-->>S: PaymentReceipt
    S-->>O: Reply Message
~~~

Vì **verifiedPayments** là DirectChannel, handler thường chạy ngay trên thread gửi. **paymentReceipts** là QueueChannel phục vụ ví dụ/test. Trong hệ thống thực, cần consumer phù hợp và tránh để QueueChannel in-memory tích lũy dữ liệu vô hạn.

### 9.2. Vì sao method trả PaymentReceipt thì có output?

Với Service Activator dạng request/reply, giá trị trả về khác null được dùng làm **reply payload** theo quy tắc framework. Vì endpoint khai báo **outputChannel = "paymentReceipts"**, kết quả được gửi sang channel đó.

Nếu một method chỉ thực hiện side effect và trả **void**, đó là hợp đồng **one-way**: đừng cấu hình Gateway đồng bộ đang chờ PaymentReceipt rồi hy vọng reply tự sinh ra.

### 9.3. Không đăng ký hai endpoint cạnh tranh trên cùng DirectChannel

Nếu vừa đăng ký @ServiceActivator(inputChannel="verifiedPayments") ở trên, vừa tạo một IntegrationFlow khác tiêu thụ **cùng verifiedPayments DirectChannel**, hai subscriber có thể cạnh tranh hoặc được chọn theo semantics của channel, khiến test khó đoán. Các ví dụ ở phần Java DSL dưới đây là **phương án thay thế**, không phải cấu hình cần bổ sung đồng thời.

## 10. Java DSL .handle(...) cũng đọc được headers

Không bắt buộc viết một method có @ServiceActivator để xử lý header. Java DSL cho phép handler lambda nhận **payload và headers**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import java.util.Map;

// Biến thể thay thế endpoint @ServiceActivator ở mục 7.
@Bean
IntegrationFlow paymentDslFlow(PaymentLedger ledger) {
    return IntegrationFlow.from("verifiedPayments")
            .handle(PaymentSubmitted.class, (payment, headers) -> {
                String tenant = requiredString(
                        headers, "trustedTenantId");
                String eventId = requiredString(
                        headers, "businessEventId");
                String businessKey = requiredString(
                        headers, "businessCorrelationKey");

                if (!businessKey.equals(
                        PaymentCorrelation.key(tenant, payment))) {
                    throw new SecurityException("CORRELATION_MISMATCH");
                }

                return ledger.apply(
                        payment, tenant, eventId, businessKey);
            })
            .channel("paymentReceipts")
            .get();
}

private static String requiredString(
        Map<String, Object> headers,
        String name) {
    Object value = headers.get(name);
    if (!(value instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException(
                "INVALID_REQUIRED_HEADER_" + name);
    }
    return text;
}
~~~

Trong code hoàn chỉnh, đặt method **requiredString** trong cùng class cấu hình/utility phù hợp. Đây là **biến thể độc lập**: bỏ bean PaymentHeaderServiceActivator hoặc đổi input channel, không đăng ký hai consumers cùng nhận verifiedPayments nếu mục tiêu chỉ có một handler.

### 10.1. So sánh annotation và DSL lambda

| Tiêu chí | @ServiceActivator với @Header | DSL .handle(payload, headers) |
| --- | --- | --- |
| Dạng code | Java method có annotated parameters | Lambda hoặc handler object |
| Đọc một header | Framework resolve trực tiếp vào tham số | Code tự đọc Map |
| Missing header | Framework có required semantics | Code tự kiểm tra |
| Conversion | Có thể thông qua argument resolvers/conversion | Code quyết định ép kiểu |
| Dễ unit test | Gọi Java method trực tiếp | Tách lambda logic thành service để test |
| Tách business và messaging | Tốt khi khai báo metadata cần thiết | Tốt nếu mapping ngắn, nhưng dễ phình Map logic |
| Có Spring MessageHeaders | @Headers hoặc Message<?> | Map headers đã truyền |

**Không có cách nào tự động bảo đảm dữ liệu đáng tin.** Thứ quan trọng là ingress đã kiểm tra quyền và handler có contract chặt về tên, kiểu và semantics của header.

### 10.2. Đặt manual mapping vào một lớp riêng

Khi một handler DSL cần bốn hoặc năm header, có thể tạo một immutable **BusinessContext** để giảm sự phụ thuộc của domain service vào MessageHeaders:

~~~java
record PaymentBusinessContext(
        String tenantId,
        String eventId,
        String groupKey) {
}

final class PaymentContexts {
    static PaymentBusinessContext from(
            Map<String, Object> headers) {
        return new PaymentBusinessContext(
                requiredString(headers, "trustedTenantId"),
                requiredString(headers, "businessEventId"),
                requiredString(headers, "businessCorrelationKey"));
    }

    private static String requiredString(
            Map<String, Object> headers,
            String name) {
        Object value = headers.get(name);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_REQUIRED_HEADER_" + name);
        }
        return text;
    }
}
~~~

Đây vẫn chỉ là **chuyển metadata đã được xác thực sang kiểu Java nội bộ**. Nếu context được tạo từ HTTP headers chưa verify, record chỉ giúp code đẹp hơn chứ không tăng bảo mật.

## 11. Biến thể handler nhận toàn bộ Message

Khi endpoint cần đọc framework headers phức tạp, một method có thể nhận **Message<PaymentSubmitted>** thay vì nhiều annotated arguments:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;

final class RawMessagePaymentHandler {
    private final PaymentLedger ledger;

    RawMessagePaymentHandler(PaymentLedger ledger) {
        this.ledger = ledger;
    }

    // Biến thể thay thế, không đăng ký đồng thời cùng inputChannel.
    @ServiceActivator(inputChannel = "verifiedPayments")
    public PaymentReceipt accept(Message<PaymentSubmitted> message) {
        PaymentSubmitted payload = message.getPayload();

        String tenant = (String) message.getHeaders()
                .get("trustedTenantId");
        String eventId = (String) message.getHeaders()
                .get("businessEventId");
        String key = (String) message.getHeaders()
                .get("businessCorrelationKey");

        if (tenant == null || eventId == null || key == null) {
            throw new IllegalArgumentException("MISSING_HEADER");
        }
        if (!key.equals(PaymentCorrelation.key(tenant, payload))) {
            throw new SecurityException("CORRELATION_MISMATCH");
        }
        return ledger.apply(payload, tenant, eventId, key);
    }
}
~~~

**Ưu điểm:** toàn bộ message và header metadata đều có sẵn. **Nhược điểm:** business method bị ràng buộc trực tiếp vào Spring Messaging; các phép cast thủ công có thể gây ClassCastException và bỏ qua required semantics mà @Header cung cấp.

Nếu handler chỉ cần hai ba trường, annotated parameters giúp tách mạch lạc hơn. Nếu handler thực sự làm công việc hạ tầng như routing, fan-out, reply/error header handling hoặc copy selected headers, nhận Message có thể hợp lý.

### 11.1. Đừng dùng cùng tham số cho hai vai trò

Một service chuyên về nghiệp vụ có thể nhận:

~~~java
PaymentReceipt apply(
        PaymentSubmitted payment,
        PaymentBusinessContext context);
~~~

Service Activator đóng vai trò **adapter** từ Spring Message sang business service:

~~~text
Spring Message
   -> @Payload + @Header arguments
   -> PaymentBusinessContext
   -> Domain service
~~~

Như vậy domain service không phụ thuộc trực tiếp vào **@Header**, **MessageHeaders** hoặc **replyChannel** mà vẫn nhận đủ identity để chống nhầm tenant và duplicate.

## 12. Kiểu dữ liệu header và chuyển đổi tham số

Spring Messaging method invocation có thể dùng các argument resolvers và conversion mechanisms tùy phiên bản/cấu hình. Tuy nhiên **không nên phụ thuộc vào việc bất kỳ Java object nào trong headers đều tự được convert sang bất kỳ tham số nào**.

### 12.1. Ví dụ một header số nguyên

~~~java
void consume(
        @Payload PaymentSubmitted payment,
        @Header("trustedTenantId") String tenant,
        @Header("workflowEpoch") Integer epoch) {
    if (epoch == null || epoch != payment.workflowEpoch()) {
        throw new IllegalArgumentException("EPOCH_MISMATCH");
    }
}
~~~

Nếu message được tạo nội bộ, gắn **workflowEpoch** là **Integer**:

~~~java
MessageBuilder.withPayload(payment)
        .setHeader("workflowEpoch", payment.workflowEpoch())
        .build();
~~~

Nếu một broker header gửi **"3"** dưới dạng String, một số cấu hình conversion có thể chuyển sang Integer, nhưng không nên xem đó là mặc định ổn định cho mọi adapter/type. Tốt nhất **parse và validate tại ingress**, sau đó gắn đúng kiểu header nội bộ. Với các loại phức tạp như UUID, Instant, enum hoặc custom record, cần conversion rules và tests rõ.

### 12.2. Chuyển đổi chuỗi thành UUID

~~~java
// Nếu @Header tham số có kiểu UUID, phải có converter phù hợp:
@Header("requestUuid") java.util.UUID requestUuid
~~~

Nếu đầu vào là String không hợp lệ, lỗi conversion có thể xảy ra **trước khi body method được chạy**. Muốn kiểm soát error code, ingress nên parse UUID, bắt lỗi và quarantine/reject theo schema; không để một giá trị tùy ý len lỏi vào business method.

### 12.3. Không dùng header Map cho dữ liệu biến động chưa kiểm chứng

~~~java
@Headers Map<String, Object> headers
~~~

có thể chứa:

- **String**: tenant, trace ID, source.
- **Number**: sequence number, retry count.
- **UUID/Long**: Spring message id, timestamp.
- **MessageChannel hoặc tên channel**: replyChannel, errorChannel.
- **Transport metadata**: broker tags, native headers, content type.

Một **Map<String, Object>** giúp quan sát nhưng làm yếu type safety nếu dùng xuyên business layer. Chỉ extract trường cần thiết và tạo immutable typed context cho nghiệp vụ.

### 12.4. Header thiếu, null và default: chọn nghĩa rõ ràng

| Trường | Thiếu thì sao? | Vì sao |
| --- | --- | --- |
| trustedTenantId | Reject | Không biết quyền/tenant |
| businessEventId | Reject hoặc quarantine | Không thể dedup đáng tin |
| businessCorrelationKey | Reject nếu flow cần group | Tránh false split/join |
| traceId | Có thể tiếp tục với trace instrumentation phù hợp | Quan sát, không phải business authority |
| sourceSystem | Tùy contract, có thể optional để log | Không được mặc định thành producer có quyền |
| workflowEpoch | Reject nếu dùng phân biệt các phiên workflow | Tránh trộn phiên cũ/mới |
| replyChannel | Có thể vắng trong one-way flow | Runtime routing, không phải domain header |
| sequenceNumber | Có thể vắng nếu message chưa Splitter | Không suy diễn có sequence |

Không “chữa” một header thiếu bằng cách tự sinh eventId ngẫu nhiên trong Service Activator nếu idempotency của giao dịch phụ thuộc vào eventId gốc.

## 13. Một số Spring Integration headers quan trọng

Khi xử lý message trong một luồng tích hợp, không phải header nào cũng thuộc nghiệp vụ. Spring Integration có các header kỹ thuật phục vụ correlation, sequencing, request/reply và dispatch.

| Header | Ý nghĩa thường gặp | Có nên đưa thẳng vào domain service? |
| --- | --- | --- |
| **id** | ID của Spring Message hiện tại | Không dùng thay business eventId |
| **timestamp** | Timestamp framework gắn vào Message | Không thay occurredAt của business event |
| **correlationId** | Khóa nhóm các message trong một scope | Chỉ dùng đúng scope của Aggregator/Splitter |
| **sequenceNumber** | Thứ tự một child message trong sequence | Chỉ khi logic cần sequence |
| **sequenceSize** | Số message dự kiến trong một sequence | Không coi là số business outcomes trong mọi trường hợp |
| **replyChannel** | Destination reply trong Spring runtime | Giữ ở tầng integration |
| **errorChannel** | Destination xử lý lỗi | Giữ ở tầng integration |
| **contentType** | Gợi ý kiểu nội dung | Không thay schema validation |
| **priority** | Metadata ưu tiên (khi được sử dụng) | Chỉ khi hợp đồng xử lý có quy định |
| **custom trustedTenantId** | Tenant đã xác minh bởi ingress | Đưa qua context có validation |
| **custom businessEventId** | Logical event identity | Dùng cho idempotency đúng scope |

Spring MessageHeaders.ID/TIMESTAMP và các constants của IntegrationMessageHeaderAccessor có thể giúp tránh lỗi gõ sai tên header trong code. Ví dụ:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.handler.annotation.Header;

void inspect(
        @Header(MessageHeaders.ID) java.util.UUID springMessageId,
        @Header(
                value = IntegrationMessageHeaderAccessor.CORRELATION_ID,
                required = false) Object correlationId,
        @Header(
                value = IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                required = false) Integer sequenceNumber) {

    // springMessageId phục vụ diagnostics.
    // correlationId và sequenceNumber chỉ có nghĩa
    // trong topology đã tạo ra chúng.
}
~~~

**Lưu ý:** header sequence có thể không tồn tại nếu message chưa qua Splitter hoặc nguồn chưa cấp sequence. correlationId cũng có thể không tồn tại ở flow one-way không cần grouping.

### 13.1. Business correlation khác technical correlation

Giả sử một order có nhiều packages:

~~~text
Business correlation:
  shipping:tenant-a:SHIP-901:epoch-3

Splitter technical correlation:
  split-batch-44

Child 1: sequenceNumber = 1
Child 2: sequenceNumber = 2
Child 3: sequenceNumber = 3
~~~

Một Service Activator xử lý từng package có thể cần cả **businessCorrelationKey** (thuộc shipment) và **sequenceNumber** (thuộc nhóm child). Nếu chỉ gắn cùng một giá trị correlationId cho mọi cấp nested group, Aggregator có thể gom sai.

### 13.2. @Header không làm correlation tự động

~~~java
@Header("businessCorrelationKey") String groupKey
~~~

chỉ lấy giá trị header. Để Aggregator thực sự nhóm theo header đó, cần cấu hình **CorrelationStrategy** dùng businessCorrelationKey, hoặc đặt đúng **CORRELATION_ID** khi có scope phù hợp và sử dụng chiến lược mặc định.

Tương tự, một method nhận sequenceNumber không khiến những messages tự đi theo thứ tự. Resequencer/Aggregator cần được cấu hình riêng.

### 13.3. Xử lý header replyChannel đặc biệt

Trong request/reply flow, Gateway có thể gắn temporary replyChannel là một **MessageChannel object**. Dù có thể lấy ở tầng hạ tầng, không đưa object này vào PaymentBusinessContext, JSON DTO hoặc database. Nó không phải business ID và không có ý nghĩa ngoài invocation runtime.

Trường hợp xử lý thuần nghiệp vụ, để Service Activator trả PaymentReceipt và để framework quyết định gửi reply theo outputChannel/replyChannel. Chỉ handler mức messaging đặc biệt mới cần thao tác trực tiếp với reply channel, và phải kiểm tra security/routing semantics.

## 14. Header qua Transformer, Router và subflow

Giả sử một ingress đã gắn trustedTenantId, businessEventId và businessCorrelationKey. Trước Service Activator có một Transformer đổi payload:

~~~mermaid
flowchart LR
    A["Verified input Message"] --> R["Content-Based Router"]
    R --> T1["Transformer A"]
    R --> T2["Transformer B"]
    T1 --> S["Service Activator"]
    T2 --> S
    S --> O["Business reply / event"]
~~~

Thông thường khi Transformer trả **một payload thuần**, Spring Integration có cơ chế propagate headers của input vào output theo framework semantics. Nếu Transformer trả **Message hoàn chỉnh**, header preservation phụ thuộc cách Message mới được dựng. Hai biến thể rất khác nhau:

### 14.1. Biến đổi payload, giữ header theo message handling

~~~java
return IntegrationFlow.from("rawPaymentEvents")
        .transform(RawPayment.class, parser::convertToPaymentSubmitted)
        .channel("verifiedPayments")
        .get();
~~~

Đoạn này **chỉ minh họa topology**. Nếu rawPaymentEvents chứa input chưa xác minh, không nên gửi thẳng vào verifiedPayments chỉ vì parser thành công: cần bước authorization/identity binding trước đó.

### 14.2. Tạo Message mới có chủ đích

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<PaymentSubmitted> rebuildTrusted(
        Message<RawPayment> input,
        PaymentSubmitted parsed,
        VerifiedPaymentContext verified,
        PaymentAuthorization auth) {

    // Tạo lại allowlisted headers sau khi kiểm tra quyền.
    return new TrustedPaymentMessageFactory(auth)
            .create(parsed, verified);
}
~~~

Đây là điểm **trust boundary**: thay vì copy hàng trăm headers từ HTTP/broker, tạo metadata nội bộ từ verified context. Nhưng một bước rebuild như vậy có thể **không giữ temporary replyChannel** của Gateway request/reply. Nếu flow cần reply cho caller, phải thiết kế việc chuyển replyChannel/sequence headers ở **trusted internal hop** phù hợp.

### 14.3. Tạo Message từ Message trước đó

~~~java
Message<?> next = MessageBuilder.fromMessage(inputMessage)
        .setHeader("processingStage", "NORMALIZED")
        .build();
~~~

**fromMessage** thường giúp giữ những headers hiện có của một Message nội bộ đã được xác minh. Không nên dùng nó trên **raw message do client kiểm soát** rồi tự mặc định mọi header đều an toàn.

### 14.4. Một header có thể biến mất khi rời JVM

Nếu subflow đưa Message vào HTTP/JMS/AMQP/TCP outbound adapter, việc header nào được chuyển phụ thuộc HeaderMapper/MessageConverter/serializer. Một header kiểu **String businessCorrelationKey** có thể được map theo contract; một object **replyChannel** không phải payload portable.

Nếu business workflow cần sống qua restart hoặc callback đến muộn, đưa identity cần thiết vào **versioned wire envelope** và tái xác minh khi nhận lại, thay vì dựa vào temporary framework headers.

## 15. Gateway request/reply và mapping tham số

Một **@MessagingGateway** có thể nhận lời gọi Java rồi tạo Spring Message. Gateway thường quản lý đường reply cho invocation, trong khi Service Activator dùng @Payload/@Header lấy dữ liệu.

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway
interface PaymentGateway {
    @Gateway(requestChannel = "verifiedPayments")
    PaymentReceipt submit(
            @Payload PaymentSubmitted payment,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId,
            @Header("businessCorrelationKey") String groupKey);
}
~~~

**Điều kiện an toàn:** application service phải xác thực tenant/payment/epoch và tự tính groupKey **trước khi gọi gateway**. Interface này không tự kiểm tra quyền; nó chỉ chuyển arguments thành Message headers/payload.

### 15.1. Gateway và Service Activator có thể cùng dùng @Header

~~~text
Caller:
  gateway.submit(payment, "tenant-a", "evt-1042", "payment:v1:...")

Gateway:
  Message.payload = payment
  Message.headers.trustedTenantId = tenant-a
  Message.headers.businessEventId = evt-1042
  Message.headers.businessCorrelationKey = payment:v1:...

Service Activator:
  @Payload -> payment
  @Header("trustedTenantId") -> tenant-a
  @Header("businessEventId") -> evt-1042
  @Header("businessCorrelationKey") -> payment:v1:...
~~~

Tuy nhiên, cấu hình ví dụ **PaymentHeaderFlowConfig** ở mục 9 đặt một **outputChannel cố định** tên paymentReceipts. Nếu muốn Gateway sync nhận reply, cần **wiring request/reply riêng**: không được giả định Gateway tự lấy Message từ một QueueChannel khác mà không có bridge/reply route. Một lựa chọn là để Service Activator trả lời theo replyChannel của Gateway trong flow dành riêng cho request/reply, thay vì ép tất cả kết quả vào một output queue tách biệt.

### 15.2. Temporary replyChannel và businessCorrelationKey không cùng nhiệm vụ

~~~text
Logical payment workflow:
  businessCorrelationKey = payment:v1:tenant-a:PAY-1042:3

Gateway invocation 1:
  replyChannel = temporaryChannelA

Gateway invocation 2 (retry):
  replyChannel = temporaryChannelB

Business workflow vẫn có cùng key.
~~~

Không dùng replyChannel làm idempotency key; không dùng businessCorrelationKey làm tên dynamic channel tùy ý. Một giá trị phục vụ **liên kết nghiệp vụ dài hạn**, một giá trị phục vụ **đường trả lời cho một invocation ngắn hạn**.

### 15.3. Gateway trả void và handler không trả reply

Nếu Gateway method chỉ gửi command và trả void, caller không nhận PaymentReceipt qua method. Khi một Service Activator được cấu hình chỉ làm one-way effect, không tạo giả một reply theo eventId mới. Với request có kết quả đến từ provider sau nhiều phút, chọn **accepted + persisted workflow + async callback** thay vì giữ Gateway caller chờ không giới hạn.

## 16. Header mapping ở các inbound adapters

**Header mapping** có hai tầng dễ nhầm:

1. **Adapter mapping:** HTTP/JMS/AMQP/TCP header/property → Spring Message headers.
2. **Method parameter mapping:** Spring Message header → Java argument bằng @Header.

Hoàn thành tầng 2 không chứng minh tầng 1 đã đúng. Ví dụ:

~~~text
HTTP X-Event-Id = evt-1042
      |
      v
HTTP HeaderMapper / inbound controller
      |
      v
Spring header businessEventId = evt-1042
      |
      v
@Header("businessEventId") String eventId
~~~

Nếu mapper không copy header hoặc chuyển sai tên, @Header("businessEventId") không thể tự lấy đúng trường đó từ HTTP.

### 16.1. So sánh adapters

| Adapter / transport | Header cần quan tâm | Rủi ro |
| --- | --- | --- |
| **HTTP inbound** | HTTP headers, request path, auth principal | Client tự khai tenant/role/correlation |
| **JMS inbound** | JMS headers/properties, messageId, correlationId, replyTo | Broker properties không đồng nghĩa application business identity |
| **AMQP inbound** | Message properties, routing key, headers | Publisher có thể cung cấp custom properties tùy permissions |
| **TCP inbound** | Connection metadata, framing, serialized fields | Payload có thể không mang Spring headers |
| **File/SFTP inbound** | Path/name, content, batch metadata | File name không mặc định là trusted correlation |

**HeaderMapper** là công cụ chuyển biểu diễn, không tự là một authorization system. Identity người gửi phải được xác minh và liên kết với tenant/workflow trước khi sử dụng trong Service Activator.

### 16.2. Phản ví dụ: client giả mạo tenant

~~~http
POST /api/payments/events HTTP/1.1
X-Tenant-Id: tenant-admin
X-Event-Id: evt-fake
Content-Type: application/json

{"paymentId":"PAY-999","amountMinor":1000,"currencyCode":"VND","workflowEpoch":1}
~~~

Nếu application tự map X-Tenant-Id thành trustedTenantId mà không đối chiếu credential, Service Activator có thể xử lý sai tenant dù các annotation đều được viết đúng.

### 16.3. Chính sách allowlist cho ingress

- Chỉ nhận những HTTP/broker headers thực sự thuộc contract.
- Giới hạn độ dài, charset và kiểu của các metadata.
- Không chuyển trực tiếp **replyChannel**, **errorChannel**, **routingSlip** từ bên ngoài.
- Dựng internal trustedTenantId và businessCorrelationKey từ principal/registry.
- Không dùng traceId do client tự khai làm quyền truy cập hoặc idempotency key.
- Nếu partner có external correlationId riêng, giữ như **externalCorrelationRef** để đối soát nhưng không tự dùng làm business group key.
- Test cả trường hợp header thiếu, không hỗ trợ, bị duplicate hoặc có nhiều giá trị.

## 17. Unit test: method đọc đúng tham số đã được truyền

Unit test trực tiếp một Java method giúp xác minh **logic kiểm tra dữ liệu sau khi arguments đã có giá trị**. Vì test gọi method bằng Java bình thường, nó **không kiểm chứng framework argument resolver**; điều đó sẽ được kiểm tra ở integration test.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class PaymentHeaderServiceActivatorUnitTest {

    private InMemoryPaymentLedger ledger;
    private PaymentHeaderServiceActivator handler;

    @BeforeEach
    void prepare() {
        ledger = new InMemoryPaymentLedger();
        handler = new PaymentHeaderServiceActivator(ledger);
    }

    private PaymentSubmitted samplePayment() {
        return new PaymentSubmitted(
                "PAY-1042", 125000, "VND", 3);
    }

    private String key(PaymentSubmitted payment) {
        return PaymentCorrelation.key("tenant-a", payment);
    }

    @Test
    void handlesTrustedMetadataAndReturnsReceipt() {
        PaymentSubmitted payment = samplePayment();

        PaymentReceipt receipt = handler.accept(
                payment,
                "tenant-a",
                "evt-payment-1042",
                key(payment),
                "BILLING",
                Map.of(
                        "trustedTenantId", "tenant-a",
                        "businessEventId", "evt-payment-1042"));

        assertEquals("RECORDED", receipt.decision());
        assertEquals("PAY-1042", receipt.paymentId());
        assertEquals("tenant-a", receipt.tenantId());
        assertEquals(
                "evt-payment-1042", receipt.eventId());
        assertEquals(key(payment),
                receipt.businessCorrelationKey());
        assertEquals(1, ledger.uniqueEventCount());
    }

    @Test
    void rejectsCorrelationFromDifferentWorkflow() {
        PaymentSubmitted payment = samplePayment();

        assertThrows(SecurityException.class, () ->
                handler.accept(
                        payment,
                        "tenant-a",
                        "evt-payment-1042",
                        "payment:v1:tenant-b:PAY-1042:3",
                        "BILLING",
                        Map.of("trustedTenantId", "tenant-a")));

        assertEquals(0, ledger.uniqueEventCount());
    }

    @Test
    void missingOptionalSourceCanBeHandled() {
        PaymentSubmitted payment = samplePayment();

        PaymentReceipt receipt = handler.accept(
                payment,
                "tenant-a",
                "evt-no-source",
                key(payment),
                null,
                Map.of("trustedTenantId", "tenant-a"));

        assertEquals("RECORDED", receipt.decision());
    }

    @Test
    void headerMapConflictIsRejectedBeforeLedgerCall() {
        PaymentSubmitted payment = samplePayment();

        assertThrows(SecurityException.class, () ->
                handler.accept(
                        payment, "tenant-a", "evt-conflict",
                        key(payment), "BILLING",
                        Map.of("trustedTenantId", "tenant-b")));

        assertEquals(0, ledger.uniqueEventCount());
    }

    @Test
    void duplicateLogicalEventDoesNotCreateSecondRecord() {
        PaymentSubmitted payment = samplePayment();
        Map<String, Object> headers =
                Map.of("trustedTenantId", "tenant-a");

        PaymentReceipt first = handler.accept(
                payment, "tenant-a", "evt-repeat",
                key(payment), "BILLING", headers);
        PaymentReceipt replay = handler.accept(
                payment, "tenant-a", "evt-repeat",
                key(payment), "BILLING", headers);

        assertEquals(first, replay);
        assertEquals(1, ledger.uniqueEventCount());
    }
}
~~~

Các unit tests trên chứng minh logic của handler và fake ledger; **chúng không hề để Spring gọi @Header**. Một test chỉ gọi handler.accept(...) không thể chứng minh framework ánh xạ đúng tên header hoặc xử lý required/optional arguments.

## 18. Integration test: Spring thực hiện @Header argument mapping

Tạo context từ **PaymentHeaderFlowConfig**, gửi một Message vào **verifiedPayments**, sau đó đọc **PaymentReceipt** từ **paymentReceipts**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Set;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PaymentHeaderFlowConfig.class)
class PaymentHeaderMappingIntegrationTest {

    @Autowired
    @Qualifier("verifiedPayments")
    MessageChannel input;

    @Autowired
    @Qualifier("paymentReceipts")
    QueueChannel output;

    @Autowired
    InMemoryPaymentLedger ledger;

    // Test-only authorization stub: KHÔNG triển khai production.
    private final PaymentAuthorization stubAuthorization =
            (context, payment) -> {
                if (!Set.of("tenant-a", "tenant-b")
                        .contains(context.tenantId())) {
                    throw new SecurityException("TENANT_NOT_ALLOWED");
                }
            };

    private TrustedPaymentMessageFactory factory() {
        return new TrustedPaymentMessageFactory(stubAuthorization);
    }

    private PaymentSubmitted sample(
            String id, int epoch) {
        return new PaymentSubmitted(id, 125000, "VND", epoch);
    }

    @BeforeEach
    void drainOutput() {
        while (output.receive(0) != null) {
            // Không để reply của test trước làm nhiễu test sau.
        }
    }

    private PaymentReceipt nextReceipt() {
        Message<?> reply = output.receive(0);
        assertNotNull(reply);
        assertInstanceOf(PaymentReceipt.class, reply.getPayload());
        return (PaymentReceipt) reply.getPayload();
    }

    @Test
    void frameworkMapsRequiredAndOptionalHeaders() {
        PaymentSubmitted payment = sample("PAY-1101", 3);
        VerifiedPaymentContext context =
                new VerifiedPaymentContext(
                        "tenant-a", "evt-1101", "BILLING");

        Message<PaymentSubmitted> message =
                factory().create(payment, context);
        assertTrue(input.send(message));

        PaymentReceipt reply = nextReceipt();
        assertEquals("PAY-1101", reply.paymentId());
        assertEquals("tenant-a", reply.tenantId());
        assertEquals("evt-1101", reply.eventId());
        assertEquals(
                "payment:v1:tenant-a:PAY-1101:3",
                reply.businessCorrelationKey());
        assertEquals("RECORDED", reply.decision());
        assertNull(output.receive(0));
    }

    @Test
    void twoTenantsWithSamePaymentIdGetDifferentKeys() {
        PaymentSubmitted payment = sample("PAY-1102", 4);

        assertTrue(input.send(factory().create(
                payment,
                new VerifiedPaymentContext(
                        "tenant-a", "evt-1102a", "BILLING"))));
        assertTrue(input.send(factory().create(
                payment,
                new VerifiedPaymentContext(
                        "tenant-b", "evt-1102b", "BILLING"))));

        PaymentReceipt first = nextReceipt();
        PaymentReceipt second = nextReceipt();

        assertEquals("tenant-a", first.tenantId());
        assertEquals("tenant-b", second.tenantId());
        assertNotEquals(
                first.businessCorrelationKey(),
                second.businessCorrelationKey());
    }

    @Test
    void duplicateMessageReturnsSameBusinessReceipt() {
        PaymentSubmitted payment = sample("PAY-1103", 1);
        Message<PaymentSubmitted> message = factory().create(
                payment,
                new VerifiedPaymentContext(
                        "tenant-a", "evt-1103", "BILLING"));

        assertTrue(input.send(message));
        assertTrue(input.send(message));

        PaymentReceipt first = nextReceipt();
        PaymentReceipt replay = nextReceipt();

        assertEquals(first, replay);
        // Tổng số event trong ledger có thể còn các test khác,
        // nên không assert bằng 1 trên singleton toàn suite.
    }

    @Test
    void missingOptionalHeaderDoesNotBlockValidPayment() {
        PaymentSubmitted payment = sample("PAY-1104", 2);
        Message<PaymentSubmitted> message = factory().create(
                payment,
                new VerifiedPaymentContext(
                        "tenant-a", "evt-1104", "BILLING"));

        // Không có sourceSystem. Các required headers vẫn giữ.
        Message<PaymentSubmitted> withoutSource =
                org.springframework.messaging.support.MessageBuilder
                        .fromMessage(message)
                        .removeHeader("sourceSystem")
                        .build();

        assertTrue(input.send(withoutSource));
        assertEquals(
                "evt-1104", nextReceipt().eventId());
    }
}
~~~

**Ý nghĩa của integration test:** Spring context thực sự đăng ký endpoint và method invocation phải tự giải quyết **@Payload**, **@Header**, **@Headers**. Điều này khác unit test gọi Java method trực tiếp.

### 18.1. Kết quả outputChannel và reply

Các test dùng QueueChannel vì ví dụ đã khai báo outputChannel rõ. Không nhầm đây với một test Gateway replyChannel: flow Gateway sync cần wiring request/reply riêng, có thể không dùng output queue này.

### 18.2. Cẩn thận state test và framework context caching

Spring test có thể cache ApplicationContext giữa các test. Fake InMemoryPaymentLedger là singleton trong context, nên event từ test trước có thể còn trong map. Test dùng các eventIds riêng để tránh phụ thuộc thứ tự và không assert tổng số bản ghi toàn context là 1. Nếu cần isolation tuyệt đối, reset test fixture có kiểm soát hoặc dùng @DirtiesContext theo nhu cầu.

### 18.3. Test timeout và lỗi hạ tầng không nằm trong ví dụ này

DirectChannel + fake ledger trong cùng JVM chỉ chứng minh **argument mapping** và đường output. Nó chưa kiểm tra database transaction, broker acknowledgment, redelivery sau restart, error channel của poller hay kết quả Gateway qua network.

## 19. Negative tests: thiếu header hoặc dữ liệu mâu thuẫn

Những test này quan trọng vì sai header có thể dẫn đến **trộn tenant** hoặc **gắn nhầm workflow** mà không báo lỗi rõ.

### 19.1. Header bắt buộc không tồn tại

~~~java
// Mảnh test bên trong PaymentHeaderMappingIntegrationTest.
@Test
void missingTrustedTenantHeaderRejectsBeforeBusinessEffect() {
    PaymentSubmitted payment = sample("PAY-1201", 2);
    String groupKey = PaymentCorrelation.key("tenant-a", payment);

    Message<PaymentSubmitted> missingTenant =
            org.springframework.messaging.support.MessageBuilder
                    .withPayload(payment)
                    .setHeader("businessEventId", "evt-1201")
                    .setHeader("businessCorrelationKey", groupKey)
                    .build();

    // Exception có thể là MessagingException wrapper tùy version.
    assertThrows(RuntimeException.class,
            () -> input.send(missingTenant));
    assertNull(output.receive(0));
}
~~~

Với một **@Header required**, framework không nên tự cấp một trusted tenant thay thế. Cần kiểm tra outcome bên ngoài flow để chắc chắn đã reject, đồng thời theo dõi error code/exception chain khi áp dụng thật.

### 19.2. Header businessCorrelationKey bị giả mạo

~~~java
// Mảnh test bên trong PaymentHeaderMappingIntegrationTest.
@Test
void forgedCorrelationHeaderIsRejected() {
    PaymentSubmitted payment = sample("PAY-1202", 1);

    Message<PaymentSubmitted> forged =
            org.springframework.messaging.support.MessageBuilder
                    .withPayload(payment)
                    .setHeader("trustedTenantId", "tenant-a")
                    .setHeader("businessEventId", "evt-1202")
                    .setHeader(
                            "businessCorrelationKey",
                            "payment:v1:tenant-b:PAY-1202:1")
                    .build();

    assertThrows(RuntimeException.class,
            () -> input.send(forged));
    assertNull(output.receive(0));
}
~~~

Handler tính lại expected groupKey từ tenantId và payload, nên mismatch bị chặn. **Nhưng ví dụ này vẫn giả định header trustedTenantId thực sự đáng tin**: nếu attacker được phép tự đặt cả tenantId và groupKey cùng một giá trị giả, phép so sánh chuỗi không thay thế authorization ở ingress.

### 19.3. Cùng event ID nhưng payload khác

~~~java
// Mảnh test bên trong PaymentHeaderMappingIntegrationTest.
@Test
void sameEventIdWithDifferentAmountIsAConflict() {
    VerifiedPaymentContext context =
            new VerifiedPaymentContext(
                    "tenant-a", "evt-1203", "BILLING");

    Message<PaymentSubmitted> first = factory().create(
            new PaymentSubmitted("PAY-1203", 1000, "VND", 1),
            context);
    Message<PaymentSubmitted> changed = factory().create(
            new PaymentSubmitted("PAY-1203", 2000, "VND", 1),
            context);

    assertTrue(input.send(first));
    assertNotNull(output.receive(0));

    assertThrows(RuntimeException.class,
            () -> input.send(changed));
    assertNull(output.receive(0));
}
~~~

Nếu eventId có phạm vi duy nhất theo **tenant + producer**, fake ledger key tenant+eventId chưa đủ cho production. Cần điều chỉnh key theo contract và tạo conflict detection trên payload digest/operation identity.

### 19.4. Sai kiểu header hoặc conversion thất bại

~~~java
// Ví dụ payload được xây dựng với header type không như contract.
Message<PaymentSubmitted> wrongHeaderType =
        org.springframework.messaging.support.MessageBuilder
                .withPayload(sample("PAY-1204", 1))
                .setHeader("trustedTenantId", java.util.List.of("tenant-a"))
                .setHeader("businessEventId", "evt-1204")
                .setHeader(
                        "businessCorrelationKey",
                        "payment:v1:tenant-a:PAY-1204:1")
                .build();
~~~

Đừng phụ thuộc vào một exception class duy nhất cho mọi kiểu header vì conversion có thể khác theo Spring version/converters. Trong hệ thống thật, kiểm tra exception cause và bảo đảm **không có side effect** khi một required identity header không đúng kiểu.

### 19.5. Không log toàn bộ headers khi assertion thất bại

Một test có thể in Message.toString() để debug, nhưng trong production headers có thể chứa token, session identifiers hoặc framework channel references. Log có cấu trúc với **eventRef**, **reasonCode**, **component**, **source** an toàn hơn dump nguyên Message.

## 20. Khi nào handler nên đọc một header, nhiều headers hay toàn Message?

Ba kiểu signature có ưu và nhược điểm khác nhau:

~~~java
// A: Tối thiểu, khai báo dependency chính xác.
public PaymentReceipt accept(
        @Payload PaymentSubmitted payment,
        @Header("trustedTenantId") String tenantId,
        @Header("businessEventId") String eventId) {
    // ...
}

// B: Cần một tập metadata phục vụ monitoring/diagnostics.
public PaymentReceipt accept(
        @Payload PaymentSubmitted payment,
        @Headers Map<String, Object> headers) {
    // ...
}

// C: Cần thao tác với Message trong tầng integration.
public PaymentReceipt accept(
        org.springframework.messaging.Message<PaymentSubmitted> message) {
    // ...
}
~~~

**Chúng là các chữ ký thay thế nhau**, không phải ba phương thức overload cần cùng đăng ký làm một Service Activator. Không copy/paste các method có cùng tên và kiểu trong một class thật.

| Tình huống | Lựa chọn ưu tiên | Vì sao |
| --- | --- | --- |
| Business service cần tenant và eventId | @Payload + @Header | Rõ ràng, ít coupling |
| Adapter cần kiểm tra ba bốn metadata | @Header cho từng trường hoặc typed context | Dễ test required/validation |
| Error/log decorator cần kiểm tra headers động | @Headers Map | Có thể quan sát nhiều field có chọn lọc |
| Một endpoint đang xây Message reply riêng | Message<?> | Cần ngữ cảnh runtime, nhưng phức tạp hơn |
| Flow nhỏ có logic ngắn | DSL .handle(payload, headers) | Không cần tạo annotation handler class |
| Xử lý nghiệp vụ trong domain layer | DTO + immutable BusinessContext | Không phụ thuộc Spring Message |

### 20.1. Tham số annotation không thay domain validation

Một method có thể nhận **String tenantId** hợp lệ về kiểu, nhưng không có bằng chứng tenant đó được phép đối với paymentId. Nên kiểm tra binding ở ingress:

~~~text
AuthenticatedPrincipal
    + paymentId / workflowEpoch
    + tenant registry / ACL
    -> VerifiedPaymentContext
    -> Spring Message headers
    -> @Header Java arguments
~~~

Không dùng constructor **VerifiedPaymentContext** với dữ liệu client chưa xác thực rồi coi đó là kiểm tra quyền.

### 20.2. Khi handler cần một giá trị dẫn xuất

Ví dụ một handler cần **businessCorrelationKey** được tính từ tenant+paymentId+epoch. Hai lựa chọn:

- Ingress đã xác minh và tính trước business key, handler đọc qua @Header và kiểm tra lại.
- Handler nhận typed BusinessContext rồi gọi service đáng tin để tra key.

Không để nhiều handlers tự tính key theo các thuật toán khác nhau (trường hợp có người thêm prefix hoặc normalize case tùy ý), vì cùng event có thể bị gắn nhiều group keys. Thuật toán correlation có version và contract phải dùng nhất quán.

## 21. Error handling: missing header không giống business rejection

Trong Java code, một số lỗi xảy ra **trước khi gọi method**, số khác xảy ra **trong method**, và số khác chỉ xuất hiện **sau khi service đã thực hiện side effect**.

~~~mermaid
flowchart TD
    A["Incoming Message"] --> M{"Argument mapping"}
    M -->|"Missing / invalid header"| E1["Mapping error"]
    M -->|"PASS"| B{"Business handler"}
    B -->|"Security / validation fail"| E2["Business rejection"]
    B -->|"Transient IO failure"| E3["Retry / recovery"]
    B -->|"Effect committed"| R{"Reply delivery"}
    R -->|"Reply arrived"| O["Receipt"]
    R -->|"Timeout / lost ack"| U["Unknown to caller"]
~~~

### 21.1. Đường lỗi trên DirectChannel

Trong flow DirectChannel đồng bộ:

- Argument resolver có thể ném exception do thiếu required header hoặc conversion lỗi.
- Service Activator có thể ném SecurityException/IllegalArgumentException khi metadata và payload mâu thuẫn.
- Exception có thể được Spring Integration wrap thành một MessagingException hoặc MessageHandlingException.
- Caller hoặc inbound adapter quyết định cách trả lỗi/ack/retry theo contract.

Vì vậy test có thể assert RuntimeException chung trước, sau đó kiểm tra **cause chain và error code** cụ thể theo Spring Integration version khi tích hợp chính thức. Không giả định mọi lỗi đều luôn có cùng class exception ngoài cùng.

### 21.2. Đường lỗi trên ExecutorChannel/poller

Khi handler chạy trên một executor hoặc poller, exception có thể được gửi thành **ErrorMessage** tới error channel thích hợp. ErrorMessage có payload là Throwable, có thể mang thông tin failedMessage trong những trường hợp hỗ trợ; không mặc định ErrorMessage payload chính là PaymentSubmitted.

Nếu muốn tạo failure outcome:

1. Tìm lại event/tenant/workflow identity từ nguồn đáng tin.
2. Phân loại lỗi schema, auth, business rejection, transient I/O hay unknown effect.
3. Chỉ tạo terminal business outcome nếu **nghiệp vụ thực sự đã biết kết quả**.
4. Giữ eventId/operationId qua retry.
5. Audit/quarantine khi thiếu metadata đáng tin.

**errorChannel không tự là durable DLQ**. Nếu cần lưu để xử lý sau restart, cấu hình storage/broker persistence và recovery policy.

### 21.3. Lỗi mapping không được retry như lỗi mạng vô hạn

Nếu message thiếu trustedTenantId do adapter luôn sai cấu hình, retry cùng input hàng nghìn lần không làm header xuất hiện. Nên phân loại:

| Lỗi | Retry? | Hướng xử lý |
| --- | --- | --- |
| Missing trustedTenantId | Không tự retry vô hạn | Security reject, fix ingress |
| Correlation mismatch | Không tiếp tục business effect | Quarantine/alert |
| Invalid amountMinor | Không retry nguyên payload | Source correction |
| Unsupported source schema | Không retry vô hạn | Update parser/contract |
| Database unavailable | Có thể retry bounded | Backoff + recovery |
| Reply delivery timeout sau commit | Không chạy effect mới bừa bãi | Idempotent lookup/reconcile |
| Duplicate exact event | Không tạo effect mới | Trả receipt cũ hoặc skip |
| Same event ID, different payload | Không coi là duplicate bình thường | ID_CONFLICT |

### 21.4. Không biến exception thành reply thành công giả

Phản ví dụ:

~~~java
try {
    return ledger.apply(payment, tenant, eventId, key);
} catch (Exception ex) {
    return new PaymentReceipt(
            tenant, payment.paymentId(), eventId, key,
            "RECORDED");
}
~~~

Một lỗi DB, thiếu quyền hoặc timeout không chứng minh thanh toán đã được ghi. Nếu cần kết quả UNKNOWN/PENDING, phải có domain state riêng, nguyên nhân và cơ chế reconciliation; không trả **RECORDED** chỉ để caller không thấy lỗi.

## 22. Retry và idempotency khi tham số @Header được lấy lại

Khi một message được redeliver, Spring Integration có thể tạo một **Message mới** hoặc tiếp tục sử dụng Message cũ tùy adapter/recovery. **ID kỹ thuật** và retry headers có thể khác, nhưng **businessEventId và businessCorrelationKey** của cùng logical operation phải ổn định.

~~~text
Attempt 1:
  Spring message ID: a1
  @Header("businessEventId"): evt-payment-1042
  @Header("businessCorrelationKey"): payment:v1:tenant-a:PAY-1042:3

Attempt 2:
  Spring message ID: b2
  @Header("businessEventId"): evt-payment-1042
  @Header("businessCorrelationKey"): payment:v1:tenant-a:PAY-1042:3
~~~

Handler có thể gọi ledger bằng đúng hai identity trên để chống duplicate. Nếu eventId bị tái tạo tại mỗi Service Activator invocation, ledger không có cách nhận ra cùng logical event.

### 22.1. Schema inbox bền thay cho in-memory Map

Một ví dụ PostgreSQL:

~~~sql
CREATE TABLE payment_event_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    producer_id VARCHAR(64) NOT NULL,
    event_id VARCHAR(96) NOT NULL,
    payment_id VARCHAR(64) NOT NULL,
    workflow_epoch INTEGER NOT NULL,
    business_key VARCHAR(220) NOT NULL,
    payload_digest VARCHAR(128) NOT NULL,
    processing_status VARCHAR(32) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, producer_id, event_id)
);

CREATE INDEX payment_event_inbox_status_idx
    ON payment_event_inbox (processing_status);
~~~

Ở đây producer_id được thêm vào identity vì một eventId có thể chỉ duy nhất trong một producer. Phải điều chỉnh theo contract thực tế. Cùng eventId nhưng payload_digest khác phải báo **ID_CONFLICT**, không overwrite silently.

### 22.2. Cửa sổ crash phải được giải quyết

~~~text
1. Ghi inbox status=SEEN
2. Commit
3. Crash trước khi Service Activator thực hiện side effect
4. Redelivery thấy SEEN và bị drop
=> Side effect bị mất vĩnh viễn
~~~

Cần **transactional inbox/outbox**, state machine hoặc recovery worker để phân biệt RECEIVED, DISPATCH_PENDING, EFFECT_COMMITTED, FAILED và đủ thông tin khôi phục. Đừng chỉ gọi một method được annotate @ServiceActivator rồi coi toàn bộ flow đã có atomic exactly-once semantics.

### 22.3. Retry advice có thể gọi handler nhiều lần

Nếu một handler được bọc bằng retry advice, business method có thể chạy lại sau exception. **Một header retryCount khác** không làm nghiệp vụ trở thành một operation mới. Giữ idempotency key ổn định, bảo vệ external API calls bằng provider idempotency key/lookup và kiểm thử trường hợp response bị mất sau khi effect commit.

### 22.4. Sequence headers không phải idempotency keys

Nếu Splitter tạo sequenceNumber=1,2,3, không dùng một mình sequenceNumber để dedup: mỗi parent batch đều có child #1. Đúng scope có thể là **tenant + parent event ID + child logical ID**, còn sequenceNumber chỉ là vị trí xử lý.

## 23. Security: trường header nào có thể cấp quyền?

Trả lời ngắn: **một String trong MessageHeaders không tự là quyền truy cập**. Dữ liệu chỉ đáng tin sau khi được tạo tại boundary có authentication/authorization phù hợp.

### 23.1. Kịch bản giả mạo qua HTTP

~~~http
POST /api/payments/events HTTP/1.1
X-Tenant-Id: tenant-admin
X-Role: SUPERUSER
X-Correlation-Id: payment:v1:tenant-admin:PAY-999:1
Content-Type: application/json

{"paymentId":"PAY-999","amountMinor":1000,"currencyCode":"VND","workflowEpoch":1}
~~~

Code sai:

~~~java
// Không làm:
String tenant = request.getHeader("X-Tenant-Id");
Message<?> internal = MessageBuilder
        .withPayload(parsedPayment)
        .setHeader("trustedTenantId", tenant)
        .build();
~~~

Code đúng về **thứ tự trách nhiệm**:

~~~text
HTTP request + security principal
    -> verify signature/session
    -> authorize principal against payment/tenant/workflow
    -> verified tenant from registry / principal binding
    -> TrustedPaymentMessageFactory
    -> @ServiceActivator @Header("trustedTenantId")
~~~

Nếu bên ngoài gửi một custom correlation header để tracing, có thể lưu riêng như **externalCorrelationRef** sau validate độ dài/charset, nhưng không cho nó thay businessCorrelationKey hoặc quyền tenant.

### 23.2. Header injection vào channel điều khiển

Spring Integration có những header đặc biệt ảnh hưởng việc gửi reply/lỗi hoặc routing. Nếu client tùy ý chỉ định replyChannel, errorChannel hoặc routingSlip, nó có thể làm luồng nội bộ gửi message tới destination ngoài dự kiến.

Không làm:

~~~java
// Phản ví dụ:
MessageBuilder.withPayload(payment)
        .copyHeaders(allHeadersFromHttpRequest)
        .build();
~~~

Chỉ map **business fields được allowlist**, dựng lại framework control headers trong phạm vi trusted internal flow khi thật sự cần.

### 23.3. Data minimization

Không để Service Activator nhận mọi header chứa Authorization token, cookie, broker secret hoặc PII rồi gửi toàn bộ sang domain service/log. Chỉ truyền những dữ liệu nghiệp vụ cần thiết: verified tenant, event ID, business correlation, payload có kiểu.

### 23.4. Test security boundary riêng

Các integration tests của mục 18 tạo VerifiedPaymentContext bằng stub. Chúng **không chứng minh** JWT/mTLS/broker ACL đã được cấu hình đúng. Production cần test controller/adapter với credential thực, tenant cross-access, expired token, invalid signature, replay và forged headers.

## 24. Observability: tìm được header bị mất ở hop nào

Một lỗi thường gặp là downstream chỉ báo “Missing trustedTenantId”, trong khi ingress đã xác nhận thanh toán được tiếp nhận. Vấn đề có thể nằm ở HeaderMapper, Transformer tạo Message mới, Router không giữ metadata mong đợi hoặc một callback đến từ flow khác.

### 24.1. Metrics nên có

| Metric | Ý nghĩa | Label có kiểm soát |
| --- | --- | --- |
| **service_activator_input_total** | Số messages tới endpoint | endpoint, sourceType |
| **service_activator_success_total** | Số handler calls thành công | endpoint, decision |
| **service_activator_error_total** | Lỗi business/mapping | endpoint, reasonCode |
| **service_activator_duration_seconds** | Latency handler | endpoint |
| **service_activator_missing_header_total** | Header bắt buộc thiếu | headerName từ allowlist |
| **service_activator_invalid_header_total** | Sai type, value hoặc scope | headerName, reason |
| **service_activator_correlation_mismatch_total** | businessKey sai | endpoint |
| **service_activator_duplicate_event_total** | Dedup/redelivery | producerType |
| **service_activator_identity_conflict_total** | Cùng eventId, payload khác | sourceType |
| **service_activator_reply_failure_total** | Lỗi gửi reply | endpoint |
| **service_activator_retry_total** | Retry attempts | errorClass hữu hạn |
| **service_activator_inbox_pending** | Event chưa commit | status |

Metric labels không nên mang tenantId, paymentId, eventId, correlationKey hoặc traceId với cardinality cao. Dùng structured logs/tracing có retention và quyền truy cập phù hợp để truy một logical event.

### 24.2. Log mẫu khi mapping thành công

~~~json
{
  "component": "paymentServiceActivator",
  "stage": "HANDLE",
  "eventRef": "evt-payment-1042",
  "source": "BILLING",
  "headerContractVersion": 1,
  "businessCorrelationRef": "redacted-group-reference",
  "result": "RECORDED"
}
~~~

### 24.3. Log mẫu khi header không hợp lệ

~~~json
{
  "component": "paymentServiceActivator",
  "stage": "ARGUMENT_BINDING",
  "headerName": "trustedTenantId",
  "reasonCode": "MISSING_REQUIRED_HEADER",
  "result": "REJECTED"
}
~~~

Đây là **log ứng dụng minh họa**, không phải format mà Spring Integration tự sinh. Khi framework không thể resolve argument, body method có thể chưa chạy; muốn metric/log tại bước argument binding, cần error handler/endpoint instrumentation phù hợp, không chỉ đặt log trong body handler.

### 24.4. Tracing và security context

Trace/span IDs có thể được propagate bởi instrumentation. Chúng giúp theo dõi từ adapter qua Service Activator nhưng không thay eventId, không cấp quyền tenant và không chứng minh business operation đã commit.

Với ExecutorChannel, một **ThreadLocal** chứa tenant của HTTP request trước đó có thể trống ở worker thread. Business identity phải xuất phát từ trusted Message/context đã được xác minh, không từ một ThreadLocal tình cờ còn tồn tại.

## 25. Runbook: @Header nhận null hoặc không nhận được giá trị

**Tình huống:** một method có @Header("businessEventId") String eventId, nhưng integration test hoặc production trả lỗi trước khi gọi handler.

### Bước 1 — Kiểm tra message thực sự đi vào đúng endpoint

Xác định channel inbound, Router mapping và Service Activator bean. Hai endpoint trên cùng DirectChannel có thể thay đổi consumer nhận message; nếu method không chạy, đừng vội kết luận @Header bị lỗi.

### Bước 2 — Kiểm tra payload type và bean method

Payload có thật là PaymentSubmitted không? Có Transformer đổi payload thành Map/String/Envelope không? Method có được @EnableIntegration và bean scan/register đúng không?

### Bước 3 — Kiểm tra chính xác tên header

~~~text
Expected Spring header:
  businessEventId

Actual Spring headers:
  BusinessEventID
  X-Business-Event-Id
  event_id
~~~

Đó là **các tên khác nhau**. HeaderMapper hoặc ingress factory cần tạo **businessEventId** như hợp đồng; không thay đổi @Header mỗi khi một đối tác đổi tên HTTP header.

### Bước 4 — Kiểm tra header hiện diện và kiểu

Một header có thể tồn tại nhưng sai kiểu:

~~~text
expected: trustedTenantId -> String
actual:   trustedTenantId -> List<String>
~~~

Nếu converter không xử lý, method argument binding có thể thất bại. Dùng log/test code để kiểm tra type và normalize tại ingress; không ép kiểu bừa rồi coi như identity đã được xác minh.

### Bước 5 — Kiểm tra required/optional contract

Nếu businessEventId bắt buộc, để mặc định required=true và reject khi thiếu. Nếu traceId phụ trợ có thể thiếu, dùng required=false rồi xử lý null đúng cách. Đừng đặt mọi header là optional để “khỏi bị lỗi” rồi làm mất bảo đảm nghiệp vụ.

### Bước 6 — Kiểm tra Transformer/subflow trước đó

Một Transformer trả payload thuần thường được framework hỗ trợ propagation headers; một handler tự tạo Message mới có thể thiếu các headers cần thiết. Xem code tạo Message, HeaderEnricher/HeaderFilter và các endpoint trung gian.

### Bước 7 — Kiểm tra adapter mapping

Qua HTTP/JMS/AMQP/TCP, MessageConverter và HeaderMapper quyết định dữ liệu nào đi qua wire. Nếu bên gửi ghi header trong Java Message nhưng bên nhận chỉ có payload JSON, cần thiết kế wire envelope hoặc selected header mapping.

### Bước 8 — Kiểm tra error channel và exception chain

Nếu lỗi xảy ra trước khi body method chạy, log đặt trong Service Activator sẽ không chạy. Xem cause chain, errorChannel/poller/adapter error handling. Đừng tự động retry missing tenant như lỗi mạng tạm thời.

### Bước 9 — Kiểm tra business correlation scope

Nếu Spring correlationId khác businessCorrelationKey, có thể là **đúng** khi đi qua Splitter nested groups. Đối chiếu scope kỹ thuật và business; không ghi đè technical correlationId toàn cục để tất cả trở nên giống nhau.

### Bước 10 — Xác minh sau sửa

Gửi một event hợp lệ rồi assert:

~~~text
@Payload.paymentId            == PAY-1042
@Header.trustedTenantId       == tenant-a
@Header.businessEventId       == evt-payment-1042
@Header.businessCorrelationKey== payment:v1:tenant-a:PAY-1042:3
PaymentReceipt                == RECORDED
~~~

Tiếp theo thử message thiếu header, sai tenant, eventId trùng và input đến từ adapter thực để bảo đảm **không tạo side effect sai**.

## 26. Các anti-pattern khi mapping header vào tham số

| Anti-pattern | Vì sao nguy hiểm | Cách thay |
| --- | --- | --- |
| Đoán tên header theo tên biến Java | Refactor làm binding mơ hồ | Dùng @Header với tên tường minh |
| Coi HTTP X-Tenant-Id là trustedTenantId | Client có thể giả mạo | Auth + registry binding |
| Đặt required=false cho mọi header | Missing identity bị giấu | Required theo hợp đồng |
| Default eventId bằng UUID mới | Redelivery vượt dedup | Stable logical eventId |
| CopyHeaders toàn bộ từ external message | Có thể nhập replyChannel/errorChannel không an toàn | Allowlist + verified context |
| Map Number/String tùy tiện | Runtime conversion lỗi | Parse/validate tại ingress |
| Dùng MessageHeaders.ID làm business ID | Message build lại có ID mới | Header businessEventId riêng |
| Dùng replyChannel làm correlation key | Mỗi invocation có channel riêng | Business correlation bền |
| Đưa Header Map nguyên vào domain | Coupling với hạ tầng/secret leakage | Immutable BusinessContext |
| Dùng group.size() để suy đủ outcomes | Duplicate có thể làm sai | Unique members + release strategy |
| Cho hai Service Activators cùng input DirectChannel | Có thể cạnh tranh messages | Một flow rõ owner hoặc publish-subscribe có chủ đích |
| Gắn header sau khi đã ghi side effect | Validation đến quá muộn | Verify trước khi dispatch |
| Tự mutate MessageHeaders | Trái semantics immutable, khó trace | MessageBuilder hoặc HeaderEnricher |
| Dùng ThreadLocal tenant trong async handler | Thread khác không còn context | Verified header/context |
| Nuốt exception rồi trả RECORDED | Che lỗi và tạo false success | Typed error + recovery |
| Coi @Header là authorization | Annotation chỉ lấy giá trị | Security boundary trước handler |
| Không test error path | Missing/malformed header chỉ lỗi ở production | Negative + contract tests |
| Retry full flow vô hạn | Side effects có thể lặp | Bounded retry + ledger/reconcile |
| Tạo one-way handler nhưng Gateway đợi reply | Reply timeout | Rõ request/reply contract |

## 27. Bài thực hành: mapping header từ ba nguồn vào cùng Service Activator

Thiết kế luồng ghi nhận **OrderPaymentEvent** từ HTTP, JMS và một job nội bộ:

~~~mermaid
flowchart LR
    A["HTTP adapter"] --> V["Ingress verify"]
    B["JMS adapter"] --> V
    C["Internal scheduler"] --> V
    V --> M["MessageBuilder trusted headers"]
    M --> S["@ServiceActivator"]
    S --> D["Domain service / inbox"]
    D --> R["Receipt / status"]
~~~

### 27.1. Hợp đồng đầu vào

Payload:

~~~java
record OrderPaymentEvent(
        String orderId,
        String paymentReference,
        long amountMinor,
        String currencyCode,
        int workflowEpoch) {
}
~~~

Trusted Spring headers:

~~~text
trustedTenantId         -> String, bắt buộc
businessEventId         -> String, bắt buộc
businessCorrelationKey  -> String, bắt buộc
sourceSystem            -> String, optional cho log
traceId                 -> String, optional cho tracing
workflowEpoch           -> Integer, bắt buộc nếu không đọc từ payload
~~~

Nếu workflowEpoch được lưu cả trong payload và header, Service Activator phải **so sánh tính nhất quán**; không chọn một trong hai tùy tiện. Nếu có một source of truth từ registry, tốt hơn tính business key ở ingress và không lặp metadata dư thừa không cần thiết.

### 27.2. Các bước triển khai

1. Tạo DTO cho payload, validate currency, amount, order/payment identity.
2. Định nghĩa verified identity/context từ principal, certificate hoặc broker ACL.
3. Kiểm tra quyền tenant đối với orderId/paymentReference và workflowEpoch.
4. Xây dựng **MessageBuilder** gắn các trusted headers đúng tên/kiểu.
5. Viết @ServiceActivator nhận @Payload và ba @Header bắt buộc.
6. Thêm một @Header optional cho traceId hoặc sourceSystem.
7. Nếu thực sự cần nhiều metadata, thử @Headers Map và sau đó refactor thành typed context.
8. Viết một lựa chọn DSL .handle(payload,headers) để so sánh, **không đăng ký đồng thời hai endpoint trên cùng DirectChannel**.
9. Tạo một error path cho missing/invalid header và authorization mismatch.
10. Cấu hình outputChannel hoặc Gateway reply path theo request/reply contract.
11. Viết fake ledger idempotent cho unit test và store bền cho integration stage production.
12. Thử một event bị redeliver với cùng businessEventId.
13. Thử cùng eventId nhưng payload digest khác: phải báo ID_CONFLICT.
14. Thử hai tenant cùng orderId: businessCorrelationKey phải khác.
15. Thử replyChannel không tồn tại khi flow one-way; handler không nên cố dùng nó làm business key.
16. Thêm trace/log và metrics lỗi mapping nhưng không log token hoặc raw payload nhạy cảm.

### 27.3. Ma trận kiểm thử

| Case | Điều kiện | Mong đợi |
| --- | --- | --- |
| A | Đủ required headers | Handler nhận đúng từng argument |
| B | sourceSystem thiếu | Vẫn chạy nếu contract cho optional |
| C | trustedTenantId thiếu | Reject trước business side effect |
| D | trustedTenantId sai kiểu | Reject/convert theo contract được test |
| E | businessCorrelationKey sai tenant | Reject, không ghi ledger |
| F | businessEventId thiếu | Reject/quarantine, không sinh UUID tại retry |
| G | Cùng eventId và cùng payload | Idempotent replay |
| H | Cùng eventId nhưng payload thay đổi | ID_CONFLICT |
| I | Hai tenant cùng paymentId | Hai business groups độc lập |
| J | HTTP header giả mạo tenant-admin | Security ingress reject |
| K | JMS message mất custom header | Adapter mapping error, không false success |
| L | Transformer tạo Message mới mất header | Contract test phát hiện |
| M | Gateway sync không có reply path | Timeout đúng hợp đồng, không coi effect thất bại |
| N | ExecutorChannel chuyển thread | Identity không phụ thuộc ThreadLocal |
| O | Splitter tạo child messages | sequence/correlation đúng scope |
| P | Broker redelivery sau commit | Không thực hiện effect lần hai |

### 27.4. Tiêu chí đạt

Một người đọc code handler phải nhìn thấy ngay:

- Dữ liệu nào là **payload nghiệp vụ**.
- Metadata nào lấy từ **@Header**.
- Header nào **required** hoặc **optional**.
- Ai xác minh tenant, event ID và business key trước khi handler chạy.
- Handler tạo reply hay một one-way side effect.
- Cách lỗi mapping được ghi nhận và retry/quarantine.
- Cách event bị redeliver không gây tác động trùng.

Nếu người đọc cần lần mò tất cả HTTP/JMS fields trong business method để hiểu tenant hoặc correlation, boundary mapping chưa đủ rõ.

## 28. Câu hỏi tự kiểm tra

1. Service Activator có vai trò gì giữa Spring Message và Java business service?
2. Một message có payload PaymentSubmitted và header trustedTenantId: tham số nào nên dùng @Payload, tham số nào dùng @Header?
3. @Header("businessEventId") khác @Headers Map<String,Object> như thế nào?
4. Nếu @Header required=true nhưng message thiếu header, body method có nhất thiết được chạy không?
5. Header tồn tại nhưng là chuỗi rỗng có được xem là hợp lệ nghiệp vụ không?
6. Tại sao không đặt default tenantId="public" để tránh lỗi thiếu header?
7. Header tên **X-Tenant-Id** ở HTTP có tự trở thành **trustedTenantId** trong Spring Message không?
8. HeaderMapper có tự chứng minh một tenant được phép với payment không?
9. Vì sao không copy toàn bộ HTTP headers vào MessageBuilder?
10. @Header có thể giải quyết trường hợp String trên wire phải thành UUID hay Integer bằng cách nào? Cần kiểm tra gì?
11. Khi nào nên nhận Message<?> thay vì nhiều @Header parameters?
12. Lý do nào khiến @Headers Map làm business layer phụ thuộc hạ tầng nhiều hơn?
13. Spring MessageHeaders.ID có nên dùng làm eventId phục vụ dedup không?
14. businessCorrelationKey khác replyChannel và technical correlationId của Splitter như thế nào?
15. Nếu Service Activator trả PaymentReceipt nhưng không có output/reply route, Gateway caller có nhận được kết quả không?
16. Một method Service Activator trả void có ý nghĩa gì với flow request/reply?
17. Vì sao một Transformer trả Message mới có thể làm mất header?
18. Khi nào MessageBuilder.fromMessage hữu ích và khi nào có rủi ro?
19. Tại sao cùng payload/eventId nhưng khác tenant phải nằm ở namespace idempotency khác nhau?
20. Một eventId bị dùng lại với payload khác nên trả “already processed” hay “conflict”?
21. Fake ConcurrentHashMap ledger có đủ chống duplicate qua restart và nhiều instances không?
22. Header retryCount tăng có phải business event mới không?
23. Khi missing header xảy ra trước khi handler chạy, nên đặt metrics/log ở đâu?
24. Vì sao không retry một schema lỗi vĩnh viễn giống một lỗi DB tạm thời?
25. Khi ExecutorChannel đổi thread, có nên lấy tenant từ ThreadLocal của HTTP request không?
26. Một ErrorMessage trên errorChannel có tự mang payload PaymentSubmitted không?
27. Nếu một Gateway timeout sau khi side effect đã commit, có thể retry vô điều kiện không?
28. Làm sao test sự khác nhau giữa unit test trực tiếp và integration test @Header argument resolver?
29. Vì sao không để hai Service Activators cạnh tranh trên cùng DirectChannel nếu chỉ cần một handler?
30. Những lỗi nào phát sinh nếu dùng sequenceNumber một mình làm idempotency key?

## 29. Checklist trước khi triển khai Service Activator mapping

- Method có **@ServiceActivator** được đăng ký vào đúng inputChannel.
- Đã chọn **@Payload**, **@Header** hoặc **@Headers** đúng nhu cầu, không dựa vào tên tham số ngầm.
- Những headers có business significance dùng tên rõ ràng, nhất quán giữa producer và consumer.
- Required/optional contract được định nghĩa riêng cho từng header.
- Thiếu tenant, eventId hoặc business correlation bắt buộc được reject trước effect.
- Header type và conversion được test với message thực, không chỉ gọi Java method trực tiếp.
- Ingress xác thực producer/tenant và business object/workflow epoch.
- Không tin các header tự khai như X-Tenant-Id, X-Role, X-Correlation-Id.
- MessageBuilder tại trust boundary sử dụng header allowlist; không copy live control headers từ external input.
- BusinessCorrelationKey có namespace tenant/entity/workflow instance và thuật toán versioned.
- eventId là logical identity ổn định qua retry; không dùng MessageHeaders.ID.
- Custom headers được map đúng qua HTTP/JMS/AMQP/TCP adapters hoặc versioned envelope.
- Nếu Transformer tạo Message mới, cần kiểm tra những trusted/runtime headers phải được giữ.
- CorrelationId, sequenceNumber, sequenceSize chỉ được dùng đúng scope Splitter/Aggregator.
- ReplyChannel/errorChannel thuộc runtime control; không đưa vào domain context hoặc wire DTO không portable.
- Handler ghi business effect có transaction và idempotency/ledger thích hợp.
- Duplicate event và eventId conflict có chính sách rõ ràng.
- Có recovery khi crash giữa inbox insert, dispatch và effect commit.
- Error handling phân biệt lỗi mapping, auth, schema, transient IO và unknown external effect.
- DirectChannel/async/poller/broker ack semantics được test theo topology đang dùng.
- Gateway request/reply có output/reply path và timeout bounded; one-way method không bị coi là sync result.
- Tracing/metrics đọc metadata cần thiết nhưng không log token, secrets hoặc raw payload nhạy cảm.
- Queue channels, executors, retries và quarantine có giới hạn và retention.
- Unit tests chứng minh business logic xử lý arguments đã được truyền.
- Spring integration tests chứng minh framework thực sự bind @Header, @Headers và @Payload.
- Negative tests bao phủ missing header, sai kiểu, correlation mismatch, tenant spoofing, duplicate và ID_CONFLICT.
- Adapter contract tests bao phủ header names/casing/conversion, multi-value headers và schema upgrades.
- Đã có runbook điều tra từ inbound adapter → MessageBuilder → Transformer/Router → Service Activator → Ledger/reply.

## 30. Tổng kết

**Mapping header vào tham số** giúp một Service Activator nhận được đúng **payload** và những **metadata** mà Java method cần mà không phải truy xuất toàn bộ Spring Message bằng tay:

~~~java
@ServiceActivator(inputChannel = "verifiedPayments")
public PaymentReceipt accept(
        @Payload PaymentSubmitted payment,
        @Header("trustedTenantId") String tenantId,
        @Header("businessEventId") String eventId,
        @Header("businessCorrelationKey") String groupKey) {
    // Validate identity và xử lý nghiệp vụ có idempotency.
}
~~~

**@Payload** ánh xạ nội dung message vào DTO có kiểu. **@Header** ánh xạ một metadata có tên và required/optional semantics. **@Headers** giúp nhận một tập headers khi endpoint thực sự cần. Java DSL **.handle(payload, headers)** và handler nhận **Message<?>** là các phương án thay thế khi cấu trúc flow phù hợp.

Quan trọng hơn cú pháp annotation là **chủ sở hữu của metadata**:

~~~text
External HTTP/JMS/AMQP message
    -> parse + authenticate + authorize
    -> build trusted Spring Message headers
    -> Router / Transformer / subflows
    -> @ServiceActivator argument mapping
    -> typed business context + idempotent operation
    -> reply / error / persistent state
~~~

Nếu tenant, eventId hoặc correlation chưa được xác minh ở ingress, annotation không tự biến chúng thành dữ liệu đáng tin. Nếu một Transformer, adapter hoặc Gateway không giữ header theo đúng contract, method có thể thiếu argument dù code business không đổi. Vì thế **kiểm thử cả method và Spring runtime mapping**, cùng với error path, retry và trust boundary, là điều kiện để sử dụng Service Activator an toàn trong một hệ thống Spring Integration nhiều nhánh.

## Tài liệu tham khảo

- [Enterprise Integration Patterns — Service Activator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingAdapter.html): kết nối logic nghiệp vụ với hệ thống messaging thông qua điểm kích hoạt dịch vụ.
- [Spring Integration Reference — Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html): POJO method invocation, input/output channels, request/reply và endpoint configuration.
- [Spring Integration Reference — Annotation Support](https://docs.spring.io/spring-integration/reference/configuration/annotations.html): @ServiceActivator và các endpoint annotations.
- [Spring Framework API — @Header](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Header.html): binding một Message header vào Java method parameter, required/default semantics.
- [Spring Framework API — @Headers](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Headers.html): binding tập Message headers vào method.
- [Spring Framework API — @Payload](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Payload.html): binding payload vào method parameter.
- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): Message, MessageHeaders và immutable message semantics.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): IntegrationFlow, handler lambdas, channels và composition.
- [Spring Integration Reference — Messaging Gateway](https://docs.spring.io/spring-integration/reference/gateway.html): Gateway request/reply, temporary reply channel và timeout.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, QueueChannel, ExecutorChannel và dispatch semantics.
- [Spring Integration Reference — Routers](https://docs.spring.io/spring-integration/reference/router.html): routing theo message content và header values.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): payload transformation và header propagation.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): sequence/correlation metadata của child messages.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): grouping và release strategy.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage, errorChannel và lỗi đồng bộ/bất đồng bộ.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): duplicate detection và giới hạn cần nhớ khi bảo vệ side effects.
