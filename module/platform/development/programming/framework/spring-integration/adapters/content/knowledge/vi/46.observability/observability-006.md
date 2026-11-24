# Logging payload có kiểm soát trong Spring Integration Adapters

## 1. Vì sao không nên log toàn bộ payload?

Trong Spring Integration, message có thể mang nội dung file, bản ghi cơ sở dữ liệu, HTTP body, sự kiện Kafka, JMS/AMQP message, tài liệu lấy từ SFTP hoặc đối tượng Java đã được chuyển đổi. Khi một luồng lỗi, thao tác tưởng như nhanh nhất là in toàn bộ `Message<?>`, payload và headers. Đây cũng là cách dễ vô tình làm lộ **dữ liệu cá nhân, thông tin thanh toán, mật khẩu, access token, session cookie, private key, dữ liệu khách hàng và cấu trúc hệ thống nội bộ**.

**Logging payload có kiểm soát** là thiết kế cho phép thu thập **đủ thông tin để chẩn đoán** trong khi giới hạn **trường nào được ghi, ghi ở điểm nào, tần suất bao nhiêu, ai được đọc và giữ bao lâu**. Mặc định nên dùng metadata an toàn; chỉ bổ sung một phần dữ liệu nghiệp vụ đã được cho phép sau khi đánh giá mức độ nhạy cảm và nhu cầu điều tra.

Bài học thuộc chương **Observability** của module **SPRING_INTEGRATION_ADAPTERS**. Phạm vi module là tích hợp hệ thống ngoài qua inbound/outbound adapter, gateway, poller và MessageChannel, thực hành file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; đồng thời quan sát **hợp đồng message, lỗi và vòng đời kết nối**. Vì vậy trọng tâm không chỉ là cấu hình logger, mà là **đặt điểm quan sát đúng và không vô tình xuất dữ liệu nhạy cảm ở ranh giới adapter**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt log metadata, log payload đã rút gọn, log raw payload và audit nghiệp vụ.
2. Thiết lập **deny-by-default**, allowlist trường, giới hạn kích thước, redaction và chính sách retention.
3. Dùng **WireTap, MessageChannel, service activator, LoggingHandler/DSL logging** một cách có chủ đích.
4. Tránh lộ nội dung khi xử lý File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC, converter và error flow.
5. Tạo structured logs an toàn và nối với correlation ID, message history, Micrometer metrics và distributed tracing.
6. Kiểm thử chống rò rỉ, vận hành debug logging có thời hạn và điều tra khi log thực sự chứa dữ liệu nhạy cảm.

> **Giới hạn:** Ví dụ Java và cấu hình minh họa cách tiếp cận. Tên API/overload có thể thay đổi theo phiên bản Spring Integration, Spring Boot và logging stack; phải xác minh trên phiên bản dự án. Nội dung không cung cấp quyền mặc định để ghi PII hoặc secrets vào production log.

## 2. Thế nào là một bản ghi đủ để chẩn đoán?

Giả sử adapter nhận một đơn hàng qua HTTP và đẩy sang Kafka. Để biết thông điệp đã qua bước nào, hệ thống thường chỉ cần:

~~~json
{
  "event": "INTEGRATION_CHECKPOINT",
  "flow": "http-order-to-kafka",
  "component": "validateOrder",
  "direction": "inbound",
  "payload_type": "json",
  "size_bucket": "1kb-10kb",
  "schema_version": "v2",
  "outcome": "accepted",
  "correlation_ref": "opaque-correlation-id",
  "trace_ref": "trace-context-reference"
}
~~~

**Không cần** ghi full JSON đơn hàng, email, địa chỉ khách hàng, access token hoặc trường thanh toán để biết transformer nào thất bại. Những thông tin chi tiết hơn có thể được tra cứu qua **ID tham chiếu có kiểm soát** ở hệ thống nghiệp vụ nếu người điều tra có thẩm quyền.

### 2.1. Bốn cấp logging

| Cấp | Nội dung | Sử dụng |
|---|---|---|
| **L0 — Technical metadata** | Flow, component, message type, outcome, reason code, size bucket, duration | Mặc định cho production |
| **L1 — Approved business metadata** | Event type, schema version, phân loại tài liệu, opaque business reference | Khi đã đánh giá mức dữ liệu và phê duyệt |
| **L2 — Sanitized sample** | Một tập trường được allowlist, đã chuẩn hóa và kiểm thử redaction | Điều tra hạn chế, sampling và TTL |
| **L3 — Raw payload** | Toàn bộ body, file, record hoặc message | Mặc định **không được phép**; trường hợp đặc biệt cần quy trình chuyên biệt được ủy quyền, không đi qua log ứng dụng thông thường |

L2 không phải “toString rồi che vài chuỗi”. Cách an toàn hơn là **chủ động trích xuất đúng các trường được duyệt**, và với mọi dữ liệu khác thì không ghi. L3 thường có rủi ro lớn vì bản sao dữ liệu lan sang hệ lưu log, hệ tìm kiếm, cảnh báo, bản sao lưu và tài khoản hỗ trợ.

## 3. Phân loại dữ liệu trước khi quyết định log

### 3.1. Nhóm dữ liệu cần xem xét

| Nhóm dữ liệu | Ví dụ | Chính sách mặc định nên áp dụng |
|---|---|---|
| **Secret/credential** | Password, OAuth token, API key, private key, cookie, session token, recovery code | **Không ghi giá trị**, kể cả debug; chỉ ghi key ID/fingerprint an toàn khi cần |
| **Dữ liệu cá nhân** | Họ tên, email, số điện thoại, địa chỉ, định danh khách hàng | Không ghi mặc định; dùng opaque ref hoặc số liệu tổng hợp |
| **Dữ liệu tài chính/y tế/nhạy cảm** | Thông tin thanh toán, chẩn đoán, dữ liệu hợp đồng mật | Không ghi nội dung; theo yêu cầu kiểm soát ngành và policy |
| **Payload nghiệp vụ ít nhạy cảm** | Event type trong danh mục cố định, schema version | Có thể allowlist sau review |
| **Thông tin nội bộ** | Remote path, hostname, tên tenant, ID endpoint, queue/topic | Chỉ ghi mức cần thiết; tránh tiết lộ topology qua log xuất ngoài |
| **Technical metadata** | Direction, bounded error code, payload kind, retry count | Thường phù hợp nếu chuẩn hóa và không chứa giá trị từ người dùng |
| **Binary/opaque body** | PDF, ảnh, byte[], multipart file, protobuf | Không dump bytes/base64; có thể ghi loại, size bucket và checksum được duyệt |

**Ngay cả trường có vẻ vô hại cũng có thể nhạy cảm**: tên file có tên khách hàng, HTTP path chứa số tài khoản, Kafka key chứa email, exception message chứa raw request, hay correlation ID thực chất là số hợp đồng. Việc đổi tên field thành `masked` không làm nó tự an toàn.

### 3.2. Dữ liệu nào nên dùng cho điều tra?

Ưu tiên các thông tin không cần giữ nguyên nội dung:

- Flow/endpoint ID do ứng dụng đặt và nằm trong danh mục đã duyệt.
- Timestamp, duration, outcome, error classification hữu hạn.
- Message size **theo bucket** thay vì giá trị chi tiết khi size cũng nhạy cảm.
- Schema version, event category thuộc danh mục cho phép.
- Record count/batch count và retry attempt.
- Opaque correlation reference do hệ thống tin cậy tạo, không nhúng PII.
- Tham chiếu evidence/ticket để truy nội dung ở hệ thống có quyền, thay vì sao chép payload vào log.

### 3.3. Log không phải hệ lưu dữ liệu nghiệp vụ

Log thường được nhân bản tới collector, SIEM, search index, alerting và backup. **Xóa log trên một instance không xóa mọi bản sao**. Nếu một payload cần được lưu vì quy định/audit, hãy thiết kế một **kho dữ liệu hoặc audit store riêng** với phân quyền, mã hóa, retention và mục đích sử dụng rõ ràng.

## 4. Những vị trí dễ lộ payload trong Spring Integration

~~~mermaid
flowchart LR
    EXT[HTTP / SFTP / File / JMS / AMQP / Kafka / DB] --> IN[Inbound Adapter / Gateway]
    IN --> CH[Input MessageChannel]
    CH --> CV[Converter / Transformer]
    CV --> H[Filter / Router / Handler]
    H --> OUT[Outbound Adapter / Gateway]
    OUT --> TARGET[Remote Target]
    CH -. WireTap .-> SAFE[Safe Log Projection]
    CV -. Exception .-> ERR[Error Channel / ErrorMessage]
    H -. Observation .-> MET[Metrics / Tracing]
    SAFE --> COL[Protected Log Collector]
    ERR --> COL
    MET --> OBS[Monitoring]
~~~

Một vài điểm phát sinh log ngoài code nghiệp vụ:

1. **Framework DEBUG/TRACE** có thể ghi message, payload hoặc headers qua một số logger/adapter tùy phiên bản.
2. **`LoggingHandler`** hoặc DSL `.log(...)` có thể xuất dữ liệu nhiều hơn mong muốn nếu dùng expression mặc định hoặc in cả `Message`.
3. **WireTap** tạo nhánh quan sát; handler ở nhánh này có thể vô tình in raw payload.
4. **HTTP client/server logging** có thể capture request/response body và `Authorization`.
5. **Kafka/JMS/AMQP converter** có thể dump record/header khi parse thất bại.
6. **SFTP/File adapter** có thể log đường dẫn, tên file, permissions hoặc nội dung nếu custom code in object.
7. **JDBC/ORM SQL logging** có thể hiển thị bind parameters và dữ liệu bản ghi.
8. **Exception stack trace** có thể kèm URL có query token, body lỗi của đối tác hoặc các giá trị bị đưa vào exception message.
9. **Tracing baggage/span attributes** có thể đưa nội dung message sang backend tracing.

**Phạm vi kiểm soát** phải bao trùm code, framework log level, middleware/client và telemetry exporters; không chỉ che payload tại một service activator.

## 5. Chính sách logging theo môi trường và mục đích

| Môi trường | Mặc định | Khi cần điều tra |
|---|---|---|
| **Unit test** | Có thể dùng dữ liệu giả đã tạo | Test logic log projection và anti-leak |
| **Local dev** | Metadata + dữ liệu giả; không dùng credentials production | Tăng chi tiết trên fixture an toàn |
| **Staging** | Metadata đã chuẩn hóa và synthetic fixtures | Bật sanitized sample theo kiểm thử |
| **Production** | L0, một số L1 đã duyệt; không raw body | Activation có ticket/owner/TTL, sampling và kiểm soát xuất log |

### 5.1. Không chỉ dựa vào logger level

Chuyển `DEBUG` thành `INFO` không phải cơ chế bảo vệ dữ liệu nếu một logger `INFO` đang in toàn bộ payload. Ngược lại, bật `TRACE` cho toàn bộ package Spring Integration có thể kích hoạt logging ở nhiều nơi không được rà soát.

**Mặc định an toàn:** mỗi vị trí log dùng **safe projection** dù log level là gì; bật debug chỉ làm tăng số checkpoint hoặc tần suất sampling, **không mở khóa nội dung nhạy cảm**.

### 5.2. Điều kiện bật log chi tiết tạm thời

Trước khi bật một chế độ tăng chi tiết ở production, nên có:

1. Incident/ticket và lý do cần dữ liệu bổ sung.
2. Flow, component, môi trường và tập message **được giới hạn**.
3. Đánh giá data classification; trường nào được allowlist và trường nào phải loại bỏ.
4. Người có thẩm quyền phê duyệt theo chính sách.
5. Sampling rate, dung lượng/volume dự kiến và **thời gian hết hạn**.
6. Backend nhận log, quyền truy cập, retention và phương án ngừng chế độ debug.
7. Phép thử tránh lộ credential/PII trước khi đưa vào sản xuất.
8. Hậu kiểm và xác nhận cấu hình trở về baseline.

**Không** bật log nội dung hàng loạt để tìm một message nếu chỉ cần correlation ID, error code và trace.

## 6. Logging message body khác logging header thế nào?

Một Spring Message gồm `payload` và `headers`. Nhiều người tập trung che body nhưng bỏ sót:

| Vị trí | Dữ liệu nhạy cảm có thể xuất hiện |
|---|---|
| Payload | JSON chứa email, XML chứa tài khoản, binary document, database row |
| HTTP headers | Authorization, Cookie, Set-Cookie, custom API key, client certificate metadata |
| JMS/AMQP headers | Application properties chứa token, user/key, trace baggage không được kiểm soát |
| Kafka headers/key | Business ID mang PII, token trong custom header, tenant identifier |
| Spring Integration headers | `file_name`, remote path, reply/error channel, original file, internal routing |
| Error message | Failed payload, nested exception, original message, URL, raw response |
| Message object string | Có thể stringify payload **và** headers, tùy type/implementation |

### 6.1. Header allowlist thay vì blacklist

**Blacklist** chỉ loại những tên biết trước như `Authorization`, trong khi key tùy biến `x-session-secret` vẫn có thể bị in. Với log chẩn đoán, nên **tạo object log mới chỉ có các field được phép** (flow ID, endpoint ID, outcome, payload kind) và không duyệt/copy toàn bộ headers.

### 6.2. Không tin mọi header do bên gửi cung cấp

Một HTTP caller hay Kafka producer bên ngoài có thể đặt `correlationId` hoặc `eventType` chứa giá trị bất kỳ, kể cả ký tự xuống dòng giả mạo log, chuỗi rất dài hoặc PII. Cần xác thực định dạng, chuẩn hóa, giới hạn độ dài và tốt nhất phát **opaque ID nội bộ** tại ingress nếu nguồn không đáng tin.

## 7. WireTap là điểm quan sát, không phải công cụ tự bảo vệ dữ liệu

Trong Spring Integration, `WireTap` (channel interceptor) có thể chuyển message tới một kênh thứ cấp để quan sát mà flow chính vẫn tiếp tục. Nó hữu ích khi muốn thêm checkpoint mà không sửa mọi handler.

~~~mermaid
flowchart LR
    SRC[Inbound] --> INPUT[rawInput]
    INPUT --> FLOW[Business Flow]
    INPUT --> TAP[WireTap]
    TAP --> LOGCH[safeLogChannel]
    LOGCH --> PROJ[Allowlist + Classification]
    PROJ --> LOG[Structured Log]
    FLOW --> OUT[Outbound]
~~~

### 7.1. Rủi ro với WireTap

- **Không tự redaction:** message gửi sang kênh phụ vẫn có thể chứa payload và headers gốc.
- **Không tự bền vững:** log branch không phải audit store hay message backup.
- **Ảnh hưởng hiệu năng:** xử lý đồng bộ/logging chậm có thể tăng latency; xử lý async có thêm queue, memory và rủi ro mất log khi đầy.
- **Mutable payload:** nếu payload chứa object có thể bị sửa, nhánh quan sát và business flow có thể cùng tham chiếu object đó; không giả định luôn có bản sao sâu.
- **Exception:** lỗi ở logger, appender hay safe projection cần được xử lý theo kiến trúc; đừng để một chức năng debug tùy chọn làm hỏng message business ngoài chủ đích.
- **Lifecycle:** nếu queue log bị đầy, phải có drop/backpressure policy, metric và cảnh báo; không im lặng để tích tụ dữ liệu nhạy cảm trong bộ nhớ.

### 7.2. Quy tắc thiết kế

**WireTap chỉ nên gửi tới một consumer chuyên tạo safe log record**, không tới một logger gọi `message.toString()`. Kênh quan sát cần có tên rõ, quyền truy cập, giới hạn lưu lượng và được kiểm thử cùng flow nghiệp vụ.

## 8. Ví dụ Java DSL: gắn WireTap và consumer ghi metadata an toàn

Ví dụ sau trình bày một flow nhận message, dùng WireTap tại channel và xử lý nghiệp vụ bình thường; một handler riêng đọc **metadata tối thiểu**. Import và API cần đối chiếu version đang triển khai.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
public class SafeLoggingFlowConfiguration {

    @Bean
    MessageChannel rawInput() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel safeLogChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel businessInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow inboundFlow() {
        return IntegrationFlow.from("rawInput")
                .wireTap("safeLogChannel")
                .channel("businessInput")
                .get();
    }

    @Bean
    @ServiceActivator(inputChannel = "safeLogChannel")
    MessageHandler safeLogHandler() {
        return SafeLogProjection::writeLog;
    }

    @Bean
    @ServiceActivator(inputChannel = "businessInput")
    MessageHandler businessHandler() {
        return message -> {
            // Thực thi nghiệp vụ; không log raw payload.
        };
    }
}
~~~

**Điều quan trọng:** đoạn demo chỉ trình bày đường kết nối. Việc dùng `DirectChannel` cho nhánh log có thể gây chi phí đồng bộ; khi xây hệ throughput cao cần cân nhắc **executor có giới hạn, backpressure và kiểm thử lỗi**. Trường hợp auditing bắt buộc không nên chỉ dựa vào WireTap phụ trợ.

## 9. Ví dụ Java: tạo safe log projection thay vì in message

Một lớp log cơ bản có thể chỉ ghi **ID message nội bộ, loại payload hữu hạn và event type thuộc allowlist**. Nó không đọc toàn bộ body.

~~~java
import java.io.File;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;

public final class SafeLogProjection {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeLogProjection.class);

    private static final Set<String> APPROVED_EVENTS =
            Set.of("ORDER_RECEIVED", "INVOICE_IMPORTED", "FILE_READY");

    private SafeLogProjection() {}

    public static void writeLog(Message<?> message) {
        Object rawEvent = message.getHeaders().get("eventType");
        String eventType =
                rawEvent instanceof String
                && APPROVED_EVENTS.contains(rawEvent)
                        ? (String) rawEvent
                        : "OTHER";

        String payloadKind = classifyPayload(message.getPayload());

        LOG.info(
                "event=INTEGRATION_CHECKPOINT flow=orders "
                + "outcome=received payload_kind={} event_type={} "
                + "message_ref={}",
                payloadKind, eventType, message.getHeaders().getId()
        );
    }

    private static String classifyPayload(Object payload) {
        if (payload instanceof byte[]) {
            return "binary";
        }
        if (payload instanceof String) {
            return "text";
        }
        if (payload instanceof File) {
            return "file";
        }
        return "object";
    }
}
~~~

### 9.1. Vì sao ví dụ này hạn chế rò rỉ?

- `payload` **không bị gọi `toString()`** hoặc serialize.
- Chỉ ba giá trị `eventType` hợp lệ được ghi; mọi giá trị khác là `OTHER`.
- Không copy bất kỳ header tùy biến nào vào log.
- `flow` và `outcome` là giá trị hằng do code xác định.
- Message ID ở đây là ID Spring Message, dùng làm tham chiếu trong phạm vi ứng dụng; **không mặc định tương đương business ID xuyên hệ thống**.

### 9.2. Điểm còn cần quyết định khi production

1. Mức độ cho phép ghi message ID và thời gian retention theo privacy policy.
2. Có nên giảm tần suất `INFO` để tránh log volume lớn.
3. Cách thêm `traceId/correlationRef` đã kiểm tra và không chứa PII.
4. Khi payload là `InputStream` hoặc object lazy, không được đọc nội dung chỉ để tạo log.
5. Cách chống logger/appender ném exception, queue log đầy và thay đổi tác động tới throughput.
6. Cách đặt code logging để không đánh giá payload chỉ nhằm xuất thông tin không cần thiết.

## 10. LoggingHandler và DSL `.log(...)`: cần kiểm soát biểu thức

Spring Integration có `LoggingHandler` và các tiện ích DSL `log(...)` hỗ trợ ghi thông tin message trong flow. Một số cách dùng mặc định có thể ghi payload hoặc message object. **Không dùng trực tiếp `.log()` một cách thiếu kiểm tra trên đường dữ liệu nhạy cảm**.

### 10.1. Nguyên tắc chọn cách triển khai

| Cách làm | Khi phù hợp | Điều phải kiểm tra |
|---|---|---|
| Custom handler như mục 9 | Muốn kiểm soát chính xác trường được xuất | Chỉ dùng safe projection, không raw headers |
| DSL `log(...)` với biểu thức rõ ràng | Muốn checkpoint gọn trong flow | Biểu thức không trả payload/Message; xác minh overload/version |
| `LoggingHandler` cấu hình level/expression | Hệ thống Java/XML cấu hình handler riêng | Đảm bảo không log raw theo default |
| Framework logger DEBUG/TRACE | Điều tra nội bộ thư viện theo sự cố | Scope, TTL và khả năng log headers/payload |
| WireTap + bounded logging channel | Muốn tách logging khỏi business handler | Queue/memory, logger failures, leak test |

### 10.2. Biểu thức log nên tạo dữ liệu mới có kiểm soát

Ví dụ **logic mong muốn** cho một checkpoint:

~~~text
Chỉ xuất:
  checkpoint = "validateInvoice"
  flow = "sftp-invoice-import"
  outcome = "accepted"
  correlation_ref = validatedOpaqueRef
  payload_kind = "json"

Không xuất:
  payload
  message.toString()
  headers.toString()
  full failed message
  raw exception message
~~~

Khi dùng SpEL, Kotlin DSL hoặc Java DSL, kết quả expression phải là **giá trị đã được phân loại an toàn**, không phải cách viết khác của `payload.toString()`. Sự an toàn phụ thuộc chính dữ liệu cuối cùng vào appender, không phụ thuộc việc gọi API nào.

## 11. Không log payload bằng cách gọi `toString()` của object

Các đối tượng Java thường có `toString()` phục vụ debug, nhưng chúng có thể bao gồm:

- Mọi field của DTO qua Lombok `@Data` hoặc `@ToString`.
- Hibernate/JPA entity với quan hệ dữ liệu và giá trị nhạy cảm.
- Collection chứa hàng nghìn phần tử.
- Value object có token/secret trong field.
- URL kèm query parameters bí mật.
- Java `Message<?>` chứa payload và headers.

Một thay đổi nhỏ ở DTO có thể làm log tiết lộ trường mới dù code logger không đổi.

### 11.1. Ví dụ anti-pattern

~~~java
// Không an toàn cho payload không được phân loại:
log.debug("Received message={}", message);
log.info("Payload={}", message.getPayload());
log.warn("Headers={}", message.getHeaders());
log.error("Failed payload=" + payload, exception);
~~~

### 11.2. Ví dụ thay thế

~~~java
log.warn(
    "event=PAYLOAD_REJECTED flow=invoice-import "
    + "reason_code={} payload_kind={} message_ref={}",
    "INVALID_SCHEMA",
    "json",
    message.getHeaders().getId()
);
~~~

**Lưu ý:** `reason_code` được thiết kế như enum hữu hạn, không phải raw exception text hoặc body từ remote service. Nếu cần debug item cụ thể, dùng ID tham chiếu do hệ thống tin cậy phát và tra dữ liệu trong kho có quyền.

## 12. Redaction, masking, tokenization và allowlist

### 12.1. Bốn kỹ thuật khác nhau

| Kỹ thuật | Ví dụ | Giới hạn |
|---|---|---|
| **Omission** | Không ghi field `email` | An toàn và đơn giản nhất khi không cần field |
| **Allowlist projection** | Chỉ lấy `eventType`, `schemaVersion` | Cần kiểm soát schema và giá trị field |
| **Masking/redaction** | Thay email bằng `[REDACTED]` | Có thể bỏ sót cấu trúc lồng nhau/alias |
| **Tokenization/HMAC reference** | Chuyển ID nhạy cảm thành opaque ref có kiểm soát | Vẫn có rủi ro liên kết lại; phải quản lý key và quyền |

**Hash thường** của email/số điện thoại có entropy thấp không mặc nhiên làm dữ liệu vô danh; có thể bị đoán bằng dictionary. Nếu phải tạo tham chiếu ổn định, cân nhắc phương án **HMAC có quản lý khóa**, phân tách mục đích sử dụng và retention; dữ liệu đầu ra vẫn cần xem theo chính sách privacy.

### 12.2. Vì sao regex blacklist không đủ?

Giả sử regex tìm `password=...` sẽ bỏ sót `passwd`, `pwd`, field JSON lồng nhau, URL-encoding, base64, multipart hoặc secret không có dấu phân tách quen thuộc. Regex có thể là **lớp bảo vệ bổ sung**, không thay cho thiết kế không log raw.

### 12.3. Không có fallback ghi raw khi parse lỗi

Một trong những anti-pattern nguy hiểm nhất:

~~~java
try {
    return parseAndMask(json);
} catch (Exception ex) {
    log.warn("Cannot parse, raw={}", json); // Không an toàn
    return json;
}
~~~

Thay bằng:

~~~java
try {
    return approvedProjection(json);
} catch (Exception ex) {
    return "[UNAVAILABLE_SANITIZED_VIEW]";
}
~~~

Không log trực tiếp `ex.getMessage()` nếu thư viện parser có thể nhúng fragment payload trong lỗi; dùng exception **class/code được chuẩn hóa**, trace ở nơi đã lọc và cần thiết.

## 13. Ví dụ JSON payload: chỉ trích xuất field được duyệt

Giả sử message inbound có JSON gồm `eventType`, `schemaVersion`, `customerEmail`, `paymentToken` và `items`. Chỉ cần biết loại sự kiện và phiên bản schema để chẩn đoán converter.

~~~json
{
  "eventType": "ORDER_RECEIVED",
  "schemaVersion": "v2",
  "customerEmail": "customer@example.invalid",
  "paymentToken": "EXAMPLE_ONLY_NOT_A_REAL_TOKEN",
  "items": [{"sku": "ABC", "quantity": 1}]
}
~~~

**Không** đem JSON trên vào log production. Ví dụ dữ liệu giả chỉ để minh họa trường nào cần bỏ. Có thể tạo projection theo allowlist bằng Jackson:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Set;

public final class SafeJsonView {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final Set<String> EVENT_TYPES =
            Set.of("ORDER_RECEIVED", "ORDER_CANCELLED");
    private static final Set<String> SCHEMA_VERSIONS =
            Set.of("v1", "v2");

    private SafeJsonView() {}

    public static String eventType(String json) {
        try {
            JsonNode root = MAPPER.readTree(json);
            String value = root.path("eventType").asText("");
            return EVENT_TYPES.contains(value) ? value : "OTHER";
        } catch (Exception ignored) {
            return "UNKNOWN";
        }
    }

    public static String schemaVersion(String json) {
        try {
            JsonNode root = MAPPER.readTree(json);
            String value = root.path("schemaVersion").asText("");
            return SCHEMA_VERSIONS.contains(value) ? value : "OTHER";
        } catch (Exception ignored) {
            return "UNKNOWN";
        }
    }
}
~~~

### 13.1. Điều cần cải thiện khi dùng thực tế

- Parsing hai lần như ví dụ là **đơn giản nhưng chưa tối ưu**; production có thể parse một lần tại bước validation đã có rồi lấy các field cho phép.
- Không đọc JSON body khổng lồ **chỉ để log**; cần giới hạn kích thước đầu vào, timeout và bảo vệ tài nguyên tại ingress.
- Tránh field có text tùy ý: `eventType` và `schemaVersion` được kiểm tra bằng enum set.
- Đừng chuyển payload nhạy cảm sang JSON chỉ để “mask trước khi log” nếu không có nhu cầu thật.
- Nếu schema mới chưa được nhận diện, log `OTHER` hoặc mã lỗi, không ghi raw để phân tích thủ công.

## 14. Giới hạn kích thước, sampling và rate limiting

Ngay cả log chỉ có metadata cũng có thể quá nhiều ở luồng Kafka hoặc HTTP throughput cao.

### 14.1. Sampling có chủ đích

| Cách sampling | Phù hợp | Rủi ro |
|---|---|---|
| **Tỷ lệ theo flow** | Quan sát tổng quan trong production | Có thể không bắt được lỗi hiếm |
| **Deterministic theo opaque ID** | Theo dõi nhất quán một nhóm message | Phải tránh lộ/hash PII và tính sai phân bố |
| **Error-biased sampling** | Tăng quan sát khi có error code | Có thể tăng log đột ngột lúc outage |
| **Time-bounded debug** | Điều tra một incident/flow hẹp | Quên tắt gây chi phí/lộ dữ liệu |
| **Per-component throttling** | Bảo vệ log collector khi message burst | Làm mất một phần sự kiện; cần counter dropped |

Sampling **không làm một field nhạy cảm trở nên an toàn**. Mọi mẫu vẫn phải qua allowlist/sanitizer. Không dùng correlation ID từ bên ngoài làm seed khi chưa xác minh/trung hòa thông tin.

### 14.2. Giới hạn kích thước log

Nên giới hạn:

- Độ dài mọi giá trị string được cho phép.
- Số lượng thuộc tính hoặc phần tử được xuất.
- Size bucket thay cho size chi tiết khi phù hợp.
- Tổng kích thước event được gửi tới collector.
- Tổng volume theo flow và tỷ lệ sampling có ngưỡng.

Nếu vượt giới hạn, ghi `TRUNCATED` hoặc `OMITTED`, **không** tiếp tục log phần còn lại ở một appender khác.

## 15. Adapter File: không log tên file và nội dung vô tội vạ

### 15.1. File inbound

Một file có thể mang dữ liệu hóa đơn, danh sách khách hàng, thông tin nhân sự hoặc tài liệu y tế. Ngoài payload, đường dẫn file thường chứa **customer name, tenant, project hoặc dữ liệu bí mật trong tên**.

Nên log:

| Field | Cách xử lý |
|---|---|
| Flow ID | Giá trị cố định, chẳng hạn `invoice-file-import` |
| Source type | `file` |
| Payload kind | `file`, `bytes` hoặc `text` |
| Size | Bucket như `10kb-100kb` |
| Checkpoint | `discovered`, `accepted`, `parsed`, `confirmed` |
| File name/path | Mặc định không log; dùng opaque file reference |
| File content | Không log raw |
| Parse exception | Mã lỗi như `INVALID_CSV_SCHEMA`, không in dòng lỗi có PII |

### 15.2. File outbound

Khi ghi file, một log “file sent” trước khi rename/flush/atomic handoff (nếu được thiết kế) có thể gây hiểu lầm. Phân biệt các bước `write_started`, `write_completed`, `handoff_confirmed` bằng metadata an toàn. Đừng lưu nội dung file trong log khi cần xác minh tính toàn vẹn; dùng cơ chế checksum/evidence được chủ hệ thống chấp thuận.

### 15.3. InputStream và resource lifecycle

Nếu payload là `InputStream` hoặc resource lazy, đọc vài KB để log có thể **tiêu thụ stream**, làm business handler không đọc được nữa hoặc tăng I/O đáng kể. Không đọc payload để preview chỉ vì debug; dựa trên metadata hoặc buffer có giới hạn đã được thiết kế cho nghiệp vụ.

## 16. SFTP: remote path, session và credential

SFTP inbound/outbound adapter thường có remote filename/path, session information, lỗi xác thực và thời gian truyền dữ liệu.

**Không ghi:**

- Username/password, private key, passphrase, credential URI.
- Remote path đầy đủ nếu chứa tên khách hàng, tài khoản hoặc cấu trúc nội bộ nhạy cảm.
- Nội dung tài liệu được truyền, đặc biệt log lỗi parse.
- SSH stack diagnostics chứa secret/config nhạy cảm chưa được lọc.

**Nên ghi:**

| Sự kiện | Metadata thích hợp |
|---|---|
| Poll SFTP | `source=sftp`, flow, poll outcome, số file eligible |
| Tạo session | Dependency alias cố định, `CONNECTED/FAILED`, duration |
| Download | Opaque file ref, size bucket, transfer outcome |
| Upload | Target alias, bytes bucket, confirmation stage |
| Lỗi | `AUTH_FAILURE`, `NETWORK_TIMEOUT`, `REMOTE_PERMISSION` |
| Retry | Attempt count, bounded reason code, backoff category |

### 16.1. Không đưa hostname/username vào metric tag hay log công khai

Nếu cần xác định server, sử dụng alias đã được phê duyệt như `partner-sftp-a`; ánh xạ alias → host được giữ trong hệ cấu hình có quyền. Tránh in cả connection string hoặc secret manager path khi không cần thiết.

### 16.2. Phân biệt lỗi trước và sau khi tạo Message

Nếu không kết nối được SFTP, chưa có message và `MessageHistory` sẽ không giúp giải thích file nào thiếu. Quan sát qua **poll metrics, session events, error code**; không bật dump toàn bộ file sau khi kết nối khôi phục.

## 17. HTTP gateway: request/response body và headers nguy hiểm

### 17.1. HTTP inbound gateway

Request có thể chứa:

- Authorization bearer token, Cookie, API key, session ID.
- JSON body với email, thông tin thanh toán, địa chỉ.
- URL path/query có ID hoặc secret.
- Multipart file, form data hoặc dữ liệu do client bất kỳ gửi.

Nên log **route template**, HTTP method, status class, latency, request size bucket và opaque request ID đáng tin cậy; không log raw URI/query/body hoặc headers tùy ý.

### 17.2. HTTP outbound gateway

HTTP client error thường kèm response body của đối tác. Body lỗi có thể chứa dữ liệu nhạy cảm, thông điệp trả về của upstream, request echo hoặc token. Đừng viết:

~~~java
log.error("HTTP failed, responseBody={}", responseBody);
log.error("Request headers={}", requestHeaders);
log.error("Remote URL={}", fullUrlWithQuery);
~~~

Thay bằng:

~~~java
log.warn(
    "event=REMOTE_CALL_FAILED target={} status_class={} "
    + "error_class={} correlation_ref={}",
    "billing-api",
    "5xx",
    "REMOTE_SERVER_ERROR",
    safeCorrelationRef
);
~~~

Ở đây `safeCorrelationRef` chỉ được log sau khi đã **xác minh/chuẩn hóa**, không lấy thẳng giá trị tùy ý từ request. Khi có status 202 hoặc timeout, không dùng log “sent” như bằng chứng remote business commit.

### 17.3. HTTP wire logging

Các HTTP client/gateway có thể bật wire logging hoặc interceptor ghi toàn bộ headers/body. Cần kiểm tra **đồng thời** logging của HTTP server, WebClient/RestClient, proxy/API gateway và thư viện HTTP đang dùng. Việc tắt một logger ứng dụng chưa bảo đảm không có body ở proxy hoặc tracing exporter.

## 18. JMS adapter: headers, redelivery và DLQ

JMS message có thể chứa text, bytes, map/object payload và application properties; adapter/converter có thể biến chúng thành Spring Message.

### 18.1. Log theo transport semantics

| Sự kiện | Metadata an toàn có ích |
|---|---|
| Message received | Broker alias, destination alias, correlation reference nếu an toàn |
| Processing attempt | Flow, handler, attempt index, result class |
| Redelivery | Redelivered flag/count nếu được hệ thống cung cấp |
| Transaction/ack | Attempted, committed hoặc rolled back theo kết quả thực |
| DLQ | Reason category, DLQ alias, opaque event reference |

**Không** log toàn bộ `TextMessage`, `BytesMessage` hay JMS properties chỉ vì consumer lỗi; properties có thể chứa session/token hoặc identifier nhạy cảm.

### 18.2. Retry và log volume

Một poison message có thể redeliver hàng nghìn lần, tạo hàng nghìn bản log với cùng payload nếu logging không kiểm soát. Dùng bounded retry, rate limit, DLQ và counter terminal failures; log theo **event category** thay vì in mỗi lần body lỗi.

## 19. AMQP/RabbitMQ: không nhầm broker metadata với payload

AMQP message gồm body và headers/properties, có thể có routing key, exchange và delivery tag. Khi ghi log:

- Dùng **exchange/queue alias** cố định do tổ chức quản lý.
- Ghi ack/nack/requeue outcome, retry count, DLQ event và connection status.
- Không log raw message body khi deserialization thất bại.
- Không coi delivery tag hoặc routing key động là correlation ID nghiệp vụ an toàn.
- Đánh dấu rõ producer confirm, consumer ACK và business completion là những mốc khác nhau.

### 19.1. Lỗi converter

Khi JSON/Java conversion lỗi, exception có thể chứa fragment dữ liệu. Thay vì in raw `failedMessage` hoặc bytes, ghi:

~~~text
event=AMQP_CONVERSION_FAILED
target=orders-queue
content_type=application/json
error_class=INVALID_MESSAGE_SCHEMA
payload_kind=binary
attempt=2
~~~

Các giá trị trên là minh họa đã chuẩn hóa. Không xuất raw payload vào DLQ header hoặc error log trừ khi chính sách lưu trữ riêng cho phép; DLQ bản thân nó là một **kho dữ liệu nhạy cảm** cần phân quyền và retention.

## 20. Kafka: record key, headers và serializer logs

Kafka record thường có topic, partition, offset, key, value và headers. Trong nhiều hệ thống, **record key có thể chính là customer ID hoặc email**, không nên mặc định log.

| Thành phần | Khuyến nghị |
|---|---|
| Topic | Dùng tên hoặc alias cố định nếu policy cho phép |
| Partition/offset | Metadata vận hành, cân nhắc scope/retention |
| Record key | Không in raw trừ khi đã phân loại an toàn |
| Record value | Không dump JSON/Avro/Protobuf/binary |
| Headers | Allowlist; loại token/baggage nhạy cảm |
| Consumer group | Tên cố định được phép; không xuất bí mật cấu hình |
| Serialization error | Mã lỗi/serializer class, schema version đã duyệt |
| Retries/DLQ | Attempts, reason class, event ref và outcome |

### 20.1. Kafka deserialization failure

Một lỗi schema/serializer có thể xảy ra **trước khi tạo Spring Message hợp lệ**. Khi đó không có payload đã parse để log an toàn; metadata Kafka, exception class đã chuẩn hóa và schema ID là đủ để điều tra bước đầu. Đừng bật serializer DEBUG để dump bytes của tất cả records.

### 20.2. Producer và consumer có thể là hai tiến trình khác

Không đưa full Spring Message header/history vào Kafka record để thuận tiện debug; chỉ propagate **correlation/trace context được cho phép** và dữ liệu hợp đồng. Log của producer và consumer nên được nối bằng tham chiếu an toàn, không dùng raw key/value làm ID.

### 20.3. Exactly-once không được chứng minh qua log

Một log “Kafka send success” không chứng minh consumer đã commit database hoặc event không bị redeliver. Cần producer acknowledgment, consumer offset/transaction semantics, idempotency/reconciliation và event nghiệp vụ riêng khi yêu cầu.

## 21. JDBC/database adapter: SQL parameters và dữ liệu hàng

Database inbound/outbound adapter và gateway thường được debug bằng SQL logs, nhưng một câu lệnh có bind parameters có thể tiết lộ:

- Email, số tài khoản, thông tin thanh toán.
- Nội dung hồ sơ, tên người, địa chỉ.
- Token/secret lưu sai chỗ trong bảng cấu hình.
- Query có khóa khách hàng hoặc dữ liệu nhạy cảm ở điều kiện WHERE.

### 21.1. Cách ghi an toàn

| Cần đo | Nên ghi |
|---|---|
| Query nào chạy? | **Query ID cố định** hoặc repository method |
| Tốn bao lâu? | Duration, timeout/lock wait |
| Kết quả thế nào? | Rows selected/updated/committed, transaction outcome |
| Đang vướng gì? | SQL state/error class đã phân loại |
| Có row nào bị lỗi? | Opaque record reference ở log được bảo vệ |
| SQL parameter values? | Mặc định **không ghi** |
| Toàn bộ ResultSet/Entity? | Không ghi |

### 21.2. Đừng bật SQL bind logging toàn cục để tìm một lỗi

ORM/JDBC driver hoặc proxy có thể ghi bind values ở một số log level. Cần review logger configuration ngoài Spring Integration, đặc biệt nếu đội bật SQL TRACE theo một sự cố. Thay bằng query ID, thời gian, số row và mã lỗi; nếu cần dữ liệu thật, tra cứu có quyền trong database qua quy trình kiểm toán.

### 21.3. Phân biệt transaction outcome

Một log từ handler ghi “DB update requested” không chứng minh transaction đã commit. Kết quả cần đi cùng actual JDBC update/transaction event hoặc bằng chứng nghiệp vụ ở target. Không log raw row chỉ để chứng minh update.

## 22. Logging ở error channel và ErrorMessage

Trong Spring Integration, một số lỗi có thể được đưa qua `errorChannel` dưới dạng `ErrorMessage`, tùy endpoint, giao thức, cấu hình async/transaction và error handler.

**Nguy cơ đặc biệt:** error message có thể chứa:

- Exception message/stack trace với đoạn payload hoặc URL.
- Original failed message và mọi headers.
- Failed delivery object có reference tới raw bytes.
- Broker record body, HTTP response body, file path.

### 22.1. Checklist một error logger an toàn

1. Chỉ ghi **exception class đã chuẩn hóa** và `reason_code` từ taxonomy hữu hạn.
2. Ghi flow, endpoint, transport type và attempt.
3. Nếu có original message, chỉ lấy **opaque ID và safe metadata**, không stringify nó.
4. Không gọi `Throwable.getMessage()` nếu nội dung chưa được kiểm duyệt.
5. Stack trace chi tiết chỉ đưa vào sink được kiểm soát khi chính sách cho phép; rà thư viện nào nhúng payload vào trace.
6. Tách lỗi transient, permanent và unknown outcome; không log mỗi retry như terminal failure.
7. Giữ DLQ và error queue theo cùng chính sách dữ liệu như nguồn.

### 22.2. Ví dụ safe error event

~~~json
{
  "event": "INTEGRATION_PROCESSING_FAILED",
  "flow": "jms-invoice-import",
  "component": "validateInvoiceSchema",
  "error_class": "INVALID_SCHEMA",
  "attempt": 1,
  "terminal": false,
  "payload_kind": "json",
  "message_ref": "opaque-message-reference",
  "exception_type": "MessageConversionException"
}
~~~

Đây là event do ứng dụng định nghĩa; **`exception_type` cũng cần normalize/allowlist** nếu nguồn exception có thể mang tên class gây rò rỉ thông tin không phù hợp.

## 23. Splitter, aggregator, retry: tránh nhân bản dữ liệu nhạy cảm trong log

### 23.1. Splitter fan-out

Một batch 10.000 records có thể tạo 10.000 message con. Nếu bật log full payload ở mỗi handler, cùng một loại dữ liệu có thể bị ghi nhiều lần, làm tăng chi phí và nguy cơ lộ.

**Nên ghi:** batch size, accepted/rejected count, category lỗi hữu hạn, correlation reference đã xác minh và tổng completion.

### 23.2. Aggregator

Aggregator gom nhiều message; payload kết quả có thể chứa **nhiều dữ liệu nhạy cảm hơn** từng item riêng. Không in toàn bộ aggregate result để kiểm tra group completion. Thay bằng group size, completion reason, elapsed duration và outcome.

### 23.3. Retry

Retry nhiều lần khiến một credential/body có thể bị ghi lại trên mọi attempt nếu logging thiếu kiểm soát. Cần rate limit, backoff, lỗi được phân loại và counter; sample log **chỉ sau sanitizer**.

### 23.4. PublishSubscribeChannel và ExecutorChannel

Một message có thể được xử lý ở nhiều nhánh hoặc nhiều thread. Tránh vừa log raw ở tap channel vừa log raw ở business handler; theo dõi per-branch outcome qua metadata và correlation. Nếu sử dụng executor, xác minh **MDC/tracing context propagation**, không sao chép tùy ý toàn bộ headers sang log context.

## 24. Correlation ID, message ID và tracing context

### 24.1. Mỗi ID có mục đích riêng

| Tham chiếu | Ý nghĩa | Cách ghi log |
|---|---|---|
| Spring Message ID | Instance message cục bộ, có thể đổi khi tạo message mới | Ghi khi policy cho phép, không coi là cross-service ID |
| Correlation ID | Nối các message/request cùng quy trình | Chỉ dùng opaque ID đã xác minh |
| Trace ID / Span ID | Liên kết các operation được instrument | Dùng cơ chế tracing propagation được hỗ trợ |
| Business ID | Mã đơn hàng/hợp đồng/khách hàng | Có thể nhạy cảm; chuyển thành opaque reference nếu cần |
| Broker record identity | Kafka topic/partition/offset, JMSMessageID | Dùng trong phạm vi vận hành và policy |

### 24.2. Không lấy raw user input đưa vào MDC

MDC và tracing baggage thường được tự động đưa vào mọi log cùng thread/context. Nếu một web client gửi `X-Correlation-ID` với thông tin nhạy cảm hoặc ký tự đặc biệt, việc copy thẳng vào MDC sẽ phát tán sang nhiều event. Cần **validate pattern, giới hạn độ dài, thay thế/khởi tạo ID nội bộ** và điều chỉnh baggage allowlist.

### 24.3. Context qua thread và broker

`ExecutorChannel` thay thread; queue và consumer cũng tạo ranh giới xử lý. MDC là **thread-local logging context**, không tương đương Spring Message headers. Dùng thư viện context propagation/tracing phù hợp phiên bản để giữ trace khi cần, và đảm bảo context được **clear/reset** sau khi xử lý để không rò correlation sang tác vụ khác.

## 25. MessageHistory và log payload: hai mục tiêu khác nhau

Spring Integration có `MessageHistory` và có thể bật bằng `@EnableMessageHistory` theo khả năng phiên bản. History ghi metadata những component đi qua khi được bật và header được bảo toàn.

**History không đòi phải in payload**, cũng không có nghĩa history nên được đưa ra ngoài broker hoặc HTTP response.

| Câu hỏi | Cách quan sát ưu tiên |
|---|---|
| Message đi qua endpoint nào? | MessageHistory cục bộ, endpoint IDs, trace/log checkpoint |
| Handler mất bao lâu? | Micrometer Timer/Observation |
| Đã gửi đi broker chưa? | Producer metrics/confirm callback |
| Vì sao filter loại message? | Reason code có cấu trúc, discard counter |
| File nào chưa xử lý? | Inventory có quyền + opaque file reference |
| Payload cụ thể cần xem? | Truy hệ thống dữ liệu có phân quyền, không dump vào log |

### 25.1. Không sử dụng history như dữ liệu tin cậy

Header history truyền từ nguồn ngoài có thể bị giả mạo hoặc mất ở serializer/mapper. Không dùng nó để chấp nhận payment, thực thi quyền hay quyết định đã validate thành công. Sự an toàn của payload logging và authorization phải dựa vào **policy, code kiểm chứng và dữ liệu nguồn đáng tin**.

## 26. Metrics/Observation thay thế phần lớn nhu cầu log body

Nhiều câu hỏi vận hành có thể giải bằng metrics:

| Vấn đề | Metric phù hợp |
|---|---|
| File inbound có dữ liệu không? | Poll count, empty count, eligible files, oldest file age |
| SFTP mất kết nối? | Session/transfer errors, retry, latency |
| HTTP outbound chậm? | Request duration p95/p99, status class, timeout |
| JMS/AMQP redelivery? | Attempt/redelivery, requeue, DLQ |
| Kafka consumer tụt lại? | Lag, offset commit, DLQ, handler latency |
| JDBC update chậm? | Query/transaction duration, pool wait, lock errors |
| QueueChannel nghẽn? | Depth, oldest age, enqueue/dequeue rate |
| Filter reject nhiều? | Accepted/rejected count theo reason class |

Không cần bật log toàn bộ payload khi có thể xác định nguyên nhân bằng **counters, histograms, queue age và traces**. Metrics cũng cần bảo vệ: không dùng email, file name, record key, correlation ID hay full URI làm tag vì **cardinality cao và nguy cơ lộ dữ liệu**.

## 27. Cấu hình logger và appender: lớp bảo vệ bổ sung

Một cấu hình logging có thể giới hạn mức log theo package/flow, nhưng **không thay thế allowlist projection**.

Ví dụ cấu hình `application.yml`:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.integration: INFO
    org.springframework.messaging: INFO
    com.example.integration: INFO
    com.example.integration.debug: OFF
~~~

Tên package là ví dụ; các logger và mức log thực tế cần xác định trong ứng dụng. `OFF` cho một logger debug chỉ chặn logger đó, **không đảm bảo các framework khác không log body**.

### 27.1. Appender và collector cũng cần kiểm soát

1. Hạn chế quyền đọc stdout, container logs và log aggregation.
2. Bảo vệ transport tới collector, mã hóa storage theo chính sách.
3. Tách audit và diagnostic log khi có mục đích/retention khác nhau.
4. Có log rotation, size limit, sampling và retention.
5. Bảo vệ debug console, IDE remote, support bundle, crash dump và profiling artifacts.
6. Rà khả năng log forwarding tới dịch vụ bên thứ ba.
7. Có cơ chế điều tra/xóa/cách ly bản ghi lộ dữ liệu theo quy trình tổ chức.

### 27.2. Chú ý log injection

Không nối thẳng chuỗi không tin cậy vào log. Dùng structured logging/parameterized logging và **sanitize field values**, hạn chế CR/LF, độ dài, control characters và field name. Parameterized logger giúp tránh tạo chuỗi không cần thiết nhưng **không tự che PII** hoặc chặn ký tự xuống dòng.

## 28. Debug logging có thời hạn và kiểm soát bằng feature flag

Một giải pháp vận hành tốt cho phép quan sát một flow trong một khoảng ngắn, **không cho phép bật raw body**.

Ví dụ policy cấu hình logic:

~~~yaml
integration:
  diagnostics:
    enabled: false
    flowAllowlist: []
    mode: METADATA_ONLY
    samplingRate: 0.01
    maxEventBytes: 2048
    expiresAt: null
    incidentRef: null
~~~

Đây là **schema giả lập do ứng dụng tự định nghĩa**, không phải property mặc định của Spring Integration. Muốn dùng phải tự xây cơ chế đánh giá config và event projection.

### 28.1. Bất biến nên cưỡng chế trong code

- `mode` không có lựa chọn xuất raw secrets.
- Flow chỉ được bật nếu nằm trong allowlist và có approval hợp lệ.
- `expiresAt` được thực thi bằng logic; đến hạn phải tắt dù không có ai nhớ.
- Sampling/byte limit không vượt ngưỡng theo policy.
- Feature flag không thay đổi các quy tắc redaction.
- Log activation/deactivation có actor, thời điểm, ticket và phạm vi.
- Mọi thay đổi cấu hình được review và có rollback.

### 28.2. Không phụ thuộc duy nhất vào thời hạn config

Nếu service không reload config, flag hết hạn mà vẫn hoạt động có thể gây rủi ro. Cần cơ chế kiểm tra `expiresAt` tại thời điểm phát log hoặc controlled reconciliation, giám sát số event debug sau expiry và alert khi có sai lệch.

## 29. Kiểm thử tự động chống rò rỉ

### 29.1. Bộ fixture cần có

Tạo **dữ liệu giả** chứa nhiều hình thức dễ lộ:

- JSON field `password`, `accessToken`, nested `credentials.secret`.
- Email/phone/card-like strings giả, tên file có thông tin cá nhân.
- HTTP `Authorization` và `Cookie` giả.
- Kafka key với string giả như email, custom header chứa token.
- JMS/AMQP properties có key name không chuẩn `x-auth-secret`.
- Error message chứa một đoạn input giả hoặc URL query có token giả.
- Binary payload với bytes marker riêng và một InputStream.
- Payload quá dài, Unicode, newline và ký tự control.

**Không dùng credentials thật** hoặc dữ liệu production để kiểm thử khả năng log an toàn.

### 29.2. Tiêu chí test

1. Safe projection chỉ gồm field đã duyệt.
2. Fixture secret/PII **không xuất hiện** trong log output.
3. Khi parse lỗi, không rơi về raw fallback.
4. Header tùy biến không tự được log.
5. Message `toString()` không được gọi để dựng event.
6. Payload binary/stream không bị đọc để tạo preview.
7. Flow/filter/retry vẫn hoạt động khi diagnostics disabled.
8. Việc bật/tắt debugging tuân thủ allowlist, TTL và sampling.
9. Khi log sink lỗi, behavior theo chính sách đã định và có metric dropped logs.
10. Stress test xác minh giới hạn event size, throughput và queue memory.

### 29.3. Ví dụ JUnit đơn giản

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class SafeJsonViewTest {
    @Test
    void extractsOnlyApprovedClassification() {
        String input = """
            {
              "eventType":"ORDER_RECEIVED",
              "schemaVersion":"v2",
              "customerEmail":"hidden@example.invalid",
              "paymentToken":"FAKE_SECRET_MARKER"
            }
            """;

        String safeView = SafeJsonView.eventType(input)
                + ":" + SafeJsonView.schemaVersion(input);

        assertTrue(safeView.contains("ORDER_RECEIVED"));
        assertTrue(safeView.contains("v2"));
        assertFalse(safeView.contains("FAKE_SECRET_MARKER"));
        assertFalse(safeView.contains("hidden@example.invalid"));
    }
}
~~~

Đây là test của **projection function**, chưa kiểm chứng các appender/framework logger khác. Để phát hiện log leak thực tế, integration test nên capture output của logger được dùng, proxy/HTTP client, error channel và serializer với fixtures giả.

## 30. Kiểm thử integration flow có WireTap

### 30.1. Cần xác minh hai hướng

Một WireTap được xem là triển khai đúng khi:

- Nhánh business vẫn nhận và xử lý message như trước.
- Nhánh logging tạo event **chỉ chứa field hợp lệ**, không thay payload hoặc header business.
- Lỗi logging không làm message business thất bại ngoài chủ đích và chính sách.
- Không sinh bản ghi lặp vô hạn khi có retry hoặc circular channel.
- Tên flow/endpoint và kết quả đúng với checkpoint quan sát.
- Log throughput và latency vẫn nằm trong ngưỡng khi bật/tắt diagnostics.

### 30.2. Ma trận test

| Test case | Mô phỏng | Kỳ vọng |
|---|---|---|
| Happy path | JSON giả hợp lệ | Flow thành công; log metadata an toàn |
| Invalid schema | JSON thiếu field | Reason code, không raw input |
| Nested secret | Field secret nhiều tầng | Không lộ bất kỳ secret marker |
| Unknown header | `x-custom-token` | Không được log |
| Stream payload | `InputStream` | Không bị tiêu thụ để tạo preview |
| File payload | Path có tên khách hàng giả | Không log raw path |
| HTTP error | Response body có token giả | Log status/error class, không body |
| Broker retry | 10 attempts cùng event | Rate/sampling đúng; không log body 10 lần |
| Async channel | ExecutorChannel | Không trộn correlation context |
| Logger failure | Appender throws/queue full | Theo error policy, có dropped-log metric |
| Debug TTL | Hết `expiresAt` | Không tiếp tục tăng logging detail |
| Multiple subscribers | PublishSubscribeChannel | Branch metrics đúng, không nhân bản raw log |

## 31. Runbook LOG-01 — Khi cần điều tra một message lỗi

**Tình huống:** khách hàng báo một message không tới hệ thống đích, nhưng đội vận hành không muốn bật log raw payload.

1. **Xác định flow và business event** bằng opaque ID/ticket có quyền.
2. Kiểm tra **metrics** của inbound adapter, QueueChannel, handler và outbound; xác định mốc cuối đã xác nhận.
3. Tra **structured logs** theo correlation/trace, status, error code và endpoint.
4. Nếu bật MessageHistory, xem component path cục bộ; không tin history như bằng chứng remote commit.
5. Tại adapter, xem protocol-specific outcome: SFTP transfer result, HTTP status, Kafka producer callback, JMS/AMQP ack/DLQ, JDBC transaction.
6. Nếu chưa đủ, đề nghị diagnostics có ticket/owner/TTL và **chỉ thêm field allowlisted**; không log body “tạm”.
7. Với timeout có kết quả chưa rõ, **readback/reconcile** tại target trước khi retry để tránh duplicate.
8. Ghi kết luận, evidence và biện pháp phòng ngừa; tắt diagnostics và xác minh log volume trở về baseline.

### 31.1. Câu hỏi cần trả lời ở mỗi checkpoint

| Checkpoint | Câu hỏi | Log an toàn gợi ý |
|---|---|---|
| Inbound | Message đã được nhận chưa? | Event type, source alias, accepted/invalid |
| Filter | Bị loại vì sao? | Bounded reason code |
| Transformer | Schema/serialization nào lỗi? | Schema version, converter ID, error class |
| Router | Nhánh nào được chọn? | Destination category cố định |
| Queue | Đang chờ bao lâu? | Queue age, depth metrics |
| Outbound | Target xác nhận gì? | Attempt, transport status, outcome type |
| DLQ | Có dữ liệu nào cần replay? | Opaque event ref, reason, attempt |

## 32. Runbook LOG-02 — Phát hiện dữ liệu nhạy cảm trong log

**Trigger:** secret scanner, SOC, support hoặc owner phát hiện password/token/PII trong log ứng dụng, collector, tracing hoặc support bundle.

1. **Tạo security incident**; không sao chép giá trị nhạy cảm sang ticket mới hoặc chat. Chỉ ghi log event ID, vị trí lưu và thời gian.
2. Xác định **loại dữ liệu**, thời điểm bắt đầu lộ, flow, logger, collector, ai có quyền đọc và những bản sao liên quan.
3. Theo quyền/phân loại rủi ro, **ngừng nguồn phát tán**, giảm quyền truy cập sink hoặc tắt chế độ diagnostics đang gây lộ mà không phá hủy bằng chứng cần điều tra.
4. Với credential có khả năng sử dụng, **revoke/rotate tại issuer** và kiểm tra session/token liên quan; xóa log không vô hiệu hóa secret đã bị lộ.
5. Bảo toàn chứng cứ gốc trong kho điều tra có ACL và retention theo quy trình; không xóa trước khi SOC/Legal đánh giá.
6. Xác định việc log có đi tới downstream SIEM, search index, alert notification, file backup, external vendor hoặc support exports không.
7. Phối hợp privacy/compliance đánh giá nghĩa vụ xử lý nếu có dữ liệu cá nhân.
8. Sửa root cause: safe projection, header allowlist, debug logger scope, appender, parser error fallback, serializer/client.
9. Kiểm thử không tái lộ bằng **dữ liệu giả**, xác minh deployment và cập nhật guardrails.
10. Theo dõi sau khắc phục, ghi owner/evidence và đóng incident theo chính sách.

### 32.1. Không coi “redact trong UI” là đủ

Một nền tảng logging có thể che một chuỗi ở giao diện nhưng vẫn giữ raw event trong storage hoặc export API. Phải kiểm tra **toàn đường đi và bản sao dữ liệu**, không chỉ hình thức hiển thị.

### 32.2. Không xóa hoặc rewrite log tùy tiện

Log có thể là bằng chứng điều tra hoặc chịu legal hold. Việc quarantine, redaction, purge hoặc điều chỉnh retention phải theo quy trình đã được tổ chức ủy quyền; tránh làm mất tính toàn vẹn kiểm toán.

## 33. Audit và event logging không phải một

**Diagnostic log** phục vụ tìm lỗi, có thể sampled và có retention ngắn. **Audit event** phục vụ xác nhận ai làm gì, theo quyền nào, lúc nào, trên tài nguyên nào và kết quả gì; thường cần integrity, retention và truy vết độc lập.

| Tiêu chí | Diagnostic logging | Audit logging |
|---|---|---|
| Mục đích | Debug/quan sát performance và lỗi | Truy trách nhiệm, kiểm soát, tuân thủ |
| Payload | Không raw theo mặc định | Chỉ lưu thông tin nghiệp vụ được phê duyệt |
| Sampling | Có thể có | Không thể tùy tiện bỏ sự kiện bắt buộc |
| Retention | Theo nhu cầu vận hành | Theo nghĩa vụ và chính sách |
| Bảo toàn | Thường không bất biến | Có thể yêu cầu chống chỉnh sửa, audit trail |
| Truy cập | SRE/Dev theo phân quyền | Người kiểm toán/Security/owner có thẩm quyền |

Một WireTap ghi log metadata **không tự trở thành audit trail** đáng tin. Nếu giao dịch hoặc lệnh cấp quyền cần audit bắt buộc, thiết kế event store theo hợp đồng và transaction/idempotency; đừng dựa vào appender bất đồng bộ có thể drop logs.

## 34. Anti-pattern và cách cải thiện

| Anti-pattern | Hậu quả | Thay thế |
|---|---|---|
| `log.info("{}", message)` | In payload và headers tùy type | Safe projection với field allowlist |
| Bật TRACE toàn `org.springframework.*` | Rủi ro lộ data, log storm | Scope nhỏ, TTL, review logger cụ thể |
| Regex che password rồi log raw JSON | Bỏ sót alias/nested/encoded secrets | Omit/allowlist đúng schema |
| Khi parse fail thì log raw request | Lộ payload đúng lúc lỗi | Mã lỗi và fallback không dữ liệu |
| Log tên file SFTP đầy đủ | Lộ path/username/khách hàng | Opaque file ref/alias |
| Log HTTP headers/bodies | Lộ Authorization/Cookie/PII | Route template, status, duration |
| Log Kafka key/value | Lộ domain ID và dữ liệu | Topic alias, partition/offset, outcome |
| Log JDBC bind values | Lộ row và dữ liệu khách hàng | Query ID, row count, SQL state |
| Lấy `correlationId` raw làm MDC | Log injection/PII phát tán | Validate/normalize/issue opaque ID |
| Dump ErrorMessage/originalMessage | In raw failed payload/headers | Exception class, reason, safe ref |
| Sampling trước sanitizer | Mẫu còn raw dữ liệu | Sanitize mọi event trước khi emit |
| Dùng debug logs làm audit | Không bảo đảm đầy đủ/bất biến | Audit store có policy riêng |
| Quên tắt diagnostics | Thu thập dài hạn không cần thiết | TTL cưỡng chế và monitoring |
| Logging branch không bounded | Heap tăng, làm chậm main flow | Queue/capacity/drop policy và metrics |
| Log raw payload khi broker retry | Lặp dữ liệu nhạy cảm hàng nghìn lần | Attempts/terminal outcome counters |

## 35. Tình huống thực hành có hướng giải

### Tình huống A — Inbound HTTP ghi cả bearer token

Một developer bật logging toàn request headers để xem lý do HTTP 401; log collector bắt đầu nhận `Authorization`.

**Hướng xử lý:** dừng nguồn phát tán, kiểm soát bản ghi đã lộ, đánh giá revoke token qua SOC khi cần; thay bằng status class, request route template, auth failure category. Thêm test bảo đảm header Authorization không xuất hiện trong log hoặc trace.

### Tình huống B — SFTP file lỗi parse, log tên khách hàng

Parser lỗi tên file như `customer-name_contract.pdf`; log hiện full path và stack trace.

**Hướng xử lý:** dùng opaque file reference, source alias, size bucket và `INVALID_DOCUMENT_FORMAT`. Tra file thật qua hệ thống có quyền; không log file name/path hoặc contents vào SIEM chung.

### Tình huống C — Kafka consumer gặp JSON không hợp lệ

Deserializer ném exception có đoạn JSON chứa email và token giả. Logger in `exception.getMessage()`.

**Hướng xử lý:** chuyển sang exception class/error code, schema ID an toàn, topic/partition/offset theo policy, loại raw exception message. Test với fixture có marker secret, kiểm tra serializer logging phía framework.

### Tình huống D — WireTap làm chậm luồng thanh toán

Một WireTap dùng DirectChannel gọi logger và formatter nặng. P99 latency tăng khi bật DEBUG.

**Hướng xử lý:** chỉ tạo safe projection rất nhỏ, đo overhead, cân nhắc executor/queue có giới hạn và dropped-logs metric, áp sampling/TTL; không để debug branch thành điểm nghẽn transaction.

### Tình huống E — InputStream bị đọc hết bởi logger

File inbound mang stream; handler logging đọc 4 KB để preview, khiến downstream nhận stream thiếu dữ liệu.

**Hướng xử lý:** bỏ preview, dùng metadata; nếu nghiệp vụ cần nội dung stream nhiều lần phải thiết kế caching/re-readable resource trong processing flow với kiểm soát bộ nhớ/đĩa, không làm riêng cho log.

### Tình huống F — Logback DEBUG đã tắt mà dữ liệu vẫn lộ

Framework logger INFO còn in `Message.toString()` tại một error handler.

**Hướng xử lý:** không chỉ chỉnh logger level; tìm mọi sink trong flow/error channel, thay bằng safe projection, kiểm thử all paths và rà stack trace/callback/client logs.

### Tình huống G — Correlation ID chứa xuống dòng

HTTP caller gửi `X-Correlation-ID` chứa CR/LF và một chuỗi trông như log event mới.

**Hướng xử lý:** xem inbound correlation là input chưa tin cậy, cấp opaque ID nội bộ hoặc kiểm tra pattern/length, chuẩn hóa trước đưa vào MDC/log, kiểm thử log injection.

### Tình huống H — JMS redelivery làm log volume tăng vọt

Một message chứa PII bị retry 500 lần, mỗi attempt log nguyên body.

**Hướng xử lý:** ngừng raw logging, dùng reason class, retry/terminal counters, bounded backoff và DLQ có phân quyền; đánh giá bản log đã chứa PII theo quy trình. Không dùng số lần handler lỗi làm số business messages thất bại.

### Tình huống I — Database SQL logger hiển thị bind params

Đội vận hành bật SQL TRACE để debug JDBC outbound gateway, SIEM thu được email và số tài khoản.

**Hướng xử lý:** ngừng bind value logging, dùng query ID, SQL state, rows count, timing và transaction result; kiểm soát bản ghi đã phát tán và thêm guardrail logging configuration.

### Tình huống J — Aggregator log toàn batch

Một aggregator tạo danh sách 10.000 hồ sơ và in `payload.toString()`, khiến log pipeline bị nghẽn.

**Hướng xử lý:** log group size, completion reason, duration, count rejected, safe correlation ref; xử lý bulk log backlog và kiểm tra khả năng lộ dữ liệu.

### Tình huống K — Debug flag hết hạn vẫn chưa tắt

Config có `expiresAt` nhưng service chỉ kiểm tra lúc khởi động, debug vẫn chạy sau thời hạn.

**Hướng xử lý:** cưỡng chế TTL khi emit hoặc refresh theo cơ chế an toàn, theo dõi metric diagnostics_active và alert quá hạn, xác minh phục hồi baseline sau incident.

### Tình huống L — Kafka → HTTP không nối được trace

Producer và consumer có logs metadata an toàn nhưng không tìm thấy request liên quan bên HTTP target.

**Hướng xử lý:** thiết kế propagation của trace context/correlation qua header mapper cho phép, bảo vệ baggage, không đưa full payload hoặc Spring MessageHistory sang service khác. Kiểm tra tracing ở executor/consumer.

## 36. Checklist triển khai và vận hành

### 36.1. Trước khi thêm một câu log

- [ ] Đã xác định mục đích và checkpoint? Có metric/trace thay thế được không?
- [ ] Payload/header thuộc loại dữ liệu nào? Có secrets/PII không?
- [ ] Có thể chỉ log event code, size bucket, schema version và opaque ref?
- [ ] Giá trị nào **từ bên ngoài** và cần validate/normalize?
- [ ] Đã dùng allowlist, không dump object/toString?
- [ ] Có nguy cơ raw exception text, URL, SQL params hoặc filename không?
- [ ] Log level và appender có thể được bật tại production không?

### 36.2. Khi thiết kế WireTap/LoggingHandler

- [ ] Nhánh log có handler chuyên tạo safe projection?
- [ ] Business flow vẫn giữ đúng payload và header contract?
- [ ] Có đánh giá sync/async, capacity và lỗi logger?
- [ ] Có giới hạn kích thước, sampling và rate limit?
- [ ] Có kiểm thử filter/router/splitter/aggregator/retry và error channel?
- [ ] Không truyền nguyên history, raw headers hay credentials ra ngoài adapter?
- [ ] Có quy trình bật diagnostics có approval, TTL và hậu kiểm?

### 36.3. Theo từng adapter

- [ ] File: không raw content/path; không tiêu thụ stream để log.
- [ ] SFTP: không secret, username/private key và remote path nhạy cảm.
- [ ] HTTP: không request/response body, Authorization, Cookie, full URI/query.
- [ ] JMS: không TextMessage/raw properties; tách retry/redelivery.
- [ ] AMQP: không body, key headers, queue DLQ phải có ACL/retention.
- [ ] Kafka: không record key/value; có offset/ack/outcome phù hợp.
- [ ] JDBC: không bind parameters/ResultSet; có query ID và transaction status.
- [ ] Error flow: không dump original Message hoặc raw exception body.

### 36.4. Trước khi release

- [ ] Dùng synthetic secret/PII fixtures để chạy leak tests.
- [ ] Review framework log config, clients, serializers, tracing và proxy.
- [ ] Không có raw debug fallback khi parse lỗi.
- [ ] Actuator/log collector có quyền truy cập và retention phù hợp.
- [ ] Đã đo log volume, latency và dropped diagnostics.
- [ ] Có runbook khi phát hiện secret/PII đã lộ qua log.
- [ ] Debug mode trở về baseline sau exercise/incident.

## 37. Tổng kết

**Logging payload có kiểm soát** không có nghĩa che vài field rồi in phần còn lại. Đây là một **hợp đồng quan sát dữ liệu**: mặc định không ghi nội dung nhạy cảm, chọn đúng checkpoint, tạo **safe projection theo allowlist**, kiểm tra nguồn header, giới hạn kích thước/tần suất, bảo vệ log collector và có quy trình vận hành debug tạm thời.

Trong **Spring Integration Adapters**, nguy cơ rò rỉ có thể xuất hiện ở inbound/outbound adapter, gateway, poller, MessageChannel, WireTap, LoggingHandler, converter, error channel, client và framework logger. Mỗi giao thức File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC có metadata và ranh giới xác nhận khác nhau; log “đã gửi” không thể thay bằng chứng “target đã hoàn tất”. Cách làm bền vững là phối hợp **structured metadata logs, MessageHistory cục bộ, correlation/tracing, Micrometer metrics, audit riêng và xác minh ở hệ thống đích**, đồng thời luôn kiểm thử rằng **không có secrets, PII hoặc raw payload ngoài phạm vi được phép lọt vào telemetry**.
